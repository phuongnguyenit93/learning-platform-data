# Persisting Data with Volumes and Recreating Environments

When running MySQL in Docker, data lives inside the MySQL data directory inside the container. If data is only stored in the container's writable layer, removing and recreating the container can wipe out the entire database. To make data survive restarts, updates, or container recreations, you need to mount a volume to the MySQL data directory.

This practical lesson sets up a MySQL Server with Docker Compose, persists data in a named volume, creates a verification record, then recreates the container and confirms the data is still intact. The lesson also distinguishes volumes from backups to avoid confusing persistent storage with data recoverability.

## 1. Objectives and Prerequisites

After this lesson, you will be able to:

- Explain why data in a container's writable layer can be lost when the container is replaced.
- Declare a named volume and mount it to `/var/lib/mysql`.
- Start, check status, and connect to MySQL using Docker Compose.
- Recreate the container to verify that data is retained.
- Distinguish `docker compose down` from `docker compose down -v`.
- Recognize why volumes cannot replace backups.

You need Docker Desktop or Docker Engine with Docker Compose v2 support installed, Docker Engine running, and a terminal to run `docker` commands. Verify your tools:

```bash
docker --version
docker compose version
```

Create a dedicated working directory, such as `mysql-volume-lab`, and place the files for this exercise inside it.

## 2. Understanding Where Docker Stores Data

A container has a writable layer tied to the container's lifecycle. When the container is removed, that writable layer is deleted as well. Therefore, database data stored solely inside the container's private filesystem does not persist across container replacement.

A Docker volume is a storage area managed by Docker independently of the container lifecycle. When you declare a volume in Compose and mount it to `/var/lib/mysql`, MySQL reads and writes database files in the volume. The container can be stopped, removed, or recreated; the volume remains as long as the operation does not request deleting the volume.

```mermaid
flowchart LR
    C["MySQL Container"] -->|"mounted at /var/lib/mysql"| V[("Named volume mysql_data")]
    R["Recreate container"] --> C
    V --> D["Database files are preserved"]
```

In this example:

- The container provides the MySQL Server process and runtime environment.
- `/var/lib/mysql` is the default data directory of the official MySQL image.
- `mysql_data` is the volume name declared in Docker Compose.
- Data is stored in the volume, independent of the container's own writable layer.

Named volumes are usually the right choice for database data because Docker manages their lifecycle and storage location. You do not need to manually pick a physical path inside Docker Desktop or access MySQL's internal files directly.

## 3. Creating the MySQL Configuration with Docker Compose

In the `mysql-volume-lab` directory, create three files: `compose.yaml`, `.env.example`, and `.gitignore`.

### 3.1. Creating the Sample Environment Variables File

Contents of `.env.example`:

```dotenv
MYSQL_ROOT_PASSWORD=replace-with-a-strong-local-root-password
MYSQL_DATABASE=appdb
MYSQL_USER=appuser
MYSQL_PASSWORD=replace-with-a-strong-local-app-password
```

Copy the sample file to `.env` so Docker Compose automatically reads the variables on startup:

```bash
cp .env.example .env
```

On Windows PowerShell, the equivalent command is:

```powershell
Copy-Item .env.example .env
```

Open `.env` and replace the two placeholder passwords with your own passwords for the practice environment. Do not commit `.env` to Git because it contains credentials. The `.env.example` file only contains variable names and illustrative placeholders, not real passwords.

### 3.2. Keeping Secrets Out of Git

Contents of `.gitignore`:

```gitignore
.env
backup.sql
*.sql.gz
```

If the project already has a `.gitignore`, append the necessary lines to the existing file instead of overwriting existing rules.

### 3.3. Declaring the Service and Named Volume

Contents of `compose.yaml`:

```yaml
services:
  db:
    image: mysql:8.4
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:?Set MYSQL_ROOT_PASSWORD in .env}
      MYSQL_DATABASE: ${MYSQL_DATABASE:-appdb}
      MYSQL_USER: ${MYSQL_USER:-appuser}
      MYSQL_PASSWORD: ${MYSQL_PASSWORD:?Set MYSQL_PASSWORD in .env}
    ports:
      - "127.0.0.1:3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "127.0.0.1", "--silent"]
      interval: 5s
      timeout: 5s
      retries: 20
      start_period: 20s

volumes:
  mysql_data:
```

Configuration explanation:

- `image: mysql:8.4` selects the MySQL 8.4 image for the practice environment. In production deployments, select a tested version and manage an upgrade plan.
- `environment` passes initialization variables to the official MySQL image. `MYSQL_ROOT_PASSWORD` sets the root password; the other three variables create the database and application account on initial setup.
- `ports` binds the MySQL port only to the host machine's `127.0.0.1` loopback interface, suitable for a lab running on a personal computer. If port `3306` is already used by another program, you can change the host port, for example `127.0.0.1:3307:3306`.
- `mysql_data:/var/lib/mysql` mounts the named volume `mysql_data` to the exact directory where MySQL stores data.
- `healthcheck` checks whether the server is responding. A `healthy` status indicates MySQL is ready more reliably than merely seeing that the container is running.
- Top-level `volumes` declares the named volume managed by Compose. Docker usually prepends the project name as a prefix to the actual volume name.

If another application also runs in the same Compose project, that application connects to hostname `db` and port `3306`. The `127.0.0.1:3306` entry in `ports` is for tools running on the host machine; inside the Compose network, `localhost` for an application refers to the application container itself, not the MySQL container.

## 4. Starting and Verifying MySQL

Run these commands from the directory containing `compose.yaml`:

```bash
docker compose up -d
docker compose ps
```

The first command pulls the image if not already present locally, creates the network, creates the named volume if needed, and starts the container. First-time database initialization may take extra time. Check `docker compose ps` until the `db` service shows status `healthy`.

If you want to watch the initialization progress:

```bash
docker compose logs -f db
```

Press `Ctrl+C` to stop tailing the logs; this does not stop the container.

Connect to the database using the application account:

```bash
docker compose exec db mysql -uappuser -p appdb
```

When the terminal prompts for the password, enter the `MYSQL_PASSWORD` value from `.env`. Using `-p` without a password lets the MySQL client prompt interactively, avoiding placing passwords directly in command history.

At the MySQL prompt, create a table and a verification record:

```sql
CREATE TABLE IF NOT EXISTS volume_demo (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    note VARCHAR(200) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id)
) ENGINE=InnoDB;

INSERT INTO volume_demo (note)
VALUES ('Data persists after recreating the container');

SELECT id, note, created_at
FROM volume_demo
ORDER BY id;
```

Note the query output, then exit MySQL:

```sql
exit;
```

You can list the volumes managed by Docker with:

```bash
docker volume ls
```

Compose volumes typically have names like `<project>_mysql_data`; the prefix varies by project name or Compose configuration. You can inspect details of a volume using `docker volume inspect <volume-name>` after getting the actual name from the list.

## 5. Recreating the Container and Verifying Data Intactness

This is the most important step of the exercise. Recreate the `db` service:

```bash
docker compose up -d --force-recreate db
docker compose ps
```

Wait for the service to return to `healthy` status, then query the record you created:

```bash
docker compose exec db mysql -uappuser -p appdb -e "SELECT id, note, created_at FROM volume_demo ORDER BY id;"
```

Enter the application password again when prompted. The record still appears because the new container re-mounted the `mysql_data` volume containing the previous data directory. You can also run a full stop-and-start cycle of the entire project:

```bash
docker compose down
docker compose up -d
```

Once MySQL is healthy, re-run the `SELECT` statement to confirm the data is still there. `docker compose down` removes the project's containers and network while preserving named volumes by default.

### Why Don't Initialization Variables Re-run?

The official MySQL image uses variables like `MYSQL_DATABASE`, `MYSQL_USER`, and `MYSQL_PASSWORD` during initialization of an empty datadir. When `/var/lib/mysql` already contains a database, the image preserves the existing data and does not re-run the initialization process.

Therefore, if you edit `MYSQL_PASSWORD` in `.env` and only recreate the container, the password of the existing user in MySQL does not change automatically. Change passwords using the appropriate SQL statement, or use a new volume when you genuinely want to create a brand-new lab database. Never treat editing `.env` as a data migration operation.

## 6. Understanding Which Commands Keep or Delete Volumes

Common operations have different effects:

| Command | Container / network | Project named volume |
| --- | --- | --- |
| `docker compose stop` | Stops container | Preserved |
| `docker compose start` | Starts stopped container | Reuses existing volume |
| `docker compose up -d --force-recreate` | Recreates container | Preserved and re-mounted |
| `docker compose down` | Removes project containers and network | Preserved by default |
| `docker compose down -v` | Removes project containers and network | Deletes named volumes declared in the project and associated anonymous volumes |

**Be careful with `docker compose down -v`:** this command can delete the volume containing the database and destroy lab data. Only use it when you intentionally want to wipe data and have verified the exact project/volume. Commands like `docker volume rm` and `docker volume prune` can also delete volume data; confirm the exact target before running them.

If you want to restart the lab from scratch, first confirm there is no data worth keeping and check the current project. Only then run `docker compose down -v`, followed by `docker compose up -d` so Compose creates an empty volume and MySQL initializes a fresh database from `.env`.

## 7. How Do Named Volumes and Bind Mounts Differ?

Docker has two common ways to mount data:

| Criterion | Named Volume | Bind Mount |
| --- | --- | --- |
| Example | `mysql_data:/var/lib/mysql` | `./mysql-data:/var/lib/mysql` |
| Location | Managed by Docker | Specific path on the host machine |
| Best suited for | Database data needing a lifecycle independent of the container | When direct access to a specific host directory is required |
| Notes | Requires volume lifecycle management and backups | Prone to permissions, path, and cross-OS filesystem differences |

For this MySQL practice lesson, a named volume is the default choice. Bind mounts can be useful in certain development workflows, but they require understanding file ownership and filesystem behavior of the OS/VM Docker is using. Never modify InnoDB data files directly while the server is running; use SQL or an appropriate backup tool.

## 8. Volumes Do Not Replace Backups

A volume protects data from being lost when a container alone is removed or replaced, but the volume itself can still be deleted, corrupted, or lost along with the host machine/disk. A volume does not create an independent copy and cannot recover data accidentally deleted by a user or wrongly written by an application.

For the lab's InnoDB database, you can create a logical backup with `mysqldump`. The following example runs from Bash or Git Bash in the project directory; the shell redirects the dump output from the container into `backup.sql` on the host machine:

```bash
docker compose exec -T db sh -c 'exec mysqldump --single-transaction --no-tablespaces -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' > backup.sql
```

`--single-transaction` creates a consistent snapshot for transactional tables like InnoDB under suitable conditions; avoid running DDL operations that alter table structures during the dump. Backup files contain sensitive data and must be protected, access-restricted, and stored independently of the source volume.

When you need to restore into a target database that already exists and is in an appropriate state, you can use:

```bash
docker compose exec -T db sh -c 'exec mysql -u"$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE"' < backup.sql
```

Do not blindly import into a database that already contains data, as you may hit table-already-exists errors or alter existing data. Test restores in a separate environment, verify row counts, and verify data readability afterward. A backup is only trustworthy once the restore procedure has also been verified.

## 9. Common Issues

| Symptom | Possible Cause | How to Check or Resolve |
| --- | --- | --- |
| Container stays `starting` or `unhealthy` | MySQL is still initializing, missing environment variables, or misconfiguration | Check `docker compose logs db`, inspect `.env`, and wait for initial setup to finish |
| `Access denied` on login | Wrong user/password, or `.env` changed while volume holds older account credentials | Verify existing accounts; change the password via SQL or follow an intentional reset process |
| Port `3306` already in use | Another MySQL instance is listening on the host | Change host port to `127.0.0.1:3307:3306` and connect from the host on port `3307` |
| Data disappears after recreate | Volume not mounted to the right path, volume was deleted, or project is using a different volume | Check `compose.yaml`, `docker volume ls`, and `docker volume inspect` |
| Changed `MYSQL_DATABASE` but database did not change | Datadir was already initialized so init variables did not re-run | Apply changes via SQL/migrations or create a new volume if resetting the lab |

Do not delete the volume immediately when hitting a login or startup error. First read the logs, identify which volume is attached, and check whether the data needs to be preserved.

## 10. Self-Practice Exercises

1. Start the project and insert at least three records into `volume_demo`.
2. Run `docker compose up -d --force-recreate db`, then verify all three records are still present.
3. Run `docker compose down`, start it again with `docker compose up -d`, and confirm the data still exists.
4. Run `docker volume ls`, identify the project's volume name, and use `docker volume inspect` to view its metadata.
5. Create `backup.sql`, verify the file contains SQL content, and practice restoring into a separate lab database.
6. Explain what happens if you run `docker compose down -v`; only execute it once you accept deleting all lab data.

## 11. Summary

To keep MySQL data across container lifecycles, mount a named volume at `/var/lib/mysql`. Docker Compose preserves named volumes on a normal `down` or service recreate, whereas `docker compose down -v` can delete volumes and the databases inside them. The MySQL image's initialization variables apply only when the datadir is initialized for the first time; changing `.env` does not automatically update existing accounts or schemas.

Volumes allow data to live independently of containers. Independent backups and tested restores ensure data can be recovered if the volume or host fails. A solid practice environment requires understanding both mechanisms, verifying data after recreating containers, and carefully controlling any volume-deletion operations.
