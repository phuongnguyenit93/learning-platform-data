# Bảo vệ kênh vận chuyển trong Java Core Logging

## Mục tiêu học tập

Bài học thuộc nhóm **Bảo mật logging**, với chủ đề **Bảo vệ kênh vận chuyển**. Một log event có thể chứa tên dịch vụ, URL, mã lỗi, trace ID, đường dẫn nội bộ, dữ liệu truy cập hoặc thông tin nghiệp vụ. Ngay cả khi ứng dụng không cố ý ghi secret, nội dung exception và metadata trong log vẫn có thể tiết lộ kiến trúc, tài khoản hay dữ liệu nhạy cảm. Vì vậy, đường đi của log từ Java đến hệ thống lưu trữ cần được bảo vệ như một luồng dữ liệu có giá trị.

Sau bài học, bạn có thể:

- Liệt kê các **hop** trong logging pipeline và xác định hop nào có thể bị nghe lén, giả mạo hoặc chỉnh sửa dữ liệu.
- Giải thích vai trò của **TLS**, **mTLS**, kiểm tra tên máy chủ, CA/truststore, client certificate, quyền truy cập và mã hóa trong quá trình vận chuyển.
- Phân biệt HTTPS/OTLP qua TLS, syslog qua TLS, kết nối TCP thông thường và UDP không mã hóa.
- Áp dụng Java 17 JSSE/HttpClient theo nguyên tắc xác thực máy chủ; nhận diện các cấu hình nguy hiểm như “trust all certificates” hoặc tắt hostname verification.
- Thiết kế luồng log chịu lỗi với timeout, retry, buffering, backpressure và chính sách khi không thể thiết lập kênh an toàn.
- Kiểm thử từ JVM tới collector, kiểm tra rotation/revocation của chứng chỉ, và xác minh rằng không có đường gửi log bí mật qua kênh không được duyệt.

**Điểm chính:** Có TLS ở một kết nối **không** có nghĩa toàn bộ đường vận chuyển log được bảo vệ. Phải xác định từng kết nối, bên nào được xác thực, khóa được lưu ở đâu và chuyện gì xảy ra khi kết nối an toàn thất bại.

## 1. Kênh vận chuyển log nằm ở đâu?

Một kiến trúc phổ biến:

```text
        Java application (Logback / Log4j 2 / JUL)
                           |
                    [A] stdout / file
                           |
                 container runtime / host
                           |
                    log agent / shipper
                           |
                    [B] TLS / mTLS
                           |
                    log collector
                           |
                    [C] TLS / mTLS
                           |
                gateway / broker / backend
                           |
                    [D] internal link
                           |
                    storage / index / query
```

Không phải ứng dụng nào cũng đi qua stdout, file và agent. Có ứng dụng gửi trực tiếp qua HTTP/gRPC/TCP tới collector; có ứng dụng ghi ra Kafka hay dùng forwarder tại host. Mỗi kiến trúc có một tập hop riêng.

| Hop | Dữ liệu di chuyển thế nào? | Câu hỏi bảo mật |
| --- | --- | --- |
| **A. JVM → stdout/file** | Ghi vào stream, pipe hoặc filesystem cục bộ | Ai có thể đọc file/pipe? Runtime/host có cô lập process và giới hạn quyền không? |
| **B. Agent → collector** | Qua mạng nội bộ/VPC/Internet | Có TLS? Agent xác thực đúng collector? Collector có xác thực agent không? |
| **C. Collector → backend** | HTTP, gRPC, TCP/TLS hoặc broker | Có mã hóa và kiểm tra endpoint ở hop tiếp theo hay chỉ tin vào mạng nội bộ? |
| **D. Internal/storage** | Các dịch vụ và kho lưu trữ khác | Có kênh bảo vệ khi vượt ranh giới tin cậy? Có phân quyền và mã hóa lưu trữ riêng không? |

Nếu Java ghi trực tiếp vào `https://collector...` thì ứng dụng Java chịu trách nhiệm cấu hình HTTP client/TLS. Nếu Java chỉ ghi stdout và agent mới gửi qua mạng, **TLS tại agent** mới là lớp mã hóa cho hop ra khỏi host. Không có ý nghĩa nói “bật TLS trong Logback” nếu thực tế Logback không thực hiện kết nối mạng nào.

Đường đi của log cần được vẽ cho **từng loại log**: ứng dụng, audit, security, access, exception, debug và các luồng bị chuyển riêng. Một log có thể đi qua nhiều tuyến (fan-out), mỗi tuyến cần được kiểm tra.

## 2. Mối đe dọa và mục tiêu bảo vệ

Kênh log không an toàn có thể đối mặt với:

1. **Nghe lén (eavesdropping):** bên có khả năng quan sát mạng đọc được message, trace ID hoặc nội dung sự cố.
2. **Giả mạo endpoint:** ứng dụng hoặc agent gửi log tới máy chủ giả do DNS, proxy, cấu hình endpoint hay certificate validation sai.
3. **Chỉnh sửa trong đường truyền:** event hoặc metadata bị thay đổi trước khi tới collector.
4. **Giả mạo nguồn gửi log:** bên không được phép gửi event giống dịch vụ thật, làm nhiễu điều tra hay giả mạo audit.
5. **Phát lại (replay):** event hợp lệ được gửi lại làm sai số đếm, gây hiểu nhầm về một giao dịch xảy ra hai lần.
6. **Gián đoạn kết nối:** lỗi TLS handshake, chứng chỉ hết hạn, network partition hoặc collector quá tải làm log chậm, mất hoặc chặn ứng dụng.

TLS được cấu hình đúng giúp **mã hóa, bảo vệ tính toàn vẹn của byte trong phiên truyền và xác thực server**; mTLS còn xác thực danh tính client bằng chứng chỉ khi hai bên cấu hình đúng. Nhưng TLS không tự giải quyết mọi nguy cơ:

- Không ngăn ứng dụng **ghi secret vào log ngay từ đầu**.
- Không tự bảo vệ log khi đã được giải mã tại proxy/collector hoặc khi nằm trong file/index.
- Không tự chứng minh event đến backend **đúng một lần**, được lưu bền vững hay không bị sửa sau khi lưu.
- Không thay thế **authorization**: client có chứng chỉ hợp lệ chưa chắc có quyền ghi mọi tenant/index.
- Không ngăn lạm dụng từ endpoint đã bị xâm nhập hoặc một client hợp lệ bị lộ khóa.

Vì vậy, bảo vệ kênh gồm cả **TLS/identity**, **kiểm soát quyền và tuyến**, **bảo mật key**, **xử lý lỗi** và **kiểm thử**.

## 3. TLS, HTTPS và mTLS: phân biệt chính xác

### 3.1. TLS bảo vệ một kết nối

TLS (Transport Layer Security) dùng cơ chế trao đổi khóa, xác thực endpoint và mã hóa có kiểm tra tính toàn vẹn để bảo vệ luồng truyền. Với kết nối Java → collector:

```text
Java client                   collector server
    |                              |
    |--- ClientHello ------------->|
    |<-- ServerHello / cert / ... -|
    | validate chain + hostname    |
    |<-- / --> handshake messages -|
    |========= encrypted data =====|
```

Đây là sơ đồ giản lược, **không phải thứ tự đầy đủ của mọi handshake TLS 1.2/1.3**. Việc xác thực máy chủ cần ít nhất hai loại kiểm tra:

- **Certificate chain/trust:** chứng chỉ server có dẫn về một trust anchor/CA được tin cậy, phù hợp mục đích và các điều kiện xác thực không?
- **Endpoint identity/hostname verification:** tên server mà client **định kết nối** có khớp tên trong chứng chỉ (thông thường là DNS Subject Alternative Name – SAN) không?

Một chứng chỉ có chữ ký từ CA tin cậy nhưng được cấp cho **máy chủ khác** không được coi là hợp lệ cho collector mong đợi. Tương tự, kết nối tới IP khi chứng chỉ chỉ chứa DNS name có thể thất bại hostname verification; nên dùng hostname ổn định và SAN đúng thay vì vô hiệu hóa kiểm tra tên.

TLS hiện đại thường dùng TLS 1.3 hoặc TLS 1.2 theo chính sách và khả năng tương thích của các bên. TLS 1.0/1.1 đã lỗi thời và không nên được bật chỉ để “kết nối cho xong”. Bộ mật mã, security provider và phiên bản giao thức thực tế phụ thuộc JVM, hệ điều hành, máy chủ và policy; đừng giả định mọi JDK 17 đều thương lượng cùng một cipher suite.

### 3.2. HTTPS không đồng nghĩa mTLS

- **HTTPS** = HTTP qua TLS. Client thông thường **xác thực server**. Dịch vụ có thể xác thực client riêng bằng token/API key, cookie hoặc cơ chế khác qua kênh đã mã hóa.
- **mTLS (mutual TLS)** = hai bên xác thực bằng chứng chỉ trong handshake: server xuất chứng chỉ cho client xác minh, và client trình chứng chỉ cho server xác minh. mTLS có thể dùng với HTTP/gRPC hoặc các giao thức được thiết kế chạy trên TLS.
- **Bearer token qua HTTPS** có thể bảo vệ token khi truyền, nhưng nếu token bị lộ bên ngoài hoặc được log lại, TLS không cứu được. mTLS không có nghĩa API không còn cần kiểm soát quyền.

Một collector có thể yêu cầu **cả mTLS lẫn authorization ở tầng ứng dụng**. Ví dụ: chỉ client identity của service A được ghi vào tenant A và không được gửi audit event sang tenant B. Chứng chỉ là bằng chứng danh tính; logic phân quyền là một quyết định khác.

### 3.3. Nơi kết thúc TLS cũng quan trọng

Ví dụ:

```text
Java --TLS--> load balancer --plaintext--> collector
```

Đường Java → load balancer được bảo vệ bằng TLS, nhưng đoạn load balancer → collector vẫn là plaintext. Nếu đoạn sau vượt ranh giới tin cậy, cần TLS/mTLS riêng hoặc một biện pháp cô lập được đánh giá rõ. Kết nối qua service mesh cũng phải xác định sidecar nào khởi tạo và kết thúc TLS, policy peer authentication, đường passthrough và các tuyến bypass.

**TLS là bảo vệ theo hop**. Với dữ liệu đặc biệt nhạy cảm cần bảo mật xuyên suốt ngay cả trước một số intermediate processors, có thể cần mã hóa payload ở tầng ứng dụng và quản lý khóa riêng; điều này làm phức tạp tìm kiếm/parse và không phải yêu cầu mặc định cho mọi log.

## 4. Chọn giao thức vận chuyển log phù hợp

Không phải mọi “TCP logging” đều được mã hóa. Cần phân biệt các trường hợp cụ thể:

| Giao thức/cách vận chuyển | Bảo vệ truyền tải | Điểm cần xác minh |
| --- | --- | --- |
| **HTTPS POST** tới ingest API | TLS nếu thực sự dùng `https://` và client xác minh chứng chỉ + hostname | CA/truststore, auth, redirect, timeout, payload schema và retry |
| **OTLP/HTTP qua HTTPS** | TLS giữa exporter và endpoint | Endpoint, trust, token hoặc mTLS, Content-Type/schema, response codes |
| **OTLP/gRPC qua TLS** | TLS cho kênh HTTP/2 gRPC | Channel credentials, server name, client identity, deadline |
| **Syslog TCP không TLS** | Không có bảo mật TLS chỉ nhờ TCP | Tránh gửi qua ranh giới mạng không tin cậy |
| **Syslog UDP** | Không có mã hóa hay bảo đảm giao nhận mặc định | Không thích hợp cho dữ liệu nhạy cảm trên mạng không tin cậy |
| **Syslog over TLS** | Có profile chuẩn hóa, ví dụ RFC 5425 | Trust chain, peer identity, framing và certificate policy |
| **Stdout/file tại host** | Không phải kết nối TLS từ JVM | Quyền host/container, agent, nơi chuyển qua mạng tiếp theo |
| **Message broker** | Tùy cấu hình của client và broker | TLS/mTLS, SASL/token nếu có, ACL topic, replication và storage |

Với OpenTelemetry, cần phân biệt **OTLP exporter configuration** và **OpenTelemetry Collector configuration**. Nếu app Java xuất OTLP, cấu hình exporter theo stack Java/instrumentation đang dùng; nếu app chỉ ghi log qua SLF4J và agent đọc stdout thì OTLP/TLS thường được cấu hình ở agent/collector, không phải ngay tại `logger.info`.

Ngoài mã hóa, hãy kiểm tra *protocol correctness*: dùng `https://` không tự tạo thành endpoint hỗ trợ OTLP. Một HTTP server chỉ chấp nhận OTLP protobuf/JSON theo định dạng quy định sẽ không hiểu một JSON log tùy ý chỉ vì cùng dùng đường `/v1/logs`. Tài liệu giao thức và hệ thống nhận là nguồn xác định payload/headers chính xác.

**Không xây giả định rằng “mạng nội bộ là an toàn tuyệt đối”.** Mạng nội bộ vẫn có rủi ro cấu hình sai, lateral movement, máy chủ bị chiếm quyền, packet capture hoặc truy cập chéo namespace/tenant.

## 5. Truststore, keystore, chứng chỉ và bí mật trong Java

### 5.1. Java JSSE kiểm tra máy chủ ra sao?

Java 17 cung cấp JSSE qua `javax.net.ssl`. Thành phần cần hiểu:

- **`SSLContext`:** cung cấp thiết lập TLS cho socket/HTTP client, bao gồm key managers và trust managers.
- **`TrustManagerFactory`:** tạo trust managers dựa trên truststore hoặc nguồn trust tương ứng.
- **`KeyManagerFactory`:** tạo key managers chứa danh tính client và private key (cần khi mTLS được cấu hình).
- **`KeyStore`:** cấu trúc lưu chứng chỉ/key, thường dùng dạng PKCS12; file truststore và keystore có mục đích khác nhau.
- **`SSLParameters`:** cho phép cấu hình các tham số TLS, gồm thuật toán xác minh danh tính endpoint trong một số client API.
- **`HttpClient`:** HTTP client của JDK 17 hỗ trợ HTTPS/TLS. Với cấu hình bình thường, phải để cơ chế kiểm tra certificate chain và server identity hoạt động; không bật cờ nội bộ tắt hostname verification.

**Truststore** chứa CA/chứng chỉ được phép tin cậy để xác minh **server**; **client keystore** trong mTLS chứa chứng chỉ client và private key tương ứng. Việc import chứng chỉ server chưa đủ nếu client vẫn không kiểm tra hostname; ngược lại tên server đúng không đủ nếu chain không đáng tin.

Trong một số môi trường doanh nghiệp, collector dùng private CA. Cần đưa **CA phù hợp** vào truststore của client hoặc agent, không thêm mọi chứng chỉ vào một truststore chung không kiểm soát. Khi thay CA hoặc rotate chứng chỉ, đảm bảo client và server có cửa sổ chuyển tiếp tin cậy và cơ chế reload/restart được kiểm thử.

### 5.2. Các mẫu cấu hình không an toàn phải tránh

Tuyệt đối không coi những cách sau là giải pháp production:

- `X509TrustManager` có `checkServerTrusted(...)` rỗng hoặc chấp nhận mọi certificate.
- `HostnameVerifier` luôn trả `true` hoặc tắt endpoint identification qua property nội bộ.
- Đổi endpoint từ `https://` sang `http://` để né lỗi certificate.
- Bật toàn bộ giao thức/cipher cũ để vượt handshake error mà không đánh giá nguy cơ.
- Đưa private key, truststore password, bearer token hoặc nội dung certificate nhạy cảm vào log.
- Cài đặt certificate hoặc trust anchor từ nguồn không xác minh và xem đó là biện pháp sửa nhanh.

Nếu handshake thất bại, hãy điều tra nguyên nhân thật: tên SAN không khớp, chain thiếu intermediate, CA chưa được tin cậy, chứng chỉ hết hạn, đồng hồ hệ thống sai, mTLS client certificate thiếu, key/cipher không tương thích hoặc proxy chuyển tuyến sai.

### 5.3. Cấp phát, lưu trữ và rotation

Chứng chỉ máy chủ và client nên có vòng đời quản trị rõ ràng: cấp phát, phân phối, kiểm tra thời hạn, cảnh báo trước hết hạn, rotation, thu hồi/quarantine khi lộ khóa và xóa danh tính không còn dùng. Private key phải được bảo vệ bằng quyền filesystem phù hợp, secret manager hoặc nền tảng cung cấp identity; không đóng vào Git repo hoặc Docker image dưới dạng plaintext.

Khi cần nhập mật khẩu vào runtime, tránh hard-code trong code/log và tránh đặt secret trong command-line arguments nếu hệ điều hành/monitoring có thể hiển thị tham số process. Một số môi trường dùng secret volume, file descriptor, service identity hoặc secret injection do platform quản lý; chọn phương án phù hợp chính sách tổ chức và kiểm tra file permission.

**Rotation test** phải bao gồm lúc hai bộ chứng chỉ cùng được chấp nhận, lúc chứng chỉ cũ hết hiệu lực, khi instance vẫn dùng connection pool cũ và khi app/agent reconnect. Việc thay file certificate trên đĩa **không tự bảo đảm** JVM hay collector đang chạy đã reload trust/key material; cơ chế hot reload phụ thuộc implementation.

## 6. Java 17 chạy độc lập: chính sách HTTPS-only và cấu hình TLS

Chương trình sau chỉ dùng JDK 17+, không cần server, thư viện bên thứ ba hay truy cập mạng. Nó thực hiện ba việc:

1. Kiểm tra một ingest endpoint có dùng **HTTPS**, có hostname và không chứa `userinfo`, query hay fragment theo **chính sách của ví dụ**.
2. Tạo `HttpClient` với `SSLContext` mặc định của JVM, yêu cầu endpoint identification algorithm `HTTPS`, connect timeout và **không tự động follow redirect**.
3. In trạng thái để kiểm chứng các quyết định cấu hình, nhưng **không gửi request**. Vì không có handshake, ví dụ **không chứng minh** server thật có certificate hợp lệ; việc đó cần integration test.

Quy tắc không chấp nhận query là lựa chọn bảo thủ để ngăn vô tình nhúng credential vào URL. Một API thực tế có thể dùng query hợp lệ; khi đó cần allowlist chặt các tham số và không bao giờ đặt token/bí mật trong URL. Tương tự, các endpoint không dùng HTTP, chẳng hạn syslog over TLS, cần một validator riêng.

Tạo file **`SecureLogTransportPolicyDemo.java`**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;

public class SecureLogTransportPolicyDemo {
    private static boolean allowed(String endpoint) {
        try {
            URI uri = URI.create(endpoint);
            return !uri.isOpaque()
                    && "https".equalsIgnoreCase(uri.getScheme())
                    && uri.getHost() != null
                    && !uri.getHost().isBlank()
                    && uri.getRawUserInfo() == null
                    && uri.getRawQuery() == null
                    && uri.getRawFragment() == null;
        } catch (IllegalArgumentException exception) {
            return false;
        }
    }

    private static void check(String label,
                              String url,
                              boolean expected) {
        boolean actual = allowed(url);
        if (actual != expected) {
            throw new IllegalStateException(label + " failed");
        }
        System.out.println(label + "=" + actual);
    }

    public static void main(String[] args) throws Exception {
        check("https_allowed",
                "https://collector.example.test/ingest", true);
        check("http_allowed",
                "http://collector.example.test/ingest", false);
        check("userinfo_allowed",
                "https://user:fake-pass@collector.example.test/ingest",
                false);
        check("query_allowed",
                "https://collector.example.test/ingest?token=fake",
                false);

        SSLParameters tls = new SSLParameters();
        tls.setEndpointIdentificationAlgorithm("HTTPS");

        HttpClient client = HttpClient.newBuilder()
                .sslContext(SSLContext.getDefault())
                .sslParameters(tls)
                .connectTimeout(Duration.ofSeconds(5))
                .followRedirects(HttpClient.Redirect.NEVER)
                .version(HttpClient.Version.HTTP_1_1)
                .build();

        System.out.println("hostname_policy="
                + tls.getEndpointIdentificationAlgorithm());
        System.out.println("redirect_policy="
                + client.followRedirects());
        System.out.println("requests_sent=0");
    }
}
```

Biên dịch và chạy:

```bash
javac SecureLogTransportPolicyDemo.java
java SecureLogTransportPolicyDemo
```

**stdout chính xác:**

```text
https_allowed=true
http_allowed=false
userinfo_allowed=false
query_allowed=false
hostname_policy=HTTPS
redirect_policy=NEVER
requests_sent=0
```

Giải thích quan trọng:

- `URI.create(...)` chỉ phân tích cú pháp URI; nó **không kết nối** hoặc xác minh chứng chỉ. Rule kiểm tra hostname/scheme là một lớp policy trước khi tạo kết nối, **không thay thế TLS handshake**.
- `SSLContext.getDefault()` lấy thiết lập trust mặc định đang có hiệu lực cho JVM. Ở doanh nghiệp, truststore của ứng dụng có thể khác truststore hệ điều hành; cần kiểm tra đúng nguồn trust được dùng.
- `SSLParameters#setEndpointIdentificationAlgorithm("HTTPS")` thể hiện yêu cầu xác minh danh tính endpoint cho cấu hình client. JDK HttpClient bình thường đã thực hiện xác minh HTTPS; không dùng bất cứ cờ “disable hostname verification” nào để né lỗi.
- `HttpClient.Redirect.NEVER` tránh việc tự động chuyển request log sang endpoint khác. Nếu hệ thống có redirect hợp lệ, phải xác minh endpoint mới với cùng chính sách thay vì theo dõi chuyển hướng mù.
- `connectTimeout` giới hạn **thời gian thiết lập kết nối**, không phải tổng thời gian mọi request hoặc thời gian chờ queue. Khi gửi request thật còn cần request timeout/deadline phù hợp.

Tên `collector.example.test` và token giả trong URL âm tính chỉ phục vụ kiểm tra policy; chúng không đại diện cho endpoint thực tế, và chương trình không thử đăng nhập hoặc chuyển dữ liệu ra ngoài.

**Ranh giới an toàn của ví dụ:** Dùng HTTPS URL hợp lệ **không chứng minh** collector đáng tin; cần handshake thật, certificate chain/hostname validation, authorization, policy theo hop và kiểm thử lỗi. Code cũng không thể phát hiện mọi proxy/redirect hoặc cấu hình JVM bị sửa theo cách nguy hiểm; đó là phần audit môi trường triển khai.

## 7. Tích hợp với truststore riêng và mTLS trong Java

Khi collector dùng CA nội bộ, ứng dụng Java có thể tạo `SSLContext` với truststore do tổ chức cấp. Dưới đây là **đoạn mã tích hợp**, không phải một chương trình độc lập: cần có file PKCS12 và mật khẩu nhận an toàn từ runtime, đồng thời phải kiểm tra quyền đọc file.

```java
// Trích đoạn trong lớp cấu hình: biến trustStorePath và
// trustStorePassword được cấp từ secret/config runtime.
KeyStore trustStore = KeyStore.getInstance("PKCS12");
try (InputStream input = Files.newInputStream(trustStorePath)) {
    trustStore.load(input, trustStorePassword);
}

TrustManagerFactory trustManagers = TrustManagerFactory.getInstance(
        TrustManagerFactory.getDefaultAlgorithm());
trustManagers.init(trustStore);

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, trustManagers.getTrustManagers(), null);

HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .followRedirects(HttpClient.Redirect.NEVER)
        .connectTimeout(Duration.ofSeconds(5))
        .build();
```

Các import cần thiết khi đặt đoạn trên trong lớp Java thật gồm `java.security.KeyStore`, `java.nio.file.Files`, `java.io.InputStream`, `javax.net.ssl.TrustManagerFactory`, `javax.net.ssl.SSLContext`, `java.net.http.HttpClient` và `java.time.Duration`. Khi dùng `HttpClient`, giữ nguyên hostname verification; nếu dùng `SSLSocket` trực tiếp, phải cấu hình endpoint identification đúng với giao thức và kiểm thử nó thực sự được áp dụng. Không tạo một trust manager “accept all” chỉ để chương trình kết nối được.

**Lưu ý truststore tùy biến:** Khi bạn cung cấp truststore riêng theo đoạn trên, JVM không tự động thêm toàn bộ các trust anchor mặc định vào truststore đó. Nếu ứng dụng cần kết nối nhiều loại endpoint, phải thiết kế phạm vi tin cậy có chủ đích, không thêm mọi CA tràn lan. Truststore path và password không được log.

Đối với **mTLS**, client còn cần một `KeyManagerFactory` được khởi tạo từ keystore chứa chứng chỉ client/private key. Khái niệm:

```java
// Trích đoạn bổ sung, cần các biến keyStore và keyPassword
// được tạo/lấy từ secret manager và cấu hình triển khai.
KeyManagerFactory keyManagers = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
keyManagers.init(keyStore, keyPassword);

SSLContext mutualTlsContext = SSLContext.getInstance("TLS");
mutualTlsContext.init(
        keyManagers.getKeyManagers(),
        trustManagers.getTrustManagers(),
        null);
```

Trong đoạn này, `keyStore` là một `KeyStore` đã được load phù hợp, `keyPassword` là `char[]` quản lý an toàn; nó là **đoạn tích hợp**, không độc lập biên dịch. Việc có client certificate **không** tự bảo đảm server yêu cầu mTLS, cũng không tự bảo đảm client được phép ghi vào tenant cụ thể. Phải kiểm thử bắt tay mTLS và kiểm tra authorization ở collector.

### Kết nối mạng thật cần thêm những gì?

Với HTTP collector thật, ngoài SSLContext và endpoint validation, cần:

- Gửi body đúng **giao thức/schema ingest** mà collector hỗ trợ, ví dụ OTLP/HTTP protobuf hoặc JSON theo OTLP spec, không tùy tiện gửi một đối tượng JSON bất kỳ.
- Có timeout/deadline, chính sách retry có giới hạn, tránh phát lại request gây duplicate không kiểm soát.
- Xác thực bằng token hoặc chứng chỉ theo policy; tuyệt đối không log `Authorization` header.
- Giới hạn batch size, kích thước payload, số kết nối đồng thời và buffer khi mạng chậm.
- Kiểm tra response status và acknowledgement semantics của sink; HTTP 2xx không đương nhiên là đã index/searchable hoặc durable.
- Dùng TLS tiếp cho collector → backend, nếu hop đó vượt vùng tin cậy cần bảo vệ.

## 8. Cấu hình ở logging framework và agent

Điểm cấu hình TLS phụ thuộc nơi thực hiện kết nối mạng. Không thể áp một thuộc tính chung `tls=true` cho mọi logger.

### 8.1. Khi ứng dụng chỉ ghi stdout/file

Nếu Logback hoặc Log4j 2 ghi local stdout, phần kết nối tới collector thường do Fluent Bit, Vector, OpenTelemetry Collector, Filebeat, Promtail hoặc agent được tổ chức sử dụng thực hiện. Lúc đó:

1. JVM phải giữ log có cấu trúc và tránh ghi dữ liệu nhạy cảm.
2. File/stdout/host được bảo vệ bằng quyền truy cập và policy container.
3. **Agent** phải dùng TLS/mTLS, trust bundle và auth phù hợp cho outbound.
4. Collector phải xác thực nguồn, phân quyền ghi theo tenant/service và định tuyến đúng backend.
5. Kiểm tra cả đoạn collector → storage; không coi bảo vệ agent → collector là hoàn thành toàn pipeline.

Tên agent ở trên là ví dụ công nghệ có thể gặp; khả năng TLS, trường config, cách reload certificate và chính sách retry phụ thuộc phiên bản. Đọc tài liệu chính thức của **công cụ thực sự được triển khai** thay vì sao chép một YAML của agent khác.

### 8.2. Khi appender/exporter gửi trực tiếp qua mạng

Với Logback SocketAppender, Log4j 2 SocketAppender, HTTP appender hoặc OpenTelemetry exporter, phải kiểm tra transport cụ thể:

- Socket qua TCP bình thường **không** có TLS nếu không dùng chế độ TLS tương ứng.
- Appender “SSL” hay “TLS” phải có cấu hình trust/hostname verification đúng; chỉ tạo socket TLS không đủ nếu bỏ qua kiểm tra identity.
- Exporter HTTP cần `https://` hoặc TLS tương ứng; exporter gRPC cần channel TLS credentials và peer name validation.
- Với async network appender, lỗi TLS/collector có thể làm queue đầy; cần xác định block/drop/spool/fallback.
- Khi dùng thư viện client riêng, kiểm tra redirect, proxy, DNS/SNI, certificate validation và nơi nạp credential.

**Không gửi trực tiếp log quan trọng ra một IP tuỳ ý** chỉ vì IP đó nằm trong VPC. Sử dụng DNS/identity phù hợp; nếu cần kết nối bằng IP, chứng chỉ cần chứa SAN dành cho địa chỉ IP và policy xác minh tương ứng.

### 8.3. Ví dụ chính sách theo hop

Giả sử một hệ thống có Java → stdout → collector agent → gateway → index:

```text
JVM / stdout:           host/container access control
Agent -> gateway:       TLS 1.2+/TLS 1.3, trusted CA, hostname check
Gateway -> collector:   mTLS, identity-based authorization
Collector -> backend:   TLS + service account permissions
Index / storage:        encryption at rest + access control + retention
```

Đây là **mẫu mục tiêu thiết kế**, không phải mô tả hạ tầng mặc định. Nếu gateway kết thúc TLS nhưng đi plaintext sang collector, phải ghi rõ ranh giới tin cậy của hop đó; không được điền “all TLS” vào checklist chỉ vì cổng ngoài là 443.

## 9. Xác thực danh tính và phân quyền nguồn gửi log

Một collector nhận log từ nhiều service/tenant không chỉ cần mã hóa kết nối. Nếu mọi client được quyền ghi vào mọi namespace, một client bị chiếm quyền có thể giả mạo hoặc làm nhiễu log của bên khác.

Có thể kết hợp:

- **mTLS client identity** gắn với service/workload cụ thể, certificate subject/SAN và policy xác thực tại gateway.
- **Token/API key** được cấp phạm vi tối thiểu và truyền qua HTTPS, rotate định kỳ.
- **ACL/routing policy** buộc danh tính service A chỉ gửi log vào index/tenant A; không tin vào trường `tenant_id` do client tự khai báo để quyết định quyền.
- **Rate limit/quota theo identity** để giảm log spam hoặc DoS vào collector.
- **Network policy/firewall** giới hạn nơi được kết nối tới collector, chỉ mở cổng cần thiết.
- **Audit của thay đổi cấu hình** TLS, truststore, token, route, collector và index permissions.

Nếu cả mTLS và token được dùng, phải có quy tắc rõ về vai trò từng lớp và quy trình thu hồi. Chẳng hạn revoke một client certificate mà token của client vẫn hoạt động qua tuyến khác thì có thể vẫn còn lối truy cập ngoài ý muốn.

**Không dựa vào source IP đơn lẻ để xác thực service.** NAT, proxy, workload di động và hạ tầng container có thể làm IP thay đổi hoặc được dùng chung. Network segmentation là biện pháp bổ trợ, không thay thế certificate identity và authorization khi rủi ro yêu cầu.

## 10. Timeout, retry và độ tin cậy khi TLS/collector gặp lỗi

Một kênh được bảo vệ vẫn có thể gián đoạn. TLS handshake có thể thất bại vì chứng chỉ hết hạn, CA chưa được tin, sai hostname, mTLS client identity không hợp lệ hoặc bất đồng phiên bản. Khi đó **không được tự hạ cấp về plaintext** để “giữ log chạy”.

Cần chọn chính sách thất bại:

| Sự cố | Hành vi an toàn mong muốn | Tác động phải đo |
| --- | --- | --- |
| Server certificate không được tin cậy | Từ chối kết nối; cảnh báo cấu hình/identity | Log delivery fail, queue/backlog tăng |
| Hostname không khớp SAN | Từ chối kết nối, không bỏ qua xác minh | Kết nối không thành công |
| Client mTLS certificate hết hạn | Từ chối handshake; kích hoạt rotation/runbook | Exporter retry và log pipeline lag |
| Collector timeout/network partition | Bounded retry/backoff; buffer trong ngân sách | Delivery latency, memory, drop, disk spool |
| Queue đầy | Block hoặc drop theo policy đã duyệt; tách critical events | Ảnh hưởng request p99 hoặc số log mất |
| Payload/authorization lỗi 4xx | Xác định là lỗi cấu hình/payload; không retry vô hạn | Số event bị từ chối và nguyên nhân |
| Lỗi tạm thời 5xx/429 | Retry có backoff/jitter theo hướng dẫn hệ thống nhận | Throughput, retry volume, duplicate risk |
| Agent/host crash | Buffer trong RAM có thể mất; disk spool nếu có phải được quản lý bền vững và bảo vệ | Event counts, recovery, local data risk |

**Không phải mọi 4xx hay 5xx đều có cùng semantics.** Ví dụ token hết hạn, malformed payload, rate limit và lỗi server tạm thời cần chính sách khác nhau. Hãy dựa vào tài liệu API/collector và thông tin retry có sẵn; tránh retry lại những request chắc chắn không thể thành công.

### 10.1. Backpressure có thể làm chậm cả ứng dụng

Nếu producer ghi log nhanh hơn sink có thể gửi qua TLS, queue bounded sẽ tích tụ. Khi đầy, logging framework có thể block luồng nghiệp vụ, drop event hoặc fallback synchronous. Điều đó tạo tradeoff giữa **request latency** và **độ đầy đủ log**.

Một phép thử cần đo đồng thời:

- `logger_call_latency` p50/p95/p99 và latency endpoint.
- `queue_depth`, `enqueue_block_time` và high-water mark.
- `sent_events`, `failed_events`, `dropped_events`, `retried_events`.
- `tls_handshake_failures` theo loại lỗi, không log nội dung khóa/token.
- `collector_ingest_lag` và event-to-searchable latency.

Không thể kết luận “TLS làm ứng dụng chậm” chỉ từ việc bật HTTPS. Chi phí handshake, connection reuse, batch size, encode, downstream throttle và network RTT đều có thể đóng góp; cần đo từng giai đoạn trên workload đại diện. Connection pooling và batch có thể giảm overhead, nhưng phải hạn chế số lượng connection và thời gian giữ log trong RAM.

### 10.2. Gửi lại có thể tạo log trùng

Khi client gửi event và timeout trước khi nhận acknowledgement, không chắc server đã tiếp nhận hay chưa. Retry có thể tạo hai bản ghi. Nếu hệ thống cần dedup, dùng `event_id` hoặc cơ chế theo giao thức/sink hỗ trợ, nhưng không giả định mọi collector đều cung cấp “exactly once”. Một trace ID có thể thuộc nhiều log event; nó không đủ làm khóa dedup từng event.

Với audit hoặc sự kiện pháp lý yêu cầu bảo đảm tính toàn vẹn, thiết kế durable message path/transactional outbox hoặc audit store riêng theo yêu cầu. Async queue trong bộ nhớ cộng TLS **không** tương đương bảo đảm không mất dữ liệu.

### 10.3. Disk spool cũng cần bảo vệ

Khi agent buffer log ra disk để chờ mạng hồi phục, dữ liệu nhạy cảm **tồn tại ở trạng thái lưu trữ**. Cần quyền filesystem tối thiểu, giới hạn dung lượng, retention, encryption at rest khi phù hợp và cleanup sau khi gửi thành công. Một giải pháp chỉ mã hóa TLS outbound nhưng để plaintext spool chứa token trên máy dùng chung vẫn chưa đáp ứng yêu cầu bảo mật toàn diện.

## 11. Kiểm thử TLS/mTLS và đường vận chuyển end-to-end

Kiểm thử trên staging hoặc môi trường kiểm soát tương đương, với log giả không chứa secret thật. Xác định rõ expected policy trước khi thử.

### 11.1. Ma trận kiểm thử bắt buộc

| Mã | Tình huống | Kỳ vọng |
| --- | --- | --- |
| T1 | Collector có chứng chỉ hợp lệ, chain được tin và SAN khớp | TLS kết nối thành công; event thử đến sink được phép |
| T2 | Self-signed/CA chưa tin | Client từ chối; không tự fallback HTTP |
| T3 | Chứng chỉ tin cậy nhưng SAN khác hostname | Client từ chối do endpoint identity mismatch |
| T4 | Certificate hết hạn/chưa có hiệu lực | Kết nối thất bại theo policy xác thực |
| T5 | mTLS server bắt buộc client cert, client thiếu chứng chỉ | Handshake/auth thất bại, không gửi log |
| T6 | Client cert hợp lệ nhưng không được phép ghi tenant này | Bị từ chối authorization dù TLS thành công |
| T7 | Collector unreachable/timeouts | Retry/backoff/buffer/drop đúng chính sách; app không bị treo vô hạn ngoài thiết kế |
| T8 | TLS termination tại gateway | Xác minh hop gateway → collector cũng có bảo vệ khi cần |
| T9 | Tự thay đổi endpoint sang HTTP | Config validation hoặc policy chặn; không chuyển log nhạy cảm |
| T10 | Rotate server CA/client certificate | Có giai đoạn chuyển đổi; reconnect thành công; không mở trust-all |
| T11 | Đường stdout/file → agent → backend | Event có mặt ở đúng destination, không lọt index ngoài phạm vi |
| T12 | Burst log / queue full | Có số liệu block/drop, không được gọi đây là thành công hoàn toàn |

**Cách đo đúng:** Tạo `test_event_id` riêng cho một log test và ghi nhận mốc phát sinh. Tìm ở sink/collector/backend theo ID đó và theo environment/tenant, xác minh cả nội dung cần thiết và **không có mặt** ở sink sai. Nếu pipeline eventual-consistent, dùng polling có deadline rồi kết luận, không đòi event xuất hiện tức thời.

### 11.2. Công cụ và tín hiệu hữu ích

- `keytool -list -v -keystore ...` có thể giúp kiểm tra certificate/truststore; chạy với quyền tối thiểu và không đưa password vào đoạn log chia sẻ. `keytool` có sẵn trong JDK, cú pháp/format output tùy phiên bản.
- `openssl s_client -connect host:port -servername host -verify_return_error` hữu ích khi OpenSSL sẵn có để khảo sát handshake, SNI và chain. Việc công cụ kết nối thành công **không** chứng minh cấu hình trust của Java client giống OpenSSL, và không chứng minh authorization của collector.
- `curl` với URL HTTPS và CA bundle phù hợp có thể dùng để thử HTTP endpoint đã được cấp quyền, nhưng không đưa bearer token vào log shell/verbose output và không dùng `-k`/`--insecure` để “test thành công”.
- Có thể bật debug JSSE/JVM ở môi trường kiểm soát để xem handshake/cert path failure, nhưng log TLS debug có thể rất nhiều và chứa thông tin nhạy cảm về kết nối. Chỉ dùng theo quy trình được phép và tắt sau điều tra.
- JVM metrics, appender/agent status, collector receiver/exporter metrics, gateway logs và index counters giúp xác định hop lỗi thay vì chỉ nhìn application log.

Nếu endpoint dùng mTLS, client thử nghiệm phải có đúng danh tính và certificate được phép. Đừng suy ra “server không hoạt động” từ việc một client test không mang chứng chỉ bị từ chối.

### 11.3. Kiểm tra hostname và SNI

Nhiều hệ thống dùng virtual hosting, load balancer hoặc nhiều certificate trên một IP. **SNI (Server Name Indication)** giúp client chỉ định tên máy chủ khi bắt tay TLS để server chọn cấu hình/certificate thích hợp; **hostname verification** là bước client xác minh server certificate tương ứng tên mong đợi. Hai khái niệm liên quan nhưng không thay thế nhau.

Khi kết nối tới IP thay vì hostname, SNI và SAN có thể không tương thích với chứng chỉ, tùy stack. Hướng sửa đúng thường là cấu hình hostname, DNS và SAN phù hợp; không tắt hostname verification. Khi qua proxy/load balancer, kiểm tra chính xác tên nào được TLS client xác thực ở mỗi đoạn.

## 12. Troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `PKIX path building failed` | CA/intermediate thiếu, truststore khác dự kiến | Xác minh chain, truststore đang load và CA đúng |
| `No subject alternative DNS name matching` | Endpoint hostname không khớp SAN | Sửa DNS/SAN/certificate; không disable hostname verification |
| TLS handshake fail sau rotation | Cert mới chưa được tin, key/client cert cũ, process chưa reload | Kiểm tra giai đoạn rollout, reload/restart và expiry |
| Client tới HTTP được nhưng HTTPS không được | Sai listener/port/certificate/proxy hoặc protocol | Kiểm tra đúng endpoint TLS; không hạ cấp mặc định |
| Handshake thành công nhưng HTTP 401/403 | Token/ACL/tenant permission hoặc client identity chưa được cấp quyền | Kiểm tra auth và authorization; TLS không thay thế ACL |
| Log tới gateway nhưng không có ở collector | Hop tiếp theo bị chặn, TLS termination/routing sai | Truy vết theo event ID và gateway/collector metrics |
| App chậm khi collector mất kết nối | Async queue đầy hoặc synchronous network appender block | Đo caller latency, queue policy, retry/buffering |
| Log có trong file local nhưng chưa tìm thấy ở backend | Agent/network/ingest/index gặp lỗi hoặc đang lag | Xem từng hop và eventual consistency |
| Có trùng event sau retry | Timeout không rõ server đã nhận hay chưa | Theo dõi event ID, dedup theo khả năng sink |
| Client cert hợp lệ nhưng ghi sai tenant | Không có/thiếu authorization theo client identity | Enforce policy phía collector, test negative |
| Nhiều handshake, CPU cao | Không reuse connection, reconnect mỗi log hoặc collector reset | Dùng batching/connection pooling, đo lại |
| Một service không kết nối được qua proxy | Proxy/TLS inspection khác trust policy, SNI sai | Làm rõ trust boundary, kiểm tra certificate và đường network |
| Disk spool phình to | Collector down kéo dài, retry không drain | Alert queue/spool, giới hạn dung lượng và recovery plan |
| TLS đã bật nhưng kiểm toán phát hiện plaintext | Đường fallback/bypass hoặc hop sau termination chưa mã hóa | Vẽ lại topology, enforce policy và kiểm thử âm |

**Không xử lý sự cố TLS bằng trust-all hoặc `http://` tạm thời trên production.** Nếu một chứng chỉ bị hết hạn, cần khôi phục certificate/trust đúng quy trình, quan sát backlog và khẳng định không có log bị rò vào tuyến khác.

## 13. Bảo vệ dữ liệu bên trong log song song với bảo vệ kênh

TLS giúp ngăn nhiều nguy cơ trong quá trình truyền, nhưng thông điệp sau khi giải mã vẫn cần được quản trị:

1. **Không log secret:** password, API key, bearer token, private key, cookie phiên, toàn bộ request/response body có dữ liệu nhạy cảm. Kiểm tra cả exception messages và HTTP interceptors.
2. **Structured logging và masking:** dùng encoder có escape đúng, giảm log injection; loại/redact dữ liệu cá nhân theo chính sách trước khi gửi.
3. **Tách log theo mức độ nhạy cảm:** audit/security có thể cần sink, retention và quyền truy cập khác log debug. Định tuyến đúng cả trên collector/index.
4. **RBAC/ACL tại backend:** ai được đọc hoặc export log? TLS client identity của agent không tự giới hạn quyền người dùng ở dashboard.
5. **Retention và xóa dữ liệu:** dữ liệu khi đã được lưu phải chịu chính sách at-rest, lifecycle và audit truy cập riêng.
6. **Không leak diagnostics:** thông báo lỗi handshake phải đủ để chẩn đoán loại lỗi nhưng không in token, private key hoặc raw log payload.

Mỗi lần bật debug HTTP/TLS trên staging cần dữ liệu thử an toàn và thời gian giới hạn. Kênh transport có TLS không làm việc đẩy secret vào collector trở nên chấp nhận được.

## 14. Checklist triển khai production

Trước khi duyệt một kênh vận chuyển log, trả lời:

- [ ] Đã vẽ đầy đủ đường log từ Java, stdout/file/agent, collector đến backend cho từng loại event chưa?
- [ ] Mọi hop vượt ranh giới tin cậy có TLS/mTLS hoặc biện pháp bảo vệ được đánh giá chưa?
- [ ] Client có kiểm tra **certificate chain và hostname/SAN**, không dùng trust-all/disable verification?
- [ ] Có quy định rõ client identity, token/certificate, authorization và quyền ghi theo tenant/service?
- [ ] Truststore/keystore và private key được phân phối bằng cơ chế quản lý bí mật phù hợp, không commit vào repository?
- [ ] Có theo dõi expiry, rotation, thu hồi và tình trạng chưa reload certificate?
- [ ] Collector/API có timeout/deadline, retry/backoff, bounded buffering và giới hạn payload?
- [ ] Khi TLS handshake thất bại, hệ thống **không tự downgrade** sang plaintext hay route sang sink không được duyệt?
- [ ] Đã phân biệt policy filtering, queue overflow, sink write failure và ingest lag?
- [ ] Có test âm với certificate sai CA/SAN, thiếu mTLS client identity, sai tenant và collector không sẵn sàng?
- [ ] Có test event ID xuyên suốt để khẳng định log tới đúng index và không xuất ở đích không được phép?
- [ ] Đã kiểm tra spool/temporary files, retention, access control và encryption at rest theo yêu cầu?
- [ ] Có kế hoạch rollback và runbook khi certificate rotation hoặc collector outage gây mất log/ứng dụng chậm?

**Tiêu chí hoàn thành:** Bạn giải thích được TLS bảo vệ hop nào, nắm được xác minh chứng chỉ và danh tính endpoint trong Java, phân biệt TLS/mTLS/auth, lập được kế hoạch kiểm thử tích cực và tiêu cực cho đường log, và chứng minh không có fallback sang plaintext khi kênh an toàn gặp lỗi.

## 15. Câu hỏi tự kiểm tra

1. Java đã dùng `https://collector.example`; vì sao vẫn cần xem đường collector → backend?
2. Một certificate có CA hợp lệ nhưng SAN không chứa tên collector có được chấp nhận không? Vì sao?
3. Khi dùng mTLS, collector có tự động biết tenant nào được phép ghi từ chứng chỉ client không?
4. Tại sao `SSLContext.getDefault()` có thể dùng tập CA khác với công cụ OpenSSL trên máy?
5. Kênh TLS bị lỗi sau khi server certificate rotate: nên điều tra gì thay vì dùng trust-all?
6. Gửi log trực tiếp bằng HTTP client và ghi log ra stdout để agent ship có điểm cấu hình TLS khác nhau thế nào?
7. Tại sao retry sau timeout có thể tạo bản ghi log trùng, dù TLS kết nối an toàn?
8. Nếu queue đầy khi collector ngừng hoạt động, bạn chọn gì để cân bằng request latency và log loss?
9. Một chứng chỉ client hợp lệ nhưng không được phép ghi vào index audit: lỗi nằm ở TLS hay authorization?
10. Vì sao một test với `requests_sent=0` không thể chứng minh certificate của server thật hợp lệ?

## Tài liệu tham khảo

- [RFC 8446 — TLS 1.3](https://www.rfc-editor.org/rfc/rfc8446) — giao thức TLS phiên bản 1.3.
- [RFC 8996 — Deprecating TLS 1.0 and TLS 1.1](https://www.rfc-editor.org/rfc/rfc8996) — loại bỏ phiên bản TLS lỗi thời.
- [RFC 5425 — Transport Layer Security (TLS) Transport Mapping for Syslog](https://www.rfc-editor.org/rfc/rfc5425) — syslog over TLS.
- [Java SE 17 — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html) — cấu hình TLS của JSSE.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html) — tham số TLS và endpoint identification.
- [Java SE 17 — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html) — HTTPS client, timeout và redirect.
- [Java SE 17 — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html) — quản lý trust.
- [OpenTelemetry Protocol (OTLP)](https://opentelemetry.io/docs/specs/otlp/) — vận chuyển telemetry và các yêu cầu giao thức.
- [OWASP Transport Layer Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Transport_Layer_Security_Cheat_Sheet.html) — khuyến nghị triển khai TLS.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html) — bảo vệ nội dung và quy trình logging.
