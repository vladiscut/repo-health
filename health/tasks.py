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
def task_update_all_public_repos(page_token: str | None = None):
    """Обрабатывает порцию страниц и, если остались
    данные, ставит следующую задачу с курсором `page_token`"""

    from health.services import update_all_public_repositories

    next_token = update_all_public_repositories(
        start_page_token=page_token,
    )
    if next_token:
        task_update_all_public_repos.apply_async(args=[next_token])


@app.task
def task_scan_repository():
    # TODO
    pass
