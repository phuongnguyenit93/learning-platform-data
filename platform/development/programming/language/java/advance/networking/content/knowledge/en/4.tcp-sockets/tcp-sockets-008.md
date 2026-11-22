# shutdownInput, shutdownOutput, and Half-Closing a TCP Connection in Java

**TCP is a full-duplex connection**: both sides can simultaneously send and receive bytes on the same socket. However, an application may have finished sending its *entire* request while still needing to receive a response. If the entire socket is closed immediately after sending, the receiving direction is also closed. **Socket.shutdownOutput()** solves this case: it terminates the **local sending direction** while keeping the **local receiving direction** open to read data from the peer.

Java also has **Socket.shutdownInput()**, but this operation is completely different: it terminates **local reading**, without sending a TCP FIN to tell the peer to stop sending. **Socket.close()**, on the other hand, terminates the use of the entire socket. Understanding these three operations clearly is core knowledge in the **TCP with Sockets** section.

Lesson objectives: explain FIN and EOF in TCP half-close; determine which direction remains active after each call; write a Java 17 program that sends a request, calls shutdownOutput, and then receives a response; understand why shutdownInput does not close the sending direction; and avoid bugs involving data loss, deadlocks waiting for EOF, premature stream closure, timeouts, and improper resource management.

## 1. One connection, two byte stream directions

~~~text
                TCP connection
CLIENT                                         SERVER
OutputStream  ----------------------------->  InputStream
InputStream   <-----------------------------  OutputStream
            two independent transmission directions
~~~

Closing the client's **sending direction** means the client will not send any more new bytes, while the server can continue returning a response. Closing the client's **receiving direction** means the client gives up the ability to read data sent by the server, while the direction from the client to the server can still remain open.

**Half-close (closing one direction)** usually refers to one side stopping *sending* via FIN while still being able to receive bytes in the opposite direction. A TCP FIN follows the order of the byte stream: the peer reads all bytes sent before the FIN and then sees **EOF** (in Java, many read calls return **-1**).

~~~text
CLIENT                                              SERVER
write(request) -----------------------------------> read(): request bytes
shutdownOutput() --------- FIN -------------------> read(): -1
[client has finished sending but can still read]
               <----------------------------------- write(response)
read(): response bytes <---------------------------
read(): -1 <----------- FIN ----------------------- shutdownOutput()
close()                                             close()
~~~

**FIN is not a business ACK.** Java returning after shutdownOutput does not prove that the peer has processed the request, written data to a database, or sent a result. If you need to know that a task has completed, you need a **response** or acknowledgment defined at the application layer.

**One-way EOF does not mean the entire TCP connection is dead.** When the server sees EOF on its input, the client may still be waiting for the server to send a response in the reverse direction. This is why distinguishing half-close from close is so important.

## 2. Comparing shutdownOutput, shutdownInput, and close

| Call on java.net.Socket | Effect on the calling host | Signal/effect at the peer | Remaining direction |
|---|---|---|---|
| **shutdownOutput()** | Stops writing; subsequent writes throw IOException. TCP terminates the local → peer direction after already-sent bytes | Peer reads all prior bytes and then receives EOF (-1) when FIN arrives | **Local input can still be read** |
| **shutdownInput()** | Puts local input at EOF; reads on previously obtained streams return -1; subsequent arriving bytes are discarded | Does not send FIN to signal the peer to stop sending | **Local output can still be written** |
| **close()** | Closes the socket and its streams; the socket cannot be reused | Peer may observe EOF or an error/reset depending on state and how it was closed | **No I/O remains** |

### 2.1. Socket.shutdownOutput()

The contract of **Socket.shutdownOutput()**: for TCP, data previously written to the socket is sent before the sending direction goes through the normal TCP connection-termination sequence. After that, further **OutputStream.write(...)** calls throw **IOException**. The local **InputStream** can still be used to read the response.

The following snippet assumes the socket is already connected and requestBytes is already available (it is not a standalone runnable program):

~~~java
socket.getOutputStream().write(requestBytes);
socket.shutdownOutput();        // Stop local sending, send FIN following the data.
byte[] reply = socket.getInputStream().readAllBytes();
// When the protocol finishes, close the socket to release resources.
~~~

**A direction that has been shut down cannot be reopened on the same connection.** If a protocol requires the client to send multiple requests in succession, do not call shutdownOutput after the first request unless the protocol specifies that the client will permanently stop sending.

### 2.2. Socket.shutdownInput()

**Socket.shutdownInput()** places the local input at end-of-stream: for an **InputStream obtained before the shutdown**, read calls return **-1**, and available returns 0. Subsequent data sent by the peer in this direction is acknowledged and then discarded per the Socket contract.

~~~java
InputStream in = socket.getInputStream(); // Obtain before shutdown.
socket.shutdownInput();
int eof = in.read();                     // -1.
~~~

**Note:** **Socket.getInputStream()** may throw IOException if called *after the input has been shut down*. Therefore, you should not obtain a new stream after shutdown and expect to reliably receive -1. The code snippet above intentionally obtains the InputStream beforehand.

**shutdownInput does not notify the peer that the client has finished sending.** If the server is waiting for EOF on the client → server direction, the client must call **shutdownOutput()**, not shutdownInput(). Most request/response protocols need shutdownOutput far more often than shutdownInput.

### 2.3. Socket.close()

**close()** closes the socket, InputStream, and OutputStream; it also closes the associated SocketChannel if one exists. A closed socket cannot be reconnected or rebound. Depending on unread/unsent data state, TCP, and settings such as SO_LINGER, the other side may observe EOF or a reset/error; you must not assume every close is equivalent to a normal FIN where the application has finished acknowledging all data.

~~~java
try (Socket socket = new Socket(host, port)) {
    // Use streams or half-close according to the protocol.
} // Automatically calls Socket.close() when leaving scope.
~~~

**Closing a stream obtained from a Socket also closes the entire socket.** Therefore, a **separate try-with-resources for OutputStream** is a trap if you still intend to read from InputStream afterward. Let try-with-resources manage the Socket at the transaction scope, and use shutdownOutput when you need to signal the end of data while keeping the receiving direction open.

## 3. EOF and message boundaries: using them properly per protocol

TCP only provides a **byte stream**; it does not preserve the boundary of one write as one read. A peer may read a request across multiple reads; multiple writes may also be coalesced.

To know where a message ends, a protocol needs framing rules:

- **Length-prefix:** send the length first, then receive the exact number of declared bytes.
- **Delimiter:** use a separator token (such as newline), with escaping control and length limits.
- **EOF-delimited:** the entire payload in one direction is defined as ending when the peer half-closes/closes its sending direction. **shutdownOutput()** is very useful for this style because the sender can still read the response.

If the server uses **InputStream.readAllBytes()** to wait for EOF while the client does not close its sending direction, the server will wait for more data and may hang. The EOF-delimited style is also unsuitable for multiple request-response rounds on the same sending direction, because after shutdownOutput no further request can be written.

## 4. Complete Java 17 example: send PING, close sending direction, receive ACK

Illustrative protocol: the client sends UTF-8 **PING** and calls shutdownOutput so the server knows the request is complete; the server reads the entire request until EOF, sends **ACK:PING**, and then calls shutdownOutput so the client knows the response is complete. Both sides use try-with-resources to close the socket after the exchange finishes.

The example uses loopback and an OS-assigned ephemeral port, requiring no external server. A worker thread for the server side lets both sides run concurrently. Main prints all results after completion so stdout has a deterministic order.

File **HalfCloseRoundTripDemo.java**:

~~~java
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class HalfCloseRoundTripDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(0, 10, loopback)) {
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverRead = worker.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(4_000);
                        String request = new String(
                                peer.getInputStream().readAllBytes(),
                                StandardCharsets.UTF_8);

                        byte[] response = ("ACK:" + request)
                                .getBytes(StandardCharsets.UTF_8);
                        peer.getOutputStream().write(response);
                        peer.shutdownOutput();
                        return request;
                    }
                });

                String reply;
                boolean clientOutputShutdown;

                try (Socket client = new Socket(
                        loopback, listener.getLocalPort())) {
                    client.setSoTimeout(4_000);
                    client.getOutputStream().write(
                            "PING".getBytes(StandardCharsets.UTF_8));
                    client.shutdownOutput();

                    clientOutputShutdown = client.isOutputShutdown();
                    reply = new String(
                            client.getInputStream().readAllBytes(),
                            StandardCharsets.UTF_8);
                }

                String requestAtServer =
                        serverRead.get(5, TimeUnit.SECONDS);
                System.out.println(
                        "Client output shutdown: " + clientOutputShutdown);
                System.out.println("Server received: " + requestAtServer);
                System.out.println("Client received: " + reply);
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
~~~

Compile and run in the directory containing the file:

~~~bash
javac -encoding UTF-8 HalfCloseRoundTripDemo.java
java HalfCloseRoundTripDemo
~~~

Stdout of a successful run:

~~~text
Client output shutdown: true
Server received: PING
Client received: ACK:PING
~~~

### Step-by-step explanation

1. **ServerSocket** opens a loopback port, and **accept()** waits for a connection in the worker. The **Socket** returned by accept is the established connection, distinct from the listener.
2. The client writes **PING**, then calls **shutdownOutput()**. This signals the end of the request in the EOF-delimited protocol. **isOutputShutdown()** becomes true locally.
3. The server's **readAllBytes()** reads the entire request up to EOF caused by the client's FIN. It **does not wait for the client socket to close completely**. Then the server builds the reply.
4. The server sends **ACK:PING** and calls **shutdownOutput()**. The client can still read because it only stopped its own sending direction, not its receiving direction.
5. The client's readAllBytes receives the response and reaches EOF, and then the sockets are closed in turn. **Future.get(...)** in main retrieves the request the server read so the results are printed in a deterministic order.

This small example uses **readAllBytes()**, but in real applications you must limit total input size and set a deadline. **Socket.setSoTimeout(...)** limits the wait for blocking read operations; it is **not** a deadline for the entire request and does not automatically limit write or connect. If a response is very large, read it in chunks and control backpressure.

### What if the client forgets shutdownOutput?

Keep the server's **readAllBytes()** as-is, but remove **client.shutdownOutput()**:

~~~text
CLIENT                                  SERVER
write("PING")
readAllBytes(response) --- waits ---> readAllBytes(request) waiting for EOF
                          (both sides waiting)
~~~

The server does not know the request has ended, so it has not generated ACK yet; the client waits for ACK. This is a **protocol-level deadlock**. One side may eventually time out or close the socket, but the root cause must be fixed with explicit framing or by having the client call shutdownOutput according to the EOF-delimited convention.

## 5. Complete Java 17 example: shutdownInput only disables local reading

The following example confirms that **shutdownInput** does not prohibit writing. The client obtains InputStream first, calls shutdownInput, and reads **-1**. Afterward, the client still sends **HELLO**. The server reads the full data because the client → server direction remains active until the client calls shutdownOutput.

File **ShutdownInputDemo.java**:

~~~java
import java.io.InputStream;
import java.net.InetAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class ShutdownInputDemo {
    public static void main(String[] args) throws Exception {
        InetAddress loopback = InetAddress.getLoopbackAddress();

        try (ServerSocket listener = new ServerSocket(0, 10, loopback)) {
            ExecutorService worker = Executors.newSingleThreadExecutor();
            try {
                Future<String> received = worker.submit(() -> {
                    try (Socket peer = listener.accept()) {
                        peer.setSoTimeout(4_000);
                        return new String(
                                peer.getInputStream().readAllBytes(),
                                StandardCharsets.UTF_8);
                    }
                });

                boolean inputShutdown;
                int localRead;

                try (Socket client = new Socket(
                        loopback, listener.getLocalPort())) {
                    InputStream input = client.getInputStream();
                    client.shutdownInput();

                    inputShutdown = client.isInputShutdown();
                    localRead = input.read();  // -1 per Socket contract.

                    client.getOutputStream().write(
                            "HELLO".getBytes(StandardCharsets.UTF_8));
                    client.shutdownOutput();
                }

                System.out.println(
                        "Client input shutdown: " + inputShutdown);
                System.out.println(
                        "Client read after shutdown: " + localRead);
                System.out.println(
                        "Server received: " + received.get(
                                5, TimeUnit.SECONDS));
            } finally {
                worker.shutdownNow();
            }
        }
    }
}
~~~

~~~bash
javac -encoding UTF-8 ShutdownInputDemo.java
java ShutdownInputDemo
~~~

Stdout on a successful run:

~~~text
Client input shutdown: true
Client read after shutdown: -1
Server received: HELLO
~~~

In the example, **the server completes readAllBytes() thanks to client.shutdownOutput()**, not client.shutdownInput(). If you only call shutdownInput without terminating the sending direction, the server can still wait indefinitely for EOF.

Common pitfall: if you replace **InputStream input = client.getInputStream()** with a call to **client.getInputStream()** *after* shutdownInput, Java Socket may throw **IOException**. To demonstrate local EOF, you must keep the stream obtained beforehand.

## 6. Using BufferedOutputStream: flush before half-close

Suppose the application uses a Java buffer to reduce the number of writes:

~~~java
BufferedOutputStream buffered =
        new BufferedOutputStream(socket.getOutputStream());
buffered.write(requestBytes);
buffered.flush();
socket.shutdownOutput();
byte[] response = socket.getInputStream().readAllBytes();
~~~

This is an **illustrative snippet**, assuming the socket is already connected and requestBytes is available; it is not a complete program.

**Why must you flush?** Writing to BufferedOutputStream may only place bytes into a buffer inside the Java process, without yet passing those bytes to SocketOutputStream. **shutdownOutput()** only knows about data already passed to the socket layer; it does not automatically reach into every buffer wrapper created by the application. You must call **flush() before shutdownOutput()**.

**Why not call buffered.close() right after writing?** Closing the wrapper closes the underlying socket output stream and closes the entire socket. If you still need to read the response, keep the socket alive, flush and then call shutdownOutput; at the end of the session, close the Socket with try-with-resources. Do not use a separate try-with-resources for an output wrapper in the middle of a half-close transaction.

Nor should flush be interpreted as meaning the peer has processed the data: flush moves data out of the application buffer per the stream contract; FIN signals the end of the sending direction; confirming business-level success requires an appropriate response.

## 7. Distinguishing local state from peer signals

| State/observation | Correct conclusion | Incorrect conclusion to avoid |
|---|---|---|
| **socket.isOutputShutdown()** is true | Local host has shut down the sending direction | Peer has definitely finished processing the request |
| **socket.isInputShutdown()** is true | Local host has shut down the receiving direction | Peer received a signal asking it to stop sending |
| **socket.isClosed()** is true | Local socket object is closed | Remote definitely observed a normal EOF |
| **socket.isConnected()** is true | Socket was successfully connected at some point | Connection is still alive right now; even after close it may still be true |
| **input.read() == -1** | Reached EOF on that input stream | Can no longer send a response in the reverse direction |
| **input.available() == 0** | At that moment there are no bytes immediately available per the API | Reached EOF; 0 is not EOF |
| **IOException/SocketException** | An I/O error or invalid state occurred | Every error is a normal FIN from the peer |

If your side calls **shutdownInput()**, reads on a previously obtained stream return **-1** due to a **local decision**. If the peer calls **shutdownOutput()**, reads can also reach **-1**, but the cause is a **FIN from the peer**. Distinguish them using protocol flow, logging shutdown timestamps, and local flags; do not rely solely on the -1 value.

In TCP, **FIN** only terminates one transmission direction normally. When there is a network error, peer crash, socket closure with unprocessed data remaining, or special SO_LINGER settings, **RST** and an exception may occur instead of EOF. Code must handle the failure path as well and always clean up the socket.

## 8. Half-close and close do not replace resource management

After shutdownOutput, the socket still holds resources; input can continue reading, but the socket must be **closed** when the protocol finishes. Even if both sides have called shutdownOutput and both have read EOF, you should still close to release local resources and clarify ownership.

**Do not reuse a direction that has been shut down**: after shutdownOutput, further writes to the Socket OutputStream throw IOException; after shutdownInput, reads on the previously obtained InputStream report EOF. There is no undo method to resume two-way exchange on the same connection.

**Do not use close to simulate shutdownOutput** if the protocol requires a response. Close terminates the ability to receive as well. When you need to send data and wait for a result, specify precisely who calls shutdownOutput and when; only call close after receiving the full response.

**ServerSocket.close()** closes the listener so accept no longer waits for/receives new connections; it is not a half-close call on each accepted Socket. In real server code, the listener and the accepted sockets have separate lifecycles.

## 9. With SocketChannel and higher-level protocols

**java.nio.channels.SocketChannel** (Java NIO) has **shutdownInput()** and **shutdownOutput()** with similar half-close semantics, but the methods return the channel itself and the NIO contract has its own details:

- After **SocketChannel.shutdownInput()**, subsequent reads on the channel return **-1**; the channel can still remain open for writing.
- After **SocketChannel.shutdownOutput()**, subsequent writes to the channel throw **ClosedChannelException** per the Java 17 API; this does not mean the entire channel is closed.
- If one thread is blocked in SocketChannel.read while another thread shuts down input, the read may complete with **-1**. Shutting down output while another thread is blocked in write may cause that thread to receive **AsynchronousCloseException**.
- With Selector/non-blocking NIO, you must also manage SelectionKey, half-close state, and buffers; you cannot simply call shutdown and ignore the event loop.

Do not assume **AsynchronousSocketChannel** has all the same methods as SocketChannel. Always follow the exact API of the channel type you are actually using.

At the application layer, **HTTP/1.1 keep-alive**, HTTP/2, WebSocket, and protocols with their own framing generally **do not** treat EOF of the entire TCP connection as the end of each request. Do not call shutdownOutput yourself between requests on a connection that is still being reused. **TLS/SSLSocket** has its own closing procedure such as close_notify; a raw TCP FIN does not replace TLS's secure closure semantics. When using a framework, follow the lifecycle managed by the framework and protocol.

## 10. When to choose shutdownOutput, shutdownInput, or close?

| Situation | Appropriate decision |
|---|---|
| Client has sent the full payload under an EOF-delimited protocol but needs to receive a reply | **Flush if buffered, then shutdownOutput; keep reading the response** |
| Server uses EOF to determine the end of a request | **Read until -1, then process and send the response**; do not default to closing the socket as soon as EOF is received |
| Local host no longer wants to read incoming data but still has data to send | Consider **shutdownInput**, accepting that inbound data will be discarded |
| Want to completely end the transaction and release resources | **Socket.close()** or try-with-resources |
| Want to use the connection for multiple requests/responses | Choose **length-prefix/delimiter** or standard framing; **do not call shutdownOutput after the first request** |
| Want to break a hanging read caused by a peer not sending FIN | Set a **read timeout**, deadline, byte limit, and close policy |
| Want to know whether the peer has processed the request | Use an **application-layer ack/response**, not just the shutdown flag |

### Common mistakes

1. **Confusing shutdownInput with shutdownOutput**: only shutdownOutput signals the end of the sending direction so the peer receives EOF.
2. **Calling close or OutputStream.close too early**: loses the ability to read the response as well.
3. **Calling readAllBytes on an unbounded payload**: can exhaust RAM or wait forever; set quotas, timeouts, and framing.
4. **Not flushing Java buffers before shutdownOutput**: bytes sitting in the buffer may not have reached the socket yet.
5. **Interpreting EOF as the entire connection being closed**: the peer can still send a reply in the reverse direction.
6. **Assuming shutdownOutput proves the server received/processed the data**: a business-level response is required.
7. **Assuming isConnected is a liveness check**: the method does not prove the connection is currently active.
8. **Not handling RST, timeouts, and exceptions**: error termination differs from normal EOF.
9. **Not calling close after half-close**: socket resources are not guaranteed to be cleaned up.
10. **Not defining message framing**: one write does not correspond to one read.

## 11. Self-verification exercises

### Exercise A — Create a controlled deadlock

In **HalfCloseRoundTripDemo**, remove client.shutdownOutput while keeping the server's readAllBytes and the client reading the response. Predict which thread waits where. Use a timeout to avoid hanging indefinitely, then restore shutdownOutput to verify the EOF-delimited mechanism.

### Exercise B — Output stream closure bug

Try modifying the client to wrap **client.getOutputStream()** in a separate try-with-resources, closing the stream before reading the response. Explain why the socket gets closed and why **shutdownOutput()** is the right operation if you want to keep the receiving direction open.

### Exercise C — State after each operation

Record the values of **isConnected**, **isInputShutdown**, **isOutputShutdown**, and **isClosed** before shutdown, after shutdownOutput, and after close. Explain why isConnected does not change to false just because the socket has been closed.

### Exercise D — Compare framing styles

Replace readAllBytes with a 4-byte length-prefix and a 1 MB payload limit. Send two consecutive requests over a single TCP connection; when is shutdownOutput needed, and when is length alone sufficient for the server to know a message is complete?

### Exercise E — Test input shutdown

Run **ShutdownInputDemo**, keep the InputStream obtained beforehand, and observe read() returning -1. Try obtaining InputStream **after shutdownInput** and check for IOException. Explain why shutdownInput does not cause the server's readAllBytes to finish before the client calls shutdownOutput.

## 12. Comprehension check questions

**1. Does shutdownOutput close the local reading direction?** No. That is the basis for sending a request and still being able to read the response.

**2. Does read() == -1 on the server mean the client cannot receive a response?** No. The client may have only sent FIN via shutdownOutput.

**3. Does shutdownInput send a TCP FIN to the peer?** No. It stops local reading; to signal the end of bytes in the sending direction, you must call shutdownOutput.

**4. Why shouldn't you close OutputStream before reading the response?** Closing a stream provided by Socket closes the entire Socket, preventing the transaction from continuing.

**5. Why can readAllBytes block?** Because it waits for EOF. If the peer does not terminate its sending direction or send more data, the operation can wait until timeout.

**6. Can you call write after shutdownOutput?** No. The Java Socket OutputStream will throw IOException.

**7. Do you still need to call close after both directions have ended?** Yes. Close cleans up local resources and ends the lifecycle of the Socket object.

**8. Does FIN mean the data has been successfully processed?** No. It is a transport signal; business processing requires a separate acknowledgment.

## API reference documentation

- Java SE 17, **Socket**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/Socket.html
- Java SE 17, **SocketChannel**: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/channels/SocketChannel.html

**Remember:** **shutdownOutput() terminates the TCP sending direction and lets the peer observe EOF after the bytes preceding FIN; the receiving direction remains usable. shutdownInput() terminates local reading and does not send FIN on behalf of the peer. close() terminates the use of the entire socket.** Half-close is only correct when the protocol defines clear data boundaries, preserves buffers, handles errors/timeouts, and closes after the transaction is complete.