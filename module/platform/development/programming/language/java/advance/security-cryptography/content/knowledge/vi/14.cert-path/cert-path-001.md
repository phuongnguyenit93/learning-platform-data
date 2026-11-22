# 14.1 Mô hình `CertPath`, `TrustAnchor` và chứng thư trung gian

## 1. Mục tiêu: một chứng thư hợp lệ về chữ ký chưa đủ để được tin cậy

Trong Java Security / PKI, **chứng thư X.509** (*certificate*) thường gắn một **public key** với một **subject** (chủ thể) và mang chữ ký của **issuer** (bên cấp). Việc một chứng thư có chữ ký kiểm tra được **không tự động** có nghĩa ứng dụng phải tin public key ấy: trước hết phải xác định issuer đó có được trao quyền cấp chứng thư hay không, rồi lần ngược qua các **chứng thư CA trung gian** đến **điểm neo tin cậy (`TrustAnchor`)** đã được ứng dụng chấp nhận từ trước.

Bài học này giải thích ba thành phần chính:

- **`CertPath`:** một **đường dẫn chứng nhận** (*certification path*), tức chuỗi chứng thư mục tiêu và các chứng thư trung gian theo quy tắc thứ tự của Java.
- **`TrustAnchor`:** điểm xuất phát được **tin cậy theo chính sách/cấu hình bên ngoài đường dẫn**, thường đại diện cho CA gốc, có thể biểu diễn bằng chứng thư CA đã được tin cậy hoặc tên CA + public key.
- **Chứng thư trung gian (`intermediate CA certificate`):** chứng thư CA nằm giữa certificate mục tiêu và điểm neo; nó **không mặc nhiên được tin cậy**, mà được xác thực bởi CA ở phía trên theo quy tắc PKIX.

Nội dung dùng mô hình **PKIX / RFC 5280** và Java 17+. Ví dụ thực nghiệm có **root → intermediate → leaf**, sử dụng `CertificateFactory`, `CertPathValidator`, `PKIXParameters`, `CertPathBuilder`, `CertStore` và `TrustAnchor`.

**Điều quan trọng nhất:** *Dữ liệu certificate chain được bên kia gửi đến không phải danh sách trusted roots.* CA gốc chỉ là trust anchor sau khi **chính ứng dụng hoặc môi trường tin cậy đã phê duyệt** nó. Không được chấp nhận bất kỳ chứng thư tự ký (*self-signed*) nào chỉ vì chữ ký tự kiểm tra thành công.

## 2. Một đường dẫn tin cậy trông như thế nào?

Giả sử dịch vụ `demo.example.invalid` có chứng thư leaf do **Intermediate CA** ký; Intermediate CA do **Root CA** ký:

```text
                          PHÍA CẤP / CẤU HÌNH TIN CẬY

         +----------------------------------------------------+
         | Root CA: TrustAnchor đã được cài và tin cậy        |
         | Subject: CN=Training Root CA                        |
         | Public key gốc được quản trị, không lấy theo peer  |
         +---------------------------+------------------------+
                                     |
                         ký chứng thư Intermediate
                                     v
         +----------------------------------------------------+
         | Intermediate CA certificate                        |
         | Subject: CN=Training Intermediate CA                |
         | Issuer:  CN=Training Root CA                        |
         | BasicConstraints: CA=true, pathLenConstraint=0     |
         | KeyUsage: keyCertSign (+ cRLSign nếu có CRL)         |
         +---------------------------+------------------------+
                                     |
                         ký chứng thư leaf
                                     v
         +----------------------------------------------------+
         | End-entity / leaf certificate                      |
         | Subject: CN=demo.example.invalid                    |
         | Issuer:  CN=Training Intermediate CA                |
         | BasicConstraints: CA=false                         |
         | Dùng theo mục đích và định danh ứng dụng            |
         +----------------------------------------------------+

Đối tượng Java CertPath (X.509) theo thứ tự:
    [leaf, intermediate]                // KHÔNG đưa root vào đây

Đầu vào tin cậy riêng:
    Set<TrustAnchor> = {root đã tin cậy}
```

**Hướng quan hệ chữ ký** là Root ký Intermediate, Intermediate ký Leaf. **Hướng sắp thứ tự trong `CertPath` của Java** lại là từ *đối tượng cần xác thực* đi dần đến *CA gần điểm neo nhất*:

```text
getCertificates().get(0)  -> leaf (target)
getCertificates().get(1)  -> intermediate
TrustAnchor               -> root (ở ngoài CertPath)
```

Tài liệu Java SE 17 về `CertPath` và *Java PKI Programmer's Guide* nêu rõ **certificate đại diện cho `TrustAnchor` không nên nằm trong certification path**. Path do `CertPathBuilder` tạo theo PKIX cũng **không chứa** root/trust anchor; lấy điểm neo qua `PKIXCertPathBuilderResult.getTrustAnchor()`.

### 2.1 Các vai trò không được đánh đồng

| Đối tượng | Nó đại diện cho gì? | Nó có sẵn đáng tin không? | Đặt ở đâu trong Java? |
| --- | --- | --- | --- |
| Leaf / end entity | Danh tính hoặc public key cần xác minh cho ứng dụng (máy chủ TLS, người ký, v.v.) | **Không**; phải có path và policy phù hợp | Chứng thư đầu tiên trong `CertPath` |
| Intermediate CA | CA ủy quyền cấp chứng thư cấp dưới | **Không tự có**; phải xác minh chuỗi chữ ký, BasicConstraints và các ràng buộc | Chứng thư tiếp theo trong `CertPath` |
| Root CA certificate | Thường là chứng thư CA tự ký (*self-signed*) chứa public key gốc | Chỉ khi được **chấp nhận/cài sẵn qua kênh đáng tin** | Thường dùng để tạo `TrustAnchor`, không đưa vào path |
| `TrustAnchor` | Thông tin CA đã được tin cậy để kết thúc kiểm tra đường dẫn | **Có, vì đã được chọn bởi chính sách của ứng dụng** | Tập `Set<TrustAnchor>` trong `PKIXParameters` |
| `CertPath` | Thứ tự các chứng thư cần được xác thực | **Chưa** cho đến khi PKIX validation thành công | `java.security.cert.CertPath` |
| `PKIXCertPathValidatorResult` | Kết quả PKIX validation thành công cùng trust anchor đã dùng | Có ý nghĩa theo **anchors + policy + thời điểm** đã truyền | Giá trị trả về sau `CertPathValidator.validate` |

**Một intermediate cũng có thể được tổ chức chủ động cấu hình làm `TrustAnchor`.** Khi đó điểm neo là intermediate đã được phê duyệt, còn đường dẫn có thể ngắn hơn. Sự khác biệt là **vai trò chính sách** (*anchor*) so với **vai trò cấu trúc** (*CA nằm trong path*), không chỉ nằm ở trường `BasicConstraints`.

## 3. Nền tảng X.509: subject, issuer, chữ ký và quyền làm CA

Một chứng thư X.509 có những trường/extension phục vụ xác minh đường dẫn:

| Trường/extension | Chức năng trong kiểm tra đường dẫn | Lưu ý |
| --- | --- | --- |
| `subject` | Định danh X.500 của chủ thể được cấp | Không đồng nghĩa đã khớp hostname/định danh ứng dụng |
| `issuer` | Định danh bên phát hành | Hỗ trợ nối với CA cấp trên; **so trùng tên không đủ** |
| `subjectPublicKeyInfo` | Public key của leaf hoặc CA | Dùng để xác minh chữ ký ở tầng dưới tương ứng |
| `signatureAlgorithm` và `signatureValue` | Thuật toán/chữ ký của issuer lên TBSCertificate | PKIX phải kiểm tra chữ ký bằng public key issuer và constraint thuật toán |
| `notBefore` / `notAfter` | Khoảng thời gian hợp lệ | Validation theo ngày đã cấu hình; không được bỏ qua |
| `BasicConstraints` | `CA=true/false`, cùng `pathLenConstraint` nếu có | Intermediate ký chứng thư cấp dưới phải có quyền CA |
| `KeyUsage` | Quyền dùng key: `keyCertSign`, `digitalSignature`, `keyEncipherment`, ... | CA ký chứng thư cần `keyCertSign` nếu extension hiện diện |
| `ExtendedKeyUsage` | Mục đích dùng end-entity: TLS `serverAuth`, `clientAuth`, `codeSigning`, ... | Ứng dụng cần xác thực đúng purpose |
| `SubjectAlternativeName` (SAN) | Tên DNS/IP/danh tính thay thế của leaf | TLS hostname matching **là bước riêng**, không chỉ validate path |
| `NameConstraints` | Giới hạn namespace CA có thể cấp | PKIX áp dụng constraints theo RFC |
| `CertificatePolicies`, `PolicyConstraints` | Kiểm soát chính sách chứng thư | Quan trọng với nhiều hệ thống PKI chuyên dụng |
| `AuthorityKeyIdentifier` (AKI), `SubjectKeyIdentifier` (SKI) | Gợi ý tìm issuer/khóa tương ứng | Hỗ trợ path building; **không phải chứng minh mật mã duy nhất** |
| CRL Distribution Points / AIA OCSP | Thông tin truy vấn trạng thái thu hồi | Không có nghĩa runtime sẽ tự truy vấn thành công |

**Ví dụ `BasicConstraints`:** root có `CA=true, pathLenConstraint=1`; intermediate có `CA=true, pathLenConstraint=0`. Intermediate `pathLen=0` vẫn có thể ký **leaf end-entity**, nhưng không cho phép thêm một CA trung gian **không self-issued** khác bên dưới nó trong một đường dẫn được phép. Path-length constraint không phải giới hạn số lượng leaf do CA cấp.

**Ví dụ `KeyUsage`:** intermediate có `keyCertSign`, root cũng có `keyCertSign`; leaf dùng `digitalSignature` theo nhu cầu ứng dụng. Không hoán đổi `digitalSignature` của leaf thành quyền ký CA. Một CA chỉ có subject tên “CA” không đủ để hợp thức hóa việc cấp chứng thư.

### 3.1 Vì sao self-signed root chưa tự đáng tin?

Chứng thư tự ký nghĩa là public key của chứng thư có thể kiểm tra chữ ký của **chính chứng thư đó**. Điều này chứng minh tính **tự nhất quán**, không chứng minh danh tính CA hoặc sự chấp thuận của ứng dụng. `TrustAnchor` đến từ tập tin cấu hình, truststore do quản trị viên cung cấp, certificate pinning theo cơ chế đã xác thực hoặc chính sách tin cậy tương đương.

Nếu attacker đưa một chuỗi:

```text
attacker leaf <- attacker self-signed root
```

thì mọi chữ ký có thể hợp lệ về toán học. Nhưng nếu attacker root **không nằm trong tập trust anchors đã phê duyệt**, PKIX validation phải không thể kết thúc ở root ấy. **Tuyệt đối không tạo `TrustAnchor` trực tiếp từ root bất kỳ nằm trong chain do peer gửi.**

### 3.2 Trust anchor không luôn là một chứng thư đầy đủ

Java `TrustAnchor` có các constructor thường gặp:

```java
// Minh họa trong phương thức có quyền truy cập trustedRoot:
TrustAnchor byCertificate = new TrustAnchor(trustedRoot, null);

// Tương đương khái niệm: đặt tên CA + public key đáng tin
TrustAnchor byNameAndKey =
        new TrustAnchor(
                trustedRoot.getSubjectX500Principal(),
                trustedRoot.getPublicKey(),
                null);
```

Tham số thứ hai/ba `null` ở đây là **name constraints tùy chọn**. Constructor dùng tên + public key không chứa toàn bộ chứng thư self-signed. Cả hai cách tạo chỉ được dùng với **dữ liệu đã tin cậy từ trước**, không biến bất kỳ certificate tải được thành CA được chấp nhận.

## 4. `CertPath` trong Java được tạo và đọc thế nào?

Các thành phần liên quan đều thuộc `java.security.cert`:

- `X509Certificate`: đại diện một chứng thư X.509, cho phép đọc subject, issuer, extension, public key, chữ ký, ngày hiệu lực.
- `CertificateFactory.getInstance("X.509")`: phân tích chứng thư DER/PEM và tạo `CertPath` theo collection/list.
- `CertPath.getCertificates()`: đọc danh sách bất biến các chứng thư của path.
- `CertPathValidator.getInstance("PKIX")`: **xác thực path đã xác định**.
- `CertPathBuilder.getInstance("PKIX")`: **tìm path phù hợp** từ nguồn chứng thư và trust anchors theo constraints.
- `PKIXParameters`: cấu hình anchors, thời điểm, policy, revocation, checkers cho validator.
- `PKIXBuilderParameters`: kế thừa `PKIXParameters`, bổ sung target selector, `CertStore` và `maxPathLength`.
- `CertStore.getInstance("Collection", ...)`: cung cấp candidate certificates (và có thể CRLs) từ bộ nhớ cho path builder.

Mô hình quan hệ:

```text
Dữ liệu đã có sẵn path
    [leaf, intermediate]
            |
            v
  CertificateFactory.generateCertPath(List)
            |
            v
  CertPathValidator("PKIX")
      + PKIXParameters(
            trusted anchors,
            date, revocation, policy, checkers
        )
            |
          success? ---- no ---> CertPathValidatorException
            |
           yes
            v
  PKIXCertPathValidatorResult
      .getTrustAnchor()
      .getPublicKey()
      .getPolicyTree()

Dữ liệu có nhiều certificate candidates, chưa chọn path
    leaf + intermediates ở CertStore
            |
            v
  CertPathBuilder("PKIX")
      + PKIXBuilderParameters(anchors, X509CertSelector)
      + CertStore chứa candidates
            |
          success?
            |
           yes
            v
  PKIXCertPathBuilderResult
      .getCertPath()      // thứ tự leaf -> intermediates; không có anchor
      .getTrustAnchor()
```

`CertificateFactory.generateCertPath(List.of(leaf, intermediate))` **chỉ tạo cấu trúc**; nó không thực hiện PKIX validation. Cũng tương tự, `X509Certificate.checkValidity()` chỉ kiểm tra thời gian riêng của chứng thư; `leaf.verify(intermediate.getPublicKey())` chỉ kiểm tra một chữ ký của leaf. **Không phép nào thay thế xác thực toàn bộ path.**

### 4.1 Thứ tự không đúng và thiếu intermediate

Trong Java X.509 `CertPath`, đường dẫn thường là:

```java
// Minh họa, leaf và intermediate là các X509Certificate đã tải:
CertificateFactory factory = CertificateFactory.getInstance("X.509");
CertPath correct = factory.generateCertPath(
        java.util.List.of(leaf, intermediate)); // leaf trước
```

Các trường hợp thường sai:

- `[intermediate, leaf]` đảo thứ tự, dù cả hai chứng thư đều hợp lệ riêng.
- `[leaf]` thiếu intermediate khi leaf không trực tiếp được root cấp.
- `[leaf, intermediate, root]` đưa root vào path đồng thời dùng root làm `TrustAnchor`, trái quy ước PKIX Java.
- `[leaf, wrongIntermediate]` issuer name/key/chữ ký hoặc constraints không khớp.
- Chỉ kiểm tra `leaf.getIssuerX500Principal().equals(intermediate.getSubjectX500Principal())` rồi chấp nhận: tên khớp chưa chứng minh chữ ký đúng, CA có quyền hay đường dẫn kết thúc ở anchor tin cậy.

Đôi khi dữ liệu TLS hoặc PEM gửi theo thứ tự khác, hoặc có nhiều cross-signed intermediates. Dùng **path builder** để tìm một đường dẫn hợp lệ thay vì giả định index/issuer name đơn giản là đủ. PKIX Builder chỉ tìm trong **các nguồn `CertStore`/cơ chế được cấu hình**; không bảo đảm tự tải hết intermediates từ Internet.

## 5. Khác nhau giữa `CertPathValidator` và `CertPathBuilder`

| Vấn đề | `CertPathValidator` | `CertPathBuilder` |
| --- | --- | --- |
| Câu hỏi | *Đường dẫn cho trước này có hợp lệ không?* | *Có thể tạo một đường dẫn hợp lệ tới trust anchor không?* |
| Đầu vào chính | `CertPath` đã có thứ tự + `PKIXParameters` | `PKIXBuilderParameters` với target `CertSelector`, `CertStore` và anchors |
| Trả về khi thành công | `PKIXCertPathValidatorResult` | `PKIXCertPathBuilderResult` |
| Có tự tìm intermediate? | Không, vì path đã được đưa vào | Có, trong tập nguồn certificates/constraints được cấu hình |
| Trust anchor có là phần tử cuối `CertPath`? | **Không** | **Không** |
| Nếu thiếu intermediate | Thường validation không thể nối path tới root đã tin | Builder có thể tìm được nếu candidate intermediate ở `CertStore` |
| Mục tiêu | Kiểm tra một path xác định | Tìm và kiểm tra một path hợp lệ |

**Câu nhớ nhanh:** *Builder tìm đường; Validator kiểm tra đường.* Một `CertPathBuilder` PKIX tạo đường dẫn đã được kiểm tra trong quy trình build, nên trả về path và trust anchor đã chọn; với validation một đường dẫn sẵn có, bạn vẫn cần chọn anchors/chính sách đúng.

## 6. Thực nghiệm Java 17: tạo ba chứng thư bằng `keytool`

Phần này dùng **fixture hoàn toàn cục bộ**, không tải private key của người khác và không cần kết nối CA thật. Mọi mật khẩu `changeit` chỉ phục vụ bài lab, tuyệt đối **không dùng cho hệ thống thực**.

### 6.1 Chuẩn bị và sinh ba cặp khóa

Mở shell có `keytool`, `javac`, `java` từ JDK 17+, tạo **thư mục bài thực hành riêng**:

```bash
mkdir pkix-lab
cd pkix-lab
```

Tạo **Root CA tự ký** với quyền CA và một intermediate ở dưới (`pathlen:1`). Lệnh có thể chạy trên shell xử lý dấu ngoặc kép thông thường (Bash, PowerShell):

```bash
keytool -genkeypair -alias root -dname "CN=Training Root CA, O=Local Demo" -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -keystore root.p12 -storetype PKCS12 -storepass changeit -keypass changeit -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -noprompt
```

Tạo một **cặp key của Intermediate CA** và một **cặp key của leaf**. Ở thời điểm sinh keypair, `keytool` có thể gắn chứng thư tự ký tạm thời cho entry; chứng thư có quan hệ CA thực trong lab sẽ được **ký qua CSR ở bước tiếp**:

```bash
keytool -genkeypair -alias intermediate -dname "CN=Training Intermediate CA, O=Local Demo" -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -keystore intermediate.p12 -storetype PKCS12 -storepass changeit -keypass changeit -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -noprompt
keytool -genkeypair -alias leaf -dname "CN=demo.example.invalid, O=Local Demo" -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 365 -keystore leaf.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt
```

### 6.2 Root cấp Intermediate; Intermediate cấp leaf

**Bước 1 — CSR của Intermediate:** tạo yêu cầu chứng thư từ public key / subject của Intermediate:

```bash
keytool -certreq -alias intermediate -keystore intermediate.p12 -storepass changeit -file intermediate.csr
```

**Bước 2 — Root ký và cấp chứng thư cho Intermediate:**

```bash
keytool -gencert -alias root -keystore root.p12 -storepass changeit -infile intermediate.csr -outfile intermediate.pem -rfc -validity 365 -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign"
```

**Bước 3 — CSR của leaf:**

```bash
keytool -certreq -alias leaf -keystore leaf.p12 -storepass changeit -file leaf.csr
```

**Bước 4 — Intermediate ký chứng thư leaf**, đánh dấu end entity, `serverAuth` và DNS SAN minh họa:

```bash
keytool -gencert -alias intermediate -keystore intermediate.p12 -storepass changeit -infile leaf.csr -outfile leaf.pem -rfc -validity 365 -ext "BC:critical=ca:false" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -ext "SAN=dns:demo.example.invalid"
```

**Bước 5 — Xuất chứng thư công khai của Root để làm trusted anchor trong lab:**

```bash
keytool -exportcert -alias root -keystore root.p12 -storepass changeit -file root.pem -rfc
```

Kết quả cần có:

```text
pkix-lab/
  root.p12                (có PRIVATE KEY của root: giữ kín)
  intermediate.p12        (có PRIVATE KEY của intermediate: giữ kín)
  leaf.p12                (có PRIVATE KEY của leaf: giữ kín)
  intermediate.csr        (chỉ phục vụ cấp chứng thư)
  leaf.csr
  root.pem                (public certificate; lab phê duyệt làm anchor)
  intermediate.pem        (intermediate certificate do root ký)
  leaf.pem                (leaf certificate do intermediate ký)
```

Các file `.pem` là **chứng thư X.509 công khai**, không chứa private key; `.p12` có private key và **không** được đưa lên Internet hoặc commit repository. `-rfc` của `keytool` xuất PEM (Base64 cùng header/footer). Các lệnh được dùng để tạo dữ liệu **học tập**; PKI sản xuất cần quy trình phát hành CA, bảo vệ signing keys, key ceremony, certificate policies, thu hồi và quản lý khóa nghiêm ngặt.

**Chi tiết dễ nhầm trong lab:** `intermediate.p12` ban đầu chứa keypair và chứng thư tự ký tạm; lệnh `-gencert` sử dụng **private key tương ứng** để ký `leaf.pem`. Đường dẫn cần validate trong bước tiếp chỉ dùng **chứng thư CA được Root ký là `intermediate.pem`**, không nhầm với chứng thư tự ký tạm trong entry của keystore.

## 7. Chương trình Java 17 đầy đủ: validate path, thử lỗi, rồi build path

Tạo file **`CertPathTrustModelDemo.java`** trong cùng thư mục chứa ba file PEM. Chương trình:

1. Tải `root.pem`, `intermediate.pem`, `leaf.pem` thành `X509Certificate` bằng `CertificateFactory`.
2. Kiểm tra thuộc tính CA (`getBasicConstraints()`).
3. Tạo `CertPath` theo thứ tự **`[leaf, intermediate]`**, tạo `TrustAnchor(root, null)` và dùng `CertPathValidator("PKIX")` để xác thực.
4. Thử thiếu intermediate và đảo thứ tự: kỳ vọng bị từ chối.
5. Tạo `CertStore` chứa candidate certificates và dùng `CertPathBuilder("PKIX")` để **tìm** đường dẫn.
6. Quan sát result cho thấy path có **2 certificate**, root chỉ xuất hiện ở `TrustAnchor`.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.cert.CertPath;
import java.security.cert.CertPathBuilder;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.CertStore;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.PKIXBuilderParameters;
import java.security.cert.PKIXCertPathBuilderResult;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class CertPathTrustModelDemo {
    private static X509Certificate readCert(String name) throws Exception {
        try (InputStream in = Files.newInputStream(Path.of(name))) {
            CertificateFactory factory = CertificateFactory.getInstance("X.509");
            return (X509Certificate) factory.generateCertificate(in);
        }
    }

    private static PKIXParameters validationParams(X509Certificate root)
            throws GeneralSecurityException {
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        // Lab-only: no CRL/OCSP infrastructure for these training certificates.
        params.setRevocationEnabled(false);
        return params;
    }

    private static boolean isRejected(CertPath path, X509Certificate root)
            throws GeneralSecurityException {
        try {
            CertPathValidator.getInstance("PKIX").validate(
                    path, validationParams(root));
            return false;
        } catch (CertPathValidatorException expected) {
            return true;
        }
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 3) {
            throw new IllegalArgumentException(
                    "Usage: java CertPathTrustModelDemo root.pem intermediate.pem leaf.pem");
        }
        X509Certificate root = readCert(args[0]);
        X509Certificate intermediate = readCert(args[1]);
        X509Certificate leaf = readCert(args[2]);

        System.out.println("Intermediate is CA: " +
                (intermediate.getBasicConstraints() >= 0));
        System.out.println("Leaf is CA: " +
                (leaf.getBasicConstraints() >= 0));

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        CertPath supplied = factory.generateCertPath(
                List.of(leaf, intermediate)); // Target first; no root.
        PKIXCertPathValidatorResult checked =
                (PKIXCertPathValidatorResult)
                CertPathValidator.getInstance("PKIX").validate(
                        supplied, validationParams(root));
        System.out.println("Supplied path size: " +
                supplied.getCertificates().size());
        System.out.println("Validated trust anchor is root: " +
                root.equals(checked.getTrustAnchor().getTrustedCert()));

        CertPath missingIntermediate = factory.generateCertPath(List.of(leaf));
        System.out.println("Missing intermediate rejected: " +
                isRejected(missingIntermediate, root));

        CertPath reversed = factory.generateCertPath(
                List.of(intermediate, leaf));
        System.out.println("Wrong certificate order rejected: " +
                isRejected(reversed, root));

        X509CertSelector target = new X509CertSelector();
        target.setCertificate(leaf);
        PKIXBuilderParameters builderParams = new PKIXBuilderParameters(
                Set.of(new TrustAnchor(root, null)), target);
        builderParams.setRevocationEnabled(false); // Lab only.
        builderParams.setMaxPathLength(1);
        builderParams.addCertStore(CertStore.getInstance(
                "Collection", new CollectionCertStoreParameters(
                        List.of(leaf, intermediate))));
        PKIXCertPathBuilderResult built = (PKIXCertPathBuilderResult)
                CertPathBuilder.getInstance("PKIX").build(builderParams);
        System.out.println("Builder path size: " +
                built.getCertPath().getCertificates().size());
        System.out.println("Builder path starts with leaf: " +
                leaf.equals(built.getCertPath().getCertificates().get(0)));
        System.out.println("Builder trust anchor is root: " +
                root.equals(built.getTrustAnchor().getTrustedCert()));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 CertPathTrustModelDemo.java
java CertPathTrustModelDemo root.pem intermediate.pem leaf.pem
```

Stdout **đã kiểm chứng** với ba chứng thư được tạo theo lệnh lab:

```text
Intermediate is CA: true
Leaf is CA: false
Supplied path size: 2
Validated trust anchor is root: true
Missing intermediate rejected: true
Wrong certificate order rejected: true
Builder path size: 2
Builder path starts with leaf: true
Builder trust anchor is root: true
```

**Giải thích các dòng:**

- `Intermediate is CA: true` vì `intermediate.pem` có BasicConstraints CA hợp lệ.
- `Leaf is CA: false`: leaf không có quyền cấp chứng thư CA.
- `Supplied path size: 2`: path chỉ chứa **leaf và intermediate**; root nằm trong tập `TrustAnchor`.
- `Validated trust anchor is root: true`: `validate` đã hoàn tất và trả về anchor chính xác theo cấu hình lab.
- `Missing intermediate rejected: true`: leaf được **intermediate** cấp, không trực tiếp bởi root; path `[leaf]` không nối được tới anchor root.
- `Wrong certificate order rejected: true`: `CertPath` đảo thứ tự sai, không phải đường từ target về anchor.
- `Builder path size: 2`: builder tìm intermediate từ `CertStore` với selector chọn leaf.
- `Builder path starts with leaf: true`: xác nhận quy ước sắp thứ tự của Java.
- `Builder trust anchor is root: true`: builder trả riêng thông tin root đáng tin.

**Giới hạn có chủ đích:** `setRevocationEnabled(false)` ở **cả validator lẫn builder** là để lab không phải thiết lập CRL/OCSP cho CA tự tạo. Trong production, **không vô hiệu hóa revocation chỉ vì môi trường thiếu mạng**. Phải triển khai chính sách thu hồi phù hợp (OCSP/CRL, timeout, caching, xử lý offline và lỗi) và kiểm thử thực tế. Tương tự, chương trình **không thực hiện xác minh hostname TLS**, không triển khai chứng chỉ CT, không tự kiểm tra mọi yêu cầu nghiệp vụ lên leaf: đây là ví dụ **PKIX path model**, không phải HTTPS client hoàn chỉnh.

Một lưu ý nữa: thời hạn fixture là **365 ngày kể từ thời điểm tạo**. Nếu để file trong nhiều năm rồi chạy lại, có thể fail vì expired; hãy tạo mới fixture hoặc thiết lập validation date theo tình huống kiểm thử có chủ đích, không “bỏ qua” ngày hiệu lực trong production.

## 8. Đặt `TrustAnchor` đúng chỗ: `PKIXParameters` và `KeyStore`

Ở cấp API có hai cách thông dụng:

### 8.1 Truyền tập anchors trực tiếp

```java
// Minh họa đặt trong phương thức throws GeneralSecurityException.
Set<TrustAnchor> anchors =
        Set.of(new TrustAnchor(trustedRootCertificate, null));
PKIXParameters params = new PKIXParameters(anchors);
```

- `PKIXParameters(Set<TrustAnchor>)` yêu cầu một tập **không rỗng**; nếu rỗng sẽ có `InvalidAlgorithmParameterException`.
- `setDate(Date)` có thể dùng để xác minh tại một thời điểm; giá trị `null` mặc định nghĩa là thời điểm hiện tại khi validate, không có nghĩa “không cần kiểm tra thời gian”.
- `setInitialPolicies`, `setExplicitPolicyRequired`, `setAnyPolicyInhibited`, `setPolicyMappingInhibited` v.v. cho phép cấu hình các ràng buộc PKIX theo policy.
- `setRevocationEnabled(boolean)` kiểm soát việc kiểm tra thu hồi; cấu hình đúng cần nguồn dữ liệu tin cậy và chính sách thất bại.
- `PKIXRevocationChecker` có thể cung cấp điều khiển OCSP/CRL và các option như `PREFER_CRLS`, `ONLY_END_ENTITY` hay `SOFT_FAIL`. `SOFT_FAIL` là quyết định an ninh cần chủ đích, **không phải cờ bật mặc định để bỏ qua sự cố**.

### 8.2 Lấy anchors từ truststore được quản trị

```java
// Minh họa trong phương thức có quyền truy cập trustStore đã load:
PKIXParameters params = new PKIXParameters(trustStore);
```

Constructor `PKIXParameters(KeyStore)` xem các mục **trusted certificate entry** trong truststore là nguồn anchors (theo đặc tả API). Nó không lấy tất cả chứng thư bất kỳ trong keypair entries làm root đáng tin. Trên JVM server, truststore có thể được cấu hình bởi hệ thống, container hoặc ứng dụng và phải được quản lý như **cấu hình an ninh**.

**Không** xây truststore theo cách tải danh sách chứng thư từ TLS peer rồi `setCertificateEntry` tất cả, vì lúc đó đã **biến dữ liệu chưa tin thành trust anchors**. Truststore nội bộ dùng cho mTLS hoặc test chỉ nên chứa CA/peer đã được phê duyệt theo chính sách.

### 8.3 `TrustAnchor` và certificate root trong chain

Nếu TLS peer gửi kèm chứng thư root, bên nhận **không mặc nhiên tin root đó**. Trust manager phải tìm một anchor trong truststore **đã được cấu hình độc lập**. Root trong peer chain có thể trùng với anchor đã tin, nhưng sự trùng dữ liệu không phải nguồn cấp quyền tin cậy; anchor được lựa chọn từ truststore.

Một application có nhiều anchors có thể tìm được **nhiều đường dẫn hợp lệ khác nhau** tới các root khác nhau khi xuất hiện cross-signing. Builder được phép chọn một path hợp lệ theo constraints và candidates của provider; ứng dụng không nên giả định “chỉ có đúng một đường”, hoặc so sánh tên root bằng chuỗi hiển thị để suy luận tin cậy.

## 9. PKIX validation kiểm tra những gì — và những gì còn ở tầng ứng dụng?

Theo RFC 5280 và các giới hạn thuật toán/chính sách của provider, việc xác minh đường dẫn thường bao gồm:

1. **Nối issuer–subject và chữ ký số:** certificate cấp dưới có thể được xác minh bằng public key của CA cấp trên tương ứng.
2. **Thời hạn hợp lệ** cho các certificate trong path tại validation date.
3. **Quyền CA:** `BasicConstraints: CA=true` ở issuer intermediates, `pathLenConstraint` thích hợp và `KeyUsage.keyCertSign` khi có extension.
4. **Name constraints** kế thừa từ các CA theo quy tắc RFC.
5. **Certificate policies/policy mappings** và các extension critical được nhận diện.
6. **Algorithm constraints** của runtime/policy, ví dụ `jdk.certpath.disabledAlgorithms` cho các thuật toán hoặc key-size bị loại bỏ.
7. **Trạng thái thu hồi** nếu được bật và có đủ thông tin/cơ chế xử lý theo cấu hình.

Nhưng một thành công của `CertPathValidator.validate()` **chưa đủ** để chấp nhận leaf cho mọi ứng dụng:

| Điều ứng dụng cần | PKIX path validation có tự làm đầy đủ không? | Phần còn phải kiểm tra |
| --- | --- | --- |
| Chứng thư có chain hợp lệ tới CA đã tin | **Có**, trong phạm vi PKIX parameters và provider | Lựa chọn anchors/policy đúng cho ứng dụng |
| Chứng thư đúng cho **hostname TLS** | **Không**, chỉ kiểm tra path không tự khớp DNS bạn đang kết nối | SAN DNS/IP và endpoint identity theo quy tắc TLS/JSSE |
| Chứng thư có quyền **TLS serverAuth** hoặc **codeSigning** | Không mặc định cho mọi purpose | EKU/KeyUsage và policy ứng dụng/JSSE |
| Chứng thư có bị thu hồi hay không | Phụ thuộc `setRevocationEnabled` và cấu hình checker/CRL/OCSP | Chính sách revocation, xử lý offline/failure |
| Root có nên được tin ở tenant này hay không | Không tự chọn chính sách trust store | Trust anchors phân vùng theo tenant/purpose |
| Chủ thể có quyền thực hiện hành động nghiệp vụ không | **Không** | Authorization, mapping identity → role/account |
| Có chống replay/đảm bảo dữ liệu kênh không bị sửa? | Không bởi riêng path | TLS handshake + record protection / protocol khác |

**Phân biệt `CertPathValidator` với HTTPS verification:** JSSE `X509TrustManager`/`X509ExtendedTrustManager` phục vụ xác thực chuỗi trong ngữ cảnh TLS; `HttpsURLConnection`/HTTP client và cấu hình endpoint identification bổ sung kiểm tra hostname/purpose theo giao thức. Một bài tập gọi trực tiếp `CertPathValidator` **không thay cho HTTPS client an toàn**.

## 10. Các lỗi hay gặp khi làm việc với intermediate và root

| Hiện tượng/lỗi | Nguyên nhân thường gặp | Cách xử lý đúng |
| --- | --- | --- |
| `CertPathValidatorException` do không nối được tới anchor | Thiếu intermediate, sai issuer/key, hoặc root chưa nằm trong tập đáng tin | Cung cấp intermediate đúng, **không tự tin root do peer gửi** |
| Dùng `CertPath [root, intermediate, leaf]` | Sai thứ tự, đưa trust anchor vào path | Tạo `[leaf, intermediate]`, truyền root riêng trong `PKIXParameters` |
| Builder không tìm được path | `CertStore` thiếu intermediate hoặc selector/ràng buộc quá chặt | Kiểm tra target `X509CertSelector`, candidate store, issuer/cert extensions |
| Chứng thư intermediate bị từ chối | `BasicConstraints CA=false`, thiếu `keyCertSign`, `pathLenConstraint` hoặc critical extensions sai | CA phải phát hành lại chứng thư trung gian hợp lệ, **không tắt check** |
| Chứng thư hết hạn | `notAfter` đã qua hoặc `notBefore` còn ở tương lai | Cấp mới/gia hạn đúng quy trình, đồng bộ đồng hồ; không bỏ qua validity |
| `InvalidAlgorithmParameterException: trustAnchors must be non-empty` | Tập anchor rỗng hoặc truststore không có trusted cert entries | Cài anchors phê duyệt rồi tạo `PKIXParameters` |
| Revocation báo lỗi do mạng/thiếu CRL | Policy bật nhưng nguồn trạng thái không khả dụng | Cấu hình OCSP/CRL, cache/timeout và quy tắc fail-open/closed có phê duyệt |
| `validate` thành công nhưng hostname sai | Code chỉ kiểm tra path, không kiểm tra server identity | Xác minh SAN/endpoint identification ở tầng TLS/ứng dụng |
| Tin tự động root được peer gửi | Vô tình mở rộng trust anchors theo dữ liệu chưa đáng tin | Root phải đến từ truststore/pinning/quản trị độc lập |
| So trùng `issuer.getName()` rồi coi là hợp lệ | Không kiểm tra chữ ký/policy/constraints | Dùng PKIX validator/builder |
| Dùng `getBasicConstraints() >= 0` như kiểm tra tất cả | Chỉ cho biết CA bit/độ sâu, **chưa chứng minh chain hợp lệ** | Bắt buộc validate toàn bộ path |
| Dùng Java certificate entry/keystore nhầm loại | `KeyStore` chứa key entries/certs khác trusted entries | Phân biệt `isCertificateEntry`/entry policy, kiểm tra truststore thực |

### 10.1 Chẩn đoán exception thay vì chấp nhận tiếp

`CertPathValidatorException` có thể cung cấp:

```java
// Đoạn minh họa trong catch (CertPathValidatorException ex):
int index = ex.getIndex();  // vị trí chứng thư lỗi trong path, có thể -1
CertPathValidatorException.Reason reason = ex.getReason();
```

Giá trị `index` có thể giúp chỉ ra leaf/intermediate nào liên quan, nhưng **không phải mọi lỗi đều gắn với một index**. Không bắt tất cả exception rồi `return true` hoặc tự fallback sang một CA tự ký không được tin. Nếu validation thất bại, **không chấp nhận certificate**.

Không dùng `jdk.certpath.disabledAlgorithms` theo cách làm yếu chính sách để “sửa” lỗi tương thích. Nếu ứng dụng đang dùng thuật toán yếu hay root không hợp lệ, cần **di trú đúng** (cấp lại certificate/khóa, cấu hình trust anchors thích hợp) thay vì tắt bảo vệ.

## 11. Bài tập kiểm tra bằng chính fixture

**Bài tập A — Nhận diện ba vai trò.** Dùng `keytool -printcert -file root.pem`, `-file intermediate.pem` và `-file leaf.pem` để quan sát subject, issuer, BasicConstraints, KeyUsage, SAN/EKU. Xác định:

- Root tự ký có subject/issuer trùng nhau; nhưng điều làm nó đáng tin là nó đã được ứng dụng chọn làm `TrustAnchor`.
- Intermediate mang subject riêng, issuer là Root, `CA=true`, `pathlen:0` và quyền `keyCertSign`.
- Leaf mang issuer là Intermediate, `CA=false`, SAN DNS theo lab.

**Bài tập B — Đổi thứ tự `CertPath`.** Thay `List.of(leaf, intermediate)` thành `List.of(intermediate, leaf)` trong đoạn validate. Vì sao cùng hai certificate vẫn không tạo đường từ target đến anchor? Dùng `getIndex()`/`getReason()` để hiểu lỗi, không dựa vào một thông điệp text cố định của provider.

**Bài tập C — Bỏ intermediate.** Chỉ truyền `[leaf]` cho validator, giữ Root là anchor. Nhận biết không thể nối leaf trực tiếp tới root. Thêm intermediate vào `CollectionCertStoreParameters` cho builder để nó tìm lại path đúng.

**Bài tập D — Sai anchor.** Sinh **một CA root khác** trong lab, thay `TrustAnchor` bằng root mới. `CertPath` vẫn có các chữ ký nội bộ đúng theo root cũ nhưng **không thể kết thúc ở anchor mới**. Đây là khác biệt giữa “chứng thư có chữ ký hợp lệ” và “ứng dụng tin issuer cuối”.

**Bài tập E — CA mất quyền cấp.** Thử thay intermediate được Root ký thành bản không có `CA=true` hoặc thiếu `keyCertSign` (khi có KeyUsage), rồi kiểm tra PKIX validator từ chối. Đừng tự thêm chứng thư ấy vào truststore để lách lỗi.

**Bài tập F — Thời gian và revocation.** Tạo fixture có thời hạn ngắn và thử sau khi hết hạn; quan sát `CertPathValidatorException`. Tìm hiểu `PKIXRevocationChecker` (cần hạ tầng OCSP/CRL) và giải thích vì sao `setRevocationEnabled(false)` chỉ dùng cho thí nghiệm kín.

**Bài tập G — Purpose và hostname.** Thay SAN của leaf bằng DNS khác nhưng giữ root/intermediate hợp lệ. Chỉ `validate()` chưa đủ kết luận máy chủ đúng hostname. Kiểm tra thêm quy tắc endpoint identification/TLS và EKU/KeyUsage.

## 12. Checklist thiết kế đường dẫn tin cậy trong Java

- [ ] **Không lấy trust anchor từ dữ liệu chưa tin cậy**; tin CA/định danh qua truststore/chính sách được quản trị.
- [ ] Phân biệt **leaf, intermediate và root**; `CertPath` X.509 theo thứ tự leaf → intermediate; root/anchor **nằm ngoài** path.
- [ ] Với `CertPathValidator("PKIX")`, truyền **đúng `PKIXParameters`**, thời gian, anchors, chính sách và revocation.
- [ ] Với `CertPathBuilder("PKIX")`, có selector **đúng target** và `CertStore` chứa intermediate candidates, không mong mọi intermediate tự tải xuống.
- [ ] Không tự viết thuật toán “so tên issuer → subject” rồi coi như path validation; phải kiểm tra chữ ký, BasicConstraints, KeyUsage, time, constraints và policy.
- [ ] Không nhầm `KeyStore` trusted cert entry với keypair/private-key entry hoặc certificates được peer trình bày.
- [ ] Không bỏ qua hostname/EKU/purpose khi dùng certificate cho TLS, mTLS, code signing hoặc danh tính nghiệp vụ.
- [ ] Revocation phải là **quyết định chính sách thực tế** có OCSP/CRL và xử lý lỗi; ví dụ tắt chỉ để lab.
- [ ] Theo dõi thuật toán/key-size bị chính sách JDK từ chối; **không vô hiệu hóa bảo vệ** để chạy certificate yếu.
- [ ] Có negative tests: thiếu intermediate, đảo thứ tự, sai root, CA=false, thiếu keyCertSign, certificate expired, hostname mismatch.
- [ ] Không để khóa CA private từ fixture/hệ thống production vào source code, log, repo, hoặc file tải công khai.

## 13. Tự kiểm tra kiến thức

**1. Trong Java, `CertPath` của root → intermediate → leaf được sắp ra sao?**  
Theo X.509 path của Java: **`[leaf, intermediate]`** từ target đến phía trust anchor. `root` cung cấp riêng dưới dạng `TrustAnchor`, không thêm vào danh sách.

**2. `TrustAnchor` là certificate tự ký nào bất kỳ phải không?**  
**Không.** Nó là thông tin CA đã được cấu hình **tin cậy ngoài đường dẫn**. Một certificate tự ký do attacker gửi không thể tự trở thành anchor.

**3. Intermediate được Root ký rồi có tự động trở thành trusted root không?**  
**Không.** Intermediate là chứng thư CA trong đường dẫn; nó phải được kiểm tra chữ ký/constraints và nối lên một anchor đáng tin đã có.

**4. `pathLenConstraint=0` trên intermediate có cấm cấp certificate leaf không?**  
**Không.** Nó cấm thêm CA trung gian **không self-issued** phía dưới trong path hợp lệ, không cấm cấp leaf.

**5. `CertificateFactory.generateCertPath` có tự kiểm tra chain không?**  
**Không.** Nó tạo representation. Dùng `CertPathValidator("PKIX").validate` để kiểm tra path; builder có thể tìm và xác thực path theo constraints.

**6. `CertPathValidator` và `CertPathBuilder` khác nhau ở đâu?**  
Validator **xác thực path đã cho**. Builder **tìm path** từ certificates/`CertStore` và trust anchors, rồi trả path hợp lệ khi build thành công.

**7. `validate()` thành công đã bảo đảm hostname trong URL trùng certificate chưa?**  
**Chưa.** Phải có kiểm tra SAN/endpoint identity cùng key usage/purpose ở tầng ứng dụng/TLS.

**8. Vì sao ví dụ đặt `setRevocationEnabled(false)` và production có nên copy nguyên không?**  
Lab không có hệ thống CRL/OCSP để kiểm thử thu hồi. Production phải có chính sách revocation phù hợp; tắt vì tiện có thể khiến chứng thư đã thu hồi vẫn được chấp nhận.

## Tài liệu chính thức

- [Java SE 17 — `CertPath`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPath.html): tập certificate, quy tắc thứ tự X.509 và vai trò riêng của trust anchor.
- [Java SE 17 — `TrustAnchor`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/TrustAnchor.html): mô hình CA tin cậy với certificate hoặc CA name + public key, name constraints.
- [Java SE 17 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): engine PKIX validation và exceptions.
- [Java SE 17 — `CertPathBuilder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): xây dựng đường dẫn bằng target constraints, certificates nguồn và trust anchors.
- [Java SE 17 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): anchors, date, policies, revocation.
- [Java SE 17 — `PKIXBuilderParameters`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXBuilderParameters.html): target selector, CertStore, max path length.
- [Java SE 17 — `PKIXCertPathValidatorResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXCertPathValidatorResult.html): kết quả gồm `getTrustAnchor`, public key, policy tree.
- [Java SE 17 — `PKIXCertPathBuilderResult`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXCertPathBuilderResult.html): path được build và trust anchor riêng.
- [Java SE 17 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): hướng dẫn chính thức về xây và xác minh certification paths.
- [Java SE 17 — `keytool` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): `-genkeypair`, `-certreq`, `-gencert`, `-ext BC`, `-ext KU`, `-exportcert`.
- [RFC 5280 — X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): §4.2.1.9 BasicConstraints; §4.2.1.3 KeyUsage; §6 path validation và trust anchors.

**Kết luận:** `CertPath` là **đường đi của các chứng thư cần kiểm tra**, intermediate là **mắt xích phải được xác thực**, còn `TrustAnchor` là **điểm xuất phát được tin theo chính sách**. `CertPathValidator` kiểm tra một đường đã cho; `CertPathBuilder` tìm một đường hợp lệ từ candidate certificates. Không chấp nhận một chứng thư chỉ vì chữ ký của nó kiểm tra được — chỉ tin khi nó có **đường dẫn hợp lệ tới anchor đã phê duyệt và đáp ứng các ràng buộc của chính ứng dụng**.
