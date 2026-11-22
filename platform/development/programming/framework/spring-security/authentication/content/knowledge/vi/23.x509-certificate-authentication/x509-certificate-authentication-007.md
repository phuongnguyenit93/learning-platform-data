# Hết hạn, thu hồi chứng thư và kiểm thử chuỗi tin cậy

Xác thực bằng chứng thư X.509 dựa trên nhiều điều kiện **đồng thời**: chứng thư nằm trong khoảng hiệu lực, chuỗi chứng thư được ký hợp lệ và dẫn đến một **trust anchor** được tin cậy, khóa/chứng thư đúng mục đích sử dụng, trạng thái thu hồi phù hợp chính sách và danh tính được ánh xạ đúng với tài khoản ứng dụng. Một chứng thư có chữ ký đúng vẫn có thể hết hạn, bị CA thu hồi, thuộc CA không được phép hoặc mang danh tính chưa được cấp quyền.

Trong ứng dụng Spring Security sử dụng **mutual TLS (mTLS)**, việc xác minh chứng thư client trước hết thuộc **TLS stack** (ví dụ Tomcat + JSSE hoặc API gateway). Chỉ khi TLS handshake được chấp nhận, Spring Security mới có cơ hội đọc chứng thư, xác định principal và nạp quyền. Vì vậy, cần phân biệt rõ lỗi ở **tầng TLS/PKIX** với lỗi **HTTP authorization**: một chứng thư bị từ chối tại TLS thường không tạo ra response HTTP 401/403 từ ứng dụng.

Bài học này tập trung vào **hết hạn, thu hồi chứng thư và kiểm thử chuỗi tin cậy** trong bối cảnh xác thực X.509 trên Spring Security Servlet, với ví dụ Java 17+, Spring Boot 3.x, Spring Security 6.x và OpenSSL 3.x. Tên miền và các file `.pem`/`.p12` là fixture minh họa; không dùng CA production để tạo hoặc thu hồi chứng thư chỉ nhằm chạy bài thử.

## 1. Ba câu hỏi bắt buộc khi xác minh X.509

| Nhóm kiểm tra | Câu hỏi chính | Kiểm tra điển hình |
| --- | --- | --- |
| **Thời gian hiệu lực** | Chứng thư hiện có hiệu lực chưa, đã hết hạn chưa? | `notBefore`, `notAfter`, thời gian hệ thống, thời hạn các intermediate |
| **Chuỗi tin cậy và mục đích** | Ai ký chứng thư? Có đường dẫn đến CA được phép không? Đúng mục đích TLS không? | Signature, path building, trust anchor, Basic Constraints, Key Usage, EKU, SAN/hostname |
| **Thu hồi** | CA đã rút hiệu lực trước thời điểm hết hạn chưa? | CRL, OCSP, chữ ký và độ mới của phản hồi, fail policy |

Kiểm tra cả ba **chưa đủ để cấp quyền ứng dụng**: sau khi chứng thư client hợp lệ, ứng dụng vẫn phải xác định người dùng và quyền nghiệp vụ. Ví dụ client `CN=client-linh` có thể vượt qua mTLS nhưng bị HTTP 403 nếu tài khoản ứng dụng không có authority `API_READ`.

Những trường X.509 thường cần đọc:

- `Subject` và `Issuer`: nhận diện subject và CA phát hành; hai chuỗi này giống kỳ vọng **không thay thế** xác minh chữ ký.
- `Serial Number`: nhận diện chứng thư trong phạm vi issuer, rất quan trọng khi xem CRL/OCSP. Serial đứng một mình không định danh duy nhất trên mọi CA.
- `Not Before`/`Not After`: khoảng hiệu lực của từng chứng thư.
- `Subject Alternative Name (SAN)`: định danh DNS/URI/email... Với chứng thư HTTPS server, hostname phải khớp SAN theo chính sách của client.
- `Basic Constraints`: xác định chứng thư có được làm CA không và giới hạn độ dài chuỗi.
- `Key Usage`: quyền sử dụng khóa như digitalSignature hoặc keyCertSign.
- `Extended Key Usage (EKU)`: ví dụ `clientAuth` (TLS Web Client Authentication) và `serverAuth` (TLS Web Server Authentication).
- `Authority Key Identifier`, `Subject Key Identifier`: hỗ trợ liên kết key/issuer khi xây dựng path.
- `CRL Distribution Points` và `Authority Information Access`: có thể dẫn tới nguồn CRL, OCSP hoặc intermediate CA. URI có trong chứng thư **không có nghĩa** mọi runtime sẽ tự tải hoặc tự bật kiểm tra thu hồi.

## 2. Chuỗi tin cậy gồm root, intermediate và leaf

Ví dụ một tổ chức cấp chứng thư mTLS cho nhân viên:

~~~text
TRUSTSTORE của server
└── Corporate Root CA                   [Trust Anchor]
          │ ký
          ▼
    Employee Issuing CA                 [Intermediate CA]
          │ ký
          ▼
    client-linh                         [Leaf / End-Entity]
    EKU: TLS Web Client Authentication
          │ sử dụng private key trong TLS handshake
          ▼
    Client kết nối HTTPS đến server
~~~

**Trust anchor** là gốc mà bên xác minh **đã quyết định tin cậy** qua cấu hình. Truststore server chứa CA được phép cấp client certificate; keystore server chứa khóa riêng và chứng thư server để trình cho phía client. Phía client cũng có CA tin cậy riêng để xác minh chứng thư server.

Trong thuật toán PKIX, validator cần dựng và kiểm tra đường từ leaf qua issuer/intermediate đến trust anchor. Một intermediate được gửi kèm qua TLS chỉ là dữ liệu để xây dựng path, **không tự được tin cậy**. Những điều kiện quan trọng gồm:

1. Chữ ký của mỗi chứng thư dưới chứng thư issuer phải hợp lệ.
2. Mỗi intermediate làm CA cần đáp ứng `basicConstraints CA=true`, key usage và `pathLenConstraint` áp dụng.
3. Thời hạn và ràng buộc thuật toán/chính sách phải hợp lệ theo bộ validator.
4. Đường kết thúc ở trust anchor nằm trong tập CA được phép, không phải một root bất kỳ có chữ ký tự ký.
5. Với mTLS, chứng thư leaf phải phù hợp mục đích client authentication; với HTTPS server, server certificate còn cần khớp hostname của kết nối.

**Thiếu intermediate:** leaf có thể do CA hợp lệ ký nhưng server không tìm được issuer để xây chain. **Sai root:** chữ ký vẫn có thể hợp lệ theo một CA khác, song CA đó không nằm trong truststore của ứng dụng. **Sai EKU:** chain đúng nhưng chứng thư chỉ dùng cho `serverAuth`, không phù hợp làm client certificate.

Không kết luận chain hợp lệ chỉ nhờ `Subject` và `Issuer` cùng tên; phải dùng thuật toán xác minh chữ ký/PKIX.

## 3. Hết hạn: kiểm tra Not Before và Not After

Thời hạn chứng thư được biểu diễn bằng hai mốc:

~~~text
                  Khoảng có hiệu lực
notBefore  |================================|  notAfter
           |                                |
   Trước mốc: chưa hợp lệ          Sau mốc: hết hạn
~~~

- **Not Before:** client không nên dùng chứng thư trước khi đến thời điểm này. Đây thường là lỗi cấp chứng thư có thời điểm bắt đầu trong tương lai hoặc đồng hồ máy xác minh đang bị lệch.
- **Not After:** chứng thư hết hạn khi vượt quá thời điểm kết thúc hiệu lực; không thể “gia hạn” bằng cách đổi đồng hồ JVM hay sửa metadata PEM.
- **Intermediate expiry:** leaf còn hạn nhưng intermediate trong chain hết hạn vẫn có thể khiến path validation thất bại.
- **Đồng hồ:** phần kiểm tra thời hạn dùng thời gian ở nơi validation diễn ra. Cần đồng bộ NTP và hiểu các mốc UTC; giao diện hiển thị theo múi giờ địa phương có thể gây nhầm lẫn.

### 3.1. Đọc thời hạn và các extension với OpenSSL

~~~bash
openssl x509 -in pki/client-valid.pem -noout -subject -issuer -serial -dates
openssl x509 -in pki/client-valid.pem -noout -text
~~~

Một output thời hạn điển hình có trường `notBefore=...` và `notAfter=...`. Phần `-text` giúp tìm `Basic Constraints`, `Key Usage`, `Extended Key Usage`, `Authority Information Access` và `CRL Distribution Points`. Đây mới chỉ là **đọc cấu trúc chứng thư**, chưa phải kiểm tra truststore hay trạng thái thu hồi.

Nếu chứng thư nằm trong PKCS#12:

~~~bash
keytool -list -v -storetype PKCS12 -keystore pki/client-keystore.p12
~~~

`keytool` thường yêu cầu mật khẩu tương tác. Không đưa mật khẩu keystore lên lịch sử lệnh, source code hoặc log CI. Kiểm tra tất cả chứng thư trong chain và alias liên quan, không chỉ leaf.

### 3.2. Kiểm thử tại một thời điểm xác định

Có thể kiểm tra path ở timestamp UNIX cố định (ví dụ 2026-11-06 00:00:00 UTC):

~~~bash
openssl verify \
  -CAfile pki/root-ca.pem \
  -untrusted pki/intermediate-ca.pem \
  -purpose sslclient \
  -attime 1793923200 \
  pki/client-valid.pem
~~~

`-attime` khiến OpenSSL đánh giá hiệu lực ở thời điểm được chọn, hữu ích khi kiểm thử chứng thư chưa có hiệu lực hoặc sắp hết hạn. Nó **không thay đổi đồng hồ của Spring Boot/Tomcat** và không thay thế bài test revocation lịch sử. Thời điểm sử dụng cần khớp thời gian mốc của test fixture.

### 3.3. Kiểm tra thời hạn bằng Java 17

`X509Certificate.checkValidity()` kiểm tra thời hạn trên một chứng thư. Đoạn chương trình độc lập dưới đây đọc `.pem` và kiểm tra cả thời gian hiện tại lẫn một thời gian cố định.

Tệp `CertificateTimeCheck.java`:

~~~java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateExpiredException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertificateNotYetValidException;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.util.Date;

public class CertificateTimeCheck {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            System.err.println("Usage: java CertificateTimeCheck <cert.pem>");
            System.exit(2);
        }

        X509Certificate cert;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            cert = (X509Certificate)
                    CertificateFactory.getInstance("X.509")
                            .generateCertificate(in);
        }

        System.out.println("Subject: " + cert.getSubjectX500Principal());
        System.out.println("Issuer: " + cert.getIssuerX500Principal());
        System.out.println("NotBefore: " + cert.getNotBefore().toInstant());
        System.out.println("NotAfter: " + cert.getNotAfter().toInstant());

        try {
            cert.checkValidity();
            System.out.println("Current time: VALID");
        } catch (CertificateExpiredException e) {
            System.out.println("Current time: EXPIRED");
        } catch (CertificateNotYetValidException e) {
            System.out.println("Current time: NOT_YET_VALID");
        }

        Instant fixedTime = Instant.parse("2026-11-06T00:00:00Z");
        try {
            cert.checkValidity(Date.from(fixedTime));
            System.out.println("Fixed time: VALID");
        } catch (CertificateExpiredException e) {
            System.out.println("Fixed time: EXPIRED");
        } catch (CertificateNotYetValidException e) {
            System.out.println("Fixed time: NOT_YET_VALID");
        }
    }
}
~~~

Biên dịch/chạy bằng JDK 17+ khi đã có file chứng thư:

~~~bash
javac --release 17 CertificateTimeCheck.java
java CertificateTimeCheck pki/client-valid.pem
~~~

Giá trị Subject/Issuer/NotBefore/NotAfter và hai dòng kết quả phụ thuộc **nội dung certificate thực tế**, nên không có stdout cố định cho các file minh họa. Nếu gọi `checkValidity()` không lỗi, chỉ kết luận chứng thư hợp lệ **về thời gian**. Phương thức này không kiểm tra chữ ký, CA tin cậy, revocation, hostname, mục đích hay quyền ứng dụng. Để kiểm tra chain, dùng PKIX `CertPathValidator` hoặc TLS trust manager được cấu hình đúng.

## 4. Thu hồi chứng thư trước thời hạn

**Revocation** xảy ra khi CA rút hiệu lực của chứng thư trước khi `notAfter` kết thúc, chẳng hạn private key bị lộ, thiết bị mất, tài khoản bị vô hiệu hóa hoặc chứng thư được cấp sai. “Chưa hết hạn” **không đồng nghĩa** “chưa bị thu hồi”.

Các trạng thái cần phân biệt:

| Kết quả | Có thể suy ra điều gì? |
| --- | --- |
| `expired` | Không hợp lệ về thời gian, dù OCSP/CRL chưa liệt kê serial |
| `not yet valid` | Chưa đến thời điểm sử dụng, không phải trạng thái thu hồi |
| `revoked` | CA/responder hợp lệ đã thông báo chứng thư bị rút hiệu lực |
| OCSP `good` | Responder nói chứng thư không bị thu hồi theo nguồn và thời điểm phản hồi; vẫn cần kiểm tra chain/mục đích |
| OCSP `unknown` | Không xác định được trạng thái; **không tự chuyển thành good** |
| CRL/OCSP không truy cập được | Chưa chứng minh được trạng thái; cần hard-fail/soft-fail policy rõ ràng |

### 4.1. CRL — Certificate Revocation List

CRL là danh sách serial bị thu hồi **do CA ký**. Một CRL dùng được cần đúng issuer/phạm vi, chữ ký hợp lệ, thời điểm `thisUpdate`/`nextUpdate` phù hợp và dữ liệu đủ mới. Nếu thiết lập check toàn chain, cần có CRL phù hợp cho leaf và các intermediate cần xác minh, không chỉ file CRL leaf.

Ưu điểm: tải/cache được, có thể kiểm tra offline khi CRL còn hiệu lực. Hạn chế: danh sách có thể lớn, việc phát hành định kỳ tạo độ trễ giữa lúc revoke và lúc các verifier nhận bản mới.

**Không mặc định CRLDP tự động được tải.** Việc chứng thư có URI CRL là một chỉ dẫn, còn cách runtime tải/cache/check là cấu hình riêng.

### 4.2. OCSP — Online Certificate Status Protocol

OCSP cho phép hỏi responder về trạng thái của một chứng thư theo issuer và serial. Phản hồi phải được kiểm tra chữ ký, chứng thư/ủy quyền ký OCSP, độ mới và trạng thái `good`/`revoked`/`unknown`.

Một response HTTP 200 từ OCSP server hoặc chữ `good` từ nguồn không được xác minh **không đủ** để cấp quyền truy cập. OCSP có thể bị lỗi mạng, quá hạn `nextUpdate` hoặc trả `unknown`; cần định nghĩa cách xử lý.

**Phân biệt OCSP stapling:** nhiều tài liệu mô tả server đính kèm OCSP response cho chứng thư **server** trong bắt tay HTTPS. Điều đó không chứng minh phía **server đã kiểm tra thu hồi chứng thư client** khi dùng mTLS. Phải kiểm tra chính sách của đúng bên đang xác thực certificate.

### 4.3. Hard-fail và soft-fail

| Trường hợp | Hard-fail | Soft-fail |
| --- | --- | --- |
| Chứng thư bị thu hồi theo response hợp lệ | Từ chối | **Vẫn từ chối** |
| Không lấy được CRL/OCSP vì lỗi mạng | Từ chối | Có thể tiếp tục nếu policy cho phép |
| Response OCSP quá cũ/sai chữ ký | Không dùng làm bằng chứng tốt | Không chấp nhận dữ liệu giả; xử lý lỗi theo policy |
| Trạng thái OCSP `unknown` | Không coi là tốt | Không tự mặc định thành good |

`PKIXRevocationChecker.Option.SOFT_FAIL` trong Java chỉ cho phép bỏ qua **một số lỗi xác định** khi không thể thu thập thông tin revocation, không phải lựa chọn “bỏ qua chứng thư đã bị thu hồi”. Với hệ thống yêu cầu bảo mật cao, hard-fail tránh chấp nhận certificate khi nguồn revocation không đáng tin cậy, nhưng cần SLA/timeout/cache tốt để tránh làm toàn dịch vụ gián đoạn.

## 5. Kiểm thử chuỗi với OpenSSL

Giả sử test PKI có các file:

~~~text
pki/
├── root-ca.pem
├── intermediate-ca.pem
├── client-valid.pem
├── client-expired.pem
├── client-revoked.pem
├── client-untrusted.pem
├── client-server-only.pem
├── issuing-ca.crl.pem
├── client-valid.key
└── server-root.pem
~~~

Mọi certificate cần do test CA tạo hợp lệ cho tình huống được mô phỏng. Một file chỉ đổi tên thành `client-revoked.pem` **không** tự trở thành revoked.

### 5.1. Kiểm tra chain/trust anchor và đúng mục đích client

~~~bash
openssl verify \
  -show_chain \
  -CAfile pki/root-ca.pem \
  -untrusted pki/intermediate-ca.pem \
  -purpose sslclient \
  pki/client-valid.pem
~~~

- `-CAfile`: CA mà lệnh **chủ động tin cậy**, thường là root trong fixture.
- `-untrusted`: cung cấp intermediate để xây chain, **không** có nghĩa intermediate được thêm làm trust anchor.
- `-purpose sslclient`: yêu cầu xác minh mục đích sử dụng TLS client, gồm các ràng buộc phù hợp trong OpenSSL.
- `-show_chain`: in chain đã được xây để đối chiếu với issuer mong đợi.

Với fixture thực sự hợp lệ, output có dòng:

~~~text
pki/client-valid.pem: OK
~~~

Lệnh này **không** chứng minh đã kiểm tra thu hồi nếu không có revocation options; cũng không kiểm tra việc client sở hữu private key trong TLS handshake.

### 5.2. Kiểm tra thiếu intermediate và root sai

Khi không cung cấp intermediate (và không có nguồn khác), lệnh có thể thất bại:

~~~bash
openssl verify -CAfile pki/root-ca.pem \
  -purpose sslclient pki/client-valid.pem
~~~

Khi dùng root không phải issuer hợp lệ:

~~~bash
openssl verify \
  -CAfile pki/unrelated-root.pem \
  -untrusted pki/intermediate-ca.pem \
  -purpose sslclient \
  pki/client-valid.pem
~~~

Kết quả có thể mang lỗi `unable to get local issuer certificate`, `unable to verify the first certificate` hoặc lý do phù hợp với fixture. Không giả định mã lỗi/chuỗi stdout giống nhau giữa các phiên bản OpenSSL.

### 5.3. Kiểm tra CRL và chứng thư đã thu hồi

~~~bash
openssl crl \
  -in pki/issuing-ca.crl.pem \
  -noout -issuer -lastupdate -nextupdate
~~~

Lệnh trên kiểm tra metadata của CRL; muốn xem danh sách serial bị thu hồi:

~~~bash
openssl crl -in pki/issuing-ca.crl.pem -noout -text
~~~

Sau khi bảo đảm CRL được test CA ký đúng và còn thời hạn:

~~~bash
openssl verify \
  -CAfile pki/root-ca.pem \
  -untrusted pki/intermediate-ca.pem \
  -purpose sslclient \
  -CRLfile pki/issuing-ca.crl.pem \
  -crl_check \
  pki/client-revoked.pem
~~~

`-crl_check` yêu cầu CRL cho end-entity. `-crl_check_all` yêu cầu kiểm tra thêm các chứng thư trong chain, vì vậy cần CRL đúng của những issuer tương ứng. Khi serial leaf thực sự được liệt kê trong CRL hợp lệ, lệnh phải **thất bại** vì `certificate revoked`. Nếu CRL không tìm được hoặc quá cũ, đó là lỗi thiếu bằng chứng, không phải xác nhận chứng thư còn tốt.

### 5.4. Truy vấn OCSP từ test responder

~~~bash
openssl ocsp \
  -issuer pki/intermediate-ca.pem \
  -cert pki/client-valid.pem \
  -url http://ocsp.pki.example.test \
  -CAfile pki/root-ca.pem \
  -resp_text
~~~

Cần endpoint OCSP tồn tại và thông tin CA/responder hợp lệ; output phụ thuộc tình trạng thực tế. Lệnh minh họa cách truy vấn và đọc response, **không** làm thay việc thiết lập revocation checking của server. Hãy kiểm tra issuer, chữ ký responder, `thisUpdate`, `nextUpdate` và kết quả theo policy.

### 5.5. Kiểm tra key, mTLS và hostname bằng HTTPS thật

~~~bash
curl --cacert pki/server-root.pem \
  --resolve api.example.test:8443:127.0.0.1 \
  --cert pki/client-valid.pem \
  --key pki/client-valid.key \
  https://api.example.test:8443/api/private/ping
~~~

- `--cacert` cho phép curl kiểm tra chứng thư **server** bằng CA đã chọn.
- `--resolve` giữ hostname `api.example.test` cho TLS hostname verification nhưng kết nối đến IP lab.
- `--cert` và `--key` để client tham gia mTLS; private key không được gửi cho server.
- Phải có **server certificate SAN chứa `api.example.test`** và client chain đúng. Nếu cần, file `--cert` có thể chứa leaf kèm intermediate.

Không dùng `curl -k` trong bài kiểm thử trust vì flag đó bỏ qua xác minh chứng thư server. Nếu chương trình Spring chưa chạy hoặc chứng thư không tồn tại, command không thể có kết quả HTTP mong đợi.

## 6. Kiểm thử PKIX trong Java: mức độ và giới hạn

Các API chính:

- `CertificateFactory` đọc X.509 từ file, tạo `CertPath` theo thứ tự leaf → intermediate.
- `TrustAnchor` biểu diễn root/CA được tin cậy.
- `PKIXParameters` chứa trust anchors, cert stores, chính sách, thời điểm validation và bật/tắt revocation.
- `CertPathValidator.getInstance("PKIX")` kiểm tra đường đã dựng.
- `PKIXRevocationChecker` bổ sung quy tắc OCSP/CRL khi được cấu hình và hỗ trợ.

Ví dụ mã **minh họa đặt trong phương thức**, có sẵn biến `leaf`, `intermediate`, `root` kiểu `X509Certificate`:

~~~java
CertificateFactory factory = CertificateFactory.getInstance("X.509");

// CertPath từ leaf tới intermediate; trust anchor nằm bên ngoài path.
CertPath path = factory.generateCertPath(List.of(leaf, intermediate));

TrustAnchor rootAnchor = new TrustAnchor(root, null);
PKIXParameters params = new PKIXParameters(Set.of(rootAnchor));

params.setRevocationEnabled(false); // Chỉ minh họa chain, CHƯA kiểm tra CRL/OCSP.
CertPathValidator.getInstance("PKIX").validate(path, params);
~~~

Các import thuộc `java.security.cert` và `java.util`; đây là snippet cần truyền chứng thư/khai báo biến từ program khác, **không** phải file độc lập chạy ngay. `setRevocationEnabled(false)` chỉ dùng để tách riêng path validation trong test; không coi đó là cấu hình production phù hợp.

Nếu bật kiểm tra revocation trong validator được cấu hình đầy đủ:

~~~java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

// Không bật SOFT_FAIL trong ví dụ.
checker.setOptions(Set.of(PKIXRevocationChecker.Option.NO_FALLBACK));

PKIXParameters params = new PKIXParameters(trustAnchors);
params.setRevocationEnabled(true);
params.addCertPathChecker(checker);

// certPath và trustAnchors phải được chuẩn bị từ nguồn đáng tin cậy.
// Cấu hình bổ sung responder / CRL / CertStore tùy PKI thực tế.
validator.validate(certPath, params);
~~~

`NO_FALLBACK` điều khiển cơ chế fallback OCSP/CRL của checker, không tạo dữ liệu revocation hợp lệ. Nếu test cần CRL offline, có thể cấp `CertStore` chứa những CRL đã ký đúng và còn hạn; nếu cần OCSP, phải xác minh responder được cấu hình và kết nối được. Việc chạy thủ công một `CertPathValidator` trong ứng dụng **không tự bật** cấu hình đó trong TLS trust manager đang dùng.

## 7. Spring Boot + Spring Security: giới hạn trách nhiệm

### 7.1. Hai tầng kiểm tra của mTLS

~~~text
Client certificate + private key
              │ TLS handshake
              ▼
Embedded Tomcat / Java JSSE (hoặc gateway)
   ├── xác minh chain, thời hạn, trust anchor, mục đích
   ├── revocation nếu được cấu hình và hỗ trợ
   └── thất bại → lỗi TLS, chưa có request HTTP
              │ thành công
              ▼
Spring Security X509AuthenticationFilter
   ├── đọc chứng thư client được container cung cấp
   ├── trích xuất principal
   ├── nạp UserDetails và GrantedAuthority
   └── authorization → cho phép hoặc từ chối HTTP
~~~

`http.x509(...)` **không** thay thế bộ trust manager ở tầng TLS. Nếu chứng thư hết hạn hoặc CA không được tin và TLS chặn, Spring không thể “cứu” xác thực bằng một `UserDetailsService`. Nếu TLS thành công nhưng người dùng không được cấp quyền, lỗi xảy ra **sau TLS**, thường là HTTP 403.

### 7.2. Dependencies và cấu hình SSL ở Spring Boot 3.x

Trong `build.gradle` của ứng dụng servlet đã có Spring Boot plugin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
}
~~~

Trong `src/main/resources/application.properties`:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=${TLS_SERVER_KEYSTORE}
server.ssl.key-store-password=${TLS_SERVER_KEYSTORE_PASSWORD}
server.ssl.key-store-type=PKCS12

server.ssl.trust-store=${TLS_CLIENT_CA_TRUSTSTORE}
server.ssl.trust-store-password=${TLS_CLIENT_CA_TRUSTSTORE_PASSWORD}
server.ssl.trust-store-type=PKCS12

server.ssl.client-auth=need
~~~

- **Server keystore** chứa server private key và server certificate chain.
- **Client CA truststore** chứa những CA mà server cho phép phát hành client certificates. Không đưa mọi CA công cộng vào truststore chỉ để thử cho qua.
- `server.ssl.client-auth=need` yêu cầu client certificate ngay trong TLS handshake; `want` chỉ yêu cầu khi client có chứng thư.
- Các giá trị biến môi trường/secret phải trỏ đúng resource keystore/truststore, có quyền đọc và mật khẩu hợp lệ. Ví dụ chưa thể khởi động nếu chưa chuẩn bị PKI.
- Đây là cấu hình yêu cầu client cert và CA trust; **không tự chứng minh đã bật CRL/OCSP**.

### 7.3. Ví dụ ánh xạ X.509 sang quyền ứng dụng

Tệp `src/main/java/example/mtls/MtlsApplication.java`:

~~~java
package example.mtls;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class MtlsApplication {
    public static void main(String[] args) {
        SpringApplication.run(MtlsApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class MtlsSecurityConfig {

    @Bean
    UserDetailsService certificateUsers() {
        // Dữ liệu demo, production phải dùng repository và định danh ổn định.
        return username -> {
            if (!"client-linh".equals(username)) {
                throw new UsernameNotFoundException("Unknown application client");
            }
            return User.withUsername(username)
                    .password("{noop}not-used")
                    .authorities("API_READ")
                    .build();
        };
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http, UserDetailsService certificateUsers)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/private/**").hasAuthority("API_READ")
                .anyRequest().authenticated());

        http.x509(x509 -> x509
                .subjectPrincipalRegex("CN=(.*?)(?:,|$)")
                .userDetailsService(certificateUsers));

        http.formLogin(AbstractHttpConfigurer::disable);
        http.httpBasic(AbstractHttpConfigurer::disable);
        return http.build();
    }
}

@RestController
class PrivateController {
    @GetMapping("/api/private/ping")
    String ping() {
        return "ok";
    }
}
~~~

Ở đây:

1. Tomcat/JSSE chấp nhận hoặc từ chối client certificate theo cấu hình TLS trước.
2. Spring Security trích principal từ Subject DN, ví dụ `CN=client-linh` thành `client-linh`.
3. `UserDetailsService` nạp authority `API_READ`. `password("{noop}not-used")` chỉ là giá trị cấu trúc trong `UserDetails`; không dùng mật khẩu này để xác thực certificate.
4. Endpoint yêu cầu `API_READ`, nên một client có chứng thư hợp lệ nhưng tài khoản nội bộ không có quyền vẫn bị từ chối.
5. Regex CN chỉ phù hợp **minh họa**: CN có thể không duy nhất hoặc dễ thay đổi. Ở production, nên ánh xạ issuer + định danh bền vững (ví dụ Subject Alternative Name theo chính sách), tránh dùng CN trùng hoặc tên tự khai báo chưa được quản trị.

Trong dự án có TLS và fixture hợp lệ, chạy:

~~~bash
./gradlew bootRun
~~~

Sau đó dùng `curl` ở mục 5.5. Nếu server certificate, client certificate, private key, chain và user mapping đều đúng, kết quả dự kiến từ endpoint là:

~~~text
ok
~~~

Nếu TLS fail, có thể **không có HTTP response**; không khẳng định tất cả lỗi mTLS sẽ là HTTP 401/403.

### 7.4. Khi mTLS kết thúc ở reverse proxy/gateway

Nếu gateway xác thực chứng thư rồi chuyển request HTTP đến Spring Boot, backend thường **không trực tiếp thấy** client certificate trên servlet request. Một header như `X-Client-Cert`/`X-Verified-User` chỉ được tin nếu gateway bảo đảm:

- Backend không nhận traffic trực tiếp từ internet/vòng qua gateway.
- Gateway loại bỏ header danh tính do client tự gửi rồi tự tạo lại từ session/certificate đã xác minh.
- Kết nối gateway → backend được bảo vệ theo mô hình đe dọa (mTLS hoặc mạng truy cập giới hạn).
- Cơ chế mapping danh tính, issuer, tenant và quyền không cho phép tự nâng quyền bằng một chuỗi header.

Trong mô hình này, chính **gateway** là nơi phải có chính sách expiry, trust chain và revocation cho client certificate. `http.x509(...)` ở backend không thể tự kiểm tra revocation của một chứng thư đã bị gateway bỏ đi.

## 8. Thực sự bật revocation checking ở Java/TLS

Một cấu hình Java PKIX hoặc property Spring Security **không chứng minh** Java TLS stack đã bật kiểm tra CRL/OCSP. Cần biết nơi TLS termination diễn ra và runtime/provider/trust manager nào được dùng.

Với một số hệ thống SunJSSE/SunPKIX, có các system properties:

~~~text
-Dcom.sun.net.ssl.checkRevocation=true
-Dcom.sun.security.enableCRLDP=true
~~~

Và Java security property hỗ trợ OCSP:

~~~java
java.security.Security.setProperty("ocsp.enable", "true");
~~~

Security property phải được cấu hình trước khi SSL context/trust manager được khởi tạo (hoặc trong file java.security được JVM tải). **Đừng nhầm** `ocsp.enable` dạng Java security property với một Java `-D` system property bất kỳ. Tính hiệu lực của từng thiết lập cần đối chiếu với phiên bản Java, PKIX provider, Tomcat hoặc gateway thực tế.

Một hệ thống có thể sử dụng `PKIXRevocationChecker`/`PKIXParameters.setRevocationEnabled(true)`, hoặc custom JSSE trust manager đúng cách. Tuy nhiên, một đoạn `CertPathValidator` chạy trong unit test **không tự động áp dụng** cho TLS trust manager của Tomcat. Chỉ kiểm chứng được cấu hình production khi test **revoked certificate còn hạn** bị từ chối đúng ở TLS layer và test timeout/outage tuân theo chính sách đã chọn.

Ngoài ra:

- Nếu dùng CRL, phải có đúng CRL của issuer, chữ ký hợp lệ và freshness đáp ứng policy.
- Nếu dùng OCSP, phải xác minh responder, thời điểm phản hồi, signature, `good/revoked/unknown`.
- Nếu bật hard-fail, cần timeout/HA hợp lý cho responder để tránh dừng mọi đăng nhập do outage PKI.
- Nếu cho soft-fail, phải có đánh giá rủi ro và giám sát các lần không kiểm tra được; trạng thái `revoked` hợp lệ vẫn phải bị từ chối.
- Chứng thư có thể bị revoke **sau khi một kết nối TLS đã được thiết lập**. Các kết nối/session đang mở không tự bị hủy ngay vì bản CRL cập nhật; cần chính sách vòng đời kết nối, session và thu hồi tài khoản ứng dụng.

## 9. Ma trận kiểm thử đầy đủ

Tạo bộ fixture **bằng test CA** rồi kiểm thử từng điều kiện độc lập. Nếu test revoked, chứng thư phải **còn hạn, chain hợp lệ và đúng EKU**; nếu không, một lỗi hết hạn có thể che lỗi revocation và dẫn đến kết luận sai.

| Trường hợp | Thiết lập | Kết quả mong đợi |
| --- | --- | --- |
| 1. Mọi điều kiện hợp lệ | Root tin cậy, chain đủ, leaf còn hạn, đúng EKU, status good, user có `API_READ` | TLS thành công, endpoint trả HTTP 200 |
| 2. Không gửi client certificate | `server.ssl.client-auth=need`, request không có `--cert` | TLS handshake bị từ chối |
| 3. Leaf hết hạn | `notAfter` ở quá khứ | Bị từ chối ở TLS/path; `checkValidity` báo expired |
| 4. Leaf chưa có hiệu lực | `notBefore` trong tương lai | Bị từ chối ở TLS/path |
| 5. Intermediate hết hạn | Leaf còn hạn, intermediate hết hạn | PKIX path validation thất bại |
| 6. Root không được trust | Dùng cert từ CA không có trong truststore | Handshake thất bại vì không có trust path |
| 7. Thiếu intermediate | Không gửi đủ chain và validator không có issuer | Path building thất bại |
| 8. Intermediate không có quyền ký | Basic Constraints/Key Usage/pathLen không hợp lệ | Path validation thất bại |
| 9. Sai EKU | Leaf chỉ có serverAuth thay vì clientAuth | Phải bị từ chối bởi TLS validator áp dụng purpose |
| 10. Client private key sai | `--cert` và `--key` không phải một cặp | Handshake/thiết lập credential thất bại |
| 11. Leaf revoked | CRL/OCSP hợp lệ đã đánh dấu serial revoked | TLS/path từ chối khi revocation checking đã bật |
| 12. CRL/OCSP mất kết nối | Chặn truy cập test responder | Từ chối hoặc tiếp tục đúng theo hard/soft-fail policy |
| 13. Revocation response stale | `nextUpdate` đã qua | Không coi là bằng chứng tốt |
| 14. Hostname server sai | Client gọi host không nằm trong SAN server | Client từ chối TLS server certificate |
| 15. User chưa được map | Client cert hợp lệ nhưng thiếu user trong app | TLS thành công, Spring Security từ chối |
| 16. User thiếu authority | Client cert hợp lệ nhưng thiếu `API_READ` | TLS thành công, HTTP 403 |
| 17. Truy cập vòng gateway | Client tự đặt header xác thực vào backend | Phải bị chặn bởi ranh giới tin cậy |
| 18. Xoay CA | CA mới được phân phối, CA cũ được loại theo lịch | Không vô tình tin CA ngoài phạm vi hoặc mất kết nối do truststore chưa đồng bộ |

### Kiểm tra lỗi theo đúng tầng

| Triệu chứng | Kiểm tra trước |
| --- | --- |
| `certificate has expired`, `not yet valid` | `notBefore/notAfter` của leaf và intermediate, UTC và NTP |
| `unable to get local issuer certificate` | Intermediate, trust anchor, chain gửi qua TLS |
| `self-signed certificate in certificate chain` | Root có được truststore của **đúng bên** tin cậy không |
| `unsuitable certificate purpose` | EKU, Key Usage, Basic Constraints |
| `certificate revoked` | CRL/OCSP hợp lệ, issuer/serial, việc bật revocation |
| `unable to get certificate CRL` | Có CRL đúng issuer và còn hạn, đường tải/file CRL |
| `PKIX path building failed` | Truststore và chain, issuer signatures, path constraints |
| TLS handshake thất bại nhưng không có HTTP | Chứng thư, private key, TLS/cipher, truststore, revocation |
| HTTP 403 sau TLS thành công | Principal mapping, user repository và `GrantedAuthority` |
| OpenSSL verify OK nhưng JVM mTLS fail | Trust anchors, thuật toán/trust manager, phiên bản provider và policy khác nhau |

Các cờ JVM chẩn đoán trong môi trường test:

~~~text
-Djavax.net.debug=ssl,handshake,trustmanager
-Djava.security.debug=certpath
~~~

Chỉ bật khi cần; log có thể lớn và chứa thông tin về certificates/principals. Các flag **không bật revocation checking**, mà chỉ giúp quan sát tiến trình validation.

## 10. Lỗi thực tế cần tránh

1. **Đồng nhất thời hạn với trust.** `checkValidity()` có thể thành công dù CA không tin cậy hoặc cert đã revoked.
2. **Tin Subject/Issuer dưới dạng text.** Tên giống nhau không chứng minh chữ ký; cần PKIX path validation.
3. **Đặt root bất kỳ vào truststore.** Việc này mở rộng tập issuer được phép và thay đổi ranh giới tin cậy.
4. **Nhầm `-untrusted` thành “CA xấu”.** Trong OpenSSL, tùy chọn này là nguồn intermediate để xây chain, không phải nơi quyết định trust anchor.
5. **Tưởng CRL/OCSP tự chạy chỉ vì có URI AIA/CRLDP.** Phải bật/configure và có test revoked end-to-end.
6. **Coi OCSP `unknown` là `good`.** Không xác định được trạng thái là một tình huống riêng, có chính sách riêng.
7. **Dùng `curl -k` để test HTTPS.** Bỏ kiểm tra server certificate làm che lỗi hostname/trust.
8. **Chỉ kiểm tra file mà không thử mTLS.** File verify không chứng minh client dùng đúng private key, Spring nhận đúng principal hay được cấp quyền.
9. **Nhầm revocation OCSP stapling phía server với kiểm tra client certificate.** Cần đúng bên thực hiện validation.
10. **Kết luận 403 là chứng thư hết hạn.** Với `client-auth=need`, lỗi hết hạn thường bị chặn trước HTTP.
11. **Bỏ qua kết nối TLS đang tồn tại khi revoke.** Revocation mới không tự đóng mọi kết nối phiên cũ.
12. **Tin header client certificate do client gửi.** Khi có proxy, chỉ tin danh tính qua ranh giới được bảo vệ và xác minh.

## 11. Vận hành certificate lifecycle

Một chương trình vận hành mTLS ổn định nên có:

- **Theo dõi và cảnh báo hạn** cho leaf, intermediate và CA quan trọng; lập cảnh báo trước các mốc (ví dụ 30/14/7 ngày) phù hợp SLA.
- **Gia hạn và thay khóa** trước hạn; sau khi thay phải kiểm tra SAN, EKU, private key, chain và luồng chứng thực thực tế.
- **Giám sát revocation infrastructure:** OCSP/CRL availability, độ mới CRL, response errors, hard-fail rate, log an toàn.
- **Kịch bản lộ private key:** revoke, cấp lại, làm mới trust/policy, chặn tài khoản hoặc phiên khi cần; không chờ đến `notAfter`.
- **Kế hoạch xoay CA:** thời gian overlap truststore có kiểm soát, phân phối lên các node, kiểm tra client/server trước khi gỡ CA cũ.
- **Chính sách cache/connection/session:** khi quyền ứng dụng bị thu hồi hoặc cert revoked, xác định TTL, thời gian áp dụng và cách invalidation.
- **Kiểm thử định kỳ:** dùng fixture good, expired, revoked, unknown issuer và responder outage trong môi trường tương đồng production.

## 12. Câu hỏi tự kiểm tra

1. Vì sao một chứng thư còn hạn và có chữ ký đúng vẫn có thể bị từ chối?
2. `TrustAnchor` khác `intermediate CA` ở điểm nào? Vì sao không tự tin mọi CA được gửi qua TLS?
3. Vì sao `checkValidity()` không chứng minh certificate có quyền xác thực?
4. Khi CRL chứa serial của chứng thư vẫn còn hạn, validator cần làm gì?
5. OCSP `unknown` có phải là `good` không? Chính sách hard-fail có tác động gì khi responder timeout?
6. Khác biệt giữa `-CAfile` và `-untrusted` trong `openssl verify` là gì?
7. Phân biệt lỗi mTLS handshake do expiry với HTTP 403 do thiếu `API_READ`.
8. `server.ssl.client-auth=need` và `http.x509(...)` thuộc hai tầng xác thực nào?
9. Vì sao test revocation phải dùng chứng thư chưa hết hạn và chain còn tốt?
10. Nếu gateway terminate TLS client certificate, thành phần nào có trách nhiệm xác minh CRL/OCSP?

**Đáp án gợi ý:** (1) root chưa trust, sai purpose/identity, revoked hoặc sai chain; (2) trust anchor do verifier cấu hình còn intermediate chỉ là mắt xích ký số; (3) phương thức chỉ kiểm tra mốc thời gian; (4) từ chối nếu revocation policy áp dụng; (5) không, hard-fail từ chối khi không đủ bằng chứng; (6) CA được tin cậy và intermediate cung cấp để xây chain; (7) trước HTTP so với đã có request HTTP nhưng thiếu quyền; (8) TLS validation so với mapping principal/authority; (9) tránh nguyên nhân thất bại bị che; (10) gateway, còn ứng dụng bảo vệ danh tính/ủy quyền sau gateway.

## 13. Checklist nghiệm thu

- [ ] Có test valid, expired, not-yet-valid, revoked, unknown issuer, missing intermediate và wrong EKU.
- [ ] Đã kiểm tra toàn bộ chain đến đúng root trong truststore, không mở rộng CA vô tội vạ.
- [ ] Đã xác minh thời gian UTC/NTP và expiry của cả leaf/intermediate.
- [ ] Đã xác minh revocation checking **thật sự được kích hoạt** ở TLS termination bằng test revoked end-to-end.
- [ ] Đã có hard/soft-fail policy, test responder outage, stale/unknown response và chữ ký CRL/OCSP.
- [ ] Client kiểm tra server CA + hostname; server kiểm tra client CA + purpose + principal.
- [ ] Quyền ứng dụng được nạp sau mTLS và HTTP 403 được phân biệt với lỗi TLS.
- [ ] Truststore/keystore, private key và secret được quản lý theo nguyên tắc quyền tối thiểu.
- [ ] Có lịch gia hạn, cảnh báo expiry, kế hoạch CA rotation và xử lý revoke khẩn cấp.
- [ ] Reverse proxy nếu có phải bảo vệ danh tính đã xác minh, không nhận header giả từ client.

## 14. Tài liệu tham khảo

- [Spring Security 6.5 — X.509 Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/x509.html)
- [Spring Security — X509Configurer API](https://docs.spring.io/spring-security/site/docs/6.5.0-M1/api/org/springframework/security/config/annotation/web/configurers/X509Configurer.html)
- [Spring Boot 3.3 — SSL](https://docs.spring.io/spring-boot/3.3/reference/features/ssl.html)
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/)
- [Oracle Java 21 — PKIXRevocationChecker.Option](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXRevocationChecker.Option.html)
- [Oracle — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
- [OpenSSL — verification options](https://docs.openssl.org/3.0/man1/openssl-verification-options/)
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280)
- [RFC 6960 — Online Certificate Status Protocol](https://www.rfc-editor.org/rfc/rfc6960)
