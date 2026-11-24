# Preparing Message Brokers and Credentials for Testing Environments

## 1. Objectives and Scope

A Spring application using a message broker needs to know the connection address, protocol port, virtual host, username, and password. The broker must also be initialized properly, have a dedicated namespace for the testing environment, and grant appropriate permissions to the application.

A good testing configuration should meet these goals:

- Be able to start the broker reproducibly on a developer machine or in CI.
- Isolate the application's queues, exchanges, and bindings from other environments.
- Use a dedicated account for the application, with just enough permissions on the testing virtual host.
- Never write real passwords into Git, shared configuration files, logs, or screenshots.
- Let Spring Boot receive configuration via environment variables and profiles.
- Have health checks and smoke tests to catch connection errors, wrong passwords, or missing permissions early.
- Have a way to clean up test data without accidentally deleting data in a shared environment.

This lesson uses RabbitMQ as an example because Spring AMQP integrates directly with RabbitMQ. The principles regarding endpoints, identities, authorization, environment isolation, and secret management also apply to other brokers, even though configuration names and protocols will differ.

## 2. Information to Prepare

An AMQP connection to RabbitMQ typically requires the following information:

| Information | Example in testing environment | Meaning |
|---|---|---|
| Host | localhost | Machine name or DNS of the broker as seen by the application |
| Port | 5672 | Default unencrypted AMQP port |
| Username | spring_test | Dedicated account for the application |
| Password | Separately generated secret | Authentication secret for the account |
| Virtual host | /messaging-test | Namespace containing exchanges, queues, and bindings |
| TLS | Disabled on local loopback; enabled per test server policy | Encrypts the connection over the network |

Do not confuse the AMQP port with the management port:

- 5672 is the AMQP protocol port that Spring AMQP uses to send and receive messages.
- 15672 is the HTTP management UI of the RabbitMQ Management Plugin. Spring AMQP does not connect to this port.

A virtual host (vhost) is a logical namespace in RabbitMQ. A queue named orders in /messaging-test and a queue named orders in / are two separate resources. Using a dedicated vhost avoids naming collisions and limits permission scope.

In a testing environment, there should be a dedicated vhost such as /messaging-test and an application user such as spring_test. Do not use an administrator account to run listeners or send messages in the application.

## 3. Starting RabbitMQ with Docker Compose

Docker Compose ensures the entire team uses the same broker version, same ports, and same initialization method. Create a directory for the testing environment, then create a compose.yaml file:

~~~yaml
services:
  rabbitmq:
    image: rabbitmq:3.13-management
    container_name: spring-messaging-test-rabbitmq
    hostname: rabbitmq
    environment:
      RABBITMQ_DEFAULT_USER: ${RABBITMQ_BOOTSTRAP_USER:?Set RABBITMQ_BOOTSTRAP_USER}
      RABBITMQ_DEFAULT_PASS: ${RABBITMQ_BOOTSTRAP_PASSWORD:?Set RABBITMQ_BOOTSTRAP_PASSWORD}
      RABBITMQ_DEFAULT_VHOST: ${RABBITMQ_VHOST:-/messaging-test}
    ports:
      - "127.0.0.1:5672:5672"
      - "127.0.0.1:15672:15672"
    volumes:
      - rabbitmq_test_data:/var/lib/rabbitmq
    healthcheck:
      test: ["CMD", "rabbitmq-diagnostics", "-q", "ping"]
      interval: 10s
      timeout: 5s
      retries: 12
      start_period: 20s

volumes:
  rabbitmq_test_data:
~~~

The rabbitmq:3.13-management image includes RabbitMQ and the management UI. In CI or teams with strict reproducibility requirements, pin a tested patch version or image digest instead of letting tags change over time.

Ports are bound to 127.0.0.1, so the broker is only exposed on the loopback interface of the machine running Docker. This is suitable for a local broker. If the broker resides on a shared server, configure firewalls, TLS, DNS, and access controls according to that environment's infrastructure; do not expose the management UI to the Internet.

The rabbitmq_test_data volume preserves broker data across container restarts. This is convenient for development environments. For tests requiring a completely clean environment, use a separate ephemeral container per test run.

### 3.1. Creating a Local Secret File

Create a .env.example file to document the required variable names:

~~~dotenv
RABBITMQ_BOOTSTRAP_USER=local_admin
RABBITMQ_BOOTSTRAP_PASSWORD=replace-with-a-random-secret
RABBITMQ_VHOST=/messaging-test

RABBITMQ_USER=spring_test
RABBITMQ_PASSWORD=replace-with-another-random-secret
~~~

Copy it to .env on your personal machine and replace both password values with random secrets. You can generate secrets with openssl rand -base64 32 or your organization's password manager. Do not use the same password for the bootstrap account and the application account.

Add .env to .gitignore:

~~~gitignore
.env
.env.*
!.env.example
~~~

Check the existing .gitignore before adding rules to avoid overwriting existing exceptions. The .env.example file only contains placeholders, not usable passwords.

Docker Compose automatically reads .env to substitute variables in compose.yaml. However, that does not mean a Spring Boot process running directly on the host machine also automatically reads .env. The application must be supplied with its own environment variables via the terminal, IDE, CI secret store, or environment run configuration.

### 3.2. Starting and Checking the Container

From the directory containing compose.yaml and .env, run:

~~~bash
docker compose up -d rabbitmq
docker compose ps
~~~

Verify the broker responds:

~~~bash
docker exec spring-messaging-test-rabbitmq rabbitmq-diagnostics -q ping
~~~

A successful result indicates the RabbitMQ node is responding to diagnostic commands. You can inspect logs if startup fails:

~~~bash
docker compose logs --tail=100 rabbitmq
~~~

Open the management UI at http://localhost:15672. Log in with the bootstrap account declared in .env. This account is for configuring the broker; do not put it into the application's application-test.yaml.

## 4. Creating an Application Account and Granting Permissions

### 4.1. Separating the Bootstrap User from the Application User

RABBITMQ_DEFAULT_USER and RABBITMQ_DEFAULT_PASS create the bootstrap account when RabbitMQ initializes its data directory for the first time. This default account typically has administrator privileges. Use it only to create the initial vhost, users, and permissions.

Create a dedicated application account named spring_test. It can be created through the management UI:

1. Open the Admin tab, select Users, then select Add a user.
2. Enter username spring_test and the password taken from your local secret.
3. Leave user tags empty so the account has no management UI admin privileges.
4. Create the user, then open Virtual Hosts and select /messaging-test.
5. Grant permissions to spring_test on this vhost. For a local vhost dedicated to testing, you can use .* for configure, write, and read.
6. Confirm the bootstrap account can still administer the broker when needed.

Equivalent operations can be performed via CLI:

~~~bash
docker exec spring-messaging-test-rabbitmq rabbitmqctl add_user spring_test 'PASTE_APP_PASSWORD_HERE'
docker exec spring-messaging-test-rabbitmq rabbitmqctl set_permissions -p /messaging-test spring_test '.*' '.*' '.*'
~~~

Replace the placeholder with the application password value. The CLI command takes the password as an argument, so terminal history or process lists may expose the secret. When this risk must be avoided, create the user through the management UI or use your organization's secure secret-provisioning workflow.

The three expressions in set_permissions correspond to configure, write, and read permissions for resources in the vhost. .* allows the account to create and use queues/exchanges in that vhost. This is broad permission within an already isolated namespace, suitable for local environments. For shared environments, restrict queue and exchange names according to application naming conventions and grant only the permissions actually required.

### 4.2. Verifying Vhost, User, and Permissions

Verification commands:

~~~bash
docker exec spring-messaging-test-rabbitmq rabbitmqctl list_vhosts name
docker exec spring-messaging-test-rabbitmq rabbitmqctl list_users
docker exec spring-messaging-test-rabbitmq rabbitmqctl list_permissions -p /messaging-test
~~~

Confirm that:

- Vhost /messaging-test exists.
- User spring_test exists and has no administrator tag.
- The user has configure, write, and read permissions on the right vhost.
- The application does not need to log in with the bootstrap account.

Do not share outputs containing usernames or internal environment details publicly. Permission-listing commands do not display passwords, but deployment logs should still be treated as operational information.

## 5. Configuring Spring Boot by Profile

Isolate broker connection configuration into a testing profile. Create src/main/resources/application-test.yaml:

~~~yaml
spring:
  application:
    name: spring-messaging-sample
  rabbitmq:
    host: ${RABBITMQ_HOST:localhost}
    port: ${RABBITMQ_PORT:5672}
    username: ${RABBITMQ_USER}
    password: ${RABBITMQ_PASSWORD}
    virtual-host: ${RABBITMQ_VHOST:/messaging-test}
    connection-timeout: 5s
    requested-heartbeat: 30s
~~~

The RABBITMQ_USER and RABBITMQ_PASSWORD placeholders have no default values. If forgotten in configuration, the application will report missing variables rather than silently using a weak password or wrong account. host and port have convenient defaults for applications running on a developer machine.

Run the application with the test profile. In PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "test"
$env:RABBITMQ_HOST = "localhost"
$env:RABBITMQ_PORT = "5672"
$env:RABBITMQ_USER = "spring_test"
$env:RABBITMQ_PASSWORD = "set-the-local-secret"
$env:RABBITMQ_VHOST = "/messaging-test"
./mvnw spring-boot:run
~~~

In Bash:

~~~bash
export SPRING_PROFILES_ACTIVE=test
export RABBITMQ_HOST=localhost
export RABBITMQ_PORT=5672
export RABBITMQ_USER=spring_test
export RABBITMQ_PASSWORD='set-the-local-secret'
export RABBITMQ_VHOST=/messaging-test
./mvnw spring-boot:run
~~~

Replace the illustrative password value with the secret you created. In an IDE, configure the profile and environment variables in the Run Configuration. In CI, fetch username/password from the pipeline's secret store; do not write them into workflow YAML or command-line arguments logged in output.

### 5.1. Hostname Depends on Where the Application Runs

The broker address depends on the network namespace:

- Spring Boot running directly on the host machine: use localhost and the published port, e.g., 5672.
- Spring Boot running in another service of the same Docker Compose project: use the service hostname rabbitmq and container port 5672.
- Spring Boot running on a CI runner or another machine: use the DNS/IP visible to the runner, along with the accessible broker port.

localhost inside an application container points to the application container itself, not the RabbitMQ container. This is a common cause of Connection refused when moving an application from running on the host machine to running inside Docker.

If packaging the application into Compose as well, you can declare a dependency on health status:

~~~yaml
services:
  app:
    build: .
    environment:
      SPRING_PROFILES_ACTIVE: test
      RABBITMQ_HOST: rabbitmq
      RABBITMQ_PORT: 5672
      RABBITMQ_USER: ${RABBITMQ_USER}
      RABBITMQ_PASSWORD: ${RABBITMQ_PASSWORD}
      RABBITMQ_VHOST: ${RABBITMQ_VHOST:-/messaging-test}
    depends_on:
      rabbitmq:
        condition: service_healthy
~~~

This is an addition for the app service in the same Compose file that declares the rabbitmq service. depends_on with service_healthy waits for the broker's health check before starting the application. The application must still handle losing connection to the broker after startup.

## 6. Environment Isolation and Data Lifecycle Management

Use different configurations for local, integration tests, shared test, staging, and production:

| Environment | Broker | Credentials | Data |
|---|---|---|---|
| Local developer | Container on machine | Per-machine local secret | Can be kept in a local volume |
| Integration test | Ephemeral container or job-dedicated service | Ephemeral test credentials | Deleted after each run |
| Shared test | Centrally managed broker/vhost | Secret issued to team or pipeline | Has queue and message cleanup policies |
| Staging/production | Infrastructure-operated broker | Secret manager and rotation | Retention, backup, and monitoring per SLA |

Do not share a vhost between test and production. If multiple applications share one broker, issue a dedicated vhost to each application or group with clear data boundaries. If multiple CI branches run in parallel, use per-build vhosts or resource prefixes to prevent two jobs from deleting each other's queues or consuming each other's messages.

A volume with existing data retains previously created users, vhosts, and permissions. Changing RABBITMQ_DEFAULT_USER, RABBITMQ_DEFAULT_PASS, or RABBITMQ_DEFAULT_VHOST in .env does not automatically modify accounts already in the data directory. When you need to change users on a running broker, use management commands such as change_password, add_user, set_permissions, or the management UI.

For a fully reproducible local environment, docker compose down -v deletes the containers and volumes declared in the project, including messages and broker data. Only run this command when you are sure the volume belongs to a disposable testing environment. In shared test environments, do not arbitrarily delete volumes or reset the broker to fix a connection error.

## 7. Testing Connectivity from the Application

A healthy broker does not prove Spring Boot has authenticated successfully. You must test from the application's actual runtime to catch wrong hostnames, ports, users, passwords, vhosts, or permissions.

A simple smoke test can use RabbitTemplate to declare a temporary queue, send a message, and receive it back:

~~~java
package com.example.messaging;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@ActiveProfiles("test")
class RabbitMqConnectionTest {

    @Autowired
    private RabbitTemplate rabbitTemplate;

    @Test
    void applicationCanPublishAndReceive() {
        String queueName = "test.connectivity.queue";

        rabbitTemplate.execute(channel -> {
            channel.queueDeclare(
                queueName,
                true,
                false,
                false,
                null
            );
            return null;
        });

        try {
            rabbitTemplate.convertAndSend(queueName, "connection-ok");

            Object received = rabbitTemplate.receiveAndConvert(
                queueName,
                5_000
            );

            assertThat(received).isEqualTo("connection-ok");
        } finally {
            rabbitTemplate.execute(channel -> {
                channel.queueDelete(queueName);
                return null;
            });
        }
    }
}
~~~

The queue in the test is durable, non-exclusive, and non-auto-delete; each test explicitly deletes the queue in a finally block, even if assertions fail. `receiveAndConvert` uses the AMQP `basic.get` polling operation rather than registering a long-lived consumer, so it cannot rely on auto-delete for queue cleanup. RabbitTemplate uses the default exchange when sending with the queue name as the routing key.

Add spring-boot-starter-test in test scope if the project does not already have it. When running the smoke test with the test profile, supply the same connection environment variables as when running the application. This test verifies the basic path from Spring to the broker; it does not yet test retries, dead-lettering, concurrency, or recovery after a broker restart.

### 7.1. Using Testcontainers for a Dedicated Broker in Integration Tests

For CI or integration tests requiring isolation, Testcontainers can spin up RabbitMQ in an ephemeral container. Add the test dependency:

~~~xml
<dependency>
    <groupId>org.testcontainers</groupId>
    <artifactId>junit-jupiter</artifactId>
    <version>1.20.6</version>
    <scope>test</scope>
</dependency>
~~~

The example below uses GenericContainer, so no separate RabbitMQ module is required:

~~~java
package com.example.messaging;

import org.junit.jupiter.api.Test;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;

import static org.assertj.core.api.Assertions.assertThat;

@Testcontainers
@SpringBootTest
@ActiveProfiles("test")
class RabbitMqContainerTest {

    @Container
    static final GenericContainer<?> rabbit =
        new GenericContainer<>(
            DockerImageName.parse("rabbitmq:3.13-management")
        )
            .withExposedPorts(5672)
            .withEnv("RABBITMQ_DEFAULT_USER", "test_user")
            .withEnv("RABBITMQ_DEFAULT_PASS", "test_password")
            .withEnv("RABBITMQ_DEFAULT_VHOST", "/messaging-test");

    @DynamicPropertySource
    static void rabbitProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.rabbitmq.host", rabbit::getHost);
        registry.add(
            "spring.rabbitmq.port",
            () -> rabbit.getMappedPort(5672)
        );
        registry.add("spring.rabbitmq.username", () -> "test_user");
        registry.add("spring.rabbitmq.password", () -> "test_password");
        registry.add(
            "spring.rabbitmq.virtual-host",
            () -> "/messaging-test"
        );
    }

    @Autowired
    RabbitTemplate rabbitTemplate;

    @Test
    void canPublishAndReceiveFromTemporaryBroker() {
        String queueName = "test.container.queue";

        rabbitTemplate.execute(channel -> {
            channel.queueDeclare(
                queueName,
                false,
                false,
                true,
                null
            );
            return null;
        });

        try {
            rabbitTemplate.convertAndSend(queueName, "container-ok");

            Object received = rabbitTemplate.receiveAndConvert(
                queueName,
                5_000
            );

            assertThat(received).isEqualTo("container-ok");
        } finally {
            rabbitTemplate.execute(channel -> {
                channel.queueDelete(queueName);
                return null;
            });
        }
    }
}
~~~

Testcontainers requires a running Docker daemon. The test container uses dummy user/password values that only exist for the lifetime of the test container and are not shared secrets. DynamicPropertySource injects the host and randomly mapped port into the Spring context, avoiding reliance on port 5672 on CI machines. The test queue is explicitly deleted in `finally`; Testcontainers also stops and removes the container after the test.

Use the same RabbitMQ version in Testcontainers as in local/shared test environments if version-specific behavior needs to be reproduced. Do not rely on leftover data from previous runs; ephemeral containers give each test run a clean broker.

## 8. Enabling TLS and Connecting to a Shared Broker

Local loopback setups can usually use non-TLS AMQP because traffic never leaves the developer's machine. When connecting over a network to shared test or staging, follow the broker's TLS policy.

With a RabbitMQ TLS listener, Spring Boot supports SSL configuration via spring.rabbitmq.ssl properties. Example enabling SSL:

~~~yaml
spring:
  rabbitmq:
    ssl:
      enabled: true
~~~

The snippet above only enables client-side SSL; the broker must have a TLS listener and a suitable certificate. Real environments also need a trust store or certificate trust mechanism aligned with the infrastructure. Do not disable certificate verification as a "quick fix" for TLS errors. The TLS port is usually configured separately, so obtain the exact endpoint and port from the broker administrator.

For shared test environments:

- Obtain the hostname, port, vhost, and secret names from a team-approved configuration source.
- Do not create accounts on a shared broker yourself unless you have provisioning rights.
- Do not paste passwords into tickets, chats, commits, or CI logs.
- Request least-privilege permissions per vhost and resource name.
- Define how passwords are rotated and pipeline secrets are updated.
- Do not put sensitive payloads into messages just because the environment is called test.

## 9. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to check |
|---|---|---|
| Connection refused | Broker not running, wrong port, wrong hostname, or port not published | Check docker compose ps, health check, and endpoint from where the app runs |
| UnknownHostException | Using Compose service hostname from host machine or bad DNS | Host process uses localhost; containers on same network use rabbitmq |
| ACCESS_REFUSED on login | Wrong username/password or user not permitted to access vhost | Check user, vhost, and secrets loaded into the process |
| ACCESS_REFUSED on declare/publish/consume | Missing configure, write, or read permission | Run rabbitmqctl list_permissions -p /messaging-test |
| NOT_ALLOWED or vhost error | Vhost does not exist or vhost name mismatch | Check exact leading / and vhost name |
| Intermittent connection drops | Broker restarts, unstable network, or unsuitable heartbeat/timeout | Check broker logs, heartbeat, and connection timing |
| App works locally but fails in Docker | Using localhost inside the application container | Change host to the service name rabbitmq |
| Changed password but still rejected | Old volume retains old account or secret was not updated properly | Check users on the broker and environment variables of the process |
| Tests pass individually but fail in parallel | Tests share a queue or vhost and consume each other's messages | Use per-test queue/vhost names or separate containers |

When investigating, check in order: is the broker running, can the app reach the endpoint, does authentication succeed, does the vhost exist, does the user have permissions, and only then check queues/exchanges and topology. Do not fix issues by granting the administrator tag to the application user; that masks authorization issues and widens blast radius.

## 10. Securing Credentials

- Generate random, sufficiently long passwords that differ across the bootstrap user, application user, and each environment.
- Add .env to .gitignore; commit only .env.example with placeholders.
- Use the secret store of your CI/CD or deployment platform for shared test and production.
- Do not write passwords into source code, Dockerfiles, image layers, test reports, command logs, or exception messages.
- Do not use the bootstrap/admin account in Spring Boot configuration.
- Do not grant the administrator tag to consumer users.
- Restrict permissions on the vhost and restrict network access to the broker.
- Enable TLS when connecting over a network per infrastructure policy.
- Secret rotation requires updating the broker and secret store in sync; verify new connections before revoking old credentials if zero-downtime transition is needed.
- Delete or disable unused test users.

Docker Compose .env is convenient for local development but is not a secret manager. Anyone with file read access or Docker daemon access on the machine can inspect the container's environment variables. Therefore, do not use this storage method for production credentials or shared environments with strict access control requirements.

## 11. Cleaning Up the Testing Environment

Stop the broker while keeping the volume:

~~~bash
docker compose down
~~~

Starting up again later will reuse the existing data directory, vhosts, users, permissions, and remaining messages.

If a local broker needs to be completely reset, you can delete volumes:

~~~bash
docker compose down -v
~~~

The command with -v deletes the project's named volumes. All dynamically declared queues, exchanges, messages, and broker data in that volume may be lost. Use only in local or temporary test environments confirmed safe to destroy. Never run this command against a shared test or production broker.

## 12. Pre-Testing Checklist

- [ ] RabbitMQ version is pinned and compatible with the project's Spring AMQP version.
- [ ] Broker is running and health check passes.
- [ ] AMQP port and management port are properly distinguished.
- [ ] Dedicated vhost for the testing environment exists.
- [ ] Dedicated application user has been created without the administrator tag.
- [ ] User has required configure/write/read permissions on the right vhost.
- [ ] Passwords are randomly generated and stored outside Git.
- [ ] Spring Boot receives the right profile, host, port, username, password, and vhost.
- [ ] Hostname matches where the application runs: host machine or container.
- [ ] Publish/receive smoke test succeeds.
- [ ] CI fetches secrets from a secret store and does not print values to logs.
- [ ] Safe local data reset method and shared test management procedures are in place.
- [ ] TLS is enabled when connecting over a network as required by the environment.

## 13. Summary

A reliable message broker testing environment starts with explicit endpoints, a dedicated vhost, a least-privilege application account, and secrets managed outside source code. Docker Compose provides a reproducible local broker; Spring Boot profiles and environment variables switch configuration per runtime location; smoke tests or Testcontainers confirm the application can actually connect, authenticate, publish, and consume.

When switching environments, distinguish initial bootstrap configuration from data already persisted in volumes. Also distinguish the AMQP port from the management port, host-machine hostnames from Docker network hostnames, and administrative accounts from application accounts. Keeping these boundaries clear catches errors early and keeps the testing environment isolated, safe, and reproducible.