# Đọc giao thức ALPN đã chọn trên SSLSocket hoặc SSLEngine (Java 9+)

## 1. Mục tiêu và ngữ cảnh

Khi client và server thiết lập kết nối TLS, chúng có thể dùng **ALPN (Application-Layer Protocol Negotiation)** để thống nhất giao thức ứng dụng sẽ chạy **bên trong kết nối TLS**, chẳng hạn `h2` (HTTP/2) hoặc `http/1.1` (HTTP/1.1). ALPN được thương lượng trong quá trình **TLS handshake**, trước khi ứng dụng trao đổi dữ liệu của giao thức đã chọn.

Kể từ **Java 9**, hai API chuẩn `javax.net.ssl.SSLSocket` và `javax.net.ssl.SSLEngine` đều có:

- `getApplicationProtocol()`: đọc giao thức ứng dụng đã được thương lượng gần nhất cho kết nối.
- `getHandshakeApplicationProtocol()`: đọc trạng thái giao thức ứng dụng khi **handshake đang diễn ra**.

Hai phương thức vẫn được hỗ trợ trong Java SE hiện hành (kể cả Java 17, 21, 25 và API Java SE 26), không phải API legacy. Bài này tập trung vào **đọc và xử lý kết quả ALPN**; phần cấu hình danh sách giao thức chỉ nhằm tạo điều kiện để handshake có kết quả có thể đọc.

**Phân biệt quan trọng:** `getApplicationProtocol()` trả `"h2"`/`"http/1.1"` (giao thức ứng dụng), còn `getSession().getProtocol()` trên `SSLSocket` hoặc `getSession().getProtocol()` trên `SSLEngine` trả phiên bản giao thức **bảo mật TLS**, ví dụ `"TLSv1.3"`. Hai kết quả trả lời hai câu hỏi khác nhau.

## 2. Hiểu chính xác giá trị trả về

Theo hợp đồng Java API, `getApplicationProtocol()` và `getHandshakeApplicationProtocol()` có **ba trạng thái**, không được coi tất cả là chuỗi thông thường:

| Giá trị | Nghĩa | Phản ứng nên làm |
| --- | --- | --- |
| `null` | Chưa xác định được liệu ALPN có được dùng trong kết nối/handshake đang xét hay không. Thường gặp khi gọi quá sớm. | Chờ quá trình handshake tiến triển hoặc hoàn tất. Không suy ra `"http/1.1"`. |
| `""` (chuỗi rỗng) | Đã xác định **không sử dụng giao thức ứng dụng qua ALPN**. | Chỉ fallback sang giao thức mặc định nếu ứng dụng **chủ động cho phép** và hai phía có contract tương thích; nếu bắt buộc ALPN thì từ chối. |
| Chuỗi không rỗng, ví dụ `"h2"` | ALPN đã thống nhất giao thức ứng dụng. | Chỉ chuyển sang bộ xử lý hỗ trợ đúng giao thức đó; không giả định mọi chuỗi đều là HTTP. |

Ví dụ xử lý kết quả cuối cùng sau khi handshake thành công:

```java
static String requireHttpAlpn(String protocol) {
    if (protocol == null) {
        throw new IllegalStateException("ALPN chưa được xác định");
    }
    return switch (protocol) {
        case "h2", "http/1.1" -> protocol;
        case "" -> throw new IllegalStateException("Không thương lượng được ALPN");
        default -> throw new IllegalStateException(
                "Giao thức ứng dụng không được hỗ trợ: " + protocol);
    };
}
```

Đây là **phương thức minh họa**, được gọi với chuỗi trả về của `getApplicationProtocol()`; bản thân nó không thực hiện handshake. Nếu ứng dụng có quy tắc fallback riêng thì nhánh `""` có thể xử lý khác, nhưng cần quyết định rõ ràng.

**Một ngoại lệ khác cần biết:** cài đặt mặc định trong lớp trừu tượng `SSLSocket`/`SSLEngine` của các phương thức ALPN có thể ném `UnsupportedOperationException` nếu SSL provider không cài đặt tính năng. Provider TLS mặc định của các JDK hiện đại có hỗ trợ ALPN, nhưng với provider tùy biến cần kiểm thử. Không đánh đồng ngoại lệ thiếu hỗ trợ với trạng thái trả `""`.

## 3. Cấu hình ALPN trước handshake để có kết quả đọc được

Ở hai đầu kết nối, chuẩn Java dùng `SSLParameters.setApplicationProtocols(String[])`, sau đó áp dụng cấu hình qua `setSSLParameters(...)`.

**Client dùng SSLSocket:**

```java
SSLParameters parameters = socket.getSSLParameters();
parameters.setApplicationProtocols(new String[] {"h2", "http/1.1"});
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);

// Gọi trước khi handshake:
socket.startHandshake();

String selected = socket.getApplicationProtocol();
System.out.println("ALPN: " + selected);
```

Đây là **đoạn mã tích hợp**, giả định `socket` là `SSLSocket` đã kết nối đến máy chủ mong muốn. `setEndpointIdentificationAlgorithm("HTTPS")` bật kiểm tra hostname của TLS certificate theo quy tắc HTTPS. Luôn dùng cấu hình trust/certificate thích hợp; ALPN **không thay thế việc xác thực máy chủ**.

**Server dùng SSLSocket:**

```java
SSLParameters parameters = serverSideSocket.getSSLParameters();
parameters.setApplicationProtocols(new String[] {"h2", "http/1.1"});
serverSideSocket.setSSLParameters(parameters);

serverSideSocket.startHandshake();
String selected = serverSideSocket.getApplicationProtocol();
```

Đoạn này giả định `serverSideSocket` là `SSLSocket` ở phía server. Có thể cấu hình `SSLServerSocket` để những socket được `accept()` kế thừa thiết lập; ví dụ chạy đầy đủ bên dưới làm theo cách này.

**Cú pháp tương ứng với SSLEngine:**

```java
SSLEngine engine = sslContext.createSSLEngine(host, port);
engine.setUseClientMode(true);
SSLParameters parameters = engine.getSSLParameters();
parameters.setApplicationProtocols(new String[] {"h2", "http/1.1"});
parameters.setEndpointIdentificationAlgorithm("HTTPS");
engine.setSSLParameters(parameters);

// Tiếp theo ứng dụng phải điều khiển handshake qua wrap/unwrap.
engine.beginHandshake();
```

Đây là **đoạn cấu hình**, chưa phải một chương trình hoàn chỉnh. `sslContext` phải được khởi tạo với trust managers/certificates phù hợp; `host` và `port` là địa chỉ mục tiêu; phần `SSLEngine` không tự mở socket hay truyền dữ liệu.

**Lưu ý về danh sách giao thức:**

- `SSLParameters.getApplicationProtocols()` chỉ cho biết **danh sách được cấu hình/đề xuất**, không phải giao thức đã được chọn.
- Các mã `"h2"` và `"http/1.1"` là mã ALPN tiêu chuẩn; tên phải khớp chính xác, phân biệt chữ hoa/chữ thường.
- Danh sách trong `setApplicationProtocols` có thứ tự ưu tiên. Khi phía server dùng cơ chế chọn mặc định của JSSE, ứng viên phù hợp đầu tiên theo danh sách ưu tiên của server có thể được chọn.
- Khi **không có giao thức chung**, TLS handshake có thể thất bại vì `no_application_protocol`. Không mặc định rằng kết quả luôn là chuỗi rỗng.
- Nếu server dùng `setHandshakeApplicationProtocolSelector(...)` thì callback chọn giao thức có thể thay thế cơ chế so khớp danh sách mặc định; cần xem chính sách của server.

## 4. Với SSLSocket: đọc kết quả sau startHandshake()

`SSLSocket.startHandshake()` cho phép kích hoạt handshake tường minh. Với **handshake ban đầu**, phương thức đồng bộ và trả về khi quá trình thương lượng hoàn tất, hoặc ném `IOException`/`SSLException` nếu lỗi.

Mẫu chuẩn:

```java
try (SSLSocket socket = /* tạo socket bằng SSLSocketFactory */) {
    SSLParameters p = socket.getSSLParameters();
    p.setApplicationProtocols(new String[] {"h2", "http/1.1"});
    p.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(p);

    socket.startHandshake();  // Handshake ban đầu hoàn tất hoặc ném lỗi.
    String protocol = socket.getApplicationProtocol();

    if ("h2".equals(protocol)) {
        // Chỉ sau đây mới chuyển dữ liệu sang HTTP/2 handler.
    } else if ("http/1.1".equals(protocol)) {
        // Dùng HTTP/1.1 handler.
    } else {
        // null, "" hoặc một giá trị khác: áp dụng chính sách rõ ràng.
    }
}
```

Đây là mã **minh họa tích hợp**: dấu chú thích trong vị trí khởi tạo socket cần được thay bằng `SSLSocket` thực. Không đưa dữ liệu HTTP/2 vào đường truyền trước khi biết peer đã thống nhất `h2` và ứng dụng thực sự có bộ xử lý HTTP/2.

Có thể gọi `getApplicationProtocol()` **trước** `startHandshake()` để quan sát trạng thái, nhưng khi đó thường là `null`. Đừng dùng nó để quyết định giao thức trước khi có kết quả. Nếu cần thông tin **khi handshake đang chạy** (ví dụ trong callback hoặc điểm kiểm soát handshake), gọi `getHandshakeApplicationProtocol()`; giá trị này vẫn có thể là `null` khi chưa xác định và **không phải tín hiệu handshake đã thành công**.

## 5. Ví dụ đầy đủ: hai SSLSocket thương lượng ALPN trên máy cục bộ

Ví dụ tạo **TLS server và client trên 127.0.0.1** trong cùng tiến trình. Hai bên đều hỗ trợ `h2`, `http/1.1`; sau khi hoàn tất handshake, cả hai gọi `getApplicationProtocol()` để đọc kết quả. Không cần Internet hoặc database.

Để tránh tắt kiểm tra bảo mật, ví dụ dùng một certificate tự ký **chỉ dành cho máy local** và nạp certificate đó vào trust store của client. Certificate chứa SAN `127.0.0.1`; client vẫn bật hostname verification qua `HTTPS`.

### 5.1. Tạo certificate thử nghiệm (JDK keytool)

Chạy trong một thư mục rỗng, dùng **JDK 17+**:

```bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -validity 7 -storetype PKCS12 -keystore demo.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=DNS:localhost,IP:127.0.0.1" -noprompt
```

Mật khẩu `changeit` chỉ phục vụ demo local và tệp `demo.p12` phải được bảo vệ/xóa sau thực hành. **Không** sử dụng certificate tự ký và mật khẩu demo làm cấu hình production. Trong hệ thống thực, dùng TLS credentials và trust chain đã được quản lý đúng cách.

### 5.2. Chương trình Java hoàn chỉnh

Lưu tệp **`AlpnSocketDemo.java`** cùng thư mục với `demo.p12`:

```java
import java.net.InetAddress;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import javax.net.ssl.*;

public class AlpnSocketDemo {
    public static void main(String[] args) throws Exception {
        char[] password = args[1].toCharArray();
        KeyStore keys = KeyStore.getInstance("PKCS12");
        try (var in = java.nio.file.Files.newInputStream(Path.of(args[0]))) {
            keys.load(in, password);
        }

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, password);
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(keys);

        SSLContext serverContext = SSLContext.getInstance("TLS");
        serverContext.init(kmf.getKeyManagers(), null, null);
        SSLContext clientContext = SSLContext.getInstance("TLS");
        clientContext.init(null, tmf.getTrustManagers(), null);

        ExecutorService threads = Executors.newSingleThreadExecutor();
        try (SSLServerSocket listener = (SSLServerSocket)
                serverContext.getServerSocketFactory().createServerSocket(
                        0, 1, InetAddress.getByName("127.0.0.1"))) {
            SSLParameters serverOptions = listener.getSSLParameters();
            serverOptions.setApplicationProtocols(new String[] {"h2", "http/1.1"});
            listener.setSSLParameters(serverOptions);

            Future<String> serverResult = threads.submit(() -> {
                try (SSLSocket server = (SSLSocket) listener.accept()) {
                    server.startHandshake();
                    return server.getApplicationProtocol();
                }
            });

            try (SSLSocket client = (SSLSocket)
                    clientContext.getSocketFactory().createSocket(
                            "127.0.0.1", listener.getLocalPort())) {
                SSLParameters options = client.getSSLParameters();
                options.setApplicationProtocols(new String[] {"h2", "http/1.1"});
                options.setEndpointIdentificationAlgorithm("HTTPS");
                client.setSSLParameters(options);

                String before = client.getApplicationProtocol();
                client.startHandshake();

                System.out.println("Truoc handshake: "
                        + (before == null ? "chua xac dinh" : before));
                System.out.println("Client ALPN: " + client.getApplicationProtocol());
                System.out.println("Server ALPN: " + serverResult.get());
            }
        } finally {
            threads.shutdownNow();
        }
    }
}
```

Chương trình tạo hai `SSLContext` riêng: server dùng private key trong keystore; client dùng trust manager chứa certificate được tin cậy cho **demo local**. `listener` ràng buộc vào loopback và cổng tự chọn. Server thực hiện handshake trong một thread; client thực hiện handshake ở thread main. `Future` giúp main lấy kết quả của server sau khi server đã hoàn tất handshake.

**Biên dịch và chạy:**

```bash
javac -encoding UTF-8 --release 17 AlpnSocketDemo.java
java AlpnSocketDemo demo.p12 changeit
```

**Stdout đã kiểm thử với OpenJDK 24.0.2, biên dịch `--release 17`:**

```text
Truoc handshake: chua xac dinh
Client ALPN: h2
Server ALPN: h2
```

Đầu ra này đến từ môi trường demo mà cả hai đầu do cùng một JDK điều khiển. Trên kết nối thật, **server khác có thể chọn `http/1.1`, không dùng ALPN hoặc từ chối handshake**. Ở ví dụ này chỉ thương lượng tên `h2`; **không có HTTP/2 frame nào được truyền**. Muốn giao tiếp HTTP/2 thực tế cần thư viện/triển khai giao thức HTTP/2, không chỉ gọi API ALPN.

## 6. Với SSLEngine: đọc kết quả sau khi vòng lặp handshake hoàn tất

`SSLEngine` là TLS engine **không tự đọc/ghi network socket**. Ứng dụng hoặc framework phải đưa dữ liệu TLS qua `wrap()` (mã hóa/đóng gói) và `unwrap()` (giải mã/mở gói), xử lý `SSLEngineResult`, chạy delegated tasks từ `getDelegatedTask()` và quản lý `ByteBuffer`. Đây là lựa chọn phổ biến trong NIO/reactive networking.

Một quy trình đơn giản hóa:

```text
createSSLEngine() + setUseClientMode(...) + setSSLParameters(...)
                            |
                     beginHandshake()
                            |
                    +-------+--------+
                    |                |
                NEED_WRAP        NEED_UNWRAP
                    |                |
                  wrap()           unwrap()
                    |                |
                 gửi bytes       nhận bytes
                    +-------+--------+
                            |
                   NEED_TASK nếu có
                            |
                 chạy getDelegatedTask()
                            |
                  lặp theo handshake status
                            |
                  FINISHED / NOT_HANDSHAKING
                            |
                 getApplicationProtocol()
                            |
              xử lý "h2", "http/1.1", "", null
```

**Điểm dễ nhầm:** trạng thái `SSLEngineResult.HandshakeStatus.FINISHED` được trả trong kết quả **lần `wrap/unwrap` hoàn tất handshake**; gọi `engine.getHandshakeStatus()` sau đó thường thấy `NOT_HANDSHAKING`. Đừng chỉ đợi `getHandshakeStatus() == FINISHED` — đây không phải trạng thái engine thường được giữ lại. Khi driver vòng lặp của bạn xác nhận handshake đã thành công, đọc:

```java
String selected = engine.getApplicationProtocol();
if ("h2".equals(selected)) {
    // Chuyển plaintext sang HTTP/2 parser/encoder.
} else if ("http/1.1".equals(selected)) {
    // Chuyển plaintext sang HTTP/1.1 parser/encoder.
} else if (selected == null) {
    throw new IllegalStateException("TLS/ALPN chưa xác định");
} else if (selected.isEmpty()) {
    throw new IllegalStateException("Kết nối không sử dụng ALPN");
} else {
    throw new IllegalStateException("ALPN không hỗ trợ: " + selected);
}
```

Đây là **đoạn tích hợp vào vòng lặp handshake SSLEngine đã có**, không phải chương trình có `main` và không tự tạo cặp TLS endpoint. Nó phải được gọi **sau khi** `wrap/unwrap` báo handshake hoàn tất; nếu vòng lặp đang ở `NEED_UNWRAP`, `NEED_WRAP` hoặc `NEED_TASK` thì chưa đủ điều kiện.

Trong những callback cần quan sát tiến trình, có thể đọc:

```java
String handshakeProtocol = engine.getHandshakeApplicationProtocol();
// null: chưa xác định; "": không dùng ALPN; non-empty: đã có giá trị.
```

Không dùng `handshakeProtocol` làm bằng chứng xác thực kết nối. Giá trị ALPN có thể xuất hiện trước khi tất cả bước kiểm tra TLS hoàn tất; cần tiếp tục xử lý handshake, kết quả tin cậy chứng chỉ và ngoại lệ `SSLException`. Chỉ gửi dữ liệu ứng dụng sau khi chính sách TLS và handshake đã hoàn thành.

### Cấu hình ở phía server SSLEngine

Nếu server dùng `SSLEngine`, phải gọi `setUseClientMode(false)` **trước** handshake, cấu hình danh sách `SSLParameters.setApplicationProtocols(...)` hoặc selector tùy chỉnh và cung cấp key manager/certificate trong `SSLContext`. Sau handshake, server cũng gọi `engine.getApplicationProtocol()` giống client. Cả hai phía cần đồng ý về ALPN; riêng client đặt `h2` trong danh sách không đảm bảo server chọn nó.

## 7. Chọn đúng API theo giai đoạn

| API | Gọi khi nào | Ý nghĩa |
| --- | --- | --- |
| `SSLParameters.setApplicationProtocols(...)` | **Trước** handshake | Khai báo các giao thức ALPN có thể thương lượng. |
| `SSLParameters.getApplicationProtocols()` | Khi kiểm tra cấu hình | Danh sách đề xuất, **không** phải giá trị được chọn. |
| `SSLSocket.getHandshakeApplicationProtocol()` | Trong handshake đang tiến hành | Giá trị ALPN tại thời điểm kiểm tra handshake; có thể chưa xác định. |
| `SSLEngine.getHandshakeApplicationProtocol()` | Trong vòng lặp `wrap/unwrap` | Giá trị ALPN trong handshake engine đang tiến hành. |
| `SSLSocket.getApplicationProtocol()` | Sau `startHandshake()` thành công | Giá trị ALPN cuối cho kết nối socket, hoặc `""` nếu không dùng. |
| `SSLEngine.getApplicationProtocol()` | Sau vòng lặp handshake engine thành công | Giá trị ALPN cuối cho kết nối engine, hoặc `""` nếu không dùng. |
| `SSLSession.getProtocol()` | Sau TLS handshake | **Phiên bản TLS**, không phải mã ALPN. |

Đối với cả `SSLSocket` và `SSLEngine`, phương thức ALPN có thể ném `UnsupportedOperationException` khi implementation/provider không hỗ trợ. Với endpoint trực tiếp có hỗ trợ JSSE ALPN, hãy dựa trên chuỗi kết quả nhưng **không** giả định luôn non-null hay non-empty.

## 8. Quy tắc xử lý giao thức sau khi chọn

1. **Phân nhánh chính xác theo giá trị:** `"h2"` dùng HTTP/2 implementation, `"http/1.1"` dùng HTTP/1.1 implementation. Không gọi `getSession().getProtocol()` để phân nhánh HTTP.
2. **Không tự downgrade khi không được phép:** `""` chỉ được fallback nếu yêu cầu kết nối và dịch vụ chấp nhận giao thức mặc định; với giao thức bắt buộc (ví dụ một RPC cần ALPN cụ thể), từ chối.
3. **Không chuyển plaintext trước khi TLS xác thực thành công:** ALPN có thể được thương lượng sớm trong handshake, nhưng ứng dụng vẫn phải xử lý certificate validation, hostname verification và lỗi TLS.
4. **Không coi ALPN là bộ định tuyến HTTP hoàn chỉnh:** Nó chỉ thương lượng identifier. Quản lý parser, framing, multiplexing, flow control, content negotiation là trách nhiệm tầng ứng dụng.
5. **Không tự gắn `"h2"` với TLSv1.3:** HTTP/2 có thể hoạt động qua TLS phù hợp mà không đồng nghĩa phiên bản TLS cố định; TLS protocol và ALPN là hai phần thông tin riêng.
6. **Giữ kiểm thử hiện đại:** Dùng TLSv1.2/1.3 theo chính sách JDK và hệ thống. Không mở lại SSLv3/TLSv1.0/TLSv1.1 để “sửa” sự cố ALPN.

## 9. Lỗi thường gặp

| Triệu chứng | Nguyên nhân / hướng xử lý |
| --- | --- |
| `getApplicationProtocol() == null` | Gọi trước handshake hoặc chưa xác định ALPN. Với `SSLEngine`, kiểm tra tiến trình `wrap/unwrap`/delegated tasks. |
| `getApplicationProtocol().isEmpty()` | Handshake đã xác định không dùng ALPN; kiểm tra cấu hình danh sách ở **cả client và server** và chính sách fallback. |
| Handshake báo `no_application_protocol` | Hai đầu không có lựa chọn ALPN chung hoặc selector server từ chối. Đồng bộ danh sách giao thức, không tự bỏ qua lỗi. |
| `UnsupportedOperationException` | SSL provider không triển khai phương thức ALPN. Kiểm tra provider/JDK cấu hình thực tế, không xử lý như chuỗi rỗng. |
| `SSLHandshakeException` | Có thể do certificate/trust/hostname/TLS protocol/cipher suite **hoặc** ALPN; xem cause, stack trace và log JSSE an toàn. |
| Đọc `TLSv1.3` khi mong `h2` | Đã gọi `SSLSession.getProtocol()`; dùng `getApplicationProtocol()`. |
| `SSLParameters.getApplicationProtocols()` cho `h2` nhưng kết quả khác | Đây chỉ là danh sách được cấu hình; peer có quyền chọn giá trị khác hợp lệ, không chọn hoặc thất bại handshake. |
| `SSLEngine` kẹt ở `NEED_WRAP`/`NEED_UNWRAP` | Driver handshake thiếu vòng chuyển bytes, xử lý `BUFFER_UNDERFLOW`/`BUFFER_OVERFLOW` hoặc delegated tasks. Đây là lỗi orchestration TLS, không giải quyết chỉ bằng getter ALPN. |
| Server/client chọn khác nhau | Kiểm tra thực sự đang đọc cùng một kết nối/handshake, cấu hình ALPN trên accepted `SSLSocket` hoặc engine đúng instance; dùng cùng phiên trao đổi để đối chiếu. |

Khi debug JDK SunJSSE trong môi trường kiểm thử, có thể khởi chạy với `-Djavax.net.debug=ssl:handshake` để quan sát quá trình TLS. Log handshake có thể chứa metadata nhạy cảm; hạn chế truy cập và không dùng log chi tiết bừa bãi trên production.

## 10. Câu hỏi tự kiểm tra

1. Sau `socket.startHandshake()` thành công, gọi phương thức nào để biết ứng dụng đang dùng HTTP/2 hay HTTP/1.1?  
   **Đáp án:** `socket.getApplicationProtocol()`, rồi kiểm tra `"h2"` hoặc `"http/1.1"`.

2. `getApplicationProtocol()` trả `null` và `""` khác nhau thế nào?  
   **Đáp án:** `null` là **chưa xác định liệu ALPN có được dùng**; `""` là **đã xác định không sử dụng ALPN**.

3. `engine.beginHandshake()` đã trả về thì có đọc kết quả ALPN cuối ngay được không?  
   **Đáp án:** Không. Với `SSLEngine`, `beginHandshake()` chỉ bắt đầu handshake; cần điều khiển `wrap/unwrap` và tasks cho tới khi handshake hoàn tất.

4. `SSLParameters.getApplicationProtocols()` trả `["h2", "http/1.1"]` chứng minh server đã chọn `h2` chưa?  
   **Đáp án:** Chưa. Đó chỉ là danh sách cấu hình. Đọc `getApplicationProtocol()` sau handshake để biết kết quả.

5. Có thể dùng kết quả ALPN thay cho xác thực hostname/certificate không?  
   **Đáp án:** Không. ALPN và xác thực TLS là hai bước có chức năng khác nhau.

## 11. Tài liệu chính thức đang được duy trì

- [`SSLSocket` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLSocket.html): `getApplicationProtocol()`, `getHandshakeApplicationProtocol()` và `startHandshake()`.
- [`SSLEngine` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngine.html): ALPN getter và cơ chế handshake `wrap/unwrap`.
- [`SSLParameters` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setApplicationProtocols` và `getApplicationProtocols`.
- [`SSLEngineResult.HandshakeStatus` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/javax/net/ssl/SSLEngineResult.HandshakeStatus.html): `NEED_WRAP`, `NEED_UNWRAP`, `NEED_TASK`, `FINISHED`, `NOT_HANDSHAKING`.
- [RFC 7301 — TLS Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301): tiêu chuẩn trao đổi tên giao thức ứng dụng trong TLS.
