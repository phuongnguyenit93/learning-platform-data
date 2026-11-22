# 13.7. Phân biệt checkValidity, verify chữ ký chứng thư và kiểm tra độ tin cậy

**Một chứng thư X.509 có thể còn hạn sử dụng, có chữ ký mật mã hoàn toàn hợp lệ, nhưng vẫn không đáng tin để kết nối đến máy chủ mà bạn định truy cập.** Đây là điểm cần hiểu trước khi dùng `java.security.cert.X509Certificate` trong Java.

Ba thao tác thường bị đánh đồng:

1. **`certificate.checkValidity()`**: kiểm tra **thời gian hiện tại** có nằm trong khoảng `notBefore`–`notAfter` của **một chứng thư cụ thể** không.
2. **`certificate.verify(issuerPublicKey)`**: kiểm tra **chữ ký số trên chính chứng thư đó** có hợp lệ đối với **public key được cung cấp** không.
3. **Kiểm tra độ tin cậy (certificate path validation / PKIX trust validation)**: xác định có **đường chứng thực hợp lệ từ chứng thư đích qua các CA trung gian tới một trust anchor đã được chấp nhận từ trước**, đồng thời thỏa chính sách về thời gian, ràng buộc CA, thuật toán, mục đích dùng, revocation và các giới hạn có liên quan hay không.

Khi đối tượng là máy chủ HTTPS, còn một yêu cầu **khác nữa**: chứng thư đã được xác minh phải đại diện cho **đúng tên máy chủ mà client mong muốn kết nối**, ví dụ `api.example.com`. Và trong một handshake TLS, phía server cần chứng minh có quyền dùng private key tương ứng theo giao thức. Do đó, cả ba thao tác kể trên đều **không nên được dùng riêng lẻ thay cho TLS/PKIX verification hoàn chỉnh**.

## 1. Mục tiêu và bản đồ ba tầng kiểm tra

Sau bài học, bạn có thể:

- Đọc `notBefore`, `notAfter` và áp dụng đúng `checkValidity()`/`checkValidity(Date)`.
- Dùng `verify(PublicKey)` đúng nghĩa là kiểm tra chữ ký X.509 bằng khóa của issuer, **không phải** kiểm tra chứng thư có đáng tin hay không.
- Hiểu vì sao chứng thư **self-signed** do kẻ tấn công tạo vẫn có thể vượt qua cả hai kiểm tra trên.
- Giải thích `TrustAnchor`, `KeyStore`/truststore, `CertPath`, `CertPathValidator`, `CertPathBuilder` và `PKIXParameters`.
- Phân biệt chain cryptographically valid, path trusted, certificate policy hợp lệ và application identity đúng.
- Xác định cách xử lý CA certificate, `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage`, `SubjectAlternativeName`, policy, revocation và hostname.
- Viết và chạy minh họa Java 17+ dựa trên truststore mặc định, cho thấy signature/time validity khác với trust root.
- Nhận diện các anti-pattern: trust-all, tự tin vào self-signature, tạo trust anchor từ certificate client gửi, bỏ hostname verification, tắt revocation không có đánh giá.
- Biết khi nào nên giao xác thực chứng thư cho **JSSE/HttpClient/TLS stack** thay vì viết một validator riêng.

### 1.1. Bảng phân biệt ngay từ đầu

| Câu hỏi | API hoặc cơ chế | Nó trả lời điều gì? | **Không** chứng minh |
| --- | --- | --- | --- |
| Chứng thư có nằm trong khoảng thời gian của nó? | `X509Certificate.checkValidity()` | Một ngày nằm trong `notBefore ≤ date ≤ notAfter` theo phép kiểm tra của API | Chữ ký, issuer, trust, hostname, quyền |
| Nội dung chứng thư được issuer ký hợp lệ? | `X509Certificate.verify(issuerPublicKey)` | Chữ ký trên `tbsCertificate` hợp lệ với khóa chỉ định | Khóa issuer có đáng tin, chuỗi CA đúng, chứng thư còn hạn hay hostname |
| Chứng thư đích có thể được tin theo cấu hình/policy? | `CertPathValidator("PKIX")` và `TrustAnchor`; hoặc trust manager trong TLS | Một đường PKIX thỏa các kiểm tra chứng thực tới anchor được tin | Tên dịch vụ HTTPS đúng nếu không kiểm tra danh tính endpoint, ứng dụng được cấp quyền |
| Có đúng server `api.example.com` không? | Endpoint identification/hostname validation trong TLS/JSSE | Certificate identity phù hợp với **tên client định gọi** | Người dùng/app có quyền truy cập mọi tài nguyên |
| Server có private key phù hợp với certificate không? | Chứng minh trong TLS handshake như `CertificateVerify` ở TLS 1.3 | Bằng chứng sở hữu khóa ký trong phiên và binding với handshake | Authorization nghiệp vụ, chống replay của request ứng dụng |
| Client có quyền thực hiện thao tác? | Authorization của ứng dụng | Principal đã xác thực có quyền với resource/action/tenant | Những bảo đảm này không tự đến từ `checkValidity`/`verify` |

Một câu ghi nhớ: **“Còn hạn” khác “chữ ký đúng”; “chữ ký đúng” khác “được tin”; “được tin” khác “đúng đối tượng và được phép”.**

## 2. Cấu trúc chứng thư X.509 tối thiểu cần hiểu

Một chứng thư X.509 thường có:

```text
Certificate
  tbsCertificate  (to-be-signed certificate)
    version
    serialNumber
    signature algorithm identifier
    issuer name
    validity
      notBefore
      notAfter
    subject name
    subjectPublicKeyInfo
      public key algorithm
      public key bytes
    extensions
      BasicConstraints
      KeyUsage
      ExtendedKeyUsage
      SubjectAlternativeName
      SubjectKeyIdentifier / AuthorityKeyIdentifier
      policies / name constraints / CRL or OCSP metadata...
  signatureAlgorithm
  signatureValue
```

Khi CA cấp certificate cho server, CA **ký nội dung `tbsCertificate`** bằng private signing key của CA. Server nhận certificate cùng public key được cấp; client có thể xác minh chữ ký bằng **public key của CA tương ứng** nếu có certificate issuer.

Chẳng hạn:

```text
Root CA (được lưu tin cậy từ trước)
   subject = Example Root CA
   public key = K_root_public
           |
           | ký certificate của Intermediate CA
           v
Intermediate CA
   issuer = Example Root CA
   public key = K_intermediate_public
           |
           | ký certificate của api.example.com
           v
Leaf / end-entity certificate
   issuer = Example Intermediate CA
   SAN = DNS:api.example.com
   public key = K_server_public
```

Để tin server, không đủ kiểm tra chữ ký của leaf bằng public key intermediate. Client phải kiểm tra tiếp **issuer intermediate**, chuỗi ràng buộc, anchor được tin, constraints và **đúng tên máy chủ**.

### 2.1. Self-issued, self-signed và trusted không đồng nghĩa

- **Self-issued:** subject name trùng issuer name. Điều này chỉ liên quan metadata tên; không tự chứng minh chữ ký tự ký.
- **Self-signed:** chữ ký certificate có thể được xác minh bằng **chính public key** của certificate (và trong cách dùng thông thường còn có subject/issuer phù hợp).
- **Trusted:** một chính sách tin cậy, truststore hoặc cấu hình out-of-band đã **chấp nhận** certificate/key đó làm anchor cho mục đích phù hợp.

Một root CA trong truststore thường tự ký; **kẻ tấn công cũng có thể tạo một root tự ký hợp lệ bằng khóa của họ**. Self-signature chỉ chứng tỏ sự nhất quán mật mã đối với public key đó, không chứng tỏ CA đáng tin.

### 2.2. Issuer DN khớp không đủ

Dù:

```text
leaf.issuer == intermediate.subject
```

vẫn chưa đủ. Hai CA khác nhau có thể dùng cùng tên (hoặc cùng tên qua lần thay khóa). Phải chọn đúng certificate/key ký, xác minh chữ ký và kiểm tra **toàn bộ đường** theo PKIX. Extensions `AuthorityKeyIdentifier`/`SubjectKeyIdentifier` có thể hỗ trợ path building, nhưng không thay chữ ký hoặc trust policy.

## 3. `checkValidity()` thực sự kiểm tra gì?

Java cung cấp:

```java
certificate.checkValidity();
certificate.checkValidity(someDate);
```

`checkValidity()` sử dụng thời điểm hiện tại theo đồng hồ hệ thống. `checkValidity(Date)` kiểm tra tại thời điểm người gọi chỉ định. Nếu chứng thư vượt qua, nghĩa là ngày xét **nằm trong cửa sổ thời gian `notBefore` đến `notAfter` của chính certificate**.

Các lỗi đặc trưng:
- `CertificateNotYetValidException`: thời điểm kiểm tra **trước `notBefore`**.
- `CertificateExpiredException`: thời điểm kiểm tra **sau `notAfter`**.

Ví dụ chỉ nhằm minh họa API (giả sử biến `cert` là `X509Certificate` đã parse):

```java
try {
    cert.checkValidity();
    System.out.println("Certificate is within its validity interval");
} catch (java.security.cert.CertificateExpiredException expired) {
    System.out.println("Certificate expired");
} catch (java.security.cert.CertificateNotYetValidException notYet) {
    System.out.println("Certificate is not yet valid");
}
```

Đây là **snippet phụ thuộc biến `cert`**, không phải toàn chương trình; chương trình tự chạy đầy đủ ở phần 10.

### 3.1. Đừng nhầm với việc xác định chứng thư đáng tin

`checkValidity()` **không**:
- Kiểm tra chữ ký số của certificate.
- Kiểm tra certificate có được CA nào ký hay không.
- Kiểm tra chain đi tới trust anchor đã cấu hình.
- Kiểm tra CA có `BasicConstraints: CA=true` hoặc `KeyUsage: keyCertSign`.
- Kiểm tra server name trong SAN có khớp hostname không.
- Kiểm tra chứng thư có bị thu hồi (revoked) không.
- Kiểm tra thuật toán ký hay độ dài khóa có phù hợp chính sách không.
- Kiểm tra certificate có mục đích `serverAuth` hay `clientAuth` phù hợp không.
- Chứng minh bên kia đang sở hữu private key tương ứng.

Có thể nói: **một certificate tự ký do Mallory tạo hôm nay với hiệu lực một năm sẽ vượt qua `checkValidity()` ngay lập tức**. Điều đó hoàn toàn không khiến Alice phải tin Mallory là `bank.example.com`.

### 3.2. Kiểm tra tại thời điểm khác

`checkValidity(Date)` hữu ích khi mô phỏng một thời điểm để test, nhưng thay ngày kiểm tra không tự biến một certificate đã expired thành hợp lệ cho giao thức production. Việc xác minh chữ ký lịch sử, timestamp và chính sách thời điểm ký có các yêu cầu riêng.

Ví dụ:

```java
Date reference = new Date();
cert.checkValidity(reference);
```

Với TLS đang hoạt động, client thường cần chứng thư hợp lệ theo chính sách thời điểm handshake. Nếu đồng hồ client sai, kết quả có thể sai; vận hành cần đồng bộ thời gian, không nới lỏng validation vô điều kiện.

### 3.3. Chứng thư CA cũng có hạn

Chỉ kiểm tra `leaf.checkValidity()` bỏ sót khoảng hiệu lực của **intermediate CA certificates**. PKIX path validation xét một chuỗi gồm nhiều certificate với các quy tắc cụ thể. Trust anchors có địa vị cấu hình đặc biệt và cách kiểm tra thời gian/constraints của anchor có thể khác các certificate trong path: đừng tự khẳng định “path validator luôn `checkValidity` root giống leaf”.

## 4. `verify(PublicKey)` thực sự kiểm tra gì?

`X509Certificate.verify(PublicKey key)` sử dụng **public key do người gọi cung cấp** để xác minh chữ ký trên certificate.

Đối với một leaf có issuer là intermediate:

```java
leaf.verify(intermediate.getPublicKey());
```

Đối với một intermediate do root ký:

```java
intermediate.verify(root.getPublicKey());
```

Đối với certificate tự ký:

```java
selfSignedRoot.verify(selfSignedRoot.getPublicKey());
```

Về mật mã, thao tác kiểm tra rằng `signatureValue` phù hợp với `tbsCertificate`, signature algorithm và public key cung cấp. Nó không tự hỏi “public key này được lấy từ đâu?”, “CA này có được phép ký chứng thư không?” hoặc “subject này có đúng người nhận không?”.

### 4.1. Chữ ký đúng vẫn có thể không đáng tin

Giả sử Mallory:
1. Sinh một RSA/EC/Ed25519 key pair riêng.
2. Tạo certificate tự ký cho `CN=api.example.com`, đặt `notBefore` là hôm qua và `notAfter` là năm sau.
3. Tự ký `tbsCertificate` bằng private key của mình.
4. Gửi certificate cho Alice.

Alice gọi:

```java
malloryCert.checkValidity();
malloryCert.verify(malloryCert.getPublicKey());
```

Cả hai phép kiểm tra **có thể thành công**. Nhưng không có gì ràng buộc public key Mallory với `api.example.com` theo trust policy của Alice. Nếu Alice chấp nhận sau hai dòng này, Alice đã bỏ qua **xác thực nguồn chứng thư** và có thể bị MITM.

**Lỗi nguy hiểm hơn:** ứng dụng đọc certificate do peer gửi rồi luôn gọi `verify(peerCertificate.getPublicKey())`. Với leaf được CA ký, thao tác đó thường thất bại vì leaf không tự ký; với certificate tự ký của kẻ tấn công, lại có thể thành công. Đây là sự đảo ngược logic kiểm tra tin cậy.

### 4.2. `verify` có kiểm tra thời gian không?

Không. Một certificate đã hết hạn vẫn có thể có chữ ký số hoàn toàn hợp lệ. Chữ ký mô tả nội dung certificate đã được một key ký, không quyết định certificate còn được phép dùng ở thời điểm hiện tại hay không.

Ngược lại, certificate còn hạn nhưng bị sửa `tbsCertificate` sau khi ký hoặc được kiểm tra bằng sai public key có thể bị `verify` từ chối.

### 4.3. `verify` có kiểm tra CA/KeyUsage không?

Không đủ. Nếu một certificate intermediate thực sự có chữ ký hợp lệ của một key, vẫn phải xác định issuer có được phép ký certificate theo `BasicConstraints`, `KeyUsage` và các ràng buộc path/policy khác.

Ví dụ:
- Một end-entity certificate có `BasicConstraints: CA=false` không thể tự động được dùng làm intermediate hợp lệ chỉ vì nó chứa public key có thể verify một chữ ký.
- Một chain có quá nhiều CA dưới một CA với `pathLenConstraint` có thể vi phạm policy mặc dù từng chữ ký riêng lẻ hợp lệ.
- Name constraints có thể cấm intermediate cấp certificate cho một miền tên cụ thể.

Đây là lý do **không tự làm path validation bằng vòng lặp `cert.verify(issuerKey)` rồi trả true**.

### 4.4. Chữ ký của certificate khác chữ ký trong TLS handshake

Xác minh chữ ký X.509 certificate xác định certificate đã được **issuer ký**. Nó không trực tiếp chứng minh server đang kết nối **giữ private key của leaf certificate**.

Trong TLS 1.3 dùng certificate authentication, thông điệp `CertificateVerify` chứng minh quyền sở hữu private signing key tương ứng trên ngữ cảnh handshake được protocol định nghĩa. `Finished` tiếp tục xác thực transcript bằng handshake secrets. Bởi vậy, việc tự gọi `leaf.verify(issuerPublicKey)` khi parse một PEM **không thay thế toàn bộ TLS handshake**.

## 5. Kiểm tra độ tin cậy là bài toán **path validation**

PKI dựa trên một quan hệ tin cậy cấu hình từ trước:

```text
                 TRUST CONFIGURATION
               (KeyStore / Trust Anchors)
                           |
                       Root CA
                       (trusted)
                           |
                      verifies/signs
                           |
                    Intermediate CA
                    (CA constraints)
                           |
                      verifies/signs
                           |
                      Leaf certificate
                      (server identity)
                           |
               Must additionally match:
                  requested hostname
                  intended key usage/EKU
                  application security policy
```

Trong Java, các đối tượng quan trọng:

- `KeyStore`: kho lưu certificate/key entries; truststore là cách thông dụng cấu hình các CA được tin.
- `TrustAnchor`: đại diện một root certificate hoặc CA name + public key được người vận hành **chủ động tin cậy**.
- `CertPath`: danh sách certificate **từ target/leaf hướng về issuer**, theo thứ tự mà provider mong đợi; thông thường **không bao gồm trust anchor**.
- `CertPathValidator` với thuật toán `PKIX`: kiểm tra một path đã có đối với cấu hình tin cậy và constraints.
- `CertPathBuilder`: tìm hoặc xây dựng một đường chứng thực từ certificate store/candidate chains/constraints.
- `PKIXParameters` / `PKIXBuilderParameters`: tập trust anchors, thời gian kiểm tra, certificate policies, revocation settings, checker/constraints khác.
- `X509TrustManager` / `X509ExtendedTrustManager`: thành phần JSSE thực hiện certificate-chain trust decisions trong TLS theo ngữ cảnh provider/session.

**Có ba bài toán khác nhau:** *tìm chain*, *xác minh chain*, và *đối chiếu certificate identity với dịch vụ mà ứng dụng định truy cập*. Một API không nhất thiết giải quyết cả ba.

### 5.1. Cấu trúc `CertPath` và trust anchor

Ví dụ chain:

```text
Certificate path (đưa cho validator):
    [leaf api.example.com, intermediate Example Issuer]

Trust anchor (cấu hình tin cậy bên ngoài path):
    Example Root CA
```

PKIX validator xác minh leaf bằng khóa intermediate và intermediate theo path/anchor tương ứng, đồng thời áp các ràng buộc được quy định.

**Không** đưa một certificate root từ chính gói tin của client vào:

```java
// Anti-pattern: root certificate comes only from untrusted network input.
new TrustAnchor(untrustedRootSentByPeer, null);
```

rồi tuyên bố đã có trust vì `CertPathValidator` pass. Làm vậy thực chất **tự tin một CA do đối thủ chọn**. Trust anchor phải có từ một truststore hoặc kênh cấu hình đã xác thực với policy phù hợp.

### 5.2. Điều mà PKIX có thể kiểm tra

Với cấu hình/implementation phù hợp, PKIX path validation xem xét:
- Chữ ký của các certificate trong chain và quan hệ với issuer/trust anchor.
- Thời hạn certificate trong path tại thời điểm kiểm tra.
- `BasicConstraints`, `KeyUsage` và khả năng certificate có được làm CA hay không.
- Path length constraints, name constraints và những extension được nhận diện/critical.
- Chứng thư/thuật toán/kiểu khóa có thỏa policy của validator/provider, các checker tùy chọn.
- Certificate policies và ràng buộc cụ thể khi cấu hình.
- Revocation qua CRL/OCSP hoặc cơ chế tương ứng **khi có bật và cấu hình theo policy**.

**Nhưng PKIX path validation thuần không tự biết ứng dụng muốn kết nối tới `api.example.com` hay `mail.example.com`.** Hostname/endpoint identification cần chính sách ứng dụng/TLS bổ sung.

### 5.3. Path xây dựng khác với path kiểm tra

`CertPathBuilder` có thể cần một tập candidate intermediate certificates, CA stores hoặc AIA retrieval theo provider/config. `CertPathValidator` được đưa một path đã xác định và áp luật validation.

Đừng mặc định JDK sẽ tự tải toàn bộ intermediate từ mạng cho bạn. Nếu thiếu intermediate và builder không được cấu hình nguồn/cách tải, một certificate hợp lệ về lý thuyết vẫn có thể không xây được chain.

Với cross-signing, có thể tồn tại nhiều đường tới những root khác nhau; path builder cần chọn đường phù hợp anchor/policy. So khớp issuer/subject strings không đủ để tự xây một path chính xác và an toàn.

## 6. Trust anchor không phải kết quả của `verify`

### 6.1. Trust anchor là quyết định tin cậy từ trước

Root CA trong truststore được hệ thống hoặc người quản trị đặt ở trạng thái đáng tin cho một phạm vi sử dụng. Đó là **quyết định vận hành/chính sách**, không phải hệ quả toán học của self-signature.

Một attacker có thể:
- Sinh cặp khóa và certificate X.509 tự ký.
- Đặt `notBefore`/`notAfter` hợp lệ.
- Đặt subject giống tên cơ quan có uy tín.
- Tự verify chữ ký bằng public key của mình.

Nhưng Alice không có lý do để tin certificate đó là trust anchor trừ khi có kênh phân phối/kiểm tra độc lập đáng tin.

### 6.2. Cấu hình truststore sai là một lỗi thực tế

Các anti-pattern:
- Load `cacerts` hoặc truststore rỗng, rồi nếu validation thất bại thì “tự thêm server certificate vào truststore”.
- Chấp nhận mọi self-signed certificate.
- Bắt ngoại lệ `CertificateException` rồi bỏ qua.
- Dùng một truststore toàn công ty nhưng vô tình cấp trust cho CA không đúng scope.
- Pin một public key lấy từ lần kết nối đầu tiên mà không có biện pháp xử lý MITM đầu tiên, nhưng lại tuyên bố tương đương xác thực CA.

Đối với CA nội bộ, có thể thêm CA certificate vào truststore riêng **sau khi được xác minh qua kênh quản trị an toàn**. Sau đó bắt tay vẫn phải kiểm tra chain, danh tính endpoint, key usages và rotation/revocation theo policy.

### 6.3. Cẩn thận với root do bên kia gửi kèm

TLS server có thể gửi một certificate chain và đôi khi gửi cả root. Bản sao root được truyền qua mạng **không trở thành trusted** chỉ vì server gửi nó. Client phải so khớp đường chứng thực với trust anchor đã có trong cấu hình, không “tự cấp quyền trust” cho root từ packet.

## 7. Hostname và danh tính dịch vụ: lớp khác với PKIX

Giả sử client gọi:

```text
https://payments.example.com
```

Server trình certificate có chain hoàn toàn hợp lệ tới CA công khai, nhưng `SubjectAlternativeName` chứa:

```text
DNS:files.example.com
```

Cả:
- `checkValidity()`,
- `verify(issuerPublicKey)`,
- và thậm chí **PKIX path validation** tới một trust anchor hợp lệ,

đều có thể pass, trong khi client **vẫn phải từ chối certificate cho `files.example.com`** vì ứng dụng mong đợi `payments.example.com`.

### 7.1. Expected identity phải do client xác định

Đừng lấy “expected hostname” từ một field không tin cậy do server tự khai rồi hỏi certificate có khớp hay không. Nếu client định nối `payments.example.com`, chính tên đó là reference identity từ target URL hoặc cấu hình dịch vụ đã xác thực.

Các nguyên tắc:
- DNS name thường được kiểm tra trong **SAN dNSName** theo chuẩn TLS/service identity được áp dụng.
- Kết nối tới IP literal cần xử lý quy tắc **iPAddress SAN**, không tự so sánh string CN hoặc reverse DNS để chấp nhận.
- Wildcard, IDNA và canonicalization phải tuân theo quy tắc thư viện/chuẩn; không viết `endsWith(".example.com")` tự chế.
- `CN` trong subject không nên được xem là giải pháp thay thế mặc định cho SAN hiện đại.
- SNI giúp server chọn certificate phù hợp, **không phải** bằng chứng rằng certificate đó khớp hostname hoặc đáng tin.

### 7.2. Endpoint identification trong JSSE

Khi dùng HTTPS client chuẩn, để TLS stack thực hiện certificate-chain validation và hostname validation. Ví dụ `java.net.http.HttpClient` của Java 17 theo cấu hình mặc định phù hợp dùng TLS verification; **đừng** tắt nó với các tùy chọn insecure.

Nếu tự dùng `SSLSocket` trong trường hợp đặc biệt, phải bảo đảm endpoint identification (ví dụ `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` cho kết nối HTTPS), đúng expected host, trust manager và client/server mode. Việc trực tiếp gọi `X509TrustManager.checkServerTrusted(...)` trên một mảng certificate mà **không có ngữ cảnh endpoint** thường **không thay hostname validation**.

### 7.3. Các bước cho TLS 1.3 server authentication

Một sơ đồ khái niệm:

```text
Client wants: payments.example.com
   |
   v
TLS handshake receives certificate chain
   |
   +--> PKIX / trust manager checks:
   |      signatures, path, anchors, constraints, validity,
   |      revocation/policies according to configuration
   |
   +--> Endpoint identity check:
   |      SAN matches payments.example.com
   |
   +--> TLS handshake proof of possession / transcript:
   |      CertificateVerify and Finished as defined by TLS 1.3
   |
   +--> Security policy:
          key/algorithm rules, TLS version, application authorization
   |
   v
Only then treat channel as connected to expected server
```

**Một certificate hợp lệ không tự tạo một kênh TLS an toàn.** Còn phải bảo đảm handshake transcript, key agreement, record protection và identity theo giao thức.

## 8. Revocation: chứng thư “còn hạn” vẫn có thể bị thu hồi

Một certificate có thể được CA **thu hồi trước `notAfter`**, ví dụ do private key bị lộ, subject không còn quyền hoặc CA cấp sai.

`checkValidity()` chỉ xem cửa sổ thời gian; `verify(...)` kiểm tra chữ ký đã tồn tại; cả hai **không** tra cứu trạng thái thu hồi.

Cơ chế thường gặp:
- **CRL (Certificate Revocation List)**: danh sách chứng thư bị thu hồi do CA công bố và ký.
- **OCSP (Online Certificate Status Protocol)**: hỏi trạng thái certificate qua responder theo profile.
- **OCSP stapling** và các chính sách TLS liên quan, tùy client/server stack.
- **Short-lived certificates** hoặc private PKI policy giảm thời gian rủi ro, nhưng không tự giải quyết mọi trường hợp compromise.

### 8.1. `PKIXParameters.setRevocationEnabled(...)`

`PKIXParameters` có cờ kiểm tra revocation và các cơ chế `PKIXRevocationChecker`/`CertStore`, cấu hình/khả năng provider. **Bật một cờ không bảo đảm hệ thống đã có đầy đủ dữ liệu CRL/OCSP hoặc policy xử lý lỗi.** Ngược lại, gọi:

```java
params.setRevocationEnabled(false);
```

là **cố ý tắt** revocation check của luồng PKIX đó. Đoạn mã ví dụ trong phần 10 có dòng này **chỉ để trình diễn ngoại tuyến không phụ thuộc mạng**, nên tuyệt đối không lấy đó làm cấu hình production mặc định.

Hệ thống thật phải quyết định:
- Khi không truy vấn được OCSP/CRL, fail closed hay chấp nhận theo ngoại lệ cụ thể?
- Có giới hạn tuổi CRL/staple và caching policy không?
- Network egress từ trust validator được kiểm soát ra sao?
- Với CA nội bộ, hệ thống cấp chứng thư ngắn hạn/rotation và revoke ra sao?
- Quan sát sự cố và cảnh báo có bảo vệ dữ liệu nhận dạng/chứng thư không?

Nếu một nhóm hệ thống dùng mTLS với private CA, việc không cấu hình revocation và rotation có thể khiến chứng thư đã bị thu hồi thực tế vẫn được client chấp nhận cho tới `notAfter`.

## 9. Chính sách CA, leaf và certificate extensions

### 9.1. BasicConstraints

Một intermediate CA thường cần `BasicConstraints: CA=true`. Một leaf server certificate thường là `CA=false`. `pathLenConstraint` giới hạn số lượng CA không tự cấp dưới nó theo quy tắc chuẩn. `verify` không thay việc kiểm tra ràng buộc này.

### 9.2. KeyUsage

Một CA certificate thường có `keyCertSign` để được sử dụng ký certificate. Leaf có các key usage khác tùy scheme, chẳng hạn `digitalSignature` để chứng minh possession trong TLS 1.3. Không suy luận từ một chữ ký certificate hợp lệ rằng key usage được phép.

### 9.3. ExtendedKeyUsage (EKU)

Một certificate dành cho server TLS có thể cần mục đích `id-kp-serverAuth`; client certificate dùng mTLS có thể cần `id-kp-clientAuth`. Việc áp EKU cụ thể phụ thuộc protocol, policy và implementation. `checkValidity()` không biết service đang dùng certificate cho mục đích nào; `verify(...)` cũng không kiểm tra EKU thay bạn.

### 9.4. Critical extensions và name constraints

X.509 extensions đánh dấu **critical** cần được hiểu và xử lý theo PKIX. Validator không được âm thầm bỏ qua những critical extensions ảnh hưởng security policy. Name constraints của CA có thể giới hạn miền được cấp certificate; chỉ verify chữ ký từng bước dễ bỏ qua chúng.

### 9.5. Algorithm/key strength

Chữ ký toán học hợp lệ bằng một thuật toán đã yếu hoặc kích thước khóa không đủ không đồng nghĩa **được phép sử dụng hôm nay**. Hệ thống phải áp algorithm constraints của JDK/provider, TLS security policy, tổ chức và cập nhật khi tiêu chuẩn thay đổi. Không tự động fallback xuống MD5/SHA-1 hoặc tắt constraints để “chấp nhận chứng thư cũ”.

## 10. Java 17+: minh họa ba phép kiểm tra bằng truststore có sẵn

Đoạn chương trình sau là **một class đầy đủ có thể biên dịch và chạy với Java 17+**, không tải dữ liệu từ Internet và không ghi file.

Nó làm những điều có thể tái lập, sử dụng những CA certificates **đã nằm trong truststore mặc định** của Java runtime:

1. Tìm hai certificate CA **self-signed, còn hạn và có public keys khác nhau** trong trust manager được cấu hình mặc định.
2. Với root đầu tiên, gọi `checkValidity()` và `verify(root.getPublicKey())`.
3. Chứng minh root này hiện có trong danh sách trusted issuers, nhưng **không** có trong một trust set rỗng.
4. Thử dùng `CertPathValidator("PKIX")` xác minh certificate đầu tiên **chỉ với root thứ hai, không liên quan, làm trust anchor**: kết quả thất bại. Đây là tình huống minh họa một self-signature đúng vẫn **không nối tới anchor khác**.
5. Chỉ ra rằng chương trình **chưa hề kiểm tra hostname**. Đây không phải ví dụ hoàn chỉnh để xác thực một HTTPS server.

**Lưu ý môi trường:** chương trình giả định truststore mặc định có **ít nhất hai root CA self-signed hiện còn hạn với public keys phân biệt**. JDK thông thường có nhiều CA như vậy. Nếu môi trường dùng truststore tối giản/rỗng, chương trình báo lỗi rõ thay vì tự tải hoặc tự tin một root lạ. Thứ tự certificate trong `getAcceptedIssuers()` không cố định; demo không in subject cụ thể.

Tệp `X509ChecksDemo.java`:

```java
import java.security.GeneralSecurityException;
import java.security.KeyStore;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateEncodingException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.List;
import java.util.Set;
import javax.net.ssl.TrustManager;
import javax.net.ssl.TrustManagerFactory;
import javax.net.ssl.X509TrustManager;

public class X509ChecksDemo {

    static X509TrustManager defaultTrustManager()
            throws GeneralSecurityException {
        TrustManagerFactory factory = TrustManagerFactory.getInstance(
                TrustManagerFactory.getDefaultAlgorithm()
        );
        factory.init((KeyStore) null); // Runtime's configured default trust store.

        for (TrustManager manager : factory.getTrustManagers()) {
            if (manager instanceof X509TrustManager x509) {
                return x509;
            }
        }
        throw new GeneralSecurityException("No X509 trust manager");
    }

    static boolean selfSignedAndCurrentlyValid(X509Certificate cert) {
        try {
            cert.checkValidity();
            if (!cert.getSubjectX500Principal().equals(
                    cert.getIssuerX500Principal())) {
                return false;
            }
            cert.verify(cert.getPublicKey());
            return true;
        } catch (GeneralSecurityException e) {
            return false;
        }
    }

    static X509Certificate[] chooseRoots(X509TrustManager manager) {
        X509Certificate first = null;

        for (X509Certificate cert : manager.getAcceptedIssuers()) {
            if (!selfSignedAndCurrentlyValid(cert)) {
                continue;
            }
            if (first == null) {
                first = cert;
                continue;
            }
            if (!Arrays.equals(
                    first.getPublicKey().getEncoded(),
                    cert.getPublicKey().getEncoded())) {
                return new X509Certificate[] {first, cert};
            }
        }
        throw new IllegalStateException(
                "Need two distinct currently valid CA certificates"
        );
    }

    static boolean isInTrustSet(
            X509Certificate candidate,
            X509Certificate[] trusted
    ) throws CertificateEncodingException {
        for (X509Certificate c : trusted) {
            if (Arrays.equals(candidate.getEncoded(), c.getEncoded())) {
                return true;
            }
        }
        return false;
    }

    static boolean pkixValidWithUnrelatedAnchor(
            X509Certificate candidate,
            X509Certificate unrelated
    ) throws GeneralSecurityException {
        // Deliberately use this self-signed CA as path target,
        // with a different CA as the only configured trust anchor.
        // This is a negative trust-path test, not normal leaf validation.
        CertPath path = CertificateFactory.getInstance("X.509")
                .generateCertPath(List.of(candidate));

        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(unrelated, null))
        );
        // OFFLINE DEMO ONLY: intentionally disables revocation checking.
        params.setRevocationEnabled(false);

        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return true;
        } catch (CertPathValidatorException expected) {
            return false;
        }
    }

    public static void main(String[] args) throws Exception {
        X509TrustManager manager = defaultTrustManager();
        X509Certificate[] roots = chooseRoots(manager);
        X509Certificate selected = roots[0];

        selected.checkValidity();
        selected.verify(selected.getPublicKey());

        System.out.println("Certificate time validity: true");
        System.out.println("Self-signature verifies: true");
        System.out.println("Listed in configured trust anchors: " +
                isInTrustSet(selected, manager.getAcceptedIssuers()));
        System.out.println("Listed in empty trust store: " +
                isInTrustSet(selected, new X509Certificate[0]));
        System.out.println("PKIX validates against unrelated root: " +
                pkixValidWithUnrelatedAnchor(selected, roots[1]));
        System.out.println("This program checked hostname: false");
    }
}
```

Biên dịch và chạy:

```bash
javac X509ChecksDemo.java
java X509ChecksDemo
```

Stdout đã được kiểm tra bằng các API tương thích Java 17 (trên JDK có truststore đủ root phù hợp):

```text
Certificate time validity: true
Self-signature verifies: true
Listed in configured trust anchors: true
Listed in empty trust store: false
PKIX validates against unrelated root: false
This program checked hostname: false
```

### 10.1. Diễn giải kết quả đúng nghĩa

- `Certificate time validity: true`: `selected` nằm trong cửa sổ hiệu lực hiện tại. Nó không chứng minh điều gì về identity của một máy chủ.
- `Self-signature verifies: true`: chữ ký self-signed của root xác minh được bằng chính public key nó chứa; không có CA khác đứng ra bảo chứng chỉ từ phép toán này.
- `Listed in configured trust anchors: true`: root đã được **runtime cấu hình tin cậy từ trước**; điều đó khác với việc tự ký hợp lệ.
- `Listed in empty trust store: false`: nếu không có trust anchor được chấp thuận, self-signature không tự đưa certificate vào tập đáng tin.
- `PKIX validates against unrelated root: false`: một root khác dù bản thân cũng đáng tin trong runtime **không thể tùy tiện ký thay certificate này**. Path validation phụ thuộc **đúng chuỗi và đúng anchor**.
- `This program checked hostname: false`: chương trình không có expected service hostname; dù một CA root trusted, đây vẫn **không phải một bài kiểm tra TLS server**.

**Giới hạn của demo:** `isInTrustSet` chỉ kiểm tra membership trong một array để minh họa định nghĩa trust anchor; **đừng dùng nó làm certificate validation cho leaf**. `pkixValidWithUnrelatedAnchor` cố tình đưa một root self-signed thành path target để chứng minh kết quả thất bại; hệ thống bình thường sẽ kiểm tra **leaf → intermediates** tới root trusted.

### 10.2. Dấu hiệu chứng minh tách biệt time/signature/trust

Hãy nhìn ba giả thuyết:

```text
A. Certificate still within dates?
   -> checkValidity()          [certificate-local test]

B. Certificate signature matches supplied key?
   -> verify(issuerPublicKey)  [cryptographic signature test]

C. Certificate chain accepted by configured PKI?
   -> CertPathValidator/JSSE   [trust-policy/path test]
      + HTTPS hostname match   [endpoint identity test]
```

Một lỗi ở A, B hoặc C có thể xảy ra độc lập với những phần còn lại. Nối ba phương thức bằng toán tử boolean tự viết chưa thay thế mọi ràng buộc của PKIX/TLS.

## 11. Java PKIX: xác minh một chain thực khi đã có các certificates tin cậy

Giả sử ứng dụng **đã nhận và parse đúng** các biến:
- `leaf`: X.509 end-entity certificate của dịch vụ.
- `intermediate`: certificate CA trực tiếp ký leaf.
- `configuredTrustedRoot`: root CA lấy từ **cấu hình/truststore có quyền**, không lấy từ packet không tin cậy.

Đoạn sau là **snippet Java 17**, cần các biến trên và import tương ứng; không phải chương trình độc lập:

```java
// Imports for this snippet:
// import java.security.cert.*;
// import java.util.*;

CertPath path = CertificateFactory.getInstance("X.509")
        .generateCertPath(List.of(leaf, intermediate));
// Trust anchor is kept OUT of the certificate path.

Set<TrustAnchor> approvedAnchors =
        Set.of(new TrustAnchor(configuredTrustedRoot, null));

PKIXParameters params = new PKIXParameters(approvedAnchors);
// params may also define evaluation date, revocation configuration,
// trusted CertStores, policy constraints, and additional checkers.

// Do NOT disable revocation here for a real security policy.
// Configure PKIXRevocationChecker / CRL / OCSP facilities as required.

CertPathValidator validator = CertPathValidator.getInstance("PKIX");
validator.validate(path, params);

// This success means the supplied path satisfied the configured
// PKIX trust validation. It is NOT by itself HTTPS hostname validation.
```

Để tránh hiểu sai:
- Nếu leaf được root ký trực tiếp, path thường là `List.of(leaf)`, trust anchor vẫn đặt riêng.
- Nếu có hai intermediates, đưa đúng thứ tự leaf → intermediate gần leaf → intermediate cấp trên, **không** trộn root vào path.
- Nếu chain chưa có đủ intermediates, phải xây dựng đúng path qua `CertPathBuilder`/certificate stores theo chính sách; không tự điền issuer bằng cách nối subject string.
- Không tự tạo `configuredTrustedRoot` từ certificate attacker vừa gửi. Mọi kết quả phía sau sẽ mất ý nghĩa nếu anchor không có nguồn tin cậy.
- PKIX có các quy tắc về BasicConstraints, key usage, policies, extensions và revocation được cấu hình; không thay chúng bằng hai lệnh `leaf.verify(...)` và `intermediate.verify(...)`.
- Sau validation, còn cần xác định **đúng tên dịch vụ/identity**, TLS handshake, application scope và authorization.

### 11.1. Cách parse certificate PEM hoặc DER trong Java

Một `CertificateFactory` X.509 có thể đọc certificate từ stream:

```java
// Snippet, requires java.nio.file.* and java.security.cert.* imports.
try (java.io.InputStream input =
             java.nio.file.Files.newInputStream(
                     java.nio.file.Path.of("server-cert.pem"))) {
    X509Certificate leaf = (X509Certificate)
            CertificateFactory.getInstance("X.509")
                    .generateCertificate(input);
}
```

Đây chỉ là **đọc và parse certificate**, không kiểm tra trust. Không được dùng `CertificateFactory.generateCertificate` như bằng chứng server đáng tin: parser có thể parse một certificate do attacker tạo đúng cấu trúc ASN.1/X.509.

Khi xử lý PEM bundles, nhiều certificate có thể được trình cùng nhau; cần chính sách xử lý thứ tự và path building. Certificate file và private key file là những loại tài liệu khác nhau, không phải root certificate được công khai thì private signing key cũng được công khai.

## 12. Điều Java HTTPS client nên làm trong production

Khi mục tiêu là gọi HTTPS, giải pháp tốt nhất thường **không** phải một class tự gọi `checkValidity` rồi `verify`, mà là dùng **JSSE/HTTP client chuẩn**:

```java
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class SecureHttpExample {
    public static void main(String[] args) throws Exception {
        HttpClient client = HttpClient.newHttpClient();
        HttpRequest request = HttpRequest.newBuilder(
                URI.create("https://example.com/")
        ).GET().build();

        HttpResponse<String> response = client.send(
                request, HttpResponse.BodyHandlers.ofString()
        );
        System.out.println("HTTP status: " + response.statusCode());
    }
}
```

Đây là **chương trình độc lập** nhưng cần có kết nối mạng, DNS và server hoạt động; **không nêu stdout cố định**. Mục đích là cho thấy có thể giao nhiệm vụ certificate chain/hostname/TLS handshake cho client chuẩn thay vì tự làm một validator. Chính sách trust thực tế còn phụ thuộc JDK, cấu hình TLS, truststore tùy chỉnh và các thiết lập hệ thống.

Không làm:

```java
// ANTI-PATTERNS: not safe for production.
// TrustManager.checkServerTrusted(...) { /* do nothing */ }
// HostnameVerifier.verify(host, session) { return true; }
// Ignore SSLHandshakeException and continue insecurely.
```

Nếu gặp `SSLHandshakeException`/`PKIX path building failed`, hãy tìm nguyên nhân: chain thiếu intermediate, truststore chưa có CA đúng, chứng thư hết hạn, tên máy chủ không khớp, ciphers/protocol policy hay revocation. Không “sửa” bằng cách tắt SSL verification.

### 12.1. Cẩn trọng với custom `SSLContext` và truststore

Nếu ứng dụng cần tin CA nội bộ:
- Import certificate CA **đã được xác thực out-of-band** vào truststore riêng hoặc dùng trust manager chuẩn đã cấu hình đúng.
- Kiểm tra rằng **chỉ đúng CA** và phạm vi được phép nằm trong truststore; không đưa tất cả certificate client gửi vào truststore.
- Vẫn giữ endpoint identification/hostname verification.
- Định nghĩa cách rotate CA, expire, revoke và quản lý truststore phiên bản.
- Kiểm thử bằng certificate chain thật và negative test wrong hostname/untrusted root.

Nếu tự thay `TrustManager` bằng implementation chấp nhận mọi certificate, bạn có thể đang **bỏ cả chain validation** mà không nhận ra.

## 13. Những tình huống phân biệt ba mức kiểm tra

### Tình huống A — Self-signed của người lạ

`notBefore` hôm qua, `notAfter` năm sau; chữ ký tự ký hợp lệ; không có trong truststore.

- `checkValidity()`: **pass**.
- `verify(cert.getPublicKey())`: **pass**.
- PKIX đối với truststore không chứa root đó: **fail**.
- Kết luận: **không được tin để đại diện server** chỉ vì time và signature đúng.

### Tình huống B — Certificate do CA trusted ký nhưng đã hết hạn

- `checkValidity()`: **fail**, ví dụ `CertificateExpiredException`.
- `verify(correctIssuerPublicKey)`: có thể **pass**; chữ ký vẫn tồn tại.
- PKIX thông thường tại thời điểm hiện tại: **fail** khi leaf ngoài validity interval.
- Kết luận: chữ ký đúng không “gia hạn” certificate.

### Tình huống C — Leaf hợp lệ, intermediate hết hạn

- `leaf.checkValidity()`: có thể pass.
- `leaf.verify(intermediate.getPublicKey())`: có thể pass.
- PKIX path validation: có thể **fail** vì certificate trong chain không hợp lệ ở thời điểm kiểm tra (trừ các điều kiện/ngoại lệ chính sách được chuẩn hóa).
- Kết luận: không kiểm tra mỗi leaf rồi quên intermediate.

### Tình huống D — Chữ ký không hợp lệ hoặc sai issuer key

- `checkValidity()`: vẫn có thể pass.
- `verify(wrongPublicKey)`: **fail**.
- PKIX path tương ứng: không được chấp nhận.
- Kết luận: validity không chứng minh certificate chưa bị sửa hoặc đúng signer.

### Tình huống E — Chain hợp lệ nhưng sai hostname

- `checkValidity()`: pass.
- `verify(issuerPublicKey)`: pass.
- PKIX path tới trusted root: pass.
- Certificate SAN chứa `files.example.com`, nhưng client gọi `payments.example.com`: **TLS identity check fail**.
- Kết luận: trusted chain không đồng nghĩa đúng peer.

### Tình huống F — Certificate bị thu hồi giữa vòng đời

- `checkValidity()`: có thể pass.
- `verify(issuerPublicKey)`: có thể pass.
- PKIX/TLS với **revocation policy thực thi đầy đủ**: phải xử lý revoked state theo policy.
- Kết luận: thời gian và chữ ký không thay trạng thái thu hồi.

### Tình huống G — Root tự ký và được pin an toàn

- Root certificate có self-signature đúng và được **cấu hình tin cậy độc lập** sau khi kiểm chứng key/fingerprint.
- Path tới root có thể được chấp nhận nếu đáp ứng constraints và chính sách.
- Khi dùng cho HTTPS, vẫn phải kiểm tra SAN hostname và TLS proof of possession.
- Kết luận: root là trust anchor nhờ **quyết định trust có căn cứ**, không nhờ tính chất “tự ký”.

### Tình huống H — Certificate đúng server nhưng application không được cấp quyền

- TLS handshake/certificate validation/hostname đều đúng.
- User gửi request tới resource không được cấp phép.
- Application phải trả authorization denial.
- Kết luận: trust vào server certificate không trao mọi quyền nghiệp vụ cho client.

### Tình huống I — Certificate chain bị kẻ tấn công thay bằng chain họ tự tạo

- Nếu ứng dụng dùng root từ **payload** làm `TrustAnchor`, path có thể “đúng” dưới root attacker.
- Nếu trust anchor chỉ từ config đã xác thực, chain attacker không nối được vào root phù hợp.
- Kết luận: nguồn trust anchor là yếu tố **bất biến trong threat model**.

### Tình huống J — CSR và certificate signing

Một CSR có chữ ký hợp lệ chứng minh thông tin request nhất quán với private key tương ứng, nhưng không tự chứng minh CA đã cấp certificate tin cậy. CSR parsing/verification không đồng nghĩa certificate path validation. Đây là ví dụ tương tự cho sự khác nhau giữa **cryptographic signature verification** và **trust decision**.

## 14. Các anti-pattern cần nhận biết

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ gọi `cert.checkValidity()` rồi “trusted” | Chỉ kiểm tra cửa sổ thời gian | PKIX/trust manager và expected identity |
| Chỉ gọi `cert.verify(cert.getPublicKey())` | Có thể chỉ xác minh self-signature của attacker | Dùng issuer key đúng, validate chain tới anchor tin cậy |
| Ghép các `verify` theo issuer string | Bỏ qua CA constraints, policies, revocation, path issues | Dùng `CertPathValidator/Builder` |
| Root tự ký được gửi trong TLS chain nên tự tin | Attacker có thể gửi root của họ | Trust anchors từ config độc lập |
| Đặt `new TrustAnchor(receivedRoot, null)` | Tin vào nguồn không đáng tin | Dùng pinned/configured CA hợp lệ |
| PKIX pass nhưng bỏ qua SAN hostname | Tin nhầm certificate cho domain khác | Endpoint identification |
| CN khớp nên bỏ qua SAN khác | Quy tắc hiện đại ưu tiên SAN và matching theo chuẩn | Dùng TLS hostname verification chuẩn |
| Dùng `HostnameVerifier` luôn trả true | Mất kiểm tra đúng server | Dùng default verifier |
| TrustManager luôn accept | Mất PKIX authentication, MITM | Dùng trust manager chuẩn |
| Tắt revocation vô thời hạn mà không có policy | Không phát hiện compromised cert sớm | Thiết kế CRL/OCSP/short-lived policy |
| Khóa CA key usage sai nhưng `verify` pass | Signature đúng không cấp quyền làm CA | Kiểm tra BasicConstraints/KeyUsage qua PKIX |
| Leaf certificate CA=false được dùng ký intermediate | Sai mục đích dùng | Không thay PKIX bằng signature-only checks |
| Bỏ ngoại lệ `CertificateExpiredException` | Hết hạn vẫn được chấp nhận | Kiểm soát validity theo policy |
| Bỏ qua `SSLHandshakeException` | Có thể đang bị MITM/cấu hình PKI sai | Chẩn đoán chain/trust/name đúng |
| Certificate chain valid = server sở hữu private key | Chữ ký CA không chứng minh handshake PoP | TLS certificate proof |
| PKIX pass = user được phép gọi API | Trust server khác application authorization | Phân quyền riêng |
| Log toàn certificate/key material và header nhạy cảm | Lộ dữ liệu và khó kiểm soát retention | Chỉ log metadata cần thiết theo policy |

## 15. Checklist kiểm thử cho Java certificate validation

### 15.1. Unit tests

- [ ] Certificate còn hạn: `checkValidity()` pass; expired/notYetValid được phân biệt đúng.
- [ ] Thử `checkValidity(Date)` với thời điểm trước/sau để xác minh logic thời gian, không tự bỏ qua lỗi.
- [ ] `verify(correctIssuerPublicKey)` pass, `verify(wrongIssuerPublicKey)` fail.
- [ ] Certificate self-signed mới tạo nhưng **chưa trust** không được chấp nhận cho server production.
- [ ] Certificate parser X.509 không được nhầm với trust validation.
- [ ] Validator từ chối chain sai ký, thiếu intermediate, vượt path length, CA=false ở vị trí issuer.
- [ ] Critical extensions/KeyUsage/EKU/name constraints được xử lý theo policy áp dụng.
- [ ] Trust anchor được kiểm soát từ cấu hình chứ không copy tùy tiện từ client request.

### 15.2. Integration tests HTTPS/mTLS

- [ ] Valid chain + correct SAN hostname được chấp nhận theo TLS policy.
- [ ] Valid chain + **wrong hostname** bị từ chối.
- [ ] Valid dates + self-signed untrusted bị từ chối.
- [ ] Valid leaf + expired intermediate bị từ chối theo path policy.
- [ ] Revoked certificate bị từ chối khi revocation policy yêu cầu.
- [ ] Server không chứng minh private key phù hợp trong handshake bị từ chối.
- [ ] Expired/replaced root và key rotation được kiểm tra theo hệ thống truststore.
- [ ] Custom truststore không tắt hostname verification và không “trust all”.
- [ ] Client certificate cho mTLS được map sang đúng principal, tenant/role; không cấp quyền chỉ dựa vào TLS succeeded.
- [ ] Thuật toán/chứng thư yếu bị từ chối theo security policy hiện hành.

### 15.3. Operational QA

- [ ] Truststore CA list, lịch cập nhật, quyền thay đổi và audit rõ ràng.
- [ ] Clock/NTP đồng bộ; có cảnh báo certificate sắp hết hạn.
- [ ] Có phương án cấp/rotate certificate và khôi phục nếu intermediate bị thay.
- [ ] Revocation, certificate lifetime và quy tắc soft-fail/hard-fail được thống nhất với threat model.
- [ ] Log lỗi TLS tránh lộ private key, session key, token, request body và plaintext; có correlation ID.
- [ ] Không dùng flag “insecure TLS” hoặc trust-all chỉ để khắc phục một sự cố tạm thời.
- [ ] CA nội bộ và CA công khai có phạm vi tin cậy được phân chia phù hợp.

## 16. Câu hỏi tự kiểm tra

**1. `checkValidity()` pass có chứng minh certificate được CA trusted ký không?**  
Không. Nó chỉ kiểm tra `notBefore/notAfter` của certificate tại một thời điểm.

**2. `leaf.verify(issuer.getPublicKey())` pass có chứng minh issuer nằm trong truststore không?**  
Không. Phép toán chỉ xác minh chữ ký bằng key bạn cung cấp. Key đó có được tin hoặc đủ quyền làm CA không là bài toán khác.

**3. Vì sao certificate tự ký của attacker có thể pass cả `checkValidity` và `verify`?**  
Attacker tự chọn thời hạn và tự ký bằng private key tương ứng với public key trong certificate. Không có trust anchor đã cấu hình hoặc identity binding từ bên ngoài.

**4. Nếu một CA root thật có self-signature đúng, nó được tin chỉ nhờ `verify(root.getPublicKey())`?**  
Không. Trust dựa trên cấu hình/kiểm tra out-of-band; phép tự ký không tự trao thẩm quyền.

**5. Đường chứng thực leaf → intermediate → root nên đưa những phần tử nào vào `CertPath`?**  
Thường là `List.of(leaf, intermediate)`; root được khai báo riêng dưới dạng `TrustAnchor` đã có nguồn tin cậy.

**6. PKIX path validation pass thì HTTPS hostname tự đúng không?**  
Không. Phải so expected service name với certificate identity theo quy tắc endpoint identification; TLS client chuẩn kết hợp các bước này.

**7. Vì sao không lấy root từ gói tin server gửi để tạo `TrustAnchor`?**  
Kẻ tấn công có thể tạo và gửi root của họ; tạo anchor trực tiếp từ input không tin cậy khiến kết quả validator không phản ánh trust từ client.

**8. Certificate còn hạn và chữ ký đúng nhưng bị thu hồi. Hai API nào vẫn có thể pass?**  
`checkValidity()` và `verify(...)` có thể vẫn pass. Revocation cần cơ chế/policy bổ sung.

**9. `BasicConstraints: CA=false` ở certificate intermediate ảnh hưởng điều gì?**  
Nó không được dùng làm CA trung gian theo PKIX hợp lệ; chữ ký toán học đúng không cấp quyền ký chứng thư.

**10. `verify` certificate là bằng chứng server đang giữ private key trong TLS handshake?**  
Không. Certificate signature do issuer tạo; TLS `CertificateVerify`/handshake authentication có vai trò chứng minh private key phù hợp và bind phiên.

**11. Nếu server certificate có SAN `files.example.com` nhưng client muốn `payments.example.com` thì kết luận?**  
Dù chain trusted và time/signature đúng, endpoint identity sai nên phải reject theo chính sách HTTPS.

**12. Có nên bỏ qua lỗi chứng thư trong môi trường production bằng một `TrustManager` chấp nhận mọi certificate không?**  
Không. Nó làm mất authentication kênh và tạo MITM risk; phải sửa truststore, chain, SAN, thời gian hoặc cấu hình hợp lệ.

## 17. Sơ đồ ghi nhớ

```text
                  X.509 CERTIFICATE FROM PEER
                             |
                             v
                checkValidity()?
                   /             \
               time OK       time NOT OK
                 |              reject
                 v
        verify(issuerPublicKey)?
             /              \
        signature OK      mismatch
             |              reject
             v
       PKIX path validation:
       - chain signatures / CA rules
       - constraints / validity / policies
       - trusted configured root
       - revocation as configured
             |
             v
       Endpoint identity:
       - expected HTTPS DNS/IP
       - SAN / protocol matching
             |
             v
       TLS handshake:
       - proof of key possession
       - transcript / Finished
             |
             v
       App authorization:
       - principal, tenant, resource, action
             |
             v
         ACCEPT ONLY IF POLICY SATISFIED

  WARNING: Diagram is a conceptual dependency list.
  Correct PKIX/JSSE validates many elements together;
  do not reimplement the protocol as ad-hoc sequential checks.
```

**Kết luận:** `checkValidity` kiểm tra **thời gian**, `verify` kiểm tra **chữ ký certificate với một public key**, còn “đáng tin” yêu cầu **đường PKIX tới trust anchor được cấu hình từ trước** và các ràng buộc chứng thư/ứng dụng phù hợp. Với HTTPS còn phải xác định **đúng hostname, TLS proof of possession và authorization**. Đừng để việc hai phương thức Java không ném exception bị hiểu nhầm thành “certificate đã được xác thực đáng tin”.

### Tài liệu tham khảo

- RFC 5280 — *Internet X.509 Public Key Infrastructure Certificate and CRL Profile*: https://www.rfc-editor.org/rfc/rfc5280
- RFC 9525 — *Service Identity in TLS* (định danh DNS/IP, name matching): https://www.rfc-editor.org/rfc/rfc9525
- RFC 8446 — *The Transport Layer Security (TLS) Protocol Version 1.3*: https://www.rfc-editor.org/rfc/rfc8446
- RFC 6960 — *X.509 Internet Public Key Infrastructure Online Certificate Status Protocol - OCSP*: https://www.rfc-editor.org/rfc/rfc6960
- Java SE 17, `X509Certificate`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html
- Java SE 17, `Certificate` / `verify(PublicKey)`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/Certificate.html
- Java SE 17, `CertPathValidator`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html
- Java SE 17, `CertPathBuilder`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html
- Java SE 17, `PKIXParameters` / `TrustAnchor`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html
- Java SE 17, `TrustManagerFactory`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/TrustManagerFactory.html
- Java SE 17, `SSLParameters` / endpoint identification: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html
- Java SE 17, `HttpClient`: https://docs.oracle.com/en/java/javase/17/docs/api/java.net.http/java/net/http/HttpClient.html
