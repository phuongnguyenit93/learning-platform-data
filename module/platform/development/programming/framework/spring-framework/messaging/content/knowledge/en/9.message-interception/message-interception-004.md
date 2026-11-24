# postSend and afterSendCompletion on Success or Failure

## Learning Objectives

After this lesson, you will be able to:

- Describe the lifecycle of sending a Message through a channel with a registered ChannelInterceptor.
- Distinguish preSend, postSend, and afterSendCompletion.
- Understand the different states represented by the sent and ex parameters.
- Recognize when send returns true, returns false, or throws an exception.
- Know when postSend is invoked and when afterSendCompletion is invoked.
- Understand the limitations of interceptors when a channel dispatches asynchronously.
- Use afterSendCompletion to release resources according to the proper lifecycle.
- Write thread-safe interceptors when multiple threads send Messages concurrently.

## 1. Where Does ChannelInterceptor Sit?

In Spring Messaging, MessageChannel is the message-sending boundary. A producer calls send(Message), and the channel receives and forwards the Message according to its implementation. ChannelInterceptor lets you observe or intervene in send/receive operations at that boundary without modifying producer or handler code.

ChannelInterceptor belongs to the org.springframework.messaging.support package. It provides callbacks for the sending process:

- **preSend:** runs before the channel performs the send operation; can modify the Message or block sending.
- **postSend:** runs immediately after the send call returns normally; receives a boolean indicating the send outcome.
- **afterSendCompletion:** runs when the send operation finishes for cleanup; receives both the sent outcome and any exception.

A channel that supports interceptor registration typically implements InterceptableChannel. Spring Framework and Spring Integration channels may provide an addInterceptor API for registration.

~~~mermaid
flowchart TB
    A["Producer calls send(message)"]
    B["preSend(message, channel)"]
    C{"preSend returns Message?"}
    D["Channel performs send"]
    E{"send returns normally?"}
    F["postSend(message, channel, sent)"]
    G["afterSendCompletion(message, channel, sent, null)"]
    H["afterSendCompletion(message, channel, sent, exception)"]
    I["send returns boolean"]
    J["Send blocked before channel"]

    A --> B --> C
    C -->|Yes| D --> E
    C -->|No, returns null| J
    E -->|Yes| F --> G --> I
    E -->|Throws exception| H
~~~

The diagram illustrates the send lifecycle of an interceptor whose preSend completed successfully. If preSend returns null, the send operation is blocked and there is no postSend for that interceptor; earlier interceptors that already completed preSend may still receive the completion callback for cleanup.

## 2. Three Callbacks to Distinguish

### 2.1. preSend: Before Sending

Signature:

~~~java
Message<?> preSend(Message<?> message, MessageChannel channel);
~~~

The callback receives the Message and the target channel. It can:

- Return the original Message to continue sending.
- Build a new Message using MessageBuilder to add or adjust headers.
- Return null to prevent the actual send operation from happening.
- Throw an exception if an invalid condition is detected.

Example of blocking a Message missing a required header:

~~~java
@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    if (!message.getHeaders().containsKey("eventType")) {
        return null;
    }
    return message;
}
~~~

When preSend returns null, the channel does not invoke sendInternal for that Message and the send call typically returns false. This is a send blocked by an interceptor, not a Message that a consumer failed to process.

### 2.2. postSend: Immediately After the Send Call

Signature:

~~~java
void postSend(Message<?> message, MessageChannel channel, boolean sent);
~~~

This callback runs right after the channel's send operation returns a boolean. The sent parameter is that boolean result:

- sent=true: the channel reports that it accepted/sent the Message according to the implementation's contract.
- sent=false: the channel returned normally but did not accept or could not send the Message under current conditions.

postSend is suitable for recording send outcomes, incrementing counters, or emitting metrics. It does not receive an exception because this callback only runs when the send operation returned normally.

If sending throws an exception instead of returning a boolean, postSend is not invoked for that send attempt. Cleanup is still handled via afterSendCompletion.

### 2.3. afterSendCompletion: Cleanup After the Operation Finishes

Signature:

~~~java
void afterSendCompletion(
        Message<?> message,
        MessageChannel channel,
        boolean sent,
        Exception ex
);
~~~

This callback is designed as a completion point after the send operation, even when an exception occurs, so the interceptor can release resources or finish cleanup work.

The two outcome parameters must be read together:

- sent indicates the boolean result if the send operation returned normally; when the operation throws an exception, this value is typically still false because no successful send result occurred.
- ex is the exception raised during the send process, if any; ex=null means no exception was passed to the callback.

afterSendCompletion is only invoked for interceptors whose preSend completed successfully and returned a Message. If preSend returned null, the completion callback is not invoked for the interceptor that blocked that Message.

Do not confuse afterSendCompletion with a “consumer finished processing” callback. It only marks that the channel's send operation has ended.

## 3. Distinguishing Three Send States

An interceptor needs to distinguish at least these three situations:

| Situation | send Returns | postSend | afterSendCompletion |
|---|---|---|---|
| Send accepted | true | Yes, sent=true | Yes, sent=true, ex=null |
| Channel returns false | false | Yes, sent=false | Yes, sent=false, ex=null |
| Send operation throws exception | No boolean | Does not run | Yes, sent=false, ex holds exception |

This is an important point: **false and an exception are two different failure modes**.

- false is a normal return value from the send call; the producer can inspect it and decide to retry, throttle, or record the rejection.
- An exception indicates the send operation did not complete along the normal flow. The application must classify the exception and decide how to handle it.
- true only reflects that the channel accepted the Message according to its implementation. It does not guarantee the handler has completed business work or that the broker has durably persisted the data.

With an asynchronous channel, send may return true after the task is dispatched to an executor. If the handler fails later on a worker thread, the handler's exception is usually not propagated back to afterSendCompletion on the sending thread. The interceptor only observes the channel's send/dispatch lifecycle.

## 4. Callback Ordering Within a Single Send

With a single interceptor, when send returns normally, the basic sequence is:

~~~text
preSend
channel performs send
postSend
afterSendCompletion
send returns to caller
~~~

If send returns false, postSend is still invoked with sent=false, and then afterSendCompletion receives sent=false and ex=null.

If the send operation throws an exception:

~~~text
preSend
channel performs send
exception occurs
afterSendCompletion(sent=false, ex=exception)
exception is thrown to caller
~~~

postSend is not called in this case because no boolean result was returned from the send operation.

When multiple interceptors exist:

- preSend is invoked in registration order.
- postSend is invoked after the send operation; the channel implementation manages callback ordering.
- afterSendCompletion is invoked in the reverse order of successful preSend calls, similar to unwinding a resource stack in reverse.

Do not rely on ordering across different producer/consumer threads. With an asynchronous channel, a consumer may begin processing before or after the producer receives the postSend callback, depending on the dispatch mechanism and thread scheduling.

## 5. afterSendCompletion Is Not Synonymous with Business Completion

The callback name may lead readers to think it runs after the consumer finishes processing. In reality, the callback is tied to the send call on the MessageChannel.

For example, with ExecutorSubscribableChannel:

1. Producer calls send.
2. Channel submits a task to the executor.
3. Executor accepts the task.
4. send returns true.
5. postSend and afterSendCompletion run on the sending thread.
6. The handler may start or continue processing on a worker thread.

Thus, an interceptor can record that the channel accepted the Message, but cannot conclude that the handler has finished.

If you need to observe business processing outcomes, use consumer-side mechanisms such as logging in the handler, an error channel, acknowledgements, replies, or business metrics. Do not use afterSendCompletion as a substitute for acknowledgements.

## 6. Registering an Interceptor on a Channel

Channels that support interceptors provide a registration API, typically addInterceptor:

~~~java
DirectChannel channel = new DirectChannel();
channel.addInterceptor(new ChannelInterceptor() {
    @Override
    public void postSend(
            Message<?> message,
            MessageChannel channel,
            boolean sent) {
        System.out.println("sent=" + sent);
    }

    @Override
    public void afterSendCompletion(
            Message<?> message,
            MessageChannel channel,
            boolean sent,
            Exception ex) {
        System.out.println("completed");
    }
});
~~~

ChannelInterceptor in modern Spring Framework versions has default methods. Therefore, you can override only the callbacks you need without implementing the entire interface.

If logic must apply to every channel in a Spring Integration application, consider a global channel interceptor. Global interceptors must be configured using Spring Integration's mechanism; direct registration via addInterceptor applies only to a specific channel.

## 7. Runnable Java 17 Example: Success, false, and Exception

The example below uses Spring Integration's DirectChannel and QueueChannel to demonstrate the three send outcomes. It logs from postSend and afterSendCompletion.

### 7.1. Maven Configuration

Create pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>channel-interceptor-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.integration</groupId>
            <artifactId>spring-integration-core</artifactId>
            <version>6.5.10</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 7.2. Complete Program

Create src/main/java/demo/ChannelInterceptorLifecycleDemo.java:

~~~java
package demo;

import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;

public class ChannelInterceptorLifecycleDemo {

    private static ChannelInterceptor loggingInterceptor(String label) {
        return new ChannelInterceptor() {
            @Override
            public void postSend(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent) {
                System.out.println(label + ".postSend.sent=" + sent);
            }

            @Override
            public void afterSendCompletion(
                    Message<?> message,
                    MessageChannel channel,
                    boolean sent,
                    Exception ex) {
                System.out.println(
                        label + ".afterSendCompletion.sent=" + sent
                );
                System.out.println(
                        label + ".afterSendCompletion.exceptionPresent="
                                + (ex != null)
                );
            }
        };
    }

    public static void main(String[] args) {
        demonstrateSuccess();
        demonstrateFalseResult();
        demonstrateException();
    }

    private static void demonstrateSuccess() {
        System.out.println("-- success --");

        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(loggingInterceptor("success"));

        channel.subscribe(message ->
                System.out.println(
                        "handler.payload=" + message.getPayload()
                )
        );

        boolean sent = channel.send(message("ORD-108"));
        System.out.println("send.result=" + sent);
    }

    private static void demonstrateFalseResult() {
        System.out.println("-- false result --");

        QueueChannel channel = new QueueChannel(1);

        // Fill the queue before registering the interceptor.
        channel.send(message("already-queued"));
        channel.addInterceptor(loggingInterceptor("full"));

        // Queue is full; timeout 0 requests not waiting for free space.
        boolean sent = channel.send(message("ORD-108"), 0);
        System.out.println("send.result=" + sent);
    }

    private static void demonstrateException() {
        System.out.println("-- exception --");

        DirectChannel channel = new DirectChannel();
        channel.addInterceptor(loggingInterceptor("failure"));

        channel.subscribe(message -> {
            System.out.println("handler.throwing=true");
            throw new IllegalStateException("simulated handler failure");
        });

        try {
            channel.send(message("ORD-108"));
        }
        catch (RuntimeException ex) {
            System.out.println("send.exceptionObserved=true");
        }
    }

    private static Message<String> message(String payload) {
        return MessageBuilder.withPayload(payload).build();
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.ChannelInterceptorLifecycleDemo
~~~

Stdout:

~~~text
-- success --
handler.payload=ORD-108
success.postSend.sent=true
success.afterSendCompletion.sent=true
success.afterSendCompletion.exceptionPresent=false
send.result=true
-- false result --
full.postSend.sent=false
full.afterSendCompletion.sent=false
full.afterSendCompletion.exceptionPresent=false
send.result=false
-- exception --
handler.throwing=true
failure.afterSendCompletion.sent=false
failure.afterSendCompletion.exceptionPresent=true
send.exceptionObserved=true
~~~

### 7.3. Explaining the Three Results

**Success Case**

DirectChannel invokes the handler synchronously. The handler prints the payload and returns. The send call results in true, so postSend receives sent=true. Next, afterSendCompletion receives sent=true and ex=null.

**Channel Returns false Case**

QueueChannel has a capacity of 1 and was already filled before registering the interceptor. The second send uses timeout 0, so the channel does not wait for space and returns false. Because send returned normally, postSend still runs with sent=false. afterSendCompletion also runs with sent=false and ex=null.

**Exception Case**

The DirectChannel handler throws IllegalStateException. The send operation does not return a boolean normally, so postSend does not run. afterSendCompletion is still invoked with sent=false and a non-null ex. The caller catches RuntimeException and logs the error.

The example illustrates the callback lifecycle. In real applications, specific exception types may be wrapped by the channel inside a specialized MessagingException; therefore, handle exceptions by exception hierarchy and root cause rather than relying on a single class.

## 8. When preSend Blocks or Throws an Exception

preSend can alter the flow before the channel sends the Message:

- If it returns a Message, the send operation continues and that interceptor is eligible to receive afterSendCompletion.
- If it returns null, the channel does not perform the send operation. postSend does not run for the interceptor that blocked that Message. The send call usually returns false.
- If it throws an exception, the send operation stops and the exception propagates outward. Earlier interceptors whose preSend already completed may receive afterSendCompletion for cleanup.

When multiple interceptors exist, one interceptor may have opened resources in preSend. If a subsequent interceptor blocks the Message or throws an exception, the earlier interceptor's afterSendCompletion is the right place to release resources.

Do not open resources in postSend expecting afterSendCompletion to clean them up if postSend is skipped because send threw an exception. If you must open resources in preSend, ensure the corresponding completion callback can release them in both success and failure cases.

## 9. Multiple Interceptors and Cleanup Order

Suppose two interceptors A and B are registered in the order A then B.

Normal success flow:

~~~text
A.preSend
B.preSend
channel.send
A.postSend
B.postSend
B.afterSendCompletion
A.afterSendCompletion
~~~

afterSendCompletion runs in reverse order to support a stack model: resources opened in the order A then B are released in the order B then A.

When B's preSend returns null or throws an exception, A has already completed preSend so A can receive the completion callback. B did not complete preSend successfully, so it is not considered a fully registered interceptor on the completion stack.

Interceptors should not depend on one another unnecessarily. Keep callbacks small, clear, and safe to run repeatedly across different threads.

## 10. Thread Safety and Interceptor Overhead

ChannelInterceptor can be invoked concurrently when multiple producers send Messages through the same channel. An interceptor registered once is typically shared across many send calls.

Therefore:

- Avoid storing per-Message state in mutable fields of the interceptor.
- Use AtomicInteger, LongAdder, or a thread-safe metric registry when updating counters concurrently.
- Do not assume the same thread will invoke every callback if a channel or adapter changes how it dispatches.
- Avoid HTTP calls, database calls, or long blocking operations inside callbacks.
- Do not throw exceptions from afterSendCompletion just to report metrics; this callback is mainly for cleanup and recording.
- If per-send context must be passed, use Message headers or a context with a clear lifecycle.

If send duration must be measured, record the start time in preSend and compute the elapsed time in afterSendCompletion. Timing data must be stored in a thread-safe manner; do not use a single startedAt field shared across all Messages.

## 11. Choosing the Right Callback for the Purpose

| Need | Appropriate Callback | Reason |
|---|---|---|
| Inspect or modify a Message before sending | preSend | Runs before channel send |
| Block an invalid Message | preSend returning null or throwing exception | Prevents the send operation |
| Record the boolean result of send | postSend | Receives sent=true or false when send returns normally |
| Cleanup after send finishes, including exceptions | afterSendCompletion | Receives sent and exception |
| Measure actual processing inside consumer | Logic in handler or endpoint | Send interceptor does not prove handler finished |
| Track each handler invocation in an executor | ExecutorChannelInterceptor | Callbacks at the handler execution boundary |
| Observe all operations passing through a channel | ChannelInterceptor | Cross-cutting behavior at the channel |

ChannelInterceptor also has callbacks for receive. preReceive, postReceive, and afterReceiveCompletion apply only to PollableChannel because only that channel type has a receive operation actively called by consumers.

## 12. Common Pitfalls

1. **Assuming postSend runs when send throws an exception:** postSend takes a boolean, so it runs only when the send call returns normally.
2. **Assuming sent=false always comes with an exception:** send can return false normally; in that case ex in afterSendCompletion is null.
3. **Assuming afterSendCompletion always runs for every interceptor:** the callback runs only for interceptors whose preSend completed successfully and returned a Message.
4. **Confusing afterSendCompletion with consumer completion:** it only completes the channel's send operation.
5. **Using postSend to clean up resources:** if send throws an exception, postSend does not run; cleanup belongs in afterSendCompletion.
6. **Ignoring preSend returning null:** the Message is blocked, with no postSend for the interceptor that blocked it.
7. **Logging exceptions while ignoring sent:** both false results and exceptions must be distinguished to understand the true state.
8. **Assuming send=true means the handler succeeded:** an asynchronous channel may have only accepted the task.
9. **Holding shared mutable state in the interceptor:** multiple threads can overwrite each other's data.
10. **Doing heavy I/O in callbacks:** increases send latency or holds resources for too long.
11. **Assuming callback order is identical across channels and threads:** rely only on the order guaranteed within a single send chain.
12. **Confusing ChannelInterceptor with ExecutorChannelInterceptor:** one intercepts at the channel, while the other tracks handler execution.

## 13. Self-Check Questions

1. What does the sent parameter received by postSend represent?
2. When send returns false, do postSend and afterSendCompletion run?
3. When send throws an exception, which callback is used for cleanup?
4. Why can postSend not receive an exception directly?
5. Is afterSendCompletion invoked if preSend returns null?
6. How does sent=false with ex=null differ from sent=false with a non-null ex?
7. With an asynchronous channel, does postSend prove the handler finished processing?
8. Why does afterSendCompletion run in the reverse order of preSend?
9. When should ExecutorChannelInterceptor be used instead of ChannelInterceptor?
10. How can an interceptor be kept safe when multiple threads send concurrently?

## 14. Conclusion

postSend and afterSendCompletion serve two distinct points in the ChannelInterceptor send lifecycle. postSend runs right after the send operation returns normally and reports the boolean sent. afterSendCompletion runs when the send operation ends for cleanup, even on exceptions, provided the interceptor's preSend completed and returned a Message.

When send returns false, postSend still runs with sent=false and afterSendCompletion receives ex=null. When send throws an exception, postSend does not run; afterSendCompletion receives the exception so the interceptor can clean up. With asynchronous channels, these callbacks only describe the channel accepting or completing the send operation, not that the consumer has finished business processing.

## Official References

- Spring Framework ChannelInterceptor API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html
- Spring Framework AbstractMessageChannel API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/AbstractMessageChannel.html
- Spring Integration Channel Interceptors reference: https://docs.spring.io/spring-integration/reference/channel/interceptors.html
- Spring Integration DirectChannel API: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/DirectChannel.html
- Spring Integration QueueChannel API: https://docs.spring.io/spring-integration/api/org/springframework/integration/channel/QueueChannel.html
