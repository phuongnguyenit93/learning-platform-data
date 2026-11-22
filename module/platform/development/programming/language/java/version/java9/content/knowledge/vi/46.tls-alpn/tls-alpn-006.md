# OCSP stapling và thông tin thu hồi chứng thư trong TLS/Java

## 1. Vấn đề: chứng thư hợp lệ theo thời hạn nhưng vẫn có thể bị thu hồi

Trong TLS, máy khách dùng chứng thư số X.509 để xác thực danh tính máy chủ (và có thể xác thực máy khách khi dùng mutual TLS). Xây dựng được đường dẫn tin cậy tới CA, kiểm tra chữ ký, hostname, mục đích sử dụng và khoảng `notBefore/notAfter` là các phần quan trọng, nhưng **chưa trả lời đầy đủ liệu CA đã thu hồi chứng thư trước ngày hết hạn hay chưa**.

Ví dụ: khóa riêng của một website bị lộ hôm nay; chứng thư của nó còn hạn trong vài tuần. CA có thể đánh dấu chứng thư là **revoked** để các bên kiểm tra trạng thái từ chối nó sớm. Cũng có trường hợp CA thu hồi chứng thư vì cấp sai, thay đổi thông tin hoặc lý do quản trị khác.

Ba khái niệm cần phân biệt ngay:

- **Certificate expiry:** chứng thư hết hạn theo `notAfter`, thường xác định trực tiếp từ chứng thư.
- **Certificate revocation:** CA hoặc nguồn được ủy quyền thông báo chứng thư không còn được chấp nhận trước khi hết hạn; cần dữ liệu trạng thái từ một nguồn được tin cậy.
- **OCSP stapling:** cơ chế **máy chủ đính kèm phản hồi OCSP đã được ký** trong TLS handshake, giúp máy khách nhận thông tin thu hồi mà thường không phải tự hỏi OCSP responder của CA.

OCSP là viết tắt của **Online Certificate Status Protocol**; “stapling” không phải một thuật toán mật mã mới và không thay thế kiểm tra chuỗi chứng thư. Phần lớn chi tiết cơ chế thuộc RFC 6960; TLS 1.3 hiện hành được mô tả bởi **RFC 9846 (tháng 7/2026)**.

Bài thuộc nhóm **TLS và ALPN**, nhưng OCSP stapling và ALPN giải quyết **hai câu hỏi độc lập**: OCSP hỗ trợ kiểm tra tình trạng chứng thư, còn ALPN thương lượng giao thức ứng dụng trên TLS như `h2` hoặc `http/1.1`. Bật ALPN không tự động bật revocation checking.

## 2. Ba nguồn thông tin trạng thái cần biết

| Cách kiểm tra | Ai lấy thông tin? | Dữ liệu nhận được | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- | --- |
| **CRL (Certificate Revocation List)** | Máy khách hoặc hệ thống PKI | Danh sách chứng thư đã thu hồi, ký bởi nguồn có thẩm quyền | Có thể cache/phân phối tập trung, phù hợp môi trường nội bộ | Danh sách có thể lớn, khoảng cập nhật quyết định độ trễ phát hiện |
| **Client-driven OCSP** | Máy khách trực tiếp hỏi OCSP responder | Phản hồi trạng thái cho chứng thư cụ thể | Nhỏ gọn, trực tiếp từ responder được ủy quyền | Thêm truy cập mạng/độ trễ, có thể lộ thông tin kiểm tra của máy khách cho responder |
| **OCSP stapling** | Máy chủ TLS lấy và cache phản hồi, rồi gửi kèm handshake | Phản hồi OCSP ký sẵn, thường dành cho chứng thư máy chủ | Giảm lượt hỏi của từng client, giảm tải responder, cải thiện riêng tư so với hỏi trực tiếp | Phụ thuộc máy chủ cung cấp đáp ứng còn hạn và máy khách thực sự kiểm tra nó |

CRL và OCSP là **nguồn dữ liệu** cho revocation checking; stapling là **cách vận chuyển phản hồi OCSP trong TLS**. Nó không làm thay đổi giá trị trạng thái do CA/responder cung cấp.

Một đường kiểm tra thực tế có thể kết hợp các nguồn. Khi không có stapled response, thư viện PKIX tùy cấu hình có thể thử OCSP trực tiếp, CRL hoặc kết thúc bắt tay với lỗi. Không được mặc định mọi TLS client đều luôn thực hiện bước này.

**Chứng thư ngắn hạn** cũng là một chiến lược giảm thời gian khóa bị lộ còn có thể được dùng. Nó không làm OCSP stapling “vô ích” trong mọi hệ thống và không thay thế các yêu cầu thu hồi riêng của môi trường tổ chức.

## 3. OCSP responder trả lại những gì?

Một OCSP request xác định chứng thư cần kiểm tra bằng thông tin về CA cấp và serial number, thay vì gửi mật khẩu hoặc khóa riêng. Địa chỉ responder thường được CA công bố trong phần **Authority Information Access (AIA)** của chứng thư, hoặc do chính sách PKI cấu hình.

Theo RFC 6960, mỗi `SingleResponse` gồm định danh chứng thư, trạng thái và các mốc thời gian có ý nghĩa:

| Trường/trạng thái | Ý nghĩa chính | Kết luận đúng |
| --- | --- | --- |
| `good` | Responder khẳng định không thấy chứng thư bị thu hồi ở thời điểm trạng thái được biết | **Không có thông báo thu hồi**; chưa đủ để tuyên bố chứng thư hợp lệ về mọi mặt |
| `revoked` | Đã bị thu hồi; có thể kèm `revocationTime` và `revocationReason` | Phải từ chối chứng thư khi chính sách yêu cầu xác thực hợp lệ |
| `unknown` | Responder không có thông tin đủ tin cậy về chứng thư đó | Không được xem là `good` |
| `thisUpdate` | Thời điểm mà trạng thái được biết là chính xác | Kiểm tra phản hồi không chứa thông tin quá cũ |
| `nextUpdate` (có thể vắng) | Mốc mà tại hoặc trước đó dự kiến sẽ có thông tin trạng thái mới | Xem phản hồi có còn nằm trong giới hạn freshness theo chính sách |
| `producedAt` | Thời điểm responder ký/sản sinh phản hồi | Cần xét cùng thời gian hiệu lực, chữ ký và chính sách |

**Hai lớp kết quả khác nhau:** phản hồi giao thức OCSP bên ngoài có thể báo xử lý thành công hoặc lỗi (ví dụ responder unavailable), trong khi một phản hồi thành công mới có `SingleResponse.certStatus = good/revoked/unknown`. Vì vậy **“OCSP response status: successful” không đồng nghĩa “Cert Status: good”**.

Một phản hồi stapled ở dạng DER/ASN.1 phải được kiểm tra: chữ ký, chứng thư được hỏi, thẩm quyền ký của CA hoặc delegated responder, mốc thời gian/freshness và quy tắc của PKIX. Một chuỗi byte “trông giống OCSP” không đủ làm bằng chứng. Chứng thư của delegated OCSP responder phải có thẩm quyền và sử dụng khóa thích hợp theo cấu trúc PKI.

Lưu ý chính xác: RFC 6960 nêu rằng `good` ít nhất cho biết số serial được hỏi không nằm trong danh sách thu hồi trong thời điểm trạng thái; riêng giá trị này **không bảo đảm chứng thư từng được phát hành**. Máy khách vẫn cần kiểm tra chuỗi chứng thư tới trust anchor, chữ ký, thời hạn, tên máy chủ, key usage/extended key usage và các chính sách áp dụng.

## 4. OCSP stapling diễn ra trong TLS handshake như thế nào?

Một luồng lý tưởng:

```text
             Trước/giữa các lần kết nối
             ┌──────────────────────────────┐
             │ TLS server                   │
             │ lấy OCSP response từ CA      │
             │ kiểm tra/cất vào cache       │
             └──────────────┬───────────────┘
                            │   signed OCSP response (còn hạn)
                            ▼
TLS client                                     TLS server
    │                                             │
    ├── ClientHello + status_request ────────────>│
    │                                             │
    │<── ServerHello / handshake messages ───────┤
    │<── certificate + stapled OCSP response ────┤
    │                                             │
    │ kiểm tra chuỗi chứng thư, hostname,         │
    │ chữ ký OCSP, trạng thái, freshness          │
    │ theo chính sách PKIX                        │
    │                                             │
    ├── handshake hoàn tất nếu hợp lệ ───────────>│
    │<────────── dữ liệu ứng dụng ───────────────>│
```

Ở bước đầu, server có thể lấy và cache phản hồi từ OCSP responder do CA chỉ định. Khi client gửi TLS extension `status_request`, server có thể trả phản hồi đã cache. Client không cần truy vấn responder riêng **nếu đã có phản hồi phù hợp và chính sách chấp nhận được**.

**Định dạng theo phiên bản TLS đang dùng:**

- Với **TLS 1.3**, phản hồi OCSP stapled được truyền dưới dạng extension `status_request` của `CertificateEntry` tương ứng trong thông điệp `Certificate`. Đây là quy tắc hiện hành tại **RFC 9846 §4.5.1.1**.
- Trong trường hợp vận hành hệ thống còn dùng **TLS 1.2**, phản hồi OCSP được vận chuyển bằng thông điệp riêng `CertificateStatus`. Chi tiết này chỉ để nhận biết packet capture/lưu lượng tương thích, không phải lời khuyên chọn phiên bản cũ hơn.
- `status_request_v2`/“multiple certificate status request” đã bị **deprecated cho TLS 1.3**. Không xây dựng kiến trúc TLS 1.3 mới dựa vào `status_request_v2` hoặc RFC 6961. RFC 9846 thay thế RFC 8446 và obsoletes RFC 6961.

OCSP stapling **không mã hóa riêng nội dung phản hồi**; tính xác thực của thông tin dựa vào chữ ký OCSP và xác thực TLS/PKIX. Việc server giữ bản sao OCSP ký sẵn không trao cho server khả năng tự tạo “good” hợp lệ nếu CA/responder không ký.

## 5. Khi thiếu, hết hạn hoặc báo revoked: phải hiểu chính sách

Đừng chỉ hỏi “server có gửi staple không?”; cần hỏi **máy khách có kiểm tra, kiểm tra tới đâu và sẽ xử lý lỗi thế nào?**

| Tình huống | Điều nhận được | Hướng xử lý an toàn |
| --- | --- | --- |
| Có phản hồi `good`, chữ ký đúng, khớp cert, thời gian phù hợp | Bằng chứng chưa bị thu hồi theo nguồn được ủy quyền trong thời hạn chấp nhận | Tiếp tục các kiểm tra PKIX/hostname khác |
| Có phản hồi `revoked` hợp lệ | Chứng thư đã bị thu hồi | Từ chối |
| Có phản hồi `unknown` | Không kết luận tốt/xấu | Xử lý theo chính sách xác thực; không mặc định là tốt |
| Phản hồi bị sửa/chữ ký sai/không đúng chứng thư | Không đáng tin | Không chấp nhận là bằng chứng OCSP hợp lệ |
| `nextUpdate` đã qua hoặc thời gian sai | Dữ liệu cũ/chưa đến kỳ hợp lệ | Không lấy response cũ làm bằng chứng mới; áp dụng fallback hoặc fail theo chính sách |
| Server không staple gì | Chưa có dữ liệu trạng thái từ đường stapling | Có thể hỏi OCSP/CRL nếu đã cấu hình; không suy ra cert “revoked” |
| OCSP responder hoặc mạng không truy cập được | Không thể lấy trạng thái mới | Phân biệt lỗi hạ tầng với trạng thái `revoked`; định nghĩa fail-open/fail-closed một cách có chủ đích |

**Soft-fail** là chấp nhận tiếp tục trong một số lỗi không xác định được trạng thái (như responder tạm thời không truy cập). **Hard-fail** là từ chối khi trạng thái yêu cầu không xác minh được. Hai lựa chọn có đánh đổi về tính sẵn sàng và rủi ro; trong môi trường đòi hỏi thu hồi bắt buộc, phải cấu hình PKIX và đường dự phòng phù hợp để tránh fail-open ngoài ý muốn.

Không được tự suy rằng một trình duyệt, proxy hoặc phiên bản JDK nào cũng hard-fail khi thiếu staple. Hành vi phụ thuộc implementation, trust manager, policy và cấu hình. Chứng thư có TLS Feature/“Must-Staple” theo RFC 7633 có thể đưa ra yêu cầu bảo đảm sự hiện diện của status request ở một số máy khách, **nhưng không được giả định mọi client đều thực thi yêu cầu đó**.

Về vận hành máy chủ: theo dõi thời điểm làm mới response, giới hạn cache theo `nextUpdate` và TTL, đồng bộ thời gian, theo dõi cảnh báo responder, và tránh phục vụ response quá hạn. Nếu TLS kết thúc tại ingress, load balancer hoặc reverse proxy, **đó chính là nơi cần cấu hình stapling**; không chỉ cấu hình trên ứng dụng ở phía sau.

## 6. Java JSSE hiện đại: ba công tắc cần phân biệt

Java hỗ trợ TLS thông qua **JSSE** (thư viện `javax.net.ssl`). JDK đã có hỗ trợ OCSP stapling và `ExtendedSSLSession.getStatusResponses()` từ Java 9. Với provider SunJSSE/OpenJDK thông dụng, các cài đặt chính hiện được nêu trong tài liệu JSSE của Oracle:

| Thuộc tính | Đặt ở đâu? | Vai trò | Mặc định theo tài liệu Oracle |
| --- | --- | --- | --- |
| `jdk.tls.client.enableStatusRequestExtension` | Java system property ở **client** | Cho phép gửi extension hỏi OCSP stapling | `true` |
| `com.sun.net.ssl.checkRevocation` | Java system property ở **client** | Bật kiểm tra thu hồi khi dùng cấu hình trust manager PKIX mặc định | Không bật mặc định trong trường hợp thông dụng |
| `ocsp.enable` | **Java security property**, không phải system property thông thường | Cho phép client-driven OCSP, gồm dự phòng khi không có response stapled phù hợp | Cần bật khi muốn dùng đường OCSP trực tiếp |
| `jdk.tls.server.enableStatusRequestExtension` | Java system property ở **server** | Cho phép JSSE server tạo và gửi response stapled | `false` |
| `jdk.tls.stapling.cacheLifetime` | Java system property ở server | Giới hạn vòng đời response trong cache | 3.600 giây |
| `jdk.tls.stapling.responseTimeout` | Java system property ở server | Thời gian chờ lấy OCSP response | 5.000 ms |
| `jdk.tls.stapling.responderURI` | Java system property ở server | URI responder dự phòng nếu cert không có AIA | Không có sẵn |

Chú ý: **gửi `status_request` không tự động bắt buộc từ chối chứng thư revoked**. Để JSSE sử dụng stapled OCSP response trong đường xác minh, phải bật revocation checking. Theo hướng dẫn Oracle, có thể bật qua `com.sun.net.ssl.checkRevocation=true` hoặc cấu hình `PKIXParameters.setRevocationEnabled(true)` trong trust manager được dùng thật sự. Khi fallback sang OCSP trực tiếp, `ocsp.enable` phải là **security property**.

### 6.1. Client: cấu hình bằng JVM options

Với ứng dụng dùng trust manager mặc định và SunJSSE, có thể khởi chạy (ví dụ; lớp chạy do ứng dụng cung cấp):

```bash
java -Djdk.tls.client.enableStatusRequestExtension=true \
     -Dcom.sun.net.ssl.checkRevocation=true \
     -jar app.jar
```

Dấu `\` để xuống dòng là cú pháp shell kiểu Unix; trên PowerShell/Windows, đặt các tùy chọn `-D...` trên **một dòng**, hoặc dùng cú pháp nối dòng tương ứng. Hai system properties nên được cấu hình **trước khi tạo SSLContext/TLS client**; thư viện HTTP dùng trust manager riêng có thể bỏ qua cài đặt mặc định. Để bật đường OCSP trực tiếp trong ứng dụng Java, đặt security property `ocsp.enable=true` qua file cấu hình security của JDK hoặc gọi `Security.setProperty("ocsp.enable", "true")` đủ sớm trong vòng đời tiến trình.

Không dùng tùy chọn `-Docsp.enable=true` rồi tưởng đó chắc chắn là cách bật security property. Thư viện/ứng dụng thực tế phải được thử với provider và cấu hình thật.

### 6.2. Server JSSE: cấu hình stapling

Khi chính **Java server/SunJSSE trực tiếp chấm dứt TLS**, cấu hình trước khi SSLContext khởi tạo:

```bash
java -Djdk.tls.server.enableStatusRequestExtension=true \
     -Djdk.tls.stapling.cacheLifetime=3600 \
     -jar server.jar
```

Server còn phải có chứng thư/khóa riêng hợp lệ, chuỗi chứng thư đầy đủ và OCSP responder có thể truy cập. Bật property chỉ mở tính năng, **không bảo đảm** server sẽ luôn có một response để đính kèm. Nếu HTTPS được xử lý bởi Nginx, Envoy, CDN hoặc ingress, hãy cấu hình **thành phần terminate TLS thực tế** theo tài liệu của nó; thuộc tính của JVM phía sau không thay đổi handshake bên ngoài.

Không tùy tiện kéo dài cache quá hạn `nextUpdate`; khi gặp chứng thư mới hoặc CA/responder thay đổi, cache cần phản ánh trạng thái mới đúng hạn.

## 7. Ví dụ Java 17+: kiểm tra cấu hình và quan sát stapled response

Ví dụ chạy độc lập dưới đây **không giả tạo phản hồi OCSP**. Khi chạy **không có đối số**, nó chỉ xác minh khả năng TLS 1.3 và các property đã thiết lập; không yêu cầu mạng, nên stdout cố định trên JDK hỗ trợ TLS 1.3. Khi truyền hostname, chương trình sẽ thực hiện TLS handshake thật, bật **hostname verification**, sử dụng trust manager mặc định với revocation checking, rồi truy xuất số phản hồi DER từ `ExtendedSSLSession.getStatusResponses()` nếu provider hỗ trợ.

**Điều quan trọng:** số phản hồi OCSP **không phải kết quả `good/revoked`**; không in ra byte DER rồi tự kết luận hợp lệ. Khi server không staple hoặc provider không cung cấp response, số lượng có thể bằng 0; khi xác thực/revocation thất bại, TLS handshake có thể ném exception trước khi in ra kết quả.

Lưu thành `OcspStaplingDemo.java`:

```java
import java.security.Security;
import java.util.Arrays;
import javax.net.ssl.ExtendedSSLSession;
import javax.net.ssl.SSLContext;
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSession;
import javax.net.ssl.SSLSocket;

public class OcspStaplingDemo {
    public static void main(String[] args) throws Exception {
        // Đặt các cấu hình trước khi tạo SSLContext.
        System.setProperty("jdk.tls.client.enableStatusRequestExtension", "true");
        System.setProperty("com.sun.net.ssl.checkRevocation", "true");
        Security.setProperty("ocsp.enable", "true");

        SSLContext context = SSLContext.getInstance("TLS");
        context.init(null, null, null);
        boolean tls13 = Arrays.asList(context.getSupportedSSLParameters()
                .getProtocols()).contains("TLSv1.3");

        System.out.println("tls13Supported=" + tls13);
        System.out.println("clientStatusRequest="
                + System.getProperty("jdk.tls.client.enableStatusRequestExtension"));
        System.out.println("revocationChecking="
                + System.getProperty("com.sun.net.ssl.checkRevocation"));
        System.out.println("ocspFallback=" + Security.getProperty("ocsp.enable"));

        if (args.length == 0) {
            System.out.println("networkHandshake=SKIPPED");
            return;
        }

        String host = args[0];
        int port = args.length > 1 ? Integer.parseInt(args[1]) : 443;
        try (SSLSocket socket = (SSLSocket) context.getSocketFactory()
                .createSocket(host, port)) {
            socket.setSoTimeout(10_000);
            SSLParameters parameters = socket.getSSLParameters();
            parameters.setEndpointIdentificationAlgorithm("HTTPS");
            socket.setSSLParameters(parameters);
            socket.startHandshake();

            SSLSession session = socket.getSession();
            System.out.println("negotiatedTls=" + session.getProtocol());
            if (session instanceof ExtendedSSLSession extended) {
                System.out.println("stapledResponses="
                        + extended.getStatusResponses().size());
            } else {
                System.out.println("stapledResponses=UNAVAILABLE");
            }
        }
    }
}
```

Biên dịch/chạy offline:

```bash
javac -encoding UTF-8 OcspStaplingDemo.java
java OcspStaplingDemo
```

Kết quả khi chạy trên JDK 24 đã kiểm chứng:

```text
tls13Supported=true
clientStatusRequest=true
revocationChecking=true
ocspFallback=true
networkHandshake=SKIPPED
```

Nếu muốn thử với server **do bạn quản lý hoặc được phép kiểm thử**, có thể chạy:

```bash
java OcspStaplingDemo tls.example.test 443
```

Thay `tls.example.test` bằng hostname hợp lệ có chứng thư được truststore tin cậy, AIA/OCSP hoặc CRL có thể truy cập theo policy và endpoint đang phục vụ TLS. Kết quả `negotiatedTls=...` và `stapledResponses=...` **phụ thuộc server, phiên bản TLS, truststore, thời điểm, provider** nên không được hardcode thành một stdout “chắc chắn”.

**Lưu ý kiểm thử:** `SSLContext.getSupportedSSLParameters()` chỉ cho biết phiên bản được runtime hỗ trợ, không có nghĩa kết nối đã thương lượng TLS 1.3; muốn biết phiên bản của một kết nối, xem `SSLSession.getProtocol()`. Cũng vậy, `System.getProperty` cho thấy **cấu hình đã đặt**, không chứng minh rằng server gửi staple và client xác thực được trạng thái.

Trong ứng dụng thực tế, đừng tắt hostname verification, đừng cài `TrustManager` “trust all certificates” và đừng bỏ qua `SSLHandshakeException` để ép kết nối đi tiếp. Ví dụ dùng `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` vì raw `SSLSocket` không mặc nhiên giống một HTTP client đã cấu hình đầy đủ.

## 8. Tích hợp chính sách PKIX cho ứng dụng Java

Nếu muốn cấu hình theo từng TLS client thay vì thay đổi toàn JVM, hãy khởi tạo trust manager riêng dựa trên `PKIXBuilderParameters` và `CertPathTrustManagerParameters`. Đây là **mảnh tích hợp** minh họa API; giả sử biến `trustStore` là `KeyStore` đã được nạp với các CA gốc tin cậy theo chính sách ứng dụng, không phải file bất kỳ từ mạng:

```java
PKIXBuilderParameters pkix = new PKIXBuilderParameters(
        trustStore, new X509CertSelector());
pkix.setRevocationEnabled(true);

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) CertPathValidator.getInstance("PKIX")
                .getRevocationChecker();
// Chỉ dùng nếu chính sách muốn ưu tiên OCSP và không fallback sang CRL.
checker.setOptions(Set.of(PKIXRevocationChecker.Option.NO_FALLBACK));
pkix.addCertPathChecker(checker);

TrustManagerFactory tmf = TrustManagerFactory.getInstance("PKIX");
tmf.init(new CertPathTrustManagerParameters(pkix));

SSLContext context = SSLContext.getInstance("TLS");
context.init(null, tmf.getTrustManagers(), null);
```

Các import tương ứng gồm `java.security.KeyStore`, `java.security.cert.PKIXBuilderParameters`, `java.security.cert.X509CertSelector`, `java.security.cert.CertPathValidator`, `java.security.cert.PKIXRevocationChecker`, `java.util.Set`, `javax.net.ssl.TrustManagerFactory`, `javax.net.ssl.CertPathTrustManagerParameters` và `javax.net.ssl.SSLContext`. Trước đoạn này, ứng dụng phải nạp truststore tin cậy riêng. Đây **không phải chương trình chạy độc lập**; đừng copy nguyên đoạn vào main khi chưa có truststore.

Ý nghĩa của `PKIXRevocationChecker.Option.NO_FALLBACK` rất cụ thể: không thử cơ chế revocation dự phòng (ví dụ CRL) nếu đường ưu tiên gặp lỗi. Nó **không** có nghĩa “bỏ qua lỗi”; các lựa chọn `SOFT_FAIL` và `PREFER_CRLS` có ý nghĩa khác nhau. Không bật/tắt các option bằng thử vận may: hãy quy định rõ dùng OCSP trực tiếp, CRL hay cả hai, và quyết định lỗi mạng có làm thất bại xác thực hay không. Khi hoạt động trong mạng kín, truststore và responder thường do tổ chức quản lý; cần cung cấp đường dữ liệu thu hồi hoạt động được.

**Chưa đủ nếu chỉ tạo checker.** `PKIXRevocationChecker` chỉ phát huy hiệu lực khi được gắn vào tham số PKIX/trust manager thực sự dùng cho handshake hoặc pipeline `CertPathValidator` tương ứng. Không nên tạo một đối tượng checker rồi không truyền vào ai và tưởng revocation checking đã bật.

Với thư viện HTTP framework (ví dụ dùng SSLContext riêng), hãy kiểm tra nó dùng **đúng** context/trust manager bạn cấu hình. ALPN hoặc HTTP/2 vẫn vận hành theo một cơ chế khác; revocation được đánh giá ở lớp TLS/PKIX.

## 9. Triển khai và giám sát trong production

Một thiết lập tốt nên có các bước vận hành sau:

1. **Xác định nơi terminate TLS.** Với reverse proxy/CDN, cấu hình OCSP stapling trên lớp TLS ngoài cùng; với Java JSSE trực tiếp thì cấu hình trên server JVM.
2. **Kiểm tra đường dẫn PKI.** Đảm bảo leaf/intermediate, hostname, trust anchor, AIA OCSP URL và quyền truy cập từ máy chủ TLS tới responder là chính xác. Không lấy OCSP response của chứng thư cũ sau khi thay cert.
3. **Bật stapling ở máy chủ và revocation checking ở máy khách cần xác thực nghiêm ngặt.** Kể cả khi client có `status_request`, việc xác thực còn lệ thuộc chính sách PKIX.
4. **Làm mới response đúng hạn.** Theo dõi `thisUpdate/nextUpdate`, độ lệch đồng hồ, cache TTL, lỗi responder, response lỗi/chữ ký không hợp lệ và số handshake thất bại. Không coi response từ lần kiểm tra cũ là hợp lệ mãi mãi.
5. **Thiết kế fallback và hành vi khi lỗi rõ ràng.** Định nghĩa fail-open hoặc fail-closed theo rủi ro và tính sẵn sàng; kiểm thử cả trường hợp revoked, unknown, no staple, response cũ và responder tắt.
6. **Kiểm thử từ client thật.** Cấu hình TLS, truststore, JSSE provider, application proxy và chính sách chứng thư của client có thể khác môi trường dev. Theo dõi logs/metrics ở các tầng phù hợp mà không ghi dữ liệu nhạy cảm.

Một cách quan sát trên máy có OpenSSL tương thích (phụ thuộc mạng/đích thật):

```bash
openssl s_client -connect host.example:443 \
  -servername host.example -status -tls1_3
```

Thay `host.example` bằng hostname của server được phép kiểm tra. `-status` yêu cầu và hiển thị thông tin stapled OCSP nếu server gửi. Nếu kết quả có `OCSP response: no response sent`, đó là **không có response được staple**, chưa đủ để kết luận cert revoked. Nếu có response, đối chiếu `Cert Status`, thời gian và chữ ký; công cụ hiển thị riêng các trường và một kết nối thành công không thay thế đánh giá chính sách PKIX của ứng dụng.

## 10. Các nhầm lẫn hay gặp

| Nhận định sai | Sửa lại như thế nào |
| --- | --- |
| “Chứng thư còn hạn là chắc chắn an toàn.” | Còn hạn không loại trừ việc CA đã thu hồi hoặc private key bị lộ. |
| “Có `good` là bỏ qua hostname và chain validation.” | `good` chỉ cung cấp một phần thông tin về revocation; cần kiểm tra đầy đủ PKIX. |
| “Server gửi staple nghĩa là client chắc chắn kiểm tra.” | Client cần có chính sách revocation checking được bật và implementation hỗ trợ. |
| “`jdk.tls.client.enableStatusRequestExtension=true` là đủ.” | Đó chỉ là yêu cầu hỏi staple, không đồng nghĩa bật kiểm tra thu hồi. |
| “Đặt `-Docsp.enable=true` là giống security property.” | `ocsp.enable` là Java security property; cấu hình bằng cơ chế security phù hợp. |
| “OCSP responder không trả lời nghĩa là cert revoked.” | Lỗi truy cập là trạng thái không xác định; chính sách fallback/failure quyết định hành vi. |
| “Status response có `successful` nghĩa là chứng thư `good`.” | Trạng thái xử lý OCSP khác với `SingleResponse.certStatus`. |
| “Stapled response không cần chữ ký vì do TLS server chuyển.” | Cần kiểm tra tính xác thực của responder, thông tin cert và thời gian. |
| “Chỉ cần bật ở Java app sau load balancer.” | OCSP stapling phải đặt tại điểm kết thúc TLS thực tế. |
| “TLS 1.3 gửi thông điệp `CertificateStatus` giống TLS 1.2.” | TLS 1.3 đặt OCSP vào extension của `CertificateEntry`. |
| “Dùng `status_request_v2` để hỗ trợ TLS 1.3 tốt hơn.” | RFC 9846 đã deprecated `status_request_v2`; dùng `status_request`. |
| “OCSP stapling và ALPN là một extension.” | Hai extension có vai trò và chính sách hoàn toàn khác nhau. |
| “`getStatusResponses().size()==0` nghĩa là revoked.” | Danh sách rỗng có thể do không được staple hoặc provider không trả thông tin. |

## 11. Tự kiểm tra kiến thức

**Câu 1.** Server gửi chứng thư còn hạn, chain ký đúng, nhưng OCSP response xác thực được báo `revoked`. Client có nên chấp nhận trong chính sách yêu cầu revocation hợp lệ? **Trả lời:** Không; phải từ chối chứng thư revoked.

**Câu 2.** Trên client Java, bạn bật `jdk.tls.client.enableStatusRequestExtension=true` nhưng không bật revocation checking. Bạn có thể khẳng định JSSE đã bác bỏ cert revoked nhờ staple không? **Trả lời:** Không. Extension xin thông tin và việc xác minh PKIX là hai việc khác nhau.

**Câu 3.** Trong TLS 1.3, OCSP response stapled nằm ở đâu? **Trả lời:** Trong extension `status_request` gắn với `CertificateEntry` của chứng thư liên quan theo RFC 9846; không tìm `CertificateStatus` riêng như TLS 1.2.

**Câu 4.** OCSP response cho biết `unknown` hoặc đã quá `nextUpdate`; có được coi tương đương `good`? **Trả lời:** Không. Cần áp dụng chính sách và fallback nếu cấu hình cho phép.

**Câu 5.** Dịch vụ Java chạy phía sau ingress thực hiện HTTPS. Ở đâu nên bật stapling cho client ngoài Internet? **Trả lời:** Trên ingress/thiết bị đang terminate TLS công khai.

**Câu 6.** Một lập trình viên in `stapledResponses=1` và tuyên bố chứng thư hợp lệ. Điều gì sai? **Trả lời:** Đếm phản hồi không kiểm tra chữ ký, chứng thư, thời gian, status và chain/hostname. Phải dựa vào kiểm tra PKIX được cấu hình hợp lệ.

**Câu 7.** Tại sao stapling thường giảm ảnh hưởng riêng tư so với client-driven OCSP? **Trả lời:** Máy chủ lấy/cache phản hồi từ responder và chuyển cho nhiều máy khách, nên responder không cần nhận yêu cầu trực tiếp của từng máy khách.

## Tài liệu chuẩn và hướng dẫn còn áp dụng

- [RFC 9846 — The Transport Layer Security (TLS) Protocol Version 1.3, §4.5.1.1](https://www.rfc-editor.org/rfc/rfc9846.html): chuẩn TLS 1.3 hiện hành (2026), vị trí `status_request`, cập nhật và thay thế tài liệu TLS 1.3 trước đó.
- [RFC 6960 — X.509 Online Certificate Status Protocol (OCSP)](https://www.rfc-editor.org/rfc/rfc6960.html): định dạng, xác minh và ý nghĩa `good/revoked/unknown`, `thisUpdate/nextUpdate`.
- [RFC 7633 — X.509v3 TLS Feature Extension](https://www.rfc-editor.org/rfc/rfc7633.html): thông tin về chính sách TLS Feature/Must-Staple; mức thực thi khác nhau tùy client.
- [Oracle JDK 27 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/27/security/java-secure-socket-extension-jsse-reference-guide.html): cấu hình stapling client/server, certificate revocation và cache/fallback của SunJSSE.
- [Oracle Java SE 21 — ExtendedSSLSession.getStatusResponses()](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/javax/net/ssl/ExtendedSSLSession.html#getStatusResponses()): API Java 9+ đọc danh sách OCSP responses DER khi provider hỗ trợ.
- [Oracle Java SE 21 — PKIXRevocationChecker](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): lựa chọn kiểm tra thu hồi và phương pháp tích hợp PKIX.

**Điểm cốt lõi để áp dụng:** OCSP stapling giúp server chuyển thông tin thu hồi chứng thư đã được ký tới client trong TLS handshake; **việc máy khách thật sự từ chối chứng thư bị thu hồi phụ thuộc kiểm tra PKIX/JSSE được bật, chất lượng/freshness của phản hồi và chính sách khi không có dữ liệu**. Luôn kiểm tra nơi terminate TLS và cấu hình trust manager thực tế.
