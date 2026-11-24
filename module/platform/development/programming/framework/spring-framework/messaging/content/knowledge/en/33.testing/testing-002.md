# Testing MessageHandler and Interceptor Blocking Conditions

## Objectives

In Spring Messaging, a MessageHandler receives and processes a Message, while a MessageChannel is responsible for delivering the message to registered handlers. A ChannelInterceptor sits on the send or receive path of a channel to observe, transform, or block a message before it proceeds. When using an executor-backed channel, an ExecutorChannelInterceptor can also intervene separately in each individual subscriber invocation.

Properly testing these layers helps answer key questions:

- Does the handler receive the right payload and headers?
- Does an allow condition forward the message to the handler?
- Does a deny condition block the entire channel or only a single handler?
- What does send() returning true or false mean in each scenario?
- When are postSend, afterSendCompletion, and afterMessageHandled callbacks invoked?
- When a handler throws an exception, where is the error observed?

This lesson uses Spring Framework 6.1 APIs, Java 17+, and JUnit Jupiter. Examples focus on Spring Messaging core; testing STOMP, RSocket, or Spring Integration adapters requires additional test layers suited to each adapter.

## 1. Components to Test

### 1.1. Message and MessageBuilder

A Message is the unit of data passed through the messaging system. A Message consists of a payload and headers. The payload holds the main content; headers hold metadata such as content type, correlation id, tenant context, or destination.

Use MessageBuilder to construct messages in tests:

~~~java
Message<String> message = MessageBuilder.withPayload("order-42")
        .setHeader("tenantId", "acme")
        .setHeader("eventType", "ORDER_CREATED")
        .build();
~~~

MessageBuilder creates a GenericMessage and provides an API to set, copy, or remove headers. This lets tests strictly control inputs without starting a broker or transport.

Avoid bringing too many transport details into pure handler tests. If the goal is to verify payload and header handling logic, construct a Message directly. Only use WebSocket, STOMP, or RSocket when you also need to verify protocol, codecs, routing, and connection configuration.

### 1.2. MessageHandler

MessageHandler is a functional interface with a single method:

~~~java
void handleMessage(Message<?> message);
~~~

A handler receives a Message and processes it. The method does not return a business value; if a response needs to be sent, the handler or adapter must do so through the system's reply mechanism.

You can create a MessageHandler using a lambda:

~~~java
MessageHandler handler = message -> {
    String orderId = (String) message.getPayload();
    String tenantId = (String) message.getHeaders().get("tenantId");

    // Process message or call service.
};
~~~

In unit tests, verify that the handler receives the expected payload/headers, invokes the right dependencies, produces the right side effects, or throws the expected exception type. There is no need to set up a channel if the test only targets logic inside the handler.

### 1.3. MessageChannel and SubscribableChannel

MessageChannel defines the send operation. The boolean return value of send() indicates whether the channel accepted the message for sending. Certain unrecoverable failures may be represented by a RuntimeException.

SubscribableChannel allows registering one or more MessageHandlers. When a message is sent, the channel delivers the message to subscribers according to its specific implementation.

**ExecutorSubscribableChannel** is an implementation in Spring Messaging. It sends messages to each subscriber; it can run synchronously on the calling send() thread or use a provided Executor. The no-Executor constructor executes handlers on the caller's thread, which is very useful for synchronous, predictable tests.

### 1.4. ChannelInterceptor

ChannelInterceptor is a strategy for intercepting send/receive operations on a MessageChannel. The main callbacks are:

| Callback | Timing | Can block? |
|---|---|---|
| preSend | Before the channel performs send | Yes; return null to stop send |
| postSend | Immediately after send is invoked | No; only observes the sent result |
| afterSendCompletion | After send finishes, even if an exception occurs | No; used for cleanup/metrics |
| preReceive | Before the channel retrieves a message | Yes; return false to stop receive |
| postReceive | After retrieving a message, before returning to caller | Can return null to cancel further interceptor processing |
| afterReceiveCompletion | After receive finishes, even if an exception occurs | No; used for cleanup |

Receive callbacks apply only to PollableChannel. SubscribableChannel does not provide receive(), because messages are pushed directly to subscribers.

## 2. Blocking Conditions in preSend

### 2.1. Returning null to Block the Entire Channel

preSend is called before the message is actually sent into the channel. An interceptor can return:

- The original message to allow it to proceed.
- A new message to modify the payload or headers before sending.
- null to prevent the send invocation from taking place.

Example allowing only messages belonging to an accepted tenant:

~~~java
public class TenantGuardInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        Object tenantId = message.getHeaders().get("tenantId");

        if (!"acme".equals(tenantId)) {
            return null;
        }

        return message;
    }
}
~~~

When preSend returns null, AbstractMessageChannel does not invoke sendInternal. The call to channel.send(message) returns false. Handlers do not receive that message.

This is a channel-level message filtering decision. Sending across the entire channel is halted; no subscriber receives that message.

### 2.2. Distinguishing Returning null from Throwing an Exception

These two approaches have different meanings:

| preSend Behavior | Meaning |
|---|---|
| Return the message | Allow sending to proceed |
| Return a new message | Allow sending to proceed with transformed content |
| Return null | Reject sending due to filter condition; send() returns false |
| Throw RuntimeException | Send failed due to error; AbstractMessageChannel may wrap the error in MessageDeliveryException |
| Throw MessagingException | Messaging error propagated via Spring's exception mechanism |

Use null when it is an intentional blocking condition and the caller can handle a false result. Use an exception when there is an error that must be reported clearly, such as when the interceptor cannot access a required dependency or detects a misconfigured state.

If the client needs to receive an error response such as UNAUTHORIZED or INVALID_MESSAGE, returning null only stops sending at the channel and may not generate a response for the client. Design responses at the appropriate protocol/controller layer rather than expecting an interceptor to produce a response by itself.

### 2.3. Callback Lifecycle When Blocked

For an interceptor that returns null from preSend:

- sendInternal is not called.
- postSend is not called for that send attempt.
- afterSendCompletion of the interceptor that returned null itself is not called, because this callback only applies when preSend returned a Message.
- If earlier interceptors returned a message successfully, they can still receive afterSendCompletion with sent=false for cleanup.

When send actually takes place, postSend receives the sent value returned by the channel. afterSendCompletion is invoked after send completes to release resources or record the outcome. Do not use afterSendCompletion to change the send decision; by then, the send has already completed.

## 3. Blocking Conditions for Individual MessageHandlers

### 3.1. ExecutorChannelInterceptor.beforeHandle

ExecutorChannelInterceptor extends ChannelInterceptor with two callbacks:

- beforeHandle runs right before a specific MessageHandler is invoked.
- afterMessageHandled runs after the handler finishes, even if the handler throws an exception.

With ExecutorSubscribableChannel, these callbacks execute inside the task submitted to the Executor. An interceptor can return null from beforeHandle to skip only the subscriber currently being processed.

Example:

~~~java
public class SubscriberGuardInterceptor
        implements ExecutorChannelInterceptor {

    @Override
    public Message<?> beforeHandle(
            Message<?> message,
            MessageChannel channel,
            MessageHandler handler) {

        if (shouldSkip(message, handler)) {
            return null;
        }

        return message;
    }

    private boolean shouldSkip(
            Message<?> message,
            MessageHandler handler) {
        // Subscriber-specific filter condition.
        return false;
    }
}
~~~

Key distinction:

- ChannelInterceptor.preSend blocks the message before the channel dispatches it. No subscriber receives the message.
- ExecutorChannelInterceptor.beforeHandle blocks right before a specific handler. Other subscribers can still process the same message.

Therefore, with ExecutorSubscribableChannel, send() can return true even if one subscriber was skipped by beforeHandle. A true result says that the channel accepted and dispatched the message according to its mechanism; it does not prove that every handler ran or that business processing succeeded.

### 3.2. When to Use Each Callback?

| Need | Appropriate Callback |
|---|---|
| Block all messages failing a condition before entering the channel | ChannelInterceptor.preSend |
| Normalize shared headers for all subscribers | ChannelInterceptor.preSend |
| Skip only one handler among multiple subscribers | ExecutorChannelInterceptor.beforeHandle |
| Record whether send succeeded or failed | ChannelInterceptor.postSend |
| Release resources after send | ChannelInterceptor.afterSendCompletion |
| Record processing outcome of each individual handler | ExecutorChannelInterceptor.afterMessageHandled |
| Block retrieving a message from a pollable channel | ChannelInterceptor.preReceive |

Do not use beforeHandle for a MessageChannel implementation that does not support ExecutorChannelInterceptor. This callback is supported on channels with configurable Executors, typically ExecutorSubscribableChannel.

## 4. Testing MessageHandler Directly

A handler unit test should inspect the actual message the handler receives. The example below uses an AtomicReference to capture the Message:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.MessageBuilder;

class MessageHandlerTests {

    @Test
    void handlerReceivesPayloadAndHeaders() {
        AtomicReference<Message<?>> received = new AtomicReference<>();
        MessageHandler handler = received::set;

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .setHeader("tenantId", "acme")
                .build();

        handler.handleMessage(message);

        assertNotNull(received.get());
        assertEquals("order-42", received.get().getPayload());
        assertEquals(
                "acme",
                received.get().getHeaders().get("tenantId"));
    }
}
~~~

This test verifies the MessageHandler contract: the handler receives the exact payload and headers passed in. For real handlers, replace AtomicReference by invoking the handler and verifying dependencies with Mockito or checking resulting state.

If the handler can throw an error:

~~~java
MessageHandler handler = message -> {
    throw new IllegalStateException("invalid order state");
};
~~~

Use assertThrows to verify the exception. When testing the handler directly, the test observes the exception at the handleMessage call site. When the handler is invoked by a channel, the channel implementation may wrap non-MessagingException exceptions into MessageDeliveryException. Therefore, write assertions against the specific layer under test.

## 5. Testing preSend Blocking the Entire Channel

The test below uses an ExecutorSubscribableChannel without passing an Executor. Handlers run synchronously on the thread calling send(), so assertions can run immediately after send returns.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

class ChannelInterceptorTests {

    @Test
    void preSendNullBlocksTheWholeChannel() {
        AtomicInteger handled = new AtomicInteger();
        AtomicInteger postSendCalls = new AtomicInteger();
        AtomicInteger completionCalls = new AtomicInteger();

        ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel();

        channel.subscribe(message -> handled.incrementAndGet());

        channel.addInterceptor(new ChannelInterceptor() {

            @Override
            public Message<?> preSend(
                    Message<?> message,
                    MessageChannel channel) {

                Object tenantId =
                        message.getHeaders().get("tenantId");

                return "acme".equals(tenantId) ? message : null;
            }

            @Override
            public void postSend(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent) {
                postSendCalls.incrementAndGet();
            }

            @Override
            public void afterSendCompletion(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent,
                    Exception ex) {
                completionCalls.incrementAndGet();
            }
        });

        Message<String> accepted = MessageBuilder
                .withPayload("order-42")
                .setHeader("tenantId", "acme")
                .build();

        Message<String> rejected = MessageBuilder
                .withPayload("order-43")
                .setHeader("tenantId", "other")
                .build();

        assertTrue(channel.send(accepted));
        assertFalse(channel.send(rejected));

        assertEquals(1, handled.get());
        assertEquals(1, postSendCalls.get());
        assertEquals(1, completionCalls.get());
    }
}
~~~

The assertions prove:

- The message with tenantId acme is sent and the handler runs once.
- The message with tenantId other is blocked before sendInternal.
- send() for the blocked message returns false.
- The interceptor's postSend and afterSendCompletion are called only for the message that passed preSend.

Here completionCalls equals 1 because the sole interceptor returned null for the rejected message; the rejecting interceptor's afterSendCompletion callback does not run. If an earlier interceptor had accepted the message, that earlier interceptor would still get cleaned up via afterSendCompletion when a downstream interceptor blocked it.

## 6. Testing beforeHandle Blocking a Single Subscriber

The next test registers two MessageHandlers on the same channel. ExecutorChannelInterceptor skips only the chosen handler; the other handler still processes the message.

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageHandler;
import org.springframework.messaging.support.ExecutorChannelInterceptor;
import org.springframework.messaging.support.ExecutorSubscribableChannel;
import org.springframework.messaging.support.MessageBuilder;

class ExecutorChannelInterceptorTests {

    @Test
    void beforeHandleCanSkipOneSubscriber() {
        AtomicInteger acceptedCalls = new AtomicInteger();
        AtomicInteger skippedCalls = new AtomicInteger();
        AtomicInteger afterHandledCalls = new AtomicInteger();

        MessageHandler acceptedHandler =
                message -> acceptedCalls.incrementAndGet();

        MessageHandler skippedHandler =
                message -> skippedCalls.incrementAndGet();

        ExecutorSubscribableChannel channel =
                new ExecutorSubscribableChannel();

        channel.subscribe(acceptedHandler);
        channel.subscribe(skippedHandler);

        channel.addInterceptor(new ExecutorChannelInterceptor() {

            @Override
            public Message<?> beforeHandle(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler) {

                return handler == skippedHandler ? null : message;
            }

            @Override
            public void afterMessageHandled(
                    Message<?> message,
                    MessageChannel channel,
                    MessageHandler handler,
                    Exception ex) {
                afterHandledCalls.incrementAndGet();
            }
        });

        Message<String> message = MessageBuilder
                .withPayload("order-42")
                .build();

        assertTrue(channel.send(message));

        assertEquals(1, acceptedCalls.get());
        assertEquals(0, skippedCalls.get());
        assertEquals(1, afterHandledCalls.get());
    }
}
~~~

Because the channel is created without an Executor, the SendTasks run immediately on the thread calling send(). Thus the counters already have their final values when assertions run.

The test also reveals an easily misunderstood detail: channel.send(message) returns true even though skippedHandler was not invoked. The channel accepted the message and dispatched it to subscribers; the filter in beforeHandle only skipped one handler invocation. afterMessageHandled is called only for handlers where beforeHandle returned a Message. For a skipped subscriber, this callback is not called for the interceptor that returned null.

If the channel is configured with an asynchronous Executor, do not assert counters immediately after send(). Synchronize the test using CountDownLatch, CompletableFuture, or a bounded-timeout wait mechanism. Avoid Thread.sleep because execution time depends on thread scheduling and can make tests flaky.

## 7. Testing Allow/Deny Conditions

Blocking conditions should be tested on both the allow branch and the deny branch. Testing only the deny branch can miss bugs like an interceptor always returning null; testing only the allow branch can miss invalid messages slipping through.

A sample test matrix:

| Condition | Expected Result | Assertion |
|---|---|---|
| Allowed tenantId header | Handler is called | send true, handled increments by 1 |
| Disallowed tenantId header | Channel blocks message | send false, handled does not increment |
| Missing required header | Block or report error per chosen policy | Check false or contract-compliant exception |
| Message type in allow list | Allow sending | Handler receives exact payload |
| Message type outside allow list | Block or route to error handling | Business handler is not invoked |
| Expired message | Block before dispatch | No side effects occur |
| Rate limit exceeded | Reject per policy | Count blocked messages accurately |
| beforeHandle rejects one subscriber | That subscriber does not run | Other subscribers still run |

Each test should prepare its own data, register interceptors explicitly, and verify both the send result and handler side effects. Do not merely assert that the interceptor was called; what must be proven is whether the message reached the right handler or was blocked at the right scope.

## 8. Testing Interceptor Ordering and Callbacks

A channel can have multiple interceptors. An interceptor added via addInterceptor(interceptor) is appended to the end of the list; the overload addInterceptor(index, interceptor) allows placing it at a specific position. setInterceptors(list) replaces the entire current list, so using it in configuration can accidentally wipe out previously registered interceptors.

When testing ordering, you can use AtomicReference or a List to record callbacks:

- Interceptor A adds a normalized header in preSend.
- Interceptor B checks that header in preSend.
- The handler checks the final message it receives.
- postSend records the sent outcome.
- afterSendCompletion verifies cleanup after send completes.

If an interceptor returns a new Message, that new message is passed to subsequent interceptors and the channel. Use MessageBuilder.fromMessage(message) when you need to create a copy that preserves existing headers and updates certain fields.

~~~java
Message<?> normalized = MessageBuilder
        .fromMessage(message)
        .setHeader("normalized", true)
        .build();

return normalized;
~~~

Do not directly modify the MessageHeaders of an already-published message as if it were a mutable Map. Messages and headers are designed around immutability; create a new message or use MessageHeaderAccessor according to its lifecycle when headers need to change.

On a normal send:

1. preSend runs before sendInternal.
2. postSend runs after sendInternal and receives boolean sent.
3. afterSendCompletion runs last for cleanup, even if send throws an exception, provided the interceptor let preSend pass.

If preSend returns null, sendInternal and postSend do not run. afterSendCompletion applies only to earlier interceptors that already accepted the message; the interceptor returning null does not receive its own completion callback.

## 9. Blocking Conditions on Receive

ChannelInterceptor also has callbacks for receive, though their scope is narrower:

- preReceive returns false to prevent the channel from retrieving a message.
- postReceive runs after retrieving a message and can transform the message.
- These receive callbacks apply only to PollableChannel.

SubscribableChannel pushes messages directly to subscribers and has no receive() API. Therefore, do not write preReceive tests on ExecutorSubscribableChannel; such tests do not exercise an actual execution path.

If the system uses a PollableChannel, separately test cases where preReceive allows, preReceive denies, and no message is available to receive. Only verify callbacks relevant to the channel implementation in use.

## 10. Testing Annotated Handlers and Adapters

A method annotated with @MessageMapping is not by itself a MessageHandler. Spring creates an adapter/handler mapping to locate the method matching a message, resolve parameters, convert the payload, and then invoke the method.

Therefore, tests should be split into layers:

| Test Layer | What to Prove |
|---|---|
| Unit test service/controller method | Business logic, outputs, and exceptions |
| Unit test MessageHandler | Payload/headers are processed properly |
| Channel test | Channel dispatch and interceptor allow/deny behave properly |
| Handler mapping test | Destination/route maps to the right method |
| Adapter integration test | Codec, header mapping, authentication, and protocol work properly |
| End-to-end test | Real client sends a message over the transport and receives the expected result |

Directly calling a controller method in a unit test does not test @MessageMapping, argument resolvers, message converters, or channel interceptors. When those parts need verification, create a test with the real adapter configuration or use the corresponding test client, such as a STOMP client for WebSocket/STOMP or RSocketRequester for RSocket.

Do not pull the entire Spring ApplicationContext and transport into every test. Small unit tests run fast and pinpoint causes; fewer integration tests verify wiring across layers.

## 11. Common Testing Mistakes

| Mistake | Why It Is Wrong | How to Fix |
|---|---|---|
| Only checking that the interceptor was called | Does not prove whether the handler ran | Assert send result and handler invocation count |
| Assuming send true means every handler finished | send confirms channel acceptance/dispatch per implementation | Check side effects or completion separately |
| Using preSend to block a single subscriber | preSend blocks the entire channel | Use ExecutorChannelInterceptor.beforeHandle if the channel supports it |
| Assuming beforeHandle null makes send false | beforeHandle runs per subscriber after channel dispatch | Assert the skipped subscriber and that other subscribers still ran |
| Testing async and asserting immediately | Handler may not have run when assertions start | Use a latch/future with a timeout |
| Using Thread.sleep to wait | Tests depend on timing and turn flaky | Synchronize on completion signals |
| Testing preReceive on SubscribableChannel | SubscribableChannel has no receive() | Use an actual PollableChannel |
| Testing only the deny branch | The interceptor might be blocking all messages | Test both allow and deny |
| Using setInterceptors and wiping other configs | This API replaces the current list | Use addInterceptor or configure the full list |
| Using client-sent headers as trusted identity | Headers can be spoofed | Rely on authenticated Principal/session and server policies |
| Expecting a return value from MessageHandler | handleMessage returns void | Check side effects, output channel, or adapter replies |
| Testing @MessageMapping method directly and concluding routing works | Handler mapping did not run | Add an integration test for the adapter |

## 12. Safe Interceptor Design

Interceptors typically sit on the path of every message in a channel. Therefore:

- Keep preSend and beforeHandle fast; avoid synchronous network calls or database queries.
- Check only necessary conditions at the channel layer; keep complex business processing in handlers/services.
- Do not use client-controlled headers as proof of identity. Use authenticated principal/session details and enforce authorization on the server.
- Distinguish intentional blocking from operational errors: null is message filtering; exceptions are observable failures.
- Record counts of blocked messages by reason, while avoiding logging tokens, cookies, personal payloads, or secrets.
- Do not cause business side effects in interceptors because callbacks may execute on the sending thread or an executor thread depending on the channel.
- When modifying a message, create a new message and preserve necessary headers.
- For async channels, ensure any shared state inside an interceptor is thread-safe.

A blocking interceptor should not silently drop important commands without proper metrics or logs. If a rejected message needs to be retried, dead-lettered, or reported as an error to the client, design that handling path explicitly; a false return from send() is not by itself a business response.

## 13. Checklist for a Solid Test Suite

Before concluding that a MessageHandler and its interceptors work properly, verify:

1. Tests create Messages with payload and headers of the proper types.
2. Direct handlers receive the right message and behave properly.
3. preSend allows valid messages.
4. preSend returning null blocks invalid messages and send() returns false.
5. Handlers are not called when the entire channel is blocked.
6. postSend and afterSendCompletion are verified across their lifecycle.
7. beforeHandle returning null skips only the selected subscriber.
8. Other subscribers still receive the message when one subscriber is skipped.
9. Asynchronous tests have deterministic wait mechanisms and finite timeouts.
10. preReceive is tested only on PollableChannel.
11. Integration tests verify mapping, conversion, and transport when needed.
12. Tests check both side effects and key metrics/logs, not just that callbacks executed.

## Key Takeaways

MessageHandler is where a Message is processed; MessageChannel coordinates sending; ChannelInterceptor intervenes at the channel boundary. preSend returning null blocks the entire send and causes send() to return false. ExecutorChannelInterceptor.beforeHandle returning null skips only one MessageHandler during ExecutorSubscribableChannel dispatch; send() can still return true because the channel accepted the message.

For clear testing, use MessageBuilder to construct inputs, call MessageHandler directly for unit tests, use ExecutorSubscribableChannel to verify dispatch and interceptors, and add integration tests when verifying adapters or protocols. Always check the send result, handler invocation counts, completion callbacks, and actual side effects.

## References

- [MessageHandler — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/MessageHandler.html)
- [MessageChannel — Spring Framework 6.1.x API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/messaging/MessageChannel.html)
- [ChannelInterceptor — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [ExecutorChannelInterceptor — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ExecutorChannelInterceptor.html)
- [ExecutorSubscribableChannel — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ExecutorSubscribableChannel.html)
- [AbstractMessageChannel — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html)
- [InterceptableChannel — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/InterceptableChannel.html)
- [MessageBuilder — Spring Framework 6.1.21 API](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/MessageBuilder.html)
- [Spring Framework Messaging package](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/package-summary.html)
