# Designing Consistent Service, Instance, Environment, and Version Labels

> Scope: operating Spring Boot Actuator 3.3.x with Micrometer; Prometheus is used to illustrate the metrics collection process. Java examples use APIs available in Java 21. The value conventions in this article are a concrete design for reference, not mandatory label names for every system.

## 1. Four Questions That Must Be Answered from an Operational Signal

When error rates rise, operators need to determine: which service is having trouble, which running instance emitted the signal, which environment the data belongs to, and which software version is running. A measurement with a value but missing identity can cause you to investigate the wrong release or mix test metrics into production metrics.

Four concepts to keep distinct:

| Concept | Question answered | Example |
| --- | --- | --- |
| service | Which functional component? | orders-api |
| instance | Which specific running copy or scrape target? | runtime-a or 10.0.12.21:8080, depending on the model |
| environment | Which environment is it running in? | production |
| version | Which software release is running? | 2.4.1 |

Suppose two running instances both serve orders. They need the same service name, may have the same environment and version, yet must be distinguishable when tracing errors per running instance. Conversely, during a rolling deployment, two versions may coexist under one service.

Do not bundle everything into a name like orders-api-production-v2-pod-a. Doing so forces every query to parse a string and makes version changes look like new services appearing. Separating dimensions helps choose the right aggregation level.

## 2. Defining the Label Contract Before Writing Configuration

A label contract is an agreement on meaning, key names, value domains, where values are supplied, and when they are allowed to change. Agreeing on key names alone is not enough: production, prod, and Production still produce three different values if sent as-is.

A reference contract:

| Dimension | Value convention | Source | Change rule |
| --- | --- | --- | --- |
| service | Stable functional name, lowercase, e.g. orders-api | Application catalog/deployment configuration | Does not change when scaling instances or releasing new versions |
| environment | One of development, test, staging, production | Deployment environment configuration | Fixed for the lifetime of the process |
| version | Release identifier, e.g. 2.4.1 or immutable build ID | Artifact build and release pipeline | Changes when the artifact is replaced; rolling back to an old release must restore the old version |
| instance | Distinguishes the exact unit to investigate | Runtime platform or collection system | Stable within the defined unit/lifecycle, not regenerated per request |

If multiple systems can share the same service name, add a namespace dimension such as service_namespace or map to service.namespace when using OpenTelemetry. Agree on the uniqueness scope of the name, rather than assuming short names are globally unique across the organization.

For version, latest is only a mutable reference label. It does not answer which exact codebase is running. Tie version to the actual artifact and record its relationship to the commit ID or artifact hash in the release record.

For instance, define whether it means a **scrape target** or a **single process lifetime**. A host:port address can be reused after a process restarts; it does not by itself prove two samples belong to the same JVM run.

## 3. Each Key Has One Owner Supplying Its Value

In the illustrative design throughout this article:

- The application attaches service, environment, and version to the metrics it emits.
- Prometheus supplies job and instance for the targets it scrapes.
- The runtime platform may additionally supply INSTANCE_ID for logs or traces when per-process identity is needed.

Do not re-add service/environment/version to Prometheus target configuration in this same model. If the organization wants the collection platform to own those keys, transfer ownership to the platform and remove the corresponding declarations from the application.

Having two places write the same key easily creates conflicts: the application says environment=staging while the scraper attaches environment=production. One of them being renamed or dropped does not mean the data is now right.

Values used in production should be validated early: mandatory, not whitespace-only, environment belongs to the accepted list, and version matches the artifact about to run. Do not use unknown as a default value just to make a deployment appear successful.

## 4. Applying Common Tags in Spring Boot Actuator

Common tags in Micrometer are applied at the registry level. In Spring Boot 3.3, management.metrics.tags is the way to configure these tags. If Java handling is needed, MeterRegistryCustomizer is the extension point applied before meters are registered. [Spring Boot common tags](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.customizing.common-tags), [MeterRegistryCustomizer API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/metrics/MeterRegistryCustomizer.html).

The following application.yml snippet is for an application that already has Actuator and the Prometheus registry:

```yaml
spring:
  application:
    name: orders-api

management:
  metrics:
    tags:
      service: "${spring.application.name}"
      environment: "${DEPLOYMENT_ENVIRONMENT}"
      version: "${APP_VERSION}"
  endpoints:
    web:
      exposure:
        include: health,prometheus,metrics
```

This is configuration merged into a Spring Boot application, not a complete standalone project. The corresponding dependencies, under Spring Boot's version management, include:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
implementation 'org.springframework.boot:spring-boot-starter-actuator'
runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
```

Values supplied by the deployment environment can be prepared as follows in PowerShell:

```powershell
$env:DEPLOYMENT_ENVIRONMENT = 'production'
$env:APP_VERSION = '2.4.1'
```

The configuration references spring.application.name as the source for service. Do not infer that merely declaring the application name gives every registry a service label matching this contract. Similarly, an active profile is not necessarily the environment name: an application can simultaneously activate the production and postgres profiles.

Environment variables and other configuration sources have an order of precedence. When the actual value differs from the YAML file, check which override source is in effect, especially deployment configuration and command-line arguments. [Spring Boot 3.3 external configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### Verifying at the Application

In a lab environment where accessing these endpoints is permitted:

```powershell
curl.exe -fsS 'http://localhost:8080/actuator/metrics/jvm.memory.used'
curl.exe -fsS 'http://localhost:8080/actuator/prometheus'
```

At the metrics endpoint, inspect availableTags to confirm service/environment/version. In the Prometheus data, find a sample belonging to a JVM meter and check the application labels. Numeric values and label order may vary; do not use the entire response as a fixed expected output.

The metrics endpoint serves diagnostics; the data there is not yet the time series after Prometheus attaches target labels. Enabling an endpoint and allowing HTTP access are also separate parts of configuration. Only include necessary endpoints on controlled operational access paths. [Actuator endpoints](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

### When Java Configuration Is Needed

If tags need to be computed or validated in code, use a callback before meters are registered. Do not wait until the application has been running for a while to change common tags: existing meters must not be assumed to transform automatically in bulk under the new configuration. Choose one intentional way to supply tags rather than declaring the same key in both YAML and multiple customizers. [Micrometer common tags timing](https://docs.micrometer.io/micrometer/reference/1.13/concepts/naming.html#_common_tags).

## 5. Understanding instance Properly When Using Prometheus

Prometheus by default attaches job from the scrape configuration and instance from the target's host:port address. Therefore, an application does not need to export an instance label itself just for Prometheus to distinguish two different targets. [Jobs and instances](https://prometheus.io/docs/concepts/jobs_instances/).

The example below uses two illustrative addresses. Replace them with addresses that the machine running Prometheus can actually reach:

```yaml
scrape_configs:
  - job_name: orders-api-production
    metrics_path: /actuator/prometheus
    static_configs:
      - targets:
          - '10.0.12.21:8080'
          - '10.0.12.22:8080'
```

Assume both applications are running version 2.4.1. After scraping, the series can share service=orders-api, environment=production, version=2.4.1 while differing in instance. This is a distinction added on the Prometheus side.

If calling /actuator/prometheus directly does not show instance in the response, that matches this design: Prometheus has not yet performed the step of attaching target labels to the data you are viewing.

### Avoiding Two Meanings for the Same instance Key

If the application also exports instance=runtime-a itself, this key conflicts with the target label. With honor_labels=false, Prometheus's default, the conflicting label in the scraped data is renamed to exported_instance and the Prometheus-side label is kept under instance. With honor_labels=true, the label from the scraped data is kept and the conflicting target label is ignored. [honor_labels mechanism](https://prometheus.io/docs/prometheus/latest/configuration/configuration/#scrape_config).

Do not change honor_labels just to mask an unclear label contract. If you need to additionally distinguish each process run, consider an app_instance key and define its source, uniqueness scope, and lifecycle. An ID generated once at startup is completely different from a UUID regenerated per request.

In a push-metrics model without Prometheus's instance-labeling step, design the identifier at the registry, resource attributes, or corresponding collector. Do not copy the decision to omit instance from this example verbatim to every collection system.

### The Labels of up Do Not Automatically Inherit Labels from Application Data

up is generated by Prometheus for the scrape target. The service/environment/version labels inside application data do not automatically transfer into labels on up. With the configuration above, targets can be checked with:

```promql
up{job="orders-api-production"}
```

If up needs to be filtered by service or environment, the platform must supply the corresponding target labels. In that case, adjust ownership and conflict rules for application data rather than duplicating the same key in two places without verification.

## 6. Keeping Useful Identity Without Uncontrolled Series Growth

In time-series metrics, each distinct combination of labels creates a separate series. The number of distinct values for a label is commonly called cardinality. A tag attached commonly accompanies many meters, so its cost does not stay limited to a single business metric. [Prometheus label rules](https://prometheus.io/docs/practices/naming/#labels).

A calculation example to understand scale: suppose one running instance already emits 2,000 series after accounting for existing labels. If 20 instances are deployed and distinguished individually, the total could be around 40,000 corresponding series, not counting other platform signals.

Do not multiply every dimension mechanically. In this example, each running instance has one version and one environment at a time; the dimensions are correlated. Estimate according to combinations that actually occur.

Choices to avoid:

- Putting requestId, traceId, userId, email, or full URLs with parameters into common tags.
- Using the current time as version for every metric recording.
- Changing instance on every scrape or every request.
- Emitting the same meaning under multiple keys such as env, environment, and deployment_env without a clear migration reason.

The instance and version labels remain useful even though they create additional series. The goal is to keep growth bounded by instance count and release count, while monitoring newly created series over time. When version changes, historical data from the old release still remains within the retention period.

If an unexpectedly growing business label domain needs to be blocked, Micrometer has MeterFilter to filter or transform meter identifiers. This is an additional safeguard; it does not replace fixing the faulty label source. [Meter filters](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

## 7. Using the Same Meaning Across Metrics, Logs, and Traces

Consistency does not require every protocol to use the same key spelling. What must be preserved is that meanings and values share the same canonical source. Reference mapping table:

| Meaning | Metrics label in this article | Log field defined by project team | OpenTelemetry resource attribute |
| --- | --- | --- | --- |
| Service | service | service | service.name |
| Version | version | version | service.version |
| Environment | environment | environment | deployment.environment.name |
| Instance | instance supplied by Prometheus; app_instance if a separate need exists | instance | service.instance.id |

service.name remains stable across running instances of the same service; service.version describes the version. service.instance.id must distinguish instances within the scope of service.namespace and service.name. The scrape address does not necessarily equal the service.instance.id value, so if they need to be correlated, a mapping must be stored. [OpenTelemetry service conventions](https://opentelemetry.io/docs/specs/semconv/resource/service/).

deployment.environment.name describes the deployment environment tier, such as production or staging. This is a separate dimension; do not stuff it into the service name just to make environment filtering easier. [Deployment environment conventions](https://opentelemetry.io/docs/specs/semconv/resource/deployment-environment/).

In the OpenTelemetry integration path auto-configured by Spring Boot 3.3, Resource attributes can be configured via management.opentelemetry.resource-attributes. The snippet below illustrates the mapping; by itself it does not set up full tracing or an exporter:

```yaml
management:
  opentelemetry:
    resource-attributes:
      service.name: "${spring.application.name}"
      service.version: "${APP_VERSION}"
      service.instance.id: "${INSTANCE_ID}"
      deployment.environment.name: "${DEPLOYMENT_ENVIRONMENT}"
```

If you have declared a Resource yourself or used an agent/starter via another integration path, check the configuration mechanism of that exact path. management.metrics.tags, management.observations.key-values, and Resource attributes have different scopes; one setting does not automatically configure all the others. Adding fields to logs also requires corresponding logging configuration. [Observability and Resource in Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 8. Preserving Comparability During Rolling Deployments

During a version rollout, a valid state might look like:

| service | environment | Prometheus instance | version |
| --- | --- | --- | --- |
| orders-api | production | 10.0.12.21:8080 | 2.4.1 |
| orders-api | production | 10.0.12.22:8080 | 2.5.0 |

To view total heap memory by version:

```promql
sum by (service, environment, version) (
  jvm_memory_used_bytes{
    service="orders-api",
    environment="production",
    area="heap"
  }
)
```

To view request rate by version when the application already has corresponding HTTP meter data:

```promql
sum by (service, environment, version) (
  rate(http_server_requests_seconds_count{
    service="orders-api",
    environment="production"
  }[5m])
)
```

In the rate query, compute rate on each series first before summing so counter-reset handling still has full information. [Prometheus rate function](https://prometheus.io/docs/prometheus/latest/querying/functions/#rate).

These queries intentionally omit instance from the aggregation result while keeping version. When you need to locate a failing instance, add instance to the grouping or filter. When you need overall service health, you can omit version from the grouping.

The 5-minute window may still contain data from the old release after it has stopped running. A line on the rate chart does not by itself prove that instance still exists at the present moment.

Keep the environment definition and service name unchanged throughout the deployment. When rolling back to artifact 2.4.1, version must reflect 2.4.1; do not change it to the timestamp of the rollback operation.

## 9. Java Example: Validating the Value Contract

The program below only illustrates the identity contract in plain Java. It does not attach tags to Spring Boot itself. The metricTags method intentionally returns the three application labels in the chosen Prometheus model; instance is still stored to illustrate two different running copies.

File IdentityLabelsDemo.java:

```java
import java.util.Map;
import java.util.Set;

public class IdentityLabelsDemo {
    record Identity(String service, String environment,
                    String version, String instance) {
        Identity {
            service = required("service", service);
            environment = required("environment", environment);
            version = required("version", version);
            instance = required("instance", instance);

            if (!service.matches("[a-z][a-z0-9]*(?:-[a-z0-9]+)*")) {
                throw new IllegalArgumentException("Invalid service");
            }
            if (!Set.of("development", "test", "staging", "production")
                    .contains(environment)) {
                throw new IllegalArgumentException("Invalid environment");
            }
            if (Set.of("latest", "unknown", "unspecified").contains(version)) {
                throw new IllegalArgumentException("Ambiguous version");
            }
        }

        Map<String, String> metricTags() {
            return Map.of(
                "service", service,
                "environment", environment,
                "version", version
            );
        }

        private static String required(String key, String value) {
            if (value == null || value.isBlank()
                    || !value.equals(value.strip())) {
                throw new IllegalArgumentException("Invalid " + key);
            }
            return value;
        }
    }

    public static void main(String[] args) {
        Identity first = new Identity(
            "orders-api", "production", "2.4.1", "runtime-a"
        );
        Identity second = new Identity(
            "orders-api", "production", "2.4.1", "runtime-b"
        );

        System.out.println("service=" + first.service());
        System.out.println("environment=" + first.environment());
        System.out.println("version=" + first.version());
        System.out.println("sameMetricTags="
            + first.metricTags().equals(second.metricTags()));
        System.out.println("sameInstance="
            + first.instance().equals(second.instance()));

        try {
            new Identity("orders-api", "Prod", "2.4.1", "runtime-c");
            throw new AssertionError("Invalid environment was accepted");
        }
        catch (IllegalArgumentException expected) {
            System.out.println("invalidEnvironment=rejected");
        }
    }
}
```

Compile and run with JDK 21 or later:

```powershell
javac --release 21 -encoding UTF-8 IdentityLabelsDemo.java
java IdentityLabelsDemo
```

Stdout:

```text
service=orders-api
environment=production
version=2.4.1
sameMetricTags=true
sameInstance=false
invalidEnvironment=rejected
```

sameMetricTags=true indicates both running instances share the three dimensions supplied by the application. They are still distinguished after Prometheus attaches different target labels. sameInstance=false indicates the separate instance IDs in the example also differ.

The value Prod is rejected because this contract requires production. This is an illustrative data validation decision, not Spring normalizing Prod automatically. Real verification also requires matching version against the artifact and verifying instance uniqueness on the deployment platform; a local Java function is not enough to prove those.

## 10. Verifying from Configuration Sources to the Storage System

A full verification should pass through these layers:

1. **Release record:** Do version and the artifact ID match the release about to run?
2. **Effective configuration:** Are service/environment/version accurate, missing, or overridden?
3. **At the application:** Do diagnostic endpoints and exported data carry the agreed application labels?
4. **At the collector:** Does the target have the right job/instance, and do unexpected exported_service, exported_environment, or exported_instance labels appear?
5. **In queries:** Can two environments, two instances, and two versions be cleanly separated as intended?
6. **During rollouts:** Are old and new release data identified accurately without changing the service name?

Also test cases for missing metadata, misspelled environment, simultaneous rollout of two versions, and rollback to an old version. Do not only confirm one working configuration on a local machine.

Signs that the contract needs review are: production mixed with prod, every running instance having the same instance due to hardcoding, version always being latest, or labels changing per request. When detected, fix at the source and evaluate impact on dashboards/alerts; historical data is not automatically renamed under the new configuration.

## 11. Self-Practice

1. Given two running copies with the same service and version but in staging and production, point out which label must differ and write a filter so the two environments are not mixed.
2. Given an application that exports instance itself while Prometheus uses honor_labels=false, predict the two keys that will appear after scraping and explain the origin of each key.
3. Deploy two versions simultaneously. Write one query aggregating by service and one separating by version; state the difference in the operational questions they answer.
4. Try passing version=latest into the Java example to observe the rejection, then add a check aligned with your actual release policy. Explain why format validation still does not prove the artifact is right.
5. Design a mapping between Prometheus's instance and service.instance.id in traces if an investigation requires jumping from metrics of a target to traces of a specific run.

The design achieves its goal when every signal answers the four identity questions, value sources do not compete for ownership, and scaling instances or changing versions preserves comparability.
