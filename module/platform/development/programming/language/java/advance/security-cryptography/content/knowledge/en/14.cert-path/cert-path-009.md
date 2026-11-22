# 14.9. Giới hạn của PKIX: kiểm tra danh tính máy chủ là một bước riêng

## 1. Bài toán: chứng thư có CA tin cậy chưa chắc thuộc đúng server

Giả sử một ứng dụng Java định gọi API tại `https://billing.example.test`. Trên đường truyền, máy chủ trình ra một chứng thư X.509:

- Do một CA hợp lệ, nằm trong tập trust anchors mà client đã cấu hình, ký.
- Chưa hết hạn, đường dẫn chứng thư và chữ ký đều có thể được kiểm tra thành công theo PKIX.
- Nhưng **Subject Alternative Name (SAN)** của chứng thư chỉ chứa `DNS:service.example.test`, **không** chứa `billing.example.test`.

Nếu lập trình viên chỉ gọi `CertPathValidator.getInstance("PKIX").validate(...)` rồi kết luận “đúng server”, ứng dụng có thể bị kết nối đến **sai danh tính**. Đây là lỗi ghép hai bài toán khác nhau thành một:

1. **Path validation (PKIX):** chuỗi chứng thư có xây dựng được một đường tin cậy hợp lệ đến một trust anchor được chấp nhận, thỏa các ràng buộc và chính sách PKIX hay không?
2. **Endpoint identification / hostname verification:** chứng thư được chấp nhận đó có **ràng buộc với tên DNS hoặc địa chỉ IP mà ứng dụng thực sự dự định kết nối** hay không?

**Kết luận cốt lõi:** `PKIX path valid = true` **không kéo theo** `hostname matches = true`. Một kết nối TLS đúng phải thỏa **cả hai điều kiện** theo giao thức, đồng thời bắt tay TLS chứng minh server dùng được private key tương ứng với chứng thư được chấp nhận.

### Mục tiêu học tập

Sau bài này, bạn sẽ biết:

- Phân biệt `CertPathBuilder`, `CertPathValidator`, `PKIXParameters`, `TrustAnchor` với bước xác minh tên máy chủ.
- Hiểu vì sao đường tin cậy hợp lệ vẫn có thể bị dùng cho **sai hostname**.
- Nhận diện SAN `dNSName` (type 2), `iPAddress` (type 7), wildcard và giới hạn của `Common Name (CN)`.
- Viết ví dụ Java 17+ **thực sự xác minh PKIX chain** nhưng chỉ có SAN của một hostname khác, rồi thấy giới hạn của kết quả.
- Cấu hình `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` khi sử dụng JSSE trực tiếp, và không vô hiệu hóa hostname/trust verification.
- Xây test matrix có đủ **đường tin cậy đúng/sai** và **danh tính đúng/sai**, phân biệt lỗi issuer với name mismatch.

## 2. Hai câu hỏi khác nhau trong xác thực TLS

### 2.1. PKIX xác minh đường tin cậy là gì?

**PKIX** (*Public Key Infrastructure using X.509*) là tập tiêu chuẩn dùng để xây dựng và xác minh chứng thư. Đối với một chuỗi chứng thư server thường gặp:

```text
Trust anchor / Root CA được client tin từ trước
           |
           | ký hoặc ủy quyền theo cấu trúc CA
           v
Intermediate CA (có thể không có)
           |
           | ký leaf certificate
           v
Server leaf certificate
           |
           +-- Subject Public Key
           +-- Subject Alternative Name (SAN)
           +-- KeyUsage / ExtendedKeyUsage
           +-- Validity / signature algorithm / extensions
```

Một quá trình **PKIX path validation** với chính sách phù hợp có thể xét các khía cạnh như:

- Chữ ký từng chứng thư và mối quan hệ issuer/subject trong đường dẫn.
- Đường dẫn kết thúc tại **trust anchor mà ứng dụng chủ động tin**, không phải một CA ngẫu nhiên bất kỳ.
- Hiệu lực thời gian (`notBefore`/`notAfter`) theo thời điểm kiểm tra.
- `BasicConstraints`, độ sâu CA, `KeyUsage` cho chức năng chứng thực của CA.
- Các ràng buộc tên (`NameConstraints`), certificate policies, thuật toán/độ mạnh khóa theo cấu hình và provider.
- Tình trạng thu hồi (CRL/OCSP) nếu đã cấu hình đúng và cơ chế kiểm tra tương ứng được kích hoạt.

**Không có một tập bảo đảm duy nhất cho mọi lần gọi `validate`:** kết quả phụ thuộc trust anchors, PKIX parameters, cert stores, chính sách thu hồi, thời gian, implementation/provider và ngữ cảnh ứng dụng. Trong Java, cấu hình mà bạn chọn là một phần của yêu cầu bảo mật.

### 2.2. Endpoint identification kiểm tra điều gì?

Khi ứng dụng **muốn** kết nối `billing.example.test`, client phải xác minh certificate chứa **reference identity** phù hợp với tên đó. Thông thường HTTPS sử dụng:

- **DNS-ID:** `subjectAltName` dạng `dNSName` cho hostname DNS.
- **IP-ID:** `subjectAltName` dạng `iPAddress` cho địa chỉ IP literal.
- Các quy tắc về wildcard/IDNA/so khớp được profile giao thức quy định.

**Tên mong đợi phải đến từ phía ứng dụng/giao thức đáng tin**, ví dụ hostname trong URI mà client đã chọn hoặc danh tính peer đã cấu hình. Không lấy tên mong đợi từ chứng thư vừa nhận rồi kiểm tra chứng thư ấy “có chứa tên đó” — phép kiểm sẽ trở thành vòng lặp tự xác nhận và không bảo vệ đích mà người dùng muốn gọi.

### 2.3. Điều kiện kết nối an toàn

```text
Khởi tạo kết nối tới hostname H do client tin
                    |
                    v
Nhận certificate chain của TLS peer
                    |
                    v
[1] Validate PKIX path đến trust anchor được phép?
       | không --> FAIL: không tin đường chứng thư
       | có
       v
[2] Xác minh endpoint identity H khớp SAN đúng kiểu?
       | không --> FAIL: sai server identity
       | có
       v
[3] TLS handshake/chính sách/algorithm/key proof thành công?
       | không --> FAIL
       | có
       v
Chỉ lúc này mới chấp nhận kênh TLS theo chính sách
và tiếp tục kiểm tra authorization nghiệp vụ.
```

Sơ đồ mô tả **các điều kiện logic**, không áp đặt thứ tự gọi nội bộ của tất cả TLS providers. JSSE có thể phối hợp kiểm tra path, endpoint và các tham số handshake trong cùng một quá trình. Không nên tự chia thao tác thành ba bước bằng tay nếu API TLS cấp cao đã kiểm tra chúng an toàn.

## 3. Vì sao một certificate hợp lệ lại có thể thuộc sai host?

Ví dụ ba dịch vụ:

```text
api.example.test
billing.example.test
files.example.test
```

Một CA có thể cấp **ba chứng thư đều hợp lệ** cho ba dịch vụ này. Việc client tin CA không có nghĩa mọi chứng thư CA đó cấp đều đại diện cho **mọi tên**.

Tình huống lỗi:

1. Java client kết nối `billing.example.test`.
2. Attacker có chứng thư hợp lệ cho `api.example.test` từ một CA mà client cũng tin hoặc có thể can thiệp định tuyến/địa chỉ peer.
3. Client chỉ xác thực chain: chữ ký hợp lệ, anchor được tin, validity và ràng buộc PKIX đều đạt.
4. Client **bỏ qua hostname verification** nên chấp nhận chứng thư có `DNS:api.example.test` như thể nó dùng được cho `billing.example.test`.

Ngay cả khi attacker **không thể tạo certificate giả cho billing**, họ vẫn có thể lạm dụng một certificate thật của **tên khác** nếu ứng dụng chỉ kiểm chain. Với hostname verification, client phải từ chối vì danh tính mục tiêu không khớp SAN.

**Không chỉ là vấn đề “CA giả”:** việc kiểm CA *đúng* vẫn chưa đủ nếu bạn không kiểm tên. Và việc tự pin một public key cũng phải có policy ràng buộc key với đúng endpoint và scope, không biến bất kỳ key đã pin nào thành danh tính chung cho mọi dịch vụ.

## 4. PKIX trong Java: API nào có và không có chức năng gì?

| API | Chức năng | Không thể suy ra chỉ từ lời gọi này |
| --- | --- | --- |
| `CertificateFactory.getInstance("X.509")` | Parse DER/PEM, tạo `X509Certificate` hoặc `CertPath` | Chưa xác minh trust chain hoặc hostname. |
| `X509Certificate.checkValidity()` | Kiểm tra ngày hiệu lực của đúng certificate | Không xác minh issuer, policy hoặc server identity. |
| `X509Certificate.verify(PublicKey)` | Kiểm chữ ký certificate bằng key đã cung cấp | Không tự chứng minh key đưa vào được tin, không kiểm hostname. |
| `X509Certificate.getSubjectAlternativeNames()` | Đọc danh sách GeneralName ở SAN extension | Chỉ là **getter**, không phải hostname verifier. |
| `CertPathBuilder.getInstance("PKIX")` | Tìm đường chứng thư đáp ứng tham số/target selector và trust policy | Không mặc nhiên lấy hostname URL cần bảo vệ. |
| `CertPathValidator.getInstance("PKIX")` | Xác minh đường `CertPath` cụ thể theo tham số PKIX | Không mặc nhiên so hostname/IP của kết nối TLS với SAN. |
| `PKIXParameters` / `PKIXBuilderParameters` | Cấu hình trust anchors, date, policy, revocation, cert stores, v.v. | Không có cơ chế mặc định “đây là URL billing của tôi” trong `validate`. |
| `TrustAnchor` | Biểu diễn root/CA tin cậy mà policy đã cho phép | Không tự xác minh rằng anchor do bên đáng tin cấp phát. |
| `X509ExtendedTrustManager` + JSSE endpoint algorithm | Trong TLS handshake có đủ ngữ cảnh, có thể phối hợp trust và endpoint identification | Không an toàn nếu trust manager tự viết luôn cho qua, hoặc không bật endpoint identification khi cần. |
| `HttpClient` / `HttpsURLConnection` (HTTPS) | Client TLS cấp cao với xác minh certificate/hostname theo cấu hình an toàn | Mất bảo đảm nếu custom SSL/trust/hostname configuration bỏ qua kiểm tra. |

**Điểm phân biệt giữa CertPathBuilder và CertPathValidator:** `Builder` tìm đường phù hợp từ những certificates/`CertStore` có sẵn; `Validator` kiểm **đường cụ thể** đã được cung cấp. Dù tự build hay validate, kết quả “đường hợp lệ” không tự biến thành “đúng DNS host”.

### 4.1. Trust anchor là một quyết định bảo mật

Trong ví dụ Java, chương trình sẽ tạo `new TrustAnchor(demoRootCertificate, null)`. Nghĩa là **chính chương trình tuyên bố** root đó là một anchor tin cậy. PKIX validator đánh giá chain dưới điều kiện đã cho; nó **không** xác minh bằng phép màu vì sao chương trình lại chọn root này.

Trong production, trust anchors đến từ truststore/PKI policy được quản trị: JDK/system CA store, một truststore nội bộ được provision an toàn hoặc cơ chế xác thực/pinning được duyệt. Nếu attacker có quyền thêm root CA của mình vào truststore, đường dẫn đến root đó có thể hợp lệ và phá vỡ giả định tin cậy. **Quản lý truststore** là một phần của mô hình an ninh.

### 4.2. PKIX thu hồi chứng thư không có nghĩa lúc nào cũng bật sẵn

Trong Java, `PKIXParameters` có tùy chọn `setRevocationEnabled(boolean)`. Một bài lab offline có thể vô hiệu hóa revocation vì không cung cấp CRL/OCSP và không có PKI thật; cách đó **không phải** policy phù hợp cho mọi ứng dụng production.

Khi deploy, cần quyết định rõ chế độ CRL/OCSP, nguồn trả lời, thời hạn cache, xử lý lỗi mạng, yêu cầu must-staple/nội bộ nếu áp dụng, và fail-open/fail-closed theo chính sách. Không khái quát rằng một lần `CertPathValidator.validate` thành công chắc chắn đã tra đầy đủ mọi trạng thái thu hồi trong thực tế.

### 4.3. PKIX path validation và TLS usage constraints

Generic `CertPathValidator` không biết **tất cả ngữ cảnh giao thức TLS**: hostname đang kết nối, SNI, có dùng serverAuth hay clientAuth, TLS version, handshake purpose, authType, application authorization. JSSE trust manager theo ngữ cảnh có thể áp dụng additional checks như extended key usage, thuật toán và danh tính endpoint.

Ví dụ chứng thư ký code hoặc client certificate có chain hợp lệ không tự động trở thành server certificate phù hợp cho mọi hostname. Phải kết hợp đúng **KeyUsage/EKU**, giao thức và identity verification.

## 5. Endpoint identity: DNS SAN và IP SAN là hai kiểu khác nhau

### 5.1. DNS hostname → dNSName (type 2)

Với URI `https://billing.example.test`, tên tham chiếu bình thường là `billing.example.test`, so với SAN `dNSName` của chứng thư server.

Ví dụ chứng thư chứa `DNS:service.example.test`. Chứng thư này **không** hợp lệ cho `billing.example.test` chỉ vì cùng suffix `example.test`. Một dNSName chính xác hoặc wildcard hợp lệ theo tiêu chuẩn phải khớp.

Các so sánh DNS-ID cần tuân thủ profile: tên DNS không phân biệt chữ hoa/chữ thường theo quy tắc, dạng IDN/IDNA ASCII A-label, các giới hạn wildcard; **không tự viết regex tùy tiện** để thay verifier của TLS stack.

### 5.2. IP literal → iPAddress (type 7)

Với `https://192.0.2.10` hoặc `https://[2001:db8::10]`, reference identity là IP address. Certificate cần SAN `iPAddress` có giá trị nhị phân tương ứng (4 octet cho IPv4, 16 octet cho IPv6). Dùng `DNS:192.0.2.10` không tự trở thành `IP Address:192.0.2.10`.

Không lấy kết quả reverse DNS để đổi yêu cầu kiểm IP-ID thành DNS-ID. Hai địa chỉ IPv6 có biểu diễn text khác nhau nhưng cùng 16 octet phải được hiểu theo giá trị IP; so text thuần có thể sai.

### 5.3. Common Name (CN) không thay cho SAN

Trước đây một số TLS clients có thể dùng `Subject CN` làm fallback nếu chứng thư thiếu dNSName. **RFC 9525**, thay thế RFC 6125, quy định không dùng Common Name RDN làm danh tính dịch vụ. Với thiết kế mới: cấp chứng thư có SAN phù hợp và không dựa vào fallback CN.

Một `Subject: CN=billing.example.test` **không nên** được xem là lý do cho qua khi SAN chỉ chứa `DNS:service.example.test`. Một certificate có CN đúng và SAN sai vẫn không bảo vệ danh tính cần thiết.

### 5.4. Wildcard không được tự mở rộng vô hạn

Theo profile DNS-ID, wildcard hợp lệ được giới hạn (ví dụ nguyên nhãn bên trái `*.example.test`), thông thường chỉ khớp **một nhãn**. Nó không khớp `example.test` và không khớp `a.b.example.test`. Một số hệ thống còn có chính sách hạn chế wildcard nghiêm ngặt hơn; phải theo RFC 9525 và profile đang áp dụng.

Không dùng `endsWith(".example.test")` hoặc `replace("*",".*")` để tự xác minh host. Một lỗi xử lý label, dấu chấm, Unicode/IDNA hoặc wildcard có thể tạo ra lỗ hổng xác thực endpoint.

## 6. Demo Java 17+: PKIX chain hợp lệ nhưng hostname cần kiểm tra riêng

### 6.1. Mục tiêu và ranh giới của demo

Chương trình sử dụng **hai chứng thư X.509 thử nghiệm công khai**:

- **Demo Root CA:** self-signed, với CA BasicConstraints và KeyUsage phù hợp, được chương trình chọn làm trust anchor chỉ cho bài học.
- **Leaf certificate:** được Demo Root CA ký, có SAN `DNS:service.example.test`; phần `Subject CN` là `legacy.example.test`.

Java `CertPathValidator` sẽ xác minh một đường có **leaf certificate** dẫn đến **root CA** đã được chương trình tin. Kết quả thành công **không** chứa hoặc nhận tham số `billing.example.test`; vì vậy nó không thể trả lời trực tiếp liệu hostname đó có đúng không.

Sau đó chương trình đọc SAN để **minh họa** rằng tên `service.example.test` có trong certificate, nhưng `billing.example.test` thì không. Phép tìm phần tử `List.contains` trong demo chỉ dùng vì test certificate chứa **một DNS-ID chính xác, không có wildcard hoặc IDN**. **Nó không phải hàm xác minh HTTPS hostname tổng quát.** Trong ứng dụng thật, để JSSE kiểm tra endpoint theo thuật toán `HTTPS` và PKIX trust manager thích hợp.

Certificate fixture được tạo cho mục đích học tập, chỉ có **public certificates**, **không nhúng private key**. Nó có hiệu lực dự kiến từ **31/10/2026 đến 28/10/2036** theo thời gian ghi trong certificate. Sau thời hạn đó, ví dụ PKIX **cần certificate mới**, không được tắt kiểm tra thời gian để ép pass.

Chương trình **không mở kết nối mạng** và không làm TLS handshake; nó minh họa sự khác nhau giữa hai câu hỏi ở lớp certificate.

### 6.2. Mã hoàn chỉnh PkixHostnameDemo.java

```java
import java.io.ByteArrayInputStream;
import java.nio.charset.StandardCharsets;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public final class PkixHostnameDemo {
    // Public test certificates. Never add this demo CA to a production truststore.
    private static final String CA_PEM = """
            -----BEGIN CERTIFICATE-----
            MIIDMDCCAhigAwIBAgIIdN8VOPntrL4wDQYJKoZIhvcNAQEMBQAwNjELMAkGA1UE
            BhMCVVMxEDAOBgNVBAoTB0V4YW1wbGUxFTATBgNVBAMTDERlbW8gUm9vdCBDQTAe
            Fw0yNjEwMzExMzI4NThaFw0zNjEwMjgxMzI4NThaMDYxCzAJBgNVBAYTAlVTMRAw
            DgYDVQQKEwdFeGFtcGxlMRUwEwYDVQQDEwxEZW1vIFJvb3QgQ0EwggEiMA0GCSqG
            SIb3DQEBAQUAA4IBDwAwggEKAoIBAQDVz/2xjKXNgom5vKohD6AGorxwLk3S/GZo
            KVU900y+GZG18aBjMbUIJAPZIRSykF3QCO5OfGJqHa3aqo6mctBknES2h3wGRw15
            MFjmDenGHl5HqjouG2iXAff9gKbencmgigDHKc5IWHLXx0N00TH0LWF9bf+b71Q1
            5MP8gZ3ad5v9PTNRhBGjli7ywoK68qTGhdSPUarHEYk0Ii5OW4mTtsfYlNZpsU15
            Unxz6ViASsaO96cAt/BD6gZQ7UtFhiwZc5p7B0lQiLFzv+B4YV1bRl3fN6FyV5u4
            gdol+uCSfl1g57bgYqb6JVsSb5pxchAoYLYBYqN7hNMEUwfmOLhZAgMBAAGjQjBA
            MB0GA1UdDgQWBBR8adDvW8CFs/qJKxm38W243usibTAOBgNVHQ8BAf8EBAMCAQYw
            DwYDVR0TAQH/BAUwAwEB/zANBgkqhkiG9w0BAQwFAAOCAQEAg4pxYY0c11RBf+CD
            y1bWEUQzGCKaa5zVkutxoaYSSuDhZEOnxn7+buY/EkMfAEWfttm32jI8HfvVvP5p
            dmF/PqUchpk/GwshauAWuCeWRc490aMudGB5LWgciFtK3L6opSsZYNUI47JJTAY9
            P79ybEgwUDjKm1po7h5o1aJYVzqWW9/8QgLXlb2dpz9gGYum45LpSEa17qEoAwG9
            2ADlnOcLc5OUNjt9Qv5arLzD/lUxkqc97xo4/ziKu/JUczn5qK+PPHuOcIZE39KB
            J6Xfg7dmD26RR0muKcGT80gjFzrdsPjYap6fhKfHRCiGfyhYXmEV3xBsx7a3qFcO
            T5ktkg==
            -----END CERTIFICATE-----
            """;

    private static final String SERVER_PEM = """
            -----BEGIN CERTIFICATE-----
            MIIDgDCCAmigAwIBAgIJALbt87m4xELfMA0GCSqGSIb3DQEBDAUAMDYxCzAJBgNV
            BAYTAlVTMRAwDgYDVQQKEwdFeGFtcGxlMRUwEwYDVQQDEwxEZW1vIFJvb3QgQ0Ew
            HhcNMjYxMDMxMTMyOTAwWhcNMzYxMDI4MTMyOTAwWjA9MQswCQYDVQQGEwJVUzEQ
            MA4GA1UEChMHRXhhbXBsZTEcMBoGA1UEAxMTbGVnYWN5LmV4YW1wbGUudGVzdDCC
            ASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEBANhgczqgksY3gGlhNUrb619R
            vR9PuIPa7c1wDdju1jGUlBv86XfjLXNzuVL92YdBI7OGzXcrUlYYdaieyXtNdM4c
            N6hBIFhWHaNxq5O98ljKHeCXSgAixz0FyvCG8odzwjbW8VFXfVlqXT839tZMhcpm
            gayLXW6p5GmGnujV/q1TZxXp4IDqsYLDTD0YSaghm/hFRF9wlNW1eoPS7EKemACV
            i75iY9w9ImdjjPtxr36/1nWKGMhksIzNMw/ClygruwaVb+ROERx8EM8UcMcJg4jn
            w+uhYUQ7uTEM2N+i3BzERt29R6pSHDWc8zuVyB+766YkjK52D7zUnQoPOfNN1rMC
            AwEAAaOBiTCBhjAdBgNVHQ4EFgQU3FgVZYXNv6Ofpywezmb/kZpFWywwDgYDVR0P
            AQH/BAQDAgWgMB8GA1UdEQQYMBaCFHNlcnZpY2UuZXhhbXBsZS50ZXN0MB8GA1Ud
            IwQYMBaAFHxp0O9bwIWz+okrGbfxbbje6yJtMBMGA1UdJQQMMAoGCCsGAQUFBwMB
            MA0GCSqGSIb3DQEBDAUAA4IBAQBOEY35M1IhiI/F4codM6kCBQcjCM3QpB8D1nvL
            nVB4HXZENtIRnDhXVDCzzo3Xko+/SuMiobli5+j4iKDncy/wrwbnhJr/koPGN5jP
            GnpNmwBNw9m4OSH7xjgFdbfH4S0DrNYv/NsvH1dJchdzSVm3ZVFLNDb0Ao/LB7ib
            Gs72BDXNiYxLrByryRDCVdoI6KNqL57Ll7ep2yRs2LGLNvP787rWH1frObGUz4KR
            wR+l0T8A93nPteXO0/P/8K30QdJ9Eyb5bftnBqWDO+aSlDnk2mhSAZ0Trroj68uQ
            Y3IYs9CG3VKGCvopFX+mrgBvVP28BIlyNevP3glqiyO9t1f1
            -----END CERTIFICATE-----
            """;

    private static X509Certificate certificate(CertificateFactory factory, String pem)
            throws Exception {
        return (X509Certificate) factory.generateCertificate(
                new ByteArrayInputStream(pem.getBytes(StandardCharsets.US_ASCII)));
    }

    public static void main(String[] args) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        X509Certificate root = certificate(factory, CA_PEM);
        X509Certificate server = certificate(factory, SERVER_PEM);

        CertPath path = factory.generateCertPath(List.of(server));
        PKIXParameters policy = new PKIXParameters(Set.of(new TrustAnchor(root, null)));
        policy.setRevocationEnabled(false); // Test fixture only; not a production policy.
        PKIXCertPathValidatorResult result = (PKIXCertPathValidatorResult)
                CertPathValidator.getInstance("PKIX").validate(path, policy);
        System.out.println("PKIX path valid: " + (result.getTrustAnchor() != null));

        List<String> dnsNames = new ArrayList<>();
        Collection<List<?>> sans = server.getSubjectAlternativeNames();
        if (sans != null) {
            for (List<?> name : sans) {
                if (((Integer) name.get(0)) == 2 && name.get(1) instanceof String dns) {
                    dnsNames.add(dns);
                }
            }
        }

        System.out.println("DNS SANs: " + dnsNames);
        System.out.println("Intended service DNS listed: " +
                dnsNames.contains("service.example.test"));
        System.out.println("Different target DNS listed: " +
                dnsNames.contains("billing.example.test"));
        System.out.println("Legacy CN in DNS SAN: " +
                dnsNames.contains("legacy.example.test"));
    }
}
```

### 6.3. Biên dịch, chạy và stdout

Dùng Java 17 trở lên, không cần kết nối mạng hay file khóa riêng:

```bash
javac PkixHostnameDemo.java
java PkixHostnameDemo
```

Stdout đã kiểm thử trên JDK có hỗ trợ PKIX thông thường, trong thời hạn hiệu lực certificate fixture:

```text
PKIX path valid: true
DNS SANs: [service.example.test]
Intended service DNS listed: true
Different target DNS listed: false
Legacy CN in DNS SAN: false
```

**Đọc kết quả đúng cách:**

1. `PKIX path valid: true` cho thấy `CertPathValidator` đã kiểm tra **leaf do demo CA ký** theo trust anchor/chính sách đã chỉ định, không phải chỉ so fingerprint hoặc parse PEM.
2. `DNS SANs` chứa `service.example.test` là dữ liệu **được đọc** từ leaf certificate. Chưa thực hiện hostname matching theo RFC 9525/JSSE trong demo này.
3. `Different target DNS listed: false` minh họa hostname `billing.example.test` **không được chứng thư đại diện**. Điều này **không làm** cho `CertPathValidator.validate` ném exception, bởi vì không có tên `billing.example.test` nào được đưa vào yêu cầu path validation.
4. `Legacy CN in DNS SAN: false` là do CN được đặt khác DNS SAN. Không được dùng CN để “cứu” một name mismatch trong chính sách hiện đại.
5. Việc `setRevocationEnabled(false)` chỉ được dùng cho **fixture offline**. Từ ví dụ không được suy ra production có thể bỏ kiểm tra thu hồi hoặc rằng demo root là một public trusted root.
6. Tập PEM gồm **root và leaf public certificates**; nếu người dùng chỉ thay `SERVER_PEM` bằng một leaf không được root này ký, PKIX sẽ thất bại trừ khi có đường tin cậy hợp lệ khác được cấu hình. Thay nội dung SAN không thể làm một certificate ký sẵn vẫn có chữ ký hợp lệ.

**Điều demo không làm:** chưa có TLS network handshake, chưa có kiểm proof-of-possession từ remote server, chưa có kiểm tên bằng hostname verifier của JSSE, chưa kiểm TLS server usage profile/authorization và không chứng minh một máy chủ thực tế đang hiện diện. Đây là bài kiểm tra **ranh giới của PKIX**, không phải ví dụ khuyến khích tự kiểm tra SAN với `contains` trong production.

## 7. Cách làm đúng trong Java TLS: đưa endpoint identity vào handshake

### 7.1. Dùng HttpClient/HTTPS API cấp cao trước

Trong Java, khi dùng `java.net.http.HttpClient` với URL HTTPS, cấu hình mặc định phù hợp của client thực hiện kiểm tra TLS và danh tính máy chủ. Với ứng dụng mới, ưu tiên client cấp cao có truststore chuẩn, chính sách TLS được quản lý, không thay bằng `SSLContext` tùy tiện tin mọi chứng thư.

Đoạn mã dưới đây **chỉ minh họa cấu hình client**; hostname `.test` là ví dụ tài liệu, không có giả định tồn tại server Internet:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

HttpClient client = HttpClient.newHttpClient();
HttpRequest request = HttpRequest.newBuilder(
        URI.create("https://billing.example.test/orders")).GET().build();
HttpResponse<String> response =
        client.send(request, HttpResponse.BodyHandlers.ofString());
```

Đây **không phải chương trình Java độc lập**, chỉ là đoạn mã đặt trong một phương thức có thể ném `Exception`. `HttpClient` vẫn cần DNS/network hợp lệ và server certificate được PKIX + endpoint verification chấp nhận. Chương trình `PkixHostnameDemo` ở trên không kết nối host này.

**Không** chỉnh hệ thống để tắt hostname verification khi gặp mismatch, không thay trust manager bằng “accept-all”, không dùng custom `SSLContext` hoặc property nội bộ vô hiệu hóa kiểm tra tên để làm test pass.

### 7.2. Với SSLSocket, bật endpoint identification

API `SSLSocket` cấp thấp đòi hỏi lập trình viên kiểm soát cấu hình xác minh tên. Một cách được JDK hỗ trợ là `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`:

```java
import javax.net.ssl.SSLParameters;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

SSLSocketFactory factory = (SSLSocketFactory) SSLSocketFactory.getDefault();
try (SSLSocket socket =
        (SSLSocket) factory.createSocket("billing.example.test", 443)) {
    SSLParameters parameters = socket.getSSLParameters();
    parameters.setEndpointIdentificationAlgorithm("HTTPS");
    socket.setSSLParameters(parameters);
    socket.startHandshake();
    // Chỉ xử lý dữ liệu nếu TLS handshake và endpoint verification thành công.
}
```

Đây là **snippet minh họa**, không phải một class độc lập. Host `billing.example.test` là tài liệu, không phải server có thật. Với SSL/TLS triển khai thực tế, phải dùng trust manager có **PKIX trust validation** đúng; một trust manager luôn chấp nhận certificate hoặc các cấu hình vô hiệu hóa check có thể làm suy yếu/triệt tiêu bảo đảm, ngay cả khi đã chỉ định endpoint algorithm.

Đặt `"HTTPS"` là yêu cầu áp dụng cơ chế tên theo kiểu HTTPS trong JSSE. Không đặt thuật toán `null` hoặc `""` chỉ để đi qua lỗi tên. Nếu chứng thư có SAN sai, sửa hostname đích hoặc phát hành lại certificate có SAN đúng, không “tạm cho qua”.

### 7.3. SSLEngine, X509ExtendedTrustManager và ngữ cảnh TLS

Ở mức `SSLEngine`, cần cung cấp **peerHost** có ý nghĩa khi tạo engine và bật endpoint identification trên `SSLParameters`, đồng thời cấu hình trust manager đúng và thực hiện handshake qua transport với trạng thái SSL đầy đủ.

Một `X509ExtendedTrustManager` có phương thức `checkServerTrusted(chain, authType, SSLEngine)` và phiên bản nhận `Socket` để dùng **ngữ cảnh TLS** (khi được dùng đúng trong handshake). Điều này khác với việc gọi `X509TrustManager.checkServerTrusted(chain, "RSA")` trực tiếp ở code nghiệp vụ mà không truyền host/context: một lời gọi chỉ có `chain` và `authType` **không** tự biết URL được yêu cầu là gì.

**Sai lầm:** tự tạo `X509TrustManager` luôn chấp nhận mọi chain rồi dùng `HttpsURLConnection.setDefaultHostnameVerifier((host,session) -> true)`. Khi đó cả trust và danh tính có thể bị bỏ qua, mở đường MITM.

### 7.4. SNI không thay endpoint verification

**Server Name Indication (SNI)** là extension trong TLS ClientHello giúp server biết client muốn virtual host nào để chọn certificate phù hợp. SNI **không** thay thế bước client xác minh rằng certificate thực nhận có đúng SAN và trust chain.

Không sử dụng SNI do kẻ khác điều khiển như một nguồn danh tính thay cho URI đáng tin. Với reverse proxy, load balancer hoặc kết nối socket trực tiếp tới IP nhưng danh tính dịch vụ là DNS, cần cấu hình TLS peer host/reference identity sao cho **không đánh mất** tên DNS mà client thực sự muốn xác thực.

## 8. Khi truy cập bằng IP hoặc hệ thống có nhiều hostname

### 8.1. DNS đến IP không làm biến đổi reference identity

Nếu `billing.example.test` được DNS resolve thành `192.0.2.10`, nhưng client vẫn gọi URL theo hostname, danh tính để xác minh là `billing.example.test`, không phải số IP được resolver trả về. Bản ghi DNS có thể đổi IP theo thời gian mà certificate có SAN DNS vẫn đúng.

Nếu ứng dụng chủ động dùng `https://192.0.2.10` thì client kỳ vọng `iPAddress` SAN cho IP literal. Tên `DNS:billing.example.test` **không tự khớp** với một reference identity dạng IP. Bản ghi iPAddress dùng octet (IPv4 4, IPv6 16), không phải chuỗi text DNS.

### 8.2. Wildcard SAN và nhiều tên

Chứng thư có thể có nhiều `dNSName`:

```text
DNS:billing.example.test
DNS:reports.example.test
DNS:*.svc.example.test
IP Address:192.0.2.10
```

Chỉ tên nào khớp với **reference identity được yêu cầu** theo profile giao thức mới được chấp nhận. Wildcard `*.svc.example.test` không tự khớp `svc.example.test` hoặc `a.b.svc.example.test`. Một certificate chứa nhiều tên hợp lệ có thể được dùng cho nhiều endpoints, nhưng **private key leak** làm tăng phạm vi ảnh hưởng; cần quản lý provisioning, quyền phát hành và rotation.

### 8.3. Internationalized Domain Names (IDN)

Domain quốc tế hóa có Unicode ở giao diện người dùng, nhưng dữ liệu `dNSName` trong X.509 theo profile chứa ASCII IA5String (IDNA A-label như `xn--...` khi cần). Đảm bảo client, thư viện URI và TLS stack sử dụng cách chuẩn hóa/so khớp phù hợp với chuẩn. Không lấy `String.toLowerCase()` theo locale hoặc chỉ so suffix làm verifier.

### 8.4. Đừng lấy SAN của đối tác làm hostname để kết nối

Không nên xử lý như sau: “certificate có DNS SAN `api.example.test`, vậy ta coi đích hiện tại chính là `api.example.test`”, trong khi ứng dụng thực tế định gọi `billing.example.test`. Đây là đảo chiều của kiểm tra danh tính, biến claim trong chứng thư thành yêu cầu mà không so sánh với identity bên ngoài chứng thư.

## 9. Những yếu tố ngoài PKIX và hostname matching vẫn phải tính

### 9.1. Authorization và nhận diện dịch vụ

Ngay cả khi `billing.example.test` được chứng thư đại diện chính xác và TLS handshake an toàn, ứng dụng vẫn phải xác minh đối tác có **quyền thực hiện thao tác nghiệp vụ**: API scope, tenant, JWT audience, mutual TLS client identity, hạn mức, quyền đọc dữ liệu, chống replay/idempotency. Hostname verification không thay thế authorization.

### 9.2. mTLS và các dạng định danh khác

Với **mutual TLS**, server cũng kiểm chứng certificate của client. Identity của client có thể theo profile nội bộ: DNS SAN, URI SAN (chẳng hạn mô hình service identity), chứng thư người dùng hoặc ràng buộc khác được tổ chức định nghĩa. Không lấy một hostname ngẫu nhiên trong SAN của client certificate làm “người dùng được phép truy cập tất cả API”.

Hostname verification server HTTPS và xác thực danh tính **client mTLS** là hai hướng khác nhau của trust. PKIX chain vẫn là nền tảng, nhưng mỗi hướng cần **identity và authorization policy riêng**.

### 9.3. Certificate pinning có phải thay thế PKIX không?

Pinning chứng thư hoặc SPKI có thể bổ sung giới hạn tin cậy khi được provisioning qua kênh đáng tin, nhưng tạo bài toán rollover/cert renewal và backup pins. Không dùng “pin công khai” thu từ kết nối chưa xác thực như thể nó đã xác thực lần kết nối đầu tiên. Một pin cho tổ chức cũng không có nghĩa key được phép đại diện cho **mọi hostname/tenant**; vẫn cần binding hợp lệ theo policy.

### 9.4. Revocation và thời điểm đánh giá

Khi một private key server bị lộ, certificate còn hạn sử dụng và SAN có thể vẫn khớp. Nếu client không có cơ chế phát hiện thu hồi/compromise theo chính sách, hai kiểm tra “chain và hostname” có thể không đủ để phát hiện hiện trạng mới. Cần quản lý vòng đời chứng thư, trust updates, CRL/OCSP khi áp dụng và incident response.

### 9.5. Redirects, proxy và DNS cache

Khi HTTP client theo redirect từ `billing.example.test` sang một origin khác, phải có xác minh TLS đúng với **hostname mới**; đồng thời ứng dụng cần kiểm soát chính sách **được phép redirect sang đâu**. DNS caching, split-horizon DNS, service mesh hoặc proxy không phải lý do bỏ endpoint validation.

**Tách layer:** TLS xác nhận *endpoint identity*; ứng dụng quyết định có tin endpoint đó để xử lý dữ liệu/credentials hay không. Một redirect đến server có certificate hoàn toàn hợp lệ vẫn có thể không phù hợp chính sách gửi bearer token của ứng dụng.

## 10. Bảng quyết định: path và hostname là hai phép kiểm độc lập

| PKIX trust/path | Hostname/IP identity | Kết quả phải xử lý | Ý nghĩa |
| --- | --- | --- | --- |
| **Đạt** | **Khớp** | Có thể chấp nhận **nếu** các điều kiện TLS/policy khác đạt | Cả nguồn trust và đúng endpoint đã được kiểm. |
| **Đạt** | **Không khớp** | **Từ chối** | Certificate hợp lệ nhưng thuộc server khác. |
| **Không đạt** | **Khớp** | **Từ chối** | SAN đúng nhưng chứng thư không được tin/đã hết hạn/bị lỗi path/policy. |
| **Không đạt** | **Không khớp** | **Từ chối** | Cả trust và identity đều không đạt. |
| **Không kiểm** | **Khớp** | **Từ chối** | So hostname trên certificate chưa được tin là không đủ. |
| **Đạt** | **Không kiểm** | **Từ chối** | Bỏ hostname verification không được thay bằng PKIX. |

Không dùng cờ `ignoreSslErrors` hoặc một trust manager luôn true để chuyển các ô “từ chối” thành “chấp nhận”. Trong bài test, phải dùng CA test và server test cô lập thay vì làm yếu cấu hình toàn cục của JVM.

## 11. Trường hợp sai thường gặp khi viết Java

| Triệu chứng / anti-pattern | Vì sao chưa đúng | Cách xử lý |
| --- | --- | --- |
| Gọi `CertPathValidator.validate` xong rồi coi đúng server | Validator không nhận reference hostname HTTPS | Kết hợp endpoint verification của JSSE. |
| Gọi `X509Certificate.verify(caKey)` rồi chấp nhận | Chỉ kiểm chữ ký certificate bằng key caller đưa vào | Xác minh chain, trust anchor, usage, hostname. |
| `new TrustAnchor(anyCert, null)` với cert do remote gửi | Client tự tin một root do attacker kiểm soát | Trust anchors phải được provision đáng tin. |
| `CertificateFactory` parse được certificate | Parse không xác minh certificate chain hay name | Dùng JSSE/PKIX phù hợp, không dùng parser làm trust verifier. |
| `getSubjectAlternativeNames()` thấy một DNS name rồi chấp nhận | Chỉ liệt kê SAN, chưa so với hostname mong đợi | Sử dụng endpoint matcher theo profile. |
| SAN đúng nhưng chain fail | Root/intermediate thiếu, bị thu hồi, hết hạn, sai policy | Sửa PKI/truststore/cert chain; không tắt trust. |
| Chain đúng nhưng hostname fail | Leaf cho DNS/IP khác, wildcard không phù hợp | Sửa SAN certificate hoặc tên endpoint tin cậy. |
| Chỉ có `CN=billing.example.test` | CN không phải reference identity hợp lệ theo RFC 9525 | Phát hành SAN dNSName đúng. |
| URL dùng IP nhưng certificate chỉ có `DNS:IP-text` | Không đúng type `iPAddress` | Thêm IP SAN hoặc dùng hostname được xác thực đúng cách. |
| Gọi `SSLSocket.startHandshake` không bật endpoint identification | TLS thấp tầng có thể không so hostname mặc định | Dùng `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")`. |
| Cài custom `HostnameVerifier` luôn true | Bỏ qua mismatch, gây MITM | Gỡ bypass, sửa chứng thư và endpoint. |
| Tắt revocation trong production “vì demo chạy” | Thay đổi độ an toàn theo policy, bỏ kiểm trạng thái thu hồi | Định nghĩa CRL/OCSP và failure behavior phù hợp. |
| Dùng SNI như bằng chứng endpoint identity | SNI giúp server chọn cert, không kiểm cert phía client | Vẫn phải xác minh SAN sau handshake. |
| Coi mTLS client certificate là quyền truy cập tự động | Trust/identity khác authorization | Kiểm tra role/scope/tenant sau mTLS. |
| Kết nối đến proxy/IP và không giữ hostname logic | Peer identity sai hoặc không được kiểm | Cấu hình reference identity đáng tin cho TLS. |

### 11.1. Lỗi và dấu hiệu cụ thể

- `CertPathValidatorException` với nguyên nhân path validation: có thể do signature, validity, policy, trust anchor hoặc revocation. Không tự kết luận đây là hostname mismatch.
- `SSLHandshakeException` trong JSSE: có thể bọc lỗi PKIX **hoặc** lỗi endpoint identity. Đọc root cause và diagnostics không tiết lộ secret.
- `CertificateException` với thông tin kiểu “No subject alternative DNS name matching ...” hoặc “No subject alternative names present”: thường hướng tới lỗi tên/loại SAN, nhưng thông điệp chính xác phụ thuộc JDK/provider.
- Lỗi kiểu “unable to find valid certification path”: thường hướng tới trust anchors/chain building, **không phải** bằng chứng hostname đúng/sai.
- Nếu test chỉ gọi `CertPathValidator` và trả thành công, **không** có bằng chứng rằng hostname verification đã chạy.

Debug nên ghi **hostname/IP tham chiếu đã được chọn**, dạng SAN công khai, issuer/trust policy, trạng thái chứng thư và exception category; không log private keys, session secrets, bearer tokens hoặc dữ liệu riêng tư.

## 12. Kiểm thử hai chiều để không bỏ sót lỗ hổng

### 12.1. Test matrix tối thiểu

Dùng một test CA được tin **chỉ trong môi trường test** và các leaf certificates tùy biến. Không thêm CA test vào production truststore.

| Ca | Certificate chain | DNS/IP SAN của leaf | Đích client mong đợi | Kỳ vọng |
| --- | --- | --- | --- | --- |
| 1 | Trust hợp lệ | `DNS:billing.example.test` | `billing.example.test` | TLS được chấp nhận nếu các policy khác đạt |
| 2 | Trust hợp lệ | `DNS:service.example.test` | `billing.example.test` | TLS phải từ chối **name mismatch** |
| 3 | Self-signed không tin cậy | `DNS:billing.example.test` | `billing.example.test` | TLS phải từ chối **untrusted chain** |
| 4 | Hết hạn | `DNS:billing.example.test` | `billing.example.test` | TLS phải từ chối |
| 5 | Trust hợp lệ | `IP:192.0.2.10` | `192.0.2.10` | Khớp IP-ID nếu policy khác hợp lệ |
| 6 | Trust hợp lệ | `DNS:192.0.2.10` | `192.0.2.10` | Từ chối vì sai loại SAN |
| 7 | Trust hợp lệ | `DNS:*.svc.example.test` | `a.svc.example.test` | Có thể khớp một nhãn theo RFC/profile |
| 8 | Trust hợp lệ | `DNS:*.svc.example.test` | `a.b.svc.example.test` | Từ chối vì wildcard vượt một nhãn |
| 9 | Trust hợp lệ | Chỉ CN đúng, không có SAN | `billing.example.test` | Từ chối theo RFC 9525 |
| 10 | Chain hợp lệ cho đúng hostname | Certificate sai EKU/KeyUsage TLS server | `billing.example.test` | Từ chối theo TLS policy |

**Điểm test quan trọng nhất của bài:** tạo một chain **đạt PKIX** nhưng SAN **không** khớp hostname. Đây là ca mà unit test chỉ gọi `CertPathValidator` thường bỏ qua. Demo Java ở trên tạo ra tình huống này ở lớp certificate; integration test qua JSSE cần xác nhận handshake **bị từ chối**.

### 12.2. Test qua JSSE thật, không chỉ qua getter

Một integration test đúng phải chạy một **local TLS server có private key tương ứng leaf certificate**, đồng thời client có truststore chỉ tin test CA và hostname reference được cấu hình đúng. Khi client kết nối bằng hostname cố định trong kịch bản, kiểm tra:

- Chain đúng + hostname đúng → handshake được chấp nhận.
- Chain đúng + hostname sai → `SSLHandshakeException`/`CertificateException` tùy provider.
- Chain sai + hostname đúng → phải từ chối.
- Khi thử `SSLSocket`, bật `setEndpointIdentificationAlgorithm("HTTPS")` để kiểm tra mục tiêu của bài.

Dùng DNS test host mapping/local resolver thích hợp hoặc cấu hình peer host đúng trong SSLEngine/SSLSocket; không dùng một chứng thư self-signed không được tin để chứng minh lỗi hostname vì khi đó handshake đã có thể bị chặn **trước** name comparison.

### 12.3. Các câu hỏi bắt buộc khi QA bảo mật

- Hostname để verify đến từ đâu? Có phải đích mà ứng dụng lựa chọn, không phải field từ attacker?
- Client có sử dụng TLS trust manager đáng tin và anchor đúng không?
- Endpoint identification có thực sự bật cho từng loại client, từng đường code, từng môi trường không?
- Các API có retry/fallback sang “insecure mode” khi gặp lỗi SSL không?
- Proxy/redirect/reverse proxy có làm thay đổi reference identity hoặc gửi credentials sang origin khác không?
- Có kiểm SAN DNS type 2 và IP type 7 đúng cách không?
- Có tránh CN fallback, wildcard quá rộng, IDNA không nhất quán không?
- Có kiểm certificate validity/revocation/algorithm/EKU theo policy không?
- Có test negative chain-valid-but-host-wrong, cùng với negative host-right-but-chain-invalid không?

## 13. Bài tập và câu hỏi tự kiểm tra

1. `CertPathValidator.validate` nhận những loại input nào? Vì sao nó không thể tự biết bạn đang gọi URL `billing.example.test`?
2. Trong demo, vì sao `PKIX path valid: true` đồng thời với `Different target DNS listed: false`?
3. Nếu đưa một leaf certificate được CA tin cậy ký cho `other.example.test` vào HTTPS client kết nối `billing.example.test`, phải chấp nhận hay từ chối?
4. Phân biệt `X509Certificate.verify`, `CertPathBuilder`, `CertPathValidator`, `X509Certificate.getSubjectAlternativeNames` và JSSE endpoint identification.
5. `TrustAnchor` do ai lựa chọn? Vì sao “client tự tin root do server gửi” là sai?
6. Nếu `PKIXParameters.setRevocationEnabled(false)` dùng trong demo offline, điều đó có nói gì về an toàn khi triển khai thật?
7. Với `https://192.0.2.10`, hostname identity được kiểm với SAN loại nào? Vì sao `DNS:192.0.2.10` không thay thế?
8. Khi nào một wildcard DNS-ID có thể khớp một hostname? Vì sao không dùng `String.endsWith`?
9. `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` phải được dùng ở đâu trong luồng `SSLSocket`?
10. Nếu dùng HTTP client cấp cao mà lập trình viên gắn trust manager luôn true và hostname verifier luôn true, còn bảo đảm gì từ PKIX/hostname?
11. Vì sao SNI không chứng minh chứng thư đã được xác minh danh tính?
12. Khi cấu hình mTLS, bước PKIX của client certificate có tự đủ để gán mọi quyền nghiệp vụ không?

**Bài tập A:** chạy `PkixHostnameDemo` và ghi lại hai kết quả `PKIX path valid`, `Different target DNS listed`. Giải thích “thành công ở lớp certificate path” và “không thỏa hostname” không hề mâu thuẫn.

**Bài tập B:** giữ nguyên test CA/leaf, nhưng giả sử endpoint khác là `service.example.test`. Mô tả vì sao bước **reference identity** thay đổi trong khi PKIX path validation vẫn như cũ. Không lấy SAN từ certificate làm URL mong muốn.

**Bài tập C:** dùng local TLS server/truststore test để tạo tình huống PKIX hợp lệ nhưng hostname sai, rồi bật/tắt `setEndpointIdentificationAlgorithm("HTTPS")` trong **môi trường lab cô lập**. Đối chiếu sự khác biệt, sau đó luôn trả cấu hình về an toàn. Không đưa chế độ tắt kiểm tra vào production.

**Bài tập D:** thiết kế test matrix có chứng thư chỉ có CN, certificate có IP SAN, cert hết hạn và certificate chain từ CA không được trust. Chỉ một trong hai điều kiện PKIX/name đạt vẫn phải bị từ chối.

## 14. Checklist trước khi deploy

- [ ] Chỉ tin các root/intermediate/trust anchors theo PKI policy của tổ chức.
- [ ] Dùng HTTPS client/JSSE tin cậy, có endpoint identification hoạt động trên **mọi** đường code cần TLS server authentication.
- [ ] Reference hostname/IP được chọn từ endpoint đáng tin, không phải từ thông tin certificate/server tự gửi.
- [ ] SAN dNSName/iPAddress đúng kiểu, wildcard đúng quy tắc, không dựa vào CN fallback.
- [ ] Không có trust-all manager, `HostnameVerifier` luôn true, insecure fallback hoặc flags vô hiệu hóa identity verification.
- [ ] Kiểm thuật toán, độ mạnh khóa, validity, usage, policies, revocation theo chuẩn và chính sách.
- [ ] Có negative test PKIX-pass/hostname-fail cùng hostname-pass/PKIX-fail.
- [ ] Phân biệt hostname verification, TLS cryptographic authentication và **authorization** nghiệp vụ.
- [ ] Có quy trình certificate rotation, cấu hình truststore, quản lý proxy/redirect/SNI và test nhiều environment.
- [ ] Không dùng root/leaf demo của bài học làm chứng thư hoặc trust anchor production.

## 15. Tài liệu chính thức

- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): đường chứng thư, trust anchors, extensions, policies và tên trong SAN.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): đối chiếu reference identity với presented identity, DNS-ID/IP-ID, wildcard, không dùng Common Name RDN.
- [CertPathValidator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): `getInstance("PKIX")`, `validate(CertPath, CertPathParameters)`.
- [CertPathBuilder — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): tìm đường chứng thư theo policy.
- [PKIXParameters — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, revocation, date và các chính sách path.
- [TrustAnchor — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/TrustAnchor.html): biểu diễn CA/root tin cậy.
- [X509Certificate — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): SAN và metadata chứng thư.
- [SSLParameters — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): `setEndpointIdentificationAlgorithm("HTTPS")`.
- [X509ExtendedTrustManager — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): trust checks với ngữ cảnh `Socket` hoặc `SSLEngine`.
- [HttpClient — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html): HTTPS client và cấu hình TLS.
