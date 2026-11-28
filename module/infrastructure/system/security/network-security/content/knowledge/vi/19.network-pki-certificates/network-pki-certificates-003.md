# Quy trình yêu cầu và cấp certificate trong PKI mạng: từ khóa và CSR đến triển khai an toàn

Trong chương **PKI và chứng thư cho mạng** của module **SECURITY_NETWORK_SECURITY**, **quy trình yêu cầu và cấp certificate** là chuỗi hoạt động giúp một hệ thống có được chứng thư số phù hợp với **danh tính, mục đích sử dụng, chính sách tin cậy và vòng đời khóa**. Certificate thường là **chứng thư X.509** được dùng trong TLS/HTTPS, VPN, mTLS giữa dịch vụ, xác thực Wi-Fi doanh nghiệp với EAP-TLS, thiết bị mạng hoặc các kết nối quản trị.

Nhiều sự cố được mô tả là “TLS lỗi”, “VPN không đăng nhập được” hoặc “Wi-Fi báo chứng chỉ không đáng tin” thực chất bắt nguồn từ một trong các khâu: **tạo khóa**, **lập CSR**, **xác minh quyền yêu cầu**, **CA chọn nội dung/chính sách ký**, **cài chuỗi chứng thư**, **thiết lập trust store**, **gia hạn** hoặc **thu hồi**. Vì vậy, không thể coi việc nhận được một tệp .crt là kết thúc quá trình cấp chứng thư.

Mục tiêu của bài học là thiết kế được một quy trình **tự phục vụ hoặc có phê duyệt** mà vẫn giữ được khả năng kiểm toán, giới hạn quyền và vận hành an toàn. Nội dung kết nối PKI với phòng vệ mạng nhiều lớp: firewall, VPN/ZTNA, IDS/IPS, DNS, Wi-Fi, phân đoạn mạng và hạ tầng cloud.

Sau bài học, bạn có thể:

- Phân biệt **public key, private key, certificate, CSR, CA, RA, root CA, intermediate CA và relying party**.
- Xác định thông tin cần phê duyệt trước khi cấp: **danh tính, tên DNS/IP trong SAN, key usage, extended key usage, thời hạn và certificate profile**.
- Thực hiện các bước an toàn để **tạo keypair, sinh CSR, kiểm tra CSR, xác minh quyền sở hữu rồi phát hành chứng thư**.
- Giải thích **certificate chain, trust anchor, hostname verification, key matching** và những nguyên nhân xác minh TLS thất bại.
- So sánh cấp chứng thư **thủ công, ACME, EST, SCEP** và các quy trình enrollment có kiểm soát trong mạng doanh nghiệp.
- Xây dựng cơ chế **theo dõi hạn, gia hạn/rekey, luân chuyển CA, thu hồi và ứng phó khi private key bị lộ**.
- Phân tích log và chứng cứ của một lần issuance, triển khai các bài **positive/negative tests** trước khi đưa chứng thư vào sản xuất.

## 1. Certificate là lời xác nhận có giới hạn, không phải “tệp bảo mật” chung chung

### 1.1. Các đối tượng tham gia

| Đối tượng | Vai trò chính | Điều không nên hiểu nhầm |
| --- | --- | --- |
| **Subject / subscriber** | Danh tính hoặc hệ thống mà certificate mô tả và bên chịu trách nhiệm sử dụng | Tên nằm trong certificate không tự chứng minh endpoint đang chạy an toàn |
| **Private key** | Bí mật dùng để ký/chứng minh quyền nắm khóa, hoặc phục vụ trao đổi khóa tùy cơ chế | Không được đưa vào CSR hoặc gửi cho CA chỉ để cấp leaf certificate |
| **Public key** | Khóa công khai tương ứng, được certificate gắn với danh tính/thông tin khác | Công khai được nhưng phải xác minh nó thuộc certificate và hệ thống dự kiến |
| **CSR (Certificate Signing Request)** | Yêu cầu cấp chứng thư, thông thường theo định dạng PKCS#10, chứa public key và thông tin được đề nghị | CSR ký bằng private key chưa đủ chứng minh người yêu cầu sở hữu domain hay là nhân viên hợp lệ |
| **RA (Registration Authority)** | Thực hiện/điều phối kiểm tra danh tính, quyền yêu cầu và chính sách trước khi CA phát hành | RA không nhất thiết nắm CA signing key |
| **CA (Certificate Authority)** | Xây dựng và ký certificate theo profile và policy đã được phê duyệt | CA không nên chấp nhận mọi SAN/EKU chỉ vì có trong CSR |
| **Root CA** | Điểm gốc tin cậy thường có certificate tự ký và được cài làm trust anchor | Một certificate tự ký bất kỳ không tự trở thành đáng tin |
| **Intermediate/issuing CA** | Được CA cấp trên ủy quyền ký chứng thư trong phạm vi nhất định | Có quyền mạnh; cần bảo vệ key và áp ràng buộc CA phù hợp |
| **Relying party** | Client/service quyết định có tin certificate khi xác thực đối tác không | Việc ký hợp lệ chỉ là một bước; còn kiểm tra tên, mục đích, thời gian và trust policy |

**PKI (Public Key Infrastructure)** là toàn bộ con người, quy trình, khóa, hệ thống, chính sách và cơ chế vận hành xung quanh việc phát hành/kiểm tra/thu hồi chứng thư, không chỉ gồm phần mềm CA.

### 1.2. Certificate và CSR khác nhau ở đâu?

Một CSR có thể được người yêu cầu ký bằng **private key tương ứng với public key đính kèm**. Việc kiểm tra chữ ký CSR giúp phát hiện thay đổi nội dung và có thể hỗ trợ **proof of possession** của private key; nó **không xác thực danh tính bên ngoài** như quyền quản trị tên miền, tư cách nhân viên hay quyền cấp chứng chỉ cho production.

Một certificate do CA ký chứa **public key cùng subject, issuer, thời hạn, serial, extensions và chữ ký của CA**. Relying party xác minh chain và các điều kiện áp dụng để quyết định có tin chứng thư cho **mục đích cụ thể** hay không.

~~~mermaid
flowchart LR
    S["Chủ hệ thống / requestor"] --> K["Sinh keypair an toàn"]
    K --> Q["CSR: public key + thông tin đề xuất"]
    Q --> R["RA / Policy engine: xác minh quyền"]
    R --> C["Issuing CA: cấp và ký certificate"]
    C --> D["Trả leaf cert + intermediate chain"]
    D --> E["Cài tại VPN/TLS/802.1X/service"]
    E --> T["Client xác minh chain + identity + usage"]
    T --> M["Theo dõi, gia hạn và thu hồi khi cần"]
~~~

Nếu endpoint được kỳ vọng chứng minh quyền sở hữu private key, certificate phải đi cùng **private key tương ứng tại đúng endpoint**. Chỉ chép tệp .crt lên server không đủ để server thực hiện TLS handshake.

## 2. Xác định mục tiêu cấp trước khi tạo khóa

Trước bước kỹ thuật, cần trả lời **cấp chứng thư cho ai, được phép dùng ở đâu và bên nào sẽ tin nó?** Một quy trình xét duyệt tốt tránh tạo certificate quá rộng hoặc sai mục đích.

### 2.1. Phân loại use case

| Use case | Đối tượng dùng certificate | Các điểm cần quyết định |
| --- | --- | --- |
| **HTTPS / TLS server** | Reverse proxy, web server, VPN portal, API gateway | DNS/IP SAN, EKU serverAuth, CA client tin cậy, nơi terminate TLS |
| **Mutual TLS (mTLS)** | Máy chủ và/hoặc client dịch vụ xác thực hai chiều | Server trust store, client certificate identity, clientAuth EKU, authorization mapping |
| **VPN client authentication** | Laptop/thiết bị hoặc user identity qua certificate | Issuing CA, clientAuth, mapping user/device, revocation, remote wipe và session policy |
| **Wi-Fi 802.1X/EAP-TLS** | Supplicant/client và máy chủ EAP/RADIUS theo profile | Client cert/key, server certificate validation, EKU, chính sách mapping và lifecycle thiết bị |
| **Thiết bị mạng quản trị** | Switch, router, firewall, controller hoặc NMS | Management-plane TLS, tên SAN quản trị, tự động gia hạn, trách nhiệm thiết bị |
| **Service mesh / cloud workload** | Workload identity, sidecar, service-to-service TLS | Danh tính workload ngắn hạn, key isolation, issuance API, rotation và trust domain |
| **Code/document signing** | Hệ thống ký sản phẩm/tài liệu | Profile và keyUsage/EKU khác với TLS server; không dùng nhầm web-server certificate |

**Một certificate không nên được dùng cho mọi nhu cầu** chỉ vì có thể cấu hình nó trên nhiều hệ thống. Mục đích dùng phải khớp với policy, profile, extensions và kiểm tra của relying party.

### 2.2. Hồ sơ yêu cầu (request record)

Một ticket/enrollment record nên có:

~~~yaml
# Mẫu yêu cầu nghiệp vụ, không phải API chuẩn của mọi CA.
request_id: PKI-REQ-003
requested_by: "Owner của dịch vụ VPN"
asset_id: "VPN-EDGE-01"
environment: "production"
use_case: "TLS server authentication"
requested_names:
  dns_san:
    - "vpn.example.test"
  ip_san: []
requested_profile: "internal-server-tls"
key_custody: "Generate on VPN endpoint or approved HSM"
key_algorithm_policy: "Organization-approved algorithm and strength"
desired_validity: "Within issuing CA policy"
approver: "Network Security Service Owner"
deployment_owner: "VPN Operations"
renewal_owner: "Certificate Automation / VPN Operations"
evidence_location: "Restricted PKI audit case"
~~~

**example.test** là tên miền được dành cho thử nghiệm/tài liệu; mẫu này minh họa **private PKI**, không phải yêu cầu tới public CA để cấp chứng thư tin cậy công khai cho một tên nội bộ không được phép cấp.

Khi dùng **publicly trusted certificate** cho tên Internet thật, cần tuân thủ chính sách và yêu cầu hiện hành của CA/hệ sinh thái trình duyệt, cùng cơ chế chứng minh quyền kiểm soát domain. Quy trình nội bộ có thể bổ sung yêu cầu phê duyệt dịch vụ, phân quyền và tài sản.

### 2.3. Nguyên tắc hạn chế phạm vi

- **Tên:** chỉ yêu cầu các DNS/IP identity mà tài sản thực sự được phép phục vụ.
- **Mục đích:** serverAuth, clientAuth hoặc profile tương ứng; không tự cấp CA certificate cho endpoint.
- **Thời gian:** sử dụng thời hạn trong giới hạn chính sách, cân đối rotation và độ tin cậy.
- **Khóa:** sinh đúng thuật toán/độ dài cho client và CA policy, quản lý private key tại nơi phù hợp.
- **Owner:** mỗi chứng thư có hệ thống quản lý, người chịu trách nhiệm và đường khôi phục rõ ràng.
- **Môi trường:** tách test/staging/production, tránh tin nhầm root CA của lab trong môi trường sản xuất.

## 3. Những trường X.509 phải hiểu trước khi cấp

Một certificate X.509 có nhiều thuộc tính; kiểm tra đúng những trường quyết định **được tin cho việc gì**.

| Trường / extension | Chức năng | Sai lệch có thể gây ra |
| --- | --- | --- |
| **Subject** | Danh tính mang chứng thư theo quy tắc của profile | Nhầm owner, mapping tài khoản sai hoặc metadata không phù hợp |
| **Issuer** | Tên CA phát hành | Nhầm CA không được tin hoặc chain không đầy đủ |
| **Serial Number** | Số định danh certificate duy nhất trong phạm vi issuing CA theo quy tắc áp dụng | Khó audit/revoke nếu quản lý sai; serial không phải mật khẩu |
| **Not Before / Not After** | Khoảng thời gian certificate có hiệu lực | Lỗi đồng hồ, chưa tới hạn hoặc đã hết hạn |
| **Subject Public Key Info (SPKI)** | Public key cùng thuật toán/tham số | Key không khớp private key triển khai |
| **Signature Algorithm/Value** | Chữ ký CA lên nội dung certificate | Chain không xác minh được nếu chữ ký hoặc thuật toán không được chấp nhận |
| **Subject Alternative Name (SAN)** | Các danh tính như DNS hoặc iPAddress theo định dạng extension | Hostname verification thất bại dù Common Name có vẻ đúng |
| **Key Usage (KU)** | Các hoạt động mật mã key được phép thực hiện, ví dụ digitalSignature, keyEncipherment, keyCertSign | Certificate không phù hợp với handshake hoặc dùng sai quyền |
| **Extended Key Usage (EKU)** | Mục đích ứng dụng, thường gặp serverAuth/clientAuth | Relying party từ chối do sai mục đích hoặc chính sách |
| **Basic Constraints** | Phân biệt CA certificate và end-entity; có thể giới hạn độ sâu CA | End-entity bị cấp quyền CA không mong muốn |
| **Subject/Authority Key Identifier** | Hỗ trợ dựng chain và nhận diện khóa chủ thể/issuer | Khó lựa chain khi nhiều khóa/CA được sử dụng |
| **AIA / CRL Distribution Points** | Thông tin có thể hỗ trợ lấy intermediate hoặc kiểm tra trạng thái | Client không thể dựng chain/kiểm tra revoke nếu phụ thuộc endpoint không hoạt động |
| **Certificate Policies / Name Constraints** | Ràng buộc chính sách và phạm vi theo cấu hình CA | Sử dụng certificate ngoài domain, tenant hoặc mục tiêu đã định |

### 3.1. SAN quan trọng hơn một Common Name “trông đúng”

Đối với xác minh TLS server hiện đại, danh tính **DNS name/IP address cần có trong SAN** theo cách client hỗ trợ và policy yêu cầu. Chỉ đặt **CN=vpn.example.test** mà **không có dNSName SAN** không phải một yêu cầu cấp hợp lý cho server TLS hiện đại.

Ví dụ:

~~~text
Subject:
  CN = vpn.example.test

Subject Alternative Name:
  DNS:vpn.example.test
  DNS:remote.example.test
~~~

Một kết nối bằng **IP literal** có thể yêu cầu **iPAddress SAN** phù hợp thay vì DNS SAN chứa chuỗi trông giống IP. Không tự thêm các wildcard/tên môi trường khác chỉ vì tiện vận hành; mỗi SAN tăng phạm vi danh tính mà certificate có thể đại diện.

**SNI** trong TLS giúp server chọn chứng thư thích hợp khi có nhiều tên trên cùng IP, nhưng **SNI không thay thế hostname validation** tại client.

### 3.2. KU/EKU theo use case

Các cấu hình điển hình:

- **Server TLS:** end-entity certificate với **Basic Constraints CA:FALSE**, EKU **serverAuth** theo chính sách, KU phù hợp thuật toán và phiên bản TLS.
- **mTLS client hoặc EAP-TLS client:** EKU **clientAuth** và identity mapping phù hợp; certificate có thể mang định danh thiết bị/user thay vì DNS tên máy chủ.
- **CA certificate:** **Basic Constraints CA:TRUE**, KU có thể gồm **keyCertSign/cRLSign**, path length constraint nếu phù hợp.

Với TLS hiện đại, **digitalSignature** quan trọng trong nhiều cipher/key exchange mode; đừng sử dụng một mẫu KU/EKU cũ cho tất cả thuật toán và giao thức. CA phải phát hành theo **profile được kiểm thử với client/relying party mục tiêu**, không chỉ sao chép extension từ một CSR bất kỳ.

### 3.3. Chữ ký CA và độ tin cậy

Một certificate có thể **có chữ ký mật mã hợp lệ** nhưng vẫn bị từ chối vì:

- Chain không dẫn tới trust anchor mà client cho phép.
- Tên truy cập không khớp SAN hoặc ứng dụng yêu cầu identity khác.
- EKU/KU/constraints không cho mục đích sử dụng.
- Certificate hết hạn, chưa hiệu lực hoặc clock không đúng.
- Certificate/issuer bị thu hồi theo chính sách xác minh của client.
- Chứng thư do CA có quyền nhưng **nằm ngoài phạm vi** name constraints hoặc policy.

Ngược lại, một ứng dụng tắt **certificate verification** có thể kết nối thành công với chứng thư sai; đó là **bypass kiểm tra tin cậy**, không phải một lần cấp hoặc triển khai thành công.

## 4. Tạo keypair: bước phải bảo vệ chặt nhất

**Private key nên được tạo và lưu trong ranh giới kiểm soát phù hợp với tài sản sử dụng.** Trong mô hình thông thường, CA nhận CSR/public key chứ **không cần nhận private key leaf certificate**. Nếu hệ thống PKI có dịch vụ sinh key tập trung, phải coi đó là quy trình key custody và chuyển giao nhạy cảm riêng, có controls tương ứng.

### 4.1. Các lựa chọn lưu trữ khóa

| Nơi tạo/giữ key | Ưu điểm | Rủi ro và yêu cầu |
| --- | --- | --- |
| **HSM / TPM / secure element** | Giảm nguy cơ private key bị export, hỗ trợ chứng minh key provenance tùy nền tảng | Cần backup/HA, policy truy cập và quản trị thiết bị; không tự bảo vệ application nếu bị chiếm quyền |
| **Keystore do OS quản lý** | Tích hợp với danh tính máy, quyền dịch vụ và tính năng phần cứng nếu có | Cần least privilege, patching, backup có kiểm soát |
| **Software key file** | Đơn giản cho lab và một số dịch vụ | Cần quyền file chặt, mã hóa khi phù hợp, hạn chế copy/backup và rotation |
| **Managed CA/secret service trên cloud** | Tự động hóa lifecycle, IAM và audit tùy dịch vụ | Cần phân tích trust boundary, quyền IAM, region, key export policy và lock-in |

**HSM không phải bảo đảm tuyệt đối.** Nếu ứng dụng có thể yêu cầu HSM ký tùy ý mà không có authorization, kẻ chiếm ứng dụng vẫn có thể lạm dụng key dù không lấy được bytes của private key.

### 4.2. Thuật toán và chính sách khóa

Phổ biến có **RSA** và **Elliptic Curve Cryptography (ECC)** với các tham số phù hợp chuẩn và năng lực phần mềm. Tổ chức cần chọn theo **CA policy, security baseline, khả năng HSM và khả năng tương thích client**, không dùng mặc định thuật toán legacy hoặc khóa quá ngắn.

Quy trình nên:

1. Sinh khóa bằng **cryptographically secure random generator** của môi trường được tin cậy.
2. Không dùng chung một private key giữa nhiều endpoint nếu không có thiết kế và rủi ro được phê duyệt.
3. Bảo vệ bằng HSM/OS keystore hoặc cơ chế lưu file có phân quyền phù hợp.
4. Gắn **key ID, owner, vị trí tạo, mục đích và thời điểm** vào inventory được phân quyền.
5. Cấm đưa private key, seed, passphrase hoặc PFX vào repository, ticket, chat hay image container công khai.
6. Có phương án phục hồi mà **không mở rộng quyền export key** quá mức.

### 4.3. Ví dụ sinh khóa và CSR bằng OpenSSL

Ví dụ cho **môi trường lab/private PKI** với tên **vpn.example.test**; chỉ chạy trên máy có quyền quản trị. Lệnh sau tạo **private key RSA có yêu cầu passphrase** và CSR; không tự phát hành certificate:

~~~bash
# Thực hiện trên host được cấp quyền, với OpenSSL hỗ trợ -addext.
# Không đưa private key, passphrase hoặc CSR chứa thông tin nhạy cảm vào git.
umask 077

openssl req -new -newkey rsa:3072 \
  -keyout vpn.example.test.key \
  -out vpn.example.test.csr \
  -subj "/CN=vpn.example.test" \
  -addext "subjectAltName=DNS:vpn.example.test"

# Kiểm tra cấu trúc CSR và các thông tin được yêu cầu.
openssl req -in vpn.example.test.csr -noout -text

# Kiểm tra chữ ký CSR (không có nghĩa đã xác minh quyền sở hữu tên miền).
openssl req -in vpn.example.test.csr -noout -verify
~~~

**Lưu ý:** OpenSSL sẽ yêu cầu passphrase cho private key theo cơ chế của lệnh và phiên bản tương ứng. Khi triển khai dịch vụ không hỗ trợ nhập passphrase tương tác, cân nhắc **OS keystore, HSM hoặc hệ thống key management**; nếu buộc dùng key không mã hóa khi lưu, cần bảo vệ file/volume, service identity và backup cẩn thận. Không gỡ bảo vệ bằng cách ghi passphrase ngay trong shell history.

Đầu ra là:

~~~text
vpn.example.test.key   # PRIVATE KEY: chỉ chủ thể được ủy quyền giữ
vpn.example.test.csr   # CSR: gửi tới workflow enrollment/CA đã được phê duyệt
~~~

**CSR không chứa private key**. Một CSR được ký hợp lệ vẫn cần các bước RA/domain/device identity verification trước khi CA cấp.

## 5. Kiểm tra CSR trước khi chuyển sang RA/CA

Một CSR nên được kiểm tra ở cả **khía cạnh mật mã, định dạng và nghiệp vụ**.

### 5.1. Kiểm tra kỹ thuật

| Kiểm tra | Câu hỏi | Hành động khi sai |
| --- | --- | --- |
| **CSR signature** | CSR có toàn vẹn và chữ ký hợp lệ so với public key trong CSR không? | Từ chối, tạo lại CSR trên endpoint |
| **Public key algorithm/strength** | Có đáp ứng policy về thuật toán và key size không? | Yêu cầu sinh keypair mới |
| **Requested SAN** | Mọi DNS/IP trong CSR có cần thiết và nằm trong quyền requestor không? | Loại bỏ tên không có thẩm quyền hoặc từ chối |
| **Subject/identity** | Tên hệ thống, user hoặc thiết bị có khớp record được quản lý không? | Xác minh lại với owner/inventory |
| **Requested extensions** | Có yêu cầu CA:TRUE, keyCertSign hoặc EKU quá rộng không? | Không cấp theo yêu cầu không hợp lệ; dùng profile an toàn |
| **CSR duplication** | Có CSR trùng key, trùng tên hoặc yêu cầu bất thường không? | Đối chiếu ticket, tần suất và key lifecycle |
| **Request origin** | Ai gửi, từ thiết bị/automation identity nào, ở môi trường nào? | Kiểm tra authorization trước khi duyệt |

**CA là bên quyết định nội dung certificate cuối cùng.** SAN, KU, EKU và thời hạn trong CSR (nếu có yêu cầu) **không phải một lệnh bắt buộc CA phải tuân theo**. Issuance profile phải ghi đè hoặc từ chối các extension không đúng chính sách.

### 5.2. Xác nhận CSR và key thuộc cùng endpoint

Sau khi certificate được cấp, có thể so sánh **public key** của CSR, certificate và private key tại endpoint được phép để tránh cài một cặp không khớp. Không cần trích xuất private key để chuyển cho người kiểm tra.

~~~bash
# Đối chiếu fingerprint của public key chứa trong CSR.
openssl req -in vpn.example.test.csr -pubkey -noout |
  openssl pkey -pubin -outform DER |
  openssl dgst -sha256

# Sau khi cấp, đối chiếu fingerprint public key của leaf certificate.
openssl x509 -in vpn.example.test.crt -pubkey -noout |
  openssl pkey -pubin -outform DER |
  openssl dgst -sha256
~~~

Nếu fingerprint của **SPKI/public key** không trùng, certificate đã cấp không thuộc cặp key mà CSR ban đầu đại diện, hoặc file đang dùng bị nhầm. Việc so sánh này là **kiểm tra khớp khóa**, không thay thế xác thực danh tính/chính sách CA.

## 6. RA: xác minh người yêu cầu và quyền dùng danh tính

**Registration Authority (RA)** có thể là nhóm vận hành PKI, helpdesk/IAM với quy trình phê duyệt, hoặc một **policy engine tự động**. Mục tiêu là xác thực rằng **người/thiết bị/workload yêu cầu có quyền xin certificate mang danh tính được đề nghị**.

### 6.1. Public certificate và internal certificate có khác nhau?

| Trường hợp | Cần xác minh gì? | Bằng chứng thường dùng |
| --- | --- | --- |
| **Publicly trusted TLS server certificate** | Quyền kiểm soát tên miền theo phương pháp và policy được CA/hệ sinh thái chấp nhận | Domain control validation theo cơ chế của CA, CAA khi cần và audit |
| **Internal HTTPS/VPN server** | Chủ hệ thống có quyền dùng tên DNS/service và sở hữu asset trong tổ chức không | CMDB, DNS zone owner, service approval, automated workload identity |
| **EAP-TLS device certificate** | Thiết bị có được quản lý và đủ điều kiện nhận identity không | MDM enrollment, device attestation khi có, inventory và chính sách cấp |
| **User certificate** | Danh tính nhân viên/nhà thầu còn hiệu lực, có đúng quyền và phương thức recovery không | IAM/HR identity, MFA/approval, role assignment |
| **mTLS workload certificate** | Workload/service account/namespace/cluster được phép mang identity nào | Workload attestation, trusted orchestrator, short-lived enrollment token |

**Chứng minh kiểm soát domain** không đồng nghĩa người yêu cầu được toàn quyền sử dụng certificate cho một hệ thống production của tổ chức. Một CA nội bộ có thể cần **cả kiểm chứng DNS/domain lẫn phê duyệt service owner**.

### 6.2. Ví dụ kiểm chứng quyền cho VPN gateway

Giả sử ticket xin certificate cho **vpn.example.test**:

1. Xác minh gateway **VPN-EDGE-01** còn được quản lý và sử dụng FQDN này.
2. Kiểm tra tên nằm trong **private DNS zone** do tổ chức quản trị, không bị nhầm view test/production.
3. Xác minh requestor/automation account được phân quyền cấp certificate cho asset.
4. Kiểm tra CSR có **chỉ một SAN phù hợp**, không tự thêm **admin.example.test** hoặc wildcard rộng.
5. Kiểm tra profile phải là **server TLS end-entity**, không có quyền ký CA.
6. Lưu phê duyệt, hồ sơ asset và kết quả validation trước khi phát hành.

Khi dùng policy-as-code, nên có danh sách ràng buộc giữa **requestor identity → asset/workload → tên SAN được phép → issuing profile**, thay vì một API token có thể xin mọi tên.

### 6.3. Domain validation trong ACME

**ACME (Automatic Certificate Management Environment)** hỗ trợ tự động hóa việc chứng minh quyền điều khiển tên miền qua các **challenge** được CA/ACME server chấp nhận, ví dụ:

- **HTTP-01:** chứng minh quyền điều khiển endpoint HTTP cho tên miền bằng phản hồi challenge theo giao thức.
- **DNS-01:** công bố bản ghi DNS challenge thích hợp, thường hữu ích cho wildcard và một số môi trường không mở HTTP.
- **TLS-ALPN-01:** chứng minh qua TLS ALPN và thông tin challenge phù hợp trên endpoint được kiểm soát.

Không có một challenge nào phù hợp cho mọi loại certificate. **Cơ chế nào được phép, loại identifier nào được hỗ trợ và chính sách phát hành** do CA/ACME server quyết định. Việc một token DNS API cho phép sửa toàn bộ zone tạo rủi ro cao: nên giới hạn quyền, dùng phân quyền theo zone/record khi có thể và bảo vệ secret cấp chứng thư.

Với public certificate, cần xét **DNS CAA** nếu được áp dụng để kiểm soát CA nào có thể phát hành cho domain; CAA là lớp chính sách DNS, **không phải cơ chế xác thực người dùng** và không thay thế xác minh domain control.

## 7. CA xét duyệt, ký và phát hành certificate

### 7.1. Issuing CA thực hiện điều gì?

Sau khi kiểm tra điều kiện issuance, CA:

1. Nhận **CSR/public key và kết quả RA/authorization**.
2. Chọn **certificate profile**: subject/SAN được phê duyệt, KU, EKU, basic constraints, thời hạn, policies và extensions thích hợp.
3. Xác nhận **key algorithm/strength và định dạng** phù hợp.
4. Gán **serial number** hợp lệ và không trùng trong phạm vi CA theo yêu cầu áp dụng.
5. Tạo certificate với **issuer, validity, public key** và những extension cần thiết.
6. Dùng **CA private key** được bảo vệ để ký certificate.
7. Lưu **issuance audit record**, request/approval correlation và trạng thái phát hành.
8. Trả **leaf certificate và chain/intermediate cần thiết** cho requestor hoặc deployment automation.

Trong hệ thống sản xuất, issuing CA cần **giới hạn quyền và ghi audit cho mỗi issuance**. Một template được cấu hình để cho requestor tùy ý cung cấp SAN hoặc EKU mạnh có thể khiến người ít quyền xin chứng thư đại diện tên/danh tính có đặc quyền.

### 7.2. Root, intermediate và end-entity

~~~mermaid
flowchart TD
    ROOT["Root CA / trust anchor\nprivate key được bảo vệ nghiêm ngặt"] --> INT["Issuing Intermediate CA\nCA:TRUE, keyCertSign"]
    INT --> L1["TLS Server Certificate\nCA:FALSE, serverAuth"]
    INT --> L2["VPN / Device Certificate\nCA:FALSE, clientAuth nếu phù hợp"]
    INT --> L3["mTLS Workload Certificate\nCA:FALSE, usage theo service policy"]
    L1 --> CL["TLS client kiểm tra chain và SAN"]
    L2 --> AUTH["VPN/RADIUS kiểm tra chain và identity"]
    L3 --> MTLS["Service kiểm tra chain và workload identity"]
~~~

**Root key** thường được vận hành với kiểm soát nghiêm ngặt, có thể offline cho nhu cầu ký hiếm, còn issuing/intermediate CA được sử dụng cho phát hành hằng ngày theo quy định. Điều này giảm tác động nếu một issuing CA bị lỗi hoặc phải thu hồi.

Không nên sử dụng **root CA private key trực tiếp ký hàng loạt leaf certificates** khi kiến trúc cần khả năng quản trị, cô lập và thu hồi từng issuing CA.

### 7.3. Các hồ sơ trust khác nhau

- **Public TLS:** relying party chỉ tin những CA đã có trong trust store/browser/OS theo chính sách. Một private CA của tổ chức không tự được browser Internet toàn cầu tin cậy.
- **Private PKI:** tổ chức phân phối root/intermediate trust anchor đúng đối tượng, ví dụ managed laptop, VPN gateway, RADIUS hoặc service mesh.
- **Cross-sign hoặc nhiều chain:** có thể có nhiều con đường xây chain tới trust anchor khác nhau; cần kiểm tra chain phù hợp với tập client.

**Không cài root CA của tổ chức vào mọi hệ thống/thiết bị không cần thiết.** Một root được tin rộng làm tăng phạm vi hậu quả nếu CA policy hoặc key bị xâm phạm.

### 7.4. Certificate Transparency và quyền riêng tư

Trong hệ sinh thái **publicly trusted TLS**, nhiều chứng thư được yêu cầu đáp ứng cơ chế **Certificate Transparency (CT)** theo chính sách của các chương trình tin cậy/trình duyệt. CT hỗ trợ phát hiện chứng thư được phát hành không mong muốn, nhưng **không tự ngăn issuance** và không thay domain authorization.

Đối với **private PKI**, không mặc định gửi tên host nội bộ hoặc certificate doanh nghiệp lên public CT log. Cần kiểm tra chính sách CA, dữ liệu lộ qua tên SAN và mục tiêu quan sát trước khi chọn dịch vụ phát hành.

## 8. Bàn giao certificate: không chỉ là gửi một tệp .crt

Kết quả issuance tối thiểu thường gồm:

~~~text
Leaf certificate   -> danh tính và public key của vpn.example.test
Intermediate chain -> issuing CA certificate(s) cần cho client dựng chain
Private key        -> đã nằm an toàn trên endpoint, KHÔNG gửi kèm từ CA
Root trust anchor  -> nằm trong trust store của bên dựa vào certificate, theo policy
~~~

**Root CA certificate không phải lúc nào cũng nên gửi trong TLS handshake**. Thông thường server gửi leaf và các intermediate cần thiết, còn client dựa vào root trong trust store của mình. Cấu hình chain sai có thể khiến một số client thất bại dù certificate còn hạn.

### 8.1. Các định dạng hay gặp

| Định dạng/đuôi | Nội dung thường thấy | Chú ý |
| --- | --- | --- |
| **PEM (.pem, .crt, .cer)** | Dữ liệu Base64 có nhãn BEGIN CERTIFICATE hoặc BEGIN PRIVATE KEY | Đuôi file không tự nói file chứa gì; kiểm tra header |
| **DER (.der, .cer)** | ASN.1 binary encoding của certificate/key | Cần biết loại dữ liệu để parse đúng |
| **PKCS#7 (.p7b, .p7c)** | Có thể chứa certificate/chain, thông thường không mang private key theo cách dùng phổ biến | Không thay thế file private key tại server |
| **PKCS#12 (.p12, .pfx)** | Container có thể gồm private key, certificate và chain, thường có password/bảo vệ | Xử lý như **bí mật rất nhạy cảm**, không upload vào ticket/chat |
| **JKS/PKCS#12 keystore** | Trust/private-key store cho ứng dụng Java hay dịch vụ khác | Phân biệt **keystore chứa private key** với **truststore chứa CA tin cậy** |

**Đuôi tệp không phải nguồn tin duy nhất.** Ví dụ một file .pem có thể chứa leaf, intermediate hoặc private key; không được công khai toàn bộ tệp chỉ vì nghĩ .pem là certificate.

### 8.2. Cài đúng vai trò ở đúng nơi

- **TLS server:** cấu hình leaf + intermediate chain cùng private key tương ứng; khóa không bị lộ cho mọi người đọc.
- **TLS client:** sử dụng trust store đúng CA và xác minh SAN/hostname, KU/EKU, policy theo giao thức.
- **mTLS server:** ngoài server certificate, cần trust store/policy cho **client certificates** và mapping danh tính sang quyền ứng dụng.
- **VPN gateway:** server certificate phục vụ TLS/IKE theo giải pháp; client certificate có thể ở laptop/thiết bị; cần gắn certificate identity với user/device và chính sách revoke.
- **Wi-Fi Enterprise:** client phải xác minh đúng server certificate của EAP/RADIUS; EAP-TLS cũng cần client certificate/khóa hợp lệ khi profile yêu cầu.
- **Proxy/load balancer:** xác định chính xác điểm TLS termination và backend TLS; nơi nào terminate TLS là nơi phải có leaf+private key tương ứng.

**Cấp certificate thành công không tự tạo một đường truyền được mã hóa an toàn**. Còn cần cấu hình giao thức, cipher, hostname validation, root trust, điểm kết thúc TLS và quyền truy cập network/application.

## 9. Trust chain và kiểm chứng sau issuance

Một certificate không được tin chỉ vì chữ ký bên trong “hợp lệ”. Relying party phải dựng và xác minh **certification path** từ leaf qua những issuer thích hợp đến **trust anchor được chấp nhận**, cùng các kiểm tra danh tính và mục đích.

### 9.1. Checklist xác minh end-to-end

1. **Cryptographic signature:** từng link trong chain có chữ ký đúng với public key issuer tương ứng.
2. **Trust anchor:** chain kết thúc tại root/trust anchor mà ứng dụng thực sự tin.
3. **Validity:** mọi chứng thư liên quan đang trong thời gian hiệu lực theo policy.
4. **SAN/identity:** tên DNS/IP hoặc danh tính user/device đúng với đối tượng client muốn kết nối.
5. **KU/EKU:** certificate được phép dùng cho mục tiêu server/client/CA tương ứng.
6. **Constraints/path:** Basic Constraints, keyCertSign, name constraints/path length và policy cần được tuân thủ.
7. **Revocation policy:** kiểm tra trạng thái theo khả năng client, CA và chính sách của hệ thống.
8. **Key possession:** endpoint thực sự dùng private key khớp leaf certificate.
9. **Protocol configuration:** TLS/IKE/EAP phiên bản/cipher được phê duyệt, SNI và chứng thư được chọn chính xác.
10. **App authorization:** mTLS identity hoặc VPN user certificate chỉ được ánh xạ tới quyền cần thiết.

### 9.2. Kiểm tra offline bằng OpenSSL

Các lệnh sau sử dụng các file **được cấp quyền** sau khi nhận certificate:

~~~bash
# Xem subject/issuer/serial, hạn và các extension của leaf.
openssl x509 -in vpn.example.test.crt -noout -text

# Kiểm tra chain với root trust anchor và intermediate do CA cung cấp.
# Tên file chỉ minh họa, không dùng khóa riêng CA ở đây.
openssl verify -purpose sslserver \
  -CAfile internal-root.pem \
  -untrusted issuing-intermediate.pem \
  vpn.example.test.crt

# Kiểm tra ngày bắt đầu/kết thúc hiệu lực.
openssl x509 -in vpn.example.test.crt -noout -dates
~~~

Kết quả verify thành công trên máy thử nghiệm **không có nghĩa mọi client sẽ thành công**: trust store, thuật toán, revocation policy, hỗ trợ extensions và tên truy cập của từng client có thể khác. Ngoài ra, **openssl verify** theo cách này chủ yếu kiểm tra chain/purpose; khi đánh giá endpoint TLS thực tế phải xác minh **hostname/IP và giao thức** theo công cụ phù hợp.

### 9.3. Kiểm tra handshake server thực tế

~~~bash
# Chỉ kiểm tra endpoint thuộc hệ thống được phép.
# Thay hostname và CAfile bằng giá trị thực của môi trường.
openssl s_client \
  -connect vpn.example.test:443 \
  -servername vpn.example.test \
  -showcerts \
  -verify_return_error \
  -verify_hostname vpn.example.test \
  -CAfile internal-root.pem
~~~

Ở đây **-servername** gửi tên SNI, còn **-verify_hostname** yêu cầu kiểm tra tên trong certificate. Nếu dùng test lab với domain chỉ tồn tại trên DNS nội bộ, máy chạy lệnh phải phân giải/định tuyến tới endpoint phù hợp. Kiểm tra:

- Server đang gửi **leaf đúng FQDN** hay đang gửi default certificate của virtual host khác?
- Có **intermediate cần thiết** không, và root trust của client phù hợp không?
- Thời hạn, EKU/serverAuth, hostname verification và revocation policy có đạt không?
- Server có hỗ trợ giao thức/cipher được policy chấp nhận không?
- Có load balancer nhiều node chỉ một node còn dùng certificate cũ không?

Không sử dụng cách bỏ qua kiểm tra certificate để “làm xanh” bài test. Điều đó có thể che giấu sai chain, giả mạo endpoint hoặc CA bị dùng sai.

## 10. Cấp phát tự động: ACME, SCEP, EST và hệ thống quản trị thiết bị

Tự động hóa rất hữu ích khi có hàng trăm certificate cần **cấp, triển khai, gia hạn và thu hồi**. Nhưng automation phải được cấp quyền theo **danh tính và scope**, tránh biến một token thành khả năng yêu cầu certificate cho cả tổ chức.

| Cơ chế | Mô hình thường gặp | Điều kiện an toàn trọng tâm |
| --- | --- | --- |
| **ACME** | Web/API/TLS certificate enrollment và renewal thông qua CA hỗ trợ ACME | Account key, domain authorization, challenge credentials, rate/issuance policy |
| **EST (Enrollment over Secure Transport)** | Cấp chứng thư thiết bị/enterprise qua kênh TLS và quy trình enrollment | Bootstrap trust, client authentication, authorization mapping, re-enrollment |
| **SCEP (Simple Certificate Enrollment Protocol)** | Cấp certificate cho thiết bị/network appliance/MDM theo nền tảng | Enrollment authorization/challenge, bảo vệ bí mật/RA, validation và khả năng hỗ trợ giao thức |
| **CMP/CMC và API CA nội bộ** | PKI enterprise/phức tạp có quy trình registration, issuance, renewal | Authentication, policy engine, audit, phân quyền và hỗ trợ client |
| **MDM/Identity workload controller** | Cấp certificate tự động dựa trên thiết bị/workload identity | Attestation/registration, lifecycle revoke, chính sách nhóm và giới hạn tên |

**Đừng chọn protocol chỉ theo độ tiện cài đặt.** Một hệ thống có khả năng dùng SCEP không tự bảo đảm quyền yêu cầu SAN; một ACME server nội bộ cấu hình sai cũng có thể cấp cert tùy tiện. Cần kiểm tra *who can request what*.

### 10.1. ACME lifecycle khái niệm

~~~mermaid
sequenceDiagram
    participant A as ACME Client / Service
    participant P as Policy/RA
    participant CA as ACME-enabled CA
    participant D as DNS/HTTP Challenge Endpoint
    A->>CA: Đăng ký account và đặt order cho identifier
    CA-->>A: Authorization/challenge
    A->>D: Chuẩn bị proof được cấp quyền
    CA->>D: Xác minh challenge
    CA->>P: Đánh giá policy/authorization liên quan
    P-->>CA: Kết quả phê duyệt theo cấu hình
    A->>CA: Finalize order với CSR
    CA-->>A: Certificate + chain
    A->>A: Cài và kiểm tra service
    A->>A: Theo dõi hạn và lập lịch renewal
~~~

Đây là sơ đồ **kết hợp nghiệp vụ RA với ACME**, không phải trình tự thông điệp bắt buộc cho mọi ACME server. Trên triển khai thật, kiểm tra policy có thể diễn ra ở những bước khác nhau và không có RA độc lập.

### 10.2. Tự động hóa đi kèm giới hạn quyền

- Cấp **enrollment identity** riêng cho từng nhóm dịch vụ, environment hoặc namespace.
- Ràng buộc được yêu cầu **SAN pattern, profile, key type, EKU, validity và quota**.
- Không trao DNS API token quản lý toàn bộ domain cho mọi workload.
- Ghi **audit correlation** giữa request, người/agent, challenge, CSR fingerprint và issuance serial.
- Bảo vệ **account key, challenge secret và API token**, rotate khi bị lộ hoặc thay owner.
- Có cơ chế **backoff, retry, HA** nhưng không tạo vòng request vô hạn gây rate-limit hoặc flood CA.
- Khi agent lỗi hoặc mất quyền, chỉ những certificate liên quan bị ảnh hưởng; không được có “super-token” dùng chung toàn bộ cluster.

## 11. Gia hạn và luân chuyển certificate không gián đoạn

Certificate có thời hạn. Mục tiêu của **renewal** không chỉ là phát hành certificate mới mà còn là **triển khai trên đúng endpoint, giữ key custody, xác minh handshake và không làm đứt phiên nghiệp vụ**.

### 11.1. Renewal, reissue, rekey khác nhau thế nào?

| Khái niệm | Ý nghĩa thực tế | Khi nào cân nhắc |
| --- | --- | --- |
| **Renewal** | Cấp certificate mới để tiếp tục sử dụng danh tính được phê duyệt theo quy trình của CA | Gần hết hạn, thường qua automation |
| **Reissue / replacement** | Cấp chứng thư thay thế vì thay tên, profile hoặc sai dữ liệu | Bổ sung/bỏ SAN, sửa EKU hoặc thay CA |
| **Rekey** | Tạo keypair mới rồi lấy certificate mới gắn với public key mới | Theo key rotation policy, nghi private key lộ hoặc chuyển HSM |
| **CA/key rollover** | Chuyển sang issuing CA hoặc CA key mới; có thể thay chain/trust | Hết hạn CA, nâng thuật toán, compromise hoặc thay PKI |

Thuật ngữ trong giao diện CA có thể khác. **Không suy luận “renew” chắc chắn tạo keypair mới**: phải kiểm tra quy trình và policy. Khi private key **đã hoặc có khả năng bị lộ**, tái sử dụng khóa cũ không phù hợp; cần **rekey và revoke** theo xử lý sự cố.

### 11.2. Quy trình zero/low-downtime

1. Inventory tất cả **endpoints/nodes/regions** dùng certificate hiện tại.
2. Tạo **CSR/key mới** nếu policy rekey yêu cầu; giữ private key đúng ranh giới.
3. Xác minh **quyền và nội dung request**; CA cấp certificate mới.
4. Kiểm tra chain, SAN, KU/EKU, key match **trước khi triển khai**.
5. Deploy có kiểm soát: **canary/pilot một node**, kiểm tra TLS handshake và app.
6. Phân phối tới các node còn lại, reload/rolling restart theo tính năng dịch vụ.
7. Kiểm tra **tất cả VIP, SNI, backend, region, client platform** không còn phục vụ cert cũ ngoài ý muốn.
8. Cập nhật inventory, expiry alert và ticket; quyết định thời điểm retire/revoke chứng thư cũ.
9. Có rollback plan nhưng **không quay về private key đã bị compromise**.

### 11.3. Gia hạn tự động cần quan sát gì?

Chỉ số hữu ích gồm **days-to-expiry, renewal attempt success rate, issuance rejection reason, deployment propagation lag, số node dùng serial cũ, key rotation coverage, chain verification errors và certificate-related outage**. Đừng chỉ xem “CA đã issue success” khi production load balancer vẫn gửi chứng thư cũ.

## 12. Revocation: chứng thư còn hạn vẫn có thể không còn đáng tin

**Thu hồi certificate** được sử dụng khi không muốn bên xác minh tiếp tục chấp nhận một certificate trước khi nó hết hạn, ví dụ **private key bị lộ, danh tính không còn hợp lệ, thiết bị mất hoặc issuance sai**.

### 12.1. CRL, OCSP và giới hạn thực tế

| Cơ chế | Ý tưởng | Điều cần cân nhắc |
| --- | --- | --- |
| **CRL (Certificate Revocation List)** | CA công bố danh sách serial bị thu hồi, có chu kỳ cập nhật | Client phải lấy/đọc CRL và xử lý khi endpoint không truy cập được |
| **OCSP** | Client/responder cung cấp trạng thái certificate theo yêu cầu | Cache, responder availability, chính sách client, tính riêng tư và failure mode |
| **OCSP stapling** | TLS server có thể đính kèm phản hồi OCSP phù hợp trong handshake | Tính khả dụng/phạm vi hỗ trợ phụ thuộc TLS stack và client |
| **Short-lived certificates** | Giảm thời gian tồn tại của certificate không còn phù hợp | Cần automation đáng tin; không tự thay thế containment nhanh cho mọi trường hợp |
| **Gateway/MDM/IdP policy** | Chặn danh tính/serial/key cụ thể tại điểm enforcement | Có thể bổ sung khi revocation checking không đồng nhất hoặc cần ngắt phiên ngay |

**Revocation không tự bảo đảm mọi client biết ngay**: một số client cache trạng thái, một số hệ thống xử lý timeout theo cách khác, và kết nối đã thiết lập có thể tiếp tục theo quy tắc phiên. Trong sự cố private key lộ, cần kết hợp **revoke + terminate session + thay key + kiểm chứng từng enforcement point**.

### 12.2. Quy trình khi private key bị lộ

1. Xác định **certificate serial, issuer, public key fingerprint, SAN/identity, nơi triển khai**.
2. Ưu tiên cô lập quyền sử dụng key ở **VPN/TLS/mTLS/802.1X gateways hoặc service** theo mức độ rủi ro.
3. Yêu cầu CA **revoke đúng certificate**, ghi reason/audit và xác nhận CRL/OCSP/trust-policy đã cập nhật theo thiết kế.
4. Tạo **keypair mới ở endpoint đáng tin hoặc HSM**, xin certificate mới với authorization đã kiểm tra lại.
5. Triển khai certificate/key mới và kiểm tra handshake/identity matching.
6. Ngắt hoặc hạn chế **session cũ** nếu có nguy cơ tiếp tục truy cập.
7. Điều tra nguyên nhân lộ: repository, backup, ticket, máy chủ bị xâm nhập hoặc pipeline có quyền rộng.
8. Kiểm tra những nơi khác cùng key được sử dụng và cập nhật **controls ngăn tái diễn**.

Nếu **issuing CA key** bị lộ, phạm vi tác động **rộng hơn nhiều** so với một leaf key; cần kích hoạt runbook CA compromise, đánh giá trust anchors/issuance và khả năng reissue số lượng lớn. Không áp công thức “thu hồi một leaf” cho sự cố CA key.

## 13. Threat model của quy trình yêu cầu và cấp certificate

Certificate issuance là **hệ thống cấp quyền danh tính**: ai điều khiển được bước kiểm chứng hoặc signing có thể gây ảnh hưởng ngay cả khi không xâm nhập máy chủ ứng dụng.

| Threat | Đường tấn công hoặc sai sót | Control phù hợp |
| --- | --- | --- |
| **CSR đề nghị SAN trái quyền** | Requestor xin tên của hệ thống khác hoặc wildcard quá rộng | RA kiểm tra asset/name authorization, allowlist pattern, approval |
| **Template cấp quá nhiều quyền** | End-entity được cấp CA:TRUE, clientAuth/serverAuth tùy ý hoặc policy mapping sai | Profile cố định, least privilege template, kiểm toán thay đổi CA |
| **Lộ CA private key** | CA signing key bị export hoặc API ký bị lạm dụng | HSM, dual control khi cần, tách root/issuing CA, audit/backup security |
| **Lộ leaf private key** | File .key/PFX lộ qua repo, image, backup hoặc CI log | Không export khi khả thi, secret scanning, OS permission, rotation/revocation |
| **Enrollment token quá rộng** | Automation account xin certificate cho mọi domain/tenant | RBAC/ABAC, ràng buộc SAN/profile, TTL/quota, per-workload identity |
| **Domain validation bị chiếm** | DNS/HTTP challenge hoặc tài khoản registrar/DNS bị takeover | MFA, DNS API least privilege, ownership monitoring và change audit |
| **Certificate bị cấp sai chain** | Client không có intermediate/trust anchor phù hợp | Chain tests theo từng platform, inventory CA, staged rollout |
| **Client bỏ qua xác minh tên/chain** | “Trust all” hoặc skip cert validation cho nhanh | Code review, TLS policy, negative tests và cảnh báo |
| **Revocation không có hiệu lực** | CRL/OCSP không tới được, cache lâu hoặc client fail-open | Theo dõi revocation path, short-lived strategy khi phù hợp, session termination |
| **Gia hạn thất bại** | ACME token hết quyền, CA outage, job lỗi, cert hết hạn | SLO renewal, expiry alerts, HA, failover/runbook |
| **Public CT lộ tên nhạy cảm** | Dùng public CA để cấp tên private service ngoài thiết kế | Private PKI cho internal names, data minimization, policy review |
| **Trust anchor phân phối sai** | Cài root CA không được kiểm soát lên client hoặc thêm vào truststore quá rộng | Trust store management, approved root inventory, change audit |

### 13.1. Dấu hiệu cần ưu tiên theo dõi

Một hệ thống CA nên cảnh báo khi có:

- Certificate mới cho **SAN chưa từng được phê duyệt**, wildcard hoặc tên quản trị quan trọng.
- Request từ **enrollment identity lạ**, khác environment, hoặc tăng đột biến issuance.
- **Template/profile** thay đổi quyền requestor, KU/EKU, Basic Constraints, validity hoặc rule xét duyệt.
- Thay đổi **CA trust anchors**, issuing CA, CRL/OCSP endpoints hoặc DNS challenge credentials.
- Certificate được cấp cho key đã sử dụng ở nhiều asset ngoài policy.
- Chứng thư bị **revoke bất thường** hoặc nhiều lần renewal fail gần hạn.
- Một số node tiếp tục dùng **serial certificate cũ** sau deployment.

Đây là tín hiệu để điều tra, không phải cứ issuance mới là tấn công. Cần đối chiếu ticket/change window, owner, workload lifecycle và sự kiện cloud/MDM tương ứng.

## 14. Case study: cấp certificate mới cho VPN gateway nội bộ

### 14.1. Bối cảnh giả định

Một tổ chức dùng **VPN gateway** tại **vpn.example.test** cho thiết bị nhân viên được quản lý. Gateway sử dụng **private PKI**, còn client được quản trị bằng MDM với trust anchor doanh nghiệp. Certificate TLS server sắp hết hạn và nhóm network muốn thay bằng chứng thư mới **không gián đoạn truy cập từ xa**.

Đây là mô hình học tập, **không phải hướng dẫn public CA cấp certificate cho .test**.

### 14.2. Các bước với owner và evidence

| Giai đoạn | Người/chức năng chịu trách nhiệm | Evidence cần lưu |
| --- | --- | --- |
| **1. Request** | VPN service owner | Ticket PKI-REQ-003; asset VPN-EDGE-01, FQDN, profile, phạm vi |
| **2. Authorization** | RA/Network Security | Kiểm tra quyền quản trị tên và thiết bị, phê duyệt SAN/EKU |
| **3. Key generation** | VPN ops/HSM automation | Key ID/attestation nếu có, CSR fingerprint; không xuất private key |
| **4. CSR validation** | PKI policy engine | Chữ ký CSR, thuật toán, SAN và requested extensions |
| **5. Certificate issuance** | Issuing CA | Serial, issuer, validity, profile, signing audit, chain |
| **6. Staged deployment** | VPN ops | Canary node, key match, chain, SNI và handshake |
| **7. End-to-end validation** | Security/Helpdesk | Client trust tests, MFA/VPN connectivity, app/DNS access |
| **8. Rollout** | VPN ops | Kết quả từng gateway/node, thời điểm reload, serial thực phục vụ |
| **9. Retirement** | PKI/Asset owner | Inventory cập nhật, cert cũ được loại bỏ/thu hồi theo policy |
| **10. Monitoring** | SOC/PKI operations | Alerts expiry, validation error, unexpected issuance |

### 14.3. Những tình huống thất bại cần dự tính

1. **CSR đúng nhưng SAN bị cấp sai**: client kết nối theo vpn.example.test nhưng leaf chỉ có CN, không có SAN phù hợp → hostname verification fail.
2. **Intermediate thiếu trên gateway**: một số client có cached intermediate vẫn kết nối, một số client khác báo unknown issuer → cần sửa chain served.
3. **Key mismatch**: certificate cấp cho public key A, gateway lại dùng private key B → handshake không thể hoàn tất như mong đợi.
4. **Trust anchor sai trên thiết bị mới**: laptop vừa được enrollment không có enterprise root phù hợp → cần sửa trust distribution, không tắt validation.
5. **Chỉ một node được deploy**: load balancer gửi client tới node certificate cũ → lỗi ngẫu nhiên theo node.
6. **Thu hồi cert cũ quá sớm trước khi rollout đầy đủ**: một node vẫn dùng cert cũ → có thể gián đoạn một phần người dùng.
7. **Gia hạn xong nhưng application mapping sai**: TLS thành công, VPN authentication/authorization vẫn lỗi → phải kiểm tra lớp IAM và policy riêng.

### 14.4. Mẫu handoff kỹ thuật

~~~yaml
case_id: PKI-REQ-003
service: "Internal remote-access VPN"
subject_identity: "vpn.example.test"
profile: "internal-server-tls"
request:
  requester: "VPN Operations"
  approved_by: "PKI Registration Authority"
  csr_fingerprint: "Stored in restricted issuance record"
issued_certificate:
  issuer: "Approved issuing CA"
  serial: "Recorded by CA"
  dns_san: ["vpn.example.test"]
  usage: "TLS server authentication"
  key_custody: "On approved VPN endpoint / HSM"
  chain: "Leaf + approved intermediate(s)"
validation:
  - "Certificate public key matches requested CSR key"
  - "Correct SAN and serverAuth profile"
  - "Chain validates from managed VPN clients"
  - "Both primary and backup gateways serve expected leaf"
  - "VPN authentication, MFA and app connectivity pass"
  - "Certificate expiry alert and renewal owner registered"
rollback:
  allowed: "Only if previous key/certificate are not compromised"
  owner: "VPN Service Owner"
~~~

Không đưa **private key, password, PFX, token API CA hoặc mã MFA** vào trường báo cáo/ticket.

## 15. Trường hợp khác: chứng thư client cho VPN và Wi-Fi EAP-TLS

Quy trình phát hành **client certificate** có điểm khác server TLS: danh tính được chứng nhận thường là **user/device/workload**, không nhất thiết là DNS FQDN của dịch vụ.

### 15.1. Enrollment thiết bị

Một quy trình điển hình:

~~~mermaid
sequenceDiagram
    participant D as Managed device / supplicant
    participant M as MDM / Enrollment service
    participant R as RA / Policy engine
    participant CA as Issuing CA
    participant V as VPN gateway / RADIUS
    D->>M: Thiết bị đăng ký quản trị, chứng minh trạng thái cần thiết
    M->>R: Yêu cầu identity và profile client certificate
    R-->>M: Authorization kết hợp device/user identity
    D->>D: Sinh keypair trong keystore phù hợp
    D->>CA: CSR qua kênh enrollment được kiểm soát
    CA-->>D: Client certificate + chain
    D->>V: Xác thực bằng certificate khi sử dụng dịch vụ
    V->>V: Kiểm tra chain, clientAuth, revocation và identity mapping
~~~

Sơ đồ chỉ là **mô hình trách nhiệm**, không áp đặt MDM hoặc thiết bị tự nói chuyện trực tiếp với CA trong mọi phương thức SCEP/EST. Một số hệ thống có RA/proxy gửi yêu cầu thay thiết bị theo cơ chế được quản lý. Điểm cốt lõi là **khóa, identity và authorization phải khớp**.

### 15.2. Điều gì xảy ra khi thiết bị mất?

Khi laptop mất hoặc bị thu hồi khỏi inventory:

- Xác định **certificate serial/key ID và device identity** gắn với thiết bị.
- **Revoke hoặc ngừng chấp nhận** certificate cũ ở CA/gateway/IdP policy theo thiết kế.
- Chấm dứt **VPN sessions** và các app sessions liên quan nếu rủi ro yêu cầu.
- Cấp certificate mới **trên thiết bị đã xác minh tin cậy**, không sao chép private key cũ.
- Cập nhật MDM/asset inventory và kiểm tra device posture/role trước khi cấp lại quyền.

**Không nhầm client certificate với device authorization.** CA xác nhận identity theo phạm vi, còn VPN/RADIUS vẫn phải quyết định client đó **được phép vào mạng nào** ở thời điểm truy cập.

## 16. Quan sát và kiểm toán quy trình cấp chứng thư

Một nền tảng PKI có thể cấp thành công hàng nghìn chứng thư nhưng vẫn thiếu khả năng điều tra khi có sự cố nếu không lưu **request-to-certificate traceability**.

| Bằng chứng | Trường nên có | Lợi ích |
| --- | --- | --- |
| **Request/ticket** | Request ID, requester, owner, asset, environment, thời điểm | Truy ngược lý do certificate được yêu cầu |
| **Identity/RA check** | Danh tính đã xác minh, quyền đối với SAN/device, approver | Chứng minh đã xét quyền trước issuance |
| **CSR record** | CSR digest, public key fingerprint, requested SAN, algorithm | Phát hiện CSR bị thay đổi hoặc key không khớp |
| **CA issuance audit** | Issuer ID, serial, profile, final SAN/KU/EKU, validity, issuance timestamp | Xác định certificate thực được cấp và vì policy nào |
| **Key custody metadata** | Key ID, keystore/HSM location, allowed export policy | Tránh mất kiểm soát private key |
| **Deployment evidence** | Endpoint/node, serial đã cài, SNI/chain, rollout revision | Biết nơi certificate đang được sử dụng |
| **Validation logs** | TLS/client test, trust path, hostname/EKU, verify outcome | Phát hiện lỗi sau khi cấp |
| **Lifecycle events** | Renewal attempt, revoke reason, CRL/OCSP update, retirement | Điều tra cert hết hạn hoặc bị lạm dụng |
| **Administrative changes** | Thay CA template, issuing policy, RA role hoặc trust anchor | Phát hiện quyền cấp chứng thư bị thay đổi |

### 16.1. Không ghi bí mật vào log

Nên lưu **fingerprint của CSR/public key, serial, key ID và đường dẫn artifact đã kiểm soát** thay vì toàn bộ private key hoặc credential. PEM certificate thường là dữ liệu công khai theo thiết kế nhưng **SAN, subject và metadata hạ tầng nội bộ có thể nhạy cảm**; cần phân quyền và giới hạn chia sẻ phù hợp.

Nếu có dữ liệu trong PCAP/TLS handshake, có thể nhìn thấy nhiều trường certificate nhưng **không có nghĩa private key đã bị lộ**. Với TLS 1.3, việc truy xuất nội dung certificate từ packet capture thụ động có những giới hạn do handshake được mã hóa sau các bước nhất định; cần kết hợp log endpoint/cert inventory khi cần.

### 16.2. Chỉ số vận hành

- **Certificates hết hạn trong các cửa sổ cảnh báo** theo chính sách (ví dụ 30/14/7 ngày chỉ là ví dụ).
- **Renewal success và deployment success** tách riêng nhau.
- Số lượng **issued certificates không có owner** hoặc không có asset mapping.
- Số yêu cầu **SAN/EKU/profile bị từ chối** và nguyên nhân.
- **Thời gian từ request đến approval và issuance** theo mức độ rủi ro.
- **Tỷ lệ endpoint dùng certificate khác inventory**.
- Trạng thái **CRL/OCSP/RA/CA availability** và time synchronization.
- Những thay đổi **trust anchors và issuer keys** chưa có ticket.

## 17. Troubleshooting theo từng giai đoạn

| Triệu chứng | Bước có thể lỗi | Cách điều tra |
| --- | --- | --- |
| CA từ chối CSR ngay | CSR parse/signature/key strength | Kiểm tra openssl req -verify, thuật toán, định dạng PEM/DER |
| Request được nhận nhưng không cấp | RA/domain authorization, template permission, approval | Xem request ID, auth identity, quyền dùng SAN/profile |
| Certificate đã cấp nhưng tên không đúng | SAN request/profile/approval | Đối chiếu CSR, final SAN và issuer policy |
| Service báo certificate/private key mismatch | Deploy nhầm leaf/key | So public key fingerprint; kiểm tra keystore alias |
| Client báo unknown CA/issuer | Thiếu intermediate, sai trust anchor hoặc issuer | Kiểm tra chain, client trust store, alternate chain |
| Client báo hostname mismatch | SAN không có FQDN/IP đích | Kiểm tra URL/SNI, leaf thực phục vụ và SAN |
| TLS handshake thất bại do EKU/KU | Profile sai serverAuth/clientAuth hoặc cipher/policy | Xem extensions, client requirements và CA template |
| Vừa cấp mà đã “expired/not yet valid” | Not Before/After hoặc clock skew | Kiểm tra đồng hồ client/server/CA, timezone |
| Truy cập lúc được lúc không sau rollout | Một số node/VIP còn cert cũ | So serial trên từng IP, node, SNI và region |
| Mỗi lần reboot mất private key | Keystore/volume ephemeral hoặc permission | Kiểm tra nơi lưu, persistence, account dịch vụ và backup |
| VPN/Wi-Fi xác thực cert xong vẫn bị deny | Client identity mapping hoặc network authorization | RADIUS/VPN logs, role, VLAN, group và firewall |
| Certificate bị revoke nhưng session vẫn còn | Session lifetime/cached revocation state | Kiểm tra gateway session, CRL/OCSP và disconnect policy |
| Gia hạn ACME thất bại | Challenge/DNS/HTTP/CA API/authorization | Audit ACME, DNS policy, challenge endpoint, token scope |
| CA hoạt động nhưng workload không deploy được | Automation/CI/sidecar/reload lỗi | Xem deployment logs, service restart, key file ownership |

### 17.1. Cây chẩn đoán nhanh

~~~mermaid
flowchart TD
    A["Certificate enrollment hoặc TLS thất bại"] --> B{"Có issuance thành công chưa?"}
    B -- "Chưa" --> C["CSR hợp lệ? RA/authorization? CA profile/quota?"]
    B -- "Rồi" --> D{"Leaf + key match và deploy đúng endpoint?"}
    D -- "Không" --> E["Sửa deployment/keystore, không cần nới client trust"]
    D -- "Có" --> F{"Client tin chain + đúng SAN/KU/EKU/validity?"}
    F -- "Không" --> G["Sửa chain/profile/trust distribution"]
    F -- "Có" --> H{"Protocol/auth/authorization phía sau TLS thành công?"}
    H -- "Không" --> I["Kiểm tra TLS policy, EAP/VPN, IAM, firewall, route"]
    H -- "Có" --> J["Ghi validation, monitor expiry và lifecycle"]
~~~

Phải điều tra theo **đúng lớp đang thất bại**. Không giải quyết “SSL error” bằng cách tắt hostname verification hoặc đặt trust-all; thao tác đó có thể khiến client tin một endpoint giả.

## 18. Bộ kiểm thử issuance và deployment an toàn

Các phép thử phải được thực hiện trên **CA, tên miền, host, thiết bị và mạng có quyền quản trị**. Dùng lab/private PKI, test identity và challenge được ủy quyền; không thử xin chứng thư cho domain hoặc tài khoản người khác.

### 18.1. Ma trận positive/negative tests

| Test | Điều kiện | Kết quả kỳ vọng |
| --- | --- | --- |
| **P1 – CSR hợp lệ** | Chủ asset tạo keypair và CSR với SAN được phép | RA/CA xét duyệt, certificate cấp đúng profile |
| **N1 – SAN trái quyền** | Test requestor không có quyền với tên được đề nghị | CA/RA từ chối trước khi ký |
| **N2 – CSR signature lỗi** | Dùng fixture CSR bị sửa/không hợp lệ trong lab | CSR bị từ chối, không có certificate |
| **N3 – thuật toán/key quá yếu** | Fixture dưới policy cho phép | Issuing policy từ chối |
| **N4 – yêu cầu CA:TRUE sai quyền** | End-entity requester đề nghị keyCertSign/CA role | Profile loại bỏ quyền không hợp lệ hoặc request bị từ chối |
| **P2 – chain hợp lệ** | Leaf + intermediate đúng, root trong trust store client | Relying party xác minh đúng chain |
| **N5 – hostname mismatch** | Client kết nối bằng tên không có trong SAN | Xác minh TLS thất bại |
| **N6 – thiếu root trust** | Client lab không tin root CA nội bộ | Certificate validation từ chối, không dùng trust-all |
| **N7 – sai clientAuth/serverAuth** | Leaf dùng sai EKU cho phương thức đang thử | Relying party từ chối theo profile |
| **N8 – key mismatch** | Leaf certificate không khớp private key endpoint | Cấu hình/handshake thất bại, có log chỉ nguyên nhân |
| **P3 – renewal** | Automation cấp cert mới, triển khai canary và toàn cluster | Tất cả endpoint phục vụ serial mới và app vẫn hoạt động |
| **N9 – revoked certificate** | Certificate bị thu hồi trong test PKI, client kiểm tra theo policy | Certificate cũ không còn được chấp nhận trong phạm vi yêu cầu |
| **N10 – issuance audit** | Yêu cầu có requestor, approval, CSR digest và serial | CA log truy được chuỗi request → issuance → deploy |
| **P4 – EAP-TLS/VPN client** | Thiết bị tin cậy dùng client certificate hợp lệ | Auth, role/VLAN/network policy và app hoạt động |
| **N11 – lost device certificate** | Device identity bị thu hồi trong test | Gateway/RADIUS từ chối và sessions được xử lý theo policy |

**Test N9 cần được đánh giá theo mô hình revocation thực tế**: thời gian cache CRL/OCSP, availability và session đang hoạt động có thể ảnh hưởng kết quả. Không tuyên bố “revoke xong” nếu điểm thực thi vẫn chấp nhận chứng thư trong phạm vi cần thu hồi.

### 18.2. Acceptance criteria

Một yêu cầu cấp certificate được coi là **hoàn thành kỹ thuật** khi:

1. **Danh tính/SAN đã được xác minh và phê duyệt** theo đúng owner/asset.
2. Private key **được tạo và quản lý đúng**, không bị sao chép vào nơi ngoài policy.
3. CSR hợp lệ, CA đã phát hành **leaf theo profile** và có audit/serial.
4. Leaf có **SAN, KU/EKU, Basic Constraints và thời hạn** phù hợp.
5. Endpoint phục vụ **leaf + intermediate chain**, dùng key tương ứng.
6. Client/relying party **xác minh chain, tên và mục đích** thành công, không tắt validation.
7. Quyền ứng dụng/VPN/Wi-Fi sau xác thực phù hợp phân đoạn và IAM policy.
8. Có **inventory, owner, expiry monitoring, renewal/revocation plan** và rollback được giới hạn.
9. Negative tests xác nhận **cert sai tên, không được tin hoặc ngoài quyền** không thể vượt qua kiểm tra.

## 19. Các nhầm lẫn thường gặp

1. **“CSR chứa private key.”** CSR thông thường chứa public key và thông tin đề nghị, không chứa private key.
2. **“CSR ký hợp lệ chứng minh requestor sở hữu domain.”** Nó chỉ hỗ trợ chứng minh quyền nắm private key; danh tính/quyền SAN cần RA/domain validation.
3. **“CA phải cấp đúng mọi extension CSR yêu cầu.”** CA phải áp profile và policy riêng, từ chối hoặc thay đổi yêu cầu sai.
4. **“Common Name đúng là đủ cho HTTPS.”** Client hiện đại dựa vào SAN để đối chiếu DNS/IP theo policy.
5. **“Certificate có CA signature là đáng tin trên mọi máy.”** Client cần trust anchor và các bước xác minh phù hợp.
6. **“Private CA tự động được mọi browser tin.”** Phải phân phối trust anchor có kiểm soát tới đúng relying parties.
7. **“Cài root CA lên server là tự hoàn tất chain.”** Server thường cần leaf và intermediate, client mới là bên có trust anchor.
8. **“Một certificate dùng được cho mọi mục đích.”** KU/EKU, identity và authorization phải đúng use case.
9. **“Cấp certificate đồng nghĩa client có quyền vào subnet.”** VPN/RADIUS/firewall còn quyết định quyền truy cập sau xác thực.
10. **“Cert đã cấp nên không cần quản lý private key.”** Private key là tài sản nhạy cảm hàng đầu trong vòng đời.
11. **“Đặt certificate trong .pfx nghĩa chỉ có dữ liệu công khai.”** PFX có thể chứa private key và phải bảo vệ như secret.
12. **“Gia hạn luôn tạo keypair mới.”** Cần kiểm tra chính sách rekey/renewal của CA và công cụ.
13. **“CA báo issue success nghĩa production đã đổi cert.”** Cần kiểm tra deployment trên từng node, SNI và client.
14. **“OCSP/CRL luôn thu hồi tức thời mọi kết nối.”** Cache, failure mode và session state có giới hạn.
15. **“TLS kết nối được dù tắt xác minh là đã sửa lỗi certificate.”** Đây là bỏ qua kiểm soát tin cậy.
16. **“CT log đảm bảo không có chứng thư giả.”** CT hỗ trợ minh bạch/phát hiện, không thay authorization hoặc private-key security.
17. **“DNS-01 chứng minh người yêu cầu có quyền cấp mọi certificate nội bộ.”** Challenge chỉ chứng minh điều kiện domain theo policy, còn authorization asset/service cần được xem xét.
18. **“HSM làm key an toàn ngay cả khi API ký không có kiểm soát.”** Kẻ chiếm quyền sử dụng API vẫn có thể lạm dụng việc ký.
19. **“Sao chép private key qua nhiều máy giúp hệ thống HA an toàn hơn.”** Cần đánh giá blast radius, key export và phương án riêng của HSM/PKI.
20. **“Không có log lỗi nghĩa certificate vẫn hợp lệ.”** Có thể thiếu telemetry; cần chủ động kiểm tra expiry, chain và endpoint.

## 20. Bài tập vận dụng

### Bài 1 — CSR chưa đủ để được cấp

Một developer tạo CSR có SAN **vpn.example.test** và **admin.example.test**, ký thành công bằng private key của họ. Họ chỉ sở hữu dịch vụ VPN. CA có nên cấp cả hai tên?

**Gợi ý:** không. RA/CA phải kiểm chứng quyền sở hữu/ủy quyền **cho từng SAN**; chữ ký CSR không chứng minh quyền cấp certificate cho admin service. Nên từ chối hoặc yêu cầu một CSR đã điều chỉnh và được phê duyệt.

### Bài 2 — Đã cấp certificate nhưng client báo không tin

CA nội bộ cấp leaf hợp lệ cho vpn.example.test. Một số laptop kết nối được, máy mới báo **unknown issuer**. Hãy nêu ba kiểm tra đầu tiên.

**Gợi ý:** (1) trust store trên máy mới có enterprise root đúng không, (2) server có gửi intermediate cần thiết không, (3) client có dùng đúng FQDN/SNI và chain của environment không. Không yêu cầu người dùng nhấn “bỏ qua cảnh báo”.

### Bài 3 — Leaf key bị lộ trong container image

Một nhóm phát hiện file private key của TLS server đã được đóng gói trong image mà nhiều người có quyền đọc. Họ định xin certificate mới nhưng dùng lại key cũ. Vì sao phương án đó không phù hợp?

**Gợi ý:** public-key identity mới vẫn dùng private key đã có nguy cơ bị sao chép. Cần **rekey**, revoke/retire certificate liên quan, cập nhật image/pipeline để không đưa secret vào image và đánh giá phạm vi các hệ thống đã dùng key.

### Bài 4 — EAP-TLS xác thực được nhưng client bị deny

Laptop có client certificate hợp lệ, RADIUS xác nhận certificate chain, nhưng người dùng vẫn không truy cập được subnet ứng dụng. Đây có chắc là lỗi CA cấp chứng thư không?

**Gợi ý:** không. Kiểm tra mapping user/device identity, trạng thái tài khoản, VLAN/role NAC, network segmentation, firewall, DNS và route. PKI xác thực danh tính không tự cấp quyền truy cập mọi tài nguyên.

### Bài 5 — Thiết kế tự động hóa ACME

Một team muốn cấp certificate cho nhiều workload trong cluster. Hãy thiết kế **enrollment identity**, phạm vi SAN, challenge secret, expiry alert, audit record, canary deployment và cách thu hồi một workload key khi bị lộ.

**Gợi ý:** dùng identity/role riêng từng workload hoặc namespace, limit domain/SAN, token ngắn hạn và quyền DNS hẹp; lưu mapping request→serial→node; tự động kiểm chứng handshake; thu hồi key/cert bị ảnh hưởng mà không tác động mọi service.

### Bài 6 — Vấn đề khi chỉ đổi leaf certificate

Tổ chức đổi issuing CA, certificate mới đã được cài lên VPN gateway, nhưng một số client cũ báo validation failure. Hãy phân biệt **leaf mismatch, intermediate chain mismatch và trust anchor mismatch**.

**Gợi ý:** đối chiếu SAN/key, issuer/AKI và chain served, sau đó kiểm tra root trust store và thuật toán được client hỗ trợ; không mặc định chỉ cần thêm mọi root CA vào trust store.

### Bài 7 — Lập ma trận threat → control → evidence

Với một PKI cung cấp certificate cho **VPN, Wi-Fi EAP-TLS, internal HTTPS và cloud mTLS**, hãy xác định:

- Ai được yêu cầu certificate và **được phép yêu cầu những SAN/identity nào**?
- Khóa được sinh/lưu ở đâu và khi nào bắt buộc **non-exportable key hoặc HSM**?
- CA/RA dùng control nào để ngăn cấp sai EKU, Basic Constraints và validity?
- Làm thế nào client có **đúng trust anchor, revocation policy và hostname/identity validation**?
- Khi một key bị lộ hoặc certificate sắp hết hạn, **rekey/revoke/rotate** thế nào không làm gián đoạn toàn bộ mạng?
- Những **evidence IDs, audit logs và positive/negative tests** nào chứng minh issuance đúng?

**Gợi ý:** bắt đầu từ asset/identity inventory, threat boundary và profile riêng cho từng use case; không có một certificate profile hoặc token automation “dùng cho mọi thứ” mà vẫn giữ least privilege.

## 21. Tổng kết

**Quy trình yêu cầu và cấp certificate** phải được thiết kế như **chuỗi kiểm soát danh tính và quyền sử dụng khóa**, không chỉ là thao tác tạo file. Một luồng an toàn gồm **xác định use case → sinh và bảo vệ keypair → lập CSR → RA/authorization validation → issuing CA áp profile và ký → bàn giao leaf/chain → triển khai và xác minh ở relying party → theo dõi, gia hạn, rekey hoặc thu hồi**.

Trong kiến trúc **SECURITY_NETWORK_SECURITY**, certificate giữ vai trò thiết yếu ở **TLS/HTTPS, VPN, 802.1X/EAP-TLS, mTLS, thiết bị mạng và cloud workloads**, nhưng chỉ an toàn khi **client kiểm tra đúng trust anchor/SAN/KU/EKU**, private key được bảo vệ, quyền truy cập sau xác thực bị giới hạn, và hệ thống có log/evidence đủ để điều tra. Cấp phát tự động qua **ACME, EST, SCEP hoặc CA API** cần **identity và policy hẹp**, kiểm thử được cả tình huống cấp hợp lệ lẫn cố xin certificate ngoài quyền.

Chỉ coi việc cấp chứng thư hoàn tất khi **endpoint thực sự dùng đúng certificate/key, các client được phép xác minh thành công, yêu cầu không hợp lệ bị từ chối, và chủ sở hữu đã có kế hoạch theo dõi hạn, thay khóa, thu hồi cùng phương án khôi phục**.
