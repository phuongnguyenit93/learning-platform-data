# 14.7 Chính sách khi không lấy được trạng thái thu hồi và hệ quả của SOFT_FAIL

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt ba tình huống: chứng thư **chưa bị thu hồi theo bằng chứng hợp lệ**, chứng thư **đã bị thu hồi**, và chứng thư **không thể xác định trạng thái thu hồi**.
2. Đánh giá lựa chọn **hard-fail/fail-closed** so với **soft-fail có điều kiện**, nhất là khi OCSP/CRL hoặc mạng đang gặp sự cố.
3. Hiểu chính xác `PKIXRevocationChecker.Option.SOFT_FAIL` trong Java 17, các trường hợp được phép bỏ qua, và tương tác với `NO_FALLBACK`, `PREFER_CRLS`, `ONLY_END_ENTITY`.
4. Cấu hình `CertPathValidator`, `PKIXParameters`, `TrustAnchor` và `PKIXRevocationChecker`; nắm vai trò của `getSoftFailExceptions()`.
5. Chạy hai bài lab Java 17: một OCSP responder không liên lạc được gây `UNDETERMINED_REVOCATION_STATUS` ở chế độ strict nhưng được soft-fail; một CRL được ký hợp lệ xác nhận `REVOKED` và vẫn bị từ chối dù bật SOFT_FAIL.
6. Thiết kế chính sách theo cấp độ rủi ro, giới hạn fallback/cache/timeout, giám sát soft-fail và kiểm thử việc không chấp nhận chứng thư đã thu hồi.

## 1. Thu hồi chứng thư khác với xác minh chữ ký, thời hạn hoặc danh tính

**X.509 certificate** có thể được ký đúng bởi CA, chưa hết hạn, có Subject Alternative Name phù hợp, nhưng **vẫn đã bị thu hồi trước `notAfter`** do private key bị xâm phạm, thiết bị bị mất, dịch vụ thay đổi chủ sở hữu, hoặc các lý do quản trị PKI khác.

```text
Leaf certificate + chain
            |
            v
Kiểm chữ ký, trust anchor, thời hạn, policy,
KeyUsage/EKU, hostname/SAN...
            |
            v
Kiểm trạng thái thu hồi bằng OCSP/CRL
            |
     +------+------+ 
     |      |      |
    good  revoked  undetermined
     |      |      |
 tiếp tục REJECT   áp dụng chính sách
```

**Undetermined không phải good.** Một timeout mạng, DNS lỗi hoặc OCSP responder không trả lời cho biết client **thiếu bằng chứng trạng thái hiện tại**, chứ không phải CA đã xác nhận chứng thư còn tốt.

| Tình trạng | Bản chất | Xử lý |
| --- | --- | --- |
| **Not-revoked theo OCSP/CRL hợp lệ** | Bằng chứng thu hồi đáng tin, đúng chứng thư, còn hiệu lực và đúng phạm vi không chỉ ra revoked | Có thể tiếp tục các điều kiện PKIX còn lại |
| **REVOKED** | Có bằng chứng hợp lệ xác nhận chứng thư bị thu hồi | **Từ chối** |
| **UNDETERMINED** | Không lấy/xác minh đủ bằng chứng để kết luận | Hard-fail hoặc soft-fail theo chính sách/API |
| **Sai chữ ký/chain/CA, hết hạn, hostname không khớp** | Lỗi độc lập với kênh thu hồi | **Từ chối**, SOFT_FAIL không hợp thức hóa |
| **Không có responder hoặc CRL hợp lệ** | Thiếu bằng chứng, có thể do cấu hình hoặc profile | Không mặc định coi là good |

`X509Certificate.checkValidity()` chỉ kiểm `notBefore` và `notAfter`; không tự truy vấn OCSP hoặc CRL. Ngược lại, revocation check không thay thế xác minh chain, identity hay các ràng buộc của chứng thư.

## 2. Cơ chế cung cấp trạng thái: OCSP và CRL

### 2.1 OCSP theo RFC 6960

**Online Certificate Status Protocol (OCSP)** cho phép hỏi một OCSP responder về trạng thái của chứng thư xác định bởi certificate ID. Cần kiểm chữ ký/ủy quyền responder, certificate ID đúng đối tượng, và độ mới của thông tin.

Khi phản hồi OCSP xử lý thành công, `SingleResponse.certStatus` có ba loại:

- **`good`**: theo phạm vi của responder, chứng thư chưa được xác nhận là revoked. RFC 6960 nêu rằng điều này **không tự chứng minh chứng thư đã từng được cấp** hoặc trust chain hợp lệ.
- **`revoked`**: chứng thư bị thu hồi; có profile cho phép trạng thái này áp dụng trường hợp non-issued. Verifier phải từ chối.
- **`unknown`**: responder không biết chứng thư/issuer được hỏi. Đây là **một trạng thái có cấu trúc**, không phải đồng nghĩa network error.

Khi OCSP response bị lỗi xử lý, `responseStatus` có thể là:

```text
successful (0)
malformedRequest (1)
internalError (2)
tryLater (3)
sigRequired (5)
unauthorized (6)
```

Trong nhóm trên, `internalError` và `tryLater` có ý nghĩa riêng trong quy tắc Java SOFT_FAIL. **Không gom `unknown`, `malformedRequest`, `unauthorized` và `tryLater` vào một kiểu “không trả lời”**.

Các mốc `thisUpdate`, `nextUpdate`, `producedAt` giúp đánh giá độ mới/chữ ký của response. Một response `good` **đã stale** không thể tự động được dùng như chứng cứ `good` hiện tại.

### 2.2 CRL theo RFC 5280

**Certificate Revocation List (CRL)** là danh sách các serial bị thu hồi được ký bởi CA hoặc CRL issuer được ủy quyền. Kiểm tra có giá trị đòi hỏi:

- Xác minh **chữ ký CRL**, authority và quyền ký `cRLSign` theo profile.
- Kiểm tra **issuer/scope**, issuing distribution point, reason masks, delta CRL nếu được dùng.
- Kiểm tra `thisUpdate`/`nextUpdate` và độ mới, không sử dụng một bản CRL quá hạn làm chứng cứ sạch.
- Tra serial chứng thư theo phạm vi issuer, không dùng “CRL bất kỳ không thấy serial” để kết luận tốt.
- Xử lý chứng thư trung gian/CA theo chính sách; không chỉ kiểm leaf nếu luồng yêu cầu mọi thành phần path.

OCSP và CRL có đặc điểm khác nhau; một hệ thống có thể ưu tiên một kênh và dự phòng bằng kênh kia. Nhưng **đều phải xác thực nguồn chứng cứ** và độ mới trước khi dùng kết quả.

## 3. Hard-fail và soft-fail phân bổ rủi ro khác nhau

### 3.1 Hard-fail / fail-closed

Nếu không thể xác định trạng thái thu hồi theo chính sách, kết nối hoặc thao tác phải **bị từ chối**.

```text
OCSP/CRL timeout
      |
      v
status undetermined
      |
      v
HARD-FAIL --> REJECT
```

Ưu điểm: đối thủ khó dùng việc chặn liên lạc tới responder để đưa một chứng thư đã bị thu hồi vào sử dụng. Nhược điểm: lỗi DNS, proxy, mạng nội bộ, CA responder hoặc outage diện rộng có thể khiến các chứng thư hợp lệ bị từ chối, gây gián đoạn dịch vụ.

### 3.2 Soft-fail / fail-open có điều kiện

Với soft-fail, **một số lỗi không lấy được trạng thái thu hồi** có thể bị bỏ qua để quá trình xác minh tiếp tục, miễn không có lỗi PKIX khác.

```text
OCSP/CRL tạm thời không truy cập được
      |
      v
status undetermined
      |
      v
SOFT-FAIL cho phép bỏ qua lỗi theo nhóm quy định
      |
      v
có thể tiếp tục xác minh / chấp nhận path
```

Ưu điểm: cải thiện availability khi responder hoặc mạng gặp trục trặc.

**Hệ quả bảo mật:** giả sử private key đã bị lộ và chứng thư tương ứng đã bị CA thu hồi. Nếu kẻ tấn công làm hỏng đường kết nối tới OCSP/CRL hoặc chờ lúc responder down, một verifier cấu hình soft-fail có thể **tiếp tục chấp nhận chứng thư cũ dù chưa thể nhận tin thu hồi**. Đây là sự đánh đổi có thật, không phải “cùng mức bảo mật nhưng ít lỗi kết nối hơn”.

| Trạng thái | Hard-fail | Soft-fail có điều kiện |
| --- | --- | --- |
| Bằng chứng hợp lệ xác nhận chưa revoked | Tiếp tục điều kiện khác | Tiếp tục điều kiện khác |
| Bằng chứng hợp lệ xác nhận **REVOKED** | **Từ chối** | **Từ chối** |
| Network error thuộc phạm vi được cho phép | **Từ chối** | Có thể tiếp tục, phải ghi nhận thiếu bằng chứng |
| OCSP `internalError` hoặc `tryLater` được phép xử lý mềm | **Từ chối** nếu hết nguồn khác | Có thể tiếp tục theo quy tắc fallback |
| OCSP `unknown` | Chưa xác nhận tình trạng | Không tự động được phân loại như network error |
| Chứng thư hết hạn, sai chữ ký, chain không trusted | **Từ chối** | **Từ chối** |

Bảng thể hiện mô hình quyết định. Kết quả thực tế phụ thuộc `PKIXRevocationChecker`, provider, tùy chọn fallback và nguồn chứng cứ sẵn có.

## 4. Semantics chính xác của Java 17 `PKIXRevocationChecker.Option.SOFT_FAIL`

Tài liệu Oracle Java SE 17 giới hạn SOFT_FAIL vào các tình huống:

1. **CRL hoặc OCSP response không lấy được do lỗi mạng**.
2. **OCSP responder trả `internalError` hoặc `tryLater`** theo giao thức.

Đây không phải cờ “bỏ qua tất cả lỗi thu hồi”. **Chứng thư biết chắc đã bị thu hồi phải bị từ chối**; lỗi chữ ký/chain/algorithm/time không tự trở thành hợp lệ.

Theo API `PKIXRevocationChecker.Option`, khi không dùng `NO_FALLBACK`, checker chỉ có thể soft-fail khi **cả OCSP và CRL đều thất bại theo một trong những nguyên nhân được cho phép** trong phạm vi cơ chế kiểm tra. Nếu nguồn dự phòng hoạt động và xác nhận revoked, phải reject.

### 4.1 Các option có ảnh hưởng trực tiếp

| Option | Ý nghĩa | Cần cân nhắc |
| --- | --- | --- |
| `SOFT_FAIL` | Bỏ qua một số lỗi không xác định do mạng/OCSP tạm thời | Có thể chấp nhận path chưa có revocation evidence |
| `NO_FALLBACK` | Vô hiệu cơ chế dự phòng | Tăng phụ thuộc kênh ưu tiên, không phù hợp mọi production |
| `PREFER_CRLS` | Ưu tiên CRL thay vì OCSP | Thay thứ tự truy cập, phụ thuộc CRL có sẵn |
| `ONLY_END_ENTITY` | Chỉ check leaf, không check trạng thái thu hồi các CA trong path | Có thể trái yêu cầu revocation của intermediate CA |

Mặc định trong mô tả API là **ưu tiên OCSP, fallback CRL**. `PREFER_CRLS` đảo ưu tiên; `NO_FALLBACK` tắt fallback.

```java
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.SOFT_FAIL,
        PKIXRevocationChecker.Option.NO_FALLBACK));
```

Đây là **đoạn code nhúng**, cần import và biến `validator`, không phải chương trình độc lập. Cặp cờ `SOFT_FAIL + NO_FALLBACK` được dùng trong bài lab để tái hiện rõ một kênh OCSP lỗi, **không phải công thức mặc định nên áp dụng sản xuất**.

### 4.2 `setRevocationEnabled(false)` có thể **không** tắt checker

Tài liệu `PKIXRevocationChecker` nêu rõ: khi thêm checker tường minh vào `PKIXParameters` bằng `addCertPathChecker`, checker vẫn được dùng **bất kể giá trị `revocationEnabled`**.

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

PKIXParameters params = new PKIXParameters(trustAnchors);
params.setRevocationEnabled(false);
params.addCertPathChecker(checker);
validator.validate(certPath, params);
```

Đây là code minh họa từng đoạn; cần `trustAnchors`, `certPath` và imports. `setRevocationEnabled(false)` trong trường hợp này vô hiệu **luồng checker mặc định**, không vô hiệu checker đã thêm bằng API. Ngược lại, tắt flag mà **không thêm checker** có thể khiến ứng dụng không kiểm thu hồi. Cần kiểm tra cấu hình tổng thể, không nhìn một dòng.

### 4.3 `getSoftFailExceptions()` để phân biệt “good” với “bỏ qua lỗi”

`PKIXRevocationChecker.getSoftFailExceptions()` trả về danh sách **`CertPathValidatorException` đã bị bỏ qua** vì SOFT_FAIL.

- Danh sách unmodifiable và được **xóa mỗi lần checker `init`**.
- Theo API, các exception được sắp theo **certificate index**.
- Có thể dùng để ghi nhận lượt validate có bỏ qua lỗi mạng nào, khác với việc đã có revocation evidence hợp lệ.

**Caveat:** `PKIXParameters.addCertPathChecker` **clone checker** và provider có thể quản lý/khởi tạo lại các instance. Vì vậy không giả định mọi `checker` tham chiếu đều phản ánh chính xác lượt validation; test đúng JDK/provider trong production. Cũng không chia sẻ checker mutable giữa các request/threads vì API không bảo đảm thread-safe.

Một metric “`soft fail exceptions = 0`” **không chứng minh đã check revocation**: nếu ai đó vô tình tắt kiểm tra hoàn toàn, nó cũng có thể bằng 0.

## 5. Phân biệt reason trong `CertPathValidatorException`

`CertPathValidatorException.BasicReason` trên Java 17 gồm:

- `UNDETERMINED_REVOCATION_STATUS` — trạng thái thu hồi không xác định được.
- `REVOKED` — chứng thư đã bị thu hồi.
- `EXPIRED` / `NOT_YET_VALID` — ngoài khoảng validity.
- `INVALID_SIGNATURE` — chữ ký không hợp lệ.
- `ALGORITHM_CONSTRAINED` — thuật toán/key bị ràng buộc chính sách.

**Không tự viết đoạn catch “gặp undetermined thì return true”**:

```java
// PHẢN VÍ DỤ, KHÔNG DÙNG TRONG SẢN PHẨM
try {
    validator.validate(path, params);
    return true;
} catch (CertPathValidatorException e) {
    return e.getReason() ==
            CertPathValidatorException.BasicReason.UNDETERMINED_REVOCATION_STATUS;
}
```

Đây là đoạn **chống ví dụ**, không tự compile. Nó lách cơ chế phân loại của checker, có thể bỏ qua điều kiện fallback và không bảo đảm các lỗi đã có trước/sau. Hãy để checker/validator thực thi policy đã được cấu hình; chỉ chấp nhận kết quả sau **toàn bộ kiểm tra path**, không nuốt mọi exception chung.

## 6. Thực hành 1 — Java 17: OCSP không kết nối được

Ta tạo **CA và leaf certificate riêng cho lab**, rồi ép OCSP responder về `http://127.0.0.1:1/ocsp`. Trong môi trường kiểm thử, không có dịch vụ nào lắng nghe cổng 1, nên request trả lỗi kết nối. Không truy vấn hệ thống bên ngoài.

**Kết quả mong đợi trong lab:** strict trả `UNDETERMINED_REVOCATION_STATUS`; SOFT_FAIL có thể validate và ghi nhận 1 lỗi bị bỏ qua. Nếu trên máy bạn cổng 1 có service hoặc provider xử lý khác, kết quả/exception count có thể thay đổi; chọn một cổng loopback không có responder thực sự và kiểm tra cấu hình.

### 6.1 Chuẩn bị CA/leaf bằng `keytool`

Chạy trong **thư mục thử nghiệm trống** bằng JDK 17+, không dùng keystore production:

```bash
keytool -genkeypair -alias labca -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Lab Root CA,O=Example Lab,C=VN" -validity 180 -ext bc:c -ext ku=keyCertSign,cRLSign -keystore ca.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -exportcert -alias labca -keystore ca.p12 -storetype PKCS12 -storepass changeit -rfc -file ca.pem

keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=lab.local,O=Example Lab,C=VN" -validity 30 -keystore leaf.p12 -storetype PKCS12 -storepass changeit -noprompt

keytool -certreq -alias leaf -keystore leaf.p12 -storetype PKCS12 -storepass changeit -file leaf.csr

keytool -gencert -alias labca -keystore ca.p12 -storetype PKCS12 -storepass changeit -infile leaf.csr -outfile leaf.pem -rfc -validity 30 -ext ku=digitalSignature -ext EKU=serverAuth -ext SAN=dns:lab.local
```

`ca.p12` và `leaf.p12` chứa **private keys chỉ để thực hành**; không commit, chia sẻ, triển khai. Password `changeit` chỉ dành cho lab. `ca.pem` là public CA certificate dùng làm trust anchor **tường minh trong lab**, còn `leaf.pem` là leaf certificate do CA lab ký. Việc import một CA tùy ý từ network làm trust anchor của sản phẩm là **nguy hiểm**.

### 6.2 Chương trình `RevocationPolicyLab.java`

```java
import java.io.InputStream;
import java.net.URI;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.*;
import java.util.*;

public class RevocationPolicyLab {
    private static X509Certificate load(String filename) throws Exception {
        try (InputStream stream = Files.newInputStream(Path.of(filename))) {
            return (X509Certificate) CertificateFactory.getInstance("X.509")
                    .generateCertificate(stream);
        }
    }

    private static void check(X509Certificate leaf, X509Certificate root,
                              boolean allowSoftFail) throws Exception {
        CertPathValidator validator = CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();

        checker.setOcspResponder(URI.create("http://127.0.0.1:1/ocsp"));
        checker.setOptions(allowSoftFail
                ? EnumSet.of(PKIXRevocationChecker.Option.NO_FALLBACK,
                             PKIXRevocationChecker.Option.SOFT_FAIL)
                : EnumSet.of(PKIXRevocationChecker.Option.NO_FALLBACK));

        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        params.setRevocationEnabled(false);
        params.addCertPathChecker(checker);

        CertPath certPath = CertificateFactory.getInstance("X.509")
                .generateCertPath(List.of(leaf));
        try {
            validator.validate(certPath, params);
            System.out.println((allowSoftFail ? "soft" : "strict") +
                    ": VALIDATED");
        } catch (CertPathValidatorException e) {
            System.out.println((allowSoftFail ? "soft" : "strict") +
                    ": REJECTED reason=" + e.getReason());
        }
        System.out.println("original checker ignored: " +
                checker.getSoftFailExceptions().size());
        for (PKIXCertPathChecker candidate : params.getCertPathCheckers()) {
            if (candidate instanceof PKIXRevocationChecker) {
                System.out.println("params checker ignored: " +
                        ((PKIXRevocationChecker) candidate)
                                .getSoftFailExceptions().size());
            }
        }
    }

    public static void main(String[] args) throws Exception {
        X509Certificate leaf = load(args[0]);
        X509Certificate root = load(args[1]);
        leaf.verify(root.getPublicKey());
        System.out.println("leaf signed by trusted CA: true");
        check(leaf, root, false);
        check(leaf, root, true);
    }
}
```

Biên dịch và chạy cùng thư mục `leaf.pem`/`ca.pem`:

```bash
javac --release 17 RevocationPolicyLab.java
java RevocationPolicyLab leaf.pem ca.pem
```

Đầu ra **đã được chạy và kiểm chứng** trên JDK/provider thử nghiệm:

```text
leaf signed by trusted CA: true
strict: REJECTED reason=UNDETERMINED_REVOCATION_STATUS
original checker ignored: 0
params checker ignored: 0
soft: VALIDATED
original checker ignored: 1
params checker ignored: 1
```

**Giải thích:**

1. `leaf.verify(root.getPublicKey())` kiểm chữ ký leaf theo khóa của CA lab. Nó không tự chứng minh root trusted; chương trình **cố ý tạo trust anchor** `new TrustAnchor(root,null)`.
2. `setOcspResponder` **ghi đè** endpoint OCSP trong AIA/thuộc tính bảo mật nếu có; địa chỉ loopback là một cách giả lập lỗi mạng.
3. `NO_FALLBACK` tắt khả năng thử CRL dự phòng; nhờ đó lượt strict thất bại khi không hỏi được OCSP.
4. Lượt có `SOFT_FAIL` bỏ qua lỗi kết nối thuộc phạm vi API; path có thể được xác thực thành công dù **chưa có OCSP good**.
5. Trên JDK thử nghiệm, `getSoftFailExceptions()` ghi nhận lỗi đã bỏ qua; không giả định con số hay trạng thái object giống hệt trên mọi provider hoặc qua mọi lượt `init`.
6. `params.setRevocationEnabled(false)` không chặn checker đã thêm tường minh. Nếu check thực sự bị tắt, lượt strict đã không có reason về revocation như stdout.

Điều lab chứng minh là **sự khác biệt chính sách khi thiếu bằng chứng**. Không triển khai cứng `NO_FALLBACK` hay loopback OCSP trong ứng dụng thật. Nên cho provider lấy nguồn OCSP/CRL có thẩm quyền và áp dụng policy/monitoring đã duyệt.

## 7. Thực hành 2 — SOFT_FAIL vẫn từ chối chứng thư REVOKED

Để chứng minh SOFT_FAIL **không chấp nhận bằng chứng thu hồi rõ ràng**, dùng lại `ca.p12`/`ca.pem`/`leaf.pem` ở trên. Sinh một CRL do CA lab ký, liệt kê **serial thật** của leaf, thêm CRL vào `CertStore` và kiểm bằng `PREFER_CRLS + NO_FALLBACK + SOFT_FAIL`.

### 7.1 Tạo CRL với serial của chứng thư

`keytool -gencrl -id` nhận serial decimal. Vì serial X.509 có thể vượt `long`, ta đọc serial hex từ `keytool -printcert` và dùng `BigInteger` để đổi sang decimal.

Các lệnh sau dùng **PowerShell 5.1+** trong thư mục lab:

```powershell
$serialLine = (keytool -printcert -file leaf.pem |
    Select-String 'Serial number:' | Select-Object -First 1).ToString()
$serialHex = ($serialLine -split 'Serial number:')[1].Trim()
$serialDecimal = [System.Numerics.BigInteger]::Parse(
    ('0' + $serialHex),
    [System.Globalization.NumberStyles]::AllowHexSpecifier
).ToString()
keytool -gencrl -alias labca -keystore ca.p12 -storepass changeit -file revoked.crl -rfc -id $serialDecimal
```

`revoked.crl` chỉ là CRL lab. Thời điểm/serial thay đổi qua mỗi lần tạo. **Không dùng lệnh này với CA production**; bài lab tạo/sử dụng các khóa thử nghiệm riêng.

### 7.2 Chương trình `KnownRevokedLab.java`

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.*;
import java.util.*;

public class KnownRevokedLab {
    public static void main(String[] args) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        X509Certificate leaf;
        X509Certificate ca;
        X509CRL crl;
        try (InputStream in = Files.newInputStream(Path.of(args[0]))) {
            leaf = (X509Certificate) factory.generateCertificate(in);
        }
        try (InputStream in = Files.newInputStream(Path.of(args[1]))) {
            ca = (X509Certificate) factory.generateCertificate(in);
        }
        try (InputStream in = Files.newInputStream(Path.of(args[2]))) {
            crl = (X509CRL) factory.generateCRL(in);
        }

        crl.verify(ca.getPublicKey());
        System.out.println("CRL signature verifies: true");
        System.out.println("leaf on CRL: " + crl.isRevoked(leaf));

        CertPathValidator validator = CertPathValidator.getInstance("PKIX");
        PKIXRevocationChecker checker =
                (PKIXRevocationChecker) validator.getRevocationChecker();
        checker.setOptions(EnumSet.of(
                PKIXRevocationChecker.Option.PREFER_CRLS,
                PKIXRevocationChecker.Option.NO_FALLBACK,
                PKIXRevocationChecker.Option.SOFT_FAIL));

        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(ca, null)));
        params.setRevocationEnabled(false);
        params.addCertStore(CertStore.getInstance("Collection",
                new CollectionCertStoreParameters(List.of(crl))));
        params.addCertPathChecker(checker);
        CertPath path = factory.generateCertPath(List.of(leaf));

        try {
            validator.validate(path, params);
            System.out.println("soft fail accepts revoked: true");
        } catch (CertPathValidatorException e) {
            System.out.println("soft fail rejects revoked: " +
                    (e.getReason() ==
                            CertPathValidatorException.BasicReason.REVOKED));
            System.out.println("reason: " + e.getReason());
        }
    }
}
```

Biên dịch và chạy sau khi tạo `revoked.crl`:

```bash
javac --release 17 KnownRevokedLab.java
java KnownRevokedLab leaf.pem ca.pem revoked.crl
```

Đầu ra đã kiểm chứng với CA và CRL lab:

```text
CRL signature verifies: true
leaf on CRL: true
soft fail rejects revoked: true
reason: REVOKED
```

Giải thích:

- `crl.verify(ca.getPublicKey())` xác minh chữ ký CRL; trong sản phẩm còn phải kiểm authority/scope/time/distribution point và các yêu cầu CRL khác.
- `crl.isRevoked(leaf)` xác nhận leaf được liệt kê.
- Checker đã bật `SOFT_FAIL` nhưng kết quả PKIX vẫn là `REVOKED`, vì **bằng chứng thu hồi hợp lệ không phải network error**.
- `PREFER_CRLS + NO_FALLBACK` cố ý chọn kênh CRL để test, không phản ánh toàn bộ chính sách production.

## 8. Tại sao SOFT_FAIL có thể bị khai thác qua lỗi mạng?

Một kịch bản nguy hiểm:

1. Private key của một thiết bị hoặc service bị đánh cắp.
2. CA phát hiện sự cố và công bố trạng thái `revoked` qua OCSP/CRL.
3. Kẻ tấn công vẫn có certificate cũ và private key bị lộ.
4. Đúng lúc verifier xác thực, kết nối tới nguồn revocation gặp lỗi (có thể do attacker tác động hoặc outage ngẫu nhiên).
5. Nếu chính sách soft-fail cho phép đi qua khi thiếu chứng cứ, service có thể **tiếp tục chấp nhận certificate đã bị thu hồi**.

Điều này cho thấy tính sẵn sàng của responder là một thành phần của mô hình bảo mật. Việc chặn mạng không phá khóa riêng CA nhưng có thể **làm suy yếu quyết định revocation** nếu verifier fail-open.

Rủi ro tăng lên khi:

- Soft-fail được bật ở quy mô toàn hệ thống, không phân biệt privilege.
- Không có timeout/budget; trạng thái không xác định kéo dài hàng ngày.
- Không giám sát hoặc xem mọi `validator.validate() == success` là chứng cứ not-revoked.
- Không có CRL/OCSP mirror hoặc nguồn fallback đã kiểm tra.
- Dùng `ONLY_END_ENTITY` dù chính sách cần kiểm CA trung gian.
- Cấu hình ứng dụng nuốt exception chung rồi cho phép đăng nhập bất kỳ.
- Một lỗi DNS/proxy được attacker gây có chủ đích nhưng bị xem như sự cố vận hành thông thường.

Giải pháp không nhất thiết là “mọi nơi hard-fail”. Cần đánh giá **giá trị tài sản**, tính sẵn sàng, phạm vi authority và cơ chế dự phòng sao cho soft-fail nếu có là ngoại lệ **được phê duyệt và quan sát được**.

## 9. Chính sách theo mức độ rủi ro

| Hệ thống/ngữ cảnh | Hướng thiết kế thường phù hợp | Điều kiện |
| --- | --- | --- |
| Xác thực mTLS của service có quyền quản trị, thanh toán, HSM, ký giao dịch | **Hard-fail** khi không xác định được revocation nếu policy bắt buộc | Nguồn chứng cứ dự phòng/caching còn hạn, báo lỗi rõ, tránh outage không cần thiết |
| Cấp phát chứng thư thiết bị, truy cập hệ quản trị/đặc quyền | **Hard-fail**, có phương án xử lý outage có kiểm soát | Giữ độ tin cậy key/issuer/chain, không tự bỏ kiểm tra |
| Client kết nối dịch vụ công cộng, ít đặc quyền | Có thể **soft-fail có điều kiện** theo chuẩn áp dụng/threat model | Ghi audit, giới hạn thời gian, không bỏ qua revoked |
| Máy offline theo chu kỳ, có CRL/OCSP response đã cache | Chỉ dùng bằng chứng **còn hiệu lực**; sau đó áp dụng policy offline rõ | Định nghĩa max age, thiết bị được phép và cách khôi phục |
| Mạng nội bộ có CRL mirror/OCSP proxy quản lý | Ưu tiên nguồn đáng tin cậy/có sẵn | Xác minh chữ ký và freshness, không chỉ tin endpoint vì nằm trong mạng nội bộ |
| Chuỗi CA trung gian có quyền ký nhiều service | Thường cần kiểm toàn bộ path theo policy | Không vô tình bỏ CA revocation bằng `ONLY_END_ENTITY` |

Không có một cấu hình mặc định luôn đúng cho tất cả. Quy định ngành, đặc tả giao thức hoặc policy nội bộ có thể bắt buộc hard-fail hoặc cách lấy chứng cứ cụ thể.

### 9.1 Nếu chọn soft-fail, phải định nghĩa ngoại lệ

Một quyết định soft-fail có kiểm soát cần mô tả:

- **Lỗi hợp lệ**: chỉ những nguyên nhân `SOFT_FAIL` hỗ trợ; không coi revoked/invalid response thành lỗi “nhẹ”.
- **Phạm vi**: loại workload, certificate/CA, tài khoản, quyền và thao tác được phép; ví dụ read-only có thể có policy khác thao tác cấp quyền.
- **Thời hạn**: bao lâu có thể tiếp tục khi mất bằng chứng mới; ngưỡng liên tiếp và điều kiện phục hồi.
- **Nguồn thay thế**: cơ chế fallback có ký và còn hiệu lực, mirror/cache được giám sát.
- **Đo lường**: lần validation, lý do, thời điểm, responder, tỉ lệ soft-fail và độ tuổi bằng chứng.
- **Dừng khẩn cấp**: ngưỡng chuyển hard-fail hoặc phong tỏa thao tác nhạy cảm; kiểm soát sự cố CA/key leak.
- **Người phê duyệt**: chủ quản PKI/security, lịch sử thay đổi policy và yêu cầu kiểm tra định kỳ.

**Soft-fail không đồng nghĩa return true khi mạng hỏng.** Toàn bộ chain, identity và các kiểm tra khác vẫn phải đạt.

## 10. Fallback, cache, retry và timeout

### 10.1 Fallback phải dựa trên bằng chứng có hiệu lực

Nếu OCSP không trả lời, CRL còn hiệu lực có thể là nguồn kiểm tra thay thế; ngược lại, nếu CRL không truy xuất được, OCSP hợp lệ có thể giúp xác nhận. Nhưng fallback **không được** dùng chứng cứ sai chữ ký, sai issuer, hết hạn hoặc không bao phủ certificate.

`NO_FALLBACK` giúp cô lập hành vi trong bài lab nhưng **có thể giảm availability lẫn khả năng tìm được tình trạng revoked** khi nguồn ưu tiên lỗi.

### 10.2 Cache không đồng nghĩa giữ “good” vô hạn

- OCSP có `thisUpdate`, `nextUpdate`, `producedAt`.
- CRL có `thisUpdate` và thường `nextUpdate` theo profile.
- Cache status `good` **quá hạn** không còn là bằng chứng mới đáng tin. Nếu policy cho phép tiếp tục, phải ghi rõ đó là **ngoại lệ degraded**, không phải “OCSP currently good”.
- Không tự đặt TTL cao hơn giới hạn freshness của nguồn và không coi `HTTP 200` là bằng chứng có chữ ký hợp lệ.

### 10.3 Timeout và retry có thể biến outage thành DoS

Một responder bị chậm có thể khiến hàng nghìn request/handshake cùng chờ hoặc retry. Vì vậy cần:

- Timeout DNS/TCP/HTTP/OCSP hữu hạn theo SLO và chính sách.
- Backoff/jitter, giới hạn retry và concurrency, tránh thundering herd.
- Cache/deduplicate các request đang xác thực cùng một certificate.
- Circuit breaker có kết quả **explicit** (fail closed hoặc approved soft-fail), không giả lập success.
- Kiểm soát network egress tới URL CRL/AIA vì thông tin URL có thể đến từ certificate ngoài; tránh truy xuất mạng nội bộ tùy ý.
- Theo dõi đồng hồ và độ mới của response. Clock drift làm certificate hoặc chứng cứ status bị xem sai thời hạn.

Một timeout quá ngắn làm tăng soft-fail; quá dài gây tăng latency và rủi ro DoS. Phải benchmark trên môi trường và provider thật.

## 11. OCSP stapling và must-staple là vấn đề riêng

**OCSP stapling** cho phép server cung cấp OCSP response trong quá trình TLS handshake, giúp client không cần hỏi responder trực tiếp trong nhiều trường hợp. Tuy nhiên client vẫn phải kiểm chữ ký, responder authority, đúng certificate và freshness.

**TLS Feature extension — RFC 7633** đôi khi được gọi là “must-staple”. Đây là tín hiệu/protocol constraint riêng, **không cùng ý nghĩa** với Java `PKIXRevocationChecker.Option.SOFT_FAIL`.

Không mặc định rằng một Java JSSE/HTTPS client sẽ tự enforce must-staple chỉ vì có `SOFT_FAIL`/`setRevocationEnabled`. Nếu chính sách TLS của sản phẩm yêu cầu revocation hoặc stapling, phải kiểm tra trust manager/provider, các security properties và **test end-to-end**. Bài lab `CertPathValidator` standalone chỉ chứng minh behavior của API PKIX đã cấu hình, không chứng minh mọi HTTP/TLS client trên máy đều tuân theo.

## 12. Giám sát và xử lý sự cố

Một số metric có ích:

| Metric / field đề xuất | Vai trò |
| --- | --- |
| `pkix_soft_fail_total` | Tổng lượt bỏ qua lỗi revocation do chính sách |
| `revocation_check_total{method,outcome}` | Phân biệt OCSP/CRL, good/revoked/undetermined/error |
| `ocsp_crl_error_total{endpoint,reason}` | Phân tích DNS, timeout, HTTP, responder error |
| `revocation_evidence_age_seconds` | Cảnh báo bằng chứng sắp stale/hết hạn |
| `revocation_next_update_remaining_seconds` | Quản lý thời hạn cache hợp lệ |
| `cert_validation_total{reason}` | Phân biệt `REVOKED`, `EXPIRED`, `INVALID_SIGNATURE`, `UNDETERMINED` |
| `soft_fail_duration_seconds` | Theo dõi thời gian vận hành trong trạng thái degraded |

Trong log audit có thể lưu CA/issuer ID, certificate serial/fingerprint, responder, phiên bản policy và basic reason. Cần kiểm soát quyền truy cập; không log private key/credential; tránh đưa DN hoặc serial từng người dùng vào nhãn metric cardinality cao không kiểm soát.

**Lưu ý:** metric soft-fail bằng 0 không chứng minh checker đang bật. Cần **synthetic test** với một certificate đã revoked để bảo đảm hệ thống thật từ chối nó ngay cả khi xảy ra lỗi mạng.

### 12.1 Runbook khi responder mất khả dụng

1. Xác nhận là lỗi responder/DNS/proxy/circuit hay lỗi PKIX khác; không vội tắt toàn bộ validation.
2. Kiểm tra fallback CRL/OCSP và cache **còn hạn, đúng issuer/scope**.
3. Phân nhóm flow đặc quyền cao; ưu tiên hard-fail nếu chưa có policy ngoại lệ hợp lệ.
4. Nếu một nhóm được phép soft-fail, ghi rõ chủ thể phê duyệt, thời hạn, tài sản ảnh hưởng, metrics và ngưỡng kết thúc.
5. Khôi phục responder hoặc đồng bộ chứng cứ mới; xác nhận tỉ lệ soft-fail giảm.
6. Sau outage, đối chiếu log để xác định những lượt đã được chấp nhận **khi revocation chưa xác định** và xem có cần thu hồi quyền/rotate certificate hay không.

## 13. Ma trận kiểm thử bắt buộc

| Tình huống | Kỳ vọng |
| --- | --- |
| Chain đáng tin, OCSP/CRL hợp lệ xác nhận không revoked | Tiếp tục nếu các điều kiện khác đạt |
| OCSP hợp lệ xác nhận `revoked` | REJECT dù SOFT_FAIL |
| CRL hợp lệ liệt kê leaf revoked | REJECT dù SOFT_FAIL (thực hành 2) |
| OCSP network error, `NO_FALLBACK`, strict | `UNDETERMINED_REVOCATION_STATUS` (thực hành 1) |
| OCSP network error, `NO_FALLBACK`, SOFT_FAIL | Có thể validate; audit được lỗi bỏ qua (thực hành 1) |
| OCSP lỗi nhưng CRL dự phòng còn hiệu lực | Sử dụng kết quả CRL, không bỏ qua sớm |
| OCSP `internalError` / `tryLater` | Theo phạm vi SOFT_FAIL và quy tắc fallback |
| OCSP `unknown` hoặc `unauthorized` | Không tự xem là network error |
| OCSP response ký sai, sai serial/issuer, sai thời điểm | Không chấp nhận như bằng chứng good |
| CRL quá hạn hoặc không bao phủ certificate | Không xem là revocation verified |
| Certificate hết hạn hoặc trust anchor sai | REJECT độc lập SOFT_FAIL |
| Intermediate CA bị revoked | Theo scope path/policy, không bỏ qua ngoài ý muốn |
| Outage dài / failover / đổi JDK/provider | Kiểm tra timeout, config và behavior thực tế |
| TLS client production | Test full handshake/trust manager, không chỉ unit test PKIX |

Nếu có ngoại lệ phát sinh, test phải thất bại và đưa vào quy trình điều tra chứ không chấp nhận bằng cách thêm `catch(Exception) return true`.

## 14. Sai lầm phổ biến

1. **“OCSP không liên lạc được nghĩa là không bị thu hồi.”** Sai: đó là trạng thái không xác định.
2. **“SOFT_FAIL bỏ qua mọi lỗi certificate.”** Sai: chỉ một số lỗi mạng/OCSP tạm thời theo API.
3. **“Đã biết REVOKED vẫn có thể cho qua vì SOFT_FAIL.”** Sai: REVOKED luôn reject.
4. **“OCSP unknown giống tryLater.”** Sai: một bên là status chứng thư, một bên là lỗi responder.
5. **“NO_FALLBACK càng an toàn vì ít request.”** Không mặc nhiên: mất nguồn thay thế có thể khiến không có chứng cứ.
6. **“setRevocationEnabled(false) chắc chắn không còn checker.”** Sai khi thêm checker tường minh.
7. **“getSoftFailExceptions rỗng chứng minh certificate good.”** Không; có thể checker không chạy hoặc chưa đúng instance/lượt.
8. **“Có OCSP good là tin được website.”** Không; còn PKIX chain, identity, EKU, algorithm constraints.
9. **“Cache good có thể dùng đến khi certificate hết hạn.”** Sai; response có thời hạn riêng.
10. **“Tăng retry vô hạn là tăng tính an toàn.”** Sai; gây availability/DoS, không khắc phục responder sai.
11. **“Có OCSP stapling là Java tự bắt buộc mọi client phải thực thi.”** Phụ thuộc implementation và policy.
12. **“Dùng SOFT_FAIL cho administrator và guest như nhau.”** Thiếu phân loại rủi ro.
13. **“Metric validate success chứng minh đã có revocation evidence.”** Sai: soft-fail có thể cho success khi thiếu bằng chứng.
14. **“Không tìm thấy cert trong một CRL bất kỳ nghĩa là good.”** Sai: cần scope/issuer/time/authority đúng.
15. **“Bắt UNDETERMINED ở tầng ngoài rồi trả true tương đương PKIX SOFT_FAIL.”** Sai: làm mất điều kiện/semantics bảo mật của checker.

## 15. Câu hỏi tự kiểm tra

**1.** `UNDETERMINED_REVOCATION_STATUS` và `REVOKED` có giống nhau không?  
**Đáp:** Không. Undetermined là chưa có đủ bằng chứng; revoked là đã xác nhận bị thu hồi và phải từ chối.

**2.** Java SOFT_FAIL cho phép những nguyên nhân nào?  
**Đáp:** Lỗi mạng khi lấy OCSP/CRL và OCSP `internalError`/`tryLater`, có ràng buộc fallback; không phải mọi lỗi.

**3.** SOFT_FAIL có làm certificate đã có trong CRL hợp lệ trở thành đáng tin không?  
**Đáp:** Không. Lab CRL trả reason `REVOKED` dù SOFT_FAIL đang bật.

**4.** `NO_FALLBACK` có vai trò gì?  
**Đáp:** Tắt việc chuyển sang nguồn kiểm tra thu hồi dự phòng, khiến thất bại ở kênh được chọn có thể mang tính quyết định.

**5.** `PREFER_CRLS + NO_FALLBACK` có ý nghĩa gì?  
**Đáp:** Ưu tiên CRL và không fallback sang OCSP.

**6.** Vì sao `setRevocationEnabled(false)` trong ví dụ vẫn check OCSP?  
**Đáp:** Vì một `PKIXRevocationChecker` đã được thêm tường minh vào `PKIXParameters` và API quy định nó được dùng bất kể flag đó.

**7.** `getSoftFailExceptions()` dùng để làm gì?  
**Đáp:** Đọc các lỗi mà checker bỏ qua vì SOFT_FAIL, hỗ trợ audit nếu truy cập đúng instance sau validation.

**8.** Cache OCSP `good` vượt `nextUpdate` còn có thể báo “verified now” không?  
**Đáp:** Không; phải lấy chứng cứ còn hạn hoặc quyết định ngoại lệ degraded có giới hạn.

**9.** Vì sao dịch vụ mTLS quyền cao thường nghiêng về hard-fail?  
**Đáp:** Chấp nhận một credential đã bị CA thu hồi có thể nghiêm trọng hơn outage tạm thời, nhất là khi attacker cố tình chặn responder.

**10.** Vì sao không thể suy ra toàn bộ JSSE TLS client từ một lab `CertPathValidator`?  
**Đáp:** Trust manager, cấu hình revocation, provider và policy TLS khác nhau; phải kiểm thử tại đúng đường gọi production.

## Tóm tắt

```text
OCSP/CRL:
  VALID not-revoked evidence -> tiếp tục PKIX
  REVOKED evidence           -> REJECT
  UNDETERMINED              -> cần chính sách cụ thể

Java PKIXRevocationChecker.SOFT_FAIL:
  chỉ bỏ qua lỗi thuộc phạm vi được phép
  không bỏ qua REVOKED / sai chain / invalid signature
  ảnh hưởng bởi NO_FALLBACK / PREFER_CRLS
  getSoftFailExceptions giúp quan sát lỗi bỏ qua

Trade-off:
  HARD_FAIL -> bảo vệ tốt hơn trước bypass do mạng hỏng,
               nhưng có nguy cơ outage
  SOFT_FAIL -> cải thiện availability,
               nhưng có thể chấp nhận cert đã revoked nếu
               bằng chứng bị chặn hoặc không truy cập được

Thực hành an toàn:
  phân loại quyền -> chọn policy -> fallback/caching có kiểm chứng
  -> metrics/audit -> giới hạn soft fail -> test revoked thật.
```

**Ghi nhớ quan trọng nhất:** `SOFT_FAIL` không có nghĩa “certificate đã được xác nhận tốt”. Nó là **một ngoại lệ có rủi ro khi không lấy được trạng thái thu hồi**. Nếu áp dụng, phải minh bạch về phạm vi, thời hạn, cách giám sát và cách từ chối khi chứng cứ xác nhận `REVOKED`.

## Tài liệu tham khảo chính thức

- [Oracle Java 17 — PKIXRevocationChecker](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): OCSP/CRL, fallback, `getSoftFailExceptions`, clone và thread-safety.
- [Oracle Java 17 — PKIXRevocationChecker.Option](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXRevocationChecker.Option.html): chính xác các tùy chọn `SOFT_FAIL`, `NO_FALLBACK`, `PREFER_CRLS`, `ONLY_END_ENTITY`.
- [Oracle Java 17 — CertPathValidatorException.BasicReason](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.BasicReason.html): `REVOKED` và `UNDETERMINED_REVOCATION_STATUS`.
- [Oracle Java 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors và cert-path checkers.
- [Oracle Java 17 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): sử dụng `PKIXRevocationChecker` với validator/builder.
- [RFC 5280 — Certificate/CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): CRL profile, path validation và revocation.
- [RFC 6960 — OCSP](https://www.rfc-editor.org/rfc/rfc6960): good/revoked/unknown, error responses, freshness/authorized responder.
- [RFC 7633 — TLS Feature Extension](https://www.rfc-editor.org/rfc/rfc7633): TLS feature/must-staple, một cơ chế riêng với Java SOFT_FAIL.
