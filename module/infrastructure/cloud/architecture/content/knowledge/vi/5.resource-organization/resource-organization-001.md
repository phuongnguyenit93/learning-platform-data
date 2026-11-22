# Thiết kế landing zone và các năng lực nền tảng tối thiểu

## 1. Landing zone là gì và giải quyết vấn đề nào?

Khi một đội phát triển bắt đầu dùng cloud, cách đơn giản nhất có vẻ là tạo một tài khoản, một mạng, vài máy chủ và cơ sở dữ liệu. Hệ thống có thể chạy nhanh, nhưng khi số đội, môi trường và dữ liệu tăng lên, nhiều câu hỏi xuất hiện: ai được tạo tài nguyên, ai xem log, tài khoản nào trả chi phí, dữ liệu production cách ly với môi trường thử nghiệm ra sao, kết nối tới hệ thống nội bộ bằng cách nào và khi mất quyền truy cập quản trị thì ai xử lý?

**Cloud landing zone** là **môi trường nền tảng được chuẩn bị và quản trị có chủ đích**, trong đó các ứng dụng có thể được triển khai với các quy tắc chung về tổ chức tài nguyên, danh tính, mạng, bảo mật, quản lý, ghi nhận hoạt động và chi phí. Landing zone gồm **cấu trúc, kiểm soát, quy trình vận hành và tự động hóa**; nó không chỉ là một VPC/VNet, một Kubernetes cluster hay một bộ Terraform.

Trong module **CLOUD_ARCHITECTURE**, landing zone là nền móng nối yêu cầu nghiệp vụ với lựa chọn mạng, compute, dữ liệu và mô hình triển khai. Khi thiết kế kiến trúc cần cân nhắc độ tin cậy, bảo mật, mở rộng, chi phí và vận hành, landing zone giúp các yêu cầu đó được thực thi nhất quán ngay từ đầu, thay vì để từng nhóm ứng dụng giải quyết riêng.

**Ví dụ:** một nền tảng đặt chỗ cần môi trường production có giám sát, sao lưu và quyền chặt chẽ; môi trường development cần linh hoạt nhưng vẫn giới hạn ngân sách. Landing zone tạo các ranh giới và năng lực chung để hai môi trường có thể phát triển mà không vô tình chia sẻ toàn bộ quyền, mạng hay dữ liệu.

### Kết quả cần đạt

Sau bài học, bạn có thể:

1. Giải thích landing zone, phân biệt **platform foundation**, **application workload** và **các dịch vụ dùng chung**.
2. Phác thảo cấu trúc tổ chức tài nguyên theo đội, môi trường, rủi ro, chi phí và phạm vi quản trị.
3. Xác định các năng lực nền tảng tối thiểu trước khi đưa một workload quan trọng lên cloud.
4. Mô tả luồng cấp môi trường mới bằng hạ tầng dưới dạng mã (Infrastructure as Code, IaC) và chính sách guardrail.
5. Đánh giá các đánh đổi của landing zone theo tư duy Well-Architected, từ độ tin cậy và bảo mật đến vận hành và chi phí.

## 2. Phạm vi thiết kế: nền tảng, workload và trách nhiệm

Landing zone hữu ích khi quyền sở hữu được xác định rõ:

| Phạm vi | Thường do ai phụ trách? | Quyết định tiêu biểu |
|---|---|---|
| **Tổ chức cloud và quản trị chung** | Cloud platform, security, IT governance | Cấu trúc tài khoản/subscription/project, danh tính, chính sách tổ chức, quy tắc tạo môi trường |
| **Năng lực nền tảng dùng chung** | Platform/network/security/operations | Kết nối, DNS, tập trung audit, giám sát cơ bản, secrets/keys, công cụ IaC và quy trình cấp phát |
| **Workload ứng dụng** | Product team, developer, SRE của dịch vụ | Chọn compute, thiết kế DB, API, cache, queue, scaling, SLO, backup theo yêu cầu nghiệp vụ |
| **Kiểm soát và đảm bảo tuân thủ** | Security/compliance phối hợp cùng chủ sở hữu | Phân loại dữ liệu, quy định lưu giữ, mã hóa, phân quyền, bằng chứng kiểm toán, chấp nhận rủi ro |
| **Tài chính và tối ưu tài nguyên** | Finance/FinOps cùng các chủ sở hữu workload | Tag/label, ngân sách, phân bổ chi phí, cảnh báo, hạn mức, đánh giá hiệu quả sử dụng |

Trong đội nhỏ, một người có thể đảm nhiệm nhiều vai trò. Điều quan trọng không phải có nhiều phòng ban, mà là **mỗi quyết định và mỗi cảnh báo đều có người chịu trách nhiệm**.

Một landing zone **không** tự bảo đảm ứng dụng tuân thủ mọi yêu cầu. Ví dụ, có cấu hình mã hóa ở tầng lưu trữ không giải quyết được lỗi kiểm tra quyền trong API; đã tạo backup không có nghĩa đã khôi phục thử thành công. Nền tảng cung cấp baseline và công cụ, còn workload phải thiết kế đúng hành vi ứng dụng.

## 3. Những đầu vào cần làm rõ trước khi thiết kế

Không nên chọn cấu trúc tài khoản hay mô hình mạng trước khi hiểu quy mô và ràng buộc. Trả lời tối thiểu các nhóm câu hỏi sau:

| Nhóm câu hỏi | Ví dụ cần làm rõ | Hệ quả lên landing zone |
|---|---|---|
| **Nghiệp vụ** | Hệ thống nội bộ, sản phẩm khách hàng hay ứng dụng xử lý giao dịch? Mức độ quan trọng? | Mức cô lập, bảo vệ và quy trình thay đổi |
| **Đội ngũ và quyền sở hữu** | Có mấy product team, ai quản trị tenant/cloud organization và ai trực sự cố? | Phân cấp quyền, quyền tự phục vụ, định tuyến cảnh báo |
| **Môi trường** | Dev, test, staging, production có yêu cầu dữ liệu và quyền khác nhau ra sao? | Ranh giới tài khoản/subscription/project, chính sách truy cập |
| **Bảo mật và dữ liệu** | Có dữ liệu cá nhân/nhạy cảm? Khu vực lưu trữ, thời hạn lưu giữ, yêu cầu audit? | Data residency, chính sách region, log, KMS, quyền và kiểm soát xuất dữ liệu |
| **Kết nối** | Có văn phòng, trung tâm dữ liệu, bên thứ ba, dịch vụ public/private nào? | CIDR/IPAM, DNS, routing, VPN/private circuit, ingress/egress |
| **Tin cậy và phục hồi** | SLO ứng dụng, RTO/RPO cho từng loại sự cố, mức chấp nhận gián đoạn? | Vùng triển khai, backup, failover, kiểm tra khôi phục |
| **Tài chính** | Ngân sách ban đầu, tăng trưởng dự báo, cách phân bổ chi phí? | Billing hierarchy, tags/labels, quota, cảnh báo và tự dọn tài nguyên |
| **Tự động hóa** | Quản lý IaC ở đâu, ai duyệt thay đổi, ai nhận môi trường mới? | Bootstrap, pipeline, policy as code, cấu hình chuẩn |

Các chỉ tiêu như SLO, RPO hay RTO phải do chủ sở hữu nghiệp vụ xác nhận theo kịch bản đo cụ thể. Không nên lấy một “best practice” chung làm cam kết cho mọi ứng dụng.

## 4. Tổ chức tài nguyên: ranh giới chính và cách đặt tên

Hầu hết nền tảng cloud có nhiều cấp quản lý tài nguyên. Khái niệm tương đương không hoàn toàn giống nhau, nhưng đều giúp áp dụng quyền, chính sách, billing và cô lập trên phạm vi xác định.

| Nhu cầu logic | AWS (ví dụ) | Azure (ví dụ) | Google Cloud (ví dụ) |
|---|---|---|---|
| Gốc tổ chức và quản trị | AWS Organizations | Microsoft Entra tenant cùng hệ thống Azure management groups | Organization resource |
| Nhóm phạm vi quản trị | Organizational Unit (OU) | Management group | Folder |
| Ranh giới sở hữu tài nguyên và thường cả giới hạn/billing | AWS account | Subscription | Project |
| Nhóm tài nguyên trong ranh giới | Tags, các cấu trúc theo dịch vụ | Resource group | Resource hierarchy/labels và tài nguyên theo service |
| Kiểm soát chính sách cấp cao | Service Control Policies (SCP) và các cơ chế bổ trợ | Azure Policy và RBAC | Organization Policy và IAM |

**Lưu ý:** đây là đối chiếu theo mục tiêu thiết kế, không phải ánh xạ một-một về hành vi hay khả năng. AWS account, Azure subscription và Google Cloud project khác nhau về quyền, quota, billing, kế thừa chính sách và một số ranh giới kỹ thuật; cần kiểm tra tài liệu và các dịch vụ thực tế trước khi triển khai.

### 4.1. Phân tách production, non-production và nền tảng

Một cấu trúc **tham khảo** cho tổ chức có vài đội sản phẩm:

~~~mermaid
flowchart TD
    Org["Cloud organization / Tenant"]
    Org --> Sec["Security & Audit"]
    Org --> Platform["Shared Platform"]
    Org --> Workloads["Workloads"]
    Sec --> Log["Centralized logging"]
    Sec --> Security["Security tooling"]
    Platform --> Network["Connectivity & DNS"]
    Platform --> Tooling["IaC / CI-CD platform"]
    Workloads --> Prod["Production boundary"]
    Workloads --> NonProd["Non-production boundary"]
    Prod --> BookingProd["Booking prod"]
    Prod --> CatalogProd["Catalog prod"]
    NonProd --> BookingDev["Booking dev/test"]
    NonProd --> CatalogDev["Catalog dev/test"]
~~~

*Sơ đồ là mô hình **logic**. Một ô có thể tương ứng với account/subscription/project hoặc nhóm tài nguyên khác nhau tùy nhà cung cấp và nhu cầu cô lập.*

Các nguyên tắc thiết kế:

1. **Tách ranh giới theo mức rủi ro:** production và môi trường thử nghiệm không dùng chung đặc quyền quản trị hoặc dữ liệu nhạy cảm nếu không có lý do và biện pháp kiểm soát được duyệt.
2. **Giảm blast radius:** lỗi cấu hình, vượt quota hoặc chiếm quyền ở một workload không nên mặc nhiên có quyền phá hủy workload khác.
3. **Quyền sở hữu rõ:** một ranh giới có người phụ trách chi phí, vận hành, phân quyền và vòng đời.
4. **Chính sách kế thừa có chủ đích:** baseline áp dụng từ tổ chức hoặc nhóm quản trị; ngoại lệ được ghi nhận, hết hạn và có người phê duyệt.
5. **Đừng chia quá vụn:** mỗi tài khoản/project mới tạo chi phí quản lý quyền, logging, networking, quota và vận hành. Chỉ tách thêm khi rủi ro hoặc yêu cầu độc lập biện minh được.

Nếu công ty có một ứng dụng và một nhóm nhỏ, landing zone có thể đơn giản hơn nhiều. Điều cần giữ là các ranh giới quan trọng, không phải tạo đủ mọi tầng tổ chức như sơ đồ.

### 4.2. Quy ước tên, tag/label và vòng đời

Tên giúp con người nhận diện; tag/label hỗ trợ automation, báo cáo và quản lý chi phí. Một quy ước nên ngắn, ổn định, tránh dữ liệu bí mật và có máy kiểm tra được:

~~~yaml
# Ví dụ metadata logic cho một workload; không phải cú pháp
# khai báo tài nguyên dùng chung cho mọi cloud provider.
workload: booking
environment: prod
region: primary-region
owner_team: reservations
technical_contact: platform-oncall
cost_center: product-booking
data_classification: confidential
criticality: high
managed_by: infrastructure-as-code
~~~

Tùy hệ thống, có thể bổ sung service, application, business_unit, expiry_date cho sandbox. Tránh để tên người cụ thể, email cá nhân hoặc thông tin nhạy cảm trong tag nếu cơ chế hiển thị/billing cho phép người ngoài phạm vi cần biết truy cập chúng.

Không mặc định rằng tất cả loại tài nguyên đều hỗ trợ tag giống nhau. Nên có **danh sách trường bắt buộc**, giá trị hợp lệ và cách kiểm tra khi tạo mới; với tài nguyên không hỗ trợ, sử dụng inventory/CMDB hoặc nguồn metadata tương ứng. Tag không phải cơ chế bảo mật thay cho IAM hay policy.

## 5. Danh tính và quyền: năng lực đầu tiên cần có

Trước khi một đội có thể tạo tài nguyên production, cần trả lời: **người nào, workload nào và pipeline nào được cấp quyền gì, trong bao lâu, ở phạm vi nào**?

### 5.1. Baseline truy cập

- **Federation/SSO:** tích hợp danh tính doanh nghiệp nếu có, tránh nhân bản tài khoản quản trị dài hạn không cần thiết.
- **MFA:** yêu cầu xác thực đa yếu tố cho người dùng, đặc biệt các quyền nhạy cảm, theo khả năng của nhà cung cấp và chính sách tổ chức.
- **Least privilege:** cấp quyền tối thiểu cần thiết cho vai trò; tách quyền đọc, triển khai, vận hành và thay đổi chính sách tổ chức.
- **Phân biệt người và workload:** ứng dụng/pipeline dùng workload identity, role hoặc token ngắn hạn theo cơ chế hỗ trợ; hạn chế khóa truy cập tĩnh.
- **Privileged access:** các quyền nâng cao được cấp có thời hạn khi có thể, có ghi dấu thao tác và quy trình xét duyệt.
- **Emergency access:** có đường truy cập khẩn cấp được bảo vệ, kiểm soát riêng và diễn tập; tránh phụ thuộc duy nhất vào hệ thống SSO đang gặp sự cố.
- **Quản lý vòng đời:** khi nhân viên đổi vai trò/nghỉ việc, quyền được thu hồi; quyền đặc biệt được rà soát định kỳ.

### 5.2. Ví dụ mô hình quyền

| Vai trò | Quyền điển hình | Quyền nên hạn chế |
|---|---|---|
| Platform administrator | Quản lý cấu trúc tổ chức, baseline và quy trình cấp môi trường | Truy cập dữ liệu nghiệp vụ nếu không cần |
| Security auditor | Xem log bảo mật, posture và bằng chứng theo chính sách | Tự ý thay đổi workload hoặc xóa audit log |
| Application developer | Thao tác tài nguyên non-prod được giao, xem metric/log đã lọc | Thay đổi tổ chức, chính sách trung tâm, tài nguyên prod không qua quy trình |
| Deployment pipeline | Triển khai loại tài nguyên cho đúng workload và môi trường | Quyền toàn tổ chức, cấp đặc quyền vượt phạm vi |
| Production operator | Vận hành, xem telemetry và thực hiện runbook được phép | Quyền xóa tài nguyên bảo mật, thay đổi guardrail |
| Finance/FinOps analyst | Đọc báo cáo chi phí và metadata phân bổ | Truy cập bí mật ứng dụng hoặc dữ liệu giao dịch |

Một ranh giới tài khoản riêng không có nghĩa tự động an toàn nếu mọi người đều có role quản trị xuyên toàn tổ chức. Phải đánh giá **đường đi của quyền**, trust relationship, chính sách kế thừa và thông tin xác thực đang tồn tại.

## 6. Guardrails: bảo vệ nhưng vẫn cho phép tự phục vụ

**Guardrail** là cơ chế giới hạn hoặc phát hiện hành vi không phù hợp với tiêu chuẩn tổ chức. Landing zone tốt cần phân biệt:

| Loại | Cách hoạt động | Ví dụ |
|---|---|---|
| **Preventive** (ngăn chặn) | Chặn thao tác vi phạm trước khi cấu hình có hiệu lực | Cấm tạo tài nguyên ngoài region được duyệt; từ chối public storage theo tiêu chí |
| **Detective** (phát hiện) | Kiểm tra cấu hình/sự kiện rồi thông báo vi phạm | Phát hiện storage bị công khai, security group quá rộng hoặc thiếu logging |
| **Corrective** (khắc phục) | Tự điều chỉnh hoặc kích hoạt quy trình sửa | Gỡ quyền public không hợp lệ, cô lập tài nguyên, mở ticket cho chủ sở hữu |

Guardrail có thể được thực thi bởi organization policy, IAM, policy as code trong pipeline, cấu hình chuẩn, kiểm tra drift và công cụ security posture. Một chính sách **detective** chỉ cảnh báo; nó không tự ngăn thao tác. Một **preventive policy** có thể chặn ứng dụng vận hành khi thiết kế sai mục tiêu hoặc quá rộng. Cần quy trình ngoại lệ rõ người phê duyệt, lý do, phạm vi và thời hạn.

### Baseline chính sách tối thiểu

1. Chỉ cho phép những khu vực triển khai phù hợp yêu cầu dữ liệu và pháp lý đã xác nhận.
2. Ngăn cấu hình public không được phép trên dữ liệu/lưu trữ nhạy cảm; kiểm soát điểm vào mạng theo thiết kế.
3. Bảo vệ nguồn audit log, chính sách ghi nhận sự kiện và quyền xóa/sửa log.
4. Đảm bảo mã hóa phù hợp đối với dữ liệu khi lưu và truyền; quy định trách nhiệm quản lý khóa.
5. Kiểm soát quyền quản trị, cấp quyền nhạy cảm và tạo thông tin xác thực tĩnh.
6. Kiểm tra metadata chủ sở hữu, phân loại dữ liệu và phân bổ chi phí nơi khả thi.
7. Ghi nhận và theo dõi sai lệch cấu hình; có phương án khắc phục theo mức độ rủi ro.

Ví dụ: chính sách “không có IP public cho mọi compute” có thể phù hợp mạng nội bộ nghiêm ngặt, nhưng không phù hợp một thành phần phải cung cấp điểm vào công khai. Cần phân biệt **điểm vào được phép**, lớp bảo vệ và việc compute backend có thực sự cần IP public hay không.

## 7. Thiết kế mạng nền tảng: kết nối, cô lập và giải quyết tên

Landing zone phải xác định chiến lược mạng đủ sớm vì thay đổi CIDR, routing và DNS sau khi nhiều workload đã phụ thuộc thường tốn kém.

### 7.1. Các quyết định mạng bắt buộc

| Thành phần | Cần chốt điều gì? | Rủi ro khi bỏ qua |
|---|---|---|
| **IP addressing / CIDR** | Dải địa chỉ không trùng, dự trù tăng trưởng, IPAM và quan hệ với on-prem | Xung đột IP, kết nối hybrid khó khăn |
| **DNS** | Vùng tên public/private, người quản lý, forwarder, resolution xuyên mạng | Ứng dụng kết nối sai endpoint, lỗi khó chẩn đoán |
| **Ingress** | Điểm vào từ Internet/đối tác, TLS, authentication, WAF khi phù hợp | Mở rộng bề mặt tấn công, thiếu kiểm soát |
| **Egress** | Workload được kết nối ra ngoài qua đâu, cách ghi nhận và giới hạn | Rò rỉ dữ liệu, không kiểm soát phụ thuộc hoặc chi phí traffic |
| **East-west** | Giao tiếp giữa các workload, micro-segmentation và quyền mạng | Lỗi/chiếm quyền lan rộng |
| **Private service access** | Kết nối private tới managed database/storage/services theo khả năng cloud | Phải dựa vào endpoint public ngoài ý muốn |
| **Hybrid connectivity** | VPN, leased/private connection, độ dự phòng, routing, DNS và vận hành | Một đường kết nối lỗi làm hỏng nhiều dịch vụ |

Một thiết kế tham khảo:

~~~mermaid
flowchart TD
    Internet((Internet)) --> Edge["Public ingress: DNS / WAF / Load Balancer"]
    Edge --> App["Application workload network"]
    App --> DB[("Private managed database")]
    App --> Endpoint["Private endpoint to cloud services"]
    Office["On-prem / Office"] <-->|"VPN / private link"| Hub["Connectivity hub"]
    Hub <--> App
    Hub <--> Other["Other workload network"]
    App --> Egress["Controlled outbound access"]
    Egress --> Internet
~~~

*Sơ đồ chỉ biểu diễn luồng logic. Quy tắc định tuyến, tường lửa, NAT, mạng con, độ dự phòng và khả năng private endpoint phụ thuộc dịch vụ và nhà cung cấp.*

**Mô hình hub-and-spoke** có thể phù hợp khi cần quản lý connectivity/DNS/firewall tập trung. Nhưng hub trung tâm cũng có thể là điểm nghẽn, tạo chi phí lưu lượng xuyên vùng và rủi ro chung. Một số tổ chức phù hợp mô hình mạng phân tán hoặc kết hợp, với guardrail chung và quyền sở hữu theo workload.

### 7.2. Không nhầm “private” với “an toàn”

Mạng riêng giảm khả năng tiếp cận trực tiếp từ Internet nhưng không thay thế xác thực, phân quyền, TLS, quản lý secrets và kiểm tra hành vi ứng dụng. Dịch vụ trong mạng nội bộ vẫn có thể bị xâm nhập qua quyền workload hoặc đường kết nối được cho phép.

Ngoài ra, **đừng buộc mọi lưu lượng đi qua một thiết bị trung tâm** nếu chưa có yêu cầu an ninh và bài đo hiệu năng/chi phí. Phải kiểm tra đường đi thực tế cho logging, giám sát, DNS và các dịch vụ cloud dùng private connectivity.

## 8. Logging, bảo mật dữ liệu và khả năng quan sát

Một landing zone tối thiểu cần **biết ai thay đổi tài nguyên, hệ thống đang chạy ra sao và điều gì xảy ra khi sự cố xuất hiện**.

### 8.1. Audit nền tảng và telemetry ứng dụng

Phân biệt:

- **Control-plane audit:** ai đăng nhập, tạo/xóa tài nguyên, thay IAM, đổi network policy, thay khóa hoặc cấu hình cloud.
- **Data-plane audit:** ai truy cập dữ liệu và thực hiện thao tác dữ liệu nào; khả năng ghi nhận thay đổi theo dịch vụ, cấu hình và chi phí.
- **Platform metrics:** quota, tình trạng network, tài nguyên chung, lỗi policy, sức khỏe dịch vụ dùng chung.
- **Workload observability:** SLI/SLO, metrics, logs, traces và hành trình nghiệp vụ cụ thể; thuộc trách nhiệm ứng dụng với hỗ trợ của platform.

Những yêu cầu tối thiểu với log:

1. Có nơi thu thập và lưu giữ audit phù hợp; tách quyền của người tạo log và người có thể xóa/sửa log khi khả thi.
2. Bảo vệ dữ liệu log bằng phân quyền, mã hóa, retention và kiểm soát truy cập; áp dụng yêu cầu chống sửa đổi khi cần.
3. Theo dõi **việc mất luồng log** và lỗi cấu hình thu thập, không chỉ các sự kiện bên trong log.
4. Có chính sách lọc/chỉnh sửa dữ liệu nhạy cảm: log không nên chứa secret, token, thông tin thanh toán hoặc dữ liệu cá nhân ngoài mục đích có căn cứ.
5. Phân biệt cảnh báo có thể hành động với dữ liệu chỉ dùng tra cứu; bảo đảm có người nhận và runbook.

Thu gom toàn bộ log không giới hạn không tự đồng nghĩa quan sát tốt: log có thể chứa dữ liệu cần bảo vệ, chi phí lưu và truy vấn cao, tín hiệu bị nhiễu. Cần quyết định loại log, độ chi tiết và thời hạn giữ theo rủi ro và nghiệp vụ.

### 8.2. Ví dụ chuỗi phát hiện và xử lý sự cố

Giả sử một tài khoản mới có storage bị cấu hình công khai ngoài chính sách:

1. Preventive guardrail chặn cấu hình nếu hành vi thuộc phạm vi hỗ trợ.
2. Detective scan kiểm tra lại trạng thái thực tế để phát hiện sai lệch.
3. Cảnh báo đến owner và đội security với bằng chứng: tài nguyên, phạm vi, thời gian, chính sách vi phạm.
4. Nếu được duyệt trước, corrective workflow cô lập/khắc phục, có audit và tránh phá hủy dữ liệu.
5. Đội phụ trách xem xét nguyên nhân, cập nhật IaC hoặc guardrail; kiểm tra sự kiện không lặp lại.

Điểm quan trọng: **kiểm soát có vòng đời**, bao gồm triển khai, phát hiện sai lệch, khắc phục và đo hiệu quả.

## 9. Quản lý khóa, secrets và dữ liệu nền tảng

Các chức năng tối thiểu cần thiết:

- **Quản lý khóa mã hóa:** xác định khi nào dùng khóa do nhà cung cấp quản lý, khi nào cần customer-managed key; ai có quyền tạo, sử dụng, xoay vòng, vô hiệu hóa và xóa khóa.
- **Secrets management:** secret được lưu trong dịch vụ phù hợp, không đặt trong repository, image, IaC state hoặc log; quy định rotation và thu hồi.
- **Quản lý chứng chỉ:** cấp/gia hạn TLS, kiểm soát private key và cảnh báo trước khi hết hạn.
- **Data governance:** phân loại dữ liệu, nơi cư trú dữ liệu, mục đích lưu trữ, chia sẻ, retention và xóa phù hợp yêu cầu.
- **Backup và phục hồi:** dữ liệu quan trọng có lịch backup, khả năng khôi phục đã thử và phân quyền bảo vệ bản sao.

Không nên cho rằng “dùng dịch vụ managed” đồng nghĩa hệ thống tự đáp ứng toàn bộ RPO/RTO. Khả năng restore phụ thuộc loại dịch vụ, cấu hình, độ dài retention, kịch bản lỗi và quy trình của đội ngũ. Hủy/khóa mã hóa sai có thể làm mất khả năng giải mã dữ liệu dù backup vẫn còn.

## 10. IaC, bootstrap và quy trình cấp môi trường mới

Một landing zone chỉ được tạo bằng tay dễ dẫn tới các account/project khác nhau về cấu hình và khó khôi phục. Vì thế nên mô tả các thành phần quản trị chung bằng **Infrastructure as Code (IaC)** và quy trình có thể lặp lại.

### 10.1. Bootstrap: bài toán “ai tạo nền tảng ban đầu?”

Trước khi pipeline IaC hoạt động, cần thiết lập một số năng lực nền móng: tổ chức/tenant, danh tính quản trị, nơi lưu state, quyền triển khai, cơ chế kiểm soát truy cập và đường phục hồi khi pipeline lỗi.

Trình tự tham khảo:

1. **Bảo vệ gốc quản trị:** thiết lập tài khoản quản trị ban đầu, MFA, quản lý quyền và emergency access.
2. **Tạo nơi chạy và lưu trạng thái IaC:** remote state có kiểm soát quyền, mã hóa, cơ chế chống ghi đè đồng thời và bản sao phù hợp.
3. **Cấp danh tính cho pipeline:** ưu tiên liên kết danh tính và thông tin xác thực ngắn hạn; giới hạn phạm vi quyền.
4. **Tạo cấu trúc tổ chức:** nhóm phạm vi và ranh giới nền tảng, logging, security, non-prod/prod.
5. **Áp guardrail và audit:** chính sách tổ chức, luồng ghi log, cảnh báo kiểm soát, bảo vệ nguồn log.
6. **Tạo mạng/kết nối dùng chung khi cần:** IPAM, DNS, route, VPN/private connectivity và cơ chế quan sát.
7. **Cấp môi trường workload theo mẫu:** role, quota, tags, budget, network attachment và baseline observability.
8. **Kiểm chứng và bàn giao:** thử policy, quyền, pipeline, log, backup và quy trình khắc phục sự cố.

Phần bootstrap thường có một số thao tác thủ công ban đầu; cần ghi lại, giảm dần và bảo vệ chúng. Không ghi trực tiếp bí mật vào mã IaC hoặc state nếu có cách tham chiếu an toàn hơn.

### 10.2. Mô hình “account/subscription/project vending”

**Vending** là quy trình cấp một môi trường quản trị chuẩn từ yêu cầu có cấu trúc. Ví dụ:

~~~mermaid
flowchart LR
    Request["Đội sản phẩm yêu cầu môi trường"] --> Validate["Kiểm tra owner / môi trường / dữ liệu / ngân sách"]
    Validate --> Approval{"Cần phê duyệt?"}
    Approval -->|Có| Review["Người có thẩm quyền duyệt"]
    Approval -->|Không| Plan["IaC plan + policy checks"]
    Review --> Plan
    Plan --> Provision["Tạo ranh giới và cấu hình baseline"]
    Provision --> Verify["Xác minh IAM, audit, network, tags, budget"]
    Verify --> Handover["Bàn giao owner + runbook + inventory"]
    Verify -->|Không đạt| Remediate["Sửa hoặc rollback theo quy trình"]
    Remediate --> Plan
~~~

*Quy tắc phê duyệt phụ thuộc loại môi trường và mức rủi ro: tạo sandbox thông thường có thể tự phục vụ, trong khi tạo production xử lý dữ liệu nhạy cảm có thể cần xem xét bổ sung.*

Mẫu yêu cầu nên có ít nhất: workload, owner, environment, region, mức nhạy cảm dữ liệu, kết nối mạng, ngân sách, phạm vi người triển khai và thời hạn tồn tại với tài nguyên tạm. Sau khi cấp xong, đội ứng dụng nhận **đường truy cập chính thống** để triển khai compute/DB/queue của mình và biết nơi xem trạng thái/chi phí/cảnh báo.

### 10.3. CI/CD và quản lý drift

Đưa chính sách và chuẩn vào pipeline:

- IaC được review, kiểm tra cú pháp và kiểm tra policy trước khi áp dụng.
- Phân tách quyền xem kế hoạch và thực thi thay đổi khi phù hợp; thay đổi production có kiểm soát.
- Gắn version cho module nền tảng, có quy trình nâng cấp và hướng dẫn di trú.
- Theo dõi **configuration drift** (cấu hình thực tế lệch khỏi IaC), đánh giá hậu quả trước khi tự sửa.
- Có phương án khôi phục khi sửa IAM, route hoặc DNS khiến pipeline mất quyền hoặc mất kết nối.

Lưu ý: **rollback IaC không đảm bảo hoàn tác dữ liệu**. Nếu thay đổi tác động DB, storage hoặc resource state, cần kế hoạch migration/backup/recovery riêng.

## 11. Chi phí, quota và vòng đời tài nguyên

Kiến trúc cloud chịu ràng buộc chi phí ngay từ tổ chức tài nguyên. Quản lý chi phí tối thiểu không nên chờ tới khi hóa đơn tăng đột biến.

### Baseline FinOps

| Năng lực | Cách triển khai ban đầu | Lý do |
|---|---|---|
| **Billing và ownership** | Gắn tài nguyên với owner/cost center theo tổ chức và tag/label | Xác định đội chịu trách nhiệm và phân bổ |
| **Budget** | Thiết lập ngân sách/cảnh báo theo workload và môi trường | Phát hiện chi phí vượt dự báo trước khi kéo dài |
| **Quota / service limits** | Theo dõi và điều chỉnh hạn mức theo tải dự kiến | Ngăn cấp dư ngoài ý muốn và tránh bị lỗi do hết quota |
| **Cost visibility** | Dashboard theo account/project, service, workload và xu hướng | Nhận biết tài nguyên bị quên hoặc chi phí mạng/log |
| **Lifecycle** | Hạn dùng và thu hồi sandbox tạm; lịch tắt tài nguyên dev khi phù hợp | Giảm chi phí nhàn rỗi |
| **Review định kỳ** | So sánh chi phí thực tế với dự báo, SLO và tải | Tối ưu có căn cứ, tránh cắt giảm phá hỏng độ tin cậy |

**Budget alert thường chỉ cảnh báo**, không tự khóa toàn bộ chi tiêu. **Quota cũng không phải ngân sách**: có dịch vụ tính phí theo số yêu cầu/lưu lượng mà quota không kiểm soát đủ. Cần hiểu chính xác loại cảnh báo và hành động tự động ở nhà cung cấp cụ thể.

Ví dụ, đường truyền qua NAT gateway, cross-region replication, log ingestion và message traffic có thể chiếm chi phí đáng kể ngay cả khi VM nhỏ. Cân nhắc chi phí **toàn hành trình** thay vì chỉ giá compute.

## 12. Độ tin cậy và khôi phục trong landing zone

Landing zone là hạ tầng chung; nếu sai cấu hình IAM, DNS hoặc connectivity, nhiều workload có thể cùng lỗi. Vì thế nó cũng cần mục tiêu tin cậy và quy trình khôi phục.

### Phân biệt các kịch bản

| Kịch bản | Câu hỏi thiết kế |
|---|---|
| Một VM/node lỗi | Workload có health checks, cơ chế thay thế và năng lực dự phòng không? |
| Một zone lỗi | Thành phần có được phân bổ phù hợp, có failover và DB hỗ trợ không? |
| Một region lỗi | Nghiệp vụ có thật sự cần đa vùng? Dữ liệu, DNS, failover và vận hành chịu chi phí nào? |
| Một tài khoản/project bị cấu hình sai | Blast radius, quyền tác động, audit và quy trình phục hồi? |
| Hỏng IAM/SSO hoặc pipeline | Emergency access, đường kiểm soát thay đổi và break-glass đã thử chưa? |
| Mất kết nối hybrid / DNS | Workload nào phụ thuộc on-prem, cách suy giảm và routing dự phòng ra sao? |
| Dữ liệu bị xóa nhầm hoặc hỏng | Backup có được bảo vệ và restore test với RTO/RPO mục tiêu chưa? |

**RTO** là thời gian mục tiêu để khôi phục dịch vụ sau sự cố xác định; **RPO** là khoảng mất dữ liệu chấp nhận được tính theo thời gian. Các giá trị này phải được thống nhất cho workload/kịch bản tương ứng. Backup một lần mỗi ngày không tự đảm bảo RPO 15 phút; chạy trên nhiều zone không tự đảm bảo xử lý xóa nhầm dữ liệu.

### Kiểm chứng độ tin cậy từ nền tảng

- Thử đăng nhập và thao tác với emergency role khi kịch bản SSO bị gián đoạn.
- Xác minh audit log vẫn được gửi đến nơi lưu giữ khi workload bị cấu hình sai.
- Diễn tập phục hồi DNS/route/IaC state theo tình huống đã chọn.
- Kiểm tra việc khôi phục tài nguyên/dữ liệu bằng bản backup, đo thời gian và điều chỉnh runbook.
- Kiểm chứng một workload bị quá tải không mặc nhiên làm cạn quota hoặc kết nối của toàn bộ môi trường chung.

Không cần diễn tập mọi kịch bản mỗi tuần. Hãy ưu tiên theo tác động nghiệp vụ, tần suất thay đổi và khả năng quan sát thực tế.

## 13. Xác định “tối thiểu” theo mức rủi ro

Một landing zone **minimum viable** nên đủ để triển khai workload đầu tiên một cách có kiểm soát, đồng thời có đường nâng cấp khi công ty mở rộng. Không nên cố tự xây toàn bộ nền tảng nội bộ trước khi có sản phẩm.

| Nhóm năng lực | **Trước workload production đầu tiên** | **Khi tăng quy mô / yêu cầu phức tạp hơn** |
|---|---|---|
| **Cấu trúc tài nguyên** | Owner, môi trường prod/non-prod và phạm vi quản trị rõ | Phân tầng theo nhiều product/team/data domain; tự động cấp môi trường |
| **Identity** | SSO/MFA nếu khả thi, least privilege, workload identity, emergency access | JIT access, rà soát quyền tự động, quản lý đặc quyền quy mô lớn |
| **Security baseline** | Guardrail thiết yếu, mã hóa, quản lý secrets, audit | Policy as code rộng hơn, tự khắc phục, posture management liên tục |
| **Networking** | CIDR/DNS, ingress/egress hợp lý, cô lập network quan trọng | Hub/spoke hoặc mô hình nhiều mạng, hybrid, IPAM tự động |
| **Observability** | Central audit, dashboard/cảnh báo cho thành phần quan trọng và owner rõ | Correlation/tracing tập trung, SLO platform, phân tích sự cố xuyên đội |
| **IaC** | Tài nguyên nền tảng và workload quan trọng được quản lý có version | Vending/self-service, catalog module, kiểm soát drift quy mô lớn |
| **Data protection/DR** | Backup, retention và một lần restore test theo rủi ro | Bài diễn tập thường xuyên hơn, kịch bản nhiều vùng/region nếu có yêu cầu |
| **Cost** | Billing owner, tag/label, budget alert và theo dõi quota | Showback/chargeback, unit economics, policy tối ưu tự động |

Thứ tự triển khai vẫn tùy tổ chức: nếu hệ thống bắt buộc kết nối on-prem trước khi hoạt động, **hybrid network không thể chờ giai đoạn sau**. Nếu doanh nghiệp xử lý dữ liệu chịu nghĩa vụ tuân thủ nghiêm ngặt, một số năng lực nâng cao có thể trở thành điều kiện tối thiểu ngay ban đầu.

## 14. Ví dụ triển khai: nền tảng đặt chỗ đưa ứng dụng đầu tiên lên cloud

Giả định một doanh nghiệp có ứng dụng **Booking API**, **Search**, một cơ sở dữ liệu quan hệ, worker gửi email và dashboard vận hành. Đội khoảng một vài nhóm kỹ thuật muốn mở môi trường dev/test và production tại một vùng chính, có kế hoạch mở rộng trong tương lai.

Đây là giả định dùng để thực hành, không phải mẫu áp dụng nguyên xi cho mọi hệ thống.

### 14.1. Bản thiết kế tối thiểu

| Thành phần | Quyết định ban đầu | Lý do và kiểm chứng |
|---|---|---|
| **Organization** | Một gốc quản trị, ranh giới riêng cho prod, non-prod và khả năng audit chung | Hạn chế phạm vi thay đổi và phân quyền |
| **Identity** | SSO, role theo nhóm, pipeline dùng workload identity, break-glass | Thử quyền tối thiểu và truy cập khẩn cấp |
| **Network** | Không gian địa chỉ được quy hoạch; ingress công khai qua điểm vào có TLS; app/DB truy cập private | Kiểm tra đường mạng, DNS và thử chặn kết nối trái phép |
| **Security** | Mã hóa, secrets manager, hạn chế public storage, guardrail thay đổi quyền | Kiểm tra policy và nhật ký truy cập |
| **Logging** | Control-plane audit tập trung; app metrics/log/trace theo owner | Thử cảnh báo và truy vết sự cố tạo đặt chỗ |
| **Data** | Managed relational DB, backup/restore có mục tiêu xác nhận từ nghiệp vụ | Khôi phục thử, kiểm tra mất dữ liệu và quyền khôi phục |
| **Delivery** | IaC có review, môi trường tách biệt, pipeline production có kiểm soát | Thử tạo lại sandbox, kiểm tra policy gate |
| **FinOps** | Owner và cost center; budget alert; quota và rà soát tài nguyên thử nghiệm | Có dashboard chi phí, thử nhận cảnh báo |

### 14.2. Luồng phát hành một tính năng

1. Product team thay đổi mã Booking API và cấu hình IaC trong repository có review.
2. CI kiểm tra build/test, cấu hình IaC và guardrail theo môi trường.
3. Pipeline dev triển khai bằng role chỉ có quyền trong ranh giới non-prod.
4. Kiểm thử tải, bảo mật và dữ liệu xác nhận thay đổi phù hợp.
5. Pipeline production chỉ được dùng role prod qua cơ chế được duyệt; mọi thay đổi tạo audit.
6. Sau phát hành, metrics, logs và SLO xác nhận hành trình đặt chỗ vẫn đáp ứng mục tiêu.
7. Khi có sự cố, owner sử dụng runbook, rollout/rollback hoặc khôi phục phù hợp; ghi lại bài học để cải thiện platform template.

Điểm lợi của landing zone nằm ở sự **lặp lại có kiểm soát**: khi tạo thêm một workload khác, đội ngũ không phải thiết kế lại IAM, audit, quy ước cost owner và quy trình triển khai từ đầu.

### 14.3. Ba tình huống phản biện

**Tình huống A — Đội phát triển yêu cầu quyền admin trên production.** Hãy làm rõ thao tác cần làm, quyền tối thiểu tương ứng, phương án hỗ trợ khẩn cấp và cơ chế tự phục vụ. Không cấp admin toàn diện chỉ vì việc xin quyền đang chậm; cũng không thiết kế quy trình quá nặng khiến sự cố không thể được xử lý kịp.

**Tình huống B — Mọi workload dùng chung VPC/VNet và cùng một NAT.** Kiểm tra nhu cầu cô lập, routing, traffic cost, quota, lỗi lan truyền và quyền mạng; so sánh với mô hình tách mạng theo môi trường/đội. Quyết định dựa trên rủi ro và chi phí, không chỉ số lượng network.

**Tình huống C — Muốn triển khai multi-region ngay từ đầu.** Yêu cầu mô tả kịch bản mất cả region, SLO/RTO/RPO và ảnh hưởng doanh thu. Tính thêm replication, quyền truy cập, đồng bộ cấu hình, định tuyến, diễn tập failover và chi phí. Nếu chưa có yêu cầu rõ, tập trung kiểm chứng khả năng phục hồi trong phạm vi phù hợp trước.

## 15. Đánh giá landing zone theo tư duy Well-Architected

Các nhà cung cấp cloud trình bày Well-Architected với phạm vi và cách gọi khác nhau. Có thể dùng các góc nhìn chung sau để phản biện nền tảng:

| Góc nhìn | Câu hỏi kiểm tra | Bằng chứng |
|---|---|---|
| **Operational excellence** | Tạo môi trường mới có lặp lại, kiểm tra drift và biết ai xử lý lỗi không? | IaC repository, pipeline, runbook, owner, kết quả thử cấp môi trường |
| **Security** | Chính sách ngăn cấu hình rủi ro, quyền tối thiểu và audit có hiệu lực thực tế không? | Policy test, quyền role, log truy cập, kết quả kiểm tra cấu hình |
| **Reliability** | Nền tảng có điểm lỗi chung nào? Có cách khôi phục IAM, DNS, state và dữ liệu không? | Kịch bản sự cố, restore test, bài diễn tập, kết quả failover |
| **Performance efficiency** | Network, quota và năng lực nền tảng có đáp ứng tải dự kiến không? | Load test, đo độ trễ kết nối, saturation và quota headroom |
| **Cost optimization** | Có biết chi phí theo môi trường/workload, xử lý tài nguyên nhàn rỗi và lưu lượng ẩn không? | Báo cáo cost allocation, budget, inventory và review chi phí |
| **Sustainability** | Cấp phát và lưu giữ tài nguyên có phù hợp mức sử dụng thực tế không? | Mức sử dụng, chính sách retention, lịch thu hồi sandbox |

Không có lựa chọn “chặn càng nhiều càng tốt” hay “tập trung càng nhiều càng tốt” áp dụng cho mọi tình huống. Tập trung logging và guardrail có thể tăng nhất quán; tập trung toàn bộ lưu lượng mạng qua một điểm có thể tạo nút thắt. Phân tách workload tăng cô lập nhưng cũng tăng số tài nguyên, tài khoản và chi phí nền tảng. **Quyết định kiến trúc cần nêu rõ đánh đổi và cách kiểm chứng.**

## 16. Những sai lầm thường gặp

| Sai lầm | Hậu quả | Cách tránh |
|---|---|---|
| **Chỉ tạo network rồi gọi đó là landing zone** | Thiếu identity, guardrail, audit, chi phí và quy trình vận hành | Dùng ma trận năng lực và tiêu chí sẵn sàng |
| **Mọi workload chung một quyền quản trị** | Một tài khoản bị chiếm hoặc cấu hình sai ảnh hưởng rộng | Phân quyền theo phạm vi, MFA, workload identity và đặc quyền có kiểm soát |
| **Tất cả hoạt động đều phải qua platform team** | Platform thành nút thắt, đội ứng dụng tìm cách vượt quy trình | Thiết lập self-service template và policy gate |
| **Tài nguyên tạo bằng tay không có IaC** | Drift, khó khôi phục, môi trường không nhất quán | IaC, kiểm tra drift và quy trình thay đổi |
| **Quá nhiều account/project từ đầu** | Tốn công quản trị, kết nối và chi phí không cần thiết | Bắt đầu từ ranh giới rủi ro thực, có phương án tách khi cần |
| **Bật audit nhưng không ai giám sát pipeline log** | Có thể mất sự kiện mà không phát hiện | Theo dõi độ đầy đủ và độ trễ thu thập |
| **Lưu secrets trong state/pipeline log** | Rò rỉ dữ liệu xác thực ngoài dự kiến | Cấp thông tin xác thực ngắn hạn, secret manager, kiểm soát state |
| **Coi budget alert là giới hạn chi phí cứng** | Hóa đơn có thể tiếp tục tăng dù đã cảnh báo | Hiểu ngữ nghĩa alert, quota, giới hạn khả dụng và phản ứng thực tế |
| **Có backup nhưng chưa restore test** | RTO/RPO chỉ là giả định | Diễn tập và lưu kết quả khôi phục |
| **Chặn mọi ngoại lệ không có quy trình** | Cản tính năng hợp lệ hoặc tăng cấu hình “lách” | Exception có đánh giá rủi ro, chủ sở hữu và thời hạn |

## 17. Checklist nghiệm thu landing zone tối thiểu

Đánh giá theo **bằng chứng có thể kiểm tra**, không chỉ một sơ đồ hoặc lời xác nhận:

- [ ] Có sơ đồ phạm vi quản trị, ranh giới production/non-production, chủ sở hữu và cách phân bổ chi phí.
- [ ] Có quy trình cấp môi trường mới, yêu cầu đầu vào và cách thu hồi khi không còn sử dụng.
- [ ] Tài khoản quản trị gốc/đặc quyền được bảo vệ; có phương án emergency access đã được thử.
- [ ] Đã cấu hình danh tính người dùng và workload theo quyền tối thiểu; có cơ chế thu hồi quyền.
- [ ] Guardrail quan trọng được áp dụng và có bằng chứng thử trường hợp vi phạm.
- [ ] Tài nguyên nhạy cảm dùng mã hóa, quản lý secrets và chính sách truy cập phù hợp.
- [ ] Có quy hoạch CIDR, DNS, routing, ingress/egress và kết nối hybrid nếu cần.
- [ ] Control-plane audit hoạt động; log được bảo vệ, có retention và cảnh báo khi gián đoạn thu thập.
- [ ] Workload có baseline observability, người nhận cảnh báo và runbook tối thiểu.
- [ ] IaC/pipeline có review, quản lý state an toàn, kiểm tra chính sách và xử lý drift.
- [ ] Có phương án backup/restore, mục tiêu RTO/RPO theo từng kịch bản và ít nhất một phép thử khôi phục phù hợp.
- [ ] Có tag/label hoặc metadata thay thế cho owner, môi trường, phân loại dữ liệu và cost center.
- [ ] Budget alert, quota và báo cáo chi phí được kiểm tra; có quy trình xử lý khi vượt ngưỡng.
- [ ] Vai trò giữa platform, security, operations và ứng dụng được bàn giao rõ ràng.
- [ ] Đã ghi nhận giới hạn hiện tại, rủi ro tồn dư và điều kiện mở rộng landing zone về sau.

## 18. Bài tập thực hành

**Bối cảnh:** Một công ty có hai nhóm phát triển, một nền tảng tìm kiếm/đặt phòng, môi trường dev và production. Dữ liệu production chứa thông tin khách hàng; ứng dụng cần kết nối tới hệ thống kế toán ở văn phòng. Dự kiến mở rộng thêm ba workload trong sáu tháng, nhưng đội platform chỉ có một người phụ trách và ngân sách giới hạn.

Hãy lập thiết kế landing zone với các yêu cầu:

1. Đề xuất cấu trúc tổ chức tài nguyên tối thiểu, giải thích lý do phân tách production, non-production, audit hoặc shared platform.
2. Phác thảo luồng đăng nhập, role triển khai, quyền vận hành và emergency access.
3. Chọn ranh giới mạng, DNS, kết nối office và vị trí đặt điểm vào ứng dụng public.
4. Nêu ít nhất năm guardrail cần có và một cách kiểm chứng cho mỗi loại.
5. Mô tả cách cấp workload mới bằng IaC; xác định chỗ cần review và chỗ có thể tự phục vụ.
6. Đặt giả định về backup, observability và quản lý chi phí, sau đó nêu câu hỏi cần nghiệp vụ xác nhận.
7. So sánh hai phương án: (A) mạng trung tâm với hub kết nối office; (B) mạng tách theo môi trường với kết nối trực tiếp được quản lý. Nêu chi phí/độ phức tạp và điều kiện chọn.

**Gợi ý tự kiểm tra:** Nếu thiết kế mới chỉ có sơ đồ VPC/VNet, hãy bổ sung quyền, guardrail, audit, chi phí và vòng đời. Nếu chọn multi-region hay nhiều account/project, cần nêu lợi ích về độ tin cậy/cô lập và chứng minh đội ngũ đủ khả năng vận hành. Nếu không có phương án khi pipeline IAM hoặc VPN lỗi, landing zone vẫn thiếu một phần quan trọng.

## 19. Ghi nhớ

Landing zone là **nền tảng quản trị và vận hành cloud có thể lặp lại**: tổ chức tài nguyên, xác định quyền, xây guardrail, thiết kế kết nối, bảo vệ audit/dữ liệu, tự động cấp môi trường và quản lý chi phí. Những năng lực này tạo điều kiện để các đội ứng dụng chọn compute, dữ liệu và mô hình triển khai phù hợp với yêu cầu nghiệp vụ.

Một landing zone tốt không cần nhiều thành phần nhất; nó cần **đúng ranh giới rủi ro, đủ năng lực tối thiểu, người chịu trách nhiệm rõ và có phép thử chứng minh các kiểm soát hoạt động**. Khi nhu cầu tăng, mở rộng nền tảng dựa trên số liệu về sự cố, chi phí, độ tin cậy và tốc độ phát triển, đồng thời đánh giá lại các quyết định theo tư duy Well-Architected.
