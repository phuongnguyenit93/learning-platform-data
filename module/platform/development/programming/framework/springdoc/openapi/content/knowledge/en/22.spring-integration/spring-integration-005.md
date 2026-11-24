# Management Port Distinct from Application Port and Its Impact on the UI

Spring Boot can run business APIs on one port and Actuator management endpoints on a separate port. When using springdoc-openapi, Swagger UI and the OpenAPI document can also be moved to the management port. This deployment separates the management surface from the user-facing port, but changes the documentation URLs, how browsers call the API, and CORS requirements.

For example, an application running its API on port 8080 and its management server on port 9090:

- Business API: http://localhost:8080/api/orders.
- OpenAPI JSON: http://localhost:9090/actuator/openapi.
- Swagger UI: http://localhost:9090/actuator/swagger-ui.

To achieve this result, configure the management server with a port different from the application port, enable Actuator endpoint exposure for the endpoints registered by springdoc, and enable springdoc.use-management-port. If the UI on the management port calls an API on the application port, browsers treat the two addresses as two different origins and enforce CORS.

## 1. Distinguishing Application Port and Management Port

Spring Boot has two groups of port configuration:

| Property | Function | Example |
| --- | --- | --- |
| **server.port** | HTTP port serving controllers and business APIs | 8080 |
| **management.server.port** | Separate port for the management server and Actuator endpoints | 9090 |
| **management.server.address** | Network address the management server listens on | 127.0.0.1 |
| **management.endpoints.web.base-path** | URL prefix for Actuator web endpoints | /actuator |
| **springdoc.use-management-port** | Moves springdoc's Swagger UI and OpenAPI endpoints to the management port | true |

If management.server.port is not configured, Actuator typically shares the same web server as the application. When a different port is set, Spring Boot creates a separate management server. Thus, the two endpoint groups can have different network addresses, TLS, context paths, and access policies.

management.server.address can differ from the application server's address only when the management port differs from the application port. For instance, binding the management server to 127.0.0.1 allows only processes on the same host to reach the management port. If access from an operations network is needed, use an appropriate internal network address and restrict access with firewalls or network policies.

Do not confuse changing ports with securing endpoints. Port 9090 can still be reached externally if the server listens on all interfaces and the network allows connections.

## 2. Adding Actuator and Springdoc UI Dependencies

To serve the UI and specification on the management port, the application needs Spring Boot Actuator and the springdoc starter matching the web stack.

Gradle example for Spring MVC:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-actuator")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.10.0")
}
~~~

If the application uses WebFlux, replace the MVC starter with:

~~~groovy
implementation("org.springdoc:springdoc-openapi-starter-webflux-ui:2.10.0")
~~~

The example uses springdoc v2.10.0 for Spring Boot 3.x. Choose a springdoc version compatible with the Spring Boot line in use and manage versions centrally via a BOM or version catalog if the project has multiple modules. Do not arbitrarily mix starters from different major versions.

If only OpenAPI JSON/YAML is needed without Swagger UI, the corresponding API starter can be used. However, this lesson requires the UI starter because the goal is accessing Swagger UI on the management port.

## 3. Configuring Management Port and Springdoc

Example application.yml:

~~~yaml
server:
  port: 8080

management:
  server:
    port: 9090
    # Listen only on localhost in this example.
    # Remove or replace with the management network address when remote access is needed.
    address: 127.0.0.1
  endpoints:
    web:
      base-path: /actuator
      exposure:
        include: "health,info,openapi,swagger-ui"

springdoc:
  use-management-port: true
~~~

Key configurations:

- server.port: 8080 keeps the business API on the application server.
- management.server.port: 9090 creates the management server on a separate port.
- management.server.address restricts the listening interface. In this example, only localhost can access it.
- management.endpoints.web.exposure.include enables Actuator endpoints to be accessed over HTTP.
- springdoc.use-management-port: true registers OpenAPI and Swagger UI under the management endpoint base path.

If remote access to the management port is needed, do not use 127.0.0.1; bind to the required internal interface, configure TLS, and restrict source access at the network layer.

In application.properties, the equivalent properties are:

~~~properties
server.port=8080
management.server.port=9090
management.server.address=127.0.0.1
management.endpoints.web.base-path=/actuator
management.endpoints.web.exposure.include=health,info,openapi,swagger-ui
springdoc.use-management-port=true
~~~

By default, Spring Boot exposes only a limited set of Actuator endpoints over HTTP, typically including health. When setting an include list, only the listed endpoints are exposed over HTTP. Do not use management.endpoints.web.exposure.include=* just to make Swagger UI work. Expose only the endpoints actually needed.

## 4. URLs When use-management-port Is Enabled

With the configuration above, springdoc registers endpoints under the Actuator base path:

| Resource | URL |
| --- | --- |
| Actuator base path (discovery links depend on config) | http://localhost:9090/actuator |
| OpenAPI definition | http://localhost:9090/actuator/openapi |
| Swagger UI | http://localhost:9090/actuator/swagger-ui |

The paths openapi and swagger-ui are Actuator endpoint IDs registered by springdoc. If management.endpoints.web.base-path is changed to /manage, the corresponding URLs become:

- http://localhost:9090/manage/openapi
- http://localhost:9090/manage/swagger-ui

The names of these two endpoints created by springdoc under the Actuator base path cannot currently be customized using springdoc's regular path properties.

Key takeaway: when springdoc.use-management-port=true, springdoc path properties such as springdoc.api-docs.path and springdoc.swagger-ui.path do not apply to endpoints exposed on the management port. Adjust management.endpoints.web.base-path if you want to change the Actuator prefix.

Standard URLs such as /v3/api-docs or /swagger-ui.html belong to serving on the application web server. When using the management port, access endpoints under the configured Actuator base path rather than inferring URLs from default Swagger UI configuration.

## 5. Exposing Endpoints Does Not Grant Permissions

management.endpoints.web.exposure.include determines which endpoints are published over HTTP. This property does not define which users are allowed to access them.

Two configuration layers must be considered separately:

1. **Exposure:** whether the endpoint is registered and reachable over HTTP.
2. **Security:** whether the caller is permitted to view or use the endpoint.

An OpenAPI definition can reveal endpoint names, data structures, error models, and deployment details. Swagger UI also allows sending requests to the API. Therefore, the management port needs an access policy appropriate for the documentation it serves.

For example, allow only users with the OPS role to access Actuator endpoints, while leaving health open for probes:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ManagementSecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain managementSecurity(HttpSecurity http)
            throws Exception {
        return http
            .securityMatcher(EndpointRequest.toAnyEndpoint())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to("health"))
                    .permitAll()
                .anyRequest()
                    .hasRole("OPS")
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

This is an example for the servlet stack. Real-world applications need an appropriate authentication mechanism and a separate filter chain for business APIs if required. When declaring multiple SecurityFilterChain beans, place the Actuator matcher at an appropriate priority order so management rules are not intercepted first by a broad chain.

If Spring Security relies on default auto-configuration, declaring a custom SecurityFilterChain can cause default security configuration to back off. Explicitly define the chains protecting management endpoints, Swagger UI, and business APIs.

## 6. Management Port Can Use Separate TLS and Address

The management server has its own SSL properties under the management.server.ssl prefix. They do not automatically match server.ssl configuration.

Example of both the application server and management server using HTTPS:

~~~yaml
server:
  port: 8443
  ssl:
    enabled: true
    key-store: classpath:application-keystore.p12
    key-store-password: ${APP_KEYSTORE_PASSWORD}
    key-store-type: PKCS12

management:
  server:
    port: 9443
    ssl:
      enabled: true
      key-store: classpath:management-keystore.p12
      key-store-password: ${MANAGEMENT_KEYSTORE_PASSWORD}
      key-store-type: PKCS12
~~~

The example only illustrates two independent TLS configurations; keystores and passwords must be supplied securely per environment. Never commit real passwords into source control.

Spring Boot also allows the management server to use a different SSL configuration from the application server. That can be useful in an internal management network, though sensitive management traffic should not run over unencrypted HTTP on untrusted networks.

If you do not want to provide management HTTP endpoints, set management.server.port=-1 or remove endpoints from web exposure. Disabling HTTP exposure does not necessarily mean other management channels, such as JMX, are disabled as well.

## 7. Distinguishing use-management-port and show-actuator

The two springdoc properties have different purposes:

| Property | Purpose |
| --- | --- |
| springdoc.use-management-port | Moves the OpenAPI endpoint and Swagger UI/Scalar interface to the management port |
| springdoc.show-actuator | Adds documentation for Actuator endpoints to OpenAPI/Swagger UI |

Both can be combined:

~~~yaml
springdoc:
  use-management-port: true
  show-actuator: true
~~~

When show-actuator is enabled, springdoc can add a separate group for Actuator endpoints. If the application has no groups yet, springdoc can create a default group for the application API.

If only show-actuator=true is enabled without use-management-port, Swagger UI continues to be served on the application port. When the management port differs from the application port, a UI on the application port that calls Actuator endpoints on the management port needs CORS on those Actuator endpoints.

Conversely, when use-management-port=true is enabled, the UI and OpenAPI endpoint live under the Actuator base path. If the UI calls business APIs on the application port, CORS must be configured on the application server.

## 8. Impact on Try it out and CORS

Suppose:

- Swagger UI is loaded from http://localhost:9090/actuator/swagger-ui.
- The business API runs at http://localhost:8080/api/orders.

The two URLs share the same hostname but have different ports, making them two different origins. When a user clicks Try it out, the browser sends a request from origin http://localhost:9090 to http://localhost:8080. Without a matching CORS policy, the browser can block the request or prevent JavaScript from reading the response.

Example CORS configuration for the application API:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class ApiCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/**")
            .allowedOrigins("http://localhost:9090")
            .allowedMethods("GET", "POST", "PUT", "PATCH", "DELETE")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Request-Id"
            )
            .maxAge(3600);
    }
}
~~~

If using cookie sessions or cross-origin credentials, enable allowCredentials(true) and specify explicit origins. Do not combine credentials with the wildcard origin *. Also configure credentials properties on the client if Swagger UI or the request mechanism requires them.

When using Spring Security, CORS must be handled before authorization rejects preflight OPTIONS requests. CORS configuration in Spring MVC can be integrated with Spring Security via http.cors(...) or the application's corresponding configuration.

If the API and Swagger UI are served under the same scheme, host, and port via a reverse proxy, browsers treat them as same-origin and CORS is not needed. In that case, the proxy must route API requests to the application server and documentation requests to the management server.

## 9. Ensuring the OpenAPI Server URL Points to the Application Port

A common point of confusion when the UI runs on the management port is the API's base URL. The OpenAPI document is fetched from the management server, whereas business controllers still run on the application server.

Inspect the servers field in the OpenAPI JSON. If the server URL is relative or mistakenly points to the management port, Try it out may send requests to 9090 instead of 8080.

For local environments, you can declare an explicit server URL:

~~~java
import io.swagger.v3.oas.annotations.OpenAPIDefinition;
import io.swagger.v3.oas.annotations.servers.Server;
import org.springframework.context.annotation.Configuration;

@Configuration
@OpenAPIDefinition(
    servers = {
        @Server(
            url = "http://localhost:8080",
            description = "Application API"
        )
    }
)
class OpenApiServerConfiguration {}
~~~

If the application has context path /shop, the server URL must include the context path, for example http://localhost:8080/shop. For production, use the external API URL clients actually call, such as https://api.example.com; do not put localhost or internal management ports into public documentation.

In multi-environment systems, externalize the server URL via profile-based configuration or create an OpenAPI bean reading values from configuration. Do not hardcode a local URL across all environments.

## 10. Reverse Proxy and Context Path

In production, the management port is usually not exposed directly to the Internet. A reverse proxy or management network can route public paths to the management server.

Example:

~~~text
https://ops.example.com/manage/openapi
        |
        v
Reverse proxy
        |
        v
management server :9090
~~~

When configuring a proxy:

- Route the Actuator base path properly to the management port.
- Preserve or map the path prefix accurately.
- Configure external host, scheme, and port properly if the application generates redirect URLs.
- Only trust Forwarded or X-Forwarded-* headers from trusted proxies.
- Do not directly expose the management port if the architecture requires access only via VPN or an operations network.

The application context path and the management endpoint base path are two separate scopes. For instance, the API has context path /shop while management endpoints have base path /actuator; do not assume one prefix automatically applies to both servers.

When changing management.endpoints.web.base-path, Actuator endpoints move to the new prefix. If a separate management port is configured, the base path is resolved according to the corresponding management server configuration. Check the Spring Boot documentation for your exact version when the application has a separate management context path.

## 11. Verifying Endpoints After Startup

After the application starts, check each server individually:

~~~bash
# Business API on the application port
curl -i http://localhost:8080/api/orders

# OpenAPI definition on the management port
curl -i http://localhost:9090/actuator/openapi

# Swagger UI endpoint on the management port
curl -i http://localhost:9090/actuator/swagger-ui
~~~

If the management port is bound to 127.0.0.1, run the commands only from the same host. If endpoints require authentication, provide credentials according to the configured mechanism; do not leave real passwords in shell history or shared logs.

In the browser:

1. Open http://localhost:9090/actuator/swagger-ui.
2. Verify Swagger UI loads JavaScript, CSS, and the OpenAPI definition.
3. Open the Network panel and confirm the request fetching the documentation goes to the management port.
4. Check the servers field in the OpenAPI definition.
5. Run Try it out and confirm business requests go to the application port.
6. If requests are blocked, inspect the OPTIONS preflight and CORS response.
7. Verify authentication and authorization on both management endpoints and business APIs.

Do not conclude the configuration is correct merely because the Swagger UI page renders. The UI can load successfully while an incorrect OpenAPI server URL or missing CORS stops Try it out from calling the API.

## 12. Common Mistakes

**/actuator/swagger-ui returns 404.** Check that the Actuator dependency, springdoc UI starter, and springdoc.use-management-port=true are present, and that endpoint ID swagger-ui is in management.endpoints.web.exposure.include.

**/actuator/openapi returns 404.** Check that the openapi endpoint is exposed. If management.endpoints.web.base-path was changed, use the new prefix instead of /actuator.

**Management server does not start on a separate port.** Check that management.server.port differs from server.port, the port is not occupied by another process, and the bind address is valid.

**Swagger UI remains on the application port.** Check whether springdoc.use-management-port is enabled in the active profile and the right config file is loaded. Distinguish it from springdoc.show-actuator, which only adds Actuator documentation to the UI.

**Properties springdoc.api-docs.path or springdoc.swagger-ui.path have no effect.** When springdoc.use-management-port=true, regular springdoc path properties do not apply to Actuator endpoints. Use management.endpoints.web.base-path instead.

**UI page opens but Try it out fails with CORS.** The UI and API are on different origins. Allow the exact Swagger UI origin on the application server with the proper methods/headers and credentials if needed.

**Try it out sends requests to the management port instead of the application port.** Inspect the servers field in the OpenAPI definition. Set the server URL to point to the application API and include any necessary context path.

**UI cannot reach Actuator endpoints when using show-actuator=true.** If the UI runs on the application port while Actuator runs on a different management port, CORS is required on the Actuator endpoints.

**Management endpoints are publicly reachable.** Check management.server.address, firewalls, network policies, TLS, Spring Security, and the exposure list. A separate port alone does not create a security boundary.

**After changing base path, proxy returns 404.** Synchronize management.endpoints.web.base-path with the reverse proxy routes and the URLs operators access.

**Documentation uses HTTP while application API uses HTTPS.** Check management.server.ssl.* and the external proxy scheme. Never allow credentials or tokens to travel over plain HTTP on untrusted networks.

## 13. Deployment Checklist

- [ ] Actuator and springdoc UI starter matching MVC/WebFlux are present.
- [ ] Choose management.server.port distinct from server.port when separating the management server.
- [ ] Configure management.server.address according to the intended network scope.
- [ ] Expose at least openapi and swagger-ui via Actuator.
- [ ] Enable springdoc.use-management-port=true.
- [ ] Use URLs under the Actuator base path to access OpenAPI and Swagger UI.
- [ ] Do not rely on springdoc.api-docs.path or springdoc.swagger-ui.path when using the management port.
- [ ] Distinguish use-management-port from show-actuator.
- [ ] Protect OpenAPI and Swagger UI with authentication, authorization, and network policy.
- [ ] Configure separate TLS for the management server if needed.
- [ ] Verify servers in OpenAPI points to the application API.
- [ ] Configure CORS on the proper server when UI and API have different origins.
- [ ] Synchronize context paths and reverse proxy routes.
- [ ] Verify URLs with curl and the Browser Network panel.

## 14. Conclusion

The management port separates operational endpoints from the business API port. With springdoc, enabling springdoc.use-management-port=true and exposing the two Actuator endpoints openapi and swagger-ui moves the documentation onto the management server. The UI will live under the Actuator base path while business controllers continue running on the application port. Therefore, verify the OpenAPI server URL, configure CORS when two ports form two origins, and protect the management port with authentication, TLS, and network policies. Port separation helps organize the access surface cleanly; actual security still depends on exposure, security, and network configuration.

## 15. References

- [Spring Boot — Monitoring and Management Over HTTP](https://docs.spring.io/spring-boot/reference/actuator/monitoring.html): management port, address, base path, SSL, and web exposure.
- [springdoc-openapi v2 — Actuator support](https://springdoc.org/v2/#actuator-support): springdoc.use-management-port, endpoint IDs openapi/swagger-ui, Actuator base path, show-actuator, and CORS requirements.
- [springdoc-openapi v2 — Core Properties](https://springdoc.org/v2/core-properties.html): configuring springdoc.use-management-port.
- [Spring Boot — Actuator Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): endpoint exposure and accessing Actuator endpoints.
- [Spring Framework — CORS](https://docs.spring.io/spring-framework/reference/web/webmvc-cors.html): configuring CORS for cross-origin requests in Spring MVC.
