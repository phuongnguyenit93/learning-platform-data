# HTTPS, SSLContext và xác minh chứng thư máy chủ

## 1. HTTPS bảo vệ điều gì?

HTTP truyền dữ liệu ứng dụng giữa client và server. Khi dùng **HTTPS**, HTTP được chạy bên trong một kết nối được bảo vệ bởi **TLS (Transport Layer Security)**. TLS cung cấp ba thuộc tính quan trọng:

1. **Mã hóa (confidentiality):** người đứng giữa đường truyền không đọc được nội dung nếu không có khóa phù hợp.
2. **Toàn vẹn (integrity):** dữ liệu bị sửa trên đường truyền sẽ bị phát hiện.
3. **Xác thực peer:** client xác minh danh tính máy chủ thông qua chứng thư số và chuỗi tin cậy; tùy cấu hình, server cũng có thể xác thực client bằng chứng thư.

Một luồng HTTPS cơ bản:

~~~text
Java HTTP client
       |
       | 1. Kết nối TCP
       v
    TLS handshake
       |
       | 2. Server gửi certificate chain
       v
Client xác minh:
  - Chuỗi chứng thư có dẫn tới trust anchor?
  - Chứng thư còn hạn và phù hợp mục đích?
  - Tên host URL có khớp certificate SAN?
       |
       | 3. Thỏa thuận khóa và thuật toán
       v
Kênh TLS được thiết lập
       |
       | 4. HTTP request/response đi trong kênh TLS
       v
     HTTPS server
~~~

Trong Java 17, phần TLS được triển khai qua **JSSE (Java Secure Socket Extension)**. Những API quan trọng gồm:

- `SSLContext`: cấu hình môi trường TLS, bao gồm key managers, trust managers và nguồn ngẫu nhiên.
- `TrustManager`: quyết định chứng thư peer có được tin cậy hay không.
- `KeyManager`: cung cấp danh tính và private key của client khi cần xác thực client.
- `SSLSocket`/`SSLEngine`: các API TLS mức thấp.
- `HttpsURLConnection` và `java.net.http.HttpClient`: API HTTP/HTTPS mức cao.

**HTTPS không đồng nghĩa với việc chỉ mã hóa dữ liệu.** Nếu client bỏ qua xác minh chứng thư hoặc hostname, kết nối có thể được mã hóa tới một máy chủ giả mạo. Mã hóa mà không xác thực đúng peer không bảo vệ được người dùng trước tấn công man-in-the-middle.

## 2. SSL, TLS và phiên bản nên dùng

### 2.1. TLS là giao thức hiện đại

Tên `SSLContext` là tên API lịch sử của JSSE. Trong ứng dụng mới, hãy dùng TLS. SSL 2.0/3.0 và các phiên bản TLS cũ như TLS 1.0/1.1 đã lỗi thời và không nên bật lại để xử lý lỗi tương thích một cách tùy tiện.

Trên Java 17, TLS 1.3 và TLS 1.2 là các phiên bản hiện đại cần ưu tiên. JDK thường cung cấp tập protocol/cipher mặc định theo chính sách bảo mật của runtime và provider. Không nên hardcode một danh sách cipher cũ chỉ vì tìm thấy trong ví dụ trên mạng.

### 2.2. `SSLContext.getInstance("TLS")` không có nghĩa chỉ dùng một phiên bản TLS

Ví dụ:

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, null, null);
~~~

`"TLS"` là tên giao thức/algorithm family dùng để lấy SSLContext từ provider. Các phiên bản giao thức thực tế được bật trên socket/engine theo cấu hình của provider và JSSE.

Nếu ứng dụng có chính sách rõ ràng cần giới hạn phiên bản, có thể cấu hình `SSLParameters` để chỉ cho phép TLS 1.3 và TLS 1.2. Không bật lại SSLv3, TLS 1.0 hoặc TLS 1.1 chỉ để làm cho một server cũ kết nối được; cần nâng cấp cấu hình server hoặc xử lý ngoại lệ theo quy trình bảo mật của tổ chức.

### 2.3. Không nhầm TLS protocol với certificate algorithm

TLS version, cipher suite, chữ ký certificate và thuật toán khóa công khai là các phần liên quan nhưng khác nhau:

- **TLS version:** giao thức handshake và record layer.
- **Cipher suite:** tổ hợp thuật toán mã hóa/xác thực được TLS 1.2 sử dụng; TLS 1.3 có cách đặt tên và cấu trúc suite khác.
- **Certificate signature algorithm:** thuật toán CA dùng để ký certificate.
- **Public key algorithm/size:** loại khóa của certificate, ví dụ RSA hoặc EC.

Một kết nối có thể thất bại do không có phiên bản TLS chung, cipher không tương thích, certificate algorithm bị chính sách runtime từ chối hoặc chuỗi tin cậy không hợp lệ. Cần đọc nguyên nhân gốc trong exception/handshake log thay vì đổi tất cả cấu hình cùng lúc.

## 3. Certificate máy chủ là gì?

### 3.1. X.509 certificate

Trong HTTPS thông thường, server gửi một hoặc nhiều chứng thư X.509 để chứng minh danh tính. Certificate thường chứa:

- Subject: chủ thể được chứng thư xác nhận.
- Issuer: CA hoặc tổ chức phát hành/ký certificate.
- Public key: khóa công khai của chủ thể.
- Validity: thời điểm bắt đầu và kết thúc hiệu lực.
- Subject Alternative Name (SAN): tên DNS hoặc địa chỉ IP mà certificate áp dụng.
- Key Usage và Extended Key Usage (EKU): mục đích sử dụng khóa/chứng thư.
- Chữ ký số của issuer.

Client dùng public key và chữ ký để xác minh tính toàn vẹn của certificate, đồng thời kiểm tra certificate có phù hợp với mục đích xác thực server hay không.

### 3.2. Certificate chain

Một certificate server thường không được client tin trực tiếp. Nó được ký bởi intermediate CA; intermediate có thể được ký bởi root CA mà client đã tin cậy:

~~~text
Trust store của client
       |
       v
Root CA (trust anchor)
       |
       | ký
       v
Intermediate CA
       |
       | ký
       v
Server certificate
       |
       v
api.example.com
~~~

Server thường gửi leaf certificate và các intermediate cần thiết. Client xây dựng/kiểm tra đường dẫn chứng thư đến một trust anchor được tin cậy.

Root certificate thường được cấu hình trong trust store của client. Server không thể tự làm cho certificate của mình đáng tin chỉ bằng cách gửi kèm một root certificate lạ; client phải có trust anchor tương ứng hoặc được cấu hình tin cậy theo chính sách.

### 3.3. Kiểm tra chuỗi chứng thư không giống kiểm tra tên host

Đây là điểm rất quan trọng:

1. **Path validation/trust:** certificate có chuỗi chữ ký hợp lệ dẫn đến trust anchor, còn hạn, đúng mục đích và đáp ứng các ràng buộc cần thiết không?
2. **Hostname verification:** certificate có được cấp cho đúng host mà client đang kết nối không?

Một certificate có thể được CA tin cậy ký nhưng lại thuộc về `other.example.com`, trong khi URL là `api.example.com`. Chuỗi chứng thư có thể hợp lệ nhưng hostname không khớp; client phải từ chối kết nối.

## 4. Xác minh hostname và Subject Alternative Name

### 4.1. Certificate phải khớp host trong URL

Giả sử client gọi:

~~~text
https://api.example.com/v1/orders
~~~

Certificate server phải có SAN phù hợp với `api.example.com`. Với DNS name, certificate thường có SAN dạng `dNSName`. Nếu URL dùng địa chỉ IP, certificate cần SAN dạng `iPAddress` khớp địa chỉ IP đó.

Ví dụ certificate có:

~~~text
Subject Alternative Name:
  DNS:api.example.com
  DNS:orders.example.com
~~~

thì các host tương ứng có thể được xác minh theo quy tắc hostname. Certificate chỉ có SAN `DNS:other.example.com` không hợp lệ cho URL `https://api.example.com`.

### 4.2. Không dựa vào Common Name như cơ chế thay thế SAN

Các certificate hiện đại cần chứa SAN. Không nên thiết kế hệ thống mới dựa vào việc hostname khớp trường Common Name (CN) của Subject. Khi phát hành certificate, hãy yêu cầu CA hoặc hệ thống nội bộ tạo SAN chính xác cho các DNS/IP cần dùng.

### 4.3. Wildcard có phạm vi giới hạn

Certificate wildcard như:

~~~text
DNS:*.example.com
~~~

có thể áp dụng cho một label con, ví dụ `api.example.com`, theo quy tắc hostname verification. Nó không có nghĩa tự động bao phủ mọi cấp như `v2.api.example.com` hoặc domain gốc `example.com`.

Không tự viết hostname verifier bằng cách so sánh chuỗi đơn giản hoặc dùng regex tùy tiện. Hãy để HTTPS client/JSSE thực hiện hostname verification theo quy tắc chuẩn.

## 5. Trust store, Key store và vai trò của SSLContext

### 5.1. Trust store: client tin CA nào?

**Trust store** chứa các certificate được ứng dụng tin cậy làm trust anchor hoặc certificate tin cậy theo cấu hình. Trong HTTPS client thông thường, trust manager dùng trust store để xác minh certificate chain của server.

Java thường có trust store mặc định trong cài đặt JDK/JRE. JSSE cũng hỗ trợ cấu hình bằng system properties, chẳng hạn:

- `javax.net.ssl.trustStore`: đường dẫn trust store.
- `javax.net.ssl.trustStorePassword`: mật khẩu mở trust store.
- `javax.net.ssl.trustStoreType`: loại keystore, ví dụ `PKCS12`.

Không nên ghi mật khẩu trust store vào source code, command line công khai hoặc log. Dùng secret/configuration management phù hợp với môi trường triển khai.

### 5.2. Key store: client sở hữu danh tính nào?

**Key store** thường chứa private key và certificate chain của chính ứng dụng. Nó được KeyManager sử dụng khi client cần trình certificate để server xác thực client (mutual TLS/mTLS).

| Thành phần | Câu hỏi |
|---|---|
| Trust store | Tôi tin certificate/CA nào của peer? |
| Key store | Tôi có private key/certificate nào để chứng minh danh tính của mình? |
| TrustManager | Certificate peer có được chấp nhận không? |
| KeyManager | Khi peer yêu cầu client certificate, tôi trình danh tính nào? |

HTTPS một chiều thông thường chỉ cần client xác thực server. Client không phải có key store riêng nếu server không yêu cầu mTLS.

### 5.3. SSLContext kết nối các thành phần TLS

`SSLContext` là điểm khởi tạo factory cho các socket/engine TLS. Phương thức:

~~~java
context.init(keyManagers, trustManagers, secureRandom);
~~~

nhận:

- `KeyManager[]`: danh tính/key của phía local nếu cần.
- `TrustManager[]`: chính sách tin cậy đối với peer.
- `SecureRandom`: nguồn ngẫu nhiên dùng trong quá trình TLS.

Đối với HTTPS client dùng trust store mặc định, cách đơn giản thường là dùng default SSLContext:

~~~java
SSLContext context = SSLContext.getDefault();
~~~

Hoặc khởi tạo context `TLS` với các manager mặc định theo JSSE:

~~~java
SSLContext context = SSLContext.getInstance("TLS");
context.init(null, null, null);
~~~

Không cần tạo TrustManager riêng chỉ để “bỏ qua” certificate. Nếu certificate hợp lệ nhưng chưa được tin cậy, hãy cập nhật trust configuration đúng cách.

## 6. HTTPS client mặc định trên Java 17

### 6.1. Dùng java.net.http.HttpClient

Java 11 trở lên có `java.net.http.HttpClient`, vì vậy Java 17 có thể dùng API này mà không cần thư viện ngoài:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class DefaultHttpsClient {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();

        HttpRequest request = HttpRequest.newBuilder()
                .uri(URI.create("https://example.com/"))
                .timeout(Duration.ofSeconds(20))
                .GET()
                .build();

        HttpResponse<String> response = client.send(
                request,
                HttpResponse.BodyHandlers.ofString()
        );

        System.out.println("Status: " + response.statusCode());
        System.out.println(response.body());
    }
}
~~~

Khi không cấu hình SSLContext tùy chỉnh, `HttpClient` sử dụng cấu hình TLS mặc định của runtime. Với HTTPS, client thực hiện xác minh certificate chain và hostname theo cấu hình bảo mật mặc định. Không cần tự viết hostname verifier cho trường hợp thông thường.

Lưu ý:

- `connectTimeout` giới hạn thời gian thiết lập kết nối.
- `HttpRequest.timeout` đặt timeout cho request.
- Timeout HTTP không thay thế các chính sách retry, cancellation hoặc timeout nghiệp vụ.
- Body handler `ofString()` cần xử lý charset theo quy tắc HTTP response; không liên quan đến charset của Console.

### 6.2. HTTPS với HttpsURLConnection

API `HttpsURLConnection` vẫn có trong Java 17 và hữu ích khi làm việc với code cũ hoặc URLConnection:

~~~java
import javax.net.ssl.HttpsURLConnection;
import java.net.URI;
import java.net.URL;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

URL url = URI.create("https://example.com/").toURL();
HttpsURLConnection connection =
        (HttpsURLConnection) url.openConnection();

connection.setConnectTimeout(10_000);
connection.setReadTimeout(20_000);
connection.setRequestMethod("GET");

int status = connection.getResponseCode();
try (InputStream input = status < 400
        ? connection.getInputStream()
        : connection.getErrorStream()) {
    if (input != null) {
        String body = new String(
                input.readAllBytes(),
                StandardCharsets.UTF_8
        );
        System.out.println(body);
    }
} finally {
    connection.disconnect();
}
~~~

`HttpsURLConnection` dùng SSL socket factory và hostname verifier mặc định nếu không bị ứng dụng thay đổi. Đừng gán một hostname verifier chấp nhận tất cả host; điều đó vô hiệu hóa một phần quan trọng của xác thực HTTPS.

## 7. Tạo SSLContext với trust store riêng

Một ứng dụng nội bộ có thể kết nối tới server dùng certificate được ký bởi CA riêng của tổ chức. Khi đó cần đưa CA tin cậy vào trust store của ứng dụng và tạo SSLContext sử dụng trust manager từ trust store đó.

### 7.1. Tạo trust store PKCS12

Ví dụ dùng `keytool` đi kèm JDK để import certificate CA nội bộ:

~~~shell
keytool -importcert ^
  -alias company-root-ca ^
  -file company-root-ca.crt ^
  -keystore app-truststore.p12 ^
  -storetype PKCS12
~~~

Trên shell kiểu Unix, thay dấu nối dòng `^` bằng ký tự nối dòng phù hợp hoặc chạy toàn bộ lệnh trên một dòng.

Lệnh sẽ yêu cầu mật khẩu trust store và xác nhận certificate. Chỉ import certificate CA sau khi đã xác minh fingerprint hoặc lấy từ kênh phân phối tin cậy. Không nhấn chấp nhận một certificate không rõ nguồn gốc chỉ để làm cho kết nối chạy được.

Có thể xem thông tin certificate trước khi import:

~~~shell
keytool -printcert -file company-root-ca.crt
~~~

PKCS12 là định dạng keystore hiện đại, được hỗ trợ trong Java 17. Các file JKS cũ vẫn có thể tồn tại trong hệ thống, nhưng khi tạo cấu hình mới nên chọn định dạng được hỗ trợ rộng rãi như PKCS12 nếu không có yêu cầu tương thích đặc biệt.

### 7.2. Load trust store và tạo TrustManagerFactory

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

static SSLContext createSslContext(
        Path trustStorePath,
        char[] trustStorePassword
) throws Exception {
    KeyStore trustStore = KeyStore.getInstance("PKCS12");

    try (InputStream input = Files.newInputStream(trustStorePath)) {
        trustStore.load(input, trustStorePassword);
    }

    TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm()
            );
    trustManagerFactory.init(trustStore);

    SSLContext context = SSLContext.getInstance("TLS");
    context.init(
            null,
            trustManagerFactory.getTrustManagers(),
            null
    );
    return context;
}
~~~

Giải thích:

1. `KeyStore.getInstance("PKCS12")` tạo đối tượng đọc trust store.
2. `load(...)` đọc file và mở bằng mật khẩu.
3. `TrustManagerFactory` tạo trust manager theo thuật toán mặc định của provider.
4. `init(trustStore)` cấu hình các certificate được tin cậy.
5. `SSLContext.init` gắn trust managers vào context; không cần KeyManager cho HTTPS một chiều.

Trong ứng dụng thực tế, không nên để password dưới dạng String cố định trong source. Lấy secret từ hệ thống quản lý secret, chỉ giữ trong bộ nhớ cần thiết và xóa mảng char sau khi hoàn tất nếu vòng đời cho phép.

### 7.3. Dùng SSLContext với HttpClient

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Path;
import java.time.Duration;

char[] password = obtainTrustStorePassword();
try {
    SSLContext sslContext = createSslContext(
            Path.of("config", "app-truststore.p12"),
            password
    );

    HttpClient client = HttpClient.newBuilder()
            .sslContext(sslContext)
            .connectTimeout(Duration.ofSeconds(10))
            .build();

    HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://internal.example.com/api/status"))
            .timeout(Duration.ofSeconds(20))
            .GET()
            .build();

    HttpResponse<String> response = client.send(
            request,
            HttpResponse.BodyHandlers.ofString()
    );

    System.out.println(response.statusCode());
} finally {
    java.util.Arrays.fill(password, '\0');
}
~~~

`obtainTrustStorePassword()` là hàm ví dụ đại diện cho cơ chế lấy secret của ứng dụng. Không lưu password thực vào file mã nguồn.

SSLContext tùy chỉnh thay đổi trust configuration được dùng cho client đó. **Nếu trust store chỉ chứa CA nội bộ, client có thể không còn tin các public CA mặc định**. Nếu ứng dụng cần cả endpoint nội bộ và public, trust store phải chứa đầy đủ các trust anchor cần thiết hoặc có một chiến lược trust manager được thiết kế và kiểm soát rõ ràng.

Không tự viết một TrustManager “kết hợp” thiếu kiểm tra thứ tự/điều kiện. Cần giữ nguyên PKIX validation và hostname verification.

### 7.4. Dùng SSLContext với HttpsURLConnection

~~~java
SSLContext sslContext = createSslContext(
        Path.of("config", "app-truststore.p12"),
        password
);

HttpsURLConnection connection =
        (HttpsURLConnection) URI
                .create("https://internal.example.com/health")
                .toURL()
                .openConnection();

connection.setSSLSocketFactory(sslContext.getSocketFactory());
connection.setConnectTimeout(10_000);
connection.setReadTimeout(10_000);

int status = connection.getResponseCode();
~~~

Việc đặt socket factory thay đổi trust configuration cho kết nối này. Hãy giữ hostname verification mặc định của `HttpsURLConnection`; không cài `HostnameVerifier` luôn trả `true`.

## 8. Certificate chain validation hoạt động thế nào?

### 8.1. TrustManagerFactory và PKIX

Trong cấu hình phổ biến, `TrustManagerFactory` tạo X.509 trust manager. Khi TLS handshake nhận certificate chain từ server, trust manager kiểm tra đường dẫn chứng thư theo chính sách PKIX của provider:

- Certificate có chữ ký hợp lệ theo issuer không?
- Chuỗi có thể nối đến trust anchor trong trust store không?
- Certificate còn trong thời gian hiệu lực không?
- CA có quyền ký certificate con theo Basic Constraints/Key Usage không?
- Certificate leaf có mục đích phù hợp, chẳng hạn server authentication, không?
- Có vi phạm thuật toán hoặc chính sách bảo mật của runtime không?

Khi không xây dựng được đường dẫn tin cậy, lỗi thường có nguyên nhân như:

~~~text
PKIX path building failed
unable to find valid certification path to requested target
~~~

Đây là dấu hiệu client không xây dựng được đường dẫn chứng thư tới trust anchor tin cậy. Nó không đồng nghĩa chắc chắn certificate server bị giả; có thể server thiếu intermediate, CA nội bộ chưa được import hoặc trust store cấu hình sai.

### 8.2. Server phải gửi đủ intermediate certificate

Nếu server chỉ gửi leaf certificate mà bỏ intermediate cần thiết, client có thể không dựng được chain. Cách sửa đúng thường là cấu hình server gửi certificate chain đầy đủ (leaf + intermediate), đồng thời client tin root CA phù hợp.

Không nên giải quyết bằng cách import leaf certificate của từng server vào trust store một cách tùy tiện. Điều đó tạo gánh nặng rotation và có thể làm mất khả năng quản trị trust ở cấp CA.

### 8.3. Kiểm tra thời hạn và đồng hồ hệ thống

Certificate có `Not Before` và `Not After`. Nếu đồng hồ máy client sai đáng kể, một certificate hợp lệ có thể bị xem là chưa có hiệu lực hoặc đã hết hạn.

Khi gặp lỗi validity:

1. Xem thời gian hệ thống client.
2. Xem `Not Before`/`Not After` của leaf và intermediate.
3. Kiểm tra server đã triển khai certificate mới và gửi đúng chain chưa.
4. Kiểm tra trust store đang được JVM sử dụng.

Không bỏ kiểm tra thời hạn để làm cho kết nối chạy.

### 8.4. Revocation và trạng thái thu hồi

Certificate có thể bị thu hồi trước khi hết hạn. CRL và OCSP là các cơ chế phổ biến để phân phối trạng thái thu hồi. Tuy nhiên, **không nên giả định mọi cấu hình JSSE mặc định đều thực hiện online revocation checking theo chính sách mà ứng dụng mong muốn**.

Nếu hệ thống yêu cầu kiểm tra revocation, cần cấu hình và kiểm thử rõ PKIX/OCSP/CRL theo provider, network policy và yêu cầu vận hành. Việc bật revocation có thể tạo thêm phụ thuộc mạng tới responder hoặc CRL distribution point.

## 9. Hostname verification: xác minh server đúng tên

### 9.1. Vì sao chain hợp lệ vẫn chưa đủ?

Giả sử:

- Client gọi `https://payments.example.com`.
- Server trình certificate do một public CA tin cậy ký.
- SAN certificate chỉ có `DNS:marketing.example.com`.

Chain validation thành công không có nghĩa server là `payments.example.com`. Client phải kiểm tra hostname trong URL với SAN của certificate.

Đây là bước hostname verification. HTTPS client chuẩn thực hiện bước này tự động.

### 9.2. Không tắt hostname verification

Một anti-pattern nguy hiểm:

~~~java
// TUYỆT ĐỐI KHÔNG dùng trong ứng dụng:
HostnameVerifier trustEveryHost = (hostname, session) -> true;
HttpsURLConnection.setDefaultHostnameVerifier(trustEveryHost);
~~~

Đoạn code này chấp nhận mọi hostname, kể cả certificate được cấp cho máy chủ khác. Nó làm suy yếu xác thực HTTPS và mở đường cho tấn công man-in-the-middle.

Một anti-pattern khác là TrustManager chấp nhận mọi certificate:

~~~java
// TUYỆT ĐỐI KHÔNG dùng:
// X509TrustManager.checkServerTrusted(...) { } // bỏ trống
// getAcceptedIssuers() { return new X509Certificate[0]; }
~~~

Tắt chain validation và tắt hostname verification là hai lỗi độc lập; chỉ giữ một trong hai cũng chưa đủ để có HTTPS an toàn.

### 9.3. HttpClient và HttpsURLConnection

Với `HttpClient` và `HttpsURLConnection` tiêu chuẩn, hãy giữ cấu hình xác minh hostname mặc định. Khi dùng custom `SSLContext`, mục tiêu là thay đổi trust anchors hoặc client identity theo nhu cầu, **không phải bỏ xác minh hostname**.

Không dùng property nội bộ hoặc cờ debug để tắt hostname verification trong production. Nếu test cần server giả lập, hãy tạo certificate test có SAN khớp hostname test và CA test được trust store test tin cậy.

## 10. Dùng SSLSocket mức thấp và bật endpoint identification

Khi tự mở TLS socket thay vì dùng HTTPS client cấp cao, lập trình viên chịu trách nhiệm cấu hình xác minh endpoint phù hợp.

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import java.net.InetSocketAddress;
import java.net.Socket;

String host = "api.example.com";
int port = 443;

SSLContext context = SSLContext.getDefault();
Socket tcp = new Socket();
tcp.connect(new InetSocketAddress(host, port), 10_000);
try (SSLSocket socket = (SSLSocket) context.getSocketFactory()
        .createSocket(tcp, host, port, true)) {

    SSLParameters parameters = socket.getSSLParameters();
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    parameters.setProtocols(new String[] { "TLSv1.3", "TLSv1.2" });
    socket.setSSLParameters(parameters);

    socket.startHandshake();

    System.out.println("TLS protocol: " +
            socket.getSession().getProtocol());
    System.out.println("Cipher suite: " +
            socket.getSession().getCipherSuite());
}
~~~

Điểm quan trọng là:

- `setEndpointIdentificationAlgorithm("HTTPS")` yêu cầu xác minh tên endpoint theo quy tắc HTTPS.
- `setProtocols(...)` giới hạn protocol được bật cho socket này theo chính sách ví dụ.
- `startHandshake()` thực hiện handshake trước khi ứng dụng sử dụng kênh.
- `getSession()` cho biết phiên TLS đã thương lượng.

Với socket mức thấp, không chỉ kiểm tra chain qua TrustManager rồi cho rằng đã xác thực hostname. Hãy bật endpoint identification. Cũng cần xem xét SNI, đặc biệt khi kết nối tới máy chủ dùng virtual hosting; tạo socket bằng hostname giúp provider có thông tin host để xử lý SNI trong cấu hình thông thường.

Nếu kết nối bằng IP nhưng certificate chỉ có DNS SAN, xác minh sẽ thất bại. Dùng đúng hostname được certificate cấp, hoặc phát hành certificate có IP SAN nếu hợp đồng thực sự dùng IP.

## 11. Mutual TLS (mTLS): khi server cũng cần xác thực client

### 11.1. HTTPS một chiều và mTLS

Trong HTTPS thông thường:

- Client xác minh certificate của server.
- Server không nhất thiết yêu cầu certificate của client.

Trong **mutual TLS (mTLS)**:

- Client xác minh server.
- Server yêu cầu client trình certificate.
- Client dùng private key tương ứng để chứng minh sở hữu danh tính.
- Server xác minh client certificate theo trust store riêng của server.

~~~text
Client                              Server
  |                                  |
  | -------- TLS ClientHello ------> |
  | <------- Server certificate --- |
  |                                  |
  | Verify server chain + hostname  |
  |                                  |
  | <----- CertificateRequest ------ |
  |                                  |
  | ----- Client certificate -----> |
  | ----- CertificateVerify ------> |
  |                                  |
  |                         Verify client chain
  |                                  |
  | <======= TLS channel ===========>|
~~~

### 11.2. Tạo SSLContext với KeyManager và TrustManager

Ví dụ khái niệm:

~~~java
import javax.net.ssl.KeyManagerFactory;
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;

static SSLContext createMtlsContext(
        Path clientKeyStorePath,
        char[] clientKeyStorePassword,
        char[] privateKeyPassword,
        Path serverTrustStorePath,
        char[] serverTrustStorePassword
) throws Exception {
    KeyStore clientKeys = KeyStore.getInstance("PKCS12");
    try (InputStream in = Files.newInputStream(clientKeyStorePath)) {
        clientKeys.load(in, clientKeyStorePassword);
    }

    KeyManagerFactory keyManagerFactory =
            KeyManagerFactory.getInstance(
                    KeyManagerFactory.getDefaultAlgorithm()
            );
    keyManagerFactory.init(clientKeys, privateKeyPassword);

    KeyStore serverTrust = KeyStore.getInstance("PKCS12");
    try (InputStream in = Files.newInputStream(serverTrustStorePath)) {
        serverTrust.load(in, serverTrustStorePassword);
    }

    TrustManagerFactory trustManagerFactory =
            TrustManagerFactory.getInstance(
                    TrustManagerFactory.getDefaultAlgorithm()
            );
    trustManagerFactory.init(serverTrust);

    SSLContext context = SSLContext.getInstance("TLS");
    context.init(
            keyManagerFactory.getKeyManagers(),
            trustManagerFactory.getTrustManagers(),
            null
    );
    return context;
}
~~~

Ở đây:

- Client key store chứa private key và certificate chain của client.
- KeyManagerFactory tạo KeyManager để chọn danh tính client khi server yêu cầu.
- Server trust store chứa CA/certificate mà client tin cậy khi xác minh server.
- TrustManagerFactory tạo TrustManager để kiểm tra peer server.

Phía server cũng phải được cấu hình yêu cầu client certificate và trust client CA phù hợp. Chỉ tạo client SSLContext không tự bật mTLS nếu server không yêu cầu.

### 11.3. Phân quyền và vòng đời private key

Private key client là tài sản nhạy cảm:

- Không commit file key store hoặc password vào repository.
- Hạn chế quyền đọc file theo service account.
- Ưu tiên secret manager, HSM hoặc cơ chế quản lý khóa phù hợp.
- Có quy trình cấp phát, rotation, thu hồi và audit.
- Không ghi private key hoặc password vào log.

Không dùng trust store làm nơi lưu private key của client chỉ vì cả hai đều là file KeyStore. Hai loại dữ liệu có vai trò khác nhau.

## 12. Cấu hình TLS bằng system properties

JSSE hỗ trợ các system properties để cấu hình trust store mặc định khi JVM khởi động:

~~~shell
java ^
  -Djavax.net.ssl.trustStore=config/app-truststore.p12 ^
  -Djavax.net.ssl.trustStoreType=PKCS12 ^
  -Djavax.net.ssl.trustStorePassword=<secret-from-runtime> ^
  -jar application.jar
~~~

Trên shell Unix, dùng cú pháp nối dòng tương ứng. Không đưa secret thật vào script được commit hoặc lịch sử shell nếu có thể tránh.

System properties tác động đến cấu hình JSSE mặc định của JVM và có phạm vi rộng hơn một client cụ thể. Nếu chỉ một `HttpClient` cần trust store riêng, tạo SSLContext riêng và truyền vào builder thường dễ kiểm soát hơn.

Khi thay đổi trust store:

- Kiểm tra file tồn tại, loại keystore và mật khẩu.
- Kiểm tra certificate được import đúng alias.
- Xác minh fingerprint/nguồn CA qua kênh đáng tin.
- Kiểm tra ứng dụng thực sự dùng SSLContext/trust store mới.
- Xem xét lifecycle của HttpClient/SSLContext; client đã tạo có thể tiếp tục dùng context cũ.

## 13. Chẩn đoán lỗi HTTPS trong Java

### 13.1. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng điều tra |
|---|---|---|
| `PKIX path building failed` | Không dựng được chain tới trust anchor | Kiểm tra trust store, CA và intermediate server gửi |
| `unable to find valid certification path` | CA không được tin hoặc chain thiếu | Xem certificate chain và trust anchors |
| `CertificateExpiredException` | Leaf/intermediate/root hết hạn | Kiểm tra validity và đồng hồ máy |
| `No subject alternative DNS name matching ...` | SAN không khớp hostname URL | Kiểm tra URL và SAN certificate |
| `No subject alternative names matching IP address ...` | URL dùng IP nhưng certificate thiếu IP SAN tương ứng | Dùng hostname đúng hoặc phát hành IP SAN |
| `SSLHandshakeException` | Lỗi tổng quát trong TLS handshake | Đọc cause lồng bên trong và debug handshake |
| `protocol_version` | Không có TLS version chung hoặc server chỉ hỗ trợ phiên bản cũ | Kiểm tra protocol policy ở hai đầu |
| `handshake_failure` | Có thể do cipher, key algorithm, client auth hoặc policy | Kiểm tra server log và TLS debug |
| `bad_certificate`/client certificate rejected | mTLS certificate không phù hợp hoặc không được server tin | Kiểm tra client key store, chain và trust của server |
| `UnrecoverableKeyException` | Password private key sai hoặc không đọc được key entry | Kiểm tra alias và password riêng của private key |
| `NoSuchAlgorithmException` | Provider không có algorithm/context được yêu cầu | Kiểm tra JDK/provider và tên algorithm |

Không kết luận từ class exception ngoài cùng. `SSLHandshakeException` thường bọc một nguyên nhân cụ thể hơn như `CertPathValidatorException`.

### 13.2. Xem certificate của server

`keytool` có thể hiển thị certificate:

~~~shell
keytool -printcert -sslserver api.example.com:443
~~~

Có thể kiểm tra:

- Subject và issuer.
- Validity.
- SAN.
- Public key và signature algorithm.
- Chain mà server trình.

Lệnh này là công cụ chẩn đoán; kết quả hiển thị không thay thế kiểm tra bảo mật của ứng dụng và không nên tự động import certificate vừa xem mà không xác minh nguồn tin cậy.

### 13.3. Bật JSSE debug có kiểm soát

Để điều tra handshake, có thể chạy trong môi trường phát triển:

~~~shell
java -Djavax.net.debug=ssl,handshake,trustmanager -jar application.jar
~~~

Log có thể rất dài và chứa thông tin về certificate, handshake, địa chỉ và cấu hình. Chỉ bật khi cần, giới hạn quyền truy cập log và tắt sau khi điều tra. Không dùng debug log làm cách khắc phục lỗi bằng cách bỏ validation.

### 13.4. Trình tự điều tra đề xuất

1. Xác nhận URL, hostname và port chính xác.
2. Xác nhận thời gian hệ thống.
3. Xem certificate chain server gửi.
4. Kiểm tra trust store JVM/client thực sự đang sử dụng.
5. Kiểm tra hostname/SAN.
6. Kiểm tra TLS version/cipher/provider.
7. Nếu mTLS, kiểm tra client certificate và server trust.
8. Bật JSSE debug ở môi trường kiểm soát nếu nguyên nhân vẫn chưa rõ.

Sửa đúng cấu hình server, certificate hoặc trust anchor. Không tắt xác minh chain hoặc hostname để “thử cho chạy”.

## 14. Kiểm thử HTTPS cục bộ một cách an toàn

### 14.1. Dùng CA test riêng

Để kiểm thử client với server tự ký hoặc CA test:

1. Tạo certificate server cho hostname test, có SAN phù hợp.
2. Tạo CA test hoặc certificate test theo quy trình kiểm thử.
3. Import CA test vào trust store riêng chỉ dành cho test.
4. Kết nối bằng URL có hostname khớp SAN.
5. Kiểm tra trường hợp hợp lệ và trường hợp certificate không khớp hostname.

Không đưa CA test hoặc trust store test vào production.

### 14.2. Test các tình huống phải bị từ chối

Một bộ test hữu ích nên bao gồm:

- Certificate do CA không được tin cậy ký.
- Certificate hết hạn.
- Certificate chưa có hiệu lực.
- Certificate chain thiếu intermediate.
- Hostname URL không khớp SAN.
- Certificate không có mục đích server authentication phù hợp.
- TLS protocol không có phiên bản chung.
- Server yêu cầu mTLS nhưng client không trình certificate.
- Client trình certificate sai CA hoặc hết hạn.

Mục tiêu không chỉ là test request thành công, mà còn xác nhận client **từ chối đúng các peer không hợp lệ**.

### 14.3. Không dùng trust-all trong unit test

Một test có thể tạo server local với CA test và trust store test. Cách này giữ nguyên cơ chế xác minh thực tế. Một TrustManager chấp nhận mọi certificate khiến test không còn kiểm tra được chain validation và có thể che lỗi production.

Nếu chỉ test business logic không liên quan TLS, mock HTTP boundary hoặc dùng test server có certificate hợp lệ thay vì tắt xác minh toàn cục.

## 15. Những hiểu nhầm thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “HTTPS chỉ cần mã hóa dữ liệu.” | Cần xác thực server bằng certificate chain và hostname nữa. |
| “SSLContext tự kiểm tra mọi thứ.” | SSLContext tạo socket/engine theo các manager; TrustManager và endpoint identification thực hiện các phần xác minh tương ứng. |
| “Certificate do CA tin cậy ký thì dùng được cho mọi hostname.” | Hostname phải khớp SAN của certificate. |
| “Trust store và key store là một.” | Trust store lưu trust anchors; key store thường chứa private key/certificate identity của local side. |
| “Custom trust store chỉ thêm CA mới vào default trust store.” | Khi cấu hình trust manager từ trust store riêng, tập trust anchors có thể thay thế tập mặc định; phải quản lý đầy đủ roots cần thiết. |
| “Server gửi root certificate là client tự tin.” | Client cần trust anchor được cấu hình tin cậy; certificate tự gửi không tự tạo niềm tin. |
| “Tắt hostname verifier là cách sửa SAN mismatch.” | Điều đó bỏ xác minh danh tính host và làm HTTPS yếu đi. |
| “TrustManager chấp nhận mọi certificate chỉ dùng trong test là an toàn.” | Nó làm mất kiểm tra chain; dùng CA test và trust store test đúng chuẩn. |
| “Dùng `SSLContext.getInstance("TLSv1.3")` là cách duy nhất để dùng TLS 1.3.” | Có thể dùng context `TLS` và cấu hình protocol parameters/policy phù hợp. |
| “TLS 1.0/1.1 nên bật nếu server cũ không kết nối được.” | Các protocol này đã lỗi thời; nên nâng cấp server hoặc xử lý ngoại lệ theo chính sách bảo mật. |
| “HTTPS client luôn cần client certificate.” | Chỉ cần khi server yêu cầu mTLS/client authentication. |
| “Có certificate hợp lệ là đã kiểm tra revocation.” | Revocation checking là cấu hình/chính sách riêng; không giả định luôn được bật. |
| “Console charset hoặc default charset ảnh hưởng TLS certificate.” | Charset của console không liên quan đến việc xác minh certificate chain/hostname. |

## 16. Ví dụ tổng hợp: HTTPS client với CA riêng và xác minh server

File **VerifiedHttpsClient.java**:

~~~java
import javax.net.ssl.SSLContext;
import javax.net.ssl.TrustManagerFactory;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.time.Duration;

public class VerifiedHttpsClient {

    static SSLContext loadTrustContext(
            Path path,
            char[] password
    ) throws Exception {
        KeyStore trustStore = KeyStore.getInstance("PKCS12");
        try (InputStream in = Files.newInputStream(path)) {
            trustStore.load(in, password);
        }

        TrustManagerFactory tmf = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
        tmf.init(trustStore);

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, tmf.getTrustManagers(), null);
        return context;
    }

    public static void main(String[] args) throws Exception {
        Path trustStorePath = Path.of(
                "config", "internal-ca-truststore.p12"
        );
        char[] password = readSecretFromApprovedSource();

        try {
            SSLContext context =
                    loadTrustContext(trustStorePath, password);

            HttpClient client = HttpClient.newBuilder()
                    .sslContext(context)
                    .connectTimeout(Duration.ofSeconds(10))
                    .build();

            HttpRequest request = HttpRequest.newBuilder()
                    .uri(URI.create(
                            "https://api.internal.example/health"
                    ))
                    .timeout(Duration.ofSeconds(15))
                    .GET()
                    .build();

            HttpResponse<String> response = client.send(
                    request,
                    HttpResponse.BodyHandlers.ofString()
            );

            System.out.println("HTTP status: " + response.statusCode());
            System.out.println(response.body());
        } finally {
            java.util.Arrays.fill(password, '\0');
        }
    }

    private static char[] readSecretFromApprovedSource() {
        // Placeholder: lấy secret từ secret manager hoặc runtime config.
        throw new UnsupportedOperationException(
                "Cấu hình nguồn secret cho môi trường triển khai"
        );
    }
}
~~~

Ví dụ cho thấy các thành phần chính nhưng cố ý để `readSecretFromApprovedSource()` là placeholder vì cách lấy secret phụ thuộc nền tảng triển khai. Khi hoàn thiện:

- Trust store phải được cấp từ nguồn đáng tin và chứa CA cần thiết.
- URL hostname phải khớp SAN của server certificate.
- `HttpClient` giữ hostname verification mặc định.
- Không có TrustManager/HostnameVerifier bỏ qua validation.
- Password không được ghi cứng trong source.

Biên dịch phần mã sau khi cung cấp implementation cho hàm lấy secret:

~~~shell
javac --release 17 VerifiedHttpsClient.java
java VerifiedHttpsClient
~~~

## 17. Bài tập thực hành

### Bài 1 — Quan sát default HTTPS

Viết một `HttpClient` gửi GET tới một endpoint HTTPS công khai mà bạn được phép truy cập. In HTTP status và TLS protocol/cipher nếu môi trường có cách quan sát tương ứng. Giải thích vì sao không cần tự tạo TrustManager cho CA công khai được JDK tin cậy.

### Bài 2 — Tạo trust store cho CA nội bộ

Trong môi trường lab, lấy certificate CA test từ nguồn tin cậy, xác minh fingerprint, import vào PKCS12 trust store bằng `keytool`. Dùng TrustManagerFactory và SSLContext để cấu hình một client riêng.

Không import certificate tùy ý lấy từ kết nối thất bại mà không xác minh nguồn.

### Bài 3 — Phân biệt chain validation và hostname verification

Tạo hai endpoint test:

- Endpoint có certificate chain được trust store tin nhưng SAN đúng host.
- Endpoint có chain được trust nhưng SAN thuộc hostname khác.

Quan sát trường hợp đầu thành công và trường hợp sau bị từ chối. Giải thích vì sao thêm CA vào trust store không thể sửa hostname mismatch.

### Bài 4 — Phân tích lỗi PKIX

Thử kết nối endpoint test với trust store không chứa CA tương ứng. Đọc `SSLHandshakeException` và cause lồng bên trong. Sau đó thêm đúng CA test vào trust store và giải thích thay đổi.

### Bài 5 — Dùng SSLSocket

Tạo một `SSLSocket` tới hostname test, bật `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`, giới hạn TLS 1.3/1.2 và gọi `startHandshake()`. Thử dùng hostname không khớp SAN để xác nhận handshake thất bại.

### Bài 6 — mTLS

Trong lab, tạo client key store PKCS12 có certificate/private key, server trust store tin CA client, và client trust store tin CA server. Dùng KeyManagerFactory + TrustManagerFactory để tạo SSLContext. Kiểm tra server từ chối client thiếu certificate và chấp nhận client có identity hợp lệ.

### Bài 7 — Điều tra handshake

Bật `-Djavax.net.debug=ssl,handshake,trustmanager` trong môi trường kiểm thử, đọc log về certificate chain, trust decision và protocol negotiation. Nêu lý do không nên để debug bật liên tục trong production.

## 18. Câu hỏi tự kiểm tra

1. HTTPS bổ sung những thuộc tính bảo mật nào so với HTTP?
2. Vai trò của TLS handshake là gì?
3. Certificate chain và trust anchor khác nhau thế nào?
4. TrustManagerFactory tạo thành phần nào của SSLContext?
5. KeyManagerFactory được dùng trong tình huống nào?
6. Khác nhau giữa trust store và key store?
7. Vì sao certificate chain hợp lệ chưa đủ để xác minh hostname?
8. SAN có vai trò gì và vì sao không nên dựa vào CN?
9. Vì sao custom trust store có thể làm client không còn tin public CA mặc định?
10. `SSLContext.getInstance("TLS")` có đồng nghĩa chỉ bật TLS 1.3 không?
11. Vì sao không nên bật SSLv3/TLS 1.0/TLS 1.1 để sửa lỗi tương thích?
12. HttpClient và HttpsURLConnection xử lý hostname verification mặc định ra sao?
13. Khi dùng SSLSocket trực tiếp, vì sao phải bật endpoint identification algorithm HTTPS?
14. mTLS khác HTTPS một chiều thế nào?
15. `PKIX path building failed` thường chỉ ra nhóm vấn đề nào?
16. Revocation checking có luôn được bật theo ý muốn của ứng dụng không?
17. Vì sao TrustManager chấp nhận mọi certificate là nguy hiểm?
18. Làm thế nào kiểm thử TLS mà không tắt xác minh certificate?

## 19. Tài liệu tham khảo

- [Java SE 17 API — SSLContext](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLContext.html): tạo context, khởi tạo key/trust managers và tạo socket factory.
- [Java SE 17 API — TrustManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html): tạo trust managers từ trust store.
- [Java SE 17 API — KeyManagerFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/KeyManagerFactory.html): tạo key managers từ key store.
- [Java SE 17 API — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): cấu hình protocol, cipher và endpoint identification.
- [Java SE 17 API — HttpClient](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): cấu hình HTTPS client và SSLContext.
- [Java SE 17 API — HttpsURLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/HttpsURLConnection.html): HTTPS qua URLConnection và các cấu hình TLS liên quan.
- [Java SE 17 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): trust store, key store, TLS, certificate validation và JSSE properties.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): đặc tả TLS 1.3.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): quy tắc xác minh danh tính dịch vụ và hostname trong TLS.

Khi triển khai HTTPS trên Java 17, hãy giữ nguyên cả hai lớp xác minh: **TrustManager kiểm tra certificate chain tới trust anchor**, còn **hostname verification xác nhận certificate dành cho đúng host trong URL**. Dùng `SSLContext` để cấu hình trust/key material theo nhu cầu, giữ các protocol TLS hiện đại, và chỉ bật mTLS khi hợp đồng yêu cầu client certificate. Không dùng trust-all hoặc hostname verifier luôn chấp nhận; nếu kết nối thất bại, hãy sửa chain, SAN, trust store hoặc cấu hình TLS tại đúng nguyên nhân.
