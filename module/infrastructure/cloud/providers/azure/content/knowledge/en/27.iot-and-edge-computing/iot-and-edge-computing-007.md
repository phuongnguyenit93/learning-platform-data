# Azure Digital Twins and Modeling the Physical Environment

A campus has three buildings, each with multiple floors, meeting rooms, air conditioners, temperature sensors, and power meters. IoT data changes continuously: room 101's temperature rises from 25°C to 29°C, an HVAC unit raises an alert, or a room transitions from vacant to occupied. If you only store millions of sensor messages, the system knows **measured values** yet struggles to answer **physical context** questions: which room is this sensor monitoring, which floor is that room on, which air conditioner serves that zone, and are adjacent rooms affected?

**Azure Digital Twins (ADT)** helps build a **graph representing the physical environment** using digital twins, models, and relationships. This graph links sensor data to locations, equipment, and spatial structure to support monitoring, analytics, automation, or simulation at the application layer.

```text
PHYSICAL ENVIRONMENT                 DIGITAL MODEL ON AZURE

Building A                           Twin bldg-a
   |                                      |
   +-- Room 101                          +-- contains --> Twin room-101
   |     |                                                   |
   |     +-- Temperature sensor                              +-- monitoredBy --> sensor-temp-01
   |     +-- Air conditioner                                 +-- servedBy ----> hvac-01
   |
   +-- Room 102                          +-- contains --> Twin room-102

IoT telemetry (29°C) --> IoT Hub / event processing --> update room-101 property
                                                    --> state analytics application
```

The digital model **does not appear automatically when you plug in a sensor**. You must define object types using **Digital Twins Definition Language (DTDL)**, create twin instances, add relationship edges, and build pipelines syncing state from data sources. ADT does not by default replace **Azure IoT Hub**, time-series databases, or BIM/GIS/CAD software.

This lesson belongs to the **IoT and Edge Computing** chapter in the `CLOUD_PROVIDERS_AZURE` module. The module introduces the Microsoft Azure ecosystem from subscriptions, resource groups, and Microsoft Entra ID through virtual networks, compute, storage, data, deployment, monitoring, security, and cost management. From that perspective, this lesson focuses on **modeling the physical environment** and connecting ADT with IoT Hub, Functions, Event Grid, Event Hubs, historical data, control systems, and safe operational requirements.

> Examples use **DTDL v2** and Azure Digital Twins data-plane SDK/REST syntax for illustration. Features, limits, API versions, history integrations, quotas, regions, SKUs, and pricing may change. Before operating in Production, check product docs and actual instance capabilities. Never control critical physical equipment solely because of a twin property or an AI query recommending an action; every control command requires an independent protection layer.

## 1. Learning Objectives

After this lesson, you can:

1. Distinguish **physical asset, digital twin, model, relationship, component, property, and telemetry**.
2. Explain Azure Digital Twins as a **semantic graph of the physical environment**, not merely a sensor data table.
3. Author DTDL v2 models for Building, Room, and Sensor with IDs, properties, telemetry, and relationships.
4. Distinguish **model schema** from **twin instance** and state updated over time.
5. Design identities, names, and versions for models/twins/relationships across a campus or factory.
6. Create and query twins/relationships via the SDK in an authorized environment.
7. Design the flow **IoT device → IoT Hub → Functions/worker → ADT**, integrating Event Grid/Event Hubs and historical storage.
8. Explain why **telemetry events do not automatically become twin properties** and why ADT is not a default time-series database.
9. Write graph queries to find related rooms and equipment.
10. Distinguish **topology state, latest known state, history, and desired control state**.
11. Apply Microsoft Entra ID/managed identities, Azure RBAC/data-plane roles, and private networking where supported.
12. Handle **stale data, late/out-of-order events, idempotency, concurrency, drift, and schema evolution**.
13. Configure observability, location data security, cost monitoring, and incident procedures.
14. Design a mini-lab modeling a building and verifying the graph.

## 2. What Is a Digital Twin and What Is It Not?

A **digital twin** is a digital representation of a real-world object, process, or environment linked with data and relationships to support understanding state, analysis, or decision-making. What a digital twin system can do depends on update freshness and business integration.

For example, a real-world meeting room has:

- Room name, usage type, area.
- The floor and building containing it.
- Temperature, humidity, and CO₂ sensors.
- Air conditioning unit supplying airflow.
- Current temperature, estimated occupancy.
- History of threshold breaches.
- Alerting/maintenance dispatch rules.

In ADT, you can represent that room as a **twin** with properties and edges linking to other twins.

**Do not confuse:**

| Concept | Represents | Does Not Provide by Default |
|---|---|---|
| **Azure Digital Twins** | Models, twins, graph relationships, state, and contextual queries. | Device connectivity protocols, long-term telemetry storage, full physics simulators. |
| **Azure IoT Hub** | Device connectivity, identity, and message exchange per IoT Hub capabilities. | A graph of buildings/rooms/business relationships. |
| **Azure IoT Edge / edge compute** | Collection/pre-processing at the device site, handling intermittent networks. | Automatic model graph syncing with ADT. |
| **Azure Data Explorer/Analytics** | Large-scale event/time-series data and historical analytics. | Twin/relationship modeling and topology semantics like ADT. |
| **BIM/GIS/CAD** | Architectural design/geometry/mapping models. | A live operational twin graph without integration. |
| **CMDB/ERP/Asset register** | Authoritative asset management, ownership, maintenance records. | Real-time sensor telemetry by default. |

**ADT is one piece of the solution**, not a replacement for all systems above.

## 3. Why Use a Graph Instead of a Device Table?

A telemetry table:

```text
deviceId          timestamp             temperature
sensor-temp-01    2026-11-20T09:00Z      25.1
sensor-temp-01    2026-11-20T09:01Z      28.5
sensor-temp-02    2026-11-20T09:01Z      23.4
```

does not answer by itself:

- Which room is `sensor-temp-01` in?
- Does that room share an HVAC unit with other rooms?
- Which machines belong to Building A?
- Which capacity/controller affects a hot zone?
- Which tenant or department owns that room?

A **graph** adds context:

```text
[bldg-a] --contains--> [floor-01] --contains--> [room-101]
                                                  |
                                                  +--monitoredBy--> [sensor-temp-01]
                                                  |
                                                  +--servedBy----> [hvac-01]
                                                  |
                                                  +--adjacentTo--> [room-102]
```

Now the application can **query relationships** to find assets connected to a threshold breach, pull historical data from the analytics store, and decide whether to raise an alert.

## 4. Core Concepts of Azure Digital Twins

| Component | Meaning | Example |
|---|---|---|
| **ADT instance** | Azure resource holding models, twins, and the graph. | `adt-campus-lab` |
| **Model / Interface** | Data type and structure defined in DTDL. | `dtmi:example:Room;1` |
| **Twin instance** | Entity instance created from a model. | `room-101` |
| **Twin ID** | Instance ID inside the graph. | `room-101`, not the model ID. |
| **Property** | State/attribute persisted on a twin per schema. | `temperature=28.5` |
| **Telemetry** | Declaration of measurement data/event type; processed via APIs/integrations. | `temperatureReading` |
| **Relationship** | Directed edge from source twin to target twin. | `bldg-a --contains--> room-101` |
| **Relationship property** | Metadata on an edge when declared in the model. | `installedAt`, `priority` |
| **Component** | Structured sub-part inside a single model/twin. | `thermostat` inside an HVAC unit. |
| **DTDL** | JSON-LD language describing models, properties, and relationships. | Room Interface version 1. |
| **Event route** | Routes events emitted by ADT to configured endpoints. | Event Grid/Event Hubs/Service Bus per support. |
| **Data history pipeline** | Integration pushing changes/events to historical storage/analytics. | Azure Data Explorer via supported config. |

**Twin ID**, **model ID**, and **device ID** do not have to be identical values. A physical sensor authenticated in IoT Hub can correspond to a Sensor twin via a trusted mapping table.

## 5. Distinguishing Models and Twin Instances

The `Room` model describes **a class of rooms**:

```text
Room model:
  name: string
  temperature: double
  occupancy: integer
  relationship monitoredBy -> Sensor
```

**Twin instances** materialize the model:

```text
room-101:
  name = "Room 101"
  temperature = 28.5
  occupancy = 7

room-102:
  name = "Room 102"
  temperature = 24.0
  occupancy = 0
```

This resembles **classes** and **objects** in object-oriented programming, except DTDL should not be treated as an executable programming language. Models primarily describe schema/semantics, while services and apps execute updates, queries, and event handling.

### Choosing Model Versions

The string:

```text
dtmi:example:Room;1
```

is a **Digital Twin Model Identifier (DTMI)** at version 1. When incompatible structural changes occur, the standard practice is publishing a new model ID/version, such as `dtmi:example:Room;2`, and planning migrations for twins and data pipelines.

**Never rename a model on paper and assume existing twins follow the new schema.** In ADT, uploaded models have governance/immutability rules; versioning and controlled migrations are required.

## 6. Digital Twins Definition Language (DTDL)

**DTDL** is the language for defining models, typically represented in JSON-LD. An Interface model has key fields:

- `@id`: globally unique, versioned DTMI.
- `@type`: DTDL entity type, e.g., `Interface`.
- `@context`: grammar/context, e.g., `dtmi:dtdl:context;2` for DTDL v2.
- `displayName` / `description`: human-readable metadata.
- `contents`: Properties, Telemetries, Relationships, Components, and supported elements.

Skeleton example:

```json
{
  "@id": "dtmi:example:SimpleRoom;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": "Simple Room",
  "contents": [
    {
      "@type": "Property",
      "name": "temperature",
      "schema": "double"
    }
  ]
}
```

**This model creates zero rooms.** It merely lets the service and applications understand the structure matching instances must follow.

### DTDL v2 and Other Versions

Azure Digital Twins supports specific model languages/versions over time. This lesson uses **DTDL v2** for consistency across snippets. Before uploading DTDL v3 or extensions, verify ADT instance/API/SDK support and avoid mixing syntax across versions.

## 7. DTDL Sample: Building

Let's define a Building model with a name and a `contains` relationship to a room.

```json
{
  "@id": "dtmi:example:campus:Building;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": {
    "en": "Building",
    "vi": "Tòa nhà"
  },
  "contents": [
    {
      "@type": "Property",
      "name": "name",
      "schema": "string",
      "writable": true
    },
    {
      "@type": "Relationship",
      "name": "contains",
      "target": "dtmi:example:campus:Room;1"
    }
  ]
}
```

Key points:

1. `@id` is the **model** ID, distinct from twin ID `bldg-a`.
2. `contains` is a **directed** relationship from Building to Room.
3. `target` specifies the expected target model.
4. `name` is a string property on Building.
5. `writable` describes a schema characteristic, **not user RBAC permissions**.
6. DTDL does not automatically generate room lists or pull names from a building management system.

### Diagram

```text
Model: Building;1
    ├── name: string
    └── contains ──> Model: Room;1
```

A building containing multiple rooms is modeled using **multiple relationship instances** sharing the relationship name `contains` yet carrying distinct relationship IDs.

## 8. DTDL Sample: Room

Room has properties representing latest state plus relationships to Sensor/HVAC.

```json
{
  "@id": "dtmi:example:campus:Room;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": "Room",
  "contents": [
    {
      "@type": "Property",
      "name": "name",
      "schema": "string",
      "writable": true
    },
    {
      "@type": "Property",
      "name": "temperature",
      "schema": "double",
      "writable": true
    },
    {
      "@type": "Property",
      "name": "occupancy",
      "schema": "integer",
      "writable": true
    },
    {
      "@type": "Telemetry",
      "name": "temperatureReading",
      "schema": "double"
    },
    {
      "@type": "Relationship",
      "name": "monitoredBy",
      "target": "dtmi:example:campus:Sensor;1"
    },
    {
      "@type": "Relationship",
      "name": "servedBy",
      "target": "dtmi:example:campus:HVAC;1"
    }
  ]
}
```

Notes:

- `temperature` as a **Property** stores persisted queryable state.
- `temperatureReading` as **Telemetry** declares measurement events; **emitting it does not automatically save every reading into the `temperature` property**.
- `monitoredBy` and `servedBy` express physical/infrastructure links.
- If Sensor/HVAC models matching those target IDs aren't loaded yet, upload dependent models properly and pass validation before constructing the graph.

### Room Temperature Is Not Always Equal to the Last Sensor Reading

An application might average multiple sensors, filter outliers, or check sensor health before updating room state. Therefore, **property calculation rules** belong in the business processing layer, never inferred automatically from a telemetry name.

## 9. DTDL Samples: Sensor and HVAC

Two simple models:

**Sensor:**

```json
{
  "@id": "dtmi:example:campus:Sensor;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": "Temperature Sensor",
  "contents": [
    {
      "@type": "Property",
      "name": "deviceId",
      "schema": "string"
    },
    {
      "@type": "Property",
      "name": "health",
      "schema": "string",
      "writable": true
    },
    {
      "@type": "Telemetry",
      "name": "temperatureReading",
      "schema": "double"
    }
  ]
}
```

**HVAC:**

```json
{
  "@id": "dtmi:example:campus:HVAC;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "displayName": "HVAC Unit",
  "contents": [
    {
      "@type": "Property",
      "name": "name",
      "schema": "string"
    },
    {
      "@type": "Property",
      "name": "operationalState",
      "schema": "string",
      "writable": true
    },
    {
      "@type": "Property",
      "name": "powerKw",
      "schema": "double",
      "writable": true
    }
  ]
}
```

These models are **learning schemas**—they carry no automatic rule like "if `health=Failed`, shut off HVAC." Executing actions requires processors, rules, and dedicated safety control systems.

### Versioned Model IDs

Namespace IDs by organization:

```text
dtmi:example:campus:Room;1
dtmi:example:campus:Sensor;1
dtmi:example:campus:HVAC;1
```

Keep IDs/versions consistent so code and deployment scripts reference them reliably. Never assign a new model ID merely because a display name changed.

## 10. Property, Telemetry, Component, and Relationship

| Kind | Nature | Example | When to Choose |
|---|---|---|---|
| **Property** | Persisted state/value on a twin per schema. | `temperature`, `health`, `name`. | Querying an object's latest known state. |
| **Telemetry** | Stream of measurements/events over time. | `temperatureReading`. | Event processing, streaming, or history pipelines. |
| **Component** | Structured sub-element **inside the same twin/model**. | `thermostat` unit with its properties. | Tightly bound sub-part needing no independent graph identity/edges. |
| **Relationship** | Directed edge between **two independent twins**. | `room-101 --monitoredBy--> sensor-01`. | Graph traversal queries, asset reuse, independent lifecycles. |

### Practical Rule: Component or Separate Twin?

A small controller exposing only HVAC parameters can be a **Component**. A physical sensor with a serial number, warranty, and room-to-room relocations needing multi-party links usually fits better as an **independent Sensor twin**.

No single modeling style fits every organization. Decide based on **lifecycle, identity, query patterns, and asset independence**.

## 11. DTDL Component: Representing Internal Parts

Suppose we have a Thermostat model:

```json
{
  "@id": "dtmi:example:campus:Thermostat;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "contents": [
    {
      "@type": "Property",
      "name": "setpoint",
      "schema": "double",
      "writable": true
    },
    {
      "@type": "Property",
      "name": "mode",
      "schema": "string",
      "writable": true
    }
  ]
}
```

Another model can embed it as a component:

```json
{
  "@id": "dtmi:example:campus:HVACWithThermostat;1",
  "@type": "Interface",
  "@context": "dtmi:dtdl:context;2",
  "contents": [
    {
      "@type": "Property",
      "name": "name",
      "schema": "string"
    },
    {
      "@type": "Component",
      "name": "thermostat",
      "schema": "dtmi:example:campus:Thermostat;1"
    }
  ]
}
```

A component is declared **inside the containing twin's model**. It does not create a relationship between two separate twin IDs.

### Notes

- With DTDL components, instance JSON and patch paths follow specific API structures; use SDK/model-aware helpers and check examples for your version.
- Component schemas must be uploaded/resolved properly.
- Do not treat components as substitutes for full assets carrying their own asset IDs.
- Never stuff thousands of historical readings into component fields.

## 12. DTDL Relationship: Directed Edges and Meaning

The Building model declares `contains` pointing Building → Room, so an instance:

```text
bldg-a --contains--> room-101
```

does not automatically create a reverse edge `room-101 --inside--> bldg-a`. If the application needs reverse traversal, write the corresponding graph query or explicitly model the inverse relationship.

A relationship has its **own ID**, type name, and two endpoints:

```json
{
  "$relationshipId": "bldg-a-contains-room-101",
  "$sourceId": "bldg-a",
  "$relationshipName": "contains",
  "$targetId": "room-101"
}
```

**Values:**

- `$sourceId`: source twin ID.
- `$targetId`: target twin ID.
- `$relationshipName`: relationship name declared on the source model.
- `$relationshipId`: unique ID for the outgoing relationship from the source twin per API contract.

If edge metadata such as `installedAt` is needed, declare relationship properties in DTDL and validate inputs. Do not attach undeclared properties expecting the schema to accept them.

## 13. Creating Twin Instances from Models

Once `dtmi:example:campus:Room;1` is uploaded, create instance `room-101`:

```json
{
  "$dtId": "room-101",
  "$metadata": {
    "$model": "dtmi:example:campus:Room;1"
  },
  "name": "Room 101",
  "temperature": 25.1,
  "occupancy": 0
}
```

A Building instance:

```json
{
  "$dtId": "bldg-a",
  "$metadata": {
    "$model": "dtmi:example:campus:Building;1"
  },
  "name": "Building A"
}
```

A Sensor instance:

```json
{
  "$dtId": "sensor-temp-01",
  "$metadata": {
    "$model": "dtmi:example:campus:Sensor;1"
  },
  "deviceId": "iot-sensor-01",
  "health": "Healthy"
}
```

These objects are **digital twin payloads**, not DTDL models. Never mix up a model's `@id` with an instance's `$dtId`.

### Not Every Twin Needs a Dedicated Sensor

A room or production line can have a twin even without a direct sensor. Twin values can originate from ERP, BMS, operator inputs, analytics, or computed models. Links to the physical world must still be **verified and attributed**.

## 14. Building a Graph from Twin Instances

Given objects:

```text
bldg-a
room-101
room-102
sensor-temp-01
hvac-01
```

Create relationships:

```text
bldg-a --contains--> room-101
bldg-a --contains--> room-102
room-101 --monitoredBy--> sensor-temp-01
room-101 --servedBy--> hvac-01
```

The graph answers:

- Which rooms are inside Building A?
- Which sensors monitor Room 101?
- Which rooms are served by the same HVAC?
- When an HVAC unit faults, which rooms might be affected?

**A relationship does not prove physical effect.** A room marked `servedBy` does not prove the HVAC is actually delivering airflow. Invariants like "each room has at most one primary HVAC" must be enforced by applications and source data unless explicitly supported.

## 15. How Does Real-Time Data Enter the Graph?

ADT does not open MQTT connections to IoT devices directly to read temperature. A common pipeline is:

```text
Real-world sensor
      |
      | MQTT/AMQP/HTTPS (per IoT Hub device protocols)
      v
Azure IoT Hub
      |
      | Route telemetry/events
      v
Azure Functions / event-processing worker
      |
      +-- validate deviceId and message schema
      +-- map deviceId → twinId
      +-- check timestamp/sequence/idempotency
      +-- convert units °F → °C if needed
      |
      v
Azure Digital Twins data-plane API
      |
      +-- Update property temperature
      +-- (optional) Publish telemetry event
      |
      v
ADT event routes → Event Grid / Event Hubs / Service Bus
                       |
                       v
              Azure Data Explorer / analytics / alerting
```

Key takeaways:

1. Devices usually send data to **IoT Hub**, not directly into ADT.
2. Functions/workers act as **adapters** bridging device IDs, schemas, and twin IDs.
3. Updating a property is an explicit **write operation** to ADT.
4. Emitting events downstream requires configuring **event routes/endpoints**.
5. Store long-term history in the appropriate **analytics service**.
6. Retries, duplicates, and out-of-order events must be handled at ingestion.

## 16. Designing the Message Contract Between Device and Worker

A simulated IoT message:

```json
{
  "deviceId": "iot-sensor-01",
  "eventId": "evt-sensor-01-20261120-0901",
  "sequence": 12804,
  "observedAtUtc": "2026-11-20T09:01:00Z",
  "temperatureC": 28.5,
  "quality": "ok"
}
```

The adapter application should:

- **Authenticate origin** via the IoT Hub identity/messaging boundary; never trust the body's `deviceId` field alone.
- Validate schema, units, ranges, and timestamps.
- Use a backend-managed mapping: `iot-sensor-01 → sensor-temp-01 → room-101`.
- Prevent a Tenant A sensor from writing to a Tenant B twin.
- Deduplicate by `eventId` or sequence within a suitable window.
- Compare `observedAtUtc` against stored timestamps to prevent out-of-order overwrites.
- Save source events in an analytics/event store when auditing is needed.
- Log errors and quarantine malformed messages.
- Retry with backoff on ADT 429/5xx responses.
- Never unconditionally overwrite `temperature=28.5` when `sensor.health=Failed`.

### Two Timestamps

- **Event/observation time:** when the sensor actually measured the value.
- **Processing/update time:** when the worker received, computed, and updated the twin.

Storing only processing time misrepresents late events. Where business logic cares, track both and compute source lag.

## 17. Properties Are State; Telemetry Is Events

A sound architecture separates:

```text
Sensor sends at 09:00: 24.0°C
Sensor sends at 09:01: 24.5°C
Sensor sends at 09:02: 29.0°C

Azure Digital Twins:
  room-101.temperature = 29.0 (latest accepted state)

Time-series store:
  (09:00, 24.0)
  (09:01, 24.5)
  (09:02, 29.0)
```

If you only update properties:

- You can query the **current/latest accepted temperature**.
- You do **not automatically retain minute-by-minute history** just because the property changed.
- To chart weeks/months, build a pipeline persisting historical events in an appropriate store.
- Track **freshness/last observation time** explicitly so stale values aren't shown as live.

If you only publish telemetry:

- Properties do not update automatically.
- Querying `room.temperature` may return stale values.
- A processor must update state explicitly if needed.

**Never use ADT as a store for billions of measurements** without designing history, scale, and cost properly.

## 18. Data History and Time-Series Analytics

A campus system must answer:

- What was Room 101's average temperature over the past 7 days?
- Which HVAC used the most power this month?
- Did the sensor fault occur before or after occupancy rose?
- Which rooms stayed hotter than 28°C for over 15 minutes?

These are historical/aggregation queries fitting time-series analytics services like **Azure Data Explorer** and related streaming pipelines, per supported features.

```text
Azure Digital Twins
    |
    | Digital Twin updates / telemetry events / routes
    v
Event Hubs / supported history integration
    |
    v
Azure Data Explorer
    |
    +-- time-window aggregation
    +-- anomaly detection
    +-- historical visualization
    |
    v
Grafana / dashboards / analytical services
```

ADT provides **data history** integrations with Azure Data Explorer within supported scopes, yet **creating an ADT instance does not turn history on automatically**. You must configure event routes/integrations, event schemas, authorization, retention, and budgets per component.

### Distinguishing Three Data Categories

| Data | Where Should It Live? |
|---|---|
| **Topology:** Building contains Room, which HVAC serves which Room. | ADT graph/relationships. |
| **Latest known operational state:** room temperature, HVAC health. | ADT twin properties or state store per design. |
| **Historical measurements:** one million readings over 12 months. | Azure Data Explorer/ADLS/analytics storage. |

## 19. Querying the Graph with Azure Digital Twins Query Language

ADT has its own graph query language. It is **not full-featured SQL Database/T-SQL**, even though some syntax resembles SQL.

### Find All Twins by Model

```sql
SELECT *
FROM DIGITALTWINS T
WHERE IS_OF_MODEL(T, 'dtmi:example:campus:Room;1')
```

### Find Rooms Hotter Than 27°C

```sql
SELECT room
FROM DIGITALTWINS room
WHERE IS_OF_MODEL(room, 'dtmi:example:campus:Room;1')
  AND room.temperature > 27
```

### Traverse Building → Room Relationship

```sql
SELECT room
FROM DIGITALTWINS building
JOIN room RELATED building.contains
WHERE building.$dtId = 'bldg-a'
```

These queries illustrate **ADT graph queries**, not queries to run verbatim in Azure SQL Database. When implementing, verify exact syntax/aliases supported by your query engine version.

### Limitations to Keep in Mind

- Do not treat ADT queries like a data warehouse with arbitrary JOIN/GROUP BY/ORDER BY/aggregations.
- Queries need careful graph traversal planning and selective filters.
- Never concatenate unvalidated/unescaped user input directly into query strings.
- Enforce backend and result-level authorization if multiple tenants share a graph.
- Handle paging/continuation tokens for large result sets.
- For multi-month time-series analytics, query the history/analytics store.

## 20. From Query to Operational Answer

**Question:** "Are any rooms in Building A overheating?"

Instead of scanning every raw reading and guessing locations, the app:

1. Queries Building twin `bldg-a`.
2. Traverses `contains` to rooms.
3. Filters `temperature > 27` on latest known state.
4. Checks `lastObservedAtUtc`/freshness (if modeled).
5. Checks `sensor.health` on linked sensors.
6. Pulls historical temperature curves from Azure Data Explorer.
7. Evaluates whether data is fresh and trustworthy enough to alert.
8. Returns room, threshold, sensor, and timestamp.
9. If HVAC adjustment is needed, routes through an **approved** workflow.

**A room showing 30°C with a timestamp from two days ago** must not be treated as "currently hot" with the same confidence as a fresh reading.

## 21. Azure Digital Twins SDK: Connecting Securely with Identity

Python example for a lab environment with an ADT instance provisioned and data-plane permissions assigned.

Install packages in a dedicated lab project:

```bash
python -m pip install azure-digitaltwins-core azure-identity
```

Configure the endpoint via environment variable:

```text
ADT_ENDPOINT=https://<your-instance-hostname>
```

**Do not guess hostnames from resource names** without checking the actual `hostName` in the Azure Portal. Authenticate using Microsoft Entra credentials/managed identity:

```python
import os
from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient

endpoint = os.environ["ADT_ENDPOINT"]
client = DigitalTwinsClient(
    endpoint,
    DefaultAzureCredential(),
)

# Read-only graph query in this permission-check example.
for twin in client.query_twins(
    "SELECT * FROM DIGITALTWINS T "
    "WHERE IS_OF_MODEL(T, 'dtmi:example:campus:Room;1')"
):
    print(twin.get("$dtId"))
```

Prerequisites:

- Valid instance host reachable over configured networking.
- Principal holds **Azure Digital Twins Data Reader** or role matching the operation.
- Network/TLS/DNS work from the actual runtime.
- Model IDs match the instance.
- Query results are filtered by **business authorization** before returning to end users.

**Azure subscription Contributor does not automatically grant ADT data-plane graph permissions.**

## 22. SDK: Creating Models, Twins, and Relationships in Lab

The snippets below illustrate operational order in a **dedicated sandbox environment**, never run against Production.

### Step 1 — Upload Models in Dependency Order

Example DTDL JSON payloads should come from the models in Sections 7–9.

```python
from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient

endpoint = "https://<your-instance-hostname>"
client = DigitalTwinsClient(endpoint, DefaultAzureCredential())

# Replace with the DTDL interfaces validated in this lesson:
sensor_model = {
    "@id": "dtmi:example:campus:Sensor;1",
    "@type": "Interface",
    "@context": "dtmi:dtdl:context;2",
    "contents": [
        {"@type": "Property", "name": "deviceId", "schema": "string"}
    ]
}
building_model = {
    "@id": "dtmi:example:campus:Building;1",
    "@type": "Interface",
    "@context": "dtmi:dtdl:context;2",
    "contents": [
        {"@type": "Property", "name": "name", "schema": "string"}
    ]
}

# API introduction example; if a model with the same ID is already loaded, do not duplicate.
client.create_models([
    sensor_model,
    building_model,
])
```

**Note:** this is an API example using Python dictionaries, not the complete set of 4 models for the sample graph. Models with relationship `target`s and component dependencies must be uploaded in a valid batch/order so references resolve cleanly without overwriting existing model IDs. Check exact input types against your SDK version. In a complete lab, upload the full DTDL for Building, Room, Sensor, and HVAC before building the graph.

### Step 2 — Create Twins

```python
building = {
    "$dtId": "bldg-a",
    "$metadata": {"$model": "dtmi:example:campus:Building;1"},
    "name": "Building A"
}

sensor = {
    "$dtId": "sensor-temp-01",
    "$metadata": {"$model": "dtmi:example:campus:Sensor;1"},
    "deviceId": "iot-sensor-01"
}

# Lab only: upsert can create or update the resource.
client.upsert_digital_twin("bldg-a", building)
client.upsert_digital_twin("sensor-temp-01", sensor)
```

**Caution:** `upsert` is not read-only. Incompatible models/schemas will fail. Never run against existing organizational twin IDs without approval.

### Step 3 — Create Relationships

Assuming the full Building model with `contains` is uploaded and `room-101` exists:

```python
relationship = {
    "$relationshipId": "bldg-a-contains-room-101",
    "$sourceId": "bldg-a",
    "$relationshipName": "contains",
    "$targetId": "room-101"
}

client.upsert_relationship(
    "bldg-a",
    "bldg-a-contains-room-101",
    relationship,
)
```

With `Building.contains` and target `room-101` present, the service validates schemas and IDs. If the target twin or model reference is missing/invalid, the operation is rejected.

## 23. SDK: Updating Properties with JSON Patch

Once a worker validates telemetry and determines an accepted reading, it can update a property:

```python
from azure.identity import DefaultAzureCredential
from azure.digitaltwins.core import DigitalTwinsClient
import os

client = DigitalTwinsClient(
    os.environ["ADT_ENDPOINT"],
    DefaultAzureCredential(),
)

# Simulated example; run only against twin room-101 in the lab.
patch = [
    {
        "op": "replace",
        "path": "/temperature",
        "value": 28.5,
    }
]

client.update_digital_twin(
    "room-101",
    patch,
)
```

**Verify:**

- Twin `room-101` already has property `temperature`; `replace` differs from `add`.
- Model schema permits a matching `double` value.
- Worker holds data-plane write permissions.
- Stale messages do not overwrite newer applied state.
- Competing writers need concurrency control/ETags or clear state ownership.
- A successful update in ADT **does not guarantee** all downstream consumers/analytics finished processing.

### What If the Property Doesn't Exist Yet?

JSON Patch `add` behaves differently from `replace`. Design initial property states and test patch operations against the API so you don't hit "path not found" and loop infinitely.

## 24. Managing Concurrency and Out-of-Order Telemetry

Suppose a sensor sends:

```text
Event A: observed 09:01 → 28.5°C
Event B: observed 09:02 → 29.0°C

Network:
  B reaches the worker first and updates 29.0
  A arrives later and overwrites with 28.5
```

Calling `update_digital_twin` blindly in arrival order causes **latest known state to move backward**.

### Safeguards

1. Carry event timestamps and sequences from a trusted source.
2. Persist `lastObservedAtUtc`/lastSequence in the state model or an ingestion state store.
3. Accept events only if newer than the current checkpoint for that sensor/twin.
4. When concurrent workers update, use **optimistic concurrency/ETags** where API and SDK support them.
5. Deduplicate on `eventId` so retries don't duplicate side effects.
6. Set clock-skew thresholds; device timestamps aren't always trustworthy.
7. With multiple sensors, compute aggregated room state over explicit windows.
8. Send very late events to history without necessarily overwriting current properties.
9. Add telemetry freshness alerts alongside high-temperature alerts.
10. Test reordering and duplicates in the pipeline.

**A read-then-write check across two separate requests can race.** For strict guarantees, use a proper concurrency strategy rather than comparing timestamps in memory and issuing unconditional updates.

## 25. Source of Truth and Ownership of Twin Properties

A common mistake is letting multiple systems write the same property:

```text
IoT worker      → room-101.temperature
BMS integration → room-101.temperature
Manual operator → room-101.temperature
```

Values overwrite each other unpredictably and become impossible to explain. Define an **ownership matrix**:

| Property/Relationship | Authoritative Source | Update Cadence |
|---|---|---|
| `Building.name` | Approved asset register/BIM. | On catalog changes. |
| `Room.location/floor` | Facility management system. | On structural changes. |
| `Room.temperature` | Sensor ingestion/aggregation worker. | Per sampling/quality policy. |
| `Room.occupancy` | Approved input/aggregation. | Per business and privacy policy. |
| `HVAC.operationalState` | BMS/control unit. | On state transitions. |
| `Room.servedBy` | Facility engineering/asset register. | On equipment reconfiguration. |

Store source metadata/observation timestamps where appropriate without adding unnecessary PII. Each owning system is responsible for handling sync errors or dropped updates.

## 26. A Model Graph Is Not a Physical Simulation Engine

A graph captures relationships, yet cannot compute on its own:

- Heat transfer across rooms via physics equations.
- HVAC power draw from rated capacity.
- Causal links between occupancy and air quality.
- Confirmation that a control command physically took effect.
- Predictive maintenance or setpoint optimization without external models/algorithms.

To simulate or predict, combine:

- Physics models or domain logic in compute/analytics.
- Azure Machine Learning/AI with proper training data and evaluation.
- Time-series history for calibration.
- Device control rules, thresholds, and fail-safe behavior.
- Human review or safety constraints for decisions affecting people.

**ADT provides context, topology, and state**—it does not turn a DTDL model into a "full physics simulator of everything."

## 27. Integrating BIM, GIS, ERP, and BMS Data

Modeling the real environment draws from multiple systems:

| Source | Data | How It Is Used |
|---|---|---|
| **BIM/CAD** | Floors, rooms, equipment layouts. | Seed initial topology or reconcile locations. |
| **GIS** | Coordinates/zones/addresses. | Link spaces outside buildings. |
| **ERP/CMDB** | Asset IDs, vendors, warranties, costs. | Authoritative asset metadata. |
| **BMS/SCADA** | Setpoints, control states, alarms. | Update operational state per policy. |
| **IoT Hub/Edge** | Measurements, online/offline, device events. | Update latest state and history. |
| **Azure Data Explorer** | Telemetry history/aggregates. | Long-term analytics and dashboards. |
| **Ticketing/work orders** | Maintenance items. | Connect twins to operational workflows. |

### Avoid "One Copy Containing Everything"

Never dump entire ERP records or PII into ADT simply because twins accept properties. Store only **metadata needed by the graph/use cases**, and use reference IDs/authorized APIs to fetch details from source systems.

## 28. ID Naming, Ontology, and Data Governance

Large projects require **naming conventions and ontologies**:

```text
Model IDs:
  dtmi:company:campus:Building;1
  dtmi:company:campus:Floor;1
  dtmi:company:campus:Room;1
  dtmi:company:campus:Sensor;1

Twin IDs:
  campus-hcm-bldg-a
  campus-hcm-bldg-a-floor-01
  campus-hcm-bldg-a-room-101
  device-sensor-00081

Relationships:
  bldg-a/contains/floor-01
  floor-01/contains/room-101
  room-101/monitoredBy/device-sensor-00081
```

These IDs are conventions only; character/length limits and escaping must follow API rules. Never embed emails, phone numbers, or secrets in IDs because they appear in logs, URLs, and diagnostics.

### Rules to Establish Before Deployment

- Who owns each model and can modify its definition?
- Do model versions have release notes and migration plans?
- Do two teams using `contains` mean the same thing?
- Are units °C or °F? kW or W? UTC or local time?
- When replacing a device, does the asset ID stay or change?
- When deleting/moving a room, how are old relationships cleaned up?
- Are orphan relationships and stale graphs prevented?
- Is there a tenant scope/permission matrix?

**Establishing ontology early** is far cheaper than refactoring millions of twins or changing semantics across dashboards later.

## 29. Versioned Schema/Model Changes

New requirement: Room must add `relativeHumidity` and `lastObservedAtUtc`. Never edit the model on paper and assume old twins automatically gain those fields.

Recommended workflow:

1. Determine whether the change is additive or breaking.
2. Author a **new DTDL model version** if required.
3. Validate model dependencies and data types.
4. Register the model in a test environment.
5. Update ingestion mappings, queries, and dashboards to handle the transition version.
6. Create/update twin instances via valid APIs.
7. Backfill properties from trusted sources if available.
8. Test consumers reading both v1 and v2 during transition.
9. Monitor model validation/query errors.
10. Once ready, retire old models/twins per workflow and service limits.

**Never assume deleting an old model is safe:** existing twins/relationships may still reference it. Deletion rules and version migrations depend on current API/support constraints.

## 30. Event Routes and Downstream Processing

When twins change or telemetry is published per supported features, ADT can emit events through **event routes** to endpoints such as Event Grid, Event Hubs, or Service Bus.

```text
ADT graph
   |
   +-- Twin lifecycle/property change events
   |
   +-- Telemetry events (if published)
   |
   v
ADT event route + filter
   |
   +-- Event Grid → Azure Functions/Logic Apps
   |
   +-- Event Hubs → streaming consumers/analytics
   |
   +-- Service Bus → downstream workflow
```

### Things to Manage

- A working route requires configured **endpoint, permissions, and filters**.
- Emitted events have a **schema** requiring compatible consumers.
- Delivery can be delayed, duplicated, or fail; never treat the message bus as sharing a transaction with twin updates.
- Consumers must be idempotent with retries and dead-letter/quarantine handling.
- Alert on route/endpoint errors or rising lag.
- Never route sensitive content to unapproved services/regions.
- Prevent feedback loops: ADT event → processor updates same twin → ADT emits event → infinite loop.

Use **event-origin/correlation IDs** and no-op checks (skip updating if state is unchanged) to prevent loops.

## 31. ADT vs. IoT Plug and Play Digital Twins

In the Azure IoT ecosystem, terms like **IoT Plug and Play** and **IoT Hub device twins** also appear. They are **not identical** to Azure Digital Twins.

| Concept | Purpose |
|---|---|
| **IoT Hub device twin** | Desired/reported properties, tags, and single-device state management inside IoT Hub. |
| **IoT Plug and Play model** | Device capability/telemetry/command contract, which may use DTDL depending on ecosystem. |
| **Azure Digital Twins graph twin** | Entity in the environment graph carrying relationships to rooms/assets/processes. |

Having desired state on an IoT Hub device twin does not automatically create an ADT graph twin. Even when both contexts use DTDL, **data planes, permissions, relationships, and sync mechanisms** differ.

### Integration Pattern

Design explicit mappings:

```text
IoT Hub deviceId = iot-sensor-01
    |
    v
Mapping service:
  deviceId → Sensor twin sensor-temp-01
  Sensor twin → Room twin room-101
    |
    v
Accepted telemetry updates Room.temperature
```

Never treat a device-reported property as the source of truth for facility asset data governed by facilities teams.

## 32. Azure IoT Edge and Pre-Cloud Processing

In factories, Internet connectivity can drop. Edge devices/gateways can:

1. Read Modbus/OPC UA or sensor signals via appropriate integrations.
2. Validate, filter outliers, and standardize units.
3. Aggregate readings over windows (e.g., 30 seconds).
4. Buffer events during outages.
5. Flush to IoT Hub when connectivity returns.
6. Attach timestamps/sequences so the cloud handles late events cleanly.

```text
Physical sensors
      |
      v
Edge gateway
  - validation
  - sampling/aggregation
  - local buffer
      |
      v
Azure IoT Hub
      |
      v
Worker → ADT latest state
       → historical stream
```

### Design Limitations

- Long buffering can cause bursts of stale data upon reconnect.
- Cloud workers must not overwrite current properties with late-arriving readings.
- Edge device auth/key lifecycles still require management.
- Edge AI/model inference needs dedicated hardware, licensing, and latency checks.
- Cloud graphs can go stale during outages; surface quality/freshness to operators.

**Edge compute and ADT complement each other** without solving full synchronization automatically.

## 33. Multi-Tier Graph Design and Query Efficiency

With a campus hierarchy Building → Floor → Room → Sensor, examine which queries run most often.

### Multi-Tier Graph

```text
campus-a
   |
   +--contains--> bldg-a
                    |
                    +--contains--> floor-01
                                      |
                                      +--contains--> room-101
                                                          |
                                                          +--monitoredBy--> sensor-01
```

Benefits:

- Mirrors the physical layout closely.
- Convenient queries by campus/building/floor.
- Clear updates when equipment moves or floors reconfigure.

Trade-offs:

- Queries must traverse multiple relationship hops.
- Large graphs need selective filters and bounded result sets.
- If UI screens repeatedly fetch large topology snapshots, build a dedicated **read model/cache** in the app.
- Moving rooms/sensors requires updating relationships while preserving business consistency.

### Selective Denormalization

A Room twin might store `buildingId` for fast lookups, yet if `bldg-a --contains--> room-101` also exists, **the two representations can drift**. Pick a single source of truth and sync via workflow rather than tolerating silent graph/property contradictions.

## 34. Data Quality and Interpreting Readings

A sensor reporting 35°C could mean:

- The room is genuinely overheating.
- The sensor sits right next to a hot exhaust vent.
- The device mixed up °C and °F.
- The sensor is faulty while still transmitting.
- The clock is skewed by several hours.
- Another tenant's message mapped to the wrong room.
- A synthetic test value leaked into the stream.

Checks before updating a twin:

1. Authenticate device/producer.
2. Validate payload schema and numeric ranges.
3. Normalize units (°C/°F, W/kW, kPa/Pa).
4. Verify device → Sensor twin → Room twin mapping.
5. Inspect quality flags and sensor health.
6. Filter outliers per approved rules.
7. Check timestamps/sequences/duplicates.
8. Determine which model property actually updates.
9. Record raw events in history if forensics may be needed.
10. Alert on stale/untrusted state rather than staying silent.

### Do Not "Clean Data" by Silently Altering Readings

If a system rewrites 35°C to 25°C simply because it looks abnormal, it could mask a real fire/overheating emergency. Smoothing and outlier rules require **domain owners**, monitoring, and audit trails.

## 35. Security: Identity, RBAC, and Least Privilege

ADT data plane uses Microsoft Entra identity/RBAC per supported capabilities. Separate permissions across layers:

| Layer | Permissions | Who Should Hold Them? |
|---|---|---|
| Azure control plane | Create/modify ADT instance, networking, endpoints, role assignments. | Minimal platform/infra team. |
| ADT graph data plane read | Query models/twins/relationships. | Authorized API readers/analysts. |
| ADT graph data plane write | Create/edit twins, properties, relationships, models per role. | Controlled ingestion workers/graph admins. |
| IoT Hub data plane | Receive/send device telemetry, manage identities as needed. | Scoped IoT services. |
| Analytics/ADX data plane | Query history. | Reporting backends/analysts. |
| Application authorization | Which zones/buildings/tenants a user can view. | Business backend. |
| Physical control authorization | Who can toggle equipment or change setpoints. | Safety-governed BMS/PLC workflows. |

**Data-plane graph read access does not imply permission to view every tenant in the web app.** When multiple tenants share an ADT instance, the app must enforce tenant ACLs/boundaries rather than trusting user-supplied `buildingId` parameters.

### Managed Identity

Azure Functions, Container Apps, or AKS workload identities can call ADT via `DefaultAzureCredential`/managed identity once assigned the proper scoped role. Enabling an identity **does not grant permissions automatically**; verify resource roles and endpoint access.

Never embed client secrets or access keys in firmware, frontends, or repos just to bypass 403 errors. For devices, use proper IoT Hub auth mechanisms.

## 36. Network, TLS, and Sensitive Location Data

Components often connect as:

```text
IoT devices / Edge
      |
      v
IoT Hub
      |
      v
Functions/Worker in appropriate network
      |
      +-- Azure Digital Twins endpoint
      +-- Event Grid/Event Hubs/Service Bus
      +-- Azure Data Explorer
      +-- Storage/Key Vault
```

Verify:

- How service tiers support Private Endpoints/Private Link/network restrictions.
- Whether Private DNS resolves properly from the worker/VNet.
- NSGs, Azure Firewall, UDRs, and outbound routes.
- TLS/hostname validation.
- Entra token audiences and data-plane roles.
- Event destination/handler permissions.
- Whether logs expose employee locations, occupancy behavior, or camera metadata.
- Retention rules for location/occupancy data.
- Data residency across graph, telemetry, history, and logs.
- Whether DR environments have matching networking/identities.

**Location/occupancy data can be sensitive.** Never store identities of people inside each room in twin properties indiscriminately. Apply aggregation, pseudonymization, and privacy policies.

## 37. Eventual Consistency, Graph State, and Transaction Needs

Never assume real-world changes update every system atomically at the exact same instant.

Example: moving a sensor from Room 101 to Room 102:

```text
T0 Facility DB records sensor relocation
T1 Integration worker deletes relationship Room101 -> Sensor
T2 Integration worker adds relationship Room102 -> Sensor
T3 Dashboard refreshes graph
T4 Telemetry adapter updates mapping
```

**Intermediate inconsistent states** can exist between T1–T4. Involved systems do not participate in a single distributed ACID transaction.

### Safe Design Practices

1. Establish a single **source of truth** for equipment moves.
2. Use stable **`operationId`/versions**.
3. Track transition states `Pending/Applied/Verified`.
4. Update mappings and graph via retryable workflows.
5. Stop the telemetry adapter from writing to the old room once mapping shifts.
6. Run reconciliation jobs verifying relationship consistency.
7. Block physical control actions until location is verified.
8. Maintain rollback/compensation plans.
9. Record event source and cutover timestamp.
10. Show "syncing" when topology is not yet consistent.

**Azure Digital Twins does not wrap multi-node/edge edits plus IoT Hub/BMS updates into a global transaction.** Business logic must handle eventual consistency.

## 38. Availability, Backup, Recovery, and Rebuilding the Model

A digital twin system has two recovery sources:

- **Schema/topology state:** DTDL models, twin instances, relationship graph, properties/metadata.
- **Raw/history/source systems:** IoT events, asset registers, BIM, BMS, ERP, logs.

Ask:

1. Can we **rebuild the graph** from IaC/scripts/asset catalogs/relationship exports?
2. Are snapshots/exports/versioned definitions maintained per policy?
3. Where is the latest state rehydrated from if an instance fails?
4. Could latest properties unpersisted elsewhere be lost?
5. Can event routes and endpoints be reconfigured cleanly?
6. If failing over to another region, do model IDs and twin IDs remain stable?
7. Do apps know how to switch endpoints and reconnect with updated identities?
8. Have dry-run restores been tested with lab data?

**Do not assume ADT provides SQL Database-style PITR/geo-replication.** Design backup/restore/DR around exact service capabilities and authoritative rebuild sources.

## 39. Monitoring Azure Digital Twins and Pipelines

Signals to observe:

| Category | Signals | Meaning |
|---|---|---|
| Graph/data plane | Twin/relationship create/update/query failures. | Schema, permission, or capacity errors. |
| Event processing | IoT Hub ingress, Function failures, retries, DLQs. | Dropped/delayed events or malformed payloads. |
| Freshness | Time since last valid observation per sensor/twin. | Stale property still shown in UI. |
| Data quality | Invalid units, outliers, unknown `deviceId`, mapping misses. | Risk of inaccurate state. |
| Graph integrity | Missing targets, orphan assets, conflicting relationships. | Topology out of sync with reality. |
| Downstream | Event route delivery errors, lag, ADX ingestion failures. | Lost historical/alerting visibility. |
| Security | 401/403s, role changes, suspicious reads/cross-tenant requests. | Permission drift or attacks. |
| Performance | p95 query/update latency, throttling/429s, operation counts. | Resource/architecture bottlenecks. |
| Costs | ADT operations/messages, event transport, history storage/compute, logs. | Cost forecasting and optimization. |

**Do not claim all of these are built-in Azure Monitor metrics with these exact names.** Many require application-level telemetry or reconciliation jobs beyond built-in metrics/diagnostic logs.

### Key Alerts

- Sensor emits no valid event for 10 minutes when 1-minute cadence is expected.
- Ingestion worker repeatedly retries 429/5xx errors.
- Sudden spike in unknown `deviceId` rates.
- ADT event route or ADX history ingestion stops.
- Graph queries fail with 403 after identity/role changes.
- Rising orphan relationships or asset mapping conflicts.
- Unusual spikes in operation counts or logging costs.

The 10-minute threshold is **illustrative**; tune thresholds to sampling rates, networks, SLAs, and asset criticality.

## 40. Cost: Not Just the Price of One Twin

An architecture includes:

```text
Monthly total cost ≈
  Azure Digital Twins data-plane operations and messages
+ IoT Hub/device messaging
+ Azure Functions/Container Apps/Edge compute
+ Event Grid/Event Hubs/Service Bus
+ Azure Data Explorer/Storage historical data
+ Networking/Private Endpoint
+ Monitoring/Log Analytics
+ Model/topology maintenance and support
```

### Workload Drivers

- Number of twins and relationships.
- Frequency of property updates, graph queries, and event routes.
- Number of sensors × messages per minute.
- Edge aggregation cadence and cloud-bound event volume.
- Number of consumers and reprocessing runs.
- History retention length and ADX query volume.
- Asset catalog sync frequency.
- Retry storms or redundant property writes when values haven't changed.

### Telemetry Volume Estimation Example

Suppose 1,000 sensors each send 1 message/minute:

```text
1,000 sensors × 1 message/min = 1,000 messages/min
                              = 60,000 messages/hour
                              = 1,440,000 messages/day
```

**1.44 million messages/day does not automatically equal 1.44 million twin property updates:** adapters can aggregate/deduplicate and write only when state changes. Each service meters differently; measure real workloads and check the Azure Pricing Calculator for your region and tier.

**Never reduce monitoring frequency on a safety-critical system solely to cut costs without domain owner sign-off.**

## 41. Runbook: Sensor Sends Telemetry Yet room.temperature Doesn't Change

**Symptom:** IoT Hub receives new readings, yet the ADT dashboard for Room 101 still shows 25°C while actual temperature is 29°C.

### Investigation

1. Identify device ID, `eventId`, and latest measurement timestamp.
2. Did IoT Hub route the event to the right worker?
3. Did the worker hit message parse/schema/range errors?
4. Is the Device → Sensor twin → Room twin mapping accurate?
5. Does the worker have ADT write permissions and point to the right endpoint/tenant?
6. Does JSON Patch path `/temperature` exist in the twin schema/instance?
7. Did idempotency/out-of-order logic drop the event erroneously?
8. Are there 429/5xx/network/TLS/permission errors?
9. Is the dashboard query reading stale cache or the wrong twin ID?
10. If the property updated, check UI refresh and client timezone.

### Remediation

- Fix the root cause in routes, schemas, or mappings.
- Replay valid events from retained sources without causing duplicate side effects.
- Use timestamps/sequences to prevent backward overwrites.
- Display source of truth and freshness timestamps clearly in the UI.
- Alert whenever telemetry ingress is active yet twin latest state goes stale.

## 42. Runbook: Model or Relationship Creation Fails

**Symptom:** uploading DTDL or creating a relationship returns an error.

### Model Checks

1. Is JSON valid, and does `@context` match the DTDL version?
2. Does `@id` follow valid DTMI syntax/versioning?
3. Do `@type` and `contents` conform to schema?
4. Does relationship `target` point to a valid, resolvable model ID?
5. Does component `schema` reference a valid interface dependency?
6. Is there a collision with an already-uploaded model ID?
7. Does the model exceed limits or use unsupported capabilities?
8. Does the principal hold model-write permissions?
9. Does the endpoint point to the right ADT instance?

### Relationship Checks

1. Do both source twin and target twin exist?
2. Does the source model declare `contains`/`monitoredBy`/`servedBy` with the exact name?
3. Does the target twin's model match the declared `target`?
4. Do `$sourceId`/`$targetId`/`$relationshipName` match the payload?
5. Is the relationship ID conflicting or invalidly formatted?
6. Is a concurrent operation modifying or deleting the involved twins?

**Never fix 400 errors by deleting old models blindly.** Fix DTDL/schemas and manage versions; deleting models can impact many twins.

## 43. Runbook: Graph Shows Valid Data in the Wrong Zone

**Symptom:** Room 101 is linked to Building B even though the asset register places it in Building A.

### Investigation

- Which BIM/ERP import created the initial relationship?
- Did a room ID or model version change?
- Are two integrations performing competing double writes?
- Are twin IDs normalized by campus/building/tenant?
- Did a worker retry emit a stale relationship?
- Is there an approved mapping table?
- Was a tenant authorization boundary crossed?
- Is the dashboard caching an old graph?

### Remediation

1. Confirm authoritative topology.
2. Pause the misbehaving sync pipeline if needed.
3. Correct the relationship via an audited change request.
4. Verify no orphan or conflicting edges remain.
5. Update mappings and test replay/reconciliation.
6. Ensure future sensor readings route to the right room.
7. Add multi-tenant/hierarchy integration tests.

**A graph error can turn into an authorization breach or physical control error**, not just a cosmetic chart bug.

## 44. Hands-On Lab: Modeling a Building in Azure Digital Twins

**Context:** a lab campus has Building A, two rooms, one temperature sensor, and one HVAC unit. All IDs/values are simulated. Use only an authorized Azure subscription/resource group and lab ADT instance.

### Target Graph

```text
                 [bldg-a]
                    |
       +------------+-----------+
       |                        |
    contains                  contains
       |                        |
       v                        v
   [room-101]              [room-102]
       |
       +---monitoredBy---> [sensor-temp-01]
       |
       +---servedBy------> [hvac-01]
```

### Expected Data

| Twin ID | Model | Sample Properties |
|---|---|---|
| `bldg-a` | Building;1 | name = "Building A". |
| `room-101` | Room;1 | name="Room 101", temperature=25.1, occupancy=0. |
| `room-102` | Room;1 | name="Room 102", temperature=24.0, occupancy=2. |
| `sensor-temp-01` | Sensor;1 | deviceId="iot-sensor-01", health="Healthy". |
| `hvac-01` | HVAC;1 | name="HVAC A-01", operationalState="Running". |

### Tasks

1. Write a short explanation distinguishing ADT from IoT Hub and historical storage.
2. Create a lab ADT instance per budget/approval; verify region, endpoint, and permissions.
3. Complete the four DTDL v2 models: Building, Room, Sensor, HVAC.
4. Validate JSON, IDs, targets, and dependencies before uploading.
5. Upload models in dependency order or SDK-supported batch.
6. Create the five twin instances from the uploaded models.
7. Create two Building `contains` Room relationships.
8. Create Room 101 `monitoredBy` Sensor relationship.
9. Create Room 101 `servedBy` HVAC relationship.
10. Query all Room twins by model.
11. Query rooms inside Building A using `JOIN ... RELATED`.
12. Query Rooms with `temperature > 27°C` before and after updating.
13. Send a simulated IoT message through the lab pipeline—never use Production devices.
14. Have the adapter verify `deviceId`, timestamp, temperature unit, and quality.
15. Update `room-101.temperature` via JSON Patch after validation.
16. Verify querying Room 101 returns the latest 28.5°C.
17. Simulate an old event arriving after a newer event; confirm current state is not overwritten.
18. Diagram the route from ADT to analytics/history and state required configurations.
19. Explain why 7 days of history cannot be read from a single twin property.
20. Run a query with an unauthorized identity; expect 403/permission denial.
21. Attempt creating a relationship to a nonexistent target twin; confirm API rejection.
22. Design a v2 model adding humidity.
23. Configure three alerts: stale sensor state, ingestion worker errors, event route failure.
24. Write a checklist for location/occupancy data and least privilege.
25. Forecast load/cost from sensor count × sampling interval.
26. Prepare a scoped cleanup/rebuild plan without touching shared resources.

### Evidence to Demonstrate

- DTDL models with clear IDs/versions.
- Each twin instance carries the right `$metadata.$model`.
- Valid relationship IDs/sources/targets.
- Graph query returning Building A's Rooms accurately.
- State updates passing through a validated adapter rather than arbitrary devices writing directly to any twin.
- Old events failing to overwrite newer state.
- Clear distinction between latest state and time-series history.
- Identity, network, and safety restrictions enforced.
- Sanitized logs plus request count/latency measurements.
- Model migration and recovery plan.

### Reference Solution Direction

A solid design uses **IoT Hub for device connectivity**, **Functions/workers for event quality validation**, **ADT for graph topology and latest known state**, and **Azure Data Explorer or appropriate historical storage for time-series analytics**. DTDL models define types/relationships; data-plane identities and application authorization govern read/write access; and **BMS/control systems** decide when a real command may physically affect the environment.

## 45. Production Readiness Checklist

**Model/graph**

- [ ] Maintain a physical asset inventory, source of truth, and ownership matrix.
- [ ] Model IDs follow DTMI/versioning; DTDL schemas validated.
- [ ] Clear distinction between model and twin instance, property and telemetry.
- [ ] Naming conventions, units, timestamps, and ID mappings defined.
- [ ] Relationships oriented consistently with uniform semantics.
- [ ] Workflows exist for orphan/stale graph cleanup and asset relocation.
- [ ] Migration plans defined for new model versions.
- [ ] Large history never stuffed into twin properties.

**Ingestion/consistency**

- [ ] IoT Hub/edge pipelines authenticated and schema-validated.
- [ ] Device IDs never trusted solely from unverified payloads.
- [ ] Device → twin mappings governed with tenant boundary checks.
- [ ] Deduplication, retries, backoff, and DLQ/quarantine designed.
- [ ] `observedAtUtc`/sequence enforced with out-of-order handling.
- [ ] Freshness/quality/health surfaced whenever data turns stale.
- [ ] Clear state owners preventing uncontrolled multi-writer races.
- [ ] ADT event routes and history integrations tested end-to-end.

**Security/safety**

- [ ] Managed identities/data-plane roles scoped narrowly.
- [ ] Application authorization enforced by tenant/location.
- [ ] Private networking/DNS/TLS verified from runtime.
- [ ] Logs avoid leaking unnecessary PII/sensitive locations.
- [ ] Data residency/retention and consent evaluated.
- [ ] Control actions backed by rule engines, approvals, and fail-safes.
- [ ] Twin updates never treated as automatic physical commands.
- [ ] Incident runbooks exist for permissions, topology, and data quality.

**Operations/cost**

- [ ] Metrics cover update/query failures, ingestion lag, and route errors.
- [ ] Alerts trigger on silent sensors or stale state.
- [ ] Graph recovery/rebuild plans exist using authoritative sources.
- [ ] Capacity/quotas/429s/backoff load-tested.
- [ ] Cost model spans ADT, IoT Hub, workers, events, history, and logs.
- [ ] Restores, model migrations, and change approvals tested.
- [ ] Lab cleanup isolated from Production.

## 46. Self-Check Questions

**Q1.** How does Azure Digital Twins differ in purpose from Azure IoT Hub?

**Answer:** ADT models object/state/relationship graphs of an environment; IoT Hub handles device connectivity and messaging per IoT Hub capabilities. They complement rather than replace each other.

**Q2.** Do a model and a twin instance share the same ID?

**Answer:** No. A DTDL model has a DTMI like `dtmi:example:campus:Room;1`, whereas an instance has a `$dtId` like `room-101`.

**Q3.** How do DTDL `Property` and `Telemetry` differ?

**Answer:** Property represents persisted state on the twin; Telemetry declares events/measurements and neither auto-updates properties nor stores history without a pipeline.

**Q4.** Does a `contains` relationship from Building to Room automatically create a reverse edge?

**Answer:** No. Relationships are directed edges; write traversal queries or explicitly model reverse relationships if needed.

**Q5.** Can one Building contain multiple rooms using a single relationship instance?

**Answer:** Not in that naive way; create separate relationship instances from Building to each Room with distinct IDs.

**Q6.** How does DTDL `@id` differ from `$dtId`?

**Answer:** `@id` identifies the model schema; `$dtId` identifies a twin instance in the graph.

**Q7.** What does `@context` do in DTDL v2?

**Answer:** Specifies the DTDL grammar/context, e.g., `dtmi:dtdl:context;2`.

**Q8.** Does ADT automatically collect MQTT telemetry from every sensor once a Room twin is created?

**Answer:** No. Devices/IoT Hub, ingestion workers, and mapping/update logic are required.

**Q9.** Why not use a temperature graph property to chart 12 months of history?

**Answer:** A property holds only the latest known state, not a complete time-series store; a history pipeline/store is needed.

**Q10.** How do Azure Data Explorer and Azure Digital Twins complement each other?

**Answer:** ADT holds topology/context/latest state; ADX excels at storing and analyzing time-series event history.

**Q11.** Does a sensor sending 29°C mean the Room twin immediately becomes 29°C?

**Answer:** No. Workers must authenticate, map, validate, and explicitly update state.

**Q12.** Why are event timestamps important?

**Answer:** Late-arriving events can overwrite newer values; event time/sequence, idempotency, and concurrency controls prevent regressions.

**Q13.** Can a twin instance represent a room without its own sensor?

**Answer:** Yes. It remains an environmental entity with metadata/relationships updatable from management sources or derived calculations.

**Q14.** How does a component differ from a relationship?

**Answer:** A component is a structured sub-part inside a model/twin; a relationship links two independent twins with separate IDs and lifecycles.

**Q15.** Does `writable=true` mean any user is allowed to write that property?

**Answer:** No. That is schema metadata, not Azure RBAC or application permissions.

**Q16.** What is `IS_OF_MODEL` used for?

**Answer:** Filtering twins matching a model ID in the Azure Digital Twins Query Language.

**Q17.** Does ADT query support every SQL Database feature?

**Answer:** No. It is built for graph/twin queries; historical analytics and large aggregations usually require an analytics store.

**Q18.** Does Azure Contributor automatically grant all ADT data-plane permissions?

**Answer:** No. Specific data-plane roles and separate application authorization are required.

**Q19.** Does enabling managed identity mean ADT access already works?

**Answer:** Not yet. Scoped roles, network/DNS/TLS, and matching token audiences are needed.

**Q20.** Should names of people inside a room be stored in twin properties when unnecessary for business?

**Answer:** No. Follow data minimization/privacy and store only authorized, necessary attributes.

**Q21.** Does a successful ADT property update mean Event Hubs/ADX already received it?

**Answer:** No. Event routes/downstream delivery can lag or fail; monitor the pipeline separately.

**Q22.** When upgrading Room model v1 to v2, can you edit models/twins directly with zero app impact?

**Answer:** Never assume that. Versioning, migrations, and testing consumers/indexes/ingestion are required.

**Q23.** Is an IoT Hub device twin identical to an Azure Digital Twins graph twin?

**Answer:** No. They operate on different data planes for different purposes.

**Q24.** How does Azure IoT Edge help when a factory loses connectivity?

**Answer:** It can process/buffer near devices and resend when connectivity recovers; the cloud still must handle late/duplicate events.

**Q25.** When a sensor moves to another room, what must be updated?

**Answer:** Authoritative mapping sources, graph relationships, and related pipelines per workflow, avoiding conflicting writers.

**Q26.** Does the graph automatically compute heat propagation via physics equations?

**Answer:** No. Separate simulation/domain logic/ML models are needed if required.

**Q27.** Why shouldn't an AI agent automatically shut off HVAC simply because a twin shows high temperature?

**Answer:** Twin state may be stale/wrong; physical control requires sensor verification, safety policies, authorization, and fail-safe workflows.

**Q28.** What makes multi-tenant graph queries dangerous?

**Answer:** If an API filters solely by twin ID without authorization checks, it can leak another tenant's topology/locations.

**Q29.** As sensor count grows, which components incur costs?

**Answer:** IoT messages, ingestion compute, ADT operations/events, history storage/queries, networking, and monitoring.

**Q30.** What is ADT's core value in an IoT/edge architecture?

**Answer:** Creating **structured digital context** across assets, spaces, and their relationships—linking data and applications to query, analyze, and operate the physical environment safely.

**Summary:** **Azure Digital Twins** uses **DTDL models** to define entity types, **twin instances** to represent assets/spaces, and **relationships** to build a graph of the physical environment. IoT Hub/Edge supply telemetry, Functions/workers validate and update state, and event routes/historical stores power downstream analytics. Sound design separates **latest state from telemetry history, models from instances, components from relationships, and graph context from physical actuation**, backed by versioning, authorization, data quality, concurrency, observability, backup/rebuild plans, and cost management. A digital twin is only useful when **relationships are accurate, data is sufficiently fresh, and real-world usage remains safe**.
