# 13.1 Chứng thư gắn khóa công khai với danh tính và vai trò của CA

## Mục tiêu học tập và vị trí của bài

Sau bài này, bạn có thể giải thích **vì sao một public key cần được gắn với một danh tính thông qua chứng thư X.509**, **CA thực sự chứng nhận điều gì** và **vì sao chữ ký của CA mới chỉ là một bước trong quyết định tin cậy**. Bạn cũng có thể đọc cấu trúc cốt lõi của một certificate bằng Java 17, phân biệt private key, public key, chứng thư, CSR và trust anchor mà không nhầm chứng thư với một giấy phép truy cập.

Bài 13.1 là **nền tảng khái niệm** cho chương 13. Những kỹ thuật chi tiết được học ở các bài riêng: phân tầng root/intermediate/leaf (13.2), DER/PEM và `CertificateFactory` (13.3), các trường subject/issuer/serial/validity (13.4), SAN DNS/IP (13.5), KU/EKU/BC (13.6), `checkValidity`/`verify`/PKIX (13.7), quy trình keytool CSR/reply (13.8) và cách ly CA thử nghiệm (13.9). Những điều kiện được nhắc vắn tắt ở đây đủ để hiểu bức tranh lớn nhưng không thay thế quy trình chuyên sâu trong từng bài.

## 1. Bài toán: khóa công khai không tự khai báo nguồn gốc đáng tin

Alice muốn kết nối an toàn tới dịch vụ `api.example.test`. Cô nhận được một public key dùng trong giao thức mật mã. Đối thủ Mallory cũng có thể tạo một cặp khóa và tự xưng mình là `api.example.test`. **Chỉ nhận byte public key không đủ để phân biệt hai trường hợp.**

```text
Alice cần nói chuyện với api.example.test
                 |
                 +--> Public key K1 do chủ dịch vụ kiểm soát?
                 |
                 +--> Public key K2 do kẻ giả mạo đưa tới?
                 |
                 v
Vấn đề còn thiếu: bằng chứng đáng tin về
mối liên hệ giữa danh tính được mong đợi và public key.
```

**X.509 certificate** giải quyết một phần trọng yếu: một issuer ký lên **một gói dữ liệu mô tả subject, public key và các điều kiện sử dụng**. Người xác minh có thể kiểm rằng thông tin này thực sự được ký bởi khóa issuer tương ứng và không bị sửa đổi kể từ khi ký. Nhưng ai được phép cấp chứng thư cho tên đó và issuer có được tin không vẫn là câu hỏi về **chính sách PKI**.

Một public key tự sinh có thể dùng để verify chữ ký toán học, nhưng điều đó không chứng minh chủ khóa là ai. Một certificate tự ký cũng có thể có chữ ký hợp lệ về mặt mật mã mà chưa có nguồn tin cậy để xác nhận danh tính được khai báo.

## 2. Cấu trúc lời xác nhận: CA ký `TBSCertificate`, không chỉ “ký public key”

Cấu trúc X.509 v3 ở mức học thuật:

```text
Certificate
  |
  +-- tbsCertificate  (to-be-signed certificate)
  |     +-- version, serialNumber
  |     +-- issuer, validity
  |     +-- subject
  |     +-- subjectPublicKeyInfo
  |     |     +-- algorithm + PUBLIC KEY
  |     +-- extensions (SAN, KU, EKU, BC, ...)
  |
  +-- signatureAlgorithm
  +-- signatureValue   <-- ký lên DER của tbsCertificate
```

Những trường cùng nằm trong phần được ký:

| Thành phần | Vai trò với liên kết khóa–danh tính | Điều không thể tự suy ra |
| --- | --- | --- |
| `subjectPublicKeyInfo` | Chứa public key của **subject** và thuật toán liên quan | Chủ sở hữu khóa là ai nếu không có quá trình xác minh |
| `subject` | Distinguished Name của chủ thể; có thể rỗng theo profile | Subject CN là hostname TLS đã kiểm chứng |
| `subjectAltName` (SAN) | Mang định danh theo loại như DNS/IP/URI, tùy profile | Giá trị SAN tự chứng minh CA đáng tin |
| `issuer` | Nêu danh tính bên cấp chứng thư | Trùng DN với CA đã tin là đủ xác minh chữ ký |
| `serialNumber` | Định danh chứng thư trong phạm vi **issuer** | Serial duy nhất trên mọi CA |
| `notBefore`/`notAfter` | Khoảng thời gian có hiệu lực được CA tuyên bố | Chứng thư còn hạn chắc chắn chưa bị thu hồi |
| `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage` | Giới hạn vai trò CA và mục đích sử dụng khóa | Chứng thư có thể dùng cho mọi purpose hoặc cấp quyền nghiệp vụ |
| `signatureValue` | Chữ ký của issuer trên dữ liệu được bảo vệ | Issuer nhất thiết nằm trong truststore của người nhận |

Nói “CA ký public key” chỉ là một cách nói tắt. Chính xác hơn, **CA ký phần `TBSCertificate`**, trong đó public key được gắn với subject, issuer, serial, thời hạn và các extensions. Việc đổi một trường được ký làm phép kiểm chữ ký thất bại nếu không có chữ ký mới từ private key của issuer.

**Chứng thư không mã hóa dữ liệu**: thông thường certificate và public key được phân phối công khai. Private key tương ứng với subject phải được bảo vệ trong keystore, HSM hoặc hệ thống quản lý khóa thích hợp; không nằm trong certificate PEM/DER thông thường. Private key của **CA** là một khóa khác: nó ký certificate, không phải khóa mà mọi server đều được sao chép.

## 3. CA làm gì, và quyền lực của CA đến từ đâu?

**Certification Authority (CA)** là chủ thể/đơn vị vận hành quy trình phát hành chứng thư theo chính sách xác minh danh tính và bảo vệ signing key. CA có thể kiểm soát quyền đối với DNS name, tổ chức, người dùng hoặc thiết bị tùy loại chứng thư, rồi cấp X.509 với nội dung đã duyệt.

Các vai trò tách biệt:

| Vai trò | Trách nhiệm |
| --- | --- |
| **Subject / applicant** | Sinh và bảo vệ private key; đưa public key và thông tin đề nghị cấp đến CA qua CSR hoặc quy trình khác |
| **Registration Authority (RA)**, khi có | Hỗ trợ thẩm định người xin cấp/quyền sử dụng định danh và quy trình enrollment |
| **CA / issuer** | Xác minh và phê duyệt theo chính sách; đặt serial, hiệu lực, extensions; ký `TBSCertificate` bằng private key CA |
| **Relying party / verifier** | Quyết định trust anchors nào được chấp nhận; xác minh path, điều kiện sử dụng và danh tính đích cần kết nối |
| **Chủ ứng dụng** | Kiểm quyền nghiệp vụ sau khi danh tính đã được xác thực qua giao thức tương ứng |

**CA không cấp quyền đăng nhập vào mọi hệ thống** chỉ bằng chữ ký chứng thư. Ví dụ doanh nghiệp cấp client certificate cho nhân viên có thể chứng minh một danh tính mTLS; quyền đọc từng đơn hàng vẫn do IAM/ACL của ứng dụng quyết định.

Về mặt PKI, **root CA** thường là trust anchor được cấu hình tin cậy trước, **intermediate CA** nhận quyền phát hành từ CA cấp trên với ràng buộc cụ thể, còn **leaf/end-entity** được cấp cho website/người dùng/ứng dụng. Một self-signed root chỉ có giá trị trusted khi verifier **chủ động đặt nó vào tập trust anchors** theo kênh và chính sách đáng tin. Đừng suy từ `Subject=Issuer` hay `CA=true` rằng một CA mặc nhiên được tin. Vai trò, pathLen, CA constraints và sự khác biệt self-issued/self-signed được phân tích sâu ở bài 13.2.

### 3.1. Chữ ký của issuer chứng minh được điều gì?

Ví dụ issuer tên `Example Issuing CA` ký leaf với SAN `DNS:api.example.test`.

- Nếu byte `TBSCertificate` bị đổi sau khi ký, bước `verify` bằng public key của issuer phù hợp sẽ phát hiện sai khác.
- Nếu một public key **khác** được dùng để kiểm chữ ký, phép kiểm thường thất bại.
- Nếu issuer key đúng nhưng issuer **không nằm trên đường tin cậy** mà client chấp thuận, chứng thư **chưa được tin** cho kết nối.
- Nếu CA đã cấp nhầm SAN, chữ ký vẫn có thể hợp lệ về mặt mật mã, nhưng chứng thư có thể tạo rủi ro giả mạo. Bảo mật vì thế phụ thuộc cả quy trình **thẩm định và cấp** của CA.

Điều này giải thích vì sao CA cần quản trị identity validation, kiểm soát quyền truy cập signing key, audit, certificate profile, revocation/rotation và xử lý chứng thư cấp nhầm. Khả năng ký không có nghĩa quyền phát hành tùy ý.

## 4. Luồng từ khóa tới chứng thư, sau đó tới quyết định chấp nhận

```text
[1] Subject sinh cặp khóa
    private key được giữ bí mật; public key được chia sẻ
               |
               v
[2] Subject gửi CSR (PKCS#10) hoặc yêu cầu cấp tương ứng
    proof of possession + subject/public key + requested extensions
               |
               v
[3] CA/RA kiểm tra quyền đối với identity theo policy
    xác định SAN, KU, EKU, BC, validity và serial được cấp
               |
               v
[4] CA ký tbsCertificate -> phát hành X.509 leaf + issuer chain
               |
               v
[5] Peer nhận certificate và xác minh:
    issuer signatures + path tới trust anchor đáng tin
    + thời hạn, constraints, purpose, revocation policy
               |
               v
[6] Ứng dụng kiểm expected identity và giao thức chứng minh
    peer thực sự giữ private key (ví dụ TLS handshake)
               |
               v
[7] Ứng dụng kiểm quyền business riêng trước khi cho thao tác
```

Đây là **bản đồ khái niệm**, không phải chỉ dẫn rằng phải tự code từng bước kiểm TLS theo thứ tự. Trong ứng dụng Java HTTPS, JSSE/trust manager và endpoint identification phối hợp nhiều bước, áp quy tắc theo provider và chính sách. Bài 13.7 đi vào `checkValidity`, `verify`, `CertPathValidator`; bài 13.8 đi sâu từng lệnh `keytool` phát hành và nhập phản hồi CSR.

### 4.1. CSR là lời đề nghị, không phải chứng thư

**Certification Signing Request (PKCS#10)** chứa public key, subject/attributes và chữ ký do applicant tạo bằng private key tương ứng. Chữ ký của CSR cho thấy người yêu cầu điều khiển khóa trong ngữ cảnh chữ ký, **không** chứng minh họ sở hữu domain. CSR có thể yêu cầu SAN nhưng CA phải **thẩm định độc lập** trước khi cấp; nó có thể từ chối, sửa hoặc không cấp extensions đó.

**Certificate reply** đã được CA ký là đối tượng khác. Khi nhận reply cho một CSR, phải khớp public key của chứng thư với private key đã tạo CSR. Server muốn dùng chứng thư trong TLS cần lưu **leaf certificate chain cùng private key**. Thao tác keytool nhập reply vào đúng alias được học đầy đủ ở 13.8.

### 4.2. Trust anchor là quyết định của người xác minh, không phải “một root bất kỳ”

Một root CA công khai thường được hệ điều hành/JDK hoặc chính sách ứng dụng cung cấp trong truststore. Một private CA có thể do tổ chức chủ động thêm vào **truststore riêng theo mục đích**. Chứng thư tự ký có thể được chủ động pin/trust theo thiết kế hẹp sau khi kiểm nguồn gốc; tự ký **không tự cấp trust**.

Không import root do chính server chưa được xác thực gửi tới, chỉ vì `PKIX path building failed`. Nếu làm vậy, attacker có thể tạo cả root lẫn leaf tự ký hợp lệ cho tên tùy ý. Dùng trust anchors đã kiểm chứng và luôn giữ kiểm tên endpoint.

## 5. Một ví dụ dễ hình dung: chứng thư đúng nhưng danh tính chưa chắc đúng

Giả sử Alice muốn liên lạc với `payments.example.test`:

| Trường hợp | Chữ ký leaf | Trust/identity theo client | Kết luận |
| --- | --- | --- | --- |
| Leaf do CA được client tin cấp cho `payments.example.test`, SAN DNS khớp, các điều kiện khác đạt | Đúng | Path và tên đích phù hợp | Có thể chấp nhận trong TLS theo policy |
| Leaf do CA được tin cấp cho `files.example.test`, client gọi `payments.example.test` | Đúng | Path có thể đúng, **SAN sai đích** | Từ chối kết nối do sai endpoint |
| Leaf tự ký với `CN=payments.example.test` do Mallory tạo | Tự ký đúng bằng khóa Mallory | Không có trust anchor phù hợp | Từ chối; tên tự khai không tạo tin cậy |
| Leaf do CA được tin cấp nhưng đã hết hạn hoặc bị thu hồi | Chữ ký có thể đúng | Vi phạm validity/status policy | Từ chối theo chính sách |
| Client mTLS có certificate được CA nội bộ tin cấp nhưng gọi API vượt role | Chữ ký/path có thể đúng | Không đạt authorization của tài nguyên | Không cấp quyền thao tác |

Ba nhầm lẫn cần loại bỏ ngay:

1. **“Tôi đã parse được chứng thư.”** Parse chỉ giúp đọc cấu trúc; `CertificateFactory` không tự tin CA.
2. **“Tôi đã verify được chữ ký.”** `X509Certificate.verify(publicKey)` chỉ kiểm chữ ký chứng thư bằng key được cung cấp; không chọn trust anchor, không kiểm hostname, không kiểm revocation toàn diện.
3. **“Tôi đã tìm ra root.”** Nếu root lấy từ chính input không đáng tin, việc tự đặt nó làm `TrustAnchor` phá vỡ mô hình PKI.

Trong HTTPS, client thường phải đối chiếu DNS/IP **theo SAN đúng loại** của hostname/IP mà client định truy cập; Subject CN không thay thế bước nhận diện tên hiện đại. Bài 13.5 dành riêng cho DNS/IP/wildcard/IDNA và cơ chế endpoint identification.

## 6. Thực hành nền tảng Java 17+: quan sát CA certificate, không tự tạo trust

Đây là thí nghiệm nhỏ nhằm **nhìn tận mắt binding và signer**. Mã tạo một CA demo self-signed, xuất **chỉ public certificate** ra PEM và dùng Java đọc các trường. Nó **không** phát hành leaf, không tự import root vào truststore, không mở TLS. Một lab root self-signed thành công về mật mã vẫn **không có quyền trusted mặc định**.

Trong một thư mục mới chỉ dùng cho bài học, chạy `keytool` của JDK 17+. Các lệnh hỏi password tương tác; không đưa password thật lên command line:

```bash
keytool -genkeypair -alias lab-ca -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Learning CA,O=Training,C=VN" -validity 30 -ext BC:critical=ca:true,pathlen:0 -ext KU:critical=keyCertSign,cRLSign -keystore ca-demo.p12 -storetype PKCS12
keytool -exportcert -alias lab-ca -rfc -file ca-demo.pem -keystore ca-demo.p12 -storetype PKCS12
```

- `ca-demo.p12` chứa **private signing key của CA**, phải giữ bí mật và chỉ dùng trong lab.
- `ca-demo.pem` chỉ chứa certificate/public key và có thể đọc được; **việc có file không đồng nghĩa client đã tin CA**.
- `BasicConstraints CA=true` và `KeyUsage keyCertSign` diễn đạt vai trò được cấp trong chứng thư. Việc sử dụng làm root trusted là quyết định riêng của verifier.
- `-validity 30` tạo một khoảng hiệu lực từ lúc lập lab; sau 30 ngày cần tạo fixture mới để test điều kiện còn hạn.

Tạo file **`CaBindingInspect.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

public final class CaBindingInspect {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) {
            throw new IllegalArgumentException(
                    "Usage: java CaBindingInspect <certificate.pem>");
        }

        X509Certificate cert;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            cert = (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(in);
        }

        System.out.println("X.509 parsed: " + "X.509".equals(cert.getType()));
        System.out.println("Self-issued DN: " +
                cert.getSubjectX500Principal()
                    .equals(cert.getIssuerX500Principal()));
        System.out.println("Certificate is CA: " +
                (cert.getBasicConstraints() >= 0));

        cert.checkValidity();
        System.out.println("Within current validity interval: true");
        cert.verify(cert.getPublicKey());
        System.out.println("Self-signature verifies: true");

        // Không được coi các dòng trên là phép kiểm tra trust/hostname.
        System.out.println("Issuer trusted by this program: not evaluated");
        System.out.println("Endpoint hostname verified: not evaluated");
    }
}
```

Biên dịch và chạy sau khi tạo `ca-demo.pem` (lệnh Java ở dưới là chương trình độc lập):

```bash
javac --release 17 CaBindingInspect.java
java CaBindingInspect ca-demo.pem
```

Với **fixture vừa tạo** trên JDK có `keytool` và các provider cần thiết, kết quả kỳ vọng:

```text
X.509 parsed: true
Self-issued DN: true
Certificate is CA: true
Within current validity interval: true
Self-signature verifies: true
Issuer trusted by this program: not evaluated
Endpoint hostname verified: not evaluated
```

Điều gì đã được chứng minh?

- `CertificateFactory("X.509")` đọc cấu trúc chứng thư, **không** xác định CA có được ứng dụng tin cậy.
- `Subject=Issuer` phản ánh **self-issued**; `verify(cert.getPublicKey())` xác nhận riêng chữ ký tự ký của fixture. Đây là hai thuộc tính khác nhau và sẽ được phân tích sâu hơn ở 13.2.
- `checkValidity()` chỉ cho biết ngày hiện tại nằm trong validity interval, **không** kiểm tra danh tính hoặc trạng thái thu hồi.
- Chương trình chủ ý in **not evaluated** ở hai mục trust và hostname vì nó chưa dùng trust anchors/PKIX hay kết nối HTTPS.
- Root PEM public có thể phân phối theo kênh phù hợp, nhưng không tự đặt nó thành trusted root của hệ thống hoặc browser. Từ thí nghiệm này, người học cần phân biệt **một signature đúng** với **một trust decision hợp lệ**.

**Không nhập CA demo vào truststore production/cacerts, không dùng private key lab ngoài phòng thực hành.** Bài 13.9 trình bày rõ cách cách ly một CA lab, quản lý password, truststore và các bài kiểm thử âm.

## 7. Chẩn đoán tư duy từ việc nhận một chứng thư

Khi được giao một file chứng thư mới, hãy trả lời theo thứ tự:

1. **File thật sự là gì?** Là public X.509 certificate, CSR, public key thô hay keystore có private key? Không căn cứ vào đuôi file. Bài 13.3 hướng dẫn cách đọc DER/PEM.
2. **Ai là subject, issuer, danh tính được cấp?** Đọc các trường đã được ký; issuer name không bảo đảm chữ ký hoặc trust. Bài 13.4 giải thích DN, serial và validity.
3. **CA đã tuyên bố phạm vi sử dụng nào?** SAN, KeyUsage, ExtendedKeyUsage, BasicConstraints, các critical extensions có phù hợp? Bài 13.5–13.6 kiểm từng nhóm.
4. **Ai được verifier chủ động tin?** Root/intermediate nào tạo đường PKIX hợp lệ đến trust anchor và chứng thư có bị thu hồi theo policy? Bài 13.2 và 13.7 đi sâu.
5. **Đây có phải đúng dịch vụ/role cần xác thực?** Kiểm expected identity, TLS proof-of-possession và authorization theo protocol; không lấy identity kỳ vọng từ chính chứng thư chưa xác minh.
6. **Có phải chứng thư cấp từ quy trình đúng?** CSR, CA reply, private-key alias, chain, thời hạn, review/audit và môi trường lab/prod. Bài 13.8–13.9 làm rõ.

Đây là một **bảng câu hỏi đánh giá**, không phải code thay thế bộ xác minh TLS/PKIX. Khi lập trình kết nối HTTPS thật, ưu tiên JSSE/`HttpClient`/`HttpsURLConnection` được cấu hình an toàn; không tạo `X509TrustManager` chấp nhận mọi certificate hoặc `HostnameVerifier` luôn trả true.

## 8. Tình huống cần giải thích, thay vì chỉ học thuộc định nghĩa

**Tình huống A.** CA cấp certificate với `SAN=DNS:api.example.test` cho public key của service. Kẻ tấn công đổi SAN thành `admin.example.test` trong DER đã cấp mà không biết private key issuer. Điều gì phải xảy ra?

> Phần SAN thuộc `TBSCertificate` đã được ký, nên chữ ký không còn khớp. Một verifier đúng sẽ từ chối chứng thư đã bị chỉnh sửa.

**Tình huống B.** Mallory tạo root CA tự ký hợp lệ và đặt `CN=Example Trusted CA`. Alice có nên tin chứng thư server do root đó ký?

> Không. Tên và chữ ký tự ký là thông tin do Mallory điều khiển. Alice chỉ chấp nhận root nếu nó được xác lập làm trust anchor qua kênh và chính sách độc lập đáng tin.

**Tình huống C.** Một certificate do CA đáng tin cấp cho `files.example.test`, còn client cần gọi `payments.example.test`. Có nên kết nối?

> Không nếu SAN không bao phủ đúng đích. Trust chain có thể hợp lệ nhưng endpoint identity sai.

**Tình huống D.** Một client certificate mTLS được CA tin cấp và path hợp lệ. Nó có mặc nhiên được sửa toàn bộ hóa đơn không?

> Không. Xác thực danh tính không tự cấp quyền nghiệp vụ; service phải kiểm principal/tenant/role theo từng thao tác.

**Tình huống E.** Một CSR xin được cấp `CA:true` và `DNS:service.prod.example`. CA có nên sao chép nguyên yêu cầu vì CSR signature hợp lệ?

> Không. CSR signature chỉ xác thực quyền điều khiển private key của requester; CA phải thẩm định yêu cầu, danh tính và giới hạn certificate profile trước khi ký.

## 9. Những nhầm lẫn cốt lõi cần tránh

| Nhận định sai | Vì sao sai | Cách diễn đạt chính xác |
| --- | --- | --- |
| “CA chỉ ký public key.” | Chữ ký bao phủ `TBSCertificate` chứa nhiều trường | CA ký cấu trúc dữ liệu certificate được cấp, gồm public key, identity và constraints |
| “Certificate chứa private key.” | `subjectPublicKeyInfo` là public key | Private key được giữ tách biệt trong keystore/HSM |
| “Certificate parse được nên an toàn.” | Parser chỉ đọc định dạng X.509 | Cần kiểm trust/path/purpose/identity theo tình huống |
| “Issuer DN giống CA đáng tin nên chữ ký đúng.” | Bất kỳ ai có thể đặt DN giống | Phải kiểm signature bằng CA public key phù hợp và path policy |
| “Self-signed root mặc nhiên là trust anchor.” | Self-signature chỉ là sự kiện mật mã | Trust anchor do relying party thiết lập từ nguồn đáng tin |
| “Có CA signature thì đúng hostname.” | CA có thể cấp chứng thư cho tên khác | Kiểm expected DNS/IP qua SAN và verifier chuẩn |
| “Certificate của client được CA cấp nên có quyền admin.” | CA binding liên quan identity, không phải ACL | Sau xác thực phải kiểm authorization ở ứng dụng |
| “Certificate tự nó mã hóa HTTP.” | X.509 chỉ mang public key và các thuộc tính | TLS thiết lập kênh bảo mật theo giao thức, có xác thực endpoint |

## 10. Tổng kết và ranh giới với các bài tiếp theo

Chứng thư X.509 là **một lời xác nhận có chữ ký của issuer rằng public key gắn với subject/định danh đã được cấp trong một phạm vi sử dụng nhất định**. CA phải thực hiện issuance policy; verifier phải lựa chọn trust anchor, kiểm path, mục đích và đúng endpoint; ứng dụng vẫn phải kiểm quyền sau xác thực.

Bài 13.1 giúp người học đặt đúng câu hỏi về nguồn gốc public key và vai trò CA. Các bài kế tiếp cung cấp kiểm chứng chuyên biệt: **13.2** vai trò root/intermediate/leaf, **13.3–13.6** đọc và hiểu trường X.509, **13.7** phân tách validity/signature/trust, **13.8** quy trình CSR/chain trong keytool, **13.9** mô hình CA test cô lập.

**Tài liệu chuẩn:**

- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280) — cấu trúc `TBSCertificate`, issuer/subject, extensions, path validation.
- [Java SE 17 — X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html) — API xem các trường, chữ ký và hiệu lực.
- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html) — đọc DER/PEM thành chứng thư.
- [Java SE 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html) — tạo, xuất và xem chứng thư.