# 14.3. Cấu hình `PKIXParameters`, `PKIXBuilderParameters` và `X509CertSelector` trong Java 21

Một chuỗi chứng thư số trông có vẻ hợp lý — leaf do intermediate CA ký, intermediate do root CA ký — **chưa đủ** để một ứng dụng tin rằng chứng thư được cấp cho đúng đối tượng. Ứng dụng cần chọn **trust anchor** từ nguồn tin cậy riêng, tìm hoặc nhận **certificate path**, kiểm các chữ ký và ràng buộc **PKIX**, thời hạn, basic constraints, key usage, chính sách và trạng thái thu hồi khi áp dụng. Ngoài ra, giao thức còn phải xác minh **danh tính mục tiêu**, ví dụ hostname trong HTTPS.

Java cung cấp những khối xây dựng riêng biệt: `X509CertSelector` xác định chứng thư đích cần tìm; `PKIXBuilderParameters` cấu hình **tìm và dựng đường dẫn** đến trust anchor; còn `PKIXParameters` chứa các tham số để **xác minh đường dẫn đã có**. Chúng làm việc với `CertPathBuilder`, `CertPathValidator`, `CertStore` và `TrustAnchor`.

Bài học thuộc mục **“14. Đường dẫn tin cậy”** của Java Advanced – Security & Cryptography. Mục tiêu chính là cấu hình ba lớp `PKIXParameters`, `PKIXBuilderParameters` và `X509CertSelector` **đúng vai trò**, hiểu tác động từng tham số, thực hành Java 21 với chuỗi root → intermediate → leaf và thử trường hợp CA không được tin.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt *certificate path building*, *path validation* và *application identity verification*; giải thích vì sao kiểm chữ ký của từng certificate không tự tạo ra sự tin cậy.
2. Sử dụng `TrustAnchor` từ CA tin cậy **được cấu hình ngoài chuỗi chứng thư chưa tin**, hiểu nguồn `KeyStore` hoặc `Set<TrustAnchor>`.
3. Tạo `X509CertSelector` với leaf cụ thể, subject, `basicConstraints` và `extendedKeyUsage`; hiểu selector chỉ là **bộ lọc chứng thư đích**, không thay thế chứng thực toàn bộ path.
4. Cấu hình `PKIXBuilderParameters`, thêm `CertStore` chứa candidate certificates, `setMaxPathLength`, `setDate`/`setRevocationEnabled` theo chính sách; gọi `CertPathBuilder.getInstance("PKIX")`.
5. Dùng `PKIXParameters` với `CertPathValidator.getInstance("PKIX")` để xác minh một `CertPath` đã xây, kiểm tra root nhận được từ kết quả.
6. Chạy chương trình Java 21 đầy đủ và giải thích đầu ra **path entries = 2**, **root excluded**, **trusted root validated**, **untrusted root rejected**.
7. Tránh các lỗi như tin root do attacker gửi, tắt revocation trong production không có đánh giá, bỏ qua hostname/SAN, nhầm candidate `CertStore` với truststore và tự triển khai TLS certificate verification.

## 1. Mô hình trust path: ba vai trò trong một chuỗi

Xét hệ thống muốn xác thực chứng thư cho `service.example.test`. Chuỗi ví dụ:

```text
             Trust anchor: Lab Root CA
          (được cấu hình tin cậy độc lập)
                         |
                         | ký, CA:TRUE, pathLen:1
                         v
             Lab Intermediate CA
                 CA:TRUE, pathLen:0
                         |
                         | ký, CA:TRUE của issuer
                         v
    Leaf: CN=service.example.test
      SAN: DNS:service.example.test
      EKU: serverAuth
      BasicConstraints: CA:FALSE
```

Trong PKIX theo cách thường dùng:

- **Leaf (end-entity certificate):** chứng thư đích cần đánh giá; có public key dịch vụ, SAN, EKU và các extension.
- **Intermediate CA:** chứng thư CA trung gian dùng để xây path; chứng thư này phải thỏa mãn điều kiện ký certificate, basic constraints, path length, validity, signature/policy constraints.
- **Trust anchor/root:** một public key hoặc certificate đã **được quyết định tin bởi ứng dụng/truststore**. Đó là điểm kết thúc chuỗi logic, không phải thứ được tự suy ra vì certificate “tự ký”.

Một `CertPath` theo PKIX có thứ tự **target → intermediates**. **Trust anchor thường không nằm trong `CertPath.getCertificates()`**; nó được cung cấp riêng bằng tham số và xuất hiện trong kết quả build/validate. Với bài lab có một intermediate, số lượng certificate **trong path là 2**, dù sơ đồ logic có 3 certificate tính cả root.

### 1.1 Ba câu hỏi khác nhau

| Bước | Câu hỏi cần trả lời | Java API |
| --- | --- | --- |
| **Chọn target** | Chứng thư end-entity nào thỏa selector (subject, EKU, key usage...)? | `X509CertSelector` |
| **Path building** | Có thể xây chuỗi target → CA trung gian → trust anchor đã cấu hình không? | `PKIXBuilderParameters` + `CertPathBuilder` |
| **Path validation** | Một chuỗi đã có có hợp lệ theo PKIX, trust anchor, thời điểm/chính sách không? | `PKIXParameters` + `CertPathValidator` |
| **Identity/authorization** | Chứng thư hợp lệ có thực sự thuộc hostname/đơn vị/dịch vụ mong đợi và được phép thực hiện hành động này không? | TLS/JSSE hostname verifier, policy ứng dụng |

**Lưu ý:** `CertPathBuilder` theo PKIX vừa tìm đường dẫn vừa thực hiện/đòi hỏi tính hợp lệ của path theo tham số. Gọi `CertPathValidator` sau đó trong ví dụ là một bước **học tập minh họa**, không phải luôn bắt buộc sau mọi `CertPathBuilder` thành công. Không sử dụng điều đó để suy luận rằng builder “không validate gì”.

## 2. `PKIXParameters`: chính sách xác minh một path đã có

`java.security.cert.PKIXParameters` là một lớp tham số cho các thuật toán PKIX, đặc biệt `CertPathValidator`. Bạn có thể tạo từ:

```java
Set<TrustAnchor> anchors = Set.of(new TrustAnchor(rootCertificate, null));
PKIXParameters parameters = new PKIXParameters(anchors);
```

Đây là **đoạn minh họa trong scope** có biến `rootCertificate` thuộc kiểu `X509Certificate`; chương trình chạy đầy đủ nằm ở phần thực hành.

### 2.1 Điều kiện quan trọng nhất: TrustAnchor đúng nguồn

`TrustAnchor` thể hiện một CA/public key mà ứng dụng **đã quyết định tin**. Có thể tạo từ `X509Certificate` của CA hoặc CA name/public key theo constructor tương ứng. *Trust anchor không tự có độ tin cậy chỉ nhờ đối tượng Java được tạo.*

**Sai rất nguy hiểm:** lấy certificate cuối chuỗi do server chưa xác thực gửi tới, rồi viết `new TrustAnchor(peerRoot, null)`. Bằng cách đó attacker chỉ cần tự tạo root và ký leaf của mình là vượt được đường dẫn PKIX do ứng dụng vừa “tự tin” vào root giả.

**Đúng:** trust anchors đến từ truststore/configuration đã được bảo vệ, CA được quản trị, pinning hoặc quy trình phân phối ngoài băng tin cậy. Trong bài lab, file root PEM được coi như một **trust anchor được cấp trước có chủ đích** để mô phỏng việc cấu hình này, không có nghĩa mọi file root PEM bất kỳ phải được chấp nhận.

Có thể tạo `PKIXParameters` từ một `KeyStore` đã `load`, khi truststore có `TrustedCertificateEntry`:

```java
PKIXParameters parameters = new PKIXParameters(trustStore);
```

Constructor `KeyStore` chỉ dùng các trusted X.509 certificate entries làm CA đáng tin, không phải ngầm xem mọi `PrivateKeyEntry` là trust anchor. Phải quản lý file truststore riêng, kiểm soát import và update CA. `new PKIXParameters(Set.of(...))` cũng yêu cầu set không rỗng và các phần tử hợp lệ.

### 2.2 Các cấu hình quan trọng

| API | Ý nghĩa | Hướng dẫn |
| --- | --- | --- |
| `getTrustAnchors()` / `setTrustAnchors(...)` | Các CA/public keys được tin | Giữ nguồn và quyền cập nhật rõ ràng; không lấy từ peer tùy tiện |
| `setDate(Date)` | Thời điểm dùng khi kiểm tra chứng thư | Dùng đồng hồ/chính sách có kiểm soát; nếu không chỉ định, thông thường lấy thời điểm hiện hành |
| `setRevocationEnabled(boolean)` | Có thực hiện revocation checking theo khả năng provider/cấu hình không | **Không tắt trong production chỉ vì lab dễ chạy** |
| `addCertStore(CertStore)` | Nguồn các candidate certificate/CRL để tìm/kiểm path | Chứa candidate **không có nghĩa đã tin** |
| `setInitialPolicies(Set<String>)` | Tập certificate-policy OID quan tâm ban đầu | Chỉ cấu hình sau khi hiểu policy PKIX và yêu cầu của domain |
| `setExplicitPolicyRequired(boolean)` | Ràng buộc explicit policy | Có thể làm path không hợp lệ nếu policy cần không được đáp ứng |
| `setPolicyMappingInhibited(boolean)` | Kiểm soát policy mapping | Một phần kiểm soát certificate policy được tiêu chuẩn hóa |
| `setAnyPolicyInhibited(boolean)` | Kiểm soát vai trò `anyPolicy` | Tránh tự đặt theo suy đoán, cần profile cụ thể |
| `addCertPathChecker(PKIXCertPathChecker)` | Kiểm tra PKIX custom ở path | Chỉ dùng khi có yêu cầu đã được đặc tả và kiểm thử |
| `setSigProvider(String)` | Provider dùng cho xác minh chữ ký khi cần | Mặc định để JCA chọn thường phù hợp; chính sách HSM/FIPS có thể khác |

Một lỗi phổ biến là đặt `setRevocationEnabled(false)` để “không còn lỗi OCSP/CRL” rồi đưa vào production. Bài lab **cố ý tắt** vì toàn bộ CA tự dựng không phát hành CRL/OCSP; đây chỉ là cách tránh phụ thuộc dịch vụ mạng trong thử nghiệm, không phải khuyến nghị bảo mật.

### 2.3 Không nhầm certificate validity và trust policy

`setDate(...)` ảnh hưởng kiểm tra thời điểm hợp lệ `NotBefore/NotAfter` của các certificate đang kiểm. Dùng một thời điểm quá khứ để xác minh lưu trữ chữ ký lịch sử cần chính sách thời gian, timestamp và revocation phù hợp; **không** tùy tiện lùi đồng hồ để “làm cert hết hạn trở nên hợp lệ”. Các thuộc tính như certificate policies, name constraints, algorithm constraints và trust anchors vẫn quan trọng.

Root được chỉ định làm **trust anchor** thường không được xử lý như một chứng thư thông thường trong path. Tổ chức phải tự quản trị trust anchor về nguồn gốc, vòng đời, alg/key strength và thay thế an toàn.

## 3. `X509CertSelector`: cách mô tả chứng thư đích

`X509CertSelector` thực hiện interface `CertSelector` và cho phép kiểm tra một certificate có khớp yêu cầu không (`match(Certificate)`). Khi build PKIX, nó được truyền vào `PKIXBuilderParameters` làm `targetConstraints`.

Ví dụ trong chương trình sắp chạy:

```java
X509CertSelector target = new X509CertSelector();
target.setCertificate(leaf);
target.setSubject(leaf.getSubjectX500Principal());
target.setBasicConstraints(-2);
target.setExtendedKeyUsage(Set.of("1.3.6.1.5.5.7.3.1"));
```

Ý nghĩa:

- `setCertificate(leaf)` yêu cầu target chính là certificate cụ thể đó. Phù hợp khi ứng dụng đã nhận/giữ leaf và muốn dựng path cho nó; **không** nhất thiết dùng nếu bạn đang tìm nhiều certificate theo đặc tính.
- `setSubject(X500Principal)` ràng buộc subject distinguished name. Trong đoạn trên, nó mang tính minh họa thêm vì đã chỉ định chính certificate bằng `setCertificate`.
- `setBasicConstraints(-2)` có nghĩa chỉ chấp nhận **end-entity certificate**, không chấp nhận certificate CA. Với API này, `-1` là không áp constraint basic constraints, còn giá trị **0 trở lên** dùng để yêu cầu certificate CA với mức path length tương ứng.
- `setExtendedKeyUsage(Set<String>)` nhận **OID** dạng chuỗi; `1.3.6.1.5.5.7.3.1` là `id-kp-serverAuth`. Nếu certificate có EKU không phù hợp, selector sẽ không chọn nó. Không nhầm tên hiển thị `serverAuth` với tên API/OID.
- Có thêm `setKeyUsage(boolean[])`, `setSubjectAlternativeNames(...)`, `setIssuer(...)`, `setSerialNumber(...)`, `setCertificateValid(...)` và các selector chuyên biệt khác, cần biết chính xác hợp đồng và cách kết hợp trước khi dùng.

**Mỗi constraint đặt vào selector thường là điều kiện bổ sung**, chứ không mang ý nghĩa “nếu một điều kiện đúng thì đủ”. Chẳng hạn có cùng subject name chưa chứng minh cert được tin; tên `CN=service.example.test` có thể bị attacker đặt vào một chứng thư tự ký.

### 3.1 Selector khác hostname verification

Chọn certificate có `subject == X` hoặc `EKU == serverAuth` chưa tự kiểm tra **hostname bạn đang kết nối** là `api.example.test` hay `service.example.test`. HTTPS cần kiểm tra identity từ SAN và quy tắc protocol; TLS JSSE client nên được cấu hình **endpoint identification/hostname verification** theo profile. Một certificate chain có thể PKIX-valid nhưng dành cho **domain khác**. Chính sách ứng dụng còn có thể yêu cầu tenant, purpose và authorization độc lập.

`setSubjectAlternativeNames(...)` của `X509CertSelector` là một **bộ lọc** hữu ích khi lựa chọn, nhưng không tự thay thế toàn bộ hostname verification chuẩn TLS (wildcard, DNS/IP, tên quốc tế, các loại SAN và bối cảnh endpoint). Tránh tự viết hostname verifier tùy tiện nếu đã có stack TLS chuẩn.

### 3.2 Selector không đồng nghĩa PKIX validation

`selector.match(cert) == true` chỉ là sự phù hợp đối với **những điều kiện đã đặt**. Chữ ký issuer, CA path length, trust anchor, CRL/OCSP và các chính sách PKIX khác phải được kiểm theo builder/validator. Đừng tạo một selector với một điều kiện đúng rồi coi đó là chứng thư đáng tin.

## 4. `PKIXBuilderParameters`: từ target đến root đáng tin

`PKIXBuilderParameters` **kế thừa** `PKIXParameters` và bổ sung ràng buộc để bộ dựng đường dẫn lựa chọn target, tìm issuer certificates và dừng ở trust anchor.

Khởi tạo:

```java
Set<TrustAnchor> anchors =
        Set.of(new TrustAnchor(root, null));
PKIXBuilderParameters builderParams =
        new PKIXBuilderParameters(anchors, target);
```

Ở đây `root` là certificate được lấy từ kho tin cậy hợp lệ, `target` là `X509CertSelector` đã thiết lập. Một instance cũng có thể được tạo từ `KeyStore` cùng `CertSelector`. Mặc định của builder có giới hạn path length; bài lab đặt tường minh để thể hiện chính sách.

### 4.1 Dùng `CertStore` làm nguồn chứng thư trung gian

Builder cần tìm các certificate có thể nối leaf với trust anchor. Trong lab, không yêu cầu gọi HTTP hay LDAP:

```java
CertStore candidates = CertStore.getInstance(
        "Collection",
        new CollectionCertStoreParameters(
                List.of(leaf, intermediate)));
builderParams.addCertStore(candidates);
```

`CollectionCertStoreParameters` nhận một collection certificate/CRL trong bộ nhớ, hữu ích cho lab và nhiều luồng dữ liệu đã nhận sẵn. **CertStore chỉ là nguồn ứng viên, không phải nguồn tin cậy!** Bạn có thể thêm certificate do peer gửi vào `CertStore` để builder tìm path, miễn trust anchors đến từ nguồn độc lập. Thêm một CA tự ký vào collection không khiến nó được tin.

Ngoài Collection, provider có thể có nguồn certificate/CRL khác; lựa chọn và hành vi lấy issuer qua AIA/network không nên dựa vào phỏng đoán. Với hệ thống thật, thiết kế rõ cách fetch issuer và CRL/OCSP, caching, timeout, offline behavior và quyền truy cập mạng.

### 4.2 `setMaxPathLength` là giới hạn intermediates

Bài lab:

```java
builderParams.setMaxPathLength(1);
```

Trong PKIXBuilderParameters, tham số này giới hạn **số lượng certificate CA trung gian không tự cấp (non-self-issued)** trong path, không đơn thuần là `chain.length` và cũng không đếm leaf hay root trust anchor như thể chúng đều là intermediate.

- `0`: không cho intermediate thông thường; path chỉ cần một certificate end-entity dưới trust anchor khi có thể.
- `1`: cho một intermediate, như `Lab Intermediate CA` trong fixture.
- `-1`: không áp giới hạn từ thuộc tính này; **không** có nghĩa bỏ qua basic constraints của CA certificate.
- Nhỏ hơn `-1`: không hợp lệ.

Các extension `BasicConstraints.pathLenConstraint` của CA còn có ràng buộc riêng và có thể chặt hơn policy builder. Ví dụ root lab cho một intermediate, intermediate cho **0 CA cấp dưới nữa**. Vì vậy không thể thêm tùy ý một CA mới chỉ vì builder cho path length lớn.

### 4.3 Builder chạy thuật toán gì?

```java
PKIXCertPathBuilderResult result =
    (PKIXCertPathBuilderResult)
        CertPathBuilder.getInstance("PKIX").build(builderParams);
```

Kết quả chứa `CertPath` đã chọn, `TrustAnchor` được dùng, policy tree/public key liên quan. Nếu không tìm được chain hợp lệ, builder ném `CertPathBuilderException` (có thể chứa nguyên nhân provider-specific). Lỗi có thể do target không có, không có intermediate, trust anchor sai, cert hết hạn, không đáp ứng constraints, revocation unavailable hoặc policy mismatch; không kết luận “password sai” hay “public key sai” chỉ từ message chung.

**Build thành công không đồng nghĩa hostname đúng hoặc người dùng có quyền.** Đó là kiểm chứng PKIX theo tập tham số được cung cấp.

## 5. Thực hành: tạo CA root → intermediate → leaf bằng `keytool`

Chúng ta tạo **tệp lab duy nhất** `lab.p12` chứa private keys của CA và dịch vụ **chỉ để phát hành chứng thư thử nghiệm**. Sau đó xuất **bốn public certificates** thành PEM để Java build PKIX; chương trình Java **không đọc private key**. Điều này giữ trọng tâm đúng ở xây dựng/kiểm tra trust path.

> Tuyệt đối không áp dụng cách đặt CA signing private key cùng file dịch vụ trong production. Một PKI thật cần cách ly CA key (HSM/offline hoặc policy phù hợp), role separation, certificate issuance audit, revocation và bảo vệ backup.

### 5.1 Chuẩn bị thư mục và password lab

Dùng một **thư mục trống** với JDK 21 `keytool` và `javac` trong PATH. Hai cách đặt biến môi trường:

PowerShell (Windows):

```powershell
$env:PKIX_DEMO_PASS = 'LabOnly-TrustChain42'
```

Bash (Linux/macOS):

```bash
export PKIX_DEMO_PASS='LabOnly-TrustChain42'
```

Chuỗi trên **chỉ dành cho lab**. `-storepass:env PKIX_DEMO_PASS` đọc password từ biến môi trường thay vì đưa trực tiếp giá trị vào command line; đây chưa phải hệ thống quản lý secret production.

Kiểm tra:

```text
java -version
javac -version
keytool -help
```

### 5.2 Tạo root CA tự ký

```text
keytool -genkeypair -alias lab-root -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Lab Root CA,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -validity 60 -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -keypass:env PKIX_DEMO_PASS -noprompt
```

Root CA có `BasicConstraints CA:TRUE`, `pathLen:1` và `keyCertSign`. Certificate root tự ký **không tự đáng tin**: nó chỉ trở thành trust anchor của bài lab vì chúng ta **chủ động cấp trước** trong code.

### 5.3 Tạo intermediate có chữ ký của root

```text
keytool -genkeypair -alias lab-intermediate -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=Lab Intermediate CA,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -signer lab-root -signerkeypass:env PKIX_DEMO_PASS -validity 45 -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -keypass:env PKIX_DEMO_PASS -noprompt
```

`-signer lab-root` dùng private key ở alias root ký intermediate; tạo chain cho alias `lab-intermediate`. Extension `pathlen:0` ngăn intermediate này làm CA cấp trên cho **một CA trung gian mới** nữa, nhưng vẫn có thể cấp end-entity certificate theo policy.

### 5.4 Tạo chứng thư dịch vụ (leaf) do intermediate ký

```text
keytool -genkeypair -alias lab-service -keyalg RSA -keysize 3072 -sigalg SHA256withRSA -dname "CN=service.example.test,O=Training,C=VN" -ext "BC:critical=ca:false" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -ext "SAN=dns:service.example.test" -signer lab-intermediate -signerkeypass:env PKIX_DEMO_PASS -validity 20 -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -keypass:env PKIX_DEMO_PASS -noprompt
```

Leaf có `BasicConstraints CA:FALSE`, EKU `serverAuth` và DNS SAN `service.example.test`. Đây là certificate lab, **không dùng làm chứng thư TLS production** và không trông đợi được trình duyệt tin vì root CA tự ký chưa nằm trong truststore.

Trong `lab.p12`, `lab-service` có thể có chain length **3**: leaf + intermediate + root. Nhưng khi Java xây path đối với root làm `TrustAnchor`, kết quả `CertPath` chỉ chứa leaf + intermediate.

### 5.5 Tạo root không đáng tin để kiểm thử thất bại

```text
keytool -genkeypair -alias lab-untrusted -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Untrusted Root,O=Training,C=VN" -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -validity 50 -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -keypass:env PKIX_DEMO_PASS -noprompt
```

`lab-untrusted` là một CA riêng, không ký leaf hay intermediate ở trên. Khi thay root tin cậy bằng chứng thư này, builder **phải thất bại** dù leaf và intermediate đều có chữ ký nội bộ khớp.

### 5.6 Xuất certificate PEM cho Java

Chạy bốn lệnh, chỉ xuất **public certificates**, không xuất private key:

```text
keytool -exportcert -rfc -alias lab-root -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -file lab-root.pem
keytool -exportcert -rfc -alias lab-intermediate -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -file lab-intermediate.pem
keytool -exportcert -rfc -alias lab-service -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -file lab-service.pem
keytool -exportcert -rfc -alias lab-untrusted -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS -file lab-untrusted.pem
```

Kiểm tra alias service:

```text
keytool -list -v -alias lab-service -keystore lab.p12 -storetype PKCS12 -storepass:env PKIX_DEMO_PASS
```

Các dòng cấu trúc mong đợi:

```text
Alias name: lab-service
Entry type: PrivateKeyEntry
Certificate chain length: 3
Owner: CN=service.example.test, O=Training, C=VN
Issuer: CN=Lab Intermediate CA, O=Training, C=VN
...
Owner: CN=Lab Intermediate CA, O=Training, C=VN
Issuer: CN=Lab Root CA, O=Training, C=VN
...
Owner: CN=Lab Root CA, O=Training, C=VN
Issuer: CN=Lab Root CA, O=Training, C=VN
```

`keytool -list` hiển thị **chain lưu trong KeyStore**, không phải `CertPath` mà validator nhận sau này. Hai khái niệm có thứ tự liên quan nhưng **khác điểm kết thúc**.

## 6. Java 21: builder + validator + selector, kiểm cả trường hợp CA sai

Tạo file **`PkixPathDemo.java`** trong cùng thư mục với bốn tệp `*.pem`. Chương trình không dùng private key và không cần dependency ngoài JDK.

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPathBuilder;
import java.security.cert.CertPathBuilderException;
import java.security.cert.CertPathValidator;
import java.security.cert.CertStore;
import java.security.cert.CollectionCertStoreParameters;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXBuilderParameters;
import java.security.cert.PKIXCertPathBuilderResult;
import java.security.cert.PKIXCertPathValidatorResult;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509CertSelector;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class PkixPathDemo {
    static X509Certificate read(Path directory, String name) throws Exception {
        CertificateFactory cf = CertificateFactory.getInstance("X.509");
        try (InputStream in = Files.newInputStream(directory.resolve(name))) {
            return (X509Certificate) cf.generateCertificate(in);
        }
    }

    public static void main(String[] args) throws Exception {
        Path directory = Path.of(args.length == 1 ? args[0] : ".");
        X509Certificate root = read(directory, "lab-root.pem");
        X509Certificate intermediate = read(directory, "lab-intermediate.pem");
        X509Certificate leaf = read(directory, "lab-service.pem");
        X509Certificate otherRoot = read(directory, "lab-untrusted.pem");

        // Policy: trust is provisioned from outside the untrusted chain.
        Set<TrustAnchor> anchors = Set.of(new TrustAnchor(root, null));
        X509CertSelector target = new X509CertSelector();
        target.setCertificate(leaf);
        target.setSubject(leaf.getSubjectX500Principal());
        target.setBasicConstraints(-2); // End-entity, not a CA.
        target.setExtendedKeyUsage(Set.of("1.3.6.1.5.5.7.3.1")); // serverAuth

        CertStore issuerCandidates = CertStore.getInstance("Collection",
                new CollectionCertStoreParameters(List.of(leaf, intermediate)));
        PKIXBuilderParameters buildParams =
                new PKIXBuilderParameters(anchors, target);
        buildParams.addCertStore(issuerCandidates);
        buildParams.setMaxPathLength(1);
        buildParams.setRevocationEnabled(false); // Lab only!

        PKIXCertPathBuilderResult path =
                (PKIXCertPathBuilderResult) CertPathBuilder
                        .getInstance("PKIX").build(buildParams);
        System.out.println("path entries: " +
                path.getCertPath().getCertificates().size());
        System.out.println("root omitted from path: " +
                !path.getCertPath().getCertificates().contains(root));
        System.out.println("path starts at leaf: " +
                path.getCertPath().getCertificates().get(0).equals(leaf));

        PKIXParameters validationParams = new PKIXParameters(anchors);
        validationParams.setRevocationEnabled(false); // Lab only!
        PKIXCertPathValidatorResult verified =
                (PKIXCertPathValidatorResult) CertPathValidator
                        .getInstance("PKIX").validate(
                                path.getCertPath(), validationParams);
        System.out.println("validated with trusted root: " +
                verified.getTrustAnchor().getTrustedCert().equals(root));

        PKIXBuilderParameters wrongAnchors =
                new PKIXBuilderParameters(
                        Set.of(new TrustAnchor(otherRoot, null)), target);
        wrongAnchors.setRevocationEnabled(false); // Lab only!
        wrongAnchors.addCertStore(issuerCandidates);
        boolean rejected = false;
        try {
            CertPathBuilder.getInstance("PKIX").build(wrongAnchors);
        } catch (CertPathBuilderException expected) {
            rejected = true;
        }
        System.out.println("untrusted root rejected: " + rejected);
    }
}
```

### 6.1 Biên dịch và chạy

Khi các tệp `lab-root.pem`, `lab-intermediate.pem`, `lab-service.pem`, `lab-untrusted.pem` nằm trong thư mục hiện tại:

```text
javac --release 21 -encoding UTF-8 PkixPathDemo.java
java PkixPathDemo .
```

Stdout từ fixture đã tạo:

```text
path entries: 2
root omitted from path: true
path starts at leaf: true
validated with trusted root: true
untrusted root rejected: true
```

Đầu ra này đã được kiểm tra với compiler hỗ trợ `--release 21` và JDK provider PKIX thông dụng. Việc tạo khóa dùng `SecureRandom` và `keytool` nên nội dung certificate/fingerprint sẽ khác giữa các lần thử, nhưng các **boolean và path length** nói trên ổn định nếu fixture và chính sách được giữ đúng.

### 6.2 Diễn giải từng bước, từng dòng output

1. `CertificateFactory.getInstance("X.509")` parse PEM certificates. **Đọc được một certificate không có nghĩa là certificate đã được xác minh.** Đừng import root do attacker cung cấp làm trust anchor.
2. `new TrustAnchor(root, null)` khai báo root đáng tin **theo giả định trust được cấp trước trong lab**. Tham số `null` là name constraints bổ sung của trust anchor (không phải mật khẩu hay khóa).
3. `X509CertSelector` chọn chính leaf, yêu cầu end-entity và EKU serverAuth; đây là **target constraint** cho path builder.
4. `CollectionCertStoreParameters(List.of(leaf, intermediate))` cung cấp certificates **để tìm path**, không nâng mức tin cậy. Root không cần nằm trong `CertStore` vì đã được truyền riêng qua `anchors`.
5. `buildParams.setMaxPathLength(1)` chấp nhận một intermediate CA. Extension `BC.pathLen` của CA cũng được kiểm theo PKIX.
6. `build(...)` trả `PKIXCertPathBuilderResult`, trong đó `getCertPath().getCertificates()` gồm **leaf trước, intermediate sau**. Vì root là trust anchor ngoài path, `path entries: 2` và `root omitted from path: true`.
7. `new PKIXParameters(anchors)` và `validate(path, params)` xác minh **cert path đã có**, không tìm một path mới. `verified.getTrustAnchor()` trỏ về root được chấp nhận.
8. Thay trust anchors bằng `otherRoot` không có quan hệ cấp phát với leaf/intermediate làm builder không tìm được path hợp lệ. Chương trình bắt `CertPathBuilderException` và in `untrusted root rejected: true`.
9. `setRevocationEnabled(false)` xuất hiện ở cả build và validate **chỉ để lab offline có kết quả tái lập**. Với hệ thống thật, lập chính sách revocation và nguồn CRL/OCSP đúng profile; không sao chép cấu hình này mà thiếu phân tích bảo mật.

### 6.3 Một điểm có thể gây hiểu sai: root PEM nằm cạnh leaf PEM

Trong demo, chúng ta lưu cả bốn PEM cùng thư mục để thuận tiện. **Vị trí vật lý cùng thư mục không làm root đáng tin**; đoạn code cố ý chỉ định `lab-root.pem` làm trust anchor theo giả định root đó được cấp một cách đáng tin trước thời điểm nhận message. Nếu attacker điều khiển được thư mục rồi thay đồng thời `lab-root.pem` và `lab-service.pem`, demo sẽ có thể chấp nhận chuỗi mới do attacker tạo. Production cần truststore/kho cấu hình bảo vệ quyền ghi, pinning/chính sách quản trị root và đường dẫn filesystem phù hợp.

Không lưu khóa riêng CA trong kho mà ứng dụng validation có quyền đọc. Demo Java chỉ nhận PEM public certificates; tệp `lab.p12` dùng tạo chứng thư và nên xóa sau lab.

## 7. Thử nghiệm thất bại: biết lỗi nằm ở tầng nào

Một chương trình PKIX thực tế sẽ gặp nhiều lỗi không đơn thuần là “signature sai”.

| Thay đổi trong lab | Điều bạn nên quan sát | Giải thích |
| --- | --- | --- |
| Chỉ cấp `otherRoot` làm trust anchor | `CertPathBuilderException` | Không có chuỗi từ leaf đến root được tin |
| Xóa intermediate khỏi `CertStore` (không có nguồn khác) | Thông thường không build được | Thiếu certificate issuer để nối lên root |
| Giữ root, thay leaf bằng certificate khác | Có thể selector mismatch hoặc path khác | Target constraints xác định certificate mong muốn |
| Đặt `setMaxPathLength(0)` khi cần một intermediate | Builder từ chối path này | Policy không cho CA trung gian cần thiết |
| Dùng cert leaf hết hạn theo thời điểm validation | `CertPathValidatorException` hoặc builder failure | Date window không còn hợp lệ |
| Intermediate thiếu `CA:TRUE` / `keyCertSign` | Path không hợp lệ | BasicConstraints/KeyUsage không cho ký certificate |
| Intermediate bị ràng buộc `pathLen:0` nhưng thêm CA bên dưới | Path không hợp lệ | Vượt CA path length của issuer |
| Sai EKU ở selector | Không chọn được target | Selector target không khớp |
| Không có dịch vụ CRL/OCSP nhưng bật revocation | Có thể fail do không xác minh được trạng thái | Phải cấu hình chính sách/source, không đơn giản tắt tùy tiện |
| PKIX pass nhưng URL hostname khác SAN | PKIX có thể pass, **TLS identity check phải reject** | Path trust khác mục đích endpoint |
| CA root hợp lệ nhưng policy ứng dụng không chấp nhận loại client | PKIX có thể pass, ứng dụng phải reject | Chain validation không đồng nghĩa authorization |

Bước kiểm lỗi có hệ thống:

1. **Parsing:** kiểm đúng loại DER/PEM, certificate có đọc được không, path có trùng/thiếu phần tử?
2. **Target selector:** dùng `match(...)`/kiểm constraints để biết leaf có phù hợp điều kiện không.
3. **Candidates:** intermediate có được cung cấp/truy xuất trong `CertStore` không, có đúng issuer subject/key identifier không?
4. **Trust anchors:** root được lấy từ **nguồn quản trị đáng tin** hay do peer gửi? Có đúng root được hệ thống cho phép không?
5. **PKIX constraints:** validity date, CA basic constraints, signature algorithm, key size/algorithm constraints, policies, name constraints, revocation.
6. **Identity/application:** hostname/SAN, EKU/service role, authorization, pinning nếu dùng.
7. **Vận hành:** JDK/provider và crypto policy, network access, timeouts, chênh lệch đồng hồ, CRL/OCSP cache.

**Không trả toàn bộ diagnostic certificate chain/CA names/stack traces qua public HTTP API**. Ghi log có cấu trúc ở phía nội bộ với mức nhạy cảm hợp lý, cung cấp cho client một lỗi xác thực an toàn, và không tự động fallback sang “accept all” khi validate thất bại.

## 8. Những constructor và API dễ nhầm

### 8.1 `PKIXParameters` từ `Set<TrustAnchor>` hay `KeyStore`

Từ một set:

```java
PKIXParameters validationParams =
        new PKIXParameters(Set.of(new TrustAnchor(root, null)));
```

Từ truststore đã load (đoạn minh họa, `trustStore` phải có TrustedCertificateEntry):

```java
PKIXParameters validationParams = new PKIXParameters(trustStore);
```

Hai cách đều tạo policy trust anchors. **Không** đưa một identity keystore chứa private keys của dịch vụ vào và mặc định rằng constructor sẽ lấy certificate chain của mọi private-key alias làm root tin cậy.

### 8.2 `PKIXBuilderParameters` cần target

```java
PKIXBuilderParameters buildParams =
        new PKIXBuilderParameters(anchors, target);
```

Constructor này bắt buộc target constraints thích hợp. Với selector trống và nguồn candidates rộng, builder có thể chọn không đúng đối tượng mong muốn; ứng dụng phải chỉ rõ **ai/cert nào cần chứng minh**. Với constructor từ `KeyStore`, trust anchors cũng đến từ trusted entries như đã trình bày.

### 8.3 `X509CertSelector` chỉ lọc certificate

```java
X509CertSelector selector = new X509CertSelector();
selector.setSubject(leaf.getSubjectX500Principal());
selector.setBasicConstraints(-2);
boolean matches = selector.match(leaf);
```

Đoạn này **không độc lập**: cần biến `leaf` đã được đọc. `matches == true` chỉ xác nhận leaf đáp ứng selector; certificate tự ký có cùng subject cũng có thể match nếu selector không ràng buộc khóa/chứng thư. Chỉ PKIX path + trust policy mới quyết định certificate có nằm trên đường dẫn tin cậy không.

### 8.4 `CertPath` có sẵn khác `CertPathBuilder`

Khi đối tác gửi sẵn chain, có thể tạo `CertPath` bằng `CertificateFactory.generateCertPath(List<? extends Certificate>)` theo thứ tự phù hợp, rồi gọi `CertPathValidator` với `PKIXParameters`. Nếu không có chain hoàn chỉnh, `CertPathBuilder` kết hợp candidate `CertStore`/trust anchors để **tìm** một path thích hợp.

Không đưa root vào path rồi kỳ vọng số lượng phần tử luôn đúng như sơ đồ. Hợp đồng PKIX giả định trust anchor **tách khỏi cert path**, và builder demo thể hiện rõ điều đó.

## 9. Tăng chất lượng chính sách PKIX ngoài bài lab

### 9.1 Trust anchor governance

Quản lý trust anchors như một thành phần an ninh trọng yếu: ai được thêm/xóa CA, cập nhật truststore ra sao, audit, key strength, thời hạn sử dụng, revocation/compromise response, policy theo môi trường test/staging/prod và rollover. **Một CA được trust thường có thể ký nhiều leaf** trong phạm vi name constraints/policies, nên quyền thêm root có tác động rất rộng.

Nếu ứng dụng chỉ cần tin một service cụ thể, có thể cân nhắc pinning theo quy trình quản trị/rotate phù hợp, hoặc private PKI có name constraints và issuance policy rõ. Không tự lấy root từ handshake phía ngoài rồi biến nó thành trust anchor.

### 9.2 Revocation, CRL và OCSP

PKIX path validation thông thường có thể áp dụng revocation checking. `PKIXParameters.setRevocationEnabled(true)` là cờ quan trọng, nhưng **không bảo đảm** mọi thứ sẽ đúng nếu CRL/OCSP provider/network chưa được cấu hình. Có thể cần `PKIXRevocationChecker` từ validator/provider hoặc trust manager chính thức, `CertStore` chứa CRL, OCSP responder, cache, timeout và chính sách **hard-fail/soft-fail** theo threat model. Không tự xem cert là “good” chỉ vì gọi API mà không có nguồn trạng thái thu hồi.

Bật/tắt revocation là quyết định hệ thống, không phải mẹo xử lý exception. Nếu chỉ học offline, hãy ghi chú tường minh “LAB ONLY” như trong code. Khi triển khai, kiểm tra cách JSSE stack đang sử dụng CRL/OCSP và các system/security properties liên quan cho đúng phiên bản JDK.

### 9.3 Application identity và mục đích sử dụng

Ngay cả path tin cậy cũng phải được ràng buộc với đích:

- **HTTPS:** SAN DNS/IP phải khớp hostname, kiểm tra protocol version và EKU serverAuth đúng policy.
- **Mutual TLS:** kiểm tra certificate phía client với trust policy phù hợp, sau đó ánh xạ certificate identity đến principal/tenant và xác minh quyền thực hiện request.
- **Code signing:** mục đích key usage/EKU/signing policy khác TLS; không coi một leaf chỉ có `serverAuth` là authorized code signer.
- **Document signing:** phải biết signer/đơn vị cần tin, chính sách thời gian và chứng cứ ký; chỉ path validation vẫn không bảo đảm thẩm quyền nghiệp vụ.

Trong ứng dụng Java thực, nên để **JSSE/HTTPS** thực hiện chứng thực TLS theo chuẩn, với `SSLContext`, `TrustManagerFactory`, `PKIX` trust manager và hostname verification phù hợp; không thay TrustManager bằng loại “accept any certificate” hoặc cố kiểm CN thủ công.

### 9.4 Algorithm constraints và đồng hồ

Chữ ký RSA-3072/SHA-256 trong lab được chọn để tương thích JDK21 và mục tiêu học tập. Hệ thống thật phải áp dụng algorithm constraints của profile, cập nhật khi thuật toán/khóa bị coi là yếu, xử lý certificate quá hạn/not-yet-valid và đồng bộ đồng hồ. Không cố “sửa” lỗi bằng cách chấp nhận bất kỳ chữ ký hay tắt certificate validity checks.

`setDate` nên được dùng có mục đích (ví dụ test thời điểm hoặc profile xác minh chữ ký lịch sử được chuẩn hóa); không chuyển thời gian lùi tùy ý chỉ để vượt chứng thư hết hạn.

### 9.5 PKIX path builder không phải giao thức tin cậy đầy đủ

`CertPathBuilder` và `CertPathValidator` làm đúng nhiệm vụ PKIX, nhưng chúng không tự xử lý bảo mật kênh TLS, chứng minh possession of private key trong handshake, chống replay yêu cầu ứng dụng, authorization, thông điệp nghiệp vụ hay idempotency. Các lớp phải phối hợp:

```text
Truststore / managed CA roots
              |
              v
X509CertSelector + CertStore candidates
              |
              v
PKIXBuilderParameters ----> CertPathBuilder("PKIX")
              |                        |
              |                        v
              |                 path + trust anchor
              |                        |
              v                        v
 PKIXParameters ------------> CertPathValidator("PKIX")
                                       |
                                       v
               Hostname/SAN + EKU + endpoint/application policy
                                       |
                                       v
                       Authenticated channel / authorization
```

Trong HTTPS client thông thường, những bước này thường được framework và JSSE stack tổ chức thay cho ứng dụng; bạn không cần tự gọi `CertPathBuilder` trên mọi request. Dù vậy, hiểu ba lớp này giúp rà soát việc **chọn CA, cấu hình truststore, xử lý certificate-chain failure** và tránh lỗ hổng trust bypass.

## 10. Những sai lầm phổ biến cần nhớ

1. **“Có ba chứng thư trong chain là đủ tin cậy.”** Sai: chain đầy đủ nhưng root không nằm trong truststore được bảo vệ vẫn có thể do attacker tự ký.
2. **“Lấy root từ gói bên kia rồi `new TrustAnchor(root,null)`.”** Sai: tự cho phép attacker tạo root đáng tin.
3. **“`CertStore` là truststore.”** Sai: `CertStore` là nguồn candidate certificates/CRLs; trust anchors là policy độc lập.
4. **“`X509CertSelector` trả `true` nghĩa là PKIX đã thành công.”** Sai: match không xác minh path, trust, validity, revocation toàn diện.
5. **“`PKIXParameters` và `PKIXBuilderParameters` là như nhau.”** Sai: builder parameters thêm target và path-length policy cho xây path; validator dùng path đã có.
6. **“CertPath có leaf, intermediate, root.”** Không mặc định: trust anchor được truyền riêng, path demo chỉ có leaf và intermediate.
7. **“Giảm `setMaxPathLength` để giảm số certificate tùy ý.”** Sai: nó đếm **intermediate CA không self-issued**, không chỉ đơn giản đếm mọi cert.
8. **“Chỉ cần `setRevocationEnabled(true)` là OCSP/CRL luôn hoạt động tốt.”** Sai: phải cấu hình cơ chế/sources và failure policy.
9. **“Tắt revocation vì không có mạng thì production an toàn.”** Sai nếu không có quyết định bảo mật tương ứng; ví dụ tắt chỉ phục vụ lab.
10. **“Chứng thư do trusted CA ký chắc chắn thuộc hostname tôi định gọi.”** Sai: cần endpoint identity/SAN verification.
11. **“Mọi certificate có subject CN giống nhau đều cùng chủ thể.”** Sai: subject có thể do nhiều CA/attacker tạo; cần trust và policy.
12. **“Certificate root tự ký có thể validate bằng public key của chính nó thì đã tin.”** Sai: sự kiện self-signature đúng không nói gì về nguồn gốc root.
13. **“Vì path builder thành công nên user đã có quyền gọi API.”** Sai: quyền ứng dụng cần ánh xạ principal và authorization.
14. **“Bài lab chứng minh provider PKIX chạy trên mọi JDK/HSM.”** Sai: phải kiểm thử trên provider/runtime/chính sách và cấu hình CA/CRL/OCSP thật.

## 11. Bài tập thực hành

1. **Kiểm tra target:** bỏ `setCertificate(leaf)` và chỉ dùng subject + EKU + basic constraints. Điều gì xảy ra nếu `CertStore` có hai leaf cùng subject/EKU? Bạn phải bổ sung constraint nào hoặc chọn xác thực danh tính bằng cách nào?
2. **Không có intermediate:** loại `lab-intermediate.pem` khỏi collection `CertStore`. Với không có nguồn issuer khác, builder trả gì? Phân biệt lỗi thiếu issuer với root không tin.
3. **Sai trust anchor:** thay root được trust thành `lab-untrusted.pem`; chạy code và giải thích vì sao chữ ký trên leaf của intermediate vẫn đúng mà builder thất bại.
4. **Giới hạn path length:** đổi `setMaxPathLength(1)` thành `setMaxPathLength(0)`; path leaf→intermediate→root có được phép không? Nếu bạn có leaf ký trực tiếp bởi root thì kết quả khác thế nào?
5. **Certificate validity:** in `getNotBefore()/getNotAfter()` của leaf, dùng `setDate(...)` trong một bài test với thời điểm vượt NotAfter, kiểm chứng trạng thái path. Không thao tác đồng hồ máy production để tạo “bằng chứng” hết hạn.
6. **EKU:** đổi selector từ OID serverAuth sang OID clientAuth `1.3.6.1.5.5.7.3.2`; vì sao target leaf lab không còn khớp?
7. **Subject vs SAN:** xây path thành công cho `service.example.test`, sau đó giả sử HTTP client gọi `api.example.test`. PKIX builder có tự trả lỗi hostname mismatch không? Bạn cấu hình endpoint identification ở tầng nào?
8. **Truststore:** thiết kế một PKCS12 riêng chỉ chứa `TrustedCertificateEntry` cho root, đọc bằng `KeyStore` rồi tạo `new PKIXParameters(trustStore)`. Vì sao đưa private-key keystore do peer gửi vào constructor là sai?
9. **Revocation:** phác thảo quy trình CRL/OCSP provider được cấu hình cho hệ thống thật; chọn hard-fail hoặc soft-fail theo chính sách, và mô tả kết quả mong muốn khi responder không phản hồi.
10. **Điều tra lỗi:** một container Java gặp `CertPathBuilderException`, còn laptop xây path thành công. Liệt kê nguyên nhân khả dĩ liên quan truststore, certificates/candidates, JDK/provider, clock, revocation/network và hostname verification, không vội tắt PKIX.
11. **Ứng dụng mTLS:** giải thích riêng ba việc: validate client certificate path; ánh xạ certificate sang identity; quyết định identity có được gọi một endpoint nhạy cảm không.
12. **Chứng thư CA:** vì sao intermediate `pathLen:0` vẫn được ký leaf nhưng không được tạo một intermediate CA cấp dưới mới theo policy? Phân biệt extension `pathLenConstraint` với `setMaxPathLength`.

**Tiêu chí hoàn thành:** bạn chỉ ra được **trust anchor đến từ đâu**, leaf được chọn bằng những ràng buộc gì, intermediate nằm ở `CertStore` nào, builder giới hạn path thế nào, validator dùng chính sách gì, revocation/hostname được kiểm ra sao và vì sao **một path được xây dựng đúng không đồng nghĩa mọi mục tiêu bảo mật của ứng dụng đều được đáp ứng**.

## Tài liệu tham khảo chính thức

- [Java SE 21 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXParameters.html): cấu hình trust anchors, validation date, revocation, policies, CertStore.
- [Java SE 21 — `PKIXBuilderParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXBuilderParameters.html): selector, giới hạn intermediate CA, constructor từ truststore/anchors.
- [Java SE 21 — `X509CertSelector`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CertSelector.html): subject/issuer/EKU/basic constraints/key usage/SAN selectors.
- [Java SE 21 — `TrustAnchor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/TrustAnchor.html): trusted CA và name constraints.
- [Java SE 21 — `CertStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertStore.html): collection certificates/CRLs; không đồng nghĩa truststore.
- [Java SE 21 — `CertPathBuilder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathBuilder.html), [`CertPathValidator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html): xây và kiểm path.
- [Java SE 21 — `CertificateFactory`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertificateFactory.html): parse PEM/DER X.509.
- [Java SE 21 — `PKIXRevocationChecker`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXRevocationChecker.html): hỗ trợ revocation checking theo provider.
- [JDK 21 — `keytool`](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html): `-genkeypair -signer`, export certificate, PKCS12, extensions.
- [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280): X.509 PKI certificate and CRL profile, certificate path validation.
- [Java 21 JSSE Reference Guide](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, trust managers và endpoint identity.
