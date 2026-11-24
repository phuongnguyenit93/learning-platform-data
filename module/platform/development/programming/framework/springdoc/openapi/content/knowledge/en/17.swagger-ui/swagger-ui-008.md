# supportedSubmitMethods and Restricting Try-It-Out from the UI

Swagger UI does more than display OpenAPI documentation; it also provides the **Try it out** button so users can enter parameters, send requests, and inspect responses directly in the browser. In development environments, this feature speeds up API testing. In shared or production environments, allowing users to test every HTTP method can introduce risks if users accidentally perform write, update, or delete actions.

springdoc-openapi provides the **supportedSubmitMethods** setting to control which HTTP methods Swagger UI is allowed to submit via Try it out. You can enable only read methods, or disable try-it-out actions entirely. This configuration limits the UI's interactive capabilities; API access permissions and safety must still be enforced on the backend.

## 1. How does Try it out work?

In Swagger UI, each operation is displayed with its HTTP method, path, description, parameters, request body, and responses. When a user selects **Try it out**, the interface opens input fields and allows sending the request.

A typical try-it-out flow:

1. The user opens Swagger UI and chooses an operation.
2. Swagger UI reads the operation description from the OpenAPI document.
3. The user enters path/query parameters, headers, or a request body.
4. The user clicks Execute.
5. The browser sends an HTTP request to the server specified by OpenAPI servers or Swagger UI configuration.
6. Swagger UI displays the received status, headers, and response body.

For example, a document might contain:

~~~yaml
paths:
  /api/products:
    get:
      summary: List products
      responses:
        '200':
          description: Product list
    post:
      summary: Create product
      responses:
        '201':
          description: Product created
  /api/products/{id}:
    delete:
      summary: Delete product
      responses:
        '204':
          description: Product deleted
~~~

Swagger UI can display GET, POST, and DELETE. If the user has permissions and the server allows it, Try it out can send the corresponding requests. Having an operation appear in documentation does not mean the user is authorized to execute it; authorization is decided on the backend.

## 2. What is supportedSubmitMethods?

supportedSubmitMethods is a Swagger UI configuration option exposed by springdoc-openapi in the UI config. Its value is the list of HTTP methods permitted for use via the Try it out button.

Common methods:

- get
- post
- put
- delete
- patch
- options
- head
- trace

When configuring, method names should be lowercase and match OpenAPI methods. If the list contains only get and head, Swagger UI allows testing GET and HEAD operations; other methods will not have the corresponding submit button.

By Swagger UI's default, standard methods are supported. If you want to alter this policy, declare the list explicitly rather than relying on defaults that may differ across versions or setups.

This setting affects the Swagger UI interface. It does not change the HTTP methods declared in OpenAPI, does not remove operations from the document, and does not stop another client from calling endpoints directly.

## 3. Allowing only read HTTP methods

A common choice for demo environments or production documentation is enabling only read methods. For example, allowing only GET:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
~~~

If the API has HEAD endpoints to check metadata or resource existence, you can enable both:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - head
~~~

Equivalent configuration in application.properties:

~~~properties
springdoc.swagger-ui.supportedSubmitMethods=get,head
~~~

After this configuration, Swagger UI still displays POST, PUT, PATCH, and DELETE operations in the documentation. However, those operations no longer offer Execute via Try it out.

This is useful when you want users to read the API contract, inspect schemas and sample responses, while reducing the risk of triggering write operations directly from the documentation UI.

Enabling only GET/HEAD does not guarantee read requests are completely harmless. A poorly designed GET endpoint can still cause side effects. The backend must follow HTTP semantics and avoid mutating data merely upon receiving GET.

## 4. Disabling Try it out for all HTTP methods

To completely disable sending requests from Swagger UI, configure an empty list:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods: []
~~~

An empty list means no method is enabled for Try it out. Users can still view:

- Endpoint list.
- HTTP methods and paths.
- Summary, description, and tags.
- Query/path/header parameters.
- Request body schemas.
- Response schemas and status codes.
- Security schemes and authentication descriptions.

The documentation UI remains useful for looking up contracts, while no longer providing an Execute button to send requests.

YAML syntax with an empty list is the clearest representation. If the project only uses application.properties, verify how your Spring Boot/springdoc version's binder represents an empty list; do not assume a blank string value will always convert into an empty list. If other config files, environment variables, or a config server override the value, runtime behavior can differ from application.yml.

## 5. Enabling a specific subset of methods

You can allow a subset of methods according to environment policy. For instance, a test environment allowing GET, POST, and PATCH:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - patch
~~~

A staging environment might additionally allow PUT while keeping DELETE disabled:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - put
      - patch
~~~

In application.properties:

~~~properties
springdoc.swagger-ui.supportedSubmitMethods=get,post,put,patch
~~~

This policy operates at the HTTP method level, applying to every operation of that method shown in the UI. The setting does not distinguish which endpoints are safe or dangerous within the same method.

For example, if POST is enabled, every POST operation in the document can show Try it out, including endpoints that create orders, submit payments, or trigger jobs. Review the actual operation list before enabling a method capable of mutating data.

## 6. Per-environment configuration

Try-it-out policies typically differ across local, development, staging, and production. Spring profiles can be used for separate configurations.

application.yml:

~~~yaml
spring:
  profiles:
    active: dev

springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - put
      - patch
      - delete
~~~

application-dev.yml:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
      - put
      - patch
      - delete
~~~

application-prod.yml:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - head
~~~

When running with the production profile:

~~~bash
java -jar app.jar --spring.profiles.active=prod
~~~

Swagger UI in production allows testing only GET and HEAD. The OpenAPI document can still include write/delete operations for client reference.

The sample configuration above illustrates per-profile policies. In real projects, avoid hardcoding a default active profile in application.yml if deployments already manage profiles via environment variables or launch arguments. What matters is identifying the final configuration source loaded by Spring Boot.

## 7. Property names in YAML and properties

Spring Boot supports relaxed binding, so YAML configuration can be written in kebab-case:

~~~yaml
springdoc:
  swagger-ui:
    supported-submit-methods:
      - get
      - post
~~~

In application.properties, use the springdoc property name:

~~~properties
springdoc.swagger-ui.supportedSubmitMethods=get,post
~~~

Key points to keep in mind:

- YAML uses a list to clearly express each method.
- Properties files can use a comma-separated string.
- Write method names in lowercase to match Swagger UI configuration.
- Do not include spaces or invalid delimiters in method names.
- Avoid defining the same property in multiple config sources with hard-to-track values.
- Check profiles, environment variables, command-line arguments, and config servers if values do not behave as expected.

Property names and binding syntax should be verified against your project's springdoc version. If the application uses an older major version, consult the corresponding reference documentation instead of inferring solely from newer examples.

## 8. supportedSubmitMethods differs from tryItOutEnabled

These two settings have similar names but different purposes:

| Setting | Role |
|---|---|
| supportedSubmitMethods | List of HTTP methods permitted for submission via Try it out |
| tryItOutEnabled | Enables Try it out by default for operations, depending on Swagger UI version |

supportedSubmitMethods determines which methods are allowed to be tested. tryItOutEnabled activates Try it out by default for operations; it does not create a method allowlist and does not replace supportedSubmitMethods.

Example:

~~~yaml
springdoc:
  swagger-ui:
    try-it-out-enabled: true
    supported-submit-methods:
      - get
~~~

This configuration enables Try it out by default for operations supported by Swagger UI, while the method list still allows submitting only GET.

If the supportedSubmitMethods list is empty, enabling tryItOutEnabled will not bring back submission for methods. Consider both properties together when designing the user experience.

Behavior and configuration names may vary by the Swagger UI version packaged by springdoc. Verify against the UI and actual runtime configuration.

## 9. supportedSubmitMethods is not a backend security mechanism

This is the most important limitation of this setting.

If production enables only GET in Swagger UI, clients can still send POST, PUT, or DELETE using:

- curl.
- Postman.
- HTTP clients in applications.
- JavaScript running outside Swagger UI.
- Another tool or script.

supportedSubmitMethods only hides or disables try-it-out capability from the Swagger UI interface. It is not a firewall, authorization rule, CSRF protection, or server-side allowlist.

If a DELETE endpoint must be forbidden to regular users, it must be enforced on the backend via Spring Security, method-level authorization, service authorization, or an API gateway. If an endpoint is not implemented, the controller should not map that method.

Do not use supportedSubmitMethods as the sole measure to protect production data.

## 10. Distinguishing hiding actions from hiding documentation

There are three distinct decisions:

1. **Keep the operation in OpenAPI but disable Try it out:** readers still see the endpoint, schemas, and responses, but cannot send requests from Swagger UI.
2. **Hide the operation from documentation:** the operation does not appear in published docs. Mechanisms like @Hidden or group-based filtering can be used when appropriate.
3. **Block the operation on the backend:** actual requests are rejected by security rules, authorization, routing, or gateway policies.

These three decisions do not substitute for one another. If you want partners to read an endpoint without testing write actions, keep the operation in docs and restrict supportedSubmitMethods. If an internal endpoint must not be published, control the documentation. If an endpoint must be protected, control runtime execution.

## 11. Risks of allowing try-it-out for write methods

POST, PUT, PATCH, and DELETE can usually mutate system state. When Try it out is open in an environment with real data, users can accidentally:

- Create duplicate orders or transactions.
- Update customer records.
- Change order statuses.
- Delete resources.
- Send emails or trigger background jobs.
- Call payment services or external integrations.

To reduce risk:

- Enable only necessary methods in each respective environment.
- Use test accounts with least privilege.
- Use mock or sandbox data whenever possible.
- Require business confirmation before irreversible actions.
- Protect endpoints with authentication and authorization.
- Inspect audit logs for data-mutating actions.
- Implement idempotency for transaction-creating requests where appropriate.

Do not rely on the UI to prevent operational mistakes. The backend must verify permissions and business conditions before applying changes.

## 12. CORS when Swagger UI calls an API on a different origin

Swagger UI is often loaded from one origin while the API server resides on another. Example:

- Swagger UI: https://docs.example.com
- API: https://api.example.com

When the browser sends a cross-origin request, the server's CORS policy determines which origins are permitted and which methods/headers are accepted.

If Try it out reports a CORS error, check:

- Does Access-Control-Allow-Origin allow Swagger UI's origin?
- Does Access-Control-Allow-Methods include the method being called?
- Does Access-Control-Allow-Headers allow Authorization, Content-Type, or custom headers?
- Does the request trigger an OPTIONS preflight?
- Is Spring Security's CORS configuration applied in the proper order?

Illustrative Spring MVC CORS configuration example:

~~~java
@Configuration
class WebCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("https://docs.example.com")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
            .allowedHeaders("Authorization", "Content-Type", "X-Request-Id");
    }
}
~~~

If using Spring Security, configure CORS integration with SecurityFilterChain and check preflight requests. CORS configuration only permits browsers from valid origins to read responses; it does not replace authentication or authorization.

Do not combine wildcard origins with credentials if application security policy forbids it. Only declare the origins that genuinely require access.

## 13. Authentication and authorization in Try it out

If an operation requires a bearer token, Swagger UI can provide the Authorize button based on the security scheme in OpenAPI. Users enter a token and send requests via Try it out.

Example bearer scheme declaration:

~~~java
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@Configuration
class OpenApiSecurityConfiguration {
}
~~~

Protected operation:

~~~java
@Operation(
    summary = "Get current profile",
    security = @SecurityRequirement(name = "bearerAuth")
)
@GetMapping("/api/me")
public ProfileResponse getProfile() {
    return profileService.current();
}
~~~

Distinguish clearly:

- OpenAPI security schemes tell Swagger UI how to send credentials.
- Authentication verifies the caller's identity.
- Authorization decides whether the caller has permission to perform the operation.
- supportedSubmitMethods only controls which methods can be invoked via Try it out.

If a user supplies an invalid token, the backend must still return 401. If the token is valid yet lacks permissions, the backend must return 403 per API policy. Never assume that because Swagger UI hides a method, the backend does not need permission checks.

## 14. CSRF and cookie-based authentication

If the application uses session cookies or cookie-based authentication, state-mutating requests may be subject to Spring Security CSRF protection.

When Try it out sends POST, PUT, PATCH, or DELETE, the request may be rejected if a valid CSRF token is missing. This is runtime security behavior, not a supportedSubmitMethods bug.

Identify the API's authentication mechanism:

- With bearer tokens sent via the Authorization header, CSRF configuration can differ from session-based apps.
- With cookie sessions, manage CSRF tokens and cookies according to policy.
- If Swagger UI runs on a different origin, CORS and cookie SameSite/credential policies also affect requests.

Do not disable CSRF merely to make the Execute button work. Configure protection suitable for the authentication model and attack surface of the application.

## 15. Verifying Swagger UI configuration after startup

After changing application.yml or application.properties, restart the application using the target environment configuration.

Open Swagger UI at the default path, typically:

~~~text
http://localhost:8080/swagger-ui.html
~~~

In many setups, this URL redirects to the UI under /swagger-ui/index.html. If the project changed springdoc.swagger-ui.path or has a context path, use the actual URL.

Check:

1. Do GET operations have the Try it out button?
2. Do POST operations have the Try it out button?
3. Are PUT/PATCH/DELETE operations enabled or disabled according to the list?
4. When the list is empty, are all Execute buttons disabled?
5. Are documentation, schemas, and responses still fully displayed?
6. Does the configuration match the currently active profile?

If nothing changed, verify the loaded configuration, active profile, environment variables, and browser cache. Try reloading the page without cache to avoid viewing an old bundle or config.

## 16. Inspecting the Swagger UI config endpoint

springdoc typically exposes Swagger UI configuration via the config endpoint, defaulting to:

~~~text
GET /v3/api-docs/swagger-config
~~~

You can check it with curl:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs/swagger-config
~~~

Depending on the springdoc version and config serialization, the response may contain UI settings such as document URL, config URL, OAuth redirect, and the submit methods list. Look for the matching property to confirm the values supplied by the backend to the UI.

If the config endpoint does not show the property in the expected way, that alone is insufficient to conclude the setting was ignored. Check reference documentation for the version in use and observe actual behavior in Swagger UI.

Do not directly modify JavaScript bundle files served by springdoc just to alter the method list. Configuring Spring Boot or an appropriate custom Swagger UI config is much easier to maintain across upgrades.

## 17. Distinguishing configuration errors from API call errors

When Try it out does not work, determine whether the fault lies in the UI or backend:

| Symptom | Where to check |
|---|---|
| No Try it out button | supportedSubmitMethods excludes the method, or another UI setting disabled it |
| Button exists but Execute fails | Inspect browser console and Network tab |
| Browser reports CORS | Check CORS, preflight, and origins |
| 401 response | Check token, security scheme, and authentication |
| 403 response | Check authorization or CSRF |
| 404 response | Check server URL, context path, and operation path |
| 405 response | Check HTTP methods supported by controller/gateway |
| 415 response | Check Content-Type and consumes |
| 400 response | Check request parameters, body, and validation |
| Swagger UI still shows a disabled method | Check runtime config, profile, config endpoint, and cache |

A hidden Try it out button does not mean the endpoint does not exist. Conversely, an available button does not guarantee the server will accept the request.

## 18. Verifying the server still protects endpoints

After restricting supportedSubmitMethods, still test the backend independently. For example, if Swagger UI only enables GET, sending a DELETE request directly to the endpoint must be evaluated against actual security policies.

~~~bash
curl -i -X DELETE http://localhost:8080/api/products/123
~~~

Expected outcomes depend on authorization and API design:

- May return 401 if unauthenticated.
- May return 403 if lacking permissions.
- May return 404 if the resource or route does not exist.
- May return 204 if the caller is authorized and deletion succeeds.

If policy dictates the current user cannot delete, tests must prove the backend returns 403 or the appropriate rejection even when requests originate outside Swagger UI.

Do not use a single hardcoded status code as the expectation for every application. Determine the principal's permissions, resource state, and policy under test.

## 19. Recommended policy by environment

A policy can be structured as follows:

| Environment | Recommended supportedSubmitMethods | Purpose |
|---|---|---|
| Local | GET, POST, PUT, PATCH, DELETE | Development and testing with local data |
| Development | GET, POST, PUT, PATCH | Testing write flows on test data |
| Staging | GET, POST, PUT, PATCH | Controlled UAT; enable DELETE only when needed |
| Production | GET or empty list | Reading documentation, reducing accidental UI writes |

This is only a reference policy. If production needs to let partners test endpoints in a sandbox, provide a dedicated sandbox environment with appropriate data and permissions.

Some teams disable Try it out completely in production while still publishing OpenAPI JSON for client generators. Distributing the spec and permitting UI-driven requests are two independent decisions.

## 20. Common mistakes

| Mistake | Consequence | Resolution |
|---|---|---|
| Thinking supportedSubmitMethods blocks APIs on the server | Clients outside Swagger UI can still call endpoints | Protect backend with Security/gateway |
| Leaving all methods enabled by default in production | Documentation viewers can test write/delete operations | Enable only genuinely needed methods |
| Using wrong letter casing | UI fails to apply expected methods | Use lowercase method names |
| Declaring an empty list with invalid YAML syntax | Binder may not interpret the empty value as expected | Use YAML empty list syntax and verify at runtime |
| Editing only application.yml while another profile overrides it | UI still shows old configuration | Check the final configuration source |
| Confusing tryItOutEnabled with supportedSubmitMethods | Wrong expectations around Execute button | Check default state and method list separately |
| Disabling write methods while forgetting CORS | GET or enabled methods can still be blocked by browser | Configure CORS for right origins/methods |
| Disabling CSRF to fix Execute errors | Weakens protection for session-based apps | Handle CSRF tokens matching the auth model |
| Hiding operations instead of only disabling Try it out | Readers can no longer see the endpoint contract | Pick the right mechanism: UI submit, hide docs, or backend security |
| Believing GET is always safe | A GET endpoint with side effects can still be invoked | Design GET as read-only and verify at runtime |

## 21. Checklist for configuring supportedSubmitMethods

- [ ] Identified which methods need testing in each environment.
- [ ] supportedSubmitMethods contains only necessary HTTP methods.
- [ ] Method names are written in lowercase.
- [ ] Aware that an empty list disables Try it out.
- [ ] Distinguished supportedSubmitMethods from tryItOutEnabled.
- [ ] Checked YAML/properties syntax against the springdoc version.
- [ ] Verified active profile and final configuration source.
- [ ] Swagger UI still displays operations and schemas meant to be published.
- [ ] Tested the Try it out button on each representative method.
- [ ] CORS permits the right origins and methods if UI is on a different origin.
- [ ] Authentication, authorization, and CSRF remain configured properly.
- [ ] Backend tests prove restricted methods cannot bypass security policies.
- [ ] Verified Swagger UI configuration after restarting the application.

## 22. References

- [springdoc-openapi – official documentation](https://springdoc.org/)
- [Swagger UI – Configuration](https://swagger.io/docs/open-source-tools/swagger-ui/usage/configuration/)
- [Swagger UI – Try it out](https://swagger.io/docs/open-source-tools/swagger-ui/usage/overview/)
- [Spring Boot – Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Security – CSRF](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Framework – CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html)

supportedSubmitMethods helps control which HTTP methods are permitted for testing in Swagger UI. It is a UX setting that reduces accidental actions from the UI; APIs still require authentication, authorization, CSRF/CORS, and business validation at runtime. After changing settings, verify Swagger UI, the config endpoint, and actual backend responses before applying to shared environments.
