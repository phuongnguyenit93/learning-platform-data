# 8.6 Phân biệt DER, PEM, khóa thô, khóa mã hóa và chứng thư

Trong Java Security/JCA, một file mang tên `server.pem`, `public.der`, `private.key` hoặc `certificate.crt` không tự cho biết nó chứa loại khóa nào, có mật khẩu bảo vệ hay không, và có được tin cậy hay không. **DER, PEM, raw key, encrypted key và certificate mô tả những chiều khác nhau của dữ liệu mật mã**. Nhầm các chiều này thường dẫn tới `InvalidKeySpecException`, lỗi TLS, lộ private key hoặc xác thực nhầm đối tác.

Một public key RSA có thể nằm trong cấu trúc ASN.1 **SubjectPublicKeyInfo (SPKI)** được mã hóa **DER**, rồi bọc text **PEM** với nhãn `-----BEGIN PUBLIC KEY-----`. Một chứng thư X.509 cũng thường được mã hóa DER và bọc PEM nhưng có nhãn `-----BEGIN CERTIFICATE-----`: bên trong có public key *cùng* các trường subject, issuer, validity, extension và chữ ký số. Một private key có thể là PKCS#8 không mã hóa (`BEGIN PRIVATE KEY`), PKCS#8 đã mã hóa (`BEGIN ENCRYPTED PRIVATE KEY`), hoặc dạng riêng của RSA/EC.

Bài này giải thích từ lớp byte tới lớp tin cậy, đề xuất cách chọn parser và thuật toán, có ví dụ Java 17+ biên dịch/chạy được, cùng checklist chống nhầm lẫn và thực hành bảo vệ khóa.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **vật liệu khóa**, **cấu trúc dữ liệu**, **binary encoding**, **text armor**, **mã hóa khi lưu** và **chứng thư/tin cậy**.
2. Nhận ra cấu trúc SPKI, PKCS#8, PKCS#1, SEC 1 và X.509 certificate từ **quy ước được công bố**, không chỉ từ đuôi file.
3. Dùng đúng các API Java: `PKCS8EncodedKeySpec`, `X509EncodedKeySpec`, `KeyFactory`, `EncryptedPrivateKeyInfo`, `CertificateFactory`, `X509Certificate` và `KeyStore`.
4. Biết vì sao **PEM không phải encryption**, **X509EncodedKeySpec không nhận certificate**, và **public key không chứng minh danh tính**.
5. Phân biệt **encryption key** (khóa dùng mã hóa) với **encrypted key** (khóa đã được mã hóa để bảo vệ) và **wrapped key**.
6. Thiết kế luồng nhập/xuất key và chứng thư có kiểm soát thuật toán, permission, trust anchor, hostname, rotation và lỗi parser.
7. Kiểm thử DER ↔ PEM và chứng minh cặp khóa khôi phục có thể ký/xác minh, đồng thời không nhầm đó với việc xác minh chứng thư.

## 2. Đừng so sánh những thứ thuộc các lớp khác nhau

Hãy đặt năm câu hỏi trước khi “chuyển đổi định dạng”:

| Câu hỏi | Ví dụ câu trả lời | Điều không suy ra |
| --- | --- | --- |
| **Đây là đối tượng gì?** | Public key, private key, symmetric key, CSR, certificate | File `.pem` không nói rõ đối tượng |
| **Cấu trúc của nó là gì?** | SPKI, PKCS#8 PrivateKeyInfo, EncryptedPrivateKeyInfo, X.509 Certificate | ASN.1 SEQUENCE không đủ để biết loại |
| **Byte được serialize thế nào?** | DER theo ASN.1; raw bytes theo một chuẩn thuật toán | DER không mặc định là certificate |
| **Có được bọc thành text/container?** | PEM/Base64, PKCS#12, JWK, OpenSSH | PEM không tự mã hóa bảo mật |
| **Ai có quyền và ai đáng tin?** | Key được giữ trong HSM; certificate có chain tới CA được phép | Parse đúng không đồng nghĩa trust |

Sơ đồ quan hệ:

```text
Vật liệu khóa hoặc thông tin chứng thư
  |
  +-- Raw bytes theo đặc tả thuật toán (nếu dùng raw representation)
  |
  +-- ASN.1 schema
        +-- SubjectPublicKeyInfo             [public key]
        +-- PrivateKeyInfo / OneAsymmetricKey [private key]
        +-- EncryptedPrivateKeyInfo           [private key đã được mã hóa]
        +-- Certificate                      [X.509 certificate]
        +-- RSAPublicKey / RSAPrivateKey     [RSA PKCS#1]
        +-- ECPrivateKey                     [SEC 1]
        |
        v
     DER binary bytes
        |
        +-- file nhị phân theo contract
        |
        +-- Base64 + PEM BEGIN/END label -> file PEM văn bản
```

Cùng một **certificate** có thể có hai file khác nhau, một file là DER bytes và file còn lại là PEM của chính những DER bytes đó. Chỉ đổi lớp armor **không** làm thay đổi tính hợp lệ hoặc độ tin cậy của certificate.

## 3. DER là gì?

**DER** (*Distinguished Encoding Rules*) là quy tắc chuẩn tắc mã hóa một giá trị ASN.1 thành byte theo ITU-T X.690. Nhiều cấu trúc khóa và chứng thư trong hệ sinh thái PKIX/PKCS được đặc tả bằng ASN.1; sau đó DER thể hiện cấu trúc đó ở mức binary.

ASN.1 mô tả **kiểu dữ liệu/schema**, DER mô tả **cách encoding**. Ví dụ, SPKI bao gồm một `AlgorithmIdentifier` và trường chứa public key. Cấu trúc PKCS#8 cũng thường có algorithm identifier nhưng chứa private key trong vị trí được quy định khác. Certificate X.509 lại có cấu trúc certificate hoàn chỉnh gồm phần dữ liệu được ký, thông tin thuật toán và chữ ký.

DER có quy tắc định dạng tag/length/value (TLV), có các ràng buộc canonical chặt hơn BER (*Basic Encoding Rules*). Tag byte `0x30` có thể báo một ASN.1 SEQUENCE, nhưng **không phải dấu hiệu đủ để phân biệt SPKI, private key hay certificate** vì cả ba loại có thể bắt đầu bằng SEQUENCE.

Những điều DER **không** làm:

- Không mã hóa dữ liệu để giữ bí mật: DER của private key PKCS#8 không mã hóa vẫn tiết lộ private key.
- Không cho biết public key thuộc ai hay issuer có đáng tin không.
- Không thay certificate chain validation, algorithm policy và authorization.
- Không biến raw key byte thành PKCS#8/SPKI bằng cách thêm vài byte tùy ý.
- Không cung cấp metadata tự mô tả đầy đủ nếu bạn thiếu ASN.1 schema cần dùng.

Không dùng `new String(derBytes, StandardCharsets.UTF_8)` để “đọc” DER. Binary DER không phải văn bản UTF-8. Khi cần debug, dùng công cụ ASN.1 và hex, bảo đảm không làm lộ private key.

**BER/CER/DER:** có nhiều ASN.1 encoding rules. Một parser có thể chấp nhận BER rộng hơn tùy implementation, nhưng khi giao thức quy định DER thì **đầu ra và validation cần tuân DER**, nhất là với dữ liệu được ký. Chuyển đổi đúng là parse theo schema và serialize theo chuẩn đích, không chỉnh sửa byte đầu theo cảm tính.

## 4. PEM là gì?

**PEM** trong ngữ cảnh key/certificate thường là văn bản chứa **Base64 của một payload nhị phân**, kèm các dòng BEGIN/END cho biết loại payload. Ví dụ dưới đây chỉ là **sơ đồ**, không phải private/public key hợp lệ để copy trực tiếp:

```text
-----BEGIN PUBLIC KEY-----
Base64 của một cấu trúc SPKI DER hợp lệ
-----END PUBLIC KEY-----
```

Để tạo file thực tế, phải lấy đúng SPKI DER bytes, encode Base64 đúng quy tắc và dùng label tương ứng. Ví dụ Java chạy được ở mục 11 thực hiện việc đó từ key đã sinh.

PEM thường sử dụng armor theo RFC 7468 và convention của từng hệ sinh thái. Một số định dạng có cấu trúc bọc khác như OpenSSH; **đừng mặc định mọi file có BEGIN/END đều là PKCS#8 hoặc SPKI**.

Đặc tính cần nhớ:

- PEM dễ dùng trong text config/email nhưng Base64 **không phải mã hóa bảo mật**; đọc được PEM không mã hóa là decode được private key.
- Nhãn có ý nghĩa: `BEGIN PRIVATE KEY` ≠ `BEGIN ENCRYPTED PRIVATE KEY` ≠ `BEGIN CERTIFICATE`.
- Một PEM file có thể chứa **nhiều block**, chẳng hạn certificate chain. Parser phải xử lý đúng số lượng, thứ tự và loại block mà protocol yêu cầu.
- Đuôi `.pem`, `.crt`, `.cer`, `.key` không đáng tin bằng **cấu trúc thực tế và hợp đồng định dạng**.
- LF, CRLF, khoảng trắng và PEM headers legacy có thể khác nhau; code học tập dạng split dòng đơn giản thường không đủ cho mọi loại input bên ngoài.
- Không đổi nhãn BEGIN/END để biến payload từ private key thành public key hay certificate. Nhãn sai không tự thay cấu trúc bên trong.

### So sánh DER và PEM

| Tiêu chí | DER | PEM |
| --- | --- | --- |
| Cách biểu diễn | Binary bytes theo quy tắc ASN.1 | Text armor chứa Base64 |
| Nội dung có thể là | SPKI, PKCS#8, X.509 certificate, v.v. | Những object đó sau khi bọc đúng label |
| Khả năng bảo mật mặc định | Không | Không |
| Dễ hiển thị trong terminal | Không | Có |
| Đọc bằng Java | Chọn parser đúng cấu trúc | Decode armor rồi chọn parser đúng cấu trúc |
| Chuyển đổi DER ↔ PEM | Giữ nguyên DER payload nếu bọc/giải bọc đúng | Không tự chuyển đổi loại key/certificate |

Nếu một certificate X.509 DER được bọc PEM, chính **DER payload** đại diện cho certificate; không nên hash cả dấu xuống dòng/armor rồi nhầm với certificate fingerprint theo DER.

## 5. Khóa thô (raw key): không có schema chung

**Raw key** là byte của vật liệu khóa theo biểu diễn của **một thuật toán cụ thể**, thay vì một cấu trúc có wrapper chung như SPKI/PKCS#8. Ý nghĩa của raw bytes thay đổi theo thuật toán, library và protocol:

| Trường hợp | Raw material thường được hiểu là gì? | Thông tin còn cần |
| --- | --- | --- |
| AES-256 | 32 byte symmetric key | Algorithm, usage, key ID, nguồn entropy, quyền |
| Ed25519 public | 32 byte public key encoding theo RFC 8032 | Algorithm/format, policy, trust binding |
| Ed25519 private | Có protocol dùng seed 32 byte; có library dùng cách biểu diễn khác | Định nghĩa seed vs private encoding; không tự coi là PKCS#8 |
| X25519 | 32 byte coordinate/secret scalar theo RFC 7748 | Public/private, endianness, clamping/handling theo API |
| EC P-256 public | Điểm trên đường cong ở dạng compressed/uncompressed | Curve/domain parameters và kiểm point |
| RSA public | Hai số nguyên `n` và `e`, hoặc một cấu trúc thuật toán-cụ-thể `RSAPublicKey` | Modulus/exponent, padding/signature scheme, key policy |
| RSA private | Các thành phần RSA, đôi khi cấu trúc `RSAPrivateKey` PKCS#1 | Kiểm nhất quán tham số, CRT, độ dài, bảo vệ |

**Cùng 32 byte không có nghĩa hai key có thể dùng thay nhau.** Raw AES-256 key và raw Ed25519 public key có thể cùng kích thước nhưng là hai đối tượng với phép toán hoàn toàn khác nhau.

Raw key không bắt buộc kém an toàn, nhưng rất dễ bị hiểu nhầm nếu truyền không có algorithm/version/curve/usage. Chỉ dùng raw representation khi một protocol có đặc tả chính xác và implement parser theo chuẩn đó.

### Raw key khác EncodedKeySpec

`PKCS8EncodedKeySpec` đòi **cấu trúc private key PKCS#8**, không nhận trực tiếp mọi raw secret scalar/seed. `X509EncodedKeySpec` đòi **cấu trúc SPKI**, không nhận trực tiếp mọi raw public point. Nếu đưa 32 byte raw Ed25519 vào `new X509EncodedKeySpec(rawBytes)`, việc Java constructor tạo object spec không chứng minh bytes hợp lệ; `KeyFactory.generatePublic` thường từ chối vì thiếu đúng wrapper.

Với AES, việc dùng `new SecretKeySpec(rawAesBytes, "AES")` là một mô hình khác: nó mô tả **symmetric key** từ byte đã có. Điều này không chứng minh key có entropy đủ hoặc được cấp phát quyền. Đối với RSA/EC từ thành phần thô, Java có những spec phù hợp từng thuật toán như `RSAPublicKeySpec`, `RSAPrivateCrtKeySpec`, `ECPublicKeySpec`, `ECPrivateKeySpec`; phải có đủ thông số và validation.

## 6. SPKI, PKCS#8, PKCS#1 và SEC 1: đúng loại cấu trúc mới dùng đúng API

Bảng nhận dạng quan trọng:

| Cấu trúc | Đối tượng | PEM label phổ biến | Java 17 |
| --- | --- | --- | --- |
| **SubjectPublicKeyInfo (SPKI)** | Public key với AlgorithmIdentifier | `PUBLIC KEY` | `X509EncodedKeySpec` rồi `KeyFactory.generatePublic` |
| **PKCS#8 PrivateKeyInfo / OneAsymmetricKey** | Private key cùng thông tin thuật toán | `PRIVATE KEY` | `PKCS8EncodedKeySpec` rồi `KeyFactory.generatePrivate` |
| **PKCS#8 EncryptedPrivateKeyInfo** | Private key đã mã hóa cùng tham số mã hóa | `ENCRYPTED PRIVATE KEY` | Giải mã bằng provider thích hợp trước, rồi parse private key |
| **PKCS#1 RSAPublicKey** | RSA public modulus + exponent | `RSA PUBLIC KEY` | Không phải SPKI, cần parse/convert đúng |
| **PKCS#1 RSAPrivateKey** | RSA private key theo cấu trúc thuật toán | `RSA PRIVATE KEY` | Không phải PKCS#8, cần parse/convert đúng |
| **SEC 1 ECPrivateKey** | EC private key kiểu truyền thống | `EC PRIVATE KEY` | Không phải PKCS#8, cần parse/convert đúng |
| **X.509 Certificate** | Public key + chủ thể/issuer/validity/extension/signature | `CERTIFICATE` | `CertificateFactory.getInstance("X.509")` |

**Chú ý tên gây nhầm:**

- `X509EncodedKeySpec` không phải parser certificate. Nó đại diện cho **SPKI public key encoding**. Tên “X.509” phản ánh xuất xứ cú pháp public-key information, không có nghĩa tham số đầu vào là nguyên chứng thư X.509.
- `PKCS8EncodedKeySpec` dùng với **private key không mã hóa**. `BEGIN ENCRYPTED PRIVATE KEY` là một container khác, phải được giải mã theo đúng format/thuật toán/password trước.
- `RSA PRIVATE KEY` có thể là PKCS#1 legacy chưa mã hóa, hoặc mang lớp PEM encryption legacy tùy headers; không vì nhãn chứa “PRIVATE” mà mặc định decode bằng PKCS#8.
- `PUBLIC KEY` theo SPKI khác `RSA PUBLIC KEY` theo PKCS#1. Cả hai có thể mô tả cùng toán học RSA public key nhưng **byte và schema không giống nhau**.

### Liên hệ với Ed25519, X25519 và EC

RFC 8410 mô tả algorithm identifiers/encoding cho các key thuật toán Ed25519/Ed448/X25519/X448 trong SPKI/PKCS#8. Nếu protocol đưa **raw 32-byte Ed25519 public key**, cần conversion đúng tiêu chuẩn, không thêm “prefix cố định” tùy tiện. Dữ liệu PKCS#8 Ed25519 private cũng không đơn giản là 32-byte seed được Base64 bọc nhãn `PRIVATE KEY`.

Với EC, một encoded point thiếu domain parameters có thể dẫn tới nhầm curve. Phải xác định chuẩn representation, public-key validation và thuật toán, không giả định mọi EC point đều thuộc P-256.

## 7. “Khóa mã hóa” có hai nghĩa khác nhau

Cụm “khóa mã hóa” đôi khi có nghĩa **encryption key** (key dùng để mã hóa dữ liệu), nhưng trong thảo luận file format có thể có nghĩa **encrypted key** (bản thân key được mã hóa để bảo vệ khi lưu/truyền).

1. **Encryption key / decryption key**: key dùng trong thuật toán, ví dụ AES key hoặc RSA public/private key cho encryption/decryption theo scheme cho phép. Key có thể lưu dạng raw, DER, PEM hay trong HSM tùy loại.
2. **Encrypted private key**: blob chứa private key được mã hóa, chẳng hạn PKCS#8 `EncryptedPrivateKeyInfo`, mở được bằng mật khẩu hoặc cơ chế khóa tương ứng theo thuật toán và policy. Không thể dùng trực tiếp ciphertext của key như object `PrivateKey`.
3. **Wrapped key**: key được bao bọc bằng *key encryption/wrapping key (KEK)* hoặc KMS wrapping operation, ví dụ AES Key Wrap hoặc envelope encryption. Không mặc định là PKCS#8 hay dùng cùng PEM label.
4. **Certificate**: chứng thư chứa **public key**, không chứa private key; nó không “mã hóa private key” và không thay thế việc bảo vệ key thật.

Hãy luôn viết chính xác “key dùng để mã hóa”, “key đã được mã hóa” hay “key được bọc (wrapped)” trong tài liệu kỹ thuật để tránh đặt sai API/quyền truy cập.

## 8. PKCS#8 được mã hóa: không đồng nghĩa với PEM

Một private key PKCS#8 chưa mã hóa thường có dạng:

```text
PrivateKeyInfo
  -> version + AlgorithmIdentifier + privateKey data
  -> DER bytes
  -> optional PEM armor "PRIVATE KEY"
```

Khi bảo vệ private key tại rest bằng password/secret:

```text
PrivateKeyInfo DER
  -> encryption/KDF/protection algorithm + parameters
  -> EncryptedPrivateKeyInfo (algorithmIdentifier, encryptedData)
  -> DER bytes
  -> optional PEM armor "ENCRYPTED PRIVATE KEY"
```

**Bảo mật nằm ở thuật toán và cách quản lý password/key**, không nằm ở việc thêm PEM armor. Mật khẩu yếu có thể bị brute-force offline nếu blob rơi vào tay attacker. Mặt khác, encrypted key không tự cho biết người được phép sử dụng hay algorithm có an toàn đủ không.

### Những yếu tố cần hiểu khi mở encrypted key

- **KDF và tham số:** salt, iteration count, thuật toán PRF hoặc profile khác; lựa chọn phù hợp workload và khuyến nghị hiện hành.
- **Thuật toán bảo vệ:** lựa chọn mạnh, không dùng profile legacy yếu không cần thiết. Cần biết liệu format có cung cấp authenticated encryption hay chỉ encryption+padding.
- **Tương thích provider:** Java có `EncryptedPrivateKeyInfo`, `Cipher` và `SecretKeyFactory`, nhưng các cách encoding PBES2/algorithm names/parameters giữa OpenSSL và JDK/provider có thể khác; không giả định mọi file OpenSSL đều chạy với một lệnh JCA generic.
- **Nguồn password:** secure input, secret manager; tránh hard-code, CLI history, log. Với KMS/HSM có thể không bao giờ có bản sao raw private key trong ứng dụng.
- **Validation:** sau decrypt, phải kiểm private key structure, algorithm và policy. Không xem byte giải mã được là key an toàn bất kể format.
- **Legacy PEM encryption:** một số `BEGIN RSA PRIVATE KEY` có PEM headers `Proc-Type: 4,ENCRYPTED`, `DEK-Info`. Đó không đồng nghĩa `BEGIN ENCRYPTED PRIVATE KEY` dạng PKCS#8. Dùng parser/migration hiểu chính xác định dạng.

### Ví dụ thao tác OpenSSL (minh họa CLI, không phải Java)

Giả sử bạn có một private key hợp lệ trong file `private.pem` và OpenSSL thích hợp:

```bash
# Trích public key dạng SPKI PEM từ private key
openssl pkey -in private.pem -pubout -out public.pem

# Mã hóa private key thành encrypted PKCS#8; công cụ yêu cầu nhập password
openssl pkcs8 -topk8 -in private.pem -out private-encrypted.pem \
  -v2 aes-256-cbc -v2prf hmacWithSHA256 -iter 200000

# Đọc metadata certificate, không cần private key
openssl x509 -in certificate.pem -noout -subject -issuer -dates
```

Các lệnh yêu cầu file đầu vào phù hợp, quyền truy cập và policy của hệ thống. Con số vòng lặp chỉ minh họa, không phải khuyến nghị dùng mãi cho mọi tải và threat model. AES-CBC trong cấu hình PBE này không đồng nghĩa một envelope authenticated AEAD hoàn chỉnh. Không ghi password trong argv hoặc commit encrypted private key với password yếu chỉ vì nghĩ “đã mã hóa là an toàn”.

## 9. Certificate X.509: một public key với các khẳng định có chữ ký

X.509 certificate chứa public key dưới cấu trúc SPKI *và* nhiều trường khẳng định về chủ thể, issuer, hiệu lực, usage. Theo cấu trúc tổng quát, certificate bao gồm phần được ký `tbsCertificate`, thông tin signature algorithm và signature bits.

| Trường | Ý nghĩa |
| --- | --- |
| Serial number, version | Số serial do issuer quản lý và version cấu trúc |
| Subject, Issuer | Chủ thể được cấp và thực thể cấp/ký |
| NotBefore / NotAfter | Khoảng hiệu lực của certificate |
| SubjectPublicKeyInfo | Public key cùng algorithm identifier |
| Subject Alternative Name (SAN) | DNS/IP/định danh khác, đặc biệt quan trọng với TLS hostname |
| Key Usage / Extended Key Usage | Mục đích sử dụng chứng thư và key được cho phép |
| Basic Constraints | Có phải CA, giới hạn path length |
| Chữ ký của issuer | Cho phép xác minh dữ liệu certificate không bị sửa với public key issuer theo trust model |

**Certificate không mang private key** tương ứng. Private key được giữ ở server, HSM/KMS hoặc keystore bảo vệ; client nhận certificate/public key phục vụ quá trình xác thực theo protocol.

### Parse được không phải trust

Ba câu hỏi cần tách biệt:

1. **Parse hợp lệ:** `CertificateFactory` dựng object `X509Certificate` từ DER/PEM certificate.
2. **Chữ ký certificate có đúng với một issuer public key cụ thể?** `certificate.verify(issuerPublicKey)` có thể giúp kiểm chữ ký với key được chỉ định, nhưng tự nó không chứng minh issuer key đáng tin.
3. **Có thể tin chủ thể để thực hiện tác vụ này?** Cần **PKIX path validation tới trust anchor được phép**, hiệu lực, algorithm constraints, basic constraints, key usage/EKU, revocation theo policy và với HTTPS còn **hostname/SAN matching**.

Chứng thư self-signed có thể tự verify chữ ký của chính nó; điều đó **không** tự đưa nó vào truststore. Chứng thư hết hạn vẫn parse được. Certificate có tên trong Subject rất giống tên công ty không tự tạo bằng chứng danh tính.

Java dùng `CertificateFactory`, `CertPathValidator`, `PKIXParameters` và các thành phần JSSE/`TrustManager` phù hợp để xác minh trust. Với HTTPS bình thường, ưu tiên client/TLS stack đáng tin với hostname verification bật, không tự xây lại toàn bộ PKIX logic từ vài lời gọi `verify`.

### CSR khác certificate

`BEGIN CERTIFICATE REQUEST` là CSR/PKCS#10: yêu cầu CA cấp chứng thư, có public key và chữ ký chứng minh possession của private key. CSR **chưa phải certificate đã được CA cấp**. Certificate từ CA có issuer, time validity, signature/usage semantics riêng. Không dùng CSR thay certificate để xác thực TLS peer.

## 10. PKCS#12/PFX và các format khác

Nhiều hệ thống lưu private key + certificate chain trong **PKCS#12** (`.p12`/`.pfx`), một **container** có thể chứa nhiều entry, password protection và metadata. Nó không phải một file DER SPKI hoặc một PEM certificate đơn thuần. Trong Java, `KeyStore.getInstance("PKCS12")` cho phép đọc các entry khi có quyền/mật khẩu phù hợp.

Các format khác cần nhận diện riêng:

- **OpenSSH**: `BEGIN OPENSSH PRIVATE KEY` và public-key dòng `ssh-ed25519 AAAA...` thuộc định dạng SSH, không mặc định là PKCS#8/SPKI PEM.
- **JWK/JWKS**: key biểu diễn bằng JSON/JSON Web Key với `kty`, `crv`, `n`, `e` hoặc `x` tùy loại; giá trị Base64url không biến JSON thành DER.
- **PKCS#1 / SEC 1 legacy**: key RSA/EC truyền thống, có thể convert sang PKCS#8 bằng công cụ hiểu schema; chỉ đổi `BEGIN` là sai.
- **PEM certificate chain**: nhiều block `CERTIFICATE` trong cùng file, phải xác định leaf/intermediate/anchor và policy. Không tự xem root do peer gửi là trust anchor.

Với PKCS#12, private key vẫn cần được bảo vệ cả khi container được password-protected: secret có thể bị sao chép và tấn công offline; certificate chain trong container cũng không tự là chain đáng tin.

## 11. Ví dụ Java 17+ hoàn chỉnh: SPKI/PKCS#8 DER ↔ PEM

Chương trình sau sinh một cặp **RSA** dùng cho minh họa, xuất private key theo **PKCS#8 DER** và public key theo **SPKI DER**, tạo PEM, đọc lại bằng `KeyFactory` và kiểm chữ ký. Nó cố ý **không tạo certificate**: key ASN.1 SPKI không phải X.509 certificate.

Lưu file đúng tên **`KeyFormatsDemo.java`**:

```java
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import java.util.Arrays;
import java.util.Base64;

public class KeyFormatsDemo {
    static String toPem(String label, byte[] der) {
        String b64 = Base64.getMimeEncoder(64, new byte[] {'\n'})
                .encodeToString(der);
        return "-----BEGIN " + label + "-----\n"
                + b64 + "\n-----END " + label + "-----\n";
    }

    // A deliberately narrow parser for one PEM block produced by toPem.
    static byte[] fromPem(String pem, String expectedLabel) {
        String begin = "-----BEGIN " + expectedLabel + "-----";
        String end = "-----END " + expectedLabel + "-----";
        String[] lines = pem.replace("\r\n", "\n").split("\n");
        if (lines.length < 3 || !begin.equals(lines[0])
                || !end.equals(lines[lines.length - 1])) {
            throw new IllegalArgumentException("Wrong PEM label or boundaries");
        }
        StringBuilder base64 = new StringBuilder();
        for (int i = 1; i < lines.length - 1; i++) {
            if (!lines[i].matches("[A-Za-z0-9+/=]+")) {
                throw new IllegalArgumentException("Invalid Base64 line");
            }
            base64.append(lines[i]);
        }
        return Base64.getDecoder().decode(base64.toString());
    }

    public static void main(String[] args) throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair pair = generator.generateKeyPair();

        byte[] privateDer = pair.getPrivate().getEncoded();
        byte[] publicDer = pair.getPublic().getEncoded();
        String privatePem = toPem("PRIVATE KEY", privateDer);
        String publicPem = toPem("PUBLIC KEY", publicDer);

        KeyFactory factory = KeyFactory.getInstance("RSA");
        PrivateKey privateKey = factory.generatePrivate(
                new PKCS8EncodedKeySpec(fromPem(privatePem, "PRIVATE KEY")));
        PublicKey publicKey = factory.generatePublic(
                new X509EncodedKeySpec(fromPem(publicPem, "PUBLIC KEY")));

        Signature signature = Signature.getInstance("SHA256withRSA");
        byte[] message = "Format != trust".getBytes(StandardCharsets.UTF_8);
        signature.initSign(privateKey);
        signature.update(message);
        byte[] signed = signature.sign();

        signature.initVerify(publicKey);
        signature.update(message);
        boolean verified = signature.verify(signed);

        System.out.println("Private format: " + pair.getPrivate().getFormat());
        System.out.println("Public format: " + pair.getPublic().getFormat());
        System.out.println("Private label: " + privatePem.split("\n")[0]);
        System.out.println("Public label: " + publicPem.split("\n")[0]);
        System.out.println("Private DER SEQUENCE tag: " + (privateDer[0] == 0x30));
        System.out.println("Public DER SEQUENCE tag: " + (publicDer[0] == 0x30));
        System.out.println("Private DER round trip: "
                + Arrays.equals(privateDer, privateKey.getEncoded()));
        System.out.println("Public DER round trip: "
                + Arrays.equals(publicDer, publicKey.getEncoded()));
        System.out.println("Signature valid: " + verified);
        try {
            fromPem(publicPem, "CERTIFICATE");
            System.out.println("Certificate label accepted: true");
        } catch (IllegalArgumentException e) {
            System.out.println("Certificate label accepted: false");
        }
    }
}
```

Biên dịch/chạy với **JDK 17 trở lên**:

```bash
javac --release 17 KeyFormatsDemo.java
java KeyFormatsDemo
```

**Stdout đã kiểm chứng:**

```text
Private format: PKCS#8
Public format: X.509
Private label: -----BEGIN PRIVATE KEY-----
Public label: -----BEGIN PUBLIC KEY-----
Private DER SEQUENCE tag: true
Public DER SEQUENCE tag: true
Private DER round trip: true
Public DER round trip: true
Signature valid: true
Certificate label accepted: false
```

### Phân tích ví dụ

1. `getEncoded()` của khóa software exportable được provider tạo trong demo trả bytes theo `getFormat()` tương ứng. `PKCS#8` là private encoding, `X.509` trong `PublicKey.getFormat()` là **SPKI public-key encoding**, không phải certificate.
2. `toPem` Base64-encode DER rồi thêm label đúng. Không có password-based encryption trong bước này. File private PEM tạo được vẫn là **secret cần bảo vệ**.
3. `fromPem` được viết *cố ý giới hạn*: một block duy nhất, label đúng, Base64 line được kiểm. Đây **không phải parser PEM đầy đủ** cho file từ đối tác; production dùng thư viện/logic RFC 7468 phù hợp, giới hạn kích thước/headers và số block.
4. `KeyFactory.getInstance("RSA")` parse hai cấu trúc đúng bằng `PKCS8EncodedKeySpec` và `X509EncodedKeySpec`. Nếu thay private DER bằng encrypted PKCS#8 hoặc PKCS#1 raw, cách này **không áp dụng trực tiếp**.
5. `Signature` chỉ xác nhận cặp key vừa khôi phục ký/xác minh được trên đúng byte message. Nó **không** chứng minh bên thứ ba hoặc một certificate chain đáng tin.
6. Hai DER bytes trong demo bắt đầu bằng `0x30` vì cùng là ASN.1 SEQUENCE, nhưng là **hai schema khác nhau**. Không dùng tag đầu làm parser-type detector.
7. `PUBLIC KEY` PEM không qua được parser kỳ vọng nhãn `CERTIFICATE`; nhãn đúng chỉ là một bước, muốn dùng certificate vẫn cần parser chứng thư và trust policy.
8. Ví dụ dùng RSA-2048 để chạy phổ biến, không nhằm quy định mọi use case phải dùng RSA-2048; thuật toán/kích thước/trọn vòng đời phải tuân chính sách.

Với khóa HSM/KMS không xuất được, `getEncoded()` có thể trả `null`. Đừng coi đó là lỗi cần bypass security; thay vào đó dùng key handle/API ký hoặc giải mã được provider cho phép.

## 12. Java: parse certificate X.509 đúng API

Đoạn sau **minh họa bên trong method** có các import và exception handling thích hợp; giả sử file `certificate.pem` tồn tại và chứa một certificate X.509 hợp lệ về cú pháp:

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.PublicKey;
import java.security.cert.CertificateFactory;
import java.security.cert.X509Certificate;

try (InputStream input = Files.newInputStream(Path.of("certificate.pem"))) {
    CertificateFactory factory = CertificateFactory.getInstance("X.509");
    X509Certificate certificate =
            (X509Certificate) factory.generateCertificate(input);
    PublicKey key = certificate.getPublicKey();
    String subject = certificate.getSubjectX500Principal().getName();
    String issuer = certificate.getIssuerX500Principal().getName();

    // Parsing, extracting key/subject/issuer do NOT establish trust.
}
```

Việc `getPublicKey()` trả về một `PublicKey` không thay thế chain validation. Nếu đây là certificate của endpoint TLS, cần kiểm trust anchor, chain, SAN/hostname, thời hạn và policy usage qua JSSE hoặc cơ chế PKIX đúng chuẩn. `certificate.checkValidity()` chỉ kiểm khoảng hiệu lực; `certificate.verify(somePublicKey)` chỉ kiểm chữ ký với key đã cho, không tự chứng minh `somePublicKey` thuộc issuer đáng tin.

### Phân biệt certificate DER và PEM

Hai dạng có thể chứa **cùng một certificate**:

```text
cert.der    = DER bytes của X.509 Certificate
cert.pem    = BEGIN CERTIFICATE + Base64 của chính DER bytes + END CERTIFICATE
```

Đổi dạng PEM ↔ DER **không** cấp thêm niềm tin. Certificate fingerprint thông thường hash **DER certificate bytes**, không hash cả dấu xuống dòng và PEM armor. Nếu file certificate bị thay, chữ ký/đường tin cậy cần được kiểm lại theo trust policy.

## 13. Java: PKCS#12 keystore không phải một private-key PEM

Một service có thể nhận identity dưới dạng `identity.p12` gồm private key và certificate chain. API Java minh họa (không phải chương trình độc lập, cần biến `password` và `alias` lấy từ cấu hình tin cậy và xử lý exception):

```java
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.Key;
import java.security.KeyStore;
import java.security.cert.Certificate;

KeyStore store = KeyStore.getInstance("PKCS12");
try (InputStream in = Files.newInputStream(Path.of("identity.p12"))) {
    store.load(in, password);
}
Key privateKey = store.getKey(alias, password);
Certificate[] chain = store.getCertificateChain(alias);
```

Không suy ra mọi PKCS#12 đều có private key; entry có thể là certificate hoặc key tùy cấu hình. Một private key và certificate chain trong cùng container không có nghĩa chain **được tin cậy**; bên nhận vẫn phải thực hiện validation theo yêu cầu, không lấy root peer gửi tự động làm CA.

Mật khẩu container bảo vệ thông tin ở rest theo provider/profile, **không phải khóa mã hóa dữ liệu ứng dụng**. Với HSM/KMS non-exportable key, thường service tham chiếu key handle và giữ certificate chain riêng, không cần xuất private key để tạo `.p12`.

## 14. Quy trình nhận diện file và chọn parser

Đầu tiên xác định **hợp đồng nguồn dữ liệu** rồi kiểm thực tế:

```text
Input có dòng BEGIN/END?
  |
  +-- Có:
  |   |
  |   +-- PUBLIC KEY            -> SPKI DER -> KeyFactory / X509EncodedKeySpec
  |   +-- PRIVATE KEY           -> PKCS#8 DER -> KeyFactory / PKCS8EncodedKeySpec
  |   +-- ENCRYPTED PRIVATE KEY -> giải mã PKCS#8 outer trước
  |   +-- CERTIFICATE           -> X.509 CertificateFactory + trust validation
  |   +-- RSA/EC PRIVATE KEY    -> parser legacy riêng / conversion phù hợp
  |   +-- OPENSSH ...           -> parser định dạng SSH
  |
  +-- Không:
      |
      +-- Binary DER SPKI/PKCS#8/Certificate -> parser đúng schema
      +-- Raw key bytes                     -> algorithm-specific spec/format
      +-- PKCS#12                           -> KeyStore PKCS12
      +-- JWK/JWKS JSON                      -> JWK parser + policy
```

**Không đoán chỉ từ extension**. Một ASN.1 DER blob chứa certificate có thể dùng `.cer`, `.crt`, `.der`; một file `.pem` có thể chứa nhiều certificate block. Khi nhận input không tin cậy:

- Giới hạn kích thước trước khi Base64 decode hoặc ASN.1 parse; giới hạn số block, chiều sâu/cấu trúc và thời gian xử lý.
- Từ chối label không thuộc allowlist và algorithm OID/kích thước/curve không đáp ứng chính sách.
- Nếu yêu cầu một public key SPKI thì từ chối certificate hoặc PKCS#1 RSA public key trừ khi đặc tả cho phép và parser đúng loại.
- Nếu cần certificate, không chỉ parse mà còn validate chain/identity/usage.
- Nếu cần private key, kiểm quyền và cách lưu/mở khóa, tránh xuất dữ liệu nhạy cảm ra log/heap không cần thiết.
- Nếu có nhiều block, dùng format mô tả **đúng cách chọn** leaf/intermediate và private key, không lấy ngẫu nhiên block đầu.

## 15. Các lỗi Java phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân có khả năng | Cách xử lý |
| --- | --- | --- |
| `InvalidKeySpecException` khi đọc `RSA PRIVATE KEY` bằng `PKCS8EncodedKeySpec` | PKCS#1 RSA private khác PKCS#8 | Dùng parser/convert schema chuẩn |
| `InvalidKeySpecException` với raw Ed25519 public 32 byte đưa vào `X509EncodedKeySpec` | Raw key không có SPKI wrapper | Dùng raw-key API phù hợp hoặc convert đúng RFC 8410 |
| CertificateFactory không nhận `PUBLIC KEY` | SPKI public key không phải X.509 certificate | `KeyFactory` cho SPKI; `CertificateFactory` cho certificate |
| Mở `ENCRYPTED PRIVATE KEY` như `PRIVATE KEY` | Chưa giải mã EncryptedPrivateKeyInfo | Dùng password/algorithm/provider phù hợp |
| OpenSSL encrypted key không mở được ở Java provider hiện tại | PBES2/algorithm identifiers/parameters khác hoặc unsupported | Kiểm compatibility/migrate bằng tooling an toàn |
| `getEncoded() == null` | Key không export được do HSM/provider | Dùng key handle để thực hiện crypto operation |
| Certificate parse thành công nhưng HTTPS fail | Chain/SAN/hostname/expiry/EKU/trust policy không hợp lệ | Kiểm PKIX/endpoint identification đúng cách |
| Signature verify sai sau khi convert key | Không đúng key pair, algorithm, message bytes hoặc scheme | Kiểm khóa và signed bytes trước khi quy lỗi cho PEM |
| Chỉ đổi PEM label mà parser báo lỗi | Payload ASN.1 bên trong không khớp label | Parse/serialize thực sự sang cấu trúc đích |
| PKCS#12 mở được nhưng không có private key alias kỳ vọng | Container/alias/entry khác yêu cầu | Liệt kê/kiểm entry theo policy và quyền |

Không giải quyết lỗi trust bằng cách tắt TLS verification, tắt hostname verification, tự thêm certificate bất kỳ vào truststore, hoặc fallback sang thuật toán yếu. Không giải quyết lỗi key format bằng cách in private key raw vào log để thử.

## 16. Vận hành: key lifecycle và certificate lifecycle

**Private key:**

1. Sinh bằng CSPRNG/provider tin cậy hoặc HSM/KMS theo chính sách thuật toán/độ dài.
2. Giữ bí mật và hạn chế export; nếu cần lưu file, ACL/private-key encryption/password đủ mạnh, backup và auditing.
3. Không lưu plaintext private key trong source control, issue tracker, chat, config không được bảo vệ.
4. Dùng key ID/version để quản lý rotation; không lẫn secret key material với public metadata.
5. Khi convert/backup, bảo vệ file tạm và xóa theo quy trình; việc chuyển sang PEM không tự mã hóa.
6. Với encryption key và signing key, tách mục đích; không dùng một key cho mọi giao thức không được thiết kế.
7. Nếu nghi lộ private key, thực hiện quy trình revoke/rotate và phát hành lại certificate cần thiết.

**Certificate và public key:**

1. Xác minh nguồn gốc bằng chain/trust anchor hoặc pinning có lifecycle phù hợp; không tin chỉ vì parse được.
2. Kiểm SAN/hostname và intended key usage theo ứng dụng; kiểm validity và revocation theo policy.
3. Kiểm cặp public/private key tương ứng khi triển khai server identity; certificate không chứa private key.
4. Tự động theo dõi expiry/renewal theo hệ thống vận hành, bảo đảm không phát key ra ngoài.
5. Khi chuyển DER ↔ PEM, giữ đúng bytes và kiểm lại format; không coi conversion là trust validation.
6. Với CSR, kiểm yêu cầu và quyền cấp certificate; CSR không phải certificate đã cấp.

**Key wrapping/container:**

1. Biết rõ key encryption key (KEK) và data encryption key (DEK) thuộc vùng nào, bảo vệ bằng KMS/HSM khi phù hợp.
2. Không xem encrypted blob là private key đã mở; phải qua decrypt/unwrap với quyền tương ứng.
3. Version KDF/algorithm và kiểm interoperability trước khi rotation/migration.
4. Chống downgrade profile hoặc dùng key không còn được phép do request chỉ định.
5. Không cài password trong lệnh hoặc log; không nhầm password container với algorithm key.

## 17. Bộ test kỹ thuật nên chạy

| Test | Đầu vào | Kỳ vọng |
| --- | --- | --- |
| PKCS#8 round trip | RSA private key exportable → DER → PEM → DER | Byte DER và key sau parse khớp |
| SPKI round trip | RSA public key → DER → PEM → DER | Byte DER và key sau parse khớp |
| Ký/xác minh | Private PKCS#8 và public SPKI vừa parse | Chữ ký xác minh đúng message |
| Nhãn PEM sai | SPKI `PUBLIC KEY` đưa vào parser chờ `CERTIFICATE` | Bị từ chối |
| PKCS#1/PKCS#8 nhầm | `RSA PRIVATE KEY` đưa vào PKCS#8 parser | Bị từ chối/không parse sai schema |
| Raw Ed25519 vs SPKI | Raw bytes theo RFC 8032 | Không tự parse như SPKI nếu thiếu wrapper |
| Encrypted PKCS#8 | Password đúng/sai, KDF/algorithm theo policy | Chỉ mở khóa với quyền/password đúng; lỗi được xử lý an toàn |
| Certificate parse | X.509 DER và PEM của cùng certificate | Parse được; public key/SPKI giống nhau |
| Certificate trust | Self-signed không nằm trong truststore | Có thể parse nhưng không tự được tin |
| Hostname | Certificate cho DNS A dùng truy cập DNS B | Endpoint identification từ chối |
| Expired certificate | Certificate ngoài validity | Bị từ chối theo policy dù ASN.1 parse được |
| Kích thước input | PEM/ASN.1 quá lớn hoặc quá nhiều block | Từ chối sớm theo quota |
| Container PKCS#12 | Entry/cert chain/password phù hợp | Lấy đúng entry, không tự tin chain |
| Non-exportable key | Hardware/provider key có `getEncoded() == null` | Dùng handle, không cố export |
| Định dạng nhiều ngôn ngữ | Java và OpenSSL cùng SPKI/PKCS#8 | Có thể parse và ký/verify chéo đúng chuẩn |

**Test phân biệt trust:** cho ứng dụng parse một certificate tự ký và thử tự verify bằng public key từ chính certificate. Việc toán học thành công không được tự biến đối tượng thành peer đáng tin. Hãy test đầy đủ trust anchor/chain, SAN và authorization.

## 18. Bài tập thực hành

### Bài 1 — Đọc nhãn và chọn API

Bạn nhận năm nguồn dữ liệu: `BEGIN PUBLIC KEY`, `BEGIN PRIVATE KEY`, `BEGIN ENCRYPTED PRIVATE KEY`, `BEGIN CERTIFICATE` và `BEGIN RSA PRIVATE KEY`. Với mỗi nguồn, hãy xác định payload/schema, có chắc chứa private key không, có password không, Java parser/KeySpec phù hợp và rủi ro nếu nhận từ client chưa tin cậy.

### Bài 2 — Chạy KeyFormatsDemo

Biên dịch bằng `javac --release 17`. Giải thích vì sao public format hiển thị `X.509` nhưng chương trình không hề tạo certificate. Thử thay nhãn PEM của public key thành `CERTIFICATE` mà không thay DER, rồi mô tả tại sao đó không phải conversion đúng.

### Bài 3 — Migrate khóa RSA kiểu cũ

Một đối tác gửi private key `BEGIN RSA PRIVATE KEY` không mã hóa. Thiết kế quy trình chuyển sang encrypted PKCS#8: chọn parser chuẩn, giới hạn input, kiểm public key tương ứng, mã hóa với password/algorithm theo policy, bảo vệ file tạm, kiểm compatibility và theo dõi rotation. Chỉ rõ nơi không được log secret.

### Bài 4 — Raw Ed25519

Một giao thức trả 32 byte Ed25519 public key. Bạn cần dùng Java JCA để verify. Ghi rõ chuẩn byte input, cách tạo public-key object hoặc SPKI theo spec phù hợp, algorithm allowlist và cách xác lập **key đó thuộc bên nào** (trust binding) trước khi verify message.

### Bài 5 — Certificate bị giả mạo tên

Một endpoint gửi certificate tự ký có Subject ghi tên doanh nghiệp và public key hoạt động bình thường. Vì sao `getPublicKey()` và `verify(ownPublicKey)` vẫn chưa đủ để tin API? Mô tả trust anchor, chain, hostname/SAN, validity, KU/EKU, revocation policy và quyền thực hiện tác vụ.

### Bài 6 — Vận hành server key + certificate

So sánh ba lựa chọn: (a) `PRIVATE KEY` PEM + certificate PEM, (b) password-protected PKCS#12, (c) HSM/KMS non-exportable key + certificate chain. Phân tích cách triển khai, backup, rotation, quyền và nguy cơ lộ secret. Khi certificate hết hạn, vì sao không nhất thiết phải thay đổi thuật toán/format private key mà vẫn phải tuân chính sách rotation?

**Điều kiện hoàn thành:** bạn nhận biết chính xác **kiểu dữ liệu, schema, encoding, lớp bảo vệ và trust policy**; phân biệt được “convert PEM/DER” với “convert PKCS#1/PKCS#8”, “decrypt private key” với “dùng key để mã hóa”, và “đọc certificate” với “tin cậy certificate”.

## 19. Tài liệu tham khảo

- [RFC 7468 — Textual Encodings of PKIX, PKCS, and CMS Structures](https://www.rfc-editor.org/rfc/rfc7468): PEM textual encoding và labels.
- [ITU-T X.690 — ASN.1 Encoding Rules](https://www.itu.int/rec/T-REC-X.690/): BER, CER và DER.
- [RFC 5280 — Internet X.509 PKI Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): X.509 certificate và PKIX.
- [RFC 5958 — Asymmetric Key Packages](https://www.rfc-editor.org/rfc/rfc5958): OneAsymmetricKey, EncryptedPrivateKeyInfo.
- [RFC 5208 — PKCS#8 Private-Key Information Syntax](https://www.rfc-editor.org/rfc/rfc5208): PrivateKeyInfo/EncryptedPrivateKeyInfo truyền thống.
- [RFC 8017 — PKCS#1: RSA Cryptography Specifications](https://www.rfc-editor.org/rfc/rfc8017): cấu trúc và thuật toán RSA.
- [RFC 8410 — Algorithm Identifiers for Ed25519, Ed448, X25519, X448](https://www.rfc-editor.org/rfc/rfc8410): SPKI/PKCS#8 cho thuật toán hiện đại.
- [RFC 7292 — PKCS#12](https://www.rfc-editor.org/rfc/rfc7292): container key/certificate.
- [Java SE 17 — PKCS8EncodedKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/PKCS8EncodedKeySpec.html) và [X509EncodedKeySpec](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/spec/X509EncodedKeySpec.html): các key spec cần phân biệt.
- [Java SE 17 — EncryptedPrivateKeyInfo](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/javax/crypto/EncryptedPrivateKeyInfo.html): private key được mã hóa.
- [Java SE 17 — CertificateFactory](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertificateFactory.html), [X509Certificate](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/X509Certificate.html), [CertPathValidator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/cert/CertPathValidator.html): parse và validate certificate.
- [Java SE 17 — KeyStore](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/security/KeyStore.html): PKCS#12 và keystore providers.
