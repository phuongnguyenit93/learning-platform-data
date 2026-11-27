# Interceptor Order and Multiple Interceptors

In Spring Integration, a **MessageChannel** is the transit point for messages between endpoints. A channel can have multiple **ChannelInterceptor** instances attached to normalize headers, validate messages, record audits, measure timing, or observe the processing flow. When multiple interceptors are present, the invocation order determines which interceptor sees the message first, which can modify data received by subsequent interceptors, and when cleanup runs.

This topic belongs to the **Channel interceptor** group in Spring Integration Runtime. Understanding interceptor ordering helps you read the message send and receive lifecycle accurately and diagnose differences between synchronous processing, executor-based dispatch, and queued channels.

## 1. Order During a Message Send

Interceptors are attached to a channel as a list. For a send operation, Spring invokes **preSend** in order from the start of the list to the end. The message returned by the previous interceptor becomes the input to the next interceptor. Therefore, if the first interceptor creates or modifies a header and returns a new message, subsequent interceptors see that header.

After the channel executes the send operation, **postSend** is called in list order. The **sent** parameter indicates whether the channel's send operation succeeded. Finally, **afterSendCompletion** is called in reverse order for the interceptors that successfully participated in the **preSend** phase. This hook also receives an **Exception** to handle completion or cleanup when the send operation encounters an error.

Example list with three interceptors A, B, and C:

~~~text
preSend:             A -> B -> C
channel.doSend(...)
postSend:            A -> B -> C
afterSendCompletion: C -> B -> A
~~~

**postSend** and **afterSendCompletion** serve different roles. **postSend** observes the send result returned by the channel. **afterSendCompletion** is suitable for closing resources or restoring state set up in **preSend**, because it is invoked when the send call ends, even if an exception occurred. Reverse completion order gives the interceptor invoked last during preparation the chance to clean up first.

### Stopping a Send with preSend

**preSend** returns a **Message** to continue sending. If it returns **null**, the interceptor rejects the message and the send chain stops there: the channel does not execute the send operation and **postSend** is not called for the blocked send. Interceptors that already passed through the **preSend** phase still receive the **afterSendCompletion** callback in reverse order so they can clean up.

Do not return **null** due to an unexpected condition without recording the reason. When using an interceptor to filter or block messages, log the channel, message ID, or correlation ID along with the rejection reason. If that condition is a primary business rule, consider placing it in a filter endpoint so the flow is easier to read and test.

## 2. Order During a Message Receive

Receive hooks are used with channels that support the **receive** operation, typically **PollableChannel** implementations such as **QueueChannel**. **preReceive** is called in list order before the channel retrieves a message. If an interceptor returns **false**, the receive operation is prevented. When a message is received, **postReceive** is called in list order; each interceptor can return a transformed message for the next interceptor to use.

**afterReceiveCompletion** is called in reverse order for the interceptors that participated in the **preReceive** phase. This hook receives the message (if any) and the exception (if any), making it suitable for restoring state or releasing resources after the receive operation.

~~~text
preReceive:             A -> B -> C
channel.receive(...)
postReceive:            A -> B -> C
afterReceiveCompletion: C -> B -> A
~~~

Since Spring Integration 5.1, **postReceive** is no longer called when no message is received. If you need to handle completion even when the queue is empty or the receive operation throws an exception, use **afterReceiveCompletion**.

## 3. Configuring Multiple Interceptors on the Same Channel

For local interceptors, **addInterceptor** appends the interceptor to the end of the list. Therefore, the invocation order can be controlled directly where the channel is created. **addInterceptor(index, interceptor)** allows inserting at a specific index; only use an index when that position has clear meaning and is maintained consistently.

~~~java
@Bean
MessageChannel ordersChannel() {
    DirectChannel channel = new DirectChannel();
    channel.addInterceptor(new HeaderNormalizationInterceptor());
    channel.addInterceptor(new OrderAuditInterceptor());
    channel.addInterceptor(new DispatchMetricsInterceptor());
    return channel;
}
~~~

In this example, **HeaderNormalizationInterceptor** runs first, **OrderAuditInterceptor** receives the message after headers have been normalized, and **DispatchMetricsInterceptor** observes the outcome of the preceding steps. Local interceptors are invoked in the exact order they were added to the list.

When configuring with Java DSL, you can attach interceptors to the current channel using **intercept(...)**. The passed interceptors are appended in declaration order, after any interceptors already on the channel:

~~~java
IntegrationFlow flow = IntegrationFlow
    .from("orders.input")
    .intercept(normalizeHeaders, auditOrder, measureDispatch)
    .handle(orderHandler)
    .get();
~~~

Be explicit about which channel is being configured. An interceptor attached to a channel only observes operations passing through that channel; it does not automatically wrap the entire endpoint or every step in an **IntegrationFlow**.

## 4. Global Interceptors and the order Attribute

When the same behavior needs to apply across multiple channels, Spring Integration provides global channel interceptors. In Java configuration, annotate a bean with **@GlobalChannelInterceptor**; the **patterns** attribute restricts which channel names match. If **patterns** is omitted, the interceptor applies to all channels.

~~~java
@Configuration
class OrderInterceptorConfiguration {

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*", order = -20)
    ChannelInterceptor normalizeOrderHeaders() {
        return new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message, MessageChannel channel) {
                return MessageBuilder.fromMessage(message)
                    .setHeader("flow", "orders")
                    .build();
            }
        };
    }

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*", order = -10)
    ChannelInterceptor auditOrders() {
        return new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message, MessageChannel channel) {
                // Record audit using channel and message ID.
                return message;
            }
        };
    }

    @Bean
    @GlobalChannelInterceptor(patterns = "orders*", order = 20)
    ChannelInterceptor observeDispatch() {
        return new ChannelInterceptor() {
            @Override
            public void postSend(
                    Message<?> message, MessageChannel channel, boolean sent) {
                // Record the channel's send outcome.
            }
        };
    }
}
~~~

The **order** of **@GlobalChannelInterceptor** controls where the global interceptor is inserted on a channel:

| order value | Position |
|---|---|
| Negative | Before interceptors configured directly on the channel |
| Positive | After interceptors configured directly on the channel |
| Multiple global interceptors matching one channel | Sorted by order value |
| Not specified | Defaults to 0 |

Thus, in the example, the two interceptors with negative **order** run before local interceptors; **normalizeOrderHeaders** comes before **auditOrders** because it has a lower value. **observeDispatch** has a positive **order**, so it is inserted after interceptors configured directly on the channel. When ordering affects data or side effects, assign distinct **order** values rather than relying on bean discovery order.

**patterns** selects channels by name. You can restrict an interceptor to a group of channels like **orders*** instead of applying logging or auditing to every channel in the application. Since Spring Integration 5.1, global interceptors also apply to dynamically registered channels, such as channels created via **IntegrationFlowContext**.

## 5. Do Not Confuse Interceptor Order with Processing Order Across Threads

The order of interceptors within a single send or receive call is determined by the interceptor list. However, you cannot infer a fixed order between send events and receive events when the channel allows both sides to run independently. Channel type and when the consumer polls for messages both affect the observed sequence.

| Channel type | What happens on send | Meaning of callbacks |
|---|---|---|
| **DirectChannel** | Dispatches to subscriber synchronously on the sending thread | **postSend** runs after the channel's dispatch call completes |
| **ExecutorChannel** | Hands off dispatch work to an executor | **postSend** reflects channel dispatch/task submission; does not prove the handler finished |
| **QueueChannel** | Places message into a queue | Send and receive are two separate operations; consumer may receive before or after sender runs **postSend** |

With **QueueChannel**, if a receiver is already waiting, **preReceive** and **postReceive** may appear before the sender's **postSend**. If the sender enqueues the message and finishes before the receiver polls, **postSend** will appear before the receive callbacks. This is a timing difference across two threads, not an interceptor ordering bug.

Therefore, rely only on relationships within a single operation: **preSend** occurs before **postSend**, and **preReceive** occurs before **postReceive**. Do not use log ordering between sender and receiver to conclude that interceptors ran out of order. With **DirectChannel**, the receiving path does not go through **preReceive**/**postReceive**; those hooks are for receive operations on pollable channels.

One point to keep in mind when measuring performance: **afterSendCompletion** finishes the channel's send call. On an **ExecutorChannel**, it is not a signal that business processing in the consumer has ended. To measure handler processing time, place observation or advice around the handler/endpoint, or emit measurement events from the consumer itself.

## 6. Designing a Maintainable Interceptor Chain

A good interceptor chain has an easily explainable order. For example, in an order flow:

1. Normalize headers and add shared metadata.
2. Check technical preconditions on the message before putting it into the channel.
3. Record an audit or trace ID so subsequent steps can correlate.
4. Send the message and record the result returned by the channel.
5. Clean up state in **afterSendCompletion** or **afterReceiveCompletion**.

Not every interceptor needs to implement every callback. The default methods of **ChannelInterceptor** do nothing or return the message/value allowing continuation, so each interceptor should override only the hooks it actually needs.

Some practical guidelines:

- **Keep interceptors lightweight.** Avoid remote service calls, database queries, or long I/O waits in **preSend** and **postSend**. Those operations sit on the send path and can increase latency or reduce throughput.
- **Return the modified message.** **Message** is immutable; when creating a new message with **MessageBuilder**, you must return that message for the next interceptor and channel to use.
- **Distinguish rejection from error.** Returning **null** from **preSend** or **false** from **preReceive** actively stops the operation. Throwing an exception indicates an error and can trigger error handling in the caller layer.
- **Do not treat completion as transaction commit.** **afterSendCompletion** and **afterReceiveCompletion** conclude a channel call. They do not represent that the entire flow or endpoint transaction has committed.
- **Avoid relying on ThreadLocal across executors.** When a message moves to another thread, state bound to the sending thread does not automatically appear on the consumer thread. If you need to pass traces or context, prefer message headers or an appropriate propagation mechanism.
- **Do not log sensitive payloads.** Use channel name, message ID, correlation ID, selected headers, and processing duration for diagnostics.

## 7. Verifying Order at Runtime

When a message passes through multiple interceptors, verify the actual list on the exact channel rather than inferring from bean names alone. For channels implementing **InterceptableChannel**, **getInterceptors()** returns a read-only view of the configured interceptor list. You can inspect this list at startup or in integration tests.

An ordering test can use a list that records events:

~~~java
List<String> events = new CopyOnWriteArrayList<>();

// Each interceptor appends its name to events in preSend,
// postSend, and afterSendCompletion.
// Send a message through a DirectChannel and compare events
// against the expected order of each callback.
~~~

Test the following scenarios separately:

- Successful send through **DirectChannel**.
- An interceptor returning **null** in **preSend**.
- **doSend** or a callback throwing an exception.
- Receiving a message from **QueueChannel** both when a message is present and when the queue is empty.
- Sending through **ExecutorChannel**, confirming **postSend** is not mistaken for consumer completion.
- A channel having both local interceptors and global interceptors with negative and positive **order**.

During runtime diagnostics, cross-reference channel name, message ID/correlation ID, thread name, and timestamp. If logs between two sides do not match your expected order, first identify whether the channel is synchronous, executor-backed, or pollable; only then inspect the interceptor list order.

## 8. Key Takeaways

- Local interceptors are added to the list in registration order; **addInterceptor** appends to the end of the list.
- **preSend** and **postSend** run in list order; **afterSendCompletion** runs in reverse order for interceptors that participated in the preparation phase.
- For receive operations, **preReceive** and **postReceive** run in list order; **afterReceiveCompletion** runs in reverse order.
- **@GlobalChannelInterceptor.order** places global interceptors before or after local interceptors; global interceptors are sorted by **order** value.
- Callback ordering between send and receive is not fixed on channels with independent senders/receivers.
- **postSend** and **afterSendCompletion** reflect the channel's send lifecycle, not necessarily the business processing lifecycle of an asynchronous consumer.

## References

- [Spring Integration Reference — Channel Interceptors](https://docs.spring.io/spring-integration/docs/latest-ga/reference/html/channel.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [GlobalChannelInterceptor API](https://docs.spring.io/spring-integration/docs/latest-ga/api/org/springframework/integration/config/GlobalChannelInterceptor.html)
