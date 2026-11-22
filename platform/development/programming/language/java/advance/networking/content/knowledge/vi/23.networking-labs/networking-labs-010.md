# Kiểm tra tên máy và truststore bằng cặp HTTPS client/server thử nghiệm

**Chủ đề:** Java Advance - networking  
**Nhóm:** Thực nghiệm mạng  
**Ngôn ngữ và công cụ:** Java 17+, **java.net.http.HttpClient**, **com.sun.net.httpserver.HttpsServer**, **javax.net.ssl.SSLContext**, **KeyStore PKCS12**, **keytool**.

## 1. Bài toán và kết quả cần quan sát

Khi một HTTPS client kết nối tới server, **thành công của TCP connect không đủ để coi server đáng tin**. Trong quá trình TLS handshake, client cần xác thực chứng chỉ máy chủ, gồm hai câu hỏi độc lập:

1. **Trust/chain validation:** chứng chỉ hoặc chuỗi chứng chỉ server có dẫn tới một **trust anchor** mà client được cấu hình tin cậy không? Chứng chỉ có thỏa các ràng buộc sử dụng, chữ ký, thời hạn và chính sách liên quan không?
2. **Hostname verification (endpoint identification):** danh tính tên máy trong **URL đích** có khớp **Subject Alternative Name (SAN)** phù hợp trên chứng chỉ server không?

Bài thực hành xây một **cặp HTTPS server/client chạy trên cùng máy**, không gọi Internet, để kiểm chứng cả hai cơ chế:

| Ca kiểm thử | Truststore client | URI truy cập | Kết quả kỳ vọng |
| --- | --- | --- | --- |
| A | Có chứng chỉ server được tin cậy | **https://localhost:PORT/hello** | TLS thành công; HTTP 200 và body TLS_OK |
| B | Chỉ có chứng chỉ **không liên quan** | **https://localhost:PORT/hello** | TLS handshake bị từ chối vì không xác thực được server |
| C | Có chứng chỉ server được tin cậy | **https://127.0.0.1:PORT/hello** | TLS handshake bị từ chối vì SAN chỉ có **DNS:localhost**, không có **IP:127.0.0.1** |

**Điểm then chốt:** B và C thất bại vì **hai nguyên nhân khác nhau**, mặc dù cùng server/port. Sửa truststore **không** tự sửa lỗi sai hostname; sửa URL thành đúng hostname **không** tự biến certificate chưa được tin cậy thành trusted.

Demo dùng chứng chỉ self-signed và mật khẩu minh họa trong **môi trường test tạm**, không sao chép khóa riêng, truststore hay password này vào production. **Không tắt hostname verification hoặc dùng trust-all TrustManager** để ép HTTPS handshake thành công.

## 2. HTTPS được xác thực ở đâu?

Quy trình rút gọn:

~~~text
HttpClient                 TCP/TLS server
    |                           |
    | --- TCP connect --------> |
    | <--- TCP established ----- |
    |                           |
    | --- TLS ClientHello ----> | (có thể chứa SNI "localhost")
    | <--- certificate chain --- |
    |                           |
    | [1] kiểm chứng trust chain |
    | [2] kiểm chứng SAN        |
    | [3] policy, validity,     |
    |     key usage, algorithms |
    |                           |
    | --- TLS handshake done -->| nếu hợp lệ
    |                           |
    | --- HTTPS GET /hello ---> |
    | <--- HTTP 200 TLS_OK ----- |
~~~

**TLS handshake** xảy ra trước khi request HTTP được xử lý trong server handler. Nếu chain hoặc hostname không hợp lệ, client thường ném **SSLHandshakeException** (hoặc I/O exception có nguyên nhân bên trong) và **không có một HttpResponse.statusCode() bình thường** để đọc.

### Ba danh tính cần phân biệt

- **IP đích của TCP socket:** địa chỉ thật dùng để đi tới server, ví dụ **127.0.0.1**.
- **Host trong HTTPS URI:** phần hostname ứng dụng yêu cầu, ví dụ **localhost** hoặc **127.0.0.1**.
- **Tên máy trong certificate SAN:** chứng chỉ khai báo endpoint được phép đại diện, ví dụ **DNS:localhost**.

Khi URL là **https://localhost:PORT**, client có thể resolve localhost về một địa chỉ loopback. Dù TCP thực sự nối vào **127.0.0.1**, endpoint identification vẫn kiểm tra **tên localhost trong URL** với SAN DNS. Khi đổi URI thành **https://127.0.0.1:PORT**, client phải đối chiếu **địa chỉ IP** với **SAN IP address**; **SAN DNS:localhost không thay thế IP SAN**.

**DNS resolve thành công không phải bằng chứng TLS identity thành công.** Một IP có thể phục vụ nhiều virtual hosts; một chứng chỉ chỉ hợp lệ cho đúng các DNS/IP identities mà nó được cấp.

## 3. Keystore và truststore có nhiệm vụ khác nhau

### Server keystore

Server HTTPS phải chứng minh quyền sử dụng một **private key** tương ứng với public key trên certificate. Trong demo, file **server.p12** kiểu PKCS12 chứa:

- **Private key** RSA của server.
- **Certificate self-signed** mang public key, subject CN=localhost, và **SAN DNS:localhost**.
- Alias **localhost** để server JSSE chọn key/certificate.

Server đọc file này bằng **KeyStore**, đưa vào **KeyManagerFactory**, rồi dùng KeyManagers khi tạo **SSLContext** cho HttpsServer.

**Không được đưa server.p12 cho client**: nó chứa private key. Nếu chỉ cần client tin server, xuất **chứng chỉ public** thành **server.cer**, rồi nhập certificate đó vào client truststore.

### Client truststore

Một client truststore chứa certificates được coi là **trusted entries/trust anchors** theo chính sách PKIX. Trong demo:

- **client-trusted.p12** chứa certificate public của server (alias server), đủ để tin cậy chính self-signed certificate test.
- **client-untrusted.p12** chứa certificate public của một keypair **khác, không liên quan**, nên không xác thực được server test.

Client đọc truststore bằng **TrustManagerFactory**, tạo **SSLContext**, và truyền SSLContext vào **HttpClient.newBuilder().sslContext(...)**.

**Một truststore đúng vẫn chưa đủ**: HttpClient còn phải xác minh **hostname** của URI. Nếu URI chứa IP 127.0.0.1 nhưng SAN chỉ có DNS:localhost, request phải bị từ chối.

### Bảng phân biệt

| Khái niệm | Có private key không? | Ai dùng trong demo? | Mục đích |
| --- | --- | --- | --- |
| **server.p12** | Có | HttpsServer/KeyManagerFactory | Server xuất trình certificate và chứng minh sở hữu private key |
| **server.cer** | Không | Được xuất từ server.p12 | Certificate public để phân phối trust một cách có kiểm soát |
| **client-trusted.p12** | Không có private key server | HttpClient/TrustManagerFactory | Client tin đúng certificate self-signed test |
| **client-untrusted.p12** | Chỉ certificate công khai của máy không liên quan | HttpClient/TrustManagerFactory | Tạo ca negative trust validation |
| **JDK cacerts** | Thường các CA public trust anchors | HTTPS client dùng defaults | Không tự tin chứng chỉ self-signed test |
| **SAN extension** | Nằm trong certificate | Client hostname verifier | Kiểm chứng host/IP request có được certificate đại diện |

**Cảnh báo:** PKCS12 là một **định dạng kho khóa/chứng chỉ**, không tự mang nghĩa “keystore” hay “truststore”. Hai vai trò được xác định bởi **nội dung và cách ứng dụng sử dụng**.

## 4. Tạo chứng chỉ self-signed có SAN DNS:localhost bằng keytool

Để bài chạy lặp lại được, dùng **JDK 17+** có **keytool**, **javac** và **java** trên PATH. Tạo một **thư mục test riêng** rồi chạy các lệnh sau bên trong. Không dùng thư mục làm việc của repo production để lưu key/cert. Tất cả tệp tạo ra là **fixtures ngắn hạn**, xóa sau khi học.

### Bước 1 — tạo server.p12

~~~bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 7 -storetype PKCS12 -keystore server.p12 -storepass changeit -keypass changeit -dname "CN=localhost, OU=Learning, O=Example, C=VN" -ext "SAN=DNS:localhost" -ext "EKU=serverAuth" -noprompt
~~~

Giải thích:

- **-genkeypair:** tạo private key và certificate self-signed.
- **-alias localhost:** alias keypair bên trong server keystore.
- **RSA 2048 / SHA256withRSA:** thuật toán phục vụ test, không phải kết luận về lựa chọn thuật toán production.
- **-validity 7:** chứng chỉ chỉ có thời hạn 7 ngày tính từ lúc tạo; phải tạo lại khi hết hạn.
- **-storetype PKCS12:** format portable trong Java/JDK.
- **-dname CN=localhost:** subject; **không dựa vào CN thay thế SAN**.
- **-ext SAN=DNS:localhost:** khai báo rõ tên máy được chứng chỉ bảo vệ.
- **-ext EKU=serverAuth:** certificate hướng đến xác thực TLS server.
- **changeit:** mật khẩu mẫu, **tuyệt đối không dùng như production secret**.

**Quan trọng:** Chỉ cấp **DNS:localhost**, **không cấp IP:127.0.0.1**, để ca C thất bại đúng mục tiêu. Nếu tự thêm IP:127.0.0.1 vào SAN, ca C **có thể thành công**, và bài kiểm thử hostname mismatch sẽ không còn tác dụng.

### Bước 2 — xuất public certificate, không xuất private key

~~~bash
keytool -exportcert -alias localhost -keystore server.p12 -storepass changeit -file server.cer
~~~

**server.cer** chứa **public certificate**. Việc export/import một certificate khác hoàn toàn với copy **server.p12**: bản export này không chứa private key và chỉ giúp phía client biết certificate nào được tin cậy. Trong thực tế cần xác minh fingerprint và kênh phân phối certificate trước khi quyết định trust; import một certificate bất kỳ từ nguồn không tin cậy có thể phá vỡ mô hình bảo mật.

### Bước 3 — tạo truststore chấp nhận server test

~~~bash
keytool -importcert -alias server -file server.cer -keystore client-trusted.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

**-noprompt** chỉ thích hợp trong thí nghiệm kiểm soát được certificate đã xuất từ keypair do chính bạn tạo. Với hệ thống thật, không dùng nó để tự động tin một certificate chưa được xác minh. Truststore này sẽ chứa certificate public của server làm trust anchor cho bài test.

### Bước 4 — tạo certificate không liên quan và truststore sai

Tạo một keypair độc lập, với tên miền khác:

~~~bash
keytool -genkeypair -alias unrelated -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 7 -storetype PKCS12 -keystore unrelated.p12 -storepass changeit -keypass changeit -dname "CN=unrelated.example, OU=Learning, O=Example, C=VN" -ext "SAN=DNS:unrelated.example" -noprompt
~~~

Xuất certificate public không liên quan:

~~~bash
keytool -exportcert -alias unrelated -keystore unrelated.p12 -storepass changeit -file unrelated.cer
~~~

Nhập vào truststore để test negative trust path:

~~~bash
keytool -importcert -alias unrelated -file unrelated.cer -keystore client-untrusted.p12 -storetype PKCS12 -storepass changeit -noprompt
~~~

**Không** dùng một truststore rỗng nếu muốn loại trừ vấn đề riêng của provider khi không có trust anchors; dùng certificate **unrelated** khiến bài test rõ ràng: có truststore hợp lệ, chỉ là **không tin server này**.

### Bước 5 — xem thông tin trước khi chạy

~~~bash
keytool -list -v -alias localhost -keystore server.p12 -storepass changeit
keytool -list -v -alias server -keystore client-trusted.p12 -storepass changeit
keytool -list -v -alias unrelated -keystore client-untrusted.p12 -storepass changeit
~~~

Kiểm tra **SHA-256 fingerprint**, **Owner/Issuer**, **SubjectAlternativeName**, validity, EKU và aliases. Ở server certificate phải thấy **DNSName: localhost** trong SAN (cách keytool in có thể khác JDK). **Không** tìm hay đoán một IP SAN vì ta không tạo nó.

**Lưu ý tương thích shell:** các lệnh trên là một dòng, dùng được với terminal thông thường của JDK. Trong PowerShell 5.1, tùy việc parse các options bắt đầu bằng -D, có thể cần truyền tham số JVM dưới dạng **một chuỗi có dấu nháy** ở bước chạy chương trình bên dưới. Các file .p12 chỉ dùng cho test; đừng upload lên git, email hoặc share công khai.

## 5. Demo HTTPS server/client Java 17 hoàn chỉnh

Chương trình **HttpsTrustAndHostnameDemo.java** thực hiện đầy đủ ba ca A/B/C. Toàn bộ HTTPS server nằm trong JVM:

- **HttpsServer** bind **127.0.0.1** và port 0 (OS chọn port chưa dùng), tránh public network.
- **KeyManagerFactory** nạp private key/certificate từ **server.p12**.
- **HttpsConfigurator** gắn SSLContext vào server.
- **GET /hello** sau TLS thành công trả **HTTP 200**, content type **text/plain; charset=UTF-8**, body **TLS_OK**.
- **TrustManagerFactory** nạp một trong hai client truststores, tạo SSLContext cho từng HttpClient.
- Client A gọi **https://localhost:PORT/hello** bằng truststore đúng.
- Client B gọi cùng URI với truststore chứa certificate unrelated, dự kiến handshake fail.
- Client C dùng truststore đúng nhưng URI **https://127.0.0.1:PORT/hello**, dự kiến hostname check fail.

**Không có dòng nào vô hiệu hóa hostname verification.** Demo cũng không thay system-wide default truststore; nó tạo hai SSLContexts **riêng theo từng client**, tránh ảnh hưởng các HTTPS requests khác của cùng JVM.

### Source: HttpsTrustAndHostnameDemo.java

~~~java
import com.sun.net.httpserver.HttpsConfigurator;
import com.sun.net.httpserver.HttpsServer;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.InetAddress;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.time.Duration;
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLHandshakeException;
import javax.net.ssl.TrustManagerFactory;

public class HttpsTrustAndHostnameDemo {
    static final char[] PASSWORD = "changeit".toCharArray();

    static KeyStore loadStore(Path file) throws Exception {
        KeyStore store = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(file)) {
            store.load(in, PASSWORD);
        }
        return store;
    }

    static SSLContext serverContext(Path file) throws Exception {
        KeyManagerFactory keys =
                KeyManagerFactory.getInstance(
                        KeyManagerFactory.getDefaultAlgorithm());
        keys.init(loadStore(file), PASSWORD);

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(keys.getKeyManagers(), null, new SecureRandom());
        return tls;
    }

    static SSLContext clientContext(Path file) throws Exception {
        TrustManagerFactory tm =
                TrustManagerFactory.getInstance(
                        TrustManagerFactory.getDefaultAlgorithm());
        tm.init(loadStore(file));

        SSLContext tls = SSLContext.getInstance("TLS");
        tls.init(null, tm.getTrustManagers(), new SecureRandom());
        return tls;
    }

    static HttpClient client(Path file) throws Exception {
        return HttpClient.newBuilder()
                .sslContext(clientContext(file))
                .connectTimeout(Duration.ofSeconds(3))
                .version(HttpClient.Version.HTTP_1_1)
                .build();
    }

    static HttpRequest request(URI uri) {
        return HttpRequest.newBuilder(uri)
                .timeout(Duration.ofSeconds(5))
                .GET()
                .build();
    }

    static boolean rejectsHandshake(
            HttpClient client, URI uri) throws Exception {
        try {
            client.send(
                    request(uri),
                    HttpResponse.BodyHandlers.ofString());
            return false;
        } catch (SSLHandshakeException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Expected 3 PKCS12 files");
        }

        SSLContext serverTls = serverContext(Path.of(args[0]));
        HttpsServer server = HttpsServer.create(
                new InetSocketAddress(
                        InetAddress.getByName("127.0.0.1"), 0), 0);
        server.setHttpsConfigurator(
                new HttpsConfigurator(serverTls));

        server.createContext("/hello", exchange -> {
            try (exchange) {
                byte[] bytes = "TLS_OK".getBytes(
                        StandardCharsets.UTF_8);
                exchange.getResponseHeaders().set(
                        "Content-Type",
                        "text/plain; charset=UTF-8");
                exchange.sendResponseHeaders(200, bytes.length);
                try (OutputStream output =
                             exchange.getResponseBody()) {
                    output.write(bytes);
                }
            }
        });

        server.start();
        try {
            int port = server.getAddress().getPort();

            URI good = URI.create(
                    "https://localhost:" + port + "/hello");
            URI badName = URI.create(
                    "https://127.0.0.1:" + port + "/hello");

            HttpClient trusted = client(Path.of(args[1]));
            HttpClient untrusted = client(Path.of(args[2]));

            HttpResponse<String> response = trusted.send(
                    request(good),
                    HttpResponse.BodyHandlers.ofString(
                            StandardCharsets.UTF_8));
            System.out.println(
                    "trustedHostStatus=" + response.statusCode());
            System.out.println(
                    "trustedHostBody=" + response.body());

            System.out.println(
                    "wrongTrustRejected="
                            + rejectsHandshake(untrusted, good));
            System.out.println(
                    "wrongHostnameRejected="
                            + rejectsHandshake(trusted, badName));
        } finally {
            server.stop(0);
        }
    }
}
~~~

### Chạy demo

Lưu đúng source vào **HttpsTrustAndHostnameDemo.java** trong **thư mục chứa ba file .p12** đã tạo. Biên dịch trên JDK 17+:

~~~bash
javac --release 17 -encoding UTF-8 HttpsTrustAndHostnameDemo.java
~~~

Chạy, ép JVM ưu tiên IPv4 để **localhost** nối được tới fixture bind **127.0.0.1** cả trên máy có IPv6:

~~~bash
java -Djava.net.preferIPv4Stack=true HttpsTrustAndHostnameDemo server.p12 client-trusted.p12 client-untrusted.p12
~~~

**Nếu dùng Windows PowerShell 5.1**, có thể dùng tham số -D được đặt trong quotes:

~~~powershell
java '-Djava.net.preferIPv4Stack=true' HttpsTrustAndHostnameDemo server.p12 client-trusted.p12 client-untrusted.p12
~~~

**Stdout đã được kiểm chứng thực tế khi biên dịch với javac --release 17, chạy trên JDK 24.0.2 với keytool tạo fixtures mới:**

~~~text
trustedHostStatus=200
trustedHostBody=TLS_OK
wrongTrustRejected=true
wrongHostnameRejected=true
~~~

**Lưu ý:** exception message cụ thể của JSSE/PKIX có thể thay đổi theo JDK, provider, OS, certificate state và truststore. Vì vậy demo **không so khớp nguyên văn exception text**, mà xác nhận đúng nhóm **SSLHandshakeException** cho hai ca âm tính. Nếu một ca bất ngờ ném loại I/O error khác (ví dụ không connect được do bind/IPv6 mismatch), chương trình fail rõ ràng thay vì in “rejected=true” sai bản chất.

### Giải thích output

1. **trustedHostStatus=200**: truststore có certificate server và URL host khớp SAN; TLS handshake hoàn tất, HTTP handler mới chạy.
2. **trustedHostBody=TLS_OK**: response body đã được HttpClient giải mã UTF-8 đúng.
3. **wrongTrustRejected=true**: truststore chỉ có unrelated certificate; client không xây được trust path tới server certificate, nên bắt được SSLHandshakeException.
4. **wrongHostnameRejected=true**: client đã tin certificate server, nhưng URI host là địa chỉ IP 127.0.0.1, trong khi SAN server chỉ có **DNS:localhost**. Endpoint identification từ chối.
5. Server vẫn bind cùng một port trong mọi ca. **Không có 404/500** cho hai handshake failures; HTTP handler không được chạy để trả status cho những request không vượt qua TLS.
6. Chương trình **server.stop(0)** trong finally và đóng file InputStream khi nạp keystore/truststore. Trong Java 17, HttpClient chưa có AutoCloseable/close API của Java 21+, nên không dùng try-with-resources cho HttpClient dưới --release 17.

**Bảo mật:** Password **changeit** chỉ nhằm làm các lệnh có thể tái tạo trong môi trường test ngắn hạn. Không sử dụng password này hay private key self-signed fixture cho production. Trong hệ thống thật, secret nên được cấp qua secrets manager/keystore có quyền hạn giới hạn.

## 6. Phân tích chuyên sâu: tin cậy certificate chưa phải tin đúng tên máy

Giả sử server certificate có:

~~~text
Subject: CN=localhost
Subject Alternative Name:
    DNSName: localhost

Public Key: RSA 2048-bit
Extended Key Usage: TLS Web Server Authentication
Issuer: self-signed for this demo
~~~

Trường **CN** có thể được sử dụng trong những compatibility corner cases cũ, nhưng **không nên thiết kế HTTPS hiện đại dựa vào CN fallback khi có SAN**. Với certificate có SAN DNS:localhost, hostname verification phải đối chiếu DNS name trong URI.

**Ba phép kiểm tra tách rời:**

### A — trust đúng, tên đúng

~~~text
URI host: localhost
Cert SAN: DNS:localhost
Truststore: chứa public certificate server

Trust path: PASS
Hostname:   PASS
HTTP:       GET /hello -> 200 TLS_OK
~~~

### B — trust sai, tên đúng

~~~text
URI host: localhost
Cert SAN: DNS:localhost
Truststore: chỉ có unrelated certificate

Trust path: FAIL
Hostname:   có thể chưa cần đánh giá tiếp
HTTP:       không có successful HttpResponse
~~~

### C — trust đúng, tên sai

~~~text
URI host: 127.0.0.1
Cert SAN: DNS:localhost
Truststore: chứa public certificate server

Trust path: PASS
Hostname:   FAIL (thiếu SAN IP Address 127.0.0.1)
HTTP:       không có successful HttpResponse
~~~

**Không cố suy thứ tự mọi bước kiểm tra từ exception message**: JSSE provider có thể sắp xếp các kiểm tra hoặc báo lỗi khác nhau. Điểm chắc chắn của bài là client chỉ cho phép HTTP sau khi tất cả ràng buộc TLS identity/trust yêu cầu đều qua.

### Vì sao đổi localhost thành 127.0.0.1 lại quan trọng?

Đây không phải lỗi routing/IP. Cả hai URI đều có thể tới **cùng một local server**, nhưng **HTTPS URI host là danh tính cần chứng minh**. Khi client dùng IP literal, certificate phải có **IP Address SAN** khớp. Một DNS SAN chứa chuỗi "127.0.0.1" (nếu có) cũng không nên dùng thay IP SAN đúng loại. Nếu thực sự cần cả hai cách truy cập trong production, CA phải cấp chứng chỉ chứa **cả DNS SAN và IP SAN tương ứng** theo chính sách; với public PKI, cấp certificate cho internal name/IP có các ràng buộc riêng.

## 7. Truststore mặc định của JDK so với custom SSLContext

Một ứng dụng Java có nhiều cách để quản lý trust:

- **Mặc định:** HttpClient sử dụng SSLContext/trust manager mặc định của JVM, thường dựa trên một JDK truststore như **cacerts**, cùng các Java security/system properties có thể ảnh hưởng.
- **Per-client:** Tạo **SSLContext** từ một truststore chỉ định, rồi truyền vào **HttpClient.newBuilder().sslContext(tls)**. Demo dùng cách này để **cô lập test**.
- **System-wide:** Các system properties **javax.net.ssl.trustStore**, **javax.net.ssl.trustStorePassword**, **javax.net.ssl.trustStoreType** có thể ảnh hưởng trust manager mặc định khi khởi tạo. Cần hiểu tác động toàn process, initialization timing và môi trường.

**Không nhầm:**

~~~text
javax.net.ssl.keyStore       -> thường chỉ client/server key material
javax.net.ssl.trustStore     -> trust anchors đối với peer
HttpClient.Builder.sslContext -> gắn SSLContext vào HTTP client cụ thể
~~~

Trong bài này, **server.p12** là nơi cất private key của server; **client-trusted.p12** là nơi tin certificate public. Nếu bạn chỉ set **javax.net.ssl.keyStore** trên client mà không cấu hình truststore, bạn chưa giải quyết bài toán client tin server.

**Cẩn trọng với truststore thay thế:** Một custom SSLContext được tạo chỉ với trust managers từ một truststore nhỏ có thể **không còn tin các public CAs** từng có trong JVM default. Demo chỉ nói chuyện với server test nên đó là điều mong muốn. Trong ứng dụng production, cần thiết kế policy trust rõ: private CA, public CAs, trust bundle rotation và giới hạn blast radius. Không thêm một certificate ngẫu nhiên rồi coi toàn bộ trust chain an toàn.

### Cách xem fingerprint

~~~bash
keytool -list -v -alias localhost -keystore server.p12 -storepass changeit
keytool -list -v -alias server -keystore client-trusted.p12 -storepass changeit
~~~

Dùng fingerprint **SHA-256** để xác minh client thực sự tin đúng cert vừa tạo. Nếu certificate khác sau khi server rotate key/cert, client truststore cũ có thể không tin nữa. Khi dùng private CA thật, thường tin **CA phù hợp** thay vì pin trực tiếp leaf server certificate để hỗ trợ rotation; vẫn phải kiểm tra SAN/validity/usage.

## 8. TLS handshake failure khác HTTP status 4xx/5xx

Đây là một lỗi chẩn đoán rất phổ biến. **HTTP 401/403/404/500** chỉ có nghĩa khi HTTP layer đã trao đổi được response. Khi certificate không trusted hoặc SAN không khớp, **TLS handshake thất bại trước HTTP request/response**. Không có HTTP 500 do chính HttpsServer handler gửi trong demo ấy.

| Tình huống | Có TCP connect? | TLS thành công? | Có HttpResponse? | Cần xử lý |
| --- | --- | --- | --- | --- |
| Trust đúng + hostname đúng | Có | Có | Có, 200 | Đọc status/body |
| Truststore không tin cert | Có thể có | Không | Không | Kiểm tra trust anchors/cert chain |
| SAN không khớp URI host | Có thể có | Không | Không | Sửa URI hoặc cấp certificate SAN đúng |
| Cert hết hạn | Có thể có | Không theo chính sách bình thường | Không | Renew/redeploy cert đúng |
| DNS không resolve | Không | Chưa tới TLS | Không | Kiểm tra DNS/URI |
| TCP connect refused | Không kết nối được | Chưa tới TLS | Không | Kiểm tra bind/port/firewall |
| HTTP 404 sau TLS tốt | Có | Có | Có, 404 | Xử lý HTTP route |
| HTTP 503 sau TLS tốt | Có | Có | Có, 503 | Service readiness/backend |
| TLS client certificate bị từ chối | Có | Không hoàn tất | Không | Kiểm tra mTLS client identity |

Trong Java, **SSLHandshakeException** kế thừa **SSLException**, một subtype của **IOException**. Với **HttpClient.sendAsync**, lỗi có thể được bọc trong **CompletionException** khi gọi join(), hoặc trong **ExecutionException** khi get(). Tách nguyên nhân qua **getCause()** và log exception class, endpoint đã làm mờ, nhưng không log private keys/passwords.

**Không làm kiểu này:**

~~~java
catch (IOException e) {
    return 500; // SAI: bịa HTTP 500 khi chưa có response.
}
~~~

Thay vào đó, API nên có kiểu kết quả phân biệt **HttpOutcome(status,body)** với **TransportOrTlsFailure(cause)**, và service-level health response với business validation errors.

## 9. Các cách “sửa lỗi” nguy hiểm phải tránh

### Không dùng TrustManager tin mọi certificate

Ví dụ anti-pattern (không chạy):

~~~java
// ANTI-PATTERN: TrustManager chấp nhận mọi certificate.
// Không triển khai X509TrustManager checkServerTrusted() rỗng.
// Không dùng SSLContext có trust-all trong production/test thực.
~~~

Nếu client bỏ qua certificate chain validation, một kẻ tấn công middlebox có thể xuất trình certificate do họ tạo. Đường truyền có thể vẫn được mã hóa nhưng **không xác thực đúng peer**.

### Không tắt hostname verification

Đừng đặt một cấu hình “disable endpoint identification” hoặc property implementation-specific để cho **https://127.0.0.1** chấp nhận cert chỉ có DNS:localhost. Làm vậy **hủy đúng bài test cần kiểm chứng** và tạo nguy cơ kết nối tới server khác với identity mong muốn.

Đặc biệt tránh truyền **SSLParameters** tùy tiện hoặc property không được hỗ trợ vào HttpClient với mục tiêu bỏ qua endpoint identification. Demo sử dụng **HttpClient.sslContext(custom)** nhưng giữ **hostname verification mặc định** và chứng minh mismatch bị chặn.

### Không nhập bừa certificate khi nhìn thấy handshake error

Chạy keytool importcert -noprompt với certificate download từ một endpoint chưa được xác thực có thể khiến bạn tin đúng certificate của kẻ giả mạo. Để an toàn:

1. Có certificate/trust bundle từ **kênh quản trị đáng tin**.
2. Kiểm tra SHA-256 fingerprint ngoài băng hoặc bằng PKI được quản lý.
3. Import đúng CA hoặc certificate được phê duyệt.
4. Kiểm chứng **URI hostname** khớp SAN.
5. Thiết lập rotation/expiration monitoring.
6. Giữ quyền đọc/ghi truststore chặt chẽ và không leak secrets.

### Không chuyển sang HTTP không mã hóa

Thay **https://** thành **http://** để bỏ lỗi TLS sẽ loại bỏ bảo mật kênh truyền. Trong demo, điều này còn khiến HTTP request gửi tới một **TLS-only port**, có thể thất bại theo cách khác chứ không tạo thành công thực.

## 10. Xác minh SAN, trust chain và nguyên nhân lỗi

### Bằng keytool

~~~bash
keytool -list -v -alias localhost -keystore server.p12 -storepass changeit
keytool -list -v -alias server -keystore client-trusted.p12 -storepass changeit
keytool -list -v -alias unrelated -keystore client-untrusted.p12 -storepass changeit
~~~

Kiểm tra:

- **Alias** và **Entry type**: server.p12 chứa PrivateKeyEntry; client-trusted.p12 thường là trustedCertEntry.
- **Subject, issuer, validity**: CN=localhost, self-signed fixture, ngày bắt đầu/kết thúc.
- **SAN**: chỉ DNSName: localhost.
- **ExtendedKeyUsage**: serverAuth nếu được in.
- **SHA-256 fingerprint**: certificate server trong truststore đúng phải có fingerprint tương ứng server.cer.

Nếu nhập nhầm alias/certificate hoặc gõ sai password, lỗi có thể xảy ra **khi khởi tạo KeyStore/SSLContext** trước cả network. Không nhầm một **IOException giải mã keystore** với một **SSLHandshakeException do remote server**.

### SSL debug chỉ trong môi trường kiểm soát

JDK JSSE hỗ trợ diagnostic:

~~~bash
java -Djava.net.preferIPv4Stack=true -Djavax.net.debug=ssl,handshake,trustmanager HttpsTrustAndHostnameDemo server.p12 client-trusted.p12 client-untrusted.p12
~~~

**Output rất dài** và có thể chứa chi tiết trao đổi TLS, certificate và môi trường; chỉ bật trong test/dev có kiểm soát. Đừng đưa logs raw chứa bí mật/traces nhạy cảm lên hệ thống công khai. Các bản JDK/provider có thể thay đổi format, không viết parser business phụ thuộc message text.

Các gợi ý chẩn đoán:

| Triệu chứng | Thứ cần kiểm tra trước |
| --- | --- |
| **PKIX path building failed** hoặc unable to find valid certification path | Truststore nào đang được dùng? Có đúng certificate/CA? |
| **No subject alternative names matching IP address** | URL là IP, SAN có loại IP Address và giá trị tương ứng không? |
| **No name matching ... found** | Host trong URI có khớp DNS SAN không? |
| **Keystore was tampered with / password incorrect** | Password, format PKCS12/JKS, file bytes, alias |
| **Connection refused** | Server bind đúng IP/port, tiến trình còn chạy? |
| **Unrecognized SSL message/plaintext connection** | HTTP/HTTPS sai scheme/port, proxy termination? |
| **Handshake timeout** | Network path, proxy, TLS capabilities và deadline |
| **Received fatal alert: bad_certificate** | Có thể liên quan mTLS client certificate hoặc server policy |
| **Certificate expired/not yet valid** | Clock/timezone, certificate validity, rotation |

Exception messages chỉ mang tính gợi ý. Xem **cause chain** và bằng chứng từ đúng môi trường trước khi kết luận.

## 11. SAN DNS vs SAN IP và việc đổi hostname

Một người mới thường hỏi: “localhost và 127.0.0.1 cùng về loopback, sao HTTPS vẫn fail?”. TLS endpoint identity không xác thực “cùng đích IP” mà xác thực **tên hoặc IP trong URI** theo rules. Nếu muốn **hợp lệ cho cả DNS localhost và IP 127.0.0.1 trong một test khác**, cần cấp cert chứa cả hai SAN types:

~~~bash
keytool -genkeypair -alias localhost -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 7 -storetype PKCS12 -keystore server-both.p12 -storepass changeit -keypass changeit -dname "CN=localhost, OU=Learning, O=Example, C=VN" -ext "SAN=DNS:localhost,IP:127.0.0.1" -ext "EKU=serverAuth" -noprompt
~~~

**Đây là một biến thể thực hành khác**, không dùng file đó thay server.p12 trong demo gốc nếu bạn còn muốn kiểm chứng ca C fail. Nếu đổi certificate server, cũng phải xuất/import đúng certificate hoặc CA vào truststore client tương ứng; chỉ sửa SAN trên một certificate mới mà client vẫn tin leaf cũ sẽ gây trust failure.

**SNI khác hostname verification:** Trong TLS ClientHello, SNI thường cho server biết tên host client muốn truy cập để server chọn certificate. Nhưng việc server chọn certificate không tự nói client chấp nhận nó; client vẫn kiểm tra trust chain và SAN. Với IP literal, một số implementations không gửi SNI giống khi URL chứa DNS name; đừng dựa vào SNI để bỏ qua SAN check.

**Tên DNS sau proxy:** Nếu client kết nối tới proxy, host cần verify thường là hostname của HTTPS origin theo URL, không phải tự động hostname của proxy hop; xem tài liệu proxy/TLS mode cụ thể để tránh lẫn các kết nối.

## 12. Phân biệt server trust với mTLS

Trong bài demo, **server dùng private key/certificate**, client xác minh server certificate. Server **không yêu cầu client certificate**. Đây là TLS server authentication thông thường.

**Mutual TLS (mTLS)** là yêu cầu khác: server cũng cần xác minh certificate của client. Điều này đòi hỏi:

- Client có **client keypair/certificate** trong client keystore và **KeyManagerFactory**.
- Server có **truststore** chứa CA/certificate phù hợp để xác minh client.
- Server cấu hình request/require client authentication qua SSLParameters (chẳng hạn needClientAuth) theo API.
- Client vẫn xác minh **server trust chain và hostname** như cũ.

**Thêm mTLS không thay thế hostname verification của client**; hai hướng xác thực độc lập. Một server có thể yêu cầu client cert đúng nhưng client vẫn phải từ chối server có hostname mismatch.

Không lẫn **server-keystore** với **server-truststore** trong mTLS. Server keystore chứa private key **của server**, còn server truststore chứa trust anchors để tin **client certificates**. Demo gốc không cần server truststore riêng vì không yêu cầu client certificate.

## 13. Triển khai trong môi trường thật: chính sách thay vì trust-all

Trong production, thường sử dụng một trong các mô hình:

1. **Public CA**: server certificate có chuỗi dẫn tới CA public được JDK/client tin cậy; hostname trong URL có SAN đúng. Không cần tự import server leaf vào mỗi client nếu truststore có root phù hợp.
2. **Private/enterprise CA**: cấp certificate từ CA nội bộ; client truststore có CA nội bộ được quản lý; rotate leaf mà không cần thay mọi truststore nếu CA unchanged.
3. **Pinning giới hạn**: một số hệ thống áp policy pin public key/certificate đặc biệt. Cần rotation, rollback và kiểm soát outage; **không** lấy việc import một leaf ngẫu nhiên từ network làm pinning an toàn.

Bộ yêu cầu thực tế:

- **Hostname/SAN** đúng theo service DNS.
- **Certificate chain** đầy đủ và được ký bởi CA được tin cậy.
- **Validity** và rotation trước expiration; đồng bộ đồng hồ hệ thống.
- **Server authentication EKU/key usage**, thuật toán/khóa đủ mạnh theo security policy.
- **TLS versions/cipher suites** phù hợp; không enable protocols yếu chỉ để test pass.
- **Truststore/keystore permissions** chặt chẽ, mật khẩu/secret management.
- **Load balancer/ingress certificate termination**: xác định TLS terminate ở đâu; nếu proxy terminate TLS, chứng chỉ mà Java client thấy có thể là của proxy-facing endpoint.
- **HTTP connect/request timeout** và lỗi DNS riêng; certificate verification không thay network retry policy.
- **Observability**: phân biệt certificate verify error, hostname mismatch, DNS, TCP, TLS protocol, HTTP status, application error.
- **Deployment tests**: xác minh certificate/SAN/truststore sau khi thay endpoint, CA hoặc chạy container image khác JDK.

**Không hard-code absolute path tới JDK cacerts** trong mọi môi trường. JDK/container images có thể khác nhau; dùng cấu hình chuẩn, per-client SSLContext hoặc secrets/CA bundle được quản lý và test xác nhận.

## 14. Regression test nên tách các nguyên nhân

| Test | Thay đổi một điều kiện | Điều cần assert |
| --- | --- | --- |
| Baseline | Trust đúng, URL localhost | HTTP 200, body TLS_OK |
| Negative trust | Truststore chỉ có unrelated certificate, URL localhost | TLS handshake rejected |
| Negative hostname | Trust đúng, URL 127.0.0.1, cert chỉ DNS:localhost | TLS handshake rejected |
| SAN đúng cả IP và DNS | Cert mới có SAN DNS + IP và truststore được cập nhật | Cả hai URI có thể thành công |
| Certificate rotated | Server thay leaf, client vẫn chỉ tin leaf cũ | Trust path thất bại trừ khi đã cập nhật trust policy |
| CA truststore | Leaf được ký bởi private CA client tin | Pass nếu chain/identity/usage hợp lệ |
| Expired certificate | Kiểm thử dưới policy phù hợp | Không nên chấp nhận certificate hết hạn |
| Wrong port | Server chưa bind | Connection refused/timeout, không phải hostname mismatch |
| Plain HTTP trên TLS port | Sai scheme/protocol | Lỗi protocol trước HTTP response mong đợi |
| Truststore password sai | Sai mật khẩu file PKCS12 | Lỗi nạp keystore trước network |
| Client certificate required | Server mTLS needClientAuth nhưng client không có keypair | Handshake fail theo server policy |

**Không kiểm thử negative hostname bằng cách vừa đổi truststore vừa đổi URL**: khi có nhiều lỗi đồng thời, exception đầu tiên có thể che lỗi thứ hai. Demo gốc tách hai điều kiện để thấy rõ trust và name.

### Kiểm thử an toàn khi chạy CI

- Sinh certificate/keypair vào thư mục temporary của job, không commit private key.
- Dùng loopback **127.0.0.1** và port 0, không expose server công khai.
- Dùng cert có **thời hạn ngắn**; không làm production phụ thuộc test certificate.
- Chạy **java -Djava.net.preferIPv4Stack=true** để tránh khác biệt localhost IPv4/IPv6 trong fixture này.
- Không assert full exception message; assert loại lỗi/contract như SSLHandshakeException.
- Có connect/request timeouts để test không treo vô hạn.
- Dọn hết fixtures sau khi job kết thúc.
- Không import certificate thử nghiệm vào **cacerts toàn máy** hay thay system-wide truststore chỉ vì test.

## 15. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| Chỉ đặt CN=localhost, bỏ SAN | Client HTTPS hiện đại dựa vào SAN | Cấp DNS SAN rõ ràng |
| Truy cập bằng 127.0.0.1 với chỉ DNS SAN localhost | IP identity không match DNS SAN | Dùng localhost hoặc cấp IP SAN đúng |
| Tin server.cer nhưng nghĩ mọi hostname đều được phép | Trust và hostname độc lập | Luôn kiểm tra endpoint identity |
| Dùng trust-all để “fix PKIX” | Cho phép MITM/cert giả | Import CA/cert đã xác minh |
| Disable hostname verification | Cho phép server sai tên | Sửa URI hoặc certificate |
| Copy server.p12 sang client-truststore | Lộ private key | Export public cert, import certificate |
| Nhầm javax.net.ssl.keyStore với trustStore | Client không tin server | Cấu hình trust anchors đúng |
| Thử GET rồi bắt HTTP 500 khi handshake fail | Chưa có HTTP response | Phân loại SSLHandshakeException |
| Tin rằng DNS localhost thành IP nên SAN IP không quan trọng | TLS so host trong URI | SAN đúng DNS/IP type |
| Dùng certificate đã hết hạn từ lần chạy trước | Handshake fail không đúng lý do cần test | Tạo fixtures mới, kiểm tra validity |
| Không kiểm tra fingerprint khi import | Có thể tin cert sai nguồn | Verify ngoài băng/trust channel |
| Cài cert test vào JDK cacerts để mọi app đều tin | Tăng phạm vi trust vô ý | Per-client SSLContext |
| Dùng cùng một truststore sai trong hai negative tests | Không phân biệt trust vs name | Mỗi test chỉ đổi một điều kiện |
| Xóa timeout vì test network chậm | Hangs khó chẩn đoán | Timeout phù hợp và logs có kiểm soát |
| Dùng URL host 127 nhưng server chỉ bind IPv6 | TCP fail trước TLS | Chọn đúng bind/resolution, ưu tiên IPv4 cho fixture |
| Dựa vào full text exception message | Provider/JDK khác nhau | Dùng exception class, cause chain và cert metadata |
| Dùng HttpsServer fixture như server production | Thiếu auth/rate limit/hardening | Dùng server/framework được bảo trì cho production |

## 16. Bài tập mở rộng

1. Giải thích sự khác nhau giữa **server keystore** và **client truststore**; private key nằm ở đâu?
2. Khi client tin đúng certificate nhưng URL host sai, vì sao handshake vẫn thất bại?
3. Vì sao **https://localhost** và **https://127.0.0.1** là hai TLS endpoint identities khác nhau?
4. Certificate chỉ có **SAN DNS:localhost** thì những ca nào trong A/B/C phải pass/fail?
5. Tạo certificate có thêm **IP:127.0.0.1 SAN**, xuất public cert và nhập vào truststore mới. Dự đoán kết quả khi dùng URL IP.
6. Đọc **keytool -list -v** để xác nhận fingerprint/issuer/subject/SAN/EKU. Không nhầm CN và SAN.
7. Bỏ client-trusted.p12 khỏi chương trình, cho HttpClient dùng default truststore. Trên máy chưa tin demo cert, lỗi dự kiến ở tầng nào? Vì sao không tuyệt đối dựa vào môi trường mặc định để assert?
8. Giải thích vì sao truststore có unrelated certificate là negative case mạnh hơn việc sửa đồng thời trust và hostname.
9. Trong **sendAsync**, SSLHandshakeException có thể được bọc bởi kiểu CompletableFuture exception nào?
10. Thử chuyển HttpsServer bind sang 127.0.0.1 trong khi JVM ưu tiên IPv6 cho localhost. Một connect refusal khác TLS name mismatch ra sao?
11. Tại sao import certificate không rõ nguồn nguy hiểm, dù hết lỗi PKIX?
12. Phân biệt **certificate validity error** với **hostname mismatch**, **trust chain failure**, **DNS failure** và **HTTP 503**.
13. Nêu điều kiện cần để server yêu cầu **mTLS client authentication**; vì sao mTLS không miễn hostname verification?
14. Thiết kế test CI sinh certs ngắn hạn, chạy loopback, không commit private key và không sửa cacerts toàn máy.
15. Trong môi trường ingress proxy, certificate nào được Java client nhìn thấy? Phân biệt TLS client→ingress và ingress→backend.
16. Một service đổi DNS host từ api-old.example sang api-new.example nhưng vẫn dùng certificate chỉ có SAN api-old.example. Cần sửa truststore hay certificate/URI?
17. Nếu server certificate được rotate nhưng client pin trực tiếp leaf cũ, điều gì xảy ra? Khi nào tin CA nội bộ sẽ giúp rotation?
18. Viết error mapper phân biệt IOException do connect failure, SSLHandshakeException do TLS, HttpResponse 404 và HttpResponse 503; không bịa status HTTP khi chưa có response.

## 17. Checklist kết thúc bài

- [ ] Server HttpsServer dùng **private key** trong server.p12 và certificate có SAN DNS:localhost?
- [ ] Client truststore **chỉ chứa public certificate**, không chứa private key server?
- [ ] Mật khẩu changeit chỉ dùng tạm cho test, không dùng production?
- [ ] Client tạo TrustManagerFactory/SSLContext từ đúng PKCS12?
- [ ] Không tắt certificate validation hoặc hostname verification?
- [ ] Ca A trusted + localhost nhận **200 TLS_OK**?
- [ ] Ca B unrelated truststore + localhost bị **SSLHandshakeException**?
- [ ] Ca C trusted + 127.0.0.1 (thiếu IP SAN) bị **SSLHandshakeException**?
- [ ] Không nhầm hai ca handshake failures thành HTTP 4xx/5xx?
- [ ] JDK 17 source biên dịch bằng javac --release 17?
- [ ] Server chỉ bind loopback và dùng dynamic port?
- [ ] Có connect/request timeouts và cleanup fixture?
- [ ] Đã xem SAN/fingerprint/validity bằng keytool?
- [ ] Có phân biệt URI hostname, DNS resolution, SNI và SAN?
- [ ] Không sửa global cacerts/truststore ngoài scope test?
- [ ] Biết xử lý CA rotation/mTLS/ingress khác demo self-signed?

**Tổng kết:** một HTTPS client đúng phải vừa **tin cậy certificate chain** vừa **xác minh tên máy trong URL phù hợp SAN**. Với cùng server certificate SAN DNS:localhost, client có truststore đúng gọi localhost sẽ nhận HTTP 200; truststore khác sẽ bị từ chối do **trust path**; còn truststore đúng nhưng gọi 127.0.0.1 sẽ bị từ chối do **hostname/IP SAN mismatch**. Cách giải quyết là cấu hình **certificate, trust anchor và URI identity đúng**, không phải bỏ xác thực TLS.

### Nguồn tham khảo

- [Java SE 17: HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html)
- [Java SE 17: HttpClient.Builder.sslContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html)
- [Java SE 17: SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html)
- [Java SE 17: KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html)
- [Java SE 17: TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html)
- [Java SE 17: KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html)
- [Java SE 17: HttpsServer](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsServer.html)
- [Java SE 17: HttpsConfigurator](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.httpserver/com/sun/net/httpserver/HttpsConfigurator.html)
- [Java keytool command reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html)
- [RFC 5280 — PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 6125 — Service Identity Verification](https://www.rfc-editor.org/rfc/rfc6125)
- [RFC 2818 — HTTP Over TLS](https://www.rfc-editor.org/rfc/rfc2818)
