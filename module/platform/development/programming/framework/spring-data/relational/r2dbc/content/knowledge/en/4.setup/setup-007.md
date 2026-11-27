# Preparing a Development Database with Docker Compose

## 1. Purpose of the Development Database Environment

A Spring Data R2DBC application needs to connect to a relational database management system that has a compatible R2DBC driver. During local development, installing and configuring a database directly on the host operating system can create differences between team members' machines: database versions, ports, accounts, settings, and sample data.

**Docker Compose** lets you describe the database and supporting components in a configuration file that can be stored alongside the source code. Team members can start the same database with a consistent configuration using a single command. Containers provide an isolated runtime environment; named volumes preserve data across container recreations.

This lesson uses **PostgreSQL** as an example because the ecosystem has a widely used R2DBC driver and Spring Data R2DBC supports relational data mapping. If your project uses MySQL, MariaDB, or another DBMS, replace the image, initialization parameters, and driver accordingly.

The goals of the development environment are:

- Start the database quickly without installing a database server directly on the host machine.
- Use a uniform database version across team members.
- Persist development data across container stops or recreations.
- Expose a clear port and hostname for the Spring Boot application to connect to.
- Provide a healthcheck to know when the database is ready to accept connections.
- Provide a way to load schemas and sample data for development.

Docker Compose fits local development and integration testing. Development configurations must be reviewed before being used in production, which has separate requirements for secrets, backups, network security, monitoring, HA, and data management.

## 2. How Docker Compose Organizes the Database

Docker Compose describes a multi-container application in a YAML file, commonly named **compose.yaml**. Each runnable component is declared as a service. Compose creates a network so services can communicate by service name, while also managing volumes and port mappings.

For a Spring Data R2DBC application, a simple development setup can look like this:

~~~text
Development machine
    |
    | Spring Boot runs directly on the machine
    | R2DBC URL: localhost:5432
    v
127.0.0.1:5432  (published port)
    |
    v
Docker Compose network
    |
    v
Service: db (PostgreSQL container)
    |
    +---- Named volume: postgres_data
           database data is persisted
~~~

If the Spring Boot application also runs inside a container belonging to the same Compose project, the application connects to hostname **db** and internal port **5432**. On a Compose network, the service name acts as a DNS name.

Distinguish three concepts:

- **Service** describes how a component runs, such as its image, environment variables, ports, volumes, and healthcheck.
- **Container** is the actual running instance created from a service.
- **Volume** is storage independent of the container lifecycle. Deleting and recreating a container does not delete the volume.

## 3. Preparing Tools

You need Docker Engine or Docker Desktop with Docker Compose plugin support. On Windows, Docker Desktop is usually the most convenient setup; ensure the Docker daemon is running before executing Compose commands.

Check versions:

~~~bash
docker --version
docker compose version
~~~

The second command must recognize the Docker Compose plugin. This guide uses the **docker compose** (Compose V2) syntax. If the terminal reports command not found or cannot connect to the Docker daemon, check Docker Desktop and the engine status before troubleshooting the Compose file.

Place `compose.yaml` in the project root directory or a clearly agreed devops directory. The commands below assume your terminal is inside the directory containing that file.

## 4. Creating compose.yaml for PostgreSQL

Create **compose.yaml**:

~~~yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: ${DB_NAME:-app}
      POSTGRES_USER: ${DB_USER:-app}
      POSTGRES_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD in .env}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./db/init:/docker-entrypoint-initdb.d:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 5s

volumes:
  postgres_data:
~~~

The example uses the **postgres:17** image to pin PostgreSQL's major version. Real projects should select the major version matching their target environment and pin a tested version. Avoid using the **latest** tag if you need reproducible development results.

Meaning of the configuration fields:

| Setting | Purpose |
|---|---|
| **image** | Selects the PostgreSQL image and specific version |
| **POSTGRES_DB** | Creates the default database when initializing the data directory for the first time |
| **POSTGRES_USER** | Creates the initial superuser of the container |
| **POSTGRES_PASSWORD** | Sets the password for the initial user |
| **ports** | Publishes the database port to the development machine's loopback interface |
| **postgres_data** | Stores database data in a named volume |
| **./db/init** | Holds SQL initialization scripts, mounted read-only |
| **healthcheck** | Checks whether PostgreSQL is ready to accept connections |

The port is bound to **127.0.0.1** so the database only accepts connections from the development machine over loopback. If the team needs access from other machines on the network, intentionally redesign the port publishing and firewall rules; do not accidentally expose the database on all interfaces.

In the healthcheck, the **$$** notation instructs Compose to pass environment variables through to the shell inside the container rather than interpolating them on the host machine. The **pg_isready** command checks whether PostgreSQL is accepting connections. A passing healthcheck indicates the database is ready for connections; it does not guarantee that business schemas or sample data are already valid.

Mounting **./db/init** is optional. If you do not have initialization scripts yet, you can create an empty directory or remove that volume line.

## 5. Managing Environment Variables and Connection Details

Do not hardcode real passwords directly in a Compose file committed to Git. You can use a **.env** file in the same directory as `compose.yaml` so Compose interpolates configuration variables.

Create a **.env** file for your development machine:

~~~dotenv
DB_NAME=app
DB_USER=app
DB_PASSWORD=local-dev-password
~~~

The password in the example is for local development only. Each team can choose its own development password according to project conventions. The `.env` file containing local values should be added to **.gitignore**. Instead, commit a **.env.example** file containing no real secrets:

~~~dotenv
DB_NAME=app
DB_USER=app
DB_PASSWORD=replace-with-a-local-password
~~~

New team members copy `.env.example` to `.env` and update the values appropriately. Docker Compose automatically reads `.env` in the project directory to substitute expressions like **${DB_NAME:-app}** in `compose.yaml`.

The syntax **${DB_PASSWORD:?Set DB_PASSWORD in .env}** requires `DB_PASSWORD` to have a value. If it is missing, Compose fails immediately while parsing the configuration instead of silently starting the database with an empty password.

You can inspect the Compose configuration after variables are provided:

~~~bash
docker compose config
~~~

This command prints the interpolated configuration. Because the output may contain sensitive values, do not paste the raw output into public issues or logs. Mask passwords and tokens before sharing configurations.

## 6. Starting and Verifying the Database

In the directory containing `compose.yaml`, run:

~~~bash
docker compose up -d db
~~~

Compose pulls the image if not already present, creates the network, creates the volume, and starts the **db** service in detached mode.

Check status:

~~~bash
docker compose ps
~~~

The health status column may display **starting**, **healthy**, or **unhealthy**. If the container is not healthy yet, check the logs:

~~~bash
docker compose logs -f db
~~~

Press Ctrl+C to exit log following; this does not stop the container.

You can test PostgreSQL from inside the container:

~~~bash
docker compose exec db pg_isready -U app -d app
~~~

Or run an SQL query:

~~~bash
docker compose exec db psql -U app -d app -c "SELECT version();"
~~~

These commands use `app` from the sample `.env` file. If you changed `DB_NAME` or `DB_USER`, update the arguments accordingly.

To list databases:

~~~bash
docker compose exec db psql -U app -d app -c "\l"
~~~

To open an interactive shell:

~~~bash
docker compose exec db psql -U app -d app
~~~

Inside `psql`, you can run SQL and exit with **\q**.

## 7. Connecting Spring Data R2DBC to PostgreSQL

How you write the R2DBC URL depends on where the Spring Boot application is running.

### 7.1. Application Running Directly on the Development Machine

If Spring Boot runs from an IDE or Gradle on the host, the application accesses the published port via **localhost:5432**.

Example in `application.properties`:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://localhost:5432/app
spring.r2dbc.username=app
spring.r2dbc.password=${DB_PASSWORD}
~~~

You can parameterize the user and database via environment variables if the project needs to support multiple setups:

~~~properties
spring.r2dbc.url=${R2DBC_URL:r2dbc:postgresql://localhost:5432/app}
spring.r2dbc.username=${DB_USER:app}
spring.r2dbc.password=${DB_PASSWORD}
~~~

Ensure the Spring Boot process receives the corresponding environment variables. Docker Compose reads `.env` automatically for `compose.yaml` interpolation; it does not automatically inject those variables into a Java process running directly on the host. Configure environment variables in your IDE, terminal, or launcher according to your project's conventions.

### 7.2. Spring Boot Application Also Running in Docker Compose

If both the application and database are on the same Compose network, use the service name **db** as the hostname:

~~~properties
spring.r2dbc.url=r2dbc:postgresql://db:5432/app
spring.r2dbc.username=app
spring.r2dbc.password=${DB_PASSWORD}
~~~

In this case, do not use `localhost`. Inside the application container, `localhost` points to the application container itself. The name **db** is resolved by Docker Compose to the database container's address.

You can add the application service to `compose.yaml` like this:

~~~yaml
services:
  db:
    image: postgres:17
    environment:
      POSTGRES_DB: ${DB_NAME:-app}
      POSTGRES_USER: ${DB_USER:-app}
      POSTGRES_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD in .env}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 5s
      retries: 10
      start_period: 5s

  app:
    build: .
    environment:
      SPRING_R2DBC_URL: r2dbc:postgresql://db:5432/${DB_NAME:-app}
      SPRING_R2DBC_USERNAME: ${DB_USER:-app}
      SPRING_R2DBC_PASSWORD: ${DB_PASSWORD:?Set DB_PASSWORD in .env}
    depends_on:
      db:
        condition: service_healthy

volumes:
  postgres_data:
~~~

This illustrates how the connection is wired; the `app` service requires a suitable `Dockerfile` in the project. If you only run the database in Compose and run the application from your IDE, you do not need to declare the `app` service.

**depends_on with condition: service_healthy** makes Compose wait until the database healthcheck reaches `healthy` before starting `app`. It reduces startup connection failures caused by the database not being ready yet on first boot. The application should still have a retry or connection error handling strategy in case the database restarts while `app` is running.

### 7.3. R2DBC Dependencies in a Spring Boot Project

With Gradle Groovy DSL, a Spring Data R2DBC application using PostgreSQL typically needs:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-r2dbc'
    runtimeOnly 'org.postgresql:r2dbc-postgresql'
}
~~~

The starter provides Spring Data R2DBC integration; the PostgreSQL driver provides communication over the R2DBC SPI. Let Spring Boot dependency management manage compatible versions instead of mixing incompatible driver and framework versions yourself.

Simply running PostgreSQL in Docker does not put an R2DBC driver inside your application. The database container and the application dependencies are two separate pieces of configuration—both are required.

## 8. Creating the Schema and Sample Data

A fresh database needs tables and data so the application can be developed, APIs can be tested, and repositories can be verified. You can use the PostgreSQL image's init scripts for simple local environments.

Create the directory layout:

~~~text
project/
├── compose.yaml
├── .env
├── .env.example
└── db/
    └── init/
        └── 001-schema.sql
~~~

Example **db/init/001-schema.sql**:

~~~sql
CREATE TABLE IF NOT EXISTS customers (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    status VARCHAR(30) NOT NULL
);

INSERT INTO customers (name, email, status)
VALUES
    ('An Nguyen', 'an@example.test', 'ACTIVE'),
    ('Binh Tran', 'binh@example.test', 'INACTIVE')
ON CONFLICT (email) DO NOTHING;
~~~

The official PostgreSQL image runs scripts inside **/docker-entrypoint-initdb.d** when initializing a new data directory. Scripts are executed in alphabetical filename order. Mounting read-only allows the container to read scripts without writing back into the project's source tree.

Verify the table and data after database initialization:

~~~bash
docker compose exec db psql -U app -d app -c "SELECT id, name, email, status FROM customers ORDER BY id;"
~~~

**Important note on init script lifecycle:** scripts in the init directory only run when the data directory is initialized for the first time and is still empty. If the `postgres_data` volume already contains data, editing `001-schema.sql` and running `docker compose up` again will not re-run the script automatically.

For projects that need to manage schema changes over time, use a migration tool such as Flyway or Liquibase with version-controlled migrations. Container init scripts are convenient for bootstrapping a brand-new database, but they do not replace application migration workflows. Some migration tools use JDBC; that can be configured separately even when the application's runtime data access path uses R2DBC.

## 9. Container Lifecycle and Data in Volumes

Containers and database data have different lifecycles. Named volumes keep data intact when containers are stopped or removed and recreated.

Common commands:

| Command | Effect |
|---|---|
| **docker compose up -d db** | Creates or starts the database service in the background |
| **docker compose stop db** | Stops the container while keeping both container and volume |
| **docker compose start db** | Restarts an already-stopped container |
| **docker compose restart db** | Restarts the service |
| **docker compose down** | Stops and removes the project's containers and network; named volumes are kept by default |
| **docker compose down -v** | Removes containers, network, and named volumes of the project |
| **docker compose logs -f db** | Streams database logs |
| **docker compose exec db psql -U app -d app** | Opens `psql` inside the container |

Only run **docker compose down -v** when you intentionally want to wipe the development database data and start fresh. That operation deletes volumes; data stored in those volumes will be lost. If you just want to shut down the environment at the end of the day, use **docker compose stop** or **docker compose down**.

You can list volumes created by Compose:

~~~bash
docker volume ls
~~~

Actual volume names are typically prefixed with the Compose project name. Do not edit PostgreSQL data files directly inside the volume while the container is running.

## 10. Configuration and Conventions for Development Teams

So every team member can spin up an identical environment, agree on a few conventions in the repository:

- Store `compose.yaml` with the project or in a designated devops directory.
- Pin the PostgreSQL major version and change versions deliberately.
- Commit `.env.example` but never commit `.env` containing local passwords.
- Add `.env`, dumps containing sensitive data, and secret files to `.gitignore`.
- Name databases, users, ports, and volumes consistently.
- Place initialization scripts in a clearly structured directory; use versioned migrations for long-term schema evolution.
- Document commands to start, inspect, and stop the database in the project's README.
- Never use real personal or production data in local environments unless sanitized and authorized.

Example lines for `.gitignore`:

~~~gitignore
.env
.env.*
!.env.example
~~~

These rules ignore `.env` and its variants while still allowing `.env.example` to be committed. If the project already has custom ignore rules, merge them carefully so you do not accidentally ignore other sample configuration files.

## 11. Troubleshooting Common Issues

### 11.1. Port 5432 Is Already in Use

A common error is Docker failing to bind the host port because it is already used by a locally installed PostgreSQL instance or another container.

Check running containers:

~~~bash
docker compose ps
docker ps
~~~

You can change the host port in `compose.yaml`, for example:

~~~yaml
ports:
  - "127.0.0.1:5433:5432"
~~~

In that case, applications running directly on the machine must connect to **localhost:5433**. Applications inside the same Compose network still connect to **db:5432**, because the container's internal port has not changed.

### 11.2. Application Cannot Connect to the Database

Check in order:

1. Is the container running via **docker compose ps**?
2. Does the healthcheck report `healthy`?
3. Do PostgreSQL logs show initialization or authentication errors?
4. Is the application running on the host or inside a container?
5. Do hostname and port match where the application is running?
6. Do database name, username, and password match what initialized the volume?

A very common mistake is using **localhost** inside an application container. On a Compose network, use the service name **db**. Conversely, an application running directly on the development machine must use the published host address, such as **localhost:5432**.

### 11.3. Password in .env Changed, but Database Still Rejects Login

The official image's `POSTGRES_DB`, `POSTGRES_USER`, and `POSTGRES_PASSWORD` variables are used to initialize the database when the data directory is empty. If the named volume already contains a database, changing environment variables does not update passwords or recreate users in the existing database.

There are two ways to resolve this:

- If you need to keep data, log in with an account that has sufficient privileges and update the user/password via SQL.
- If this is a disposable development database, deliberately remove the volume and restart so the image initializes a fresh data directory.

Do not delete a volume just to test a configuration change without confirming its data can be discarded.

### 11.4. Healthcheck Remains Unhealthy

Check the logs:

~~~bash
docker compose logs --tail=200 db
~~~

Verify the interpolated database and user values, healthcheck syntax, volume initialization state, and machine resources. The user and database used by the healthcheck must exist in the instance. If the healthcheck configuration differs from the account initialized in the volume, the check can fail even while the server is running.

### 11.5. Init SQL Was Edited, but Schema Did Not Change

Init scripts do not re-run against an already-initialized data directory. To update an existing database schema, use migrations or controlled SQL execution. Only recreate the volume if you want to reset the entire development database and accept losing current data.

### 11.6. Application Starts Before the Database

Declaring a plain list under **depends_on** does not mean the database is ready to accept connections. Use a healthcheck and **condition: service_healthy** when the app is also managed by Compose. Additionally, the application should handle connection retries if the database starts slowly or restarts.

## 12. Recommended Daily Workflow

A typical local workflow looks like this:

~~~text
First time cloning the project
       |
       v
Copy .env.example to .env
       |
       v
Update local configuration
       |
       v
docker compose up -d db
       |
       v
Check healthcheck and logs
       |
       v
Run migrations / prepare schema
       |
       v
Start Spring Boot
       |
       v
Develop and test repositories
       |
       v
docker compose stop (when stopping is needed)
~~~

Core commands:

~~~bash
# Start the database
docker compose up -d db

# Check status
docker compose ps

# View logs
docker compose logs -f db

# Check PostgreSQL
docker compose exec db pg_isready -U app -d app

# Stop the database, keep data
docker compose stop db
~~~

When returning to work, run **docker compose start db** or **docker compose up -d db**. The volume preserves the database so you do not have to reload data from scratch.

## 13. Checklist for Onboarding New Team Members

A development environment can be considered ready for another team member when:

- Docker Engine and the Docker Compose plugin run properly.
- `compose.yaml` parses cleanly with **docker compose config** after setting `.env`.
- The PostgreSQL image version is pinned.
- The database starts and its healthcheck reaches `healthy`.
- You can connect with `psql` from the container.
- Spring Boot uses the right R2DBC URL for where it runs (`localhost` from host or `db` from a container).
- The R2DBC driver dependency matches the chosen database.
- Schema and sample data are created via init scripts or migrations.
- Stopping and restarting the container preserves data in the named volume.
- The README documents how to start, inspect, stop, and reset the development database.

## 14. Conclusion

Docker Compose standardizes development databases by describing services, networks, ports, volumes, environment variables, and healthchecks in configuration shared with the repository. With Spring Data R2DBC, PostgreSQL can run in its own container while the application connects via an R2DBC URL.

The most important rule when configuring connections is that the hostname depends on where the application runs: **localhost** when Spring Boot runs on the host and the **Compose service name** when Spring Boot runs on the same container network. Named volumes preserve data across container lifecycles; PostgreSQL init scripts run only when initializing the data directory for the first time. Once these rules are clear, the team can spin up consistent development environments and focus on implementing and testing the data access layer.
