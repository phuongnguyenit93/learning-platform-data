# Integrating Kafka Clients with Event Hubs

> **Chapter:** Events and Streaming Data  
> **Module:** `CLOUD_PROVIDERS_AZURE` — Exploring the Microsoft Azure ecosystem from subscriptions, resource groups, and Entra ID to virtual networks, compute services, storage, and data. Learn how to deploy, monitor, secure, and control the cost of an application architecture on Azure.

## Lesson Objectives

Upon completing this lesson, you will be able to:

1. Explain why **Azure Event Hubs provides an Apache Kafka-compatible endpoint** and distinguish it from operating your own Kafka cluster.
2. Map **Event Hubs namespace, event hub, partition, consumer group, Kafka topic, producer, consumer, and offset** into an operable streaming architecture.
3. Connect Kafka clients via **SASL_SSL/PLAIN with a connection string**, understand Microsoft Entra ID authentication options, and prevent credential leaks.
4. Provision appropriate Event Hubs resources, configure **bootstrap server, topic, and group.id**, and send/read events using **Python confluent-kafka**.
5. Distinguish **at-least-once**, **consumer offset commit**, **per-partition ordering**, duplicate handling, retention, and replay.
6. Design partition keys, concurrency, backpressure, batching, quotas, and consumer lag monitoring.
7. Understand **Kafka API compatibility limits**: broker administration, topic creation, log compaction, transactions, and Kafka-cluster-specific features.
8. Diagnose authentication/TLS/network issues, unknown topics, rebalances, offset-out-of-range, throttling, and latency; apply security and cost optimization practices.

## 1. Real-World Scenario: Using Kafka Libraries Without Operating Kafka Brokers

An e-commerce platform has Java and Python applications emitting purchase events. The development team already uses Kafka libraries to publish and consume events. The operations team wants to offload managing:

- Broker instances, partition distribution, and storage disks.
- Installing, upgrading, and monitoring Kafka controllers/brokers.
- Building custom monitoring, failover, and availability for Kafka infrastructure.
- Managing connectivity across multiple consumer teams.

**Azure Event Hubs** is a managed streaming ingestion service on Azure. An **Event Hubs namespace** on a supported tier provides a **Kafka-compatible endpoint**, allowing many Kafka clients to connect using the Kafka protocol **without deploying a separate Kafka cluster**.

Example:

~~~mermaid
flowchart LR
    P1["Order service\nKafka producer"]
    P2["Checkout gateway\nKafka producer"]
    EP["Event Hubs namespace\nKafka endpoint :9093"]
    EH["Event Hub: orders-events\nKafka topic"]
    PT["Partitions: 0,1,2,3"]
    C1["Analytics\nConsumer group A"]
    C2["Fraud detection\nConsumer group B"]
    DB["Databases / Data Lake"]
    P1 -->|"SASL_SSL"| EP
    P2 -->|"SASL_SSL"| EP
    EP --> EH --> PT
    PT --> C1 --> DB
    PT --> C2 --> DB
~~~

Key takeaway: **Event Hubs is the Event Hubs service**, not a hidden cluster of Kafka brokers under your full control. Protocol compatibility lets you reuse most client code, yet **it does not mean every Kafka API or broker-admin feature behaves identically to Apache Kafka**.

### Alternatives to keep in mind

| Need | Solution to evaluate |
| --- | --- |
| High-speed event/telemetry ingestion via Kafka producers/consumers | **Azure Event Hubs Kafka endpoint** |
| Business commands needing queues, dead-lettering, sessions, message locks | **Azure Service Bus** |
| Routing Azure/CloudEvents notifications to handlers, webhooks, or Functions | **Azure Event Grid** |
| Full control over Kafka brokers, log compaction, advanced Kafka internals | **Apache Kafka / managed Kafka service** with appropriate support |
| Stream analytics after ingestion | **Stream Analytics, Spark, Fabric, or compatible consumer frameworks** |
| Running consumers in a language lacking a suitable Kafka SDK | Evaluate **Event Hubs native AMQP SDK** and integration options |

**Never swap a Service Bus order-processing queue for Event Hubs merely because both transport messages.** Service Bus and Event Hubs differ fundamentally in storage, consumption, settlement, and retention.

## 2. Mapping Kafka Concepts to Event Hubs

### 2.1. Corresponding entities

| Apache Kafka | Azure Event Hubs | Explanation |
| --- | --- | --- |
| Kafka cluster/brokers | **Azure-managed Event Hubs namespace and endpoint** | You do not access or configure brokers like self-managed Kafka |
| Kafka topic | **Event Hub** | The topic name in a Kafka client maps to an existing event hub name |
| Partition | **Event Hub partition** | Unit of ordered log sharding and parallel consumption |
| Kafka producer | **Kafka-compatible producer client** | Sends records to the event hub via the Kafka endpoint |
| Kafka consumer | **Kafka-compatible consumer client** | Polls records from partitions |
| Kafka consumer group | **Compatible consumer group** | Uses `group.id` to coordinate consumers and offsets; verify group mapping/authorization on Event Hubs |
| Kafka record key | **Client-protocol partition routing key** | Same key routes consistently to the same partition under stable configuration |
| Kafka offset | **Record position in a partition** | Used for checkpointing/replay; not a business MessageId |
| Kafka bootstrap server | **Namespace Kafka endpoint** | Formatted as `<namespace>.servicebus.windows.net:9093` |
| Kafka broker administration | **Azure portal / CLI / ARM / Bicep / Terraform** | Provision event hubs, partitions, retention, throughput, and networking in Azure |

One namespace holds multiple Event Hubs, each representing a distinct event stream. Example:

~~~text
Event Hubs namespace: ehns-shop-dev
  Kafka endpoint: ehns-shop-dev.servicebus.windows.net:9093

  Event Hub: orders-events
    partitions: 0, 1, 2, 3

  Event Hub: payment-events
    partitions: 0, 1

  Event Hub: telemetry
    partitions: 0, 1, 2, 3, ...
~~~

Partition counts are illustrative. **Do not rely on Kafka clients auto-creating topics**; provision Event Hubs ahead of time via the **Azure management plane**.

### 2.2. The Kafka endpoint is namespace-level

Kafka clients do not connect to addresses like `kafka-1.example:9092` or your own broker bootstrap list. Instead:

~~~text
bootstrap.servers = ehns-shop-dev.servicebus.windows.net:9093
topic             = orders-events
security.protocol = SASL_SSL
sasl.mechanisms   = PLAIN
~~~

Port **9093** on the Kafka endpoint uses TLS; **never disable TLS** for a “quick test” when troubleshooting. Firewall, proxy, or VNet restrictions require verifying this port. The Event Hubs native AMQP endpoint uses a different protocol and port model; never replace Kafka bootstrap with an AMQP connection URI.

### 2.3. Kafka group.id and Event Hubs consumer groups

Kafka clients typically specify:

~~~properties
group.id=orders-analytics-lab
~~~

Clients sharing a `group.id` coordinate dividing topic partitions within the group as supported. The fraud group uses a different ID from analytics to **read every event independently**. Event Hubs also has a service-side **consumer group** concept; configure group names/mappings and permissions according to your protocol version, SDK, and namespace policy.

To keep this lab easy to control, we will **create the consumer group in Azure** matching `group.id`, then verify actual Kafka client behavior. Never assume any arbitrary Kafka group name automatically receives data-plane rights or auto-creates resources across all environments.

### 2.4. Partitions are not consumer groups

Suppose `orders-events` has four partitions and group `analytics-lab` runs:

- **One consumer instance:** the consumer may be assigned all four partitions.
- **Two consumer instances:** two consumers split the partitions, each partition handled by one group member per group assignment.
- **Six consumer instances:** no more than four members can concurrently process those four partitions under one-member-per-partition assignment; excess members sit idle.

**Adding consumer replicas does not create more partitions** and cannot scale throughput infinitely. A separate group `fraud-lab` can read the exact same partitions **independently** of `analytics-lab`.

### 2.5. Offsets do not delete records

A Kafka consumer reading up to offset 105 and committing does not erase offsets 0–105 from the Event Hub. Events stay retained per **retention policy**; the consumer merely saves **its processed position** to resume next time.

Unlike Service Bus PeekLock/Complete, Event Hubs does not remove an event from the stream because one consumer finished it. Choose Event Hubs when you need **replay within retention** and multiple independent reader groups.

## 3. Records, Keys, Partitions, Offsets, and Event Ordering

### 3.1. Visualizing a partition log

~~~text
Topic / Event Hub: orders-events

Partition 0:
  offset 0: OrderCreated(orderId=ORD-101)
  offset 1: OrderPaid(orderId=ORD-101)
  offset 2: OrderShipped(orderId=ORD-101)

Partition 1:
  offset 0: OrderCreated(orderId=ORD-202)
  offset 1: OrderCancelled(orderId=ORD-202)
~~~

Within one partition, records follow write/read order by offset. **There is no absolute total order between partition 0 and partition 1.**

### 3.2. Designing the message contract

Example JSON value:

~~~json
{
  "eventId": "evt-ORD-101-created",
  "eventType": "OrderCreated",
  "schemaVersion": 1,
  "orderId": "ORD-101",
  "occurredAt": "2026-11-20T09:00:00Z",
  "amount": 2500000,
  "currency": "VND"
}
~~~

A Kafka record should look like:

~~~text
topic:   orders-events
key:     ORD-101
value:   UTF-8 JSON above
headers: eventType=OrderCreated, schemaVersion=1
timestamp: producer/broker timestamp per config and support
~~~

**A Kafka record key is not an encryption key.** It is a data routing key, typically used for partitioning and potentially affecting processing order. Never place secrets or sensitive personal data into keys or headers.

### 3.3. Choosing keys by entity needing order

For order state-change streams, using `orderId` as the key is a sound choice. When partition count and partitioner/serialization remain stable, records sharing a key land in the same partition, preserving per-partition order.

However:

- Changing **partition count**, partitioning algorithms, or producer implementations can alter routing for the same key; evaluate order preservation across topology changes.
- Concurrent publisher streams, retries/out-of-order sends, or application sequencing can make arrival order diverge from business expectations.
- An overly common key—such as `region=VN` for 95% of traffic—creates a **hot partition**.
- Consumer side effects into databases must enforce any required ordering themselves; the broker does not turn the whole system into a serial transaction.

### 3.4. Do not depend on offsets as business IDs

An offset is meaningful only within **one partition** of a topic at a point in time; offset 10 on partition 0 is unrelated to offset 10 on partition 1. For deduplication and tracing, rely on `eventId`/`orderId` in the payload alongside topic/partition/offset for technical diagnostics.

A record can be received multiple times if the consumer finishes processing but crashes before committing the offset. Consumers must be **idempotent**.

## 4. Requirements for Using Event Hubs' Kafka Endpoint

### 4.1. Check tier and support

The Kafka endpoint is available on **Event Hubs tiers supporting Kafka, such as Standard, Premium, and Dedicated**. Never build a lab on a **Basic** namespace expecting full Kafka client support. Tier policies, regions, limits, and features can change; check your namespace's actual configuration when deploying.

### 4.2. Lab prerequisites

- Azure subscription with permission to use and create required resources.
- Event Hubs namespace on a Kafka-supported tier, plus Event Hub `orders-events`.
- A dedicated lab consumer group, e.g., `orders-analytics-lab`.
- Kafka client supporting **TLS + SASL PLAIN** (e.g., Python `confluent-kafka`).
- SAS policy/connection string granting **Send** for producers and **Listen** for consumers, or an appropriate Entra OAuth setup.
- Client host able to reach TCP **9093** on the namespace endpoint.
- Azure Monitor and application logs to verify throughput, errors, and lag.
- Never use a production namespace or live data for tests without approval.

### 4.3. Connection path

~~~mermaid
flowchart LR
    APP["Kafka client\nlaptop/VM/AKS"]
    DNS["DNS namespace FQDN"]
    TLS["TLS + SASL authentication\nport 9093"]
    NS["Event Hubs namespace\nKafka front end"]
    EH["Event Hub / Kafka topic\norders-events"]
    APP --> DNS --> TLS --> NS --> EH
~~~

TLS verifies the namespace certificate; SASL authenticates the client credential per configured mechanism. Network routing and authorization **are two separate layers**: passing TCP/TLS does not guarantee Publish/Consume permissions.

### 4.4. Cost notes

Provisioning namespaces/event hubs incurs charges based on tier, throughput/capacity, retained data, capture, networking, and observability. **Fixed dollar estimates are not provided** because pricing, quotas, and availability vary by region and subscription. Use the Azure Pricing Calculator and Cost Management before creating lab resources.

## 5. Creating Event Hubs Resources via Portal or Azure CLI

### 5.1. Portal workflow

1. In the Azure portal, confirm the exact **subscription** and **resource group**.
2. Create an **Event Hubs namespace** in an approved region on a Kafka-supported tier.
3. Create an **Event Hub** named `orders-events` with an approved partition count, e.g., 4 for the lab.
4. Set retention per requirements and tier limits; never assume infinite retention.
5. Create a **consumer group** named `orders-analytics-lab` per your model.
6. Configure least-privilege SAS policies or Entra ID/RBAC as supported by your client setup.
7. Verify namespace status, networking/firewall/private endpoint, and TCP 9093 reachability.
8. Enable appropriate metrics, alerts, and diagnostic settings before load testing.

### 5.2. Creating via CLI in an authorized lab

The following commands are **write operations that create resources and may incur costs**. Run only in an approved lab subscription and resource group.

~~~bash
az login

az account show \
  --query "{subscription:name, subscriptionId:id, tenantId:tenantId}" \
  --output json

# Replace with your actual lab subscription ID.
az account set --subscription "<SUBSCRIPTION_ID>"

RG="rg-eventhubs-kafka-lab"
LOCATION="southeastasia"
EHNS="ehns-kafka-unique-demo"
EVENTHUB="orders-events"
GROUP="orders-analytics-lab"

az group create \
  --name "$RG" \
  --location "$LOCATION"

# Replace EHNS with a valid, globally unique namespace name.
az eventhubs namespace create \
  --resource-group "$RG" \
  --name "$EHNS" \
  --location "$LOCATION" \
  --sku Standard

az eventhubs eventhub create \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --name "$EVENTHUB" \
  --partition-count 4

az eventhubs eventhub consumer-group create \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --eventhub-name "$EVENTHUB" \
  --name "$GROUP"
~~~

**Verify at runtime:** CLI versions and Azure policies may require extra parameters or restrict regions/tiers. Check `az eventhubs namespace create --help` and `az eventhubs eventhub create --help` first. Never blindly raise quotas or upgrade to pricier tiers to work around an undiagnosed error.

### 5.3. Resource readback

~~~bash
az eventhubs namespace show \
  --resource-group "$RG" \
  --name "$EHNS" \
  --query "{name:name, location:location, sku:sku, status:status}" \
  --output json

az eventhubs eventhub show \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --name "$EVENTHUB" \
  --output json

az eventhubs eventhub consumer-group list \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --eventhub-name "$EVENTHUB" \
  --output table
~~~

Azure management commands talk to the **management plane**; they do not prove a Kafka producer can connect to the data plane over TCP 9093.

### 5.4. Do not use Kafka AdminClient to auto-create Event Hubs

Kafka clients often auto-create topics when permitted by a Kafka broker. With Event Hubs, an **Event Hub is an Azure resource** that must be provisioned via portal/CLI/ARM/Bicep/Terraform or supported management APIs. Do not rely on Kafka's `auto.create.topics.enable=true`.

If a producer reports `UnknownTopicOrPartition`, verify the **exact Event Hub name** and namespace first rather than attempting unsupported Kafka admin topic creation.

## 6. Kafka Client Authentication: SASL_SSL, SAS, and Microsoft Entra ID

### 6.1. SASL_SSL/PLAIN with Event Hubs connection string

A common starting config for a Kafka client:

~~~properties
bootstrap.servers=<namespace>.servicebus.windows.net:9093
security.protocol=SASL_SSL
sasl.mechanisms=PLAIN
sasl.username=$ConnectionString
sasl.password=<EVENT_HUBS_NAMESPACE_CONNECTION_STRING>
~~~

This is an **illustrative configuration**, not a ready-to-use file. Replace the hostname and connection string with real values, protect secrets, and audit access.

- `sasl.username` must be the literal `$ConnectionString`, not an Entra username.
- `sasl.password` must be the **entire** Event Hubs connection string supported by the Kafka endpoint, not just `SharedAccessKey`.
- Connection strings typically contain `Endpoint=sb://<namespace>.servicebus.windows.net/;SharedAccessKeyName=...;SharedAccessKey=...`.
- Use a **namespace-level connection string appropriate for the Kafka endpoint** per protocol/tier guidance; do not blindly paste strings containing `EntityPath` meant for the native Event Hubs SDK.
- `SASL_SSL` runs over TLS. `PLAIN` sends credentials inside **an encrypted connection**—it does not disable TLS.
- Never try `SASL_PLAINTEXT` or disable TLS verification to work around network or auth errors.

### 6.2. Least-privilege permissions for producers and consumers

~~~text
orders-producer:
  SAS policy / principal with Send permission

analytics-consumer:
  SAS policy / principal with Listen permission
~~~

Never hand out `RootManageSharedAccessKey` to every workload. Publishers, consumers, and Event Hub administrators are **distinct roles**. When using SAS:

1. Separate Send and Listen credentials within the policy scopes supported by the Kafka endpoint.
2. Store secrets in Key Vault, a secret manager, or CI/CD secret injection.
3. Never bake connection strings into source code, Docker images, or logs.
4. Maintain a rotation plan and test client reconnection.
5. Check entity vs. namespace policy behavior, as connection string rules can differ between Kafka and the native AMQP SDK.

### 6.3. Microsoft Entra ID / OAuth

Event Hubs supports **Microsoft Entra ID** authentication for compatible Kafka client/OAuth setups. When running with managed identities or workload identities on Azure, evaluate Entra ID to avoid managing long-lived SAS keys.

Design steps:

1. Choose an authorized identity/principal.
2. Assign the right data-plane role, such as **Azure Event Hubs Data Sender** or **Azure Event Hubs Data Receiver**, at minimal scope.
3. Choose a Kafka SDK supporting OAuth/SASL and configure token acquisition/refresh per SDK and Event Hubs guidance.
4. Verify token audience/scope, lifetime, and refresh before expiry.
5. Never log access tokens.

**You cannot keep `PLAIN` and simply drop an arbitrary OAuth access token into `sasl.password`.** Kafka Java, librdkafka/confluent-kafka, and various frameworks implement different OAuth callbacks. This lab uses SASL_SSL/PLAIN to keep protocol mechanics clear; production can adopt Entra/OAuth where supported by client and runtime.

### 6.4. Authentication differs from networking

~~~text
DNS namespace FQDN
  → TCP 9093
    → TLS trust + SNI
      → SASL authentication
        → Send/Listen authorization
          → Event Hub topic
            → Consumer group / offsets
~~~

- DNS resolving does not prove TCP 9093 is open.
- TLS handshake succeeding does not prove SASL credentials are valid.
- Valid credentials do not guarantee Send/Listen authorization.
- Read authorization does not guarantee the consumer configured the right group or offset.

## 7. Network, Firewall, Private Endpoint, and TLS

### 7.1. Public Kafka endpoint

If the namespace permits public network access per policy:

~~~text
<namespace>.servicebus.windows.net:9093
~~~

Clients must be allowed to reach the endpoint on port **9093**. Never open the entire Internet just to fix a timeout. Note that Kafka uses raw TCP/TLS with metadata/heartbeats and does not automatically traverse standard HTTP proxies.

### 7.2. Testing DNS, TCP, and TLS

Linux/macOS (if tools are installed):

~~~bash
nslookup ehns-kafka-unique-demo.servicebus.windows.net

nc -vz ehns-kafka-unique-demo.servicebus.windows.net 9093

openssl s_client \
  -connect ehns-kafka-unique-demo.servicebus.windows.net:9093 \
  -servername ehns-kafka-unique-demo.servicebus.windows.net \
  -brief
~~~

Windows PowerShell:

~~~powershell
Resolve-DnsName ehns-kafka-unique-demo.servicebus.windows.net

Test-NetConnection ehns-kafka-unique-demo.servicebus.windows.net -Port 9093
~~~

These are **read-only checks** of DNS, networking, and TLS; **they do not prove SASL authorization**. If TLS succeeds yet the client reports authentication failed, inspect permissions and connection strings rather than disabling TLS.

### 7.3. Private endpoint and DNS

When a namespace uses a Private Endpoint:

- The namespace/tier must support private connectivity.
- Clients need routing to the private IP over VNet, VPN, or ExpressRoute as designed.
- Private DNS Zones / forwarders must resolve the **namespace hostname** to the private endpoint per Azure architecture.
- Firewalls, NSGs, UDRs, and proxies must not block port 9093 or return paths.
- TLS SNI/certificate validation keeps using the valid FQDN; **never replace it with a private IP** and turn off validation.
- Managed identity/RBAC or SAS authorization remains a separate requirement not replaced by private networking.

### 7.4. Proxies, idle timeouts, and NAT

Kafka clients maintain long-lived TCP connections, heartbeats, and metadata fetches. Traditional HTTP proxies rarely handle Kafka TCP/TLS properly. For AKS/container workloads, inspect egress NAT/SNAT, idle timeouts, DNS, TCP passthrough, and network quotas. Drops after idle periods are often networking issues rather than offset bugs.

### 7.5. Do not hardcode frontend IP addresses

TLS validates the namespace hostname. Never rely on current Azure frontend IPs or disable certificate verification, as IPs rotate and disabling checks weakens security. Fix DNS and routing per the Event Hubs model.

## 8. Python Example with confluent-kafka

### 8.1. Files and dependencies

Create a local lab directory without adding extra files into the module:

~~~text
eventhubs-kafka-lab/
  requirements.txt
  kafka_settings.py
  producer.py
  consumer.py
~~~

`requirements.txt`:

~~~text
confluent-kafka
~~~

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
~~~

On PowerShell, use the PowerShell virtual environment activation script. For production, pin versions in a lockfile and verify `librdkafka` compatibility.

### 8.2. Configuration and secrets

Inject two environment variables from a secret manager or equivalent mechanism:

~~~text
EH_KAFKA_BOOTSTRAP=ehns-kafka-unique-demo.servicebus.windows.net:9093
EH_KAFKA_CONNECTION_STRING=<INJECT_SECRET_AT_RUNTIME>
~~~

**Never commit, echo, or log** connection strings. In production, issue separate Send and Listen credentials per workload; a lab may use a suitably scoped policy if permitted by administrators.

`kafka_settings.py`:

~~~python
import os


def kafka_base_config() -> dict:
    bootstrap = os.environ["EH_KAFKA_BOOTSTRAP"]
    connection_string = os.environ["EH_KAFKA_CONNECTION_STRING"]

    return {
        "bootstrap.servers": bootstrap,
        "security.protocol": "SASL_SSL",
        "sasl.mechanisms": "PLAIN",
        "sasl.username": "$ConnectionString",
        "sasl.password": connection_string,
        "client.id": "orders-kafka-lab",
    }
~~~

This requires an **Event Hubs namespace connection string**, not an Azure Storage string or HTTP URL. When using Entra/OAuth, replace the authentication settings accordingly rather than using this `PLAIN` configuration.

### 8.3. Producer: sending keyed records and verifying delivery

`producer.py`:

~~~python
import json
import uuid

from confluent_kafka import Producer
from kafka_settings import kafka_base_config


TOPIC = "orders-events"

config = kafka_base_config()
config.update({
    "client.id": "orders-producer-lab",
    "acks": "all",
    "compression.type": "none",
})

producer = Producer(config)
delivered = 0
failed = 0


def on_delivery(error, message):
    global delivered, failed

    if error is not None:
        failed += 1
        print("Delivery failed:", str(error))
    else:
        delivered += 1
        print(
            "Delivered:",
            message.topic(),
            "partition=", message.partition(),
            "offset=", message.offset(),
        )


for n in range(6):
    order_id = f"ORD-{1000 + n}"
    payload = {
        "eventId": str(uuid.uuid4()),
        "eventType": "OrderCreated",
        "schemaVersion": 1,
        "orderId": order_id,
        "amount": (n + 1) * 1000000,
    }

    producer.poll(0)

    producer.produce(
        topic=TOPIC,
        key=order_id.encode("utf-8"),
        value=json.dumps(payload).encode("utf-8"),
        headers=[
            ("eventType", b"OrderCreated"),
            ("schemaVersion", b"1"),
        ],
        on_delivery=on_delivery,
    )

pending = producer.flush(timeout=30)
print("delivered=", delivered, "failed=", failed, "pending=", pending)

if failed or pending:
    raise RuntimeError("Batch delivery was not fully confirmed")
~~~

Meaning:

- `produce()` mainly places records into a local buffer; **it does not mean the broker persisted them yet**.
- `on_delivery` reports acknowledgment or error; `flush` waits for pending messages.
- `key=order_id` routes records for the same order to the same partition while partitioner and partition count stay stable.
- `acks=all` does not guarantee **exactly-once processing** at the consumer.
- `compression.type=none` keeps the lab less dependent on Kafka codec support.
- Production code must handle full local buffers, retries/backoff, idempotent event IDs, batching, rate limiting, and metrics.

Sample output:

~~~text
Delivered: orders-events partition= 2 offset= 10
Delivered: orders-events partition= 1 offset= 13
...
delivered= 6 failed= 0 pending= 0
~~~

Exact partition and offset numbers vary. Business message IDs belong in the payload; never treat offsets as business identifiers.

### 8.4. Producer errors

| Symptom | Likely cause | Remediation |
| --- | --- | --- |
| Client buffer full | Producing faster than network can flush | Backpressure, `poll`, tune batching |
| Authentication failed | Wrong SAS username/password or policy | Verify secret and credentials |
| Authorization failed | Missing Send rights or wrong scope | Check RBAC/SAS policy |
| Unknown topic | Event Hub not created or typo | Inspect Azure resource |
| Request timeout | Network/throttling or slow server | Monitor, add bounded retries |
| Record too large | Payload exceeds tier/API limit | Shrink payload, store in Blob and send reference |
| Unsupported API/codec | Client requested unsupported feature | Adjust configuration or architecture |

**Never print the full producer config when debugging**, because `sasl.password` contains credentials.

## 9. Consumer: Poll, Process, Then Commit Offset

### 9.1. Dedicated lab consumer group

If the group does not exist yet:

~~~bash
az eventhubs eventhub consumer-group create \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --eventhub-name "$EVENTHUB" \
  --name "orders-analytics-lab"
~~~

Set `group.id=orders-analytics-lab` in the Kafka client. The fraud consumer should use a different ID to read independently. Verify group mapping behavior in your SDK/namespace, and never use a production group for testing because committing alters shared read positions.

### 9.2. Python consumer with manual commit

`consumer.py`:

~~~python
import json
import time

from confluent_kafka import Consumer, KafkaException
from kafka_settings import kafka_base_config


TOPIC = "orders-events"
MAX_MESSAGES = 6
DEADLINE_SECONDS = 90

config = kafka_base_config()
config.update({
    "client.id": "orders-analytics-consumer-lab",
    "group.id": "orders-analytics-lab",
    "auto.offset.reset": "earliest",
    "enable.auto.commit": False,
})

consumer = Consumer(config)
count = 0
deadline = time.monotonic() + DEADLINE_SECONDS

try:
    consumer.subscribe([TOPIC])

    while count < MAX_MESSAGES and time.monotonic() < deadline:
        message = consumer.poll(timeout=5.0)

        if message is None:
            print("No events received in 5 seconds")
            continue

        if message.error() is not None:
            raise KafkaException(message.error())

        payload = json.loads(message.value().decode("utf-8"))
        event_id = payload["eventId"]
        order_id = payload["orderId"]

        # Print only in demo; production requires durable writes/idempotency.
        print(
            "Processed", event_id, order_id,
            "partition=", message.partition(),
            "offset=", message.offset(),
        )

        # Commit only after processing succeeds.
        consumer.commit(message=message, asynchronous=False)
        count += 1

finally:
    consumer.close()

print("Processed count:", count)
~~~

**Key points:**

- `enable.auto.commit=False` stops the client from periodically auto-committing before business work completes.
- `commit(message=message, asynchronous=False)` commits the position after the record is successfully handled.
- Demo code only prints; production must persist state durably **before committing**.
- If parsing or processing fails, the exception exits the loop without committing the failing record.
- `consumer.close()` leaves the group cleanly when the script exits.
- The 90-second deadline prevents the lab script from hanging indefinitely if fewer than six records arrive.

### 9.3. Manual commit is not yet exactly-once

~~~text
Record received
    ↓
Validate + idempotency check
    ↓
Database write succeeds
    ↓
Worker crashes BEFORE offset commit
    ↓
Same record can be received again
~~~

That is why idempotency is needed, such as a unique constraint on `eventId` and a business transaction. Kafka offsets track read progress, not an atomic transaction across Azure SQL / Cosmos DB.

### 9.4. Never commit past a failing record

Within **the same partition**:

~~~text
offset 10: processing fails, not committed
offset 11: processing succeeds and commits position after offset 11
~~~

Committing the higher offset means restarts may **skip offset 10**. Never swallow exceptions on a failing record and keep committing subsequent records in that partition. In production:

1. Separate transient failures from malformed events.
2. Retry transient failures with bounded backoff.
3. Quarantine poison events to durable storage when deciding to skip.
4. Commit only after work or durable error handling succeeds.
5. Track commit progress per partition when processing concurrently.

### 9.5. When does `auto.offset.reset=earliest` take effect?

It primarily applies **when the group has no valid committed offset yet** or when the committed offset fell outside retention per client semantics. Once a group has valid committed offsets, changing config to `earliest` does not rewind it to the beginning.

For lab replays, use a **new group** or an authorized offset reset procedure; only data **still within retention** can be replayed. Never reset production groups casually.

### 9.6. Consumer groups and partition assignment

~~~text
orders-events (4 partitions)
  group analytics-lab:
    consumer A → partition 0, 1
    consumer B → partition 2, 3

  group fraud-lab:
    consumer C → partition 0, 1, 2, 3
~~~

Illustrative diagram. Members in **the same group** split partitions, while different groups read independently. When members join or leave, **rebalances** reassign partitions, requiring safe handling of in-flight records and offsets.

## 10. Integrating Java Kafka Clients

If a Java app already uses `org.apache.kafka.clients.producer.KafkaProducer` or `KafkaConsumer`, most record-processing logic can be reused. Update **bootstrap, authentication, and broker-specific settings**, and verify which API features Event Hubs actually supports.

### 10.1. Java client.properties

~~~properties
bootstrap.servers=<namespace>.servicebus.windows.net:9093
security.protocol=SASL_SSL
sasl.mechanism=PLAIN
sasl.jaas.config=org.apache.kafka.common.security.plain.PlainLoginModule required username="$ConnectionString" password="<FULL_NAMESPACE_CONNECTION_STRING>";
client.id=orders-java-client
~~~

This is an **illustrative** config with secret placeholders. Never commit files with real connection strings to Git or log JAAS configs. In Java, the property name is `sasl.mechanism` (singular), whereas `confluent-kafka` uses `sasl.mechanisms` (plural). **Verify the exact property names for your SDK.**

### 10.2. Java producer concept

~~~java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, bootstrap);
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
          StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
          StringSerializer.class.getName());

// Load security.protocol, sasl.mechanism, and sasl.jaas.config
// from managed secret configuration.

try (Producer<String, String> producer = new KafkaProducer<>(props)) {
    ProducerRecord<String, String> record = new ProducerRecord<>(
        "orders-events",
        "ORD-101",
        "{\"eventType\":\"OrderCreated\",\"orderId\":\"ORD-101\"}"
    );
    producer.send(record).get();
    producer.flush();
}
~~~

This is an **illustrative snippet**, omitting full imports, `main`, and secret loading. `send(record).get()` lets you observe results/exceptions synchronously in a lab, whereas production apps typically use async batching and delivery callbacks. Never treat `flush` alone as per-record error checking.

### 10.3. Java consumer

Logical config:

~~~properties
group.id=orders-analytics-lab
enable.auto.commit=false
auto.offset.reset=earliest
key.deserializer=org.apache.kafka.common.serialization.StringDeserializer
value.deserializer=org.apache.kafka.common.serialization.StringDeserializer
~~~

The consumer calls `poll`, persists durable state, and calls `commitSync` or equivalent. When processing concurrently, never commit past an unfinished earlier record on the same partition. Attach a rebalance listener when graceful partition revocation and pending-work flushing are required.

### 10.4. Kafka Connect and Kafka Streams

Several Kafka ecosystem tools work with Event Hubs' Kafka endpoint under compatible configs, yet **not every Kafka Connect connector or Kafka Streams topology is fully compatible**. Before adopting them, check:

- Does the connector rely on the Kafka Admin API to auto-create topics?
- Does it require **log compaction** or internal changelog/repartition topics?
- Does it depend on Kafka transactional APIs or idempotent producer modes specific to native Kafka brokers?
- Does it require a Confluent-compatible Schema Registry REST protocol or a separate endpoint?
- Does the framework read/commit offsets and metrics via standard Kafka groups or a custom store?
- Have the exact SDK version, SASL/OAuth, port 9093 networking, and real throughput passed integration tests?

**`KafkaProducer` connecting successfully does not prove all Kafka Connect/Streams features work.** Test your exact topology with your target framework version and workload.

## 11. Consumer Lag, Retention, and Replay

### 11.1. Consumer lag is an offset distance

\[
\text{Lag}_{p}\approx\text{LatestOffset}_{p}-\text{CommittedOffset}_{p}
\]

Example:

~~~text
Partition 0 latest offset:      10000
Committed offset group A:        9600
Approximate lag:                  400
~~~

Lag measures record/offset distance; **400 records does not automatically mean 400 seconds behind**. To evaluate business delay, inspect event timestamps, ingress rates, and processing times.

### 11.2. Retention is a bounded window

Event Hubs keeps records per retention policy and tier limits. Consumer commits do not remove events from the stream. However, if a group pauses too long, older offsets drop out of retention.

When that happens:

- `earliest` moves the consumer to the **oldest retained** record; expired records cannot be recovered from the stream.
- `latest` starts from the end when no valid offset exists, skipping prior data.
- `none` throws an error when no valid offset exists.

Never treat short retention as a **permanent event store**. For long-term replay, design external storage such as Event Hubs Capture / Data Lake / Blob plus an audited replay workflow.

### 11.3. Multiple groups and independent positions

~~~text
orders-events partitions
  group analytics-lab:  p0=950, p1=1200, ...
  group fraud-lab:      p0=900, p1=800, ...
~~~

Fraud lagging does not mean analytics is lagging, because offsets are independent. Still, both share the namespace/Event Hub's egress capacity; extra groups increase total reads and processing cost.

### 11.4. Why does lag grow?

- Consumer CPU/RAM shortage or heavy business logic.
- Downstream database/API throttling, locking, or rate limits.
- Fewer partitions than consumer replicas.
- Hot partition due to key skew.
- Constant group rebalances from heartbeat/poll timeouts.
- Large messages, heavy serialization/schema validation.
- Event Hubs namespace throughput throttling.
- Network latency, packet loss, or NAT idle timeout / SNAT exhaustion.

Never scale consumers blindly: with four partitions, eight members in one group cannot process eight partitions simultaneously because only four exist.

### 11.5. Broker metrics do not replace client lag

Azure Monitor offers namespace/Event Hub metrics such as incoming/outgoing messages, errors, or throttling per tier. However, total incoming message metrics **cannot tell what offset the analytics group committed**. Measure per-group/per-partition lag via Kafka client/framework metrics alongside Azure Monitor.

## 12. Kafka Protocol Compatibility Limits

### 12.1. Event Hubs is not self-managed Kafka brokers

Event Hubs exposes a **Kafka-compatible API subset** on Azure's service model. You have no access to internal Kafka brokers, ZooKeeper/KRaft, or broker disk logs.

| Assumption from self-managed Kafka | What to do with Event Hubs |
| --- | --- |
| Producers auto-create missing topics | Provision Event Hubs first via Azure management plane |
| Kafka AdminClient alters broker configs/replicas | Use Azure portal / CLI / IaC and tier features |
| `cleanup.policy=compact` is always available | Do not rely on Kafka log compaction |
| Kafka transactional producers work fully | Verify compatibility; do not assume exactly-once |
| Kafka Streams internal topics auto-create | Test and provision entities via Azure mechanisms |
| All Kafka client API versions work | Check supported versions and APIs |
| Raising partition count never affects ordering | Assess key routing, skew, and tier support |
| Infinite data retention is possible | Event Hubs retention is strictly bounded |
| Native Kafka ACLs / broker users | Use Azure SAS / Entra RBAC and network controls |
| Kafka broker JMX metrics available | Use Azure Monitor + client/app metrics |

### 12.2. Log compaction differs from retention

A native Kafka broker with `cleanup.policy=compact` retains the latest record per key. **Do not design Event Hubs' Kafka endpoint as a compacted Kafka changelog** unless a feature explicitly guarantees those semantics. Event Hubs focuses on event ingestion and time-based retention.

If your application needs a latest-state table, build a separate materialized view / state store in a database or cache updated by a stream processor with idempotency and replay support.

### 12.3. Transactions and exactly-once

Kafka SDKs support idempotent producers and transactional IDs against self-managed Kafka brokers. **Do not assume every transactional/idempotent Kafka API is supported identically on Event Hubs.** Verify the compatibility matrix for your tier, API, and client version.

Even on systems supporting Kafka transactions, updating Azure SQL / Cosmos DB and committing offsets do not automatically form one atomic transaction. Consumers still need idempotent durable processing and/or outbox patterns.

### 12.4. Record size, headers, and compression

- Keep payloads within your tier's event/message-size limits.
- Use compression/codecs supported by the endpoint; do not assume every `librdkafka` codec is accepted.
- For very large events, store payloads in Blob Storage and emit events with **authorized references**.
- Headers are metadata; exclude credentials and PII.
- Batching, linger, and retries raise throughput at the cost of latency or duplicate risk.

### 12.5. Schema Registry is not identical to Confluent REST API

Azure Event Hubs offers **Azure Schema Registry** for schema governance per service capabilities. However, **do not assume** it exposes every endpoint or compatibility behavior of Confluent Schema Registry's REST API. When using Avro/Protobuf/JSON serializers, verify SDK plugins, registration, schema IDs, and format/version compatibility.

## 13. Throughput, Partitions, and Backpressure

### 13.1. Choosing partition keys to avoid hot partitions

If 80% of events carry `region=VN` and you key by `region`, most traffic crowds onto one partition. One consumer member saturates while others sit idle with spare CPU.

If business logic requires **per-order** ordering, key by `orderId`, which distributes far better than `region`. Still test for key skew on massive orders or customers, and avoid altering partitioners or partition counts arbitrarily.

### 13.2. Estimating raw ingress

Suppose:

~~~text
Incoming:            10,000 events/second
Average payload:          2 KiB
Raw payload ingress:   19.53 MiB/s
~~~

Calculation:

\[
10{,}000\times2/1024\approx19.53\text{ MiB/s}
\]

This is **raw payload** before protocol overhead, Kafka headers, compression, and network retries. If two consumer groups read all records, total egress increases substantially over a single group. Size with real payloads, Azure tier capacity, and pricing.

### 13.3. Batching and latency

`linger.ms` and batch settings raise throughput by grouping records, while increasing wait times. Tune based on:

- Record size, peak traffic, and partition count.
- Target p95/p99 publish-to-consume latency.
- Broker/namespace throttling and producer buffer capacity.
- Supported compression codecs and client versions.
- Retries/backoff, message size, and fault tolerance.

Never optimize events/s in isolation at the expense of breaking latency SLOs.

### 13.4. Consumer backpressure

When consumers poll faster than the database can write, memory pressure and deadline/rebalance errors follow. You can:

1. Cap concurrency and in-flight database operations.
2. Use `pause()/resume()` on partition consumption via client APIs where appropriate.
3. Batch database writes with safe transaction boundaries.
4. Retry transient errors with exponential backoff and jitter.
5. Quarantine poison events before advancing commits.
6. Scale consumers within partition counts, compute resources, and downstream quotas.

### 13.5. Tier and capacity

Standard and Premium/Dedicated use different throughput and capacity models. When throttling appears, inspect Azure Monitor namespace metrics, tier, ingress/egress, partition/group counts, and quotas before simply raising client timeouts.

### 13.6. Changing partition count is an architectural change

Partition count impacts concurrency, key-based ordering, hotspots, and scaling. Not every tier allows changing partition count afterward. Where supported, test how key routing shifts and how business ordering is preserved during cutover.

## 14. Security and Production Configuration

### 14.1. Separate publishers, consumers, and administrators

| Principal | Permissions to grant | Should not have by default |
| --- | --- | --- |
| Producer | Azure Event Hubs Data Sender / SAS Send at right scope | Listen, Manage, Owner |
| Analytics consumer | Azure Event Hubs Data Receiver / SAS Listen | Send / Manage |
| CI/CD provisioning namespace/Event Hub | Appropriate Azure control-plane role | Unnecessary business data access |
| SRE / Monitoring | Read metrics/logs and incident diagnostics | Full SAS keys by default |
| Network administrator | Private Endpoint / firewall / DNS | Message payload access unless required |

### 14.2. Secrets, TLS, and networking

- Use Key Vault / secret injection; prefer identity-based auth where supported by your Kafka client/SDK.
- Never write `sasl.password`, JAAS configs, or tokens to logs or tickets.
- Enforce TLS encryption and certificate verification.
- Restrict public access or deploy private endpoints per threat model.
- Test private DNS resolution from AKS, VMs, and on-premises networks.
- Separate Dev/Staging/Prod namespaces for isolation.
- Key rotation plans must include rollback and reconnect testing.

### 14.3. Authorization is not partitioning

A record keyed `tenant-A` is not tenant-isolated authorization. A Kafka partition key only selects storage/ordering lanes—**it is not an access control list**. For multi-tenant privacy, isolate principals, namespaces/event hubs, RBAC, encryption, and producer validation; never rely on record keys to stop consumers from reading another tenant's data.

### 14.4. Do not treat Kafka client headers as trusted identity

Headers like `tenantId` or `eventType` can be populated arbitrarily by publishers. Consumers must validate contracts and verify origin at the broker/identity layer. Never let Internet clients supply arbitrary keys/headers and trust them for authorization or financial state changes.

## 15. Monitoring: Combining Azure Monitor with Kafka Client Metrics

### 15.1. A dashboard needs two perspectives

**Azure Event Hubs metrics** show whether the service is ingesting/serving and whether throttling or errors occur. **Kafka client metrics** show how each producer/consumer connects, sends, polls, commits, and where group lag stands.

| Layer | Key signals | Question |
| --- | --- | --- |
| Producer | Delivery success/error, retries, queue depth, latency | Did the broker acknowledge all events? |
| Network / TLS | Connection failures, reconnects, DNS/TLS errors | Are client connections stable? |
| Event Hubs namespace | Incoming/outgoing messages, requests, errors, throttling | Is tier/capacity sufficient? |
| Event Hub / partitions | Partition distribution, end offsets, event volume | Is any partition running hot? |
| Consumer group | Committed offsets, per-partition lag, rebalance count | Is the group keeping up with producers? |
| Consumer business logic | Processed/error counts, durable writes, retries/quarantine | Are events processed or merely polled? |
| Downstream | SQL/Cosmos DB latency, throttling, pool usage | Where is the bottleneck? |
| Cost | Tier/capacity, data movement, logging, retained data | Is spend within budget? |

Metric names and dimensions vary by tier and service mode. **Inspect live metric definitions before building dashboards** instead of copying charts blindly from another environment.

### 15.2. Azure CLI to inspect supported metrics

~~~bash
NS_ID=$(az eventhubs namespace show \
  --resource-group "$RG" \
  --name "$EHNS" \
  --query id \
  --output tsv)

# List currently available metric definitions.
az monitor metrics list-definitions \
  --resource "$NS_ID" \
  --output table

# Inspect namespace configuration without modifying resources.
az eventhubs namespace show \
  --resource-group "$RG" \
  --name "$EHNS" \
  --output json
~~~

These are **read-only** commands. When querying metrics, match exact names, granularities, units, and dimensions from the namespace output. Never cite namespace-wide incoming/outgoing totals as proof a consumer group finished processing.

### 15.3. Logging with correlation IDs

Example producer log:

~~~json
{
  "service": "orders-producer",
  "topic": "orders-events",
  "eventId": "evt-ORD-101-created",
  "orderId": "ORD-101",
  "result": "delivered",
  "partition": 2,
  "offset": 341
}
~~~

Example consumer log:

~~~json
{
  "service": "analytics-consumer",
  "groupId": "orders-analytics-lab",
  "eventId": "evt-ORD-101-created",
  "topic": "orders-events",
  "partition": 2,
  "offset": 341,
  "result": "processed-and-committed"
}
~~~

Use `eventId` to correlate business flows; use topic/partition/offset for technical debugging. Never log SAS connection strings, OAuth tokens, or sensitive payloads.

### 15.4. Tracing and processing duration

In a pipeline:

~~~text
HTTP request
  → producer (eventId=E1)
  → Event Hub orders-events
  → consumer group analytics
  → database write
~~~

To trace across async boundaries, propagate correlation/trace context in record headers or payloads using standards such as W3C Trace Context, and check whether your SDK propagates automatically or needs explicit instrumentation. Never assume a Kafka client stitches traces automatically with every Azure SDK.

### 15.5. Recommended alerts

- Rising delivery failures or producer retry rates.
- Rising namespace throttled requests or availability errors.
- Consumer group lag exceeding threshold for several minutes.
- Lag age approaching retention safety margins.
- Continuous rebalances, consumer heartbeat losses, or poll timeouts.
- A hot partition carrying heavy load while others sit nearly empty.
- Downstream DB throttling or rising consumer errors/quarantine counts.
- Zero incoming events despite rising business traffic.
- Cost or capacity utilization exceeding forecast.

Every alert needs an **owner, SLO, severity, and runbook**. Brief lag spikes during batch bursts can be acceptable if consumers recover well within retention.

## 16. Diagnostic Playbook When Kafka Clients Fail to Connect or Receive Data

### 16.1. Quick error reference

| Symptom | Suspected layer | First check |
| --- | --- | --- |
| DNS fails to resolve | DNS / public-private zone | Namespace FQDN, VNet DNS, forwarding |
| TCP 9093 timeout | Network / firewall / proxy | NSG, outbound rules, NAT, Public Network Access |
| TLS handshake failed | TLS / SNI / trust | FQDN, CA certs, clock skew, proxy interception |
| SASL authentication failed | Username / password | Literal `$ConnectionString`, secret/key rotation |
| Authorization error | SAS policy or Entra RBAC | Send vs. Listen, role scope, propagation |
| Unknown topic or partition | Event Hub name or resource | Verify Event Hub exists in exact namespace |
| Producer enqueues without delivery | Buffer / retry / network / ack | Delivery callbacks and `flush` result |
| Consumer runs with zero records | Offset / group / retention | Group ID, committed offset, `auto.offset.reset` |
| Consumer receives duplicates | Uncommitted offset, rebalance, crash | Manual commit and idempotency |
| Records out of order | Multiple partitions, differing keys, retries | Key selection, partition assignment |
| Consumer lag climbs | Downstream or capacity | SQL/API latency, partitions, throttling |
| Constant rebalances | Membership / heartbeat / poll | Poll processing time and group metrics |
| Kafka AdminClient topic creation fails | Kafka topic admin APIs unsupported | Provision Event Hub via Azure management plane |
| Kafka Streams stateful topology fails | Internal topics / compaction / transactions | Event Hubs feature compatibility |
| Event Hub has records yet Kafka group reads empty | Group offset, retention, or auth | Group ID, fresh test, client logs |
| Cost rises despite light tests | Tier / capacity or logging | Cost Management and lingering lab resources |

### 16.2. Step 1 — Confirm the target

Record **subscription/resource group, namespace, event hub name, tier, client library/version**, and UTC timestamp. Never paste connection strings into tickets.

~~~bash
az eventhubs namespace show \
  --resource-group "$RG" \
  --name "$EHNS" \
  --query "{name:name, sku:sku, status:status}" \
  --output json

az eventhubs eventhub show \
  --resource-group "$RG" \
  --namespace-name "$EHNS" \
  --name "$EVENTHUB" \
  --output json
~~~

If the Event Hub is missing, do not point `bootstrap.servers` to some random broker IP: provision the proper resource through governance first.

### 16.3. Step 2 — DNS, TCP, and TLS

~~~bash
nslookup ehns-kafka-unique-demo.servicebus.windows.net

nc -vz ehns-kafka-unique-demo.servicebus.windows.net 9093

openssl s_client \
  -connect ehns-kafka-unique-demo.servicebus.windows.net:9093 \
  -servername ehns-kafka-unique-demo.servicebus.windows.net \
  -brief
~~~

Move on to SASL and authorization only once TCP/TLS passes. When using a Private Endpoint, inspect the resolved DNS address and actual route rather than disabling TLS.

### 16.4. Step 3 — SASL and permissions

Verify safely:

- `security.protocol=SASL_SSL` and `sasl.mechanisms=PLAIN`.
- `sasl.username` is literally `$ConnectionString`.
- `sasl.password` is the complete namespace connection string.
- Policy/role grants the right Send/Listen rights for the workload.
- Connection string has not been rotated or revoked.
- For OAuth, token flow, refresh, and role assignment are configured properly.

**Never paste connection strings into terminal debug output when asking for help.** Verify secret existence, length, or metadata without exposing the secret value.

### 16.5. Step 4 — Producer delivery and Event Hub availability

If `produce()` throws no exception yet no data appears:

1. Did you call `poll()/flush()` to trigger callbacks?
2. Did the delivery callback report an error?
3. Is the Event Hub active?
4. Did the message exceed maximum size?
5. Is the namespace throttled on capacity?
6. Is an unsupported codec or API feature in use?

Never treat `produce()` returning normally as proof the backend persisted the record.

### 16.6. Step 5 — Consumer group and offsets

When consumer `poll()` returns nothing:

1. Verify you subscribed to the exact **Event Hub / topic name**.
2. Verify `group.id` matches the intended consumer group.
3. Inspect committed offsets and end offsets via client/framework tools if supported.
4. Check `auto.offset.reset` if the group has no committed offset yet.
5. Verify data is still within retention.
6. Inspect assignment/rebalance logs and partition/member counts.
7. Ensure another consumer in the same group is not already draining all records.

In the lab, **creating a fresh group and sending a new eventId** is a clean controlled test. Never reset production offsets just to probe.

### 16.7. Step 6 — Downstream and lag

If the consumer receives records yet commits slowly:

- Measure per-event processing duration and SQL/API latency.
- Check consumer CPU/RAM/GC and network sockets.
- Check for hot partitions and key distribution skew.
- Inspect rebalances and `max.poll.interval.ms` per client config.
- Throttle concurrency when downstream saturates.
- Use backpressure and bounded retries instead of endlessly adding replicas.

### 16.8. Step 7 — Verify recovery

After fixing:

- Producer callbacks confirm delivery.
- Event Hub metrics reflect incoming data at the expected timestamp.
- Consumer group receives new events, persists durable state, and commits.
- Event IDs match expectations with zero duplicate side effects.
- Consumer lag drops to healthy levels.
- Zero leaked connection strings or secrets.
- Costs, capacity, and alerts sit within normal thresholds.

## 17. Cost and Operational Responsibility

### 17.1. Cost components

| Component | Factors to size |
| --- | --- |
| Event Hubs namespace | Standard/Premium/Dedicated tier and capacity |
| Event Hubs traffic | Ingress/egress/requests per tier pricing |
| Retention | Storage window limits and policy charges |
| Event Hubs Capture | Writing streams to Blob/Data Lake when enabled |
| Client compute | AKS/VM/Container Apps/Functions running producers/consumers |
| Network | Egress, VNet, Private Endpoints, NAT per topology |
| Monitoring | Azure Monitor, Log Analytics ingestion and retention |
| Data processing | Spark, Stream Analytics, Fabric, databases, or storage |
| Security infrastructure | Key Vault, identity/networking services where billable |

**Never rely on a fixed USD/month figure** from study materials. Use the Pricing Calculator and Cost Management for your region, tier, and load-test profiles.

### 17.2. Scaling consumer groups increases egress

On a topic with 2 million records/day, if three consumer groups read all data, total consumption volume triples relative to one group. Adding groups buys **independent fan-out**, not free bandwidth or compute.

### 17.3. Cutting cost without breaking SLOs

- Keep records compact with necessary metadata only.
- Set retention to match replay and compliance needs rather than maxing it out.
- Use batching within acceptable latency budgets.
- Balance partition keys to prevent hot partitions.
- Size consumer concurrency to match downstream capacity.
- Avoid creating orphaned consumer groups without owners.
- Tune log sampling/retention reasonably while preserving incident signals.
- Shut down or clean up lab environments when authorized and verify residual spend.

## 18. Synthesis Practice: Producer, Consumer, and Replay

### 18.1. Scenario

A system emits events:

~~~text
Event Hubs namespace: ehns-kafka-unique-demo
Event Hub / Kafka topic: orders-events
Partitions: 4

Consumer groups:
  orders-analytics-lab
  orders-fraud-lab
~~~

Goals:

- Producer sends 6 events keyed by `orderId`.
- Analytics group consumes and commits after processing.
- Fraud group uses a different group to read independently.
- Topic, partition, and offset appear in logs.
- Practice safe replay using a fresh lab group within retention.

### 18.2. Verification Checklist

| Step | Action | Expected result |
| --- | --- | --- |
| 1 | Verify namespace tier and Event Hub exist | Appropriate Standard/Premium/Dedicated tier, exact `orders-events` |
| 2 | Test TCP/TLS 9093 | DNS/TCP/TLS succeed, valid certificate |
| 3 | Grant least-privilege SAS or Entra permissions | Producer Send, consumer Listen |
| 4 | Inject secrets via secure environment | Zero hardcoded/logged connection strings |
| 5 | Run `producer.py` | 6 successful delivery callbacks |
| 6 | Run `consumer.py` with fresh group | Receives retained events |
| 7 | Inspect key/topic/partition/offset | Useful metadata for tracing |
| 8 | Re-run consumer with the same group | Does not re-read already committed records |
| 9 | Replay with a new lab group | Re-reads retained records |
| 10 | Kill consumer between processing and commit | Redelivers record without duplicate side effects |
| 11 | Monitor lag and capacity | Healthy lag and zero throttling |
| 12 | Clean up approved lab resources | Production namespaces and consumer groups untouched |

### 18.3. Exercise A — Consumers and partitions

An Event Hub has 4 partitions. The Analytics group runs 6 consumer processes.

**Question:** can all 6 consumers concurrently process 6 different partitions?

**Answer:** No—at most four partitions exist to assign in parallel within the group. Excess members sit idle depending on assignment. If bottlenecked on a hot partition, adding consumers does not solve the root cause.

### 18.4. Exercise B — Choosing a partition key

You need to preserve order for `OrderCreated → OrderPaid → OrderShipped` on each order.

**Question:** should you key by `region` or `orderId`?

**Answer:** `orderId` is usually better because it keeps records for one order in one partition (given stable partitioner/partitions) and distributes far more evenly than `region`. You must still manage publisher concurrency/retries and business schemas.

### 18.5. Exercise C — Auto-commit and logical data loss

A consumer enables auto-commit. Offsets auto-commit before the database write completes, then the process crashes.

**Question:** what can happen?

**Answer:** On restart, the consumer resumes from the committed offset and skips the record that never updated the database. Use manual commits after durable processing paired with idempotency.

### 18.6. Exercise D — Crash between database write and commit

A worker commits to the DB successfully and then crashes before committing the offset.

**Question:** can the event be received again? Should it send a second email?

**Answer:** Yes, it can be redelivered; no, it must not trigger a second side effect after already being handled. Use a stable `eventId`, unique constraints, outbox/deduplication, or equivalent idempotent mechanics.

### 18.7. Exercise E — Earliest does not replay

The Analytics group already committed up to the latest offset. You change `auto.offset.reset=earliest`, restart, and still see no older events.

**Question:** why?

**Answer:** because the group already has valid committed offsets. `earliest` does not force a rewind. Use a new group or a controlled reset, and ensure data remains within retention.

### 18.8. Exercise F — Private Endpoint

Namespace DNS resolves to a private IP, yet the Kafka client times out on port 9093.

**Answer:** check VNet routing, NSGs/UDRs, firewalls, VPN/ExpressRoute, NAT/proxies, and TCP 9093. Never swap bootstrap to a private IP and disable certificate validation.

### 18.9. Exercise G — Kafka Streams and internal topics

A Kafka Streams topology requires creating internal changelog topics and log compaction, which the Event Hubs Kafka endpoint does not satisfy as assumed.

**Answer:** evaluate feature compatibility and either choose another Kafka platform or adapt the architecture/state store; do not misdiagnose this as a SASL password error.

### 18.10. Exercise H — Estimating raw throughput

A producer sends 5,000 events/second at 4 KiB each.

\[
5{,}000\times4/1024=19.53\text{ MiB/s}
\]

**Answer:** raw payload rate is roughly 19.53 MiB/s, before overhead, compression, multiple consumer groups, and peaks. Use this as sizing input, **not as an official bill or quota**.

## 19. Safe Lab Cleanup

### 19.1. Inventory before deleting

~~~bash
az resource list \
  --resource-group "$RG" \
  --output table
~~~

Never delete `RG` if it holds shared resources. A consumer group or namespace may serve dependent applications invisible from your immediate task.

### 19.2. Delete only if the resource group is strictly lab-only

~~~bash
# DESTRUCTIVE ACTION: run only with approval after verifying the RG contains only lab resources.
az group delete --name "$RG" --yes
~~~

This lesson **does not require executing this command**. If sharing a namespace, delete only named lab entities after checking active consumers and retention. Retain telemetry and lesson notes per organizational security policy.

### 19.3. Post-cleanup checks

- No stray lab namespaces or compute remain running.
- Zero secrets or connection strings in Git, logs, or tickets.
- Lab role assignments reviewed and cleaned up.
- Dashboards/alerts no longer point to deleted resources.
- Cost Management confirms no unexpected lab spend continues.

## 20. Self-Check Questions

**Question 1.** What Event Hubs entity maps to a Kafka topic?

**Answer:** An Event Hub (entity) pre-created inside an Event Hubs namespace.

**Question 2.** What does the Kafka bootstrap endpoint look like?

**Answer:** The namespace FQDN, typically `<namespace>.servicebus.windows.net:9093`, using TLS and a supported SASL mechanism.

**Question 3.** With SASL/PLAIN, what username is typically used?

**Answer:** The literal `$ConnectionString`; the password is an appropriate Event Hubs connection string.

**Question 4.** Can you auto-create Event Hubs via Kafka AdminClient `createTopics` like on a Kafka broker?

**Answer:** Do not assume so. Provision Event Hubs via the Azure management plane / IaC.

**Question 5.** What does it mean when producer `produce()` returns before a delivery callback fires?

**Answer:** The record may still sit in a local buffer; check callbacks/`flush` and errors to confirm broker acceptance.

**Question 6.** Does committing a Kafka offset delete the event?

**Answer:** No. Offsets only track read progress; records remain per Event Hub retention.

**Question 7.** Do two consumers in the same group both read every partition independently from the beginning?

**Answer:** No. They split partitions between them. To read independently, use separate groups with separate offsets.

**Question 8.** Does `auto.offset.reset=earliest` rewind a group that already has valid committed offsets?

**Answer:** No.

**Question 9.** Why is an idempotent consumer still required even with manual commits?

**Answer:** A crash can happen after a durable write and before committing the offset, causing the event to be re-read.

**Question 10.** At what scope is ordering guaranteed in Event Hubs Kafka?

**Answer:** Within a single partition by offset; there is no global ordering across partitions.

**Question 11.** Can the Event Hubs Kafka endpoint serve as a Kafka compacted changelog keeping the latest record per key?

**Answer:** Not by default; check feature compatibility and design a dedicated state store when needed.

**Question 12.** TCP 9093 passes yet SASL auth fails—what should you check?

**Answer:** Check username, full connection string, policy/role scope, and secret rotation; never disable TLS.

**Question 13.** Why does adding consumer replicas not always fix high lag?

**Answer:** Causes can include hot partitions, too few partitions, DB throttling, networking, or Event Hubs capacity limits.

**Question 14.** Once old records pass retention, can a new group replay them?

**Answer:** No. You need a separate historical store such as Data Lake / Capture if configured beforehand.

**Question 15.** Does Event Hubs' Kafka endpoint support every Kafka Streams / Connect feature?

**Answer:** Not by default. Test API support, internal topics, compaction, transactions, and your exact framework/version.

## Key Takeaways

- **Azure Event Hubs Kafka endpoint** lets Kafka-compatible producers/consumers use a managed Azure streaming service—**not a full-control Kafka broker cluster**.
- **Kafka topics map to Event Hubs**; bootstrap FQDN runs on **port 9093** with **SASL_SSL**, while topics, partitions, and retention are managed through Azure.
- Producers need **delivery callbacks/acks**, and consumers need **durable processing before committing offsets** plus **idempotency** against redelivery.
- **Partition keys** shape distribution and ordering; order exists only per partition, never globally across partitions.
- **Consumer group offsets** are independent per group; `auto.offset.reset=earliest` does not rewind a group with existing committed offsets.
- **Retention is finite** and **Kafka API compatibility has boundaries**. Never assume Kafka log compaction, full broker admin APIs, or exactly-once transactions work out of the box.
- Combine **Azure Monitor + Kafka client metrics + business logs** to monitor ingestion, lag, throttling, errors, and cost.
- Secure **SAS credentials / OAuth tokens, TLS, RBAC, Private Endpoints / DNS**, and test both failure and replay paths before production.
