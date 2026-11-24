# JNDI, ServletContext, and ServletConfig in a Servlet Environment

> **Topic:** Spring Boot Externalized Configuration  
> **Group:** Sources and Precedence

## 1. Context and Objectives

A Spring Boot application can obtain the same configuration from `application.properties`/`application.yml`, OS environment variables, JVM arguments, command-line arguments, or from the Servlet environment where the application is deployed. When deploying a web application as a WAR to a Servlet container/application server, three common configuration sources are:

- **JNDI**: values or resources published by the container under the `java:comp/env` namespace.
- **ServletContext init parameters**: initialization parameters shared across the web application.
- **ServletConfig init parameters**: initialization parameters specific to a single Servlet.

All three can participate in Spring `Environment`'s `PropertySource` mechanism, yet **they differ in lifetime scope, declaration syntax, and availability conditions**. Understanding these differences helps avoid reading the wrong value when moving from local runs to WAR deployments.

After this lesson, you will be able to identify the source of a configuration property, predict which value wins when keys collide, read values via Spring or Servlet APIs, and distinguish a JNDI value from a JNDI resource such as a `DataSource`.

## 2. Three Configuration Sources in the Servlet Environment

| Source | Typical Declaration Location | Scope / Meaning | Direct Access API |
| --- | --- | --- | --- |
| **JNDI (`java:comp/env`)** | Container/application server configuration; environment resource declarations per server mechanism | Values or objects supplied by the server to the application; depends on container and JNDI setup | `InitialContext.lookup("java:comp/env/...")` |
| **ServletContext init parameters** | `<context-param>` in `WEB-INF/web.xml` or equivalent Servlet configuration | Shared across one `ServletContext` of the web application | `servletContext.getInitParameter("...")` |
| **ServletConfig init parameters** | `<init-param>` inside a `<servlet>` declaration or corresponding registration | Tied to a single Servlet; each Servlet can have its own set of values | `servletConfig.getInitParameter("...")` |

**Point to remember:** `ServletContext` is the context of the web application, whereas `ServletConfig` is the configuration of **one Servlet**. You cannot assume a parameter on Servlet A also exists in Servlet B or is always visible from every Spring application context.

### 2.1. JNDI: Container-Provided Configuration and Resources

JNDI (Java Naming and Directory Interface) lets an application look up names registered by the runtime environment. In a Servlet application, `java:comp/env` is the standard namespace for an application's environment entries.

Illustrative example in **Tomcat** context configuration (exact syntax depends on the container):

~~~xml
<Context>
    <Environment name="app.region"
                 type="java.lang.String"
                 value="ap-southeast"
                 />
</Context>
~~~

When the server supplies this entry, Java code can read it with JNDI:

~~~java
import javax.naming.InitialContext;
import javax.naming.NamingException;

public class JndiExample {
    public String region() throws NamingException {
        return (String) new InitialContext()
                .lookup("java:comp/env/app.region");
    }
}
~~~

In a Spring Servlet environment where JNDI is available, a `JndiPropertySource` can cause the key `app.region` to resolve from `java:comp/env/app.region` via Spring `Environment`. Creating a JNDI entry is still the container's responsibility; merely adding a key to `application.yml` does not create a JNDI entry.

JNDI is also used for **object resources**, such as a connection pool. For a resource published by the server at `java:comp/env/jdbc/ReportingDS`, the application can configure:

~~~properties
spring.datasource.jndi-name=java:comp/env/jdbc/ReportingDS
~~~

Here, `spring.datasource.jndi-name` is **a Spring Boot property pointing to the JNDI resource**; that differs from declaring the literal key `spring.datasource.jndi-name` itself inside JNDI. JNDI entries can return objects and are not always suitable to treat as simple configuration strings.

### 2.2. ServletContext: Parameters for the Whole Web Application

An excerpt from `WEB-INF/web.xml` of a WAR application:

~~~xml
<context-param>
    <param-name>app.region</param-name>
    <param-value>region-from-context</param-value>
</context-param>
~~~

Inside a Servlet or component holding a `ServletContext` reference:

~~~java
String region = servletContext.getInitParameter("app.region");
~~~

This value belongs to the current `ServletContext`, so Servlets in the same web application can read it in common. It fits some traditional WAR applications requiring container-layer configuration, though in modern Boot applications `application.yml` and externalized configuration mechanisms are usually more convenient for general settings.

### 2.3. ServletConfig: Parameters Specific to Each Servlet

An excerpt from `web.xml`, declaring a Servlet with its own initialization parameter:

~~~xml
<servlet>
    <servlet-name>reportServlet</servlet-name>
    <servlet-class>com.example.web.ReportServlet</servlet-class>
    <init-param>
        <param-name>app.region</param-name>
        <param-value>region-from-servlet</param-value>
    </init-param>
</servlet>
~~~

Inside `ReportServlet`:

~~~java
String region = getServletConfig().getInitParameter("app.region");
// Or call getInitParameter("app.region") directly inside HttpServlet.
~~~

Other Servlets do not automatically receive `reportServlet`'s `init-param`. In particular, a `DispatcherServlet`'s `ServletConfig` is normally meaningful for the context attached to that Servlet; **do not assume** all Servlet-specific parameters appear in the root Spring Boot application's `Environment`. Whether they can be read through Spring depends on the structure of the application contexts and when Servlet sources are initialized.

## 3. Precedence Order in Spring Boot

Spring Boot gathers values from multiple `PropertySource` instances into `Environment`. When **the same key** appears in multiple sources, the higher-precedence source wins; values are not automatically concatenated or merged. The list below shows the order from **high → low** in normal Spring Boot operation, omitting test-only and Devtools sources:

| Precedence | Source |
| --- | --- |
| 1 (highest in this table) | Application command-line arguments, e.g. `--app.region=from-cli` |
| 2 | `SPRING_APPLICATION_JSON` |
| 3 | `ServletConfig` init parameters, **if present in the `Environment` being queried** |
| 4 | `ServletContext` init parameters |
| 5 | JNDI attributes in `java:comp/env` |
| 6 | Java system properties, e.g. `-Dapp.region=from-jvm` |
| 7 | OS environment variables, e.g. `APP_REGION=from-os` |
| 8 | `RandomValuePropertySource`, supplying only `random.*` keys |
| 9 | Config data: `application.properties`, `application.yml`, and profile/location variants |
| 10 | `@PropertySource` on configuration classes |
| 11 (lowest) | `SpringApplication` default properties |

The official Spring Boot documentation lists these from **low → high**, meaning sources listed later can override earlier ones. The table above reverses the order to make answering "which source wins?" easier.

A few exceptions must be checked before predicting: tests can add higher-precedence sources; Devtools has global settings; an application can add or reorder a `PropertySource` itself; and a program can disable accepting command-line arguments. Also, a source participates in comparison **only if it is actually present in the `Environment` being queried**.

Among the three Servlet sources in a Boot environment, remember this order:

~~~text
ServletConfig > ServletContext > JNDI > Java system properties > OS environment
~~~

Example where the same key `app.region` is provided as follows:

~~~text
application.properties                app.region=from-file
OS environment (APP_REGION)          from-os
JVM (-Dapp.region=from-jvm)           from-jvm
JNDI java:comp/env/app.region        from-jndi
ServletContext init-param            from-context
ServletConfig init-param             from-servlet
Application argument                 --app.region=from-cli
~~~

If all of the sources above are registered and readable from **the same Spring `Environment`**, the final value is `from-cli`. Removing the command-line argument lets `from-servlet` win; if the application only has `ServletContext` and JNDI, `from-context` wins. Do not use this example to infer that Servlet-specific parameters always appear in the root context.

### 3.1. Difference Between Precedence Order and Initialization Order

There are two separate questions:

1. **Which source has higher precedence?** That is the `PropertySource` lookup order once the application has initialized.
2. **Is that source available at the time the value is read?** Certain settings such as `logging.*` and `spring.main.*` are processed early; a configuration source added later may arrive too late to control bootstrap behavior.

Similarly, a component can read `ServletContext` directly once the context is ready, but that does not prove the key participated in the right `Environment` when another part of the application initialized.

## 4. Accessing Configuration: Choosing an API by Purpose

### 4.1. Using Spring Environment for a General Configuration Key

~~~java
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class RegionSettings {
    private final Environment environment;

    public RegionSettings(Environment environment) {
        this.environment = environment;
    }

    public String region() {
        return environment.getProperty("app.region", "unknown");
    }
}
~~~

This looks up the key across the `PropertySource` instances known to the current `Environment`. When you need multiple properties sharing a prefix with type checking, you can use `@ConfigurationProperties` for structured configuration binding.

### 4.2. Using the Servlet API When You Need the Exact Servlet Scope

~~~java
import jakarta.servlet.ServletConfig;
import jakarta.servlet.ServletContext;

public class ServletParameterReader {
    public String sharedValue(ServletContext context) {
        return context.getInitParameter("app.region");
    }

    public String servletValue(ServletConfig config) {
        return config.getInitParameter("app.region");
    }
}
~~~

The two calls return values at two different scopes. `null` can indicate the key was not declared in that specific scope; it does not mean Spring cannot find a value with the same name in another source.

### 4.3. Using JNDI Lookup for Server-Managed Resources

~~~java
import javax.naming.InitialContext;
import javax.naming.NamingException;
import javax.sql.DataSource;

public class ServerResources {
    public DataSource reportingDataSource() throws NamingException {
        return (DataSource) new InitialContext()
                .lookup("java:comp/env/jdbc/ReportingDS");
    }
}
~~~

In Spring Boot, if the target is a `DataSource`, it is usually better to let Spring Boot manage the bean/connection pool via `spring.datasource.jndi-name` suited to your deployment rather than scattering manual lookups across services. When no matching entry exists, a JNDI lookup can throw `NamingException`; do not assume every server provides the exact same name.

## 5. WAR Deployment Example and Differences When Running a JAR

A legacy system deploying a Spring Boot application as a WAR to Tomcat might have:

- `application.properties` inside the application: `app.region=default-region`.
- A JNDI environment entry in Tomcat configuration: `app.region=jndi-region`.
- `<context-param>` in `web.xml`: `app.region=web-region`.
- A Servlet's own `<init-param>`: `app.region=servlet-region`.

If the queried Spring `Environment` contains all of these sources, the Servlet init param has the highest precedence among the four. If the root application context does not have a dedicated `ServletConfig` attached, `web-region` can be the winning value. Meanwhile, calling `getServletConfig().getInitParameter(...)` directly inside the Servlet still returns `servlet-region` for that Servlet's scope, regardless of Spring precedence.

For applications run with `java -jar` and an **embedded** servlet container, do not assume traditional WAR JNDI/`web.xml` declarations appear automatically. How Servlet params or JNDI are provided depends on how the embedded container is configured and when the container starts. If you need environment-specific configuration across deployment styles, prefer Boot's standard sources (config data, environment variables, system properties, command-line arguments) to reduce container coupling.

Version note: Spring Boot 3+ uses the Servlet API under the `jakarta.servlet` namespace; the JNDI API and JDBC `DataSource` remain in the `javax.naming` and `javax.sql` packages, respectively.

## 6. How to Diagnose When a Value Differs from Expectations

**Step 1 — Verify the key and context.** Ensure the property name matches; for example, the environment variable `APP_REGION` is typically mapped by Spring Boot to `app.region` when bound/read via the corresponding mechanism. Confirm whether you are inspecting the root context or a Servlet context.

**Step 2 — Inspect available sources.** For a non-sensitive demo key, you can list `PropertySource` names and the values found:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceProbe implements ApplicationRunner {
    private final ConfigurableEnvironment environment;

    public PropertySourceProbe(ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        String key = "app.region";
        System.out.println("Resolved: " + environment.getProperty(key));

        environment.getPropertySources().forEach(source -> {
            Object value = source.getProperty(key);
            if (value != null) {
                System.out.println(source.getName() + " -> " + value);
            }
        });
    }
}
~~~

This snippet is diagnostic: run it only with demo keys, and never log secrets, tokens, passwords, or the entire `Environment`. Source positions can vary based on actual configuration, so observe the source names and order at runtime. When Spring Boot Actuator is configured and secured appropriately, the `env` and `configprops` endpoints also help trace why a value was selected.

**Step 3 — Check Servlet/JNDI separately.** If Spring does not see the key: verify whether the server published the JNDI entry under the exact name `java:comp/env/...`; whether `ServletContext` actually contains the `context-param`; and whether the `ServletConfig` you are inspecting belongs to the right Servlet.

**Step 4 — Create a controlled key-collision test.** Use a demo key such as `app.region`, vary each source in a test environment, and compare `Environment` results against direct Servlet/JNDI calls. Also test omitting the key from each source to verify fallback behavior.

### Common Errors

| Symptom | Cause to Check |
| --- | --- |
| `Environment.getProperty(...)` returns a different value than `ServletConfig.getInitParameter(...)` | Spring is querying multiple sources in precedence order; or that specific `ServletConfig` is not included in the current `Environment` |
| JNDI lookup throws `NameNotFoundException` | Entry is not registered by the server, name mismatches, or the `java:comp/env` prefix is wrong |
| Changing `web.xml` has no effect when running an executable JAR | The embedded container flow does not consume traditional WAR configuration the way you expected |
| JVM `-D...` appears ignored | A higher-precedence source is present, such as JNDI, Servlet params, or command-line arguments |
| Two Servlets read two different `init-param` values | Each `ServletConfig` belongs to its own Servlet; this is the expected behavior |
| Early config key does not reflect a late-added source | The bootstrap phase already processed the key before the source was registered |

## 7. Guided Practice

**Scenario A.** `app.mode` is `default` in `application.yml`, JVM `-Dapp.mode=prod`, JNDI = `managed`, `ServletContext` = `context`. No `ServletConfig` has the same key and there are no command-line arguments. When all sources are present in the same `Environment`, the winning value is **`context`**.

**Scenario B.** Add `--app.mode=preview` when running the application. With Spring Boot's default configuration, **`preview`** wins due to command-line argument precedence.

**Scenario C.** Inside `reportServlet`, `getInitParameter("app.mode")` returns `report-only`, while another bean's `Environment` returns `context`. Both results can be simultaneously correct: the Servlet API call reads only `reportServlet`'s own init param, whereas the other bean's Spring `Environment` may not contain that `ServletConfig`.

## 8. Design Takeaways

- Choose JNDI only when you genuinely need container-managed configuration or resources, especially server-managed resources like a `DataSource`.
- Use `ServletContext` for web-application-wide settings and `ServletConfig` for a single Servlet's settings; do not treat them as system-wide configuration.
- Consider **both source presence and precedence order** when explaining a Spring Boot value. The three Servlet sources only exist when the corresponding Servlet runtime/configuration is present.
- For Boot applications running across diverse environments, prefer standard externalized configuration mechanisms to minimize dependence on deployment-specific details.

## References

- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): source precedence, environment-based configuration, and ways to access values.
- [Spring Framework — Environment Abstraction](https://docs.spring.io/spring-framework/reference/core/beans/environment.html): `Environment`, `PropertySource`, `StandardServletEnvironment`, and Servlet source scopes.
- [Spring Boot — Traditional Deployment](https://docs.spring.io/spring-boot/how-to/deployment/traditional-deployment.html): differences between WAR deployment and running an executable application.
