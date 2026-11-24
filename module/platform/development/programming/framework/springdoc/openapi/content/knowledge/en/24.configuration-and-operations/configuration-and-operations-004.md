# Property to Enable or Disable Swagger UI

springdoc-openapi can publish an OpenAPI specification and provide Swagger UI so developers can read, search, and try out API operations. In many environments, these two capabilities need independent control: development teams may need the Swagger UI interface in local or development, while production only exposes documentation to a controlled pipeline or disables publication completely.

The primary property controlling the UI is **springdoc.swagger-ui.enabled**. This property enables or disables Swagger UI when the application includes the UI starter. OpenAPI JSON/YAML specification endpoints are controlled separately by **springdoc.api-docs.enabled**. Understanding the difference between these two properties prevents situations where the UI is disabled while the JSON specification remains public, or where Swagger UI cannot load the specification because the OpenAPI endpoint is disabled.

## 1. Role of Swagger UI in a Spring Boot Application

Swagger UI is a web interface that reads an OpenAPI specification. When integrated via springdoc-openapi, the application typically provides:

- An entry page for Swagger UI, by default usually /swagger-ui.html.
- Static assets such as JavaScript, CSS, and images under /swagger-ui/**.
- The OpenAPI JSON specification at /v3/api-docs.
- The OpenAPI YAML specification at /v3/api-docs.yaml.
- Separate specifications for document groups at /v3/api-docs/{group}.

Swagger UI reads the OpenAPI specification and builds an interface organized by path, method, parameter, request body, response, and security scheme. Users can inspect schemas, try requests, and observe responses if permitted by the API and security policies.

Swagger UI is the frontend UI component. OpenAPI JSON/YAML is the contract document that Swagger UI renders. The two components are related, yet they are neither the same endpoint nor the same configuration property.

## 2. The springdoc.swagger-ui.enabled Property

To enable Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
~~~

To disable Swagger UI:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

The springdoc.swagger-ui.enabled property is a Boolean flag in Spring Boot configuration. When using a starter that includes the Swagger UI interface, the default value is typically enabled. Explicitly declaring true or false makes per-environment configuration easier to read and audit.

This property controls the Swagger UI integration. It does not replace springdoc.api-docs.enabled, does not modify business endpoints, and does not automatically apply authentication or authorization to documentation endpoints that remain active.

If the application uses only an API-only starter, there is no Swagger UI component to enable. In that case, setting springdoc.swagger-ui.enabled: true will not automatically add the missing UI library.

## 3. Distinguishing Swagger UI from OpenAPI JSON/YAML

To control documentation completely, you must understand both properties:

| Property | Purpose |
|---|---|
| springdoc.swagger-ui.enabled | Enables or disables the Swagger UI interface |
| springdoc.api-docs.enabled | Enables or disables the endpoint generating OpenAPI JSON/YAML |

Default OpenAPI endpoints typically include /v3/api-docs and /v3/api-docs.yaml. Swagger UI usually loads JSON from this OpenAPI endpoint to render the interface.

Example disabling Swagger UI while keeping the specification:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

In this configuration, users do not get the Swagger UI hosted by the application, while the OpenAPI endpoint remains accessible according to the application's security policy.

Example disabling both:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
~~~

This is typically the right configuration when an environment should not publish either the UI or the specification through the running application.

## 4. Four Common Combined States

Swagger UI and the OpenAPI document can be enabled or disabled independently:

| Swagger UI | OpenAPI docs | Result |
|---|---|---|
| Enabled | Enabled | Swagger UI can load the internal OpenAPI specification and display APIs |
| Disabled | Enabled | No UI interface; JSON/YAML continues to be served |
| Enabled | Disabled | UI cannot load the default internal OpenAPI endpoint; only useful if configured to use an external specification or another source |
| Disabled | Disabled | Both UI and internal OpenAPI endpoints are disabled |

Enabling the UI while disabling internal OpenAPI requires intentional configuration. For instance, Swagger UI can act as a viewer for a specification file published on another server. In that case, you must declare the external specification URL and ensure the browser can reach it.

Do not enable Swagger UI with OpenAPI disabled and expect the UI to discover the application's APIs on its own. Without an alternative specification source, the UI has no document to display.

## 5. Enabling Swagger UI in Development Environments

You can enable Swagger UI in application-dev.yml:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /docs
  api-docs:
    enabled: true
~~~

When the dev profile is active, access the configured UI path:

~~~text
http://localhost:8080/docs
~~~

The /docs path is a customization example. If springdoc.swagger-ui.path is not specified, use the default path of your installed version, typically /swagger-ui.html.

In development environments, the UI helps teams inspect request/response payloads, view schemas, and test APIs quickly. However, if the application uses real data or connects to sensitive services, appropriate Spring Security rules are still needed even in development.

## 6. Disabling Swagger UI in Production Using Profiles

A common pattern is enabling the UI in local/dev and disabling it in production:

application.yml:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
  api-docs:
    enabled: true
~~~

application-prod.yml:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
~~~

When the prod profile is activated, values in application-prod.yml override corresponding settings from the default file. Confirm that the profile is actually active in the deployed environment.

If production still needs OpenAPI JSON for an API gateway, test pipeline, or separate documentation portal, you can keep api-docs.enabled: true while disabling swagger-ui.enabled.

Do not assume production automatically uses the prod profile. Spring Boot loads a profile file only when that profile is activated via deployment configuration, environment variables, or command-line arguments.

## 7. Activating Profiles via Environment Variables or Command Line

You can activate the production profile via an environment variable:

~~~bash
export SPRING_PROFILES_ACTIVE=prod
~~~

Or pass an argument when starting the application:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

You can override the property directly:

~~~bash
java -jar app.jar --springdoc.swagger-ui.enabled=false
~~~

In container environments, environment variables are typically set in deployment configs or platform manifests. There is no need to rebuild the JAR file just to toggle Swagger UI across environments.

After startup, inspect logs or Actuator environment/configuration diagnostics in accordance with operational policy to verify the active profile and actual property values. Do not expose sensitive Actuator endpoints publicly merely to inspect configuration.

## 8. Using Environment Variables for Swagger UI Properties

Spring Boot supports relaxed binding from property names to environment variables. The property:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

can be overridden by the variable:

~~~bash
SPRINGDOC_SWAGGER_UI_ENABLED=false
~~~

Similarly, to control the OpenAPI document:

~~~bash
SPRINGDOC_API_DOCS_ENABLED=false
~~~

Environment variables are useful when deploying the same artifact across multiple environments. Check spelling, underscores, and Boolean values. True and false are clearer than arbitrary strings.

In Kubernetes, Docker Compose, or cloud platforms, the variable must be declared on the exact container/process running Spring Boot. Setting the variable on a build machine without passing it to the runtime container will not change the running application's configuration.

## 9. Configuration Precedence Order

A property can be declared in multiple sources. Spring Boot applies externalized configuration precedence rules; a higher-priority source overrides a lower-priority one.

In common scenarios, the order from lowest to highest is typically:

1. Default values inside the application.
2. Packaged configuration files such as application.yml.
3. Profile-specific configuration files such as application-prod.yml.
4. Process environment variables.
5. Java system properties.
6. Application command-line arguments.

The complete order also includes other configuration sources such as imported config data, test properties, and DevTools. When conflicts occur, consult the externalized configuration documentation for your exact Spring Boot version.

For example, if the production file sets:

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
~~~

yet the launch command passes:

~~~bash
java -jar app.jar --springdoc.swagger-ui.enabled=true
~~~

the command-line argument can override the file value. Therefore, if the UI still appears despite editing YAML, check higher-priority configuration sources and the process's actual runtime values.

## 10. Customizing the Swagger UI URL

The springdoc.swagger-ui.path property changes the entry path to the interface:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    path: /api-docs-ui
~~~

Users visit:

~~~text
http://localhost:8080/api-docs-ui
~~~

A custom path is not a security measure. Changing /swagger-ui.html to /api-docs-ui only changes the access URL, not who is allowed to view it. Use Spring Security or gateway protection if the documentation requires authentication.

When changing the path, update Spring Security rules, reverse proxies, ingress, smoke tests, and operational guides. Also verify the static asset paths the UI loads after redirecting.

## 11. Customizing the OpenAPI URL Used by Swagger UI

Swagger UI needs to know the specification URL. By default, springdoc points to the document generated by the application. You can configure a specific URL:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    url: /v3/api-docs
~~~

If using a specification published on another server:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    url: https://docs.example.com/contracts/store-api.json
~~~

When using an external URL, the browser must be able to reach that address. If it is on a different origin, the server hosting the specification must configure appropriate CORS headers. An HTTPS page should not load a spec over HTTP because browsers may block mixed content.

The url property selects a single specification source. For multiple document groups or multiple APIs, you can configure a springdoc.swagger-ui.urls list using the syntax supported by your version.

## 12. Using Multiple Specifications in Swagger UI

Example configuration for a list of documents:

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    urls:
      - name: Public API
        url: /v3/api-docs/public
      - name: Partner API
        url: /v3/api-docs/partner
      - name: Internal API
        url: /v3/api-docs/internal
~~~

Swagger UI can render a selector dropdown allowing users to choose a document. Each URL must return a valid OpenAPI document and must be accessible under its corresponding security policy.

If the internal group requires higher privileges than public, merely hiding the group from the dropdown is not enough to protect it. You must enforce authorization on the /v3/api-docs/internal endpoint at the server or gateway. Users can call the URL directly without using the UI.

The urls property name and structure must match the binding model of the springdoc version in use. With complex YAML configurations, verify the bound values and actual request URLs in Developer Tools.

## 13. Combining UI and API Docs Toggles by Need

Sample configurations:

**Development:**

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
  api-docs:
    enabled: true
~~~

**Production, JSON only for pipelines:**

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: true
~~~

**Production, no documentation published:**

~~~yaml
springdoc:
  swagger-ui:
    enabled: false
  api-docs:
    enabled: false
~~~

**Swagger UI reading an external specification:**

~~~yaml
springdoc:
  swagger-ui:
    enabled: true
    url: https://docs.example.com/contracts/store-api.json
  api-docs:
    enabled: false
~~~

The last example is appropriate only when Swagger UI does not need an internal application-generated document and the external URL is safely reachable. When configuring groups or external URLs, check whether they are overridden by other url/urls properties.

## 14. Disabling UI by Property or Removing the UI Starter?

There are two distinct approaches:

| Approach | When Appropriate | Consequence |
|---|---|---|
| springdoc.swagger-ui.enabled=false | The same artifact needs UI enabled in dev and disabled in production | Retains the UI dependency in the artifact while disabling integration via configuration |
| Using the API-only starter or removing the UI starter | The project does not need Swagger UI in any environment | Does not package Swagger UI components; retains only OpenAPI generation if using the API starter |

If no environment needs the UI, using the API-only starter reduces unnecessary dependencies and static assets. If developers need the UI locally while production must disable it, profile-based properties are usually more convenient.

Changing dependencies requires updating the build file and checking the dependency tree. Changing a property requires redeploying the application so the new configuration is loaded.

## 15. The Enable/Disable Property Is Not a Runtime Switch

springdoc.swagger-ui.enabled is read during Spring Application Context initialization. Changing an environment variable or YAML file after the application is already running typically does not cause beans and endpoints to toggle state immediately.

To apply a new value, you typically need to:

1. Update the environment configuration.
2. Restart or roll out the application.
3. Verify the new instance loaded the configuration.
4. Check the UI URL and OpenAPI document after rollout.

Do not treat this as a feature flag that can be toggled instantly via an HTTP request. If dynamic access control is needed, use an appropriate authorization mechanism; do not build an endpoint that lets users arbitrarily turn on Swagger UI in production.

## 16. Combining with Spring Security

Disabling Swagger UI does not mean the OpenAPI endpoint is secured. If springdoc.api-docs.enabled remains true, users can still download JSON/YAML from the documentation path if the security policy permits it.

Example allowing only the DOCS_READ authority to access the UI and OpenAPI:

~~~java
http.authorizeHttpRequests(authorize -> authorize
    .requestMatchers(
        "/swagger-ui.html",
        "/swagger-ui/**",
        "/v3/api-docs",
        "/v3/api-docs/**",
        "/v3/api-docs.yaml"
    ).hasAuthority("DOCS_READ")
    .anyRequest().authenticated()
);
~~~

If using custom paths, update the matchers accordingly. With multiple SecurityFilterChains, check their order and securityMatcher so documentation requests are not handled first by a less restrictive chain.

If the goal is to publish no documentation in production, disable both UI and OpenAPI via properties and verify the live endpoints. If the goal is to restrict access to a specific audience, keep the necessary endpoints enabled and protect them with authentication/authorization rather than merely hiding the UI.

## 17. Impact on Reverse Proxies, Gateways, and Caching

In production environments, public paths may differ from backend paths. When changing springdoc.swagger-ui.path, update:

- Ingress or reverse proxy routes.
- API gateway routes and policies.
- Spring Security matchers.
- Health/smoke tests and monitoring.
- Documentation links in portals or internal guides.

If the UI is disabled while a CDN still caches old HTML or JavaScript, users may continue seeing the interface for some time. If OpenAPI JSON is cached, stale documentation content may also continue to be served.

After changing the state:

1. Roll out the application.
2. Verify the endpoints at the origin.
3. Verify the endpoints through the public domain/gateway.
4. Purge caches if stale UI/spec content must be cleared.
5. Check using an incognito window or a non-caching client.

Do not rely on localhost results to conclude that production configuration has taken effect.

## 18. Verifying Swagger UI Status After Enabling

When enabling the UI, check the URLs:

~~~bash
curl -i http://localhost:8080/swagger-ui.html
curl -i http://localhost:8080/v3/api-docs
~~~

The Swagger UI entry page may return a redirect to the UI HTML asset. Therefore, inspect both Location and the target URL instead of expecting /swagger-ui.html to always return 200.

In the browser:

- Does the Swagger UI page load HTML, CSS, and JavaScript?
- Does the UI load the correct OpenAPI document URL?
- Does the document return 200 and parse as valid JSON?
- Is the group list accurate?
- Do the Authorize and Try it out buttons work according to security policy?
- Are there any CORS, mixed content, or 401/403 errors?

If the UI page opens but shows Failed to load API definition, inspect the OpenAPI request in the Network panel. The cause may lie in api-docs.enabled, the specification URL, security, proxy, or CORS.

## 19. Verifying Status After Disabling

When springdoc.swagger-ui.enabled=false, check both the UI entry point and static assets. Depending on the version, path configuration, and security filters, the response may be 404 or a security-layer response such as 401/403. What matters is that the Swagger UI interface is no longer served, in accordance with the desired policy.

~~~bash
curl -i http://localhost:8080/swagger-ui.html
curl -i http://localhost:8080/swagger-ui/index.html
~~~

If only the UI is disabled while OpenAPI remains enabled:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

The JSON/YAML endpoints may still return 200. This is expected behavior if springdoc.api-docs.enabled=true and policy permits access.

If both are disabled, verify the JSON, YAML, UI, and each group endpoint. Do not declare success just because /swagger-ui.html fails to open; the document endpoint may still be active.

## 20. Testing Configuration with Spring Boot

You can write integration tests for different profiles or configurations. Example test when the UI is disabled while OpenAPI remains enabled:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "springdoc.swagger-ui.enabled=false",
    "springdoc.api-docs.enabled=true"
})
@AutoConfigureMockMvc
class SwaggerUiDisabledTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void openApiDocumentRemainsAvailable() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON
            ));
    }
}
~~~

This test verifies that OpenAPI JSON remains available. Verifying that the UI is disabled requires adding a request to the UI path and an assertion matching how your application/security filters respond in your version.

When testing profiles, use @ActiveProfiles("prod") in a dedicated test or run the application with the production profile in a test environment. Avoid checking only the property in a file; verify the actual endpoints.

With WebFlux, use WebTestClient instead of MockMvc if the application runs on the reactive stack. Do not add both test clients just because the example above uses MVC.

## 21. Common Mistakes

| Mistake | Cause | Fix |
|---|---|---|
| Disabled Swagger UI yet /v3/api-docs still returns 200 | Only swagger-ui.enabled=false was set | Also disable api-docs.enabled if you do not want to publish the spec |
| Swagger UI does not appear in dev | Active profile sets enabled=false or UI starter is missing | Check active profiles, dependencies, and property values |
| UI still appears in production | prod profile is inactive or property is overridden by higher-priority source | Check active profiles, environment, and command line |
| Set enabled: false at wrong YAML level | Property does not bind to springdoc.swagger-ui.enabled | Check indentation and property name |
| UI opens but fails to load spec | OpenAPI is disabled, URL is wrong, or blocked by security | Check api-docs.enabled, url, and Network tab |
| UI enabled yet no interface appears | Only API-only starter is used | Add the UI starter matching MVC/WebFlux |
| Changed swagger-ui.path yet still using old URL | Links, security matchers, or proxies not updated | Synchronize all paths |
| Disabled UI yet browser still sees old page | Browser/CDN cached stale assets | Check origin and purge caches appropriately |
| UI group fails to load | Group URL is wrong or group endpoint is blocked | Check urls, group paths, and authorization |
| Disabled both yet JSON still available | Stale instance, wrong profile, overridden property, or gateway cache | Check runtime config and call origin directly |
| Assuming property changes take effect immediately | Property is read at context initialization | Restart or roll out the application |

## 22. Configuration and Verification Workflow

Follow these steps in order:

1. Identify which environments need Swagger UI: local, dev, test, staging, or production.
2. Determine whether OpenAPI JSON/YAML should be published in each environment.
3. Choose the UI or API-only starter appropriate for MVC/WebFlux.
4. Set springdoc.swagger-ui.enabled and springdoc.api-docs.enabled explicitly.
5. Configure via profiles or environment variables if environments have different policies.
6. Check whether higher-priority configuration sources override the properties.
7. Align swagger-ui.path, OpenAPI path, security matchers, and gateway routes.
8. Start or roll out the application to load the new configuration.
9. Verify the UI, JSON, YAML, and each document group directly.
10. Re-verify through the production domain and behind caches/proxies.
11. Automate integration tests for the supported UI/docs combinations.
12. Document the chosen policy and verification results for each environment.

## 23. Key Takeaways

- springdoc.swagger-ui.enabled enables or disables the Swagger UI interface.
- springdoc.api-docs.enabled controls the OpenAPI JSON/YAML endpoints.
- Disabling the UI does not mean disabling the OpenAPI document.
- Enabling the UI while disabling internal docs requires an external specification URL or another source.
- Use profiles, environment variables, or command-line arguments to control settings per environment.
- Check precedence because command-line arguments and environment variables can override YAML.
- springdoc.swagger-ui.path changes the UI URL; it is not a security measure.
- Use the API-only starter if the UI is not needed in any environment.
- Properties are loaded at application startup; applying changes usually requires a restart or rollout.
- If you need to restrict readers, use Spring Security or a gateway; hiding the UI does not protect document endpoints.
- Verify status with live requests to the UI, JSON, YAML, and group endpoints, both at the origin and on the public domain.

To manage Swagger UI by environment, configure springdoc.swagger-ui.enabled separately from springdoc.api-docs.enabled. Enable the UI in development environments, disable it in production when no UI is needed, and decide explicitly whether to continue serving OpenAPI JSON/YAML. After every change, test the live endpoints along the actual deployment path to confirm the configuration is in effect.
