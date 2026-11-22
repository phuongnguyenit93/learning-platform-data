# 14.6. Thu hồi bằng CRL, OCSP và `PKIXRevocationChecker`

## Mục tiêu và phạm vi

Khi kiểm tra một chứng chỉ X.509, việc thấy chữ ký của CA hợp lệ và `notBefore ≤ now ≤ notAfter` **chưa đủ**: CA có thể đã thu hồi chứng chỉ trước ngày hết hạn do private key bị lộ, cấp nhầm, thay đổi quyền sử dụng hoặc chấm dứt dịch vụ. Bài này tập trung vào **revocation checking trong đường dẫn tin cậy PKIX**, sử dụng **CRL**, **OCSP** và API `java.security.cert.PKIXRevocationChecker` của Java 17+.

Học xong, bạn có thể:

1. Phân biệt **hết hạn**, **bị thu hồi**, **chưa xác định được trạng thái**, và **đường dẫn chứng chỉ không đáng tin**.
2. Đọc CRL/X.509, hiểu CRL issuer, serial number, `thisUpdate`, `nextUpdate`, chữ ký, CRL Distribution Points (CDP) và các giới hạn của danh sách thu hồi.
3. Hiểu OCSP `good/revoked/unknown`, responder URL qua AIA, kiểm tra chữ ký response và độ tươi của trạng thái, OCSP stapling và rủi ro mạng.
4. Cấu hình `PKIXRevocationChecker` theo chính sách: `PREFER_CRLS`, `NO_FALLBACK`, `ONLY_END_ENTITY`, `SOFT_FAIL` và nguồn CRL từ `CertStore`.
5. Dùng `CertPathValidator` để kiểm tra thực sự một certificate path trên **CRL sạch** và **CRL có chứng chỉ bị thu hồi**; không nhầm kiểm tra một serial trong CRL với kiểm tra PKIX hoàn chỉnh.
6. Chọn chính sách xử lý lỗi **fail-closed/hard-fail** hay **soft-fail** một cách minh bạch, đo lường timeout và kiểm thử tích hợp TLS.

**Giới hạn:** đây là bài về **thu hồi của chứng chỉ và đường dẫn PKIX**, không phải bài phát hành CA, TLS handshake hoàn chỉnh hay giao thức ứng dụng. Ví dụ dùng khóa/chứng chỉ **lab**, không bao giờ đưa CA tự tạo trong ví dụ vào truststore production. Java code dùng JDK 17+; hành vi mạng và các thiết lập hệ thống có thể khác giữa provider/JDK/ứng dụng.

## 1. “Chứng chỉ hợp lệ” gồm nhiều điều kiện

Một chứng chỉ có thể thỏa chữ ký số của CA mà vẫn bị từ chối vì:

- Chưa đến ngày `notBefore` hoặc đã quá `notAfter` (validity period).
- Không xây được đường dẫn từ chứng chỉ lá qua intermediate đến **trust anchor được tin cậy**.
- Trật tự CA/basic constraints/key usage, thuật toán/key strength, certificate policies hoặc name constraints không đạt yêu cầu.
- Tên máy chủ/SAN, Extended Key Usage hoặc mục đích sử dụng không phù hợp với ứng dụng, đặc biệt trong TLS.
- **Bị CA thu hồi** trước khi hết hạn và có bằng chứng thu hồi hợp lệ.
- **Không xác định được trạng thái thu hồi** vì không có CRL/OCSP response đáng tin, quá hạn hoặc không liên hệ được responder, tùy chính sách.

Ba trạng thái revocation cần hiểu rõ:

| Trạng thái | Ý nghĩa | Không được hiểu thành |
| --- | --- | --- |
| **GOOD / không tìm thấy revocation trong nguồn hợp lệ** | Theo bằng chứng revocation hợp lệ cho đúng issuer/serial/phạm vi và thời điểm kiểm tra, cert chưa bị ghi nhận là thu hồi | “Chứng chỉ hoàn toàn hợp lệ cho mọi mục đích” |
| **REVOKED** | CA/OCSP responder có thẩm quyền đã công bố thu hồi certificate | “Có thể bỏ qua do mạng chập chờn” |
| **UNKNOWN / UNDETERMINED** | Chưa thể chứng minh trạng thái theo dữ liệu và policy hiện có | “Không bị thu hồi” |

**Revocation không thay thế các bước PKIX và ứng dụng.** OCSP `good` chỉ nói về trạng thái thu hồi theo nguồn trả lời; không tự chứng minh domain/identity, certificate chain, thuật toán hoặc key usage hợp lệ. Một CRL không chứa serial cũng chưa chứng minh cert an toàn nếu CRL bị giả, sai issuer, hết hạn hoặc không bao phủ đúng đối tượng.

### Ví dụ một tình huống cụ thể

CA cấp certificate `serial=0x42`, hạn 1 năm. Sau 1 tháng private key bị nghi lộ, CA thu hồi `serial=0x42`. Dù certificate còn 11 tháng hiệu lực và chữ ký CA không thay đổi, verifier phải từ chối nếu có bằng chứng thu hồi hợp lệ. Nếu OCSP server down, verifier cần **quyết định trạng thái chưa biết theo policy**, không lặng lẽ gắn nhãn GOOD.

## 2. Vị trí kiểm tra thu hồi trong đường dẫn PKIX

Giả sử:

```text
Trusted Root CA (TrustAnchor, đã được chọn qua policy tin cậy)
    |
    +-- Intermediate CA (cert được Root ký)
             |
             +-- Leaf certificate: api.example.invalid
                    |
                    v
        Kiểm tra chữ ký / chain / thời hạn / purpose
                    |
                    v
             Revocation checks
           (leaf và CA trung gian nếu policy yêu cầu)
                    |
                    v
            ACCEPT hoặc REJECT
```

Trong Java, `CertPath` thông thường liệt kê **leaf → intermediate → ...**, **không chứa trust anchor** ở cuối. Trust anchor được truyền riêng qua `PKIXParameters`/`TrustAnchor`. Không được lấy root CA trực tiếp từ chain do peer gửi rồi tự thêm vào trust anchors: peer có thể tự phát hành CA giả. Nguồn trust anchor phải nằm trong cấu hình/KeyStore hoặc trust policy đáng tin.

**Phạm vi revocation:** thường quan tâm cả leaf và intermediate; nếu intermediate bị thu hồi, nhiều leaf do CA đó phát hành cũng mất đường tin cậy. `ONLY_END_ENTITY` làm giảm kiểm tra đối với CA certificates nên chỉ cân nhắc khi có chính sách/nguồn kiểm tra thay thế rõ ràng.

**Trust anchor** thường được tin trực tiếp và không được xử lý như một certificate path element bình thường; trạng thái root CA/trust anchor cần được quản lý bằng cập nhật truststore và chính sách tin cậy. Không nghĩ “PKIX check all certs” tức tự động phát hiện mọi CA gốc bị distrust ngoài cấu hình.

## 3. CRL — Certificate Revocation List

**CRL** (RFC 5280) là một danh sách **được CA hoặc CRL issuer có thẩm quyền ký**, chứa thông tin về các serial number được thu hồi theo một phạm vi/phân phối cụ thể.

Các trường và khái niệm thường gặp:

| Trường | Ý nghĩa thực tế |
| --- | --- |
| `issuer` | Danh tính issuer của CRL; thường CA cấp certificate, nhưng PKIX còn có trường hợp indirect CRL |
| `thisUpdate` | Thời điểm trạng thái danh sách có hiệu lực/cập nhật |
| `nextUpdate` | Thời điểm dự kiến phát hành CRL tiếp theo; dùng trong chính sách về độ tươi |
| `revokedCertificates` | Danh sách serial number của các cert bị thu hồi, thường kèm thời điểm và lý do |
| `signatureAlgorithm / signature` | Bằng chứng nội dung CRL do khóa được ủy quyền ký |
| `CRL Number` | Extension giúp định danh và quản lý phiên bản CRL |
| `Authority Key Identifier (AKI)` | Giúp xác định khóa dùng ký CRL trong bối cảnh có nhiều key/certificate |
| `CRL Distribution Points (CDP)` | X.509 extension trong certificate chỉ nơi có thể tải CRL (HTTP/LDAP...) |
| `Issuing Distribution Point` | Có thể thu hẹp phạm vi CRL, ví dụ chỉ cert end-entity hoặc chỉ một tập lý do |
| `delta CRL` | Chỉ thay đổi so với base CRL; không tự xử lý như danh sách đầy đủ nếu policy cần base |

Đường dẫn ví dụ:

```text
Certificate leaf -> CRL Distribution Points URI (nếu có)
                  -> tải CRL từ điểm phân phối
                  -> kiểm tra chữ ký và issuer/ủy quyền
                  -> kiểm tra thisUpdate/nextUpdate và phạm vi
                  -> đối chiếu serial number và reason
                  -> kết luận revocation theo quy tắc PKIX
```

Một số tính chất:

- CRL có thể **cache** và dùng offline sau khi nhận được bản còn hợp lệ. Ưu điểm là không cần kết nối OCSP cho từng lần kiểm tra, nhược điểm là độ lớn CRL và độ trễ cập nhật; thời điểm thu hồi thực tế có thể nằm sau thời điểm CRL gần nhất.
- **Không có serial trong CRL không đủ để kết luận an toàn** nếu CRL không đúng issuer/scope hoặc không còn mới. Một CRL “sạch” có issuer khác cũng không làm certificate trở thành hợp lệ.
- `X509CRL.isRevoked(cert)`/`getRevokedCertificate(serial)` là **kiểm tra membership** trên object CRL đã parse, không tự thay `CertPathValidator`: đừng chỉ gọi `isRevoked` rồi bỏ qua trust/freshness/signature/chain.
- **Đừng tự tải URL từ certificate chưa đáng tin tùy tiện**: CDP từ input X.509 có thể trỏ tới mạng nội bộ hoặc địa chỉ không mong muốn. Cần egress/proxy/SSRF controls và timeout thích hợp; hành vi phụ thuộc provider.
- CRL được một CA ký có thể bị phân vùng theo distribution point, reason hoặc issuer. Không lấy một CRL bất kỳ của CA đó rồi giả định luôn đầy đủ mọi chứng chỉ.

### Java đọc CRL thủ công

Snippet sau **chỉ minh họa parse và kiểm tra vài điều kiện riêng lẻ**, không phải validator độc lập:

```java
CertificateFactory factory = CertificateFactory.getInstance("X.509");
X509CRL crl;
try (InputStream in = Files.newInputStream(Path.of("issuer.crl"))) {
    crl = (X509CRL) factory.generateCRL(in);
}
System.out.println(crl.getIssuerX500Principal());
System.out.println(crl.getThisUpdate());
System.out.println(crl.getNextUpdate());
System.out.println(crl.getRevokedCertificates());
```

Snippet cần `java.io.InputStream`, `java.nio.file.Files/Path` và `java.security.cert.CertificateFactory/X509CRL`, cùng xử lý checked exceptions. `getRevokedCertificates()` có thể trả `null` nếu không có entries; dữ liệu có thể chứa thông tin nhạy cảm vận hành nên đừng log toàn bộ serial của đối tác nếu không cần. **Chỉ parse thành công không tự chứng minh CRL trusted**.

Nếu đã có một CA certificate thực sự đáng tin, `crl.verify(issuerPublicKey)` giúp kiểm tra chữ ký CRL, nhưng còn phải xác minh issuer/khả năng ký CRL (`cRLSign`), thời hạn, phạm vi và đường dẫn tin cậy. API PKIX có trách nhiệm xử lý đầy đủ hơn; đừng tự ghép check rời rạc rồi gắn nhãn “đã validate”.

## 4. OCSP — Online Certificate Status Protocol

**OCSP** (RFC 6960, kế thừa RFC 2560) là cơ chế hỏi responder về tình trạng của **một certificate cụ thể**, thay vì tải toàn bộ CRL.

Bản tin OCSP thường gắn với `CertID` gồm nhận diện issuer (hash của issuer name/key) và **serial** của certificate. Responder trả response có chữ ký, status, thời gian và thông tin responder; verifier phải kiểm tra **quyền ký OCSP response**, chữ ký, thời gian, association đúng cert/issuer và các quy tắc khác.

| Kết quả | Nội dung | Cách diễn giải |
| --- | --- | --- |
| `good` | Responder không báo chứng chỉ bị thu hồi theo thông tin responder cung cấp | Không thay thế xác minh chữ ký certificate/chain/hostname |
| `revoked` | Có bằng chứng bị thu hồi, có thể kèm revocationTime/reason | **REJECT** khi response hợp lệ |
| `unknown` | Responder không có trạng thái đáng tin cho CertID yêu cầu | **Không mặc định coi GOOD** |
| Response bị lỗi/timeout | Không nhận được bằng chứng sử dụng được | Xử lý **UNDETERMINED / policy fallback**, không coi là `good` |
| Response có chữ ký sai/không được ủy quyền | Không có bằng chứng đáng tin | Từ chối hoặc áp dụng cơ chế kiểm tra khác theo policy, **không** coi là `good` |

Trong chứng chỉ, extension **Authority Information Access (AIA)** có thể chứa OCSP responder URL. Một cấu hình ứng dụng cũng có thể dùng responder cố định (chẳng hạn CA nội bộ). Với `PKIXRevocationChecker.setOcspResponder(URI)`, URI cấu hình sẽ **ghi đè** URL OCSP từ AIA cho checker đó; chỉ dùng URL được phê duyệt cho trust boundary cụ thể.

**Tính mới và chống replay:** quan tâm `thisUpdate`, `nextUpdate`, `producedAt` và quy tắc allowed clock skew/cache TTL. OCSP nonce là extension tùy profile giúp liên kết request/response nhưng có yếu tố tương thích và hiệu năng; không tự thêm nonce mà chưa kiểm tra hỗ trợ responder/stapling/cache. OCSP response bị stale hoặc không đúng certificate không được coi là `good`.

### OCSP stapling trong TLS

Thay vì client tự hỏi responder, server TLS có thể gửi kèm **OCSP response đã ký** trong handshake (stapling). Lợi ích có thể gồm giảm độ trễ/khả năng lộ thông tin client đến responder và giúp cache ở server. Tuy nhiên client vẫn phải **thực sự kiểm tra** chữ ký, thời gian, cert association và chính sách; không phải cứ server gửi bytes “stapled” là tin được.

Một số chứng chỉ có extension về việc bắt buộc phải stapling (TLS Feature, thường gọi Must-Staple); khả năng hỗ trợ/enforcement khác nhau giữa client. **Không tự giả định Java JSSE của bạn đang kiểm tra revocation hoặc Must-Staple** nếu chưa cấu hình, kiểm thử và xác minh chính xác implementation.

## 5. So sánh CRL và OCSP khi vận hành

| Tiêu chí | CRL | OCSP |
| --- | --- | --- |
| Đơn vị truy vấn | Danh sách cho một issuer/phạm vi | Status của một certificate (hoặc nhóm CertID) |
| Cập nhật | Theo chu kỳ CRL, có thể có delta | Theo response và thời hạn cache/responder |
| Kích thước dữ liệu | Có thể lớn khi nhiều cert bị thu hồi | Response thường nhỏ, nhưng nhiều yêu cầu |
| Hoạt động offline | Có thể dùng CRL cache hợp lệ đã tin cậy | Có thể dùng response cache/stapled còn hợp lệ |
| Riêng tư | Người tải CRL không nhất thiết tiết lộ cert nào đang kiểm tra | Client hỏi responder có thể tiết lộ cert/timing; stapling giúp giảm |
| Sự cố mạng | CRL fetch không được / CRL quá hạn -> unknown | OCSP timeout, `tryLater`, responder unreachable -> unknown |
| Điều kiện tin cậy | Chữ ký CRL/issuer/ủy quyền/phạm vi/thời gian | Chữ ký response/responder authorization/CertID/thời gian |
| Java PKIX | `CertStore` CRLs, CRLDP nếu provider hỗ trợ | `PKIXRevocationChecker`, AIA/responder, OCSP responses |

**Đừng chọn cơ chế duy nhất chỉ vì tốc độ một lần đo.** Đặt trước yêu cầu về freshness, cách xử lý mất mạng, CA ecosystem, egress, chứng chỉ trung gian, cache, khả năng đo lường và mô hình đe dọa. Một cơ chế fallback giúp khả dụng nhưng chỉ có ích khi **nguồn thay thế thật sự xác thực được** trạng thái, không phải bỏ qua lỗi.

## 6. Các lớp Java tham gia revocation checking

| API | Trách nhiệm |
| --- | --- |
| `CertificateFactory.getInstance("X.509")` | Parse certificate, CRL và tạo `CertPath` |
| `X509Certificate` | Đại diện chứng chỉ, issuer/serial/validity/extension |
| `X509CRL` | Đại diện CRL, issuer, times, entries, kiểm tra signature riêng |
| `TrustAnchor` | CA/public key được ứng dụng chọn là gốc tin cậy |
| `CertPath` | Chuỗi chứng chỉ theo hướng leaf → intermediate, không kèm trust anchor |
| `CertStore` + `CollectionCertStoreParameters` | Cung cấp CRL/certificate cho việc tìm và kiểm tra |
| `PKIXParameters` | Trust anchors, ngày kiểm tra, CertStore, policy, checker |
| `PKIXBuilderParameters` | Tương tự nhưng có target constraints để **xây** đường dẫn |
| `CertPathValidator.getInstance("PKIX")` | Kiểm tra path đã có theo PKIX |
| `CertPathBuilder.getInstance("PKIX")` | **Xây** path từ candidate certificates và trust anchors |
| `PKIXRevocationChecker` | Chọn OCSP/CRL, fallback, soft-fail, responder và OCSP responses |
| `CertPathValidatorException` | Cho biết lý do PKIX thất bại, certificate index, cause |

Phân biệt **builder** và **validator**: `CertPathBuilder` tìm đường đi từ cert lá đến trust anchor qua các candidate certificates/`CertStore`; `CertPathValidator` kiểm tra một `CertPath` đã có. **Cả hai** có thể dùng `PKIXRevocationChecker` khi được thêm vào parameters phù hợp. Khi application đã có chain từ TLS handshake, không mặc nhiên coi nó là đường dẫn hợp lệ chỉ vì peer gửi đầy đủ.

## 7. `PKIXRevocationChecker`: cấu hình chính xác

Checker không được tạo bằng `new PKIXRevocationChecker()` vì đây là lớp **abstract**. Lấy checker từ PKIX engine:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();
```

Các option chuẩn:

| Option | Ý nghĩa | Cảnh báo |
| --- | --- | --- |
| `PREFER_CRLS` | Ưu tiên CRL thay vì OCSP | **Không** vô hiệu hóa OCSP fallback nếu chưa có `NO_FALLBACK` |
| `NO_FALLBACK` | Tắt cơ chế dự phòng thứ hai | Chọn cùng `PREFER_CRLS` để chỉ ưu tiên CRL mà không chuyển OCSP |
| `ONLY_END_ENTITY` | Chỉ kiểm tra thu hồi của chứng chỉ leaf | Bỏ phần kiểm tra revocation các CA intermediate, cân nhắc rủi ro |
| `SOFT_FAIL` | Cho phép bỏ qua một số lỗi không xác định trạng thái từ mạng/OCSP `tryLater`/`internalError` theo Javadoc | **Không** biến `revoked` thành `good`; việc bỏ qua unknown có rủi ro |

Theo Java SE 17 API, khi dùng checker cụ thể, **OCSP là cơ chế ưu tiên mặc định, CRL là fallback**; `PREFER_CRLS` đảo thứ tự, `NO_FALLBACK` tắt fallback. Đây là contract của **checker API**; phần **thu hồi mặc định do system/security properties** của Oracle/SUN provider lại có cấu hình legacy riêng ở mục 11, nên không được đánh đồng hai đường cấu hình.

**Đặt options trước khi add vào parameters**. `PKIXParameters.addCertPathChecker(checker)` clone checker, nên sửa biến `checker` **sau** khi add sẽ không làm parameters đã tạo đổi theo. Nếu cần thay policy, tạo checker/parameters mới cho operation tương ứng.

### `setRevocationEnabled(false)` có nghĩa gì?

`PKIXParameters` mặc định `isRevocationEnabled()==true`. Nếu gọi `setRevocationEnabled(false)`, bạn tắt **default revocation checking mechanism** của provider. Nhưng khi **thêm một `PKIXRevocationChecker` rõ ràng** bằng `addCertPathChecker`, Javadoc quy định checker đó **vẫn được dùng** bất kể flag `RevocationEnabled`.

Điều này giải thích snippet trong demo offline:

```java
params.setRevocationEnabled(false); // Tắt checker mặc định, KHÔNG tắt checker thêm sau.
params.addCertPathChecker(checker);  // Checker này vẫn thực hiện kiểm tra.
```

Mục đích là tránh hai con đường kiểm tra trùng lặp, đồng thời chủ động kiểm soát nguồn CRL/options. **Không copy `setRevocationEnabled(false)` mà bỏ `addCertPathChecker`**: lúc đó bạn có thể vô tình **vô hiệu hóa mọi kiểm tra thu hồi** trong pipeline đó.

### `SOFT_FAIL` không tương đương “tự động an toàn”

Theo Java SE 17 API, `SOFT_FAIL` chỉ bỏ qua một số trường hợp **không thể lấy CRL/OCSP vì lỗi mạng** hoặc OCSP responder trả `internalError`/`tryLater`. Nếu cho phép fallback, thường cả hai cơ chế phải thất bại theo các điều kiện soft-fail tương ứng thì mới được cho qua theo option này. **Bằng chứng REVOKED hợp lệ không được bỏ qua.**

`checker.getSoftFailExceptions()` có thể liệt kê exception đã bị bỏ qua khi kiểm tra, nhưng lưu ý checker bị **clone** khi thêm vào `PKIXParameters`; đừng mặc định gọi getter trên **biến checker ban đầu** sau validate sẽ phản ánh internal instance mà provider đã dùng. Khi cần telemetry chính xác, thiết kế logging/instrumentation ở layer kiểm chứng, thử nghiệm provider và xác nhận số liệu trên môi trường thật.

Đối với high-assurance authentication, key signing/cấp quyền nhạy cảm, nên có chính sách **fail-closed** khi không thể xác minh revocation, kèm timeout/UX/retry có kiểm soát. Với một số hệ thống cần availability, soft-fail có thể là quyết định chấp nhận rủi ro, nhưng phải đo lường, giới hạn và phân biệt rõ trạng thái unknown. Không dùng soft-fail để “sửa” CA/CRL cấu hình sai.

## 8. Java 17: ví dụ không cần mạng để kiểm tra cấu hình checker

**`RevocationCheckerOptionsDemo.java`** có thể chạy ngay trên JDK 17+ có PKIX provider. Nó chỉ lấy checker, đặt options và một responder URI minh họa `.invalid`; **không làm request OCSP hay xác minh certificate nào**.

```java
import java.net.URI;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXRevocationChecker;
import java.util.EnumSet;

public final class RevocationCheckerOptionsDemo {
    public static void main(String[] args) throws Exception {
        CertPathValidator validator = CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();

        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK));
        checker.setOcspResponder(URI.create("https://ocsp.example.invalid"));

        System.out.println("prefersCRL=" + checker.getOptions()
                .contains(PKIXRevocationChecker.Option.PREFER_CRLS));
        System.out.println("fallbackDisabled=" + checker.getOptions()
                .contains(PKIXRevocationChecker.Option.NO_FALLBACK));
        System.out.println("softFailEnabled=" + checker.getOptions()
                .contains(PKIXRevocationChecker.Option.SOFT_FAIL));
        System.out.println("responderConfigured=" +
                (checker.getOcspResponder() != null));
        System.out.println("noNetworkRequestWasSent=true");
    }
}
```

```bash
javac -encoding UTF-8 RevocationCheckerOptionsDemo.java
java RevocationCheckerOptionsDemo
```

**Stdout đã kiểm tra:**

```text
prefersCRL=true
fallbackDisabled=true
softFailEnabled=false
responderConfigured=true
noNetworkRequestWasSent=true
```

Bài học chính:

1. `getRevocationChecker()` phải được gọi từ PKIX validator tương thích.
2. `EnumSet.of(PREFER_CRLS, NO_FALLBACK)` chọn **CRL-only** cho checker trong ví dụ; OCSP responder URI đã đặt nhưng **sẽ không được sử dụng** nếu checker chạy chỉ với CRL.
3. `SOFT_FAIL` **không được bật**: nếu không xác định được trạng thái thì phương thức kiểm tra path sẽ không tự xem đó là thành công.
4. Các getter chỉ xác minh cấu hình **chưa phải kết quả bảo mật**: chưa có `PKIXParameters`, `CertPath`, trust anchor, CRL hay response. Dòng `noNetworkRequestWasSent=true` là khẳng định do code chỉ gọi setter/getter, không chứng minh hệ thống OCSP endpoint hoạt động.
5. Địa chỉ `example.invalid` **không phải** responder thật; khi demo lab `CRL-only`, không gửi network request đến URI đó.

## 9. Java 17: xác minh đường dẫn thực sự với CRL sạch và CRL thu hồi

Ví dụ thứ hai **`OfflineCrlValidationDemo.java`** nhận bốn file **của CA lab do bạn quản lý**: `root.pem` (trust anchor), `leaf.pem` (chứng chỉ do root cấp), `clean.crl` (CRL do root ký không thu hồi leaf) và `revoked.crl` (CRL do root ký, chứa serial leaf).

**Điều kiện dữ liệu đầu vào:** CA phải có basicConstraints CA=true và quyền ký CRL theo KeyUsage khi những ràng buộc này được áp dụng. Leaf phải do root tương ứng ký; CRL phải đúng issuer, còn thời hạn và có chữ ký hợp lệ. Đây là **fixture kiểm thử offline**, không phải một hệ thống tin cậy ngoài đời; `root.pem` được ứng dụng test tự chọn là anchor.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.*;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;

public final class OfflineCrlValidationDemo {
    private static X509Certificate certificate(String file) throws Exception {
        try (InputStream input = Files.newInputStream(Path.of(file))) {
            return (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(input);
        }
    }

    private static X509CRL crl(String file) throws Exception {
        try (InputStream input = Files.newInputStream(Path.of(file))) {
            return (X509CRL) CertificateFactory.getInstance("X.509")
                    .generateCRL(input);
        }
    }

    private static String evaluate(X509Certificate root, X509Certificate leaf,
            X509CRL list) throws Exception {
        list.verify(root.getPublicKey());

        CertPath chain = CertificateFactory.getInstance("X.509")
                .generateCertPath(List.of(leaf));

        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        params.setRevocationEnabled(false);
        params.addCertStore(CertStore.getInstance("Collection",
                new CollectionCertStoreParameters(List.of(list))));

        CertPathValidator validator = CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();
        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK));
        params.addCertPathChecker(checker);

        try {
            validator.validate(chain, params);
            return "ACCEPT";
        } catch (CertPathValidatorException e) {
            if (e.getReason() ==
                    CertPathValidatorException.BasicReason.REVOKED) {
                return "REVOKED";
            }
            if (e.getReason() ==
                    CertPathValidatorException.BasicReason
                            .UNDETERMINED_REVOCATION_STATUS) {
                return "UNKNOWN";
            }
            throw e;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 4) {
            System.err.println(
                    "Usage: java OfflineCrlValidationDemo root.pem leaf.pem clean.crl revoked.crl");
            return;
        }

        X509Certificate root = certificate(args[0]);
        X509Certificate leaf = certificate(args[1]);
        X509CRL clean = crl(args[2]);
        X509CRL revoked = crl(args[3]);

        System.out.println("issuerMatches=" +
                clean.getIssuerX500Principal()
                        .equals(root.getSubjectX500Principal()));
        System.out.println("cleanListsLeaf=" +
                (clean.getRevokedCertificate(leaf.getSerialNumber()) != null));
        System.out.println("revokedListsLeaf=" +
                (revoked.getRevokedCertificate(leaf.getSerialNumber()) != null));
        System.out.println("cleanPath=" + evaluate(root, leaf, clean));
        System.out.println("revokedPath=" + evaluate(root, leaf, revoked));
    }
}
```

Biên dịch và chạy khi đã có **bộ bốn file tương ứng**:

```bash
javac -encoding UTF-8 OfflineCrlValidationDemo.java
java OfflineCrlValidationDemo root.pem leaf.pem clean.crl revoked.crl
```

**Stdout đã được kiểm tra trên bộ chứng chỉ/CRL lab sinh riêng cho ví dụ:**

```text
issuerMatches=true
cleanListsLeaf=false
revokedListsLeaf=true
cleanPath=ACCEPT
revokedPath=REVOKED
```

**Đọc code theo đúng tầng kiểm tra:**

- `CertificateFactory` parse `root.pem`, `leaf.pem` và hai CRL từ file. Không mở kết nối CA hoặc OCSP.
- `crl.getRevokedCertificate(serial)` minh họa **membership**: CRL sạch không chứa serial, CRL revoked có chứa. Đây chỉ là quan sát, không tự xác minh PKIX.
- `list.verify(root.getPublicKey())` kiểm tra chữ ký CRL bằng khóa của root **đã được ứng dụng chọn làm trust anchor**. Nếu CRL do khóa khác ký không có ủy quyền, ví dụ ngắn này không phải mô hình cho mọi trường hợp CRL gián tiếp/ủy quyền; hãy dùng validation PKIX phù hợp với CA thật.
- `CertPath` gồm đúng **leaf**, vì **root là `TrustAnchor` riêng**, không được đưa root vào danh sách chain.
- `CollectionCertStoreParameters(List.of(list))` đưa CRL đã đọc vào PKIX validator, không phụ thuộc kết nối đến CDP. `PREFER_CRLS + NO_FALLBACK` bảo đảm checker dùng CRL thay vì OCSP.
- `params.setRevocationEnabled(false)` tắt **default mechanism**, nhưng `params.addCertPathChecker(checker)` đăng ký checker explicit vẫn hoạt động theo Java API; cả **ACCEPT** và **REVOKED** thực sự được thử trên PKIX engine.
- `validate` có thể ném `CertPathValidatorException`. Chỉ hai lý do đã được phân loại trong ví dụ: `REVOKED` và `UNDETERMINED_REVOCATION_STATUS`; các lỗi như chữ ký certificate, constraint hoặc thuật toán không hợp lệ được **ném lại**, không bị che thành “không thu hồi”.
- `cleanPath=ACCEPT` chỉ có nghĩa **PKIX path với trust anchor/parameters của lab vượt qua kiểm tra**. Nó không chứng minh hostname/TLS identity, quyền truy cập hay một CA ngoài đời đã đáng tin.

### Nếu file CRL không hợp lệ thì sao?

Có thể gặp `CRLException`, `SignatureException`, `InvalidKeyException` hoặc `CertPathValidatorException` tùy lỗi và bước xảy ra. Không catch tổng quát `Exception` rồi trả `ACCEPT`. Khi CRL không dùng được, bảo đảm **fail theo policy**; không tự diễn giải “không đọc được CRL” thành “CRL sạch”.

## 10. Chuẩn bị fixture lab để thử CRL thu hồi

Bài code offline cần bốn file. Một CA test do bạn tự tạo có thể sinh `root.pem`, cấp `leaf.pem`, tạo một CRL sạch và CRL chứa serial của leaf.

**Bước A — tạo CA và certificate leaf bằng lệnh `keytool` chuẩn** (giả định password lab đã được cấp an toàn dưới biến môi trường `LAB_PASS`):

```bash
# Tạo key pair CA cho lab; KHÔNG đưa CA này vào truststore production.
keytool -genkeypair -alias ca -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Test Root CA" -validity 30 -ext "BC:critical=ca:true" -ext "KU:critical=keyCertSign,cRLSign" -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS

# Xuất chứng chỉ công khai CA.
keytool -exportcert -rfc -alias ca -file root.pem -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS

# Tạo private key và CSR của chứng chỉ leaf lab.
keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=leaf.example.invalid" -validity 30 -keystore leaf.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS
keytool -certreq -alias leaf -file leaf.csr -keystore leaf.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS

# CA lab ký CSR và xuất leaf.pem.
keytool -gencert -alias ca -infile leaf.csr -outfile leaf.pem -rfc -validity 30 -ext "KU:critical=digitalSignature" -ext "EKU=serverAuth" -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS

# Xem serial leaf và trường issuer.
keytool -printcert -file leaf.pem
```

Những lệnh này đã được chạy thành công trong môi trường lab của bài. Một certificate `leaf.pem` có thể chưa đáp ứng mọi đòi hỏi của một CA/TLS sản phẩm thực, ví dụ name/SAN, CRLDP/AIA, certificate policies và quy trình trust thực tế. Vì đây là bài **revocation offline**, `OfflineCrlValidationDemo` không thực hiện hostname check.

**Bước B — có CRL do CA lab ký:**

- **Ưu tiên CA test tool của bạn** để phát hành một CRL mới không có revoked entry và một CRL có revoked entry của leaf, bảo đảm issuer/chữ ký/`thisUpdate`/`nextUpdate` hợp lệ. Với OpenSSL CA, tạo CRL theo cấu hình CA test và database revocation của nó; với CA enterprise, dùng chức năng quản lý revocation thử nghiệm.
- **Tùy chọn chỉ cho môi trường JDK có lệnh `keytool -gencrl`**: một số bản JDK có tiện ích không được liệt kê trong mọi trang man page public; đã xác nhận trên môi trường JDK dùng thử. Có thể tạo `clean.crl` và `revoked.crl` với CA lab:

```bash
# Chỉ khi "keytool -gencrl -help" trên JDK của bạn báo hỗ trợ.
keytool -gencrl -alias ca -file clean.crl -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS

# SERIAL_DEC là serial leaf trong hệ thập phân (KHÔNG phải chuỗi hex).
# Thay SERIAL_DEC bằng giá trị tính từ Serial number của leaf.pem.
keytool -gencrl -alias ca -id SERIAL_DEC:1 -file revoked.crl -keystore ca.p12 -storetype PKCS12 -storepass:env LAB_PASS -keypass:env LAB_PASS
```

`keytool -printcert` thường hiển thị serial bằng **hexadecimal** (ví dụ `7d52...`), còn `-id` của tiện ích lab này nhận **số serial thập phân**. Khi dùng JDK hỗ trợ, chuyển hex sang decimal trước khi thay `SERIAL_DEC`. Ví dụ snippet trong JShell:

```java
import java.math.BigInteger;
new BigInteger("7d52d72e6d72b894", 16).toString();
// Ví dụ này in "9030516797235968148" cho serial hex trên.
```

**Ví dụ serial trên chỉ là số minh họa**, mỗi chứng chỉ mới có serial khác. `:1` là revocation reason code của chức năng lab này. Vì `-gencrl` không nằm trong mọi tài liệu chính thức `keytool`, **không phụ thuộc vào lệnh này trong quy trình sản xuất** và không coi nó là một CA revocation management system. Nếu JDK không hỗ trợ, dùng công cụ CA chuẩn phát hành CRL.

**Bước C — kiểm tra fixture:** dùng `keytool -printcrl -file clean.crl` và `-printcrl -file revoked.crl` để xem nội dung, sau đó chạy chương trình. Xác minh đúng CA issuer, serial của leaf trong CRL thứ hai và độ tươi trước khi dùng. Các file chỉ để test và phải được tạo/lưu ở **thư mục lab riêng**, mật khẩu lab không phải credential thật.

## 11. Tích hợp với `PKIXParameters` và dữ liệu CRL/OCSP

### Truyền CRL vào checker qua `CertStore`

Một `CertStore` kiểu `Collection` là cách tiện dụng để kiểm thử offline (đã dùng ở mục 9). Với nhiều CRL và intermediate certificates, có thể thêm vào collection:

```java
CertStore store = CertStore.getInstance(
        "Collection",
        new CollectionCertStoreParameters(
                List.of(intermediateCert, currentCrl)));
params.addCertStore(store);
```

Đây là snippet giả định `intermediateCert`, `currentCrl` và `params` đã được khai báo đúng kiểu; cần import `java.security.cert.*` và `java.util.List`. `CertStore` giúp PKIX tìm certificate/CRL, không có nghĩa mọi object thêm vào collection đều được tin. PKIX vẫn phải kiểm tra issuer, signature, constraints và thời điểm theo thuật toán của provider.

### Cấu hình OCSP responder tường minh

```java
PKIXRevocationChecker checker =
        (PKIXRevocationChecker)
                CertPathValidator.getInstance("PKIX").getRevocationChecker();

checker.setOcspResponder(URI.create("https://ocsp.example.org"));
checker.setOptions(EnumSet.noneOf(PKIXRevocationChecker.Option.class));
params.addCertPathChecker(checker);
```

Đây là snippet minh họa **không độc lập**, trong đó `params` là `PKIXParameters` đã có trust anchors và chain đang được validate; `example.org` là placeholder URL tài liệu **không phải service thật**. Với checker mặc định (không `PREFER_CRLS`), API ưu tiên OCSP, có thể dùng CRL fallback. Responder thực phải được CA/protocol phê duyệt; nếu cần delegated responder, sử dụng `setOcspResponderCert(X509Certificate)` và tin cậy responder theo quy tắc RFC/PKIX tương ứng.

Có thể đưa OCSP response đã nhận được (đã được hệ thống fetch/staple đúng cách) vào `checker.setOcspResponses(Map<X509Certificate, byte[]>)`. Đây là **DER-encoded OCSP response bytes theo certificate**, không phải mảng boolean `good`. Engine vẫn cần kiểm tra chữ ký, responder authority, CertID và time validity theo implementation. Không tự tạo `good` bằng cách đưa chuỗi “true” vào map.

**Phân biệt:** `setOcspResponder(URI)` chỉ chọn endpoint, **không khẳng định request đã được gửi hoặc response đã được kiểm chứng**. Chỉ một lần `validator.validate(certPath,params)` thực hiện actual validation (với dữ liệu và cấu hình hợp lệ).

### Sự khác nhau giữa explicit checker và security properties

Theo Java 17 PKI Programmer's Guide của Oracle/SUN implementation:

- `PKIXParameters.setRevocationEnabled(true)` bật **default revocation mechanism** của provider (mặc định là true khi tạo `PKIXParameters`).
- Một số cấu hình provider mặc định dùng security property `ocsp.enable` (trong `java.security` hoặc `Security.setProperty`): có thể khiến default mechanism dùng OCSP rồi CRL fallback khi đã bật revocation. Nếu property không bật, con đường mặc định có thể dùng CRL. 
- `PKIXRevocationChecker` được lấy trực tiếp từ PKIX validator có **contract riêng**: mặc định ưu tiên OCSP và fallback CRL theo Javadoc, bất kể cách cấu hình legacy default mechanism.

Do đó không nói “OCSP mặc định luôn bật trong toàn bộ Java” hoặc “chỉ cần `ocsp.enable=true` là mọi TLS client đã check CRL/OCSP”. **Phải xác định API path và provider cụ thể**; cách cấu hình trong một framework có thể dùng trust manager/builder khác hẳn ví dụ manual `CertPathValidator`.

### CRL Distribution Points và truy vấn mạng

Oracle PKI Programmer's Guide mô tả system property `com.sun.security.enableCRLDP=true` để bật cách tự tìm CRL theo CDP trong SUN provider; một số cấu hình tắt mặc định để tương thích. Khi đã đưa CRL qua `CertStore` và dùng `PREFER_CRLS`, bài demo **không cần mạng**, điều này giúp test có kết quả ổn định.

Tính năng tự fetch CDP/OCSP cần xem xét:

- **Network egress** và proxy: responder có thể là host ngoài Internet.
- **Timeout và retry**: thư viện có defaults riêng; `com.sun.security.crl.timeout` là ví dụ property được tài liệu Oracle nêu cho CRL, có tính chất provider-specific.
- **SSRF và metadata leakage**: certificate có thể do peer gửi, URL có thể không an toàn. Bật tự động truy vấn URL từ chứng chỉ chưa tin cần có boundary egress.
- **Cache và đồng hồ**: dữ liệu cached chỉ dùng khi phù hợp freshness/clock skew. Ngắt clock NTP có thể làm một response bị đánh giá không hợp lệ.
- **Phạm vi check**: cert lá, intermediate và chain; không chỉ một certificate tiện xem đầu tiên.

Tránh chỉnh `java.security` global chỉ để làm một test nếu có thể cấu hình qua API riêng. Việc thay security property runtime có thể ảnh hưởng nhiều component và vẫn không có hiệu lực nếu implementation đã cache settings. Test bằng một process chuyên biệt trong lab, không bật vào cả cụm production trước khi có kế hoạch.

## 12. Phân loại lỗi `CertPathValidatorException`

Đối với đường PKIX đã cấu hình revocation, `CertPathValidator.validate(...)` có thể ném `CertPathValidatorException`. Đọc `getReason()`, `getIndex()` và `getCause()` thay vì chỉ in message:

| Reason (ví dụ) | Ý nghĩa | Chính sách ứng dụng |
| --- | --- | --- |
| `BasicReason.REVOKED` | Chứng chỉ được xác nhận bị thu hồi | **Từ chối**; không fallback thành success |
| `BasicReason.UNDETERMINED_REVOCATION_STATUS` | Thiếu bằng chứng xác định trạng thái thu hồi | Từ chối hoặc soft-fail **nếu policy cho phép và được đo lường** |
| `BasicReason.EXPIRED` | Certificate hết hạn | Từ chối theo policy hiện hành; không phải “CRL lỗi” |
| `BasicReason.NOT_YET_VALID` | Chứng chỉ chưa đến thời gian hợp lệ | Từ chối |
| `BasicReason.INVALID_SIGNATURE` | Signature của certificate/path không phù hợp | Từ chối; không hạ cấp sang soft-fail |
| `BasicReason.ALGORITHM_CONSTRAINED` | Algorithm/key vi phạm security constraints | Từ chối, sửa policy/certificate chứ không bỏ check |
| `BasicReason.UNSPECIFIED` hoặc reason khác | Lỗi khác/cụ thể provider | Ghi nhận có kiểm soát và điều tra |

`getIndex()` là index certificate theo thứ tự `CertPath`, không phải row trong keystore. Giá trị `-1` có thể xảy ra khi lỗi không xác định được một chứng chỉ cụ thể. Không dùng `BasicReason.REVOKED` như cách phát hiện mọi trường hợp “invalid”; phạm vi của enum được phân biệt rõ.

**Code anti-pattern:**

```java
try {
    validator.validate(path, params);
    return true;
} catch (CertPathValidatorException error) {
    return true; // SAI: bỏ qua mọi thất bại, gồm REVOKED!
}
```

Snippet minh họa lỗi, không phải code được khuyên dùng; `validator`, `path` và `params` giả định đã khai báo. Nếu chính sách yêu cầu fail-closed, một lỗi revocation không rõ phải ngăn accept. Nếu có soft-fail được phê duyệt, chỉ cho qua đúng phân loại lỗi được policy chấp nhận, giới hạn thời gian/trạng thái và ghi telemetry.

## 13. Chính sách khi OCSP hoặc CRL unavailable

### Fail-closed / hard-fail

**Fail-closed** nghĩa là không cho phép hoạt động yêu cầu chứng chỉ tin cậy khi trạng thái thu hồi cần kiểm tra mà **không xác định được**. Lợi ích: không cho attacker vô hiệu hóa kiểm tra bằng cách chặn responder. Đánh đổi: một sự cố CA responder/egress có thể gây gián đoạn ứng dụng.

Các bước giảm ảnh hưởng: cache hợp lệ theo policy, CRL/OCSP fallback có xác minh, egress dự phòng, timeout hữu hạn, capacity planning, liveness/health monitoring, xử lý thông báo lỗi rõ ràng và runbook phục hồi.

### Soft-fail có kiểm soát

**Soft-fail** cho phép tiếp tục trong những tình huống đặc biệt **không xác định được** theo danh sách lỗi cho phép, nhưng chỉ khi đã chấp nhận rủi ro. Không phải `REVOKED`. Ví dụ một ứng dụng internet-facing có thể ưu tiên availability ở một số use case, nhưng hệ thống quản trị khóa, ký phát hành phần mềm hoặc internal mTLS nhạy cảm có thể đặt yêu cầu khác.

Nếu áp dụng `SOFT_FAIL`:

- Ghi lại **đã soft-fail** chứ không báo người vận hành “OCSP GOOD”.
- Đặt scope ứng dụng, endpoint/role và thời hạn policy rõ ràng.
- Tăng monitoring cho thời gian dài responder/CRL unavailable.
- Định nghĩa giới hạn cache TTL, retry/timeout và xử lý khi status thay đổi thành `REVOKED`.
- Xem lại security implications nếu một attacker có thể chủ động làm gián đoạn kết nối responder.

### Không có một cấu hình đúng cho mọi giao thức

| Bối cảnh | Vấn đề cần quyết định |
| --- | --- |
| mTLS nội bộ cho hệ thống quản trị/production key access | Tính toàn vẹn danh tính có thể ưu tiên hard-fail; bố trí revocation distribution nội bộ có sẵn cao |
| TLS client của ứng dụng công cộng | Cân bằng UX, OCSP availability, hiệu ứng responder outages, client/provider behavior |
| Ký số tài liệu/phần mềm dài hạn | Cần chứng cứ trạng thái tại **thời điểm ký**, timestamp/certification policy và lưu trữ OCSP/CRL evidence theo chuẩn áp dụng |
| Offline signing verification | Cần dữ liệu revocation đã thu thập từ trước và xác minh freshness/validation time phù hợp |
| Hệ thống không có kết nối mạng | Không thể “hỏi OCSP online” lúc verify; đưa CRL/OCSP evidence vào trust bundle hoặc thiết kế exception policy có phê duyệt |

Không vội nâng `SOFT_FAIL` thành mặc định trên toàn bộ máy chủ chỉ để giảm số lỗi log. Nếu revocation là yêu cầu bảo mật không thể nhượng bộ, Unknown phải được từ chối.

## 14. Tích hợp trong TLS/JSSE: đừng nhầm manual PKIX validation với handshake

Các ví dụ ở trên gọi `CertPathValidator` trực tiếp. Chúng **không tự thiết lập** cấu hình kiểm tra thu hồi cho:

- `HttpsURLConnection` / `java.net.http.HttpClient` đang sử dụng `SSLContext` mặc định.
- Server nhận mTLS qua `SSLServerSocket` hoặc framework.
- Ứng dụng dùng `X509TrustManager` riêng/được tạo qua `TrustManagerFactory`.
- Thư viện HTTP/TLS có trình xác minh riêng hoặc dùng native TLS stack.

Nếu TLS của ứng dụng cần revocation checking, phải cấu hình đúng **trust manager / PKIXBuilderParameters / CertPath policy** mà TLS stack sử dụng, kèm trust anchors, hostname verification và revocation options. Một cách tiếp cận tùy provider là khởi tạo `TrustManagerFactory` với `CertPathTrustManagerParameters` chứa `PKIXBuilderParameters` đã cấu hình; cần kiểm tra hỗ trợ của algorithm/provider và hành vi thực tế trước khi sử dụng.

Ví dụ khung cấu hình (snippet, không chạy độc lập):

```java
PKIXBuilderParameters params =
        new PKIXBuilderParameters(trustAnchors, targetSelector);
params.setRevocationEnabled(false);
params.addCertPathChecker(configuredRevocationChecker);

TrustManagerFactory tmf =
        TrustManagerFactory.getInstance("PKIX");
tmf.init(new CertPathTrustManagerParameters(params));
```

`trustAnchors`, `targetSelector`, `configuredRevocationChecker` là các đối tượng phải được tạo từ **nguồn tin cậy và policy đã phê duyệt**; ở một số provider, có thể phải cấu hình target constraints hoặc dùng các constructor khác. Không coi snippet là cách duy nhất cho mọi JSSE triển khai. Nếu dùng `SSLEngine` và custom trust manager, vẫn cần hostname verification/endpoint identification theo giao thức.

**Quan trọng:** các property như `ocsp.enable`, `com.sun.security.enableCRLDP` hoặc `-D...` không chứng minh điều gì cho TLS client/server cho đến khi bạn test end-to-end với certificate chưa thu hồi, đã thu hồi, responder timeout và certificate chain thiếu intermediate. Test bằng chính framework và JVM/runtime đưa lên production.

## 15. Kiểm thử và vận hành revocation checking

### Bộ test tối thiểu

| Test | Điều kiện | Kết quả được kỳ vọng khi hard-fail |
| --- | --- | --- |
| Happy path CRL | Leaf hợp lệ, CRL signed/fresh, không có serial | PKIX validate thành công |
| Revoked leaf | CA đưa leaf serial vào CRL hợp lệ | `REVOKED` và reject |
| Missing CRL + no OCSP | Không có nguồn xác định trạng thái | Không được accept trong hard-fail |
| Expired/stale CRL | `nextUpdate` đã qua hoặc freshness không đạt | Không coi dữ liệu cũ là bằng chứng GOOD |
| Wrong issuer CRL | CRL không do issuer được ủy quyền ký | Reject, không dùng membership |
| Forged CRL signature | Byte CRL bị sửa, chữ ký không hợp lệ | Reject hoặc fail validation theo provider |
| OCSP `good` hợp lệ | Đúng CertID, signature/responder trust, timestamp | Vượt qua **revocation layer**, tiếp tục các PKIX/TLS checks |
| OCSP `revoked` | Responder có thẩm quyền báo revoked | Reject dù có đường CRL fallback |
| OCSP `unknown` | Không có status đáng tin | Không coi unknown là good |
| OCSP network failure | Timeout/`tryLater` | Fallback nếu được phép và nguồn thay thế hợp lệ; ngược lại hard-fail |
| Chứng chỉ intermediate bị revoke | Intermediate nằm trong chain | Reject nếu policy kiểm tra CA cert |
| Kiểm tra chỉ leaf | `ONLY_END_ENTITY` | Xác định rõ rủi ro bỏ kiểm tra intermediate và test policy |
| Sai hostname/SAN | PKIX path có thể hợp lệ | TLS identity verifier vẫn phải reject |
| Thay JDK/provider | Provider khác, options/fetch/timeouts khác | Chạy lại integration tests |

Các test CRL/OCSP cần dữ liệu và responder **của môi trường lab**. Đừng tạo/chỉnh sửa CRL public CA hoặc sử dụng mTLS endpoint production làm đích thử tấn công; mục đích là tái tạo hành vi bảo mật trong môi trường bạn quản lý.

### Telemetry hữu ích, không lộ dữ liệu quá mức

- `algorithm=PKIX`, provider/JDK version, profile checker/options, loại nguồn (CRL/OCSP/cache/stapled), thời gian kiểm tra, timeout.
- Reason enum khi fail, certificate index, CA/trust anchor identifier theo policy, status responder (không log URL nhạy cảm nếu có rủi ro).
- Phân biệt **REVOKED / UNDETERMINED / OTHER_INVALID**. Ghi rõ số lần fallback và soft-fail được chấp nhận.
- Đo p50/p95/p99 latency và tỷ lệ lỗi mỗi issuer/responder để phát hiện sự cố nguồn thu hồi.
- Giới hạn log có chứa subject/SAN/serial và response bytes để tránh thu thập thông tin cá nhân/khóa/metadata quá mức.

Để debug trên Oracle/OpenJDK, có thể bật **chỉ trong môi trường kiểm soát**:

```bash
java -Djava.security.debug=certpath YourApplication
```

Đây là cơ chế debug của implementation; log có thể nhiều và chứa thông tin certificate/path. Không bật trên hệ thống thật trong thời gian dài khi chưa kiểm tra tác động logging/performance và dữ liệu nhạy cảm.

## 16. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| Chỉ kiểm tra `checkValidity()` rồi kết luận certificate trusted | Không xét chain, trust anchor, revocation, purpose | Dùng PKIX validation và verification tầng ứng dụng |
| `getRevokedCertificate(serial)==null` ⇒ GOOD ngay | CRL có thể stale, sai issuer, thiếu phạm vi hoặc giả mạo | Validate CRL/path và rule của RFC 5280 |
| Tạo trust anchor từ root CA do peer gửi | Attacker có thể tự phát hành CA giả | Trust anchor phải từ config/truststore đã phê duyệt |
| Đưa root vào `CertPath` rồi lại cấu hình như trust anchor | Hiểu sai path trust boundary | CertPath leaf/intermediates, anchor truyền riêng |
| Bật `setRevocationEnabled(false)` rồi quên checker | Vô hiệu hóa revocation theo đường mặc định | Đặt checker explicit hoặc giữ cơ chế mặc định theo policy |
| Set options sau `params.addCertPathChecker(checker)` | Parameters clone checker | Set đầy đủ trước khi add |
| Dùng `PREFER_CRLS` và tưởng không bao giờ hỏi OCSP | Vẫn có fallback mặc định | Dùng `NO_FALLBACK` nếu yêu cầu CRL-only |
| Dùng `SOFT_FAIL` và coi REVOKED được bỏ qua | Sai contract Java | REVOKED vẫn reject; soft-fail cho lỗi không xác định có giới hạn |
| Chỉ test CRL sạch, không test CRL revoked | Không chứng minh revocation thực sự hoạt động | Test cả CRL clean và revoked, xác minh reason |
| Dùng CRL từ issuer khác | Không đại diện trạng thái của cert | Match issuer/AKI/CRL scope và kiểm tra signature |
| Trộn OCSP response của serial/issuer khác | Status không áp dụng cho cert cần kiểm tra | Kiểm tra CertID, responder authority, freshness |
| Ký số OCSP response đúng nhưng responder không được ủy quyền | Signature đúng không đủ trust | Kiểm tra delegation/EKU, issuer và policy |
| Nhầm `unknown` thành `good` khi OCSP server down | Attacker có thể khai thác outage | Thực thi fail policy minh bạch, có telemetry |
| Bật CDP fetch không giới hạn egress | Rủi ro SSRF, latency, data leakage | Network policy, proxy, timeout, allowlist khi phù hợp |
| Coi `PKIXRevocationChecker` của manual validator đã bật cho toàn JSSE | Pipeline TLS có thể khác | Kiểm thử trust-manager/framework thực |
| Tin `getSoftFailExceptions` trên checker ban đầu luôn là checker đã dùng | `PKIXParameters` clone checker | Instrumentation/provider-aware diagnostics |
| Không kiểm tra intermediate revocation | CA trung gian có thể đã bị thu hồi | Tránh `ONLY_END_ENTITY` trừ khi có lý do |
| Không cập nhật chứng cứ revocation của chữ ký lưu dài hạn | Trạng thái hôm nay khác thời điểm ký lịch sử | Thiết kế timestamp/archival validation theo tiêu chuẩn phù hợp |
| Hard-fail nhưng không có cache/timeout | Sự cố CA gây outage lớn | Cache có hạn, monitoring, fallback hợp lệ, budget |
| Test với CA/CRL thật không được phép | Gây rủi ro vận hành | Sử dụng fixture và responder riêng trong môi trường lab |

## 17. Bài tập tự đánh giá

1. **Phân biệt trạng thái:** một cert còn hạn nhưng có serial trong CRL hợp lệ. Kết quả phải là gì? Nếu không thể tải CRL và OCSP cũng timeout thì khác `REVOKED` thế nào?
2. **Đọc CRL:** chỉ ra issuer, `thisUpdate`, `nextUpdate`, revoked serial và lý do trên CRL lab. Vì sao đọc `revokedCertificates` mà không xác minh CRL issuer/signature/freshness là không đủ?
3. **Hiểu OCSP:** tại sao `good` khác “TLS hostname và chain hoàn toàn hợp lệ”? Những điều kiện nào phải kiểm tra đối với delegated responder?
4. **So sánh:** thiết kế CRL distribution cho ứng dụng có hàng triệu client offline; sau đó đề xuất khi nào OCSP/stapling giúp hơn.
5. **Thực hành API:** chạy `RevocationCheckerOptionsDemo` và đổi `PREFER_CRLS` thành chỉ `NO_FALLBACK`. Cơ chế nào trở thành ưu tiên? Tại sao chỉ đặt OCSP URI không đồng nghĩa request đã được gửi?
6. **Thực hành PKIX:** với `OfflineCrlValidationDemo`, giải thích vì sao `root` là trust anchor, `leaf` ở `CertPath` và `params.setRevocationEnabled(false)` không tắt checker explicit.
7. **Revoked test:** tạo CRL có serial leaf, xác nhận `revokedListsLeaf=true` và `revokedPath=REVOKED`. Nếu sửa một byte CRL, outcome phải là accept hay reject?
8. **Policy:** đặt `SOFT_FAIL` trên một endpoint mTLS high-assurance có yêu cầu thu hồi nghiêm ngặt. Trình bày rủi ro và đề xuất runbook khác nếu responder unavailable.
9. **Intermediates:** nếu intermediate CA bị thu hồi nhưng leaf chưa bị liệt kê, tại sao `ONLY_END_ENTITY` có thể nguy hiểm?
10. **SSRF:** certificate leaf có URL CDP trỏ vào địa chỉ mạng nội bộ của server. Thiết kế egress policy và timeout khi ứng dụng dùng CRLDP auto-fetch.
11. **JSSE:** đã chạy demo manual nhưng HTTPS client vẫn chấp nhận cert đã thu hồi. Có thể thiếu bước nào? Cần kiểm thử tầng trust manager và hostname verification ra sao?
12. **Archival:** một tài liệu được ký 5 năm trước, certificate ký hiện nay đã hết hạn. Vì sao xác minh chữ ký lịch sử cần có validation time/timestamp và revocation evidence lưu trữ theo chuẩn riêng?
13. **Phân tích exception:** phân biệt `BasicReason.REVOKED`, `UNDETERMINED_REVOCATION_STATUS`, `INVALID_SIGNATURE` và `ALGORITHM_CONSTRAINED`. Trường hợp nào không thể biến thành thành công bằng retry OCSP?
14. **Đánh giá vận hành:** xác định metric về tỷ lệ revoked, unknown, soft-fail, fallback và latency theo responder. Những metric nào sẽ kích hoạt rollback cấu hình?

**Tiêu chí hoàn thành:** bạn giải thích đúng **revoked khác unknown**, biết CRL/OCSP phải được kiểm tra bằng nguồn tin cậy và độ tươi, tạo và cấu hình `PKIXRevocationChecker` theo options chính xác, xử lý path với trust anchor ngoài CertPath, kiểm thử được accept/revoked trên fixture, và hiểu rằng cần tích hợp/kiểm chứng riêng trên TLS stack production.

## Tài liệu chính thức

- [Java SE 17 — `PKIXRevocationChecker` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): lựa chọn OCSP/CRL, fallback, setOcspResponder và các checker methods.
- [Java SE 17 — `PKIXRevocationChecker.Option`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.Option.html): `PREFER_CRLS`, `NO_FALLBACK`, `ONLY_END_ENTITY`, `SOFT_FAIL`.
- [Java SE 17 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, CertStore, revocation enabled và thêm custom checker.
- [Java SE 17 — `CertPathValidatorException.BasicReason`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.BasicReason.html): `REVOKED`, `UNDETERMINED_REVOCATION_STATUS` và những lý do khác.
- [Oracle Java 17 — PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): PKIX, CertStore, CRL Distribution Points và OCSP properties của SUN provider.
- [Java SE 17 — `X509CRL`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509CRL.html), [`CertificateFactory`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html), [`CertStore`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertStore.html).
- [RFC 5280 — X.509 Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280), đặc biệt thuật toán path/CRL processing.
- [RFC 6960 — Online Certificate Status Protocol](https://www.rfc-editor.org/rfc/rfc6960), thay thế RFC 2560 và mô tả OCSP status/responses.
- [Java SE 17 — `keytool`](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): phát hành certificate lab và lệnh đọc CRL.
