# List Indices in Environment Variable Names

## 1. Why do list indices need a special syntax?

Spring Boot supports **externalized configuration**: the same application can load configuration from **application.yml**, **application.properties**, environment variables, system properties, or startup arguments. When configuration has only single values like **server.port**, environment variable naming is relatively easy to remember:

~~~text
server.port       -> SERVER_PORT
app.service-url   -> APP_SERVICEURL
~~~

But what if the configuration contains a **list**? In YAML files, we usually declare multiple elements with bullet dashes. In **.properties** files, elements usually have an index in square brackets like **app.targets[0].url**. Operating system environment variables typically only accept letters, digits, and underscores; characters like **[**, **]**, dot **.**, and hyphen **-** are unsuitable for standard environment variable naming.

Therefore, **Spring Boot relaxed binding** defines a specific rule:

> When binding a **List** from environment variables, the element's index is placed between underscores.

Key example:

~~~text
Property:         app.targets[0].url
Environment var:  APP_TARGETS_0_URL

Property:         app.targets[1].url
Environment var:  APP_TARGETS_1_URL
~~~

The numbers **0** and **1** are **list element indices**, starting from 0, not ordinary property name segments. Keeping underscores before and after the index helps the **Binder** identify the boundaries between the list name, the element, and the fields inside the element.

## 2. Rules for converting properties to environment variables

For a property name in canonical form (*canonical name*, usually written in lowercase with hyphens for compound words), Spring Boot instructs:

1. Replace dots **.** between name parts with underscores **_**.
2. **Remove** hyphens **-** inside property names.
3. Convert letters to **UPPERCASE**.
4. For a **List** element, convert index **[n]** to **_n_** in the corresponding position.

Examples:

| Property name | Corresponding environment variable |
| --- | --- |
| **app.name** | **APP_NAME** |
| **app.service-url** | **APP_SERVICEURL** |
| **app.targets[0]** | **APP_TARGETS_0** |
| **app.targets[0].name** | **APP_TARGETS_0_NAME** |
| **app.targets[0].url** | **APP_TARGETS_0_URL** |
| **app.targets[1].url** | **APP_TARGETS_1_URL** |
| **app.service-pool[2].connect-timeout** | **APP_SERVICEPOOL_2_CONNECTTIMEOUT** |
| **my.service[0].other** | **MY_SERVICE_0_OTHER** |
| **app.regions[3]** | **APP_REGIONS_3** |

Pay attention to two easily confused forms:

~~~text
app.service-pool[2].connect-timeout
  -> APP_SERVICEPOOL_2_CONNECTTIMEOUT
~~~

Hyphens in **service-pool** and **connect-timeout** are **removed**, while underscores are used to separate **property levels** and **indices**.

**APP_SERVICE_POOL_2_CONNECT_TIMEOUT** looks readable, but it is not the canonical conversion of the two segments **service-pool** and **connect-timeout** according to the rule above. If an environment variable fails to bind as expected, first check whether you inserted extra underscores inside a kebab-case name.

### 2.1. The _ before and after the number is not [0] syntax

The name **APP_TARGETS_0_URL** represents:

~~~text
APP         -> app
TARGETS     -> targets
0           -> [0], first element
URL         -> url, field of the first element
~~~

For an element of a scalar list, such as **app.regions[0]**, the variable name ends with the number:

~~~text
app.regions[0]  -> APP_REGIONS_0
app.regions[1]  -> APP_REGIONS_1
~~~

Do not add a trailing underscore at the end of the variable because there is no following field. Saying "the index is surrounded by underscores" means the number must be separated from adjacent segments; at the end of a variable name, you do not generate an empty segment.

### 2.2. Nested lists

Example of a list of groups, where each group has a list of servers:

~~~text
app.groups[0].servers[1].host
  -> APP_GROUPS_0_SERVERS_1_HOST
~~~

Each list element has its own index. The Binder reads **groups[0]**, then **servers[1]**, and then the **host** field.

In real applications, if a structure becomes too deeply nested, consider splitting configuration into more manageable groups. Even so, the naming conversion rule remains consistent.

## 3. The same list in YAML, properties, and environment variables

Suppose an application defines two fallback endpoints.

**application.yml**:

~~~yaml
app:
  targets:
    - name: primary
      url: https://primary.example.invalid
    - name: backup
      url: https://backup.example.invalid
~~~

Spring Boot converts the YAML structure into equivalent property paths:

~~~properties
app.targets[0].name=primary
app.targets[0].url=https://primary.example.invalid
app.targets[1].name=backup
app.targets[1].url=https://backup.example.invalid
~~~

If you need to provide **the same list** via environment variables, use:

~~~text
APP_TARGETS_0_NAME=primary
APP_TARGETS_0_URL=https://primary.example.invalid
APP_TARGETS_1_NAME=backup
APP_TARGETS_1_URL=https://backup.example.invalid
~~~

Comparison table:

| Element | YAML | .properties | Environment |
| --- | --- | --- | --- |
| Name of element 0 | **targets[0].name** | **app.targets[0].name** | **APP_TARGETS_0_NAME** |
| URL of element 0 | **targets[0].url** | **app.targets[0].url** | **APP_TARGETS_0_URL** |
| Name of element 1 | **targets[1].name** | **app.targets[1].name** | **APP_TARGETS_1_NAME** |
| URL of element 1 | **targets[1].url** | **app.targets[1].url** | **APP_TARGETS_1_URL** |

In the YAML column, **targets[0].name** is the relative path under the shown **app** branch; the full property path is still **app.targets[0].name**.

The **.invalid** values are purely illustrative. They are not real endpoints and require no network connection to observe configuration.

## 4. Java example: binding to a List with @ConfigurationProperties

**@ConfigurationProperties** is the Spring Boot-supported way to map structured configuration to a Java object. It fits lists of objects much better than writing numerous **@Value** annotations per index.

Suppose the application uses Java 21, Spring Boot 3.3.x, and **spring-boot-starter-web**.

### 4.1. Registering @ConfigurationProperties scanning

~~~java
package com.example.listenv;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ListEnvApplication {
    public static void main(String[] args) {
        SpringApplication.run(ListEnvApplication.class, args);
    }
}
~~~

### 4.2. Declaring the configuration type

~~~java
package com.example.listenv;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Target> targets) {

    public record Target(String name, String url) {
    }
}
~~~

**Explanation:**

- **prefix = "app"** instructs binding of keys under the **app** branch.
- **targets** maps to a **List<Target>**.
- Each **Target** has two properties: **name** and **url**.
- Spring Boot supports constructor binding with **record** types via configuration property scanning in this case.
- Variable **APP_TARGETS_0_NAME** supplies the **name** field of the first element, while **APP_TARGETS_1_URL** supplies the **url** field of the second element.

If the project uses a regular JavaBean class instead of a record, getters/setters and suitable binding configuration can also be used. The core point is that the binder receives a **List**, so it can interpret the index expressed in the environment variable names.

### 4.3. An endpoint to observe the result

~~~java
package com.example.listenv;

import java.util.List;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class TargetController {

    private final AppProperties properties;

    public TargetController(AppProperties properties) {
        this.properties = properties;
    }

    @GetMapping("/targets")
    public List<AppProperties.Target> targets() {
        return properties.targets();
    }
}
~~~

**src/main/resources/application.yml**:

~~~yaml
server:
  port: 8080

app:
  targets:
    - name: built-in-primary
      url: https://built-in-primary.example.invalid
    - name: built-in-backup
      url: https://built-in-backup.example.invalid
~~~

When running without overriding environment variables, call:

~~~bash
curl http://localhost:8080/targets
~~~

Illustrative output:

~~~json
[
  {
    "name": "built-in-primary",
    "url": "https://built-in-primary.example.invalid"
  },
  {
    "name": "built-in-backup",
    "url": "https://built-in-backup.example.invalid"
  }
]
~~~

This is the YAML data, bound via **@ConfigurationProperties** and returned by the controller.

In real applications, do not build a public API to expose sensitive properties. The example uses a simple endpoint with dummy names and URLs only so learners can observe the result.

## 5. Replacing an entire List via environment variables

Build the application once with the Gradle wrapper:

~~~bash
./gradlew bootJar
~~~

Assume the artifact is named **app.jar**; if Gradle generates a different name, substitute the actual JAR name.

### 5.1. Linux/macOS: passing variables to a Java process

~~~bash
APP_TARGETS_0_NAME=prod-primary \
APP_TARGETS_0_URL=https://prod-primary.example.invalid \
APP_TARGETS_1_NAME=prod-backup \
APP_TARGETS_1_URL=https://prod-backup.example.invalid \
java -jar app.jar
~~~

Once the application is running, call:

~~~bash
curl http://localhost:8080/targets
~~~

Illustrative output:

~~~json
[
  {
    "name": "prod-primary",
    "url": "https://prod-primary.example.invalid"
  },
  {
    "name": "prod-backup",
    "url": "https://prod-backup.example.invalid"
  }
]
~~~

This command supplies environment variables only to the Java process launched in the shell example. It does not modify the YAML inside the JAR and requires no rebuild.

### 5.2. PowerShell: setting variables for a shell session

~~~powershell
$env:APP_TARGETS_0_NAME = "local-primary"
$env:APP_TARGETS_0_URL = "https://local-primary.example.invalid"
$env:APP_TARGETS_1_NAME = "local-backup"
$env:APP_TARGETS_1_URL = "https://local-backup.example.invalid"

java -jar app.jar
~~~

PowerShell allows assigning string values to variables whose names contain letters, digits, and underscores. These variables are present in the environment of the Java process launched from that shell.

If you want to test the case **without** overriding environment variables on a subsequent run, unset the variables you set or open a new shell. Otherwise, Spring Boot may continue reading the old values.

### 5.3. Docker: each element as an -e variable

~~~bash
docker run --rm -p 8080:8080 \
  -e APP_TARGETS_0_NAME=container-primary \
  -e APP_TARGETS_0_URL=https://container-primary.example.invalid \
  -e APP_TARGETS_1_NAME=container-backup \
  -e APP_TARGETS_1_URL=https://container-backup.example.invalid \
  my-list-env:1.0.0
~~~

The example assumes the image **my-list-env:1.0.0** has been built from the application above and runs a Java process reading Spring Boot configuration. The order of **-e** options in the Docker command does not determine list order; the **_0_**, **_1_** indices in the **variable names** determine it.

## 6. Scalar lists: List<String> is even simpler

Not every list contains objects. For example, suppose the application needs a list of regions:

**application.yml**:

~~~yaml
app:
  regions:
    - asia
    - europe
    - america
~~~

Equivalent properties:

~~~properties
app.regions[0]=asia
app.regions[1]=europe
app.regions[2]=america
~~~

Environment variables:

~~~text
APP_REGIONS_0=asia
APP_REGIONS_1=europe
APP_REGIONS_2=america
~~~

**There is no trailing _REGION_** because the list element itself is the value, not an object with child fields.

Java type:

~~~java
package com.example.listenv;

import java.util.List;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app")
public record RegionProperties(List<String> regions) {
}
~~~

Note when using this standalone snippet alongside the previous **AppProperties**: both classes use the prefix **app**, though each only binds the fields declared in its own record. To build a complete application, you can group fields into a single configuration record or assign separate prefixes per group as needed.

### 6.1. Lists with various value types

Spring Boot also binds types such as integers, booleans, durations, enums, or nested objects through the appropriate **ConversionService** mechanism.

Example:

~~~yaml
app:
  retry-delays:
    - 1s
    - 5s
    - 30s
~~~

The corresponding environment variable names are:

~~~text
APP_RETRYDELAYS_0=1s
APP_RETRYDELAYS_1=5s
APP_RETRYDELAYS_2=30s
~~~

The Java type can be **List<Duration>** if the configuration is bound via **@ConfigurationProperties** and duration values are converted by Spring Boot. The strings **1s**, **5s**, **30s** are values with units, not part of the environment variable name.

## 7. Element order is based on index, not declaration order

Suppose the deployment system supplies variables in a different order:

~~~text
APP_TARGETS_1_NAME=backup
APP_TARGETS_0_NAME=primary
APP_TARGETS_1_URL=https://backup.example.invalid
APP_TARGETS_0_URL=https://primary.example.invalid
~~~

The list is bound according to **index**:

~~~text
targets[0] -> primary
targets[1] -> backup
~~~

Do not infer list order from line order in an environment variable declaration file or the order of **-e** pairs in Docker. The environment variable source may be a map that does not guarantee ordering.

**Indices start at 0**:

- **_0_** represents the first element.
- **_1_** represents the second element.
- **_2_** represents the third element.

Use **contiguous** indices, avoiding starting at **_1_** and skipping **_0_**. A list with gaps in indices, such as having elements 0 and 2 without 1, may not bind properly into a contiguous **List**. Supply all elements and all required fields for each object.

## 8. Lists across multiple configuration sources: replacement, not element-by-element merging

This is an error-prone and very important rule when using environment variables.

Suppose **application.yml** has:

~~~yaml
app:
  targets:
    - name: default-primary
      url: https://default-primary.example.invalid
    - name: default-backup
      url: https://default-backup.example.invalid
~~~

At runtime, the deployment environment only supplies:

~~~text
APP_TARGETS_0_NAME=production-primary
APP_TARGETS_0_URL=https://production-primary.example.invalid
~~~

Many people expect the final list to be:

~~~text
[0] production-primary (from environment)
[1] default-backup     (from YAML)
~~~

However, for a **List** in Spring Boot's binding system, when a list is configured in multiple sources, **the higher-priority source replaces the list from the lower-priority source**. It does not perform an element-by-element merge to automatically keep **targets[1]** from YAML.

In the example above, the expected binding result contains only element **targets[0]** from the environment source. **targets[1]** from YAML is not appended to the new list.

If each object has multiple fields, note further: do not expect Spring Boot to take **name** from the environment source and pull the corresponding **url** from YAML for the same list element. A list from a higher-priority source may contain missing fields; if validation or code requires mandatory fields, binding or startup may fail to meet requirements.

### 8.1. How to supply full configuration when overriding a List

When replacing a list for a deployment environment, provide **all expected elements**:

~~~text
APP_TARGETS_0_NAME=prod-primary
APP_TARGETS_0_URL=https://prod-primary.example.invalid
APP_TARGETS_1_NAME=prod-backup
APP_TARGETS_1_URL=https://prod-backup.example.invalid
~~~

If you genuinely only want one target in production, supplying only element 0 is a valid choice, but you must understand it **replaces the entire list**.

### 8.2. When is Map a better fit than List?

If items have **stable identifying keys** and the main need is overriding individual items while keeping the others, **Map** may fit better than **List**. Spring Boot has merge rules for **Map** across configuration sources; the same map key takes its value according to source precedence.

For example, wanting to manage endpoints by names **primary** and **backup**:

~~~yaml
app:
  targets-by-name:
    primary:
      url: https://primary.example.invalid
    backup:
      url: https://backup.example.invalid
~~~

When declaring the corresponding Java model as **Map<String, Target>**, the configuration meaning is a **map by name**, no longer depending on positions [0], [1]. This is a different design decision; do not switch a List to a Map merely to fix environment variable names if element ordering carries business meaning.

**The List replacement rule applies across PropertySources**, not only between two YAML files. Therefore, environment variables must also be viewed as a source that can replace an entire list declared in Config Data.

## 9. Why use @ConfigurationProperties instead of multiple @Value annotations?

You can read a single simple value via **Environment.getProperty(...)** or **@Value**, but for a list of objects, **@ConfigurationProperties** provides structured binding and supports type conversion, nested properties, and collections.

Configuration example:

~~~text
APP_TARGETS_0_NAME=alpha
APP_TARGETS_0_URL=https://alpha.example.invalid
APP_TARGETS_1_NAME=beta
APP_TARGETS_1_URL=https://beta.example.invalid
~~~

With a record:

~~~java
@ConfigurationProperties(prefix = "app")
public record AppProperties(List<Target> targets) {
    public record Target(String name, String url) {
    }
}
~~~

The Binder can group environment variables under the same prefix into two **Target** objects inside one list.

If you try reading each key with **@Value**, the code must know in advance how many elements exist and manually handle missing elements. That defeats the benefit of dynamic collection binding.

To enable this binding, you must register the **@ConfigurationProperties** class via **@ConfigurationPropertiesScan** or **@EnableConfigurationProperties(...)**. Merely adding the annotation on the record without registering the configuration bean can leave the controller unable to receive the injected object.

### 9.1. Compound-word prefixes

When using:

~~~java
@ConfigurationProperties(prefix = "client-config")
public record ClientConfigProperties(List<Client> clients) {
    public record Client(String baseUrl) {
    }
}
~~~

The matching canonical key is:

~~~text
client-config.clients[0].base-url
~~~

Environment variable name by relaxed binding rules:

~~~text
CLIENTCONFIG_CLIENTS_0_BASEURL
~~~

Not:

~~~text
CLIENT_CONFIG_CLIENTS_0_BASE_URL
~~~

That is why, when working with long property names, you should write out the canonical path first, apply the four renaming steps sequentially, and only then declare the variable in the deployment system.

## 10. Distinguishing List from Map when key names are numbers

Sometimes a **Map** has string keys **"0"** or **"1"**, for example:

~~~yaml
app:
  labels:
    "0": zero
    "1": one
~~~

Semantically, **labels** is a **Map**, whereas **targets** in previous examples is a **List**. A number in a variable name does not automatically turn arbitrary data into a list; **the target type in @ConfigurationProperties** determines how the binder interprets the configuration.

In particular, Spring Boot converts key names from environment variables to lowercase when binding a **Map**, which is notable if the Map has case-sensitive keys.

For lists, explicitly use **List<T>** and **[n]** indices in configuration files. Do not rely on variable names to try to simulate Map keys or vice versa.

If you want an ordered list, **List** with indices is the natural choice. If you want lookup by name and per-key overrides, consider **Map**.

## 11. Declaring in Docker Compose

For a Spring Boot service running in Docker Compose, you can pass variables as follows:

~~~yaml
services:
  api:
    image: my-list-env:1.0.0
    ports:
      - "8080:8080"
    environment:
      APP_TARGETS_0_NAME: "compose-primary"
      APP_TARGETS_0_URL: "https://compose-primary.example.invalid"
      APP_TARGETS_1_NAME: "compose-backup"
      APP_TARGETS_1_URL: "https://compose-backup.example.invalid"
~~~

In the example above, **environment** is a Docker Compose YAML map. The keys are converted into environment variables inside the container; Spring Boot then performs relaxed binding from those variables to **AppProperties.targets**.

Do not write:

~~~yaml
environment:
  app.targets[0].name: compose-primary
~~~

and assume it is a standard declaration that works across all shells or platforms. The uppercase form with underscores **APP_TARGETS_0_NAME** is the approach guided by Spring Boot and works better when the application moves across multiple deployment tools.

Similarly, if using a **.env** file, the familiar declaration is:

~~~dotenv
APP_TARGETS_0_NAME=compose-primary
APP_TARGETS_0_URL=https://compose-primary.example.invalid
APP_TARGETS_1_NAME=compose-backup
APP_TARGETS_1_URL=https://compose-backup.example.invalid
~~~

**Note:** Docker Compose's **.env** file primarily supports variable substitution within Compose configurations. A variable simply sitting in **.env** is not automatically passed into a container unless the Compose configuration references or injects it into the container environment through an appropriate mechanism. With the **environment** example above, the keys are declared directly and therefore passed to the container.

## 12. Using with Kubernetes

In Kubernetes, each entry under **env** has a name and a value:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: list-env-demo
spec:
  replicas: 1
  selector:
    matchLabels:
      app: list-env-demo
  template:
    metadata:
      labels:
        app: list-env-demo
    spec:
      containers:
        - name: app
          image: my-list-env:1.0.0
          ports:
            - containerPort: 8080
          env:
            - name: APP_TARGETS_0_NAME
              value: "k8s-primary"
            - name: APP_TARGETS_0_URL
              value: "https://k8s-primary.example.invalid"
            - name: APP_TARGETS_1_NAME
              value: "k8s-backup"
            - name: APP_TARGETS_1_URL
              value: "https://k8s-backup.example.invalid"
~~~

Kubernetes does not need to know that **_0_** is a Spring Boot list index. It simply supplies environment variable name-value strings to the container; Spring Boot interprets them once the application starts.

When the application has many elements, the list of env entries can grow long. If the list is complex or requires many objects, consider mounting an external configuration file from a ConfigMap or using an appropriate configuration management mechanism instead of defining hundreds of individual environment variables. Whether using a ConfigMap or environment variables, the principles of source precedence and List replacement still need to be understood.

Do not put real passwords into examples or publicly committed manifests. Use the appropriate Secret mechanism for sensitive values and restrict access permissions.

## 13. From which source are lists via environment variables loaded?

Spring Boot applies relaxed binding from OS environment variables via a PropertySource named **systemEnvironment** and certain compatible PropertySources whose names end with **-systemEnvironment**. This is why the naming rule **APP_TARGETS_0_URL** works naturally with the Java process's environment.

However, if you manually create a **MapPropertySource** with an arbitrary name containing key **APP_TARGETS_0_URL**, do not assume it will be processed like system environment. When writing custom configuration integration code, check how that PropertySource is added to Environment and how the binder interprets key names.

In Spring Boot's typical configuration precedence order:

- Config Data files like **application.yml** provide default or profile-specific values.
- Environment variables can override corresponding values from Config Data.
- Java system properties and command-line arguments also have their own priority positions.
- For tests, test-specific sources may have higher priority.

Do not think of relaxed binding as a **data merging** rule. It only determines how **property names** from different sources map onto the target structure; **List replacement** belongs to collection merge rules.

## 14. How to verify binding results without exposing sensitive configuration

In the learning example, the **GET /targets** endpoint returns non-sensitive fields and suffices to observe list order. In real applications, verify using integration tests or logs with restricted information.

Example of a test when environment variables are already supplied by the test execution environment:

~~~java
package com.example.listenv;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class ListEnvironmentBindingTest {

    @Autowired
    AppProperties appProperties;

    @Test
    void bindsTargetsInIndexOrder() {
        assertEquals(2, appProperties.targets().size());
        assertEquals("prod-primary",
                appProperties.targets().get(0).name());
        assertEquals("prod-backup",
                appProperties.targets().get(1).name());
    }
}
~~~

The test above is an example for when the exact set of environment variables **APP_TARGETS_0_NAME**, **APP_TARGETS_1_NAME**, and their corresponding URLs are **already provided** during the test run. Without those variables, the test will read the default configuration and assertions would need adjustment.

In standalone tests, if you want fixed data without depending on the shell, you can use **@SpringBootTest(properties = {...})** with property names like **app.targets[0].name** and **app.targets[1].name**, or use **ApplicationContextRunner** as appropriate. However, to verify the exact **environment variable** syntax, you still need an actual run supplying names like **APP_TARGETS_0_NAME** through the process environment.

### 14.1. Diagnosing binding failures

If binding does not match, check:

1. Original canonical name: is it really **app.targets[0].url**?
2. Were dots turned into **_**?
3. Were hyphens inside property names **removed**, rather than replaced with another **_**?
4. Is the index placed in the right position **_0_**, **_1_**?
5. Do elements start from **0** and have contiguous indices?
6. Did you declare **@ConfigurationProperties** and register scanning/enabling?
7. Is the Java field properly a **List** with the right element type?
8. Were the variables actually supplied to the Java process/container?
9. Is a higher-priority source replacing the whole list?
10. Are values requiring type conversion valid (numbers, durations, URIs, enums...)?

When investigation is needed, you can log the variable names used or the count of bound elements. Never log tokens, passwords, or secret contents.

## 15. Common mistakes

### 15.1. Using square brackets in environment variable names

~~~text
APP_TARGETS[0]_URL
~~~

This is not Spring Boot's recommended syntax for environment variables. Many shells do not accept this form as a normal variable name. The right way for a list is:

~~~text
APP_TARGETS_0_URL
~~~

### 15.2. Forgetting the underscore between the index and the field

~~~text
APP_TARGETS_0URL       <- does not clearly express [0].url
APP_TARGETS_0_URL      <- corresponds to app.targets[0].url
~~~

### 15.3. Adding underscores into kebab-case names

~~~text
app.targets[0].base-url
~~~

Conversion by canonical rules:

~~~text
APP_TARGETS_0_BASEURL
~~~

Do not manually split **base-url** into **BASE_URL** when the goal is mapping the exact same property segment.

### 15.4. Using index 1 for the first element

~~~text
APP_TARGETS_1_NAME=only-target
~~~

Spring Boot lists are 0-indexed. If there is only one target, use:

~~~text
APP_TARGETS_0_NAME=only-target
~~~

### 15.5. Overriding one element and expecting the remaining YAML element to stay

If both **targets[0]** and **targets[1]** are defined in YAML, but the environment only specifies **targets[0]**, Spring Boot does not by default build a list containing the new **targets[0]** and the old **targets[1]**. The List in the higher-priority source replaces the List in the lower-priority source.

### 15.6. Forgetting that environment variables must exist in the process

If you declare variables in another terminal, in a .env file not passed into the container, or in another CI job, the current Java process may not see them. Inspect the deployment environment's env delivery mechanism rather than only checking variable spelling.

### 15.7. Editing environment variables and expecting a running app to update automatically

Spring Boot normally binds **@ConfigurationProperties** when starting the ApplicationContext. Changing environment variables in the shell afterward usually does not automatically refresh beans in a running process; a restart or an explicitly designed refresh mechanism is required.

### 15.8. Mixing multiple list configuration styles without understanding precedence

Declaring part of a List in **application.yml**, part in **application-prod.yml**, and a few elements via env can lead to unexpected results. Establish one primary source for the **entire list** in the target environment and avoid partial overrides.

## 16. Practice exercises

### Exercise A: from YAML to four environment variables

1. Put two targets **built-in-primary** and **built-in-backup** in **application.yml**.
2. Build the application and call **GET /targets** to see the YAML data.
3. Stop the application.
4. Supply **APP_TARGETS_0_NAME**, **APP_TARGETS_0_URL**, **APP_TARGETS_1_NAME**, and **APP_TARGETS_1_URL**.
5. Run the same JAR again and call the endpoint to observe the new data.

**What to observe:** the two elements are bound according to indices **0** and **1**, not by the order in which variables were declared.

### Exercise B: supplying only one element

1. Launch with an environment variable set containing only **APP_TARGETS_0_NAME** and **APP_TARGETS_0_URL**.
2. Call the **/targets** endpoint.
3. Compare with the two-element list in YAML.

**What to observe:** the list from the higher-priority source replaces the YAML list; the second element in YAML is not automatically appended.

### Exercise C: testing a field with a hyphen

1. Create a model with field **baseUrl** and canonical property **app.targets[0].base-url**.
2. Supply variable **APP_TARGETS_0_BASEURL**.
3. Verify the bound value via **@ConfigurationProperties**.

**What to observe:** the environment variable removes the hyphen from **base-url**; **_0_** represents the list element.

### Exercise D: list of strings

1. Use **List<String> regions** in a configuration properties record.
2. Supply **APP_REGIONS_0=asia**, **APP_REGIONS_1=europe**, **APP_REGIONS_2=america**.
3. Read the list and verify the corresponding indices.

**What to observe:** for a scalar List, the variable name ends right after the index, with no child field.

### Exercise E: observing inside a container

1. Declare the variables using Docker Compose **environment** or **docker run -e**.
2. Start the built application image.
3. Call the endpoint to verify the bound list.
4. Change an env value and recreate the container to see the effect.

**What to observe:** Docker passes the environment variables; Spring Boot is what interprets **_0_**, **_1_** as List indices.

## 17. Key points to remember

- In **.properties** and property paths flattened from YAML, list elements are written with **[0]**, **[1]**, **[2]**.
- In environment variables, indices are separated by underscores: **app.targets[0].url → APP_TARGETS_0_URL**.
- Convert property names by the rule: **dot → underscore; hyphen → remove; letters → uppercase; index [n] → _n_**.
- Lists start at index **0**, and indices should be declared contiguously.
- **@ConfigurationProperties** supports binding Lists and nested objects from environment variables via relaxed binding.
- When multiple sources define the same **List**, Spring Boot selects the list from the higher-priority source; it does not merge elements from the remaining sources.
- When overriding a List via deployment environment, provide all elements and fields the application requires.
- Environment variables must actually be passed into the Java process, and changes after startup typically require a restart to take effect.

**Official references:**

- Spring Boot 3.3 — Externalized Configuration, sections *Relaxed Binding*, *Binding From Environment Variables*, *Merging Complex Types*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 — Type-safe Configuration Properties: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties
