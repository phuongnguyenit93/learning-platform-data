# Thiết kế landing zone với organization và folder trên Google Cloud

Khi một nhóm mới sử dụng Google Cloud, họ có thể tạo một **project**, bật API và triển khai ứng dụng. Cách bắt đầu này phù hợp với thực hành nhỏ, nhưng khi tổ chức vận hành hàng chục project cho Compute Engine, GKE, Cloud Run, Cloud Storage, Cloud SQL và BigQuery, những vấn đề quản trị xuất hiện: ai được tạo project, dữ liệu được phép lưu ở đâu, môi trường production tách khỏi thử nghiệm như thế nào, log tập trung về đâu và ai chịu trách nhiệm chi phí?

**Cloud landing zone** là nền tảng tổ chức, bảo mật, mạng, vận hành và quản trị được thiết kế trước để những workload mới có thể triển khai theo các quy tắc thống nhất. Trên Google Cloud, **organization** và **folder** là hai khối cấu trúc quan trọng giúp tạo ranh giới quản trị đó. Landing zone là một **mô hình kiến trúc cùng tập quy trình/cấu hình**, không phải một tài nguyên đơn lẻ có nút “Create landing zone”.

Bài học thuộc chương **Quản trị tổ chức** của mô-đun **CLOUD_PROVIDERS_GCP**. Người học sẽ thiết kế cấu trúc tài nguyên cho hệ thống có IAM, VPC, Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu; kết nối quyết định về cấu trúc với quyền truy cập, tự động hóa phát hành, độ tin cậy và chi phí.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

1. Phân biệt **organization**, **folder**, **project** và **service resource**; hiểu quan hệ cha–con.
2. Giải thích cách IAM allow policy và Organization Policy tác động theo cây tài nguyên.
3. Chọn cấu trúc folder phù hợp với tổ chức, môi trường production/nonproduction và nhóm nghiệp vụ.
4. Phân chia các project nền tảng như mạng, nhật ký, bảo mật và các project chạy workload.
5. Thiết kế quy trình cấp project mới, gắn billing, định danh owner, gắn nhãn và áp dụng kiểm soát ban đầu.
6. Đề xuất cách kiểm chứng landing zone bằng câu hỏi vận hành và ví dụ lệnh `gcloud`.

## 2. Cây tài nguyên Google Cloud

### 2.1. Bốn cấp khái niệm

| Thành phần | Vai trò | Ví dụ | Lưu ý |
| --- | --- | --- | --- |
| **Organization** | Nút gốc quản trị tài nguyên Google Cloud của tổ chức. | `organizations/123456789012` | Nơi đặt nhiều kiểm soát và quyền quản trị dùng chung; gắn với môi trường danh tính doanh nghiệp theo quy trình Google Cloud. |
| **Folder** | Nhóm con để tổ chức dự án và áp dụng chính sách theo phạm vi. | `folders/456789012345` | Có thể lồng nhau; folder thường dùng để chia môi trường, bộ phận hoặc mức độ kiểm soát. |
| **Project** | Đơn vị cơ bản để sử dụng API, quản lý tài nguyên, quota và liên kết thanh toán. | `retail-orders-prod-001` | Project ID cần được thiết kế cẩn thận; nhiều chính sách/quyền được áp dụng theo project. |
| **Service resource** | Tài nguyên cụ thể do dịch vụ tạo và quản lý. | VM, VPC network, GKE cluster, Cloud Run service, bucket, Cloud SQL instance. | Khả năng cấp IAM trực tiếp và cách tổ chức theo cấp nhỏ hơn phụ thuộc dịch vụ. |

Một project chỉ có **một parent trực tiếp** trong cây tài nguyên; parent có thể là organization hoặc folder. Một folder có một parent là organization hoặc folder khác, và folder nằm trong một organization. Organization có thể chứa project trực tiếp, nhưng trong landing zone doanh nghiệp thường dùng folder để làm rõ ranh giới quản trị.

~~~mermaid
flowchart TB
    O["Organization: example.com"] --> F1["Folder: platform"]
    O --> F2["Folder: workloads"]
    O --> F3["Folder: sandbox"]
    F1 --> P1["Project: shared-network-prod"]
    F1 --> P2["Project: central-logging"]
    F2 --> F21["Folder: production"]
    F2 --> F22["Folder: nonproduction"]
    F21 --> P3["Project: orders-prod"]
    F22 --> P4["Project: orders-dev"]
    P3 --> R1["Cloud Run / Cloud SQL"]
    P4 --> R2["Compute Engine / GKE"]
~~~

Folder trong sơ đồ là **vùng quản trị logic**; folder không tự tạo một VPC riêng, không thay thế subnet/firewall và không tự động cô lập mạng giữa các project. Tương tự, project là ranh giới quản lý quan trọng nhưng vẫn cần cấu hình IAM, networking, chính sách tổ chức và tài nguyên cụ thể để đạt yêu cầu bảo mật.

### 2.2. Organization được hình thành thế nào?

Trong môi trường doanh nghiệp, organization resource thường gắn với **Google Workspace hoặc Cloud Identity** và tên miền/thiết lập danh tính thích hợp. Nhóm khởi tạo cần phối hợp với quản trị viên danh tính để xác định tổ chức nào sở hữu resource, nhóm nào quản trị, cách cấp quyền ban đầu và phương án khôi phục quyền truy cập.

Đừng xem thao tác tạo project đầu tiên bằng tài khoản cá nhân là một thiết kế landing zone hoàn chỉnh. Một tổ chức có thể có nhiều project do các nhóm khác nhau tạo, nhưng thiếu organization và quy trình quản trị chung sẽ khiến quyền, billing và ownership khó kiểm soát khi quy mô tăng.

### 2.3. Folder và project khác nhau thế nào?

Giả sử cần tách hệ thống đơn hàng và phân tích dữ liệu:

- Folder `production` biểu diễn ranh giới quản trị của môi trường, nơi có thể áp dụng những kiểm soát chặt hơn.
- Project `orders-prod` chứa Cloud Run, Cloud SQL và tài nguyên phục vụ đơn hàng.
- Project `analytics-prod` chứa pipeline dữ liệu hoặc dịch vụ phân tích, có IAM, quota và giám sát riêng.
- Cả hai project có thể cùng nằm dưới folder `production`, nhưng có owner và ngân sách khác nhau.

**Không nên tạo project chỉ để mô phỏng folder** hoặc cho nhiều ứng dụng không liên quan dùng chung một project chỉ để “đỡ phải quản lý”. Thiết kế project cần tính đến vòng đời workload, quyền quản lý, quota, độ nhạy dữ liệu và khả năng phân bổ chi phí.

## 3. Những thành phần tạo nên một landing zone

Organization/folder là bộ khung. Landing zone triển khai được cần thêm các lớp vận hành:

| Lớp nền tảng | Quyết định tối thiểu | Công nghệ hoặc cơ chế thường dùng |
| --- | --- | --- |
| **Identity & access** | Ai quản trị organization, ai quản trị folder, ai tạo project, ai triển khai ứng dụng? | Cloud Identity/Workspace, IAM groups, service accounts, federation, IAM Conditions. |
| **Governance & policy** | Vùng nào được phép sử dụng, loại cấu hình nào bị hạn chế, có chính sách khác nhau giữa prod/dev không? | Organization Policy Service, tags khi phù hợp, quy trình ngoại lệ. |
| **Resource hierarchy** | Phân chia folder theo môi trường hay đơn vị? Project nào thuộc phạm vi nào? | Organization, folders, projects, project factory. |
| **Networking** | Workload kết nối nội bộ và ra ngoài thế nào? Ai quản lý DNS, firewall, egress? | VPC, Shared VPC khi thích hợp, subnet, Cloud DNS, Cloud NAT, firewall. |
| **Security & keys** | Ai truy cập dữ liệu, khóa mã hóa và secret? Phát hiện cấu hình sai thế nào? | IAM, Secret Manager, Cloud KMS, Security Command Center theo gói/khả năng sử dụng. |
| **Observability** | Log, metrics và cảnh báo quan trọng đi về đâu? Đội nào trực sự cố? | Cloud Logging, Cloud Monitoring, log sinks, alerting, runbook. |
| **Billing & cost** | Mỗi project tính chi phí cho ai, kiểm soát chi tiêu ra sao? | Cloud Billing account, budgets, labels, báo cáo chi phí và xuất dữ liệu billing khi cần. |
| **Provisioning & delivery** | Ai cấp project mới, thay đổi chính sách được kiểm soát thế nào? | Terraform hoặc công cụ IaC phù hợp, CI/CD, code review, chuẩn mẫu project. |
| **Reliability & recovery** | Hệ thống cần HA, backup, DR và SLO ở mức nào? | Kiến trúc nhiều zone/region khi cần, backup, chính sách phục hồi, kiểm thử. |

Không phải mọi doanh nghiệp đều phải triển khai tất cả công cụ trên ngay ngày đầu. Một landing zone tốt thể hiện **mức kiểm soát phù hợp với rủi ro và quy mô**, có phương án bổ sung khi tổ chức phát triển.

## 4. Chọn chiến lược folder

### 4.1. Phân chia theo môi trường

Trong mô hình này, các folder chính phản ánh mức độ quan trọng:

~~~text
organization
├── platform
│   ├── production
│   └── nonproduction
├── workloads
│   ├── production
│   └── nonproduction
└── sandbox
~~~

**Ưu điểm:** dễ áp dụng baseline bảo mật nghiêm ngặt cho production, nới quy tắc cho dev/test trong phạm vi cho phép, tách quyền vận hành và chi phí. **Hạn chế:** cùng một nhóm nghiệp vụ có project rải ở nhiều folder; cần naming, labels/tags và quản lý ownership để liên kết.

### 4.2. Phân chia theo đơn vị hoặc dòng sản phẩm

~~~text
organization
├── retail
│   ├── production
│   └── nonproduction
├── data-platform
│   ├── production
│   └── nonproduction
└── corporate
~~~

**Ưu điểm:** dễ giao quyền và trách nhiệm cho bộ phận, nhóm dự án. **Hạn chế:** chính sách production có thể cần duy trì ở nhiều nhánh; nếu quy trình quản trị không tốt, các nhánh tạo cấu hình lệch nhau.

### 4.3. Chọn cấu trúc theo những câu hỏi quyết định

| Câu hỏi | Gợi ý thiết kế |
| --- | --- |
| Chính sách production khác dev/test đáng kể không? | Cân nhắc folder môi trường để áp dụng chính sách nhất quán. |
| Đơn vị kinh doanh có đội vận hành và trách nhiệm độc lập? | Cân nhắc folder theo đơn vị, thêm tầng môi trường. |
| Ai có quyền tạo và di chuyển project? | Giao quyền ở cấp folder thích hợp, kiểm soát qua quy trình xét duyệt. |
| Project có cần dùng chung mạng, nhật ký hay dịch vụ bảo mật? | Tách project nền tảng và xác định mô hình chia sẻ có kiểm soát. |
| Workload có dữ liệu nhạy cảm hoặc yêu cầu vị trí đặc thù? | Cân nhắc nhánh riêng và policy phù hợp; xác minh khả năng áp dụng ở từng dịch vụ. |
| Tổ chức có bao nhiêu project và nhóm? | Tránh cấu trúc quá sâu gây khó hiểu, nhưng cũng tránh đặt mọi project trực tiếp dưới root. |

**Một folder chỉ có một parent**, nên không thể đồng thời phân nhóm project độc lập theo cả “team” và “environment” nếu hai chiều này cắt nhau. Chọn **một chiều làm cây chính**, dùng folder con khi có ích và sử dụng labels/tags hoặc danh mục ownership cho các chiều còn lại.

### 4.4. Nguyên tắc đặt tên

Tên hiển thị của folder nên có quy tắc, chẳng hạn:

- `platform`, `workloads`, `sandbox` cho các tầng trách nhiệm;
- `production`, `nonproduction` cho mức kiểm soát;
- `retail`, `finance`, `data` cho đơn vị nghiệp vụ khi cần;
- `security-logging`, `shared-network-prod` cho những project hạ tầng.

**Folder display name không phải ID**: tài nguyên folder có định danh số dùng trong API/CLI. Một tên hiển thị có thể trùng ở những vị trí khác nhau; khi scripting nên dùng folder ID thay vì suy từ tên.

Project ID cần được chọn theo quy tắc đặt tên riêng và có tính ổn định lâu dài; không đặt thông tin bí mật vào tên project, labels hay các trường metadata có thể được nhiều người đọc.

## 5. Chính sách kế thừa: IAM và Organization Policy

### 5.1. IAM: quyền ở tổ tiên có thể áp dụng xuống con

IAM **allow policy** định nghĩa binding giữa principal và role. Khi cấp role ở cấp organization hoặc folder, quyền được kế thừa tới những tài nguyên con phù hợp, phụ thuộc vào cách IAM được dịch vụ hỗ trợ và các điều kiện/phần hạn chế khác.

Ví dụ:

~~~text
organization
└── folder: workloads
    ├── folder: production
    │   └── project: orders-prod
    └── folder: nonproduction
        └── project: orders-dev

group:prod-observers@example.com
  -> roles/monitoring.viewer tại folder production

group:dev-team@example.com
  -> role phát triển phù hợp tại project orders-dev
~~~

Nhóm quan sát production có quyền xem dữ liệu monitoring trong phạm vi được role/binding cho phép ở các project con; nhóm phát triển được cấp quyền ở `orders-dev` không vì thế có quyền ở `orders-prod`.

Một project **không thể đơn giản “gỡ” một allow binding được cấp ở tổ tiên** bằng cách xóa binding cục bộ. Nếu không muốn quyền lan xuống, cần thiết kế phạm vi cấp ở tầng khác, dùng IAM Conditions khi thích hợp hoặc các cơ chế giới hạn quyền được Google Cloud hỗ trợ. IAM deny policies và principal access boundary policies (khi áp dụng) cần được đánh giá riêng với allow policy.

### 5.2. Organization Policy: đặt ràng buộc lên cấu hình

**Organization Policy Service** giúp đặt những ràng buộc (*constraints*) lên cách tài nguyên được cấu hình hoặc sử dụng. Một số constraint có dạng boolean; một số có tập giá trị được cho phép hoặc bị cấm. Policy có thể gắn tại organization, folder hoặc project theo khả năng áp dụng; mức hiệu lực được xác định từ quan hệ tổ tiên và quy tắc của constraint cụ thể.

Ví dụ các mục tiêu thường gặp:

| Mục tiêu quản trị | Ví dụ cách tiếp cận | Điều cần kiểm tra |
| --- | --- | --- |
| Giảm rủi ro key tĩnh của service account | Xem xét constraint hạn chế tạo service account key. | Tác động đến pipeline cũ và các ngoại lệ bắt buộc. |
| Giới hạn vị trí tài nguyên | Xem xét constraint giới hạn resource locations. | Dịch vụ và loại tài nguyên nào chịu tác động, khả năng triển khai multi-region. |
| Giảm rủi ro cấu hình mạng không mong muốn | Xem constraint liên quan đến VPC, địa chỉ IP hoặc thiết lập mạng của dịch vụ. | Tính tương thích và mức hỗ trợ theo dịch vụ, trường hợp kết nối hợp lệ. |
| Kiểm soát tài nguyên theo mức nhạy cảm | Dùng folder policy kết hợp IAM, quy trình và tags khi cơ chế hỗ trợ. | Không suy rằng gắn một tag tự tạo là đã thực thi mọi giới hạn. |

Ví dụ định danh constraint phổ biến để nghiên cứu: `constraints/iam.disableServiceAccountKeyCreation` và `constraints/gcp.resourceLocations`. **Không áp dụng hàng loạt bằng cách sao chép ví dụ**: mỗi constraint có phạm vi áp dụng, hành vi kế thừa, ngoại lệ và ảnh hưởng sản phẩm riêng. Đọc tài liệu hiện hành và thử trên nhánh nonproduction trước khi dùng với production.

Organization Policy khác IAM:

- **IAM** trả lời: principal này có quyền làm việc đó với tài nguyên không?
- **Organization Policy** trả lời: cấu hình hoặc hành vi tài nguyên này có đáp ứng những ràng buộc của tổ chức không?
- **VPC firewall**, quy tắc bảo mật ứng dụng và các cơ chế kiểm soát dữ liệu giải quyết những lớp khác. Một role IAM hợp lệ không tự làm vô hiệu ràng buộc organization policy.

### 5.3. Tags và labels: giống tên nhưng khác chức năng

| Công cụ | Dùng cho | Hạn chế cần nhớ |
| --- | --- | --- |
| **Folder** | Phân cấp sở hữu và phạm vi chính sách. | Mỗi tài nguyên trong cây có một đường tổ tiên; khó thể hiện mọi chiều phân loại. |
| **Resource Manager tags** | Phân loại có quản trị; có thể tham gia IAM Conditions hoặc Organization Policy ở những cơ chế được hỗ trợ. | Cần cấu hình tag key/value, binding, quyền và policy cụ thể; bản thân tag không tự cấp/cấm quyền. |
| **Labels** | Metadata phục vụ nhận diện, tìm kiếm, phân bổ/đối chiếu chi phí ở dịch vụ hỗ trợ. | Không phải hàng rào bảo mật hoặc IAM policy. |

Ví dụ một project nằm dưới folder `production` vẫn có thể gắn label như `team=orders`, `cost_center=retail` và tag được quản lý theo chính sách. Không dùng labels để thay thế quyền hoặc ràng buộc bảo mật.

## 6. Thiết kế các project nền tảng

Một landing zone lớn thường tách các **platform projects** khỏi **application projects** để quyền và vận hành rõ ràng:

| Project/nhóm project | Chức năng | Các kiểm soát nên tính đến |
| --- | --- | --- |
| **Network host** | Quản lý VPC/subnet và thành phần mạng dùng chung nếu chọn Shared VPC. | Quản trị mạng tập trung, firewall, route, DNS, egress, IAM trên subnet. |
| **Security / KMS** | Chứa một số thành phần bảo mật tập trung theo kiến trúc. | Quyền quản trị khóa, quy trình cấp/thu hồi quyền, audit. |
| **Logging / monitoring** | Nhận hoặc phân tích dữ liệu quan sát tập trung khi cần. | Log sinks, phạm vi dữ liệu, retention, quyền đọc và chi phí lưu trữ. |
| **Automation / CI/CD** | Công cụ cấp project và pipeline phát hành hạ tầng. | Danh tính triển khai, quyền tối thiểu, phê duyệt thay đổi, theo dõi drift. |
| **Workload application** | Chạy Cloud Run, Compute Engine, GKE, Cloud SQL và dịch vụ ứng dụng. | IAM theo owner, quota, budget, SLO, backup và phân vùng mạng. |
| **Sandbox** | Thử nghiệm thời hạn hoặc ngân sách giới hạn. | Quyền tạo tài nguyên có kiểm soát, expiration/cleanup, giới hạn rủi ro. |

Đây là **mô hình tham khảo**, không phải danh sách project bắt buộc. Nếu tổ chức nhỏ, một số thành phần nền tảng có thể chia sẻ project khi vẫn đáp ứng được yêu cầu về quản trị, dữ liệu và vòng đời. Ngược lại, hệ thống có yêu cầu bảo mật cao có thể cần tách hơn nữa.

### 6.1. Shared VPC và ranh giới mạng

**Shared VPC** cho phép một project được chỉ định làm **host project** cung cấp mạng cho những **service projects** được liên kết theo điều kiện hỗ trợ. Mục tiêu là quản lý mạng tập trung trong khi các nhóm vẫn sở hữu project ứng dụng riêng.

~~~mermaid
flowchart LR
    N["Host project: shared-network-prod"] --> V["VPC / subnets / firewall"]
    V -. "Shared VPC attachment" .-> A["Service project: orders-prod"]
    V -. "Shared VPC attachment" .-> B["Service project: catalog-prod"]
    A --> R["Cloud Run / Cloud SQL"]
    B --> G["GKE / Compute Engine"]
~~~

**Folder không tự liên kết VPC.** Nếu không dùng Shared VPC, mỗi project có thể có VPC riêng, nhưng cần thiết kế kết nối phù hợp khi các ứng dụng giao tiếp. Shared VPC cũng không có nghĩa mọi loại tài nguyên đều kết nối riêng tư theo một cách; Cloud Run, GKE, Cloud SQL và VM có cơ chế networking và quyền liên quan khác nhau.

### 6.2. Logging, monitoring và bảo mật tập trung

Tổ chức có thể tạo log sinks để định tuyến một số loại log từ phạm vi organization/folder/project tới đích được hỗ trợ. Khi lập kiến trúc, hãy ghi rõ:

1. Loại log nào cần thu thập và mục tiêu lưu giữ.
2. Đích nhận log, quyền của danh tính ghi log, quyền của nhóm điều tra.
3. Cách kiểm tra log bị thiếu hoặc quyền đọc không đúng.
4. Chi phí ingest, lưu trữ, truy vấn và khả năng xuất dữ liệu.

**Không giả định mọi log tự động được chuyển về một project trung tâm** chỉ vì tạo folder logging. Tương tự, Cloud Monitoring cần cấu hình phạm vi quan sát, alerting và SLO theo hệ thống thực tế; folder chỉ hỗ trợ tổ chức quyền và tài nguyên.

### 6.3. Billing và chi phí

Một Cloud Billing account có thể thanh toán cho nhiều project, còn mỗi project được liên kết với billing account theo mô hình thanh toán hiện hành. **Billing account không nằm trong cây folder như một project con.**

Ngay trong landing zone, hãy xác định:

- Owner chịu trách nhiệm chi phí cho từng project.
- Billing account dùng cho các project và cơ chế phê duyệt liên kết.
- Quy tắc gắn label/tag hoặc metadata cho cost center nếu dịch vụ hỗ trợ.
- Budget/alert, trách nhiệm xử lý cảnh báo và báo cáo theo thời gian.
- Cách phân tích chi phí mạng chung, log tập trung, GKE, Cloud SQL và tài nguyên dùng chung.

**Budget alert không tự động chặn chi tiêu**. Nếu cần hạn chế sử dụng, phải thiết kế thêm quota, policy, tự động hóa và quy trình vận hành phù hợp; không dựa riêng vào cảnh báo.

## 7. Ví dụ thiết kế landing zone cho doanh nghiệp bán lẻ

Giả sử doanh nghiệp có ba nhóm: **Platform**, **Retail Applications** và **Data Analytics**. Hệ thống đơn hàng chạy Cloud Run và Cloud SQL; nhóm sản phẩm có một số workload trên GKE; dữ liệu ảnh ở Cloud Storage; Compute Engine phục vụ một số công cụ nội bộ. Doanh nghiệp muốn phân biệt production, nonproduction, sandbox và quản lý chi phí theo đội.

### 7.1. Cấu trúc tham khảo

~~~text
Organization: example.com
│
├── Folder: platform
│   ├── Folder: production
│   │   ├── Project: shared-network-prod
│   │   ├── Project: security-services-prod
│   │   └── Project: centralized-logging
│   └── Folder: nonproduction
│       └── Project: shared-network-dev
│
├── Folder: workloads
│   ├── Folder: production
│   │   ├── Project: orders-prod
│   │   ├── Project: catalog-prod
│   │   └── Project: analytics-prod
│   └── Folder: nonproduction
│       ├── Project: orders-dev
│       ├── Project: catalog-test
│       └── Project: analytics-dev
│
└── Folder: sandbox
    ├── Project: retail-lab-01
    └── Project: data-experiment-01
~~~

Sơ đồ chỉ mô tả **tên logic**; khi tạo trên Google Cloud, mỗi folder có folder ID số và mỗi project cần project ID hợp lệ, duy nhất. Tên mẫu không phải tài nguyên đang tồn tại. Một tổ chức cũng có thể đặt folder theo nhóm sản phẩm bên dưới `production` nếu nhiều project và owner cùng cần một tầng phân quyền riêng.

### 7.2. Quy định khác nhau theo tầng

| Phạm vi | Quyền truy cập | Mạng và dữ liệu | Chi phí và vận hành |
| --- | --- | --- | --- |
| **Organization** | Nhóm quản trị tổ chức rất hạn chế; cơ chế quản trị khẩn cấp. | Baseline governance, chính sách dùng chung và quy trình ngoại lệ. | Quy tắc billing, ownership, giám sát tuân thủ. |
| **Platform production** | Platform team quản trị thành phần chung; nhóm ứng dụng chỉ nhận quyền sử dụng cần thiết. | Mạng production, bảo mật tập trung, hạ tầng logs. | Chi phí hạ tầng dùng chung, theo dõi tính sẵn sàng của dịch vụ nền tảng. |
| **Workloads production** | Nhóm ứng dụng có quyền vận hành chính xác; quyền thay đổi nhạy cảm cần kiểm soát. | Hạn chế cấu hình rủi ro; lựa chọn HA, backup, kết nối riêng theo yêu cầu. | SLO, cảnh báo, cost center và trách nhiệm sự cố. |
| **Nonproduction** | Dev/test đủ quyền thực hiện công việc trong phạm vi được cấp. | Dùng dữ liệu thử, tránh sao chép dữ liệu nhạy cảm không kiểm soát. | Budget phù hợp, vòng đời tài nguyên tạm. |
| **Sandbox** | Quyền thử nghiệm có thời hạn và phạm vi rõ. | Giới hạn loại workload, vị trí và phương thức truy cập theo rủi ro. | Budget/alert, ngày hết hạn và cơ chế dọn dẹp. |

Không nên áp dụng một policy quá chặt lên organization nếu nó phá vỡ một nhu cầu đã được phê duyệt trên mọi môi trường. Thay vào đó, xác định baseline chung, đánh giá rủi ro và đặt quy tắc chuyên biệt tại folder thích hợp, tuân theo khả năng kế thừa/ngoại lệ của từng constraint.

### 7.3. Luồng tạo project đơn hàng mới

Giả sử Retail Applications yêu cầu project production mới cho API thanh toán. Quy trình đề xuất:

1. Nhóm ứng dụng nộp yêu cầu gồm owner, mục đích, độ nhạy dữ liệu, region dự kiến, yêu cầu mạng, SLO, RTO/RPO và chi phí dự kiến.
2. Platform xác nhận folder đích: `workloads/production`, đồng thời kiểm tra nhu cầu tách project khỏi hệ thống đơn hàng hiện hữu.
3. Cấp project qua mẫu IaC được kiểm soát, chọn project ID duy nhất, liên kết billing và gắn metadata sở hữu.
4. Áp dụng IAM tối thiểu cho nhóm vận hành và danh tính CI/CD; cấu hình service accounts riêng cho runtime và triển khai.
5. Kết nối tới network host/service project nếu cần; cấu hình DNS, subnet, egress và firewall theo kiến trúc thực tế.
6. Bật những API cần dùng, thiết lập log, metrics, cảnh báo ngân sách, chính sách backup và bảo mật.
7. Chạy kiểm tra đọc: vị trí project trong cây, policy hiệu lực, quyền truy cập, network path, billing, log và cảnh báo.
8. Bàn giao project cùng runbook, owner, chi phí ước tính và lịch rà soát quyền/cấu hình.

Project chỉ nên được coi là “sẵn sàng cho workload” khi các bước cấp phát, kiểm tra và bàn giao đạt yêu cầu của tổ chức.

## 8. Khởi tạo và quan sát cấu trúc bằng gcloud

Các lệnh trong phần này minh họa cách kiểm tra và tạo cấu trúc trong Google Cloud CLI. **Lệnh `list`, `describe` và `get-iam-policy` là thao tác đọc. Lệnh `create` và thay đổi billing sẽ tác động lên tài nguyên thực**, chỉ thực thi khi đã được tổ chức cho phép và đi đúng quy trình quản trị.

### 8.1. Kiểm tra organization và folder hiện có

~~~bash
# Các organization mà tài khoản đang sử dụng có thể nhìn thấy.
gcloud organizations list

# Liệt kê folder trực thuộc organization (thay bằng organization ID thực).
gcloud resource-manager folders list \
  --organization=123456789012 \
  --format="table(name,displayName,parent)"

# Xem folder cụ thể (folder ID là số, không phải display name).
gcloud resource-manager folders describe 456789012345 \
  --format="yaml(name,displayName,parent)"

# Xem các project tài khoản có thể liệt kê.
gcloud projects list \
  --format="table(projectId,name,lifecycleState)"
~~~

Kết quả phụ thuộc IAM và ngữ cảnh CLI. Việc tài khoản không thấy một organization, folder hoặc project không chứng minh tài nguyên đó không tồn tại. Khi cần kiểm kê toàn tổ chức, sử dụng danh tính được cấp quyền đọc phù hợp hoặc các công cụ kiểm kê tài nguyên được tổ chức triển khai.

### 8.2. Kiểm tra allow policy ở từng tầng

~~~bash
# IAM allow policy gắn trực tiếp trên organization.
gcloud organizations get-iam-policy 123456789012 \
  --format="yaml(bindings)"

# IAM allow policy gắn trực tiếp trên folder.
gcloud resource-manager folders get-iam-policy 456789012345 \
  --format="yaml(bindings)"

# IAM allow policy gắn trực tiếp trên project.
gcloud projects get-iam-policy retail-orders-prod-001 \
  --format="yaml(bindings)"
~~~

Ba lệnh trên giúp khảo sát các binding tại **từng tài nguyên**, nhưng một kết quả chỉ gồm binding trực tiếp không đại diện cho toàn bộ **quyền hiệu lực**. Muốn giải thích vì sao một principal được phép hoặc bị từ chối, cần đối chiếu tổ tiên, conditions, deny policies, boundary policies khi có và các cơ chế kiểm soát bổ sung.

### 8.3. Ví dụ tạo folder và project có kiểm soát

Các lệnh dưới đây **chỉ để minh họa quy trình**, dùng cú pháp Bash. Chúng tạo tài nguyên và có thể dẫn đến chi phí sau khi project được liên kết billing và sử dụng dịch vụ:

~~~bash
# Giá trị minh họa: dùng ID thực được phê duyệt.
ORG_ID="123456789012"
PARENT_FOLDER_ID="456789012345"
PROJECT_ID="retail-orders-prod-001"

# Tạo folder cấp dưới organization; thực tế cần ghi nhận folder ID trả về.
gcloud resource-manager folders create \
  --organization="$ORG_ID" \
  --display-name="workloads"

# Tạo folder production dưới một folder cha đã xác nhận.
gcloud resource-manager folders create \
  --folder="$PARENT_FOLDER_ID" \
  --display-name="production"

# Sau khi có ID của folder production và quyền cấp project phù hợp:
PROD_FOLDER_ID="567890123456"
gcloud projects create "$PROJECT_ID" \
  --folder="$PROD_FOLDER_ID" \
  --name="Retail Orders Production"
~~~

Không chạy cả ví dụ trong organization đang hoạt động mà chưa kiểm tra folder có tồn tại hay không, tránh tạo cấu trúc trùng lặp. Sau khi cấp project, quy trình thật còn phải quản lý billing, IAM, API, networking, logs, labels và các kiểm soát khác; `gcloud projects create` **không tự tạo landing zone hoàn chỉnh**.

### 8.4. Xác minh sau cấp phát

Một checklist read-only có thể gồm:

~~~bash
# Kiểm tra thông tin project.
gcloud projects describe retail-orders-prod-001 \
  --format="yaml(projectId,name,parent,lifecycleState)"

# Kiểm tra binding IAM của project.
gcloud projects get-iam-policy retail-orders-prod-001 \
  --format="yaml(bindings)"

# Xem API đã bật (không đồng nghĩa toàn bộ tài nguyên đang sử dụng).
gcloud services list --enabled \
  --project=retail-orders-prod-001

# Xem các mạng VPC được tạo trong project đó.
gcloud compute networks list \
  --project=retail-orders-prod-001
~~~

Nếu project dùng Shared VPC, danh sách network tạo **trong chính service project** có thể không cho thấy các subnet được chia sẻ từ host project. Việc kiểm tra networking phải đối chiếu association, quyền và đường kết nối thực tế. Tương tự, kiểm tra org policy hiệu lực cần dùng công cụ/tài liệu Organization Policy phù hợp, không suy từ kết quả IAM allow policy.

## 9. Những quyết định khó và lỗi thiết kế thường gặp

### 9.1. “Một project cho mọi thứ” có ổn không?

Đôi khi hợp lý cho dự án nhỏ hoặc môi trường học tập. Với production nhiều nhóm, việc dồn mọi workload vào một project có thể gây khó quản lý quyền, quota, billing, vòng đời triển khai và sự cố. Phân tách project theo **nhóm tài nguyên có owner và vòng đời chung** thường rõ ràng hơn.

### 9.2. “Một project cho mỗi microservice” có luôn tốt hơn?

Không nhất thiết. Quá nhiều project làm tăng chi phí quản trị, cấu hình kết nối, cấp quyền, quota và tooling. Hãy tạo ranh giới project khi có yêu cầu thực sự về trách nhiệm, bảo mật, billing, vòng đời hoặc độc lập vận hành.

### 9.3. “Folder production đã bảo vệ ứng dụng” có đúng không?

Folder hỗ trợ kế thừa IAM/organization policies, nhưng không tự tạo HA, mã hóa ứng dụng, firewall hay backup. Một Cloud SQL không có kế hoạch restore vẫn có thể khiến hệ thống mất dữ liệu; một VM đơn lẻ vẫn có thể ngừng phục vụ dù nằm dưới `production`.

### 9.4. “Chuyển project sang folder khác chỉ đổi tên nhóm” có đúng không?

Không. **Di chuyển project giữa các folder có thể thay đổi policy hiệu lực** do khác cây tổ tiên: IAM cho người quản trị, constraints, tags được thừa kế và các yêu cầu kiểm soát khác có thể thay đổi. Cần đánh giá tác động trước/sau, lịch thực hiện, hệ thống tích hợp, người chịu trách nhiệm và kiểm tra truy cập sau di chuyển. Không di chuyển project production chỉ để làm sạch cây hiển thị.

### 9.5. “Labels có thể thay thế folder và policy” có đúng không?

Không. Labels hữu ích cho tìm kiếm, phân loại và báo cáo chi phí ở dịch vụ hỗ trợ. Chúng không tạo nhánh trong cây tài nguyên và không tự giới hạn quyền như IAM/Organization Policy. Tags có khả năng kết nối với một số cơ chế chính sách, nhưng cũng cần policy cụ thể mới phát sinh kiểm soát.

### 9.6. “Budget đạt ngưỡng thì Google tự dừng tài nguyên” có đúng không?

Không nên hiểu như vậy. Cloud Billing budgets chủ yếu để theo dõi và cảnh báo. Khi cần quy tắc hành động theo ngưỡng chi phí, cần thiết kế automation và xác nhận tác động, nhất là tránh làm gián đoạn workload quan trọng.

## 10. Kiểm thử landing zone trước khi đưa vào vận hành

### 10.1. Các ca kiểm tra quản trị

| Tình huống kiểm thử | Kết quả mong đợi |
| --- | --- |
| Dev chỉ có quyền ở `orders-dev` tìm cách thay đổi IAM của `orders-prod`. | Bị từ chối nếu không có binding hợp lệ khác. |
| Platform team đọc cấu hình network host project trong phạm vi được giao. | Được phép. |
| Một tài khoản sandbox thử tạo cấu hình bị organization policy ràng buộc. | Bị chặn khi constraint áp dụng cho yêu cầu đó. |
| Một project production mới được cấp từ template. | Xuất hiện dưới folder đúng, có owner, billing, IAM, logs, monitoring và policy phù hợp. |
| Thêm workload vào project không có budget owner. | Quy trình phát hiện thiếu thông tin và yêu cầu bổ sung. |
| Xem logs của sự kiện IAM thay đổi. | Đội được ủy quyền truy cập được dữ liệu audit cần thiết theo cấu hình ghi log và retention. |
| Một project chuẩn bị di chuyển sang folder khác. | Có bản đánh giá policy trước/sau và phương án kiểm chứng. |

Các ca “bị từ chối” nên kiểm tra qua môi trường thử nghiệm, phân tích policy hoặc thao tác không phá hủy. Không cần cố ý xóa dữ liệu production để kiểm chứng kiểm soát.

### 10.2. Chỉ số vận hành landing zone

Có thể đo chất lượng nền tảng bằng những chỉ số nội bộ:

- Tỷ lệ project có **owner và cost center** hợp lệ.
- Tỷ lệ project production được cấp qua **mẫu IaC chuẩn**.
- Số trường hợp **ngoại lệ policy** đang mở và ngày hết hạn.
- Tỷ lệ project có **billing và budget alert** được cấu hình.
- Tỷ lệ workload production có **logs, cảnh báo và runbook**.
- Thời gian cấp project mới từ yêu cầu hợp lệ đến khi bàn giao.
- Số phát hiện về quyền rộng bất thường hoặc cấu hình trái baseline.

Không nên biến các chỉ số thành mục tiêu hình thức. Một project có nhãn `owner=team-a` nhưng không ai thực sự nhận trách nhiệm vẫn là project thiếu quản trị.

### 10.3. Bài thực hành

**Tình huống:** Công ty có hai nhóm `retail` và `analytics`, mỗi nhóm cần `dev` và `prod`. Platform team sở hữu mạng dùng chung và hệ thống logs; nhóm ứng dụng tự triển khai Cloud Run, GKE, Compute Engine và Cloud SQL trong project riêng.

Hãy thiết kế một cây tài nguyên đáp ứng:

1. Production có chính sách nghiêm ngặt hơn nonproduction.
2. Platform team quản lý network host nhưng nhóm ứng dụng có quyền sử dụng subnet cần thiết.
3. Nhóm analytics không được mặc định thay đổi tài nguyên của nhóm retail.
4. Mỗi project có owner và thông tin phân bổ chi phí.
5. Log bảo mật cần được thu thập tập trung với quyền đọc hạn chế.

**Một phương án tham khảo:** tạo `platform/production`, `platform/nonproduction`, `workloads/production`, `workloads/nonproduction`; chia project ứng dụng theo nhóm nghiệp vụ; cấp IAM theo group/role và scope; dùng Shared VPC nếu được lựa chọn; cấu hình log sinks riêng; đặt baseline policy tại tổ tiên phù hợp; gắn metadata owner/cost center. Nếu cần quyền IAM riêng cho mỗi nhóm ở cấp folder, có thể thêm folder `retail` và `analytics` dưới từng môi trường thay vì cấp tất cả role ở cùng folder production.

Hãy giải thích **vì sao** chọn cấp folder đó cho IAM và policy, ai chịu trách nhiệm tạo project, cũng như cách kiểm chứng một project mới kế thừa đúng cấu hình.

## 11. Checklist áp dụng và tài liệu chính thức

Trước khi đưa landing zone vào hoạt động, xác nhận:

| Hạng mục | Tiêu chí đạt |
| --- | --- |
| **Organization** | Xác định tổ chức sở hữu, quản trị viên và phương án truy cập khẩn cấp. |
| **Folder tree** | Cấu trúc phản ánh ranh giới policy và trách nhiệm; có quy tắc tên/ID. |
| **Project lifecycle** | Có mẫu cấp, đặt owner, quy trình đổi folder, đóng project và cleanup. |
| **IAM** | Dùng group/service account phù hợp; role tối thiểu; đánh giá kế thừa quyền. |
| **Organization Policy** | Có baseline, chính sách production và quy trình ngoại lệ được kiểm chứng. |
| **Networking** | Quyết định project mạng, VPC/subnet, kết nối, firewall, DNS, egress và trách nhiệm vận hành. |
| **Security** | Có bảo vệ secrets/keys, audit, rà soát cấu hình và quyền đọc dữ liệu nhạy cảm. |
| **Observability** | Logs và metrics được cấu hình; cảnh báo, SLO, người trực và retention phù hợp. |
| **Billing** | Project liên kết đúng billing; có owner, báo cáo và budget alerts. |
| **Automation** | Tài nguyên nền tảng được quản lý bằng IaC/quy trình có review; kiểm soát drift. |
| **Validation** | Thử thành công/từ chối quyền, áp dụng policy, networking và kịch bản phục hồi. |

Tham khảo tài liệu chính thức để kiểm tra cú pháp, tính năng và khả năng áp dụng theo từng sản phẩm:

- [Google Cloud resource hierarchy](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [Creating and managing folders](https://cloud.google.com/resource-manager/docs/creating-managing-folders)
- [Google Cloud setup / enterprise foundation](https://cloud.google.com/docs/enterprise/foundations)
- [Organization Policy Service](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
- [IAM overview](https://cloud.google.com/iam/docs/overview)
- [Shared VPC overview](https://cloud.google.com/vpc/docs/shared-vpc)
- [Cloud Billing documentation](https://cloud.google.com/billing/docs)
- [Cloud Logging routing and storage](https://cloud.google.com/logging/docs/routing/overview)
- [Google Cloud CLI reference](https://cloud.google.com/sdk/gcloud/reference)

Điểm cần ghi nhớ: **organization** xác định phạm vi quản trị cấp cao, **folder** nhóm tài nguyên theo ranh giới trách nhiệm và chính sách, còn **project** là đơn vị triển khai/quản lý nhiều dịch vụ Google Cloud. Landing zone chỉ phát huy tác dụng khi cây tài nguyên được kết hợp với IAM, Organization Policy, mạng, bảo mật, billing, quan sát hệ thống và quy trình cấp phát có thể kiểm tra lại.
