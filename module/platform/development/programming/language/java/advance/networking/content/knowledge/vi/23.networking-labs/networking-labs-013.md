# Lập bảng tương thích JDK, giao thức và API cho ví dụ có thể tái lập

## 1. Mục tiêu và nguyên tắc lập bảng tương thích

Một ví dụ Java networking “chạy được” có thể được hiểu theo nhiều nghĩa khác nhau: **biên dịch được trên một JDK**, **chạy được trên runtime đích**, **kết nối thật sự tới peer** và **thương lượng đúng giao thức cần kiểm chứng**. Đây là bốn tiêu chí phải phân biệt khi lập bảng tương thích.

Ví dụ `HttpClient.Version.HTTP_2` tồn tại nhưng peer chỉ phản hồi HTTP/1.1; `SSLContext` có TLSv1.3 trong danh sách supported nhưng handshake thực tế dùng TLSv1.2; mã `UnixDomainSocketAddress` biên dịch ở Java 17 nhưng không thể bind trên OS hạn chế; hoặc `--release 8` biên dịch thành công trên JDK 24 nhưng chưa hề được chạy trên JVM 8.

Bài Knowledge này cung cấp **bảng tương thích JDK × giao thức × API × bằng chứng**, kèm **bốn chương trình Java độc lập** kiểm thử trên loopback/capability:

- `NetworkBaseline8.java`: TCP và UDP echo trên `127.0.0.1`, source/API tương thích Java 8.
- `HttpClientCompatibility11.java`: `HttpClient` + `HttpServer` HTTP/1.1, capability API HTTP/2/WebSocket, danh sách supported JSSE TLS.
- `UnixDomainApi17.java`: kiểm tra API Unix-domain address có thể biên dịch với target Java 17.
- `VirtualThreadApi21.java`: virtual-thread executor chính thức từ Java 21.

**Phạm vi thực nghiệm đã xác nhận:** cả bốn source **biên dịch** với `--release 8/11/17/21` tương ứng và **chạy bằng OpenJDK 24.0.2**. Điều này **không** chứng minh đã chạy trên JVM 8/11/17/21 thật, cũng **không** chứng minh đã thương lượng HTTP/2, WebSocket hoặc TLS handshake. Bảng phải ghi trung thực những gì đo được.

## 2. Ba tầng tương thích và một điều kiện môi trường

| Tầng | Câu hỏi | Cách kiểm chứng | Sai lầm cần tránh |
| --- | --- | --- | --- |
| **Source + API** | Compiler target có API và cú pháp không? | `javac --release N`, official API `Since` | Nhìn `java -version` rồi đoán source target |
| **Class file + runtime** | Runtime thật có chạy bytecode và API không? | Chạy `java` bằng phiên bản đích, kiểm exit/exception | Tưởng `--release 8` trên JVM24 là đã test JVM8 |
| **Protocol negotiated** | Hai bên dùng TCP/UDP/HTTP1.1/HTTP2/TLS version đúng chưa? | Echo bytes, `HttpResponse.version()`, `SSLSession.getProtocol()` | Đồng nhất cấu hình preference và giao thức thực |
| **Environment** | OS/JDK vendor/cert/network có cho phép không? | Ghi metadata, peer config, timeouts, bind address | Quy kết mọi lỗi sang API hoặc JDK version |

**Compile PASS không bằng Runtime PASS; Runtime PASS không bằng Protocol PASS.** Một socket kết nối thành công không tự có HTTP request hợp lệ. Một HTTP request 200 chưa chứng minh HTTP/2 nếu response đang là HTTP/1.1. Một TLS provider hỗ trợ TLS1.3 chưa chứng minh peer đã negotiate TLS1.3.

Nên ghi riêng các trường `compiler`, `target_release`, `runtime`, `requested_protocol`, `observed_protocol`, `peer`, `OS`, `status` và `evidence`.

## 3. Bảng tương thích JDK theo phiên bản phát hành

Bảng cập nhật tại **01/11/2026**: Java **27 đã phát hành ngày 15/09/2026**; Java **25 là LTS**. JDK 26 phát hành 17/03/2026, JDK25 LTS phát hành 16/09/2025. Các phiên bản sau tiếp tục cung cấp các API ổn định của các phiên bản trước, nhưng vẫn cần test lại security defaults, module image và hành vi của vendor/build thực tế.

| Dòng JDK | Nhóm | Mốc Java networking đáng chú ý | Chỉ định thử nghiệm |
| --- | --- | --- | --- |
| **8** | LTS, 2014 | `Socket`, `ServerSocket`, `DatagramSocket`, `HttpURLConnection`, `SSLSocket`, core NIO | TCP/UDP/HTTP1.1 client baseline; chưa có `java.net.http` chuẩn |
| **11** | LTS, 2018 | `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse`, `WebSocket`; JSSE triển khai TLS 1.3 | HTTP1.1/HTTP2 **client**, WebSocket client, TLS capability |
| **17** | LTS, 2021 | Bao gồm API Java 11 và Unix-domain socket APIs đã có **từ Java 16** | Unix-domain address API; OS bind/connect test riêng |
| **21** | LTS, 2023 | Virtual threads chính thức; `Executors.newVirtualThreadPerTaskExecutor()`, `Thread.isVirtual()` | Executor/virtual thread test, không thay wire protocol |
| **25** | LTS, 16/09/2025 | Các baseline API ở trên tiếp tục là nguồn hợp lệ | Chạy regression với đúng JDK25/patch/provider |
| **26** | Non-LTS, 17/03/2026 | Các baseline API trên; có thêm thay đổi networking/security tùy release | Test lại runtime và protocol negotiation |
| **27** | Non-LTS, 15/09/2026 | Các baseline API; TLS1.3 được cải tiến hybrid post-quantum key exchange | Test handshake/cipher/group với peer thực, không đoán |

JDK 11 có TLS 1.3 theo JEP 332, nhưng **một số bản cập nhật/vender JDK 8 có thể backport TLS 1.3**, nên không diễn đạt “mọi JDK 8 đều không hỗ trợ TLS 1.3”. Ngược lại, số release lớn hơn không bảo đảm một protocol/cipher cụ thể luôn được bật; security properties, certificates và server quyết định handshake.

JDK 9/10 từng có HTTP client ở dạng incubating. **API ổn định `java.net.http` của bài chọn baseline JDK11**, tránh dùng tên module incubating làm mã có thể tái lập trên các bản JDK khác.

## 4. Bảng tương thích giao thức × API × mức JDK tối thiểu

| Giao thức/khả năng | API phù hợp | Mốc Java dùng ổn định | Điều kiện phía peer | Bằng chứng để đánh dấu PASS |
| --- | --- | --- | --- | --- |
| **TCP stream** | `Socket`, `ServerSocket`, `InputStream`, `OutputStream` | **Java 8 hoặc cũ hơn** | TCP peer hoặc listener local | Connect đúng address/port, echo exact, EOF |
| **UDP datagram** | `DatagramSocket`, `DatagramPacket` | **Java 8 hoặc cũ hơn** | UDP receiver có deadline | Payload/length echo exact, không timeout |
| **HTTP/1.1 legacy client** | `HttpURLConnection` | **Java 8 hoặc cũ hơn** | HTTP/1.1 server | Status/headers/body đúng |
| **HTTP/1.1 modern client** | `HttpClient`, `HttpRequest`, `HttpResponse` | **Java 11** | HTTP server phù hợp | `response.version()==HTTP_1_1` |
| **HTTP/2 client** | `HttpClient.Version.HTTP_2` | **Java 11** | HTTP/2 server và negotiation/ALPN phù hợp | `response.version()==HTTP_2` |
| **JDK HTTP server đơn giản** | `com.sun.net.httpserver.HttpServer` / `jdk.httpserver` | **JDK-specific module từ Java 9** | HTTP client | HTTP/1.1 response thật, không suy ra HTTP/2 server |
| **WebSocket client** | `HttpClient.newWebSocketBuilder()`, `WebSocket` | **Java 11** | RFC6455 WebSocket server | Handshake, frames, receive callbacks, Close |
| **TLS1.2** | `SSLSocket`, `SSLEngine`, `SSLContext` | **Java 8 baseline** | Certificate/trust + TLS peer | `SSLSession.getProtocol()==TLSv1.2` |
| **TLS1.3** | JSSE `SSLContext`, `SSLSession` | **JDK11 implementation**; JDK8 update có thể backport | TLS1.3 peer/cert/cipher policy | Negotiated protocol `TLSv1.3` |
| **NIO TCP channels** | `SocketChannel`, `ServerSocketChannel`, `Selector` | **Java 8 hoặc cũ hơn** | Socket peer | Nonblocking I/O/readiness và bytes đúng |
| **Unix-domain socket** | `UnixDomainSocketAddress`, `StandardProtocolFamily.UNIX`, NIO | **Java 16** | OS/FS/permissions AF_UNIX | Actual bind/connect, không chỉ class presence |
| **Virtual thread cho I/O** | `Executors.newVirtualThreadPerTaskExecutor` | **Java 21** | Không thay network protocol | `Thread.currentThread().isVirtual()` trong task |

**Không nhầm các tầng:** HTTP/2 là protocol, `HttpClient.Version.HTTP_2` là API preference; WebSocket client API không tạo server; `SSLContext` hỗ trợ TLS không có nghĩa handshake thành công. Virtual threads là **công cụ concurrency**, không phải HTTP/3/TCP/UDP protocol mới.

Đối với JDK 8, `com.sun.net.httpserver` từng được phân phối như JDK-specific API nhưng không thuộc Java SE baseline portable; bảng chọn Java 11 khi xây `jdk.httpserver` fixture để tránh phụ thuộc vào khác biệt runtime image của các dòng cũ.

## 5. Mẫu kết quả kiểm thử tương thích nên lưu những gì?

| Cột | Giá trị ví dụ | Ý nghĩa |
| --- | --- | --- |
| `test_id` | `HTTP11-LOCAL-001` | Kịch bản cố định |
| `source_file` | `HttpClientCompatibility11.java` | Tên source thực |
| `compiler_version` | `javac 24.0.2` | Công cụ biên dịch đã dùng |
| `target_release` | `11` | API/bytecode boundary |
| `runtime_version` | `OpenJDK 24.0.2` | JVM thật đã thực thi |
| `vendor/build` | OpenJDK + vendor/build metadata | Security/provider khác nhau |
| `OS/architecture` | Windows x64, Linux x64... | AF_UNIX, firewall, path behavior |
| `requested_protocol` | `HTTP_2` | Preference chưa phải kết quả |
| `observed_protocol` | `HTTP_1_1` | Giao thức server/client thực dùng |
| `endpoint` | `127.0.0.1:<OS port>` | Không hard-code cổng |
| `assertions` | status 200, body exact | Chống PASS giả |
| `result` | PASS/FAIL/SKIP/NOT_TESTED | Phân biệt điều kiện thiếu |
| `exception/exit_code` | 0, `SocketTimeoutException` | Dữ liệu gỡ lỗi |
| `scope` | compile target11 + runtime24 | Giới hạn bằng chứng |

Nếu chưa có runtime 8 thật, **không ghi “runtime8 PASS”** dù compiler JDK24 biên dịch được `--release 8`. Nếu chưa có peer HTTP/2/TLS/WebSocket, ghi `SKIP_NO_PEER` hoặc `API_PRESENT_ONLY`, không đánh đồng API presence với protocol completion.

## 6. `--release`, bytecode và Java runtime

Từ JDK 9, `javac --release N` giới hạn **cú pháp, API public tương ứng và major class file version**. Chỉ dùng `-source N -target N` trên JDK mới mà không khóa platform API có thể vô tình truy cập API chỉ tồn tại ở JDK mới.

~~~bash
# Compiler tương thích target 8, ví dụ javac 24.0.2 đã thử:
javac --release 8 NetworkBaseline8.java
java NetworkBaseline8

# Compiler hỗ trợ release 11/17/21 tương ứng:
javac --release 11 HttpClientCompatibility11.java
javac --release 17 UnixDomainApi17.java
javac --release 21 VirtualThreadApi21.java
~~~

**`java` dùng ở runtime phải hỗ trợ class file/APIs tương ứng**. Một class target21 không chạy trên JVM17. Mã target8 thường có thể chạy trên JVM cao hơn nếu dependencies/behavior phù hợp, nhưng **để chứng minh runtime8, cần chạy bằng đúng JVM8**.

Trên JDK8 compiler chưa có tùy chọn `--release`:

~~~bash
javac NetworkBaseline8.java
java NetworkBaseline8
~~~

Compiler mới có thể cảnh báo target8 đã cũ, và một compiler tương lai có thể bỏ một số target quá cũ. Hãy kiểm `javac --help`. Trong lần test, compiler **24.0.2** chấp nhận `--release 8` nhưng cảnh báo source/target 8 “obsolete”, không phải compile failure.

| Target Java | Class file major version |
| --- | --- |
| 8 | 52 |
| 11 | 55 |
| 17 | 61 |
| 21 | 65 |
| 25 | 69 |
| 26 | 70 |
| 27 | 71 |

Dùng `javap -verbose ClassName` để xem `major version`, nhưng major version **không chứng minh** TLS/HTTP2/OS runtime compatibility.

## 7. Quy tắc môi trường cho ví dụ có thể tái lập

1. **Bind loopback IPv4 `127.0.0.1`** ở hai phía. `localhost` có thể resolve IPv6 `::1` khác với địa chỉ server đã bind.
2. **Bind cổng `0`** để OS tự cấp và lấy cổng thực bằng `getLocalPort()` hoặc `getAddress().getPort()`. Không mở socket tạm lấy port rồi đóng trước khi bind lại, vì có race.
3. Server đã **bind/listen** trước khi client kết nối. Nếu `accept()` là blocking call, chạy server worker và client trên các threads phù hợp.
4. Có **timeouts** cho connect/accept/read/request; tránh test treo vô hạn. `SO_TIMEOUT` không phải toàn phiên deadline.
5. Kiểm **nội dung chính xác**: TCP UTF-8 echo, UDP byte-for-byte, HTTP 200 + body + version.
6. **Đóng sockets/server và executors** trong `finally` hoặc `try-with-resources`.
7. Không in **port ngẫu nhiên** vào stdout cần so khớp exact; in `port > 0`, còn port thật chỉ dùng khi tạo endpoint.
8. Không coi test loopback là bảo đảm delivery/security trên Internet. TCP không giữ message boundary; UDP không đảm bảo delivery/order/uniqueness.

## 8. Chương trình 1 — Java 8 baseline: TCP và UDP thật trên loopback

File `NetworkBaseline8.java` chạy hai trường hợp trong cùng process:

- **TCP:** `ServerSocket(0,16,127.0.0.1)` và một thread xử lý `accept()`. Client kết nối đúng cổng OS cấp, gửi dòng UTF-8 `xin chào`, nhận `ECHO:xin chào`, kiểm exact. `shutdownOutput()` half-close chiều gửi trong khi còn đọc echo.
- **UDP:** `DatagramSocket` receiver cũng bind port 0, nhận bốn byte `{0,1,0xff,10}`, echo đúng `DatagramPacket.getLength()`, client so `Arrays.equals`. UDP packet có thể mất trong mạng thực, vì vậy receive có timeout.

Mã dùng cú pháp/API Java 8, không có `var`, `record`, virtual threads hay `java.net.http`.

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.Socket;
import java.nio.charset.StandardCharsets;
import java.util.Arrays;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class NetworkBaseline8 {
    public static void main(String[] args) throws Exception {
        final InetAddress loopback = InetAddress.getByName("127.0.0.1");
        ExecutorService worker = Executors.newSingleThreadExecutor();
        try {
            try (ServerSocket listener = new ServerSocket(0, 16, loopback)) {
                listener.setSoTimeout(5_000);
                Future<String> served = worker.submit(new Callable<String>() {
                    @Override public String call() throws Exception {
                        try (Socket peer = listener.accept()) {
                            peer.setSoTimeout(5_000);
                            BufferedReader in = new BufferedReader(
                                    new InputStreamReader(peer.getInputStream(),
                                            StandardCharsets.UTF_8));
                            BufferedWriter out = new BufferedWriter(
                                    new OutputStreamWriter(peer.getOutputStream(),
                                            StandardCharsets.UTF_8));
                            String request = in.readLine();
                            out.write("ECHO:" + request);
                            out.newLine();
                            out.flush();
                            return request;
                        }
                    }
                });
                try (Socket client = new Socket()) {
                    client.connect(new InetSocketAddress(
                            loopback, listener.getLocalPort()), 3_000);
                    client.setSoTimeout(5_000);
                    BufferedWriter out = new BufferedWriter(
                            new OutputStreamWriter(client.getOutputStream(),
                                    StandardCharsets.UTF_8));
                    BufferedReader in = new BufferedReader(
                            new InputStreamReader(client.getInputStream(),
                                    StandardCharsets.UTF_8));
                    out.write("xin chào");
                    out.newLine();
                    out.flush();
                    client.shutdownOutput();
                    String answer = in.readLine();
                    if (!"ECHO:xin chào".equals(answer)) {
                        throw new AssertionError("TCP echo mismatch: " + answer);
                    }
                    System.out.println("tcp loopback: "
                            + listener.getInetAddress().isLoopbackAddress());
                    System.out.println("tcp ephemeral port: "
                            + (listener.getLocalPort() > 0));
                    System.out.println("tcp echo: " + answer);
                }
                System.out.println("tcp server request: "
                        + served.get(5, TimeUnit.SECONDS));
            }

            try (DatagramSocket receiver =
                         new DatagramSocket(new InetSocketAddress(loopback, 0))) {
                receiver.setSoTimeout(5_000);
                Future<Integer> served = worker.submit(new Callable<Integer>() {
                    @Override public Integer call() throws Exception {
                        byte[] buffer = new byte[32];
                        DatagramPacket input = new DatagramPacket(buffer, buffer.length);
                        receiver.receive(input);
                        DatagramPacket echoed = new DatagramPacket(
                                input.getData(), input.getLength(),
                                input.getAddress(), input.getPort());
                        receiver.send(echoed);
                        return input.getLength();
                    }
                });
                try (DatagramSocket sender =
                             new DatagramSocket(new InetSocketAddress(loopback, 0))) {
                    sender.setSoTimeout(5_000);
                    byte[] payload = new byte[] {0, 1, (byte) 0xff, 10};
                    sender.send(new DatagramPacket(payload, payload.length,
                            loopback, receiver.getLocalPort()));
                    byte[] receivedBytes = new byte[32];
                    DatagramPacket reply = new DatagramPacket(
                            receivedBytes, receivedBytes.length);
                    sender.receive(reply);
                    byte[] exact = Arrays.copyOf(
                            reply.getData(), reply.getLength());
                    boolean matched = Arrays.equals(payload, exact);
                    if (!matched) throw new AssertionError("UDP echo mismatch");
                    System.out.println("udp ephemeral port: "
                            + (receiver.getLocalPort() > 0));
                    System.out.println("udp echo exact: " + matched);
                }
                System.out.println("udp server bytes: "
                        + served.get(5, TimeUnit.SECONDS));
            }
        } finally {
            worker.shutdownNow();
        }
    }
}
~~~

Chạy bằng compiler mới có `--release 8`:

~~~bash
javac --release 8 NetworkBaseline8.java
java NetworkBaseline8
~~~

Expected stdout đã đo trên **runtime JDK24.0.2**:

~~~text
tcp loopback: true
tcp ephemeral port: true
tcp echo: ECHO:xin chào
tcp server request: xin chào
udp ephemeral port: true
udp echo exact: true
udp server bytes: 4
~~~

Dòng `tcp ephemeral port: true`/`udp ephemeral port: true` không cho biết port luôn giống nhau: số port **do hệ điều hành chọn** và có thể đổi mỗi lần. `udp echo exact: true` chứng minh packet của **lượt test** đã về chính xác, không cam kết UDP không mất packet khi dùng ở môi trường mạng thực.

## 9. Diễn giải kết quả TCP và UDP của chương trình 1

**TCP:** `ServerSocket` là listening socket, `accept()` trả một `Socket` cho kết nối. `BufferedReader.readLine()` dùng newline do **ứng dụng quy định**; TCP bản thân chỉ là luồng byte, không chia message theo mỗi lời gọi `write`. Client `flush()` trước `shutdownOutput()` để truyền hết byte; server viết echo và đóng peer. Client kiểm `ECHO:xin chào` rồi kết thúc.

**UDP:** `DatagramPacket` là một datagram, nhưng OS/network có quyền drop/delay và datagram có giới hạn size. Server gửi về `input.getAddress()/getPort()` của client, phải dùng `input.getLength()` để không echo byte rác ở phần dư buffer. Trong dữ liệu, `(byte)0xff` có giá trị signed `-1` theo Java, **không phải EOF** của `InputStream.read()`. Chúng ta dùng `Arrays.equals` để kiểm bit pattern byte.

**Không hard-code `8080`** khi listener đã bind port `0`. Không kết nối client vào port `0`: số 0 là yêu cầu cấp port tại thời điểm **bind**, không phải địa chỉ peer.

## 10. Chương trình 2 — Java 11 HTTP client và server trên loopback

Từ Java 11, JDK cung cấp API chuẩn `java.net.http.HttpClient`, `HttpRequest`, `HttpResponse` và `WebSocket`. Để kiểm thử HTTP/1.1 thật, chương trình mở một `HttpServer` nội bộ từ module `jdk.httpserver` ở `127.0.0.1:0` rồi gửi một GET bằng `HttpClient.Version.HTTP_1_1`.

Chương trình cũng **kiểm khả năng tồn tại API** enum `HTTP_2` và interface `WebSocket`, đồng thời đọc **danh sách TLS protocols mà provider báo hỗ trợ**. Điều đó **không** thực hiện HTTP/2 request, WebSocket handshake hoặc TLS handshake.

Tạo file `HttpClientCompatibility11.java`:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.WebSocket;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Arrays;
import javax.net.ssl.SSLContext;

public class HttpClientCompatibility11 {
    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(
                new InetSocketAddress("127.0.0.1", 0), 16);
        server.createContext("/probe", (HttpExchange exchange) -> {
            try {
                byte[] bytes = "jdk-httpserver".getBytes(StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type", "text/plain; charset=utf-8");
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream out = exchange.getResponseBody()) {
                    out.write(bytes);
                }
            } finally {
                exchange.close();
            }
        });
        server.start();
        try {
            URI uri = URI.create("http://127.0.0.1:"
                    + server.getAddress().getPort() + "/probe");
            HttpClient client = HttpClient.newBuilder()
                    .connectTimeout(Duration.ofSeconds(3))
                    .version(HttpClient.Version.HTTP_1_1).build();
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .timeout(Duration.ofSeconds(5)).GET().build();
            HttpResponse<String> response = client.send(
                    request, HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            if (response.statusCode() != 200
                    || !response.body().equals("jdk-httpserver")) {
                throw new AssertionError("HTTP response mismatch");
            }
            System.out.println("http status: " + response.statusCode());
            System.out.println("http response protocol: " + response.version());
            System.out.println("http body: " + response.body());
            System.out.println("http2 preference constant: "
                    + HttpClient.Version.HTTP_2);
            System.out.println("websocket client API present: "
                    + (WebSocket.class != null));
            boolean tls13 = Arrays.asList(SSLContext.getDefault()
                    .getSupportedSSLParameters().getProtocols())
                    .contains("TLSv1.3");
            System.out.println("tls13 supported by runtime: " + tls13);
        } finally {
            server.stop(0);
        }
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 11 HttpClientCompatibility11.java
java HttpClientCompatibility11
~~~

Stdout đã kiểm thử trên JDK24.0.2:

~~~text
http status: 200
http response protocol: HTTP_1_1
http body: jdk-httpserver
http2 preference constant: HTTP_2
websocket client API present: true
tls13 supported by runtime: true
~~~

**Dòng `tls13 supported by runtime` có thể khác trên runtime/vendor/security config khác.** Nó là capability probe `SSLContext.getDefault().getSupportedSSLParameters()`, không có TLS connection thật. Khi ghi kết quả matrix, hãy chép **giá trị quan sát trên JVM đang chạy** chứ không ép mọi JVM in “true”.

## 11. HTTP/1.1 và HTTP/2: requested không đồng nghĩa negotiated

Trong chương trình 2, client đặt preference `HTTP_1_1` và server demo trả HTTP/1.1; `response.version()` cho thấy `HTTP_1_1`. Nếu sửa preference thành `HTTP_2`, **không có bảo đảm** server chỉ hỗ trợ HTTP/1.1 sẽ trả HTTP/2. Kết nối có thể fallback hoặc thất bại tùy peer/protocol negotiation.

Ví dụ minh họa trong một HTTP client đã có `request`:

~~~java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2).build();
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
System.out.println(response.version()); // Đây mới là observed protocol.
~~~

*Chưa phải chương trình độc lập; cần request/exception handling và một HTTP/2 server thực sự.*

Với HTTPS, HTTP/2 thường thương lượng qua **ALPN trong TLS**; HTTP cleartext/h2c đòi hỗ trợ tương ứng của peer. **`jdk.httpserver.HttpServer` trong demo là HTTP server đơn giản để thử HTTP/1.1, không phải HTTP/2 test fixture**. Để đánh dấu HTTP2 PASS, dùng HTTP/2 peer phù hợp và assert `response.version()==HTTP_2` sau response thành công.

Cần ghi hai cột riêng: `requested_version=HTTP_2` và `observed_version=HTTP_1_1/HTTP_2`. Không tự chuyển một fallback HTTP/1.1 hợp lệ thành “API HTTP/2 không tồn tại”.

## 12. WebSocket client: class presence khác trao đổi frame

`java.net.http.WebSocket` có từ Java 11 dưới dạng API client. Để kiểm chứng WebSocket phải dùng một WebSocket server RFC6455 thực sự, không chỉ có `WebSocket.class != null`.

Một positive test thực nên: kết nối `buildAsync(uri, listener)` thành công; gửi text/binary và chờ future **gửi**; nhận echo qua `Listener.onText/onBinary` với receive demand `request(n)`; gửi Ping rồi chờ Pong qua `Listener.onPong`; cuối cùng gửi và nhận Close theo protocol. **Future `sendPing` hoàn tất chỉ chứng minh Ping đã gửi**, chưa chứng minh Pong đã nhận.

`HttpServer` HTTP đơn giản không tự trở thành WebSocket server bởi một response 101; server WebSocket còn phải xử lý RFC6455 framing, masking và control frames. Khi chưa dựng peer, ghi **WebSocket API PRESENT, protocol NOT_TESTED**.

## 13. TLS: supported, enabled và negotiated

| Câu hỏi | API/điều kiện | Có chứng minh TLS handshake đã dùng giao thức đó? |
| --- | --- | --- |
| Runtime/provider hỗ trợ TLS1.3? | `SSLContext.getSupportedSSLParameters().getProtocols()` | Không, mới là capability |
| Cấu hình cho phép TLS1.3? | `SSLSocket.getEnabledProtocols()` hoặc `SSLEngine.getEnabledProtocols()` | Chưa, vẫn là candidates |
| TLS handshake với peer đã hoàn tất? | `socket.startHandshake()`, trust/cert hợp lệ | Có phiên thành công, chưa chắc TLS1.3 |
| Phiên đang dùng TLS1.3? | `SSLSession.getProtocol()` sau handshake | **Có**, nếu giá trị là `TLSv1.3` |

Trong một chương trình đã có `SSLSocket socket` được kết nối và xác minh certificate/hostname đúng:

~~~java
socket.startHandshake();
String protocol = socket.getSession().getProtocol();
System.out.println("negotiated TLS protocol: " + protocol);
~~~

*Đoạn minh họa phụ thuộc peer và cấu hình TLS; không có stdout cố định, không phải một chương trình tự chạy.*

JDK11 đưa implementation TLS1.3 vào JSSE theo JEP332; backport/vendor update ở JDK8 có thể khác nhau. JDK27 cập nhật hybrid post-quantum key exchange cho TLS1.3 nhưng **không** chứng minh mọi phiên giao tiếp đều dùng thuật toán đó: cần xem negotiated details ở peer/provider và điều kiện security policy. Không tắt xác thực TLS, không dùng trust-all trong test.

## 14. Chương trình 3 — Unix-domain socket API với Java 17

`UnixDomainSocketAddress` có **Since 16**; bài dùng baseline **`--release 17`** vì đó là một dòng LTS tiện so sánh. Tạo file `UnixDomainApi17.java`:

~~~java
import java.net.StandardProtocolFamily;
import java.net.UnixDomainSocketAddress;
import java.nio.file.Path;

public class UnixDomainApi17 {
    public static void main(String[] args) {
        UnixDomainSocketAddress address =
                UnixDomainSocketAddress.of(Path.of("network-demo.sock"));
        System.out.println("unix address API: "
                + address.getClass().getSimpleName());
        System.out.println("unix family enum: "
                + StandardProtocolFamily.UNIX);
        System.out.println("socket file: "
                + address.getPath().getFileName());
    }
}
~~~

Chạy:

~~~bash
javac --release 17 UnixDomainApi17.java
java UnixDomainApi17
~~~

Stdout:

~~~text
unix address API: UnixDomainSocketAddress
unix family enum: UNIX
socket file: network-demo.sock
~~~

**Điều được kiểm thử:** compiler target17 và runtime JDK24 nhận dạng lớp address/enum. **Điều không được kiểm thử:** OS có hỗ trợ/cho phép AF_UNIX bind/connect không, đường dẫn socket file có quyền/độ dài phù hợp không. Để xác minh runtime Unix socket thật, thêm server/client `ServerSocketChannel`/`SocketChannel` trên `StandardProtocolFamily.UNIX` và test cleanup trên OS đang chạy.

Nếu biên dịch cùng source `UnixDomainApi17.java` bằng `--release 11`, compiler **phải từ chối** những symbol API xuất hiện từ Java16. Đó là một negative compile gate hữu ích, không phải lỗi networking.

## 15. Chương trình 4 — Virtual threads Java 21

Virtual threads thành API chính thức từ **Java 21**. Chúng có thể giúp xử lý nhiều blocking socket operations với chi phí quản thread phù hợp, nhưng không thay đổi packet TCP/UDP, framing HTTP, TLS handshake hoặc yêu cầu backpressure.

Tạo file `VirtualThreadApi21.java`:

~~~java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

public class VirtualThreadApi21 {
    public static void main(String[] args) throws Exception {
        try (ExecutorService executor =
                     Executors.newVirtualThreadPerTaskExecutor()) {
            Future<Boolean> task = executor.submit(
                    () -> Thread.currentThread().isVirtual());
            System.out.println("virtual thread: "
                    + task.get(5, TimeUnit.SECONDS));
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 21 VirtualThreadApi21.java
java VirtualThreadApi21
~~~

Stdout:

~~~text
virtual thread: true
~~~

`Executors.newVirtualThreadPerTaskExecutor()` và `Thread.isVirtual()` không tồn tại trong public API target Java17. Cùng source với `--release 17` phải compile FAIL, ngay cả nếu compiler chính đang dùng là JDK24. Runtime phải là Java21+ mới chạy class file level65. Trong ứng dụng TCP server thật, số virtual threads không tự giới hạn connections/body bytes; vẫn cần quota và bounded resource policy.

## 16. Negative compile gates: test những gì phải bị từ chối

Một ma trận tương thích chính xác có cả **positive** và **negative** gates:

~~~bash
# FAIL là kết quả đúng vì java.net.http không thuộc Java 8:
javac --release 8 HttpClientCompatibility11.java

# FAIL là kết quả đúng vì UnixDomainSocketAddress Since 16:
javac --release 11 UnixDomainApi17.java

# FAIL là kết quả đúng vì virtual-thread APIs chính thức từ 21:
javac --release 17 VirtualThreadApi21.java
~~~

Trong QA đã xác nhận **hai phép thử cuối** có exit code nonzero, nghĩa là compiler từ chối API đúng khi bị giới hạn về release. Để CI không coi compile-failure là thất bại toàn job, negative-gate test phải mong đợi nonzero exit code nhưng cũng kiểm nguyên nhân missing APIs; **không chỉ accept mọi nonzero do syntax error**.

Không cố so khớp text lỗi nguyên văn của compiler vì wording có thể thay đổi theo JDK/vendor. Biên dịch từng gate vào thư mục khác nhau để không lưu lại class files cũ và vô tình chạy artifact từ build trước.

## 17. Module system và khả năng thiếu module ở runtime

Java 8 chưa có `module-info.java`. Java 9+ có module system, với code HTTP client/server trong **named module** cần khai báo đúng:

~~~java
module demo.network {
    requires java.net.http;
    requires jdk.httpserver;
}
~~~

*Đây là mẫu `module-info.java` cho module chứa hai nhóm API, không phải Java main program độc lập.*

`java.base` chứa `Socket`/`ServerSocket`/`DatagramSocket`/JSSE và được đọc tự động. `java.net.http` chứa HTTP/WebSocket client. `jdk.httpserver` là JDK-specific module từ Java 9, xuất `com.sun.net.httpserver`. Khi ví dụ đơn giản chạy trên **classpath**, không cần cung cấp module descriptor như trên.

Nếu runtime được đóng gói bằng `jlink` và thiếu `java.net.http`/`jdk.httpserver`, chương trình có thể gặp lỗi module/class resolution dù source compile trên JDK đầy đủ. Khi đó phân loại là **packaging/runtime-image mismatch**, không phải HTTP transport failure.

## 18. Ma trận bằng chứng đã kiểm thử trên toolchain thực tế

| Chương trình/gate | Compile target | Runtime/khả năng đã thực sự đo | Trạng thái |
| --- | --- | --- | --- |
| `NetworkBaseline8` | `--release 8` | JVM24.0.2: TCP loopback Unicode echo, UDP byte echo | **PASS cho compile8 + run24**, không phải run8 |
| `HttpClientCompatibility11` | `--release 11` | JVM24.0.2: HTTP 200/HTTP_1_1, WebSocket API, TLS supported flag | **PASS cho compile11 + run24** |
| `UnixDomainApi17` | `--release 17` | JVM24.0.2: address + enum API | **PASS API-only**, chưa bind Unix socket |
| `VirtualThreadApi21` | `--release 21` | JVM24.0.2: task chạy virtual thread | **PASS compile21 + run24** |
| Unix API biên dịch release11 | `--release 11` | Compiler từ chối API chưa tồn tại | **EXPECTED FAIL / gate PASS** |
| Virtual thread source release17 | `--release 17` | Compiler từ chối APIs Java21 | **EXPECTED FAIL / gate PASS** |
| HTTP/2 network | API available | Chưa có HTTP2 peer trong bài | **NOT_TESTED**, không báo negotiated |
| WebSocket network | API available | Chưa mở WebSocket server trong bài | **NOT_TESTED**, không báo echo |
| TLS handshake | Provider supports TLSv1.3 | Chưa có TLS peer/cert/trust trong bài | **NOT_TESTED**, không báo negotiated |
| Unix-domain socket transport | Unix address object hiện diện | Chưa thử AF_UNIX bind/connect | **NOT_TESTED** |

Đây là điểm học thuật quan trọng nhất của bài: **biết đặt nhãn cho bằng chứng**. Không thể thay dấu “NOT_TESTED” bằng “PASS” vì API class đã được import. Không thể coi một test chạy trên JDK24 là test chạy trên JDK8 nếu bytecode được build với release8.

## 19. Kế hoạch chạy CI trên các runtime đích

| CI runtime thật | Những source nên compile/chạy | Ý nghĩa |
| --- | --- | --- |
| **JDK 8** | `NetworkBaseline8` | Chứng minh Java8 runtime TCP/UDP, dùng compiler8 không có `--release` |
| **JDK 11** | Baseline8 + HttpClientCompatibility11 | Kiểm JDK11 HTTP/1.1 và TLS provider của chính JVM11 |
| **JDK 17** | Trên + UnixDomainApi17 | API Unix Since16; có thể test AF_UNIX OS riêng |
| **JDK 21** | Trên + VirtualThreadApi21 | Virtual executor chạy trên JVM21 |
| **JDK 25 LTS** | Tất cả bốn source | Regression trên bản LTS mới, đúng vendor/patch |
| **JDK 27** | Tất cả bốn source | Regression newest release, thêm TLS1.3 peer testing tùy mục tiêu |

Nếu chỉ có compiler JDK24, chạy các lệnh `--release 8/11/17/21` chỉ tạo **compile-target matrix**, không tạo **runtime matrix**. Muốn chứng minh runtime phải chọn binary `java` của phiên bản đó hoặc job CI có JDK image tương ứng. Ghi chính xác `java -version`, `javac -version`, OS và vendor trong artifact; không sử dụng giá trị từ người biên dịch thay cho runtime.

Với dependency bên ngoài JDK, mỗi job phải pin version và kiểm module/API availability. Với security/network experiments, pin certificate/truststore hoặc local peer fixture để tránh lỗi Internet, DNS và TLS certificate ngoài ý muốn.

## 20. Điều kiện PASS/FAIL/SKIP có ích

| Trường hợp | Phân loại đúng | Không nên gọi là |
| --- | --- | --- |
| `cannot find symbol HttpClient` khi target8 | API compatibility compile FAIL | HTTP/2 network FAIL |
| `UnsupportedClassVersionError` | JVM quá cũ so class file | TLS/HTTP server bug |
| `NoClassDefFoundError` vì thiếu module/runtime image | Packaging/JPMS failure | UDP unsupported |
| `BindException` port đã chiếm | Bind/address conflict | JDK không có ServerSocket |
| `ConnectException` | Không kết nối được tới listener/port | API đã bị xóa |
| `SocketTimeoutException` | Quá thời gian chờ connect/accept/read | Server chắc chắn không xử lý |
| UDP echo timeout | Datagram/peer/permissions | Byte arrays không tương thích Java |
| `SSLHandshakeException` | TLS cert/trust/cipher/hostname/protocol | HTTP method GET/POST sai |
| Preferred HTTP_2 nhưng observed HTTP_1_1 | Negotiation/fallback | HttpClient thiếu HTTP/2 API |
| WebSocket handshake rejected | Peer/endpoint/protocol/auth | WebSocket class không tồn tại |
| Unix-domain bind thất bại | OS/filesystem/permission | JDK không chứa address class |
| Virtual thread symbol thiếu ở target17 | Java API gate | TCP stack hỏng |

Một môi trường CI có thể cấm TCP/UDP socket trên loopback, hoặc firewall/namespace thay đổi behavior. Đó là **environment restriction**; ghi nguyên nhân và chọn SKIP nếu policy cho phép, không thay bằng test không mở network rồi tự nhận PASS.

## 21. Security và tính tái lập khi chạy thí nghiệm

- Bind `127.0.0.1` thay vì `0.0.0.0` để không expose server test ra interface bên ngoài. Dù vậy các process không tin cậy cùng host/namespace vẫn có thể cố truy cập loopback.
- Dùng port `0` để OS cấp, rồi client connect **đúng port đã bind**. Đừng mở socket tạm rồi đóng để “giữ chỗ” cổng; có race.
- Không gửi secrets trong TCP plaintext/HTTP; nếu test TLS phải có certificates SAN hợp lệ và truststore đúng, **không dùng trust-all**.
- `Socket.setSoTimeout` giới hạn một lần đọc, không phải tổng thời gian toàn phiên. Bổ sung deadline tổng/body byte limits nếu mở rộng production.
- UDP **không đảm bảo delivery/order/uniqueness**. Test một datagram loopback không thay thế test mạng có packet loss.
- TCP không giữ ranh giới write/read; với nhiều messages cần length-prefix hoặc delimiter và kiểm partial reads.
- Giới hạn worker pool, số connections, payload bytes và thời gian. Dùng try-with-resources/finally để cleanup và không để runner treo.
- Không log token/keystore password/khóa riêng vào test stdout. Vendor/JDK version metadata có thể lưu, nhưng tránh secret environment variables.

## 22. Quy trình tạo một bảng tương thích mới

Đối với một ví dụ mạng khác, làm theo trình tự:

1. **Xác định giao thức** thật cần thử (TCP/UDP/HTTP/2/WebSocket/TLS...).
2. **Chọn API public** và đọc trường `Since` của Javadoc hoặc JEP; đặt minimum JDK hợp lý.
3. **Đặt source/target release** rõ ràng, tách compiler version và runtime version.
4. **Dựng peer local** hoặc ghi chính xác server version/config/TLS cert khi cần remote peer.
5. **Viết test deterministic** với port0, loopback, timeout, assertions byte/status/version và cleanup.
6. **Thêm negative compile gates** ở mức target thấp hơn để phát hiện API mới bị dùng ngoài ý muốn.
7. **Chạy trên runtime thật** của các JDK được tuyên bố hỗ trợ, không chỉ cross-compile.
8. **Đo observed protocol**, không gán bằng requested enum hoặc supported JSSE protocols.
9. **Ghi PASS/FAIL/SKIP/NOT_TESTED** có nguyên nhân, stdout, exception và version.
10. **Tái chạy khi nâng runtime/OS/vendor/protocol peer** để phát hiện thay đổi security defaults hoặc runtime behavior.

Một record minh họa:

~~~text
test_id: HTTP11-LOCAL-001
source: HttpClientCompatibility11.java
compiler: javac 24.0.2
target: --release 11
runtime: OpenJDK 24.0.2
server: jdk.httpserver / 127.0.0.1:ephemeral
expected: 200, HTTP_1_1, body=jdk-httpserver
observed: 200, HTTP_1_1, body=jdk-httpserver
status: PASS
scope: compile Java11 API + run JDK24, NOT a runtime11 test
~~~

## 23. Các câu hỏi tự kiểm tra

**Câu 1.** `javac --release 8` thành công nhưng `java -version` cho biết JVM24. Có thể ghi Java8 runtime PASS không?

*Đáp án:* Không. Đã kiểm compile/API target8 và run JVM24; cần chạy bằng JVM8 để chứng minh runtime8.

**Câu 2.** `HttpClient.Version.HTTP_2` tồn tại và client cấu hình HTTP_2, nhưng response báo HTTP_1_1. Có phải Java không hỗ trợ HTTP/2?

*Đáp án:* Không. API hỗ trợ HTTP/2, nhưng peer/negotiation trên request đó đã dùng HTTP/1.1; cần server HTTP/2 và kiểm `response.version()`.

**Câu 3.** TLSv1.3 nằm trong `getSupportedSSLParameters()`. Có thể ghi “TLSv1.3 negotiated PASS” không?

*Đáp án:* Không. Chưa có handshake thực. Cần `SSLSocket` handshake hợp lệ và `SSLSession.getProtocol()`.

**Câu 4.** `UnixDomainSocketAddress` compile target17 thành công, có đồng nghĩa AF_UNIX socket bind được trên OS hiện tại không?

*Đáp án:* Không. API presence khác runtime OS/FS support; cần bind/connect test.

**Câu 5.** Vì sao `Executors.newVirtualThreadPerTaskExecutor()` không thể dùng với `--release 17`?

*Đáp án:* API virtual threads chính thức từ Java21, không nằm trong API Java17.

**Câu 6.** UDP echo 4 byte PASS ở loopback có chứng minh UDP reliable trên Internet không?

*Đáp án:* Không. UDP không có delivery guarantee; test chứng minh datagram của một lượt local đã đến và echo đúng.

**Câu 7.** Vì sao port 0 hữu ích cho CI?

*Đáp án:* OS cấp cổng còn trống trong lúc bind, giảm collision; client cần connect tới port thực do listener báo, không phải port 0.

**Câu 8.** `UnsupportedClassVersionError` thuộc lỗi API compile, runtime hay TLS?

*Đáp án:* Runtime/bytecode compatibility: JVM không hiểu class file version.

## 24. Bài tập vận dụng

1. Dùng JDK8 **thật** compile/chạy `NetworkBaseline8`, sau đó thử JDK11,17,21,25. Ghi compiler, runtime, OS, stdout, PASS/FAIL.
2. Dùng compiler mới `--release 8` rồi chạy class trên JVM8 thật; so hai loại bằng chứng và chạy `javap -verbose` để xem major52.
3. Trong `HttpClientCompatibility11` đổi HTTP1.1 preference sang HTTP2; đo `response.version()` và giải thích không có HTTP2 server fixture.
4. Dựng một HTTP2-capable HTTPS server test có certificate/trust đúng; kiểm request HTTP2 trả response.version()==HTTP_2.
5. Dựng WebSocket RFC6455 server loopback và client Java11, assert text/binary echo, onPong, Close và receive demand.
6. Tạo TLS test có chứng chỉ SAN hợp lệ, đo `SSLSession.getProtocol()` sau handshake, so với `getSupportedSSLParameters()`.
7. Biên dịch UnixDomainApi17 với `--release 11`, kiểm negative compile gate; bổ sung bind/connect AF_UNIX trên OS cho phép.
8. Biên dịch VirtualThreadApi21 với `--release 17` để thấy expected failure, sau đó chạy target21 bằng JVM21 thật.
9. Thiết kế JSON/CSV matrix có các trường `test_id`, compile/runtime vendor+version, requested/observed protocol, OS, evidence, result.
10. Thử port cố định bị chiếm và port0 cấp động để thấy khác biệt; không dùng time-of-check/time-of-use free-port trick.
11. Thử sai IP family `localhost` IPv6 vs `127.0.0.1` IPv4 và phân loại `ConnectException`, không coi là lỗi API Java.
12. Cố tình chặn UDP response để kiểm timeout; không đánh đồng timeout với “Java không hỗ trợ UDP”.
13. Tạo custom runtime bằng `jlink`, thử thiếu module `java.net.http` hoặc `jdk.httpserver` để nhận diện lỗi module packaging.
14. So sánh JDK25 LTS và JDK27 trên TLS1.3 endpoint đúng; ghi negotiated protocol/cipher/cert, không suy ra hybrid key exchange từ release name.
15. Viết checklist CI đảm bảo **test thực thi từng runtime** thay vì chỉ cross-compile trên một runtime duy nhất.

## Tài liệu tham khảo chính thức

- [Oracle Java SE Support Roadmap](https://www.oracle.com/technetwork/java/javase/tech/eol-135779.html): JDK8/11/17/21/25 LTS và non-LTS releases.
- [Oracle JDK 27 Release Notes](https://www.oracle.com/java/technologies/javase/27-relnote-issues.html): Java27 GA 15/09/2026.
- [Oracle Java 27 announcement](https://www.oracle.com/news/announcement/oracle-releases-java-27-and-strengthens-post-quantum-cryptography-support-2026-09-15/): cập nhật hybrid post-quantum key exchange TLS1.3.
- [Oracle JDK 11 Release Notes](https://www.oracle.com/java/technologies/javase/11-relnote-issues.html): JEP332 implementation TLS1.3.
- [`javac --release` — Java SE21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html): giới hạn source/API/bytecode và supported targets.
- [`HttpClient` — Java SE11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html): HTTP1.1/HTTP2 API và version preference.
- [`HttpResponse` — Java SE11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpResponse.html): `version()` và response.
- [`WebSocket` — Java SE11](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/WebSocket.html): WebSocket client API.
- [`ServerSocket` — Java SE17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/ServerSocket.html): TCP listener và ephemeral port.
- [`DatagramSocket` — Java SE17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/DatagramSocket.html): UDP datagram.
- [`jdk.httpserver` — Java SE17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/module-summary.html): simple HTTP server module.
- [`UnixDomainSocketAddress` — Java SE17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/UnixDomainSocketAddress.html): Since16, Unix-domain address.
- [Virtual Threads — Java SE21](https://docs.oracle.com/en/java/javase/21/core/virtual-threads.html): virtual-thread executor.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113), [RFC 6455 — WebSocket](https://www.rfc-editor.org/rfc/rfc6455), [RFC 8446 — TLS1.3](https://www.rfc-editor.org/rfc/rfc8446): giao thức chuẩn.
