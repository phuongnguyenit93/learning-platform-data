# Distinguishing Standalone Spring Authorization Server History from Spring Security Integration

Spring Authorization Server (SAS) was previously developed and released as a separate project by the Spring Security team. Starting with Spring Security 7.0, the Authorization Server component was brought into the Spring Security project itself. This is a change in where it is developed, released, and documented; it does not mean applications must replace the entire OAuth 2.0 model, rewrite clients, or turn Authorization Server into a different service.

For the **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** module, concepts such as RegisteredClient, authorization, consent, token endpoint, PKCE, refresh token, JWK, and OIDC remain foundational. This article belongs to the **Upgrade and Migration** chapter, helping you accurately identify both library generations, choose compatible dependencies, and plan an application migration from the standalone SAS 1.x line to Spring Security 7.x.

## 1. Development History and Transition Milestones

Before SAS, the Spring ecosystem had the Spring Security OAuth project, usually identified by artifacts from the legacy Spring Security OAuth group. That project was superseded for building modern Authorization Servers. Spring Authorization Server is the successor project, led by the Spring Security team, developed to provide an OAuth 2.1 Authorization Server foundation for the Spring community.

SAS 1.0 was officially released in November 2022. Standalone development helped the project rapidly complete OAuth 2.0 and OpenID Connect features while stabilizing APIs before deep integration into Spring Security. The 1.5.x line is the final generation of the standalone SAS project.

In September 2025, the Spring team announced moving Spring Authorization Server into Spring Security 7.0. Starting with this generation, source code, Javadoc, reference documentation, issues, and pull requests for OAuth2 Authorization Server are managed alongside Spring Security. Spring Security 7.0 incorporates Authorization Server as a module of the project itself.

| Phase | Development and Release Location | Version Line | Interpretation |
|---|---|---|---|
| Legacy Spring Security OAuth | Former Spring Security OAuth project | Legacy 2.x lines | Predecessor technology, not SAS |
| Standalone Spring Authorization Server | Spring Authorization Server repository | 1.0.x through 1.5.x | Separate project maintained by the Spring Security team |
| Authorization Server in Spring Security | Spring Security repository and documentation | Starting from 7.0 | Authorization Server module integrated into Spring Security |

Do not refer to Spring Authorization Server 1.5.x as Spring Security 6.5 Authorization Server. The two projects are closely related and released according to a compatibility matrix, but they have separate version numbers and release cycles. Similarly, legacy Spring Security OAuth and Spring Authorization Server 1.x are two distinct generations.

A common way to read the generation matrix is that SAS 1.5.x pairs with Spring Security 6.5.x and Spring Framework 6.2.x; Spring Security 7.0.x pairs with Spring Framework 7.0.x and is commonly used with Spring Boot 4.0.x. These are generation pairings for orientation, not a rule replacing the BOM. Check the dependency management of the exact Spring Boot or Spring Security version your application selects.

## 2. What Does "Standalone Project" Mean?

In the 1.x era, Spring Authorization Server had its own repository, reference documentation, issue tracker, and release versions. Applications added the SAS dependency to a Spring application to expose OAuth/OIDC endpoints. "Standalone" describes how library development and releases were organized; it does not mean SAS is a server running separately from your Spring application.

An application using SAS 1.x still runs inside Spring Boot or Spring Framework, using the Spring Security filter chain, RegisteredClientRepository, OAuth2AuthorizationService, JWKSource, and storage components configured by the application. Operationally it may be deployed as an independent application, but the SAS library is a dependency embedded within that application.

When moving to Spring Security 7.0, the Authorization Server components continue to be provided as a module and artifact. The main change is that source code ownership, documentation, and releases shift to Spring Security. There is no requirement to create a separate process or change the protocol between clients and the Authorization Server.

## 3. Dependencies Before and After Integration

One point clearly announced by Spring is that the Maven coordinates of the Authorization Server library retain the same groupId and artifactId; what changes is the version. The direct artifact looks like:

~~~groovy
dependencies {
    // Example using a release from the standalone SAS 1.5.x line
    implementation("org.springframework.security:spring-security-oauth2-authorization-server:1.5.0")
}
~~~

When using the Authorization Server inside Spring Security 7.0, the direct artifact keeps those coordinates and moves to version 7.0.x:

~~~groovy
dependencies {
    implementation("org.springframework.security:spring-security-oauth2-authorization-server:7.0.0")
}
~~~

Versions 1.5.0 and 7.0.0 illustrate the two generations and are not a recommendation to pin the first patch release in production. Use a patch version aligned with your support policy and let the Spring Security BOM or Spring Boot dependency management select synchronized versions.

If using Spring Boot in the manner recommended in the Spring Security 7 documentation, you can add the starter:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-oauth2-authorization-server")
}
~~~

Or with Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
</dependency>
~~~

The starter manages dependencies and auto-configuration according to the corresponding Spring Boot version. If the application does not use Spring Boot, you can declare the Spring Security Authorization Server artifact directly.

Do not add multiple versions of the Authorization Server artifact simultaneously or mix the starter with a manually declared dependency of a different version. Inspect the dependency tree to confirm there is only one Authorization Server line and that Spring Security modules belong to the same generation.

## 4. Differences in Configuration and APIs

Most Spring Authorization Server classes keep their names and packages when moving to Spring Security 7.0. The Spring team noted only minor package changes. Therefore, most applications can retain components such as RegisteredClient, RegisteredClientRepository, OAuth2AuthorizationService, OAuth2AuthorizationConsentService, AuthorizationServerSettings, JWKSource, and token customizers.

However, Spring Security 7.0 brings the Authorization Server DSL into HttpSecurity. Configuring the Authorization Server filter chain using the new DSL looks like:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http
        .oauth2AuthorizationServer(authorizationServer -> {
            http.securityMatcher(authorizationServer.getEndpointsMatcher());
            authorizationServer.oidc(Customizer.withDefaults());
        })
        .authorizeHttpRequests(authorize ->
            authorize.anyRequest().authenticated()
        )
        .exceptionHandling(exceptions ->
            exceptions.defaultAuthenticationEntryPointFor(
                new LoginUrlAuthenticationEntryPoint("/login"),
                new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
            )
        );

    return http.build();
}
~~~

This is the filter chain configuration for protocol endpoints. The application still needs an appropriate filter chain to handle form login, user authentication, and remaining requests. If the application already has multiple SecurityFilterChains, preserve the proper order and matchers so Authorization Server endpoints are handled by the dedicated chain.

Some configurations in SAS 1.x projects use Authorization Server's own configuration API, such as applying default configuration or using SAS's configurer. When moving to 7.0, switch to the integrated DSL described in the Spring Security 7 documentation. Do not rename classes in bulk by guessing; read compiler errors, check imports, and consult the Javadoc for the exact version.

Beyond the Authorization Server DSL, this is also a major upgrade of Spring Security. General Spring Security 7 changes can affect the same application, such as removal of deprecated HttpSecurity configuration APIs, replacement of old matchers, and changes to serialization APIs. Follow the Spring Security migration guide as well, not just Authorization Server import fixes.

## 5. Upgrade Roadmap from SAS 1.5.x to Spring Security 7.0

Perform the upgrade in small steps to isolate whether a change belongs to dependencies, APIs, or protocol behavior.

### Step 1: Record the Running Baseline

Collect the following details from the build and deployment environment:

- Spring Boot, Spring Framework, and Spring Security versions.
- Standalone SAS version in use and actual dependency tree.
- Java runtime, database driver, and related OAuth/OIDC libraries.
- SecurityFilterChains, chain ordering, and endpoint matchers.
- Customizers, authentication providers, token generators, and JWKSource.
- Persistence type used for RegisteredClient, authorizations, and consents.

Do not look only at versions declared in the build file. Dependency management or dependency constraints can change the versions resolved at build time.

### Step 2: Choose the Target Generation

If the application is still on Spring Security 6.x, you can continue using a SAS 1.x line compatible with that generation while preparing for the upgrade. If moving to Spring Security 7.0, upgrade both the Spring Security foundation and Authorization Server as a synchronized change.

Spring Security 7 requires Java 17 or higher. In the Spring Boot ecosystem, moving to Spring Security 7 typically accompanies a new Spring Boot generation compatible with Spring Framework 7. Select Boot, Framework, Security, and Authorization Server versions via the official BOM; avoid upgrading a single Security module independently beyond the application's generation.

### Step 3: Update Dependencies and Remove Duplicate Versions

Switch the direct artifact version to the 7.0.x line or use the corresponding Spring Boot starter. Then run dependency insight to verify:

- SAS 1.5.x is no longer on the runtime classpath.
- There are not two versions of Authorization Server.
- All Spring Security modules belong to the same generation.
- No older dependency pulls Spring Security 6.x into the application.

If the build uses a version catalog, dependency constraints, or an internal BOM, update the version management source so subsequent builds do not reintroduce the old version.

### Step 4: Migrate Filter Chain Configuration

Migrate the Authorization Server SecurityFilterChain to the integrated DSL in Spring Security 7. Re-verify:

- The matcher covers only Authorization Server protocol endpoints.
- The chain has the appropriate priority order.
- OIDC is enabled if the application provides OpenID Connect.
- Unauthenticated HTML requests are routed to the appropriate login page.
- Other application endpoints remain in their corresponding chains.

If the application has custom endpoints or changed endpoint URIs, re-verify the matcher and AuthorizationServerSettings.

### Step 5: Handle Package Changes and Compilation

The Spring team expects only minor package relocations. Use the compiler to pinpoint exactly which imports need changing. After updating:

- Remove old imports that no longer exist.
- Check bean types and method signatures of customizers.
- Check extension points that subclass Authorization Server classes.
- Check test sources and test fixtures because they may also reference old packages.

Do not create same-named adapter classes merely to preserve old imports. If an API moved packages, use the official class in the new package.

### Step 6: Verify Behavioral Changes

Spring Security 7.0 enables PKCE by default in OAuth 2.0 Authorization Server. This can change outcomes for clients that previously did not send a code challenge. Re-check all RegisteredClients and client integrations:

- Public clients must send PKCE with S256.
- Confidential clients may also be affected by the new default; check client settings configuration and requirements for each client type.
- Test authorization requests missing `code_challenge` and token requests with an invalid `code_verifier`.
- Do not disable PKCE globally just to keep a single legacy client working.

At the same time, review other major Spring Security 7 changes such as removal of deprecated APIs, HttpSecurity DSL changes, and Jackson serialization changes. Default PKCE applies to clients using the Authorization Code flow, including confidential clients if they use Authorization Code; it is not a step of the Client Credentials grant.

### Step 7: Test Persistence and Issued Data

If using JDBC, check the schema and how authorization data is serialized. If the application has a custom ObjectMapper, custom JdbcOAuth2AuthorizationService, or stores authorization JSON in a custom format, test reading data created by the previous version.

Spring Security 7 switches Spring Authorization Server to Jackson 3 by default. The migration documentation notes that the serialization format of Jackson 3 support is compatible with the deprecated Jackson 2 format, so data serialized with Jackson 2 can be read with Jackson 3 support. If the application configures its own ObjectMapper, migrate from SecurityJackson2Modules to JsonMapper.Builder and SecurityJacksonModules per the guide. If you need to continue using deprecated Jackson 2 support, you must proactively manage Jackson 3 and Jackson 2 dependencies according to the migration guide.

Default format compatibility does not guarantee that every custom serializer, subtype, or application database schema is compatible. Back up the database before upgrading, test reading records created by the old version, then test writing new records and reading them back with the new version.

If running a rolling deployment across multiple instances, do not let two generations share a database for an extended period if serialization or transaction behavior has not been proven compatible. Choose an upgrade window, deployment strategy, and rollback capability accordingly.

## 6. Post-Upgrade Test Matrix

| Area | Checks to Run | Pass Criteria |
|---|---|---|
| Discovery | OAuth/OIDC metadata and JWKS | Issuer, endpoints, and public keys are accurate |
| Client registration | Read existing RegisteredClient and create new client | Client ID, grants, scopes, redirect URIs, and authentication methods are preserved |
| Authorization Code | Login, consent, state, and redirect URI | Authorization codes are issued only to valid clients |
| PKCE | Valid S256, missing challenge, invalid verifier | PKCE policy is enforced properly |
| Client Credentials | Valid and invalid client secret | Tokens are issued only to authenticated clients |
| Refresh Token | Refresh, rotation, and replay | New/old tokens obey configured policy |
| OIDC | ID Token, UserInfo, logout if enabled | Claims, issuer, signatures, and endpoints are accurate |
| Signing key | Sign JWT and verify via JWKS | Key ID and public key match; old tokens continue to be handled per policy |
| Persistence | Read old data, write new data, restart | RegisteredClient, authorization, and consent remain retrievable |
| Security chain | Login page, protocol endpoints, and other APIs | No request is handled by the wrong chain |

Include both integration tests running through the HTTP filter chain and persistence tests against a test database. Unit tests for token customizers or validators cannot replace protocol endpoint testing.

## 7. Deployment and Rollback Plan

Before production deployment:

1. Create a reproducible build from a tested commit.
2. Back up the database and signing key configuration.
3. Verify issuer, client registrations, and redirect URIs in staging.
4. Run full authorization, token, refresh, OIDC, and persistence tests.
5. Verify existing Resource Servers and clients continue validating tokens issued by the new Authorization Server.
6. Monitor token endpoint error rates, `invalid_client`, `invalid_grant`, latency, and signature verification errors after deployment.

Rollback is not just reverting dependencies to the old version. If the new version wrote data in a different format or changed authorization state, you must know whether the old version can read that data. Keep backups and test backward readability in staging. If data compatibility cannot be guaranteed, use a deployment strategy with clear restore points rather than running two generations writing to the same data store simultaneously.

Keep the issuer and signing keys unchanged per operational policy during version upgrades. If you change the issuer or keys at the same time, clients and Resource Servers may reject currently valid tokens. Separate platform upgrades from trust configuration changes to make risk isolation easier.

## 8. Misconceptions to Avoid

- **Confusing standalone SAS with legacy Spring Security OAuth:** Spring Authorization Server is the successor project to the legacy Authorization Server, not merely an artifact rename.
- **Thinking SAS 1.5.x is a separate server:** it is a library embedded inside a Spring application.
- **Thinking moving into Spring Security 7 changes the entire API:** most classes and packages are preserved, though there are minor package relocations and DSL changes to handle.
- **Guessing artifactId changes:** the direct artifact keeps its groupId and artifactId, while the version changes by generation.
- **Upgrading only the SAS dependency:** Spring Security 7 is a major generation requiring synchronized module upgrades and framework-wide migration steps.
- **Overlooking default PKCE:** legacy clients may encounter authorization errors if they do not satisfy the new policy.
- **Assuming databases are automatically compatible:** you must test schemas, serialized authorizations, and custom persistence.
- **Putting Spring Security 6.x and 7.x in the same runtime:** avoid having multiple generations of the same module on the classpath.

## 9. Migration Completion Checklist

- Confirmed whether the application is currently using legacy Spring Security OAuth or Spring Authorization Server 1.x.
- Recorded Spring Boot, Spring Framework, Spring Security, SAS, and Java runtime versions.
- Explicitly decided whether to stay on a compatible SAS 1.x or move to Spring Security 7.x.
- Dependency tree contains only one generation of Authorization Server and Spring Security.
- Authorization Server filter chain uses the DSL suited to the new generation.
- Package relocations have been updated based on compiler errors and official documentation.
- PKCE is tested with public clients and remaining clients.
- RegisteredClient, consent, authorization, token signing, and OIDC endpoints work after upgrade.
- Database and legacy serialized authorizations have been tested against the new version.
- Existing Resource Servers and OAuth2 Clients continue working with issued tokens.
- Backups, deployment plan, and rollback procedure are verified.

## 10. Official References

- [Spring Authorization Server moving to Spring Security 7.0](https://spring.io/blog/2025/09/11/spring-authorization-server-moving-to-spring-security-7-0/) — historical announcement, rationale for moving the project, Maven coordinates, and scope of package changes.
- [What’s New in Spring Security 7.0](https://docs.spring.io/spring-security/reference/7.0/whats-new.html) — confirms Authorization Server as a Spring Security 7.0 module and related behavioral changes.
- [Spring Security 7.0: Getting Started with Authorization Server](https://docs.spring.io/spring-security/reference/7.0/servlet/oauth2/authorization-server/getting-started.html) — dependencies, starter, filter chain, and required beans.
- [Spring Security Migration Guide](https://docs.spring.io/spring-security/reference/migration/) — preparation and migration steps when upgrading Spring Security generations.

By clearly understanding the boundary between the standalone SAS project and the Authorization Server module inside Spring Security, the development team can select the right generation of dependencies, preserve protocol stability, and control the changes genuinely needed during an upgrade.
