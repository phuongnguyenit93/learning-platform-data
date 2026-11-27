# Choosing Discovery Starters and Reading Gradle or Maven Dependency Trees

## 1. Why Must You Choose the Right Starter?

In Spring Cloud Service Discovery, an application needs a mechanism to register its instance and look up other instances by service name. Spring Cloud provides shared abstractions such as **DiscoveryClient** and **ServiceRegistry**; each concrete discovery system provides the corresponding integration.

When using Eureka, an application needs the Eureka starter matching its role. Eureka Server accepts registrations and provides the registry; Eureka Client registers an instance, renews leases, and looks up services. If using Consul, the application chooses the Consul Discovery starter. A starter is the entry point for a bundle of dependencies and auto-configurations that integrate that system with Spring Boot.

Choosing the right starter gives the project the required libraries and matching auto-configuration. Choosing the wrong starter can leave the application missing functionality, pull in unnecessary libraries, or create version conflicts. Therefore, before writing discovery code, identify the application's role, choose the starter, and inspect the dependency tree resolved by Maven or Gradle.

## 2. Distinguishing Common Starters

Common starters within the scope of service discovery:

| Starter | When to Use? | Primary Role |
|---|---|---|
| **spring-cloud-starter-netflix-eureka-server** | Creating a Eureka Server application | Provides Eureka Server and mechanisms to accept registrations, store the registry, and serve lookups |
| **spring-cloud-starter-netflix-eureka-client** | Application registering with or looking up via Eureka | Integrates Eureka Client with Spring Cloud Discovery |
| **spring-cloud-starter-consul-discovery** | Using Consul as the discovery system | Registers and looks up services through Consul |
| **spring-cloud-starter-loadbalancer** | Application needs to pick one instance from a list of instances | Provides the client-side load balancer |

Not every application needs all of the starters above. A Eureka Server application typically uses the server starter. A business application registering with Eureka uses the client starter. Add LoadBalancer only when the application needs client-side instance selection and no suitable dependency is already provided in the current configuration.

### 2.1. Server and Client Have Two Different Roles

**Eureka Server** maintains the registry and handles registration, renewal, and deregistration operations. A server application typically enables server functionality with the **@EnableEurekaServer** annotation:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.netflix.eureka.server.EnableEurekaServer;

@SpringBootApplication
@EnableEurekaServer
public class DiscoveryServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(DiscoveryServerApplication.class, args);
    }
}
~~~

**Eureka Client** is a business application that wants to publish its own instance or look up other services. When the Eureka Client starter and appropriate endpoint configuration are present, Spring Cloud can auto-configure the Eureka integration. The application can use the **DiscoveryClient** abstraction to look up instances by service ID:

~~~java
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.stereotype.Component;

@Component
public class ServiceLookup {
    private final DiscoveryClient discoveryClient;

    public ServiceLookup(DiscoveryClient discoveryClient) {
        this.discoveryClient = discoveryClient;
    }

    public List<ServiceInstance> findInstances(String serviceId) {
        return discoveryClient.getInstances(serviceId);
    }
}
~~~

Package names and some configuration details may vary by Spring Cloud version. Use a version compatible with your project's Spring Boot and check the documentation for the corresponding release train.

### 2.2. Discovery and Load Balancing Are Not the Same Function

Discovery returns the list of known instances for a service. Load balancing selects one instance from that list for a specific request. For example, **DiscoveryClient** may return three instances of **payment-service**; the client-side load balancer decides which instance the next request goes to.

~~~mermaid
flowchart LR
    APP[Service-calling application] --> DISC[DiscoveryClient]
    DISC --> REG[Eureka or Consul Registry]
    REG --> INST[Instance list]
    INST --> LB[LoadBalancer]
    LB --> TARGET[Selected instance]
~~~

Therefore, do not assume adding the Eureka Client starter means the application already has all load-balancing policies. Inspect the dependency tree and actual configuration to know whether LoadBalancer is present.

## 3. Managing Versions with Spring Cloud BOM

Libraries in Spring Cloud are released on a release train. Modules within the same release train are tested to work with the corresponding Spring Boot versions. Projects should manage versions according to the Spring Boot and Spring Cloud compatibility matrix rather than picking an individual version for each starter.

**BOM (Bill of Materials)** is a collection of metadata managing dependency versions. When importing the Spring Cloud BOM, the project can declare Spring Cloud starters without repeating versions for each dependency. The BOM ensures Spring Cloud modules use aligned versions within the same release train.

Version selection workflow:

1. Identify the Spring Boot version in use.
2. Consult the compatibility matrix to select the Spring Cloud release train supporting that Boot version.
3. Import the BOM of the selected release train.
4. Declare the required starters without specifying individual versions if the BOM already manages them.
5. Inspect the dependency tree and the dependencies actually selected by Maven or Gradle.

Do not pick a release train just because it is the latest version. The latest version may require a different Spring Boot line than your current project.

## 4. Declaring Dependencies with Maven

### 4.1. Importing Spring Cloud BOM

In **pom.xml**, declare the release train in properties and import the BOM in **dependencyManagement**. Replace the placeholder value with a release train compatible with your project's Spring Boot version:

~~~xml
<properties>
    <java.version>17</java.version>
    <spring-cloud.version>REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

The value **REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN** is a placeholder where a real version must be filled in, not a valid version to keep in the project.

### 4.2. Choosing Dependencies for Eureka Server

For a project acting solely as a Eureka Server, the core dependencies are:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-server</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

The Eureka Server starter provides the server integration. The web starter is declared so the application serves the UI and HTTP endpoints via Spring MVC in this example. Depending on the version and packaging, inspect the pulled-in dependencies before adding duplicate libraries.

### 4.3. Choosing Dependencies for Eureka Client

For a business application registering with Eureka:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
</dependencies>
~~~

The web starter here serves the business application's HTTP API. It is not a core component of discovery; the application may use a different communication style if the architecture requires it.

You do not need to declare both the server starter and client starter in every application. Only include both when intentionally building a process that runs both Eureka Server and acts as a Eureka Client in a specialized architecture.

### 4.4. Choosing Consul Instead of Eureka

If the system uses Consul as its registry, the commonly used starter is:

~~~xml
<dependency>
    <groupId>org.springframework.cloud</groupId>
    <artifactId>spring-cloud-starter-consul-discovery</artifactId>
</dependency>
~~~

Do not add both Eureka Client and Consul Discovery at the same time just as a fallback without a clear design. When multiple discovery clients are enabled, the application may register or perform lookups across multiple systems, complicating operations and determining the source of truth.

## 5. Declaring Dependencies with Gradle

Gradle can import a BOM using a dependency platform. The following example uses Groovy DSL in **build.gradle**:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version 'REPLACE_WITH_COMPATIBLE_BOOT_VERSION'
}

ext {
    springCloudVersion = 'REPLACE_WITH_COMPATIBLE_RELEASE_TRAIN'
}

dependencies {
    implementation platform(
        'org.springframework.cloud:spring-cloud-dependencies:' + springCloudVersion
    )

    implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-client'
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Replace both placeholders with compatible Spring Boot and Spring Cloud versions. If the project already has a dependency management plugin or convention, follow the project's existing mechanism rather than adding a second version management approach.

For Eureka Server, replace the Eureka Client dependency with:

~~~groovy
implementation 'org.springframework.cloud:spring-cloud-starter-netflix-eureka-server'
~~~

For Consul Discovery, use:

~~~groovy
implementation 'org.springframework.cloud:spring-cloud-starter-consul-discovery'
~~~

Gradle Kotlin DSL (**build.gradle.kts**) has different syntax, but the principle remains the same: import the BOM via **platform(...)**, then declare the starters in **dependencies**.

## 6. How to Read a Dependency Tree

A dependency tree describes the direct dependencies and transitive dependencies resolved by the build tool for the project. When adding a starter, the project usually receives many underlying libraries rather than a single artifact.

Conceptual diagram example:

~~~text
payment-service
└── spring-cloud-starter-netflix-eureka-client
    ├── Spring Cloud Eureka integration
    ├── Spring Cloud Commons / Context
    ├── Netflix Eureka Client
    └── related foundational libraries
~~~

This is a conceptual diagram explaining relationships, not a fixed list of dependencies. The actual tree depends on the release train, starter version, other project dependencies, and Maven or Gradle resolution rules.

When reading the tree, distinguish between:

- **Direct dependency:** a dependency declared directly in the build file.
- **Transitive dependency:** a dependency pulled in by another dependency.
- **Version constraint or version management:** rules constraining or managing the selected version.
- **Conflict resolution:** how the build tool picks one version when multiple branches request different versions.
- **Exclusion:** a rule removing a transitive dependency from a specific branch.

A starter can pull in shared Spring Cloud libraries. If a library appears multiple times across branches, that does not automatically mean the runtime will package multiple copies of the same artifact. Maven and Gradle perform resolution to select the effective dependency according to their rules.

## 7. Viewing the Dependency Tree with Maven

### 7.1. Printing the Entire Tree

Run in the directory containing **pom.xml**:

~~~bash
mvn dependency:tree
~~~

The output displays dependencies in a tree format, including parent-child relationships and selected versions.

### 7.2. Filtering Dependencies Related to Spring Cloud and Eureka

~~~bash
mvn dependency:tree -Dincludes=org.springframework.cloud:*,com.netflix.eureka:*
~~~

The filter command helps focus on artifacts related to Spring Cloud and Eureka. If you need to understand why a version was selected, use verbose mode:

~~~bash
mvn dependency:tree -Dverbose
~~~

### 7.3. Checking the POM After Applying the BOM

~~~bash
mvn help:effective-pom
~~~

The effective POM is the POM after Maven applies the parent, properties, dependency management, and inherited configurations. This is a useful place to inspect BOM-managed versions and inherited settings that the current **pom.xml** does not show directly.

If the build fails to resolve dependencies, check:

1. Whether the BOM is imported properly in dependencyManagement.
2. Whether the Spring Cloud release train version is compatible with Spring Boot.
3. Whether the groupId and artifactId names are exact.
4. Whether the Maven repository is reachable and the artifact is published.
5. Whether any parent or profile dependency management overrides the version.

## 8. Viewing the Dependency Tree with Gradle

### 8.1. Printing the Runtime Dependency Tree

With Gradle Wrapper on Linux or macOS:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

On Windows:

~~~powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
~~~

**runtimeClasspath** shows the dependencies needed when running the application. If you want to see dependencies used for compiling source code, inspect **compileClasspath**. The two configurations can differ because some dependencies are needed only at compile time or only at runtime.

### 8.2. Finding Why a Dependency Was Selected

~~~bash
./gradlew dependencyInsight --dependency spring-cloud-starter-netflix-eureka-client --configuration runtimeClasspath
~~~

**dependencyInsight** focuses on a single dependency, showing where it was introduced from and why its version was chosen. This command is useful when multiple modules request an artifact or when a constraint affects the resolution result.

### 8.3. Reading Gradle Output

When examining the output, pay attention to:

- Which branch brings the starter into the runtime classpath.
- The originally requested version and the actual selected version.
- Which dependencies are replaced or upgraded due to constraints/platforms.
- Whether any lines show a dependency not selected, excluded, or unresolvable.
- Whether the starter pulls in libraries overlapping in role with directly declared dependencies.

If using a multi-module build, run the command with the right project path or module. The root project's tree does not necessarily represent the classpath of the service being checked.

## 9. Example of Analyzing a Dependency Tree

Suppose an application has the following direct dependencies:

~~~text
spring-boot-starter-web
spring-cloud-starter-netflix-eureka-client
spring-cloud-starter-loadbalancer
~~~

When inspecting the tree, we can ask:

1. Does the Eureka Client starter appear in the runtime classpath?
2. Which version of the Eureka Client artifact is actually pulled in?
3. Are Spring Cloud Commons and foundational libraries aligned with the BOM?
4. Is LoadBalancer present due to a direct dependency or pulled in by another starter?
5. Do two release trains or multiple versions of the same Spring Cloud module appear in the tree?

If the tree shows inconsistent Spring Cloud versions, check the BOM and dependency management first. Do not rush to add exclusions or force versions manually, as doing so can mask the root cause and produce a combination of libraries not tested together.

### 9.1. When Should Exclusions Be Used?

Exclusions are useful when a specific transitive dependency is genuinely unsuitable and the project has a compatible alternative. Maven syntax example:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>library-a</artifactId>
    <version>1.0.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>library-b</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

This is merely a syntax example with hypothetical coordinates, not a recommendation to exclude a specific Eureka dependency. Before using an exclusion, identify which dependency needs to be removed, which dependency will replace it, and test startup, registration, heartbeat, and service lookup flows.

## 10. Starter Selection and Dependency Verification Workflow

The following workflow can be applied to each service:

1. **Identify the role:** is the service a Eureka Server, a Eureka Client, or an application using Consul?
2. **Choose the starter:** add only the starter matching that role; consider LoadBalancer based on service-calling needs.
3. **Choose foundational versions:** match Spring Boot against the Spring Cloud release train.
4. **Import the BOM:** let the BOM manage the versions of Spring Cloud modules.
5. **Declare dependencies:** avoid specifying individual versions for starters already managed by the BOM.
6. **Print the dependency tree:** check direct and transitive dependencies in the target classpath.
7. **Investigate conflicts:** use effective POM or dependencyInsight to find version sources and constraints.
8. **Verify the application:** build, start up, and test registration or lookup through the registry.

| Symptom | Likely Areas to Check |
|---|---|
| Eureka Server class not found | Missing server starter or dependency not on the classpath |
| No instances in the registry | Client starter, endpoint, registration config, or server connectivity |
| Build reports artifact not found | Incorrect coordinates, version, BOM, or repository |
| Compatibility error at startup | Spring Boot and Spring Cloud release train incompatibility |
| Missing class at runtime despite successful compilation | Dependency scope/configuration or runtime classpath |
| Dependency tree shows unexpected version | BOM, parent, constraint, conflict resolution, or directly declared dependency |

## 11. Summary

Starters determine the service discovery integration an application needs: Eureka Server, Eureka Client, or Consul Discovery. **DiscoveryClient** provides the abstraction for looking up instances; LoadBalancer handles picking an instance for a request and is a separate feature whose dependency should be verified accordingly.

With Maven or Gradle, import the Spring Cloud BOM compatible with Spring Boot and declare starters without manually setting versions when the BOM already manages them. Commands such as **mvn dependency:tree**, **mvn help:effective-pom**, **gradlew dependencies**, and **dependencyInsight** help identify direct dependencies, transitive dependencies, and the effective selected versions. Reading the dependency tree before resolving conflicts gives the project a clean classpath and reduces risks when deploying service discovery.
