# Device Shadow and Device State Synchronization

AWS IoT Device Shadow is an AWS IoT Core service that stores device state as a JSON document in the cloud. Applications can read a device's latest state and write a desired state even when the device is disconnected. When the device reconnects, it reads the difference between the desired state and its reported state, applies the appropriate changes, and updates its actual reported state.

Device Shadow decouples the application lifecycle from device network connectivity. A dashboard can ask a thermostat to set the temperature to 24°C without requiring the device to be online; the device can pick up the request once it reconnects. AWS IoT persists the current state and emits notifications when changes occur. The device and application still need to coordinate execution, confirmation, and conflict handling.

Within the AWS ecosystem, Device Shadow is part of AWS IoT Core. It integrates with Thing Registry, MQTT, X.509 certificates, IoT policies, IAM, AWS IoT Rules Engine, Lambda, and Fleet Indexing. This lesson focuses on designing the desired/reported model, bidirectional synchronization, version management, named shadow separation, topic security, and operating device fleets at scale.

## 1. Learning Objectives

After this lesson, learners will be able to:

- Explain Device Shadow and its role in IoT architecture.
- Distinguish between Thing, device, shadow document, and MQTT messages.
- Explain the meaning of `desired`, `reported`, and `delta`.
- Design synchronization flows when devices are online, offline, and reconnecting.
- Interpret `metadata`, `timestamp`, `version`, and `clientToken` fields.
- Update shadows using MQTT reserved topics or HTTPS APIs.
- Distinguish classic shadows from named shadows.
- Handle update conflicts, out-of-order messages, and duplicate notifications.
- Design ownership conventions between cloud applications and firmware.
- Secure shadows with X.509 certificates, AWS IoT policies, and least-privilege IAM.
- Combine Device Shadow with IoT Rules Engine, Fleet Indexing, and Device Management Jobs.
- Evaluate payload, request rate, and in-flight request limits.
- Establish procedures for testing, monitoring, and troubleshooting synchronization errors.

## 2. What Problem Does Device Shadow Solve?

An IoT device may experience intermittent connectivity due to:
- Wi-Fi, cellular, or Internet outages.
- Weak signal coverage.
- Gateway or router reboots.
- Power-saving sleep cycles where the device wakes periodically.
- Firmware updates or device reboots.
- MQTT connection drops due to network issues or maintenance.

If an application only sends commands directly to an MQTT topic while the device is offline, the device may miss that request. The application would have to manage connection state, retries, command storage, resynchronization, and conflict resolution itself.

Device Shadow provides a shared state store:
- The application writes the desired state to the cloud.
- AWS IoT stores that state in the shadow document.
- The device can read the shadow upon reconnecting.
- AWS IoT calculates the difference between `desired` and `reported`.
- The device applies changes and reports its actual state.

For example, a thermostat is offline. A user changes the target temperature from 26°C to 24°C. The application writes `desired.setpoint = 24` to the shadow. When the device reconnects, it reads the delta, adjusts the controller, and writes `reported.setpoint = 24` after verifying the state.

Device Shadow is useful when applications need to know **the latest state desired by the cloud and the most recent state reported by the device**. It is not a historical log of every command, a job queue, or a time-series telemetry store.

## 3. Thing, Device, and Shadow Document

In AWS IoT Core:
- **Thing** is a logical object representing a device or asset in the AWS IoT Registry.
- **Device** is the physical hardware/firmware connecting to AWS IoT Core.
- **Shadow** is a JSON document stored by AWS IoT for a Thing.
- **Shadow document** is the state representation containing `desired`/`reported` and metadata.
- **MQTT client** is the software component on the device or application that publishes/subscribes with AWS IoT Core.

A Thing can have certificates and policies attached for authentication and connection authorization. Thing Registry stores asset identity and attributes. A shadow is a separate state resource; it does not automatically synchronize with Thing Registry attributes or arbitrary MQTT payloads.

A Thing does not have a shadow until one is created. It can be created via the AWS IoT console, an MQTT update, or the Device Shadow API. For a classic shadow, a `get` request before the shadow exists returns `get/rejected`; the device can create the shadow by sending an initial update with its `reported` section. For a named shadow, the corresponding named shadow must be created before reading.

A single Thing can simultaneously have one classic shadow and multiple named shadows. Each shadow is independent of the others. If a device uses multiple shadows, firmware must clearly define the data source and synchronization logic for each shadow to avoid reporting conflicting states.

## 4. Three State Sections: Desired, Reported, and Delta

This is the core model of Device Shadow.

| Section | Typically Updated By | Meaning |
|---|---|---|
| `desired` | Cloud applications, backend, or operators | The state the system wants the device to reach |
| `reported` | Firmware/device | The state the device is currently reporting |
| `delta` | Calculated by AWS IoT | Attributes where `desired` differs from `reported` |

Example shadow document:

~~~json
{
  "state": {
    "desired": {
      "power": "ON",
      "setpoint": 24,
      "mode": "COOL"
    },
    "reported": {
      "power": "ON",
      "setpoint": 26,
      "mode": "COOL"
    },
    "delta": {
      "setpoint": 24
    }
  },
  "version": 18,
  "timestamp": 1795161600
}
~~~

In this example:
- The cloud wants a target temperature of 24°C.
- The device is reporting 26°C.
- The `power` and `mode` attributes already match.
- AWS IoT includes only `setpoint` in `delta`.

Delta is a virtual state computed from `desired` and `reported`. Clients do not send `delta` to update a shadow. Once `desired` and `reported` match, the corresponding `delta` disappears.

### 4.1 Ownership Convention

An easy-to-operate convention is:

- Cloud applications update only `desired` when requesting device changes.
- Firmware updates only `reported` after observing or achieving actual state.
- AWS IoT computes `delta`.
- Backends read `reported` to display device state and verify request fulfillment.

Avoid letting multiple components write the same attribute into both `desired` and `reported` without clear conventions. For example, the backend should not write `reported.temperature` as if it were a real sensor reading if it did not receive that data from the device.

### 4.2 Delta Is Not a Command Queue

Delta only represents the current difference. If the cloud updates `desired` multiple times while the device is offline, the shadow retains only the latest desired state. Intermediate values do not form an ordered command queue to execute sequentially.

Example:
1. Cloud sets `setpoint = 24`.
2. Cloud later changes it to `22`.
3. Device reconnects and reads the shadow.

The device should converge to 22°C. There is no built-in guarantee or requirement that the device execute 24°C followed by 22°C sequentially.

If every command must be executed exactly once with progress tracking, deadlines, retries, and individual results, use AWS IoT Device Management Jobs or a dedicated command/job system.

## 5. Shadow Document Structure

A basic request document:

~~~json
{
  "state": {
    "desired": {
      "power": "ON",
      "setpoint": 24
    }
  },
  "clientToken": "web-req-00042",
  "version": 17
}
~~~

Inside `state`, the service persists fields under `desired` and `reported`. Custom application fields placed outside those two sections are not persisted as state. In standard designs, each request updates only `desired` or `reported` to preserve clear ownership between cloud and firmware.

Key attributes:

| Attribute | Purpose |
|---|---|
| `state.desired` | Desired values from the cloud |
| `state.reported` | Values reported by the device |
| `state.delta` | Difference calculated by the service in responses |
| `metadata` | Per-attribute timestamps inside `state` |
| `timestamp` | Time AWS IoT generated the response document |
| `version` | Shadow document version |
| `clientToken` | Value used to correlate requests with responses |

`metadata` is generated automatically by AWS IoT. It contains timestamps for each attribute in `desired`/`reported`, helping clients determine when an attribute was last updated. Metadata does not count toward the state document size limit.

`timestamp` in the response is when AWS IoT generated the message, not the exact clock reading of when the device performed the action. When device measurement time is needed, firmware should report a separate field such as `lastMeasuredAt` or `deviceUptime`.

`clientToken` is a client-provided string to match responses with pending requests. It is helpful in MQTT because multiple requests can be in flight over the same connection. `clientToken` does not replace `version` and should not be treated as an automatic idempotency key.

`version` increments after each successful shadow update. Clients can use `version` to detect stale data and avoid overwriting newer state.

## 6. Partial Updates and JSON Rules

Shadow updates are typically partial updates. Clients send only the fields they want to change; other fields remain untouched.

Suppose the shadow currently holds:

~~~json
{
  "state": {
    "desired": {
      "power": "ON",
      "setpoint": 24,
      "mode": "COOL"
    }
  }
}
~~~

The application sends:

~~~json
{
  "state": {
    "desired": {
      "setpoint": 22
    }
  }
}
~~~

After the update, `power` remains `ON`, `mode` remains `COOL`, and `setpoint` changes to `22`. There is no need to resend the entire `desired` state.

### 6.1 Deleting an Attribute

Set an attribute's value to `null` to delete it from that state section:

~~~json
{
  "state": {
    "desired": {
      "schedule": null
    }
  }
}
~~~

This is a key-deletion operation, not storing a JSON `null` value as a normal state field.

### 6.2 Arrays Are Treated as Single Values

Arrays are compared as whole values. If the `desired` array differs from the `reported` array, the entire `desired` array appears in `delta`. Individual array elements cannot be patched via shadow merge semantics.

Example:

~~~json
{
  "state": {
    "desired": {
      "allowedModes": ["AUTO", "COOL"]
    }
  }
}
~~~

To change a list, send the entire updated array. For long lists or elements requiring independent updates, consider an object keyed by stable identifiers instead of an array.

### 6.3 Nested Objects

Nested objects are compared field by field. If only one nested property differs, `delta` may contain only the path to that property.

Example `desired`:

~~~json
{
  "lights": {
    "color": {
      "r": 255,
      "g": 255,
      "b": 255
    }
  }
}
~~~

`reported`:

~~~json
{
  "lights": {
    "color": {
      "r": 255,
      "g": 0,
      "b": 255
    }
  }
}
~~~

Delta:

~~~json
{
  "lights": {
    "color": {
      "g": 255
    }
  }
}
~~~

Keep the schema stable and avoid deep object nesting. AWS IoT enforces a maximum nesting depth on `desired`/`reported` state documents.

## 7. Classic Shadow vs. Named Shadow

AWS IoT supports two shadow types:

| Type | Characteristics | When to Use |
|---|---|---|
| Classic/unnamed shadow | Each Thing can have at most one classic shadow | Devices with a small, simple group of states |
| Named shadow | A Thing can have multiple named shadows | Need to separate multiple state groups or access permissions |

For example, a gateway device could have:
- `configuration`: network settings and sampling interval.
- `climate`: target temperature, HVAC mode.
- `maintenance`: maintenance state and diagnostic info.

Named shadows help organize data by concern. They can also help apply distinct policies per data group, such as allowing a configuration service to write only `configuration` while an operations app only reads `maintenance`.

Named shadows do not create security boundaries automatically. You must author IoT policies restricting the exact Thing, shadow name, and topic actions. If every client has wildcard access across all named shadows, authorization isolation is lost.

If the system is likely to grow into multiple state domains, consider named shadows from the outset. Classic shadow is simpler, but provides only one unnamed state namespace per Thing.

## 8. MQTT Reserved Topics

Devices typically interact with Device Shadow over MQTT. Each operation has a request topic, an accepted response topic, and a rejected response topic.

### 8.1 Topic Prefix

Classic shadow:

~~~text
$aws/things/thermostat-01/shadow
~~~

Named shadow:

~~~text
$aws/things/thermostat-01/shadow/name/climate
~~~

After the prefix, append a topic suffix such as `/get`, `/update`, or `/delete`.

### 8.2 Main Topics

| Topic Suffix | Direction | Meaning |
|---|---|---|
| `/get` | Publish | Request to read the current shadow |
| `/get/accepted` | Subscribe | Returns the shadow document |
| `/get/rejected` | Subscribe | GET request was rejected |
| `/update` | Publish | Send a partial state update |
| `/update/accepted` | Subscribe | Update was accepted |
| `/update/rejected` | Subscribe | Update was rejected |
| `/update/delta` | Subscribe | `desired` and `reported` differ |
| `/update/documents` | Subscribe | Notification with documents before/after update |
| `/delete` | Publish | Delete the shadow |
| `/delete/accepted` | Subscribe | Deletion succeeded |
| `/delete/rejected` | Subscribe | Deletion was rejected |

For the `climate` named shadow of Thing `thermostat-01`, the update topic is:

~~~text
$aws/things/thermostat-01/shadow/name/climate/update
~~~

The corresponding delta topic:

~~~text
$aws/things/thermostat-01/shadow/name/climate/update/delta
~~~

Topics are case-sensitive. You must match the exact Thing name and shadow name.

### 8.3 Subscribe Before Publishing

MQTT is publish/subscribe. Clients should subscribe to response topics before sending a request. Publishing a request prior to subscribing can cause the client to miss the response.

Example GET flow:
1. Subscribe to `/get/accepted`.
2. Subscribe to `/get/rejected`.
3. Publish an empty payload to `/get`.
4. Receive the response on one of the two topics.

For updates, subscribe at minimum to `/update/accepted` and `/update/rejected`; devices needing cloud requests must also subscribe to `/update/delta`.

Do not subscribe with broad wildcards like `$aws/things/thermostat-01/shadow/#`. AWS may introduce new topics under reserved topic structures. Subscribe only to the exact topics the client uses.

### 8.4 Deleting a Shadow

The client publishes an empty payload to `/delete` and waits on `/delete/accepted` or `/delete/rejected`. Deleting a shadow removes the current state document; it does not reset `version` to 0. A deleted shadow document cannot be recovered by calling GET. Before deleting, confirm the Thing no longer depends on the shadow and that any required audit/backup has been saved externally.

## 9. Cloud-to-Device Synchronization Flow

Suppose the cloud requests the thermostat to set 24°C and `COOL` mode.

### Step 1: Cloud Updates Desired

The cloud application sends:

~~~json
{
  "state": {
    "desired": {
      "setpoint": 24,
      "mode": "COOL"
    }
  },
  "clientToken": "dashboard-req-1001"
}
~~~

The request is published to the shadow's `/update` topic or sent via `UpdateThingShadow` over the HTTPS API.

### Step 2: AWS IoT Updates the Shadow

If the request is valid:
- AWS IoT stores the new `desired` state.
- `version` increments.
- Field `metadata` is updated.
- AWS IoT publishes to `/update/accepted`.
- If `desired` differs from `reported`, AWS IoT publishes to `/update/delta`.

`/update/accepted` confirms the shadow persisted the update. It does not prove the device physically executed the action.

### Step 3: Device Receives Delta

The device receives the delta payload, for example:

~~~json
{
  "state": {
    "setpoint": 24,
    "mode": "COOL"
  },
  "metadata": {
    "setpoint": {
      "timestamp": 1795161600
    },
    "mode": {
      "timestamp": 1795161600
    }
  },
  "version": 18,
  "timestamp": 1795161600
}
~~~

Firmware checks the version, validates the values, and applies the configuration. Never apply a `desired` value blindly. For instance, the device may reject a setpoint outside safe operating bounds or an unsupported mode.

### Step 4: Device Reports Actual State

After applying and verifying, the device sends:

~~~json
{
  "state": {
    "reported": {
      "setpoint": 24,
      "mode": "COOL"
    }
  },
  "clientToken": "device-report-501"
}
~~~

AWS IoT updates `reported`. When `desired` and `reported` match, the corresponding `delta` clears.

### Step 5: Application Confirms State

The dashboard reads `reported` to show that the device applied the configuration. If the device cannot comply, firmware can report a separate error state, such as `applyStatus = REJECTED` and `lastError = SETPOINT_OUT_OF_RANGE`.

Do not treat `update/accepted` as proof the device succeeded. Execution confirmation must come from `reported` state or a dedicated job workflow.

## 10. Synchronization During Offline and Reconnect

A key strength of Device Shadow is that applications can update `desired` while a device is offline. AWS IoT persists the latest desired state. When the device reconnects, it can fetch cloud state to converge.

Recommended reconnect workflow:

1. Connect to AWS IoT Core using valid certificates/credentials.
2. Subscribe to response topics and delta topics supported by firmware.
3. Publish `/get` to fetch the latest shadow document.
4. On `/get/accepted`, inspect `desired`/`reported`, `version`, and `delta`.
5. If no shadow exists yet and `/get/rejected` indicates it is missing, create the shadow by sending a `reported` update with current device state.
6. Apply any `desired` differences from `reported` per firmware logic.
7. Publish `reported` after confirming actual state.
8. Continue processing incoming deltas while connected.

Flow diagram:

~~~text
Cloud application
      |
      | Update desired while device offline
      v
AWS IoT Device Shadow
      |
      | Device reconnects
      v
Subscribe response topics
      |
      v
GET current shadow
      |
      v
Compare desired and reported
      |
      v
Apply safe changes on device
      |
      v
Publish reported state
      |
      v
Delta becomes empty for matched fields
~~~

Do not assume a device will receive every delta published while offline. MQTT notifications can be missed when disconnected; the current shadow document is the authoritative source for resynchronization.

If `desired` changed multiple times while offline, the device should converge to the latest desired state. If business rules require sequential execution of every intermediate command, use a separate queue/job mechanism rather than relying on delta.

## 11. Versioning and Update Conflict Resolution

Shadow documents have a `version`. Every successful update increments `version`. Clients can include the current `version` in a request so the update succeeds only if the document has not been modified by another client.

For example, a client reads shadow version 18. Before it writes, another app updates the shadow to version 19. If the client sends an update with version 18, AWS IoT rejects it due to stale version.

Handling workflow:
1. Receive `/update/rejected` or an HTTP conflict error.
2. Inspect the error code/message.
3. GET the latest shadow.
4. Recompute changes against the fresh state.
5. Submit the update with the new version if read-modify-write protection is needed.
6. Use backoff with jitter when multiple clients contend.

Example versioned update:

~~~json
{
  "state": {
    "desired": {
      "setpoint": 22
    }
  },
  "version": 19,
  "clientToken": "dashboard-req-1002"
}
~~~

If an application updates an independent field without depending on previously read data, an unversioned partial update may suffice. When an operation relies on prior read state, include `version` to prevent overwriting another client's newer decision.

### 11.1 Out-of-Order Messages

Due to network conditions and asynchronous delivery, a device may receive an older-version message after a newer-version message. Devices should track the highest processed version and ignore notifications with lower versions.

If versions jump or the device suspects missed messages, call GET to retrieve a fresh snapshot. Do not try to reconstruct state solely from a potentially incomplete stream of delta messages.

### 11.2 clientToken

`clientToken` helps applications correlate responses with pending requests. Each outstanding request should have a distinct token to simplify log correlation.

Do not use `clientToken` as a substitute for `version`. Tokens identify requests; versions protect state consistency.

## 12. REST API vs. MQTT: Choosing the Access Method

AWS IoT Device Shadow can be accessed via:
- MQTT reserved topics.
- HTTPS REST API.
- AWS SDK or AWS CLI wrapping the corresponding APIs.

| Criterion | MQTT | HTTPS/SDK |
|---|---|---|
| Typical callers | Firmware/devices and real-time apps | Backend services, admin tools, automation |
| Model | Publish/subscribe, topic-based request/response | API request/response |
| Connection | Persistent MQTT connection | HTTP request |
| Delta notifications | Subscribe to `/update/delta` | Backend can subscribe via MQTT or use appropriate integrations |
| Common auth | X.509 certificates and AWS IoT policies | AWS credentials/IAM with SigV4 |
| Best suited for | Devices needing persistent connections and live state updates | Backends reading/writing shadows via API |

Common APIs:
- `GetThingShadow`: retrieve a shadow document.
- `UpdateThingShadow`: update a shadow document.
- `DeleteThingShadow`: delete a shadow.
- `ListNamedShadowsForThing`: list named shadows for a Thing.

`ListNamedShadowsForThing` lists named shadows; the classic shadow has no name and therefore does not appear as a named shadow.

Whether using MQTT or HTTPS, `desired`/`reported`, `delta`, and `version` semantics remain identical. Choose the protocol based on where the client runs and its connectivity pattern.

## 13. Security and Authorization

Device Shadow holds device configuration and state. Any principal permitted to write `desired` can alter device behavior; therefore, strictly control who can update versus only read.

### 13.1 Device Authentication

Devices typically connect to AWS IoT Core using X.509 certificates. Certificates are registered, activated, and attached to Things/policies under the device management model.

Principles:
- Use a unique certificate per device or tightly scoped identity.
- Protect private keys in a secure element/TPM if supported by hardware.
- Maintain certificate rotation/revocation procedures.
- Never share a private key across the fleet.
- Bind certificates properly to Thing identities.
- Always use TLS when connecting.

### 13.2 AWS IoT Policy for MQTT

IoT policies govern publish, subscribe, and receive on MQTT topics. Three common actions:

| Action | Resource Type | Purpose |
|---|---|---|
| `iot:Publish` | `topic` | Allows sending requests to `/get`, `/update`, `/delete` |
| `iot:Subscribe` | `topicfilter` | Allows subscribing to response/delta topics |
| `iot:Receive` | `topic` | Allows receiving messages from subscribed topics |

Example narrow policy for a thermostat device:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "iot:Connect",
      "Resource": "arn:aws:iot:ap-southeast-1:123456789012:client/thermostat-01"
    },
    {
      "Effect": "Allow",
      "Action": "iot:Publish",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/get",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/update"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Subscribe",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/get/accepted",
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/get/rejected",
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/update/delta",
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/update/accepted",
        "arn:aws:iot:ap-southeast-1:123456789012:topicfilter/$aws/things/thermostat-01/shadow/name/climate/update/rejected"
      ]
    },
    {
      "Effect": "Allow",
      "Action": "iot:Receive",
      "Resource": [
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/get/accepted",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/get/rejected",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/update/delta",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/update/accepted",
        "arn:aws:iot:ap-southeast-1:123456789012:topic/$aws/things/thermostat-01/shadow/name/climate/update/rejected"
      ]
    }
  ]
}
~~~

This is an illustrative example; substitute Region, account, Thing name, and MQTT client ID for your environment (the example above uses client ID `thermostat-01`). Policies authorize by MQTT topic, not by inspecting keys inside JSON payloads. Because both `desired` and `reported` use `/update`, publishing to that topic cannot be restricted to `reported`-only via IoT policy alone. Enforce the convention that firmware sends only `reported` and backend writes only `desired`, validate payloads at the application layer, and use a separate IAM role for backend HTTPS API calls. If stronger edge enforcement is needed, add an authentication/authorization or validation layer rather than relying on topic policies to distinguish JSON fields.

### 13.3 IAM for the HTTPS API

Backends call the Device Shadow REST API using AWS credentials and IAM policies. Separate backend permissions from device MQTT certificate permissions. AWS IoT policies and IAM policies are distinct authorization systems; configuring one does not grant permissions in the other.

### 13.4 Least-Privilege Principles

- By convention, firmware publishes only `reported`; policies constrain which topics firmware can publish/subscribe.
- Backends can configure `desired` only for authorized Thing groups.
- Only a dedicated admin role may delete shadows.
- Named shadows are scoped by exact name.
- Never grant wildcards across all Things if a service manages only one device group.
- Never subscribe to `$aws/things/THING/shadow/#` by default.
- Periodically review certificates, policy attachments, and access permissions.

## 14. Integration with Other AWS Services

Device Shadow is usually one part of a broader IoT architecture.

### 14.1 AWS IoT Rules Engine

Rules Engine can read MQTT messages and forward events to AWS services. For example:
- Listen to `update/documents` to record audit events.
- Listen to `update/delta` to detect new configuration changes.
- Republish a condensed payload to an application topic.
- Invoke Lambda to evaluate business rules or send notifications.
- Write event data to Kinesis, S3, or analytics pipelines by design.

Avoid logging every shadow message as telemetry if only the latest state is needed. If full history is required, define a dedicated event schema and retention policy.

### 14.2 AWS Lambda and Backend Services

Lambda functions or services on ECS/EC2 can use the AWS SDK to:
- Read shadows before sending configurations.
- Update `desired`.
- Validate versions.
- Inspect `reported`.
- Handle dashboard or API requests.

Backends should implement business-layer idempotency, write audit logs, and verify user authorization before writing `desired`.

### 14.3 Fleet Indexing

AWS IoT Fleet Indexing indexes data from Thing Registry, Device Shadow, connectivity, and related fleet sources. Backends can search and aggregate by device attributes, state, or group.

Examples:
- Find devices with an outdated `reported.firmwareVersion`.
- Find devices with `reported.temperature` exceeding thresholds.
- Find devices where `desired` and `reported` have not converged.
- Aggregate state by Thing Group or device type.

Fleet Indexing suits fleet queries. It does not replace shadow schema design, authorization, or a dedicated telemetry data store.

### 14.4 AWS IoT Device Management Jobs

Use Device Shadow for current state such as:
- Target configuration.
- Operating mode.
- Currently reported firmware version.
- Connection state or latest error.

Use Device Management Jobs for tasks requiring progress and outcome tracking:
- OTA firmware updates.
- Running maintenance tasks.
- Executing migrations.
- Installing packages.
- Performing actions with queued/in-progress/succeeded/failed states.

Shadow represents current desired state; Jobs represents work to be executed and tracked.

## 15. Designing the Shadow Schema

Shadow documents have size limits, so store only attributes that require synchronization. Do not treat a shadow as a replica of the entire device database.

Example schema for an HVAC unit:

~~~json
{
  "state": {
    "desired": {
      "control": {
        "power": "ON",
        "mode": "COOL",
        "setpointC": 24
      },
      "sampling": {
        "intervalSeconds": 60
      }
    },
    "reported": {
      "control": {
        "power": "ON",
        "mode": "COOL",
        "setpointC": 24
      },
      "sampling": {
        "intervalSeconds": 60
      },
      "telemetry": {
        "lastKnownTemperatureC": 25.4,
        "lastKnownHumidityPercent": 61
      },
      "firmwareVersion": "2.4.1",
      "applyStatus": "SUCCEEDED"
    }
  }
}
~~~

Design guidelines:
- Use stable, self-explanatory field names.
- Choose consistent data types.
- Include explicit units in field names or the schema.
- Separate desired configuration from measurement data.
- Never store long telemetry histories in shadows.
- Never store secrets, private keys, passwords, or unnecessary sensitive data.
- Limit field count and object nesting depth.
- Define a schema version convention if firmware and backend evolve independently.

### 15.1 Schema Evolution

Older firmware may not understand new fields. Backends may need to roll out configurations by device version.

Best practices:
- Add fields in a backward-compatible manner.
- Never change the meaning of existing fields.
- Use `configSchemaVersion` or `desiredConfigVersion` when needed.
- Have devices ignore unsupported fields and report status clearly.
- Send only configurations that the target firmware version understands.
- Test old firmware, new firmware, and rollback scenarios.

### 15.2 Separating State and Telemetry

Shadows store the latest state, not time-series history. You may keep a few latest summary values such as `lastKnownTemperatureC` if meaningful for device status. If a device measures temperature every second, writing every sample to the shadow generates excessive updates, increases load, and discards prior sample history.

A sound architecture:
- Shadow: setpoint, mode, last known status, firmware version.
- MQTT telemetry topic: temperature, humidity, voltage, vibration.
- IoT Rules Engine: routes telemetry to Kinesis, Timestream, S3, or analytics pipelines.
- Fleet Indexing: queries fleet state.
- CloudWatch: operational service logs and metrics.

## 16. Limits and Quotas to Design For

Per current AWS IoT Core quotas, notable Device Shadow limits include:

| Limit | Published Default | Notes |
|---|---:|---|
| Size per JSON shadow state document | 8 KB | Adjustable; metadata does not count toward size |
| `desired`/`reported` nesting depth | 8 levels | Not adjustable |
| Shadow name | 64 bytes UTF-8 | Not adjustable |
| Thing name | 128 bytes UTF-8 | Per Thing limit |
| Request rate per shadow | 20 requests/second | Adjustable |
| Account shadow API request rate | 4,000 requests/second | Some Regions default to 400; adjustable via quota |
| Unacknowledged in-flight requests per Thing/connection | 10 | Exceeding returns response code 429 |

Quotas can vary by Region and account. Before deploying a large fleet, verify AWS General Reference and Service Quotas in the target Region.

### 16.1 Reducing Payload Size

- Send only changed fields.
- Avoid duplicating application-generated metadata.
- Keep schemas concise.
- Split state domains into named shadows where appropriate.
- Do not store long telemetry arrays.
- Never send the full shadow document when updating a single field.

### 16.2 Request Rate Control

If devices or backends send updates too rapidly:
- Coalesce multiple `desired` changes into a single update.
- Limit outstanding request concurrency.
- Wait for `accepted`/`rejected` before sending excessive requests.
- Use exponential backoff and jitter on throttling.
- Avoid reconnect storms when thousands of devices boot simultaneously.
- Stagger fleet rollouts in batches.

## 17. Common Errors and Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `get/rejected` on startup | Shadow does not exist yet | Create via an initial `reported` update |
| `update/rejected` due to version | Client used an outdated version | GET fresh state, merge, and retry |
| `update/rejected` due to JSON | Malformed JSON or fields outside `state` | Validate schema; use only `desired`/`reported` |
| Payload too large | Shadow document exceeds limit | Trim fields or split into named shadows |
| No `accepted` received | Not subscribed before publishing or missing permissions | Subscribe to response topics first; check policy |
| No `delta` received | `desired` matches `reported` or client not subscribed | GET shadow, compare sections, check subscriptions |
| `delta` keeps reappearing | Device fails to update `reported` or reports mismatched value | Check actuator, firmware, and state reporting |
| Device does not apply `desired` | Firmware lacks field support or invalid value | Check capability/version and validation |
| Request gets 429 | Exceeded request rate or in-flight limit | Lower concurrency, add backoff, review quotas |
| Cloud shows wrong state | Backend wrote `reported` on device's behalf | Enforce ownership; only firmware reports physical state |
| Reconnect executes stale command | Firmware acted on old notification | GET snapshot, compare versions, sync current state |
| Named shadow inaccessible | Wrong shadow name or topic ARN | Verify prefix and policy resources |

AWS IoT Device Shadow can log errors to CloudWatch Logs when logging is enabled. When investigating, correlate:
- MQTT client logs.
- `accepted` and `rejected` responses.
- `code`, `message`, `clientToken`, and `version`.
- AWS IoT logs.
- Certificates and IoT policies.
- IAM policies if the backend uses the HTTPS API.

## 18. Observability and Fleet Operations

A shadow architecture must monitor both service health and device state.

### 18.1 Metrics to Observe

| Metric | Meaning |
|---|---|
| Shadow update success/reject rate | Ratio of successful vs. failed updates |
| Version conflict count | Optimistic concurrency conflicts |
| Throttling/429 count | Rate-limited requests |
| Delta age | How long `desired` remains unconfirmed by `reported` |
| Desired/reported mismatch count | Number of devices that have not converged |
| Reconnect synchronization time | Time taken for devices to sync after reconnecting |
| Payload size distribution | Identifies shadows approaching size limits |
| Request latency | Shadow operation response time |
| Fleet coverage | Percentage of devices reporting state |
| Firmware capability distribution | Device breakdown by firmware version |

Not every metric is available out of the box in CloudWatch. Some must be derived from events, Rules, backend logs, or Fleet Indexing.

### 18.2 Alerting

Configure alerts when:
- `update/rejected` rate spikes abnormally.
- 429 responses occur persistently.
- Many devices exhibit `desired`/`reported` mismatches beyond SLA.
- Devices reconnect without updating `reported`.
- Outdated firmware versions represent a high percentage.
- Shadow documents grow close to size limits.

Alerts should distinguish connectivity failures from execution errors. An offline device does not necessarily have an actuator fault, whereas a `desired` state lingering too long may indicate the device has not received the configuration.

### 18.3 Auditing and History

Shadows hold current state, not a full command history like an event log. If auditing is required:
- Capture update events via `update/documents` or Rules Engine.
- Record actor, request ID, Thing name, and timestamp.
- Store old/new values per security requirements.
- Enforce audit log retention and read access controls.
- Distinguish who requested `desired` from which device confirmed `reported`.

## 19. Hands-On Example: Controlling a Thermostat with a Named Shadow

Goal: the backend updates the target temperature; the device receives the delta, applies it, and reports back.

### Step 1: Select Thing and Shadow

Thing:

~~~text
thermostat-01
~~~

Named shadow:

~~~text
climate
~~~

Topic prefix:

~~~text
$aws/things/thermostat-01/shadow/name/climate
~~~

### Step 2: Device Subscribes

The device subscribes to:
- `.../get/accepted`
- `.../get/rejected`
- `.../update/delta`
- `.../update/accepted`
- `.../update/rejected`

Optionally subscribe to `.../update/documents` to receive full documents before/after each update.

### Step 3: Device Initializes Reported State

Publish to:

~~~text
$aws/things/thermostat-01/shadow/name/climate/update
~~~

Payload:

~~~json
{
  "state": {
    "reported": {
      "power": "ON",
      "setpointC": 26,
      "mode": "AUTO",
      "firmwareVersion": "2.4.1"
    }
  },
  "clientToken": "thermostat-boot-001"
}
~~~

### Step 4: Backend Updates Desired State

The backend publishes to the same `/update` topic or calls the API:

~~~json
{
  "state": {
    "desired": {
      "setpointC": 24,
      "mode": "COOL"
    }
  },
  "clientToken": "operator-change-2001"
}
~~~

### Step 5: Device Receives Delta and Executes

The delta contains `setpointC = 24` and `mode = COOL`. Firmware checks bounds, applies the settings, reads back controller state, and publishes `reported`:

~~~json
{
  "state": {
    "reported": {
      "setpointC": 24,
      "mode": "COOL",
      "applyStatus": "SUCCEEDED"
    }
  },
  "clientToken": "thermostat-report-002"
}
~~~

### Step 6: Backend Confirms

The backend reads the shadow. Once `desired` and `reported` match, `delta` no longer includes those fields. The dashboard can display:
- Desired setpoint: 24°C.
- Reported setpoint: 24°C.
- Apply status: SUCCEEDED.

If the device does not support `COOL`, firmware must not report `mode = COOL` as if applied. It should preserve the actual reported mode and publish a separate error so the backend can surface the mismatch.

## 20. Production Design Checklist

- [ ] Thing identity and state ownership are defined.
- [ ] Classic vs. named shadow choice is finalized.
- [ ] Cloud writes only `desired` and device writes only `reported` by convention.
- [ ] Delta is treated as current difference, not a command queue.
- [ ] Firmware subscribes to response topics before publishing requests.
- [ ] Devices GET the shadow on startup and reconnect.
- [ ] Firmware validates `desired` values before applying them.
- [ ] Devices publish `reported` only after verifying actual state.
- [ ] Version tracking and stale-message handling are implemented.
- [ ] `clientToken` is used to correlate requests and responses.
- [ ] Rejected updates, version conflicts, and throttling are handled.
- [ ] Retries use backoff and jitter.
- [ ] Shadow schema is small, stable, and versioned.
- [ ] No time-series telemetry or secrets are stored in shadows.
- [ ] Payload size, nesting depth, and request rate limits are checked.
- [ ] IoT policies scope exact Thing, shadow, and topic actions.
- [ ] HTTPS backends use dedicated IAM policies.
- [ ] Unnecessary wildcard shadow topic subscriptions are avoided.
- [ ] CloudWatch logging and audit events are configured.
- [ ] Offline, reconnect, concurrent update, and legacy firmware scenarios are tested.
- [ ] Device Management Jobs or a queue is selected if command/job history is required.

## 21. Practice Exercises

### Exercise 1: Desired and Reported

The cloud updates `desired setpoint = 22`, while the device reports `setpoint = 25`.

Question: What does `delta` contain? When does `delta` disappear?

Answer: `delta` contains `setpoint = 22`. Once the device applies it and updates `reported` to `22`, both sections match and `delta` disappears.

### Exercise 2: Offline Device

A device is offline for 3 hours. During that time, the backend changes `desired` from `24` to `23` and then `22`.

Question: Upon reconnecting, which value should the device apply?

Answer: Converge to the latest `desired` value of `22`. Device Shadow does not retain a queue requiring sequential execution of `24`, `23`, and `22`.

### Exercise 3: Version Conflict

The backend reads version 15. Another service updates the shadow to version 16. The backend sends an update specifying version 15.

Question: How should this be handled?

Answer: The update is rejected due to the stale version. The backend GETs the latest shadow, merges required changes, and retries with the current version.

### Exercise 4: Deleting a Field

An application wants to remove the `desired` field `schedule`.

Question: What payload should it send?

Answer:

~~~json
{
  "state": {
    "desired": {
      "schedule": null
    }
  }
}
~~~

### Exercise 5: Named Shadows

A gateway manages network config, sensor config, and maintenance state.

Question: Propose named shadows and their benefits.

Suggested answer: `network`, `sensors`, `maintenance`. Separates concerns, schemas, and policies by group; firmware must synchronize each shadow independently.

### Exercise 6: Throttling

A backend sends 40 updates/second to the same shadow and receives 429 responses.

Question: Propose mitigations.

Answer: Coalesce updates, reduce concurrency, limit in-flight requests, apply backoff/jitter, and evaluate adjustable quotas. Never retry immediately in a tight loop.

### Exercise 7: Authorization

Firmware should only read `desired` and write `reported`. Only the backend may modify `desired`.

Question: How should MQTT permissions be split?

Answer: Firmware subscribes to delta/response topics and publishes to `/update` to report `reported`; the backend role has API permissions to update `desired` for the target Thing. Note that IoT policies authorize by topic only and cannot distinguish `desired` from `reported` inside the JSON body of the same `/update` topic. Enforce the write convention in firmware/backend and validate payloads at the application layer. Do not grant `delete` permission to firmware unless needed.

### Exercise 8: Choosing Shadow vs. Jobs

A group of devices needs to update firmware, tracking download progress, installation, reboot, and success/failure results.

Answer: Use AWS IoT Device Management Jobs to manage task progress and execution outcomes. Shadow can be used to report the current or target firmware version.

## 22. Self-Check Questions

1. What information does Device Shadow store?
2. How does a Thing differ from a shadow?
3. Who updates `desired` and `reported`?
4. How does AWS IoT calculate `delta`?
5. Why is `delta` not a command queue?
6. Can a shadow be updated while a device is offline?
7. When a device reconnects, why should it GET the shadow?
8. Why should a client subscribe to response topics before publishing a request?
9. How do classic shadows and named shadows differ?
10. What information does `metadata` contain?
11. How does `timestamp` differ from device measurement time?
12. What role does `clientToken` serve?
13. How does `version` help resolve race conditions?
14. When an update is rejected due to an outdated version, what should the client do?
15. Does a partial update to a shadow document preserve unsent fields?
16. How do you delete a `desired` attribute?
17. How are arrays compared in shadow deltas?
18. What does MQTT `update/accepted` prove, and what does it not prove?
19. When should you use Device Management Jobs instead of Device Shadow?
20. Which payload and request-rate limits should you verify?

Suggested Answers:

1. The desired state and the latest state reported by the device.
2. A Thing is a logical asset in the Registry; a shadow is the state document for that Thing.
3. The cloud typically updates `desired`; the device updates `reported`.
4. By comparing `desired` with `reported` and placing differing fields into `delta`.
5. It only represents the current difference, not a history of every request.
6. Yes, the cloud can update the shadow while the device is offline.
7. To retrieve the latest snapshot and converge after potentially missing notifications.
8. MQTT does not guarantee the client receives responses if it has not subscribed yet.
9. A Thing can have at most one classic shadow, whereas it can have multiple named shadows.
10. Per-attribute update timestamps.
11. `timestamp` is when AWS IoT processed/generated the response; measurement time requires a dedicated field.
12. Correlates responses with their corresponding requests.
13. Clients pass the version they read to prevent updating over newer state.
14. GET the latest state, merge, and retry.
15. Yes, omitted fields are normally preserved.
16. Send the field with a `null` value.
17. The entire array is treated as a single value; if different, the whole `desired` array appears in `delta`.
18. It confirms the service updated the shadow, not that the device executed the action.
19. When you need job workflows, progress tracking, retries, and execution results.
20. 8 KB default state document, 8 nesting levels, 20 requests/second/shadow, and 10 unacknowledged in-flight requests per Thing/connection.

## 23. Official References

- [AWS IoT Device Shadow service](https://docs.aws.amazon.com/iot/latest/developerguide/iot-device-shadows.html)
- [Device Shadow service documents](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-document.html)
- [Device Shadow MQTT topics](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-mqtt.html)
- [Interacting with shadows](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-data-flow.html)
- [Using shadows in devices](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-comms-device.html)
- [Using shadows in apps and services](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-comms-app.html)
- [Device Shadow REST API](https://docs.aws.amazon.com/iot/latest/developerguide/device-shadow-rest-api.html)
- [Device Shadow service limits and quotas](https://docs.aws.amazon.com/general/latest/gr/iot-core.html)
- [AWS IoT Core policies](https://docs.aws.amazon.com/iot/latest/developerguide/iot-policies.html)
- [Fleet indexing](https://docs.aws.amazon.com/iot/latest/developerguide/iot-indexing.html)
- [AWS IoT Device Management Jobs](https://docs.aws.amazon.com/iot/latest/developerguide/iot-jobs.html)
- [AWS IoT Core Rules Engine](https://docs.aws.amazon.com/iot/latest/developerguide/iot-rules.html)

Limits, APIs, MQTT topics, and integration capabilities may vary by Region and over time. Before deploying a production fleet, verify current AWS documentation and test firmware reconnects, concurrent updates, version conflicts, throttling, and certificate rotation in a staging environment.
