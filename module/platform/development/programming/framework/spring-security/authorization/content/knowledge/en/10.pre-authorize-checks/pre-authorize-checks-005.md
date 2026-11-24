# Parameter Name Discovery: `-parameters`, `@P`, and Version Compatibility in Spring Security

> **Topic:** Spring Security — Pre-method checks (`@PreAuthorize`). This lesson explains how Spring Security exposes Java parameters to the SpEL context, the difference between **compiling with `-parameters`**, explicit aliasing with **`@P`**, the Spring Data `@Param` option, positional aliases, and key changes since Spring Framework 6.1. Examples use Java 17+, Spring Boot 3.5.x, Spring Security 6.5.x, and security testing.

## 1. Problem: SpEL needs to know which parameter `#owner` is

Consider a service that only allows callers to read **their own** data:

~~~java
@PreAuthorize("#owner == authentication.name")
public String readOwnProfile(String owner) {
    return "profile:" + owner;
}
~~~

Here:

- `#owner` is a **SpEL variable** created from the method's Java parameter name `owner`.
- `authentication.name` is the **server-authenticated** identity name.
- If Alice calls `readOwnProfile("alice")`, the condition is true; if Alice calls `readOwnProfile("bob")`, it must be denied.
- The condition is checked **before** the target method runs, provided `@EnableMethodSecurity` is enabled and the call passes through a Spring-managed proxy.

The issue lies in how Spring knows the first parameter is actually named `owner`. **Parameter names in Java source code are not always preserved in `.class` files**. A method can compile and run normally even if reflection only sees `arg0` instead of `owner`.

If SpEL uses `#owner` yet runtime cannot find that name, the policy may evaluate incorrectly, deny access, or throw a SpEL error depending on the expression/configuration. Do not assume that merely seeing **403** means the user truly lacks permission, and never switch to `permitAll` to hide a parameter-name error.

**Three main approaches** will be covered:

1. Compile Java with **`javac -parameters`** to retain the name `owner` in class metadata.
2. Use **`@P("alias")`** to publish a dedicated variable name for Spring Security, independent of the original name.
3. Use positional aliases such as **`#p0`**, **`#a0`** for the first parameter when genuinely needed; less clear if the method signature changes.

## 2. `@EnableMethodSecurity` and the path to SpEL

To evaluate `@PreAuthorize`, enable method-level authorization:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

In modern Spring Security, the configuration above registers method-security interceptors, including `AuthorizationManagerBeforeMethodInterceptor` for `@PreAuthorize`. When a controller or another bean calls the service through the Spring AOP proxy:

~~~text
Caller → Spring proxy → @PreAuthorize
                               |
                               v
                    MethodInvocation (method, args)
                               |
                               v
                 MethodSecurityExpressionHandler
                               |
                               v
             EvaluationContext with authentication
               + discovered parameter variables
                               |
                      SpEL expression
                         /         \
                       true        false
                        |             |
                        v             v
                   Target method   DENY
~~~

Spring Security uses a `ParameterNameDiscoverer` to assign names to elements of the arguments array. The default component is documented as **`DefaultSecurityParameterNameDiscoverer`**. It links compilation metadata or annotations to SpEL variables like `#owner`.

**Distinguish two errors:**

- *Name discovery error*: the parameter holds `"alice"`, yet `#owner` in SpEL is not wired properly.
- *Genuine permission error*: `#owner` resolved correctly to `"bob"`, yet the caller is Alice so the expression denies.

Do not use a controller's HTTP `@PathVariable` name to guess a **service parameter** name. They are **two separate methods** with different metadata and annotations.

## 3. Parameter name discovery order: which priority is checked?

According to official Spring Security 6.5 documentation, `DefaultSecurityParameterNameDiscoverer` uses the following mechanisms:

| Mechanism | Example | Meaning | Requirement |
| --- | --- | --- | --- |
| Spring Security **`@P`** | `@P("subject") String name` | Names SpEL variable `subject` | `spring-security-core` dependency |
| Spring Data **`@Param`** | `@Param("subject") String name` | Names variable from Spring Data annotation | Appropriate Spring Data on classpath |
| Java Reflection **`-parameters`** | `String owner` → `#owner` | Preserves real name in class metadata | Compile class/interface with flag |
| Legacy debug info | Local variable table in `-g` | Some legacy mechanisms inferred names | **Do not rely on this since Spring Framework 6.1** |

**Note the version boundary:** Some older explanations of method parameter discovery still mention debug symbols as a fallback. However, the **Spring Security 6.5** migration guide explicitly states that **Spring Framework 6.1 removed `LocalVariableTableParameterNameDiscoverer`**. Therefore, in Spring Boot 3.2+/Spring Framework 6.1+ and newer, **`-g` is not a substitute for `-parameters`** when SpEL needs Java names. Safe upgrade rule: use `-parameters` or explicit naming annotations, and write tests.

### 3.1. When is `@P` most suitable?

- When a library/service **cannot guarantee** the module build preserves Java names.
- When you want stable SpEL names independent of parameter renames in source.
- When an interface is compiled by another module and needs an explicit security contract.
- When you need a short, clear name like `@P("document")` for a complex object.

### 3.2. When is `-parameters` most suitable?

- Modern Java projects where you fully control the Maven/Gradle build.
- Wanting SpEL to read natural names `#ownerId`, `#tenantId`, `#documentId`.
- Retaining parameter names for multiple frameworks that use Java reflection.
- Avoiding adding `@P` to hundreds of methods that already have descriptive names.

### 3.3. Spring Data `@Param` is a conditional option

If the project already includes Spring Data, `org.springframework.data.repository.query.Param` can supply names to Spring Security. **Do not add Spring Data solely to replace `@P`** in a simple service. Using Spring Security's `@P` or `-parameters` is cleaner, unless the Spring Data dependency is already part of the architecture.

## 4. Plain Java 17: proving what `-parameters` does

Before opening Spring Boot, inspect class metadata using Java Reflection. This program **compiles and runs standalone** with JDK 17+, requiring no external libraries.

Create **`ParameterNameProbe.java`**:

~~~java
import java.lang.reflect.Method;
import java.lang.reflect.Parameter;

public class ParameterNameProbe {

    public static void findAccount(String account) {
        // Observe metadata only; contains no business logic.
    }

    public static void main(String[] args) throws Exception {
        Method method = ParameterNameProbe.class.getDeclaredMethod(
            "findAccount", String.class
        );
        Parameter param = method.getParameters()[0];

        System.out.println("name=" + param.getName());
        System.out.println("present=" + param.isNamePresent());
    }
}
~~~

### 4.1. Compiling **with** `-parameters`

~~~bash
javac -parameters ParameterNameProbe.java
java ParameterNameProbe
~~~

**Exact stdout:**

~~~text
name=account
present=true
~~~

`javac` adds the **`MethodParameters`** attribute to the class file. Java reflection therefore returns the `account` name declared by the source method.

### 4.2. Compiling **without** `-parameters`

~~~bash
javac ParameterNameProbe.java
java ParameterNameProbe
~~~

**Typical stdout with JDK 17:**

~~~text
name=arg0
present=false
~~~

If only `-g` is added:

~~~bash
javac -g ParameterNameProbe.java
java ParameterNameProbe
~~~

Java reflection still **does not** recognize `account` via `Parameter#getName()` without `MethodParameters`. `-g` can add a debug `LocalVariableTable`, which is a **different** kind of metadata. This is the exact difference that causes issues after Spring Framework 6.1.

**Re-run note:** each `javac` invocation above overwrites `ParameterNameProbe.class`, and `java` runs the newly compiled class. Do not mix results from an old JAR/classpath.

### 4.3. Inspecting bytecode

On the compiled class:

~~~bash
javap -v ParameterNameProbe
~~~

Look for the `MethodParameters` attribute in the output. With `-parameters`, the `account` name information is recorded in the class file. Without the flag, merely seeing a `LocalVariableTable` (if present) is **not sufficient** to conclude Java reflection in a Spring Framework 6.1+ app will see parameter names.

**Technical takeaway:** `-parameters` is a **compiler flag**, not a JVM runtime option. Running `java -parameters ...` will not fix a class file already compiled without metadata.

## 5. Configuring Maven to retain parameter names

If using the Spring Boot 3.x **`spring-boot-starter-parent`** parent, it usually configures compilation with `-parameters` already. However, **do not guess** if the project only imports the Boot BOM, uses a custom parent, uses a different Gradle module, overrides plugins, or gets code from a third-party JAR.

### 5.1. Explicit configuration in Maven Compiler Plugin

In `pom.xml`, example fragment:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <release>17</release>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

`<parameters>true</parameters>` instructs Maven Compiler Plugin to pass the required flag to the compiler. `<release>17</release>` keeps API/bytecode compatible with Java 17. This is a **build fragment**; if the POM already declares the compiler plugin, **merge the configuration** instead of duplicating the plugin entry.

In a project using the default Boot parent, this fragment may be unnecessary because the parent provides it by default. In a **multi-module Maven** project, check the module containing the **compiled interface/service**, not only the final web module.

### 5.2. Checking the effective build

~~~bash
# From Maven project root (Linux/macOS):
./mvnw clean test

# Inspect inherited Maven configuration:
./mvnw help:effective-pom
~~~

On Windows you can use `mvnw.cmd clean test` and `mvnw.cmd help:effective-pom`.

Next, inspect the compiled class with `javap` or a reflection test. A safer signal than grepping strings in the POM is:

~~~java
// Fragment inside a JUnit test:
Method method = OwnerService.class.getMethod(
    "readNamed", String.class
);
assertTrue(method.getParameters()[0].isNamePresent());
assertEquals("account", method.getParameters()[0].getName());
~~~

The names `OwnerService`/`readNamed` match the demo app in section 10. The fragment requires imports for `java.lang.reflect.Method` and `org.junit.jupiter.api.Assertions.*`, and runs against the **actual class file** compiled by the test build.

### 5.3. Why is `clean` needed when debugging?

If a module was compiled before adding `-parameters` and an incremental build skips recompiling the class, the old class may still lack the attribute. A **clean build** ensures metadata is generated from the new configuration. Do not expect changing a compiler flag without rebuilding dependent library JARs to fix parameter names inside those JARs.

## 6. Gradle: enabling the flag properly for Java modules

For **Groovy DSL `build.gradle`**:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

If using Gradle Kotlin DSL `build.gradle.kts`:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

This is a **fragment** in a Gradle Java project with the appropriate plugin and `JavaCompile` imported/available in the DSL. The setting applies to `JavaCompile` tasks in the module where it is declared. For multi-module builds, place it in each relevant Java module or in an appropriate convention plugin.

After editing:

~~~bash
./gradlew clean test
~~~

On Windows use `gradlew.bat clean test`. Verify reflection with `Parameter#getName()` rather than just observing that the build succeeded.

### Do not confuse Java, Kotlin, and Java records

- The `-parameters` Java compiler flag is for **Java sources**. Kotlin has its own metadata and compiler plugin mechanisms; do not assume `JavaCompile` controls all Kotlin compilation.
- Java records have separate metadata for record components; **do not infer from record component names that every Java method has parameter names**.
- With mixed Java/Kotlin sources and library modules, inspect the actual compiler for each source set, especially service methods with `@PreAuthorize`.
- When using interfaces and JDK dynamic proxies, metadata on the interface or `@P` annotations may govern name binding. Compile every module owning interfaces consistently.

## 7. Using `@P` when an explicit parameter alias is wanted

Exact import:

~~~java
import org.springframework.security.access.method.P;
~~~

A service can use:

~~~java
@PreAuthorize("#subject == authentication.name")
public String readByAlias(@P("subject") String account) {
    return "subject:" + account;
}
~~~

Here:

- The source parameter is named **`account`**.
- Spring Security `@P("subject")` declares the SpEL variable name as **`subject`**.
- The expression reads `#subject`, **not** `#account`.
- No reliance on `-parameters` metadata is needed to know that **alias**.

You can rename the Java parameter from `account` to `requestedAccount` and `#subject` continues to work, provided `@P("subject")` and the method contract stay intact.

### Mismatched alias error

~~~java
// WRONG: annotation sets alias "subject" but SpEL asks for "user":
@PreAuthorize("#user == authentication.name")
public String read(@P("subject") String account) {
    return "private";
}
~~~

In this single-parameter example, `#user` is not defined by the annotation. Spring does not guess that `subject` and `user` mean the same thing. When SpEL cannot obtain the value, the outcome may be DENY or an error depending on the expression. **Never fix this error by removing the security annotation**.

### Multiple parameters with `@P`

~~~java
@PreAuthorize("#subject == authentication.name and #documentId.startsWith('DOC-')")
public String readDocument(
        @P("subject") String account,
        @P("documentId") String id
) {
    return account + ":" + id;
}
~~~

For methods with multiple parameters, **annotate all referenced parameters** so names do not depend on a different fallback. If a discoverer prioritizes present annotations, an unaliased remaining parameter may not resolve the way you expect. Test every SpEL variable after adding/modifying parameters.

**Spring Security's `@P` is not Spring MVC's `@PathVariable` or `@RequestParam`**. One names arguments for the method-security evaluation context; the other two bind HTTP data to controller parameters. They do not substitute for each other.

## 8. Spring Data `@Param`: useful, but not a required dependency

Spring Security documentation also notes recognition of `org.springframework.data.repository.query.Param` when that annotation is on the classpath:

~~~java
import org.springframework.data.repository.query.Param;

@PreAuthorize("#owner == authentication.name")
public String readOwner(@Param("owner") String account) {
    return "owner:" + account;
}
~~~

This fragment requires the corresponding Spring Data dependency. In a repository/service already using Spring Data, `@Param` can simultaneously serve as metadata for repository queries and for security expressions. However:

1. **Do not add Spring Data just to get a naming annotation**, since `@P` is already built into Spring Security.
2. Do not confuse Spring Data's `@Param` with a `@Param` from another library sharing the same simple name.
3. If the same method mixes multiple name-providing annotations, know the discoverer order and test exact name mapping.
4. SpEL expressions do not infer names from SQL placeholders or JSON fields; they require metadata of **the intercepted method**.

## 9. Positional aliases: `#p0` and `#a0`

Spring's method evaluation context can expose parameters under positional aliases:

| Variable | Meaning |
| --- | --- |
| `#p0` | First parameter (index 0) |
| `#a0` | Alternate alias for the first parameter |
| `#p1` | Second parameter (index 1) |
| `#a1` | Alternate alias for the second parameter |
| `#owner` | Exists only when metadata/annotation assigns the name `owner` |

Example:

~~~java
@PreAuthorize("#p0 == authentication.name")
public String readByIndex(String account) {
    return "index:" + account;
}
~~~

This snippet does not require the compiler to retain the `account` name to access **the first parameter**. Understand that this is an **index-based alias**, not recovered metadata.

**Downside:** if the signature changes to:

~~~java
public String readByIndex(String locale, String account)
~~~

then `#p0` is now `locale`, no longer `account`. If you forget to update the policy to `#p1`, you can cause false denials or false grants. For long-lived sensitive policies, meaningful names via `-parameters` or `@P` are usually safer.

Do not confuse `#p0` with `@P("p0")`; they belong to two different mechanisms. Properties `authentication.name` and `principal` come from the security expression root, **not** Java method parameters.

## 10. Runnable Java 17+ Spring Boot application

### 10.1. Problem specification

We will build an API with these routes:

| Request | Service call | How parameter name is obtained |
| --- | --- | --- |
| `GET /api/named/{account}` | `readNamed(String account)` | `-parameters` → `#account` |
| `GET /api/annotated/{account}` | `readAnnotated(@P("subject") String account)` | `@P` → `#subject` |
| `GET /api/positional/{account}` | `readPositional(String account)` | `#p0` |
| `GET /api/pair/{account}/{documentId}` | `readPair(@P...,...@P...)` | Two explicit aliases |
| `GET /public/ping` | Public | No method-security parameters needed |
| `GET /api/unknown` | No allow rule | HTTP default deny |

Sample users:

| User | Authorities | Meaning |
| --- | --- | --- |
| `alice` | `ROLE_USER` | May view Alice's own data |
| `bob` | `ROLE_USER` | May view Bob's own data |
| `ops` | `owner:override` | May override owner check on the three simple endpoints, **does not** bypass the pair rule |

When Alice calls `/api/named/alice`, the service must ALLOW. When Alice calls `/api/named/bob`, the service must DENY. User `ops` can access Alice/Bob paths via the `owner:override` authority on the three rules with declared ORs.

### 10.2. Maven dependencies / compiler

For a Maven Spring Boot **3.5.x**, Java 17+ project, choose:

- `spring-boot-starter-web`
- `spring-boot-starter-security`
- `spring-boot-starter-test` (test)
- `spring-security-test` (test)

With the Boot parent, `-parameters` is typically enabled by default; still verify the actual build. If using a custom parent, add `maven-compiler-plugin` with `<parameters>true</parameters>` as in section 5. This is required for the `readNamed` example to bind `#account` reliably.

### 10.3. Complete application code

Create **`src/main/java/com/example/parameters/ParameterBindingApplication.java`**:

~~~java
package com.example.parameters;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableMethodSecurity
public class ParameterBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(ParameterBindingApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/ping").permitAll()
                .requestMatchers("/api/named/**").authenticated()
                .requestMatchers("/api/annotated/**").authenticated()
                .requestMatchers("/api/positional/**").authenticated()
                .requestMatchers("/api/pair/**").authenticated()
                .anyRequest().denyAll()
            )
            .httpBasic(Customizer.withDefaults());
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("demo123"))
            .roles("USER")
            .build();

        UserDetails bob = User.withUsername("bob")
            .password(encoder.encode("demo456"))
            .roles("USER")
            .build();

        UserDetails ops = User.withUsername("ops")
            .password(encoder.encode("demo789"))
            .authorities("owner:override")
            .build();

        return new InMemoryUserDetailsManager(alice, bob, ops);
    }

    @Service
    public static class OwnerService {

        // Requires javac -parameters so #account resolves to the name.
        @PreAuthorize(
            "#account == authentication.name or hasAuthority('owner:override')"
        )
        public String readNamed(String account) {
            return "named:" + account;
        }

        // Alias "subject" does not depend on Java parameter name "account".
        @PreAuthorize(
            "#subject == authentication.name or hasAuthority('owner:override')"
        )
        public String readAnnotated(@P("subject") String account) {
            return "annotated:" + account;
        }

        // First parameter, does not require Java name metadata.
        @PreAuthorize(
            "#p0 == authentication.name or hasAuthority('owner:override')"
        )
        public String readPositional(String account) {
            return "positional:" + account;
        }

        // Two explicitly named parameters.
        @PreAuthorize(
            "#subject == authentication.name and #docId.startsWith('DOC-')"
        )
        public String readPair(
                @P("subject") String account,
                @P("docId") String documentId
        ) {
            return "pair:" + account + ":" + documentId;
        }
    }

    @RestController
    static class Api {

        private final OwnerService service;

        Api(OwnerService service) {
            this.service = service;
        }

        @GetMapping("/public/ping")
        String ping() {
            return "pong";
        }

        @GetMapping("/api/named/{account}")
        String named(@PathVariable("account") String account) {
            return service.readNamed(account);
        }

        @GetMapping("/api/annotated/{account}")
        String annotated(@PathVariable("account") String account) {
            return service.readAnnotated(account);
        }

        @GetMapping("/api/positional/{account}")
        String positional(@PathVariable("account") String account) {
            return service.readPositional(account);
        }

        @GetMapping("/api/pair/{account}/{documentId}")
        String pair(
                @PathVariable("account") String account,
                @PathVariable("documentId") String documentId
        ) {
            return service.readPair(account, documentId);
        }

        @GetMapping("/api/unknown")
        String unknown() {
            return "should not be reached";
        }
    }
}
~~~

### 10.4. What each part actually proves

1. `@EnableMethodSecurity` activates `@PreAuthorize`. The HTTP filter only checks that the caller is logged in on the four API prefixes, while **the owner check** lives in the service.
2. `readNamed(String account)` uses `#account`: resolving the Java name requires `-parameters` on the actually compiled class.
3. `readAnnotated(@P("subject") String account)` uses `#subject`, proving **an alias** can differ from the Java variable name.
4. `readPositional(String account)` uses `#p0`, demonstrating **index-based** parameter referencing.
5. `readPair(...)` shows two `@P` annotations with distinct names used in the same expression.
6. `@PathVariable("account")` on the controller declares the name **explicitly** so Spring MVC does not have to guess the path variable name. Yet it **does not guarantee** the service parameter's name.
7. The controller calls through the Spring-injected `OwnerService`, so the AOP proxy can apply the annotations. Never call `new OwnerService()` or `this.readNamed(...)` from inside the target service.
8. `UserDetailsService` supplies server-side identity and authorities. The URL containing `alice` is client-chosen, so it **must be compared against `authentication.name`**, never trusting the path parameter.
9. `anyRequest().denyAll()` blocks any new URL lacking a policy, even if a controller exists.
10. All endpoints use GET to avoid mixing CSRF errors with method-security parameter errors.

**Demo safety:** hard-coded passwords are for learning only; HTTP Basic requires HTTPS in real systems. Checking `owner` by name in this example is a simple simulation, not a replacement for tenant/ACL/domain policies when managing real data.

## 11. Request matrix and expected HTTP results

Assuming the build retains `-parameters` properly, no other custom filters/exception handlers exist, and HTTP Basic is used:

| HTTP request | Alice | Bob | Ops | Reason |
| --- | :---: | :---: | :---: | --- |
| `GET /api/named/alice` | **200** | 403 | **200** | `#account` from Java metadata |
| `GET /api/named/bob` | 403 | **200** | **200** | Owner or override authority |
| `GET /api/annotated/alice` | **200** | 403 | **200** | `@P("subject")` |
| `GET /api/annotated/bob` | 403 | **200** | **200** | `subject` alias |
| `GET /api/positional/alice` | **200** | 403 | **200** | `#p0` |
| `GET /api/positional/bob` | 403 | **200** | **200** | Index 0 parameter |
| `GET /api/pair/alice/DOC-42` | **200** | 403 | 403 | Both AND conditions |
| `GET /api/pair/bob/DOC-42` | 403 | **200** | 403 | Owner and docId |
| `GET /api/pair/alice/IMG-42` | 403 | 403 | 403 | docId lacks DOC- prefix |
| `GET /api/unknown` | 403 | 403 | 403 | HTTP default deny |

Anonymous callers hitting the four protected endpoints typically receive **401** in this HTTP Basic example; public ping returns **200**. An authenticated user lacking permission typically receives **403**. If method SpEL fails to find a variable due to missing metadata, the result may be an expression evaluation error or DENY — **do not hard-assert it will always be 403**, check logs/tests.

### Trying with curl

~~~bash
# macOS/Linux: start at the Maven project root.
./mvnw spring-boot:run

# Windows:
mvnw.cmd spring-boot:run
~~~

Once the server runs on `http://localhost:8080`:

~~~bash
# Public:
curl -i http://localhost:8080/public/ping

# Alice reads her own data across all three binding modes:
curl -i -u alice:demo123 http://localhost:8080/api/named/alice
curl -i -u alice:demo123 http://localhost:8080/api/annotated/alice
curl -i -u alice:demo123 http://localhost:8080/api/positional/alice

# Alice cannot impersonate Bob:
curl -i -u alice:demo123 http://localhost:8080/api/named/bob
curl -i -u alice:demo123 http://localhost:8080/api/annotated/bob

# Ops is allowed on the three rules with owner:override:
curl -i -u ops:demo789 http://localhost:8080/api/named/bob

# Two @P: valid owner and valid docId:
curl -i -u alice:demo123 http://localhost:8080/api/pair/alice/DOC-42
curl -i -u alice:demo123 http://localhost:8080/api/pair/alice/IMG-42

# No allow rule:
curl -i -u alice:demo123 http://localhost:8080/api/unknown
~~~

The bodies of allowed requests are `pong`, `named:alice`, `annotated:alice`, `positional:alice`, `named:bob` (Ops), and `pair:alice:DOC-42`, respectively. The bodies returned by the app are not standalone proof of metadata correctness; what matters is the ALLOW/DENY matrix and verifying parameter names via reflection.

## 12. MockMvc/JUnit 5: testing security rules and metadata together

### 12.1. Test dependencies

In `pom.xml`, fragments under `<dependencies>`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

If `spring-boot-starter-test` is already present, do not add a duplicate. Testing `@P` does not require adding Spring Data.

### 12.2. Complete test class

Create **`src/test/java/com/example/parameters/ParameterBindingApplicationTests.java`**:

~~~java
package com.example.parameters;

import java.lang.reflect.Method;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ParameterBindingApplicationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void javacRetainsRealParameterName() throws Exception {
        Method method =
            ParameterBindingApplication.OwnerService.class.getMethod(
                "readNamed", String.class
            );
        assertTrue(method.getParameters()[0].isNamePresent());
        assertEquals("account", method.getParameters()[0].getName());
    }

    @ParameterizedTest
    @CsvSource({
        // user,password,path,expectedStatus
        "anonymous,none,/public/ping,200",
        "anonymous,none,/api/named/alice,401",

        "alice,demo123,/api/named/alice,200",
        "alice,demo123,/api/named/bob,403",
        "bob,demo456,/api/named/bob,200",
        "bob,demo456,/api/named/alice,403",
        "ops,demo789,/api/named/alice,200",

        "alice,demo123,/api/annotated/alice,200",
        "alice,demo123,/api/annotated/bob,403",
        "bob,demo456,/api/annotated/bob,200",
        "ops,demo789,/api/annotated/alice,200",

        "alice,demo123,/api/positional/alice,200",
        "alice,demo123,/api/positional/bob,403",
        "bob,demo456,/api/positional/bob,200",
        "ops,demo789,/api/positional/alice,200",

        "alice,demo123,/api/pair/alice/DOC-42,200",
        "alice,demo123,/api/pair/alice/IMG-42,403",
        "alice,demo123,/api/pair/bob/DOC-42,403",
        "bob,demo456,/api/pair/bob/DOC-42,200",
        "ops,demo789,/api/pair/alice/DOC-42,403",

        "alice,demo123,/api/unknown,403"
    })
    void parameterAuthorizationMatrix(
            String user, String password, String path, int expected
    ) throws Exception {
        MockHttpServletRequestBuilder request = get(path);
        if (!"anonymous".equals(user)) {
            request.with(httpBasic(user, password));
        }
        mvc.perform(request).andExpect(status().is(expected));
    }

    @Test
    void aliasNameAndJavaParameterNameAreDistinct()
            throws Exception {
        mvc.perform(get("/api/annotated/alice")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isOk())
            .andExpect(content().string("annotated:alice"));
    }

    @Test
    void namedParameterReallyReadsTheCorrectArgument()
            throws Exception {
        mvc.perform(get("/api/named/bob")
                .with(httpBasic("alice", "demo123")))
            .andExpect(status().isForbidden());
    }

    @Test
    void wrongPasswordFailsAuthentication() throws Exception {
        mvc.perform(get("/api/named/alice")
                .with(httpBasic("alice", "wrong")))
            .andExpect(status().isUnauthorized());
    }
}
~~~

**This test suite proves two independent things:**

1. `javacRetainsRealParameterName()` verifies **actual metadata in the compiled class**, not merely that the app returns 200/403.
2. `parameterAuthorizationMatrix(...)` verifies that **SpEL variable binding properly drives authorization decisions**, covering both ALLOW and DENY cases.

If someone renames `account` to `username` and forgets to update `#account`, tests will catch it via reflection or behavior. Testing only Alice calling Alice's URL for 200 can miss an overly permissive policy; you must test Alice calling Bob's URL returning 403 and Ops overriding strictly as required.

### 12.3. Testing the service directly with `@WithMockUser`

You can test method security without going through HTTP by injecting the **Spring-managed bean**, instead of calling `new`:

~~~java
// Fragment inside a @SpringBootTest class:
@Autowired
ParameterBindingApplication.OwnerService service;

@Test
@WithMockUser(username = "alice")
void explicitPWorksWhenCalledThroughProxy() {
    assertEquals("annotated:alice", service.readAnnotated("alice"));
}
~~~

This is a supplementary fragment requiring `import org.springframework.security.test.context.support.WithMockUser`. `@WithMockUser` establishes a mock Authentication for the test; it **does not** test HTTP Basic/`UserDetailsService`, whereas MockMvc's `httpBasic` does.

### 12.4. Running the tests

~~~bash
# Linux/macOS:
./mvnw clean test

# Windows:
mvnw.cmd clean test
~~~

Tests are expected to pass with the described sources, dependencies, and compiler flags. Maven/JUnit output depends on the environment; never claim tests were actually run if you have not executed them. Note that the compiler option must apply to **the module containing OwnerService.class**.

## 13. Interfaces, proxies, and separately compiled modules

An issue that often surfaces only at deployment: the service interface lives in library A, the implementation lives in application B, and the two are built with different configurations.

Example interface:

~~~java
public interface AccountReader {
    @PreAuthorize("#owner == authentication.name")
    String read(String owner);
}
~~~

This is a fragment requiring the `PreAuthorize` import. If the compiled interface **lacks `-parameters`**, Spring may fail to obtain the name `owner` from **the method/interface being analyzed**, even if the implementation source shows the exact same name. Certain proxies and annotation-placement patterns also affect which method is inspected.

**Safe practices:**

- Compile **both the API/interface module** and the implementation with `-parameters` if expressions rely on names.
- Or publish the contract explicitly using `@P`:
  
~~~java
public interface AccountReader {
    @PreAuthorize("#subject == authentication.name")
    String read(@P("subject") String owner);
}
~~~

This fragment requires importing `P` and `PreAuthorize`; if the implementation customizes proxies or security annotation placement, **integration tests are the proof**.
- With JDK dynamic proxies, the interface may be the reflected method inspected; implementation parameter names are not always sufficient.
- With class-based proxies, watch out for final/private methods and self-invocation; those are **proxy/interception** issues, not SpEL naming issues.
- A pre-packaged library JAR with old metadata **will not fix itself** when the consuming app enables `-parameters`. Rebuild **the source module** or place alias annotations in editable source.

## 14. Version compatibility: which source should you read?

| Platform | What to remember |
| --- | --- |
| Java 8 and later | `javac -parameters` emits parameter name metadata for reflection |
| Legacy Spring Security (pre-modern migrations) | Some setups relied on debug local-variable metadata; do not treat as a long-term contract |
| Spring Framework **6.1+** | **Removed `LocalVariableTableParameterNameDiscoverer`** |
| Spring Security **6.5** | Docs describe `@P`, Spring Data `@Param`, `-parameters`, and discovery mechanisms; migration guide **emphasizes `-parameters` is required** |
| Spring Boot 3.x / Spring Framework 6.x | Check the exact underlying Framework version and Java compiler configuration per module |
| Spring Security 7+ / Spring Framework 7+ | Do not assume all behavior/APIs match 6.5; check docs for your active version and re-run tests |

### When old docs say “debug symbols still work” but the migration guide says “-parameters is required”

Prioritize documentation for **the framework version actually running**. For Spring Framework 6.1+, the migration guide confirms the old local-variable-table discovery mechanism was removed; therefore:

- **Do not treat `javac -g` as a reliable fallback.**
- Use `-parameters` for sources you control.
- Use `@P` at boundaries needing explicit aliases or where Java names are outside your control.
- Write **reflection tests** to catch missing attributes before running an entire suite of authorization tests.
- Write **integration tests** for both ALLOW and DENY. A CI test classpath/JAR that differs from the deployed artifact can still cause production to behave differently.

Do not assume a flag is active because “it works on a developer machine”. Read the **effective build** and inspect the final class file/JAR.

## 15. Common design errors and 403 diagnostics

| Mistake | Consequence | How to check/fix |
| --- | --- | --- |
| SpEL writes `#owner` yet class lacks `-parameters` | Variable fails to resolve as intended | Reflection test, enable compiler flag |
| Adding only `-g` | Debug info does not replace MethodParameters in Spring Framework 6.1+ | Switch to `-parameters` |
| Passing flag to `java` JVM instead of compiler | Does not modify `.class` metadata | Configure Maven/Gradle javac |
| Editing parent POM while child module overrides plugin | Service module still lacks flag | Check effective POM and class files |
| Adding `@P("subject")` yet expression uses `#owner` | Alias mismatch | Use `#subject` or update annotation |
| `@P` on one parameter while relying on Java name for another | Discoverer may return unexpected metadata | Explicitly name every referenced variable |
| Using Spring Data `@Param` without the dependency | Import error or missing discoverer | Use Spring Security `@P` |
| Assuming controller `@PathVariable("owner")` names service parameter | Two independent methods | Attach metadata at the service |
| Prepending a parameter while keeping `#p0` | Policy shifts to the wrong value | Choose clear names or update tests |
| Interface/JAR compiled without flag | Reflection on interface lacks names | Rebuild module or add alias annotations |
| Enabling flag without clean build | Stale class still lacks metadata | Clean/test and verify bytecode |
| `@PreAuthorize` skipped due to self-invocation | Guard bypassed despite valid names | Call via Spring bean proxy |
| Testing only happy path, no negative tests | Permission holes go unnoticed | ALLOW/DENY matrix and side-effect checks |
| SpEL compares client parameter without authenticated identity | Can trust spoofed data | Compare against server-side `authentication` and domain policy |
| Concluding every 403 is a parameter-name error | Could be missing authority/CSRF/HTTP rule | Identify filter/advisor and run control tests |

### Step-by-step debugging workflow

1. **Identify the protected method** and exact expression, not just the URL or controller.
2. **Enable `@EnableMethodSecurity`** and ensure the method runs through a Spring AOP proxy; check for self-invocation.
3. **Verify parameter names**: use reflection `getParameters()[i].isNamePresent()` for Java names or inspect `@P`/`@Param` on the intercepted method.
4. **Verify the running class/JAR** was compiled from the right source, module, and compiler flags.
5. **Evaluate actual SpEL inputs**: owner, tenantId, documentId; never log plaintext tokens/secrets.
6. **Check server-side principal and authorities**; if the condition fails despite valid metadata, it may be a legitimate DENY.
7. **Check both HTTP + method layers**. If a POST request lacks CSRF, 403 may appear before method security; this lesson uses GET to isolate the check.
8. **Run negative tests** for accounts attempting to access another user's data and unauthorized actions.
9. **Never change a policy to `permitAll`** just to make a test green. Missing metadata is a build/config or annotation contract error, never a reason to grant more access.

### Separating error types in a real environment

- Unauthenticated request with HTTP Basic: typically **401**.
- Logged-in user denied by `@PreAuthorize`: typically **403**.
- SpEL expression missing a variable or failing property access: **may raise an evaluation exception**, exact HTTP code depends on exception translation/config.
- POST/PUT/PATCH/DELETE missing CSRF token: can be **403 before reaching method security**.
- Proxy/interceptor did not run: can be **unintended 200**, far more dangerous than 403.
- Domain policy deny: can be **403/404 per policy**, requiring audit at the exact blocking point.

## 16. Self-check questions

**Q1.** Why might `@PreAuthorize("#owner == authentication.name")` work on a developer's machine yet fail on CI?  
**Answer:** The module may be compiled with different compiler flags, leaving CI classes without `MethodParameters` metadata, so Spring cannot obtain the `owner` name as expected.

**Q2.** Is `-parameters` an option for `javac` or `java`?  
**Answer:** `javac`; it modifies the contents of `.class` files at compile time.

**Q3.** Does `javac -g` replace `-parameters` in Spring Framework 6.1+?  
**Answer:** Do not rely on it. `LocalVariableTableParameterNameDiscoverer` was removed.

**Q4.** Where should `@P` be imported from?  
**Answer:** `org.springframework.security.access.method.P`.

**Q5.** Given `read(@P("subject") String account)`, which name must the expression use?  
**Answer:** `#subject`, not `#account` automatically.

**Q6.** When using the Spring Boot 3 Maven parent, is adding the compiler plugin manually always required?  
**Answer:** Not necessarily; the Boot parent typically enables `-parameters`. Still check the effective build and bytecode in the service module.

**Q7.** What does `#p0` mean?  
**Answer:** Parameter at position 0, independent of name, though very error-prone if parameter order changes.

**Q8.** Does `@PathVariable("account")` on a controller automatically make `#account` work on a service?  
**Answer:** No. Service metadata is resolved independently.

**Q9.** Is placing `@P` on an interface method helpful?  
**Answer:** It can establish an explicit contract right on the interface; still test with your app's proxy type and version, as method/annotation resolution depends on configuration.

**Q10.** When a class is compiled with `-parameters`, what does `Parameter#isNamePresent()` return for `String account`?  
**Answer:** `true`; `getName()` is `account`.

**Q11.** If `@PreAuthorize` does not run due to `this.readNamed(...)`, is enabling `-parameters` enough to fix it?  
**Answer:** No. That is a self-invocation/proxy issue, not parameter name metadata.

**Q12.** How do you distinguish a valid DENY from a parameter-name error?  
**Answer:** Check metadata via reflection/annotations, inspect the method proxy, then run control tests for matching owner and mismatched owner with the same code.

**Q13.** Should you add Spring Data solely to use `@Param`?  
**Answer:** Usually no; Spring Security's `@P` is sufficient for explicit aliases.

**Q14.** When an expression uses two parameters—one with `@P`, one relying on Java source name—what is the risk?  
**Answer:** Discoverers follow priority order and should not be assumed to merge names from mixed sources automatically; explicitly name all used parameters or verify build metadata/tests.

**Q15.** Does preserving parameter names correctly automatically protect against IDOR/BOLA?  
**Answer:** No. SpEL reading the right value is only the first step; you still must verify owner, tenant, role, permission, and resource policies on the server.

**Practical summary:** When `@PreAuthorize` references `#ownerId` or `#tenantId`, ensure **metadata for that exact method** exists: compile the module with **`-parameters`**, or use explicit **`@P`**; `#p0` fits intentional positional references. On Spring Framework 6.1+, **do not rely on debug symbols as a substitute**. Verify with reflection and **allow-right/deny-right** tests before deployment.

## Official documentation

- Spring Security 6.5 — Method Security, section **Using Method Parameters**: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Security 6.5 — Authorization Migrations, section **Compile With -parameters** and Spring Framework 6.1: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/authorization.html
- Spring Framework 6.2 — `MethodBasedEvaluationContext` (`p0`, `a0` aliases, parameter names): https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/context/expression/MethodBasedEvaluationContext.html
- Spring Security 6.5 — `DefaultSecurityParameterNameDiscoverer` API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/parameters/DefaultSecurityParameterNameDiscoverer.html
- Spring Security 6.5 — `P` annotation API: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/access/method/P.html
- Spring Boot — Maven Plugin, `spring-boot-starter-parent` `-parameters` default support: https://docs.spring.io/spring-boot/maven-plugin/using.html
