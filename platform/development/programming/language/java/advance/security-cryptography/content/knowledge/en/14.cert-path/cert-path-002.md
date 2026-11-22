# 14.2 Phân biệt xây đường dẫn bằng CertPathBuilder với kiểm tra bằng CertPathValidator

Trong Java PKI, một certificate X.509 của máy chủ có thể được cấp bởi intermediate CA, rồi intermediate được cấp bởi root CA mà ứng dụng tin cậy. Để quyết định có thể **tin vào khóa công khai của certificate đích** hay không, ứng dụng cần một **certification path** phù hợp và phải kiểm tra path đó theo chính sách PKIX. Java phân biệt hai nhiệm vụ:

- **`CertPathBuilder` — xây đường dẫn:** từ **certificate đích**, tập **trust anchors**, tiêu chí chọn và nguồn **certificate ứng viên**, engine **tìm một đường dẫn hợp lệ** dẫn về trust anchor. Nó vừa **tìm kiếm** vừa **kiểm tra** để trả một đường dẫn đã được xác minh theo các tham số được cung cấp.
- **`CertPathValidator` — kiểm tra đường dẫn:** nhận **một đường dẫn đã được cung cấp** và tập trust anchors/chính sách, rồi **đánh giá đúng đường dẫn đó**. Nó không có nhiệm vụ tìm một chuỗi mới thay thế nếu chuỗi đưa vào thiếu intermediate, sai thứ tự hay không hợp lệ.

Đây là bài **14.2** thuộc phần **14. Đường dẫn tin cậy** của Java Advanced Security & Cryptography. Trọng tâm là hiểu đầu vào/đầu ra của hai engine JCA, vai trò của `CertStore`, `PKIXBuilderParameters`, `PKIXParameters`, `TrustAnchor`; chạy một thí nghiệm Java 17+ có root/intermediate/leaf thật do `keytool` sinh; và nhận diện đúng giới hạn PKIX so với xác thực hostname/TLS/revocation trong hệ thống sản xuất.

## 1. Một bảng để không nhầm hai engine

| Khía cạnh | `CertPathBuilder` | `CertPathValidator` |
| --- | --- | --- |
| Câu hỏi chính | “**Tìm được** một certification path hợp lệ từ mục tiêu đến trust anchor không?” | “**Certification path đã cho** có hợp lệ với trust anchors và policy không?” |
| Input chính | `CertSelector` chọn target, `TrustAnchor`, nguồn candidate (`CertStore`), `PKIXBuilderParameters` | Một `CertPath` **đã có**, `TrustAnchor`, `PKIXParameters` |
| Có cần sẵn toàn bộ chain? | **Không nhất thiết**; cần đủ candidate/intermediate có thể tra cứu để nối chain | **Có**: phải cung cấp path theo thứ tự và đủ certificate, ngoại trừ trust anchor |
| Có tìm kiếm nhiều khả năng/cross-sign không? | Có thể tìm các ứng viên/path theo implementation và policy | Không tự tìm các path thay thế; chỉ xử lý đường dẫn đã truyền |
| Có kiểm tra chữ ký/thời hạn/ràng buộc PKIX? | **Có**; đường dẫn trả về đã được xác minh theo các tham số xây dựng | **Có**; đây là nhiệm vụ chính |
| Parameters | `PKIXBuilderParameters` (extends `PKIXParameters`) | `PKIXParameters` |
| Kết quả PKIX | `PKIXCertPathBuilderResult` có `CertPath`, `TrustAnchor`, public key và policy tree | `PKIXCertPathValidatorResult` có `TrustAnchor`, public key và policy tree; **không** trả một `CertPath` mới |
| Lỗi thông dụng | `CertPathBuilderException` khi không tìm ra đường dẫn được chấp thuận | `CertPathValidatorException` khi đường dẫn được đưa vào không đạt điều kiện |
| Dùng trong tình huống | Chỉ có leaf và một kho intermediate/CA ứng viên; chain chưa đủ hoặc có nhiều khả năng nối | Đã nhận/có một chain cố định cần kiểm tra theo trust policy |
| Bảo mật quan trọng | Candidate store **không phải truststore**; một candidate đẹp chưa đủ tin cậy | Certificate path đúng về cú pháp vẫn có thể bị từ chối vì trust/policy/thời gian |

**Điểm dễ trả lời sai:** `CertPathBuilder.build(...)` **không chỉ “ghép cho đủ các chứng chỉ”**. Với thuật toán `"PKIX"`, engine tìm **một path đã được validate** theo chính sách PKIX; `PKIXCertPathBuilderResult.getCertPath()` chứa một đường dẫn đã qua kiểm tra. Có thể gọi `CertPathValidator` sau đó nếu cần kiểm tra lại ở **thời điểm/chính sách khác**, hoặc để minh họa, nhưng không phải cứ build thành công mới bắt buộc validate thêm lần nữa với y hệt parameters.

## 2. Certification path, trust anchor và certificate ứng viên

Xét topology đơn giản:

```text
                         ROOT CA
             CN=Example Root CA
             [self-signed trong lab]
             [TRUST ANCHOR do app cấu hình]
                        |
                        | ký certificate
                        v
                     ISSUING CA
              CN=Example Issuing CA
              [intermediate certificate]
              [CA=true; keyCertSign]
                        |
                        | ký certificate
                        v
                   END ENTITY / LEAF
             CN=service.example.test
             [SAN: service.example.test]
             [CA=false; serverAuth]
```

Người kiểm tra bắt đầu từ **leaf certificate** và muốn truy vết một chuỗi chữ ký/issuer phù hợp về **root CA đã được chấp thuận**. Không phải root CA nào tồn tại trong Internet đều tự trở thành trust anchor: danh sách root được chấp thuận đến từ **truststore hoặc chính sách của ứng dụng**.

### 2.1 Trong Java, CertPath gồm những gì?

Với hướng lưu trữ Java PKIX thông dụng, danh sách certificate của path được biểu diễn từ **mục tiêu trở lên**:

```text
CertPath.getCertificates():
    [0] leaf certificate                (target)
    [1] intermediate CA certificate
    [không chứa root trust anchor]

PKIXCertPathBuilderResult.getTrustAnchor():
    root CA được tin cậy
```

Đó là lý do trong ví dụ thực tế, `getCertPath().getCertificates().size()` bằng **2** dù topology có **3 certificate**. **Trust anchor thường nằm riêng**, không được thêm vào danh sách certificate của `CertPath` trả về bởi PKIX builder.

`CertPath` là một **đối tượng bất biến** chứa thứ tự certificate và loại path, có thể tạo từ `CertificateFactory.generateCertPath(...)`, được nhận từ `CertPathBuilder`, hoặc đọc một dạng encoding phù hợp. Có một đối tượng `CertPath` **không tự khẳng định nó hợp lệ**: một danh sách certificate có thể được tạo ra dù chữ ký, thời hạn hoặc trust anchors không đúng.

### 2.2 TrustAnchor là quyết định tin cậy độc lập

`java.security.cert.TrustAnchor` mô tả CA được chấp thuận làm điểm bắt đầu tin cậy trong PKIX. Nó có thể được tạo từ `X509Certificate` được tin hoặc tên CA + public key (theo API). Trong lab này ta dùng:

```java
// Đoạn mã trong phương thức đã có root là X509Certificate.
TrustAnchor anchor = new TrustAnchor(root, null);
Set<TrustAnchor> anchors = Set.of(anchor);
```

Đoạn trên là **minh họa không độc lập**, không phải một full Java class. Root certificate trong lab được ứng dụng **chủ động tin**; chỉ bởi `root` tự ký không khiến nó trở thành an toàn trong production. Trước khi thêm một root CA/CA riêng vào truststore, phải kiểm chứng **nguồn, fingerprint, phạm vi tin cậy và quyền quản trị**.

Trust anchor nằm ngoài path được validate theo cách thông thường; đừng suy ra toàn bộ thuộc tính của certificate gốc được kiểm tra giống leaf/intermediate (ví dụ các ràng buộc đối với anchor phải được quản lý ở **trust policy**). Đổi trust anchor có thể đổi hoàn toàn kết quả của cùng một path.

### 2.3 CertStore là nguồn ứng viên, không phải điểm tin cậy

`java.security.cert.CertStore` là nguồn tìm certificate và CRL. Nó có thể lấy từ một collection trong RAM, directory LDAP hay backend khác tùy provider.

```text
Trusted CA / TrustAnchor
     |
     +-- từ truststore/chính sách -> cơ sở để chấp thuận path
     |
CertStore (Collection/LDAP/...):
     +-- leaf certificates
     +-- intermediate CA certificates
     +-- CRLs ứng viên
     |
     +-- cung cấp dữ liệu cho builder/PKIX, CHƯA tạo trust
```

Một intermediate được đưa vào `CertStore` chỉ giúp builder **tìm được mắt xích**, không tự biến intermediate thành trusted root. Một chứng chỉ do attacker cung cấp có thể nằm trong candidate pool; chính builder/validator phải kiểm tra chuỗi dẫn tới **trust anchor được cấu hình trước** và các điều kiện bảo mật.

**Không nhập bừa intermediate thiếu vào truststore làm anchor** chỉ vì builder báo lỗi. Hãy tìm intermediate từ nguồn phù hợp, xác nhận issuer/chain và cung cấp nó làm **candidate**; trust anchor phải là quyết định của chính sách.

## 3. CertPathBuilder: chọn target rồi tìm path hợp lệ

Các lớp liên quan:

```text
java.security.cert.CertPathBuilder
    getInstance("PKIX")
    build(CertPathParameters)
                |
                v
java.security.cert.PKIXBuilderParameters
    trustAnchors          (CA mà bên nhận thực sự tin)
    targetCertConstraints (CertSelector chọn mục tiêu)
    CertStores            (intermediate/CRL candidates)
    date, policies, revocation, checkers, constraints...
    maxPathLength          (giới hạn intermediate)
                |
                v
java.security.cert.PKIXCertPathBuilderResult
    getCertPath()     = path đã build VÀ validate
    getTrustAnchor()  = anchor được dùng
    getPublicKey()    = khóa công khai của target
    getPolicyTree()   = kết quả policy tree (có thể null)
```

### 3.1 Input tối thiểu

```java
// Đoạn mã minh họa (không độc lập):
// root và leaf là X509Certificate đã được parse;
Set<TrustAnchor> anchors =
        Set.of(new TrustAnchor(root, null));

X509CertSelector target = new X509CertSelector();
target.setCertificate(leaf);

CertStore source = CertStore.getInstance(
        "Collection",
        new CollectionCertStoreParameters(
                List.of(leaf, intermediate)));

PKIXBuilderParameters params =
        new PKIXBuilderParameters(anchors, target);
params.addCertStore(source);
params.setRevocationEnabled(false); // Chỉ trong lab này.

PKIXCertPathBuilderResult result =
        (PKIXCertPathBuilderResult)
                CertPathBuilder.getInstance("PKIX").build(params);
```

**Các điểm cần hiểu:**

1. **Target constraints** là tiêu chí cho certificate đích. `target.setCertificate(leaf)` chọn đúng một certificate cụ thể; với một hệ thống tìm nhiều ứng viên có thể dùng `setSubject`, `setKeyUsage`, `setExtendedKeyUsage` cùng bộ tiêu chí thích hợp.
2. **Trust anchors** xác định điểm chấp thuận cuối cùng, không rút ra từ tên file hay chỉ từ chứng chỉ tự ký bất kỳ.
3. **CertStore** cung cấp intermediate/certificates/CRLs ứng viên; **builder được phép tìm** trong những nguồn provider/policy hỗ trợ. Đừng kỳ vọng mọi provider luôn tự tải AIA qua Internet; cung cấp nguồn được kiểm soát và đo trên JDK thật.
4. **PKIXBuilderParameters extends PKIXParameters**: ngoài các tham số validation còn thêm **target constraints và giới hạn độ dài path**.
5. **Revocation** trong code được tắt **chỉ để demo hoạt động offline**, không có CA phát CRL hay OCSP thật. Production phải có **chính sách revocation rõ ràng** thay vì copy `false`.
6. Builder có thể kiểm tra nhiều candidates/chains; đường dẫn cuối cùng được **validate**, không chỉ xếp nối theo `issuerDN == subjectDN`.

### 3.2 setMaxPathLength có nghĩa gì?

`PKIXBuilderParameters.setMaxPathLength(int)` giới hạn **số intermediate certificate không phải self-issued** trong path theo contract API. Với topology leaf → một intermediate → root anchor, `maxPathLength=1` là đủ; `maxPathLength=0` chỉ cho path không có intermediate tương ứng.

- Giá trị **`-1`**: không giới hạn bởi thiết lập này.
- Giá trị **`0`**: chỉ cho path có **một certificate** trước anchor.
- Nếu không đặt, **mặc định trong API là 5** theo tài liệu Java 21.
- Đây **không** phải giới hạn tổng số certificate bao gồm root anchor và leaf. Có các quy tắc riêng về `BasicConstraints.pathLenConstraint` do CA ký; policy thực tế có thể chặt hơn giới hạn builder.

Ví dụ:

```java
// Chỉ minh họa, trong phương thức có PKIXBuilderParameters params.
params.setMaxPathLength(1); // Một intermediate trong bài lab.
```

Giới hạn giúp tránh thuật toán dò tìm quá sâu và các path ngoài chính sách, **nhưng không** thay thế validation chữ ký, usage, algorithm constraints hay trust anchors.

## 4. CertPathValidator: kiểm tra một CertPath đã có

Validator nhận một **certification path xác định**:

```text
     CertPath
  [leaf, intermediate]  --------+
                                |
          PKIXParameters -------+------> CertPathValidator("PKIX")
          - trust anchors                      |
          - date, policies                     v
          - revocation                    Validate signatures,
          - checkers                      basicConstraints,
          - cert constraints             validity, policies...
                                                |
                                       +--------+---------+
                                       |                  |
                                     PASS                 FAIL
                                       |                  |
                         PKIXCertPathValidatorResult  CertPathValidatorException
                           trustAnchor, publicKey,         index/reason/cause
                           policyTree
```

### 4.1 Tạo một CertPath bằng tay

Khi **đã có chain theo đúng thứ tự**, có thể dựng `CertPath` qua `CertificateFactory`:

```java
// Đoạn mã minh họa bên trong phương thức có đủ imports/throws.
// root không nằm trong danh sách path vì nó là trust anchor.
CertificateFactory factory = CertificateFactory.getInstance("X.509");
CertPath givenPath =
        factory.generateCertPath(List.of(leaf, intermediate));

PKIXParameters params = new PKIXParameters(
        Set.of(new TrustAnchor(root, null)));
params.setRevocationEnabled(false); // CHỈ lab không CRL/OCSP.

PKIXCertPathValidatorResult checked =
        (PKIXCertPathValidatorResult)
                CertPathValidator.getInstance("PKIX")
                        .validate(givenPath, params);
```

Khác builder: validator **không lấy `CertStore` để tự sửa lại thứ tự hay bổ sung intermediate bị thiếu**. Nó có thể dùng `CertStore` khi cần **thông tin phục vụ validation**, đặc biệt CRL/revocation, nhưng điều đó **không biến** validator thành path discovery engine.

**Thứ tự quan trọng:** `CertificateFactory.generateCertPath(List)` với X.509 PKIX thường dùng thứ tự **leaf → intermediate CA(s)** theo API Java. Đừng thêm root trust anchor vào cuối danh sách chỉ để làm “đủ ba chứng chỉ”: anchor được truyền qua parameters riêng.

### 4.2 PKIXParameters mô tả chính sách xác minh

Những thuộc tính quan trọng của `PKIXParameters`:

| Thành phần | API tiêu biểu | Tác động |
| --- | --- | --- |
| Trust anchors | `new PKIXParameters(Set<TrustAnchor>)` hoặc từ trusted certificate entries của `KeyStore` | Định nghĩa CA/key nào là điểm tin cậy được chấp thuận |
| Ngày kiểm tra | `setDate(Date)` | Xác định thời điểm dùng để kiểm tra validity; không tự làm clock-stamping |
| Revocation | `setRevocationEnabled(boolean)` | Bật/tắt bước kiểm tra thu hồi theo khả năng/checker/policy |
| Certificate/CRL sources | `addCertStore(CertStore)` | Cung cấp nguồn phục vụ revocation và các tác vụ kiểm tra tương ứng |
| Policy OIDs | `setInitialPolicies(Set<String>)` | Ràng buộc certificate policies được chấp nhận theo mô hình PKIX |
| Custom checkers | `addCertPathChecker(PKIXCertPathChecker)` | Kiểm tra thêm theo extension/logic policy |
| Xác định policy | `setExplicitPolicyRequired(...)`, `setPolicyMappingInhibited(...)`... | Điều khiển xử lý policy tree |
| Danh sách trusted CA | `getTrustAnchors()` | Đối chiếu quy tắc tin cậy đã được cấu hình, không suy từ candidate pool |

Trong thực tế còn có **thuật toán bị cấm**, constraints của JDK/provider, certificate extensions, name constraints, basic constraints và key usages; định nghĩa policy cụ thể tùy môi trường. Không cố tự liệt kê một vài if-statement là đã thay được PKIX validator.

**`CertPathValidator.validate` thành công không có nghĩa mọi quy tắc TLS đã hoàn tất.** Xác thực hostname/SAN cho HTTPS, mục đích sử dụng server/client, danh tính ứng dụng, pinning và trạng thái/replay thuộc layer tiêu thụ certificate/JSSE và policy tương ứng. Phải xác minh phần đó riêng, không chỉ dựa vào thành công của API PKIX.

## 5. Các kiểu kết quả và ngoại lệ: khác nhau về hợp đồng

| API | Thành công trả về | Thất bại chính |
| --- | --- | --- |
| `CertPathBuilder.getInstance("PKIX")` | Một engine builder | `NoSuchAlgorithmException` |
| `CertPathBuilder.build(PKIXBuilderParameters)` | `CertPathBuilderResult`, thường là `PKIXCertPathBuilderResult` | `CertPathBuilderException`; configuration có thể gây lỗi tham số |
| `CertPathValidator.getInstance("PKIX")` | Một engine validator | `NoSuchAlgorithmException` |
| `CertPathValidator.validate(certPath, PKIXParameters)` | `CertPathValidatorResult`, thường là `PKIXCertPathValidatorResult` | `CertPathValidatorException`, `InvalidAlgorithmParameterException` |
| `CertificateFactory.generateCertPath(List)` | Đối tượng `CertPath` từ danh sách certificate | `CertificateException` nếu input không hợp lệ theo contract |
| `CertStore.getCertificates(selector)` | Một collection ứng viên | `CertStoreException` khi nguồn tra cứu lỗi |
| `PKIXBuilderParameters(trustAnchors, target)` | Parameters phù hợp cho builder | `InvalidAlgorithmParameterException` nếu trust anchors không có/không hợp lệ theo constructor |

**`CertPathBuilderException` không có nghĩa chắc chắn “không tìm thấy intermediate”.** Nó có thể do không có path hợp lệ tới anchor, lỗi candidate source, certificate constraints, signature, thời hạn, thuật toán bị chặn hoặc revocation. Ngược lại, **`CertPathValidatorException` không tự nói lỗi do chữ ký**; xem `getReason()`, `getIndex()`, `getCause()`, thông tin policy và logging phù hợp.

Với `CertPathValidatorException.getIndex()`, index chỉ vào certificate gây lỗi **nếu provider có thông tin đó**; có thể là **`-1`** khi không xác định. Không tự diễn giải index -1 là “root certificate lỗi” hay “toàn bộ chain an toàn”.

## 6. Lab chạy được: root CA → intermediate CA → leaf

Ta tạo **ba X.509 certificate thật trong môi trường test tạm** để builder và validator làm việc với chữ ký/extension, không dùng “pseudo certificates”. Công cụ `keytool` có sẵn cùng JDK, không cần dịch vụ certificate authority thực hay kết nối Internet.

**Chỉ chạy trong thư mục lab trống**, không chứa keystore thật. Password `changeit` và tên `service.example.test` chỉ dành cho thử nghiệm; các private keys được keytool tạo trong file `.p12`, vì vậy không đưa các file này vào Git, artifact hay môi trường production. Lệnh dưới dùng một dòng mỗi thao tác, có thể nhập lần lượt trong shell, gồm PowerShell với `keytool.exe`.

### 6.1 Tạo root CA tự ký cho lab

```bash
keytool -genkeypair -alias root -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 3650 -dname "CN=Example Root CA,O=Lab,C=VN" -ext "BC:critical=ca:true,pathlen:1" -ext "KU:critical=keyCertSign,cRLSign" -keystore root.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -exportcert -alias root -rfc -file root.pem -keystore root.p12 -storetype PKCS12 -storepass changeit
```

- Root CA dùng keypair RSA-2048 cho **lab**; `BasicConstraints CA=true` và `keyCertSign` mô tả vai trò CA.
- Tệp `root.pem` chứa **certificate công khai**, còn `root.p12` giữ private key của root. **Chỉ `root.pem`** sẽ được ứng dụng Java dùng làm trust anchor.
- Trong production không tự phát hành root rồi đương nhiên chấp thuận: phải quản lý trust distribution, fingerprint, private key bảo vệ và lifecycle theo chính sách CA.

### 6.2 Sinh intermediate CA rồi để root ký

```bash
keytool -genkeypair -alias intermediate -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 800 -dname "CN=Example Issuing CA,O=Lab,C=VN" -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -keystore intermediate.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -certreq -alias intermediate -file intermediate.csr -keystore intermediate.p12 -storetype PKCS12 -storepass changeit

keytool -gencert -alias root -infile intermediate.csr -outfile intermediate.pem -rfc -validity 730 -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -keystore root.p12 -storetype PKCS12 -storepass changeit

keytool -importcert -alias root -file root.pem -keystore intermediate.p12 -storetype PKCS12 -storepass changeit -noprompt

keytool -importcert -alias intermediate -file intermediate.pem -keystore intermediate.p12 -storetype PKCS12 -storepass changeit -noprompt
```

Các lệnh trên tạo **CSR**, dùng **private root CA** ký intermediate, sau đó nạp root và certificate đã được cấp vào identity keystore của intermediate. `intermediate.pem` là certificate ứng viên mà builder sẽ cần. `pathlen:0` trên intermediate giới hạn số CA phụ thuộc bên dưới (ngoại trừ các trường hợp self-issued theo chuẩn); nó vẫn được phép cấp leaf end-entity certificate.

**Phân biệt:** `keytool -importcert` vào `intermediate.p12` để hoàn thành identity certificate chain của intermediate **không** có nghĩa application bên nhận phải đặt intermediate thành trust anchor. Trong Java lab ta chỉ đặt **root** trong `Set<TrustAnchor>`.

### 6.3 Sinh leaf certificate do intermediate ký

```bash
keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -validity 300 -dname "CN=service.example.test,O=Lab,C=VN" -ext "SAN=dns:service.example.test" -keystore leaf.p12 -storetype PKCS12 -storepass changeit -keypass changeit -noprompt

keytool -certreq -alias leaf -file leaf.csr -keystore leaf.p12 -storetype PKCS12 -storepass changeit

keytool -gencert -alias intermediate -infile leaf.csr -outfile leaf.pem -rfc -validity 200 -ext "BC=ca:false" -ext "KU:critical=digitalSignature,keyEncipherment" -ext "EKU=serverAuth" -ext "SAN=dns:service.example.test" -keystore intermediate.p12 -storetype PKCS12 -storepass changeit
```

Leaf có `CA=false`, `serverAuth` và SAN của domain lab. File `leaf.pem` là certificate cần được kiểm tra. Để test API `CertPathBuilder`, ứng dụng Java chỉ cần **ba file PEM certificate**; chương trình không cần truy cập private keys trong các `.p12` vừa tạo.

**Trước khi dùng thật:** certificate self-issued/self-signed và password trong demo hoàn toàn không dùng làm trust configuration production. Nếu mất các file lab, có thể sinh lại và chạy lại. Đừng copy root certificate này vào `cacerts` chung của JDK hoặc truststore production.

## 7. Java 17+: xây, kiểm tra và minh họa hai kiểu lỗi

Lưu chương trình hoàn chỉnh sau thành **`CertPathBuilderValidatorDemo.java`** trong **cùng thư mục** có `root.pem`, `intermediate.pem`, `leaf.pem`.

```java
import java.io.*;
import java.nio.file.*;
import java.security.*;
import java.security.cert.*;
import java.time.*;
import java.util.*;

public final class CertPathBuilderValidatorDemo {
    static X509Certificate cert(String path) throws Exception {
        CertificateFactory cf = CertificateFactory.getInstance("X.509");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            return (X509Certificate) cf.generateCertificate(in);
        }
    }

    public static void main(String[] args) throws Exception {
        X509Certificate root = cert("root.pem");
        X509Certificate intermediate = cert("intermediate.pem");
        X509Certificate leaf = cert("leaf.pem");

        // Trust anchor: quyết định tin root CA của lab.
        Set<TrustAnchor> anchors =
                Set.of(new TrustAnchor(root, null));

        // Chỉ rõ certificate mục tiêu cần xây đường dẫn.
        X509CertSelector target = new X509CertSelector();
        target.setCertificate(leaf);

        // Intermediate chỉ là candidate, không phải trust anchor.
        CertStore repository = CertStore.getInstance(
                "Collection",
                new CollectionCertStoreParameters(
                        List.of(leaf, intermediate)));

        PKIXBuilderParameters bp =
                new PKIXBuilderParameters(anchors, target);
        bp.setRevocationEnabled(false); // Chỉ lab, không CRL/OCSP.
        bp.addCertStore(repository);

        CertPathBuilder builder =
                CertPathBuilder.getInstance("PKIX");
        PKIXCertPathBuilderResult built =
                (PKIXCertPathBuilderResult) builder.build(bp);

        System.out.println("Builder path certificates: "
                + built.getCertPath().getCertificates().size());
        System.out.println("Builder trusted root: "
                + built.getTrustAnchor()
                        .getTrustedCert()
                        .getSubjectX500Principal()
                        .getName()
                        .contains("Example Root CA"));

        // Xác minh lại cùng path đã được build, minh họa API riêng.
        PKIXParameters vp = new PKIXParameters(anchors);
        vp.setRevocationEnabled(false); // Chỉ lab.
        CertPathValidator validator =
                CertPathValidator.getInstance("PKIX");
        PKIXCertPathValidatorResult validated =
                (PKIXCertPathValidatorResult)
                        validator.validate(
                                built.getCertPath(), vp);

        System.out.println("Validator public key matches leaf: "
                + validated.getPublicKey()
                        .equals(leaf.getPublicKey()));

        // Builder chỉ thấy leaf; không có intermediate trong kho.
        PKIXBuilderParameters missing =
                new PKIXBuilderParameters(anchors, target);
        missing.setRevocationEnabled(false);
        missing.addCertStore(CertStore.getInstance(
                "Collection",
                new CollectionCertStoreParameters(
                        List.of(leaf))));
        boolean cannotBuild = false;
        try {
            builder.build(missing);
        } catch (CertPathBuilderException expected) {
            cannotBuild = true;
        }
        System.out.println("Build without intermediate fails: "
                + cannotBuild);

        // Validator nhận path hoàn chỉnh nhưng kiểm tại ngày
        // rất xa tương lai, sau hạn của leaf/intermediate.
        PKIXParameters future = new PKIXParameters(anchors);
        future.setRevocationEnabled(false);
        future.setDate(Date.from(
                Instant.now().plus(
                        4000, java.time.temporal.ChronoUnit.DAYS)));

        boolean expired = false;
        try {
            validator.validate(built.getCertPath(), future);
        } catch (CertPathValidatorException expected) {
            expired = true;
        }
        System.out.println("Validate at future date fails: "
                + expired);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 CertPathBuilderValidatorDemo.java
java CertPathBuilderValidatorDemo
```

Stdout được kiểm chứng với JDK có thuật toán PKIX tương thích, sau khi tạo file từ **ba bước keytool** trên:

```text
Builder path certificates: 2
Builder trusted root: true
Validator public key matches leaf: true
Build without intermediate fails: true
Validate at future date fails: true
```

### 7.1 Giải thích các kết quả

**Dòng 1 — Builder path certificates = 2**

Đường dẫn gồm **leaf, intermediate**, không có root. `PKIXCertPathBuilderResult.getTrustAnchor()` cung cấp root được chọn **riêng**. Nếu chỉ đếm danh sách path rồi thấy không có root, đó **không phải một lỗi**.

**Dòng 2 — Builder trusted root = true**

Builder nối được đường dẫn đến một trust anchor do ta cung cấp trong `anchors`. `contains("Example Root CA")` chỉ là **cách in bool minh họa** dựa trên tên cố định của certificate lab; trong production không chọn trust bằng cách kiểm tra substring trong DN.

**Dòng 3 — Validator public key matches leaf = true**

`CertPathValidator` kiểm tra **cùng path** dưới `PKIXParameters` của lab và trả `PKIXCertPathValidatorResult` với public key của target. Việc gọi lại validator ở đây là để học sự khác biệt API; builder **đã validate path** khi `build` trả thành công.

**Dòng 4 — Build without intermediate fails = true**

Khi `CertStore` chỉ chứa leaf, không có intermediate và lab không có nguồn khác được cấu hình, builder **không tìm được** path tới root. Đây là lỗi **thiếu certificate ứng viên để xây đường dẫn**. Nó không có nghĩa root thiếu trong tập trust anchors; root vẫn có mặt.

**Dòng 5 — Validate at future date fails = true**

Đường dẫn vừa xây là hợp lệ **hiện tại**, nhưng ở thời điểm cách 4000 ngày theo ví dụ sẽ vượt khỏi hiệu lực của leaf/intermediate; `CertPathValidator` từ chối đường dẫn đó. Cùng một danh sách certificates có thể có kết quả khác nếu **validation date, trust anchors hoặc chính sách** khác.

### 7.2 Điều lab cố ý chưa kiểm tra

- **Revocation:** các certificate lab không có dịch vụ CRL/OCSP; `setRevocationEnabled(false)` chỉ dùng để chạy offline. Production cần chính sách thực về kiểm tra thu hồi.
- **Hostname/SAN của TLS:** `CertPathValidator.validate` không tự biết ứng dụng đang gọi URL nào. Dù leaf có `SAN=dns:service.example.test`, đoạn Java **không so sánh với endpoint yêu cầu**.
- **Mức tin cậy bên ngoài:** chương trình **chủ động** chọn root lab làm anchor. Nó không chứng minh certificate của một CA production được tổ chức chấp thuận.
- **Toàn bộ thuật toán/cipher suite TLS:** chứng chỉ có path PKIX hợp lệ chưa bảo đảm giao thức TLS handshake, host, ciphers, certificate usage và identity policy đều đúng.
- **Những path thay thế:** lab có đúng một intermediate. Production có thể có cross-signing/nhiều CA, khiến builder phải tìm/đánh giá nhiều lựa chọn.
- **Key usage tùy nghiệp vụ:** `serverAuth` và `digitalSignature` nằm trong certificate lab, nhưng ứng dụng vẫn cần ràng buộc mục đích dùng certificate đúng giao thức/JSSE.

## 8. Builder có thể giải bài toán mà Validator không tự giải

Một hệ thống thực tế chỉ nhận **leaf certificate** từ peer; intermediate có thể nằm trong kho của ứng dụng, trong certificate chain được gửi kèm hoặc một nguồn tra cứu được cấu hình phù hợp.

```text
Dữ liệu sẵn có:
  leaf
  candidates = {intermediate A, intermediate B, cross-signed CA C, ...}
  anchors = {root X, root Y}

Builder:
  chọn target leaf
  tìm issuer candidates
  kiểm tra chữ ký/validity/constraints theo cấu hình
  nối các candidate có thể dẫn về X hoặc Y
  trả một validated CertPath + TrustAnchor

Validator:
  nhận CertPath [leaf, intermediate A] đã có sẵn
  kiểm tra CHÍNH path đó dưới trust anchors/policy
  không tự đổi intermediate A thành B vì A thất bại
```

**Trường hợp cross-signing:** cùng một subject/public key CA có thể xuất hiện dưới nhiều certificate do issuer khác nhau ký. Có thể có nhiều con đường tới các root khác nhau; builder có thể tìm một con đường theo candidates và policy của provider. Nếu bạn đã nhận một certificate path cụ thể, validator không tự “đi đường vòng” bằng một cross-signed certificate khác. **Đừng chỉ dựa vào subject DN** để coi hai certificate là tương đương; chữ ký, key, extensions, issuance và policy đều quan trọng.

### 8.1 Khi nào xây đường dẫn là cần thiết?

- Ứng dụng có leaf certificate nhưng **không nhận đủ intermediate chain** và có nguồn candidate đáng tin cậy để tìm.
- Một certificate có thể được cấp qua **nhiều chain** đến nhiều root, cần tìm path phù hợp trust policy.
- Một hệ thống PKI nội bộ lưu certificate/CRL trong directory/collection và cần xây path từ end-entity đến root.
- Một công cụ kiểm chứng tài liệu/chữ ký phải tìm issuer path cho certificate của người ký.

Dù vậy, **builder không đảm bảo nguồn tải intermediate luôn có sẵn hoặc an toàn**. Nếu dùng AIA hoặc LDAP/network, cần hạn chế endpoint, timeout, số lượng/trọng lượng dữ liệu, xử lý SSRF và cache, và không coi content nhận về là trusted chỉ vì được tải tự động. Tùy JDK/provider, tự động truy vấn AIA có thể cần option riêng hoặc không được hỗ trợ; **không mặc định mọi build sẽ tự tải Internet**.

### 8.2 Khi nào chỉ cần Validator?

- Ứng dụng đã có một chain theo đúng thứ tự từ nguồn được xác định, muốn đánh giá nó theo một bộ `PKIXParameters`.
- Một ứng dụng muốn **kiểm chứng lại** path ở **ngày khác** (ví dụ thời gian ký và bằng chứng thời gian theo policy phù hợp) hoặc bộ trust anchors khác.
- Kiểm thử một đường dẫn cố định với certificate hết hạn, CA không phù hợp, policy không thỏa hoặc chữ ký sai.
- Công cụ quản trị/diagnostics cần phân biệt lỗi chính xác của **đường dẫn được cho trước**.

Nếu thiếu intermediate, không “sửa” bằng cách thêm root vào `CertPath`. Hãy cung cấp candidate đúng cho builder hoặc bổ sung **intermediate thực sự** vào path từ nguồn đã xác minh; trust anchor vẫn độc lập.

## 9. Kiểm tra path PKIX làm gì?

PKIX validation không đơn thuần là `cert.verify(issuer.getPublicKey())` cho từng cặp. Một đường dẫn được chấp nhận phải đáp ứng các kiểm tra liên quan **chữ ký và liên kết issuer**, **hiệu lực thời gian**, **CA basic constraints**, **key usage**, **name constraints**, **certificate policies**, **thuật toán/độ dài key** và các yêu cầu khác theo chuẩn, API, provider/policy.

Một mental model:

```text
CertPath [leaf, intermediate, ...] + TrustAnchor root
                   |
            1. Chain order/issuer
                   |
            2. Verify signatures
                   |
            3. Check dates (validationDate)
                   |
            4. Check BasicConstraints + keyCertSign
                   |
            5. Process name constraints / policy constraints
                   |
            6. Algorithm policy / critical extensions
                   |
            7. Revocation checking theo cấu hình
                   |
                PASS / FAIL
```

Thứ tự thật của thuật toán PKIX phức tạp hơn sơ đồ (xem RFC 5280, Section 6); **không được dùng sơ đồ này như một implementation spec** để tự viết validator. Một provider có thể thực thi các chính sách bổ sung như `jdk.certpath.disabledAlgorithms` ở JDK phù hợp.

### 9.1 Không nhầm trust anchors với certificate candidates

| Thuộc tính | TrustAnchor | CertStore candidate |
| --- | --- | --- |
| Do ai chấp thuận? | **Operator/ứng dụng** theo trust policy | Có thể được lấy từ mạng/file/peer, không đáng tin mặc định |
| Dùng để làm gì? | Là **điểm xuất phát tin cậy** khi đánh giá chain | Nguồn certificate/CRL giúp tìm/kiểm tra chain |
| Thêm vào API nào? | `PKIXParameters`/`PKIXBuilderParameters` | `PKIXParameters.addCertStore` và tham số builder |
| Thêm một phần tử có làm rộng trust không? | **Có thể**, nếu thêm anchor ngoài chính sách | **Không trực tiếp**; candidates vẫn phải được validate đến anchor |
| Hệ quả khi bị sửa trái phép | Có thể cho phép CA giả chấp thuận certificate giả | Có thể gây DoS, nhầm lựa chọn hoặc thử path khác; validation đúng vẫn cần trust anchors |

### 9.2 Path building không phải hostname verification

Một chain hợp lệ về chữ ký từ root chấp thuận có thể kết thúc ở certificate cho `service-a.example.test` trong khi client đang kết nối `service-b.example.test`. **Chỉ PKIX builder/validator không đủ để xác minh danh tính hostname của một HTTPS request**.

Khi làm TLS, dùng HTTP client/JSSE được cấu hình **endpoint identification** đúng API và chính sách, kiểm tra SAN, EKU/usage và tên endpoint theo giao thức. Đừng tự viết một trust manager chỉ gọi `CertPathValidator.validate` rồi tuyên bố HTTPS đã xác thực đầy đủ.

## 10. Revocation: cần thiết kế riêng, không để false trong production

Trong lab, ta gọi:

```java
params.setRevocationEnabled(false);
```

Điều này **tắt bước kiểm tra thu hồi** ở parameters, cần thiết cho demo offline không có CRL/OCSP. Trong sản phẩm thực:

- Chọn cơ chế CRL, OCSP hoặc checker tương ứng theo loại certificate/giao thức/policy.
- Quy định tính tươi của dữ liệu, thời gian, cache, timeout và cách xử lý khi nguồn revocation không khả dụng.
- Kiểm tra `PKIXRevocationChecker`/provider support nếu cần tùy chỉnh.
- Xác nhận nguồn CRL/OCSP được xác thực (CRL có chữ ký và issuer phù hợp; OCSP response theo chính sách).
- Phân biệt **không có phản hồi** với **certificate không bị thu hồi**; đừng đánh đồng cả hai khi chính sách đòi fail-closed.
- Test certificate bị revoke, certificate không có thông tin revocation, CRL expired và network timeout trên JDK/provider thật.

**Việc thêm `CertStore` có CRL không tự bảo đảm revocation được kiểm tra** nếu chính sách không bật/cấu hình tương ứng. Ngược lại, bật revocation mà không cung cấp dữ liệu/nguồn hoạt động có thể khiến path bị từ chối do không thể xác định trạng thái.

## 11. Các lỗi thường gặp và cách đọc đúng

| Dấu hiệu | Điểm xuất hiện | Chẩn đoán chính |
| --- | --- | --- |
| `CertPathBuilderException: unable to find valid certification path to requested target` | `builder.build` | Không có path đáp ứng **tập anchor, candidate và chính sách hiện tại**; kiểm tra intermediate, truststore, thuật toán, constraints, ngày, revocation |
| `CertPathValidatorException: validity check failed` | `validator.validate` | Certificate trong path ngoài thời gian hợp lệ tại `validationDate`; xem index/reason |
| `CertPathValidatorException: Path does not chain with any of the trust anchors` | `validator.validate` | Path được cho không nối được tới anchor; kiểm tra root/chain/order |
| `CertPathValidatorException: signature check failed` | `validator.validate` | Chữ ký issuer không hợp lệ, sai key, path bị thay hoặc chain không phù hợp |
| `CertPathValidatorException` với `INVALID_KEY_USAGE`/constraints | `validator.validate` | Intermediate thiếu `keyCertSign`, không được là CA, vi phạm constraints hoặc policy |
| `InvalidAlgorithmParameterException` | Constructor parameters hoặc validate | Không có trust anchor phù hợp, parameters sai hoặc không được provider chấp nhận |
| `CertificateException` | `CertificateFactory.generateCertificate`/`generateCertPath` | Input certificate/encoding bị hỏng hoặc không đúng format |
| `NoSuchAlgorithmException` | `getInstance("PKIX")` | JDK/provider không có engine `PKIX` |
| `CertStoreException` | `CertStore` lấy certificates/CRLs | Nguồn candidate hỏng, network/LDAP lỗi, selector/backend không tương thích |
| `SSLHandshakeException` có lỗi PKIX | TLS/JSSE | Có thể do builder/validator bên dưới; kiểm tra đúng truststore hiệu dụng **và** hostname/chain/policy |

**Đừng kết luận “thiếu root” từ mọi lỗi builder.** Trong lab, root vẫn được cấu hình, nhưng thiếu **intermediate** cũng làm builder thất bại. Ngược lại, có đủ intermediate mà root không được tin vẫn không thể chấp thuận path.

Khi xử lý `CertPathValidatorException` trong ứng dụng:

```java
// Đoạn minh họa, không phải một class đầy đủ.
// ex là CertPathValidatorException đã được bắt.
int index = ex.getIndex(); // Có thể là -1.
CertPathValidatorException.Reason reason = ex.getReason();
// Log reason/index ở kênh nội bộ được bảo vệ, tránh leak dữ liệu nhạy cảm.
```

Có thể bật debug tạm thời trong môi trường kiểm soát, chẳng hạn `-Djava.security.debug=certpath` với JDK/implementation hỗ trợ. Log path building có thể lộ hostname, subject/issuer, truststore và chi tiết nội bộ; không bật lâu dài trong production, không đưa vào API response công khai.

## 12. Các sai lầm lớn cần loại bỏ

1. **“Builder chỉ tìm chain, validator mới xác minh.”** Sai: với PKIX, builder **trả path đã validate**, không phải một danh sách ghép tùy tiện.
2. **“Validator sẽ tự tìm intermediate nếu path không có.”** Sai: validator kiểm tra **path được cung cấp**; nó không có nhiệm vụ path discovery.
3. **“Kết quả path chỉ có 2 certificate nghĩa là bị thiếu root.”** Không: PKIX builder **loại trust anchor khỏi `CertPath`**; anchor lấy riêng qua result.
4. **“CertStore = truststore.”** Không: `CertStore` chứa **candidates**; trust anchors là quyết định độc lập.
5. **“Thêm intermediate vào truststore sẽ chữa mọi lỗi PKIX.”** Rất nguy hiểm: có thể vô tình mở rộng tập CA được tin cậy; cung cấp intermediate làm candidate đúng chức năng.
6. **“Chỉ cần subject DN của issuer trùng subject DN của cert trước.”** Không: cần kiểm tra chữ ký, key, constraints, thời hạn, policy và chain đầy đủ.
7. **“Trust anchor phải luôn là self-signed root.”** Không về mặt API: trust anchor là một quyết định trust, có thể trỏ vào CA khác theo policy; nhưng phạm vi tin cậy phải được hiểu và kiểm soát.
8. **“Builder trả thành công nghĩa là hostname chính xác.”** Không: PKIX path validation không tự biết hostname mà client đang muốn kết nối.
9. **“Bật tắt revocation không quan trọng.”** Sai: đây là phần quan trọng của threat model; demo offline tắt không được copy vào production.
10. **“Set `maxPathLength=1` nghĩa là cả path chỉ gồm một cert.”** Không: tham số này giới hạn **intermediate**; leaf và trust anchor có vai trò riêng.
11. **“Path xây thành công hôm nay sẽ luôn hợp lệ.”** Không: time, revocation, trust policy và thuật toán bị cấm có thể thay đổi.
12. **“Có certificate bất kỳ từ mạng là có thể tin.”** Không: candidates không có authority; phải nối tới **trust anchor đã xác minh trước**.
13. **“Đúng root CA là đủ chống mọi MITM.”** Không: cần endpoint identity (SAN/hostname), EKU/purpose và bảo vệ giao thức TLS.
14. **“Một lời gọi `CertPathValidator.validate` chính là toàn bộ TLS handshake.”** Không: TLS còn key agreement, proof of possession, protocol negotiation, record protection, replay policies và JSSE configuration.

## 13. Tình huống luyện tập

**Tình huống A.** Client có leaf của server và truststore chứa root; peer không gửi intermediate nhưng ứng dụng có `intermediate.pem` ở một `CertStore`. Nên dùng gì?  
**Trả lời:** Dùng **`CertPathBuilder`** nếu cần tìm path từ leaf tới trust anchor qua candidate; builder có thể tìm intermediate và validate chain. Không thêm intermediate làm trust anchor chỉ để qua lỗi.

**Tình huống B.** Ứng dụng đã có path `[leaf, intermediate]` và muốn xác minh nó có còn hợp lệ vào một thời điểm cụ thể.  
**Trả lời:** Dùng **`CertPathValidator`** với `PKIXParameters` có trust anchors và `setDate(...)` theo policy; nó kiểm tra **path đã cho**.

**Tình huống C.** Builder trả `getCertPath().getCertificates().size() == 2` trong hệ thống có root/intermediate/leaf. Có thiếu root không?  
**Trả lời:** Không. **Root là trust anchor**, lấy từ `getTrustAnchor()`, không nằm trong danh sách path.

**Tình huống D.** Có certificate chain với leaf cho `internal-a.example.test`, app kết nối tới `internal-b.example.test`. Builder/validator PKIX thành công có đủ an toàn cho HTTPS không?  
**Trả lời:** **Không.** Cần kiểm tra hostname/endpoint identity và mục đích certificate trong TLS client.

**Tình huống E.** Một intermediate xuất hiện trong `CertStore` có chữ ký hợp lệ nhưng dẫn về root chưa được tin. Có được chấp thuận không?  
**Trả lời:** Không chỉ nhờ intermediate nằm trong CertStore. Phải có path đến **trust anchor được chấp thuận** và các constraints đều thỏa.

**Tình huống F.** Builder với `setMaxPathLength(0)` thất bại vì cần một intermediate. Có thể tăng lên `1` không?  
**Trả lời:** Có thể nếu trust policy chấp thuận một intermediate và các CA constraints cho phép; cần đánh giá bảo mật. Đừng tự động cho phép vô hạn chỉ vì lỗi.

**Tình huống G.** Có đủ chain và anchor nhưng validator báo `EXPIRED` tại thời gian hiện tại. Có nên gọi builder để “tìm một chain khác” và bỏ qua expiry?  
**Trả lời:** Không được bỏ qua yêu cầu thời hạn. Builder cũng phải tôn trọng validation date; nếu thực sự có path khác hợp lệ thì chỉ khi chính sách cho phép mới có ý nghĩa.

**Tình huống H.** CertStore có nhiều CRL, nhưng `setRevocationEnabled(false)`. Certificate bị thu hồi có chắc bị từ chối không?  
**Trả lời:** Không. Thêm CRL candidates không tự bật revocation. Production phải cấu hình revocation checker/policy đúng và test.

**Tình huống I.** Một certificate tự ký của attacker được cấp vào truststore bởi một script import tự động. Builder có thể trả thành công cho leaf do attacker cấp không?  
**Trả lời:** Có thể nếu anchor bị thêm trái phép và các tham số còn lại thỏa; truststore quản trị sai **làm thay đổi ranh giới tin cậy**. Không nhập chứng chỉ chưa xác minh.

**Tình huống J.** `PKIXCertPathBuilderResult` trả path đã validate. Vì sao ví dụ còn gọi `CertPathValidator`?  
**Trả lời:** Để học hai API và minh họa **revalidation** khi thay thời điểm/chính sách. Không phải vì builder chỉ “xây mà chưa kiểm”.

## 14. Checklist khi thiết kế PKIX trong Java

- **Xác định đúng việc cần làm:** cần **tìm** path từ target → builder; đã có path muốn **kiểm tra** → validator.
- **Chọn trust anchors từ nguồn đã xác minh:** tránh import certificate vô tội vạ, không đánh đồng candidate với trust.
- **Chọn target constraints chính xác:** `X509CertSelector` phù hợp, nhận dạng certificate hoặc key/subject/usage cần dùng.
- **Cung cấp candidate stores có kiểm soát:** leaf, intermediates và CRL; giới hạn kết nối mạng và input kích thước lớn.
- **Hiểu `CertPath` ordering:** Java PKIX path thường từ leaf đến intermediate, **không chứa trust anchor**.
- **Dùng đúng parameter class:** `PKIXBuilderParameters` khi `build`, `PKIXParameters` khi `validate`; đặt date, revocation, policy, algorithm constraints phù hợp.
- **Không tắt revocation vì tiện:** phân loại demo offline với production, có chiến lược CRL/OCSP/failure handling.
- **Đừng coi PKIX là hostname check:** TLS client phải thực hiện endpoint identification/SAN và certificate purpose/usage checks.
- **Báo lỗi đúng API:** builder failure khác validator failure; ghi reason/index/cause trong log an toàn khi có thể.
- **Kiểm thử nhiều loại path:** thiếu intermediate, wrong anchor, expired, invalid signature, constrained CA, cross-sign, revocation và hostname mismatch.
- **Bám theo provider/runtime thật:** `PKIX` thường có sẵn trên JDK, nhưng certpath policies, AIA behavior, disabledAlgorithms, revocation support có thể thay đổi.
- **Không tự viết validator X.509:** RFC 5280 phức tạp; dùng JCA/JSSE và thư viện/giao thức được duy trì.

## 15. Tài liệu đối chiếu

- [Java SE 21 — `CertPathBuilder`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathBuilder.html): engine xây đường dẫn và `build`.
- [Java SE 21 — `CertPathValidator`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html): engine kiểm tra path đã cho.
- [Java SE 21 — `PKIXBuilderParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXBuilderParameters.html): target constraints, trust anchors, CertStore và `maxPathLength`.
- [Java SE 21 — `PKIXParameters`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXParameters.html): date, policies, revocation, trust anchors, CertStores.
- [Java SE 21 — `PKIXCertPathBuilderResult`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXCertPathBuilderResult.html) và [`PKIXCertPathValidatorResult`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/PKIXCertPathValidatorResult.html): kết quả thành công và ý nghĩa trust anchor.
- [Java SE 21 — `CertStore`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertStore.html), [`TrustAnchor`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/TrustAnchor.html), [`X509CertSelector`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CertSelector.html): candidate pool, điểm tin cậy và lựa chọn target.
- [Java SE 17 — Java PKI Programmer’s Guide](https://docs.oracle.com/en/java/javase/17/security/java-pki-programmers-guide.html): ví dụ path building/validation và tập API certpath.
- [RFC 5280 — X.509 PKIX Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280.html): thuật toán kiểm tra certification path, trust anchor, constraints, CRL.
- [RFC 4158 — Internet X.509 Public Key Infrastructure: Certification Path Building](https://www.rfc-editor.org/rfc/rfc4158.html): tư duy path building và lựa chọn đường dẫn.

**Điểm cần nhớ:** `CertPathBuilder` **tìm và trả một path đã được xác minh**, sử dụng target, candidates và trust anchors; `CertPathValidator` **kiểm tra một path được đưa vào**, không tự xây chain khác. **Trust anchor là quyết định tin cậy**, `CertStore` chỉ là nguồn ứng viên, và **PKIX path thành công không thay thế kiểm tra hostname, mục đích certificate hay toàn bộ TLS policy**.