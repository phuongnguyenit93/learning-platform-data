# Observing Registrations and Status via the Eureka REST API

## 1. Why Observe the Registry via the REST API?

Eureka Server stores a registry containing registered applications and instances. Each instance publishes information such as service ID, host, port, status, metadata, and lease duration. When a microservice cannot find an instance, calls the wrong address, or still sees a stopped instance, operators need to inspect the data Eureka Server currently holds.

Eureka provides a REST API for clients to register, renew, deregister, and read the registry. The read endpoints are very useful when you want to:

- Confirm whether an application has registered with the right service ID.
- Check which instances are currently published and whether host/port are accurate.
- View statuses such as UP, DOWN, or OUT_OF_SERVICE.
- Inspect version metadata and lease information.
- Compare the registry across multiple Eureka Servers to detect discrepancies.
- Investigate why a client does not yet see an instance or still sees stale data.

The REST API reports the state currently stored by Eureka Server at query time. It does not directly test every business endpoint, nor does it prove that every peer or client already has the exact same data.

## 2. Base Address of the Eureka REST API

In the default configuration, Eureka Server normally runs on port 8761 and has a service URL ending in /eureka/:

~~~yaml
server:
  port: 8761

eureka:
  client:
    service-url:
      defaultZone: http://localhost:8761/eureka/
~~~

The Dashboard is typically accessed at:

~~~text
http://localhost:8761/
~~~

The REST API for managing the registry typically has the base path:

~~~text
http://localhost:8761/eureka
~~~

If the application changes the port, context path, servlet path, or reverse proxy configuration, construct the endpoint using the environment's actual address. Do not assume every environment uses localhost or port 8761.

Commonly used read endpoints:

| HTTP method | Endpoint | Purpose |
|---|---|---|
| GET | /eureka/apps | Read the entire registry |
| GET | /eureka/apps/{APP_NAME} | Read the instances of an application |
| GET | /eureka/apps/{APP_NAME}/{INSTANCE_ID} | Read a specific instance |
| GET | /eureka/apps/delta | Read registry changes since the previous sync using Eureka's delta mechanism |

Eureka supports representing data as JSON or XML via content negotiation. When calling with an HTTP tool, send an appropriate Accept header, such as application/json.

## 3. Reading the Entire Registry

To view the list of applications and instances currently held by Eureka Server, send a GET request to /eureka/apps:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8761/eureka/apps
~~~

On Windows PowerShell, use curl.exe to invoke the curl executable rather than the Invoke-WebRequest alias:

~~~powershell
curl.exe -i -H "Accept: application/json" http://localhost:8761/eureka/apps
~~~

The JSON response has a general structure similar to:

~~~json
{
  "applications": {
    "versions__delta": "1",
    "apps__hashcode": "UP_2_",
    "application": [
      {
        "name": "PAYMENT-SERVICE",
        "instance": [
          {
            "instanceId": "payment-service:8081",
            "hostName": "payment-01",
            "app": "PAYMENT-SERVICE",
            "ipAddr": "10.0.1.21",
            "status": "UP",
            "overriddenStatus": "UNKNOWN",
            "port": {
              "$": 8081,
              "@enabled": "true"
            },
            "metadata": {
              "version": "2.4.1"
            }
          }
        ]
      }
    ]
  }
}
~~~

This is a simplified example to illustrate the structure; an actual response may contain additional fields and representations depending on the Eureka version. In Eureka JSON, the list of applications resides in applications.application; each application has a name and a list of instances.

### 3.1. Fields to Pay Attention To

| Field | Meaning |
|---|---|
| name | Application name in the registry; Eureka normally normalizes the name to uppercase |
| instanceId | Identifier of an instance within the application |
| app | Application name associated with the instance |
| hostName | Hostname published by the instance |
| ipAddr | Published IP address |
| status | Current status recorded by the registry |
| overriddenStatus | Override status if present; UNKNOWN usually means no override |
| port | HTTP port and attribute indicating whether the port is enabled |
| securePort | HTTPS port and enabled/disabled attribute if the instance publishes a secure port |
| metadata | Key/value pairs published by the application, such as version or build |
| leaseInfo | Lease duration and registration/renewal timestamps if included in the response |

The application name in the registry may differ in letter casing from the application's configuration. When querying by APP_NAME, use the application name displayed by the registry to avoid confusion.

## 4. Looking Up an Application or an Instance

### 4.1. Looking Up All Instances of an Application

If you only care about payment-service, use the endpoint by application name:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8761/eureka/apps/PAYMENT-SERVICE
~~~

The response contains only the requested application and the instances that the Eureka node currently holds for that application. This is faster when the registry contains many services.

### 4.2. Looking Up a Specific Instance

Once you know the instance ID, you can read an individual instance:

~~~bash
curl -i -H "Accept: application/json" http://localhost:8761/eureka/apps/PAYMENT-SERVICE/payment-service%3A8081
~~~

In the example URL, the colon in the instance ID is encoded as %3A. Use the actual instance ID from the registry and URL-encode special characters if they appear in the path.

Looking up a single instance is useful when verifying the host, port, metadata, status, and lease of a specific deployment.

## 5. Reading Instance Status

The status field describes the state recorded by the Eureka registry for an instance. Common values include:

| Status | General meaning | Operational interpretation |
|---|---|---|
| UP | Instance is marked ready | May be considered by discovery clients, depending on cache and instance selection policy |
| DOWN | Instance is marked unavailable | Investigate the cause and application state |
| STARTING | Instance is in startup phase | Should not yet be treated as a normally serving instance |
| OUT_OF_SERVICE | Instance is taken out of service | Commonly used during maintenance or to drain an instance from traffic |
| UNKNOWN | Specific status cannot be determined | Inspect the status source and configuration |

The list of statuses and how providers use them can depend on the version, implementation, and override state. Do not infer that an instance is definitely healthy solely because its status is UP.

### 5.1. Status and Health Check Are Different

Status is the state published by the instance or registry. A health check is an assessment of the health of the application or one of its components. The two pieces of information are related but not identical:

- An application may continue sending heartbeats while a business endpoint is failing.
- An instance may be marked OUT_OF_SERVICE during maintenance even while the process is still running.
- If health check integration is not enabled or not properly configured, Eureka may not reflect Actuator's status as expected.

For a Eureka Client integrated with Spring Boot Actuator, you can enable health check integration in application.yml:

~~~yaml
eureka:
  client:
    healthcheck:
      enabled: true
~~~

When enabled, Eureka Client uses the application's health state to update its published status via the integration mechanism. Check the documentation for the release train in use and verify the behavior in a test environment. Enabling health check integration does not replace designing proper readiness/liveness probes.

## 6. Reading Leases and Heartbeats

Each instance registered with Eureka has a lease so the server knows whether the client is still renewing its registration. In the API response, the leaseInfo field can contain data such as:

| leaseInfo field | Meaning |
|---|---|
| renewalIntervalInSecs | Heartbeat interval declared by the instance |
| durationInSecs | Published lease duration |
| registrationTimestamp | Timestamp when the instance registered |
| lastRenewalTimestamp | Timestamp of the most recently recorded renewal |
| evictionTimestamp | Eviction timestamp if the instance was removed |
| serviceUpTimestamp | Timestamp when the instance transitioned to UP, if present |

Timestamps in Eureka responses are typically represented as milliseconds since the Unix epoch. When analyzing them, convert timestamps into human-readable times and compare using a consistent time zone.

For example, if renewalIntervalInSecs is 30 and durationInSecs is 90, the client is expected to renew every 30 seconds and the lease lasts 90 seconds. If lastRenewalTimestamp is significantly older than the current time, check client-server connectivity, renewal logs, and eviction status.

An expired lease does not necessarily make an instance disappear at that exact instant. Eureka Server runs an eviction task periodically; self-preservation can also delay eviction when heartbeat volume drops abnormally. Consequently, a stale instance may remain in the registry for some time.

## 7. Reading Version Metadata

Metadata allows an application to publish additional instance information. For example:

~~~yaml
spring:
  application:
    name: payment-service

eureka:
  instance:
    metadata-map:
      version: 2.5.0
      build: 2026.11.24
      region: ap-southeast-1
~~~

Once the instance registers and the registry updates, these values can appear in the metadata field of the REST API response.

Metadata is useful for:

- Distinguishing running versions within the same application.
- Identifying builds or deployment regions.
- Supporting internal dashboards and rollout verification tools.
- Allowing clients with custom logic to filter instances by metadata if the architecture requires it.

Eureka only stores and distributes metadata; it does not automatically perform canary, blue-green, or version-based routing. If version-based routing is needed, implement an explicit policy in the gateway or client load balancer.

Do not place passwords, tokens, private keys, or sensitive data in metadata because registry data can be queried by many clients.

## 8. Comparing the Registry Across Eureka Servers

In a Eureka cluster, each server maintains a local registry and exchanges changes with peers. Because replication has latency, querying two nodes at the same moment may temporarily return different data.

For example, reading an application from two nodes:

~~~bash
curl -s -H "Accept: application/json" http://eureka-a:8761/eureka/apps/PAYMENT-SERVICE
curl -s -H "Accept: application/json" http://eureka-b:8762/eureka/apps/PAYMENT-SERVICE
~~~

Compare:

- Number of instances.
- Instance IDs.
- Hostnames and IPs.
- Ports.
- Status and overriddenStatus.
- Metadata version/build.
- Last renewal timestamp if present.

If two nodes differ, first determine whether the change was just registered. Then inspect peer logs, connection errors, sync timing, and self-preservation status. A single discrepant read is not enough to conclude the registry is broken; repeat the observation after an appropriate interval.

### 8.1. Full Registry vs. Delta

The GET /eureka/apps endpoint returns the full registry on the queried node. The GET /eureka/apps/delta endpoint returns changes since the previous sync using Eureka's delta mechanism. Eureka Clients typically use delta fetches to reduce the amount of data transferred.

When investigating incidents, the full registry is suitable for viewing overall state. Delta is useful for understanding recent changes, though delta contents depend on sync state and client/server caches. Do not treat a single delta response as a complete snapshot of the registry.

## 9. Related Lifecycle Endpoints

In addition to GET endpoints for observation, the Eureka REST API has endpoints used by Eureka Clients during the registration lifecycle:

| HTTP method | Endpoint | Role |
|---|---|---|
| POST | /eureka/apps/{APP_NAME} | Register a new instance |
| PUT | /eureka/apps/{APP_NAME}/{INSTANCE_ID} | Renew lease (heartbeat/renew) |
| DELETE | /eureka/apps/{APP_NAME}/{INSTANCE_ID} | Deregister an instance |

POST, PUT, and DELETE operations are normally performed automatically by Eureka Client. Avoid invoking them manually in routine operations unless you fully understand the request body, instance ID, state, and impact on the registry. This lesson focuses on the GET endpoints for observing data.

## 10. Distinguishing Eureka REST API, Dashboard, and Actuator

These three tools answer different questions:

| Tool | Primary data | Used to answer |
|---|---|---|
| Eureka Dashboard | Visual presentation of the registry on a Eureka Server | Which applications and instances is the server currently displaying? |
| Eureka REST API | Structured JSON/XML registry data | What host, port, status, lease, and metadata does an instance have? |
| Spring Boot Actuator | Health, metrics, and operational info of a single process | How healthy is the application itself? |

For example, the REST API might show payment-service as UP. However, if the application's /actuator/health endpoint reports DOWN because the database is unreachable, the instance still may not serve requests properly if health integration or readiness does not yet reflect that state.

Use the REST API to confirm registry data and Actuator to check the application. When concluding serviceability, combine both with logs and metrics.

## 11. Security When Querying the Eureka REST API

The registry contains internal topology, instance addresses, ports, and metadata. Therefore, protect the endpoints:

- Allow access only from management networks or workloads that need discovery.
- Use TLS when traffic traverses untrusted networks.
- Configure authentication/authorization if required by the environment.
- Do not expose the dashboard or REST API to the Internet without a protective layer.
- Avoid putting sensitive information into metadata.
- Log access and restrict permissions for users who only need read-only observation.

If adding Spring Security to Eureka Server, verify protection rules for Eureka endpoints. Improper CSRF configuration can block the POST/PUT/DELETE requests that Eureka Clients need to register, renew, or cancel. API protection must allow legitimate clients to perform required operations.

## 12. Workflow for Investigating a Missing Instance

Suppose payment-service just started, yet does not appear on the Eureka Dashboard. You can check in sequence:

1. Call GET /eureka/apps to confirm the overall registry is responding.
2. Call GET /eureka/apps/PAYMENT-SERVICE to locate the right application.
3. If the application is present, inspect each instance ID, host, IP, and port.
4. Read status, overriddenStatus, and metadata to see how the instance is being advertised.
5. Read leaseInfo and lastRenewalTimestamp if present to see whether heartbeats were renewed recently.
6. Check application logs for register/renew errors or Eureka Server connection errors.
7. If running a cluster, query the same application on another peer and compare registries.
8. Check Actuator health, health check configuration, self-preservation, and eviction when a stopped instance still remains in the registry.

| Observed result | Next investigation step |
|---|---|
| GET /eureka/apps does not respond | Check Eureka Server, port, context path, DNS, and network |
| Registry responds, but application is absent | Check Eureka Client starter, service URL, and registration logs |
| Application exists, but one instance is missing | Check instance ID, register requests, and the instance's logs |
| Instance has status DOWN or OUT_OF_SERVICE | Check health state, status overrides, and maintenance actions |
| Instance is UP, but service calls fail | Check Actuator, host/port, network, and business endpoints |
| Two peers display different data | Check replication, peer connectivity, and update latency |
| Stale instance persists for a long time | Check heartbeats, lease, eviction interval, and self-preservation |

## 13. Summary

The Eureka REST API lets you observe the registry through GET endpoints such as /eureka/apps, /eureka/apps/{APP_NAME}, and /eureka/apps/{APP_NAME}/{INSTANCE_ID}. Responses provide application, instance, status, metadata, and lease information to support investigating service registration and status.

When reading data, distinguish the status published by the registry from the actual health of the application, and understand that lease expiration, eviction, replication, and cache updates are steps that involve latency. The Dashboard provides quick visual inspection, the REST API provides structured data, and Actuator reports the state inside the process. Combining all three with logs and metrics helps pinpoint why an instance is missing, stale, or unable to serve requests.
