# Setting Up a MongoDB Environment with Docker: Volume Persistence and Connection Configuration

MongoDB is a document database that primarily stores data in BSON format. When learning MongoDB, installing it directly onto the host operating system can cause environments to vary across machines and make switching versions difficult. Docker lets you run MongoDB in a container with an explicit configuration, while Docker Compose lets you describe and start the environment from a single file.

This practice exercise sets up **a standalone MongoDB instance** for local development on a personal machine. Data is stored in a **Docker named volume**, an administrative account is created during initial setup, and the application connects via a MongoDB connection string. At the end of the lesson, we will tear down and recreate the container to prove that the data persists.

## 1. Learning Outcomes and Environment Architecture

After this lesson, you will be able to:

- Start and manage MongoDB using Docker Compose.
- Distinguish data inside a container's writable layer from data in a Docker volume.
- Configure accounts, access ports, and MongoDB connection URIs.
- Connect from a local terminal, from a Java/Spring Boot application, and from another container.
- Verify that data persists after a container is recreated; identify operations that can delete a volume.
- Diagnose common errors involving ports, accounts, host addresses, and startup states.

Environment diagram:

~~~text
Developer Machine (Windows/macOS/Linux)
  |
  | MongoDB URI: mongodb://...@localhost:27017/appdb?authSource=...
  v
127.0.0.1:27017  -- Docker port mapping -->  mongodb:27017
                                                |
                                      MongoDB Container
                                                |
                                            /data/db
                                                |
                                      Docker named volume
                                  mongo-persistence-lab_mongo_data

Application in the same Docker Compose network
  |
  +-- MongoDB URI using hostname mongodb:27017
~~~

Two things to distinguish from the start:

1. **Container** holds the `mongod` process and runtime environment; it can be stopped, removed, and recreated.
2. **Volume** holds MongoDB's data files; its lifecycle is independent of the container, provided we do not explicitly delete the volume.

## 2. Prerequisites

Your machine needs Docker Engine or Docker Desktop, Docker Compose v2, and the ability to pull images from a registry. Docker Desktop on Windows typically uses the WSL 2 backend. You do not have to install MongoDB Server or `mongosh` separately on the host because you can run `mongosh` directly inside the container.

Open a terminal in your working directory and verify:

~~~bash
docker --version
docker compose version
docker info
~~~

The last command must connect to the Docker daemon. If it reports that the daemon is not running, start Docker Desktop or the Docker service before continuing.

In the example, host port **27017** is reserved for MongoDB. If another service is already using that port, you can change the host-side port to 27018 in the configuration step without changing MongoDB's port inside the container.

Create a practice directory:

~~~text
mongo-lab/
├── compose.yaml
├── .env
└── .gitignore
~~~

Run all Docker Compose commands below from the exact directory containing `compose.yaml`. This avoids targeting the wrong Compose project or volume.

## 3. Writing the Docker Compose Configuration File

Create the **compose.yaml** file:

~~~yaml
name: mongo-persistence-lab

services:
  mongodb:
    image: mongo:8.0
    restart: unless-stopped
    ports:
      - "127.0.0.1:27017:27017"
    environment:
      MONGO_INITDB_ROOT_USERNAME: ${MONGO_ROOT_USERNAME:?Set MONGO_ROOT_USERNAME in .env}
      MONGO_INITDB_ROOT_PASSWORD: ${MONGO_ROOT_PASSWORD:?Set MONGO_ROOT_PASSWORD in .env}
    volumes:
      - mongo_data:/data/db
    healthcheck:
      test:
        - CMD
        - mongosh
        - --quiet
        - --eval
        - "if (db.adminCommand({ ping: 1 }).ok !== 1) quit(1)"
      interval: 10s
      timeout: 5s
      retries: 10
      start_period: 20s

volumes:
  mongo_data:
~~~

**Role of each component:**

| Component | Role |
|---|---|
| name | Sets a stable Compose project name; the resulting volume is typically named `mongo-persistence-lab_mongo_data`. |
| image | Uses the MongoDB image from the 8.0 branch. For strictly reproducible environments, you can pin a patch version or image digest after testing. |
| restart | Docker automatically restarts the container according to the `unless-stopped` policy when appropriate. |
| ports | Publishes port 27017 only on the machine's loopback address `127.0.0.1`, restricting access from other machines. |
| environment | The official image uses `MONGO_INITDB_ROOT_USERNAME` and `MONGO_INITDB_ROOT_PASSWORD` to create the administrative account when the data directory is empty. |
| volumes | Mounts the named volume `mongo_data` to the `/data/db` data path inside the container. |
| healthcheck | Runs a `ping` command so Docker can report basic readiness. It does not replace testing authentication or business operations. |

**Why use a named volume?** Docker manages the storage location and file permissions automatically, working consistently across Windows, macOS, and Linux. Bind-mounting a host folder to `/data/db` is also possible, but often runs into differences in file permissions, performance, and filesystem semantics—especially on Docker Desktop.

This file only describes the MongoDB service; there is no Java application yet. Docker Compose automatically creates a default network for the project, so other containers in the same project can reach the service by the hostname **mongodb**.

### 3.1. Declaring Environment Variables

Create the **.env** file alongside `compose.yaml`:

~~~dotenv
MONGO_ROOT_USERNAME=admin
MONGO_ROOT_PASSWORD=DevMongo_2026_Local
MONGO_APP_PASSWORD=AppMongo_2026_Local
~~~

These values are **examples for a learning machine only**; replace them with your own passwords. The `MONGO_APP_PASSWORD` variable will be used if you create an application account later. The MongoDB image **does not automatically create an application account** just because this variable exists in `.env`.

The `.env` file is used by Docker Compose to **substitute variables in `compose.yaml`**. It does not automatically become an environment variable in the terminal running Java, nor does a variable omitted from the service's `environment` section appear inside the container.

Create the **.gitignore** file:

~~~gitignore
.env
backups/
*.archive
*.archive.gz
~~~

Never commit real passwords to a repository. For shared projects, include a `.env.example` file containing only variable names and placeholders so teammates can create their own `.env`.

**Note on first initialization:** the `MONGO_INITDB_ROOT_*` variables only take effect to create the root user when MongoDB's data directory is empty. If the volume already exists and contains data, changing the password in `.env` **does not update the existing account's password**. You must change the password via an administrative operation in MongoDB or, strictly in test environments with disposable data, recreate the volume.

## 4. Starting and Inspecting MongoDB

Validate syntax and configuration values, then start the service:

~~~bash
docker compose config --quiet
docker compose up -d
docker compose ps
docker compose logs --tail 60 mongodb
~~~

The **config --quiet** command validates the Compose configuration without printing resolved variable values to the terminal, helping avoid accidentally leaking passwords. On first startup, Docker may need to pull the image and MongoDB needs to initialize its data files, so it will not accept connections immediately.

In **docker compose ps**, the status column indicates the service is running and, after initialization completes, may show `healthy`. To stream logs continuously:

~~~bash
docker compose logs -f mongodb
~~~

Press `Ctrl+C` to stop watching logs; this does not stop MongoDB running in the background.

To inspect volume details:

~~~bash
docker volume ls
docker volume inspect mongo-persistence-lab_mongo_data
~~~

The `inspect` command shows volume metadata, including its name and the Docker-managed mount path. Do not modify data files directly while `mongod` is running; always interact through a MongoDB client.

### 4.1. Logging In with `mongosh` Inside the Container

The following command opens MongoDB Shell inside the container:

~~~bash
docker compose exec mongodb mongosh --username admin --authenticationDatabase admin
~~~

Enter the password when `mongosh` prompts; in the `.env` example it is **DevMongo_2026_Local**. The authentication database is **admin** because the root user created by the image resides in the `admin` database.

Once inside `mongosh`, try:

~~~javascript
db.adminCommand({ ping: 1 })
db.runCommand({ connectionStatus: 1 })
show dbs
~~~

A successful ping returns `ok: 1`. The `connectionStatus` command lets you inspect the authenticated user. The `show dbs` command lists existing databases you have permission to view.

Type `exit` to leave `mongosh`. You can also install `mongosh` on your host machine and connect to `127.0.0.1:27017`, though that is not required for this lesson.

## 5. Writing Data and Proving Persistence

Inside an authenticated `mongosh` session, switch to the practice database and create a document:

~~~javascript
use appdb

db.products.updateOne(
  { _id: "volume-test-001" },
  {
    $set: {
      name: "Notebook",
      quantity: 3,
      source: "docker-volume-lab"
    }
  },
  { upsert: true }
)

db.products.findOne({ _id: "volume-test-001" })
~~~

MongoDB creates a database and collection upon the first write operation; running **use appdb** alone does not guarantee the database exists on disk. Here, `updateOne` with `upsert` creates the document if it does not exist, allowing you to repeat the exercise without duplicate `_id` errors.

Exit `mongosh` and run:

~~~bash
docker compose down
docker compose up -d
docker compose ps
docker compose exec mongodb mongosh --username admin --authenticationDatabase admin
~~~

In the new `mongosh` session:

~~~javascript
use appdb
db.products.findOne({ _id: "volume-test-001" })
~~~

If the document still has `name` set to `Notebook` and `source` set to `docker-volume-lab`, you have verified that data survived removing and recreating the container. MongoDB writes its data files to `/data/db`; mounting the volume tells Docker to store those files outside the container's writable layer.

**Distinguishing key commands:**

| Command | Effect on Container | Effect on Named Volume |
|---|---|---|
| `docker compose stop` | Stops container. | Preserved. |
| `docker compose start` | Starts existing container. | Reuses existing volume. |
| `docker compose restart mongodb` | Restarts MongoDB service. | Preserved. |
| `docker compose down` | Stops and removes project containers and networks. | Typically preserves named volumes. |
| `docker compose up -d` | Creates or updates containers and runs them in background. | Reattaches same-named volume if present. |
| `docker compose down -v` | Removes containers/networks and project-managed volumes per Compose config. | **Data inside the volume may be permanently deleted.** |

During this exercise, **do not run `down -v`** if you want to keep the data you just created. A named volume is not a backup solution: deleting the volume, disk failure, or data corruption can still cause data loss.

### 5.1. Changing the Host Port Without Touching Data

If host port 27017 is already occupied, edit only the `ports` section to:

~~~yaml
ports:
  - "127.0.0.1:27018:27017"
~~~

Then run:

~~~bash
docker compose up -d
~~~

Now clients running **on the host** use `127.0.0.1:27018`; the MongoDB container still listens on port 27017, and other containers in the same Compose project still use `mongodb:27017`. Data in the named volume is unaffected because port mapping only alters network routing.

## 6. Understanding and Configuring the MongoDB Connection String

A basic MongoDB URI has the form:

~~~text
mongodb://<username>:<password>@<host>:<port>/<database>?authSource=<authenticationDatabase>
~~~

Components:

| URI Part | Meaning |
|---|---|
| `mongodb://` | Uses the standard MongoDB connection protocol. |
| `username`, `password` | MongoDB user credentials to authenticate. |
| `host`, `port` | Service address as seen from **where the client runs**. |
| `database` in path | Default database the application targets. |
| `authSource` | Database storing the user record used for authentication. |

For the practice root account, the URI from the host machine is:

~~~text
mongodb://admin:DevMongo_2026_Local@localhost:27017/appdb?authSource=admin
~~~

Here, **appdb** is the database holding application data, while **admin** is the database used to authenticate the root user. These two databases can differ; omitting `authSource` may cause the driver to attempt authentication against the path database and return `Authentication failed`.

**Choosing the host based on where the client runs:**

| Where Does the Client Run? | MongoDB Host/Port |
|---|---|
| Java, IDE, or `mongosh` on the developer machine | `localhost:27017` or `127.0.0.1:27017` |
| Another service in the same Docker Compose project | `mongodb:27017` |
| `mongosh` running inside the MongoDB container | `localhost:27017` |
| Client on another machine | Requires separate network, firewall, authentication, and secure access setup; this lesson binds only to loopback. |

**`localhost` is always the client's own machine or container.** If the Java application is packaged into another container, `localhost` in the URI points to the application container, not the MongoDB container. Inside a Compose network, use **mongodb**, the service name.

Usernames or passwords containing URI-reserved special characters such as `@`, `:`, `/`, `?`, `#`, or `%` must be **percent-encoded** in the userinfo segment. For example, `@` becomes `%40`. Do not change the actual password stored in MongoDB; only encode its representation in the URI.

### 6.1. Creating a Dedicated Application Account

The root user is convenient for initial setup but should not be used long-term by applications because it holds broad administrative privileges. In `mongosh` logged in as root, create a user with only `readWrite` permissions on `appdb`:

~~~javascript
use appdb

db.createUser({
  user: "app_user",
  pwd: "AppMongo_2026_Local",
  roles: [
    { role: "readWrite", db: "appdb" }
  ]
})
~~~

This is an account for a learning environment, with a password matching `MONGO_APP_PASSWORD` declared earlier for use in the application Compose section below. Replace it with a dedicated password and apply least-privilege roles in real projects.

Host URI for the application account:

~~~text
mongodb://app_user:AppMongo_2026_Local@localhost:27017/appdb?authSource=appdb
~~~

This time `authSource` is **appdb** because the user was created inside `appdb`. You can verify by exiting `mongosh` and logging in:

~~~bash
docker compose exec mongodb mongosh --username app_user --authenticationDatabase appdb
~~~

After entering the password, run:

~~~javascript
use appdb
db.products.findOne({ _id: "volume-test-001" })
~~~

This user can read and write data in `appdb`, but has no system-wide administrative permissions. If you re-run `db.createUser` with the same username, MongoDB reports that the user already exists; to change a password, use an administrative update command rather than recreating a duplicate user.

## 7. Connecting from a Java Application

When writing Java code, externalize the URI via environment variables or your deployment environment's secret manager. That allows the same application to use different configurations when running locally, in a container, or on a server without modifying source code.

### 7.1. Spring Boot with Spring Data MongoDB

In a **Spring Boot 3.x** project with the Spring Data MongoDB dependency, `application.yml` can reference an environment variable:

~~~yaml
spring:
  data:
    mongodb:
      uri: ${MONGODB_URI}
~~~

Example setting `MONGODB_URI` in **PowerShell** before running the application on the host:

~~~powershell
$env:MONGODB_URI = 'mongodb://app_user:AppMongo_2026_Local@localhost:27017/appdb?authSource=appdb'
~~~

Equivalent in **bash/zsh**:

~~~bash
export MONGODB_URI='mongodb://app_user:AppMongo_2026_Local@localhost:27017/appdb?authSource=appdb'
~~~

Then launch the Java application using your project's build tool. If using a different Spring Boot version, check the exact MongoDB property name for that version. The `MONGODB_URI` variable must exist in the **Java process** environment; placing a URI in Docker Compose's `.env` does not automatically pass it to a Java process running outside Docker.

A simple repository to verify connectivity can be written as:

~~~java
import org.springframework.data.mongodb.repository.MongoRepository;

public interface ProductRepository extends MongoRepository<Product, String> {
}
~~~

In this example, `Product` is an entity you define and map to the corresponding collection via Spring Data MongoDB. At application startup, the driver connects using the URI; repository operations like `save` or `findById` send requests to MongoDB. No username or password needs to be written inside the repository.

### 7.2. Java MongoDB Sync Driver Without Spring

If the application uses the MongoDB Java Sync Driver directly, you can verify connectivity with a `ping` command:

~~~java
import com.mongodb.client.MongoClient;
import com.mongodb.client.MongoClients;
import org.bson.Document;

public class MongoConnectionCheck {
    public static void main(String[] args) {
        String uri = System.getenv("MONGODB_URI");
        if (uri == null || uri.isBlank()) {
            throw new IllegalStateException("MONGODB_URI is required");
        }

        try (MongoClient client = MongoClients.create(uri)) {
            Document result = client.getDatabase("appdb")
                    .runCommand(new Document("ping", 1));
            System.out.println(result.toJson());
        }
    }
}
~~~

This example requires the **org.mongodb:mongodb-driver-sync** dependency at a project-compatible version. `MongoClient` is closed cleanly via `try-with-resources`. In a long-running application, you should typically reuse a single `MongoClient` instance rather than creating a new one per query.

### 7.3. When Both Java and MongoDB Run in Docker Compose

Suppose the Java project already has a `Dockerfile`. You can extend the `services` list in `compose.yaml` with this illustrative snippet:

~~~yaml
  app:
    build: .
    environment:
      MONGODB_URI: "mongodb://app_user:${MONGO_APP_PASSWORD:?Set MONGO_APP_PASSWORD in .env}@mongodb:27017/appdb?authSource=appdb"
    depends_on:
      mongodb:
        condition: service_healthy
~~~

The **app** service is illustrative and only runs if you have a real `Dockerfile` and an application reading `MONGODB_URI`. It uses the Compose-provided hostname `mongodb` and requires the `app_user` created in Section 6.1. For an app running in a container, do not use `localhost:27017` because that refers to the app container's own loopback interface.

`depends_on` with `condition: service_healthy` delays starting `app` until MongoDB's healthcheck passes. However, connections can still drop later while the system is running; the application must handle transient errors and implement appropriate retries at the operational layer.

## 8. Initialization Configuration, Volumes, and Data Lifecycle

### 8.1. Distinguishing Initialization Data from Long-Lived Data

The official MongoDB image supports executing scripts under `/docker-entrypoint-initdb.d` when data is initialized for the first time. For example, you can mount a `.js` file to create collections or application users. However, these initialization scripts **do not re-run on a volume that already contains data**. This is an important characteristic when changing configuration after an environment has been used for a few days.

If you add `MONGO_INITDB_DATABASE` to `environment`, do not assume that variable alone creates a populated database. A MongoDB database only materializes on disk when data is written or an init script creates a collection/document.

For schemas or seed data that must run repeatedly, use a dedicated idempotent migration/seed procedure rather than expecting Docker init scripts to execute on every `docker compose up`.

### 8.2. Volumes Are Persistent, Not Backups

A named volume preserves data when a container is replaced, but does not protect against all risks. Before upgrading MongoDB, making major configuration changes, or migrating machines, back up data using an appropriate MongoDB tool (such as `mongodump`/`mongorestore` or a consistent system-level backup mechanism) and verify that you can restore it.

Hot-copying files inside `/data/db` while `mongod` is running should not be treated as a safe backup procedure. To update the image from one MongoDB version to another, read the compatibility guide and upgrade path for that exact version; avoid jumping major versions arbitrarily on a volume holding important data.

In this exercise, a standalone instance suffices for basic CRUD. Multi-document transactions and features requiring a replica set need an explicit MongoDB replica set or cluster configuration—they do not follow automatically from using Docker.

### 8.3. Stopping, Restarting, and Cleaning Up the Environment

Common commands:

~~~bash
# Stop while keeping containers and volumes
docker compose stop

# Start previously stopped containers
docker compose start

# Restart only MongoDB
docker compose restart mongodb

# Tear down project containers/networks, keep named volumes
docker compose down

# Recreate services from compose.yaml
docker compose up -d
~~~

Only when you truly want to **delete all practice data** and have confirmed the volume belongs to the right project should you consider:

~~~bash
docker compose down -v
~~~

That command can delete the volume containing MongoDB data; do not use it in the persistence verification sequence in Section 5.

## 9. Common Issues and Root-Cause Diagnosis

| Symptom | Common Cause | How to Check and Fix |
|---|---|---|
| Cannot run `docker compose` | Docker daemon is not running or Compose is unavailable | Check `docker info`, `docker compose version`, and Docker Desktop/service status. |
| Bind port 27017 failed / address already in use | Another MongoDB instance or program occupies the host port | Inspect listening processes and change mapping to `127.0.0.1:27018:27017` if appropriate. |
| Connection refused | Container not running or `mongod` not ready yet; wrong host/port | Check `docker compose ps`, `docker compose logs mongodb`, and the client's actual URI. |
| Authentication failed | Wrong username/password or `authSource` | Example root user uses `authSource=admin`; `app_user` uses `authSource=appdb`. Check actual users in the volume. |
| Changed `.env` password but old password still works | Volume already exists so root user init did not re-run | Change password via MongoDB admin command; do not delete volume if data is needed. |
| Java container cannot connect to `localhost:27017` | `localhost` resolves to the Java container itself | Use hostname `mongodb:27017` inside the same Compose network. |
| Host client cannot resolve hostname `mongodb` | Compose service names primarily resolve inside the Docker network | Use `localhost` with the published host port when the client runs on the host. |
| New database not visible after `use` | No document/collection has been created yet | Run `insertOne` or `updateOne` with `upsert`, then run `show dbs`. |
| Data appears lost after changing directory/project | Docker Compose creates volumes scoped to the new project name | Check `docker volume ls` and the `name` setting; avoid accidentally creating a separate volume. |
| Container runs, but transactional queries fail | Standalone MongoDB does not support features requiring a replica set | Configure a replica set when the workload truly requires transactions or change streams. |

When investigating, rely on actual logs and state before deleting containers or volumes:

~~~bash
docker compose ps
docker compose logs --tail 100 mongodb
docker volume ls
~~~

Credentials inside URIs, `.env`, or `docker compose config` can be sensitive secrets; redact passwords and tokens before sharing logs or configs for troubleshooting.

## 10. Self-Verification Exercise

Complete the following steps in order:

1. Start MongoDB using `compose.yaml` and confirm the container is running with a named volume.
2. Log in to `mongosh` with the root user; create database `appdb` and a document with `_id` set to `volume-test-001`.
3. Run `docker compose down` followed by `docker compose up -d`; query again to verify the document still exists.
4. Create `app_user` with only `readWrite` on `appdb`; use `app_user` to read the document back.
5. Change the host port to `27018`; connect from the host via `localhost:27018` and explain why `mongodb:27017` inside the Compose network remains valid.
6. Configure `MONGODB_URI` for a Java/Spring Boot application; verify a successful data read or `ping` through the driver.

**Completion criteria:** you can explain accurately where the data files live, why `down` followed by `up` does not erase data, when `authSource` is `admin` versus `appdb`, and why the URI for Java running on the host differs from Java running inside a container.

## 11. Principles to Carry into Production Projects

Docker Compose is ideal for learning environments, local integration testing, and bug reproduction. When bringing an application to an environment holding critical data, also design backup and restore, secret management, network access controls, health monitoring, upgrade strategies, and high availability according to real requirements.

Three core principles run throughout this lesson:

- **Decouple data from container lifecycles:** mount `/data/db` to an explicitly managed volume.
- **Address the server from the client's perspective:** host-based apps use `localhost` plus the published port; apps in the same Compose project use the service name `mongodb`.
- **Separate authentication from business data:** the root user lives in `admin`, application users hold narrower privileges in `appdb`, and connection strings declare `authSource` matching where the user was created.

Mastering these three points moves you from simply "getting MongoDB running in Docker" to a reproducible development environment connected to Java applications with controlled data lifecycles.
