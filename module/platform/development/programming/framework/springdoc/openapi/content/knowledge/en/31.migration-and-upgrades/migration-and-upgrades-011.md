# Re-verifying Security, Proxy, UI, and CI Spec Export After Upgrading

Upgrading Spring Boot, Spring Security, or springdoc-openapi can change how an application publishes API documentation, how requests traverse a reverse proxy, how Swagger UI fetches the OpenAPI document, and how CI pipelines generate JSON/YAML files. An application can start successfully while documentation returns 401/403, Swagger UI renders a blank page, OAuth redirects to internal HTTP, server URLs expose container hostnames, or CI archives an empty document by mistake.

After every upgrade, verify the entire documentation flow from runtime to consumers. This guide focuses on four areas:

1. **Security:** who can view OpenAPI docs, open Swagger UI, and execute Try it out?
2. **Reverse proxy:** are host, scheme, port, context path, and public prefix detected accurately?
3. **Swagger UI:** do the UI, configuration, OAuth redirect, and API docs URL still work?
4. **CI export:** does the pipeline generate the right document, validate, diff, and store the artifact for the commit being built?

## 1. Why re-verify after upgrading?

Components have independent lifecycles. A change in one layer can break another:

~~~mermaid
flowchart TD
    A["Browser / API consumer"] --> B["Reverse proxy / ingress"]
    B --> C["Spring Security filter chain"]
    C --> D["Spring Boot web server"]
    D --> E["springdoc-openapi"]
    E --> F["OpenAPI JSON/YAML"]
    E --> G["Swagger UI"]
    H["CI build"] --> I["Start app with docs profile"]
    I --> E
    F --> J["Validate / semantic diff"]
    J --> K["Store release artifact"]
~~~

Examples:

- Spring Security changes matchers, unexpectedly protecting /v3/api-docs.
- The reverse proxy changes how it sends X-Forwarded-*; OpenAPI servers emit internal URLs instead of public URLs.
- A springdoc major upgrade changes starters, default paths, or Swagger UI assets.
- The API docs path is changed while springdoc.swagger-ui.config-url still points to the old path.
- CI runs a different profile from production, causing the OpenAPI file to miss operations or include internal endpoints.
- Gradle/Maven plugins no longer launch the application the old way after a version bump.

Checking whether the application returns HTTP 200 is not enough. Verify that the right users receive the right documentation, right URLs, and right content.

## 2. Determine the springdoc branch by Spring Boot

Before checking configuration, confirm the platform version and starter:

| Spring Boot | springdoc branch | Migration notes |
|---|---|---|
| 2.x and 1.x | springdoc 1.8.0 is the final open-source line | Do not use 2.x/3.x starters |
| 3.x | springdoc 2.x | Use the matching springdoc-openapi-starter-* starters |
| 4.x | springdoc 3.x | Re-check starters, transitive dependencies, and Spring Framework 7 changes |

Do not simply bump the dependency version and assume the migration is complete. Inspect the dependency tree to catch two springdoc branches coexisting, overridden swagger-core versions, or old Swagger UI WebJars pulled in.

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-ui --configuration runtimeClasspath
~~~

Record values before and after upgrading:

- Spring Boot and Spring Framework.
- springdoc starter and swagger-core version.
- Bundled Swagger UI assets.
- Spring Security.
- Web server (Tomcat, Jetty, or Reactor Netty).
- Java runtime and Gradle/Maven wrapper.

springdoc's official compatibility matrix clearly distinguishes Boot 2, Boot 3, and Boot 4. Follow documentation for your active branch rather than copying properties from another major's guide.

## 3. Re-verify security for OpenAPI and Swagger UI

Default endpoints typically served by springdoc:

| Endpoint | Content |
|---|---|
| /v3/api-docs | OpenAPI document in JSON format |
| /v3/api-docs.yaml | OpenAPI document in YAML format |
| /v3/api-docs/swagger-config | Configuration used by Swagger UI to load documents |
| /swagger-ui.html | Entry URL for the Swagger UI interface |
| /swagger-ui/** | HTML, JavaScript, CSS, and UI assets |

Actual paths can differ if the application sets a context path or customizes springdoc properties. Verify endpoints after configuration rather than assuming default paths always apply.

### Choose an access policy per environment

Before upgrading, determine which model applies to API documentation:

- Public documentation: anyone can view docs, while business APIs still enforce separate authorization.
- Internal documentation: only internal users or internal networks are permitted to view docs.
- Restricted production documentation: disable Swagger UI and/or API docs in production, exporting artifacts only in CI.
- Documentation behind SSO: require login and specific permissions for developers or operators.

An OpenAPI document can reveal internal paths, schema names, authentication flows, responses, and unpublished operations. Allowing read access to docs does not grant permission to invoke APIs, yet this information can still aid attack-surface reconnaissance.

### Example: separate security chain for internal docs

The example below requires the API_DOCS role for Swagger UI and API docs, while other requests pass through the application chain:

~~~java
@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain apiDocumentation(HttpSecurity http) throws Exception {
        return http
            .securityMatcher(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs",
                "/v3/api-docs.yaml",
                "/v3/api-docs/**"
            )
            .authorizeHttpRequests(authorize -> authorize
                .anyRequest().hasRole("API_DOCS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain application(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

This is an example for a Servlet application using Basic Authentication for docs and form login for the application. Replace the authentication mechanism to match your real system. If using an OAuth2 Resource Server, SSO, or an API gateway, align matchers and filter chains with that mechanism.

securityMatcher scopes the requests handled by the first chain; requestMatchers inside the chain enforce authorization. The second chain handles only requests that did not match the first chain. @Order precedence is critical.

If documentation is meant to be public, use permitAll() specifically on the documentation paths. Never open all of /** just to make Swagger UI work. Likewise, do not add web.ignoring() for all static resources if doing so bypasses required security filters.

### Check CSRF and Try it out

Swagger UI can issue GET, POST, PUT, PATCH, and DELETE requests via Try it out. If the application uses session/cookie authentication, Spring Security CSRF protection can block state-changing requests when the UI omits a CSRF token.

After upgrading, check:

- Does the Swagger UI page load?
- Does Authorize pass credentials using the right scheme?
- Do GET requests succeed?
- Do POST/PUT/PATCH/DELETE requests include a CSRF token when required by the app?
- Does the API return 401, 403, or 404 in each scenario?

Never disable CSRF globally just to make Try it out work. For session-based applications, integrate tokens via Spring Security's CSRF mechanism. For stateless APIs using bearer tokens, only consider exempting specific API matchers from CSRF when the auth architecture genuinely does not rely on automatically sent cookies.

springdoc provides CSRF configuration for Swagger UI, including enabling support and cookie/header names. Example:

~~~yaml
springdoc:
  swagger-ui:
    csrf:
      enabled: true
      cookie-name: XSRF-TOKEN
      header-name: X-XSRF-TOKEN
~~~

The cookie and header names must match the application's actual CSRF configuration. Check these properties in the documentation for your active springdoc branch.

## 4. Check CORS after changing domains or proxies

If Swagger UI is served from one origin and the API from another, browsers enforce CORS. Requests carrying an Authorization header or non-simple content types trigger preflight OPTIONS requests.

Spring Security requires CORS handling before authorization so preflight requests are not rejected due to missing cookies/sessions. You can configure CORS:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();
    configuration.setAllowedOrigins(
        List.of("https://docs.example.com")
    );
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
    );
    configuration.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-XSRF-TOKEN")
    );
    configuration.setAllowCredentials(true);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", configuration);
    return source;
}
~~~

In the Security chain:

~~~java
http.cors(Customizer.withDefaults());
~~~

Permit only genuinely required origins. When allowCredentials is true, do not use a wildcard origin. If Swagger UI and the API share the same origin, do not enable CORS merely because Swagger UI is in use.

## 5. Check forwarded headers and reverse proxies

When running behind an ingress, load balancer, or reverse proxy, the application may see:

~~~text
http://10.20.0.15:8080/internal
~~~

Whereas consumers must access:

~~~text
https://api.example.com/platform
~~~

Proxies may forward headers:

- Forwarded per RFC 7239.
- X-Forwarded-Host.
- X-Forwarded-Port.
- X-Forwarded-Proto.
- X-Forwarded-For.
- X-Forwarded-Prefix.

These headers affect redirects, generated HTML/JSON links, and server URLs inferred by springdoc. If the application mishandles them, Swagger UI may fetch API docs from an internal host or send Try it out requests over HTTP instead of HTTPS.

### Spring Boot 3.x properties

Spring Boot 3.5 uses server.forward-headers-strategy:

~~~yaml
server:
  forward-headers-strategy: NATIVE
~~~

Common values:

| Value | Meaning |
|---|---|
| NONE | Ignore forwarded headers |
| NATIVE | Use the web server's native handling |
| FRAMEWORK | Use Spring Framework's ForwardedHeaderFilter or ForwardedHeaderTransformer |

NATIVE usually fits when Tomcat/Jetty/Netty supports the headers sent by the proxy. FRAMEWORK applies Spring Framework's general handling when the web server does not cover it.

### Spring Boot 4.x properties

Spring Boot 4 moved to a new namespace:

~~~yaml
server:
  request:
    header:
      forwarded:
        strategy: web-server
        use-prefix: true
~~~

Current strategy options:

| Value | Meaning |
|---|---|
| none | Ignore forwarded headers |
| web-server | Use web server support |
| framework | Use Spring Framework forwarded header support |

In Boot 4, use-prefix: true enables processing X-Forwarded-Prefix. By default this prefix is ignored. If a proxy strips /platform before forwarding to the application without restoring the prefix, Swagger UI and OpenAPI links may omit the public path segment.

Do not retain server.forward-headers-strategy unchanged when moving from Boot 3 to Boot 4 without verifying the new properties. The old property may no longer bind as expected.

### Only trust forwarded headers from trusted proxies

Clients can spoof forwarded headers if a proxy fails to strip user-supplied headers and rewrite canonical values. Configure the ingress/proxy to:

1. Strip or overwrite Forwarded and X-Forwarded-* from external requests.
2. Regenerate headers from the actual connection and route config.
3. Allow the application to accept traffic only from trusted proxies.
4. If using Tomcat, configure appropriate trusted/internal proxies.
5. Never configure trust-all proxies in production.

Do not blindly enable forwarded-header processing when an application is directly reachable from the Internet.

### Check context path and prefixes

If the application uses server.servlet.context-path, spring.webflux.base-path, or proxy prefix stripping, verify actual paths in all four places:

- Swagger UI URL.
- swagger-config URL.
- /v3/api-docs or custom API docs path URL.
- servers in the OpenAPI document.

If servers are statically declared via @OpenAPIDefinition, those values may not reflect request-derived URLs. After upgrading, inspect the actual JSON document instead of assuming forwarded headers will fix every server URL automatically.

## 6. Check springdoc and Swagger UI paths

Key properties:

~~~yaml
springdoc:
  api-docs:
    path: /v3/api-docs
    enabled: true
  swagger-ui:
    path: /swagger-ui.html
    enabled: true
    config-url: /v3/api-docs/swagger-config
    oauth2-redirect-url: /swagger-ui/oauth2-redirect.html
~~~

YAML property names use kebab-case; properties in application.properties can use the corresponding dot notation.

After upgrading, verify:

- Does springdoc.api-docs.path match the path permitted by security matchers?
- Does springdoc.swagger-ui.config-url point to the actual swagger-config endpoint?
- Does the OAuth redirect URL use the right host, HTTPS scheme, context path, and prefix?
- Does the reverse proxy rewrite URLs and return proper MIME types for JavaScript/CSS?
- Are two different versions of Swagger UI dependencies accidentally packaged together?

If you change the API docs path without updating security matchers or config-url, Swagger UI may load HTML yet fail to load the OpenAPI document.

### UI options to re-verify

| Property | What to verify |
|---|---|
| springdoc.swagger-ui.path | Does the HTML path redirect cleanly |
| springdoc.swagger-ui.config-url | Does the config URL exist and allow access |
| springdoc.swagger-ui.oauth2-redirect-url | Does the OAuth callback use the right public URL |
| springdoc.swagger-ui.try-it-out-enabled | Is Try it out enabled by default per policy |
| springdoc.swagger-ui.supported-submit-methods | Which HTTP methods are allowed from the UI |
| springdoc.swagger-ui.persist-authorization | Are credentials retained across refreshes |
| springdoc.swagger-ui.deep-linking | Do tag/operation links work |
| springdoc.swagger-ui.doc-expansion | Is default expansion level appropriate |

tryItOutEnabled controls only the initial default state. supportedSubmitMethods restricts submittable methods; an empty array disables Try it out without removing operations from the document. When configuring through Spring Boot, use the springdoc.swagger-ui prefix and property names supported by your springdoc version; YAML can use kebab-case matching Swagger UI's camelCase option names.

Do not enable queryConfigEnabled merely for the convenience of overriding config via URL. This option has been disabled since springdoc 1.6.0 due to associated security advisories.

### Credential persistence

persistAuthorization is disabled by default. If enabled, Swagger UI can retain Authorize credentials across page refreshes. Before keeping this option after migration, assess:

- Are shared computers or kiosk browsers used?
- Are tokens stored longer than intended?
- Do logout and session expiry policies clear credentials from the UI?
- Does the OAuth flow use PKCE where appropriate?

Do not use persistAuthorization to work around lost tokens without evaluating credential storage risks.

## 7. Re-verify OpenAPI security schemes

Swagger UI displays the Authorize button solely based on security schemes described in the OpenAPI document. Spring Security protects runtime requests; @SecurityScheme and security document the mechanism. Both layers must agree.

Bearer JWT example:

~~~java
@Configuration
@OpenAPIDefinition(
    security = @SecurityRequirement(name = "bearerAuth")
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {
}
~~~

After upgrading, inspect the JSON:

- Does components.securitySchemes.bearerAuth still exist?
- Is root- or operation-level security scoped accurately?
- Did public endpoints accidentally receive a security requirement?
- Are endpoints requiring specific roles/scopes clearly documented?
- Does Swagger UI send Authorization: Bearer ... properly?

Declaring a security scheme does not enable runtime authentication. Conversely, Spring Security may enforce login while OpenAPI omits security declarations, leaving client generators unaware of how to send credentials.

## 8. Enable or disable documentation per environment

API docs endpoints and Swagger UI can be toggled independently:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

If production must not serve documentation, place this config in the production profile and verify /v3/api-docs, /v3/api-docs.yaml, /v3/api-docs/swagger-config, /swagger-ui.html, and /swagger-ui/** are all unreachable.

If a pipeline needs to generate docs, use a dedicated profile:

~~~yaml
# application-openapi.yml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: false
~~~

CI needs only the API docs endpoint; there is no need to expose Swagger UI. This reduces the UI surface inside the temporary export process.

Do not use the openapi profile to accidentally enable management or debug endpoints absent in production. Compare the profile configuration against deployment config and document intentional differences.

## 9. Export OpenAPI in CI after upgrading

CI aims to generate artifacts from the exact commit, exact profile, and exact API group. With springdoc-openapi-gradle-plugin 2.x, the generateOpenApiDocs task starts the application, fetches the document, and stops the application automatically. Legacy 1.x tasks forkedSpringBootRun/forkedSpringBootStop are no longer used in 2.x.

Kotlin DSL configuration example:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "4.2.0"
    id("org.springdoc.openapi-gradle-plugin") version "2.1.0"
}

openApi {
    apiDocsUrl.set("http://localhost:8080/v3/api-docs")
    outputDir.set(layout.buildDirectory.dir("openapi"))
    outputFileName.set("service-openapi.json")
    waitTimeInSeconds.set(90)

    customBootRun {
        args.set(listOf("--spring.profiles.active=openapi"))
    }
}
~~~

The example Spring Boot version must match the release used in your project; do not copy this version number if the project has not upgraded to Boot 4.2. The plugin requires Gradle 8.0 or newer. Starting from plugin 2.1, the build must declare the Spring Boot Gradle plugin explicitly.

Run:

~~~bash
./gradlew clean test generateOpenApiDocs
~~~

Result with the configuration above:

~~~text
build/openapi/service-openapi.json
~~~

If the application has multiple groups, configure groupedApiMappings and store each document as a separate artifact. Do not merge public/admin/partner APIs into one file if they have different audiences or policies.

### Configure stable profiles and ports

CI must control:

- The Spring profile used to generate documentation.
- Port and context path of the temporary application.
- Custom API docs path.
- Test databases/services the app needs to start.
- Feature flags that alter controllers or schemas.
- Server URL and forwarded headers.
- Security profile allowing the CI process to fetch docs.

If CI uses a random port, apiDocsUrl must receive the actual port or use a job-dedicated fixed port config. Avoid two concurrent jobs colliding on the same port on one runner.

Do not let the CI task depend on an already-running app from a previous step when the plugin is configured to start the app itself. Doing so can cause the task to fetch a document from a stale process or another environment.

## 10. Validate and compare files after exporting

After generating the document, verify the file exists, is non-empty, and parses cleanly:

~~~bash
test -s build/openapi/service-openapi.json
jq -e '.openapi and .info.title and (.paths | length > 0)' \
  build/openapi/service-openapi.json
~~~

Basic checks to verify:

- openapi has a valid version value.
- info.title and info.version match the release.
- servers contains URLs matching the published environment.
- paths is non-empty and includes all expected operations.
- components.securitySchemes and security match policy.
- No out-of-scope internal/admin endpoints appear.

Next, run an OpenAPI validator matching the document version and a semantic diff against the reviewed baseline. If breaking changes exist, CI should produce a report and require review; never auto-update the baseline just to turn the pipeline green.

Example semantic diff check with oasdiff:

~~~bash
oasdiff validate build/openapi/service-openapi.json
oasdiff breaking \
  api/openapi-baseline.yaml \
  build/openapi/service-openapi.json
oasdiff changelog \
  api/openapi-baseline.yaml \
  build/openapi/service-openapi.json
~~~

Store the OpenAPI file and diff report as artifacts tied to the commit/build number. A CI artifact does not mean documentation has been published to the production portal.

## 11. Sample pipeline

A pipeline can separate build, export, validate, and artifact archiving:

~~~yaml
steps:
  - name: Build and test
    run: ./gradlew clean test

  - name: Generate OpenAPI
    run: ./gradlew generateOpenApiDocs

  - name: Validate OpenAPI
    run: oasdiff validate build/openapi/service-openapi.json

  - name: Check breaking changes
    run: >
      oasdiff breaking --fail-on ERR
      api/openapi-baseline.yaml
      build/openapi/service-openapi.json

  - name: Upload OpenAPI artifact
    uses: actions/upload-artifact@v4
    with:
      name: openapi-description
      path: build/openapi/service-openapi.json
~~~

This is a GitHub Actions example; other CI systems can swap the upload step for their matching artifact store. Ensure the oasdiff command is available on the runner and pinned per project policy.

Also record metadata:

- Commit SHA.
- Build number.
- Spring Boot and springdoc versions.
- Spring profile and API group.
- OpenAPI info.version.
- Snapshot creation date.

Do not include secrets, tokens, or sensitive environment variables in artifact metadata.

## 12. Post-upgrade regression test matrix

Run the same test matrix before and after upgrading:

| Category | Check | Expected result |
|---|---|---|
| Security | Unauthenticated user accesses internal docs | 401 or 403 per policy |
| Security | User with docs role accesses docs | 200 |
| Security | User with docs role calls unauthorized business API | 403 |
| Security | API docs disabled in production profile | Endpoint not served |
| Proxy | Access via HTTPS public hostname | Redirects and links use HTTPS |
| Proxy | Access via public prefix | UI and API docs preserve prefix |
| Proxy | Direct access with spoofed Internet headers | Proxy strips/overwrites untrusted headers |
| UI | Swagger UI loads HTML, JS, CSS | No 404 or MIME errors |
| UI | Swagger config and OpenAPI document | Loads right URL and API group |
| UI | Authorize with bearer/OAuth | Sends right credentials and redirect URI |
| UI | Try it out GET and write operations | Results match auth, CSRF, and CORS policies |
| Export | CI generates JSON/YAML file | File exists, non-empty, valid syntax |
| Export | servers and paths | Right public URL and operations |
| Contract | Semantic diff against baseline | Breaking changes flagged and reviewed |
| Artifact | File and report archived | Tied to exact commit/build |

### Smoke test with curl

Check API docs endpoints:

~~~bash
curl -i https://api.example.com/v3/api-docs
curl -i https://api.example.com/v3/api-docs.yaml
~~~

Check Swagger UI:

~~~bash
curl -I https://api.example.com/swagger-ui.html
curl -I https://api.example.com/swagger-ui/index.html
curl -I https://api.example.com/v3/api-docs/swagger-config
~~~

If documentation is protected, run both unauthenticated requests and requests with valid credentials. Record status codes and redirect Location headers. Do not test only in a browser with an active session because stale sessions can mask authentication errors.

### Check OpenAPI server URL through proxy

Fetch the document via the public URL and inspect the servers field:

~~~bash
curl -fsS https://api.example.com/platform/v3/api-docs \
  | jq '.servers, (.paths | keys[0:5])'
~~~

The output must use the hostname, scheme, and prefix consumers actually call. If servers is hard-coded, inspect the declared annotation/configuration instead of tweaking only forwarded headers.

## 13. Targeted checks for common configuration changes

| Post-migration change | Common regression | How to verify |
|---|---|---|
| Spring Boot 3 to 4 | Old forwarded-header property no longer in right namespace | Check server.request.header.forwarded.* |
| springdoc 2 to 3 | Starter, dependencies, and UI assets changed major | Check dependency tree and default endpoints |
| Spring Security major upgrade | Matchers or filter chain behavior changed | Test each role with MockMvc or live HTTP |
| Context path changed | Swagger config URL missing context path | Check redirects and Network tab |
| Added ingress prefix | X-Forwarded-Prefix ignored | Enable prefix support matching Boot version |
| Enabled new OAuth2/SSO | Wrong redirect URI or CORS origin | Test authorization code/PKCE and callbacks |
| Docs path changed | Old security matcher or config-url | Check both swagger-config and JSON/YAML |
| Gradle plugin upgraded | Task lifecycle or output path changed | Run task on clean runner and inspect artifact |
| API group changed | Export contains only one group or wrong filter | Check each file and path set |

## 14. Troubleshooting

| Symptom | Possible cause | Resolution |
|---|---|---|
| /v3/api-docs returns 401 | Endpoint sits behind authentication | Check security matchers and access permissions |
| /v3/api-docs returns 403 even when logged in | Missing authority/role or CSRF on unsafe requests | Check roles and HTTP method |
| Swagger UI HTML opens as blank page | Wrong config URL or document URL | Inspect Network/Console and fetch swagger-config directly |
| Swagger UI returns 404 after deploy | Lost context path or proxy prefix | Check redirects and forwarded prefix |
| servers contains http://localhost:8080 | Forwarded headers unhandled or servers hard-coded | Check proxy and OpenAPI configuration |
| OAuth callback hits internal host | Scheme/host inferred incorrectly | Check forwarded host/proto and registered redirect URI |
| Try it out reports CORS error | Origin, method, or Authorization header not allowed | Configure explicit CORS and handle preflight before security |
| Try it out POST returns 403 | Missing CSRF token or insufficient role | Check CSRF integration and authorization |
| Swagger UI lacks Authorize button | OpenAPI missing security scheme | Check components.securitySchemes and security |
| CI exports an empty file | App not ready, wrong profile, or API docs disabled | Check startup logs, wait time, and docs profile |
| CI export missing operations | Different profile, group, or path filter | Compare config and path set against baseline |
| CI fetches document from stale app | Port occupied by another process | Use dedicated port, clean up processes, and check process logs |
| Artifact uses internal URL | CI generated document from internal host/port | Configure server URL for artifact or export via test proxy |
| Large diff after upgrading springdoc | Schema serialization or model converter changed | Validate, semantic diff, and review schemas |
| Production still exposes docs unexpectedly | Disable profile not loaded or config overridden | Check effective configuration and smoke test production profile |

## 15. Repeatable migration workflow

Before upgrading:

1. Save current OpenAPI snapshot.
2. Record endpoints, security policy, Swagger UI config, and public server URLs.
3. Save dependency tree and Spring Boot/springdoc/Security versions.
4. Record smoke test results through the proxy and on the internal network.
5. Record output paths and CI export commands.

After upgrading:

1. Confirm the dependency graph holds only one matching springdoc branch.
2. Verify effective configuration, especially forwarded headers and API docs paths.
3. Run security tests for docs, UI, API, and relevant roles.
4. Access through an actual reverse proxy or staging environment with equivalent config.
5. Open Swagger UI and check config URL, Authorize, OAuth redirect, and Try it out.
6. Generate JSON/YAML from CI using the agreed profile and groups.
7. Validate documents and check servers, paths, security, and schemas.
8. Run semantic diff against the pre-upgrade snapshot.
9. Review breaking changes and update the baseline once approved.
10. Publish artifacts only after all mandatory checks pass.

Keeping pre/post-upgrade results helps trace issues that surface only in staging or production.

## 16. Migration completion checklist

- [ ] Spring Boot and springdoc are on a compatible branch.
- [ ] Dependency tree has no unintended duplicate or overridden starters or swagger-core.
- [ ] API docs path and Swagger UI path verified.
- [ ] Security matchers cover docs, config, and static UI assets accurately.
- [ ] Permission to view docs is separated from permission to invoke business APIs.
- [ ] CSRF is not disabled globally just to support Try it out.
- [ ] CORS preflight runs before authorization when cross-origin is used.
- [ ] OpenAPI security schemes match runtime authentication.
- [ ] OAuth redirect URL uses the right HTTPS host and public prefix.
- [ ] Forwarded-header properties match the Boot major version.
- [ ] Proxy strips/overwrites untrusted forwarded headers.
- [ ] X-Forwarded-Prefix is handled when the proxy strips prefixes.
- [ ] servers in the document use the expected public URL.
- [ ] Swagger UI loads swagger-config and OpenAPI documents accurately.
- [ ] persistAuthorization and queryConfigEnabled reviewed per security policy.
- [ ] Production profile disables or protects docs intentionally.
- [ ] CI generates docs from the designated commit/profile/group.
- [ ] JSON/YAML artifacts parse cleanly and contain all operations.
- [ ] Semantic diff reviewed prior to updating baseline.
- [ ] Reports and artifacts archived with the commit/build.

## 17. Official references

- [springdoc-openapi Compatibility](https://github.com/springdoc/springdoc-openapi#compatibility): choose springdoc branch by Spring Boot.
- [springdoc-openapi v2 Properties](https://springdoc.org/v2/properties.html): configuration for Spring Boot 3.x.
- [springdoc-openapi Core Properties](https://springdoc.org/core-properties.html): current API docs configuration.
- [Swagger UI Properties](https://springdoc.org/ui-properties.html): path, config URL, OAuth redirect, Try it out, CSRF, and UI options.
- [Spring Boot 3.5 – Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): server.forward-headers-strategy and forwarded headers.
- [Spring Boot 4 – Running Behind a Front-end Proxy](https://docs.spring.io/spring-boot/how-to/webserver.html): server.request.header.forwarded.* and forwarded prefix.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): matchers and authorization rule ordering.
- [Spring Security – CORS](https://docs.spring.io/spring-security/reference/servlet/integrations/cors.html): handling preflight before security.
- [springdoc-openapi Gradle Plugin](https://github.com/springdoc/springdoc-openapi-gradle-plugin): generateOpenApiDocs and export configuration.

## Conclusion

A migration is complete when the application both runs properly and publishes the right contract in real environments. Check security for every documentation endpoint, forwarded headers and prefixes behind reverse proxies, Swagger UI along with OAuth/CSRF/CORS, and generate OpenAPI from CI using controlled profiles and API groups. In particular, proxy properties in Spring Boot 3 and Boot 4 use different namespaces; retaining old config after a major upgrade can break server URLs and redirects even while the app returns 200. Finally, validate documents, verify servers/paths/security, run semantic diffs against the baseline, and archive commit-tagged artifacts before publishing.
