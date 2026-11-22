# 13.6 KeyUsage, ExtendedKeyUsage, BasicConstraints và extension critical

## 1. Vì sao chứng thư X.509 cần các extension giới hạn quyền?

Chứng thư **X.509 v3** gắn một *public key* với chủ thể, tổ chức cấp, thời hạn, chữ ký và nhiều điều kiện sử dụng. Chữ ký CA xác nhận nội dung chứng thư không bị sửa và được CA phát hành, nhưng **không tự cho phép dùng khóa cho mọi mục đích**. Một chứng thư được cấp để xác thực TLS server, ký mã ứng dụng, xác thực máy khách hoặc **ký chứng thư CA** thường cần các ràng buộc **khác nhau**.

Ba extension quan trọng trong bài:

1. **KeyUsage (KU, OID `2.5.29.15`):** những **nhóm phép toán mật mã cơ bản** mà public key trong chứng thư được phép thực hiện, biểu diễn bằng các bit như `digitalSignature`, `keyEncipherment`, `keyCertSign`.
2. **ExtendedKeyUsage (EKU, OID `2.5.29.37`):** những **mục đích ứng dụng/giao thức** được phép, biểu diễn bằng danh sách OID như TLS server authentication hoặc client authentication.
3. **BasicConstraints (BC, OID `2.5.29.19`):** chủ thể có phải **Certificate Authority (CA)** có thể phát hành chứng thư hay không và độ sâu CA con (`pathLenConstraint`).

Mỗi extension có thêm cờ **critical**. Nếu một extension được đánh dấu critical, bên xác minh phải **hiểu và xử lý đúng ngữ nghĩa** của extension đó, hoặc **từ chối chứng thư** khi không có cơ chế được phê duyệt để xử lý. Cờ này **không đồng nghĩa chứng thư đáng tin, mạnh hơn hoặc có quyền cao hơn**.

### 1.1 Một chứng thư có chữ ký hợp lệ vẫn có thể bị từ chối

Giả sử một CA được trust đã phát hành một certificate cho `service.example.test`:

- `KeyUsage` không cho phép `digitalSignature`, trong khi handshake TLS 1.3 cần server dùng khóa ký handshake.
- Hoặc EKU chỉ chứa `clientAuth`, không chứa `serverAuth` trong profile ứng dụng yêu cầu.
- Hoặc certificate có extension critical riêng mà verifier không hiểu.
- Hoặc chứng thư cấp dưới được dùng làm CA mặc dù `BasicConstraints.cA=false`.
- Hoặc SAN không khớp DNS đang truy cập; hoặc chứng thư quá hạn, bị thu hồi, chain không về trust anchor được chấp nhận.

Trong mỗi trường hợp, **chỉ kiểm tra chữ ký cryptographic trên certificate là chưa đủ** để đưa ra quyết định “cho phép dùng làm TLS server”. Cần thực hiện **PKIX path validation, identity/hostname validation, usage validation, algorithm policy và (khi cần) revocation checking** theo giao thức.

## 2. Cấu trúc extension trong X.509 v3

Mỗi extension có cấu trúc ASN.1 đại ý:

```text
Extension ::= SEQUENCE {
    extnID      OBJECT IDENTIFIER,
    critical    BOOLEAN DEFAULT FALSE,
    extnValue   OCTET STRING
}

TBSCertificate ::= SEQUENCE {
    ...,
    extensions [3] EXPLICIT Extensions OPTIONAL
}
```

- **`extnID`** xác định loại extension theo OID. Các OID chuẩn: KU `2.5.29.15`, BC `2.5.29.19`, EKU `2.5.29.37`, SAN `2.5.29.17`.
- **`critical`** mặc định **false** nếu không ghi trong DER. Có thể đánh dấu true với các extension cần bên xác minh thực thi bắt buộc.
- **`extnValue`** là một `OCTET STRING` chứa **DER encoding của giá trị bên trong** từng loại extension. Java `X509Certificate.getExtensionValue(oid)` trả byte của **DER-encoded OCTET STRING bên ngoài**, không trực tiếp trả đối tượng Java đã phân tích.

Đừng parse `getExtensionValue("2.5.29.15")` như một mảng bool thô: bên trong còn ASN.1 encoding. Với KU/EKU/BC, **dùng API typed** của `X509Certificate`; với extension tùy biến cần bộ decoder ASN.1 có kiểm soát và chính sách xử lý OID.

Một certificate có nhiều extension khác: `subjectAltName` (SAN), `authorityKeyIdentifier`, `subjectKeyIdentifier`, `nameConstraints`, `certificatePolicies`, `authorityInfoAccess`, CRL distribution points... Không được bỏ qua toàn bộ extension khác chỉ vì bài này tập trung KU/EKU/BC.

## 3. KeyUsage: từng bit nói lên quyền gì?

Java đọc `boolean[] ku = cert.getKeyUsage()`. Các bit có **chỉ số cố định** theo ASN.1 và Java API:

| Chỉ số | Bit KU | Ý nghĩa điển hình |
| ---: | --- | --- |
| 0 | `digitalSignature` | Xác minh chữ ký trên dữ liệu, giao thức xác thực thực thể, chữ ký handshake; **không** phải chữ ký cấp chứng thư/CRL |
| 1 | `nonRepudiation` / `contentCommitment` | Chữ ký mang ngữ nghĩa cam kết nội dung theo chính sách, không phải phép bảo đảm pháp lý tự động |
| 2 | `keyEncipherment` | Khóa công khai được dùng **bọc/vận chuyển key** (`key transport`), ví dụ RSA key transport lịch sử |
| 3 | `dataEncipherment` | Mã hóa trực tiếp dữ liệu người dùng bằng public key trong một số giao thức, hiếm gặp |
| 4 | `keyAgreement` | Tham gia phép thỏa thuận khóa như DH/ECDH trong các profile phù hợp |
| 5 | `keyCertSign` | Public key được dùng **xác minh chữ ký phát hành chứng thư** của CA |
| 6 | `cRLSign` | Public key được dùng **xác minh chữ ký CRL** |
| 7 | `encipherOnly` | Hạn chế mục đích “chỉ mã hóa” khi `keyAgreement` được bật |
| 8 | `decipherOnly` | Hạn chế mục đích “chỉ giải mã” khi `keyAgreement` được bật |

**Điều kiện quan trọng:**

- Nếu KU **có mặt**, khóa không được dùng ngoài các mục đích mà bit được bật cho phép. Nếu KU **không có**, `getKeyUsage() == null`; điều đó không tự có nghĩa mọi hệ thống đều nên cấp quyền, vì **EKU, profile/giao thức và policy riêng** vẫn có thể hạn chế.
- Nếu KU chứa `keyCertSign`, BC cần thể hiện chủ thể là **CA** (`cA=true`) theo RFC 5280. Nếu BC không có hoặc `cA=false`, public key **không được dùng để xác minh chữ ký chứng thư** chỉ vì nó có bit keyCertSign.
- `encipherOnly` và `decipherOnly` chỉ có ý nghĩa khi `keyAgreement` bật; dùng chúng độc lập với keyAgreement là không phù hợp profile RFC 5280.
- Khi CA dùng public key ký chứng thư/CRL, KU cần bit `keyCertSign`/`cRLSign` tương ứng. RFC 5280 yêu cầu extension KU trên chứng thư của CA có những mục đích đó và khuyến nghị đánh dấu critical.
- **TLS 1.3** dùng chữ ký trong cơ chế xác thực server bằng certificate, nên `digitalSignature` là bit KU liên quan. `keyEncipherment` xuất hiện trên nhiều chứng thư RSA để tương thích profile TLS cũ, nhưng **không thay thế `digitalSignature` trong TLS 1.3**. Sự phù hợp chính xác phải theo TLS version, key algorithm, signature scheme và profile hiện hành.

Ví dụ một leaf certificate RSA cho TLS server có thể có:

```text
KeyUsage: critical
  digitalSignature = true
  keyEncipherment  = true
  keyCertSign      = false
  cRLSign          = false
```

`keyEncipherment=true` **không** làm chứng thư trở thành CA và không chứng minh serverAuth EKU tồn tại. Ngược lại, chứng thư CA thường bật `keyCertSign` và có thể bật `cRLSign`, đồng thời cần BC `cA=true`.

### Java: đọc bit an toàn

```java
// Đoạn minh họa trong phương thức Java, với X509Certificate cert.
boolean[] usage = cert.getKeyUsage(); // null nếu thiếu extension
boolean canSignData = usage != null
        && usage.length > 0 && usage[0];
boolean canIssueCerts = usage != null
        && usage.length > 5 && usage[5];
```

Đây là ví dụ **policy nghiêm ngặt** yêu cầu bit phải có, chứ không tự diễn giải sự vắng KU là “cấm mọi thao tác” ở mọi giao thức. Với các profile cho phép KU vắng mặt, hãy triển khai quy tắc **“nếu extension có mặt thì phải phù hợp”** và các yêu cầu bắt buộc riêng của profile.

## 4. ExtendedKeyUsage: mục đích ứng dụng

`ExtendedKeyUsage` là danh sách **KeyPurposeId OID**, không phải bit array. Java trả `List<String>` từ `cert.getExtendedKeyUsage()` (và có thể ném `CertificateParsingException` nếu encoding sai).

Các OID thường gặp:

| EKU | OID | Trường hợp sử dụng |
| --- | --- | --- |
| `serverAuth` | `1.3.6.1.5.5.7.3.1` | Xác thực TLS server |
| `clientAuth` | `1.3.6.1.5.5.7.3.2` | Xác thực TLS client |
| `codeSigning` | `1.3.6.1.5.5.7.3.3` | Ký mã phần mềm |
| `emailProtection` | `1.3.6.1.5.5.7.3.4` | Bảo vệ email/S/MIME theo profile |
| `timeStamping` | `1.3.6.1.5.5.7.3.8` | Time-stamping authority |
| `OCSPSigning` | `1.3.6.1.5.5.7.3.9` | Ủy quyền ký phản hồi OCSP |
| `anyExtendedKeyUsage` | `2.5.29.37.0` | OID đặc biệt; cách chấp nhận chịu ràng buộc profile và chính sách relying party |

**Quy tắc kết hợp:** khi **cả KU và EKU có mặt**, mục đích sử dụng cần phù hợp **với cả hai**. EKU `serverAuth` không cấp quyền ký handshake nếu KU cấm digital signature trong profile có yêu cầu nó; KU `digitalSignature` cũng không vượt qua EKU chỉ ghi `clientAuth` nếu ứng dụng đang xác thực **server**.

**EKU vắng mặt:** `getExtendedKeyUsage()==null` nghĩa là chứng thư **không bị ràng buộc bởi extension EKU**; không phải certificate bị hỏng, cũng **không chứng minh quyền dùng trong mọi hệ thống**. Ứng dụng hoặc tổ chức có thể yêu cầu **EKU serverAuth phải hiện diện rõ ràng**; đó là lựa chọn policy và có thể nghiêm hơn yêu cầu chung của một số profile.

**EKU có mặt:** danh sách OID chỉ định các mục đích được cấp. EKU có thể được đánh dấu critical **hoặc non-critical** theo RFC 5280; dù non-critical, verifier **biết rõ** EKU vẫn phải thực thi ràng buộc khi xét mục đích sử dụng. Không coi non-critical là “được bỏ qua mọi lúc”.

**`anyExtendedKeyUsage`:** không phải nút “bỏ qua mọi kiểm tra”. RFC có khái niệm OID này nhưng relying party có thể đòi explicit OID mục đích và các profile riêng có quy tắc chặt hơn. Với TLS server trong một policy nội bộ yêu cầu `serverAuth`, nên yêu cầu rõ OID tương ứng thay vì tự suy diễn từ `anyExtendedKeyUsage`.

### Tình huống rõ nhất: một certificate clientAuth dùng làm server

```text
Leaf certificate:
  KeyUsage: digitalSignature
  ExtendedKeyUsage: clientAuth
  BasicConstraints: cA=false
  Signature: hợp lệ bởi CA được trust

Kết quả:
  PKIX path validation thuần: có thể PASS.
  TLS-server purpose "phải có EKU serverAuth": FAIL.
```

**Vì sao?** PKIX `CertPathValidator` kiểm tra chuỗi/điều kiện PKIX, nhưng **không tự là HTTPS hostname verifier hoặc bộ đánh giá mọi purpose nghiệp vụ**. Người lập trình phải dùng trust manager/phân hệ TLS được cấu hình đầy đủ; ví dụ bên dưới cố ý tách hai kiểm tra để người học thấy rõ.

## 5. BasicConstraints: ai có thể phát hành chứng thư?

Cấu trúc:

```text
BasicConstraints ::= SEQUENCE {
    cA                 BOOLEAN DEFAULT FALSE,
    pathLenConstraint  INTEGER (0..MAX) OPTIONAL
}
```

- `cA=false`: chủ thể không phải CA phát hành chứng thư theo profile, thường là **end entity (EE)** như một server hoặc client certificate.
- `cA=true`: chứng thư có thể được dùng làm CA **nếu** các điều kiện khác như `keyCertSign`, trust, thuật toán, path validation đều thỏa.
- `pathLenConstraint`: số lượng tối đa **chứng thư CA trung gian không tự cấp (non-self-issued)** được phép nằm sau CA này trong đường dẫn hợp lệ, trước end entity. Không tính end-entity leaf. **`pathLen=0` vẫn cho phép CA trực tiếp ký leaf**, nhưng không cho thêm intermediate CA không tự cấp bên dưới theo RFC 5280.
- Không có `pathLenConstraint` ở một certificate CA `cA=true`: không giới hạn CA-chain depth bởi **chính field này**; path vẫn phải tuân thủ các constraint/policy khác.
- RFC 5280 không cho phép khai báo pathLen trên certificate có `cA=false`; và khi CA dùng khóa để ký chứng thư, BC phải hiện diện và **critical** theo profile.

Trong Java:

```java
// Đoạn minh họa: cert là X509Certificate.
int constraint = cert.getBasicConstraints();
boolean isCa = constraint >= 0;
// constraint == -1: không phải CA (hoặc BC không có).
// constraint == 0 : CA nhưng không có non-self-issued intermediate CA sau nó.
// constraint > 0  : CA với giới hạn độ sâu tương ứng.
// constraint == Integer.MAX_VALUE : CA không khai báo pathLen.
```

**Điểm dễ nhầm:** giá trị Java `-1` xuất hiện cả khi BC **không có** lẫn khi BC có `cA=false`; muốn biết extension có hiện diện, kiểm tra `cert.getExtensionValue("2.5.29.19") != null`. `getBasicConstraints()` là một **convenience API**, không phải công cụ dump toàn bộ ASN.1.

### CA chain và trust anchor

```text
Trust anchor (CA root được cấu hình tin cậy)
    |
    +--- Intermediate CA (BC cA=true, KU keyCertSign)
             |
             +--- End entity / server (BC cA=false, EKU serverAuth)
```

**Không tự coi certificate có `cA=true` là root đáng tin.** Bất kỳ attacker nào cũng có thể tự ký một certificate `CA=true`; chỉ trust anchor được cấp qua cấu hình/PKI đáng tin mới là cơ sở trust. Trong Java `TrustAnchor(rootCert,null)` cố ý **coi rootCert được tin**; nếu nhận file root từ mạng không tin rồi lập tức đưa làm TrustAnchor, toàn bộ kiểm tra chuỗi trở nên vô nghĩa.

Trust anchor có thể được xử lý khác một intermediate certificate khi kiểm tra path: nhiều ràng buộc trong certificate tự ký của root không được áp dụng hệt như các chứng thư nằm *trong* CertPath. Phải quản lý chính sách trust anchor/PKIXParameters riêng, không lấy kết quả `CertPathValidator` làm chứng cứ root đã được kiểm duyệt.

## 6. Extension critical: “hiểu và xử lý hoặc từ chối”

Theo RFC 5280, cờ critical được đặt trong **từng extension**, không phải cờ toàn certificate.

| Tình huống | Hành vi của bộ xác minh phù hợp |
| --- | --- |
| Extension **critical** và được hiểu/được xử lý | Áp dụng ràng buộc của nó trong bối cảnh PKIX/application |
| Extension **critical** nhưng chưa có checker xử lý | **Từ chối certificate/path** |
| Extension **non-critical** không được hiểu | Có thể bỏ qua extension chưa biết theo profile |
| Extension **non-critical** đã biết và liên quan purpose (như EKU) | Không được tự ý bỏ ràng buộc cần thực thi khi xét usage |
| Có các extension critical quen thuộc, nhưng key usage/mục đích không phù hợp | **Vẫn từ chối** dù parser hiểu extension |
| Không có extension unknown critical, nhưng chain/hostname sai | **Vẫn từ chối**; critical không thay thế PKIX/identity validation |

Ví dụ:

```text
Certificate A:
  Critical: KeyUsage (2.5.29.15)
  Noncritical: ExtendedKeyUsage (2.5.29.37)
  Khả năng: verifier hiểu KU và kiểm tra purpose EKU -> có thể hợp lệ.

Certificate B:
  Critical: 1.2.3.4.5 (OID custom không ai xử lý)
  Khả năng: parser X.509 đọc được file nhưng PKIX phải từ chối path.

Certificate C:
  Noncritical: 1.2.3.4.5
  Khả năng: PKIX có thể bỏ qua OID không biết nếu các kiểm tra khác đạt.
```

### Các API Java liên quan

| API | Trả về | Lưu ý |
| --- | --- | --- |
| `getCriticalExtensionOIDs()` | `Set<String>` các OID critical; có thể `null` | Không tự nói extension có được **xử lý đúng** hay không |
| `getNonCriticalExtensionOIDs()` | `Set<String>` các OID non-critical | Sử dụng để kiểm tra nhãn, không thay định nghĩa extension |
| `hasUnsupportedCriticalExtension()` | `boolean` | Chỉ phản ánh sự hỗ trợ mà implementation báo cáo; **không đủ thay PKIX/purpose validation** |
| `getExtensionValue(oid)` | `byte[]` DER của outer OCTET STRING hoặc `null` | Không phải kết quả parse typed; phải decode ASN.1 đúng lớp |
| `getKeyUsage()` | `boolean[]` hoặc `null` | Các bit cố định 0..8 |
| `getExtendedKeyUsage()` | `List<String>` hoặc `null` | OID, không phải tên thân thiện |
| `getBasicConstraints()` | `int` | `-1` end entity/not CA; giá trị CA là path length |
| `checkValidity()` | Không trả về khi ngày hợp lệ | Chỉ thời gian, không kiểm tra chain/trust/purpose |

Cần sử dụng `CertificateFactory` để parse chứng thư, `CertPathValidator.getInstance("PKIX")` để kiểm tra một CertPath đến trust anchor đã cấu hình, và TLS trust manager/hostname verifier cho HTTPS. `certificate.verify(issuerPublicKey)` chỉ kiểm tra **chữ ký của certificate**, không tự xác minh CA chain, KU/EKU, critical extensions, SAN, thời hạn hoặc revocation.

## 7. Tạo bộ chứng thư demo với keytool (Java 17+)

Để ví dụ **không phụ thuộc CA/tệp bí mật bên ngoài**, dùng `keytool` đi kèm JDK để tạo **chứng thư test tự ký** và certificate leaf được CA test ký. Toàn bộ key material chỉ phục vụ học tập.

Sử dụng **PowerShell 5.1+ trên Windows** hoặc PowerShell 7+; chạy trong một phiên PowerShell và lưu nguồn Java của phần 8 ở file `X509ExtensionsDemo.java` trong thư mục đang làm việc.

**Không dùng password mẫu `changeit` hoặc root CA test này trong sản phẩm.** Mã demo tạo `root.p12` chứa private key CA trong một thư mục tạm; hãy bảo vệ/xóa thư mục và không commit lên repository. Những chứng thư này **không thuộc hệ thống CA công khai và không được trust ngoài chương trình demo**.

```powershell
# Tạo thư mục tạm và password DEMO. Chạy liên tiếp cùng phiên PowerShell.
$t = Join-Path $env:TEMP ("x509-extension-demo-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Force -Path $t | Out-Null
$pw = "changeit"

# CA root: BasicConstraints critical, CA=true, pathLen=0;
# KeyUsage critical, cho phép ký certificate và CRL.
keytool -genkeypair -alias root -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=Example Test Root" -validity 365 -storetype PKCS12 -keystore (Join-Path $t "root.p12") -storepass $pw -keypass $pw -ext "BC:critical=ca:true,pathlen:0" -ext "KU:critical=keyCertSign,cRLSign" -noprompt

# Leaf tạo khóa và CSR, chưa phải certificate do CA ký.
keytool -genkeypair -alias leaf -keyalg RSA -keysize 2048 -sigalg SHA256withRSA -dname "CN=service.example.test" -validity 30 -storetype PKCS12 -keystore (Join-Path $t "leaf.p12") -storepass $pw -keypass $pw -noprompt
keytool -certreq -alias leaf -keystore (Join-Path $t "leaf.p12") -storepass $pw -file (Join-Path $t "leaf.csr")

# Export root certificate (không phải private key).
keytool -exportcert -alias root -keystore (Join-Path $t "root.p12") -storepass $pw -rfc -file (Join-Path $t "root.pem")

# Các tham số chung cho 4 leaf certificates do root ký.
$base = @("-gencert", "-alias", "root",
  "-keystore", (Join-Path $t "root.p12"), "-storepass", $pw,
  "-infile", (Join-Path $t "leaf.csr"), "-validity", "30", "-rfc",
  "-ext", "KU:critical=digitalSignature,keyEncipherment",
  "-ext", "BC=ca:false", "-ext", "SAN=dns:service.example.test")

# Server hợp lệ theo mục đích demo.
& keytool @base -outfile (Join-Path $t "server.pem") -ext "EKU=serverAuth"

# OID tùy biến dạng critical: validator thông thường không xử lý được.
& keytool @base -outfile (Join-Path $t "critical.pem") -ext "EKU=serverAuth" -ext "1.2.3.4.5:critical=0101FF"

# Cùng OID tùy biến dạng noncritical: validator có thể bỏ qua.
& keytool @base -outfile (Join-Path $t "noncritical.pem") -ext "EKU=serverAuth" -ext "1.2.3.4.5=0101FF"

# Chứng thư chỉ có EKU clientAuth, không có serverAuth.
& keytool @base -outfile (Join-Path $t "client.pem") -ext "EKU=clientAuth"
```

Lệnh `-gencert` cho ra các leaf certificate đã được root ký. Tham số `-ext "1.2.3.4.5:critical=0101FF"` biểu diễn một OID tùy biến giả lập cho bài học, với một giá trị DER nhỏ. Không dùng OID tùy tiện như vậy để thiết kế extension sản phẩm; cần OID/schema đã đăng ký và bộ xử lý phù hợp.

Các lệnh `keytool` có thể in thông báo tạo chứng thư trên stderr/stdout tùy JDK; **stdout chính xác** mà phần 8 ghi là output của **lệnh `java`**, không bao gồm thông báo `keytool`. Nếu môi trường không có `keytool`, cần cài JDK hỗ trợ. Khi chạy ở macOS/Linux, có thể chuyển script PowerShell sang cú pháp shell tương ứng, nhưng các tham số `keytool` và ý nghĩa certificate không thay đổi.

## 8. Chương trình Java 17+: đọc KU/EKU/BC và thử critical/noncritical

Chương trình sau dùng **chỉ Java SE** để:

1. Đọc chứng thư PEM bằng `CertificateFactory("X.509")`.
2. Kiểm tra CA `BasicConstraints.cA=true`, `pathLen=0`, KU `keyCertSign` và BC `critical`.
3. Kiểm tra leaf `cA=false`, KU `digitalSignature/keyEncipherment`, EKU `serverAuth`, KU critical, EKU noncritical.
4. Thiết lập một trust anchor CA test **cố ý tin cậy trong phạm vi demo**, tạo `CertPath` cho leaf và gọi `CertPathValidator("PKIX")`.
5. So sánh certificate có OID tùy biến **critical vs noncritical**: critical bị từ chối, noncritical được chấp nhận theo PKIX khi các điều kiện khác đúng.
6. So sánh certificate chỉ có `clientAuth`: PKIX path thuần vẫn được chấp nhận, nhưng phép kiểm tra *server purpose* riêng từ chối.

Lưu thành **`X509ExtensionsDemo.java`**:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Collection;
import java.util.List;
import java.util.Set;

public final class X509ExtensionsDemo {
    private static final String KU = "2.5.29.15";
    private static final String EKU = "2.5.29.37";
    private static final String BC = "2.5.29.19";
    private static final String SERVER_AUTH = "1.3.6.1.5.5.7.3.1";
    private static final String CUSTOM = "1.2.3.4.5";

    private static X509Certificate read(String path) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        try (InputStream in = Files.newInputStream(Path.of(path))) {
            return (X509Certificate) factory.generateCertificate(in);
        }
    }

    private static boolean bit(boolean[] bits, int index) {
        return bits != null && bits.length > index && bits[index];
    }

    private static boolean has(Set<String> oids, String oid) {
        return oids != null && oids.contains(oid);
    }

    private static boolean hasDnsSan(X509Certificate certificate,
                                     String host) throws Exception {
        Collection<List<?>> names = certificate.getSubjectAlternativeNames();
        if (names == null) return false;
        for (List<?> item : names) {
            if (item.size() >= 2 && Integer.valueOf(2).equals(item.get(0))
                    && item.get(1) instanceof String dns
                    && host.equalsIgnoreCase(dns)) {
                return true;
            }
        }
        return false;
    }

    private static boolean pkixAccepts(X509Certificate root,
                                       X509Certificate leaf) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        CertPath path = factory.generateCertPath(List.of(leaf));
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(root, null)));
        params.setRevocationEnabled(false); // Test fixture only.
        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return true;
        } catch (CertPathValidatorException rejected) {
            return false;
        }
    }

    private static boolean demoServerPurpose(X509Certificate certificate)
            throws Exception {
        List<String> purposes = certificate.getExtendedKeyUsage();
        return certificate.getBasicConstraints() == -1
                && bit(certificate.getKeyUsage(), 0)
                && purposes != null
                && purposes.contains(SERVER_AUTH)
                && hasDnsSan(certificate, "service.example.test");
    }

    public static void main(String[] args) throws Exception {
        if (args.length != 5) {
            throw new IllegalArgumentException(
                    "Usage: java X509ExtensionsDemo root.pem server.pem "
                    + "critical.pem noncritical.pem client.pem");
        }
        X509Certificate root = read(args[0]);
        X509Certificate server = read(args[1]);
        X509Certificate unknownCritical = read(args[2]);
        X509Certificate unknownNoncritical = read(args[3]);
        X509Certificate client = read(args[4]);

        root.checkValidity();
        server.checkValidity();
        System.out.println("rootIsCa=" + (root.getBasicConstraints() >= 0));
        System.out.println("rootPathLen=" + root.getBasicConstraints());
        System.out.println("rootKeyCertSign=" + bit(root.getKeyUsage(), 5));
        System.out.println("rootBcCritical=" + has(
                root.getCriticalExtensionOIDs(), BC));

        System.out.println("leafIsEndEntity="
                + (server.getBasicConstraints() == -1));
        System.out.println("leafDigitalSignature="
                + bit(server.getKeyUsage(), 0));
        System.out.println("leafKeyEncipherment="
                + bit(server.getKeyUsage(), 2));
        System.out.println("leafServerAuthEku="
                + server.getExtendedKeyUsage().contains(SERVER_AUTH));
        System.out.println("leafKuCritical=" + has(
                server.getCriticalExtensionOIDs(), KU));
        System.out.println("leafEkuNonCritical=" + has(
                server.getNonCriticalExtensionOIDs(), EKU));
        System.out.println("serverPkixAccepted="
                + pkixAccepts(root, server));
        System.out.println("serverPurposeForDemo="
                + demoServerPurpose(server));

        System.out.println("unknownCriticalDeclared=" + has(
                unknownCritical.getCriticalExtensionOIDs(), CUSTOM));
        System.out.println("unknownCriticalRejected="
                + !pkixAccepts(root, unknownCritical));
        System.out.println("unknownNoncriticalDeclared=" + has(
                unknownNoncritical.getNonCriticalExtensionOIDs(), CUSTOM));
        System.out.println("unknownNoncriticalAccepted="
                + pkixAccepts(root, unknownNoncritical));

        System.out.println("clientOnlyPkixAccepted="
                + pkixAccepts(root, client));
        System.out.println("clientOnlyServerPurpose="
                + demoServerPurpose(client));
    }
}
```

Biên dịch và chạy (trong **cùng phiên PowerShell** còn giữ biến `$t`):

```powershell
javac --release 17 -encoding UTF-8 X509ExtensionsDemo.java
java X509ExtensionsDemo (Join-Path $t "root.pem") (Join-Path $t "server.pem") (Join-Path $t "critical.pem") (Join-Path $t "noncritical.pem") (Join-Path $t "client.pem")
```

**Kết quả đã kiểm tra** với JDK 17+ có provider PKIX/keytool thông dụng:

```text
rootIsCa=true
rootPathLen=0
rootKeyCertSign=true
rootBcCritical=true
leafIsEndEntity=true
leafDigitalSignature=true
leafKeyEncipherment=true
leafServerAuthEku=true
leafKuCritical=true
leafEkuNonCritical=true
serverPkixAccepted=true
serverPurposeForDemo=true
unknownCriticalDeclared=true
unknownCriticalRejected=true
unknownNoncriticalDeclared=true
unknownNoncriticalAccepted=true
clientOnlyPkixAccepted=true
clientOnlyServerPurpose=false
```

Sau khi học xong, xóa các private keys/certificates demo trong thư mục tạm:

```powershell
# Chỉ chạy khi $t đúng là thư mục DEMO vừa tạo, không chứa dữ liệu cần giữ.
if ($t -like (Join-Path $env:TEMP "x509-extension-demo-*")) {
    Remove-Item -LiteralPath $t -Recurse -Force
}
```

**Cảnh báo:** xóa file thông thường không đồng nghĩa secure erase khỏi SSD/snapshot/backup. Test fixture không nên dùng key thật; thư mục đã được tạo chỉ để thực hành.

### 8.1 Vì sao các nhóm kết quả quan trọng?

**`rootIsCa=true`, `rootPathLen=0`, `rootKeyCertSign=true`:** root test có BC CA=true, không cho trung gian CA non-self-issued sau root, nhưng vẫn có thể ký trực tiếp end-entity leaf. `rootBcCritical=true` chứng minh flag critical của BC hiện diện trong fixture.

**`leafIsEndEntity=true`:** `getBasicConstraints() == -1` chứng minh Java xem leaf không phải CA. **Không được** dùng leaf để ký chứng thư con kể cả khi khóa của nó có khả năng kỹ thuật tạo RSA signature.

**`leafDigitalSignature=true` và `leafKeyEncipherment=true`:** hai quyền KU đều bật trong fixture. Không có nghĩa leaf có quyền `keyCertSign`; đây là quyền khác ở bit 5.

**`leafServerAuthEku=true`, `leafKuCritical=true`, `leafEkuNonCritical=true`:** xác nhận EKU serverAuth được phát hành, KU được đánh dấu critical và EKU được đánh dấu non-critical. Việc EKU non-critical không làm ràng buộc mục đích bị vô hiệu.

**`serverPkixAccepted=true`:** chuỗi leaf → root **với root test đã được cấu hình như TrustAnchor** qua `PKIXParameters` vượt qua các kiểm tra chung trong runtime. Đây **không** có nghĩa root tự nhiên được Internet trust. Trong ví dụ `params.setRevocationEnabled(false)` chỉ để fixture không cần CRL/OCSP; **không nên tắt revocation mặc định trong hệ thống thực** mà không có chính sách thay thế thích hợp.

**`unknownCriticalRejected=true`:** chứa OID critical không có checker xử lý khiến CertPathValidator trả `CertPathValidatorException` và path bị loại. Chỉ parse certificate thành công bằng `CertificateFactory` **không chứng minh** nó có thể được chấp nhận.

**`unknownNoncriticalAccepted=true`:** OID không hiểu nhưng non-critical có thể được bỏ qua, miễn tất cả yêu cầu khác đạt. Điều này không có nghĩa một non-critical EKU serverAuth/clientAuth đã biết cũng có thể bỏ qua khi kiểm tra mục đích.

**`clientOnlyPkixAccepted=true` nhưng `clientOnlyServerPurpose=false`:** generic PKIX path validator **không tự xác minh mọi mục đích nghiệp vụ**. Trong fixture, leaf có EKU `clientAuth`, còn policy minh họa yêu cầu EKU `serverAuth`; do đó không cho phép dùng nó làm TLS-server certificate.

### 8.2 Những giới hạn cố ý của ví dụ

- `demoServerPurpose` chỉ kiểm tra **đúng một DNS SAN** không wildcard/IDNA, KU digitalSignature, EKU serverAuth và BC EE. Đây là **giải thích học thuật**, **không phải hostname verifier sản phẩm**. TLS phải dùng `TrustManagerFactory`, `X509ExtendedTrustManager`/JSSE và cơ chế endpoint identification phù hợp.
- `CertPathValidator` trong ví dụ chỉ xác nhận **một leaf** do root demo ký. Hệ thống thực có intermediate CA, name constraints, certificate policy, algorithm constraints, revocation, các ràng buộc trust store, EKU TLS và identity/hostname cần xử lý theo giao thức.
- `params.setRevocationEnabled(false)` chỉ cho môi trường test không có CRL/OCSP. Trong sản phẩm cần chính sách revocation được đánh giá, cache/failure mode phù hợp, có thể dùng `PKIXRevocationChecker` hoặc JSSE provider được cấu hình.
- `TrustAnchor(root, null)` giả định root đã được trust. **Không bao giờ lấy root từ người gửi không xác thực rồi tự thêm làm trust anchor.**
- `keytool` và cách nhận biết custom extension của các provider khác có thể có khác biệt. Mã và output trên đã được kiểm thử trên môi trường JDK có các thành phần trên, không hứa mọi provider sẽ có cùng diagnostic message.
- Không dùng private key test chứa trong PKCS12 demo cho bất cứ hệ thống thật. Password `changeit` dễ đoán; mọi bí mật sản phẩm phải dùng storage và lifecycle riêng.

## 9. KU/EKU/BC phối hợp trong các tình huống thực tế

| Certificate | KU quan trọng | EKU theo purpose | BC | Chú ý |
| --- | --- | --- | --- | --- |
| TLS server key ký handshake | `digitalSignature` | `serverAuth` khi profile yêu cầu | EE `cA=false` | Cần SAN/hostname + PKIX + thuật toán/signature scheme |
| TLS mutual-auth client | `digitalSignature` | `clientAuth` | EE | Không dùng làm server nếu policy yêu cầu serverAuth |
| CA phát hành certificate | `keyCertSign` (và `cRLSign` nếu ký CRL) | Theo policy CA, nhiều trường hợp không có EKU hoặc bị ràng buộc | CA `cA=true`, BC critical | Phải trust/path valid, pathLen tuân thủ |
| CA trung gian | `keyCertSign` | Nếu có EKU, cần xem giới hạn mục đích chain theo profile | CA `cA=true` | `pathLen` xác định CA con non-self-issued tối đa |
| Ký mã nguồn/phần mềm | `digitalSignature` hoặc profile thích hợp | `codeSigning` | EE | Không tự được dùng làm TLS server |
| S/MIME email | KU tùy chức năng ký/mã hóa | `emailProtection` | EE | Cần policy và kiểm tra địa chỉ/chủ thể liên quan |
| OCSP delegated responder | `digitalSignature` | `OCSPSigning` | Theo profile OCSP | Cần xác minh ủy quyền OCSP/responder chain |
| Chứng thư giả làm CA chỉ bật KU keyCertSign | `keyCertSign` | Bất kỳ | `cA=false` | **Không** được dùng cấp certificate theo RFC 5280 |

**Đừng sao chép KU/EKU template vô điều kiện** giữa các sản phẩm. Các chuẩn TLS, S/MIME, CMS, code-signing, OCSP, CA/B Forum, PKI nội bộ có yêu cầu chi tiết khác nhau và có thể thay đổi. Chọn extension theo **mục đích key, cơ chế signature/encryption và relying-party profile**.

Một chứng thư CA có `pathLen=0` có thể trực tiếp phát hành leaf; nếu cần intermediate CA mới dưới nó, phải có CA pathLen phù hợp và được cấp lại với key hierarchy thích hợp. `BasicConstraints` không phải công cụ phân quyền nghiệp vụ tất cả loại chứng thư; nó chủ yếu giới hạn **quyền phát hành certificate** và chain depth.

## 10. Phân tích lỗi và chống sai cấu hình

| Biểu hiện | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `InvalidCertificate` hoặc `CertificateParsingException` khi đọc EKU | DER ASN.1 của extension sai | Từ chối certificate, xác định issuer, dùng parser/provider an toàn |
| `getKeyUsage()==null` | Certificate không có KU | Phân biệt “không hạn chế bởi KU” với policy yêu cầu KU hiện diện |
| `getExtendedKeyUsage()==null` | Certificate không có EKU | Đánh giá profile/purpose, không mặc định mọi ứng dụng đều cho phép |
| `getBasicConstraints()==-1` | EE `cA=false` hoặc không có BC | Không dùng làm CA; kiểm tra presence nếu cần phân biệt |
| `Integer.MAX_VALUE` từ `getBasicConstraints` | CA không có `pathLenConstraint` | Không có giới hạn **từ field pathLen**, nhưng các constraint khác vẫn áp dụng |
| KU `keyCertSign=true` nhưng BC `cA=false` | Extension mâu thuẫn | Từ chối dùng làm CA, sửa cấp phát certificate |
| Generic PKIX PASS nhưng HTTPS fail | SAN/hostname, serverAuth EKU, KU/signature algorithm hoặc TLS policy khác | Dùng JSSE trust manager và endpoint verification đầy đủ |
| PKIX fail ở `UNRECOGNIZED_CRIT_EXT` / lỗi critical | Extension critical OID không được checker nào xử lý | Bổ sung checker hợp lệ hoặc yêu cầu issuer cấp chứng thư tương thích; không bỏ cờ critical tại runtime |
| Unknown non-critical bị bỏ qua | Đúng hành vi khi extension không ảnh hưởng purpose/profile | Không nhầm với extension được biết nhưng hạn chế usage |
| Test self-signed root “pass” dù root không tin cậy | Ứng dụng tự thêm root tùy ý làm `TrustAnchor` | Chỉ dùng trust store/anchor được quản trị qua kênh xác thực |
| `CertificateFactory` parse được certificate nhưng validation fail | Parse cú pháp không bằng xác minh chain/trust | Gọi `CertPathValidator`/TLS engine đúng nhiệm vụ |
| Leaf KU/EKU không khớp mục đích | CA dùng extension template sai | Cấp lại với purpose và thuật toán phù hợp; không bỏ qua policy |
| PKIX fail do thời hạn hoặc chính sách crypto | Chứng thư hết hạn, key yếu, algorithm disabled | Rotate/re-issue, cập nhật PKI an toàn, không tắt algorithm constraints |
| Không xác minh revocation | Không cấu hình CRL/OCSP hoặc cố ý disable để demo | Thiết kế revocation policy cho môi trường thực |

### Quy trình kiểm tra đề xuất

1. **Parse:** `CertificateFactory("X.509")`, giới hạn kích thước input, không coi file PEM hợp lệ là certificate đáng tin.
2. **Xem extension:** `getKeyUsage()`, `getExtendedKeyUsage()`, `getBasicConstraints()`, OID critical/noncritical; chú ý vắng extension và các giá trị mặc định.
3. **Xác minh chain:** cấu hình trusted anchors thực, intermediate certificates, thời hạn, algorithm constraints, policy, critical extensions, revocation theo profile.
4. **Xác minh purpose:** KU/EKU phù hợp thao tác và hệ thống, ví dụ TLS server vs client. Khi cả hai có mặt phải đồng thời phù hợp.
5. **Xác minh identity:** SAN hostname/IP hay định danh khác theo giao thức; không dùng CN đơn thuần như thay thế SAN trong hệ thống TLS hiện đại.
6. **Chỉ cho phép operation sau khi tất cả bước liên quan PASS.** Ghi audit có chọn lọc (subject, issuer, serial, fingerprint public certificate), không log private keys/tokens nhạy cảm.

## 11. Các hiểu lầm cần nhớ

**“KeyUsage critical thì certificate tự đáng tin?”** Không. Critical chỉ yêu cầu verifier hiểu và xử lý extension; trust anchor, chain, thời hạn, danh tính và purpose vẫn phải kiểm tra.

**“EKU non-critical nghĩa là được bỏ qua serverAuth?”** Không. Nếu một application verifier hiểu EKU, nó phải xét quyền sử dụng trong profile; noncritical chỉ cho phép bỏ qua **extension không hiểu** theo chính sách.

**“CA=true là root CA đáng tin?”** Không. `cA=true` là quyền phát hành về mặt cấu trúc; trust anchor cần được thiết lập ngoài certificate bằng cơ chế đáng tin.

**“pathLen=0 nghĩa là không được cấp leaf?”** Không. Nó hạn chế **non-self-issued intermediate CA** ở phía dưới, không cấm cấp end entity trực tiếp.

**“Có KU digitalSignature nghĩa là được cấp CA?”** Không. Muốn ký chứng thư cần `keyCertSign` và `BasicConstraints.cA=true`, cùng path/trust/policy phù hợp.

**“Có KU keyEncipherment nghĩa là server TLS 1.3 dùng được?”** Không đủ. TLS 1.3 certificate authentication dùng chữ ký; certificate algorithm, digitalSignature, EKU và SAN/hostname phải được đánh giá.

**“Nếu `getExtendedKeyUsage() == null` thì chứng thư không dùng được?”** Không tự động. Nó chỉ không có ràng buộc EKU được khai báo; giao thức/policy có thể yêu cầu cụ thể.

**“`certificate.verify(publicKey)` là đã kiểm PKIX?”** Không. Đó là kiểm chữ ký certificate, không làm toàn bộ path validation và hostname/purpose checks.

**“`getCriticalExtensionOIDs()` rỗng thì HTTPS an toàn?”** Không. Thiếu critical unknown chỉ loại một nhóm lỗi; các điều kiện trust/identity khác vẫn bắt buộc.

## 12. Tự kiểm tra kiến thức

1. **OID của KU, BC, EKU?** Lần lượt `2.5.29.15`, `2.5.29.19`, `2.5.29.37`.
2. **Chỉ số bit `digitalSignature`, `keyEncipherment`, `keyCertSign`?** `0`, `2`, `5`.
3. **Java trả gì nếu KU không có?** `X509Certificate.getKeyUsage()==null`.
4. **Java trả gì nếu EKU không có?** `getExtendedKeyUsage()==null`.
5. **`getBasicConstraints()==-1` có thể có mấy tình huống?** `cA=false` hoặc BC không có; đều không thể dựa vào đó để cấp quyền làm CA.
6. **`getBasicConstraints()==Integer.MAX_VALUE` thường là gì?** CA có `cA=true` nhưng không nêu `pathLenConstraint`.
7. **Root CA có `pathLen=0` có được ký leaf trực tiếp không?** Có; không được có thêm non-self-issued intermediate CA bên dưới theo ràng buộc đó.
8. **KU `keyCertSign=true` có đủ để dùng key làm CA không?** Không; cần `BasicConstraints.cA=true`, trust/path và chính sách.
9. **EKU serverAuth có thay thế KU digitalSignature cho TLS 1.3 không?** Không; khi cả hai có mặt phải phù hợp nhau.
10. **Một certificate chỉ có EKU clientAuth, generic PKIX chain có thể pass không?** Có; server-purpose verifier vẫn phải từ chối khi yêu cầu `serverAuth`.
11. **Extension critical không nhận biết có thể được bỏ qua không?** Không; verifier phù hợp phải hiểu và xử lý hoặc từ chối.
12. **Unknown non-critical có thể bỏ qua không?** Có thể, khi extension không được hỗ trợ và profile cho phép; không có nghĩa được bỏ qua EKU/KU đã biết.
13. **`getExtensionValue(oid)` trả raw nội dung extension hay bytes outer OCTET STRING?** Bytes **DER-encoded OCTET STRING** bên ngoài.
14. **Dùng `TrustAnchor(rootFromNetwork,null)` tùy tiện có an toàn không?** Không, vì đã tự tin một CA không được xác minh.
15. **`checkValidity()` có xác minh hostname/EKU/CRL không?** Không; chỉ kiểm tra thời hạn.
16. **Tại sao trong demo tắt revocation?** Để bộ fixture tạm không cần CRL/OCSP; hệ thống thực phải thiết lập chính sách revocation thích hợp.
17. **Một certificate được parse thành công bởi `CertificateFactory` có chắc được chấp nhận bởi `CertPathValidator` không?** Không, có thể fail critical, chain, signature, constraints, policy.
18. **Muốn dùng certificate cho HTTPS nên tự gọi một vài hàm KU/EKU không?** Không nên thay thế JSSE/TrustManager và hostname verification bằng checker đơn giản; phải dùng bộ xác minh giao thức đầy đủ.

## Tài liệu chuẩn và API chính thức

- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile: `4.2.1.3 Key Usage; `4.2.1.9 Basic Constraints; `4.2.1.12 EKU](https://www.rfc-editor.org/rfc/rfc5280.html)
- [X509Certificate (Java SE 21): getKeyUsage, getExtendedKeyUsage, getBasicConstraints](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Certificate.html)
- [X509Extension: getCriticalExtensionOIDs, hasUnsupportedCriticalExtension, getExtensionValue](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509Extension.html)
- [CertificateFactory: parse X.509 certificate và CertPath](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertificateFactory.html)
- [CertPathValidator và PKIXParameters](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/CertPathValidator.html)
- [TrustAnchor](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/TrustAnchor.html)
- [X509CertSelector (lọc theo KU, EKU, constraints — không thay path validation)](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/security/cert/X509CertSelector.html)
- [JSSE Reference Guide — TLS validation và trust managers](https://docs.oracle.com/en/java/javase/21/security/java-secure-socket-extension-jsse-reference-guide.html)
- [keytool: quản lý và cấp chứng thư demo](https://docs.oracle.com/en/java/javase/21/docs/specs/man/keytool.html)
