# Certificate là gì

**Certificate (chứng thư số)** là một cấu trúc dữ liệu điện tử được một bên phát hành ký số để liên kết một danh tính hoặc một chủ thể với một public key cụ thể, cùng các thuộc tính và giới hạn sử dụng của khóa đó. Trong hạ tầng khóa công khai (PKI), certificate giúp bên nhận kiểm tra rằng public key đang sử dụng được một tổ chức phát hành đáng tin cậy xác nhận cho đúng chủ thể và đúng mục đích.

Certificate thường được dùng trong HTTPS/TLS, ký số phần mềm và tài liệu, xác thực thiết bị, email bảo mật, VPN và các hệ thống danh tính máy. Certificate **không phải là private key** và thông thường không chứa private key. Nó chứa public key, thông tin nhận diện, thời hạn hiệu lực, thông tin về bên phát hành và chữ ký số của bên phát hành. Người sở hữu certificate phải chứng minh mình kiểm soát private key tương ứng khi thực hiện thao tác cần khóa riêng.

Bài học này thuộc phạm vi **SECURITY_KEY_MANAGEMENT_FUNDAMENTALS**, kết nối certificate và public key với vòng đời khóa mật mã: tạo, cấp phát, lưu trữ, sử dụng, xoay vòng, thu hồi và hủy. Hiểu certificate cần nắm mật mã bất đối xứng, chữ ký số, CA/PKI, KMS/HSM, kiểm soát truy cập và kiểm toán.

## 1. Certificate giải quyết vấn đề gì?

Trong mật mã bất đối xứng, một cặp khóa gồm:

- **Public key:** có thể phân phối cho bên khác. Tùy thuật toán, nó được dùng để xác minh chữ ký hoặc tham gia thiết lập/bảo vệ bí mật.
- **Private key:** phải được giữ bí mật bởi chủ thể. Nó được dùng để ký, giải mã trong một số hệ thống cũ hoặc thực hiện thao tác mật mã tương ứng với thuật toán.

Nếu một máy chủ gửi public key cho trình duyệt, trình duyệt có thể dùng khóa đó theo giao thức. Nhưng chỉ nhìn thấy public key thì trình duyệt chưa biết khóa thuộc về máy chủ nào. Kẻ tấn công có thể tự tạo một cặp khóa và gửi public key của mình, rồi tự nhận là máy chủ hợp lệ.

Certificate giải quyết bài toán liên kết danh tính với public key. Một CA (Certificate Authority) xác minh yêu cầu theo chính sách của mình rồi ký certificate. Bên kiểm tra có thể xác minh chữ ký của CA và xây dựng chuỗi tin cậy đến một trust anchor đã được cấu hình tin cậy.

Ví dụ, một certificate TLS có thể liên kết tên DNS www.example.com với một public key. Khi kết nối HTTPS, trình duyệt kiểm tra certificate và chuỗi tin cậy, xác minh tên máy chủ, thời hạn và các điều kiện khác. Sau đó, giao thức TLS còn yêu cầu máy chủ chứng minh quyền kiểm soát private key tương ứng trong quá trình handshake.

Certificate vì vậy giúp trả lời câu hỏi: **Public key này được ràng buộc với danh tính nào, do ai xác nhận, trong thời gian nào và được phép dùng cho mục đích gì?**

## 2. Certificate không phải là key pair

Các khái niệm sau thường bị nhầm lẫn:

| Thành phần | Chứa gì? | Vai trò |
|---|---|---|
| Key pair | Public key và private key tương ứng | Thực hiện các phép toán mật mã bất đối xứng. |
| Public key | Phần công khai của cặp khóa | Xác minh chữ ký hoặc tham gia giao thức mật mã. |
| Private key | Phần bí mật của cặp khóa | Ký hoặc thực hiện thao tác riêng tư theo thuật toán. |
| CSR (Certificate Signing Request) | Public key, thông tin chủ thể đề nghị và chữ ký chứng minh quyền sở hữu private key | Gửi yêu cầu cấp certificate đến CA. |
| Certificate | Public key, subject, issuer, thời hạn, extensions và chữ ký của issuer | Liên kết public key với danh tính và chính sách sử dụng. |
| CA certificate | Certificate của một CA, thường có Basic Constraints cho phép làm CA | Cho phép xác minh chữ ký của CA và xây dựng chuỗi tin cậy. |

Certificate không cần giữ private key bên trong. Nếu private key bị đính kèm vào certificate rồi phân phối cho nhiều bên, bí mật của khóa sẽ bị phá vỡ. Trong quy trình chuẩn, private key được tạo và giữ ở phía chủ thể, còn CSR chỉ gửi public key cùng thông tin yêu cầu.

Một certificate có thể được công khai trên máy chủ, trong directory hoặc gửi qua mạng. Việc certificate công khai không có nghĩa private key tương ứng được phép công khai.

## 3. Ai phát hành certificate?

**Certificate Authority (CA)** là thực thể có trách nhiệm phát hành và ký certificate theo chính sách xác minh và quản trị của mình. CA có một cặp khóa ký riêng; private key ký của CA phải được bảo vệ nghiêm ngặt, thường bằng HSM đối với CA quan trọng.

Các vai trò phổ biến trong PKI:

- **Root CA:** CA gốc của một hệ thống tin cậy. Certificate gốc thường được phân phối hoặc cài đặt trước như trust anchor trong hệ điều hành, trình duyệt, thiết bị hoặc tổ chức.
- **Intermediate CA:** CA trung gian được root CA hoặc CA cấp cao hơn ký. Nó phát hành certificate cho CA thấp hơn hoặc cho end entity theo phạm vi được phép.
- **Issuing CA:** CA trực tiếp phát hành certificate cho máy chủ, người dùng, thiết bị hoặc ứng dụng.
- **Registration Authority (RA):** thành phần hỗ trợ tiếp nhận, xác minh danh tính và phê duyệt yêu cầu; RA có thể không trực tiếp ký certificate.
- **Certificate holder/subject:** chủ thể được nêu trong certificate, ví dụ tên miền, người dùng, máy chủ hoặc thiết bị.
- **Relying party:** bên nhận certificate và quyết định có tin cậy danh tính/public key dựa trên chính sách kiểm tra.

Trong một hệ thống phân cấp, root CA thường được giữ offline hoặc hạn chế sử dụng. Intermediate/issuing CA đảm nhiệm phần lớn hoạt động phát hành thường ngày để giảm nguy cơ private key của root bị truy cập.

~~~mermaid
flowchart TD
    R["Root CA - Trust Anchor"] --> I["Intermediate CA"]
    I --> C["Issuing CA"]
    C --> E1["Certificate máy chủ"]
    C --> E2["Certificate người dùng"]
    C --> E3["Certificate thiết bị"]
    E1 --> V["Relying Party xác minh chuỗi"]
    E2 --> V
    E3 --> V
~~~

Một root certificate có thể tự ký (self-signed), nhưng chữ ký tự thân không tự động làm cho nó đáng tin cậy. Nó được tin vì relying party đã cài đặt hoặc chấp nhận nó làm trust anchor thông qua một kênh quản trị đáng tin cậy.

## 4. Cấu trúc cơ bản của X.509 certificate

X.509 là định dạng certificate phổ biến trong PKI Internet và nhiều hệ thống doanh nghiệp. Certificate X.509 v3 thường có phần dữ liệu được ký (TBSCertificate), thuật toán chữ ký và chữ ký số của issuer.

Các trường quan trọng:

| Trường | Ý nghĩa |
|---|---|
| Version | Phiên bản cấu trúc X.509; v3 hỗ trợ extensions. |
| Serial Number | Số định danh certificate do issuer cấp; thường phải duy nhất trong phạm vi CA. |
| Signature Algorithm | Thuật toán issuer dùng để ký certificate, ví dụ một tổ hợp hash và chữ ký. |
| Issuer | Danh tính CA phát hành certificate. |
| Validity | Thời điểm bắt đầu và kết thúc hiệu lực (Not Before, Not After). |
| Subject | Danh tính chủ thể được certificate mô tả. |
| Subject Public Key Info (SPKI) | Thuật toán và public key của subject. |
| Extensions | Các thuộc tính và ràng buộc như SAN, Key Usage, EKU, Basic Constraints, policies và thông tin revocation. |
| Signature Value | Chữ ký của issuer trên phần TBSCertificate. |

Điểm cốt lõi là issuer ký dữ liệu certificate, bao gồm public key và các thuộc tính liên quan. Nếu ai đó thay public key, subject hoặc thời hạn mà không có private key ký của issuer, chữ ký certificate sẽ không còn hợp lệ.

### Ví dụ cấu trúc khái quát

~~~text
Certificate
  tbsCertificate
    version
    serialNumber
    signature
    issuer
    validity
      notBefore
      notAfter
    subject
    subjectPublicKeyInfo
    extensions
  signatureAlgorithm
  signatureValue
~~~

Đây là mô tả logic, không phải một file certificate hoàn chỉnh. Trong DER, các trường được mã hóa theo ASN.1 Distinguished Encoding Rules; PEM thường là DER được Base64 và đặt trong các dòng đánh dấu.

## 5. Subject, Issuer và Subject Alternative Name

**Subject** mô tả chủ thể mà certificate được cấp cho. Với certificate người dùng hoặc CA nội bộ, subject có thể chứa Common Name (CN), Organization (O), Organizational Unit (OU), Country (C) và các thành phần Distinguished Name khác.

**Issuer** mô tả CA đã phát hành certificate. Issuer của certificate end entity thường là subject của CA trung gian ký nó. Issuer của certificate CA trung gian thường là subject của CA cấp trên.

Với certificate TLS cho tên miền, **Subject Alternative Name (SAN)** là extension quan trọng chứa danh sách định danh được bảo vệ, ví dụ DNS name, địa chỉ IP hoặc URI tùy loại certificate. Trình duyệt hiện đại xác minh tên máy chủ dựa trên SAN; không nên dựa vào CN như cách triển khai cũ.

Ví dụ SAN:

~~~text
X509v3 Subject Alternative Name:
    DNS:api.example.com
    DNS:portal.example.com
    IP Address:192.0.2.10
~~~

Certificate có SAN cho api.example.com không tự động hợp lệ cho admin.example.com. Bên xác minh phải so sánh hostname được yêu cầu với SAN theo quy tắc matching của giao thức và loại tên. Wildcard cũng có quy tắc giới hạn; không nên tự triển khai phép so sánh tên bằng chuỗi tùy ý.

## 6. Public key được biểu diễn trong certificate như thế nào?

Trường Subject Public Key Info chứa thuật toán public key và dữ liệu khóa công khai. Những thuật toán thường gặp gồm:

- **RSA:** public key chứa modulus và public exponent. Độ dài khóa và padding phải phù hợp chính sách; chữ ký RSA hiện đại thường dùng RSA-PSS hoặc các profile được phê duyệt.
- **Elliptic Curve Cryptography (ECC):** public key là một điểm trên đường cong được chỉ định, ví dụ P-256 hoặc P-384. ECDSA là một thuật toán chữ ký thường dùng với ECC.
- **EdDSA:** các thuật toán như Ed25519 có cách biểu diễn và sử dụng chữ ký riêng, cần được hỗ trợ bởi hệ thống và profile certificate.

Certificate mô tả public key, còn private key tương ứng được lưu ở phía subject. Để chứng minh đang kiểm soát private key, chủ thể phải thực hiện một thao tác yêu cầu chữ ký hoặc phép toán riêng tư phù hợp. Chỉ gửi certificate không chứng minh người gửi đang sở hữu private key.

Thuật toán public key trong SPKI và thuật toán issuer dùng để ký certificate là hai thuộc tính khác nhau. Ví dụ, certificate có thể chứa public key ECDSA của máy chủ nhưng được một CA ký certificate bằng RSA. Không được nhầm thuật toán của subject key với thuật toán ký certificate.

## 7. Chữ ký của CA bảo vệ certificate ra sao?

Khi phát hành certificate, CA tạo phần TBSCertificate với subject, public key, thời hạn và extensions đã được phê duyệt. CA sau đó dùng private key ký của mình để tạo chữ ký trên phần dữ liệu này.

Khi kiểm tra certificate, relying party dùng public key của issuer để xác minh chữ ký. Nếu dữ liệu bị sửa, chữ ký không khớp. Tuy nhiên, chữ ký hợp lệ chỉ chứng minh certificate được ký bởi private key tương ứng với issuer public key; nó chưa chứng minh issuer đó được relying party tin cậy hoặc certificate còn phù hợp với mục đích sử dụng.

Quy trình xác minh cần nhiều bước:

1. Kiểm tra chữ ký certificate bằng public key của issuer.
2. Xây dựng đường dẫn từ certificate cần kiểm tra qua các intermediate CA.
3. Kết thúc tại một trust anchor được relying party chấp nhận.
4. Kiểm tra thời hạn hiệu lực của các certificate theo chính sách.
5. Kiểm tra Basic Constraints, Key Usage, EKU, name constraints và certificate policies nếu áp dụng.
6. Kiểm tra danh tính được yêu cầu, ví dụ hostname hoặc định danh người dùng.
7. Áp dụng chính sách revocation/status phù hợp.
8. Xác nhận certificate phù hợp với mục đích và thuật toán được phép.

~~~mermaid
flowchart TD
    A["Certificate end entity"] --> B["Xác minh chữ ký bằng Intermediate public key"]
    B --> C["Intermediate certificate"]
    C --> D["Xác minh bằng Root public key"]
    D --> E["Root là trust anchor đã cấu hình"]
    E --> F["Kiểm tra thời hạn, mục đích, tên và trạng thái"]
    F --> G["Chấp nhận hoặc từ chối"]
~~~

Một chữ ký hợp lệ không đồng nghĩa certificate luôn được chấp nhận. Ví dụ certificate có thể hết hạn, sai hostname, bị thu hồi hoặc không có EKU phù hợp.

## 8. Certificate chain và trust anchor

**Certificate chain (chuỗi chứng thư)** là đường dẫn xác minh gồm certificate của subject và một hoặc nhiều certificate CA cấp trên. Chuỗi thường được mô tả theo hướng từ end entity lên intermediate rồi đến root.

Ví dụ:

~~~text
api.example.com certificate
        |
        v
Example Issuing CA certificate
        |
        v
Example Intermediate CA certificate
        |
        v
Example Root CA (trust anchor)
~~~

Máy chủ thường gửi certificate end entity và các intermediate cần thiết. Root certificate thường đã có sẵn trong trust store của client và không cần gửi như một phần bắt buộc của chain. Gửi thiếu intermediate có thể làm một số client không xây dựng được đường dẫn, dù root đã được tin cậy.

Một CA certificate trung gian cần được xác minh theo chính sách: Basic Constraints phải cho phép CA, Key Usage phải phù hợp với ký certificate và các ràng buộc path length/name constraints nếu có phải được tôn trọng.

Có thể tồn tại nhiều đường dẫn hợp lệ đến các trust anchor khác nhau do cross-signing hoặc nhiều CA chain. Path building là quá trình chọn và xác minh đường dẫn; ứng dụng không nên giả định chain luôn chỉ có đúng một chuỗi cố định.

## 9. Các extension quan trọng của X.509 v3

Extensions giúp giới hạn mục đích và phạm vi sử dụng certificate. Một số extension thường gặp:

| Extension | Vai trò | Ví dụ |
|---|---|---|
| Basic Constraints | Xác định certificate có đại diện CA hay không; có thể giới hạn độ sâu CA con | CA:TRUE, pathLenConstraint |
| Key Usage | Giới hạn loại thao tác khóa được phép | digitalSignature, keyEncipherment, keyCertSign, cRLSign |
| Extended Key Usage (EKU) | Giới hạn mục đích cấp cao của certificate | serverAuth, clientAuth, codeSigning, emailProtection |
| Subject Alternative Name | Chứa các định danh thay thế của subject | DNS name, IP address, URI |
| Subject Key Identifier (SKI) | Định danh public key của subject trong certificate | key identifier |
| Authority Key Identifier (AKI) | Hỗ trợ xác định khóa của issuer tương ứng | key identifier, issuer/serial |
| CRL Distribution Points | Cho biết nơi lấy CRL | URI của CRL |
| Authority Information Access (AIA) | Có thể chứa thông tin truy cập OCSP hoặc CA Issuers | OCSP URI, issuer certificate URI |
| Certificate Policies | Tham chiếu chính sách phát hành/sử dụng | policy OID |

**Key Usage** và **EKU** không thể tùy ý thay thế cho nhau. Key Usage giới hạn loại phép toán khóa, còn EKU mô tả mục đích sử dụng certificate ở mức ứng dụng. Một certificate có digitalSignature không tự động được phép làm TLS server nếu EKU hoặc chính sách yêu cầu serverAuth mà certificate không đáp ứng.

Nếu extension được đánh dấu critical, relying party phải hiểu và xử lý extension đó; nếu không hiểu extension critical, theo quy tắc X.509, certificate phải bị từ chối. Extension non-critical có thể được bỏ qua bởi bên không sử dụng nó, tùy profile.

## 10. Certificate cho TLS/HTTPS

Trong HTTPS, certificate TLS thường xác định tên máy chủ và chứa public key của máy chủ. Khi client kết nối, TLS dùng certificate chain để xác minh danh tính máy chủ và dùng private key tương ứng để chứng minh quyền kiểm soát khóa trong handshake.

Ở mức khái quát, quy trình TLS 1.3:

1. Client và server thương lượng phiên bản TLS, cipher suite và các tham số handshake.
2. Server gửi Certificate chứa certificate end entity và các intermediate cần thiết.
3. Server gửi CertificateVerify, dùng private key tương ứng để ký transcript handshake.
4. Client xác minh chữ ký CertificateVerify bằng public key trong certificate, sau khi kiểm tra certificate chain, hostname, thời hạn và chính sách.
5. Hai bên hoàn tất handshake và thiết lập khóa phiên đối xứng.

CertificateVerify trong TLS 1.3 là chữ ký trên transcript handshake, khác với chữ ký CA trên certificate. Việc tách hai chữ ký này giúp phân biệt:

- CA xác nhận mối liên kết danh tính-public key trong certificate.
- Server chứng minh đang kiểm soát private key tương ứng trong phiên kết nối cụ thể.

Trong TLS 1.3, certificate thường dùng để xác thực và ký handshake; trao đổi khóa phiên được thực hiện bằng các cơ chế như (EC)DHE hoặc PSK theo cipher suite và cấu hình. Không nên mô tả certificate TLS hiện đại như thể nó luôn được dùng để mã hóa trực tiếp dữ liệu phiên.

## 11. Certificate cho ký số và xác thực thiết bị

Certificate không chỉ dùng cho HTTPS:

- **Code signing:** certificate liên kết public key ký với nhà phát hành phần mềm. Hệ điều hành hoặc công cụ kiểm tra chữ ký và chính sách tin cậy để đánh giá nguồn gốc artifact.
- **Document signing:** certificate hỗ trợ xác minh danh tính người ký và public key dùng để kiểm tra chữ ký tài liệu.
- **Client authentication:** certificate có thể xác thực người dùng, workload hoặc thiết bị trong mutual TLS.
- **Email protection:** certificate có thể hỗ trợ S/MIME để ký hoặc mã hóa email theo profile.
- **Device identity:** certificate cấp cho thiết bị IoT, gateway hoặc máy công nghiệp để xác thực thiết bị trong mạng.
- **VPN và Wi-Fi doanh nghiệp:** certificate có thể dùng cho xác thực máy hoặc người dùng theo chính sách.

Mỗi mục đích cần profile phù hợp về Subject/SAN, Key Usage, EKU, thời hạn, thuật toán và quy trình cấp phát. Không nên dùng một certificate duy nhất cho mọi mục đích chỉ để giảm số lượng certificate, vì phạm vi compromise và quyền sử dụng sẽ khó kiểm soát.

## 12. CSR và quy trình cấp certificate

Certificate thường được cấp qua quy trình có yêu cầu và xác minh:

1. **Tạo key pair:** subject tạo private/public key bằng thư viện mật mã, KMS hoặc HSM. Với khóa quan trọng, private key nên được tạo và giữ trong vùng bảo vệ phù hợp.
2. **Tạo CSR:** subject tạo Certificate Signing Request chứa public key và thông tin chủ thể đề nghị. CSR được ký bằng private key tương ứng để chứng minh quyền kiểm soát khóa tại thời điểm yêu cầu.
3. **Gửi yêu cầu:** CSR được gửi đến RA hoặc CA qua kênh được kiểm soát.
4. **Xác minh danh tính/quyền:** CA kiểm tra quyền kiểm soát domain, danh tính tổ chức, người dùng hoặc thiết bị theo chính sách.
5. **Phê duyệt profile:** xác định SAN, Key Usage, EKU, thời hạn, thuật toán và các extension cần thiết.
6. **Phát hành:** CA tạo TBSCertificate và ký bằng private key của CA.
7. **Phân phối và cài đặt:** subject cài certificate cùng chain cần thiết; private key vẫn nằm trong vùng quản lý của subject.
8. **Kiểm tra vận hành:** xác minh chain, hostname/identity, thời hạn, mục đích và khả năng sử dụng private key.

CSR không phải certificate. Chữ ký CSR chứng minh bên tạo yêu cầu có quyền sử dụng private key tương ứng với public key được đề xuất, nhưng CA vẫn phải tự xác minh danh tính và quyền được cấp certificate.

## 13. Self-signed certificate và certificate do CA ký

**Self-signed certificate** là certificate có chữ ký được tạo bởi private key tương ứng với public key trong chính certificate đó. Nó có thể hữu ích trong lab, hệ thống nội bộ nhỏ hoặc làm trust anchor khi được phân phối và cài đặt qua kênh tin cậy.

Certificate do CA ký được xác minh thông qua public key của CA và đường dẫn tin cậy. Trong môi trường Internet công cộng, trình duyệt thường dựa trên các root CA có trong trust store của nền tảng.

| Tiêu chí | Self-signed | CA-signed |
|---|---|---|
| Ai ký | Chủ thể hoặc tổ chức tạo certificate tự ký | CA phát hành theo chính sách |
| Tin cậy | Phải phân phối trust anchor an toàn hoặc cấu hình tin cậy riêng | Có thể xây dựng chain đến trust anchor đã có |
| Xác minh danh tính | Do tổ chức tự thực hiện và quản lý | Dựa trên quy trình xác minh của CA và chính sách relying party |
| Phù hợp | Lab, môi trường nội bộ được quản lý, trust anchor riêng | Website công khai, hệ thống doanh nghiệp và PKI có quản trị |
| Rủi ro | Cài nhầm hoặc phân phối trust anchor không an toàn | Phụ thuộc vào bảo mật CA, quy trình cấp phát và trust store |

Không nên cảnh báo rằng mọi self-signed certificate đều không an toàn. Vấn đề là relying party có thiết lập trust anchor đúng cách và kiểm soát phân phối nó hay không. Ngược lại, certificate do CA công khai ký cũng không được tự động chấp nhận nếu sai hostname, hết hạn, bị thu hồi hoặc sai mục đích.

## 14. Thời hạn hiệu lực và gia hạn

Certificate có Not Before và Not After xác định khoảng thời gian hiệu lực. Khi kiểm tra, hệ thống cần dùng thời gian đáng tin cậy và tính đến sai lệch đồng hồ theo chính sách.

Certificate hết hạn không có nghĩa private key tự động bị xóa. Private key có thể vẫn tồn tại trong HSM/KMS hoặc backup, nhưng certificate đó không còn hợp lệ cho mục đích yêu cầu theo thời gian hiệu lực. Ngược lại, certificate còn hạn cũng không có nghĩa private key chưa bị compromise hoặc certificate chưa bị thu hồi.

Gia hạn có thể:

- Cấp certificate mới cho cùng public key nếu chính sách cho phép và khóa vẫn an toàn.
- Tạo key pair mới rồi cấp certificate mới để giảm phụ thuộc vào khóa cũ hoặc đáp ứng cryptoperiod.
- Thay đổi SAN, EKU, profile hoặc thời hạn theo nhu cầu mới.

Với khóa dài hạn, tạo key pair mới khi gia hạn thường giúp quản lý vòng đời và giảm rủi ro từ việc dùng một private key quá lâu. Tuy nhiên, quyết định phải xét hệ thống phụ thuộc, pinning, khả năng phân phối certificate mới và thời gian chuyển đổi.

## 15. Thu hồi certificate: CRL và OCSP

Certificate có thể cần bị thu hồi trước Not After, ví dụ khi private key bị lộ, thông tin subject sai, thiết bị mất hoặc quan hệ tin cậy không còn hợp lệ.

Hai cơ chế phổ biến:

- **Certificate Revocation List (CRL):** CA công bố danh sách serial number của certificate đã thu hồi. Relying party tải CRL và kiểm tra certificate serial có nằm trong danh sách hay không. CRL có thời gian phát hành và hết hạn; client cần cập nhật theo chính sách.
- **Online Certificate Status Protocol (OCSP):** client hoặc thành phần trung gian hỏi trạng thái của một certificate cụ thể từ OCSP responder. Phản hồi thường cho biết good, revoked hoặc unknown, có chữ ký và thời hạn hiệu lực.

CRL và OCSP có khác biệt về hiệu năng, khả năng sẵn sàng, quyền riêng tư và cách client xử lý khi dịch vụ trạng thái không truy cập được. Một số hệ thống dùng OCSP stapling để server gửi kèm phản hồi OCSP còn hiệu lực trong TLS handshake.

Trạng thái **good** của OCSP không phải lời bảo đảm rằng certificate hoàn toàn an toàn trong mọi khía cạnh; nó chỉ là trạng thái được responder báo cáo theo phạm vi và thời điểm. Tương tự, không truy cập được OCSP/CRL không đồng nghĩa certificate đã bị thu hồi. Client cần áp dụng chính sách fail-open/fail-closed phù hợp với rủi ro và giao thức.

## 16. Certificate revocation khác key destruction

Thu hồi certificate làm cho relying party biết certificate không còn được chấp nhận theo cơ chế trạng thái. Hành động này không tự động xóa private key khỏi HSM, KMS, backup hoặc thiết bị.

Nếu private key bị compromise, quy trình xử lý thường gồm:

1. Cô lập việc sử dụng khóa và đánh giá phạm vi ảnh hưởng.
2. Yêu cầu CA thu hồi certificate liên quan.
3. Tạo key pair mới trong vùng bảo vệ phù hợp.
4. Gửi CSR mới và xác minh lại danh tính/quyền.
5. Cài certificate mới, cập nhật trust/configuration và kiểm tra hệ thống phụ thuộc.
6. Xử lý private key cũ, backup, wrapped copies và bản sao theo quy trình key destruction.
7. Lưu audit, bằng chứng thu hồi và bằng chứng xử lý vật liệu khóa.

Nếu chỉ revoke certificate mà private key cũ vẫn được lưu trong một backup có thể restore, người vận hành có thể vô tình đưa lại khóa đã compromise vào hoạt động. Vì vậy, quản lý trạng thái certificate phải liên kết với inventory và vòng đời private key.

## 17. Bảo vệ private key tương ứng với certificate

Certificate thường được phân phối công khai; private key tương ứng phải được bảo vệ. Mức bảo vệ phụ thuộc vào giá trị của danh tính và phạm vi sử dụng:

- Tạo khóa bằng nguồn ngẫu nhiên an toàn và thuật toán/độ dài được phê duyệt.
- Với CA, code signing, khóa ký giao dịch hoặc danh tính quan trọng, cân nhắc tạo và giữ private key trong HSM.
- Với workload, dùng KMS/HSM hoặc secret/key store được quản lý; hạn chế export private key.
- Cấp quyền theo least privilege; tách quyền sử dụng khóa khỏi quyền quản trị khóa.
- Dùng MFA, dual control hoặc quorum cho thao tác quản trị và khôi phục nhạy cảm.
- Không ghi private key, passphrase hoặc nội dung PKCS#12 vào log, ticket, source code hay image.
- Sao lưu theo chính sách nếu cần khôi phục cùng danh tính; bảo vệ backup bằng miền lỗi và khóa độc lập.
- Kiểm kê certificate, key ID, fingerprint, owner, version, vị trí lưu và ngày hết hạn.

Certificate và private key có thể được lưu trong cùng một container như PKCS#12/PFX, nhưng container đó có thể chứa cả bí mật. Khi phân phối hoặc backup, phải xử lý nó như tài sản chứa private key, không như certificate công khai đơn thuần.

## 18. Định dạng PEM, DER và PKCS#12

Certificate X.509 có thể được lưu dưới các định dạng khác nhau:

| Định dạng | Mô tả | Dấu hiệu thường gặp |
|---|---|---|
| DER | Mã hóa nhị phân ASN.1 DER | File nhị phân, thường có đuôi .der hoặc .cer |
| PEM | Base64 của DER, có dòng BEGIN/END | BEGIN CERTIFICATE |
| PKCS#7/P7B | Container có thể chứa certificate/chain, thường không chứa private key | BEGIN PKCS7 hoặc BEGIN CMS |
| PKCS#12/PFX | Container có thể chứa certificate, chain và private key, thường được bảo vệ bằng mật khẩu | File .p12 hoặc .pfx |

Đuôi file không phải bằng chứng chắc chắn về nội dung. Một file .cer có thể là DER hoặc PEM; một file .pem cũng có thể chứa certificate, private key hoặc nhiều đối tượng. Phải kiểm tra loại dữ liệu và quyền truy cập trước khi xử lý.

PEM certificate thường có dạng:

~~~text
-----BEGIN CERTIFICATE-----
... Base64-encoded DER ...
-----END CERTIFICATE-----
~~~

Certificate PEM có thể được phân phối công khai. Nếu file chứa PRIVATE KEY hoặc ENCRYPTED PRIVATE KEY, đó là vật liệu bí mật và phải được bảo vệ tương ứng.

## 19. Kiểm tra certificate bằng OpenSSL

OpenSSL có thể giúp đọc thông tin certificate và kiểm tra chain trong môi trường kiểm thử hoặc vận hành. Các lệnh sau chỉ minh họa thao tác kiểm tra:

~~~bash
# Đọc thông tin certificate PEM
openssl x509 -in server.crt -noout -text

# Đọc certificate DER
openssl x509 -inform DER -in server.cer -noout -text

# Tính fingerprint SHA-256
openssl x509 -in server.crt -noout -fingerprint -sha256

# Xác minh certificate với CA bundle
openssl verify -CAfile trusted-roots.pem -untrusted intermediates.pem server.crt

# Kiểm tra certificate mà endpoint TLS trả về
openssl s_client -connect api.example.com:443 -servername api.example.com -showcerts
~~~

Lệnh verify chỉ đáng tin khi CA bundle là trust store mà tổ chức chủ đích sử dụng, intermediate phù hợp và các điều kiện xác minh cần thiết được bật. Kết quả kiểm tra trên một máy không đại diện cho mọi client vì trust store, thời gian hệ thống, chính sách revocation và thuật toán được chấp nhận có thể khác nhau.

Không dùng các lệnh hiển thị private key trong log hoặc phiên terminal được ghi lại. Khi kiểm tra container có private key, tránh đưa mật khẩu hoặc nội dung khóa vào command history.

## 20. Certificate pinning và trust store

**Trust store** là tập hợp trust anchor hoặc certificate được một nền tảng/ứng dụng chấp nhận. Hệ điều hành, trình duyệt, runtime Java và ứng dụng riêng có thể có trust store khác nhau.

**Certificate pinning** hoặc public key pinning là kỹ thuật ứng dụng giới hạn certificate hoặc public key được chấp nhận cho một dịch vụ. Pinning có thể giảm một số rủi ro khi CA bị lạm dụng, nhưng làm tăng độ phức tạp khi xoay vòng certificate/key. Nếu không có kế hoạch cập nhật pin, ứng dụng có thể từ chối certificate hợp lệ mới và gây gián đoạn.

Khi triển khai pinning, cần:

- Xác định pin là certificate fingerprint hay SPKI/public key fingerprint.
- Có ít nhất một phương án pin dự phòng nếu mô hình cho phép.
- Lên kế hoạch cập nhật trước khi certificate hoặc key hết hạn/đổi.
- Phân phối pin qua kênh tin cậy và có cơ chế rollback.
- Kiểm thử trên các phiên bản ứng dụng đang được hỗ trợ.

Pinning không thay thế xác minh hostname, chain, validity và các kiểm tra certificate khác trừ khi một thiết kế đặc biệt được phê duyệt rõ ràng. Pinning cũng không phải cách an toàn để bỏ qua mọi quy tắc PKI.

## 21. Certificate lifecycle và quản lý vòng đời khóa

Certificate có vòng đời riêng nhưng liên kết chặt với vòng đời public/private key:

~~~mermaid
flowchart TD
    A["Xác định nhu cầu và profile"] --> B["Tạo key pair"]
    B --> C["Tạo và ký CSR"]
    C --> D["CA xác minh danh tính và phê duyệt"]
    D --> E["Phát hành certificate"]
    E --> F["Phân phối và sử dụng"]
    F --> G{"Có thay đổi hoặc sự cố?"}
    G -- "Gia hạn/xoay vòng" --> B
    G -- "Hết hạn" --> H["Ngừng dùng certificate"]
    G -- "Compromise hoặc sai thông tin" --> I["Revoke certificate"]
    H --> J["Lưu hoặc hủy private key theo chính sách"]
    I --> K["Thay khóa, cấp certificate mới và xử lý key cũ"]
~~~

Quản lý lifecycle cần inventory tự động hoặc quy trình cập nhật đáng tin cậy để tránh certificate hết hạn bất ngờ, SAN không còn đúng, khóa không rõ owner hoặc certificate bị thu hồi nhưng vẫn được triển khai.

Một bản ghi inventory hữu ích có thể chứa:

- Certificate fingerprint và serial number.
- Subject, SAN, issuer và chain.
- Public key algorithm, key size/curve và signature algorithm.
- Key ID hoặc tham chiếu đến private key trong KMS/HSM.
- Owner, ứng dụng, môi trường và mục đích.
- Not Before, Not After và trạng thái revocation.
- Key Usage, EKU và policy.
- Nơi triển khai, nơi lưu backup và người có quyền quản lý.

Không lưu private key bytes trong inventory. Chỉ lưu key reference và metadata đủ để truy vết.

## 22. Những lỗi thường gặp khi dùng certificate

- Tin certificate chỉ vì chữ ký của nó hợp lệ mà không kiểm tra trust anchor.
- Bỏ qua hostname/SAN và chỉ kiểm tra certificate chain.
- Nhầm public key trong certificate với private key cần giữ bí mật.
- Dùng certificate sai EKU hoặc Key Usage.
- Không gửi intermediate certificate cần thiết cho client.
- Dùng certificate hết hạn hoặc không kiểm tra thời gian hệ thống.
- Cho rằng revoke certificate tự động xóa private key khỏi backup.
- Dùng một certificate cho nhiều mục đích làm mở rộng phạm vi compromise.
- Không quản lý version, fingerprint, owner và nơi triển khai.
- Dùng self-signed certificate mà không phân phối trust anchor qua kênh an toàn.
- Gia hạn certificate nhưng quên cập nhật pinning hoặc trust store riêng.
- Coi OCSP/CRL không truy cập được là trạng thái good hoặc revoked mà không theo chính sách.
- Không kiểm tra private key có khớp public key trong certificate hay không.
- Để PKCS#12/PFX chứa private key ở nơi lưu trữ có quyền truy cập rộng.

## 23. Ví dụ thực tế: cấp certificate TLS cho API

Một đội nền tảng cần cấp certificate cho api.example.com:

1. Tạo cặp khóa trên máy chủ hoặc HSM/KMS theo chính sách.
2. Giữ private key trong vùng bảo vệ; chỉ cho service identity cần thiết sử dụng.
3. Tạo CSR chứa public key và SAN api.example.com.
4. Gửi CSR đến CA sau khi xác minh quyền kiểm soát domain.
5. CA phát hành certificate với EKU serverAuth, Key Usage phù hợp và thời hạn theo profile.
6. Cài certificate cùng intermediate chain trên load balancer hoặc TLS endpoint.
7. Kiểm tra chain đến trust anchor, hostname/SAN, thời hạn và trạng thái.
8. Thực hiện TLS handshake thử và xác minh server chứng minh quyền kiểm soát private key.
9. Theo dõi ngày hết hạn và lập kế hoạch xoay vòng certificate/key.

Nếu private key bị lộ, đội vận hành phải thu hồi certificate, tạo key pair mới, cấp certificate mới và xử lý bản sao private key cũ trong backup. Chỉ thay certificate mà vẫn dùng private key cũ bị lộ sẽ không giải quyết được sự cố.

## 24. Checklist xác minh certificate

Trước khi chấp nhận một certificate, hãy kiểm tra:

- [ ] Certificate có định dạng và cấu trúc X.509 hợp lệ.
- [ ] Chữ ký của issuer được xác minh bằng public key phù hợp.
- [ ] Chain xây dựng được đến trust anchor được cấu hình tin cậy.
- [ ] Subject/SAN khớp với danh tính hoặc hostname cần xác minh.
- [ ] Not Before và Not After phù hợp với thời gian hiện tại.
- [ ] Basic Constraints, Key Usage và EKU phù hợp mục đích.
- [ ] Thuật toán, độ dài khóa hoặc đường cong được chính sách cho phép.
- [ ] Trạng thái revocation được xử lý theo chính sách CRL/OCSP.
- [ ] Không có name constraints hoặc certificate policy nào bị vi phạm.
- [ ] Private key tương ứng được giữ an toàn và có thể thực hiện thao tác cần thiết.
- [ ] Certificate được triển khai cùng intermediate chain cần thiết.
- [ ] Inventory ghi đúng serial, fingerprint, issuer, owner, key reference và ngày hết hạn.

Certificate là bằng chứng có chữ ký về mối liên kết giữa một danh tính và public key, được đánh giá trong một hệ thống tin cậy cụ thể. Chỉ khi kiểm tra cả chain, danh tính, thời hạn, mục đích, trạng thái và quyền kiểm soát private key, hệ thống mới có cơ sở chấp nhận certificate cho một hoạt động mật mã.
