# Choosing Compatible Spring Boot, Spring Security, and Protocol Library Versions

**Topic:** Spring Security – federation / Spring Platform. This lesson guides you through choosing a **buildable, runnable, and maintainable version combination** to implement OIDC/OAuth 2.0, SAML 2.0, or Kerberos/SPNEGO with Spring Security.

**Information baseline: 07/11/2026.** The version numbers below are cross-checked against public Spring documentation at the time of writing. When starting a new project or preparing a release, you must re-check patches, dependency BOMs, and support timelines. Do not treat the version examples in this lesson as permanently the "latest version".

## 1. Understanding the Technology Stack Before Choosing Versions

```text
Java/JDK and Maven or Gradle
  └─ Spring Boot (parent or dependency management BOM)
      ├─ Spring Framework (Core, Web MVC/WebFlux, HTTP)
      ├─ Spring Security (Core, Web, Config)
      │   ├─ OAuth2 Client / OpenID Connect login
      │   ├─ OAuth2 Resource Server / JOSE-JWT
      │   ├─ SAML2 Service Provider / OpenSAML
      │   ├─ Kerberos/SPNEGO (when used)
      │   └─ OAuth2 Authorization Server (when issuing tokens itself)
      ├─ Servlet container / reactive runtime
      └─ Jackson, logging, test, intermediary libraries
```

**Spring Boot** coordinates the versions of Spring Framework, Spring Security, foundational libraries, and a number of non-Spring libraries in the `spring-boot-dependencies` BOM. **Spring Security** consists of modules that must be API- and version-compatible. **Protocol libraries** may pull in OpenSAML, XML Signature libraries, Nimbus JOSE/JWT, Java GSS/Kerberos, or Identity Provider (IdP)-specific libraries.

Therefore, the right choice is not "grab the latest Spring Security release and drop it into any Boot version". You need to select a supported **Spring Boot release train**, then let the BOM determine the coordinated versions. A major change can break bytecode, package namespaces, auto-configuration, or assertion/token verification.

Distinguish the roles so you do not choose the wrong starter:

- **OIDC login / OAuth2 Client:** a web application acting as a client/Relying Party, redirecting users to an OpenID Provider to authenticate and receive an authorization code/ID Token.
- **OAuth2 Resource Server:** an API that receives and verifies access tokens (JWT or opaque tokens), without building a web SSO login experience itself.
- **SAML 2.0 SP:** a web application acting as a Service Provider/Relying Party, verifying a SAML Response/Assertion from an IdP.
- **Kerberos/SPNEGO:** a web application using domain/KDC tickets in a Windows Integrated Authentication model.
- **Authorization Server:** your own service issuing authorization codes/access tokens to clients. Do not install it when the application only needs to log in to another IdP.
- **LDAP/SCIM:** directory/provisioning does not replace a web SSO protocol; only add an LDAP/SCIM client if business requirements genuinely call for it.

## 2. Version Matrix as a Starting Point (07/11/2026)

| Released Spring Boot | Spring Framework Managed by Boot | Spring Security Managed by Boot | Minimum Java | Suitable Usage |
| --- | --- | --- | --- | --- |
| **4.1.2** | **7.0.x** line | **7.1.2** | Java **17** | New projects whose supporting libraries and environment are Boot 4-compatible |
| **4.0.9** | **7.0.x** line | **7.0.8** | Java **17** | Systems already on Boot 4.0; need to plan branch update schedule |
| **3.5.16** | **6.2.x** line | **6.5.11** | Java **17** | Existing baseline or transition step before upgrading to Boot 4 |
| **4.2.0-RC2** (preview at check time) | Depends on preview release | Depends on preview release | Read preview requirements | Migration testing; do not default to production before GA |

The Security versions in the table are the values published in the **Managed Dependency Coordinates** of each exact Boot release: Boot 4.1.2 manages core Security artifacts at **7.1.2**, Boot 4.0.9 at **7.0.8**, and Boot 3.5.16 at **6.5.11**. With **Boot 3.5.16**, Spring Authorization Server is a separate **1.5.8** line; with **Boot 4.x**, Authorization Server capabilities are already a module of Spring Security 7.

**Java 17+** is the baseline of the lines listed above. You may choose Java 21 LTS when CI, runtime, SDK, and deployment environments support it; check specific JDK limits in the System Requirements of each patch release. Do not compile with `--release 21` and deploy onto Java 17. Maven/Gradle wrapper, bytecode, native image toolchain, container, and application must share the same target.

**Spring Boot GA does not mean every branch still receives security support.** When locking versions, check the [Spring Support Policy](https://spring.io/support), CVE advisories, release notes, and your organization's actual maintenance policy. Do not use RC/milestone/snapshot releases merely because the major/minor number is higher.

### 2.1. BOM Rules

When using `spring-boot-starter-parent` (Maven) or importing the Boot BOM in Maven/Gradle, dependencies managed by the BOM **do not need a `<version>` or version string declared**. For example, Boot 4.1.2 + `spring-security-oauth2-client` will select Security 7.1.2 from the BOM.

Only override a dependency when there is a specific requirement (security patch, external software compatibility) and it has been evaluated across the entire classpath. Changing `spring-security-core` alone from 7.1.2 to another version while keeping older `spring-security-web`, `config`, and `test` artifacts can cause `NoSuchMethodError` at runtime. If a newer Spring Security version requires a newer Spring Framework version, consult Spring Security's documentation rather than guessing combinations.

**Do not mix Spring Security 6.x and 7.x in the same JVM**; do not mix Framework 6 and 7 in a Spring Boot 4 application. Avoid adding a second BOM that overrides Security/OpenSAML/Nimbus/Jackson versions without analyzing dependency management precedence.

## 3. Library Matrix by Protocol and Boot Version

Starters in the two Boot columns have group `org.springframework.boot` unless another group is explicitly stated.

| Role or Requirement | **Boot 4.1.x / Security 7.1.x** | **Boot 3.5.x / Security 6.5.x** | Accompanying Conditions |
| --- | --- | --- | --- |
| Web MVC/Servlet | `spring-boot-starter-webmvc` | `spring-boot-starter-web` | Boot 4 renames the starter for modular clarity; the old `web` starter remains for migration but is deprecated |
| General Spring Security | `spring-boot-starter-security` | `spring-boot-starter-security` | Only one Security line per BOM |
| **OIDC Login / OAuth2 Client** | `spring-boot-starter-security-oauth2-client` | `spring-boot-starter-oauth2-client` | OP issuer/discovery, client registration, callback, client secret/PKCE |
| **OAuth2 Resource Server** | `spring-boot-starter-security-oauth2-resource-server` | `spring-boot-starter-oauth2-resource-server` | API JWT/opaque token, issuer, audience, key/introspection |
| **SAML 2.0 Service Provider** | `spring-boot-starter-security-saml2` | `org.springframework.security:spring-security-saml2-service-provider` | Requires adding the Shibboleth repository to resolve OpenSAML |
| **OAuth2 Authorization Server** | `spring-boot-starter-security-oauth2-authorization-server` | `spring-boot-starter-oauth2-authorization-server` | Security 7 integrates AS; Boot 3 manages the AS 1.5.x line |
| **Kerberos/SPNEGO** | `org.springframework.security:spring-security-kerberos-core` and `spring-security-kerberos-web` | Extension 2.x line, group `org.springframework.security.kerberos` | Check extension version supporting Security 6.5, JDK, and KDC infrastructure |
| Test Security | `spring-boot-starter-security-test` or `spring-security-test` | `org.springframework.security:spring-security-test` | Test module must match Security runtime major/minor |

**Do not add every starter just because the application says SSO.** A Spring MVC web app using OIDC does not need SAML/OpenSAML; a resource server that only verifies Bearer tokens does not need login client; a B2B portal using SAML should include the SAML SP module. Unnecessary libraries bloat the classpath, increase conflict risk, and add patching overhead.

### 3.1. OIDC and OAuth2 on Boot 4

OIDC login typically uses `spring-boot-starter-security-oauth2-client`, which pulls in the required OAuth2 and JOSE modules. The application must perform Authorization Code according to the specification, validating `iss`, `aud`, signature, expiration, `state`, and `nonce` per flow; public clients use PKCE. Client secrets must not be placed in the browser.

APIs accepting JWTs should use the resource server module; JWTs must be verified against the issuer and the **recipient/access token audience** expected by the API. An ID Token meant for the client to verify user identity **is not automatically an access token** authorized to call APIs. OIDC client and resource server can coexist in one product, but must clearly separate security filter chains and policies.

**Do not manually pick a Nimbus JOSE/JWT version just because an online example shows a higher version number**. The BOM/starter normally resolves the related JOSE stack; if an external library requires a specific version, inspect the runtime graph, release notes, and test against the IdP's actual signing keys/algorithms.

### 3.2. SAML2 SP and OpenSAML

Spring Security's SAML v2.0 web SSO is a **Servlet** integration using `spring-security-saml2-service-provider`. Boot 4.1 provides the `spring-boot-starter-security-saml2` starter, while Boot 3.5 uses the Security module directly. **OpenSAML** requires the Shibboleth Releases repository, so Maven/Gradle must configure, in addition to Maven Central:

```text
https://build.shibboleth.net/maven/releases/
```

Spring Security 7 documentation currently describes `OpenSaml5AuthenticationProvider`. When upgrading from Security 6.x or older SAML extensions, you must check the OpenSAML upgrade, Java API changes, metadata handling, `RelyingPartyRegistration`, signing/encryption configuration, signatures, and authorities mapping. Do not fix dependency errors by forcing an arbitrary `org.opensaml` major version that conflicts with the supported combination.

If the main web stack is **WebFlux**, do not copy Servlet APIs like `HttpSecurity` into `SecurityWebFilterChain` and expect SAML to work. Check support on the exact version; an architecture using a **Servlet identity broker/gateway** in front and OIDC/OAuth2 for the reactive application can be simpler.

### 3.3. Kerberos/SPNEGO and the Maven Group Change

Spring Security Kerberos **7.1.2** is described in official documentation as tested with JDK 17, Spring Security 7.1.2, and Spring Framework 7.0.x. With Security 7, the Maven coordinates changed back to:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-core</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-kerberos-web</artifactId>
</dependency>
```

The Boot 4.1.2 BOM manages those modules at Security **7.1.2**. With Boot 3.5 / Security 6.5, the previous-generation Kerberos extension uses group `org.springframework.security.kerberos` and a standalone 2.x release; **you must read the compatibility/release notes of that specific 2.x extension** before adding a version manually. Avoid using the new Security 7 artifact group in Boot 3.5, or forcing 2.x extension JARs into Boot 4 simply because class names match.

Outside the build, you must also configure the service principal, SPN, keytab, Kerberos realm/KDC, DNS, system clock, and browser HTTP Negotiate. A `401` on an intranet can easily be caused by SPN/keytab or browser settings rather than a version bug.

### 3.4. OAuth Authorization Server, LDAP, and External SDKs

If your product **issues tokens** to other clients, Boot 4.1 uses `spring-boot-starter-security-oauth2-authorization-server` in the Security 7 ecosystem; Boot 3.5 uses `spring-boot-starter-oauth2-authorization-server` with the Spring Authorization Server 1.5.x line managed by the Boot BOM. Do not install Authorization Server 1.5.x JARs and the Security 7 module simultaneously.

Accessing AD via LDAP may require Spring LDAP, but **OIDC/SAML federation with an IdP already connected to AD does not require the application to include an LDAP client**. For third-party IdP SDKs (legacy Keycloak adapters, gateway modules, XML/security libraries), check the vendor's version matrix: especially constraints on Java 17, Jakarta Servlet, Spring Framework 7, Jackson 3, and Spring Security 7. Avoid relying on unmaintained SDKs when Spring Security already provides standard support.

## 4. Choosing a Version Set from Project Requirements

### Step 1 – Identify the Architecture and Identity Boundaries

Before choosing dependencies, answer: Servlet web or WebFlux? Do users log in via OIDC/SAML or Windows Negotiate? Does the API only accept access tokens or also handle interactive login? Are you acting as an Authorization Server yourself? Do partners require specific metadata, signing algorithms, or specialized libraries? Which Java/Maven/Gradle version does CI run? Are you using Spring Cloud or an external servlet container?

Use a simple decision table:

| Question | Output to Record |
| --- | --- |
| Web MVC or reactive? | Appropriate web starter, Servlet or Reactive DSL |
| Federation role? | OIDC client, SAML SP, Kerberos acceptor, JWT resource server, or Authorization Server |
| What does the IdP require? | Issuer/discovery/redirect; metadata/ACS/certificates; SPN/KDC |
| Infrastructure constraints? | Java toolchain, Gradle/Maven wrapper, proxy repository, Tomcat/Jetty |
| Are there SDKs/modules outside the BOM? | Artifact, group, version, compatibility document, owner responsible for updates |
| Production support? | GA branch, security patch cadence, regression and rollback plan |

### Step 2 – Choose a Spring Boot GA Release, Then Cross-Check the BOM

For new projects, choose a supported Boot GA release and key libraries confirmed to be compatible. For example, as of 07/11/2026, **Boot 4.1.2 + Security 7.1.2** is an officially managed pair. For systems that cannot migrate yet, **Boot 3.5.16 + Security 6.5.11** is a baseline example for standardization and upgrade planning; evaluate actual support for the 3.5 branch.

Do not manually pair Boot 3.5 with Security 7.1; do not manually pull Framework 7 into a Boot 3.5 application. When patching outside the BOM for a CVE, perform corresponding dependency and integration testing.

### Step 3 – Select the Minimal Modules for the Exact Role

- Web OIDC: MVC/WebFlux, Security, OAuth2 Client; register the RP with the IdP.
- Bearer API: Security, OAuth2 Resource Server; properly validate JWT/opaque access tokens.
- SAML portal: MVC, Security, SAML2 SP + Shibboleth repository, trust IdP certificate.
- Intranet Kerberos: Security, matching Kerberos extension, and AD/SPNEGO configuration.
- Token issuance: Authorization Server; design client registration, scopes, key rotation, token storage, and policies.

### Step 4 – Verify the Dependency Tree **Before Writing Features**

You must check **the actual resolved versions**, not only the versions visible in `pom.xml`. Maven uses nearest-wins and dependency management, while Gradle has conflict resolution/version constraints; an SDK can pull in unwanted versions. Compare compile classpath and runtime classpath; build on clean CI with the official JDK.

## 5. Maven Example: Spring Boot 4.1.2 + OIDC Login on Servlet MVC

This example consists of Java 17+, XML, and YAML files that must be placed inside **a Spring Boot Maven project**; standalone `javac` cannot compile Spring classes because the classpath is missing. The project **compiles once Maven resolves dependencies**, whereas actual login requires a real IdP and valid credentials; the example has no predetermined stdout.

```text
federation-web/
├─ pom.xml
└─ src/main/
   ├─ java/com/example/federation/
   │  ├─ FederationApplication.java
   │  └─ SecurityConfig.java
   └─ resources/application.yml
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>federation-web</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security-test</artifactId>
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
```

There is no separate `<version>` for the starters or Spring Security: the Spring Boot parent manages them.

`src/main/java/com/example/federation/FederationApplication.java`:

```java
package com.example.federation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FederationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FederationApplication.class, args);
    }
}
```

`src/main/java/com/example/federation/SecurityConfig.java`:

```java
package com.example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/public/**").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate-idp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
        provider:
          corporate-idp:
            issuer-uri: https://idp.example.com/realms/corporate
```

This is an illustrative domain URL: you must replace **issuer-uri** with the real OP, provide `OIDC_CLIENT_ID` and `OIDC_CLIENT_SECRET` via environment variables/secret manager, and register the matching redirect URI `/login/oauth2/code/corporate` at the IdP. When behind a reverse proxy, configure forwarded headers/host/scheme and HTTPS properly to avoid redirect mismatches. `oauth2Login` only provides the authentication mechanism; **role/permission and tenant mapping** must be added according to your system's policies.

In the directory containing `pom.xml`:

```bash
java -version
mvn -version
mvn -DskipTests compile
mvn dependency:tree -Dincludes=org.springframework.security
mvn test
```

In the dependency graph of Boot 4.1.2, expect the managed Security modules to be **7.1.2**. With a real sandbox IdP, run `mvn spring-boot:run` and test login/callback, without claiming the program produces a fixed stdout. If you only need a resource server API, replace the client starter with `spring-boot-starter-security-oauth2-resource-server` and configure the filter chain/resource server settings accordingly.

## 6. Maven Example: Boot 3.5.16 + SAML2 Service Provider

This POM snippet highlights the difference between Boot 3 and 4: SAML on Boot 3.5 uses the `spring-security-saml2-service-provider` module directly; because OpenSAML requires an extra repository, the POM declares Shibboleth Releases. This is a **build example**; you must add the Java application, SAML relying party metadata, trusted certificate, ACS, and `saml2Login` to have a working service.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
           https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>partner-saml</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <repositories>
        <repository>
            <id>shibboleth-releases</id>
            <url>https://build.shibboleth.net/maven/releases/</url>
            <snapshots>
                <enabled>false</enabled>
            </snapshots>
        </repository>
    </repositories>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-saml2-service-provider</artifactId>
        </dependency>
    </dependencies>
</project>
```

Do not manually add version 7.x for SAML SP: the Boot 3.5.16 BOM manages it at Security **6.5.11**. When upgrading to Boot 4.1.2, change `web` → `webmvc`, add `spring-boot-starter-security-saml2`, and verify migration across all APIs/security config/OpenSAML; **Boot 4 still requires the Shibboleth repository**. If CI fails to resolve `org.opensaml`, check your internal Nexus/Artifactory proxy and Maven mirrors first instead of "fixing" it by pulling a different OpenSAML major version.

## 7. Gradle Example: How to Lock a Compatible BOM

For `build.gradle` (Groovy DSL) on Boot 4.1.2, you can use the Spring Boot Gradle plugin and declare the BOM via Gradle `platform`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')
    testImplementation platform('org.springframework.boot:spring-boot-dependencies:4.1.2')

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

If you use the `io.spring.dependency-management` plugin to import the Boot BOM, avoid managing versions with **two conflicting BOMs**. For SAML, add `maven { url 'https://build.shibboleth.net/maven/releases/' }` to `repositories` and the `spring-boot-starter-security-saml2` dependency. Remember to lock the Gradle wrapper according to the System Requirements of the exact Boot patch.

Verification commands on Linux/macOS (on Windows use `gradlew.bat`):

```bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-saml2-service-provider --configuration runtimeClasspath
./gradlew test
```

`dependencyInsight` for SAML only displays the module if the project actually declares the SAML dependency; not finding the matching dependency is not an error in an OIDC build. Check both `compileClasspath` and `runtimeClasspath` when runtime errors occur.

## 8. Practice: Verifying the Dependency Tree / Classpath

### 8.1. Maven

```bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.security
mvn dependency:tree -Dincludes=org.springframework
mvn dependency:tree -Dincludes=org.opensaml
mvn test
```

Read the results in order:

1. Does the parent/BOM version match the chosen architecture?
2. Are `spring-security-core`, `spring-security-config`, `spring-security-web`, `spring-security-oauth2-*`, `spring-security-saml2-service-provider`, and `spring-security-test` on the same version family per the BOM?
3. Is another SDK pulling Security 6 into Boot 4, Framework 6 into Framework 7, or an older OpenSAML version into runtime?
4. Do the artifacts have the right group and name for the Boot major version? Kerberos 7 uses `org.springframework.security`; Boot 3 Kerberos uses the old extension group.
5. Are repositories trusted and builds/releases locked in CI? Tokens, secrets, and IdP metadata/keys must not be hardcoded in POM/YAML.
6. Are `ClassNotFoundException` or `NoSuchMethodError` occurring only in the packaged JAR even though IDE compilation succeeds? If so, inspect the dependency graph **inside the final artifact**.

The Maven BOM manages dependency versions, but if another version is introduced by an explicit dependency or a parent/property override, runtime may differ from expectations. `mvn -U test` checks for metadata updates via Maven's mechanism; `-U` by itself does not solve binary incompatibility.

### 8.2. Gradle

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-security-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency opensaml --configuration runtimeClasspath
./gradlew test
```

Gradle version constraints, BOM plugins, and transitive dependencies can lead to **mismatched** versions when applied together. Watch for `->` markers in the dependency resolution report. Record the dependency graph or SBOM alongside the build/commit to accurately reproduce federation issues in production.

## 9. Upgrading from Boot 3.5 / Security 6.5 to Boot 4.1 / Security 7.1

**A major upgrade requires preparation and testing, not just changing a number in the POM.**

1. **Stabilize the 3.5 baseline:** update to an appropriate patch, keep Java 17+ and Spring Security 6.5, and run all tests. Read [Spring Security Migration 7.0](https://docs.spring.io/spring-security/reference/7.0/migration/index.html) to address deprecated APIs, lambda DSL, and authentication/authorization behavior first.
2. **Audit SDKs outside the BOM:** Spring Cloud, IdP adapters, XML/OpenSAML libraries, Jackson, test frameworks, servlet engine, Jakarta namespace, and any custom starters. Boot 4 changes modularization/auto-configuration and uses Spring Framework 7; do not assume a custom Boot 3 library will be compatible with Boot 4.
3. **Upgrade the Boot parent/plugin and corresponding modules:** pick the same Security 7 BOM line, replace `spring-boot-starter-web` with `webmvc`, update OAuth2 Client/Resource Server/Authorization Server starters to Boot 4 names, and update the SAML2 starter for Boot 4.
4. **Update Kerberos/Authorization Server:** verify the new Kerberos Security 7 group, replace AS 1.5.x modules with the corresponding Security 7 module; remove old adapter imports/code if no longer valid.
5. **Update code and configuration:** Boot 4 modularization/Jackson 3/Servlet API; Security 7 changes several DSL/APIs and defaults. For applications older than Boot 3, the `javax.servlet.*` → `jakarta.servlet.*` migration must follow the Boot 3 path rather than "patching" it by putting both APIs on the classpath.
6. **Test against real/sandbox federation:** OIDC redirect, discovery, callback, session/CSRF; SAML metadata, ACS, signature validation, certificate rotation; Kerberos ticket/SPN; resource server audience/issuer; auth server token endpoint if applicable.
7. **Canary/rollback:** keep deployed artifacts and IdP configuration compatible, monitor login errors; do not rotate certificates/client secrets one-way before confirming you can roll back. Document an ADR for the version pair and dependencies.

Security patches can make token/assertion verification stricter; an IdP sending non-compliant messages may be rejected after an upgrade. Investigate validation errors, metadata, issuer/audience, and signatures. **Do not disable signature verification, audience/issuer checks, state, or CSRF just to "get the system running again".**

## 10. Common Error Matrix When Choosing Wrong Combinations

| Symptom | Possible Cause | Verification Step |
| --- | --- | --- |
| `NoSuchMethodError` or `NoClassDefFoundError` | Mismatched Framework/Security line, class moved to another package, or wrong exclusion | Read stack trace + runtime dependency tree, compare against Boot BOM |
| `ClassNotFoundException: javax.servlet...` | Legacy SDK/adapter not migrated to Jakarta for Boot 3+/4 | Upgrade to a `jakarta.servlet`-compatible SDK, check Servlet/container |
| Maven cannot download `org.opensaml` | Missing Shibboleth Releases or unconfigured internal proxy | Add the proper repository and check mirror/TLS/network |
| SAML login fails after upgrade | OpenSAML API or wrong metadata/certificate/ACS/issuer/audience | Test sandbox IdP, inspect filtered validation errors, compare exact assertion |
| OIDC reports missing client registration | Wrong OAuth2 Client starter for Boot major, missing config, issuer lacks discovery | Inspect build graph, client registration, metadata endpoint, and redirect URI |
| Every API request returns 401 | Access token has wrong issuer/audience, key/algorithm, or API is verifying an ID Token | Check `iss`, `aud`, key/JWKS, opaque introspection, and API policy |
| SPNEGO works on some machines only | Browser does not send Negotiate, wrong SPN/keytab/DNS/KDC/time | Check domain join, service principal, ticket, realm, Kerberos extension version |
| Security unit tests fail while app builds | `spring-security-test` differs from runtime or test auto-config changed | Use test module from the same BOM, update `MockMvc`/`WebTestClient` config |
| Local passes, CI fails | Different JDK/wrapper/Gradle plugin, repository mirror/cache, stale locked dependencies | Compare `java -version`, wrapper, resolved graph, clean build |
| Login succeeds but permissions are wrong | Authentication differs from authorization, missing issuer/tenant/role mapping | Test least privilege and cross-tenant isolation; do not trust all IdP claims blindly |

A `401` code or callback failure can originate from the IdP, proxy, clock, claims, or configuration; **never conclude it is a "version bug" without evidence from the dependency tree and error logs.**

## 11. QA Checklist Before Selecting/Approving a Version Combination

**Versions and build**
- [ ] Spring Boot is a GA release supported by the organization; release notes and security advisories have been reviewed.
- [ ] Java runtime/toolchain, Maven/Gradle wrapper, and servlet container meet that Boot release's requirements.
- [ ] Spring Framework/Security/Crypto/Web/OAuth2/SAML2/Test do not mix major versions or drift outside the BOM.
- [ ] Actual resolved versions have been verified in `dependency:tree` / `dependencyInsight`; SBOM/build metadata is saved.
- [ ] Shibboleth repo is configured when using SAML; Kerberos extension uses the right Maven group and version.
- [ ] No client secrets, signing private keys, keytabs, tokens, or SAML assertions are exposed in logs/build output.

**Protocol checks**
- [ ] OIDC Authorization Code login works; callback, issuer, audience, signature, expiry, state/nonce/PKCE follow the flow properly.
- [ ] Resource server rejects access tokens with wrong issuer/audience, expired tokens, or insufficient scope; ID Tokens are not used to call APIs.
- [ ] SAML SP rejects assertions with wrong issuer, signature, recipient/audience, expired timestamps, or replay; certificate rotation has been tested with partners.
- [ ] Kerberos SPNEGO is tested on both domain-joined and non-domain machines; KDC, SPN/keytab, and time drift errors are handled properly.
- [ ] Roles/tenants are mapped from trusted identities rather than auto-granting permissions based on matching email/domain.
- [ ] Logout, session timeout, IdP outage, MFA/step-up, reverse proxy HTTPS, and rollback are verified.

**Choosing safe versions also depends on ecosystem-wide support**: Spring Boot may compile, while an IdP provider, browser, proxy, third-party SDK, or extension does not yet support the new major version. Deploy only when test evidence covers critical real-world integrations.

## 12. Four Selection Scenarios

**A. New Spring MVC Web App + OIDC IdP + Java 21:** You can choose **Boot 4.1.2/Security 7.1.2** via the BOM with starters `webmvc` + `security` + `security-oauth2-client`. Add resource server on separate APIs if needed; do not manually pin Nimbus. Register redirects, verify JWT/OIDC tokens, and implement tenant mapping.

**B. B2B SAML Portal Currently on Boot 3.5.16:** Use **Security 6.5.11** managed by the BOM and `spring-security-saml2-service-provider` with the Shibboleth repo. Moving to Boot 4.1 requires testing SDKs, OpenSAML, SAML metadata/ACS/certificates, and switching to the appropriate starter; avoid mixing Security 7 into Boot 3.5.

**C. Intranet Requiring Windows Integrated Authentication:** On Boot 4.1.2 use Kerberos group `org.springframework.security` line **7.1.2**. On Boot 3.5/Security 6.5 use the older extension group 2.x line verified for compatibility. Both still require valid SPN, keytab, domain/browser/KDC setup; if mobile/Internet access is required, consider OIDC via an AD-connected IdP.

**D. Building Your Own Authorization Server:** With Boot 3.5 use the older Authorization Server starter managed at 1.5.x; Boot 4.1 uses `spring-boot-starter-security-oauth2-authorization-server` belonging to Spring Security 7. Never put both generations on the same classpath. An application that only uses an existing IdP does not need to deploy an Authorization Server.

## 13. Official Documentation to Review on Every Upgrade

1. [Spring Boot – Stable Releases](https://docs.spring.io/spring-boot/) and [System Requirements](https://docs.spring.io/spring-boot/system-requirements.html).
2. [Spring Boot 4.1 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/4.1/appendix/dependency-versions/coordinates.html) and [Spring Boot 3.5 – Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.5/appendix/dependency-versions/coordinates.html).
3. [Spring Boot – Build Systems/Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html).
4. [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide).
5. [Spring Security – Getting Spring Security](https://docs.spring.io/spring-security/reference/getting-spring-security.html) and [Migration to 7](https://docs.spring.io/spring-security/reference/7.0/migration/index.html).
6. [Spring Security – SAML2 Service Provider](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html).
7. [Spring Security – Kerberos](https://docs.spring.io/spring-security/reference/servlet/authentication/kerberos/introduction.html).
8. [Spring Security – Releases](https://spring.io/projects/spring-security) and [Spring Support Policy](https://spring.io/support).

**Remember:** Choose the **Spring Boot branch + patch** first; use the **BOM to align Spring Security/Framework and protocol libraries**; add only the starter matching the role; verify the **dependency graph, IdP integration, and regression tests** before declaring compatibility.