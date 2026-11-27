# Distinguishing Exact Channels from Pattern Subscriptions in Spring Data Redis Pub/Sub

## 1. The problem: listen to a single channel or a group of channels?

Redis Pub/Sub allows an application to **publish** messages to a channel name and connected **subscribers** to receive the corresponding messages. With Spring Data Redis, an application can register two subscription types:

- **Exact channel** (*exact channel subscription*): listens to **one exact channel name**, using the Redis `SUBSCRIBE` command or `ChannelTopic` in Spring Data Redis.
- **Pattern subscription**: listens to **any channel whose name matches a glob pattern**, using the Redis `PSUBSCRIBE` command or `PatternTopic`.

Suppose a system emits the events:

```text
orders.created
orders.cancelled
orders.paid
payments.completed
```

If a component only handles order creation events, it can subscribe directly to `orders.created`.

If a component logs all order events, it can subscribe to the pattern `orders.*`. When an event is published to `orders.created`, both subscription forms can receive the message.

Key point: **the publisher still publishes to a specific channel name**. The pattern lives on the **subscriber** side and is a rule for selecting which channels to listen to; it is not a separate type of channel that the publisher writes to.

After this lesson, you will be able to:

1. Distinguish `SUBSCRIBE`, `PSUBSCRIBE`, `UNSUBSCRIBE`, and `PUNSUBSCRIBE`.
2. Understand Redis glob rules and avoid confusing them with regex.
3. Distinguish `message` notifications from `pmessage` notifications.
4. Use `ChannelTopic` and `PatternTopic` with `RedisMessageListenerContainer`.
5. Recognize that a single publication can arrive multiple times when subscriptions overlap.
6. Choose subscription scope based on business, security, and performance requirements.
7. Understand limitations regarding durability, ordering, subscription timing, and multi-instance operation.
8. Diagnose issues when a subscriber receives none or more messages than expected.

## 2. How Redis Pub/Sub works

A publisher sends a message:

```redis
PUBLISH orders.created '{"orderId":"o-101","status":"CREATED"}'
```

Redis determines the matching subscriptions and delivers the message to those subscribed clients:

```text
                          Redis Pub/Sub

Publisher
    |
    | PUBLISH orders.created payload
    v
Channel name "orders.created"
    |
    +--> Client A: SUBSCRIBE orders.created  ------> receives
    |
    +--> Client B: PSUBSCRIBE orders.*       ------> receives
    |
    +--> Client C: PSUBSCRIBE orders.paid    ------> does not receive
    |
    +--> Client D: SUBSCRIBE payments.done   ------> does not receive
```

**A channel is not a Redis List, Stream, or Hash storing event history.** In regular Pub/Sub, a channel name is a real-time broadcast route. Redis does not create a durable queue simply because a client calls `SUBSCRIBE` or `PSUBSCRIBE`.

If a publisher sends when no matching subscriber is listening, the message is not saved for a subscriber that connects later to catch up.

### 2.1. Two perspectives to separate

| Concept | Which side owns it? | Example | Meaning |
|---|---|---|---|
| Channel | Specified by publisher when sending; subscriber can subscribe directly | `orders.created` | Route name that messages are published to |
| Exact subscription | Subscriber | `SUBSCRIBE orders.created` | Interested only in the channel name matching the exact string |
| Pattern subscription | Subscriber | `PSUBSCRIBE orders.*` | Interested in all channel names matching the glob pattern |
| Message payload | Sent by publisher, received by subscriber | `{"orderId":"o-101"}` | Event data |
| Matching pattern | Provided by Redis for pattern messages | `orders.*` | Which pattern matched the original channel |

The publisher does not need to know how many subscribers exist or whether they subscribe by exact name or by pattern. Those decisions belong to the receiving side.

## 3. Exact channel: SUBSCRIBE

Redis syntax:

```redis
SUBSCRIBE channel [channel ...]
```

Example:

```redis
SUBSCRIBE orders.created
```

This client receives messages published to that exact channel:

```redis
PUBLISH orders.created "new-order"
```

But it does not receive messages published to other names:

```redis
PUBLISH orders.cancelled "cancelled-order"
PUBLISH orders.created.v2 "new-order-v2"
PUBLISH payments.completed "payment-done"
```

Redis matches the channel name exactly. The dot (`.`) in `orders.created` is just a character in the name; Redis does not treat it as a parent/child namespace hierarchy.

### 3.1. Subscribing to multiple specific channels

A subscriber can listen to multiple names:

```redis
SUBSCRIBE orders.created orders.cancelled orders.paid
```

This is still an **exact subscription** for each channel. The listed names do not become a pattern.

When the channel list is known in advance and relatively stable, explicit subscriptions keep the received data scope clear. It is also easier to control when each event type has its own handler or processing policy.

### 3.2. `message` notifications

After `SUBSCRIBE orders.created`, a matching publication has the logical Pub/Sub response shape:

```text
1) "message"
2) "orders.created"
3) "{\"orderId\":\"o-101\"}"
```

Three key pieces of information:

1. Notification type: `message`.
2. Actual channel name: `orders.created`.
3. Published payload: string or byte data.

An exact-type notification carries no pattern field because it was not delivered via a pattern subscription.

## 4. Pattern subscription: PSUBSCRIBE

Syntax:

```redis
PSUBSCRIBE pattern [pattern ...]
```

Example:

```redis
PSUBSCRIBE orders.*
```

The subscriber receives publications on channels matching the pattern:

```text
orders.created
orders.cancelled
orders.paid
orders.created.v2
orders.
```

The pattern `orders.*` means a name starting with the string `orders.` followed by **zero or more arbitrary characters**.

This pattern does not automatically restrict itself to "exactly one level" of a namespace. If the application uses multiple dots in channel names, `orders.*` can still match across multiple levels.

### 4.1. Redis patterns use glob, not regex

Common symbols:

| Pattern | Rule | Matching examples | Non-matching examples |
|---|---|---|---|
| `orders.*` | Starts with `orders.` followed by 0 or more characters | `orders.created`, `orders.a.b` | `payments.created` |
| `orders.?` | Starts with `orders.` followed by exactly one character under glob matching | `orders.a` | `orders.created` |
| `orders.[ab]` | Final character is `a` or `b` | `orders.a`, `orders.b` | `orders.c` |
| `orders.[0-9]` | One character within the given range | `orders.7` | `orders.ready` |
| `*` | Every channel name | `orders.created`, `payments.paid` | No normal channel name is excluded by name |
| `audit.*` | Every channel with prefix `audit.` | `audit.login` | `orders.created` |

Redis globs are not full regular expressions:

- There is no regex syntax such as `^orders\\..+$` in the regex sense.
- The `.` character is an ordinary literal character; it does not mean "any character" as in many regex engines.
- `*` is a glob wildcard; writing `orders.*` does not mean "a dot and then repeat the dot".
- Channel name matching should be treated as an exact naming contract, and it is case-sensitive.
- When you need to match a wildcard character literally, use the corresponding glob escape mechanism and test against actual names; avoid constructing unnecessarily complex patterns.

Example:

```text
Pattern: orders.*

orders.created      -> match
orders.CANCELLED    -> match
orders.created.v2   -> match
orders.             -> match
order.created       -> no match
Orders.created      -> no match
```

### 4.2. Patterns automatically pick up new future channel names

Suppose today the system only uses:

```text
orders.created
orders.cancelled
```

A subscriber with `PSUBSCRIBE orders.*` does not need to re-subscribe when tomorrow the publisher begins publishing:

```text
orders.refunded
orders.shipped
```

As long as the new name matches the pattern and the subscriber remains connected, it will receive those new publications.

**A pattern subscription does not create channels and does not scan history.** It only widens the set of channel names selected when messages are published in the future.

### 4.3. `pmessage` notifications

With:

```redis
PSUBSCRIBE orders.*
```

when a publisher sends:

```redis
PUBLISH orders.created '{"orderId":"o-101"}'
```

the pattern subscriber receives the logical response:

```text
1) "pmessage"
2) "orders.*"
3) "orders.created"
4) "{\"orderId\":\"o-101\"}"
```

Four components:

1. Notification type: `pmessage`.
2. Matched pattern: `orders.*`.
3. **Actual** channel name: `orders.created`.
4. Payload.

If the handler needs to know whether this is a `created` or `cancelled` event, it must rely on the **actual channel**, never treating the pattern `orders.*` as the event name.

## 5. Direct comparison of the two subscription types

| Criterion | Exact channel | Pattern subscription |
|---|---|---|
| Redis command | `SUBSCRIBE` | `PSUBSCRIBE` |
| Unsubscribe | `UNSUBSCRIBE` | `PUNSUBSCRIBE` |
| Spring Data Redis Topic | `ChannelTopic` | `PatternTopic` |
| Match scope | Exact channel name | Channel names matching glob pattern |
| Pub/Sub notification type | `message` | `pmessage` |
| Pattern metadata | No pattern | Includes the matched pattern name |
| Pick up newly added channels? | Must subscribe to new name | Automatically received if new name matches |
| Filtering overhead | No glob pattern evaluation for this subscription | Redis must evaluate registered patterns |
| Risk of unintended reception | Low if the channel list is exact | Higher if the pattern is too broad |
| Suitable use cases | Dedicated business handlers for a few events | Logging, observability, namespace-based dispatchers |
| Storage/delivery guarantees | Ephemeral Pub/Sub | Also ephemeral Pub/Sub; no higher durability |

An important design difference: **broad patterns are convenient for extensibility**, but can expose a subscriber to message types it does not yet support. When defining a pattern, define at the same time how unknown channels and new payloads are handled.

## 6. Hands-on practice with three terminals

Start a local Redis or connect to a test Redis instance. You can run Redis via Docker:

```bash
docker run --rm --name redis-pubsub-demo -p 6379:6379 redis:7-alpine
```

In terminal A:

```bash
redis-cli
```

Then:

```redis
SUBSCRIBE orders.created
```

In terminal B:

```bash
redis-cli
```

Then:

```redis
PSUBSCRIBE orders.*
```

In terminal C:

```bash
redis-cli
```

Publish:

```redis
PUBLISH orders.created "event-1"
PUBLISH orders.cancelled "event-2"
PUBLISH orders.created.v2 "event-3"
PUBLISH payments.completed "event-4"
```

Expected:

| Publication | Terminal A (`SUBSCRIBE orders.created`) | Terminal B (`PSUBSCRIBE orders.*`) |
|---|---|---|
| `orders.created` / `event-1` | Receives `message` | Receives `pmessage` |
| `orders.cancelled` / `event-2` | Does not receive | Receives |
| `orders.created.v2` / `event-3` | Does not receive | Receives |
| `payments.completed` / `event-4` | Does not receive | Does not receive |

You must **subscribe before publishing**. If you run the publish commands before terminal A or B finishes subscribing, messages that have already passed will not be replayed.

When you want to unsubscribe:

```redis
UNSUBSCRIBE orders.created
PUNSUBSCRIBE orders.*
```

The two unsubscribe commands operate on **two different subscription types**. Unsubscribing from an exact subscription does not unsubscribe a pattern subscription covering the same name, and vice versa.

## 7. Why can one message be received twice?

Suppose **a single client** simultaneously registers:

```redis
SUBSCRIBE orders.created
PSUBSCRIBE orders.*
```

When there is:

```redis
PUBLISH orders.created "event-1"
```

Redis can send **two separate Pub/Sub notifications** to that client:

```text
message:
    channel = orders.created
    payload = event-1

pmessage:
    pattern = orders.*
    channel = orders.created
    payload = event-1
```

This is not Redis automatically retrying a failed message. It is the result of **two subscriptions matching the same publication**.

Similarly, a client subscribing to multiple overlapping patterns:

```redis
PSUBSCRIBE orders.* *.created
```

A publication on `orders.created` can match both patterns and be delivered as corresponding `pmessage` notifications.

### 7.1. Business consequences

If the subscriber performs a side effect:

```text
Receive order created
    -> send email
    -> award loyalty points
    -> update another system
```

having two overlapping subscriptions can execute the business action twice if the code does not distinguish or deduplicate them.

Ways to avoid this:

- For dedicated handlers, subscribe to only **one exact channel**.
- For aggregate handlers, use one intentional pattern and avoid multiple patterns with overlapping scope.
- Separate logging/metrics handlers from handlers that produce side effects.
- Include `eventId` in the payload and enforce idempotency for critical side effects.
- If the application intentionally registers both exact and pattern subscriptions, clearly designate one path for observation or metrics only.

**Idempotency is a separate business requirement.** A Pub/Sub message published once can still trigger multiple callbacks because multiple subscriptions or multiple application instances are listening.

### 7.2. Distinguishing duplicates by subscriber count

If three application instances all subscribe to `orders.created`, all three can receive the same publication. Redis Pub/Sub is **broadcast to matching subscribers**, not automatic work-splitting ("one event to only one worker") like a queue with consumer groups.

Combining multiple instances with multiple overlapping patterns can produce more executions than expected. If the goal is a group of workers sharing work with processing tracking, consider Redis Streams with consumer groups or an appropriate queue system.

## 8. Spring Data Redis: ChannelTopic and PatternTopic

Spring Data Redis maps the two subscription types into the `Topic` abstraction.

Common classes:

```java
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.Topic;
```

Create an exact topic:

```java
Topic exact = new ChannelTopic("orders.created");
```

Create a pattern topic:

```java
Topic wildcard = new PatternTopic("orders.*");
```

A `ChannelTopic` expresses the intent to subscribe to **an exact channel name**. A `PatternTopic` expresses the intent to subscribe to **a glob pattern**.

Both objects describe **receiving**, not a payload container or a pre-created Redis data structure. The publisher still invokes publish with a normal channel string.

### 8.1. RedisMessageListenerContainer

Instead of opening a connection manually, calling `SUBSCRIBE`, and managing thread-blocking lifecycles yourself, Spring Data Redis provides `RedisMessageListenerContainer`.

The container manages subscriptions, connections, and message delivery to `MessageListener` instances. In a standard Spring application, the container is registered as a bean; it begins receiving subscriptions according to Spring's lifecycle.

Example configuring two listeners:

```java
package com.example.pubsub;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.data.redis.connection.RedisConnectionFactory;
import org.springframework.data.redis.listener.ChannelTopic;
import org.springframework.data.redis.listener.PatternTopic;
import org.springframework.data.redis.listener.RedisMessageListenerContainer;

@Configuration
public class PubSubConfiguration {

    @Bean
    RedisMessageListenerContainer redisMessageListenerContainer(
            RedisConnectionFactory connectionFactory) {

        RedisMessageListenerContainer container =
            new RedisMessageListenerContainer();

        container.setConnectionFactory(connectionFactory);

        MessageListener exactListener = (message, matchedPattern) ->
            trace("EXACT", message, matchedPattern);

        MessageListener patternListener = (message, matchedPattern) ->
            trace("PATTERN", message, matchedPattern);

        container.addMessageListener(
            exactListener,
            new ChannelTopic("orders.created")
        );

        container.addMessageListener(
            patternListener,
            new PatternTopic("orders.*")
        );

        return container;
    }

    private static void trace(
            String source,
            Message message,
            byte[] matchedPattern) {

        String channel = new String(
            message.getChannel(),
            StandardCharsets.UTF_8
        );

        String payload = new String(
            message.getBody(),
            StandardCharsets.UTF_8
        );

        String pattern = matchedPattern == null
            ? "(direct)"
            : new String(matchedPattern, StandardCharsets.UTF_8);

        System.out.printf(
            "%s | pattern=%s | channel=%s | payload=%s%n",
            source, pattern, channel, payload
        );
    }
}
```

This example assumes channel names and payloads are sent as UTF-8 text. For binary payloads, custom JSON serializers, or JDK serialization, you cannot arbitrarily use `new String(bytes, UTF_8)` to reconstruct business objects.

Because two listeners are registered, when publishing to `orders.created`:

```text
EXACT   | pattern=(direct) | channel=orders.created | payload=...
PATTERN | pattern=orders.* | channel=orders.created | payload=...
```

When publishing to `orders.cancelled`, only the pattern listener in this configuration is invoked.

### 8.2. What does MessageListener receive?

Interface:

```java
public interface MessageListener {
    void onMessage(Message message, byte[] pattern);
}
```

In the callback:

- `message.getChannel()` holds the **actual channel name** as bytes.
- `message.getBody()` holds the payload as bytes.
- `pattern` holds the matched pattern for pattern subscriptions; for regular direct subscriptions it is `null`.

Shared handling code can distinguish them:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    boolean fromPatternSubscription = pattern != null;

    String actualChannel = new String(
        message.getChannel(),
        StandardCharsets.UTF_8
    );

    if (fromPatternSubscription) {
        String matchedPattern = new String(
            pattern,
            StandardCharsets.UTF_8
        );
        // Handle according to pattern and actual channel name.
    } else {
        // Handle direct subscription.
    }
}
```

For a handler registered with `PatternTopic("orders.*")`, **do not use `pattern` to infer which event occurred**. A single pattern can match many channels; `message.getChannel()` is what tells you which channel was actually published to.

### 8.3. Do not confuse method names or class names

| Redis CLI | Spring Data Redis |
|---|---|
| `SUBSCRIBE orders.created` | `new ChannelTopic("orders.created")` |
| `PSUBSCRIBE orders.*` | `new PatternTopic("orders.*")` |
| `PUBLISH orders.created payload` | `StringRedisTemplate.convertAndSend("orders.created", payload)` |
| Cancel exact subscription | Remove `ChannelTopic` listener or manage subscription lifecycle |
| Cancel pattern subscription | Remove `PatternTopic` listener or manage subscription lifecycle |

Listener management methods on the container should be called properly according to Spring's API and lifecycle. Dynamic registration/removal should guard against duplicate registrations and accidentally removing shared listeners.

## 9. Spring Data Redis publishers still publish to specific channels

A publisher:

```java
package com.example.pubsub;

import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.stereotype.Service;

@Service
public class OrderEventPublisher {

    private final StringRedisTemplate redis;

    public OrderEventPublisher(StringRedisTemplate redis) {
        this.redis = redis;
    }

    public long publishCreated(String json) {
        Long subscribers = redis.convertAndSend(
            "orders.created",
            json
        );
        return subscribers == null ? 0L : subscribers;
    }

    public long publishCancelled(String json) {
        Long subscribers = redis.convertAndSend(
            "orders.cancelled",
            json
        );
        return subscribers == null ? 0L : subscribers;
    }
}
```

Corresponding Redis configuration in a Spring Boot application:

```yaml
spring:
  data:
    redis:
      host: localhost
      port: 6379
```

Example payload:

```json
{
  "eventId": "evt-1001",
  "orderId": "o-101",
  "occurredAt": "2026-11-13T02:00:00Z"
}
```

`StringRedisTemplate` serializes `String` values in a way suited for text. If a producer uses `RedisTemplate<String, Object>` with a different serializer, the receiver must know the corresponding payload format to read the data.

**A publisher does not publish to `orders.*`.** If you call `PUBLISH orders.* payload`, Redis treats `orders.*` as a **literal channel name**. It does not automatically fan out to `orders.created` and `orders.cancelled`. Patterns apply on the subscription side.

### 9.1. The return value of PUBLISH is not a business ACK

The return value of `PUBLISH`/`convertAndSend` relates to the number of subscribers that received the publication at the Redis level according to command semantics and deployment configuration. It **does not prove**:

- The handler processed the payload successfully.
- Data was written to the subscriber's database.
- An email was sent.
- A process did not fail after receiving the message.
- The message was saved for replay.

In Redis Cluster, the count returned by `PUBLISH` also has node-level scoping limits. Therefore, do not use the returned count as an end-to-end business receipt or proof of guaranteed delivery.

If the application needs ACKs, retries, dead-lettering, or event history, regular Redis Pub/Sub is not enough.

## 10. Routing events inside a pattern listener

When a listener subscribes to `orders.*`, it receives multiple event types. It must therefore branch explicitly by **actual channel**.

Example:

```java
package com.example.pubsub;

import java.nio.charset.StandardCharsets;

import org.springframework.data.redis.connection.Message;
import org.springframework.data.redis.connection.MessageListener;
import org.springframework.stereotype.Component;

@Component
public class OrderPatternListener implements MessageListener {

    @Override
    public void onMessage(Message message, byte[] pattern) {
        String channel = new String(
            message.getChannel(),
            StandardCharsets.UTF_8
        );

        String body = new String(
            message.getBody(),
            StandardCharsets.UTF_8
        );

        switch (channel) {
            case "orders.created":
                handleCreated(body);
                break;
            case "orders.cancelled":
                handleCancelled(body);
                break;
            case "orders.paid":
                handlePaid(body);
                break;
            default:
                handleUnknownChannel(channel, body);
        }
    }

    private void handleCreated(String json) {
        // Parse JSON and apply the corresponding business logic.
    }

    private void handleCancelled(String json) {
        // Parse JSON and apply the corresponding business logic.
    }

    private void handlePaid(String json) {
        // Parse JSON and apply the corresponding business logic.
    }

    private void handleUnknownChannel(String channel, String json) {
        // Log/record metrics per policy; avoid unintended side effects.
    }
}
```

If using this bean instead of the lambdas in the configuration section:

```java
@Bean
RedisMessageListenerContainer orderListenerContainer(
        RedisConnectionFactory factory,
        OrderPatternListener listener) {

    RedisMessageListenerContainer container =
        new RedisMessageListenerContainer();

    container.setConnectionFactory(factory);
    container.addMessageListener(
        listener,
        new PatternTopic("orders.*")
    );

    return container;
}
```

This is an **alternative configuration**—do not register it alongside the demo container in section 8 unless you want additional subscriptions. In a real project, pick one clean bean organization to avoid duplicate listener registrations.

### 10.1. Avoid processing data of unknown type

Each channel may use a different schema. For instance, `orders.created` contains `newOrder`, while `orders.cancelled` contains `reason`. A pattern listener must classify the channel **before** deserializing into a specialized DTO.

If you parse every payload into a single class just because they all match `orders.*`, new events can fail or be misprocessed.

One way to scale this is to standardize an envelope:

```json
{
  "eventId": "evt-1001",
  "type": "OrderCreated",
  "schemaVersion": 1,
  "payload": {
    "orderId": "o-101"
  }
}
```

Then both the channel name and the `type` field can participate in contract validation, though you must clearly specify which field is the primary routing source and how to handle mismatches between the two.

### 10.2. Handling unforeseen events

Because a pattern can match new channels in the future, an aggregate handler needs a policy:

- Ignore unsupported channels and record a metric.
- Forward the event to an extension handler if one exists.
- Alert when an event/schema violates the contract.
- Never run a default side effect solely because a prefix matched the pattern.

Patterns save subscribers from having to re-subscribe often, but they **do not automatically guarantee payload compatibility**.

## 11. Notes on channel and payload serialization

`MessageListener` receives bytes. Channel names and payloads can be serialized differently:

```text
Java Publisher:
    convertAndSend(channel, object)
       |
       +-- channel serializer -> channel name bytes
       +-- value serializer   -> payload bytes

Redis Pub/Sub:
    channel bytes + payload bytes

Listener:
    message.getChannel() -> byte[]
    message.getBody()    -> byte[]
```

If the publisher uses `StringRedisTemplate`, String channels and payloads are human-readable. However, if using `RedisTemplate` with a binary object serializer, the body is not necessarily JSON or UTF-8.

### 11.1. Common mistake: subscriber listens for a String channel while publisher encodes keys differently

For example, the subscriber has:

```java
new ChannelTopic("orders.created")
```

Meanwhile, the publisher uses a template whose channel encoding differs from the expected String. Even though Java sees the same string `"orders.created"`, the **actual channel bytes** may not match, leaving the listener receiving nothing.

Standardize the channel name serializer—commonly `StringRedisSerializer` or `StringRedisTemplate`. Body data may use a dedicated JSON codec, provided the format is shared between producer and consumer.

### 11.2. JSON does not automatically become a DTO in MessageListener

Code:

```java
String json = new String(
    message.getBody(),
    StandardCharsets.UTF_8
);
```

only produces a Java `String`. If you need a DTO, use `ObjectMapper` or an appropriate codec:

```java
OrderCreatedEvent event = objectMapper.readValue(
    message.getBody(),
    OrderCreatedEvent.class
);
```

Here `OrderCreatedEvent` is an application-defined DTO, and the publisher must send JSON matching the schema. When designing a listener, handle parse exceptions at the right layer so one malformed payload does not repeatedly disrupt the entire event-receiving pipeline.

## 12. Performance cost: pattern matching is not free

With exact subscriptions, Redis can look up subscribers directly by channel name. With pattern subscriptions, Redis must check registered patterns to determine which patterns match the channel name.

The publish cost model is commonly expressed as:

```text
PUBLISH complexity: O(N + M)

N = number of clients subscribed directly to the receiving channel
M = total number of registered pattern subscriptions
```

This formula expresses delivering to direct subscribers and evaluating patterns. Actual cost also depends on payload size, client count, slow connections, buffers, and traffic volume.

Example:

```text
10 specific channels with many subscribers
  -> Redis looks up by channel on each publication.

5,000 registered patterns
  -> Each publish may have to evaluate many patterns.
```

Do not assume wildcards are always slow or exact subscriptions are always better in every situation. A single pattern can be more sensible than dynamically maintaining hundreds of channel names in the application. However, **a large number of very broad patterns** can increase per-publication overhead and send many unnecessary messages to subscribers.

### 12.1. Broad patterns create heavy processing load on the consumer

If an application subscribes:

```redis
PSUBSCRIBE *
```

it can receive nearly every publication in regular Redis Pub/Sub that it has permission to access. A slow logger or listener can become a bottleneck, consuming memory buffers and CPU.

Prefer narrower patterns:

```text
orders.*
orders.audit.*
tenant:{t-7}:orders.*
```

Remember: these are merely **naming conventions** and glob matching. Redis does not understand tenants, orders, or colons in a business sense.

### 12.2. Patterns are not a multi-attribute routing system

Patterns primarily match **channel names**. They do not support arbitrary queries over JSON fields inside the payload:

```json
{
  "tenant": "t-7",
  "priority": 10,
  "region": "south"
}
```

`PSUBSCRIBE orders.*` cannot automatically filter `priority > 5` or `region == "south"` from the JSON. If you need such filtering, encode the attribute in the channel name, filter in the application, or use a suitable messaging/querying system.

Strike a balance: encoding too many attributes into channel names can make the namespace complex and easily lead to overlapping patterns.

## 13. Observing subscribers with PUBSUB commands

Redis provides several diagnostic commands:

```redis
PUBSUB CHANNELS
PUBSUB CHANNELS orders.*
PUBSUB NUMSUB orders.created orders.cancelled
PUBSUB NUMPAT
```

Meanings:

| Command | What is it for? | Notes |
|---|---|---|
| `PUBSUB CHANNELS` | Lists channels currently having direct subscribers | Does not list every channel ever published to |
| `PUBSUB CHANNELS orders.*` | Filters the list of channels with direct subscriptions using the supplied pattern | Does not mean it lists pattern subscriptions themselves |
| `PUBSUB NUMSUB orders.created` | Counts direct subscribers for a channel name | Does not count all pattern subscribers that would match |
| `PUBSUB NUMPAT` | Counts active pattern subscriptions per Redis semantics | Not the number of events or channels |

A common misunderstanding is:

```redis
PUBSUB NUMSUB orders.created
```

returning `0` even though a `PSUBSCRIBE orders.*` listener exists. That is completely normal because this command focuses on **direct subscriptions**. Do not conclude nobody will receive a publication solely based on `NUMSUB = 0`.

In Redis Cluster, subscription inspection results can be local or follow per-command, per-node scoping rules. When investigating distributed systems, know which node you queried and which Pub/Sub mode is in use.

### 13.1. PUBLISH response is a limited measurement

```redis
PUBLISH orders.created "hello"
```

The command returns a count related to clients receiving the publication at the broker level. This number **is not a processing completion ACK**. A handler might receive and then fail, restart, or not yet persist data elsewhere.

In Cluster, the count scope may only reflect clients connected to the node where the publish occurred per Redis Cluster semantics. Therefore, do not rely on this number to confirm all application instances received and succeeded.

## 14. Connection lifecycle and listener container

`SUBSCRIBE`/`PSUBSCRIBE` switches a connection into message-receiving subscription mode. With RESP2, running other commands on a subscribed connection is restricted; RESP3 differs, but typical applications should still let the listener container manage Pub/Sub connections.

Do not:

1. Borrow a regular connection from a pool used for data commands.
2. Call `SUBSCRIBE` in an indefinitely blocking manner on a request thread.
3. Continue assuming that connection can be used just like a normal connection.
4. Forget to unsubscribe or fail to manage reconnects.

`RedisMessageListenerContainer` provides lifecycle management, multi-listener registration, and callback dispatching tailored for Spring. It is designed to share subscription connections and serve listeners at the container level; exact threading behavior depends on the executors and configuration.

### 14.1. Do not let handlers block for too long

If a callback performs heavy work:

```java
@Override
public void onMessage(Message message, byte[] pattern) {
    // External API calls taking seconds, infinite retries, or reading a huge file...
}
```

it can slow message processing, block the executor, and grow pending payloads. Under high load, you should:

- Keep callbacks short.
- Decode and validate just enough to route.
- Offload heavy work to a bounded, managed executor/queue.
- Set I/O timeouts and avoid infinite retries inside callbacks.
- Record metrics for received messages, processing errors, and handler duration.

However, offloading to a separate in-memory queue still does not make Pub/Sub durable. If the process dies, unprocessed messages in memory can still be lost.

### 14.2. Dynamic registration

In some applications, the channels to listen to depend on runtime configuration or state. The container supports topic-based listener management, allowing controlled additions and removals of registrations.

Keep in mind:

- Avoid registering the same listener/topic multiple times unintentionally.
- Track which channels/patterns are attached to which handlers.
- If widening a pattern, review the scope of events that may arrive.
- When removing an exact listener, check whether any pattern listener still receives that channel.
- When the container reconnects, ensure lifecycle and registration state are restored properly according to the library's mechanism.

Before trying to optimize connection counts, prioritize clarity of subscription scope and error handling.

## 15. Reliability: neither direct nor pattern has durable storage

Regular Redis Pub/Sub has **at-most-once** delivery semantics per Pub/Sub delivery: once a message is sent to a subscriber, the broker does not keep a durable record for the subscriber to ACK and request redelivery on failure.

Situations where messages are easily lost:

```text
Publisher publishes before the subscriber finishes subscribing.
Subscriber loses connection at publish time.
Application stops while the handler has not yet processed the message.
Client is overloaded or the connection is closed.
Redis or the network experiences an outage.
```

Both `SUBSCRIBE` and `PSUBSCRIBE` share these limitations. A pattern subscription **is not a queue with wildcards**, nor does it turn messages into replayable records.

### 15.1. Do not confuse Pub/Sub with Redis Streams

If you need to:

- Re-read messages when a consumer starts up later.
- Track IDs/offsets.
- ACK after processing.
- Distribute work across a consumer group.
- Handle pending entries, retries, or recovery after disconnects.

then Redis Streams (`XADD`, `XREAD`, `XREADGROUP`, `XACK`) or another message broker is generally more suitable. Redis Streams has a different storage, retention, and consumption model than Pub/Sub.

A system can still use Pub/Sub for real-time signals (cache invalidation, state change notifications) and Streams/queues for work requiring high reliability.

### 15.2. Duplicate reception does not contradict at-most-once

Redis does not retry Pub/Sub like an ACK-based queue, yet an application can **create duplicate deliveries at the business level**:

- One client registers overlapping exact and pattern subscriptions.
- Two patterns match the same publication.
- Multiple instances subscribe to the same channel.
- The publisher sends two events with identical payloads.

Therefore, for critical side effects, identify `eventId`, prevent duplicate execution, and verify whether Pub/Sub satisfies acceptable message-loss tolerances.

## 16. Redis Cluster: do not confuse classic Pub/Sub with sharded Pub/Sub

Redis Cluster has multiple shards. For **classic Pub/Sub** (`PUBLISH`, `SUBSCRIBE`, `PSUBSCRIBE`), Redis Cluster propagates publications so subscribers can receive them across the cluster even when connected to different nodes. This can increase inter-node communication under high event volume.

Redis 7 introduced **sharded Pub/Sub** with a different command group:

```text
SPUBLISH
SSUBSCRIBE
SUNSUBSCRIBE
```

Sharded Pub/Sub binds channels to hash slots/shards to limit propagation scope. This is a different model from classic Pub/Sub.

| Aspect | Classic Pub/Sub | Sharded Pub/Sub |
|---|---|---|
| Publish | `PUBLISH` | `SPUBLISH` |
| Exact subscribe | `SUBSCRIBE` | `SSUBSCRIBE` |
| Pattern subscribe | `PSUBSCRIBE` | No equivalent `SPSUBSCRIBE` command in the basic group |
| Propagation scope in Cluster | Classic Pub/Sub propagation across the cluster | Primarily scoped to the channel's shard |
| Routing via Spring Data Redis | `ChannelTopic`/`PatternTopic` under regular Pub/Sub APIs | Verify specific sharded Pub/Sub API and driver support |
| Durability | No backlog retained | Also not a Redis Stream with ACK/replay |

A `PatternTopic("orders.*")` on `RedisMessageListenerContainer` serves the regular Pub/Sub pattern mechanism. Do not assume it automatically subscribes to all matching sharded Pub/Sub channels.

If the requirement is "wildcard subscribe across multiple shards in sharded Pub/Sub", you must design channel registration separately or choose a system compatible with that goal; you cannot assume `SPSUBSCRIBE` exists just because `PSUBSCRIBE` exists in classic mode.

### 16.1. Overhead in Cluster

With classic Pub/Sub, heavy publications and broad patterns can increase message-forwarding traffic and CPU load across the cluster. With sharded Pub/Sub, hash slot and shard placement determine where data is distributed; in exchange, wildcard pattern capabilities are not the same as classic Pub/Sub.

Thus, choosing `ChannelTopic` vs. `PatternTopic` usually falls under the **classic Pub/Sub API**, while choosing classic vs. sharded Pub/Sub is a separate architectural decision.

## 17. Security and namespace isolation

A pattern like:

```redis
PSUBSCRIBE *
```

can receive many message types beyond the intended business scope, depending on ACLs and Redis configuration. Do not use a very broad pattern in a service handling sensitive data without a clear need.

Example channel naming per tenant:

```text
tenant.t-7.orders.created
tenant.t-7.orders.cancelled
tenant.t-8.orders.created
```

A listener for tenant `t-7` might choose:

```redis
PSUBSCRIBE tenant.t-7.orders.*
```

However, **patterns in channel names do not create a security boundary by themselves**. If a client has broad Pub/Sub permissions, it can still request other subscriptions directly. Configure Redis ACL channel permissions and isolate connections, permissions, or infrastructure according to the application's security requirements.

Do not let external clients send arbitrary patterns to your application to open broad subscriptions without authorization and resource controls.

### 17.1. Intentional channel naming

A simple convention:

```text
<domain>.<entity>.<event>
orders.order.created
orders.order.cancelled
billing.invoice.paid
```

Then:

```text
orders.order.created  -> one exact event
orders.order.*        -> all order events
orders.*              -> every name starting with "orders."
```

The more stable the names, the easier it is to control pattern breadth. If changing naming conventions, plan migrations for publishers and subscribers; renaming a channel can stop older subscribers from receiving messages.

## 18. When to use exact channels and when to use patterns?

### 18.1. Prefer ChannelTopic when

- The handler receives only one specific business event.
- The payload has a dedicated schema.
- Side effects are permitted only for a single event type.
- You want to minimize the risk of receiving unintended messages.
- The channel list is small and known.
- Strict per-channel permission control is required.

Example:

```java
container.addMessageListener(
    paymentSuccessListener,
    new ChannelTopic("payments.completed")
);
```

### 18.2. Prefer PatternTopic when

- Multiple channels under the same namespace need observation.
- Channel names can arise dynamically by ID/tenant/source while following a clear convention.
- An aggregate listener needs to accept new events as long as names match.
- Lightweight logging/metrics/auditing is needed for an event group.
- Dispatching by actual channel and handling unknown events are already in place.

Example:

```java
container.addMessageListener(
    orderAuditListener,
    new PatternTopic("orders.*")
);
```

### 18.3. Selection table

| Need | Option | Why |
|---|---|---|
| Handle only `orders.created` | `ChannelTopic("orders.created")` | Explicit event name, minimal out-of-scope traffic |
| Log all `orders.*` | `PatternTopic("orders.*")` | Single registration captures multiple channels |
| Receive only `orders.created` and `orders.cancelled` | Two `ChannelTopic`s | Explicit, prevents new events from accidentally entering the handler |
| Pick up new channel `orders.shipped` without changing subscription config | `PatternTopic("orders.*")` | Pattern matches the new channel name automatically |
| Require exactly-once execution by one worker | Pub/Sub is insufficient | Requires queue/Streams and idempotency |
| Require replay after disconnect | Pub/Sub is insufficient | Use retained message storage |
| Want pattern subscription for sharded Pub/Sub | Different design needed | `PSUBSCRIBE` belongs to classic Pub/Sub |
| Need filtering by JSON fields | Handler/filter or another system | Patterns only match channel names |

The most effective choice is usually **exact for business handlers with side effects**, and **pattern for observers or dispatchers capable of handling schemas and unknown channels**.

## 19. Common errors and troubleshooting steps

### 19.1. "PUBLISH succeeded but the Spring listener did not receive it"

Check in order:

1. Had the container started and finished subscribing before publishing?
2. Does the Java channel name actually match the exact channel or pattern?
3. Was `ChannelTopic` accidentally used instead of `PatternTopic`?
4. Are publisher and subscriber connected to the same target Redis/Cluster?
5. Do the channel serializers produce identical bytes?
6. Do Redis ACLs allow subscribing/publishing on that channel?
7. Did the Pub/Sub connection drop, and has the container reconnected?
8. Is the callback failing to parse the payload or blocked in the executor?

Do not rush to conclude Redis failed to deliver before verifying lifecycle and channel formatting.

### 19.2. "PSUBSCRIBE orders.* does not receive only orders.created"

This is expected behavior: wildcard `*` matches any extension after `orders.`. If you need a single event, use `SUBSCRIBE orders.created`. If you need a finite set, use multiple explicit `ChannelTopic` instances.

### 19.3. "One publish ran the handler twice"

Look for overlapping exact and pattern subscriptions, overlapping patterns, listener beans registered twice, or multiple application instances subscribing. Inspect `message`/`pmessage`, matched pattern, and actual channel before assuming Redis retried.

### 19.4. "PUBSUB NUMSUB returns 0 yet someone still received it"

`PUBSUB NUMSUB` primarily counts direct subscribers on the channel. Pattern listeners can receive the message without being counted as direct subscribers of that channel name.

### 19.5. "Subscriber receives channels the application does not handle yet"

Patterns widen subscription scope. Dispatch by `message.getChannel()`, handle unknown events explicitly, and do not assume a single DTO applies to every channel.

### 19.6. "Message arrives but decodes into garbled characters"

The publisher may be using JDK/JSON/binary serialization while the listener assumes UTF-8 text. Separate channel bytes from payload bytes, standardize formats, or use compatible serializers.

### 19.7. "Messages lost after restart"

Pub/Sub does not store a backlog and does not replay. Use Redis Streams or a message broker with retention and ACKs if business requirements demand it.

### 19.8. "Multiple instances all process one task"

Pub/Sub broadcasts to matching subscribers rather than splitting tasks. Use a consumer group/queue when one message should be processed by a single group member.

### 19.9. "Pattern listener becomes overloaded as the system adds event types"

The pattern is matching more new channels, giving the decode/dispatch handler more work. Measure message rate, handler errors, and processing latency; review pattern breadth and executor sizing.

### 19.10. "Channels share a prefix yet the pattern does not match"

Check dots, separators, letter casing, the exact name published, wildcards, and byte serializers. `orders.*` does not match `order.created`; `Orders.created` is also not the same as `orders.created`.

## 20. Guided exercises

### Exercise 1 — Observing message and pmessage

Open three terminals as in section 6. In terminal A run `SUBSCRIBE orders.created`, in terminal B run `PSUBSCRIBE orders.*`, and in terminal C publish four events. Note the reply type, actual channel, and matched pattern.

Answer: Why does terminal B have an extra `orders.*` field in the message while terminal A does not?

### Exercise 2 — Distinguishing glob from regex

Predict whether `orders.*` receives the following channels:

```text
orders.
orders.created
orders.created.v2
order.created
orders.paid
Orders.paid
```

Then test via Redis CLI to verify. Explain why glob `*` is not equivalent to one namespace level.

### Exercise 3 — Using ChannelTopic and PatternTopic

Using `RedisMessageListenerContainer`:

```java
container.addMessageListener(
    createdListener,
    new ChannelTopic("orders.created")
);

container.addMessageListener(
    auditListener,
    new PatternTopic("orders.*")
);
```

Publish `orders.created`, `orders.cancelled`, and `payments.completed`. Observe which listener is invoked. Inside the audit listener, print `message.getChannel()` and `pattern`.

### Exercise 4 — Overlapping subscriptions

Have the same client subscribe to exact `orders.created` and pattern `orders.*`, or to two patterns `orders.*` and `*.created`. Publish one `orders.created` event. Record the number of Pub/Sub responses and explain why one publication can trigger multiple logical callbacks.

If the listener creates side effects, propose a way to avoid duplicate processing.

### Exercise 5 — New channel

A subscriber is running with:

```redis
PSUBSCRIBE orders.*
```

Start publishing additionally:

```redis
PUBLISH orders.shipped "shipped"
```

Observe whether it receives immediately or needs to re-subscribe. Explain why this behavior does not equate to message replay.

### Exercise 6 — Diagnostics with PUBSUB

Run:

```redis
PUBSUB CHANNELS
PUBSUB NUMSUB orders.created
PUBSUB NUMPAT
```

Test when only an exact subscriber exists, only a pattern subscriber exists, and both exist. Distinguish direct subscriber counts from pattern subscription counts. Do not treat these counts as the number of successfully processed events.

### Exercise 7 — Mismatched serialization

Use `StringRedisTemplate` to publish JSON text and a `MessageListener` decoding UTF-8. Then try having a publisher use a different binary serializer in a test environment. Explain why a callback cannot assume every payload is a JSON String.

### Exercise 8 — Choosing Pub/Sub or Streams

Given three scenarios:

1. Updating real-time status for online dashboards.
2. Sending mandatory emails even if the processing service restarts.
3. Lightweight logging of all `orders.*` events while the system is running.

Recommend `ChannelTopic`, `PatternTopic`, or a messaging system with retention/ACK. Explain the difference between **channel reception scope** and **message delivery guarantees**.

## 21. Key takeaways

- **`SUBSCRIBE`/`ChannelTopic` receives one exact channel name**. Multiple channels can be subscribed to, but each name is still matched individually.
- **`PSUBSCRIBE`/`PatternTopic` receives any channel name matching a glob** such as `orders.*`, including channels used for the first time after the subscriber has subscribed.
- Publishers always use the **actual channel name** with `PUBLISH`; publishing to `orders.*` does not broadcast to every `orders.*` channel.
- Direct subscriptions receive type `message`; pattern subscriptions receive type `pmessage` and carry the **matched pattern** alongside the actual channel.
- **One publication can produce multiple notifications** when direct/pattern or multiple patterns overlap. Multiple subscribed instances can also all receive it.
- In `MessageListener.onMessage`, `message.getChannel()` is the actual channel, `message.getBody()` is the payload as bytes, and the `pattern` parameter indicates the matched pattern or `null` for direct subscriptions.
- Patterns are **globs, not regex or JSON filters**. Broad patterns increase reception scope and pattern evaluation cost.
- Regular Redis Pub/Sub **does not store history, does not replay, and has no processing ACK**. Exact and pattern subscriptions share the same reliability limits.
- `PUBSUB NUMSUB` does not fully count pattern listeners; `PUBLISH` responses are not business acknowledgments.
- **Classic Pub/Sub with `PSUBSCRIBE` differs from sharded Pub/Sub** on Redis Cluster; there is no direct sharded wildcard equivalent in the basic command set.
- Choose `ChannelTopic` for specific business handlers; choose `PatternTopic` for observers or namespace dispatchers that handle unknown events.

### Official references

- [Redis — Pub/Sub](https://redis.io/docs/latest/develop/pubsub/)
- [Redis — SUBSCRIBE](https://redis.io/docs/latest/commands/subscribe/)
- [Redis — PSUBSCRIBE](https://redis.io/docs/latest/commands/psubscribe/)
- [Redis — PUBLISH](https://redis.io/docs/latest/commands/publish/)
- [Redis — PUBSUB](https://redis.io/docs/latest/commands/pubsub/)
- [Redis — PUBSUB NUMSUB](https://redis.io/docs/latest/commands/pubsub-numsub/)
- [Redis — PUBSUB NUMPAT](https://redis.io/docs/latest/commands/pubsub-numpat/)
- [Redis — Redis Cluster specification](https://redis.io/docs/latest/operate/oss_and_stack/reference/cluster-spec/)
- [Spring Data Redis — Pub/Sub Messaging](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html)
- [Spring Data Redis — RedisMessageListenerContainer](https://docs.spring.io/spring-data/redis/reference/redis/pubsub.html#redis:pubsub:messaging)
