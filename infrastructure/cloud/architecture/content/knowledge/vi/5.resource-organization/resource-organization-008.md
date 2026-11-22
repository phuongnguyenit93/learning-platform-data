# Quy trình cấp phát, tiếp nhận và thu hồi môi trường

> **Chương:** Tổ chức tài nguyên  
> **Module:** CLOUD_ARCHITECTURE  
> **Phạm vi:** Thiết kế kiến trúc ứng dụng trên đám mây từ nhu cầu nghiệp vụ tới lựa chọn mạng, compute, dữ liệu và triển khai; cân đối độ tin cậy, bảo mật, khả năng mở rộng, chi phí và vận hành theo tư duy Well-Architected.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Mô tả vòng đời một môi trường cloud từ **yêu cầu, phê duyệt, cấp phát, kiểm tra, tiếp nhận vận hành, thay đổi đến thu hồi**.
2. Xác định hồ sơ yêu cầu môi trường, chủ sở hữu, phân quyền, nhãn tài nguyên, ngân sách, giới hạn và các điểm kiểm soát cần thiết.
3. Phân biệt cấp phát **tài nguyên kỹ thuật** với **bàn giao một môi trường sẵn sàng sử dụng**, có tiêu chí nghiệm thu và người chịu trách nhiệm.
4. Xây dựng quy trình thu hồi có kiểm tra phụ thuộc, dữ liệu, sao lưu, quyền truy cập, chi phí và chứng cứ hoàn tất.
5. Áp dụng Infrastructure as Code (IaC), tự động hóa kiểm tra chính sách và quản lý sai lệch cấu hình để quy trình lặp lại được.
6. Phân tích đánh đổi giữa tốc độ cấp phát, mức cách ly, bảo mật, độ tin cậy và chi phí bằng câu hỏi Well-Architected.

## 1. Vì sao môi trường cloud cần quy trình vòng đời?

Một **môi trường** là tập hợp tài nguyên, cấu hình, danh tính, quyền truy cập, dữ liệu và quy trình vận hành nhằm phục vụ một mục đích xác định, chẳng hạn development, integration, testing, staging hoặc production. Nó có thể nằm trong một tài khoản/subscription/project riêng, một cụm dùng chung với vùng tên tách biệt, hoặc kết hợp nhiều dịch vụ. Tên và ranh giới kỹ thuật cụ thể phụ thuộc vào nhà cung cấp và mức cô lập cần thiết.

Khả năng tạo máy chủ nhanh của cloud tạo ra hai mặt: nhóm sản phẩm triển khai thử nghiệm nhanh, nhưng cũng dễ xuất hiện tài nguyên không có chủ sở hữu, cấu hình bảo mật không nhất quán, dữ liệu thật trong môi trường thử và chi phí tiếp tục phát sinh sau khi dự án kết thúc.

Ví dụ một nhóm tạo môi trường để thử tính năng tìm kiếm trong hai tuần. Nếu chỉ có thao tác “tạo database + VM”, sau hai tuần có thể không ai biết:

- Ai được quyền quyết định môi trường còn cần hay không?
- Database chứa dữ liệu cá nhân hay chỉ dữ liệu mẫu?
- Người vận hành biết endpoint, log, sao lưu và quy trình khôi phục ở đâu không?
- Tài nguyên nào được dùng chung với hệ thống khác, có thể xóa mà không ảnh hưởng chúng không?
- Quyền của tài khoản CI/CD, secret và API token có còn tồn tại sau khi ngừng môi trường không?
- Ai kiểm tra rằng chi phí đã dừng thực sự?

Một quy trình tốt phải cung cấp **khả năng truy vết và trách nhiệm xuyên suốt**, không chỉ một script tạo tài nguyên.

### 1.1. Các loại môi trường và nguyên tắc phân biệt

| Loại | Mục đích | Đặc điểm/kiểm soát thường gặp |
|---|---|---|
| **Development (dev)** | Phát triển, thử thay đổi hàng ngày | Chi phí thấp, có thể tái tạo; dữ liệu tổng hợp; không yêu cầu HA như production |
| **Integration/test** | Kiểm tra tích hợp, contract, chức năng | Dữ liệu kiểm thử có thể reset; tự động dựng/hủy; cần quyền và kết nối với hệ thống giả lập phù hợp |
| **Ephemeral/preview** | Thử theo branch, pull request hoặc một công việc ngắn | Có TTL, owner, ngân sách, tự động đóng sau khi kết thúc |
| **Staging/pre-production** | Kiểm chứng gần điều kiện production, diễn tập release | Cấu hình và đường đi quan trọng tương đồng production; vẫn phải bảo vệ dữ liệu |
| **Production (prod)** | Phục vụ người dùng thực | Kiểm soát thay đổi, giám sát, backup/DR, phân quyền và chính sách vận hành theo yêu cầu nghiệp vụ |
| **DR/standby** | Khôi phục sau sự cố đã định nghĩa | Dữ liệu, khả năng chuyển vùng/khôi phục và RTO/RPO phải được thử, không chỉ tồn tại tài nguyên |

**Staging không nhất thiết phải cùng kích thước với production**, nhưng phải đủ tương đồng để thử các rủi ro quan trọng: cấu hình, chính sách mạng, cơ chế triển khai, schema, xác thực và các tích hợp cần thiết. Nếu dùng dữ liệu production để thử nghiệm, phải có căn cứ cho phép, cơ chế tối thiểu hóa/ẩn danh và kiểm soát quyền/retention phù hợp; mặc định ưu tiên dữ liệu tổng hợp.

### 1.2. Cấp phát, tiếp nhận và thu hồi là ba điểm kiểm soát khác nhau

- **Cấp phát (provisioning):** tạo và cấu hình tài nguyên, kết nối, danh tính, chính sách, quan sát và các khả năng nền tảng theo bản thiết kế được phê duyệt.
- **Tiếp nhận (acceptance/handover):** xác nhận môi trường sử dụng được cho đúng mục đích, đạt kiểm tra kỹ thuật và được người sở hữu/vận hành nhận trách nhiệm.
- **Thu hồi (decommissioning):** xác nhận không còn nhu cầu, xử lý dữ liệu và phụ thuộc, rút quyền, gỡ tài nguyên đúng phạm vi, rồi kiểm tra chi phí/trạng thái cuối cùng.

Việc đánh dấu provisioning “success” chỉ cho biết một tập lệnh đã chạy xong. Nó **chưa chứng minh ứng dụng có thể truy cập an toàn, dữ liệu khôi phục được hoặc nhóm vận hành biết cách ứng cứu sự cố**. Ngược lại, môi trường đã ngừng nhận request nhưng database, snapshot, IP, log, khóa và các tài nguyên phụ trợ vẫn tồn tại thì chưa thu hồi hoàn chỉnh.

## 2. Mô hình vòng đời và trách nhiệm

### 2.1. Luồng trạng thái tham chiếu

~~~mermaid
flowchart TD
    A[Requested: có hồ sơ yêu cầu] --> B{Review / Approve}
    B -- Cần bổ sung --> A
    B -- Từ chối --> X[Rejected / Closed]
    B -- Chấp thuận --> C[Approved]
    C --> D[Provisioning bằng IaC]
    D --> E{Kiểm tra kỹ thuật}
    E -- Không đạt --> F[Fix / Re-provision]
    F --> D
    E -- Đạt --> G[Ready for acceptance]
    G --> H{Chủ sở hữu và vận hành tiếp nhận?}
    H -- Chưa --> I[Remediate / bổ sung hồ sơ]
    I --> G
    H -- Có --> J[Active: sử dụng và giám sát]
    J --> K[Change / Review định kỳ]
    K --> J
    J --> L[Decommission requested]
    L --> M{Xác nhận dữ liệu / phụ thuộc / phê duyệt}
    M -- Chưa đủ --> J
    M -- Đủ --> N[Quiesce / export / revoke / destroy]
    N --> O{Kiểm chứng thu hồi}
    O -- Còn tài nguyên hoặc phụ thuộc --> P[Cleanup có kiểm soát]
    P --> O
    O -- Hoàn tất --> Q[Retired / Closed]
~~~

Các trạng thái trên là mô hình quy trình đề xuất, không phụ thuộc một công cụ cụ thể. Trong thực tế cần ghi thời gian, người phê duyệt, mã yêu cầu, kết quả kiểm tra và bằng chứng chuyển trạng thái. Với production, việc thu hồi có thể cần phê duyệt riêng do tác động lớn và dữ liệu có yêu cầu lưu giữ.

### 2.2. Ai chịu trách nhiệm?

Các vai trò thường gặp:

| Vai trò | Trách nhiệm chính |
|---|---|
| **Business/service owner** | Xác định mục đích, ưu tiên, yêu cầu nghiệp vụ, chấp nhận chi phí và rủi ro còn lại |
| **Technical/application owner** | Xác định workload, phụ thuộc, thông số tài nguyên, kiểm thử ứng dụng và dữ liệu |
| **Platform/cloud team** | Cung cấp mô hình landing zone, IaC module, guardrail, mạng, danh tính nền tảng, quan sát |
| **Security/compliance** | Xác định chính sách truy cập, phân loại dữ liệu, vùng lưu trữ, yêu cầu log và ngoại lệ |
| **Operations/SRE** | Xác minh monitoring, on-call, runbook, backup/restore, thay đổi và khôi phục |
| **FinOps/budget owner** | Xem xét ngân sách, nhãn phân bổ chi phí, cảnh báo và tài nguyên không sử dụng |

Một người có thể đảm nhận nhiều vai trò trong nhóm nhỏ, nhưng **mỗi môi trường vẫn cần ít nhất một owner chịu trách nhiệm và một kênh vận hành được chỉ định**. Không nên để môi trường có owner là một cá nhân đã rời nhóm mà không có người thay thế.

Ví dụ bảng RACI (R = thực hiện, A = chịu trách nhiệm cuối cùng, C = tham vấn, I = được thông báo):

| Hoạt động | Service owner | Platform | Security | Operations | FinOps |
|---|---|---|---|---|---|
| Xác nhận nhu cầu & hạn sử dụng | **A/R** | C | C | I | C |
| Thiết kế/cấp phát nền tảng | C | **A/R** | C | C | I |
| Phê duyệt ngoại lệ bảo mật | C | C | **A/R** | I | I |
| Nghiệm thu ứng dụng & vận hành | **A** | R | C | R | I |
| Rà soát chi phí/TTL | **A** | R | I | I | R |
| Chấp thuận ngừng và xử lý dữ liệu | **A** | R | C | C | I |
| Xác nhận đã gỡ tài nguyên | I | **A/R** | C | R | C |

Ma trận chỉ mang tính minh họa: các tổ chức có thể phân công khác nhau, nhưng cần tránh một bước vừa thiếu owner vừa thiếu người xác nhận.

## 3. Bước 1 — Tiếp nhận yêu cầu và xác định phạm vi

Hồ sơ môi trường nên đủ để xác định **mục đích, mức rủi ro, ranh giới và điểm kết thúc** ngay từ đầu. Tạo môi trường mà không có thông tin này sẽ khó quyết định chính sách mạng, quyền, chi phí và dữ liệu.

### 3.1. Bộ thông tin yêu cầu tối thiểu

| Trường | Ví dụ | Vì sao cần |
|---|---|---|
| Mã yêu cầu và người đề nghị | ENV-2026-042, nhóm Booking | Truy vết quyết định và thay đổi |
| Tên/service và loại môi trường | booking-preview-pr-248, preview | Gắn với workload và mục đích |
| Business/technical owner | Nhóm Booking, người trực theo nhóm | Xác nhận nhu cầu và xử lý sự cố |
| Thời gian bắt đầu, hết hạn/chu kỳ review | 14 ngày, review mỗi 7 ngày | Kiểm soát tài nguyên bỏ quên |
| Region và yêu cầu địa lý | Region gần người dùng mục tiêu; dữ liệu lưu theo chính sách | Độ trễ, tuân thủ, khả năng dịch vụ |
| Phân loại dữ liệu | Tổng hợp, không chứa PII | Quyết định quyền, backup, logging và retention |
| Thành phần cần có | API, relational DB, queue, object storage | Dự tính chi phí và phụ thuộc |
| Tải và mục tiêu độ tin cậy | 50 req/s thử nghiệm; không cần HA sản xuất | Chọn cỡ và mô hình triển khai |
| Network/ingress/egress | Chỉ CI + QA truy cập qua auth, hạn chế egress | Xác định trust boundary |
| Truy cập và tích hợp | Nhóm QA, pipeline test, provider giả lập | Quyết định danh tính và kết nối |
| Dự toán + budget owner | Trần chi phí thử nghiệm và cảnh báo | Ngăn tài nguyên chạy vượt dự kiến |
| Phụ thuộc và dữ liệu dùng chung | Dùng DNS sandbox, không kết nối payment production | Tránh xóa nhầm hoặc tích hợp nguy hiểm |
| Điều kiện kết thúc | PR đóng hoặc TTL hết, sau review | Cơ sở thu hồi đúng thời điểm |

Không cần mọi môi trường đều đi qua hội đồng phê duyệt. Với loại rủi ro thấp và guardrail đã thiết lập, có thể **cấp phát tự phục vụ** bằng template. Những trường hợp xử lý dữ liệu nhạy cảm, mở ingress công khai, chi phí lớn, cần quyền đặc biệt hoặc triển khai production có thể cần kiểm tra sâu hơn.

### 3.2. Ví dụ một yêu cầu dạng khai báo

Đoạn YAML minh họa **hồ sơ đầu vào cho workflow tự xây dựng**, không phải schema chuẩn của AWS/Azure/GCP hay công cụ IaC cụ thể:

~~~yaml
requestId: ENV-2026-042
service: booking-api
environment: preview
purpose: "Kiểm tra PR-248: tính năng lọc khung giờ"
owners:
  businessTeam: booking
  technicalTeam: booking-platform
  supportChannel: "booking-oncall"
lifecycle:
  requestedAt: "2026-11-18"
  expiresAt: "2026-12-02"
  reclaimOn: "pull-request-closed-or-TTL"
data:
  classification: synthetic
  productionCopyAllowed: false
location:
  region: "region-duoc-to-chuc-phe-duyet"
network:
  publicIngress: false
  egressPolicy: restricted
workload:
  apiInstances: 1
  database: managed-relational-small
  queue: managed-queue
budget:
  alertThresholdPercent: 80
  ownerTeam: booking
dependencies:
  sharedDnsZone: sandbox.example.test
  paymentProvider: mocked
acceptance:
  technicalOwner: booking-platform
  operationsOwner: booking-oncall
~~~

Những giá trị như tên region, cỡ tài nguyên và quota chỉ là ví dụ. Trong triển khai thật, hệ thống nhận hồ sơ cần kiểm tra schema, phân quyền người đề nghị, giá trị cho phép, ngày hết hạn và tính khả thi của dịch vụ tại khu vực.

### 3.3. Kiểm tra chính sách và phê duyệt

Trước khi phê duyệt, xác nhận:

1. **Mục đích và owner:** workload thuộc dịch vụ nào, ai chịu trách nhiệm khi hết hạn?
2. **Vùng triển khai và dữ liệu:** có vi phạm yêu cầu vị trí dữ liệu, bảo mật và retention không?
3. **Ranh giới truy cập:** cần Internet công khai hay chỉ mạng nội bộ? Có kết nối production không?
4. **Ngân sách và quota:** có vượt giới hạn tài khoản/project hoặc dự toán không?
5. **Kiến trúc:** cần số zone, backup và SLO ở mức nào? Có dùng dịch vụ đã được tổ chức phê duyệt không?
6. **Phụ thuộc chia sẻ:** có tài nguyên nào thuộc owner khác cần phối hợp khi tạo và khi hủy?
7. **Thời hạn:** ngày hết hạn hoặc sự kiện kích hoạt review/thu hồi là gì?

Các kiểm tra phổ biến có thể tự động: naming convention, required tag, region allowlist, loại instance được phép, cấm public database, bắt buộc mã hóa, giới hạn CIDR, quyền tối thiểu, budget và TTL. Trường hợp ngoại lệ cần mã phê duyệt, lý do, thời hạn và người chịu trách nhiệm.

## 4. Bước 2 — Thiết kế và cấp phát có kiểm soát

### 4.1. Chọn ranh giới cô lập phù hợp

| Phương án | Ưu điểm | Giới hạn và khi cần thận trọng |
|---|---|---|
| **Tài khoản/subscription/project riêng** | Ranh giới quota, IAM, billing và policy rõ; giảm nguy cơ tác động chéo | Tăng công việc thiết lập kết nối, policy và quản lý nhiều tài khoản |
| **Virtual network riêng trong một tài khoản** | Kiểm soát route/firewall riêng; dùng được nhiều dịch vụ chung | Vẫn chia sẻ một số quota, IAM, billing và cấp quản trị |
| **Namespace trong cluster dùng chung** | Tạo nhanh, sử dụng tài nguyên hiệu quả | Namespace không mặc nhiên là biên bảo mật mạnh; phải xét RBAC, NetworkPolicy, node sharing, secret và quota |
| **Tài nguyên chia sẻ có phân vùng logic** | Giảm chi phí môi trường nhỏ | Dễ xung đột tài nguyên, rò dữ liệu hoặc xóa nhầm khi thiếu phân quyền và ownership |

Với production hoặc dữ liệu nhạy cảm, thường cần mức cô lập mạnh hơn preview. Không quyết định chỉ dựa trên tiết kiệm tài nguyên: phải xét blast radius, quyền quản trị, nhu cầu audit, quota và thời gian xử lý sự cố.

### 4.2. Cấp phát bằng mẫu hạ tầng có phiên bản

**Infrastructure as Code (IaC)** mô tả cấu hình mong muốn và cho phép xem xét thay đổi trước khi áp dụng. Một workflow điển hình:

~~~mermaid
sequenceDiagram
    actor Requester as Service owner
    participant Portal as Request portal / Git PR
    participant Policy as Policy / Approval
    participant Pipe as IaC pipeline
    participant Cloud as Cloud control plane
    participant Check as Validation / Inventory
    Requester->>Portal: Gửi hồ sơ có owner, TTL, ngân sách, dữ liệu
    Portal->>Policy: Kiểm tra schema, quyền, chính sách và dự toán
    alt Không đạt
        Policy-->>Requester: Trả lý do và yêu cầu điều chỉnh
    else Được phê duyệt
        Policy->>Pipe: Cho phép plan/apply theo phiên bản đã review
        Pipe->>Cloud: Tạo tài nguyên và phân quyền đã giới hạn
        Cloud-->>Pipe: ID và trạng thái tài nguyên
        Pipe->>Check: Kiểm tra policy, network, logging, backup
        Check-->>Portal: Bằng chứng + inventory + trạng thái
    end
~~~

**Những thành phần cần có trong template** thường gồm cấu trúc account/project, network và route, IAM/workload identity, KMS/secret, compute, data store, logging/metrics, backup phù hợp, budget/tag/owner và policy. Cần tránh lặp cấu hình thủ công giữa các môi trường khi có thể quản lý bằng module IaC dùng chung.

Trong pipeline:

- Thay đổi phải được **review qua diff/plan**; đánh dấu rõ thao tác có thể tạo, sửa, thay thế hoặc xóa tài nguyên.
- Danh tính triển khai có quyền tối thiểu theo đúng scope và được bảo vệ khỏi sử dụng ngoài pipeline.
- State của IaC được lưu an toàn, có khóa/điều phối tránh ghi đồng thời và kiểm soát quyền; state có thể chứa thông tin nhạy cảm.
- Áp dụng policy-as-code hoặc kiểm tra cấu hình theo quy tắc của tổ chức; không cấp quyền rộng chỉ để pipeline “dễ chạy”.
- Kết quả cấp phát phải đăng ký vào inventory với ID tài nguyên, owner, mã yêu cầu, TTL và địa chỉ liên hệ vận hành.

Ví dụ **mã giả** minh họa các bước, không phải cú pháp của một nhà cung cấp:

~~~text
validate(request) -> check_owner_policy_budget_ttl()
design = generate_iac_from_approved_template(request)
review(design.plan) -> approve_with_change_record()
apply_with_scoped_identity(design)
verify(network, iam, tags, encryption, monitoring, backup)
register_inventory(resource_ids, owner, ttl, dependency_graph)
create_acceptance_package()
~~~

### 4.3. Quy ước tên, nhãn và inventory

Nên quy định tên dễ tìm, có ngữ nghĩa vừa đủ, không nhúng bí mật hoặc dữ liệu cá nhân. Ví dụ:

~~~text
Tên logic: booking-preview-pr248-api
Tags/labels:
  service      = booking
  environment  = preview
  ownerTeam    = booking-platform
  costCenter   = product-booking
  requestId    = ENV-2026-042
  lifecycle    = ephemeral
  expiresAt    = 2026-12-02
  managedBy    = iac
~~~

Tên và tag không thay thế **resource ID** do nhà cung cấp cấp. Inventory nên lưu ID chính xác, account/project/region, trạng thái, quan hệ sở hữu và phụ thuộc, thời điểm tạo, bản IaC, chính sách backup, chi phí ước tính/thực tế và thời hạn. Các dịch vụ không hỗ trợ tag như mong muốn cần mapping inventory riêng. Nên kiểm tra định kỳ tài nguyên không có owner hoặc không khớp IaC để phát hiện drift.

### 4.4. Kiểm soát chi phí và khả năng mở rộng ngay khi tạo

Tại bước cấp phát cần có:

- **Budget và cảnh báo:** chủ sở hữu ngân sách, ngưỡng theo dõi, escalation và cách xử lý khi vượt dự báo.
- **Quota/service limit:** không để môi trường mới chiếm toàn bộ quota mà production cần.
- **Capacity policy:** kích thước mặc định theo loại môi trường, trần autoscaling và giới hạn chi phí bất thường.
- **Retention/lifecycle:** log, snapshot, object, volume và tài nguyên tạm có chính sách sống/chết rõ ràng.
- **Accountability:** tag và báo cáo chi phí theo service, môi trường, owner hoặc cost center.

Budget alert thường chỉ là tín hiệu và có độ trễ đo lường; **không được giả định nó tự ngăn mọi phát sinh chi phí**. Muốn giới hạn chặt phải kết hợp quota, policy, thiết kế capacity và biện pháp vận hành phù hợp.

## 5. Bước 3 — Kiểm tra sau cấp phát và nghiệm thu kỹ thuật

Một môi trường chỉ được chuyển sang trạng thái **Ready for acceptance** sau khi có bằng chứng nó đáp ứng thiết kế đã được chấp thuận. Cần tách hai tầng kiểm tra:

1. **Infrastructure validation:** các tài nguyên tồn tại, kết nối mạng đúng, policy được áp dụng, quyền và nhãn đúng, quan sát hoạt động.
2. **Workload validation:** ứng dụng deploy được, các luồng nghiệp vụ mẫu chạy đúng, dữ liệu và tích hợp có trạng thái xác định, owner có thể tiếp nhận.

Nếu mới cấp phát database mà chưa thử một kết nối có danh tính hợp lệ, chưa biết backup policy có bật đúng hay không, thì chưa đủ cơ sở nghiệm thu.

### 5.1. Checklist và bằng chứng nghiệm thu

| Nhóm kiểm tra | Tiêu chí đạt minh họa | Bằng chứng cần lưu |
|---|---|---|
| **Identity/IAM** | Người dùng và workload chỉ có quyền theo nhiệm vụ; quyền quản trị có MFA nếu chính sách yêu cầu | Kết quả kiểm tra IAM, vai trò đã phê duyệt, phép thử truy cập từ chối |
| **Network** | Ingress/egress, subnet, route, firewall đúng sơ đồ; DB không mở trực tiếp Internet | Network test, cấu hình policy, kết quả thử kết nối từ ngoài |
| **Mã hóa và bí mật** | TLS, mã hóa dữ liệu lưu trữ, secrets đi qua kho quản lý; không nằm trong code/log | Policy scan, kết quả cấu hình, kiểm tra secret handling |
| **Compute và storage** | Đúng loại/cỡ/vùng; ứng dụng khởi động và truy cập kho dữ liệu | Smoke test, health check, thông số tài nguyên |
| **Dữ liệu** | Dữ liệu đúng phân loại; dữ liệu tổng hợp cho preview; quyền đọc/ghi giới hạn | Báo cáo phân loại, cấu hình retention, truy cập kiểm thử |
| **Quan sát** | Log, metrics, tracing cần thiết có dữ liệu; cảnh báo đến đúng nhóm | Dashboard, bài test cảnh báo, liên kết on-call |
| **Độ tin cậy** | Cấu hình replica/backup theo yêu cầu môi trường; khôi phục đã được thử khi bắt buộc | Kết quả backup và restore drill, runbook, RTO/RPO đo được |
| **Delivery** | Pipeline triển khai và rollback phù hợp; không cần thao tác thủ công không được ghi nhận | Bản ghi release/smoke test, artifact ID, kế hoạch rollback |
| **FinOps** | Tag/owner đầy đủ, budget/alert/quota đã có; chi phí dự toán được xác nhận | Bảng tính hoặc cost report, kết quả policy gate |
| **Inventory** | Resource ID, ranh giới IaC, phụ thuộc và TTL được đăng ký | Snapshot inventory, liên kết request/change, owner |

Không phải môi trường dev nào cũng cần DR hoặc SLO như production. **Tiêu chí nghiệm thu phải bám theo mức dịch vụ đã yêu cầu**, với ngoại lệ có chủ sở hữu phê duyệt và thời hạn rà soát.

### 5.2. Smoke test xuyên các tầng

Với ứng dụng đặt lịch, một phép thử tối thiểu có thể:

1. Tạo phiên đăng nhập bằng cơ chế xác thực dành cho môi trường này, kiểm tra quyền truy cập endpoint.
2. Gọi API tra cứu, xác nhận TLS, routing, load balancer và log/correlation ID.
3. Tạo booking với dữ liệu tổng hợp; kiểm tra transaction và quyền truy cập database.
4. Phát sự kiện thử vào queue và xác nhận worker nhận, xử lý, ghi kết quả mà không gọi nhầm nhà cung cấp production.
5. Gửi lại cùng idempotency key; xác nhận không tạo booking trùng.
6. Kiểm tra telemetry từ API, database, worker và cảnh báo mẫu; xóa dữ liệu thử theo chính sách.

Đối với môi trường có yêu cầu chịu lỗi, bổ sung bài thử mất một instance/zone phù hợp phạm vi; với môi trường cần backup, tối thiểu phải có lịch kiểm chứng restore và người thực hiện. Việc thử “API trả 200” không thay thế kiểm tra phân quyền, dữ liệu hay khôi phục.

### 5.3. Quản lý lỗi nghiệm thu

Khi kiểm tra không đạt, ghi **điều kiện thất bại → mức tác động → hành động sửa → người chịu trách nhiệm → lần kiểm tra lại**. Nếu cấu hình cần thay đổi, ưu tiên sửa trong nguồn IaC rồi áp dụng lại qua workflow, tránh một bản vá thủ công khiến môi trường khác khác biệt.

Đối với lỗi bảo mật nghiêm trọng như database công khai ngoài dự kiến hoặc thiếu kiểm soát danh tính, không bàn giao như môi trường đã sẵn sàng. Với rủi ro thấp được chấp nhận tạm thời, phải ghi ngoại lệ rõ nội dung, owner và ngày hết hạn.

## 6. Bước 4 — Bàn giao và tiếp nhận vận hành

**Bàn giao** là việc chuyển toàn bộ thông tin cần thiết để sử dụng và duy trì môi trường, **tiếp nhận** là xác nhận trách nhiệm thực tế. Nếu chỉ gửi đường dẫn console và thông báo “đã dựng xong”, khi phát sinh sự cố sẽ không rõ ai có quyền, ai được gọi hoặc thao tác nào an toàn.

### 6.1. Gói bàn giao tối thiểu

Một **acceptance package** có thể gồm:

- **Danh tính môi trường:** tên, ID account/project/subscription, region, loại môi trường, trạng thái, owner, mã yêu cầu, liên kết inventory.
- **Sơ đồ logic và phụ thuộc:** ingress/egress, network boundary, compute, dữ liệu, queue, secret, DNS, kết nối hệ thống dùng chung và bên thứ ba.
- **Tài liệu IaC:** repository/đường dẫn cấu hình, version/tag áp dụng, pipeline, vị trí quản lý state và cách review thay đổi.
- **Quyền và truy cập:** nhóm người dùng, danh tính workload, phương pháp cấp/rút quyền, yêu cầu MFA, quy trình truy cập khẩn cấp nếu áp dụng.
- **Triển khai ứng dụng:** build artifact, môi trường/runtime, quy trình release, smoke test, rollback hoặc cách xử lý khi rollback không phù hợp.
- **Observability:** dashboard, log, tracing, metric nghiệp vụ, cảnh báo, mức ưu tiên và kênh nhận cảnh báo.
- **Khôi phục:** backup schedule/retention, phạm vi HA/DR, quy trình restore, kết quả diễn tập, mục tiêu RTO/RPO nếu có.
- **Dữ liệu và bảo mật:** mức phân loại, chủ dữ liệu, hạn lưu, quy tắc sử dụng dữ liệu thật, key/secret rotation và audit log.
- **Chi phí và vòng đời:** ngân sách, cảnh báo, tag/cost center, quota, ngày review/TTL, điều kiện và đầu mối thu hồi.
- **Rủi ro còn lại:** ngoại lệ được chấp nhận, giới hạn thiết kế và kế hoạch khắc phục.

Tài liệu bàn giao nên **trỏ đến vị trí được quản trị tập trung** thay vì chép mật khẩu, private key hoặc token vào biên bản. Thông tin bí mật phải nằm trong hệ thống quản lý secret; tài liệu chỉ hướng dẫn cách xin và dùng quyền.

### 6.2. Mẫu biên bản nghiệm thu có tiêu chí kiểm tra

| Nội dung | Giá trị minh họa |
|---|---|
| Environment | booking-staging |
| Business owner | Nhóm Booking |
| Technical owner | Nhóm Backend |
| Operations/on-call | Nhóm Platform/SRE |
| Infrastructure version | Tham chiếu commit/release IaC cụ thể |
| Workload version | Tham chiếu artifact đã thử thành công |
| Kiểm thử đã đạt | Policy scan, smoke test, alert route, backup check |
| Kiểm thử chưa đạt/ngoại lệ | Nêu mã issue, owner, hạn xử lý và ảnh hưởng |
| RTO/RPO | Có giá trị cụ thể theo kịch bản nếu nghiệp vụ yêu cầu |
| Chi phí ước tính | Theo mô hình tải đã nêu; kèm ngân sách được duyệt |
| Hết hạn/review | Ngày và trách nhiệm rà soát |
| Kết luận | Accepted / Accepted with approved exceptions / Rejected |

Để chuyển sang **Active**, người chịu trách nhiệm cuối cùng phải chấp nhận kết quả và đội vận hành xác nhận có **thông tin, quyền và công cụ** cần thiết. Nên lưu thời điểm tiếp nhận, người xác nhận và phiên bản cấu hình được nghiệm thu. Với môi trường preview tạo/hủy liên tục, biên bản có thể được tự động hóa bằng policy và test thay cho ký tay từng lần.

### 6.3. Phân biệt tiếp nhận ứng dụng và tiếp nhận hạ tầng

Platform team có thể bàn giao VPC, IAM, cluster hoặc database hoạt động đúng; nhưng **application owner** vẫn cần xác nhận bản deploy, đường đi nghiệp vụ và quản lý dữ liệu. Operations team nhận on-call/runbook, nhưng không tự trở thành chủ sở hữu nghiệp vụ hay dữ liệu. Ranh giới trách nhiệm phải được ghi để tránh tình huống “hạ tầng báo xanh, ứng dụng không dùng được”.

## 7. Bước 5 — Duy trì môi trường trong thời gian sử dụng

Sau nghiệm thu, môi trường chuyển sang **Active** và cần được theo dõi liên tục về cấu hình, quyền, tài nguyên, chi phí và thời hạn.

### 7.1. Các nhịp rà soát

| Sự kiện/chu kỳ | Hoạt động | Ai cần tham gia |
|---|---|---|
| Khi phát hành hoặc thay đổi hạ tầng | Review IaC plan, policy, backward compatibility, rollout/rollback | Technical owner + Platform, Security theo rủi ro |
| Định kỳ ngắn đối với preview | Kiểm tra TTL, PR liên quan, owner còn hoạt động, chi phí | Pipeline/automation và owner |
| Định kỳ theo chính sách tổ chức | Soát IAM, token, cấu hình công khai, cảnh báo, backup | Platform, Security, Operations |
| Khi SLO/capacity thay đổi | Load test, giới hạn scale, quota, ngân sách, rủi ro tập trung | Service owner, Operations, FinOps |
| Khi đổi owner hoặc đội phụ trách | Bàn giao inventory, alert, quyền và tài liệu | Owner cũ, owner mới, Operations |
| Trước khi hết hạn | Xác nhận gia hạn hoặc bắt đầu quy trình thu hồi | Service owner, Platform, dữ liệu nếu liên quan |

Tần suất là quyết định nội bộ tùy môi trường, độ nhạy cảm dữ liệu và mức tác động. Không tự hiểu rằng mọi preview phải chạy liên tục 24/7 hoặc mọi staging được phép tắt bất kỳ lúc nào: cần dựa trên lịch sử dụng và rủi ro được xác định.

### 7.2. Phát hiện drift và tài nguyên mồ côi

**Configuration drift** xảy ra khi cấu hình cloud thực tế không còn khớp trạng thái mong muốn trong IaC, ví dụ có người sửa firewall trên console. Drift có thể gây lỗ hổng bảo mật, lỗi deploy hoặc làm hỏng thao tác thu hồi.

Kiểm soát cần gồm:

1. So sánh định kỳ actual state với IaC/policy và lưu kết quả.
2. Tạo issue/cảnh báo cho drift có ảnh hưởng bảo mật, độ tin cậy hoặc chi phí.
3. Quy định thời gian và cách xử lý thay đổi khẩn cấp ngoài pipeline; đưa thay đổi hợp lệ trở lại IaC.
4. Tìm tài nguyên **không có owner, không có tag, không còn nằm trong state, không còn ứng dụng sử dụng**.
5. Không tự động xóa tài nguyên chỉ vì thiếu tag: phải xác minh chủ sở hữu, dữ liệu, phụ thuộc và trạng thái hợp lệ.

### 7.3. Thiết kế tự phục vụ có guardrail

Một cổng self-service tốt có thể cho phép nhóm phát triển tự tạo môi trường preview từ template chuẩn. Tốc độ có thể nhanh vì các quyết định chính được mã hóa trước: region được cho phép, loại tài nguyên, phân quyền, quota, TTL, dữ liệu tổng hợp và bộ kiểm tra nghiệm thu. Các môi trường ngoại lệ được chuyển sang quy trình review tương ứng thay vì được cấp quyền quản trị rộng.

Đây là một đánh đổi kiến trúc: tự phục vụ giảm thời gian chờ nhưng đòi hỏi đầu tư ban đầu vào platform, policy-as-code, inventory và kiểm soát vòng đời. Việc cấp phát tự phục vụ thành công không miễn trừ trách nhiệm owner về chi phí hoặc dữ liệu.

## 8. Bước 6 — Thu hồi môi trường an toàn và có bằng chứng

**Thu hồi là một hoạt động kiến trúc có thể tác động đến dữ liệu và dịch vụ khác**, không đơn thuần là chạy lệnh xóa. Cần phân biệt:

- **Tắt tạm (suspend/stop):** giảm hoặc ngừng một phần compute; volume, IP, log, database, snapshot và dịch vụ quản lý có thể vẫn tính phí.
- **Ngừng phục vụ (retire):** chuyển luồng truy cập khỏi môi trường, kết thúc trách nhiệm vận hành chính theo kế hoạch nhưng tài nguyên có thể còn để hoàn tất lưu giữ.
- **Thu hồi hoàn toàn (decommission/destroy):** xử lý dữ liệu theo retention, rút quyền và loại bỏ tài nguyên trong phạm vi sở hữu sau khi đã xác minh điều kiện an toàn.

Không đánh đồng **hết TTL** với **đã được phép xóa mọi dữ liệu**. TTL là tín hiệu bắt đầu rà soát hoặc thực hiện policy đã được chấp thuận từ trước; production và dữ liệu có yêu cầu lưu giữ phải tuân thủ phê duyệt tương ứng.

### 8.1. Điều kiện bắt đầu và phê duyệt

Các tác nhân có thể kích hoạt thu hồi:

- Branch/PR liên quan đã đóng, chiến dịch thử nghiệm hoàn tất, dự án ngừng.
- Ngày hết hạn đã đến và owner không gia hạn trong cửa sổ thông báo.
- Dịch vụ đã chuyển sang môi trường thay thế, lưu lượng và dữ liệu được di chuyển.
- Môi trường vi phạm chính sách hoặc không còn owner; cần kiểm tra, điều tra và quyết định hợp lệ.

Trước khi thực hiện, xác nhận **environment ID, owner, mục đích, phạm vi, dependency graph, dữ liệu, nghĩa vụ lưu giữ, người phê duyệt và thời điểm**. Các môi trường preview không chứa dữ liệu thật có thể được cho phép tự thu hồi khi PR đóng nếu chính sách tạo môi trường đã quy định rõ. Với production, môi trường chứa dữ liệu nhạy cảm hoặc tài nguyên chia sẻ, cần kiểm tra và phê duyệt theo rủi ro cao hơn.

### 8.2. Quy trình thu hồi từng bước

~~~mermaid
flowchart TD
    A[Đề nghị thu hồi: ID, lý do, owner] --> B[Kiểm tra phụ thuộc và quyền sở hữu]
    B --> C{Có dữ liệu cần giữ / legal hold / phụ thuộc?}
    C -- Có --> D[Hoàn tất export / migration / retention / chuyển owner]
    D --> E[Xác nhận dữ liệu và điều kiện kết thúc]
    C -- Không --> E
    E --> F{Phê duyệt theo loại môi trường?}
    F -- Chưa --> G[Giữ nguyên / xử lý điều kiện còn thiếu]
    G --> B
    F -- Đủ --> H[Ngừng traffic / job / write và thông báo]
    H --> I[Thu hồi credentials, routes và quyền liên quan]
    I --> J[Review destroy plan, chỉ đúng tài nguyên sở hữu]
    J --> K[Thực hiện teardown qua IaC/workflow]
    K --> L[Đối soát inventory, dữ liệu, chi phí, DNS, log]
    L --> M{Còn tài nguyên hoặc nghĩa vụ?}
    M -- Có --> N[Cleanup có kiểm soát và theo dõi]
    N --> L
    M -- Không --> O[Lưu biên bản và chuyển Retired / Closed]
~~~

Trình tự trên có thể điều chỉnh theo dependency. Ví dụ cần xuất dữ liệu trước khi rút quyền đọc; cần xóa hoặc chuyển bản ghi DNS trước khi bỏ endpoint; cần chặn writer và đồng bộ dữ liệu trước khi xóa database; quyền triển khai phải bị rút theo thời điểm phù hợp để ngăn hệ thống tái tạo tài nguyên. Không tồn tại một thứ tự xóa cố định an toàn cho mọi kiến trúc.

### 8.3. Danh sách kiểm tra phụ thuộc theo lớp tài nguyên

| Lớp | Câu hỏi phải xác minh trước khi gỡ | Tình huống dễ bỏ sót |
|---|---|---|
| **DNS/edge** | Có domain, CDN, WAF rule, certificate, health check dùng chung không? | DNS còn trỏ tới endpoint đã bị xóa; certificate còn tự gia hạn tính phí |
| **Network** | IP, NAT, VPN, load balancer, private endpoint, peering và route thuộc ai? | Egress/NAT hoặc public IP còn tính phí; xóa route làm hỏng hệ thống khác |
| **Compute/orchestration** | Có VM, container, job, scheduler, autoscaling group, serverless function liên quan? | Scheduler hoặc controller tạo lại tài nguyên sau khi xóa |
| **Database/storage** | Dữ liệu cần export, archive, giữ bao lâu, ai có quyền khôi phục? | Xóa DB trước khi backup; snapshot/volume/object vẫn còn chi phí |
| **Queue/events** | Message chưa xử lý, subscription, dead-letter queue, event rule có phụ thuộc? | Message thất lạc hoặc trigger vẫn gọi endpoint đã xóa |
| **Identity/secrets** | Workload identity, role, token, key, secret, service principal dùng riêng hay chung? | Credential còn hiệu lực hoặc xóa nhầm secret dùng chung |
| **Observability** | Có log, metric, dashboard, alert, audit trail phải giữ theo chính sách? | Xóa luôn bằng chứng sự cố hoặc log vẫn phát sinh tính phí |
| **CI/CD/IaC** | Pipeline, backend state, biến môi trường, deploy key và webhook có còn chạy? | Job tự cấp phát lại workload; state bị xóa không kiểm soát |
| **Billing/quota** | Các tài nguyên bị quản lý ngoài IaC và khoản phí chậm có còn không? | Hóa đơn còn tăng do backup, storage, support hoặc dịch vụ chia sẻ |

Tài nguyên **dùng chung** phải được chuyển owner hoặc giữ nguyên theo dependency. Không cho phép pipeline xóa cả một account/project chỉ vì môi trường mục tiêu đã hết hạn khi trong đó còn workload khác.

### 8.4. Xử lý dữ liệu, backup và retention

Trước khi xóa dữ liệu, xác minh:

1. **Phân loại và chủ dữ liệu:** dữ liệu cá nhân, dữ liệu hợp đồng, log kiểm toán, dữ liệu thử hay dữ liệu có ràng buộc lưu trữ?
2. **Nghĩa vụ lưu giữ:** thời hạn retention, yêu cầu pháp lý, legal hold, quyền xóa theo quy định và trách nhiệm phê duyệt.
3. **Kết quả di chuyển/export:** dữ liệu đã chuyển sang nơi mới chưa, đã đối soát số lượng và tính toàn vẹn chưa?
4. **Backup/snapshot:** bản nào tiếp tục giữ, bản nào phải xóa, ai quản lý khóa giải mã và thời hạn?
5. **Phương pháp xóa:** xóa logic, hủy tài nguyên, xóa khóa hoặc cơ chế xóa dữ liệu theo cam kết của nhà cung cấp và chính sách tổ chức; xác minh phạm vi, khả năng phục hồi và rủi ro.

**Không vội hủy khóa mã hóa** khi vẫn còn bản sao lưu cần đọc để đáp ứng retention hoặc khôi phục dữ liệu; việc mất khóa có thể khiến dữ liệu không thể phục hồi. Ngược lại, chỉ giữ backup “cho chắc” vô thời hạn có thể vi phạm retention và phát sinh chi phí. Phải ghi lại quyết định giữ/xóa theo chính sách hiện hành và quyền của chủ dữ liệu.

Với môi trường preview dùng **chỉ dữ liệu tổng hợp**, quy trình có thể đơn giản hơn nhiều: kiểm tra không có dữ liệu thật và không có phụ thuộc chung rồi xóa theo TTL đã duyệt. Với production cần kế hoạch chuyển tải, thông báo, đối soát dữ liệu, quyền truy cập, audit trail và thời gian lưu giữ rõ ràng.

### 8.5. Teardown bằng IaC và kiểm soát blast radius

Một workflow có kiểm soát nên:

- Chỉ chạy với **environment ID và scope đã xác thực**; hiển thị account/project/region và danh sách resource ID sẽ bị xóa.
- Đối chiếu danh sách tài nguyên với **inventory, owner, policy, tag và state**; tag chỉ là trợ giúp chứ không đủ để xác định quyền sở hữu.
- Tạo **destroy plan**, yêu cầu review theo mức rủi ro và đặc biệt kiểm tra database, networking, key, tài nguyên chia sẻ.
- Tránh xóa state IaC trước khi biết tài nguyên đã được gỡ. Nếu state lệch, thực hiện quy trình reconcile/import/cleanup được kiểm soát.
- Ghi log thao tác, tài khoản thực hiện, các lỗi chưa giải quyết và resource ID thực tế đã thu hồi.
- Chặn pipeline, controller, scheduler hoặc automation có thể tự dựng lại môi trường sau khi xóa.

Không nên dùng một script duy nhất cố gắng xóa tất cả theo tiền tố tên; cách đó dễ xóa nhầm tài nguyên có tên gần giống và không hiểu dependency. Trong trường hợp destroy thất bại giữa chừng, cần lưu trạng thái phần còn lại và tiếp tục có kiểm soát, tránh tuyên bố hoàn tất khi chưa đối soát.

### 8.6. Khi nào có thể xác nhận “đã thu hồi”?

Đặt tiêu chí hoàn thành có bằng chứng:

| Nhóm | Bằng chứng xác nhận |
|---|---|
| **Lưu lượng và nghiệp vụ** | Không còn routing hoặc job ghi tới môi trường; hệ thống thay thế đã tiếp nhận nếu có |
| **Dữ liệu** | Export/migration/retention/xóa hoàn tất theo quyết định đã phê duyệt; bản sao lưu giữ lại có owner và ngày hết hạn |
| **Tài nguyên** | Inventory và cloud API không còn tài nguyên mục tiêu ngoài danh sách giữ lại đã duyệt |
| **Quyền** | Danh tính, token, vai trò, truy cập CI/CD dành riêng cho môi trường đã rút/điều chỉnh |
| **Phụ thuộc** | DNS, webhook, event, queue, route, alert, dashboards, certificate được làm sạch hoặc chuyển owner |
| **Chi phí** | Có kiểm tra báo cáo chi phí sau thu hồi qua chu kỳ cập nhật billing, xử lý khoản phí còn lại |
| **Hồ sơ** | Ticket/ADR/runbook cập nhật, ai xác nhận, ngày đóng, ID tài nguyên và ngoại lệ lưu giữ |

**Dữ liệu billing có thể đến chậm**, vì vậy “không còn tài nguyên” và “không còn khoản phí phát sinh trong báo cáo tiếp theo” là hai điều kiện cần kiểm tra vào những thời điểm khác nhau. Có thể đóng phần hạ tầng sau đối soát kỹ thuật, nhưng vẫn duy trì một mục theo dõi hậu thu hồi cho đến khi chi phí và retention được xử lý.

## 9. Tự động hóa vòng đời và các tình huống ngoại lệ

### 9.1. Thiết kế bộ điều khiển TTL cho môi trường tạm

Một controller định kỳ có thể phát hiện preview hết hạn và thực hiện các bước sau:

~~~text
for each environment in inventory:
    if environment.lifecycle != "ephemeral":
        continue
    if not is_expired(environment) and not source_event_closed(environment):
        continue
    notify(environment.owner, proposed_reclaim)
    if has_approved_extension(environment):
        update_expiry_and_audit(environment)
        continue
    if has_legal_hold_or_unknown_owner_or_shared_dependency(environment):
        open_review_ticket(environment)
        continue
    if not satisfies_preapproved_reclaim_policy(environment):
        open_review_ticket(environment)
        continue
    quiesce_and_check_data(environment)
    review_scope_and_teardown(environment)
    reconcile_inventory_and_cost_followup(environment)
~~~

Đây là **mã giả logic**, không phải script production. Việc tự động thu hồi chỉ thích hợp khi loại tài nguyên, quyền, dữ liệu và rủi ro đã được quy định trước. Điều kiện hết TTL một mình không đủ cho phép xóa production, dữ liệu có retention hoặc tài nguyên dùng chung. Việc kiểm tra owner vắng mặt phải mở luồng chuyển ownership/xử lý ngoại lệ, không tự diễn giải là được phép xóa.

### 9.2. Một số tình huống khó cần xử lý riêng

**Tình huống A — Preview dùng chung database staging:** nếu destroy preview xóa luôn database thì ảnh hưởng các nhóm khác. Cần phân biệt quyền sở hữu database và đối tượng dữ liệu thuộc preview, chỉ xóa dữ liệu/schema có cơ chế bảo đảm phạm vi, sau khi xác nhận ảnh hưởng và retention. Với độ rủi ro cao, chuyển sang database riêng ngay từ thiết kế.

**Tình huống B — Môi trường đã hết hạn nhưng có tài khoản không rõ chủ:** không đủ điều kiện thu hồi tự động. Đưa vào hàng đợi xác minh với service owner của sản phẩm, platform và security, áp dụng biện pháp giảm rủi ro phù hợp trong lúc tìm owner.

**Tình huống C — Đã stop VM nhưng hóa đơn vẫn tăng:** kiểm tra volume, snapshot, IP, NAT/load balancer, database, log, dịch vụ quản lý và chi phí lưu trữ. Stop và destroy khác nhau về đối tượng và chính sách tính phí.

**Tình huống D — Thay môi trường production bằng môi trường mới:** cần chuyển DNS/traffic, bảo đảm tương thích dữ liệu và hoàn thành đối soát trước khi gỡ. Có thể duy trì bản cũ ở chế độ chỉ đọc hoặc ngừng ghi trong cửa sổ quan sát, nhưng phải đặt thời hạn và quyết định giữ/xóa rõ ràng.

**Tình huống E — Pipeline có quyền rộng và tạo lại môi trường:** thu hồi tài nguyên mà quên gỡ trigger/webhook hoặc quyền deployment sẽ không có hiệu lực lâu dài. Cần chuyển hoặc vô hiệu hóa cấu hình triển khai liên quan, sau đó đối soát lại cloud state.

**Tình huống F — Backup còn thời hạn nhưng owner dự án đã giải tán:** chuyển ownership backup cho đơn vị chịu nghĩa vụ lưu giữ, ghi key và chính sách truy cập, lịch xóa sau retention. Không để tài nguyên “không owner” tồn tại mãi.

## 10. Đánh giá quy trình theo Well-Architected

Vòng đời môi trường phản ánh nhiều trụ cột kiến trúc:

| Trụ cột | Câu hỏi cần đánh giá | Dấu hiệu kiểm chứng |
|---|---|---|
| **Operational Excellence** | Có thể tạo, kiểm tra, tiếp nhận, thay đổi và thu hồi lặp lại được không? | Pipeline, ticket, runbook, owner, thời gian cấp phát, lỗi thao tác |
| **Security** | Quyền tối thiểu và phân loại dữ liệu có được áp dụng từ lúc tạo đến khi xóa? | IAM scan, encryption, audit, kiểm tra quyền sau thu hồi |
| **Reliability** | Môi trường có backup/HA/DR tương ứng yêu cầu và biết ai chịu sự cố? | SLO, restore/failover test, on-call, dependency map |
| **Performance Efficiency** | Tài nguyên có đúng nhu cầu và được rà soát capacity không? | Load test, utilization, quota, resize theo số liệu |
| **Cost Optimization** | Có owner, budget, TTL và bằng chứng dừng phí sau thu hồi? | Allocation tags, chi phí theo môi trường, báo cáo mồ côi |
| **Sustainability** | Có tránh tài nguyên dư thừa, tự tắt thử nghiệm không dùng, quản lý vòng đời storage? | TTL compliance, thời gian chạy, xóa preview, storage lifecycle |

Không nên tối ưu một trụ cột một cách đơn lẻ. Ví dụ xóa mọi môi trường staging để giảm chi phí có thể làm giảm khả năng thử tương thích và tăng rủi ro khi deploy production. Ngược lại, giữ mọi preview vô thời hạn để “tránh xóa nhầm” làm tăng chi phí, bề mặt tấn công và rác vận hành. Quy trình tốt chọn mức tự động hóa và kiểm soát dựa trên **mục đích, độ rủi ro và bằng chứng**.

### 10.1. Metric vận hành quy trình

Có thể đo:

- **Provisioning lead time:** từ yêu cầu hợp lệ đến môi trường sẵn sàng; chia theo mức rủi ro để phát hiện điểm nghẽn.
- **First-pass acceptance rate:** tỷ lệ môi trường đạt nghiệm thu ngay lần đầu, phản ánh chất lượng template/guardrail.
- **Ownership completeness:** tỷ lệ môi trường có owner, cost center, dependency map và kỳ review hợp lệ.
- **Policy exception age:** số ngoại lệ tồn quá hạn hoặc chưa có người xử lý.
- **TTL compliance:** tỷ lệ preview hết hạn được gia hạn đúng quy trình hoặc thu hồi theo chính sách.
- **Orphaned resource count/cost:** số và chi phí tài nguyên không xác định được owner hoặc không khớp inventory.
- **Decommission completeness:** tỷ lệ thu hồi đủ bằng chứng về tài nguyên, quyền, dữ liệu và kiểm tra billing.
- **Drift remediation time:** thời gian đưa sai lệch cấu hình về trạng thái được chấp thuận.

Các metric cần phân loại theo loại môi trường. Không đặt mục tiêu giảm thời gian phê duyệt production bằng mọi giá; mục tiêu là **nhanh đối với công việc đã được chuẩn hóa, có kiểm soát tại những điểm có tác động lớn**.

## 11. Bài thực hành: vòng đời môi trường cho một dịch vụ đặt lịch

**Bối cảnh:** Nhóm Booking có hệ thống production đang chạy. Họ cần một staging để thử thay đổi schema và một môi trường preview cho pull request mới. Preview dự kiến dùng 10 ngày, tạo API, database nhỏ, queue và object storage, không dùng dữ liệu thật. Staging cần giả lập giao tiếp với payment provider. Sau đợt thử nghiệm, preview phải thu hồi; staging vẫn phục vụ các bản phát hành tiếp theo.

Hãy xây dựng một bản thiết kế quy trình gồm:

1. **Hồ sơ yêu cầu:** điền mục đích, loại môi trường, owner, ngày hết hạn/review, phân loại dữ liệu, mạng, dịch vụ, ngân sách và dependency cho preview và staging.
2. **Phân quyền/phê duyệt:** lập RACI cho service owner, platform, security, operations, FinOps; chỉ rõ trường hợp được tự phục vụ và trường hợp bắt buộc review.
3. **Kiến trúc cấp phát:** vẽ sơ đồ account/project, network, compute, database, queue, IAM, logging; giải thích mức cô lập giữa preview, staging và production.
4. **IaC và policy gate:** mô tả input template, kiểm tra public ingress, TTL, required tags, quota, mã hóa, secret và resource ownership.
5. **Nghiệm thu:** tạo checklist có bằng chứng cho smoke test, quyền truy cập, log/alert, backup nếu yêu cầu, kiểm tra mock payment và dự toán chi phí.
6. **Bàn giao:** đề xuất acceptance package gồm owner, runbook, dashboard, pipeline, địa chỉ liên hệ, version IaC và rủi ro còn lại.
7. **Thu hồi preview:** mô tả trigger khi PR đóng/hết TTL, kiểm tra dữ liệu/phụ thuộc, destroy plan, revoke credential, xóa job/DNS và đối soát chi phí.
8. **Đánh giá Well-Architected:** nêu ít nhất một rủi ro cho mỗi trụ cột, cách giảm thiểu và bằng chứng đóng rủi ro.

Ví dụ một bảng kiểm tra trước khi đóng yêu cầu thu hồi:

| Câu hỏi | Kết quả cần ghi | Bằng chứng/owner |
|---|---|---|
| Đúng môi trường và ID cần thu hồi? | Có/Không | Inventory + mã yêu cầu |
| Dữ liệu có nghĩa vụ lưu trữ không? | Không/Có và quyết định lưu | Chủ dữ liệu + policy |
| Có tài nguyên chung với staging/prod? | Không/Có và phương án xử lý | Dependency graph |
| Traffic, trigger, job đã ngừng? | Có/Không | Monitoring + cấu hình |
| Credential và quyền đã rút? | Có/Không | IAM/secret review |
| Danh sách xóa đã được review? | Có/Không | IaC destroy plan |
| Còn tài nguyên hoặc khoản phí cần theo dõi? | Không/Có và ticket phụ | Inventory + billing report |
| Ai xác nhận đóng? | Tên vai trò, thời điểm | Biên bản audit |

**Tiêu chí hoàn thành:** Một người vận hành khác có thể tạo lại môi trường từ hồ sơ và IaC đã được duyệt, kiểm tra chất lượng trước khi sử dụng, biết ai chịu trách nhiệm trong suốt vòng đời, rồi thu hồi mà không mất dữ liệu cần giữ hoặc ảnh hưởng đến hệ thống dùng chung.

## 12. Các nguyên tắc mang theo

1. **Không có môi trường vô chủ:** mỗi môi trường cần owner, mục đích, ranh giới tài nguyên và điều kiện kết thúc được biết đến.
2. **Không đồng nhất cấp phát và bàn giao:** một pipeline hoàn tất chưa phải bằng chứng môi trường đã sẵn sàng hoặc có người tiếp nhận.
3. **Tự động hóa cùng với guardrail:** template IaC, policy-as-code, inventory, review và audit giúp cấp phát nhanh mà vẫn kiểm soát được.
4. **Thay đổi và thu hồi đều có thể gây sự cố:** phải xem xét dữ liệu, quan hệ phụ thuộc, quyền, nghĩa vụ lưu giữ và kế hoạch phục hồi.
5. **Kiểm chứng bằng trạng thái thực:** đối soát tài nguyên, kiểm tra truy cập, khôi phục, telemetry và báo cáo chi phí; không dựa duy nhất vào nhãn hoặc kết quả một lệnh.
6. **Tối ưu theo rủi ro:** preview có dữ liệu tổng hợp và TTL có thể tự cấp phát/thu hồi; production hoặc môi trường có dữ liệu nhạy cảm cần bước phê duyệt và bằng chứng chặt hơn.

Quy trình **yêu cầu → phê duyệt → cấp phát → kiểm tra → tiếp nhận → vận hành → thu hồi → đối soát** biến tổ chức tài nguyên thành một phần của kiến trúc cloud. Nó giúp từng tài nguyên có lý do tồn tại, người chịu trách nhiệm, mức bảo vệ phù hợp và một cách kết thúc vòng đời rõ ràng.
