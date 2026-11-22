# 13.2 Phân biệt root, intermediate, leaf và chứng thư tự ký

## Mục tiêu

Bài học thuộc **13. Chứng thư X.509** trong Java Advance – security-cryptography. Bạn sẽ:

1. Phân biệt đúng **root CA certificate**, **intermediate CA certificate**, **leaf/end-entity certificate** và **self-signed certificate** theo vai trò của chúng trong một chuỗi tin cậy.
2. Hiểu sự khác nhau giữa **“chứng thư có chữ ký hợp lệ”**, **“chuỗi được xác minh tới một trust anchor”** và **“chứng thư thuộc đúng máy chủ/người dùng/dịch vụ mà ứng dụng mong đợi”**.
3. Đọc các trường X.509 quan trọng: `Subject`, `Issuer`, `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage` (EKU), `SubjectAlternativeName` (SAN), `NotBefore/NotAfter`, `SubjectKeyIdentifier` (SKI) và `AuthorityKeyIdentifier` (AKI).
4. Dùng **`keytool` và Java 17+** dựng một chuỗi giả lập root → intermediate → leaf, kiểm chứng chữ ký và chạy `CertPathValidator("PKIX")` với một trust anchor đúng/sai.
5. Nhận diện các lỗi phổ biến trong Java TLS, mTLS, PKIX và việc tin chứng thư tự ký mà chưa kiểm tra nguồn gốc.

> **Ý chính:** `self-signed` mô tả **cách chứng thư được ký**; `root`, `intermediate`, `leaf` mô tả **vai trò trong đường dẫn chứng thực**; `trusted` mô tả **chính sách tin cậy của ứng dụng**. Đó là các khái niệm liên quan, nhưng không đồng nghĩa.

## 1. Một chứng thư X.509 chứa thông tin gì?

**Chứng thư số X.509 (certificate)** là cấu trúc dữ liệu đã được ký, thường chứa:

- **Subject:** định danh chủ thể mà chứng thư mô tả; trong các use case TLS hiện đại, danh tính DNS/IP được kiểm tra chủ yếu theo **SAN**, không chỉ nhìn vào `CN`.
- **Subject public key information (SPKI):** public key và thuật toán liên quan của chủ thể; **không chứa private key**.
- **Issuer:** tên chủ thể được nêu là bên phát hành (ký) chứng thư.
- **Serial number:** số sê-ri do issuer gán trong phạm vi issuer.
- **Validity:** `NotBefore` và `NotAfter`, khoảng thời gian chứng thư dự kiến có hiệu lực.
- **Signature algorithm và signature value:** thuật toán/chữ ký của issuer lên phần **tbsCertificate** (*to-be-signed certificate*).
- **Extensions:** ví dụ `BasicConstraints`, `KeyUsage`, `ExtendedKeyUsage`, `SubjectAlternativeName`, `NameConstraints`, SKI/AKI và Certificate Policies.

Mỗi chứng thư có **public key của subject**, nhưng chữ ký chứng thư được xác minh bằng **public key của issuer**, ngoại trừ trường hợp tự ký thì hai khóa đó có thể trùng.

Khi một trình duyệt thấy chứng thư với subject là `service.example.test`, nó không chỉ kiểm tra “có chữ ký” mà cần xây dựng đường dẫn tin cậy và kiểm tra **đúng hostname**, thời hạn, mục đích sử dụng, policy, thuật toán và trạng thái thu hồi theo chính sách.

Chứng thư không phải khóa bí mật. Bạn có thể gửi chứng thư cho bên khác; **private key tương ứng phải được giữ kín** và không nằm trong PEM certificate. Đừng nhầm file `.crt/.cer/.pem` có certificate với keystore chứa private key hoặc PKCS#8 private-key file.

## 2. Sơ đồ chuỗi root → intermediate → leaf

Một cấu hình PKI phổ biến:

```text
                     TRUST STORE CỦA ỨNG DỤNG
                     +-----------------------+
                     | Root CA / Trust Anchor|
                     | ĐÃ được tin cậy trước |
                     +-----------+-----------+
                                 |
           Root private key ký certificate của Intermediate
                                 |
                                 v
                     +-----------------------+
                     | Intermediate CA       |
                     | BasicConstraints CA=1 |
                     | được Root xác nhận    |
                     +-----------+-----------+
                                 |
             Intermediate private key ký certificate của Leaf
                                 |
                                 v
                     +-----------------------+
                     | Leaf / End Entity     |
                     | service.example.test  |
                     | CA=0, SAN và EKU      |
                     +-----------------------+
                                 |
                      Leaf private key dùng
                     cho TLS hoặc chữ ký app
```

Trong mạng TLS thông thường, máy chủ gửi **leaf và các intermediate cần thiết**; root tin cậy thường đã có sẵn trong trust store phía client và **không cần được máy chủ gửi**. Chuỗi mà server gửi chưa chắc chính là đường dẫn cuối cùng được validator chọn (ví dụ khi có cross-sign); trình kiểm tra có thể phải xây hoặc chọn một path phù hợp với tập trust anchors tại client.

### Vai trò khác nhau

| Loại | Nhiệm vụ trong chuỗi | Thường ký cho ai? | Extension thường cần | Có cần là self-signed? |
| --- | --- | --- | --- | --- |
| **Root CA** | Điểm bắt đầu tin cậy (*trust anchor*) của một hệ thống PKI | Intermediate hoặc các CA khác | `BasicConstraints: CA=true`, `KeyUsage: keyCertSign` | **Không bắt buộc về mặt khái niệm trust anchor**; các root CA certificate thường tự ký |
| **Intermediate CA** | Cấp/chứng thực certificate ở tầng thấp hơn; phân quyền từ root | Intermediate khác hoặc leaf | `CA=true`, `keyCertSign`, `pathLenConstraint` nếu có | **Thường không**; nó được issuer phía trên ký |
| **Leaf / End-Entity** | Gắn public key với máy chủ, người dùng, dịch vụ hoặc ứng dụng cuối | Không đóng vai trò CA trong path đó | `CA=false`, SAN, EKU, KeyUsage phù hợp mục đích | **Thường không**; tuy nhiên có thể tự ký trong một số môi trường |
| **Self-signed certificate** | Mô tả **đặc tính chữ ký**, không phải một tầng cụ thể | Subject ký certificate của chính mình | Có thể `CA=true` hoặc `CA=false` tùy mục đích | **Theo định nghĩa là tự ký** |

Một **root CA** là vai trò theo *trust anchor được chọn*, không phải “mọi certificate có `Subject=Issuer`”. Một certificate tự ký có `CA=true` vẫn **không trở thành trust anchor chỉ vì nó tự ký**. Ngược lại, một tổ chức có thể chủ động tin một certificate/khóa không tự ký làm trust anchor nội bộ hoặc tin một intermediate làm anchor theo chính sách; `TrustAnchor` trong Java hỗ trợ cả certificate hoặc CA name/public key.

### CA khác với end entity ở đâu?

Certificate có `BasicConstraints` **CA=true** có thể đóng vai trò CA nếu các điều kiện path/KeyUsage/policy phù hợp. Một **leaf** thông thường có `BasicConstraints CA=false` hoặc không có quyền CA. Với Java `X509Certificate.getBasicConstraints()`:

- Trả **`-1`** nếu certificate không phải CA.
- Trả số **`>=0`** nếu certificate là CA; số này phản ánh mức `pathLenConstraint` được khai báo hoặc một giá trị đại diện khi không giới hạn.
- `pathLenConstraint=0` với intermediate nghĩa là không cho phép **CA trung gian không tự phát hành thêm** nằm dưới intermediate đó trong đường dẫn, nhưng vẫn có thể cấp certificate cho **leaf**.
- Trong path validation, ý nghĩa path length cần tuân theo RFC 5280, gồm quy tắc về các CA self-issued. Không tự kiểm tra path length bằng cách đếm tất cả certificate trong một mảng.

Một CA certificate còn thường có bit **`KeyUsage.keyCertSign`**, và validator phải áp dụng các constraint phù hợp. **`CA=true` đơn độc không có nghĩa ứng dụng phải tin hoặc certificate đó chắc chắn được phép cấp mọi loại certificate.**

## 3. Self-issued và self-signed không hoàn toàn giống nhau

Đây là sự phân biệt dễ bị bỏ qua:

- **Self-issued:** `Subject` và `Issuer` có cùng Distinguished Name (DN). Đó là một so sánh **tên**, không phải bằng chứng chữ ký.
- **Self-signed:** chữ ký trên certificate được tạo bằng private key tương ứng với **public key chứa trong chính certificate**, và chữ ký có thể được xác minh bằng public key đó. Thông thường subject và issuer cũng trùng tên.

Một certificate **self-issued nhưng không self-signed** có thể xuất hiện trong quá trình chuyển khóa (*CA key rollover*): tên CA không đổi nhưng certificate được ký bởi một khóa khác của cùng CA. Vì vậy không được coi `subject.equals(issuer)` là phép kiểm tra self-signed đầy đủ.

**Self-signed không đồng nghĩa self-trusted.** Ví dụ:

```text
Root-A tự ký hợp lệ. Client đã cài Root-A làm trust anchor.
=> Một path kết thúc ở Root-A có THỂ được tin nếu còn các policy khác.

Root-B tự ký hợp lệ. Client chưa hề phê duyệt/cài Root-B.
=> Root-B KHÔNG được tin chỉ vì chữ ký tự ký đúng.
```

Đối thủ có thể sinh vô số cặp khóa và certificate tự ký có chữ ký hợp lệ. Không có bài toán mật mã nào ngăn họ làm việc đó. Chính **phân phối trust anchor từ nguồn đã được kiểm soát** mới quyết định root nào đáng tin với ứng dụng.

### Vì sao root CA thường self-signed?

Đường dẫn certificate phải có điểm dừng. Root certificate tự ký tạo một định dạng đóng gói tiện lợi cho **public key và metadata của điểm tin cậy**; tuy nhiên **niềm tin không đến từ chữ ký của root lên chính nó**. Nó đến từ việc ứng dụng/hệ điều hành/tổ chức **đã chọn khóa/certificate đó làm trust anchor** thông qua cơ chế tin cậy bên ngoài.

Trong nhiều PKI, private key root được giữ offline hoặc trong HSM, intermediate thực hiện việc ký certificate thường ngày. Nếu intermediate bị lộ, nhà quản trị có thể thu hồi/thay intermediate mà không bắt buộc thay toàn bộ root; nhưng đó vẫn là sự cố nghiêm trọng ảnh hưởng các leaf đã cấp và yêu cầu quy trình revocation/rotation.

## 4. Signature link khác với một path tin cậy

Xem ba chứng thư:

```text
Root:         Subject = CN=Training Root CA
              Issuer  = CN=Training Root CA
Intermediate: Subject = CN=Training Intermediate CA
              Issuer  = CN=Training Root CA
Leaf:         Subject = CN=service.example.test
              Issuer  = CN=Training Intermediate CA
```

Các đường liên kết mật mã có thể kiểm tra:

- `intermediate.verify(root.getPublicKey())`: chữ ký của intermediate phù hợp public key root.
- `leaf.verify(intermediate.getPublicKey())`: chữ ký leaf phù hợp public key intermediate.
- `root.verify(root.getPublicKey())`: chữ ký root tự xác minh được nếu root là self-signed.

**Nhưng chỉ ba lời gọi `verify` trên chưa thiết lập được trust**:

- Bạn có thể đã lấy `root.pem` từ chính attacker. Cả ba chữ ký có thể đúng, nhưng root chưa được **tin cậy**.
- Có thể có intermediate `CA=false` hoặc `keyCertSign` không được cho phép. Từng chữ ký vẫn có thể khớp nhưng **đường dẫn không đạt constraint**.
- Certificate có thể hết hạn, chưa có hiệu lực, bị thu hồi hoặc dùng thuật toán không được policy cho phép.
- Leaf có thể hợp lệ cho hostname `service-b.example.test`, nhưng client cần kết nối `service-a.example.test`.
- Root được tin trong một **purpose/namespace** không đồng nghĩa có quyền cấp certificate cho mọi mục đích hoặc tenant.

**Xác minh một certificate signature** là thao tác cục bộ. **PKIX path validation** xét một đường dẫn certificate trong ngữ cảnh trust anchors và các constraints. **Xác minh danh tính dịch vụ/người dùng** là ràng buộc tiếp theo của ứng dụng/TLS.

## 5. Các trường X.509 nên đọc để xác định vai trò

| Field / extension | Vai trò | Điều không được suy diễn |
| --- | --- | --- |
| `Subject` | Tên chủ thể | Tên có thể được tự khai, không tự chứng minh danh tính |
| `Issuer` | Tên bên phát hành được khai báo | Trùng tên root không chứng minh certificate được root ký |
| `AuthorityKeyIdentifier` (AKI) | Hỗ trợ tìm public key/certificate của issuer thích hợp | AKI không tự là trust anchor hoặc bằng chứng path hợp lệ |
| `SubjectKeyIdentifier` (SKI) | Định danh khóa chủ thể, hỗ trợ dựng path | Cùng một SKI không chứng minh đã được tin cậy |
| `BasicConstraints` | Phân biệt CA, ràng buộc số CA ở dưới | `CA=true` không tự cấp niềm tin |
| `KeyUsage` | Các mục đích khóa như `digitalSignature`, `keyCertSign`, `keyEncipherment` | Một certificate chỉ có public key RSA không mặc nhiên cho phép mọi usage |
| `ExtendedKeyUsage` (EKU) | Mục đích như `serverAuth`, `clientAuth`, `codeSigning` | `serverAuth` không tự cấp quyền ký bản cập nhật ứng dụng |
| `SubjectAlternativeName` (SAN) | Danh tính DNS/IP/email/URI theo profile | Chỉ nhìn CN hoặc một SAN bất kỳ không đủ để khớp hostname |
| `NotBefore` / `NotAfter` | Khoảng thời gian hiệu lực | Trong hạn không đồng nghĩa chưa bị thu hồi |
| `CRLDistributionPoints` / `AuthorityInfoAccess` | Gợi ý điểm lấy CRL/OCSP/certificate issuer | Có URL trong extension không đảm bảo client đã thực hiện revocation checks |
| `CertificatePolicies` / `NameConstraints` | Ràng buộc policy, namespace | Không thể bỏ qua critical extension không hiểu mà vẫn coi path hợp lệ |

Một chain phù hợp còn phải có **chữ ký đúng giữa từng tầng**, **issuer/subject linkage**, hỗ trợ thuật toán phù hợp, các critical extensions được xử lý đúng, BasicConstraints/KeyUsage/policy và **trust anchor đã chọn**.

### Root / intermediate không chỉ dựa vào tên

Thấy subject chứa chữ `Root` không có nghĩa certificate đó là root. Thấy `Issuer=Subject` không chắc nó self-signed. Thấy một certificate `CA=true` không chắc nó nằm ở tầng intermediate; **cùng certificate CA có thể là intermediate trong một path, nhưng được tổ chức khác chủ động dùng làm trust anchor trong một path khác**. Vai trò phụ thuộc **đường dẫn/chính sách**, không phải nhãn trong DN.

### Leaf không nhất thiết là chứng thư server TLS

Leaf có thể là certificate cho **client mTLS**, ký code, ký tài liệu, xác thực người dùng hoặc thiết bị. EKU/KeyUsage và quy tắc định danh cần phù hợp đúng use case. Ví dụ `serverAuth` thuộc OID **`1.3.6.1.5.5.7.3.1`**, còn `clientAuth` là **`1.3.6.1.5.5.7.3.2`**. Một leaf có thể có hoặc không có một EKU cụ thể theo profile; không tự coi “leaf” là “web server”.

## 6. PKIX path validation trong Java

Java cung cấp API chuẩn để parse certificate và xác thực đường dẫn:

- `CertificateFactory.getInstance("X.509")`: parse PEM/DER certificate, hoặc tạo `CertPath` từ danh sách certificate.
- `X509Certificate`: đọc `getSubjectX500Principal()`, `getIssuerX500Principal()`, `getBasicConstraints()`, `getKeyUsage()`, `getExtendedKeyUsage()`, `getSubjectAlternativeNames()`, `getNotBefore()/getNotAfter()`.
- `X509Certificate.verify(issuerPublicKey)`: kiểm tra chữ ký **của certificate** bằng public key issuer; **không** kiểm tra path, trust, hostname hay revocation đầy đủ.
- `CertPathValidator.getInstance("PKIX")`: validate một **đường dẫn certificate đã có** với `PKIXParameters`.
- `CertPathBuilder.getInstance("PKIX")`: thử **xây một path** từ certificate/CertStore và trust anchor theo cấu hình; không đồng nghĩa “luôn tự lấy được intermediate trên Internet”.
- `TrustAnchor`: certificate/CA key mà ứng dụng **đã quyết định tin**, không phải certificate chỉ vì nó self-signed.
- `KeyStore` và `TrustManagerFactory`: lưu/provision trust anchors và tích hợp JSSE/TLS; không nhầm **truststore** với **keystore private key**.

**Thứ tự `CertPath` cho PKIX thông thường:** leaf trước, các intermediate tiếp theo, và **trust anchor thường không nằm trong danh sách certificate của path** vì đã được cung cấp riêng trong `PKIXParameters`. Một số hệ thống server gửi root certificate thừa; việc root có trong handshake không có nghĩa client coi nó đáng tin.

### Ba kiểm tra độc lập

```text
X509Certificate.verify(issuerKey)
         |
         v
[Certificate signature hợp lệ?]
         |
         v
PKIX path validation với trust anchors của client
         |
         v
[Root tin cậy? CA constraints? time/policy? revocation policy?]
         |
         v
Endpoint / identity verification
         |
         v
[DNS SAN/IP/issuer identity/role đúng expected target?]
         |
         v
Authorization / application policy
         |
         v
[Được phép truy cập resource/hành động này?]
```

Nếu thiếu bước **endpoint identity**, một certificate hợp lệ trong chuỗi CA có thể bị chấp nhận cho **sai máy chủ**. Nếu thiếu bước **trust anchor**, kẻ tấn công có thể tự cấp chain cho chính mình. Nếu thiếu bước **authorization**, chứng thư hợp lệ vẫn có thể thực hiện hành động vượt quyền.

## 7. Thực hành Java 17: dựng root → intermediate → leaf và một root không được tin

Bài thực hành dùng **`keytool` đi kèm JDK** và **Java 17**. Bạn tạo bốn cặp khóa **chỉ dành cho thử nghiệm**:

1. `root`: CA tự ký với `BasicConstraints CA=true` và `pathLen=1`.
2. `intermediate`: lúc sinh keypair có certificate tạm tự ký; sau đó tạo CSR, **root ký certificate mới** và import certificate reply vào cùng alias. Kết quả **không còn self-signed**.
3. `leaf`: tương tự, certificate cuối do **intermediate ký**, có `SAN=dns:service.example.test` và `EKU=serverAuth`. Leaf **không phải CA**.
4. `rogue`: CA tự ký độc lập có chữ ký hoàn toàn đúng, nhưng **không phải trust anchor được chọn** khi xác minh chain root → intermediate → leaf.

**Không dùng keystore thử nghiệm, mật khẩu `changeit`, root giả lập hoặc private key của lab trong production.** Chỉ làm trong một thư mục dùng riêng, có thể xóa sau khi kiểm thử.

### 7.1 Tạo certificate bằng PowerShell trên Windows

Mở PowerShell trong terminal có `keytool.exe` từ JDK và chạy **toàn bộ đoạn** dưới đây. Script tạo thư mục riêng trong `%TEMP%`, keystore PKCS#12 `chain.p12` và bốn file PEM. Nó không truy cập internet. Nếu chạy lại, keystore của **lab** trong thư mục tạm được tạo lại; tránh đặt tài liệu cá nhân vào cùng thư mục.

```powershell
$ErrorActionPreference = "Continue"
$qaPath = Join-Path $env:TEMP 'x509-roles-training'
New-Item -ItemType Directory -Force -Path $qaPath | Out-Null
Set-Location $qaPath
$p = "changeit"

function Invoke-Keytool([string[]]$params) {
    $result = & keytool.exe @params 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw ("keytool failed: " + ($params -join " ")
               + " :: " + ($result -join " "))
    }
}

if (Test-Path -LiteralPath 'chain.p12') {
    Remove-Item -LiteralPath 'chain.p12' -Force
}

Invoke-Keytool @("-genkeypair","-alias","root","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Training Root CA,O=Training",
    "-ext","BC=ca:true,pathlen:1",
    "-ext","KU=keyCertSign,cRLSign",
    "-storetype","PKCS12","-keystore","chain.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Invoke-Keytool @("-genkeypair","-alias","intermediate","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Training Intermediate CA,O=Training",
    "-ext","BC=ca:true,pathlen:0",
    "-ext","KU=keyCertSign,cRLSign",
    "-storetype","PKCS12","-keystore","chain.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Invoke-Keytool @("-certreq","-alias","intermediate",
    "-file","intermediate.csr","-keystore","chain.p12","-storepass",$p)

Invoke-Keytool @("-gencert","-alias","root",
    "-infile","intermediate.csr","-outfile","intermediate-signed.pem",
    "-rfc","-validity","600",
    "-ext","BC=ca:true,pathlen:0",
    "-ext","KU=keyCertSign,cRLSign",
    "-keystore","chain.p12","-storepass",$p)

Invoke-Keytool @("-importcert","-alias","intermediate",
    "-file","intermediate-signed.pem",
    "-keystore","chain.p12","-storepass",$p,"-noprompt")

Invoke-Keytool @("-genkeypair","-alias","leaf","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=service.example.test,O=Training",
    "-ext","SAN=dns:service.example.test",
    "-ext","EKU=serverAuth",
    "-ext","KU=digitalSignature,keyEncipherment",
    "-storetype","PKCS12","-keystore","chain.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

Invoke-Keytool @("-certreq","-alias","leaf","-file","leaf.csr",
    "-keystore","chain.p12","-storepass",$p)

Invoke-Keytool @("-gencert","-alias","intermediate",
    "-infile","leaf.csr","-outfile","leaf-signed.pem",
    "-rfc","-validity","90",
    "-ext","SAN=dns:service.example.test",
    "-ext","EKU=serverAuth",
    "-ext","KU=digitalSignature,keyEncipherment",
    "-keystore","chain.p12","-storepass",$p)

Invoke-Keytool @("-importcert","-alias","leaf",
    "-file","leaf-signed.pem",
    "-keystore","chain.p12","-storepass",$p,"-noprompt")

Invoke-Keytool @("-genkeypair","-alias","rogue","-keyalg","RSA",
    "-keysize","2048","-validity","3650",
    "-dname","CN=Untrusted Root CA,O=Training",
    "-ext","BC=ca:true,pathlen:1",
    "-ext","KU=keyCertSign,cRLSign",
    "-storetype","PKCS12","-keystore","chain.p12",
    "-storepass",$p,"-keypass",$p,"-noprompt")

foreach ($alias in @("root","intermediate","leaf","rogue")) {
    Invoke-Keytool @("-exportcert","-alias",$alias,"-rfc",
        "-file",("$alias.pem"),"-keystore","chain.p12","-storepass",$p)
}
Get-ChildItem -Name '*.pem'
```

Kết quả cần có các file:

```text
intermediate-signed.pem
leaf-signed.pem
root.pem
intermediate.pem
leaf.pem
rogue.pem
```

Tên file được liệt kê theo cách sắp xếp của hệ thống; **không** cần tin vào thứ tự hiển thị. `intermediate-signed.pem` và `leaf-signed.pem` là certificate replies trung gian; bốn file `root.pem`, `intermediate.pem`, `leaf.pem` và `rogue.pem` được lớp Java bên dưới đọc. Phần output “Generating...”, “Certificate reply was installed...” của `keytool` phụ thuộc JDK/OS và không phải stdout cố định của bài.

**Lưu ý:** Trong bài thực hành, root/intermediate/leaf ban đầu được tạo với keystore chứa **private key** để có thể ký CSR. Sau khi thay certificate reply, private key của từng alias vẫn do keystore lưu. **Certificate PEM xuất bằng `-exportcert` chỉ chứa public certificate**, không chứa private key. Một CA thực phải có kiểm soát nghiêm ngặt riêng cho khóa root/intermediate (HSM, role, key ceremony, phát hành và revoke).

Trên Linux/macOS, ý tưởng tương tự với `keytool` và câu lệnh shell tương đương; khối bên trên là script **PowerShell dành cho Windows** nên không thể dán nguyên vào Bash.

### 7.2 Java 17: đọc certificate, kiểm tra CA và validate PKIX

Tại chính thư mục chứa bốn file PEM, tạo file **`CertificateRolesDemo.java`** có nội dung:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.GeneralSecurityException;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.CertPathValidatorException;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.List;
import java.util.Set;

public final class CertificateRolesDemo {
    public static void main(String[] args) throws Exception {
        X509Certificate root = load("root.pem");
        X509Certificate intermediate = load("intermediate.pem");
        X509Certificate leaf = load("leaf.pem");
        X509Certificate untrustedRoot = load("rogue.pem");

        root.checkValidity();
        intermediate.checkValidity();
        leaf.checkValidity();

        System.out.println("Root self-signed: " + selfSigned(root));
        System.out.println("Intermediate self-signed: " + selfSigned(intermediate));
        System.out.println("Leaf self-signed: " + selfSigned(leaf));
        System.out.println("Other root self-signed: " + selfSigned(untrustedRoot));
        System.out.println("Root is CA: " + (root.getBasicConstraints() >= 0));
        System.out.println("Intermediate is CA: "
                + (intermediate.getBasicConstraints() >= 0));
        System.out.println("Leaf is CA: " + (leaf.getBasicConstraints() >= 0));

        intermediate.verify(root.getPublicKey());
        leaf.verify(intermediate.getPublicKey());
        System.out.println("Intermediate signature by root: true");
        System.out.println("Leaf signature by intermediate: true");

        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        CertPath path = factory.generateCertPath(List.of(leaf, intermediate));
        System.out.println("PKIX with trusted root: " + validates(path, root));
        System.out.println("PKIX with unrelated root: "
                + validates(path, untrustedRoot));

        boolean dnsMatch = leaf.getSubjectAlternativeNames().stream()
                .anyMatch(entry -> Integer.valueOf(2).equals(entry.get(0))
                        && "service.example.test".equals(entry.get(1)));
        boolean serverAuth = leaf.getExtendedKeyUsage() != null
                && leaf.getExtendedKeyUsage()
                        .contains("1.3.6.1.5.5.7.3.1");
        System.out.println("Leaf SAN contains expected DNS: " + dnsMatch);
        System.out.println("Leaf EKU allows serverAuth: " + serverAuth);
    }

    private static X509Certificate load(String name) throws Exception {
        CertificateFactory factory = CertificateFactory.getInstance("X.509");
        try (InputStream in = Files.newInputStream(Path.of(name))) {
            return (X509Certificate) factory.generateCertificate(in);
        }
    }

    private static boolean selfSigned(X509Certificate certificate) {
        if (!certificate.getSubjectX500Principal()
                .equals(certificate.getIssuerX500Principal())) {
            return false;
        }
        try {
            certificate.verify(certificate.getPublicKey());
            return true;
        } catch (GeneralSecurityException e) {
            return false;
        }
    }

    private static boolean validates(CertPath path, X509Certificate anchor)
            throws GeneralSecurityException {
        PKIXParameters params = new PKIXParameters(
                Set.of(new TrustAnchor(anchor, null)));
        // Only for an offline teaching example without CRL/OCSP.
        params.setRevocationEnabled(false);
        try {
            CertPathValidator.getInstance("PKIX").validate(path, params);
            return true;
        } catch (CertPathValidatorException e) {
            return false;
        }
    }
}
```

Biên dịch/chạy ở PowerShell (vẫn ở thư mục `x509-roles-training`):

```powershell
javac --release 17 CertificateRolesDemo.java
java -cp . CertificateRolesDemo
```

**Stdout Java đã được kiểm thử trên fixture `keytool` tạo như trên:**

```text
Root self-signed: true
Intermediate self-signed: false
Leaf self-signed: false
Other root self-signed: true
Root is CA: true
Intermediate is CA: true
Leaf is CA: false
Intermediate signature by root: true
Leaf signature by intermediate: true
PKIX with trusted root: true
PKIX with unrelated root: false
Leaf SAN contains expected DNS: true
Leaf EKU allows serverAuth: true
```

Lưu ý kết quả phụ thuộc JDK/provider hỗ trợ RSA, X.509, PKIX, keytool options và độ hiệu lực của certificates trong ví dụ; các certificate được tạo mới với thời hạn 90/600/3650 ngày nên bình thường sẽ còn hiệu lực khi chạy ngay. Bài thực hành **không** kết nối tới domain `service.example.test` và **không** đăng ký root giả lập này với hệ điều hành.

### 7.3 Vì sao mỗi dòng quan trọng?

1. **`Root self-signed: true`**: root có subject/issuer cùng tên **và** chữ ký xác minh được bằng public key của chính root. Đây là sự kiện mật mã, **không phải nguyên nhân root đáng tin**.
2. **`Intermediate self-signed: false` và `Leaf self-signed: false`**: sau khi import certificate replies, chúng được cấp bởi CA phía trên, dù lúc tạo keypair trước đó `keytool` đã tạo các certificate placeholder tự ký.
3. **`Other root self-signed: true`**: root “rogue” tự ký có chữ ký đúng; bản thân chữ ký tự ký không phân biệt được một CA được ứng dụng phê duyệt với một CA do người khác tự sinh.
4. **`Root is CA: true`; `Intermediate is CA: true`; `Leaf is CA: false`**: `getBasicConstraints()` phản ánh quyền CA trong certificate, không căn cứ vào chữ “root/intermediate/leaf” trong subject.
5. **`Intermediate signature by root: true`; `Leaf signature by intermediate: true`**: hai lời gọi `verify` đơn chứng minh *certificate signature links*, **không đủ để thay cho PKIX**.
6. **`PKIX with trusted root: true`**: path `leaf → intermediate` đạt kiểm tra PKIX khi `root` được **ứng dụng chủ động chọn** làm `TrustAnchor`.
7. **`PKIX with unrelated root: false`**: vẫn chính path đó nhưng trust anchor được thay bằng một CA tự ký khác; path không kết thúc ở root được tin, nên bị từ chối. Đây là bằng chứng bài học quan trọng nhất.
8. **`Leaf SAN contains expected DNS: true` và `Leaf EKU allows serverAuth: true`**: đọc riêng hai extension liên quan use case TLS. **Chúng không phải một bộ kiểm tra hostname/endpoint hoàn chỉnh**; code chỉ kiểm tra một DNS literal trong fixture.

**Quan trọng với `selfSigned`:** hàm ví dụ yêu cầu `Subject DN=Issuer DN` rồi gọi `certificate.verify(certificate.getPublicKey())`. Việc kiểm tra đúng sự tự ký về mặt mật mã **không** tạo trust. Với các certificate/provider có cách biểu diễn DN/khóa đặc biệt hoặc signature algorithm không được hỗ trợ, có thể cần xử lý thêm lỗi; đây là phương pháp minh họa chuẩn cho fixture đã tạo.

### 7.4 Vì sao bài thực hành tắt revocation?

Lệnh `params.setRevocationEnabled(false)` chỉ dùng để demo **offline** vì các certificate tự tạo ở đây không có hệ thống CRL/OCSP thật. Nó **không phải khuyến nghị production**. Trong môi trường thực, định nghĩa chính sách kiểm tra thu hồi phù hợp, các nguồn CRL/OCSP, timeout, cache, chế độ fail-open/fail-closed theo threat model, cũng như xử lý sự cố CA/key bị thu hồi. Mọi bước path/identity/role/freshness đều cần quyết định rõ ràng; một mã demo có `PKIX validates==true` **không tự đạt đủ tất cả yêu cầu TLS**.

**Trust anchor validity:** root certificate trong code được gọi `root.checkValidity()` tường minh. Trust anchor là đầu vào được tin cậy từ trước của `CertPathValidator`; không mặc định nó được kiểm tra tất cả các trường/điều kiện theo cùng quy tắc như certificate nằm trong path. Vòng đời root/trust store là policy riêng của ứng dụng.

## 8. Java API nào trả lời câu hỏi nào?

| API | Nó kiểm tra/làm gì? | Nó **không** làm gì? |
| --- | --- | --- |
| `CertificateFactory.generateCertificate` | Parse PEM/DER X.509 thành object | Không xác thực issuer hoặc trust |
| `X509Certificate.getSubjectX500Principal` | Trả subject DN | Không chứng minh subject là danh tính đúng |
| `X509Certificate.getIssuerX500Principal` | Trả issuer DN | Không chứng minh issuer thực sự ký |
| `X509Certificate.getBasicConstraints` | Trả CA/path length constraint, hoặc `-1` | Không quyết định CA có đáng tin |
| `X509Certificate.getKeyUsage/getExtendedKeyUsage` | Trả mục đích được extension khai báo | Không thay thế validation toàn bộ chain/policy |
| `X509Certificate.getSubjectAlternativeNames` | Đọc SAN entries theo kiểu | Không tự so hostname theo quy tắc TLS |
| `X509Certificate.checkValidity` | Kiểm tra NotBefore/NotAfter ở thời điểm xét | Không kiểm tra chữ ký, revocation, trust hoặc identity |
| `X509Certificate.verify(issuerKey)` | Kiểm tra chữ ký certificate bằng khóa issuer | Không tự dựng/validate chuỗi hoặc chọn trust anchor |
| `CertPathValidator.validate(path, params)` | Áp dụng thuật toán PKIX lên path với trust anchors/params | Không tự là bộ kiểm tra hostname, app authorization hoặc tự tạo trust |
| `CertPathBuilder.build(params)` | Tìm một path phù hợp theo chứng thư/cert stores/constraints được cấu hình | Không cam kết lấy được mọi issuer qua mạng |
| `TrustManagerFactory` / JSSE | Liên kết chính sách tin certificate chain vào TLS | Vẫn cần cấu hình endpoint identification và policy service đúng use case |

Đoạn dưới đây **chỉ minh họa khởi tạo PKIX validator**, không độc lập và chưa thực hiện đường dẫn:

```java
CertPathValidator validator = CertPathValidator.getInstance("PKIX");
// Cần CertPath, PKIXParameters và trust anchors được chuẩn bị đáng tin.
// Cũng cần identity/hostname, purpose, revocation policy theo use case.
```

Không tạo `new TrustAnchor(certFromNetwork, null)` rồi dùng nó để “xác minh” chính certificate do network gửi: như vậy đưa **dữ liệu chưa tin cậy** thành điểm tin cậy và vô hiệu hóa mục đích của PKI.

## 9. TLS, mTLS và danh tính certificate

### 9.1 HTTPS server: chain hợp lệ chưa đủ

Client HTTPS có thể gặp hai certificate đều được root đáng tin ký:

```text
CN=service-a.example.test, SAN=DNS:service-a.example.test
CN=service-b.example.test, SAN=DNS:service-b.example.test
```

Cả hai có thể có path PKIX hợp lệ. Nhưng khi client kết nối tới **`service-a.example.test`**, certificate của **service-b** không được chấp nhận chỉ vì cùng CA. **Endpoint identity verification** phải khớp DNS/IP từ URL/kết nối tới SAN với quy tắc theo chuẩn áp dụng; không chỉ so raw `CN`.

Trong JSSE, cách thực hiện endpoint identification phụ thuộc API/socket/engine và cấu hình client. Ví dụ snippet dưới đây dành cho **client `SSLSocket` hoặc `SSLEngine` đã có**, không phải chương trình độc lập:

```java
SSLParameters parameters = sslSocket.getSSLParameters();
parameters.setEndpointIdentificationAlgorithm("HTTPS");
sslSocket.setSSLParameters(parameters);
// Sau đó thực hiện TLS handshake với trust manager đúng policy.
```

Cần import `javax.net.ssl.SSLParameters`, có `sslSocket` hợp lệ và truststore an toàn. Các HTTP client tiêu chuẩn thường đã có hành vi xác thực hostname riêng; **không tắt hostname verification/trust manager để sửa lỗi certificate**. Nếu dùng hostname verifier tùy chỉnh, nó phải tuân thủ giao thức thay vì `return true`.

### 9.2 mTLS client: cert chain hợp lệ không tự cấp quyền

mTLS xác thực chứng thư ở **cả hai phía** khi cấu hình yêu cầu client certificate. Dù client cert có path hợp lệ, server vẫn phải ánh xạ danh tính được phép từ SAN/subject/PKI policy sang **tài khoản, service, role, tenant và quyền tài nguyên**. Một client có cert hợp lệ từ cùng CA không mặc nhiên được đọc dữ liệu của tenant khác.

Tương tự, `ExtendedKeyUsage=serverAuth` dùng cho TLS server khác `clientAuth` dành cho client. Một certificate chỉ phù hợp với một mục đích không tự được chấp nhận trong mục đích khác. Cần dùng trust manager/certificate policy đúng theo role, không chỉ “bất kỳ cert nào chain tới CA chung”.

### 9.3 Self-signed cert trong môi trường dev

Certificate tự ký cho localhost/dev có thể chấp nhận trong **một trust model hẹp** nếu fingerprint/public key đã được phân phối đáng tin và ứng dụng cố ý tin nó. Nhưng:

- Không dùng `X509TrustManager` luôn chấp nhận mọi chain.
- Không tắt hostname check toàn cục.
- Không import bừa certificate từ email/URL do người gửi chưa được xác thực.
- Phải giới hạn trust theo môi trường, hostname/purpose; tránh đưa CA test vào trust store production.

## 10. Chẩn đoán lỗi certificate và chain

| Triệu chứng | Nguồn gốc cần xem | Hành động phù hợp |
| --- | --- | --- |
| `PKIX path building failed` hoặc `unable to find valid certification path` | Client không tìm được path về trust anchor đã cài; intermediate thiếu/issuer sai hoặc policy | Kiểm tra truststore/trust anchors, intermediate được gửi, path constraints và log chẩn đoán; **không** tự tin root do server gửi |
| `CertPathValidatorException` với path cụ thể | Signature, validity, constraints, policies, revocation hoặc trust mismatch | Đọc lý do/`index` để debug nội bộ; xác minh chuỗi và chính sách |
| `CertificateExpiredException` / `CertificateNotYetValidException` | Thời gian `NotAfter/NotBefore` không hợp lệ với thời điểm xét | Kiểm tra hệ thống đồng hồ, renew/replace cert đúng quy trình |
| Certificate là self-signed nhưng `verify(selfPublicKey)` pass | Certificate tự ký có chữ ký đúng | **Chưa đủ để tin**; phải có pin/trust anchor được provision hợp lệ |
| `CA=false` ở intermediate | Extension BasicConstraints không cho phép cấp chứng thư tầng dưới | Phát hành lại intermediate hợp lệ; không bỏ qua constraints |
| CA có `KeyUsage` nhưng thiếu `keyCertSign` khi bị yêu cầu | Key không được cấp đúng vai trò CA | Sửa profile CA, không chỉ thêm ca vào truststore |
| Root đáng tin nhưng hostname mismatch | Certificate có SAN khác hostname đích | Sửa cấp phát SAN hoặc hostname truy cập, không tắt endpoint identification |
| Chain OK nhưng leaf không có `serverAuth` khi policy yêu cầu | EKU/mục đích sử dụng không phù hợp | Cấp leaf theo profile đúng, không coi chain là đủ |
| Chain đúng nhưng thiếu CRL/OCSP trong môi trường yêu cầu | Revocation data không khả dụng hoặc cấu hình không nhất quán | Thiết kế policy, mạng/cache/timeouts, không tự tắt toàn bộ xác minh |
| Máy khác validate, máy này không | Truststore khác, clock skew, provider, thuật toán, intermediates hoặc policy khác | So sánh JDK, trust anchors, endpoint, version/chain; không log private keys |
| Self-issued có `Subject=Issuer` nhưng `verify(selfKey)` lỗi | Không phải self-signed hoặc dữ liệu/chữ ký khác | Xét rollover/cross-sign, không kết luận chỉ từ chuỗi DN |

**Đừng trả thông tin bí mật hoặc bật tính năng “trust all” trên môi trường thật.** Log nên chứa certificate fingerprint (không phải private key), issuer/subject ở mức phù hợp, key ID, expected hostname, failure category và correlation ID. Cẩn thận với log chứa danh tính hoặc metadata nhạy cảm; làm sạch và kiểm soát quyền xem log.

## 11. Cross-signing, root rollover và trust anchor mới

Một tổ chức có thể cấp certificate cho **cùng một intermediate public key** dưới nhiều issuer khác nhau (*cross-signing*) hoặc phát hành certificate self-issued để **chuyển đổi khóa CA**. Hệ quả:

- **Không phải lúc nào cũng có một đường path duy nhất** từ leaf tới root. Các client có trust stores khác nhau có thể chọn các path hợp lệ khác nhau.
- Root có thể được thay thế qua cập nhật truststore của OS/JDK hoặc qua quá trình phân phối policy của tổ chức. Việc phân phối đó **phải đáng tin**, không dựa trên một root tự ký mới do peer bất kỳ gửi.
- Một CA **có thể đóng vai intermediate trong path A nhưng được coi là trust anchor trong path B** vì tổ chức B trực tiếp tin CA đó. Trust anchor là **đầu vào policy của validator**.
- SKI/AKI giúp chọn issuer nhưng không bảo đảm chữ ký/trust; subject/issuer DN có thể giống nhau trong key rollover. Phải xác minh đúng key và signature.
- Việc root/intermediate đổi certificate, key hay thuật toán có thể khiến thiết bị cũ chưa cập nhật truststore không xây được path, dù server vẫn có một chain hợp lệ cho client khác.
- **Chứng thư cross-signed không đồng nghĩa “hai CA được tin như nhau”**; chỉ những trust anchors thực sự được cấu hình ở client mới có quyền kết thúc path.

Khi triển khai thay CA hoặc intermediate, cần thử nhiều client/JDK/truststore, expiration và thuật toán yếu trong path, sắp xếp intermediate, backup và rollback; đừng thử nghiệm bằng cách vô hiệu hóa kiểm tra certificate rồi phát hành production.

## 12. Những lỗi nhận thức cần tránh

1. **“Subject=Issuer nên đây là root đáng tin.”** Sai: đó chỉ là dấu hiệu self-issued. Chữ ký tự ký phải kiểm tra riêng; trust anchor phải do ứng dụng chọn.
2. **“Certificate tự ký thì luôn nguy hiểm hoặc luôn không hợp lệ.”** Không chính xác: nó có thể được tin có chủ đích sau provisioning an toàn; nguy hiểm là *tự động tin một certificate mới nhận*.
3. **“Intermediate chứng nhận được leaf thì intermediate là root.”** Sai: intermediate có quyền do CA phía trên cấp, chịu path constraints; root là trust anchor theo policy.
4. **“Leaf không có quyền cấp cert thì không ký gì được.”** Sai: leaf có thể dùng private key **ký thông điệp/TLS handshake** theo KeyUsage/EKU, nhưng không được dùng như CA phát hành certificate nếu `CA=false`.
5. **“Nếu chữ ký leaf.verify(intermediateKey) đúng thì HTTPS an toàn.”** Sai: thiếu trust root, path constraints, hostname, EKU, validity, revocation và đúng chính sách ứng dụng.
6. **“Root nằm trong certificate chain server gửi nên nó là trusted root.”** Sai: trust không đến từ server. Root phải xuất phát từ truststore/policy đã được provision.
7. **“CertPathValidator kiểm tra hostname giúp tôi.”** Sai trong cách dùng API tổng quát: path validation không thay thế JSSE endpoint identification hoặc hostname verifier đúng.
8. **“`getBasicConstraints() >= 0` là đủ để CA cấp bất kỳ cert nào.”** Sai: còn KeyUsage, pathLen, name constraints, policies, signature, validity và trust.
9. **“Nếu thấy path validation fail, cứ nhập certificate lạ vào cacerts.”** Sai: việc thay đổi trust anchors là quyết định bảo mật cao, phải xác minh nguồn gốc và phạm vi tin cậy.
10. **“Thấy revocation gây lỗi thì tắt vĩnh viễn.”** Sai: đó là chính sách có rủi ro và phải được thiết kế/đánh giá, không phải cách sửa tự động.
11. **“Có cert PEM thì ứng dụng đã có private key để ký.”** Sai: public certificate không chứa private key; key material được lưu nơi khác.
12. **“X.509 certificate giống public key SPKI.”** Sai: certificate có thêm issuer, validity, signature/extensions; public key SPKI chỉ mang khóa và thông số thuật toán.
13. **“Wildcard SAN/DNS chỉ cần so chuỗi đơn giản.”** Sai: hostname verification dùng quy tắc cụ thể về DNS/IP, wildcard, encoding, IDNA; đừng tự thay thế bằng `String.contains(...)`.
14. **“Một certificate root tự ký có chữ ký hợp lệ chứng minh danh tính tổ chức.”** Sai: bất kỳ bên nào cũng có thể sinh certificate tự ký với `O`/`CN` tùy ý; nguồn trust anchor mới tạo niềm tin.

## 13. Checklist dùng trong ứng dụng Java

- [ ] Xác định **expected identity** (hostname, service name, client identity) từ ngữ cảnh đáng tin, không từ certificate/claim chưa được xác minh.
- [ ] Trust anchors đến từ truststore/policy được phân phối và quản lý đáng tin, không lấy trực tiếp từ chain peer.
- [ ] Leaf và các intermediate được parse đúng và xây path phù hợp; root/trust anchor không được tự gán theo subject string.
- [ ] Đánh giá chữ ký từng link, `BasicConstraints`, `KeyUsage`, `pathLenConstraint`, name/policy constraints và thuật toán.
- [ ] Kiểm tra `NotBefore/NotAfter` theo thời gian, kế hoạch renew và policy revocation.
- [ ] TLS server: xác thực SAN của **hostname thực sự kết nối**; không tắt JSSE endpoint identification.
- [ ] mTLS: phân biệt `serverAuth`/`clientAuth` và gắn identity đã xác thực vào tenant/role/authorization.
- [ ] Kiểm tra quy trình root/intermediate rotation, cross-sign, thay truststore giữa các client/JDK.
- [ ] Không tin certificate tự ký chỉ vì `cert.verify(cert.getPublicKey())` trả thành công.
- [ ] Không cho ứng dụng tự thêm root vào truststore từ một URL, request body hoặc chứng thư do attacker tự cung cấp.
- [ ] Kiểm tra CRL/OCSP/short-lived certificates theo chính sách, không dùng cài đặt offline demo để thay production.
- [ ] Bảo vệ khóa CA, root offline/HSM, phân quyền phát hành leaf, quản lý audit, backup, revocation và response khi key lộ.

## 14. Bài tập thực hành

1. Chạy script `keytool` và `CertificateRolesDemo`. Vì sao **`Other root self-signed: true`** vẫn đồng thời cho **`PKIX with unrelated root: false`**? Đây là minh họa cho sự khác nhau nào?
2. Sau khi tạo certificate tạm cho `intermediate` bằng `-genkeypair`, trước khi import certificate reply, nó có self-signed không? Vì sao sau khi root ký và import lại, câu trả lời đổi thành `false`?
3. Kiểm tra `root.getBasicConstraints()`, `intermediate.getBasicConstraints()` và `leaf.getBasicConstraints()`. Giải thích ý nghĩa pathLen root 1, intermediate 0, leaf -1. Vì sao intermediate vẫn có thể ký leaf?
4. Thử dùng `leaf.verify(root.getPublicKey())` thay cho intermediate public key. Dự đoán kết quả và giải thích vì sao tên issuer/link chữ ký phải khớp khóa phát hành.
5. Đổi trust anchor từ root sang một certificate tự ký mới do bạn tạo. Vì sao path validation fail dù root mới `verify(selfKey)` thành công?
6. Đổi `SAN=dns:service.example.test` thành một tên khác khi phát hành leaf. Giữ nguyên root/intermediate và kiểm tra riêng path PKIX và expected hostname; vì sao **hai kết luận khác nhau**?
7. Thử phát hành intermediate **không có BasicConstraints CA=true** rồi yêu cầu nó ký leaf. PKIX cần bảo vệ điều gì và vì sao chỉ `leaf.verify(intermediateKey)` chưa đủ?
8. Thiết kế một mTLS service cấp client cert từ cùng CA. Những bước nào biến “path hợp lệ” thành “client được phép gọi API quản trị”?
9. Viết một bản ghi trust anchor inventory gồm owner, fingerprint SPKI/cert, algorithm, mục đích, ngày hết hạn, rotation plan, cách cập nhật tin cậy và cách thu hồi.
10. Mô tả quá trình đổi intermediate trong hệ thống có hàng nghìn service và nhiều JDK: certificate chain phục vụ, truststore, compatibility, CRL/OCSP, version, thời điểm cutover và quy trình rollback.

## Tài liệu tham khảo

- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): định nghĩa BasicConstraints, KeyUsage, CA/pathLen, path validation, self-issued/self-signed.
- [Java SE 17 — X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html): `getBasicConstraints`, `verify`, SAN, KeyUsage, EKU, validity.
- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html): parse certificate và tạo `CertPath`.
- [Java SE 17 — CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): kiểm tra một đường dẫn với thuật toán PKIX.
- [Java SE 17 — CertPathBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathBuilder.html): dựng đường dẫn chứng chỉ.
- [Java SE 17 — PKIXParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/PKIXParameters.html): trust anchors, revocation và tham số path validation.
- [Java SE 17 — TrustAnchor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/TrustAnchor.html): biểu diễn điểm tin cậy do ứng dụng cấu hình.
- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): lưu trữ certificate/trust material và key entries.
- [Java SE 17 — SSLParameters](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/net/ssl/SSLParameters.html): cấu hình endpoint identification.
- [JDK `keytool` reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html): `-genkeypair`, `-certreq`, `-gencert`, `-importcert` và `-exportcert`.
