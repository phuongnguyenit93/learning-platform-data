# Server-Assigned Random Ports Instead of Guessing Free Ports

When writing integration tests, an HTTP server, database proxy, or auxiliary service often needs a TCP port to listen on. If multiple tests run concurrently or multiple processes share a development machine, fixing a port such as 8080, 5432, or 9090 easily causes collisions.

A safe approach is to let **the server itself ask the operating system to assign a free port at bind time**. In Java, port `0` has a special meaning: when a socket binds to port 0, the operating system picks an available ephemeral port and attaches it to the socket. Once binding succeeds, the application reads the actual port back from the socket or server.

This marks an important difference between:

- **The server binding port 0 itself and reading the assigned port:** choosing and claiming the port occur in the same bind operation, avoiding a gap between check and use.
- **The test probing a seemingly free port, closing the socket, and telling the server to use that port:** another process can claim the port during the interval between the two operations.

## 1. Why Should You Not Guess or Probe for Free Ports?

Suppose a test needs to open an HTTP server on port 8080. If another application already uses that port, the test server cannot bind and the test fails. You could try port 8081, 8082, or another number, yet this approach still relies on the assumption that the chosen port happens to be free.

A common pattern is opening `ServerSocket(0)` to ask the OS for a free port, grabbing that port, closing the socket, and passing the port to the real server:

~~~java
int port;
try (ServerSocket socket = new ServerSocket(0)) {
    port = socket.getLocalPort();
}

// After the socket is closed, another process may claim this port.
startHttpServer(port);
~~~

This code has a race condition. Once `ServerSocket` closes, the port is released. Before `startHttpServer(port)` binds, another process can grab that exact port. The test may pass on a personal machine yet fail intermittently in CI or under parallel execution.

This issue is called **TOCTOU (time of check to time of use)**: a resource is checked at one moment, but used only later. The state of the resource can change between those two moments.

~~~text
Test A                          OS / Test B
  |                                      |
  | bind port 0                          |
  |------------------------------------->|
  | receive port 49173                   |
  |                                      |
  | close socket, port is released       |
  |                                      |
  |                                      | Test B binds port 49173
  |                                      |-------------------->
  | start server on 49173                |
  |------------------------------------->|
  | bind failed: address already in use  |
~~~

The best solution is letting the real server bind port 0 itself, then reading the port that the server is holding. That eliminates the "probe then release" gap before the server uses it.

## 2. What Does Port 0 Mean?

In Java's socket API, port 0 does not mean the server will listen on port 0. It means asking the operating system to select a suitable port during bind.

Example:

~~~java
ServerSocket serverSocket = new ServerSocket(0);
int actualPort = serverSocket.getLocalPort();
~~~

After the constructor binds successfully:

- `serverSocket.getLocalPort()` returns the actual assigned port.
- The actual port is a positive integer in the ephemeral port range managed by the OS.
- `ServerSocket` continues holding that port until the socket closes.
- You must not assume the next run will receive the same port.

When creating an unbound socket:

~~~java
ServerSocket socket = new ServerSocket();
int portBeforeBind = socket.getLocalPort(); // -1 when not yet bound
socket.bind(new InetSocketAddress(0));
int actualPort = socket.getLocalPort();
~~~

Only read the port after binding succeeds. With `ServerSocket(0)`, binding happens directly in the constructor. With an unbound socket, `bind(...)` must be called first.

Port 0 is a request on the server/socket bind side. Clients do not connect to `localhost:0`; clients must use the actual port read after the server binds.

## 3. Example: JDK ServerSocket Obtaining Its Own Port

The following example creates a TCP server listening on the loopback interface with an OS-assigned port:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;

public class RandomPortServer implements AutoCloseable {

    private final ServerSocket serverSocket;

    public RandomPortServer() throws IOException {
        serverSocket = new ServerSocket();
        serverSocket.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(),
            0
        ));
    }

    public int port() throws IOException {
        return serverSocket.getLocalPort();
    }

    @Override
    public void close() throws IOException {
        serverSocket.close();
    }
}
~~~

Usage:

~~~java
try (RandomPortServer server = new RandomPortServer()) {
    int actualPort = server.port();
    System.out.println("Server is bound to port " + actualPort);
    // Continue handling connections while serverSocket remains open.
}
~~~

`InetAddress.getLoopbackAddress()` restricts the socket to the loopback interface, which fits servers serving only tests running on the same machine. If connections must arrive from a container or another host, choose an interface appropriate for the environment. Avoid binding all interfaces indiscriminately just to test local connections.

In the example above, the socket already holds the port once the constructor finishes. If another HTTP server needs this port, you cannot close the socket and hope the other server captures the exact same port. You must let the HTTP server itself bind port 0, or use an API capable of accepting an already-bound socket/channel if the library supports it.

### With `DatagramSocket`

UDP follows a similar mechanism:

~~~java
try (DatagramSocket socket = new DatagramSocket(0)) {
    int actualPort = socket.getLocalPort();
    // Send or receive datagrams while the socket remains open.
}
~~~

The port assigned to a UDP socket is independent of a TCP port with the same number. A TCP socket and a UDP socket can share the same port number without necessarily colliding because they belong to two different transport protocols.

## 4. Testing Directly with a Random Port

With JUnit, you can start the server in `@BeforeEach` or `@BeforeAll`, then read the actual port inside the test:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

class RandomPortTests {

    private ServerSocket serverSocket;

    @BeforeEach
    void startServer() throws IOException {
        serverSocket = new ServerSocket();
        serverSocket.bind(new InetSocketAddress(
            InetAddress.getLoopbackAddress(),
            0
        ));
    }

    @AfterEach
    void stopServer() throws IOException {
        serverSocket.close();
    }

    @Test
    void operatingSystemAssignsAnAvailablePort() throws IOException {
        int port = serverSocket.getLocalPort();

        assertThat(port).isPositive();
        assertThat(serverSocket.isBound()).isTrue();
        assertThat(serverSocket.isClosed()).isFalse();
    }
}
~~~

The test verifies that the socket is bound and has a positive port. Do not assert a fixed number or assume the port always falls within a specific range, because the ephemeral port range depends on the operating system and machine configuration.

In real tests, replace `ServerSocket` with the HTTP server or resource the application uses. What matters is that the port is assigned by the bind operation of that resource itself.

## 5. Spring Boot Embedded Server with `RANDOM_PORT`

Spring Boot supports starting an embedded web server on a random port via:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
~~~

`RANDOM_PORT` instructs the embedded server to bind to an OS-assigned random port. Tests can read the actual port using `@LocalServerPort`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ApplicationHttpIntegrationTests {

    @LocalServerPort
    int port;

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void respondsOnThePortAssignedByTheServer() {
        ResponseEntity<String> response =
            restTemplate.getForEntity("/health", String.class);

        assertThat(port).isPositive();
        assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
    }
}
~~~

In Spring Boot 3, `@LocalServerPort` lives in package `org.springframework.boot.test.web.server`. In older Boot versions, the annotation package may differ; use the package matching your project version.

When using `RANDOM_PORT`, Spring Boot starts a real server inside the test process. Tests send requests over HTTP to the embedded server. This differs from MockMvc, where requests execute through Spring MVC without binding a TCP port.

You can configure the equivalent via a property:

~~~properties
server.port=0
~~~

or pass the property when running the application. For Spring Boot tests, `webEnvironment = RANDOM_PORT` expresses the intent clearly and provides the bound port via `@LocalServerPort`.

### Distinguishing `RANDOM_PORT` and `DEFINED_PORT`

| WebEnvironment | Behavior |
|---|---|
| `MOCK` | Creates a mock web environment; does not start a real server. |
| `RANDOM_PORT` | Starts a real server on a random port. |
| `DEFINED_PORT` | Starts a server on the configured port, typically `server.port`. |
| `NONE` | Does not create a web environment. |

Choose `RANDOM_PORT` when you need to test over real HTTP without depending on a fixed port.

## 6. Reading the Port After the Embedded Server Has Bound

In a Spring Boot integration test, `@LocalServerPort` is injected after the web server starts. Do not attempt to read the port before the server binds or manually probe a free port to pass into `server.port`.

Example using a dynamic URI:

~~~java
URI baseUri = URI.create("http://localhost:" + port);
~~~

If the test uses Boot-provided `TestRestTemplate`, it can call relative URIs:

~~~java
restTemplate.getForEntity("/health", String.class);
~~~

`TestRestTemplate` is preconfigured to target the test's embedded server. If building your own `RestClient` or `WebClient`, construct the base URL from the injected port after the server is ready.

Do not cache a base URL built from an old port if the server is restarted. A new port is only available after the new bind and must be read again.

## 7. WireMock Choosing Its Own Port

WireMock provides the `dynamicPort()` API so the server picks a port when starting:

~~~java
import static com.github.tomakehurst.wiremock.client.WireMock.get;
import static com.github.tomakehurst.wiremock.client.WireMock.urlEqualTo;
import static com.github.tomakehurst.wiremock.client.WireMock.aResponse;
import static com.github.tomakehurst.wiremock.core.WireMockConfiguration.options;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import com.github.tomakehurst.wiremock.WireMockServer;

import static org.assertj.core.api.Assertions.assertThat;

class PartnerStubTests {

    static final WireMockServer partner =
        new WireMockServer(options().dynamicPort());

    @BeforeAll
    static void startPartner() {
        partner.start();
    }

    @AfterAll
    static void stopPartner() {
        partner.stop();
    }

    @Test
    void exposesTheActualBoundPort() {
        int port = partner.port();
        String baseUrl = partner.baseUrl();

        assertThat(port).isPositive();
        assertThat(baseUrl).endsWith(":" + port);

        partner.stubFor(get(urlEqualTo("/health"))
            .willReturn(aResponse()
                .withStatus(200)
                .withBody("UP")));
    }
}
~~~

`dynamicPort()` configures WireMock to pick a port during server startup. Only read `port()` or `baseUrl()` after `start()`. Do not pass a previously probed port into WireMock without a special reason.

If a Spring bean needs WireMock's base URL as soon as the `ApplicationContext` is created, ensure WireMock starts before Spring reads the property. You can manage the resource with an appropriate lifecycle or register a supplier via `@DynamicPropertySource`; the supplier only reads the address, while the start operation still must happen earlier.

## 8. Testcontainers: Container Port vs. Mapped Host Port

Testcontainers also uses dynamic port mapping. A container may listen on a fixed port inside the container, while Docker maps that port to a random port on the host.

Example:

~~~text
Inside container:
  HTTP server listens on :8080

On host:
  Docker maps 49173 -> container:8080

Client from test process:
  http://<host>:49173
~~~

Code example:

~~~java
import org.testcontainers.containers.GenericContainer;
import org.testcontainers.utility.DockerImageName;

class PartnerContainerFixture {

    static final GenericContainer<?> partner =
        new GenericContainer<>(DockerImageName.parse("example/partner:1.0"))
            .withExposedPorts(8080);

    static void start() {
        partner.start();
    }

    static String baseUrl() {
        return "http://" + partner.getHost() + ":"
            + partner.getMappedPort(8080);
    }
}
~~~

`getMappedPort(8080)` can only be called after the container has started. `getHost()` returns the host the test process can use to reach the container; in some CI or remote Docker environments, this host is not necessarily `localhost`.

Do not confuse:

- `8080`: port inside the container.
- `getMappedPort(8080)`: port mapped out to the host side.
- `getHost()`: hostname/IP for the test process to reach that mapping.

Testcontainers handles selecting and binding the host port. You do not need to search for a free port yourself and pass it to Docker.

## 9. Random Ports and Parallel Testing

Fixed ports easily cause conflicts when:

- Multiple test classes start the same kind of server.
- Build tools run multiple test forks.
- CI runs multiple jobs on the same host.
- A developer runs a local application using the same port.
- Tests run in parallel within the same JVM.

When each server binds port 0 itself, the OS assigns an available port at bind time. Each server holds its own socket, so port allocation is coordinated at the OS level rather than guessed by tests.

However, random ports do not solve all concurrency issues by themselves:

- Two tests can still share the same server instance if the fixture is declared static or singleton.
- A resource can be stopped while another test is still using it.
- A test can still read an old stale port if the server restarts.
- A port may be reused after a server closes; never assume a port stays unique for the machine's entire uptime.

Manage both port and server lifecycle separately. Each test needs the accurate endpoint of the resource it is using.

## 10. Why Should You Not Write `findFreePort` and Close the Socket?

A common helper:

~~~java
static int findFreePort() throws IOException {
    try (ServerSocket socket = new ServerSocket(0)) {
        return socket.getLocalPort();
    }
}
~~~

This function returns a port briefly held by a temporary socket, yet immediately upon exiting try-with-resources, the socket closes and the port is released. The returned value is merely an earlier observation; it is not an active reservation for a server that will start later.

Do not use it like this:

~~~java
int port = findFreePort();
embeddedServer.setPort(port);
embeddedServer.start();
~~~

The gap between `findFreePort()` and `embeddedServer.start()` creates a race condition. If the embedded server supports port 0, configure port 0 directly and read the actual port after the server starts.

If a library does not support port 0 but has an API accepting an already-bound socket/channel, you can keep the bound socket open and hand that exact socket to the server. This applies only when the library officially supports receiving an open socket; do not close the socket and pass only the port number.

If an external process supports neither port 0 nor receiving a bound socket, no probe-and-close approach can completely guarantee avoiding races. In that case, consider changing how the service is launched, using container port mapping, or using an appropriate resource coordination mechanism.

## 11. Choosing the Right Bind Address

The port is only part of an endpoint. Besides the port, the server must also choose a network interface/address:

| Bind address | Typical meaning |
|---|---|
| `127.0.0.1` | Accepts IPv4 loopback connections from the same host only. |
| `::1` | Accepts IPv6 loopback connections from the same host only. |
| `InetAddress.getLoopbackAddress()` | Loopback address appropriate for the JVM environment. |
| `0.0.0.0` | Listens on all IPv4 interfaces. |
| `::` | Listens on all IPv6 interfaces; dual-stack behavior depends on the OS. |

For tests running in the same process or on the same host, loopback is usually appropriate. If the test process reaches the service across a Docker bridge or another host, choose a host/interface routable from the test process.

Do not assume `localhost` always resolves to IPv4. On some machines, it may prefer IPv6. If a server binds only `127.0.0.1` while the client connects to `::1`, the connection can fail. Use a hostname matching the bind address or configure both families explicitly if needed.

## 12. Reading the Port of a Custom Server Using `ServerSocketChannel`

With NIO, `ServerSocketChannel` also allows binding port 0:

~~~java
import java.io.IOException;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.SocketAddress;
import java.nio.channels.ServerSocketChannel;

try (ServerSocketChannel channel = ServerSocketChannel.open()) {
    channel.bind(new InetSocketAddress(
        InetAddress.getLoopbackAddress(),
        0
    ));

    SocketAddress actualAddress = channel.getLocalAddress();
    int actualPort = ((InetSocketAddress) actualAddress).getPort();

    System.out.println("Listening on " + actualAddress);
}
~~~

`getLocalAddress()` returns the bound socket address. Only retrieve the port after `bind(...)` succeeds.

## 13. Reactor Netty Server on Port 0

If a test needs to start a standalone Reactor Netty server, you can configure `HttpServer` with port 0 and read the port after binding:

~~~java
import reactor.netty.DisposableServer;
import reactor.netty.http.server.HttpServer;

DisposableServer server = HttpServer.create()
    .host("127.0.0.1")
    .port(0)
    .route(routes -> routes.get("/health",
        (request, response) -> response.sendString(
            reactor.core.publisher.Mono.just("UP")
        )))
    .bindNow();

int actualPort = server.port();
String baseUrl = "http://127.0.0.1:" + actualPort;

try {
    // Use baseUrl to test the HTTP client.
} finally {
    server.disposeNow();
}
~~~

`bindNow()` waits for binding to complete. Afterward, `server.port()` returns the actual port. `disposeNow()` closes the server and releases the port.

Do not read the port from the initial configuration, because the configuration is 0; read it from the server object after binding.

## 14. What Should Be Asserted in Tests?

A test's goal is usually to confirm the server received a valid port and the application can connect to that endpoint. There is no need to assert the exact port number selected by the OS.

Appropriate assertions:

~~~java
assertThat(server.port()).isPositive();
assertThat(server.isRunning()).isTrue();
~~~

With Spring Boot:

~~~java
assertThat(port).isPositive();
assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
~~~

With Testcontainers:

~~~java
assertThat(container.getMappedPort(8080)).isPositive();
assertThat(container.isRunning()).isTrue();
~~~

If the endpoint is part of application configuration, also verify that the real client can call the endpoint and receive the expected response. A positive port only proves a port number exists; it does not prove the service is ready or routes work.

Avoid this assertion:

~~~java
assertThat(port).isEqualTo(49173);
~~~

Assigned ports vary across runs and environments. Tests should verify required properties of the endpoint rather than hardcoding the OS's selection.

## 15. Lifecycle and Cleanup

A server holding a port must be closed when tests finish. For Java sockets, use try-with-resources or `@AfterEach`. For servers with their own lifecycle, invoke the corresponding stop/dispose method.

Example:

~~~java
@AfterEach
void tearDown() throws IOException {
    if (serverSocket != null && !serverSocket.isClosed()) {
        serverSocket.close();
    }
}
~~~

For a server shared across multiple test methods, you can start it in `@BeforeAll` and stop it in `@AfterAll`. Ensure no test is still using the server when teardown begins.

If the Spring `ApplicationContext` caches a bean whose base URL points to the server, the server must live at least as long as the context needs it. Do not stop the resource in `@AfterAll` of one class if the context is reused by another class.

When a server restarts:

1. Close the old instance.
2. Start the new instance with port 0.
3. Read the new port after binding.
4. Update any necessary clients/configuration.

Do not assume the new port equals the old port.

## 16. Common Mistakes

### Using a Fixed Port for All Tests

Multiple processes or parallel tests can collide. Use port 0 if the server supports it and read the actual port after binding.

### Probing a Port and Closing the Socket Before the Server Uses It

This creates a race condition. Let the server itself bind port 0, or pass the already-bound socket if the API supports it.

### Reading `getLocalPort` Before Binding

On an unbound `ServerSocket`, the port value is not yet a valid endpoint. Call `bind(...)` first before reading `getLocalPort()`.

### Pointing Clients at Port 0

Port 0 is only an instruction for the bind operation. Clients must use the actual port returned by the server after binding.

### Reading the Port from Configuration Instead of the Server

If configuration specifies 0, that is not the real port. Use `@LocalServerPort`, `WireMockServer.port()`, `DisposableServer.port()`, or the resource's corresponding API.

### Confusing Container Port with Host Port

A container may listen on 8080 while the mapped host port is a different number. Use `getMappedPort(8080)` and `getHost()`.

### Treating an Open Port as Service Ready

A socket can start listening before the application finishes initialization. Use a health endpoint or appropriate readiness condition.

### Closing the Server Before Tests Finish

Clients may receive connection refused errors between tests. Synchronize the server lifecycle with the tests and `ApplicationContext` using it.

### Asserting a Specific Port Number

The operating system may assign a different port on every run. Assert that the port is valid and reachable, not a fixed port number.

## 17. Port Selection Workflow for Tests

When a test needs to open a server or network resource:

1. Identify the resource's port-binding API.
2. If supported, configure port 0 or the official dynamic port mode.
3. Start and wait for binding to complete.
4. Read the actual port from the server/container object.
5. Build the base URL or client configuration from that actual endpoint.
6. Verify service readiness with a health check if needed.
7. Run tests without assuming any specific port number.
8. Close the resource once all consumers have finished.

If the resource is Spring Boot's embedded server, use `WebEnvironment.RANDOM_PORT` and `@LocalServerPort`. If it is WireMock, use `dynamicPort()` and read `port()` after starting. If it is a container, use port mapping and read `getMappedPort(...)` after starting. If writing your own Java server, bind the socket to port 0 and read `getLocalPort()`.

The core principle is **letting the listening component itself perform the bind with port 0 and hold that socket**, then publishing the endpoint assigned by the OS. This eliminates race conditions caused by probing for free ports, reduces conflicts during parallel test runs, and makes integration tests more reliable across both developer machines and CI.
