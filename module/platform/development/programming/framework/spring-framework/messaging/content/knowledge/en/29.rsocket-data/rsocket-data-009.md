# Contract Compatibility When Changing Codecs, Routes, or Data Types

In Spring Messaging with RSocket, the communication contract is not just a Java DTO. Each request depends simultaneously on the route used for routing, how payloads are encoded, the data types expected by both ends, and the RSocket interaction model. A small change in one layer can prevent older clients from calling handlers, decoding payloads, or interpreting data accurately.

The goal of compatibility management is to allow clients and servers to be upgraded at different times while still exchanging data properly. To achieve that, you must identify which part of the contract is changing, classify the compatibility level, and roll out changes in phases.

## 1. What parts make up an RSocket contract?

An RSocket message has a **data** part and a **metadata** part. Metadata can carry routes, authentication info, or auxiliary data. Data typically carries the business payload. These two parts can use different formats.

There are four parts to manage:

1. **Route:** the target name sent by the requester in metadata and used by the responder to locate a handler. For example: **orders.submit.v1**.
2. **Codec and MIME type:** how objects are converted to bytes and bytes decoded back into objects. For example, JSON, CBOR, or Protobuf.
3. **Payload schema:** field names, data types, required fields, default values, semantics, and nullability rules.
4. **Interaction model:** Request-Response, Request-Stream, Channel, or Fire-and-Forget. Changing from a single result to a stream of results is also a contract change.

A route is not a field inside a JSON payload. Routes usually live in routing metadata. Therefore, editing a DTO does not automatically change the route, and changing a route does not automatically change the payload schema.

RSocket declares MIME types for data and metadata in the connection's `SETUP` frame. These MIME types apply to requests on that connection. This is critical when rolling out codec changes: both sides must agree on how to encode and decode on each connection.

## 2. Classifying changes by compatibility level

| Change | Risk | How to Handle |
|---|---|---|
| Adding an optional field | Usually compatible if old consumers ignore unknown fields and new consumers handle missing fields | Keep the new field optional and define clear defaults |
| Adding a required field | May cause new consumers to reject old payloads | Enable enforcement only after all producers send the field |
| Renaming or deleting a field | Breaking change | Maintain aliases or old DTO versions during transition |
| Changing a field's data type | Breaking change if representation or value domain is incompatible | Create a new schema version and migrate explicitly |
| Changing a field's meaning | Dangerous because payload still decodes but business logic is wrong | Introduce a new field or a new contract version |
| Adding an enum value | Can break old consumers if enum handling is closed | Provide a fallback branch for unknown values |
| Changing a route | Clients calling the old route may fail to find a handler | Keep the old route as an alias during migration |
| Switching JSON to CBOR or Protobuf | Endpoints may fail to decode each other's payload bytes | Align MIME types, codecs, and a connection migration plan |
| Changing Request-Response to Stream | Changes return type, lifecycle, and consumption model | Treat as a new contract and test separately |

A change is compatible only when both actual producers and actual consumers handle it properly. Never conclude that "adding a field is always safe" without checking unknown-field decoding settings, null rules, and the behavior of running clients.

## 3. Maintaining compatibility when changing routes

In Spring, RSocket responders typically declare handlers with **@MessageMapping**. Requesters specify the route via **RSocketRequester.route(...)**.

~~~java
@Controller
class OrderRSocketController {

    @MessageMapping("orders.submit.v1")
    Mono<Receipt> submitV1(OrderSubmitV1 request) {
        return orderService.submit(request);
    }
}
~~~

The requester calls the agreed route:

~~~java
Mono<Receipt> response = requester
    .route("orders.submit.v1")
    .data(request)
    .retrieveMono(Receipt.class);
~~~

If the route changes from **orders.submit** to **orders.create**, older clients still send **orders.submit**. A new handler listening only on the new route will not automatically be compatible with older clients.

You can maintain both routes during the transition and share business logic:

~~~java
@Controller
class OrderRSocketController {

    @MessageMapping("orders.submit")
    Mono<Receipt> submitLegacy(OrderSubmitV1 request) {
        return orderService.submit(request);
    }

    @MessageMapping("orders.create.v2")
    Mono<Receipt> createV2(OrderSubmitV2 request) {
        return orderService.submit(toCommand(request));
    }
}
~~~

This allows the old and new routes to coexist while clients upgrade. Only after telemetry confirms zero traffic on the old route should you remove the legacy handler.

Spring uses a route matcher to find handlers. The default **SimpleRouteMatcher** is based on **AntPathMatcher**; when **spring-web** is present, **PathPatternRouteMatcher** can be configured. RSocket routes can be hierarchical and use dots as the default separator. They are not URL paths: do not apply HTTP URL-decoding or slash assumptions to RSocket routes.

When designing routes:

- Use stable names describing the action or capability.
- Add a version to the route only when a new major contract is needed, such as **orders.create.v2**.
- Keep the old route during the transition window.
- Test exact routes, route patterns, and route variables if the application uses them.
- Never use routes to hold long business data or secrets.

## 4. Maintaining compatibility when changing codecs and MIME types

The codec determines how objects are serialized into bytes. The decoder on the receiving side must understand that exact byte format. For example, a client encoding objects as JSON while the server decodes as CBOR will fail to process payloads as expected.

In Spring, **RSocketStrategies** bundles encoders, decoders, and the route matcher. Basic codecs from **spring-core** support **String**, **byte[]**, and **ByteBuffer**. With **spring-web**, applications can additionally register JSON, CBOR, or Protobuf codecs.

Example CBOR configuration using current Spring APIs:

~~~java
@Bean
RSocketStrategies rsocketStrategies() {
    return RSocketStrategies.builder()
        .encoders(encoders -> encoders.add(new JacksonCborEncoder()))
        .decoders(decoders -> decoders.add(new JacksonCborDecoder()))
        .routeMatcher(new PathPatternRouteMatcher())
        .build();
}
~~~

You can use the same strategy configuration for both requester and responder to reduce the risk of registering mismatched codecs on either side. In real applications, verify the codec class names corresponding to the Spring version in use.

The requester can declare the data MIME type when establishing the connection:

~~~java
RSocketRequester requester = RSocketRequester.builder()
    .dataMimeType(MimeType.valueOf("application/cbor"))
    .rsocketStrategies(rsocketStrategies)
    .tcp("localhost", 7000);
~~~

Distinguish between:

- **Data MIME type** describes the format of business payloads.
- **Metadata MIME type** describes the format of metadata. Composite metadata allows multiple metadata entries with individual formats, such as routing and authentication.
- **Encoder** is used when sending objects; **Decoder** is used when receiving objects. Client and server need compatible encoder/decoder pairs for both requests and responses.

Because data MIME type is announced in `SETUP` and applies to the connection, do not change one side's codec config and assume open connections will automatically switch to the new format. When changing MIME types, establish connections with the new config and ensure the peer supports the corresponding format. If multiple formats must run in parallel, organize connections or endpoints so they can be distinguished and monitored.

Several principles when changing codecs:

1. Identify the current and target MIME types on both requester and responder.
2. Register decoders before starting to send payloads in the new format.
3. If the MIME type changes at the connection level, open new connections with the matching configuration.
4. Test both request and response directions; the two directions may use different objects and codecs.
5. Do not implicitly rely on codec registration order to pick the default MIME type. When stability matters, declare the MIME type explicitly.
6. Retain the ability to read the old format during migration if legacy clients still exist.

## 5. Safely changing schemas and data types

The schema describes the structure and meaning of payloads. With JSON, field names and value representations usually dictate compatibility. With binary formats like Protobuf, field numbers and schema evolution rules are also part of the contract.

### Adding an optional field

Suppose the old payload has three fields:

~~~json
{
  "orderId": "O-100",
  "amount": 125000,
  "currency": "VND"
}
~~~

The new version wants to add a **channel** field:

~~~json
{
  "orderId": "O-100",
  "amount": 125000,
  "currency": "VND",
  "channel": "MOBILE"
}
~~~

This can be a compatible change if old consumers tolerate unknown fields and new consumers still handle old payloads lacking **channel**. However, unknown-field behavior depends on Jackson and specific codec settings; test with the application's actual configuration.

When the new field is absent, the application should specify a default value at the boundary converting the DTO to the business model:

~~~java
String channel = request.channel() == null
    ? "WEB"
    : request.channel();
~~~

Avoid accidentally relying on Java primitive default values. For example, a missing primitive numeric field might become **0**, even though **0** could be a valid business value. Use nullable types or explicit checks to distinguish "not sent" from "sent as 0".

### Renaming fields

Renaming **customerId** to **buyerId** can prevent old clients and new servers from understanding the same payload. When using Jackson, an alias can accept the old name during transition:

~~~java
record OrderRequest(
    @JsonAlias("customerId") String buyerId
) {}
~~~

An alias lets the decoder accept both the old name and the new name; separately check the field name emitted by the encoder to ensure new producers send the agreed format. Once all producers have switched to the new name, the alias can be removed in a subsequent major version.

### Changing field types or semantics

The following changes must be treated as breaking changes unless a verified conversion rule exists:

- **amount** from integer to string.
- **createdAt** from epoch milliseconds to ISO-8601.
- **quantity** from individual items to boxes.
- A nullable field becoming required.
- Extending an enum while old consumers reject unknown values.

Keeping the same field name does not mean the contract remains compatible. Semantics, units of measure, value ranges, timezones, and rounding rules are all part of the schema.

With Protobuf, never reuse deleted field numbers; mark deleted field numbers and names as `reserved` per Protobuf rules. With JSON, explicitly define how unknown fields, null values, and new enum values are handled.

### Separating DTOs by version

When a change cannot be made compatible, using separate DTOs keeps a clear boundary between the two contracts:

~~~java
record OrderSubmitV1(
    String orderId,
    BigDecimal amount,
    String currency
) {}

record OrderSubmitV2(
    String orderId,
    BigDecimal amount,
    String currency,
    String channel
) {}
~~~

Convert the DTO into an internal command or domain model before invoking business logic. That way, business logic does not depend on which payload version the client used.

## 6. Migration workflow without disrupting clients

A safe rollout process can be broken into the following steps:

1. **Inventory active contracts:** record routes, MIME types, payload schemas, interaction models, and client versions. Identify which consumers still use legacy routes or codecs.
2. **Expand the receiving side:** deploy handlers or decoders capable of accepting both old and new formats. If changing MIME types at the connection level, prepare new configurations/connections rather than silently altering live connections.
3. **Keep the old route:** add the new route while continuing to serve the old route. If the new schema is incompatible, use a new DTO and map it to the internal model.
4. **Migrate producers in waves:** upgrade clients in batches, optionally using configuration or feature flags to control when they switch.
5. **Monitor traffic:** count requests by route, MIME type, payload version, and client version. Monitor route-not-found errors, decoding errors, and validation errors.
6. **Retire the old contract:** delete old routes, decoders, or DTOs only when metrics confirm no consumers still need them and the support window has ended.

If the change only adds an optional field, you can keep the route and MIME type. If changing codecs, handle MIME type compatibility. If changing payload structure or semantics in a breaking way, create a new contract version. Avoid combining all three types of changes in a single release without clear justification.

## 7. Contract testing

Unit tests for DTOs are not enough to prove two RSocket applications are compatible. Test at the requester–responder boundary using the exact codecs, MIME types, route matchers, and Jackson/Protobuf configurations of the runtime environment.

Minimum test matrix:

| Producer | Consumer | What to Verify |
|---|---|---|
| Old client | New server | Old route still works; old payload still decodes |
| New client | Old server | Expect pass only if the change was designed to be backward-compatible |
| New client | New server | New route, MIME type, schema, and response match |
| Payload missing new field | New consumer | Defaulting or validation matches the contract |
| Payload with unknown field | Old consumer | Ignored or rejected as configured |
| Payload with unknown enum | Consumer | Intentional fallback or error |
| Connection using old/new MIME type | Corresponding peer | No cross-format mis-decoding occurs |

Save sample payloads (golden fixtures) for each version. For binary codecs, also test reading payloads produced by earlier versions. For JSON, check field names, nulls, large numbers, decimal precision, and date/time formats.

Also verify the interaction model: Request-Response must return a single response; Request-Stream must preserve element types and order; Channel must handle bidirectional streams and backpressure; Fire-and-Forget confirms only message transmission, not that the handler finished business work.

## 8. Observability and error handling during migration

During migration, logs and metrics should help answer:

- Which routes are being called and how frequently is the old route used?
- What data MIME type and metadata MIME type are connections using?
- Which client version or contract version sent the request?
- How many route-not-found errors, decode/encode errors, or validation errors occur?
- Did the error happen on the request, response, or while processing a stream?

Contract version can be carried in metadata or a standardized header field, provided both sides agree on how to transmit and decode it. Never log tokens, personal data, or full sensitive payloads. Use correlation IDs to link requester and responder logs.

When an error is detected after rollout, identify which layer failed before rolling back: mismatched route, incompatible MIME type, undecodable schema, or decoded data with wrong semantics. Rolling a producer back to an earlier version is safe only while the server still keeps the old route and decoder.

## 9. Pre-release checklist

- [ ] Recorded routes, MIME types, schemas, and interaction models of the current contract.
- [ ] Classified changes as compatible or breaking.
- [ ] Old routes still have handlers during the required support window.
- [ ] Requester and responder have compatible encoders/decoders for both requests and responses.
- [ ] Connection MIME types are explicitly configured and aligned.
- [ ] New consumers properly handle missing fields, nulls, unknown fields, and unknown enums.
- [ ] Tested old clients against the new server with realistic payloads.
- [ ] Tested new connections if data MIME type changed.
- [ ] Metrics exist to detect when traffic leaves the old contract.
- [ ] Clear retirement criteria established before removing old routes, codecs, or DTOs.

## 10. References

- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — message model, requester, responder, routes, MIME types, `RSocketStrategies`, and codecs.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — protocol structure, `SETUP`, data, and metadata.
- [Spring Framework API: RSocketRequester](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketRequester.html) — request creation and requester configuration APIs.
- [Spring Framework API: RSocketStrategies](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/rsocket/RSocketStrategies.html) — encoder, decoder, and route matcher configuration.
