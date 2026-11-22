# Thiết kế truy cập quản trị và truy cập dịch vụ nội bộ

Một hệ thống cloud không chỉ có điểm vào dành cho khách hàng. Nhà phát triển cần triển khai phiên bản mới, người vận hành cần xem log và xử lý sự cố, công cụ tự động hóa cần tạo tài nguyên, còn các dịch vụ backend phải gọi database, queue hoặc API nội bộ. Nếu tất cả những hoạt động này đi qua cùng một đường truy cập với cùng một loại danh tính, hệ thống dễ cấp quyền quá rộng, mở bề mặt tấn công không cần thiết và khó xác định ai đã thực hiện thay đổi.

Thiết kế kiến trúc cần phân biệt ít nhất hai nhóm:

- **Truy cập quản trị (administrative access):** Con người hoặc hệ thống vận hành có quyền quản lý cấu hình, hạ tầng, tài khoản, workload và hoạt động khắc phục sự cố.
- **Truy cập dịch vụ nội bộ (internal service access):** Ứng dụng, worker hoặc workload identity gọi API, database, queue, cache và các dịch vụ khác để thực hiện nghiệp vụ.

Hai nhóm này có thể dùng chung một số nền tảng danh tính hoặc mạng, nhưng phải có **điểm vào, danh tính, phạm vi quyền, chính sách xác thực và kiểm toán** phù hợp với mục đích. Trong module CLOUD_ARCHITECTURE, đây là một quyết định liên quan trực tiếp tới kiến trúc mạng, compute, dữ liệu, bảo mật, độ tin cậy, chi phí và vận hành theo tư duy Well-Architected.

## 1. Phân biệt hai mặt phẳng truy cập

Trong nhiều thiết kế, có thể dùng cách phân tích **management plane** và **service/data plane**:

- **Management plane (mặt phẳng quản trị):** Nơi tạo, thay đổi, cấu hình, quan sát và quản lý tài nguyên. Ví dụ: cloud console, API quản lý tài nguyên, hệ thống IAM, pipeline triển khai, hệ thống quản lý Kubernetes control plane.
- **Service/data plane (mặt phẳng dịch vụ/dữ liệu):** Nơi xử lý lưu lượng nghiệp vụ hoặc truy cập dữ liệu khi hệ thống hoạt động. Ví dụ: khách hàng gọi Booking API, Booking API gọi Payments API, worker đọc queue hoặc API truy vấn database.

Ranh giới này là **một cách tư duy kiến trúc**; tên gọi và phạm vi chính xác có thể khác theo dịch vụ cloud. Có dịch vụ cung cấp control plane và data plane riêng biệt, có dịch vụ kết hợp chúng qua endpoint hoặc cơ chế xác thực chung. Không nên giả định mọi thao tác admin đều chỉ dùng một endpoint hoặc mọi lưu lượng giữa dịch vụ đều là data plane theo định nghĩa sản phẩm.

| Tiêu chí | Truy cập quản trị | Truy cập dịch vụ nội bộ |
|---|---|---|
| Chủ thể | Nhân viên, quản trị viên, kỹ sư, pipeline/automation có quyền quản trị | API, worker, job, workload identity |
| Mục tiêu | Quản lý tài nguyên, triển khai, xem trạng thái, thay đổi cấu hình, khắc phục sự cố | Thực hiện nghiệp vụ, trao đổi dữ liệu và sự kiện giữa các workload |
| Điểm vào | Identity provider/SSO, cloud console, API quản lý, bastion hoặc truy cập zero-trust, CI/CD | Private endpoint, internal load balancer, service discovery, private API, queue/database endpoint |
| Danh tính | Danh tính người dùng hoặc danh tính automation với quyền quản trị giới hạn | Danh tính máy/workload riêng cho từng ứng dụng hoặc dịch vụ |
| Cấp quyền | Role theo nhiệm vụ, scope và thời hạn; phê duyệt cho thao tác nhạy cảm | Quyền tối thiểu theo service, API, resource, action và dữ liệu |
| Giao thức | HTTPS tới console/API, SSH/RDP nếu thật sự cần, API của công cụ quản trị | HTTPS/gRPC, giao thức database, queue hoặc giao thức chuyên dụng |
| Kiểm toán | Ai đã đăng nhập, nâng quyền, thay đổi hoặc phê duyệt thao tác nào? | Workload nào gọi dịch vụ nào, với quyền gì, kết quả và lượng dữ liệu ra sao? |
| Rủi ro chính | Chiếm tài khoản đặc quyền, thay đổi diện rộng, thao tác nhầm | Giả mạo workload, truy cập ngang, lộ secret, dữ liệu bị đọc/ghi sai |

**Không dùng tài khoản cá nhân của nhân viên làm danh tính mặc định cho ứng dụng.** Khi một service dùng credential của một người để gọi database hoặc API khác, vòng đời quyền bị gắn vào nhân viên đó, khó thu hồi, kiểm toán và thay thế. Ứng dụng nên có danh tính workload riêng và quyền phù hợp.

## 2. Bản đồ điểm vào cho một hệ thống cloud

Giả sử nền tảng đặt chỗ có Booking API, Payments API, database, queue và worker. Đội vận hành cần deploy, theo dõi và xử lý sự cố. Một kiến trúc tham khảo có thể tách luồng như sau:

~~~mermaid
flowchart TB
    subgraph PEOPLE["Con người và công cụ quản trị"]
        ADMIN["Kỹ sư / Admin"]
        IDP["Enterprise IdP / SSO / MFA"]
        PORTAL["Cloud console / Management API"]
        CICD["CI/CD và automation identity"]
    end
    ADMIN --> IDP
    IDP --> PORTAL
    CICD -->|"Federation / short-lived role"| PORTAL
    subgraph CLOUD["Môi trường cloud"]
        subgraph MGMT["Management plane"]
            IAM["IAM / RBAC / policy"]
            AUDIT["Audit log / security monitoring"]
            PORTAL --> IAM
            IAM --> AUDIT
        end
        subgraph PRIVATE["Private application network"]
            LB["Internal load balancer / service discovery"]
            BOOK["Booking API"]
            PAY["Payments API"]
            DB[("Booking database")]
            Q[("Message queue")]
            WORKER["Notification worker"]
            BOOK -->|"Service identity + TLS"| PAY
            BOOK -->|"Database identity"| DB
            BOOK --> Q
            Q --> WORKER
        end
        BOOK -. "Application / security telemetry" .-> AUDIT
        PAY -. "Application / security telemetry" .-> AUDIT
    end
~~~

Sơ đồ thể hiện nguyên tắc: nhân viên đi qua hệ thống danh tính doanh nghiệp và điểm vào quản trị; automation dùng danh tính riêng; các workload gọi nhau qua đường mạng dịch vụ được thiết kế. Audit log của management plane và log giao dịch/workload đều quan trọng, nhưng phải kiểm soát quyền đọc, sửa, xóa và lưu giữ phù hợp.

Sơ đồ không khẳng định mọi control plane phải nằm trong VPC/VNet riêng. Nhiều API quản lý của nhà cung cấp cloud được truy cập qua endpoint dịch vụ công khai có xác thực, trong khi workload data plane có thể dùng private endpoint. Điều cần thiết là kiểm soát danh tính, nguồn truy cập, phạm vi quyền và luồng dữ liệu theo khả năng nền tảng.

## 3. Thiết kế truy cập quản trị cho con người

### 3.1. SSO, identity federation và MFA

Một hệ thống doanh nghiệp thường dùng **Identity Provider (IdP)** tập trung, như Microsoft Entra ID hoặc một IdP hỗ trợ giao thức liên kết danh tính, để nhân viên đăng nhập một lần và nhận quyền tới các nền tảng cần thiết.

Luồng khái niệm:

1. Nhân viên đăng nhập bằng tài khoản doanh nghiệp và xác minh đa yếu tố (MFA) theo chính sách.
2. IdP xác thực danh tính và phát assertion/token theo giao thức liên kết được hỗ trợ.
3. Cloud identity broker hoặc cơ chế federation xác định người dùng/nhóm và gán role phù hợp.
4. Người dùng nhận **phiên hoặc credential có thời hạn**, thao tác trong đúng phạm vi được cấp.
5. Sự kiện đăng nhập, nâng quyền và hành động quản trị được ghi lại để kiểm toán.

**SSO không phải là cấp quyền vô hạn.** SSO giải quyết cách xác thực và liên kết danh tính; IAM/RBAC vẫn quyết định tài nguyên và thao tác nào được phép. Người chỉ cần xem metric không nên nhận quyền xóa database chỉ vì cùng đăng nhập một IdP.

MFA giúp giảm rủi ro khi mật khẩu bị lộ, nhưng vẫn cần bảo vệ session/token, chống phishing theo khả năng hỗ trợ, quản lý thiết bị, thu hồi phiên và giám sát hành vi bất thường. Nên ưu tiên phương thức MFA chống phishing cho tài khoản có đặc quyền cao nếu hệ sinh thái hỗ trợ.

### 3.2. Role theo nhiệm vụ và quyền tối thiểu

Thiết kế quyền nên bắt đầu từ **nhiệm vụ thực tế** thay vì cấp role quản trị tổng quát:

| Vai trò | Quyền ví dụ | Các quyền không nên mặc định có |
|---|---|---|
| Developer | Xem log/metric dev, triển khai vào môi trường dev, đọc cấu hình không nhạy cảm | Quản trị IAM cấp organization, xóa dữ liệu prod |
| Release operator | Thực hiện release được phê duyệt, theo dõi triển khai | Tự cấp thêm quyền hoặc thay policy bảo mật |
| Database operator | Theo dõi, sao lưu/khôi phục theo quy trình, thao tác bảo trì được phê duyệt | Đọc dữ liệu nghiệp vụ không cần thiết hoặc sửa IAM toàn hệ thống |
| Security auditor | Đọc audit log, xem policy và trạng thái tuân thủ | Sửa/xóa nguồn log và vô hiệu hóa giám sát |
| Platform administrator | Quản lý thành phần nền tảng trong scope được giao | Mặc định quyền sở hữu mọi dữ liệu sản phẩm |

Các role là ví dụ; một tổ chức có thể chia nhỏ hơn hoặc kết hợp theo quy mô. Khi thiết kế cần xác định:

- **Principal:** Người dùng, nhóm, service principal, role hoặc workload identity nào đang hành động?
- **Resource/scope:** Role áp dụng ở organization, account, subscription, project, resource group, cluster, namespace hay resource cụ thể?
- **Action:** Được xem, tạo, cập nhật, xóa, cấp quyền, tải dữ liệu hay khôi phục?
- **Condition:** Có giới hạn theo môi trường, mạng, thiết bị, thời gian, ticket hoặc mức độ xác thực không?
- **Duration:** Quyền là thường trực hay chỉ tồn tại trong cửa sổ công việc?

Ưu tiên cấp quyền tại **scope nhỏ nhất đủ dùng** và định kỳ rà soát quyền không còn cần thiết. Tên role “read-only” cũng cần kiểm tra kỹ: quyền đọc secret, xuất dữ liệu hoặc xem log có thể gây rủi ro lớn dù không thay đổi cấu hình.

### 3.3. Truy cập đặc quyền theo thời gian (JIT)

Với thao tác nhạy cảm, có thể dùng mô hình **Just-In-Time (JIT) access** hoặc cơ chế nâng quyền tạm thời:

1. Nhân viên có role cơ bản, không giữ thường trực quyền admin rộng.
2. Khi cần thay đổi, họ gửi yêu cầu nêu lý do, scope, thời hạn và mã ticket.
3. Hệ thống phê duyệt hoặc kiểm tra điều kiện theo policy.
4. Quyền được kích hoạt trong khoảng thời gian giới hạn và tự hết hạn.
5. Hoạt động được ghi audit và sau đó được review.

Ví dụ, database operator được quyền xem metric thường trực; khi cần restore prod, họ xin quyền khôi phục database trong một cửa sổ bảo trì. Phạm vi của quyền nên chỉ gồm database cần xử lý và thao tác được phê duyệt.

### 3.4. Break-glass access

**Break-glass** là cơ chế truy cập khẩn cấp khi hệ thống đăng nhập hoặc phê duyệt thông thường gặp sự cố và tổ chức cần khôi phục dịch vụ.

Thiết kế break-glass cần:

- Tài khoản/cơ chế khẩn cấp được bảo vệ và giới hạn số lượng.
- Bảo vệ credential, MFA mạnh và quy trình lưu trữ/luân chuyển an toàn.
- Cảnh báo tức thời khi được sử dụng, audit log độc lập nếu có thể.
- Chỉ dùng trong tình huống và phạm vi được quy định; ghi lại lý do, người thực hiện và thao tác.
- Sau sự cố, thu hồi/đổi credential cần thiết và review hành động.

Không nên tạo “tài khoản admin dự phòng” dùng chung, mật khẩu không đổi và không có cảnh báo. Break-glass là **cơ chế khôi phục có kiểm soát**, không phải đường tắt cho quy trình cấp quyền thường ngày.

## 4. Bastion, VPN và mô hình zero-trust cho truy cập quản trị

### 4.1. Bastion host

**Bastion host (jump host)** là máy trung gian được kiểm soát để nhân viên truy cập tới máy chủ hoặc thiết bị quản trị trong mạng riêng. Người dùng không kết nối SSH/RDP trực tiếp từ Internet tới mọi máy nội bộ.

~~~mermaid
flowchart LR
    OP["Kỹ sư"] -->|"SSO + MFA"| ACCESS["VPN / Zero-trust access"]
    ACCESS --> BASTION["Bastion / Session gateway"]
    BASTION -->|"SSH/RDP chỉ tới đích được phép"| VM["Private VM / admin endpoint"]
    VM -. "Session log / audit" .-> LOG["Central logging"]
~~~

Bastion giúp tập trung điểm vào và theo dõi phiên, nhưng trở thành thành phần có đặc quyền cao. Phải vá lỗi, giới hạn nguồn vào, không lưu khóa dùng chung không kiểm soát, ghi log phiên khi phù hợp và có phương án HA/khôi phục. Nếu nền tảng hỗ trợ dịch vụ truy cập quản trị không cần máy trung gian, cần đánh giá để giảm công vận hành bastion.

### 4.2. VPN

VPN tạo đường kết nối mạng mã hóa giữa thiết bị/người dùng hoặc giữa mạng doanh nghiệp và cloud, tùy mô hình. Tuy nhiên **VPN không tự cấp quyền tới mọi tài nguyên**; sau khi tunnel lên, IAM/RBAC, firewall, endpoint policy và xác thực ứng dụng vẫn áp dụng.

VPN truyền thống có thể khiến thiết bị trở thành một phần của mạng có khả năng truy cập rộng nếu route và ACL thiết kế không chặt. Cần giới hạn prefix, split/full tunnel có chủ đích, phân đoạn theo nhóm người dùng và kiểm tra thiết bị theo chính sách.

### 4.3. Zero-trust network access (ZTNA)

ZTNA mô tả cách tiếp cận trong đó **không tin cậy mặc định chỉ vì người dùng đang ở trong mạng nội bộ**. Mỗi yêu cầu cần được đánh giá dựa trên danh tính, thiết bị, ngữ cảnh, tài nguyên và policy. Một số nền tảng cung cấp dịch vụ truy cập ứng dụng riêng mà không cần mở kết nối mạng tổng quát tới toàn bộ subnet.

Zero-trust không đồng nghĩa “không có mạng riêng” hoặc “mọi request phải qua một sản phẩm duy nhất”. Nó là tập nguyên tắc kiểm soát liên tục: xác minh danh tính, giới hạn quyền, phân đoạn, kiểm tra trạng thái thiết bị và giảm phạm vi tác động nếu tài khoản bị chiếm.

| Mô hình | Lợi ích | Rủi ro/điều kiện cần xử lý |
|---|---|---|
| VPN tới mạng riêng | Dễ tích hợp công cụ cần giao thức mạng truyền thống | Có thể mở rộng khả năng tiếp cận mạng quá rộng nếu route/ACL không chặt |
| Bastion/jump host | Tập trung quản trị máy riêng và phiên terminal | Điểm vào đặc quyền cao; cần hardening, log và HA |
| ZTNA theo ứng dụng | Cấp quyền theo ứng dụng và ngữ cảnh, giảm phụ thuộc subnet | Cần tích hợp danh tính/thiết bị, kiểm soát policy và ứng dụng tương thích |
| Dịch vụ quản trị cloud qua console/API | Dùng cơ chế IAM và audit của nhà cung cấp | Phải kiểm soát endpoint, role, session, quyền và nguy cơ thay đổi diện rộng |

Không nhất thiết chỉ chọn một mô hình. Ví dụ, console/API cloud phục vụ quản trị tài nguyên; ZTNA cấp quyền truy cập dashboard nội bộ; bastion dành cho một số máy cần SSH/RDP. Mỗi đường cần scope và owner rõ.

## 5. Truy cập dịch vụ nội bộ: danh tính workload và endpoint riêng

Khi Booking API gọi Payments API, đây là **service-to-service access**. Kết nối có thể đi trong VPC/VNet riêng, qua private endpoint, internal load balancer, service discovery hoặc transit network. Nhưng mạng riêng không tự xác nhận caller có quyền thực hiện nghiệp vụ.

### 5.1. Danh tính workload

Mỗi workload nên có danh tính riêng, như:

- IAM role gắn với workload trên AWS (ví dụ thông qua cơ chế role dành cho compute hoặc federation phù hợp).
- Managed identity hoặc workload identity trên Azure.
- Workload Identity Federation/service account trên Google Cloud.
- Service account hoặc SPIFFE/SPIRE identity trong một nền tảng nội bộ nếu được triển khai và vận hành phù hợp.

Các tên gọi không hoàn toàn tương đương; cần xem cách cấp credential, phạm vi trust, thời hạn và khả năng federation của từng nền tảng.

**Ưu tiên credential ngắn hạn được cấp theo danh tính workload**, tránh nhúng access key dài hạn, mật khẩu database hoặc token tĩnh trong source code, image, biến môi trường không được bảo vệ hoặc tệp cấu hình được commit vào Git.

Ví dụ quyền tối thiểu:

| Workload | Danh tính | Quyền cần có |
|---|---|---|
| Booking API | booking-api-prod | Gọi Payments API với scope tạo yêu cầu thanh toán; ghi/đọc bảng đặt chỗ cần thiết |
| Notification Worker | notification-worker-prod | Đọc queue và gửi email qua dịch vụ được cấp |
| CI/CD Booking | booking-deploy-prod | Cập nhật đúng workload Booking theo pipeline; không đọc dữ liệu thanh toán |
| Monitoring agent | monitoring-agent | Gửi telemetry tới hệ thống giám sát; không đọc business database |

### 5.2. Private endpoint và internal load balancer

**Private endpoint** cho phép workload truy cập một dịch vụ qua địa chỉ riêng hoặc đường kết nối được nhà cung cấp hỗ trợ, giảm nhu cầu phơi bày dịch vụ trên Internet công cộng. **Internal load balancer** phân phối lưu lượng trong phạm vi mạng nội bộ theo cấu hình.

Chúng hữu ích khi:

- Database hoặc API chỉ cần được gọi bởi workload trong những mạng được phê duyệt.
- Dữ liệu không cần đi qua endpoint công khai.
- Muốn quản lý đường đi, DNS và chính sách firewall rõ ràng.
- Có ràng buộc kết nối hybrid hoặc phân đoạn theo môi trường.

Private endpoint vẫn phải được bảo vệ bằng IAM, network policy và xác thực ở dịch vụ. Trong một số dịch vụ, private DNS, endpoint policy hoặc quyền của principal phải cấu hình riêng. Một private endpoint không tự đảm bảo chỉ một ứng dụng truy cập được.

### 5.3. Service discovery và DNS nội bộ

Các workload thường dùng tên logic như payments.internal thay vì gắn cứng IP của một instance. Service discovery/DNS ánh xạ tên tới địa chỉ hoặc endpoint phù hợp khi replica, Region hay deployment thay đổi.

Cần thiết kế:

- Namespace và tên dịch vụ theo môi trường, ví dụ payments.prod.internal và payments.staging.internal.
- DNS zone riêng, resolver, forwarding và quyền quản lý record.
- TTL phù hợp với mục tiêu chuyển đổi; TTL quá dài có thể giữ địa chỉ cũ, quá ngắn có thể tăng tải DNS.
- Phân quyền truy cập endpoint và xác minh chứng chỉ TLS đúng tên.
- Tránh để dịch vụ non-prod phân giải nhầm tới endpoint prod.

## 6. Xác thực, phân quyền và mã hóa giữa các dịch vụ

### 6.1. Authentication và authorization là hai bước khác nhau

- **Authentication (xác thực):** Ai hoặc workload nào đang gọi?
- **Authorization (phân quyền):** Danh tính đó được thực hiện hành động nào trên resource nào?

Ví dụ, Booking API được xác thực bằng workload identity và gọi được Payments API. Điều đó chưa đồng nghĩa nó được quyền **hoàn tiền**, xem toàn bộ lịch sử thẻ hoặc sửa cấu hình thanh toán. Authorization cần phân quyền theo scope, action và dữ liệu, có thể ở API gateway, service hoặc hệ thống policy.

### 6.2. TLS và mTLS

**TLS** bảo vệ dữ liệu trên đường truyền và giúp client xác minh server dựa trên chứng chỉ. **Mutual TLS (mTLS)** bổ sung xác thực chứng chỉ của client với server. mTLS thường hữu ích khi service-to-service cần danh tính ở lớp kết nối.

~~~mermaid
sequenceDiagram
    participant B as Booking API
    participant P as Payments API
    B->>P: Kết nối TLS + client identity (mTLS nếu dùng)
    P-->>B: Xác minh chứng chỉ/client trust
    B->>P: Request kèm token/scope nghiệp vụ nếu cần
    P->>P: Xác thực và kiểm tra quyền
    P-->>B: Response theo policy
~~~

mTLS không tự thay thế authorization nghiệp vụ. Một chứng chỉ xác minh workload có thể chỉ chứng minh “caller là Booking API”, không quyết định nó được phép thực hiện hành động nào. Token OAuth hoặc cơ chế policy có thể bổ sung scope/claim theo thiết kế.

Nếu sử dụng chứng chỉ, phải có quy trình **cấp phát, xoay vòng, thu hồi, quản lý trust bundle và xử lý hết hạn**. Chứng chỉ tĩnh lưu trong image lâu dài dễ trở thành credential khó kiểm soát.

### 6.3. API gateway và service mesh

| Cơ chế | Vai trò | Phù hợp khi | Giới hạn |
|---|---|---|---|
| **API Gateway** | Điểm vào API có chính sách xác thực, rate limit, routing, logging và chuyển đổi | API dành cho client/đối tác hoặc cần governance tập trung | Không nhất thiết là nơi duy nhất cho mọi giao tiếp nội bộ; vẫn cần bảo vệ backend trực tiếp |
| **Internal API gateway** | Kiểm soát một tập luồng API nội bộ | Nhiều nhóm dịch vụ cần policy/API catalog chung | Thêm hop, phí, cấu hình và một phụ thuộc cần HA |
| **Service mesh** | Hỗ trợ service discovery/traffic policy, telemetry và mTLS giữa workload tùy sản phẩm | Nhiều service, cần quản lý giao tiếp đông và có chuẩn chung | Tăng độ phức tạp control plane/data plane, debug và vận hành |
| **Workload identity trực tiếp** | Dịch vụ nhận credential theo danh tính compute | Kiến trúc đơn giản hoặc nền tảng có IAM đủ năng lực | Cần tự quản lý policy ứng dụng, network và quan sát phù hợp |

Không nên đưa service mesh hoặc gateway vào chỉ vì kiến trúc cloud-native được kỳ vọng có chúng. Chọn theo số lượng dịch vụ, nhóm sở hữu, yêu cầu bảo mật, cách định tuyến và năng lực vận hành.

## 7. Truy cập dữ liệu, secret và hệ thống quản lý

### 7.1. Quyền truy cập database

Database nên nhận kết nối từ workload hoặc nhóm nguồn được phép, qua mạng thích hợp và với credential/quyền tối thiểu. Một số nguyên tắc:

- Không mở port database rộng tới Internet công cộng chỉ để nhân viên truy cập bằng GUI.
- Dùng private network/private endpoint khi phù hợp; giới hạn nguồn, port và đường kết nối.
- Workload dùng database principal riêng theo ứng dụng hoặc vai trò; tránh một tài khoản DBA dùng chung cho toàn bộ API.
- Tách quyền đọc/ghi và schema khi yêu cầu; không cấp quyền DDL hoặc admin cho ứng dụng runtime nếu không cần.
- Quản lý connection pool, timeout, TLS, rotation và audit; kiểm tra quyền thực tế chứ không chỉ cấu hình ở firewall.

### 7.2. Quản lý secret

Mật khẩu, API key, private key, token và connection string nhạy cảm cần được lưu trong **secret manager/key vault** phù hợp. Workload identity được cấp quyền lấy secret đúng phạm vi và thời gian; không ghi secret vào log hoặc sơ đồ/ADR.

Xoay vòng credential có thể làm gián đoạn dịch vụ nếu ứng dụng không chịu được giai đoạn chuyển đổi. Cần thiết kế quy trình overlap credential, rollout, xác minh kết nối mới và thu hồi credential cũ. Không xoay khóa đột ngột nếu chưa biết những ứng dụng nào còn phụ thuộc.

### 7.3. Đường truy cập hệ thống quản lý cloud

Cloud console và management API thường có endpoint riêng với resource/data API. Tổ chức nên:

- Bảo vệ đăng nhập bằng SSO, MFA và policy thiết bị/ngữ cảnh nếu có.
- Dùng role/permission set theo account/subscription/project và trách nhiệm công việc.
- Giới hạn quyền tạo/sửa IAM, network, public endpoint, key và logging.
- Tách automation identity khỏi user identity; pipeline không dùng personal access key không kiểm soát.
- Duy trì audit log ở phạm vi khó bị workload hoặc người quản trị thông thường sửa/xóa.
- Xem xét hạn chế quản trị từ thiết bị/mạng không được quản lý nếu quy định công ty yêu cầu.

## 8. Quy trình triển khai và automation identity

Pipeline CI/CD cũng là một **điểm vào quản trị** vì có thể tạo hoặc thay đổi tài nguyên production. Cần coi danh tính pipeline như một principal đặc quyền:

1. Mỗi dự án hoặc môi trường có workload identity/service principal thích hợp.
2. Pipeline xác thực qua OIDC federation hoặc cơ chế ngắn hạn được nền tảng hỗ trợ, khi có thể.
3. Credential không nằm trong source code; secret dùng trong pipeline phải được bảo vệ và giới hạn.
4. Role deploy chỉ được thay đổi các tài nguyên mà pipeline phụ trách.
5. Thay đổi hạ tầng và quyền cần được review, policy check và approval theo mức rủi ro.
6. Ghi lại người khởi tạo, revision, artifact, danh tính pipeline và scope thay đổi.
7. Với release thất bại, rollback theo quy trình; không cấp quyền admin rộng cho pipeline chỉ để tránh xử lý lỗi.

**Tách build khỏi deploy:** Build artifact có thể chạy trong môi trường build ít đặc quyền; deploy prod dùng identity riêng ở bước phát hành. Điều này giảm nguy cơ mã build hoặc dependency chưa tin cậy thừa hưởng quyền sửa production.

~~~mermaid
flowchart LR
    DEV["Developer"] --> PR["Pull request / review"]
    PR --> BUILD["Build + test + scan"]
    BUILD --> ART["Signed artifact"]
    ART --> APPROVE["Release approval / policy"]
    APPROVE --> FED["Workload federation"]
    FED --> ROLE["Short-lived deploy role"]
    ROLE --> PROD["Production resources"]
    PROD -. "Audit events" .-> LOG["Central audit"]
~~~

Các bước này là mô hình minh họa; công cụ Git, pipeline, registry và cloud provider khác nhau. Quan trọng là pipeline không trở thành đường vòng bỏ qua SSO, phê duyệt và audit.

## 9. Các rủi ro khi gộp đường quản trị với đường dịch vụ

### 9.1. Dùng chung một danh tính

Nếu admin và runtime service dùng cùng một credential, một lỗi trong ứng dụng có thể sử dụng quyền quản trị tài nguyên; khi credential bị lộ, phạm vi ảnh hưởng lớn hơn nhiều. **Giải pháp:** tách user identity, automation identity và workload identity; phân quyền theo nhiệm vụ.

### 9.2. Để endpoint quản trị công khai không kiểm soát

Một dashboard hoặc API quản trị được công khai có thể bị dò quét, brute force hoặc khai thác lỗi ứng dụng. **Giải pháp:** dùng điểm vào quản trị có xác thực mạnh, hạn chế nguồn/điều kiện truy cập, private access hoặc ZTNA khi phù hợp; theo dõi đăng nhập và hành động đặc quyền.

### 9.3. Tin rằng mạng private đồng nghĩa an toàn

Kẻ tấn công có thể di chuyển ngang nếu một workload trong mạng private bị xâm nhập và có quyền quá rộng. **Giải pháp:** phân đoạn mạng, workload identity, mTLS/TLS, authorization ở dịch vụ, quản lý secret và giới hạn egress.

### 9.4. Cho phép admin dùng cùng đường vào database với ứng dụng

Quản trị viên truy cập trực tiếp tới database từ laptop có thể tạo đường mở rộng không kiểm soát, trong khi ứng dụng runtime cần kết nối liên tục. **Giải pháp:** đường quản trị riêng được phê duyệt/audit; workload dùng identity và quyền database riêng.

### 9.5. Không có audit log độc lập

Nếu người có quyền admin có thể xóa cả log do chính họ tạo, kiểm toán mất bằng chứng. **Giải pháp:** tập trung log sang phạm vi khác, giới hạn quyền xóa, bảo vệ retention/immutability nếu phù hợp và cảnh báo khi logging bị tắt.

### 9.6. Không kiểm thử break-glass và thu hồi quyền

Credential khẩn cấp có thể lỗi, hoặc role tạm thời không hết hạn. **Giải pháp:** kiểm tra định kỳ trong môi trường an toàn, diễn tập, theo dõi TTL và rà soát phiên/quyền sau sự cố.

### 9.7. Quá nhiều lớp truy cập không có chủ sở hữu

VPN, bastion, gateway, proxy và service mesh có thể cùng tồn tại, mỗi lớp có policy riêng. **Giải pháp:** lập sơ đồ đường vào và luồng dịch vụ, chỉ rõ ai sở hữu, ai cấp quyền, nơi lưu log và cách xử lý lỗi của từng lớp.

## 10. Ví dụ thiết kế: hệ thống đặt chỗ trên cloud

### Bối cảnh

Doanh nghiệp vận hành Booking API và Payments API trong các mạng riêng. Đội Platform quản lý hạ tầng cloud; nhóm Security kiểm toán chính sách và log; đội Booking deploy thường xuyên; ứng dụng cần gọi database và queue.

### Mô hình quyền và điểm vào

| Chủ thể | Điểm vào | Danh tính | Phạm vi quyền |
|---|---|---|---|
| Developer Booking | SSO → cloud portal/dev tools | User identity + MFA | Dev environment, đọc log/metric theo scope |
| Release pipeline Booking | CI/CD → federation → cloud role | booking-deploy-prod | Deploy Booking API và cấu hình runtime được duyệt |
| Booking API | Private service endpoint | booking-api-prod | Gọi Payments API theo scope, truy cập bảng Booking cần thiết |
| Notification Worker | Queue endpoint private | notification-worker-prod | Đọc queue, lấy secret gửi email |
| Platform admin | SSO/JIT → management API | Admin identity | Quản trị mạng, compute, policy ở phạm vi được giao |
| Security auditor | SSO → audit/security console | Auditor identity | Đọc audit log và trạng thái bảo mật, không xóa log |
| Break-glass operator | Emergency path được kiểm soát | Credential khẩn cấp riêng | Thao tác phục hồi hạn chế, có cảnh báo và post-review |

### Ma trận luồng

| Nguồn | Đích | Luồng | Kiểm soát |
|---|---|---|---|
| Admin laptop/managed device | Management console/API | HTTPS quản trị | SSO, MFA, conditional access, role/JIT, audit |
| CI/CD | Cloud management API | Deploy tài nguyên | Federation, identity riêng, scope hẹp, approval |
| Booking API | Payments API | HTTPS private | Route/firewall, TLS hoặc mTLS, workload identity, authorization |
| Booking API | Database | Database protocol private | Private endpoint, TLS, database principal và quyền schema |
| Booking API | Message queue | Queue protocol/API | Workload identity, quyền publish, network policy |
| Notification Worker | Email Provider | HTTPS outbound | Egress policy, secret manager, retry và log đã lọc dữ liệu nhạy cảm |
| Security platform | Central audit store | Thu log và cảnh báo | Quyền ghi/đọc tách biệt, retention bảo vệ |

**Điểm cần chú ý:** Developer có thể xem log ứng dụng nhưng không mặc nhiên đọc secret; pipeline có thể triển khai API nhưng không có quyền truy cập bảng thanh toán; Booking API có thể gọi endpoint Payments được phép nhưng không được dùng role deploy để thay đổi cấu hình Payments. Cùng nằm trong cloud organization không có nghĩa chia sẻ chung một quyền quản trị.

## 11. Kiểm thử và vận hành truy cập

Thiết kế truy cập chỉ có giá trị khi được kiểm chứng bằng các tình huống cho phép và từ chối:

| Kiểm thử | Kết quả mong đợi | Bằng chứng |
|---|---|---|
| Developer đăng nhập bằng SSO và MFA | Chỉ nhận role/scope đúng nhiệm vụ | IdP sign-in log, cloud audit event |
| Developer thử sửa database prod | Bị từ chối | Authorization denial, alert/audit |
| Pipeline Booking deploy Booking-prod | Thành công qua identity riêng, revision được ghi nhận | CI/CD logs, cloud audit, artifact identity |
| Pipeline Booking thử sửa Payments-prod | Bị từ chối | Role scope, policy evaluation |
| Booking API gọi Payments API | Được phép qua private endpoint với danh tính hợp lệ | Network flow, TLS/mTLS log, application audit |
| Một workload lạ gọi Payments API | Bị chặn ở network hoặc service authorization | Denied connection/request và cảnh báo |
| Credential/role tạm hết hạn | Không thể tiếp tục thao tác sau thời hạn | Token expiry, IAM/JIT audit |
| Break-glass được kích hoạt | Phát cảnh báo, sự kiện được audit và hậu kiểm | Alert delivery, incident record |
| Logging bị tắt hoặc không gửi được | Có cảnh báo và quy trình xử lý | Monitoring health, independent audit |

### Các chỉ số nên quan sát

- Số lượng tài khoản đặc quyền và quyền không sử dụng.
- Số lần nâng quyền JIT, thời lượng và tỷ lệ yêu cầu bị từ chối.
- Đăng nhập bất thường, xác thực thất bại và phiên ở thiết bị không được quản lý.
- Lưu lượng east-west giữa workload, denied connection, lỗi TLS và lỗi authorization.
- Secret access, rotation, token issuance và credential hết hạn.
- Pipeline deploy thành công/thất bại, thay đổi policy/IAM và rollback.
- Tình trạng audit log, độ trễ thu nhận, retention và quyền xóa.

Không nên thu thập quá mức dữ liệu cá nhân hoặc payload nhạy cảm chỉ để “có log”. Log cần phục vụ điều tra và vận hành, với phân quyền người đọc, chính sách lưu giữ và biện pháp bảo vệ thích hợp.

## 12. Đánh giá theo Well-Architected

| Khía cạnh | Câu hỏi cho truy cập quản trị | Câu hỏi cho truy cập dịch vụ |
|---|---|---|
| **Vận hành xuất sắc** | Có quy trình JIT, break-glass, review và thu hồi role? | Có service inventory, rotation, runbook và quan sát luồng gọi? |
| **Bảo mật** | SSO/MFA, quyền tối thiểu, thiết bị và audit có đủ? | Workload identity, TLS/mTLS, authorization, secret và network policy có đúng? |
| **Độ tin cậy** | Nếu IdP hoặc hệ thống cấp quyền lỗi, khôi phục quản trị thế nào? | Nếu DNS, identity provider, private endpoint hoặc service mesh lỗi, nghiệp vụ phản ứng ra sao? |
| **Hiệu quả hiệu năng** | SSO/proxy có làm chậm thao tác vận hành thường xuyên? | Gateway, mesh, TLS và kiểm tra policy có thêm latency/throughput overhead? |
| **Tối ưu chi phí** | Chi phí platform access, logging và bastion có phù hợp? | Chi phí private endpoint, NAT, gateway, mesh và telemetry tăng theo số service ra sao? |
| **Bền vững** | Có loại bỏ bastion/máy quản trị nhàn rỗi và log không cần thiết? | Có right-size gateway/mesh, tránh lưu telemetry quá mức và xoay vòng tài nguyên không? |

### Phân tích một số đánh đổi

**Tập trung danh tính** giúp quản lý vòng đời nhân viên và policy thống nhất, nhưng IdP trở thành phụ thuộc quan trọng của quản trị. Cần dự phòng và quy trình khẩn cấp. **Phân quyền JIT** giảm quyền thường trực nhưng làm tăng độ trễ khi xử lý sự cố; quy trình phê duyệt phải đủ nhanh và có break-glass được kiểm soát.

**Private endpoint** giảm exposure công khai nhưng tăng cấu hình DNS, route, endpoint policy và chi phí; phải quản trị vòng đời endpoint. **mTLS** giúp nhận diện workload ở lớp kết nối nhưng tạo gánh nặng cấp/đổi/thu hồi chứng chỉ. **Service mesh** có thể chuẩn hóa nhiều luồng nhưng thêm control plane, proxy và chi phí vận hành. Chọn theo rủi ro thực tế và năng lực đội ngũ.

Mục tiêu ví dụ như “mọi quyền admin prod có MFA và audit”, “chỉ workload Booking được gọi Payments API theo scope được phép” hoặc “thu hồi role tạm trong một thời hạn xác định” cần được biến thành policy test, phép thử truy cập và cảnh báo. Đừng kết luận hệ thống an toàn chỉ vì đã bật SSO hoặc đặt API trong subnet private.

## 13. Quy trình thiết kế access architecture

Một quy trình có thể áp dụng cho dự án mới hoặc rà soát hệ thống hiện tại:

1. **Kiểm kê tác nhân:** Con người, nhóm, nhà cung cấp, pipeline, ứng dụng, worker và dịch vụ quản lý.
2. **Liệt kê hành động:** Đăng nhập, deploy, xem log, truy cập database, gọi API, quản lý secret, thay policy, khôi phục và xóa tài nguyên.
3. **Chia management plane và service/data plane:** Xác định endpoint, mạng, danh tính, dữ liệu và chủ sở hữu từng đường.
4. **Chọn cơ chế xác thực:** SSO/federation/MFA cho người; workload identity, certificate, OAuth hoặc credential ngắn hạn cho dịch vụ.
5. **Thiết kế authorization:** Role, scope, action, condition, thời hạn và người phê duyệt; tách quyền runtime khỏi quyền deploy.
6. **Thiết kế network path:** Public/private endpoint, VPN/ZTNA/bastion, route, firewall, DNS, egress và service discovery.
7. **Bảo vệ secret và dữ liệu:** Secret manager, TLS/mTLS, database principal, mã hóa và rotation.
8. **Thiết kế audit và phát hiện:** Log đăng nhập, nâng quyền, thao tác quản trị, service call, denied access và thay đổi logging.
9. **Kiểm thử quyền cho phép/từ chối:** Xác minh các luồng hợp lệ và các truy cập ngoài phạm vi.
10. **Vận hành vòng đời:** Review, thu hồi, thay chứng chỉ/secret, xử lý nhân viên nghỉ việc, incident và break-glass.

### ADR minh họa — Tách đường quản trị khỏi service-to-service

> **Bối cảnh:** Nhân viên vận hành và Booking API hiện cùng sử dụng một credential có quyền đọc/ghi cấu hình production để kết nối tới Payments API và theo dõi trạng thái.
>
> **Quyết định:** Dùng SSO + MFA + role/JIT riêng cho nhân viên; pipeline có federation và role deploy; Booking API có workload identity riêng với scope gọi Payments API; các service endpoint dùng private connectivity và TLS/mTLS theo yêu cầu. Audit log quản trị và log workload được thu tập trung với quyền xóa tách biệt.
>
> **Lý do:** Giảm quyền, tách vòng đời credential và giới hạn blast radius nếu máy chủ hoặc người dùng bị xâm nhập.
>
> **Đánh đổi:** Tăng số identity, policy, quy trình cấp quyền và thành phần quan sát; cần tự động hóa provisioning/rotation và vận hành IdP/private endpoint.
>
> **Kiểm chứng:** Developer không sửa được Payments-prod; Booking API gọi được đúng API/operation; workload lạ bị từ chối; quyền JIT hết hạn; break-glass tạo alert và audit record.

## 14. Bài tập thực hành

Một hệ thống thương mại điện tử đang dùng một tài khoản admin chung cho ba mục đích: deploy ứng dụng, kết nối database và truy cập cloud console. API và worker chạy trong mạng private; dashboard quản trị lại được publish trên public Internet bằng mật khẩu tĩnh. Developer có thể đọc secret của production để debug.

**Yêu cầu:**

1. Chỉ ra ít nhất năm rủi ro trong cách tổ chức hiện tại.
2. Thiết kế lại danh tính cho Developer, Platform Admin, CI/CD, API, Worker và Security Auditor.
3. Vẽ luồng quản trị từ thiết bị nhân viên tới cloud management plane.
4. Vẽ luồng service-to-service giữa API, database, queue và worker.
5. Đưa ra cách bảo vệ dashboard quản trị và database; nói rõ khi nào dùng private endpoint, VPN, bastion hoặc ZTNA.
6. Thiết kế JIT và break-glass; ghi cách kiểm tra audit log độc lập.
7. Lập bảng test cho cả truy cập được phép và truy cập phải bị từ chối.

### Hướng giải quyết

- Loại bỏ tài khoản admin dùng chung; chuyển sang user identity cá nhân qua SSO/MFA và role có scope.
- CI/CD dùng identity riêng qua federation/credential ngắn hạn, chỉ deploy đúng ứng dụng.
- API và worker dùng workload identity tách biệt; API có quyền database cần thiết và gọi queue; worker chỉ đọc queue và gọi provider tương ứng.
- Dashboard quản trị chuyển về điểm vào có SSO/MFA và kiểm soát thiết bị/nguồn; chỉ mở Internet công khai khi có lý do và các lớp bảo vệ được đánh giá đầy đủ.
- Database không public; ứng dụng kết nối qua private endpoint/network với principal riêng. Nhân viên truy cập quản trị database qua quy trình được phê duyệt và audit.
- Secret chỉ được cấp cho workload đúng scope từ secret manager; developer không đọc secret prod mặc định. Debug dùng log/trace đã lọc dữ liệu nhạy cảm và quyền truy cập có kiểm soát.
- Thiết lập role JIT, credential break-glass được bảo vệ, cảnh báo tức thời và hậu kiểm.
- Kiểm tra các hành động bị từ chối, thu hồi quyền, rotation và độ đầy đủ của audit log.

### Câu hỏi tự kiểm tra

1. Vì sao đăng nhập qua SSO chưa đủ để chứng minh người dùng được phép xóa database?
2. Vì sao workload identity tốt hơn việc nhúng access key dài hạn trong image?
3. Private endpoint có bảo đảm mọi client trong mạng đều được phép gọi API không? Cần những lớp kiểm soát gì khác?
4. Khi nào bastion hữu ích, và nó tạo thêm những trách nhiệm vận hành nào?
5. mTLS chứng minh điều gì ở lớp kết nối, và vì sao vẫn cần authorization ở tầng ứng dụng?
6. Làm thế nào thiết kế break-glass để có khả năng phục hồi mà không trở thành tài khoản admin dùng chung?
7. Nếu IdP tạm thời không khả dụng, những hoạt động quản trị nào bị ảnh hưởng và quy trình khẩn cấp phải hoạt động ra sao?

Một kiến trúc truy cập cloud tốt mô tả rõ **ai hoặc workload nào đang truy cập, đi qua điểm vào nào, tới tài nguyên nào, bằng quyền gì và để làm gì**. Khi quản trị con người được tách khỏi truy cập dịch vụ, danh tính và luồng dữ liệu có thể được giới hạn, kiểm toán và kiểm thử riêng; từ đó giảm rủi ro nhưng vẫn duy trì khả năng vận hành, triển khai và mở rộng ứng dụng.
