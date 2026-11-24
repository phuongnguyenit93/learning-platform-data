# The ERROR frame and ending a session because of an error

## 1. What is an ERROR frame?

STOMP defines `ERROR` as a frame the server sends to the client when the server cannot continue processing the protocol or a frame from the client. Unlike `MESSAGE`, which is used to deliver business data, and `RECEIPT`, which is used to confirm that the server has processed a frame, `ERROR` represents an error at the STOMP connection level.

The most important rule of STOMP 1.2: after sending `ERROR`, the server **must close the connection immediately afterwards**. Therefore, the client must treat a received `ERROR` frame as a sign that the current STOMP session has ended. The client should not continue to send `SEND`, `SUBSCRIBE`, `ACK`, or other frames on that connection.

`ERROR` is a server frame. The client does not send `ERROR` to report an error to the server; the client can close the socket or end the transport when it encounters an error on its own side.

In a Spring application, you need to distinguish three kinds of outcomes:

- **STOMP `ERROR` frame:** a protocol/server-level error; the connection is closed according to STOMP.
- **Application error message:** a normal `MESSAGE` containing a business error code; the session can continue to operate.
- **Transport error or WebSocket close:** the network/WebSocket connection has an error or is closed; there may be no `ERROR` frame that reaches the client.

## 2. Structure of an ERROR frame

A STOMP frame has this general structure:

~~~text
COMMAND
header:value
header:value

body
\0
~~~

Example of the server rejecting a `SEND` command to a destination that does not exist:

~~~text
ERROR
message:destination-unavailable
receipt-id:send-42
content-type:text/plain;charset=utf-8
content-length:31

The destination is unavailable.\0
~~~

Meaning of the parts:

| Component | Meaning |
| --- | --- |
| `ERROR` | The command of the server frame |
| `message` | An optional header; it should contain a short, human-readable description |
| `receipt-id` | If the error relates to a client frame that has `receipt`, this value should match the `receipt` of that frame |
| `content-type` | The MIME type of the body, if any |
| `content-length` | The number of bytes of the body, not the number of characters; it should be present when the frame carries a body |
| Body | Additional detailed information; it may be empty or absent |
| `\0` | The NUL byte that terminates the frame |

STOMP 1.2 does not require a specific mandatory header for `ERROR`. The `message` header is recommended. If a body exists, `content-type` and `content-length` are recommended; if the body contains a NUL byte, `content-length` is mandatory so that the decoder can determine the body boundary correctly.

Header values in STOMP 1.2 use escape sequences for `\r`, `\n`, `\c`, and `\\`. When building a frame manually, you must apply the escape rules correctly. `content-length` counts the actual UTF-8 octets; do not use `String.length()` for content that has multi-byte characters.

## 3. When does the server send ERROR?

STOMP 1.2 allows the server to send `ERROR` when there is an error, and specifies that the server must close the connection after that frame. Common situations:

- The server does not accept `CONNECT`/`STOMP`, for example there is no common protocol version or the virtual host is invalid.
- The frame is syntactically incorrect, is missing a required header, or contains an invalid header escape sequence.
- The client sends an unsupported command.
- The server cannot process `SEND`, for example the destination is invalid or the operation is rejected.
- The server cannot create a subscription for `SUBSCRIBE`.
- The frame exceeds the limits on the number of headers, header length, or body size that the server sets.
- The broker or the broker relay returns an error that prevents the server from continuing to process the connection.

Example of a version negotiation error:

~~~text
ERROR
message:version-not-supported
content-type:text/plain;charset=utf-8

Supported protocol versions are 1.1 and 1.2.\0
~~~

Example of a `SEND` error with a receipt:

~~~text
SEND
destination:/queue/unknown
receipt:send-42

hello\0

ERROR
message:destination-unavailable
receipt-id:send-42
content-type:text/plain;charset=utf-8

The destination cannot be resolved.\0
~~~

In the second example, `receipt-id` helps the client identify the frame that caused the error. After `ERROR`, the server closes the connection; the client must create a new connection/STOMP session if it wants to continue.

## 4. ERROR, RECEIPT, and ACK have different meanings

You should not treat these frames as equivalent ways of confirming:

| Frame | Who sends it? | What is confirmed | Does it end the connection? |
| --- | --- | --- | --- |
| `RECEIPT` | Server | The server has processed a client frame that requested a receipt; a receipt is also a cumulative confirmation that the earlier frames have been received by the server | No |
| `ERROR` | Server | The server encountered a STOMP-level error and cannot continue the connection according to the protocol | Yes; the server must close the connection after the frame |
| `ACK` | Client | The client confirms it has consumed the message according to the subscription acknowledgement mode | No |
| `NACK` | Client | The client declines to acknowledge the message according to the acknowledgement mode | No, but the broker may redeliver or handle it according to its policy |

`RECEIPT` does not prove that the consumer-side business processing has completed. STOMP 1.2 describes a receipt as confirmation that the server has processed the corresponding frame and as a cumulative confirmation that the earlier frames have been received; those earlier frames may still not have been fully processed.

If the server cannot process a frame that has `receipt`, it can send `ERROR` with the corresponding `receipt-id` and then close the connection. The client needs to handle the receipt error and the connection state; it must not wait for a successful `RECEIPT` after an `ERROR` for the same operation.

Spring `StompSession.send(...)` and `subscribe(...)` can return a `StompSession.Receiptable`. When a `TaskScheduler` is configured, the client can register callbacks for receipt success/failure and receipt timeout. A receipt timeout is a client-side timeout waiting for confirmation; it does not by itself prove that the broker rejected the frame.

## 5. ERROR ends the STOMP session and connection

A STOMP session holds protocol state such as the negotiated version, subscription IDs, transaction IDs, and related information. When the server sends `ERROR`, the STOMP connection is closed; the current session state can no longer be used.

With STOMP over WebSocket, the server sends the `ERROR` frame over the WebSocket and then closes the WebSocket connection. On the client side, you can observe both the content of the `ERROR` and the transport close event. Do not send any more frames on the old session after receiving `ERROR`.

The STOMP specification has a connection lingering rule: the server can close/reset the socket very quickly after the last frame. Therefore, the client may not have time to receive the final `ERROR` or `RECEIPT` before the transport is closed. The application must handle both paths: receiving a clear `ERROR`, and receiving only a transport close/error.

Do not confuse a STOMP session with an HTTP login session. The end of a STOMP/WebSocket connection does not necessarily delete the HTTP session or the logged-in account. The client can open a new WebSocket and perform the STOMP `CONNECT` again with appropriate authentication information.

## 6. How Spring handles errors on the server side

With `@EnableWebSocketMessageBroker`, Spring receives a WebSocket message, decodes the STOMP frame, converts it into a Spring `Message<?>`, and sends it into the `clientInboundChannel`. Messages with the `/app` destination can be routed to `@MessageMapping`; `/topic` or `/queue` messages can be routed to the broker.

`StompSubProtocolHandler` manages the conversion between WebSocket and STOMP. When an error occurs while decoding or processing a client message, Spring uses `StompSubProtocolErrorHandler` to prepare the error message sent back to the client.

`StompEndpointRegistry.setErrorHandler(...)` lets you replace the default handler. `StompSubProtocolErrorHandler` has two main handling points:

- `handleClientMessageProcessingError(clientMessage, ex)`: handles an error that arises when Spring processes a client message; it can create or prevent sending an `ERROR`.
- `handleErrorMessageToClient(errorMessage)`: handles an error message sent from the server side to the client, for example an error from the broker relay or an external broker.

By default, Spring creates a STOMP `ERROR` frame for an error in processing a client message. Because STOMP requires the server to close the connection after `ERROR`, the client must reconnect if it wants to continue.

### 6.1. Customizing the ERROR frame and masking internal information

Do not send stack traces, SQL, table names, internal paths, credentials, or infrastructure information in the error body. Record the detailed cause in a controlled server log and return an error code with a safe message to the client.

Spring Framework 6.2 configuration example:

~~~java
package com.example.messaging;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.messaging.StompSubProtocolErrorHandler;

@Configuration
@EnableWebSocketMessageBroker
public class StompServerErrorConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/stomp");
        registry.setErrorHandler(new SanitizingErrorHandler());
    }

    private static final class SanitizingErrorHandler
            extends StompSubProtocolErrorHandler {

        @Override
        protected Message<byte[]> handleInternal(
                StompHeaderAccessor errorHeaders,
                byte[] errorPayload,
                Throwable cause,
                StompHeaderAccessor clientHeaders) {

            byte[] body = "Request could not be processed"
                    .getBytes(StandardCharsets.UTF_8);
            errorHeaders.setMessage("Request failed");
            errorHeaders.setNativeHeader("error-code", "PROCESSING_FAILED");
            errorHeaders.setContentType(MimeTypeUtils.TEXT_PLAIN);
            errorHeaders.setContentLength(body.length);
            return MessageBuilder.createMessage(body, errorHeaders.getMessageHeaders());
        }
    }
}
~~~

The handler keeps the `ERROR` command that Spring has already created, replaces the message/body with safe content, and adds the `error-code` header. If you need to investigate, record `cause` in the server log together with the session/request ID; do not pass the exception through to the client as is.

The example above only configures a simple endpoint and broker to illustrate the error hook. A real application needs to add authentication, authorization, an origin policy, and a broker relay or broker appropriate to the infrastructure.

### 6.2. When does the handler return null?

`handleClientMessageProcessingError(...)` can return `null` to prevent Spring from sending the `ERROR` frame. The Spring Javadoc gives the example of sending a notification message through the broker, for example to a user destination.

Only do this when the error is a business error and the session can safely continue. In that case, send a `MESSAGE` with a structure such as `code`, `message`, `correlationId`, and `retryable` to `/user/queue/errors`, and let the client display the error. If the frame is syntactically wrong or the protocol state can no longer be trusted, you should not hide the error and continue using the connection.

## 7. Business errors and @MessageExceptionHandler

A business error such as “the order has been cancelled” or “the user does not have permission to join the chat room” usually does not need to end the STOMP session. Return the error as an application message.

Example:

~~~java
public record ApplicationError(
        String code,
        String message,
        String correlationId) {
}

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    public void send(ChatInput input) {
        if (!isAllowed(input)) {
            throw new ChatRejectedException("Chat is unavailable");
        }
        // Process the valid message.
    }

    @MessageExceptionHandler(ChatRejectedException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ApplicationError handleChatRejected(ChatRejectedException ex) {
        return new ApplicationError(
                "CHAT_REJECTED",
                "Your message could not be sent",
                null);
    }
}
~~~

The client receives a STOMP `MESSAGE` on the user destination containing an `ApplicationError`; the connection remains active. `broadcast=false` limits the response to the session that caused the error when the user has multiple sessions. You need to configure the user destination and the corresponding broker.

`@MessageExceptionHandler` handles exceptions that arise in a message handler method. It does not replace the protocol error handler for frame parse errors, negotiation errors, or errors at the transport layer. Choose the mechanism according to the type of error:

| Situation | How to handle it |
| --- | --- |
| Wrong STOMP syntax, invalid command, unable to create a subscription | STOMP `ERROR`, close the connection |
| The broker rejects the frame or the protocol state is faulty | STOMP `ERROR` according to the server/provider behavior |
| Business validation or rejecting an operation while the session is still valid | `@MessageExceptionHandler` or an application `MESSAGE` |
| WebSocket/network is lost | Transport close/error callback; there is not necessarily a STOMP `ERROR` |

## 8. The Spring client receives an ERROR frame via StompSessionHandler

`StompSessionHandler` extends `StompFrameHandler`, so it receives the STOMP `ERROR` frame. `StompSessionHandlerAdapter.getPayloadType(...)` returns `String.class` by default for the payload of an `ERROR` frame. `handleFrame(...)` is the callback to read the error headers and body.

Three callbacks to distinguish:

| Callback | When is it called? | What is it used for? |
| --- | --- | --- |
| `handleFrame(headers, payload)` | Receiving a STOMP frame such as `ERROR` | Read the `message` header, `receipt-id`, a custom error code, and the body |
| `handleException(session, command, headers, payload, exception)` | An error while processing a frame, for example a converter error or the application's `StompFrameHandler` throws an exception | Record a processing error on the client |
| `handleTransportError(session, exception)` | A transport-layer error such as I/O, encode/decode, or `ConnectionLostException` | Mark the connection as lost and start an appropriate reconnect procedure |

Client handler example:

~~~java
package com.example.messaging;

import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;

public class ClientErrorHandler extends StompSessionHandlerAdapter {

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        System.err.println("STOMP ERROR: " + headers.getFirst("message"));
        System.err.println("errorCode=" + headers.getFirst("error-code"));
        System.err.println("body=" + payload);
        // Mark the current session as no longer usable.
    }

    @Override
    public void handleException(
            StompSession session,
            StompCommand command,
            StompHeaders headers,
            byte[] payload,
            Throwable exception) {
        System.err.println(
                "Frame handler failed: " + exception.getClass().getSimpleName());
    }

    @Override
    public void handleTransportError(StompSession session, Throwable exception) {
        System.err.println(
                "STOMP transport failed: " + exception.getClass().getSimpleName());
        // Put the session into the disconnected state and schedule a reconnect.
    }
}
~~~

Client initialization example:

~~~java
WebSocketStompClient client =
        new WebSocketStompClient(new StandardWebSocketClient());
client.setMessageConverter(new StringMessageConverter());

client.connectAsync(
        "ws://localhost:8080/stomp",
        new ClientErrorHandler());
~~~

When `ERROR` is received, `handleFrame` may be called before the underlying WebSocket closes. After that, the client may also receive `handleTransportError` or the transport close event. Make the logic that marks the session disconnected and the cleanup idempotent so that the two callbacks do not trigger two reconnects.

`handleException` is not the callback that receives the STOMP `ERROR` from the server. It is for exceptions when the client processes a frame. `handleTransportError` also does not mean “the server sent ERROR”; it reports an error at the connection/codec layer.

## 9. How Spring detects that a STOMP session has ended

On the server, Spring publishes `SessionDisconnectEvent` when a STOMP session ends. The client may have sent `DISCONNECT`, or the WebSocket session may have been closed and Spring ends the STOMP session on its own.

Listener example:

~~~java
@Component
public class StompSessionLifecycleListener {

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        String sessionId = event.getSessionId();
        // Release the subscriptions/resources attached to the session.
        // The cleanup operation must be safe if the event is published multiple times.
    }
}
~~~

`SessionDisconnectEvent` can be published multiple times for the same session in some situations. Cleanup must be idempotent: delete state by session ID, check for existence before releasing, and do not emit repeated side effects.

With the broker relay, Spring can automatically reconnect the system connection to the broker when the broker is temporarily down. Client connections are not restored automatically; the client needs to reconnect on its own. `BrokerAvailabilityEvent` indicates whether the broker relay is available so that the server avoids sending messages when the broker is unavailable.

## 10. Reconnecting after ERROR or a transport failure

Because `ERROR` ends the connection, a reconnect must create a new WebSocket connection and STOMP session. The usual procedure:

1. Mark the old session as disconnected; stop sending frames on that session.
2. Close and release the client resources attached to the old session.
3. Classify the error: protocol/auth/configuration or a temporary network/broker error.
4. If it can be recovered, wait using exponential backoff with jitter and then open a new transport.
5. Send `CONNECT` again, authenticate, and wait for `CONNECTED`.
6. Re-register the necessary subscriptions.
7. Restore the application state and continue sending commands according to the retry policy.

Do not reconnect continuously at a high rate when the error is `version-not-supported`, wrong credentials, or denied access. Configuration/auth errors need to be fixed before retrying.

### 10.1. Do not retry SEND blindly

If the connection is lost after the client sends `SEND` but before it receives `RECEIPT`, the client may not know whether the server processed the frame. Resending a command that has side effects can create duplicate effects.

For a business command, attach a stable `requestId` or `idempotencyKey` in the payload/header. The server stores state by key and returns the earlier result when it receives the same command again. Use `receipt` to know that the server processed the frame at the STOMP level; use an event/result message or a status API to know that the business has completed.

### 10.2. Restoring subscriptions

A subscription ID belongs to the current connection. After a reconnect, the client must create a new subscription and manage the new handle. Do not assume the old subscription exists on its own on the new connection.

If the consumer uses manual acknowledgement, you need to determine whether the broker can redeliver messages that have not been ACK/NACKed after the connection is lost. The consumer must be idempotent and must not use the old subscription ID on the new session.

## 11. Graceful DISCONNECT and ERROR are different

The client can close the socket directly, but then there is no guarantee that the server received all earlier frames. To disconnect in a controlled way according to STOMP 1.2:

~~~text
DISCONNECT
receipt:disconnect-77

\0

RECEIPT
receipt-id:disconnect-77

\0
~~~

The client waits for `RECEIPT` and then closes the socket. After sending `DISCONNECT`, the client must not send any more STOMP frames.

A graceful disconnect is a proactive operation, with a receipt confirming that the server received/processed the disconnect frame. `ERROR` is the server reporting an error and forcing the connection to close. The two situations can both lead to `SessionDisconnectEvent`, but the causes and the client-side handling differ.

## 12. Heartbeat, WebSocket close, and errors without an ERROR frame

Not every connection failure has an `ERROR` frame. For example:

- A TCP reset or the network suddenly being lost.
- The WebSocket container closing the socket due to a timeout or shutdown.
- A heartbeat not arriving within the negotiated interval.
- A proxy/load balancer closing an idle connection.
- The STOMP decoder on the client detecting an error and closing the transport.
- The server process stopping before it could send the final frame.

STOMP heartbeat is used to detect that a peer is no longer active. When the client does not receive data/heartbeat within the agreed threshold, the client can consider the connection dead and close it. This is transport liveness detection, not a STOMP `ERROR` frame.

Therefore, client code needs both `handleFrame` for ERROR and `handleTransportError`/transport close for errors without ERROR. Do not rely solely on the content of the error body to detect that the session has ended.

## 13. Security and error content

An error frame can travel to a browser or a client outside the trust boundary. Treat its headers and body as public data:

- Use stable error codes such as `AUTH_REQUIRED`, `DESTINATION_DENIED`, `INVALID_FRAME`, or `PROCESSING_FAILED`.
- Keep messages brief and do not reveal stack traces, SQL, broker hosts, internal queues, file paths, tokens, or credentials.
- Do not echo the entire input frame if the frame may contain secrets or personal data.
- Log detailed exceptions on the server side, attach a correlation ID/session ID, and restrict access to the logs.
- Limit the size of the error body; avoid returning a large payload or data controlled by an attacker.
- Do not put a passcode or access token in the error log.

For an application error `MESSAGE`, the same principles apply. The client should not display internal errors verbatim; use the error code to choose appropriate content and a handling approach.

## 14. Java 17 example: decoding an ERROR frame with StompDecoder

This example uses Spring Messaging's `StompDecoder` to parse a complete ERROR frame. The program does not open a WebSocket or a broker; it checks the correct structure of a STOMP frame and how Spring extracts the command/headers/body.

Project structure:

~~~text
stomp-error-frame-demo/
  pom.xml
  src/main/java/com/example/stomp/StompErrorFrameDemo.java
  src/main/java/com/example/stomp/StompServerErrorConfiguration.java
  src/main/java/com/example/stomp/ClientErrorHandler.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>stomp-error-frame-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-websocket</artifactId>
            <version>${spring.version}</version>
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

`src/main/java/com/example/stomp/StompErrorFrameDemo.java`:

~~~java
package com.example.stomp;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompDecoder;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public final class StompErrorFrameDemo {
    private StompErrorFrameDemo() {
    }

    public static void main(String[] args) {
        String body = "The destination is unavailable.";
        String wire = "ERROR\n"
                + "message:destination-unavailable\n"
                + "receipt-id:send-42\n"
                + "content-type:text/plain;charset=utf-8\n"
                + "content-length:" + body.getBytes(StandardCharsets.UTF_8).length + "\n"
                + "\n"
                + body
                + '\0';

        List<Message<byte[]>> frames = new StompDecoder().decode(
                ByteBuffer.wrap(wire.getBytes(StandardCharsets.UTF_8)));
        if (frames.size() != 1) {
            throw new IllegalStateException(
                    "Expected one complete STOMP frame, got " + frames.size());
        }

        Message<byte[]> frame = frames.get(0);
        StompHeaderAccessor headers = StompHeaderAccessor.wrap(frame);
        if (headers.getCommand() != StompCommand.ERROR) {
            throw new IllegalStateException(
                    "Expected ERROR frame, got " + headers.getCommand());
        }

        System.out.println("command=" + headers.getCommand());
        System.out.println("message=" + headers.getMessage());
        System.out.println("receiptId=" + headers.getReceiptId());
        System.out.println("body=" +
                new String(frame.getPayload(), StandardCharsets.UTF_8));
    }
}
~~~

`StompServerErrorConfiguration.java` and `ClientErrorHandler.java` respectively illustrate the server error handler configuration and the client callbacks in sections 6.1 and 8; put them in the same package as in the project structure in order to compile the whole example.

Run with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=com.example.stomp.StompErrorFrameDemo"
~~~

Stdout:

~~~text
command=ERROR
message=destination-unavailable
receiptId=send-42
body=The destination is unavailable.
~~~

The example uses a `content-length` computed from the number of UTF-8 bytes of the body and terminates the frame with NUL. `StompDecoder` returns a Spring `Message<byte[]>`; `StompHeaderAccessor` reads the command and the STOMP headers. When a frame is incomplete, the decoder can return an empty list and the caller must buffer the remainder before decoding further.

## 15. Common mistakes

- **Treating ERROR as an ordinary MESSAGE:** a STOMP `ERROR` is a protocol error and the server must close the connection after sending it.
- **Continuing to send frames on the old session:** after ERROR, treat the session as ended and create a new connection.
- **Confusing the ERROR frame with a WebSocket close reason:** a WebSocket can close without a STOMP ERROR; handle the transport callbacks as well.
- **Using ERROR for every validation error:** business errors should usually return an application MESSAGE so that the session remains active.
- **Thinking that `@MessageExceptionHandler` catches parse/protocol errors:** it handles exceptions in the message handler; protocol errors need a handler at the STOMP layer.
- **Putting stack traces or SQL in the body:** the client can see them; return an error code and a safe message.
- **Ignoring `receipt-id`:** when there is a receipt, this header helps identify the frame that caused the error.
- **Treating RECEIPT as business processing being complete:** a receipt only confirms frame processing at the server/protocol level.
- **Waiting for the ERROR frame to always arrive before the socket closes:** connection lingering can cause the final frame to be lost.
- **Implementing only `handleTransportError`:** this callback does not replace `handleFrame` for reading the ERROR frame.
- **Confusing `handleException` with the ERROR frame:** this is an exception when the client processes a frame/converter or callback.
- **Not reconnecting/resubscribing:** a new connection does not carry over the old subscription IDs.
- **Retrying SEND without an idempotency key:** an operation with side effects can run repeatedly when the result of the previous send is undetermined.
- **Non-idempotent session cleanup:** `SessionDisconnectEvent` can be published multiple times.
- **Not classifying transient errors versus configuration errors:** reconnecting endlessly with wrong credentials or an incompatible protocol version creates unnecessary load.

## 16. Operations checklist

1. Does the server send `ERROR` with a brief `message` header and a safe body?
2. If the error relates to a frame that has `receipt`, does `receipt-id` match the receipt value?
3. Does the body have `content-type`, a `content-length` equal to the number of UTF-8 bytes, and the NUL terminator?
4. Does the server close the connection after ERROR according to STOMP 1.2?
5. Does the client stop sending on the old session as soon as it receives ERROR?
6. Does the client distinguish `handleFrame`, `handleException`, and `handleTransportError`?
7. Does the application distinguish protocol errors from business errors that need an application MESSAGE?
8. Does `StompSubProtocolErrorHandler` mask sensitive information?
9. Is there enough detailed server logging with a session ID/correlation ID without leaking secrets?
10. Is transport close handled when the final ERROR frame does not reach the client?
11. Does the reconnect have backoff, jitter, and classification of permanent/transient errors?
12. Does the client send CONNECT/authentication and re-register subscriptions after a reconnect?
13. Do commands with side effects have an idempotency key so they can be retried safely?
14. Is the `SessionDisconnectEvent` cleanup idempotent?
15. Are malformed frame, version mismatch, destination denied, broker outage, heartbeat timeout, and socket reset tested?

## 17. Key takeaways

STOMP `ERROR` is a server frame used to report an error at the protocol level; according to STOMP 1.2, the server must close the connection immediately after sending this frame. The `message` header briefly describes the error, the body can contain details, and `receipt-id` can link the error to a client frame that requested a receipt. The Spring server uses `StompSubProtocolErrorHandler` to create, customize, or prevent sending ERROR; if you want the session to continue after a business error, send an application `MESSAGE` using `@MessageExceptionHandler` or a user destination. The Spring client receives ERROR through `StompSessionHandler.handleFrame`; `handleException` handles callback/conversion errors and `handleTransportError` handles transport errors. After ERROR, create a new STOMP session, authenticate, and subscribe again; retrying a command with side effects must use an idempotency key.

### References

- [STOMP 1.2 Specification — ERROR frames and connection behavior](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework 6.2 — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp.html)
- [Spring Framework 6.2 — Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
- [Spring Framework 6.2.14 — StompSubProtocolErrorHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolErrorHandler.html)
- [Spring Framework 6.2.14 — StompSessionHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/simp/stomp/StompSessionHandlerAdapter.html)
- [Spring Framework 6.2.14 — StompDecoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html)