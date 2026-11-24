# Verifying Specifications and UI Assets on the Real Native Build

A Spring Boot application running on the JVM does not prove the native image build works properly either. A native image is produced via AOT processing and reachability analysis; classes, methods, resources, or reflection accesses not recognized may be absent from the final executable. Because springdoc-openapi generates documentation from application metadata and Swagger UI also loads static assets, both capabilities must be verified on the exact native binary or container that will be deployed.

This lesson focuses on post-build native verification: checking OpenAPI configuration, JSON/YAML endpoints, document groups, Swagger UI HTML, JavaScript, CSS, and custom assets. It also covers handling OpenAPI annotations stripped during native compilation, adding runtime hints when evidence shows missing resources or reflection, comparing JVM/native outputs, and automating smoke tests in CI.

## 1. Why Must the Native Build Be Tested Separately?

In JVM mode, class loaders, reflection, and classpath resource reads are generally more flexible. Native images are constructed via static analysis and AOT; parts not identified as reachable can be stripped from the executable or lack runtime access registration.

Areas related to springdoc requiring verification:

- Controllers, request mappings, and method metadata.
- DTOs, generic types, Swagger annotations, and Bean Validation.
- OpenAPI configuration, security schemes, and OpenApiCustomizers.
- GroupedOpenApi beans.
- Schemas generated via Jackson or model converters.
- JSON and YAML endpoints.
- Swagger UI assets packaged inside the WebJar.
- Custom logos, CSS, JavaScript, or static OpenAPI files added by the application.
- Reflection, proxy, or resource accesses arising from custom integrations.

A passing JVM test only proves the flow works on the JVM. A passing native build only proves the compiler produced an executable. Neither proves endpoints and assets are served properly once the native binary starts.

## 2. Distinguishing AOT, Native Executable, and Native Container

Three related yet distinct concepts:

| Component | Role |
|---|---|
| AOT processing | Analyzes ApplicationContext at build time and generates required code/hints |
| Native executable | Binary compiled for the target operating system and architecture |
| Native container image | Container packaging the native executable along with required runtime files |

With Spring Boot, AOT processing is part of the native image build pipeline. You can use GraalVM Native Build Tools to produce an executable or Cloud Native Buildpacks to build a container image holding the native executable.

When verifying Swagger UI, test the exact artifact intended for release. If production runs a native container, running the binary on a developer machine cannot replace container image testing, because the image may differ in resources, user, port, environment, and filesystem.

## 3. Choosing the Right Spring Boot and Springdoc Generation

Native support must be evaluated by version combination:

- Springdoc notes native image support starting from the Spring Boot 3 generation.
- Spring Boot 3 typically pairs with springdoc 2.x.
- Spring Boot 4 pairs with springdoc 3.x.
- For older versions or special setups, consult the corresponding compatibility matrix and native guide.

Do not take a Spring Boot 3 native example and apply it verbatim to Spring Boot 4 or vice versa. The AOT engine, GraalVM, JDK, plugins, and reachability metadata can change across generations.

Before building, record:

1. Spring Boot version.
2. Springdoc starter and version.
3. Java/GraalVM distribution and version.
4. Maven or Gradle plugin version.
5. Web stack: MVC or WebFlux.
6. Whether the starter includes Swagger UI or API docs only.
7. OS and CPU architecture of the native target.

The version combination must fall within Spring Boot and Springdoc's support matrix. Native images also depend on OS/architecture; a binary built for Linux x64 cannot run directly on Windows or ARM64 by default.

## 4. OpenAPI Annotations Must Reside on a Retained Configuration Class

Springdoc highlights an important caveat during native compilation: if @OpenAPIDefinition or @SecurityScheme is placed on a class without an implementation and that class is not recognized by Spring as configuration, the class may be stripped from the native executable.

Place global metadata on a genuine configuration class:

~~~java
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.info.Info;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;

@Configuration
@OpenAPIDefinition(
    info = @Info(
        title = "Store API",
        version = "1.0.0",
        description = "Store management API"
    )
)
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiConfiguration {
}
~~~

This class must lie within the component scan scope or be explicitly imported. Adding @Configuration alone while placing the class outside scan scope can still prevent the configuration from loading.

After the native build, verify the document contains the expected info.title, info.version, and security schemes. Do not merely check that the class exists in source code.

## 5. Checking Custom Beans and Document Groups

If using an OpenAPI bean, OpenApiCustomizer, or GroupedOpenApi, confirm those beans are created inside the native ApplicationContext.

Group example:

~~~java
@Configuration
public class OpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }
}
~~~

If a group does not appear in the native document:

- Check whether the configuration's package is component-scanned.
- Check @Profile, @ConditionalOnProperty, and bean conditions.
- Check the group name and pathsToMatch.
- Call the group endpoint directly on the native binary.
- Compare ApplicationContext and profiles between JVM and native.

Do not assume a bean present in JVM tests is always registered in native if build-time profiles or configuration conditions differ.

## 6. Distinguishing OpenAPI Endpoints from Swagger UI

Both parts must be tested separately:

| Capability | Common Endpoint/Resource |
|---|---|
| OpenAPI JSON | /v3/api-docs |
| OpenAPI YAML | /v3/api-docs.yaml |
| Document group | /v3/api-docs/{group} |
| Swagger UI entry page | /swagger-ui.html |
| UI index and static assets | /swagger-ui/** |

JSON/YAML endpoints are generated by the springdoc runtime. Swagger UI is a web interface reading the specification and requires HTML, JavaScript, CSS, and image assets.

If using the API-only starter, OpenAPI endpoints can work without Swagger UI. To test the UI, the application must include the UI starter matching Spring MVC or WebFlux.

Do not conclude native integration is complete just because /v3/api-docs returns 200. The UI may still be missing JavaScript or CSS files.

## 7. Building Native with Maven

With Maven and the Spring Boot Maven Plugin, the native profile supplied by spring-boot-starter-parent can coordinate AOT processing and native build steps. If the project does not use this parent, configure AOT executions and Native Build Tools per Spring Boot documentation.

Create a native executable using GraalVM Native Build Tools:

~~~bash
./mvnw -Pnative native:compile
~~~

On Windows:

~~~powershell
.\mvnw.cmd -Pnative native:compile
~~~

Or build a native container image via Buildpacks:

~~~bash
./mvnw -Pnative spring-boot:build-image
~~~

Buildpacks require a Docker daemon and compatible builder configuration. JDK/GraalVM requirements vary by Spring Boot line and builder; follow the exact requirements in your project version's documentation.

Do not confuse the Maven profile named native with the application's Spring profile. -Pnative activates the Maven build profile; application profiles such as contract or prod are configured separately via Spring environment properties.

## 8. Building Native with Gradle

With Gradle, add the GraalVM Native Image plugin following Spring Boot and GraalVM Native Build Tools guidance. When the native plugin is applied, the Spring Boot Gradle Plugin can configure AOT tasks.

Example creating a container image:

~~~bash
./gradlew bootBuildImage
~~~

On Windows:

~~~powershell
.\gradlew.bat bootBuildImage
~~~

The bootBuildImage task builds a native image when the build is configured with the GraalVM Native Image plugin according to the corresponding guide. If the project uses the nativeCompile task to produce an executable directly, confirm the task and output path for the installed plugin version.

Do not assume a native build ran simply because a task name contains native. Inspect the build log to confirm AOT and native-image compilation actually executed.

## 9. Running the Exact Native Artifact Just Built

After building, launch the generated executable. Filename and path depend on artifactId, plugin configuration, and platform.

Example on Linux:

~~~bash
./target/store-service
~~~

Example on Windows if the output is an EXE file:

~~~powershell
.\target\store-service.exe
~~~

If building a container image:

~~~bash
docker run --rm -p 8080:8080 store-service:latest
~~~

Do not substitute java -jar for this step. Running java -jar executes the application on the JVM and does not test the native executable.

When running the container, use the same profiles and environment variables planned for deployment. If profiles or configurations alter controllers/groups, OpenAPI output may differ.

## 10. Waiting for the Native Application to Be Ready

A native executable can start quickly, yet fast startup does not mean the server is ready to accept requests. The application may still need to connect to a database, load secrets, run migrations, or initialize custom beans.

If Actuator readiness is enabled:

~~~bash
curl --fail --silent --show-error http://localhost:8080/actuator/health/readiness
~~~

If no readiness endpoint exists, poll the OpenAPI endpoint with a bounded timeout. When the timeout expires, print native process logs and container status.

Do not send an OpenAPI request immediately after spawning the process and treat connection refused as a Springdoc bug. First confirm the application has bound its port and finished startup.

## 11. Verifying OpenAPI JSON on the Native Binary

Call the endpoint against the running native process:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Verify:

- Status code is 2xx, usually 200.
- Content-Type is JSON.
- Response body parses cleanly.
- Fields openapi, info, and paths are present.
- Key operations are included.
- Schemas and component references are complete.
- Security schemes and security requirements are accurate.

You can use jq for a smoke check:

~~~bash
curl --fail --silent http://localhost:8080/v3/api-docs \
  | jq -e '.openapi and .info.title and .paths'
~~~

If the application enables authentication for documentation, test requests must supply credentials for a test identity. Do not disable security just to make curl return 200.

A 200 response is insufficient if the body is an HTML login page or a gateway error JSON. Inspect both Content-Type and document structure.

## 12. Verifying OpenAPI YAML

If the application supports the YAML endpoint:

~~~bash
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

Confirm the response is valid YAML and contains the same core information as JSON:

- OpenAPI version.
- Info title and version.
- Paths and HTTP methods.
- Request/response schemas.
- Security schemes.
- Document groups.

If JSON works but YAML does not, check endpoint configuration, runtime dependencies, and response serialization. Do not rename a JSON file extension to .yaml and treat YAML as verified.

## 13. Checking Every Document Group

For each GroupedOpenApi, call the corresponding URL:

~~~bash
curl --fail --silent http://localhost:8080/v3/api-docs/public
curl --fail --silent http://localhost:8080/v3/api-docs/partner
~~~

Create a verification table for published groups:

| Group | Endpoint | What to Verify |
|---|---|---|
| public | /v3/api-docs/public | Contains only public APIs |
| partner | /v3/api-docs/partner | Contains expected partner endpoints |
| internal | /v3/api-docs/internal | Contains expected schemas and access policy |

These are illustrative group names; use your application's real groups. If a group disappears in native, check bean registration, component scanning, profiles, and bean creation conditions.

A group missing from the Swagger UI dropdown could be a dropdown configuration issue. Call the group endpoint directly to separate document generation errors from UI errors.

## 14. Checking the Swagger UI Entry Page

Open the default path or the configured path:

~~~bash
curl -i -L http://localhost:8080/swagger-ui.html
~~~

The /swagger-ui.html path typically redirects to the UI index page. Inspect the redirect and final response rather than assuming every version returns 200 directly at the initial URL.

If using a custom path via springdoc.swagger-ui.path, call that exact path. If a context path is configured, include it in the URL.

Successfully fetching HTML is only the first step. The browser still must fetch CSS, JavaScript, favicon, and the OpenAPI document. A blank page or an error stating the definition failed to load can occur even when the initial HTML returns 200.

## 15. Checking JavaScript, CSS, and WebJar Assets

Swagger UI uses static assets packaged in a WebJar. Springdoc serves these classpath resources under META-INF/resources/webjars/swagger-ui/<version>/, for example:

- index.html
- swagger-ui-bundle.js
- swagger-ui-standalone-preset.js
- swagger-ui.css
- favicon-32x32.png

Exact filenames and HTTP URLs can vary with Swagger UI version and how Springdoc serves resources. Use the browser's Network panel to capture the exact URLs the UI page requests.

For every asset request, verify:

- Status 200 or valid cache status.
- Content-Type matches the file type.
- Response body is not an HTML error page.
- No unexpected redirect to a login page.
- URLs carry the correct context path or proxy prefix.

If the index HTML returns 200 while the JavaScript bundle returns 404, the UI will not initialize. If CSS returns 404, the page may render text with broken layout.

## 16. Checking with Browser Network and Console Tools

Open Swagger UI at the native instance's URL and open Developer Tools:

1. Select the Network tab and enable Preserve log.
2. Reload the UI page.
3. Filter requests for JS, CSS, images, and api-docs.
4. Check status, Content-Type, and response URLs.
5. Open the Console tab to look for JavaScript, CORS, or mixed-content errors.
6. Verify the exact OpenAPI URL the UI actually loads.
7. Test switching each document group if the UI has a dropdown.
8. Test Authorize and Try it out per the test environment's security policy.

Testing in a real browser is especially valuable because curl only checks raw HTTP responses. Browsers also enforce same-origin, CORS, mixed-content, CSP, and JavaScript execution.

If running behind a reverse proxy, access via the public domain and path just as production users do. Accessing localhost directly does not test the full path through ingress or gateway.

## 17. Checking Custom Static Assets and External OpenAPI Files

Applications may add:

- Custom logos or favicons.
- Custom CSS/JavaScript for Swagger UI.
- Static OpenAPI JSON/YAML files.
- Example or supplementary documentation files.
- Resource transformers modifying the index page or WebJar assets.

These files must be packaged in the native artifact and readable at runtime. If placing files in src/main/resources/static, verify the live URL after building rather than merely checking the file exists in the source tree.

If Swagger UI loads a static OpenAPI file via springdoc.swagger-ui.url, confirm that file is served by the native binary and the UI loads the right URL. If the URL resides on another host, check CORS, TLS, and browser network access.

For custom resource transformers, verify both original assets and transformed output. A transformer can work on the JVM yet fail when resources or classes are accessed in ways unrecognized by native metadata.

## 18. Adding Resource Hints Only When Assets Are Truly Missing

Spring AOT and dependency metadata already supply many resource hints. Do not register the entire classpath or every WebJar broadly just to avoid errors. First pinpoint the exact missing resource from native logs or HTTP responses.

For example, an application has a custom file at src/main/resources/static/openapi/examples.json and the native runtime cannot find it due to custom classpath access. Register the resource pattern:

~~~java
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;
import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.context.annotation.Configuration;

class OpenApiResourceHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(RuntimeHints hints, ClassLoader classLoader) {
        hints.resources().registerPattern("static/openapi/examples.json");
    }
}

@Configuration
@ImportRuntimeHints(OpenApiResourceHints.class)
class OpenApiNativeConfiguration {
}
~~~

The path in registerPattern is the classpath resource path matching how the application reads the file. Adjust it to the actual location and test on the binary after rebuilding.

If the file is served by Spring MVC's static resource handler, first check the URL and resource handler configuration. Runtime hints only solve resource reachability; they do not fix URL mappings, context paths, or security policies.

## 19. Reflection Hints for Custom Schemas and Models

Springdoc and underlying libraries use controller, DTO, Jackson, and annotation metadata to generate schemas. Spring Boot AOT along with dependency reachability metadata handles many standard cases.

If custom code uses dynamic reflection to inspect fields, constructors, or methods that AOT cannot infer, the native runtime may report errors such as missing reflective access or unreadable metadata. In that case:

1. Read the stack trace to identify the missing class/member.
2. Identify which code performs the reflection.
3. Check whether the library already provides reachability metadata or Spring RuntimeHints.
4. Register the exact type/member requiring access.
5. Rebuild the native image and re-run the failing flow.

Do not register reflection for an entire package when only one DTO is missing. Overly broad hints inflate the native image and obscure unclear dependencies.

For types requiring binding that Spring did not detect, consider mechanisms such as @RegisterReflectionForBinding or RuntimeHintsRegistrar per the Spring Boot version's API. Only add hints with evidence of the specific member or type needing access.

## 20. Using the GraalVM Tracing Agent When Missing Hints Are Elusive

The tracing agent can record certain reflection, resource, and proxy operations while running the application on the JVM. You can then use its output to investigate metadata needed for the native image.

General workflow:

1. Run the JVM application with the native image tracing agent.
2. Hit the OpenAPI and Swagger UI endpoints that need support.
3. Exercise flows involving custom resources, groups, and schemas.
4. Stop the application so the agent writes metadata.
5. Review generated files and remove unnecessary hints.
6. Place verified metadata in the appropriate native-image location.
7. Rebuild and test the native executable.

The tracing agent records only executed paths. If Swagger UI was never opened or a group endpoint was never called during the tracing session, the agent may omit resources or reflection needed for those flows.

Do not copy all metadata blindly from a large test suite without review. Test infrastructure can emit many hints unnecessary in production runtime.

## 21. Comparing OpenAPI Output on JVM and Native

To detect AOT differences, capture two documents from the same commit:

1. Run the application on the JVM with the contract profile.
2. Fetch JSON/YAML from the endpoint.
3. Run the native executable with the same profile and configuration.
4. Fetch JSON/YAML from the native endpoint.
5. Compare both documents after normalizing environment-dependent fields if any.

Sections to compare:

- Info title, version, and description.
- Paths, methods, and operationIds.
- Parameters and request bodies.
- Response statuses, media types, and schemas.
- Components.schemas and references.
- Security schemes and requirements.
- Tags and document groups.
- Server URLs.

Server URLs may differ if host, port, proxy, or forwarded headers differ. Normalize this field if the comparison targets schemas/operations; do not strip differences if server URLs themselves are under test.

Do not compare path counts alone. Two documents with identical path counts can still differ in required request fields, response schemas, or security requirements.

## 22. Checking Caching and the First Request

Springdoc computes and caches the OpenAPI description by default. The first request may trigger schema construction work; subsequent requests typically reuse the cached result.

In the native image, test all of these:

- The first request after startup.
- Repeated requests once the cache is populated.
- Requests to each group.
- Requests with Accept-Language if the application localizes documentation.

If only the first request fails, inspect document generation and customizer logs. If every request is slow, measure timing and inspect oversized schemas, custom converters, or custom logic.

Do not disable caching merely to make a native test pass. Only adjust cache settings for concrete operational requirements, then re-measure on both JVM and native.

## 23. Checking Security on Native

The native binary must enforce the same security policy as the JVM application. Check separately:

- /v3/api-docs
- /v3/api-docs.yaml
- /v3/api-docs/{group}
- /swagger-ui.html
- /swagger-ui/**

If endpoints require authentication, use a test identity with appropriate permissions. A 401/403 response may reflect the intended policy rather than a native failure.

If the UI loads HTML while the OpenAPI request returns 401, verify whether Swagger UI sends credentials or cookies as configured. If only the internal group returns 403, check group endpoint authorities and matchers.

Do not make all documentation public just for smoke testing. Run tests in an isolated network with least-privilege CI credentials.

## 24. Checking Context Path and Reverse Proxy

An application may run under a context path or be exposed through an ingress. In that setup, UI and API docs URLs must reflect the public paths.

Example external URL:

~~~text
https://api.example.com/store
~~~

URLs that may need to work:

~~~text
https://api.example.com/store/swagger-ui.html
https://api.example.com/store/v3/api-docs
~~~

Verify:

- Server context path.
- Forwarded headers from trusted proxies.
- springdoc.swagger-ui.path and springdoc.api-docs.path if customized.
- Spec URL fetched by Swagger UI.
- CORS and CSP.
- Routes for /swagger-ui/** and /v3/api-docs/**.

If direct access to the native container succeeds while access through the public domain fails, focus on ingress, proxy, and security headers. Do not rush to add reflection hints when the issue lies outside the native executable.

## 25. Automated Smoke Tests on the Native Executable

A minimal smoke test should verify HTTP responses from the native binary:

~~~bash
curl --fail --silent --show-error http://localhost:8080/v3/api-docs \
  -o target/native-openapi.json

jq -e '.openapi and .info and .paths' target/native-openapi.json

curl --fail --silent --show-error http://localhost:8080/v3/api-docs.yaml \
  -o target/native-openapi.yaml

curl --fail --silent --show-error -L http://localhost:8080/swagger-ui.html \
  -o target/native-swagger-ui.html
~~~

The commands above assume endpoints require no authentication and the YAML endpoint is enabled. If security is enabled, supply credentials via CI secret environment variables; never hardcode tokens in committed scripts.

HTML output does not prove JavaScript/CSS works. Supplement with browser tests or HTTP checks for actual asset URLs observed in Network logs. If not running a browser in CI, at least include an HTTP check for critical static assets.

After the smoke test, run an OpenAPI validator and contract diff on the JSON/YAML. The goal is to verify both serving behavior and contract content.

## 26. Testing the Native Container in CI

The pipeline should start the exact native image just built:

~~~text
Build AOT and native image
          |
          v
Start native container
          |
          v
Wait for readiness
          |
          v
Fetch JSON and YAML
          |
          v
Check Swagger UI HTML and static assets
          |
          v
Validate OpenAPI document
          |
          v
Compare with JVM/baseline contract
          |
          v
Stop container and publish test artifacts
~~~

Execution steps:

1. Build the native image on a runner with the appropriate toolchain.
2. Start the container with the contract profile.
3. Wait for readiness with a finite timeout.
4. Fetch JSON, YAML, and each group.
5. Check Swagger UI HTML and JavaScript/CSS assets.
6. Run browser tests if the pipeline supports browser automation.
7. Validate OpenAPI and compare against baseline.
8. Collect logs whenever any step fails.
9. Stop the container in an always-executed cleanup step.
10. Release the image only when mandatory checks pass.

Native builds take more time and resources than JVM builds. You can cache dependency/build layers per CI policy, but never use a stale binary in place of native testing for the current commit.

## 27. Diagnosing Common Failures

| Symptom on Native | Cause to Investigate | Resolution |
|---|---|---|
| /v3/api-docs returns 404 | API docs disabled, wrong path, or wrong starter | Check runtime dependencies and springdoc.api-docs.path |
| JSON missing title or security scheme | Annotation-only class stripped from native image | Place annotations on a scanned @Configuration class |
| Group does not appear | Group bean not created or different profile | Check component scan, conditions, and profiles |
| JSON has paths but missing schemas | Reflection/binding metadata or custom converter | Inspect stack trace and add exact hints |
| /v3/api-docs returns 500 | Schema generation, customizer, or reflection error | Read native process logs and identify failing class/member |
| YAML returns 404 while JSON works | YAML endpoint disabled or configuration differs | Check runtime configuration and URL |
| Swagger UI HTML returns 200 but page is blank | JavaScript bundle or CSS failed to load | Use Network/Console to locate failing asset |
| JS/CSS returns 404 | Wrong URL, resource missing from image, or wrong proxy path | Check WebJar/resource mapping and native image |
| Custom logo or static spec missing | Custom asset not packaged/registered | Check classpath and resource hints |
| UI loads yet definition fails | Wrong OpenAPI URL, security, or CORS | Inspect api-docs request in Network tab |
| Works on JVM, fails on native | AOT/reachability differences | Check hints and run the real native binary |
| Only the first request fails | Error in document generation or caching | Collect logs and inspect customizers/model converters |
| Works locally, fails in container | Wrong port, user, filesystem, env, or architecture | Inspect container config and logs |
| Native build succeeds yet endpoints incomplete | Build success does not guarantee all runtime flows | Add native smoke tests for every endpoint and asset |

## 28. Pre-Release Checklist

Before accepting a native artifact, verify:

- [ ] Spring Boot, Springdoc, JDK/GraalVM, and native plugin form a compatible combination.
- [ ] AOT processing and native compilation actually ran during the build.
- [ ] The native binary/container was launched, not merely the JVM jar.
- [ ] Profiles and environment variables match the planned release configuration.
- [ ] OpenAPI annotation classes reside in Spring-scanned configuration.
- [ ] OpenAPI JSON returns a valid document.
- [ ] OpenAPI YAML returns valid content if enabled.
- [ ] Every key document group is accessible.
- [ ] Paths, schemas, responses, and security schemes match the expected contract.
- [ ] Swagger UI HTML loads.
- [ ] JavaScript, CSS, favicon, and custom assets are present.
- [ ] The UI fetches the right OpenAPI URL.
- [ ] Context path, proxy, and security behave properly.
- [ ] JVM/native documents were compared or checked against baseline.
- [ ] Native smoke tests and validators run in CI.
- [ ] Containers/processes are cleaned up even when tests fail.

## 29. Key Takeaways

- JVM tests do not replace running and testing the native executable.
- Native builds rely on AOT and reachability analysis; custom reflection, proxies, and resources must be recognized.
- Springdoc notes native support starting from Spring Boot 3; choose the matching major version for Spring Boot.
- Place @OpenAPIDefinition and @SecurityScheme on a component-scanned @Configuration class.
- Verify OpenAPI JSON/YAML, document groups, and Swagger UI separately.
- Swagger UI also depends on HTML, JavaScript, CSS, favicons, and WebJar assets.
- Add resource/reflection hints only when logs or tests pinpoint what is missing.
- The tracing agent helps discover metadata but records only executed flows.
- Compare JVM and native documents to catch AOT or profile discrepancies.
- Verify the first request, caching, security, context path, and reverse proxy behavior.
- CI must smoke-test the exact native image/container built from the current commit.

To verify that specifications and UI assets work on the real native build, launch the exact executable or container to be released. Fetch JSON, YAML, and each document group directly; open Swagger UI and check every JavaScript/CSS request in the browser. If discrepancies from the JVM appear, use native logs and reachability metadata to locate the exact missing class or resource, then rebuild and repeat smoke tests on the new artifact.

## References

- Springdoc FAQ – Is GraalVM supported?: https://springdoc.org/faq.html
- Springdoc OpenAPI v2 documentation: https://springdoc.org/v2/
- Spring Boot – Developing Your First GraalVM Native Application: https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html
- Spring Boot – Advanced Native Images Topics: https://docs.spring.io/spring-boot/reference/packaging/native-image/advanced-topics.html
- Spring Boot Maven Plugin – Ahead-of-Time Processing: https://docs.spring.io/spring-boot/maven-plugin/aot.html
