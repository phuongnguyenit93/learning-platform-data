# Thiết kế phòng vệ nhiều lớp cho tài nguyên GCP

Một môi trường Google Cloud an toàn cần nhiều lớp kiểm soát hoạt động cùng nhau. IAM giới hạn ai được làm gì; Organization Policy giới hạn loại cấu hình được phép; mạng riêng kiểm soát đường đi của lưu lượng; cấu hình workload và dữ liệu giảm tác động khi một thành phần bị xâm nhập; còn nhật ký, cảnh báo và quy trình ứng phó giúp phát hiện sự cố trước khi nó lan rộng.

Trong phạm vi **CLOUD_PROVIDERS_GCP**, bài học này đi từ cấu trúc tổ chức, project, IAM và VPC đến Compute Engine, GKE, Cloud Run, dịch vụ lưu trữ và cơ sở dữ liệu. Mục tiêu là biết chọn lớp bảo vệ phù hợp, triển khai chúng theo một kiến trúc nhất quán, tự động hóa kiểm tra và theo dõi độ tin cậy cùng chi phí.

Sau bài học, người học có thể:

- Phân chia ranh giới bảo mật theo organization, folder, project và workload.
- Kết hợp IAM, Organization Policy và kiểm soát mạng theo nguyên tắc đặc quyền tối thiểu.
- Chọn biện pháp bảo vệ phù hợp cho máy ảo, Kubernetes, dịch vụ serverless, storage và database.
- Thiết lập mã hóa, quản lý bí mật, nhật ký kiểm toán và phát hiện mối đe dọa.
- Đưa kiểm soát bảo mật vào Infrastructure as Code và quy trình phát hành.
- Đánh giá một thiết kế bằng luồng truy cập, tình huống tấn công và bằng chứng vận hành.

## 1. Tư duy phòng vệ nhiều lớp

Phòng vệ nhiều lớp (defense in depth) giả định rằng một kiểm soát đơn lẻ có thể bị cấu hình sai, bị vượt qua hoặc bị chiếm quyền. Vì vậy, một yêu cầu truy cập quan trọng cần được kiểm tra ở nhiều ranh giới độc lập.

Ví dụ, một dịch vụ web chỉ nên đọc dữ liệu từ Cloud Storage khi đồng thời thỏa mãn các điều kiện: workload chạy bằng danh tính dịch vụ được cấp quyền đọc đúng bucket; bucket không cho truy cập công khai; đường truy cập và chính sách tổ chức phù hợp; dữ liệu được mã hóa; thao tác truy cập được ghi nhận và có thể điều tra. Nếu một lớp bị cấu hình sai, các lớp còn lại vẫn có thể giới hạn phạm vi thiệt hại.

Các lớp thường gặp:

| Lớp | Câu hỏi cần trả lời | Kiểm soát tiêu biểu |
|---|---|---|
| Quản trị tổ chức | Tài nguyên nào được phép tồn tại và ở đâu? | Resource hierarchy, Organization Policy, phân tách project |
| Danh tính | Ai hoặc workload nào được phép thực hiện hành động? | IAM, IAM Conditions, service account, Workload Identity Federation |
| Mạng | Lưu lượng nào được đi vào, đi ra và đi giữa các vùng? | VPC, subnet, firewall policy, Cloud NAT, Private Service Connect |
| Workload | Máy ảo, container và runtime được cấu hình an toàn ra sao? | Shielded VM, GKE security, Cloud Run ingress, vá lỗi |
| Dữ liệu | Dữ liệu được phân loại, truy cập, mã hóa và khôi phục thế nào? | Cloud KMS, Secret Manager, bucket controls, database private IP |
| Chuỗi cung ứng | Mã nguồn và image nào được phép phát hành? | CI/CD identity, image scanning, Binary Authorization, provenance |
| Phát hiện và ứng phó | Làm sao biết có sự cố và giới hạn tác động? | Cloud Audit Logs, Security Command Center, Cloud Logging, alert |

Không phải workload nào cũng cần mọi sản phẩm bảo mật. Hãy bắt đầu từ tài sản, dữ liệu, luồng truy cập và mối đe dọa; sau đó chọn kiểm soát tương xứng với rủi ro, yêu cầu tuân thủ và chi phí vận hành.

### 1.1. Xác định tài sản và ranh giới tin cậy

Trước khi tạo firewall rule hay gán IAM role, cần lập danh sách:

1. Tài sản: project, VM, cluster, service, bucket, database, secret, khóa mã hóa và pipeline.
2. Chủ sở hữu: nhóm chịu trách nhiệm vận hành và nhóm phê duyệt quyền truy cập.
3. Dữ liệu: công khai, nội bộ, nhạy cảm hoặc chịu yêu cầu lưu trú/retention cụ thể.
4. Luồng dữ liệu: nguồn gọi, đích đến, giao thức, danh tính sử dụng và dữ liệu đi qua.
5. Mối đe dọa: tài khoản bị đánh cắp, cấu hình công khai, di chuyển ngang, đánh cắp secret, phát hành image độc hại hoặc xóa dữ liệu.

Ranh giới tin cậy không nhất thiết trùng với ranh giới mạng. Một VM ở subnet riêng vẫn có thể bị truy cập trái phép nếu service account của nó có quyền quá rộng. Ngược lại, một dịch vụ có endpoint công khai vẫn có thể được bảo vệ bằng xác thực, kiểm soát ingress, WAF và quyền truy cập dữ liệu chặt chẽ.

## 2. Lớp quản trị: tổ chức, folder, project và Organization Policy

Google Cloud tổ chức tài nguyên theo cây:

~~~text
Organization
├── Folder: production
│   ├── Project: app-prod
│   └── Project: data-prod
├── Folder: non-production
│   ├── Project: app-dev
│   └── Project: app-test
└── Folder: security
    └── Project: central-security
~~~

IAM allow policy và Organization Policy có thể kế thừa từ node cha xuống node con. Thiết kế hierarchy tốt giúp áp dụng quy tắc chung ở cấp cao, đồng thời cho phép ngoại lệ có kiểm soát ở phạm vi nhỏ hơn.

### 2.1. Phân tách project theo môi trường và trách nhiệm

- Tách production khỏi development/test để quyền thử nghiệm không tự động trở thành quyền trên dữ liệu thật.
- Tách project mạng dùng chung, logging/security và workload khi tổ chức cần ranh giới quản trị riêng.
- Dùng Shared VPC khi nhiều project workload cần dùng chung một mạng do nhóm network quản lý. Host project sở hữu mạng; service project chứa workload.
- Đặt tên, label và owner rõ ràng để truy vết chi phí, tài sản và trách nhiệm.
- Hạn chế quyền tạo project và thay đổi cấu trúc organization cho một nhóm quản trị nhỏ.

Tách project không tự tạo ra bảo mật. Cần kiểm tra cả quyền IAM, liên kết mạng, service account, log sink và đường truy cập dữ liệu giữa các project.

### 2.2. Dùng Organization Policy để chặn cấu hình rủi ro

Organization Policy đặt giới hạn cấu hình trên tài nguyên. Một số constraint thường được cân nhắc:

- **constraints/iam.disableServiceAccountKeyCreation**: ngăn tạo khóa service account dạng tệp.
- **constraints/iam.disableServiceAccountKeyUpload**: ngăn tải khóa service account bên ngoài lên.
- **constraints/storage.publicAccessPrevention**: ngăn cấp quyền truy cập công khai cho Cloud Storage.
- **constraints/compute.vmExternalIpAccess**: giới hạn VM được phép có địa chỉ IP bên ngoài.
- **constraints/compute.requireShieldedVm**: yêu cầu sử dụng Shielded VM trong phạm vi hỗ trợ.
- **constraints/gcp.resourceLocations**: giới hạn vị trí tạo tài nguyên theo chính sách tổ chức.

Khả năng áp dụng và hành vi của từng constraint phụ thuộc loại tài nguyên, phiên bản dịch vụ và phạm vi hỗ trợ. Cần kiểm tra tài liệu của constraint trước khi áp dụng ở cấp organization.

Quy trình an toàn:

1. Chọn một folder hoặc project thử nghiệm.
2. Xác định tài nguyên hiện có có vi phạm constraint hay không.
3. Thử chế độ audit hoặc kiểm tra tác động nếu constraint hỗ trợ.
4. Xử lý workload cần ngoại lệ bằng quy trình phê duyệt.
5. Enforce ở phạm vi phù hợp, theo dõi lỗi triển khai và định kỳ rà soát ngoại lệ.

Organization Policy và IAM giải quyết hai câu hỏi khác nhau. IAM quyết định principal có quyền gọi hành động nào; Organization Policy giới hạn cấu hình nào được phép tồn tại. Chặn tạo IP công khai không thay thế việc kiểm tra quyền IAM, và cấp quyền IAM không làm cho cấu hình bị Organization Policy cấm trở nên hợp lệ.

## 3. Lớp danh tính: IAM và service account

Trong cloud, danh tính là ranh giới bảo mật chính. Một request có thể đến từ người dùng, nhóm, service account, workload trong GKE hoặc hệ thống CI/CD bên ngoài.

### 3.1. Áp dụng đặc quyền tối thiểu

- Cấp quyền cho Google Group thay vì gán trực tiếp cho nhiều tài khoản cá nhân.
- Ưu tiên predefined role phù hợp với nhiệm vụ. Tạo custom role khi role có sẵn cấp thừa quyền và tổ chức có khả năng duy trì custom role.
- Tránh dùng các primitive role Owner, Editor và Viewer cho công việc thường ngày vì phạm vi quyền rộng.
- Gán role ở node nhỏ nhất đáp ứng nhu cầu: resource hoặc project thay vì organization nếu không cần quyền toàn tổ chức.
- Dùng IAM Conditions để giới hạn quyền theo thời gian, thuộc tính tài nguyên hoặc ngữ cảnh được hỗ trợ.
- Tách quyền triển khai, quyền vận hành và quyền đọc log; không dùng một tài khoản quản trị cho mọi công việc.

Ví dụ: nhóm phát triển cần triển khai Cloud Run có thể được cấp quyền triển khai dịch vụ trong project ứng dụng và quyền sử dụng đúng runtime service account. Nhóm này không cần quyền quản trị organization, sửa firewall của toàn công ty hoặc đọc mọi secret production.

### 3.2. Thiết kế service account cho workload

Mỗi workload nên có danh tính riêng theo chức năng và môi trường. Không dùng chung một service account có quyền rộng cho nhiều ứng dụng vì khi một ứng dụng bị xâm nhập, kẻ tấn công có thể kế thừa toàn bộ quyền của danh tính dùng chung.

- Chỉ cấp các role cần thiết để workload đọc/ghi đúng tài nguyên.
- Không nhúng khóa JSON vào source code, image container, biến môi trường lâu dài hoặc CI variable.
- Ưu tiên danh tính gắn với runtime và cơ chế impersonation thay cho khóa dài hạn.
- Dùng Workload Identity Federation để CI/CD hoặc workload bên ngoài Google Cloud lấy danh tính ngắn hạn mà không phải lưu khóa service account.
- Với GKE, dùng Workload Identity Federation for GKE để ánh xạ Kubernetes ServiceAccount sang quyền Google Cloud.
- Rà soát quyền của service agent do dịch vụ quản lý; không xóa hoặc chỉnh sửa role của service agent theo suy đoán.

Khóa service account chỉ nên là ngoại lệ có lý do, chủ sở hữu, thời hạn và quy trình thu hồi rõ ràng. Nếu phải dùng khóa trong hệ thống cũ, lưu trong kho bí mật được kiểm soát, giới hạn nơi sử dụng, theo dõi lần dùng và lập kế hoạch loại bỏ.

### 3.3. Kiểm tra quyền định kỳ

IAM Recommender và Policy Intelligence có thể hỗ trợ phát hiện quyền ít dùng hoặc phân tích tác động của policy. Đây là tín hiệu để người sở hữu rà soát; không nên tự động xóa quyền chỉ dựa trên một khoảng thời gian không hoạt động nếu chưa hiểu quy trình nghiệp vụ.

Khi điều tra một request bị từ chối, kiểm tra principal, resource, permission, policy kế thừa, IAM Condition, deny policy và Organization Policy. Một lỗi 403 không nhất thiết có nghĩa là thiếu một role đơn giản.

## 4. Lớp mạng: phân đoạn, kiểm soát ingress và egress

VPC tạo phạm vi mạng logic cho tài nguyên. Subnet phân chia dải địa chỉ IP theo vùng; firewall rule và firewall policy kiểm soát lưu lượng; các dịch vụ kết nối riêng hạn chế nhu cầu đưa tài nguyên ra Internet.

### 4.1. Phân đoạn mạng theo luồng nghiệp vụ

Thiết kế mạng nên xuất phát từ luồng giao tiếp cần thiết:

- Web/API chỉ nhận lưu lượng từ load balancer hoặc nguồn đã xác định.
- Application tier chỉ gọi database trên cổng cần thiết.
- Database không nhận kết nối trực tiếp từ Internet.
- Management traffic đi qua IAP hoặc đường quản trị riêng.
- Môi trường dev/test không mặc nhiên được kết nối tới production.
- Egress chỉ mở theo nhu cầu; các dịch vụ cần gọi API Google có thể dùng Private Google Access hoặc Private Service Connect tùy kiến trúc.

Không coi subnet là biện pháp cô lập đầy đủ. Trong cùng VPC, firewall policy vẫn cần xác định nguồn, đích, giao thức và cổng. Khi dùng Shared VPC, cần thống nhất quyền quản lý network, firewall và quyền triển khai workload giữa host project và service project.

### 4.2. Quản lý firewall

Ưu tiên quy tắc rõ ràng, có chủ sở hữu và mục đích:

1. Xác định luồng hợp lệ trước khi tạo rule.
2. Tránh mở SSH/RDP hoặc cổng quản trị tới toàn Internet.
3. Không dùng dải IP nguồn quá rộng khi có thể giới hạn theo subnet, service account, tag hoặc danh tính phù hợp.
4. Dùng hierarchical firewall policies khi cần quy tắc bắt buộc ở cấp organization/folder; dùng VPC firewall rules cho phạm vi mạng tương ứng.
5. Rà soát rule không còn được dùng, rule trùng lặp và rule có độ ưu tiên làm vô hiệu quy tắc dự kiến.
6. Kiểm tra cả ingress lẫn egress, kể cả lưu lượng từ workload tới API bên ngoài.

Một rule cho phép rộng có thể làm mất tác dụng của phân đoạn mạng. Mọi thay đổi firewall cần được đánh giá theo luồng ứng dụng thực tế và có kế hoạch rollback.

### 4.3. Truy cập riêng và kết nối ra ngoài

- **IAP TCP forwarding** cho phép quản trị VM qua danh tính và IAM mà không cần mở SSH/RDP công khai.
- **Cloud NAT** cung cấp NAT cho kết nối outbound từ workload không có external IP; có thể cấu hình địa chỉ NAT tĩnh khi cần địa chỉ nguồn ổn định. Cloud NAT không tạo đường kết nối inbound vào VM.
- **Private Google Access** cho phép VM chỉ có địa chỉ nội bộ truy cập các API và dịch vụ Google được hỗ trợ.
- **Private Service Connect** cung cấp kết nối riêng tới dịch vụ Google hoặc dịch vụ được publish bởi nhà cung cấp.
- **Cloud VPN** và **Cloud Interconnect** kết nối mạng tại chỗ với VPC qua các mô hình phù hợp về mã hóa, độ trễ và băng thông.
- **Cloud Armor** bảo vệ ứng dụng phía sau load balancer bằng chính sách WAF và khả năng giảm thiểu DDoS phù hợp với loại load balancer.

### 4.4. Phân biệt firewall với VPC Service Controls

VPC Service Controls tạo service perimeter quanh các dịch vụ Google được hỗ trợ để giảm nguy cơ truy cập hoặc đưa dữ liệu ra ngoài perimeter qua API. Nó hữu ích với dữ liệu nhạy cảm trong các dịch vụ như Cloud Storage và BigQuery.

VPC Service Controls không phải firewall mạng tổng quát, không thay thế IAM và không bảo vệ mọi API hay mọi đường truyền. Thiết kế perimeter phải tính đến ingress/egress rule, project, service, danh tính, thiết bị và các dịch vụ tích hợp. Hãy thử nghiệm luồng hợp lệ trước khi enforce để tránh chặn pipeline hoặc ứng dụng đang chạy.

## 5. Lớp workload: bảo vệ Compute Engine, GKE và Cloud Run

### 5.1. Compute Engine

- Dùng Shielded VM khi phù hợp để tăng khả năng bảo vệ chuỗi khởi động bằng Secure Boot, vTPM và integrity monitoring.
- Ưu tiên VM không có external IP; dùng IAP hoặc bastion được kiểm soát cho truy cập quản trị.
- Bật OS Login và gắn quyền SSH qua IAM thay vì quản lý khóa SSH thủ công trên từng máy.
- Vá hệ điều hành và package theo lịch; theo dõi trạng thái cập nhật và lỗ hổng.
- Giới hạn service account của VM; metadata server không nên trở thành đường lấy credential có quyền rộng.
- Tách workload theo môi trường và mức độ nhạy cảm; không chạy nhiều ứng dụng không liên quan dưới cùng một danh tính.

### 5.2. Google Kubernetes Engine

Cluster Kubernetes có thêm lớp quyền Kubernetes RBAC bên cạnh IAM của Google Cloud. Cần kiểm soát cả hai:

- Dùng private nodes và giới hạn đường truy cập control plane theo mô hình mạng của tổ chức.
- Dùng Workload Identity Federation for GKE để pod truy cập API Google bằng danh tính riêng.
- Áp dụng Kubernetes RBAC theo namespace và nhiệm vụ; tránh cấp cluster-admin cho tài khoản ứng dụng.
- Dùng NetworkPolicy để giới hạn giao tiếp giữa pod khi kiến trúc và dataplane hỗ trợ.
- Quản lý image qua Artifact Registry; quét lỗ hổng và chỉ triển khai image từ nguồn tin cậy.
- Cân nhắc Binary Authorization để áp dụng chính sách về image được phép chạy.
- Bảo vệ secret, cấu hình admission và quyền truy cập vào Kubernetes API; cập nhật control plane và node theo lịch hỗ trợ.

Private cluster không đồng nghĩa cluster đã an toàn. Quyền RBAC quá rộng, image độc hại hoặc workload identity có quyền cao vẫn có thể dẫn đến chiếm quyền.

### 5.3. Cloud Run và dịch vụ serverless

- Chọn ingress phù hợp: chỉ nội bộ, nội bộ và load balancer, hoặc cho phép truy cập rộng theo yêu cầu sản phẩm.
- Bật xác thực IAM cho endpoint không dành cho truy cập công khai; nếu dịch vụ phải public, giới hạn ingress và bảo vệ phía load balancer.
- Gán runtime service account riêng với quyền tối thiểu.
- Dùng Secret Manager để cung cấp secret; không đóng secret vào image.
- Dùng Direct VPC egress hoặc Serverless VPC Access khi dịch vụ cần truy cập tài nguyên mạng riêng, tùy loại dịch vụ và yêu cầu kiến trúc.
- Giới hạn concurrency, timeout, CPU/memory và autoscaling theo tải thực tế để kiểm soát độ tin cậy và chi phí.

Serverless giảm gánh nặng quản lý máy chủ nhưng không loại bỏ trách nhiệm bảo vệ danh tính, ứng dụng, dữ liệu, cấu hình ingress và dependency.

## 6. Lớp dữ liệu: quyền truy cập, mã hóa và khôi phục

### 6.1. Cloud Storage

Với bucket chứa dữ liệu nội bộ hoặc nhạy cảm:

- Bật Uniform bucket-level access để quản lý quyền bằng IAM nhất quán thay vì trộn IAM với ACL.
- Bật Public Access Prevention để ngăn cấp quyền công khai ngoài ý muốn.
- Chỉ cấp quyền cho service account hoặc nhóm cần truy cập.
- Dùng versioning, retention policy hoặc cơ chế backup phù hợp với mục tiêu khôi phục.
- Kiểm soát vị trí dữ liệu và vòng đời object để đáp ứng yêu cầu lưu trú, lưu giữ và chi phí.
- Bật Data Access audit logs khi cần bằng chứng ai đã đọc hoặc thay đổi dữ liệu.

Ví dụ Terraform cho bucket riêng tư:

~~~hcl
resource "google_storage_bucket" "private_data" {
  name                        = "example-project-private-data"
  location                    = "ASIA"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }
}
~~~

Đây là cấu hình minh họa. Tên bucket phải duy nhất toàn cầu; vị trí phải được chọn theo yêu cầu dữ liệu; provider và quyền triển khai phải phù hợp với môi trường. Versioning hỗ trợ phục hồi object nhưng không thay thế bản sao lưu độc lập hoặc quy trình kiểm thử restore.

### 6.2. Cloud SQL và cơ sở dữ liệu

- Ưu tiên private IP và kết nối qua VPC khi ứng dụng chạy trong môi trường mạng phù hợp.
- Tránh mở authorized network quá rộng hoặc cho phép mọi địa chỉ nguồn.
- Dùng danh tính và cơ chế xác thực được dịch vụ hỗ trợ; không chia sẻ một tài khoản database cho mọi ứng dụng.
- Lưu credential trong Secret Manager và có lịch thay đổi/thu hồi.
- Bật backup, point-in-time recovery và kiểm thử khôi phục định kỳ.
- Giới hạn quyền database theo schema, bảng hoặc thao tác cần thiết.
- Theo dõi kết nối, lỗi xác thực, thay đổi cấu hình và truy vấn nhạy cảm theo khả năng của dịch vụ.

Private IP giảm bề mặt phơi lộ mạng nhưng không tự kiểm soát quyền ở tầng database. Ứng dụng vẫn cần xác thực và phân quyền dữ liệu.

### 6.3. Cloud KMS và Secret Manager

Mã hóa dữ liệu khi lưu trữ và khi truyền là lớp nền tảng. Mặc định mã hóa do Google quản lý đáp ứng nhiều trường hợp; CMEK (customer-managed encryption keys) phù hợp khi tổ chức cần kiểm soát vòng đời khóa, quyền sử dụng hoặc yêu cầu kiểm toán cụ thể.

Khi dùng CMEK:

- Tách người quản trị khóa khỏi người quản trị dữ liệu khi cần phân nhiệm.
- Cấp quyền dùng khóa cho service agent đúng dịch vụ và đúng key.
- Thiết kế rotation, giám sát và phương án khôi phục dịch vụ/quyền truy cập khóa; với external key manager, làm rõ khả năng backup theo nhà cung cấp.
- Hiểu tác động khi khóa bị vô hiệu hóa hoặc mất quyền truy cập: workload có thể không đọc/ghi được dữ liệu.

Secret Manager dành cho secret như API token, mật khẩu và credential. Phân quyền theo secret, tránh cấp quyền đọc toàn bộ secret cho workload; dùng version, rotation và audit log phù hợp. Không ghi secret vào log, exception message hoặc output của pipeline.

## 7. Lớp chuỗi cung ứng phần mềm và triển khai

Một workload được cấu hình tốt vẫn có thể bị xâm nhập nếu pipeline phát hành image không đáng tin cậy. Chuỗi cung ứng cần được bảo vệ từ source đến runtime.

1. Bảo vệ repository, branch, review và credential của hệ thống build.
2. Dùng Workload Identity Federation để pipeline bên ngoài lấy quyền ngắn hạn; tách identity build khỏi identity deploy.
3. Cấp cho pipeline quyền đẩy image vào đúng Artifact Registry repository và triển khai đúng project/service.
4. Quét lỗ hổng image, kiểm soát dependency và tạo provenance cho artifact khi quy trình hỗ trợ.
5. Dùng Binary Authorization hoặc cơ chế admission tương đương để giới hạn image được chạy.
6. Quản lý hạ tầng bằng Terraform hoặc công cụ IaC; review thay đổi IAM, firewall, bucket, key và policy như review code.
7. Chạy kiểm tra policy trong CI trước khi áp dụng; phát hiện public bucket, quyền quá rộng, external IP ngoài danh sách và cấu hình mã hóa thiếu.
8. Ghi nhận ai phê duyệt, commit nào tạo artifact và artifact nào được triển khai.

Không nên để pipeline có quyền Owner chỉ vì cần triển khai. Tạo role triển khai hẹp theo dịch vụ, resource và môi trường; dùng approval riêng cho production.

## 8. Lớp phát hiện: nhật ký, Security Command Center và cảnh báo

Kiểm soát phòng ngừa không thể bảo đảm không có sự cố. Hệ thống cần tạo bằng chứng đủ để phát hiện, điều tra và khôi phục.

### 8.1. Cloud Audit Logs

Cloud Audit Logs ghi nhận hoạt động trên tài nguyên Google Cloud. Các nhóm log quan trọng gồm:

- **Admin Activity**: thao tác quản trị và thay đổi cấu hình.
- **System Event**: hoạt động do hệ thống Google Cloud thực hiện.
- **Policy Denied**: request bị từ chối bởi policy trong trường hợp dịch vụ hỗ trợ.
- **Data Access**: truy cập dữ liệu hoặc thao tác đọc/ghi cần kiểm toán; cần xem xét bật rõ ràng cho dịch vụ và dữ liệu nhạy cảm.

Đưa log quan trọng về project logging/security tập trung bằng aggregated sink ở cấp organization hoặc folder. Giới hạn quyền đọc, sửa và xóa log; cấu hình retention và export phù hợp yêu cầu điều tra. Log tập trung vẫn cần kiểm soát chi phí ingest, lưu trữ và truy vấn.

### 8.2. Security Command Center

Security Command Center (SCC) cung cấp góc nhìn về tư thế bảo mật, lỗ hổng, cấu hình sai và mối đe dọa trên tài nguyên Google Cloud. Năng lực cụ thể phụ thuộc edition, dịch vụ được bật và phạm vi triển khai.

Quy trình vận hành nên có:

- Phân loại finding theo mức độ nghiêm trọng và mức phơi lộ thực tế.
- Gán owner và thời hạn xử lý.
- Ưu tiên finding có đường khai thác rõ, dữ liệu nhạy cảm hoặc quyền đặc biệt.
- Theo dõi trạng thái khắc phục và finding tái xuất hiện.
- Đưa finding quan trọng vào hệ thống ticket/incident theo quy trình của tổ chức.

Cloud Asset Inventory hỗ trợ kiểm kê tài sản và truy vấn cấu hình; Policy Intelligence hỗ trợ phân tích quyền. Kết hợp các nguồn này để trả lời câu hỏi tài sản nào đang tồn tại, ai có quyền truy cập và thay đổi nào vừa xảy ra.

### 8.3. Cảnh báo và ứng phó

Tạo cảnh báo cho các sự kiện có ý nghĩa vận hành, ví dụ:

- Có thay đổi IAM ở cấp organization hoặc project production.
- Có service account key mới hoặc dấu hiệu sử dụng credential bất thường.
- Firewall mở cổng quản trị ra dải nguồn rộng.
- Bucket hoặc dịch vụ dữ liệu trở nên công khai.
- Workload phát sinh lưu lượng egress bất thường.
- Finding nghiêm trọng xuất hiện hoặc backup/restore thất bại.

Mỗi cảnh báo cần có người nhận, mức độ ưu tiên, nguồn log, bước xác minh và hành động khắc phục. Kiểm thử quy trình ứng phó bằng tình huống giả lập; chỉ bật cảnh báo mà không có người xử lý sẽ tạo nhiễu thay vì giảm rủi ro.

## 9. Ví dụ kiến trúc: ứng dụng API dùng Cloud Run và Cloud SQL

Giả sử một ứng dụng nhận request từ Internet, xử lý bằng Cloud Run, lưu dữ liệu trong Cloud SQL và lưu tệp trong Cloud Storage.

~~~mermaid
flowchart TD
    U[Người dùng Internet] --> B[External HTTPS Load Balancer]
    A[Cloud Armor security policy] -. Gắn với backend service .-> B
    B --> C[Cloud Run API]
    C -->|Danh tính runtime riêng| D[Cloud SQL private IP]
    C -->|Quyền đọc ghi giới hạn| E[Cloud Storage private bucket]
    C --> F[Secret Manager]
    D --> G[Backup và phục hồi]
    C --> H[Cloud Logging và Audit Logs]
    E --> H
    D --> H
    H --> I[Project security tập trung]
    I --> J[Security Command Center và cảnh báo]
~~~

Các quyết định bảo mật:

1. Load balancer là điểm nhận lưu lượng Internet; Cloud Armor áp dụng chính sách bảo vệ HTTP(S).
2. Cloud Run giới hạn ingress ở internal-and-cloud-load-balancing khi kiến trúc dùng external Application Load Balancer; cấu hình xác thực phù hợp với cách ứng dụng phục vụ người dùng.
3. Cloud Run chạy bằng service account riêng, chỉ có quyền truy cập database và bucket cần thiết.
4. Cloud Run dùng Direct VPC egress hoặc Serverless VPC Access để kết nối Cloud SQL qua private IP.
5. Bucket bật Uniform bucket-level access và Public Access Prevention; quyền truy cập chỉ cấp cho service account của ứng dụng.
6. Secret Manager giữ credential cần thiết; ứng dụng không đóng credential trong image.
7. Backup database được cấu hình theo RPO/RTO; nhóm vận hành kiểm thử restore.
8. Audit log và log ứng dụng được chuyển về nơi lưu tập trung; SCC và cảnh báo hỗ trợ phát hiện cấu hình sai hoặc hoạt động bất thường.

Điểm cần kiểm chứng khi triển khai là đường đi thực tế từ load balancer đến Cloud Run, quyền invoke, kết nối VPC, DNS, firewall, quyền Cloud SQL và quyền đọc secret. Một sơ đồ đúng về mặt ý tưởng vẫn có thể thất bại nếu thiếu một quyền hoặc tuyến mạng cụ thể.

## 10. Lộ trình triển khai theo từng giai đoạn

Không nên bật đồng loạt mọi policy trên production khi chưa biết tác động. Có thể triển khai theo thứ tự:

| Giai đoạn | Việc thực hiện | Bằng chứng hoàn thành |
|---|---|---|
| 1. Kiểm kê | Liệt kê project, tài sản, owner, dữ liệu và luồng truy cập | Inventory có owner và mức độ nhạy cảm |
| 2. Quản trị | Chuẩn hóa folder/project, bật Organization Policy phù hợp | Policy được thử nghiệm, ngoại lệ có owner |
| 3. Danh tính | Rà soát role rộng, service account, khóa và quyền CI/CD | Danh sách quyền tối thiểu, không còn khóa không cần thiết |
| 4. Mạng | Phân đoạn VPC, kiểm tra firewall, loại bỏ IP công khai không cần | Luồng được cho phép có tài liệu và kiểm thử |
| 5. Workload/dữ liệu | Hardening VM/GKE/Cloud Run, bucket/database private, secret và backup | Kiểm tra cấu hình và thử restore đạt |
| 6. Phát hiện | Tập trung audit log, bật SCC, tạo cảnh báo | Log truy vấn được, cảnh báo có người nhận |
| 7. Tự động hóa | Đưa policy và kiểm tra cấu hình vào IaC/CI | Pipeline chặn được cấu hình vi phạm mẫu |
| 8. Vận hành | Diễn tập sự cố, rà soát ngoại lệ và quyền định kỳ | Biên bản diễn tập và action item có owner |

Mỗi giai đoạn cần có kế hoạch rollback, người chịu trách nhiệm và cách đo tác động tới ứng dụng. Với thay đổi có thể chặn request, hãy thử trên môi trường đại diện trước khi mở rộng.

## 11. Checklist đánh giá thiết kế

### Tổ chức và IAM

- [ ] Production được tách khỏi môi trường phát triển theo ranh giới phù hợp.
- [ ] Quyền Owner/Editor được giới hạn và có quy trình cấp quyền khẩn cấp.
- [ ] Workload dùng service account riêng, quyền tối thiểu.
- [ ] Không còn service account key dài hạn không có lý do và chủ sở hữu.
- [ ] Organization Policy có phạm vi, ngoại lệ và quy trình kiểm tra rõ ràng.

### Mạng và workload

- [ ] VM không cần public IP đã được loại bỏ external IP.
- [ ] SSH/RDP không mở cho toàn Internet; truy cập quản trị có danh tính.
- [ ] Firewall rule có owner, mục đích và nguồn/đích giới hạn.
- [ ] GKE có RBAC, Workload Identity Federation và kiểm soát image.
- [ ] Cloud Run có ingress, xác thực và runtime identity phù hợp.
- [ ] Database không nhận kết nối công khai ngoài yêu cầu đã phê duyệt.

### Dữ liệu và vận hành

- [ ] Bucket nhạy cảm bật Uniform bucket-level access và Public Access Prevention.
- [ ] Secret không nằm trong source, image hoặc log.
- [ ] Mã hóa, key access và vị trí dữ liệu đáp ứng yêu cầu.
- [ ] Backup có RPO/RTO và đã thử khôi phục.
- [ ] Audit log cần thiết được bật và chuyển về nơi lưu tập trung.
- [ ] Finding nghiêm trọng có owner, thời hạn và bằng chứng khắc phục.
- [ ] Chi phí log, network egress, backup và dịch vụ bảo mật được theo dõi.

## 12. Sai lầm thường gặp

**Chỉ dựa vào firewall.** Firewall không thay thế IAM, xác thực ứng dụng hay quyền database. Một workload bị xâm nhập vẫn có thể dùng service account quá rộng để đọc dữ liệu.

**Dùng một service account cho nhiều ứng dụng.** Điều này làm tăng phạm vi ảnh hưởng khi một ứng dụng bị chiếm quyền. Hãy tách danh tính theo workload và môi trường.

**Cho rằng private IP đồng nghĩa an toàn.** Private IP giảm khả năng bị truy cập trực tiếp từ Internet nhưng không ngăn principal nội bộ có quyền quá mức hoặc workload bị xâm nhập.

**Bật policy ở cấp organization mà chưa đánh giá tác động.** Constraint có thể làm pipeline hoặc dịch vụ hiện hữu không triển khai được. Hãy thử nghiệm, ghi nhận ngoại lệ và mở rộng theo giai đoạn.

**Dùng VPC Service Controls như firewall tổng quát.** Service perimeter tập trung vào truy cập API và nguy cơ thất thoát dữ liệu của dịch vụ được hỗ trợ; nó không thay thế firewall, IAM hay kiểm soát egress tổng quát.

**Bật log nhưng không có người xử lý.** Log chỉ có giá trị khi được giữ đủ lâu, có thể truy vấn và gắn với quy trình cảnh báo/ứng phó.

**Coi backup là đã khôi phục được dữ liệu.** Chỉ một lần restore thử nghiệm mới cho biết bản backup, quyền, khóa và quy trình phục hồi có hoạt động cùng nhau hay không.

**Bỏ qua chi phí vận hành.** Log Data Access, lưu trữ dài hạn, Cloud NAT, egress, SCC và backup có thể tạo chi phí đáng kể. Cần đặt retention, sampling ở nơi phù hợp và theo dõi ngân sách mà không làm mất bằng chứng cần thiết.

## 13. Tài liệu tham khảo chính thức

- [Organization Policy overview](https://cloud.google.com/resource-manager/docs/organization-policy/overview)
- [IAM overview](https://cloud.google.com/iam/docs/overview)
- [VPC firewall rules](https://cloud.google.com/vpc/docs/firewalls)
- [VPC Service Controls overview](https://cloud.google.com/vpc-service-controls/docs/overview)
- [Cloud Armor overview](https://cloud.google.com/armor/docs/overview)
- [Shielded VM overview](https://cloud.google.com/compute/shielded-vm/docs/shielded-vm)
- [Workload Identity Federation](https://cloud.google.com/iam/docs/workload-identity-federation)
- [Cloud Audit Logs overview](https://cloud.google.com/logging/docs/audit)
- [Security Command Center overview](https://cloud.google.com/security-command-center/docs/concepts-security-command-center-overview)
- [Secret Manager overview](https://cloud.google.com/secret-manager/docs/overview)
- [Binary Authorization overview](https://cloud.google.com/binary-authorization/docs/overview)

Khi thiết kế cho một hệ thống thực tế, hãy kiểm tra lại giới hạn, edition, vùng hỗ trợ và hành vi hiện hành trong tài liệu sản phẩm tương ứng. Kiến trúc phòng vệ chỉ hiệu quả khi các lớp kiểm soát được cấu hình đúng, được kiểm thử theo luồng nghiệp vụ và được duy trì trong suốt vòng đời vận hành.
