# PKIXRevocationChecker, OCSP và CRL trong Java

**Chủ đề cha:** Mật mã ứng dụng. **Trọng tâm:** Kiểm tra chứng thư X.509 đã bị thu hồi hay chưa trong quá trình xác thực đường dẫn PKIX bằng Java 8+, sử dụng `PKIXRevocationChecker`, `OCSP` và `CRL`. Bài học phân biệt cơ chế mặc định của provider với checker được cấu hình tường minh, giải thích các tùy chọn `PREFER_CRLS`, `NO_FALLBACK`, `ONLY_END_ENTITY`, `SOFT_FAIL`, cách lấy thông tin OCSP/CRL, và cách vận hành kiểm tra thu hồi an toàn.

**Phiên bản:** `PKIXRevocationChecker`, `CertPathValidator`, `PKIXParameters`, `CertStore` và các tùy chọn trong bài có từ Java 8, vẫn được hỗ trợ trong Java hiện hành. Các chương trình hoàn chỉnh dùng **Java 17+**. Nội dung tham chiếu Java SE 26 và các chuẩn IETF còn hiệu lực; `RFC 6960` đã thay thế `RFC 2560` cho giao thức OCSP.

> **Điểm cần nhớ:** Chữ ký hợp lệ và chứng thư còn hạn **chưa đủ** để kết luận chứng thư vẫn đáng tin. CA có thể thu hồi chứng thư trước ngày hết hạn. PKIX revocation checking bổ sung bước hỏi trạng thái qua OCSP hoặc kiểm tra CRL. `PKIXRevocationChecker` cho phép chọn cơ chế, thứ tự ưu tiên và chính sách khi không lấy được dữ liệu trạng thái. `SOFT_FAIL` chỉ nới lỏng một số lỗi kết nối/khả dụng được chỉ định; nó không biến một chứng thư có trạng thái `revoked` thành hợp lệ.

## 1. Vì sao cần kiểm tra thu hồi chứng thư?

Một chứng thư X.509 thường có:
- Chủ thể (subject) và khóa công khai.
- Nhà phát hành (issuer), thường là CA.
- Số sê-ri (serial number).
- Thời điểm bắt đầu và kết thúc hiệu lực (`notBefore`, `notAfter`).
- Chữ ký số của issuer.
- Các extension như `KeyUsage`, `BasicConstraints`, `AuthorityInformationAccess` và `CRLDistributionPoints`.

Chữ ký số xác nhận nội dung chứng thư được ký bởi khóa của issuer. Khoảng thời gian hiệu lực xác nhận chứng thư chưa đến ngày bắt đầu hoặc quá ngày kết thúc. Nhưng CA vẫn có thể phải thu hồi chứng thư trong khoảng thời gian đó, chẳng hạn:

- Khóa riêng của chủ thể bị lộ hoặc nghi ngờ bị sao chép.
- Chủ thể thay đổi vai trò hoặc không còn được phép dùng chứng thư.
- CA cấp chứng thư nhầm thông tin hoặc sai chính sách.
- Hệ thống phát hiện một chứng thư được cấp không đúng quy trình.
- Chứng thư bị thay thế và CA muốn vô hiệu hóa chứng thư cũ.

Nếu ứng dụng chỉ kiểm tra chữ ký và ngày hết hạn, chứng thư đã bị thu hồi vẫn có thể vượt qua các bước đó. Vì vậy xác thực PKIX thường cần kiểm tra trạng thái thu hồi theo chính sách bảo mật của ứng dụng.

### 1.1. Bốn câu hỏi khác nhau khi xác thực

| Kiểm tra | Câu hỏi | Cơ chế thường dùng |
| --- | --- | --- |
| Path building | Có tìm được chuỗi issuer nối chứng thư đích tới trust anchor không? | `CertPathBuilder` |
| Path validation | Chữ ký, thời hạn, constraints, policy và các quy tắc PKIX có hợp lệ không? | `CertPathValidator` |
| Revocation | Chứng thư trong đường dẫn có bị thu hồi không? | OCSP hoặc CRL qua PKIX |
| Identity/hostname | Chứng thư có đại diện đúng máy chủ mà client kết nối không? | Kiểm tra tên máy chủ trong TLS/JSSE |

Các bước này liên quan nhưng không thay thế nhau. Một chứng thư không bị thu hồi vẫn có thể hết hạn, sai hostname, sai EKU, sai policy hoặc không nối được tới trust anchor. Ngược lại, một chứng thư có chữ ký và hostname đúng vẫn có thể bị thu hồi.

### 1.2. Certification path và trust anchor

Một đường dẫn X.509 thông thường có thứ tự từ chứng thư đích về phía CA:

```text
End-entity certificate
        |
        v
Intermediate CA certificate
        |
        v
Intermediate CA certificate
        |
        v
Trust anchor (CA được ứng dụng tin cậy)
```

`CertPath` thường chứa chứng thư đích và các intermediate cần thiết. Trust anchor được cung cấp riêng qua `PKIXParameters`; chứng thư trust anchor không được đưa vào `CertPath` theo quy ước X.509 PKIX.

Revocation checking tập trung vào các chứng thư thuộc đường dẫn mà provider cần xác minh. Trust anchor được ứng dụng tin cậy trực tiếp thường không được xử lý như một chứng thư trung gian trong path; nếu tổ chức muốn thay đổi hoặc thu hồi một trust anchor, cần cập nhật trust store/trust policy tương ứng.

## 2. Hai nguồn dữ liệu trạng thái: CRL và OCSP

### 2.1. CRL — Certificate Revocation List

`CRL` là danh sách có chữ ký số, do CA hoặc một CRL issuer được ủy quyền phát hành. Danh sách chứa số sê-ri của những chứng thư đã bị thu hồi, cùng thông tin về issuer, thời gian và các extension liên quan.

Một CRL thường có:
- `issuer`: tên nhà phát hành CRL.
- `thisUpdate`: thời điểm trạng thái trong CRL được biết là đúng.
- `nextUpdate`: thời điểm dự kiến có bản cập nhật mới.
- `revokedCertificates`: danh sách entry gồm serial number, thời điểm thu hồi và lý do nếu có.
- `CRL number`: số phiên bản của CRL nếu extension được sử dụng.
- Chữ ký của CRL issuer.

Ứng dụng tải CRL, xác minh chữ ký và issuer, kiểm tra thời hạn cũng như phạm vi CRL, rồi tìm serial number của chứng thư cần xác minh. Nếu serial nằm trong CRL phù hợp, chứng thư bị thu hồi.

**CRL Distribution Points** là extension trong chứng thư, có thể chỉ ra nơi lấy CRL. Một CRL có thể chỉ bao phủ một nhóm chứng thư hoặc một số lý do thu hồi; không được coi bất kỳ CRL nào có thể tải về là bằng chứng đầy đủ cho mọi chứng thư.

CRL thường được cập nhật theo chu kỳ. Ưu điểm là nhiều chứng thư được kiểm tra từ một bản tải chung và có thể cache. Hạn chế là CRL có thể lớn, dữ liệu thu hồi mới có độ trễ cho tới lần phát hành tiếp theo, và client phải quản lý freshness/caching đúng cách.

### 2.2. OCSP — Online Certificate Status Protocol

`OCSP` cho phép client hỏi trạng thái của một chứng thư cụ thể từ OCSP responder. Thông tin định danh thường bao gồm issuer và serial number của chứng thư.

Một OCSP response có trạng thái:
- `good`: theo mức tối thiểu của RFC 6960, responder cho biết hiện không có chứng thư mang serial được hỏi bị thu hồi trong phạm vi kiểm tra. Trạng thái này **không nhất thiết chứng minh chứng thư từng được cấp**.
- `revoked`: chứng thư đã bị thu hồi; response có thể kèm thời điểm và lý do.
- `unknown`: responder không biết trạng thái, thường vì không quản lý issuer/chứng thư đó.

`unknown` không đồng nghĩa `good`. RFC 6960 cho phép client cân nhắc nguồn trạng thái khác, chẳng hạn CRL, khi responder trả `unknown`.

OCSP response còn có thông tin thời gian:
- `thisUpdate`: lần gần nhất trạng thái được xác nhận là đúng.
- `nextUpdate`: mốc dự kiến có dữ liệu mới; trường này có thể không xuất hiện.
- `producedAt`: thời điểm response được tạo.

Client phải xác minh response, chữ ký và thẩm quyền của responder, cũng như thời gian hiệu lực. Responder có thể được CA ủy quyền ký response bằng một chứng thư responder phù hợp. Không chấp nhận một chuỗi văn bản hoặc HTTP response chưa xác minh như bằng chứng trạng thái.

OCSP thường cung cấp thông tin mới hơn CRL và response cho một chứng thư thường nhỏ. Đổi lại, client cần kết nối tới responder, có thể làm lộ thông tin chứng thư mà client đang kiểm tra cho bên vận hành responder, và phải xử lý độ trễ/lỗi mạng.

### 2.3. So sánh CRL và OCSP

| Tiêu chí | CRL | OCSP |
| --- | --- | --- |
| Dữ liệu | Danh sách nhiều chứng thư bị thu hồi | Trạng thái cho từng chứng thư được hỏi |
| Nơi chỉ định | CRL Distribution Points | Authority Information Access (AIA), access method OCSP |
| Cập nhật | Theo chu kỳ phát hành CRL | Responder trả response cho request |
| Cache | Cache CRL theo issuer/phạm vi/thời gian | Cache response theo CertID và validity interval |
| Kích thước | Có thể lớn khi issuer cấp nhiều chứng thư | Thường nhỏ hơn cho một chứng thư |
| Tính riêng tư | Tải CRL có thể không tiết lộ chứng thư cụ thể đang được kiểm tra | Responder có thể thấy client đang hỏi chứng thư nào |
| Khi không kết nối được | Không lấy được CRL mới hoặc không có CRL phù hợp | Không lấy được response |
| Cách dự phòng | Có thể thử OCSP tùy policy | Có thể thử CRL tùy policy |

OCSP stapling là một cách phân phối response trong TLS: máy chủ gửi kèm response đã lấy trước, để client không phải tự hỏi responder trong mọi lần handshake. Đây là cơ chế tích hợp TLS, khác với việc chỉ cấu hình URL OCSP cho một lần xác thực PKIX độc lập. Nếu ứng dụng lấy được response DER từ một nguồn đã xác minh phù hợp, API `setOcspResponses` có thể nhận response theo từng chứng thư.

## 3. PKIXRevocationChecker trong Java

`java.security.cert.PKIXRevocationChecker` là một triển khai mở rộng của `PKIXCertPathChecker` dành cho kiểm tra trạng thái thu hồi trong PKIX.

Các API quan trọng:

| API | Vai trò |
| --- | --- |
| `CertPathValidator.getInstance("PKIX")` | Tạo validator cho thuật toán PKIX |
| `CertPathValidator.getRevocationChecker()` | Lấy revocation checker từ validator |
| `CertPathBuilder.getInstance("PKIX")` | Tạo builder cho thuật toán PKIX |
| `CertPathBuilder.getRevocationChecker()` | Lấy checker từ builder |
| `PKIXRevocationChecker.setOptions(...)` | Cấu hình lựa chọn revocation |
| `PKIXRevocationChecker.setOcspResponder(URI)` | Chỉ định OCSP responder |
| `PKIXRevocationChecker.setOcspResponderCert(...)` | Chỉ định chứng thư OCSP responder |
| `PKIXRevocationChecker.setOcspExtensions(...)` | Đặt extension trong OCSP request |
| `PKIXRevocationChecker.setOcspResponses(...)` | Cung cấp sẵn OCSP response dạng DER |
| `PKIXParameters.addCertPathChecker(...)` | Gắn checker vào tham số xác thực |
| `CertPathValidator.validate(...)` | Xác thực đường dẫn đã có |

Checker lấy từ validator hoặc builder phải được ép kiểu về `PKIXRevocationChecker` nếu provider trả đúng loại này:

```java
CertPathValidator validator =
        CertPathValidator.getInstance("PKIX");

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();
```

Đây là đoạn mã cấu hình, chưa thực hiện xác thực vì chưa có `CertPath` và trust anchors.

### 3.1. Trình tự cấu hình đúng

1. Tạo `CertPathValidator` hoặc `CertPathBuilder` cho PKIX.
2. Lấy `PKIXRevocationChecker` từ đối tượng đó.
3. Cấu hình options và thông tin OCSP/response trước khi gắn checker.
4. Tạo `PKIXParameters` hoặc `PKIXBuilderParameters` với trust anchors.
5. Thêm checker vào parameters.
6. Gọi `validate` hoặc `build`.

Ví dụ khung:

```java
CertPathValidator validator =
        CertPathValidator.getInstance("PKIX");

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));

PKIXParameters parameters = new PKIXParameters(trustAnchors);
parameters.addCertPathChecker(checker);

// Khi đã gắn checker tường minh, có thể tắt cơ chế revocation mặc định
// của provider để tránh chạy thêm một cơ chế mặc định song song.
parameters.setRevocationEnabled(false);

PKIXCertPathValidatorResult result =
        (PKIXCertPathValidatorResult)
                validator.validate(certPath, parameters);
```

Đây là **mẫu tích hợp trong ứng dụng**. `trustAnchors` là tập `TrustAnchor` đã cấu hình; `certPath` là đường dẫn X.509 theo thứ tự từ chứng thư đích về phía issuer, không chứa trust anchor. Mẫu chỉ chạy khi ứng dụng cung cấp đường dẫn và trust anchors thật.

### 3.2. Vì sao có thể đặt revocationEnabled=false khi đã gắn checker?

`PKIXParameters` mặc định bật cơ chế revocation mặc định của provider. Nhưng khi một `PKIXRevocationChecker` được thêm qua `addCertPathChecker` hoặc `setCertPathCheckers`, checker đó vẫn được dùng **bất kể** giá trị `revocationEnabled`.

Vì vậy, khi ứng dụng đã chọn checker tường minh, đặt:

```java
parameters.setRevocationEnabled(false);
```

sẽ tắt cơ chế mặc định của provider, trong khi checker tường minh vẫn thực hiện kiểm tra thu hồi. Đây là cách tránh chạy thêm cơ chế mặc định ngoài cấu hình mà ứng dụng đã chủ động chọn.

**Cảnh báo:** Nếu không gắn `PKIXRevocationChecker` hoặc checker thay thế nào, gọi `setRevocationEnabled(false)` sẽ tắt kiểm tra thu hồi mặc định. Không dùng dòng này như một cách "bỏ lỗi OCSP" trong production.

### 3.3. Checker được clone khi thêm vào parameters

`PKIXParameters.addCertPathChecker` clone checker để bảo vệ khỏi việc caller sửa đối tượng gốc sau đó. `getCertPathCheckers()` cũng trả các bản clone.

Do đó:
- Hãy gọi `setOptions`, `setOcspResponder` và các setter khác **trước khi** thêm checker.
- Đừng sửa checker ban đầu sau khi đã thêm và kỳ vọng parameters thay đổi.
- Đừng chia sẻ một checker có trạng thái cho nhiều luồng xác thực đồng thời.
- Tạo checker/parameters phù hợp cho từng lượt xác thực hoặc dùng cơ chế quản lý riêng đã kiểm chứng.

Các đối tượng trong API CertPath nói chung không được bảo đảm thread-safe trừ khi tài liệu chỉ rõ. `PKIXParameters` và các method instance của `CertPathValidator` cũng cần được dùng theo quy tắc thread-safety tương ứng.

## 4. Các Option của PKIXRevocationChecker

`PKIXRevocationChecker.Option` có bốn lựa chọn chính:

| Option | Ý nghĩa | Khi cân nhắc |
| --- | --- | --- |
| `PREFER_CRLS` | Ưu tiên CRL thay vì OCSP | Môi trường có hạ tầng CRL ổn định hoặc muốn giảm truy vấn OCSP |
| `NO_FALLBACK` | Tắt cơ chế dự phòng giữa OCSP và CRL | Khi policy yêu cầu chỉ dùng một nguồn trạng thái |
| `ONLY_END_ENTITY` | Chỉ kiểm tra chứng thư cuối (leaf/end-entity) | Chỉ khi policy chấp nhận không kiểm tra revocation của intermediate CA |
| `SOFT_FAIL` | Cho phép tiếp tục trong một số trường hợp không lấy được trạng thái do lỗi mạng/OCSP service tạm thời | Chỉ khi risk policy cho phép và có monitoring |

### 4.1. Mặc định của checker

Nếu không đặt option:
- OCSP được ưu tiên.
- CRL là cơ chế dự phòng khi OCSP gặp vấn đề theo chính sách provider.
- Tất cả các chứng thư thuộc phạm vi checker phải được xử lý theo quy tắc PKIX/provider, trừ khi có option giới hạn.

`checker.getOptions()` có thể trả một tập rỗng khi ứng dụng chưa chọn option nào. Điều này **không có nghĩa** revocation checking bị tắt; đó là cấu hình mặc định của checker.

### 4.2. PREFER_CRLS

`PREFER_CRLS` đổi thứ tự ưu tiên để CRL được thử trước OCSP. Nếu không có `NO_FALLBACK`, cơ chế còn lại vẫn có thể là nguồn dự phòng theo quy tắc của provider.

Ví dụ:

```java
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));
```

Đây là cấu hình **CRL ưu tiên, còn fallback vẫn được phép**.

Nếu cần CRL-only trong checker tường minh:

```java
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS,
        PKIXRevocationChecker.Option.NO_FALLBACK));
```

Đây là lựa chọn chặt hơn: khi CRL không thể cung cấp trạng thái theo policy, checker không chuyển sang OCSP.

### 4.3. NO_FALLBACK

`NO_FALLBACK` tắt nguồn dự phòng. Nếu không dùng `PREFER_CRLS`, mặc định OCSP được ưu tiên và không chuyển sang CRL. Nếu dùng cả hai option, CRL được ưu tiên và không chuyển sang OCSP.

Không đặt `NO_FALLBACK` chỉ để giảm network traffic nếu hệ thống vẫn yêu cầu độ sẵn sàng của revocation status. Một nguồn dữ liệu duy nhất có thể tạo điểm lỗi tập trung; policy cần xác định rõ cách xử lý khi nguồn đó không hoạt động.

### 4.4. ONLY_END_ENTITY

`ONLY_END_ENTITY` giới hạn revocation checking vào chứng thư đích. Khi dùng option này, intermediate CA không được kiểm tra trạng thái thu hồi qua checker đó.

Một intermediate CA bị thu hồi có thể ảnh hưởng nhiều chứng thư phía dưới. Chỉ bật option khi policy/kiến trúc PKI xác định rõ rằng việc kiểm tra intermediate được xử lý ở một lớp khác hoặc không thuộc yêu cầu của ứng dụng.

### 4.5. SOFT_FAIL

`SOFT_FAIL` cho phép revocation check thành công trong một số trường hợp không thể xác định trạng thái vì:
- Không lấy được CRL hoặc OCSP response do lỗi mạng.
- OCSP responder trả `internalError` hoặc `tryLater` theo giao thức.

Nếu fallback đang bật, Java chỉ cho phép soft-fail khi **cả hai cơ chế** đều thất bại vì các điều kiện được chỉ định. Nếu `NO_FALLBACK` được bật, điều kiện được áp dụng cho cơ chế duy nhất được chọn.

`SOFT_FAIL` **không** phải tùy chọn "bỏ qua mọi lỗi revocation":
- Một response xác nhận `revoked` không được coi là hợp lệ.
- Response sai chữ ký, sai issuer hoặc không hợp lệ không trở thành `good` chỉ vì có SOFT_FAIL.
- Một status `unknown` không phải `good`; phải tuân theo xử lý/fallback của provider và policy.
- Lỗi cấu hình trust, sai đường dẫn chứng thư hoặc sai thuật toán không phải lỗi mạng được SOFT_FAIL cho phép bỏ qua.

Dùng SOFT_FAIL là một quyết định **fail-open có giới hạn**. Với hệ thống xác thực, thanh toán, ký số hoặc quyền truy cập nhạy cảm, thường cần cân nhắc fail-closed: nếu không xác định được trạng thái thu hồi, không chấp nhận chứng thư cho đến khi có dữ liệu đáng tin.

## 5. Hai loại mặc định cần phân biệt trong Oracle JDK

Có một khác biệt dễ gây nhầm giữa **cơ chế mặc định của SUN PKIX provider** và **checker được ứng dụng lấy rồi gắn tường minh**.

### 5.1. Khi chỉ dùng revocation mặc định của provider

Trong Oracle JDK/SUN provider hiện hành:
- `PKIXParameters` mặc định có `revocationEnabled=true`.
- Security property `ocsp.enable` mặc định là `false`.
- Với revocation mặc định bật và `ocsp.enable=false`, provider dùng CRL.
- Khi `ocsp.enable=true`, provider dùng OCSP và có thể fallback sang CRL nếu OCSP gặp vấn đề.

`ocsp.enable` là **security property**, không phải tên system property thông thường. Có thể cấu hình trong file `java.security` hoặc qua cơ chế `Security.setProperty` ở thời điểm cấu hình thích hợp.

Bảng hành vi mặc định của SUN provider:

| revocationEnabled | ocsp.enable | Cơ chế |
| --- | --- | --- |
| `true` | `false` | CRL |
| `true` | `true` | OCSP, fallback CRL |
| `false` | `false` | Không kiểm tra thu hồi |
| `false` | `true` | Không kiểm tra thu hồi |

Đây là hành vi được tài liệu Oracle JDK mô tả cho SUN provider; provider khác có thể có chính sách riêng.

### 5.2. Khi ứng dụng gắn PKIXRevocationChecker tường minh

Với checker tường minh, API `PKIXRevocationChecker` mô tả mặc định:
- OCSP được ưu tiên.
- CRL là fallback.
- `PREFER_CRLS` đổi thứ tự ưu tiên.
- `NO_FALLBACK` tắt fallback.

Đây là cấu hình riêng của checker. Đừng suy luận rằng `ocsp.enable=false` sẽ tự biến một checker tường minh thành CRL-only. Nếu muốn kiểm soát chính xác, hãy cấu hình `setOptions`.

## 6. Java 17+ runnable: Cấu hình checker và gắn vào PKIXParameters

Chương trình này kiểm tra việc lấy checker, đặt options, cấu hình OCSP responder và gắn checker vào `PKIXParameters`. Nó **không** gọi OCSP/CRL và **không** xác thực chứng thư thật; trust anchor được tạo bằng khóa ngẫu nhiên chỉ để minh họa việc khởi tạo parameters.

Tạo file **`RevocationCheckerConfigDemo.java`**:

```java
import java.net.URI;
import java.security.KeyPairGenerator;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXParameters;
import java.security.cert.PKIXRevocationChecker;
import java.security.cert.TrustAnchor;
import java.util.Collections;
import java.util.EnumSet;
import javax.security.auth.x500.X500Principal;

public class RevocationCheckerConfigDemo {
    public static void main(String[] args) throws Exception {
        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");

        PKIXRevocationChecker checker =
                (PKIXRevocationChecker)
                        validator.getRevocationChecker();

        System.out.println("Algorithm: "
                + validator.getAlgorithm());
        System.out.println("Default options empty: "
                + checker.getOptions().isEmpty());

        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS));

        checker.setOcspResponder(
                URI.create("https://ocsp.example.test"));

        System.out.println("Prefer CRLs: "
                + checker.getOptions().contains(
                        PKIXRevocationChecker.Option.PREFER_CRLS));
        System.out.println("Fallback disabled: "
                + checker.getOptions().contains(
                        PKIXRevocationChecker.Option.NO_FALLBACK));
        System.out.println("OCSP override: "
                + checker.getOcspResponder());

        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        var pair = generator.generateKeyPair();

        TrustAnchor anchor = new TrustAnchor(
                new X500Principal("CN=Example Root"),
                pair.getPublic(),
                null);

        PKIXParameters parameters =
                new PKIXParameters(
                        Collections.singleton(anchor));

        System.out.println("Default revocation enabled: "
                + parameters.isRevocationEnabled());

        parameters.addCertPathChecker(checker);
        parameters.setRevocationEnabled(false);

        PKIXRevocationChecker installed =
                (PKIXRevocationChecker)
                        parameters.getCertPathCheckers().get(0);

        System.out.println("Revocation flag after custom checker: "
                + parameters.isRevocationEnabled());
        System.out.println("Installed checker prefers CRLs: "
                + installed.getOptions().contains(
                        PKIXRevocationChecker.Option.PREFER_CRLS));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 RevocationCheckerConfigDemo.java
java RevocationCheckerConfigDemo
```

**Stdout:**

```text
Algorithm: PKIX
Default options empty: true
Prefer CRLs: true
Fallback disabled: false
OCSP override: https://ocsp.example.test
Default revocation enabled: true
Revocation flag after custom checker: false
Installed checker prefers CRLs: true
```

**Giải thích:**
1. `getRevocationChecker()` trả checker do provider PKIX cung cấp.
2. `getOptions()` ban đầu rỗng vì chưa có option nào được đặt.
3. `PREFER_CRLS` yêu cầu CRL được ưu tiên; không đặt `NO_FALLBACK` nên fallback vẫn bật.
4. `setOcspResponder` ghi đè địa chỉ responder được suy ra từ certificate AIA hoặc property mặc định. Trong demo CRL được ưu tiên, URL này chỉ có ý nghĩa khi cơ chế OCSP được dùng.
5. `PKIXParameters` mặc định bật revocation.
6. Sau khi thêm checker tường minh, `setRevocationEnabled(false)` tắt cơ chế mặc định của provider; checker được gắn vẫn hoạt động.
7. Chương trình không gọi `validate`, vì chưa có certificate path và CA thật. Không coi stdout này là bằng chứng một chứng thư đã vượt qua revocation check.

## 7. Cấu hình OCSP responder và response có sẵn

### 7.1. Responder URI

`PKIXRevocationChecker.setOcspResponder(URI)` đặt địa chỉ OCSP responder. Nếu không đặt, provider có thể tìm URL từ Authority Information Access extension của chứng thư hoặc từ cấu hình bảo mật tương ứng.

`setOcspResponder` ghi đè:
- URL được đặt qua security property `ocsp.responderURL`.
- URL OCSP được chỉ định trong certificate AIA.

Ví dụ:

```java
checker.setOcspResponder(
        URI.create("https://ocsp.example.test"));
```

Đây là đoạn cấu hình với URI minh họa. URL này không tự tạo ra trust. Client vẫn phải xác minh OCSP response và thẩm quyền của signer.

### 7.2. Responder certificate

Trong một số deployment, responder dùng chứng thư được CA ủy quyền ký response. Có thể chỉ định chứng thư responder:

```java
checker.setOcspResponderCert(authorizedResponderCertificate);
```

Đây là đoạn cấu hình; `authorizedResponderCertificate` phải là chứng thư responder hợp lệ theo policy của CA. Không lấy một chứng thư bất kỳ từ mạng rồi gắn vào như trust anchor.

### 7.3. OCSP request extensions

`setOcspExtensions(List<Extension>)` cho phép thêm extension vào request. Một ví dụ quan trọng là nonce extension. Nonce có thể liên kết request với response để giảm nguy cơ dùng lại response cũ trong một số mô hình.

Nonce có trade-off:
- Tăng khả năng phát hiện response bị phát lại.
- Có thể làm giảm hiệu quả cache/pre-produced response.
- Cần responder hỗ trợ và xử lý đúng extension.
- Cần tránh vừa tự cung cấp nonce vừa bật cơ chế provider tự sinh nonce theo cấu hình có thể xung đột.

Không tự xây ASN.1 extension bằng chuỗi tùy ý. Dùng OID, DER encoding và cấu hình đúng theo RFC 6960 cùng provider đang chạy.

### 7.4. Cung cấp OCSP response đã lấy trước

`setOcspResponses(Map<X509Certificate, byte[]>)` nhận map từ chứng thư sang OCSP response đã mã hóa DER:

```java
Map<X509Certificate, byte[]> responses =
        Collections.singletonMap(certificate, derResponse);

checker.setOcspResponses(responses);
```

Đây là đoạn trong phương thức. `derResponse` phải là response OCSP DER phù hợp cho chính chứng thư đó. Việc cung cấp bytes không bỏ qua xác minh chữ ký, responder authorization, freshness hoặc các kiểm tra PKIX còn lại.

API này hữu ích khi ứng dụng quản lý cache/response sẵn có hoặc có lớp TLS thu thập response trước đó. Không dùng bytes tùy ý hoặc response không được xác minh.

## 8. CRL và CertStore trong Java

`CertStore` là abstraction để PKIX implementation tìm chứng thư và CRL. `PKIXParameters.addCertStore` có thể thêm một store vào danh sách nguồn dữ liệu được validator/builder sử dụng.

Một `CollectionCertStore` có thể chứa CRL đã được ứng dụng tải hoặc đọc từ file. Ví dụ đọc một CRL DER/PEM phù hợp bằng `CertificateFactory`:

```java
CertificateFactory factory =
        CertificateFactory.getInstance("X.509");

X509CRL crl;
try (InputStream input =
        Files.newInputStream(Path.of("issuer.crl"))) {
    crl = (X509CRL) factory.generateCRL(input);
}

CertStore store = CertStore.getInstance(
        "Collection",
        new CollectionCertStoreParameters(
                Collections.singleton(crl)));

parameters.addCertStore(store);
```

Đây là đoạn tích hợp; cần import `java.io.InputStream`, `java.nio.file.Files`, `java.nio.file.Path` và các lớp `java.security.cert` tương ứng. `parameters` là `PKIXParameters` hoặc `PKIXBuilderParameters` đã được tạo với trust anchors.

### 8.1. CRL phải phù hợp với chứng thư cần kiểm tra

Chỉ đọc được file CRL không có nghĩa CRL đó đủ để xác minh mọi certificate. Provider phải xác định CRL:
- Được ký bởi issuer hoặc CRL issuer được ủy quyền hợp lệ.
- Có issuer/authority phù hợp với certificate.
- Có phạm vi phân phối và lý do thu hồi phù hợp.
- Còn hiệu lực theo `thisUpdate`/`nextUpdate` và thời điểm validation.
- Không chứa critical extension chưa được xử lý.
- Có chữ ký và thuật toán được policy/provider chấp nhận.

Không tự viết logic "nếu serial không có trong file thì certificate tốt". Nếu CRL sai issuer, stale, chỉ bao phủ một phạm vi khác hoặc không đủ reason coverage, việc không tìm thấy serial không chứng minh certificate chưa bị thu hồi.

### 8.2. CRL Distribution Points

Certificate có thể chứa extension `CRLDistributionPoints` chỉ ra URI hoặc vị trí lưu CRL. Với Oracle SUN provider, hỗ trợ tải CRL từ extension này được cấu hình qua system property `com.sun.security.enableCRLDP`; tài liệu Oracle JDK 26 ghi cơ chế này mặc định tắt vì tương thích.

Khi dùng:

```bash
java -Dcom.sun.security.enableCRLDP=true MyCertificateValidationApp
```

Đây là cấu hình provider cụ thể, không phải API portable cho mọi provider. Cần kiểm tra network, proxy, URI allowlist, firewall và timeout. Có thể thay thế/ bổ sung nguồn CRL bằng `CertStore` được ứng dụng quản lý.

### 8.3. Delta CRL và provider support

RFC 5280 mô tả delta CRL và extension liên quan. Tuy nhiên, không giả định mọi PKIX provider đều hỗ trợ mọi CRL extension. Tài liệu Oracle JDK 26 về SUN CertPath implementation nêu các giới hạn hỗ trợ đối với `freshestCRL` và delta CRL extensions. Nếu hệ thống dựa vào delta CRL, phải kiểm chứng provider/version thực tế hoặc dùng giải pháp PKI có hỗ trợ được công bố rõ.

## 9. Cấu hình và thực hiện validation thực tế

Một ứng dụng thật cần:
- Trust anchors được quản lý rõ ràng.
- CertPath đã được xây dựng hoặc một builder có target constraints.
- Các chứng thư intermediate/target đúng thứ tự.
- Nguồn OCSP/CRL truy cập được theo policy.
- Timeout và proxy phù hợp.
- Revocation checker được cấu hình trước khi thêm vào parameters.

### 9.1. Validate một CertPath đã có

`CertPathValidator` xác thực một đường dẫn đã được tạo. Cấu trúc tích hợp:

```java
CertPathValidator validator =
        CertPathValidator.getInstance("PKIX");

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));

PKIXParameters parameters = new PKIXParameters(trustAnchors);
parameters.addCertPathChecker(checker);
parameters.setRevocationEnabled(false);

try {
    PKIXCertPathValidatorResult result =
            (PKIXCertPathValidatorResult)
                    validator.validate(certPath, parameters);

    System.out.println("PKIX validation: PASS");
    System.out.println("Validated public key algorithm: "
            + result.getPublicKey().getAlgorithm());
} catch (CertPathValidatorException ex) {
    System.out.println("PKIX validation: FAIL");
    System.out.println("Certificate index: " + ex.getIndex());
    System.out.println("Reason: " + ex.getReason());
    throw ex;
}
```

Đây là đoạn tích hợp trong ứng dụng với `trustAnchors` và `certPath` đã được tải. Nó thể hiện vị trí gắn checker vào quy trình; kết quả thực tế phụ thuộc certificate, CRL/OCSP, provider và network.

### 9.2. Build và validate một CertPath

Khi ứng dụng chưa có đường dẫn đầy đủ, `CertPathBuilder` có thể tìm đường dẫn dựa trên target constraints, trust anchors và các CertStore:

```java
CertPathBuilder builder =
        CertPathBuilder.getInstance("PKIX");

PKIXRevocationChecker checker =
        (PKIXRevocationChecker) builder.getRevocationChecker();

checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));

PKIXBuilderParameters parameters =
        new PKIXBuilderParameters(trustAnchors, targetSelector);

parameters.addCertPathChecker(checker);
parameters.setRevocationEnabled(false);

PKIXCertPathBuilderResult result =
        (PKIXCertPathBuilderResult)
                builder.build(parameters);
```

Đây là đoạn tích hợp với `trustAnchors` và `targetSelector` đã được khai báo. `PKIXBuilderParameters` kế thừa các thiết lập từ `PKIXParameters`, bao gồm revocation và CertStore.

Builder có thể thử các path khác nhau khi một candidate path không hợp lệ. Provider quyết định chi tiết thuật toán build/backtracking; hãy tham khảo tài liệu provider nếu ứng dụng phụ thuộc vào hành vi cụ thể.

### 9.3. Bắt và phân tích CertPathValidatorException

Một validation failure có thể đến từ:
- Chữ ký certificate không hợp lệ.
- Certificate hết hạn hoặc chưa tới ngày hiệu lực.
- Không nối được path tới trust anchor.
- Revocation status là revoked hoặc không thể xác định theo policy.
- CRL/OCSP response không hợp lệ hoặc không đủ freshness.
- Algorithm/key size bị security policy chặn.
- Critical extension không được xử lý.

Dùng `CertPathValidatorException.getIndex()` và `getReason()` để biết vị trí/lý do theo API. Kết hợp cause và provider debug output để phân biệt path failure, network failure và revocation failure. Không bắt mọi exception rồi trả kết quả "certificate hợp lệ".

## 10. OCSP/CRL mặc định trong Oracle JDK: Các property vận hành

Những property sau là cấu hình **provider cụ thể**. Chúng không phải một API chung bảo đảm giống nhau trên mọi JDK vendor.

| Property | Loại | Tác dụng |
| --- | --- | --- |
| `ocsp.enable` | Security property | Bật OCSP trong cơ chế revocation mặc định của SUN provider; mặc định false |
| `ocsp.responderURL` | Security property | Chỉ định OCSP responder mặc định khi cần override URL từ AIA |
| `com.sun.security.enableCRLDP` | System property | Cho phép SUN provider dùng CRL Distribution Points trong certificate để tìm CRL |
| `com.sun.security.ocsp.timeout` | System property | Timeout kết nối OCSP |
| `com.sun.security.ocsp.readtimeout` | System property | Timeout đọc response OCSP |
| `com.sun.security.crl.timeout` | System property | Timeout kết nối lấy CRL |
| `com.sun.security.crl.readtimeout` | System property | Timeout đọc CRL |
| `com.sun.security.cert.timeout` | System property | Timeout kết nối khi lấy certificate theo AIA |
| `com.sun.security.cert.readtimeout` | System property | Timeout đọc certificate lấy qua AIA |
| `jdk.certpath.disabledAlgorithms` | Security property | Hạn chế thuật toán/key size yếu trong quá trình CertPath validation của provider hỗ trợ property này |

Tài liệu Oracle JDK 26 mô tả timeout mặc định 15 giây cho các kết nối/đọc CRL và OCSP tương ứng; giá trị 0 có nghĩa timeout vô hạn. Không đặt vô hạn một cách tùy tiện vì validation có thể bị treo khi endpoint không phản hồi.

Các security property thường được cấu hình trong file `java.security` hoặc bằng API `Security.setProperty` ở thời điểm khởi tạo thích hợp. Các system property được truyền khi khởi chạy JVM, ví dụ:

```bash
java -Dcom.sun.security.enableCRLDP=true \
     -Dcom.sun.security.ocsp.timeout=5 \
     -Dcom.sun.security.ocsp.readtimeout=5 \
     MyCertificateValidationApp
```

Đây là ví dụ cấu hình cho Oracle/SUN provider; hãy xác minh tên property, đơn vị và hỗ trợ trên runtime thực tế. Không sao chép nguyên cấu hình provider-specific sang một JDK vendor khác mà không kiểm tra tài liệu.

## 11. SOFT_FAIL và quyết định fail-open/fail-closed

Revocation checking phụ thuộc vào hệ thống bên ngoài: OCSP responder, HTTP/LDAP repository, CRL issuer, DNS, proxy và network. Một chứng thư có thể không bị thu hồi nhưng client không lấy được dữ liệu để xác định trạng thái.

Hai chính sách phổ biến:

- **Fail-closed / hard-fail:** nếu không xác minh được trạng thái theo yêu cầu, không chấp nhận chứng thư. Bảo mật cao hơn khi việc dùng certificate không hợp lệ có hậu quả lớn; đổi lại dịch vụ phụ thuộc availability của hệ thống trạng thái.
- **Soft-fail / fail-open có giới hạn:** chấp nhận một số trường hợp trạng thái không xác định do lỗi khả dụng đã được chỉ định. Dịch vụ sẵn sàng hơn nhưng có thể tiếp tục dùng chứng thư mà trạng thái thu hồi mới chưa biết.

`SOFT_FAIL` chỉ bao phủ các điều kiện được Java API mô tả. Nó không phải cách bỏ qua mọi lỗi chứng thư. Nếu dùng, cần:
1. Ghi nhận exception bị bỏ qua qua cơ chế diagnostics phù hợp, chẳng hạn `getSoftFailExceptions()` của checker.
2. Theo dõi tỷ lệ lỗi mạng/OCSP/CRL và thời gian response.
3. Có cảnh báo khi không lấy được trạng thái kéo dài.
4. Đặt policy riêng theo mức độ nhạy cảm của thao tác.
5. Kiểm tra rằng một response `revoked` vẫn bị từ chối.

Không dùng SOFT_FAIL để che lỗi cấu hình trust store, lỗi ký CRL, response hết hạn, sai issuer hoặc thuật toán không còn được phép.

## 12. OCSP status, freshness và xác minh response

### 12.1. Good không có nghĩa là mọi điều kiện certificate đều hợp lệ

OCSP `good` trả lời câu hỏi trạng thái thu hồi theo phạm vi response. Nó không thay thế:
- Xác minh chữ ký certificate.
- Kiểm tra validity period.
- Xác minh certificate chain và trust anchor.
- Kiểm tra hostname/subject identity.
- Kiểm tra key usage/EKU/policy.
- Kiểm tra algorithm constraints.

RFC 6960 nói rõ `good` tối thiểu chỉ cho biết không có certificate mang serial được hỏi đang bị thu hồi trong phạm vi status inquiry; nó không nhất thiết chứng minh certificate từng được cấp.

### 12.2. Revoked và unknown

- `revoked`: phải xử lý như trạng thái bị thu hồi, từ chối certificate theo policy.
- `unknown`: responder không xác định được trạng thái. Client có thể thử CRL hoặc nguồn khác nếu policy cho phép. Không tự đổi unknown thành good.
- OCSP protocol error như `tryLater` hoặc `internalError`: thể hiện lỗi dịch vụ; đây là các trường hợp có thể liên quan tới SOFT_FAIL theo option của Java, nhưng phải xem fallback và policy cụ thể.

### 12.3. Freshness và replay

Response OCSP cũ có thể không phản ánh lần thu hồi vừa xảy ra. Vì vậy cần kiểm tra:
- `thisUpdate` có hợp lý với thời điểm validation không.
- `nextUpdate` nếu có, chưa vượt qua thời điểm hết hạn.
- `producedAt` có hợp lý và phù hợp policy không.
- Chữ ký response, signer và responder authorization hợp lệ.
- Nonce nếu policy sử dụng request-response binding.

Nonce giúp ràng buộc request và response để hạn chế replay trong các deployment hỗ trợ. Tuy nhiên, response pre-produced/caching có thể không tương thích với nonce theo cách triển khai của responder. Thiết kế nonce, cache lifetime và freshness phải được kiểm thử với CA/responder thật.

## 13. OCSP stapling và TLS/JSSE

OCSP stapling cho phép TLS server gửi kèm OCSP response đã lấy trước trong handshake. Cách này có thể:
- Giảm số request trực tiếp từ client tới OCSP responder.
- Giảm latency cho client.
- Giảm việc responder quan sát từng client đang hỏi chứng thư nào.
- Chuyển chi phí lấy response sang server.

Client vẫn phải xác minh response và freshness. Stapling không làm certificate tự hợp lệ; response stapled cũ hoặc sai chữ ký không được chấp nhận.

**Phân biệt API:** `PKIXRevocationChecker.setOcspResponder` chỉ cấu hình URL responder cho checker. Nó không tự bật toàn bộ TLS stapling hoặc tự cấu hình mọi `SSLContext`/`TrustManager` của ứng dụng. Nếu ứng dụng dùng JSSE, phải cấu hình trust manager/SSL parameters theo tài liệu JSSE của JDK và kiểm thử handshake thực tế.

Ngoài revocation, HTTPS client cần kiểm tra endpoint identification (hostname) theo chính sách. Revocation check không thay thế hostname verification.

## 14. Hiệu năng, cache và độ sẵn sàng

Revocation checking có thể thêm network round-trip vào quá trình xác thực certificate. Tác động phụ thuộc số chứng thư trong chain, cache, số request đồng thời, responder latency và cách provider lấy CRL.

Các điểm vận hành:
- Cache CRL/OCSP response theo issuer, certificate ID và thời hạn hợp lệ; không dùng cache quá `nextUpdate`.
- Đồng bộ clock của máy; sai giờ có thể khiến response hoặc CRL bị xem là stale/not-yet-valid.
- Cấu hình timeout kết nối và đọc hữu hạn.
- Kiểm tra proxy, DNS, firewall và egress policy tới các URL AIA/CRL DP.
- Không fetch URL tùy tiện từ certificate mà không có kiểm soát mạng/egress phù hợp.
- Theo dõi lỗi responder, HTTP status, timeout, cache hit, response age và soft-fail.
- Với hệ thống tải cao, cân nhắc OCSP stapling, CRL cache tập trung hoặc nguồn status nội bộ được vận hành đúng.

CRL cache thường tái sử dụng được cho nhiều chứng thư cùng issuer/phạm vi; OCSP cache thường gắn với certificate ID và response validity interval. Cache sai có thể kéo dài thời gian dùng dữ liệu trạng thái cũ sau khi certificate đã bị thu hồi.

### 14.1. Đừng đặt timeout vô hạn

Oracle JDK 26 mô tả giá trị 0 cho các timeout CRL/OCSP là vô hạn. Trong ứng dụng server, timeout vô hạn có thể giữ thread, connection hoặc request trong thời gian không giới hạn. Hãy đặt deadline phù hợp với SLA và policy bảo mật; không được tự động biến timeout thành "good" trừ khi policy cho phép soft-fail.

### 14.2. Không phải provider nào cũng hỗ trợ mọi extension

PKIX là chuẩn, nhưng provider có thể khác nhau về:
- Extension certificate/CRL được hỗ trợ.
- Cách lấy CRL từ distribution point.
- Delta CRL support.
- Cache, network timeout và responder fallback.
- Debug output và property riêng.

Tài liệu của provider là một phần của thiết kế triển khai. Kiểm thử trên đúng JDK vendor/version được deploy, không chỉ dựa vào chương trình chạy trên máy phát triển.

## 15. Debugging và kiểm tra lỗi

Với Oracle/SUN provider, có thể bật trace CertPath:

```bash
java -Djava.security.debug=certpath MyCertificateValidationApp
```

Trace này có thể cung cấp thông tin về quá trình path building/validation. Không bật debug chi tiết thường trực trên production nếu log volume hoặc thông tin chứng thư gây ảnh hưởng vận hành.

Khi nhận `CertPathValidatorException`:
- Đọc `getIndex()` để biết certificate nào trong path gây lỗi.
- Đọc `getReason()` và `getCause()`.
- Phân biệt lỗi signature/path, expired certificate, revocation status và network/CertStore.
- Kiểm tra chain có intermediate đúng issuer hay không.
- Kiểm tra OCSP responder/CRL endpoint có truy cập được không.
- Kiểm tra response/CRL có đúng issuer, đúng thời gian và còn freshness không.
- Kiểm tra system clock và timeout/proxy.

Không bắt exception rồi trả `true` hoặc bỏ qua mọi `CertPathValidatorException`. Cần phân loại lỗi theo reason và policy đã được phê duyệt.

## 16. Những lỗi thường gặp

1. **Chỉ kiểm tra chữ ký và ngày hết hạn:** certificate vẫn có thể bị thu hồi trước ngày hết hạn.
2. **Nghĩ OCSP và CRL là hai kiểu certificate:** đây là hai cơ chế phân phối thông tin revocation.
3. **Nghĩ `ocsp.enable` mặc định true:** trong Oracle JDK 26, security property này mặc định false cho cơ chế mặc định của SUN provider.
4. **Nghĩ `PKIXParameters` mặc định tắt revocation:** flag mặc định là true.
5. **Nhầm default provider với checker explicit:** cấu hình mặc định của SUN provider và mặc định của `PKIXRevocationChecker` là hai lớp khác nhau.
6. **Gọi `setRevocationEnabled(false)` mà không thêm checker khác:** vô tình tắt kiểm tra revocation.
7. **Nghĩ `setRevocationEnabled(false)` vô hiệu hóa checker đã gắn:** checker explicit vẫn được sử dụng theo hợp đồng API.
8. **Gắn checker rồi mới sửa options:** checker đã được clone; sửa đối tượng ban đầu không thay đổi bản đã lưu trong parameters.
9. **Dùng một checker cho nhiều thread:** các method checker không được bảo đảm thread-safe.
10. **Dùng `ONLY_END_ENTITY` mà không đánh giá intermediate CA:** bỏ qua trạng thái thu hồi của intermediate.
11. **Bật `SOFT_FAIL` cho mọi ứng dụng:** có thể làm tăng rủi ro khi responder không khả dụng.
12. **Nghĩ `SOFT_FAIL` chấp nhận chứng thư bị revoked:** option chỉ cho một số lỗi không lấy được status.
13. **Coi OCSP `unknown` là `good`:** unknown nghĩa responder không biết trạng thái.
14. **Coi OCSP `good` là chứng thư chắc chắn từng được cấp:** RFC 6960 không bảo đảm điều đó.
15. **Không kiểm tra `thisUpdate`/`nextUpdate`:** response cũ có thể không phản ánh trạng thái mới.
16. **Không xác minh chữ ký/ủy quyền responder:** response chưa xác minh không phải bằng chứng.
17. **Tự tải CRL rồi chỉ tìm serial:** bỏ qua issuer, signature, scope, reason coverage và freshness.
18. **Dùng CRL không đúng issuer hoặc distribution point:** có thể kết luận sai về trạng thái certificate.
19. **Nghĩ CRL nào cũng bao phủ tất cả lý do thu hồi:** CRL có thể bị giới hạn phạm vi.
20. **Nghĩ mọi provider hỗ trợ delta CRL:** extension/provider support phải được kiểm chứng.
21. **Không thêm CRL vào CertStore khi cần nguồn cục bộ:** provider có thể không tìm thấy dữ liệu.
22. **Nhầm CertStore với TrustStore:** CertStore cung cấp certificates/CRLs để build/validate; trust anchors xác định CA được tin cậy.
23. **Tin rằng setOcspResponder là bắt buộc:** nếu AIA đã có URL phù hợp, provider có thể tự lấy từ certificate.
24. **Nghĩ setOcspResponder tự bật TLS stapling:** đây là cấu hình responder cho checker, không phải toàn bộ TLS.
25. **Đặt URL OCSP là trust anchor:** URL chỉ định nơi hỏi, không chứng minh responder được ủy quyền.
26. **Không đặt timeout hữu hạn:** network failure có thể giữ request quá lâu.
27. **Đặt timeout 0 mà không biết nghĩa là vô hạn:** có thể làm thread bị giữ không giới hạn.
28. **Cache response vượt nextUpdate:** có thể dùng status quá cũ.
29. **Bỏ qua đồng hồ hệ thống:** clock skew có thể làm response/CRL bị coi là stale hoặc chưa có hiệu lực.
30. **Dùng checker demo với trust anchor ngẫu nhiên như bằng chứng path thật:** cấu hình checker không đồng nghĩa đã xác thực một certificate.
31. **Nghĩ PKIX revocation check kiểm tra hostname:** hostname verification là bước khác trong TLS.
32. **Nghĩ CertPathValidator tự tìm mọi intermediate certificate:** validator xác thực path đã có; builder dùng để tìm path.
33. **Bỏ qua lỗi CertPathValidatorException:** có thể biến path không hợp lệ thành trusted.
34. **Không kiểm tra provider/version production:** behavior mạng và extension support có thể khác runtime phát triển.
35. **Dùng RFC 2560 làm tài liệu giao thức hiện hành:** RFC 6960 đã thay thế RFC 2560.
36. **Cho rằng OCSP error response là trạng thái good:** internalError/tryLater/unauthorized là lỗi giao thức, không phải xác nhận không bị thu hồi.
37. **Bật soft-fail nhưng không giám sát:** hệ thống có thể âm thầm vận hành trong thời gian dài mà không có revocation evidence.
38. **Chỉ test một certificate chưa bị thu hồi:** cần test revoked, unknown, stale response và network outage.
39. **Không kiểm tra CRL signature hoặc delegated CRL issuer:** có thể tin dữ liệu từ nguồn không được ủy quyền.
40. **Nhầm revocation với hết hạn:** certificate hết hạn và certificate bị thu hồi là hai trạng thái độc lập.

## 17. Checklist triển khai

- [ ] Trust anchors có nguồn gốc và vòng đời quản lý rõ ràng?
- [ ] CertPath đúng thứ tự target → intermediate, không đưa trust anchor vào path?
- [ ] Dùng `CertPathValidator` cho path đã có hay `CertPathBuilder` khi cần tìm path?
- [ ] Revocation có được bật rõ ràng trong policy?
- [ ] Ứng dụng dùng cơ chế mặc định của provider hay gắn `PKIXRevocationChecker` tường minh?
- [ ] Nếu gắn checker, options được cấu hình trước khi add vào parameters?
- [ ] Có hiểu checker được clone khi add không?
- [ ] Có chọn rõ OCSP ưu tiên hay CRL ưu tiên?
- [ ] Có biết fallback được bật/tắt như thế nào?
- [ ] Có giới hạn `ONLY_END_ENTITY` chỉ khi policy cho phép?
- [ ] Có quyết định fail-closed hay soft-fail theo rủi ro?
- [ ] Nếu dùng SOFT_FAIL, có monitoring và cảnh báo không?
- [ ] OCSP responder lấy từ AIA hay URL override đã được kiểm soát?
- [ ] Response signer/authorized responder được xác minh?
- [ ] OCSP response freshness được kiểm tra?
- [ ] Có xử lý status `unknown` khác `good`?
- [ ] CRL issuer, signature, distribution point, scope và freshness hợp lệ?
- [ ] CRL/OCSP retrieval có timeout, proxy và network egress rõ?
- [ ] CertStore có nguồn CRL/certificate phù hợp nếu dùng offline?
- [ ] Provider/version có hỗ trợ các extension PKI mà deployment dựa vào?
- [ ] Có kiểm thử revoked, unknown, stale, malformed, network outage và fallback?
- [ ] TLS hostname verification được thực hiện riêng?
- [ ] Log/debug có đủ thông tin chẩn đoán mà không làm lộ dữ liệu không cần thiết?
- [ ] JDK security properties/algorithm constraints được giữ theo baseline an toàn?

## 18. Các tình huống kiểm thử cần có

| Kịch bản | Kết quả cần kiểm chứng |
| --- | --- |
| Certificate hợp lệ, OCSP good | Path được chấp nhận nếu các kiểm tra PKIX khác đều đạt |
| Certificate revoked theo OCSP | Path bị từ chối |
| OCSP unknown, CRL có dữ liệu phù hợp | Provider/policy xử lý fallback đúng |
| OCSP responder timeout, CRL truy cập được | Fallback CRL hoạt động nếu được bật |
| OCSP timeout và CRL timeout, SOFT_FAIL tắt | Revocation check thất bại theo hard-fail policy |
| OCSP timeout và CRL timeout, SOFT_FAIL bật | Chỉ soft-fail trong các điều kiện API cho phép; ghi nhận exception |
| NO_FALLBACK bật, nguồn ưu tiên lỗi | Không chuyển sang nguồn còn lại |
| PREFER_CRLS bật | CRL được thử trước theo provider |
| ONLY_END_ENTITY bật | Intermediate không được checker kiểm tra |
| CRL hết nextUpdate | Không coi CRL cũ là trạng thái hiện hành |
| CRL sai issuer hoặc chữ ký | Validation thất bại |
| OCSP response chữ ký không hợp lệ | Validation thất bại |
| OCSP response stale | Không chấp nhận response stale |
| Intermediate CA bị revoked | Path thất bại nếu policy kiểm tra intermediate |
| Trust anchor thay đổi | Cập nhật trust store/trust policy |
| OCSP endpoint không truy cập được qua proxy | Timeout/soft-fail/fallback đúng policy |
| Network outage kéo dài | Metrics/alert hiển thị, không âm thầm bỏ qua |
| TLS hostname sai nhưng certificate chưa bị revoked | Hostname check vẫn phải từ chối |
| OCSP response được cache | Không dùng sau freshness interval |
| JDK/provider thay đổi | Regression test revocation trên runtime mới |

## 19. Java 17+: Bộ kiểm tra cấu hình checker

Chương trình này kiểm tra các bất biến cấu hình mà không cần kết nối OCSP hoặc tải CRL. Nó không xác thực certificate path; các test path thực tế cần certificate/CRL/OCSP fixture của môi trường thử nghiệm.

Tạo file **`RevocationCheckerConfigChecks.java`**:

```java
import java.net.URI;
import java.security.KeyPairGenerator;
import java.security.cert.CertPathValidator;
import java.security.cert.PKIXParameters;
import java.security.cert.PKIXRevocationChecker;
import java.security.cert.TrustAnchor;
import java.util.Collections;
import java.util.EnumSet;
import javax.security.auth.x500.X500Principal;

public class RevocationCheckerConfigChecks {
    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) throws Exception {
        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");

        PKIXRevocationChecker checker =
                (PKIXRevocationChecker)
                        validator.getRevocationChecker();

        check(checker.getOptions().isEmpty(),
                "initial options should be empty");

        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK));

        check(checker.getOptions().contains(
                PKIXRevocationChecker.Option.PREFER_CRLS),
                "prefer CRLs");
        check(checker.getOptions().contains(
                PKIXRevocationChecker.Option.NO_FALLBACK),
                "disable fallback");

        URI responder = URI.create(
                "https://ocsp.example.test");
        checker.setOcspResponder(responder);

        check(responder.equals(checker.getOcspResponder()),
                "responder URI");
        System.out.println("Checker options and URI: PASS");

        KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        var pair = generator.generateKeyPair();

        TrustAnchor anchor = new TrustAnchor(
                new X500Principal("CN=Test Root"),
                pair.getPublic(),
                null);

        PKIXParameters parameters =
                new PKIXParameters(
                        Collections.singleton(anchor));

        check(parameters.isRevocationEnabled(),
                "PKIX default revocation flag");

        parameters.addCertPathChecker(checker);
        parameters.setRevocationEnabled(false);

        PKIXRevocationChecker installed =
                (PKIXRevocationChecker)
                        parameters.getCertPathCheckers().get(0);

        check(!parameters.isRevocationEnabled(),
                "default provider mechanism disabled");
        check(installed.getOptions().contains(
                PKIXRevocationChecker.Option.PREFER_CRLS),
                "checker cloned with options");
        check(installed.getOptions().contains(
                PKIXRevocationChecker.Option.NO_FALLBACK),
                "checker cloned with fallback option");

        System.out.println("PKIXParameters wiring: PASS");
        System.out.println("Custom checker retained: PASS");
        System.out.println("All checks: PASS");
    }
}
```

Chạy:

```bash
javac --release 17 RevocationCheckerConfigChecks.java
java RevocationCheckerConfigChecks
```

**Stdout:**

```text
Checker options and URI: PASS
PKIXParameters wiring: PASS
Custom checker retained: PASS
All checks: PASS
```

Bài test xác nhận checker có thể được lấy từ PKIX provider, options/URI được cấu hình, và checker được giữ lại trong parameters sau khi clone. Nó **không** xác nhận responder thật đang hoạt động hoặc CRL/OCSP response thật hợp lệ.

## 20. Câu hỏi ôn tập

1. Vì sao chữ ký certificate hợp lệ và chưa hết hạn vẫn chưa đủ để tin cậy?
2. CRL chứa dữ liệu gì và được xác minh bằng cách nào?
3. OCSP trả những trạng thái nào?
4. Vì sao `unknown` không đồng nghĩa `good`?
5. `good` theo RFC 6960 có chứng minh certificate từng được cấp không?
6. `CertPathValidator` khác `CertPathBuilder` thế nào?
7. Trust anchor có nằm trong `CertPath` theo quy ước X.509 không?
8. `PKIXRevocationChecker` có từ phiên bản Java nào?
9. Lấy checker từ `CertPathValidator` bằng API nào?
10. `PREFER_CRLS` thay đổi điều gì?
11. `NO_FALLBACK` có tác dụng gì?
12. `ONLY_END_ENTITY` bỏ qua loại chứng thư nào?
13. `SOFT_FAIL` cho phép bỏ qua những loại lỗi nào theo API?
14. SOFT_FAIL có chấp nhận certificate đã bị revoked không?
15. Vì sao có thể đặt `revocationEnabled=false` khi đã gắn checker tường minh?
16. Vì sao phải cấu hình checker trước khi gọi `addCertPathChecker`?
17. `setOcspResponder` ghi đè nguồn URL nào?
18. `setOcspResponses` nhận dữ liệu response ở định dạng nào?
19. `CertStore` có thể lưu CRL không?
20. Vì sao chỉ tìm serial number trong một file CRL chưa đủ?
21. `ocsp.enable` là system property hay security property?
22. Trong Oracle JDK 26, giá trị mặc định của `ocsp.enable` là gì?
23. `PKIXParameters` mặc định bật hay tắt revocation?
24. Vì sao phải kiểm tra `thisUpdate` và `nextUpdate`?
25. OCSP stapling có thay thế mọi bước xác minh response không?
26. Revocation checking có thay thế hostname verification không?
27. Khi nào nên chọn fail-closed?
28. Nếu dùng SOFT_FAIL, cần theo dõi những chỉ số nào?

**Gợi ý đáp án:** (1) CA có thể thu hồi trước ngày hết hạn. (2) Danh sách serial/reason/time có chữ ký; cần xác minh issuer, signature, scope và freshness. (3) good, revoked, unknown. (4) Responder không xác định được trạng thái. (5) Không. (6) Validator kiểm tra path có sẵn; builder tìm path. (7) Không. (8) Java 8. (9) `getRevocationChecker()`. (10) Ưu tiên CRL. (11) Tắt fallback giữa OCSP và CRL. (12) Intermediate CA. (13) Một số lỗi mạng và OCSP internalError/tryLater. (14) Không. (15) Checker tường minh vẫn được dùng; flag tắt cơ chế mặc định provider. (16) Parameters clone checker khi thêm. (17) ocsp.responderURL và URL trong AIA. (18) DER-encoded OCSP response. (19) Có. (20) Cần xác minh issuer, signature, scope, reason coverage và freshness. (21) Security property. (22) false. (23) Bật. (24) Để tránh response/CRL stale. (25) Không. (26) Không. (27) Khi không xác minh được trạng thái thì không được chấp nhận chứng thư. (28) Timeout, response age, soft-fail exceptions, CRL/OCSP errors và fallback frequency.

**Kết luận:** `PKIXRevocationChecker` giúp ứng dụng kiểm soát revocation trong PKIX bằng OCSP hoặc CRL. Hiểu rõ sự khác nhau giữa checker explicit và cơ chế mặc định của provider, lựa chọn fallback, phạm vi certificate được kiểm tra và giới hạn của SOFT_FAIL là điều kiện để cấu hình đúng. Dùng trust anchors và CertPath thật, xác minh chữ ký/freshness của OCSP/CRL, đặt timeout hữu hạn, kiểm thử cả trạng thái revoked lẫn lỗi mạng, và giữ revocation tách biệt với hostname verification. Các API này có từ Java 8 và vẫn dùng được trong Java hiện hành; khi triển khai, luôn kiểm tra behavior của provider/JDK thực tế.

## Tài liệu tham khảo chính thức hiện hành

- `PKIXRevocationChecker` — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html
- `PKIXRevocationChecker.Option` — Java SE 26 API, PREFER_CRLS/NO_FALLBACK/ONLY_END_ENTITY/SOFT_FAIL: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXRevocationChecker.Option.html
- `PKIXParameters` — Java SE 26 API, revocationEnabled, CertStore và checker cloning: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/PKIXParameters.html
- `CertPathValidator` — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPathValidator.html
- `CertPathBuilder` — Java SE 26 API: https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/security/cert/CertPathBuilder.html
- Oracle `Java PKI Programmer's Guide` — CertPath, CRL, OCSP, provider behavior and configuration: https://docs.oracle.com/en/java/javase/26/security/java-pki-programmers-guide.html
- **RFC 6960** — X.509 Online Certificate Status Protocol (OCSP), thay thế RFC 2560: https://www.rfc-editor.org/rfc/rfc6960
- **RFC 5280** — Internet X.509 PKI Certificate and Certificate Revocation List (CRL) Profile: https://www.rfc-editor.org/rfc/rfc5280
