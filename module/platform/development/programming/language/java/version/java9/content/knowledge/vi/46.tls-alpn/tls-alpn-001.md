# Đàm phán giao thức ứng dụng trong TLS bằng ALPN (Java 9+)

## 1. ALPN giải quyết vấn đề gì?

**ALPN (Application-Layer Protocol Negotiation)** là phần mở rộng của TLS được chuẩn hóa trong **RFC 7301**. Nó cho phép hai đầu kết nối thỏa thuận **giao thức ở tầng ứng dụng** ngay trong quá trình bắt tay TLS, trước khi gửi dữ liệu ứng dụng. Điển hình, một máy chủ HTTPS phục vụ cả HTTP/2 và HTTP/1.1 trên cùng địa chỉ/port 443: client đề xuất những giao thức mình hiểu, server chọn một giao thức mà cả hai có thể sử dụng.

Ví dụ:

```text
Client (ClientHello)       Server
  ALPN: ["h2", "http/1.1"] ────────►
                          Chọn "h2" vì cả hai hỗ trợ
                    ◄──────────────  ALPN: "h2"
Kết thúc TLS handshake
  → Hai bên biết cùng một giao thức ứng dụng: "h2"
  → Lớp HTTP/2 bắt đầu trao đổi frame theo đặc tả HTTP/2
```

Các điểm cần tách bạch:

- **TLS** xác thực peer (theo cấu hình), tạo kênh truyền được bảo vệ và đàm phán phiên bản TLS/cipher suite.
- **ALPN** xác định tên giao thức chạy **bên trên** kênh TLS đó; ví dụ `h2` hoặc `http/1.1`. ALPN **không** tự mã hóa thêm, tự cài đặt HTTP/2 hay thay thế kiểm tra chứng chỉ.
- **SNI** (Server Name Indication) cho biết tên máy chủ đích để chọn cấu hình/chứng chỉ thích hợp; **ALPN** cho biết giao thức ứng dụng. Cả hai đều xuất hiện trong TLS handshake nhưng có mục đích khác nhau.
- Đàm phán ALPN không cần một round trip ứng dụng riêng. Ứng dụng đọc giá trị đã chọn sau handshake để điều hướng dữ liệu đến **bộ xử lý giao thức tương ứng**.

**Quan hệ với Java 9:** JDK 9 bổ sung các API ALPN tiêu chuẩn trên `SSLParameters`, `SSLSocket` và `SSLEngine`. API vẫn có mặt trong JDK hiện hành. Ví dụ thực hành bên dưới dùng Java 17+ để tận dụng TLS 1.3; **TLS 1.3 không có nghĩa đã đi kèm Java 9**.

## 2. ALPN hoạt động ở bước nào của handshake?

Quy trình ở mức thiết kế:

1. **Client** lập danh sách tên giao thức mà lớp ứng dụng thực sự hỗ trợ, ví dụ `["h2", "http/1.1"]`; JSSE đưa danh sách đó vào extension `application_layer_protocol_negotiation` của `ClientHello`.
2. **Server** so sánh danh sách nhận được với những giao thức bản thân có thể phục vụ. Với cơ chế chọn mặc định của JSSE, server xét danh sách của **server theo thứ tự ưu tiên**, chọn mục đầu tiên có trong danh sách của client.
3. **Server** trả về đúng **một** tên giao thức đã được client đề xuất và được server chấp nhận. Với TLS 1.2, kết quả nằm trong `ServerHello` theo RFC 7301; với TLS 1.3, phản hồi ALPN xuất hiện trong `EncryptedExtensions` theo RFC 8446.
4. Sau khi handshake thành công, mỗi bên lấy kết quả bằng `getApplicationProtocol()`, quyết định dùng HTTP/2, HTTP/1.1 hay một giao thức ứng dụng khác **mà mã ứng dụng đã triển khai**.
5. Nếu không có giao thức chung trong một kết nối **yêu cầu ALPN**, máy chủ từ chối thương lượng (thường phát cảnh báo TLS `no_application_protocol`). Không âm thầm tự chọn tên khác với tên đã thương lượng.

**Không có ALPN** khác với **ALPN thất bại**. Khi ứng dụng hoặc peer không sử dụng extension, một số loại kết nối có thể vẫn bắt tay TLS thành công và dùng giao thức đã định sẵn qua cấu hình ngoài TLS. Ngược lại, nếu dịch vụ yêu cầu `h2` qua ALPN thì kết quả trống hoặc không khớp phải được coi là thất bại đối với yêu cầu đó.

### Tên định danh thường gặp

| Giá trị ALPN | Ý nghĩa | Sử dụng đúng |
| --- | --- | --- |
| `h2` | HTTP/2 qua TLS (TCP) | Có thể quảng bá khi ứng dụng **thực sự triển khai** HTTP/2 |
| `http/1.1` | HTTP/1.1 | Có thể quảng bá khi có bộ xử lý HTTP/1.1 |
| `h3` | HTTP/3 trên QUIC với TLS 1.3 | Dùng trong giao thức QUIC/HTTP/3, **không** biến một `SSLSocket` TCP thành HTTP/3 |
| Giá trị riêng đã được đăng ký/định nghĩa | Giao thức ứng dụng khác | Hai đầu phải thống nhất byte định danh và cách xử lý |

Theo **RFC 9113**, `h2c` không được gửi/chọn làm ALPN cho HTTP/2 qua TLS; cơ chế HTTP/2 cleartext upgrade cũ không phù hợp làm hướng triển khai mới. Với HTTPS hiện đại, chọn `h2` và `http/1.1` là ví dụ đúng trọng tâm.

Tên giao thức là định danh **byte** theo ALPN; các token ASCII như `h2`, `http/1.1` được chuẩn hóa nên tránh nhầm encoding. Với giá trị tùy biến, cần tuân thủ quy tắc mã hóa của JSSE và registry liên quan; không tùy ý dùng chuỗi Unicode tùy nghi làm định danh mạng.

## 3. Các API ALPN chính trong Java

Tất cả API sau thuộc **`javax.net.ssl`**, hoạt động với JSSE provider hỗ trợ ALPN. Việc phương thức tồn tại từ Java 9 không có nghĩa mọi provider TLS của bên thứ ba đều triển khai đầy đủ.

| API | Dùng khi nào | Hành vi |
| --- | --- | --- |
| `SSLParameters.setApplicationProtocols(String[])` | Trước handshake, ở client và server | Cấu hình danh sách tên ALPN theo thứ tự ưu tiên |
| `SSLParameters.getApplicationProtocols()` | Kiểm tra cấu hình trước handshake | Trả danh sách đã cấu hình; **không** phải kết quả đàm phán |
| `SSLSocket.setSSLParameters(params)` | Với socket TLS | Áp dụng tham số đã đặt vào socket, cần gọi trước `startHandshake()` |
| `SSLEngine.setSSLParameters(params)` | Với engine TLS không chặn (nonblocking) | Áp dụng danh sách ALPN trên engine trước khi chạy vòng handshake |
| `SSLSocket.getApplicationProtocol()` | Sau handshake thành công | Kết quả ALPN của kết nối socket |
| `SSLEngine.getApplicationProtocol()` | Sau khi engine hoàn thành handshake | Kết quả ALPN của kết nối engine |
| `getHandshakeApplicationProtocol()` | **Trong lúc** handshake | Giá trị tạm thời nếu đã được xác định ở giai đoạn đang thương lượng |
| `setHandshakeApplicationProtocolSelector(BiFunction<..., List<String>, String>)` | Chủ yếu tại **server**, trước handshake | Callback tùy chọn chọn tên ALPN từ danh sách client; thay cơ chế chọn mặc định |

### Cấu hình trên client

```java
// Đoạn minh họa; clientSocket là SSLSocket vừa tạo,
// chưa bắt đầu handshake và đã có cấu hình trust thích hợp.
SSLParameters params = clientSocket.getSSLParameters();
params.setApplicationProtocols(new String[] {"h2", "http/1.1"});
clientSocket.setSSLParameters(params);
clientSocket.startHandshake();

String selected = clientSocket.getApplicationProtocol();
if (!"h2".equals(selected) && !"http/1.1".equals(selected)) {
    throw new IllegalStateException("Không chọn được HTTP qua ALPN");
}
```

Client **quảng bá những giao thức mà nó có khả năng xử lý**, không buộc server phải chọn mục đầu tiên. Nếu dùng socket TCP trực tiếp, phải tự triển khai lớp xử lý HTTP tương ứng; chỉ nhận được chuỗi `"h2"` không đủ để gửi HTTP/2 frame hợp lệ.

### Cấu hình mặc định trên server

```java
// Đoạn minh họa; acceptedSocket là SSLSocket server đã accept,
// nhưng chưa bắt đầu handshake.
SSLParameters params = acceptedSocket.getSSLParameters();
params.setApplicationProtocols(new String[] {"h2", "http/1.1"});
acceptedSocket.setSSLParameters(params);

acceptedSocket.startHandshake();
String selected = acceptedSocket.getApplicationProtocol();
```

Ở JSSE mặc định, danh sách của server có thứ tự ưu tiên. Nếu client chào `["http/1.1", "h2"]`, server chào `["h2", "http/1.1"]` thì **kết quả là `h2`** khi cấu hình và provider hỗ trợ. Server phải có bộ xử lý HTTP/2 thật sự trước khi công bố `h2`.

### Giá trị trả về có ba trạng thái

Theo hợp đồng API `SSLSocket`/`SSLEngine`:

- `null`: chưa xác định có sử dụng thông tin giao thức ứng dụng hay không (chẳng hạn gọi quá sớm).
- Chuỗi rỗng `""`: kết nối không sử dụng giá trị giao thức ứng dụng đã đàm phán.
- Chuỗi không rỗng (ví dụ `"h2"`): có giá trị giao thức ứng dụng đã đàm phán.

Vì vậy, không viết `socket.getApplicationProtocol().equals("h2")` khi kết quả có thể là `null`. Dùng `"h2".equals(socket.getApplicationProtocol())` hoặc kiểm tra riêng các trạng thái. Trong callback/handshake, `getHandshakeApplicationProtocol()` có thể trả `null` trước hoặc sau giai đoạn thương lượng; sử dụng `getApplicationProtocol()` sau handshake để điều hướng dữ liệu.

## 4. Ví dụ chạy độc lập Java 17+: thương lượng ALPN TLS 1.3 trên localhost

Ví dụ gồm **một chương trình Java** và **ba lệnh `keytool`** tạo bộ chứng chỉ thử nghiệm. Hai đầu kết nối giao tiếp qua `localhost`, không cần mạng ngoài, và **không tắt kiểm tra chứng chỉ**. Client tin cậy rõ ràng chứng chỉ self-signed được tạo riêng cho bài thử nghiệm.

Mục đích là chứng minh:

- Client quảng bá `http/1.1` trước `h2`.
- Server ưu tiên `h2` trước `http/1.1`.
- Hai bên hoàn thành TLS 1.3 handshake và thống nhất `h2`.
- Kết quả được đọc từ `SSLSocket.getApplicationProtocol()` ở **cả hai bên**.

**Lưu ý:** Chương trình dừng ngay sau handshake; nó **không triển khai HTTP/2** và không gửi HTTP request. Các tên ALPN chỉ dùng để minh họa cơ chế chọn. Khi xây dựng server thực tế, chỉ quảng bá `h2` nếu có stack HTTP/2 hợp lệ.

### 4.1. Tạo khóa thử nghiệm và truststore

Mở terminal trong một **thư mục thử nghiệm riêng** (đã có `keytool` từ JDK 17+):

```bash
keytool -genkeypair -alias alpn-local -keyalg RSA -keysize 2048 -validity 7 -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=dns:localhost,ip:127.0.0.1" -noprompt

keytool -exportcert -alias alpn-local -keystore server.p12 -storetype PKCS12 -storepass changeit -file server.cer

keytool -importcert -alias alpn-local -file server.cer -keystore trust.p12 -storetype PKCS12 -storepass changeit -noprompt
```

Kết quả có ba file: `server.p12` giữ khóa riêng và chứng chỉ dùng cho **server**; `server.cer` chỉ có chứng chỉ công khai; `trust.p12` chứa chứng chỉ mà **client** tin cậy cho buổi thử nghiệm. Mật khẩu `changeit` cố ý dùng trong ví dụ cục bộ, **không** dùng cho production. Self-signed certificate không phải thay thế cho chuỗi CA tin cậy khi triển khai thật.

### 4.2. Chương trình hoàn chỉnh: `AlpnLoopbackDemo.java`

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLServerSocket;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.TrustManagerFactory;

public class AlpnLoopbackDemo {
    private static final char[] PASSWORD = "changeit".toCharArray();

    public static void main(String[] args) throws Exception {
        // Server có khóa riêng (server.p12); client chỉ tin chứng chỉ
        // đã được import vào trust.p12.
        KeyStore serverKeys = loadStore("server.p12");
        KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
            KeyManagerFactory.getDefaultAlgorithm()
        );
        keyManagers.init(serverKeys, PASSWORD);

        KeyStore trustedCertificates = loadStore("trust.p12");
        TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm()
        );
        trustManagers.init(trustedCertificates);

        SSLContext serverContext = SSLContext.getInstance("TLS");
        serverContext.init(keyManagers.getKeyManagers(), null,
            new SecureRandom());

        SSLContext clientContext = SSLContext.getInstance("TLS");
        clientContext.init(null, trustManagers.getTrustManagers(),
            new SecureRandom());

        // Port 0: hệ điều hành cấp một port localhost còn trống.
        try (SSLServerSocket listener = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(0)) {
            listener.setEnabledProtocols(new String[] {"TLSv1.3"});
            ExecutorService pool = Executors.newSingleThreadExecutor();
            try {
                Future<String> serverResult = pool.submit(() -> {
                    try (SSLSocket accepted = (SSLSocket) listener.accept()) {
                        accepted.setEnabledProtocols(
                            new String[] {"TLSv1.3"}
                        );

                        // Server ưu tiên HTTP/2.
                        SSLParameters p = accepted.getSSLParameters();
                        p.setApplicationProtocols(
                            new String[] {"h2", "http/1.1"}
                        );
                        accepted.setSSLParameters(p);

                        accepted.startHandshake();
                        return accepted.getApplicationProtocol();
                    }
                });

                try (SSLSocket client = (SSLSocket)
                        clientContext.getSocketFactory().createSocket(
                            "localhost", listener.getLocalPort())) {
                    client.setEnabledProtocols(new String[] {"TLSv1.3"});

                    SSLParameters p = client.getSSLParameters();
                    p.setApplicationProtocols(
                        new String[] {"http/1.1", "h2"}
                    );
                    // Bật xác minh tên máy chủ trong chứng chỉ.
                    p.setEndpointIdentificationAlgorithm("HTTPS");
                    client.setSSLParameters(p);

                    client.startHandshake();
                    String clientProtocol = client.getApplicationProtocol();
                    String serverProtocol =
                        serverResult.get(10, TimeUnit.SECONDS);

                    if (!"h2".equals(clientProtocol)
                            || !clientProtocol.equals(serverProtocol)) {
                        throw new IllegalStateException(
                            "ALPN không chọn được h2 ở cả hai đầu");
                    }

                    System.out.println(
                        "TLS: " + client.getSession().getProtocol()
                    );
                    System.out.println("Client ALPN: " + clientProtocol);
                    System.out.println("Server ALPN: " + serverProtocol);
                }
            } finally {
                pool.shutdownNow();
            }
        }
    }

    private static KeyStore loadStore(String file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(Path.of(file))) {
            store.load(in, PASSWORD);
        }
        return store;
    }
}
```

Biên dịch và chạy trong cùng thư mục với `server.p12` và `trust.p12`:

```bash
javac -encoding UTF-8 AlpnLoopbackDemo.java
java AlpnLoopbackDemo
```

**Dòng stdout mong đợi trên JDK 17+ chuẩn có TLS 1.3/ALPN:**

```text
TLS: TLSv1.3
Client ALPN: h2
Server ALPN: h2
```

Các thông điệp tiến độ từ `keytool` (nếu có) không phải stdout của chương trình Java. Nếu môi trường cấm TLS 1.3 hoặc có chính sách provider riêng, ví dụ sẽ thất bại và cần kiểm tra cấu hình; **không tự tắt xác minh chứng chỉ** để chạy cho qua.

Giải thích các bước đáng chú ý:

1. `serverContext` có `KeyManager` chứa khóa riêng/chứng chỉ, để server chứng minh danh tính trong TLS handshake.
2. `clientContext` có `TrustManager` được tạo từ `trust.p12`; client chỉ tin chứng chỉ mà chúng ta chủ động nhập. `setEndpointIdentificationAlgorithm("HTTPS")` kiểm tra danh tính hostname `localhost` dựa trên SAN của chứng chỉ.
3. `listener.accept()` và `client.startHandshake()` chạy ở hai luồng để tránh chờ nhau. `SSLParameters.setApplicationProtocols(...)` được gọi **trước** handshake ở cả hai socket.
4. Hai danh sách có giao nhau là `h2` và `http/1.1`; mặc định JSSE chọn `h2` theo thứ tự ưu tiên server.
5. Mỗi đầu đọc kết quả và chương trình so sánh để chắc chắn hai bên đồng thuận, không dùng giá trị `null`/rỗng như thể đó là giao thức hợp lệ.

### 4.3. Thử tình huống không có giao thức chung

Trong ví dụ, đổi **duy nhất** cấu hình server thành:

```java
p.setApplicationProtocols(new String[] {"h2"});
```

và cấu hình client thành:

```java
p.setApplicationProtocols(new String[] {"http/1.1"});
```

Lúc này hai bên không có token chung. Khi dùng ALPN theo chuẩn, dự kiến handshake bị từ chối, thường biểu hiện qua `SSLHandshakeException` và TLS alert `no_application_protocol` (thông báo cụ thể phụ thuộc JDK/provider). Vì handshake đã lỗi, không thể coi `getApplicationProtocol()` như một giá trị giao thức hợp lệ. Điều đúng cần kiểm thử là **kết nối không bắt đầu trao đổi dữ liệu ứng dụng như thể đã chọn thành công**.

Sau khi thử, khôi phục danh sách ban đầu trước khi chạy lại trường hợp thành công. Với một service bắt buộc HTTP/2, cũng cần từ chối kết quả `""` dù TLS handshake có thể hoàn thành khi không sử dụng ALPN.

## 5. Chọn ALPN tùy chỉnh trên server

Mặc định JSSE chọn phần tử **đầu tiên trong danh sách ưu tiên của server** có mặt trong danh sách client. Đối với ứng dụng có nhiều bộ xử lý giao thức hoặc lựa chọn phụ thuộc kết quả handshake, có thể đặt callback:

```java
// ĐOẠN MINH HỌA: accepted là SSLSocket phía server.
// Biến http2Ready phải phản ánh khả năng HTTP/2 thật của ứng dụng.
accepted.setHandshakeApplicationProtocolSelector(
    (socket, offeredProtocols) -> {
        if (http2Ready && offeredProtocols.contains("h2")) {
            return "h2";
        }
        if (offeredProtocols.contains("http/1.1")) {
            return "http/1.1";
        }
        return null; // Không có giao thức được chấp nhận.
    }
);
```

Đặt callback **trước `startHandshake()`**. Đây là một **đoạn minh họa**, không phải chương trình Java độc lập: `accepted` và `http2Ready` là các biến của hệ thống thực. Callback được gọi bởi tầng TLS trong quá trình handshake, nên chỉ thực hiện thao tác lựa chọn nhanh và có thể dự đoán.

Hợp đồng của callback:

- **Trả đúng một chuỗi có trong danh sách client quảng bá** khi lựa chọn thành công.
- **Trả `null`** khi không có giao thức phù hợp. Với ALPN, điều này có thể gây cảnh báo `no_application_protocol` và kết thúc handshake.
- **Trả `""`** nếu chủ đích không sử dụng chỉ định giao thức ứng dụng; đây không phải cách thay thế cho `null` trong chính sách “bắt buộc có giao thức chung”.
- **Trả tên không có trong danh sách client** là sai điều kiện thương lượng; lớp TLS có thể từ chối.
- Khi đã dùng `setHandshakeApplicationProtocolSelector(...)`, callback **ghi đè lựa chọn mặc định theo `SSLParameters.setApplicationProtocols(...)`**. Không giả định mảng server vẫn quyết định kết quả.

Với `SSLEngine` (server TLS chạy kiểu sự kiện/nonblocking), API tương ứng là:

```java
// ĐOẠN MINH HỌA; serverEngine được cấu hình server mode trước handshake.
serverEngine.setHandshakeApplicationProtocolSelector(
    (engine, offered) -> offered.contains("h2") ? "h2" : null
);
```

`SSLEngine` không tự đọc/ghi mạng: ứng dụng/framework phải xử lý vòng `wrap`/`unwrap`, `HandshakeStatus`, `NEED_TASK` và bộ đệm TLS đúng cách. ALPN nằm trong cấu hình TLS engine; nó **không** thay thế quy trình hoàn thành handshake của `SSLEngine`.

### Callback dựa trên cipher suite hoặc hostname

Một số hệ thống có thể chọn giao thức khác nhau theo SNI, cipher suite đã thương lượng hoặc chính sách máy chủ. Khi đó callback có thể đọc `getHandshakeSession()` và các thông tin đã sẵn có trong handshake. Phải bảo đảm giao thức định chọn **tương thích với cấu hình TLS** và chính sách bảo mật. Ví dụ HTTP/2 có các ràng buộc TLS/cipher suite theo RFC 9113; không đơn giản chọn `h2` khi server không thể thực hiện HTTP/2 hợp lệ trên kết nối đó.

## 6. Kết nối ALPN với HTTP/2 trong Java

Dùng `SSLSocket`/`SSLEngine` trực tiếp chỉ thích hợp khi bạn **xây dựng hoặc tích hợp lớp giao thức mạng riêng**. Nếu mục tiêu chỉ là gọi HTTP API từ ứng dụng, JDK có `java.net.http.HttpClient` hiện hành (có từ Java 11; API incubator thời Java 9 đã được thay thế, không phải lựa chọn cho code mới).

Ví dụ **đoạn cấu hình cho chương trình HTTP client**, không chạy độc lập vì cần URI/response và các import phù hợp:

```java
HttpClient http = HttpClient.newBuilder()
    .version(HttpClient.Version.HTTP_2)
    .build();

// Khi gửi request HTTPS, dùng HttpResponse.version()
// để biết thực tế đã dùng HTTP_2 hay HTTP_1_1.
```

`HttpClient.Version.HTTP_2` là **ưu tiên phiên bản**, không bảo đảm mọi request sẽ dùng HTTP/2: proxy, TLS peer, cấu hình runtime và khả năng của kết nối có thể dẫn đến HTTP/1.1. Không tự chỉnh ALPN trên `HttpClient.sslParameters(...)` một cách mù quáng: client HTTP cấp cao tự quản lý handshake/HTTP version, và một số tham số TLS được triển khai kiểm soát nội bộ.

Ở server, dùng framework HTTP hỗ trợ HTTP/2 (ví dụ server web/Netty được cấu hình đúng), thay vì chỉ đặt `"h2"` trên `SSLSocket` rồi gửi văn bản HTTP/1.1. **ALPN đã chọn `h2` nghĩa là dữ liệu sau handshake phải tuân theo framing và state machine HTTP/2.**

### Trường hợp HTTP/3

HTTP/3 dùng **QUIC**, tích hợp TLS 1.3 và token ALPN `h3` theo RFC 9114. `SSLSocket` của Java dùng TCP/TLS kiểu truyền thống; chỉ gọi `setApplicationProtocols(new String[]{"h3"})` trên `SSLSocket` **không** tạo kết nối QUIC hay HTTP/3. Cần một stack QUIC/HTTP3 riêng có hỗ trợ ALPN. Đó là phạm vi khác với ví dụ JSSE TCP ở đây.

## 7. Bảo mật và tương thích khi triển khai

### Chứng chỉ TLS luôn cần xác minh

Đàm phán ALPN thành công **không chứng minh peer là máy chủ dự kiến**. Ở client TLS tự xây, cần truststore hợp lệ, xác minh chuỗi chứng chỉ và hostname (`SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` cho HTTPS). Không dùng `X509TrustManager` luôn trả chấp nhận, tắt kiểm tra hostname hoặc bỏ qua `SSLHandshakeException` để “sửa” ALPN.

Ví dụ `keytool` sử dụng self-signed certificate **chỉ cho localhost**. Production nên dùng chứng chỉ cấp đúng hostname/chuỗi tin cậy, bảo vệ private key, thiết lập chính sách vòng đời chứng chỉ và cấu hình trust phù hợp.

### Bảo đảm giao thức và phiên bản TLS

- **ALPN không đặt phiên bản TLS.** Có thể dùng cùng API ALPN trên các phiên bản TLS được JSSE hiện hành hỗ trợ; lựa chọn TLS version/cipher suite là việc riêng. Ưu tiên TLS 1.3 trong hệ thống mới nếu tương thích; với TLS 1.2, đánh giá ràng buộc của HTTP/2 theo RFC 9113.
- Nếu chỉ chấp nhận HTTP/2 thì **chỉ công bố `h2`** (nếu stack hỗ trợ) và từ chối kết nối khi không thương lượng được; đừng tự gửi HTTP/1.1 trên kết nối mà đôi bên đã chọn `h2`.
- Nếu chấp nhận cả HTTP/2 và HTTP/1.1, cấu hình cả hai và lựa chọn máy chủ nhất quán. **Fallback** phải là kết quả chính sách được cho phép, không phải giải pháp tự động cho handshake thất bại vì lỗi chứng chỉ/cipher suite.
- Mỗi kết nối TLS có kết quả ALPN riêng. Không dùng giá trị ALPN của kết nối trước như bằng chứng cho kết nối mới; ngay cả khi có TLS session resumption, giá trị ALPN phải gắn với handshake/kết nối phù hợp.
- Nếu dùng proxy hoặc TLS termination ở ingress/load balancer, ALPN giữa client và proxy **không tự quyết định** giao thức của kết nối proxy ↔ backend. Kiểm tra từng chặng TLS độc lập.
- Nếu không sử dụng ALPN hoặc kết quả rỗng, đừng đoán `"http/1.1"` trừ khi giao thức của hệ thống **định nghĩa rõ** mặc định đó và endpoint thực sự chấp nhận.

### Tên giao thức là hợp đồng giữa hai lớp

Lỗi cấu hình nguy hiểm là quảng bá `"h2"` nhưng sau TLS handshake lại luôn chạy handler HTTP/1.1. Đàm phán thành công vẫn dẫn đến lỗi giao thức. Đối với giao thức tự định nghĩa, hãy cố định tên định danh (byte), semantics, versioning và kiểm thử cả hai phía. Không coi ALPN như hệ thống phát hiện tính năng tùy ý ngoài những giao thức đã được định nghĩa.

## 8. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân thường gặp | Cách xác minh và xử lý |
| --- | --- | --- |
| `getApplicationProtocol() == null` | Hỏi quá sớm, chưa xác định kết quả | Chờ `startHandshake()`/`SSLEngine` handshake hoàn tất |
| `getApplicationProtocol().isEmpty()` | Kết nối không sử dụng giá trị ALPN | Kiểm tra cả hai đầu có cấu hình ALPN và chính sách ứng dụng có cho phép không |
| TLS handshake lỗi `no_application_protocol` | Không có tên giao thức chung hoặc callback từ chối | So sánh đúng danh sách client/server và giá trị trả từ selector |
| Client chào cả `h2` và `http/1.1` nhưng chọn HTTP/1.1 | Thứ tự server, selector tùy chỉnh, hoặc cấu hình framework | Kiểm tra danh sách trên socket/engine thật và callback đang dùng |
| Thay đổi `SSLParameters` mà kết quả không đổi | Chưa gọi `socket.setSSLParameters(params)`, hoặc đặt sau handshake | Gán tham số lại **trước** khi handshake bắt đầu |
| Callback dường như không chạy/không theo thứ tự mong muốn | Selector được đặt trên socket khác, vai trò client/server sai, hoặc provider không hỗ trợ | Kiểm tra socket/engine thực tế, `getHandshakeApplicationProtocolSelector()` và ngoại lệ provider |
| Handshake lỗi chứng chỉ | Truststore thiếu chứng chỉ, SAN sai hostname, chứng chỉ hết hạn | Sửa trust/identity, **không** vô hiệu hóa xác minh |
| Bên gửi HTTP/1.1 sau khi ALPN chọn `h2` | Không dispatch sang bộ xử lý HTTP/2 | Gắn đúng handler ứng dụng theo chuỗi ALPN và kiểm thử framing |
| HTTP/3 không chạy trên `SSLSocket` | `h3` cần QUIC/TLS 1.3, không chỉ TCP TLS | Sử dụng stack QUIC/HTTP3 đúng kiến trúc |
| Chạy được JDK mặc định nhưng hỏng trên provider khác | Provider không hỗ trợ ALPN hoặc khác chính sách TLS | Xem tài liệu provider, kiểm tra môi trường triển khai và thử handshake thực tế |

Có thể bật **JSSE debug** tạm thời trong môi trường thử nghiệm:

```bash
java -Djavax.net.debug=ssl,handshake AlpnLoopbackDemo
```

Xem log `ClientHello`, extension ALPN, lựa chọn TLS và lỗi handshake. Log có thể rất dài hoặc bộc lộ metadata nhạy cảm của kết nối; chỉ thu thập trên môi trường phù hợp, không bật tùy tiện trong production. Với TLS 1.3, phản hồi ALPN là một extension trong `EncryptedExtensions`.

Đối với client HTTP cấp cao, kết quả đáng tin cậy là `HttpResponse.version()`; đối với `SSLSocket`/`SSLEngine`, dùng `getApplicationProtocol()` **sau** handshake. Giá trị đã cấu hình `SSLParameters.getApplicationProtocols()` chỉ là **danh sách đề xuất**, không phải bằng chứng hai bên chọn thành công.

## 9. Checklist kiểm thử cho hệ thống thật

1. Chỉ quảng bá những giao thức ứng dụng đã có handler tương ứng.
2. Client/server có danh sách chồng lấp → bắt tay TLS thành công, kết quả ALPN hai đầu giống nhau, dữ liệu đi đúng handler.
3. Không có tên trùng → kết nối yêu cầu ALPN phải thất bại đúng cách, không trao đổi dữ liệu theo giao thức đoán mò.
4. Thay thứ tự server → lựa chọn mặc định đổi theo ưu tiên nếu cả hai token cùng được client chào.
5. Sai truststore/hostname → TLS thất bại dù có tên ALPN chung.
6. TLS version/cipher suite không tương thích → không tự hạ chính sách bảo mật chỉ để “sửa” ALPN.
7. Kết nối qua proxy, load balancer hoặc TLS termination → kiểm tra riêng ALPN ở từng chặng và giao thức backend.
8. Khi vận hành, quan sát token đã chọn, phiên bản TLS và lỗi handshake mà **không ghi khóa hay dữ liệu bí mật**.

## Tài liệu tham khảo đang áp dụng

- [RFC 7301 — TLS Application-Layer Protocol Negotiation Extension](https://www.rfc-editor.org/rfc/rfc7301): chuẩn giao thức ALPN và lỗi `no_application_protocol`.
- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446): extension `application_layer_protocol_negotiation` trong `EncryptedExtensions`.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): định danh `h2`, yêu cầu TLS và lý do không gửi `h2c` trong ALPN.
- [RFC 9114 — HTTP/3](https://www.rfc-editor.org/rfc/rfc9114): `h3`, QUIC và TLS 1.3.
- [Oracle — JSSE Reference Guide, mục TLS Application Layer Protocol Negotiation](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html): cấu hình, thứ tự ưu tiên, callback và chẩn đoán ALPN.
- [Java SE 25 — SSLParameters](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setApplicationProtocols`, `getApplicationProtocols` và cấu hình hostname.
- [Java SE 25 — SSLSocket](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLSocket.html): `getApplicationProtocol` và server selector.
- [Java SE 25 — SSLEngine](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html): API tương đương cho I/O không chặn.
- [Java SE 25 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/25/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): ưu tiên HTTP/2 và các tình huống dùng HTTP/1.1 thực tế.

Bài viết tập trung vào **API ALPN vẫn được duy trì trên Java hiện hành**, dùng Java 17+ cho ví dụ TLS 1.3 và không dựa vào API incubator hoặc cơ chế HTTP/2 cleartext upgrade đã lỗi thời.