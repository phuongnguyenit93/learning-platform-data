# Verifying Default Changes for Identity, Retries, and Listeners

When upgrading Spring Boot, Spring Cloud OCI, or the OCI Java SDK, an application's behavior can change even if configuration files remain unchanged. Any undeclared property takes its default value from the library running at runtime. If a new version adds authentication providers, updates retry policies, or swaps Spring Messaging dependencies, actual behavior can diverge from the old environment.

An upgrade must verify three independent behavioral groups:

- **Identity:** is the application authenticating via an API key profile, Instance Principal, Resource Principal, Session Token, or Workload Identity?
- **Retry:** which layer is retrying, which operations have default retries enabled, and what are the attempt counts and backoff values?
- **Listener:** does the consumer auto-start, how many consumers run, how long does the listener wait for messages, and how are error handling and transactions/acknowledgements configured?

You cannot conclude that defaults changed solely because a version number increased. You must compare release notes, version-specific documentation, dependency graphs, and observed runtime behavior. This lesson builds a verification workflow to detect real changes, identify preserved defaults, and lock critical values before rollout.

## 1. Learning Objectives

After this lesson, learners will be able to:

1. Explain why an upgrade can change behavior even when application configuration is unchanged.
2. Distinguish defaults across Spring Cloud OCI, OCI Java SDK, Spring Cloud Stream, and Spring JMS.
3. Compare authentication defaults between Spring Cloud Oracle 1.x and 2.x.
4. Verify the actual authentication type, profile, and region in effect.
5. Distinguish retries at the SDK operation, message listener, and broker redelivery layers.
6. Read OCI Java SDK retry policies on a per-operation basis.
7. Inspect retry attempt counts, retry conditions, backoff, and precedence.
8. Verify listener auto-startup, concurrency, timeouts, and transaction modes.
9. Distinguish OCI Queue/Streaming API consumers from Spring Cloud Stream listeners.
10. Identify which defaults are documented and which values must be verified at runtime.
11. Produce explicit configuration for production after an upgrade.
12. Design regression tests for identity, retries, and listeners.
13. Roll out and roll back safely when runtime behavior changes.
14. Save before/after evidence so future upgrades are repeatable.

## 2. Why Must Defaults Be Checked During an Upgrade?

Spring Boot and Spring Cloud rely on auto-configuration. When a property is not declared, the framework picks the default from the library or module present on the classpath.

For example, a service might omit declaring:

- spring.cloud.oci.config.type
- spring.cloud.oci.config.profile
- spring.cloud.stream.bindings.orders-in-0.consumer.concurrency
- spring.cloud.stream.bindings.orders-in-0.consumer.max-attempts
- spring.jms.listener.auto-startup
- spring.jms.listener.session.transacted

When upgrading versions, newer dependencies may:

- Add an authentication mode.
- Update the OCI SDK and retry behavior.
- Change the Spring Cloud Stream or Spring Framework version.
- Update auto-configuration conditions.
- Change how listener containers are created.
- Change a property default or how a property is bound.
- Keep the same default while changing the underlying implementation.

~~~mermaid
flowchart TD
    A[Upgrade Spring Boot / Spring Cloud / OCI SDK] --> B[Did resolved dependency graph change?]
    B --> C[Did auto-configuration and defaults change?]
    C --> D[Identity / Retry / Listener behavior]
    D --> E[Observe runtime]
    E --> F{Differs from baseline?}
    F -->|No| G[Record default preserved]
    F -->|Yes| H[Assess impact and configure explicitly]
    H --> I[Regression tests]
    I --> J[Canary / rollout]
~~~

A release note that omits mentioning authentication or listeners is not absolute proof that nothing changed. It only indicates the project did not call out that change in the release notes section. You must verify the dependency graph, configuration metadata, and runtime behavior.

## 3. Identify the Exact Versions Being Upgraded

Before comparing defaults, record the version of each layer:

| Layer | Examples to record |
| --- | --- |
| Java runtime | Java 17, 21, or version in use |
| Spring Boot | Parent/plugin and resolved Boot artifacts |
| Spring Framework | spring-core, spring-context, spring-jms |
| Spring Cloud release train | BOM if used by the application |
| Spring Cloud OCI | spring-cloud-oci-starter and service modules |
| OCI Java SDK | Resolved OCI SDK modules/versions |
| Spring Cloud Stream | Core and binder versions |
| Oracle TxEventQ binder | Version independent from the OCI starter |
| Spring JMS/AQ-JMS | Spring Integration JMS and AQ API |

Spring Cloud OCI 2.0.4 is an independent release line. Release notes for 2.0.4 state it upgrades Spring Boot to 4.1.1 and refreshes third-party dependencies. Release notes for 2.0.0 state support for Spring Boot 4 and Spring Framework 7. These changes require verifying the dependency graph and integration behavior even without a separate release note line mentioning retries or listeners.

Do not assume the OCI SDK version solely from the starter name. Read the dependency tree to see the exact version pulled into runtime.

### 3.1. Maven

~~~bash
mvn help:effective-pom
mvn dependency:tree -Dincludes=org.springframework.boot,org.springframework,org.springframework.cloud,com.oracle.cloud.spring,com.oracle.oci.sdk
~~~

Save outputs for both the old and new versions. Focus on:

- Spring Boot parent/BOM.
- Spring Framework modules.
- Spring Cloud Stream.
- spring-cloud-oci-core and service modules.
- OCI Java SDK common and service-specific modules.
- Spring Integration JMS.
- Oracle AQ-JMS API if using TxEventQ over JMS.

### 3.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-oci-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency oci-java-sdk-common --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-stream --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-jms --configuration runtimeClasspath
~~~

Record dependency constraints, forced versions, and platforms/BOMs affecting resolution.

### 3.3. Build a before/after comparison table

| Item | Before upgrade | After upgrade | Evidence |
| --- | --- | --- | --- |
| Spring Boot | Locked version | Target version | Effective POM/Gradle graph |
| OCI starter | Old version | New version | Dependency tree |
| OCI SDK | Old version | New version | Resolved runtime graph |
| Auth type | Effective value | Effective value | Property + audit principal |
| Retry | Effective policy | Effective policy | SDK Javadoc + tests |
| Listener | Auto-start/concurrency | Auto-start/concurrency | Runtime config + metrics |
| Error handling | Retry/DLQ/transaction | Retry/DLQ/transaction | Integration tests |

Do not mark "same" by inspecting only application.yaml. You must verify bound values and actual behavior.

## 4. Verifying OCI Identity Defaults

### 4.1. FILE remains the Spring Cloud OCI default

Both Spring Cloud Oracle 1.0.0 documentation and 2.0.4 documentation state configuration-file authentication as the default. Properties:

| Property | Current default | Meaning |
| --- | --- | --- |
| spring.cloud.oci.config.type | FILE | Authentication type |
| spring.cloud.oci.config.profile | DEFAULT | Profile inside the OCI config file |
| spring.cloud.oci.config.file | No fixed default value | Path to config file |
| spring.cloud.oci.config.region | No fixed default value | Region in auth configuration |
| spring.cloud.oci.region.static | No fixed default value | Region used for API calls |
| spring.cloud.oci.compartment.static | No fixed default value | Default compartment |

Important observations when comparing 1.x and 2.x:

- The default authentication type FILE is preserved in both 1.0.0 and 2.0.4 documentation.
- Profile DEFAULT remains the default profile.
- Current auth modes include FILE, SIMPLE, INSTANCE_PRINCIPAL, RESOURCE_PRINCIPAL, SESSION_TOKEN, and WORKLOAD_IDENTITY.
- 1.0.0 documentation lists fewer options; additional auth modes in newer release lines are not automatically selected if properties do not change.

Therefore, do not assume upgrading to 2.x automatically switches the application to Instance Principal or Workload Identity. If spring.cloud.oci.config.type is not configured, Spring Cloud OCI still chooses FILE per published defaults.

### 4.2. The FILE default can fail when switching runtimes

An application running locally with ~/.oci/config works with FILE. When deploying the same image to Compute or OKE, that file may not exist. The application may:

- Fail to start because the config file cannot be found.
- Read the wrong default profile.
- Use an API key belonging to an inappropriate environment user.
- Run but receive 403 due to unsuitable user policies.

Production should explicitly configure identity per runtime.

Local:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: FILE
        profile: DEFAULT
~~~

OCI Compute:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
~~~

OCI Functions:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: RESOURCE_PRINCIPAL
~~~

OKE with federation configured:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: WORKLOAD_IDENTITY
~~~

These are environment-specific configurations. Do not enable multiple auth profiles simultaneously in a way that leaves the chosen identity ambiguous.

### 4.3. Verify region precedence

spring.cloud.oci.region.static takes higher precedence than spring.cloud.oci.config.region and the region inside the OCI auth configuration file.

During an upgrade, a new environment variable or profile can introduce a static region that was absent before. Clients can switch to a different endpoint even when the OCI profile remains unchanged.

Check:

1. spring.cloud.oci.region.static.
2. spring.cloud.oci.config.region.
3. Region in the OCI config file.
4. Region of the actual resource.
5. Region recorded in audit/requests.

Do not verify only that authentication succeeds; verify that requests go to the right region.

### 4.4. Verify the actual principal

Configuration tells you which provider the application intends to choose. OCI Audit tells you which principal actually called the API.

Check:

- Local: expected OCI user OCID.
- Compute: Instance Principal of the intended instance/dynamic group.
- Functions: Resource Principal of the function.
- OKE: Workload Identity bound to the cluster, namespace, and service account.
- IAM policy: principal has the right permissions and scope.

If the audit principal does not match the expected configuration, halt rollout and investigate profile/environment overrides before proceeding.

### 4.5. Configure explicitly to avoid relying on defaults

Once verified, set critical properties explicitly:

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: OCI_REGION
      compartment:
        static: OCI_COMPARTMENT_OCID
~~~

In the example above, uppercase values are placeholders to be replaced with deployment values. Do not commit real OCIDs or credentials to source if policy requires externalizing configuration.

## 5. Distinguishing Three Layers of Retries

An error can be retried by multiple layers:

1. OCI Java SDK retries requests to the OCI service.
2. Spring Cloud Stream retries when a function/consumer listener throws an exception.
3. The broker or messaging system redelivers a message after listener failure, session rollback, or visibility/ack deadline expiration.

These three layers have different purposes and counters. Without distinguishing them, a single message can be processed more times than expected.

~~~mermaid
flowchart TD
    A[Message arrives at consumer] --> B[Listener processes]
    B --> C{Calls OCI API?}
    C -->|Yes| D[OCI SDK retries operation]
    C -->|No| E[Business handler]
    D --> E
    E --> F{Handler succeeded?}
    F -->|Yes| G[Commit / ack / checkpoint]
    F -->|No| H[Spring listener retry]
    H --> I{Attempts remaining?}
    I -->|Yes| B
    I -->|No| J[Broker redelivery / DLQ / error flow]
~~~

The diagram is a general model. Exact ordering depends on the binder, listener container, and transaction mode. Not every service supports redelivery or DLQs in the same way.

### 5.1. OCI SDK retries

The OCI Java SDK has retry configuration at the SDK/global, client, and request levels. SDK documentation states default retries have been supported since SDK 2.10.0, but this does not mean every operation retries automatically. Each service operation must be checked in Javadoc to confirm whether default retry is enabled for that operation.

Error groups retried by default in the SDK may include:

- HTTP 409 with service code IncorrectState.
- HTTP 429 throttling.
- HTTP 500, 502, 503, and 504.
- Connection/read timeouts.
- Request connection errors.
- Request exceptions.
- Circuit breaker exceptions.

Do not retry all 4xx errors. Authentication 401, authorization 403, and validation 400 typically require fixing credentials, policies, or requests rather than retrying repeatedly.

### 5.2. OCI Java SDK default strategy

OCI Java SDK documentation describes the default retry strategy as follows:

| Component | Published default |
| --- | --- |
| Termination strategy | MaxAttemptsTerminationStrategy with value 8 |
| Delay strategy | Exponential backoff |
| Jitter | Random within 0–1000 ms |
| Maximum delay between calls | 30 seconds |
| Retryable errors | Per DefaultRetryCondition and per-operation documentation |
| Async client | No default retry support per SDK documentation |

8 is the max-attempts value of the termination strategy. When upgrading the SDK, check the exact version's Javadoc and how the implementation counts attempts for the operation in use; do not assume 8 retries plus the initial call unless that version's documentation confirms it.

### 5.3. Retries are enabled per operation

Each service operation may state one of the following:

- The operation uses RetryConfiguration.SDK_DEFAULT_RETRY_CONFIGURATION if the request does not provide a retry strategy.
- The operation does not retry by default; callers can enable retries using the SDK default.
- The operation has custom retry behavior.

Consequently, two methods on the same client can behave differently. When upgrading the SDK, check critical operations in the Javadoc of the resolved version instead of reading only general retry configuration.

### 5.4. Retry precedence

The OCI SDK supports configuration at multiple levels. Precedence order:

1. Request-level retry configuration.
2. Client-level retry configuration.
3. Global/default retry configuration and environment overrides.

Request-level configuration can override the client's policy for that request. Client-level configuration can override the global/default policy for that client.

The environment variable OCI_SDK_DEFAULT_RETRY_ENABLED=false disables default retries globally. If code sets an explicit retry configuration on a client or request, that explicit configuration can override the environment default.

### 5.5. Async clients are a special case

Current OCI Java SDK documentation explicitly states that default retries are not supported for asynchronous clients. If an upgrade switches an integration from a synchronous to an asynchronous client, do not assume retry behavior remains the same.

For async clients, you must:

- Identify the retry owner.
- Classify transient errors.
- Set a total retry budget.
- Verify whether request bodies can be replayed.
- Implement idempotency keys or reconciliation.
- Avoid unbounded retries inside callbacks/executors.

## 6. Spring Cloud Stream Consumer Retries

Spring Cloud Stream has its own retry policy for input bindings. Current defaults in the binding properties reference:

| Property | Default | Meaning |
| --- | --- | --- |
| autoStartup | true | Consumer binding starts automatically |
| concurrency | 1 | Number of concurrent consumers |
| maxAttempts | 3 | Total processing attempts, including the initial attempt |
| backOffInitialInterval | 1000 ms | Initial backoff |
| backOffMaxInterval | 10000 ms | Maximum backoff |
| backOffMultiplier | 2.0 | Backoff multiplier |
| defaultRetryable | true | Undeclared exceptions are retried by default |
| retryableExceptions | Empty | Map of exception classes to true/false |

With maxAttempts=3, the listener gets up to three processing attempts within Spring Cloud Stream's retry cycle: the initial attempt plus two retries. This is a listener retry, not an OCI SDK retry.

These numbers belong to Spring Cloud Stream ConsumerProperties. The 5.1.0 reference page publishes these values; if your application's dependency graph resolves a different version, consult the binding properties reference matching that version.

### 6.1. Listener retries differ from broker redelivery

If a listener throws an exception:

1. Spring Cloud Stream may re-invoke the listener according to maxAttempts.
2. If the retry cycle fails, the binder/error handler decides the next step.
3. Depending on the binder, the message may be rejected, requeued, redelivered, or sent to a DLQ.
4. If a transaction rolls back, the broker may redeliver the message per broker semantics.

Do not add maxAttempts=3 to a fixed broker redelivery count without knowing binder behavior. Record both listener attempts and broker delivery counts.

### 6.2. Example locking retries per binding

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        invoiceConsumer-in-0:
          destination: invoice-events
          group: invoice-workers
          consumer:
            auto-startup: true
            concurrency: 1
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
            default-retryable: true
~~~

The values above restate the defaults to make configuration explicit. If production needs different values, adjust based on latency budgets and workload fault tolerance.

### 6.3. Retry only recoverable errors

Classification examples:

| Exception/condition | Retry? | Reason |
| --- | --- | --- |
| Temporary network timeout | Yes, bounded | Potentially recoverable |
| HTTP 429 | Yes, with backoff | Throttling |
| HTTP 503 | Yes, bounded | Service temporarily unavailable |
| Invalid payload/schema | No | Retrying cannot fix malformed data |
| HTTP 401/403 | No | Requires fixing identity/policy |
| Business rule violation | Usually no | Not a transient error |
| Database deadlock | Maybe | Depends on transaction/idempotency |
| Duplicate business event | Do not re-apply side effects | Deduplicate by event ID |

Specific exceptions can be configured via retryable-exceptions. Before leaving default retries enabled for all exceptions, check whether the listener throws non-recoverable business exceptions.

## 7. Verifying Listener Defaults per Programming Model

There is no single shared listener default across all OCI messaging integrations. You must identify which API the application uses.

| Integration | Consumer model | Listener defaults to verify |
| --- | --- | --- |
| OCI Queue starter | Queue service bean and Queue API | No default Spring @QueueListener in starter docs |
| OCI Streaming starter | Streaming service bean and getMessages/cursor API | No default Spring listener/container auto-start in starter docs |
| Oracle TxEventQ Stream Binder | Spring Cloud Stream function binding | autoStartup, concurrency, retry properties of Spring Cloud Stream |
| Oracle TxEventQ via Spring JMS | @JmsListener and listener container | Spring Boot/JMS container defaults |

This distinction matters during upgrades. If the application uses the OCI Queue bean to poll manually, you cannot use Spring Cloud Stream's default concurrency to infer the number of Queue consumers. If the application uses the TxEventQ binder, you cannot use the Queue starter API to infer listener lifecycle.

### 7.1. OCI Queue and OCI Streaming

The Spring Cloud OCI Queue starter auto-configures a Queue bean to work with queues/messages. The Streaming starter auto-configures a Streaming bean to create streams, publish, and fetch records.

The starter documentation describes API beans and operations; it does not publish a Spring listener annotation or listener container with auto-startup/concurrency defaults.

If the application implements its own polling loop:

- Determine the number of worker threads created by the application.
- Determine the poll interval and request timeout.
- Determine message visibility/lease/settlement behavior per the Queue API.
- Determine cursors and checkpoints per the Streaming API.
- Ensure shutdown stops the polling loop.
- Bound the number of in-flight messages.
- Verify idempotency across process restarts.

These values belong to the application implementation and OCI service APIs, not Spring Cloud OCI starter listener defaults.

### 7.2. TxEventQ with Spring Cloud Stream binder

The TxEventQ binder supports functional Consumer, Function, and Supplier beans. A consumer binding can be configured as follows:

~~~yaml
spring:
  cloud:
    function:
      definition: invoiceConsumer
    stream:
      bindings:
        invoiceConsumer-in-0:
          destination: INVOICE_EVENTS
          group: INVOICE_WORKERS
          consumer:
            concurrency: 1
~~~

Oracle documentation includes an example with concurrency: 2; that is a sample configuration value, not the default. The general Spring Cloud Stream consumer default is 1.

Binder-specific properties:

- spring.cloud.stream.txeventq.bindings.<bindingName>.consumer.timeout
- spring.cloud.stream.txeventq.bindings.<bindingName>.consumer.batchSize

The binder timeout defaults to 1000 ms. This is the maximum duration the consumer thread waits during each consume operation, not the business handler timeout, message retention, or listener shutdown timeout.

batchSize defines the maximum number of messages in a single callback when batch mode is enabled. This property is ignored if batch-mode=false.

### 7.3. TxEventQ with Spring JMS

Oracle TxEventQ can also be used via Spring JMS:

~~~java
@Component
public class InvoiceJmsListener {

    @JmsListener(destination = "INVOICE_QUEUE")
    public void receive(String payload) {
        // Validate and process message
    }
}
~~~

Oracle documentation confirms @JmsListener creates a DefaultMessageListenerContainer by default unless another factory is provided. With Spring Boot auto-configuration, values worth checking include:

| Property | Published Boot/JMS default |
| --- | --- |
| spring.jms.listener.auto-startup | true |
| spring.jms.listener.receive-timeout | 1s |
| spring.jms.listener.session.acknowledge-mode | auto |
| spring.jms.listener.min-concurrency | Not set by default; underlying container starts with 1 consumer |
| spring.jms.listener.max-concurrency | Not set by default |
| spring.jms.listener.session.transacted | true if no JTA transaction manager is present; when JTA is present, the container uses that transaction manager |

Spring Framework DefaultMessageListenerContainer defaults to concurrentConsumers=1 and maxConcurrentConsumers=1. Increasing concurrency can change processing ordering and allow multiple consumers to process concurrently.

If the application declares a custom DefaultJmsListenerContainerFactory, factory settings can override Boot defaults. Therefore, inspect the actual factory used by @JmsListener.

### 7.4. Transactions and acknowledgements in TxEventQ

TxEventQ can coordinate database DML with send/consume operations inside a single local transaction when using supported transaction features.

With Spring JMS:

- Requires a transacted JMS Session.
- AQjmsSession.getDBConnection() provides the JDBC connection tied to the session.
- DML and JMS operations are committed/rolled back together when the container commits the session.

With TxEventQ Stream Binder:

- Functional callbacks need to work directly with Spring Message.
- TxEventQUtils.getDBConnection(message) retrieves the JDBC connection tied to the consume operation.
- DML and message consume/produce can share one local transaction per binder capabilities.

Do not generalize these transaction semantics to OCI Queue or OCI Streaming. For those services, use appropriate inbox/outbox patterns, idempotency, or reconciliation.

## 8. Changes That Can Appear After an Upgrade

When versions increase, several changes can affect runtime even without config file edits:

| Change source | Potential impact |
| --- | --- |
| OCI SDK patch | Operations enabled for retry or retry conditions change |
| Spring Cloud Stream patch/minor | Binding defaults, retry integration, or lifecycle changes |
| Spring Boot/Spring Framework | Listener factory auto-configuration, transaction defaults, or property binding changes |
| TxEventQ binder | Consumer polling, batch behavior, transaction integration, or compatibility changes |
| OCI authentication module | New auth modes, provider implementation, or token handling changes |
| Environment/profile | Property overrides altering identity, region, retries, or listeners |

Do not evaluate an upgrade solely from release notes. Compare effective runtime configuration and test the same workload across both versions.

### 8.1. Conclusions supported by public documentation

| Item | Comparison evidence | Safe conclusion |
| --- | --- | --- |
| OCI authentication default | Both 1.0.0 and 2.0.4 docs state FILE; profile DEFAULT is preserved | No evidence the FILE default changed between these two doc milestones |
| Auth modes | 1.0.0 docs list FILE, SIMPLE, INSTANCE_PRINCIPAL, and RESOURCE_PRINCIPAL; current docs also list SESSION_TOKEN and WORKLOAD_IDENTITY | Choice set expanded; does not mean apps automatically switch to new modes |
| OCI SDK retry | SDK docs describe operation-specific default retries; OCI 2.0.4 release notes only mention refreshing third-party dependencies | Must check actual SDK version and per-operation Javadoc; release notes do not confirm retry policy stayed identical |
| Spring Cloud Stream listener | Defaults autoStartup/concurrency/retry belong to Spring Cloud Stream ConsumerProperties | Compare the actual Spring Cloud Stream version resolved by the binder; do not attribute every difference to the OCI starter |
| TxEventQ binder | Oracle docs publish a 1000 ms consumer timeout and dedicated batch properties | Check binder version, batch-mode, and transaction configuration separately |
| Spring JMS listener | Defaults are governed by Spring Boot auto-configuration and the listener factory | Check Boot version, custom factories, JTA, and session transaction mode |

Spring Cloud Oracle 2.0.4 release notes state an upgrade of Spring Boot to 4.1.1 and refreshed third-party dependencies, without publishing specific changes to default identity, SDK retries, or listener concurrency. That alone is not enough to conclude runtime is unchanged; it identifies the exact points to verify via dependency graphs and regression tests.

## 9. Explicit Configuration for Production

One way to reduce reliance on defaults is to explicitly set values that affect security and delivery.

### 9.1. Identity

~~~yaml
spring:
  cloud:
    oci:
      config:
        type: INSTANCE_PRINCIPAL
      region:
        static: OCI_REGION
~~~

### 9.2. Spring Cloud Stream listener

~~~yaml
spring:
  cloud:
    stream:
      bindings:
        invoiceConsumer-in-0:
          destination: INVOICE_EVENTS
          group: INVOICE_WORKERS
          consumer:
            auto-startup: true
            concurrency: 2
            max-attempts: 3
            back-off-initial-interval: 1000
            back-off-max-interval: 10000
            back-off-multiplier: 2.0
            default-retryable: true
~~~

Increase concurrency only after measuring throughput, DB pools, downstream capacity, and ordering requirements. The value 2 is a configuration example, not the default.

### 9.3. Spring JMS listener

~~~yaml
spring:
  jms:
    listener:
      auto-startup: true
      min-concurrency: 1
      max-concurrency: 1
      receive-timeout: 1s
      session:
        acknowledge-mode: auto
        transacted: true
~~~

If using JTA or a custom listener factory, verify the actual transaction manager and factory. Do not blindly set session.transacted=true if the application uses JTA or different transaction semantics.

### 9.4. OCI SDK retry

SDK retries should be configured per client/request and operation. For example, request-level configuration can cap attempts:

~~~java
RetryConfiguration noRetry =
        RetryConfiguration.builder()
                .terminationStrategy(new MaxAttemptsTerminationStrategy(1))
                .build();

GetObjectRequest request = GetObjectRequest.builder()
        .namespaceName(namespace)
        .bucketName(bucketName)
        .objectName(objectName)
        .retryConfiguration(noRetry)
        .build();
~~~

The example above illustrates a request override. In real applications, choose retry policies based on operation idempotency, request body replayability, and timeout budgets. Do not disable retries globally if only one operation needs special handling.

## 10. Verification Process Before and After Upgrade

### Step 1 — Capture baseline

Save:

- Dependency tree/runtimeClasspath.
- Effective bound application properties.
- Principal appearing in OCI Audit.
- Retry behavior of critical operations.
- Listener auto-startup/concurrency.
- Message attempts/redelivery/DLQ.
- Consumer lag/queue depth.
- Database transaction/acknowledgement behavior.

### Step 2 — Compare version-specific documentation

Read:

- Spring Cloud Oracle release notes.
- OCI Core and Configuration Properties docs.
- OCI Java SDK Javadoc for operations in use.
- Version-matched Spring Cloud Stream binding properties.
- Version-matched Spring Boot JMS application properties.
- Oracle TxEventQ binder docs and binder-specific properties.

Do not use latest documentation to draw conclusions about an older runtime version if APIs/defaults changed. Record URLs/versions and the check date.

### Step 3 — Verify effective configuration

Use Spring Boot Actuator configprops or configuration metadata in a test environment to inspect bound properties. You can use the auto-configuration report (--debug) to identify which beans/containers were created.

Do not expose env, configprops, beans, or sensitive endpoints publicly. These endpoints can leak configuration and internal details. If Actuator is needed in production, restrict access with authentication, network policies, and endpoint exposure controls.

### Step 4 — Verify identity

- Start up using the test environment's identity.
- Call a read-only operation first.
- Verify the principal in OCI Audit.
- Verify region and compartment.
- Run positive and negative IAM tests.
- Confirm no legacy profile/API key is loaded silently.

### Step 5 — Verify retries

Create controlled scenarios:

- A request that succeeds on the first attempt.
- A transient error such as 429/503.
- A non-retryable error such as 400/401/403.
- A timeout after the server may have received the request.
- A non-idempotent operation.
- An async SDK client if the application uses one.

Record the actual request count, intervals between retries, request IDs, and final outcomes. Do not rely solely on counting exceptions in application logs.

### Step 6 — Verify listeners

- Does the container/binding auto-start?
- Is the consumer count as expected?
- Can consumers be stopped/started via lifecycle controls?
- How many times are exceptions retried?
- What happens to messages after retries are exhausted?
- Does ack/commit occur after the business transaction?
- Does shutdown wait for in-flight messages to finish?
- Are duplicates produced during process restarts?
- Does ordering change when concurrency increases?

### Step 7 — Compare and approve rollout

Roll out only when:

- Identity is right and follows least privilege.
- Retries stay within the latency budget.
- Listener concurrency fits capacity.
- No unexpected duplicate side effects occur.
- Transaction/ack semantics are verified.
- DLQ/replay/reconciliation works.
- Metrics and alerts can detect new errors.

## 11. Regression Test Matrix

| Group | Test | Expected result |
| --- | --- | --- |
| Identity | Local FILE profile | Principal is the test user |
| Identity | Instance Principal on Compute | Principal is the intended instance |
| Identity | Resource/Workload Identity | Principal matches resource/workload |
| Identity | Missing IAM policy | Request denied, no fallback to admin |
| SDK retry | 429/503 | Retries per operation policy |
| SDK retry | 401/403 | Does not retry endlessly |
| SDK retry | Async client | Errors handled per application retry logic |
| Stream listener | Binding startup | Matches locked autoStartup |
| Stream listener | Handler throws | Attempt count matches maxAttempts |
| Stream listener | Concurrency | Consumer count matches configuration |
| JMS listener | Container startup | Correct lifecycle and receive timeout |
| JMS listener | Transaction rollback | Message is not lost before commit |
| TxEventQ | DML + consume | Shares transaction per supported binder/JMS mode |
| Recovery | App restart | Uncommitted messages are safely reprocessed |
| Duplicate | Redelivery | Side effects remain idempotent |
| DLQ | Retries exhausted | Message follows configured error/DLQ flow |

## 12. Common Issues After an Upgrade

### 12.1. Application still uses FILE in production

Cause: spring.cloud.oci.config.type was not declared and the FILE default stayed active.

Resolution:

- Set the auth type explicitly per runtime.
- Check environment variables/profiles.
- Verify the principal via OCI Audit.
- Do not embed personal API keys into images as a workaround.

### 12.2. Retries spike unexpectedly

Possible causes:

- Newer OCI SDK enables retries for an operation that previously did not retry.
- Request-level/client-level retry overrides were removed.
- Listener retries and broker redelivery compound.
- A new error is classified as retryable.

Resolution:

- Identify request IDs and operations.
- Check operation Javadoc for the running SDK version.
- Inspect retry configuration across all three layers.
- Check whether events/messages are duplicated.
- Establish idempotency and retry budgets.

### 12.3. Listener processes slowly or backlog grows

Possible causes:

- concurrency remained 1 after workload increased.
- Listener retries block consumer threads during backoff.
- receive-timeout or binder timeout is unsuitable.
- Connection pool is exhausted.
- Database transactions stay open too long.

Resolution:

- Measure consumer throughput and processing duration.
- Check DB pools and downstream capacity.
- Increase concurrency in a controlled manner.
- Offload slow retries to a DLQ/retry queue if supported by the binder.
- Avoid keeping transactions open while calling external APIs.

### 12.4. Messages are processed multiple times

Causes:

- Business commit succeeded, but ack/settlement failed.
- Process died before checkpointing.
- Listener retries and broker redelivery stacked up.
- Timeout left the client unsure whether the operation completed.

Resolution:

- Use a business event ID/inbox table.
- Commit business effects and idempotency markers in the same transaction when possible.
- With TxEventQ, leverage supported transaction integration.
- With OCI Queue/Streaming, design dedicated reconciliation and deduplication.

### 12.5. Listener fails to start

Check:

- Is auto-startup set to false?
- Is there a custom listener factory?
- Does the binding function definition match the bean name?
- Can the binder/destination be resolved?
- Does Database/Queue connectivity succeed?
- Do auto-configuration conditions match?

Do not assume the cause is service unavailability; the binding might be disabled by a property or profile.

## 13. Rollout and Rollback

### Before rollout

- Pin versions of Boot, Spring Cloud, OCI SDK, and binders.
- Lock auth type and listener settings.
- Save the dependency tree and effective config.
- Run regression tests.
- Prepare rollback image and previous config.
- Determine whether uncommitted messages can be processed by both old and new versions.

### Canary

Deploy a small group of consumers:

1. Verify principal and policies.
2. Observe retry counts and error codes.
3. Observe queue depth/stream lag.
4. Check duplicates and ordering.
5. Check transactions/acks.
6. Scale up replicas once behavior stabilizes.

### Rollback

If rollback is needed:

- Stop new consumers using the verified lifecycle controls.
- Ensure uncommitted messages can still be processed by the old version.
- Do not delete queues, stream cursors, or checkpoints.
- Avoid downgrading schemas/payloads that old consumers cannot understand.
- Restore the baseline dependency graph and configuration.
- Reconcile timed-out/unknown-outcome operations before replaying messages.

## 14. Hands-On Exercise: Verifying the Invoice Worker Upgrade

**Context:** Invoice Worker upgrades Spring Boot and Spring Cloud OCI. The application uses Instance Principal to read secrets from Vault, receives messages from Oracle TxEventQ via the Spring Cloud Stream binder, and calls the Object Storage SDK to read PDFs.

The task is to prove identity, SDK retries, and listener behavior do not change unintentionally.

### Part A — Identity

1. Record Spring Cloud OCI version before/after.
2. Record effective spring.cloud.oci.config.type.
3. Confirm production uses INSTANCE_PRINCIPAL.
4. Verify the principal in OCI Audit.
5. Verify IAM policies permit reading only the required secrets/objects.
6. Confirm no FILE profile is loaded unintentionally.

### Part B — Retries

1. Record actual OCI SDK version.
2. Check Javadoc for the GetObject operation.
3. Check request/client/global retry configuration.
4. Check Spring Cloud Stream maxAttempts and backoff.
5. Trigger 503 and 403 test cases.
6. Count OCI API calls and listener execution attempts.
7. Verify no duplicate business effects are created.

### Part C — Listener

1. Record autoStartup, concurrency, and maxAttempts.
2. Check TxEventQ binder timeout and batch mode.
3. Run the consumer with concurrency 1.
4. Increase concurrency to 2 in the test environment.
5. Inject a failure after consume and before business commit.
6. Verify rollback/redelivery.
7. Test shutdown and restart.
8. Verify messages are processed effectively once at the business level.

### Part D — Report

Create a table:

| Item | Before upgrade | After upgrade | Conclusion |
| --- | --- | --- | --- |
| Auth type |  |  |  |
| Audit principal |  |  |  |
| OCI SDK retry |  |  |  |
| Stream maxAttempts |  |  |  |
| Listener auto-start |  |  |  |
| Listener concurrency |  |  |  |
| TxEventQ timeout |  |  |  |
| Transaction/ack |  |  |  |
| Duplicate test |  |  |  |

### Deliverables

- Before and after dependency tree/effective POM.
- Table of authentication defaults and principal audits.
- Table of retry policies per OCI operation.
- Table of Spring Cloud Stream/JMS listener settings.
- Integration tests for 429/503/403 and timeouts.
- Tests for concurrency, rollback, redelivery, and duplicates.
- Metrics for retry count, listener duration, consumer lag, and DLQ.
- Decision to keep or change each default with rationale.
- Rollout and rollback runbook.

## 15. Self-Check Questions

1. Why can upgrading a version change behavior even when application.yaml does not change?
2. Are FILE and DEFAULT still defaults in Spring Cloud OCI 2.0.4?
3. Are SESSION_TOKEN and WORKLOAD_IDENTITY selected automatically after upgrading?
4. What is the precedence of static region?
5. Why must you check the principal via OCI Audit?
6. Are OCI SDK retries enabled for every operation?
7. Which HTTP statuses/errors can be retried under the SDK default condition?
8. How does the OCI SDK's default max-attempts differ from Spring Cloud Stream's maxAttempts?
9. Why can request-level retry config override client-level config?
10. Does the async OCI SDK client use default retries?
11. How many retries are included in Spring Cloud Stream's maxAttempts=3?
12. What do autoStartup=true and concurrency=1 mean?
13. Why do Queue/Streaming starters not have listener defaults like Spring Cloud Stream?
14. What kind of timeout is the 1000 ms TxEventQ binder timeout?
15. Which container does Spring JMS @JmsListener create by default?
16. When does Spring Boot enable transacted JMS sessions?
17. Why can increasing listener concurrency affect ordering?
18. How do listener retries differ from broker redelivery?
19. How do you verify business effects are not duplicated?
20. What evidence should be saved before rolling out an upgrade?

## 16. Key Takeaways

- Do not infer default changes solely from a version bump; compare release notes, dependency graphs, configuration metadata, and runtime behavior.
- Spring Cloud OCI 1.0.0 and 2.0.4 both publish FILE as the authentication default; the default profile is DEFAULT.
- Newer auth modes like SESSION_TOKEN and WORKLOAD_IDENTITY expand choices without automatically replacing the currently configured identity.
- spring.cloud.oci.region.static takes precedence over the region in auth configuration.
- OCI SDK retries and Spring Cloud Stream listener retries are two independent mechanisms.
- OCI SDK retries are enabled per operation; do not assume every request retries.
- The OCI SDK default retry strategy uses max-attempts 8, exponential backoff, jitter, and a 30-second maximum delay per SDK documentation; verify Javadoc for the actual version.
- Spring Cloud Stream consumer defaults include autoStartup=true, concurrency=1, maxAttempts=3, backoff 1s/10s/multiplier 2, and defaultRetryable=true.
- OCI Queue/Streaming starters expose service API beans; no listener auto-start default exists in starter documentation.
- The TxEventQ binder uses Spring Cloud Stream consumer defaults; the binder-specific consume timeout defaults to 1000 ms.
- Spring JMS @JmsListener uses DefaultMessageListenerContainer per configuration; check auto-startup, concurrency, receive timeout, and transaction mode.
- Listener retries, broker redelivery, and SDK retries can compound; establish idempotency and retry budgets.
- Lock identity/retry/listener settings once verified and save before/after upgrade evidence.

## References

- [Spring Cloud Oracle 1.0.0 — OCI authentication defaults](https://oracle.github.io/spring-cloud-oracle/1.0.0/reference/html/appendix.html)
- [Spring Cloud Oracle 1.4.5 — Reference documentation](https://oracle.github.io/spring-cloud-oracle/latest/reference/html/index.html)
- [Spring Cloud OCI 2.0.4 — Core authentication](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/core/)
- [Spring Cloud OCI 2.0.4 — Configuration properties](https://oracle.github.io/spring-cloud-oracle/site/docs/oci/configuration-properties/)
- [Spring Cloud Oracle — Release notes](https://oracle.github.io/spring-cloud-oracle/site/docs/releases/changelog/)
- [OCI Java SDK — Concepts and retry behavior](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdkconcepts.htm)
- [OCI Java SDK — DefaultRetryCondition Javadoc](https://docs.oracle.com/en-us/iaas/tools/java/latest/com/oracle/bmc/retrier/DefaultRetryCondition.html)
- [Spring Cloud Stream 5.1 — Binding properties](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/binding-properties.html)
- [Spring Cloud Stream — Error handling](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/overview-error-handling.html)
- [Oracle TxEventQ — Spring Framework integration](https://docs.oracle.com/en/database/oracle/oracle-database/26/adque/txeventq-with-springframework.html)
- [Spring Boot 4.1 — JMS application properties](https://docs.spring.io/spring-boot/4.1/appendix/application-properties/index.html)
- [Spring Boot 4.1 — JMS integration](https://docs.spring.io/spring-boot/4.1/reference/messaging/jms.html)
- [Spring Framework 7 — DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/7.0.x/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html)
