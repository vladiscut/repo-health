from celery.signals import worker_ready

from core.celery import app


@worker_ready.connect
def task_worker_ready_update_all_public_repos(sender, **kwargs):
    with sender.app.connection() as conn:
        sender.app.send_task(
            'health.tasks.task_update_all_public_repos',
            connection=conn
        )


@app.task
def task_update_all_public_repos():
    from health.services import update_all_public_repositories
    update_all_public_repositories()


@app.task
def task_scan_repository():
    # TODO
    pass
