# Separating Service Lists by Profile and Environment

Across development, testing, and production environments, the same microservice typically has different instance addresses. For example, `inventory-service` may run on `localhost` during development, use a Docker Compose DNS service name during integration, and use an internal hostname in production deployment. If these addresses are hardcoded in source code, the application must be modified or repackaged every time it moves between environments.

Spring Cloud `SimpleDiscoveryClient` allows declaring service IDs and URI lists via configuration. Spring Boot Profiles select the configuration set corresponding to the running environment. As a result, the same application can look up services by logical name while receiving addresses appropriate for the active profile.

## 1. SimpleDiscoveryClient and static configuration

Spring Cloud provides the `DiscoveryClient` abstraction to resolve a service ID into a list of `ServiceInstance` objects. When no `DiscoveryClient` implementation backed by a registry server is on the classpath, Spring Cloud can use `SimpleDiscoveryClient`. This implementation reads instance information from application configuration.

The configuration prefix is:

    spring.cloud.discovery.client.simple.instances

Each service ID has an instance list indexed from `0`. Each element declares the instance's URI:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081
                  - uri: http://localhost:8082
                payment-service:
                  - uri: http://localhost:8091

In the example, `inventory-service` has two instances and `payment-service` has one instance. When the application calls `DiscoveryClient.getInstances("inventory-service")`, `SimpleDiscoveryClient` returns two `ServiceInstance` objects with the corresponding URIs.

Static configuration does not register instances with Eureka or Consul. It also does not automatically discover new instances, perform periodic health checks, or automatically update when an address stops working. The operations team must maintain the URI list and redeploy or reload configuration according to the application's mechanism whenever the list changes.

**Note on dependencies:** `SimpleDiscoveryClient` is used when no service-registry-backed `DiscoveryClient` is on the classpath. If the application has added Consul Discovery or Eureka Client, the corresponding implementation may be used instead of `SimpleDiscoveryClient`. When practicing static discovery independently, inspect the discovery dependencies present in the application; do not assume that merely adding `simple.instances` configuration will override Consul or Eureka.

## 2. Spring Profiles separate environment configuration

Spring Profiles allow loading a subset of configuration only when the corresponding profile is active. Spring Boot supports configuration files by convention:

- `application.yml`: shared configuration for all environments.
- `application-local.yml`: configuration for a developer's machine.
- `application-test.yml`: configuration for the test environment.
- `application-docker.yml`: configuration when services run inside a Docker network.
- `application-prod.yml`: production configuration.

Spring Boot loads `application.yml` and the active profile file(s). Values in profile-specific files take higher precedence than corresponding values in the shared file. If multiple profiles are active simultaneously, a profile processed later can override values from an earlier profile.

You can organize the configuration directory as follows:

    src/main/resources/
      application.yml
      application-local.yml
      application-test.yml
      application-docker.yml
      application-prod.yml

This organization lets each environment have its own instance list without changing Java code.

## 3. Placing shared configuration in application.yml

The shared file should contain environment-independent properties, such as the application name and shared discovery settings:

    spring:
      application:
        name: order-service

Do not place a URI list suitable only for a developer's machine in `application.yml` if this file is packaged and used across multiple environments. If the shared configuration contains `localhost` endpoints, a missing or inactive profile could cause a production application to mistakenly call its own container.

You can keep instance lists entirely inside each profile-specific file to avoid having to override a default list.

## 4. Configuring the instance list for local

Example `application-local.yml`:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081
                  - uri: http://localhost:8082
                payment-service:
                  - uri: http://localhost:8091

When running locally, the application can look up two `inventory-service` instances and one `payment-service` instance. These ports are examples only; they must match the actual ports the services are listening on on the development machine.

If a service has only one instance, still declare a list with one element:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081

## 5. Configuring the instance list for test and Docker

In integration tests, services may run on hostnames or ports provisioned by the test environment. Example `application-test.yml`:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-test.internal:18081
                payment-service:
                  - uri: http://payment-test.internal:18091

If the application runs alongside services inside a Docker Compose network, use the service name as the internal hostname instead of `localhost`. Example `application-docker.yml`:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-service:8080
                  - uri: http://inventory-service-canary:8080
                payment-service:
                  - uri: http://payment-service:8080

In Docker, `localhost` inside a container points to that same container. If `order-service` calls `localhost:8080`, the request goes to `order-service` rather than the `inventory-service` container. Service name DNS only resolves when containers are on the appropriate network and the target service is declared properly.

## 6. Configuring the instance list for production

Example `application-prod.yml`:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: https://inventory-a.internal:8443
                  - uri: https://inventory-b.internal:8443
                payment-service:
                  - uri: https://payment.internal:9443

In production, declare only approved hostnames and ports that are resolvable and reachable from the calling application's network. If endpoints use HTTPS, the application's certificates and trust store must be configured properly.

Do not place usernames, passwords, access tokens, or API keys in URIs. Use a secret manager or the platform's secret management mechanism to supply credentials separately.

Static configuration is only appropriate when the instance list is relatively stable and has a clear update workflow. If production frequently scales, replaces, or creates instances automatically, a dynamic registry or the deployment platform's service discovery is usually better suited.

## 7. Activating a profile when running the application

There are multiple ways to activate a profile. Choose one suited to the deployment environment.

**Command line**

    java -jar order-service.jar --spring.profiles.active=local

**Environment variable on Linux**

    SPRING_PROFILES_ACTIVE=test java -jar order-service.jar

**JVM system property**

    java -Dspring.profiles.active=docker -jar order-service.jar

**Docker Compose**

    services:
      order-service:
        image: example/order-service
        environment:
          SPRING_PROFILES_ACTIVE: docker
        networks:
          - backend

The profile value must match the configuration file suffix. `SPRING_PROFILES_ACTIVE=docker` causes Spring Boot to load `application-docker.yml` alongside `application.yml`.

Do not set `spring.profiles.active=prod` by default in the shared `application.yml` file. If a runtime environment forgets to set a profile, the application might accidentally load production config on a developer machine or vice versa. Specify the profile explicitly in the launch command, environment variable, or deployment configuration.

## 8. Using multiple profiles at the same time

Spring Boot allows activating multiple profiles, separated by commas:

    java -jar order-service.jar --spring.profiles.active=docker,observability

Here `docker` provides the URI list and `observability` can enable logging or metrics configuration. When the same property is declared in multiple profiles, the last-wins rule applies: the profile processed later can override the value of an earlier profile.

You can use profile groups to bundle related profiles:

    spring:
      profiles:
        group:
          production:
            - prod
            - observability

Then you only need to run:

    java -jar order-service.jar --spring.profiles.active=production

Spring Boot activates the `production` profile and its member profiles. `spring.profiles.group` declarations must live in a profile-independent configuration document, such as `application.yml`; do not place them inside `application-prod.yml`.

## 9. Multi-document YAML as an alternative

Instead of creating multiple files, you can use multiple YAML documents in the same `application.yml` and activate each document with `spring.config.activate.on-profile`:

    spring:
      application:
        name: order-service

    ---
    spring:
      config:
        activate:
          on-profile: local
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://localhost:8081
                  - uri: http://localhost:8082

    ---
    spring:
      config:
        activate:
          on-profile: docker
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-service:8080

    ---
    spring:
      config:
        activate:
          on-profile: prod
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: https://inventory-a.internal:8443
                  - uri: https://inventory-b.internal:8443

Only documents whose profile expression matches are added to the `Environment`. This approach is convenient when configuration is short and there are few environments. When service lists grow long or environments differ significantly, splitting into `application-{profile}.yml` files is usually easier to maintain and review.

## 10. Understanding precedence and configuration merging

Spring Boot allows multiple configuration sources to supply the same property. Profile-specific files override corresponding values in the shared file; command-line arguments, environment variables, and higher-precedence sources can also alter the final value.

With `SimpleDiscoveryClient` configuration, pay attention to nested data types:

- `instances` is a Map keyed by service ID.
- The value for each service ID is a List of instances.
- Different Map keys can be contributed from multiple configuration sources.
- If the same service ID has instance lists in multiple sources, the higher-precedence list replaces the entire previous list; elements are not appended automatically.

Example `application.yml`:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: http://inventory-default-1:8080
                  - uri: http://inventory-default-2:8080
                payment-service:
                  - uri: http://payment-default:8080

Example `application-prod.yml`:

    spring:
      cloud:
        discovery:
          client:
            simple:
              instances:
                inventory-service:
                  - uri: https://inventory-prod.internal:8443

When the `prod` profile is active, the `inventory-service` list contains only `inventory-prod.internal:8443`. It does not retain the two instances from `application.yml`. `payment-service` can still keep the shared value because it is a different Map key and is not overridden by the `prod` profile.

To avoid confusion, declare the complete list of instances for a service inside the profile file whenever that service needs an environment-specific list. Do not rely on an element in a profile being appended to the shared list.

## 11. Default profile and misconfigured activation

If no profile is explicitly activated, Spring Boot uses the default profile named `default`. You can declare `application-default.yml` to supply configuration for this case, but in multi-environment systems you should proactively set a profile to avoid using the wrong URI list.

Some common mistakes:

- Placing `spring.profiles.active` inside `application-local.yml` or a YAML document activated with `on-profile`. The `active` property may only be declared in a profile-independent document.
- Misspelling the profile name, such as activating `docker` when the file is `application-container.yml`.
- Declaring a service list in `application.yml` pointing to `localhost` and forgetting to override it in production.
- Activating both `local` and `prod` simultaneously, causing one profile to override the other's URIs.
- Specifying a profile list on the command line while forgetting it can replace `active` values declared in a lower-precedence configuration source.
- Using `spring.config.location` pointing to a single file and expecting Spring Boot to auto-discover all profile-specific variants as it does with a config directory location. Check the Config Data rules of your Spring Boot version.

Inspect startup logs to confirm which profiles are actually active. Do not rely solely on file names existing inside the JAR.

## 12. Verifying DiscoveryClient receives the right list

You can inject `DiscoveryClient` and print the instance list to confirm the profile supplies the right URIs:

    import java.util.List;

    import org.springframework.cloud.client.ServiceInstance;
    import org.springframework.cloud.client.discovery.DiscoveryClient;
    import org.springframework.core.env.Environment;
    import org.springframework.stereotype.Component;

    @Component
    public class DiscoveryConfigurationCheck {

        private final DiscoveryClient discoveryClient;
        private final Environment environment;

        public DiscoveryConfigurationCheck(
                DiscoveryClient discoveryClient,
                Environment environment) {
            this.discoveryClient = discoveryClient;
            this.environment = environment;
        }

        public void logInventoryInstances() {
            String[] profiles = environment.getActiveProfiles();

            List<ServiceInstance> instances =
                    discoveryClient.getInstances("inventory-service");

            System.out.println("Active profiles: "
                    + String.join(",", profiles));

            for (ServiceInstance instance : instances) {
                System.out.println(
                        instance.getServiceId() + " -> " + instance.getUri()
                );
            }
        }
    }

In a real project, use a logger instead of `System.out` and avoid logging sensitive information. If the list is empty, check whether `SimpleDiscoveryClient` is actually being used, whether the service ID matches exactly, and whether the profile file was loaded.

You can also inspect further via Actuator `env` or `configprops` in a protected development environment. Do not expose these endpoints to public networks just to diagnose configuration.

## 13. Combining DiscoveryClient and LoadBalancer

`DiscoveryClient` only returns the `ServiceInstance` list. If the application needs to invoke a service, you can use Spring Cloud LoadBalancer to select an instance from that list.

Example with `RestTemplate`:

    @Configuration
    public class ClientConfiguration {

        @Bean
        @LoadBalanced
        RestTemplate restTemplate() {
            return new RestTemplate();
        }
    }

Calling the service by service ID:

    restTemplate.getForObject(
            "http://inventory-service/api/items/42",
            Item.class
    );

LoadBalancer uses `DiscoveryClient` to fetch the instance list for `inventory-service` and selects one instance according to the configured policy. When the profile changes, the URIs returned by `DiscoveryClient` change according to the loaded configuration.

Remember that `SimpleDiscoveryClient` does not check whether endpoints are actually running. LoadBalancer can select a stale URI if static configuration has not been updated. The application still needs timeouts, error handling, and a workflow to update configuration when addresses change.

## 14. Testing workflow for environment separation

You can verify profile configuration with these steps:

1. Start `inventory-service` on the two local ports declared in `application-local.yml`.
2. Run `order-service` with the `local` profile.
3. Call `getInstances("inventory-service")` and confirm the list contains only the two local URIs.
4. Stop the local services and start the service set inside the Docker network.
5. Run `order-service` with the `docker` profile.
6. Confirm the returned list uses Docker DNS service names and internal ports.
7. Test the `prod` profile in an equivalent staging environment, verifying hostnames, TLS, and network policies before release.
8. Restart `order-service` with each profile to confirm no URIs from a previous environment remain.

Record the active profile, service ID, and returned URIs in each test run. This data helps catch misconfigured environment mistakes before live requests hit an endpoint.

## 15. When should profile-based static configuration be used?

This approach fits well when:

- The number of services and instances is small and changes infrequently.
- Each environment has a known endpoint list ahead of time.
- Addresses are managed alongside deployment configuration.
- You need to demo or test service discovery without standing up Eureka or Consul.
- There is a release process to update URI lists when the topology changes.

Do not rely on static lists when applications autoscale, instances are replaced frequently, or health checks and dynamic registration are required. In those cases, Eureka, Consul, or the deployment platform's service discovery helps keep the registry aligned with the running topology.

Separating profiles is not a network security mechanism. Endpoints in `application-prod.yml` must still be protected with TLS, firewalls, network policies, and application-layer authentication as needed.

## 16. Conclusion

`SimpleDiscoveryClient` allows declaring instance lists using `spring.cloud.discovery.client.simple.instances`. Spring Boot Profiles select the right URI list for local, test, Docker, or production without changing source code. Place shared settings in `application.yml`, place environment-specific URIs in `application-{profile}.yml`, and activate profiles explicitly via command line or environment variables.

When overriding configuration, remember that the instance list for a given service is replaced as a whole rather than merged cumulatively across profiles. Finally, verify the active profiles and `getInstances()` output before allowing consumers to call services. For frequently changing topologies, migrate to a dynamic registry rather than continuing to maintain static lists manually.

## References

- [Spring Cloud Commons — SimpleDiscoveryClient](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html)
- [Spring Boot — Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Boot — Properties and Configuration](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html)
