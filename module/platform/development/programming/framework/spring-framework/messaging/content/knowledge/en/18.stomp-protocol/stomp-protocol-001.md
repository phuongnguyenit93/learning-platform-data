# STOMP frame structure: command, headers, and body

## Learning objectives

After this lesson, you can:

- Describe the wire-format structure of a STOMP frame according to STOMP 1.2.
- Distinguish the command, the header section, the body, and the terminating NUL byte.
- Read the CONNECT, CONNECTED, SEND, SUBSCRIBE, MESSAGE, ACK, RECEIPT, and ERROR frames.
- Understand how to use content-length and content-type, and how to count the bytes of a body.
- Encode and decode header values according to the STOMP 1.2 escape rules.
- Handle repeated headers, heartbeats, and multiple frames on the same stream connection.
- Distinguish a STOMP frame from a WebSocket frame and a Spring Message.
- Trace how Spring WebSocket/STOMP converts a frame into an internal message.
- Build a correctly formatted SEND frame using Java 17 and UTF-8.

## 1. What is STOMP?

STOMP stands for Simple Text Oriented Messaging Protocol. It is a lightweight messaging protocol that uses frames to exchange data between a client and a message server/broker. STOMP can run over a reliable bidirectional connection such as TCP or WebSocket.

STOMP is designed to be easy to implement across many languages and platforms. A client can send a message with a SEND frame, subscribe to receive messages with SUBSCRIBE, and then receive data from the server through MESSAGE frames.

STOMP is a protocol at the wire-format layer. It specifies the frame structure and the common commands, but leaves it to the broker to decide the meaning of a destination, as well as how messages are stored, delivered, retried, and made durable. For example, names such as /queue/orders or /topic/orders are common conventions, but the exact syntax and semantics depend on the STOMP server.

This lesson focuses on STOMP 1.2. When working with a specific broker or client, you need to check the STOMP version that the two sides negotiate and the server's own extensions.

## 2. General structure of a STOMP frame

A frame has four parts, in this order:

1. Command: the name of the action, for example SEND or SUBSCRIBE.
2. Header section: zero or more key:value lines.
3. Blank line: marks the end of the headers and the start of the body.
4. Body: the message data, followed by a NUL byte that terminates the frame.

General form:

~~~text
COMMAND
header1:value1
header2:value2

Body^@
~~~

In the example, the ^@ notation represents a single NUL byte with the value 0x00. This is an illustrative notation used in documentation; it is not the two characters caret and @ being sent over the network.

A real SEND frame:

~~~text
SEND
destination:/queue/orders
content-type:text/plain
content-length:9

Xin chào^@
~~~

The frame above has:

- The command is SEND.
- The destination header indicates the receiving destination.
- The content-type header describes the format of the body.
- The content-length header states that the body is 9 UTF-8 bytes long.
- The blank line separates the headers from the body.
- The body is the string Xin chào.
- The NUL byte terminates the frame.

A frame is not a single line of text. It is a structured sequence of bytes. A connection can carry many frames one after another.

## 3. Command line and EOL

The command is on the first line of the frame. The command is terminated by an EOL (end-of-line).

In STOMP 1.2, the EOL is:

- LF: the line feed byte, value 10.
- CRLF: the carriage return byte 13 followed by the line feed byte 10.

STOMP 1.2 allows both LF and CRLF. LF is the form commonly seen in examples and in simple clients.

Example:

~~~text
SEND\n
destination:/queue/orders\n
\n
hello^@
~~~

Here \n represents an LF byte. In the real wire-format, the backslash and the letter n do not appear; they only help illustrate the line breaks.

The command and header names are case-sensitive. SEND and send are not the same command. destination and Destination are also two different header names.

A parser must not arbitrarily convert a command to lowercase or uppercase, because that changes the meaning of the frame.

## 4. Header section

After the command come zero or more header lines. Each header has this structure:

~~~text
key:value
~~~

The first colon separates the header name from the value. Each header line ends with an EOL.

Example:

~~~text
SEND
destination:/queue/orders
content-type:application/json
content-length:10
receipt:send-186

{"id":186}^@
~~~

Headers can carry protocol control information or message metadata.

Common headers:

| Header | Meaning |
|---|---|
| destination | The destination that SEND or SUBSCRIBE targets |
| content-type | The MIME type of the body |
| content-length | The number of bytes in the body |
| receipt | Asks the server to send a RECEIPT when it has processed the frame |
| id | The subscription ID or transaction ID, depending on the command |
| ack | The acknowledgement mode of the subscription |
| transaction | The STOMP transaction ID |
| message-id | The message ID supplied by the server in a MESSAGE |
| subscription | The ID of the subscription that receives the MESSAGE |
| ack (in MESSAGE) | The token used for ACK/NACK when the subscription requires acknowledgement |
| receipt-id | The matching receipt value in a RECEIPT |

A header can be a standard STOMP header or a header defined by the application/broker. Custom headers are commonly used to carry a correlation ID, an event type, a tenant, or metadata used for message filtering.

### 4.1. The blank line that ends the headers

A blank EOL line marks the boundary between the headers and the body.

Example:

~~~text
SEND
destination:/queue/a
content-type:text/plain

hello^@
~~~

The blank line after content-type is not an empty header. It is the mandatory delimiter between the header section and the body.

If there are no headers, the frame still has a command line followed by a blank EOL:

~~~text
DISCONNECT

^@
~~~

A parser must recognize this blank line before reading the body. If it mistakes it for the body, the parser will lose its position and may be unable to decode the next frame.

### 4.2. Do not trim header values on your own

According to STOMP 1.2, clients and servers must not arbitrarily trim or add whitespace at the start/end of a header. Whitespace can be part of a value sent by the application.

For example, the value:

~~~text
x-label:  urgent  
~~~

has two spaces at the start and at the end of the value. A parser must not remove them on its own.

If the application wants to normalize the value, do it at the business logic layer after the frame has been decoded, without changing the wire-format.

### 4.3. Repeated headers

STOMP 1.2 allows a frame to have multiple headers with the same name. When receiving duplicate headers, the client/server SHOULD use the value of the header that appears first. The later values may be kept as a history of changes or ignored.

Example:

~~~text
MESSAGE
foo:World
foo:Hello

^@
~~~

According to the STOMP 1.2 rule, the value of foo that is used is World.

This point matters when a broker adds headers or updates metadata in a store-and-forward topology. Applications should not assume that duplicate headers are always merged into a list, or that the last value wins.

If a header needs to have multiple values, use a clear convention at the application layer or a header with a suitable format, instead of relying on the broker's own behavior.

## 5. Header escaping in STOMP 1.2

A header value cannot directly contain certain frame delimiter characters such as CR, LF, and the colon. STOMP 1.2 uses escape sequences to represent them.

For ordinary frames, the escape rules are:

| Original character | Form on the wire |
|---|---|
| Backslash \ | \\ |
| Carriage return | \r |
| Line feed | \n |
| Colon : | \c |

Example of an original header value:

~~~text
line1:ok
line2\done
~~~

When encoded as a header value:

~~~text
note:line1\cok\nline2\\done
~~~

When decoding, the parser reverses the escape sequences to restore the original value.

Undefined escape sequences, for example \t, are protocol errors in STOMP 1.2 and must be handled as a protocol error.

There is a compatibility exception: CONNECT and CONNECTED do not apply the escape rules for CR, LF, and colon the way other frames do. This is to maintain compatibility with STOMP 1.0. When writing an encoder/decoder, handle the frame type and the protocol version correctly.

Practical rules:

- When encoding, escape the backslash first, and only then escape CR, LF, and colon.
- When decoding, accept only the escape sequences defined by STOMP 1.2.
- Do not trim whitespace in headers.
- Do not escape the body on your own; this rule applies to the header section.

If you escape the backslash last, a backslash that was just produced by the encoding process may be escaped again and corrupt the value.

## 6. Body section

The body starts immediately after the blank EOL line and ends with a NUL byte (0x00).

Only three frame types in STOMP 1.2 are allowed to have a body:

- SEND: the client sends the message content.
- MESSAGE: the server delivers a message to a subscriber.
- ERROR: the server may send content that explains the error.

Other frames such as CONNECT, CONNECTED, SUBSCRIBE, ACK, RECEIPT, and DISCONNECT must not have a body according to the specification.

A body can be text or binary. STOMP is text-oriented, but the payload is not required to be plain text.

JSON body example:

~~~text
SEND
destination:/queue/trade
content-type:application/json

{"action":"BUY","ticker":"MMM"}^@
~~~

A binary body example can contain a NUL byte in the middle. In that case the parser cannot use the first NUL byte as the terminator; content-length must be present so that the exact number of body bytes is known.

## 7. content-length: count bytes, not characters

content-length is the length of the body measured in octets (bytes). It is not the number of characters, not the number of code points, and not necessarily equal to String.length() in Java.

For a UTF-8 body containing non-ASCII characters, the number of bytes can differ from the number of characters.

Example body:

~~~text
Xin chào
~~~

In Java:

- String.length() returns 8 UTF-16 code units.
- UTF-8 encoding produces 9 bytes.
- Therefore content-length must be 9.

Example frame:

~~~text
SEND
destination:/queue/a
content-type:text/plain;charset=UTF-8
content-length:9

Xin chào^@
~~~

If the body contains a NUL byte inside it, content-length is mandatory. The parser must read exactly the declared number of bytes, and then still read the NUL byte that terminates the frame.

If content-length is absent, the parser looks for the first NUL byte to determine the end of the body. This approach does not work when the payload contains a NUL byte.

### 7.1. content-type

When a frame has a body, SEND, MESSAGE, and ERROR SHOULD send content-type so that the receiver knows how to interpret the payload.

content-type is a MIME type, for example:

- text/plain
- application/json
- application/xml
- application/octet-stream

For textual content, UTF-8 is recommended to improve compatibility. If you use a different charset, declare it explicitly in the MIME type, for example text/plain;charset=UTF-16.

If content-type is absent, the receiver should treat the body as a binary blob according to the specification.

### 7.2. The NUL byte is not counted in content-length

content-length counts only the bytes of the body. The NUL byte that terminates the frame comes after the body and is not included in the content-length value.

Example:

~~~text
content-length:3

abc^@
~~~

The body is 3 bytes long: a, b, c. The NUL byte is the fourth byte after the blank line, used to terminate the frame.

## 8. Terminating a frame with NUL

The NUL byte with the value 0x00 is the frame terminator. After the NUL, the specification allows zero or more additional EOLs.

The ^@ notation in this document represents the NUL byte. Do not send the two characters ^ and @.

Frames can be sent back to back on the same connection:

~~~text
SEND
destination:/queue/a

first^@SEND
destination:/queue/a

second^@
~~~

In the example, after the NUL byte of the first frame, the second frame begins immediately with the SEND command. There may be additional EOLs after the NUL, but the parser must skip exactly the right number of EOLs according to the grammar.

NUL is an important delimiter byte. Do not use a newline to terminate the body, because the body can contain multiple lines or binary data.

## 9. How a parser reads a frame

STOMP runs over a bidirectional stream such as TCP. A single socket read is not guaranteed to return exactly one whole frame. A frame can be split across several reads; a single read can also contain several frames.

A streaming parser usually follows these steps:

1. Read the command up to the EOL.
2. Read each header line up to the EOL.
3. On reaching a blank EOL, end the header section.
4. Check content-length, if present.
5. If content-length is present, read exactly that many octets of body, then check for the terminating NUL byte.
6. If content-length is absent, read the body up to the first NUL byte.
7. Skip any additional EOLs after the NUL, if present.
8. Continue parsing the next frame in the buffer.

When the body has a NUL inside it, content-length tells the parser which NUL belongs to the body and which NUL terminates the frame.

The parser also needs limits on:

- The number of headers per frame.
- The length of each header line.
- The body size.
- The time to wait for an incomplete frame.
- The number of buffered bytes held for a connection.

The specification allows a server to set size limits to avoid excessive memory consumption. If a limit is exceeded, the server may return an ERROR and close the connection.

Do not write a production parser by calling readLine() for the whole frame and then assembling the body into a String. That approach corrupts binary payloads, does not honor content-length in bytes, and may misread the next frame.

## 10. Connection frames: CONNECT, STOMP, and CONNECTED

The client starts a STOMP session with CONNECT or STOMP. The server returns CONNECTED if it accepts.

Client example:

~~~text
CONNECT
accept-version:1.2
host:broker.example
heart-beat:10000,10000

^@
~~~

Server example:

~~~text
CONNECTED
version:1.2
heart-beat:10000,10000
session:session-186

^@
~~~

In STOMP 1.2, the client MUST send:

- accept-version: the protocol versions the client supports.
- host: the name of the virtual host the client wants to connect to.

The server returns version to confirm the chosen version. The two sides use the highest version that both support.

Common optional headers:

- login: the user name.
- passcode: the password or credential, depending on the server configuration.
- heart-beat: the heartbeat parameters.
- session: the session ID supplied by the server.
- server: information about the server.

Do not write a real passcode into logs or production examples. STOMP frames can travel over the network; use TLS and a suitable authentication mechanism.

STOMP command and header names are case-sensitive. CONNECT and STOMP are two connection commands; a STOMP 1.2 server MUST handle STOMP the same way as CONNECT.

## 11. Common client commands

| Command | Purpose | Important headers |
|---|---|---|
| CONNECT / STOMP | Opens a STOMP session | accept-version, host |
| SEND | Sends a message | destination |
| SUBSCRIBE | Subscribes to receive messages | destination, id, ack |
| UNSUBSCRIBE | Cancels a subscription | id |
| ACK | Acknowledges that a message has been processed | id |
| NACK | Reports that a message has not been processed | id |
| BEGIN | Starts a STOMP transaction | transaction |
| COMMIT | Commits a transaction | transaction |
| ABORT | Rolls back a transaction | transaction |
| DISCONNECT | Closes the session | receipt (optional) |

### 11.1. SEND

SEND requires the destination header. The body contains the content sent to the destination.

~~~text
SEND
destination:/queue/orders
content-type:application/json
content-length:10

{"id":186}^@
~~~

Custom application headers can be added to SEND. The broker may forward those headers to the subscriber's MESSAGE frame.

STOMP treats a destination as an opaque string. The protocol does not require that the names /queue or /topic have specific semantics. Check the broker documentation.

### 11.2. SUBSCRIBE

SUBSCRIBE registers to receive messages from a destination:

~~~text
SUBSCRIBE
id:orders-sub-1
destination:/queue/orders
ack:client-individual

^@
~~~

id is a subscription identifier that is unique within the same connection. The server uses this ID to link MESSAGE and UNSUBSCRIBE.

The ack header specifies the acknowledgement mode:

- auto: the client does not send ACK; the server considers the message received when it is sent to the client.
- client: ACK is cumulative; it acknowledges the specified message and all earlier messages in the subscription.
- client-individual: ACK/NACK applies only to the corresponding message.

If ack is not specified, the default is auto.

### 11.3. UNSUBSCRIBE

UNSUBSCRIBE needs the ID of the subscription that was created:

~~~text
UNSUBSCRIBE
id:orders-sub-1

^@
~~~

After the server processes it, the connection no longer receives messages through that subscription.

### 11.4. ACK and NACK

When a subscription uses client or client-individual, MESSAGE has an ack header. The client sends ACK or NACK with that value:

~~~text
ACK
id:ack-token-186

^@
~~~

~~~text
NACK
id:ack-token-187

^@
~~~

In STOMP 1.2, the id header of ACK/NACK must match the ack value in MESSAGE, not message-id. You can add transaction to attach the acknowledgement to a STOMP transaction.

NACK reports that the client has not processed the message. The broker may redeliver it, discard it, or put it into a dead-letter queue; the exact behavior depends on the server.

## 12. Server frames: CONNECTED, MESSAGE, RECEIPT, and ERROR

The server sends CONNECTED after a successful connection. After that, the server may send MESSAGE, RECEIPT, or ERROR.

### 12.1. MESSAGE

MESSAGE delivers content to a subscription:

~~~text
MESSAGE
destination:/queue/orders
message-id:msg-186
subscription:orders-sub-1
content-type:application/json
content-length:10

{"id":186}^@
~~~

Required headers:

- destination: the destination the message was sent to.
- message-id: the unique ID of the message.
- subscription: the ID of the subscription that is receiving the message.
- ack: present when the subscription uses explicit acknowledgement.

The subscription header in MESSAGE must match the ID of the corresponding SUBSCRIBE.

### 12.2. RECEIPT

A client can request a receipt with the receipt header on a client frame, except CONNECT. The server returns RECEIPT with a receipt-id that has the same value.

Example the client sends:

~~~text
SEND
destination:/queue/orders
receipt:send-186

order-186^@
~~~

The server returns:

~~~text
RECEIPT
receipt-id:send-186

^@
~~~

RECEIPT confirms that the server has processed the corresponding frame at the protocol level. Because STOMP runs over a stream, a receipt is also a cumulative confirmation that the earlier frames have been received by the server. However, a receipt does not mean the message has been fully processed by a consumer or that a business transaction has been committed.

If business-level confirmation is needed, the application must define a response/event at the business layer.

### 12.3. ERROR

The server may send ERROR when a frame is syntactically wrong, is missing a required header, or the command cannot be processed.

~~~text
ERROR
message:malformed frame
content-type:text/plain

Missing required destination header^@
~~~

ERROR can contain a body that describes the error. According to STOMP 1.2, the server sends ERROR and then closes the connection. The client should read the error, release resources, and reconnect according to an appropriate policy.

Do not treat ERROR as an ordinary response after which the connection is certain to remain active.

## 13. Transactions in STOMP

STOMP defines the BEGIN, COMMIT, and ABORT commands. The transaction ID is used in the SEND, ACK, and NACK frames to attach the operation to a transaction.

Example:

~~~text
BEGIN
transaction:tx-186

^@SEND
destination:/queue/orders
transaction:tx-186

order-186^@COMMIT
transaction:tx-186

^@
~~~

Flow:

1. BEGIN opens transaction tx-186.
2. SEND attaches transaction tx-186.
3. COMMIT confirms the transaction.
4. ABORT can be used instead of COMMIT to cancel the transaction.

A transaction ID must be unique within the same connection. An uncommitted transaction is implicitly aborted if the client sends DISCONNECT or the TCP connection is lost.

A STOMP transaction is semantics provided by the broker for the STOMP operations that are attached to a transaction. It does not automatically include a database transaction in the Spring application.

## 14. RECEIPT and DISCONNECT with confirmed graceful shutdown

A client can close the socket directly, but in that case it is not certain that the server has received all earlier frames.

To close the connection with confirmation:

~~~text
DISCONNECT
receipt:close-186

^@
~~~

The client waits for:

~~~text
RECEIPT
receipt-id:close-186

^@
~~~

After receiving the receipt, the client closes the socket. The client MUST NOT send any more frames after DISCONNECT.

In practice, the server may close the socket quickly and the client may not receive the final receipt. The client needs a timeout for the graceful shutdown process.

## 15. Heartbeat: an EOL is not a command frame

STOMP heartbeat checks whether the connection is still alive. The two sides negotiate the heartbeat with the heart-beat header in CONNECT and CONNECTED.

Example:

~~~text
CONNECT
accept-version:1.2
host:broker.example
heart-beat:10000,5000

^@
~~~

~~~text
CONNECTED
version:1.2
heart-beat:8000,6000

^@
~~~

The header has two numbers:

- The first number: the minimum interval at which the sender can send data out.
- The second number: the interval at which the sender wants to receive data in.

Let the client values be cx,cy and the server values be sx,sy:

- The client sends a heartbeat to the server every MAX(cx, sy) milliseconds if both values are non-zero.
- The server sends a heartbeat to the client every MAX(sx, cy) milliseconds if both values are non-zero.

If there is no frame to send within the heartbeat interval, the sender sends a single EOL, usually LF. This EOL is not a STOMP frame because it has no command, headers, or NUL terminator.

Any data received on the connection can also prove that the peer is still alive. The receiver should allow a tolerance margin because the scheduler and the network can introduce delays.

STOMP heartbeat is different from WebSocket Ping/Pong. Heartbeat belongs to the STOMP protocol; Ping/Pong belongs to the WebSocket transport. The two mechanisms can coexist.

## 16. Distinguishing a STOMP frame from a WebSocket frame and a Spring Message

These three concepts sit at different layers:

| Component | Role |
|---|---|
| WebSocket frame/message | The unit of data at the WebSocket transport layer |
| STOMP frame | The command, headers, body structure at the messaging layer |
| Spring Message | Spring's internal object consisting of headers and a payload |

When using Spring WebSocket/STOMP, a STOMP frame from the client is decoded into a Spring Message and put into the clientInboundChannel. A message with the destination prefix /app can be routed to an @MessageMapping method; a /topic or /queue destination is usually routed to the broker according to the configuration.

When the server sends a message through the brokerChannel, the broker distributes it to the matching subscribers. The message is passed through the clientOutboundChannel, encoded into a STOMP frame, and sent back to the WebSocket client.

Spring configuration example:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

A controller that receives the SEND frame after Spring has converted it into a message:

~~~java
@Controller
public class GreetingController {

    @MessageMapping("/greeting")
    @SendTo("/topic/greeting")
    public String handle(String greeting) {
        return "Hello " + greeting;
    }
}
~~~

The client sends:

~~~text
SEND
destination:/app/greeting
content-type:text/plain

Spring^@
~~~

The client subscribes:

~~~text
SUBSCRIBE
id:greeting-sub
destination:/topic/greeting
ack:auto

^@
~~~

Spring receives the SEND, routes it to GreetingController.handle, and then publishes the result to /topic/greeting. The broker sends a MESSAGE frame to the subscriber.

In this configuration, /app, /topic, and /queue are prefixes configured by the application. The STOMP specification treats a destination as an opaque string; other brokers may use different conventions.

## 17. Spring APIs related to STOMP headers and frames

Spring provides several APIs for working with STOMP at the messaging layer:

- StompHeaderAccessor: accesses and modifies the STOMP command/headers through a Spring Message.
- StompHeaders: represents a set of STOMP headers in the Spring APIs that support it.
- StompDecoder: decodes a byte stream into an internal STOMP message.
- StompEncoder: encodes a Spring Message into a STOMP frame.
- SimpMessagingTemplate: sends a message to a destination in Spring's messaging model.
- @MessageMapping: maps an incoming message to a handler method in a controller.

These APIs help an application work with metadata and payloads without having to concatenate the wire-format strings by hand for each request.

When you need to debug the protocol, you can look at the raw frames in the client or in the broker log. When writing business code in Spring, it is usually better to use MessageMapping, SimpMessagingTemplate, and the header accessor.

Do not confuse StompHeaderAccessor with JMS Message headers. STOMP and JMS are two different APIs/protocols, even though a broker can support both.

## 18. Java 17 example: building a SEND frame with a UTF-8 body and header escaping

This example builds a STOMP 1.2 SEND frame as a byte array. It illustrates three details that are easy to get wrong:

- Header values must escape the colon, newline, and backslash.
- content-length must count the UTF-8 bytes of the body.
- The frame ends with a NUL byte.

Create the file StompFrameBuilderDemo.java:

~~~java
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class StompFrameBuilderDemo {

    private static byte[] encodeSend(
            String destination,
            String contentType,
            String note,
            String body) {

        byte[] bodyBytes = body.getBytes(StandardCharsets.UTF_8);
        ByteArrayOutputStream frame = new ByteArrayOutputStream();

        writeLine(frame, "SEND");
        writeLine(frame, "destination:" + escapeHeader(destination));
        writeLine(frame, "content-type:" + escapeHeader(contentType));
        writeLine(frame, "note:" + escapeHeader(note));
        writeLine(frame, "content-length:" + bodyBytes.length);

        // A blank EOL ends the header section.
        frame.write('\n');

        // The body is UTF-8 bytes, not the number of Java characters.
        frame.writeBytes(bodyBytes);

        // The NUL octet terminates the frame; it is not counted in content-length.
        frame.write(0);

        return frame.toByteArray();
    }

    private static void writeLine(
            ByteArrayOutputStream output,
            String line) {

        output.writeBytes(
                (line + "\n").getBytes(StandardCharsets.UTF_8)
        );
    }

    private static String escapeHeader(String value) {
        return value
                .replace("\\", "\\\\")
                .replace("\r", "\\r")
                .replace("\n", "\\n")
                .replace(":", "\\c");
    }

    public static void main(String[] args) {
        String body = "Xin chào";
        String note = "line1:ok\nline2\\done";

        byte[] frame = encodeSend(
                "/queue/orders",
                "text/plain;charset=UTF-8",
                note,
                body
        );

        // Only replace NUL with a readable symbol in order to print the example.
        String printable = new String(
                frame,
                StandardCharsets.UTF_8
        ).replace(String.valueOf((char) 0), "^@");

        System.out.println(printable);
        System.out.println("body.utf8Octets="
                + body.getBytes(StandardCharsets.UTF_8).length);
        System.out.println("body.javaLength=" + body.length());
    }
}
~~~

Compile and run with Java 17:

~~~bash
javac StompFrameBuilderDemo.java
java StompFrameBuilderDemo
~~~

Stdout:

~~~text
SEND
destination:/queue/orders
content-type:text/plain;charset=UTF-8
note:line1\cok\nline2\\done
content-length:9

Xin chào^@
body.utf8Octets=9
body.javaLength=8
~~~

In the output, the ^@ notation represents the NUL byte. The program only replaces NUL with a readable symbol when printing; the actual byte in the frame is still 0x00.

The example shows that String.length() is 8 while the UTF-8 body is 9 bytes long. The correct content-length value is 9.

The escapeHeader function applies the rules for header values of the SEND frame. Do not use this function for the body. A production encoder must also handle the command, valid header names, size limits, the STOMP version, and other frame types.

## 19. Common mistakes when reading or building frames

1. **Forgetting the blank line between the headers and the body:** the parser does not know where the body begins.
2. **Using a newline to terminate the body:** a STOMP frame ends with a NUL byte, not a newline.
3. **Sending the two characters ^@ in place of NUL:** ^@ is only a notation in documentation.
4. **Counting characters instead of bytes:** content-length must be the number of octets after encoding.
5. **Counting the NUL byte in content-length:** the NUL terminator lies outside the body length.
6. **Not setting content-length when the body contains NUL:** the parser may end the body too early.
7. **Not escaping header values:** a colon, CR, LF, or backslash can break the header structure.
8. **Escaping in the wrong order:** the backslash must be escaped before the other characters.
9. **Using an invalid escape sequence:** STOMP 1.2 does not define \t.
10. **Trimming header values:** leading/trailing whitespace can be intentional data.
11. **Assuming the last value of a duplicate header wins:** STOMP 1.2 recommends using the first value.
12. **Assuming every frame has a body:** only SEND, MESSAGE, and ERROR are allowed to have a body.
13. **Confusing a heartbeat LF with an empty frame:** a heartbeat is a single EOL, with no command and no NUL.
14. **Treating RECEIPT as business-level confirmation:** a receipt only confirms that the server has processed the frame at the protocol level.
15. **Confusing the ACK id with message-id:** the ACK id must match the ack header in MESSAGE.
16. **Assuming /queue and /topic are mandatory syntax:** the semantics of a destination are defined by the server.
17. **Assuming one socket read corresponds to one frame:** a stream can split or merge frames depending on timing.
18. **Not limiting the frame size:** large headers/bodies can exhaust the parser's memory.
19. **Confusing a STOMP frame with a WebSocket frame:** STOMP is a subprotocol running on top of the transport; a Spring Message is an internal object.
20. **Using the JMS API to parse STOMP:** a JMS Message and a STOMP wire frame are two different abstractions.

## 20. Checklist for inspecting a frame

When debugging a raw frame, check in this order:

- Does the command have the right name and the right letter case?
- Is the EOL valid for the STOMP version?
- Does each header line have the key:value form?
- Are the command's required headers present?
- Is there a blank EOL line before the body?
- Are the header values escaped correctly?
- Are there duplicate headers to which the first-value rule must be applied?
- Does content-type describe the body correctly?
- Does content-length equal the number of body bytes after encoding?
- If the body contains NUL, is content-length present?
- Is the NUL terminator byte in the right place?
- If there is no frame, is the single EOL a heartbeat?
- Does the frame exceed the client/server size limits?
- Are the destination and the header extensions correct for the broker in use?

## 21. Self-check questions

1. What parts does a STOMP frame consist of?
2. How can the EOL in STOMP 1.2 be either LF or CRLF?
3. What is the role of the blank line?
4. Which byte terminates a frame?
5. Why is ^@ in the documentation not data sent on the wire?
6. Does content-length count bytes or characters?
7. When is content-length mandatory?
8. Which frames are allowed to have a body?
9. What does content-type help the receiver do?
10. Which sequences does STOMP 1.2 use to escape the colon, LF, CR, and backslash?
11. Why does the backslash need to be escaped first?
12. If a header appears multiple times, which value SHOULD be used?
13. What represents a heartbeat when there is no frame to send?
14. How do SEND and SUBSCRIBE differ in purpose?
15. What does the ack header in SUBSCRIBE control?
16. Which header of MESSAGE must the ACK id match?
17. What does RECEIPT confirm, and what does it not confirm?
18. Why is a single socket read not guaranteed to contain exactly one frame?
19. Which internal abstraction does Spring convert a STOMP frame into?
20. Why doesn't the destination /queue/orders have the same semantics on every broker?

## 22. Conclusion

A STOMP frame has a clear structure: command, header section, blank line, body, and a terminating NUL byte. The command determines the operation; headers carry routing and control information; the body carries the payload. content-length counts the bytes of the body, content-type describes the format, and header escaping protects the delimiter characters inside header values.

When parsing a stream, you need to handle incomplete frames, multiple frames in a row, the NUL terminator, heartbeats, and size limits. When working with Spring, a STOMP frame is decoded into a Spring Message and then goes through a message channel, a controller, or the broker. Correctly understanding the boundary between the wire-format, the transport, and the Spring Message helps you debug the protocol accurately and avoid handling strings in ways that corrupt binary payloads.

## Official references

- STOMP Protocol Specification, Version 1.2: https://stomp.github.io/stomp-specification-1.2.html
- Spring Framework 6.2 — STOMP Overview: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/overview.html
- Spring Framework 6.2 — STOMP Message Flow: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html
- Spring Framework 6.2 — STOMP Protocol Support: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp.html
- Spring Framework 6.2 — STOMP Client: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/client.html
- Spring Framework 6.2 StompHeaderAccessor API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html
- Spring Framework 6.2 StompDecoder API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html
- Spring Framework 6.2 StompEncoder API: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/stomp/StompEncoder.html
