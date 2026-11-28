# Xác định trust boundary trước khi chọn công cụ

## 1. Vì sao kiến trúc bảo mật phải bắt đầu từ ranh giới tin cậy?

Khi thiết kế mạng an toàn, câu hỏi đầu tiên không nên là “mua firewall nào?”, “có cần service mesh không?” hay “chọn VPN hay Zero Trust?”. Câu hỏi đúng hơn là: **những chủ thể nào được phép tương tác với tài sản nào, với loại dữ liệu nào, qua ranh giới nào và trong điều kiện nào?**

**Trust boundary** (ranh giới tin cậy) là vị trí logic hoặc vật lý mà tại đó một yêu cầu, dữ liệu hay chủ thể chuyển từ **ngữ cảnh tin cậy này** sang **ngữ cảnh có giả định, mức bảo đảm hoặc quyền hạn khác**. Tại điểm chuyển giao, hệ thống cần xác định lại những điều không được phép mặc định tin tưởng: danh tính, nguồn gốc, tính toàn vẹn, thẩm quyền, loại dữ liệu và hành vi được phép.

Trong chương **Quyết định kiến trúc bảo mật mạng** thuộc mô-đun **SECURITY_NETWORK_SECURITY**, việc xác định trust boundary là cơ sở lựa chọn và phối hợp phân đoạn mạng, firewall, VPN, IDS/IPS, DNS security, bảo vệ Wi-Fi, mTLS, WAF, dịch vụ định danh và chính sách trong cloud. Chọn công cụ trước khi hiểu ranh giới thường dẫn tới:

- Có firewall mạnh ở Internet edge nhưng luồng giữa các workload nội bộ lại quá rộng.
- Có VPN mã hóa nhưng mặc định tin toàn bộ người dùng sau khi vào mạng.
- Có WAF ở API public nhưng đường quản trị hoặc endpoint nội bộ truy cập trực tiếp được origin.
- Có security group nhưng không xác minh traffic qua NAT, proxy, overlay hoặc service mesh.
- Có nhiều sản phẩm an ninh mà không rõ lớp nào ra quyết định **cho phép**, lớp nào chỉ **quan sát** và ai chịu trách nhiệm kiểm chứng.

**Mục tiêu bài học:** nhận diện boundary từ tài sản và luồng nghiệp vụ; mô hình hóa đối tượng và giả định tin cậy; chọn kiểm soát đúng chức năng; làm rõ quyền thực thi, phát hiện và quan sát; ghi nhận trade-off trong quyết định kiến trúc; thiết kế phép kiểm thử chứng minh boundary được áp dụng như kỳ vọng.

## 2. Những khái niệm cần phân biệt

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Trust domain** | Phạm vi cùng chia sẻ một bộ giả định và cơ chế bảo đảm nhất định | Một workload identity domain với cùng chính sách cấp danh tính |
| **Trust boundary** | Điểm chuyển giữa hai ngữ cảnh có yêu cầu xác minh khác nhau | Internet → API gateway; workload → database |
| **Security zone** | Nhóm tài sản được áp một tập chính sách mạng | GUEST, APP, DATABASE, ADMIN |
| **Asset / crown jewel** | Tài sản hoặc dữ liệu cần bảo vệ, theo mức tác động nghiệp vụ | Hệ thống thanh toán, dữ liệu định danh khách hàng |
| **Principal / identity** | Chủ thể được xác thực để yêu cầu tài nguyên | User, service account, workload, thiết bị |
| **Policy enforcement point (PEP)** | Điểm thực thi allow/deny hoặc giới hạn hành động | Firewall, API gateway, proxy, workload policy |
| **Policy decision point (PDP)** | Thành phần đánh giá điều kiện truy cập theo chính sách | Authorization service, IAM policy engine |
| **Control plane** | Nơi thay đổi, phân phối hoặc điều phối cấu hình và chính sách | Cloud API, Kubernetes API, SDN controller |
| **Data plane** | Nơi traffic ứng dụng thực tế được chuyển tiếp hoặc xử lý | Router, load balancer, service-to-service path |
| **Management plane** | Giao diện quản trị và giám sát hệ thống | SSH, API quản trị, bastion, NMS |
| **Attack surface** | Những điểm tương tác có thể bị lạm dụng | Listener, API, admin endpoint, trust relationship |

**Trust boundary không đồng nghĩa VLAN, subnet, firewall hoặc một đường kẻ trên sơ đồ.** Một VLAN là công cụ tổ chức mạng; bên trong cùng VLAN vẫn có thể tồn tại nhiều identity và mức tin cậy khác nhau. Ngược lại, một boundary ứng dụng có thể nằm **bên trong cùng một máy hoặc một pod**, nơi traffic qua loopback không đi qua network firewall bên ngoài.

### 2.1. “Trusted network” không có nghĩa mọi thành phần đều đáng tin

Một gói tin đến từ subnet nội bộ không chứng minh người gửi đã được xác thực, được phép gọi API hay đang sử dụng thiết bị an toàn. IP nguồn có thể thay đổi qua DHCP/NAT, proxy có thể che nguồn gốc, và một workload nội bộ vẫn có thể bị xâm nhập.

Trong thiết kế hướng **Zero Trust**, không có quyền truy cập chỉ vì vị trí mạng thuận tiện: hệ thống xác minh rõ ràng danh tính và điều kiện truy cập, cấp quyền tối thiểu và đánh giá liên tục khi phù hợp. Điều này **không loại bỏ nhu cầu phân đoạn mạng**; network segmentation và identity-aware authorization là các lớp bổ sung, không thay thế hoàn toàn cho nhau.

## 3. Bắt đầu từ tài sản, dữ liệu và tác động nghiệp vụ

Trước khi chọn điểm đặt firewall hoặc gateway, hãy lập một danh sách đủ thực tế:

| Câu hỏi | Thông tin nên thu |
| --- | --- |
| Chức năng nào là trọng yếu? | Luồng đặt hàng, thanh toán, xác thực, quản trị, sao lưu |
| Tài sản nào xử lý chúng? | API, queue, database, DNS, identity provider, VPN, certificate authority |
| Dữ liệu có mức nhạy cảm nào? | Công khai, nội bộ, bí mật, dữ liệu được quản lý bởi quy định cụ thể |
| Ai được truy cập? | Người dùng cuối, nhân viên, nhà thầu, ứng dụng, job tự động |
| Tác động nếu bị truy cập trái phép? | Rò rỉ thông tin, sửa giao dịch, nâng quyền |
| Tác động nếu bị gián đoạn? | Mất doanh thu, không thể đăng nhập, mất quyền quản trị |
| Chủ sở hữu là ai? | Business owner, service owner, IAM owner, network owner |
| RTO/RPO hoặc yêu cầu phục hồi? | Thời hạn gián đoạn và mức mất dữ liệu chấp nhận được |

Một thiết bị có vai trò nhỏ về lưu lượng nhưng tác động lớn về quyền quản trị có thể quan trọng hơn nhiều server ứng dụng. Ví dụ **PKI, IdP, DNS authoritative, VPN gateway và cloud organization administrator** là các phụ thuộc chung; xâm nhập hoặc lỗi ở chúng có thể ảnh hưởng nhiều trust domain.

### 3.1. Phân loại luồng theo dữ liệu, không chỉ theo cổng

Hai request cùng đi qua TCP/443 có thể khác hẳn rủi ro: một request lấy ảnh công khai, một request chỉnh quyền người dùng hoặc tải dữ liệu khách hàng. Vì vậy, ma trận boundary cần ghi **mục đích nghiệp vụ, loại thao tác và phân quyền ứng dụng**, không chỉ source IP, destination IP và port.

Ví dụ:

| Luồng | Dữ liệu/hành động | Mức rủi ro |
| --- | --- | --- |
| Người dùng → public catalog API | Đọc thông tin công khai | Thường thấp hơn các thao tác có quyền |
| Người dùng → orders API | Tạo đơn, thay đổi trạng thái nghiệp vụ | Cần xác thực và ủy quyền theo đối tượng |
| Payment service → payment database | Ghi trạng thái giao dịch | Quyền cao, yêu cầu giới hạn chính xác |
| Quản trị viên → firewall management API | Thay đổi phân đoạn toàn mạng | Nhạy cảm cao dù số request rất ít |
| Backup service → repository | Đọc hoặc ghi bản sao cấu hình có secret | Nhạy cảm về bí mật, tính toàn vẹn và phục hồi |

## 4. Lập bản đồ luồng dữ liệu trước khi đặt ranh giới

Một **data-flow diagram (DFD)** hữu ích hơn sơ đồ chỉ liệt kê các ô thiết bị vì nó diễn tả **chủ thể, dữ liệu, hướng đi và nơi có quyết định tin cậy**.

~~~mermaid
flowchart LR
    U[Người dùng Internet] --> E[Public DNS / Edge]
    E --> W[WAF / Reverse proxy]
    W --> A[Order API]
    A --> P[Payment service]
    P --> D[(Payment database)]
    A --> Q[(Order database)]
    I[Identity provider] -. Cấp và xác thực danh tính .-> A
    I -. Workload identity .-> P
    O[Admin qua MFA] --> B[Bastion / Privileged access]
    B --> M[Management plane]
    M -. Cấu hình và chính sách .-> W
    M -. Cấu hình và chính sách .-> A
    T[Telemetry] -. Thu sự kiện .-> W
    T -. Thu sự kiện .-> P
~~~

Các trust boundary chính có thể là:

1. **B1 — Internet → Edge:** khách chưa xác thực đến dịch vụ public.
2. **B2 — Edge → Ứng dụng:** proxy chuyển request, có thể thay đổi IP, TLS và header.
3. **B3 — Service → Service:** ứng dụng gọi dịch vụ có quyền nghiệp vụ khác.
4. **B4 — Service → Database:** chuyển sang tài nguyên có dữ liệu nhạy cảm.
5. **B5 — Admin → Management plane:** chủ thể đặc quyền thay đổi cấu hình hoặc chính sách.
6. **B6 — Workload → Identity/PKI:** yêu cầu cấp hoặc xác minh danh tính và chứng chỉ.
7. **B7 — Workload → Telemetry/Backup:** chuyển dữ liệu vận hành có thể chứa secrets hoặc thông tin nhạy cảm.

Đây là **bản đồ logic**, chưa khẳng định đường đi packet vật lý. Bước tiếp theo là thêm subnet, VPC/VNet, VLAN/VRF, NAT, proxy, VPN, service mesh và các giao diện thực thi vào từng nhánh.

### 4.1. Mỗi mũi tên là một câu hỏi bảo mật

Đối với từng luồng, ghi:

- **Ai chủ động?** User, service identity, thiết bị hay một tiến trình quản trị?
- **Tới đâu?** FQDN, service, API route, workload ID và IP/port tại từng hop.
- **Để làm gì?** Read, write, administrative action, health check hay replication?
- **Thông tin nào vượt ranh giới?** Payload, credential, token, metadata hoặc cấu hình?
- **Kiểm soát nào xác minh?** Identity, authorization, network ACL, encryption, rate limit, schema validation?
- **Ai quan sát và chứng minh?** Access log, audit, firewall, flow logs, trace, NDR hay endpoint log?
- **Nếu kiểm soát thất bại thì sao?** Lộ dữ liệu, lateral movement, mất availability hoặc policy drift?

Nếu không trả lời được ai phát sinh và vì sao cần một kết nối, chưa nên tạo rule mở rộng chỉ để “đảm bảo dịch vụ chạy”.

## 5. Phân loại trust boundary theo vai trò

| Loại boundary | Ví dụ | Sự tin cậy thay đổi | Kiểm soát cần cân nhắc |
| --- | --- | --- | --- |
| **Internet / external edge** | Internet → public API | Người ngoài chưa được xác thực vào hệ thống | DDoS protection, TLS, gateway, WAF theo rủi ro |
| **Network zone** | GUEST → APP, APP → DATABASE | Network origin và độ nhạy tài sản | Firewall, ACL, microsegmentation, route |
| **Identity** | Contractor → admin portal | Quyền người dùng và device posture | MFA, IdP, PAM, conditional access |
| **Service identity** | Order service → Payment service | Quyền workload và scope API | mTLS/workload identity, authz ứng dụng |
| **Data classification** | API → dữ liệu nhạy cảm | Mức độ bí mật/toàn vẹn tăng | Least privilege, kiểm soát đối tượng, audit, encryption |
| **Control/management plane** | Admin → cloud API, firewall CLI | Có quyền thay đổi hệ thống | PAM, MFA, tách tài khoản, audit, approval |
| **Cloud tenancy** | Account/project A → B | Ownership, IAM, billing, policy khác | Cross-account role, explicit trust, private connectivity |
| **Cluster/namespace** | Pod ở namespace X → namespace Y | Chủ sở hữu workload/policy khác | NetworkPolicy, service auth, CNI/mesh controls |
| **Wireless/remote access** | Wi-Fi khách hoặc VPN user → LAN | Thiết bị và mạng nguồn ít bảo đảm hơn | NAC/802.1X, client isolation, identity-aware access |
| **Third party / supply chain** | SaaS, CDN, nhà cung cấp → hệ thống | Không kiểm soát đầy đủ chính sách phía kia | Contract, scoped integration, token scope, audit |

**Boundary có thể chồng lên nhau.** Khi request từ người dùng Internet đi qua WAF tới một service trong Kubernetes và service truy vấn database, có thể xuất hiện ranh giới về Internet, identity, workload, dữ liệu và quản trị trên cùng một đường nghiệp vụ.

### 5.1. Boundary động không thể diễn tả chỉ bằng subnet tĩnh

Trong cloud và container, pod IP, instance IP hoặc load balancer target có thể đổi theo autoscaling. Một service có thể gồm nhiều endpoint được cấp mới trong vài phút. Khi đó chính sách nên ưu tiên **identity và nhóm tài nguyên có thể quản trị** (label/selector, security group, service account, workload identity) thay vì danh sách IP viết tay, trong giới hạn tính năng nền tảng.

## 6. Dựng đúng đường đi request và response

Một lỗi thiết kế phổ biến là đặt kiểm soát tại vị trí **không thực sự thấy lưu lượng cần kiểm soát**.

~~~text
Client Internet
   |
   | TCP/TLS tới VIP công khai
   v
CDN / WAF / Reverse proxy  <-- có thể kết thúc TLS tại đây
   |
   | TCP/TLS mới tới backend; có thể đổi IP/port và HTTP version
   v
API gateway / Service mesh
   |
   | gọi dịch vụ theo workload identity
   v
Application service
   |
   | quyền database theo tài khoản ứng dụng
   v
Database
~~~

Không được giả định proxy chuyển nguyên packet hoặc duy trì cùng TCP sequence qua hai chặng. **L7 reverse proxy** thường là một TCP/TLS endpoint riêng, rồi tạo kết nối upstream mới. WAF ở edge có thể chặn request trước khi backend nhận được; ngược lại, giao tiếp nội bộ hoặc một đường direct-to-origin nếu cấu hình sai có thể **không đi qua WAF**.

### 6.1. NAT và địa chỉ gốc

Sau SNAT, server có thể chỉ thấy IP của proxy hoặc NAT gateway. Header **X-Forwarded-For** không phải bằng chứng tầng IP và có thể bị giả mạo nếu gateway không chuẩn hóa từ nguồn tin cậy. Nếu muốn thực thi chính sách theo danh tính client, phải xác định cách đưa identity đã xác minh qua boundary, không chỉ dựa trên header do caller tự khai.

### 6.2. Đường về và route bất đối xứng

Stateful firewall cần thấy hoặc có trạng thái phù hợp cho lưu lượng hai chiều. Với ECMP, policy routing, nhiều VPN gateway hoặc multi-region, request và response có thể đi qua các đường khác nhau. Một packet vào được không bảo đảm response quay về đúng. Khi quyết định đặt enforcement point, phải kiểm tra **forward path, return path, failover path** và vị trí log.

### 6.3. Encryption không thay thế authorization

TLS/mTLS bảo vệ kênh truyền và có thể xác thực danh tính đầu cuối theo cấu hình, nhưng **không tự quyết định** một user được sửa giao dịch nào, service được truy vấn record nào hoặc workload được gọi API nhạy cảm nào. Bên nhận vẫn phải áp chính sách ủy quyền ở mức tài nguyên/hành động; network ACL cũng không thay được authorization theo đối tượng.

## 7. Threat modeling tại từng boundary

Threat modeling nên bắt đầu từ **điều cần bảo vệ, ai kiểm soát mỗi phía, attacker có thể bắt đầu từ đâu và tác động nếu kiểm soát thất bại**, thay vì liệt kê lỗ hổng từ sản phẩm đã chọn.

Khung **STRIDE** có thể dùng để đặt câu hỏi:

| Nhóm đe dọa | Câu hỏi tại boundary | Biện pháp kiến trúc gợi ý |
| --- | --- | --- |
| **Spoofing** | Caller hoặc workload có thể giả mạo danh tính? | Authentication, mTLS, signed identity, chống spoofing ở mạng |
| **Tampering** | Dữ liệu hoặc chính sách có thể bị sửa trên đường đi? | TLS, integrity, signed configs, policy audit |
| **Repudiation** | Có thể truy ra ai đã gọi và thay đổi gì? | Audit trail, request ID, trusted time, log integrity |
| **Information disclosure** | Secret, payload hoặc metadata có vượt boundary sai mục đích? | Encryption, data minimization, ACL, token scope |
| **Denial of service** | Thành phần nào có thể bị làm cạn tài nguyên? | Rate limits, quota, isolation, capacity, circuit breakers |
| **Elevation of privilege** | Quyền từ vùng thấp có thể biến thành quyền cao hơn? | Least privilege, IAM/PAM, resource-level authz, isolation |

Không nên áp máy móc mọi biện pháp cho mọi luồng. Ví dụ WAF không thay được mTLS giữa backend, và service mesh không bảo vệ management API của cloud nếu IAM quá rộng.

### 7.1. Phân tích một giả thuyết

**Tài sản:** cơ sở dữ liệu thanh toán. **Đối tượng giả định:** workload order-service bị kiểm soát ở mức quyền ứng dụng. **Boundary:** order-service → payment-service → payment database.

Các câu hỏi:

1. Order-service có cần gọi trực tiếp database không, hay chỉ qua payment-service?
2. Nếu có quyền gọi payment-service, những API/hành động nào được phép?
3. Identity của workload có được xác minh độc lập với IP và hostname không?
4. Secret database có được cấp tối thiểu cho đúng service không?
5. Nếu order-service bị xâm nhập, phạm vi lan truyền bị giới hạn tới đâu?
6. Audit có đủ service identity, request/correlation ID và kết quả ủy quyền để điều tra không?

Thiết kế tốt có thể gồm **cấm đường DB trực tiếp**, chỉ cấp quyền API nghiệp vụ tối thiểu, xác thực workload, kiểm tra authz theo hành động và quan sát đầy đủ. Không nên chỉ thêm một firewall appliance rồi kết luận đã giải quyết được tất cả các câu hỏi.

## 8. Từ boundary đến yêu cầu kiểm soát

Sau khi hiểu boundary, viết yêu cầu theo **khả năng bảo vệ** trước, sau đó mới ánh xạ tới sản phẩm.

| Yêu cầu kiểm soát | Vị trí/cơ chế có thể dùng | Bằng chứng kiểm tra |
| --- | --- | --- |
| Chặn traffic giữa hai zone ngoài allowlist | Firewall, router ACL, CNI network policy | Rule, flow logs, test allow/deny |
| Xác thực user ở cổng truy cập | Identity provider, MFA, access gateway, NAC | Auth logs, session identity |
| Xác thực service-to-service | mTLS, workload identity, signed tokens | Certificate/principal, handshake, logs |
| Phân quyền API theo hành động/đối tượng | Application authz, API gateway phù hợp | Response 403, audit decision, test cases |
| Bảo vệ dữ liệu trên đường đi | TLS, VPN/IPsec ở boundary phù hợp | Config, negotiated protocol/cipher, cert validation |
| Lọc HTTP đầu vào | WAF, input validation, API schema/rate limit | WAF decision, request trace và negative test |
| Hạn chế quản trị đặc quyền | PAM, bastion, admin MFA, JIT access | Login/session logs, change record |
| Phát hiện hoạt động bất thường | IDS/NDR, endpoint telemetry, SIEM | Alert + raw event, sensor coverage |
| Hạn chế egress theo dịch vụ | Egress firewall, proxy, DNS policy, identity policy | Destination mapping, deny/allow logs |
| Bảo vệ điều khiển cloud | IAM least privilege, org policy, audit, scoped roles | Policy evaluation, change log, review |
| Khôi phục sau cấu hình lỗi | Versioned/immutable backup, runbook, restore drills | Restore test, RPO/RTO, evidence |

**Enforcement khác detection.** Một NDR sensor có thể phát hiện hành vi nhưng không chặn nếu không có chức năng/thẩm quyền IPS. Một firewall có thể chặn L3/L4 nhưng không biết người dùng được phép sửa đơn hàng nào. Chọn đúng **nhiệm vụ cần thực thi** và chỉ định owner cho từng lớp.

## 9. Quy trình quyết định kiến trúc: chọn yêu cầu trước công cụ

~~~mermaid
flowchart TD
    A[Xác định rủi ro nghiệp vụ và tài sản] --> B[Liệt kê chủ thể, luồng và mức nhạy cảm]
    B --> C[Đánh dấu trust boundaries, kể cả đường quản trị]
    C --> D[Phân tích đe dọa và kịch bản thất bại]
    D --> E[Viết policy: ai, được làm gì, với điều kiện nào]
    E --> F[Đặt yêu cầu enforcement, identity và telemetry]
    F --> G[So sánh phương án và trade-off]
    G --> H[Quyết định và ghi ADR]
    H --> I[Kiểm thử positive, negative và failure paths]
    I --> J[Quan sát, review thay đổi và cải tiến]
~~~

### 9.1. Ví dụ lựa chọn công cụ sai thứ tự

Đề xuất ban đầu: “Triển khai WAF vì mạng có nhiều API”. Nhưng rủi ro lớn nhất có thể là **workload nội bộ dùng chung database credential** và có thể đọc dữ liệu không thuộc chức năng. WAF ở Internet edge chỉ xử lý HTTP đi qua nó; không thay thế phân quyền database hoặc kiểm soát giao tiếp nội bộ.

Đề xuất tốt hơn: xác định quyền giữa services, tài khoản DB riêng, giới hạn kết nối network, authz theo nghiệp vụ, rồi đánh giá WAF như lớp bổ sung cho các request public. Thứ tự này tạo ra kiến trúc có thể chứng minh nhu cầu của từng control.

### 9.2. So sánh phương án theo tiêu chí

Đối với cùng một boundary, so các lựa chọn theo:

- **Điểm áp policy có thật sự nằm trên data path không?**
- **Định danh nào đáng tin?** IP/subnet, user, service account, certificate, workload ID?
- **Độ chi tiết chính sách:** L3/L4, URL/method, object permission, dữ liệu?
- **Phạm vi:** on-prem, cloud, container, IPv4/IPv6, east-west, multi-region?
- **Khả năng chịu lỗi:** fail-open hay fail-closed, phụ thuộc IdP/KMS/CA, HA và disaster recovery?
- **Tác động vận hành:** latency, throughput, log volume, cost, policy drift, nâng cấp/cấp chứng chỉ?
- **Khả năng kiểm chứng:** loại log, mapping source/target, test cases, alert và phản ứng?
- **Quyền sở hữu:** ai sửa policy, xử lý sự cố, kiểm toán và giải thích ngoại lệ?

Kết quả không nhất thiết là một công cụ đơn lẻ. Thường cần phối hợp **network isolation + identity + authorization + encryption + telemetry** ở những điểm phù hợp.

## 10. Xây ma trận policy theo luồng thay vì mở theo “mạng nội bộ”

Ví dụ hệ thống order/payment:

| Nguồn đã xác minh | Đích | Giao thức và tác vụ | Yêu cầu authorization | Network policy | Quan sát |
| --- | --- | --- | --- | --- | --- |
| Internet user | Public API gateway | HTTPS/443, request công khai | Authn/Authz cho route yêu cầu login | Chỉ public listener được chỉ định | WAF/access log |
| Order service identity | Payment service | mTLS HTTPS/8443, tạo yêu cầu thanh toán | Chỉ API được phép theo service role | Chỉ order → payment | Request/trace/mesh audit |
| Payment service identity | Payment DB | TCP/5432, truy cập dữ liệu thanh toán | DB account least privilege | Chỉ payment → DB | DB audit/flow |
| Order service identity | Payment DB | Không có nhu cầu | Không cấp credential | **Deny** | Firewall/CNI deny |
| Contractor VPN user | Admin console | Không được phép | Không có admin role | **Deny** | VPN/IAM/firewall |
| Admin thuộc nhóm vận hành | Management plane | HTTPS/SSH qua bastion được quản lý | MFA/PAM/JIT theo policy | Chỉ qua admin zone | Session audit |
| Workload | DNS resolver nội bộ | UDP/TCP/53 đến resolver được chỉ định | DNS policy theo zone | Giới hạn resolver | DNS log và flow |
| Backup service | Kho backup | TLS/443, đúng repository | Service identity và scoped write | Egress allowlist | Backup/KMS audit |

Các cổng là **minh họa**, không phải mẫu mặc định mọi hệ thống. Ma trận chính sách cần gắn với tài sản thật, owner và các trường hợp ứng dụng có thể chạy HTTP/2, QUIC hoặc giao thức quản trị khác.

### 10.1. Default deny không có nghĩa triển khai mù quáng

Mục tiêu thường là **deny traffic không được khai báo**, nhưng trước khi áp dụng cần kiểm kê DNS, NTP, telemetry, health check, secret delivery, control plane và các kết nối khởi tạo của ứng dụng. Áp quy tắc rộng trong production mà chưa kiểm thử có thể làm mất dịch vụ và khả năng quản trị. Nên triển khai theo nhóm nhỏ, dùng staging/canary, quan sát log và có rollback đã được phê duyệt.

## 11. Boundary quản trị thường nguy hiểm hơn traffic ứng dụng

Một kiến trúc có public API được bảo vệ kỹ nhưng giao diện quản trị của firewall, VPN, DNS hoặc cloud controller mở cho cả mạng người dùng vẫn thiếu ranh giới quan trọng.

Các quy tắc định hướng:

1. Tách **management plane** khỏi data plane bằng network và identity policy phù hợp.
2. Hạn chế nguồn truy cập quản trị vào các điểm được kiểm soát (PAM/bastion, admin VPN, private access).
3. Dùng MFA và tài khoản cá nhân hoặc service identity chuyên biệt; tránh shared admin account không truy vết.
4. Giới hạn đặc quyền theo vai trò, thời gian và tác vụ; thu hồi khi không cần.
5. Bảo vệ API keys, backup configs, certificate private keys, DNS admin và IAM admin.
6. Ghi audit thay đổi chính sách, đăng nhập, quyền được cấp và những hành vi nhạy cảm.
7. Kiểm tra tài khoản break-glass/khôi phục **có kiểm soát**, vì phụ thuộc hoàn toàn vào IdP có thể khóa cả đội ứng cứu khi IdP gặp sự cố.

**Boundary quản trị không chỉ là TCP/22 hoặc /443.** Một API cloud có thể được truy cập từ bất kỳ đâu nhưng quyền lực thực sự đến từ IAM; cần đánh giá tổ hợp identity, authorization, token lifetime, session protection và audit.

## 12. VPN, Wi-Fi, DNS và định danh: các boundary dễ bị đánh giá sai

### 12.1. VPN không biến người dùng thành “nội bộ đáng tin”

VPN/IPsec cung cấp kết nối được bảo vệ ở tầng thích hợp, nhưng người dùng sau VPN vẫn có thể là nhà thầu, thiết bị không quản lý hoặc tài khoản bị đánh cắp. Hạn chế những resource có thể tiếp cận theo **danh tính, trạng thái thiết bị, nhóm quyền, zone và mục đích sử dụng**. Split tunneling, route được đẩy và DNS suffix có thể làm đường đi khác với sơ đồ dự kiến.

### 12.2. Wi-Fi khách và mạng không dây doanh nghiệp

SSID không tự bảo đảm cách ly. Cần xác định ranh giới giữa guest, BYOD, corporate-managed, IoT và management. 802.1X/RADIUS/NAC giúp xác minh thiết bị/người dùng hoặc gán quyền, nhưng vẫn cần kiểm tra VLAN mapping, client isolation, ACL, DHCP và DNS policy. Một thiết bị kết nối SSID thành công chưa chứng minh nó được phép truy cập backend.

### 12.3. DNS là dependency lẫn bề mặt quyết định đường đi

Một DNS resolver đáng tin không làm tên miền được phân giải trở thành dịch vụ an toàn. Cần xem **ai được phép dùng resolver nào**, có split-horizon/DoH/DoT hay không, cách quản lý record, DNSSEC theo nhu cầu, và quyền thay zone. Thay đổi DNS record có thể làm request đi tới một điểm xử lý khác, bỏ qua security control đang đặt ở đường cũ.

### 12.4. IDS/IPS là điểm nhìn, không phải bằng chứng bao phủ toàn diện

Sensor ở một interface chỉ thấy traffic đi qua đó; east-west traffic trong pod, loopback, cloud private link hoặc mạng mã hóa có thể không xuất hiện ở sensor tại edge. Phải mô hình hóa **coverage** theo luồng và lựa chọn thêm application logs, EDR hoặc cloud telemetry khi cần. TLS decryption để phục vụ kiểm soát có rủi ro riêng về privacy, key handling và availability, chỉ thực hiện trong phạm vi quyền phù hợp.

## 13. Cloud và Kubernetes: boundary dựa trên workload identity

### 13.1. Cloud VPC và account/project

VPC/VNet, subnet, route table, security group/NSG, NACL và cloud firewall cung cấp các điểm thực thi ở những lớp khác nhau. **Network isolation không tương đương IAM isolation**: workload có thể không tới database qua TCP nhưng vẫn có cloud API permission quá rộng để đọc snapshot hoặc thay security policy.

Khi phân tích một ranh giới cloud, nên lập hai sơ đồ:

- **Data path:** workload → gateway/LB → private endpoint → dữ liệu.
- **Control path:** principal → IAM role → cloud API → thay đổi network resource hoặc data access.

Một thiết kế chỉ đánh giá data path có thể bỏ qua quyền thay đổi chính ranh giới bằng control plane.

### 13.2. Kubernetes NetworkPolicy và các giới hạn

Kubernetes **NetworkPolicy** tiêu chuẩn thường mô tả quy tắc ở mức L3/L4 đối với pod đã được chọn, tùy CNI có hỗ trợ thực thi. Nó không tự thực hiện authorization theo HTTP method hoặc object. **Ingress và egress isolation là những chiều riêng**; tạo quy tắc default-deny ingress không có nghĩa tự động chặn mọi egress.

Ví dụ mẫu policy khái niệm cho namespace **payments** (cần chỉnh nhãn và DNS/telemetry dependencies theo cụm thật):

~~~yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: payment-ingress-only-from-order
  namespace: payments
spec:
  podSelector:
    matchLabels:
      app: payment-service
  policyTypes:
    - Ingress
  ingress:
    - from:
        - namespaceSelector:
            matchLabels:
              kubernetes.io/metadata.name: orders
          podSelector:
            matchLabels:
              app: order-service
      ports:
        - protocol: TCP
          port: 8443
~~~

**Cách hiểu chính xác:**

- Policy lựa chọn các pod có nhãn **app=payment-service** ở namespace **payments**.
- Với pod được chọn, ingress chỉ cho traffic được quy tắc cho phép, cộng với ảnh hưởng của những NetworkPolicy khác cùng chọn pod (các quy tắc allow được hợp nhất theo ngữ nghĩa của Kubernetes).
- Bởi hai selector **namespaceSelector** và **podSelector** nằm cùng một phần tử của danh sách **from**, chúng được kết hợp để chọn **order-service pod thuộc namespace orders**. Nếu tách thành hai phần tử riêng, ý nghĩa sẽ khác và có thể mở rộng phạm vi không mong muốn.
- Policy này **không định nghĩa egress isolation**, không xác minh service identity bằng mật mã và không thay thế authorization tại payment-service.
- Điều kiện hỗ trợ, behavior khi đi qua Service, node/host network, overlay hoặc policy bổ sung phụ thuộc CNI và kiến trúc cụm; cần kiểm thử trên đúng nền tảng.

Trong cùng một pod, container thường chia sẻ network namespace; NetworkPolicy không phải công cụ tách biệt từng container trên loopback. Nếu boundary cần nằm giữa hai tiến trình trong pod, cần xem lại cách đóng gói, identity và ứng dụng.

### 13.3. Service mesh và mTLS

Service mesh có thể cấp workload identity và áp mTLS/authorization giữa các proxy, nhưng cần xác minh:

- Traffic nào đi qua sidecar/ambient dataplane và traffic nào có thể bypass?
- Danh tính nào được ràng buộc với certificate hoặc token?
- Policy có kiểm tra đúng **source principal, service, action và namespace** không?
- Có khả năng fail-open, policy drift hoặc lỗi cấp chứng chỉ không?
- Mesh log có ánh xạ đúng request tới workload hay chỉ ghi proxy identity?

Việc bật mTLS **không tự làm mọi traffic được phép trở nên tối thiểu**; authorization và egress policy vẫn cần thiết.

## 14. Vận hành và availability cũng là một phần của boundary

Đặt enforcement point thường tạo thêm phụ thuộc và điểm có thể thất bại. Trước khi chọn vị trí, đánh giá:

| Rủi ro vận hành | Câu hỏi thiết kế |
| --- | --- |
| Hỏng IdP | Người dùng và service còn truy cập được gì, có cơ chế emergency recovery? |
| Hết hạn certificate | mTLS có ngừng toàn bộ service-to-service traffic không? |
| WAF/API gateway quá tải | Có HA, rate limiting hoặc degradation plan phù hợp không? |
| Firewall state table đầy | Failover và route có giữ được phiên và policy không? |
| DNS resolver lỗi | Resolver redundancy, caching và application behavior ra sao? |
| Mất network telemetry | Có cảnh báo sensor blind spot và log pipeline outage không? |
| Cloud region/network partition | Kịch bản failover có đi qua boundary mới không? |
| Sai policy rollout | Có canary, rollback, kiểm tra quyền quản trị và test lại không? |

**Fail-open/fail-closed** không có đáp án chung. Một cổng bảo vệ dữ liệu nhạy cảm thường cần hạn chế truy cập khi xác minh thất bại; nhưng điều đó cũng có thể ảnh hưởng availability. Quyết định phải dựa trên rủi ro nghiệp vụ, lựa chọn degradation an toàn và quy trình khôi phục đã kiểm thử, không đặt mặc định vì tiện vận hành.

## 15. Ví dụ hoàn chỉnh: quyết định bảo vệ dịch vụ thanh toán

### 15.1. Bối cảnh và yêu cầu

Một hệ thống giả định có:

- Public order API: nhận request từ Internet.
- Order service: xử lý đơn, gọi payment service.
- Payment service: xử lý giao dịch và có quyền truy cập payment database.
- Admin portal: chỉ nhóm vận hành được quản trị qua danh tính mạnh.
- Cloud control plane: quản lý load balancer, security group và tài nguyên dữ liệu.

**Rủi ro chính:** nếu order service hoặc tài khoản nhà thầu bị lạm dụng, đối tượng không được phép trực tiếp đọc/ghi payment database hoặc sửa cấu hình mở rộng quyền. **Yêu cầu availability:** order API vẫn phục vụ được phần chức năng không phụ thuộc payment khi dịch vụ thanh toán bị sự cố, nếu phù hợp nghiệp vụ.

### 15.2. Xác định boundary

| Boundary | Giả định không được tin tự động | Yêu cầu kiểm soát |
| --- | --- | --- |
| Internet → Edge | Caller và nội dung request | TLS, input validation, rate limit, auth cho API phù hợp |
| Edge → Order service | Header, source IP và request identity | Tin header chỉ từ proxy đã xác minh; authn/authz |
| Order → Payment | Workload identity và quyền gọi nghiệp vụ | Network allowlist + workload auth + API authz |
| Payment → DB | Quyền truy cập dữ liệu và secret DB | Chỉ payment được kết nối; DB role least privilege |
| Contractor → Management | User/device không thuộc nhóm admin | Không cấp route/role quản trị, deny và audit |
| Operator → Cloud control plane | Quyền sửa policy/mở đường truy cập | MFA/PAM/JIT, scoped IAM và audit |

### 15.3. Chọn phương án theo yêu cầu

**Phương án A: chỉ chặn theo subnet.** Có giá trị giảm reachability nhưng kém chi tiết khi pod IP thay đổi, cùng subnet có nhiều service và ứng dụng vẫn có thể lạm dụng quyền nếu đã tới được API.

**Phương án B: chỉ bật mTLS/service mesh.** Tăng xác thực workload và bảo vệ kênh, nhưng nếu cho phép tất cả service gọi nhau hoặc DB role quá rộng, vẫn không đạt least privilege; còn phải quản lý certificate, mesh dataplane và fallback.

**Phương án C: phân lớp kiểm soát theo boundary.** Kết hợp segment/NetworkPolicy, service identity, authorization theo API, DB role riêng, security group và cloud IAM cho control plane; log được nối qua request ID và workload principal. Phương án này bảo vệ nhiều kiểu thất bại hơn nhưng có chi phí thiết kế policy, quan sát và khôi phục cao hơn.

Lựa chọn có thể ưu tiên C ở những đoạn rủi ro cao, đồng thời triển khai theo giai đoạn có kiểm thử. Không nhất thiết áp cùng một công nghệ cho toàn hệ thống.

### 15.4. Ma trận kiểm thử chấp nhận

| Mã test | Nguồn | Đích/hành động | Kỳ vọng | Bằng chứng |
| --- | --- | --- | --- | --- |
| T01 | Public client | GET route public của gateway | Cho phép nếu route công khai | Edge log + HTTP status |
| T02 | Public client không có quyền | Ghi đơn hàng của người khác | Từ chối ở ứng dụng | Authz audit + response phù hợp |
| T03 | Order workload hợp lệ | Gọi payment API cho phép | Cho phép theo identity và scope | Mesh/app trace |
| T04 | Order workload | Kết nối payment DB trực tiếp | Từ chối ở network policy | Flow/CNI log + DB absence có giới hạn |
| T05 | Workload ngoài allowlist | Gọi payment API | Từ chối | Network/authz log |
| T06 | Contractor VPN test identity | Truy cập admin portal | Từ chối | VPN/IAM/gateway audit |
| T07 | Admin đã có MFA/PAM | Tác vụ quản trị đã phê duyệt | Chỉ đúng vai trò/phiên | Privileged session audit |
| T08 | Identity provider unavailable (lab) | Gọi API nhạy cảm | Hành vi fail mode theo thiết kế | Health/decision/error logs |
| T09 | Failover to alternate region (lab) | Luồng order → payment | Vẫn qua boundary đã duyệt | Route + network/security logs |

**Bài test phải được phê duyệt và giới hạn vào lab/staging hoặc một cửa sổ vận hành có kiểm soát.** Các phép thử T04/T05 không cần đọc dữ liệu thật; dùng endpoint/test marker và kiểm chứng policy. Với kết quả “không thấy log”, kiểm tra độ bao phủ của nguồn trước khi kết luận.

## 16. Viết Architecture Decision Record (ADR) để giữ lại lý do

Một **Architecture Decision Record** không chỉ ghi “sẽ dùng firewall X”, mà giữ **bối cảnh, ranh giới đã xác định, yêu cầu bảo mật, phương án, trade-off và cách kiểm chứng**. Khi topology thay đổi, nhóm khác có thể hiểu vì sao một rule hoặc identity policy tồn tại.

~~~markdown
# ADR-EXAMPLE-001: Phân tách Order và Payment

Trạng thái: Proposed
Ngày: 2026-11-28
Chủ sở hữu: Platform Security + Payment Service Owner

## Bối cảnh
- Order service gọi Payment API.
- Không có nhu cầu Order service truy cập Payment DB trực tiếp.
- Workload có thể tăng/giảm động trong Kubernetes.

## Ranh giới và rủi ro
- Boundary A: Order workload -> Payment service.
- Boundary B: Payment service -> Payment DB.
- Rủi ro: lateral movement và lạm dụng database credentials.

## Yêu cầu
- Chỉ Order workload được phép gọi Payment API theo scope.
- Chỉ Payment workload được phép mở session đến DB.
- Request và quyết định deny phải có audit phù hợp.
- Có test positive, negative, failover và rollback.

## Phương án
- A: chỉ network IP ACL.
- B: chỉ service mesh mTLS.
- C: network segmentation + workload identity + authz + DB role.

## Quyết định
- Chọn C cho boundary nhạy cảm.
- Triển khai canary và kiểm thử trên từng đường trước khi mở rộng.

## Hệ quả và rủi ro còn lại
- Tăng độ phức tạp policy/certificate lifecycle.
- Phụ thuộc vào CNI/mesh/IdP và khả năng quan sát.
- Cần giám sát policy drift và diễn tập phục hồi.

## Kiểm chứng
- T01..T09 trong test matrix của dự án.
- Ghi owner và ngày review lại khi topology/identity đổi.
~~~

Đây là mẫu tài liệu, không phải một quyết định đã phê duyệt cho production. Trạng thái ADR có thể đi qua Proposed → Accepted → Superseded khi có thay đổi; không chỉnh sửa lý do cũ như thể quyết định chưa từng tồn tại.

## 17. Các lỗi thiết kế thường xuất phát từ chọn công cụ quá sớm

| Sai lầm | Tại sao sai | Cách điều chỉnh |
| --- | --- | --- |
| Có firewall ở Internet nên cho phép toàn bộ east-west | Boundary nội bộ không được bảo vệ | Xác định service/data trust boundaries và microsegmentation |
| Coi VPN user là tài khoản nội bộ đáng tin | Kênh kết nối không chứng minh quyền ứng dụng | Identity-aware access và least privilege |
| Dùng IP allowlist để thay hoàn toàn authentication | IP có thể bị dùng chung, NAT hoặc thay đổi | Kết hợp workload/user identity và application authz |
| Bật mTLS rồi bỏ qua authorization | Mã hóa và xác thực kênh không định nghĩa quyền hành động | Kiểm tra scope/role/đối tượng ở API |
| Đặt WAF trên edge rồi nghĩ bảo vệ cả nội bộ | Đường backend hoặc direct origin có thể bỏ qua WAF | Kiểm tra từng ingress path và backend controls |
| Đồng nhất VLAN với security boundary hoàn chỉnh | Nhiều máy trong VLAN vẫn có thể ngang quyền | Segmentation theo workload, host và identity |
| Bỏ qua management/control plane | Attacker có thể thay chính policy an ninh | IAM, PAM, audit và policy-as-code review |
| Chỉ vẽ đường request | Response, failover và asymmetric routing có thể khác | Vẽ cả return path và failure paths |
| Chỉ mô hình hóa IPv4 hoặc TCP | IPv6, UDP/QUIC, DNS và management protocols bị bỏ sót | Inventory protocol/address family theo luồng |
| Không kiểm tra hostname qua CDN/LB | Endpoint được quét không phải origin | Ghi TLS termination, VIP/backend mapping |
| Áp default deny toàn cụm ngay | Dịch vụ phụ thuộc DNS/NTP/telemetry có thể dừng | Inventory dependency, canary, rollback |
| Cho rằng security group đủ bảo vệ cloud | IAM/API permissions có thể vượt data path | Mô hình hóa control plane và resource permissions |
| Chỉ dựa trên alert IDS | Không biết traffic có đi qua sensor | Đánh giá coverage, packet/flow và endpoint logs |
| Chọn sản phẩm bằng bảng tính năng mà không có yêu cầu | Không đo được hiệu quả của biện pháp | Viết boundary policy và acceptance tests trước |
| Không ghi ADR/owner | Chính sách bị xóa hoặc mở rộng thiếu căn cứ | Lưu quyết định, owner, lý do và ngày review |

## 18. Quy trình thực hành cho một dự án mới

Một nhóm thiết kế có thể triển khai theo các bước:

### Bước 1 — Tập hợp bối cảnh

Lấy thông tin nghiệp vụ, tài sản, mức độ nhạy cảm dữ liệu, user/persona, các dịch vụ phụ thuộc, RTO/RPO và ownership. Chưa chọn thiết bị hay sản phẩm.

### Bước 2 — Vẽ các luồng và điểm thay đổi quyền

Vẽ request/response, luồng quản trị, identity, backup, DNS, telemetry và cloud control plane. Với mỗi luồng, ghi điểm bắt đầu, đích và điều kiện truy cập hợp lệ. Đánh dấu nơi có **principal hoặc trust domain mới**.

### Bước 3 — Đưa ra giả thuyết đe dọa

Cho mỗi boundary, hỏi điều gì xảy ra nếu caller giả mạo, workload bị xâm nhập, token bị lộ, route thay đổi, control plane bị chiếm hoặc dữ liệu rời vùng được phép.

### Bước 4 — Viết policy bằng ngôn ngữ nghiệp vụ

Ví dụ: “Order service được phép yêu cầu tạo giao dịch qua Payment API nhưng không được truy cập Payment DB”, “Nhà thầu không được tới management network”, “Cloud admin phải dùng MFA/PAM theo vai trò”. Chính sách này độc lập với tên sản phẩm.

### Bước 5 — Chọn vị trí và cơ chế thực thi

Đánh giá firewall/ACL, security group, NetworkPolicy, mTLS/mesh, API authorization, IdP/PAM, WAF, DNS policy, EDR/NDR và audit theo đúng vai trò từng control. Kiểm tra đường bypass, HA/failover và chi phí vận hành.

### Bước 6 — Ghi quyết định và kiểm thử

Tạo ADR, policy matrix, positive/negative cases, identity evidence, network flow logs, ứng dụng trace và recovery plan. Chạy trong môi trường được phép, từ đúng zone và danh tính. Không kết luận an toàn khi chỉ kiểm tra một source hoặc một port.

### Bước 7 — Rà soát trong vòng đời

Khi thêm dịch vụ, region, VPN profile, SaaS, thay IAM, tăng IPv6 hoặc thay mesh/CNI, cập nhật boundary diagram và acceptance tests. Kiểm soát đúng hôm nay có thể không còn nằm trên đường đi sau một thay đổi routing hoặc topology.

## 19. Checklist xác định trust boundary trước khi chọn công cụ

- [ ] Đã liệt kê dịch vụ nghiệp vụ, tài sản quan trọng, dữ liệu nhạy cảm và owner.
- [ ] Đã xác định user, device, service/workload identities và điều kiện xác minh.
- [ ] Đã vẽ DFD cho request, response, DNS, identity, quản trị, telemetry và backup.
- [ ] Đã đánh dấu nơi đổi trust domain, quyền hành động, dữ liệu hoặc ownership.
- [ ] Đã phân biệt network zone, identity boundary, data boundary và control plane.
- [ ] Đã xác minh đường đi thực qua NAT, proxy, TLS termination, load balancer, VPN, cloud và service mesh.
- [ ] Đã xem xét return path, failover, asymmetric routing, IPv6 và UDP/QUIC khi phù hợp.
- [ ] Đã đặt giả thuyết về spoofing, tampering, information disclosure, DoS và privilege escalation.
- [ ] Đã viết rõ ai được làm gì, trên tài nguyên nào, với điều kiện và mục đích nào.
- [ ] Đã chọn enforcement point **thật sự nhìn thấy và kiểm soát** traffic/hành động tương ứng.
- [ ] Đã tách authentication, authorization, encryption, segmentation và detection thành các yêu cầu khác nhau.
- [ ] Đã bảo vệ management plane, cloud IAM và secret/PKI dependencies.
- [ ] Đã phân tích fail mode, HA, recovery, rollback và tác động performance/cost.
- [ ] Đã định nghĩa log, request identity, sensor coverage và bằng chứng kiểm chứng.
- [ ] Đã lập ma trận kiểm thử được phép, gồm positive, negative và failure-path cases.
- [ ] Đã lưu ADR cùng các phương án bị loại, trade-off, owner và mốc review.
- [ ] Đã quy định rà soát lại boundary khi topology, service identity hoặc dữ liệu thay đổi.

**Kết luận:** trust boundary là **điều phải hiểu trước khi quyết định chọn công cụ**, không phải đường viền thêm vào sơ đồ sau khi mua firewall, WAF hay service mesh. Khi bắt đầu từ tài sản, quyền truy cập, dữ liệu và đường đi, nhóm kiến trúc có thể chọn đúng lớp kiểm soát cho đúng ranh giới, chứng minh hiệu quả bằng kiểm thử có giới hạn và duy trì một hệ thống mạng an toàn ngay cả khi ứng dụng, danh tính và hạ tầng liên tục thay đổi.
