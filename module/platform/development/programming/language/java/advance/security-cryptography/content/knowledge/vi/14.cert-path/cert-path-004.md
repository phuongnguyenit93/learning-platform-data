# 14.4 Thu thập chứng thư hoặc CRL qua CertStore

Trong hệ thống PKI, **có một certificate hợp lệ về cú pháp chưa đủ để tin người gửi**, và **có một danh sách thu hồi (Certificate Revocation List — CRL) chưa đủ để kết luận certificate không bị thu hồi**. Khi xây dựng hoặc kiểm tra **đường dẫn tin cậy (certification path)**, ứng dụng Java thường phải tìm thêm certificate của CA trung gian và CRL do các CA phát hành. API chuẩn **`java.security.cert.CertStore`** giải quyết **bước tìm/thu thập các ứng viên** từ một kho dữ liệu.

Bài học này trình bày cách dùng `CertStore` và các selector `X509CertSelector`, `X509CRLSelector` trong Java 17+; cách tạo kho `"Collection"` từ certificate/CRL đã parse; cách tra cứu kiểu `"LDAP"`; cách bổ sung `CertStore` vào tham số **PKIX**; và ranh giới quan trọng giữa **tìm được dữ liệu**, **xác minh chữ ký CRL**, **xác thực chuỗi CA**, và **kiểm tra trạng thái thu hồi**. Có chương trình Java độc lập và lệnh `keytool` tạo fixture thử nghiệm để học viên tái hiện kết quả mà không cần kết nối máy chủ ngoài.

> **Nguyên tắc gốc:** `CertStore` cung cấp các **candidate certificates/CRLs**, không phải danh sách các chứng thư tự động đáng tin. **Trust anchor**, chính sách chứng thư, đường dẫn PKIX và kiểm tra thu hồi là những bước riêng phải được thực thi đúng.

## 1. CertStore nằm ở đâu trong quá trình xác minh X.509?

Một chuỗi chứng thư TLS điển hình có thể gồm:

```text
Leaf certificate (server.example)
       |
       | signed by
       v
Intermediate CA certificate
       |
       | signed by
       v
Root CA (được cấu hình là trust anchor)
```

Khi ứng dụng chỉ nhận certificate của leaf, nó có thể **thiếu intermediate certificate**. Thêm vào đó, chính sách bảo mật có thể yêu cầu tra cứu CRL để xác định certificate có bị CA thu hồi trước khi hết hạn hay không.

`CertStore` cung cấp một giao diện đọc:

```text
                  +---------------------------+
                  | CertStore (Collection,    |
                  | LDAP, provider-specific)  |
                  +-------------+-------------+
                                |
                 +--------------+--------------+
                 |                             |
      getCertificates(selector)        getCRLs(selector)
                 |                             |
       candidate certificates              candidate CRLs
                 |                             |
                 +--------------+--------------+
                                |
                PKIX CertPathBuilder / Validator
                   + trust anchors / policy
                   + signature/time checks
                   + revocation checking
                                |
                    ACCEPT / REJECT theo policy
```

**Phân biệt các lớp:**

| Khái niệm | Vai trò | Có tự tạo niềm tin không? |
| --- | --- | --- |
| `KeyStore` | Lưu/truy cập keys, private keys và trusted certificates theo provider | Một **truststore được cấu hình** có thể chứa trust anchors; không phải mọi KeyStore đều là truststore |
| `CertStore` | Truy vấn certificate và CRL từ repository | **Không**; kết quả thu thập là dữ liệu cần kiểm chứng |
| `CertificateFactory` | Parse PEM/DER thành `Certificate`, `CRL` hoặc `CertPath` | **Không**; parse được không đồng nghĩa tin cậy |
| `X509CertSelector` | Đặt tiêu chí lọc certificate X.509 | **Không**; lọc theo thuộc tính, không thay chain validation |
| `X509CRLSelector` | Đặt tiêu chí lọc CRL X.509 | **Không**; issuer/time match không chứng minh chữ ký |
| `TrustAnchor` | Root CA certificate/public key được ứng dụng chấp thuận theo trust policy | **Có vai trò nền tảng tin cậy** nếu được cấp phát đúng |
| `CertPathBuilder("PKIX")` | Tìm một chứng thực chain đáp ứng tham số PKIX | Xây đường dẫn dựa trên trust anchors và chính sách |
| `CertPathValidator("PKIX")` | Kiểm chứng một `CertPath` đã có | Xác thực đường dẫn, với cấu hình thu hồi phù hợp |
| `PKIXRevocationChecker` | Điều khiển cách kiểm tra thu hồi theo PKIX | Kết hợp CRL/OCSP, network/policy, không phải một repository |

`CertStore` là **cơ chế đọc** ứng viên. Không dùng `getCertificates(...)` thay cho `CertPathValidator.validate(...)` hoặc thay cho TLS hostname verification.

### 1.1. Tại sao “thu thập” khác “xác minh”?

Một kho LDAP hoặc file được cấu hình có thể chứa certificate **hết hạn**, certificate của CA không còn được tin, CRL cũ hoặc file bị sửa. Selector có thể lọc đúng tên subject/issuer mà **vẫn trả về certificate của kẻ tấn công có tên trùng**. Vì vậy:

- `getCertificates` chỉ xác định **ứng viên phù hợp tiêu chí**, không nói “người này là ai” ở mức tin cậy PKIX.
- `getCRLs` chỉ lấy **danh sách thu hồi ứng viên**, không xác nhận CRL thực sự do CA tin cậy ký.
- `X509CRL.isRevoked(cert)` xét một CRL đã có, không đủ để chứng minh certificate hiện tại hợp lệ cho mọi policy.
- Chỉ hệ thống **validation** với trust anchors, thời gian, thuật toán, key usage, name constraints, chính sách và revocation rules mới đưa ra kết luận tin cậy phù hợp.

## 2. API nền tảng của `java.security.cert.CertStore`

`CertStore` là một **engine class dựa trên Security Provider**. Phương thức `getInstance(...)` chọn type và cấu hình repository.

```java
CertStore store = CertStore.getInstance("Collection", parameters);
Collection<? extends Certificate> certs = store.getCertificates(certSelector);
Collection<? extends CRL> crls = store.getCRLs(crlSelector);
```

Đây là trích đoạn minh họa, không phải chương trình độc lập: các biến `parameters`, `certSelector`, `crlSelector` phải được khởi tạo; chương trình hoàn chỉnh nằm ở mục 6.

### 2.1. Các kiểu dữ liệu và phương thức chính

| API | Ý nghĩa |
| --- | --- |
| `CertStore.getInstance(String type, CertStoreParameters params)` | Tạo repository theo type/provider, với tham số khởi tạo |
| `CertStore.getInstance(type, params, provider)` | Chọn một provider cụ thể khi cần |
| `CertStore.getType()` | Type đã dùng, ví dụ `Collection` |
| `CertStore.getProvider()` | Provider triển khai repository |
| `CertStore.getCertificates(CertSelector)` | Trả collection candidate certificate khớp selector |
| `CertStore.getCRLs(CRLSelector)` | Trả collection candidate CRL khớp selector |
| `CollectionCertStoreParameters` | Chỉ định collection trong bộ nhớ làm repository |
| `LDAPCertStoreParameters` | Chỉ định LDAP host/port cho repository tương ứng |
| `CertStoreException` | Lỗi lúc truy vấn repository, bao gồm sự cố nguồn từ xa |

**Ý nghĩa của kết quả trả về:**

- Nếu không có item phù hợp, API trả **collection rỗng**, **không** trả `null` theo contract.
- `CertStoreException` thể hiện **lỗi thu thập**, khác hoàn toàn “đã thu thập thành công và không có item khớp”.
- Với repository từ xa, trả về collection có thể **không đầy đủ** khi provider không thể duyệt toàn bộ nguồn; các selector là cả **tiêu chí lọc** và **gợi ý truy vấn**.
- `CertStore.getInstance` có thể báo `NoSuchAlgorithmException` nếu type không hỗ trợ hoặc `InvalidAlgorithmParameterException` nếu cấu hình sai.
- `getCertificates(null)`/`getCRLs(null)` có thể được hỗ trợ để yêu cầu tất cả bản ghi, **nhưng không giả định** tất cả repository — nhất là LDAP — cho phép quét toàn bộ khi selector không đủ cụ thể.

### 2.2. Vì sao không dùng `KeyStore` để tìm mọi intermediate/CRL?

`KeyStore` thường truy cập một **tập dữ liệu được quản lý cho ứng dụng**: trusted root, private key, certificate chain đã nhập. Nó không phải API chung để truy vấn một hệ thống LDAP hoặc một repository có thể rất lớn với tiêu chí subject/issuer.

`CertStore` phù hợp khi ứng dụng đã có **nhiều certificate và CRL trong memory**, cần cung cấp danh sách đó cho `CertPathBuilder`, hoặc cần provider truy vấn một nguồn ngoài theo selector. Không dùng CertStore như một nơi để lưu private key; kiểu `Certificate` và `CRL` ở đây là tài liệu PKI công khai/có thể phân phối.

## 3. Lấy certificate bằng `X509CertSelector`

`X509CertSelector` triển khai `CertSelector` và cung cấp nhiều tiêu chí để chọn certificate X.509. Các tiêu chí được đặt đồng thời thường có nghĩa **certificate phải thỏa tất cả điều kiện đã cấu hình**.

### 3.1. Các tiêu chí thường gặp

- `setSubject(X500Principal)`: chọn certificate có **Subject DN** cụ thể.
- `setIssuer(X500Principal)`: chọn certificate do **Issuer DN** cụ thể phát hành.
- `setCertificate(X509Certificate)`: chọn certificate tương ứng đối tượng/chứng thư đã chỉ định theo contract.
- `setSerialNumber(BigInteger)`: chọn số seri certificate.
- `setCertificateValid(Date)`: chọn certificate có thời hạn hiệu lực (`notBefore`, `notAfter`) bao trùm thời điểm chỉ định.
- `setBasicConstraints(int)`: dùng để phân biệt CA và end-entity; **`setBasicConstraints(0)`** trong ví dụ chọn CA có basic constraints phù hợp.
- `setKeyUsage(boolean[])`: lọc các bit KeyUsage theo yêu cầu.
- `setSubjectAlternativeNames(...)` hoặc `addSubjectAlternativeName(...)`: lọc theo SAN với cấu trúc/type phù hợp.

Ví dụ lọc certificate CA với subject được biết:

```java
// Minh họa, chưa phải chương trình độc lập:
X509CertSelector selector = new X509CertSelector();
selector.setSubject(new X500Principal("CN=Training Demo CA,O=Learning"));
selector.setBasicConstraints(0);
Collection<? extends Certificate> matches = store.getCertificates(selector);
```

Phần lớn ứng dụng **không nên tự so tên DN thành string thủ công**, vì thứ tự, encoding, escaping của tên X.500 có thể khác. Dùng `X500Principal` và selector/API chuẩn giúp giảm nhầm lẫn.

### 3.2. `setSubject` khác `setIssuer`

Giả sử:

```text
Leaf:         Subject = CN=api.example       Issuer = CN=Intermediate CA
Intermediate: Subject = CN=Intermediate CA    Issuer = CN=Root CA
Root:         Subject = CN=Root CA            Issuer = CN=Root CA (self-signed)
```

Để **tìm intermediate ký leaf**, bạn thường cần một certificate **có Subject bằng Issuer của leaf**, rồi vẫn phải xác thực chữ ký leaf bằng public key của intermediate, kiểm tra CA/key usage và xây đường đến trust anchor. Đặt `setIssuer(leaf.getIssuerX500Principal())` sẽ tìm certificate **do intermediate phát hành**, không nhất thiết là intermediate certificate đang cần.

Một cách lấy ứng viên issuer:

```java
X509CertSelector findIssuer = new X509CertSelector();
findIssuer.setSubject(leaf.getIssuerX500Principal());
findIssuer.setBasicConstraints(0); // Chi tim ung vien CA
Collection<? extends Certificate> issuerCandidates =
        store.getCertificates(findIssuer);
```

Đây là trích đoạn, vì `leaf` và `store` phải tồn tại trước. **Trùng DN không chứng minh là cùng issuer key**; PKIX builder/validator còn dùng chữ ký, AuthorityKeyIdentifier, SubjectKeyIdentifier, policy, name constraints và trust anchor để đánh giá.

### 3.3. Tránh hiểu lầm khi có kết quả

Nếu selector trả **một** certificate, nó vẫn có thể không tin cậy. Nếu trả **nhiều** certificate, không chọn ngẫu nhiên phần tử đầu. Nếu trả **rỗng**, có thể là do repository thiếu intermediate hoặc selector quá chặt; không tự động chuyển sang “bỏ kiểm tra certificate chain”.

Đặc biệt, `setCertificateValid(new Date())` chỉ lọc theo **ngày hiệu lực** của certificate tại thời điểm hiện tại; nó **không kiểm tra revocation, hostname, EKU, policy hoặc chain**. Khi đang kiểm tra historical signatures, mốc thời gian hợp lệ có thể không phải “bây giờ” và phải theo policy nghiệp vụ.

## 4. Lấy CRL bằng `X509CRLSelector`

**CRL (Certificate Revocation List)** là cấu trúc X.509 do CA hoặc thực thể được ủy quyền phù hợp phát hành, chứa thông tin về những chứng thư bị thu hồi. Nó có metadata như:

- **Issuer** của CRL;
- **thisUpdate** — mốc cập nhật CRL;
- **nextUpdate** — mốc dự kiến danh sách mới;
- **CRL entries** có serial number, revocation date và có thể có reason;
- **signature**, signature algorithm và các extension như CRL Number, Authority Key Identifier, Issuing Distribution Point.

Không phải mọi CRL áp dụng cho mọi certificate cùng tên issuer: phải xét **scope**, distribution point, certificate type, reason coverage, indirect CRL và delta CRL nếu giao thức hỗ trợ chúng.

### 4.1. Các tiêu chí cơ bản

`X509CRLSelector` triển khai `CRLSelector`. Các phương thức có ích:

| API | Vai trò |
| --- | --- |
| `addIssuer(X500Principal)` | Chỉ chọn CRL có issuer DN phù hợp |
| `setIssuers(Collection<X500Principal>)` | Chọn một tập issuer DN được chấp nhận |
| `setDateAndTime(Date)` | Chỉ nhận CRL có khoảng `thisUpdate ≤ time < nextUpdate` |
| `setCertificateChecking(X509Certificate)` | Cung cấp **gợi ý** về certificate cần kiểm tra, hỗ trợ repository định vị CRL |
| `setMinCRLNumber(BigInteger)` | Chọn CRL Number không thấp hơn ngưỡng (nếu extension phù hợp) |
| `setMaxCRLNumber(BigInteger)` | Chọn CRL Number không vượt ngưỡng |
| `match(CRL)` | Kiểm tra CRL có thỏa tiêu chí filter không |

Để tìm CRL do CA cụ thể phát hành:

```java
X509CRLSelector selector = new X509CRLSelector();
selector.addIssuer(issuerCert.getSubjectX500Principal());
selector.setCertificateChecking(certBeingChecked);
selector.setDateAndTime(new Date());

Collection<? extends CRL> candidates = store.getCRLs(selector);
```

Đây là trích đoạn minh họa, cần khởi tạo `issuerCert`, `certBeingChecked`, `store` ở code thực.

**Điểm dễ nhầm:** `setCertificateChecking(cert)` **không phải điều kiện lọc riêng để hỏi “cert đã bị thu hồi?”**. Nó là **thông tin hỗ trợ tìm CRL**; nếu chỉ có `setCertificateChecking` mà không có issuer/đặc tả đủ rõ, provider có thể không truy vấn được mọi nguồn. Thực tế nên thêm issuer và thời gian phù hợp theo mục tiêu kiểm tra.

### 4.2. Tại sao `setDateAndTime` rất quan trọng?

Một CRL đã quá `nextUpdate` có thể **không còn đủ mới** để ra quyết định thu hồi tại thời điểm hiện tại. `X509CRLSelector.setDateAndTime(now)` yêu cầu:

```text
thisUpdate <= now < nextUpdate
```

Theo contract của selector X.509, **nếu CRL không có nextUpdate, tiêu chí thời gian này không match**. Bởi vậy, “không tìm thấy CRL” có thể là do CRL cũ, thiếu mốc hoặc time skew; không được suy luận “certificate không bị thu hồi”.

Hệ thống kiểm tra PKIX thực tế cần policy về clock skew, coverage, CRL freshness và nguồn thay thế (OCSP), chứ không chỉ dùng một phép chọn theo date.

### 4.3. `X509CRL.isRevoked` là gì và chưa đủ ở đâu?

Sau khi có một `X509CRL` cụ thể, `crl.isRevoked(cert)` hỏi liệu certificate đó được liệt kê là revoked trong CRL **đang cầm** hay không.

Nếu trả `false`, có ít nhất bốn khả năng:

1. Certificate thật sự chưa bị thu hồi và CRL phù hợp, còn hiệu lực đã được kiểm tra đúng;
2. CRL **không áp dụng** cho certificate đó;
3. CRL **cũ**, thiếu thông tin mới hoặc là partial/delta CRL;
4. CRL **chưa được xác minh chữ ký và chain trust** nên dữ liệu có thể bị giả mạo.

Vì vậy, **`false` không tương đương “certificate đáng tin cậy”**. Ngoài CRL còn phải xét validity, chain, BasicConstraints, KeyUsage, EKU, hostname/name constraints, thuật toán và trust policy.

### 4.4. Xác minh chữ ký CRL

`X509CRL.verify(PublicKey)` xác minh chữ ký của **một CRL** dưới public key được cung cấp. Nhưng nếu public key lấy từ một certificate chưa được xác minh, một chữ ký “đúng” vẫn không đủ để tin CRL.

Khi xây dựng hệ thống hoàn chỉnh, phải xác định **CRL signer** thích hợp, kiểm tra chain đến trust anchor, KeyUsage `cRLSign`, issuer/authority key identifier, scope/IDP, thuật toán chữ ký và validity của CRL. Java PKIX revocation checker xử lý các quy tắc và lựa chọn phức tạp hơn so với tự gọi mỗi `verify` và `isRevoked`.

## 5. Chuẩn bị fixture certificate và CRL bằng `keytool`

Để bài học **chạy độc lập không cần LDAP hay internet**, ta tạo một CA tự ký **chỉ dùng cho demo** và một CRL của CA đó. `keytool` đi kèm JDK có thể xuất certificate dạng PEM và CRL dạng PEM (`-rfc`).

**Lưu ý an toàn:** mật khẩu `samplepass` trong các lệnh sau chỉ phục vụ một fixture tạm được tạo ở thư mục học tập cô lập. Không dùng những lệnh chứa mật khẩu trên command line cho secret sản xuất, vì shell history, process list, CI log có thể ghi lại chúng. **Không nhập CA demo vào truststore dùng thật.**

Dùng thư mục **trống riêng cho bài học** rồi chạy các lệnh một dòng sau (dùng được trên shell có `keytool` trong `PATH`):

```bash
keytool -genkeypair -alias demo-ca -keyalg RSA -keysize 2048 -validity 365 -dname "CN=Training Demo CA,O=Learning" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -storetype PKCS12 -keystore demo-ca.p12 -storepass samplepass -keypass samplepass -noprompt

keytool -exportcert -rfc -alias demo-ca -keystore demo-ca.p12 -storepass samplepass -file demo-ca.pem

keytool -gencrl -rfc -alias demo-ca -keystore demo-ca.p12 -storepass samplepass -file demo-ca.crl.pem
```

Giải thích từng lệnh:

1. **`-genkeypair`:** sinh cặp khóa và certificate CA tự ký, `BasicConstraints=CA:true` và `KeyUsage` gồm `keyCertSign`, `cRLSign`. Đây là **test CA**, không nên xem là CA thực được một trình duyệt hay hệ điều hành tin cậy.
2. **`-exportcert -rfc`:** xuất **public certificate** dưới PEM vào `demo-ca.pem`; không xuất private key.
3. **`-gencrl -rfc`:** dùng private key của demo CA phát hành `demo-ca.crl.pem` có định dạng PEM, chứa CRL được ký. Nếu không chỉ định `-id`, fixture thường không có serial certificate nào bị thu hồi.

Với command trên, `demo-ca.p12` chứa **private key test**; đừng commit hoặc đưa nó lên nơi public. Sau thử nghiệm có thể xóa toàn bộ fixture trong thư mục test; để minh họa, code Java chỉ đọc **`demo-ca.pem`** và **`demo-ca.crl.pem`**.

### 5.1. Làm sao nhận biết hai file PEM?

Certificate PEM bắt đầu bằng:

```text
-----BEGIN CERTIFICATE-----
... (base64 encoding cua certificate)
-----END CERTIFICATE-----
```

CRL PEM bắt đầu bằng:

```text
-----BEGIN X509 CRL-----
... (base64 encoding cua CRL)
-----END X509 CRL-----
```

Đoạn trên chỉ minh họa **định dạng**, không phải chứng thư có giá trị để import. PEM là **cách biểu diễn dữ liệu ASN.1/DER bằng Base64 có header**, không làm certificate hoặc CRL đáng tin hơn. Với dữ liệu nhị phân DER, `CertificateFactory.getInstance("X.509")` cũng có thể parse theo khả năng provider.

### 5.2. Vì sao demo CA được dùng làm `TrustAnchor`?

Trong code mục 6, ta đăng ký certificate demo này làm một `TrustAnchor` **chỉ để cho thấy API PKIX nhận CertStore**. Trong ứng dụng thực, CA tin cậy phải được cấp phát/đánh giá theo chính sách từ nguồn tin cậy; **tuyệt đối không tự thêm CA bất kỳ tìm được qua CertStore thành TrustAnchor**. Làm thế có thể khiến kẻ tấn công đưa CA của họ vào danh sách tin cậy và ký chứng thư giả.

## 6. Chương trình Java 17+ hoàn chỉnh: `CertStore` từ `Collection`

Chương trình dưới đây:

- Parse một X.509 certificate và một X.509 CRL từ hai file PEM đã tạo;
- Tạo `CertStore.getInstance("Collection", CollectionCertStoreParameters(...))`;
- Truy vấn certificate bằng `X509CertSelector` theo Subject và CA BasicConstraints;
- Truy vấn một subject không tồn tại, cho kết quả rỗng;
- Truy vấn CRL bằng `X509CRLSelector` theo CA issuer, `setCertificateChecking` và thời gian;
- Minh họa rằng cần **xác minh chữ ký CRL** riêng với thao tác tìm;
- Gắn `CertStore` vào `PKIXParameters` trong bộ nhớ, không tự nhận là đã kiểm chứng một chain TLS thực.

Đây là **mã chạy được** với Java 17 trở lên và fixture ở mục 5.

Lưu đúng tên **CertStoreCollectionDemo.java**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CRL;
import java.security.cert.CertStore;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509CRL;
import java.security.cert.X509CRLSelector;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.Date;
import java.util.List;
import java.util.Set;
import javax.security.auth.x500.X500Principal;

public class CertStoreCollectionDemo {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException(
                "usage: CertStoreCollectionDemo cert.pem issuer.crl.pem");
        }

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        X509Certificate ca;
        X509CRL crl;
        try (InputStream certificateStream =
                     Files.newInputStream(Path.of(args[0]));
             InputStream crlStream =
                     Files.newInputStream(Path.of(args[1]))) {
            ca = (X509Certificate) factory.generateCertificate(
                    certificateStream);
            crl = (X509CRL) factory.generateCRL(crlStream);
        }

        CertStore store = CertStore.getInstance(
                "Collection",
                new CollectionCertStoreParameters(List.of(ca, crl)));

        X509CertSelector bySubject = new X509CertSelector();
        bySubject.setSubject(ca.getSubjectX500Principal());
        bySubject.setBasicConstraints(0); // Chon CA certificate.
        Collection<? extends Certificate> certificates =
                store.getCertificates(bySubject);

        X509CertSelector missingSubject = new X509CertSelector();
        missingSubject.setSubject(
                new X500Principal("CN=Not In Store"));
        Collection<? extends Certificate> missing =
                store.getCertificates(missingSubject);

        X509CRLSelector byIssuer = new X509CRLSelector();
        byIssuer.addIssuer(ca.getSubjectX500Principal());
        byIssuer.setCertificateChecking(ca);
        byIssuer.setDateAndTime(new Date());
        Collection<? extends CRL> crls = store.getCRLs(byIssuer);

        // Chi la kiem tra chu ky tren CRL demo, KHONG thay PKIX.
        crl.verify(ca.getPublicKey());
        ca.checkValidity();

        // Demo trust anchor da tin cai. Khong lam dieu nay voi CA tu CertStore.
        PKIXParameters parameters = new PKIXParameters(
                Set.of(new TrustAnchor(ca, null)));
        parameters.addCertStore(store);

        System.out.println("CertStore type: " + store.getType());
        System.out.println("CA certificates matched: "
                + certificates.size());
        System.out.println("unknown subject matched: "
                + missing.size());
        System.out.println("current CRLs matched: " + crls.size());
        System.out.println("CRL issuer equals CA subject: "
                + crl.getIssuerX500Principal()
                     .equals(ca.getSubjectX500Principal()));
        System.out.println("CRL signature verified: true");
        System.out.println("demo CA listed as revoked: "
                + crl.isRevoked(ca));
        System.out.println("PKIX CertStores registered: "
                + parameters.getCertStores().size());
    }
}
```

Biên dịch và chạy **sau khi đã tạo fixture**:

```bash
javac -encoding UTF-8 CertStoreCollectionDemo.java
java CertStoreCollectionDemo demo-ca.pem demo-ca.crl.pem
```

Stdout kỳ vọng trên JDK với provider `Collection` và certificate/CRL demo vừa tạo:

```text
CertStore type: Collection
CA certificates matched: 1
unknown subject matched: 0
current CRLs matched: 1
CRL issuer equals CA subject: true
CRL signature verified: true
demo CA listed as revoked: false
PKIX CertStores registered: 1
```

Chương trình được kiểm tra bằng biên dịch tương thích Java 17 (`javac --release 17`) và chạy trên JDK hỗ trợ Java 17+ cùng các fixture `keytool`. **Kết quả có thể khác nếu CRL hết thời hạn `nextUpdate`, certificate hết hạn hoặc fixture đã bị thay đổi**; hãy tạo fixture mới trước mỗi lần thử.

### 6.1. Phân tích từng khối code

**Parse X.509:** `CertificateFactory.generateCertificate` và `generateCRL` tạo đối tượng Java từ dữ liệu PEM/DER. Parse thành công **không** xác minh chuỗi tin cậy hay nguồn tải. `try-with-resources` đóng các file stream.

**Repository trong memory:** `new CollectionCertStoreParameters(List.of(ca, crl))` đưa hai loại đối tượng vào một `Collection`; provider thực hiện lọc certificate và CRL phù hợp. Ở đây certificate và CRL **không** được lấy từ mạng.

**Certificate selector:** `setSubject(ca.getSubjectX500Principal())` cùng `setBasicConstraints(0)` tìm CA certificate đúng Subject. `CN=Not In Store` không khớp nên trả collection rỗng.

**CRL selector:** `addIssuer(ca.getSubjectX500Principal())` khớp issuer của CRL demo; `setDateAndTime(new Date())` chỉ chọn CRL còn nằm trong khoảng `thisUpdate/nextUpdate` tại lúc chạy. `setCertificateChecking(ca)` cung cấp hint phù hợp với fixture; nó **không kiểm tra thu hồi tự động**.

**Kiểm tra riêng:** `crl.verify(ca.getPublicKey())` xác minh chữ ký của CRL demo bằng public key CA demo; `ca.checkValidity()` kiểm tra riêng validity date của certificate. **Cả hai chưa phải PKIX path validation đầy đủ.**

**Đăng ký PKIX:** `new PKIXParameters(Set.of(new TrustAnchor(ca, null)))` chỉ tạo tham số với CA mà ta **đã chủ động chọn tin trong môi trường demo**. `parameters.addCertStore(store)` cho phép builder/validator PKIX dùng repository; trong code này **chưa gọi `CertPathBuilder.build` hoặc `CertPathValidator.validate`**.

**`crl.isRevoked(ca) == false`:** fixture CRL không chứa serial của demo CA. Kết quả này **không được áp dụng như cơ chế quyết định bảo mật của sản phẩm**; CA tự ký của demo cũng không phải mô hình hoàn chỉnh cho kiểm tra CRL end-entity.

### 6.2. Một kiểm thử âm đặc biệt quan trọng

Thay certificate/CRL bằng file khác, chọn issuer DN không khớp hoặc đặt `setDateAndTime` sau `nextUpdate` có thể làm truy vấn trả **0**. Khi đó:

- `getCRLs` trả 0 là **không có ứng viên đủ tiêu chí**, không phải xác nhận “đối tượng không bị thu hồi”.
- Một CRL được parse và trả về có thể **không được ký bởi issuer đúng** nếu thay file không đáng tin; phải kiểm chứng chữ ký và policy.
- Nếu file PEM hỏng, `generateCertificate` hoặc `generateCRL` có thể ném `CertificateException`/`CRLException`; đó là lỗi đầu vào/parse, không phải “không có CRL”.
- Nếu repository LDAP lỗi network, `CertStoreException` cũng khác với việc trả 0.

Vì lý do này, code thực phải phân biệt **FOUND**, **NO_MATCH/INSUFFICIENT_DATA**, **FETCH_ERROR**, **PARSE_ERROR**, **UNTRUSTED_DATA** và **VALIDATED** thay vì chuyển tất cả về cùng boolean “certificate valid”.

## 7. Cấp CertStore cho `CertPathBuilder` và `CertPathValidator`

Việc dùng `CertStore` có giá trị lớn nhất khi nó nằm trong một luồng **PKIX certification path**. Phần này mô tả cách ghép các API, không giả vờ rằng một truy vấn đơn lẻ là xác thực chain.

### 7.1. Tìm đường dẫn với `PKIXBuilderParameters`

Để builder tìm chuỗi từ leaf đến CA được tin, ứng dụng cần:

1. **Trust anchors được cấu hình tin cậy** từ truststore/chính sách riêng; không lấy tự động tất cả certificate trả về từ repository để làm anchors.
2. **Target constraints** xác định certificate cần xây chain bằng `X509CertSelector` (ví dụ certificate exact, subject, SAN).
3. **CertStores** cung cấp intermediate certificate và CRL ứng viên.
4. **Tham số PKIX khác**: validity date, signature/provider policy, path length, certificate policy, revocation policy và các checker cần thiết.
5. Gọi `CertPathBuilder.getInstance("PKIX").build(params)`; xử lý `CertPathBuilderException` như **không xây được chain hợp lệ theo cấu hình**, không tự động retry bằng cách bỏ tin cậy/thu hồi.

Ví dụ trích đoạn (cần `targetCertificate`, `approvedAnchors` và `store` từ cấu hình/certificate hợp lệ của ứng dụng):

```java
X509CertSelector target = new X509CertSelector();
target.setCertificate(targetCertificate);

PKIXBuilderParameters params =
        new PKIXBuilderParameters(approvedAnchors, target);
params.addCertStore(store);

CertPathBuilder builder = CertPathBuilder.getInstance("PKIX");
PKIXCertPathBuilderResult result =
        (PKIXCertPathBuilderResult) builder.build(params);
CertPath path = result.getCertPath();
```

**Đây là một fragment, không phải file Java chạy độc lập.** Nó cố ý không “tự trust certificate tìm được”. `PKIXCertPathBuilderResult` còn mang thông tin trust anchor, public key và policy tree; quy trình hoàn chỉnh phải kiểm tra danh tính đích theo yêu cầu ứng dụng (ví dụ hostname TLS) ở lớp tương ứng.

### 7.2. Kiểm tra một path đã có bằng `PKIXParameters`

Nếu ứng dụng đã có `CertPath`, dùng `CertPathValidator` với `PKIXParameters`:

```java
PKIXParameters params = new PKIXParameters(approvedAnchors);
params.addCertStore(store);
// Cấu hình thời gian/policy/revocation phù hợp trước khi validate.
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
CertPathValidatorResult result = validator.validate(path, params);
```

Đây cũng là fragment, giả định `approvedAnchors` và `path` đã được cung cấp đúng. Không đặt `params.setRevocationEnabled(false)` chỉ để “tránh phải có CRL”. Khi thiếu nguồn thu hồi, cần quyết định theo chính sách fail-closed/soft-fail đã được đánh giá, không bỏ kiểm tra tùy tiện.

### 7.3. `addCertStore` có ý nghĩa gì?

`params.addCertStore(store)` thông báo repository mà PKIX implementation **có thể dùng** để tìm intermediate hoặc CRL trong quá trình xây dựng/xác minh. Nó **không**:

- Tự khởi chạy builder/validator;
- Tự tải toàn bộ certificate/CRL trong repository;
- Tự tạo trust anchor;
- Tự buộc mọi CRL tìm thấy được chấp nhận;
- Đảm bảo provider sẽ hỏi một loại repository theo cách/cùng thứ tự ở mọi JDK.

Cần thực sự gọi `build(...)`/`validate(...)` và kiểm tra kết quả/lỗi theo chính sách.

## 8. Nguồn CertStore: `Collection`, `LDAP` và repository từ xa

### 8.1. `Collection` — nguồn trong bộ nhớ

`Collection` rất hữu ích khi:

- Đã tải intermediate certificates hoặc CRLs qua kênh riêng có kiểm soát;
- Muốn có test fixture lặp lại được mà không dùng mạng;
- Cung cấp các certificate/CRL cụ thể cho PKIX builder/validator;
- Đã có một bộ dữ liệu đã parse từ PEM, DER hoặc file bundle theo trust policy của ứng dụng.

`CollectionCertStoreParameters` nhận một collection; ứng dụng cần quản lý nguồn dữ liệu, đối tượng đồng thời, kích thước, vòng đời và độ tin cậy khi tập dữ liệu có thể bị thay đổi. Một `CertStore` chứa item ở memory **không cấp cho item trạng thái đáng tin**.

### 8.2. `LDAP` — repository ngoài

Java có `LDAPCertStoreParameters` để cấu hình hostname và port; ví dụ cú pháp:

```java
// Minh họa API, không tạo kết nối thật trong bài học.
LDAPCertStoreParameters ldapParameters =
        new LDAPCertStoreParameters("ldap.example.internal", 389);

CertStore ldapStore =
        CertStore.getInstance("LDAP", ldapParameters);

X509CertSelector subjectSelector = new X509CertSelector();
subjectSelector.setSubject(
        new X500Principal("CN=Intermediate CA,O=Example"));
Collection<? extends Certificate> matches =
        ldapStore.getCertificates(subjectSelector);
```

Đây là fragment minh họa, **không chạy được khi không có LDAP server thích hợp**. Tên host là dữ liệu ví dụ; không tự gửi request đến host này trong bài học.

Các điểm phải lưu ý:

- Provider LDAP có thể cần **Subject DN, Issuer DN hoặc issuer info** đủ rõ để xác định DN/entry cần truy vấn. `getCertificates(null)` hoặc selector rỗng có thể không khả thi và dẫn đến `CertStoreException`.
- Với CRL, dùng `X509CRLSelector` và issuer, `setCertificateChecking` khi phù hợp để provider có gợi ý về CA cần hỏi.
- Các LDAP repository phải có dữ liệu và schema phù hợp với provider; không phải mọi LDAP/Active Directory setup đều có đúng certificate/CRL attributes mong muốn.
- Port 389 trong ví dụ chỉ mô tả cấu hình API; **không khẳng định kết nối được mã hóa hay xác thực**. Để dùng thực, phải thiết kế bảo vệ kết nối LDAP, certificate/TLS, authentication, credential storage và chống giả mạo nguồn theo provider/hạ tầng.
- Network failure, timeout, authentication failure và dữ liệu directory sai là những trạng thái riêng cần policy xử lý, không âm thầm coi là “không bị thu hồi”.

### 8.3. AIA và CRL Distribution Points có phải tự tải?

Certificate X.509 có thể chứa:

- **AIA — Authority Information Access:** có thể chỉ ra nơi tìm issuer certificate hoặc dịch vụ OCSP, tùy extension.
- **CRL Distribution Points (CDP):** có thể cho biết vị trí lấy CRL thích hợp.

**Không mặc định** rằng chỉ cần tạo `CertStore("Collection")` hoặc đọc một certificate có AIA/CDP là Java tự kết nối các URL đó. Việc tự động truy xuất AIA/CDP/OCSP phụ thuộc **PKIX provider, cấu hình runtime và chính sách giao thức**. Một số JDK có thuộc tính/provider behavior riêng; không dùng chúng như hợp đồng portable của `CertStore`.

Nếu ứng dụng tự tải certificate/CRL từ URI trong extension, phải coi các URI **không tin cậy**: áp allowlist domain/protocol, giới hạn size/time/redirect, bảo vệ chống SSRF, DNS rebinding, mạng nội bộ/metadata endpoints, loop và cache poisoning. Sau khi tải vẫn phải parse và PKIX-validate như thường lệ.

### 8.4. Caching và tính mới

CRL có `thisUpdate/nextUpdate`; một cache giữ CRL sau `nextUpdate` có thể gây sai chính sách thu hồi. Cần phân biệt **HTTP cache TTL, LDAP provider cache** và **validity/freshness của CRL**. Trạng thái “có dữ liệu cache” không đồng nghĩa “dữ liệu còn hợp lệ”.

Nếu app tạo `Collection` chứa dữ liệu cache riêng, app phải đảm bảo cache invalidation và rotation đúng. Nếu provider LDAP có cache nội bộ, thời gian/cách cấu hình phụ thuộc JDK/provider; không lấy cache TTL làm thay thế cho PKIX revocation validation.

## 9. Chính sách xác minh CRL, OCSP và `PKIXRevocationChecker`

### 9.1. CRL và OCSP khác nhau

- **CRL:** một danh sách thu hồi do CA/CRL signer phát hành, có thể được lưu/cached và phân phối qua LDAP/HTTP.
- **OCSP:** cơ chế hỏi trạng thái chứng thư (thường theo serial/issuer) qua OCSP responder, có ký phản hồi và metadata riêng.
- Hệ thống PKIX có thể dùng một hoặc cả hai theo chính sách. `CertStore.getCRLs` **không** phải API OCSP. Java dùng `PKIXRevocationChecker`/provider để kiểm soát revocation-checking trong PKIX.

### 9.2. `PKIXRevocationChecker`

Từ `CertPathBuilder` hoặc `CertPathValidator` loại `PKIX`, có thể lấy một checker hỗ trợ revocation:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
PKIXRevocationChecker checker =
        (PKIXRevocationChecker) validator.getRevocationChecker();

// Ví dụ: ưu tiên CRL. Cần đánh giá policy/fallback trước khi dùng.
checker.setOptions(EnumSet.of(
        PKIXRevocationChecker.Option.PREFER_CRLS));

params.addCertPathChecker(checker);
CertPathValidatorResult result = validator.validate(path, params);
```

**Fragment** trên giả định `params` và `path` có sẵn, cùng trust anchors và CertStores hợp lệ. Tùy implementation, khi cài checker explicit, cơ chế revocation do checker quản lý và phải hiểu interaction với `setRevocationEnabled` theo API. Đừng lắp thêm một checker mà không đánh giá hiệu lực policy.

Các option hay gặp:

| Option | Ý nghĩa | Rủi ro/lưu ý |
| --- | --- | --- |
| `PREFER_CRLS` | Ưu tiên CRL thay vì OCSP theo hành vi provider | Chỉ ưu tiên, không đảm bảo luôn có CRL phù hợp |
| `NO_FALLBACK` | Không thử cơ chế thay thế khi cơ chế ưu tiên thất bại | Có thể tăng lỗi khi nguồn không khả dụng; phù hợp hay không phụ thuộc policy |
| `SOFT_FAIL` | Trong những điều kiện nguồn revocation không truy cập được/lỗi được chỉ rõ, có thể cho qua | **Có thể chấp nhận certificate khi trạng thái thu hồi chưa xác định**; chỉ dùng khi threat model cho phép |
| `ONLY_END_ENTITY` | Chỉ kiểm tra thu hồi end-entity theo semantics của option | Không phù hợp nếu policy yêu cầu kiểm tra intermediates |

Không nên bật `SOFT_FAIL` để “xử lý mọi lỗi certificate”. Nó **không phải** công tắc cho phép bỏ qua invalid signatures, hết hạn, chain không tin cậy hoặc certificate đã bị xác định revoked. Một số trường hợp thiếu thông tin revocation phải **fail closed** theo chính sách của môi trường.

### 9.3. Khi nào “không tìm được CRL” phải chặn?

Một hệ thống tài chính hoặc mTLS nội bộ có chính sách revocation nghiêm có thể yêu cầu **từ chối** nếu không xác định được trạng thái thu hồi. Hệ thống khác có thể có chính sách mềm hơn để đảm bảo availability. Đây là **quyết định bảo mật công khai trong thiết kế**, có monitoring và kiểm toán, không phải fallback được cài ẩn trong `catch (CertStoreException e) { return true; }`.

Phải phân biệt:

```text
Certificate explicitly revoked         => REJECT
CRL signature invalid / scope invalid  => REJECT candidate; status unresolved
No current CRL or OCSP status           => UNKNOWN; handle by policy
Validated status good/not revoked      => Continue chain & identity checks
CertPath invalid for another reason    => REJECT
```

Một certificate “không có trong CRL được lấy” không tự được coi là `GOOD` nếu CRL chưa được xác minh/đúng scope/đủ mới.

## 10. Lỗi, giới hạn tài nguyên và bảo vệ dữ liệu nguồn

### 10.1. Bảng chẩn đoán lỗi Java

| Hiện tượng | Khả năng | Hướng xử lý |
| --- | --- | --- |
| `CertStore.getInstance("LDAP",...)` báo `NoSuchAlgorithmException` | Type/provider không hỗ trợ | Kiểm tra provider/JDK và danh sách algorithm đã được phê duyệt |
| `InvalidAlgorithmParameterException` khi tạo store | Tham số không đúng type/schema | Dùng `CollectionCertStoreParameters` hoặc `LDAPCertStoreParameters` đúng type |
| `getCertificates(...)` trả rỗng | Không có match hoặc repository không tìm được theo tiêu chí | Kiểm tra selector, subject/issuer và nguồn dữ liệu; không tự trust |
| `getCRLs(...)` trả rỗng | Không có CRL đúng issuer/time/scope, hoặc dữ liệu thiếu | Kiểm tra `nextUpdate`, issuer, policy, nguồn CRL/OCSP |
| `CertStoreException` khi truy vấn | Lỗi repository/provider/network hoặc selector không đủ cụ thể | Ghi log thông tin phi bí mật, phân loại trạng thái UNKNOWN |
| `CertificateException` / `CRLException` khi parse | Dữ liệu PEM/DER hỏng hoặc không đúng loại | Kiểm tra encoding và nguồn, fail safely |
| `crl.verify(...)` thất bại | Chữ ký sai, key không khớp hoặc thuật toán không hỗ trợ | Không dùng CRL như bằng chứng revocation |
| `CertPathBuilderException` | Không tìm được chain hợp lệ theo trust/policy | Xem trust anchors, intermediates và constraints, không bỏ xác thực |
| `CertPathValidatorException` | Path không thỏa ràng buộc PKIX | Giữ lỗi an toàn, xem cause/reason và policy |
| Kết quả khác giữa các provider | Khác hỗ trợ type/query/cache/schema | Kiểm tra hợp đồng provider và test interop |

### 10.2. Input validation

Certificate/CRL có thể đến từ mạng hoặc file do bên khác tạo. Trước khi parse:

- Giới hạn dung lượng file/response, số item, số redirects, timeout và số lần retry.
- Không đưa URL từ AIA/CDP trực tiếp vào fetcher có quyền truy cập metadata service hoặc mạng nội bộ.
- Dùng TLS/LDAP channel phù hợp và xác minh nguồn phân phối khi chính sách yêu cầu; đồng thời vẫn **kiểm tra chữ ký certificate/CRL**.
- Không để attacker điều khiển tùy ý `provider`, LDAP host/port, file path hoặc trust anchor.
- Sử dụng đúng kiểu Java `X509Certificate`/`X509CRL`, parse format hạn chế và không tạo quá nhiều đối tượng chưa kiểm soát trong cache.
- Đảm bảo thread-safety cho collection nguồn nếu cập nhật đồng thời; không tự giả định backing collection mutable có thể thay đổi vô hại khi provider đọc.
- Log các trường chẩn đoán vừa đủ như issuer, serial, CRL number, thời gian và correlation ID theo chính sách; tránh log toàn bộ certificate/CRL nếu chứa thông tin cá nhân hoặc làm tăng rò rỉ dữ liệu.

### 10.3. Phòng tránh downgrade và bypass

Không sửa logic thành:

```java
try {
    return store.getCRLs(selector).isEmpty(); // SAI
} catch (CertStoreException problem) {
    return true; // SAI
}
```

Truy vấn rỗng **không chứng minh** certificate tốt, còn exception càng không chứng minh điều đó. Để trả lời “trust this certificate?” phải đi qua **PKIX validator/revocation checker** với policy rõ ràng. Đừng chuyển từ CRL checking sang “không kiểm tra gì cả” khi LDAP tạm lỗi.

## 11. Tình huống áp dụng

### 11.1. Server nhận thiếu intermediate certificate

Một server TLS gửi leaf nhưng thiếu intermediate. Java client có thể gặp lỗi xây certification path. Có thể tải intermediate qua nguồn được policy cho phép, đưa candidate đó vào `Collection CertStore` hoặc repository có sẵn cho path builder.

**Không được** thêm intermediate bất kỳ tìm được thành trust anchor chỉ để cho chain chạy. Builder phải tìm đường dẫn được ký hợp lệ đến **root vốn đã được tin**.

### 11.2. Hệ thống nội bộ phát hành chứng thư người dùng

Một CA doanh nghiệp công bố CRL qua directory. `LDAP CertStore` giúp lấy candidate CRL đúng issuer. Nhưng để quyết định certificate có còn dùng được trong mTLS, validator phải kiểm tra chữ ký, issuer/key usage, scope, thời gian CRL và revocation status. Nếu directory không truy cập được, áp chính sách UNKNOWN phù hợp, không tự cho qua.

### 11.3. Test PKIX offline không phụ thuộc mạng

CI có thể có bộ certificate/CRL fixture dành riêng cho test, được parse bằng `CertificateFactory` và đưa vào `CertStore("Collection")`. Như vậy test selector và path builder ổn định hơn khi mạng bị thay đổi.

Nếu muốn kiểm tra riêng logic “certificate revoked”, cần fixture CA + leaf có serial cụ thể và **CRL chứa serial leaf đó** cùng bằng chứng ký hợp lệ. Demo ở mục 6 cố ý **không** tự khẳng định đã kiểm thử quy trình revocation đầy đủ; nó tập trung vào **thu thập bằng CertStore**.

### 11.4. Cập nhật CRL trong cache

Một CRL sắp hết `nextUpdate` cần được refresh trước khi sử dụng cho quyết định mới. Cache lỗi phải trả trạng thái rõ ràng, không giữ “CRL cũ nhưng vẫn bảo mật”. Có thể theo dõi issuer, CRL number, `thisUpdate/nextUpdate` và nguồn; không cần lưu lại secret key vì CRL là **dữ liệu công khai được ký**.

### 11.5. Nhiều nguồn thu thập

Một PKIX builder có thể được cấp **nhiều CertStores**, ví dụ Collection chứa certificate chain có sẵn cộng repository LDAP có thể tìm intermediate hoặc CRL. Mỗi nguồn đều có thể chứa ứng viên không đáng tin; **trọng tâm vẫn là trust anchors và validation policy**, không phải số lượng nguồn.

## 12. Lỗi thường gặp và cách sửa

| Nhầm lẫn | Hậu quả | Cách đúng |
| --- | --- | --- |
| “`CertStore` giống truststore.” | Tin certificate thu thập chưa xác thực | CertStore chỉ là repository; trust anchors cấu hình riêng |
| “`getCertificates` trả một kết quả nghĩa đã tin.” | Bỏ chain/signature/identity checks | Dùng `CertPathBuilder/Validator` với PKIX |
| “CRL trả về nghĩa certificate bị thu hồi.” | Không kiểm tra serial/issuer/scope | Kiểm tra revocation đúng certificate và validation policy |
| “`crl.isRevoked(cert)==false` nghĩa certificate an toàn.” | Có thể dùng CRL giả/cũ/khác scope | Verify CRL, chain, date, scope, PKIX status |
| “`setCertificateChecking(cert)` kiểm tra revocation luôn.” | Không có quyết định thu hồi | Đây là hint để tìm CRL; dùng PKIX revocation checker |
| “Đã có `setIssuer` là đủ xác minh chữ ký CRL.” | Issuer DN trùng không bảo đảm đúng key | Verify signer và chain/authorization |
| “CRL thiếu `nextUpdate` cũng match theo date.” | Selector có thể trả 0 | Hiểu `setDateAndTime` cần time window đầy đủ |
| “LDAP truy vấn không cần selector.” | Provider có thể không biết DN cần tìm | Cung cấp subject/issuer/certificateChecking phù hợp |
| “Collection trả rỗng = LDAP bị lỗi.” | Gộp trạng thái khác nhau | Phân biệt empty collection và `CertStoreException` |
| “Đưa certificate tìm thấy vào `TrustAnchor` để fix.” | Attacker có thể cài CA giả | Trust anchors chỉ từ cấu hình tin cậy riêng |
| “`getCRLs(null)` quét được toàn internet.” | API không làm crawler và LDAP có giới hạn | Truy vấn theo selector/repository được cấu hình |
| “AIA/CDP luôn được Java tự fetch.” | Ứng dụng bỏ sót intermediate/CRL | Kiểm tra provider/config và explicit retrieval policy |
| “Tải CRL qua HTTP là đủ an toàn.” | Có thể nhận dữ liệu thay đổi | Xác minh chữ ký/issuer/scope và network policy |
| “Nếu LDAP lỗi, cho qua để tăng availability.” | Bỏ revocation check không có kiểm soát | Fail closed hoặc soft-fail theo policy được phê duyệt |
| “Chỉ dùng CRL, không cần biết OCSP.” | Bỏ nguồn revocation có thể được yêu cầu | Chọn chiến lược CRL/OCSP theo PKIX và policy |
| “`setCertificateValid(now)` là toàn bộ xác minh.” | Thiếu chain, revocation, hostname, EKU | Chỉ lọc validity, sau đó PKIX và identity checks |

## 13. Checklist review thiết kế CertStore

1. **Mục đích:** cần tìm certificate trung gian, CRL, hay cả hai? Đã tách repository search khỏi quyết định tin cậy?
2. **Nguồn:** Collection/LDAP/provider tương thích, nguồn dữ liệu và quyền truy cập đã được kiểm soát?
3. **Selector:** dùng Subject/Issuer, serial/CA/validity hoặc CRL issuer/date/scope đúng yêu cầu; hiểu `setCertificateChecking` chỉ là hint?
4. **Lỗi:** phân biệt empty matches, parsing error, repository exception và revocation status UNKNOWN?
5. **Trust:** có trust anchors cấp phát riêng, không tự nâng candidate thành root được tin?
6. **PKIX:** có cung cấp `CertStore` cho `PKIXParameters`/`PKIXBuilderParameters` và thực sự gọi validator/builder phù hợp?
7. **CRL:** đã kiểm tra chữ ký, issuer, `thisUpdate/nextUpdate`, `cRLSign`, delta/IDP/scope khi áp dụng, algorithm policy?
8. **Revocation:** policy CRL/OCSP/fallback/soft-fail đã được mô tả và kiểm thử? Khi không xác định được trạng thái có làm đúng policy?
9. **Định danh:** ứng dụng TLS có kiểm tra hostname và mục đích sử dụng chứng thư tại lớp phù hợp, không chỉ chain?
10. **Network:** có giới hạn timeouts, redirects, size, SSRF/AIA/CDP risks, cache expiry và quyền truy cập?
11. **Kiểm thử:** có fixture valid/expired/wrong issuer/bad signature/truncated file/revoked leaf/LDAP unavailable?
12. **Vận hành:** có log an toàn, monitoring freshness/cache, rotation CA/CRL, rollback và audit?

## 14. Bài tập tự kiểm tra

**Câu 1.** `CertStore.getCertificates(selector)` trả về một certificate có `Subject DN` đúng. Có chắc certificate này đáng tin không?  
**Đáp án:** **Không.** Selector chỉ tìm candidate; PKIX chain/trust anchor và identity validation còn phải thực hiện.

**Câu 2.** Khi dùng `CollectionCertStoreParameters`, có thể đặt cả `X509Certificate` và `X509CRL` vào một collection không?  
**Đáp án:** **Có.** `CertStore("Collection")` dùng `getCertificates` để lấy certificate và `getCRLs` để lấy CRL phù hợp.

**Câu 3.** Một CRL có issuer đúng nhưng `nextUpdate` đã qua. `setDateAndTime(new Date())` thường trả về CRL đó không?  
**Đáp án:** **Không.** CRL phải bao trùm thời điểm yêu cầu theo `thisUpdate ≤ date < nextUpdate`.

**Câu 4.** `setCertificateChecking(cert)` trên `X509CRLSelector` có phải “kiểm tra ngay cert bị thu hồi” không?  
**Đáp án:** **Không.** Đây là hint cho repository khi tìm CRL; phải chạy revocation validation.

**Câu 5.** `getCRLs` trả collection rỗng. Có thể coi certificate đang tốt không?  
**Đáp án:** **Không.** Không có CRL match là **thiếu dữ liệu thu hồi phù hợp**, không phải trạng thái GOOD.

**Câu 6.** Kết quả `crl.verify(key)` thành công có đủ để tin CRL đó không?  
**Đáp án:** **Chưa đủ.** Phải biết key đó thuộc signer có quyền phát hành CRL theo trust chain/policy, kiểm tra thời gian và scope.

**Câu 7.** Tìm intermediate ký leaf thì lọc `setSubject(leaf.getIssuerX500Principal())` hay `setIssuer(leaf.getIssuerX500Principal())`?  
**Đáp án:** Thường bắt đầu bằng **`setSubject`** để tìm certificate có subject trùng Issuer DN của leaf; sau đó xác minh chữ ký và PKIX path.

**Câu 8.** `CertStore("LDAP")` có tự động tải CRL từ mọi URL CDP của certificate không?  
**Đáp án:** **Không được mặc định.** LDAP store truy vấn theo cấu hình/provider; AIA/CDP retrieval có cơ chế riêng và yêu cầu an toàn mạng.

**Câu 9.** Một developer gọi `params.addCertStore(store)` rồi lập tức chấp nhận certificate. Đúng chưa?  
**Đáp án:** **Chưa.** `addCertStore` chỉ đăng ký nguồn; còn phải `build`/`validate` với trust anchors, revocation và các checks khác.

**Câu 10.** Khi repository gặp `CertStoreException`, có nên trả `true` để bỏ qua kiểm tra CRL không?  
**Đáp án:** **Không được tự ý.** Phải ghi nhận trạng thái UNKNOWN và theo fail-closed/soft-fail policy được phê duyệt.

**Câu 11.** `SOFT_FAIL` trong `PKIXRevocationChecker` có nghĩa được bỏ qua mọi chữ ký certificate sai không?  
**Đáp án:** **Không.** Option chỉ áp dụng cho các loại lỗi không xác định được trạng thái thu hồi được quy định; không cấp quyền chấp nhận chain có lỗi bảo mật khác.

**Câu 12.** Vì sao không nên nhập CA vừa tìm trong CertStore vào truststore để sửa lỗi “unable to find valid certification path”?  
**Đáp án:** Như vậy biến dữ liệu **chưa được tin** thành **trust anchor**; attacker có thể lợi dụng để thiết lập CA giả. Phải xác minh nguồn/cấp phát trust anchor theo policy chính thức.

### Tài liệu tham khảo

- [Oracle Java 21 — Java PKI Programmer's Guide](https://docs.oracle.com/en/java/javase/21/security/java-pki-programmers-guide.html): mô hình `CertStore`, selectors, PKIX builder/validator và nguồn LDAP.
- [Java SE 21 — CertStore](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertStore.html): `getInstance`, `getCertificates`, `getCRLs` và error contract.
- [Java SE 21 — CollectionCertStoreParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CollectionCertStoreParameters.html): nguồn collection.
- [Java SE 21 — X509CertSelector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CertSelector.html): subject, issuer, validity và BasicConstraints.
- [Java SE 21 — X509CRLSelector](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CRLSelector.html): issuer, time, `setCertificateChecking`.
- [Java SE 21 — PKIXRevocationChecker](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): CRL/OCSP và policy.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): cấu trúc certificate, CRL, scope, trust path và revocation semantics.

### Ghi nhớ

**`CertStore` dùng để tìm certificate hoặc CRL; `X509CertSelector` và `X509CRLSelector` dùng để lọc ứng viên; `PKIX` và trust anchors mới quyết định certificate/path có được chấp nhận hay không.** Với CRL, tìm được dữ liệu chưa đủ: phải kiểm tra **chữ ký, issuer, thời gian, scope và chính sách thu hồi**, và không bao giờ biến “không tìm được CRL” thành “certificate hợp lệ” mà không có một chính sách bảo mật minh bạch.
