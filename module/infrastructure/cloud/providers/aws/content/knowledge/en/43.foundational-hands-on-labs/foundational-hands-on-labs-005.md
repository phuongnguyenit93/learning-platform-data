# Deploying Spring Boot with RDS and Secrets Manager

This hands-on lab builds a REST API with Spring Boot connecting to PostgreSQL on Amazon RDS. Database credentials are stored in AWS Secrets Manager and loaded into the Spring Environment at application startup. HikariCP manages the JDBC connection pool; IAM, VPC, security groups, and TLS protect the access path.

This lesson belongs to the **Foundational Hands-On Labs** chapter of the CLOUD_PROVIDERS_AWS module. The module explores the AWS ecosystem from Region/AZ, IAM, and VPC to compute, storage, databases, integration, and serverless; learners build skills in selecting services and designing and deploying applications that are secure, observable, resilient, and cost-controlled.

## Learning Objectives

Upon completing this lesson, you will be able to:

- Distinguish the responsibilities of Spring Boot, Amazon RDS, AWS Secrets Manager, IAM, and VPC.
- Create an RDS for PostgreSQL instance in private subnets and restrict connections with security groups.
- Create a dedicated database user for the application with least privilege.
- Store credentials following the standard JSON secret structure for RDS PostgreSQL.
- Integrate Spring Cloud AWS Secrets Manager using Spring Boot Config Data import.
- Use an IAM role/default credentials provider chain instead of embedding access keys in source code.
- Configure PostgreSQL JDBC, HikariCP, and TLS with certificate verification.
- Test the REST API, database connection, and secret retrieval.
- Understand rotation, its impact on connection pools, and the role of RDS Proxy.
- Diagnose IAM, DNS, networking, TLS, secret format, and database authentication errors.
- Clean up lab resources to avoid unnecessary costs.

## 1. Architecture and Data Flow

The sample application is a customer management REST API. The application runs inside the same VPC as RDS or connects to the VPC via a controlled private network path.

~~~mermaid
flowchart TB
    U[Client / REST API] --> APP[Spring Boot application]
    APP --> H[HikariCP / JDBC]
    H --> DB[(Amazon RDS PostgreSQL)]
    APP --> SM[AWS Secrets Manager]
    APP --> IAM[IAM workload role]
    IAM --> SM
    SM --> KMS[AWS KMS encryption]
    subgraph VPC[Application VPC]
      APP
      H
      DB
      EP[Secrets Manager VPC endpoint]
    end
    APP --> EP
    EP --> SM
~~~

**Startup flow:**

1. Spring Boot reads `application.yml`.
2. Spring Cloud AWS processes `spring.config.import` and calls Secrets Manager using AWS SDK for Java 2.x.
3. Secrets Manager returns `SecretString` as JSON.
4. Top-level keys in the JSON are added to the Spring Environment.
5. Spring Boot resolves `db.host`, `db.username`, and `db.password` to configure the DataSource.
6. HikariCP establishes connections to RDS PostgreSQL over TCP 5432 and TLS.
7. The controller uses `JdbcTemplate` to execute SQL.

Secrets Manager is not on the path of every SQL statement. The secret is fetched when the application loads configuration or when reload is enabled; there is no need to call Secrets Manager per query.

## 2. Choosing Versions and Technologies

The example uses a compatible version set from the Spring ecosystem:

| Component | Version / Selection |
|---|---|
| Java | Java 21 LTS |
| Spring Boot | 4.0.10 |
| Spring Cloud AWS | 4.2.0 |
| AWS SDK | AWS SDK for Java 2.x managed by BOM |
| Database | Amazon RDS for PostgreSQL |
| JDBC driver | PostgreSQL JDBC |
| Connection pool | HikariCP (Spring Boot JDBC auto-configuration) |
| Secret | AWS Secrets Manager JSON SecretString |
| Example Region | ap-southeast-1 |

Spring Cloud AWS 4.x belongs to the Spring Boot 4.0.x compatibility line. Do not arbitrarily pair Spring Cloud AWS 3.x with Spring Boot 4.x or upgrade an individual AWS SDK module without checking the BOM. If your project uses Spring Boot 4.1.x or another patch line, verify the Spring Cloud AWS compatibility matrix before selecting versions. Use the Spring Cloud AWS BOM to lock AWSpring dependencies to a set tested together.

**Why PostgreSQL?**

- RDS for PostgreSQL supports JDBC and TLS.
- You can create a dedicated role for the application and grant permissions by schema/table.
- Secrets Manager has a standard JSON structure for PostgreSQL.
- Rotation Lambdas, RDS Proxy, and IAM authentication can be adopted in advanced steps.

## 3. Preparing the Account and Environment

You need:

- An AWS account with permissions to create RDS, Secrets Manager, IAM, VPC/security groups, and EC2 or an application runtime environment.
- AWS CLI v2 installed and configured.
- Java 21 and Maven or Maven Wrapper.
- `psql` or a PostgreSQL administration tool.
- Private network access to RDS, such as running the application inside the VPC, over VPN/Client VPN, or a development environment connected to the VPC.
- A consistent Region for RDS, the secret, IAM role, VPC endpoint, and application.

Set example variables in your terminal:

~~~bash
export AWS_REGION=ap-southeast-1
export DB_IDENTIFIER=spring-rds-lab
export SECRET_NAME=/lab/spring-rds/db
~~~

PowerShell:

~~~powershell
$env:AWS_REGION = "ap-southeast-1"
$env:AWS_PROFILE = "dev"
$DB_IDENTIFIER = "spring-rds-lab"
$SECRET_NAME = "/lab/spring-rds/db"
~~~

Sign in with IAM Identity Center if your organization uses SSO:

~~~bash
aws configure sso
aws sso login --profile dev
aws sts get-caller-identity --profile dev
export AWS_PROFILE=dev
~~~

PowerShell can set the corresponding profile via environment variable `AWS_PROFILE = dev` so subsequent AWS CLI commands use the right SSO session.

Do not create long-term access keys just to complete the lab when SSO or an IAM role can be used. Never commit access keys, database passwords, or secret JSON into Git.

## 4. Network Design Before Creating the Database

RDS should reside in private subnets and not accept direct Internet connections.

~~~mermaid
flowchart TB
    subgraph VPC["VPC 10.20.0.0/16"]
      subgraph PUB["Public subnet (only if app host/bastion needed)"]
        EC2[EC2 app host / SSM]
      end
      subgraph PRIV["Private database subnets"]
        RDS[(RDS PostgreSQL)]
      end
      EP[Interface endpoint: Secrets Manager]
    end
    EC2 -->|TCP 5432| RDS
    EC2 -->|HTTPS 443| EP
    EP --> SM[AWS Secrets Manager]
~~~

### 4.1. Security Groups

Create two separate security groups:

| Security group | Inbound | Outbound |
|---|---|---|
| sg-spring-app | No inbound needed if managed via Systems Manager Session Manager | TCP 5432 to sg-rds; HTTPS 443 to endpoint or AWS service |
| sg-rds-postgres | TCP 5432, source is sg-spring-app | Per VPC default requirements |

Do not configure PostgreSQL inbound from `0.0.0.0/0`. Do not use your personal machine's public IP as a long-term database access pattern. Referencing one security group from another keeps policies workload-based rather than tied to dynamic IPs.

### 4.2. Connecting to Secrets Manager from a Private Subnet

If the application sits in a private subnet without NAT/egress to public AWS endpoints, create an interface VPC endpoint for Secrets Manager:

- Service name: `com.amazonaws.ap-southeast-1.secretsmanager`.
- Enable Private DNS.
- Select subnets in the required Availability Zones.
- Attach an endpoint security group allowing TCP 443 from `sg-spring-app`.
- Optionally use an endpoint policy to restrict which secrets may be accessed.

If using an EC2 private subnet managed via Session Manager, ensure appropriate VPC endpoints or egress paths exist for Systems Manager. Do not confuse the Secrets Manager endpoint with the RDS endpoint: the application connects to the database via the RDS DNS endpoint through security groups.

### 4.3. Network Flow Matrix

| Source | Destination | Port | Purpose |
|---|---|---:|---|
| Spring Boot host | RDS endpoint | 5432/TCP | PostgreSQL JDBC |
| Spring Boot host | Secrets Manager endpoint | 443/TCP | Load secret |
| Rotation Lambda | RDS endpoint | 5432/TCP | Verify/update password |
| Rotation Lambda | Secrets Manager endpoint | 443/TCP | Read and update secret |
| Operator | EC2 app host | Via SSM | Administration without opening inbound SSH |



## 5. Creating RDS for PostgreSQL

In the AWS Console:

1. Open Amazon RDS and select the correct Region.
2. Choose Databases → Create database.
3. Choose Standard create to explicitly configure networking, backups, encryption, and availability.
4. Engine: PostgreSQL. Select an engine version supported by AWS in the Region.
5. DB instance identifier: `spring-rds-lab`.
6. Master username: for example `dbadmin`.
7. Choose Manage master credentials in AWS Secrets Manager so RDS manages the master password; do not hardcode passwords in source code or application config files.
8. Select the lab VPC, a DB subnet group containing private subnets in at least two Availability Zones, and Public access = No. The DB subnet group must satisfy RDS AZ requirements even if the lab uses Single-AZ.
9. Select security group `sg-rds-postgres`.
10. Enable storage encryption. Choose a KMS key per organizational policy.
11. For the lab, you can use Single-AZ and a small instance class fitting quota/budget. Production requires evaluating Multi-AZ, backup retention, maintenance windows, storage autoscaling, and failover.
12. Create the database and wait for the Available status.

Once RDS is ready, record the DB instance identifier, DNS endpoint, PostgreSQL port (default 5432), planned database name `appdb`, and the ARN of the RDS-managed master secret.

Do not use the master account in the application. The master secret is strictly for database administration and role bootstrapping.

### 5.1. Verify the Endpoint with the AWS CLI

~~~bash
aws rds describe-db-instances \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --region "$AWS_REGION" \
  --query "DBInstances[0].{Status:DBInstanceStatus,Endpoint:Endpoint.Address,Port:Endpoint.Port,Public:PubliclyAccessible,Encrypted:StorageEncrypted}" \
  --output table
~~~

Confirm `Public` is `False`, `Encrypted` is `True`, and status is `available`. If the endpoint is missing or the DB is still `creating`, wait before continuing.

## 6. Creating a Dedicated Database and User for the Application

Use the RDS-managed master secret to connect from an admin host inside the VPC or via a VPN/SSM tunnel. Do not open the database to the Internet just to run `psql`.

Create a dedicated role and database. The password below is a placeholder; replace it with a strong random password and store the exact same value in the secret in the next step. Do not commit real values to SQL files or Git.

~~~sql
-- Run using the RDS administrative account.
CREATE ROLE app_user LOGIN;
CREATE DATABASE appdb;
~~~

After creating the role, set its password using an interactive `psql` prompt or an approved admin tool; do not store passwords in SQL scripts or shell history. Record the value in a secure password manager to use the same value when creating the secret. Open a new `psql` connection to database `appdb`, then create the table and grant runtime permissions:

~~~sql
CREATE TABLE customers (
    id BIGSERIAL PRIMARY KEY,
    name VARCHAR(120) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

GRANT CONNECT ON DATABASE appdb TO app_user;
GRANT USAGE ON SCHEMA public TO app_user;

GRANT SELECT, INSERT, UPDATE, DELETE
ON TABLE customers
TO app_user;

GRANT USAGE, SELECT
ON SEQUENCE customers_id_seq
TO app_user;
~~~

Key points:

- `app_user` is solely the database login for the application.
- `app_user` is not the owner of the database or schema.
- The application has only CRUD privileges on table `customers` and required privileges on the sequence.
- Do not grant `SUPERUSER`, `CREATEDB`, `CREATEROLE`, or administrative privileges to the application.

If schema migrations are needed, use a dedicated migration role (Flyway/Liquibase) inside the deployment pipeline. Do not expand `app_user`'s runtime privileges just to let Hibernate auto-create tables. In this lab, the schema is created manually and the application performs only CRUD.

## 7. Storing Application Credentials in Secrets Manager

Create a secret for `app_user`, separate from the RDS-managed master secret. The JSON structure uses standard keys for PostgreSQL:

~~~json
{
  "engine": "postgres",
  "host": "spring-rds-lab.xxxxx.ap-southeast-1.rds.amazonaws.com",
  "username": "app_user",
  "password": "REPLACE_WITH_THE_SAME_RANDOM_PASSWORD",
  "dbname": "appdb",
  "port": 5432,
  "dbInstanceIdentifier": "spring-rds-lab"
}
~~~

Replace the endpoint and password with actual environment values. `dbInstanceIdentifier` helps Secrets Manager identify the database when configuring rotation via the Console. JSON keys are case-sensitive.

Save the content to a local file `db-secret.json` with restricted permissions. This file is only a temporary input vehicle; do not commit it to source control.

Create the secret:

~~~bash
aws secretsmanager create-secret \
  --name "$SECRET_NAME" \
  --description "Application credentials for Spring RDS lab" \
  --secret-string file://db-secret.json \
  --region "$AWS_REGION"
~~~

Do not pass the password directly in `--secret-string` arguments because shell history, process lists, and logs can expose the value. Once created successfully, delete the secret file from your workspace or store it in an organization-approved vault. On Windows, check file ACLs before deleting.

Verify metadata without printing `SecretString` to the terminal:

~~~bash
aws secretsmanager describe-secret \
  --secret-id "$SECRET_NAME" \
  --region "$AWS_REGION" \
  --query "{Name:Name,ARN:ARN,RotationEnabled:RotationEnabled,KmsKeyId:KmsKeyId}"
~~~

Secrets Manager encrypts secrets with KMS. If no customer managed key is specified, the service uses the appropriate AWS managed key. For secrets using a customer managed KMS key, the caller's policy must permit decrypting via Secrets Manager.

### 7.1. Versions and Staging Labels

Secrets Manager manages secret versions. Common staging labels:

- `AWSCURRENT`: the current active version; applications normally read this version.
- `AWSPREVIOUS`: the previous version, useful for controlled checks/rollbacks.
- `AWSPENDING`: the version currently undergoing rotation.

Do not arbitrarily reassign staging labels while a Lambda rotation is running. Only a completed rotation moves `AWSCURRENT` to the verified version.

## 8. IAM: Granting Permission to Read the Exact Secret

The application's workload role only needs to read the secret for `app_user`. Do not grant Secrets Manager administrative permissions to the application.

Example IAM policy (replace account ID and ARN/prefix for your environment):

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadSpringRdsApplicationSecret",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue"
      ],
      "Resource": "arn:aws:secretsmanager:ap-southeast-1:123456789012:secret:/lab/spring-rds/db-*"
    }
  ]
}
~~~

If the secret uses a customer managed KMS key, add `kms:Decrypt` scoped to that exact key, and optionally restrict with condition `kms:ViaService` for Secrets Manager in that Region. Never grant `kms:Decrypt` across all keys.

Attach the policy to:

- The EC2 instance profile if the app runs on EC2.
- The ECS task role if the app runs on ECS/Fargate (do not confuse with the task execution role).
- The EKS workload role via EKS Pod Identity or IRSA if the app runs on EKS.

On a developer workstation, use an IAM Identity Center profile and temporary credentials. AWS SDK for Java 2.x/Spring Cloud AWS uses the default credentials provider chain to locate credentials; there is no need to place access keys in `application.yml`.

### 8.1. Verifying Permissions via Policy Simulation or Logs

If the application throws `AccessDeniedException`, verify the IAM role, `secretsmanager:GetSecretValue` on the exact secret ARN, Region, KMS key policy, and VPC endpoint policy.

## 9. Creating the Spring Boot Project

You can generate the project via Spring Initializr or create an equivalent Maven project. Select Java 21, Spring Boot 4.0.10, Maven, Spring Web MVC, Spring JDBC, Spring Boot Actuator, PostgreSQL Driver, and the Spring Cloud AWS Secrets Manager starter.

Abbreviated `pom.xml` example:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.0.10</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>spring-rds-secrets-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>21</java.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>io.awspring.cloud</groupId>
                <artifactId>spring-cloud-aws-dependencies</artifactId>
                <version>4.2.0</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-starter-secrets-manager</artifactId>
        </dependency>
        <dependency>
            <groupId>org.postgresql</groupId>
            <artifactId>postgresql</artifactId>
            <scope>runtime</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
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

The Spring Cloud AWS BOM manages the versions of AWSpring modules. Do not pin a different version for the Secrets Manager starter without justification and compatibility testing.

Source structure:

~~~text
src/
  main/
    java/com/example/springrds/
      SpringRdsSecretsApplication.java
      CustomerController.java
    resources/
      application.yml
~~~

## 10. Configuring Spring Boot to Load Secrets from Secrets Manager

Create `src/main/resources/application.yml`:

~~~yaml
spring:
  application:
    name: spring-rds-secrets-lab
  config:
    import: "aws-secretsmanager:/lab/spring-rds/db?prefix=db."
  cloud:
    aws:
      region:
        static: ap-southeast-1
  datasource:
    url: "jdbc:postgresql://${db.host}:${db.port}/${db.dbname}?sslmode=verify-full&sslrootcert=${RDS_CA_BUNDLE_PATH}"
    username: "${db.username}"
    password: "${db.password}"
    driver-class-name: org.postgresql.Driver
    hikari:
      maximum-pool-size: 5
      minimum-idle: 1
      connection-timeout: 30000
      validation-timeout: 5000
      pool-name: SpringRdsPool
  sql:
    init:
      mode: never

management:
  endpoints:
    web:
      exposure:
        include: health,info
  endpoint:
    health:
      show-details: never
~~~

Explanation:

- `spring.config.import` instructs Spring Cloud AWS to load the secret before constructing beans needed for database configuration.
- `?prefix=db.` prepends a prefix to all JSON keys, preventing collisions with other application properties.
- `db.host`, `db.port`, `db.dbname`, `db.username`, and `db.password` resolve from the JSON secret.
- Do not use `optional:` for mandatory secrets so the application fails fast if credentials cannot be read.
- `spring.cloud.aws.region.static` must match the Region holding the secret.
- `RDS_CA_BUNDLE_PATH` is the path to the RDS CA bundle on the host running the app.
- `sslmode=verify-full` encrypts the connection and verifies both the certificate chain and hostname. Never downgrade to `disable` to work around connection errors.
- HikariCP manages the pool; pool size must fit `max_connections`, application replica count, and workload.
- Only expose `health` and `info`. Do not publicly expose actuator `env`, `configprops`, `beans`, or sensitive endpoints.

### 10.1. Downloading the RDS CA Bundle

Download the official CA bundle from AWS and place it in a protected path on the application host:

~~~bash
curl -o global-bundle.pem \
  https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
~~~

Example environment variable on Linux:

~~~bash
export RDS_CA_BUNDLE_PATH=/opt/certs/global-bundle.pem
~~~

PowerShell:

~~~powershell
$env:RDS_CA_BUNDLE_PATH = "C:\certs\global-bundle.pem"
~~~

Do not store the CA bundle inside a secret. It is a public CA certificate, though you need an update process when AWS rotates CAs. The path in the JDBC URL must exist and the Java process must have read permissions on the file.


## 11. Writing the Spring Boot Application and REST API

### 11.1. Application Entry Point

Create `SpringRdsSecretsApplication.java`:

~~~java
package com.example.springrds;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SpringRdsSecretsApplication {

    public static void main(String[] args) {
        SpringApplication.run(SpringRdsSecretsApplication.class, args);
    }
}
~~~

### 11.2. Controller Using JdbcTemplate

Create `CustomerController.java`:

~~~java
package com.example.springrds;

import java.time.OffsetDateTime;
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private static final RowMapper<Customer> CUSTOMER_MAPPER =
            (rs, rowNum) -> new Customer(
                    rs.getLong("id"),
                    rs.getString("name"),
                    rs.getString("email"),
                    rs.getObject("created_at", OffsetDateTime.class)
            );

    private final JdbcTemplate jdbcTemplate;

    public CustomerController(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @GetMapping
    public List<Customer> findAll() {
        return jdbcTemplate.query(
                """
                SELECT id, name, email, created_at
                FROM customers
                ORDER BY id
                """,
                CUSTOMER_MAPPER
        );
    }

    @PostMapping
    public Customer create(@RequestBody CreateCustomerRequest request) {
        Long id = jdbcTemplate.queryForObject(
                """
                INSERT INTO customers(name, email)
                VALUES (?, ?)
                RETURNING id
                """,
                Long.class,
                request.name(),
                request.email()
        );

        return jdbcTemplate.queryForObject(
                """
                SELECT id, name, email, created_at
                FROM customers
                WHERE id = ?
                """,
                CUSTOMER_MAPPER,
                id
        );
    }

    public record CreateCustomerRequest(String name, String email) {
    }

    public record Customer(
            long id,
            String name,
            String email,
            OffsetDateTime createdAt
    ) {
    }
}
~~~

Key points:

- `JdbcTemplate` obtains connections from the `DataSource` auto-configured by Spring Boot.
- Do not pass username/password per query.
- Prepared statements use `?` placeholders, avoiding SQL string concatenation from user input.
- Tables and access grants are prepared beforehand; the runtime user needs no schema administration privileges.


## 12. Running the Application and Testing Connectivity

### 12.1. Preparing the AWS Credentials Environment

If running the app from a development machine, sign in to SSO using a profile permitted to read the exact secret. Your workstation must also have a network route to private RDS (VPN/Client VPN/Direct Connect or a controlled tunnel). Without a private network path, run the app on EC2/ECS inside the VPC rather than enabling public access on RDS.

Linux/macOS:

~~~bash
export AWS_PROFILE=dev
export AWS_REGION=ap-southeast-1
export RDS_CA_BUNDLE_PATH=/opt/certs/global-bundle.pem
./mvnw spring-boot:run
~~~

Windows PowerShell:

~~~powershell
$env:AWS_PROFILE = "dev"
$env:AWS_REGION = "ap-southeast-1"
$env:RDS_CA_BUNDLE_PATH = "C:\certs\global-bundle.pem"
.\mvnw.cmd spring-boot:run
~~~

On EC2/ECS/EKS, prefer the IAM role attached to the workload. Do not set `AWS_ACCESS_KEY_ID` or `AWS_SECRET_ACCESS_KEY` in production environments.

### 12.2. Checking Health

~~~bash
curl http://localhost:8080/actuator/health
~~~

A successful result typically shows status `UP`. If the database health indicator is enabled, the `db` component must also report healthy. Do not expose health details to the Internet if the response might reveal internal structure.

### 12.3. Creating a Customer

~~~bash
curl -X POST http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -d '{"name":"Nguyen An","email":"an@example.com"}'
~~~

PowerShell:

~~~powershell
$body = @{
  name = "Nguyen An"
  email = "an@example.com"
} | ConvertTo-Json

Invoke-RestMethod -Method Post -Uri "http://localhost:8080/api/customers" -ContentType "application/json" -Body $body
~~~

### 12.4. Reading the Customer List

~~~bash
curl http://localhost:8080/api/customers
~~~

The response must include the newly created record. You can verify directly with `psql`:

~~~sql
SELECT id, name, email, created_at
FROM customers
ORDER BY id;
~~~

Verify the application connects with the right database role:

~~~sql
SELECT current_user, current_database();
~~~

The output must show `current_user = app_user`, `current_database = appdb`, not the master account.


## 13. Running the Application Inside AWS Instead of Connecting Directly from a Laptop

A more secure lab setup runs Spring Boot on EC2 inside the same VPC:

1. Launch an EC2 instance in an appropriate subnet and attach `sg-spring-app`.
2. Attach an instance profile with `AmazonSSMManagedInstanceCore` and the policy allowing reads on `/lab/spring-rds/db`.
3. Do not open inbound SSH if using Systems Manager Session Manager.
4. Ensure EC2 resolves the RDS endpoint and reaches TCP 5432 on `sg-rds-postgres`.
5. Ensure EC2 can call Secrets Manager via an interface endpoint or NAT/egress.
6. Deliver the JAR to EC2 via S3/private artifact store or a deployment pipeline.
7. Set `RDS_CA_BUNDLE_PATH` pointing to the CA bundle on EC2.
8. Run `java -jar` under a dedicated service account, send logs to CloudWatch Logs, and configure an appropriate restart policy.

On ECS/Fargate, use the task role to read the secret and the task security group to connect to RDS. On EKS, use EKS Pod Identity or IRSA. Do not attach Secrets Manager permissions to a shared node role when they can be scoped to a workload role.




## 14. Secret Loading Mechanism: Config Import vs. Direct SDK Calls

Spring Cloud AWS 4.2.0 provides two common approaches:

| Approach | When Suitable | Notes |
|---|---|---|
| Config Import via `spring.config.import` | Secret holds application configuration such as DB username/password | Loads the secret into the Spring Environment; straightforward for DataSource auto-configuration |
| Inject `SecretsManagerClient` | Secret is read per business logic or fetch timing must be controlled | Must manually manage JSON parsing, caching, refresh, and error handling |

Spring Cloud AWS auto-configures a `SecretsManagerClient` bean when the starter is included. You can inject the client to call the API imperatively, but avoid issuing a `GetSecretValue` call for every HTTP request or database query.

AWS SDK for Java 2.x recommends caching secrets client-side to reduce latency and API requests. If implementing custom caching, define TTL, cache-expiration behavior, retries, and rotation response behavior.

For this lab, Config Import is chosen because username/password are configuration required to construct the `DataSource`.

## 15. Rotation: Updating Passwords Without Exposing Secrets

Secrets Manager supports rotation for database secrets via Lambda functions or managed rotation depending on the secret type.

### 15.1. Enabling Rotation for the Application User

In the Secrets Manager Console:

1. Open secret `/lab/spring-rds/db`.
2. Choose Rotation configuration → Edit rotation.
3. Enable automatic rotation.
4. Choose an appropriate schedule, e.g., 30 days, and a rotation window matching operational needs. Rotation schedules run in UTC; align with maintenance windows and application deployment schedules.
5. Select the rotation Lambda template matching RDS PostgreSQL.
6. For database secrets, confirm fields `engine`, `host`, `username`, `password`, `dbname`, `port`, and `dbInstanceIdentifier` are accurate.
7. Ensure the rotation Lambda runs inside a VPC with a route to RDS.
8. The RDS security group must allow inbound 5432 from the rotation Lambda's security group.
9. The Lambda must reach Secrets Manager; use a VPC endpoint or appropriate egress path.
10. Trigger a test rotation and inspect status and the Lambda's CloudWatch Logs.

The rotation function executes the four protocol steps: `createSecret`, `setSecret`, `testSecret`, `finishSecret`. It promotes `AWSCURRENT` only after the new credentials are tested.

### 15.2. Single-User vs. Alternating-Users

| Strategy | How It Works | Trade-offs |
|---|---|---|
| Single user | Updates the password of the same database user and secret | Simple; brief window between DB password update and secret update |
| Alternating users | Creates a clone user and alternates credential updates between two users | Improves availability when apps fetch secrets mid-rotation; requires an administrative secret (`masterarn`) to clone the user |

With single-user rotation, existing open database connections are not closed solely because the password changed. However, new connections opened with the old password may be rejected during the transition window. Retries with backoff reduce transient errors.

Alternating-users rotation suits high-availability applications, though it requires keeping permissions identical across both users. Amazon RDS Proxy does not support the alternating-users strategy; verify this limitation before choosing a proxy architecture.

### 15.3. Checking Versions After Rotation

After rotation completes, inspect version metadata without printing secrets to logs:

~~~bash
aws secretsmanager list-secret-version-ids \
  --secret-id "$SECRET_NAME" \
  --region "$AWS_REGION" \
  --query "Versions[].{VersionId:VersionId,Stages:VersionStages,CreatedDate:CreatedDate}"
~~~

`AWSCURRENT` must point to the newly rotated and tested version. Do not automatically read `AWSPREVIOUS` as a production fallback without a clear validation and rollback process.

## 16. Refreshing the Spring DataSource After a Secret Changes

A common misconception: rotation in Secrets Manager does not automatically swap the username/password inside an already-constructed HikariCP `DataSource`.

- Config Import loads the secret once to build the Spring Environment and `DataSource`.
- Existing pooled connections may continue using active sessions.
- When the pool needs to open a new connection, if the `DataSource` still holds the old password, new connections will fail.
- You need a plan to refresh/restart the `DataSource` or use a proxy architecture to decouple credential lifecycles from the application.

Spring Cloud AWS supports `PropertySource` reload. Reload is disabled by default. There are two main strategies:

- `refresh`: refreshes `ConfigurationProperties` or `RefreshScope` beans per Spring Cloud Context mechanics. Do not assume arbitrary beans—especially Hikari `DataSource`—will automatically replace themselves.
- `restart_context`: gracefully restarts the entire Spring `ApplicationContext`, recreating beans and the `DataSource` with updated configuration.

To use reload, add dependencies such as Spring Boot Actuator, Spring Cloud Commons, and Spring Cloud Context per your version's documentation:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-commons</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-context</artifactId>
</dependency>
~~~

Illustrative configuration:

~~~yaml
spring:
  cloud:
    aws:
      secretsmanager:
        reload:
          strategy: restart_context
          period: 1m
~~~

`restart_context` requires enabling and exposing the Actuator `restart` endpoint per Spring Cloud AWS documentation. This endpoint has major impact on the application: never expose it publicly; if used, restrict it to a management network with strong authentication and auditing. Across multiple replicas, coordinate rolling restarts to avoid simultaneous service disruption.

Example Actuator configuration when intentionally choosing `restart_context`:

~~~yaml
management:
  endpoint:
    restart:
      enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,restart
~~~

Never expose `restart` on a public interface. Use a dedicated management port/network and security policies restricting which operators may invoke it.

For this lab, the simplest approach after a successful rotation is restarting the application:

~~~bash
# Stop the Spring Boot process via your process/service manager.
# Then restart the application so DataSource reads the new AWSCURRENT.
java -jar target/spring-rds-secrets-lab-0.0.1-SNAPSHOT.jar
~~~

In production, design the rotation and refresh workflow before enabling an automatic rotation schedule. Do not wait until a password changes to discover the connection pool is still holding stale credentials.

## 17. When Should You Use Amazon RDS Proxy?

RDS Proxy is a database proxy layer providing connection pooling and connection management between applications and RDS. The proxy can fetch database credentials from Secrets Manager via an IAM role attached to the proxy.

There are two key IAM models:

1. **Standard IAM authentication:** the application authenticates to the proxy using IAM; the proxy uses credentials in Secrets Manager to authenticate to the database. This keeps DB secrets at the proxy rather than letting applications read database passwords.
2. **End-to-end IAM authentication:** IAM is used from the application through the proxy to the database; this model does not require a Secrets Manager secret for DB credentials in the standard secret-based way.

When using RDS Proxy:

- The application connects to the proxy endpoint instead of the DB instance endpoint.
- In standard IAM authentication, the proxy needs an IAM role with `secretsmanager:GetSecretValue` on the corresponding secret. End-to-end IAM does not use a DB secret in this model.
- The application needs `rds-db:connect` permission for the proxy resource ID and database user when using IAM authentication.
- IAM connections to the proxy must use TLS.
- Verify engine family, Region, quotas, session pinning, and RDS Proxy compatibility constraints.
- Measure pool size, connection borrow latency, and actual connection counts before scaling load.

RDS Proxy is not mandatory for every small application. Consider it when running many application replicas, bursty connections, Lambda/serverless workloads, or when reducing connection pressure on the database. If the application reads passwords directly from Secrets Manager and connects directly to RDS, you must still handle rotation and `DataSource` refresh on the application side.

## 18. Production Security

### 18.1. Database and Network

- Place RDS in private subnets with `PubliclyAccessible = false`.
- Open TCP 5432 only from the application security group or proxy security group.
- Enable storage encryption with KMS.
- Configure backup retention aligned with RPO/RTO.
- Enable Multi-AZ when availability requirements demand it.
- Use TLS `verify-full` with an updated CA bundle.
- Never log endpoints/passwords or leak them in client exception messages.

### 18.2. Secrets Manager and IAM

- Use a dedicated secret per application/environment/database user.
- Scope IAM policies to allow `GetSecretValue` only on the required secret.
- Separate administrative/rotation roles from runtime roles.
- Never grant `secretsmanager:*` to the application.
- Never log `SecretString`, passwords, or credential objects.
- Use a customer managed KMS key if key policy control, auditing, or cross-account sharing is needed.
- Monitor CloudTrail for critical Secrets Manager API calls.
- Never use the master credential secret as a runtime credential.

### 18.3. Spring Boot and Actuator

- Never put secrets in `application.yml`, source code, container images, CI logs, or application logs.
- Never enable debug logging for Secrets Manager requests/responses in production if payloads could leak.
- Never publicly expose Actuator `env`, `configprops`, `heapdump`, `threaddump`, or `restart` endpoints.
- Enforce authentication and authorization on REST APIs.
- Validate requests, use prepared statements, and handle SQL errors without revealing internal schemas.
- Bound Hikari pool sizes; ensure total connections across all replicas do not exceed RDS capacity.
- Separate database migration roles from runtime roles.

## 19. Monitoring and Operations

Monitor across application, network, and database layers.

| Layer | Metrics / Logs | Purpose |
|---|---|---|
| Spring Boot | Request latency, HTTP 5xx, actuator health | Detect API errors |
| HikariCP | Active, idle, pending connections, acquisition timeout | Detect pool exhaustion |
| RDS PostgreSQL | CPU, FreeableMemory, DatabaseConnections, storage, latency | Assess DB health |
| Secrets Manager | AccessDenied, throttling, rotation status | Ensure secrets can be read/rotated |
| Rotation Lambda | Duration, errors, timeouts, logs of the four rotation steps | Detect rotation failures |
| VPC | Flow Logs, endpoint policies, DNS resolution | Investigate network errors |

Useful PostgreSQL diagnostic queries:

~~~sql
SELECT current_user, current_database(), inet_server_addr(), inet_server_port();

SELECT
    datname,
    usename,
    application_name,
    client_addr,
    state
FROM pg_stat_activity
WHERE usename = 'app_user';

SELECT
    a.usename,
    a.client_addr,
    s.ssl,
    s.version,
    s.cipher
FROM pg_stat_activity a
JOIN pg_stat_ssl s ON s.pid = a.pid
WHERE a.usename = 'app_user';
~~~

Avoid logging queries containing personal data or credentials unnecessarily. Configure CloudWatch alarms for CPU/storage/connection pressure, application error rates, and rotation failures. Maintain runbooks to quickly distinguish IAM, Secrets Manager, DNS, security group, TLS, and database issues.

## 20. Troubleshooting

| Symptom | Common Cause | Resolution |
|---|---|---|
| `ConfigDataLocationNotFoundException` | Wrong secret name/ARN or secret does not exist | Check `spring.config.import`, Region, and secret name |
| `AccessDeniedException` on startup | Role lacks `secretsmanager:GetSecretValue` | Check workload role, secret ARN, resource policy, and endpoint policy |
| `KMSAccessDeniedException` | Secret uses a customer managed key but role/key policy lacks access | Check `kms:Decrypt`, key policy, and `kms:ViaService` |
| `Unable to load credentials` | SSO not signed in, wrong profile, or workload lacks role | Check `aws sts get-caller-identity`, IAM role, and credential chain |
| `Unable to find region` | Missing `AWS_REGION`/region provider or misconfiguration | Set `spring.cloud.aws.region.static` and proper Region |
| Timeout to RDS | Wrong route, security group, NACL, or DNS | Check endpoint resolution, TCP 5432, source/destination SG, and VPC routes |
| Connection refused | Wrong port/endpoint or DB not yet Available | Check `describe-db-instances`, port 5432, and DB status |
| `password authentication failed` | Secret and DB role passwords mismatch or app holds old version | Check `AWSCURRENT`, DB user, and rotation status |
| `relation customers does not exist` | Schema not created or connected to wrong database | Check `current_database()` and execute DDL via migration/admin role |
| `permission denied for table` | App user missing grants | Grant proper `SELECT`/`INSERT`/`UPDATE`/`DELETE` and sequence privileges |
| `PKIX path building failed` | Missing CA bundle or invalid trust store | Download official RDS CA bundle, verify path and read permissions |
| `Hostname verification failed` | JDBC URL does not use exact RDS endpoint or certificate mismatch | Use the RDS-issued DNS endpoint and `sslmode=verify-full` |
| Hikari connection timeout | Pool exhausted or slow DB | Check active/pending connections, query latency, max pool size, and `max_connections` |
| Failures after rotation | DataSource/Hikari still holds old password | Controlled context reload/restart or adopt RDS Proxy |
| Rotation Lambda timeout | Lambda cannot reach DB/Secrets Manager | Check VPC, routes, Lambda SG, RDS SG, endpoints/NAT, and timeout |
| Rotation `testSecret` fails | DB user lacks minimal privileges or invalid secret JSON | Verify `engine`, `host`, `port`, `dbname`, `username`, and test query privileges |
| Secret unchanged after rotation | Rotation incomplete or Lambda errored | Check rotation status, CloudWatch Logs, and staging labels |


## 21. Extension Exercises

### Exercise A — Testing Least Privilege

1. Temporarily revoke `INSERT` privilege from `app_user`.
2. Call the `POST` API.
3. Observe the database error and application logs.
4. Re-grant the exact `INSERT` privilege.
5. Call the API again and confirm success.

Goal: understand the boundary between AWS IAM permissions and database user SQL privileges. IAM allowing secret reads does not mean the database role can manipulate tables.

### Exercise B — Rotation

1. Enable single-user rotation for the application secret.
2. Trigger an immediate rotation in the lab environment.
3. Verify the new version holds `AWSCURRENT`.
4. Test new connections.
5. Restart Spring Boot so the `DataSource` loads the new credentials.
6. Compare errors/latency before and after pool recreation.

Goal: observe the lifecycle of secrets, database passwords, and connection pools.

### Exercise C — Adding RDS Proxy

1. Create an RDS Proxy for PostgreSQL.
2. Attach the Secrets Manager secret and an IAM role to the proxy.
3. Configure IAM authentication for client connections.
4. Update the JDBC endpoint to point to the proxy.
5. Measure connection counts on RDS and latency as client concurrency grows.

Goal: understand proxy-layer pooling and decoupling database credentials from the application runtime.

### Exercise D — Testing Network Isolation

1. Confirm RDS is not public.
2. Attempt connecting from outside the VPC without a VPN/tunnel.
3. Confirm the connection is blocked.
4. Connect from the application host inside the VPC.
5. Inspect Flow Logs or security groups to explain the outcome.

Goal: demonstrate intentional network boundaries rather than relying solely on passwords.

## 22. Self-Check Questions

1. Why should the RDS master user not be used inside Spring Boot?
2. What problem does Secrets Manager solve that `application.yml` cannot?
3. What does `spring.config.import` do in the Spring Boot lifecycle?
4. Why should the JSON secret include `host`, `port`, `dbname`, `username`, `password`, and `engine`?
5. What problem does `?prefix=db.` prevent?
6. Why should mandatory secrets not be imported with `optional:` in production?
7. How does `secretsmanager:GetSecretValue` differ from SQL `SELECT` privilege?
8. Why is an ECS task IAM role different from the task execution role?
9. Why should RDS sit inside private subnets?
10. Where should the RDS security group accept inbound traffic from?
11. What problem does a Secrets Manager VPC interface endpoint solve?
12. Why use TLS `verify-full` instead of unencrypted connections?
13. How does HikariCP manage connections?
14. Why should you not set an arbitrarily large pool size?
15. When rotation changes a password, are already-open database sessions terminated immediately?
16. Why does an already-constructed `DataSource` not automatically pick up a new password just because the secret rotated?
17. How do single-user rotation and alternating-users rotation differ?
18. Why does alternating-users rotation often require an administrative secret?
19. What do `AWSCURRENT`, `AWSPREVIOUS`, and `AWSPENDING` mean?
20. Which connection/credential challenges does RDS Proxy help solve?
21. How does RDS Proxy's standard IAM authentication differ from end-to-end IAM?
22. Why should Actuator `env` or `restart` not be exposed publicly?
23. When `AccessDeniedException` occurs, which policies should be inspected?
24. How do you distinguish a network timeout from a database authentication failure?
25. Which resources should be deleted after completing the lab?

## 23. Production Readiness Checklist

- [ ] RDS is in private subnets and not publicly accessible.
- [ ] Database storage is encrypted and backup retention is properly configured.
- [ ] Security group permits TCP 5432 only from the app/proxy.
- [ ] Database runtime user has no administrative privileges.
- [ ] Secret has the right JSON structure and a valid `AWSCURRENT` version.
- [ ] Secret is encrypted with KMS per policy.
- [ ] Workload role has permission to read only the required secret.
- [ ] Application uses the default credentials provider chain or workload identity.
- [ ] No credentials appear in source code, images, CI logs, or application logs.
- [ ] JDBC uses TLS and verifies hostname/certificate.
- [ ] Hikari pool size is sized for replica count and DB capacity.
- [ ] Rotation Lambda has network paths to RDS and Secrets Manager.
- [ ] Tested rotation together with `DataSource` refresh behavior.
- [ ] Actuator exposes only necessary endpoints with access controls.
- [ ] CloudWatch metrics/alarms and CloudTrail auditing are configured.
- [ ] Retries/backoff and runbooks exist for rotation and DB failover.
- [ ] Evaluated RDS Proxy or IAM database authentication where appropriate.
- [ ] Tested backup restore and failover.
- [ ] Process exists for CA bundle updates and TLS validation.
- [ ] Cost budgets, tags, and lifecycles exist for lab/temporary resources.

## 24. Lab Resource Cleanup

This lab can incur charges for the RDS instance/storage, Secrets Manager secret, KMS, VPC endpoints/NAT, EC2, CloudWatch Logs, and rotation Lambda. When finished:

1. Stop the Spring Boot app and remove temporary artifacts if no longer needed.
2. Terminate the EC2 app host or temporary compute environment.
3. Delete RDS Proxy if created.
4. Delete the RDS DB instance according to your snapshot policy. Only use `--skip-final-snapshot` for disposable lab data.
5. Delete the rotation Lambda/role if created solely for the lab and no secrets reference it.
6. Delete the application secret with an appropriate recovery window; do not force-delete unless you understand the consequences.
7. Delete lab-specific VPC endpoints/security groups/roles once no dependent resources remain.
8. Delete `db-secret.json` and check `.gitignore`/Git history to ensure no passwords were committed.

Example deleting a secret with a recovery window:

~~~bash
aws secretsmanager delete-secret \
  --secret-id "$SECRET_NAME" \
  --recovery-window-in-days 7 \
  --region "$AWS_REGION"
~~~

Delete the database via CLI only after confirming no data needs to be retained:

~~~bash
aws rds delete-db-instance \
  --db-instance-identifier "$DB_IDENTIFIER" \
  --skip-final-snapshot \
  --delete-automated-backups \
  --region "$AWS_REGION"
~~~

Do not run deletion commands in production or shared accounts. If data must be retained, take a final snapshot and verify snapshot completion before deleting the DB.

## Conclusion

Connecting a Spring Boot application securely to Amazon RDS requires more than a JDBC URL and password. You must jointly design network boundaries, IAM identities, secret lifecycles, TLS, database privileges, and connection pooling.

The Spring Cloud AWS Secrets Manager starter injects JSON secrets into the Spring Environment via `spring.config.import`; AWSpring uses AWS SDK for Java 2.x and the default credentials provider chain to fetch the secret. Amazon RDS provides the database endpoint and TLS, while HikariCP manages reusable connections. IAM roles restrict the application to reading only the required secret, security groups constrain TCP 5432 flows, and Secrets Manager rotation updates credentials on schedule.

The most critical operational takeaway is that rotation does not automatically update an already-initialized Hikari `DataSource`. Design `DataSource` refresh/restart workflows or consider RDS Proxy/IAM authentication to reduce direct application password handling. Before production, test rotation, failover, TLS, IAM denials, restores, and costs end-to-end.

## Official References

- [Spring Cloud AWS 4.2.0 Reference Documentation](https://docs.awspring.io/spring-cloud-aws/docs/4.2.0/reference/html/index.html)
- [Spring Cloud AWS Secrets Manager integration](https://docs.awspring.io/spring-cloud-aws/docs/4.2.0/reference/html/index.html#secrets-manager-integration)
- [Spring Cloud AWS BOM and starter dependencies](https://docs.awspring.io/spring-cloud-aws/docs/4.2.0/reference/html/index.html#getting-started)
- [Spring Boot 4.0.10 documentation](https://docs.spring.io/spring-boot/4.0/)
- [Spring Boot externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [AWS SDK for Java 2.x Secrets Manager examples](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/java_secrets-manager_code_examples.html)
- [Create and connect to RDS for PostgreSQL](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/CHAP_GettingStarted.CreatingConnecting.PostgreSQL.html)
- [RDS PostgreSQL SSL/TLS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/PostgreSQL.Concepts.General.SSL.html)
- [RDS PostgreSQL certificate bundle](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.SSL.html)
- [JSON structure of Secrets Manager database secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/reference_secret_json_structure.html)
- [Connect to SQL databases using Secrets Manager credentials and JDBC](https://docs.aws.amazon.com/secretsmanager/latest/userguide/retrieving-secrets_jdbc.html)
- [Secrets Manager best practices](https://docs.aws.amazon.com/secretsmanager/latest/userguide/best-practices.html)
- [Single-user rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/tutorials_rotation-single.html)
- [Alternating-users rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/tutorials_rotation-alternating.html)
- [Rotation strategies](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotation-strategy.html)
- [Automatic rotation for RDS database secrets](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_turn-on-for-db.html)
- [Rotation schedules and UTC windows](https://docs.aws.amazon.com/secretsmanager/latest/userguide/rotate-secrets_schedule.html)
- [Troubleshoot Secrets Manager rotation](https://docs.aws.amazon.com/secretsmanager/latest/userguide/troubleshoot_rotation.html)
- [RDS Proxy concepts](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy.howitworks.html)
- [Create an RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-creating.html)
- [Connect to a database through RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-connecting.html)
- [IAM database authentication for RDS](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/UsingWithRDS.IAMDBAuth.html)
- [IAM authentication for RDS Proxy](https://docs.aws.amazon.com/AmazonRDS/latest/UserGuide/rds-proxy-iam-setup.html)
- [AWS Secrets Manager pricing](https://aws.amazon.com/secrets-manager/pricing/)
- [Amazon RDS for PostgreSQL pricing](https://aws.amazon.com/rds/postgresql/pricing/)
- [Amazon RDS Proxy pricing](https://aws.amazon.com/rds/proxy/pricing/)
- [AWS Pricing Calculator](https://calculator.aws/)
