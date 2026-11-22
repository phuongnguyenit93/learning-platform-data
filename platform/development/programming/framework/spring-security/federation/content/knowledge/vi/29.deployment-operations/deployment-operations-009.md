# Giới hạn thời gian chờ và kết nối khi gọi metadata, CAS hoặc dịch vụ thư mục

## 1. Vì sao đây là yêu cầu vận hành của hệ thống federation?

Trong **Spring Security - federation**, nhiều bước xác thực phải truy cập tài nguyên bên ngoài: lấy SAML2 IdP metadata, tải OIDC discovery/JWKS, gọi back-channel CAS để kiểm service ticket, bind/search LDAP/Active Directory, hoặc truy vấn group membership. Nếu một endpoint bị treo mà client chưa cấu hình thời gian chờ, một yêu cầu đăng nhập có thể giữ thread, socket, connection pool và session quá lâu. Khi nhiều người cùng đăng nhập, lỗi chậm từ một IdP hoặc directory có thể lan thành nghẽn web server, hết thread pool, cạn file descriptors và mất dịch vụ.

**Mục tiêu của bài** là đặt giới hạn **theo từng công đoạn**, có **deadline chung cho login**, quản lý kết nối/pool, phân biệt lỗi mạng với tài khoản sai và bảo đảm **fail closed**: timeout không bao giờ đồng nghĩa đã xác thực thành công.

Bài thuộc nhóm **Triển khai và vận hành**. Môi trường minh họa: **Java 17+, Spring Boot 3.3.5, Spring Security 6.x**, SAML2 Service Provider, OAuth2/OIDC, CAS ticket validation, LDAP/Active Directory dùng Spring LDAP/JNDI. Mọi địa chỉ `example.org` đều là ví dụ, không phải endpoint đang tồn tại.

### Sau bài này, người học phải làm được

1. Phân biệt connect timeout, response/read timeout, request timeout, pool acquisition timeout, LDAP search time limit và **end-to-end login deadline**.
2. Gán ngân sách thời gian riêng cho **metadata**, **CAS** và **LDAP**, không dùng một giá trị cho tất cả.
3. Cấu hình HTTP client có bounded waits, TLS trust, redirect/response-size policy và nguồn endpoint allowlist.
4. Đưa SAML metadata đã tải/kiểm tin cậy vào `RelyingPartyRegistrations.fromMetadata(InputStream)`; không nhầm tải dữ liệu với xác minh metadata trust.
5. Giới hạn network time của back-channel CAS; biết vì sao không retry mù quáng cùng **single-use service ticket**.
6. Cấu hình `com.sun.jndi.ldap.connect.timeout` và `com.sun.jndi.ldap.read.timeout` cho LDAP bind/search; giới hạn pool, search result size và referrals.
7. Triển khai retry có giới hạn, bounded caches, circuit breaker, metrics/alerts và negative tests mà vẫn giữ security.
8. Chạy Java 17 demo trên loopback để quan sát fast response và timeout một cách an toàn.

## 2. Luồng đăng nhập và điểm gọi ra mạng

~~~text
Browser  --->  Spring Security app  -------------------->  External systems
                   |
                   +-- SAML2 registration bootstrap/refresh
                   |      -> HTTPS GET IdP metadata
                   |      -> parse XML, verify metadata trust
                   |      -> trusted IdP signing certificates
                   |
                   +-- OIDC login / resource server
                   |      -> HTTPS GET discovery/JWKS
                   |      -> verify token signature and issuer/claims
                   |      -> optional OIDC token/userinfo endpoint
                   |
                   +-- CAS
                   |      -> HTTPS /serviceValidate or /proxyValidate
                   |      -> validate one-time ticket + service URL
                   |
                   +-- LDAP / Active Directory
                          -> TCP + TLS (LDAPS or StartTLS)
                          -> bind and search user/groups
                          -> local authorization
~~~

Các lời gọi không nhất thiết diễn ra trong cùng một request: SAML metadata có thể tải lúc startup hoặc refresh định kỳ; JWKS thường cache; CAS ticket validation diễn ra lúc callback; LDAP bind và tìm nhóm có thể là mỗi lần login hoặc một phần của phiên. **Chọn thời gian chờ theo vị trí trong flow**, thay vì mặc định tất cả đều nằm trên đường xử lý của người dùng.

### Timeout ở lớp nào?

| Loại giới hạn | Ý nghĩa | Nếu chỉ đặt loại này |
| --- | --- | --- |
| **DNS/resolver delay** | Thời gian phân giải hostname thành IP. | Không phải mọi Java client/OS bảo đảm DNS bị ràng buộc bởi connect timeout. |
| **Connect timeout** | Chờ tạo kết nối TCP và các bước kết nối theo implementation. | Không giới hạn thời gian đợi response sau khi kết nối; không áp dụng nếu tái sử dụng connection. |
| **TLS handshake timeout** | Chờ bắt tay TLS, CA/hostname validation. | Không giới hạn body hoặc LDAP search. Một số client gộp vào connect; phải kiểm implementation. |
| **Read/socket timeout** | Khoảng chờ đọc dữ liệu hoặc nhận phản hồi sau khi kết nối. | Thường là **inactivity timeout theo lần đọc**, không phải tổng thời gian toàn request. |
| **HTTP request/response timeout** | Giới hạn ở tầng request theo HTTP client. | Ngữ nghĩa phụ thuộc JDK/library, phiên bản và giai đoạn headers/body. |
| **Pool acquire timeout** | Chờ lấy một connection từ pool khi pool bận. | Không giới hạn connect/read của connection đã cấp. |
| **LDAP search time limit** | Hạn thời gian/trả kết quả cho search operation. | Không thay connect/read timeout hoặc limit số entries. |
| **Login deadline** | Tổng ngân sách cho request xác thực gồm nhiều công đoạn. | Cần kết hợp với timeouts từng transport, cancellation và resource cleanup. |
| **Session/token TTL** | Hạn dùng phiên/ticket/assertion, không phải network wait. | Không chữa treo kết nối LDAP/CAS. |

**Quan trọng với Java 17:** `HttpClient.Builder.connectTimeout(Duration)` chỉ áp dụng khi cần **kết nối mới**, không có tác dụng với connection đã reuse. `HttpRequest.Builder.timeout(Duration)` trong JDK 17 giới hạn thời gian **đợi response**; không được giả định nó là hard deadline bao cả việc đọc một body streaming chậm. Bắt đầu từ những JDK mới hơn phạm vi thực thi timeout đã thay đổi, vì vậy kiểm đúng runtime. Nếu cần budget toàn bộ payload, phải có kích thước tối đa, lifecycle/cancellation và client được thiết kế cho whole-response deadline.

### Vì sao không đặt timeout bằng 0?

Với các APIs như `HttpURLConnection.setConnectTimeout(0)` và `setReadTimeout(0)`, 0 thường biểu thị **không giới hạn** theo timeout riêng đó; `com.sun.jndi.ldap.read.timeout` JNDI nếu không đặt/không dương có thể đợi vô hạn. Đọc tài liệu chính xác của client. Không copy một cấu hình `timeout=0` rồi tưởng là “không đợi”.

## 3. Lập ngân sách thời gian và giới hạn số kết nối

Giả sử mục tiêu user-facing **login dưới 6 giây** ở ngưỡng được tổ chức chọn (chỉ là ví dụ, không phải chuẩn chung). Một flow có thể dành:

~~~text
Tổng ngân sách ví dụ: 6 000 ms

Application routing, session, crypto, redirects: 1 000 ms
CAS validation HTTPS:                   tối đa 2 000 ms
LDAP bind + search + group lookup:      tối đa 2 000 ms
Dự phòng/cleanup:                       1 000 ms

Từng lời gọi vẫn cần:
  DNS / connect / TLS
  wait-to-acquire connection
  response/read
  parse and authorization
~~~

Nếu CAS đã chiếm 2 giây, LDAP không được mặc nhiên kéo dài login thêm 5 giây. Một deadline tổng sẽ được tính từ **monotonic clock** (`System.nanoTime()` cho elapsed time), rồi phần ngân sách còn lại phải được đưa cho từng outbound call/cancellation. Các giá trị trên là minh họa, cần đo theo latency của môi trường thật, vùng địa lý, số hops và IdP contract.

**Đặt timeouts theo tầng, không cộng nhầm:**

- HTTP metadata refresh chạy nền: có thể cho connect 2 giây, đọc 3 giây, max body 1 MiB và retry 1 lần sau jitter nếu policy cho phép; nhưng cần tổng refresh deadline riêng.
- CAS ticket callback: thường cần phản hồi nhanh; ví dụ connect 1 giây, read 2 giây, deadline 3 giây, **không tự retry single-use ticket**.
- LDAP user bind và group search: ví dụ connect 1,5 giây, read 2,5 giây mỗi operation, search result time/size giới hạn, tổng login budget theo chuỗi operations.
- Pool acquisition: ví dụ wait tối đa 200–500 ms, tránh hàng trăm request đồng thời đợi pool mãi.
- Metadata/JWKS không nên tải từ network ở **mỗi HTTP request** nếu có thể dùng trusted cache và refresh chủ động.

Các số này **không phải mặc định Spring Boot**. Chúng phải được cấu hình ở HTTP client, library hoặc JNDI thực sự được dùng. Một thuộc tính `app.timeout` chỉ là custom application property cho tới khi code gắn nó vào client.

### Khuyến nghị pool capacity

Chọn tối đa số kết nối theo concurrency, không chỉ số người dùng. Ví dụ 100 request/giây, mỗi outbound call chiếm trung bình 150 ms thì số kết nối đồng thời trung bình xấp xỉ **15** (100 × 0,15). Pool 30 có thể là điểm kiểm thử ban đầu, **không tự là cấu hình đúng** ở tail latency hay khi CAS/LDAP chậm. Tối đa hóa pool mà không giới hạn upstream sẽ đẩy nghẽn sang KDC/LDAP/CAS. Cần đo per-route active/idle/pending, per-server limits, TCP file descriptors và retry fan-out.

## 4. HTTP metadata: timeout không thể thay trust

### 4.1. Khi nào nạp SAML metadata?

`RelyingPartyRegistrations.fromMetadataLocation("https://...")` có thể tải metadata IdP qua HTTP khi dựng registration. Nếu startup phụ thuộc endpoint này, IdP timeout có thể khiến application startup treo hoặc thất bại. Với **Spring Security 6.x**, có thể tự tải theo cơ chế do ứng dụng quản lý rồi gọi:

~~~java
RelyingPartyRegistrations.fromMetadata(inputStream)
~~~

Phương thức nhận `InputStream` thích hợp cho metadata được lưu ở database, file snapshot hoặc do một HTTP client bên ngoài nạp. **Caller chịu trách nhiệm đóng InputStream.** Mẫu này giúp tách network fetch/bounded waits khỏi parsing/registration, không biến endpoint HTTP thành trust anchor tự động.

### 4.2. Java 17: tải metadata với HTTP connect/read timeout

**BoundedMetadataFetch.java** — class Java 17 độc lập, chạy được nếu thay endpoint bằng URI metadata HTTPS được phê duyệt. Mã chỉ làm **fetch transport**; **không tự xác minh XML signature, IdP EntityID hoặc certificate trust**.

~~~java
import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.HttpURLConnection;
import javax.net.ssl.HttpsURLConnection;

public final class BoundedMetadataFetch {
    private static final URI APPROVED = URI.create(
        "https://idp.example.org/saml/metadata");
    private static final int MAX_BYTES = 1_048_576; // 1 MiB

    private BoundedMetadataFetch() {}

    public static byte[] load(URI requested) throws IOException {
        // URI được cấu hình từ trusted deployment, không từ browser.
        if (!APPROVED.equals(requested)
                || !"https".equalsIgnoreCase(requested.getScheme())) {
            throw new IOException("Metadata endpoint not allowlisted");
        }

        HttpsURLConnection connection =
            (HttpsURLConnection) requested.toURL().openConnection();
        connection.setConnectTimeout(2_000);
        connection.setReadTimeout(3_000);
        connection.setInstanceFollowRedirects(false);
        connection.setRequestProperty(
            "Accept", "application/samlmetadata+xml, application/xml");

        try {
            int status = connection.getResponseCode();
            if (status != HttpURLConnection.HTTP_OK) {
                throw new IOException(
                    "Metadata HTTP status: " + status);
            }
            try (InputStream stream = connection.getInputStream()) {
                byte[] bytes = stream.readNBytes(MAX_BYTES + 1);
                if (bytes.length > MAX_BYTES) {
                    throw new IOException("Metadata exceeds 1 MiB");
                }
                if (bytes.length == 0) {
                    throw new IOException("Empty metadata");
                }
                return bytes;
            }
        } finally {
            connection.disconnect();
        }
    }

    public static void main(String[] args) throws IOException {
        // Chạy với approved HTTPS endpoint thực, KHÔNG phải example.org.
        byte[] bytes = load(APPROVED);
        System.out.println("Downloaded bytes: " + bytes.length);
    }
}
~~~

Biên dịch:

~~~bash
javac BoundedMetadataFetch.java
java BoundedMetadataFetch
~~~

Không có **stdout cố định** vì server metadata thật phải tồn tại và trả nội dung khác nhau; `example.org` là minh họa. Nếu endpoint không tồn tại, chương trình phải báo lỗi thay vì in thành công. `setConnectTimeout` giới hạn kết nối; `setReadTimeout` giới hạn **thời gian chờ giữa các lần đọc**, không phải hard deadline nếu peer gửi cực chậm nhưng liên tục. Để bảo vệ toàn bộ refresh cần deadline/cancellation ở orchestration, giới hạn body, cache và quota connections. Với HTTP redirect khác origin, mẫu sẽ **không follow**; nếu IdP yêu cầu redirect, phải xét allowlist và TLS trust từng hop theo policy.

Mặc định Java TLS trust/hostname verification vẫn phải hoạt động. Không thêm trust-all `HostnameVerifier` hoặc custom SSLContext chấp nhận mọi certificate để vượt lỗi môi trường.

### 4.3. Đưa bytes đã fetch vào Spring SAML registration

Đây là **fragment trong Spring Boot app**, không phải file Java chạy độc lập nếu thiếu dependencies:

~~~java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.net.URI;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.saml2.provider.service.registration.*;

@Configuration
public class SamlRegistrationConfig {

    @Bean
    RelyingPartyRegistrationRepository relyingParties()
            throws Exception {
        URI uri = URI.create(
            "https://idp.example.org/saml/metadata");
        byte[] trustedTransportBytes =
            BoundedMetadataFetch.load(uri);

        // Cần xác minh nguồn/metadata signature và IdP EntityID
        // theo policy TRƯỚC khi coi signing keys là trusted.
        try (InputStream input =
                new ByteArrayInputStream(trustedTransportBytes)) {
            RelyingPartyRegistration corp =
                RelyingPartyRegistrations
                    .fromMetadata(input)
                    .registrationId("corp")
                    .entityId(
                        "https://sp.example.org/saml2/service-provider-metadata/corp")
                    .assertionConsumerServiceLocation(
                        "https://sp.example.org/login/saml2/sso/corp")
                    .build();
            return new InMemoryRelyingPartyRegistrationRepository(
                corp);
        }
    }
}
~~~

Cảnh báo ranh giới tin cậy: `BoundedMetadataFetch` **chỉ** cung cấp timeout, HTTPS, allowlist, body cap. Nó **chưa xác minh XML metadata signature hoặc pin được IdP signing credentials theo chính sách**. Trong production phải thêm trust validation riêng: metadata signed bằng key quản trị đã provision, approved IdP EntityID và endpoints, verification certificate inventory, TTL/validUntil, atomic promotion. **Không cho rằng gọi `fromMetadata` đã chứng minh publisher đáng tin.**

Nếu metadata refresh fail:
- Không lấy body XML một phần để cập nhật public verification keys.
- Không chuyển sang arbitrarily trusted metadata từ URL khác.
- Có thể tiếp tục dùng **last-known-good snapshot** đã được xác thực nếu **chưa hết hạn và chính sách an toàn cho phép**, có alert tuổi metadata.
- Khi snapshot hết trust validity hoặc không có key được tin, hệ thống **fail closed** với các login không thể xác minh, chứ không bypass signature.
- Refresh off request path, ghi version/fingerprint, promote atomically sau khi parse/trust pass, tránh mỗi node tự có key khác.

**OIDC discovery/JWKS** cũng là outbound HTTPS với connect/request timeout, cache và bounded refresh. Nhưng không dùng JWKS URI do JWT header `jku`/`x5u` tự khai; JWKS phải đến từ trusted issuer configuration/discovery, không lấy key bất kỳ khi unknown kid.

## 5. Java 17 HttpClient: connectTimeout không phải deadline của body

JDK 17 cung cấp `java.net.http.HttpClient`:

~~~java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class HttpClientExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newBuilder()
            .connectTimeout(Duration.ofSeconds(2))
            .followRedirects(HttpClient.Redirect.NEVER)
            .build();

        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("https://idp.example.org/metadata"))
            .timeout(Duration.ofSeconds(4))
            .GET()
            .build();

        HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());
        System.out.println(response.statusCode());
    }
}
~~~

Đây là cấu hình transport minh họa; URL ví dụ có thể lỗi, không có stdout đảm bảo. Không dùng `BodyHandlers.ofString()` để đọc metadata không giới hạn dung lượng trong production; cần **bounded body handling** theo library, và validation metadata sau tải.

**Lưu ý Java 17:** timeout của `HttpRequest` theo tài liệu đến lúc nhận response; đối với body streaming chậm không tự là bảo đảm hết mọi reads đúng deadline. JDK 26 mở rộng semantics để bao cả response body; không được dùng hành vi JDK 26 để suy ra hành vi JDK 17. Connection reuse làm `connectTimeout` không được áp dụng ở mỗi request. Phải test timeout chính xác trên JDK/container/HTTP client đang chạy.

## 6. CAS: back-channel ticket validation phải có giới hạn mạng

### 6.1. CAS service ticket validation ở đâu trong flow?

~~~text
User trình CAS ticket cho Spring CAS Service:
  Browser -> /login/cas?ticket=ST-... (một lần)

Spring CAS authentication:
  CasAuthenticationProvider -> TicketValidator
  -> HTTPS GET https://cas.example.org/cas/serviceValidate
     ?service=<exact-service-url>&ticket=<single-use-ticket>
  -> CAS response success/failure
  -> verified principal + local authorities
~~~

Spring Security CAS tích hợp với CAS Java Client `Cas20ServiceTicketValidator` hoặc proxy validator tương ứng. **CAS ticket validation là HTTP back-channel**; nếu endpoint treo, login callback có thể chiếm servlet threads lâu. Việc set login redirect timeout của browser **không đặt timeout cho ticket validator trong Java**.

Thời gian chờ cần gắn vào **HTTP connection factory/HTTP transport mà phiên bản CAS Java Client thực sự dùng**. Trong các CAS Java Client versions có `AbstractUrlBasedTicketValidator#setURLConnectionFactory(...)` để thiết lập `HttpURLConnectionFactory`; nếu sử dụng version khác, cần kiểm API và không giả định các bean properties giống nhau.

### 6.2. Hợp đồng timeouts cho CAS validator

~~~text
Trusted CAS base URL: https://cas.example.org/cas
Validation endpoint: /serviceValidate hoặc /proxyValidate theo profile
Connect timeout: 1 000 ms (ví dụ)
Read timeout:    2 000 ms (ví dụ)
Total callback deadline: 3 000 ms (ví dụ, gồm pool wait/parse)
Redirect policy: không tự follow tới origin lạ
TLS: validate hostname/CA, không trust-all
Retry: không tự lặp validation bằng cùng one-time ticket
Result timeout: AUTHENTICATION NOT ESTABLISHED
~~~

Đoạn trên là **security/transport contract**, không phải properties có sẵn của Spring Security CAS. Kiểm phiên bản `org.apereo.cas.client` hoặc legacy CAS client đang sử dụng, sau đó cấu hình đúng URLConnectionFactory/HTTP client với `setConnectTimeout` và `setReadTimeout`, hoặc pool/request timeouts tương ứng. **Đừng chỉ thêm `spring.cas.timeout` vào YAML rồi tin rằng CAS client đã đọc nó**.

Trên `HttpURLConnection`, đoạn **minh họa để chèn vào CAS library's URLConnection factory** (không phải ticket validator độc lập):

~~~java
import java.net.HttpURLConnection;

// connection đến từ trusted CAS library/factory.
static HttpURLConnection configureCasConnection(
        HttpURLConnection connection) {
    connection.setConnectTimeout(1_000);
    connection.setReadTimeout(2_000);
    connection.setInstanceFollowRedirects(false);
    return connection;
}
~~~

Nếu thay factory có sẵn, không bỏ **custom TLS trust/hostname verification** mà CAS client của tổ chức đang sử dụng. Nên giữ HTTPS socket factory/trust store đã phê duyệt và chỉ thêm timeout. Đảm bảo `service` URL được canonically configured theo public HTTPS domain; một CAS service ticket chỉ dùng cho **service chính xác** mà nó được cấp, không được xác minh cho arbitrary callback URL.

### 6.3. Khi CAS timeout có được retry không?

**Không tự động retry cùng service ticket** như một GET metadata thông thường. CAS service tickets thường là **one-time use**; một timeout có thể xảy ra **sau khi CAS đã xử lý/tiêu thụ ticket nhưng trước khi client nhận response**. Nếu client lặp lại cùng ticket, validation có thể trả invalid, tạo retry storm hoặc confusing login state.

Hành vi an toàn:
- Phân loại `CAS_VALIDATION_TIMEOUT` khác `INVALID_SERVICE_TICKET` và `BAD_CREDENTIALS`.
- Không tạo Authentication từ ticket chưa được validate.
- Trả trang lỗi login tạm thời hoặc yêu cầu người dùng **khởi tạo lại CAS authentication flow để lấy ticket mới**.
- Không log raw `ticket=ST-...` trong reverse-proxy logs, URLs, traces hoặc metrics.
- Giới hạn retry tập trung ở **health check/idempotent metadata fetch**, không ở validation of single-use credentials.
- Với proxy ticket (`/proxyValidate`), vẫn phải kiểm proxy chain và trust policy; đừng tắt kiểm proxy vì backend chậm.

## 7. LDAP/AD: TCP connect, bind, search và pool là các giới hạn khác nhau

### 7.1. Bind và search xảy ra khi nào?

~~~text
Spring login / authorization
  -> acquire LDAP connection (có thể từ pool)
  -> DNS + TCP + TLS (LDAPS:636 hoặc StartTLS trên 389)
  -> bind (service account hoặc user bind)
  -> search user DN
  -> query group membership / roles
  -> close / return connection
  -> local SecurityContext/authorization
~~~

Một LDAP directory chậm có thể làm **mỗi login tạo nhiều operations**. Nếu bind 2 giây, user search 2 giây, group search 2 giây và LDAP referral tới server khác 2 giây, tổng sẽ vượt ngân sách mặc dù từng lời gọi có read timeout 2 giây. Phải tính số operations/parallelism.

**Phân biệt authentication và authorization:** Nếu LDAP bind thành công nhưng group lookup timeout, không được tự gán ROLE_ADMIN hay trả “có quyền” từ dữ liệu chưa đọc được. Có thể dùng group cache đã được xác thực và còn hiệu lực nếu policy cho phép; thiếu dữ liệu quyền thì deny/temporarily unavailable theo thiết kế.

### 7.2. JNDI LDAP timeouts chính xác

Hai environment properties của Oracle/OpenJDK LDAP provider:

~~~text
com.sun.jndi.ldap.connect.timeout = "1500"
com.sun.jndi.ldap.read.timeout    = "2500"
~~~

Đơn vị là **milliseconds trong một string**, giá trị dương. `connect.timeout` giới hạn TCP connect; nếu native LDAP pooling được yêu cầu, nó còn có thể giới hạn thời gian **đợi connection từ pool** khi cạn theo hành vi provider. `read.timeout` giới hạn thời gian đợi LDAP response, nếu không đặt có thể block không giới hạn theo mặc định provider. Không dùng `0` để giả định timeout ngay lập tức.

**Đừng nhầm** `com.sun.jndi.ldap.connect.pool.timeout`: đây là **thời gian idle connection nằm trong JNDI native pool trước khi được giải phóng**, không phải LDAP operation read timeout. Các system properties của pool (maxsize, prefsize, timeout) có scope JVM, có thể gây tác dụng ngoài dự kiến cho nhiều context sources.

### 7.3. Java 17: JNDI bind/search với timeout

Mã **LdapDirectoryProbe.java** chỉ chạy end-to-end khi có **LDAPS test server và bind user đã được cấp quyền**. Không có stdout cố định, vì dữ liệu và server khác nhau. Đừng thay LDAPS bằng LDAP plaintext để “sửa” lỗi CA; import test CA vào trust store phù hợp.

~~~java
import java.util.Hashtable;
import java.util.Objects;
import javax.naming.Context;
import javax.naming.NamingEnumeration;
import javax.naming.NamingException;
import javax.naming.directory.DirContext;
import javax.naming.directory.InitialDirContext;
import javax.naming.directory.SearchControls;
import javax.naming.directory.SearchResult;

public class LdapDirectoryProbe {
    public static void main(String[] args)
            throws NamingException {
        String dn = Objects.requireNonNull(
            System.getenv("LDAP_BIND_DN"),
            "LDAP_BIND_DN is required");
        String password = Objects.requireNonNull(
            System.getenv("LDAP_BIND_PASSWORD"),
            "LDAP_BIND_PASSWORD is required");

        Hashtable<String, Object> env = new Hashtable<>();
        env.put(Context.INITIAL_CONTEXT_FACTORY,
            "com.sun.jndi.ldap.LdapCtxFactory");
        env.put(Context.PROVIDER_URL,
            "ldaps://directory.lab.example.org:636");
        env.put(Context.SECURITY_AUTHENTICATION, "simple");
        env.put(Context.SECURITY_PRINCIPAL, dn);
        env.put(Context.SECURITY_CREDENTIALS, password);
        env.put(Context.REFERRAL, "throw");
        env.put("com.sun.jndi.ldap.connect.timeout", "1500");
        env.put("com.sun.jndi.ldap.read.timeout", "2500");

        DirContext ctx = new InitialDirContext(env);
        try {
            SearchControls limits = new SearchControls();
            limits.setSearchScope(SearchControls.SUBTREE_SCOPE);
            limits.setTimeLimit(1500);  // search time limit ms
            limits.setCountLimit(20);   // kết quả tối đa
            limits.setReturningAttributes(
                new String[] {"uid", "cn"});

            NamingEnumeration<SearchResult> results =
                ctx.search(
                    "ou=people,dc=lab,dc=example,dc=org",
                    "(uid=alice)", limits);
            try {
                int count = 0;
                while (results.hasMore()) {
                    results.next();
                    count++;
                }
                System.out.println("entries: " + count);
            } finally {
                results.close();
            }
        } finally {
            ctx.close();
        }
    }
}
~~~

Biên dịch:

~~~bash
javac LdapDirectoryProbe.java
java LdapDirectoryProbe
~~~

Vì URL và bind credentials là lab-specific, chương trình sẽ **fail** nếu chưa có server/trust/bind credentials; không kết luận API sai. Search filter `(uid=alice)` là **giá trị cố định**; khi lấy user input phải escape LDAP filter đúng chuẩn hoặc dùng API parameterized, không nối chuỗi thô dẫn tới LDAP injection.

`SearchControls.setTimeLimit` và `setCountLimit` giúp hạn search, nhưng **không thay** JNDI connect/read timeout hoặc gateway deadline. Search time limit handling có thể khác theo server/provider; với paging/referrals, budget phải bao cả các calls phát sinh.

### 7.4. Spring LDAP LdapContextSource

Spring Boot app dùng `spring-boot-starter-data-ldap` (hoặc Spring LDAP core phù hợp) có thể cấu hình trực tiếp bean:

~~~java
package com.example.directory;

import java.util.Map;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.ldap.core.support.LdapContextSource;

@Configuration
public class DirectoryConfig {
    @Bean
    LdapContextSource directorySource(
            @Value("${app.ldap.url}") String url,
            @Value("${app.ldap.base}") String base,
            @Value("${app.ldap.bind-dn}") String dn,
            @Value("${app.ldap.bind-password}") String password) {

        LdapContextSource source = new LdapContextSource();
        source.setUrl(url);
        source.setBase(base);
        source.setUserDn(dn);
        source.setPassword(password);
        source.setReferral("throw");
        source.setPooled(false);
        source.setBaseEnvironmentProperties(Map.of(
            "com.sun.jndi.ldap.connect.timeout", "1500",
            "com.sun.jndi.ldap.read.timeout", "2500"));
        return source;
    }
}
~~~

Cấu hình `application.yml` dùng values do **ứng dụng tự định nghĩa**, không tự biến thành Spring Security LDAP auto properties:

~~~yaml
app:
  ldap:
    url: "ldaps://directory.lab.example.org:636"
    base: "dc=lab,dc=example,dc=org"
    bind-dn: "${LDAP_BIND_DN}"
    bind-password: "${LDAP_BIND_PASSWORD}"
~~~

Lưu password trong secret manager/env được quản trị; hạn chế hiển thị qua process environment, logs và diagnostic endpoints. LDAPS certificate cần trusted CA và hostname validation. Cấu hình timeout ở `LdapContextSource` chỉ tác động những consumers **thực sự dùng bean đó**. Nếu tổ chức dùng `ActiveDirectoryLdapAuthenticationProvider` tự xây context khác, `spring.ldap.*`, hoặc một LDAP SDK riêng, cần kiểm connection factory/LDAP provider tương ứng; đừng giả định bean này áp dụng toàn JVM.

**Referrals:** `setReferral("throw")` dùng để lộ referral cho ứng dụng xử lý theo policy; đừng blindly `follow` qua domains/servers chưa tin. Referral following có thể tạo kết nối ngoài và ngốn thêm budget; cần egress allowlist, trust domain policy và timeout trên mỗi hop.

### 7.5. Native LDAP pooling và Spring LDAP pool

Spring LDAP mặc định không bật JNDI native pooling cho `AbstractContextSource` theo tài liệu hiện hành. Việc **tắt native pooling** trong ví dụ giúp tránh cache các authenticated user connections sai lifecycle, đặc biệt với user bind/password rotation. Nếu cần throughput cao, cân nhắc **Spring LDAP pooling** có:
- maxTotal, maxIdle/minIdle và per-directory server limits;
- pool acquire wait có giới hạn, eviction idle timeout, validation on borrow/idle;
- separate pools cho service-account search và user-bind flows;
- account/password change/secret rotation semantics rõ ràng;
- metrics active/idle/pending/rejections;
- đóng/return DirContext/NamingEnumeration đúng cách.

Không tự coi `com.sun.jndi.ldap.connect.pool.timeout` là pool wait; Oracle mô tả đó là thời gian **loại connection idle**, khác connect.timeout. JNDI native pool dùng JVM-wide System properties và có ràng buộc theo auth principal/creds; quản trị phải kiểm leak/cross-account reuse và password change. Spring LDAP khuyến nghị pooling implementation của Spring khi cần pooling phức tạp thay vì bật native flag bừa bãi.

## 8. Retry, circuit breaker, bulkhead và cache

### 8.1. Retry đúng loại request

| Lời gọi | Có thể retry? | Điều kiện |
| --- | --- | --- |
| **GET SAML metadata** | Có thể, ngoài login critical path. | Idempotent, 1 retry có jitter, trusted origin, bounded deadline, không nạp body partial. |
| **GET OIDC discovery/JWKS** | Có thể theo cache/SDK policy. | Không dynamic trust key từ token; tránh stampede khi new kid xuất hiện. |
| **CAS service ticket validation** | **Không tự retry cùng ticket**. | CAS ticket thường one-time; timeout có thể xảy ra sau khi server đã consume. |
| **LDAP search read-only** | Có thể trong một số case, nếu budget cho phép. | Giới hạn số attempts, idempotent, referral scope, connection release. |
| **LDAP user bind** | Thận trọng, không retry vô hạn. | Có thể tăng authentication failure/lockout; phân biệt transport timeout và wrong password. |
| **LDAP write/provisioning** | Không tự retry nếu không có idempotency contract. | Outcome có thể không rõ sau timeout. |

**Không dùng một retry policy chung cho mọi outbound federation call.** Nếu 5 requests cùng retry 3 lần, load lên upstream có thể tăng mạnh; ưu tiên một số lần hữu hạn, exponential backoff có jitter nhưng deadline còn đủ. Với authentication single-use ticket, thay vì retry ticket hãy yêu cầu **fresh login** khi CAS back-channel đã timeout.

### 8.2. Circuit breaker không được thay xác thực

Circuit breaker open do LDAP/CAS down có thể trả lỗi dịch vụ nhanh, bảo vệ web threads. Nhưng **không trả verified principal hay admin roles** khi validation chưa được thực hiện. Hãy phân biệt:
- **Authentication unavailable**: trả giao diện/HTTP error có thông tin retry an toàn.
- **Invalid credentials**: chỉ khi IdP/CAS/LDAP đã trả xác nhận invalid.
- **Authenticated but unauthorized**: deny/403 theo local policy.
- **Metadata refresh unavailable**: có thể tiếp tục dùng trusted valid snapshot theo chính sách; nếu trust hết hạn hoặc unknown signing key, fail closed.

### 8.3. Cache an toàn

- SAML IdP metadata: cache chỉ **trusted/verified snapshot**, có version, validUntil, maximum age và atomic promotion. Không dùng stale ký vô hạn.
- OIDC/JWKS: cache public keys từ trusted issuer, TTL và refresh rate limits; unknown kid là reason code cần quan sát.
- CAS service ticket: **không cache unvalidated tickets như valid user**, không làm nó multi-use. Một số Spring CAS flows dùng verified assertion caches riêng, phải phân biệt với raw ticket replay.
- LDAP group membership: cache identity/permissions có TTL nhỏ và revocation semantics được phê duyệt; khi không thể kiểm một user mới/role nhạy cảm, fail closed. Không dùng stale admin group vô thời hạn.
- HTTP connections: có thể reuse pooled sockets nhưng max idle/age/connection TTL cần giới hạn để tránh stale TLS sessions và pool exhaustion; HTTPS hostname verification vẫn bắt buộc.

## 9. Sự cố thường gặp: nhận diện bằng tín hiệu

| Triệu chứng | Nghi ngờ ưu tiên | Kiểm và sửa |
| --- | --- | --- |
| Spring startup treo khi IdP chậm | Remote metadata fetch chưa bounded. | Chủ động fetch có timeout, trusted snapshot, app bootstrap policy. |
| Login SAML lúc pass lúc fail | Metadata cache/node parity hoặc IdP response signature. | Phân loại transport vs signature; kiểm keyset refresh, không disable signature. |
| JWKS unknown kid ngay sau rotation | Keyset cũ, issuer/JWKS endpoint chậm. | Trusted cache refresh, key overlap, rate limiting. |
| CAS 401/redirect loop | `/serviceValidate` chậm hoặc service URL mismatch. | CAS ticket validation logs sanitized, connect/read timeout, canonical public service URL. |
| CAS timeout rồi retry cùng ST bị invalid | One-time ticket đã được CAS consume. | Yêu cầu login flow lấy ticket mới, không loop retry. |
| LDAP bind treo vài phút | `connect.timeout` không đặt/port/DNS, TLS handshake. | Explicit JNDI connect/read, network/firewall/LDAPS trust. |
| LDAP search treo nhưng bind nhanh | Read timeout, slow group query/index, referrals. | Bounded read/search limit, query optimization, referral policy. |
| Pool idle nhiều nhưng app nghẽn | Pool max/pending, connection leaks, bind blocking. | Active/idle/pending, return contexts, thread dumps. |
| Directory unavailable mà user nhận role admin | Fail-open fallback hoặc stale-privileged cache. | Chặn authorize, security incident review. |
| HTTPS CA invalid | TLS trust/hostname issue, không phải credential sai. | Sửa certificate chain/trust store, không trust-all. |
| Timeout tăng sau deploy proxy | New DNS/egress, TLS or host routing, connection reuse. | Đo per-hop latency, connect/TLS/read failures. |
| Chỉ một pod timeout LDAP | Node DNS/network/proxy config hoặc pool state khác. | Compare version/region, connections, ACLs. |

**Chẩn đoán theo cause:** `SocketTimeoutException`, `HttpTimeoutException`, JNDI `CommunicationException` hoặc `ServiceUnavailableException` không nên tự map thành `BadCredentialsException` khi chỉ do network. Không tiết lộ thông tin tài khoản/secret trong phản hồi user.

## 10. Java 17 chạy độc lập: mô phỏng HTTP response timeout trên loopback

Để nhìn thấy hành vi timeout thật mà **không gọi IdP/CAS/LDAP nào**, chương trình dựng HTTP server chỉ trên loopback. `/fast` trả ngay; `/slow` đợi 1,5 giây **trước khi gửi response headers**. Client đặt connect timeout 500 ms và **request timeout 100 ms** cho `/slow`. Mẫu này chứng minh **timeout trước khi có response**, không chứng minh giới hạn cho body streaming chậm.

**HttpTimeoutLab.java**:

~~~java
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class HttpTimeoutLab {
    private static void reply(HttpExchange exchange, String body)
            throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "text/plain; charset=utf-8");
        exchange.sendResponseHeaders(200, bytes.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(bytes);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService workers = Executors.newFixedThreadPool(2);
        HttpServer server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);
        server.setExecutor(workers);

        server.createContext("/fast", exchange ->
            reply(exchange, "OK"));

        server.createContext("/slow", exchange -> {
            try {
                Thread.sleep(1_500);
                reply(exchange, "LATE");
            } catch (InterruptedException interrupted) {
                Thread.currentThread().interrupt();
                exchange.close();
            } catch (IOException connectionClosed) {
                exchange.close();
            }
        });
        server.start();

        try {
            String base = "http://127.0.0.1:"
                + server.getAddress().getPort();
            HttpClient client = HttpClient.newBuilder()
                .connectTimeout(Duration.ofMillis(500))
                .followRedirects(HttpClient.Redirect.NEVER)
                .proxy(HttpClient.Builder.NO_PROXY)
                .build();

            HttpRequest fast = HttpRequest.newBuilder()
                .uri(URI.create(base + "/fast"))
                .timeout(Duration.ofSeconds(3))
                .GET().build();
            HttpResponse<String> ok = client.send(
                fast, HttpResponse.BodyHandlers.ofString());
            System.out.println("fast: " + ok.statusCode()
                + " " + ok.body());

            HttpRequest slow = HttpRequest.newBuilder()
                .uri(URI.create(base + "/slow"))
                .timeout(Duration.ofMillis(100))
                .GET().build();

            try {
                client.send(slow, HttpResponse.BodyHandlers.ofString());
                System.out.println("slow: UNEXPECTED_SUCCESS");
            } catch (HttpTimeoutException timeout) {
                System.out.println("slow: TIMEOUT");
            }
        } finally {
            server.stop(0);
            workers.shutdownNow();
        }
    }
}
~~~

Biên dịch/chạy với Java 17 (module `jdk.httpserver`):

~~~bash
javac --add-modules jdk.httpserver HttpTimeoutLab.java
java --add-modules jdk.httpserver HttpTimeoutLab
~~~

**stdout kỳ vọng trong môi trường loopback hoạt động bình thường**:

~~~text
fast: 200 OK
slow: TIMEOUT
~~~

Kết quả `/slow` được cố ý tạo từ server trì hoãn response headers lâu hơn request timeout; không phụ thuộc kết nối Internet hoặc KDC. Test có thể khác ở môi trường scheduler/CPU bất thường; nếu xảy ra lỗi loopback bind hoặc executor, đó là lỗi lab runtime cần báo rõ. Không dùng mã HTTP plain loopback này để tải metadata production; production phải dùng HTTPS trusted origin như phần 4.

**Bài học từ demo:**
- `connectTimeout` 500 ms áp dụng khi cần tạo TCP connection, không phải giới hạn tổng 500 ms trên `/slow`.
- `/slow` được reject vì response chưa tới hạn 100 ms; đó là **request-level timeout**.
- Nếu body bắt đầu gửi rất chậm sau response headers, Java 17 request timeout có semantics khác; phải thiết kế thêm bounded body/deadline.
- `HttpServer` ở đây không xác thực người dùng, không liên quan CAS/LDAP; chỉ chứng minh network wait behavior.

## 11. Quan sát, metrics, logs và alert

### 11.1. Lưu log có cấu trúc, không lộ credential

~~~text
event=federation.outbound_request_failed
trace_id=trace-demo-4b12
protocol=CAS
dependency_alias=cas-prod
phase=READ
reason=TIMEOUT
timeout_budget_ms=2000
elapsed_ms=2010
retry_attempt=0
result=AUTH_NOT_ESTABLISHED
~~~

Các giá trị là ví dụ, **không phải log được framework tự tạo**. Không ghi:
- Raw CAS `ticket` query param, CAS response chứa principal/attributes.
- SAMLResponse/XML Assertion, OIDC ID Token, JWT access token hoặc Authorization headers.
- LDAP bind password, DN chứa PII, filter có user input nhạy cảm, directory returned attributes.
- Private keys, cookies, client certificates hoặc authentication secrets.

**Nên ghi** dependency alias do server định nghĩa, protocol, phase (DNS/CONNECT/TLS/POOL_WAIT/READ/PARSE), sanitized reason code, request trace ID, elapsed ms, configured budget, node/deployment, result. Không dùng user ID/token/full endpoint URL làm metric labels cardinality cao.

### 11.2. Các metrics cần quan sát

| Metric minh họa | Ý nghĩa |
| --- | --- |
| `federation_outbound_latency_seconds` | Histogram thời gian gọi từng dependency và operation. |
| `federation_outbound_timeouts_total` | Lỗi theo dependency alias/phase; tránh label user/token. |
| `federation_pool_active_connections` | Tổng connection đang dùng. |
| `federation_pool_pending_acquires` | Requests đợi pool; cạn pool hay leak? |
| `federation_pool_acquire_time_seconds` | Thời gian chờ lấy connection. |
| `federation_metadata_age_seconds` | Tuổi last-known-good metadata snapshot. |
| `federation_metadata_refresh_failures_total` | Refresh lỗi, dù login hiện còn dùng cached keys. |
| `ldap_search_duration_seconds` | Search latency, slow queries, referral loops. |
| `cas_ticket_validation_failures_total` | Phân biệt INVALID_TICKET và NETWORK_TIMEOUT. |
| `federation_login_outcome_total` | SUCCESS, BAD_CREDENTIALS, DEPENDENCY_UNAVAILABLE, POLICY_DENIED. |

### 11.3. Cảnh báo nên có

- Timeout ratio tăng nhanh ở CAS/LDAP; login p95/p99 vượt SLO.
- Pool pending > 0 kéo dài trong khi active đạt maxTotal.
- Tỷ lệ login lỗi tập trung tại một node/region, cho thấy DNS/network/pool config không đồng nhất.
- Metadata/JWKS refresh liên tục fail hoặc snapshot tuổi vượt ngưỡng.
- TLS/LDAPS handshake errors tăng đột biến sau cert rotation.
- LDAP referrals hoặc group search nhiều hops, timeouts tăng.
- Retry amplification/circuit breaker mở bất thường.
- Bất kỳ security fallback cấp Authentication khi upstream timeout đều là incident nghiêm trọng.

## 12. Test matrix: tích cực, lỗi và tải cao

| # | Test | Kỳ vọng |
| --- | --- | --- |
| 1 | Metadata HTTPS 200 nhanh, đúng trusted IdP | Tải, parse, trust-check, nạp registration. |
| 2 | Metadata TCP connect không hoàn thành | Bị giới hạn connect timeout, không treo vô hạn. |
| 3 | Metadata server nhận connection rồi chậm gửi response | Bị giới hạn read/request timeout phù hợp. |
| 4 | Metadata body cực lớn | Bị từ chối bởi MAX_BYTES, không OOM. |
| 5 | Metadata HTTP redirect sang untrusted host | Không follow tự động; reject. |
| 6 | Metadata TLS certificate không trusted | Fail TLS, không trust-all. |
| 7 | Metadata XML malformed | Reject; không import signing keys. |
| 8 | Metadata signature/trust sai | Reject, dù HTTPS fetch thành công. |
| 9 | IdP metadata stale nhưng trusted valid snapshot còn được policy cho phép | Giữ snapshot theo hạn và alert. |
| 10 | Trusted snapshot hết validUntil/policy age | Không tiếp tục tin key vô hạn. |
| 11 | JWKS fetch timeout nhưng key cached trusted hợp lệ | Dùng key cached theo chính sách, alert refresh failure. |
| 12 | JWT unknown kid khi JWKS chưa refresh | Fail closed; không tự tin token header. |
| 13 | CAS validation thành công đúng ticket/service URL | Verified authentication. |
| 14 | CAS HTTPS connect timeout | DEPENDENCY_UNAVAILABLE, không tạo Authentication. |
| 15 | CAS đã consume ticket rồi response timeout | Không lặp ticket; yêu cầu fresh login. |
| 16 | CAS HTTP 5xx | Không coi là invalid credentials/valid ticket; fail closed. |
| 17 | CAS service URL mismatch | Ticket validation fail, không sửa bằng cách bỏ URL binding. |
| 18 | CAS proxy ticket không có trusted proxy chain | Reject, không accept-any-proxy. |
| 19 | CAS TLS certificate invalid | Reject HTTPS, không disable hostname verification. |
| 20 | LDAP LDAPS bind nhanh với account đúng | Bind pass và user search tiếp tục. |
| 21 | LDAP connect quá lâu | JNDI connect.timeout hoạt động. |
| 22 | LDAP bind response chậm | JNDI read.timeout hoạt động. |
| 23 | LDAP search filter không index, chậm | Search/read timeout, query/index remediation. |
| 24 | LDAP group lookup gồm nhiều searches | Tổng login deadline không bị vượt vô hạn. |
| 25 | LDAP referral tới server ngoài allowlist | Bị chặn/throw theo policy. |
| 26 | LDAP trả quá nhiều entries | Count limit/pagination cap hoạt động. |
| 27 | LDAP simple bind qua plaintext URL | Security QA fail; yêu cầu TLS/StartTLS. |
| 28 | LDAP credentials sai thật | Bad credentials theo provider, không nhầm network timeout. |
| 29 | LDAP unavailable nhưng app tự cấp ROLE_USER/ADMIN | Security QA fail, bỏ fail-open fallback. |
| 30 | Directory role lookup timeout | Không tự cấp nhóm/quyền đặc biệt. |
| 31 | Native pool full, connection wait vô hạn | Test fail; giới hạn pool wait và maxTotal. |
| 32 | Connections không được close sau error | Leak detector/metrics phát hiện; fix lifecycle. |
| 33 | SSL handshake treo/fail | Bounded/correct TLS failure, không disable certificate trust. |
| 34 | DNS resolver cực chậm | Phân tích ngoài connect timeout, có budget/supervisor. |
| 35 | Mỗi request login fetch metadata mới | Throughput test fail; dùng cache/refresh off path. |
| 36 | 100 logins đồng thời, LDAP chậm | Bulkhead/pool limits giữ web server responsive. |
| 37 | Retry metadata bùng nổ khi IdP down | Rate-limit/jitter/circuit breaker ngăn amplification. |
| 38 | Retry một CAS ST cùng ticket khi timeout | Test fail; không retry single-use credential. |
| 39 | Metadata refresh node A pass, node B fail | Keyset parity/refresh observability phát hiện. |
| 40 | Read timeout bằng 0 theo Java/JNDI | Security/config QA fail nếu cho indefinite wait. |
| 41 | HTTP client timeout chỉ đến headers, body stream liên tục | Body cap + deadline test, không chỉ dựa request timeout JDK 17. |
| 42 | Login session/ticket đã hết hạn | Không tăng token TTL để chữa LDAP/network timeout. |
| 43 | LDAP cached admin roles đã hết TTL nhưng LDAP down | Không tiếp tục cấp admin quyền từ stale cache. |
| 44 | API request được authenticated cũ nhưng directory lỗi | Áp dụng policy session/authorization rõ ràng; không cấp thêm quyền. |
| 45 | Logs chứa CAS ticket/LDAP password/JWT | Security QA fail, redact và xử lý incident. |
| 46 | Graceful shutdown khi outbound requests pending | Cancellation/resource cleanup, không leak connections. |
| 47 | Pool wait 0ms cấu hình nhầm nghĩa là unlimited | Kiểm đúng semantics library, test saturation. |
| 48 | IdP metadata ETag/304 khi refresh | Giữ đã-verified snapshot đúng cache policy, không parse empty body. |

## 13. Các anti-pattern cần tránh

**Chỉ đặt server.servlet.session.timeout:** đây là hạn phiên HTTP, không giới hạn outgoing CAS/LDAP connection.

**Chỉ đặt `HttpClient.connectTimeout`:** connection đã mở có thể reuse; response read vẫn có thể treo.

**Dùng `readTimeout=0` để “đợi đến khi IdP trả”:** có thể block vô hạn, dẫn tới pool exhaustion.

**Cho CAS/LDAP auth timeout rồi login bằng anonymous:** biến outage thành bypass xác thực. Phải fail closed.

**Retry CAS service ticket 3 lần ngay:** ticket có thể đã được server consume trong request đầu; retry có thể vô nghĩa và làm nặng hệ thống.

**Mỗi login fetch IdP metadata/JWKS mới:** tăng latency, tạo network dependency trên critical path và nguy cơ keyset inconsistency.

**Tin metadata HTTP 200:** tải được bytes không phải chứng minh XML metadata/signing keys đáng tin.

**Follow redirect sang mọi URL do metadata/tenant/user nhập:** tăng SSRF và trust confusion. Dùng server-side allowlist/egress policy và hạn hop.

**Mở LDAP native pool không đo wait/leaks:** pool có thể làm chậm hơn và ẩn credentials lifecycle; cần caps, validation và metrics.

**Dùng pooled LDAP connection của user khác:** nguy cơ identity confusion, đặc biệt sau password change; phải đúng authentication strategy.

**Tăng pool size/timeout vô hạn để xử lý incident:** chỉ đẩy nghẽn sang CAS/LDAP, không chữa latency upstream.

**Nối user input thẳng vào LDAP search filter:** LDAP injection; dùng escaping/parameterized queries.

**Bật trust-all SSL cho CAS/LDAPS:** chuyển timeout/CA incident thành MITM risk.

**Giữ privileged group cache vô hạn khi directory down:** rủi ro revocation delay và privilege escalation.

## 14. Checklist triển khai và vận hành

### Lựa chọn timeouts

- [ ] Có login total deadline, chia budget theo upstream và số operations.
- [ ] HTTP connect/read/request timeouts đều dương, có test semantics trên JDK/library thực.
- [ ] Có pool acquire wait/maxTotal/idle timeout phù hợp throughput.
- [ ] DNS/TLS/redirect/body size không bị bỏ ngoài quá trình kiểm.
- [ ] Có deadline/cancellation và cleanup resources khi user disconnect hoặc upstream fail.

### SAML/OIDC metadata

- [ ] Metadata/JWKS chỉ đến từ trusted issuer/allowlisted endpoint.
- [ ] HTTPS CA/hostname validation còn bật.
- [ ] Metadata fetch bounded, body max và redirect policy rõ.
- [ ] Verify metadata XML signature/trust, IdP EntityID và validUntil theo policy.
- [ ] Cache verified snapshot, background refresh/atomic rollout.
- [ ] Unknown verification key thì fail closed, không nhận arbitrary KeyInfo/JWK URL.

### CAS

- [ ] Trusted CAS server URL, canonical public service URL đúng.
- [ ] CAS ticket validator HTTP transport có connect/read/pool timeouts.
- [ ] Không retry cùng single-use ST sau timeout; yêu cầu fresh login flow.
- [ ] CAS TLS trust và proxy trust policy được giữ nguyên.
- [ ] Không log ticket query param hoặc cấp Authentication khi timeout.

### LDAP

- [ ] JNDI `com.sun.jndi.ldap.connect.timeout` và `read.timeout` có giá trị dương.
- [ ] LDAPS/StartTLS certificate trust/hostname được kiểm.
- [ ] Bind/search và group lookup đều nằm trong login budget.
- [ ] Search result count/time limits, escaped filters, referral policy.
- [ ] Pooled connections có max/wait/lifecycle rõ; đóng contexts/results.
- [ ] Không cấp role mới khi directory unavailable.

### Observability và QA

- [ ] Metrics latency p95/p99, timeout phase, pool active/idle/pending.
- [ ] Alerts metadata refresh age, CAS validation outages, LDAP read spikes.
- [ ] Có tests connect stall, headers stall, streaming body, pool saturation, TLS failure, referral loops và retries.
- [ ] Không log raw assertions, tickets, passwords hoặc secrets.
- [ ] Negative tests xác nhận network timeout **không tạo Authentication**.

## 15. Câu hỏi ôn tập

**1. Vì sao cần cả connect và read timeout?**  
Vì kết nối được tạo nhanh nhưng server có thể không trả response, và ngược lại. Connect timeout không giới hạn các thao tác đọc về sau.

**2. Request timeout trong JDK 17 có bao chắc chắn toàn bộ HTTP body streaming không?**  
Không. Phải kiểm implementation/version, dùng bounded body và deadline/cancellation cho toàn bộ operation.

**3. Có nên gọi metadata IdP bằng network trên mọi login không?**  
Không nên. Dùng verified cached metadata và refresh có kiểm soát, tránh upstream availability trên request path.

**4. Spring RelyingPartyRegistrations có hỗ trợ InputStream không?**  
Có, từ trusted metadata bytes đã được tải bởi một client khác; caller phải đóng stream. Nó không tự làm mọi trust checks cho nguồn bytes.

**5. CAS service ticket validation timeout có được retry cùng ticket không?**  
Không tự động. CAS service ticket thường one-time, có thể đã bị consume. Yêu cầu fresh authentication flow nếu trạng thái không xác định.

**6. JNDI LDAP read.timeout không đặt thì sao?**  
Provider Oracle/OpenJDK có thể chờ response vô hạn theo mặc định, gây treo thread khi directory chậm.

**7. `com.sun.jndi.ldap.connect.pool.timeout` là pool wait timeout?**  
Không. Đây là idle pooled connection eviction; `connect.timeout` có tác động riêng, kể cả pool wait trong một số native pooling cases.

**8. LDAP bind thành công nhưng group lookup timeout có nên cấp ROLE_ADMIN mặc định không?**  
Không. Missing authorization evidence phải fail closed hoặc tuân theo cache TTL/revocation policy được phê duyệt.

**9. Vì sao không tăng maxTotal pool lên vô hạn khi directory bị nghẽn?**  
Vì nó tạo thêm connections/pressure lên upstream và làm cạn tài nguyên app.

**10. HTTP 200 metadata có chứng minh IdP signing certificate đáng tin không?**  
Không. Cần trust anchor/metadata signature hoặc channel/source integrity policy và kiểm issuer/keys.

**11. Khi pool đầy, request login nên làm gì?**  
Chờ bounded acquire timeout rồi trả lỗi tạm thời, không block vô hạn hoặc bypass xác thực.

**12. Lỗi CAS `ticket invalid` và CAS `network timeout` có giống nhau không?**  
Không. Một bên là xác minh ticket thất bại, bên kia không nhận được kết quả; cả hai đều không cấp Authentication, nhưng xử lý UX/incident khác nhau.

**13. Referral LDAP có thể ảnh hưởng time budget thế nào?**  
Referral có thể tạo thêm các kết nối/search tới host khác; cần allowlist, trusted domains, per-hop timeout và tổng deadline.

**14. Circuit breaker có nên fallback sang authenticated user khi CAS/LDAP down không?**  
Không. Circuit breaker chỉ giúp fail nhanh hoặc sử dụng trusted cache theo policy, không được biến lỗi upstream thành authentication bypass.

## 16. Tài liệu tham khảo chính thức

1. [Java 17 HttpClient.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.Builder.html): connectTimeout, connection reuse và TLS configuration.
2. [Java 17 HttpRequest.Builder](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpRequest.Builder.html): request timeout semantics.
3. [Java HTTP Client timeout change in JDK 26](https://inside.java/2026/03/04/jdk-26-http-client/): sự khác biệt về response body so với các JDK trước.
4. [Java URLConnection](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/net/URLConnection.html): connect/read timeouts.
5. [Spring Security RelyingPartyRegistrations API](https://docs.spring.io/spring-security/site/docs/6.0.x/api/org/springframework/security/saml2/provider/service/registration/RelyingPartyRegistrations.html): fromMetadata(InputStream)/fromMetadataLocation.
6. [Spring Security SAML2 Login Overview](https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html): registration, asserting-party metadata, refresh patterns.
7. [Spring Security CAS Authentication](https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html): CasAuthenticationProvider và CAS ticket validator back-channel.
8. [Apereo Java CAS Client](https://github.com/apereo/java-cas-client): library ticket validation và HTTP connection implementation; xác minh version.
9. [Jasig CAS Client AbstractUrlBasedTicketValidator API](https://javadoc.io/static/org.jasig.cas.client/cas-client-core/3.6.4/org/jasig/cas/client/validation/AbstractUrlBasedTicketValidator.html): ví dụ version có setURLConnectionFactory; package khác theo CAS client release.
10. [Oracle JNDI LDAP connect timeout](https://docs.oracle.com/javase/jndi/tutorial/ldap/connect/create.html): connect timeout.
11. [Oracle JNDI LDAP read timeout](https://docs.oracle.com/javase/tutorial/jndi/newstuff/readtimeout.html): read timeout.
12. [Oracle JNDI LDAP Service Provider](https://docs.oracle.com/javase/8/docs/technotes/guides/jndi/jndi-ldap.html): pool, timeout, system/env property semantics.
13. [Spring LDAP Configuration](https://docs.spring.io/spring-ldap/reference/configuration.html): ContextSource, pooling và custom environment properties.
14. [Spring LDAP AbstractContextSource API](https://docs.spring.io/spring-ldap/docs/current/api/org/springframework/ldap/core/support/AbstractContextSource.html): setBaseEnvironmentProperties/setPooled.
15. [Spring Security LDAP](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/ldap.html): bind/search và authorization.
16. [Apereo CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): service tickets, service URL và validation semantics.
17. [Spring Security Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): session timeout khác network timeouts.
18. [OWASP Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html): fail-safe authentication và vận hành.

**Kết luận:** Khi triển khai federation, phải kiểm soát **timeout của từng HTTP/LDAP transport, wait của pool, giới hạn body/search và deadline tổng**, tránh biến IdP/CAS/directory latency thành tình trạng nghẽn hệ thống. Với metadata, chỉ cache **trusted/verified snapshot**; với CAS, không lặp một ticket single-use; với LDAP, phải giới hạn bind/search và xử lý group lookup an toàn. **Timeout không bao giờ là lý do để bỏ xác minh chữ ký, ticket hay quyền truy cập.**