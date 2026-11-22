# 14.8 Phân tích CertPathValidatorException theo vị trí chứng thư và nguyên nhân

## Mục tiêu

Bài học thuộc **14. Đường dẫn tin cậy** của module Java Advance – security-cryptography. Sau bài này, bạn sẽ biết cách:

1. Đọc `CertPathValidatorException` của Java bằng **`getIndex()`, `getReason()`, `getCertPath()`, `getCause()` và `getMessage()`**, thay vì chỉ nhìn vào chuỗi “PKIX path validation failed”.
2. Liên hệ **index** với đúng certificate trong `CertPath`, đặc biệt quy tắc thông thường **index 0 = leaf**, index 1 = intermediate gần leaf và **trust anchor không nằm trong path**.
3. Phân biệt mã **`BasicReason`** (hết hạn, chữ ký sai, thu hồi, thuật toán bị hạn chế...) với **`PKIXReason`** (không có trust anchor phù hợp, sai KeyUsage, không phải CA, lỗi name chaining...).
4. Nhận diện **index = -1** là “không gắn được lỗi cho một certificate tại một chỉ số hợp lệ”, **không được tự suy ra root hỏng hoặc index âm là lỗi của root**.
5. Tạo fixture X.509 và chạy chương trình **Java 17+** để xác nhận các tình huống: path hợp lệ; trust anchor không liên quan; chữ ký leaf bị thay; chữ ký intermediate bị thay; leaf hết hạn ở thời điểm kiểm định giả lập.
6. Xây dựng quy trình chẩn đoán an toàn trong hệ thống TLS, PKIX, truststore, CRL/OCSP, chain provisioning và quan sát log mà **không vô hiệu hóa xác minh**.

**Giới hạn:** Một exception không cho phép kết luận “đã bị tấn công” hay “chắc chắn lỗi ở một chứng thư” nếu không đối chiếu path, reason, params và chính sách. Các kết quả `reason/index` trong ví dụ được kiểm thử bằng JDK hỗ trợ PKIX; nhà cung cấp dịch vụ bảo mật và đầu vào khác có thể báo khác. Không dùng cấu hình **tắt revocation** của lab để thay thế chính sách production.

## 1. `CertPathValidatorException` xuất hiện tại đâu?

Trong Java Security, một chuỗi chứng thư số X.509 thường được trình bày từ **certificate end-entity (leaf)** tới một hoặc nhiều **intermediate CA** và kết thúc tại **trust anchor** mà ứng dụng đã tin từ trước. Khi dùng PKIX:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
CertPathValidatorResult result = validator.validate(certPath, pkixParams);
```

Đoạn này là **snippet**, chưa phải chương trình độc lập: cần import `java.security.cert.CertPathValidator` và `CertPathValidatorResult`; `certPath` phải được dựng đúng thứ tự; `pkixParams` chứa trust anchors và các thông số kiểm định. `validate` kiểm tra path đã cung cấp theo thuật toán PKIX/chính sách, và khi phát hiện lỗi liên quan path thường ném `CertPathValidatorException`.

**Ba thao tác cần phân biệt:**

- `CertificateFactory.generateCertificate(...)` **parse chứng thư** từ DER/PEM. Parse được không đồng nghĩa tin cậy.
- `X509Certificate.verify(issuerPublicKey)` kiểm tra **chữ ký của đúng một certificate** bằng khóa issuer. Không kiểm tra cả chain/hostname/ủy quyền.
- `CertPathValidator.validate(...)` xét **cả path đã có** với trust anchors, constraints và các tham số. Nó vẫn không thay thế kiểm tra **hostname/SAN, expected issuer, mục đích nghiệp vụ và authorization** của ứng dụng.

Không nhầm `CertPathValidator` với `CertPathBuilder`: **builder** tìm/ghép đường dẫn từ certificate và nguồn chứng thư đã được cung cấp; **validator** xác minh một path cụ thể. Nếu không tìm được path, builder có thể ném **`CertPathBuilderException`** thay vì một `CertPathValidatorException` trực tiếp. Lớp lỗi TLS/JDBC/HTTP cao hơn có thể bọc các lỗi này trong `SSLHandshakeException` hoặc ngoại lệ kết nối khác.

### Ví dụ chain thông thường

```text
                 truststore của client (đã chọn trước)
          [Root CA certificate / trust anchor]
                         |
                root CA ký intermediate
                         |
             [Intermediate CA certificate]
                         |
               intermediate CA ký leaf
                         |
            [Leaf: api.example.test]
                         |
              dùng private key cho TLS
```

`TrustAnchor` có thể giữ certificate hoặc tên/khóa CA; **niềm tin bắt đầu từ cấu hình của bên kiểm tra**, không đến từ một root tự ký do peer bất kỳ gửi qua mạng. Trong `CertPath` cho PKIX thông thường, chỉ **leaf và intermediate** được liệt kê; trust anchor cung cấp riêng qua `PKIXParameters`.

## 2. Cấu trúc quan trọng của ngoại lệ

`java.security.cert.CertPathValidatorException` kế thừa `GeneralSecurityException` và cung cấp các getter rất hữu ích:

| API | Giá trị | Cách sử dụng đúng |
| --- | --- | --- |
| `e.getIndex()` | Chỉ số 0-based trong `CertPath` mà exception liên hệ, hoặc **`-1`** | Kiểm tra khoảng `0 <= index < path.size()` trước khi đọc certificate. Không coi `-1` là “root” |
| `e.getCertPath()` | Path liên quan lỗi, hoặc `null` khi không có thông tin | Dùng **path đi cùng exception** để tra certificate, thay vì đoán từ danh sách khác |
| `e.getReason()` | Một `CertPathValidatorException.Reason`, thường là `BasicReason` hoặc `PKIXReason` | Ưu tiên reason enum hơn parse message phụ thuộc provider |
| `e.getCause()` | Nguyên nhân bên dưới nếu có, có thể `null` | Hữu ích khi debug thư viện/validator khác; không tự coi message từ cause là mã lỗi bất biến |
| `e.getMessage()` | Văn bản do implementation cung cấp | Chỉ để hỗ trợ con người; không viết control flow dựa trên so khớp chuỗi |
| `e.getSuppressed()` | Những ngoại lệ bị suppressed nếu có | Kiểm tra khi công cụ bao bọc có sử dụng; không phải cách chính đọc PKIX reason |

**Cảnh báo:** `e.getIndex()` không nhất thiết “trỏ vào certificate gây ra **nguyên nhân vật lý**”. Nó báo **certificate tại đó validator ghi nhận lỗi**, với một lý do cụ thể. Ví dụ certificate leaf có `issuer` không khớp intermediate, validator có thể báo `NAME_CHAINING` tại một vị trí; có thể lỗi ban đầu là hệ thống lấy sai intermediate. Chẩn đoán cần kết hợp path, metadata và policies.

### Index nào là leaf, intermediate, root?

Với path được tạo bằng:

```java
CertificateFactory factory = CertificateFactory.getInstance("X.509");
CertPath path = factory.generateCertPath(
        List.of(leafCertificate, intermediateCertificate));
```

Đây là **snippet** cần có `leafCertificate`/`intermediateCertificate` đã parse và imports `java.security.cert.CertificateFactory`, `CertPath`, `java.util.List`. Java `generateCertPath(List)` giữ thứ tự list. Khi đó:

| Index | Certificate trong path | Vai trò |
| ---: | --- | --- |
| `0` | `leafCertificate` | End-entity/leaf |
| `1` | `intermediateCertificate` | Intermediate trực tiếp ký leaf |
| `2` (nếu có) | Intermediate cấp trên nữa | Đứng gần trust anchor hơn |
| **Không nằm trong path** | Root/trust anchor đã cấu hình | Không được tự gán index `path.size()` hoặc `-1` |

Bất kỳ điều kiện `getIndex() = -1` đều chỉ có nghĩa **index không chỉ định một certificate** (ví dụ không tìm được trust anchor phù hợp trong môi trường thử nghiệm); với path khác hoặc provider khác, tình huống có thể khác. **Index không được xem là một mức độ nghiêm trọng**: lỗi index 0 không “nhẹ hơn” lỗi index 1.

## 3. Hai nhóm `Reason` nên biết

Giá trị `getReason()` có kiểu interface `CertPathValidatorException.Reason`; Java định nghĩa các enum chính sau.

### 3.1 `CertPathValidatorException.BasicReason`

| Reason | Ý nghĩa cơ bản | Kiểm tra đầu tiên |
| --- | --- | --- |
| `UNSPECIFIED` | Không có reason cụ thể hơn được báo | Đọc cause, message, provider/debug log, path và params; **không suy đoán** |
| `EXPIRED` | Certificate bị coi là hết hiệu lực tại **ngày validation** | `NotAfter`, đồng hồ hệ thống, `PKIXParameters.getDate()` |
| `NOT_YET_VALID` | Certificate chưa tới `NotBefore` tại ngày validation | Clock skew, notBefore và thời gian được cấu hình |
| `REVOKED` | Validator đánh giá certificate đã bị thu hồi | CRL/OCSP, revocation policy, revocation date/reason (nếu có) |
| `UNDETERMINED_REVOCATION_STATUS` | Không đủ cơ sở xác định trạng thái thu hồi theo chính sách | Kết nối CRL/OCSP, timeout, responder, cache, fail-open/fail-closed |
| `INVALID_SIGNATURE` | Một chữ ký trong path không xác minh được theo khóa được chọn | Sai intermediate/issuer key, certificate bytes bị sửa, chain pha trộn |
| `ALGORITHM_CONSTRAINED` | Một thuật toán/key bị ràng buộc bởi chính sách bảo mật | JDK security policy, `jdk.certpath.disabledAlgorithms`, key size, digest, thời điểm dùng |

Danh sách này mô tả **ý nghĩa reason**, không bảo đảm một provider nhất định lúc nào cũng gán cùng enum cho cùng tình huống. Một số lỗi có thể thành `UNSPECIFIED` hoặc bị wrapper đổi dạng.

### 3.2 `java.security.cert.PKIXReason`

| Reason | Điều PKIX đang thông báo | Hướng điều tra |
| --- | --- | --- |
| `NO_TRUST_ANCHOR` | Path không nối tới một trust anchor được cung cấp phù hợp | Truststore thực tế, root key ID, CA cấu hình sai, incomplete/misordered chain |
| `NAME_CHAINING` | Liên kết tên issuer ↔ subject giữa certificate trong path không hợp lệ | Intermediate không tương ứng leaf, DN/issuer và key ID |
| `INVALID_KEY_USAGE` | Certificate/key usage không cho phép vai trò cần kiểm tra | `KeyUsage.keyCertSign` đối với CA, profile ký phù hợp |
| `INVALID_POLICY` | Certificate Policies hoặc policy constraints không thỏa mãn | Explicit policy, mapping, profile CA và params |
| `UNRECOGNIZED_CRIT_EXT` | Có critical extension không được validator hiểu/xử lý theo yêu cầu | Xem OID, policy, provider; **không tắt kiểm tra critical extension** |
| `NOT_CA_CERT` | Certificate tại vị trí CA không được phép đóng vai trò CA | `BasicConstraints: CA=true`, certificate profile |
| `PATH_TOO_LONG` | Vi phạm `pathLenConstraint` hoặc ràng buộc chiều sâu đường dẫn | Số CA trung gian (lưu ý self-issued), path builder/issuer chain |
| `INVALID_NAME` | Vi phạm ràng buộc tên, ví dụ `NameConstraints` | DNS/email/URI constraints của các CA trong path |

**`INVALID_NAME` không đồng nghĩa mọi lỗi hostname mismatch sẽ được `CertPathValidator` báo ở đây.** Hostname/SAN cho một HTTPS endpoint thường được kiểm tra **riêng** bởi JSSE/HTTP client sau hoặc trong TLS handshake; path PKIX có thể hợp lệ trong khi hostname sai.

### 3.3 Đừng sử dụng `getMessage()` làm “mã lỗi”

Ví dụ:

```java
if (e.getMessage().contains("expired")) {
    // Không an toàn để điều khiển chương trình theo văn bản provider.
}
```

Đây là minh họa **anti-pattern**, không phải cách nên sử dụng. Message phụ thuộc JDK/provider/ngôn ngữ/nguồn lỗi; có thể `null`, chứa thông tin nhạy cảm hoặc thay đổi sau nâng cấp. Thay vào đó, ưu tiên `e.getReason()` và `e.getIndex()`, rồi phân loại nội bộ. **Không** tự động sửa sai cấu hình truststore hoặc chấp nhận certificate dựa trên một reason string.

## 4. Quy trình đọc ngoại lệ theo thứ tự

Khi bắt được `CertPathValidatorException e`:

1. **Ghi bối cảnh kiểm định đã xác thực:** hệ thống nào, expected hostname/service/tenant, mục đích `serverAuth` hay `clientAuth`, thuật toán validation, JDK/provider version, thời điểm xét và chính sách revocation. Không tin “expected identity” do certificate chưa được xác minh tự khai.
2. **Lấy `reason` từ `e.getReason()`**: nó nêu loại vi phạm ở mức validator.
3. **Lấy `index` và `path` từ chính exception**: nếu index hợp lệ, lấy certificate **tại vị trí đó** để xem `Subject`, `Issuer`, `Serial`, `NotBefore/NotAfter`, BasicConstraints, KeyUsage, SKI/AKI và fingerprint.
4. Nếu **`index=-1`**, nêu rõ “lỗi không được gắn vào một certificate cụ thể”; so trust anchors, path construction, security parameters và error chain, **không gán cho root tùy ý**.
5. **Kiểm tra chain theo chiều leaf → issuer → trust anchor**: đúng intermediate? `Issuer DN` khớp? Chữ ký thật có hợp lệ? `BasicConstraints/KeyUsage` cho CA? Có thiếu intermediate? Có cross-sign/alternate chain?
6. **Kiểm tra chính sách path**: ngày validation, CA constraints, name constraints, các critical extensions, disabled algorithms, certificate policies, trust anchors và revocation.
7. **Kiểm tra endpoint identity và authorization riêng** sau path validation khi use case yêu cầu; không coi `CertPathValidator.validate` thành công là chứng minh hostname/role đúng.
8. **Khắc phục nguồn gốc và thử lại trên dữ liệu chuẩn** (đúng truststore/intermediate/certificate được phát hành lại), không chỉnh sửa chữ ký, tắt revocation hay trust-all để ép thành công.

Với exception nằm trong `SSLHandshakeException`, có thể duyệt `Throwable.getCause()` để tìm `CertPathValidatorException`; có khi lớp trên chỉ ném `CertPathBuilderException` vì không thể tìm được đường dẫn. Đừng lấy mọi lỗi handshake làm lỗi certificate: TLS còn có lỗi protocol/cipher/IO/peer alert.

## 5. Code phân tích index an toàn (snippet có thể tích hợp)

Đoạn **không độc lập** sau nằm trong một phương thức đã có `CertPathValidatorException e`, sử dụng `getCertPath()` thay vì đoán từ mảng input khác:

```java
int index = e.getIndex();
CertPath failedPath = e.getCertPath();
System.out.println("reason=" + e.getReason() + ", index=" + index);

if (failedPath != null
        && index >= 0
        && index < failedPath.getCertificates().size()) {
    X509Certificate bad = (X509Certificate)
            failedPath.getCertificates().get(index);
    System.out.println("subject=" + bad.getSubjectX500Principal());
    System.out.println("issuer=" + bad.getIssuerX500Principal());
    System.out.println("notAfter=" + bad.getNotAfter());
} else {
    System.out.println("No single path certificate index is available.");
}
```

Cần import `java.security.cert.CertPath` và `X509Certificate`. Đoạn này giả định certificate trong path là **X.509**; trong thư viện tổng quát cần kiểm tra `instanceof X509Certificate`. Khi đưa vào logging thật, không dùng `System.out`, tránh đưa nguyên chuỗi subject/issuer chứa dữ liệu cá nhân hoặc raw DER certificate vào log công khai; chỉ log trường cần thiết dưới quyền xem phù hợp.

**Điều quan trọng:** Vị trí `index` có ý nghĩa **trong `failedPath`**. Nếu bạn copy/reverse list, thêm trust anchor vào đầu, hoặc dùng chain theo thứ tự server gửi nhưng không kiểm chứng, bạn có thể báo sai “lỗi tại root” trong khi index thực là leaf.

## 6. Lab Java 17 có thể tái lập: năm kết quả PKIX

Trong lab, tạo:

```text
root.pem (self-signed CA; được chọn làm TrustAnchor)
     |
intermediate.pem (CA=true, được root ký)
     |
leaf.pem (CA=false, SAN=api.example.test, được intermediate ký)

rogue.pem (một self-signed CA độc lập, không ký chain trên)
```

Ta sẽ chạy các biến thể:

| Ca kiểm thử | Thao tác | Kết quả kỳ vọng trong JDK thử nghiệm |
| --- | --- | --- |
| **Valid chain** | Path `[leaf, intermediate]`, trust anchor root | `OK` |
| **Wrong trust anchor** | Cùng path, trust anchor là rogue | `index=-1`, `reason=NO_TRUST_ANCHOR` |
| **Tampered leaf signature** | Đổi bit cuối trong phần chữ ký DER của leaf, giữ nguyên intermediate | `index=0`, `reason=INVALID_SIGNATURE` |
| **Tampered intermediate signature** | Đổi bit cuối chữ ký DER intermediate, giữ nguyên leaf | `index=1`, `reason=INVALID_SIGNATURE` |
| **Expired leaf at future validation date** | `PKIXParameters.setDate` bằng ngày sau leaf NotAfter, trong khi intermediate còn hiệu lực | `index=0`, `reason=EXPIRED` |

Đây là **fixture thử nghiệm tự sinh** không có kết nối tới một máy chủ thực. Thao tác thay bit cuối DER chỉ để minh họa **chữ ký certificate không hợp lệ**; ngoài lab, không sửa certificate/DER để làm nó “hợp lệ”. Đoạn keytool dùng RSA 2048 bit cho sự tương thích lab, không nhằm chọn chính sách lâu dài cho mọi sản phẩm.

### 6.1 Sinh các certificate bằng `keytool` (PowerShell/Windows)

Tạo thư mục tạm riêng và chạy trọn script sau trong PowerShell với JDK 17+ có `keytool.exe` trên `PATH`. Script chỉ tạo fixture trong `%TEMP%\certpath-reason-training`; mật khẩu `changeit` là **dùng cho lab**. Không tái sử dụng keystore này trong môi trường thật.

```powershell
$ErrorActionPreference = 'Continue'
$dir = Join-Path $env:TEMP 'certpath-reason-training'
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Set-Location $dir
$p = 'changeit'

function Run-Keytool([string[]]$arguments) {
    $result = & keytool.exe @arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("keytool error: "
            + ($arguments -join ' ') + ' : ' + ($result -join ' '))
    }
}

if (Test-Path 'certs.p12') {
    Remove-Item -LiteralPath 'certs.p12' -Force
}

Run-Keytool @("-genkeypair","-alias","root","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Lab Root CA,O=Training",
    "-ext","BC=ca:true,pathlen:1",
    "-ext","KU=keyCertSign,cRLSign",
    "-storetype","PKCS12","-keystore","certs.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Run-Keytool @("-genkeypair","-alias","intermediate","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Lab Intermediate CA,O=Training",
    "-storetype","PKCS12","-keystore","certs.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Run-Keytool @("-certreq","-alias","intermediate",
    "-file","intermediate.csr",
    "-keystore","certs.p12","-storepass",$p)

Run-Keytool @("-gencert","-alias","root",
    "-infile","intermediate.csr",
    "-outfile","intermediate-issued.pem",
    "-rfc","-validity","365",
    "-ext","BC=ca:true,pathlen:0",
    "-ext","KU=keyCertSign,cRLSign",
    "-keystore","certs.p12","-storepass",$p)

Run-Keytool @("-importcert","-alias","intermediate",
    "-file","intermediate-issued.pem",
    "-keystore","certs.p12","-storepass",$p,"-noprompt")

Run-Keytool @("-genkeypair","-alias","leaf","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=api.example.test,O=Training",
    "-storetype","PKCS12","-keystore","certs.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Run-Keytool @("-certreq","-alias","leaf",
    "-file","leaf.csr",
    "-keystore","certs.p12","-storepass",$p)

Run-Keytool @("-gencert","-alias","intermediate",
    "-infile","leaf.csr","-outfile","leaf-issued.pem",
    "-rfc","-validity","7",
    "-ext","SAN=dns:api.example.test",
    "-ext","EKU=serverAuth",
    "-ext","KU=digitalSignature",
    "-keystore","certs.p12","-storepass",$p)

Run-Keytool @("-importcert","-alias","leaf",
    "-file","leaf-issued.pem",
    "-keystore","certs.p12","-storepass",$p,"-noprompt")

Run-Keytool @("-genkeypair","-alias","rogue","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Other Root CA,O=Training",
    "-ext","BC=ca:true,pathlen:1",
    "-ext","KU=keyCertSign,cRLSign",
    "-storetype","PKCS12","-keystore","certs.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

foreach ($alias in @("root","intermediate","leaf","rogue")) {
    Run-Keytool @("-exportcert","-alias",$alias,
        "-rfc","-file",("$alias.pem"),
        "-keystore","certs.p12","-storepass",$p)
}
Write-Output "Four PEM certificate fixture files generated"
```

**Đầu ra cuối trên môi trường đã kiểm thử:**

```text
Four PEM certificate fixture files generated
```

Script tạo bốn file cần cho Java: `root.pem`, `intermediate.pem`, `leaf.pem` và `rogue.pem`. Các file `intermediate-issued.pem` và `leaf-issued.pem` lưu certificate replies, còn `certs.p12` lưu các private key **chỉ phục vụ lab**. Bốn file PEM được xuất bằng `-exportcert` **không chứa private key**.

**Lưu ý:** Nếu keystore chứa aliases cũ hoặc script bị ngắt giữa chừng, nên xóa toàn bộ thư mục **lab vừa tạo** theo quy trình an toàn hoặc chọn thư mục tạm mới. Không xóa tệp khác chỉ vì có tên `certs.p12` ở nơi không phải thư mục lab. Trên macOS/Linux có thể dùng `keytool` tương đương với cú pháp Bash, nhưng đoạn trên dành riêng cho PowerShell.

**Tại sao leaf chỉ có validity 7 ngày?** Để chương trình có thể chọn một validation date **sau `leaf.getNotAfter()`** nhưng vẫn trong hạn intermediate 365 ngày. Nhờ vậy test `EXPIRED` tại index 0 không bị một intermediate hết hạn che khuất.

### 6.2 Chương trình Java 17 độc lập: `CertPathFailureDemo.java`

Lưu tệp **`CertPathFailureDemo.java`** trong đúng thư mục có các PEM và chạy. Code parse các file, dựng path theo thứ tự **leaf rồi intermediate**, gọi PKIX với trust anchor cụ thể, tạo dữ liệu sai **chỉ trong bộ nhớ** để test lỗi chữ ký, và dùng `getIndex/getReason/getCertPath` để báo lỗi.

```java
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.List;
import java.util.Set;

public final class CertPathFailureDemo {
    private static final CertificateFactory FACTORY = certificateFactory();

    public static void main(String[] args) throws Exception {
        X509Certificate root = load("root.pem");
        X509Certificate intermediate = load("intermediate.pem");
        X509Certificate leaf = load("leaf.pem");
        X509Certificate otherRoot = load("rogue.pem");

        CertPath valid = path(leaf, intermediate);
        System.out.println("Path order: index 0=leaf; index 1=intermediate");
        diagnose("Valid chain", valid, root, null);
        diagnose("Wrong trust anchor", valid, otherRoot, null);
        diagnose("Tampered leaf signature",
                path(tamperSignature(leaf), intermediate), root, null);
        diagnose("Tampered intermediate signature",
                path(leaf, tamperSignature(intermediate)), root, null);

        Date future = Date.from(
                leaf.getNotAfter().toInstant().plus(1, ChronoUnit.DAYS));
        diagnose("Expired leaf at future validation date",
                valid, root, future);

        System.out.println("Leaf is CA: " + (leaf.getBasicConstraints() >= 0));
        System.out.println("Intermediate is CA: "
                + (intermediate.getBasicConstraints() >= 0));
    }

    private static CertificateFactory certificateFactory() {
        try {
            return CertificateFactory.getInstance("X.509");
        } catch (GeneralSecurityException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    private static X509Certificate load(String file) throws Exception {
        try (InputStream input = Files.newInputStream(Path.of(file))) {
            return (X509Certificate) FACTORY.generateCertificate(input);
        }
    }

    private static X509Certificate tamperSignature(X509Certificate source)
            throws Exception {
        byte[] der = source.getEncoded();
        der[der.length - 1] ^= 1;
        try (ByteArrayInputStream input = new ByteArrayInputStream(der)) {
            return (X509Certificate) FACTORY.generateCertificate(input);
        }
    }

    private static CertPath path(X509Certificate leaf,
                                 X509Certificate intermediate)
            throws CertificateException {
        return FACTORY.generateCertPath(List.of(leaf, intermediate));
    }

    private static void diagnose(String label, CertPath path,
                                 X509Certificate trustedRoot, Date date)
            throws GeneralSecurityException {
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(trustedRoot, null)));
        params.setRevocationEnabled(false); // Offline lab ONLY.
        if (date != null) {
            params.setDate(date);
        }

        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            System.out.println(label + ": OK");
        } catch (CertPathValidatorException e) {
            int index = e.getIndex();
            String certificate = "none";
            CertPath failedPath = e.getCertPath();
            if (failedPath != null && index >= 0
                    && index < failedPath.getCertificates().size()) {
                X509Certificate subject = (X509Certificate)
                        failedPath.getCertificates().get(index);
                certificate = subject.getSubjectX500Principal()
                        .getName().contains("Intermediate") ?
                        "intermediate" : "leaf";
            }
            System.out.println(label + ": index=" + index
                    + " reason=" + e.getReason()
                    + " cert=" + certificate);
        }
    }
}
```

Lệnh biên dịch/chạy trên PowerShell (vẫn ở thư mục lab):

```powershell
javac --release 17 CertPathFailureDemo.java
java -cp . CertPathFailureDemo
```

**Stdout đã kiểm thử trên JDK Java 17 hỗ trợ PKIX:**

```text
Path order: index 0=leaf; index 1=intermediate
Valid chain: OK
Wrong trust anchor: index=-1 reason=NO_TRUST_ANCHOR cert=none
Tampered leaf signature: index=0 reason=INVALID_SIGNATURE cert=leaf
Tampered intermediate signature: index=1 reason=INVALID_SIGNATURE cert=intermediate
Expired leaf at future validation date: index=0 reason=EXPIRED cert=leaf
Leaf is CA: false
Intermediate is CA: true
```

Trong chương trình, phần tên `cert=leaf` hoặc `cert=intermediate` là **nhãn riêng của fixture**: helper xem subject DN có chuỗi `Intermediate` hay không; không dùng cách nhận diện tên này trong hệ thống thật. Ứng dụng production nên log subject/issuer/fingerprint được **trích từ certificate tại index hợp lệ**, và đối chiếu với expected chain. Đừng điều khiển authorization dựa trên việc subject chứa một từ như “Root” hoặc “Intermediate”.

### 6.3 Tại sao kết quả này đáng tin?

- **Valid chain: OK:** Root đã được **trực tiếp chọn** thành `TrustAnchor`, intermediate có `CA=true`/`keyCertSign` và leaf do intermediate ký. Lab không thực hiện kết nối TLS/hostname.
- **Wrong trust anchor: index=-1 reason=NO_TRUST_ANCHOR:** Root `rogue.pem` tự ký hợp lệ nhưng **không liên quan** chain này. Validator không có anchor phù hợp. **`-1` trong ca này không chỉ một certificate “root lỗi” ở index -1**.
- **Tampered leaf signature: index=0 INVALID_SIGNATURE:** Đổi một bit cuối DER khiến chữ ký leaf không còn khớp public key intermediate. Path vẫn có hai certificate; lỗi gắn ở **leaf (index 0)**.
- **Tampered intermediate signature: index=1 INVALID_SIGNATURE:** Chữ ký intermediate không còn khớp public key root. Leaf có thể vẫn có chữ ký hợp lệ theo public key intermediate; lỗi gắn ở **intermediate (index 1)**.
- **Expired leaf at future validation date: index=0 EXPIRED:** `params.setDate(future)` thay thời điểm validation, không chỉnh certificate bytes. Leaf có thời hạn 7 ngày; intermediate có 365 ngày; ngày giả lập vượt leaf NotAfter.
- **CA checks:** `leaf.getBasicConstraints()<0` và `intermediate.getBasicConstraints()>=0`, phản ánh profile leaf/CA. Không đủ để tự chứng minh trust.

**Đây là kết quả cho fixture đã kiểm thử, không phải bảng ánh xạ bắt buộc với mọi provider.** Trên JDK/provider khác, policy, thời gian tạo, extension, security properties hoặc cách dựng path có thể làm reason/exception thay đổi; **không viết unit test production bắt buộc mọi hệ thống có đúng message string**.

### 6.4 Tại sao phải dùng `getCertPath()` từ exception?

Nếu `CertPathValidator` được gọi qua một thư viện, path thật có thể là path được builder chọn, không phải danh sách certificate mà bạn nghĩ server gửi. `e.getCertPath()` (nếu có) là path được gắn trong exception; tra certificate theo `e.getIndex()` và kiểm tra giới hạn giúp tránh gắn sai lỗi cho một intermediate khác.

Với `index=-1`, code giữ `cert=none`; **không lấy phần tử cuối của path rồi gọi nó là root**, và không cố đọc `path.getCertificates().get(-1)`. Với list certificate rỗng/path null, cũng không cố truy cập theo index.

## 7. `PKIXParameters` quyết định câu trả lời của validator

Hai lần gọi `validate` với **cùng certificate path** có thể cho kết quả khác nhau khi tham số thay đổi. Các tham số quan trọng:

- **`TrustAnchors`:** root/CA key đã được provision từ nguồn tin cậy. Danh sách khác nhau giữa JDK, container, JVM, custom truststore và OS có thể làm kết quả khác.
- **`Date`:** `params.setDate(date)` cho phép kiểm định tại thời điểm xác định; nếu không đặt, thường là thời điểm hiện tại. Dùng thời gian đúng theo hợp đồng hệ thống và xem xét clock skew.
- **`RevocationEnabled` và `PKIXRevocationChecker`:** chính sách CRL/OCSP/cache/responder, độ tin cậy và khi mạng không truy cập được. Trạng thái thu hồi không thể suy ra từ hạn `NotAfter`.
- **`InitialPolicies` / explicit-policy-required:** các certificate policies/constraints được chấp nhận; khác nhau theo purpose, tenant, hệ thống.
- **`CertStores`:** nguồn intermediate/CRL để xây dựng và kiểm tra path, tùy workflow. Validator không tự “sửa” missing issuer chỉ vì certificate có URL AIA.
- **`AlgorithmConstraints`/JDK security properties:** khóa yếu, digest và thuật toán không còn được policy cho phép, có thể cho `ALGORITHM_CONSTRAINED`. Không tắt policy để chạy certificate cũ trừ khi có quyết định rủi ro được đánh giá và lộ trình thay thế.

**Cảnh báo rất quan trọng:** Lab dùng `params.setRevocationEnabled(false)` để chạy offline không cần CRL/OCSP. Trên production, cấu hình kiểm tra thu hồi phải theo chính sách bảo mật của use case. Khi gặp `UNDETERMINED_REVOCATION_STATUS` không được tự bật `false` để “sửa lỗi” nếu chính sách yêu cầu kiểm tra thu hồi.

### Validation date không bằng “ngày phát hành certificate”

Certificate có `NotBefore/NotAfter` riêng. Thời điểm `PKIXParameters.getDate()` dùng để xét hiệu lực không tự biến một certificate hết hạn thành còn hiệu lực. Không “chỉnh đồng hồ” hoặc chọn ngày tùy ý nhằm bỏ qua certificate hết hạn ngoài một use case được thiết kế rõ (ví dụ kiểm chứng dữ liệu ký lâu dài kèm timestamp/evidence được đánh giá phù hợp).

### Root trust anchor và path

Với Java PKIX thông thường, trust anchor **được cung cấp riêng** chứ không nhất thiết là phần tử trong `CertPath`. Trạng thái validity của trust-anchor certificate không tự được xử lý y hệt certificate nằm trong path; chính sách quản trị root/truststore và các bước bổ sung có thể khác. **Đừng suy ra `index=-1` nghĩa là root hết hạn**; đó chỉ là không có index cụ thể được gán trong exception.

## 8. Những reason phổ biến trong hệ thống thật

### 8.1 `NO_TRUST_ANCHOR` hoặc “PKIX path building failed”

Hãy hỏi: ứng dụng **đang chạy trên JVM nào**, tải truststore nào, trust anchors gồm những CA nào? Server có gửi **đúng intermediate** không? Có cross-signing khiến client cũ cần một đường dẫn khác không? Certificate có issuer thật được ký bởi public key nào?

- Dùng `keytool -list -v -keystore ...` hoặc công cụ quản trị truststore tương ứng để kiểm tra **có kiểm soát**. `cacerts` của JVM và truststore custom/container có thể khác nhau.
- So issuer/subject, SKI/AKI và signature link để hiểu intermediate; nhưng **chỉ so DN chưa đủ** để chứng minh issuer ký.
- Nếu server không gửi intermediate, có thể phải sửa **certificate chain server-side** hoặc provisioning ở phía ứng dụng. Không tự đưa root mới từ response của server vào truststore.
- Với các certificate tự ký của môi trường nội bộ, pin/trust anchor chỉ được cài khi danh tính/khóa đã được xác thực qua kênh đáng tin.

Cần phân biệt `CertPathBuilderException` (không tìm được path) với `CertPathValidatorException` (một path được kiểm tra và thất bại). Lỗi ở tầng TLS có thể bọc cả hai. **Đừng giả định builder thất bại có một `getIndex()`**.

### 8.2 `EXPIRED` và `NOT_YET_VALID`

Kiểm tra `NotBefore/NotAfter` của certificate **được index nêu ra**, đồng hồ máy, múi giờ/UTC và validation date thực tế. Một intermediate hết hạn có thể khiến **nhiều leaf** cùng gặp lỗi dù leaf còn hiệu lực.

Không sửa bằng cách tắt validity validation. Quy trình đúng là renew/replace certificate theo chain phù hợp, cập nhật issuer/intermediate nếu cần, kiểm tra lại key usage, SAN/EKU, chính sách và triển khai có rollback.

### 8.3 `INVALID_SIGNATURE`

Bắt đầu từ **certificate tại index**, tìm **issuer key phù hợp** trong certificate phía trên hoặc trust anchor; kiểm tra chữ ký bằng khóa đó trong môi trường debug. Các nguyên nhân hay gặp: leaf đi kèm intermediate sai, trộn chain từ hai đợt phát hành, certificate DER bị hỏng hoặc issuer key rollover. Việc message đề cập “signature” **không có nghĩa chữ ký dữ liệu ứng dụng bị sai**; ở đây là **chữ ký của X.509 certificate** trong path.

Đừng “khắc phục” bằng việc chuyển sang trust-all, bỏ qua signature link hoặc dùng public key từ payload chưa xác thực.

### 8.4 `NOT_CA_CERT`, `INVALID_KEY_USAGE`, `PATH_TOO_LONG`

Trọng tâm là **vai trò CA**:

- Intermediate phải có `BasicConstraints: CA=true` và `KeyUsage.keyCertSign` khi extension yêu cầu.
- `pathLenConstraint=0` ở một intermediate nghĩa là không có **CA intermediate không tự phát hành** thêm bên dưới (nhưng vẫn có thể cấp leaf).
- Certificate `CA=false` không được tự nâng thành CA chỉ vì private key của nó có thể ký một chữ ký kỹ thuật.

Kiểm tra bản profile được cấp bởi CA, không tự “vá” extension local vì certificate được ký: thay một byte extension làm chữ ký certificate sai. Cần phát hành lại certificate đúng quy trình.

### 8.5 `REVOKED` / `UNDETERMINED_REVOCATION_STATUS`

Certificate có thể đã bị thu hồi dù chưa tới `NotAfter`. Xem CRL/OCSP, cache, responder, network controls, nonce/stapling nếu áp dụng và chính sách khi không có kết quả. Một exception revocation có thể chứa dữ liệu chi tiết trong `cause` (ví dụ `CertificateRevokedException`); xử lý có kiểm soát, tránh lộ ra client.

`UNDETERMINED_REVOCATION_STATUS` **không đồng nghĩa certificate sạch**. Nó cho biết không xác định được trạng thái theo chính sách. Có hệ thống dùng soft-fail có đánh giá rủi ro, nhưng quyết định này **không nên phát sinh tự động từ một catch block**.

### 8.6 `ALGORITHM_CONSTRAINED`

Mật mã path có thể bị policy từ chối dù chữ ký tự thân toán học còn verify được: RSA modulus quá nhỏ, SHA-1 hoặc thuật toán không được dùng trong mục đích này, thời điểm sử dụng không thỏa policy. Kiểm tra `java.security`, `jdk.certpath.disabledAlgorithms` và thông số JDK/provider triển khai.

Phương án bền vững là phát hành lại chain theo scheme/key size được phép, cùng lộ trình tương thích. **Không** vô hiệu hóa constraints trên toàn JVM để một certificate yếu tiếp tục hoạt động.

### 8.7 `INVALID_NAME` không phải mọi lỗi hostname mismatch

`INVALID_NAME` có thể gắn với **NameConstraints** trong chain. Nhưng TLS endpoint identity (DNS SAN/IP) của certificate leaf so với tên máy bạn kết nối thường là bước **bên ngoài generic PKIX path validation**. Một path có thể `validate == OK` nhưng TLS handshake bị chặn do SAN không khớp. Đừng “sửa” bằng cách hạ expected hostname hoặc sửa `CN`.

## 9. Khi exception bị bọc trong TLS hoặc thư viện

Thường thấy stack kiểu:

```text
javax.net.ssl.SSLHandshakeException
  -> javax.net.ssl.SSLException / ValidatorException (tùy provider)
      -> java.security.cert.CertPathValidatorException
```

Hoặc:

```text
javax.net.ssl.SSLHandshakeException
  -> sun.security.provider.certpath.SunCertPathBuilderException
     (không xây dựng được đường dẫn tin cậy)
```

Hai sơ đồ là **hình minh họa cấu trúc thường gặp**, không cam kết tất cả JDK/provider có cùng chuỗi cause hay cho phép import lớp nội bộ `sun.*`. Không viết logic nghiệp vụ phụ thuộc tên lớp Sun internal. Ví dụ snippet bên dưới là **đoạn phụ trợ**, không phải chương trình độc lập:

```java
static CertPathValidatorException findValidationProblem(Throwable error) {
    Throwable current = error;
    int depth = 0;
    while (current != null && depth++ < 20) {
        if (current instanceof CertPathValidatorException found) {
            return found;
        }
        current = current.getCause();
    }
    return null;
}
```

Đặt trong một class, import `java.security.cert.CertPathValidatorException`. Giới hạn `depth` tránh loop bất thường trong exception chain; trong thư viện thực có thể xem thêm suppressed causes. Nếu trả `null`, không kết luận certificate đúng: có thể lỗi thuộc builder/hostname/protocol hoặc bị che bởi wrapper.

**Cẩn thận:** Không “catch tất cả `SSLHandshakeException` rồi kết luận `NO_TRUST_ANCHOR`”. Ghi loại lỗi thật, xác định mục đích TLS và phân loại theo các lớp thông tin có sẵn.

## 10. Logging và debug thực tế

### 10.1 Những trường có giá trị điều tra

Một log nội bộ (được hạn chế quyền) có thể ghi:

| Field | Tại sao cần? | Cách xử lý |
| --- | --- | --- |
| `correlationId` | Ghép sự kiện request với certificate failure | Không lộ dữ liệu nhạy cảm từ request |
| `validationAlgorithm`, `provider`, `javaVersion` | Tìm khác biệt giữa JVM/provider và thuật toán | Lưu phiên bản cấu hình đủ để tái hiện |
| `exceptionReason` | Phân loại ổn định hơn message text | Dùng enum, có fallback `UNSPECIFIED` |
| `pathIndex` và `pathLength` | Xác định certificate trong path theo vị trí | Nêu `-1` là không có certificate index |
| `certificateSubject/Issuer/Fingerprint` | Gắn lỗi vào certificate thực tế | Lọc PII, dùng SHA-256 fingerprint thay vì log nguyên DER |
| `expectedHostname/Role/Tenant` | So với danh tính cần xác thực | Nguồn từ policy/ngữ cảnh đã tin |
| `validationDate/NotBefore/NotAfter` | Điều tra hết hạn/đồng hồ | Dùng timezone rõ ràng |
| `trustAnchorId` / `truststoreVersion` | Phân biệt cấu hình giữa môi trường | Không ghi mật khẩu truststore hoặc key riêng |
| `revocationPolicy/Result` | Phân biệt revoked và không xác định được trạng thái | Không log OCSP secrets/nhạy cảm nếu có |

**Không log private key, keystore password, token, session secrets hoặc thông tin khách hàng không cần thiết**. Certificate public có thể chứa danh tính/địa chỉ nên vẫn phải tuân thủ chính sách log.

### 10.2 Bật debug có kiểm soát

Ví dụ khi chạy một ứng dụng Java (chỉ dành cho troubleshooting ở môi trường an toàn):

```powershell
java -Djava.security.debug=certpath -cp . CertPathFailureDemo
```

Đây là lệnh có thêm **debug trace**, không phải stdout cố định. JDK có thể in dữ liệu path/trust/algorithms rất dài; bảo vệ trace, bật có thời hạn và không để trong log public.

Với JSSE/TLS, có thể dùng option:

```powershell
java -Djavax.net.debug=ssl,handshake,trustmanager -cp . YourTlsClient
```

`YourTlsClient` chỉ là tên minh họa của một ứng dụng TLS **đã tồn tại**, không phải class do lab tạo. Một số shell/JVM yêu cầu quoting tham số khác. TLS debug có thể chứa certificate chains và metadata nhạy cảm; không mặc định để debug trong production.

### 10.3 Giới hạn của ví dụ lab

Chương trình `CertPathFailureDemo` gọi validator trực tiếp, **không làm TLS handshake**, không verify hostname trên mạng và không thực hiện revocation vì fixture offline. Nó cũng không chứng minh certificate không bị lộ private key. Để triển khai một TLS client, dùng JSSE/HTTP client với trust manager, endpoint identification và policy đúng; **không** lấy kết quả `CertPathValidator.validate(path)==OK` làm toàn bộ quyết định kết nối.

## 11. Bảng tra nhanh index + reason

| Quan sát | Không nên kết luận ngay | Cần làm |
| --- | --- | --- |
| `index=0, reason=EXPIRED` | “Root đã hết hạn” | Xem certificate index 0 trong `getCertPath()`, thường leaf |
| `index=1, reason=INVALID_SIGNATURE` | “Chữ ký ứng dụng sai” | Xem intermediate index 1 và issuer key ký certificate của nó |
| `index=-1, reason=NO_TRUST_ANCHOR` | “Certificate ở index -1 là root bị lỗi” | So trusted anchors với chain/cross-sign; không có cert index tương ứng |
| `index=0, reason=INVALID_SIGNATURE` | “Leaf chắc chắn bị hacker sửa” | Kiểm tra đúng intermediate, chain và bytes; lỗi có thể do thao tác vận hành |
| `reason=ALGORITHM_CONSTRAINED` | “Cứ bật lại thuật toán yếu” | Xem `java.security` policy, key strength và phát hành lại chain |
| `reason=UNDETERMINED_REVOCATION_STATUS` | “Certificate không bị revoke” | Kiểm tra revocation checker/responder/network và fail policy |
| `reason=NOT_CA_CERT` | “CA thiếu một nhãn hiển thị” | Kiểm tra BasicConstraints thực được ký và profile CA |
| `reason=INVALID_NAME` | “Hostname TLS sai” | Xem NameConstraints của path, đồng thời kiểm tra hostname/SAN **riêng** |
| `getCertPath()==null` | “Không có certificate nên chắc chắn không liên quan PKIX” | Path không được cung cấp trong exception; kiểm tra cause và context |
| Lỗi `CertPathBuilderException` | “Gọi `getIndex` trực tiếp được” | Builder thất bại khác validator; xem wrapper/cause/issuer source |
| `CertPathValidator.validate()==OK` | “Truy cập API tự động được phép” | Kiểm tra đúng endpoint identity, EKU, tenant/role và authorization |

## 12. Các lỗi lập trình thường gặp

1. **Reverse chain khi đọc index:** Phần tử 0 trong list demo là **leaf**, không phải root. `CertPath` có thứ tự xác định.
2. **Coi `-1` là root:** Root/trust anchor không có index trong path, và `-1` không gắn cho bất kỳ certificate cụ thể nào.
3. **Dùng `getMessage().contains(...)` để xử lý logic:** message thay đổi theo provider, locale, bản JDK và tình huống.
4. **Chỉ xét certificate tại index mà bỏ context:** đúng certificate cũng có thể bị validator gắn lỗi do thiếu issuer/truststore/params.
5. **Gán tất cả lỗi TLS cho PKIX:** certificate builder failure, hostname mismatch, protocol mismatch, TLS alert và IO khác nhau.
6. **Tắt revocation sau khi gặp `UNDETERMINED_REVOCATION_STATUS`:** đây là thay đổi chính sách bảo mật, không phải sửa lỗi an toàn mặc định.
7. **Lấy root trong handshake làm trust anchor:** attacker có thể gửi root tự ký của họ. Trust phải provision ngoài đường truyền chưa tin.
8. **Import bất kỳ issuer mới vào `cacerts`:** thay đổi vùng tin cậy của cả JVM; cần quy trình xác minh, duyệt và giới hạn.
9. **Sửa certificate DER thủ công để đổi extension/validity:** làm mất chữ ký CA. Cần CA phát hành lại.
10. **Nhầm `EXPIRED` của leaf với hệ thống thời gian sai luôn luôn:** phải so `NotAfter` với validation date; đồng hồ có thể đúng và cert thực sự hết hạn.
11. **Nhầm `INVALID_SIGNATURE` với `Signature.verify` của payload:** ở đây chủ đề là certificate signature trong PKIX.
12. **Dùng subject CN làm hostname matcher thủ công:** hostname/SAN phải theo chuẩn TLS (DNS/IP, wildcard, IDNA) và expected target.
13. **Dùng root trust anchor thử nghiệm của lab trong production:** phá ranh giới niềm tin, đặc biệt vì private key lab tồn tại trong PKCS#12 cùng mật khẩu dễ đoán.
14. **Chỉ kiểm tra `Reason` để cho phép truy cập:** lý do exception là tín hiệu thất bại, không phải token quyền. Mọi failure phải từ chối đường dẫn tương ứng.
15. **Nuốt ngoại lệ sau khi log:** nếu validation fail, không gọi tiếp nghiệp vụ như thể có certificate hợp lệ.
16. **Thử tất cả truststore đến khi có path OK:** nguy hiểm nếu tập anchors thử chứa root không được policy chấp thuận. Xác định đúng trust configuration từ trước.

## 13. Checklist cho dịch vụ Java

- [ ] Xác định đúng **expected endpoint/identity/role/tenant** từ nguồn tin cậy.
- [ ] Ghi nguồn `CertPath` đang validate và thứ tự certificate rõ ràng, không đảo list tùy tiện.
- [ ] Khi bắt lỗi, lấy `getReason()`, `getIndex()`, `getCertPath()` với kiểm tra index bounds.
- [ ] Với index hợp lệ, đối chiếu certificate **tại index trong path của exception**, không suy từ tên file.
- [ ] Với `index=-1`, giữ nhãn “không có certificate index”, kiểm tra truststore/params/cause.
- [ ] Ưu tiên `BasicReason`/`PKIXReason` cho phân loại; không dùng chuỗi `getMessage` làm mã lỗi duy nhất.
- [ ] Trust anchors được provision đáng tin; certificate server gửi không tự động biến thành trusted anchor.
- [ ] Intermediate có đúng issuer/signature, CA BasicConstraints, KeyUsage, pathLen và constraints khác.
- [ ] Time, signature schemes, key size, algorithm constraints và chính sách revocation được cấu hình nhất quán.
- [ ] Endpoint identity/SAN, EKU/application purpose và authorization kiểm tra **ngoài** generic PKIX path.
- [ ] Không tắt certificate validation, hostname verification hoặc revocation chỉ để “hết lỗi”.
- [ ] Có test happy path, wrong anchor, tampered leaf, tampered intermediate, expired leaf, missing issuer, key usage và revocation policy.
- [ ] Log có correlationId/provider/đường dẫn/path index/reason theo quyền, tránh tiết lộ secrets.
- [ ] Có quy trình cập nhật truststore, certificate rotation, CRL/OCSP monitoring và diễn tập phục hồi.

## 14. Bài tập

1. Chạy `CertPathFailureDemo.java`. Tại sao hai test `Tampered leaf` và `Tampered intermediate` đều có reason `INVALID_SIGNATURE` nhưng index lần lượt `0` và `1`?
2. Đổi thứ tự `List.of(leaf, intermediate)` thành `List.of(intermediate, leaf)`. Hãy ghi lại reason/index của JDK; vì sao không còn được đọc index theo sơ đồ ban đầu?
3. Giữ nguyên certificate path, thay trust anchor bằng `rogue.pem`. Có phải `rogue.pem` “không tự ký hợp lệ” không? Vì sao vẫn gặp `NO_TRUST_ANCHOR`?
4. Đặt validation date vào thời điểm trước `leaf.getNotBefore()`. Reason nào xuất hiện trên JDK của bạn và tại index nào? Thử so với intermediate validity.
5. Tạo intermediate có `BasicConstraints:CA=false` rồi cho nó cấp leaf, thử validate. Bạn mong chờ nhóm `PKIXReason` nào? Có thể `leaf.verify(intermediateKey)` vẫn thành công không?
6. Kiểm tra một chain server TLS thiếu intermediate. Phân biệt lỗi builder không tìm được đường dẫn với validator có đường dẫn nhưng bị lỗi chữ ký. Bạn sẽ bổ sung intermediate ở phía nào cho đúng?
7. Làm một bảng chẩn đoán cho `ALGORITHM_CONSTRAINED` khi một môi trường JDK chặn thuật toán hoặc key size mà môi trường cũ còn chấp nhận. Đề xuất biện pháp không hạ chuẩn bảo mật.
8. Với `UNDETERMINED_REVOCATION_STATUS`, thiết kế runbook kiểm tra CRL/OCSP, cache, proxy/firewall và fail policy. Vì sao không nên vô hiệu hóa revocation trong production?
9. Thêm helper lấy SHA-256 fingerprint của certificate **tại getIndex() hợp lệ**; ghi trong log nội bộ bằng hex, không in private key hay secret.
10. Một path PKIX hợp lệ cho certificate `api-b.example.test` nhưng ứng dụng gọi `api-a.example.test`. Bước kiểm tra nào vẫn có thể fail? Vì sao `CertPathValidatorException` không phải tín hiệu duy nhất cho TLS hostname mismatch?

## Tài liệu tham khảo chính thức

- [Java SE 17 — CertPathValidatorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.html): `getIndex`, `getReason`, `getCertPath` và constructors.
- [Java SE 17 — CertPathValidatorException.BasicReason](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.BasicReason.html): `EXPIRED`, `INVALID_SIGNATURE`, `REVOKED`, `UNDETERMINED_REVOCATION_STATUS`, `ALGORITHM_CONSTRAINED`.
- [Java SE 17 — PKIXReason](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXReason.html): `NO_TRUST_ANCHOR`, `NOT_CA_CERT`, `NAME_CHAINING` và các reason PKIX khác.
- [Java SE 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): kiểm định đường dẫn và thuật toán PKIX.
- [Java SE 17 — CertPathBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): tìm/dựng đường dẫn và khác biệt với validation.
- [Java SE 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, date, revocation, policy.
- [Java SE 17 — X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): subject, issuer, validity, BasicConstraints, SAN/EKU, chữ ký.
- [JDK 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): sinh CSR, ký certificate, import reply, export PEM.
- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): chứng thư X.509, trust/path, validity, BasicConstraints, Certificate Policies và CRL.
