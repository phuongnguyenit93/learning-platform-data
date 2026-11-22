# Cổng ngẫu nhiên do máy chủ cấp thay vì tự đoán cổng trống

Khi viết kiểm thử tích hợp, một HTTP server, database proxy hoặc dịch vụ phụ trợ thường cần một TCP port để lắng nghe. Nếu nhiều test chạy cùng lúc hoặc nhiều tiến trình cùng dùng máy phát triển, việc cố định một cổng như 8080, 5432 hay 9090 dễ gây xung đột.

Một cách an toàn là để **chính server yêu cầu hệ điều hành cấp một cổng trống tại thời điểm bind**. Trong Java, giá trị port `0` có ý nghĩa đặc biệt: khi socket bind với port 0, hệ điều hành chọn một ephemeral port còn dùng được và gắn nó vào socket. Sau khi bind thành công, ứng dụng đọc lại port thực tế từ socket hoặc server.

Đây là điểm khác biệt quan trọng giữa:

- **Server tự bind port 0 rồi đọc port đã cấp:** việc chọn và chiếm port diễn ra trong cùng thao tác bind, tránh khoảng trống giữa kiểm tra và sử dụng.
- **Test dò một port có vẻ đang trống, đóng socket rồi bảo server dùng port đó:** port có thể bị tiến trình khác chiếm trong khoảng thời gian giữa hai thao tác.

## 1. Vì sao không nên tự đoán hoặc dò cổng trống?

Giả sử test cần mở một HTTP server trên port 8080. Nếu một ứng dụng khác đã dùng cổng đó, server test không thể bind và test thất bại. Có thể thử port 8081, 8082 hoặc một số khác, nhưng cách này vẫn dựa trên giả định rằng cổng đã chọn còn trống.

Một cách thường thấy là mở `ServerSocket(0)` để hỏi hệ điều hành một port trống, lấy port đó, đóng socket rồi truyền port vào server thật:

~~~java
int port;
try (ServerSocket socket = new ServerSocket(0)) {
    port = socket.getLocalPort();
}

// Sau khi socket đã đóng, một tiến trình khác có thể chiếm port này.
startHttpServer(port);
~~~

Đoạn code có race condition. Khi `ServerSocket` đóng, port được giải phóng. Trước khi `startHttpServer(port)` bind, một tiến trình khác có thể lấy đúng port đó. Test có thể chạy tốt trên máy cá nhân nhưng thất bại ngẫu nhiên trong CI hoặc khi chạy song song.

Vấn đề này được gọi là **TOCTOU (time of check to time of use)**: tài nguyên được kiểm tra ở một thời điểm, nhưng chỉ được sử dụng sau đó. Trạng thái của tài nguyên có thể thay đổi giữa hai thời điểm.

~~~text
Test A                          Hệ điều hành / Test B
  |                                      |
  | bind port 0                          |
  |------------------------------------->|
  | nhận port 49173                      |
  |                                      |
  | đóng socket, port được giải phóng    |
  |                                      |
  |                                      | Test B bind port 49173
  |                                      |-------------------->
  | start server trên 49173              |
  |------------------------------------->|
  | bind thất bại: address already in use|
~~~

Giải pháp tốt nhất là để server thật tự bind port 0, rồi lấy port mà server đang giữ. Khi đó không có bước “dò rồi nhả” trước khi server sử dụng.

## 2. Port 0 có ý nghĩa gì?

Trong API socket của Java, port 0 không có nghĩa là server sẽ lắng nghe trên cổng 0. Nó có nghĩa là yêu cầu hệ điều hành chọn một cổng phù hợp khi bind.

Ví dụ:

~~~java
ServerSocket serverSocket = new ServerSocket(0);
int actualPort = serverSocket.getLocalPort();
~~~

Sau khi constructor bind thành công:

- `serverSocket.getLocalPort()` trả về port thực tế được cấp.
- Port thực tế là một số dương trong dải ephemeral port mà hệ điều hành quản lý.
- ServerSocket tiếp tục giữ port đó cho tới khi socket đóng.
- Không nên giả định lần chạy tiếp theo sẽ nhận cùng một port.

Nếu tạo một socket chưa bind:

~~~java
ServerSocket socket = new ServerSocket();
int portBeforeBind = socket.getLocalPort(); // -1 khi chưa bind
socket.bind(new InetSocketAddress(0));
int actualPort = socket.getLocalPort();
~~~

Chỉ đọc port sau khi bind thành công. Với `ServerSocket(0)`, bind đã diễn ra ngay trong constructor. Với socket tạo rỗng, phải gọi `bind(...)` trước.

Port 0 là yêu cầu ở phía server/socket bind. Client không kết nối tới `localhost:0`; client phải dùng port thực tế được đọc sau khi server bind.

## 3. Ví dụ JDK ServerSocket tự nhận port

Ví dụ sau tạo một TCP server lắng nghe trên loopback interface với port do hệ điều hành cấp:

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

Sử dụng:

~~~java
try (RandomPortServer server = new RandomPortServer()) {
    int actualPort = server.port();
    System.out.println("Server is bound to port " + actualPort);
    // Tiếp tục xử lý kết nối trong khi serverSocket vẫn mở.
}
~~~

`InetAddress.getLoopbackAddress()` giới hạn socket vào loopback interface, phù hợp với server chỉ phục vụ test chạy trên cùng máy. Nếu cần nhận kết nối từ container hoặc máy khác, phải chọn interface phù hợp với môi trường. Không nên bind tất cả interface một cách tùy tiện chỉ để test kết nối local.

Trong ví dụ trên, socket đã giữ port sau khi constructor hoàn tất. Nếu một HTTP server khác cần dùng port này, không thể đóng socket rồi hy vọng server kia sẽ chiếm được đúng port. Cần để chính HTTP server bind port 0, hoặc dùng API có khả năng nhận một socket/channel đã bind nếu thư viện hỗ trợ.

### Với DatagramSocket

UDP cũng có cơ chế tương tự:

~~~java
try (DatagramSocket socket = new DatagramSocket(0)) {
    int actualPort = socket.getLocalPort();
    // Gửi hoặc nhận datagram trong khi socket còn mở.
}
~~~

Port được cấp cho UDP socket độc lập với TCP port cùng số. Một TCP socket và một UDP socket có thể cùng dùng số port mà không nhất thiết xung đột vì chúng thuộc hai giao thức transport khác nhau.

## 4. Kiểm thử trực tiếp với port ngẫu nhiên

Với JUnit, có thể khởi động server trong `@BeforeEach` hoặc `@BeforeAll`, sau đó đọc port thực tế trong test:

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

Test xác nhận socket đã bind và có port dương. Không nên assert một con số cố định hoặc giả định port luôn nằm trong một khoảng cụ thể, vì dải ephemeral port phụ thuộc hệ điều hành và cấu hình máy.

Trong test thực tế, thay `ServerSocket` bằng server HTTP hoặc resource mà ứng dụng đang sử dụng. Điều quan trọng là port phải được cấp bởi thao tác bind của chính resource đó.

## 5. Spring Boot embedded server với RANDOM_PORT

Spring Boot hỗ trợ khởi động embedded web server trên một port ngẫu nhiên thông qua:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
~~~

`RANDOM_PORT` yêu cầu embedded server bind vào port ngẫu nhiên do hệ điều hành cấp. Test có thể đọc port thực tế bằng `@LocalServerPort`:

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

Với Spring Boot 3, `@LocalServerPort` nằm trong package `org.springframework.boot.test.web.server`. Ở các phiên bản Boot cũ, package annotation có thể khác; hãy dùng package tương ứng với phiên bản dự án.

Khi dùng `RANDOM_PORT`, Spring Boot khởi động server thật trong test process. Test gửi request qua HTTP tới embedded server. Điều này khác với MockMvc, nơi request được thực thi qua Spring MVC mà không cần bind TCP port.

Có thể cấu hình tương đương bằng property:

~~~properties
server.port=0
~~~

hoặc truyền property khi chạy ứng dụng. Với test Spring Boot, `webEnvironment = RANDOM_PORT` diễn đạt ý định rõ ràng và cung cấp port đã bind qua `@LocalServerPort`.

### Phân biệt RANDOM_PORT và DEFINED_PORT

| WebEnvironment | Hành vi |
|---|---|
| `MOCK` | Tạo mock web environment; không khởi động server thật. |
| `RANDOM_PORT` | Khởi động server thật trên port ngẫu nhiên. |
| `DEFINED_PORT` | Khởi động server trên port được cấu hình, thường là `server.port`. |
| `NONE` | Không tạo web environment. |

Chọn `RANDOM_PORT` khi cần kiểm thử qua HTTP thật nhưng không muốn phụ thuộc một cổng cố định.

## 6. Đọc port sau khi embedded server đã bind

Trong Spring Boot integration test, `@LocalServerPort` được inject sau khi web server khởi động. Không cố đọc port trước khi server bind hoặc tự tìm một port trống để truyền vào `server.port`.

Ví dụ dùng URI động:

~~~java
URI baseUri = URI.create("http://localhost:" + port);
~~~

Nếu test dùng `TestRestTemplate` được Boot cung cấp, có thể gọi URI tương đối:

~~~java
restTemplate.getForEntity("/health", String.class);
~~~

`TestRestTemplate` được cấu hình để gọi embedded server của test. Nếu tự tạo `RestClient` hoặc `WebClient`, hãy tạo base URL từ port được inject sau khi server đã sẵn sàng.

Không cache một base URL được tạo từ port cũ nếu server được khởi động lại. Port mới chỉ có sau lần bind mới và cần được đọc lại.

## 7. WireMock tự chọn port

WireMock có API `dynamicPort()` để server tự chọn cổng khi start:

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

`dynamicPort()` cấu hình WireMock chọn port trong lúc server start. Chỉ đọc `port()` hoặc `baseUrl()` sau `start()`. Không truyền một port tự dò trước đó vào WireMock nếu không có lý do đặc biệt.

Nếu Spring bean cần base URL của WireMock ngay khi ApplicationContext được tạo, cần bảo đảm WireMock start trước khi Spring đọc property. Có thể quản lý tài nguyên bằng lifecycle phù hợp hoặc đăng ký supplier qua `@DynamicPropertySource`; supplier chỉ đọc địa chỉ, còn thao tác start vẫn phải xảy ra trước.

## 8. Testcontainers: port container và mapped host port

Testcontainers cũng dùng port mapping động. Container có thể lắng nghe trên một port cố định bên trong container, nhưng Docker ánh xạ port đó sang một port ngẫu nhiên trên host.

Ví dụ:

~~~text
Trong container:
  HTTP server lắng nghe :8080

Trên host:
  Docker ánh xạ 49173 -> container:8080

Client từ test process:
  http://<host>:49173
~~~

Ví dụ code:

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

`getMappedPort(8080)` chỉ có thể được gọi sau khi container đã start. `getHost()` trả host mà test process có thể dùng để truy cập container; trong một số môi trường CI hoặc Docker remote, host này không nhất thiết là `localhost`.

Không nhầm:

- `8080`: port bên trong container.
- `getMappedPort(8080)`: port được ánh xạ ra phía host.
- `getHost()`: hostname/IP để test process truy cập mapping đó.

Testcontainers quản lý việc chọn và bind port host. Không cần tự tìm một port trống rồi truyền vào Docker.

## 9. Port ngẫu nhiên và kiểm thử song song

Port cố định dễ gây xung đột khi:

- Nhiều test class khởi động cùng loại server.
- Build tool chạy nhiều test fork.
- CI chạy nhiều job trên cùng host.
- Developer mở ứng dụng local dùng cùng port.
- Test chạy song song trong cùng JVM.

Khi mỗi server tự bind port 0, hệ điều hành cấp port đang có thể sử dụng tại thời điểm bind. Mỗi server giữ socket riêng, nên việc cấp port được phối hợp ở tầng hệ điều hành thay vì do test tự dò.

Tuy nhiên, random port không tự giải quyết mọi vấn đề đồng thời:

- Hai test vẫn có thể chia sẻ cùng một server instance nếu fixture được khai báo static hoặc singleton.
- Resource có thể bị dừng khi test khác vẫn đang dùng nó.
- Test vẫn có thể đọc nhầm port cũ nếu server restart.
- Một port có thể được tái sử dụng sau khi server đóng; không được giả định port duy nhất trong toàn bộ thời gian chạy máy.

Hãy quản lý riêng cả port lẫn lifecycle của server. Mỗi test cần endpoint đúng của resource mà nó đang sử dụng.

## 10. Vì sao không nên viết hàm findFreePort rồi đóng socket?

Một helper phổ biến:

~~~java
static int findFreePort() throws IOException {
    try (ServerSocket socket = new ServerSocket(0)) {
        return socket.getLocalPort();
    }
}
~~~

Hàm này trả về một port vừa được socket tạm thời giữ, nhưng ngay sau khi thoát try-with-resources, socket đóng và port được giải phóng. Giá trị trả về chỉ là một quan sát tại thời điểm trước đó; nó không phải một reservation có hiệu lực cho server sẽ start sau.

Không dùng nó theo kiểu:

~~~java
int port = findFreePort();
embeddedServer.setPort(port);
embeddedServer.start();
~~~

Khoảng trống giữa `findFreePort()` và `embeddedServer.start()` tạo race condition. Nếu embedded server hỗ trợ port 0, hãy cấu hình trực tiếp port 0 rồi đọc port thật sau khi server khởi động.

Nếu một thư viện không hỗ trợ port 0 nhưng có API nhận socket/channel đã bind, có thể giữ socket đã bind và chuyển chính socket đó cho server. Cách này chỉ áp dụng khi thư viện hỗ trợ chính thức việc nhận socket đã mở; không đóng socket rồi chỉ truyền số port.

Nếu tiến trình ngoài không hỗ trợ cả port 0 lẫn nhận socket đã bind, không có cách dò port trống rồi đóng socket nào bảo đảm tuyệt đối tránh race. Khi đó nên xem xét thay đổi cách khởi chạy dịch vụ, dùng port mapping của container hoặc cơ chế điều phối tài nguyên phù hợp.

## 11. Chọn địa chỉ bind phù hợp

Port là một phần của endpoint. Ngoài port, server còn cần chọn network interface/address:

| Địa chỉ bind | Ý nghĩa thường gặp |
|---|---|
| `127.0.0.1` | Chỉ nhận kết nối IPv4 loopback từ cùng host. |
| `::1` | Chỉ nhận kết nối IPv6 loopback từ cùng host. |
| `InetAddress.getLoopbackAddress()` | Địa chỉ loopback phù hợp với môi trường JVM. |
| `0.0.0.0` | Lắng nghe trên mọi interface IPv4. |
| `::` | Lắng nghe trên mọi interface IPv6; hành vi dual-stack phụ thuộc hệ điều hành. |

Với test chạy trong cùng process hoặc cùng host, loopback thường là lựa chọn phù hợp. Nếu test process truy cập dịch vụ qua Docker bridge hoặc host khác, phải chọn host/interface mà test process có thể định tuyến tới.

Đừng mặc định rằng `localhost` luôn phân giải thành IPv4. Trên một số máy, nó có thể ưu tiên IPv6. Nếu server chỉ bind `127.0.0.1` nhưng client kết nối tới `::1`, kết nối có thể thất bại. Hãy dùng hostname phù hợp với địa chỉ bind hoặc cấu hình rõ ràng cả hai family nếu cần.

## 12. Đọc port của server tự viết bằng ServerSocketChannel

Với NIO, `ServerSocketChannel` cũng cho phép bind port 0:

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

`getLocalAddress()` trả địa chỉ socket đã bind. Chỉ lấy port sau khi `bind(...)` thành công.

## 13. Reactor Netty server trên port 0

Nếu test cần khởi động một server Reactor Netty độc lập, có thể cấu hình `HttpServer` dùng port 0 rồi đọc port sau khi bind:

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
    // Dùng baseUrl để kiểm thử HTTP client.
} finally {
    server.disposeNow();
}
~~~

`bindNow()` chờ bind hoàn tất. Sau đó `server.port()` trả port thực tế. `disposeNow()` đóng server và giải phóng port.

Không lấy port từ cấu hình ban đầu, vì cấu hình là 0; phải lấy từ đối tượng server sau bind.

## 14. Kiểm tra gì trong test?

Mục tiêu của test thường là xác nhận server đã nhận một port hợp lệ và ứng dụng có thể kết nối tới endpoint đó. Không cần kiểm tra port cụ thể mà hệ điều hành đã chọn.

Các assertion phù hợp:

~~~java
assertThat(server.port()).isPositive();
assertThat(server.isRunning()).isTrue();
~~~

Với Spring Boot:

~~~java
assertThat(port).isPositive();
assertThat(response.getStatusCode().is2xxSuccessful()).isTrue();
~~~

Với Testcontainers:

~~~java
assertThat(container.getMappedPort(8080)).isPositive();
assertThat(container.isRunning()).isTrue();
~~~

Nếu endpoint là một phần của cấu hình ứng dụng, kiểm tra thêm client thật có gọi được endpoint và nhận response mong đợi. Một port dương chỉ chứng minh có một con số port; nó không tự chứng minh dịch vụ đã ready hoặc route hoạt động.

Tránh assertion:

~~~java
assertThat(port).isEqualTo(49173);
~~~

Port được cấp thay đổi theo lần chạy và môi trường. Test nên xác nhận thuộc tính cần thiết của endpoint thay vì cố định kết quả lựa chọn của hệ điều hành.

## 15. Vòng đời và dọn dẹp

Server đang giữ port phải được đóng khi test kết thúc. Với Java socket, dùng try-with-resources hoặc `@AfterEach`. Với server có lifecycle riêng, gọi phương thức stop/dispose tương ứng.

Ví dụ:

~~~java
@AfterEach
void tearDown() throws IOException {
    if (serverSocket != null && !serverSocket.isClosed()) {
        serverSocket.close();
    }
}
~~~

Với server dùng chung giữa nhiều test method, có thể khởi động ở `@BeforeAll` và dừng ở `@AfterAll`. Cần chắc chắn không có test nào đang sử dụng server khi teardown bắt đầu.

Nếu Spring ApplicationContext cache bean có base URL trỏ tới server, server phải sống ít nhất bằng thời gian context cần dùng nó. Không dừng resource trong `@AfterAll` của một lớp nếu context còn được tái sử dụng bởi lớp khác.

Khi server restart:

1. Đóng instance cũ.
2. Khởi động instance mới với port 0.
3. Đọc port mới sau khi bind.
4. Cập nhật client/configuration cần thiết.

Không giả định port mới bằng port cũ.

## 16. Các lỗi thường gặp

### Dùng port cố định cho mọi test

Nhiều tiến trình hoặc test song song có thể tranh chấp. Dùng port 0 nếu server hỗ trợ và đọc port thực tế sau bind.

### Dò port rồi đóng socket trước khi server dùng

Đây là race condition. Hãy để chính server bind port 0 hoặc chuyển socket đã bind nếu API hỗ trợ.

### Đọc getLocalPort trước khi bind

Với ServerSocket chưa bind, giá trị port chưa phải endpoint hợp lệ. Gọi `bind(...)` trước rồi mới đọc `getLocalPort()`.

### Cho client kết nối tới port 0

Port 0 chỉ là yêu cầu dành cho thao tác bind. Client phải dùng port thực tế mà server trả về sau khi bind.

### Đọc port từ cấu hình thay vì server

Nếu cấu hình là 0, đó không phải port thực tế. Dùng `@LocalServerPort`, `WireMockServer.port()`, `DisposableServer.port()` hoặc API tương ứng của resource.

### Nhầm container port với host port

Container có thể lắng nghe ở 8080 nhưng host port được ánh xạ là một số khác. Dùng `getMappedPort(8080)` và `getHost()`.

### Kiểm tra port đã mở rồi coi là service ready

Socket có thể lắng nghe trước khi ứng dụng hoàn tất khởi tạo. Dùng health endpoint hoặc readiness condition phù hợp.

### Đóng server trước khi test hoàn tất

Client có thể nhận connection refused giữa các test. Đồng bộ lifecycle của server với test và ApplicationContext sử dụng nó.

### Assert port bằng một con số cụ thể

Hệ điều hành có quyền chọn port khác nhau ở mỗi lần chạy. Kiểm tra port hợp lệ và khả năng kết nối, không kiểm tra số port cố định.

## 17. Quy trình chọn cổng cho test

Khi một test cần mở server hoặc tài nguyên mạng:

1. Xác định API bind port của tài nguyên.
2. Nếu có hỗ trợ, cấu hình port 0 hoặc chế độ dynamic port chính thức.
3. Khởi động và chờ bind hoàn tất.
4. Đọc port thực tế từ đối tượng server/container.
5. Tạo base URL hoặc cấu hình client từ endpoint thực tế đó.
6. Kiểm tra service sẵn sàng bằng health check nếu cần.
7. Chạy test mà không giả định số port cụ thể.
8. Đóng resource khi mọi consumer đã dùng xong.

Nếu tài nguyên là embedded server của Spring Boot, dùng `WebEnvironment.RANDOM_PORT` và `@LocalServerPort`. Nếu là WireMock, dùng `dynamicPort()` và đọc `port()` sau start. Nếu là container, dùng port mapping và đọc `getMappedPort(...)` sau start. Nếu tự viết server bằng Java, bind socket vào port 0 rồi đọc `getLocalPort()`.

Nguyên tắc cốt lõi là **để thành phần sẽ lắng nghe tự thực hiện thao tác bind với port 0 và giữ socket đó**, sau đó công bố endpoint mà hệ điều hành đã cấp. Cách này tránh race condition do tự dò port trống, giảm xung đột khi chạy test song song và làm cho kiểm thử tích hợp ổn định hơn trên máy phát triển lẫn CI.
