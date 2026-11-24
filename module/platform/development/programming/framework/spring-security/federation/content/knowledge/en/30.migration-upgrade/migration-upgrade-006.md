# Checking Compatibility Across Java, Spring Boot, and Kerberos Extensions

> **Module:** Spring Security – federation · **Parent topic:** Migration and Upgrade. This Knowledge article presents a methodology to verify compatibility across **JDK**, **Spring Boot**, **Spring Framework**, **Spring Security**, **Spring Security Kerberos extension**, **Jakarta Servlet**, **JAAS/JGSS**, and **KDC/Active Directory/SPNEGO** infrastructure. "Successful build" is only one verification layer: you must guarantee the browser receives `WWW-Authenticate: Negotiate`, sends a real service ticket, the server decrypts it with the right keytab, the user maps to the right local account, and only granted permissions are assigned.

> **Reference milestone:** November 2026. Version numbers are branches and baselines verified from Spring documentation and Maven Central at the time of writing; before deployment, check support policies, the latest security patches, and the actual resolved versions. Kerberos 2.x belongs to the Spring Security 6 line, whereas Kerberos 7.x modules changed their Maven group to align with Spring Security 7.

## 1. Learning Objectives

Upon completion, you can:

1. Diagram the dependency chain from JDK and Servlet container to the Spring Security SPNEGO filter, Kerberos provider, JAAS/JGSS, keytab/KDC, and local user mapping.
2. Understand why Spring Boot 3 and 4 both require Java 17+ yet cannot arbitrarily share the same Kerberos extension.
3. Read the exact baselines: Kerberos 2.1.1 (JDK 17, Security 6.3.0, Framework 6.1.8); Kerberos 2.2.0 (JDK 17, Security 6.5.1, Framework 6.2.8); and Kerberos 7.1.2 (JDK 17, Security 7.1.2, Framework 7.0.10).
4. Choose Maven coordinates `org.springframework.security.kerberos:*:2.x` when using Spring Security 6, and `org.springframework.security:spring-security-kerberos-*:7.x` when using Spring Security 7.
5. Distinguish `javax.servlet.Filter` from `jakarta.servlet.Filter`; and recognize that `javax.security.auth.Subject` and `javax.security.auth.kerberos.KerberosPrincipal` are Java SE and do **not** change to `jakarta.security.auth`.
6. Inspect `SpnegoAuthenticationProcessingFilter`, `SpnegoEntryPoint`, `KerberosServiceAuthenticationProvider`, `SunJaasKerberosTicketValidator`, and `UserDetailsService` per generation's API.
7. Write a `SecurityFilterChain` configuration on Spring Boot 3 with keytab-based Kerberos service-ticket validation without legacy `WebSecurityConfigurerAdapter`.
8. Distinguish a Kerberos acceptor (receiving SPNEGO) from a Kerberos initiator (`KerberosRestTemplate` or LDAP service client).
9. Run Gradle `dependencyInsight`, Maven `dependency:tree`, `jdeps`, and a Java 17 classpath probe to detect linkage/version conflicts.
10. Verify SPN, realm, KVNO, encryption types, JAAS/`krb5.conf`, DNS, NTP, browser IWA, and reverse proxies after upgrading the JDK.
11. Design properly scoped unit, MockMvc, MiniKdc, AD-sandbox, browser E2E, and multi-node tests.
12. Run the Java 17 decision matrix demo with deterministic stdout; never treat its output as vendor support certification.
13. Handle `NoClassDefFoundError`, `NoSuchMethodError`, `UnsupportedClassVersionError`, 401 loops, `KRB_AP_ERR_MODIFIED`, and post-auth 403s.
14. Build upgrade, rollout, observability, rollback, and incident response checklists if a keytab or service principal is misconfigured or compromised.

## 2. Kerberos Authentication Architecture on Spring Security

~~~text
Browser / SPNEGO capable client
    |
    | GET /intranet
    | 401 WWW-Authenticate: Negotiate
    |
    | (acquires service ticket from KDC)
    | Authorization: Negotiate <opaque-SPNEGO-token>
    v
TLS termination / reverse proxy
    |
    v
Spring Security FilterChainProxy (correct SecurityFilterChain)
    |
    v
SpnegoAuthenticationProcessingFilter
    |
    v
AuthenticationManager / ProviderManager
    |
    v
KerberosServiceAuthenticationProvider
    |
    +--> SunJaasKerberosTicketValidator
    |        |
    |        +--> JAAS + JGSS in JDK
    |        +--> service principal / realm
    |        +--> keytab / KVNO / encryption types
    |        +--> KDC-issued service ticket
    |
    v
UserDetailsService / local identity mapping
    |
    v
Authentication + GrantedAuthorities + SecurityContext
    |
    v
Controller / service / tenant and object-level authorization
~~~

The layers above span multiple independent systems. If the filter sits on the classpath without being added to `SecurityFilterChain`, the browser never reaches the ticket validator. If the Kerberos ticket is valid yet `UserDetailsService` does not recognize the principal, the app must deny access rather than granting a default role. If Java source compiles yet the keytab points to the wrong SPN or KVNO, production fails even with green CI compilation.

### 2.1. Separate Six Types of Compatibility

| Type | Question to Answer | Evidence |
| --- | --- | --- |
| **Language/runtime** | Are Java source, bytecode, JVM, and JGSS provider compatible? | `java -version`, `javac`, classfile, JDK modules. |
| **Framework** | Are Boot/Framework/Security/Kerberos BOMs consistent? | Dependency tree, resolved runtime classpath, Javadoc. |
| **Servlet binary** | Is the web filter compiled against `jakarta.servlet.Filter` matching the container? | Type signatures and startup test. |
| **Protocol** | Do 401 Negotiate and Kerberos service-ticket validation work? | Ticket from test KDC + HTTP/browser test. |
| **Authorization** | Does user principal map to the right local account/tenant and roles? | Local repository/negative tests, 200/403. |
| **Operations** | Are keytab, SPN, NTP, proxy, container/JDK, replicas, and rollback accurate? | Per-node canary, security/log audits. |

### 2.2. Do Not Confuse the Providers

- `KerberosServiceAuthenticationProvider` verifies service tickets/SPNEGO tokens, requiring `KerberosTicketValidator` and `UserDetailsService` to map local user/authorities.
- `SunJaasKerberosTicketValidator` uses Java JAAS/Krb5 and a service keytab; this is the **acceptor** path.
- `KerberosAuthenticationProvider` typically performs client-side authentication with username/password-to-KDC via `KerberosClient`. It **does not** extract `Authorization: Negotiate` from Servlet requests.
- `SpnegoAuthenticationProcessingFilter` parses the `Negotiate` header and calls `AuthenticationManager`.
- `SpnegoEntryPoint` sends the `WWW-Authenticate: Negotiate` challenge with status 401, with optional forward/fallback.
- `KerberosRestTemplate` is the **client/initiator** path calling a Kerberos-protected downstream HTTP service; test separately if used by the app.
- A first HTTP 401 challenge can be expected; repeated 401s after sending a real token require investigation.

## 3. Verified Version Matrix by Branch

| System Branch | Java | Spring Boot/Framework/Security | Kerberos Module | Remarks |
| --- | --- | --- | --- | --- |
| **Legacy** | Java 8/11/17 per minor | Boot 2.x, Framework 5.x, Security 5.x, `javax.servlet` | Kerberos 1.x/legacy; inspect lockfile. | Migration baseline; **never** carry old web filters into a Jakarta app. |
| **Spring 6 gen 6.3** | Java 17+ | Boot 3.3.x, Framework 6.1.x, Security 6.3.x | Kerberos **2.1.1** docs tested with JDK 17, Security 6.3.0, Framework 6.1.8. | **Candidate**; build and integration-test on actual patch. |
| **Spring 6 gen 6.5** | Java 17+ | Boot 3.5.x, Framework 6.2.x, Security 6.5.x | Kerberos **2.2.0** docs tested with JDK 17, Security 6.5.1, Framework 6.2.8. | Candidate, uses 2.x group; check support status. |
| **Spring 7** | Java 17+ | Boot 4.0/4.1.x, Framework 7.x, Security 7.x | Kerberos **7.1.2** docs tested JDK 17, Security 7.1.2, Framework 7.0.10. | Major migration; uses new group `org.springframework.security`. |
| **Bad mix** | Any | Boot 3/Security 6 with Security 7's Kerberos group/version. | Does not form a valid tested baseline. | Block to fix dependencies. |
| **Bad mix** | Any | Boot 4/Security 7 with Kerberos 2.x. | Risk of duplicate classes/API mismatch. | Do not use as candidate. |

Spring Boot sources state:
- **Spring Boot 3.3.13** requires Java 17+ and Spring Framework 6.1.21+ with Tomcat 10.1/Servlet 6.0.
- **Spring Boot 3.5.16** requires Java 17+ and Spring Framework 6.2.19+.
- **Spring Boot 4.1.2** requires Java 17+ and Spring Framework 7.0.10+ with Servlet 6.1+.
- A branch's patch/framework baseline **does not guarantee** every arbitrary combination is tested; follow the BOM and security support policy of the actual branch.
- Java 21/25 may be LTS options per the support matrix, but real GSS/Krb5 testing is required; **never assume Java 25 is compatible with an older extension just because Java 17 runs it**.

### 3.1. Artifact Metadata Can Be More Authoritative Than GitHub Releases

A repo's GitHub Releases page might show tag `v2.1.0` while Maven Central already holds `org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0`, and Spring docs cite 2.2.0. When checking "latest":
1. Check the **versioned reference docs**, not an unpinned documentation link showing historical behavior.
2. Check Maven Central package/POM/Gradle Module Metadata.
3. Check transitive dependencies (Kerberos 2.2.0 web POM references Spring Security Web 6.5.1, Jakarta Servlet 6.0, Kerberos core 2.2.0).
4. Check the Boot app's real BOM version; never let a transitive version silently "bump" the security stack out of control.
5. Check EOL/security patch policies of the organization and supplier.
6. Security 7 uses Kerberos core/web `7.x` under the new group, **not** by changing the group of artifact `2.2.0` while keeping version `2.2.0`.

### 3.2. Why Is "Java 17 Baseline" Support Alone Not Enough?

A Spring Boot 3 project running on Java 17 yet using old Kerberos 1.x compiled against `javax.servlet.Filter` can still fail. A Boot 4 project running on Java 21 yet pulling `spring-security-core:6.x` onto the classpath alongside Security 7 can fail linkage. The right JDK is necessary, not sufficient.

## 4. Java EE `javax.servlet` Differs from Jakarta `jakarta.servlet`

### 4.1. Imports to Migrate

~~~java
// LEGACY Java EE / Spring Framework 5:
import javax.servlet.Filter;
import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

// Jakarta Servlet / Spring Framework 6+:
import jakarta.servlet.Filter;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
~~~

Those two `Filter` types **are not the same Java type**. Adding both `javax.servlet-api` and `jakarta.servlet-api` to the dependency graph does not make old classes implement the new interface. Filter binaries with old signatures can fail when wired into a Servlet 5/6 container, even if source compiles.

### 4.2. Do Not Change Java SE JAAS/JGSS to Jakarta

~~~java
// Java 17+ Java SE, STILL javax.security.auth:
import javax.security.auth.Subject;
import javax.security.auth.login.LoginContext;
import javax.security.auth.kerberos.KerberosPrincipal;

// Java GSS-API:
import org.ietf.jgss.GSSContext;
import org.ietf.jgss.GSSManager;
~~~

`javax.security.auth.*` lives in Java SE, not the Java EE Servlet API. **There is no rule to replace all `javax.` with `jakarta.`.** Packages truly from Java EE like `javax.annotation`, `javax.validation`, and `javax.persistence` require separate per-framework plans.

### 4.3. Diagnosing Bad Dependencies by Error Message

| Error | Likely Cause | Category |
| --- | --- | --- |
| `ClassNotFoundException: javax.servlet.Filter` | Legacy web filter still uses Java EE on Jakarta runtime. | Wrong web API generation. |
| `ClassNotFoundException: jakarta.servlet.Filter` | Runtime/container lacks Jakarta Servlet. | Missing dependency/container. |
| `ClassCastException` casting old Filter to new Filter | Mixing javax/jakarta binaries. | Migrate library. |
| `NoSuchMethodError` in Spring Security API | Security Core/Web/Config have mismatched major/minor versions. | Version skew. |
| `UnsupportedClassVersionError` | JRE older than classfile target (Java 17=61). | Wrong runtime JDK. |
| `NoClassDefFoundError` creating SPNEGO filter | Missing Kerberos web/core module or transitive class. | Dependency graph. |
| `ExceptionInInitializerError` at JGSS startup | JAAS/Krb5 config or runtime provider issue. | Check root cause. |

## 5. Maven Coordinates and Dependency Management

### 5.1. For Spring Security 6: Kerberos Extension 2.x

~~~groovy
// Spring Boot 3.x, Spring Security 6.x branch:
implementation 'org.springframework.security.kerberos:spring-security-kerberos-core:2.2.0'
implementation 'org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0'
~~~

Example `build.gradle` for a Boot 3.5 lab:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security.kerberos:spring-security-kerberos-core:2.2.0'
    implementation 'org.springframework.security.kerberos:spring-security-kerberos-web:2.2.0'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') { useJUnitPlatform() }
~~~

**Note:** This is a dependency build skeleton; SPNEGO login requires a test KDC/keytab/SPN and does not run end-to-end from dependencies alone. The Boot BOM manages Spring artifacts, not necessarily extension 2.x versions; check resolved graphs/constraints. Do not force Security Core/Web down to 6.5.1 if the Boot BOM selects a higher valid patch, yet never skip binary tests when overriding.

Maven:

~~~xml
<!-- Spring Security 6 / Kerberos 2.2.0 -->
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-core</artifactId>
  <version>2.2.0</version>
</dependency>
<dependency>
  <groupId>org.springframework.security.kerberos</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
  <version>2.2.0</version>
</dependency>
~~~

### 5.2. For Spring Security 7: Modules Under the New Group

~~~groovy
// Spring Boot 4 / Security 7, get version from the exact Security BOM:
implementation 'org.springframework.security:spring-security-kerberos-core'
implementation 'org.springframework.security:spring-security-kerberos-web'
~~~

Maven:

~~~xml
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
~~~

The Spring Security 7 reference confirms dependency coordinates moved group from `org.springframework.security.kerberos` to `org.springframework.security`. Java class packages such as `org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter` can keep their names; **Maven group and Java package are distinct**.

Boot 4 also changes some starter names/layouts; when creating a new Boot 4 app, use Spring Initializr / Boot 4 BOM rather than copying Boot 3 dependencies verbatim. For a Web MVC servlet stack, an illustrative starter setup is:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
repositories { mavenCentral() }
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.security:spring-security-kerberos-core'
    implementation 'org.springframework.security:spring-security-kerberos-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
tasks.named('test') { useJUnitPlatform() }
~~~

**This is a candidate build**; verify the actual Boot 4.x starters/artifacts/BOM; never claim it compiled/ran on an unprovided project. Never mix Kerberos 2.x and 7.x on the same runtime classpath.

### 5.3. Kerberos 2.1.1 and Boot 3.3

Kerberos 2.1.1 docs state it was built and tested with JDK 17, Security 6.3.0, and Framework 6.1.8. That makes it a reasonable candidate for Security 6.3 apps, not proof that any arbitrary Boot 3.3 patch is supported indefinitely. When upgrading Boot 3.3 to 3.5, evaluate moving Kerberos 2.1.x → 2.2.0 and test against the Security/Framework generation rather than picking blindly by higher version numbers.

### 5.4. Use a Single Dependency Generation

~~~text
OK CANDIDATE:
  Boot 3.5.x / Spring Security 6.5.x
  Kerberos group org.springframework.security.kerberos
  Kerberos 2.2.0
  jakarta.servlet 6.0 / Framework 6.2 generation

OK CANDIDATE:
  Boot 4.1.x / Spring Security 7.1.x
  Kerberos group org.springframework.security
  Kerberos 7.1.x / Framework 7 generation
  Servlet 6.1+ / Jakarta

BAD:
  Kerberos web 2.2.0 with Security core 7.1.x
  Kerberos 2.x and Kerberos 7.x both on classpath
  javax.servlet.Filter in Jakarta application
  Spring Security core 6.x alongside Security web 7.x
~~~

## 6. Inspect the Resolved Dependency Graph Instead of Only `build.gradle`

### 6.1. Gradle

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-kerberos-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-security-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency spring-web \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency jakarta.servlet-api \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency javax.servlet-api \
  --configuration runtimeClasspath
~~~

If `javax.servlet` is absent, `dependencyInsight` may return "no dependencies matching"; that is normal in a Jakarta app. Check:
- Requested versus **resolved** versions.
- BOM/platform constraints and conflict resolution.
- `compileClasspath` vs. `runtimeClasspath`.
- Local repositories, internal proxies, dependency locks/checksums.
- Fat JAR / external WAR packaging, duplicate security libraries in shared container classloaders.
- CVEs, support status, artifact provenance, and transitive patch drift.

### 6.2. Maven

~~~bash
mvn -version
mvn help:effective-pom

mvn dependency:tree \
  -Dincludes=org.springframework.security

mvn dependency:tree \
  -Dincludes=org.springframework.security.kerberos

mvn dependency:tree \
  -Dincludes=jakarta.servlet,javax.servlet
~~~

Use Maven Enforcer / Gradle dependency constraints, SBOM, and security scanning to detect skew. Never apply a blanket "forbid all `javax`" rule because the JDK's **`javax.security.auth`** must remain; target only the Java EE API packages/artifacts unused by the target runtime.

### 6.3. Using `jdeps` and `classfile`

~~~bash
# Find external API references from the built JAR.
jdeps --multi-release 17 path/to/kerberos-or-app.jar

# Check classfile major version if encountering UnsupportedClassVersionError.
javap -verbose -classpath path/to/classes \
  org.example.kerberos.KerberosApplication
~~~

Java 8 classfile major=52; Java 11=55; Java 17=61; Java 21=65. `jdeps` has limitations with dynamic reflection/`ServiceLoader`; runtime tests are still required.

## 7. JDK 17: JAAS, JGSS, `krb5.conf`, and Runtime Concerns

### 7.1. Java SE Modules

- `java.security.jgss` provides Java GSS API / Kerberos support on standard JDKs.
- `javax.security.auth.Subject` and `javax.security.auth.login.LoginContext` are valid JAAS APIs.
- `javax.security.auth.kerberos.KerberosPrincipal` is not replaced by Jakarta Servlet.
- `org.ietf.jgss.GSSManager`/`GSSContext` negotiate/accept service tickets.
- If using a custom `jlink` image, verify the JGSS module/provider was not stripped; build JDK and runtime image must match capabilities.
- JDK crypto/default encryption policies change across patches/majors; test the actual enctypes issued by KDC/AD instead of assuming legacy RC4/DES remain enabled.

### 7.2. Java Options and Keytabs

~~~text
JAVA_TOOL_OPTIONS=-Djava.security.krb5.conf=/etc/krb5.conf
APP_KRB_SERVICE_PRINCIPAL=HTTP/portal.example.org@EXAMPLE.ORG
APP_KRB_KEYTAB_PATH=/run/secrets/http-service.keytab
~~~

Use secret mounts/Vault and least-privilege service accounts. `krb5.conf` must be a trusted config; DNS SRV/realm mappings, SPNs, and UTC/NTP clocks must match the KDC. Never print full keytab contents or raw `Negotiate` headers when debugging.

### 7.3. Read-Only Inspection Commands

~~~bash
# View principal/KVNO entries and enctypes without printing secret keys.
klist -k -e /run/secrets/http-service.keytab

# View entry timestamps; NOT an X509-style expiration date.
klist -k -t /run/secrets/http-service.keytab

# With an authorized test TGT/KDC:
kvno -k /run/secrets/http-service.keytab \
  HTTP/portal.example.org@EXAMPLE.ORG
~~~

**Never run `klist -K`**: it can display secret key material. `kvno -k` tests decrypting a service ticket with the keytab, requiring a client credential cache/TGT and reachable KDC/network; if it fails, isolate DNS/clock/principal/enctype before concluding the keytab is corrupt.

### 7.4. Never Rotate KDC Keys in Preflight

MIT `kadmin ktadd` can randomize principal keys and increment KVNO depending on workflow, causing outages on service instances still holding the old keytab. Monitoring and CI must run read-only commands only. Rotation requires a change ticket, KDC/AD admin coordination, overlap, and verified rollback. An old keytab on disk **does not** restore a KDC secret that was already rotated.

## 8. SPNEGO Filter and `SecurityFilterChain` on Spring Boot 3

The example below demonstrates Kerberos 2.2.0 on Spring Security 6. It requires a test KDC, service principal, and real keytab to log in; **it is not a JDK-only Java program**.

### 8.1. Project Structure

~~~text
spnego-upgrade-lab/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/org/example/kerberos/
    │   ├── KerberosApplication.java
    │   ├── KerberosSecurityConfig.java
    │   └── ApiController.java
    └── resources/application.yml
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'spnego-upgrade-lab'
~~~

`KerberosApplication.java`:

~~~java
package org.example.kerberos;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class KerberosApplication {
    public static void main(String[] args) {
        SpringApplication.run(KerberosApplication.class, args);
    }
}
~~~

`application.yml`:

~~~yaml
app:
  kerberos:
    service-principal: "${APP_KRB_SERVICE_PRINCIPAL}"
    keytab-path: "${APP_KRB_KEYTAB_PATH}"

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
        same-site: lax
~~~

### 8.2. `KerberosSecurityConfig.java`

~~~java
package org.example.kerberos;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.io.FileSystemResource;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.kerberos.authentication.KerberosServiceAuthenticationProvider;
import org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator;
import org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter;
import org.springframework.security.kerberos.web.authentication.SpnegoEntryPoint;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.www.BasicAuthenticationFilter;

@Configuration
public class KerberosSecurityConfig {

    @Bean
    UserDetailsService labUsers() {
        // LAB ONLY: never copy hard-coded roles into production.
        return name -> {
            if (!"alice@EXAMPLE.ORG".equals(name)) {
                throw new UsernameNotFoundException("unauthorized");
            }
            return User.withUsername(name)
                .password("{noop}unused-no-password-flow")
                .authorities("APP_READ")
                .build();
        };
    }

    @Bean
    SecurityFilterChain web(
            HttpSecurity http,
            UserDetailsService labUsers,
            @Value("${app.kerberos.service-principal}")
                String servicePrincipal,
            @Value("${app.kerberos.keytab-path}")
                String keytabPath) throws Exception {

        SunJaasKerberosTicketValidator validator =
            new SunJaasKerberosTicketValidator();
        validator.setServicePrincipal(servicePrincipal);
        validator.setKeyTabLocation(
            new FileSystemResource(keytabPath));
        validator.setDebug(false);

        KerberosServiceAuthenticationProvider provider =
            new KerberosServiceAuthenticationProvider();
        provider.setTicketValidator(validator);
        provider.setUserDetailsService(labUsers);

        ProviderManager manager =
            new ProviderManager(provider);

        SpnegoAuthenticationProcessingFilter filter =
            new SpnegoAuthenticationProcessingFilter();
        filter.setAuthenticationManager(manager);

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health", "/error").permitAll()
                .requestMatchers("/api/**")
                    .hasAuthority("APP_READ")
                .anyRequest().denyAll()
            )
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new SpnegoEntryPoint()
                )
            )
            .authenticationProvider(provider)
            .addFilterBefore(
                filter, BasicAuthenticationFilter.class
            )
            .build();
    }
}
~~~

`ApiController.java`:

~~~java
package org.example.kerberos;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ApiController {

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "UP");
    }

    @GetMapping("/api/me")
    public Map<String, Object> me(Authentication auth) {
        return Map.of(
            "authenticated", auth.isAuthenticated(),
            "authType", auth.getClass().getSimpleName()
        );
    }
}
~~~

### 8.3. Design Limitations

- `labUsers` is a fixture only. Production must map verified Kerberos principal + realm → immutable local user ID → active/tenant/role state from a trusted repository; never auto-link by email or grant `ROLE_ADMIN` by default.
- Neither `formLogin` nor `httpBasic` is enabled in the lab above; the `{noop}...` password string must never be used as a login mechanism. Production should completely replace the test `UserDetailsService`.
- `SpnegoEntryPoint` sends `401 WWW-Authenticate: Negotiate`, which is a valid initial challenge, not an error.
- `SunJaasKerberosTicketValidator` requires a valid service principal/keytab and JDK GSS provider; the config snippet does not create a KDC.
- Default local user mapping may receive a principal formatted differently from `alice@EXAMPLE.ORG` depending on realm/validator; confirm in tests rather than matching via substring.
- Never disable CSRF across the entire Spring app to make SPNEGO work. Business POSTs using session cookies must enforce CSRF policies and authorization/tenant checks.
- Do not register the Filter twice outside `SecurityFilterChain`; with multiple chains, specify clear `@Order`/`securityMatcher`.
- Spring Security 7 has different lifecycle APIs/behavior; build, test, and switch to the 7.x dependency group before reusing this code.
- Never log raw HTTP `Authorization: Negotiate` headers, sensitive keytab paths, plaintext KDC creds, or GSS debug output in production.

## 9. HTTP Negotiate Path and Common Outcomes

~~~text
GET https://portal.example.org/api/me
  -> 401 Unauthorized
  <- WWW-Authenticate: Negotiate

Browser receives challenge
  -> acquires KDC-issued service ticket for
     HTTP/portal.example.org@EXAMPLE.ORG

GET /api/me
  -> Authorization: Negotiate <token>

SPNEGO Filter
  -> TicketValidator validates GSS service ticket
  -> UserDetailsService maps verified principal
  -> SecurityContext stores Authentication
  -> Authorization checks local APP_READ
  -> 200 OK or 403 if business role missing
~~~

**An upgrade must distinguish** "browser didn't send a token" from "validator couldn't decrypt the token" and "local authorization denied." Never handle all 401/403s indiscriminately by disabling the filter.

| Symptom | Primary Suspect | Test |
| --- | --- | --- |
| First 401 Negotiate | Usually the expected challenge. | Does the browser send a second request with a token? |
| Repeated 401 without `Authorization: Negotiate` | Browser IWA allowlist, URL origin, proxy, client KDC/TGT. | Trace header presence (redacted). |
| 401 after token | SPN/realm, KVNO/keytab/enctype, clock, Kerberos provider. | KDC test, `kvno -k`, GSS error class. |
| App 403 after auth | Local role, disabled user, tenant restrictions. | Redacted `UserDetailsService`/`AuthorizationManager` logs. |
| 302 form login instead of 401 | Wrong entry point/chain; or intentional fallback. | Filter chain ordering and routing. |
| Only one replica fails | Keytab mounts, JDK/config drift, or clock skew. | Per-node canary. |
| Valid ticket yet wrong user | Realm canonicalization, identity-link error. | Trusted immutable mapping. |

## 10. Standalone Java 17 Tool: Checking Classpath and Modules

This program **compiles/runs on JDK 17 without Spring**, does not contact a KDC, and reads no keys. Output reflects classes on the **current runtime classpath** and does not certify ticket validation passes.

### 10.1. `KerberosClasspathProbe.java`

~~~java
import java.util.List;

public final class KerberosClasspathProbe {

    enum Status {
        PRESENT, MISSING, BROKEN_LINKAGE
    }

    record Probe(String label, String className) {}

    static Status inspect(String className) {
        try {
            Class.forName(
                className, false,
                Thread.currentThread().getContextClassLoader()
            );
            return Status.PRESENT;
        } catch (ClassNotFoundException e) {
            return Status.MISSING;
        } catch (LinkageError e) {
            return Status.BROKEN_LINKAGE;
        }
    }

    public static void main(String[] args) {
        System.out.println("javaFeature=" +
            Runtime.version().feature());
        System.out.println("javaVendor=" +
            System.getProperty("java.vendor"));
        System.out.println("jgssModule=" +
            ModuleLayer.boot()
                .findModule("java.security.jgss")
                .isPresent());

        List<Probe> checks = List.of(
            new Probe(
                "kerberosPrincipalFromJdk",
                "javax.security.auth.kerberos.KerberosPrincipal"
            ),
            new Probe(
                "gssManagerFromJdk",
                "org.ietf.jgss.GSSManager"
            ),
            new Probe(
                "jakartaServlet",
                "jakarta.servlet.Filter"
            ),
            new Probe(
                "legacyJavaxServlet",
                "javax.servlet.Filter"
            ),
            new Probe(
                "springFilterChain",
                "org.springframework.security.web.SecurityFilterChain"
            ),
            new Probe(
                "spnegoFilter",
                "org.springframework.security.kerberos.web.authentication.SpnegoAuthenticationProcessingFilter"
            ),
            new Probe(
                "ticketValidator",
                "org.springframework.security.kerberos.authentication.sun.SunJaasKerberosTicketValidator"
            )
        );

        for (Probe p : checks) {
            System.out.println(
                p.label() + "=" + inspect(p.className())
            );
        }
    }
}
~~~

### 10.2. Running

~~~bash
javac --release 17 KerberosClasspathProbe.java
java KerberosClasspathProbe
~~~

Example output on **standard JDK 17 running with a classpath containing only this program**, without Spring/Servlet JARs (vendor on line two varies by machine):

~~~text
javaFeature=17
javaVendor=<actual-vendor-name>
jgssModule=true
kerberosPrincipalFromJdk=PRESENT
gssManagerFromJdk=PRESENT
jakartaServlet=MISSING
legacyJavaxServlet=MISSING
springFilterChain=MISSING
spnegoFilter=MISSING
ticketValidator=MISSING
~~~

**Do not conclude "MISSING Spring = broken app"** when running `java KerberosClasspathProbe` outside the app classpath. To use it accurately, run the tool on the test/runtime classpath of the built application. `PRESENT` only proves the ClassLoader found the class; if the component isn't wired as a bean or KDC config is wrong, authentication still fails. `BROKEN_LINKAGE` signals deeper version/`NoClassDefFoundError` checks are needed.

## 11. Java 17 Deterministic Compatibility Demo

This is a **preliminary rules program**; it does not query Maven Central, read BOMs, or test a runtime KDC. Its output is `CANDIDATE_TEST_REQUIRED` to remind you that a structurally valid stack still must pass end-to-end tests.

### 11.1. `KerberosUpgradeMatrixDemo.java`

~~~java
public final class KerberosUpgradeMatrixDemo {

    record Stack(
        int javaFeature,
        int bootMajor,
        int securityMajor,
        String kerberosGroup,
        boolean jakartaServlet) {}

    enum Result {
        LEGACY_REVIEW,
        JAVA_BASELINE_FAIL,
        CANDIDATE_TEST_REQUIRED,
        VERSION_MISMATCH
    }

    static Result evaluate(Stack s) {
        if (s.bootMajor() >= 3 && s.javaFeature() < 17) {
            return Result.JAVA_BASELINE_FAIL;
        }

        if (s.bootMajor() == 2
                && s.securityMajor() == 5
                && !s.jakartaServlet()) {
            return Result.LEGACY_REVIEW;
        }

        if (s.bootMajor() == 3
                && s.securityMajor() == 6
                && s.jakartaServlet()
                && "org.springframework.security.kerberos"
                    .equals(s.kerberosGroup())) {
            return Result.CANDIDATE_TEST_REQUIRED;
        }

        if (s.bootMajor() >= 4
                && s.securityMajor() == 7
                && s.jakartaServlet()
                && "org.springframework.security"
                    .equals(s.kerberosGroup())) {
            return Result.CANDIDATE_TEST_REQUIRED;
        }

        return Result.VERSION_MISMATCH;
    }

    static void show(String name, Stack s) {
        System.out.println(name + "=" + evaluate(s));
    }

    public static void main(String[] args) {
        show("legacyBoot2", new Stack(
            11, 2, 5, "org.springframework.security.kerberos",
            false));
        show("java11Boot3", new Stack(
            11, 3, 6, "org.springframework.security.kerberos",
            true));
        show("boot3Kerberos2", new Stack(
            17, 3, 6, "org.springframework.security.kerberos",
            true));
        show("boot4Kerberos7", new Stack(
            21, 4, 7, "org.springframework.security",
            true));
        show("boot3WrongGroup", new Stack(
            17, 3, 6, "org.springframework.security",
            true));
        show("boot4OldGroup", new Stack(
            21, 4, 7, "org.springframework.security.kerberos",
            true));
        show("boot3LegacyServlet", new Stack(
            17, 3, 6, "org.springframework.security.kerberos",
            false));
    }
}
~~~

### 11.2. Run Command and Exact Stdout

~~~bash
javac --release 17 KerberosUpgradeMatrixDemo.java
java KerberosUpgradeMatrixDemo
~~~

~~~text
legacyBoot2=LEGACY_REVIEW
java11Boot3=JAVA_BASELINE_FAIL
boot3Kerberos2=CANDIDATE_TEST_REQUIRED
boot4Kerberos7=CANDIDATE_TEST_REQUIRED
boot3WrongGroup=VERSION_MISMATCH
boot4OldGroup=VERSION_MISMATCH
boot3LegacyServlet=VERSION_MISMATCH
~~~

This section models only **generation rules**, ignoring minor/patch versions, JDK vendor, KDC, and security vulnerabilities. For example, `boot4Kerberos7=CANDIDATE_TEST_REQUIRED` **does not** guarantee all Security 7 artifacts are valid. `legacyBoot2=LEGACY_REVIEW` does not mean legacy Boot 2 is currently supported.

## 12. Migrating Legacy Spring Security Configuration

### 12.1. Do Not Keep `WebSecurityConfigurerAdapter`

Security 5-era code may still contain:

~~~java
// LEGACY / FOR IDENTIFICATION DURING MIGRATION ONLY:
extends WebSecurityConfigurerAdapter
http.authorizeRequests().antMatchers("/**").authenticated();
http.addFilterBefore(spnegoFilter, BasicAuthenticationFilter.class);
~~~

When moving to Security 6/7, use:
- `@Bean SecurityFilterChain`;
- `authorizeHttpRequests` and `requestMatchers`;
- Dedicated `AuthenticationProvider`/`ProviderManager` for Kerberos service tickets;
- `SpnegoEntryPoint` and explicit filter ordering;
- Proper `securityMatcher`/`@Order` when multiple chains exist;
- Spring Security Test and protocol integration tests;
- Preserved session/CSRF/authorization policies, or controlled hardening.

### 12.2. Multiple Filter Chains

~~~text
Chain 1, higher precedence:
  /api/** bearer token authentication, stateless

Chain 2:
  /intranet/** browser SPNEGO, session-aware

Chain 3:
  other routes, explicit public or deny
~~~

If the API chain matches an intranet URL first, the browser may receive only `WWW-Authenticate: Bearer` instead of `Negotiate`. Conversely, an SPNEGO challenge on stateless API machines can cause loops. Test `FilterChainProxy` matching, rule order, and login/logout paths.

### 12.3. SecurityContext Persistence

Custom `SpnegoAuthenticationProcessingFilter` instances expose setters for `SecurityContextRepository`, `SessionAuthenticationStrategy`, and success/failure handlers per Javadoc. When upgrading Security versions, test:
- `Authentication` is stored in the right `SecurityContext`.
- Sessions are created/saved or stateless per contract.
- Session ID rotation prevents fixation.
- `SecurityContext` never leaks across requests, threads, or tenants.
- Logout truly invalidates the local session.
- CSRF on business POSTs remains protected.
- Failed GSS tokens never insecurely retain `Authentication` from a prior session.

Never assume "the framework handles everything" if a custom filter is constructed manually. Verify behavior via integration tests with the real filter.

## 13. Kerberos + Active Directory / MIT KDC: Infrastructure Compatibility

### 13.1. Service Principal Name

~~~text
Public URL: https://portal.example.org
Service principal: HTTP/portal.example.org@EXAMPLE.ORG
Realm: EXAMPLE.ORG
Keytab: /run/secrets/http-service.keytab
JDK: approved Java 17+ runtime
~~~

When a browser accesses a reverse proxy URL, it normally requests a service ticket for the public hostname/SPN, not the internal container host. If the keytab holds `HTTP/pod-1...` while the browser sends a ticket for `HTTP/portal.example.org`, SPNEGO can be rejected. Check DNS/CNAME/canonicalization/KDC realm trust and duplicate SPNs.

### 13.2. KVNO, Enctypes, Keytab Rotation

A keytab **has no `notAfter` date like X.509**. Instead of checking file age:
- List principals, KVNOs, and encryption types (`klist -k -e`).
- Compare against KDC authoritative key version and allowed enctypes.
- Use a service-ticket decryption canary (e.g., `kvno -k`) with an authorized test principal.
- Verify acceptance on every replica; during rotation, old+new key overlap may be used.
- Never invoke `ktadd`/`cpw -randkey` in a monitoring job, as that can alter the long-term KDC principal key/KVNO.
- Never enable DES/RC4 or disable encryption checks arbitrarily during Java/KDC upgrades.

### 13.3. Java/JGSS/OS Policy

- Java patch updates can alter default crypto/enctypes/JGSS behaviors.
- Linux and Windows have different default `krb5.conf`/ticket cache/realm discovery behaviors.
- AD domain-joined browsers/SSPI/Extended Protection can fall back to NTLM if configuration allows it.
- A request succeeding over NTLM **does not prove** Kerberos GSS ticket acceptance; test the real mechanism.
- JDK vendor, CPU architecture, container image, and JGSS modules must be recorded in the release manifest.
- NTP/clock skew affects Kerberos tickets; test expired and not-yet-valid tickets.
- Kerberos LDAP clients (JAAS initiator) and HTTP SPNEGO acceptors are two distinct paths; test separately.
- Fallback login must be IAM-approved, never auto-granting anonymous/admin when the KDC is unavailable.

### 13.4. Server and Proxy

- Reverse proxies must not strip `WWW-Authenticate` / `Authorization` headers belonging to the `Negotiate` flow.
- Configure trusted proxy forwarded host/proto properly so browser/KDC select the right SPN.
- Distinguish HTTP keep-alive, proxy auth, TLS termination, and browser policies where needed.
- Never log raw `Authorization: Negotiate` tokens, even as headers for debugging.
- If one node passes and another fails, compare per-node keytabs/KVNO/env/JDK and credential caches.
- Enable GSS debug flags only briefly on test hosts with verified log sanitization.

## 14. Layered Testing After Upgrade

| Layer | Objective | Tools | Do Not Overclaim |
| --- | --- | --- | --- |
| Static compile | Packages/APIs/bytecode align. | Gradle/Maven, `jdeps`, `javac`. | Does not prove KDC/login. |
| Startup | Beans/filters/providers initialize. | `@SpringBootTest` and test config. | Does not prove ticket validation. |
| Controller | Roles, tenant, CSRF, error status. | MockMvc + Spring Security Test. | Does not prove Kerberos when mocking Authentication. |
| Ticket validator | JAAS/JGSS decrypts tickets. | MiniKdc/MIT/AD sandbox, test keytab. | GSS unit alone does not prove browser flow. |
| Browser E2E | SPNEGO HTTP challenge→token→login. | Domain-joined browser/`curl --negotiate`, proxy, test KDC. | Does not replace production policy testing. |
| Multi-node | Rollout/DR/keytab consistency. | Per-replica canary. | Cannot infer whole cluster from one node. |

### 14.1. `MockMvc` Can Test the 401 Challenge

~~~java
// TEST FRAGMENT: requires a real Spring Security FilterChain
// in the test ApplicationContext and a test keytab config.
mvc.perform(get("/api/me"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        "WWW-Authenticate",
        org.hamcrest.Matchers.containsString("Negotiate")
    ));
~~~

This covers only the initial challenge. `with(authentication(...))` or `@WithMockUser` simulates an already-authenticated user and **bypasses KDC/JAAS ticket verification**. Never report "Kerberos crypto PASS" from a MockMvc 200.

### 14.2. Testing a Real GSS Handshake

Lab sequence:
1. Spin up a disposable test realm/KDC/AD sandbox.
2. Create a test user and service principal/secret via an authorized workflow.
3. Mount the keytab for the service and configure `krb5.conf`/realm/NTP/DNS.
4. Start the target app build; anonymous requests must receive `401 Negotiate`.
5. A client holding a test TGT performs HTTP Negotiate; expect 200 after verified ticket + allowed local account.
6. Wrong keytab/KVNO/principal/realm, expired tickets, clock skew, or tampered tokens → fail closed.
7. Valid Kerberos yet disabled local user / missing authority → deny/403 per policy.
8. Repeat across real OS browsers, proxies, and replicas.
9. Isolate credentials; never use a production KDC or commit test keytabs against policy.

### 14.3. `curl` with an Existing Test TGT

~~~bash
# Lab environment only, with a kinit-authenticated test principal.
curl --negotiate -u : \
  https://portal.example.org/api/me

# Never use --insecure to skip TLS checks.
# Never print raw Authorization tokens into CI logs.
~~~

`curl --negotiate` requires `libcurl` with GSSAPI/SPNEGO support, a credential cache, and a reachable KDC. Command failure can stem from the client `curl` build rather than the app's Kerberos extension.

### 14.4. Why Java 17+ Must Be Tested Specifically

- Java 17 JGSS/ciphers tested against the current KDC may differ from Java 21/25.
- Certificate/SSL/HTTP proxy behavior may change.
- KDCs may reject RC4/DES deprecated in security policies.
- Multi-node apps running different JDK vendors can exhibit different GSS behaviors.
- Build images may include the JGSS module while custom runtime images omit it.
- Container file permissions/SELinux and secret volume mounts can cause JAAS login failures.
- Servlet container upgrades can alter HTTP header parsing and session/cookie behavior.

## 15. CI Testing and Candidate Selection

### 15.1. Suggested Pipeline

~~~text
1. Baseline inventory + target version decision
2. Java runtime & toolchain validation
3. Dependency/BOM lock + SBOM scan
4. javax.servlet vs jakarta.servlet static analysis
5. Compile + JUnit + MockMvc authorization
6. Startup with test keytab
7. KDC-issued ticket acceptor tests
8. Browser/proxy HTTP Negotiate E2E
9. Wrong SPN/KVNO/enctype/clock/tenant negative cases
10. Keytab rotation/replica/DR consistency tests
11. Security review + change approval
12. Canary rollout + telemetry + rollback readiness
~~~

### 15.2. Never Let CI Mutate a Real KDC

- Never run `ktadd`/`cpw` against a production KDC.
- Never print keytabs via `klist -K` or log `Negotiate` tokens.
- Never store secrets in Git or container images.
- Create sandbox realms/test principals with separate lifecycles.
- Provision test keytabs/credentials via secret manager and destroy per policy.
- CI may mutate only disposable test KDCs within granted permissions.
- Retain audits of artifact digests, versions, success/fail classes, and case IDs; never retain raw tickets.
- `KRB_AP_ERR_MODIFIED` errors must be triaged, never auto-fixed by rotating KDC keys.

### 15.3. Before–After Comparison

| Signal | Before | After (candidate) | PASS When |
| --- | --- | --- | --- |
| `java -version` | Old Java | Approved Java 17/21 | Actual runtime valid. |
| Security dependency graph | Legacy | Exact candidate | No skew/duplicates. |
| SPNEGO challenge | 401 Negotiate | 401 Negotiate | Header and chain right. |
| Ticket acceptance | Pass | Pass | Real KDC ticket and keytab. |
| User mapping | Right user/realm | No wrong owner shift | Same trusted mapping. |
| Local roles | Approved permissions | No unexpected elevation | Tenant/resource security. |
| Session/logout | Per old policy | Per approved design | No fixation/leak. |
| Per-node canaries | Good | Good on all nodes | No hidden intermittent failures. |
| Secret handling | Restricted | Restricted | No token/keytab leakage. |

## 16. Detailed Test Matrix

| ID | Scenario | Expected Result |
| --- | --- | --- |
| C01 | Boot 3 running on Java 11. | Blocker: requires Java 17+. |
| C02 | Boot 4 Java 17, Security 7/Kerberos 7 matching BOM. | Candidate; E2E tests mandatory. |
| C03 | Boot 3 + Kerberos 1.x `javax` Servlet. | Reject/migrate to Jakarta binary. |
| C04 | Boot 3 code keeps `javax.security.auth.Subject`. | Normal: Java SE. |
| C05 | Boot 3.3/Security 6.3 with Kerberos 2.1.1. | Candidate per docs; runtime check needed. |
| C06 | Boot 3.5/Security 6.5 with Kerberos 2.2.0. | Candidate; do not skip patch review. |
| C07 | Boot 4/Security 7 using old Kerberos 2.x group. | Reject major mix. |
| C08 | Boot 4/Security 7 using `org.springframework.security` group. | Candidate; must test. |
| C09 | Spring Security Core 6 / Web 7. | Fail dependency skew. |
| C10 | Boot 4/Framework 7 pulls Spring Framework 6. | Fail dependency skew. |
| C11 | Kerberos 2.x and 7.x both at runtime. | Fail duplicate/mixed classes. |
| C12 | Boot 3 WAR on Tomcat 9. | Reject Servlet namespace mismatch. |
| C13 | Boot 4 on Servlet 6.0-only server. | Reject Servlet 6.1+ requirement. |
| C14 | Compile toolchain 17, runtime JDK 11. | `UnsupportedClassVersionError`. |
| C15 | Custom `jlink` missing `java.security.jgss`. | Kerberos unavailable. |
| C16 | `kerberos-core` excluded. | Provider/validator linkage fails. |
| C17 | `kerberos-web` excluded. | Spnego filter missing. |
| C18 | Legacy `WebSecurityConfigurerAdapter` left in Security 6. | Compile fails / migrate. |
| C19 | Legacy `antMatchers`/`authorizeRequests` config. | Migrate to supported DSL. |
| C20 | SPNEGO filter not added to `FilterChainProxy`. | Never accepts valid tickets. |
| C21 | SPNEGO filter runs twice. | Duplicate processing detected. |
| C22 | Wrong `AuthenticationEntryPoint`. | Missing 401 Negotiate on protected route. |
| C23 | Browser receives initial 401 Negotiate. | Expected protocol challenge. |
| C24 | Browser omits token on next request. | Investigate client IWA/trust policy. |
| C25 | Real service ticket decrypts successfully. | Auth succeeds + local policy. |
| C26 | Tampered service ticket. | Reject, no fallback admin. |
| C27 | Wrong SPN `HTTP/backend` hostname. | Reject; fix realm/SPN/proxy. |
| C28 | KDC KVNO 8, node keytab only KVNO 7. | Detect mismatch/canary failure per overlap. |
| C29 | Keytab permission denied. | Startup/GSS fails securely. |
| C30 | CI logs contain keytab contents. | Security QA FAIL. |
| C31 | Script uses `klist -K`. | Security QA FAIL: secret exposure. |
| C32 | Encryption type blocked by JDK/KDC. | Fail; never enable weak ciphers blindly. |
| C33 | Clock skew outside policy. | Kerberos rejects. |
| C34 | Wrong DNS SRV/realm mapping. | KDC lookup fails. |
| C35 | Duplicate AD SPN. | Ticket validation inconsistent/fails. |
| C36 | Reverse proxy strips `WWW-Authenticate`. | Browser never receives challenge. |
| C37 | Reverse proxy strips `Authorization`. | 401 loop. |
| C38 | Negotiate falls back to NTLM instead of Kerberos. | Do not report Kerberos PASS. |
| C39 | Ticket passes, `UserDetailsService` cannot find user. | Deny, no default role. |
| C40 | Kerberos passes, local account disabled. | Deny. |
| C41 | Kerberos passes, user lacks `APP_ADMIN`. | 403 on admin endpoint. |
| C42 | Two realms share same username. | Never auto-link one local user by name. |
| C43 | Email claim matches old account. | Never auto-link. |
| C44 | MockMvc mock authentication returns 200. | Controller passes; does not prove KDC. |
| C45 | MiniKdc lab ticket accepted. | Lab cryptographic integration PASS. |
| C46 | `KerberosRestTemplate` client calls downstream. | Test initiator independently. |
| C47 | Kerberized LDAP bind after Java upgrade. | Test JAAS initiator config. |
| C48 | Java 21 JGSS behavior differs from Java 17. | Requires integration/vendor testing. |
| C49 | Replica A passes, B fails. | Per-node keytab/JDK drift detected. |
| C50 | Session fixation after login. | Session rotation policy tested. |
| C51 | `SecurityContext` fails to persist properly. | Fix repository/strategy. |
| C52 | CSRF disabled to avoid auth errors. | QA FAIL for business POSTs. |
| C53 | Multi-chain bearer captures intranet route. | Fix matcher/order. |
| C54 | Actuator exposes keytab path/subject/user. | Security QA FAIL. |
| C55 | Compile passes while KDC is offline. | Do not infer Kerberos PASS. |
| C56 | `ktadd` in CI preflight alters KDC keys. | Operational FAIL. |
| C57 | Fat JAR embeds service keytab. | Security FAIL. |
| C58 | Roll back old JAR after KDC key rotated. | Rollback may fail to authenticate. |
| C59 | App server shared classloader holds old Spring Security. | Linkage FAIL. |
| C60 | Upgrade to Security 7 without changing Kerberos Maven group. | Resolve/update coordinates. |

### 16.1. Lab A — Dependency Audit

1. Capture `java -version` on the build runner and **runtime container**.
2. Run Gradle/Maven dependency tree; verify Spring Security Core/Web/Config/Kerberos align.
3. Search for `javax.servlet` in source and JAR dependencies; migrate only Java EE types.
4. Confirm JDK's `javax.security.auth` remains valid.
5. Remove legacy `WebSecurityConfigurerAdapter` and switch to `SecurityFilterChain`.
6. Run `KerberosClasspathProbe` on the app classpath and inspect `PRESENT`/`MISSING`/`BROKEN_LINKAGE`.
7. Check WAR's Servlet container, node JVM vendor, and supported versions.

### 16.2. Lab B — Real KDC/SPNEGO

1. Stand up a sandbox KDC/AD realm with a test user and service principal.
2. Mount test keytab and configure SPN/realm, DNS, NTP, and JGSS.
3. GET protected endpoint unauthenticated → `401 Negotiate`.
4. Client with real TGT executes HTTP Negotiate; verify success.
5. Wrong keytab/SPN/KVNO/token/clock → reject.
6. Valid Kerberos user lacking local role → 403.
7. Verify filters, `SecurityContext`, session fixation, CSRF, and logout.
8. Repeat across target JVMs, browsers/OSes, and replicas.

### 16.3. Lab C — Rollout/Rollback

1. Establish error budget baseline: challenge count, auth successes, GSS error classes, role denials.
2. Build target artifact with SBOM/lockfile and sign release digest.
3. Pass staging, then canary 1% traffic / approved cohort.
4. Monitor 401 loops, SPNEGO success, and keytab/KVNO per replica.
5. Avoid rotating KDC keys simultaneously with framework migration when possible.
6. Test JAR rollback and verify session compatibility / old key availability.
7. If rotation is unavoidable, obtain KDC admin approval for overlap/rollback.
8. Expand rollout only when every-node canary and local authorization pass.

## 17. Troubleshooting by Error

### 17.1. `ClassNotFoundException: javax.servlet.Filter`

Legacy web filter or library built for Boot 2/Java EE. Switch to a Jakarta-compatible Kerberos extension and matching Spring stack; never add both `javax` and `jakarta` to mask the mismatch.

### 17.2. `NoSuchMethodError` in Spring Security

`spring-security-core` and `spring-security-web` may be on different major/minor versions, or an extension pulled an old transitive. Use `dependencyInsight` and align the BOM; never fix by forcing an unverified JAR.

### 17.3. `UnsupportedClassVersionError`

Runtime JVM is older than the classfile target. Java 17 classfile is major 61; check `java -version` **inside the actual running container**, not just Gradle compile.

### 17.4. `NoClassDefFoundError: jakarta/servlet/Filter`

Container/runtime lacks the right Jakarta Servlet generation, or a WAR was deployed to an older server. Boot 3 needs a Jakarta container; Boot 4 requires Servlet 6.1+. Never drop `javax` Servlet onto the classpath.

### 17.5. 401 Negotiate Loop

Isolate whether the browser sends the token, whether the proxy forwards headers, and check keytab/SPN/KVNO/enctype/realm/NTP and GSS provider; verify `kvno -k` with a test TGT. Never disable service-ticket verification.

### 17.6. `KRB_AP_ERR_MODIFIED`

Usually points to service principal key mismatch, duplicate SPN, wrong keytab/KVNO, or an encrypted ticket that cannot be decrypted. Coordinate with KDC/AD admin and run per-node checks; never run `ktadd` carelessly.

### 17.7. 403 After SPNEGO Success

Local principal mapping, disabled account, tenant/resource policy, or granted authorities differ from before. This is **authorization**, not necessarily a Kerberos bug. Never fix by granting admin to all Kerberos users.

### 17.8. One Replica Logs In, Another Fails

Compare Java runtimes, keytab mounts/permissions, KVNO/enctypes, `krb5.conf`, DNS, NTP, Spring dependency versions, and filter chains; do not check only a health endpoint.

### 17.9. Windows Browser Fails Login While Linux `curl` Passes

Check browser Intranet allowlists, account/TGT, AD policy, NTLM fallback, and proxy TLS/Channel Binding. Test the real mechanism; never lower security policy just to go "green."

### 17.10. `KerberosRestTemplate` or LDAP Client Fails

These two use cases use Kerberos **initiator** credentials/JAAS rather than the service **acceptor**; even when browser SPNEGO server tests pass, test client paths separately.

## 18. Migration Runbook

### 18.1. P0 — Assessment

Record JDK vendor/patch, Boot/Framework/Security/Kerberos versions, WAR/JAR, container, keytab/SPN, AD/KDC, proxies, browsers, JAAS flags, local `UserDetailsService`, chain ordering, and security/support status. Collect baseline metrics from the pre-upgrade system.

### 18.2. P1 — Select a Verified Target

Use documented tested baselines/BOMs and security patches; choose one concrete target profile without mixing Kerberos 2.x/7.x. If a Java 17 uplift is needed, verify whether the old stack supports it before changing frameworks, or build a parallel environment.

### 18.3. P2 — Upgrade Code and Build

Migrate Java EE imports, remove `WebSecurityConfigurerAdapter`, and align the dependency graph. Verify `SecurityFilterChain`, JAAS/JGSS module, Bean startup, test sources, static analysis, and SBOM. Do not alter keytabs/KDC outside change scope.

### 18.4. P3 — Sandbox KDC Integration

Use real tickets/realm/SPN/keytab; verify 401→Negotiate→success, wrong-ticket failures, and local roles/tenants. Test both the Kerberos service provider and any Kerberos clients/downstream calls.

### 18.5. P4 — End-to-End Staging

Test representative OSes/browsers, HTTPS proxies, domain-joined/KDC tests, and multi-node secret distribution. Verify session handling, CSRF, logout, key-rotation overlap, and attack/negative tests.

### 18.6. P5 — Controlled Production Canary

Roll out per node/cohort and monitor auth successes, 401 loops, KRB error classes, user mapping/role denials, secret leaks, and observed runtime versions. Prepare rollback triggers and KDC coordination.

### 18.7. P6 — Completion

Reconcile target artifacts/actual runtime, finalize release notes/support matrix, keytab versions, runbooks, owner sign-off, zero unexpected role grants, and zero secret logging. Never equate a deploy job `SUCCESS` with `SSO PASS`.

### 18.8. Conditional Rollback

If only JAR/JDK changed while SPN/KDC keys remained untouched, rollback is usually simpler; if the KDC rotated KVNO/password or session serialization changed, the old JAR/keytab may no longer be compatible. KDC admins and app owners must approve KDC state, service keys, and session recovery; **never** mutate KDC keys unilaterally to roll back.

## 19. Production Checklist

- [ ] Source and target versions recorded for JDK, Boot, Framework, Security, Kerberos, and Servlet container.
- [ ] Java runtime >=17 for Boot 3/4; exact runtime container verified.
- [ ] Spring Boot 3/Security 6 uses Kerberos extension 2.x under `org.springframework.security.kerberos`.
- [ ] Spring Boot 4/Security 7 uses Kerberos modules under `org.springframework.security`.
- [ ] Tested baselines Kerberos 2.1.1, 2.2.0, 7.1.x reconciled against the Spring stack.
- [ ] No mixing of Security 6/7 or both Kerberos 2.x and 7.x on the classpath.
- [ ] Java EE `javax.servlet` source migrated to Jakarta; Java SE `javax.security.auth` left untouched.
- [ ] `SecurityFilterChain` replaces `WebSecurityConfigurerAdapter`; filter/provider/entry-point ordering is accurate.
- [ ] Runtime JAAS/JGSS module and JDK crypto policy are compatible with KDC enctypes.
- [ ] Service principal matches public hostname/realm; keytab secret mount has proper ACLs.
- [ ] KVNO/enctype/GSS ticket decryption canary passes on every replica.
- [ ] Never use `klist -K`; never run destructive `ktadd` in CI.
- [ ] HTTP 401 `WWW-Authenticate: Negotiate` → real service ticket → local auth tested.
- [ ] Browser IWA/AD policies, TLS/proxy/DNS/NTP verified in staging.
- [ ] `UserDetailsService` maps by trusted principal+realm with local enabled/tenant/role checks.
- [ ] No fallback default roles or email-only account linking.
- [ ] CSRF, session fixation, `SecurityContext` persistence, logout, and multi-chain tested.
- [ ] MockMvc tests treated as controller-level only; separate KDC integration tests exist.
- [ ] Negative tests cover wrong SPN/KVNO/enctype/expired ticket/disabled user.
- [ ] `KerberosRestTemplate`/LDAP initiator paths tested separately if used.
- [ ] Build/lockfile/SBOM and support/security patch reviews PASS.
- [ ] Runtime never logs keytabs, tickets, credentials, or sensitive PII.
- [ ] Alerts configured for 401 loops/GSS failures, per-node drift, and rollback readiness.
- [ ] Cases C01–C60 or equivalent coverage executed with real evidence.

## Remember

> **Kerberos compatibility checks must span multiple layers: Java/JGSS, Spring Boot/Framework/Security, exact Kerberos Maven group/version, Jakarta Servlet, keytab/KDC/SPN, browser HTTP Negotiate, and local authorization.** The Security 6 branch uses Kerberos extension 2.x under `org.springframework.security.kerberos`; the Security 7 branch uses Kerberos modules under `org.springframework.security`. **`javax.servlet` changes to `jakarta.servlet`, while `javax.security.auth` remains Java SE.** Passing builds or MockMvc does not prove real tickets are verified. Promote upgrades to production only after real Kerberos tickets, local users/permissions, sessions, and every replica pass QA together.

### Official Reference Documentation

- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): Java 17+ and Framework 6.1/Tomcat 10.1.
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): Java 17+ and Framework 6.2.
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): Java 17+, Framework 7, Servlet 6.1+.
- [Spring Framework — Version Compatibility](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions): Java SE, javax/Jakarta generations.
- [Spring Security Kerberos 2.1.1 — Introduction](https://docs.spring.io/spring-security-kerberos/reference/2.1/introduction.html): tested JDK 17, Security 6.3, Framework 6.1.
- [Spring Security Kerberos 2.2.0 — Introduction](https://docs.spring.io/spring-security-kerberos/reference/introduction.html): tested JDK 17, Security 6.5.1, Framework 6.2.8.
- [Spring Security Kerberos 2.2.0 — Configuration](https://docs.spring.io/spring-security-kerberos/reference/ssk.html): SPNEGO filter, provider, JAAS validator, and `UserDetailsService`.
- [Maven Central — Kerberos Web 2.2.0](https://central.sonatype.com/artifact/org.springframework.security.kerberos/spring-security-kerberos-web/2.2.0): Maven coordinates and transitive dependency baseline.
- [Spring Security 7.1 — Kerberos Introduction](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html): new dependency group `org.springframework.security` and JDK 17 baseline.
- [Spring Security — SPNEGO Filter Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoAuthenticationProcessingFilter.html): Jakarta Servlet filter/security context.
- [Spring Security — SpnegoEntryPoint Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/kerberos/web/authentication/SpnegoEntryPoint.html): HTTP 401 Negotiate, fallback support.
- [Spring Security — Servlet Filter Architecture](https://docs.spring.io/spring-security/reference/servlet/architecture.html): `FilterChainProxy` and `SecurityFilterChain`.
- [Spring Security — Getting Spring Security](https://docs.spring.io/spring-security/reference/6.5/getting-spring-security.html): dependency BOM/version management.
- [Spring Boot — Testing Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `ApplicationContext` and MockMvc tests.
- [MIT Kerberos — klist](https://web.mit.edu/Kerberos/krb5-current/doc/user/user_commands/klist.html): keytab metadata and `-K` warning.
- [MIT Kerberos — kvno](https://web.mit.edu/Kerberos/krb5-current/doc/user/user_commands/kvno.html): real service-ticket decryption test.
- [MIT Kerberos — kadmin](https://web.mit.edu/KERBEROS/krb5-1.21/doc/admin/admin_commands/kadmin_local.html): `ktadd` key rotation hazards.
- [Oracle Java 17 — Java GSS-API Guide](https://docs.oracle.com/en/java/javase/17/security/java-generic-security-services-java-gss-api.html): JGSS/JAAS Kerberos.
