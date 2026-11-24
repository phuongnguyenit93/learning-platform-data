# Exploring Beans, Bean Types, and Dependencies with the beans Endpoint

## 1. From source code to components actually managed by Spring

Having an `OrderService` class in source code does not answer: did the running application register that bean, which implementation class does the bean use, and which components did Spring wire into it?

A **bean** is an object managed by the Spring container. An **ApplicationContext** is the application context holding configurations and those components. A **bean name** is the name used to identify a bean within a container; a **bean type** is the Java type Spring determines for the bean. A bean can have additional names called **aliases**. Bean name and class name are two different pieces of information. See [Spring Framework BeanFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/BeanFactory.html).

In this lesson, we use `GET /actuator/beans` to verify three things:

1. Does the target bean appear in the observed context?
2. What are its name, aliases, and Java type?
3. Which beans does it depend on; conversely, which beans depend on it?

This is a tool for reading the application's component structure. For example, when a test configuration uses an in-memory repository while a deployment configuration uses a real repository, we can verify which component is registered before guessing from class names.

## 2. Enabling the right endpoint and understanding the response structure

The lab uses Spring Boot **3.3.0**, Java **21**, and Gradle **8.5** to establish a concrete set of versions. The Spring Boot 3.3 documentation links below describe the 3.3 line; do not mix configuration properties from newer lines into this example.

With Boot 3.3, `beans` is enabled by default but not exposed over HTTP by default. You need Actuator and to add `beans` to `management.endpoints.web.exposure.include`. If general configuration disabled endpoints, set `management.endpoint.beans.enabled=true`. `exclude` takes precedence over `include`. See [Spring Boot 3.3 endpoint configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#exposing-endpoints).

The default path is `/actuator/beans`; port, application context path, management port, and base-path changes can make the actual URL differ. The example below uses a single port and keeps the default paths.

The response is a JSON object with the following structure:

| Component | How to read |
| --- | --- |
| `contexts` | Set of described contexts, keyed by context ID. |
| `contexts.<id>.parentId` | Parent context ID, if any. |
| `contexts.<id>.beans` | Set of beans in the context, keyed by bean name. |
| `aliases` | Aliases of the bean. |
| `scope` | Bean management scope. |
| `type` | Fully qualified Java type name. |
| `resource` | Resource where the bean is defined, if any. |
| `dependencies` | Names of beans that this bean depends on. |

These are the fields of the [Spring Boot 3.3 beans API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/beans.html). Do not write tools that only read `contexts.application`: context IDs are data to discover.

## 3. Hands-on with a small standalone application

Create a separate project for the lab with this structure:

~~~text
beans-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/example/BeansLabApplication.java
    └── resources/application.properties
~~~

### 3.1. Project declaration and dependencies

Contents of `settings.gradle`:

~~~groovy
rootProject.name = 'beans-lab'
~~~

Contents of `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}
~~~

`spring-boot-starter-web` provides the HTTP server; `spring-boot-starter-actuator` provides the management endpoints. This project needs no database or separate business API to observe beans.

### 3.2. Lab scope configuration

Contents of `src/main/resources/application.properties`:

~~~properties
spring.application.name=beans-lab
server.address=127.0.0.1
server.port=8080
management.endpoints.web.exposure.include=health,beans
management.endpoint.beans.enabled=true
~~~

The example server listens only on the loopback address. The example does not add Spring Security, so HTTP requests from the local machine require no login.

On applications with Spring Security, exposing an endpoint and granting access are two separate steps. Do not copy open-access configuration into deployment environments: the response can expose class names, component structure, and configuration sources. See [Securing Actuator in Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#security).

### 3.3. Registering beans, aliases, and a dependency

Complete `src/main/java/example/BeansLabApplication.java`:

~~~java
package example;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication(proxyBeanMethods = false)
public class BeansLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(BeansLabApplication.class, args);
    }

    @Bean(name = {"orderRepository", "repoAlias"})
    OrderRepository orderRepository() {
        return new MemoryOrderRepository();
    }

    @Bean
    OrderService orderService(
            @Qualifier("orderRepository") OrderRepository repository) {
        return new OrderService(repository);
    }
}

interface OrderRepository {
    long count();
}

class MemoryOrderRepository implements OrderRepository {
    @Override
    public long count() {
        return 7L;
    }
}

class OrderService {
    private final OrderRepository repository;

    OrderService(OrderRepository repository) {
        this.repository = repository;
    }

    public long countOrders() {
        return repository.count();
    }
}
~~~

In this file:

- `orderRepository` is the primary bean name; `repoAlias` is an alias for that same bean.
- The factory method declares return type `OrderRepository`, while the created object is `MemoryOrderRepository`.
- Spring passes the repository bean into the `orderService(...)` method parameter; that method forwards it to the `OrderService` constructor.
- `@Qualifier("orderRepository")` explicitly specifies the choice at the injection point.
- Both `@Bean` methods are instance methods on the `beansLabApplication` configuration bean.

`proxyBeanMethods=false` fits here because the `@Bean` methods do not call one another directly; they receive dependencies as parameters. Package-private classes are placed in the same file to keep the example compact and compilable; when organizing larger projects you can split them into separate files.

### 3.4. Running and fetching data

If the machine already has Gradle 8.5, stand in the `beans-lab` directory to generate the wrapper once:

~~~powershell
gradle wrapper --gradle-version 8.5
~~~

Then run on Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

On Linux/macOS use `./gradlew bootRun`. The first run needs to download Gradle and dependencies. `bootRun` uses the application's classpath; do not run `javac BeansLabApplication.java` standalone because this file requires Spring libraries. See [Running applications with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html).

Once the application has started, open another PowerShell window:

~~~powershell
$response = Invoke-RestMethod -Uri 'http://127.0.0.1:8080/actuator/beans'
$response.contexts.PSObject.Properties.Name
~~~

You can download the raw response with `curl.exe` on Windows:

~~~powershell
curl.exe --fail --silent --show-error 'http://127.0.0.1:8080/actuator/beans' --output beans.json
~~~

The portion of the response covering the two beans in this lesson looks like this. Other beans are omitted from the illustration; key ordering and dependency element order are not a contract to rely on:

~~~json
{
  "contexts": {
    "beans-lab": {
      "beans": {
        "orderRepository": {
          "aliases": ["repoAlias"],
          "scope": "singleton",
          "type": "example.MemoryOrderRepository",
          "resource": "example.BeansLabApplication",
          "dependencies": ["beansLabApplication"]
        },
        "orderService": {
          "aliases": [],
          "scope": "singleton",
          "type": "example.OrderService",
          "resource": "example.BeansLabApplication",
          "dependencies": [
            "beansLabApplication",
            "orderRepository"
          ]
        }
      }
    }
  }
}
~~~

The fields of these two beans were verified against Boot 3.3.0's `BeansEndpoint`. When changing how beans are declared or how the application is packaged, the `resource` description may change.

## 4. Reading names, types, and scopes without over-inferring

### Primary name and aliases

The key `orderRepository` identifies the bean in the `beans` map. The alias `repoAlias` sits inside the `aliases` array; there is no standalone JSON entry keyed by `repoAlias`.

Both names look up the exact same bean. Therefore, counting an alias as a new bean will distort the count. When searching by name, check both the bean key and the aliases list.

### Java type

In the initialized example, `type` is `example.MemoryOrderRepository`. The injection point still uses the `OrderRepository` interface. That is normal: the type requested at the dependency site and the described type of the bean do not have to be identical strings.

A class can implement multiple interfaces, yet `type` is not a list of those interfaces. Consequently, string-filtering by exact interface name can miss matching beans. If you need to verify type assignability in code, use APIs like `isTypeMatch` or `getBeanNamesForType`, instead of inferring solely from string comparisons. See [BeanFactory: checking type](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/BeanFactory.html#isTypeMatch(java.lang.String,java.lang.Class)) and [ListableBeanFactory: finding by type](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/ListableBeanFactory.html#getBeanNamesForType(java.lang.Class)).

With proxies or `FactoryBean`, inspect the type Spring resolves in that concrete scenario. Do not assume `type` is always the class written in source code, nor assume it is always a proxy class name. In Boot 3.3.0, the endpoint retrieves the type via `BeanFactory.getType(beanName)`.

### Scope and defining resource

`singleton` means one shared object per bean in the corresponding container. Two differently named beans can share the same Java type; matching type names do not prove they are the same object. `prototype` denotes a mechanism providing a new object each time the bean is requested; endpoint data is not a list of all prototype instances ever created. See [Spring bean scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html).

`resource` helps trace back to the configuration declaring the bean. It is not the values of properties inside the object, not a business API path, and not the full source code. The example above returns the configuration class name; this field may be absent when no resource description is available.

## 5. Analyzing dependency direction correctly

For the `orderService` entry, the `dependencies` array contains `orderRepository`. Read it as:

~~~text
orderService ──depends on──> orderRepository
~~~

Do not flip it to "orderRepository needs orderService".

The data also shows edges from both beans to `beansLabApplication`. That is the configuration bean holding their factory methods. Thus, the dependency list can include components involved in bean creation alongside the business collaborators injected into it.

Boot 3.3.0 obtains these names from `getDependenciesForBean`. The reverse direction in Spring is `getDependentBeans`: beans that depend on the queried bean. See [ConfigurableBeanFactory](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html#getDependenciesForBean(java.lang.String)).

There are three limits to keep in mind when analyzing a graph:

- **Direct dependencies differ from transitive dependencies.** If A has B in its array and B has C, you must take an extra step to deduce the path A → B → C; do not demand that C appear directly in A's array.
- **Container-recorded relationships differ from method call flows.** The data does not tell which HTTP request called which method, how many times, or how long it took.
- **The graph does not represent every Java reference.** Objects created directly via `new`, lazy lookups, or links formed outside dependency registration need additional evidence. An empty array only states that this description returned no recorded dependency names.

An edge also does not prove the bean is healthy or frequently used. Answering those questions requires functional tests or other observability tools.

## 6. Practical queries with PowerShell

This section uses PowerShell 5.1+ or 7 and the `$response` object retrieved above. These queries run on the client reading the data; they do not create additional endpoints.

First transform each JSON entry into an easily filterable record while keeping the context ID to avoid name ambiguity:

~~~powershell
$rows = @(
    foreach ($context in $response.contexts.PSObject.Properties) {
        foreach ($entry in $context.Value.beans.PSObject.Properties) {
            [pscustomobject]@{
                Context      = $context.Name
                Name         = $entry.Name
                Aliases      = @($entry.Value.aliases)
                Scope        = $entry.Value.scope
                Type         = $entry.Value.type
                Resource     = $entry.Value.resource
                Dependencies = @($entry.Value.dependencies)
            }
        }
    }
)
~~~

### 6.1. Searching by primary name or alias

~~~powershell
$wanted = 'repoAlias'
$rows |
    Where-Object { $_.Name -ceq $wanted -or $_.Aliases -ccontains $wanted } |
    Select-Object Context, Name, Type, Scope
~~~

For this example, the matched record carries primary name `orderRepository`, type `example.MemoryOrderRepository`, and scope `singleton`.

Use `-ceq` and `-ccontains` for case-sensitive comparisons matching Java bean names. PowerShell's default comparison operators are case-insensitive.

### 6.2. Filtering by reported type

~~~powershell
$rows |
    Where-Object { $_.Type -ceq 'example.MemoryOrderRepository' } |
    Select-Object Context, Name, Type
~~~

To survey beans belonging to the example's code:

~~~powershell
$rows |
    Where-Object { $_.Type -clike 'example.*' } |
    Sort-Object Context, Name |
    Select-Object Context, Name, Type, Scope
~~~

This is string filtering on type names; it does not perform inheritance or interface implementation checks.

### 6.3. Finding dependencies of orderService

Retrieve exactly one record in this single-context example:

~~~powershell
$service = @($rows | Where-Object { $_.Name -ceq 'orderService' })
if ($service.Count -ne 1) {
    throw 'Must select exactly one context containing orderService.'
}
$service[0].Dependencies | Sort-Object
~~~

Sorted output for the example:

~~~text
beansLabApplication
orderRepository
~~~

In systems with multiple contexts, add a `Context` filter taken from actual data before selecting a record.

### 6.4. Finding beans that depend on orderRepository

~~~powershell
$rows |
    Where-Object { $_.Dependencies -ccontains 'orderRepository' } |
    Sort-Object Context, Name |
    Select-Object Context, Name, Type
~~~

In the sample application, the query finds `orderService`. This reverses existing edges in the response, rather than invoking a write operation on Spring.

If multiple contexts contain the name `orderRepository`, results must be interpreted alongside parent–child context relationships; each string in `dependencies` does not carry a target context ID. Do not merge everything by name and treat it as a single unambiguous graph.

### 6.5. Exporting an edge list for further analysis

~~~powershell
$edges = @(
    foreach ($row in $rows) {
        foreach ($dependency in $row.Dependencies) {
            [pscustomobject]@{
                Context   = $row.Context
                Bean      = $row.Name
                DependsOn = $dependency
            }
        }
    }
)
$edges |
    Sort-Object Context, Bean, DependsOn |
    Format-Table -AutoSize
~~~

Each row represents `Bean → DependsOn`. When traversing multiple hops, traversal tools must maintain a visited set to avoid infinite loops. Do not treat JSON array order as initialization order or execution order.

## 7. Troubleshooting unexpected results

### Cannot call the endpoint

Check in brief order:

1. Has the application started and does the URL match the actual management port/path?
2. Were Actuator added, `beans` enabled, and HTTP exposure configured?
3. Is an `exclude` setting or security rule blocking access?

`401` or `403` suggests checking authentication/authorization; `404` requires checking the URL, endpoint enablement and exposure, as well as application or proxy rules. Do not conclude "the bean does not exist" simply because you have not yet retrieved the JSON document.

The built-in endpoint in this lesson is `GET /actuator/beans`. Do not assume `/actuator/beans/orderService` or a `?name=orderService` filter exists; fetch the document and filter client-side as shown in Section 6.

### Endpoint succeeds, but the bean is missing

First search primary names, aliases, and all returned contexts. Then check bean declaration code, component-scan scope, and configuration conditions.

Specifically, the `BeansEndpoint` implementation in **3.3.0** has important observation limits:

- It iterates over names having a `BeanDefinition`; a manually registered singleton without a corresponding definition is outside that iteration set.
- Definitions carrying role `ROLE_INFRASTRUCTURE` are excluded from the list.
- For lazy-initialized definitions, the endpoint includes them only once the container holds the corresponding singleton.

These points were verified directly against the implementation in `spring-boot-actuator:3.3.0`; re-verify when changing versions. Therefore, not seeing an uninitialized lazy bean is insufficient to conclude it was not declared. Do not proactively invoke `getBean` en masse just to build a "complete" list: that action can initialize components intentionally kept lazy.

If the application fails during context creation, read startup errors and conditional configurations; do not expect that application's HTTP endpoint to work to explain the failure.

### Bean exists, but implementation or dependencies differ from expectations

For this example, if `orderRepository` is found but `type` is no longer `MemoryOrderRepository`, compare the running configuration and bean definition location before modifying `OrderService`.

If multiple beans satisfy an interface, the `beans` list alone does not fully describe selection rules at each injection point. Cross-check `@Qualifier`, `@Primary`, requested types, and configuration declarations. If the context failed to start due to ambiguous dependencies, use startup errors as evidence.

`conditions` helps explain conditional configuration; `env` and `configprops` serve value-configuration questions; `health` serves health status. Pick the tool according to the question rather than using the bean list to replace every diagnostic check.

## 8. Verification exercises and self-check guide

**Exercise 1 — Name and alias.** Search for `repoAlias` using query 6.1. Explain why the result carries the name `orderRepository`.

Check: an alias is an alternate name for the same bean; it does not require a new bean record.

**Exercise 2 — Declared type vs. described type.** Compare the return type of the `orderRepository()` method with the `type` field.

Check: the method declares the `OrderRepository` interface; in the initialized example, Spring describes `example.MemoryOrderRepository`. Do not infer that the interface is a second bean.

**Exercise 3 — Both directions of a relationship.** Run queries 6.3 and 6.4, then draw the edges involving the two business beans.

Check:

~~~text
orderService ────────> orderRepository
      │                      │
      └──────────┬───────────┘
                 v
       beansLabApplication
~~~

Edges to the configuration bean stem from creating beans via `@Bean` instance methods. Reverse-querying finds `orderService` from `orderRepository`.

**Exercise 4 — Controlled alias change.** Change `repoAlias` alone to `storageAlias`, restart, fetch a fresh response, and search again by the new name.

Check: primary name, type, and business dependency remain unchanged; the alias array reflects the new name. You must use fresh data after restarting instead of re-filtering the stale `$response` variable.

**Exercise 5 — Conclusions from evidence.** A response lacks the expected bean, or contains the bean with an empty dependencies array. State the next checks before drawing conclusions.

Check: confirm context, registration mechanism, lazy initialization status, and observation limits; an empty array does not prove the object collaborates with no Java objects at all.

After this lesson, the practical goal is to read a bean entry, distinguish name from type, trace dependency direction accurately, and clearly state the limits of conclusions drawn from the response.
