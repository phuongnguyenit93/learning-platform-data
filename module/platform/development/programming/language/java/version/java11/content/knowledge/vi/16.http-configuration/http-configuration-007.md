# Giữ kiểm tra danh tính máy chủ trong HTTPS (Java 11+)

**Chủ đề cha: Cấu hình HTTP.** Khi gọi `https://api.example.com` từ Java, không đủ để kết nối được mã hóa. Ứng dụng còn phải bảo đảm rằng bên nhận **thực sự là máy chủ mà URL định danh**, thay vì một máy chủ khác có chứng chỉ không phù hợp. Bảo vệ này gọi là **hostname verification** hay **HTTPS endpoint identification**.

Với `java.net.http.HttpClient` chuẩn từ Java 11, hãy **giữ nguyên cơ chế xác minh mặc định**, sử dụng chứng chỉ TLS hợp lệ có tên/IP phù hợp và truststore được quản lý đúng cách. Không tắt kiểm tra tên máy chủ hoặc dùng trust manager chấp nhận mọi chứng chỉ để né lỗi kết nối. Kiến thức và các API trong bài vẫn còn áp dụng ở Java hiện đại; những ví dụ bên dưới ưu tiên chạy bằng JDK 11 trở lên.

## 1. HTTPS an toàn cần hai câu trả lời, không chỉ một

Khi gọi tới:

```text
https://api.example.com/v1/orders
        ^^^^^^^^^^^^^^^
        tên máy chủ (hostname) trong URI
```

TLS phải giải quyết ít nhất hai câu hỏi liên quan nhưng **khác nhau**:

1. **Chuỗi chứng chỉ được tin cậy không?** Chứng chỉ do máy chủ cung cấp có tạo được đường xác thực hợp lệ đến trust anchor mà phía client tin, còn hiệu lực, và đáp ứng các kiểm tra thuật toán/chính sách áp dụng không? Việc này thường do `TrustManagerFactory` / X.509 trust manager và JSSE thực hiện.
2. **Chứng chỉ đó có nhận diện đúng máy chủ được yêu cầu không?** Tên trong URI phải khớp thông tin danh tính của chứng chỉ máy chủ theo quy tắc HTTPS, chủ yếu là các mục `Subject Alternative Name` (SAN). Việc này gọi là **endpoint identification**.

Một chứng chỉ có thể được ký bởi CA đáng tin cậy nhưng **được cấp cho máy chủ khác**. Vì vậy, chỉ kiểm tra trust chain mà bỏ kiểm tra hostname vẫn không đủ bảo vệ khỏi việc bị đưa sang đích sai hoặc tấn công giả mạo máy chủ.

Ngược lại, một chứng chỉ tự ký có SAN đúng tên vẫn **không được mặc nhiên tin cậy** nếu public key hoặc CA của nó chưa nằm trong truststore hợp lệ. Cần cả hai điều kiện.

| Tình huống | Chuỗi cert được trust? | Danh tính URL khớp? | Kết quả mong muốn |
| --- | :---: | :---: | --- |
| Cert hợp lệ của `api.example.com` | Có | Có | TLS có thể tiếp tục, nếu các kiểm tra TLS khác cũng đạt |
| Cert hợp lệ nhưng dành cho `other.example.com` | Có | Không | **Từ chối** |
| Cert tự ký chưa được tin cậy, dù SAN đúng | Không | Có | **Từ chối** |
| Cert không được tin cậy và SAN cũng sai | Không | Không | **Từ chối** |
| Cert hết hạn, thuật toán không được chấp nhận | Có thể | Có thể | **Từ chối** theo các kiểm tra chứng chỉ còn lại |

Bảng này giải thích logic bảo vệ; nó không dự đoán chính xác **loại exception nào xuất hiện đầu tiên** nếu một kết nối vi phạm nhiều điều kiện cùng lúc.

## 2. Java 11 HttpClient: dùng mặc định an toàn

`java.net.http.HttpClient` xuất hiện chính thức ở Java 11 và có thể tự thực hiện HTTPS qua JSSE. Mẫu cấu hình thông thường:

```java
HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

Đây là đoạn minh họa, cần import `java.net.http.HttpClient` và `java.time.Duration`. Khi không cấu hình `sslContext(...)`, builder sử dụng **SSLContext mặc định** của môi trường; đây thường là lựa chọn phù hợp với ứng dụng kết nối tới server có chứng chỉ được CA thông thường tin cậy.

**Điểm mấu chốt:** Java HttpClient chuẩn **thực hiện kiểm tra HTTPS endpoint identity trong quá trình bắt tay TLS** ở cấu hình thông thường. Không cần tự cài một callback để trả `true`. Trên JDK, việc xác minh này là cơ chế cần **giữ bật**, không phải một bước tùy chọn nên tắt khi gặp lỗi.

Phân biệt những khái niệm dễ nhầm:

- `HttpClient.Builder.sslContext(...)` dùng để cung cấp chính sách tin cậy và khóa TLS cụ thể của một client. Nó **không có nghĩa tắt hostname verification**.
- `HttpClient.Builder.sslParameters(...)` cho phép cấu hình một số tham số TLS. Javadoc cảnh báo một số tham số HTTP client tự dùng có thể bị bỏ qua. Không dùng nó để tìm cách tắt kiểm tra danh tính.
- `HttpsURLConnection.setHostnameVerifier(...)` thuộc **API `HttpsURLConnection`**, không phải phương thức của `HttpClient.Builder` trong Java 11. Đừng chuyển ví dụ cấu hình verifier của API cũ sang HttpClient mới rồi tưởng hai đối tượng dùng chung một chính sách.
- `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` là API JSSE cấp thấp hữu ích khi bạn **tự quản lý `SSLSocket`/`SSLEngine`**; HttpClient đã đảm nhiệm lớp HTTPS này ở cấu hình mặc định.

## 3. URL và Subject Alternative Name (SAN) phải tương ứng

Trong chứng chỉ X.509, extension `Subject Alternative Name` chứa các danh tính mà máy chủ được phép đại diện. Với ứng dụng HTTPS hiện đại, nên đặt danh tính ở SAN thay vì chỉ dựa vào trường `Common Name (CN)` của Subject.

### Khi URI dùng tên DNS

Ví dụ:

```text
https://api.example.com/data
```

Certificate phải có danh tính DNS phù hợp, ví dụ:

```text
X509v3 Subject Alternative Name:
    DNS:api.example.com
```

Nếu cert chỉ có `DNS:files.example.com`, việc cùng thuộc công ty hoặc cùng trỏ về một IP **không** làm nó hợp lệ cho `api.example.com`.

### Khi URI dùng địa chỉ IP trực tiếp

Ví dụ:

```text
https://192.0.2.10/api
```

Cert nên chứa **IP address SAN** đúng IP đó, ví dụ:

```text
X509v3 Subject Alternative Name:
    IP Address:192.0.2.10
```

Một mục `DNS:api.example.com` không tự cho phép truy cập `https://192.0.2.10`. Dù DNS tra tên `api.example.com` ra đúng địa chỉ `192.0.2.10`, danh tính mà client cần xác minh vẫn là **host được sử dụng trong URI**.

Do đó:

| URL được gọi | SAN trong cert | Diễn giải |
| --- | --- | --- |
| `https://api.example.com` | `DNS:api.example.com` | Phù hợp |
| `https://api.example.com` | `DNS:other.example.com` | Không phù hợp |
| `https://127.0.0.1` | `IP:127.0.0.1` | Phù hợp trong môi trường test |
| `https://127.0.0.1` | `DNS:localhost` mà không có IP SAN | Không đủ để xác minh IP literal |
| `https://localhost` | `DNS:localhost` | Phù hợp trong môi trường test |

Một chứng chỉ có thể chứa **nhiều SAN** nếu dịch vụ thật sự cần được gọi bằng nhiều tên. Nên dùng tên DNS ổn định và chứng chỉ phù hợp, thay vì thay hostname trong URL thành IP để né việc cấu hình DNS.

**Về wildcard:** Chứng chỉ wildcard có quy tắc khớp tên riêng, không có nghĩa `*.example.com` hợp lệ với mọi độ sâu như `a.b.example.com` hay tên gốc `example.com`. Không tự viết phép khớp `contains`, `endsWith` hoặc regex đơn giản thay cho bộ kiểm tra danh tính của JSSE.

## 4. Vì sao tắt hostname verification là một lỗi bảo mật?

Giả sử client muốn truy cập `payments.example.com`, nhưng bị đưa đến một endpoint khác thông qua DNS, proxy hay lỗi cấu hình. Nếu phía client chỉ tin chứng chỉ do một CA được phép cấp mà **không so tên host**, endpoint khác có thể vượt qua phần kiểm tra chuỗi chứng chỉ dù không phải `payments.example.com`.

Bảo vệ còn quan trọng khi kết nối được mã hóa: một kết nối TLS mã hóa dữ liệu đến **sai người nhận** vẫn không đạt mục tiêu xác thực máy chủ.

**Không dùng các giải pháp vượt bảo vệ sau:**

- Trust manager tùy chỉnh kiểu “trust all”, bỏ qua mọi lỗi `checkServerTrusted`.
- Hostname verifier luôn trả `true` ở một thư viện khác.
- Thuộc tính nội bộ của JDK nhằm **vô hiệu hóa hostname verification**; tài liệu Oracle nói rõ cơ chế này phục vụ test, không phải cấu hình bảo mật production. Đừng dựa vào thuộc tính nội bộ để sửa lỗi kết nối.
- Tạm sửa mã rồi quên bật lại khi lên production.
- Bỏ kiểm tra chứng chỉ chỉ vì đang ở staging, môi trường container hoặc sau một reverse proxy.

Thay vì thế, tìm **nguyên nhân gốc**: URL có đúng không? Cert có SAN phù hợp không? Truststore có đúng CA không? Proxy hoặc load balancer đang trình bày chứng chỉ nào? Thời gian hệ thống, DNS, SNI và certificate chain có đúng không?

## 5. Ví dụ cơ bản: gọi HTTPS bằng HttpClient an toàn

Tệp **`SafeHttpsClient.java`**:

```java
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import javax.net.ssl.SSLHandshakeException;

public class SafeHttpsClient {
    public static void main(String[] args)
            throws IOException, InterruptedException {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        try {
            HttpResponse<Void> response = client.send(
                    request, HttpResponse.BodyHandlers.discarding());
            System.out.println("HTTP status: " + response.statusCode());
            System.out.println("TLS identity: accepted");
        } catch (SSLHandshakeException expected) {
            System.err.println("TLS handshake/identity validation failed");
            throw expected;
        }
    }
}
```

```bash
javac --release 11 -encoding UTF-8 SafeHttpsClient.java
java SafeHttpsClient
```

Đây là **chương trình hoàn chỉnh**, nhưng cần DNS, mạng và truststore hoạt động; **stdout không cố định** vì response HTTP và trạng thái mạng có thể thay đổi. Nếu server trình bày cert không được tin hoặc tên không khớp, thao tác có thể thất bại trong TLS handshake (thường là `SSLHandshakeException`, thuộc họ `IOException`). Không viết test cố định với status 200 cho một website bên ngoài.

Chương trình cố tình không thêm bất kỳ công tắc nào để tắt hostname verification. `connectTimeout` và `HttpRequest.timeout` là giới hạn thời gian, **không thay thế xác thực chứng chỉ**.

## 6. Truststore đúng: giải quyết CA mà không bỏ kiểm tra tên

Nhiều hệ thống nội bộ dùng private CA. Khi cert máy chủ hợp lệ về tên nhưng chưa được môi trường Java tin cậy, hướng giải quyết là **cấp và phân phối CA/trust anchor một cách có kiểm soát**, không thay bằng trust manager chấp nhận mọi chứng chỉ.

Trong Java 11, ta có thể cấu hình `TrustManagerFactory` dựa trên một `KeyStore` riêng, khởi tạo `SSLContext`, rồi chuyển cho `HttpClient.Builder.sslContext(...)`.

### Chương trình độc lập: `TrustedHttpsClient.java`

```java
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;

public class TrustedHttpsClient {
    static SSLContext tlsContext(Path trustStorePath, char[] password)
            throws Exception {

        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(trustStorePath)) {
            store.load(in, password);
        }

        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        factory.init(store);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, factory.getTrustManagers(), null);
        return context;
    }

    public static void main(String[] args) throws Exception {
        // Chỉ dùng thông tin này như fixture demo, không lưu mật khẩu thật trong mã.
        char[] password = "changeit".toCharArray();
        SSLContext context = tlsContext(Path.of("trust.p12"), password);

        HttpClient client = HttpClient.newBuilder()
                .sslContext(context)
                .connectTimeout(Duration.ofSeconds(5))
                .build();

        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://localhost:8443/"))
                .timeout(Duration.ofSeconds(10))
                .GET()
                .build();

        HttpResponse<Void> response = client.send(
                request, HttpResponse.BodyHandlers.discarding());
        System.out.println("HTTP status: " + response.statusCode());
    }
}
```

```bash
javac --release 11 -encoding UTF-8 TrustedHttpsClient.java
java TrustedHttpsClient
```

**Điều kiện chạy:** phải có `trust.p12` được quản trị hợp lệ và một HTTPS server thật trên `localhost:8443` với chứng chỉ có SAN đúng, chain tin cậy và TLS hợp lệ. Vì phụ thuộc môi trường, không có stdout cố định. `Path.of` và các API trên đều có trong Java 11.

Điểm bảo mật: chỉ thay **nguồn trust được phép**, không đưa vào một `X509TrustManager` bỏ qua `checkServerTrusted`. `HttpClient` vẫn xác minh danh tính của máy chủ theo HTTPS. Trong production, mật khẩu truststore/keystore phải lấy từ cơ chế secret management phù hợp; không hard-code, commit hoặc log.

**Chính sách truststore cần cân nhắc:** cấu hình một truststore riêng như trên thường **thay thế tập anchor mặc định đối với SSLContext đó**, không tự động gộp với hệ thống. Nếu cần tin cả private CA lẫn public CA, hãy thiết kế tập trust được quản trị rõ và kiểm thử các endpoint thực sự cần gọi. Không sao chép toàn bộ chứng chỉ không rõ nguồn vào truststore cho tiện.

## 7. Thí nghiệm HTTPS local: cert được trust nhưng SAN sai vẫn bị từ chối

Để chứng minh **trust chain** và **hostname verification** là hai điều độc lập, ta tạo hai chứng chỉ tự ký chỉ phục vụ test. Cả hai được import vào cùng một truststore:

- `good.p12` có SAN `IP:127.0.0.1`, khớp URL `https://127.0.0.1:<port>`.
- `bad.p12` có SAN `IP:127.0.0.2`, **không khớp** URL `https://127.0.0.1:<port>`.
- Cả hai chứng chỉ được **tin cậy** bởi client trong bài test. Vì vậy kết nối thứ hai thất bại do **danh tính máy chủ**, không chỉ vì thiếu CA.

Đây là test tích hợp **chỉ trên loopback**, không phụ thuộc Internet. Không sử dụng chứng chỉ, mật khẩu hoặc khóa cá nhân từ demo này trong môi trường thật.

### Bước 1 — Tạo key pair và chứng chỉ SAN với keytool

Mỗi lệnh là **một dòng**, chạy trong thư mục thực hành sạch bằng `keytool` đi kèm JDK 11+. `changeit` ở đây chỉ là **mật khẩu test**, không phải mật khẩu triển khai thật.

```bash
keytool -genkeypair -alias good -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 30 -storetype PKCS12 -keystore good.p12 -storepass changeit -keypass changeit -dname "CN=local-good, O=Training" -ext "SAN=IP:127.0.0.1"
keytool -genkeypair -alias bad -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 30 -storetype PKCS12 -keystore bad.p12 -storepass changeit -keypass changeit -dname "CN=local-bad, O=Training" -ext "SAN=IP:127.0.0.2"
keytool -exportcert -alias good -keystore good.p12 -storepass changeit -rfc -file good.pem
keytool -exportcert -alias bad -keystore bad.p12 -storepass changeit -rfc -file bad.pem
keytool -importcert -alias good -file good.pem -keystore trust.p12 -storetype PKCS12 -storepass changeit -noprompt
keytool -importcert -alias bad -file bad.pem -keystore trust.p12 -storetype PKCS12 -storepass changeit -noprompt
```

Lưu ý: hãy dùng các tệp mới, chưa tồn tại, trong một thư mục test riêng. Các lệnh tạo private key trong `good.p12` và `bad.p12`; không được publish những tệp này. Hai lệnh `-importcert` đưa **public certificate** vào truststore test, không đưa private key vào truststore.

### Bước 2 — Xem SAN đã được tạo

```bash
keytool -list -v -keystore good.p12 -storepass changeit -alias good
keytool -list -v -keystore bad.p12 -storepass changeit -alias bad
```

Tìm trường `SubjectAlternativeName`. Tên tốt phải có IP 127.0.0.1; tên sai chỉ có IP 127.0.0.2. Chỉ khi cấu hình chứng chỉ được xác nhận như vậy mới diễn giải đúng kết quả negative test.

### Bước 3 — Java local HTTPS server + HttpClient

Tệp **`HttpsIdentityLocalTest.java`**:

```java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;

import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;

import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.TrustManagerFactory;

public class HttpsIdentityLocalTest {
    private static final char[] PASSWORD = "changeit".toCharArray();

    static KeyStore openStore(String filename) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream input = Files.newInputStream(Path.of(filename))) {
            store.load(input, PASSWORD);
        }
        return store;
    }

    static SSLContext serverTls(String keyFile) throws Exception {
        KeyStore keys = openStore(keyFile);

        KeyManagerFactory kmf = KeyManagerFactory.getInstance(
                KeyManagerFactory.getDefaultAlgorithm());
        kmf.init(keys, PASSWORD);

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(kmf.getKeyManagers(), null, null);
        return tls;
    }

    static SSLContext clientTls(String trustFile) throws Exception {
        KeyStore trust = openStore(trustFile);

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init(trust);

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(null, tmf.getTrustManagers(), null);
        return tls;
    }

    static HttpsServer createServer(String keyFile) throws Exception {
        HttpsServer server = HttpsServer.create(
                new InetSocketAddress("127.0.0.1", 0), 0);
        server.setHttpsConfigurator(
                new HttpsConfigurator(serverTls(keyFile)));

        server.createContext("/check", exchange -> {
            byte[] body = "ok".getBytes(StandardCharsets.US_ASCII);
            exchange.sendResponseHeaders(200, body.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(body);
            }
        });

        server.start();
        return server;
    }

    static URI addressOf(HttpsServer server) {
        int port = server.getAddress().getPort();
        return URI.create("https://127.0.0.1:" + port + "/check");
    }

    static boolean hasHandshakeFailure(Throwable error) {
        for (Throwable cause = error;
             cause != null;
             cause = cause.getCause()) {
            if (cause instanceof SSLHandshakeException) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        HttpsServer good = createServer("good.p12");
        HttpsServer bad = createServer("bad.p12");
        try {
            HttpClient client = HttpClient.newBuilder()
                    .sslContext(clientTls("trust.p12"))
                    .version(HttpClient.Version.HTTP_1_1)
                    .connectTimeout(Duration.ofSeconds(3))
                    .build();

            HttpRequest goodRequest = HttpRequest.newBuilder(
                    addressOf(good))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            HttpResponse<String> result = client.send(
                    goodRequest,
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.US_ASCII));
            System.out.println("matching SAN: "
                    + result.statusCode() + "/" + result.body());

            HttpRequest badRequest = HttpRequest.newBuilder(
                    addressOf(bad))
                    .timeout(Duration.ofSeconds(5))
                    .GET().build();

            boolean rejected = false;
            try {
                client.send(
                        badRequest,
                        HttpResponse.BodyHandlers.ofString());
            } catch (IOException error) {
                if (!hasHandshakeFailure(error)) {
                    throw error; // Không đánh đồng lỗi network khác với TLS.
                }
                rejected = true;
            }

            if (!rejected) {
                throw new AssertionError(
                        "Certificate with wrong IP SAN was accepted");
            }
            System.out.println("wrong IP SAN rejected: " + rejected);
        } finally {
            good.stop(0);
            bad.stop(0);
        }
    }
}
```

Lệnh biên dịch/chạy:

```bash
javac --release 11 --add-modules jdk.httpserver -encoding UTF-8 HttpsIdentityLocalTest.java
java --add-modules jdk.httpserver HttpsIdentityLocalTest
```

Stdout **mong đợi khi chạy thành công trên JDK 11+ trong môi trường cho phép socket loopback**:

```text
matching SAN: 200/ok
wrong IP SAN rejected: true
```

**Giải thích chi tiết:**

1. Hai `HttpsServer` lắng nghe trên `127.0.0.1` nhưng dùng **cặp khóa/chứng chỉ khác nhau**, vì vậy mỗi bên được cấp một cổng loopback động riêng.
2. `TrustManagerFactory` đọc từ `trust.p12`, chứa cả hai public certificates của demo. Do đó test không dựa vào một “trust all manager”.
3. `HttpClient` dùng `sslContext(clientTls(...))` **nhưng không vô hiệu hóa** kiểm tra hostname. Request thứ nhất gọi URI bằng IP `127.0.0.1` và cert tốt có SAN IP phù hợp.
4. Request thứ hai cũng gọi IP `127.0.0.1` nhưng cert server sai có SAN IP `127.0.0.2`. Endpoint identification phải từ chối **dù chuỗi chứng chỉ đã được trust**.
5. Kiểm tra `hasHandshakeFailure` yêu cầu lỗi thuộc chuỗi nguyên nhân TLS handshake; code **không** coi một lỗi I/O chung nào cũng là bằng chứng xác minh danh tính.
6. Nếu môi trường không cho mở socket trên loopback hoặc không hỗ trợ bộ thuật toán đã chọn, chương trình có thể thất bại trước bài kiểm tra; đó là giới hạn triển khai/môi trường, không nên quy ngay thành “hostname validation thất bại”.

**Quan trọng:** Chỉ nên nhập chứng chỉ test vào `trust.p12` test. Trong hệ thống thật, không tự động “tin tất cả leaf certificates nhận được” để sửa lỗi. Nên cấp chứng chỉ server từ CA mà ứng dụng được phép trust và quản trị trust anchors theo chính sách.

## 8. Java SSLParameters: kiểm tra endpoint ở tầng JSSE cấp thấp

Nếu trực tiếp làm việc với `SSLSocket` hoặc `SSLEngine`, **không** giả định hai lớp cấp thấp tự xác minh host theo URL. Tài liệu JSSE cảnh báo rằng ứng dụng tự dùng raw socket/engine phải cấu hình endpoint identification.

Ví dụ **đoạn minh họa** cho một `SSLSocket` do ứng dụng tự tạo:

```java
SSLParameters parameters = socket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
socket.setSSLParameters(parameters);
socket.startHandshake();
```

Ở đây `socket` phải là `javax.net.ssl.SSLSocket` đã được tạo với peer host chính xác, và bạn phải thiết kế trust managers/TLS đúng trước khi handshake. `"HTTPS"` là tên thuật toán endpoint identification chuẩn. Đoạn này không phải lời khuyên tự viết lại HttpClient; **hãy để HttpClient xử lý HTTPS** nếu ứng dụng đang dùng `java.net.http.HttpClient`.

**Không đánh đồng:**

| Thành phần | Mục đích |
| --- | --- |
| `SSLContext` | Cung cấp key/trust managers và cấu hình bảo mật chung |
| `TrustManagerFactory` | Tạo trust managers từ các trust anchors thích hợp |
| `SSLParameters` | Tập tham số TLS, gồm thuật toán endpoint identification ở JSSE |
| `SSLSocket` / `SSLEngine` | Kết nối/động cơ TLS cấp thấp cần cấu hình hợp đồng phù hợp |
| `HttpClient` của `java.net.http` | Client HTTP(S) mức cao, thực hiện TLS và hostname verification trong cấu hình thông thường |
| `HttpsURLConnection.HostnameVerifier` / `HostnameVerifier` | Callback của cơ chế HTTPS URLConnection, **không** phải setter trên HttpClient mới |

Khi sử dụng `HttpClient.Builder.sslParameters(...)`, Javadoc còn lưu ý một số tham số do HTTP client tự quản lý có thể bị bỏ qua hoặc xử lý nội bộ. Không phụ thuộc vào việc set một tham số rồi đọc lại `client.sslParameters()` để **chứng minh** rằng một kết nối HTTPS cụ thể đã được xác minh đúng: kiểm chứng tích hợp cần một tình huống SAN đúng/sai như bài local test.

## 9. Phân biệt các lỗi TLS thường gặp

Có nhiều lý do khiến HTTPS không kết nối được. Không phải lỗi nào cũng là hostname mismatch.

| Dấu hiệu | Nhóm nguyên nhân thường gặp | Hướng kiểm tra an toàn |
| --- | --- | --- |
| `PKIX path building failed` | Không xây được chain đến trust anchor phù hợp | Cấp/kiểm tra CA chain, truststore |
| `No subject alternative names matching ...` | URL host/IP không khớp SAN | Sửa URI hoặc cấp cert đúng SAN |
| `Certificate expired / not yet valid` | Thời gian hệ thống hoặc hạn chứng chỉ | Kiểm tra clock, gia hạn cert |
| `SSLHandshakeException` | Nhóm lỗi bắt tay TLS khá rộng | Xem `getCause()`, thông điệp và log kiểm soát |
| `SSLPeerUnverifiedException` | Peer identity/certificate không được xác minh trong ngữ cảnh cụ thể | Xem cơ chế và nguyên nhân TLS |
| `ConnectException` | Không kết nối được TCP/port/đường mạng | Kiểm tra DNS, địa chỉ, firewall |
| `HttpTimeoutException` | Vượt giới hạn thời gian | Kiểm tra timeout/mạng/tải |
| HTTP `403` hoặc `500` | Server **đã trả HTTP response** | Debug logic ứng dụng, không mặc định là TLS lỗi |

Thông điệp chi tiết có thể khác giữa JDK và provider. Đừng viết production logic chỉ phụ thuộc substring của thông điệp `SSLHandshakeException`. Khi nghiên cứu, có thể bật log JSSE theo chính sách chẩn đoán của tổ chức, nhưng cần tránh log thông tin mật, và tắt mức debug chi tiết sau khi xử lý xong.

### Async sendAsync

Với `sendAsync(...)`, lỗi có thể làm `CompletableFuture` hoàn tất *exceptionally* và được bọc trong `CompletionException` khi gọi `join()`. Cần duyệt chuỗi `getCause()` để tìm nguyên nhân TLS; không bắt tất cả lỗi rồi coi như response rỗng hoặc chuyển hướng sang HTTP không mã hóa.

Ví dụ minh họa:

```java
CompletableFuture<HttpResponse<String>> future = client.sendAsync(
        request, HttpResponse.BodyHandlers.ofString());

future.whenComplete((response, failure) -> {
    if (failure != null) {
        // Ghi nhận lỗi phù hợp, phân tích cause và không bỏ qua TLS failure.
    } else {
        // Xử lý status/body theo hợp đồng nghiệp vụ.
    }
});
```

Đoạn này không phải chương trình độc lập; cần `client`, `request` và import `CompletableFuture`. `sendAsync` không làm hostname verification trở thành một bước có thể bỏ qua.

## 10. Cấu hình reverse proxy, gateway, SNI và môi trường nội bộ

Trong hệ thống thật, đường đi có thể là:

```text
Java HttpClient --> DNS / proxy / load balancer --> TLS endpoint --> backend
         |
         +-- URI host cần khớp chứng chỉ TLS của endpoint mà client gặp
```

Một số lỗi thường gặp:

- **Gọi IP thay vì DNS name**: chứng chỉ có `DNS:api.internal.example` nhưng URL lại là `https://10.0.0.12`. Hướng đúng là dùng DNS name mà cert bao phủ hoặc phát hành cert có IP SAN nếu thực sự cần gọi IP.
- **Reverse proxy trình bày sai cert**: ingress/nginx/load balancer có nhiều virtual hosts nhưng route TLS/SNI không trỏ đúng. Kiểm tra cấu hình listener và server certificate.
- **Đổi host nhưng giữ chứng chỉ cũ**: migration sang `new-api.example.com` cần cert có SAN phù hợp với tên mới trước khi chuyển traffic.
- **Private CA chưa được trust**: cấp/triển khai trust anchors đúng, không viết trust-all.
- **TLS inspection proxy của tổ chức**: nếu có thiết bị TLS termination theo chính sách, chuỗi chứng chỉ phía client nhìn thấy phải được quản trị tin cậy và **tên endpoint vẫn phải khớp**.
- **Chuyển từ staging sang production**: không dùng chung thủ thuật bỏ xác minh cho tiện; môi trường test cũng nên dùng chứng chỉ đúng SAN để bắt lỗi cấu hình sớm.

**SNI** (Server Name Indication) giúp server chọn đúng virtual host/chứng chỉ trong TLS handshake; **hostname verification** là bước phía client kiểm tra danh tính sau khi server đưa chứng chỉ. Chúng liên quan nhưng **không thay thế nhau**. Tự đặt một SNI name không làm cert sai SAN trở nên hợp lệ cho host thực trong URI.

Nếu application dùng URI từ cấu hình bên ngoài hoặc từ người dùng, cần thêm kiểm soát SSRF/destination policy riêng. Hostname verification bảo vệ danh tính TLS, nhưng không thay thế allowlist đích, hạn chế mạng nội bộ hoặc kiểm soát redirect.

## 11. Khi nào cần kiểm tra chứng chỉ và URL?

Hãy kiểm tra theo thứ tự:

1. **URI chuẩn**: scheme `https`, hostname đúng, không vô tình dùng IP/alias khác tên trong cert.
2. **DNS và định tuyến**: host có phân giải và kết nối tới đúng endpoint không? Proxy nào đang chặn hoặc kết thúc TLS?
3. **Certificate SAN**: danh tính DNS/IP tương ứng với host trong URI không? Xem certificate đang thực sự được server/proxy trình bày.
4. **Trust chain**: root/intermediate CA đúng, truststore đúng, cert còn hiệu lực và không vi phạm chính sách.
5. **Time/algorithm policy**: đồng hồ hệ thống, thuật toán/chữ ký, protocol và cipher suites được JDK hỗ trợ.
6. **JDK properties và JSSE**: không có cấu hình bỏ qua hostname verification hoặc trust validation đã được dùng để “sửa” nhanh trước đó.
7. **Test âm tính**: một cert **được trust nhưng có SAN sai** phải bị từ chối. Test dương tính với SAN đúng phải thành công, như bài local test.
8. **Triển khai đồng nhất**: cùng chính sách bảo vệ cho localhost, staging, container, production, client đồng bộ và bất đồng bộ.

Nếu lỗi chỉ xuất hiện trên một hostname nhưng không xuất hiện trên host khác cùng IP, hãy nghi vấn **SAN hoặc SNI**, không kết luận vội rằng TLS “đã hỏng”. Nếu lỗi là thiếu CA, sửa CA; nếu lỗi là SAN sai, sửa chứng chỉ/URL. Không thay lỗi này bằng việc tắt bảo vệ khác.

## 12. Kiểm thử hồi quy và policy cho code review

Dù unit test trên chuỗi/URI không thể tự xác thực một handshake, nó vẫn có ích để kiểm tra **policy đầu vào** trước khi gọi network.

### Ví dụ độc lập: `HttpsUriPolicy.java`

Lớp này kiểm tra một yêu cầu nghiệp vụ đơn giản: **chỉ cho phép URI HTTPS** với host cụ thể trong danh sách cho phép. Đây là kiểm soát **bổ sung**, không thay thế xác minh chứng chỉ TLS.

```java
import java.net.URI;
import java.util.Set;

public class HttpsUriPolicy {
    private static final Set<String> ALLOWED =
            Set.of("api.example.com", "files.example.com");

    static boolean allowed(URI uri) {
        return uri != null
                && "https".equalsIgnoreCase(uri.getScheme())
                && uri.getHost() != null
                && uri.getUserInfo() == null
                && ALLOWED.contains(uri.getHost().toLowerCase(
                        java.util.Locale.ROOT));
    }

    public static void main(String[] args) {
        System.out.println(allowed(
                URI.create("https://api.example.com/v1/items")));
        System.out.println(allowed(
                URI.create("http://api.example.com/v1/items")));
        System.out.println(allowed(
                URI.create("https://other.example.com/v1/items")));
        System.out.println(allowed(
                URI.create("https://files.example.com/download")));
    }
}
```

```bash
javac --release 11 -encoding UTF-8 HttpsUriPolicy.java
java HttpsUriPolicy
```

```text
true
false
false
true
```

Cần hiểu rõ giới hạn của lớp: `allowed(uri)` mới chỉ là một **ràng buộc URL ở tầng ứng dụng**, không xác minh certificate chain, SAN, redirect đích, DNS rebind hay IP routing. Cần thực thi thêm policy nếu ứng dụng nhận URI không tin cậy; HttpClient/JSSE vẫn phải giữ hostname verification.

### Test matrix cho HTTPS

| Trường hợp | Kỳ vọng |
| --- | --- |
| Chain đáng tin, SAN đúng host | Có thể thiết lập HTTPS |
| Chain đáng tin, SAN sai host | **Handshake bị từ chối** |
| Chain không đáng tin, SAN đúng host | **Handshake bị từ chối** |
| Chứng chỉ hết hạn | **Handshake bị từ chối** |
| DNS name khác IP literal, cert chỉ có DNS SAN | IP URL **không** tự được chấp nhận |
| HTTP URL trên endpoint cần HTTPS | Bị policy ứng dụng từ chối |
| HTTPS qua proxy/ingress có cert đúng | Vẫn xác minh host của URI |
| `sendAsync` với cert sai SAN | Future hoàn tất exceptional, không trả response giả |
| Truststore chứa private CA đúng | Không bỏ endpoint identification |
| TLS error trong production | Quan sát và sửa nguyên nhân, không tự fallback sang HTTP |

Các trường hợp trust/mismatch thật nên dùng integration test với server và chứng chỉ chủ động cấu hình. Chỉ inspect cert bằng `keytool` hay kiểm tra URI chuỗi **không thể thay thế** thực nghiệm bắt tay TLS khi muốn xác nhận runtime đang bảo vệ.

## 13. Câu hỏi tự luyện

**Câu 1.** Nếu Java trust được một chứng chỉ nhưng SAN chỉ chứa `DNS:other.example.com`, có nên chấp nhận khi URL là `https://api.example.com` không?

**Câu 2.** Cert có SAN `DNS:localhost`. Khi gọi `https://127.0.0.1`, tên DNS `localhost` có tự thay thế IP SAN không?

**Câu 3.** Trong Java 11 `HttpClient`, có cần gắn `HostnameVerifier` luôn trả `true` để kết nối đến server dùng private CA không?

**Câu 4.** Khi bị lỗi `PKIX path building failed`, giải pháp đúng là gì?

**Câu 5.** Đặt `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` thường áp dụng ở cấp nào nếu bạn tự tạo kết nối TLS?

**Câu 6.** `SSLContext` có được cấu hình từ truststore riêng thì hostname verification có nên bị bỏ đi không?

**Câu 7.** Khi `sendAsync` gặp certificate mismatch, điều gì xảy ra với `CompletableFuture`?

**Đáp án:**

1. **Không.** Trust chain không thay thế bước so danh tính máy chủ; cần cert có SAN phù hợp URL.
2. **Không.** IP literal cần IP SAN tương ứng theo quy tắc xác minh danh tính.
3. **Không.** Hãy tin đúng CA/trust anchor và phát hành cert có SAN đúng; HttpClient giữ HTTPS validation.
4. **Kiểm tra issuer/CA chain, truststore, hiệu lực và chính sách chứng chỉ**, bổ sung trust anchor chính đáng nếu cần; không dùng trust-all.
5. **JSSE cấp thấp** như `SSLSocket`/`SSLEngine` khi chương trình tự quản lý TLS.
6. **Không.** Cả chain và hostname identity vẫn cần được xác minh.
7. Future hoàn tất **exceptionally**; caller cần xử lý nguyên nhân, không tự biến lỗi TLS thành response thành công.

## 14. Tóm tắt thực hành

- Dùng `HttpClient.newBuilder().build()` / `newHttpClient()` với mặc định HTTPS xác thực phù hợp.
- Đặt URL bằng **host thật sự cần truy cập** và phát hành chứng chỉ có SAN DNS/IP tương ứng.
- Khi cần private CA, cấu hình truststore/SSLContext đúng, chỉ trust những CA/cert được xác thực nguồn gốc; **không** vô hiệu hóa hostname verification.
- Không sử dụng các công tắc nội bộ, callback always-true hay trust-all để bỏ qua TLS failures.
- Kiểm tra đúng nguyên nhân lỗi: chain, SAN, hạn cert, proxy, SNI, clock hoặc TLS policy.
- Dùng integration test có **cert tin cậy nhưng SAN sai** để bảo đảm client thực sự từ chối danh tính không phù hợp.
- Xem hostname verification là **bảo vệ bắt buộc**, song song với auth, giới hạn destination/SSRF, redirect policy và quản trị secret.

## Tài liệu chính thức

- [Java SE 11 — HttpClient: SSLContext, SSLParameters và sử dụng HTTPS](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.html).
- [Java SE 11 — HttpClient.Builder: sslContext(), sslParameters() và cấu hình TLS](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html).
- [Java SE 11 — X509ExtendedTrustManager: kiểm tra chain và endpoint identity](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html).
- [Java SE 11 — SSLParameters: endpoint identification algorithm](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLParameters.html).
- [Java SE 11 — Java Secure Socket Extension (JSSE) Reference Guide](https://docs.oracle.com/en/java/javase/11/security/java-secure-socket-extension-jsse-reference-guide.html).
- [Java SE 11 — keytool: -genkeypair, SAN extension, -exportcert và -importcert](https://docs.oracle.com/en/java/javase/11/tools/keytool.html).
- [Java SE 22 — Core Libraries: hostname verification property chỉ dành cho testing](https://docs.oracle.com/en/java/javase/22/core/java-core-libraries-developer-guide.pdf).
