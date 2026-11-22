# Thiết kế ranh giới tin cậy giữa các project và môi trường

Trong Google Cloud, project là đơn vị quan trọng để tổ chức tài nguyên, phân quyền, bật API, quản lý quota và theo dõi chi phí. Cách chia project cũng quyết định phạm vi ảnh hưởng khi một tài khoản, workload hoặc cấu hình bị xâm nhập. Vì vậy, thiết kế ranh giới tin cậy cần bắt đầu từ câu hỏi: **những người, ứng dụng và dữ liệu nào được phép tin cậy lẫn nhau, và hậu quả sẽ lan đến đâu nếu một thành phần bị chiếm quyền?**

Bài học thuộc module **CLOUD_PROVIDERS_GCP**, bao quát từ tổ chức project, IAM và VPC đến Compute Engine, GKE, Cloud Run, lưu trữ và cơ sở dữ liệu. Các nguyên tắc trong bài áp dụng cho cả môi trường chạy ứng dụng lẫn nền tảng CI/CD, quản lý bí mật, mã hóa và giám sát.

Sau bài học, bạn có thể:

- Chọn ranh giới project theo môi trường, mức độ nhạy cảm dữ liệu và phạm vi quản trị.
- Thiết kế cấu trúc organization, folder và project để kế thừa chính sách có chủ đích.
- Tách quyền con người, quyền workload và quyền triển khai giữa dev, test và production.
- Kết hợp project, Shared VPC, firewall policy, Organization Policy và VPC Service Controls.
- Xây dựng quy trình triển khai, kiểm tra quyền truy cập và giám sát các ranh giới tin cậy.

## 1. Ranh giới tin cậy trong Google Cloud

Ranh giới tin cậy là điểm mà tại đó bạn xác định danh tính nào được phép truy cập tài nguyên nào, qua đường kết nối nào, với điều kiện và mức kiểm soát nào. Một thiết kế tốt giới hạn quyền mặc định, yêu cầu cấp quyền tường minh khi đi qua ranh giới và ghi nhận được hoạt động quan trọng.

Project là một ranh giới quản trị hữu ích vì IAM policy, API được bật, quota, billing và nhiều cấu hình tài nguyên được quản lý theo project. Tuy nhiên, **project không tự động là một ranh giới bảo mật hoàn chỉnh**:

- IAM policy ở organization hoặc folder có thể được kế thừa xuống project và cấp quyền trên nhiều project cùng lúc.
- Shared VPC cho phép service project sử dụng mạng nằm trong host project.
- IAM grant, service account impersonation, API endpoint hoặc kết nối mạng có thể tạo đường truy cập giữa các project.
- Dịch vụ quản lý có phạm vi và mô hình truy cập riêng; không phải mọi tài nguyên đều được bảo vệ bởi cùng một cơ chế.

Vì vậy, không nên chỉ nhìn vào tên project để kết luận hai workload đã được cách ly. Cần đánh giá đồng thời bốn mặt: **danh tính, tài nguyên, mạng và dữ liệu**.

| Mặt kiểm soát | Câu hỏi thiết kế |
|---|---|
| Danh tính | Ai có thể đăng nhập, triển khai, impersonate service account hoặc đọc dữ liệu? |
| Tài nguyên | Project nào sở hữu workload, secret, khóa mã hóa, dữ liệu và log? Chính sách nào được kế thừa? |
| Mạng | Workload có thể kết nối đến subnet, địa chỉ IP, API hoặc dịch vụ nào? |
| Dữ liệu | Ai có thể đọc, xuất, sao chép, giải mã hoặc thay đổi dữ liệu giữa các môi trường? |

## 2. Chọn ranh giới project theo môi trường và mức độ tin cậy

Không có một số lượng project cố định phù hợp với mọi tổ chức. Hãy tạo project riêng khi hai nhóm tài nguyên cần khác nhau về quyền quản trị, mức độ nhạy cảm, chính sách, quota, vòng đời hoặc phạm vi ảnh hưởng khi có sự cố.

### Tách production khỏi non-production

Mỗi môi trường nên có project riêng. Ví dụ, ứng dụng đặt hàng có thể được tổ chức như sau:

~~~mermaid
flowchart TB
    O["Google Cloud Organization"]
    O --> P["Folder: production"]
    O --> N["Folder: non-production"]
    O --> S["Folder: platform-and-security"]
    O --> B["Folder: sandbox"]
    P --> PP["Project: orders-prod"]
    P --> PN["Project: orders-data-prod"]
    P --> PH["Project: net-prod"]
    N --> ND["Project: orders-dev"]
    N --> NT["Project: orders-test"]
    N --> NH["Project: net-nonprod"]
    S --> L["Project: central-logging"]
    S --> K["Project: security-tools"]
    B --> BS["Các project thử nghiệm riêng"]
~~~

Trong mô hình này:

- **orders-prod** chạy workload production; **orders-data-prod** giữ dữ liệu có mức độ nhạy cảm cao và có thể do nhóm dữ liệu quản lý riêng.
- **orders-dev** và **orders-test** chứa workload không production. Chúng không được mặc nhiên đọc secret, dữ liệu hoặc khóa của production.
- **net-prod** và **net-nonprod** là các Shared VPC host project riêng, giúp nhóm mạng quản lý kết nối tập trung mà vẫn duy trì ranh giới giữa hai môi trường.
- **central-logging** nhận log tập trung; **security-tools** chứa công cụ kiểm kê và giám sát bảo mật.
- Sandbox được quản lý bằng chính sách riêng, quota và ngân sách để thử nghiệm không ảnh hưởng môi trường quan trọng.

Tách project giúp áp dụng IAM, Organization Policy, quota và billing theo từng môi trường. Tách folder giúp kế thừa chính sách chung cho cả nhóm project. Nếu production và non-production có yêu cầu kiểm soát khác nhau, hãy đặt chúng ở các folder khác nhau để có thể áp dụng chính sách riêng.

### Khi nào cần project riêng cho dữ liệu?

Tạo project dữ liệu riêng khi nhóm dữ liệu cần quyền quản trị độc lập, dữ liệu có phân loại cao hơn workload, cần chính sách lưu trữ hoặc khóa mã hóa khác, hoặc nhiều ứng dụng dùng chung một miền dữ liệu được quản trị tập trung. Việc tách project tạo thêm ranh giới IAM và quản trị, nhưng cũng tăng công việc cấu hình kết nối, logging và vận hành.

Nếu dữ liệu và ứng dụng có cùng chủ sở hữu, cùng mức phân loại và cùng vòng đời, một project cho mỗi ứng dụng và môi trường có thể đã đủ. Hãy chọn ranh giới theo khác biệt về quyền và rủi ro thực tế, tránh chia nhỏ chỉ vì muốn có nhiều project.

### Quy tắc thiết kế cơ bản

1. Production không dùng chung project với dev, test hoặc sandbox.
2. Tách project khi chủ sở hữu, mức độ tin cậy hoặc yêu cầu tuân thủ khác nhau.
3. Không cấp quyền ở organization hoặc folder rộng hơn nhu cầu của nhóm.
4. Dùng project mạng riêng cho từng trust domain nếu áp dụng Shared VPC.
5. Giữ log và công cụ bảo mật ở project trung tâm với quyền quản trị hạn chế.
6. Mọi đường truy cập xuyên project phải có chủ sở hữu, lý do và cách giám sát.

## 3. Thiết kế ranh giới danh tính bằng IAM

IAM kiểm soát principal nào được thực hiện hành động nào trên tài nguyên. Trong môi trường nhiều project, quyền kế thừa và quyền cấp trực tiếp cần được xem xét cùng nhau.

### Quyền của con người

Quản lý quyền thông qua Google Groups hoặc nhóm danh tính doanh nghiệp thay vì gán quyền trực tiếp cho từng người. Có thể tách nhóm theo vai trò và môi trường:

| Nhóm | Quyền điển hình | Phạm vi |
|---|---|---|
| **gcp-platform-admins** | Quản trị nền tảng và cấu trúc dùng chung | Folder platform hoặc project nền tảng |
| **orders-devs** | Phát triển, xem log và triển khai dev | Project orders-dev |
| **orders-testers** | Kiểm thử, đọc log và chạy test | Project orders-test |
| **prod-operators** | Vận hành production theo nhiệm vụ | Các project production cần thiết |
| **security-auditors** | Đọc cấu hình và audit log | Phạm vi kiểm toán được giao |

Không cấp **Owner** hoặc **Editor** rộng cho nhóm phát triển chỉ để họ có thể triển khai ứng dụng. Hãy dùng vai trò định sẵn hẹp hơn hoặc custom role theo thao tác cần thiết. Quyền đọc log không đồng nghĩa với quyền thay đổi workload; quyền triển khai cũng không nên tự động bao gồm quyền sửa IAM hoặc đọc mọi secret.

Quyền ở organization và folder có phạm vi ảnh hưởng lớn. Chỉ nhóm quản trị nền tảng có trách nhiệm rõ ràng mới nên nhận quyền quản trị ở cấp cao. Khi một nhóm chỉ vận hành **orders-prod**, cấp quyền tại project đó thay vì folder production nếu không cần quản lý các project khác.

### Quyền của workload và pipeline

Mỗi ứng dụng nên có service account riêng cho từng môi trường, ví dụ:

- **orders-api-dev** chỉ truy cập tài nguyên dev.
- **orders-api-test** chỉ truy cập tài nguyên test.
- **orders-api-prod** chỉ truy cập tài nguyên production cần thiết.

Gắn service account phù hợp với workload trên Compute Engine, GKE hoặc Cloud Run. Cấp quyền đọc secret, ghi bucket hoặc truy cập cơ sở dữ liệu trực tiếp trên tài nguyên đích với phạm vi tối thiểu. Không dùng một service account có quyền trên cả ba môi trường cho tiện cấu hình.

Pipeline triển khai nên dùng danh tính riêng cho từng môi trường. CI có thể tạo artifact, chạy kiểm thử và yêu cầu quyền triển khai; bước phát hành production cần danh tính production riêng cùng cơ chế phê duyệt phù hợp. Nếu CI chạy ngoài Google Cloud, ưu tiên Workload Identity Federation để trao đổi danh tính ngắn hạn thay vì lưu service account key lâu dài.

Tránh tải và phân phối file service account key. Key dài hạn dễ bị sao chép khỏi máy build, log hoặc kho mã nguồn. Khi cần cấp quyền cho pipeline impersonate service account, chỉ cấp quyền trên đúng service account đích và giới hạn principal được phép impersonate.

### Quyền xuyên project phải tường minh

Ví dụ, ứng dụng trong **orders-prod** cần đọc một bucket trong **orders-data-prod**. Hãy cấp quyền đọc cho service account production trên đúng bucket hoặc tài nguyên cần dùng. Không thêm service account đó vào nhóm quản trị project dữ liệu nếu ứng dụng chỉ cần đọc một tập dữ liệu.

Khi điều tra quyền truy cập, kiểm tra cả:

- IAM policy trực tiếp của tài nguyên.
- IAM policy ở project, folder và organization được kế thừa.
- Quyền impersonation service account.
- Quyền truy cập được cấp qua group hoặc principal set.
- IAM Conditions và điều kiện truy cập theo ngữ cảnh nếu tổ chức sử dụng.

## 4. Thiết kế ranh giới mạng

VPC network thuộc một project và có phạm vi toàn cầu; subnet có phạm vi khu vực. Firewall rule, route, Cloud NAT và các kết nối mạng được cấu hình ở những phạm vi khác nhau. Vì vậy, hai project riêng vẫn có thể liên lạc nếu tổ chức chủ động kết nối chúng.

### Dùng mạng riêng cho từng trust domain

Với hệ thống có production và non-production, hãy cân nhắc hai Shared VPC host project riêng:

- **net-prod** chứa VPC production, subnet ứng dụng và subnet dữ liệu production.
- **net-nonprod** chứa VPC dev/test, subnet thử nghiệm và các đường ra Internet được kiểm soát.

Nhóm mạng quản lý host project và subnet; nhóm ứng dụng triển khai tài nguyên trong service project được liên kết. Shared VPC giảm trùng lặp vận hành mạng nhưng tạo một mối quan hệ tin cậy giữa host project và các service project. Không gộp workload có mức độ tin cậy khác nhau vào cùng mạng dùng chung nếu chính sách cách ly yêu cầu ranh giới độc lập.

Ví dụ bật Shared VPC và liên kết service project:

~~~bash
# Bật Shared VPC trên host project production
gcloud compute shared-vpc enable net-prod

# Liên kết project ứng dụng production với host project
gcloud compute shared-vpc associated-projects add orders-prod --host-project=net-prod
~~~

Thay các project ID bằng ID thực tế. Người thực hiện cần quyền quản trị Shared VPC phù hợp trên host project và quyền liên kết project. Sau khi liên kết, hãy chỉ chia sẻ các subnet cần thiết và cấp quyền sử dụng subnet theo đúng nhóm vận hành.

### Kiểm soát luồng mạng

- Dùng custom VPC và subnet theo khu vực, tier hoặc trust domain.
- Xác định nguồn và đích được phép; chỉ mở firewall rule cho giao thức, cổng và dải nguồn cần thiết.
- Dùng hierarchical firewall policies khi cần áp dụng quy tắc bắt buộc ở organization hoặc folder.
- Hạn chế IP công khai cho workload nội bộ; cân nhắc Private Google Access, Cloud NAT và Private Service Connect theo kiểu truy cập dịch vụ.
- Ghi nhận các kết nối xuyên VPC, VPN, Interconnect hoặc peering; đánh giá đường đi và quyền truy cập sau mỗi thay đổi.

Firewall chỉ kiểm soát lưu lượng mạng phù hợp với phạm vi của nó. Firewall không thay thế IAM: một ứng dụng có thể gọi API qua đường mạng hợp lệ nhưng vẫn phải bị từ chối nếu principal không có quyền trên tài nguyên.

## 5. Bảo vệ dữ liệu và bí mật theo môi trường

Ranh giới project cần được phản ánh trong cách lưu trữ và mã hóa dữ liệu. Nếu workload production chạy trong project riêng nhưng dùng chung bucket, secret hoặc khóa với dev, ranh giới tin cậy vẫn có thể bị phá vỡ ở lớp dữ liệu.

### Lưu trữ và cơ sở dữ liệu

- Dùng bucket, dataset và database riêng theo môi trường hoặc miền dữ liệu.
- Chỉ cấp quyền cho service account của môi trường tương ứng; tránh cấp quyền đọc production cho toàn bộ nhóm developer.
- Bật cơ chế ngăn truy cập công khai cho Cloud Storage khi phù hợp và dùng uniform bucket-level access để quản lý quyền tập trung bằng IAM.
- Áp dụng chính sách lưu trữ, retention, backup và vị trí dữ liệu theo phân loại và yêu cầu tuân thủ.
- Không sao chép dữ liệu production sang dev/test nguyên trạng nếu dữ liệu có thông tin nhạy cảm. Hãy masking, tokenization hoặc tạo dữ liệu tổng hợp trước khi chia sẻ.

### Secret Manager và Cloud KMS

Tạo secret riêng cho từng môi trường. Ví dụ **orders-db-password-prod** chỉ tồn tại và được cấp quyền trong phạm vi production; secret dev có giá trị và quyền truy cập riêng. Không đưa secret production vào biến môi trường hoặc file cấu hình được commit vào repository.

Với CMEK, cân nhắc CryptoKey riêng cho production và non-production, phân quyền quản trị khóa tách khỏi quyền sử dụng khóa, đồng thời kiểm soát ai có thể giải mã dữ liệu. Tách khóa theo môi trường giúp thu hồi hoặc thay đổi chính sách một môi trường mà không tác động trực tiếp đến môi trường còn lại.

## 6. Dùng Organization Policy để đặt rào chắn

Organization Policy cho phép tổ chức đặt giới hạn cấu hình trên resource hierarchy. Chính sách có thể được đặt ở organization, folder hoặc project; các node con kế thừa chính sách từ node cha, trừ khi cấu hình kế thừa hoặc ngoại lệ cho phép khác.

Một số rào chắn thường được cân nhắc:

| Mục tiêu | Ví dụ constraint | Lý do |
|---|---|---|
| Hạn chế service account key dài hạn | **constraints/iam.disableServiceAccountKeyCreation** | Giảm nguy cơ lộ key tĩnh |
| Bỏ qua việc tạo default network | **constraints/compute.skipDefaultNetworkCreation** | Tránh mạng mặc định có cấu hình không phù hợp |
| Giới hạn vị trí tài nguyên | **constraints/gcp.resourceLocations** | Hỗ trợ yêu cầu nơi lưu trữ dữ liệu |
| Kiểm soát thành viên IAM ngoài miền được phép | **constraints/iam.allowedPolicyMemberDomains** | Giảm cấp quyền nhầm cho danh tính bên ngoài |

Đây là các ví dụ cần đánh giá với dịch vụ và mô hình danh tính của tổ chức trước khi áp dụng. Một số constraint có phạm vi hỗ trợ hoặc cách quản lý khác nhau; hãy kiểm tra tài liệu constraint hiện hành và thử nghiệm trên folder/project đại diện.

Nên quản lý project bằng quy trình tạo project có kiểm soát hoặc project factory. Quy trình này có thể tự động gắn folder, billing account, nhóm quản trị, log sink, budget, API cần thiết và Organization Policy. Người tạo project không nên tự ý chọn folder có ít ràng buộc hơn để né chính sách production.

Không đặt ngoại lệ quá rộng ở organization chỉ để một workload đặc biệt hoạt động. Nếu một hệ thống thực sự cần ngoại lệ, đặt nó trong folder có chủ sở hữu, lý do, thời hạn xem xét và kiểm soát bù trừ rõ ràng.

## 7. Dùng VPC Service Controls cho dịch vụ dữ liệu được hỗ trợ

VPC Service Controls (VPC SC) tạo service perimeter quanh project và dịch vụ Google Cloud được hỗ trợ để giảm nguy cơ dữ liệu bị đưa ra ngoài miền tin cậy qua API. Có thể kết hợp perimeter với access level và ingress/egress policy để xác định nguồn truy cập được phép.

Ví dụ, project production chứa dữ liệu nhạy cảm có thể thuộc perimeter riêng. Một principal từ project dev không mặc nhiên được gọi API đọc dữ liệu trong perimeter đó, kể cả khi một cấu hình IAM vô tình cấp quyền rộng; request vẫn phải đáp ứng các quy tắc của perimeter.

VPC SC cần được thiết kế cẩn thận:

- Chỉ bảo vệ các dịch vụ và thao tác được VPC SC hỗ trợ; không phải mọi Google Cloud API đều nằm trong perimeter.
- Không thay thế IAM, firewall hoặc kiểm soát danh tính.
- Kết nối giữa các project, công cụ CI/CD, tài khoản hỗ trợ và quy trình export/import dữ liệu có thể cần ingress hoặc egress rule rõ ràng.
- Hãy chạy dry-run để quan sát request có thể bị chặn, phân tích log và điều chỉnh trước khi bật enforcement.
- Kiểm tra cả luồng quản trị và vận hành; một perimeter quá chặt có thể làm hỏng backup, triển khai hoặc truy cập hỗ trợ hợp lệ.

VPC SC phù hợp với các miền dữ liệu cần giảm nguy cơ exfiltration qua dịch vụ được hỗ trợ. Nó là một lớp kiểm soát bổ sung trong kiến trúc nhiều lớp, không phải một cách tạo mạng riêng cho mọi workload.

## 8. Tách pipeline và quy trình phát hành

Ranh giới production phải được giữ nguyên trong cả quá trình build và deploy. Một mô hình phù hợp là build artifact một lần, lưu artifact trong registry được quản lý, sau đó promote cùng artifact qua test và production. Dùng digest bất biến để bảo đảm production chạy đúng artifact đã kiểm thử.

Ví dụ luồng phát hành:

~~~mermaid
flowchart LR
    C["Source repository"] --> B["Build project"]
    B --> A["Artifact Registry"]
    A --> D["Deploy dev identity"]
    D --> T["Test project"]
    T --> G["Approval gate"]
    G --> P["Deploy production identity"]
    P --> R["Production project"]
    D -. "Không có quyền truy cập" .-> R
~~~

Các điểm kiểm soát:

1. Tách quyền build khỏi quyền deploy; pipeline build không cần quyền quản trị production.
2. Dùng service account deploy riêng cho từng môi trường.
3. Yêu cầu phê duyệt hoặc điều kiện phát hành cho production.
4. Chỉ cho pipeline production truy cập secret và tài nguyên production cần thiết.
5. Lưu log build, người phê duyệt, artifact digest, danh tính triển khai và kết quả rollout.
6. Thu hồi quyền hoặc credential của pipeline khi repository, runner hoặc workload identity không còn được tin cậy.

## 9. Giám sát và kiểm tra ranh giới tin cậy

Một ranh giới chỉ có giá trị khi tổ chức có thể phát hiện việc vượt ranh giới hoặc thay đổi ngoài dự kiến.

- Bật và tập trung Cloud Audit Logs phù hợp với yêu cầu; đặc biệt chú ý thay đổi IAM, Organization Policy, cấu hình mạng, KMS và truy cập dữ liệu.
- Dùng log sink tập trung gửi log về project bảo mật hoặc logging do nhóm độc lập quản lý.
- Giới hạn quyền xóa, sửa retention hoặc thay đổi sink đối với log kiểm toán.
- Dùng Security Command Center và công cụ kiểm kê để phát hiện tài nguyên công khai, cấu hình sai hoặc quyền quá rộng.
- Đặt cảnh báo cho thay đổi IAM cấp cao, thêm project vào perimeter, thay đổi firewall policy và cấp quyền impersonation service account.
- Định kỳ rà soát quyền kế thừa, service account không còn dùng, kết nối xuyên project và ngoại lệ Organization Policy.

### Kiểm tra bằng tình huống tiêu cực

Đừng chỉ kiểm tra rằng người dùng hợp lệ truy cập được. Hãy thử xác nhận các hành vi phải bị từ chối:

| Tình huống kiểm tra | Kết quả mong đợi |
|---|---|
| Developer dev đọc secret production | Bị từ chối |
| Service account dev impersonate service account production | Bị từ chối |
| Workload non-production kết nối subnet dữ liệu production | Bị chặn nếu không có luồng được phê duyệt |
| Project ngoài perimeter gọi API dữ liệu nhạy cảm trong perimeter | Bị VPC SC từ chối nếu request không thỏa ingress/access policy |
| Người triển khai ứng dụng tự cấp quyền Owner cho mình | Bị từ chối |
| Thay đổi IAM hoặc firewall production | Được ghi audit log và phát cảnh báo theo chính sách |

Thực hiện kiểm tra bằng tài khoản thử nghiệm và workload đại diện. Lưu lại principal, project, tài nguyên, thời điểm, policy áp dụng và kết quả. Khi một truy cập bị từ chối, xác minh rằng đó là policy dự kiến chứ không phải cấu hình sai gây gián đoạn.

## 10. Ví dụ thao tác kiểm tra IAM và Shared VPC

Lấy IAM policy của project để xem các binding trực tiếp:

~~~bash
gcloud projects get-iam-policy orders-prod
~~~

Gán quyền đọc log cho nhóm vận hành trên đúng project production:

~~~bash
gcloud projects add-iam-policy-binding orders-prod --member="group:prod-operators@example.com" --role="roles/logging.viewer"
~~~

Ví dụ này chỉ cấp quyền xem log; nó không cấp quyền triển khai hoặc thay đổi workload. Thay project ID, email group và role theo cấu hình thật. Trước khi thêm binding, hãy kiểm tra quyền được kế thừa từ folder và organization để tránh vô tình mở rộng phạm vi.

Để kiểm tra cấu hình Shared VPC:

~~~bash
# Xem host project đang dùng Shared VPC
gcloud compute shared-vpc get-host-project orders-prod

# Liệt kê service project đã liên kết với host project
gcloud compute shared-vpc list-associated-resources net-prod
~~~

Các lệnh chỉ là bước kiểm tra cấu hình. Cần đối chiếu thêm subnet được chia sẻ, IAM permission sử dụng subnet, firewall policy và luồng kết nối thực tế.

## 11. Các lỗi thiết kế thường gặp

- **Chỉ tách folder nhưng dùng chung project**: IAM, quota và nhiều cấu hình vẫn nằm ở project. Hãy tách project khi cần ranh giới quản trị thực sự.
- **Đưa dev và production vào cùng Shared VPC**: hai môi trường có thể dùng chung hạ tầng mạng và chịu ảnh hưởng từ thay đổi của nhau. Dùng host project riêng nếu cần cách ly.
- **Cấp quyền ở organization để giải quyết một lỗi cục bộ**: quyền có thể lan xuống nhiều project. Cấp quyền ở phạm vi nhỏ nhất phù hợp.
- **Dùng chung service account giữa các môi trường**: một credential bị lộ có thể mở đường vào production. Tạo danh tính riêng và cấp quyền riêng.
- **Cho rằng VPC SC thay thế IAM**: perimeter không thay thế phân quyền tài nguyên và không bao phủ mọi dịch vụ.
- **Cho rằng project riêng đồng nghĩa dữ liệu riêng**: bucket, secret, khóa hoặc database dùng chung vẫn tạo phụ thuộc xuyên project.
- **Cho phép dev đọc dữ liệu production để tiện debug**: dùng dữ liệu đã masking hoặc dữ liệu tổng hợp.
- **Bật policy hoặc perimeter trực tiếp ở chế độ enforcement mà chưa thử nghiệm**: có thể chặn backup, triển khai và luồng vận hành hợp lệ. Dùng môi trường thử nghiệm và dry-run khi có hỗ trợ.
- **Không tập trung audit log**: người có quyền cao trong một project có thể tác động đến log cục bộ. Gửi log đến project trung tâm với quyền độc lập.

## 12. Checklist thiết kế

Trước khi đưa một hệ thống lên production, hãy xác nhận:

- [ ] Có project riêng cho production, dev, test và sandbox theo nhu cầu cách ly.
- [ ] Folder phản ánh miền quản trị và chính sách; quyền kế thừa đã được rà soát.
- [ ] Project dữ liệu, secret, khóa mã hóa và log có chủ sở hữu rõ ràng.
- [ ] Nhóm người dùng và service account được tách theo vai trò và môi trường.
- [ ] Không dùng service account key dài hạn nếu có thể dùng danh tính ngắn hạn hoặc federation.
- [ ] Quyền xuyên project được cấp rõ ràng, đúng tài nguyên và có log.
- [ ] Shared VPC, firewall và kết nối mạng phản ánh đúng trust domain.
- [ ] Organization Policy được thử nghiệm và có quy trình quản lý ngoại lệ.
- [ ] VPC SC được áp dụng cho dịch vụ phù hợp, đã đánh giá dry-run và luồng ingress/egress.
- [ ] Pipeline build/deploy tách danh tính; production có bước kiểm soát phát hành.
- [ ] Audit log được tập trung, hạn chế quyền sửa và có cảnh báo thay đổi nhạy cảm.
- [ ] Đã thử các tình huống truy cập phải bị từ chối.

## 13. Tự kiểm tra

1. Vì sao project riêng cho production và dev vẫn chưa đủ để bảo đảm cách ly nếu cả hai project dùng chung Shared VPC?
2. Khi nào nên đặt quyền IAM ở folder và khi nào nên đặt trực tiếp ở project?
3. Vì sao service account dùng cho workload production nên tách khỏi service account dev?
4. VPC Service Controls bổ sung lớp bảo vệ nào và vì sao vẫn cần IAM?
5. Một pipeline build cần phát hành cùng artifact qua test và production. Làm thế nào để pipeline không cần quyền quản trị production?

**Gợi ý đáp án**

1. Shared VPC tạo kết nối mạng và quan hệ quản trị giữa host project với service project; firewall, subnet và quyền dùng subnet có thể làm hai môi trường ảnh hưởng lẫn nhau.
2. Đặt ở folder khi quyền áp dụng đồng nhất cho các project con; đặt ở project khi chỉ một project cần quyền đó.
3. Tách service account giới hạn phạm vi ảnh hưởng khi credential bị lộ và ngăn workload dev mặc nhiên có quyền production.
4. VPC SC giảm nguy cơ đưa dữ liệu ra ngoài perimeter qua các dịch vụ Google Cloud được hỗ trợ; IAM vẫn quyết định principal có quyền thực hiện thao tác trên tài nguyên hay không.
5. Build artifact một lần, lưu artifact bất biến, sau đó dùng deploy identity riêng cho test và production; pipeline production chỉ nhận quyền trên project và tài nguyên cần triển khai, có phê duyệt phù hợp.

## Tài liệu tham khảo

- [Google Cloud: Resource hierarchy](https://cloud.google.com/resource-manager/docs/cloud-platform-resource-hierarchy)
- [Google Cloud: IAM overview](https://cloud.google.com/iam/docs/overview)
- [Google Cloud: Shared VPC](https://cloud.google.com/vpc/docs/shared-vpc)
- [Google Cloud: Hierarchical firewall policies](https://cloud.google.com/firewall/docs/firewall-policies)
- [Google Cloud: Organization Policy overview](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
- [Google Cloud: VPC Service Controls overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Google Cloud: Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Google Cloud: Cloud Audit Logs](https://cloud.google.com/logging/docs/audit)
