# AWS IoT Greengrass and Disconnect Handling

IoT devices frequently operate in environments with unreliable Internet connectivity: factories with weak coverage, remote pumping stations, moving vehicles, or energy monitoring systems. If every decision had to be sent to the cloud and wait for a response, a single WAN outage could halt field operations.

AWS IoT Greengrass brings application processing down to edge devices. A Greengrass core device can run components, exchange messages over a local network, process data, and buffer data destined for the cloud. Once connectivity is restored, the device resumes synchronizing and forwarding data as configured.

Offline operation does not mean every AWS service continues working when the Internet drops. You must distinguish local processing, store-and-forward buffering, state synchronization, and operations that strictly require calling the AWS Cloud. A resilient system must define which data is retained, where it is stored, for how long, what happens when memory/disk fills up, and how duplicate records are handled after reconnecting.

This lesson focuses on AWS IoT Greengrass V2—specifically the Greengrass nucleus, component lifecycle, MQTT spooler, local MQTT broker, IPC pub/sub, Stream Manager, Shadow Manager, local deployments, and recovery workflows after disconnects.

## Learning Objectives

After this lesson, learners will be able to:

- Describe the roles of a Greengrass core device, nucleus, and components.
- Distinguish Internet outages from LAN outages or failures on the device itself.
- Determine which functions continue running locally and which require the cloud.
- Configure the MQTT spooler to buffer messages awaiting redelivery to AWS IoT Core.
- Distinguish QoS 0, QoS 1, memory spooler, and disk spooler.
- Enable client devices to authenticate while the core device is offline.
- Use the local MQTT broker, MQTT bridge, and local publish/subscribe for edge messaging.
- Use Stream Manager to store, prioritize, and export data once connectivity returns.
- Synchronize device shadows and resolve state conflicts.
- Update components via local deployments without Internet access.
- Design idempotency, retries, capacity planning, security, and runbooks for offline operations.

## 1. AWS IoT Greengrass V2 in Edge Architecture

AWS IoT Greengrass V2 is an edge runtime and component management platform running on edge devices. A device runs the Greengrass Core software, consisting of the Greengrass nucleus and installed components.

| Component | Role |
|---|---|
| Greengrass core device | Edge computer at a factory, retail store, vehicle, or gateway. |
| Greengrass nucleus | Mandatory runtime managing components, deployments, IPC, cloud connectivity, and core configuration. |
| Greengrass component | Software module with a recipe, artifacts, dependencies, and lifecycle. |
| AWS IoT Core | MQTT channel and cloud service for managing devices, receiving data, and exchanging state. |
| Client device | Sensor, PLC gateway, camera, or IoT device connecting locally to the core via MQTT. |
| Stream Manager | Stores and transfers high-volume data streams from the edge to the cloud or local targets. |
| Shadow Manager | Stores local shadows and synchronizes state with AWS IoT Device Shadow. |

~~~mermaid
flowchart TB
    subgraph Edge["Factory / Edge site"]
        D1["Sensor / PLC"]
        D2["Camera / Client device"]
        B["Local MQTT broker"]
        N["Greengrass nucleus"]
        P["Local IPC pub/sub"]
        C1["Component: control"]
        C2["Component: analytics"]
        SM["Stream Manager"]
        SH["Shadow Manager"]
        D1 --> B
        D2 --> B
        B <--> C1
        B <--> P
        P <--> C1
        P <--> C2
        C1 --> SM
        C2 --> SM
        N --- P
        N --- B
        N --- SM
        N --- SH
    end
    SM -->|When online| IOT["AWS IoT Core / Kinesis / S3 / SiteWise"]
    SH <-->|When online| CLOUDSH["AWS IoT Device Shadow"]
    N <-->|Control plane / MQTT| CLOUD["AWS IoT Greengrass Cloud"]
~~~

A component can filter data, run inference, control machinery, write logs, or communicate with other components over IPC. Installed components can continue running when cloud connectivity drops, provided the device and local dependencies remain healthy.

## 2. Understanding Disconnect States Properly

In practice, many distinct failure modes occur. Do not lump them all into a single "offline" state.

| Scenario | Impact | Continuity Capability |
|---|---|---|
| Internet/WAN down, LAN still up | Core cannot reach AWS Cloud; local devices still reach each other | Local components, local MQTT, local IPC, and locally stored data can continue |
| Core loses connection to AWS IoT Core | Cloud MQTT pub/sub and cloud deployments are interrupted | MQTT spooler can queue outbound messages; local processing continues |
| Client device disconnects from core | Core stops receiving data from that client | Other clients and core components continue operating |
| LAN outage between client devices and core | Local MQTT exchange fails | Only functions running directly on the core continue |
| Core device loses power or disk fails | Runtime and local processing stop | Requires reboot, storage recovery, or hardware replacement |
| AWS Cloud/service disruption | Certain cloud APIs unavailable | Edge can continue local processing and resend once services recover |

### 2.1. Capability Matrix When WAN Drops

| Capability | Can Operate Offline? | Condition |
|---|---|---|
| Installed component with local artifacts/dependencies | Yes | Core device remains running |
| Local IPC pub/sub between components | Yes | Nucleus and relevant components are running |
| Client devices sending MQTT to local broker | Yes | LAN, broker, and local auth remain operational |
| MQTT bridge routing between LocalMqtt and Pubsub | Yes | Mapping and bridge component remain running |
| MQTT bridge sending messages to AWS IoT Core | No during WAN loss | Resumes when cloud connection recovers |
| MQTT spooler holding outbound messages | Yes | Messages fit inside spool without exceeding capacity |
| Stream Manager storing streams locally | Yes | Storage still has free capacity |
| Stream Manager exporting to AWS services | No while cloud unreachable | Exports resume when network returns |
| Local device shadows | Yes | Shadow Manager and local shadow service are running |
| Shadow sync with AWS IoT Core | No during WAN loss | Resyncs upon reconnect |
| New cloud deployments | Cannot receive from cloud offline | Can use local deployments if recipes/artifacts are available |
| Local deployments via Greengrass CLI | Yes | CLI, recipes, artifacts, and dependencies are local |
| Calling AWS APIs from a component | Usually no | Only works if endpoints and credentials are reachable |

Greengrass maintains a runtime at the edge, but it does not turn AWS cloud APIs into local APIs. A component calling S3, DynamoDB, or other AWS services still requires network reachability and valid credentials.

## 3. Component Lifecycle and Autonomous Execution

Each Greengrass component includes:

- Recipe: name, version, configuration, dependencies, platform compatibility, and lifecycle.
- Artifact: scripts, binaries, libraries, or data files needed to run.
- Dependency: other components required beforehand or concurrently for operation.

| State | Meaning |
|---|---|
| `NEW` | Recipe and artifacts loaded, component not yet installed. |
| `INSTALLED` | Component installed. |
| `STARTING` | Executing startup lifecycle. |
| `RUNNING` | Component is running. |
| `FINISHED` | Run lifecycle completed successfully. |
| `ERRORED` | Component failed and executes recover lifecycle if defined. |
| `BROKEN` | Component failed repeatedly and cannot self-recover. |
| `STOPPING` | Executing shutdown lifecycle. |
| `UNINSTALLING` / `UNINSTALLED` | Uninstalling or uninstalled. |

If a component enters `ERRORED`, Greengrass runs its recover script and attempts a restart. If a component enters `ERRORED` three times without a successful run, it transitions to `BROKEN`. Consequently, a component with an infinite retry loop inside its script that fails to report errors to Greengrass can mask failures from operations.

### 3.1. Designing Cloud-Disconnect-Resilient Components

An edge component should:

- Start cleanly using recipes/artifacts already present on the device.
- Avoid calling cloud APIs during startup if core site functionality does not need the cloud.
- Use local IPC or local storage for mandatory on-site operations.
- Decouple cloud exporters from local processing so an exporter failure does not bring down control components.
- Implement health checks, logging, and proper recover scripts.
- Declare dependencies explicitly and enforce CPU/RAM resource limits.

For example, a machine control component can receive telemetry from the local broker and issue a local emergency stop if temperature exceeds a threshold. A separate component handles uploading telemetry to Kinesis. When WAN drops, the exporter stalls, but the control component keeps operating.

## 4. Cloud Deployments vs. Local Deployments

Greengrass supports two ways to update components:

- Cloud deployment: created in AWS IoT Greengrass Cloud; devices receive it via AWS IoT Jobs.
- Local deployment: created directly on the core device via the Greengrass CLI or CLI IPC service.

### 4.1. What Happens to a Cloud Deployment When Offline?

When a core device receives a cloud deployment, the nucleus resolves dependencies. The nucleus prefers component candidates already cached on the device. With a cloud deployment, the nucleus can query AWS Cloud for the newest compatible version. If the device is offline, it can use existing local candidates.

If no local candidate satisfies the version/dependencies, the deployment fails. New artifacts cannot be downloaded from the cloud without network access.

Therefore, before deploying offline, pre-stage:

- Component recipes.
- Artifacts and dependencies.
- Versions compatible with the OS/architecture.
- Required configuration.
- Sufficient disk space and directory permissions.

### 4.2. Creating a Local Deployment

Example deploying a component whose recipe and artifacts are already staged on a Linux core device:

~~~bash
sudo /greengrass/v2/bin/greengrass-cli deployment create \
  --recipeDir ./recipes \
  --artifactDir ./artifacts \
  --merge "com.example.EdgeProcessor=1.0.0"
~~~

Track the deployment:

~~~bash
sudo /greengrass/v2/bin/greengrass-cli deployment list

sudo /greengrass/v2/bin/greengrass-cli deployment status \
  --deploymentId <DEPLOYMENT_ID>
~~~

Local deployments use local candidates only. If a recipe specifies a dependency that is missing and absent from the local artifact store, the deployment cannot complete.

Local deployment status is inspected on-device via the Greengrass CLI; local deployments cannot be tracked in the AWS IoT Greengrass console like cloud deployments.

### 4.3. Managing Offline Changes

A safe procedure:

1. Package recipes/artifacts by component version.
2. Verify artifact checksums and signatures if supported by the release pipeline.
3. Copy packages to the device over an approved administrative channel.
4. Trigger the local deployment inside a maintenance window.
5. Check deployment status and component lifecycles.
6. Run local smoke tests.
7. Record running versions and outcomes.
8. When connectivity returns, reconcile running components/versions against cloud deployment policies and decide whether to issue a cloud deployment to align the baseline.

Avoid letting local deployments and cloud deployments manage different uncoordinated versions of the same component. When the next cloud deployment arrives, it can overwrite the target's component set or configuration.

## 5. MQTT Spooler: Buffering Outbound Messages for AWS IoT Core

The Greengrass nucleus manages component MQTT messages communicating with AWS IoT Core. When the core device loses cloud connectivity, the nucleus can buffer messages to retry publishing once connectivity returns.

The MQTT spooler is a store-and-forward mechanism for outbound MQTT messages. It is neither a replacement message broker for AWS IoT Core nor a long-term archive for arbitrary data.

### 5.1. How Does QoS Affect Spooling?

| QoS | Behavior When Core Is Offline |
|---|---|
| QoS 0 | Dropped by default if unsendable. Set `keepQos0WhenOffline` to spool QoS 0 messages. |
| QoS 1 | Nucleus always spools messages for redelivery unless the spool is full. |
| QoS 2 | Do not assume end-to-end QoS 2 spooler support; verify the specific broker, protocol, and bridge. |

MQTT QoS 1 is at-least-once. After reconnects or retries, consumers can receive duplicate messages. Downstream applications need idempotency keys or event IDs to avoid executing business logic twice.

### 5.2. Memory Spooler vs. Disk Spooler

Per current Greengrass nucleus configuration:

| Property | Default / Supported Value |
|---|---|
| `storageType` | `Memory` |
| `maxSizeInBytes` | 2.5 MB for unacknowledged messages cached in memory |
| `keepQos0WhenOffline` | `false` |
| Disk spooler | Available since Greengrass nucleus 2.11.0 |
| Default disk plugin | `aws.greengrass.DiskSpooler` |
| `maxPublishRetry` | 100 retries |
| `maxInFlightPublishes` | 5 concurrent unacknowledged QoS 1 messages |

If the cache fills up, new messages are rejected. Therefore, do not rely on the default memory spooler as a multi-hour queue for a device continuously emitting telemetry.

The disk spooler is better suited when outbound MQTT needs longer retention and protection against losing the queue on process restarts. However, disk space remains finite; monitor disk usage, directory permissions, and export throughput after reconnecting.

### 5.3. Configuring the MQTT Spooler

Illustrative nucleus configuration snippet for MQTT 5 and disk spooler:

~~~json
{
  "mqtt": {
    "version": "mqtt5",
    "spooler": {
      "storageType": "Disk",
      "keepQos0WhenOffline": false
    },
    "minimumReconnectDelaySeconds": 1,
    "maximumReconnectDelaySeconds": 120
  }
}
~~~

This is an illustrative configuration for `aws.greengrass.Nucleus`. When deploying, apply a configuration update matching Greengrass deployment structure and verify the nucleus version on the device. Changing certain MQTT nucleus settings restarts the Greengrass Core software to take effect.

`maxSizeInBytes` configures the in-memory unprocessed message cache limit per nucleus documentation; do not treat it as the disk capacity limit for the Disk spooler.

### 5.4. Retries and Reconnects

With nucleus 2.10.0 or newer:

- `minimumReconnectDelaySeconds` defaults to 1 second.
- `maximumReconnectDelaySeconds` defaults to 120 seconds when using MQTT 5.
- When using MQTT 3, `maximumReconnectDelaySeconds` is ignored and the maximum is fixed at 128 seconds.
- `minimumConnectedTimeBeforeRetryResetSeconds` defaults to 30 seconds.

Flapping networks can cause continuous reconnects. Use backoff, avoid aggressive retries, and verify connection stability before resetting retry delays.

## 6. Local MQTT Broker and MQTT Bridge

Greengrass allows client devices to connect to the core device through a local MQTT broker. Devices such as sensors, cameras, or PLC gateways can send data to components for immediate on-site processing.

Common client-device components:

| Component | Role |
|---|---|
| `aws.greengrass.clientdevices.Auth` | Authenticates client devices and authorizes actions. |
| `aws.greengrass.clientdevices.mqtt.Moquette` | Local MQTT 3.1.1 broker. |
| `aws.greengrass.clientdevices.mqtt.EMQX` | Local MQTT 5 broker. |
| `aws.greengrass.clientdevices.mqtt.Bridge` | Relays messages between `LocalMqtt`, local `Pubsub`, and `IotCore`. |
| `aws.greengrass.clientdevices.IPDetector` | Publishes broker endpoints so client devices can discover the core device. |
| `aws.greengrass.ShadowManager` | Manages local shadows and synchronizes cloud shadows. |

Core devices require nucleus 2.2.0 or newer for client device support. EMQX MQTT 5 broker requires nucleus 2.6.0 or newer and compatible Client device auth. AWS recommends deploying only one MQTT broker component per core device unless explicitly justified and configured on separate ports.

### 6.1. Three Message Paths in the MQTT Bridge

The MQTT bridge can relay messages across:

- `LocalMqtt`: local broker for client devices.
- `Pubsub`: local Greengrass publish/subscribe for components.
- `IotCore`: AWS IoT Core MQTT broker.

Example configuration relaying messages from client devices to local components and the cloud:

~~~json
{
  "mqttTopicMapping": {
    "SensorToLocalComponent": {
      "topic": "factory/line1/telemetry",
      "source": "LocalMqtt",
      "target": "Pubsub"
    },
    "SensorToCloud": {
      "topic": "factory/line1/telemetry",
      "source": "LocalMqtt",
      "target": "IotCore"
    },
    "LocalAlarmToSensor": {
      "topic": "factory/line1/alarm",
      "source": "Pubsub",
      "target": "LocalMqtt"
    }
  }
}
~~~

When WAN drops, `LocalMqtt` → `Pubsub` and `Pubsub` → `LocalMqtt` routes keep running because they use local components only. Routes to `IotCore` cannot deliver while the cloud is unreachable; outbound messages follow MQTT spooler and bridge behavior.

The MQTT bridge uses QoS 1 when publishing/subscribing to AWS IoT Core, even if the client device used QoS 0 on the local broker. This can increase latency when relaying to the cloud.

### 6.2. Avoiding Message Loops

If bidirectional routes exist between `LocalMqtt` and `IotCore`, messages can bounce back to their origin and create loops. With an MQTT 5 bridge, you can configure `noLocal` on routes with source `LocalMqtt` to prevent relaying messages published by the bridge itself.

Design explicit topics, separate upstream/downstream prefixes, and test for loops in staging before rollout.

## 7. Authenticating Client Devices While Core Is Offline

Normally, the core device relies on the cloud to authenticate client devices. Greengrass supports offline authentication via the Client device auth component.

Key prerequisites:

- Client device auth component version 2.3.0 or newer.
- The client device must have authenticated and registered with AWS IoT while the core had cloud connectivity initially.
- The core device caches authenticated device credentials locally.
- When the core loses cloud connectivity, it uses cached credentials to authenticate previously connected client devices.

### 7.1. Offline Trust Duration

The `clientDeviceTrustDurationMinutes` parameter governs how long cached credentials/trust remain valid.

- Default: 1 minute, effectively disabling offline authentication.
- Configurable from 1 minute to 2,147,483,647 minutes.
- The core refreshes its credential store on initial client connection, on client reconnect while the core has cloud connectivity, and daily while the core is online.
- Only client devices associated with the core are refreshed via the corresponding API.

Do not set trust duration excessively long purely for convenience. Long durations increase the window where a client whose certificate was revoked continues being accepted by an offline core. Balance expected outage durations against security requirements.

### 7.2. Local Discovery and Limitations

Client devices can use cloud discovery to locate the core device. If a device lacks broker endpoint details, initial discovery may require cloud access. In offline environments, pre-provision endpoints or use a tested local discovery strategy.

Offline authentication only lets known clients connect to the core while the core cannot reach the cloud; it does not replace TLS, certificate lifecycle management, or MQTT topic authorization policies.

## 8. Local Publish/Subscribe via IPC

Greengrass components can exchange messages via local publish/subscribe IPC. This serves as a local message broker among components on the same core device.

Example:

- `sensor-ingest` publishes `factory/line1/telemetry`.
- `edge-rule-engine` subscribes to telemetry and emits alerts.
- `local-dashboard` subscribes to processed state.
- `cloud-exporter` reads data destined for the cloud.

Local IPC is not AWS IoT Core MQTT. To send messages to AWS IoT Core, a component must use the appropriate API/IPC or configure the MQTT bridge.

### 8.1. IPC Authorization

Components must be granted publish/subscribe permissions in their recipes. Condensed example policy:

~~~json
{
  "accessControl": {
    "aws.greengrass.ipc.pubsub": {
      "com.example.EdgeProcessor:pubsub:1": {
        "policyDescription": "Allow local telemetry topics",
        "operations": [
          "aws.greengrass#PublishToTopic",
          "aws.greengrass#SubscribeToTopic"
        ],
        "resources": [
          "factory/line1/telemetry",
          "factory/line1/alarm"
        ]
      }
    }
  }
}
~~~

Scope topics tightly per component. Do not grant access to all topics if a component only needs specific channels. The `*` wildcard in authorization resources differs from MQTT `#` or `+` wildcards; verify exact semantics for your nucleus version.

## 9. Stream Manager: Buffering Data at the Edge and Exporting When Online

Stream Manager is a component that manages data streams on a Greengrass core device. It fits high-volume telemetry, sensor data, time-series, batch uploads, or data requiring priority-ordered export.

Stream Manager allows:

- Writing data to local streams.
- Setting storage type, size, and retention policies per stream.
- Configuring export destinations.
- Tuning bandwidth and timeouts.
- Setting priorities so critical streams export first.
- Letting components read, filter, aggregate, and analyze data locally before uploading.

### 9.1. Store-and-Forward Workflow

~~~mermaid
flowchart LR
    S["Sensors / PLC"] --> C["Edge component"]
    C --> F["Filter / compress / enrich"]
    F --> SM["Stream Manager local storage"]
    SM --> L["Local analytics / control"]
    SM --> Q["Pending export queue"]
    Q -->|WAN restored| K["Kinesis Data Streams"]
    Q -->|WAN restored| S3["Amazon S3"]
    Q -->|WAN restored| SW["AWS IoT SiteWise"]
~~~

Components write data to Stream Manager using the Stream Manager SDK. Once connectivity returns, Stream Manager exports data according to configured destinations and policies.

### 9.2. Current AWS Cloud Destinations

Stream Manager supports exporting to:

- Amazon Kinesis Data Streams.
- Amazon S3 objects.
- AWS IoT SiteWise asset properties.

AWS IoT Analytics was discontinued on December 15, 2025; exporting to IoT Analytics channels no longer works. Never configure this destination for new projects, and remove legacy `IoTAnalyticsConfig` settings to avoid continuous export retry failures.

### 9.3. Configuring Stream Manager

Common parameters:

| Parameter | Meaning |
|---|---|
| `STREAM_MANAGER_STORE_ROOT_DIR` | Local directory storing streams; must exist with read/write permissions for the component user. |
| `STREAM_MANAGER_AUTHENTICATE_CLIENT` | Authenticates SDK clients; defaults to `true`, restricting access to Greengrass components. |
| `STREAM_MANAGER_EXPORTER_MAX_BANDWIDTH` | Average bandwidth cap for exports; defaults to using available bandwidth. |
| `STREAM_MANAGER_EXPORTER_THREAD_POOL_SIZE` | Maximum export threads; defaults to 5. |
| `STREAM_MANAGER_SERVER_PORT` | Stream Manager local port; defaults to 8088. |
| `STREAM_MANAGER_EXPORTER_KINESIS_INTER_CALL_DELAY_MS` | Fallback delay between Kinesis calls when shard layout is unknown; defaults to 1000 ms. |

Stream Manager requires a minimum of roughly 70 MB RAM on top of Greengrass Core software. Actual resource needs depend on stream count, throughput, and export concurrency.

### 9.4. Stream Manager Data Security

An important detail: Stream Manager does not encrypt stream data at rest or in transit between local components on the same core device by default.

- Local data relies on file permissions and full-disk encryption if enabled.
- Data exported to the AWS Cloud uses TLS.
- Client authentication is enabled by default (`true`); never disable it without clear justification.
- Store directories must have restricted access permissions.
- If changing `STREAM_MANAGER_STORE_ROOT_DIR`, Greengrass does not automatically delete the old directory or old data.

For sensitive data, enable full-disk encryption, isolate edge users/processes, and protect devices against unauthorized physical access.

## 10. Local Device Shadows and State Synchronization

Device Shadow is a JSON document holding `desired` and `reported` states. Greengrass Shadow Manager provides a local shadow service so components can read/write shadows on the core device even while disconnected from AWS IoT Core.

When cloud connectivity recovers, Shadow Manager synchronizes configured shadows with AWS IoT Core.

### 10.1. Shadows Are for State, Not Event Queues

Example:

- `desired`: motor target speed is 1200 RPM.
- `reported`: current motor speed is 1180 RPM.
- `metadata`: per-attribute timestamps.

If WAN drops, local components can still read cached desired state and update local reported state. Upon reconnecting, Shadow Manager syncs as configured.

Never use shadows to store every telemetry event. Shadows represent the latest state; if you need to preserve every event in sequence, use Stream Manager or a durable queue.

### 10.2. Synchronization Configuration

Shadow Manager does not sync every shadow to the cloud by default. You must configure synchronization and specify Thing/shadow names.

Available modes:

- `realTime`: synchronizes immediately as changes occur.
- `periodic`: synchronizes on an interval.
- `betweenDeviceAndCloud`: bidirectional.
- `deviceToCloud`: local state writes up to cloud.
- `cloudToDevice`: cloud state writes down to local.

With Shadow Manager v2.2.0 or newer, you can choose unidirectional synchronization. If both sides modify state while offline, conflicts are resolved according to Shadow Manager direction and version rules. In bidirectional sync, desired-state conflicts can prioritize cloud values while reported-state conflicts can prioritize local values per service behavior.

Choose synchronization direction based on each attribute's source of truth. For example, `desired` setpoints may be cloud-driven while `reported` temperature is device-owned.

## 11. Reconnecting and Synchronizing Once Connectivity Returns

When Internet access recovers, avoid having every device upload its entire backlog simultaneously. A large fleet can trigger a reconnect storm and exceed AWS IoT Core or target service quotas.

A recovery sequence should include:

1. Nucleus re-establishes the MQTT connection to AWS IoT Core.
2. Messages queued in the MQTT spooler retry as configured.
3. Stream Manager resumes exporting streams targeting cloud destinations.
4. Shadow Manager synchronizes local/cloud shadows.
5. Components resume calling AWS APIs once network and credentials are healthy.
6. Devices report health/status and backlog metrics.
7. Backends handle duplicates, late-arriving events, and business ordering.
8. Once backlogs drain, the system returns to normal ingestion rates.

### 11.1. Mitigating Reconnect Storms

- Use exponential backoff with jitter in custom exporters.
- Limit concurrent upload workers.
- Cap export bandwidth to match site uplink capacity.
- Prioritize alarms and critical events ahead of raw telemetry.
- Do not restart an entire component just because one cloud request timed out.
- Mark backlog items as sent only after receiving proper acknowledgements.
- Implement circuit breakers for persistently failing destinations.

### 11.2. Handling Duplicates and Ordering

QoS 1 and retries can produce duplicates. Attach to every event:

- `deviceId`.
- Unique `eventId`.
- Per-device or per-stream `sequenceNumber`.
- `eventTimestamp`.
- `schemaVersion`.
- `createdAt` and `ingestedAt`.

Cloud consumers must be idempotent: receiving the same `eventId` multiple times must apply only once. If business ordering matters, rely on `sequenceNumber` and handle gaps/reordering downstream rather than assuming arrival order after reconnect.

## 12. Storage Capacity and Backpressure

Offline durations can span hours or days. If a device generates data faster than it exports after reconnecting, the backlog will keep growing even after connectivity returns.

Basic storage estimate:

\[
Storage \approx IngressRate \times OfflineDuration \times SafetyFactor
\]

For example, a device producing 80 KB/s needing to survive a 6-hour outage:

\[
80 \times 3600 \times 6 = 1{,}728{,}000\text{ KB}
\]

This equals roughly 1.65 GiB of raw data. In practice, add overhead for metadata, file formats, retries, logs, and safety headroom.

### 12.1. Designing Near-Full Storage Policies

Define upfront:

- Which data must strictly be preserved.
- Which data can be downsampled or aggregated.
- Which data can be dropped if thresholds are exceeded.
- Export priority order.
- Maximum backlog retention window.
- Alerts when disk usage or queue depth crosses thresholds.
- Operator intervention procedures if uploads remain blocked.

For instance, machine fault alarms can keep high priority, periodic temperature telemetry can be downsampled when storage nears full, and raw camera frames can be dropped beyond retention.

Do not share a single queue across alarms, raw telemetry, and debug logs if they have different retention and priority requirements.

## 13. Security and Access Control in Offline Environments

Disconnection does not relax security requirements. Offline devices may miss timely certificate rotations, policy updates, or component security patches.

Best practices:

- Use unique device certificates for each core/client device.
- Scope `clientDeviceTrustDurationMinutes` to match outage SLAs.
- Revoke or rotate certificates per runbook once devices reconnect.
- Grant least-privilege IAM policies to the Greengrass device role.
- Restrict S3/Kinesis/SiteWise destinations to exact target resources.
- Use TLS for cloud communication.
- Enable full-disk encryption for Stream Manager data.
- Enforce local component authorization on IPC topics.
- Restrict local MQTT permissions by client group/topic.
- Protect Greengrass CLI and local debug consoles.
- Prevent components from creating local deployments that alter nucleus or sensitive components unnecessarily.
- Write local audit logs and ship logs when connectivity returns.

A component permitted to trigger local deployments or restart other components can alter device behavior without cloud involvement. Grant Greengrass CLI IPC permissions only to trusted administrative components.

## 14. Logging and Monitoring While Offline

Greengrass Core software writes logs by default to the local filesystem:

`/greengrass/v2/logs/greengrass.log`

Generic components normally write component-named logs in the same directory. While disconnected, local logging continues; when online, configure Log Manager to ship logs to CloudWatch Logs.

Metrics to monitor:

| Metric / Signal | Meaning |
|---|---|
| MQTT connection state | Whether core is connected to AWS IoT Core |
| Reconnect attempts | Reconnect frequency and outage duration |
| Spooler queue size | Count/bytes of queued messages |
| Spooler rejections | Messages dropped due to full cache |
| Stream Manager stream size | Backlog size per stream |
| Export lag | Delay from local write to successful export |
| Disk free space | Remaining disk space on the edge device |
| Component lifecycle | `RUNNING`, `ERRORED`, `BROKEN`, or `FINISHED` |
| Local deployment status | `QUEUED`, `IN_PROGRESS`, `SUCCEEDED`, or `FAILED` |
| Shadow sync lag | How far local/cloud shadows have synchronized |
| Client authentication failures | Clients rejected due to trust or authorization |
| Duplicate event rate | Duplicate ratio during replay/reconnect |

Configure alerts on offline duration, remaining disk space, rejected message counts, and backlog age. Do not alert solely when devices go offline; also alert when devices come back online without their backlogs draining.

## 15. Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Local components run, no cloud data arrives | WAN down or bridge disconnected from AWS IoT Core | Inspect nucleus logs, MQTT endpoint, DNS, firewall, and certificate |
| QoS 0 messages lost after outage | `keepQos0WhenOffline=false` | Use QoS 1 for required data or enable QoS 0 spooling if appropriate |
| Outbound messages rejected | Spooler cache full | Check `storageType`, capacity, export throughput, and retries |
| Disk spooler not working | Nucleus older than 2.11 or bad plugin/config | Verify nucleus version and `DiskSpooler` dependency |
| Client device fails to connect while core offline | Offline auth disabled or trust duration expired | Verify Client device auth >=2.3, credential cache, and device association |
| Client connects to broker but cannot publish | Authorization policy denies topic/action | Check device group and `mqtt:publish`/`mqtt:subscribe` permissions |
| Component does not receive client MQTT | Missing `LocalMqtt` → `Pubsub` bridge route | Verify `mqttTopicMapping` and local `Pubsub` subscription |
| MQTT bridge fails to push to cloud | WAN or IAM/device role failure | Check `IotCore` route, IoT policy, and cloud connection |
| Stream Manager export retries endlessly | Destination IAM, KMS, quota, or endpoint error | Verify role, target resource, local logs, and CloudWatch |
| Stream Manager cannot write stream | Disk permissions or missing store directory | Verify `STREAM_MANAGER_STORE_ROOT_DIR` and user permissions |
| Local and cloud shadows diverge | Concurrent edits during outage | Check sync direction and conflict resolution policy |
| Cloud deployment cannot apply offline | Missing local candidate/dependency/artifact | Stage local recipes/artifacts and create a local deployment |
| Component transitions to `BROKEN` | Repeated lifecycle failures | Inspect component logs, recover script, and dependencies |
| No logs in CloudWatch | Device offline or Log Manager/IAM unconfigured | Check local logs and verify log upload after reconnect |
| Backlog does not drain after reconnect | Ingress exceeds export rate or target throttling | Reduce ingress, raise export capacity, and adjust priorities |

### 15.1. Core Device Inspection Commands

Linux:

~~~bash
sudo systemctl status greengrass.service

sudo tail -n 100 /greengrass/v2/logs/greengrass.log

sudo /greengrass/v2/bin/greengrass-cli component list

sudo /greengrass/v2/bin/greengrass-cli deployment list
~~~

Inspect a specific component log:

~~~bash
sudo tail -f /greengrass/v2/logs/com.example.EdgeProcessor.log
~~~

On Windows, use PowerShell `Get-Content` to read log files under `C:\greengrass\v2\logs`.

## 16. Practical Scenario: Factory Gateway Loses Internet for 8 Hours

A factory operates a Greengrass gateway connected to:

- 12 PLCs reporting status every second.
- 30 temperature/pressure sensors.
- An edge component detecting overheating and issuing local machine stops.
- An analytics component aggregating production throughput.
- An exporter component sending data to Kinesis and S3.
- Shadow Manager synchronizing desired/reported state with the cloud.

### 16.1. Design While Online

- Client devices connect to the local MQTT broker.
- MQTT bridge forwards telemetry to local `Pubsub`.
- Edge processor reads `Pubsub` and evaluates business rules.
- Stream Manager records raw telemetry and alarm events.
- Alarm events carry higher priority than periodic telemetry.
- Shadow Manager synchronizes machine state.
- Exporter ships data to Kinesis/S3.

### 16.2. When Internet Drops

- PLCs keep sending data to the local MQTT broker.
- Edge processor continues threshold evaluation and local control.
- Local dashboard continues displaying live status.
- MQTT spooler buffers outbound MQTT messages per QoS and capacity.
- Stream Manager persists telemetry to local storage.
- Shadow Manager updates local reported state.
- Previously authenticated client devices keep connecting while trust duration holds.
- New cloud deployments and cloud API calls are interrupted.

### 16.3. When Internet Returns

1. Nucleus reconnects to AWS IoT Core.
2. MQTT spooler flushes queued messages.
3. Stream Manager exports alarms first, then telemetry by priority.
4. Shadow Manager reconciles desired/reported state.
5. Cloud consumers deduplicate by `eventId`.
6. Dashboard surfaces backlog age and replayed event counts.
7. Operators confirm zero rejected or storage-dropped events.

### 16.4. Acceptance Criteria

- Machines still shut down safely on over-temperature throughout the outage.
- Safety control loops never depend on cloud APIs.
- Zero alarm events lost during the outage per storage/retention SLAs.
- Duplicate events are processed idempotently.
- Shadow conflicts resolve according to source-of-truth rules.
- Backlog drains completely within target time after reconnect.
- Components restart cleanly after reboots without losing essential state.

## 17. Hands-On Lab: Simulating Offline and Reconnect

Goal: verify that a local component continues operating and buffered data uploads to the cloud once connectivity returns.

### Step 1: Prepare the Core Device

Install Greengrass Core software, deploy a telemetry-processing component, and deploy the local MQTT broker. Ensure components have all recipes/artifacts/dependencies staged.

### Step 2: Set Up the Local Message Path

Configure the MQTT bridge to relay from `LocalMqtt` to `Pubsub`. Write a component subscribing to the local topic and logging event IDs/timestamps.

### Step 3: Set Up Buffering

Configure the MQTT spooler appropriately. For high-volume streams, deploy Stream Manager and create a stream exporting to Kinesis or S3.

### Step 4: Cut WAN Access

Block Internet access on the core device in the test environment while keeping the LAN active between client devices and the core. Continue publishing telemetry and observe local processing.

### Step 5: Test Offline Authentication

If using client device auth, connect a client initially while the core is online. Configure trust duration in the test environment, disconnect WAN, and verify known clients can reconnect.

### Step 6: Test Local Deployment

Stage a new recipe/artifact on the device and create a local deployment. Confirm deployment status and component lifecycles.

### Step 7: Restore WAN Access

Re-enable Internet access. Monitor MQTT reconnects, spooler backlog, Stream Manager exports, and Shadow Manager synchronization.

### Step 8: Reconcile Data

Compare published event counts, locally stored counts, successfully exported counts, and duplicate counts. Verify `eventId`, `sequenceNumber`, and timestamps.

Never test network disconnects on a live production control system. Use lab hardware with independent physical safety mechanisms.

## 18. Common Misconceptions

1. **Greengrass offline means all AWS services keep working.** Only local capabilities and cached data continue; cloud APIs require network access.
2. **The local MQTT broker is identical to AWS IoT Core.** The local broker serves on-site client devices; AWS IoT Core is the cloud broker.
3. **The MQTT bridge buffers unlimited data automatically.** The bridge routes messages; the spooler has finite capacity.
4. **QoS 0 is always retained offline.** By default QoS 0 is dropped; `keepQos0WhenOffline=true` is required.
5. **QoS 1 guarantees exactly-once delivery.** QoS 1 is at-least-once; consumers must handle duplicates.
6. **Memory spooler suits long outages.** Default memory cache is only 2.5 MB.
7. **Disk spooler has unlimited capacity.** Disk space and filesystems remain bounded.
8. **Stream Manager works only online.** Stream Manager can store and process streams locally during outages.
9. **Shadow is a message queue.** Shadow represents the latest/desired state, not an ordered log of all events.
10. **Any client device can authenticate offline.** Clients must have authenticated before the core lost cloud access and stay within trust duration.
11. **Cloud deployments always apply offline.** Only pre-cached local candidates and artifacts can be used offline.
12. **Local deployments appear in the console.** Inspect local deployments using the Greengrass CLI on the device.
13. **Losing WAN stops all components.** Installed components with local dependencies continue running.
14. **Once connectivity returns, backlogs clear automatically without issues.** Capacity, retries, priorities, and idempotency are needed to prevent bottlenecks or duplicate side effects.
15. **Stream Manager local data is encrypted by default.** Local data at rest/in transit between components is not encrypted by default.
16. **Stream Manager can still export to AWS IoT Analytics.** AWS IoT Analytics was discontinued on December 15, 2025.

## 19. Self-Check Questions

**1. What role does Greengrass nucleus play?**

It is the mandatory runtime managing components, deployments, IPC, and cloud connectivity for Greengrass Core software.

**2. Do installed components keep running when Internet access is lost?**

Yes, provided the core device stays healthy and the components have their dependencies/artifacts locally.

**3. How do local deployments differ from cloud deployments?**

Local deployments run directly on the core device using local recipes/artifacts/candidates; cloud deployments are pushed from AWS IoT Greengrass Cloud via AWS IoT Jobs.

**4. When a cloud deployment arrives while a device is offline, what does nucleus do?**

Nucleus can use matching local candidates; if compatible candidates or dependencies are missing, the deployment fails.

**5. What does the MQTT spooler do?**

It buffers outbound MQTT messages that cannot yet reach AWS IoT Core so they can be retried once connectivity recovers.

**6. Is QoS 0 spooled by default?**

No. By default `keepQos0WhenOffline=false`.

**7. Can QoS 1 introduce duplicates?**

Yes. QoS 1 is at-least-once, so consumers require idempotency.

**8. Which version introduced Disk spooler?**

Greengrass nucleus 2.11.0 or newer.

**9. What prerequisites does client device offline authentication require?**

Client device auth >=2.3.0, prior client authentication while the core was online, and a valid remaining trust duration.

**10. What problem does Stream Manager solve?**

It buffers, enforces retention/priority, and exports IoT data streams from the edge once connectivity returns.

**11. Which cloud destinations does Stream Manager export to?**

Amazon Kinesis Data Streams, Amazon S3, and AWS IoT SiteWise.

**12. Why shouldn't Device Shadow be used as a telemetry queue?**

Shadow stores only the latest state; it is not designed to persist every event in sequence.

**13. Does local Pubsub send directly to AWS IoT Core?**

No. You need an MQTT bridge or appropriate IPC/API integration to forward messages to the cloud.

**14. What happens when Stream Manager local storage fills up?**

Applications can no longer assume new data is persisted; capacity alerts and overflow policies must be designed upfront.

**15. When is a local deployment needed?**

When installing/updating components on-site without cloud connectivity, provided recipes/artifacts/dependencies are staged locally.

**16. Why is idempotency required after reconnecting?**

Messages can be retried or replayed multiple times; idempotency ensures the same event never triggers duplicate business side effects.

## 20. Production Checklist

- [ ] Outage scenarios are classified: WAN, AWS IoT Core, LAN, client device, or core hardware.
- [ ] Local control paths do not depend on cloud APIs.
- [ ] Core device has sufficient CPU, RAM, disk, and auto-restarting system services.
- [ ] Required component recipes/artifacts/dependencies are available locally.
- [ ] Component lifecycles and recover scripts are tested.
- [ ] Cloud and local deployments follow a coordinated governance process.
- [ ] MQTT spooler storage mode and capacity match outage SLAs.
- [ ] QoS 0 and QoS 1 behaviors are explicitly defined.
- [ ] Duplicate handling via `eventId`/idempotency is implemented.
- [ ] Reconnects use backoff and prevent reconnect storms.
- [ ] Local MQTT broker and MQTT bridge have explicit topic mappings.
- [ ] Client device auth uses an appropriate trust duration and pre-provisioned clients.
- [ ] IPC authorization scopes topics per component.
- [ ] Stream Manager configures local storage, retention, priority, and export targets.
- [ ] Alerts monitor disk usage, spooler backlog, and export lag.
- [ ] AWS IoT Analytics is not configured as a Stream Manager destination.
- [ ] Shadow Manager syncs exact shadow names, directions, and conflict policies.
- [ ] Stream Manager local data is protected by file permissions/full-disk encryption.
- [ ] Greengrass CLI/local debug consoles have restricted access.
- [ ] Local logs have adequate retention space and ship on reconnect.
- [ ] Runbooks cover inspecting nucleus, components, deployments, spooler, and Stream Manager.
- [ ] WAN outages, reboots, reconnects, backlog replays, and duplicate events are tested.
- [ ] Acceptance criteria exist for data loss, recovery time, and backlog drain time.

## References

- [How AWS IoT Greengrass works](https://docs.aws.amazon.com/greengrass/v2/developerguide/how-it-works.html)
- [Greengrass nucleus component](https://docs.aws.amazon.com/greengrass/v2/developerguide/greengrass-nucleus-component.html)
- [Configure the AWS IoT Greengrass Core software](https://docs.aws.amazon.com/greengrass/v2/developerguide/configure-greengrass-core-v2.html)
- [Resilience in AWS IoT Greengrass](https://docs.aws.amazon.com/greengrass/v2/developerguide/disaster-recovery-resiliency.html)
- [Develop AWS IoT Greengrass components](https://docs.aws.amazon.com/greengrass/v2/developerguide/develop-greengrass-components.html)
- [AWS IoT Greengrass component recipe reference](https://docs.aws.amazon.com/greengrass/v2/developerguide/component-recipe-reference.html)
- [Deploy AWS IoT Greengrass components to devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/manage-deployments.html)
- [Local deployment with Greengrass CLI](https://docs.aws.amazon.com/greengrass/v2/developerguide/gg-cli-deployment.html)
- [Manage local deployments and components with IPC](https://docs.aws.amazon.com/greengrass/v2/developerguide/ipc-local-deployments-components.html)
- [Configure MQTT timeouts and cache settings](https://docs.aws.amazon.com/greengrass/v2/developerguide/configure-greengrass-core-v2.html)
- [Authenticate clients while offline](https://docs.aws.amazon.com/greengrass/v2/developerguide/offline-authentication.html)
- [Connect client devices to core devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/connect-client-devices.html)
- [Interact with local IoT devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/interact-with-local-iot-devices.html)
- [MQTT bridge component](https://docs.aws.amazon.com/greengrass/v2/developerguide/mqtt-bridge-component.html)
- [Publish/subscribe local messages](https://docs.aws.amazon.com/greengrass/v2/developerguide/ipc-publish-subscribe.html)
- [Manage data streams on Greengrass core devices](https://docs.aws.amazon.com/greengrass/v2/developerguide/manage-data-streams.html)
- [Configure AWS IoT Greengrass Stream Manager](https://docs.aws.amazon.com/greengrass/v2/developerguide/configure-stream-manager.html)
- [Use StreamManagerClient to work with streams](https://docs.aws.amazon.com/greengrass/v2/developerguide/work-with-streams.html)
- [Interact with device shadows](https://docs.aws.amazon.com/greengrass/v2/developerguide/interact-with-shadows.html)
- [Sync local device shadows with AWS IoT Core](https://docs.aws.amazon.com/greengrass/v2/developerguide/sync-shadows-with-iot-core.html)
- [Monitor AWS IoT Greengrass logs](https://docs.aws.amazon.com/greengrass/v2/developerguide/monitor-logs.html)
- [Troubleshooting AWS IoT Greengrass V2](https://docs.aws.amazon.com/greengrass/v2/developerguide/troubleshooting.html)
