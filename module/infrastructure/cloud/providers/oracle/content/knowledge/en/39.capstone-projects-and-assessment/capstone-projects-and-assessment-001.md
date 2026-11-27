# Three-Tier Spring Boot Project with Load Balancer and Private Database

## 1. Problem Statement and Expected Outcomes

In the **Capstone Projects and Assessment** chapter of the **CLOUD_PROVIDERS_ORACLE** module, you deploy a task management service on Oracle Cloud Infrastructure (OCI). Users call the API over HTTPS; a Load Balancer distributes requests across two instances running Spring Boot; data is stored in an Oracle database that only has a private endpoint.

The project ties together knowledge of tenancy, compartment, IAM, VCN, Compute, storage, Oracle database, monitoring, and automation into an operable system. An API endpoint returning HTTP 200 is not enough to finish: you must prove that network paths are restricted, data persists when an application instance is replaced, and the system continues serving after one backend stops operating.

Minimum deliverables include:

- An API to create and read tasks, with input validation and real persistence to Oracle Database.
- A public OCI Load Balancer accepting HTTPS on port 443.
- Two Compute instances without public IPs, running the same application build.
- An Autonomous Database with a private endpoint and no additional public access enabled.
- Administrative privileges separated from application runtime privileges; the database password retrieved from OCI Vault using instance principal.
- Evidence of functional testing, traffic distribution, network isolation, and single-backend failure testing.
- Procedures for redeployment, rollback, monitoring, and resource teardown accompanied by a cost estimate.

This is a lab API with access scoped to learners and evaluators. Use mock data only. The sample source code does not include end-user authentication; only open the listener to permitted CIDRs. If exposing the API to real users, add authentication, business authorization, and appropriate safeguards before making it broadly accessible.

## 2. Understanding "Three-Tier" Correctly in This Project

Two ways of layering appear side by side, each serving a different purpose:

| Perspective | Component | Responsibility |
| --- | --- | --- |
| Infrastructure: ingress | Public Load Balancer | Terminate client-side TLS, health-check backends, and distribute HTTP |
| Infrastructure: application processing | Two private Compute instances | Run Spring Boot, handle business logic, and connect to the database |
| Infrastructure: data | Private Autonomous Database | Store data, enforce SQL permissions, and provide recovery capabilities |
| Source code: Controller | REST controller | Receive HTTP, validate requests, and build responses |
| Source code: Service | Spring service | Coordinate business logic and define transaction boundaries |
| Source code: Repository | JDBC repository | Execute parameterized SQL and map results |

The Load Balancer does not serve a user interface or execute Java business logic. In this project, "three infrastructure tiers" describes the ingress–processing–data path of an API; it does not assume a separate web frontend.

The two backends must be **stateless** with respect to business data. Do not store tasks in an in-JVM `Map`, do not use local files as the primary data source, and do not rely on HTTP sessions on a single machine. Consecutive requests may land on two different backends.

## 3. Reference Architecture and Design Decisions

~~~mermaid
flowchart TB
    U["User / evaluator"]
    O["Operator"]
    subgraph OCI["OCI: compartment capstone-oci"]
        subgraph VCN["VCN 10.40.0.0/16"]
            subgraph EDGE["Public subnet 10.40.10.0/24"]
                LB["Public OCI Load Balancer\nHTTPS 443 → HTTP 8080"]
            end
            subgraph APP["Private app subnet 10.40.20.0/24"]
                A1["Compute app-1\nSpring Boot :8080"]
                A2["Compute app-2\nSpring Boot :8080"]
                BE["OCI Bastion private endpoint"]
            end
            subgraph DATA["Private data subnet 10.40.30.0/24"]
                DB["Autonomous Database private endpoint\nTCPS / mTLS :1522"]
            end
            NG["NAT Gateway"]
            SG["Service Gateway"]
        end
        VAULT["OCI Vault / Secret Management"]
        OBJ["Private Object Storage\nArtifacts and sanitized evidence"]
        OBS["Logging / Monitoring / Alarms"]
        B["OCI Bastion"]
    end
    U -->|"HTTPS 443"| LB
    LB -->|"HTTP 8080"| A1
    LB -->|"HTTP 8080"| A2
    A1 -->|"mTLS 1522"| DB
    A2 -->|"mTLS 1522"| DB
    O -.->|"Time-bound SSH session"| B
    B -.-> BE
    BE -.->|"SSH 22"| A1
    BE -.->|"SSH 22"| A2
    A1 -.->|"Outbound for package updates"| NG
    A2 -.->|"Outbound for package updates"| NG
    A1 -.->|"Supported OCI services"| SG
    A2 -.->|"Supported OCI services"| SG
    SG -.-> OBJ
    A1 -.->|"HTTPS + instance principal"| VAULT
    A2 -.->|"HTTPS + instance principal"| VAULT
    A1 -.-> OBS
    A2 -.-> OBS
    LB -.-> OBS
~~~

The diagram illustrates logical flows; not every arrow represents an independent route. Traffic to Vault, Logging, or OCI APIs must be verified against the endpoints and the list of services supported by Service Gateway in the region. If an endpoint requires Internet access, use NAT and appropriate egress rules.

Decisions in the reference design:

1. **Use an OCI Load Balancer capable of HTTP/HTTPS handling.** Do not substitute a Network Load Balancer directly when TLS termination and HTTP health checks are required as configured in this guide.
2. **Place both instances in the same regional app subnet.** Prefer two availability domains if the region, shape, and budget allow. In a single-availability-domain region, use two different fault domains.
3. **Select Autonomous Database with a transactional workload.** Configure a private endpoint and require mTLS. Current Oracle documentation may refer to this service as Autonomous AI Database; this project only uses transactional database features.
4. **Client → LB uses HTTPS; LB → app uses internal HTTP.** This is a trade-off for the lab. A private subnet does not encrypt traffic on your behalf. If end-to-end encryption is required, enable TLS on Spring Boot or a reverse proxy and configure SSL on the backend set, including certificate verification.
5. **App → database uses mTLS on port 1522.** The wallet and SQL account are two separate configuration factors; still provide the username/password for the database account as shown in the sample.
6. **Object Storage holds immutable releases.** Wallets, passwords, private keys, and logs containing sensitive data must not reside in the shared artifact bucket.

The Autonomous Database private endpoint is a direct destination within the configured network; the app → database path in this architecture does not need NAT or Service Gateway. See [Low-Latency Connections for Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/low-latency-connections.html).

## 4. Environment Preparation and Conventions

### 4.1. Prerequisites

You need:

- A tenancy with permission to create resources in the lab compartment.
- A region with sufficient quota and capacity for two instances, a Load Balancer, a VCN, and a private Autonomous Database.
- A development machine with JDK 21, Maven 3.6.3 or later, and Git.
- `curl`, `jq`, SSH, and a SQL client supporting Oracle connections.
- A DNS name you manage and a valid TLS certificate for the HTTPS listener.
- An administrative CIDR and a test client CIDR, typically your current public IP with `/32`.
- Permission to create budgets, or assistance from the tenancy administrator if budget management is centralized.

Do not assume Free Tier includes every required feature, shape, or private endpoint. Check available configurations, quotas, and pricing in your tenancy before provisioning.

Bash commands in this guide run on a Linux VM or suitable Bash environment. Paths such as `/opt/...` and `/etc/...` are paths on the project VMs. They are not instructions to create files inside the lesson directory.

### 4.2. Planned Resource Inventory

| Resource | Suggested Name | Key Requirement |
| --- | --- | --- |
| Compartment | `capstone-oci` | Holds project-specific resources |
| VCN | `vcn-capstone` | CIDR does not overlap with networks it will connect to |
| Public subnet | `subnet-edge` | Hosts the public LB |
| Private subnet | `subnet-app` | Disallow public IPs on Compute |
| Private subnet | `subnet-data` | Hosts the database private endpoint |
| Compute | `app-1`, `app-2` | Same image, same release, different fault domains |
| Load Balancer | `lb-taskapp` | Port 443 listener and HTTP 8080 backend set |
| Autonomous Database | `adb-taskapp` | Private endpoint, transactional workload |
| NSG | `nsg-lb`, `nsg-app`, `nsg-db` | Applied accurately to each resource |
| Vault secret | `taskapp-db-password` | Password of the SQL runtime user |
| Object Storage bucket | `taskapp-artifacts-<suffix>` | Private, stores release JARs |
| Budget, alarm, log group | Prefixed with `taskapp` | Has an owner and lab expiration date |

Apply tags such as `project=oci-taskapp`, `environment=lab`, `owner=<team>`, and `expires-on=<date>`. Distinguish display names from OCIDs; record required OCIDs in operational documentation without secrets.

## 5. VCN, Routing, and Network Security Rules Design

### 5.1. Subnets and Route Tables

| Subnet | Example CIDR | Required Route | Public IP |
| --- | --- | --- | --- |
| Edge | `10.40.10.0/24` | `0.0.0.0/0 → Internet Gateway` | Public LB |
| App | `10.40.20.0/24` | `0.0.0.0/0 → NAT Gateway`; selected service CIDRs → Service Gateway | Prohibited on app VNICs |
| Data | `10.40.30.0/24` | No default Internet route needed for the app → database flow | Do not expose a public endpoint |

Traffic between subnets in the same VCN follows default internal routing when no custom route design alters the path. Routes alone do not grant connectivity; network security rules at both ends and the OS firewall are still required.

Enable DNS hostnames and use the appropriate VCN resolver/DHCP configuration. Keep the database hostname obtained from the connection details. Do not replace the hostname with a hardcoded IP to "fix" DNS errors: doing so sacrifices flexibility and can break certificate verification.

NAT allows private instances to initiate outbound connections; it does not provide inbound access ports from the Internet. Service Gateway serves only supported OCI services, not general access to arbitrary websites.

### 5.2. Minimum NSG Matrix

The table below describes new TCP connections. When restricting egress, configure both source egress and destination ingress. Choose **stateful** rules for this lab.

| Source | Destination | Destination Port | Purpose |
| --- | --- | --- | --- |
| Permitted client CIDR | `nsg-lb` | TCP 443 | HTTPS requests |
| `nsg-lb` | `nsg-app` | TCP 8080 | Requests and health checks |
| Bastion endpoint private IP `/32` | `nsg-app` | TCP 22 | VM administration via Bastion |
| `nsg-app` | `nsg-db` | TCP 1522 | Database connection via mTLS |
| `nsg-app` | Required OCI endpoints | TCP 443 | Read secrets, artifacts, and send telemetry |
| `nsg-app` | Permitted package repositories via NAT | TCP 443 | Install or update software |

Add DNS, time synchronization, and agent connectivity according to the actual requirements of your image and services. If you allow broad outbound HTTPS from the app in the lab, document it as a design limitation and plan to narrow it. Never allow ingress on `8080`, `22`, or `1522` from `0.0.0.0/0`.

With stateful rules, return packets for tracked connections do not need a separate rule for ephemeral ports. Distinguish return traffic from a new connection initiated by the database side.

NSGs support referencing source/destination NSGs within the same VCN, which is more convenient than hardcoding two application IPs. See [Network Security Groups](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/networksecuritygroups.htm).

**Check Security Lists alongside NSGs.** Effective allow rules from Security Lists and NSGs are combined under the standard model. An overly permissive Security List can defeat the goal of narrowing an NSG. Remove redundant rules per your design while retaining required system rules. If the tenancy also enforces Zero Trust Packet Routing, that policy must be satisfied as well. See [Security Rules](https://docs.oracle.com/en-us/iaas/Content/Network/Concepts/securityrules.htm).

### 5.3. Administrative Access Configuration

Use OCI Bastion with a client CIDR allowlist and time-bound sessions. For Managed SSH, verify OpenSSH, Oracle Cloud Agent, and the Bastion plugin on the VM before creating a session. Allow port 22 from the Bastion private endpoint, without confusing it with your laptop's public IP.

This lab performs administrative SQL operations from an app VM over a controlled administrative session. If creating a direct tunnel to the database, preserve the exact hostname and TLS verification per your tool's instructions; do not disable certificate checks to work around a mismatch between `localhost` and the database hostname.

See [OCI Bastion Overview](https://docs.oracle.com/en-us/iaas/Content/Bastion/Concepts/bastionoverview.htm).

## 6. IAM Permissions and Secret Management

### 6.1. Separation of Identities

| Identity | Required Permissions | Scope Limitation |
| --- | --- | --- |
| Infrastructure builder | Create, modify, and delete required resources | Lab compartment and related dependencies |
| Operator | View status, logs, and execute deployment procedures | Project resources |
| Compute runtime | Read only the required secret and artifact | The two identified instances |
| SQL schema owner | Create tables and manage application objects | Application schema |
| SQL runtime user | `CREATE SESSION` and granted DML | Only required tables |

OCI IAM governs OCI API permissions. SQL login privileges and table permissions belong to a separate database authorization layer. Granting IAM permission to read a secret does not automatically grant `SELECT` privileges in Oracle Database.

An operator with root access on an app VM can still access process secrets. Therefore, SSH permissions, sudo rights, and permissions to create Bastion sessions are also part of the security boundary.

### 6.2. Illustrative Dynamic Group and Policy

Example dynamic group matching only the two instances:

~~~text
ANY {
  instance.id = '<APP_1_INSTANCE_OCID>',
  instance.id = '<APP_2_INSTANCE_OCID>'
}
~~~

Policy allowing dynamic group `dg-taskapp` to read one secret:

~~~text
Allow dynamic-group dg-taskapp to read secret-bundles in compartment capstone-oci where target.secret.id = '<DB_PASSWORD_SECRET_OCID>'
~~~

Substitute your compartment name, dynamic group, OCIDs, and identity domain naming syntax for your tenancy. When replacing an instance, update the matching rule; alternatively, use a tightly governed tagging strategy. Do not allow workloads to modify tags that would admit them into a privileged group.

This covers **runtime** permissions, not the full policy needed by the person provisioning the entire infrastructure. If runtime downloads artifacts from Object Storage or emits custom logs, grant access to the exact bucket or log group; do not solve it with `manage all-resources in tenancy`.

The pattern for scoping secret read access by OCID is described in [Creating Policies for Vault Secrets](https://docs.oracle.com/en-us/iaas/Content/APIGateway/Tasks/apigatewaycreatingpolicies.htm).

### 6.3. Secret Delivery Flow

1. The database administrator creates the SQL runtime user.
2. The runtime user's password is stored in Vault through an appropriate administrative channel.
3. The wallet for that exact database is transferred securely to `/opt/taskapp/wallet` on both VMs.
4. When the service starts, a script uses instance principal to fetch the `CURRENT` secret version.
5. The decoded password is written to a `0600` file under `/run/taskapp/secrets`.
6. Spring Boot loads this file via a configuration tree.

Do not place passwords, wallets, private keys, or secret contents into Git, cloud-init, public Terraform variables, report screenshots, or CI logs. Removing a secret in a newer commit does not erase it from history; if exposed, you must revoke or rotate the secret.

## 7. Creating the Private Database and Schema

### 7.1. Provisioning Autonomous Database

In the lab compartment:

1. Choose Autonomous Database with a transactional workload and an appropriate small capacity.
2. Select VCN `vcn-capstone`, private subnet `subnet-data`, and `nsg-db`.
3. Select private access only; do not enable the optional `Allow public access` setting.
4. Enable mTLS requirement for the reference setup.
5. Obtain the private hostname, service name, and wallet from the connection information of this exact database.
6. Verify that the app VMs resolve the hostname to the expected private IP and can connect on TCP 1522.

Oracle allows certain private endpoint configurations with optional public access enabled. Therefore, seeing the label "private endpoint" alone is not enough for acceptance; you must also verify the public access setting. Autonomous Database mTLS uses port 1522. See [Private Endpoints for Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/private-endpoints-autonomous.html) and [About Connecting to an Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-introduction.html).

### 7.2. Separating Owner and Runtime Users

Use the admin account to create two users. The following SQL example contains password placeholders; do not run it verbatim:

~~~sql
-- Run as the database admin account over a private connection.
CREATE USER TASK_OWNER IDENTIFIED BY "<OWNER_PASSWORD>";
GRANT CREATE SESSION, CREATE TABLE TO TASK_OWNER;
ALTER USER TASK_OWNER QUOTA 100M ON DATA;

CREATE USER TASK_APP IDENTIFIED BY "<RUNTIME_PASSWORD>";
GRANT CREATE SESSION TO TASK_APP;
~~~

`DATA` is the typical tablespace on Autonomous Database; confirm its name and quota in your environment. Supply passwords via your admin tool's secure prompt rather than storing populated scripts in a repository.

Connect as `TASK_OWNER` to create the table:

~~~sql
CREATE TABLE TASKS (
    ID          VARCHAR2(36 CHAR) PRIMARY KEY,
    TITLE       VARCHAR2(200 CHAR) NOT NULL,
    STATUS      VARCHAR2(16 CHAR) DEFAULT 'OPEN' NOT NULL,
    CREATED_AT  TIMESTAMP WITH TIME ZONE DEFAULT SYSTIMESTAMP NOT NULL,
    CONSTRAINT CK_TASKS_STATUS CHECK (STATUS IN ('OPEN', 'DONE'))
);

GRANT SELECT, INSERT ON TASKS TO TASK_APP;
~~~

The runtime user does not yet need `UPDATE` or `DELETE` because the sample API only creates and reads. When extending functionality, grant additional privileges through controlled changes.

The application uses the fully qualified name `TASK_OWNER.TASKS`. Do not run the application with an admin account, and do not enable automatic schema modification on every production startup.

### 7.3. Wallet and JDBC URL

Extract the wallet into a directory readable only by administrators and the service account. Example JDBC URL:

~~~text
jdbc:oracle:thin:@<PRIVATE_TNS_ALIAS>?TNS_ADMIN=/opt/taskapp/wallet
~~~

Replace `<PRIVATE_TNS_ALIAS>` with the actual private alias from `tnsnames.ora`, such as a `_tp` service suited to API workloads. Do not fabricate a hostname or service name from the database display name.

The sample uses an Oracle wallet, JDBC driver, and required companion JARs; keep server identity verification enabled. Handle the mTLS wallet as a revocable secret with a rotation plan. See [JDBC Thin Connections with a Wallet](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/connect-jdbc-thin-wallet.html).

## 8. Building the Three-Tier Spring Boot Application

### 8.1. API Contract

| Operation | Request | Result |
| --- | --- | --- |
| Create task | `POST /api/tasks` with `{"title":"Learn OCI"}` | `201 Created`, `Location`, and persisted payload |
| Read task | `GET /api/tasks/{uuid}` | `200 OK` if it exists |
| Non-existent ID | `GET` with a valid UUID not yet created | `404 Not Found` |
| Invalid input | Blank title, too long, or malformed UUID | `400 Bad Request` |
| Readiness | `GET /actuator/health/readiness` | `200` when app and database are ready |
| Liveness | `GET /actuator/health/liveness` | Reflects application liveness state |

Business responses include the `X-App-Instance` header to observe which backend served the request. This header is for lab visibility; it can be removed or obfuscated in production systems.

### 8.2. Project Structure

~~~text
taskapp/
  pom.xml
  src/main/java/vn/learning/ocicapstone/
    TaskApplication.java
    Task.java
    CreateTaskRequest.java
    TaskRepository.java
    TaskService.java
    TaskController.java
  src/main/resources/
    application.yml
~~~

The classes below belong to package `vn.learning.ocicapstone`. Filenames must match the public class or record names.

### 8.3. Maven and Dependencies

This example pins Spring Boot 3.5.16 and Java 21 to demonstrate a reproducible configuration. When executing the project, choose a supported patch version per your team's policy, lock versions, and preserve build outputs. Do not use `LATEST` or version ranges for releases.

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>vn.learning</groupId>
    <artifactId>taskapp</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>com.oracle.database.jdbc</groupId>
            <artifactId>ojdbc11-production</artifactId>
            <type>pom</type>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `ojdbc11-production` artifact is a POM that pulls in the JDBC driver and companion libraries; `type=pom` is intentional. The Oracle version is governed by Spring Boot's dependency management in this example. Inspect the dependency tree when upgrading versions to avoid pairing incompatible driver and wallet libraries.

See [Spring Boot 3.5 Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html) and [Oracle JDBC Maven Central Guide](https://www.oracle.com/database/technologies/maven-central-guide.html). Spring JDBC still uses HikariCP with the configuration below; having UCP in dependencies does not mean the application is using UCP.

### 8.4. Entry Point and Records

`TaskApplication.java`:

~~~java
package vn.learning.ocicapstone;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TaskApplication {
    public static void main(String[] args) {
        SpringApplication.run(TaskApplication.class, args);
    }
}
~~~

`Task.java`:

~~~java
package vn.learning.ocicapstone;

import java.util.UUID;

public record Task(UUID id, String title, String status) {
}
~~~

`CreateTaskRequest.java`:

~~~java
package vn.learning.ocicapstone;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateTaskRequest(
        @NotBlank @Size(max = 200) String title
) {
}
~~~

### 8.5. Repository: Parameterized SQL

`TaskRepository.java`:

~~~java
package vn.learning.ocicapstone;

import java.util.Optional;
import java.util.UUID;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class TaskRepository {
    private final JdbcTemplate jdbc;

    public TaskRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public void insert(Task task) {
        jdbc.update("""
                INSERT INTO TASK_OWNER.TASKS (ID, TITLE, STATUS)
                VALUES (?, ?, ?)
                """, task.id().toString(), task.title(), task.status());
    }

    public Optional<Task> findById(UUID id) {
        return jdbc.query("""
                SELECT ID, TITLE, STATUS
                FROM TASK_OWNER.TASKS
                WHERE ID = ?
                """,
                (rs, rowNum) -> new Task(
                        UUID.fromString(rs.getString("ID")),
                        rs.getString("TITLE"),
                        rs.getString("STATUS")),
                id.toString())
                .stream()
                .findFirst();
    }
}
~~~

Use bind parameters for input values. Never concatenate title or ID into SQL strings. Generating UUIDs in the service layer avoids depending on database-specific generated-key mechanisms.

### 8.6. Service: Transactions and Business Logic

`TaskService.java`:

~~~java
package vn.learning.ocicapstone;

import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class TaskService {
    private final TaskRepository repository;

    public TaskService(TaskRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Task create(String title) {
        Task task = new Task(UUID.randomUUID(), title.strip(), "OPEN");
        repository.insert(task);
        return task;
    }

    @Transactional(readOnly = true)
    public Task get(UUID id) {
        return repository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(
                        HttpStatus.NOT_FOUND, "Task not found"));
    }
}
~~~

The transaction proxy completes the commit before the service call returns to the controller. If the commit fails, the API must not report creation as successful. With this creation API, retrying a POST may create duplicate business records; when extending, design idempotency keys and unique constraints rather than blindly retrying all errors.

### 8.7. Controller: HTTP and Instance Identification

`TaskController.java`:

~~~java
package vn.learning.ocicapstone;

import java.net.URI;
import java.util.UUID;
import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/tasks")
public class TaskController {
    private final TaskService service;
    private final String instanceId;

    public TaskController(
            TaskService service,
            @Value("${app.instance-id}") String instanceId) {
        this.service = service;
        this.instanceId = instanceId;
    }

    @PostMapping
    public ResponseEntity<Task> create(
            @Valid @RequestBody CreateTaskRequest request) {
        Task task = service.create(request.title());
        return ResponseEntity
                .created(URI.create("/api/tasks/" + task.id()))
                .header("X-App-Instance", instanceId)
                .body(task);
    }

    @GetMapping("/{id}")
    public ResponseEntity<Task> get(@PathVariable UUID id) {
        return ResponseEntity.ok()
                .header("X-App-Instance", instanceId)
                .body(service.get(id));
    }
}
~~~

The controller contains no SQL and the repository does not decide HTTP status codes. This layering makes it possible to change protocols or data access strategies without lumping every concern into one class.

### 8.8. Application Configuration

`src/main/resources/application.yml`:

~~~yaml
server:
  address: 0.0.0.0
  port: 8080
  shutdown: graceful
  error:
    include-message: never
    include-stacktrace: never

spring:
  application:
    name: taskapp
  config:
    import: "configtree:/run/taskapp/secrets/"
  lifecycle:
    timeout-per-shutdown-phase: 30s
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    driver-class-name: oracle.jdbc.OracleDriver
    hikari:
      maximum-pool-size: 5
      minimum-idle: 1
      connection-timeout: 3000
      validation-timeout: 1000
      data-source-properties:
        oracle.net.CONNECT_TIMEOUT: 3000
        oracle.jdbc.ReadTimeout: 5000
        oracle.net.ssl_server_dn_match: true
  jdbc:
    template:
      query-timeout: 3s
  sql:
    init:
      mode: never

management:
  endpoints:
    web:
      exposure:
        include: health
  endpoint:
    health:
      show-details: never
      probes:
        enabled: true
      group:
        liveness:
          include: livenessState
        readiness:
          include: readinessState,db

app:
  instance-id: ${APP_INSTANCE_ID}
~~~

The file `/run/taskapp/secrets/spring.datasource.password` supplies the password property via the configuration tree. Do not add `optional:` here: a missing secret directory is a deployment error that should halt startup.

Place `db` only in readiness. Liveness must not depend on the database to avoid a situation where a database outage causes every app instance to restart continuously. Including the database in readiness is an intentional decision here because every business API depends on the database. If the shared database fails, both backends may be taken out of rotation; a Load Balancer cannot heal a shared dependency failure.

The timeouts above bound different phases and do not sum into an exact response-time guarantee. Two instances can open up to roughly `2 × 5 = 10` connections from the two primary pools; during rolling updates with extra instances or admin tools, the total will be higher. Tune against database limits and measured load.

Health group, probe, and dependency selection behavior is explained in [Spring Boot Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html).

## 9. Building, Distributing the Artifact, and Running on Compute

### 9.1. Build Once

In the application repository you create for the project:

~~~bash
mvn clean verify
mvn dependency:tree
sha256sum target/taskapp-1.0.0.jar
~~~

`verify` only runs tests that actually exist; having the test dependency does not generate tests automatically. At a minimum, add tests for validation, creating/reading data on Oracle, and not-found cases. Do not rely on H2 results as sole proof for Oracle SQL.

Upload the JAR to private Object Storage at an immutable path, such as `releases/1.0.0/taskapp.jar`. Record the commit, JDK, dependency versions, and SHA-256. Both VMs must run artifacts with the identical checksum; do not build separately on each VM.

### 9.2. Preparing the VMs

On both VMs:

1. Install JDK 21 and the OCI CLI from a source appropriate for the image; verify the CLI runs under the service account.
2. Create the system user `taskapp` without interactive login.
3. Create the release, script, wallet, and configuration directories.
4. Transfer the wallet over a secure administrative channel, then restrict permissions.
5. Download the same JAR using an identity permitted to read the bucket, verify the checksum, and place it in the release directory.
6. Open the OS firewall for port 8080 from the LB subnet or actual LB source range; the NSG still allows only `nsg-lb`.
7. Keep SSH restricted to the authorized Bastion path.

Directory layout on the VM:

~~~text
/opt/taskapp/
  releases/1.0.0/taskapp.jar
  current -> releases/1.0.0
  bin/load-db-password.sh
  wallet/...
/etc/taskapp/taskapp.env
/etc/systemd/system/taskapp.service
/run/taskapp/secrets/spring.datasource.password
~~~

The service account may read the JAR and wallet, but must not modify scripts or artifacts. Release directories, symlinks, and scripts are owned and managed by root. For example, set wallet ownership to `root:taskapp`, directory permissions `0750`, and file permissions `0640`; runtime secrets in `/run` use `0600`. Do not bundle the wallet inside the JAR.

### 9.3. Environment File Without Passwords

`/etc/taskapp/taskapp.env` on `app-1`:

~~~ini
DB_URL="jdbc:oracle:thin:@<PRIVATE_TNS_ALIAS>?TNS_ADMIN=/opt/taskapp/wallet"
DB_USERNAME=TASK_APP
DB_PASSWORD_SECRET_OCID=<DB_PASSWORD_SECRET_OCID>
OCI_REGION=<REGION_IDENTIFIER>
APP_INSTANCE_ID=app-1
~~~

On `app-2`, change only `APP_INSTANCE_ID=app-2`. Replace placeholders with actual values before starting. This uses systemd `EnvironmentFile` syntax, not a YAML file or a shell script to `source`.

### 9.4. Script to Load the Password from Vault

`/opt/taskapp/bin/load-db-password.sh`:

~~~bash
#!/usr/bin/env bash
set -euo pipefail
umask 077

: "${DB_PASSWORD_SECRET_OCID:?Missing DB_PASSWORD_SECRET_OCID}"
: "${OCI_REGION:?Missing OCI_REGION}"

secret_dir=/run/taskapp/secrets
mkdir -p "$secret_dir"

temp_file=$(mktemp "$secret_dir/.db-password.XXXXXX")
trap 'rm -f "$temp_file"' EXIT

oci secrets secret-bundle get \
  --secret-id "$DB_PASSWORD_SECRET_OCID" \
  --stage CURRENT \
  --region "$OCI_REGION" \
  --auth instance_principal \
  --query 'data."secret-bundle-content".content' \
  --raw-output |
  base64 --decode > "$temp_file"

test -s "$temp_file"
chmod 600 "$temp_file"
mv -f "$temp_file" "$secret_dir/spring.datasource.password"
~~~

Do not enable `set -x`. The secret value must be the exact runtime password, without an extra trailing newline when entering the secret. The script fails if retrieval or decoding fails; the application will not fall back to a default value.

This command depends on IAM and an HTTPS path to the region's Secrets API. If denied, fix the policy or network; do not create an administrative API key and copy it onto the VM to bypass the error.

### 9.5. systemd Unit

`/etc/systemd/system/taskapp.service`:

~~~ini
[Unit]
Description=OCI Task API
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=taskapp
Group=taskapp
WorkingDirectory=/opt/taskapp
EnvironmentFile=/etc/taskapp/taskapp.env
RuntimeDirectory=taskapp
RuntimeDirectoryMode=0700
ExecStartPre=/bin/bash /opt/taskapp/bin/load-db-password.sh
ExecStart=/usr/bin/java -XX:MaxRAMPercentage=60 -jar /opt/taskapp/current/taskapp.jar
Restart=on-failure
RestartSec=5
TimeoutStopSec=45
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/run/taskapp
UMask=0077

[Install]
WantedBy=multi-user.target
~~~

Install the OCI CLI in a system path reachable by the unit, or use an absolute path in the script. These hardening flags assume the CLI, JDK, wallet, and artifacts reside outside home directories; adjust if your image has a different layout.

Enable and verify:

~~~bash
sudo systemctl daemon-reload
sudo systemctl enable --now taskapp
sudo systemctl status taskapp --no-pager
sudo journalctl -u taskapp -n 100 --no-pager
curl --fail http://127.0.0.1:8080/actuator/health/liveness
curl --fail http://127.0.0.1:8080/actuator/health/readiness
~~~

Readiness must reach `UP` before adding the backend to traffic rotation. If the JVM fails to start, inspect configuration and dependency errors before troubleshooting the Load Balancer.

## 10. Configuring the Load Balancer and HTTPS

### 10.1. Backend Set

Create backend set `bs-taskapp`:

| Attribute | Lab Value |
| --- | --- |
| Policy | Round Robin |
| Backend 1 | Actual private IP of `app-1`, port 8080 |
| Backend 2 | Actual private IP of `app-2`, port 8080 |
| Health check protocol | HTTP |
| Health check path | `/actuator/health/readiness` |
| Expected status | 200 |
| Interval | 10,000 ms |
| Timeout | 3,000 ms |
| Retries | 3 |
| Backend SSL | Disabled in the lab's internal HTTP setup |
| Session persistence | Disabled for this stateless API |

Do not use a TCP health check as proof that the database is ready. TCP only proves a connection can be opened to the port; HTTP readiness verifies the state published by the application.

When a backend returns an unexpected response or times out per the policy, the Load Balancer removes it from rotation and restores it upon recovery. The actual observed duration depends on the check cycle and failure progression; do not promise an exact multiple of three intervals. See [OCI Load Balancer Health Management](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/load_balancer_health_management.htm).

### 10.2. Listener and Certificate

1. Create an HTTPS listener on port 443 attached to a valid certificate and the backend set above.
2. Configure the proper certificate chain; keep the private key in an approved certificate management mechanism.
3. Create a DNS record pointing to the LB's frontend address.
4. Allow ingress only from the selected lab client CIDR.
5. Test using the hostname matching the certificate; do not validate acceptance with `curl -k`.
6. If adding a port 80 listener to redirect to HTTPS, explicitly declare network rules and test the redirect accordingly.

Health checks go directly from the LB to the backend; the client-facing listener certificate does not substitute for backend encryption or backend certificates. When enabling backend TLS, align the port, SSL settings, and health checks. See [Creating Load Balancers](https://docs.oracle.com/en-us/iaas/Content/Balance/Tasks/managingloadbalancer_topic-Creating_Load_Balancers.htm).

Expose only summary health details as configured in the sample. Never expose `env`, `configprops`, `heapdump`, or administrative endpoints containing sensitive information through the LB.

## 11. Infrastructure and Deployment Automation

### 11.1. IaC Scope

Manage at least the VCN, subnets, route tables, NSGs, Compute, and Load Balancer with Terraform or OCI Resource Manager. If the database, Vault, or certificates are managed separately, record reference OCIDs and the corresponding provisioning steps so others can reproduce the setup.

Inputs should include compartment OCID, region, CIDRs, image OCID, shape, CPU/RAM configuration, public SSH key, client CIDR, and release artifact. Do not place private SSH keys or application passwords in `tfvars`.

The following example is only a **snippet** managing the backend set of an existing LB and two existing instances, not a complete Terraform configuration for the entire architecture:

~~~hcl
variable "lb_id" {
  type = string
}

variable "app_private_ips" {
  type = map(string)
}

resource "oci_load_balancer_backend_set" "taskapp" {
  load_balancer_id = var.lb_id
  name             = "bs-taskapp"
  policy           = "ROUND_ROBIN"

  health_checker {
    protocol           = "HTTP"
    port               = 8080
    url_path           = "/actuator/health/readiness"
    return_code        = 200
    interval_ms        = 10000
    timeout_in_millis  = 3000
    retries            = 3
  }
}

resource "oci_load_balancer_backend" "taskapp" {
  for_each         = var.app_private_ips
  load_balancer_id = var.lb_id
  backendset_name  = oci_load_balancer_backend_set.taskapp.name
  ip_address       = each.value
  port             = 8080
  weight           = 1
}
~~~

An example value for `app_private_ips` is a map from `app-1` and `app-2` to their two actual private IPs. Pin provider versions and commit the lockfile in the project repository. Backend set attributes are documented in the [OCI Terraform provider](https://docs.oracle.com/en-us/iaas/tools/terraform-provider-oci/latest/docs/r/load_balancer_backend_set.html).

Before applying:

~~~bash
terraform fmt -check
terraform validate
terraform plan -out=lab.tfplan
terraform apply lab.tfplan
~~~

`init` must be run before the first run to install providers and initialize backend state. Protect both state and saved plans: marking values `sensitive` only masks certain outputs and does not guarantee removal from state. Pay particular attention to the database admin password if a provisioning resource writes it into state.

### 11.2. Deploying One Backend at a Time

Procedure for updating from release `1.0.0` to `1.0.1`:

1. Build and test once; record the new JAR, commit, and checksum.
2. Select `app-1`, set the backend to drain mode, and wait for in-flight requests to finish.
3. Point the `current` symlink to the new release using a controlled operation.
4. Restart the service; verify liveness, readiness, and one business read/write directly on the VM.
5. Disable drain, wait for the backend to become healthy, then test through the LB.
6. Repeat for `app-2`.
7. Confirm both backends are running the same release and checksum.

If the new release fails, keep that backend out of rotation, switch back to the previous artifact, and verify before re-enabling it. Schema migrations must remain compatible with both versions during a rolling update. Rolling back a JAR does not automatically undo a destructive migration.

Do not stop both instances simultaneously for routine deployments.

## 12. Outside-In Acceptance Testing

### 12.1. Creating and Reading Data Over HTTPS

From a client machine in an authorized CIDR:

~~~bash
BASE_URL='https://api.example.com'

curl --fail-with-body --silent --show-error \
  -D /tmp/task-create.headers \
  -o /tmp/task-create.json \
  -H 'Content-Type: application/json' \
  -d '{"title":"Complete OCI capstone"}' \
  "$BASE_URL/api/tasks"

cat /tmp/task-create.headers
cat /tmp/task-create.json

TASK_ID=$(jq -er '.id' /tmp/task-create.json)

curl --fail-with-body --silent --show-error -i \
  "$BASE_URL/api/tasks/$TASK_ID"
~~~

Replace the hostname with your DNS name. Acceptance requires POST to return `201`, include `Location`, a valid UUID, the expected title, and status `OPEN`; GET returns `200` with the same data. `curl --fail-with-body` works on curl versions supporting this option; if using an older tool, upgrade or check HTTP status codes separately.

Additional checks:

~~~bash
curl --silent --show-error -i \
  -H 'Content-Type: application/json' \
  -d '{"title":"   "}' \
  "$BASE_URL/api/tasks"

curl --silent --show-error -i \
  "$BASE_URL/api/tasks/not-a-uuid"

curl --silent --show-error -i \
  "$BASE_URL/api/tasks/00000000-0000-0000-0000-000000000000"
~~~

The first two requests must be rejected with `400`. The final request returns `404` if that record does not exist. Error response bodies do not need to match a specific Spring Boot version character for character.

### 12.2. Proving Both Backends Serve Traffic

~~~bash
for i in $(seq 1 30); do
  curl --fail --silent --show-error \
    --dump-header - \
    --output /dev/null \
    "$BASE_URL/api/tasks/$TASK_ID" |
    tr -d '\r' |
    awk 'tolower($1) == "x-app-instance:" { print $2 }'
done
~~~

Combine headers, backend status, and logs on both machines to demonstrate that both `app-1` and `app-2` handle requests. Strictly equal counts or exact request-by-request alternation are not required. Verify that every iteration actually returns `200`; a failed curl call must not count as a successful sample.

If only one backend appears, check health, drain/offline state, cookie persistence, and backend set configuration before increasing load.

### 12.3. Proving Shared and Durable Data

1. Create a task through the LB and save the UUID.
2. Over an administrative session, call GET directly on localhost of `app-1` and `app-2` with the same UUID.
3. Restart `app-1`, wait for readiness to recover, then GET again.
4. Take `app-1` out of traffic rotation and GET via the LB.
5. Query the database with an authorized account to cross-check the record.

Data must persist at every step. The header identifies the backend; the shared database explains why the application needs no file or memory synchronization between the two VMs.

### 12.4. Proving the Database Is Private

Collect both configuration evidence and test results:

| Check | Expected Result |
| --- | --- |
| Database network configuration | Private endpoint, no additional public access enabled |
| App VNIC | No public IP |
| DNS from app VM | Database hostname resolves to the expected private endpoint |
| New connection from app VM | TCP and SQL queries succeed |
| Direct connection from Internet, no VPN/tunnel | Cannot establish a session to the private endpoint |
| SQL runtime user creates a table | Denied due to missing DDL privileges |
| Compute outside dynamic group reads secret | Denied by IAM |

A timeout from an Internet test alone is not sufficient proof of a private database: the failure could be due to DNS or another cause. You must combine network configuration, routes, NSGs/Security Lists, and connectivity tests from authorized locations.

Do not include passwords in command-line arguments or SQL client screenshots as evidence.

## 13. Fault Injection and Availability Assessment

### 13.1. Stopping One App Instance

Before testing, confirm both backends are healthy and at least one task is stored. Run a loop of GET requests logging timestamps, HTTP status, and latency. On `app-1`:

~~~bash
sudo systemctl stop taskapp
~~~

Observe:

- While the LB detects the failure, some requests may fail.
- After the failed backend is removed, new requests are served by `app-2`.
- Previously created data remains readable.
- Alarms and logs are sufficient to identify the failing component.

Recover:

~~~bash
sudo systemctl start taskapp
~~~

Wait for readiness and backend status to recover, then verify both instances receive traffic again. Record the fault-injection timestamp, last error timestamp, stable service timestamp, and full recovery timestamp.

Set a lab target, such as resuming stable service within 90 seconds after losing one backend. This is a target to measure, not an OCI SLA. If missed, analyze timeouts, health checks, and remaining backend capacity.

### 13.2. Losing Database Connectivity

During a controlled test window, block new connections from one backend to the database or apply an invalid connection configuration on a drained backend. Record the prior configuration before changing it so you can restore accurately.

When testing via NSGs, inspect other allow rules and existing pooled connections. An already-established connection continuing to work does not prove new connections are permitted. Test opening a new connection within the prepared scope.

Expected outcomes:

- Readiness on the affected backend transitions to unhealthy or fails to become healthy.
- Liveness does not automatically fail merely because the database is temporarily unreachable.
- Wait times are bounded; requests do not hang indefinitely.
- Restoring the configuration returns the backend to readiness.

If both backends lose the shared database, the business service is no longer available even though both JVMs stay alive. Designing for database or region failures requires a dedicated HA/DR strategy, recovery objectives, and appropriate drills.

### 13.3. Architecture Limitations

Two instances in one fault domain do not provide the same fault isolation as two fault domains. Two fault domains in one availability domain are not equivalent to two availability domains. Nor do two app instances turn the database into a multi-region DR system.

For transactions committed before an app-only restart, the data remains in the database. That does not prove zero RPO for database loss or region loss. RPO and RTO must be tied to specific failure scenarios.

Database backups do not replace application releases or IaC code. Verify backup policies and restore capability; if practicing a restore to a separate database, account for temporary costs, private endpoints, access permissions, and updating connection configurations.

## 14. Monitoring and Troubleshooting

### 14.1. Minimum Signal Set

| Layer | Signals to Observe | Action on Anomaly |
| --- | --- | --- |
| LB | Healthy backends, 5xx errors, response time | Inspect backends and health checks |
| Compute | CPU, memory via agent if configured, disk space | Check JVM, logs, and load |
| Application | Error rate, latency, connection pool, restarts | Distinguish resource vs. dependency failure |
| Database | Sessions, load, connection errors, and storage | Cross-check pools, SQL, and DB configuration |
| Security | IAM actions, secret reads, Bastion sessions | Verify identities and authorized changes |
| Cost | Cost by compartment/tag and leftover resources | Right-size, stop, or tear down per plan |

Enable LB access/error logs as needed, custom logs for the application, and required metrics. `journalctl` does not automatically appear in OCI Logging: you must configure an agent or log-forwarding mechanism along with appropriate IAM logging permissions.

The sample exposes only health; if exporting Micrometer metrics is needed, add the dependency, endpoint, and a controlled collection path. Do not expose all of Actuator just to build a dashboard.

Create an alarm when the healthy backend count drops below two over an appropriate observation window; configure higher severity when it drops to zero. Add alarms for errors and latency aligned with lab targets. Retrieve actual metric names, namespaces, and dimensions from Metrics Explorer on the exact resources rather than guessing names.

Logs should include consistent timestamps, release, instance, and request IDs. Mask sensitive data; never log Authorization headers, secret contents, passwords, or full JDBC URLs if a URL contains credentials.

### 14.2. Isolating Issues Along the Path

| Symptom | Check First | Common Causes |
| --- | --- | --- |
| HTTPS handshake fails | DNS, certificate, listener 443, LB NSG | Wrong hostname, missing intermediate CA, client CIDR changed |
| LB reports no healthy backends | Health path, port, and service on VM | App not running, readiness failing, firewall blocking |
| TCP 8080 works but readiness fails | Application logs and DB connection | Wrong secret, wallet, alias, or SQL privileges |
| Cannot resolve DB hostname | Resolver/DHCP and private DNS | Wrong hostname or DNS configuration |
| Certificate error connecting to DB | Wallet, hostname, and driver | Wrong DB wallet/expired, incompatible libraries |
| SQL table access denied | User and schema grants | Missing `SELECT`/`INSERT` or wrong schema name |
| Oracle fails to resolve alias | `TNS_ADMIN` and `tnsnames.ora` | Wrong alias or service account lacks file read permission |
| Only one VM can read the secret | Dynamic group and principal | Matching rule missing instance or policy not yet active |
| DB overloaded after adding replicas | Total connection pools and SQL | Each replica multiplies connections, slow queries |
| Closed NSG but traffic still passes | Security Lists, other NSGs, old connections | Another allow rule remains active |

Start by checking on the VM: liveness → readiness → simple SQL → call via LB → HTTPS from client. Do not change multiple rules and timeouts at once; each change should have a hypothesis and a confirming measurement.

OCI also provides a guide on [Troubleshooting Load Balancer Health Checks](https://docs.oracle.com/en-us/iaas/Content/Balance/Reference/troubleshooting_health.htm).

## 15. Cost Control and Resource Teardown

### 15.1. Pre-Provisioning Estimate

Build a table using current prices for your chosen region, shape, database tier, and billing model:

| Category | Units to Check | Control Method |
| --- | --- | --- |
| Compute | CPU, RAM, and running hours | Start small; measure single-backend load capacity |
| Boot/Block Volume | Capacity, performance tier, backups | Limit capacity and retention |
| Load Balancer | Active hours, bandwidth shape | Choose min/max suited for the lab |
| Autonomous Database | Compute, storage, and scaling options | Pick needed sizing, check autoscaling |
| Object Storage | Capacity, requests, and retention | Retain only needed releases/evidence |
| Logging/Monitoring | Ingest, storage, and retention by service | Limit log volume and retention period |
| Networking & auxiliary services | Data transfer and service billing models | Review applicable rate cards |

Estimate total lab cost by summing each resource's cost over the expected duration plus storage, logging, and data transfer. Do not cite a flat figure without recording the date, region, and assumptions.

Create a budget on the compartment or project tag with alert thresholds such as 50%, 80%, and 100%. Budgets are soft limits and alerting mechanisms; by default they do not block resources or halt spending. See [OCI Budgets](https://docs.oracle.com/en-us/iaas/Content/Billing/Concepts/budgetsoverview.htm).

### 15.2. Dependency-Ordered Teardown

After saving required evidence and data:

1. Stop sending test requests and capture observed costs.
2. Remove listeners/LB and backends per IaC configuration.
3. Terminate Compute instances along with volumes, backups, or IPs no longer needed.
4. Terminate the database and clones/backups per your chosen data retention policy.
5. Clean up expired artifacts and logs; handle secrets and keys according to service lifecycle rules.
6. Delete networking components once dependent resources are released.
7. Re-check resources in the compartment and Cost Analysis after billing update lag.

If using `terraform destroy`, inspect the plan and confirm the scope is the lab before running. Resources created outside state, retained backups, and objects with retention policies may require separate handling. Stopping Compute instances does not mean all other components have stopped incurring charges.

## 16. Handover Package and Grading Rubric

### 16.1. Required Evidence

The project dossier includes:

- Architecture diagram, region, subnets, route tables, and NSG matrix.
- Explanation of the placement of the two app instances and remaining HA limitations.
- Application code, locked dependencies, commit, and artifact checksum.
- IaC or Resource Manager configuration, plus provisioning instructions for separately managed parts.
- Sanitized IAM policies, matching rules, and SQL grants.
- Valid/invalid API results, shared data verification, and backend fault-injection tests.
- Private database proof combining configuration and connectivity tests.
- Dashboard/alarm screenshots, sample logs, and troubleshooting runbook.
- Cost estimate, observed spend, and inventory of terminated or retained resources.

State which tests were executed, environment, timestamps, results, and limitations. Responses, commands, and targets in this guide are instructional examples; they are not proof that your environment has been successfully deployed.

### 16.2. 100-Point Rubric

| Category | Points | Criteria for Full Credit |
| --- | ---: | --- |
| Networking and private database | 20 | Correct routes, private app/DB, both allow and deny tests documented |
| IAM and secrets | 15 | Least-privilege runtime, uses instance principal, no leaked secrets |
| Application and data | 20 | Clear three tiers, validation, bind parameters, transactions, and durable data |
| Load Balancer and availability | 15 | Valid HTTPS, both backends serving, fault and recovery measured |
| Monitoring and operations | 10 | Signals, alarms, logs, and usable runbook present |
| Automation and release | 10 | Reproducible, immutable artifacts, clear rolling update and rollback |
| Cost and handover | 10 | Cost assumptions, budget, and resource teardown documented |
| **Total** | **100** | |

Mandatory gate conditions to pass the project:

- The database has no public access beyond the required design.
- Neither app instance has a public IP and both serve traffic through the LB.
- Previously created data remains readable when restarting or removing one app instance.
- HTTPS connections are verified with a valid certificate.
- Runtime does not use the database admin account.
- No passwords, wallets, or private keys appear in the repository or handover dossier.

A submission scoring high on features yet violating any of these conditions must remediate them before acceptance.

## 17. Signs You Have Mastered the Project

You can trace from an HTTPS request down to a specific SQL statement: which identity is used, which route forwards traffic, which rules permit the connection, where data is committed, and which signals indicate a failure. You can also replace an app instance with a new deployment, return it to the backend set, read prior data, and demonstrate that environment costs are being tracked.

The value of the capstone lies in being able to rebuild and verify those behaviors with your own configuration, source code, and measurements.
