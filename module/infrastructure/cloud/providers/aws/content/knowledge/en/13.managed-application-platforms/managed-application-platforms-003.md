# Deploying Java on Elastic Beanstalk

> **Chapter:** Managed Application Platforms  
> **Module:** CLOUD_PROVIDERS_AWS — exploring AWS infrastructure from Regions/Availability Zones (AZs), IAM, and VPCs to compute, storage, databases, integration, and serverless; practicing service selection, building secure applications, observability, recovery, and cost control.

## Learning Objectives

After this lesson, learners can:

1. Explain what **AWS Elastic Beanstalk** manages when deploying a Java application, and distinguish **application**, **application version**, **environment**, and **platform**.
2. Choose appropriately between the **Java SE platform** for Java/Spring Boot applications run as an executable JAR and the **Tomcat platform** for applications packaged as a WAR.
3. Build, test, and package a Spring Boot service with Maven, create a **Procfile**, and configure ports, health checks, and an Elastic Beanstalk-compatible source bundle.
4. Carry out the **EB CLI** deployment workflow in an authorized lab environment; understand the differences between creating an environment, deploying a version, updating configuration, and terminating an environment.
5. Design an architecture with an **ALB, EC2 Auto Scaling, VPC, IAM roles, CloudWatch**, an independent database, and HTTPS for production-grade operations.
6. Compare **deployment policies**, rolling/immutable/traffic splitting, blue/green, and rollback strategies.
7. Analyze application health, Java errors, 502/504 proxy issues, permissions, database dependencies, scaling limits, and total cost.
8. Use the AWS CLI in read-only mode to trace **environment health, events, application versions, configuration**, and related resources.

## 1. What Problem Does AWS Elastic Beanstalk Solve?

Suppose a development team has a Java Spring Boot service started with:

~~~bash
java -jar orders-api.jar
~~~

Running a JAR on a developer laptop is straightforward. To expose that service to real users, however, the team must also solve:

- Provisioning servers and installing a matching Java runtime.
- Configuring VPCs, subnets, Security Groups, routing, and a load balancer.
- Deploying releases and starting/restarting processes automatically.
- Collecting logs, monitoring health, and handling errors.
- Scaling capacity up and down with traffic.
- Managing HTTPS, IAM permissions, secrets, and database connectivity.
- Updating the runtime/OS and preparing rollbacks.

**AWS Elastic Beanstalk (EB)** is an application deployment and operations service following the **Platform as a Service (PaaS)** model. You supply **source code or a packaged artifact** and choose an AWS-supported **platform**; Elastic Beanstalk creates and coordinates the AWS resources required for the environment.

~~~mermaid
flowchart TB
    DEV["Developer / CI pipeline"] -->|"Source bundle / application version"| EB["Elastic Beanstalk"]
    EB --> CFN["AWS CloudFormation stack"]
    CFN --> EC2["EC2 instances / Auto Scaling"]
    CFN --> ALB["Elastic Load Balancer if configured"]
    CFN --> SG["Security Groups / VPC resources"]
    CFN --> MON["CloudWatch / enhanced health"]
    USER["Client"] -->|"HTTPS"| ALB
    ALB -->|"HTTP to Java process via proxy"| EC2
~~~

This is a logical diagram for a **load-balanced web environment**. A single-instance environment does not necessarily include an ALB. EB creates and manages resources, but **does not replace the team's responsibilities for application security, data, and budget**.

### 1.1. What Elastic Beanstalk Helps Automate

| Layer | What Elastic Beanstalk Assists With | What the Development Team Still Owns |
| --- | --- | --- |
| **Provisioning** | Orchestrates EC2, Auto Scaling, load balancers, and related resources per environment. | Choosing instance classes, network/HA configuration, quotas, and cost limits. |
| **Platform runtime** | Provides platform branches/Java runtimes and matching deployment mechanics. | Choosing supported versions, updating dependencies, and compatibility testing. |
| **Deployment** | Manages application versions, artifact distribution, and rollout mechanics. | Building/testing artifacts, migrations, rollbacks, and release governance. |
| **Scaling** | Configures EC2 Auto Scaling for load-balanced environments. | Load testing, selecting metrics/thresholds, and designing stateless apps. |
| **Health/monitoring** | Basic/enhanced health, events, and log integration as configured. | Building readiness endpoints, setting alarms, and investigating root causes. |
| **Security** | Creates/attaches configured roles/SGs and resources. | Least-privilege IAM, HTTPS, data encryption, secrets, and network isolation. |
| **Persistence** | Can integrate with AWS storage and database services. | Choosing durable data stores, backups, recovery, and data ownership. |

### 1.2. Beanstalk Is Not "Serverless" in the Sense of Having No EC2

Elastic Beanstalk **does not turn every workload into Lambda or Fargate**. In a typical Java SE/Tomcat web environment, the application still runs on **EC2 instances** owned by the environment; EB manages the infrastructure orchestration, while EC2, load balancer, and related resource charges are still billed by the underlying services.

If you want to run containers without managing instances using the ECS Fargate model, evaluate **Amazon ECS/Fargate**, **AWS App Runner**, or another suitable option. EB offers a Docker platform, though this lesson focuses on Java SE/Tomcat.

## 2. Components to Distinguish

### 2.1. Application

An **Application** is the logical boundary grouping **application versions** and **environments** for a single product or system.

For example, an application named **orders-api** includes:

- Environment **orders-dev**.
- Environment **orders-staging**.
- Environment **orders-prod**.

Each environment has its own configuration, URL, resource set, and currently running version. The same application version can be deployed across multiple environments for staged testing.

### 2.2. Application Version

An **Application version** represents a deployable release: a source bundle or artifact referencing an S3 object, together with a **VersionLabel**.

Example:

~~~text
Application: orders-api
VersionLabel: orders-api-1.4.2-build138
Source bundle: s3://managed-artifacts-bucket/orders-api/1.4.2.zip
~~~

This path is illustrative; EB can manage artifact buckets using service-defined names and workflows. A **VersionLabel** distinguishes builds, though it does not guarantee the artifact inside was well-tested or free of secrets.

### 2.3. Environment

An **Environment** is a running deployment of the application, consisting of resources such as EC2 instances, an Auto Scaling group, an ELB, and service settings.

Distinguish:

- **Web server environment:** receives HTTP/HTTPS requests, optionally behind a load balancer.
- **Worker environment:** processes asynchronous tasks with Amazon SQS integration supported by the platform/worker tier; do not assume a worker environment automatically shares the same public HTTP path as the web tier.

This lesson deploys a Java API on a **web server environment**. If the Java application is a batch worker, choose the appropriate tier and message-handling path.

### 2.4. Platform Branch and Platform Version

An environment must select a **platform** for Java, such as Java SE on Amazon Linux 2023 or Tomcat on an AWS-supported Amazon Linux release.

- **Platform branch** describes the technology/runtime/OS lineage, e.g., Java on a specific Amazon Linux generation.
- **Platform version** is a concrete release of that branch.
- **Supported branches** and supported Corretto runtimes evolve over time; check the official platform catalog in your target Region.
- Do not pin an outdated OS/runtime version simply because a tutorial used it.

**AWS provides the runtime/platform**, yet you must still test application dependencies, Spring Boot/Java compatibility, database drivers, and application behavior during platform upgrades.

## 3. Choosing Java SE or Tomcat?

### 3.1. Two Common Deployment Paths

| Criterion | **Java SE platform** | **Tomcat platform** |
| --- | --- | --- |
| Application style | Standalone Java process, typically an **executable JAR**. | Servlet-container web application, typically a **WAR**. |
| Spring Boot | Very common with **embedded Tomcat/Jetty/Undertow** inside the JAR. | Spring Boot can be packaged as a WAR for external Tomcat when configured properly. |
| HTTP server | Started by the Java application itself. | Managed Tomcat provided by the platform receives and deploys the WAR. |
| Artifact | JAR and **Procfile** per deployment method. | WAR, or a source bundle containing WAR(s)/config per platform rules. |
| Startup control | Procfile, app arguments, environment variables, supported hooks. | Tomcat/server settings, servlet application, and platform configuration. |
| Best-fit apps | Spring Boot microservices, Dropwizard, standalone Java services. | Traditional Servlet/JSP apps, WARs needing platform-managed Tomcat. |
| Common pitfalls | Wrong port, wrong JAR path, missing startup command. | Servlet compatibility, WAR context path, Jakarta vs. javax, container version mismatch. |

**Recommendation for new Spring Boot REST APIs:** start with **Java SE + executable JAR**, because the build/run workflow is simpler and the app owns its embedded HTTP server. If an existing system is already packaged as a WAR and depends on external Tomcat, choose the matching **Tomcat platform**.

### 3.2. Choosing the Right Java Runtime

Suppose a project uses **Java 17** and **Spring Boot 3.x**:

- Choose an Elastic Beanstalk **Java SE platform** with a supported Amazon Corretto 17 runtime.
- Verify the project actually compiles bytecode compatible with Java 17.
- Do not pick a Java 11 runtime for an artifact compiled with Java 17.
- If using **Java 21** or another version, select the corresponding Corretto branch supported by AWS at deployment time.

Typical error from a runtime mismatch:

~~~text
java.lang.UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
~~~

This is a **Java bytecode/runtime compatibility** issue—it cannot be fixed by adding more EC2 instances or opening Security Groups.

### 3.3. Spring Boot 3 and Legacy Java Applications

Spring Boot 3.x uses **Jakarta EE namespaces** for many servlet APIs, whereas older Java apps may still rely on **javax.servlet**. When choosing a Tomcat platform for a WAR, verify the Tomcat major version and namespace compatibility; do not merely rename a JAR file extension to WAR.

Legacy Spring MVC/Servlet applications should have a **migration plan** and regression tests before upgrading platforms or runtimes in production.

## 4. Java Web Application Deployment Architecture

A common production design:

~~~mermaid
flowchart TB
    CLIENT["Client / Browser"] --> R53["Route 53: api.example.com"]
    R53 --> ALB["ALB HTTPS 443 / ACM"]
    subgraph VPC["Amazon VPC"]
      subgraph PUB["Public subnets — multi-AZ"]
        ALB
      end
      subgraph PRIVATE["Private app subnets — multi-AZ"]
        A1["EC2 Java app A"]
        A2["EC2 Java app B"]
      end
      subgraph DATA["Private database subnets"]
        DB[("Amazon RDS / database")]
      end
      ALB -->|"Appropriate HTTP/HTTPS, SG"| A1
      ALB -->|"Appropriate HTTP/HTTPS, SG"| A2
      A1 -->|"DB traffic"| DB
      A2 -->|"DB traffic"| DB
    end
    EB["Elastic Beanstalk environment"] -.->|"Manages deployment, ASG, config"| A1
    EB -.->|"Manages deployment, ASG, config"| A2
    CW["CloudWatch metrics and logs"] <-->|"Telemetry"| EB
~~~

The diagram shows the **ALB in public subnets**, app EC2s in private subnets, and an isolated database. This is a **reference design**; not every EB environment creates this topology automatically. You must configure the right VPC, subnets, ELB scheme, and Security Groups.

### 4.1. Single-Instance vs. Load-Balanced Environments

| Aspect | Single-Instance | Load-Balanced |
| --- | --- | --- |
| EC2 instances | Typically one instance. | One or more instances in an ASG. |
| Load balancer | Typically none. | Configured ELB, usually an ALB for HTTP/HTTPS. |
| Automatic instance scaling | Not like a load-balanced topology. | Can configure load-based Auto Scaling. |
| Availability on EC2 failure | Downtime during replacement/recovery. | Can stay up if healthy targets remain across AZs. |
| Cost | Often lower in labs due to no ELB. | Adds ELB and multiple EC2 costs, potentially higher. |
| Use case | Dev, testing, load-limited labs. | Staging/production requiring HA and variable load. |

**Single-instance is not the default production HA setup.** Load-balanced does not guarantee HA either if ASG min is 1 or all instances sit in one AZ.

### 4.2. Reverse Proxy and Java Process Port

On modern Amazon Linux Java SE platforms, EB typically runs an **Nginx reverse proxy** in front of the Java app:

~~~mermaid
flowchart LR
    U["Client"] -->|"HTTPS :443"| ALB["ALB"]
    ALB -->|"HTTP :80"| NGINX["Nginx on EC2"]
    NGINX -->|"HTTP localhost :5000"| JVM["Spring Boot Java process"]
~~~

This is a **typical flow with default configuration**; ports, ALB-to-instance HTTPS, and Nginx settings can be customized depending on the platform.

- The ALB can terminate TLS with a certificate from **AWS Certificate Manager (ACM)**.
- Nginx receives traffic on the instance and reverse-proxies it to the Java process.
- The application must **listen on the port Nginx is configured to forward to**, commonly **5000** on the Java SE platform.
- If the app stays on its default **8080** while the proxy forwards to 5000, health checks can fail and clients receive **502 Bad Gateway**.
- Do not try to fix this by opening backend ports to the Internet when the real issue is a proxy/process port mismatch.

### 4.3. Application State Must Be Decoupled from EC2

Elastic Beanstalk EC2 instances can be **replaced during deployments, scaling, or platform updates**. Therefore:

- Do not treat **/tmp**, the instance filesystem, or local log files as the sole durable storage location.
- Use **S3** for uploaded images/files, **RDS/Aurora** for transactional data, and **ElastiCache** or a suitable store for sessions/caches when needed.
- Design the Java service to be **stateless**, or externalize session state to a shared store.
- Any background task with side effects must support idempotency/checkpointing in case instances are replaced.

## 5. Creating a Java Spring Boot Application to Deploy

Let's build a minimal REST API using:

- Java 17.
- Spring Boot 3.x.
- Maven.
- Spring Boot Actuator for a health endpoint.
- Executable JAR running on the Java SE platform.

### 5.1. Project Structure

~~~text
orders-api/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/orders/
│   │   │       ├── OrdersApplication.java
│   │   │       └── StatusController.java
│   │   └── resources/
│   │       └── application.properties
│   └── test/
│       └── java/
└── .gitignore
~~~

The **Procfile** will be placed **at the root of the deployment source bundle**, alongside the executable JAR—it does not necessarily have to reside inside the project's `src` directory.

### 5.2. Example Maven POM

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>orders-api</artifactId>
  <version>0.0.1-SNAPSHOT</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-actuator</artifactId>
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

**Note:** Spring Boot version **3.5.0** in this example is simply an illustrative released version; for real applications, choose a **currently supported patch release** and verify CVEs, dependencies, and runtime compatibility before deploying.

### 5.3. Java Source Code

**OrdersApplication.java**

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

**StatusController.java**

~~~java
package com.example.orders;

import java.time.Instant;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class StatusController {
    @GetMapping("/")
    public Map<String, String> home() {
        return Map.of(
            "service", "orders-api",
            "status", "ok"
        );
    }

    @GetMapping("/api/status")
    public Map<String, String> status() {
        return Map.of(
            "status", "ok",
            "at", Instant.now().toString()
        );
    }
}
~~~

**application.properties**

~~~properties
spring.application.name=orders-api

# Java SE/Nginx typically forwards to port 5000 by default.
# If a different port is required, adjust the proxy/platform accordingly.
server.port=5000

# Expose only the actuator endpoints that are genuinely needed.
management.endpoints.web.exposure.include=health,info
management.endpoint.health.show-details=never
~~~

Illustrative endpoints:

~~~text
GET /                 -> JSON with service name and status
GET /api/status       -> JSON status and timestamp
GET /actuator/health  -> health response for basic readiness
~~~

Do not let the health endpoint leak sensitive details such as database passwords, environment variables, private IPs, or stack traces. If readiness needs to check databases and downstream services, enforce timeouts so the health endpoint does not become a load amplifier or cause cascading failures.

### 5.4. Testing and Building Locally or in CI

~~~bash
# Use the Maven wrapper in the project directory; otherwise use mvn.
./mvnw --version

# Run tests and build the executable Spring Boot JAR.
./mvnw clean verify

# Inspect the built artifact.
ls -lh target/*.jar

# Verify locally on the configured port.
java -jar target/orders-api-0.0.1-SNAPSHOT.jar
~~~

In another terminal:

~~~bash
curl -i http://localhost:5000/
curl -i http://localhost:5000/actuator/health
~~~

Proceed to deployment only after the build and tests pass and the health endpoint returns the expected response. Never deploy a JAR built for a different Java version or an artifact incompatible with the production platform.

### 5.5. Why Does an Executable JAR Work Well with Java SE?

A Spring Boot executable JAR embeds its own HTTP server. Elastic Beanstalk Java SE simply **starts the Java process** per the Procfile, and the reverse proxy forwards traffic to the HTTP port the app listens on.

If a legacy application requires an external Tomcat (Servlet container) rather than an executable JAR, choose the Tomcat platform/WAR as described below—do not force a JAR Procfile onto a WAR.

## 6. Packaging the Source Bundle and Procfile

### 6.1. Procfile

On the Java SE platform for Amazon Linux 2/2023, a **Procfile** at the root of the source bundle declares the process to run.

~~~text
web: java -jar app.jar
~~~

- **web** is the process name used by the platform for web applications.
- **app.jar** is the artifact alongside the Procfile in the ZIP.
- Spring Boot is configured with **server.port=5000**, matching the default proxy route noted earlier.
- Never hard-code access keys or database passwords in the Procfile.

Minimal source bundle structure:

~~~text
orders-api-bundle/
├── app.jar
└── Procfile
~~~

### 6.2. Packaging the Artifact

Example steps in a local or CI environment (do not run these in an unauthorized production environment):

~~~bash
./mvnw clean verify

mkdir -p deploy
cp target/orders-api-0.0.1-SNAPSHOT.jar deploy/app.jar

# Create deploy/Procfile with a single line:
# web: java -jar app.jar

cd deploy
zip ../orders-api-eb.zip app.jar Procfile
cd ..
~~~

When inspecting the ZIP archive, **app.jar and Procfile must sit at the root of the ZIP**, not nested inside a `deploy/` or `orders-api-bundle/` subdirectory. This is a common mistake: an extra directory level causes Elastic Beanstalk not to find the Procfile or to fail finding `app.jar`.

**Do not package `target/`, `.git/`, IDE metadata, local secrets, or test config files containing credentials** into the source bundle unless needed.

### 6.3. Creating the Procfile on Linux/macOS

~~~bash
printf 'web: java -jar app.jar\n' > deploy/Procfile
~~~

This is an example command for a build environment, not an action executed by this lesson. On Windows, ensure proper UTF-8/ASCII plain text without saving it as **Procfile.txt**.

### 6.4. Can You Deploy Source Code Instead of a JAR?

Elastic Beanstalk Java SE can process certain source bundles/builds depending on the platform; however, **packaging a tested artifact in CI** generally produces more **reproducible** releases. Building on the instance requires managing the JDK/Maven/Gradle toolchain, startup time, and dependency repositories.

In a professional pipeline:

1. CI tests and builds the artifact.
2. The artifact is tagged with a checksum/version and stored in S3 or an artifact repository.
3. An Elastic Beanstalk application version is created from that artifact.
4. That exact version is deployed to staging and then production.
5. Rollbacks can revert to a previous version without rebuilding source code.

## 7. When to Deploy a Java WAR on the Tomcat Platform?

A traditional Java application often follows a Servlet/JSP or Spring MVC layout and packages as a **WAR**.

Example:

~~~text
legacy-web/
├── pom.xml
└── src/main/webapp/
    └── WEB-INF/
        └── web.xml
~~~

With the Tomcat platform, Elastic Beanstalk provides the corresponding Tomcat container to deploy the WAR. The WAR can be uploaded directly or placed in a source bundle according to platform rules.

### 7.1. Spring Boot WARs Require Different Configuration

If deploying Spring Boot onto an external Tomcat:

- Set Maven packaging to **war**.
- Mark the Tomcat starter dependency as **provided** to avoid conflicting embedded server initialization.
- Extend **SpringBootServletInitializer** and override **configure(...)**.
- Build the WAR and pick a Tomcat platform with a **matching major version and compatible Servlet API namespace**.
- If the app must serve at context root **/**, follow artifact naming rules such as **ROOT.war** per Tomcat platform documentation.

Example WAR bootstrap configuration class:

~~~java
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

public class ServletInitializer extends SpringBootServletInitializer {
    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder app) {
        return app.sources(OrdersApplication.class);
    }
}
~~~

This snippet illustrates the WAR bootstrap helper class; the project must have complete imports/package declarations, Maven packaging, and dependencies configured before building.

### 7.2. Do Not Mix Up Java SE and Tomcat Arbitrarily

**A Spring Boot executable JAR already embeds Tomcat** and usually does not need the Tomcat platform. Conversely, a WAR designed for external Tomcat may fail if you simply rename `.war` to `.jar`.

If you encounter errors such as:

~~~text
NoClassDefFoundError: javax/servlet/...
ClassNotFoundException: jakarta.servlet....
HTTP 404 at wrong context path
~~~

Check the **Tomcat version, Servlet namespace, packaging, context root, and dependencies** instead of increasing instance size or opening additional network ports.

## 8. Creating and Deploying an Environment with the EB CLI

The **EB CLI** is a command-line tool tailored to Elastic Beanstalk, distinct from the **AWS CLI** which manages AWS APIs broadly. It helps initialize local configuration, create environments, deploy, view logs, and manage operations.

**Cost warning:** Commands such as **eb create**, **eb deploy**, **eb setenv**, and **eb terminate** can modify resources and incur charges. The commands below are **illustrative instructions** not executed in this lesson. Run them only in an authorized account/lab after verifying configuration and budget.

### 8.1. Preparation

You need:

- An AWS account/role permitted to create Beanstalk applications/environments and the required infrastructure resources.
- **AWS CLI** and **EB CLI** installed and configured.
- Compatible Git/Maven/Java 17 tooling.
- Chosen Region, VPC/subnets/security, and valid quotas.
- **Elastic Beanstalk service role** and **EC2 instance profile** created/authorized as required—do not assume new accounts always have default roles pre-created.

~~~bash
aws sts get-caller-identity
aws configure get region
eb --version
java -version
~~~

**Never share output containing access keys or secret keys** in docs or tickets. Running **aws sts get-caller-identity** confirms the active account/role before deployment, preventing accidental creation in the wrong account.

### 8.2. Initializing the EB Project

Inside the working directory containing the source bundle or a project configured so the EB CLI picks the right artifact:

~~~bash
eb init
~~~

The interactive flow typically prompts you to:

1. Choose the **Region**.
2. Select or create an **Elastic Beanstalk application**, e.g., **orders-api**.
3. Choose a **Java SE platform/branch** with a compatible Amazon Corretto runtime.
4. Configure an SSH key pair if needed for operations and permitted by company policy.

Displayed platform branch/version names vary by Region and date; choose a currently AWS-supported version rather than copying branch names from outdated tutorials.

### 8.3. Creating a Dev Environment

~~~bash
eb create orders-dev
~~~

This command typically triggers creation of a CloudFormation stack, EC2 instances, Security Groups, Auto Scaling, and a load balancer depending on options. For cost-conscious labs, you can pick a **single-instance environment** via EB CLI/console options; for production, evaluate load-balanced/multi-AZ.

When creating the environment, verify:

- VPC/subnets and public/private placement.
- Instance type/size and platform version.
- Min/Max capacity for load-balanced environments.
- IAM service role and EC2 instance profile.
- Java app startup configuration and health endpoint.
- Tags, log retention, and budgets.

**Do not treat wizard defaults as production-safe defaults** without reviewing security and availability.

### 8.4. Deploying the Application

~~~bash
eb deploy orders-dev
~~~

Deployment behavior depends on how the **EB CLI selects artifacts** (source code, source bundle, build/ignore config). If you created **orders-api-eb.zip**, ensure the EB CLI actually uploads that ZIP—or use an ApplicationVersion/S3 pipeline—rather than assuming it automatically grabs the ZIP just because the file sits in the project folder.

Another option is uploading the source bundle via the **Elastic Beanstalk console**, or creating an application version via API/IaC. Either way, what matters most is that the **deployed artifact** has the proper `Procfile + app.jar` layout.

### 8.5. Verifying After Deployment

~~~bash
eb status orders-dev
eb health orders-dev
eb events orders-dev
eb logs orders-dev
eb open orders-dev
~~~

**eb open** opens the environment URL in a browser; **status/health/events/logs** are primarily observational. Depending on the environment, **eb health** requires enhanced health and corresponding permissions.

Verification checklist:

1. Environment reaches a stable healthy state.
2. **GET /** returns the expected status.
3. **GET /actuator/health** returns HTTP success.
4. No unexpected 502/504 responses or Java stack traces.
5. All ALB targets are healthy when using a load balancer.
6. Running application version and config match the intended release.
7. CloudWatch metrics/logs capture baseline telemetry.

### 8.6. Updating Environment Variables

Example for dev:

~~~bash
eb setenv SPRING_PROFILES_ACTIVE=dev
~~~

This command **modifies the environment** and may trigger a config update or restart deployment. Never pass **database passwords, access keys, or tokens** directly on the command line where they risk exposure in shell history, logs, terminal recordings, or CI output. Use Secrets Manager/SSM Parameter Store via platform-supported integrations and proper permissions.

### 8.7. Deleting the Lab Environment When Finished

~~~bash
# DANGEROUS: run only on a lab environment you are sure is no longer needed.
eb terminate orders-dev
~~~

**Terminate can delete many environment-managed resources.** If an RDS database was created coupled to the environment lifecycle, terminating can result in data loss depending on configuration and retention policies. Before deleting, verify whether any database is coupled to the environment lifecycle, take needed backups, and review ALB/EC2/EBS and cost-generating resources.

**Never run terminate in production as a "quick cleanup"** without a data retention plan, recovery capability, and approved authorization.

## 9. Managing Configuration with `.ebextensions` and `.platform`

A source bundle can contain more than the application JAR. Elastic Beanstalk supports platform-specific configuration mechanisms, including:

- **Environment configuration / option settings:** via console, EB CLI, API, IaC, or config files.
- **`.ebextensions`:** YAML/JSON `.config` files supplying option settings and platform-supported customizations.
- **`.platform/hooks`:** script hooks for Amazon Linux 2/2023 platforms, executed at supported deployment phases.
- **`.platform/nginx`:** reverse-proxy configuration extensions when needed, following platform layout rules.

Choose mechanisms matching your **platform version**. Do not copy legacy Amazon Linux 1 instructions to Amazon Linux 2/2023 without verifying compatibility.

### 9.1. Example `option_settings`

For a **load-balanced Java SE environment with an Application Load Balancer**, you can set an environment variable and health check path:

~~~yaml
option_settings:
  aws:elasticbeanstalk:application:environment:
    SPRING_PROFILES_ACTIVE: prod
  aws:elasticbeanstalk:environment:process:default:
    HealthCheckPath: /actuator/health
~~~

Save the file at:

~~~text
.ebextensions/01-application.config
~~~

**Important limitations:**

- The **aws:elasticbeanstalk:environment:process:default** namespace applies to supported **ALB process** configurations and may not apply to single-instance or other ELB setups.
- **SPRING_PROFILES_ACTIVE** here is not a secret.
- Configuring a health check in `.config` does not mean the ALB validates databases, migrations, or dependencies automatically. The **/actuator/health** endpoint must actually serve real requests.
- Environment settings from console/CLI/IaC can follow precedence/override rules over `.ebextensions`; intentionally standardize on a clear configuration source of truth.

### 9.2. Procfile vs. Buildfile and Platform Hooks

| Component | Purpose | When to Use |
| --- | --- | --- |
| **Procfile** | Defines the command to start the application process. | Java SE executable JAR. |
| **Buildfile** | Executes supported build/config steps before app startup per platform. | When preparing artifacts on the instance via supported mechanics. |
| **`.ebextensions/*.config`** | Option settings and feature-based environment configuration. | Environment variables, health paths, AWS options. |
| **`.platform/hooks/prebuild`** | Hook running before the build/deploy phase. | Environment prep if genuinely needed. |
| **`.platform/hooks/predeploy`** | Hook running prior to application deployment. | Pre-startup checks/setup. |
| **`.platform/hooks/postdeploy`** | Hook running after application deployment. | Post-deploy verification, being very careful with side effects. |

Minimal hook example:

~~~bash
#!/bin/bash
set -euo pipefail
echo "Elastic Beanstalk postdeploy hook completed"
~~~

Place it at **`.platform/hooks/postdeploy/10-verify.sh`** when supported by the platform. Across different platform releases, automatic executable permissions and line-ending handling can vary; use **LF**, verify permissions, and test hooks in staging.

**Never place destructive schema migrations or non-idempotent actions inside a hook that runs on every EC2 instance**. In a multi-EC2 environment, the same hook can execute **multiple times**, causing race conditions or duplicate side effects. Database migrations should use a dedicated orchestrated step or reliable locking.

### 9.3. Do Not Hard-Code Environment-Specific Settings

Parameters that should be managed outside the JAR per environment:

- **SPRING_PROFILES_ACTIVE**.
- Database hostname, database name, and pool settings.
- Feature flags and API base URLs.
- Log levels and observability endpoints.
- Secret references and access permissions.
- JVM memory/concurrency tuning when required.

A single tested JAR can move through **dev → staging → prod** without rebuilding if configuration is properly externalized from the artifact.

### 9.4. Java Heap and Memory

Do not set **`-Xmx`** equal to the EC2 instance's total RAM: the OS, Nginx, Java non-heap/native memory, metaspace, thread stacks, and CloudWatch/health agents all need memory too.

For instance, a modest EC2 instance can trigger the Linux **OOM killer** if the Java heap consumes most of the RAM, leading to 502 errors and unhealthy instances. Measure **RSS, heap usage, GC pauses, CPU, and memory pressure**, and size instance classes and JVM flags from real telemetry. Adding more instances will not cure a memory leak inside each JVM.

## 10. VPC, ALB, HTTPS, and Network Access Controls

### 10.1. Public ALB, Private EC2

A production environment can adopt:

- **ALB** in public subnets across at least two AZs in a load-balanced topology.
- **EC2 Java instances** in private application subnets.
- **RDS database** in private database subnets, with no unnecessary public access.
- **Security Groups** opening only the required sources, destinations, and ports.
- **NAT Gateway or VPC endpoints** so EC2 instances can reach ECR/S3/CloudWatch/SSM/Secrets Manager when needed.

Not every Beanstalk environment places EC2 instances in private subnets by default. Creating an environment in the default VPC without reviewing subnets and SGs can over-expose your application and instances.

### 10.2. Sample Security Group Flow

| Component | Direction | Illustrative Rule |
| --- | --- | --- |
| ALB SG | Inbound | TCP/443 from permitted user sources (`0.0.0.0/0` for a public API; consider WAF). |
| ALB SG | Outbound | To instance SG on the target/proxy port (commonly TCP/80). |
| EC2 SG | Inbound | Only from the **ALB SG** to the Nginx/application port. |
| EC2 SG | Outbound | To DB, external APIs, and S3/VPC endpoints/NAT as needed. |
| RDS SG | Inbound | Only from the **EC2 instance SG** on the DB port such as 5432 or 3306. |

**Never open the RDS port to the entire Internet** just because the Java app cannot connect. Check VPC routing, SG source references, database hostname, credentials, and TLS.

### 10.3. HTTPS via ACM

With an ALB:

1. Own a domain such as **api.example.com** in managed DNS.
2. Request a certificate for the hostname in the **ACM Region** matching the ALB.
3. Attach the certificate to the **ALB HTTPS listener/443**.
4. If appropriate, redirect HTTP/80 to HTTPS/443.
5. Use a Route 53 Alias A/AAAA record pointing the domain to the ALB endpoint.
6. Test HTTPS from a browser/client using the real hostname, not just the raw ALB DNS name.

TLS can be **terminated at the ALB**. If policy requires encryption from the ALB to EC2, configure the target protocol and instance proxy certificate per the corresponding guide. Do not confuse **HTTPS from client to ALB** with guaranteed end-to-end HTTPS behind the ALB.

### 10.4. `X-Forwarded-*` Headers

When sitting behind an ALB/Nginx, Spring Boot may see incoming connections to the instance as HTTP on an internal port. The application may need to honor **X-Forwarded-Proto**, **X-Forwarded-For**, and host headers to build accurate redirects and absolute URLs.

**Security warning:** Only trust forwarded headers created or overwritten by a **trusted proxy/load balancer**. Blindly accepting client-supplied headers from the Internet risks scheme/IP spoofing and authorization or URL-generation bugs.

## 11. IAM: Service Role, Instance Profile, and Java App Permissions

### 11.1. Two Commonly Confused EB Roles

| Component | Who Uses It? | Typical Permissions |
| --- | --- | --- |
| **Elastic Beanstalk service role** | The EB service operating/integrating health, updates, and environment resources. | Permissions per AWS-guided managed policies/roles. |
| **EC2 instance profile role** | EC2 instances in the environment; the Java app and agents can obtain temporary credentials. | Access to S3 deployment artifacts, CloudWatch, and AWS APIs as granted. |

If the service role or instance profile is missing or lacks permissions, environment creation or deployment can fail even though the Java code compiles cleanly.

AWS provides service-linked roles, managed policies, and role creation guides. **Never attach `AdministratorAccess`** just to clear an `AccessDenied` error; verify the exact principal and required actions.

### 11.2. Application Permissions to Access S3

Example where a Java app only needs to read objects under the **invoices/** prefix of a bucket:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadInvoicesOnly",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::example-private-invoices/invoices/*"
    }
  ]
}
~~~

This is an example policy; in production, account for role isolation across application environments, bucket policies, KMS key permissions, and network conditions. On standard EC2, the Java AWS SDK automatically retrieves **temporary credentials from the instance profile** via the default credentials provider chain.

**Never store static `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` values in `application.properties`, the JAR, the Procfile, or source control** when an IAM role can be used.

### 11.3. Secret Management

RDS passwords and third-party tokens must not live in source code.

Common options:

- **AWS Secrets Manager** for secrets needing rotation and auditing.
- **SSM Parameter Store** for configuration and SecureString parameters where appropriate.
- Environment properties for non-sensitive values.
- **Elastic Beanstalk environment secrets** referencing Secrets Manager/Parameter Store on supported platforms, instead of plaintext in config files.

When using secret references, check **platform version** support, **instance profile IAM**, **KMS permissions**, DNS/VPC endpoint/network paths, **secret rotation** behavior, and when the app refreshes the value. Do not assume that rotating a secret in Secrets Manager causes every running JVM to reload it immediately.

## 12. Secure Database Connectivity: Keep RDS Independent of the Environment Lifecycle

### 12.1. Why Not Tie Database Life and Death to EC2?

A Java API commonly uses PostgreSQL, MySQL, or Aurora to store transactions. When Elastic Beanstalk replaces EC2 instances during deployments or Auto Scaling, database data must persist intact.

**Principle:** The database needs a lifecycle, backups, recovery, and ownership **independent of the environment lifecycle**, unless it is an intentional ephemeral lab DB.

Elastic Beanstalk offers integrated RDS creation in certain workflows. If a database is coupled to the environment, terminating the environment can severely impact the database depending on configuration and retention settings. For production, **create RDS separately**, connect over VPC/SGs/IAM per guidelines, and manage backups and retention independently.

### 12.2. Decoupled Database Architecture

~~~mermaid
flowchart LR
    EB["EB Java environment"] -->|"JDBC/TLS"| RDS[("Amazon RDS PostgreSQL")]
    SEC["Secrets Manager"] -->|"Secret reference / SDK"| EB
    CICD["CI/CD"] -->|"Controlled versioned migrations"| RDS
    B["Automated backups / snapshots"] -.-> RDS
~~~

This is a conceptual diagram. CI/CD migrations should use dedicated credentials and run-once coordination; do not grant database admin privileges to the runtime application role.

### 12.3. Spring Boot Database Configuration

Example **`application.properties`** without real passwords:

~~~properties
spring.datasource.url=jdbc:postgresql://db.internal.example:5432/orders
spring.datasource.username=orders_app

# Password must come from secret injection or trusted runtime configuration.
# Never commit passwords into the source repository.

spring.datasource.hikari.maximum-pool-size=10
spring.datasource.hikari.connection-timeout=30000
~~~

Include the PostgreSQL JDBC driver only if the app actually uses PostgreSQL. The password can be supplied via secrets integration or managed runtime config, never written into documentation.

If Auto Scaling grows from 2 to 20 EC2 instances and each JVM opens up to **10 DB connections**, total connections can climb from roughly **20** to **200**, before counting admin jobs or other services. Check **`max_connections`**, pool sizing, RDS Proxy if appropriate, connection reuse, and scaling behavior.

### 12.4. Schema Migrations

A Java deployment may need to add a database column. Use Flyway, Liquibase, or a controlled migration workflow:

1. Author changes to be **backward-compatible** with both old and new versions.
2. Deploy schema expansion before new code begins writing/reading the new field when needed.
3. Run the migration step with locking/coordination; never let every EC2 instance race on destructive changes.
4. Deploy the new application version using an appropriate policy.
5. Once stable, clean up obsolete schema elements in a subsequent release.

Rolling back code **does not automatically roll back schema or data**. If a migration dropped a column, reverting the JAR to an older version can still fail. Maintain a separate database change plan.

## 13. Deployment Policies and Minimizing Downtime

Elastic Beanstalk supports several **application deployment** policies trading off speed, temporary cost, and rollback behavior. Supported features depend on the environment, platform, and tier.

| Policy | Concept | Advantages | Limitations |
| --- | --- | --- | --- |
| **All at once** | Deploys to all EC2 instances simultaneously. | Fast, simple. | Risks downtime while all instances update/restart. |
| **Rolling** | Deploys in EC2 batches. | Keeps partial capacity online. | Capacity drops during deployment; faults can impact part of traffic. |
| **Rolling with additional batch** | Adds temporary capacity, deploys in batches, then scales back. | Avoids losing existing capacity. | Temporary extra EC2 cost; requires sufficient quotas/subnet IPs. |
| **Immutable** | Launches a fresh set of instances for the release, verifies, then swaps out old ones. | Strong isolation of changes; cleaner rollback in many cases. | Extra capacity/time required; understand environment limits. |
| **Traffic splitting** | Shifts a percentage of traffic to instances running the new version during evaluation. | Supports percentage-based canary and health observation. | Requires supported load balancer/conditions and temporary capacity. |
| **Blue/green** | Creates a **separate environment** for the new version, tests it, then swaps URL/CNAME. | Isolates releases; rollback by shifting traffic back to the old environment. | Two environments running concurrently; cost and state/data/DNS care required. |

**Distinction:** Blue/green across **two environments** is a **release strategy**, not simply an option inside a single environment's deployment policy dropdown.

### 13.1. Rolling Deployment

Suppose an environment has 6 EC2 instances, rolling in batches of 2:

1. Select a batch of 2 instances to update.
2. The remaining instances continue serving traffic.
3. Verify health per platform behavior.
4. Proceed to the next batch once criteria are met.

During rollout, serving capacity drops. Ensure sufficient headroom so healthy instances are not overloaded. If a rolling deploy runs alongside a non-backward-compatible database migration, both old and new releases can fail.

### 13.2. Immutable Deployment

Immutable deployment launches a fresh group of instances under AWS management to deploy the new version. Once health checks pass as expected, the environment shifts capacity to the new fleet and terminates the old resources.

The benefit is **isolating the new release from the existing fleet** during verification instead of mutating live instances in place. However, **the database and shared state remain shared risk points**: if the new code wrote incompatible data, reverting to the old fleet may not restore business functionality.

### 13.3. Traffic Splitting

Traffic splitting routes a configurable percentage of traffic to instances running the new version via supported platform/ALB capabilities, observes health over an evaluation window, and then proceeds to full cutover or rollback.

Do not confuse **ALB traffic splitting** with **Route 53 weighted DNS records**. An ALB splits traffic at the HTTP/request layer; Route 53 weighted routing splits **DNS responses** and is subject to DNS caching.

### 13.4. Blue/Green with Two Environments

~~~mermaid
flowchart TB
    DNS["api.example.com / CNAME"] --> OLD["orders-prod-blue — version 1.4"]
    DNS -.->|"After cutover / swap"| NEW["orders-prod-green — version 1.5"]
    OLD --> DB[("RDS / shared services")]
    NEW --> DB
    TEST["Smoke tests / synthetic monitoring"] --> NEW
~~~

Workflow:

1. Create a **green environment** in the same application running the new version.
2. Configure compatible VPC/IAM/secret/database endpoints.
3. Test green via its separate environment URL and synthetic checks.
4. Verify traffic behavior, ALB health, logs, and database migrations.
5. **Swap environment CNAMEs** or shift DNS per your orchestration plan.
6. Monitor live health and behavior; keep blue running long enough for rollback.
7. Retire blue only after stability is confirmed, avoiding accidental deletion of shared resources.

A CNAME swap does not cut over every client connection instantaneously due to DNS TTL/caching and keep-alive connections; allow for transition time and test against real resolvers.

### 13.5. When to Choose Which Policy?

- Dev/test or services tolerating downtime → **All at once** can make sense.
- Multi-instance apps needing reduced impact with limited headroom → **Rolling**.
- Need to preserve full serving capacity during rollout → **Rolling with additional batch**.
- Sensitive releases needing fresh-fleet isolation and cleaner rollback → **Immutable**.
- Want to test a percentage of traffic on a new version in a compatible environment → **Traffic splitting**.
- Want two independent environments with controlled traffic switching → **Blue/green**.

No policy replaces testing **schema migrations, backward compatibility, secrets, app health, data consistency**, and rollback paths.

## 14. Auto Scaling and Resilience

### 14.1. What Does Elastic Beanstalk Scale?

In a **load-balanced environment**, EB configures an **EC2 Auto Scaling group** to add or remove EC2 instances according to supported settings and metrics.

This scales **EC2 instances running the Java app**, unlike ECS Service Auto Scaling which scales **ECS tasks**. Elastic Beanstalk does not silently use ECS capacity providers in standard Java SE/Tomcat EC2 workflows.

Key parameters:

- **Min instances:** minimum EC2 instances to keep running.
- **Max instances:** maximum EC2 instances allowed by configuration.
- **Metric/trigger:** CPU utilization, network traffic, or another platform/ASG-supported signal.
- **Scaling cooldown:** prevents oscillation while instances boot, deploy, and warm up.

### 14.2. Sizing Capacity Realistically

Suppose one EC2 instance running the Java app handles roughly **100 requests/second** at acceptable latency in load tests, and peak traffic is 600 requests/second.

Idealized estimate:

\[
\text{Minimum instances by throughput}
\approx \frac{600}{100}=6
\]

This is **not** a conclusion that "six instances are enough for production." You must also factor in:

- Headroom when an AZ or instance fails.
- Startup and JVM warm-up time.
- CPU, JVM heap, GC pauses, and thread pools.
- ALB target health, database bottlenecks, and connections.
- Request payload size and traffic skew/bursts.
- Graceful shutdown, p95/p99 latency, and retries.

When Auto Scaling launches a new EC2 instance, there must be available subnet IPs, a valid IAM instance profile, accessible artifacts, network routes to dependencies, and sufficient startup time; adding instances that are not yet ready will not relieve traffic immediately.

### 14.3. Readiness and Liveness

**Liveness:** whether the Java process is still alive.

**Readiness:** whether the instance is actually ready to serve live requests.

A health endpoint returning 200 just because the JVM is up may not verify that critical database queries work. Conversely, if a health endpoint fails whenever a minor non-critical downstream blips transiently, the ALB could mark every target unhealthy and worsen availability.

Design health checks around **critical dependencies** with bounded timeouts and clear failure thresholds, distinguishing monitoring diagnostics from traffic-routing readiness.

### 14.4. Multi-AZ Is Not Multi-Region

Load-balanced EB can span multiple AZs **within a single Region**. It does not automatically provide multi-Region active-active, replicate RDS/S3, or fail over DNS across Regions during a regional outage.

For DR/multi-Region, you need:

- Environments and data services in a standby Region.
- Replication/backups meeting **RPO**.
- Traffic failover planning such as Route 53 or Global Accelerator as needed.
- Secrets, KMS keys, IAM, certificates, and VPCs in the standby Region.
- Realistic **RTO** drills.

## 15. Observability: Health, Events, Logs, and Metrics

### 15.1. Basic Health and Enhanced Health

Elastic Beanstalk offers health mechanisms suited to the environment and platform:

- **Basic health:** foundational signals such as environment responsiveness.
- **Enhanced health:** richer aggregated data on instances, request health, and degradation causes where supported.

Health states/colors such as **Ok, Warning, Degraded, Severe** help spot trouble quickly, yet **do not replace** application logs or SLO metrics. A green status does not guarantee every business endpoint returns accurate data.

### 15.2. Log Sources You Need to Know

| Log/Signal | Purpose |
| --- | --- |
| **Application logs** | Java exceptions, business errors, startup and request diagnostics. |
| **Nginx access/error logs** | Request routing, 502/504 errors, upstream connection failures. |
| **Elastic Beanstalk deployment logs** | Hooks, artifact unpacking, startup commands, deployment failures. |
| **EC2/OS/system logs** | OOM killer, full disks, service failures, and instance lifecycle events. |
| **ALB metrics/logs** | Healthy targets, 5xx counts, latency, and traffic distribution. |
| **CloudWatch metrics/alarms** | CPU, network, Auto Scaling, and health metrics. |
| **CloudTrail** | Who modified environment config, deployed a version, or changed IAM/roles within logging scope. |

Exact log file paths vary across platform generations and versions; consult the console/EB CLI and platform docs rather than hard-coding one path for every Amazon Linux version.

### 15.3. Viewing Logs and Events with the EB CLI

~~~bash
eb status orders-dev
eb health orders-dev
eb events orders-dev
eb logs orders-dev
~~~

EB CLI flags let you download full log bundles or stream logs depending on the EB CLI version. Use commands permitted in your environment. Enable **log streaming to CloudWatch Logs** with appropriate retention so logs remain available after EC2 instances are replaced.

**Privacy note:** Never log JWTs, `Authorization` headers, database passwords, secrets, or unnecessary sensitive customer data.

### 15.4. Suggested Alarms/SLOs

- Availability of **/health** and core business endpoints.
- ALB **5xx** count, target health, and p95/p99 latency.
- EC2 CPU/memory/disk pressure (memory typically requires an agent or custom metric).
- JVM GC pauses, heap usage, and thread pools.
- RDS connections/CPU/latency and query errors.
- Deployment duration and deployment failure counts.
- EC2/ALB/NAT/data transfer costs and anomalous spikes.

When the application scales out aggressively, monitor backend metrics in parallel; an overloaded database can bottleneck the whole system even while EC2 instances look completely healthy.

## 16. Troubleshooting Java Deployments on Elastic Beanstalk

### 16.1. Symptom Table

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| **502 Bad Gateway** after deploy. | Java process not running, Nginx↔JVM port mismatch, slow app startup. | Application logs, Nginx errors, Procfile, `server.port`, health checks. |
| **503** from ALB. | Zero healthy targets, deployment replacing instances, wrong health path. | ALB target group, environment health, ASG/EC2 status. |
| **504 Gateway Timeout**. | Slow Java processing, exhausted thread pool, DB/downstream timeout, LB timeout. | ALB metrics/logs, app logs, DB latency, and thread dumps per procedure. |
| **`UnsupportedClassVersionError`**. | JAR compiled with newer Java than the EB runtime. | `java -version`, Maven target/release, platform runtime. |
| **`no main manifest attribute`** or **`Unable to access jarfile`**. | Non-executable JAR, wrong artifact path/name, bad Procfile. | Source bundle ZIP, Maven Spring Boot repackage, Procfile. |
| **Environment health Red/Degraded**. | App crash, unhealthy EC2/ALB targets, failed deployment hook, network or IAM. | EB events, enhanced health, logs, instance status. |
| **`AccessDenied`** reading S3/Secrets Manager. | Instance profile missing permissions, bucket/KMS/secret policy deny, wrong role. | Runtime STS identity per procedure, IAM/KMS/networking. |
| **RDS connection timeout**. | SG, route, private DB endpoint, DNS, subnet, or DB unavailable. | VPC path, DB SG inbound from app SG, RDS metrics. |
| **RDS authentication failed**. | Wrong user/password, secret rotation drift, DB grants. | Secret source, runtime env, database logs. |
| **Errors after scale-out**. | In-memory local sessions, uploads stored on one EC2, oversized DB pool. | Shared state, sticky sessions, S3/RDS, per-instance logs. |
| **Build/hook failure**. | File permissions, CRLF line endings, missing dependencies, script bug. | Deployment logs and `.platform`/`.ebextensions` layout. |
| **Environment update stuck**. | ASG quota/subnet IP exhaustion, health mismatch, failed instance launch, IAM/service role. | EB events, CloudFormation events, EC2/ASG activities. |
| **Old release still served after CNAME swap**. | DNS TTL/caching, browser keep-alive, custom domain delegation. | Actual DNS resolvers, CNAME/ALB targets, versions. |
| **High cost despite low traffic**. | ALB, min EC2, NAT, RDS, CloudWatch, and un-deleted staging environments. | Cost Explorer, tags, environment inventory. |

### 16.2. Diagnostic Tree

~~~mermaid
flowchart TD
    A["Java application unreachable"] --> B{"Is environment health healthy?"}
    B -->|"No"| C["Read EB events / enhanced health / deployment logs"]
    B -->|"Yes"| D{"Are DNS/TLS/ALB working?"}
    D -->|"No"| E["Check Route 53, ACM, listener, SG, ALB targets"]
    D -->|"Yes"| F{"Can Nginx reach the Java process?"}
    F -->|"No"| G["Check Procfile, JAR, server.port, JVM errors"]
    F -->|"Yes"| H{"Can the API reach DB/Secrets/dependencies?"}
    H -->|"No"| I["Check VPC routes, SG, IAM/KMS, credentials, DB"]
    H -->|"Yes"| J["Inspect application logs, business errors, latency, and state"]
~~~

Always record the **application/environment/version label, Region, deployment timestamp, HTTP status, request path, and recent configuration changes**. Do not jump to blaming "an AWS outage" upon seeing a 502: it is very often a mismatch between the Procfile, port, and Java process.

### 16.3. Specific Case: Spring Boot Default 8080 vs. Nginx 5000

Symptom:

- Spring Boot logs confirm the app started cleanly on **8080**.
- Default Nginx upstream forwards requests to **5000**.
- Clients hitting the environment URL receive **502**.

Fix:

1. Check the Java SE platform's **proxy pass/upstream port**.
2. Configure the app to listen on the matching port (e.g., **`server.port=5000`**) or customize the proxy per supported workflow.
3. Redeploy the tested source bundle.
4. Verify **`/actuator/health`** through the environment URL.

**Do not** open inbound SG port 8080 from the Internet when Nginx only needs to connect over `localhost:5000`.

### 16.4. Specific Case: Procfile Missing from ZIP Root

Symptom:

~~~text
orders-api-eb.zip
└── deploy/
    ├── Procfile
    └── app.jar
~~~

The platform looks for `Procfile` at the root, but it sits inside a nested directory. Correct structure:

~~~text
orders-api-eb.zip
├── Procfile
└── app.jar
~~~

Always inspect the archive contents before uploading—do not just look at your local source directory.

### 16.5. Specific Case: RDS Created Together with the Environment

Symptom: the team plans to terminate **orders-dev** after a lab, but the database inadvertently holds data that cannot be lost.

Resolution:

1. **Halt termination immediately** until database ownership is confirmed.
2. Check whether RDS is managed by EB inside the environment's lifecycle.
3. Define a backup/snapshot/retention plan for data that must be kept.
4. For non-ephemeral systems, decouple the DB from the environment lifecycle before cleanup per AWS-supported procedures.
5. Re-verify via restore testing, DB connectivity, and access permissions.

The guiding principle: **never equate replaceable compute environments with data that must be preserved long-term**.

## 17. AWS CLI in Read-Only Mode

The commands below only **observe state**—they do not create or modify resources. Select the proper AWS account/Region and replace illustrative names with applications/environments you own or have permission to inspect.

### 17.1. Verify Account and Application

~~~bash
aws sts get-caller-identity

aws elasticbeanstalk describe-applications \
  --application-names orders-api \
  --region ap-southeast-1
~~~

If no application is returned, check the Region, account, and permissions before concluding it does not exist.

### 17.2. View Environments

~~~bash
aws elasticbeanstalk describe-environments \
  --application-name orders-api \
  --region ap-southeast-1 \
  --query "Environments[].{Name:EnvironmentName,Id:EnvironmentId,Status:Status,Health:Health,Version:VersionLabel,URL:CNAME}"
~~~

Review **Status**, **Health**, **VersionLabel**, and **CNAME**. Multiple environments under the same application can run different versions.

### 17.3. Inspect Environment Resources

~~~bash
aws elasticbeanstalk describe-environment-resources \
  --environment-name orders-prod \
  --region ap-southeast-1
~~~

Output lists associated resources such as EC2 instances, Auto Scaling groups, load balancers, scaling triggers, and supported components. Use these exact IDs to investigate further with EC2/ELB/ASG APIs rather than guessing IDs from environment names.

### 17.4. View Deployment Events

~~~bash
aws elasticbeanstalk describe-events \
  --environment-name orders-prod \
  --max-records 30 \
  --region ap-southeast-1
~~~

Events reveal updates, deployments, instance health changes, and EB-level failure reasons. **Events do not replace application logs** when hunting for Java exceptions.

### 17.5. View Detailed Health

~~~bash
aws elasticbeanstalk describe-environment-health \
  --environment-name orders-prod \
  --attribute-names All \
  --region ap-southeast-1
~~~

This requires **enhanced health** enabled and appropriate permissions. If unsupported on an environment, inspect `describe-environments`, EB events, and ALB/EC2 metrics/logs rather than assuming the environment is healthy.

### 17.6. Inspect Application Versions

~~~bash
aws elasticbeanstalk describe-application-versions \
  --application-name orders-api \
  --region ap-southeast-1 \
  --query "ApplicationVersions[].{Version:VersionLabel,Status:Status,Source:SourceBundle,Created:DateCreated}"
~~~

Verify version labels and source bundles against your release pipeline. Having the right version label **does not guarantee the source bundle contains a valid Procfile/JAR** if an incorrect artifact was uploaded.

### 17.7. Inspect Environment Configuration

~~~bash
aws elasticbeanstalk describe-configuration-settings \
  --application-name orders-api \
  --environment-name orders-prod \
  --region ap-southeast-1
~~~

Output may contain **environment property values** or sensitive settings depending on your permissions; **never paste raw output into public chats, tickets, or logs**. When sharing is necessary, redact credentials, internal endpoints, and secret references per policy.

### 17.8. List Available Platform Versions

~~~bash
aws elasticbeanstalk list-platform-versions \
  --region ap-southeast-1
~~~

Depending on the output, filter by `PlatformBranchName`/`PlatformVersion`/`PlatformStatus` to find Java SE/Tomcat and confirm support status. This avoids picking **an old deprecated platform** simply because it appeared in a tutorial.

### 17.9. Cross-Checking ALB/ASG

If **`describe-environment-resources`** returns an associated ASG or load balancer, query them with the corresponding AWS CLI commands:

~~~bash
aws autoscaling describe-auto-scaling-groups \
  --auto-scaling-group-names example-eb-asg \
  --region ap-southeast-1

aws elbv2 describe-load-balancers \
  --names example-eb-alb \
  --region ap-southeast-1
~~~

The names in the snippet are **placeholders**—substitute real resource names. Read-only commands may return `AccessDenied` if your role lacks IAM permissions.

## 18. Cost and Lifecycle Control

### 18.1. Does Elastic Beanstalk Charge a Separate Service Fee?

**Elastic Beanstalk charges no additional fee for the deployment service itself**, but the resources an environment creates or connects to **are billed under their respective AWS services**.

| Resource | Potential Charges |
| --- | --- |
| **Amazon EC2** | Instance hours, instance types, Savings Plans/Reserved/Spot if applicable. |
| **Elastic Load Balancing** | Load balancer hours and LCU/usage units. |
| **Amazon EBS** | Provisioned volumes and snapshots. |
| **Amazon S3** | Storing application bundles, logs, backups, requests/transfers. |
| **Amazon RDS/Aurora** | DB instances/storage/IO/backups/transfers. |
| **CloudWatch** | Logs, metrics, alarms, log retention. |
| **VPC networking** | NAT Gateway, data processing, VPC endpoints, data transfer. |
| **Route 53 / ACM / WAF** | DNS hosted zones/queries, certificate/edge security components per pricing. |

An environment with **zero users** still accrues charges while EC2/ALB/RDS/NAT remain running. Actual amounts depend on Region, running hours, data volume, and configuration.

### 18.2. How to Optimize Costs in a Small Lab?

- Create **single-instance** if the goal is solely learning deployments and health checks during a lab.
- Choose an instance size adequate for **Java heap/CPU**—do not pick an undersized machine that causes constant JVM OOMs.
- Skip creating RDS/NAT/ALB if the lab does not need them, unless studying those specific components.
- Monitor AWS Budgets/Cost Explorer and apply owner/environment tags.
- After the lab, verify **environment termination** and check for leftover resources, **without deleting important databases**.
- Set shorter log retention where appropriate and prune old application versions/artifacts per policy.
- For production, compare total cost and features against ECS Fargate, App Runner, or self-managed EC2—do not assume Beanstalk is always the cheapest.

### 18.3. Controlling Platform Maintenance

- Track platform branch/version support status and security patches.
- Consider **managed platform updates** during appropriate maintenance windows.
- Test in a staging environment before upgrading runtimes/OS.
- Keep snapshots of config/IaC, application artifacts, and a database rollback plan.
- Do not wait until a platform reaches end-of-support to start upgrade testing.

The Java runtime and Spring dependencies have independent lifecycles. EB patching Amazon Linux or Corretto does not replace upgrading Spring Boot, Log4j, or JDBC drivers and resolving application CVEs.

## 19. Comparing Beanstalk with Other Java Deployment Options

| Criterion | **Elastic Beanstalk** | **Self-Managed EC2** | **ECS Fargate** | **AWS App Runner** | **AWS Lambda Java** |
| --- | --- | --- | --- | --- | --- |
| Abstraction level | PaaS deploying apps onto an EB-managed EC2/ELB/ASG stack. | Team configures nearly everything manually. | Container tasks/services with Fargate-provisioned compute. | Managed web application/container service. | Event/invocation-driven functions. |
| Artifact | JAR/WAR/source bundle per platform. | Flexible: JAR, WAR, Docker, AMI. | Container image/task definition. | Source/image per supported features. | Function artifact/image per runtime. |
| Servers | EB manages lifecycle, though EC2 instances exist. | Team directly manages EC2. | No EC2 host management. | High-level host abstraction. | No persistent server management. |
| Scaling | EB configures EC2 ASG for load-balanced envs. | Manually set up/tune ASG and ELB. | ECS Service Auto Scaling task count. | Service autoscaling per configuration. | Concurrency per request/event and quotas. |
| OS control | Available within EB platform conventions. | Highest. | Limited host access; container-focused. | Limited underlying infrastructure control. | No host OS control. |
| Best fit | Java web/APIs wanting fast deploy with EC2/ELB/VPC control. | Legacy apps/agents/deep OS customization. | Containerized microservices needing the ECS ecosystem. | Web apps wanting even less infrastructure ops. | Event-driven/short-lived functions within runtime limits. |
| Trade-off | Platform lifecycle, EB conventions, and EC2 costs. | High operational overhead. | Requires containerization and task orchestration. | Service-specific config/integration limits. | Cold starts, timeout/concurrency/event model. |

**There is no single absolute right answer.** If a project is a continuously running Spring Boot API, Beanstalk Java SE can accelerate getting started. If you already have a Docker pipeline and many microservices, ECS Fargate may fit better. If the workload is genuinely event-driven, Lambda may fit within its execution limits and architecture requirements.

## 20. Scenario Exercises

### Exercise A — Spring Boot JAR Deploy Returns 502

**Context:** The team uploads a ZIP containing `app.jar` and `Procfile`. Java logs show embedded Tomcat started on port 8080. Hitting the environment URL returns 502.

**Question:** What should you check first?

**Suggested solution:** Check the **Procfile**, **`server.port`**, and Nginx's upstream port on the Java SE platform. If the default proxy forwards to 5000 while the app listens on 8080, align either the app or the proxy and redeploy. Test health via the environment URL. Do not open port 8080 publicly if the proxy only connects locally.

### Exercise B — New Version Requires Java 21

**Context:** The application source/bytecode was upgraded to Java 21, while the environment still runs Corretto 17.

**Question:** Will scaling up the EC2 instance size fix this?

**Suggested solution:** No. Select a Java SE platform branch supporting Corretto 21 (if supported by AWS in that Region), test the runtime/dependencies, and plan an appropriate update or blue/green migration. `UnsupportedClassVersionError` is a Java version mismatch, not a CPU/RAM shortage.

### Exercise C — Want Zero Downtime During Deployment

**Context:** A production API serves customers continuously across 4 EC2 instances behind an ALB. The release updates Java code without breaking backward compatibility in the database schema.

**Question:** Which policy should you choose?

**Suggested solution:** Evaluate **rolling with additional batch**, **immutable**, or **traffic splitting** based on quotas, cost, and canary needs. For higher-risk releases, **blue/green** lets you verify a separate environment and switch traffic deliberately. Any choice still requires health checks, startup/graceful shutdown tuning, and rollback testing.

### Exercise D — Database Lost When Deleting Lab Environment

**Context:** A dev environment has a database created alongside the EB environment. The team wants to terminate the environment.

**Question:** Can they delete it immediately?

**Suggested solution:** Not yet. Verify whether the database is coupled to the environment lifecycle, what data must be kept, backup/retention settings, and AWS-supported RDS decoupling steps. Terminate only after confirming data is preserved or acceptable to discard per lab goals.

### Exercise E — Scaling EC2 Still Leaves API Timing Out

**Context:** Under load, EB Auto Scaling increases from 2 to 8 EC2 instances; per-EC2 CPU drops, yet the API still times out with database connection errors.

**Question:** What is the likely cause?

**Suggested solution:** The DB connection pool multiplies with instance count and overwhelms DB limits, or slow queries/locks/RDS resources are bottlenecked. Inspect active connections, pool sizes, transaction durations, and RDS metrics, and consider RDS Proxy or scaling up the database. Scaling EC2 does not fix a backend bottleneck.

### Exercise F — CI Wants Reproducible Artifact Deployments

**Context:** The pipeline currently runs a Maven build directly on Beanstalk EC2 instances during every deployment, and flaky dependency downloads slow rollouts.

**Question:** How should the workflow change?

**Suggested solution:** Build and test in CI on controlled runners, store an immutable **versioned JAR/source bundle**, create an EB application version, and deploy that exact artifact across dev/staging/prod using checksums/version labels and retained release history. Avoid uncontrolled dependency downloads on individual EC2 instances.

### Exercise G — Multi-AZ Causes Users to Lose Login Sessions

**Context:** After expanding Auto Scaling across two AZs, some users keep getting logged out.

**Question:** Is Beanstalk broken, or is the application missing something?

**Suggested solution:** The app is likely storing sessions in each JVM's local memory, so subsequent requests routed to another EC2 lack the session. Move session state to a shared store or adopt stateless auth (e.g., tokens or ElastiCache as appropriate); treat ALB stickiness only as an option with trade-offs, not as the sole availability strategy.

## 21. Common Misconceptions

| Misconception | Correct Understanding |
| --- | --- |
| "Elastic Beanstalk is Lambda, so there are no EC2 charges." | Standard EB Java web environments still run on EC2 and bill for underlying resources. |
| "Application and Environment are the same object." | An Application groups versions and environments; one application can have multiple independent environments. |
| "The Java SE platform accepts any WAR with zero config." | Executable JARs fit Java SE; external Tomcat WARs should use a compatible Tomcat platform. |
| "If the app runs locally on port 8080, the EB proxy knows automatically." | You must match the Java process port to the proxy configuration, commonly 5000 by default on Java SE. |
| "Uploading a ZIP containing a `deploy/` folder is good enough." | `Procfile` and `app.jar` must sit at the source bundle root or configured path. |
| "Beanstalk automatically builds full DB HA and backups." | Database lifecycle, HA/backups, and RPO/RTO are separate architectural responsibilities. |
| "Having an ALB automatically gives multi-AZ/HA." | You also need ASG MinSize, multi-AZ subnets, healthy instances, durable data stores, and failover testing. |
| "Putting secrets in `.ebextensions` and committing to Git is fine." | Never commit plaintext secrets; use Secrets Manager or supported secure references. |
| "Having an IAM service role gives the Java app S3 access." | Apps on EC2 typically use the instance profile; those are two distinct roles. |
| "Rolling deployments need no capacity headroom." | Rolling can reduce serving capacity during updates, so account for traffic load and batch sizes. |
| "Immutable deploy guarantees database rollback." | Deployment rollbacks do not undo schema migrations or data mutations. |
| "Terminate only stops the Java process." | It can delete EC2/ELB/ASG and environment resources, risking coupled databases. |
| "Scaling out EC2 fixes every 502/timeout." | Root causes can be code bugs, ports, IAM, networking, DB, JVM memory, or downstream services. |
| "Beanstalk health green means all business logic works." | Health is a technical signal, not a replacement for business testing and SLO monitoring. |
| "A CNAME swap switches 100% of users instantly." | DNS caching and connection reuse can keep traffic flowing to the old version temporarily. |
| "Managed platform updates need no regression testing." | OS/runtime/library upgrades can introduce regressions; test in staging with a rollback plan. |

## 22. Self-Check Questions

**Question 1.** How does an Elastic Beanstalk Application differ from an Environment?  
**Answer:** An Application groups versions and environments; an Environment is the running set of resources for a specific version and configuration.

**Question 2.** When should you pick the Java SE platform instead of the Tomcat platform?  
**Answer:** For a Spring Boot executable JAR with an embedded HTTP server, Java SE fits; for a WAR requiring external Tomcat, pick a compatible Tomcat platform.

**Question 3.** What is the minimal `Procfile` content for a Java SE JAR named `app.jar`?  
**Answer:** **`web: java -jar app.jar`**, placed at the root of the source bundle.

**Question 4.** Why can a Java app on port 8080 cause Nginx to return 502?  
**Answer:** If EB's proxy forwards to `localhost:5000`, nothing is listening on that port; align the app and proxy ports.

**Question 5.** How does an EB platform version differ from an application version?  
**Answer:** Platform version defines the OS/runtime and tooling; application version defines the deployed application artifact/code.

**Question 6.** Is a single-instance environment suitable as a default production HA architecture?  
**Answer:** No. It typically lacks an ALB and multiple instances and can suffer downtime if the EC2 fails.

**Question 7.** Why shouldn't uploaded files live solely on an EC2 instance's filesystem in an EB environment?  
**Answer:** EC2 instances can be replaced or scaled; other instances will not have those files. Durable data belongs in S3/EFS or an appropriate datastore.

**Question 8.** How does an IAM service role differ from an EC2 instance profile?  
**Answer:** The service role allows EB to manage and integrate environment resources; the instance profile grants permissions to EC2 and applications running on it.

**Question 9.** What error occurs if a JAR compiled for Java 21 runs on a Java 17 runtime?  
**Answer:** `UnsupportedClassVersionError`; you need a compatible platform/runtime, not more CPU.

**Question 10.** Should database passwords be placed directly in `pom.xml`, `Procfile`, or `.ebextensions` and committed?  
**Answer:** No. Use Secrets Manager/Parameter Store or platform-supported secret references with least-privilege IAM/KMS.

**Question 11.** Does an ALB using an ACM certificate guarantee encryption on the ALB → EC2 hop?  
**Answer:** Not automatically; verify the target protocol and backend TLS configuration if policy requires end-to-end encryption.

**Question 12.** Can a rolling deployment temporarily reduce serving capacity?  
**Answer:** Yes. Updating batches are taken out of service temporarily, so ensure headroom or use rolling with additional batch.

**Question 13.** How does blue/green differ from an immutable deployment?  
**Answer:** Blue/green uses two independent environments and switches traffic/CNAMEs; immutable launches a new fleet within the existing environment's deployment flow.

**Question 14.** After a successful code rollback, does the database schema roll back automatically?  
**Answer:** No. Schema/data migrations require separate compatibility planning and rollback procedures.

**Question 15.** When diagnosing a Java 502 error, which sources should you inspect first?  
**Answer:** EB events/health, application startup logs, Nginx error logs, `Procfile`/port configuration, and ALB target health.

**Question 16.** Does Elastic Beanstalk charge a separate service fee?  
**Answer:** There is no extra fee for Elastic Beanstalk itself; EC2, ALB, EBS, RDS, NAT, S3, CloudWatch, and related services are billed normally.

**Question 17.** Why can adding more EC2 instances worsen database timeouts?  
**Answer:** Total DB connections and requests increase; if the DB is the bottleneck, scaling the web tier adds further overload.

**Question 18.** Which read-only AWS CLI command inspects environment events without modifying resources?  
**Answer:** **`aws elasticbeanstalk describe-events --environment-name ...`**.

**Question 19.** What should be verified before terminating a lab environment?  
**Answer:** Database lifecycle, backups, data to retain, and EC2/ELB/NAT/EBS or other billable resources.

**Question 20.** Why is a stable environment health status not enough to prove a release succeeded?  
**Answer:** You still need smoke tests, business validations, latency/5xx checks, database consistency, and real user monitoring.

## 23. Summary and Production Deployment Checklist

**Deploying Java on Elastic Beanstalk** is the process of packaging an executable JAR or WAR into an **application version**, choosing a **Java SE/Tomcat platform**, creating an **environment**, and letting EB coordinate EC2, Auto Scaling, load balancing, health monitoring, and deployment lifecycles.

Short checklist for a Spring Boot API:

1. **Build:** compatible JDK/Corretto, passing Maven tests, executable JAR, and clear version label.
2. **Artifact:** source bundle ZIP with **`app.jar` + `Procfile`** at the root, zero credentials included.
3. **Platform:** AWS-supported Java SE platform, aligned app/proxy ports, compatible dependencies.
4. **Environment:** load-balanced, multi-AZ where needed, VPC/subnets/SGs enforcing proper security boundaries.
5. **IAM:** separated service role and EC2 instance profile, least-privilege S3/Secrets/KMS permissions.
6. **Data:** RDS/backups/replication independent of the environment lifecycle; S3 for durable files, session state off EC2.
7. **HTTPS:** Route 53/ACM/ALB, listener/redirect rules, and trusted forwarded headers.
8. **Health:** accurate readiness path, healthy ALB targets, enhanced health, and CloudWatch logs/alarms.
9. **Release:** appropriate rolling/immutable/traffic-splitting or blue/green policy; backward-compatible migrations and pre-tested rollback.
10. **Scaling:** EC2 min/max, load testing, DB pool sizing, startup/warm-up tuning, and multi-AZ failover.
11. **Cost:** monitor EC2/ALB/RDS/NAT/EBS/CloudWatch, tag resources, and clean up labs deliberately.
12. **Maintenance:** keep platform/Java/Spring updated on lifecycle schedules, run staging regression tests, and audit changes.

Elastic Beanstalk reduces deployment and infrastructure orchestration overhead, yet **availability, data safety, and Java application quality still must be engineered and measured**. Choosing the right platform, bundle layout, ports, health checks, IAM roles, and database lifecycle prevents most real-world deployment failures.

### Official AWS Documentation

- [What is AWS Elastic Beanstalk?](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/Welcome.html) — overview of application, environment, and platform.
- [Java SE platform](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/java-se-platform.html) — Java SE, Procfile, and Java applications.
- [Tomcat platform](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/java-tomcat-platform.html) — deploying WAR web applications on Tomcat.
- [Configuring Elastic Beanstalk environments](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.managing.html) — environment configuration.
- [Platform hooks](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/platforms-linux-extend.hooks.html) — `.platform/hooks` on Amazon Linux platforms.
- [Environment configuration files](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/ebextensions.html) — `.ebextensions` configs and option settings.
- [Deployment policies and settings](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.rolling-version-deploy.html) — rolling, immutable, and deployment options.
- [Blue/green deployments](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/using-features.CNAMESwap.html) — two environments and traffic shifting.
- [Elastic Beanstalk security](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/security.html) — IAM, service roles, and instance profiles.
- [Enhanced health reporting](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/health-enhanced.html) — health and diagnostics.
- [EB CLI command reference](https://docs.aws.amazon.com/elasticbeanstalk/latest/dg/eb-cli3.html) — init, create, deploy, logs, health, and terminate.
- [Elastic Beanstalk pricing](https://aws.amazon.com/elasticbeanstalk/pricing/) — billable resources.

