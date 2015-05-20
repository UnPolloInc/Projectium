# -*- coding: utf-8 -*-
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ObjectDoesNotExist
from django.core.mail import send_mail
from django.core.urlresolvers import reverse, reverse_lazy
from django.forms.models import modelform_factory, inlineformset_factory, modelformset_factory
from django.http import HttpResponseRedirect, HttpResponseForbidden, Http404
from django.db import transaction
from django.shortcuts import get_object_or_404, render
from django.template.loader import get_template, render_to_string
from django.utils import timezone
from django.views import generic
from django.views.generic import detail
from django.views.generic.detail import SingleObjectTemplateResponseMixin
from guardian.mixins import LoginRequiredMixin
from guardian.shortcuts import get_perms, get_perms_for_model, assign_perm
from guardian.utils import get_403_or_None
import reversion
from project.forms import RegistrarActividadForm
from project.models import UserStory, Proyecto, MiembroEquipo, Sprint, Actividad, Nota
from project.views import CreateViewPermissionRequiredMixin, GlobalPermissionRequiredMixin
from django.contrib.sites.shortcuts import get_current_site


class UserStoriesList(LoginRequiredMixin, GlobalPermissionRequiredMixin, generic.ListView):
    '''
    Lista de User Stories del proyecto
    '''
    model = UserStory
    template_name = 'project/userstory/userstory_list.html'
    permission_required = 'project.view_project'
    context_object_name = 'userstories'
    project = None

    def get_permission_object(self):
        if not self.project:
            self.project = get_object_or_404(Proyecto, pk=self.kwargs['project_pk'])
        return self.project

    def get_context_data(self, **kwargs):
        context = super(UserStoriesList, self).get_context_data(**kwargs)
        context['proyecto_perms'] = get_perms(self.request.user, self.project)
        return context

    def get_queryset(self):
        manager = UserStory.objects
        if not self.project:
            self.project = get_object_or_404(Proyecto, pk=self.kwargs['project_pk'])
        return manager.filter(proyecto=self.project)

class ApprovalPendingUserStories(UserStoriesList):
    permission_required = 'project.aprobar_userstory'
    template_name = 'project/userstory/userstory_pending.html'
    def get_queryset(self):
        manager = UserStory.objects
        if not self.project:
            self.project = get_object_or_404(Proyecto, pk=self.kwargs['project_pk'])
        return manager.filter(proyecto=self.project, estado=2)

class UserStoryDetail(LoginRequiredMixin, GlobalPermissionRequiredMixin, generic.DetailView):
    """
    Vista de Detalles de un user story
    """
    model = UserStory
    permission_required = 'project.view_project'
    template_name = 'project/userstory/userstory_detail.html'
    context_object_name = 'userstory'

    def get_permission_object(self):
        '''
        Retorna el objeto al cual corresponde el permiso
        '''
        return self.get_object().proyecto

class AddUserStory(LoginRequiredMixin, CreateViewPermissionRequiredMixin, generic.CreateView):
    """
    View que agrega un user story al sistema
    """
    model = UserStory
    template_name = 'project/userstory/userstory_form.html'
    permission_required = 'project.create_userstory'

    def get_form_class(self):
        project = get_object_or_404(Proyecto, id=self.kwargs['project_pk'])
        form_fields = ['nombre', 'descripcion', 'valor_negocio', 'valor_tecnico', 'tiempo_estimado']
        if 'prioritize_userstory' in get_perms(self.request.user, project):
            form_fields.insert(2, 'prioridad')
        form_class = modelform_factory(UserStory, fields=form_fields)
        return form_class

    def get_permission_object(self):
        '''
        Objeto por el cual comprobar el permiso
        '''
        return get_object_or_404(Proyecto, id=self.kwargs['project_pk'])

    def get_success_url(self):
        """
        :return:la url de redireccion a la vista de los detalles del user story agregado.
        """
        return reverse('project:userstory_detail', kwargs={'pk': self.object.id})

    def form_valid(self, form):
        """
        Comprobar validez del formulario.
        :param form: formulario recibido
        :return: URL de redireccion
        """
        self.object = form.save(commit=False)
        self.object.proyecto = get_object_or_404(Proyecto, id=self.kwargs['project_pk'])
        with transaction.atomic(), reversion.create_revision():
            reversion.set_user(self.request.user)
            reversion.set_comment("Version Inicial")
            self.object.save()

        return HttpResponseRedirect(self.get_success_url())

class UpdateUserStory(LoginRequiredMixin, generic.UpdateView):
    """
    View que actualiza un user story del sistema
    """
    model = UserStory
    template_name = 'project/userstory/userstory_form.html'

    def dispatch(self, request, *args, **kwargs):
        """
        Comprobación de permisos hecha antes de la llamada al dispatch que inicia el proceso de respuesta al request de la url
        :param request: request hecho por el cliente
        :param args: argumentos adicionales posicionales
        :param kwargs: argumentos adicionales en forma de diccionario
        :return: PermissionDenied si el usuario no cuenta con permisos
        """
        if 'edit_userstory' in get_perms(request.user, self.get_object().proyecto):
            return super(UpdateUserStory, self).dispatch(request, *args, **kwargs)
        elif 'edit_my_userstory' in get_perms(self.request.user, self.get_object()):
            return super(UpdateUserStory, self).dispatch(request, *args, **kwargs)
        else:
            raise PermissionDenied()

    def get_form_class(self):
        project = self.get_object().proyecto
        form_fields = ['nombre', 'descripcion', 'valor_negocio', 'valor_tecnico', 'tiempo_estimado']
        if 'prioritize_userstory' in get_perms(self.request.user, project):
            form_fields.insert(2, 'prioridad')
        form_class = modelform_factory(UserStory, fields=form_fields)
        return form_class

    def get_context_data(self, **kwargs):
        """
        Agregar datos al contexto
        :param kwargs: argumentos clave
        :return: contexto
        """
        context = super(UpdateUserStory, self).get_context_data(**kwargs)
        context['current_action'] = "Actualizar"
        return context

    def get_success_url(self):
        """
        :return:la url de redireccion a la vista de los detalles del user story agregado.
        """
        return reverse('project:userstory_detail', kwargs={'pk': self.object.id})

    def form_valid(self, form):
        """
        Comprobar validez del formulario. Crea una instancia de user story
        :param form: formulario recibido
        :return: URL de redireccion
        """
        if form.has_changed():
            with transaction.atomic(), reversion.create_revision():
                self.object = form.save()
                reversion.set_user(self.request.user)
                reversion.set_comment("Modificacion: {}".format(str.join(', ', form.changed_data)))
            self.notify(self.object, form.changed_data)

        return HttpResponseRedirect(self.get_success_url())

    def notify(self, user_story, changes):
        proyecto = user_story.proyecto
        changelist = [c.replace('_', ' ').title() for c in changes]
        subject = 'Cambios en User Story: {} - {}'.format(user_story, proyecto)
        domain = get_current_site(self.request).domain
        message = render_to_string('mail/change_mail.html',
                                   {'proyecto': proyecto, 'us': user_story, 'domain': domain, 'cambios': changelist})
        recipients = [u.email for u in proyecto.equipo.all() if u.has_perm('project.aprobar_userstory', proyecto)]
        if user_story.desarrollador and user_story.desarrollador.email not in recipients:
            recipients.append(user_story.desarrollador.email)
        send_mail(subject, message, 'projectium15@gamil.com', recipients, html_message=message)
        #send_mail(subject, message, 'projectium15@gamil.com', ['jayala1993@outlook.com'], html_message=message)


class RegistrarActividadUserStory(LoginRequiredMixin, generic.UpdateView):
    """
    View que permite registrar los cambios aplicados a un user story
    """
    model = UserStory
    template_name = 'project/userstory/userstory_registraractividad_form.html'
    error_template = 'project/userstory/userstory_error.html'
    NoteFormset = modelformset_factory(Nota, fields=('mensaje',), extra=1)

    def get_context_data(self, **kwargs):
        context = super(RegistrarActividadUserStory, self).get_context_data(**kwargs)
        context['formset'] = self.NoteFormset(queryset=Nota.objects.none())
        return context

    def dispatch(self, request, *args, **kwargs):
        """
        Comprobación de permisos hecha antes de la llamada al dispatch que inicia el proceso de respuesta al request de la url
        :param request: request hecho por el cliente
        :param args: argumentos adicionales posicionales
        :param kwargs: argumentos adicionales en forma de diccionario
        :return: PermissionDenied si el usuario no cuenta con permisos
        """
        if 'registraractividad_userstory' in get_perms(request.user, self.get_object().proyecto) \
                or ('registraractividad_my_userstory' in get_perms(request.user, self.get_object())): #Comprobacion de permisos
            if self.get_object().sprint and self.get_object().sprint.inicio.date() <= timezone.now().date() and self.get_object().sprint.fin.date() >= timezone.now().date():
                if self.get_object().actividad:
                    current_priority = self.get_object().prioridad
                    s = self.get_object().sprint
                    a = self.get_object().actividad
                    d = self.get_object().desarrollador
                    bigger_priorities = UserStory.objects.filter(sprint=s, actividad=a, desarrollador=d, prioridad__gt=current_priority).count()
                    if bigger_priorities == 0: #Comprobacion de prioridad del User Story
                        if self.get_object().estado == 1: #Comprobacion de estado del User Story
                            return super(RegistrarActividadUserStory, self).dispatch(request, *args, **kwargs)
                        return render(request, self.error_template, {'userstory': self.get_object(), 'error': "OTRO_ESTADO"})
                return render(request, self.error_template, {'userstory': self.get_object(), 'error': "MENOR_PRIORIDAD"})
            return render(request, self.error_template, {'userstory': self.get_object(), 'error': "SPRINT_VENCIDO"})
        raise PermissionDenied()

    def get_form_class(self):
        """
        Retorna el tipo de formulario que se mostrará en el template. En caso de que
        el usuario cuente con el permiso de editar userstory se le permitirá cambiar la actividad
        del User Story.
        """
        actual_fields = ['estado_actividad']
        if 'edit_userstory' in get_perms(self.request.user, self.get_object().proyecto) or \
                        'edit_my_userstory' in get_perms(self.request.user, self.get_object()):
            actual_fields.insert(1, 'actividad')
        return modelform_factory(UserStory, form=RegistrarActividadForm, fields=actual_fields)

    def get_form(self, form_class):
        '''
        Personalización del form retornado
        '''

        form = super(RegistrarActividadUserStory, self).get_form(form_class)
        if 'actividad' in form.fields:
            form.fields['actividad'].queryset = Actividad.objects.filter(flujo=self.get_object().actividad.flujo)
        return form

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.tiempo_registrado = self.object.tiempo_registrado + form.cleaned_data['horas_a_registrar']
        nota_form = self.NoteFormset(self.request.POST)
        new_estado = 0
        #movemos el User Story a la sgte actividad en caso de que haya llegado a Done
        if form.cleaned_data['estado_actividad'] == 2:
            new_estado = 0
            try:
                next_actividad = self.object.actividad.get_next_in_order()
            except ObjectDoesNotExist:
                next_actividad = self.object.actividad
                self.object.estado = 2 #Lo marcamos como pendiente de aprobación
                new_estado = 2

            self.object.actividad = next_actividad
            self.object.estado_actividad = new_estado

        self.object.save()

        if nota_form.is_valid():
            for f in nota_form.forms:
                n = f.save(commit=False)
                n.horas_registradas = form.cleaned_data['horas_a_registrar']
                n.desarrollador = self.object.desarrollador
                n.sprint = self.object.sprint
                n.actividad = self.object.actividad
                n.estado_actividad = self.object.estado_actividad
                n.user_story = self.object
                n.save()
            self.notify(n)

        return HttpResponseRedirect(self.get_success_url())

    def notify(self, nota):
        proyecto = nota.user_story.proyecto
        subject = 'Registro de Actividad: {} - {}'.format(nota.user_story, proyecto)
        domain = get_current_site(self.request).domain
        message = render_to_string('mail/notification_mail.html', {'proyecto': proyecto, 'nota': nota, 'us': nota.user_story, 'domain': domain})
        recipients = [u.email for u in proyecto.equipo.all() if u.has_perm('project.aprobar_userstory', proyecto)]
        send_mail(subject, message, 'noreply.projectium15@gmail.com', recipients, html_message=message)


class DeleteUserStory(LoginRequiredMixin, GlobalPermissionRequiredMixin, generic.DeleteView):
    """
    Vista de Eliminacion de User Stories
    """
    model = UserStory
    template_name = 'project/userstory/userstory_delete.html'
    permission_required = 'project.remove_userstory'
    context_object_name = 'userstory'

    def get_permission_object(self):
        return self.get_object().proyecto

    def get_success_url(self):
        return reverse_lazy('project:product_backlog', kwargs={'project_pk': self.get_object().proyecto.id})


class ApproveUserStory(LoginRequiredMixin, GlobalPermissionRequiredMixin, SingleObjectTemplateResponseMixin, detail.BaseDetailView):
    """
    Vista de Aprobación o rechazo de User Stories
    """
    model = UserStory
    template_name = 'project/userstory/userstory_approve.html'
    permission_required = 'project.aprobar_userstory'
    context_object_name = 'userstory'
    action = ''

    def dispatch(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.estado == 2:
            return super(ApproveUserStory, self).dispatch(request, *args, **kwargs)
        raise Http404

    def get_context_data(self, **kwargs):
        context = super(ApproveUserStory, self).get_context_data(**kwargs)
        context['action'] = self.action
        return context

    def get_permission_object(self):
        return self.get_object().proyecto

    def get_success_url(self):
        return reverse_lazy('project:product_backlog', kwargs={'project_pk': self.get_object().proyecto.id})

    def post(self, request, *args, **kwargs):
        us = self.get_object()
        if self.action == 'aprobar':
            us.estado = 3 #Aprobado
        elif self.action == 'rechazar':
            us.estado = 1 #Vuelve al estado en desarrollo
            us.estado_actividad = 0 #Vuelve al estado de actividad To Do
            #TODO Logica de eleccion de nueva ubicacion de User Story
        us.save()
        self.notify(us)
        return HttpResponseRedirect(self.get_success_url())

    def notify(self, user_story):
        proyecto = user_story.proyecto
        subject = 'Se ha aprobado el User Story: {} - {}'.format(user_story, proyecto)
        domain = get_current_site(self.request).domain
        message = render_to_string('mail/approved_email.html',
                                   {'proyecto': proyecto, 'us': user_story, 'domain': domain, 'u': self.request.user})
        recipients = [u.email for u in proyecto.equipo.all() if u.has_perm('project.aprobar_userstory', proyecto)]
        if user_story.desarrollador and user_story.desarrollador.email not in recipients:
            recipients.append(user_story.desarrollador.email)
        send_mail(subject, message, 'projectium15@gamil.com', recipients, html_message=message)

class VersionList(LoginRequiredMixin, generic.ListView):
    """
    Vista que devuelve una lista de versiones del User Story deseado.
    """
    context_object_name = 'versions'
    template_name = 'project/version/version_list.html'
    permission_required = ['project.edit_userstory', 'project.edit_my_userstory']
    us = None

    def dispatch(self, request, *args, **kwargs):
        """
        Comprobación de permisos hecha antes de la llamada al dispatch que inicia el proceso de respuesta al request de la url
        :param request: request hecho por el cliente
        :param args: argumentos adicionales posicionales
        :param kwargs: argumentos adicionales en forma de diccionario
        :return: PermissionDenied si el usuario no cuenta con permisos
        """
        self.us = get_object_or_404(UserStory, pk=self.kwargs['pk'])
        if 'edit_userstory' in get_perms(request.user, self.us.proyecto):
            return super(VersionList, self).dispatch(request, *args, **kwargs)
        elif 'edit_my_userstory' in get_perms(self.request.user, self.us):
            return super(VersionList, self).dispatch(request, *args, **kwargs)
        else:
            raise PermissionDenied()

    def get_queryset(self):
        """
        Obtiene el user story y sus versiones
        """
        return reversion.get_for_object(self.us)

    def get_context_data(self, **kwargs):
        """
        Agrega el user story al contexto.
        """
        context = super(VersionList, self).get_context_data(**kwargs)
        context['userstory'] = self.us
        return context


class UpdateVersion(UpdateUserStory):
    '''
    Vista que permite revertir un User Story a una version anterior.
    '''
    version = None

    def get_initial(self):
        """
        Obtiene la version deseada del User Story.
        :return: diccionarnio con los datos de la version anterior.
        """
        version_pk = self.kwargs['version_pk']
        self.version = get_object_or_404(reversion.models.Version, pk=version_pk)
        initial = self.version.field_dict
        return initial

    def form_valid(self, form):
        """
        Comprobar validez del formulario. Crea una instancia de user story
        :param form: formulario recibido
        :return: URL de redireccion
        """
        with transaction.atomic(), reversion.create_revision():
            self.object = form.save()
            reversion.set_user(self.request.user)
            # rev = self.version.revision
            reversion.set_comment("Reversion: {}".format(str.join(', ', form.changed_data)))

        return HttpResponseRedirect(self.get_success_url())