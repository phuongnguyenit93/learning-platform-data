# TLS certificate: cách trình duyệt xác minh danh tính máy chủ

## 1. TLS certificate là gì?

Khi người dùng mở một website qua HTTPS, trình duyệt cần xác minh rằng đầu bên kia của kết nối thực sự đại diện cho hostname mà người dùng định truy cập. **TLS certificate** (chứng chỉ TLS) là một phần của cơ chế xác minh đó. Chứng chỉ X.509 thường chứa public key, danh tính máy chủ, thời hạn hiệu lực và chữ ký số của một Certificate Authority (CA).

Ví dụ, người dùng truy cập:

~~~text
https://shop.example.test
~~~

Máy chủ gửi chứng chỉ có Subject Alternative Name (SAN) chứa tên `shop.example.test`. Browser kiểm tra chứng chỉ, chuỗi CA và hostname trước khi chấp nhận kết nối TLS. Nếu các kiểm tra phù hợp, TLS handshake tiếp tục hoàn tất để hai bên thiết lập khóa phiên và bảo vệ dữ liệu truyền đi.

Chứng chỉ không phải là “mã hóa HTTPS” tự thân. Nó giúp xác thực danh tính và cung cấp public key hoặc thông tin cần thiết cho quá trình bắt tay. TLS handshake sử dụng các thuật toán mật mã để thiết lập khóa phiên; dữ liệu ứng dụng sau đó được bảo vệ bằng mã hóa đối xứng và cơ chế toàn vẹn phù hợp với TLS version/cipher suite.

Trong browser security, TLS certificate quan trọng vì cookie, thông tin đăng nhập, session, API request và nội dung ứng dụng đều phụ thuộc vào việc kết nối HTTPS tới đúng máy chủ. HSTS có thể buộc browser chỉ dùng HTTPS, nhưng HSTS không sửa một chứng chỉ sai hoặc hết hạn. Certificate validation và TLS configuration vẫn phải chính xác.

Bài học thuộc chương **HSTS và TLS** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Module phân tích ranh giới bảo mật giữa browser, origin, cookie và ứng dụng web, bao gồm Same-Origin Policy, CORS, XSS, CSRF, clickjacking, CSP và security headers. Bài này tập trung vào PKI, X.509, certificate chain, hostname verification, vòng đời chứng chỉ và cách browser xử lý lỗi chứng chỉ.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích chứng chỉ X.509 và vai trò của public key, danh tính, thời hạn và chữ ký CA.
2. Mô tả PKI, trust store, root CA, intermediate CA và certificate chain.
3. Giải thích browser xác minh hostname bằng SAN và vì sao CN không nên được dùng thay SAN.
4. Nhận diện lỗi hostname mismatch, hết hạn, chưa có hiệu lực, chain không tin cậy và usage không phù hợp.
5. Phân biệt server certificate với client certificate trong mutual TLS (mTLS).
6. Hiểu TLS handshake xác minh quyền sở hữu private key và thiết lập khóa phiên.
7. Nêu vai trò và giới hạn của OCSP, CRL, OCSP stapling và Certificate Transparency.
8. Thiết kế quy trình cấp, triển khai, gia hạn và xoay vòng certificate/private key.
9. Hiểu mối liên hệ giữa TLS certificate và HSTS.
10. Điều tra lỗi chứng chỉ bằng browser DevTools và công cụ dòng lệnh.

## 2. Chứng chỉ X.509 chứa những gì?

X.509 là định dạng chứng chỉ số được dùng rộng rãi trong TLS. Chứng chỉ được CA ký số để bên kiểm tra có thể xác minh rằng các trường trong chứng chỉ không bị sửa đổi và chữ ký được tạo bởi khóa của CA tương ứng.

Một chứng chỉ máy chủ thường có những thành phần quan trọng:

| Trường/extension | Vai trò |
| --- | --- |
| Subject | Danh tính chủ thể theo cấu trúc X.509; không nên chỉ dựa vào CN để xác minh hostname. |
| Subject Alternative Name (SAN) | Danh sách DNS name hoặc IP address mà chứng chỉ đại diện. |
| Subject Public Key Info | Public key và thuật toán khóa của chủ thể. |
| Issuer | CA đã ký chứng chỉ này. |
| Serial Number | Số định danh chứng chỉ trong phạm vi issuer. |
| Not Before / Not After | Khoảng thời gian chứng chỉ có hiệu lực. |
| Basic Constraints | Cho biết chứng chỉ có được phép làm CA hay không và giới hạn path length nếu có. |
| Key Usage | Giới hạn mục đích sử dụng khóa, ví dụ digitalSignature hoặc keyCertSign. |
| Extended Key Usage (EKU) | Mục đích sử dụng mở rộng, ví dụ TLS Web Server Authentication. |
| Signature Algorithm | Thuật toán CA dùng để ký chứng chỉ. |

Không phải mọi chứng chỉ đều có mọi extension hoặc mọi trường đều có cùng ý nghĩa trong từng loại chứng chỉ. Browser và TLS stack kiểm tra các extension liên quan theo profile và policy của chúng.

### 2.1. Public key và private key

Cặp khóa bất đối xứng gồm:

- **Private key:** phải được giữ bí mật bởi chủ thể hoặc hạ tầng quản lý khóa.
- **Public key:** được đưa vào certificate để bên khác sử dụng trong quá trình xác minh hoặc thiết lập bảo mật.

CA ký chứng chỉ bằng private key của CA. Browser dùng public key tương ứng trong certificate chain để xác minh chữ ký.

Máy chủ cần chứng minh đang sở hữu private key tương ứng với public key trong certificate. Trong TLS hiện đại, thông điệp CertificateVerify chứng minh quyền sở hữu khóa theo transcript của handshake. Private key không được gửi qua mạng trong TLS handshake thông thường.

### 2.2. Chứng chỉ không chứa private key máy chủ

File certificate công khai thường có thể được gửi cho mọi client. Private key là tài sản nhạy cảm và phải được lưu riêng, giới hạn quyền đọc, backup và rotation phù hợp.

Nếu private key bị lộ, kẻ tấn công có thể giả mạo máy chủ trong những điều kiện liên quan đến certificate/key đó cho tới khi key/certificate bị thay thế và các cơ chế phát hiện/thu hồi có hiệu lực. Chỉ thay file certificate mà tiếp tục dùng private key đã lộ không giải quyết được vấn đề.

## 3. PKI và mô hình tin cậy CA

**Public Key Infrastructure (PKI)** là hệ thống gồm CA, chứng chỉ, khóa, quy trình cấp/thu hồi và các chính sách xác minh. Browser không mặc định tin mọi chứng chỉ do máy chủ tự gửi. Nó cần xây dựng được một đường dẫn tin cậy từ certificate của máy chủ tới một trust anchor được tin cậy trong môi trường client.

Một chuỗi thường có:

1. **Leaf/server certificate:** chứng chỉ cho hostname mà người dùng truy cập.
2. **Intermediate CA certificate:** CA trung gian ký leaf certificate.
3. **Root CA certificate:** trust anchor được browser/OS hoặc môi trường quản lý tin cậy.

Sơ đồ khái quát:

~~~mermaid
flowchart TD
    A["Browser trust store"] --> B["Root CA"]
    B --> C["Intermediate CA"]
    C --> D["Leaf certificate: shop.example.test"]
    D --> E["Public key của máy chủ"]
    F["TLS handshake"] --> G["Browser xác minh chain và hostname"]
    E --> G
~~~

Root CA thường tự ký và được cài sẵn trong trust store; server thông thường gửi leaf certificate và các intermediate cần thiết. Server thường không cần gửi root certificate vì client đã có trust anchor hoặc tự xây dựng path phù hợp.

### 3.1. Root CA và trust store

Trust store là tập trust anchor được môi trường client chấp nhận. Tùy browser, hệ điều hành và chính sách tổ chức, trust store có thể do browser quản lý riêng, dùng chung OS hoặc được bổ sung bởi enterprise policy.

Điều này giải thích vì sao cùng một server có thể được tin trên máy này nhưng không được tin trên máy khác: trust store, thời gian hệ thống, proxy TLS inspection hoặc policy nội bộ có thể khác nhau.

Không cài một root CA lạ chỉ để làm biến mất cảnh báo trên máy cá nhân. Cài root CA đồng nghĩa cho phép CA đó có thể ký chứng chỉ được hệ thống tin cậy trong phạm vi policy của trust store. Chỉ cài CA nội bộ theo quy trình quản trị được xác minh.

### 3.2. Intermediate CA

Intermediate CA giúp root key không phải trực tiếp ký mọi chứng chỉ máy chủ. Root CA ký intermediate; intermediate ký leaf certificate. Intermediate có thể bị thu hồi hoặc thay thế mà không cần thay root trust anchor.

Server cần cấu hình gửi đúng intermediate chain. Nếu thiếu intermediate, một số client có thể tự tìm được đường dẫn khác, nhưng client khác sẽ báo lỗi chain không hoàn chỉnh. Không dựa vào cache của browser để che lỗi triển khai.

### 3.3. Path building và chain validation

Browser/TLS stack xây dựng một certificate path phù hợp từ leaf tới trust anchor. Quá trình này kiểm tra chữ ký, thời hạn, constraints, usage và policy liên quan. Có thể tồn tại nhiều đường dẫn hợp lệ tùy cross-signing, trust store và chứng chỉ có sẵn.

Vì vậy, chain mà server gửi và chain mà client cuối cùng xây dựng không phải lúc nào cũng giống hệt nhau. Khi debug, cần xem cả chain server gửi và kết quả validation trên client mục tiêu.

## 4. Hostname verification và Subject Alternative Name

Một chứng chỉ có chain tin cậy vẫn có thể không hợp lệ cho website nếu hostname không khớp.

Ví dụ người dùng truy cập:

~~~text
https://shop.example.test
~~~

Leaf certificate cần chứa DNS name phù hợp trong Subject Alternative Name (SAN). Browser xác minh hostname được yêu cầu với SAN theo quy tắc hostname verification.

### 4.1. SAN là nơi khai báo danh tính DNS/IP

SAN có thể chứa:

- DNS name như `shop.example.test`.
- IP address nếu chứng chỉ được cấp cho truy cập bằng IP.
- Các loại GeneralName khác cho những ứng dụng phù hợp.

Nếu truy cập bằng IP address, một SAN kiểu DNS chứa chuỗi biểu diễn IP không tương đương SAN kiểu iPAddress. Certificate cần đúng loại SAN cho cách client truy cập.

Các browser hiện đại yêu cầu SAN cho xác minh danh tính máy chủ; không nên dựa vào Common Name (CN) trong Subject như fallback. Khi cấp chứng chỉ mới, luôn khai báo đầy đủ DNS/IP name cần phục vụ trong SAN.

### 4.2. Wildcard certificate

Một wildcard SAN phổ biến:

~~~text
*.example.test
~~~

Wildcard này thường khớp một label ở vị trí trái, ví dụ:

~~~text
shop.example.test
api.example.test
~~~

Nó không khớp:

~~~text
example.test
deep.shop.example.test
~~~

Nếu cần apex domain example.test và các subdomain cấp một, khai báo cả `example.test` và `*.example.test`. Không giả định wildcard bao phủ mọi cấp subdomain.

Wildcard certificate giảm số lượng chứng chỉ cần quản lý nhưng tăng phạm vi ảnh hưởng nếu private key bị lộ. Một khóa wildcard có thể ảnh hưởng nhiều hostname cùng phạm vi. Với hệ thống nhạy cảm hoặc nhiều tenant, cân nhắc chứng chỉ riêng và quản lý khóa tách biệt.

### 4.3. Hostname mismatch

Lỗi có thể xảy ra khi:

- Chứng chỉ chỉ có www.example.test nhưng người dùng truy cập example.test.
- CDN trả certificate của một virtual host khác.
- Load balancer chọn sai certificate theo SNI.
- Ứng dụng truy cập bằng IP nhưng certificate chỉ có DNS SAN.
- Wildcard không khớp nhiều cấp subdomain.
- Reverse proxy hoặc staging route dùng hostname khác dự kiến.

Không khắc phục hostname mismatch bằng cách tắt kiểm tra certificate ở client. Sửa certificate, DNS, SNI hoặc URL để chúng khớp.

## 5. Thời hạn hiệu lực và thời gian hệ thống

Certificate có Not Before và Not After. Client kiểm tra thời gian hiện tại có nằm trong khoảng hiệu lực hay không.

Các lỗi thường gặp:

- Certificate đã hết hạn.
- Certificate chưa đến Not Before.
- Đồng hồ máy khách sai.
- Server triển khai nhầm certificate cũ.
- Một node trong cụm đã gia hạn nhưng node khác vẫn phục vụ certificate cũ.

### 5.1. Gia hạn trước khi hết hạn

Không chờ tới ngày cuối cùng mới gia hạn. Quy trình tự động nên:

1. Theo dõi ngày hết hạn của mọi hostname và certificate.
2. Gia hạn trước một khoảng đệm đủ để xử lý lỗi.
3. Kiểm tra SAN, issuer, chain và thời hạn của certificate mới.
4. Triển khai đồng bộ lên mọi edge, load balancer và origin server.
5. Kiểm tra handshake từ bên ngoài sau deploy.
6. Cảnh báo nếu một node còn phục vụ certificate cũ.

Việc gia hạn thành công ở CA không đồng nghĩa certificate mới đã được cài trên toàn bộ hạ tầng.

### 5.2. Đồng hồ hệ thống

Thời gian sai có thể làm certificate hợp lệ bị coi là chưa có hiệu lực hoặc đã hết hạn. Đảm bảo máy chủ, proxy và client đồng bộ thời gian bằng nguồn đáng tin cậy. Khi gặp lỗi thời hạn bất thường, kiểm tra đồng hồ và timezone trước khi kết luận CA cấp sai.

## 6. Key Usage và Extended Key Usage

Certificate có thể được ký đúng và hostname khớp nhưng vẫn không phù hợp mục đích sử dụng.

### 6.1. Key Usage

Key Usage giới hạn các phép dùng khóa. Ví dụ, certificate CA thường cần keyCertSign để ký certificate khác; certificate máy chủ TLS thường cần digitalSignature tùy thuật toán và profile.

Không dùng certificate CA như certificate leaf cho website. Basic Constraints và Key Usage giúp browser/TLS stack phân biệt vai trò certificate trong chain.

### 6.2. Extended Key Usage

EKU chỉ ra mục đích mở rộng. Với server certificate, EKU thường có TLS Web Server Authentication (serverAuth). Một certificate chỉ được cấp cho client authentication hoặc một mục đích khác có thể không được chấp nhận cho website server authentication.

Khi tạo certificate nội bộ, kiểm tra template/profile cấp chứng chỉ có EKU phù hợp với TLS server. Không sao chép một profile client certificate cho endpoint HTTPS công khai.

## 7. TLS handshake sử dụng certificate như thế nào?

TLS handshake thiết lập tham số bảo mật, xác thực server và tạo khóa phiên. Chi tiết khác nhau giữa TLS 1.2 và TLS 1.3; không nên mô tả một chuỗi message duy nhất cho mọi version.

Luồng khái quát của TLS 1.3:

~~~mermaid
sequenceDiagram
    participant C as Browser
    participant S as TLS Server
    C->>S: ClientHello (version, cipher suites, key share, SNI)
    S->>C: ServerHello (chọn tham số, key share)
    S->>C: EncryptedExtensions
    S->>C: Certificate (certificate chain)
    S->>C: CertificateVerify (proof of private key)
    S->>C: Finished
    C->>S: Finished
    Note over C,S: Hai bên hoàn tất xác thực và dùng traffic keys
~~~

Ở mức khái quát:

1. Client và server thương lượng phiên bản TLS, cipher suite và tham số key exchange.
2. Server gửi certificate chain trong handshake.
3. Client xác minh certificate chain, hostname, thời hạn, usage và các policy cần thiết.
4. Client xác minh CertificateVerify để kiểm tra server chứng minh được quyền sở hữu private key tương ứng.
5. Hai bên xác minh Finished và hoàn tất thiết lập khóa phiên.
6. Dữ liệu ứng dụng được bảo vệ bằng traffic keys của phiên.

Trong TLS 1.3, phần lớn handshake sau ServerHello được mã hóa. TLS 1.2 có trình tự và chi tiết khác; TLS 1.2 có thể dùng các key exchange khác nhau. Certificate không tự chứa khóa phiên và private key server không được truyền cho client.

### 7.1. SNI và lựa chọn certificate

Server có thể phục vụ nhiều hostname trên cùng IP. Client thường gửi Server Name Indication (SNI) trong ClientHello để server chọn certificate phù hợp với hostname.

Nếu cấu hình SNI hoặc virtual host sai, server có thể trả certificate của domain khác và browser báo hostname mismatch. Kiểm tra SNI khi một domain hoạt động nhưng domain khác trên cùng IP bị lỗi.

### 7.2. CertificateVerify khác chữ ký CA

Có hai chữ ký/kiểm tra khác nhau cần phân biệt:

- Chữ ký CA trên certificate xác minh certificate được CA phát hành và nội dung không bị sửa.
- CertificateVerify trong handshake chứng minh server đang nắm private key tương ứng và ràng buộc proof với handshake hiện tại.

Chứng chỉ có chữ ký CA hợp lệ nhưng server không sở hữu private key tương ứng thì handshake vẫn không thể hoàn tất xác thực như mong đợi.

## 8. Certificate chain trên server

Server phải gửi leaf certificate cùng các intermediate certificate cần thiết để client xây dựng chain. Thứ tự thường bắt đầu bằng leaf rồi tới intermediate gần leaf hơn, tiếp tục tới intermediate cao hơn nếu cần.

Một lỗi phổ biến là chỉ cài leaf certificate mà quên intermediate. Kết quả có thể khác nhau giữa client vì một số client đã cache hoặc có khả năng tải intermediate, trong khi client khác không có.

### 8.1. Full chain

Nhiều nền tảng cung cấp file dạng `fullchain.pem` gồm leaf và intermediate certificates. Server thường cần cấu hình đúng file full chain và private key tương ứng theo hướng dẫn của TLS server/load balancer.

Không gửi private key trong chain file hoặc vào response HTTP. Bảo vệ file key bằng permission phù hợp, secret manager hoặc hardware-backed key management nếu hệ thống yêu cầu.

### 8.2. Kiểm tra mọi edge/node

Trong hệ thống có CDN, reverse proxy, load balancer và nhiều origin node, certificate có thể được terminate ở nhiều lớp. Kiểm tra hostname từ góc nhìn client và xác định lớp nào thực sự kết thúc TLS.

Sau khi rotate certificate, kiểm tra nhiều điểm phân phối và nhiều vùng mạng. Một edge cũ có thể tiếp tục phục vụ certificate đã hết hạn dù origin đã được cập nhật.

## 9. Certificate Authority và cách cấp chứng chỉ

CA xác minh quyền kiểm soát tên miền hoặc danh tính theo loại certificate và chính sách cấp phát.

Với domain-validated certificate, CA thường xác minh quyền kiểm soát domain bằng challenge như:

- DNS-01: tạo TXT record theo yêu cầu.
- HTTP-01: phục vụ token tại một URL HTTP cụ thể.
- TLS-ALPN-01: hoàn tất challenge qua TLS/ALPN trong điều kiện được hỗ trợ.

Các challenge có thể được tự động hóa bằng ACME protocol. Automation giảm thao tác thủ công nhưng phải bảo vệ account key, DNS API credentials và quyền sửa challenge record.

### 9.1. Domain Validation không phải kiểm toán doanh nghiệp

DV certificate chứng minh CA đã xác minh quyền kiểm soát domain theo challenge. Nó không có nghĩa CA đã kiểm toán bảo mật ứng dụng, xác minh nội dung website vô hại hoặc bảo đảm doanh nghiệp đáng tin về mọi mặt.

Browser trust indicator không thay đánh giá thương hiệu, quyền truy cập hoặc nội dung nghiệp vụ.

### 9.2. CAA record

DNS Certification Authority Authorization (CAA) record cho phép domain chỉ định CA nào được phép cấp certificate theo cơ chế CAA. CAA giúp giảm nguy cơ cấp nhầm từ CA không được domain cho phép, nhưng không thay kiểm soát tài khoản CA, DNS và quy trình cấp certificate.

Cần cấu hình CAA phù hợp với CA và dịch vụ cấp chứng chỉ đang dùng. Kiểm tra thay đổi DNS và thời gian propagation trước khi phụ thuộc vào record mới.

## 10. Thu hồi chứng chỉ: CRL và OCSP

Certificate có thể cần bị thu hồi trước ngày hết hạn, ví dụ private key bị lộ, cấp sai hostname hoặc tổ chức không còn kiểm soát domain.

Hai cơ chế truyền thống:

- **CRL (Certificate Revocation List):** danh sách certificate serial number đã bị thu hồi do CA phát hành.
- **OCSP (Online Certificate Status Protocol):** client hỏi responder trạng thái của một certificate cụ thể.

### 10.1. OCSP

Client có thể truy vấn OCSP responder để hỏi certificate còn hợp lệ hay đã bị thu hồi. Cách browser thực hiện và xử lý lỗi responder khác nhau theo browser, OS, policy và thời điểm.

Không giả định mọi browser luôn gửi OCSP request cho mọi certificate hoặc luôn hard-fail khi responder không truy cập được. Một số hệ thống dùng cơ chế cập nhật trạng thái thu hồi riêng hoặc chính sách soft-fail để tránh làm gián đoạn truy cập diện rộng.

### 10.2. OCSP stapling

Với OCSP stapling, server lấy một OCSP response đã được CA/responder ký và gửi kèm trong TLS handshake khi phù hợp. Điều này giảm việc từng client phải tự truy vấn responder và có thể cải thiện privacy/latency.

OCSP stapling không tự bảo đảm certificate không bị thu hồi nếu response hết hạn, thiếu hoặc không hợp lệ. TLS server phải cấu hình cập nhật stapled response và client vẫn kiểm tra chữ ký/thời hạn theo policy.

### 10.3. CRL và giới hạn revocation checking

CRL có thể lớn và cần được cập nhật/phân phối. Browser có thể sử dụng các cơ chế riêng để phân phối dữ liệu thu hồi hiệu quả hơn. Khi điều tra revocation, cần biết browser/version, trust store và policy đang sử dụng; đừng suy ra chỉ từ việc server có OCSP URL trong certificate.

Nếu private key bị xâm phạm, ưu tiên thu hồi certificate, cấp certificate mới với key mới, triển khai lại và điều tra phạm vi lộ khóa. Chỉ cấp lại certificate dùng cùng private key đã lộ là chưa đủ.

## 11. Certificate Transparency

**Certificate Transparency (CT)** là hệ thống log công khai các certificate TLS được phát hành. Log CT giúp domain owner, browser và các hệ thống giám sát phát hiện certificate được cấp mà họ không mong đợi.

Một số browser yêu cầu certificate công khai đáp ứng các yêu cầu CT/SCT theo policy của browser. SCT (Signed Certificate Timestamp) là bằng chứng certificate đã được log hoặc được chấp nhận theo cơ chế CT tương ứng.

CT giúp tăng khả năng quan sát việc cấp certificate, nhưng:

- Không tự xác minh website có nội dung an toàn.
- Không thay hostname verification hoặc chain validation.
- Không tự thu hồi certificate đáng ngờ.
- Không bảo vệ private key của server.
- Không bảo đảm mọi loại certificate nội bộ đều xuất hiện trong public log.

Domain owner nên giám sát log CT cho domain quan trọng, điều tra certificate lạ và phối hợp CA/hosting provider khi phát hiện cấp phát bất thường.

## 12. HSTS và TLS certificate

HTTP Strict Transport Security (HSTS) yêu cầu browser dùng HTTPS cho domain đã được ghi nhận HSTS. Header ví dụ:

~~~http
Strict-Transport-Security: max-age=31536000; includeSubDomains
~~~

HSTS giúp chống downgrade và một số tình huống SSL stripping bằng cách browser tự nâng request HTTP lên HTTPS theo policy đã lưu.

Nhưng HSTS không làm certificate sai trở nên hợp lệ.

### 12.1. HSTS và certificate error

Nếu browser đã biết domain là HSTS, lỗi certificate thường không thể được người dùng bỏ qua bằng cách click tiếp tục như một trang HTTPS thông thường có cảnh báo có thể vượt qua. Điều này là có chủ đích: nếu browser buộc HTTPS, nó phải giữ xác minh danh tính TLS.

Nếu certificate hết hạn, sai hostname hoặc chain không tin cậy, cần sửa certificate/server chain. Không hướng dẫn người dùng bỏ qua cảnh báo để đăng nhập.

### 12.2. HSTS không được gửi qua HTTP có thể tin cậy

Browser chỉ chấp nhận HSTS header qua kết nối bảo mật hợp lệ trong điều kiện chuẩn. Vì vậy, lần truy cập HTTP đầu tiên trước khi browser biết HSTS vẫn có thể có khoảng trống nếu domain chưa được preload hoặc policy chưa được lưu.

Preload list có thể giảm khoảng trống first-visit nhưng có yêu cầu triển khai chặt chẽ và quy trình thêm/gỡ riêng. Không bật includeSubDomains hoặc preload khi chưa chắc mọi subdomain đều phục vụ HTTPS với certificate hợp lệ.

### 12.3. HSTS không thay certificate management

HSTS không:

- Cấp hoặc gia hạn certificate.
- Sửa SAN/hostname mismatch.
- Bổ sung intermediate bị thiếu.
- Xác minh private key có được bảo vệ.
- Thay OCSP/CRL/CT hoặc TLS configuration.
- Bảo vệ HTTP endpoint của hostname chưa được browser ghi nhận HSTS.

HSTS và certificate lifecycle phải được vận hành cùng nhau.

## 13. Mutual TLS (mTLS) khác server certificate thông thường

Trong HTTPS thông thường, server trình certificate để browser xác minh danh tính server. Client không nhất thiết phải có certificate.

**Mutual TLS (mTLS)** yêu cầu cả hai phía xác thực bằng certificate theo cấu hình giao thức:

- Server trình server certificate.
- Client trình client certificate khi server yêu cầu.
- Server xác minh client certificate theo trust store/policy của server.

mTLS thường được dùng trong service-to-service, API nội bộ, thiết bị hoặc hệ thống doanh nghiệp. Nó không đồng nghĩa mọi người dùng browser đều phải cài client certificate.

Client certificate cần EKU phù hợp với client authentication và được quản lý riêng. Không dùng server certificate làm client identity chỉ vì chúng cùng là X.509.

## 14. Certificate pinning và vì sao cần thận trọng

Certificate/public key pinning là cách client cố định certificate hoặc public key được mong đợi thay vì chỉ dựa vào trust store công khai. Nó có thể giảm một số rủi ro CA bị xâm phạm nhưng có chi phí vận hành lớn.

Nếu pin sai, rotate key không chuẩn bị trước hoặc quên backup pin, ứng dụng có thể mất khả năng kết nối tới server hợp lệ. HTTP Public Key Pinning (HPKP) cho browser đã bị loại bỏ khỏi các browser hiện đại do rủi ro lockout và vận hành.

Đối với website browser, ưu tiên:

- TLS configuration tốt.
- Certificate Transparency monitoring.
- CAA phù hợp.
- ACME/account security.
- Private key protection và rotation.
- HSTS khi đã đáp ứng điều kiện triển khai.

Không tự thêm pinning vào browser app nếu không có threat model, backup pin và quy trình rotation/incident response rõ ràng.

## 15. Quản lý private key và rotation

Private key thường có rủi ro lớn hơn bản certificate công khai. Các biện pháp vận hành:

1. Tạo key trong môi trường kiểm soát; cân nhắc HSM hoặc managed key service cho hệ thống nhạy cảm.
2. Giới hạn quyền đọc key cho đúng service/account.
3. Không commit private key vào Git, image container hoặc artifact công khai.
4. Không gửi key qua chat, ticket hoặc log.
5. Mã hóa backup và giới hạn người có quyền khôi phục.
6. Theo dõi quyền truy cập và sự kiện export key.
7. Có quy trình rotate key và certificate khi hết hạn hoặc nghi ngờ lộ.
8. Sau rotation, xác minh tất cả edge/node đã dùng key/certificate mới.

Nếu nghi private key bị lộ, xử lý như sự cố bảo mật: cô lập nguồn lộ, revoke certificate khi phù hợp, tạo key mới, cấp lại certificate, triển khai và điều tra log. Không chỉ đổi certificate nhưng tiếp tục dùng key cũ.

## 16. Cấp và gia hạn certificate bằng ACME

ACME tự động hóa trao đổi giữa client và CA để tạo account, yêu cầu certificate, chứng minh quyền kiểm soát domain và tải certificate được cấp.

Quy trình tổng quát:

1. Client tạo hoặc sử dụng ACME account.
2. Client gửi yêu cầu certificate cho các identifier cần thiết.
3. CA cung cấp challenge.
4. Client hoàn thành challenge DNS/HTTP/TLS theo loại được hỗ trợ.
5. CA xác minh quyền kiểm soát domain.
6. Client tạo Certificate Signing Request (CSR) chứa public key và SAN.
7. CA cấp certificate.
8. Client triển khai leaf và intermediate chain cùng private key tương ứng.
9. Automation theo dõi thời hạn và gia hạn trước khi hết hạn.

Bảo vệ ACME account key và credentials của DNS provider. Với DNS-01, API token có quyền sửa DNS zone cần scope tối thiểu và được lưu trong secret manager. Với HTTP-01, đảm bảo challenge endpoint có thể truy cập đúng và không bị redirect/proxy làm sai.

### 16.1. Gia hạn không phải chỉ là chạy lệnh

Một pipeline tốt cần kiểm tra:

- SAN có đủ hostname production không?
- Issuer/chain có được client mục tiêu tin cậy không?
- Certificate có thời hạn mới không?
- Server đang phục vụ đúng certificate mới không?
- Private key có khớp public key certificate không?
- Mọi node/region đã được cập nhật chưa?
- Health check HTTPS và application flow có hoạt động không?

Tạo cảnh báo ở nhiều mốc trước hạn để có thời gian xử lý lỗi CA, DNS challenge hoặc deploy.

## 17. Các lỗi certificate thường gặp trong browser

| Lỗi/triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| Certificate expired | Not After đã qua | Kiểm tra thời gian và certificate đang phục vụ trên mọi edge. |
| Certificate not yet valid | Not Before ở tương lai hoặc đồng hồ sai | Kiểm tra client/server time và certificate. |
| Name mismatch | SAN không khớp hostname truy cập | Kiểm tra URL, SAN, SNI và virtual host. |
| Unknown issuer | CA không nằm trong trust path của client | Kiểm tra issuer, intermediate, trust store và enterprise proxy. |
| Incomplete chain | Server thiếu intermediate | Kiểm tra full chain và cấu hình TLS endpoint. |
| Weak/unsupported algorithm | Key/signature/parameters không đạt policy browser | Cấp certificate mới với thuật toán/kích thước được hỗ trợ. |
| Wrong EKU/Key Usage | Certificate không dành cho server authentication | Kiểm tra profile cấp phát và extensions. |
| Revoked certificate | Certificate đã bị thu hồi | Xác minh trạng thái qua trust/revocation policy. |
| SNI returns wrong certificate | Virtual host hoặc load balancer chọn sai cert | Gửi đúng SNI khi kiểm tra và rà soát listener mapping. |

Một mã lỗi browser cụ thể có thể gộp nhiều nguyên nhân. Dùng certificate viewer, Security panel và TLS diagnostics để xác định trường hợp thực tế.

## 18. Điều tra certificate bằng DevTools

Trong Chrome/Chromium browser, có thể dùng:

1. Mở trang HTTPS.
2. Mở DevTools.
3. Chọn Security panel nếu browser cung cấp.
4. Xem connection status, certificate và thông tin origin.
5. Mở certificate details để kiểm tra Subject, SAN, Issuer, validity và chain.
6. Chọn Network request chính và kiểm tra protocol/remote endpoint khi cần.
7. Mở Console để xem lỗi TLS/certificate nếu có.

Giao diện và tên tab thay đổi theo browser/version. Certificate viewer của browser hoặc hệ điều hành có thể cung cấp chi tiết chain và trust result.

Đừng chỉ kiểm tra trang chủ. Kiểm tra cả API hostname, media CDN, auth domain và subdomain được nhúng vì mỗi hostname có thể phục vụ certificate riêng.

## 19. Thực hành A — Kiểm tra certificate chain bằng OpenSSL

Trên môi trường test hoặc hostname bạn được phép kiểm tra:

~~~bash
openssl s_client -connect shop.example.test:443 -servername shop.example.test -verify_hostname shop.example.test -showcerts -verify_return_error
~~~

Ý nghĩa các tham số:

- connect chỉ định host và port TCP.
- servername gửi SNI để server chọn certificate đúng hostname.
- verify_hostname yêu cầu OpenSSL xác minh hostname với certificate.
- showcerts hiển thị các certificate server gửi.
- verify_return_error yêu cầu báo lỗi verify thay vì chỉ tiếp tục hiển thị kết quả.

Quan sát certificate leaf, intermediate chain và kết quả verify. Lệnh có thể cần cấu hình CA file/path phù hợp với môi trường OpenSSL. Không dùng tùy chọn bỏ qua verify để kết luận endpoint an toàn.

## 20. Thực hành B — Kiểm tra SAN, issuer và thời hạn

Lấy certificate từ server test:

~~~bash
openssl s_client -connect shop.example.test:443 -servername shop.example.test -showcerts
~~~

Có thể lưu leaf certificate vào file PEM trong môi trường lab rồi xem chi tiết:

~~~bash
openssl x509 -in leaf.pem -noout -subject -issuer -dates -text
~~~

Lệnh -text hiển thị toàn bộ certificate extensions; đối chiếu:

- DNS SAN có chứa hostname cần truy cập không?
- Issuer có dẫn tới CA được tin cậy không?
- Not Before/Not After có phù hợp không?
- Key Usage/EKU có phù hợp server authentication không?

Không đăng tải file private key. Certificate leaf là dữ liệu công khai nhưng vẫn tránh đưa URL nội bộ hoặc metadata nhạy cảm vào báo cáo công khai.

## 21. Thực hành C — So sánh hostname hợp lệ và không hợp lệ

Trong lab do bạn quản lý, dùng hai hostname:

~~~text
shop.example.test
api.example.test
~~~

Cấu hình server chỉ có certificate SAN cho shop.example.test. Truy cập cả hai hostname và quan sát:

- shop.example.test có thể xác minh hostname nếu chain và các điều kiện khác hợp lệ.
- api.example.test sẽ gặp name mismatch nếu SAN không bao phủ hostname đó.
- Thay URL sang đúng hostname hoặc cấp certificate có SAN phù hợp sẽ giải quyết lỗi.

Không tắt certificate validation ở browser/client để làm bài test qua được.

## 22. Thực hành D — Quan sát HSTS khi certificate sai

Trên domain lab đã cấu hình HSTS, thử các tình huống trong môi trường kiểm soát:

1. Truy cập HTTPS với certificate hợp lệ.
2. Ghi nhận HSTS header và trạng thái browser.
3. Thử phục vụ certificate hết hạn hoặc sai hostname trên staging riêng.
4. Quan sát browser chặn kết nối và không cho bỏ qua cảnh báo HSTS theo cách thông thường.
5. Khôi phục certificate hợp lệ và kiểm tra lại.

Không thử thay certificate trên production hoặc domain đang phục vụ người dùng. Bài thực hành chỉ nhằm chứng minh HSTS buộc HTTPS và certificate validation vẫn phải thành công.

## 23. Checklist review TLS certificate

- [ ] Certificate leaf chứa đầy đủ DNS/IP SAN cho hostname được phục vụ.
- [ ] Không dựa vào Common Name thay SAN.
- [ ] Kiểm tra wildcard chỉ khớp đúng phạm vi label dự kiến.
- [ ] Not Before/Not After còn hiệu lực và đồng hồ hệ thống chính xác.
- [ ] Issuer chain dẫn tới trust anchor phù hợp.
- [ ] Server gửi đầy đủ intermediate certificates cần thiết.
- [ ] Basic Constraints, Key Usage và EKU phù hợp vai trò.
- [ ] TLS server chứng minh quyền sở hữu private key tương ứng.
- [ ] Private key được bảo vệ, không commit/log/chia sẻ.
- [ ] Certificate được triển khai đồng nhất trên CDN, proxy, load balancer và mọi node.
- [ ] SNI/virtual host trả certificate đúng hostname.
- [ ] Có automation gia hạn và cảnh báo trước khi hết hạn.
- [ ] ACME/DNS API credentials được scope tối thiểu.
- [ ] Có quy trình rotate key và xử lý khi nghi lộ key.
- [ ] Hiểu OCSP/CRL và không giả định browser luôn hard-fail khi responder lỗi.
- [ ] Cân nhắc OCSP stapling và kiểm tra trạng thái response.
- [ ] Giám sát Certificate Transparency và điều tra certificate lạ.
- [ ] CAA được cấu hình phù hợp với CA được phép cấp.
- [ ] Không dựa vào pinning cũ hoặc HPKP cho browser.
- [ ] Phân biệt server certificate và client certificate trong mTLS.
- [ ] HSTS chỉ được bật khi toàn bộ hostname/subdomain trong phạm vi đều phục vụ HTTPS hợp lệ.
- [ ] Không hướng dẫn người dùng bỏ qua certificate warning.
- [ ] Kiểm tra cả website, API, auth, media và các hostname phụ bằng browser/công cụ TLS.

## 24. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Có certificate là website an toàn.” | **Sai** | Certificate xác minh danh tính/kết nối theo PKI; không kiểm toán ứng dụng hay nội dung. |
| “Certificate tự mã hóa dữ liệu HTTPS.” | **Sai** | TLS handshake dùng certificate để xác thực; traffic keys bảo vệ dữ liệu phiên. |
| “Chỉ cần CN khớp hostname.” | **Sai** | Browser hiện đại dựa vào SAN cho hostname verification. |
| “Wildcard *.example.test khớp cả example.test và mọi cấp subdomain.” | **Sai** | Wildcard thường chỉ khớp một label; apex cần SAN riêng. |
| “Server phải gửi root CA.” | **Sai** | Client thường đã có trust anchor; server gửi leaf và intermediate cần thiết. |
| “Chain đúng ở một browser thì đúng mọi browser.” | **Sai** | Trust store, path building và policy có thể khác nhau. |
| “Certificate hết hạn có thể bỏ qua nếu HSTS bật.” | **Sai** | HSTS buộc HTTPS và certificate validation vẫn phải thành công. |
| “OCSP luôn được mọi browser truy vấn và hard-fail.” | **Sai** | Cơ chế revocation checking phụ thuộc browser, OS và policy. |
| “OCSP stapling thay toàn bộ certificate validation.” | **Sai** | Nó chỉ cung cấp trạng thái OCSP; chain, hostname và thời hạn vẫn phải được kiểm tra. |
| “CT log chứng minh website không độc hại.” | **Sai** | CT tăng khả năng quan sát cấp certificate, không đánh giá nội dung website. |
| “DV certificate chứng minh doanh nghiệp đã được kiểm toán.” | **Sai** | DV xác minh quyền kiểm soát domain theo challenge. |
| “mTLS nghĩa là certificate server được gửi hai lần.” | **Sai** | mTLS yêu cầu client cũng xác thực bằng client certificate. |
| “Thay certificate là đủ khi private key bị lộ.” | **Sai** | Cần tạo key mới, thu hồi certificate cũ và điều tra phạm vi lộ. |
| “Cài một root CA lạ chỉ ảnh hưởng một website.” | **Sai** | Trust anchor có thể ảnh hưởng xác minh nhiều hostname trong phạm vi trust store. |
| “HSTS cấp certificate hoặc sửa chain.” | **Sai** | HSTS chỉ buộc browser dùng HTTPS theo policy đã ghi nhận. |

## 25. Tổng kết

TLS certificate là bằng chứng mật mã gắn public key với danh tính máy chủ theo một chuỗi tin cậy PKI. Browser cần xác minh chain, SAN/hostname, thời hạn, constraints và mục đích sử dụng trước khi chấp nhận kết nối. TLS handshake sau đó xác minh server sở hữu private key tương ứng và thiết lập khóa phiên để bảo vệ dữ liệu.

Ba nguyên tắc cần nhớ:

1. **Xác minh đúng danh tính:** SAN phải khớp hostname, chain phải tới trust anchor đáng tin, thời hạn và Key Usage/EKU phải phù hợp.
2. **Vận hành cả vòng đời:** bảo vệ private key, triển khai full chain, theo dõi CT/revocation, tự động gia hạn và rotate key khi có sự cố.
3. **Phối hợp TLS với browser policy:** HSTS buộc HTTPS nhưng không sửa certificate lỗi; mTLS là xác thực hai phía; COOP/CSP và các cơ chế khác bảo vệ những ranh giới riêng.

Khi một browser báo lỗi certificate, hãy hỏi: **URL đang dùng hostname nào, SAN có khớp không, server gửi chain nào, trust anchor có được client tin không, certificate còn hiệu lực và đúng usage không, SNI chọn đúng certificate chưa, và HSTS có đang buộc browser từ chối kết nối không?** Trả lời các câu hỏi đó giúp xác định đúng nguyên nhân thay vì bỏ qua cảnh báo bảo mật.
