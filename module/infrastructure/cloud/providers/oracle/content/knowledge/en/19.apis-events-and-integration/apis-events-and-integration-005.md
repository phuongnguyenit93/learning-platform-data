# Creating event rules and choosing event actions

In the **APIs, Events, and Integration** chapter of Oracle Cloud Infrastructure (OCI), an event rule is the bridge between a resource state change and an automated system response. For example, when a CSV file appears in Object Storage, you can notify an operations team, invoke a Function to validate the data, or route the event to Streaming for an application to process later.

This lesson focuses on defining rule scope, writing event-matching conditions, and selecting the right action. Decisions are framed within the context of OCI tenancy, compartments, IAM, monitoring, availability, and cost.

After this lesson, you can:

- Translate an operational requirement into a triad: source event, filter condition, and target destination.
- Create rules via the Console or OCI CLI with explicit compartment scope.
- Distinguish Notifications, Functions, and Streaming when selecting actions.
- Independently verify rule matching, event delivery, and business processing completion.
- Design handlers resilient to duplicate events, target failures, and configuration changes.

## 1. Understanding the relationship between events, rules, and actions

An **event** is a message describing a change emitted by an OCI service. **Event type** indicates the kind of change, such as object creation. A **rule** contains a filter condition and a list of actions. An **action** specifies the target resource that receives events matching the rule.

Events supports three direct destination types: Notifications topic, Streaming stream, and Function. When an event matches, the service delivers the message to the configured destinations; subsequent work is the responsibility of the receiving service or application. [Source: Overview of Events](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsoverview.htm).

~~~mermaid
flowchart LR
    S["Event-emitting resource"] --> E["OCI Events"]
    E --> R{"Rule enabled and condition matches?"}
    R -->|Yes| N["Notifications topic"]
    R -->|Yes| F["Function"]
    R -->|Yes| T["Streaming stream"]
    R -->|No| X["Do not run this rule's actions"]
    N --> U["People or subscribers receive alert"]
    F --> B["Business processing"]
    T --> C["Consumer processes asynchronously"]
~~~

The diagram illustrates the options. A rule only needs the actions that serve the actual requirement; you do not need to configure all three.

### 1.1. Compartment scope determines what a rule sees

A rule applies to events from resources in the compartment containing the rule and its child compartments. Therefore:

- A rule placed in `EventLab` can monitor resources in `EventLab` and its child branches.
- A rule placed in a child branch does not automatically monitor resources in the parent compartment or sibling branches.
- To target only one specific compartment, you can add `data.compartmentId` to the condition to narrow the scope.
- Action destinations can reside in a different compartment from the rule; permissions to access the destination must be appropriate.

Every rule must have at least one action; the rule management documentation states a maximum of 10 actions per rule. This is a configuration limit, not a reason to add multiple actions unnecessarily. [Source: Managing Rules for Events](https://docs.oracle.com/en-us/iaas/Content/Events/Task/managingrules.htm).

When deploying, record both the **region** and compartment of the source, rule, and destination. This lab uses a single region for easy verification. Do not assume a created rule automatically covers other regions.

### 1.2. Distinguishing three outcomes that are often conflated

| Outcome | What is proven | What still must be checked |
| --- | --- | --- |
| Rule created successfully | Configuration was accepted by the service | Whether the source emits events and the condition matches |
| Event delivered to action | Target destination accepted the message per delivery mechanism | Whether the subscriber, Function, or consumer completed the work |
| Business processing completed | Expected output has appeared | Whether duplicates or dropped items occur under failure scenarios |

An email arriving does not prove a Function on the same rule succeeded. Likewise, successful delivery into a stream does not prove the consumer updated the database.

## 2. Inspecting the source message before writing a condition

Do not start by guessing field names. Look up the event type in the source service's catalog and read the corresponding sample payload.

Below is an **illustrative** message based on the object-creation event structure. Identifiers have been replaced with synthetic values; this is not data captured from a live tenancy.

~~~json
{
  "cloudEventsVersion": "0.1",
  "eventID": "example-event-invoice-001",
  "eventType": "com.oraclecloud.objectstorage.createobject",
  "source": "objectstorage",
  "eventTypeVersion": "2.0",
  "eventTime": "2026-11-20T03:00:00Z",
  "contentType": "application/json",
  "extensions": {
    "compartmentId": "<SOURCE_COMPARTMENT_OCID>"
  },
  "data": {
    "compartmentId": "<SOURCE_COMPARTMENT_OCID>",
    "compartmentName": "EventLab",
    "resourceName": "incoming/invoice-001.csv",
    "resourceId": "",
    "availabilityDomain": "all",
    "additionalDetails": {
      "namespace": "training_namespace",
      "bucketName": "oci-event-lab-input",
      "bucketId": "<BUCKET_OCID>",
      "eTag": "example-etag-001"
    }
  }
}
~~~

For object events, `data.resourceName` represents the object name; the bucket name resides in `data.additionalDetails.bucketName`. Do not borrow the structure of bucket events to infer the structure of object events. The OCI catalog also distinguishes `createobject`, `updateobject`, and `deleteobject`. [Source: Services that Produce Events, Object Storage section](https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventsproducers.htm#ObjectStorage).

Fields of interest in this lesson:

| Field | Role in design |
| --- | --- |
| `eventID` | Log correlation and identifying already-processed events |
| `eventType` | Selecting the exact change type to react to |
| `eventTime` | Timestamp of the event, aiding latency investigation |
| `data.compartmentId` | Scoping the source resources |
| `data.resourceName` | Filtering resource or object names as required |
| `data.additionalDetails` | Holds details specific to the source service |

Payloads depend on the service and event type. Do not assume every event has `bucketName`, tags, or a non-empty `resourceId`. The example above leaves `resourceId` empty as a case processors must tolerate, rather than using this field as a universal unique key across all event types. [Source: Contents of an Event Message](https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventenvelopereference.htm).

`cloudEventsVersion` in the example reflects the OCI format used for illustration; do not rename envelope fields to another schema when writing rules. Always base rules on the actual message emitted by the source.

## 3. Translating requirements into filter conditions

Suppose the requirement is:

> Whenever a new object appears under prefix `incoming/` with extension `.csv` in bucket `oci-event-lab-input` inside the chosen source compartment, notify the operations team.

Corresponding condition:

~~~json
{
  "eventType": [
    "com.oraclecloud.objectstorage.createobject"
  ],
  "data": {
    "compartmentId": "<SOURCE_COMPARTMENT_OCID>",
    "resourceName": "incoming/*.csv",
    "additionalDetails": {
      "bucketName": "oci-event-lab-input"
    }
  }
}
~~~

Replace `<SOURCE_COMPARTMENT_OCID>` with a real OCID before deploying. This is the **condition content**, not the entire rule object.

### 3.1. Rules for combining conditions

Declared fields must all match; values inside an array act as alternatives. Fields omitted from the condition do not participate in filtering. Nested structure must mirror the source message.

In the example, the event must match the type, compartment, object name, and bucket. OCI supports the `*` wildcard; it does not turn the condition into a regular expression. An empty condition `{}` matches every event within the rule's compartment scope. [Source: Matching Events with Filters](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/filterevents.htm).

Reading the condition aloud helps catch requirement mismatches: "Object creation type **and** matching compartment **and** name matching `incoming/*.csv` **and** matching bucket."

If business logic accepts both object creation and updates, update only the event type list:

~~~json
{
  "eventType": [
    "com.oraclecloud.objectstorage.createobject",
    "com.oraclecloud.objectstorage.updateobject"
  ]
}
~~~

This is a condition fragment illustrating arrays, not a replacement for the lab's full filter. When applying it, keep the necessary compartment, bucket, and object-name constraints.

For overwrites, copies, or multipart uploads, observe the actual event emitted by the operation before deciding which types to select. An operation's name in application code is not enough to deduce the event type with certainty.

### 3.2. Common design mistakes

| Practice | Consequence | Fix |
| --- | --- | --- |
| Putting `bucketName` directly under `data` | Does not match object event structure | Place under `data.additionalDetails` |
| Setting `resourceName` to bucket name for object events | Valid objects are filtered out | Use object name in this field |
| Putting `$.data.resourceName` syntax in field names | Confuses condition with JSONPath | Use nested JSON matching schema |
| Using `incoming/.*\.csv` as regex | Pattern lacks intended regex semantics | Use supported wildcards and test with samples |
| Filtering on tags absent from payload | May not match even if resource is tagged elsewhere | Verify source event actually contains the tag |
| Using compartment name as a long-term identifier | Renaming can break the filter | Prefer OCID when exact identification is needed |
| Using `{}` at broad scope for automation | Many unexpected events reach the destination | Start with narrow event types and scope |

Do not import operators familiar from other tools such as `$or`, `exists`, or SQL expressions if OCI Events documentation does not define them. If business rules require reading CSV contents, comparing multiple records, or calling another system, move that logic to the processor.

### 3.3. Rule tags vs. tags used to filter sources

Tags attached to a **rule** serve to organize the rule resource. Conditions such as `data.definedTags` or `data.freeFormTags`, by contrast, inspect the **source message**.

For example, tagging a rule `Environment=prod` does not automatically make it receive events only from production resources. To get that behavior, the condition must reference the tags emitted by the source. Design must govern who may edit source tags, since changing tags can alter automation scope.

## 4. Choosing actions by recipient and processing model

All three actions start from a matched event, yet serve different needs.

| Criterion | Notifications | Functions | Streaming |
| --- | --- | --- | --- |
| Typical need | Notify people or subscribers | Execute custom logic | Push messages into a stream for consumers |
| Target resource | Topic | Deployed Function | Stream |
| Components to prepare | Topic and matching subscription | Function, config, permissions, and required connectivity | Stream and consumer application |
| Next step | Subscriber receives, interprets, or forwards | Code validates, transforms, or calls APIs | Consumer reads, processes, and tracks progress |
| Extra monitoring points | Subscription status and delivery results | Logs, errors, execution time, outputs | Consumer lag, processing errors, replayability |
| Costs to evaluate | Notification channel and delivery count | Invocations, execution resources, and called services | Storage/throughput, retention, and consumers |

The selection notes below are design recommendations for this lesson's scenario; they do not add new action types to the Events service.

### 4.1. Notifications: when the primary reaction is alerting

Choose Notifications if the operations team needs to be alerted of a change, such as a new file to monitor or a database operation finishing.

The rule's target is a **topic**, not an email address. For email subscriptions, confirm the subscription via email before expecting operational alerts. [Source: Getting Started with Events](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsgetstarted.htm).

An email from a file-creation event only proves the source reported the file was created. If you need a "data validated successfully" alert, send the notification after the business validation step.

Avoid sending high-volume events to a shared inbox. Select changes requiring human action and define who owns responding to them.

### 4.2. Functions: when logic must execute

Choose Functions when you need to read metadata, inspect the object, transform the message, or call a target API.

Design example:

1. Receive event for new object.
2. Validate `eventType` and allowed bucket.
3. Use the Function's identity to read the object.
4. Validate data structure.
5. Persist processing results with a deduplication key.
6. Send a completion notification or trigger the next step.

This is a business workflow you build. The rule does not provide those steps on its own.

If the Function runs inside a VCN, design network connectivity to Object Storage, databases, or APIs used by the code. A rule successfully invoking the Function does not prove the Function has permissions or network routes to reach downstream resources.

Do not embed database passwords or access keys inside conditions or action descriptions. Use identity and secret-management mechanisms appropriate for the application.

### 4.3. Streaming: when ingestion and processing must be decoupled

Choose Streaming if applications need to consume events at their own pace or multiple teams need independent processing.

For instance, one consumer updates a file catalog while another counts arriving files. With this design, define appropriate retention periods, offset/progress management, and consumer recovery procedures.

Replayability from a stream depends on stream retention configuration and data state. It does not mean Events automatically stores full history for arbitrary replay at any time.

If business logic requires per-object ordering, design partition keys and consumer-side version checks. Do not infer global ordering simply because all events enter one stream.

### 4.4. Multiple actions mean fan-out, not a sequential workflow

A single rule can deliver the same event to multiple targets. However, never interpret the order of action entries as "run Function first, then send email after it finishes."

If you configure both a Function and Notifications on one rule, the email describes the **source event**. To make the email reflect the **Function's outcome**, have the Function or an orchestrator send it once the work reaches the reportable state.

Likewise, do not assume actions share a transaction: target A may receive the event while target B fails. Design error handling and observability independently for each branch.

API Gateway, databases, and arbitrary HTTP URLs are not among the three direct action types above. When integrating with those targets, choose an appropriate intermediary, such as a Function performing authenticated calls.

## 5. Preparing IAM before creating rules

Distinguish the permission layers:

| Principal | Permissions to review |
| --- | --- |
| Person or pipeline creating rules | Manage rules in the assigned compartment |
| Person configuring actions | Inspect or use the respective topic, Function, or stream |
| Code running inside the Function | Access objects, secrets, databases, or APIs per business logic |
| Stream consumer | Read the stream and write allowed outputs |

The example below assumes group `OciEventAuthors`, and compartments `EventLab` and `IntegrationTargets` already exist:

~~~text
Allow group OciEventAuthors to manage cloudevents-rules in compartment EventLab
Allow group OciEventAuthors to use ons-topic in compartment IntegrationTargets
Allow group OciEventAuthors to inspect compartments in tenancy
~~~

This is a scoped example for someone managing rules targeting an existing topic. It does not grant all permissions needed to create every lab resource; permissions to create buckets, topics, subscriptions, Functions, or streams must be evaluated separately.

In tenancies using identity domains, group references must follow the tenancy's domain/group syntax. Replace placeholder names with real ones and place policies at a scope with authority over the relevant compartments. [Source: Events and IAM Policies](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventspolicy.htm).

For rules, the IAM resource type is `cloudevents-rules`. Read permissions differ from management permissions; do not grant `manage` to users who only inspect configurations. [Source: Details for the Events Service](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/cloudeventspolicyreference.htm).

If selecting Functions or Streaming, look up permissions for the exact destination type rather than reusing Notifications policies. Rule management permissions do not replace a Function's business permissions.

This lesson operates within a single tenancy. Delivering events across tenancies is a separate authorization problem requiring two-sided cross-tenancy configuration per documentation; it cannot be solved merely by changing an action's OCID.

## 6. Lab: creating a rule via the Console

### 6.1. Lab layout

| Component | Illustrative value |
| --- | --- |
| Region | `ap-singapore-1` |
| Source and rule compartment | `EventLab` |
| Source bucket | `oci-event-lab-input` |
| Valid object | `incoming/invoice-001.csv` |
| Initial target | Notifications topic `event-lab-notifications` |
| Rule name | `event-lab-csv-created-notify` |

The names and region above are lab choices. If using another region, apply it consistently across Console and CLI. Actual bucket names must fit your namespace.

Starting with Notifications lets you observe the event path without writing handler code yet. Once the path works, you can replace or add actions as needed.

### 6.2. Preparing source and target

1. Select the lab region.
2. Create or identify the source bucket in `EventLab`.
3. Enable **Emit object events** on the bucket.
4. Prepare the Notifications topic.
5. Create an email subscription and complete confirmation.
6. Verify the practitioner's permissions for rules and topics.

Object events are not emitted by default. If you forget to enable this setting on the bucket, even a correct condition will receive no object-creation events. It can be enabled from the bucket page or via CLI. [Source: Managing Emitting Events for Object State Changes](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingbuckets_topic-To_enable_or_disable_emitting_events_for_object_state_changes.htm).

### 6.3. Declaring the rule

Open **Events Service → Rules**, choose the rule's compartment, and create a new rule.

Fill in name, description, and condition:

- Event type: Object Storage, object creation type.
- Source compartment attribute: real OCID of `EventLab`.
- Object name: `incoming/*.csv`.
- Bucket name: `oci-event-lab-input`.

Use the condition editor if needed to match the JSON in Section 3 exactly. For the action, choose **Notifications**, the topic's compartment, and the prepared topic.

The Console also allows choosing Streaming via a target stream or Functions via an application and target Function. Target resources must already exist to be selected. [Source: Creating an Events Rule](https://docs.oracle.com/en-us/iaas/Content/Events/Task/create-events-rule.htm).

The description should state the purpose clearly, such as: "Notify when a new CSV arrives under incoming in the lab bucket." Avoid descriptions that falsely imply the data was validated successfully.

### 6.4. Using a sample to test the condition

Use the sample event testing feature on the rule, documented in the Console as **Check if Example Event Matches Rule** or **Validate**.

Paste the illustrative event from Section 2 after replacing the compartment with the real value. Also test variations:

| Sample variation | Expected result |
| --- | --- |
| Matching event type, compartment, bucket, CSV name | Matches |
| Name is `incoming/readme.txt` | Does not match |
| Name is `processed/invoice-001.csv` | Does not match |
| Different bucket | Does not match |
| Different compartment | Does not match |
| Event type is `deleteobject` | Does not match |
| Missing `data.additionalDetails.bucketName` | Does not match |

If placing the rule in a parent compartment while the condition restricts to child compartment A, events from child compartment B must still be excluded.

Sample testing evaluates only the filter condition. It does not prove the source enabled events, delivery permissions are valid, or emails arrived. After creating the rule, verify both the rule and the action are enabled before end-to-end testing.

## 7. Equivalent practice using the OCI CLI

Commands in this section use **Bash in OCI Cloud Shell**, not PowerShell syntax. They are instructions for learners to run in their practice tenancy; OCIDs in `<...>` must be replaced with real values.

Learners need an authenticated OCI CLI, prepared source/target resources, and required permissions. Do not put private keys or tokens into illustrative configuration files.

### 7.1. Preparing condition and actions

Save the condition from Section 3 as `condition.json`, substituting the compartment OCID. Do not wrap it in an outer `condition` key inside this file.

Create `actions.json` with a Notifications action:

~~~json
{
  "actions": [
    {
      "actionType": "ONS",
      "description": "Notify on new CSV object in the lab bucket",
      "isEnabled": true,
      "topicId": "<TOPIC_OCID>"
    }
  ]
}
~~~

Input property names use camelCase, such as `actionType` and `topicId`. Do not copy hyphenated field names from CLI JSON output as input.

When targeting other destination types, use the corresponding property:

| Action type in input | Target OCID field | Service |
| --- | --- | --- |
| `ONS` | `topicId` | Notifications |
| `FAAS` | `functionId` | Functions |
| `OSS` | `streamId` | Streaming |

Here `OSS` is the action code for Streaming, not Object Storage. Action structures are illustrated in the Events getting-started guide. [Source: Getting Started with Events, CLI section](https://docs.oracle.com/en-us/iaas/Content/Events/Concepts/eventsgetstarted.htm#usingcli).

Example Function action to replace the element inside the `actions` array:

~~~json
{
  "actionType": "FAAS",
  "description": "Validate new object data",
  "isEnabled": true,
  "functionId": "<FUNCTION_OCID>"
}
~~~

If adding multiple actions, keep them as elements of the same array. Only add deployed targets that have an owner and a clear purpose.

### 7.2. Creating the rule in disabled state

In the directory containing both JSON files:

~~~bash
REGION='ap-singapore-1'
RULE_COMPARTMENT_ID='<SOURCE_COMPARTMENT_OCID>'

RULE_ID=$(oci events rule create \
  --region "$REGION" \
  --compartment-id "$RULE_COMPARTMENT_ID" \
  --display-name 'event-lab-csv-created-notify' \
  --description 'Notify on incoming CSV object creation in the lab bucket' \
  --condition "$(cat condition.json)" \
  --actions file://actions.json \
  --is-enabled false \
  --wait-for-state ACTIVE \
  --query 'data.id' \
  --raw-output)

printf '%s\n' "$RULE_ID"
~~~

The CLI accepts `--condition` as a JSON string and `--actions` as a complex JSON object; `file://` reads action input from a file. The command uses `cat` to pass the condition content as a single argument. [Source: OCI CLI — events rule create](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/events/rule/create.html).

Verify the command succeeded and `RULE_ID` is a valid OCID before proceeding. Never blindly rerun the create command after a network error: list existing rules first to avoid creating duplicates.

Waiting for lifecycle state `ACTIVE` does not mean the rule is enabled. In this command, the rule exists in an active lifecycle state while `isEnabled` remains `false`.

### 7.3. Reading back the configuration and enabling the rule

~~~bash
oci events rule get \
  --region "$REGION" \
  --rule-id "$RULE_ID"
~~~

Check:

- Correct compartment and rule name.
- Condition has the right event type, compartment OCID, and bucket.
- Topic ID points to the lab target.
- Action is enabled.
- Rule is disabled as intended during creation.

After verifying the configuration and testing the condition with a sample in the Console, enable the rule:

~~~bash
oci events rule update \
  --region "$REGION" \
  --rule-id "$RULE_ID" \
  --is-enabled true \
  --wait-for-state ACTIVE
~~~

The CLI provides `update` to change the enabled state. After changes, read back the rule instead of relying solely on the command exiting without error. [Source: OCI CLI — events rule update](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/events/rule/update.html).

If modifying the actions list, check the update parameter semantics and retain all actions you still need. Do not assume passing one new element automatically appends it while preserving all existing elements.

### 7.4. Enabling the emitter and generating real events

Set the real namespace and prepared bucket:

~~~bash
NAMESPACE='<OBJECT_STORAGE_NAMESPACE>'
BUCKET='oci-event-lab-input'

oci os bucket update \
  --region "$REGION" \
  --namespace-name "$NAMESPACE" \
  --name "$BUCKET" \
  --object-events-enabled true
~~~

Create a synthetic data file and upload it with a **new object name**:

~~~bash
printf 'invoice_id,total\nINV-001,120000\n' > event-lab.csv

oci os object put \
  --region "$REGION" \
  --namespace-name "$NAMESPACE" \
  --bucket-name "$BUCKET" \
  --name 'incoming/invoice-001.csv' \
  --file ./event-lab.csv
~~~

If that object already exists, use a new name such as `incoming/invoice-002.csv` so the creation test is unambiguous. Do not overwrite an existing object and assume the outcome must match a first-time creation.

Next, test an object that should not match the condition:

~~~bash
oci os object put \
  --region "$REGION" \
  --namespace-name "$NAMESPACE" \
  --bucket-name "$BUCKET" \
  --name 'incoming/readme.txt' \
  --file ./event-lab.csv
~~~

Even though the file content is still CSV, the object name ends in `.txt` and therefore does not match the filter. This test also demonstrates that rules filter on metadata, not file contents.

Wait for delivery signals and inspect metrics over an appropriate window. Do not treat not receiving an email immediately as sufficient proof that the rule is misconfigured.

## 8. End-to-end verification with evidence

A valid test connects three layers of evidence:

1. The source operation succeeded and the source is configured to emit events.
2. The rule matched and recorded action delivery.
3. The destination produced the expected output: email, handler logs, or consumer-written records.

In the Notifications example, the received message must reference the exact uploaded object. When moving to a Function, emit structured logs including `eventID`, `eventType`, bucket name, object name, and processing outcome; avoid logging raw sensitive business data.

With multiple rules or multiple actions, one source operation can trigger multiple deliveries. Do not use "received exactly one email" to claim the entire system processed correctly without inspecting the other branches.

### 8.1. Events metrics

The monitoring namespace is `oci_cloudevents`.

| Metric | Question supported |
| --- | --- |
| `PublishedEvents` | Are events emitted by resources in the compartment? |
| `MatchedEvents` | Did the rule match events? |
| `DeliverySucceedEvents` | Were deliveries to actions successful? |
| `DeliveryFailedEvents` | Were there failed deliveries? |

Check the right region, time window, and the rule's `resourceId` dimension when a metric applies per rule. `PublishedEvents` reflects compartment scope; do not interpret it as a counter for a single rule.

Metrics may have different dimensions; do not assume every metric can always be filtered per individual action. Use the provided dimensions, action configuration, and destination evidence to narrow down issues. [Source: Events Metrics](https://docs.oracle.com/en-us/iaas/Content/Events/Reference/eventsmetrics.htm).

An alarm on delivery failures helps detect issues on the event delivery path. To know whether a Function updated the database or a consumer is lagging, add logs and metrics for those components.

### 8.2. Isolating faults hop by hop

| Symptom | Check first | Next step |
| --- | --- | --- |
| No source events seen | Region, compartment, Emit object events, operation type | Trigger a new event after enabling emission |
| Events exist, rule does not match | Condition, field structure, event type, rule scope | Test real payload with sample validator |
| Sample condition matches, no action runs | Are rule and action enabled, is target correct? | Read back the deployed configuration |
| Delivery failures reported | Does target still exist, permissions, service state | Isolate the failing action and inspect target |
| Notifications delivery succeeds, no email | Topic, subscription, confirmation, recipient inbox | Verify the subscription path |
| Function invoked, no output | Logs, resource principal permissions, connectivity to dependencies | Fix code or access path |
| Stream receives events, app does not update | Consumer progress, decoding errors, output write errors | Fix consumer and reprocess per design |
| Processing count spikes abnormally | Overlapping rules, duplicate events, automation loops | Narrow condition and verify deduplication |

If temporarily creating a broad rule for diagnostics, use a safe observation target and restrict it to the lab compartment. Never wire a broad filter to a Function with permissions to mutate production resources.

## 9. Resilient design and deduplication

Do not design processors assuming every event arrives exactly once or in emission order. Oracle's FAQ notes duplicate delivery possibilities and recommends idempotent receivers. [Source: Events Service FAQ](https://www.oracle.com/webfolder/technetwork/tutorials/faqs/oci/events-faq.pdf).

**Idempotent** means repeatedly processing the same action does not create erroneous duplicate effects. For example, receiving an object-creation event twice must not generate a second payment request.

### 9.1. Choosing the right processing key

`eventID` is useful for recognizing redelivery of the same message. However, two events with different IDs can still relate to the same business item. Therefore, you may also need a business key combining namespace, bucket, object name, and an appropriate version identifier.

Do not assume `eTag` is a content hash or always substitutes for a version identifier. Deduplication keys must reflect the data semantics and operation type the application truly needs to protect.

Suggested design pattern:

~~~text
receive(event)
validate_event_type_and_scope(event)

key = derive_processing_key(event)
claim = acquire_atomic_claim_with_lease(key)

if claim.already_completed:
    return success

if not claim.acquired:
    return retry_later

try:
    result = perform_idempotent_business_operation(key, event)
    save_result_and_mark_completed(key, result)
    return success
catch error:
    record_failure_for_retry(key, error)
    return retry_or_escalate
~~~

This is design pseudocode, not an OCI Functions handler ready to deploy verbatim.

Acquiring the processing claim must be atomic. If code only does "read to check, then write," two workers can simultaneously believe they are first. A lease or equivalent mechanism enables recovery if a process dies mid-flight.

If external side effects and the state table are not in the same transaction, a failure window still exists: the effect happened before completion was recorded. In that case, use receiver-side idempotency keys, unique constraints, outbox patterns, or reconciliation. A simple `processed_events` table does not guarantee exactly-once by itself.

### 9.2. Retries, error capture, and reconciliation

Classify failures so actions are deliberate:

- Transient errors like timeouts or throttling: retry with appropriate delay and bounds.
- Invalid data errors: record rejection status, reason, and data location for handling.
- Permission or configuration errors: alert operators; avoid infinite retry loops.
- Prolonged dependency outages: persist enough context to recover and reconcile later.

Do not assume a rule creates a persistent error queue automatically. If unfinished work must be retained, design a dedicated error store or recovery pipeline and check destination service capabilities.

Nor should adding Streaming as a second action be treated as an automatic fallback for a Function: the stream receiving an event does not prove the Function received or processed it. Monitor each branch independently.

### 9.3. Preventing automation loops

If a Function processes `incoming/a.csv` and then writes a new file also under `incoming/`, it can emit another event matching the rule.

One way to structure this:

- Inputs under `incoming/`.
- Outputs under `processed/` or a separate bucket.
- Condition matches only the input area.
- Processor re-validates scope and deduplication keys.

For automation mutating Compute or database resources, apply the same rule: identify which events are emitted by the processor's own actions and prevent them from triggering unintended loops.

## 10. Cost control and operational change management

Actual costs depend on triggered destinations and downstream work. When estimating, account for Functions, streams, subscribers, logs, storage, and backend APIs.

For an initial estimate:

~~~text
Expected deliveries ≈ matched events × enabled actions
~~~

This is a simplified baseline model excluding retries, duplicate deliveries, and multiple matching rules. For example, 2,000 matched events with two actions generate about 4,000 deliveries in the baseline model; do not equate that directly to 4,000 completed business tasks or 4,000 billing units.

Practical controls:

- Filter to the exact change types and resources at the rule level.
- Send emails only for changes requiring human action.
- Cap the amount of work a Function can fan out.
- Monitor spikes in events, invocations, and consumer lag.
- Set retention periods for logs, stream data, and results according to need.
- Check current pricing, limits, and quotas for each service before large rollouts.

### 10.1. Verifiable change rollout

A sound procedure for critical rules:

1. Store the condition, action config, and purpose description in project change control.
2. Test with valid payloads and cases that must be excluded.
3. Verify in a practice compartment with scoped permissions.
4. Read back the configuration after deployment.
5. Emit a controlled new event and trace the entire path.
6. Monitor delivery failures and business outputs after enabling.

When swapping an active action, avoid accidentally running two paths that process the same job. If parallel execution is needed during cutover, processors must enforce deduplication.

### 10.2. Stopping rules and cleaning up lab resources

Disable a rule with:

~~~bash
oci events rule update \
  --region "$REGION" \
  --rule-id "$RULE_ID" \
  --is-enabled false \
  --wait-for-state ACTIVE
~~~

Read back the rule to confirm `isEnabled` is off. Work already delivered or started at targets must still be checked separately; disabling a rule does not undo side effects that already occurred.

After verification, delete objects and resources created solely for the lab if no longer needed. For shared topics, subscriptions, Functions, or streams, remove only the configuration tied to the lab within your assigned scope. If retaining the bucket and object events are no longer needed, disable object event emission on the bucket.

## 11. Applying the same method to Compute and Oracle databases

The Object Storage scenario makes the path easy to see, and the same design method applies to other OCI services:

1. Select the exact event type from the source service catalog.
2. Inspect the payload and verify which fields are actually usable.
3. Scope the compartment and resource group to react to.
4. Identify the final human or system recipient.
5. Attach appropriate actions and verify end-to-end.
6. Design permissions, deduplication, error capture, and reconciliation.

For a database backup operation, distinguish an "operation finished" event from concluding the backup succeeded. Draw conclusions only after checking event definitions, result fields, or authoritative resource state. Never invent event names by string-concatenating patterns from another service's examples.

For automated responses on Compute, start with alerting or status-check actions. When progressing to infrastructure-mutating actions, clearly define resource scope, execution preconditions, and recovery steps if the action runs twice.

A complete configuration for this lesson requires an explainable condition, justified target selection, evidence of both matching and non-matching cases, and an operational plan when targets fail. Simply seeing a rule in `ACTIVE` state does not satisfy those criteria.
