# TLS và JDK

**TLS (Transport Layer Security)** là giao thức bảo vệ dữ liệu khi truyền qua mạng. Trong Java, JDK cung cấp **JSSE (Java Secure Socket Extension)** và các API liên quan để ứng dụng thiết lập kết nối TLS, xác thực certificate, mã hóa dữ liệu và tùy chọn xác thực cả hai phía.

TLS được sử dụng rộng rãi trong HTTPS, kết nối database, service-to-service communication, mail, LDAP và nhiều giao thức khác. Hiểu TLS trong JDK giúp lập trình viên cấu hình certificate, keystore, truststore, giao thức, hostname verification và chẩn đoán lỗi handshake đúng cách.

## 1. TLS bảo vệ kết nối như thế nào?

TLS cung cấp các thuộc tính bảo mật chính:

- **Confidentiality:** mã hóa dữ liệu để bên thứ ba không đọc được nội dung truyền đi.
- **Integrity:** phát hiện dữ liệu bị sửa đổi trong quá trình truyền.
- **Peer authentication:** xác thực máy chủ bằng certificate; có thể xác thực cả client khi dùng mutual TLS.
- **Key establishment:** hai bên thiết lập khóa phiên để mã hóa dữ liệu sau handshake.

TLS không tự quyết định người dùng được phép làm gì trong ứng dụng. Certificate xác thực danh tính ở tầng kết nối; authorization vẫn là trách nhiệm của ứng dụng và hệ thống nghiệp vụ.

TLS cũng không mã hóa dữ liệu đang lưu trong database, file hoặc log. Nó bảo vệ dữ liệu trên đường truyền giữa các endpoint TLS.

## 2. TLS handshake diễn ra như thế nào?

Khi client kết nối đến máy chủ HTTPS, hai bên thực hiện TLS handshake trước khi trao đổi dữ liệu HTTP được bảo vệ.

Luồng tổng quát:

1. Client gửi **ClientHello**, thông báo phiên bản TLS, cipher suites, key share và các extension hỗ trợ. Với kết nối theo hostname, client thường gửi SNI để máy chủ chọn certificate phù hợp.
2. Server chọn tham số bảo mật tương thích và gửi **ServerHello**.
3. Server gửi certificate chain và bằng chứng sở hữu private key theo cơ chế của phiên bản TLS.
4. Client kiểm tra certificate chain, thời hạn, mục đích sử dụng và hostname.
5. Hai bên hoàn tất trao đổi khóa và xác nhận handshake bằng thông điệp Finished.
6. Sau handshake, dữ liệu ứng dụng được mã hóa và bảo vệ toàn vẹn bằng khóa phiên.

Với TLS 1.3, quy trình handshake được tinh gọn so với TLS 1.2 và chỉ giữ các lựa chọn mật mã hiện đại hơn. Chi tiết thông điệp khác nhau giữa TLS 1.2 và TLS 1.3, nhưng mục tiêu vẫn là xác thực peer, thống nhất khóa và bảo vệ dữ liệu.

Nếu certificate không hợp lệ hoặc không được tin cậy, client thường dừng handshake trước khi gửi request ứng dụng.

## 3. TLS 1.2 và TLS 1.3 trong JDK

Các JDK hiện đại hỗ trợ TLS 1.2 và TLS 1.3. TLS 1.3 được hỗ trợ từ JDK 11; Java 17 có thể dùng TLS 1.3 và TLS 1.2 theo cấu hình/provider của môi trường.

| Phiên bản | Đặc điểm |
| --- | --- |
| TLS 1.3 | Handshake đơn giản hơn, loại bỏ nhiều thuật toán và cơ chế cũ, thường giảm độ trễ kết nối |
| TLS 1.2 | Vẫn được sử dụng rộng rãi và cần cho một số hệ thống chưa hỗ trợ TLS 1.3 |
| TLS 1.1 / TLS 1.0 | Đã lỗi thời, không nên bật cho hệ thống mới |
| SSLv3 và cũ hơn | Không an toàn, không sử dụng |

Trong môi trường production, ưu tiên TLS 1.3 và chỉ giữ TLS 1.2 khi cần tương thích với hệ thống đích. Không bật lại protocol hoặc cipher suite yếu chỉ để bỏ qua lỗi handshake mà chưa đánh giá rủi ro.

Các protocol và cipher suite thực sự được bật phụ thuộc phiên bản JDK, security provider, file `java.security`, system properties và cấu hình ứng dụng.

## 4. JSSE là gì?

**JSSE** là bộ API và provider của Java hỗ trợ TLS/SSL. Nó cung cấp các lớp để ứng dụng tạo kết nối bảo mật ở nhiều mức trừu tượng.

Các lớp quan trọng:

| API | Vai trò |
| --- | --- |
| `SSLContext` | Điểm khởi tạo cấu hình TLS, protocol, key manager và trust manager |
| `SSLSocket` | Socket TCP có bảo vệ TLS |
| `SSLSocketFactory` | Tạo socket TLS |
| `SSLServerSocket` | Server socket nhận kết nối TLS |
| `SSLEngine` | Xử lý TLS handshake và record trên ByteBuffer, không tự quản lý socket/network I/O |
| `TrustManager` | Quyết định certificate peer có được tin cậy hay không |
| `KeyManager` | Chọn key và certificate của local endpoint khi cần xác thực |
| `TrustManagerFactory` | Tạo trust manager từ truststore hoặc nguồn certificate |
| `KeyManagerFactory` | Tạo key manager từ keystore |
| `SSLParameters` | Cấu hình protocol, cipher suite, endpoint identification và các tham số TLS |

Ứng dụng cấp cao như `java.net.http.HttpClient` và `HttpsURLConnection` sử dụng JSSE ở bên dưới. Với phần lớn ứng dụng HTTP, nên dùng API HTTP cấp cao thay vì tự xây dựng TLS protocol.

## 5. Keystore và truststore trong TLS

Hai loại kho certificate thường gặp:

**Keystore** lưu private key của chính ứng dụng hoặc máy chủ cùng certificate tương ứng và certificate chain. Ví dụ HTTPS server cần keystore chứa private key và certificate của hostname.

**Truststore** lưu certificate CA hoặc certificate được ứng dụng tin cậy. Client dùng truststore để xác minh certificate của server. Trong mutual TLS, server cũng cần truststore để xác minh certificate client.

| Thành phần | Lưu gì? | Dùng khi nào? |
| --- | --- | --- |
| Server keystore | Private key server và certificate chain | Server chứng minh danh tính |
| Client truststore | CA hoặc certificate được client tin cậy | Client xác minh server |
| Client keystore | Private key client và certificate chain | Client xác thực với server trong mTLS |
| Server truststore | CA hoặc certificate được server tin cậy | Server xác minh client trong mTLS |

PKCS12 là định dạng keystore phổ biến và phù hợp cho ứng dụng mới. JKS vẫn có thể xuất hiện trong hệ thống Java cũ.

Certificate công khai có thể được chia sẻ; private key phải được giữ bí mật. Không đặt keystore chứa private key vào source repository hoặc gửi qua kênh không bảo mật.

## 6. Truststore mặc định của JDK

Nếu ứng dụng không cấu hình truststore riêng, JSSE sử dụng cấu hình trust mặc định của JDK. Thông thường, JDK tìm truststore theo thứ tự:

1. Giá trị system property `javax.net.ssl.trustStore`, nếu được đặt.
2. Tệp `jssecacerts` trong thư mục security của Java home, nếu tồn tại.
3. Tệp `cacerts` trong thư mục security của Java home.

Vị trí phổ biến là:

```text
<JAVA_HOME>/lib/security/cacerts
```

Truststore mặc định thường chứa các CA root được JDK phân phối. Danh sách CA có thể khác theo vendor, phiên bản JDK và cách đóng gói.

Liệt kê certificate trong truststore mặc định:

```bash
keytool -list -cacerts
```

Để xem chi tiết:

```bash
keytool -list -v -cacerts
```

Keytool có thể yêu cầu mật khẩu truststore. Không thay đổi `cacerts` trực tiếp trong môi trường production nếu không có quy trình quản lý trust phù hợp; ưu tiên truststore riêng cho ứng dụng khi cần kiểm soát danh sách CA.

## 7. Tạo certificate thử nghiệm cho HTTPS localhost

Để thử TLS trong môi trường development, có thể tạo key pair và certificate tự ký bằng `keytool`.

Tạo keystore PKCS12 có alias `localhost`:

```bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -validity 365 -storetype PKCS12 -keystore server.p12 -dname "CN=localhost, OU=Development, O=Example Org, C=VN" -ext "SAN=dns:localhost,ip:127.0.0.1"
```

Giải thích:

- `-genkeypair`: tạo private key và certificate.
- `-alias localhost`: tên entry trong keystore.
- `-keyalg RSA -keysize 3072`: chọn RSA 3072 bit.
- `-storetype PKCS12`: lưu trong định dạng PKCS12.
- `-keystore server.p12`: tên tệp keystore.
- `-dname`: thông tin subject.
- `-ext "SAN=..."`: thêm Subject Alternative Name cho DNS name và IP.

Với HTTPS, hostname verification hiện đại dựa trên SAN. Certificate cho `https://localhost` cần SAN có `dns:localhost`; nếu truy cập bằng `https://127.0.0.1`, cần SAN dạng IP tương ứng. Chỉ đặt CN là localhost là chưa đủ cho các client hiện đại.

Keytool yêu cầu nhập mật khẩu. Dùng mật khẩu mạnh và không ghi mật khẩu thật vào shell history.

## 8. Xuất certificate và tạo truststore cho client

Xuất certificate công khai từ keystore server:

```bash
keytool -exportcert -rfc -alias localhost -keystore server.p12 -storetype PKCS12 -file localhost.crt
```

Kiểm tra certificate và fingerprint:

```bash
keytool -printcert -file localhost.crt -v
```

Tạo truststore client và import certificate:

```bash
keytool -importcert -alias localhost -file localhost.crt -keystore client-truststore.p12 -storetype PKCS12
```

Trước khi xác nhận import, so sánh fingerprint certificate qua một kênh độc lập đáng tin cậy. Trong ví dụ localhost, certificate tự ký được import trực tiếp như trust anchor cho môi trường thử nghiệm.

Phân biệt:

- `server.p12` chứa private key của server; không chia sẻ tệp này.
- `localhost.crt` chỉ chứa certificate và public key; có thể phân phối cho client.
- `client-truststore.p12` chứa certificate mà client tin cậy; nó không cần private key server.

Trong production, nên tin cậy CA/intermediate CA phù hợp và sử dụng certificate chain hợp lệ. Không biến mọi certificate server tự ký thành trust anchor chỉ để làm mất lỗi PKIX.

## 9. HTTPS bằng HttpClient trong Java 17

Từ Java 11, JDK cung cấp `java.net.http.HttpClient`. Đây là API phù hợp cho HTTP/HTTPS trong ứng dụng hiện đại.

Ví dụ tệp **`TlsGet.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class TlsGet {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                "Usage: java TlsGet <https-url>"
            );
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())) {
            throw new IllegalArgumentException("URL must use HTTPS");
        }

        HttpClient client = HttpClient.newBuilder()
            .version(HttpClient.Version.HTTP_2)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
            .timeout(Duration.ofSeconds(20))
            .GET()
            .build();

        HttpResponse<Void> response = client.send(
            request,
            HttpResponse.BodyHandlers.discarding()
        );

        System.out.println("HTTP status: " + response.statusCode());
        System.out.println("HTTP version: " + response.version());
    }
}
```

Biên dịch bằng Java 17 API:

```bash
javac --release 17 TlsGet.java
```

Chạy với một HTTPS endpoint:

```bash
java TlsGet https://example.com
```

Kết quả phụ thuộc endpoint, mạng, redirect và HTTP version mà server thương lượng. Ví dụ có thể in:

```text
HTTP status: 200
HTTP version: HTTP_2
```

Đây là kết quả minh họa, không phải stdout cố định cho mọi server. Nếu server chỉ hỗ trợ HTTP/1.1, HttpClient có thể dùng HTTP/1.1 dù client ưu tiên HTTP/2.

HttpClient mặc định sử dụng SSLContext mặc định của JDK, xác minh certificate chain và hostname theo cơ chế HTTPS. Không cần tự tắt xác minh hostname hoặc tạo trust manager chấp nhận mọi certificate.

## 10. Cấu hình truststore riêng cho Java client

Nếu server dùng CA nội bộ, client có thể dùng truststore riêng thay vì sửa truststore mặc định.

Có thể cấu hình JSSE bằng system properties:

- `javax.net.ssl.trustStore`: đường dẫn truststore.
- `javax.net.ssl.trustStoreType`: định dạng, ví dụ PKCS12.
- `javax.net.ssl.trustStorePassword`: mật khẩu truststore.

Ví dụ đặt đường dẫn và loại keystore khi chạy:

```bash
java -Djavax.net.ssl.trustStore=client-truststore.p12 -Djavax.net.ssl.trustStoreType=PKCS12 TlsGet https://localhost:8443
```

Mật khẩu truststore cần được cung cấp qua cơ chế secret/configuration được quản lý an toàn nếu cần kiểm tra integrity của store. Tránh đưa mật khẩu thật trực tiếp vào command line vì có thể lộ qua process listing, shell history hoặc log. Không dùng mật khẩu mặc định `changeit` cho kho khóa ứng dụng.

Các system properties này cần được đặt trước khi SSLContext mặc định hoặc các thành phần TLS được khởi tạo. Nếu ứng dụng đã khởi tạo SSLContext, thay đổi property sau đó không đảm bảo cấu hình hiện tại được thay đổi.

## 11. Tạo SSLContext bằng truststore riêng

Khi muốn cấu hình TLS riêng cho một HttpClient thay vì thay đổi cấu hình toàn JVM, có thể tạo SSLContext trong mã nguồn.

Ví dụ tệp **`CustomTrustClient.java`**:

```java
import java.io.Console;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class CustomTrustClient {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "Usage: java CustomTrustClient <https-url> <truststore>"
            );
        }

        Console console = System.console();
        if (console == null) {
            throw new IllegalStateException(
                "Run from a terminal to enter the truststore password"
            );
        }

        char[] password = console.readPassword("Truststore password: ");
        try {
            KeyStore trustStore = KeyStore.getInstance("PKCS12");
            try (InputStream input = Files.newInputStream(Path.of(args[1]))) {
                trustStore.load(input, password);
            }

            TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
            );
            tmf.init(trustStore);

            SSLContext sslContext = SSLContext.getInstance("TLS");
            sslContext.init(null, tmf.getTrustManagers(), null);

            HttpClient client = HttpClient.newBuilder()
                .sslContext(sslContext)
                .build();

            HttpRequest request = HttpRequest.newBuilder(URI.create(args[0]))
                .GET()
                .build();

            HttpResponse<Void> response = client.send(
                request,
                HttpResponse.BodyHandlers.discarding()
            );

            System.out.println("HTTP status: " + response.statusCode());
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
```

Biên dịch:

```bash
javac --release 17 CustomTrustClient.java
```

Chạy:

```bash
java CustomTrustClient https://localhost:8443 client-truststore.p12
```

Ứng dụng hỏi mật khẩu qua console, nạp truststore, tạo TrustManagerFactory rồi khởi tạo SSLContext. HttpClient sử dụng SSLContext này cho kết nối HTTPS.

Ví dụ không cung cấp KeyManager vì client chỉ cần xác minh server. Nếu cần mutual TLS, cần bổ sung KeyManager từ client keystore.

## 12. Mutual TLS (mTLS)

Trong TLS thông thường, client xác thực server. Với **mutual TLS**, server cũng yêu cầu client cung cấp certificate để xác thực client ở tầng TLS.

mTLS thường được dùng trong:

- Giao tiếp giữa các microservice.
- API nội bộ yêu cầu certificate client.
- Kết nối database hoặc gateway có xác thực certificate.
- Thiết bị hoặc agent cần danh tính mật mã riêng.

Hai phía cần:

- Keystore chứa private key và certificate của chính endpoint.
- Truststore chứa CA/certificate được chấp nhận từ peer.
- Cấu hình server yêu cầu client authentication.
- Certificate có mục đích sử dụng và subject/SAN phù hợp với chính sách.

Trong Java, có thể tạo SSLContext với cả KeyManager và TrustManager:

```java
KeyStore clientKeys = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("client-identity.p12"))) {
    clientKeys.load(in, clientKeyPassword);
}

KeyManagerFactory kmf = KeyManagerFactory.getInstance(
    KeyManagerFactory.getDefaultAlgorithm()
);
kmf.init(clientKeys, clientKeyPassword);

KeyStore trustedServers = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("server-truststore.p12"))) {
    trustedServers.load(in, trustStorePassword);
}

TrustManagerFactory tmf = TrustManagerFactory.getInstance(
    TrustManagerFactory.getDefaultAlgorithm()
);
tmf.init(trustedServers);

SSLContext context = SSLContext.getInstance("TLS");
context.init(kmf.getKeyManagers(), tmf.getTrustManagers(), null);
```

Đây là đoạn cấu hình cần đặt trong method phù hợp với các biến password/keystore của ứng dụng; nó không phải một chương trình độc lập. Client dùng SSLContext này cho kết nối. Server cũng phải được cấu hình yêu cầu client certificate và tin cậy CA đã cấp certificate client.

mTLS xác thực danh tính certificate ở tầng kết nối. Ứng dụng vẫn cần ánh xạ certificate identity sang quyền truy cập nghiệp vụ.

## 13. Cấu hình protocol và SSLParameters

Có thể kiểm tra protocol mà SSLContext hỗ trợ:

```java
import java.util.Arrays;
import javax.net.ssl.SSLContext;

SSLContext context = SSLContext.getDefault();

System.out.println(
    "Supported: " + Arrays.toString(
        context.getSupportedSSLParameters().getProtocols()
    )
);

System.out.println(
    "Default enabled: " + Arrays.toString(
        context.getDefaultSSLParameters().getProtocols()
    )
);
```

Danh sách thực tế phụ thuộc JDK, provider và security configuration. Không nên hard-code cipher suite nếu không có yêu cầu tương thích hoặc chính sách cụ thể.

Với API socket cấp thấp, có thể cấu hình protocol và hostname verification bằng `SSLParameters`:

```java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

String host = "example.com";

try (SSLSocket socket = (SSLSocket)
        SSLSocketFactory.getDefault().createSocket(host, 443)) {

    SSLParameters parameters = socket.getSSLParameters();
    parameters.setProtocols(new String[] {"TLSv1.3", "TLSv1.2"});
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(parameters);

    socket.startHandshake();

    System.out.println("TLS protocol: " +
        socket.getSession().getProtocol());
    System.out.println("Cipher suite: " +
        socket.getSession().getCipherSuite());
}
```

Biên dịch đoạn mã này trong một class Java có import tương ứng. Hostname verification được bật trước khi handshake bằng endpoint identification algorithm `HTTPS`.

Đối với `SSLSocket` tự tạo, không nên giả định hostname đã được xác minh chỉ vì certificate chain hợp lệ. Luôn cấu hình endpoint identification hoặc dùng API HTTPS cấp cao tự xử lý xác minh hostname.

## 14. Hostname verification và certificate SAN

Certificate hợp lệ về mặt chữ ký chưa đủ để xác nhận server chính là hostname mà client yêu cầu.

Ví dụ client truy cập:

```text
https://api.example.com
```

Certificate server phải có SAN tương ứng với `api.example.com`. Nếu certificate chỉ có SAN `dns:other.example.com`, client cần từ chối kết nối dù certificate chain có thể được ký bởi CA tin cậy.

Các khái niệm:

- **Certificate chain validation:** kiểm tra certificate được ký bởi CA/trust anchor đáng tin cậy và thỏa điều kiện thời hạn/chính sách.
- **Hostname verification:** kiểm tra tên server trong URL khớp với SAN của certificate.
- **Certificate pinning:** ứng dụng ràng buộc kết nối với certificate hoặc public key cụ thể; đây là cơ chế bổ sung có yêu cầu vận hành và luân chuyển khóa riêng.

Không tắt hostname verification để xử lý lỗi hostname mismatch. Sửa certificate SAN hoặc hostname mà ứng dụng truy cập.

## 15. SNI và ALPN

Hai extension TLS quan trọng:

**SNI (Server Name Indication)** cho phép client gửi hostname trong ClientHello. Một máy chủ có thể lưu nhiều certificate cho nhiều hostname trên cùng địa chỉ IP; SNI giúp chọn certificate phù hợp.

**ALPN (Application-Layer Protocol Negotiation)** cho phép hai bên thương lượng giao thức tầng ứng dụng, ví dụ HTTP/2 hoặc HTTP/1.1.

Java HttpClient tự xử lý nhiều chi tiết TLS/SNI/ALPN khi sử dụng HTTPS URI. Với socket tự quản lý, ứng dụng có thể cần cấu hình các tham số tương ứng thông qua JSSE và SSLParameters.

Nếu kết nối đến server nhiều virtual host nhưng gửi sai hostname hoặc thiếu SNI, server có thể trả certificate không khớp hoặc chọn cấu hình TLS không mong muốn.

## 16. Chẩn đoán TLS handshake

Khi kết nối thất bại, bật JSSE debug để xem handshake, certificate và trust manager.

Ví dụ:

```bash
java -Djavax.net.debug=ssl,handshake,trustmanager TlsGet https://api.example.com
```

Một số nhóm log:

- `ssl`: hoạt động SSL/TLS tổng quát.
- `handshake`: thông điệp handshake.
- `trustmanager`: quá trình chọn và kiểm tra trust.
- `record`: thông tin TLS record; có thể tạo log rất lớn.

Để điều tra certificate path:

```bash
java -Djava.security.debug=certpath TlsGet https://api.example.com
```

Log TLS có thể chứa hostname, certificate metadata và thông tin môi trường. Chỉ bật trong thời gian chẩn đoán, bảo vệ log và tắt sau khi điều tra xong. Không ghi nội dung bí mật hoặc private key vào log.

## 17. Các system properties TLS thường gặp

| Property | Tác dụng |
| --- | --- |
| `javax.net.ssl.trustStore` | Đường dẫn truststore |
| `javax.net.ssl.trustStoreType` | Định dạng truststore |
| `javax.net.ssl.trustStorePassword` | Mật khẩu truststore |
| `javax.net.ssl.keyStore` | Đường dẫn keystore chứa identity/private key |
| `javax.net.ssl.keyStoreType` | Định dạng keystore |
| `javax.net.ssl.keyStorePassword` | Mật khẩu keystore |
| `jdk.tls.client.protocols` | Protocol mặc định được bật cho TLS client trong JSSE |
| `javax.net.debug` | Bật log chẩn đoán JSSE |

Ví dụ cấu hình protocol client ở mức JVM:

```bash
java -Djdk.tls.client.protocols=TLSv1.3,TLSv1.2 TlsGet https://api.example.com
```

Không đặt property mật khẩu bằng giá trị rõ trong script hoặc command line được ghi log. Với ứng dụng production, dùng secret manager, protected configuration hoặc cơ chế nạp khóa phù hợp.

Các security properties như `jdk.tls.disabledAlgorithms` và `jdk.certpath.disabledAlgorithms` trong file security của JDK quy định thuật toán/protocol bị vô hiệu hóa. Không chỉnh sửa chúng để bật lại thuật toán yếu nếu chưa đánh giá tác động bảo mật.

## 18. Lỗi TLS thường gặp

| Lỗi/thông báo | Nguyên nhân phổ biến | Cách xử lý |
| --- | --- | --- |
| `PKIX path building failed` | Không xây dựng được certificate chain tới trust anchor tin cậy | Kiểm tra CA/intermediate, truststore và chain server gửi |
| `unable to find valid certification path` | Client không tin certificate server hoặc thiếu CA | Import CA đã xác minh vào truststore phù hợp |
| `No subject alternative DNS name matching` | Hostname URL không khớp SAN | Cấp certificate có SAN đúng hoặc truy cập hostname đúng |
| `No name matching` | Hostname verification thất bại | Kiểm tra DNS name/IP và SAN |
| `protocol_version` | Client/server không có protocol chung hoặc protocol bị disable | Kiểm tra TLS version hai phía và policy JDK |
| `handshake_failure` | Không thống nhất được cipher, certificate, key exchange hoặc chính sách | Bật handshake debug và kiểm tra cấu hình hai phía |
| `certificate_expired` | Certificate hết hạn hoặc chưa có hiệu lực | Cấp lại certificate và kiểm tra đồng hồ hệ thống |
| `bad_certificate` | Certificate không hợp lệ, chain sai hoặc client certificate không được chấp nhận | Kiểm tra certificate, chain, key usage và truststore |
| `Received fatal alert: certificate_unknown` | Peer không tin certificate được gửi | Kiểm tra truststore của phía nhận và certificate chain |
| Không tìm thấy private key alias | Keystore thiếu PrivateKeyEntry hoặc alias sai | Dùng `keytool -list -v` kiểm tra keystore |
| Server yêu cầu client certificate | Server bật mTLS nhưng client không gửi certificate hợp lệ | Cấu hình client keystore và KeyManager |
| Kết nối bị timeout | DNS, firewall, proxy, routing hoặc server không phản hồi | Kiểm tra mạng và timeout trước khi kết luận lỗi TLS |

Không xử lý lỗi PKIX bằng trust manager chấp nhận tất cả certificate. Cách đó bỏ qua kiểm tra xác thực server và có thể mở đường cho man-in-the-middle.

## 19. Thực hành bảo mật khi dùng TLS trong JDK

- Ưu tiên TLS 1.3; giữ TLS 1.2 khi cần tương thích.
- Không bật SSLv3, TLS 1.0 hoặc TLS 1.1.
- Dùng certificate từ CA được tin cậy trong production.
- Đảm bảo certificate có SAN đúng hostname/IP.
- Giữ private key trong keystore được bảo vệ, HSM hoặc secret/key management service phù hợp.
- Dùng truststore riêng khi cần kiểm soát CA tin cậy của ứng dụng.
- Không dùng trust manager chấp nhận mọi certificate.
- Không tắt hostname verification.
- Không ghi mật khẩu keystore, token hoặc private key vào log.
- Luân chuyển certificate trước khi hết hạn và chuẩn bị quy trình thu hồi khi khóa bị lộ.
- Bật mTLS khi cần xác thực cả hai endpoint, đồng thời ánh xạ certificate identity sang authorization.
- Kiểm thử certificate chain, hostname, protocol và cipher suite trong môi trường gần production.
- Theo dõi thay đổi CA và security policy khi nâng cấp JDK.

TLS là một lớp bảo vệ trong kiến trúc tổng thể. Ứng dụng vẫn cần authentication, authorization, input validation, secure logging và quản lý bí mật đúng cách.

## 20. Quy trình triển khai TLS cho ứng dụng Java

Một quy trình thực tế có thể thực hiện theo thứ tự:

1. Xác định endpoint, hostname và yêu cầu TLS version.
2. Chọn CA/certificate và xác định có cần mutual TLS hay không.
3. Tạo key pair và CSR trong keystore; bảo vệ private key.
4. Cấp certificate có SAN và key usage phù hợp.
5. Cấu hình keystore trên server và truststore trên client.
6. Cấu hình SSLContext hoặc dùng mặc định của JSSE khi phù hợp.
7. Dùng HttpClient hoặc API JSSE thích hợp cho giao thức.
8. Kiểm tra certificate chain và hostname verification.
9. Xác nhận TLS protocol/cipher suite được thương lượng.
10. Bật log JSSE tạm thời nếu handshake lỗi.
11. Kiểm thử certificate expiry, rotation, revocation và môi trường mạng.
12. Tắt debug, bảo vệ secret và triển khai theo quy trình release.

## 21. Ghi nhớ

- TLS bảo vệ tính bí mật, toàn vẹn và xác thực peer khi truyền dữ liệu.
- JSSE là bộ API TLS chính trong JDK; `SSLContext` là điểm cấu hình quan trọng.
- TLS 1.3 và TLS 1.2 là các phiên bản nên dùng theo chính sách tương thích; tránh protocol cũ.
- Keystore lưu private key/certificate của endpoint; truststore lưu CA/certificate được tin cậy.
- Java HttpClient từ Java 11 sử dụng JSSE và xác minh certificate/hostname theo mặc định.
- Certificate cần SAN khớp hostname; chain hợp lệ không thay thế hostname verification.
- mTLS yêu cầu cả hai phía có identity certificate và trust cấu hình đúng.
- `keytool` tạo key pair, export certificate và quản lý truststore.
- `javax.net.debug=ssl,handshake,trustmanager` hỗ trợ chẩn đoán handshake.
- Không dùng trust-all manager, không tắt hostname verification và không để lộ private key/mật khẩu.

Hiểu TLS và JSSE giúp bạn xây dựng kết nối Java an toàn, cấu hình đúng certificate và truststore, xử lý handshake có căn cứ và vận hành bảo mật ổn định khi ứng dụng giao tiếp qua mạng.
