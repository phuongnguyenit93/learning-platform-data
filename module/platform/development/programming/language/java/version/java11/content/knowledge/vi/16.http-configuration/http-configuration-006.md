# `SSLContext`, `SSLParameters` và chứng chỉ khi cấu hình HTTPS (Java 11+)

## 1. Mục tiêu của bài học

Khi dùng `java.net.http.HttpClient` để gọi một URL `https://...`, Java thực hiện **TLS handshake** trước khi trao đổi các thông điệp HTTP trên kết nối bảo mật. Ở bước này, client cần xác minh danh tính máy chủ, thỏa thuận phiên bản TLS, bộ mật mã và những tham số phù hợp, rồi mới gửi dữ liệu ứng dụng.

Ba thành phần có vai trò khác nhau:

- **`SSLContext`:** xác định **nền tảng TLS và vật liệu bảo mật** cho kết nối, chẳng hạn `KeyManager` của danh tính phía client, `TrustManager` kiểm tra sự tin cậy của phía máy chủ và nguồn ngẫu nhiên bảo mật. Đây là factory cho các TLS engine/socket được triển khai bên dưới.
- **`SSLParameters`:** mô tả **các tham số handshake** như những phiên bản TLS cho phép, cipher suites, thuật toán nhận diện endpoint, SNI và một số chính sách khác. Nó **không phải nơi chứa chứng chỉ hay private key**.
- **Chứng chỉ X.509:** tài liệu điện tử liên kết tên/định danh với **public key**, có thời hạn hiệu lực, issuer, chữ ký, các extension và thông tin phục vụ xác minh. **Truststore** quản lý trust anchors/chứng chỉ được tin cậy; **keystore chứa private key** được dùng khi phía client cần trình chứng chỉ cho **mutual TLS (mTLS)**.

Trong Java 11, `HttpClient.Builder` cung cấp:

```java
HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .sslParameters(parameters)
        .build();
```

Bài học tập trung vào API Java 11 **vẫn còn áp dụng trong JDK hiện đại**, cùng lựa chọn cấu hình an toàn. Không khuyến nghị TLS 1.0/1.1, SSLv3, trust-all certificate, tắt hostname verification hay các mẹo bỏ qua bảo mật để “sửa” handshake.

## 2. HTTPS, TLS và HTTP Client liên hệ như thế nào?

Luồng làm việc điển hình:

```text
HttpRequest tới https://api.example.com
          |
          v
HttpClient / kết nối TCP (có thể qua proxy)
          |
          v
TLS handshake
  - thỏa thuận phiên bản TLS / cipher suite
  - máy chủ trình certificate chain
  - TrustManager xác thực đường dẫn tin cậy
  - xác minh tên host trong chứng chỉ
  - nếu server yêu cầu mTLS, client trình chứng chỉ phù hợp
          |
          v
TLS session được thiết lập
          |
          v
Gửi HTTP request đã được bảo vệ, nhận HTTP response
```

TLS bảo vệ tính bí mật và toàn vẹn dữ liệu truyền đi, nhưng **không tự bảo đảm nội dung ứng dụng hợp lệ**. Ví dụ, dù HTTPS thành công, HTTP có thể trả `401`, `403` hoặc `500` do logic server.

Phân biệt:

1. **TLS protocol version:** `TLSv1.2`, `TLSv1.3`, dùng cho bảo mật kết nối.
2. **HTTP protocol version:** `HTTP_1_1`, `HTTP_2`, dùng cho giao thức trao đổi request/response. HTTP/2 qua TLS thường sử dụng **ALPN** để thương lượng, khác với TLS 1.3.
3. **Certificate validation:** kiểm tra chuỗi chứng chỉ, chữ ký, trust anchor, thời gian, mục đích sử dụng và các điều kiện chính sách.
4. **Hostname verification:** so khớp tên máy chủ định kết nối với danh tính chứng chỉ, thông thường qua **Subject Alternative Name (SAN)** phù hợp.

Chỉ xây dựng `HttpClient` **không thực hiện TLS handshake**. Kết nối thật được tạo khi `send` hoặc `sendAsync` cần trao đổi với HTTPS endpoint (hoặc dùng lại một kết nối đã có).

## 3. Khi nào dùng TLS mặc định là đủ?

Trong đa số ứng dụng kết nối đến dịch vụ HTTPS dùng **CA công khai được JDK tin cậy**, lựa chọn **an toàn và đơn giản nhất** là giữ cấu hình mặc định:

```java
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URI;

HttpClient client = HttpClient.newHttpClient();

HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://example.com/"))
        .GET()
        .build();

// Chỉ minh họa: sẽ gửi network thật và cần xử lý IOException,
// InterruptedException, timeout, response status.
HttpResponse<String> response = client.send(
        request, HttpResponse.BodyHandlers.ofString());
```

Đoạn trên **không phải chương trình độc lập**: đặt vào class/phương thức có import và exception handling thích hợp. Nó chỉ nhằm chỉ ra cách dùng mặc định; không có HTTP status hoặc body cố định được giả định.

Theo Javadoc, nếu không gọi `HttpClient.Builder.sslContext(...)`, HTTP client sử dụng **default SSLContext**. Nếu không gọi `sslParameters(...)`, client sử dụng một **bộ thông số TLS mặc định phụ thuộc implementation**. Cấu hình mặc định là lựa chọn thông thường khi không yêu cầu CA nội bộ, mTLS, hoặc giới hạn TLS đặc thù.

**Đừng tạo custom TrustManager chỉ để gọi HTTPS thông thường.** Một TrustManager sai có thể vô tình làm mất certificate validation. Nếu chứng chỉ hợp lệ của một dịch vụ công khai bị báo lỗi, hãy xác minh chain, hostname, thời gian và truststore thực sự đang dùng trước khi thay đổi cấu hình.

## 4. `SSLContext` — cấu hình vật liệu tin cậy và định danh

### 4.1. Những API quan trọng

| API | Vai trò |
| --- | --- |
| `SSLContext.getDefault()` | Lấy default TLS context đã được khởi tạo theo môi trường JSSE/JDK |
| `SSLContext.getInstance("TLS")` | Tạo SSLContext theo protocol family TLS, cần `init(...)` trước khi dùng |
| `context.init(keyManagers, trustManagers, secureRandom)` | Cấp nguồn xác thực danh tính client, độ tin cậy máy chủ và ngẫu nhiên |
| `context.getDefaultSSLParameters()` | Trả tham số TLS **mặc định** được cung cấp bởi context |
| `context.getSupportedSSLParameters()` | Trả các tham số provider **hỗ trợ**, không đồng nghĩa tất cả đều được bật theo chính sách |
| `clientBuilder.sslContext(context)` | Gắn context cho những kết nối HTTPS của HttpClient |

Mã minh họa:

```java
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, null, new SecureRandom());

HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .build();
```

Trong `init(...)`, truyền `null` cho TrustManager cho phép JSSE chọn cách tạo trust manager mặc định từ các provider theo chính sách. `null` cho KeyManager có nghĩa không cung cấp danh tính client tùy chỉnh. Tuy nhiên trong ứng dụng thật, **nếu không cần tùy chỉnh gì, ưu tiên `HttpClient.newHttpClient()` hoặc `SSLContext.getDefault()`** để giữ cấu hình hệ thống như thiết kế.

### 4.2. `"TLS"` không phải `"TLSv1"`

`SSLContext.getInstance("TLS")` chỉ định họ giao thức TLS do provider cung cấp, **không đồng nghĩa cố định TLS 1.0**. Bộ phiên bản thực tế được phép còn phụ thuộc provider, JSSE security properties, `SSLParameters` và phía server.

Java 11 có TLS 1.3 (JEP 332); **TLS 1.2 và TLS 1.3** là các phiên bản hiện đại thường được dùng. Đừng bật lại TLS 1.0/1.1 hoặc SSLv3 chỉ để kết nối một hệ thống lỗi thời. Nếu server không hỗ trợ phiên bản bảo mật phù hợp, cần nâng cấp server hoặc chọn giải pháp chuyển tiếp bảo mật được phê duyệt, không hạ thấp cấu hình toàn JVM.

### 4.3. TrustManager và KeyManager là hai chiều khác nhau

| Thành phần | Dùng để làm gì? | Tình huống |
| --- | --- | --- |
| `TrustManager` / `TrustManagerFactory` | Đánh giá server certificate chain có được tin cậy hay không | Client gọi HTTPS server dùng CA công khai hoặc CA nội bộ |
| `KeyManager` / `KeyManagerFactory` | Chọn chứng chỉ và **private key của client** khi server yêu cầu client authentication | mTLS |
| `SecureRandom` | Nguồn ngẫu nhiên cho các hoạt động TLS cần tính bảo mật | Khởi tạo SSLContext |
| `SSLParameters` | Các lựa chọn handshake bổ sung | Giới hạn TLS version, endpoint identification |

Nếu chỉ cần kết nối HTTPS bình thường, client **không cần có private key riêng** để xác thực server. Ngược lại, nếu server yêu cầu mTLS, cấu hình thêm **client keypair và certificate chain** là bắt buộc theo contract phía server.

## 5. `SSLParameters` — phiên bản TLS, cipher suites, endpoint identification

### 5.1. Một số phương thức chính

| Phương thức | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `setProtocols(String[])` | Đề xuất các phiên bản TLS được phép | Chỉ chọn phiên bản được provider hỗ trợ và được policy cho phép |
| `setCipherSuites(String[])` | Chọn cipher suites | Cấu hình tay dễ làm mất tương thích hoặc yếu đi nếu chọn suite sai |
| `setEndpointIdentificationAlgorithm("HTTPS")` | Bật thuật toán kiểm tra danh tính endpoint dành cho HTTPS trong các TLS engine hỗ trợ | **Không tắt** để vượt lỗi mismatch hostname |
| `setServerNames(List<SNIServerName>)` | Điều khiển SNI trong các engine/socket có hỗ trợ | SNI là gợi ý chọn virtual host, **không thay thế** hostname verification |
| `setApplicationProtocols(String[])` | Các tên protocol ALPN khi dùng engine/socket tương thích | `HttpClient` có thể **tự quản lý danh sách ALPN**; không tự đặt vào HTTP client tùy tiện |
| `getProtocols()` / `getCipherSuites()` | Đọc lại giá trị đã cấu hình | Không phải bằng chứng TLS thực sự thương lượng giá trị đó |

Javadoc của `HttpClient.Builder.sslParameters(...)` lưu ý **các thông số do HTTP client quản lý bên trong, như ALPN application protocol list, có thể bị bỏ qua**. Vì vậy không nên dùng `SSLParameters.setApplicationProtocols(...)` để ép `HttpClient` sử dụng HTTP/2; `HttpClient.Builder.version(HTTP_2)` chỉ là **HTTP version preference**, và phiên bản thực tế còn phụ thuộc thương lượng với server.

Cũng cần phân biệt **supported** và **enabled**:

- `getSupportedSSLParameters()` cho biết provider có khả năng triển khai thuật toán/phiên bản nào.
- `getDefaultSSLParameters()` cho biết lựa chọn mặc định của context.
- Các quy tắc `jdk.tls.disabledAlgorithms` và chính sách bảo mật JVM có thể vô hiệu hóa một thuật toán dù nó xuất hiện trong danh sách hỗ trợ.
- Phiên bản và cipher cuối cùng chỉ biết sau một TLS handshake thành công.

### 5.2. Chọn TLS 1.2/1.3 theo khả năng provider

```java
List<String> supported = Arrays.asList(
        context.getSupportedSSLParameters().getProtocols());

List<String> chosen = Stream.of("TLSv1.3", "TLSv1.2")
        .filter(supported::contains)
        .collect(Collectors.toList());

if (chosen.isEmpty()) {
    throw new IllegalStateException("TLS 1.2+ is not supported");
}

SSLParameters params = context.getDefaultSSLParameters();
params.setProtocols(chosen.toArray(new String[0]));
params.setEndpointIdentificationAlgorithm("HTTPS");
```

Đây là **đoạn minh họa** cần import `SSLContext`, `SSLParameters`, `List`, `Arrays`, `Stream`, `Collectors` và khai báo `context` đã khởi tạo. Ví dụ hoàn chỉnh ở mục 8.

Ưu tiên lấy `context.getDefaultSSLParameters()` rồi thay **chỉ tham số cần thiết**, thay vì tự tạo một đối tượng rỗng và bỏ qua những thiết lập mặc định có ích. Mã trên minh họa quy tắc giới hạn TLS khi ứng dụng có chính sách riêng; nó **không bảo đảm handshake thành công**, vì certificate, hostname, server support và security policy còn phải đúng.

### 5.3. Bản sao của `SSLParameters` trên HttpClient

Java 11 `HttpClient.Builder.sslParameters(parameters)` **sao chép nội dung** đối tượng `SSLParameters` được truyền vào. `HttpClient.sslParameters()` cũng **trả một bản sao** cấu hình SSLParameters của client.

Hệ quả:

```java
HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .sslParameters(params)
        .build();

// Sửa 'params' sau đó không sửa cấu hình đã lưu trong client.
SSLParameters exported = client.sslParameters();
// Sửa 'exported' cũng không chỉnh client.
```

Không coi `SSLParameters` là công tắc live để thay đổi một `HttpClient` đã tạo. Khi cần một chính sách TLS khác, tạo client mới đã được cấu hình phù hợp. Không chỉnh system-wide `SSLContext.setDefault(...)` với hy vọng tác động đến những `HttpClient` đã xây: Javadoc nói giá trị mặc định được lấy tại thời điểm tạo client.

## 6. Chứng chỉ X.509: chain, trust anchor và tên máy chủ

### 6.1. Chứng chỉ dùng để chứng minh điều gì?

Một certificate X.509 của HTTPS server thường chứa:

- **Subject** và **Subject Alternative Name (SAN)**: định danh được chứng chỉ đại diện. Với HTTPS, hostname cần khớp định danh phù hợp, ưu tiên DNS SAN.
- **Issuer**: tổ chức/chứng chỉ đã ký cho subject.
- **Public key**: khóa công khai gắn với danh tính được chứng thực.
- **Not Before / Not After**: khoảng thời gian hiệu lực.
- **Key Usage / Extended Key Usage** và các extension: giới hạn mục đích sử dụng.
- **Digital signature** của issuer, cho phép xây dựng và xác minh certificate path.

Một certificate thường được phát hành bởi intermediate CA và dẫn đến root CA (trust anchor) trong truststore. Server cần cung cấp chain đủ phù hợp để client xác minh; một số client có thể tìm được intermediate theo cơ chế khác nhưng không nên mặc định như vậy.

**Chỉ parse được chứng chỉ không đồng nghĩa tin cậy.** `CertificateFactory.getInstance("X.509")` có thể tạo `X509Certificate` từ PEM/DER nhưng **không tự kiểm tra chain đến trust anchor hoặc hostname**.

### 6.2. Kiểm tra ngày hiệu lực không phải là xác thực toàn diện

```java
try (InputStream in = Files.newInputStream(certPath)) {
    CertificateFactory factory = CertificateFactory.getInstance("X.509");
    X509Certificate cert = (X509Certificate) factory.generateCertificate(in);
    cert.checkValidity(); // Chỉ kiểm tra notBefore/notAfter tại thời điểm hiện tại.
    System.out.println(cert.getSubjectX500Principal());
    System.out.println(cert.getIssuerX500Principal());
}
```

Mã này là đoạn minh họa; cần `import java.nio.file.Files, Path;`, `java.io.InputStream`, `java.security.cert.CertificateFactory` và `X509Certificate`, cùng biến `certPath`.

- `checkValidity()` kiểm tra certificate có nằm trong khoảng thời gian hiệu lực hay không; **không xác nhận chữ ký/issuer/CA trust hoặc hostname**.
- Dùng `getSubjectX500Principal()` và `getIssuerX500Principal()` (không dùng các API DN cũ không còn được ưu tiên).
- Muốn đánh giá certificate chain đầy đủ, dùng **PKIX/TrustManager** với trust anchor/chính sách cụ thể; trong HTTPS để `HttpClient` cùng JSSE thực hiện trong TLS handshake.

### 6.3. Hostname verification là bước tách biệt với CA trust

Một server có chứng chỉ ký bởi CA uy tín **vẫn không hợp lệ cho mọi tên miền**. Nếu bạn gọi `https://api.example.com` nhưng certificate chỉ hợp lệ cho `other.example.com`, hostname verification phải từ chối.

`SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` minh họa việc yêu cầu kiểm tra endpoint identity. Với `HttpClient` chuẩn, không tự tắt hostname verification hoặc dùng system property nội bộ để vượt qua hostname mismatch. Đừng “sửa” lỗi bằng cách chuyển từ hostname sang địa chỉ IP nếu certificate chỉ ghi DNS SAN; kết nối bằng IP cần certificate có IP SAN hợp lệ.

**SNI không phải hostname verification:** SNI truyền tên host cho server để server chọn certificate đúng virtual host; việc tên trên certificate có khớp endpoint không vẫn phải được xác minh.

## 7. Truststore, keystore và cấu hình CA nội bộ/mTLS

### 7.1. Truststore: chứng chỉ nào được tin?

JDK/JSSE thường sử dụng truststore mặc định hoặc truststore đã được chỉ định trong cấu hình hệ thống; ví dụ `java.home/lib/security/cacerts` hay truststore được cấu hình bằng các thuộc tính `javax.net.ssl.trustStore`. Cách lựa chọn cụ thể tùy provider, nền tảng và bảo mật JVM; không đoán mặc định chỉ từ tên một file.

Khi gọi HTTPS đến dịch vụ **CA nội bộ** chưa nằm trong truststore mặc định, có thể tạo **truststore riêng của ứng dụng** chứa CA được xác minh. Đừng tải certificate từ một kết nối đang không đáng tin rồi tự động chấp nhận nó: phải kiểm tra nguồn, fingerprint, chính sách cấp phát qua **kênh đáng tin cậy**.

Một cách xem certificate với công cụ hiện hành của JDK:

```bash
keytool -printcert -file corp-ca.pem
```

Lệnh này chỉ **in thông tin**; hãy đối chiếu fingerprint SHA-256 với nguồn đáng tin (ví dụ nhóm quản trị PKI) trước khi nhập certificate. Để import CA đã kiểm tra:

```bash
keytool -importcert -alias corp-root -file corp-ca.pem \
    -keystore corp-trust.p12 -storetype PKCS12
```

Đây là cú pháp shell minh họa Unix; trên Windows/PowerShell, viết các đối số trên **một dòng** (hoặc dùng cách nối dòng của PowerShell). Không đặt mật khẩu truststore ngay trong lệnh hoặc log vì có thể lộ qua process list/shell history; để công cụ hỏi mật khẩu hoặc dùng cơ chế quản lý bí mật của môi trường.

### 7.2. Tạo SSLContext sử dụng truststore riêng

Giả sử ứng dụng **đã có** `corp-trust.p12` đáng tin và một mật khẩu `char[]` được lấy từ secret manager. Mẫu Java 11:

```java
static SSLContext contextFromTruststore(Path path, char[] password)
        throws Exception {
    KeyStore trust = KeyStore.getInstance("PKCS12");
    try (InputStream in = Files.newInputStream(path)) {
        trust.load(in, password);
    }

    TrustManagerFactory tmf = TrustManagerFactory.getInstance(
            TrustManagerFactory.getDefaultAlgorithm());
    tmf.init(trust);

    SSLContext ctx = SSLContext.getInstance("TLS");
    ctx.init(null, tmf.getTrustManagers(), new SecureRandom());
    return ctx;
}
```

Đây là **phương thức minh họa**, không chạy độc lập: cần import `Path`, `Files`, `InputStream`, `KeyStore`, `TrustManagerFactory`, `SSLContext` và `SecureRandom` và đặt trong class. Nó giả định password và truststore đã tồn tại; chương trình runnable ở mục 8 không yêu cầu file.

Sau đó:

```java
SSLContext context = contextFromTruststore(trustPath, trustPassword);
HttpClient client = HttpClient.newBuilder()
        .sslContext(context)
        .build();
```

**Rất quan trọng:** khi khởi tạo `TrustManagerFactory` bằng `trust`, bạn đang chọn **các trust anchors từ truststore riêng này**. Không tự động cho rằng CA công khai mặc định vẫn được gộp vào truststore đó. Nếu cần vừa tin CA nội bộ vừa tin các CA mặc định, hãy thiết kế việc **hợp nhất các trust anchors** qua quy trình quản trị tin cậy, hoặc sử dụng cơ chế trust manager kết hợp có kiểm chứng; đừng vô tình thay thế toàn bộ hệ thống trust.

Chỉ dùng **CA/root/intermediate được ủy quyền thực sự**; tránh đưa mọi certificate không kiểm chứng vào truststore, tránh bỏ qua chain validation.

### 7.3. Keystore và mTLS (client authentication)

Với HTTPS thông thường, server gửi certificate để client xác thực server. Với **mTLS**, server còn yêu cầu client trình danh tính **client certificate cùng private key**. Để Java client có thể trả lời, thường dùng `KeyManagerFactory`:

```java
// Minh họa: đã có clientStore là PKCS12 KeyStore chứa
// private key + client certificate chain và có keyPassword.
KeyManagerFactory kmf = KeyManagerFactory.getInstance(
        KeyManagerFactory.getDefaultAlgorithm());
kmf.init(clientStore, keyPassword);

SSLContext mtlsContext = SSLContext.getInstance("TLS");
mtlsContext.init(
        kmf.getKeyManagers(),
        tmf.getTrustManagers(),
        new SecureRandom());
```

Đây là **mã minh họa**: cần khai báo `clientStore`, `keyPassword`, `tmf`, import tương ứng; phải có credential thật được bảo vệ. Không hardcode password, không commit private key hay PKCS12 có khóa vào repository, không gửi private key vào HTTP header.

**`SSLParameters.setNeedClientAuth(true)` không phải cách chính để cung cấp client certificate trên `HttpClient`.** Đây là tham số thường liên quan hành vi endpoint ở chế độ server trong TLS engine; để client đáp ứng yêu cầu mTLS, cần **KeyManager** đã được cấp đúng khóa và certificate chain cùng chính sách phía server.

Nếu server không yêu cầu certificate client, việc có KeyManager không tự bảo đảm nó sẽ trình certificate. Việc chọn client certificate phụ thuộc server request và thuật toán/lựa chọn của KeyManager.

## 8. Chương trình Java 11 hoàn chỉnh — cấu hình TLS an toàn, không cần Internet

Chương trình dưới đây **không gửi request qua mạng**. Nó tạo TrustManagerFactory dùng truststore mặc định, tạo `SSLContext("TLS")`, chọn TLS 1.2/1.3 nếu provider hỗ trợ, cấu hình endpoint identification `HTTPS`, tạo `HttpClient` rồi kiểm tra việc **copy `SSLParameters`** và khả năng dùng X.509 CertificateFactory.

Tạo tệp **`HttpsTlsConfigDemo.java`**:

```java
import java.net.http.HttpClient;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.cert.CertificateFactory;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.TrustManagerFactory;

public class HttpsTlsConfigDemo {
    public static void main(String[] args) throws Exception {
        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm());
        tmf.init((KeyStore) null);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), new SecureRandom());

        List<String> supported =
                Arrays.asList(context.getSupportedSSLParameters().getProtocols());
        List<String> chosen = Stream.of("TLSv1.3", "TLSv1.2")
                .filter(supported::contains)
                .collect(Collectors.toList());
        if (chosen.isEmpty()) {
            throw new IllegalStateException("TLS 1.2+ is not supported");
        }

        SSLParameters parameters = context.getDefaultSSLParameters();
        parameters.setProtocols(chosen.toArray(new String[0]));
        parameters.setEndpointIdentificationAlgorithm("HTTPS");

        HttpClient client = HttpClient.newBuilder()
                .sslContext(context)
                .sslParameters(parameters)
                .build();

        String[] saved = client.sslParameters().getProtocols();
        System.out.println("same SSLContext: " + (client.sslContext() == context));
        System.out.println("secure protocols configured: " +
                Arrays.stream(saved).allMatch(
                        p -> p.equals("TLSv1.2") || p.equals("TLSv1.3")));
        System.out.println("HTTPS endpoint identification: " +
                "HTTPS".equals(client.sslParameters().getEndpointIdentificationAlgorithm()));

        parameters.setProtocols(new String[0]); // mutate original after build
        System.out.println("client copied parameters: " +
                Arrays.equals(saved, client.sslParameters().getProtocols()));

        SSLParameters exported = client.sslParameters();
        exported.setProtocols(new String[0]); // mutate returned copy
        System.out.println("getter returns independent copy: " +
                Arrays.equals(saved, client.sslParameters().getProtocols()));

        System.out.println("trust managers supplied: " +
                (tmf.getTrustManagers().length > 0));
        System.out.println("X509 certificate factory: " +
                CertificateFactory.getInstance("X.509").getType());
        System.out.println("default client has SSLContext: " +
                (HttpClient.newHttpClient().sslContext() != null));
    }
}
```

Biên dịch và chạy trên **JDK 11 trở lên**:

```bash
javac --release 11 -encoding UTF-8 HttpsTlsConfigDemo.java
java HttpsTlsConfigDemo
```

**Đầu ra đã kiểm thử trong môi trường JDK có TLS 1.2/1.3 và trust manager mặc định:**

```text
same SSLContext: true
secure protocols configured: true
HTTPS endpoint identification: true
client copied parameters: true
getter returns independent copy: true
trust managers supplied: true
X509 certificate factory: X.509
default client has SSLContext: true
```

Giải thích:

1. `tmf.init((KeyStore) null)` yêu cầu provider sử dụng **cấu hình trust material mặc định** theo JSSE. Đây không phải hành động bỏ qua trust validation. Một môi trường tùy biến có thể có truststore khác hoặc cấu hình khác.
2. `SSLContext.getInstance("TLS")` kết hợp `context.init(...)` tạo context TLS đã có trust managers. Ví dụ không cấp private key phía client vì không làm mTLS.
3. `chosen` chỉ chứa tên `TLSv1.3` và/hoặc `TLSv1.2` do provider liệt kê là supported. Nếu không có phiên bản hiện đại, chương trình dừng, **không tự fallback xuống TLS 1.0/1.1**.
4. `parameters.setEndpointIdentificationAlgorithm("HTTPS")` giữ ý định xác minh endpoint. Nhưng ví dụ không thực hiện handshake; chỉ khẳng định cấu hình đã được truyền vào client.
5. Sau khi build, thay đổi `parameters` gốc **không thay đổi** cấu hình trên client, và thay đổi object được trả về từ `client.sslParameters()` cũng không đổi client, do cơ chế copy.
6. `CertificateFactory.getInstance("X.509")` chỉ chứng minh JDK cung cấp khả năng **parse loại chứng chỉ X.509**; nó không tạo hay validate một certificate chain trong chương trình này.
7. `HttpClient.newHttpClient()` có SSLContext mặc định. Bài test không chứng minh server cụ thể có certificate hợp lệ hay TLS handshake thành công vì **không có kết nối mạng**.

Các dòng boolean trên có thể phụ thuộc provider/security policy trong môi trường được cấu hình khác biệt. Khi dùng một JDK 11+ chuẩn với cấu hình TLS phù hợp, kết quả mẫu đã được xác minh; ứng dụng production cần kiểm thử HTTPS handshake thật với endpoint dự kiến.

## 9. Phân biệt certificate parsing, validity, chain và hostname

Đây là bốn mức khác nhau, cần nhớ khi debug:

| Kiểm tra | Điều nó xác nhận | Công cụ/khái niệm |
| --- | --- | --- |
| **Parse** | Byte có thể biểu diễn certificate X.509 đúng định dạng | `CertificateFactory.generateCertificate` |
| **Validity period** | Chứng chỉ chưa quá hạn hoặc chưa tới ngày hiệu lực | `X509Certificate.checkValidity` |
| **Certificate path trust** | Chuỗi chữ ký/các ràng buộc certificate dẫn tới trust anchor tin cậy theo chính sách | `TrustManager`, PKIX |
| **Hostname/endpoint identification** | Certificate có định danh phù hợp đúng host đang kết nối | `SSLParameters` / kiểm tra danh tính endpoint trong TLS client |

**Chỉ thành công ở một trong bốn bước không chứng minh những bước còn lại đúng.** Đặc biệt, tự gọi `checkValidity()` rồi chấp nhận một certificate tự ký chưa được tin cậy là sai. Tương tự, chứng chỉ do CA hợp lệ cấp nhưng dành cho **host khác** cũng phải bị từ chối.

Về chứng chỉ tự ký: có thể sử dụng trong môi trường kiểm thử có **trust anchor được cấu hình rõ và đã được xác minh**; không đồng nghĩa với việc tắt hết kiểm tra. Trong production, dùng CA phù hợp, theo dõi cấp phát và gia hạn chứng chỉ.

## 10. Lỗi thường gặp khi gọi HTTPS bằng Java 11

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý an toàn |
| --- | --- | --- |
| `SSLHandshakeException` với `PKIX path building failed` | Không tìm được certificate chain tin cậy tới trust anchor; thiếu CA/intermediate hoặc trỏ nhầm truststore | Kiểm tra chain server, truststore JVM/app thực tế, CA nội bộ, chính sách PKIX |
| `SSLHandshakeException` liên quan `No subject alternative names` hoặc hostname | Certificate không khớp host/IP được gọi | Sửa tên host, DNS/SAN và cấp lại certificate; **không tắt hostname verification** |
| `CertificateExpiredException` / `CertificateNotYetValidException` | Chứng chỉ ngoài thời gian hiệu lực hoặc đồng hồ hệ thống sai | Kiểm tra thời gian và gia hạn/cấp lại certificate |
| `handshake_failure` / `protocol_version` | Không có phiên bản TLS/cipher suite chung hoặc yêu cầu client auth chưa đáp ứng | Kiểm tra TLS 1.2/1.3, cipher, key/cert mTLS và chính sách server |
| Chạy được trên máy phát triển nhưng fail ở server | Khác Java runtime, truststore, CA, proxy/TLS inspection, DNS, hệ điều hành | So sánh cấu hình TLS, trust material và kết nối thực tế ở hai môi trường |
| Chỉ HTTPS nội bộ bị fail | CA nội bộ chưa được tin cậy hoặc server thiếu intermediate | Nhập CA nội bộ **đã xác minh** vào truststore đúng phạm vi; sửa chain server |
| mTLS báo `bad_certificate` / `certificate_required` | Client không có certificate/private key phù hợp hoặc server không tin CA của client | Cấu hình `KeyManagerFactory` với client keystore đúng; kiểm tra server trust |
| Dùng `SSLParameters.setProtocols(...)` mà không kết nối được | Phiên bản đặt không được hỗ trợ/bị policy vô hiệu hóa hoặc server không hỗ trợ | Kiểm tra provider, security properties và server; không hạ cấp xuống phiên bản yếu |
| `client.sslParameters()` khác đối tượng `params` vừa sửa | `sslParameters` sao chép cấu hình | Tạo client mới với chính sách mới; không đợi bản sao tự cập nhật |
| Thay default SSLContext rồi client cũ vẫn dùng cấu hình cũ | HttpClient nhận cấu hình tại lúc được tạo | Xây client mới khi cần thay TLS configuration |
| Nhầm `SSLContext` với client certificate | Context chỉ giữ/cấp phát TLS machinery; cert/key nằm trong keystore và KeyManager | Nắm đúng vai trò `KeyManager`, `TrustManager` và SSLContext |

**Không dùng “trust-all” TrustManager** kiểu `checkServerTrusted(...)` để trống, không dùng `HostnameVerifier` luôn trả `true`, không tắt hostname verification bằng tùy chọn nội bộ của JDK để làm mất lỗi. Các cách này biến lỗi cấu hình thành **lỗ hổng man-in-the-middle**, khiến kết nối trông có vẻ thành công nhưng không xác thực đúng đối tác.

### Gợi ý debug có kiểm soát

Với JSSE JDK, có thể bật chẩn đoán **tạm thời**:

```bash
java -Djavax.net.debug=ssl,handshake YourApp
```

Đây là lệnh ví dụ; class `YourApp` phải tồn tại và tên class phù hợp. Log debug TLS có thể chứa nhiều metadata và thông tin nhạy cảm; không bật thường xuyên trong production, không công khai log/credential.

Đối với truststore/CA, đối chiếu các yếu tố: truststore thật đang được load, chain được server gửi, certificate hostname/SAN, ngày hết hạn, security policy, TLS version/cipher suite. Không quy lỗi `PKIX path building failed` cho sai `Content-Type`/HTTP status: đây là lỗi xảy ra **trước tầng HTTP ứng dụng**.

## 11. Những lưu ý hiện đại khi cấu hình TLS

### 11.1. Dùng TLS hiện đại, không nới lỏng policy

TLS 1.2 và TLS 1.3 vẫn là những lựa chọn phù hợp cho hệ thống hiện đại. JDK và security provider có thể loại bỏ thuật toán yếu theo `jdk.tls.disabledAlgorithms`; đừng sửa security policy để khôi phục RC4, SSLv3, TLS 1.0/1.1 hoặc thuật toán ký yếu.

Thực tế, JDK được cập nhật định kỳ thay đổi danh sách CA, chính sách thuật toán và bảo mật TLS. Khi triển khai, xác minh theo **JDK runtime đang dùng** và cập nhật bản vá định kỳ; không sao chép cứng một danh sách cipher từ ví dụ cũ nếu chưa đánh giá.

### 11.2. Không tự ép ALPN/HTTP2 qua SSLParameters

HTTPS chạy HTTP/2 thường dựa vào ALPN. Theo Javadoc, HTTP client **quản lý một số thông số SSLParameters bên trong**, chẳng hạn danh sách application protocols; giá trị tự đặt có thể bị bỏ qua. Nếu cần ưu tiên HTTP/2:

```java
HttpClient client = HttpClient.newBuilder()
        .version(HttpClient.Version.HTTP_2)
        .build();
```

**HTTP_2 là lựa chọn ưu tiên**, không phải bảo đảm. Sau khi gửi, kiểm tra `HttpResponse.version()` để biết giao thức thực tế. Đừng nhầm `HTTP_2` với `TLSv1.2/TLSv1.3`.

### 11.3. Theo dõi certificate lifecycle

- Giữ danh sách các CA được phép tin theo nguyên tắc **least privilege**; kiểm tra nguồn và fingerprint trước khi cấp quyền tin.
- Lên lịch gia hạn certificate trước `NotAfter`; lưu ý việc thay đổi intermediate/root CA có thể đòi cập nhật truststore.
- Khi xử lý **certificate revocation**, đừng khẳng định JDK mặc định luôn kiểm tra OCSP/CRL trong mọi cấu hình: chính sách PKIX/JSSE phải được thiết kế và bật có chủ đích nếu nghiệp vụ yêu cầu.
- Tránh hardcode mật khẩu, private key, token hay nội dung keystore vào repository; dùng secret manager/cơ chế quản trị khóa phù hợp.
- Không tự dùng một certificate bất kỳ làm CA tin cậy chỉ vì certificate đó đã được server gửi.
- Phân biệt lỗi TLS handshake với lỗi HTTP 401/403/500; logging, metrics, retry và bảo mật cần xử lý theo từng tầng.

## 12. Ôn tập nhanh

**Câu 1.** Khi nào nên dùng `HttpClient.newHttpClient()` thay vì cấu hình SSLContext?  
**Trả lời:** Với HTTPS thông thường sử dụng CA được JDK tin cậy và không yêu cầu mTLS hay chính sách TLS riêng, default thường là lựa chọn phù hợp.

**Câu 2.** `SSLContext` khác `SSLParameters` ra sao?  
**Trả lời:** SSLContext quản lý nền tảng TLS, key/trust managers và random; SSLParameters cấu hình các lựa chọn handshake như protocol, cipher và endpoint identification.

**Câu 3.** `CertificateFactory.generateCertificate` thành công thì đã được tin cậy chưa?  
**Trả lời:** Chưa. Parse thành công không chứng minh certificate path dẫn tới CA tin cậy, không xác nhận hostname hay chính sách sử dụng.

**Câu 4.** `X509Certificate.checkValidity()` có thay `TrustManager` không?  
**Trả lời:** Không. Nó chỉ kiểm tra thời gian hiệu lực.

**Câu 5.** Vì sao CA hợp lệ vẫn có thể dẫn tới handshake fail?  
**Trả lời:** Certificate có thể không khớp hostname, quá hạn, thiếu intermediate hoặc bị policy từ chối.

**Câu 6.** Nếu service dùng CA nội bộ, có nên tạo trust-all manager không?  
**Trả lời:** Không. Tạo truststore riêng với CA đã được xác minh và áp chính sách PKIX phù hợp.

**Câu 7.** mTLS cần gì ngoài truststore?  
**Trả lời:** Client certificate chain và **private key** trong keystore được `KeyManagerFactory` cung cấp cho SSLContext, theo yêu cầu server.

**Câu 8.** Sửa đối tượng `SSLParameters` sau `HttpClient.newBuilder().sslParameters(params).build()` có thay client không?  
**Trả lời:** Không. Builder sao chép nội dung parameters; client getter cũng trả một bản sao.

**Câu 9.** `SSLParameters.setApplicationProtocols(...)` có bảo đảm HttpClient dùng HTTP/2 không?  
**Trả lời:** Không. HttpClient có thể quản lý ALPN nội bộ. `HttpClient.Builder.version(HTTP_2)` là preference; `HttpResponse.version()` phản ánh phiên bản thực tế.

**Câu 10.** Nếu ứng dụng nhận lỗi `PKIX path building failed`, có nên đặt `Content-Type` hay bỏ qua hostname verification?  
**Trả lời:** Không. Phải kiểm tra trust chain/truststore, CA, intermediate và các thông số TLS. Content-Type không liên quan tới handshake.

## 13. Ghi nhớ

- **`SSLContext`**: bối cảnh TLS và **KeyManager/TrustManager**; dùng default nếu không cần CA nội bộ/mTLS.
- **`SSLParameters`**: tùy chọn handshake như TLS version, cipher suites, endpoint identification. `HttpClient.Builder.sslParameters` **sao chép cấu hình**, không phải thiết lập live.
- **X.509 certificate** chứa public key và thông tin danh tính/chữ ký; **truststore** chứa chứng chỉ được tin, **keystore** dùng cho private key và danh tính client.
- **Parse certificate**, **checkValidity**, **PKIX certificate chain** và **hostname verification** là các bước riêng biệt.
- **TLS 1.2/1.3** phù hợp trong Java 11+ hiện đại; không dùng SSLv3/TLS 1.0/1.1/trust-all/tắt hostname check.
- **mTLS** cần client certificate và private key thông qua KeyManager, ngoài việc tin certificate server.
- HTTPS thất bại ở TLS handshake cần khắc phục đúng CA, chain, SAN, thời hạn, cấu hình protocol; không che lỗi bằng việc bỏ kiểm tra.
- Kiểm thử cấu hình bằng Java có thể thực hiện không cần mạng, nhưng **handshake và validation thật chỉ được chứng minh khi kết nối tới HTTPS endpoint đúng**.

**Tài liệu chính thức còn áp dụng:** [Oracle Java 11 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/11/docs/api/java.net.http/java/net/http/HttpClient.Builder.html); [Oracle Java 11 — SSLContext](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLContext.html); [Oracle Java 11 — SSLParameters](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/javax/net/ssl/SSLParameters.html); [Oracle Java 11 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/11/security/java-secure-socket-extension-jsse-reference-guide.html); [Oracle Java 11 — CertificateFactory](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/cert/CertificateFactory.html); [Oracle Java 11 — X509Certificate](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/security/cert/X509Certificate.html); [Oracle Java 26 — HttpClient.Builder](https://docs.oracle.com/en/java/javase/26/docs/api/java.net.http/java/net/http/HttpClient.Builder.html); [OpenJDK JEP 332 — TLS 1.3](https://openjdk.org/jeps/332).