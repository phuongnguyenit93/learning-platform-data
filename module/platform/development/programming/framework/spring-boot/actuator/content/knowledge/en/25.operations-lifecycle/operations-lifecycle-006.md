# Enabling the shutdown Endpoint Intentionally and Checking Support Limits

`shutdown` is a management operation used to ask Spring Boot to close the `ApplicationContext` of the instance receiving the request. With default path configuration, the HTTP operation is `POST /actuator/shutdown` and requires no request body. Closing the context triggers Spring's shutdown lifecycle, including stopping the embedded server and destroying beans according to their lifecycle callbacks. Because this operation disrupts serving, Spring Boot 3.3 disables this endpoint by default. [shutdown API](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/shutdown.html) · [ShutdownEndpoint](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/context/ShutdownEndpoint.html)

## Checking Version, Packaging Type, and Access Permissions

1. **Check the deployment packaging.** Spring Boot 3.3 documents `shutdown` support for JAR packaging. The typical case is an executable JAR running with an embedded server. For a WAR deployed to an external servlet container, use the stop or undeploy mechanism of that container or its management platform. Seeing a mapped route alone is not enough to confirm that deployment type is within the supported scope. [Spring Boot 3.3 endpoint list](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
2. **Enable and expose the endpoint over HTTP.** In Spring Boot 3.3, `management.endpoint.shutdown.enabled=true` enables the endpoint. Add `shutdown` to `management.endpoints.web.exposure.include` to make it callable over HTTP. If `exclude` also lists `shutdown`, exclusion takes precedence. Verify the effective configuration of active profiles and any launch-time overrides. [Enabling and exposing endpoints in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html)
3. **Use the version-appropriate property.** Spring Boot 3.4 documentation uses `management.endpoint.shutdown.access=unrestricted` to allow write operations on the endpoint. The global ceiling `management.endpoints.access.max-permitted=read-only` still blocks write operations. The `access` property controls which Actuator operations are permitted, whereas HTTP exposure and caller permissions are governed by separate configuration layers. [Endpoint access in Spring Boot 3.4](https://docs.spring.io/spring-boot/3.4/reference/actuator/endpoints.html)
4. **Restrict callers.** In shared environments, allow only authenticated and authorized operational principals to invoke shutdown. You can restrict the management port to an internal network and apply access control to management routes. When using Spring Security, `POST` is also subject to the CSRF rules of the applicable security filter chain. Verify permissions and appropriate CSRF tokens before changing security policies. [Securing Actuator endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security)

## Trying on a Local JAR

Prepare a Spring Boot 3.3 executable JAR using `spring-boot-starter-web` and `spring-boot-starter-actuator`. The exercise assumes the sample application uses the default management base path, the same port as the application, and no Spring Security. Name the copy of the JAR used for testing `shutdown-demo.jar`. In the same directory, create `application-shutdown-lab.properties`.

```properties
server.address=127.0.0.1
server.port=8080
management.endpoint.shutdown.enabled=true
management.endpoints.web.exposure.include=health,shutdown
server.shutdown=graceful
spring.lifecycle.timeout-per-shutdown-phase=20s
```

`server.shutdown=graceful` enables shutdown with a wait period on the embedded server in Spring Boot 3.3. When the context closes, the server gives in-flight requests time to finish within the configured limit. Here `20s` is the timeout per Spring lifecycle shutdown phase. This setting controls **how** the server stops, whereas the Actuator configuration controls **how a stop is requested**. [Graceful shutdown in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/web/graceful-shutdown.html)

Start the application and wait for the server to come up.

```bash
java -jar ./shutdown-demo.jar --spring.profiles.active=shutdown-lab
```

From a second terminal, check the server and then send exactly one shutdown request. In PowerShell on Windows, use `curl.exe`.

```bash
curl -i http://127.0.0.1:8080/actuator/health
curl -i -X POST http://127.0.0.1:8080/actuator/shutdown
```

The second request returns `200 OK` with a body like the following.

```json
{"message":"Shutting down, bye..."}
```

The response confirms the request has initiated the shutdown process. To confirm shutdown completed, watch the context-closing logs or verify the server stops responding after the wait phase finishes. With the sample JAR, you can also verify that the `java -jar` command exited in the first terminal. In systems with multiple instances, verify which instance received the request and whether a process manager restarts it.

## Interpreting Results When Testing Limits

| Result in the exercise | What to check |
| --- | --- |
| `POST` returns `404` while `/actuator/health` still returns `200` | Check the management base path and endpoint enable/exposure configuration. Try restarting with `--management.endpoint.shutdown.enabled=false` or `--management.endpoints.web.exposure.exclude=shutdown`, one property at a time. Both cases return `404` in the sample app while the application keeps running. |
| `GET /actuator/shutdown` returns `405` when the route is mapped | Use `POST` for the write operation. You can use `GET /actuator` to inspect discovery links if enabled. |
| `POST` returns `401` or `403` in a secured environment | Check credentials, permission to perform the operation, and CSRF policy. Exposing the endpoint over HTTP only allows the route to be mapped. |
| Connection fails | Check that the process is still running, the listen address, and the management port. If `management.server.port` is set, send requests to the configured management port. |

If you customize `management.endpoints.web.base-path`, use the configured prefix instead of `/actuator`. A proxy or security filter chain can also return a response before the request reaches Actuator. [Management paths and ports](https://docs.spring.io/spring-boot/3.3/reference/actuator/monitoring.html)
