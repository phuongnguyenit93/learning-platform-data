# Preparing an Endpoint That Returns Replica Identity for Observation

When a service runs multiple replicas, clients call it by service ID and Spring Cloud LoadBalancer selects an instance to handle each request. From the client's perspective, all requests are sent to the same logical address, such as `reservation-service`. If the response does not indicate which instance handled the request, it is hard to observe load distribution results and hard to investigate cases where only one replica fails.

This lesson belongs to the **Project Setup** chapter of the `SPRING_CLOUD_SERVICE_COMMUNICATION_LOAD_BALANCING` module. The module focuses on client-side load balancing with Spring Cloud LoadBalancer: selecting a `ServiceInstance` by service ID, discovery, health checks, and routing policies; practicing integration with `RestClient`, `WebClient`, OpenFeign, retries/timeouts, and error observability. The identity endpoint is a small observation point prepared upfront: each replica returns a distinct identifier so we can tell where a request landed.

After this lesson, you will be able to:

- Distinguish a service ID from the unique identifier of each instance.
- Configure a stable identifier for each replica of a service.
- Create an HTTP endpoint that returns minimal identifying information as JSON.
- Run multiple replicas and verify each replica returns a different identifier.
- Call the endpoint through a LoadBalancer-enabled client to observe the selected instance.
- Recognize the limitations of a diagnostic endpoint and how to protect operational information.

## 1. Why Do We Need an Instance Identity Endpoint?

Suppose `reservation-service` is running three replicas:

- The first replica runs at `10.0.1.11:8080`.
- The second replica runs at `10.0.1.12:8080`.
- The third replica runs at `10.0.1.13:8080`.

The client only knows the service ID `reservation-service`. Service discovery provides the instance list, and Spring Cloud LoadBalancer selects an instance from that list. Once a request reaches a server, the application needs a simple way to answer the question: "Which replica just handled this request?"

We can add an endpoint:

```http
GET /internal/instance
```

The endpoint returns example JSON:

~~~json
{
  "serviceId": "reservation-service",
  "instanceId": "reservation-2",
  "zone": "zone-a",
  "version": "1.4.0"
}
~~~

Each replica has the same service ID but a different instance ID. When calling the endpoint through LoadBalancer, the client can inspect the instance ID in the response to see which replica received the request.

Observation flow:

~~~mermaid
flowchart LR
    A["Client calls reservation-service"] --> B["Spring Cloud LoadBalancer"]
    B --> C["Select ServiceInstance"]
    C --> D["Replica 1"]
    C --> E["Replica 2"]
    C --> F["Replica 3"]
    D --> G["GET /internal/instance"]
    E --> G
    F --> G
    G --> H["JSON containing replica's instanceId"]
~~~

The endpoint only provides identifying information. It does not register the instance into service discovery, select instances, or perform load balancing. Those responsibilities still belong to the service registry and Spring Cloud LoadBalancer.

## 2. Distinguishing Service ID and Instance ID

These two concepts play different roles:

| Concept | Example | Meaning |
|---|---|---|
| Service ID | `reservation-service` | Logical name used by clients to call a service. |
| Instance ID | `reservation-2` | Identifier of a specific replica of that service. |
| Instance address | `10.0.1.12:8080` | Host and port the client connects to after an instance is selected. |
| Version | `1.4.0` | Application version running on the replica. |

Typically, the service ID is configured via `spring.application.name`. Replicas of the same service share this name so they are registered under the same logical service.

The instance ID must distinguish replicas sharing the same service ID. If every replica returned `reservation-service` as its instance ID, the endpoint would not help determine which replica handled a request.

In this lesson, we use a custom property `app.instance.id` for the diagnostic endpoint. This property does not automatically become `ServiceInstance.getInstanceId()` in every discovery system. If you want the identifier returned by the endpoint to match the identifier in the registry, configure the registry's corresponding instance ID property as well.

## 3. Configuring a Unique Identity for Each Replica

First, declare the service name and identity properties in `application.yml`:

~~~yaml
spring:
  application:
    name: reservation-service

server:
  port: ${SERVER_PORT:8080}

app:
  instance:
    id: ${APP_INSTANCE_ID:${HOSTNAME:${COMPUTERNAME:local}}}
    zone: ${APP_INSTANCE_ZONE:local}
    version: ${APP_VERSION:dev}
~~~

Explanation:

- `spring.application.name` is the service ID used in inter-service communication.
- `server.port` specifies the process's HTTP port.
- `app.instance.id` is the replica's unique identifier. The application prioritizes the `APP_INSTANCE_ID` environment variable; if absent, it falls back to the runtime environment's hostname, and finally `local`.
- `app.instance.zone` is the deployment zone information if the system has a zone concept; when running locally, this can be left as `local`.
- `app.instance.version` indicates the running build or release version.

The `local` fallback is only convenient when running a single process for development. When running multiple replicas, assign a distinct ID to each replica. Do not let multiple replicas share the same default value, as responses will be unable to distinguish them.

You can pass values via command-line arguments when running two local processes:

~~~bash
java -jar reservation-service.jar --server.port=8081 --app.instance.id=reservation-1
java -jar reservation-service.jar --server.port=8082 --app.instance.id=reservation-2
~~~

Both processes share the same `spring.application.name`, but have different ports and instance IDs. Each command should be run in a separate terminal.

In Kubernetes, you can take the Pod name as the instance ID via the Downward API:

~~~yaml
env:
  - name: APP_INSTANCE_ID
    valueFrom:
      fieldRef:
        fieldPath: metadata.name
~~~

Pod names typically distinguish replicas within the same workload. If the deployment platform uses another hostname or identifier mechanism, pick a unique value that remains stable over the replica's lifecycle and pass it into `APP_INSTANCE_ID`.

Do not generate a new UUID on every endpoint call. The instance ID must stay constant across requests to the same process; if it changes per request, you will confuse a request identifier with a replica identifier.

## 4. Mapping Configuration into a Java Type

Use `@ConfigurationProperties` to group related properties into a type:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.instance")
public record InstanceIdentityProperties(
    String id,
    String zone,
    String version
) {}
~~~

Enable configuration properties scanning on the main application class:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ReservationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReservationApplication.class, args);
    }
}
~~~

Spring Boot binds the values under `app.instance` into `InstanceIdentityProperties`. Other components can inject this type to access the process's identity.

If the project already uses `@EnableConfigurationProperties(InstanceIdentityProperties.class)`, you can keep that registration approach instead of `@ConfigurationPropertiesScan`. Just ensure the properties class is registered in the Spring context.

## 5. Creating the Response DTO and Endpoint

Do not expose the entire configuration object or environment information over HTTP. Define a response DTO containing only the fields needed for observation:

~~~java
public record InstanceIdentityResponse(
    String serviceId,
    String instanceId,
    String zone,
    String version
) {}
~~~

Next, create the controller:

~~~java
import org.springframework.core.env.Environment;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/internal")
public class InstanceIdentityController {

    private final InstanceIdentityProperties identity;
    private final Environment environment;

    public InstanceIdentityController(
            InstanceIdentityProperties identity,
            Environment environment) {
        this.identity = identity;
        this.environment = environment;
    }

    @GetMapping(
        value = "/instance",
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public InstanceIdentityResponse getInstanceIdentity() {
        String serviceId = environment.getProperty(
            "spring.application.name",
            "unknown"
        );

        return new InstanceIdentityResponse(
            serviceId,
            identity.id(),
            identity.zone(),
            identity.version()
        );
    }
}
~~~

The controller reads the service ID from Spring configuration and retrieves instance ID, zone, and version from the bound properties. Spring MVC uses a message converter with Jackson to serialize the record into a JSON response.

When calling the endpoint, the response looks like:

~~~json
{
  "serviceId": "reservation-service",
  "instanceId": "reservation-1",
  "zone": "local",
  "version": "dev"
}
~~~

If calling the second replica, the `instanceId` field will be `reservation-2`. The remaining fields may match if both replicas run with the same zone and version configuration.

## 6. Testing Each Replica Directly

Before testing LoadBalancer, call each process directly to verify that configuration and the endpoint work.

With two processes running on ports 8081 and 8082:

~~~bash
curl http://localhost:8081/internal/instance
curl http://localhost:8082/internal/instance
~~~

Expected output:

~~~json
{
  "serviceId": "reservation-service",
  "instanceId": "reservation-1",
  "zone": "local",
  "version": "dev"
}
~~~

~~~json
{
  "serviceId": "reservation-service",
  "instanceId": "reservation-2",
  "zone": "local",
  "version": "dev"
}
~~~

If using PowerShell:

~~~powershell
Invoke-RestMethod http://localhost:8081/internal/instance
Invoke-RestMethod http://localhost:8082/internal/instance
~~~

At this step, we call the host and port directly, so load balancing is not tested yet. The purpose is to confirm each process returns the exact identifier configured for it.

If both responses show the same instance ID, inspect startup arguments, environment variables, and configuration precedence order. Spring Boot allows command-line arguments to override values in `application.yml`, so verify the final value received by the application.

## 7. Observing the Selected Instance Through LoadBalancer

Once both replicas are registered in the discovery mechanism used by the application, the client calls by service ID instead of a fixed address. For example, with a `RestClient` configured with `@LoadBalanced`:

~~~java
InstanceIdentityResponse response = restClient.get()
    .uri("http://reservation-service/internal/instance")
    .retrieve()
    .body(InstanceIdentityResponse.class);
~~~

The client sends the request to the logical address `reservation-service`. Spring Cloud LoadBalancer retrieves the list of available instances, selects an instance, and forwards the request to the corresponding host and port. The endpoint on the chosen instance returns its own instance ID.

Calling multiple times and recording the `instanceId` field lets you observe which replicas are selected. For example, the results might appear in sequence as:

~~~text
reservation-1
reservation-2
reservation-1
reservation-2
reservation-1
~~~

This is only an illustrative output. Do not require the counts of each ID to be strictly equal. Actual results depend on the instance list provided by discovery, the instance selection strategy, availability status, per-service configuration, and the timing of requests.

The identity endpoint answers "which replica did the request reach?" To explain why that replica was selected, you also need to observe the instance list, LoadBalancer configuration, health checks, and routing algorithm.

If the client always receives the same instance ID, check these in order:

1. Have all replicas actually started and registered under the same service ID?
2. Does service discovery return all instances?
3. Is the client using an HTTP client annotated with `@LoadBalanced` and calling by service ID?
4. Are the instances currently considered available?
5. Does per-service configuration or the selection strategy restrict the candidate list?
6. Is the response being cached at another layer?

Do not conclude LoadBalancer is broken just because a short sequence of requests did not hit every replica. Observe a sufficient number of requests, verify the registry, and cross-check the running configuration.

## 8. Relating Instance ID to Service Discovery

In this lesson, `app.instance.id` is application data used to respond from the endpoint. The service registry may have its own instance identifier field. The two values only match when you intentionally configure them to align.

For example, if the project uses Eureka, you can combine the service ID and the application's instance ID in Eureka configuration:

~~~yaml
eureka:
  instance:
    instance-id: ${spring.application.name}:${app.instance.id}
~~~

Then, the registry can distinguish registrations of the same service using the configured instance ID. The exact property syntax depends on the discovery client and library version the project uses. With Consul or another registry, use the corresponding instance identifier property of that platform.

Distinguish three values when investigating:

- **Service ID**: the logical name requested by the client.
- **Registry instance ID**: the identifier registered by the discovery client and returned in instance metadata, if supported by the platform.
- **Application instance ID**: the value returned by the application from the diagnostic endpoint.

If all three values are synchronized, correlating logs, the registry, and HTTP responses becomes much easier. If they differ, clearly document the mapping convention so operators do not misinterpret them.

## 9. Protecting the Endpoint and Limiting Returned Information

An identity endpoint is useful in development, testing, and internal observation. However, every diagnostic endpoint must be reviewed before exposure to public environments.

Several principles:

- Only return necessary fields such as service ID, instance ID, zone, and version.
- Do not return environment variables, system properties, file paths, credentials, tokens, connection configurations, or secret contents.
- If the endpoint is internal-only, apply appropriate network policies or authentication/authorization to restrict callers.
- Do not put personal data or sensitive information into the instance ID.
- Do not use this endpoint in place of readiness or liveness probes.

A successful response from `/internal/instance` only shows that the request reached the application and the controller could respond. It does not prove the database, message broker, or dependent services are healthy. Use Spring Boot Actuator health endpoints and readiness/liveness probes for health checking.

In environments with Spring Security, the `/internal/instance` path may be protected by existing rules. Only permit the required internal callers; avoid opening the entire internal endpoint group to the Internet for testing convenience.

## 10. Verification Checklist

Before using the endpoint in LoadBalancer exercises, verify the following conditions:

| Check | Expected Result |
|---|---|
| Multiple replicas of the same service | Replicas share the same service ID. |
| Per-replica identity | Each replica has a distinct instance ID. |
| Stability | A replica returns the same instance ID across multiple requests. |
| Endpoint | `GET /internal/instance` returns HTTP 200 and valid JSON. |
| Identity fields | Response includes service ID, instance ID, and required metadata. |
| Direct calls | Each host/port returns its configured ID. |
| Calls via LoadBalancer | Client uses service ID and observes the selected instance's ID. |
| Discovery | Registry provides the list of active instances. |
| Security | Response contains no secrets or unnecessary environment details. |

When a request through LoadBalancer returns an instance ID, we have application-layer evidence of which replica handled that request. Combining this data with logs, correlation IDs, the registry, and health check state makes routing behavior analysis much clearer.

## 11. Key Points to Remember

- Service ID identifies a logical service; instance ID identifies a specific replica.
- Replicas of the same service share `spring.application.name`, but must have distinct identifiers if per-replica observation is needed.
- Identifiers must stay stable across a replica's lifecycle and be supplied by configuration or the deployment platform.
- The `GET /internal/instance` endpoint only returns identifying information; it does not perform discovery or load balancing.
- Calling each port directly verifies each process's configuration; calling via a LoadBalancer-enabled client observes the selected instance.
- The application instance ID does not automatically match the registry instance ID; configure the mapping if you want them unified.
- Keep the response minimal and protect the endpoint within internal access boundaries.

After preparing this endpoint, subsequent hands-on lessons can call the same service ID repeatedly and read the instance ID in the response to observe Spring Cloud LoadBalancer's `ServiceInstance` selection results.
