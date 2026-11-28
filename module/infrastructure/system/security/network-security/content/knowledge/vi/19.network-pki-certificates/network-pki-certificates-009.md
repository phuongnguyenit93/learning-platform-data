# Certificate cho thiết bị và workload

> **Chương:** PKI và chứng thư cho mạng  
> **Mô-đun:** SECURITY_NETWORK_SECURITY  
> **Bối cảnh:** Bảo vệ kết nối và danh tính máy trong kiến trúc mạng có phân đoạn, firewall, VPN, NAC, Wi-Fi, IDS/IPS, DNS, cloud và các dịch vụ phân tán.  
> **Trọng tâm:** X.509 certificate cho thiết bị (device identity) và workload (service identity): thiết kế vòng đời, cấp phát, xác thực, mTLS, quản trị khóa và quyền, giám sát, ứng phó sự cố.

## 1. Vì sao thiết bị và workload cần certificate?

Trong mạng doanh nghiệp, không chỉ **người dùng** cần xác thực. Một máy tính muốn tham gia Wi-Fi Enterprise, thiết bị IoT muốn kết nối broker, máy chủ VPN muốn chứng minh danh tính, hoặc microservice muốn gọi API nội bộ đều phải trả lời những câu hỏi:

1. **Đầu bên kia là ai?** Đó có thật là thiết bị/dịch vụ được tổ chức tin cậy hay không?
2. **Đầu bên kia có quyền làm gì?** Được dùng SSID, mở VPN, gọi API hoặc quản trị thành phần nào?
3. **Kênh có an toàn không?** Có TLS đúng cấu hình, khóa riêng được giữ an toàn và endpoint được kiểm tra đúng không?
4. **Danh tính còn hiệu lực không?** Thiết bị đã bị thu hồi, workload đã dừng hay certificate đã hết hạn?

**Certificate số** cho phép một bên trình bày **khóa công khai gắn với một danh tính/thuộc tính**, có chữ ký của tổ chức cấp phát chứng thư hoặc một cơ chế tin cậy tương ứng. Trong mô hình PKI X.509, một **Certificate Authority (CA)** ký chứng thư sau khi áp dụng chính sách xác thực phù hợp.

Ví dụ:

- Laptop được cấp **device certificate** thông qua quy trình quản lý endpoint, dùng để xác thực ở **EAP-TLS/802.1X** khi kết nối Wi-Fi hoặc mạng có dây.
- Máy công nghiệp được cấp certificate riêng để xác thực tới gateway theo **mTLS**, thay cho việc dùng một mật khẩu chung cho mọi thiết bị.
- Service **orders** chạy trong Kubernetes nhận danh tính workload và dùng **mTLS** khi gọi service **inventory**.
- Reverse proxy hoặc API gateway cần **server certificate** để client xác minh đúng tên dịch vụ trước khi trao đổi token/dữ liệu.

**Điểm cốt lõi:** Certificate giúp chứng minh việc một endpoint **sở hữu khóa riêng tương ứng** với public key của chứng thư và gắn việc đó với danh tính mà bên xác thực tin cậy. **Certificate không tự cấp quyền truy cập**, không thay IAM/authorization, không sửa network segmentation và không bảo đảm thiết bị/workload không bị xâm nhập.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Đọc các thành phần X.509: public key, SAN, issuer, validity, Key Usage, Extended Key Usage và chain.
2. Phân biệt **device identity**, **workload identity**, **user identity**, **server certificate**, **client certificate**.
3. Hiểu **mTLS**, **802.1X EAP-TLS**, VPN client certificate và xác thực service-to-service.
4. Thiết kế mô hình **CA, trust domain, issuance, attestation, rotation, renewal, revocation và audit**.
5. Hiểu cách **SPIFFE/SPIRE**, Kubernetes và cloud workload identity giảm phụ thuộc credential tĩnh.
6. Phân tích giới hạn certificate trước các rủi ro **private-key compromise, rogue CA, sai SAN/EKU, expiry và trust store drift**.
7. Thực hiện chẩn đoán, kiểm thử và ứng phó sự cố theo cách không làm lộ private key.

## 2. Các thuật ngữ thiết yếu

| Thuật ngữ | Ý nghĩa | Lưu ý khi thiết kế |
|---|---|---|
| **PKI (Public Key Infrastructure)** | Hệ thống chính sách, CA, chứng thư, quản trị khóa và xác minh danh tính | PKI là một hệ thống vận hành, không chỉ một máy chủ ký cert |
| **X.509 certificate** | Dữ liệu có chữ ký liên kết public key với danh tính/thuộc tính | Certificate không chứa private key |
| **Private key** | Khóa bí mật dùng chứng minh sở hữu khóa/ký hoặc thực hiện tác vụ mật mã | Cần bảo vệ, giới hạn truy cập; không đưa vào logs/CI |
| **Public key** | Khóa công khai nằm trong certificate | Có thể phân phối để bên khác xác minh |
| **CSR** | Certificate Signing Request: yêu cầu ký chứng thư kèm public key và thông tin yêu cầu | CSR không chứa private key; CA phải tự xác minh quyền yêu cầu |
| **Root CA / trust anchor** | Gốc của chuỗi tin cậy được cài vào trust store | Trust anchor quá rộng làm tăng blast radius |
| **Intermediate CA** | CA con ký chứng thư theo phạm vi được phân quyền | Giúp tách nhiệm vụ và giảm sử dụng root key |
| **Leaf/end-entity cert** | Chứng thư của thiết bị, server hoặc workload | Không được cấu hình như CA để tự ký tiếp |
| **SAN (Subject Alternative Name)** | Định danh DNS, IP, URI hoặc kiểu phù hợp trong certificate | Client phải kiểm tra đúng loại danh tính kỳ vọng |
| **KU/EKU** | Key Usage / Extended Key Usage | Ràng buộc mục đích dùng chứng thư |
| **TLS / mTLS** | TLS bảo vệ kênh; mTLS yêu cầu cả hai phía xác thực certificate theo cấu hình | Xác thực kênh không thay business authorization |
| **Attestation** | Xác nhận thông tin nguồn gốc/trạng thái về máy hoặc workload theo cơ chế cụ thể | Không phải mọi certificate issuance đều có attestation mạnh |
| **Rotation / renewal** | Thay khóa/chứng thư hoặc gia hạn chứng thư theo policy | Gia hạn không mặc định sinh khóa mới |
| **Revocation** | Thu hồi trạng thái tin cậy của một certificate trước hạn | Cần biết bên xác minh có thực sự kiểm tra thu hồi không |
| **Trust bundle** | Tập CA/trust anchors dùng để xác minh một nhóm danh tính | Phải phân phối và cập nhật có kiểm soát |

## 3. Phân biệt certificate, identity, authentication và authorization

### 3.1. Certificate đại diện cho loại danh tính nào?

Một certificate có thể mang danh tính **DNS name** của server, **URI** của workload, hoặc dữ liệu khác được xác thực theo chính sách cấp phát. Trong TLS hiện đại, ứng dụng phải biết **loại định danh đang kỳ vọng** và xác minh certificate tương ứng.

| Đối tượng | Danh tính thường dùng | Trường hợp sử dụng |
|---|---|---|
| **Web/API server** | DNS SAN như api.example.com | TLS server authentication |
| **Thiết bị laptop quản lý** | Device ID/subject/SAN theo PKI nội bộ | EAP-TLS, VPN, NAC |
| **Thiết bị IoT/OT** | Device ID gắn serial/inventory theo policy | Xác thực tới IoT gateway hoặc broker |
| **Workload trên VM** | Service identity được cấp từ máy/agent/identity platform | mTLS tới backend |
| **Kubernetes workload** | Service identity hoặc URI SAN như SPIFFE ID | Service-to-service mTLS |
| **Người dùng** | User principal theo hạ tầng IAM/PKI | Có thể dùng user cert trong một số mô hình, khác device cert |

**Device certificate không nhất thiết chứng minh người ngồi trước laptop là ai.** Một thiết bị đạt chứng thực vẫn có thể được người khác sử dụng hoặc bị mã độc điều khiển. Với ứng dụng cần user authorization, phải kiểm tra **user session, MFA, role và quyền tài nguyên** riêng.

### 3.2. Bốn bước độc lập

~~~mermaid
flowchart TD
    A[Endpoint trình bày certificate] --> B[Kiểm tra chain, thời hạn, SAN/EKU, policy]
    B --> C{Certificate và proof of possession hợp lệ?}
    C -- Không --> X[Từ chối xác thực]
    C -- Có --> D[Ánh xạ danh tính đã xác minh]
    D --> E{Danh tính có quyền truy cập tài nguyên?}
    E -- Không --> Y[Từ chối truy cập theo ACL/IAM]
    E -- Có --> F[Cho phép đúng service và action]
    F --> G[Giám sát session, log, quyền hết hạn]
~~~

**Proof of possession** là việc endpoint chứng minh có quyền sử dụng private key tương ứng, ví dụ trong handshake TLS. **Không chỉ kiểm tra file certificate** rồi kết luận endpoint đang sở hữu khóa riêng.

## 4. Cấu trúc một X.509 certificate

Một chứng thư X.509 thường có những trường sau:

| Trường | Mục đích | Cần kiểm tra |
|---|---|---|
| **Version, serial number** | Phiên bản cấu trúc và mã định danh của certificate do CA phát hành | Serial hữu ích cho audit/revocation; không phải toàn cục duy nhất giữa mọi CA |
| **Issuer** | Tên CA phát hành | Cần xây dựng chain tới trust anchor được chấp nhận |
| **Subject** | Thông tin chủ thể | Không thay SAN khi phải so hostname/service identity |
| **Validity: Not Before/After** | Khoảng thời gian chứng thư có hiệu lực | Clock, thời hạn và grace/overlap khi đổi cert |
| **Subject Public Key Info (SPKI)** | Thuật toán và public key của chủ thể | Sức mạnh thuật toán/độ dài khóa theo policy |
| **Signature algorithm** | Thuật toán CA dùng để ký cert | Không dùng thuật toán chữ ký yếu/ngoài policy |
| **Basic Constraints** | Cho biết cert có thể là CA hay không | Leaf thường cần CA:FALSE, CA phải có giới hạn thích hợp |
| **Key Usage** | Mục đích dùng khóa như digitalSignature/keyCertSign | Phải phù hợp vai trò; CA keyCertSign khác leaf |
| **Extended Key Usage (EKU)** | Mục đích mở rộng như serverAuth/clientAuth | Policy phải kiểm tra role thích hợp |
| **Subject Alternative Name (SAN)** | DNS/IP/URI/email/otherName tùy profile | So với **identity kỳ vọng** của kết nối |
| **Authority/Subject Key Identifier** | Hỗ trợ xây dựng chain/nhận diện khóa | Không thay chữ ký và trust validation |
| **CRL Distribution Points / AIA** | Có thể gợi ý nơi lấy CRL, issuer hoặc OCSP theo profile | Có đường truy cập chưa đủ; verifier phải dùng đúng |

### 4.1. Ví dụ certificate metadata

~~~text
Certificate (ví dụ mô phỏng)
  Subject: CN=orders-workload
  Issuer: CN=Workload Issuing CA
  Validity:
    Not Before: 2026-11-28T00:00:00Z
    Not After : 2026-11-29T00:00:00Z
  Public Key: EC P-256
  Basic Constraints: CA:FALSE
  Key Usage: Digital Signature
  Extended Key Usage: TLS Web Client Authentication
  Subject Alternative Name:
    URI:spiffe://prod.example/ns/orders/sa/orders-api

Trust:
  Workload Issuing CA -> Internal Root CA -> Trusted Bundle
~~~

Các tên và thời gian trên **chỉ để học tập**. Một cert workload thực có thể dùng URI SAN, DNS SAN hoặc kiểu định danh khác theo sản phẩm. **CN=orders-workload** không thay thế việc xác minh URI SAN nếu policy yêu cầu một SPIFFE ID cụ thể.

### 4.2. Leaf và CA phải có profile khác nhau

Root/intermediate CA có quyền ký chứng thư; leaf dùng cho server/client không được trao quyền CA ngoài ý muốn. Xử lý sai **Basic Constraints, KU/EKU hoặc trust store** có thể mở rộng vùng tin cậy và làm tăng rủi ro khi một private key bị lộ.

## 5. Certificate chain và trust anchor

Ở mô hình PKI phổ biến:

1. **Root CA** là trust anchor được cài hoặc phân phối vào kho tin cậy.
2. **Intermediate CA** được root hoặc CA cao hơn ký và có quyền cấp trong phạm vi policy.
3. **Leaf certificate** được intermediate ký cho device hoặc workload.
4. Bên xác minh xây dựng **đường chứng thư hợp lệ**, kiểm tra chữ ký, thời gian, constraints, EKU, danh tính và các điều kiện policy khác.

~~~mermaid
flowchart TD
    R[Root CA / Trust Anchor] --> I1[Device Issuing CA]
    R --> I2[Workload Issuing CA]
    I1 --> D1[Laptop 802.1X certificate]
    I1 --> D2[VPN device certificate]
    I2 --> W1[orders workload certificate]
    I2 --> W2[inventory workload certificate]
    D1 --> V1[Authenticator/RADIUS validates chain + identity + policy]
    W1 --> V2[Workload peer validates chain + service identity]
~~~

**Root CA không nhất thiết trực tiếp ký leaf**. Tách intermediate theo mục đích và trust domain giúp giới hạn trách nhiệm. Tuy nhiên việc tách issuing CA **không tạo cô lập hoàn toàn** nếu mọi workload đều tin mọi root/chain hoặc bên xác minh không kiểm tra SAN/EKU/authorization.

### 5.1. Cài một root là trao quyền tin cậy rất lớn

Nếu một thiết bị tin root CA có thể phát **serverAuth cert cho các hostname tùy ý** và ứng dụng chấp nhận mọi chứng thư từ root đó mà không kiểm tra identity đúng, ranh giới tin cậy bị mở quá mức. Chỉ phân phối trust anchor phù hợp mục đích; quản lý quyền cấp cert, SAN policy, issuer constraints, audit và điều kiện xác minh.

### 5.2. Private CA và public Web PKI khác nhau

- **Public Web PKI** phục vụ chứng thư cho public DNS names qua các CA được trình duyệt/hệ điều hành tin cậy theo chính sách tương ứng.
- **Private PKI** phục vụ identity nội bộ cho device, service, VPN, Wi-Fi, IoT hoặc các hostname riêng khi client được quản lý trust.
- **Self-signed leaf** trong lab có thể dùng để học, nhưng production cần trust distribution và lifecycle được quản lý; **không dùng -k/--insecure làm cách vận hành lâu dài**.

Không mặc định một **public certificate cho hostname server** là **device identity**; hai đối tượng có profile, cấp phát và authorization khác nhau.

## 6. Device certificate: thiết bị nào cần xác thực?

**Device identity** liên kết một danh tính logic với một thiết bị hoặc instance được quản lý. Nguồn cấp có thể dựa trên **MDM/UEM, enrollment token, TPM, Secure Enclave/secure element, inventory hoặc thiết bị được nhà sản xuất cấp sẵn**.

### 6.1. Trường hợp sử dụng

| Thiết bị | Certificate phục vụ | Đường cần giới hạn |
|---|---|---|
| **Laptop/desktop** | EAP-TLS Wi-Fi/LAN, VPN device assurance | Chỉ các VLAN/role theo posture và user |
| **Mobile** | Wi-Fi Enterprise, mTLS tới service nội bộ, VPN | MDM compliance, khóa trên hardware nếu hỗ trợ |
| **Router/switch/firewall** | API quản trị, mTLS giữa thiết bị/controller, syslog TLS | Chỉ Management subnet, admin identity |
| **IoT sensor** | mTLS tới MQTT broker/ingestion | Chỉ broker và control endpoint được cấp quyền |
| **Camera/OT device** | Xác thực tới NVR/gateway, provisioning | Mạng IoT/OT riêng, allowlist service |
| **Gateway/edge node** | Danh tính node khi kết nối cloud/on-prem | Điều kiện trust theo fleet/site |

**Serial number hoặc MAC chỉ là thuộc tính nhận diện**, không tự là bằng chứng mật mã về danh tính. Một CSR mang CN=printer-001 **không có nghĩa** hệ thống nên cấp cert cho printer-001: CA/enrollment service phải kiểm tra **quyền yêu cầu identity đó**.

### 6.2. Device certificate và user certificate

Một thiết bị đạt EAP-TLS có thể cho biết đây là **máy được quản lý**, còn việc nhân viên dùng ứng dụng yêu cầu **user SSO/MFA** riêng. Một số môi trường cấp **user certificate** để xác thực người dùng, hoặc kết hợp machine/user authentication. Phải ghi rõ điều kiện nào quyết định quyền truy cập **mạng, thiết bị và ứng dụng**.

## 7. Workload certificate: xác thực service chứ không chỉ máy chủ

**Workload** là đơn vị phần mềm đang chạy: process trên VM, container, Kubernetes pod, serverless function hoặc agent trên edge. Hai workload có thể chia sẻ một host, một workload có thể được chạy lại trên máy khác, và địa chỉ IP có thể đổi thường xuyên.

Vì vậy không nên coi **IP/MAC/hostname vật lý** là danh tính duy nhất của ứng dụng. Workload identity có thể mô tả **dịch vụ và phạm vi triển khai**, ví dụ:

~~~text
spiffe://prod.example/ns/orders/sa/orders-api
spiffe://prod.example/ns/inventory/sa/inventory-api
spiffe://staging.example/ns/orders/sa/orders-api
~~~

Trong mô hình SPIFFE, những giá trị trên là **SPIFFE ID**, dạng URI thuộc trust domain. Đây là **ví dụ định danh**, không phải các địa chỉ website dùng để mở trình duyệt.

### 7.1. Workload identity không tự thể hiện user intent

Service **orders** có chứng thư hợp lệ không có nghĩa mọi request của user qua orders đều được truy cập dữ liệu inventory. **mTLS xác thực service**; ứng dụng cần thực thi authorization theo user, tenant, object và nghiệp vụ.

### 7.2. Vì sao cấp cert theo pod IP không bền vững?

Pod IP có thể đổi khi reschedule, scale hoặc restart. Nếu authorization chỉ dựa vào IP, dễ xảy ra vấn đề khi IP được tái sử dụng. Identity của workload nên được ràng buộc vào **attested deployment/service context** và có vòng đời ngắn, có thể cấp lại khi instance thay đổi.

## 8. EAP-TLS và 802.1X cho Wi-Fi Enterprise hoặc LAN

**802.1X** kiểm soát truy cập mạng tại switch/AP. Trong **EAP-TLS**, client và EAP server thường thực hiện xác thực certificate trong quá trình TLS theo profile giao thức; **AP/switch** đóng vai trò authenticator truyền thông tin EAP giữa supplicant và hệ thống AAA, thường qua RADIUS.

~~~mermaid
sequenceDiagram
    autonumber
    participant D as Laptop / Supplicant
    participant A as AP/Switch / Authenticator
    participant R as RADIUS / EAP-TLS Server
    participant P as PKI / Trust Data
    D->>A: Yêu cầu kết nối 802.1X
    A->>R: Chuyển tiếp EAP qua AAA transport
    R-->>D: EAP-TLS server certificate qua authenticator
    D->>D: Xác minh server identity/chain theo policy
    D-->>R: Client certificate + proof of possession
    R->>P: Kiểm tra chain/profile/trạng thái theo policy
    R->>R: Ánh xạ device/user identity và authorization
    R-->>A: Kết quả AAA và thuộc tính truy cập
    A-->>D: Cho hoặc từ chối truy cập, role/VLAN/ACL
~~~

Sơ đồ là **mô hình khái niệm**, không liệt kê chính xác mọi bản tin EAP-TLS/TLS theo phiên bản. **Điểm rất quan trọng:** client phải xác minh **certificate và tên/identity của EAP server**, không chỉ "tin CA bất kỳ" rồi gửi danh tính thiết bị. Nếu xác thực server bị cấu hình lỏng, thiết bị có thể trao đổi xác thực với hạ tầng không mong đợi.

### 8.1. Sau EAP-TLS vẫn cần phân đoạn

| Kiểm soát | Mục tiêu |
|---|---|
| Client cert hợp lệ và proof-of-possession | Chứng minh danh tính thiết bị theo PKI |
| EAP server cert validation | Thiết bị xác nhận đúng hệ thống xác thực Wi-Fi/LAN |
| RADIUS/NAC policy | Gán role/VLAN/ACL theo user/device/posture |
| DHCP snooping, ARP/ND protections | Giảm spoofing trong phạm vi mạng |
| Firewall/segmentation | Giới hạn quyền vào App, DB, Management |
| Endpoint/MDM security | Giảm nguy cơ một thiết bị được cấp cert bị chiếm quyền |
| Logging | Liên kết identity–port/AP–VLAN–session theo thời gian |

**Không cấp quyền Management vì máy có device certificate hợp lệ.** Certificate chỉ là một yếu tố trong quyết định access.

## 9. Certificate trong VPN và truy cập từ xa

VPN gateway có thể sử dụng:

- **Server certificate:** client xác thực đúng VPN gateway.
- **Client/device certificate:** gateway xác thực thiết bị hoặc peer.
- **User authentication/MFA:** xác thực người dùng độc lập hoặc kết hợp.
- **IAM/authorization:** xác định mạng, dịch vụ và cổng user được truy cập sau khi tunnel đã lên.

### 9.1. Chỉ có cert không có nghĩa được đi mọi mạng

~~~mermaid
flowchart LR
    D[Managed Device + Client Cert] --> V[VPN Gateway]
    U[User SSO/MFA] --> V
    V --> F[Firewall / ZTNA Policy]
    F -->|Role Employee: HTTPS| A[Private App]
    F --x M[Management]
    F --x B[(Database direct)]
    V -. Logs .-> S[SOC]
~~~

Certificate có thể bị **đánh cắp hoặc bị dùng trái phép nếu private key bị lộ**, và một thiết bị đã được công nhận vẫn có thể chạy mã độc. Cần **MFA, posture, short session lifetime, source/role binding, revoke/rotate và per-app authorization**.

### 9.2. Phân biệt TLS client cert và IPsec credential

Một số VPN dùng TLS client certificate, một số dùng **IKEv2/IPsec certificate authentication**, và các loại khác dùng public-key identity hoặc credential riêng. Chúng **không cùng một định dạng cấu hình hay cùng ngữ nghĩa EKU/SAN**. Khi triển khai phải theo protocol, client profile, ID payload, trust anchor và vendor documentation đang dùng.

## 10. mTLS cho kết nối workload-to-workload

**Mutual TLS (mTLS)** là TLS được cấu hình để **cả client lẫn server xác thực danh tính bằng certificate**; bên nào đóng vai trò client/server trong kết nối sẽ quyết định thông điệp và kiểm tra được thực hiện.

Ví dụ **orders** kết nối **inventory**:

~~~mermaid
sequenceDiagram
    autonumber
    participant O as Orders Workload
    participant I as Inventory Workload
    participant T as Trust Bundle / Policy
    O->>I: Mở TLS tới inventory service
    I-->>O: Server cert + handshake proof
    O->>T: Validate chain + inventory identity
    I-->>O: Yêu cầu client certificate (mTLS)
    O-->>I: Orders client cert + proof of possession
    I->>T: Validate chain + orders identity
    I->>I: Authorization: orders có được gọi API này?
    I-->>O: TLS established / API response theo policy
~~~

**Thứ tự mô hình được đơn giản hóa** để tập trung vào quyết định bảo mật; TLS 1.2/1.3 và các library có message flow khác nhau. Thời điểm trao đổi certificate, policy lookup và handshake validation phụ thuộc triển khai.

### 10.1. Một kết nối mTLS hợp lệ cần gì?

1. **Server identity:** client biết danh tính inventory mà nó kỳ vọng, kiểm tra chain, validity, EKU và SAN tương ứng.
2. **Client identity:** server yêu cầu và kiểm tra certificate của orders, proof of possession và trust bundle được phép.
3. **Authorization:** server hoặc proxy xác minh **orders được quyền gọi inventory** theo danh sách allow/deny.
4. **Data plane:** firewall/segmentation chỉ cho các luồng cần thiết; mTLS không thay route policy.
5. **Lifecycle:** certificate được cấp, gia hạn, phân phối và cập nhật mà không làm service gián đoạn.

### 10.2. Nếu server chỉ kiểm tra "cert do root nội bộ ký"

Một workload **staging** cũng có thể có cert từ cùng root và được chấp nhận gọi **production** nếu bên nhận không kiểm tra **SAN/SPIFFE ID, trust domain, EKU và authorization**. Đây là lỗi **trust quá rộng**. Cần kiểm tra danh tính đích/người gọi **chính xác**, không coi thuộc cùng CA là đủ.

## 11. SPIFFE và SPIRE: danh tính workload không phụ thuộc IP

**SPIFFE (Secure Production Identity Framework for Everyone)** định nghĩa mô hình danh tính workload, gồm **SPIFFE ID**, **SVID** (SPIFFE Verifiable Identity Document) và trust bundle. **SPIRE** là một hệ thống có thể triển khai để phát hành và quản lý các danh tính SPIFFE sau khi thực hiện cơ chế attestation/registration tương ứng.

### 11.1. SPIFFE ID

Một SPIFFE ID có dạng URI:

~~~text
spiffe://prod.example/ns/orders/sa/orders-api
~~~

Trong đó **prod.example** là trust domain trong ví dụ. Phần path là cách tổ chức đặt danh tính; SPIFFE **không tự gán ý nghĩa bắt buộc** rằng đoạn ns/orders/sa/orders-api phải là một Kubernetes namespace/service account trong mọi triển khai. Đó là quy ước phổ biến mà hệ thống registration/authorization phải diễn giải.

### 11.2. X.509-SVID và JWT-SVID

| Loại | Mục đích | Lưu ý |
|---|---|---|
| **X.509-SVID** | Certificate X.509 mang SPIFFE ID trong URI SAN; phù hợp mTLS | Private key và chain cần quản lý; peer phải xác minh ID chính xác |
| **JWT-SVID** | JWT mang danh tính SPIFFE để xác thực trong một số luồng | Không phải X.509 certificate/mTLS tự động; phải kiểm tra chữ ký, audience, thời hạn |
| **Trust bundle** | CA/trust roots phục vụ xác minh danh tính trong trust domain | Phải phân phối/rotate đúng; trust bundle không quyết định quyền gọi API |
| **Workload API** | Giao diện để workload lấy danh tính và trust bundle theo triển khai SPIFFE | Bảo vệ access đến socket/API; không cho một workload lấy identity của workload khác |

### 11.3. Node và workload attestation

Một hệ thống issuance như SPIRE có thể kiểm tra **node** rồi kiểm tra **workload** dựa trên những selector được tin cậy (ví dụ process, namespace, service account, cloud instance metadata) theo registration policy. Nếu agent, credential bootstrap hoặc rule registration bị cấu hình quá rộng, một workload trái phép có thể nhận danh tính sai.

**Attestation không đồng nghĩa đo mức an toàn của phần mềm**: một workload có danh tính hợp lệ vẫn có thể bị khai thác runtime. Cần kết hợp admission policy, image provenance, runtime hardening, network policy và application authorization.

### 11.4. Trust domain federation

Khi hai tổ chức/cluster cần tin danh tính từ trust domain khác nhau, có thể sử dụng **federation** với trust bundles/policy phù hợp. Nhưng việc thêm trust bundle của một đối tác **không được biến thành allow-all giữa hai hệ thống**; cần xác định **danh tính nào được phép gọi dịch vụ nào**.

## 12. Kubernetes: certificate cho service, ingress, control plane

Kubernetes có nhiều loại certificate với **mục đích rất khác nhau**:

| Vị trí | Certificate phục vụ | Không được nhầm với |
|---|---|---|
| **Ingress/Gateway** | HTTPS server identity cho hostname ứng dụng | Identity của pod phía sau |
| **Service-to-service mTLS** | Xác thực workload, thường qua sidecar/ambient/agent hoặc ứng dụng | Không mặc định có chỉ vì pod nằm trong cluster |
| **Kubelet/client/control-plane** | Kênh quản lý cluster theo thiết kế PKI của Kubernetes | Certificate để người dùng truy cập web app |
| **Admission webhook** | TLS server certificate để API server kết nối đúng webhook | Authorization của webhook |
| **Service account token** | Token của service account theo cơ chế Kubernetes | Không phải X.509 client cert mặc định |
| **cert-manager** | Tự động xin, gia hạn và tạo Kubernetes TLS Secrets qua Issuer/ClusterIssuer | Không tự chứng minh mọi workload reload cert an toàn |
| **SPIRE/SPIFFE** | Cấp danh tính workload sau attestation | Không tự tạo network policy hoặc application ACL |

### 12.1. Vì sao chỉ tạo Secret TLS chưa đủ?

Tài nguyên Secret chứa certificate/key có thể bị đọc bởi account có quyền, sao chép vào image/log hoặc mount vào nhiều workload. Cần kiểm soát **Kubernetes RBAC**, admission, encryption at rest phù hợp, service accounts, Secret distribution, audit và quy trình **reload/rollout** khi cert thay đổi.

### 12.2. cert-manager và Issuer

Một Issuer/ClusterIssuer có thể tích hợp ACME hoặc CA nội bộ theo cấu hình. **Issuer quyền quá rộng** hoặc certificate request không kiểm soát có thể khiến một namespace xin cert cho tên/danh tính không thuộc quyền. Cần giới hạn **namespace, DNS name/SAN, role, secret access và approval**.

### 12.3. SPIFFE với service mesh

Một service mesh có thể tự động cấp certificate ngắn hạn và xử lý mTLS, nhưng:

- Phải xác minh **mode**: permissive hay strict mTLS, nơi traffic plaintext còn được phép.
- Phải có **authorization policy** để service A không tự động gọi mọi service B chỉ vì cả hai có certificate.
- Phải kiểm tra **ingress/egress, namespace, multi-cluster trust domain** và các luồng bypass mesh.
- Phải xác minh proxy/workload có nhận **rotation** mà không gây outage.

## 13. Cấp certificate: từ bootstrap identity tới issuance

Certificate chỉ đáng tin nếu **quy trình cấp phát** ngăn một bên tự nhận danh tính không thuộc quyền.

### 13.1. Luồng điển hình

~~~mermaid
flowchart TD
    A[Device hoặc workload được khởi tạo] --> B[Tạo private key an toàn]
    B --> C[Tạo CSR hoặc identity request có proof of possession]
    C --> D[Enrollment/Identity service]
    D --> E{Kiểm tra attestation + quyền nhận identity}
    E -- Không --> X[Từ chối + audit]
    E -- Có --> F[CA/Issuer ký certificate profile phù hợp]
    F --> G[Phân phối chain/cert/trust bundle]
    G --> H[Client/server kiểm tra certificate + exact identity]
    H --> I[Rotate/renew và monitor]
    I --> J[Revoke/expire/decommission khi cần]
~~~

Đây là mô hình khái quát; mỗi loại hệ thống có cách tạo CSR, xác minh, issuance, renewal và lưu khóa khác nhau. **Một CSR chứa SAN=admin.example.com không có nghĩa CA nên cấp tên đó**: cần xác thực requester có quyền sử dụng tên/danh tính.

### 13.2. Các phương thức enrollment

| Cơ chế | Thường dùng cho | Rủi ro cần kiểm soát |
|---|---|---|
| **MDM/UEM-integrated issuance** | Fleet laptop/mobile | Chứng thực thiết bị, phân quyền profile, khóa riêng, deprovision |
| **EST (RFC 7030)** | Enrollment certificate cho thiết bị qua TLS | Bootstrap trust, quyền enrollment và client authentication |
| **SCEP** | Thiết bị/MDM theo hệ sinh thái hỗ trợ | Challenge/authorization, profile và giới hạn triển khai |
| **ACME (RFC 8555)** | Tự động issuance theo identifier validation, đặc biệt TLS server cert | Không dùng DNS validation để tự nhận workload identity bất kỳ |
| **Kubernetes CSR/cert-manager** | Cluster/system/service certificates theo controller/issuer | RBAC, approval, SAN scope, Secret access |
| **SPIRE Workload API** | Workload X.509-SVID/JWT-SVID | Node/workload attestation, selectors và socket access |
| **Cloud workload identity** | Workload lấy credential hoặc identity dựa trên platform | Một số dịch vụ cấp token thay vì certificate; phân biệt rõ |
| **Factory provisioning/secure element** | IoT/OT có khóa xuất xưởng | Supply-chain trust và quy trình onboarding vào fleet |

**Không có phương thức nào tự động phù hợp cho tất cả**. Hãy chọn theo threat model, khả năng quản lý thiết bị, tần suất thay workload, hỗ trợ phần cứng và yêu cầu vận hành.

## 14. Khóa riêng: tài sản nhạy cảm nhất của danh tính

**Certificate là dữ liệu công khai tương đối**, còn **private key** phải được bảo vệ. Một certificate vẫn chưa hết hạn nhưng khóa riêng đã bị lộ có thể cho phép người khác thực hiện xác thực với danh tính đó nếu các kiểm soát khác không ngăn được.

### 14.1. Lưu khóa ở đâu?

| Vị trí | Trường hợp | Kiểm soát cần có |
|---|---|---|
| **TPM / hardware-backed key store** | Laptop/server phù hợp | Key không xuất được khi có thể, binding và quản trị lifecycle |
| **Secure element / HSM** | IoT gateway, CA signing key hoặc thiết bị chuyên dụng | Hạn chế export, kiểm soát lệnh ký và audit |
| **OS keystore** | Desktop/mobile/server | Quyền truy cập, profile isolation, backup/recovery được bảo vệ |
| **Kubernetes Secret/volume** | Workload không dùng HSM/agent memory | RBAC, encryption at rest, mount scope và reload an toàn |
| **Workload identity agent memory/API** | X.509-SVID được cung cấp ngắn hạn | Bảo vệ Unix socket/API, process boundary và rotation |
| **Application file** | Trường hợp legacy | File permission chặt, tránh lưu trong image/git/logs |

### 14.2. Không "copy một certificate cho mọi thiết bị"

Nếu nhiều thiết bị dùng **cùng private key và certificate**, việc mất một thiết bị có thể ảnh hưởng cả fleet, và hệ thống khó phân biệt thiết bị nào thực sự kết nối. Nên cấp **danh tính duy nhất** theo asset/workload instance hoặc phạm vi được quản lý theo thiết kế, và có khả năng thu hồi/cô lập một bên mà không cắt mọi bên.

### 14.3. Những sai sót nguy hiểm

- Đưa **.key, .p12/.pfx kèm private key** lên git hoặc image container.
- Ghi private key, enrollment token, passphrase vào log/CI artifact/ticket.
- Cấp filesystem permission cho toàn user trong host đọc private key.
- Cho nhiều workload dùng chung identity để “đỡ phải cấu hình policy”.
- Backup private key không mã hóa hoặc quên xóa khi decommission.
- Tắt kiểm tra peer certificate để sửa lỗi chain.

**Public key/certificate có thể chia sẻ để kiểm tra; private key không được gửi cho CA cùng CSR theo quy trình bình thường.**

## 15. EKU, SAN và certificate profile theo mục đích

Certificate phải đúng **loại danh tính** và **mục đích sử dụng**.

| Profile | SAN/identity phổ biến | EKU thường phù hợp | Bên xác minh |
|---|---|---|---|
| **Web/API server** | DNS:api.example.com | serverAuth | Browser, HTTP client, API gateway |
| **mTLS client** | URI service ID hoặc DNS theo policy | clientAuth | Server/proxy có yêu cầu client cert |
| **EAP-TLS device/client** | Device identity theo PKI | clientAuth theo profile áp dụng | EAP server/RADIUS |
| **VPN TLS server** | DNS:vpn.example.com | serverAuth theo profile | VPN client |
| **VPN client/peer** | Device/user identity theo VPN policy | Phụ thuộc protocol/profile, có thể clientAuth | VPN gateway |
| **Intermediate CA** | CA identity | CA:TRUE, keyCertSign và constraints phù hợp | Verifier xây dựng path |
| **Code signing** | Identity signer theo chính sách | codeSigning | Code/package verifier |

**Đừng tự động dùng cùng leaf cert cho serverAuth, clientAuth, EAP-TLS, code signing và VPN**. Mục đích và ranh giới bảo mật khác nhau, có thể cần issuing CA, trust bundles và lifecycle riêng. Một số profile cấp **dual-use certificate** là hợp lệ khi được thiết kế/kiểm soát có chủ đích, nhưng không nên là mặc định.

### 15.1. SAN hostname là điều kiện kiểm tra bắt buộc trong các client hiện đại

Nếu client kết nối tới **api.example.com**, cần kiểm tra certificate có **DNS SAN khớp với api.example.com** theo quy tắc xác thực tên thích hợp. Chỉ so **Subject CN** thường không phù hợp với thực hành TLS hiện đại.

Nếu client kỳ vọng **SPIFFE URI ID**, nó phải kiểm tra **URI SAN phù hợp với ID cụ thể**. Một cert có URI SAN đúng nhưng được cấp bởi trust domain không được phép cũng không được chấp nhận.

## 16. Chu kỳ sống: cấp, gia hạn, xoay khóa, thu hồi và hủy

Một hệ thống PKI trưởng thành có **vòng đời tự động** thay vì chờ người vận hành xử lý lúc certificate gần hết hạn.

~~~mermaid
flowchart LR
    A[Identity approved] --> B[Generate key + CSR]
    B --> C[Issue certificate]
    C --> D[Distribute + activate]
    D --> E[Monitor expiry + usage]
    E --> F[Renew or rotate before expiry]
    F --> G[Overlap old/new trust where required]
    G --> D
    E --> H[Revoke/expire/decommission]
    H --> I[Invalidate access + remove key/trust]
~~~

### 16.1. Renewal và key rotation khác nhau

- **Renewal** có thể là cấp cert mới với public key cũ hoặc khóa mới, tùy platform/policy.
- **Key rotation** là tạo và đưa vào sử dụng một cặp khóa mới, giảm thời gian phụ thuộc vào khóa đã tồn tại lâu.
- **Trust bundle rotation** là thay/tăng root/intermediate CA mà các client tin cậy; đây là quá trình riêng cần **overlap trust** và kiểm soát scope.
- **Certificate expiration** kết thúc tính hợp lệ theo thời gian, nhưng không thay việc xử lý **credential có nguy cơ lộ** trước hạn.

### 16.2. Vì sao cert ngắn hạn có ích?

Một certificate workload sống ngắn giúp giới hạn khoảng thời gian credential còn hiệu lực nếu bị lộ, **với điều kiện** hệ thống cấp phát, policy và client hoạt động đúng. Nhưng certificate ngắn hạn làm tăng tần suất issuance và yêu cầu:

1. CA/issuer có khả năng phục vụ tải, dự phòng và rate limit phù hợp.
2. Client/sidecar ứng dụng cert mới **trước khi hết hạn** mà không restart gián đoạn.
3. Clock ở các thành phần chính xác và có buffer khi đổi chứng thư.
4. Alert issuance/rotation failures đủ sớm để khắc phục.
5. Trust bundles và permission policy được cập nhật đồng bộ.

Không có một TTL phù hợp cho mọi môi trường: IoT offline nhiều ngày, laptop tắt máy, server được điều phối và pod ngắn hạn có điều kiện khác nhau.

## 17. Revocation: CRL, OCSP, certificate ngắn hạn

**Revocation** là thông báo certificate không còn được tin cậy dù thời hạn chưa hết, ví dụ thiết bị bị mất, tài khoản/identity bị xóa hoặc private key bị nghi lộ.

### 17.1. Các cơ chế phổ biến

| Cơ chế | Vai trò | Hạn chế |
|---|---|---|
| **CRL (Certificate Revocation List)** | CA công bố danh sách serial/cert đã thu hồi | Client cần lấy CRL mới đúng thời điểm; danh sách lớn hoặc mạng offline gây khó |
| **OCSP** | Truy vấn trạng thái certificate theo cơ chế hỗ trợ | Network/reliability, caching và behavior khi responder lỗi |
| **OCSP stapling** | Server cung cấp phản hồi trạng thái phù hợp trong TLS khi được triển khai | Hành vi và yêu cầu khác nhau theo client; không tự thay mọi revocation check |
| **Certificate ngắn hạn** | Giới hạn thời gian còn hiệu lực khi không thu hồi tức thì | Không thay hoàn toàn incident response và session termination |
| **Identity deny/revoke tại CA/agent/gateway** | Ngăn issuance lại và chấm dứt quyền truy cập | Phải thực thi ở đúng hệ thống và các phiên đang hoạt động |

**Không được giả định mọi client TLS đều tự kiểm tra CRL/OCSP.** Nhiều thư viện hoặc cấu hình workload chỉ kiểm tra chain/expiry/SAN, không có revocation checking online mặc định. Cần đánh giá sản phẩm, connectivity, **fail-open/fail-closed** theo rủi ro và mô hình cert lifetime.

### 17.2. Thu hồi không đồng nghĩa cắt mọi phiên đang mở ngay

Kết nối mTLS đã được thiết lập có thể tiếp tục tồn tại cho đến khi session được ngắt hoặc policy/runtime thực thi kiểm tra lại. Khi có key compromise cần **revoke/deny identity, ngắt session, rotate keys, thu hồi quyền IAM và kiểm tra các kết nối đang hoạt động** tùy platform.

### 17.3. Thiết bị offline

IoT/OT hoặc thiết bị di động thường offline, chưa nhận trust bundle/CRL mới đúng thời hạn. Đặt yêu cầu offline duration, certificate TTL, cơ chế bootstrap an toàn và chính sách failover rõ ràng; tránh "không kiểm tra gì để thiết bị luôn chạy".

## 18. Quy trình CA và trust-domain rotation

Thay root hoặc intermediate CA sai có thể làm **mọi EAP-TLS/VPN/mTLS connection thất bại**. Vì thế cần tách:

1. **Phân phối trust anchor/bundle mới** cho các bên xác minh trước.
2. **Cấp thử leaf bằng CA mới** và xác minh nhiều nền tảng/zone.
3. **Chuyển issuance** sang CA mới từng bước, có overlap khi policy cho phép.
4. **Giám sát chain building, PKIX validation và mTLS failures** ở client/server.
5. **Ngừng tin CA cũ** chỉ sau khi các leaf/thiết bị đã chuyển, trừ trường hợp compromise khẩn cấp.

### 18.1. Rủi ro khi trust bundle không đồng nhất

| Thành phần | Sự cố có thể gặp |
|---|---|
| Laptop dùng EAP-TLS | OS/MDM chưa nhận CA mới nên không xác minh được RADIUS server |
| VPN client | Profile chỉ tin CA cũ nên không kết nối được gateway |
| Service mesh sidecar | Trust bundle chưa đồng bộ nên mTLS giữa pod mới/cũ lỗi |
| IoT offline | Không nhận intermediate/root mới, phải có phương án khôi phục riêng |
| Public endpoint phía cloud | Cert chain khác giữa các region, client báo lỗi từng vùng |
| API gateway | Trust bundle quá rộng hoặc sai SAN validation khiến nhận nhầm workload |

**Cross-signing và multiple trust paths** có thể hỗ trợ migration trong một số hệ PKI, nhưng tăng độ phức tạp. Không tự giả định một chain duy nhất sẽ được mọi client xây dựng giống nhau.

## 19. Threat modeling cho certificate của thiết bị và workload

| Tài sản | Rủi ro | Biện pháp phòng vệ |
|---|---|---|
| **Root/intermediate CA key** | Lộ khóa khiến attacker có thể phát chứng thư trái phép | HSM, least privilege, offline root nếu phù hợp, key ceremony, audit |
| **Enrollment token/credential** | Xin certificate cho identity không thuộc quyền | Short-lived bootstrap credentials, attestation, approval, rate limit |
| **Device private key** | Giả mạo thiết bị khi key bị copy | TPM/secure element, non-exportable key khi hỗ trợ, deprovision |
| **Workload private key/Secret** | Giả mạo service, truy cập ngang | RBAC/namespace/agent isolation, short-lived cert, rotate |
| **SAN/EKU policy** | Cấp cert quá nhiều mục đích/identity | Issuance constraints, approval, profile lint |
| **Trust bundle** | Thêm CA không được phép, trust domain mở rộng | Signed/config-controlled distribution, inventory và drift monitoring |
| **mTLS authorization** | Chấp nhận mọi client cert dưới cùng root | Exact service identity check + service ACL |
| **Time/revocation** | Cert hết hạn/đã thu hồi vẫn được dùng sai policy | NTP, revocation strategy, session revoke |
| **Application endpoint** | Certificate đúng nhưng user/API không có quyền | Application authorization, tokens, least privilege |
| **Network segmentation** | Workload đúng cert vẫn có đường tới DB/Management không cần thiết | Firewall, security group, microsegmentation, NAC |

### 19.1. STRIDE ở mức hệ thống

- **Spoofing:** kẻ khác dùng private key bị lộ hoặc có enrollment sai để nhận identity hợp lệ.
- **Tampering:** thay trust bundle, CA config, CSR approval hoặc policy kiểm tra identity.
- **Repudiation:** thiếu log issuance/revocation khiến không truy được ai đã yêu cầu/cấp chứng thư.
- **Information disclosure:** key/cert PFX trong backup/log, metadata user/device không được bảo vệ.
- **Denial of service:** certificate expiry đồng loạt, CA outage, clock drift, revocation backend down.
- **Elevation of privilege:** leaf cert được cấp profile CA hoặc role authorization quá rộng.

Không phải mọi trường hợp là một cuộc tấn công; lỗi **configuration, expiration hoặc automation** cũng có thể gây tác động tương tự.

## 20. Kiến trúc nhiều lớp cho device/workload certificate

Ví dụ tổ chức dùng Wi-Fi Enterprise cho nhân viên, VPN quản trị, cloud Kubernetes và API:

~~~mermaid
flowchart TB
    ROOT[Offline/Protected Root CA] --> ICA1[Device Issuing CA]
    ROOT --> ICA2[Workload Issuing CA]
    ICA1 --> MDM[MDM/UEM Device Enrollment]
    MDM --> DEV[Laptop / Mobile / IoT]
    DEV --> WIFI[802.1X AP + RADIUS]
    DEV --> VPN[VPN Gateway + MFA]
    ICA2 --> WA[Workload Identity Agent / Issuer]
    WA --> O[Orders service]
    WA --> I[Inventory service]
    O -->|mTLS + service authorization| I
    WIFI --> FW[Network Segmentation / Firewall]
    VPN --> FW
    FW --> API[Approved Internal APIs]
    FW --x DB[Direct DB / Management access]
    ICA1 -. issuance/revocation audit .-> SOC[SOC / SIEM]
    ICA2 -. rotation/validation audit .-> SOC
    WIFI -. NAC decisions .-> SOC
    VPN -. VPN/Auth decisions .-> SOC
~~~

### 20.1. Nguyên tắc thiết kế

1. **Tách identity theo mục đích:** Device CA, workload CA, public HTTPS CA và certificate quản trị không mặc định có cùng quyền.
2. **Tách mạng:** khách Wi-Fi, nhân viên, IoT, API, DB và management nằm ở zone phù hợp.
3. **Mỗi certificate có owner:** asset, workload, service hoặc team sở hữu và chu kỳ rotation.
4. **Trust ở bên xác minh có scope:** chỉ chấp nhận issuer, SAN, EKU và policy cần thiết.
5. **Xác thực không thay phân quyền:** mTLS/EAP-TLS hoàn thành mới đến NAC/firewall/IAM/app.
6. **Thay đổi có rollback:** nhất là CA roots, profile và hệ thống cấp phát tập trung.
7. **Có quan sát:** issuance failures, expired cert, certificate validation, abnormal identity use, revocation.

### 20.2. Giới hạn của mô hình CA phân tầng

Một CA tree không bảo đảm cấu hình đã an toàn. Nếu API server chỉ tin root và không xem identity, **mọi chứng thư hợp lệ từ các intermediate được root công nhận** có thể trở thành client không mong đợi. Cần xác định trust policy và authorization **tại mỗi bên nhận**, không chỉ trên sơ đồ.

## 21. Policy-as-code mẫu cho device và workload identity

~~~yaml
# Pseudocode phục vụ thiết kế; không phải cấu hình trực tiếp của CA, SPIRE hay WLC.
pki_identity_policy:
  owner: "Network Security / Platform Security"
  trust_domains:
    devices: "devices.example"
    production_workloads: "prod.example"
    staging_workloads: "staging.example"

  issuing_profiles:
    device_eap_tls:
      issuer: "Device-Issuing-CA"
      key_origin: "hardware-backed-when-supported"
      eku: ["clientAuth"]
      san_source: "verified-device-inventory"
      enrollment: "MDM/UEM-with-approval"
      unique_identity_per_device: true
    workload_mtls:
      issuer: "Workload-Issuing-CA"
      key_origin: "controlled-workload-agent"
      eku: ["clientAuth", "serverAuth"]
      identity_source: "attested-workload-registration"
      san_type: "URI"
      rotation: "automatic-before-expiry"
      unique_identity_per-service-scope: true

  validators:
    eap_tls:
      trusted_issuers: ["Device-Issuing-CA"]
      require_expected_device_identity: true
      map_to_nac_role: true
      default_access: "deny"
    inventory_api:
      trusted_domain: "prod.example"
      require_client_mtls: true
      allowed_callers:
        - "spiffe://prod.example/ns/orders/sa/orders-api"
      default_access: "deny"

  key_management:
    export_private_keys_by_default: false
    never_store_keys_in_source_control: true
    audit_key_access: true

  lifecycle:
    alert_before_expiration: true
    automatic_rotation: true
    revocation_and_session_termination_runbook: true
    trust_bundle_overlap_during_planned_rollover: true

  operations:
    log_certificate_issuance: true
    test_revocation_behavior: true
    review_trust_anchor_scope: true
    require_change_approval: true
~~~

**Lưu ý:** Trong X.509, profile workload vừa làm TLS server vừa làm TLS client có thể cần **EKU serverAuth + clientAuth** theo sản phẩm và policy. Với một số hệ SPIFFE/X.509-SVID, chi tiết EKU và validation theo SPIFFE specification cần được thực thi đúng; không sao chép bảng pseudocode làm chuẩn ràng buộc cho mọi CA.

## 22. Kiểm tra certificate bằng OpenSSL (chỉ đọc)

Các lệnh dưới đây dùng trên file certificate công khai hoặc endpoint được cấp quyền. **Không cần xuất private key, không tắt certificate validation**.

### 22.1. Xem nội dung leaf certificate

~~~bash
# File leaf.crt là PEM certificate của thiết bị/service được phép kiểm tra.
openssl x509 -in leaf.crt -noout -text

# Xem ngày hết hạn
openssl x509 -in leaf.crt -noout -dates

# Xem issuer, subject, serial và fingerprint của chứng thư
openssl x509 -in leaf.crt -noout -issuer -subject -serial -fingerprint -sha256

# Xem SAN nếu phiên bản OpenSSL hỗ trợ -ext
openssl x509 -in leaf.crt -noout -ext subjectAltName
~~~

**Fingerprint SHA-256** giúp nhận diện file certificate trong log/hồ sơ, **không phải một danh tính được phép truy cập ứng dụng**. Cần xác minh chain và SAN/role, không dùng fingerprint thủ công như cơ chế cấp quyền duy nhất nếu không có quy trình lifecycle.

### 22.2. Kiểm tra chain và mục đích

~~~bash
# Trust bundle root-ca.pem, chain intermediate-ca.pem được chuẩn bị theo lab.
# -purpose sslclient/sslserver có semantics PKIX của OpenSSL.
openssl verify -CAfile root-ca.pem \
  -untrusted intermediate-ca.pem -purpose sslclient leaf.crt

openssl verify -CAfile root-ca.pem \
  -untrusted intermediate-ca.pem -purpose sslserver server.crt
~~~

Lệnh trên chỉ là **một phần kiểm tra certificate chain/purpose**, chưa chứng minh server/client có đúng identity kỳ vọng trong ứng dụng. Với server HTTPS, cần kiểm tra **hostname** phù hợp. Với SPIFFE, cần kiểm tra **URI SAN và trust domain** ở thư viện/policy hỗ trợ.

### 22.3. Thử TLS server và hostname

~~~bash
# Quan sát TLS server certificate với SNI và hostname validation.
# Thay service.example.com bằng hostname đã được cấp quyền.
openssl s_client -connect service.example.com:443 \
  -servername service.example.com \
  -verify_hostname service.example.com \
  -verify_return_error </dev/null
~~~

**Không dùng** -verify 0, -k hoặc cấu hình trust-all để kết luận thành công. Nếu kết nối lỗi, hãy kiểm tra hostname, certificate chain, giờ hệ thống, trust store và cấu hình TLS, không tắt validation.

## 23. Kiểm tra luồng mTLS mà không lộ private key

Trong môi trường thật, một mTLS client đôi khi cần certificate **và** private key để thực hiện handshake. Không nên sao chép key production vào laptop điều tra hoặc chat để chạy thử. Nên:

1. Dùng **test workload** được cấp identity test riêng.
2. Quan sát log từ **client/server TLS termination**: peer identity, chain status, SAN/EKU, authorization decision.
3. Sử dụng **identity-aware client** của platform/mesh hoặc integration test có thể dùng key trong agent/HSM mà không cần export.
4. Kiểm tra **đúng caller allow và caller deny** trên endpoint thử nghiệm.
5. Dùng session ID/request ID để đối chiếu TLS handshake với API authorization.

### 23.1. Kịch bản kiểm tra

| Caller | Server | Certificate | Kết quả kỳ vọng |
|---|---|---|---|
| orders/prod | inventory/prod | Valid X.509-SVID, expected ID | mTLS thành công; API có thể allow theo role |
| reporting/prod | inventory/prod | Valid cert nhưng không trong allowlist | TLS có thể xác thực, **authorization deny** |
| orders/staging | inventory/prod | Valid cert ở trust domain staging | Từ chối nếu production không cho trust/role này |
| orders/prod | inventory/prod | Expired leaf | TLS validation fail |
| orders/prod | inventory/prod | Cert sai EKU/SAN theo profile | Validation/identity check fail |
| Không có client certificate | inventory/prod | Server yêu cầu mTLS | Handshake/authentication fail |

**Không tạo sai chứng thư hoặc tấn công handshake vào production để kiểm thử**; dùng staging/lab và thiết bị do tổ chức sở hữu, có phê duyệt test.

## 24. Windows, macOS, mobile và kho chứng thư thiết bị

### 24.1. Windows

Windows Certificate Store có các kho theo **CurrentUser** và **LocalMachine**. Lệnh PowerShell chỉ đọc:

~~~powershell
# Liệt kê certificate ở Personal store của máy hiện tại
Get-ChildItem Cert:\LocalMachine\My |
  Select-Object Subject, Issuer, Thumbprint, NotBefore, NotAfter

# Xem trusted roots của hệ thống (không thêm hay xóa CA)
Get-ChildItem Cert:\LocalMachine\Root |
  Select-Object Subject, Thumbprint, NotAfter

# Lọc những certificate sẽ hết hạn trong thời gian tới
$cutoff = (Get-Date).AddDays(30)
Get-ChildItem Cert:\LocalMachine\My |
  Where-Object { $_.NotAfter -lt $cutoff } |
  Select-Object Subject, NotAfter, Thumbprint
~~~

**Điểm cần lưu ý:** việc có certificate trong store **không bảo đảm private key tương ứng còn khả dụng**, certificate có đúng EKU hoặc thiết bị có role được NAC cho phép. Cần kiểm tra enrollment status, key access và log xác thực hệ thống.

### 24.2. macOS / iOS / Android

Những nền tảng này có **keychain/keystore** và cơ chế quản lý chứng thư riêng. MDM có thể triển khai certificate/trust configuration profile, đôi khi tạo key trên thiết bị hoặc dùng phần cứng bảo mật tùy khả năng. **Không yêu cầu người dùng xuất private key** để khắc phục lỗi Wi-Fi/VPN; dùng diagnostics/MDM logs và profile state theo quy trình.

### 24.3. Device identity không nên dựa trên một trường Subject CN

Một số profile hiển thị Subject CN với tên máy hoặc user, nhưng quản trị viên phải đối chiếu **issuer được phép, SAN/profile, ownership, asset ID và tình trạng enrollment**. Hostname/serial có thể đổi, thiết bị có thể được chuyển giao; cần lifecycle đồng bộ với inventory.

## 25. Cloud và workload identity: tránh long-lived secrets

Cloud cung cấp các cơ chế **managed identity / workload identity / instance role / service-account federation**. Không phải tất cả đều cấp X.509 certificate; nhiều cơ chế cấp **short-lived tokens** để gọi cloud API.

### 25.1. Kết hợp PKI và cloud identity

Ví dụ một workload trên cloud cần:

- Dùng **cloud-native workload identity** để lấy quyền truy cập secret manager hoặc điều khiển cloud API.
- Dùng **mTLS certificate** khi gọi service nội bộ khác.
- Dùng **application authorization** cho yêu cầu người dùng.
- Dùng **network segmentation/security groups** để giới hạn dữ liệu và route.

**Đừng dùng token cloud như certificate TLS** hoặc copy token vào SAN/Subject. Mỗi credential có đối tượng xác minh và threat model riêng.

### 25.2. Rủi ro của metadata/identity endpoint

Nếu workload bị SSRF hoặc một container không có quyền truy cập được metadata/identity endpoint của node, nó có thể lấy credential không thuộc quyền theo sai cấu hình. Cần **IMDS hardening, workload isolation, least privilege và IAM policy**. Certificate/mTLS vẫn có ích để xác thực giữa service, nhưng không chữa được sai cấu hình quyền cloud.

### 25.3. Multi-account/multi-cluster

Khi nhiều cluster hoặc cloud account chia sẻ CA/trust domain, cần xác định identity nào được tin và hành động nào được phép. Không sử dụng một root tin cậy chung như một cách **cho mọi workload cross-cluster truy cập nhau**.

## 26. IoT/OT: certificate khi thiết bị sống lâu và ít kết nối

Thiết bị IoT/OT có vòng đời dài, tài nguyên hạn chế và có thể **offline nhiều tuần/tháng**. Khác với pod Kubernetes chạy vài phút, chúng có thể khó nhận CA bundle hoặc certificate mới.

### 26.1. Các quyết định thiết kế

| Quyết định | Cần cân nhắc |
|---|---|
| **Factory identity** | Nhà sản xuất có cấp danh tính gốc không? Có tin được supply chain không? |
| **Secure element** | Private key có được sinh/lưu không xuất được không? |
| **Bootstrap** | Thiết bị lần đầu kết nối vào fleet thế nào mà không dùng mật khẩu chung? |
| **Certificate TTL** | Chu kỳ online/offline, SLA bảo trì và khả năng tự gia hạn |
| **Trust rollover** | Thiết bị có nhận được trust anchor mới trước khi root cũ hết hạn không? |
| **Recovery** | Nếu cert hết hạn khi offline, có cách khôi phục với quyền đúng không? |
| **Decommission** | Bán/chuyển giao thiết bị có xóa khóa và revoke identity không? |
| **Network restrictions** | Thiết bị chỉ được tới broker/management service theo policy? |

### 26.2. Không chia sẻ một device cert cho cả dây chuyền

Một certificate/key chung cho toàn bộ thiết bị làm khó việc thu hồi một thiết bị mất cắp hoặc bị khai thác. Nếu thiết kế bắt buộc chia sẻ do hạn chế legacy, phải nêu **rủi ro tồn dư, biện pháp bù mạng, lịch chuyển đổi và quyền sở hữu**, không coi đó là giải pháp lý tưởng.

### 26.3. Phòng vệ mạng vẫn cần thiết

Với OT/IoT, mTLS không thay **firewall phân đoạn, NAC, IDS/IPS, DNS policy và giám sát bất thường**. Một camera có cert hợp lệ vẫn không nên kết nối tới database nhân sự hoặc subnet quản trị nếu không có nhu cầu nghiệp vụ.

## 27. Giám sát và audit PKI

### 27.1. Nguồn telemetry

| Nguồn | Dữ liệu cần theo dõi | Mục tiêu |
|---|---|---|
| **CA/Issuer** | issuance/denial, CSR approval, requested SAN, serial, profile, operator | Phát hiện cấp nhầm/không được phép |
| **MDM/NAC/RADIUS** | device cert, EAP-TLS failures, role/VLAN, revocation, posture | Xác định thiết bị nào được vào mạng |
| **VPN** | certificate authentication, user MFA/session, peer identity | Liên kết device và user role |
| **Service mesh/SPIRE** | SVID issued/rotated, workload selector, trust bundle status | Đo identity lifecycle và drift |
| **TLS proxy/API gateway** | certificate validation result, peer identity, policy allow/deny | Kiểm tra mTLS và authorization |
| **Kubernetes** | CSR/cert-manager events, Secret lifecycle, RBAC/audit | Phát hiện cấp/mount cert trái phép |
| **Cloud IAM** | workload token role, instance identity, service permissions | Phân biệt cloud identity và TLS identity |
| **Firewall/NDR/IDS** | source/destination, lateral flows, unusual egress | Giám sát đường mạng ngoài mTLS |
| **Inventory/IPAM/CMDB** | asset owner, service owner, lifecycle state | Phát hiện cert không còn chủ sở hữu |

### 27.2. Metric và alert nên duy trì

- **Số certificate sắp hết hạn** theo owner, issuer, môi trường và ứng dụng; dự báo trước thời gian cần hành động.
- **Certificate renew/rotation failure rate** và thời gian từ issuance tới activation.
- **mTLS handshake failure** phân theo expired, unknown CA, wrong SAN/EKU, client cert missing hoặc policy deny.
- **Identity mismatch** giữa requested SPIFFE ID và attested workload selectors.
- **CA/issuer changes, unauthorized issuance, trust bundle drift**.
- **Revocation latency** từ quyết định thu hồi đến khi các entrypoint ngừng chấp nhận.
- **Tỷ lệ endpoint chấp nhận sai identity** trong bài test negative.
- **EAP-TLS/VPN authentication errors**, kèm tỷ lệ user-facing network availability.
- **Tỷ lệ workload/thiết bị dùng shared key/cert ngoài policy**.

**Ít TLS error không chứng minh policy đúng**: một server **không kiểm tra client certificate** hoặc **tin mọi client certificate dưới một CA** có thể tạo rất ít lỗi nhưng vẫn thiếu bảo vệ.

### 27.3. Tránh lộ dữ liệu nhạy cảm trong log

Không lưu private key, passphrase, bootstrap token, PKCS#12 có private key, JWT token hay CSR secret vào log. Chỉ lưu metadata cần thiết: **issuer, serial, fingerprint, SAN identity đã được duyệt, certificate expiry, policy decision và session ID** theo retention/quyền truy cập của tổ chức.

## 28. Runbook triển khai certificate cho thiết bị và workload

### Bước 1 — Inventory và phân loại

Lập danh sách thiết bị, workload, service, TLS endpoint, CA, trust store, profile, owner, lifecycle, environment, secret storage và network zone. Phân biệt public Web PKI, device EAP-TLS/VPN và workload mTLS.

### Bước 2 — Xác định trust boundary

Chọn CA/trust domains riêng theo mức rủi ro, xác định **đúng identity được phép** và yêu cầu SAN/EKU. Chỉ các bên có quyền mới được đăng ký hostname, device ID hoặc SPIFFE ID.

### Bước 3 — Thiết kế bootstrap và issuance

Chọn MDM/EST/SCEP/ACME/cert-manager/SPIRE theo đối tượng. Bảo vệ private key tại endpoint, dùng attestation/approval phù hợp và giới hạn quyền CA.

### Bước 4 — Cấu hình verifier và authorization

Trên Wi-Fi/VPN, client/server kiểm tra identity và chain đúng; NAC/gateway gắn role. Trên workload, client/server mTLS kiểm tra **exact service identity**, sau đó authorization áp ở API/proxy. Cài firewall/microsegmentation tương ứng.

### Bước 5 — Pilot có kiểm thử âm tính

Thử certificate hợp lệ **đúng role** và certificate hợp lệ **sai role/trust domain**. Thử cert hết hạn, thiếu client cert, server cert hostname sai, CA không tin cậy và rotation. Không đưa test credential vào production ngoài kế hoạch được duyệt.

### Bước 6 — Triển khai có canary/rollback

Phân phối trust bundle, cert và chính sách ở các điểm xác minh theo thứ tự bảo đảm overlap an toàn. Theo dõi EAP-TLS, VPN, mTLS handshake, request success, error budget và IAM decisions.

### Bước 7 — Tự động hóa và hậu kiểm

Thiết lập renewal/rotation, revocation, trust bundle rollover, decommission, sự cố key compromise, owner review và audit. Kiểm tra regression sau nâng cấp mesh, cloud, CA, MDM, VPN hoặc gateway.

~~~mermaid
flowchart TD
    A[Inventory + roles + trust domains] --> B[Issuance policy + key protection]
    B --> C[Deploy trust bundles + enrollment]
    C --> D[Test chain/SAN/EKU + positive/negative authorization]
    D --> E{All critical clients work and unauthorized clients denied?}
    E -- No --> F[Fix profile/issuer/verifier; rollback if needed]
    F --> C
    E -- Yes --> G[Canary rollout + monitoring]
    G --> H[Auto renewal/rotation + incident drills]
    H --> I[Decommission, audit, drift review]
    I --> A
~~~

## 29. Runbook khi certificate bị lộ hoặc cấp nhầm

### Tình huống giả định

SOC phát hiện một **workload identity** có thể đã bị dùng từ một node ngoài vùng chạy được phép. Đồng thời service inventory ghi nhận một caller hợp lệ về mặt certificate nhưng không thuộc nhóm service được phép gọi API nhạy cảm.

### Giai đoạn 1 — Xác minh và khoanh vùng

1. Xác định **issuer, serial, SAN/SPIFFE ID, key ID nếu có, thời gian, workload/host** và người sở hữu.
2. Kiểm tra log CA/issuer, node attestation, workload registration, API gateway và mTLS session.
3. Xác định certificate còn hạn, có bị copy, access key/HSM có bị lộ hay chỉ là **authorization policy sai**.
4. Tìm các session/flows đã dùng identity đó, không mặc định mọi request đều gây truy cập dữ liệu.
5. Giữ bằng chứng theo quy trình, **không sao chép private key nghi lộ sang máy điều tra**.

### Giai đoạn 2 — Ngăn tái sử dụng credential

- **Cô lập workload/thiết bị** theo phạm vi có thể mà không gây sự cố diện rộng.
- **Thu hồi hoặc từ chối identity/certificate** tại issuer/gateway/authorization layer theo khả năng.
- **Ngăn cấp lại** danh tính do attestation/enrollment policy lỗi.
- **Xoay private key/certificate** với key mới và cập nhật trust/policy theo cần thiết.
- **Kết thúc session** hoặc buộc reauthentication khi nền tảng hỗ trợ.
- Nếu một intermediate/root CA bị nghi bị xâm nhập, kích hoạt **CA compromise plan**, không chỉ revoke một leaf.

### Giai đoạn 3 — Xác minh

Test các luồng **đúng identity được allow**, cert sai danh tính bị deny, cert cũ đã bị chặn theo chiến lược revocation và service SLI vẫn hoạt động. Kiểm tra endpoint/mTLS proxy không **fail open** hoặc bỏ qua client certificate khi hệ thống identity service ngừng hoạt động.

### Giai đoạn 4 — Hậu kiểm

Xác định lỗi ở **key exposure, insecure Secret, issuance rights, registration selector, SAN validation, trust bundle quá rộng hay application authz**. Gắn owner và thời hạn khắc phục, bổ sung test negative, rotation và audit.

## 30. Những tình huống chẩn đoán thực tế

### Tình huống A — Laptop có cert nhưng không vào được Wi-Fi EAP-TLS

**Triệu chứng:** máy đã nhận device cert từ MDM nhưng RADIUS báo xác thực thất bại.

**Hướng điều tra:** kiểm tra certificate còn hạn, key có dùng được không, EKU/clientAuth và SAN/profile, trust của EAP server trên laptop, trust của device CA trên RADIUS, trạng thái revocation và NAC authorization. **Đừng tắt server certificate validation** để giải quyết.

### Tình huống B — Service có cert đúng CA nhưng gọi API bị deny

**Triệu chứng:** orders có cert dưới workload CA, TLS bắt tay thành công, API inventory trả 403.

**Phân tích:** Đây có thể là **authorization deny đúng**: orders không nằm trong caller allowlist hoặc hành động cụ thể không được cấp quyền. Xác minh exact SPIFFE ID, environment và API policy trước khi mở rule.

### Tình huống C — Pod restart liên tục sau rotation

**Triệu chứng:** cert-manager/SPIRE phát certificate mới, nhưng pod ứng dụng vẫn sử dụng cert cũ và hết hạn.

**Phân tích:** Kiểm tra cơ chế volume update, proxy reload, application TLS context caching, file watch và sự khác biệt giữa Secret được cập nhật với **process đã nạp khóa/cert vào bộ nhớ**. Sửa rotation integration và kiểm thử pod scaling/failover.

### Tình huống D — Trust bundle của staging vô tình vào production

**Triệu chứng:** production API chấp nhận mTLS từ workload staging.

**Phân tích:** Xác minh trust bundles và authorization. **Chỉ cùng CA hoặc có chain hợp lệ không đủ** để cho staging gọi production; giới hạn trust domain và exact service identity.

### Tình huống E — Cert còn hạn nhưng client báo unknown CA

**Triệu chứng:** certificate valid theo ngày tháng, nhưng trình duyệt/mesh báo không tin issuer.

**Phân tích:** Root/intermediate mới chưa được phân phối hoặc server không gửi đủ intermediate chain; cũng có thể client đúng khi từ chối CA ngoài chính sách. Kiểm tra chain và trust store, không "tin mọi certificate".

### Tình huống F — Thiết bị IoT bị mất, certificate còn nhiều tháng

**Triệu chứng:** một camera/IoT device không còn thuộc quản lý nhưng device cert chưa hết hạn.

**Phân tích:** Cần revoke/deny tại broker, chấm dứt session, cập nhật inventory, khóa issuance lại và điều tra key compromise; không chỉ chờ tới ngày hết hạn.

### Tình huống G — Hai microservice dùng chung private key

**Triệu chứng:** để đơn giản hóa CI, đội ứng dụng mount cùng PFX vào hai môi trường.

**Phân tích:** Không thể phân biệt service đúng dựa trên cert, mất một workload ảnh hưởng cả hai. Chuyển sang danh tính riêng, issuance tự động, hạn chế Secret/RBAC, rotate shared key và thu hồi theo policy.

### Tình huống H — mTLS từ client tin cậy nhưng user chưa được phép

**Triệu chứng:** API chỉ kiểm tra mTLS client certificate, sau đó xử lý mọi request đọc dữ liệu user khác.

**Phân tích:** Workload mTLS xác thực **dịch vụ gọi**, không thay user/tenant/object authorization. Cần xác thực và phân quyền dữ liệu ở tầng ứng dụng, ngăn kiểu lỗi BOLA/IDOR.

### Tình huống I — RADIUS server cert thay mới gây lỗi trên một nhóm laptop

**Triệu chứng:** cert mới được thay trên RADIUS, một số máy không thể kết nối Wi-Fi.

**Phân tích:** Device profile chỉ tin issuing CA cũ, expected server name bị đổi hoặc thiếu intermediate trong chain; cần trust bundle rollout và cấu hình tên server chính xác trước khi chuyển đổi. Không nới chính sách xác thực server toàn fleet.

### Tình huống J — Cert rất ngắn hạn nhưng CA không khả dụng

**Triệu chứng:** nhiều workload đồng loạt mất khả năng gia hạn, mTLS failures tăng khi cert hết hạn.

**Phân tích:** Short-lived cert giảm thời gian bị lạm dụng nhưng làm tăng phụ thuộc vào issuer. Thiết kế CA HA, monitoring renewal lead time, retry/backoff và emergency recovery có kiểm soát; không chấp nhận expired certificate bằng trust-all.

## 31. Ma trận kiểm thử an toàn

Tất cả phép thử dùng **lab hoặc tài sản/test identity được tổ chức sở hữu và phê duyệt**. Không thử xin chứng thư cho danh tính người khác, không xuất khóa riêng production và không tắt TLS validation để tạo kết quả "xanh".

| ID | Bối cảnh | Kết quả mong đợi | Bằng chứng |
|---|---|---|---|
| **T-01** | Device EAP-TLS với cert hợp lệ, đúng profile | Xác thực thành công, NAC áp đúng VLAN/role | RADIUS/MDM/port logs |
| **T-02** | Device cert hết hạn | Không được chấp nhận như identity hợp lệ | EAP-TLS validation error |
| **T-03** | EAP server cert sai tên/trust | Client từ chối server theo policy | Supplicant logs |
| **T-04** | Thiết bị đã revoke, session mới | Bị từ chối theo revocation strategy | Gateway/CA logs |
| **T-05** | VPN client cert hợp lệ nhưng user thiếu MFA | Access bị từ chối theo MFA policy | IdP/VPN log |
| **T-06** | VPN device hợp lệ, role Employee vào Management | Deny do network authorization | Firewall log |
| **T-07** | Orders/prod → Inventory/prod mTLS | Xác thực hai phía và allow đúng API | Mesh/API logs |
| **T-08** | Reporting/prod có valid cert nhưng không được gọi API | Authorization deny | Exact identity/policy log |
| **T-09** | Orders/staging → Inventory/prod | Bị deny nếu không có trust/allow rõ ràng | Trust domain + deny log |
| **T-10** | Client cert thiếu/wrong EKU | Verification fail theo profile | TLS/server logs |
| **T-11** | Server cert wrong DNS SAN | Client từ chối hostname | TLS verification error |
| **T-12** | Workload URI SAN không khớp expected identity | Client/server từ chối | Peer identity validation |
| **T-13** | Server dùng trust bundle không đúng | Fail có kiểm soát, không fallback trust-all | Proxy/application log |
| **T-14** | Certificate được rotation trước hạn | Service không gián đoạn, cert mới được nạp | Issuer, proxy/app logs |
| **T-15** | Certificate mới cấp nhưng process vẫn dùng cert cũ | Có alert hoặc cơ chế reload/rollout đúng | Process TLS state, cert expiry |
| **T-16** | Root/intermediate migration có overlap | Client cũ/mới phù hợp vẫn hoạt động trong giai đoạn đổi | Trust bundle diff và handshake |
| **T-17** | Thay CA khi client chưa nhận trust mới | Nhận diện và ngăn rollout gây outage | Canary failure và rollback |
| **T-18** | Revoked cert với session đang mở | Session được xử lý theo IR runbook | Session terminate/audit |
| **T-19** | Attempt xin certificate ngoài identity scope trong lab | Issuer/approver từ chối | Request/approval audit |
| **T-20** | Workload không đạt attestation được yêu cầu | Không nhận SVID/credential | Attestation failures |
| **T-21** | Một pod không được phép đọc Secret của pod khác | RBAC deny | Kubernetes audit |
| **T-22** | CA/issuer tạm outage trong lab | Alert đủ sớm, service xử lý theo SLO và runbook | Issuance metrics |
| **T-23** | Dual-stack IPv4/IPv6 với cùng mTLS endpoint | Xác minh đúng identity dù IP khác nhau | TLS logs, route, network policy |
| **T-24** | Partner trust domain federation | Chỉ identity partner đã phê duyệt được allow | Trust/authorization logs |
| **T-25** | Device decommission | Key/cert/trust access được thu hồi theo policy | CMDB/MDM/CA audit |
| **T-26** | Shared certificate/key ngoài policy | Inventory/alert phát hiện, có plan tách identity | Fingerprint + owner audit |
| **T-27** | CA được thêm vào trust store trái change | Drift detection cảnh báo | Trust store inventory |
| **T-28** | mTLS hợp lệ nhưng user không có quyền dữ liệu | Application trả 403/deny đúng | User/tenant authz log |
| **T-29** | Renew certificate trong điều kiện clock skew lab | Phát hiện time issue, không bỏ validation | NTP, notBefore/notAfter |
| **T-30** | Network policy giữa workload | Chỉ luồng cần thiết tới được endpoint | Firewall/service mesh flow logs |

### 31.1. Test cần cả allow và deny

Đừng chỉ kiểm tra một certificate hợp lệ kết nối thành công. **Negative tests** như "certificate hợp lệ nhưng sai role", "đúng CA nhưng sai URI SAN" và "service không nằm trong allowlist" giúp phát hiện chính sách **trust-all dưới một root** hoặc authorization bị bỏ qua.

### 31.2. Không kết luận từ một OpenSSL verify OK

Một certificate được OpenSSL xác nhận chain hợp lệ **chưa chắc được dùng đúng identity, EKU, hostname, trust domain hoặc authorization** của hệ thống thật. Cần đo ở **verifier thực tế** và dữ liệu mạng/application.

## 32. Những ngộ nhận thường gặp

| Ngộ nhận | Sửa lại cho đúng |
|---|---|
| **"Certificate chứa cả private key."** | Certificate chứa public key; private key được giữ riêng. |
| **"Có cert từ CA nội bộ là truy cập được mọi service."** | Phải kiểm tra exact identity và authorization. |
| **"Device cert đồng nghĩa user đã được xác thực."** | Device và user là hai danh tính khác nhau. |
| **"Xác minh chain đủ để biết đúng server."** | Cần SAN/expected hostname/URI và mục đích phù hợp. |
| **"CN là cách xác thực tên TLS hiện đại duy nhất."** | SAN là thành phần trung tâm của hostname/identity verification. |
| **"mTLS tự thay API authorization."** | mTLS xác thực endpoint/service, không phân quyền dữ liệu nghiệp vụ. |
| **"Một cert có thể chia sẻ cho tất cả pod."** | Shared key làm tăng blast radius và mất khả năng thu hồi riêng. |
| **"Cert sống ngắn thì không cần revoke session."** | Key bị lộ vẫn có thể dùng trước expiry và session có thể tiếp tục. |
| **"Mọi TLS library tự kiểm tra CRL/OCSP."** | Phải xác minh khả năng và policy thực tế của client/server. |
| **"Renew cert tự làm app reload cert mới."** | Process/proxy có thể giữ cert cũ trong bộ nhớ. |
| **"Đổi CA chỉ cần cấp leaf mới."** | Phải phân phối trust bundle và kiểm tra verifier trước. |
| **"CSR ghi SAN nào thì CA nên cấp SAN đó."** | CA/enrollment service phải xác minh quyền nhận identity. |
| **"Kubernetes service account luôn là X.509 cert."** | Service account thường gắn token; X.509 workload identity cần cơ chế riêng. |
| **"Cloud managed identity luôn trả certificate TLS."** | Nhiều cơ chế cloud cấp token để gọi API. |
| **"SPIFFE ID trong URI SAN nghĩa là service tự được quyền gọi mọi nơi."** | Cần trust domain validation và explicit service authorization. |
| **"EAP-TLS chỉ cần client cert; server cert không quan trọng."** | Supplicant phải xác minh đúng EAP server identity/certificate. |
| **"PKI hoạt động thì không cần firewall/NAC."** | PKI là một lớp xác thực, không thay segmentation và access policy. |
| **"Không có TLS error nghĩa là an toàn."** | Có thể hệ thống không kiểm tra đúng peer identity hoặc thiếu mTLS. |

## 33. Checklist đưa certificate system vào production

- [ ] Phân loại đúng **device certificate, workload identity, server TLS, VPN, EAP-TLS, public/private PKI**.
- [ ] Có owner cho mỗi CA, issuing profile, certificate, service và device fleet.
- [ ] Biết **trust anchor, intermediate, trust bundle và SAN identity** được phép tại từng verifier.
- [ ] Root/intermediate key được bảo vệ bằng HSM/hardware hoặc cơ chế tương xứng, có audit.
- [ ] Leaf có **Basic Constraints, KU/EKU, SAN, signature algorithm** đúng profile.
- [ ] CA không cấp certificate chỉ theo CSR tự khai, có attestation/approval phù hợp.
- [ ] Device enrollment được ràng buộc MDM/UEM/inventory, không dùng shared cert chung.
- [ ] Laptop EAP-TLS kiểm tra **EAP server certificate/name** và RADIUS kiểm tra client identity đúng.
- [ ] VPN dùng xác thực device/user và MFA/posture theo rủi ro, không cấp whole-network access sau TLS.
- [ ] Workload mTLS xác minh chính xác service identity/URI SAN, không chỉ chain hợp lệ.
- [ ] Trust domain production/staging/partner được giới hạn theo policy, federation có owner.
- [ ] Service-to-service authorization áp tại proxy/API và được kiểm thử negative.
- [ ] Certificate/private key không được lưu trong git/image/log/ticket; keystore/Secret có RBAC phù hợp.
- [ ] Kubernetes/cert-manager/SPIRE issuance scope và identity registration được review.
- [ ] Có **auto renewal/rotation**, kiểm tra app thực sự reload certificate mới trước expiry.
- [ ] Có alert cho expiration, issuance failure, handshake error và trust bundle drift.
- [ ] Có revocation strategy rõ cho thiết bị offline, CA outage, short-lived cert và session đang mở.
- [ ] CA/trust bundle rotation có overlap, canary, rollback và test đa nền tảng.
- [ ] Có quy trình device decommission, workload deletion, role revocation và key destruction.
- [ ] Network segmentation/firewall/NAC/IDS vẫn giới hạn đường đi và quyền theo zone.
- [ ] Không dùng -k/--insecure hoặc trust-all để xử lý nhanh production TLS errors.
- [ ] Có log issuer, serial/fingerprint, identity, policy decision, owner và thời điểm.
- [ ] Audit issuance/quyền cấp, trust anchors, private key access và các ngoại lệ theo lịch.
- [ ] Test cả **đường được allow lẫn identity/certificate phải bị deny**, bao gồm IPv4/IPv6 và failover.
- [ ] Có runbook xử lý key compromise, revoked device, certificate outage và CA compromise.

## 34. Câu hỏi tự kiểm tra

**1. Certificate X.509 chứa private key không?**  
Không. Certificate chứa public key và thông tin có chữ ký. Private key được lưu riêng và phải được endpoint bảo vệ.

**2. Device certificate khác user certificate ở điểm nào?**  
Device certificate xác thực một thiết bị/instance theo enrollment policy; user certificate xác thực user principal theo một PKI profile khác. Thiết bị được xác thực không tự đồng nghĩa người dùng đã được cấp quyền.

**3. Có chain tới root CA tin cậy đã đủ cho mTLS không?**  
Chưa. Cần validity, KU/EKU, SAN/identity phù hợp, proof-of-possession và **authorization** đúng với caller/destination.

**4. Vì sao EAP-TLS supplicant phải xác minh RADIUS/EAP server certificate?**  
Để không cung cấp quá trình xác thực cho một server giả/không được tin cậy. Kiểm tra phải bao gồm trust anchor và server identity mong đợi.

**5. Vì sao service identity nên tách khỏi pod IP?**  
Pod/IP có thể thay đổi và được tái cấp, còn identity đại diện vai trò/service được xác minh theo workload context.

**6. SPIFFE ID có nghĩa gì?**  
Đó là URI định danh workload trong một trust domain, thường được đưa vào X.509-SVID URI SAN hoặc dùng trong JWT-SVID theo đặc tả tương ứng.

**7. SPIRE có tự quyết định mọi service được phép gọi nhau không?**  
Không. SPIRE có thể cấp identity sau attestation, nhưng authorization phải được thực thi bởi service mesh/API proxy hoặc ứng dụng theo policy.

**8. cert-manager đã renew Secret nhưng service vẫn lỗi expiry, vì sao?**  
Ứng dụng/proxy có thể chưa reload certificate/key mới hoặc Secret không được mount/update như thiết kế.

**9. Certificate ngắn hạn có thay toàn bộ revocation không?**  
Không. Nó giới hạn thời hạn credential nhưng không tự ngắt session hiện tại hoặc chặn cấp lại identity đã bị lộ.

**10. CRL/OCSP có mặc định được mọi TLS client kiểm tra không?**  
Không. Cần đánh giá library, sản phẩm, đường truy cập và fail-open/fail-closed policy.

**11. Vì sao thay root CA có thể gây outage diện rộng?**  
Verifier chưa nhận trust anchor mới sẽ từ chối leaf/chain mới; cần phân phối bundle, overlap và canary đúng thứ tự.

**12. Vì sao không nên dùng một client cert chung cho toàn bộ fleet IoT?**  
Lộ một private key ảnh hưởng tất cả thiết bị và khó thu hồi/cô lập từng thiết bị.

**13. Valid cert nhưng gọi API bị 403 có phải TLS bị lỗi không?**  
Không nhất thiết. TLS có thể xác thực hợp lệ, nhưng application authorization từ chối vì caller/user không có quyền thực hiện hành động.

**14. Public HTTPS cert và workload cert có thể thay nhau không?**  
Không nên mặc định. Chúng có đối tượng xác minh, SAN, EKU, CA và lifecycle khác nhau; cần profile và trust policy riêng theo thiết kế.

**15. Nếu private key bị lộ, hành động nào quan trọng?**  
Khoanh vùng, revoke/deny identity theo policy, rotate khóa mới, ngắt session nếu cần, chặn issuance trái phép, điều tra phạm vi truy cập và khắc phục nguyên nhân lộ.

## 35. Tài liệu tham khảo

- [RFC 5280 — Internet X.509 Public Key Infrastructure Certificate and CRL Profile](https://www.rfc-editor.org/rfc/rfc5280): cấu trúc, chain/path validation, Basic Constraints, SAN, KU/EKU và CRL.
- [RFC 8446 — The Transport Layer Security (TLS) Protocol Version 1.3](https://www.rfc-editor.org/rfc/rfc8446): TLS 1.3, certificate authentication và bảo vệ kênh.
- [RFC 5216 — The EAP-TLS Authentication Protocol](https://www.rfc-editor.org/rfc/rfc5216): khái niệm EAP-TLS truyền thống.
- [RFC 9190 — EAP-TLS 1.3: Using the Extensible Authentication Protocol with TLS 1.3](https://www.rfc-editor.org/rfc/rfc9190): EAP-TLS 1.3 và mô hình chứng thực client/server.
- [RFC 7030 — Enrollment over Secure Transport (EST)](https://www.rfc-editor.org/rfc/rfc7030): mô hình enrollment certificate qua TLS.
- [RFC 8555 — Automatic Certificate Management Environment (ACME)](https://www.rfc-editor.org/rfc/rfc8555): issuance/renewal tự động theo quy trình validation.
- [RFC 6960 — X.509 Internet Public Key Infrastructure Online Certificate Status Protocol (OCSP)](https://www.rfc-editor.org/rfc/rfc6960): truy vấn trạng thái certificate.
- [RFC 8894 — Simple Certificate Enrolment Protocol (SCEP)](https://www.rfc-editor.org/rfc/rfc8894): enrollment certificate qua SCEP.
- [SPIFFE — Concepts](https://spiffe.io/docs/latest/spiffe-about/overview/): định danh workload, SPIFFE ID, SVID và trust bundle.
- [SPIRE — Documentation](https://spiffe.io/docs/latest/spire-about/spire-concepts/): node/workload attestation, workload API và issuance.
- [Kubernetes — Certificates and Certificate Signing Requests](https://kubernetes.io/docs/reference/access-authn-authz/certificate-signing-requests/): CSR, approver/signer và certificate management trong cluster.
- [cert-manager — Documentation](https://cert-manager.io/docs/): tự động cấp, gia hạn và quản lý certificate qua Issuer.
- [NIST SP 800-57 Part 1 Rev. 5 — Recommendation for Key Management](https://csrc.nist.gov/pubs/sp/800/57/pt1/r5/final): vòng đời khóa mật mã và bảo vệ khóa.
- [NIST SP 800-207 — Zero Trust Architecture](https://csrc.nist.gov/pubs/sp/800/207/final): identity, chính sách phân quyền và giảm implicit trust theo mạng.
- [NIST SP 800-53 Rev. 5 — Security and Privacy Controls for Information Systems and Organizations](https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final): tham chiếu quản trị kiểm soát access, audit và key management.

**Ghi nhớ:** Certificate cho thiết bị và workload cung cấp một cách xác thực danh tính máy có thể tự động hóa, nhưng chỉ an toàn khi **issuance kiểm tra đúng chủ thể, private key được bảo vệ, verifier kiểm tra đúng chain/SAN/EKU/trust domain, và authorization giới hạn đúng dịch vụ**. Hãy xem PKI như một **hệ thống vòng đời** gồm enrollment, renewal, rotation, revocation, audit và decommission; kết hợp **mTLS, EAP-TLS/VPN, NAC, firewall, microsegmentation, IAM và giám sát** để bảo vệ mạng nhiều lớp.
