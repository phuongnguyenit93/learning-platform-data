# 13.8 CSR PKCS#10, phản hồi CA và chuỗi chứng thư trong quy trình keytool

Một ứng dụng Java muốn dùng chứng thư X.509 thật cho TLS, mTLS hoặc ký số thường không thể dừng ở bước `keytool -genkeypair`. Lệnh đó có thể tạo **private key + chứng thư tự ký ban đầu** trong KeyStore, nhưng chứng thư được một tổ chức khác tin cậy phải đi qua **yêu cầu cấp chứng thư CSR (PKCS#10)**, quá trình **CA thẩm định và ký**, nhận **certificate reply**, rồi cài lại đúng **certificate chain** vào alias chứa private key ban đầu.

Bài này trình bày luồng hoàn chỉnh từ **khóa trong PKCS#12 → CSR PKCS#10 → CA ký → trust anchor → nhập phản hồi vào cùng alias → kiểm chain bằng Java 17+**, đồng thời giải thích chain có intermediate CA, SAN, key usage, truststore, xử lý lỗi và quản trị production. Ví dụ sử dụng **CA tự tạo chỉ trong phòng thực hành**, không giả làm chứng thư công khai được mọi trình duyệt tin cậy.

## 1. Kết quả cần đạt

Sau khi học, bạn có thể:

1. Giải thích **CSR PKCS#10** gồm những gì, không gồm những gì, và vì sao CSR có chữ ký nhưng **chưa phải certificate đã được CA ký**.
2. Phân biệt private key, public key, CSR, **CA-issued leaf certificate**, intermediate certificates, root trust anchor và chuỗi chứng thư.
3. Dùng `keytool` để tạo một PKCS#12 identity, xuất CSR, xem nội dung CSR, tạo certificate reply từ CA demo, import root và install reply vào **đúng alias**.
4. Hiểu vì sao alias chứa `PrivateKeyEntry` phải được giữ nguyên khi thay self-signed certificate bằng certificate đã được cấp.
5. Dùng Java 17+ đọc lại `KeyStore`, xác minh alias/chain, SAN, quan hệ issuer, public/private key và validate path bằng **PKIX**.
6. Nhận ra giới hạn của ví dụ: CA demo, password dòng lệnh, PKIX revocation bị tắt **chỉ để demo**, và một bài kiểm SAN không thay TLS hostname verifier.
7. Khắc phục các lỗi phổ biến `Failed to establish chain from reply`, `Public keys in reply and keystore don't match`, nhập reply nhầm alias, thiếu intermediate hoặc tin sai CA.

## 2. Các đối tượng trong một quy trình cấp chứng thư

| Đối tượng | Nội dung cốt lõi | Độ nhạy / nơi thường nằm |
| --- | --- | --- |
| **Private key** | Khóa riêng RSA/EC/... để tạo chữ ký hoặc thực hiện thao tác private key theo thuật toán | **Bí mật**, nằm trong KeyStore/HSM/KMS; không gửi cho CA |
| **Public key** | Khóa công khai tương ứng với private key | Nằm trong CSR và leaf certificate |
| **CSR PKCS#10** | Subject, SubjectPublicKeyInfo, các attributes/extension requests và **chữ ký của bên yêu cầu** | Thường có thể gửi CA; không mang private key |
| **CA-issued certificate** | Chứng thư X.509 chứa thông tin subject, public key, issuer, serial, validity, extensions và **chữ ký của CA** | Công khai; chỉ đáng tin sau khi kiểm đường dẫn và chính sách |
| **Intermediate certificate** | Chứng thư của CA trung gian do CA cấp trên ký, thường có quyền CA theo constraints | Công khai; cần cho việc dựng đường dẫn |
| **Root CA / trust anchor** | Chứng thư hoặc public-key trust anchor được cấu hình tin cậy ngoài băng | Public, nhưng việc **chọn tin** phải được bảo vệ bằng chính sách |
| **Certificate reply** | Chứng thư leaf do CA cấp, có thể kèm các intermediate/chain dưới nhiều định dạng | Công khai; dùng để **thay chain ở alias private key** |
| **Identity keystore** | Kho lưu private key cùng chain phục vụ chứng minh danh tính | Bảo vệ cẩn thận |
| **Truststore** | Kho trust anchors hoặc CA/peer cert đã được chấp nhận theo chính sách | Chỉ chứa cert công khai trong mô hình thông dụng; kiểm nguồn import |

**Ba thông điệp phải nhớ:** (1) CSR không chứa private key; (2) CA có thể ký chứng thư chỉ khi quyết định **cho phép subject/định danh** theo chính sách của mình; (3) nhận được file certificate **không tự khiến nó được trust**.

### 2.1. Sơ đồ tổng thể

~~~text
                         MÁY CHỦ / NGƯỜI XIN CẤP
   +-----------------------------------------------------------+
   | KeyStore "app.p12"                                         |
   | alias "app-server": PrivateKeyEntry                         |
   |     private key  [GIỮ BÍ MẬT]                              |
   |     self-signed cert tạm thời                              |
   +-----------------------------------------------------------+
               | keytool -certreq  (dùng private key ký CSR)
               v
          CSR PKCS#10 ----- gửi CSR, không gửi private key -----> CA
                                                               |
                                          kiểm tên/domain/chính sách
                                          thẩm định CSR + ký leaf X.509
                                                               |
               <---------- phản hồi leaf + chain (khi có) ------+
               |
               | nhập CA certificate từ nguồn ĐÃ XÁC THỰC
               | nhập signed leaf vào cùng alias "app-server"
               v
   +-----------------------------------------------------------+
   | KeyStore "app.p12"                                         |
   | alias "app-server": PrivateKeyEntry                         |
   |     cùng private key                                       |
   |     chain[0] = CA-issued leaf                              |
   |     chain[1] = CA trung gian hoặc root (tùy đường dẫn)      |
   |     ...                                                     |
   | alias "demo-ca": TrustedCertificateEntry (CA demo)         |
   +-----------------------------------------------------------+
               |
               v
        Java load + kiểm PKIX/chain; JSSE khi dùng TLS
~~~

Sơ đồ là trường hợp mô phỏng. Ở production, CA, identity store và truststore thường có các vai trò/quyền truy cập khác nhau; private key có thể **không xuất được** khỏi HSM. Root trust anchor thường được cấu hình ở phía **bên kiểm chứng (relying party)** chứ không phải chỉ cần nhập vào keystore của server rồi mọi client sẽ tin.

## 3. CSR PKCS#10 chính xác là gì?

**PKCS#10** (RFC 2986) quy định cấu trúc **CertificationRequest**. Nói đơn giản, CSR chứa:

~~~text
CertificationRequest
  certificationRequestInfo
    version
    subject (X.500 Distinguished Name)
    subjectPublicKeyInfo (public key + algorithm)
    attributes (có thể chứa extensionRequest)
  signatureAlgorithm
  signature (chữ ký bằng private key tương ứng public key trên CSR)
~~~

Chữ ký ở CSR là **bằng chứng bên xin cấp đang sở hữu private key tương ứng** khi tạo yêu cầu (proof of possession trong phạm vi kỹ thuật chữ ký); nó **không xác nhận** người đó có quyền sở hữu hostname/domain, tổ chức hoặc tài sản được khai báo. Thẩm định danh tính/domain/IP và áp chính sách issuance thuộc trách nhiệm **CA**.

Một số sự thật quan trọng:

- CSR **không chứa private key**. Không gửi `.p12`, file key, password hoặc token/HSM secret cho CA chỉ vì CA yêu cầu CSR.
- CSR **không phải certificate X.509 đã có issuer tin cậy**. Chữ ký bên xin cấp trong CSR khác chữ ký CA trên chứng thư được phát hành.
- Các trường `Subject DN` và attributes như `extensionRequest` có thể gồm **requested SAN, KeyUsage, ExtendedKeyUsage**; CA có thể chấp nhận, sửa, từ chối hoặc bỏ qua theo chính sách.
- Với HTTPS hiện đại, **DNS name/IP phải có trong Subject Alternative Name (SAN)** của leaf theo quy tắc client/chuẩn liên quan. Chỉ đặt `CN` đẹp mà không có SAN phù hợp không đủ.
- CSR thường là **DER (nhị phân ASN.1)** hoặc **PEM** có nhãn `-----BEGIN CERTIFICATE REQUEST-----` (text Base64 bọc DER). PEM chỉ là **cách biểu diễn**, không phải một loại yêu cầu mật mã khác.
- Một CSR ứng với một public key nhất định. Nếu muốn CA response gắn với **private key ở alias cũ**, public key trong reply phải khớp public key của khóa đó.

### 3.1. CSR khác certificate như thế nào?

| Điểm so sánh | CSR PKCS#10 | Chứng thư X.509 đã cấp |
| --- | --- | --- |
| Người ký | Người sở hữu **private key yêu cầu** | **CA issuer** |
| Mục đích | Yêu cầu CA cấp certificate cho public key + subject | Ràng buộc public key với identity theo chính sách CA |
| Có serial và validity do CA cấp | Chưa | Có |
| Có issuer của CA | Không theo nghĩa certificate đã phát hành | Có issuer DN và chữ ký CA |
| SAN/usage | Có thể là **yêu cầu extension** | Extension thực tế mà CA **quyết định phát hành** |
| Dùng ngay làm TLS server certificate | **Không** | Có thể, sau khi đủ chain, policy, key, thời hạn, hostname và trust validation |
| Có private key | **Không** | **Không**; private key giữ ngoài cả hai artifact |

Đừng suy luận rằng file có chữ `CERTIFICATE` trong tên đồng nghĩa chứa private key. Thông thường `.crt`/`.cer` mang certificate công khai; `.csr` mang yêu cầu; `.p12` có thể chứa private key, certificate chain và các entry khác tùy cách đóng gói. **Không kiểm nguồn chỉ bằng phần mở rộng file.**

## 4. Chain of trust: leaf, intermediate CA, root

Trong PKI phân cấp điển hình:

~~~text
Root CA (trust anchor do bên xác minh cấu hình)
    |
    | ký
    v
Intermediate CA (basicConstraints CA=true, keyCertSign)
    |
    | ký
    v
Leaf certificate (app.example.test, SAN DNS, EKU serverAuth)
    |
    | public key của leaf phải khớp private key trong app.p12
    v
TLS server/ứng dụng dùng private key để chứng minh sở hữu
~~~

Một certificate path hợp lệ thường cần:

1. Chữ ký leaf được xác minh bằng public key của intermediate CA (hoặc root nếu không có intermediate).
2. Chữ ký intermediate (và các CA tiếp theo) dẫn về một **trust anchor đã được chọn từ trước**.
3. Kiểm hạn hiệu lực, thuật toán/cỡ khóa theo chính sách, `basicConstraints`, `keyUsage`, `pathLenConstraint` và những constraint liên quan.
4. Kiểm **mục đích sử dụng**: ví dụ TLS server cần `ExtendedKeyUsage serverAuth` khi EKU được khai báo; leaf có SAN khớp hostname mà client thực sự kết nối.
5. Kiểm trạng thái thu hồi/chính sách (CRL/OCSP hoặc cơ chế của hệ thống) khi được yêu cầu; không mặc định rằng mọi CA hoặc ứng dụng đều xử lý như nhau.

**Trust anchor không được “tự chứng minh là trusted” nhờ self-signature.** Root có thể tự ký, nhưng thứ làm nó đáng tin là việc public key/certificate được đặt vào tập trust anchors bằng **quy trình phân phối đáng tin và chính sách**. Kẻ tấn công cũng có thể tự ký certificate của họ.

### 4.1. Thứ tự trong certificate chain

Trong `KeyStore.PrivateKeyEntry`, chain thường được xem như:

~~~text
chain[0] = End-entity / leaf certificate của private key
chain[1] = Issuing intermediate CA (nếu có), hoặc root (nếu root ký trực tiếp)
chain[2] = CA cấp trên, nếu có ...
~~~

**Không đặt root ở `chain[0]`** và không nhầm alias trust anchor với alias private key. Đối với TLS, server thường gửi **leaf và intermediate(s)**; root thường **không cần gửi** vì client đã có root trong truststore, tùy giao thức/triển khai. Nếu server chỉ gửi leaf mà không có intermediate và client không thể tự lấy intermediate, việc dựng đường dẫn có thể thất bại.

**Ví dụ của bài:** Root demo ký leaf trực tiếp → chain có 2 phần tử ở KeyStore: **leaf → root**. Production thường có thêm intermediate, số lượng có thể là 3 hoặc nhiều hơn.

### 4.2. Chain được tin từ đâu?

`keytool -importcert` có thể **xây certificate chain dựa trên các CA certificates đã biết** hoặc dựa trên chain được gửi trong reply. Tuy nhiên, việc import thành công và certificate reply có chữ ký CA chưa nói rằng certificate này sẽ được **mọi client công cộng tin**. Bên dựa vào chứng thư phải tự có trust anchor phù hợp trong truststore/chính sách của họ.

Không nhập “CA root” từ email hoặc cùng kênh mạng chưa được xác minh rồi coi đó là chứng cứ độc lập: attacker có thể gửi **root giả và reply giả phù hợp với nhau**. Trong ví dụ local lab, bạn tự tạo CA nên biết nguồn của nó; production phải đối chiếu certificate fingerprint, công cụ CA và quy trình tin cậy độc lập.

## 5. KeyStore và alias trong luồng CSR → reply

Đối với JDK, lệnh tạo key pair ban đầu thường tạo một **`PrivateKeyEntry`** trong PKCS#12:

~~~text
app.p12:
  alias = app-server
  PrivateKeyEntry
    private key = RSA private key
    certificate chain = self-signed placeholder (lúc mới tạo)
~~~

Sau khi CSR được ký, thao tác đúng là **cài reply trên alias `app-server` đang chứa private key**, thay **certificate chain** nhưng **giữ khóa riêng cũ**. Không tạo key pair mới chỉ để import reply, nếu không bạn sẽ có public/private key không khớp.

| Alias/lệnh | Điều xảy ra |
| --- | --- |
| `-genkeypair -alias app-server` | Tạo PrivateKeyEntry với private key và certificate tự ký ban đầu |
| `-certreq -alias app-server` | Tạo CSR ký bởi private key của **cùng alias** |
| `-importcert -alias demo-ca -file ca.crt` | Với alias CA mới, thêm `TrustedCertificateEntry` chứa CA cert (demo) |
| `-importcert -alias app-server -file app-issued.crt` | Vì `app-server` đã là key entry, lệnh xử lý file như **certificate reply**, xác minh khớp khóa và thay chain |
| `-list -v -alias app-server` | Kiểm entry type, chain length, leaf subject, issuer, SAN |
| `-list -v -alias demo-ca` | Kiểm trusted certificate entry; không có private key |

**Lưu ý:** Nếu import certificate leaf vào một alias hoàn toàn **mới** thay vì alias có private key, công cụ có thể tạo `TrustedCertificateEntry` chứ **không cài leaf vào PrivateKeyEntry**. Khi TLS server cần private key và chain, đó là lỗi thiết kế.

### 5.1. Store password và key password

- `-storepass`: password khi mở/lưu KeyStore theo provider.
- `-keypass`: password bảo vệ private key entry khi provider/type hỗ trợ.
- Một số triển khai PKCS12 yêu cầu key password **khớp store password**; demo dùng cùng giá trị `changeit-demo`.
- Lỗi password có thể biểu hiện khi `-certreq` đọc private key hoặc `-importcert` sửa chain, không chỉ lúc `-list`.

Trong production, **đừng đưa password vào terminal history, process listing, CI logs hoặc source**. Bài lab cố tình dùng literal để có thể chạy lặp trong thư mục thử nghiệm tách biệt. Hệ thống thật dùng secret manager/callback, quyền truy cập file/HSM và chính sách rotation phù hợp.

## 6. Thực hành end-to-end với `keytool`: tạo CA demo và cấp CSR

Tất cả lệnh sau đã được thử với **JDK 17+ trên thư mục tạm rỗng**. Chạy từng lệnh trong một **thư mục thực hành mới**; không chạy trong thư mục có keystore production, vì tên file được dùng lại.

Kịch bản: Tạo CA `demo-ca`, tạo identity server `app-server` cho DNS `app.example.test`, xuất CSR và nhận leaf cert do CA demo ký, import CA và reply. Đây là **phòng thực hành**, không phải hệ thống CA có quy trình thẩm định domain thực tế.

### Bước 1 — Tạo root CA tự ký cho lab

~~~bash
keytool -genkeypair -alias demo-ca -keyalg RSA -keysize 2048 -dname "CN=Training Demo Root,O=Learning,C=VN" -validity 365 -ext "bc=ca:true" -ext "ku=keyCertSign,cRLSign" -keystore ca.p12 -storetype PKCS12 -storepass changeit-demo -keypass changeit-demo -noprompt
~~~

- `-genkeypair` tạo private/public key pair và certificate tự ký ban đầu.
- `-ext "bc=ca:true"` khai báo `BasicConstraints CA=true`, điều cần có với vai trò CA.
- `-ext "ku=keyCertSign,cRLSign"` dành `KeyUsage` cho việc ký certificate và CRL.
- `-dname` là Subject DN của **CA**, không phải server.
- Key RSA 2048 và thời gian 365 ngày chỉ dùng để demo; CA production phải tuân thủ tiêu chuẩn, chính sách, cách giữ khóa riêng, bảo vệ online/offline và thời hạn riêng.

**Không dùng `ca.p12` demo làm CA production**: private key CA thử nghiệm chỉ được bảo vệ bằng password mẫu; CA thật cần chính sách issuance, audit, phân quyền, backups và thường HSM.

### Bước 2 — Xuất certificate công khai của CA

~~~bash
keytool -exportcert -alias demo-ca -keystore ca.p12 -storepass changeit-demo -rfc -file ca.crt
~~~

File `ca.crt` là **certificate public**, không có private key. `-rfc` xuất dạng PEM, dễ truyền và xem. Kiểm thông tin certificate nếu cần:

~~~bash
keytool -printcert -file ca.crt
~~~

Trong production, **phải so fingerprint SHA-256/nguồn phân phối CA qua kênh đã xác thực** trước khi tin certificate, chứ không tự đặt tin cậy vì file tên `ca.crt`.

### Bước 3 — Tạo identity PKCS12 và self-signed placeholder

~~~bash
keytool -genkeypair -alias app-server -keyalg RSA -keysize 2048 -dname "CN=app.example.test,O=Learning,C=VN" -validity 30 -ext "san=dns:app.example.test" -keystore app.p12 -storetype PKCS12 -storepass changeit-demo -keypass changeit-demo -noprompt
~~~

Lúc này alias `app-server` chứa **PrivateKeyEntry** và chain self-signed tạm. Certificate tạm **không phải leaf đã được CA demo ký**; nó chỉ cho phép `keytool` lưu identity/khóa ban đầu. `CN` đặt tên cho mẫu; HTTPS/JSSE thực tế phải kiểm **SAN DNS** theo chuẩn và chính sách TLS.

Nếu bạn chạy lại `-genkeypair` trên cùng alias khi đã tồn tại, `keytool` có thể từ chối hoặc dẫn đến yêu cầu xử lý alias; đừng xóa private key hiện hữu và sinh key mới khi đang chờ reply từ CSR cũ.

### Bước 4 — Tạo CSR PKCS#10 từ đúng alias

~~~bash
keytool -certreq -alias app-server -file app.csr -rfc -keystore app.p12 -storepass changeit-demo -ext "san=dns:app.example.test" -ext "ku=digitalSignature,keyEncipherment" -ext "eku=serverAuth"
~~~

- `-certreq` ký CSR bằng private key trong `app.p12` của alias `app-server`.
- `-file app.csr -rfc` tạo CSR dạng PEM. Đừng nhầm file này với certificate issuer trả về.
- `-ext san=dns:app.example.test` yêu cầu SAN dạng DNS.
- `ku` là yêu cầu **KeyUsage**, `eku=serverAuth` là yêu cầu **ExtendedKeyUsage** cho TLS server. CA phải quyết định cuối cùng theo chính sách; không được cấp quyền chỉ vì CSR đề xuất.
- Với TLS 1.3, `digitalSignature` là usage quan trọng cho certificate key ký handshake; `keyEncipherment` được đưa vào lab cho ví dụ RSA rộng hơn, không có nghĩa TLS 1.3 sử dụng RSA key transport.

Xem CSR:

~~~bash
keytool -printcertreq -file app.csr -v
~~~

Bạn có thể thấy Subject, algorithm, public key, signature và extension requests. Nội dung cụ thể phụ thuộc JDK/provid­er và thông tin bạn khai báo; đừng hard-code fingerprint động vào test.

**An toàn:** Có thể gửi CSR cho CA vì nó không có private key. Tuy nhiên, CSR vẫn chứa danh tính/tên máy/chi tiết tổ chức, nên chia sẻ qua đúng kênh của CA và không đưa thông tin nhạy cảm không cần thiết.

### Bước 5 — CA demo thẩm định (mô phỏng) và ký leaf certificate

~~~bash
keytool -gencert -alias demo-ca -infile app.csr -outfile app-issued.crt -rfc -keystore ca.p12 -storepass changeit-demo -validity 30 -ext "san=dns:app.example.test" -ext "ku=digitalSignature,keyEncipherment" -ext "eku=serverAuth"
~~~

Lệnh dùng private key của **demo CA** để ký certificate cho public key trong CSR.

**Điểm quyết định:** Ở demo ta cho CA cấp SAN một cách tường minh qua `-ext`. **CA production không được chỉ lấy SAN/Subject tự khai trong CSR rồi ký vô điều kiện.** CA phải kiểm quyền đối với domain/tổ chức, lựa chọn certificate profile, validate yêu cầu, đặt serial, thời hạn, extensions và ghi dấu audit theo tiêu chuẩn/policy.

`app-issued.crt` là **CA-issued leaf certificate**, không phải private key. Trong demo root CA ký trực tiếp leaf, nên chưa có intermediate. Với CA thật, phản hồi có thể là leaf đơn lẻ, **PKCS#7 chain** hoặc certificate bundle có intermediate(s).

### Bước 6 — Import root CA demo thành trusted certificate entry

~~~bash
keytool -importcert -alias demo-ca -file ca.crt -keystore app.p12 -storepass changeit-demo -noprompt
~~~

- `demo-ca` là alias **mới**, không phải `app-server`.
- Lúc này `app.p12` có thể lưu `TrustedCertificateEntry` cho root demo. Vì root được tạo **ngay trong lab**, ta có thể chủ động đặt nó làm trust anchor demo.
- `-noprompt` bỏ xác nhận tương tác; **không dùng để tự động tin CA chưa được xác minh** trong production.
- Trước khi nhập một CA certificate thực, phải đối chiếu fingerprint/nguồn cung cấp CA bằng kênh đáng tin, đặt quyền đọc/ghi hợp lý.

Tại sao nhập CA trước reply? `keytool` cần đủ thông tin về issuer chain và trust để dựng/kiểm đường dẫn certificate reply. Trong lab chỉ có root→leaf nên root đủ cho chain 2 phần tử. Với intermediate, có thể phải import certificate của intermediate hoặc cung cấp toàn bộ chain đúng format; phải kiểm chain sau khi cài.

### Bước 7 — Cài certificate reply vào **cùng alias private key**

~~~bash
keytool -importcert -alias app-server -file app-issued.crt -keystore app.p12 -storepass changeit-demo -noprompt
~~~

Đây là bước quan trọng nhất:

1. `keytool` tìm **PrivateKeyEntry** có alias `app-server`.
2. Nó kiểm tra public key trong certificate reply có khớp private key hiện có theo provider/khả năng kiểm tra.
3. Nó kiểm đường dẫn/chứng chỉ issuer cần thiết cho việc cài reply, rồi thay certificate chain của **đúng private-key entry**.
4. **Private key vẫn ở alias `app-server`**, không phải một trusted certificate alias mới.

Sau khi thành công, output lab của `keytool` cho biết certificate reply đã được cài vào KeyStore.

**Không làm sai:**

~~~bash
# SAI VỀ MỤC ĐÍCH: alias mới không nối vào private key "app-server".
keytool -importcert -alias issued-copy -file app-issued.crt -keystore app.p12 -storepass changeit-demo -noprompt
~~~

Đây chỉ là **lệnh đối chiếu minh họa lỗi logic**, không chạy nó trong bài thực hành. Alias `issued-copy` không có private key nên không thay chain của `app-server`; có thể tạo certificate-only entry hoặc dẫn tới các hành vi provider khác nhau, nhưng không tạo identity đúng.

### Bước 8 — Xem KeyStore sau khi nhập reply

~~~bash
keytool -list -v -alias app-server -keystore app.p12 -storetype PKCS12 -storepass changeit-demo
keytool -list -v -alias demo-ca -keystore app.p12 -storetype PKCS12 -storepass changeit-demo
~~~

Đối với lab vừa tạo:

- `app-server` phải là **PrivateKeyEntry**, certificate chain length **2**.
- `chain[0]` là leaf cấp cho `app.example.test` với SAN `DNSName: app.example.test`.
- `chain[1]` là root CA demo `Training Demo Root`.
- `demo-ca` là trusted certificate entry, chỉ có certificate; không chứa private key CA vì đó là **CA certificate công khai được export**.
- Private key của **demo CA** vẫn chỉ ở **`ca.p12`**, không được copy sang `app.p12`.

Nếu giá trị thực không giống, đừng bỏ qua. Kiểm file đúng, alias đúng, issuer, SAN, chain và private/public key trước khi đưa vào ứng dụng.

## 7. Java 17+: đọc lại chain, kiểm SAN, chữ ký và PKIX

Đoạn sau là **chương trình Java 17+ độc lập**, chạy sau **tám bước `keytool` ở phần 6** trong cùng thư mục có `app.p12`. Không cần thư viện ngoài JDK. Nó thực hiện những phép kiểm minh họa có ích mà không in private key hay password.

Lưu đúng tên **`CsrChainDemo.java`**:

~~~java
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.security.KeyStore;
import java.security.MessageDigest;
import java.security.Signature;
import java.security.cert.CertPath;
import java.security.cert.CertPathValidator;
import java.security.cert.Certificate;
import java.security.cert.CertificateFactory;
import java.security.cert.PKIXParameters;
import java.security.cert.TrustAnchor;
import java.security.cert.X509Certificate;
import java.util.Arrays;
import java.util.List;
import java.util.Set;

public class CsrChainDemo {
    public static void main(String[] args) throws Exception {
        // Mật khẩu mẫu CHỈ cho lab. Production lấy từ secret manager.
        char[] password = "changeit-demo".toCharArray();
        try {
            KeyStore store = KeyStore.getInstance("PKCS12");
            try (InputStream in =
                    Files.newInputStream(Path.of("app.p12"))) {
                store.load(in, password);
            }

            String alias = "app-server";
            String caAlias = "demo-ca";
            boolean privateEntry = store.entryInstanceOf(
                    alias, KeyStore.PrivateKeyEntry.class);
            boolean caTrusted = store.entryInstanceOf(
                    caAlias, KeyStore.TrustedCertificateEntry.class);
            KeyStore.PrivateKeyEntry entry =
                    (KeyStore.PrivateKeyEntry) store.getEntry(
                            alias, new KeyStore.PasswordProtection(password));

            Certificate[] chain = entry.getCertificateChain();
            X509Certificate leaf = (X509Certificate) chain[0];
            X509Certificate root =
                    (X509Certificate) store.getCertificate(caAlias);

            boolean issuerMatches = leaf.getIssuerX500Principal()
                    .equals(root.getSubjectX500Principal());
            boolean orderMatches = chain.length == 2
                    && MessageDigest.isEqual(chain[1].getEncoded(),
                            root.getEncoded());
            boolean sanContainsHost = leaf.getSubjectAlternativeNames()
                    .stream().anyMatch(field ->
                            field.get(0).equals(2)
                            && "app.example.test".equals(field.get(1)));

            // Chứng minh private key trong entry khớp public key
            // của certificate leaf bằng cách sign/verify dữ liệu giả.
            byte[] message =
                    "csr-chain-proof".getBytes(StandardCharsets.UTF_8);
            Signature signer = Signature.getInstance("SHA256withRSA");
            signer.initSign(entry.getPrivateKey());
            signer.update(message);
            byte[] signed = signer.sign();
            Signature verifier = Signature.getInstance("SHA256withRSA");
            verifier.initVerify(leaf.getPublicKey());
            verifier.update(message);
            boolean keyMatchesCert = verifier.verify(signed);

            leaf.checkValidity();
            root.checkValidity();

            // CertPath không đưa trust anchor vào list chứng thư cần
            // kiểm. Lab root ký leaf trực tiếp => path chỉ có leaf.
            CertPath path = CertificateFactory.getInstance("X.509")
                    .generateCertPath(List.of(leaf));
            PKIXParameters parameters = new PKIXParameters(
                    Set.of(new TrustAnchor(root, null)));
            parameters.setRevocationEnabled(false); // CHỈ DEMO!
            CertPathValidator.getInstance("PKIX")
                    .validate(path, parameters);

            System.out.println("KeyStore type        = " + store.getType());
            System.out.println("PrivateKeyEntry      = " + privateEntry);
            System.out.println("Trusted CA entry     = " + caTrusted);
            System.out.println("Chain length         = " + chain.length);
            System.out.println("Issuer matches CA    = " + issuerMatches);
            System.out.println("Chain order correct  = " + orderMatches);
            System.out.println("Leaf SAN DNS correct = " + sanContainsHost);
            System.out.println("Private matches cert = " + keyMatchesCert);
            System.out.println("PKIX path valid      = true");
        } finally {
            Arrays.fill(password, '\0');
        }
    }
}
~~~

Biên dịch và chạy với JDK 17+:

~~~bash
javac CsrChainDemo.java
java CsrChainDemo
~~~

**Đầu ra đã kiểm chứng** sau khi thực hiện đầy đủ chuỗi lệnh `keytool` (trên PKCS12 mới):

~~~text
KeyStore type        = PKCS12
PrivateKeyEntry      = true
Trusted CA entry     = true
Chain length         = 2
Issuer matches CA    = true
Chain order correct  = true
Leaf SAN DNS correct = true
Private matches cert = true
PKIX path valid      = true
~~~

### 7.1. Giải thích chính xác từng phép kiểm

- **`PrivateKeyEntry = true`:** Alias `app-server` giữ private key và certificate chain; reply không bị import thành một trusted certificate-only alias.
- **`Trusted CA entry = true`:** Alias `demo-ca` chứa certificate được import như một trust entry; nó **không đưa private key của CA** từ `ca.p12` vào `app.p12`.
- **`Chain length = 2`:** Demo có root ký leaf trực tiếp; production có intermediate thường dài hơn. Phép kiểm này là **kỳ vọng cố định riêng cho lab**.
- **`Issuer matches CA = true`:** Subject của root trùng Issuer DN của leaf; đây chỉ là so sánh **tên DN**, **không thay kiểm chữ ký**. Bất kỳ attacker nào cũng có thể tự tạo certificate mang cùng DN.
- **`Chain order correct = true`:** Byte của certificate `chain[1]` trùng với root certificate được lấy từ alias `demo-ca` trong lab.
- **`Leaf SAN DNS correct = true`:** Kiểm X.509 SAN có DNS name đúng mẫu. Một phép tìm chuỗi trong SAN **không thay đầy đủ thuật toán hostname verification của HTTPS**, vốn còn quy định wildcard, IDNA, IP, chuẩn so khớp và cách lấy host kết nối.
- **`Private matches cert = true`:** Dùng private key trong `app-server` để ký một thông điệp test, public key trong leaf để xác minh. Đây là phép kiểm có ý nghĩa hơn việc so alias hoặc so Subject DN.
- **`PKIX path valid = true`:** `CertPathValidator("PKIX")` kiểm path leaf → **trust anchor root được chọn tường minh** trong cấu hình demo. Ví dụ không tự động chọn mọi CA trên máy, không chứng minh hostname client và **đã cố ý tắt revocation** chỉ cho lab.

**Không biến code lab thành TLS trust manager production**: Chuỗi chứng thư tin cậy thật cần policy, hostname verification của client, kiểm thu hồi khi bắt buộc, certificate transparency/pinning theo threat model, bảo vệ danh tính CA và lựa chọn trust anchor tin cậy. Chương trình demo không mở HTTPS, không làm mTLS handshake và không chứng minh CA này được các trình duyệt công cộng công nhận.

### 7.2. Vì sao PKIX CertPath chỉ chứa leaf ở demo?

Trong `PKIXParameters`, `TrustAnchor` đại diện cho **điểm tin cậy ngoài path**. Root đã được nêu là trust anchor, nên khi root ký leaf trực tiếp, list certificate cần validate là `List.of(leaf)`, không thêm root vào list.

Khi có intermediate:

~~~java
// Mảnh ghép minh họa; intermediate phải được lấy/kiểm nguồn
// và root phải là TrustAnchor được phép tin.
CertPath path = CertificateFactory.getInstance("X.509")
        .generateCertPath(List.of(leaf, intermediate));
~~~

Thứ tự path **leaf → intermediate**, còn root nằm trong tập `TrustAnchor`. Đoạn này không phải chương trình độc lập vì `leaf` và `intermediate` cần được nạp. Việc path validator thành công phụ thuộc extensions, chữ ký, basic constraints, trust anchor, thời hạn và policy.

## 8. Nếu có intermediate CA: chain dài hơn và cách import

Trong production, root private key thường không ký leaf trực tiếp. CA tổ chức phân tầng:

~~~text
Trust anchor: Example Root CA   [trusted ở client/truststore]
      |
      v
Issuing Intermediate CA        [CA=true, keyCertSign; root ký]
      |
      v
app.example.test leaf          [CA=false, SAN, serverAuth; intermediate ký]
~~~

**Điểm khác so với lab** là **CA ký CSR leaf** thường là intermediate, không phải root. Để import đúng:

1. Xác định identity alias đã tạo CSR (ví dụ `app-server`) và kiểm public key của leaf reply **khớp private key đang có**.
2. Nhận **leaf certificate** và toàn bộ **intermediate chain** do CA cung cấp qua kênh đúng.
3. Xác minh root trust anchor bằng nguồn đáng tin; lưu trong truststore phù hợp và/hoặc import vào nơi `keytool` cần để dựng chain theo provider.
4. Cài intermediate certificates theo quy tắc và định dạng mà `keytool`/provider hỗ trợ (hoặc cung cấp certificate reply dạng chain/PKCS#7 được nhận diện); **đừng giả định leaf-only file luôn đủ**.
5. Import phản hồi vào **alias private key gốc**. Sau đó kiểm chain length và thứ tự leaf → intermediate → ... root (nếu root được lưu trong chain).
6. Kiểm issuer/subject linking, chữ ký, basic constraints CA, key usage, key path length, SAN/EKU leaf và path đến trust anchor. Đừng chỉ đếm chain length.

**Quan trọng:** `KeyStore.getCertificateChain` có thể chứa root hoặc chỉ các issuer certificates tùy provider/cách cài. TLS server **thường không cần gửi root**; việc client tìm được root là do truststore, không phải do root nằm trong reply. Không viết logic production chỉ dựa vào `chain.length == 3` mà bỏ kiểm chữ ký và trust anchor.

### 8.1. CA bundle và PKCS#7

Một CA có thể trả:

| File | Nội dung thường gặp | Cần xử lý |
| --- | --- | --- |
| `app-issued.crt` / `.cer` | Một X.509 leaf, PEM hoặc DER | Cài vào alias private key sau khi issuer chain có thể dựng |
| `intermediate.crt` | X.509 của CA trung gian | Đưa vào chain building/trust workflow như yêu cầu, **không tự coi mọi intermediate là root trusted** |
| `root.crt` | Root public certificate | Chỉ đặt làm trust anchor sau xác minh ngoài băng |
| `.p7b` / PKCS#7 | Tập certificate hoặc signed-data certificate chain, thường **không** mang private key | Có thể được `keytool -importcert` dùng làm reply tùy content/provider |
| `.p12` / PKCS#12 | Có thể chứa private key và chain hoặc chỉ certificates, tùy được export như thế nào | **Không mặc định import đè identity** nếu đang giữ private key gốc; kiểm contents/type trước |

PEM có dạng:

~~~text
-----BEGIN CERTIFICATE-----
... Base64 X.509 DER ...
-----END CERTIFICATE-----
~~~

CSR PEM có nhãn khác:

~~~text
-----BEGIN CERTIFICATE REQUEST-----
... Base64 PKCS#10 DER ...
-----END CERTIFICATE REQUEST-----
~~~

**Không gửi PKCS12 chứa private key cho CA nếu quy trình chỉ yêu cầu CSR.** Không tự ý gộp certificates sai thứ tự rồi nghĩ file mới đã có chain hợp lệ. Các công cụ hỗ trợ nhập bundle khác nhau; kiểm đáp ứng của `keytool -list -v` và thực hiện validation thực tế.

### 8.2. Intermediate không phải luôn là trust anchor

Một intermediate certificate có `CA=true` và có chữ ký của root nhưng **không tự động được tin** chỉ vì được server gửi. Nó là chứng cứ để xây **certificate path**, còn trust anchor cuối phải nằm trong chính sách trust của bên xác minh. Nếu ứng dụng tùy ý thêm mọi intermediate nhận được vào root truststore, có thể vô tình mở rộng phạm vi tin cậy.

Trường `BasicConstraints CA=true` chỉ nói một certificate **được tuyên bố có vai trò CA**; quyền lực chứng thực phải đến từ **chuỗi chữ ký hợp lệ và trust anchor được chấp nhận**. Không đánh đồng bit CA=true với “CA được tất cả máy tin”.

## 9. Các extension X.509 trong CSR và certificate reply

CSR có thể **đề xuất**, CA **phê duyệt/phát hành**. Mỗi extension có ý nghĩa mật mã/vận hành riêng:

| Extension | Trên leaf TLS server | Trên CA root/intermediate |
| --- | --- | --- |
| **Subject Alternative Name (SAN)** | DNS/IP của endpoint; bên client thực hiện matching theo chính sách | Có thể liên quan name constraints, không phải nơi tự cấp hostname cho leaf |
| **BasicConstraints** | Thường CA=false hoặc không phải CA | Phải CA=true để chứng nhận CA và đáp ứng path constraints |
| **KeyUsage** | Ví dụ digitalSignature cho TLS dùng chữ ký; keyEncipherment chỉ khi profile/giao thức cần | keyCertSign cho ký certificate, cRLSign nếu ký CRL |
| **ExtendedKeyUsage (EKU)** | serverAuth cho TLS server, clientAuth cho mTLS client tùy mục đích | Thường khác leaf, phụ thuộc policy và path validation |
| **Subject Key Identifier / Authority Key Identifier** | Hỗ trợ nhận diện khóa/issuer khi xây chain | Hỗ trợ nối issuer/subject key, không thay kiểm chữ ký |
| **Certificate Policies / NameConstraints** | Tùy CA/profile | Có thể hạn chế không gian cấp chứng thư hoặc mục đích CA |
| **CRL Distribution Points / AIA** | Gợi ý nơi tra thu hồi/CA issuer | Hỗ trợ chain building và kiểm thu hồi theo thực thi |

**Đừng chỉ nhìn CN:** Tên chứng thư server phải được kiểm theo **SAN** phù hợp với hostname kết nối, xử lý DNS/IP, wildcard và IDNA theo giao thức. `CN=app.example.test` trong demo không phải nguồn duy nhất/đủ dùng cho hostname validation.

**Đừng dựa vào `-ext` trong CSR để khẳng định certificate đã có extension đó.** Sau CA ký, kiểm **certificate leaf thực tế** bằng:

~~~bash
keytool -printcert -file app-issued.crt -v
~~~

CA có thể bỏ, chỉnh hoặc thay đổi các requested extensions. Đó là một phần của CA policy chứ không phải bug của PKCS#10.

## 10. CA response có được “tin” ngay khi nhận không?

**Không.** Certificate reply là đầu ra của CA, nhưng bên triển khai phải xác minh nhiều lớp:

1. **Đúng yêu cầu:** Public key trong leaf tương ứng private key sinh CSR; alias private-key entry đúng, không đổi key pair giữa chừng.
2. **Đúng identity:** SAN/subject và mục đích sử dụng được cấp đúng hồ sơ đã duyệt.
3. **Đúng issuer:** Leaf do CA dự kiến cấp, chữ ký và chain hợp lệ tới trust anchor được chọn.
4. **Đúng thời gian/constraints:** Validity, basic constraints, key usages, EKU, signature algorithm, key size, policies.
5. **Đúng nguồn và luồng:** CA account, giao thức issuance, fingerprint/serial/chi tiết giao dịch được đối chiếu phù hợp.
6. **Đúng nơi sử dụng:** Không dùng cert serverAuth như cert clientAuth nếu profile không cho phép; không coi root demo là public CA.
7. **Đúng vận hành:** KeyStore file và private key được bảo vệ, backup/rotation/rollback có kiểm soát.

Việc `keytool -importcert` báo `Certificate reply was installed in keystore` chứng tỏ **cài reply** thành công theo kiểm tra của công cụ và provider, **không phải tuyên bố rằng mọi peer sẽ tin CA** hay TLS hostname chắc chắn hợp lệ.

**Ví dụ tấn công:** Attacker có thể gửi một `ca.crt` do chính họ tự ký và một `app-issued.crt` do họ ký; nếu bạn import cả hai mà không xác thực nguồn và cho client dùng truststore đó, path có thể hợp lệ **đối với trust anchor giả vừa import**. Đây là lý do root trust phải được phân phối/kiểm bằng kênh độc lập.

## 11. Phân biệt certificate reply, import cert và import keystore

Trong `keytool`, cùng lệnh `-importcert` có thể có ngữ nghĩa khác do **alias đã tồn tại hay chưa**:

~~~text
Alias chưa tồn tại + certificate
  → thường tạo TrustedCertificateEntry

Alias đã là PrivateKeyEntry + certificate reply
  → xử lý reply, cài/đổi certificate chain cho private key ấy
~~~

Lệnh `-importkeystore` lại là thao tác nhập **key entries hoặc certificates từ một keystore khác**; nó **không phải** bước bắt buộc khi bạn đã giữ private key gốc trong `app.p12` và chỉ nhận certificate reply từ CA.

**Không dùng `-importkeystore` một cách mù quáng** để “cài CSR reply”. Nếu file nguồn chứa private key khác, có thể ghi đè identity, thay alias hoặc làm lệch key/cert chain. Hãy đọc alias/type của cả nguồn và đích, kiểm SHA-256 public key/certificate, kế hoạch backup và password policy trước khi migration.

### 11.1. Certificate chain trong file khác chain trong đường dẫn xác minh

- `getCertificateChain(alias)` là danh sách certificates **đang lưu** trong `PrivateKeyEntry`.
- PKIX `CertPath` là danh sách certificates cần **validator kiểm tra**, thường kết thúc **trước** trust anchor do bạn cấu hình.
- TLS peer có thể nhận chain server gửi nhưng vẫn cần trust anchor riêng và hostname validation; server không thể “gửi trust” chỉ bằng cách đưa thêm root vào chain.
- CA-issued certificate có thể là leaf hợp lệ nhưng hệ thống thiếu intermediate/trust anchor làm build path thất bại; điều đó không chứng tỏ private key bị hỏng.

## 12. Chẩn đoán lỗi `keytool` theo từng giai đoạn

| Triệu chứng | Nguyên nhân khả dĩ | Cách kiểm/khắc phục |
| --- | --- | --- |
| `-certreq` báo không thấy alias/private key | Alias sai hoặc chỉ có TrustedCertificateEntry | `keytool -list -v -alias ...`, bảo đảm PrivateKeyEntry tồn tại |
| `-certreq` không mở được private key | Sai key/store password hoặc provider | Xác định đúng type/entry protection, không log password |
| CSR thiếu SAN | Không đặt requested extension hoặc lệnh/CA profile khác | `-printcertreq -v` rồi kiểm leaf sau khi CA ký |
| `Public keys in reply and keystore don't match` | Reply thuộc CSR/key pair khác, hoặc private key bị thay | So key pair/public key, đúng file và alias, không gen lại key trong khi chờ |
| `Failed to establish chain from reply` | Thiếu CA issuer/intermediate, chain sai, CA chưa được tin hoặc input format sai | Kiểm certificates CA từ nguồn tin cậy, import/đưa chain đúng format, kiểm issuer signature |
| Certificate reply được nhập nhưng alias `app-server` vẫn self-signed | Import nhầm alias hoặc file không đúng | Kiểm `-list -v -alias app-server`, import lại đúng reply vào đúng alias nếu an toàn |
| `-importcert` tạo TrustedCertificateEntry thay vì identity | Alias dùng chưa có PrivateKeyEntry | Dùng alias sinh CSR ban đầu; không xóa private key |
| Chain order sai hoặc chain dài 1 sau reply | Thiếu CA chain / response chỉ chứa leaf | Dựng chain, bổ sung intermediate, kiểm provider |
| Peer TLS báo certificate unknown | Trust anchor không có trong peer truststore hoặc chain không dựng được | Cung cấp intermediate, cấu hình truststore của peer, không ép trust-all |
| TLS báo hostname mismatch | SAN không chứa DNS/IP cần kiểm | CA cấp lại đúng SAN đã thẩm định; không tắt hostname verification |
| Certificate expired/not yet valid | Validity window sai, clock sai hoặc chưa renew | Kiểm `-printcert -v`, thời gian UTC và lịch gia hạn |
| `basicConstraints`/`keyCertSign` fail ở issuer | Intermediate không được cấp quyền CA hoặc constraints sai | CA phải phát hành đúng CA profile; không “sửa cert” sau khi ký |
| Key algorithm/signature không được chấp nhận | Policy TLS/PKIX hoặc provider không hỗ trợ | Kiểm algorithm suite, key size, JDK provider, issuance policy |
| PKCS12 không load được | Sai password, type, file hỏng hoặc incompatibility | Kiểm file/type/password, backup và provider; không thay extension để “chuyển format” |
| Chứng thư hoạt động với một client nhưng không với client khác | Truststore/certificate policy/thu hồi và intermediate khác nhau | Kiểm chain và trust mỗi client, không suy ra từ một lượt kiểm |
| Mọi lệnh thành công nhưng chain vẫn chưa tin cậy | Root CA demo chưa được bên dựa vào cài/kiểm | Phân biệt import cục bộ với trust policy của client |

**Cách điều tra an toàn:** Ghi alias, type, certificate fingerprint, issuer, SAN, chain length, các mã lỗi và **thời điểm/phiên bản JDK**, nhưng **không ghi password/private key/token**. Kiểm cả phản hồi CA thực tế, không chỉ CSR. Hạn chế hiển thị certificate Subject nếu chúng chứa thông tin nhạy cảm ngoài mục đích logging.

## 13. Trách nhiệm của CA và của bên sử dụng chứng thư

**CA issuance** gồm nhiều bước nằm ngoài `keytool`:

- **Xác minh quyền sở hữu/tác quyền đối với định danh** theo chính sách: DNS/domain, organization, device identity hoặc application principal.
- Áp profile phát hành: subject, SAN, validity, serial, key algorithm, BasicConstraints, KU/EKU, extensions khác.
- Bảo vệ private key CA và signing service, phân quyền phê duyệt, audit và log issuance.
- Thiết kế thời hạn, renewal, revocation, CRL/OCSP, incident response.
- Cung cấp **đầy đủ intermediate certificates** để bên triển khai không tự thu thập từ nguồn thiếu tin cậy.

**Bên xin cấp/chủ ứng dụng** chịu trách nhiệm:

- Tạo private key đúng nơi và bảo vệ nó; khi có HSM/KMS phải giữ non-exportable nếu yêu cầu.
- Sinh CSR từ đúng key pair, đối chiếu nội dung yêu cầu.
- Dùng CA và các thông tin trả về qua kênh chính thức; xác minh certificate được cấp khớp mục đích.
- Import reply vào **private key alias gốc**, giữ chain và cấu hình TLS đúng.
- Giới hạn quyền đọc keystore; không chia sẻ password/file cho người không cần.
- Theo dõi expiry/rotation và khả năng reload không ngắt dịch vụ.

**Bên kiểm chứng (client/peer)** chịu trách nhiệm:

- Tin đúng root/trust anchors theo policy; không tự tin mọi certificate server gửi.
- Xác minh PKIX path, định danh hostname/subject phù hợp, KU/EKU, thời hạn, revocation/các chính sách bắt buộc.
- Không dùng `TrustManager` “accept all” hoặc tắt hostname verification để chữa lỗi nhập chain.

Một chuỗi chứng thư đúng chỉ trả lời câu hỏi **public key này được những CA nào chứng nhận theo trust policy**, không tự động chứng minh ứng dụng có quyền truy cập tài nguyên. Authentication và authorization là hai tầng khác nhau.

## 14. Bảo mật quy trình issuance và vòng đời khóa

### 14.1. Không làm lộ private key khi tạo CSR

CSR và certificate reply đều có thể lưu/chuyển như artifact công khai theo policy, nhưng **private key không**. Khi dùng `-certreq`, `keytool` đọc private key tại chỗ để ký CSR. Không export `.p12` cho CA, không dán khóa vào ticket/chat, không ghi password vào audit log.

Thư mục thực hành trong bài có **ca.p12** (private key CA demo) và **app.p12** (private key server demo). Hai file phải được xem là **secret-bearing** dù file có password. Xóa bản sao lab đúng quy trình khi xong; đừng commit vào Git hoặc nộp lên hệ thống công cộng.

### 14.2. Không tự thay certificate mà mất private key

Nếu bạn đã tạo CSR từ khóa A và nhận leaf cho public key A, nhưng deploy lại sinh khóa B rồi import leaf A, kết nối ký bằng private B không tương ứng với certificate A. Giải pháp không phải bỏ kiểm khớp key; phải khôi phục private A an toàn hoặc tạo CSR mới cho B và yêu cầu CA cấp certificate mới.

Trong kế hoạch certificate rotation, có thể dùng **alias phiên bản mới** và triển khai blue/green trước khi xóa cũ. Với key rotation, tạo key pair mới + CSR mới, cập nhật certificate chain, kiểm TLS handshake, thông báo các peer pinning nếu có. Nếu chỉ renew cùng key pair, đánh giá chính sách reuse và vòng đời khóa.

### 14.3. Certificate revocation và thời gian

Certificate có thể còn hạn nhưng đã bị thu hồi vì lộ key hoặc thay đổi tổ chức. `checkValidity()` chỉ kiểm NotBefore/NotAfter, **không kiểm thu hồi**. `CertPathValidator` có các cơ chế cấu hình policy revocation; demo đặt `setRevocationEnabled(false)` để tránh phụ thuộc CA demo không có CRL/OCSP. **Trong production không sao chép giá trị false như một quyết định bảo mật mặc định.**

Khi TLS client cần kiểm certificate revocation, hãy xác định cơ chế, chính sách hard/soft-fail và nguồn CRL/OCSP theo tiêu chuẩn/điều kiện vận hành. Không suy luận rằng có `PKIX path valid = true` trong demo đồng nghĩa đã kiểm revocation, hostname, TLS chain negotiation và mọi chính sách doanh nghiệp.

### 14.4. SAN và quyết định trust có thể thay đổi qua thời gian

Một hostname mới hoặc chuyển sang mTLS có thể cần certificate mới với SAN/EKU khác; không sửa file leaf đã ký bằng cách thay text trong PEM. Chữ ký CA bảo vệ dữ liệu certificate, nên **mọi thay đổi trường phải được CA cấp lại**.

Certificate truststore của bên kiểm chứng cũng thay đổi khi CA root được thêm, gỡ, rollover hoặc cập nhật. Phải có release/rollback plan cho cả **server identity certificate** lẫn **client truststore**, chứ không chỉ chạy lại lệnh `-importcert`.

## 15. Tình huống thực tế

### 15.1. Spring Boot HTTPS muốn chứng thư CA cấp

Nhóm phát triển có `app.p12`, alias `app-server` chứa private key. Sau CSR và CA reply, cần import đúng alias, kiểm chain và cấu hình `server.ssl.key-store`, `server.ssl.key-store-type`, password và alias theo môi trường/framework được hỗ trợ. Nếu private key/certificate chain không tương ứng, HTTPS handshake có thể thất bại dù file `.p12` “mở được”.

**Chú ý:** cấu hình cụ thể của Spring Boot thay đổi theo version; bài này mô tả khái niệm KeyStore/PKI, không áp đặt thuộc tính cấu hình cho mọi version.

### 15.2. mTLS giữa hai dịch vụ Java

Service A vừa cần **identity PrivateKeyEntry** của chính mình để xuất trình cho B, vừa cần **truststore** chứa CA được phép ký certificate của B. Service B có cấu hình tương tự nhưng identity/CA authorization riêng. CSR tạo để xin certificate với **EKU clientAuth hoặc serverAuth** theo vai trò; không dùng certificate chỉ được cấp serverAuth cho mọi luồng mTLS mà không kiểm chính sách.

### 15.3. CA gửi intermediate bundle còn server chỉ import leaf

Server vẫn có private key đúng nhưng thiếu intermediate trong chain gửi cho client. Một số client có thể tìm intermediate qua cache/AIA, số khác thất bại. Cần cài **đúng intermediate chain** và xác minh từ client có trust anchor thích hợp, không ép client tắt verification.

### 15.4. Nhập root mới sửa lỗi nhưng lại tạo rủi ro trust

Một người nhận `ca.crt` qua một kênh chưa kiểm chứng, thêm vào truststore với `-noprompt` rồi thấy certificate path valid. Điều này có thể là **tin CA của attacker**. Cần xác minh fingerprint/nguồn qua kênh độc lập và giới hạn trust anchors theo chính sách.

### 15.5. Trùng Subject DN nhưng leaf ký bởi CA khác

`CN=Training Demo Root` hoặc `Issuer DN` trông giống không đủ. Hai CA có thể dùng cùng tên DN nhưng public keys khác nhau. Bên xác minh phải kiểm **chữ ký và chain đến đúng trust anchor**, không chỉ so string tên trong certificate.

### 15.6. Hệ thống dùng HSM/PKCS11 thay vì file PKCS12

Thay vì `app.p12` chứa private key, khóa riêng nằm trong token/HSM provider và có thể không export được. CSR vẫn được ký bằng private key trong token; certificate reply phải được liên kết với **key object/alias đúng** theo cơ chế provider. Các lệnh `keytool`, cách login/token PIN và import chain có thể khác, nhưng nguyên tắc **CSR cùng public key với private key, đúng trust chain và đúng identity** vẫn giữ nguyên.

## 16. Câu hỏi tự kiểm tra (có đáp án)

**Câu 1.** `keytool -certreq` có gửi private key ra file CSR không?

**Đáp án:** Không. CSR chứa public key, subject, attributes/extension requests và chữ ký được tạo bằng private key; private key vẫn được bảo vệ trong KeyStore/HSM.

**Câu 2.** CSR đã có chữ ký hợp lệ, vậy có thể dùng ngay làm certificate TLS server không?

**Đáp án:** Không. Chữ ký CSR chứng minh khả năng ký bằng key của applicant nhưng **không phải chữ ký CA** và không xác nhận quyền với hostname. Cần CA-issued X.509 leaf + chain và xác minh trust/hostname phù hợp.

**Câu 3.** Vì sao CA có quyền từ chối hoặc sửa SAN được xin trong CSR?

**Đáp án:** SAN chỉ là **yêu cầu**. CA phải thẩm định quyền đối với định danh và tuân thủ issuance policy; nếu không sẽ cho phép xin certificate cho domain không sở hữu.

**Câu 4.** Khi CA trả `app-issued.crt` cho CSR tạo bởi alias `app-server`, nên import reply vào alias nào?

**Đáp án:** **`app-server`**, tức alias PrivateKeyEntry gốc. Import vào alias mới có thể tạo certificate-only entry chứ không kết nối certificate được cấp với private key.

**Câu 5.** Chain demo có hai phần tử. Chúng là gì và thứ tự nào?

**Đáp án:** `chain[0]` là leaf `app.example.test`; `chain[1]` là root `demo-ca` ký trực tiếp leaf. Với intermediate, chain có thể thêm phần tử giữa leaf và root.

**Câu 6.** Root CA demo là self-signed. Điều gì khiến Java PKIX example chấp nhận nó?

**Đáp án:** Chương trình **chủ động chọn root làm TrustAnchor** trong `PKIXParameters`. Self-signature hay tên root không đủ khiến nó được hệ điều hành/trình duyệt khác tin cậy.

**Câu 7.** `-importcert` báo `Public keys in reply and keystore don't match`. Nên bỏ kiểm và import ép không?

**Đáp án:** Không. Phải kiểm reply có thuộc CSR đúng không, private key có bị tái sinh/đổi alias không. Dùng lại private key đúng hoặc tạo CSR mới từ key pair đang giữ rồi yêu cầu CA cấp lại.

**Câu 8.** Khi server gửi leaf và intermediate, vì sao client vẫn có thể báo “untrusted certificate”?

**Đáp án:** Client chưa có/không cho phép trust anchor phù hợp, hoặc certificate path/policy không đạt. Các certificate server gửi **không tự trao quyền tin cậy** cho client.

**Câu 9.** `checkValidity()` và `Issuer DN khớp` có đủ bảo đảm chứng thư an toàn cho HTTPS?

**Đáp án:** Không. Cần chữ ký/path PKIX, trust anchor, key usage/EKU, SAN hostname matching, revocation policy và các yêu cầu TLS khác. Subject/issuer DN không thay kiểm chữ ký.

**Câu 10.** Một CA trả file `.p7b` và một file `.p12`. Có thể coi cả hai chỉ là leaf cert mà import bừa không?

**Đáp án:** Không. PKCS#7 thường đóng gói tập certificate/chain, không mang private key; PKCS12 có thể chứa private key và entry khác. Phải kiểm contents/type, giữ private key gốc và dùng quy trình import đúng.

**Câu 11.** Code Java demo in `PKIX path valid = true`, liệu điều đó đã kiểm server hostname và revocation chưa?

**Đáp án:** Chưa. Demo kiểm SAN mẫu riêng và tắt revocation để dễ chạy; việc hostname verification thực sự do HTTPS/TLS verifier đảm nhiệm theo chính sách. Production phải cấu hình revocation/hostname phù hợp.

**Câu 12.** Tại sao không đặt root certificate được tải qua mạng chưa xác minh vào `TrustManagerFactory` chỉ để hết lỗi TLS?

**Đáp án:** Vì đó có thể là root của attacker. Trust anchor phải được chọn qua kênh/chuỗi phân phối đáng tin, có xác minh fingerprint và kiểm soát thay đổi; “hết lỗi” không chứng minh đối tác là đúng.

## 17. Checklist trước khi cài certificate reply

- [ ] CSR sinh từ **đúng private key alias**, public key/subject/extension request được xem lại.
- [ ] Private key **không** gửi cho CA; file `.p12` và password được bảo vệ, không commit vào source.
- [ ] CA thật đã thẩm định domain/identity; SAN, KU/EKU, validity, signature/profile được kiểm trong **leaf đã phát hành**.
- [ ] Đã lấy đầy đủ intermediate chain và kiểm đúng issuer/chữ ký/basicConstraints/keyCertSign.
- [ ] Root trust anchor được phân phối từ **nguồn đã xác thực**, không import CA lạ bằng `-noprompt`.
- [ ] Reply cài vào **PrivateKeyEntry alias gốc**; không nhầm với TrustedCertificateEntry alias mới.
- [ ] `keytool -list -v` xác nhận alias, leaf/chain order/length, issuer/SAN và loại entry.
- [ ] Nếu dùng Java, `KeyStore.getEntry` trả private key + chain; kiểm public/private key và path theo chính sách.
- [ ] Truststore của **bên xác minh** chứa CA được phép tin, không suy ra từ certificate server gửi.
- [ ] HTTPS/mTLS vẫn kiểm hostname/identity, expiry, KU/EKU, revocation và policy; không dùng trust-all manager.
- [ ] Quy trình có backup/rollback, lịch certificate renewal, rotation và reload; không làm mất key đang được sử dụng.
- [ ] Không dùng password demo, CA demo hoặc `setRevocationEnabled(false)` như mẫu production mặc định.
- [ ] Dùng thư mục thử nghiệm riêng, tránh chạy lại lệnh `-genkeypair`/`-importcert` trên keystore thật không kiểm soát.

## 18. Tổng kết

**CSR PKCS#10** là **yêu cầu có chữ ký từ private key của applicant**, chứa public key, identity và extensions được đề nghị; **không chứa private key và không phải chứng thư CA đã cấp**. Sau thẩm định, **CA** ký X.509 leaf (và cung cấp intermediate chain khi cần). Trong `keytool`, phải đưa certificate reply vào **chính alias PrivateKeyEntry từng tạo CSR**, để giữ private key và thay chain self-signed bằng chain đã cấp. Root trust anchor được xác minh từ nguồn đáng tin, không mặc nhiên được trust vì là self-signed hoặc vì vừa được server gửi. Java 17+ có thể kiểm chain, public/private key và PKIX path; song **PKIX demo không thay HTTPS hostname verification và revocation policy**. Đó là ranh giới giữa quy trình cài certificate thành công và việc kết nối được xác thực thực sự.

**Tài liệu nền tảng:** PKCS#10 CSR: [RFC 2986](https://www.rfc-editor.org/rfc/rfc2986); X.509 PKIX certificate/path validation: [RFC 5280](https://www.rfc-editor.org/rfc/rfc5280); `keytool` JDK: [Oracle keytool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/keytool.html).
