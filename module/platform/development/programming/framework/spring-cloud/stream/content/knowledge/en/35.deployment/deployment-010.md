# Pipeline Deployment Role of Spring Cloud Data Flow and Scope Boundaries

In an event-driven system, Spring Cloud Stream is the framework for writing applications that connect to Kafka, RabbitMQ, or other binders via `Supplier`, `Function`, and `Consumer` functions. When multiple source, processing, and sink applications need to be deployed into a continuous pipeline, **Spring Cloud Data Flow (SCDF)** can help register artifacts, describe topologies, deploy processes, manage versions, and observe their state.

SCDF is **not** a library you need to add to every Spring Cloud Stream project. A Spring Cloud Stream application still runs standalone via `java -jar`, containers, Kubernetes Deployments, or other platforms. SCDF is an *optional* deployment orchestration layer placed on top of packaged applications. It does not replace the broker, execute `Function` logic on the app's behalf, or automatically guarantee exactly-once, retries, or data consistency.

**Product lifecycle note:** Spring announced on **April 21, 2025** that Spring Cloud Data Flow, Spring Cloud Deployer, and Spring Statemachine will no longer be maintained as open-source projects. **SCDF 2.11.x is the final OSS branch**; subsequent releases are commercial-only for Tanzu Spring customers. When considering SCDF for new projects, evaluate licensing rights, security patch channels, version compatibility, and alternatives. This **does not mean Spring Cloud Stream is ceasing open-source development**.

## 1. Distinguishing Event-Processing Frameworks from Deployment Platforms

| Component | Primary Responsibility | What It Does Not Replace |
|---|---|---|
| **Spring Cloud Stream** | Declaring input/output bindings; writing `Supplier`, `Function`, `Consumer`; using binders to exchange messages | Does not manage the full lifecycle of multiple applications |
| **Kafka/RabbitMQ/Pulsar** | Storing and distributing messages per broker mechanics | Does not dictate how Java code is deployed |
| **Spring Cloud Data Flow** | Registering apps, describing pipelines, initiating deployments, managing releases, and observing pipelines | Does not process individual messages in the data path |
| **Spring Cloud Skipper** | Managing stream release lifecycles, upgrades/rollbacks in the SCDF/Skipper model | Is not a message broker |
| **Spring Cloud Deployer / platform** | Creating actual processes or workloads on local, Kubernetes, or Cloud Foundry per configuration | Does not replace binders and message semantics |
| **Spring Cloud Task / Batch** | Running finite jobs; recording execution state and batch processing | Is not equivalent to continuous streams |

SCDF organizes *deployable applications*; Spring Cloud Stream controls data flow *inside each application*. This distinction avoids confusion during troubleshooting: Kafka connection failures usually require checking the binder and broker rather than SCDF status alone; Pod creation failures point to the deployer, registry, or Kubernetes.

## 2. Control Plane and Data Plane Architecture

~~~mermaid
flowchart TB
    subgraph Control["Control plane: deployment and management"]
      Operator[Developer / Operator] --> SCDF[SCDF Server + Shell / UI / REST]
      SCDF --> Registry[App registry: Maven / OCI image]
      SCDF --> Skipper[Skipper: stream release lifecycle]
      Skipper --> Platform[Kubernetes / Cloud Foundry / local deployer]
    end
    subgraph Data["Data plane: event processing"]
      Source[Source: Supplier / HTTP ingestion]
      Processor[Processor: Function]
      Sink[Sink: Consumer]
      Broker[(Kafka / RabbitMQ)]
      Source --> Broker
      Broker --> Processor
      Processor --> Broker
      Broker --> Sink
    end
    Platform -. starts / updates .-> Source
    Platform -. starts / updates .-> Processor
    Platform -. starts / updates .-> Sink
~~~

The **control plane** accepts operator requests, resolves artifacts, wires applications per declaration, and instructs the platform to deploy. The **data plane** consists of running Spring Boot applications and the brokers they exchange messages through. Messages do not pass through SCDF Server during processing.

If SCDF Server becomes temporarily unavailable while the applications, broker, and platform remain healthy, running pipelines can generally continue processing. Conversely, SCDF cannot fix a schema-mismatched consumer or a broker that lost quorum. SCDF is needed again when modifying definitions, upgrading, rolling back, or inspecting status through the management UI.

## 3. Source, Processor, and Sink Building Blocks

In the pipeline model, each stage is typically packaged as a separate Spring Boot application:

- **Source:** Ingests data from HTTP, files, schedulers, or external services and sends messages to the broker. `Supplier<T>` is the typical function type; sources may also use `StreamBridge` or other integrations.
- **Processor:** Receives a message, transforms/filters/enriches data, and emits a new message, typically a `Function<I,O>`.
- **Sink:** Receives messages and performs final output, such as writing to a database, auditing, or calling another service; typically a `Consumer<T>`.

Business example:

~~~text
order-source | normalize-order | persist-order
    |               |                  |
  Supplier       Function            Consumer
    |               |                  |
    +-- Kafka topic A --> Kafka topic B --> database
~~~

The `|` operator in SCDF Stream DSL represents separate applications communicating over messaging middleware. Do not confuse it with `spring.cloud.function.definition=first|second`: the `|` in Spring Cloud Function composes functions running **inside the same application/JVM**. The two mechanisms differ in deployment scope, operations, and failure domains.

Applications with multiple inputs/outputs, fan-out, dynamic topics, or complex Kafka Streams topologies do not necessarily fit the traditional single-input/single-output Stream DSL model. In those cases, you can use Stream Application DSL with explicit binding configuration, or deploy the applications directly without SCDF.

## 4. Workflow for Deploying a Stream with SCDF

In the SCDF/Skipper lifecycle, the standard workflow includes:

1. **Build and publish** Spring Boot applications as Maven artifacts or OCI images.
2. **Register** each artifact under an application name and type: `source`, `processor`, `sink`.
3. **Create** the stream definition using DSL, which does not yet launch the applications.
4. **Deploy** the stream to a configured platform.
5. **Inspect/monitor** application state, groups, broker metrics, and processing outcomes.
6. **Update / rollback** applications in the stream by registered release/version.
7. **Undeploy** to stop workloads; **destroy** to delete the definition once no longer used.

Registering an artifact merely tells SCDF where the artifact lives; it creates no containers. Similarly, `create` stores the pipeline definition; `deploy` actually launches workloads. Keep these three states distinct when authoring CI/CD pipelines and runbooks.

## 5. Registering Applications via Maven or OCI Image

SCDF resolves application artifacts from repositories accessible to the server/deployer. For Kubernetes, Docker images are the usual choice; local deployments can also use Maven artifacts depending on configuration.

Example commands in **Spring Cloud Data Flow Shell** (not direct Bash):

~~~text
dataflow:> app register --name order-source --type source --uri docker://registry.example.com/event/order-source:1.0.0
dataflow:> app register --name normalize-order --type processor --uri docker://registry.example.com/event/normalize-order:1.0.0
dataflow:> app register --name persist-order --type sink --uri docker://registry.example.com/event/persist-order:1.0.0

dataflow:> app list
~~~

The image URIs here are placeholders, not real artifacts. The registry must grant pull permissions to the platform controlled by SCDF/Skipper. Spring Boot and Spring Cloud Stream versions inside each image must be compatible with the binder, JDK, broker, and wiring mechanism used by SCDF.

A Maven URI example:

~~~text
dataflow:> app register --name normalize-order --type processor --uri maven://com.example:normalize-order:1.0.0
~~~

Do not overwrite the contents of an existing image tag or Maven coordinate expecting SCDF to pull new bytes automatically: registries/deployers may cache artifacts. Use immutable versions or image digests, register the new version, and deploy via the update/rollback workflow.

If compatible pre-built applications exist, you can import multiple registrations from a properties file formatted as `source.name=URI`, `processor.name=URI`, `sink.name=URI`. Never assume any legacy application catalog remains compatible with newer Spring Boot and Spring Cloud Stream versions.

## 6. Creating, Deploying, and Inspecting Stream Status

After registering the three applications, define the pipeline:

~~~text
dataflow:> stream create --name orderPipeline --definition "order-source | normalize-order | persist-order"
dataflow:> stream info orderPipeline
~~~

This definition represents the **logical topology**. Upon deployment, SCDF assigns destinations to adjacent output/input pairs so messages flow through the shared broker. Each app still needs appropriate binder configuration and broker connectivity permissions.

For apps using the modern `Supplier`, `Function`, `Consumer` style, ensure the binding names that traditional SCDF DSL expects as `input`/`output` are mapped accurately. The deployment example below is a *template*; actual bean names must match the code inside each image:

~~~text
dataflow:> stream deploy --name orderPipeline --properties "app.order-source.spring.cloud.stream.function.bindings.publishOrder-out-0=output,app.normalize-order.spring.cloud.stream.function.bindings.normalizeOrder-in-0=input,app.normalize-order.spring.cloud.stream.function.bindings.normalizeOrder-out-0=output,app.persist-order.spring.cloud.stream.function.bindings.persistOrder-in-0=input"
~~~

Where:

- `publishOrder` must be the `Supplier` bean in `order-source`.
- `normalizeOrder` must be the `Function` bean in `normalize-order`.
- `persistOrder` must be the `Consumer` bean in `persist-order`.
- `app.<app-name>....` properties are passed to each app at deployment time.
- `spring.cloud.stream.function.bindings.<implicit-name>=input/output` maps functional binding names to the convention used by traditional SCDF Stream DSL.

Some sample SCDF applications already define `input`/`output` aliases and need no remapping. Conversely, a newly written app having only `normalizeOrder-in-0`/`normalizeOrder-out-0` **must not be assumed automatically compatible** with every SCDF version. Testing against a real broker and verifying assigned destinations at both ends is mandatory.

For long property lists, store them in a controlled deployment properties file rather than typing everything inline on the shell. Never place plaintext credentials in shell history; use secret injection or platform-specific credential mapping.

## 7. Example Functional Code for the Three Applications

The three Java snippets below illustrate the core logic; each bean belongs to an **independent Spring Boot application** packaged and registered separately. They are not three beans running inside the same application context when SCDF deploys the three stages.

**Source** (`order-source`):

~~~java
import java.util.function.Supplier;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SourceConfiguration {

    @Bean
    Supplier<String> publishOrder() {
        return () -> "order-created";
    }
}
~~~

**Processor** (`normalize-order`):

~~~java
import java.util.Locale;
import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class ProcessorConfiguration {

    @Bean
    Function<String, String> normalizeOrder() {
        return value -> value.trim().toUpperCase(Locale.ROOT);
    }
}
~~~

**Sink** (`persist-order`):

~~~java
import java.util.function.Consumer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SinkConfiguration {

    @Bean
    Consumer<String> persistOrder() {
        return event -> System.out.println("Accepted: " + event);
    }
}
~~~

In practice, `Supplier` must read from a real data source or emit periodically; by default, a poller invokes suppliers on a schedule. `Consumer` must persist durably or execute controlled final actions rather than merely printing logs. The example intentionally uses `String` to focus on deployment architecture; using JSON, Avro, or Protobuf requires adding schemas, serializers, and compatible contracts across all stages.

SCDF does not generate the code for these three applications or fix their business bugs. The development team must still build, test, version, and maintain each application.

## 8. App Properties vs. Deployer Properties

SCDF distinguishes two important property groups during deployment:

| Group | Meaning | Example |
|---|---|---|
| `app.<app>.<property>` | Passes Spring Boot/Spring Cloud Stream configuration to the application | `app.normalize-order.spring.cloud.function.definition=normalizeOrder` |
| `deployer.<app>.<property>` | Instructs the platform deployer on instance counts or resources | `deployer.normalize-order.count=2` |

Deployment example on a platform supporting `count`:

~~~text
dataflow:> stream deploy --name orderPipeline --properties "deployer.normalize-order.count=2,app.normalize-order.spring.cloud.function.definition=normalizeOrder"
~~~

This command only illustrates property-group syntax and assumes the app is already registered and wired properly; in practice, also pass function binding aliases as shown in the previous section if needed.

Do not use an `app` property expecting to scale Kubernetes Pods; likewise, do not use a `deployer` property to configure serializers or retries for the Kafka binder. Exact resource property names vary across local, Kubernetes, and Cloud Foundry deployers and across SCDF/Skipper versions; consult the corresponding platform documentation.

## 9. What Does SCDF Contribute When Using Kubernetes?

When SCDF/Skipper is configured to deploy to Kubernetes, operators can manage pipelines by definitions and releases instead of writing and editing every application's deployment manually.

SCDF/Skipper can assist with:

- Registering and selecting versions for each source/processor/sink.
- Deploying workloads according to platform configuration.
- Assigning Stream DSL input/output destination properties.
- Passing app properties, deployer properties, and platform selection.
- Checking release/application status and performing updates/rollbacks.
- Managing stream undeploy/destroy lifecycles.

Kubernetes still remains responsible for running Pods, scheduling, image pulls, DNS, resource quotas, network policies, and controller-driven restarts. SCDF does not become the Kubernetes control plane and does not replace cluster operational mechanisms.

For simple workloads with one or two microservices and fixed bindings, Kubernetes Deployments/Helm/GitOps may involve far fewer moving parts than SCDF. Weigh the benefits of the pipeline DSL model against the operational cost of running a Data Flow Server, Skipper, backing database, and management layer.

## 10. Upgrades and Rollbacks via Skipper

In SCDF 2.x architecture, Skipper manages stream releases and rolls out application version changes. Common shell examples:

~~~text
dataflow:> app register --name normalize-order --type processor --uri docker://registry.example.com/event/normalize-order:1.1.0
dataflow:> stream update --name orderPipeline --properties "version.normalize-order=1.1.0"
dataflow:> stream rollback --name orderPipeline
~~~

Register the new version before updating. Rollback operates at the application release level; it does not revert already-published messages, database side effects, topic schemas, or external transaction states.

Do not assume Skipper's update strategy always matches a native Kubernetes rolling update. Depending on version and platform, the strategy may spin up the new version alongside the old before switching over; during that window, old and new producer/consumer versions coexist.

Before releasing, verify:

1. Message schema compatibility while old/new versions coexist.
2. Impact of rebalancing on consumer groups and Kafka Streams tasks.
3. Idempotency if messages are redelivered.
4. Rollout plan if groups/partitions change.
5. Schema and database migration rollback safety.
6. Health, lag, DLQ, throughput, and business outcomes post-deployment.

SCDF facilitates release management; it is **not** an end-to-end upgrade safety guarantee.

## 11. Undeploy and Destroy Are Two Different Operations

~~~text
dataflow:> stream undeploy --name orderPipeline
dataflow:> stream destroy --name orderPipeline
~~~

**Undeploy** stops running pipeline workloads while keeping the stream definition available for future deployment. **Destroy** removes the stream definition/metadata from SCDF per product workflow, typically run after the stream has been undeployed.

Neither operation deletes Kafka topics, RabbitMQ queues, data already written by sinks, or application databases. Deleting message broker resources is a separate operational decision that can cause data loss and affect other consumers.

When stopping a pipeline, backlogs may keep growing if upstream producers continue emitting. For systems requiring zero event loss, plan to halt sources, drain backlogs, manage retention, and check consumer offsets before undeploying.

## 12. Role of Binders and Brokers in Pipelines

SCDF only wires the logical topology. Moving real messages requires binders and brokers:

~~~text
App A                         App B
Supplier                       Function
  |                              ^
  v                              |
output binding --- Kafka topic --- input binding
                    |
                 partitions
~~~

All of these conditions must hold simultaneously:

- Each app includes binder dependencies compatible with the chosen broker.
- Connected endpoints use the same destination, protocol/schema, and matching broker settings.
- Consumer groups are set properly so multiple instances share load without unintended duplication.
- Partition counts, partition keys, and serializers align if ordering/co-partitioning is required.
- TLS/SASL/credentials are configured and broker permissions are granted.
- Retries, DLQs, error handling, and acknowledgment semantics are verified at the **application/binder** layer.

SCDF can pass configuration via deployment properties, yet it cannot turn an image built with the Kafka binder into a Rabbit binder if the image lacks the right dependencies and setup. For multi-binder apps, specify the binder per binding and verify brokers match the defined data paths.

If bridging Kafka to RabbitMQ is needed, a bridge processor carrying both binders or an appropriate connector is required. A `|` symbol in DSL does not automatically translate broker protocols.

## 13. Limitation: Does Not Replace Business Logic or Data Correctness

SCDF is not responsible for executing mapping, filtering, enrichment, windowing, schema validation, or idempotency logic. Those responsibilities belong to Spring Cloud Stream functions, Kafka Streams topologies, or dedicated business services.

Examples:

- `normalizeOrder` receives schema-invalid JSON: failure occurs in the consumer deserializer/function and requires retry/DLQ policies.
- Unstable Kafka partition keys: ordering can break; SCDF does not fix partition keys.
- Sink writes duplicate data on redelivery: requires idempotency/inbox handling in the sink.
- Slow Kafka Streams state restoration: requires proper state store/changelog, CPU/memory/disk, and probe tuning.
- Downstream API unavailable: requires timeouts, backoff, circuit breakers, or an outbox depending on architecture.

Good deployment management does not equal end-to-end delivery guarantees. Choose at-least-once, transactions, or deduplication based on business needs, and test crashes between side effects and commits/acks.

## 14. Limitation: A Stream DSL Cannot Describe Every Topology

Stream DSL in the form `source | processor | sink` works well for linear chains. Yet Spring Cloud Stream supports many richer structures:

- A single function taking multiple inputs or emitting multiple outputs.
- Dynamic destinations via `StreamBridge`.
- Kafka Streams joins between `KStream` and `KTable`/`GlobalKTable`.
- Branching consumer topologies or stateful processing.
- Multiple binders or multiple clusters with differing partitioning.

With multiple inputs/outputs, Data Flow **cannot guess** which output connects to which input. Stream Application DSL uses `||` to denote cases where bindings are not auto-wired like linear DSL, requiring the application/definition to configure destinations and binders manually. Do not treat `||` as a message join operator; it governs how applications are declared and deployed, not a Kafka Streams operation.

SCDF also offers an application registration type `app` for Stream Application DSL. This can be a plain Spring Boot app not necessarily using Spring Cloud Stream; SCDF does not auto-configure its input/output bindings as it does for `source`/`processor`/`sink` in a `|` pipeline. Thus, when using `||` with multi-binding apps, setting destinations and testing data paths belongs to the pipeline designer.

When a pipeline contains complex branches, split it into separate streams with explicit destination names, or use Kubernetes manifests/Helm directly. Exact DSL and binding support depends on your SCDF/SCSt versions.

## 15. Limitation: SCDF Does Not Replace Message Brokers or Runtime Schedulers

Do not confuse three separate concerns:

| Question | Deciding Component |
|---|---|
| Where are messages stored and for how long? | Kafka/RabbitMQ/Pulsar and broker settings |
| Which function processes the message? | Spring Cloud Stream application |
| Which app, version, and instance count are deployed? | SCDF/Skipper/deployer + platform |
| Which node runs the Pod/process? | Kubernetes/Cloud Foundry/local runtime |
| When are offsets committed or messages acked? | Binder, client/container, and transaction/ack policies |
| When does a finite task or batch job run? | SCDF Task/Scheduler + Spring Cloud Task/Batch and platform |

For **streams**, applications are usually long-running workloads triggered continuously by messages. For **tasks/batches**, applications have a start and end; SCDF can launch and record execution history for Spring Cloud Task/Batch jobs. A stream pipeline does not turn into a batch job simply because SCDF created it.

Do not treat Stream DSL as an in-process ETL engine or a scheduler guaranteeing message ordering. If you need conditional workflows, compensation, human approvals, or complex DAGs, evaluate a dedicated workflow/task orchestration engine.

## 16. Limitations Across Multi-Environment and Multi-Version Deployments

SCDF manages pipelines using registered artifacts and configured platforms. Still, applications must be built for the target environment:

- **Local:** Convenient for learning and experimentation; does not capture production HA, network/security, or container orchestration requirements.
- **Kubernetes:** Requires registry access, namespaces/RBAC, resource requests/limits, secrets, Services/DNS, probes, and network policies.
- **Cloud Foundry:** Requires proper orgs/spaces, quotas, service bindings, and deployment properties.

Do not assume `docker://...` URIs fit every platform; some deployers use Maven artifacts or different artifact resolvers. Likewise, do not assume Spring Boot 3/4 or Spring Cloud Stream 5 images are automatically compatible with older SCDF 2.11 OSS releases: verify support matrices, binding property injection, and test against a real broker.

Similarly, the existence of a Pulsar binder in Spring Cloud Stream or an external library does not mean SCDF automatically ships a Pulsar app catalog, protocol bridges, or matching support matrix. To include a Pulsar app in a pipeline, verify the actual binder, deployment, and wiring work with your SCDF version.

In particular, older online examples use `@EnableBinding`, `@StreamListener`, or `input`/`output` binding names. Modern functional-model apps typically use `<functionName>-in-0`/`<functionName>-out-0`; for traditional SCDF DSL to wire properly, define aliases or explicit bindings as in section 6. Never copy legacy configs without accounting for this difference.

## 17. Securing the Management Plane

SCDF Server, Skipper, and platform deployers hold privileges affecting many workloads; protect them like administrative endpoints:

- Expose the UI/REST/Shell only over management networks or authenticated gateways.
- Apply RBAC and least privilege to stream deploy/update/rollback/destroy actions.
- Separate read-only status permissions from pipeline modification permissions.
- Store registry, broker, and deployer credentials in a secret store; never embed them in stream definitions or command logs.
- Verify image provenance, scan for CVEs, and pin artifact digests/versions.
- Audit who made changes, stream names, app versions, platforms, timestamps, and outcomes.
- Control source/sink egress and enforce network policies between apps and brokers.

Anyone allowed to alter a stream can deploy new images, affecting the data path and data access. Therefore, never treat SCDF as merely a read-only dashboard. Especially avoid granting broad deploy permissions to every developer on a shared production cluster.

## 18. Observing Across All Three Layers

A pipeline marked "deployed" is not necessarily processing properly. Combine observability across three layers:

| Layer | Indicators |
|---|---|
| SCDF/Skipper | Stream definition, app versions, deployment/rollout status, deployer errors |
| Runtime (Kubernetes/CF) | Pod/process health, restarts, CPU/RAM, volumes, readiness, image pulls |
| Data path (binder/broker/app) | Consumer lag, topic/queue depth, throughput, retries, DLQs, deserialization errors, state restore, business outcomes |

Once `stream deploy` reports success, run a smoke test with a specific message ID: feed data into the source, confirm the processor emits output, and verify the sink. Avoid relying solely on a health endpoint or release status to conclude the pipeline is not dropping messages.

If the pipeline includes a stateful Kafka Streams processor, a Ready Pod does not prove all state stores have finished restoring. Add application-appropriate readiness indicators and monitor lag/restore progress. During scale-in/scale-out, monitor rebalances and task migrations.

## 19. Choosing SCDF or Direct Deployment?

| Situation | Typically Sensible Choice | Reason |
|---|---|---|
| A standalone Spring Cloud Stream consumer | Direct Docker/Kubernetes/Cloud Foundry | Fewer moving parts and operational steps |
| A few services with stable destinations | Helm/GitOps or direct manifests | Easy to manage in existing repositories |
| Many reusable sources/processors/sinks wired via DSL | Consider SCDF if suitable version/support exists | App registry, stream definitions, shared lifecycle |
| Many pipelines with frequent version changes | SCDF/Skipper or a dedicated CD platform | Centralized release management |
| State machines, conditional workflows, step orchestration | A dedicated workflow engine | SCDF Stream DSL is not tailored for arbitrary workflow DAGs |
| Organizations without commercial SCDF patch access | Prefer evaluating direct deployment or actively supported solutions | Avoid relying on an unmaintained OSS control plane |

SCDF can fit existing operational platforms running many pipelines that benefit from centralized management. For greenfield projects, weigh total cost of ownership: HA setup, backing databases, Skipper, security, artifact registries, training, support, and version upgrades.

Choosing **not** to use SCDF is completely viable for production Spring Cloud Stream deployments. Teams directly configure matching output/input destinations, broker connections, consumer groups, manifests, metrics, and rollout workflows.

## 20. Practical Scenario: Split or Merge a Pipeline?

Suppose an application receives orders, computes taxes, and stores reports:

~~~text
HTTP/API source --> tax processor --> report sink
~~~

**Design A — Single Spring Boot application:** One `Function` or composed functions inside a single JVM receive messages, compute taxes, and persist results. Deploy as one container directly if workload is modest, release cycles move together, and independent per-step scaling is unnecessary.

**Design B — Three independent apps without SCDF:** Each step is its own Spring Cloud Stream app connected via topics. Kubernetes/Helm deploys three workloads; CI/CD updates artifacts and manifests. Fits teams with existing deployment platforms wanting explicit per-app control.

**Design C — Three apps with SCDF:** Register the three apps and describe the pipeline with Stream DSL. SCDF/Skipper manages definitions, deploys, updates, and rollbacks; binders still handle the message path. Fits organizations running many pipelines across reusable apps with valid SCDF licensing/maintenance.

In all three designs, delivery semantics, schema compatibility, idempotency, and data access controls must still be solved at the application/broker level. No deployment tool eliminates those requirements automatically.

## 21. Checklist Before Choosing and Using SCDF

- Clearly determined whether multi-app orchestration is needed or just deploying a single Spring Cloud Stream service.
- Checked support/licensing status of SCDF, Skipper, Deployer, and security patch availability.
- Verified compatibility across Spring Boot, Spring Cloud Stream, binders, and SCDF/Skipper versions.
- Sources/processors/sinks built, tested, versioned, and registered under the right artifact types.
- Distinguished register, create, deploy, update, rollback, undeploy, and destroy.
- For the functional model, properly mapped `<function>-in-0/out-0` to `input`/`output` if required by SCDF DSL.
- For multi-input/output pipelines, configured destinations manually instead of letting DSL guess.
- Separated `app` properties from `deployer` properties.
- Verified both ends of every data edge use compatible brokers, destinations, schemas, and binders.
- Designed consumer groups, partitioning, retries, DLQs, and delivery guarantees at the application/broker layer.
- Protected registries and management APIs with authentication, RBAC, and network policies.
- Accounted for schema evolution, rebalancing, side effects, and in-flight data in rollouts/rollbacks.
- Established separate observability for the control plane, runtime workloads, and data plane.
- Prepared a direct Docker/Kubernetes deployment path if SCDF proves unsuitable.

## Summary

Spring Cloud Data Flow helps **define and deploy multiple Spring Cloud Stream applications as pipelines**, managing artifacts, platforms, and release lifecycles. Data still flows directly between applications through brokers—not through SCDF Server. SCDF does not write business logic, support every topology automatically, replace Kubernetes or Kafka/RabbitMQ/Pulsar, or guarantee exactly-once delivery or data rollbacks.

Because SCDF ceased maintained open-source releases in 2025, adopting it in new architectures requires checking support entitlements and product compatibility before investing. When the goal is simply deploying standalone Spring Cloud Stream applications, Docker, Kubernetes, Helm, and GitOps are usually more direct and easier to control.

## References

- [Spring Cloud Data Flow Reference — Stream Introduction, Lifecycle, Skipper](https://docs.spring.io/spring-cloud-dataflow/docs/2.11.0/reference/htmlsingle/)
- [Spring Cloud Data Flow — Using Applications](https://dataflow.spring.io/docs/applications/)
- [Spring Cloud Data Flow — Functional Apps and Input/Output Binding Aliases](https://dataflow.spring.io/docs/recipes/functional-apps/scst-function-bindings/)
- [Spring Cloud Data Flow — Stream Application DSL](https://dataflow.spring.io/docs/feature-guides/streams/stream-application-dsl/)
- [Spring Cloud Stream — Functional Binding Names](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/functional-binding-names.html)
- [Spring Cloud Data Flow — Standalone Deployment Without Data Flow](https://dataflow.spring.io/docs/stream-developer-guides/streams/deployment/)
- [Spring Cloud Data Flow — FAQ: Runtime Independence](https://dataflow.spring.io/docs/resources/faq/)
- [Spring Blog, April 21, 2025 — Spring Cloud Data Flow End of Open-Source](https://spring.io/blog/2025/04/21/spring-cloud-data-flow-commercial/)
