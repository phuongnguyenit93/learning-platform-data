# Bộ chọn giao thức phía máy chủ và trường hợp không tương thích trong TLS/ALPN

## 1. Bối cảnh: máy chủ chọn giao thức ứng dụng khi bắt tay TLS

**ALPN** (*Application-Layer Protocol Negotiation*, RFC 7301) cho phép máy khách và máy chủ thỏa thuận **giao thức tầng ứng dụng** ngay trong quá trình bắt tay TLS. Ví dụ, trên cùng cổng HTTPS, một máy chủ có thể hỗ trợ `h2` (HTTP/2 over TLS) và `http/1.1`. Máy khách thông báo danh sách giao thức mình chấp nhận; **máy chủ chọn tối đa một giao thức nằm trong danh sách ấy**.

~~~text
Client                                  TLS server
  | ClientHello: ALPN ["http/1.1","h2"]    |
  |-------------------------------------->|
  |                   Server policy:       |
  |                   prefer "h2"           |
  |<--------------------------------------|
  |          TLS handshake + ALPN "h2"      |
  |             ... hoàn tất ...           |
  |<========= HTTP/2 frames =============>|
~~~

Hình trên là mô hình khái niệm. Vị trí trường ALPN trong bản tin bắt tay phụ thuộc phiên bản TLS; ứng dụng nên dùng API JSSE thay vì thao tác trực tiếp với các bản tin đó.

**Phân biệt ba khái niệm:**

- **TLS protocol:** phiên bản kênh bảo mật, ví dụ `TLSv1.3`. Nó thuộc `SSLSocket.setEnabledProtocols(...)` hoặc `SSLParameters.setProtocols(...)`.
- **ALPN application protocol:** tên giao thức ứng dụng, ví dụ `h2` và `http/1.1`. Nó thuộc `SSLParameters.setApplicationProtocols(...)` hoặc bộ chọn ALPN.
- **SNI:** gợi ý tên máy chủ mà client muốn truy cập; có thể ảnh hưởng chứng chỉ/cấu hình máy chủ nhưng không phải là ALPN.

Trong Java 9, JSSE bổ sung API ALPN chuẩn lên `SSLParameters`, `SSLSocket` và `SSLEngine`. Các API này vẫn là cách làm hiện hành trên Java 17+, kể cả khi chạy TLS 1.3. Không cần dùng các extension ALPN không chuẩn của Java đời cũ.

**Tình huống chính:** máy chủ muốn tự quyết định ưu tiên giao thức hoặc chọn theo thông tin đã có trong handshake. Nếu không có giao thức chung thì xử lý ra sao, và vì sao không nên coi chuỗi rỗng là lựa chọn “từ chối” tự động?

## 2. Thỏa thuận mặc định và lựa chọn tùy chỉnh

### 2.1. Cách mặc định: `SSLParameters.setApplicationProtocols`

Trên socket máy chủ đã được chấp nhận:

~~~java
// Đoạn minh họa đặt trong nơi cấu hình một SSLSocket phía server.
SSLParameters parameters = serverSocket.getSSLParameters();
parameters.setApplicationProtocols(new String[] {"h2", "http/1.1"});
serverSocket.setSSLParameters(parameters);
~~~

Nếu client quảng bá `["http/1.1", "h2"]`, JSSE có thể chọn `h2` vì mảng phía server được sắp theo **thứ tự ưu tiên**, và giá trị đầu tiên trùng với danh sách client là ứng viên mặc định. `setApplicationProtocols` trên client xác định danh sách **được gửi**; nó không ép server phải chọn mục đầu tiên của client.

Điều kiện cần nhớ:

- Tên giao thức là chuỗi định danh chính xác; `"h2"` và `"http/1.1"` là hai giá trị khác nhau, không tự suy ra tương thích.
- Mảng `new String[0]` có nghĩa là không dùng chỉ báo giao thức ứng dụng qua cơ chế này. `null` hoặc phần tử `null`/`""` là đối số không hợp lệ cho `SSLParameters.setApplicationProtocols` và ném `IllegalArgumentException`.
- Nếu không có giá trị chung, cơ chế đàm phán tầng TLS sẽ quyết định kết quả; với ALPN theo RFC 7301, server **phải** phản hồi lỗi fatal `no_application_protocol` khi đã có lời đề nghị ALPN nhưng không có lựa chọn hợp lệ.
- Một giá trị có thể đã được đàm phán nhưng ứng dụng máy chủ vẫn cần **thực sự triển khai đúng giao thức ấy**. ALPN chọn tên, không biến phần mềm HTTP/1.1 thành bộ xử lý HTTP/2.

### 2.2. Bộ chọn server tùy chỉnh

Hai API tương ứng là:

~~~java
// SSLSocket: trong code cấu hình socket phía máy chủ.
serverSocket.setHandshakeApplicationProtocolSelector(
        (socket, clientProtocols) -> {
            if (clientProtocols.contains("h2")) {
                return "h2";
            }
            if (clientProtocols.contains("http/1.1")) {
                return "http/1.1";
            }
            return null;
        });
~~~

~~~java
// SSLEngine: trong code cấu hình engine phía máy chủ.
serverEngine.setUseClientMode(false);
serverEngine.setHandshakeApplicationProtocolSelector(
        (engine, clientProtocols) -> {
            if (clientProtocols.contains("h2")) {
                return "h2";
            }
            if (clientProtocols.contains("http/1.1")) {
                return "http/1.1";
            }
            return null;
        });
~~~

Hai đoạn trên **minh họa**; biến `serverSocket` và `serverEngine` phải được tạo trong mã TLS thật. Bộ chọn là một `BiFunction<SSLSocket, List<String>, String>` hoặc `BiFunction<SSLEngine, List<String>, String>`. Tham số `clientProtocols` là danh sách client đã quảng bá trong handshake; trả về một chuỗi biểu thị giao thức được chọn.

**Quan trọng:** khi đã đăng ký callback tùy chỉnh, **lựa chọn của callback thay thế** thuật toán chọn mặc định dựa trên `SSLParameters.setApplicationProtocols`. Đừng giả định rằng mảng mặc định sẽ tự giới hạn giá trị callback trả về. Chính callback phải thực hiện quy tắc: chỉ chọn giá trị **client quảng bá** và **server thực sự hỗ trợ**, đồng thời tương thích với cấu hình TLS/ứng dụng.

### 2.3. Cài bộ chọn vào đúng thời điểm

- Với `SSLSocket` server tạo qua `SSLServerSocket.accept()`, đăng ký selector và hoàn tất cấu hình **trước** khi bắt đầu handshake hoặc bất kỳ thao tác I/O nào làm handshake tự khởi động.
- Với `SSLEngine`, đăng ký trước `beginHandshake()`/lượt `wrap` hoặc `unwrap` đầu tiên làm handshake bắt đầu. Phần xử lý `SSLEngine` phải tiếp tục điều khiển trạng thái handshake, buffer và delegated tasks theo contract; selector không tự làm những việc đó.
- `SSLServerSocket` là listener; callback chuẩn được đặt trên **`SSLSocket` đã accept** hoặc `SSLEngine` cụ thể, không phải một callback chung trên `SSLServerSocket`.
- Callback nên nhanh, xác định và không thực hiện I/O mạng/chờ database. Có thể đọc `getHandshakeSession()` để tham khảo TLS version/cipher suite/SNI khi cần, nhưng phải áp dụng policy đúng và không lệ thuộc vào thông tin chưa có.
- Muốn trở về lựa chọn mặc định, có thể đăng ký selector `null` (hủy callback); **trả `null` từ một callback đang chạy có ý nghĩa hoàn toàn khác**.

## 3. Ba kết quả trả về của bộ chọn: không được nhầm lẫn

Theo hợp đồng API của `SSLSocket.setHandshakeApplicationProtocolSelector` và `SSLEngine.setHandshakeApplicationProtocolSelector`:

| Callback trả về | Ý nghĩa | Hành vi cần hiểu |
| --- | --- | --- |
| `"h2"` hoặc tên không rỗng khác mà client đã quảng bá | Server chọn đúng một protocol | Có thể bắt tay thành công nếu toàn bộ điều kiện TLS/cấu hình khác hợp lệ. |
| `null` | **Không có protocol client quảng bá nào chấp nhận được** | Trong ALPN, thông thường phát cảnh báo fatal `no_application_protocol` và thất bại handshake. |
| `""` (chuỗi rỗng) | **Không sử dụng chỉ báo protocol ứng dụng** | Không tương đương từ chối ALPN; TLS có thể hoàn tất nhưng không chọn application protocol. |
| Tên không rỗng nhưng **client không quảng bá** | Trả về protocol không hợp lệ đối với client | ALPN có thể kết thúc handshake với `no_application_protocol`. |

Điểm phải tách bạch:

~~~java
// Client đã quảng bá nhưng server không có protocol chung:
return null; // Từ chối chọn: bắt tay ALPN sẽ thất bại.

// Chỉ khi thiết kế cho phép handshake không có ALPN:
return ""; // Không dùng chỉ báo application protocol.
~~~

**Không dùng `return ""` làm fallback thường trực khi hai phía không tương thích.** Điều đó có thể cho phép TLS kết nối nhưng để giao thức ứng dụng mập mờ; nếu server và client hiểu khác nhau về byte tiếp theo, nguy cơ nhầm lẫn giao thức hoặc xử lý dữ liệu sai xuất hiện. RFC 9325 khuyến nghị thực thi nghiêm quy tắc từ chối khi không có ALPN chung để giảm nguy cơ *cross-protocol*.

Cũng cần phân biệt callback trả `null` với lời gọi đăng ký `setHandshakeApplicationProtocolSelector(null)`: lời gọi đăng ký hủy callback; giá trị trả trong callback đang được thực thi báo không có lựa chọn hợp lệ.

## 4. Thuật toán chọn protocol theo policy của server

Một hàm độc lập có thể chạy trên mọi Java 17+:

~~~java
import java.util.List;

public final class ProtocolChoice {
    private static final List<String> SUPPORTED =
            List.of("h2", "http/1.1"); // Thứ tự server ưu tiên.

    private ProtocolChoice() {}

    public static String select(List<String> clientOffers) {
        for (String serverPreferred : SUPPORTED) {
            if (clientOffers.contains(serverPreferred)) {
                return serverPreferred;
            }
        }
        return null; // Không có giao thức chung.
    }

    public static void main(String[] args) {
        System.out.println(select(List.of("http/1.1", "h2")));
        System.out.println(select(List.of("http/1.1")));
        System.out.println(select(List.of("mqtt")));
    }
}
~~~

Lưu thành `ProtocolChoice.java` rồi chạy:

~~~bash
javac -encoding UTF-8 ProtocolChoice.java
java ProtocolChoice
~~~

Stdout:

~~~text
h2
http/1.1
null
~~~

Hàm duyệt theo **thứ tự ưu tiên server**, đồng thời chỉ nhận các protocol client đã quảng bá. `List.contains` đủ rõ ràng khi danh sách ALPN nhỏ; trong hệ thống có nhiều protocol, có thể chuẩn hóa dữ liệu hỗ trợ một lần (không sửa/chuẩn hóa tên ALPN client theo cách làm thay đổi danh tính).

Ma trận lựa chọn của policy ở ví dụ:

| Client quảng bá | Server thực sự hỗ trợ | Callback chọn | Kết luận |
| --- | --- | --- | --- |
| `["http/1.1","h2"]` | `["h2","http/1.1"]` | `"h2"` | Hai phía có chung; server ưu tiên h2. |
| `["http/1.1"]` | `["h2","http/1.1"]` | `"http/1.1"` | Hợp lệ; không ép h2 khi client không gửi. |
| `["mqtt"]` | `["h2","http/1.1"]` | `null` | Không có chung; từ chối ALPN. |
| `["h2"]` | Chỉ triển khai HTTP/1.1 | `null` | Không giả vờ hỗ trợ HTTP/2. |
| **Không có extension ALPN** | Hai protocol phía server | Callback có thể không được gọi | TLS có thể hoàn tất **không có ALPN**; ứng dụng quyết định chính sách sau handshake. |

**Trường hợp client không gửi ALPN hoàn toàn** khác với trường hợp client đã gửi danh sách nhưng tất cả đều không tương thích. Một server chỉ phục vụ HTTP/2 qua TLS nên yêu cầu kết quả chính xác `"h2"`; server cũng hỗ trợ HTTP/1.1 và cho phép kết nối không ALPN thì phải có policy fallback rõ ràng ở tầng ứng dụng. Không dùng cùng một hành động cho mọi hệ thống.

## 5. Ví dụ TLS thật trên localhost: thành công, không tương thích và không quảng bá

Ví dụ này chạy với **Java 17+**, sử dụng `SSLSocket` thật ở cả client lẫn server. Chứng chỉ tự ký và trust store chỉ dùng cho kiểm thử localhost; client vẫn **xác thực server bằng trust store và kiểm tra IP trong SAN**, không dùng trust manager “tin tất cả”. Không cần tải thư viện bên thứ ba.

### 5.1. Sinh chứng chỉ thử nghiệm

Dùng `keytool` đi kèm JDK, chạy từ một thư mục thử nghiệm trống:

~~~bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -validity 2 -storetype PKCS12 -keystore demo.p12 -storepass changeit -keypass changeit -dname "CN=localhost" -ext "SAN=ip:127.0.0.1" -noprompt
~~~

Chứng chỉ này chỉ có hiệu lực ngắn và chỉ phục vụ demo. Không đưa `demo.p12` hoặc mật khẩu trong ví dụ vào repository hay hệ thống production. Ở môi trường thật, dùng chứng chỉ và trust store do tổ chức/CA quản lý.

### 5.2. Mã chương trình đầy đủ

Lưu tệp `AlpnServerDemo.java` cùng thư mục với `demo.p12`:

~~~java
import javax.net.ssl.*;
import java.io.IOException;
import java.io.InputStream;
import java.net.InetAddress;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.List;
import java.util.concurrent.atomic.AtomicReference;

public class AlpnServerDemo {
    static SSLContext sslContext(Path storePath) throws Exception {
        char[] password = "changeit".toCharArray();
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream stream = Files.newInputStream(storePath)) {
            store.load(stream, password);
        }

        KeyManagerFactory keys = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        keys.init(store, password);

        TrustManagerFactory trust = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        trust.init(store);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(keys.getKeyManagers(), trust.getTrustManagers(), null);
        return context;
    }

    static String select(List<String> offered) {
        // Server policy: prefer h2, then http/1.1.
        for (String preferred : List.of("h2", "http/1.1")) {
            if (offered.contains(preferred)) {
                return preferred;
            }
        }
        return null; // No mutual protocol: reject ALPN negotiation.
    }

    static String negotiate(SSLContext context, String... clientOffers)
            throws Exception {
        try (SSLServerSocket listener =
                (SSLServerSocket) context.getServerSocketFactory()
                        .createServerSocket(0, 16,
                                InetAddress.getByName("127.0.0.1"))) {
            AtomicReference<String> serverState = new AtomicReference<>("UNSET");
            Thread server = new Thread(() -> {
                try (SSLSocket socket = (SSLSocket) listener.accept()) {
                    socket.setEnabledProtocols(new String[] {"TLSv1.3"});
                    SSLParameters params = socket.getSSLParameters();
                    params.setApplicationProtocols(
                            new String[] {"http/1.1", "h2"});
                    socket.setSSLParameters(params);
                    socket.setHandshakeApplicationProtocolSelector(
                            (sslSocket, offered) -> select(offered));
                    socket.startHandshake();
                    serverState.set("OK:" + socket.getApplicationProtocol());
                } catch (SSLException failure) {
                    serverState.set("REJECTED");
                } catch (IOException failure) {
                    serverState.set("IO_ERROR");
                }
            });
            server.start();

            String clientState;
            try (SSLSocket client = (SSLSocket) context.getSocketFactory()
                    .createSocket("127.0.0.1", listener.getLocalPort())) {
                client.setEnabledProtocols(new String[] {"TLSv1.3"});
                SSLParameters params = client.getSSLParameters();
                params.setApplicationProtocols(clientOffers);
                params.setEndpointIdentificationAlgorithm("HTTPS");
                client.setSSLParameters(params);
                try {
                    client.startHandshake();
                    String chosen = client.getApplicationProtocol();
                    clientState = chosen.isEmpty() ? "NO_ALPN" : "OK:" + chosen;
                } catch (SSLException failure) {
                    clientState = "REJECTED";
                }
            }

            server.join(5000);
            if (server.isAlive()) {
                throw new IllegalStateException("Server handshake did not finish");
            }
            if ("UNSET".equals(serverState.get())
                    || "IO_ERROR".equals(serverState.get())) {
                throw new IllegalStateException(
                        "Server failed: " + serverState.get());
            }
            return clientState;
        }
    }

    public static void main(String[] args) throws Exception {
        SSLContext context = sslContext(Path.of("demo.p12"));
        System.out.println("compatible: "
                + negotiate(context, "http/1.1", "h2"));
        System.out.println("incompatible: "
                + negotiate(context, "mqtt"));
        System.out.println("ALPN absent: " + negotiate(context));
    }
}
~~~

Chạy:

~~~bash
javac -encoding UTF-8 AlpnServerDemo.java
java AlpnServerDemo
~~~

Stdout chương trình trên JDK 24 với nhà cung cấp mặc định SunJSSE:

~~~text
compatible: OK:h2
incompatible: REJECTED
ALPN absent: NO_ALPN
~~~

**Giải thích đầu ra:**

1. **`compatible: OK:h2`** — client quảng bá cả `http/1.1` và `h2`; bộ chọn server ưu tiên `h2`, mặc dù `SSLParameters` phía server được cấu hình theo thứ tự ngược. Đây là bằng chứng callback tùy chỉnh quyết định lựa chọn.
2. **`incompatible: REJECTED`** — client chỉ quảng bá `mqtt`; callback trả `null` vì server không hỗ trợ. Với ALPN trên SunJSSE, handshake thất bại (ví dụ thông báo TLS `no_application_protocol`).
3. **`ALPN absent: NO_ALPN`** — client truyền mảng protocol rỗng, nên không quảng bá ALPN. TLS 1.3 vẫn có thể hoàn tất, nhưng `getApplicationProtocol()` trả `""`. Đây **không** phải trường hợp “đã chọn một giao thức mặc định”.

Bộ test ghi kết quả từ phía client, còn thread server ghi nhận trạng thái để kiểm tra hoàn tất. Nó cố ý không trao đổi frame HTTP/2 hoặc HTTP/1.1 sau TLS; sau handshake, ứng dụng thực tế phải điều hướng đến đúng parser/protocol handler.

**Giới hạn kiểm chứng:** ví dụ đã được chạy với JDK 24/SunJSSE, nhưng lời mô tả exception/message, tập cipher và trường hợp no-ALPN có thể chịu ảnh hưởng chính sách bảo mật/provider. Điều quan trọng là các contract API và chính sách chọn/từ chối; không ràng buộc business logic vào chuỗi message của một provider.

## 6. Đọc giá trị ALPN và quyết định xử lý sau handshake

`SSLSocket.getApplicationProtocol()` và `SSLEngine.getApplicationProtocol()` trả giá trị ứng dụng đã thương lượng trên **kết nối**:

- `null` khi chưa xác định liệu ALPN có được dùng cho kết nối hay không;
- `""` nếu kết nối không dùng giá trị application protocol;
- tên không rỗng như `"h2"` hoặc `"http/1.1"` nếu đã thương lượng thành công.

`getHandshakeApplicationProtocol()` dành cho thời điểm **handshake đang tiến hành**; có thể chưa có kết quả. Sau khi handshake hoàn tất, dùng `getApplicationProtocol()` để quyết định cách xử lý dữ liệu.

Một policy nghiêm ngặt cho server **chỉ phục vụ HTTP/2 over TLS**:

~~~java
// Đoạn minh họa đặt sau socket.startHandshake() thành công.
String negotiated = socket.getApplicationProtocol();
if (!"h2".equals(negotiated)) {
    socket.close();
    throw new javax.net.ssl.SSLHandshakeException(
            "Server requires ALPN h2");
}
// Chỉ sau đó mới chuyển kết nối sang HTTP/2 handler.
~~~

Nếu server cho phép cả HTTP/2 và HTTP/1.1:

~~~java
// Đoạn minh họa: dispatcher thực sự phải có hai handler riêng.
String negotiated = socket.getApplicationProtocol();
switch (negotiated) {
    case "h2":
        // Dùng HTTP/2 frame handler.
        break;
    case "http/1.1":
        // Dùng HTTP/1.1 handler.
        break;
    case "":
        // Không có ALPN: áp dụng policy có chủ đích hoặc đóng kết nối.
        socket.close();
        break;
    default:
        socket.close();
        throw new IllegalStateException(
                "Unexpected application protocol: " + negotiated);
}
~~~

Hai đoạn code trên **không độc lập để chạy** vì `socket` đại diện một kết nối TLS đã hoàn tất handshake và phần handler ứng dụng chưa triển khai. Chúng minh họa ranh giới an toàn: **chọn được tên** không tự động làm ứng dụng nói đúng giao thức. Không lấy `getSession().getProtocol()` (sẽ là TLS version như `TLSv1.3`) thay cho `getApplicationProtocol()`.

RFC 7301 gắn lựa chọn ALPN với **kết nối**, không phải một thuộc tính cố định của session có thể được tái sử dụng tùy ý. Sau session resumption hoặc kết nối mới, luôn dựa vào kết quả ALPN của kết nối/handshake hiện tại.

## 7. Trường hợp không tương thích và cách xử lý đúng

| Trường hợp | Triệu chứng có thể thấy | Nguyên nhân | Hành động phù hợp |
| --- | --- | --- | --- |
| Client quảng bá `h2`, server chỉ hỗ trợ `http/1.1` | `SSLHandshakeException` / TLS alert `no_application_protocol` | Không có giao thức chung | Chỉ bật giao thức cùng được triển khai ở **hai phía** hoặc từ chối kết nối. |
| Callback trả `null` vì không có giao thức chung | Handshake fail trong ALPN | Từ chối lựa chọn | Đây là nhánh hợp lý cho policy nghiêm ngặt; log protocol offers đã chuẩn hóa phù hợp. |
| Callback trả `""` với lời đề nghị không tương thích | TLS có thể thành công nhưng ALPN rỗng | Bỏ chọn protocol ứng dụng | Không dùng như “chữa lỗi”; cần policy xử lý no-ALPN tường minh. |
| Callback chọn chuỗi client không quảng bá | Handshake thường fail | Vi phạm danh sách của peer | Luôn tính giao của protocol server/client trước khi chọn. |
| Client không quảng bá ALPN | Có thể handshake thành công; `getApplicationProtocol() == ""` | Không có thông tin ALPN để chọn | Nếu ứng dụng bắt buộc ALPN thì đóng kết nối; nếu không, chỉ fallback theo contract thực tế. |
| Client/server không thống nhất TLS/cipher/cert | `SSLHandshakeException` nhưng không nhất thiết có alert ALPN | Lỗi bảo mật TLS, trust, chứng chỉ hoặc bộ mật mã | Chẩn đoán TLS trước; không thay đổi selector để che lỗi. |
| Client quảng bá `h2` nhưng server HTTP stack không có HTTP/2 handler | TLS có thể thành công, dữ liệu sau đó lỗi | Chọn protocol mà ứng dụng không triển khai | Sửa danh sách hỗ trợ/selector; bảo đảm dispatcher tương ứng. |
| API selector ném `UnsupportedOperationException` | Thất bại khi cài callback | SSL provider không hỗ trợ khả năng tương ứng | Kiểm tra JDK và provider; quyết định dùng provider hỗ trợ hoặc cấu hình mặc định có kiểm chứng. |

**Không phải mọi `SSLHandshakeException` đều là lỗi ALPN.** Nó còn có thể do sai chứng chỉ, không có giao thức/cipher chung, SNI, mTLS, trust store hoặc chính sách bảo mật. Đọc nguyên nhân thật và dùng log JSSE có chọn lọc.

## 8. Cấu hình và bảo mật trong hệ thống thực tế

### 8.1. TLS bảo mật và lựa chọn ứng dụng là hai tầng độc lập

ALPN không thay TLS authentication, không xác minh hostname và không cung cấp HTTP authorization. Trên client, cấu hình trust store/hostname verification đúng; trên server, quản lý certificate, cipher suites, TLS version và mTLS theo chính sách tổ chức. Ví dụ sử dụng `TLSv1.3` là cấu hình kiểm thử hiện đại; nếu hệ thống cần TLS 1.2 vẫn được hỗ trợ theo chính sách, nhưng tuyệt đối không bật TLS 1.0/1.1 chỉ để giảm lỗi ALPN.

Không “sửa” lỗi tương thích ALPN bằng cách bỏ kiểm tra chứng chỉ, dùng TrustManager tin mọi chứng chỉ, hoặc trả bất kỳ tên giao thức nào client muốn mà server chưa triển khai.

### 8.2. Tương tác với HTTP/2

`h2` là ALPN identifier cho HTTP/2 over TLS; `http/1.1` cho HTTP/1.1. Một server công bố `h2` phải đồng thời thỏa các yêu cầu về TLS/cipher/protocol của HTTP/2 và thực thi HTTP/2 framing. Selector có thể dùng `getHandshakeSession()` để biết thông tin TLS khi chính sách cần; JSSE cũng khuyến cáo cấu hình TLS phải tương thích giao thức ứng dụng do callback chọn.

Nếu dùng Netty, Jetty, Tomcat hoặc framework làm TLS/HTTP, thường nên cấu hình ALPN qua framework/container và để framework điều hướng handler. Chỉ viết callback JSSE trực tiếp khi sở hữu tầng TLS hoặc cần policy rất cụ thể; tránh gắn thêm callback có thể xung đột với cấu hình ALPN của framework.

### 8.3. Logging và kiểm thử có kiểm soát

Nên ghi log ở mức cần thiết: client offers, giao thức được chọn, TLS version, tên provider và loại/nhân quả ngoại lệ. **Không** log private key, session secrets, raw key material hoặc thông tin nhạy cảm từ handshake.

Trong môi trường kiểm thử có thể bật JSSE debug tạm thời:

~~~bash
java -Djavax.net.debug=ssl:handshake AlpnServerDemo
~~~

Debug TLS thường rất nhiều dữ liệu; chỉ dùng khi chẩn đoán, tránh đẩy log chứa thông tin kết nối nhạy cảm vào hệ thống log công khai. Có thể lọc thông tin chứa `application_layer_protocol_negotiation`, `no_application_protocol` và TLS alert; chuỗi log cụ thể phụ thuộc provider/JDK.

Test ít nhất các trường hợp: client chỉ hỗ trợ giao thức ưu tiên thấp hơn; client hỗ trợ giao thức ưu tiên cao; client có danh sách không giao; client không gửi ALPN; callback trả protocol chưa được quảng bá; nhiều kết nối liên tiếp; sai trust/certificate (để bảo đảm không quy nhầm lỗi TLS sang lỗi ALPN).

## 9. Lỗi suy luận thường gặp

1. **Dùng `return ""` khi không có giao thức chung.** Điều này bỏ qua lựa chọn ALPN thay vì từ chối protocol không tương thích. Với ALPN nghiêm ngặt, trả `null`.
2. **Nghĩ selector còn bị danh sách `setApplicationProtocols` giới hạn tự động.** Khi callback được cài, thuật toán mặc định từ mảng bị thay thế; callback phải tự kiểm tra protocol server/client.
3. **Nhầm `setHandshakeApplicationProtocolSelector(null)` với callback trả `null`.** Một hành động tắt callback; hành động còn lại báo không có protocol được chấp nhận khi callback đang chạy.
4. **Cho rằng callback chắc chắn được gọi dù client không gửi ALPN.** Khi không có extension ALPN, không thể dựa vào callback như một cơ chế từ chối duy nhất. Kiểm tra kết quả sau handshake nếu policy bắt buộc ALPN.
5. **Nhầm `getSession().getProtocol()` với ALPN.** Giá trị đầu là TLS version; ALPN thuộc `getApplicationProtocol()`.
6. **Quên routing handler:** chọn `h2` nhưng xử lý HTTP/1.1 sau đó; TLS vẫn có thể thành công trước khi ứng dụng thất bại.
7. **Bỏ kiểm tra hostname/certificate để demo chạy:** điều đó tạo lỗ hổng độc lập với ALPN.
8. **Cố chữa mọi handshake exception bằng đổi protocol ALPN:** có thể che lỗi chứng chỉ/cipher/trust khác; phải đọc chứng cứ.
9. **Dùng công nghệ ALPN riêng của các bản Java cũ:** JSSE Java 9+ đã có API chuẩn, nên ưu tiên API hiện hành.
10. **Mặc định rằng kết quả ALPN gắn vĩnh viễn với TLS session:** hãy sử dụng kết quả cho kết nối cụ thể, kể cả sau resumption.

## 10. Tự kiểm tra

**Câu 1.** Server hỗ trợ `["h2", "http/1.1"]`, client gửi `["http/1.1", "h2"]`. Server có bắt buộc chọn mục đầu của client không?

**Không.** Server áp chính sách ưu tiên của chính mình và phải chọn một giá trị trong danh sách client. Ví dụ này chọn `h2`.

**Câu 2.** Khi client gửi ALPN `["mqtt"]` nhưng server chỉ triển khai HTTPS, selector nên trả `null` hay `""`?

**`null`** để biểu thị không có giao thức quảng bá nào được chấp nhận. `""` nghĩa là không dùng chỉ báo ALPN và có thể khiến TLS tiếp tục mà không có giao thức ứng dụng được chọn.

**Câu 3.** Sau `startHandshake()` thành công, `getApplicationProtocol()` trả `""`. Có được suy ra máy chủ đang dùng HTTP/1.1 không?

**Không.** Đó là trạng thái không có ALPN; muốn fallback HTTP/1.1 phải có policy/contract rõ ràng và handler hỗ trợ.

**Câu 4.** Vì sao callback trả `"h2"` ngay cả khi client không quảng bá `h2` là sai?

ALPN buộc lựa chọn phải nằm trong danh sách client. Trả giá trị ngoài danh sách có thể kết thúc handshake với `no_application_protocol`.

**Câu 5.** Vì sao dùng `TLSv1.3` không đảm bảo HTTP/2?

`TLSv1.3` chỉ là phiên bản bảo mật; cần ALPN chọn `h2` và bộ HTTP/2 handler thực sự hoạt động.

## Tài liệu chuẩn và API đang sử dụng

- [Oracle Java 25 — `SSLSocket.setHandshakeApplicationProtocolSelector`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLSocket.html#setHandshakeApplicationProtocolSelector(java.util.function.BiFunction))
- [Oracle Java 25 — `SSLEngine.setHandshakeApplicationProtocolSelector`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLEngine.html#setHandshakeApplicationProtocolSelector(java.util.function.BiFunction))
- [Oracle Java 25 — `SSLParameters.setApplicationProtocols`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/javax/net/ssl/SSLParameters.html#setApplicationProtocols(java.lang.String%5B%5D))
- [Oracle — JSSE Reference Guide: TLS Application Layer Protocol Negotiation](https://docs.oracle.com/en/java/javase/25/security/java-secure-socket-extension-jsse-reference-guide.html)
- [IETF RFC 7301 — TLS Application-Layer Protocol Negotiation](https://www.rfc-editor.org/rfc/rfc7301.html)
- [IETF RFC 9325 — Recommendations for Secure TLS/DTLS Use, mục ALPN](https://www.rfc-editor.org/rfc/rfc9325.html#section-3.8)