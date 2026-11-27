# Case Sensitivity and Configuration Mapping for defaultZone

When a Spring Cloud Netflix Eureka application starts up, Eureka Client needs to know the Eureka Server's address to register its instance and fetch the service list. This address is typically configured via the eureka.client.serviceUrl.defaultZone key. A small casing mistake in defaultZone can prevent the client from picking up the declared URL and cause it to keep trying to connect to the default localhost:8761 address.

The reason lies in how configuration mapping works: serviceUrl is a Map<String, String>, and defaultZone is a key in that Map. Map keys are matched by exact string, so defaultZone must keep its uppercase Z. This rule differs from Spring Boot's normal relaxed binding for JavaBean properties.

## 1. Role of defaultZone

Eureka Client has two main responsibilities:

- Registering the current instance's information with Eureka Server, if register-with-eureka is enabled.
- Fetching the registry to discover instances of other services, if fetch-registry is enabled.

Both flows require the Eureka Server address. Spring Cloud Netflix stores these addresses in the serviceUrl property, which has type Map<String, String>. Each Map key represents an availability zone, and its value is the URL or list of URLs for the Eureka Server in that zone.

defaultZone is a special fallback key. When the client does not match a specific zone, it uses the defaultZone value to locate the Eureka Server. This is why Spring Cloud documentation uses this exact camelCase form.

Minimal example:

    eureka:
      client:
        serviceUrl:
          defaultZone: http://localhost:8761/eureka/

In this example, the Eureka Server URL is http://localhost:8761/eureka/. If the application runs in a container, localhost points to the application container itself. When Eureka Server runs in another container on the same Docker network, you must use the Eureka container's DNS service name, such as http://eureka-server:8761/eureka/.

## 2. Why Is defaultZone Case-Sensitive?

Spring Boot supports relaxed binding for regular property names. For instance, a JavaBean property named serviceUrl can be expressed using corresponding property forms such as service-url or serviceUrl across supported configuration sources.

However, defaultZone is not the name of a standalone JavaBean property. It is a key inside the serviceUrl Map. Spring Cloud Netflix looks up the default key using the string defaultZone. Therefore, the following strings are distinct keys:

| Declared Key | Is Valid Fallback Key? | Explanation |
|---|---|---|
| defaultZone | Yes | Exact camelCase, uppercase Z |
| defaultzone | No | Lowercase z, a different key |
| default-zone | No | Contains a hyphen, a different key |
| DEFAULTZONE | No | All uppercase, a different key |
| DefaultZone | No | Uppercase D, a different key |

Do not blindly apply Spring Boot's kebab-case rules to this key name. Spring Cloud Netflix documentation explicitly states that defaultZone is case-sensitive because serviceUrl is a Map<String, String>; it does not follow Spring Boot's usual snake-case/kebab-case conventions.

## 3. Proper Declaration in application.yml

Standard YAML configuration:

    spring:
      application:
        name: order-service

    eureka:
      client:
        serviceUrl:
          defaultZone: http://localhost:8761/eureka/
        register-with-eureka: true
        fetch-registry: true

Key points to note:

- spring.application.name is the logical application name; Eureka uses it as the default service ID if no other name is configured.
- eureka.client.serviceUrl is the Map of server addresses by zone.
- defaultZone must keep the uppercase Z.
- register-with-eureka controls whether the current instance registers with Eureka.
- fetch-registry controls whether the client fetches the instance list from Eureka.

In YAML, indentation defines structure. defaultZone must be a child of serviceUrl, nested under eureka.client. If placed at the wrong level, the Binder may create a different property or fail to bind the value into the intended Map.

## 4. Proper Declaration in application.properties

With a properties file, use the full key name:

    spring.application.name=order-service
    eureka.client.serviceUrl.defaultZone=http://localhost:8761/eureka/
    eureka.client.register-with-eureka=true
    eureka.client.fetch-registry=true

You can use properties configuration when you want to preserve the exact Map key string and inspect each line easily. The critical part remains that the final segment must be defaultZone, not default-zone or defaultzone.

Equivalent YAML and properties configurations must produce the same Map key:

    serviceUrl = {
        "defaultZone": "http://localhost:8761/eureka/"
    }

This is a helpful mental model when diagnosing issues: do not just check the URL string—check whether the URL has been bound to the right Map key.

## 5. Common Misconfigurations

First incorrect example:

    eureka:
      client:
        serviceUrl:
          default-zone: http://localhost:8761/eureka/

default-zone is a different Map key. Relaxed binding does not automatically turn this Map key into Eureka's special defaultZone key.

Second incorrect example:

    eureka:
      client:
        serviceUrl:
          defaultzone: http://localhost:8761/eureka/

defaultzone has a lowercase z, so it does not match the fallback key.

Third incorrect example:

    eureka:
      client:
        serviceUrl:
          DEFAULTZONE: http://localhost:8761/eureka/

DEFAULTZONE is also a different key. Eureka does not normalize all Map keys to the same casing.

If the defaultZone key is missing or not bound properly, Eureka Client may fall back to the default URL localhost:8761/eureka/. Logs will then typically show the client attempting to connect to localhost even though your intended configuration points to another hostname.

## 6. Pitfalls When Using Environment Variables

Environment variables are commonly used to pass configuration into Docker, Kubernetes, or CI/CD environments. For simple properties, Spring Boot has rules to convert property names to uppercase with underscores. For example:

    eureka.client.enabled
    EUREKA_CLIENT_ENABLED

But serviceUrl is a Map. Spring Boot documents that when binding environment variables to a Map property, Map key names are converted to lowercase. As a result, the environment variable:

    EUREKA_CLIENT_SERVICEURL_DEFAULTZONE

may create the Map key defaultzone. This key does not match the defaultZone key that Eureka expects. This is a common reason why other environment variable settings work while Eureka Client still connects to localhost:8761.

For this special Map key, prefer declaring it in application.yml or application.properties. If you need to pass configuration via environment variables, you can use SPRING_APPLICATION_JSON to preserve uppercase letters in the JSON key name:

    SPRING_APPLICATION_JSON={"eureka":{"client":{"serviceUrl":{"defaultZone":"http://eureka-server:8761/eureka/"}}}}

Example in Docker Compose:

    services:
      order-service:
        image: example/order-service
        environment:
          SPRING_APPLICATION_JSON: >-
            {"eureka":{"client":{"serviceUrl":{"defaultZone":"http://eureka-server:8761/eureka/"}}}}

The JSON property source preserves the defaultZone key name inside the JSON payload. Verify the actual configuration loaded by the application after startup, especially when application.yml, profiles, and environment variables coexist.

Another option is passing a JVM system property with the exact key name:

    java -Deureka.client.serviceUrl.defaultZone=http://eureka-server:8761/eureka/ -jar order-service.jar

System properties preserve camelCase. Whichever option you choose, never assume that the EUREKA_CLIENT_SERVICEURL_DEFAULTZONE environment variable is always completely equivalent to the defaultZone Map key.

## 7. Using defaultZone with Multiple Eureka Servers

A value in serviceUrl can contain a single URL or a comma-separated list of URLs. This gives the client multiple addresses to try when one Eureka Server is unreachable.

Example:

    eureka:
      client:
        serviceUrl:
          defaultZone: http://eureka-1:8761/eureka/,http://eureka-2:8761/eureka/

The URLs should point to Eureka Servers that exchange registry data with each other in a peer-aware architecture. Configuring multiple URLs does not create replication on its own; the Eureka Servers still need proper peer replication configuration.

If deploying a standalone Eureka Server and you do not want it to register itself or fetch the registry from peers, you can configure:

    eureka:
      client:
        register-with-eureka: false
        fetch-registry: false

For a typical Eureka Client, both properties are usually kept true so the client registers its own instance and looks up other services.

## 8. Zone, Region, and the Fallback Key

In multi-zone deployments, Eureka Client can use region and availability zone settings to determine the preferred group of Eureka Servers. The serviceUrl Map stores URLs keyed by zone name. If no matching zone is found for the client, defaultZone acts as the fallback.

Illustrative example:

    eureka:
      client:
        region: ap-southeast-1
        availability-zones:
          ap-southeast-1: zone-a,zone-b
        serviceUrl:
          zone-a: https://eureka-a.internal/eureka/
          zone-b: https://eureka-b.internal/eureka/
          defaultZone: https://eureka-default.internal/eureka/

Zone names are Map keys, so they must match the zone names returned by the availability-zones configuration. defaultZone must still use exact camelCase. When designing for multiple zones, clearly define the region, the instance's zone, and the zone used by the client; if you only have a single Eureka Server, configuring defaultZone is usually sufficient.

## 9. Verifying That Configuration Has Been Applied

When a client cannot connect to Eureka Server, check in the following order:

1. **Check the exact key:** confirm the configuration contains eureka.client.serviceUrl.defaultZone with an uppercase Z.
2. **Check YAML placement:** serviceUrl must be under eureka.client; defaultZone must be under serviceUrl.
3. **Check configuration sources:** identify the active profile and sources that might override the URL, such as environment variables, JVM system properties, or command-line arguments.
4. **Check logs:** look for the URL Eureka Client is using and any connection errors. If logs still mention localhost:8761, check whether defaultZone was bound properly.
5. **Check networking:** test the URL from the actual runtime environment of the application. In a container, use a service name or DNS name resolvable by the container instead of the host's localhost.
6. **Check the server endpoint:** Eureka Server must be running and exposing the appropriate context path, typically /eureka/.
7. **Check multiple URLs:** verify that each URL in a comma-separated list is reachable and belongs to the intended Eureka cluster.

You can enable more detailed logging while diagnosing:

    logging:
      level:
        com.netflix.discovery: DEBUG
        org.springframework.cloud.netflix.eureka: DEBUG

Only enable DEBUG during investigation because log volume can increase significantly. Disable or lower the log level after confirming the configuration.

Do not expose the env or configprops endpoints to public networks just to inspect configuration. If you need to check effective configuration via Actuator, restrict access and only do so in a controlled environment.

## 10. Complete Practical Example

Suppose Eureka Server runs in Docker Compose with service name eureka-server and port 8761. The order-service client runs on the same Docker network. Client YAML configuration:

    spring:
      application:
        name: order-service

    server:
      port: 8080

    eureka:
      client:
        serviceUrl:
          defaultZone: http://eureka-server:8761/eureka/
        register-with-eureka: true
        fetch-registry: true
        registry-fetch-interval-seconds: 10

In this example:

- defaultZone preserves the uppercase Z.
- eureka-server is the DNS service name that the client container can resolve.
- Port 8761 is the Eureka Server port inside the Docker network.
- /eureka/ is the Eureka Server context path.
- order-service registers with Eureka and fetches the registry periodically.

After startup, verify across three layers:

- **Connectivity:** logs no longer show connection errors to localhost:8761; the client reaches eureka-server.
- **Registration:** the Eureka Dashboard displays the ORDER-SERVICE instance with the expected host and port.
- **Lookup:** another Eureka DiscoveryClient can locate ORDER-SERVICE by its service ID.

If the client still uses localhost, recheck the Map key name and overriding configuration sources before changing networking.

## 11. Conclusion

defaultZone is the fallback key in Eureka Client's serviceUrl Map. The uppercase Z must be exact because it is a Map key looked up by Eureka, not a JavaBean property automatically normalized by relaxed binding. Use the canonical form eureka.client.serviceUrl.defaultZone in properties or serviceUrl.defaultZone in YAML.

Be especially careful when moving configuration into environment variables: Spring Boot lowercases Map keys bound from environment variables, which can turn defaultZone into defaultzone. Use configuration files, JVM system properties, or SPRING_APPLICATION_JSON when you need to preserve the key name; then verify the actual URL in logs and confirm the client connects to the right Eureka Server.

## References

- [Spring Cloud Netflix — Eureka Client: Registering with Eureka](https://docs.spring.io/spring-cloud-netflix/reference/spring-cloud-netflix.html)
- [Spring Boot — Externalized Configuration: Binding Maps From Environment Variables](https://docs.spring.io/spring-boot/reference/features/external-config.html)
- [Spring Cloud Netflix — EurekaClientConfigBean](https://github.com/spring-cloud/spring-cloud-netflix/blob/main/spring-cloud-netflix-eureka-client/src/main/java/org/springframework/cloud/netflix/eureka/EurekaClientConfigBean.java)
