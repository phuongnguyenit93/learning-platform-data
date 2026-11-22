# Kết nối HTTPS với cấu hình chứng chỉ kiểm chứng được (Java 11+)

## Mục tiêu thực hành

Sau bài này, bạn có thể: (1) kết nối đến dịch vụ HTTPS bằng `java.net.http.HttpClient` của Java 11; (2) phân biệt chứng chỉ máy chủ, chuỗi chứng chỉ, CA tin cậy, `truststore` và `keystore`; (3) cấu hình một `PKCS12 truststore` riêng cho dịch vụ dùng CA nội bộ; (4) chứng minh kết nối thành công khi chứng chỉ được tin cậy **và** tên máy khớp, đồng thời bị từ chối khi thiếu một trong hai điều kiện; (5) xử lý lỗi TLS mà không vô hiệu hóa xác thực.

Bài sử dụng các API đang được hỗ trợ trong Java 11 trở lên: `java.net.http`, JSSE (`SSLContext`, `TrustManagerFactory`, `SSLParameters`) và công cụ `keytool`. Khi chạy Java 11 trong thực tế, sử dụng bản phân phối được cập nhật bản vá bảo mật; ví dụ cũng chạy trên các JDK LTS mới hơn.

## 1. HTTPS xác minh điều gì?

HTTPS là HTTP qua TLS. Khi client truy cập `https://api.example.com`, chỉ thấy biểu tượng khóa hay kết nối được mã hóa là chưa đủ. Để xác thực đúng máy chủ, client cần kiểm tra:

1. **Chuỗi tin cậy (certificate path):** chứng chỉ máy chủ (leaf) được ký bởi CA trung gian hoặc CA gốc dẫn tới một **trust anchor** mà client tin cậy. Java thường xây dựng và kiểm tra chuỗi theo PKIX, bao gồm chữ ký, thời hạn, ràng buộc CA/thuật toán và các quy tắc liên quan.
2. **Định danh máy chủ (hostname verification):** tên host trong URL phải phù hợp với `subjectAltName` (SAN) của chứng chỉ. Với tên DNS, cần DNS SAN tương ứng; với IP, cần IP SAN tương ứng. Chỉ đặt `CN=localhost` không thay thế việc khai báo SAN.
3. **Bắt tay và thông số TLS:** client và server thương lượng bộ mã hóa và phiên bản TLS có thể dùng được. Trong môi trường hiện đại, ưu tiên TLS 1.3 và chấp nhận TLS 1.2 khi cần tương thích.
4. **Chính sách bổ sung theo yêu cầu hệ thống:** vòng đời CA/chứng chỉ, thu hồi chứng chỉ (OCSP/CRL), nhật ký, kiểm soát proxy và đồng hồ hệ thống. Đừng mặc định rằng mọi chính sách kiểm tra thu hồi đều đã được bật.

**Truststore** chứa các chứng chỉ gốc/CA (hoặc chứng chỉ được tin cậy trực tiếp) mà client chấp nhận. **Keystore máy chủ** chứa khóa riêng của máy chủ cùng chuỗi chứng chỉ để server chứng minh danh tính. Chúng có vai trò khác nhau. Chứng chỉ công khai không phải bí mật, nhưng một CA chỉ được thêm vào truststore sau khi đối chiếu nguồn và dấu vân tay SHA-256 qua kênh tin cậy.

Java có kho CA mặc định của JDK (thường là `$JAVA_HOME/lib/security/cacerts`). Với website dùng CA công cộng đã được JDK tin cậy, dùng `HttpClient` mặc định là đủ. Với CA riêng của tổ chức, tạo truststore riêng và gắn vào client cụ thể để kiểm soát phạm vi tin cậy.

## 2. Chuẩn bị

- JDK 11 hoặc mới hơn với `java`, `javac`, `keytool` khả dụng trong terminal; có thể kiểm tra bằng `java -version` và `javac -version`.
- Một thư mục thực hành chứa các tệp `VerifiedHttpsClient.java` và, cho bài kiểm thử cục bộ, `LocalHttpsServer.java`.
- Với hệ thống nội bộ thật: URL HTTPS chính xác, chứng chỉ CA được cấp bởi quản trị PKI, và dấu vân tay CA đã kiểm chứng **độc lập**. Không tải rồi tin ngay một chứng chỉ lấy từ kết nối đang báo lỗi.

Không cần thư viện HTTP bên thứ ba. Các lệnh `keytool` phía dưới sẽ hỏi mật khẩu tương tác, vì vậy không đặt mật khẩu sản xuất trực tiếp trong dòng lệnh hoặc mã nguồn.

## 3. Viết HTTPS client xác thực chứng chỉ

Tạo tệp **`VerifiedHttpsClient.java`**:

~~~java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;
import java.util.Arrays;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.TrustManagerFactory;

public final class VerifiedHttpsClient {
    public static void main(String[] args) throws Exception {
        if (args.length < 1 || args.length > 2) {
            System.err.println(
                "Usage: java VerifiedHttpsClient <https-url> [truststore.p12]");
            System.exit(2);
        }

        URI uri = URI.create(args[0]);
        if (!"https".equalsIgnoreCase(uri.getScheme())
                || uri.getHost() == null
                || uri.getUserInfo() != null) {
            throw new IllegalArgumentException("A valid HTTPS URL is required");
        }

        // Khong co duong dan truststore: su dung CA mac dinh cua JDK.
        // Co duong dan: chi tin cay cac anchor trong truststore do.
        SSLContext context = args.length == 2
                ? contextFromTruststore(Path.of(args[1]))
                : SSLContext.getDefault();

        SSLParameters tls = context.getDefaultSSLParameters();
        tls.setEndpointIdentificationAlgorithm("HTTPS");
        tls.setProtocols(new String[] { "TLSv1.3", "TLSv1.2" });

        HttpClient client = HttpClient.newBuilder()
                .sslContext(context)
                .sslParameters(tls)
                .connectTimeout(Duration.ofSeconds(10))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(20))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));

        System.out.println("HTTP status: " + response.statusCode());
        System.out.println("Body: " + response.body().strip());
    }

    private static SSLContext contextFromTruststore(Path path)
            throws Exception {
        String rawPassword = System.getenv("TLS_TRUSTSTORE_PASSWORD");
        if (rawPassword == null || rawPassword.isEmpty()) {
            throw new IllegalStateException(
                "Set TLS_TRUSTSTORE_PASSWORD for the custom truststore");
        }

        char[] password = rawPassword.toCharArray();
        try {
            KeyStore truststore = KeyStore.getInstance("PKCS12");
            try (InputStream in = Files.newInputStream(path)) {
                truststore.load(in, password);
            }

            TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm());
            tmf.init(truststore);

            SSLContext context = SSLContext.getInstance("TLS");
            context.init(null, tmf.getTrustManagers(), null);
            return context;
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Biên dịch và thử với một website HTTPS công cộng có chứng chỉ hợp lệ:

~~~bash
javac VerifiedHttpsClient.java
java VerifiedHttpsClient https://example.com/
~~~

Nếu bắt tay TLS và request HTTP thành công, chương trình in `HTTP status: <mã HTTP>` và nội dung phản hồi. Mã HTTP do máy chủ trả về có thể thay đổi, nên **không** coi một mã nhất định là bằng chứng duy nhất của bảo mật; bằng chứng quan trọng ở bước này là Java đã hoàn thành bắt tay TLS, xác thực chuỗi chứng chỉ và hostname thay vì ném lỗi TLS.

**Giải thích các thành phần chính:**

- `SSLContext.getDefault()` sử dụng cấu hình tin cậy mặc định. `TrustManagerFactory` khởi tạo từ PKCS12 tạo bộ xác minh chứng chỉ cho **đúng truststore được truyền vào**; `context.init(null, tmf.getTrustManagers(), null)` không cấu hình chứng chỉ client, vì bài này chỉ xác thực server.
- `setEndpointIdentificationAlgorithm("HTTPS")` nêu rõ chính sách xác thực endpoint. `HttpClient` của JDK vốn thực hiện xác thực hostname cho HTTPS; tuyệt đối không bật cơ chế hệ thống dùng để vô hiệu hóa nó.
- `setProtocols` giới hạn bắt tay vào TLS 1.3/1.2 được JDK hỗ trợ. Để mặc các cấu hình thuật toán an toàn và danh sách cipher suite của JDK đã cập nhật, không ép bộ mã hóa yếu.
- `connectTimeout` giới hạn thời gian thiết lập kết nối; `HttpRequest.timeout` giới hạn thời gian xử lý request. `Redirect.NEVER` giúp ví dụ không âm thầm chuyển sang host khác.
- Client dùng truststore riêng **không tự động cộng thêm** các CA của `cacerts`. Vì vậy, nếu `client-trust.p12` chỉ chứa CA nội bộ, dùng nó để gọi website CA công cộng có thể thất bại. Có thể dùng hai `HttpClient` khác nhau theo đích đến, hoặc xây dựng truststore hợp nhất đã được rà soát khi thật sự cần.

## 4. Kiểm thử cục bộ: có tin cậy mới được kết nối

Phần này chạy HTTPS server nhỏ bằng module chuẩn `jdk.httpserver` để tạo ba tình huống có thể lặp lại: **không tin cậy**, **tin cậy đúng host**, **tin cậy nhưng sai host**. Chứng chỉ tự ký chỉ dùng trong **lab**; môi trường sản xuất nên dùng CA nội bộ/quy trình PKI được quản trị.

### Bước 4.1 — Tạo chứng chỉ thử nghiệm có SAN

Chạy trong thư mục thực hành:

~~~bash
keytool -genkeypair -alias lab-server -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=localhost,O=TLS-Lab" -ext "SAN=dns:localhost" -validity 30 -keystore server.p12 -storetype PKCS12
keytool -exportcert -rfc -alias lab-server -file lab-server.pem -keystore server.p12 -storetype PKCS12
keytool -printcert -v -file lab-server.pem
~~~

`server.p12` chứa **khóa riêng** của server và chứng chỉ tự ký; hãy bảo vệ tệp này. `lab-server.pem` chỉ chứa chứng chỉ công khai. Lệnh cuối cho phép kiểm tra `SubjectAlternativeName` có `DNSName: localhost`, thời hạn và dấu vân tay SHA-256. Ghi nhớ mật khẩu `server.p12` đã nhập ở bước đầu.

### Bước 4.2 — Viết HTTPS server chạy trên máy cục bộ

Tạo tệp **`LocalHttpsServer.java`**:

~~~java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.util.Arrays;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;

public final class LocalHttpsServer {
    public static void main(String[] args) throws Exception {
        String rawPassword = System.getenv("TLS_SERVER_KEYSTORE_PASSWORD");
        if (rawPassword == null || rawPassword.isEmpty()) {
            throw new IllegalStateException(
                "Set TLS_SERVER_KEYSTORE_PASSWORD");
        }

        char[] password = rawPassword.toCharArray();
        SSLContext context;
        try {
            KeyStore keys = KeyStore.getInstance("PKCS12");
            try (InputStream in = Files.newInputStream(Path.of("server.p12"))) {
                keys.load(in, password);
            }

            KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm());
            kmf.init(keys, password);

            context = SSLContext.getInstance("TLS");
            context.init(kmf.getKeyManagers(), null, null);
        } finally {
            Arrays.fill(password, '\0');
        }

        HttpsServer server = HttpsServer.create(
                new InetSocketAddress("127.0.0.1", 8443), 0);
        server.setHttpsConfigurator(new HttpsConfigurator(context));
        server.createContext("/", exchange -> {
            byte[] body = "TLS OK\n".getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders().set(
                    "Content-Type", "text/plain; charset=UTF-8");
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });
        server.start();
        System.out.println("Local HTTPS server started on port 8443");
    }
}
~~~

Biên dịch trong một terminal:

~~~bash
javac --add-modules jdk.httpserver LocalHttpsServer.java
~~~

Đặt biến môi trường `TLS_SERVER_KEYSTORE_PASSWORD` bằng mật khẩu của `server.p12`, sau đó chạy ở **terminal A**:

~~~bash
java --add-modules jdk.httpserver LocalHttpsServer
~~~

Trên PowerShell, với **mật khẩu lab** có thể nhập biến môi trường tương tác bằng `$env:TLS_SERVER_KEYSTORE_PASSWORD = Read-Host 'Server keystore password'` trước khi chạy server. Trong ứng dụng thực tế, đưa mật khẩu qua cơ chế quản lý bí mật của môi trường triển khai; tránh ghi mật khẩu vào lệnh có thể lưu lịch sử. Server chỉ lắng nghe địa chỉ loopback IPv4 `127.0.0.1`, cổng `8443`. Dừng bằng `Ctrl+C` sau khi thực hành.

### Bước 4.3 — Tạo truststore cho client

Đối chiếu SHA-256 fingerprint của `lab-server.pem` đã tạo trên máy của mình. Chỉ sau đó nhập nó vào truststore dùng riêng cho lab:

~~~bash
keytool -importcert -alias lab-server -file lab-server.pem -keystore client-trust.p12 -storetype PKCS12
keytool -list -v -keystore client-trust.p12 -storetype PKCS12
~~~

Xác nhận tin cậy khi `keytool` hỏi và đặt mật khẩu mới cho `client-trust.p12`. Trong kết quả `-list -v`, mục `lab-server` là `trustedCertEntry`; đây là **chứng chỉ được tin cậy**, không phải khóa riêng. Trên **terminal B**, đặt biến môi trường `TLS_TRUSTSTORE_PASSWORD` bằng mật khẩu của `client-trust.p12` (PowerShell: `$env:TLS_TRUSTSTORE_PASSWORD = Read-Host 'Client truststore password'`).

### Bước 4.4 — Chạy các ca kiểm thử

Biên dịch client trước nếu chưa biên dịch: `javac VerifiedHttpsClient.java`. Server ở terminal A phải đang chạy. Để tên `localhost` chắc chắn đi đến loopback IPv4 của ví dụ, các lệnh thử sau dùng tùy chọn JVM `-Djava.net.preferIPv4Stack=true`.

**Ca A — Không tin cậy chứng chỉ tự ký (phải thất bại):**

~~~bash
java -Djava.net.preferIPv4Stack=true VerifiedHttpsClient https://localhost:8443/
~~~

Client dùng CA mặc định, không có chứng chỉ lab. Kỳ vọng: `SSLHandshakeException` (thường kèm `PKIX path building failed`). Đây là kết quả **đúng**, không phải lỗi cần “bỏ xác minh” để sửa.

**Ca B — Truststore đúng, hostname đúng (phải thành công):**

~~~bash
java -Djava.net.preferIPv4Stack=true VerifiedHttpsClient https://localhost:8443/ client-trust.p12
~~~

Kết quả mong đợi khi server chạy đúng mã ở trên:

~~~text
HTTP status: 200
Body: TLS OK
~~~

**Ca C — Truststore đúng, hostname sai (phải thất bại):**

~~~bash
java -Djava.net.preferIPv4Stack=true VerifiedHttpsClient https://127.0.0.1:8443/ client-trust.p12
~~~

Mặc dù địa chỉ IP trỏ tới cùng server và client tin cậy chứng chỉ của nó, chứng chỉ chỉ có `DNSName: localhost`, không có `IPAddress: 127.0.0.1`. Kỳ vọng: lỗi xác thực hostname/SAN, thường được bọc trong `SSLHandshakeException`. Nếu môi trường có proxy hoặc chính sách mạng bất thường, cần kiểm tra kết nối đã tới đúng server local trước khi kết luận từ thông báo lỗi.

| Ca | Chuỗi/chứng chỉ tin cậy? | Host trong URL khớp SAN? | Kết quả mong đợi |
| --- | --- | --- | --- |
| A | Không | Có | TLS từ chối |
| B | Có | Có | HTTP 200, `TLS OK` |
| C | Có | Không | TLS từ chối |

**Điểm rút ra:** nhập một chứng chỉ vào truststore **không** có nghĩa cho phép dùng chứng chỉ đó cho mọi tên miền. Xác minh chuỗi tin cậy và xác minh hostname phải cùng đạt yêu cầu.

## 5. Áp dụng vào API nội bộ có CA thực

Trong production, không khuyến khích nhập mỗi chứng chỉ leaf tự ký như lab. Dùng chứng chỉ **CA gốc/trung gian được tổ chức phê duyệt** làm trust anchor phù hợp, có quản trị phát hành, thu hồi và luân chuyển. Quy trình:

1. Nhận `company-root-ca.pem` từ kênh phân phối PKI tin cậy, đối chiếu SHA-256 fingerprint từ kênh độc lập. Xem nội dung bằng `keytool -printcert -v -file company-root-ca.pem`; kiểm tra CA, thời hạn và nguồn phát hành.
2. Nhập CA đã xác minh vào truststore riêng, ví dụ:

~~~bash
keytool -importcert -alias company-root -file company-root-ca.pem -keystore company-trust.p12 -storetype PKCS12
keytool -list -v -keystore company-trust.p12 -storetype PKCS12
~~~

3. Đặt `TLS_TRUSTSTORE_PASSWORD` qua cơ chế bí mật của môi trường, giữ `company-trust.p12` trong nơi chỉ tài khoản ứng dụng được đọc. Gọi:

~~~bash
java VerifiedHttpsClient https://api.internal.example/ company-trust.p12
~~~

4. Xác nhận chứng chỉ server có SAN cho **đúng** `api.internal.example`, chuỗi trung gian đầy đủ, thời gian hợp lệ và thuật toán được JDK cho phép. Địa chỉ URL phải là DNS name đã cấp chứng chỉ; không đổi sang IP nếu chứng chỉ không có IP SAN tương ứng.

Nếu service dùng mTLS, ngoài cấu hình `TrustManagerFactory` để **tin cậy server**, client còn cần `KeyManagerFactory` và chứng chỉ/khóa riêng **của client** do hệ thống cấp. Đây là yêu cầu bổ sung, không phải lý do bỏ kiểm tra server.

## 6. Chẩn đoán lỗi theo nguyên nhân

| Triệu chứng | Khả năng thường gặp | Kiểm tra/cách xử lý |
| --- | --- | --- |
| `PKIX path building failed` / `unable to find valid certification path` | Thiếu CA đáng tin cậy, thiếu intermediate, dùng nhầm truststore hoặc proxy HTTPS đổi chứng chỉ | Kiểm tra chuỗi chứng chỉ phía server và CA được phép tin; thêm **đúng CA đã xác minh** vào truststore, không chấp nhận bừa chứng chỉ đang lỗi |
| `No subject alternative DNS name matching...` / `No subject alternative names matching IP address...` | URL không khớp SAN | Dùng DNS/IP được ghi trong SAN hoặc cấp lại chứng chỉ có SAN đúng; không tắt hostname verification |
| `CertificateExpiredException` / `CertificateNotYetValidException` | Chứng chỉ hết hạn/chưa hiệu lực hoặc sai đồng hồ | Kiểm tra giờ hệ thống, `Not Before`/`Not After` và cấp chứng chỉ mới |
| `IOException` khi tải PKCS12 / sai mật khẩu | Sai đường dẫn, mật khẩu, định dạng hoặc quyền đọc | Kiểm tra `-storetype PKCS12`, `keytool -list`, đường dẫn và cách cấp secret |
| `SSLHandshakeException`: protocol/cipher mismatch | Một phía chỉ cho TLS/thuật toán cũ hoặc cấu hình quá hạn chế | Kiểm tra TLS 1.2/1.3 và chính sách bảo mật hai đầu; sửa server/JDK, không bật lại giao thức yếu |
| `ConnectException` / timeout | DNS, server chưa chạy, proxy, firewall, sai cổng | Kiểm tra TCP và cấu hình mạng trước; đây chưa phải kết luận về chứng chỉ |

Khi debug tại môi trường thử nghiệm, có thể bật thông tin bắt tay và đường dẫn chứng chỉ:

~~~bash
java -Djavax.net.debug=ssl,handshake -Djava.security.debug=certpath VerifiedHttpsClient https://api.internal.example/ company-trust.p12
~~~

Log có thể rất dài và chứa metadata về phiên TLS/certificate; chỉ thu thập, chia sẻ theo chính sách bảo mật của hệ thống. Không kết luận “HTTPS an toàn” chỉ vì nhận được mã HTTP thành công qua client đã bị cấu hình bỏ xác minh.

## 7. Lưu ý bảo mật và vận hành

- **Không** viết `X509TrustManager` “trust all”, `HostnameVerifier` luôn trả `true`, hoặc bật `jdk.internal.httpclient.disableHostnameVerification`. Các cách này khiến kết nối dễ bị tấn công trung gian dù dữ liệu vẫn được mã hóa.
- Không sửa `cacerts` dùng chung toàn máy chỉ để chữa lỗi một dịch vụ; ưu tiên `SSLContext`/truststore riêng cho ứng dụng và kiểm soát thay đổi CA. Không nhét khóa riêng server vào truststore của client.
- Không coi việc tải chứng chỉ đang được máy chủ trả về rồi nhập ngay làm xác minh danh tính. Kẻ tấn công có thể thay thế chứng chỉ trên chính đường truyền đó; phải xác thực fingerprint/CA ngoài băng.
- Lập lịch theo dõi hạn chứng chỉ, thay CA/chứng chỉ trước khi hết hạn, kiểm thử sau luân chuyển. Chỉ tin cậy trực tiếp leaf (như lab) có thể làm client ngừng hoạt động khi leaf được cấp lại; PKI có CA quản trị giúp xoay vòng an toàn hơn.
- Đảm bảo JVM được vá và đồng hồ hệ thống đúng. Hạn chế TLS vào 1.2/1.3 theo yêu cầu môi trường; không bỏ thuật toán bị chặn bởi `jdk.tls.disabledAlgorithms` để kết nối hệ thống cũ.
- Nếu chính sách yêu cầu kiểm tra thu hồi chứng chỉ, thiết kế và xác minh OCSP/CRL/PKIX revocation một cách riêng biệt. Đừng giả định chỉ dùng `TrustManagerFactory` là đã thỏa mọi chính sách revocation.
- Nếu cần tự động chuyển hướng URL, xét từng host/đích tin cậy và không tự động gửi token sang địa chỉ ngoài dự kiến. Ví dụ đặt `Redirect.NEVER` để việc thử nghiệm minh bạch.
- Không in nội dung phản hồi, bí mật hoặc TLS debug log nhạy cảm trong log production chỉ vì ví dụ minh họa có `System.out.println`. Áp dụng ghi log có kiểm soát.

## 8. Tự đánh giá sau thực hành

1. Giải thích vì sao ca A thất bại mặc dù server đã mã hóa HTTPS.
2. Chỉ ra phần nào của mã quyết định CA nào được tin cậy, và phần nào yêu cầu xác minh hostname.
3. Dự đoán điều gì xảy ra nếu gọi `https://example.com/` bằng `client-trust.p12` chỉ có chứng chỉ lab.
4. Giải thích vì sao lỗi SAN không thể sửa bằng cách chỉ thêm CA vào truststore.
5. Trình bày cách lấy và xác minh fingerprint CA của tổ chức trước khi nhập; liệt kê bước kiểm tra khi chứng chỉ hết hạn hoặc server thiếu intermediate.

## Tài liệu tham khảo chính thức

- [Java SE 11 — `HttpClient.Builder`](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): `sslContext`, `sslParameters`, timeout, redirect.
- [Java SE 11 — `SSLParameters`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLParameters.html): cấu hình endpoint identification và TLS protocols.
- [Java SE 11 — `keytool`](https://docs.oracle.com/en/java/javase/11/tools/keytool.html): tạo, xuất, kiểm tra, nhập chứng chỉ và truststore.
- [OpenJDK — Trust Management in the JDK Libraries](https://ops.java/security/trust/): trust anchor, `cacerts`, PKCS12.
- [OpenJDK — Default TLS Versions](https://ops.java/security/articles/default-tls-versions/): TLS 1.2/1.3 trong JDK hiện đại.