# 14.5 Kiểm tra thời gian, ràng buộc CA, độ dài đường dẫn và mục đích sử dụng

Khi xác minh chứng thư X.509, kiểm tra rằng **chữ ký trên mỗi chứng thư đúng về mặt toán học** chỉ là một phần của bài toán. Một đường dẫn chứng thư (*certificate path*, hay *certification path*) còn phải đáp ứng nhiều **ràng buộc về thời gian, vai trò CA, số tầng CA trung gian và mục đích sử dụng khóa/chứng thư**. Nếu bỏ qua các ràng buộc này, ứng dụng có thể tin một chứng thư đã hết hạn, cho phép một chứng thư người dùng ký chứng thư khác, hoặc chấp nhận một chứng thư dùng cho email/code signing làm chứng thư máy chủ HTTPS.

Bài này tập trung vào bốn lớp chính trong **PKIX/X.509**:

1. **Thời gian hiệu lực**: `notBefore`, `notAfter`, thời điểm kiểm chứng và tính nhất quán của đồng hồ.
2. **Ràng buộc CA**: extension `BasicConstraints`, bit `cA` và `KeyUsage.keyCertSign` dành cho tổ chức phát hành.
3. **Độ dài đường dẫn**: `pathLenConstraint` giới hạn số CA trung gian **không tự cấp (non-self-issued)** được phép theo sau một CA, không phải số chứng thư bất kỳ.
4. **Mục đích sử dụng**: `KeyUsage`, `ExtendedKeyUsage` (EKU) như `serverAuth`/`clientAuth`, và kiểm tra danh tính dịch vụ riêng biệt như DNS Subject Alternative Name (*SAN*).

Trong Java 17+, `CertificateFactory` tạo đối tượng chứng thư/`CertPath`, còn `CertPathValidator` với thuật toán `PKIX` và `PKIXParameters` thực hiện phần xác thực đường dẫn theo tham số được cấu hình. **Không được đồng nhất PKIX path validation với toàn bộ HTTPS authentication:** danh tính hostname/SAN, chính sách TLS, revocation và authorization vẫn cần được áp dụng đúng nơi.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

- Đọc, phân tích và kiểm tra `X509Certificate.getNotBefore()`, `getNotAfter()`, `checkValidity(Date)`, `getBasicConstraints()`, `getKeyUsage()` và `getExtendedKeyUsage()`.
- Giải thích sự khác nhau giữa **leaf certificate**, **issuing CA**, **root/trust anchor** và **certificate chain**.
- Xác định vì sao leaf phải được cấp bởi CA có quyền ký certificate và vì sao CA trong path phải tuân `BasicConstraints`, `KeyUsage`, `pathLenConstraint` và các giới hạn khác.
- Tính đúng ý nghĩa của `pathLenConstraint = 0`, phân biệt non-self-issued intermediate CAs với end-entity certificate và hiểu trường hợp trust anchor nằm ngoài path.
- Biết `serverAuth`, `clientAuth`, `codeSigning` và `emailProtection` không thể dùng thay nhau chỉ dựa vào tên thuật toán public key.
- Xây dựng một lab keytool + Java 17 tạo root CA test, leaf được ký, root không liên quan; kiểm PKIX tại thời điểm hiện tại và tương lai.
- Viết negative tests cho hết hạn, chưa tới hiệu lực, thiếu CA flag, keyCertSign sai, path quá sâu, EKU không đúng, SAN sai và issuer không được tin.
- Tránh lỗi tự bỏ qua các extension quan trọng hoặc tắt TLS peer/hostname verification để làm handshake thành công.

## 2. Mô hình PKIX: chứng thư nào nằm ở đâu?

Một ví dụ đường dẫn hợp lệ có thể có dạng:

```text
      Trust anchor được cấu hình bên ngoài đường dẫn
      Root CA (đã được trust)
             |
             | phát hành / ký
             v
      Intermediate CA 1 (CA=true, KU=keyCertSign, pathLen >= ... )
             |
             | phát hành / ký
             v
      Intermediate CA 2 (CA=true, KU=keyCertSign, pathLen >= ... )
             |
             | phát hành / ký
             v
      Leaf certificate của server HTTPS
      (CA=false; EKU=serverAuth; SAN đúng hostname)
```

Trong nhiều triển khai PKIX, `CertPath` truyền cho validator bao gồm **leaf rồi các intermediate theo thứ tự**, và **không bao gồm trust anchor**. Trust anchor được cung cấp riêng trong `PKIXParameters`. Việc trust anchor được tin không phải do nó tự ký đúng hoặc vì có mặt trong một file certificate bất kỳ, mà do **cấu hình tin cậy được kiểm soát** của ứng dụng, hệ điều hành hoặc runtime.

### Tách những bước khác nhau

| Bước | Điều được xác minh | Công cụ Java điển hình |
| --- | --- | --- |
| Parse certificate | Dữ liệu có cú pháp X.509 và có thể dựng thành object | `CertificateFactory.generateCertificate` |
| Dựng đường dẫn | Tìm các issuer/intermediate thích hợp dẫn tới trust anchor | `CertPathBuilder("PKIX")` / nguồn `CertStore` |
| Validate đường dẫn | Chữ ký, thời hạn, BasicConstraints, CA usage, path length, policies/name constraints và quy tắc PKIX đã cấu hình | `CertPathValidator("PKIX")` + `PKIXParameters` |
| Xác minh TLS endpoint | Certificate phải đại diện cho **đúng DNS/IP đích**, mục đích TLS server/client và chính sách handshake | JSSE/`X509ExtendedTrustManager`/endpoint identification |
| Thu hồi và chính sách vận hành | OCSP/CRL, distrust, algorithm constraints, truststore updates | PKIX revocation checker/JSSE/security policy |
| Authorization nghiệp vụ | Client/user/tenant có quyền làm hành động này hay không | Application authz/RBAC/ABAC |

**Không dùng** `certificate.verify(issuerPublicKey)` hoặc `certificate.checkValidity()` đơn độc để quyết định “đã tin cậy”. Hai API đó chỉ kiểm một mảnh cụ thể của bài toán.

## 3. Kiểm tra thời gian: notBefore và notAfter

Mỗi certificate X.509 có một khoảng hiệu lực:

```text
notBefore -------------------------- notAfter
           ^ t_valid
```

Tại thời điểm `t_valid`, cần xét khoảng thời gian hợp lệ theo quy tắc PKIX/ứng dụng. Certificate có `t_valid` nằm trước `notBefore` là **chưa có hiệu lực**; nằm sau `notAfter` là **đã hết hạn**. `X509Certificate.checkValidity(Date date)` có thể ném `CertificateNotYetValidException` hoặc `CertificateExpiredException` khi không hợp lệ tại thời điểm chỉ định.

Một certificate được ký bằng thuật toán mạnh và bởi CA đáng tin vẫn **không được chấp nhận làm chứng thư hiện tại** nếu thời gian sử dụng vượt khoảng hiệu lực theo policy.

### Java API và thời điểm kiểm tra

Đoạn sau là **mã minh họa trong method** đã có `X509Certificate certificate`, không phải chương trình độc lập:

```java
Date notBefore = certificate.getNotBefore();
Date notAfter  = certificate.getNotAfter();
certificate.checkValidity(new Date());
```

Đối với path validation, `PKIXParameters.setDate(Date)` cho phép chọn thời điểm mà validator dùng để đánh giá validity của các certificates trong đường dẫn:

```java
PKIXParameters params = new PKIXParameters(trustedAnchors);
params.setDate(Date.from(Instant.now()));
CertPathValidator.getInstance("PKIX").validate(certPath, params);
```

Đây là đoạn minh họa, giả sử `trustedAnchors` là tập `TrustAnchor` được kiểm soát, `certPath` đã được xây đúng cấu trúc và các import/checked exceptions đã được xử lý. **Các cấu hình khác** (đặc biệt revocation, policies, algorithm constraints) vẫn phải được thiết kế theo threat model.

### Các lưu ý tinh tế về thời gian

1. **Kiểm toàn đường dẫn, không chỉ leaf.** Issuing CA/intermediate nằm trong `CertPath` cũng có thời hạn. Việc root trust anchor được xem là đầu vào tin cậy **bên ngoài path** có thể khiến một số extension/validity của chính root không được kiểm giống như chứng thư trong path; cần chính sách quản trị và loại bỏ trust anchors không còn hợp lệ/được phép.
2. **Đồng hồ phải đáng tin.** VM/container có clock lệch, NTP lỗi, timezone nhầm hoặc đồng hồ bị rollback có thể làm chứng thư hợp lệ bị từ chối hoặc chứng thư hết hạn được chấp nhận nhầm. Thời gian X.509 về bản chất là thời điểm tuyệt đối, không phải lấy giờ địa phương của người dùng để tùy ý tính.
3. **Không tắt validity check** chỉ vì certificate hết hạn. Cần renew/reissue hoặc xử lý migration được phê duyệt, không thêm ngoại lệ vô hạn trong code.
4. **Không nhầm thời điểm hiện tại với historical validation.** Kiểm chữ ký đã phát sinh trong quá khứ, long-term signature validation hay timestamp authority có quy tắc riêng về chứng cứ thời gian và trạng thái revocation. Đừng chỉ setDate về ngày cũ do user đưa vào rồi coi chứng thư hiện tại tin được.
5. **Certificate bị thu hồi có thể chưa hết hạn.** `notAfter` không đại diện cho revocation. Ngược lại, certificate hết hạn không được xem là hợp lệ chỉ vì OCSP nói “good” tại một thời điểm khác.
6. **Cập nhật clock và CA chain** phải đồng bộ giữa các node. Một node lệch giờ có thể báo handshake lỗi khác dù cùng truststore.

### Trường hợp minh họa

| Thời điểm kiểm tra | Certificate | Kết quả kỳ vọng |
| --- | --- | --- |
| Trước `notBefore` | Chưa tới hiệu lực | Reject |
| Trong khoảng `notBefore...notAfter` | Hợp lệ về **thời gian** | Có thể đi tiếp; chưa tự tin cả chain |
| Sau `notAfter` | Hết hạn | Reject cho xác thực TLS hiện tại |
| Trong khoảng nhưng issuer đã bị distrust | Leaf vẫn còn hạn | Reject theo trust policy |
| Trong khoảng nhưng KU/EKU sai | Leaf vẫn còn hạn | Reject cho mục đích không được phép |
| Trong khoảng nhưng hostname SAN khác | Certificate vẫn còn hạn | Reject khi kiểm TLS endpoint |

Trong lab cuối bài, leaf được cấp với validity 90 ngày. Test ở hiện tại thành công và test tại **120 ngày sau** thất bại, dù root được cấp 365 ngày. Đây là phép thử tách biệt yếu tố **validity của leaf** khỏi việc root đã được tin.

## 4. BasicConstraints: ai được phép làm CA?

Extension `BasicConstraints` có hai phần logic:

- `cA`: chứng thư public key này có thuộc về một CA được phép phát hành certificate trong cấu trúc đường dẫn hay không.
- `pathLenConstraint`: nếu có, giới hạn số **non-self-issued intermediate CA certificates** có thể theo sau trong một đường dẫn hợp lệ.

Một issuing CA nằm trong đường chứng thư phải được đánh giá với `BasicConstraints` tương ứng, có chứng thư được phép ký certificate và có các ràng buộc phù hợp. Với các profile chuẩn hiện đại, BasicConstraints của CA certificate nên được đánh dấu **critical** theo RFC 5280. Nếu một extension critical không thể được hiểu hoặc xử lý, validation phải từ chối, không bỏ qua như thông tin trang trí.

### Java: getBasicConstraints()

`X509Certificate.getBasicConstraints()` trả:

- **`-1`** nếu certificate **không** phải CA theo BasicConstraints.
- Giá trị **`>= 0`** nếu CA có `pathLenConstraint` hữu hạn, chẳng hạn 0 hoặc 2.
- Một số nguyên rất lớn (ví dụ `Integer.MAX_VALUE` theo JDK API) khi certificate là CA mà **không có giới hạn pathLenConstraint được công bố**.

Vì thế, **`getBasicConstraints() == 0` không có nghĩa “đây là leaf”**. Ngược lại, `0` biểu thị certificate **là CA**, nhưng không cho phép một non-self-issued intermediate CA ở dưới nó trong path đã cho (trừ các ngoại lệ self-issued theo quy tắc PKIX).

Ví dụ:

```text
Leaf end entity:   getBasicConstraints() = -1
Intermediate CA:   getBasicConstraints() = 0  (có thể ký trực tiếp leaf)
Intermediate CA:   getBasicConstraints() = 1  (có thể có 1 non-self-issued CA dưới)
CA không giới hạn: getBasicConstraints() = rất lớn theo provider/API
```

Đây là mô tả ý nghĩa phổ biến; việc đếm thật phải theo thuật toán PKIX, có ngoại lệ self-issued và các constraints khác. Không tự viết path validator chỉ bằng phép so sánh integer.

### Không đủ nếu chỉ kiểm CA=true

Một CA certificate còn cần:

- Chữ ký từ issuer được phép hoặc là trust anchor được cấu hình đúng.
- `KeyUsage` cho phép ký certificate khi extension đó hiện diện.
- Thời hạn và thuật toán hợp lệ.
- `pathLenConstraint`, name constraints, certificate policies và các critical extensions được áp dụng đúng.
- Thứ tự và liên kết `issuer/subject`, signature verification và key usage phù hợp.

Đừng chấp nhận certificate `CA=true` do user upload và tự thêm nó thành trust anchor. **Niềm tin là chính sách bên ngoài**, không phải một boolean tự tuyên bố.

## 5. pathLenConstraint: độ dài đường dẫn không phải số certificate bất kỳ

Đây là một trong những phần dễ hiểu sai nhất của PKIX.

Nếu một CA certificate có `pathLenConstraint=0`, CA đó vẫn có thể ký **end-entity/leaf certificates**. Giá trị 0 chỉ không cho phép **non-self-issued intermediate CA certificates tiếp theo** nằm dưới nó trong đường dẫn theo quy tắc được áp dụng.

### Ví dụ trực quan

```text
Case A — được phép bởi quy tắc pathLen của CA A:

Trust anchor
    |
   CA A [pathLen=0]
    |
   Leaf service.example.test

    Non-self-issued intermediate CA dưới CA A: 0


Case B — vi phạm pathLen=0 của CA A:

Trust anchor
    |
   CA A [pathLen=0]
    |
   CA B [CA=true, non-self-issued]
    |
   Leaf service.example.test

    Non-self-issued intermediate CA dưới CA A: 1 > 0
```

Nếu `CA A` là **trust anchor được cung cấp trực tiếp** chứ không phải certificate nằm trong `CertPath`, một số constraints ghi trong **certificate đại diện cho trust anchor** không nhất thiết được PKIX validation xử lý như constraints của CA trong path. Đây là khác biệt quan trọng! Để kiểm path length trong lab thực sự, hãy đặt CA cần kiểm là **intermediate certificate trong path**, không chỉ lấy một root trusted có `pathLen=0` rồi suy rằng JCA sẽ áp hạn đó lên mọi chain.

### Các yếu tố ảnh hưởng phép đếm

- Đếm **CA trung gian không tự cấp** bên dưới CA đang bị giới hạn, không tính end entity.
- Các **self-issued certificates** có quy tắc xử lý đặc biệt; self-issued không đồng nghĩa tự ký (*self-signed*) trong mọi trường hợp. Đừng tự coi certificate subject=issuer là bằng chứng cryptographic tự ký.
- Path length giới hạn **hệ phân cấp CA**, không phải hạn chế mạng “chỉ 3 hops” hay kích thước byte certificate.
- Một CA có `pathLenConstraint=1` có thể cho phép một non-self-issued CA tiếp theo dưới nó, rồi leaf; nhưng những constraints khác có thể thu hẹp thêm.
- Root/trust anchor có thể được cấu hình bên ngoài path. Đừng lấy giá trị `getBasicConstraints()` của root và tự giả định validator luôn dùng nó như ràng buộc của CA trung gian.
- Name constraints, certificate policies, trust-anchor constraints và các quy tắc algorithm/revocation có thể tiếp tục khiến path bị từ chối dù số CA trung gian nằm trong giới hạn.

### Cấu hình path length khi tạo CA thử nghiệm

Với `keytool` trong JDK phù hợp, CA certificate có thể được tạo với extension:

```text
-ext BC:critical=ca:true,pathlen:0
```

Đây là **một đối số keytool**. Nếu CA này phát hành trực tiếp leaf thì không có intermediate dưới CA. Nếu thử tạo thêm CA B và dựng path qua CA B, cần để **CA A nằm trong CertPath**, không chỉ làm trust anchor, để kiểm chứng `pathLenConstraint` tại vị trí mong muốn.

## 6. KeyUsage: key được phép thực hiện phép toán gì?

Extension `KeyUsage` là bit string chỉ định những chức năng được phép cho public key trong certificate. Đừng đánh đồng việc key toán học **có thể** verify signature với việc certificate **được phép** đóng vai trò CA hoặc dùng cho TLS.

Các bit thường gặp:

| Bit / tên | Ý nghĩa điển hình |
| --- | --- |
| `digitalSignature` | Phục vụ xác minh chữ ký số trong ngữ cảnh được cho phép |
| `nonRepudiation` / `contentCommitment` | Ràng buộc nội dung theo profile; không tự bảo đảm thuộc tính pháp lý |
| `keyEncipherment` | Mã hóa/bọc khóa trong giao thức thích hợp |
| `dataEncipherment` | Mã hóa dữ liệu theo profile cũ/cụ thể |
| `keyAgreement` | Tham gia thiết lập bí mật chung bằng key agreement |
| `keyCertSign` | **Ký chứng thư** khi certificate là CA |
| `cRLSign` | Ký certificate revocation list |
| `encipherOnly` / `decipherOnly` | Cùng với keyAgreement và quy tắc tương ứng |

Java `X509Certificate.getKeyUsage()` trả mảng `boolean[]`; các vị trí cố định theo chuẩn:

```text
index 0 digitalSignature
index 1 nonRepudiation / contentCommitment
index 2 keyEncipherment
index 3 dataEncipherment
index 4 keyAgreement
index 5 keyCertSign
index 6 cRLSign
index 7 encipherOnly
index 8 decipherOnly
```

Nếu extension không hiện diện, `getKeyUsage()` có thể trả **null**. Không truy cập thẳng `getKeyUsage()[5]` trong một trình kiểm chứng generic trước khi kiểm null/độ dài; code lab ở mục 10 truy cập vì **chính lab chủ động phát hành certificate có extension đó**.

### CA cần điều gì để ký certificate?

Đối với một intermediate CA trong path:

- BasicConstraints phải chỉ rõ vai trò CA theo quy tắc PKIX.
- Nếu KeyUsage hiện diện, bit `keyCertSign` phải cho phép ký chứng thư.
- Certificate phải có chữ ký/issuer/path hợp lệ.
- Các hạn chế khác, gồm path length, name constraints, validity, policies, vẫn phải được áp dụng.

**Không** chỉ nhìn `keyCertSign=true` mà bỏ qua `CA=false`. Ngược lại, `CA=true` cùng `KeyUsage` **không** cho phép `keyCertSign` cũng không đủ cho issuing CA trong path. Cần đánh giá **kết hợp**.

### Leaf KeyUsage phụ thuộc TLS mode

Trong TLS hiện đại, leaf certificate thường cần `digitalSignature` cho các thao tác authentication bằng chữ ký. Trong các profile/giao thức lịch sử, một số key/cipher suite yêu cầu `keyEncipherment` hoặc `keyAgreement`. Không áp một công thức độc lập với protocol/version/algorithm cho mọi chứng thư.

Với một RSA public key, có thể verify chữ ký về mặt toán học; nhưng nếu certificate chỉ được cấp cho mục đích khác theo KeyUsage/EKU, ứng dụng **không được** diễn giải nó là TLS server certificate hợp lệ bất chấp policy.

## 7. ExtendedKeyUsage (EKU): mục đích ứng dụng

**EKU** là một tập OID mở rộng phân loại mục đích sử dụng certificate, điển hình:

| Mục đích | OID | Ví dụ |
| --- | --- | --- |
| `serverAuth` | `1.3.6.1.5.5.7.3.1` | Xác thực TLS server |
| `clientAuth` | `1.3.6.1.5.5.7.3.2` | Xác thực TLS client khi mTLS |
| `codeSigning` | `1.3.6.1.5.5.7.3.3` | Ký phần mềm/code |
| `emailProtection` | `1.3.6.1.5.5.7.3.4` | Bảo vệ email |
| `timeStamping` | `1.3.6.1.5.5.7.3.8` | Ký timestamp theo quy tắc dịch vụ |
| `OCSPSigning` | `1.3.6.1.5.5.7.3.9` | Ký OCSP responses theo profile |

Trong Java, `X509Certificate.getExtendedKeyUsage()` trả danh sách `List<String>` OIDs hoặc `null` khi extension không có. Sự **không hiện diện** không có một kết quả allow/deny phổ quát cho mọi ứng dụng; cần áp chính sách của protocol/CA profile/TLS stack. Khi extension có mặt, intended usages phải được kiểm theo RFC/ứng dụng. Các OID chung như `anyExtendedKeyUsage` có semantics đặc thù; không lấy đó làm giấy phép bỏ kiểm mục đích.

### Vì sao KeyUsage và EKU cần kết hợp?

Một leaf có:

```text
BasicConstraints: CA=false
KeyUsage: digitalSignature
ExtendedKeyUsage: serverAuth
SubjectAlternativeName: DNS:service.example.test
```

là một **hồ sơ thích hợp làm điểm khởi đầu** cho TLS server certificate trong ngữ cảnh phù hợp, nhưng vẫn phải có chain đáng tin, thời gian hợp lệ, algorithm constraints, revocation/distrust policy và **hostname thật sự khớp SAN**.

Nếu leaf có `EKU=clientAuth` nhưng endpoint đang dùng nó làm TLS server, phải từ chối theo TLS server policy. Nếu leaf có `EKU=codeSigning`, không dùng nó như TLS server certificate chỉ vì cùng thuật toán RSA/ECDSA.

**Mục đích không thay thế identity:** `serverAuth` nói loại tác vụ, **không** nói tên DNS nào được phép. `SAN`/endpoint identification là bước riêng. Bên nhận chứng thư mTLS client cũng cần map danh tính certificate đã được xác thực sang principal/tenant có quyền.

### Một cảnh báo về API

Gọi `cert.getExtendedKeyUsage()` và tự so OID trong một demo cho thấy **cách đọc dữ liệu**; nó **không đồng nghĩa** code đã thực hiện toàn bộ JSSE TLS server authentication. Trong sản phẩm thật, dùng `X509ExtendedTrustManager`/TLS stack hoặc API được audit để bảo đảm EKU, KU và hostname được kiểm **đúng giao thức**.

## 8. Name Constraints và certificate policies: những ràng buộc không được bỏ qua

Dù tên bài tập trung vào thời gian, CA, path length và usage, một path validator chuẩn còn xử lý các extension quan trọng khác.

**Name Constraints:** CA có thể bị giới hạn phạm vi định danh được phép phát hành cho những chứng thư phía dưới, chẳng hạn tập DNS/email/IP đã quy định. Chúng thường xuất hiện trong intermediate CA và phải được áp dụng theo thuật toán PKIX. **Không** thay thế bằng một phép so sánh `String.endsWith()` đơn giản: DNS suffix, punycode, wildcard, Unicode và matching rules có các chi tiết bảo mật.

**Certificate Policies / policy constraints:** CA/certificate có thể mang OID về chính sách cấp phát, explicit policy, mapping và ràng buộc inhibit; ứng dụng có threat model đặc biệt có thể yêu cầu OID nhất định. Một path có chữ ký đúng và root trusted **vẫn có thể bị loại** nếu policy yêu cầu không đáp ứng.

**Critical extensions:** RFC 5280 yêu cầu không bỏ qua critical extension mà path processing không hiểu. Nếu tự viết “verify chữ ký rồi chấp nhận” bằng cách chỉ gọi `PublicKey` và `Signature`, bạn bỏ qua BasicConstraints, KU, path length, name constraints và những extension có tính bắt buộc khác. Hãy dùng PKIX engine đã được duy trì.

## 9. Java API: đọc metadata và xác minh PKIX là hai việc khác nhau

Các API chính:

| Java API | Vai trò | Điểm cần lưu ý |
| --- | --- | --- |
| `CertificateFactory.getInstance("X.509")` | Parse X.509 DER/PEM thích hợp, tạo `CertPath` | Parse không lập trust |
| `X509Certificate.checkValidity(Date)` | Kiểm thời hạn một certificate | Không kiểm chain hay hostname |
| `X509Certificate.getBasicConstraints()` | Đọc CA/pathLen metadata | `-1` là non-CA; root anchor có semantics đặc biệt |
| `X509Certificate.getKeyUsage()` | Đọc KeyUsage bitset | Nullable, thứ tự bit chuẩn |
| `X509Certificate.getExtendedKeyUsage()` | Đọc EKU OIDs | Nullable; cần protocol-specific policy |
| `CertPathBuilder.getInstance("PKIX")` | Tìm path tới trust anchor theo tham số và certificate sources | Path xây được không thay endpoint identification |
| `CertPathValidator.getInstance("PKIX")` | Validate path đã được dựng | Cần trusted anchors, date, revocation/policy |
| `PKIXParameters` | Cấu hình trust anchors, thời điểm, revocation, cert stores, policy | Không lấy trust anchors từ user request |
| `TrustAnchor` | Đại diện root/trust anchor tin cậy | Anchor được cấu hình ngoài path; không tự suy trust từ certificate |
| `PKIXCertPathChecker` | Mở rộng xử lý path theo chuẩn API | Không viết custom checker để bỏ qua validation |
| `X509ExtendedTrustManager` | TLS chain validation với context socket/engine | Gắn với JSSE để có protocol context |

Ví dụ đọc metadata (mã minh họa, không độc lập):

```java
int basic = cert.getBasicConstraints();
boolean isCa = basic >= 0;

boolean[] ku = cert.getKeyUsage();
boolean canSignCertificates = ku != null && ku.length > 5 && ku[5];

List<String> eku = cert.getExtendedKeyUsage();
boolean explicitServerAuth = eku != null
        && eku.contains("1.3.6.1.5.5.7.3.1");

cert.checkValidity(new Date());
```

Cần import `java.util.List`, `java.util.Date` và giả sử `X509Certificate cert` có sẵn; một số lời gọi ném checked exceptions. **Đây là kiểm metadata riêng lẻ**, không thay `PKIX` path validation hoặc TLS endpoint verification. Việc `getBasicConstraints() >= 0` không chứng minh CA là một issuer được policy cấp quyền.

## 10. Lab Java 17+ tự tạo root, leaf và thử xác minh

Đây là một lab **hoàn toàn dùng keytool + JDK 17+**, không cần website hoặc certificate của đối tác. Chúng ta tạo:

- `root.pem`: self-signed **test root CA** RSA 2048, `BasicConstraints CA=true, pathLen=0`, `KeyUsage keyCertSign,cRLSign`, hiệu lực 365 ngày.
- `leaf.pem`: chứng thư dịch vụ `service.example.test` ký bởi root, hiệu lực 90 ngày, `CA=false`, `KeyUsage digitalSignature`, `EKU serverAuth`, `SAN DNS:service.example.test`.
- `other.pem`: một **test root khác** không ký leaf.

Java tạo một `CertPath` chỉ chứa leaf, cấu hình root làm trust anchor, validate tại ngày hiện tại và tại 120 ngày sau. Test root không liên quan phải thất bại. **Root pathLen=0 trong lab được đọc/hiển thị nhưng không được coi là phép thử thực thi pathLenConstraint cho intermediate**, vì root ở đây là trust anchor nằm ngoài `CertPath`.

### 10.1 Sinh certificate lab bằng keytool

Chạy trong **thư mục thử nghiệm riêng, không phải thư mục chứa keystore sản xuất**. Các key/password được sinh chỉ phục vụ lab. Mật khẩu `changeit` bên dưới là **mật khẩu demo công khai, tuyệt đối không dùng cho khóa hoặc môi trường thật**. Trong production, dùng prompt/secret manager thay vì password trên command line.

Các lệnh sau chạy với **bash/POSIX shell** (mỗi `\` cuối dòng là tiếp dòng):

```bash
# Root CA thử nghiệm, ký certificate và CRL, pathLenConstraint=0
keytool -genkeypair -alias root -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=Training Root CA" \
  -validity 365 -ext "BC:critical=ca:true,pathlen:0" \
  -ext "KU:critical=keyCertSign,cRLSign" \
  -keystore root.p12 -storetype PKCS12 \
  -storepass changeit -keypass changeit -noprompt

keytool -exportcert -rfc -alias root \
  -keystore root.p12 -storepass changeit -file root.pem

# Sinh keypair riêng cho leaf, tạo CSR
keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=service.example.test" \
  -validity 90 -keystore leaf.p12 -storetype PKCS12 \
  -storepass changeit -keypass changeit -noprompt

keytool -certreq -alias leaf -keystore leaf.p12 \
  -storepass changeit -file leaf.csr

# Root ký certificate leaf với KU/EKU/SAN theo profile lab
keytool -gencert -alias root -keystore root.p12 \
  -storepass changeit -infile leaf.csr -outfile leaf.pem \
  -rfc -validity 90 -ext "BC:critical=ca:false" \
  -ext "KU:critical=digitalSignature" \
  -ext "EKU=serverAuth" \
  -ext "SAN=dns:service.example.test"

# Root khác, không ký leaf: đối chứng âm
keytool -genkeypair -alias other -keyalg RSA -keysize 2048 \
  -sigalg SHA256withRSA -dname "CN=Unrelated Root CA" \
  -validity 365 -ext "BC:critical=ca:true,pathlen:0" \
  -ext "KU:critical=keyCertSign,cRLSign" \
  -keystore other.p12 -storetype PKCS12 \
  -storepass changeit -keypass changeit -noprompt

keytool -exportcert -rfc -alias other \
  -keystore other.p12 -storepass changeit -file other.pem
```

Nếu chạy PowerShell, nhập mỗi lệnh thành một dòng hoặc dùng cú pháp tiếp dòng PowerShell phù hợp; **không** dán dấu `\` POSIX ở cuối dòng. Không import các root thử nghiệm này vào `cacerts`/truststore sản xuất. Xóa toàn bộ test key files theo chính sách sau lab. Các file `root.p12`/`leaf.p12`/`other.p12` có **private key demo**, còn `root.pem`/`leaf.pem`/`other.pem` chỉ là public certificates.

### 10.2 Java source độc lập

Lưu thành **`PkixPolicyDemo.java`** trong **cùng thư mục** chứa ba certificate PEM vừa tạo:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.time.Instant;
import java.time.temporal.ChronoUnit;
import java.util.Date;
import java.util.List;
import java.util.Set;

public class PkixPolicyDemo {
    static X509Certificate readCertificate(String name) throws Exception {
        try (var stream = Files.newInputStream(Path.of(name))) {
            return (X509Certificate) CertificateFactory
                    .getInstance("X.509").generateCertificate(stream);
        }
    }

    static boolean validate(CertPath path, X509Certificate root, Date at)
            throws Exception {
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        params.setRevocationEnabled(false); // Lab only.
        params.setDate(at);
        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return true;
        } catch (CertPathValidatorException ex) {
            return false;
        }
    }

    static boolean hasDnsSan(X509Certificate cert, String name)
            throws Exception {
        var sans = cert.getSubjectAlternativeNames();
        if (sans == null) return false;
        for (var entry : sans) {
            if (Integer.valueOf(2).equals(entry.get(0))
                    && name.equals(entry.get(1))) {
                return true;
            }
        }
        return false;
    }

    public static void main(String[] args) throws Exception {
        X509Certificate root = readCertificate("root.pem");
        X509Certificate leaf = readCertificate("leaf.pem");
        X509Certificate unrelated = readCertificate("other.pem");
        CertPath path = CertificateFactory.getInstance("X.509")
                .generateCertPath(List.of(leaf));

        System.out.println("Root is CA: " + (root.getBasicConstraints() >= 0));
        System.out.println("Root pathLenConstraint: " + root.getBasicConstraints());
        System.out.println("Root keyCertSign: " + root.getKeyUsage()[5]);
        System.out.println("Leaf is CA: " + (leaf.getBasicConstraints() >= 0));
        System.out.println("Leaf digitalSignature: " + leaf.getKeyUsage()[0]);
        System.out.println("Leaf serverAuth EKU: " + leaf.getExtendedKeyUsage()
                .contains("1.3.6.1.5.5.7.3.1"));
        System.out.println("Expected DNS SAN present: " +
                hasDnsSan(leaf, "service.example.test"));
        System.out.println("Path valid today: " +
                validate(path, root, Date.from(Instant.now())));
        System.out.println("Path valid after 120 days: " +
                validate(path, root,
                        Date.from(Instant.now().plus(120, ChronoUnit.DAYS))));
        System.out.println("Path with unrelated root valid: " +
                validate(path, unrelated, Date.from(Instant.now())));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 PkixPolicyDemo.java
java PkixPolicyDemo
```

**Stdout đã kiểm chứng trong lab sử dụng các lệnh phía trên:**

```text
Root is CA: true
Root pathLenConstraint: 0
Root keyCertSign: true
Leaf is CA: false
Leaf digitalSignature: true
Leaf serverAuth EKU: true
Expected DNS SAN present: true
Path valid today: true
Path valid after 120 days: false
Path with unrelated root valid: false
```

**Điều kiện của output:** các chứng thư phải vừa được tạo tại thời điểm chạy lab, provider/JDK hỗ trợ các extension/algorithm trong keytool và không có policy bảo mật bổ sung chặn RSA-2048/SHA256withRSA. Với chứng thư cũ được giữ trên disk đến sau 90 ngày, dòng `Path valid today` sẽ thay đổi — đó là hành vi đúng của validity check. Trên provider hoặc security policy khác, các tập constraints có thể làm validate thất bại. **Không** coi output là một chuỗi cố định cho mọi thời điểm và mọi runtime.

### 10.3 Vì sao từng dòng xuất hiện?

1. `Root is CA: true` vì root được tạo với `BasicConstraints.cA=true`.
2. `Root pathLenConstraint: 0` là metadata của root. Trong test này root là **TrustAnchor**, không phải intermediate trong path; đó **không phải bằng chứng** validator đã áp pathLen=0 lên một intermediate chain.
3. `Root keyCertSign: true` là `KeyUsage` bit 5 do keytool cấp cho root.
4. `Leaf is CA: false` vì leaf có `BasicConstraints.cA=false`; `getBasicConstraints()` trả `-1`.
5. `Leaf digitalSignature: true` là KU bit 0.
6. `Leaf serverAuth EKU: true` là đọc EKU OID `1.3.6.1.5.5.7.3.1`. **Chỉ đọc OID**, chưa phải một phép thử TLS handshake.
7. `Expected DNS SAN present: true` là tìm **chuỗi literal** trong SAN của chứng thư do lab tạo. Nó không thay thế hostname verification của JSSE cho mọi loại DNS/IP, wildcard hoặc IDN.
8. `Path valid today: true` vì leaf vừa được cấp, chữ ký từ đúng root anchor, profile hợp lệ trong điều kiện lab, revocation checking đã **tắt rõ ràng cho lab**.
9. `Path valid after 120 days: false` vì leaf chỉ được cấp 90 ngày; root 365 ngày. Việc kiểm path bị từ chối tại mốc tương lai vì validity của leaf.
10. `Path with unrelated root valid: false` vì root thứ hai không ký leaf và không có đường phù hợp tới anchor ấy.
11. `validate` chỉ bắt `CertPathValidatorException` để chuyển validation failure thành `false`. Lỗi I/O, parse, provider, sai cấu hình hoặc lỗi chương trình vẫn được truyền ra; không nên đánh đồng mọi exception với “certificate không đáng tin”.
12. `hasDnsSan` chỉ phục vụ bài học; toàn bộ chứng thư trong production phải được xác minh bằng TLS endpoint identification chính quy và chính sách CA được cấu hình an toàn.

### 10.4 Điểm bảo mật cố ý giới hạn

`PKIXParameters.setRevocationEnabled(false)` là thiết lập **chỉ phục vụ lab offline không có CRL/OCSP**. Nó **không** phải mẫu cấu hình production. Việc bật/tắt revocation và hành vi khi OCSP/CRL không truy cập được phải do threat model, policy và infrastructure quyết định.

Root CA do `keytool` sinh là **root tự ký mới**. Chỉ tin nó trong lab vì chúng ta chủ động cấu hình `TrustAnchor(root, null)`. Chữ ký tự ký hợp lệ hoặc tên `Training Root CA` không làm root đáng tin với các ứng dụng khác. **Đừng import** các root này vào default `cacerts`.

`CertificateFactory.generateCertPath(List.of(leaf))` tạo một path đã được biết trước. Với chain nhiều intermediate và path xây dựng từ certificate store, nên dùng `CertPathBuilder`/`CertStore` hoặc JSSE/TLS stack được duy trì, không tự đoán issuer từ subject string.

## 11. Thử thực thi pathLenConstraint cho intermediate đúng cách

Lab chính kiểm thời gian, CA metadata, KU/EKU và trust anchor. Muốn thử pathLenConstraint một cách **thực sự**, xây chain có ít nhất một intermediate:

```text
Root R           (TrustAnchor; ngoài CertPath)
   |
   v
Intermediate A   (BasicConstraints CA=true, pathLenConstraint=0)
   |
   +--> Leaf L1  (CA=false)        : depth OK
   |
   +--> Intermediate B (CA=true, non-self-issued)
                |
                +--> Leaf L2       : vượt pathLen A=0
```

Thiết kế test:

1. Sinh root R test, import vào trust anchors của validator (chỉ test).
2. Sinh CA A có `CA=true, pathLen=0, KU=keyCertSign`, ký bởi root R.
3. Sinh leaf L1 ký trực tiếp bởi A. Validate `[L1,A]` với R anchor: nếu mọi điều kiện khác hợp lệ, **pathLen riêng của A** cho phép vì dưới A không có non-self-issued CA.
4. Sinh intermediate CA B có `CA=true` ký bởi A và leaf L2 ký bởi B.
5. Validate `[L2,B,A]` với R anchor: trong trường hợp không có ngoại lệ self-issued và các test cert được tạo bình thường, **pathLen A=0 bị vi phạm**.
6. Làm một test đối chứng `A.pathLen=1` để xác minh path `[L2,B,A]` không bị loại vì path length (các constraints còn lại vẫn phải đúng).
7. Test một intermediate bị thiếu `BasicConstraints CA=true` hoặc thiếu `KeyUsage.keyCertSign` trong khi KU hiện diện: path có thể được ký đúng về mặt RSA/ECDSA nhưng **vẫn phải bị từ chối** vì CA không được phép ký chứng thư.
8. Đừng đặt A làm `TrustAnchor` khi muốn test ràng buộc của chính chứng thư A trong path; cách đó có thể bỏ qua việc kiểm constraints của trust anchor certificate như một intermediate.

Bài tập này cần **test certificates có chủ đích**, không thể kết luận từ một giá trị `getBasicConstraints()` duy nhất. Ưu tiên thư viện/PKIX engine chuẩn để xử lý non-self-issued CA counting, self-issued exceptions, name constraints và certificate policies.

## 12. Kiểm mục đích TLS server/client theo đúng tầng

Một handshake HTTPS không chỉ hỏi “có path từ leaf lên trusted root?” mà còn:

```text
Peer sends leaf + intermediate(s)
         |
         v
Build & validate PKIX path
         |
         v
Check server/client TLS certificate profile
  - KU appropriate for handshake/algorithm
  - EKU appropriate: serverAuth vs clientAuth
  - algorithm/key sizes/sig schemes allowed
         |
         v
Check endpoint identity (hostname/IP in SAN)
         |
         v
Check revocation/distrust policies as configured
         |
         v
TLS authentication success
         |
         v
Application authorization still required
```

Thứ tự xử lý thực tế có thể khác giữa TLS provider/handshake, nhưng **các kiểm soát cần thiết không được bị bỏ sót**.

### HTTPS client

Ví dụ client kết nối `https://api.example.test`. Server có thể trình leaf chứa:

```text
SAN DNS: api-other.example.test
EKU: serverAuth
CA/path: valid to a trusted root
```

Mặc dù chain và EKU có thể đúng, **hostname không khớp** nên phải từ chối kết nối. Không dùng `getSubjectX500Principal().getName().contains("api")` để tự xác minh tên. Với HTTPS, sử dụng endpoint identification theo TLS stack, bao gồm xử lý wildcard và IDN theo chuẩn được hỗ trợ.

### mTLS server xác thực client

Trong mTLS, server kiểm client certificate với CAs được phép và policy khác:

- Leaf phù hợp `clientAuth` và KU của TLS profile.
- Đường chứng thư hợp lệ tới trust anchor dành riêng cho client identities.
- Danh tính client trong SAN/Subject theo profile được cấp và ánh xạ đến principal tin cậy.
- **Authorization** quyết định principal có quyền làm API action, tenant/resource nào.

Thêm một CA public vào truststore dùng cho mTLS client authentication có thể mở rộng khả năng một số client certificates được chấp nhận ngoài ý định. Chỉ trust đúng issuer CAs và profile mà hệ thống cấp phép.

### Code signing và email

Một certificate có `EKU=codeSigning` hoặc `emailProtection` không tự hợp lệ làm TLS server. Các trust anchor/policy dành cho ký phần mềm/email cũng có thể khác root trust cho HTTPS. Đừng dùng một truststore chung không kiểm soát mục đích chỉ vì đều là X.509.

## 13. Thời hạn của CA và trust anchor: phân biệt policy và PKIX engine

Đây là bẫy tinh tế khi kiểm thời gian:

- **End-entity/leaf** và **intermediates trong `CertPath`** phải đáp ứng validity theo PKIX time.
- **Trust anchor** thường được cấu hình riêng và có thể không được kiểm tất cả certificate extensions/validity như một certificate nằm trong path. Trust anchor có thể được khai báo bằng CA name/public key hoặc certificate đại diện.
- Vì vậy, nếu một trusted root hết hạn hay policy đã distrust, không thể chỉ kỳ vọng mọi `CertPathValidator` invocation tự xử lý theo đúng chính sách root program của bạn. Phải quản lý truststore, root expiry, algorithm policy và revocation/distrust riêng khi thích hợp.
- Với path building, có thể tồn tại nhiều đường hợp lệ tới các anchors khác nhau; một root hết hạn/bị loại không luôn có nghĩa mọi path thất bại nếu cross-sign/alternate path vẫn được phép.
- Khi kiểm chứng lịch sử, chuẩn/chứng cứ như timestamp, archived validation data và policy cho chữ ký cũ khác với TLS live authentication.

**Điều không nên làm:** đặt root certificate do remote peer cung cấp vào `new TrustAnchor(root,null)` rồi validate leaf, và kết luận remote peer đáng tin. Đó là lỗi **“trust-on-input”**: attacker tự cung cấp cả root và chain, nên việc toán học đúng chỉ xác thực dữ liệu do attacker tự chọn.

## 14. Revocation và thời gian đánh giá: không thể bỏ qua trong threat model

Một chứng thư có thể **chưa hết hạn nhưng đã bị thu hồi** vì key lộ, CA cấp sai hoặc danh tính không còn đúng. CRL và OCSP là các cơ chế để đánh giá trạng thái thu hồi theo profile. Java PKIX có `PKIXRevocationChecker` và các tham số/cert stores liên quan, nhưng không được mặc định rằng mọi JSSE client bật revocation theo cùng cách.

Cần quyết định:

1. Bên nào cung cấp CRL/OCSP, URL và cơ chế caching?
2. Policy **fail-closed** hay **soft-fail** khi responder/CRL không truy cập được?
3. Có OCSP stapling hoặc cơ chế distrust do nhà cung cấp không?
4. Mốc kiểm chứng là hiện tại hay mốc lịch sử được ràng buộc bởi timestamp đáng tin?
5. Với private PKI, có PKI operations bảo đảm revoke/CRL issuance đúng thời hạn?
6. Có kiểm intermedates và trust anchors theo chính sách CA riêng?
7. Bảo vệ trước request gây network dependency/unbounded I/O khi path building hoặc revocation kiểm nguồn ngoài.

Nếu một hệ thống **có yêu cầu** phải kiểm revocation mà tắt `setRevocationEnabled(false)` để tránh latency/outage, đó không phải “tối ưu” chấp nhận được. Lab tắt vì tạo certificate không có hạ tầng CRL/OCSP; production phải theo policy.

## 15. Khi validate path thất bại: đọc lý do đúng cách

Java `CertPathValidatorException` có thể cung cấp `getReason()`, `getIndex()` (vị trí certificate trong path) và nguyên nhân gốc. Các lý do thường thuộc họ:

- `BasicReason.EXPIRED` hoặc `NOT_YET_VALID`
- `BasicReason.INVALID_SIGNATURE`
- `BasicReason.REVOKED` hoặc `UNDETERMINED_REVOCATION_STATUS`
- `PKIXReason.NOT_CA_CERT`
- `PKIXReason.PATH_TOO_LONG`
- `PKIXReason.INVALID_KEY_USAGE`
- `PKIXReason.INVALID_POLICY` / `INVALID_NAME` / `UNRECOGNIZED_CRIT_EXT`

Tên reason cụ thể và exception mapping có thể khác theo provider/JDK/trường hợp. Đừng dựa vào **một chuỗi exception text** như hợp đồng API ổn định; hãy log reason/index ở kênh nội bộ có kiểm soát và đối chiếu path thực tế.

### Bảng điều tra sự cố

| Lỗi/triệu chứng | Nguyên nhân có thể | Kiểm tra trước |
| --- | --- | --- |
| Certificate hết hạn | Leaf/intermediate đã qua `notAfter` | Runtime clock, validity từng cert, chain đang dùng |
| Chưa tới hiệu lực | `notBefore` trong tương lai | Clock/NTP, provisioning/rollout time |
| Not a CA | Intermediate có `CA=false` hoặc thiếu BasicConstraints đúng chuẩn | Certificate profile của issuing CA |
| Invalid key usage | Issuer KU không cho `keyCertSign` | KU bits và certificate issuing policy |
| Path too long | CA trung gian vượt `pathLenConstraint` | Đếm non-self-issued CA dưới constrained CA trong path |
| Không có valid path | Issuer thiếu/cross-sign sai/root không trusted | Truststore, intermediates, signature, path builder |
| Invalid purpose | Leaf chỉ có `clientAuth`/`codeSigning` cho TLS server | EKU và TLS certificate profile |
| Hostname mismatch | SAN không chứa endpoint DNS/IP tương ứng | URL/SNI, SAN, TLS endpoint identification |
| Revoke/OCSP lỗi | Certificate bị thu hồi hoặc trạng thái không xác định | Revocation policy, OCSP/CRL, time/caching |
| Thuật toán bị cấm | RSA key size/signature algorithm không đáp policy | Security properties, JDK policy và CA migration |
| Root trusted nhưng vẫn fail | Root không thay thế kiểm KU/EKU/time/name constraints trong path | Full chain và policy |
| Cert parse được nhưng fail | Parse không tương đương validate | Phân loại lỗi parse vs path vs TLS purpose |

Khi xảy ra lỗi, **không** bật “trust all”, tắt hostname verification, bỏ kiểm CA/KU/EKU hoặc đặt `PKIXParameters.setDate` giả để “fix”. Phải sửa chứng thư, CA chain, truststore hoặc thời gian hệ thống theo quy trình được duyệt.

## 16. Thiết kế kiểm thử toàn diện

Bộ test nên bao gồm cả **đường dẫn hợp lệ** và **đường dẫn bị từ chối có chủ đích**:

| Test | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| Path hợp lệ | Leaf TLS server, issuer CA hợp lệ, đúng root | PKIX pass dưới policy đã thiết lập |
| Chưa tới hiệu lực | `date` trước `leaf.notBefore` | Reject |
| Hết hạn | `date` sau `leaf.notAfter` | Reject |
| Leaf không có trusted issuer | Dùng unrelated root làm anchor | Reject |
| CA=false dùng ký certificate | Issuer intermediate thiếu CA flag | Reject |
| CA có KU nhưng thiếu keyCertSign | Intermediate có KU không cho ký cert | Reject |
| CA A pathLen=0 ký leaf trực tiếp | `[leaf,A]` với A là intermediate | PathLen riêng của A không chặn leaf |
| CA A pathLen=0 ký CA B rồi leaf | `[leaf,B,A]`, A/B là intermediates | Reject vì path length |
| CA A pathLen=1 ký CA B rồi leaf | Một non-self-issued CA B dưới A | PathLen riêng A cho phép; còn phải qua các điều kiện khác |
| EKU serverAuth | Leaf dùng làm TLS server | Được xét tiếp nếu KU/chain/SAN đúng |
| EKU clientAuth-only | Leaf dùng cho HTTPS server | TLS server policy reject |
| SAN hostname khác | Chain và KU/EKU đúng nhưng DNS khác | TLS endpoint reject |
| CA name constraints | Leaf ngoài domain được phép | PKIX reject |
| Critical extension không nhận diện | Issuer/leaf chứa critical extension không được hỗ trợ | Reject |
| Revoked certificate | CA công bố trạng thái revoked đúng policy | Reject |
| Root không đáng tin | User tự cung cấp self-signed root | Không thêm thành trust anchor |
| Trust root hợp lệ nhưng leaf hết hạn | Root vẫn còn hạn | Reject do leaf |
| Time skew | Hai nodes lệch giờ | Phát hiện bằng monitoring; không bỏ validation |
| Alternate chain | Cùng leaf có nhiều path tới anchors được phép | Chấp nhận/từ chối dựa trên full path policy |
| mTLS wrong client tenant | Client cert hợp lệ nhưng không có quyền nghiệp vụ | Reject ở authorization |
| CA rotation | Trust bundle có Old/New trong giai đoạn chuyển đổi | Được định nghĩa theo policy, không dùng trust-all |
| Disabled revocation in lab | CA test offline, không có OCSP/CRL | Chỉ được dùng trong lab với ngoại lệ rõ ràng |

**Quan trọng:** test CA pathLen phải có **ít nhất một intermediate trong `CertPath` để kiểm chính sách của intermediate đó**. Test chỉ root (TrustAnchor) và leaf không chứng minh đã thử thuật toán path length bên dưới root.

### Golden vectors và interoperability

Không chỉ kiểm thử cùng thư viện đã tạo chứng thư. Dùng `keytool`, OpenSSL hoặc PKI lab được kiểm soát để tạo fixtures độc lập; lưu **public certificate DER/PEM** và mô tả quá trình sinh/phiên bản tool. Không commit private key thực vào repository. Các test nên dựng lại truststore đúng CA mà không sửa `cacerts` của máy developer.

## 17. Thực tế triển khai trong JSSE / HTTPS

Java HTTPS client thường sử dụng JSSE trust manager và **endpoint identification** theo API. Khi bạn viết custom `SSLContext` hoặc `X509TrustManager`, đừng vô tình làm mất bước hostname verification/mục đích TLS; một generic `CertPathValidator.validate` không đủ để tự cài HTTPS client an toàn.

Mô hình khuyến nghị:

```text
HTTPS client configured with trusted root store
        |
        v
JSSE handshake / trusted CA path
        |
        v
certificate time + CA BasicConstraints + pathLen + KeyUsage
        |
        v
TLS purpose (EKU/KU) and endpoint identification (SAN)
        |
        v
connection authenticated
        |
        v
application checks service identity, authz and resource permissions
```

Đây là sơ đồ chức năng; trình tự nội bộ thay đổi theo TLS stack/provider. Với `SSLSocket` sử dụng trực tiếp, xem `SSLParameters.setEndpointIdentificationAlgorithm("HTTPS")` theo use case. Với `java.net.http.HttpClient`, dùng cơ chế HTTPS/endpoint identity mặc định được hỗ trợ thay vì tạo trust manager “checkServerTrusted rỗng”.

**CA scope:** Nên cấp root trust trong phạm vi client/tenant/protocol thích hợp, không thêm mọi intermediate/CA do peer gửi vào truststore. Thay đổi truststore làm thay đổi những chain nào có thể được chấp nhận, không chỉ một thao tác parse file.

## 18. Những lỗi nhận thức thường gặp

1. **“Chữ ký đúng thì certificate được tin.”** Sai: phải có trust anchor đáng tin và path policy.
2. **“CA=true là đủ để ký cert.”** Sai: còn keyCertSign nếu KU hiện diện, thời gian, pathLen, name constraints, signature, algorithm policy.
3. **“pathLen=0 tức không được ký leaf.”** Sai: leaf không phải non-self-issued intermediate CA.
4. **“Độ dài đường dẫn = số certificate trong danh sách.”** Sai: tính theo các non-self-issued CA thích hợp, không tính leaf và có quy tắc self-issued.
5. **“Đặt root pathLen=0 rồi chạy path root-anchor + leaf là đã test pathLen.”** Không chứng minh được: root anchor có thể nằm ngoài path validation constraints.
6. **“Leaf có serverAuth thì hostname đúng.”** Sai: serverAuth là mục đích, SAN/endpoint identity là danh tính.
7. **“Leaf có keyCertSign là CA.”** Sai: cần BasicConstraints CA=true và full PKIX rules.
8. **“X509EncodedKeySpec là certificate.”** Sai: là public-key SPKI spec; `CertificateFactory` parse certificate.
9. **“Hết hạn nhưng vẫn ký đúng thì có thể bỏ qua ngày.”** Không được cho TLS live auth.
10. **“Root trong cacerts thì mọi cert dưới root đều hợp lệ.”** Sai: leaf/intermediate có thể fail KU/EKU/validity/hostname/algorithm/revocation.
11. **“getExtendedKeyUsage()==null nghĩa là luôn được dùng cho bất kỳ tác vụ.”** Không tự đúng; tùy certificate profile/TLS policy.
12. **“Một check getBasicConstraints() đủ kiểm path.”** Sai: phải có path processing, chữ ký và policy.
13. **“Tắt revocation là luôn an toàn vì cert chưa hết hạn.”** Sai: compromise có thể xảy ra trước expiry; revocation theo threat model.
14. **“Tự xây TrustAnchor từ root peer gửi.”** Sai: attacker có thể gửi root của mình; trust anchor phải từ cấu hình tin cậy.
15. **“Một Java call verifyIssuer là toàn bộ PKIX.”** Sai: chỉ là một kiểm chữ ký số trên một certificate.
16. **“Hostname mismatch chỉ là lỗi DNS.”** Sai: tên được kiểm giữa requested endpoint và certificate identity; có thể là dấu hiệu MITM.
17. **“Chấp nhận client certificate mTLS thì cho luôn quyền admin.”** Sai: vẫn cần mapping principal/tenant và authorization.
18. **“Tất cả JDK/provider báo cùng một exception text.”** Sai: dùng typed APIs/reasons/index và test với runtime thực tế.
19. **“Có thể dùng ngày do client truyền lên để xác minh HTTPS.”** Sai: thời điểm cần đến từ policy/nguồn tin cậy.
20. **“Bỏ critical extensions không hiểu giúp tương thích tốt hơn.”** Sai: phá ràng buộc an ninh; cần dùng PKIX implementation phù hợp.

## 19. Bài tập thực hành

### Bài 1 — Đọc metadata

Chạy lab mục 10 và giải thích tại sao `root.getBasicConstraints() == 0` nhưng `leaf.getBasicConstraints() == -1`. In `getNotBefore/getNotAfter` cho từng certificate; tự tạo `Date` trước và sau validity để quan sát `checkValidity`.

### Bài 2 — Hết hạn nhưng chữ ký đúng

Giữ nguyên leaf do root ký. Đổi thời gian test thành 120 ngày sau. Giải thích vì sao chữ ký toán học vẫn đúng nhưng PKIX từ chối. Thử thay đổi đồng hồ hệ thống trong **môi trường lab cách ly** rồi khôi phục; không thay NTP/clock trên máy production.

### Bài 3 — Issuing CA không được phép

Tạo một intermediate có `BasicConstraints CA=false` nhưng thử dùng private key của nó ký một leaf. Có thể tạo chữ ký toán học hợp lệ; điều gì khiến PKIX phải từ chối intermediate làm issuer? Thử thêm KU thiếu `keyCertSign`, so sánh lý do lỗi.

### Bài 4 — pathLenConstraint thật sự

Tạo R → A(pathLen=0) → L và R → A(pathLen=0) → B(CA=true) → L. Cấu hình **R là TrustAnchor**, giữ **A trong CertPath**, không lấy A làm TrustAnchor. Giải thích vì sao path thứ hai phải bị từ chối vì intermediate depth. Thử A(pathLen=1) và kiểm constraints khác.

### Bài 5 — EKU serverAuth và clientAuth

Tạo hai leaf có cùng issuer và SAN khác nhau: một leaf `EKU=serverAuth`, một leaf `EKU=clientAuth`. Dựng HTTPS/mTLS test bằng JSSE đúng policy. Chỉ chain PKIX pass có đủ để dùng leaf clientAuth-only làm server không? Mô tả vai trò của TLS usage checks.

### Bài 6 — SAN và hostname

Leaf có SAN `service.example.test`. Kết nối tới `other.example.test` trong lab với cùng leaf, chain vẫn hợp lệ. Đo/giải thích lỗi hostname mismatch của TLS stack, và vì sao so Subject CN bằng substring là không an toàn.

### Bài 7 — Revocation và ngày kiểm chứng

Trong private PKI lab có OCSP/CRL, cấp một leaf còn hạn rồi revoke nó. Định nghĩa policy fail-closed hoặc soft-fail, thời gian cache và kiểm tra status khi responder không truy cập được. Không gỡ revocation check ở production chỉ để làm test pass.

### Bài 8 — Tích hợp CI

Tạo bộ fixtures `root.pem`, `leaf-valid.pem`, `leaf-expired.pem`, `leaf-wrong-eku.pem`, `intermediate-no-ca.pem`, `intermediate-depth0.pem` cùng cấu hình trust anchor. Test PKIX và TLS endpoint riêng. Mọi private key test phải được sinh trong môi trường kiểm soát/không tái sử dụng cho production.

### Bài 9 — Phân tích đường dẫn cross-signed

Một intermediate có hai certificate variants được ký bởi hai roots khác nhau. Dựa trên truststore và policy, builder có thể tìm nhiều paths. Làm thế nào để bảo đảm CA constraints, validity, name constraints, algorithm requirements và leaf EKU được áp cho **path thực sự được chọn**, thay vì chỉ nhìn root name?

**Tiêu chí hoàn thành:** Bạn có thể nhìn vào một certificate path và xác định **certificate nào phải là CA, key usage nào cho phép phát hành, pathLenConstraint giới hạn intermediate nào, thời điểm nào cần kiểm và EKU/SAN nào phù hợp TLS endpoint**. Quan trọng nhất, bạn biết **dùng PKIX/JSSE đúng chuẩn**, không tự kiểm một vài field rồi gọi đó là xác minh chứng thư hoàn chỉnh.

## 20. Tài liệu tham khảo

- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage`, validity, pathLenConstraint và `6.1` path validation.
- [RFC 9525 — Service Identity in TLS](https://www.rfc-editor.org/rfc/rfc9525): xác minh danh tính dịch vụ qua SAN/hostname.
- [Java 17 — X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): `checkValidity`, `getBasicConstraints`, `getKeyUsage`, `getExtendedKeyUsage`.
- [Java 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): API validate đường chứng thư.
- [Java 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): `TrustAnchor`, `setDate`, revocation/policy options.
- [Java 17 — CertPathBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): path construction.
- [Java 17 — CertPathValidatorException](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidatorException.html): reason và index của certificate lỗi.
- [Java 17 — TrustAnchor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/TrustAnchor.html): ranh giới niềm tin.
- [Java 17 — X509ExtendedTrustManager](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/X509ExtendedTrustManager.html): kiểm certificate trong ngữ cảnh TLS.
- [Java 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): endpoint identification.
- [Java 17 — keytool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): tạo CA và leaf test với BasicConstraints, KU/EKU/SAN.
- [Oracle Java 17 — JSSE Reference Guide](https://docs.oracle.com/en/java/javase/17/security/java-secure-socket-extension-jsse-reference-guide.html): TLS, trust managers và path validation.
