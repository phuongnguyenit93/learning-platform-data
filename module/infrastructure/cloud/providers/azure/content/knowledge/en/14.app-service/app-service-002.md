# Deploying Java SE and Java Web Applications

In Microsoft Azure, a Java application can run on a self-managed virtual machine, in a container, or on a managed platform service. When building a Java API, website, or backend, **Azure App Service** is a Platform as a Service (PaaS) option that lets you focus on application code and operations instead of building and maintaining the entire operating system and web server stack yourself.

However, "deploying Java" is not just uploading a file to the cloud. You must decide on the **execution model**, **artifact format**, **Java runtime**, **web container**, **App Service Plan**, application settings, network paths, identity, logging, scaling, and release/rollback strategy.

This lesson belongs to the **Web Applications with App Service** chapter of the **CLOUD_PROVIDERS_AZURE** module. Along our path covering subscriptions, resource groups, Microsoft Entra ID, virtual networking, compute, storage, and data, we will deploy two common application types:

- **Java SE on App Service:** a Java application with an embedded web server, packaged as an **executable JAR**. A typical example is a Spring Boot REST API using embedded Tomcat/Jetty.
- **Java web on App Service:** a Servlet/Jakarta Servlet application packaged as a **WAR**, running inside a platform-provided **Tomcat** container. Other stacks such as JBoss EAP have their own runtime, packaging, licensing, and SKU requirements.

> **Key takeaway:** Java SE on App Service **does not mean** running an arbitrary console program that exits immediately. App Service is designed for web applications or HTTP services that continuously listen on an appropriate port and can start, restart, and scale on demand.

## 1. Learning objectives

After completing this lesson, you will be able to:

1. Distinguish between a Java SE executable JAR and a Java web WAR/Tomcat application in Azure App Service.
2. Explain the relationship between a **Web App**, **App Service Plan**, **runtime stack**, operating system, and region.
3. Determine how to choose JDK/Tomcat versions compatible with your source code and artifact.
4. Build and verify a simple Java SE JAR application and a simple Servlet WAR application.
5. Create an App Service Plan/Web App using the Azure Portal and Azure CLI, and deploy each artifact using its proper type.
6. Securely configure environment variables, startup behavior, ports, health endpoints, logging, and secrets.
7. Test the application over HTTPS and troubleshoot 404/502/503, startup, and version mismatch errors.
8. Design a CI/CD workflow and staging slot/rollback strategy when supported by the service tier.
9. Understand scaling, costs, deployment zones, private networking, and data protection when running in production.

## 2. What problem does Azure App Service solve?

App Service provides an Azure-managed hosting environment for web applications. You deploy code or artifacts; the platform handles web app management, runtime configuration, HTTPS endpoints, deployment, logs, and scaling/availability capabilities based on the selected **App Service Plan**.

Example Orders API architecture:

~~~mermaid
flowchart LR
    U["Users / Frontend"] -->|"HTTPS"| A["Azure App Service<br/>Java Orders API"]
    A -->|"Managed identity"| K["Azure Key Vault"]
    A -->|"Application connection"| D["Azure SQL Database"]
    A -->|"SDK / HTTP"| S["Azure Storage"]
    P["Azure Monitor / App Insights"] -. "Logs, traces, metrics" .-> A
    C["CI/CD pipeline"] -->|"Deploy JAR or WAR"| A
~~~

You do not have to provision a VM for every web app. Nevertheless, you **remain responsible** for dependency vulnerabilities, application logic, permission settings, data, network access, health checks, performance, and costs.

### 2.1. Azure components to understand

| Component | Role | Example |
|---|---|---|
| **Subscription** | Management/billing boundary | Subscription for the development environment |
| **Resource group** | Logical grouping of resources with related lifecycle/governance | rg-java-app-lab |
| **App Service Plan** | Pool of compute capacity and scale/SKU characteristics serving one or more Web Apps | asp-java-linux-lab |
| **Web App** | Resource configuring endpoints, runtime, code deployment, and app settings | orders-api-lab |
| **Runtime stack** | Java SE, Tomcat, or Java environment supported by App Service | Java SE with a compatible JDK |
| **Deployment artifact** | Built file to deploy | orders-api.jar or orders-web.war |
| **Deployment slot** | Separate deployment environment within the same app on supported tiers | staging |
| **Managed identity** | App identity used to access Azure services without storing static passwords | System-assigned identity |
| **Monitoring** | Logs, metrics, tracing, and alerts | Azure Monitor / Application Insights |

### 2.2. How does a Web App differ from an App Service Plan?

A **Web App** defines the application you deploy. An **App Service Plan** determines the region, operating system, SKU, instance count, and compute capacity the app uses.

~~~mermaid
flowchart TD
    RG["Resource group"] --> PLAN["App Service Plan<br/>Linux / single region / SKU"]
    PLAN --> A["Web App A<br/>Java SE JAR"]
    PLAN --> B["Web App B<br/>Tomcat WAR"]
    PLAN --> C["Web App C<br/>Another Java API"]
~~~

Multiple apps can share a single plan **when configuration supports it**, but they share the plan's compute capacity and scaling behavior. One app consuming excessive CPU/memory can impact other apps on the same plan.

**Stopping a Web App does not automatically stop App Service Plan billing.** Many paid tiers bill based on provisioned plan instance capacity, not by request count or the time a Java process receives user traffic.

## 3. Choosing the right deployment type: Java SE or Java web?

### 3.1. Java SE with an executable JAR

Common scenario: a Spring Boot application packaged as a **self-contained executable JAR**, including its dependencies and embedded web server.

~~~text
Java code + dependencies + embedded web server
                    |
                 Maven/Gradle
                    |
              orders-api.jar
                    |
          App Service: Java SE
                    |
          Java process listening for HTTP
~~~

The application starts via an entry point, such as **public static void main(String[] args)**. The JAR must genuinely be **executable**: containing the proper manifest/launcher and required dependencies. A plain library JAR is not sufficient to run a web service.

**Best suited for:** Spring Boot REST APIs, self-packaged web services, applications with embedded Tomcat/Jetty/Undertow or a compatible embedded HTTP server.

### 3.2. Java web with a WAR in Tomcat

Another scenario: an application using Servlet/Jakarta Servlet, JSP, or a framework deployed into a pre-installed servlet container.

~~~text
Servlet / JSP / Web framework
              |
          Maven WAR
              |
         orders-web.war
              |
       App Service: Tomcat
              |
     Tomcat manages web context
~~~

A **WAR** application does not necessarily have a standalone **java -jar** command. Tomcat provides the servlet container, lifecycle, context path, and Java web components according to the runtime version.

**Best suited for:** traditional Servlet/JSP applications, Spring MVC WARs, or applications that must be deployed as a web archive onto Tomcat.

### 3.3. Quick comparison table

| Criterion | Java SE (executable JAR) | Java web (WAR/Tomcat) |
|---|---|---|
| Artifact | Self-running JAR | WAR |
| Startup mechanism | Java main/launcher and embedded web server | Tomcat deploys the web archive |
| Who provides the web server? | Artifact/application | Platform's Tomcat runtime |
| Example | Spring Boot executable JAR | Servlet/JSP, Spring MVC WAR |
| What to verify | Manifest, dependencies, startup, and HTTP port | Servlet API, Tomcat version, context path |
| URL behavior | Usually direct according to app routes | May include a context path based on WAR name/config |
| Common errors | Non-executable JAR, wrong port binding, process exits | Wrong Servlet version in WAR, 404 context, deploy failure |
| JVM configurability | Per supported runtime and startup/settings | Per Tomcat runtime, server settings, and app settings |

A **Spring Boot** application can be packaged either way, but the build setup differs. Do not deploy a WAR and select Java SE as if the WAR were an executable JAR; likewise, do not drop an executable JAR into Tomcat and expect it to run properly without a supported mechanism.

### 3.4. Is JBoss EAP the same as Tomcat?

No. **JBoss Enterprise Application Platform (EAP)** is a Java application server with a different ecosystem and feature set from Tomcat. If a project uses Jakarta EE APIs, EJB, or other enterprise server features, you must evaluate separately:

- JBoss EAP runtime variants and currently supported App Service environments.
- Appropriate Java/Jakarta EE version.
- Supported WAR/EAR formats and deployment methods.
- Licensing, terms of use, SKUs, and costs.
- Startup, configuration, and connectivity requirements.

This lesson focuses on **Java SE/JAR** and **Tomcat/WAR** to illustrate the two core deployment paths.

## 4. Choosing the runtime environment and versions

### 4.1. Linux or Windows?

App Service offers supported Java runtimes on both Linux and Windows per Azure's support list. Do not assume a given feature or Tomcat version exists on both operating systems.

Consider:

1. The JDK version supported by your code and dependencies.
2. Available Java SE or Tomcat runtimes on the target OS.
3. Requirements for native libraries, fonts, locales, file paths, and case sensitivity.
4. Runtime/OS-specific startup and logging mechanisms.
5. Networking, deployment slot, scaling, and plan SKU features.
6. Licensing or compliance requirements.

The CLI examples in this lesson use a **Linux App Service Plan**. If an application relies on the Windows Registry, `.dll` files, or Windows paths, do not migrate it straight to Linux without testing.

### 4.2. Java and Tomcat versions must be compatible

Three versions are easy to confuse:

- **Build JDK**: the JDK used in CI/Maven to compile.
- **Runtime JDK**: the Java version configured in the Web App.
- **Servlet/Tomcat API**: the container version and namespace used by the web application.

Common error: compiling with newer Java bytecode than the runtime → **UnsupportedClassVersionError**. To prevent this, configure **maven.compiler.release** or an appropriate toolchain aligned with the App Service Java runtime.

Specifically for Tomcat:

- Older applications using **javax.servlet** are not automatically compatible with Jakarta-generation Tomcat using **jakarta.servlet**.
- Tomcat 10+ switched to the Jakarta namespace in the Servlet API. Changing runtimes may require migrating code and dependencies.
- Do not take a WAR built for Tomcat 9 and deploy it to Tomcat 10.1 simply because both are "Tomcat."

### 4.3. Do not hard-code runtime lists from outdated docs

Azure-supported runtime/stack versions can change. Check the **Azure Portal** or CLI output right before creating a Web App:

~~~bash
az webapp list-runtimes --os linux --output table
~~~

This command returns the runtime identifiers supported at the time you check. Pick the exact value for **Java SE** or **Tomcat** and the matching JDK; in subsequent examples, replace placeholders with the exact listed runtime string rather than inventing a stack name.

For production apps, also maintain an upgrade plan before a runtime or framework reaches end-of-support, scan for vulnerabilities, and run integration tests after upgrading.

## 5. End-to-end workflow from source code to production

~~~mermaid
flowchart TD
    S["Source + build config"] --> B["Compile, test, package"]
    B --> A{"Artifact?"}
    A -->|Executable JAR| J["App Service Java SE"]
    A -->|WAR| T["App Service Tomcat"]
    J --> C["App settings, identity, network"]
    T --> C
    C --> D["Deploy to staging / test"]
    D --> E["Smoke test + health check + logs"]
    E --> F{"Pass?"}
    F -->|Yes| P["Release production"]
    F -->|No| R["Rollback / fix issue"]
    R --> B
    P --> M["Monitor, scale, patch, optimize cost"]
~~~

Before starting the lab, verify precisely:

- **Artifact**: JAR or WAR, filename, version, dependencies.
- **Runtime**: Java SE or Tomcat, Java release, OS.
- **Configuration**: environment variables, connection endpoints, secrets.
- **Connectivity**: whether the app uses SQL/Storage/Key Vault or internal services.
- **Health**: endpoint verifying application readiness.
- **Release**: rollback plan if the new version fails to start.
- **Cost**: SKU/instances and supporting resources.

## 6. Example A: Java SE executable JAR application

To illustrate packaging differences, we will create a minimal HTTP server using only the JDK. In real projects, you can replace it with a Spring Boot executable JAR built with your organization's vetted starter.

### 6.1. Maven structure

~~~text
orders-java-se/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── HealthServer.java
~~~

The Maven project needs to build a JAR with a **Main-Class** and an HTTP server listening continuously on a port. The example uses **JDK 17** for brevity; when deploying, select a compatible Azure runtime. This is a demonstration app, not a full production web server.

### 6.2. HealthServer.java file

~~~java
package com.example;

import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;

public final class HealthServer {
    public static void main(String[] args) throws IOException {
        // Only use PORT if the runtime environment provides this variable.
        // Defaulting to 8080 is for demo purposes; verify the actual port
        // routed by the App Service runtime.
        String configured = System.getenv("PORT");
        int port = configured == null || configured.isBlank()
                ? 8080 : Integer.parseInt(configured);

        HttpServer server = HttpServer.create(
                new InetSocketAddress("0.0.0.0", port), 0);

        server.createContext("/health", exchange -> {
            byte[] body = "{\"status\":\"UP\",\"runtime\":\"Java SE\"}"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "application/json; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.createContext("/", exchange -> {
            byte[] body = "Orders Java SE demo"
                    .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                    .set("Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (var output = exchange.getResponseBody()) {
                output.write(body);
            }
        });

        server.start();
        System.out.println("HTTP server is listening on port " + port);
    }
}
~~~

Key points:

- **0.0.0.0** lets the process listen across the container/network namespace rather than only localhost.
- **/health** returns HTTP 200 when the demo can serve traffic.
- The process keeps running after **server.start()**, fitting a web workload.
- The code contains no secrets or state requiring long-term persistence on the local filesystem.
- The port **must match the routing mechanism of the Java SE stack in App Service**. The **PORT** variable may be provided/configured depending on the environment; do not assume every stack or custom container uses the exact same variable.
- For production, Spring Boot or a servlet engine provides richer HTTP capabilities, reverse-proxy TLS handling, graceful shutdown, and observability than this demo.

### 6.3. pom.xml file to build an executable JAR

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>orders-java-se</artifactId>
  <version>1.0.0</version>
  <packaging>jar</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-jar-plugin</artifactId>
        <version>3.4.2</version>
        <configuration>
          <archive>
            <manifest>
              <mainClass>com.example.HealthServer</mainClass>
            </manifest>
          </archive>
        </configuration>
      </plugin>
    </plugins>
  </build>
</project>
~~~

This template demonstrates the build setup; in real operations, manage plugin/JDK versions according to security policies and verify the build environment.

### 6.4. Build and test locally

~~~bash
# Run inside the orders-java-se/ directory
mvn -B clean package

# Run using a compatible JDK
java -jar target/orders-java-se-1.0.0.jar
~~~

In another terminal:

~~~bash
curl --fail --show-error http://localhost:8080/health
~~~

Expected response:

~~~json
{"status":"UP","runtime":"Java SE"}
~~~

Before deploying, confirm the artifact actually builds and runs under the Java release you plan to select on App Service. **Do not start by uploading raw `.java` source files expecting App Service to guess every dependency and `Main-Class`**.

### 6.5. How does a Spring Boot executable JAR differ from this example?

For a real-world REST app built with Spring Boot, the path is typically:

~~~text
@RestController + Spring Boot + dependencies
              |
       mvn clean package
              |
      Spring Boot executable JAR
              |
         App Service Java SE
~~~

The Spring Boot plugin packages dependencies and the embedded server into an executable JAR with an appropriate launcher. If you already have a Spring Boot project on your team, you can deploy that JAR using the same Java SE flow in this lesson, but you must check:

- Build and runtime JDK compatibility with your Spring Boot version.
- That the artifact is truly an executable JAR, not a thin library JAR.
- HTTP port, startup/health endpoints, environment variables, and profiles.
- Database connections, pool settings, logging, and graceful shutdown.
- That no credentials are embedded inside **application.properties** in the artifact.

## 7. Example B: Java web WAR application for Tomcat

To clearly distinguish JAR from WAR, the second example uses **Jakarta Servlet** and Maven WAR packaging. The code below targets a Servlet API compatible with **Tomcat 10.1**; if your Tomcat runtime uses a different API version, adjust dependencies and imports accordingly.

### 7.1. Project structure

~~~text
orders-web/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── HealthServlet.java
~~~

### 7.2. Sample Servlet

~~~java
package com.example;

import jakarta.servlet.annotation.WebServlet;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;

@WebServlet("/health")
public class HealthServlet extends HttpServlet {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        response.setStatus(HttpServletResponse.SC_OK);
        response.setContentType("application/json; charset=UTF-8");
        response.getWriter().write("{\"status\":\"UP\",\"runtime\":\"Tomcat\"}");
    }
}
~~~

A Servlet **has no main method**. Tomcat receives the request, resolves the **/health** mapping, and invokes the corresponding servlet. In a production app, include proper authentication, validation, error handling, and logging.

### 7.3. POM for WAR

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <groupId>com.example</groupId>
  <artifactId>orders-web</artifactId>
  <version>1.0.0</version>
  <packaging>war</packaging>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>jakarta.servlet</groupId>
      <artifactId>jakarta.servlet-api</artifactId>
      <version>6.0.0</version>
      <scope>provided</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-war-plugin</artifactId>
        <version>3.4.0</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

**Scope provided** indicates that Tomcat supplies the Servlet API at runtime, avoiding bundling a duplicate servlet API inside the WAR. If the app uses Spring MVC or other Jakarta EE libraries, dependencies will be more extensive.

### 7.4. Build the WAR

~~~bash
# Run inside the orders-web/ directory
mvn -B clean package

# Inspect the generated file in target/
# Example: target/orders-web-1.0.0.war
~~~

The WAR contains classes, resources, and web app metadata; Tomcat deploys the archive and manages its lifecycle.

### 7.5. Context path and ROOT.war

Tomcat typically organizes web apps by context path. In some deployment configurations:

- A WAR named **orders-web.war** may be reachable under the **/orders-web** context.
- A WAR deployed as **ROOT.war** or to a runtime-supported root target may serve the **/** context.

With App Service, how the deployment tool places the WAR into Tomcat and handles the root context can depend on the runtime/target path. **Verify the actual context URL after deployment**, rather than assuming any uploaded file automatically serves **/health** at the root.

If you get an HTTP 404, inspect the WAR deployment logs and context path before changing NSGs or database firewalls.

## 8. Preparing Azure resources for the lab

The examples below **are not executed automatically in this lesson**. They illustrate commands for a practice subscription/resource group you are authorized to manage. Replace placeholders and verify region/SKU/quotas and costs before running.

### 8.1. Prerequisites

- An Azure subscription and permissions to create resource groups, App Service Plans, and Web Apps.
- A build machine with **JDK**, **Maven**, and a supported Azure CLI version.
- JAR/WAR artifacts already tested and running locally.
- A chosen region supporting Linux App Service and the required runtimes.
- A **globally unique** Web App name within the service namespace for a valid hostname.
- App deployment permissions (does not require full Subscription Owner).
- Clarity on whether the app uses a database, Storage, Key Vault, or VNet Integration.
- A lab budget and a plan to delete resources after practicing.

### 8.2. Sign in and create a resource group

~~~bash
az login
az account set --subscription "<subscription-id>"
az account show --output table

RG="rg-java-app-lab"
LOCATION="southeastasia"

az group create \
  --name "$RG" \
  --location "$LOCATION"
~~~

A resource group is a management scope with its own region metadata; it does not force every resource inside it to be in the same region. The App Service Plan and Web App must follow the service's region/OS rules.

### 8.3. Create a Linux App Service Plan

~~~bash
PLAN="asp-java-linux-lab"

az appservice plan create \
  --name "$PLAN" \
  --resource-group "$RG" \
  --location "$LOCATION" \
  --sku B1 \
  --is-linux
~~~

This uses **Basic B1** for the lab; pricing and availability may vary by region. Smaller tiers have limits on compute, memory, scaling, and deployment features. If a workload requires **deployment slots**, zone redundancy, or advanced scaling, choose a plan/SKU that supports those specific capabilities.

**An App Service Plan can start incurring charges as soon as it is created, even when the application receives no requests.**

## 9. Creating and deploying a Java SE Web App with Azure CLI

### 9.1. Choose the right Java SE runtime

~~~bash
az webapp list-runtimes --os linux --output table
~~~

Match against the runtimes supported in your region/OS and the JDK version used to build. Then:

~~~bash
JAVA_SE_RUNTIME="<exact-Java-SE-runtime-id-from-list>"
JAVA_SE_APP="<globally-unique-java-se-webapp-name>"

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$JAVA_SE_APP" \
  --runtime "$JAVA_SE_RUNTIME"
~~~

For example, the **JAVA_SE_RUNTIME** placeholder must be the exact string from `list-runtimes`; **do not** substitute a vague label like "Java 17" if the CLI expects a different identifier.

### 9.2. Set non-sensitive app settings

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --settings APP_ENV=lab
~~~

App Service app settings are exposed to the runtime as environment variables via the platform mechanism. In Java, you can read them with:

~~~java
String environment = System.getenv("APP_ENV");
~~~

For secrets, never place passwords directly into command history, shell scripts, pipeline logs, or Git. Refer to the Key Vault/managed identity section.

### 9.3. Deploy the executable JAR

~~~bash
az webapp deploy \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --src-path "target/orders-java-se-1.0.0.jar" \
  --type jar
~~~

This command assumes your working directory is the Maven project root containing the built artifact. Type **jar** must match the Java SE runtime.

Depending on the runtime and deployment method, App Service has mechanisms to automatically detect and launch the artifact. **If the app does not start automatically**, inspect startup logs, where the artifact resides on the server, and startup command support for your specific stack/OS; do not guess a fixed file path without verifying where the artifact was placed/extracted.

### 9.4. Inspect configuration and hostname

~~~bash
az webapp show \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --query "{name:name,state:state,host:defaultHostName,location:location}" \
  --output json

az webapp config show \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --query "{linuxFxVersion:linuxFxVersion,alwaysOn:alwaysOn,appCommandLine:appCommandLine}" \
  --output json
~~~

Actual fields may vary by OS/API and CLI version. Using the hostname output, construct the application's HTTPS URL:

~~~bash
curl --fail --show-error \
  "https://<globally-unique-java-se-webapp-name>.azurewebsites.net/health"
~~~

Expect an UP status response when the Java process listens on the expected port and requests route to the app. If you see a default page, timeout, or HTTP 5xx, check deployment status, process startup, port binding, and logs.

### 9.5. When is a startup command needed?

For some Java SE apps, you may need to configure a **startup command** or adjust the runtime when custom JVM options, classpaths, or special startup behavior are required.

Safe guidelines:

1. Check the default startup behavior of your Java SE runtime.
2. Check deploy logs to see where the artifact was actually placed.
3. Verify how the runtime selects the JAR, startup command, and port.
4. Set a custom command only when necessary and tested in staging.
5. Never put secrets inside the command.
6. Verify the app still starts cleanly after restarts and scale-out.

Do not hard-code a guessed command like **java -jar /some/guessed/path/app.jar** without verifying the instance path. Likewise, do not run a background process that exits the startup script without keeping the web server alive.

## 10. Creating and deploying a Tomcat/WAR Web App with Azure CLI

### 10.1. Create a Web App running Tomcat

~~~bash
az webapp list-runtimes --os linux --output table
~~~

Select a **Tomcat** runtime compatible with your Java release and Jakarta Servlet API, such as a Tomcat generation supporting your project's **jakarta.servlet**. Do not use the Java SE runtime option for this example's WAR.

~~~bash
TOMCAT_RUNTIME="<exact-Tomcat-runtime-id-from-list>"
TOMCAT_APP="<globally-unique-tomcat-webapp-name>"

az webapp create \
  --resource-group "$RG" \
  --plan "$PLAN" \
  --name "$TOMCAT_APP" \
  --runtime "$TOMCAT_RUNTIME"
~~~

Both apps can share one plan in the lab for demonstration, though they **share CPU/memory**. For critical systems, consider separating plans by load, deployment boundary, or security requirements.

### 10.2. Deploy the WAR

~~~bash
az webapp deploy \
  --resource-group "$RG" \
  --name "$TOMCAT_APP" \
  --src-path "target/orders-web-1.0.0.war" \
  --type war
~~~

This assumes you are running from the WAR project directory containing the artifact. After deployment:

1. Inspect deployment logs and Tomcat logs.
2. Check the created web application name/context path.
3. Call the `/health` endpoint under the actual context.
4. Confirm no package namespace or missing dependency errors appear.
5. Check startup time and readiness before opening production traffic.

Example check assuming context deployed by archive name:

~~~bash
curl -i \
  "https://<globally-unique-tomcat-webapp-name>.azurewebsites.net/orders-web-1.0.0/health"
~~~

**This URL is illustrative only**, not a guarantee that CLI deployment sets the context path to that exact name. If App Service deploys the WAR as the root context, the endpoint may be **/health**. Determine the actual context from runtime/deployment logs; if root context is needed, use a Microsoft-supported deployment method/target path and test after changing it.

### 10.3. Deploying a Spring Boot WAR

If a Spring Boot project currently outputs an executable JAR and needs to be deployed onto an external Tomcat, you typically must adjust the build and application bootstrap:

- Change packaging to **war**.
- Mark the embedded servlet container dependency as **provided** per Spring Boot documentation.
- Provide a servlet container entry point, typically a class extending **SpringBootServletInitializer**.
- Verify Spring Boot version and Servlet API/Jakarta namespace compatibility with Tomcat.
- Verify static resources, context paths, and filters.
- Build and test the WAR on an equivalent Tomcat version before deploying.

Do not simply rename the extension **.jar → .war**. The archive structure and startup lifecycle are two distinct mechanisms.

## 11. Azure Portal: deploying the same scenario

With the Portal, you can provision Java SE or Tomcat apps without writing CLI commands upfront.

### 11.1. Create the Web App

1. Open **Azure Portal → App Services → Create → Web App**.
2. Select subscription, resource group, and application name.
3. Choose **Publish: Code** if deploying artifacts to a built-in runtime.
4. Select the appropriate runtime stack: **Java** for Java SE or **Tomcat** where the Portal offers the corresponding option.
5. Select the supported Java version and OS.
6. Select the region and a suitable App Service Plan; review limits and pricing.
7. Review the networking, monitoring, deployment, and security configuration tabs.
8. Review, deploy, and wait for Web App provisioning to complete.
9. Open **Overview** and note the default hostname and runtime settings.

Menu labels may change as the Portal updates. Available runtimes depend on OS/region/tier.

### 11.2. Upload the artifact

Options include CLI deployment, IDE plugins, CI/CD, or Deployment Center. When choosing:

- **Executable JAR:** use deployment type **JAR** with a Java SE runtime.
- **WAR:** use **WAR deployment** targeting Tomcat.
- **Source deployment:** only when the builder/Oryx/CI is explicitly configured to produce the artifact.
- **Container image:** a separate **custom container** workflow requiring image, registry, runtime, listening port, and startup details matching container requirements.

To keep this exercise reproducible, record artifact versions and deployment logs; avoid ad-hoc drag-and-drop uploads with no history or build traceability.

## 12. Environment configuration: App settings and connection strings

### 12.1. Why separate configuration from the artifact?

A tested artifact should be deployable across **dev**, **staging**, and **production** without editing source code to change endpoints or credentials.

Example:

| Setting | Dev | Production |
|---|---|---|
| APP_ENV | dev | prod |
| API_BASE_URL | Test URL | Production URL |
| DB_HOST | Dev database | Production database |
| LOG_LEVEL | DEBUG or controlled INFO | INFO/WARN per policy |
| Secret | Secret from dev Key Vault | Secret from production Key Vault |

Sensitive data should never be hard-coded in **pom.xml**, Java classes, committed **application.properties** files, or shell history.

### 12.2. App settings and environment variables

~~~bash
az webapp config appsettings set \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP" \
  --settings APP_ENV=dev LOG_LEVEL=INFO
~~~

In Java:

~~~java
String env = System.getenv("APP_ENV");
String logLevel = System.getenv("LOG_LEVEL");
~~~

Notes:

- Changing app settings can trigger an app restart.
- Environment variable naming and resolution depend on the framework.
- **Spring Boot** maps environment variables to framework properties; verify precedence among app settings, command-line arguments, and profiles.
- When using slots, mark settings as **deployment slot settings** as needed to avoid accidentally swapping production and staging credentials/endpoints.
- Do not edit live settings in the Azure Portal without syncing your IaC/pipeline source of truth.

### 12.3. Managed identity and Key Vault

A safer pattern than static credentials:

~~~mermaid
flowchart LR
    A["App Service Java"] -->|"Managed identity token"| I["Microsoft Entra ID"]
    I -->|"Access token"| A
    A -->|"Read secret via RBAC"| K["Azure Key Vault"]
    A -->|"Azure SDK and RBAC"| S["Storage / Database"]
~~~

Workflow:

1. Enable a **system-assigned** or **user-assigned managed identity** on the Web App.
2. Grant **least-privilege** roles on target services at the proper scope.
3. Use Azure SDKs and appropriate credential chains, such as **DefaultAzureCredential**, where supported.
4. For secrets exposed as app settings, consider **Key Vault references** per App Service guidance.
5. Verify connectivity in staging; watch for 401/403 errors and permission changes.

Example enabling identity:

~~~bash
az webapp identity assign \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP"
~~~

Enabling an identity **does not automatically grant permission** to read secrets in Key Vault. Role assignments/policies must be configured separately, approved, and scoped to the right data-plane permissions.

### 12.4. HTTP port configuration

App Service runs a reverse proxy/frontend that forwards requests to your application. The Java process must listen on the **exact port** expected by the selected stack/OS and bind to an interface reachable by incoming traffic.

- For frameworks like Spring Boot, check **server.port** and how the runtime injects the port.
- For custom Java SE startups, check environment variables and port guidance provided by Azure for that stack.
- For built-in Tomcat, avoid overriding the server port unnecessarily.
- For custom containers, follow container-specific rules for exposed/listening ports and settings such as **WEBSITES_PORT** when applicable.

A program bound only to **127.0.0.1** or to a port App Service does not route to may stay running internally while continually returning HTTP 502/503 on the public endpoint.

## 13. Logging, health checks, and application observability

### 13.1. Configure an appropriate health endpoint

In both examples, the **/health** endpoint confirms the app returns HTTP 200. In production, distinguish:

- **Liveness:** the process/application is still running.
- **Readiness:** the application is ready to accept business traffic.
- **Dependency health:** whether databases, queues, caches, or downstream services are reachable.

Do not require every secondary dependency to be Healthy for a liveness probe if doing so causes unnecessary restart loops. Health endpoints should return minimal data and never leak configuration details, internal paths, or secrets.

### 13.2. Application logs and platform logs

When deployment fails, distinguish:

| Log type | Question |
|---|---|
| Deployment/build log | Was the artifact uploaded and deployed successfully? |
| Startup/console log | Did the JVM start, and were there startup exceptions? |
| Tomcat log | Did the WAR deploy to the expected context, and is the Servlet API compatible? |
| Application log | Did an endpoint return 500 due to code, SQL, config, or a dependency? |
| HTTP access log | What requests reached the server, with what status codes and latency? |
| Azure Activity Log | Who changed settings, runtime, scaling, or triggered restarts? |
| Application Insights | Request telemetry, dependency calls, exceptions, and distributed traces as configured |

Where supported, stream logs via Portal or CLI:

~~~bash
az webapp log tail \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP"
~~~

Log streaming requires logging to be enabled and supported by the OS/runtime/deployment type. If the command produces no output, that **does not prove the app is error-free**; check Diagnostic settings, log streams, and other monitoring tools.

### 13.3. Application Insights and Azure Monitor

For production, configure Java instrumentation via Azure-supported mechanisms to track:

- Request rates, 4xx/5xx status codes, and p50/p95/p99 latency.
- Exceptions by type and timestamp.
- Dependency calls to databases, HTTP APIs, and Storage.
- App Service Plan/Web App CPU, memory, and instance counts.
- Startup failures, restarts, health checks, and availability tests.
- Alerts on error spikes, abnormal latency, or unhealthy instances.

Manage sampling, retention, PII, and ingestion costs. **Never log passwords, access tokens, connection strings, or sensitive customer data**.

## 14. Safe releases and rollbacks

### 14.1. Never deploy straight to production without smoke tests

Pipelines should include clear stages:

~~~mermaid
flowchart LR
    C["Git commit"] --> B["Maven build"]
    B --> T["Unit + integration tests"]
    T --> S["Security/dependency scan"]
    S --> A["Versioned JAR/WAR"]
    A --> D["Deploy staging"]
    D --> H["Health/smoke tests"]
    H --> P["Promote / swap production"]
    P --> M["Monitor error rate and latency"]
    M --> R{"Release healthy?"}
    R -->|No| RB["Rollback per runbook"]
~~~

A deployment marked successful only means the artifact arrived or the deployment operation completed. It **does not guarantee the application has reached readiness** or that business routes work.

### 14.2. Deployment slots

On App Service Plan tiers that support deployment slots, you can create a **staging slot**, deploy the new version there, validate it, and **swap** it into production once verified.

Benefits:

- Test the build in a production-like environment.
- Warm up the application before shifting traffic where supported.
- Provide a fast path back to the previous version on issues.

Notes:

- Not every tier has deployment slots; **do not assume slots exist on the Basic B1 lab tier**.
- Slots share the plan's compute capacity and can increase memory/CPU pressure.
- App settings may be slot-specific or swapped depending on configuration.
- Swapping does not automatically roll back database schema or data changes.
- Verify sessions, caches, in-flight requests, and background jobs.

### 14.3. Why must database migrations be decoupled from artifact rollbacks?

Suppose a new Orders API release adds a column and changes a data format. If the WAR/JAR deployment is rolled back, the database does not automatically revert to the old schema. A code rollback may fail if the schema was altered incompatibly.

Risk mitigation:

1. Make database changes **backward-compatible** whenever possible.
2. Separate migrations and code rollouts into controlled phases.
3. Track schema versions and test rollbacks.
4. Maintain backups/snapshots using the database's supported mechanisms.
5. Run smoke tests covering both APIs and read/write data flows.

## 15. Scaling, memory, and the JVM

### 15.1. Scale up and scale out

- **Scale up:** change the App Service Plan tier/size for more capacity per instance.
- **Scale out:** increase the number of instances serving the app within plan limits.
- **Autoscale:** adjust instance counts by metrics/schedules when supported by the SKU and service.

Not every plan/OS supports the same autoscale rules or instance counts. Before deploying to production, verify quotas, limits, availability, and billing.

### 15.2. JVM memory does not equal total plan RAM

Java uses heap, metaspace, thread stacks, native memory, code cache, and other regions. Setting **-Xmx** too close to the instance's total physical memory can cause the JVM or container/process to be killed under memory pressure.

Measure:

- Heap usage and garbage collection pauses.
- Non-heap/native memory and thread count.
- Request concurrency and connection pools.
- Memory footprint during app warm-up and peak load.
- Combined memory when multiple Web Apps share a plan.
- JVM startup flags supported by the App Service runtime.

Do not blindly copy an arbitrary JVM heap value from a high-RAM VM onto a small B1 App Service Plan.

### 15.3. Stay stateless to scale cleanly

When scaling out, a single user's requests can hit multiple instances. Therefore:

- Avoid storing unique business data on the Web App's local filesystem.
- Use Azure Storage, a database, Redis, or an appropriate state store.
- Do not rely on static/in-memory variables to share sessions across all instances.
- Use session affinity only when you understand its trade-offs; explicit external state management is preferable.
- Implement retries, idempotency, and graceful shutdown for in-flight requests.

For Java web WARs, in-memory Tomcat sessions are not automatically synchronized across App Service instances either.

## 16. Filesystem, artifacts, and persistent data

App Service provides a filesystem for runtime and deployment, but the app host should not be treated as a durable file server.

### 16.1. Do not write critical data alongside artifacts

Application content directories such as **wwwroot** can be affected by deployments, scaling, or deployment modes. Temp directories are generally not guaranteed to survive restarts/recycles.

Applications should not:

- Write unique customer records into the project directory.
- Keep unique user-uploaded files on local disk.
- Depend on data stored solely in one instance's local cache.
- Modify files inside the deployment package expecting other instances to see the change.

Instead, use Azure Blob Storage/Azure Files or an appropriate database; define retention, backups, and access controls separately.

### 16.2. When Java needs a temporary directory

You may use temp directories for short-lived request processing, provided you:

1. Enforce quotas and cleanup.
2. Never store unprotected secrets there.
3. Handle temp files disappearing upon instance restarts.
4. Never use temp files as an inter-instance communication channel.
5. Monitor disk pressure and I/O.

### 16.3. Build artifacts must be versioned

Every release should be traceable:

~~~text
Git commit:     <commit-id>
Artifact:       orders-api-1.4.2.jar
Build JDK:      approved version
App runtime:    compatible Java SE runtime
Environment:    staging / production
Deployment:     <deployment-id-or-pipeline-run>
Smoke test:     PASS / FAIL
~~~

Record this metadata in your pipeline and release logs; do not embed tokens or secrets in public artifact metadata.

## 17. Networking: Internet ingress and VNet Integration

A Web App may expose a public HTTPS endpoint while needing private connectivity to SQL/Storage inside a VNet.

### 17.1. Inbound and outbound are two separate concerns

- **Inbound:** clients send requests to the Web App via its endpoint, custom domain, or a reverse proxy service.
- **Outbound:** the Web App calls databases, Storage, Key Vault, or internal systems.
- **VNet Integration:** primarily provides **outbound connectivity from the app** to resources via a VNet as supported.
- **Private Endpoint for App Service:** relates to **private inbound access** to the Web App when supported by the service/tier.

**Configuring VNet Integration alone does not make the Web App's public endpoint private.** Nor will a database Private Endpoint automatically work if the app's DNS and routing are not configured properly.

### 17.2. Example app using Azure SQL Database

Model:

~~~mermaid
flowchart LR
    C["Client"] -->|"HTTPS"| W["App Service Java API"]
    W -->|"VNet Integration (outbound)"| V["Integration subnet / VNet"]
    V -->|"Private IP / private DNS"| P["SQL Private Endpoint"]
    P --> D["Azure SQL Database"]
~~~

Before deploying:

1. Verify plan/tier/region support for VNet Integration.
2. Size and configure a dedicated integration subnet per requirements.
3. Configure Private Endpoints and private DNS for target services if used.
4. Design Azure RBAC/Entra authentication or database identities.
5. Test DNS resolution and TCP connectivity from the app environment.
6. Never open the SQL firewall to **0.0.0.0/0** just "to make it work."

### 17.3. Securing production ingress

Evaluate based on requirements:

- HTTPS only and appropriate TLS versions.
- Custom domains and certificates with lifecycle management.
- Access restrictions to narrow allowed source ranges.
- Private Endpoint for the Web App when private ingress is required and supported.
- Application Gateway/WAF or Azure Front Door for reverse proxying, HTTP protection, and global routing.
- Authentication/Authorization in App Service or inside the application.
- Network paths and DNS for service-to-service traffic.

Do not treat WAF, TLS, and RBAC as interchangeable. A system still needs application-level authorization for individual endpoints and data.

## 18. Securing dependencies, secrets, and the supply chain

Deploying a JAR/WAR pushes not only your code to Azure, but also every library bundled inside the artifact.

### 18.1. Dependency verification

- Pin dependency versions according to organizational policy.
- Run CVE/SCA scanners in the pipeline.
- Inspect transitively bundled libraries.
- Update the JDK, frameworks, and Tomcat on schedule and when critical vulnerabilities arise.
- Generate an SBOM when supply-chain policy requires it.
- Verify licenses and approved artifact repositories.

For WARs, **provided** dependencies must match the actual Tomcat runtime. For JARs, the embedded server and dependencies are the artifact's responsibility, not just Azure's runtime.

### 18.2. Deployment permissions should not be Owner

CI/CD only needs permissions to deploy to the Web App/slot or appropriate deployment endpoint. Use federated identity/OIDC or a managed identity/service principal where supported instead of storing long-lived publishing passwords.

Never commit a **publish profile** containing credentials to a repo or print it in logs. Create separate identities per environment with minimal scope.

### 18.3. Checking for data exposure

- Never let health endpoints print environment variables.
- Never enable sensitive debug modes in production.
- Never log connection strings on startup failures.
- Never expose Swagger/admin consoles publicly without authentication.
- Never store user data uncontrolled in temp directories.
- Maintain secret revocation/rotation procedures and authorization tests.

## 19. Comparing deployment strategies

| Deployment method | Input | When appropriate | What to verify |
|---|---|---|---|
| **Azure CLI deploy JAR** | Executable JAR | Java SE API or embedded web server | Startup, port, dependencies |
| **Azure CLI deploy WAR** | WAR | Tomcat Servlet/JSP/MVC | Tomcat version, context path, Servlet namespace |
| **IDE plugin** | Built project artifact | Fast developer iteration | Runtime config and deploy permissions |
| **Maven deployment plugin** | Maven project/artifact | Integrated build and deploy | Plugin version, auth, settings, and artifact type |
| **CI/CD** | Versioned JAR/WAR | Controlled production releases | Tests, secrets, approvals, rollback |
| **Custom container** | OCI image | Complex runtime/custom OS needs | Image security, registry, port, startup, and lifecycle |
| **Source deployment** | Source code | When build pipeline is explicitly supported | Build command, artifact reproducibility |

**Do not mix one artifact type with a mismatched stack just because Azure accepts the file upload.** Create the Web App with the right runtime first, deploy the matching artifact, and verify via the health endpoint.

## 20. App Service costs and sensible optimization

### 20.1. The App Service Plan is the billed compute unit

A Web App might receive zero requests for hours, yet a paid App Service Plan still reserves compute capacity based on tier and instance count. Therefore:

- Do not confuse **az webapp stop** with **az vm deallocate**.
- Stopping a Web App does not automatically deallocate the entire plan the way deallocating a VM does.
- If multiple apps share a plan, the plan's compute charge is generally shared rather than billed as a separate VM per app.
- Costs change when scaling up/out, changing SKUs, or adding plans in other regions.
- Separate charges may apply for Application Insights, log storage, databases, Storage Accounts, Front Door, Key Vault, NAT Gateways, and other supporting services.

A lab-only App Service Plan forgotten after practice can continue generating charges even with zero users.

### 20.2. Three primary optimizations

1. **Right-size the plan**: measure CPU, memory, requests, startup, and latency before choosing a tier.
2. **Share plans sensibly**: consolidate low-traffic apps, while preventing one app from degrading others.
3. **Scale to demand**: use metric/schedule-based autoscale where supported rather than over-provisioning statically without data.

For workloads that run a single task and exit, evaluate Azure Functions, Azure Container Apps jobs, or appropriate batch services; App Service is not always cost-effective for processes that do not continuously serve HTTP.

### 20.3. Cost monitoring

In Azure Cost Management:

- Select the correct subscription/resource group.
- Group by service/resource/meter based on available data.
- Compare App Service Plan costs against databases, storage, logs, and networking.
- Track instance count/SKU changes over the period.
- Tag owner/environment and set budgets for labs.
- Follow a clear procedure to shut down labs and clean up resources with proper permissions.

Do not rely on a single fixed unit price without verifying region, plan, and effective date.

## 21. Availability, zones, and disaster recovery

Successfully deploying an App Service Web App does not automatically mean the architecture meets HA/DR requirements.

### 21.1. Single instance vs. multiple instances

One instance may suffice for a lab; production requires evaluating:

- Which availability SLA conditions apply to the plan/tier.
- Whether multiple instances, health checks, and autoscaling are required.
- Zone redundancy if supported by the region/SKU/plan.
- Whether stateful data resides outside the instances.
- Whether databases/Storage have adequate redundancy and backups.

Scale-out adds instances within supported models, but does not replace data protection and failover testing.

### 21.2. Multi-region disaster recovery

If the business requires recovery when an entire region fails, you typically need:

- App Service Plans/Web Apps or standby deployment capability in a secondary region.
- Managed artifacts and configuration to redeploy identically.
- Database/storage replication and backups aligned with RPO.
- DNS or Traffic Manager/front-end routing able to redirect users.
- Key Vault, managed identities, networking, and external dependencies in the secondary region.
- Runbooks, drills, rollback steps, and data reconciliation procedures.

Do not mistake deployment slots for multi-region DR. Slots normally reside in the same app/plan/region and support releases/rollbacks, not regional failover.

## 22. Common errors and troubleshooting

| Symptom | Common cause | Resolution |
|---|---|---|
| JAR uploads successfully but web returns 502/503 | JVM/process not running, wrong port, crash after startup | Inspect startup logs, port, Main-Class, dependencies |
| Java SE JAR fails to start | Plain library JAR, missing launcher or Main-Class | Run **java -jar** locally, verify packaging |
| **UnsupportedClassVersionError** | Build JDK is newer than selected runtime | Align compiler bytecode target with runtime JDK |
| **ClassNotFoundException** | Missing dependency or classpath issue | Check fat JAR/Spring Boot packaging, WAR libs, and scope |
| Tomcat WAR returns 404 | Wrong context path, servlet mapping, or failed deploy | Verify deployment/context and routes |
| Tomcat WAR fails to load servlet | javax/jakarta mismatch or incompatible Servlet API | Choose matching Tomcat version, migrate packages |
| Web App shows default welcome page | Artifact not deployed properly or startup does not point to app | Check deploy history, file contents, and runtime |
| Runs locally but cannot connect to SQL in cloud | Network/DNS/identity or firewall issue | Check VNet Integration, private endpoint/DNS, credentials |
| 401/403 calling Key Vault/Storage | Managed identity missing proper role or wrong token/scope | Check role assignments, SDK, and data-plane permissions |
| JVM killed or restarting continuously | Memory limit exceeded or startup too heavy | Inspect heap/GC, native memory, SKU, and logs |
| HTTP 503 during deployment | Restart/recycle, readiness not met, or invalid config | Staging, warm-up, startup logs, rollback |
| Some requests fail after scale-out | Unshared local session/file cache | Use external state; inspect session/DB pools |
| App settings changed unexpectedly on swap | Slot settings not configured properly | Review sticky settings and release checklist |
| App Service still bills after stopping app | Plan compute still exists | Inspect App Service Plan, SKU/instances, and billing |
| Old artifact continues running | Deployment incomplete, caching, or wrong slot/app | Verify deployment record, hostname, and build version |

### 22.1. Outside-in troubleshooting workflow

When a Java API is unreachable:

1. **Verify URL/hostname**: are you calling the right app, region, slot, and context path?
2. **Verify Web App state**: is the resource Running without configuration errors?
3. **Verify deployment**: was the expected artifact version actually deployed?
4. **Verify runtime**: Java SE/JAR or Tomcat/WAR, and is the JDK compatible?
5. **Inspect startup logs**: did the JVM/Tomcat start, and what is the exact error?
6. **Verify HTTP listener/port**: is the process listening on the expected interface/port?
7. **Probe the health endpoint**: does the route return 200 or 404/5xx, and is the context path right?
8. **Check dependencies**: SQL, Storage, Key Vault, network/private DNS/identity?
9. **Check capacity**: CPU/memory, instance recycles, threads, connection pools?
10. **Correlate with releases**: did errors begin after a deployment/config change, and can you safely roll back?

Never "fix" issues by disabling authentication or opening a public database firewall wide open. Read the exact error message and troubleshoot the right layer.

### 22.2. When App Service startup fails

A practical runbook should capture:

- Deployment ID, artifact version, and commit.
- Runtime stack/OS and JDK version.
- Startup command and recently changed app settings.
- Exact exception logs (with secrets redacted).
- Health status and platform restart timestamps.
- Dependency status.
- Rollback or hotfix decision and approver.
- Post-remediation verification evidence.

## 23. Controlled CI/CD deployment

### 23.1. Minimal Maven pipeline

~~~text
Stage 1 — Validate
    - Check out exact Git commit
    - Build with consistent JDK
    - mvn test
    - Static checks / dependency scan

Stage 2 — Package
    - mvn package
    - Select .jar or .war artifact per runtime
    - Version/hash artifact

Stage 3 — Deploy staging
    - Authenticate to Azure with authorized identity
    - Deploy to the target Web App/slot
    - Verify deployment result

Stage 4 — Smoke test
    - HTTPS /health
    - A read-only business endpoint
    - Controlled dependency check
    - Inspect logs and error rates

Stage 5 — Promote
    - Approval if required
    - Supported slot swap / release mechanism
    - Monitor production and roll back if needed
~~~

### 23.2. Reproducibility principles

- Build once, deploy the **same artifact** across environments whenever possible.
- Do not rebuild with shifting dependency versions between staging and production.
- Keep secrets out of Git and artifacts.
- Document exact runtime/JDK/Tomcat versions per environment.
- Require production approvals and a rollback plan.
- Rely on application health checks, not just upload success.
- Treat database migrations as separate, higher-risk changes.

### 23.3. When staging slots are unavailable

On the Basic tier or in smaller environments, you can still set up:

- A **separate** staging Web App/plan if budget permits.
- Versioned artifacts and an independent smoke test suite.
- Defined maintenance windows for deployments if needed.
- Backups/configuration snapshots or a way to redeploy the prior artifact.
- Log checks after every release.

Do not claim zero-downtime deployment merely because **az webapp deploy** finished.

## 24. Safe lab resource cleanup

When finished, check which resources were created **solely for this lab** and whether any data or configuration needs to be kept:

1. Do the two Java SE/Tomcat Web Apps hold local data or deployments worth saving?
2. Is the App Service Plan serving any other Web Apps?
3. Does the resource group hold team resources like Azure Monitor, Storage, Key Vault, or databases?
4. Are there shared public IPs, custom domains, certificates, DNS entries, or integrations?
5. Who is the owner and who is authorized to delete them?
6. Should logs, deployment metadata, or backups be exported first?

For example, deleting **one lab Web App** after careful checks:

~~~bash
az webapp delete \
  --resource-group "$RG" \
  --name "$JAVA_SE_APP"
~~~

**Deleting a Web App does not guarantee App Service Plan billing stops** if the plan remains. Delete the plan only after confirming no other Web Apps or services use it:

~~~bash
az appservice plan delete \
  --resource-group "$RG" \
  --name "$PLAN" \
  --yes
~~~

These commands are examples for a **lab you own**, not instructions for deleting shared environments. Never delete a production resource group just to save costs.

## 25. Production deployment checklist

- [ ] Clearly chosen between **Java SE executable JAR** and **Tomcat WAR**.
- [ ] Artifact built and tested locally with a compatible JDK.
- [ ] Runtime stack/OS/Java/Tomcat still supported by Azure.
- [ ] If using Tomcat, **javax/jakarta** Servlet version matches properly.
- [ ] Built artifact is versioned with controlled dependencies.
- [ ] App Service Plan fits region, SKU, CPU/memory, scaling, and budget.
- [ ] Java process binds the proper interface/port; health endpoint checks readiness.
- [ ] App settings managed per environment with no secrets in the repo.
- [ ] Managed identity and least-privilege permissions granted at the right scope.
- [ ] Inbound/outbound networking, private DNS, and database connectivity tested.
- [ ] HTTPS/TLS, authentication/authorization, and access restrictions configured.
- [ ] Logs, traces, metrics, and alerts enabled as needed.
- [ ] Tested for startup failures, missing dependencies, and multi-instance execution.
- [ ] No unique business state stored on the Web App's local filesystem.
- [ ] Deployed to staging or test environment before production.
- [ ] Artifact rollback plan and compatible database migrations in place.
- [ ] Confirmed App Service Plan continues billing by provisioned capacity.
- [ ] Runbooks ready for releases, incident response, scaling, and disaster recovery.

## 26. Hands-on exercises

### Exercise 1: Choose the runtime

Classify the following applications as **Java SE JAR**, **Tomcat WAR**, or needing another runtime evaluation:

1. A Spring Boot REST API running embedded Tomcat packaged as an executable JAR.
2. A legacy Java Servlet using **javax.servlet** deployed on an older Tomcat generation.
3. A new Jakarta Servlet app built as a WAR for Tomcat 10.1.
4. A Jakarta EE app relying on JBoss EAP-specific features.
5. A Java program that reads a file and exits after 10 seconds without serving HTTP.

Explain why item 5 does not fit the default App Service web hosting model.

### Exercise 2: Deploy a Java SE JAR

In an approved lab resource group:

1. Build the sample JAR and test **java -jar** locally.
2. Create a Linux B1 App Service Plan.
3. List runtimes and choose a JDK-compatible Java SE runtime.
4. Create the Web App and deploy the JAR.
5. Call **/health** over HTTPS.
6. Record the build version, URL, and logs.
7. Explain why a JAR might run locally yet return 502/503 on App Service.

### Exercise 3: Deploy a Tomcat WAR

Build the Servlet WAR from section 7:

1. Confirm **jakarta.servlet** API compatibility with the chosen Tomcat.
2. Deploy the WAR to a Tomcat Web App.
3. Identify the actual context path.
4. Verify **/health**.
5. Describe differences from a Java SE JAR regarding entry point and lifecycle.
6. Explain why simply renaming **.war** to **.jar** does not create an executable app.

### Exercise 4: Secure database configuration

The Orders API needs to read Azure SQL Database over a private network and fetch secrets from Key Vault:

- Design VNet Integration and private access paths to SQL.
- Configure DNS and authentication.
- Enable the Web App's managed identity.
- Assign least-privilege Key Vault permissions.
- Keep passwords/connection strings out of the repo.
- Define safe health/smoke tests and state the risks of overly broad firewall rules.

### Exercise 5: Plan a production release

The team plans to upgrade the Java runtime and Tomcat WAR over the weekend:

1. Verify JDK/Servlet API and dependency compatibility.
2. Build a versioned artifact.
3. Deploy to staging on a supported tier or separate environment.
4. Verify health, logs, requests, and database migrations.
5. Swap/release using a supported workflow.
6. Monitor error rates and latency.
7. Outline the rollback plan if a compatibility issue occurs.

### Exercise 6: Cost and operations

A B1 App Service Plan runs one JAR API and one WAR web app. For 12 weekend hours, neither app receives requests. Analyze:

- Why can the plan still incur charges?
- Does stopping one app stop the plan's compute charges?
- Which supporting resources continue generating costs?
- When is sharing a plan reasonable, and when should you separate?
- If the apps must stay up 24/7, how can you optimize costs without breaking SLAs?

### Self-check questions

1. How do a Java SE executable JAR and a Tomcat WAR differ?
2. Why is an ordinary library JAR insufficient to run a Java web service?
3. Which deployment type uses **Main-Class**?
4. Why can Tomcat 9/10 be incompatible when switching from **javax** to **jakarta**?
5. Do an App Service Plan and a Web App serve the same role?
6. Which command lists Linux runtimes currently supported by the Azure CLI?
7. Does a successful deployment prove the API is Healthy?
8. Why must you verify the context path after deploying a WAR?
9. Does VNet Integration automatically block public inbound access to a Web App?
10. How do you grant Key Vault access without hard-coding secrets?
11. Why shouldn't unique uploaded files be written to the app instance's filesystem?
12. Does a slot swap automatically roll back database schemas?
13. Does stopping a Web App drop App Service Plan charges to zero?
14. When scaling out, why can in-memory sessions become a problem?

## 27. References

- [Azure App Service overview — Microsoft Learn](https://learn.microsoft.com/azure/app-service/overview)
- [Configure Java apps for Azure App Service](https://learn.microsoft.com/azure/app-service/configure-language-java)
- [Quickstart: Deploy a Java app to Azure App Service](https://learn.microsoft.com/azure/app-service/quickstart-java)
- [Azure CLI: az webapp deploy](https://learn.microsoft.com/cli/azure/webapp#az-webapp-deploy)
- [Java application deployment to Azure App Service](https://learn.microsoft.com/azure/developer/java/ee/how-to-deploy-to-azure-app-service)
- [Configure App Service application settings](https://learn.microsoft.com/azure/app-service/configure-common)
- [App Service deployment slots](https://learn.microsoft.com/azure/app-service/deploy-staging-slots)
- [App Service VNet integration](https://learn.microsoft.com/azure/app-service/overview-vnet-integration)
- [Use Key Vault references in App Service](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references)
- [Monitor Azure App Service](https://learn.microsoft.com/azure/app-service/monitor-app-service)
- [Azure App Service pricing](https://azure.microsoft.com/pricing/details/app-service/)
