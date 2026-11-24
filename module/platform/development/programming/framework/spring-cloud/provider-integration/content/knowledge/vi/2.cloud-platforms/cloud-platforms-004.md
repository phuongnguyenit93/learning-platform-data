# Mô hình trách nhiệm chia sẻ giữa ứng dụng và nhà cung cấp

Khi triển khai Spring Boot lên AWS, Azure hoặc Google Cloud, nhiều công việc hạ tầng được nhà cung cấp quản lý: trung tâm dữ liệu, máy chủ vật lý, hệ thống lưu trữ nền tảng và một phần vận hành dịch vụ. Tuy nhiên, việc sử dụng một dịch vụ **managed** không có nghĩa nhà cung cấp tự bảo đảm dữ liệu đúng quyền truy cập, mã ứng dụng không có lỗ hổng, secret được giữ an toàn hoặc ứng dụng luôn khôi phục được sau sự cố.

Đó là lý do tồn tại **mô hình trách nhiệm chia sẻ (shared responsibility model)**: nhà cung cấp và khách hàng mỗi bên có những trách nhiệm bảo mật, vận hành và tuân thủ nhất định; ranh giới này thay đổi theo loại dịch vụ và cấu hình. Đối với mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION** trong chương **Nền tảng đám mây**, hiểu đúng mô hình là điều kiện cần trước khi tích hợp Spring Boot với managed storage, messaging, database, secret và các thư viện Spring Cloud AWS, Spring Cloud Azure, Spring Cloud GCP.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích điều nhà cung cấp thường chịu trách nhiệm **bên dưới nền tảng** và điều nhóm ứng dụng phải chịu trách nhiệm **khi sử dụng nền tảng**.
- Phân biệt mô hình trách nhiệm trong **IaaS**, nền tảng quản lý container, **PaaS/managed services**, **serverless** và **SaaS**.
- Xác định ai cần xử lý IAM/RBAC, cấu hình truy cập storage, messaging, database, secret, encryption key, backup, log và kế hoạch khôi phục.
- So sánh cách AWS, Azure và Google Cloud mô tả và triển khai các ranh giới trách nhiệm.
- Áp dụng trách nhiệm chia sẻ vào thiết kế, lập trình, cấu hình và kiểm thử tích hợp Spring Boot.
- Chuyển các trách nhiệm trừu tượng thành **người phụ trách, biện pháp kiểm soát, bằng chứng kiểm tra** và quy trình xử lý sự cố.

## 2. Hiểu đúng về trách nhiệm chia sẻ

### 2.1. Hai phía của một hệ thống cloud

Nhà cung cấp thường bảo vệ và vận hành **hạ tầng do họ kiểm soát**: cơ sở vật lý, nguồn điện, mạng nền, phần cứng, ảo hóa và các lớp dịch vụ managed theo cam kết của sản phẩm. Khách hàng chịu trách nhiệm với **thứ mình cấu hình và đưa lên cloud**: tài khoản, danh tính, chính sách quyền, dữ liệu, mã ứng dụng, lựa chọn bảo mật, mạng và quy trình nghiệp vụ.

AWS thường tóm tắt bằng cách gọi trách nhiệm của AWS là **security of the cloud**, còn trách nhiệm của khách hàng là **security in the cloud**. Azure mô tả trách nhiệm thay đổi theo mô hình triển khai và loại dịch vụ. Google Cloud sử dụng mô hình trách nhiệm chia sẻ, đồng thời nhấn mạnh tư duy **shared fate**: nhà cung cấp cung cấp thiết kế, công cụ và hỗ trợ để khách hàng vận hành an toàn hơn. Các cách diễn đạt khác nhau nhưng **không xóa trách nhiệm của ứng dụng đối với dữ liệu và cách sử dụng dịch vụ**.

~~~mermaid
flowchart TB
    C["Khách hàng / nhóm ứng dụng"] --> A["Dữ liệu, nghiệp vụ, quyền truy cập, cấu hình"]
    A --> M["Ranh giới thay đổi theo loại dịch vụ"]
    M --> P["Nền tảng managed, runtime, host, mạng vật lý"]
    P --> V["Nhà cung cấp cloud"]
    S["Chính sách, giám sát, khôi phục, tuân thủ"] -. "Cần phối hợp và phân định rõ" .-> M
~~~

Sơ đồ chỉ thể hiện trách nhiệm ở mức khái niệm. Đối với mỗi dịch vụ, phải đối chiếu **tài liệu trách nhiệm, SLA, tính năng, cấu hình, hợp đồng và phạm vi hỗ trợ** thực tế. Không nên dùng một sơ đồ tổng quát như bằng chứng rằng mọi tính năng bảo mật hoặc sao lưu đã được bật.

### 2.2. Nhà cung cấp quản lý dịch vụ không đồng nghĩa quản lý ứng dụng

Giả sử ứng dụng Spring Boot ghi hóa đơn vào một bucket:

1. Nhà cung cấp duy trì hạ tầng object storage, mạng và các cơ chế độ bền/sẵn sàng đã công bố cho loại dịch vụ và cấu hình.
2. Nhóm ứng dụng quyết định **hóa đơn nào được ghi**, đặt tên object, nội dung có chứa dữ liệu cá nhân không, ai có quyền đọc/xóa, yêu cầu versioning/retention và chính sách phục hồi.
3. Đội platform có thể quản lý provisioning, bucket policy, network và encryption configuration. Đội bảo mật có thể định nghĩa guardrail; chủ sở hữu dữ liệu quyết định thời hạn lưu và quyền sử dụng.
4. Nếu mã Spring Boot gửi nhầm dữ liệu sang bucket production của hệ thống khác, khả năng storage hoạt động đúng thiết kế **không biến lỗi nghiệp vụ thành trách nhiệm của provider**.

**Trách nhiệm chia sẻ không nhất thiết có nghĩa mỗi nhiệm vụ được chia đôi.** Có nhiệm vụ chủ yếu do provider thực hiện, có nhiệm vụ chủ yếu do khách hàng thực hiện; một số nhiệm vụ cần cả hai phối hợp. Nội bộ phía khách hàng lại cần giao trách nhiệm cụ thể cho platform, security, development và operations.

## 3. Trách nhiệm thay đổi theo mô hình dịch vụ

Đi từ máy ảo tự quản lý đến các managed service cấp cao, nhà cung cấp thường đảm nhận nhiều lớp nền tảng hơn. Trách nhiệm đối với **dữ liệu, quyền truy cập và logic nghiệp vụ** vẫn tồn tại ở phía khách hàng.

| Lớp công việc | IaaS: VM tự quản lý | Managed containers / Kubernetes | Managed database / PaaS | Serverless ứng dụng |
|---|---|---|---|---|
| Trung tâm dữ liệu, máy vật lý, hạ tầng nền | Nhà cung cấp | Nhà cung cấp | Nhà cung cấp | Nhà cung cấp |
| Hệ điều hành của máy chạy workload | Khách hàng vá và harden guest OS | Phụ thuộc node tự quản lý hay managed; provider quản lý một số lớp | Thường nhà cung cấp quản lý OS của dịch vụ | Thường nhà cung cấp quản lý host/runtime nền theo cam kết |
| Ảnh container và package ứng dụng | Khách hàng nếu dùng container | Khách hàng | Khách hàng với thành phần tự triển khai | Khách hàng với mã, package, image/layer tự cung cấp |
| Phiên bản và cấu hình phần mềm middleware/DB | Khách hàng | Tùy thành phần, node và add-on | Chia theo dịch vụ, lựa chọn version và chính sách nâng cấp | Tùy runtime, image và cấu hình nền tảng |
| Danh tính, phân quyền ứng dụng | Khách hàng | Khách hàng | Khách hàng | Khách hàng |
| Dữ liệu, phân loại và vòng đời dữ liệu | Khách hàng | Khách hàng | Khách hàng | Khách hàng |
| Cấu hình network, endpoint, firewall | Khách hàng trong phạm vi được cung cấp | Khách hàng trong phạm vi được cung cấp | Khách hàng chọn chính sách và chế độ kết nối | Khách hàng chọn chính sách và chế độ kết nối được hỗ trợ |
| Backup, restore, DR ở mức nghiệp vụ | Khách hàng thiết kế và thực thi | Khách hàng thiết kế và thực thi | Provider cung cấp tính năng; khách hàng chọn, kiểm tra và diễn tập | Khách hàng thiết kế khôi phục dữ liệu/trạng thái |

Ví dụ:

- Với **EC2, Azure Virtual Machines, Compute Engine**, nhà cung cấp không mặc nhiên cập nhật Java, Spring Boot, OpenSSL bên trong guest OS thay khách hàng.
- Với **EKS/AKS/GKE**, ai vá node và add-on phụ thuộc loại cluster, node pool, managed mode và cấu hình. Provider quản lý control plane hoặc node ở phạm vi nhất định **không đồng nghĩa** mã trong container tự an toàn.
- Với **RDS, Azure SQL Database, Cloud SQL**, provider vận hành phần hạ tầng database theo sản phẩm; khách hàng vẫn quản lý schema, dữ liệu, quyền user, cấu hình được phép, chiến lược backup/restore và kết nối.
- Với **AWS Lambda, Azure Functions, Cloud Run**, provider xử lý nhiều việc về máy chủ và khả năng co giãn; khách hàng phải chăm sóc dependency, hành vi runtime do mình kiểm soát, IAM, input validation, secret và dữ liệu.
- Với **SaaS**, provider thường chịu trách nhiệm nhiều hơn ở cả application stack; khách hàng vẫn cần quản lý danh tính, dữ liệu nhập vào, cấu hình chia sẻ và tuân thủ việc sử dụng.

Để quyết định nhiệm vụ cụ thể, đặt câu hỏi: **mình còn có quyền thay đổi lớp này không, có phải chọn cấu hình không, và dịch vụ cam kết tự vận hành phần nào?** Không dùng tên tiếp thị “fully managed” làm kết luận bảo mật.

## 4. Ma trận trách nhiệm cho một hệ thống Spring Boot

| Thành phần | Nhà cung cấp thường đảm trách | Nhóm ứng dụng/platform cần đảm trách |
|---|---|---|
| Vật lý và hạ tầng nền | Bảo vệ trung tâm dữ liệu, phần cứng và mạng hạ tầng | Chọn Region, dịch vụ và kiến trúc đáp ứng yêu cầu |
| Danh tính cloud | Dịch vụ IAM/token và cơ chế kiểm tra danh tính | Tạo/chọn principal, cấp quyền tối thiểu, quản lý trust và audit |
| Mạng managed service | Hạ tầng, giao diện kết nối được cam kết | Firewall, subnet, ingress/egress, private endpoint, DNS/TLS trong phạm vi cấu hình |
| Storage | Độ bền và tính năng lưu trữ theo cấp dịch vụ | Phân loại dữ liệu, bucket/container policy, retention, versioning, replication |
| Messaging | Hệ thống queue/topic managed và cơ chế phân phối được công bố | Kiểm soát producer/consumer, idempotency, DLQ, retry, retention, quyền |
| Database | Hạ tầng database, tác vụ bảo trì theo dịch vụ | Schema, tài khoản SQL, truy vấn, dữ liệu, backup/restore và RPO/RTO |
| Secret manager | Dịch vụ lưu trữ và giao thức truy xuất secret | Phân quyền secret, rotation, cách dùng trong app, không lộ secret qua log |
| Encryption/KMS | Triển khai thuật toán và hạ tầng key service | Chọn cơ chế/key, key policy, vòng đời, phân tách quyền và yêu cầu residency |
| Runtime ứng dụng | Lớp host/runtime managed được công bố | Mã nguồn, thư viện, bản vá phần tự quản lý, kiểm thử bảo mật |
| Quan sát và ứng cứu | Các dịch vụ log/metric/audit và khả năng hỗ trợ được cung cấp | Bật log cần thiết, cảnh báo, giữ log, phân tích và runbook xử lý |
| Khôi phục sự cố | Tính năng HA, backup, replication/failover theo dịch vụ | Đặt mục tiêu RTO/RPO, chọn cấu hình, kiểm tra restore, chuyển traffic |
| Tuân thủ | Chứng nhận/cam kết thuộc phạm vi dịch vụ cung cấp | Đánh giá phạm vi dữ liệu, chính sách nội bộ, phân quyền, bằng chứng vận hành |
| Chi phí/quota | Đo đếm và cung cấp công cụ tính phí/quota | Chọn capacity, cấu hình budget, giám sát mức dùng và tối ưu |

**“Có tính năng” khác “đã bật và kiểm chứng”.** Ví dụ một dịch vụ có khả năng geo-replication không đồng nghĩa mọi instance đã có bản sao khác Region; provider có audit logging không đồng nghĩa nhóm ứng dụng đã bật đủ luồng log để điều tra sự cố.

## 5. AWS: trách nhiệm của khách hàng trong từng managed service

### 5.1. Amazon S3

AWS quản lý hạ tầng lưu object và tính năng dịch vụ theo loại storage, class, Region và cam kết được công bố. Khách hàng quyết định **object nào được lưu, được cấp quyền ra sao và chính sách vòng đời nào áp dụng**.

- Chọn bucket, Region, storage class, lifecycle, retention và replication phù hợp.
- Sử dụng IAM role và bucket policy theo quyền tối thiểu; cân nhắc **S3 Block Public Access**, Object Ownership và các cơ chế bảo vệ khác.
- Sử dụng versioning, Object Lock hoặc backup khi yêu cầu phải khôi phục sau xóa nhầm, ghi đè hoặc ransomware. Chỉ bật encryption at rest không tự tạo lịch sử phiên bản.
- Nếu dùng SSE-KMS với key do khách hàng quản lý, thiết kế quyền mã hóa/giải mã, key policy và vòng đời key.
- Xử lý dữ liệu nhạy cảm trước upload; kiểm tra object key và metadata từ input, tránh để URL truy cập không kiểm soát hoặc logging làm lộ dữ liệu.

Một bucket có thể được mã hóa và có độ bền cao nhưng vẫn **bị lộ dữ liệu** do chính sách truy cập quá rộng hoặc **mất bản đang dùng** khi ứng dụng ghi đè/xóa mà không có cơ chế khôi phục phù hợp.

### 5.2. Amazon SQS/SNS

AWS vận hành hệ thống messaging và các đặc tính giao nhận được công bố. Nhóm ứng dụng quyết định chính sách IAM/topic/queue, thời gian giữ message, cơ chế retry, dead-letter queue (DLQ), giới hạn retry và cách xử lý dữ liệu trong payload.

**Không mặc định “đã nhận message” nghĩa là xử lý đúng một lần.** Consumer Spring Boot phải xử lý duplicate hợp lý, bảo đảm idempotency và chỉ acknowledge/delete sau khi hoàn thành xử lý theo semantics của queue/SDK. Payload không nên chứa secret thô hoặc thông tin nhạy cảm không cần thiết.

### 5.3. Amazon RDS và AWS Secrets Manager

Với RDS, AWS quản lý các lớp database service được công bố, nhưng người dùng vẫn quyết định network exposure, credential database, SQL privilege, schema, migration, log, backup retention, Multi-AZ và khôi phục theo cấu hình dịch vụ. Với Secrets Manager, AWS cung cấp khả năng lưu và lấy secret; **quyền GetSecretValue, rotation, cách ứng dụng cache/đọc secret và phân phối giá trị đến DB** vẫn cần được thiết kế.

Không nhầm permission quản lý **RDS instance** với quyền truy vấn **bảng dữ liệu** qua JDBC. Một IAM role có thể xem metadata DB nhưng không có user hoặc quyền SQL hợp lệ.

### 5.4. Runtime và công cụ quản trị AWS

Với ECS/EKS/EC2/Lambda, kiểm tra ai quản lý guest OS, task image, node AMI, runtime, layer và dependency. AWS IAM, CloudTrail, CloudWatch, AWS Config, Security Hub hay dịch vụ tương tự cung cấp cơ chế hỗ trợ bảo mật/vận hành; **khách hàng phải cấu hình phạm vi thu thập, cảnh báo và quy trình phản ứng**. Không coi việc có dashboard là bằng chứng đã được bảo vệ.

## 6. Azure: các lớp phụ trách trong managed services

Azure cung cấp nền tảng và nhiều dịch vụ bảo mật/quản lý, nhưng khách hàng vẫn sở hữu quyết định về dữ liệu, danh tính và cấu hình truy cập.

| Dịch vụ Azure | Phần nền tảng do Microsoft quản lý theo sản phẩm | Phần ứng dụng cần quản lý |
|---|---|---|
| Azure Blob Storage | Hạ tầng lưu trữ, khả năng redundancy theo SKU | Container/blob ACL, Azure RBAC data role, mạng, soft delete/versioning, replication |
| Azure Service Bus | Hạ tầng broker/namespace managed và tính năng delivery | Sender/receiver identity, khóa truy cập nếu dùng, retry/DLQ, xử lý trùng message |
| Azure SQL Database | Database platform, các tác vụ bảo trì do dịch vụ thực hiện | Cấu hình firewall, SQL/Entra users, schema, backup/restore, HA/DR được chọn |
| Azure Key Vault | Hạ tầng lưu secret/key/certificate và API bảo mật | Ai được đọc secret, policy/RBAC mode, rotation, network, key lifecycle |
| Azure App Service / Functions | Host/runtime managed trong phạm vi dịch vụ | Mã ứng dụng, package, identity, app settings, dependency, cấu hình exposure |
| Azure Kubernetes Service | Thành phần Kubernetes do AKS quản lý theo cấu hình | Workload security, RBAC, image, networking, node và add-on thuộc phạm vi khách hàng |

### 6.1. Azure RBAC và quyền dữ liệu

Một điểm đặc trưng là sự phân biệt **management plane** của Azure Resource Manager và **data plane** của nhiều dịch vụ. Ví dụ **Reader** đối với Storage Account có thể xem metadata quản trị nhưng không mặc nhiên đọc được blob bằng Microsoft Entra. Workload thường cần **Storage Blob Data Reader/Contributor** đúng phạm vi và quyền mạng thích hợp.

**Managed Identity** giúp workload nhận token mà không lưu mật khẩu ứng dụng dài hạn, nhưng người quản trị vẫn phải **gán đúng role** và chỉ định đúng identity. Có token thành công không có nghĩa role data plane đã được cấp. Nếu dùng storage account keys hoặc SAS, cần quản lý phạm vi, thời hạn và khả năng bị lộ; một số quyền quản lý có thể gián tiếp cho phép lấy key, nên phải xem xét rủi ro này khi phân quyền.

### 6.2. Key Vault, private endpoints và backup

Key Vault hỗ trợ mô hình phân quyền theo Azure RBAC hoặc access policy tùy cấu hình vault. Quyền quản lý resource không tự đồng nghĩa quyền đọc giá trị secret. Với private endpoint, nhóm ứng dụng/platform còn phải quản lý DNS, route, firewall và quyền dữ liệu. **Private endpoint không tự thu hồi mọi role quá rộng**, cũng không bảo đảm backup nằm ở vị trí địa lý được yêu cầu.

Đối với Azure Storage, LRS/ZRS/GRS/GZRS là những lựa chọn redundancy với ý nghĩa và hạn chế khác nhau; không suy ra “có GRS thì mất dữ liệu logic không thể xảy ra”. Khi cần bảo vệ trước xóa nhầm hoặc sửa dữ liệu sai, phải xem xét soft delete, versioning, retention và kế hoạch restore bên cạnh redundancy.

## 7. Google Cloud: shared responsibility và shared fate

Google Cloud quản lý hạ tầng vật lý và lớp dịch vụ được công bố. Khách hàng vẫn phải quyết định ai được truy cập dữ liệu, giới hạn truy cập, cấu hình network, mã ứng dụng và thiết kế độ tin cậy. Khái niệm **shared fate** nhấn mạnh các biện pháp và công cụ chủ động giúp khách hàng triển khai an toàn hơn; nó không có nghĩa Google thay khách hàng chịu trách nhiệm về dữ liệu, IAM hoặc lỗi nghiệp vụ.

| Dịch vụ Google Cloud | Phần được quản lý | Phần khách hàng cần quyết định |
|---|---|---|
| Cloud Storage | Hạ tầng object storage và cơ chế replication theo loại location | Bucket IAM, object retention, versioning, lifecycle, location, key và backup |
| Pub/Sub | Hạ tầng messaging, delivery theo khả năng sản phẩm | Topic/subscription policy, retry/ack, dead-letter policy, data location policy |
| Cloud SQL | Hạ tầng managed database, backup/HA theo tính năng dịch vụ | DB user/grants, schema, instance settings, HA, backup và diễn tập restore |
| Secret Manager | Hạ tầng lưu trữ và API truy xuất secret | IAM secret accessor, replication policy, rotation và không lộ secret |
| Cloud Run | Hạ tầng chạy container, scaling theo cấu hình nền tảng | Container image, code, service account, ingress/egress, concurrency, timeout |
| GKE | Control plane/node theo mode và dịch vụ được chọn | Workload/pod security, image, K8s policy, network và phần node thuộc quyền quản lý |

### 7.1. Service account, quyền và tổ chức

Nhà cung cấp bảo vệ và vận hành cơ chế IAM/token, nhưng đội triển khai quyết định service account nào chạy Spring Boot, các role nào được gán tại organization/folder/project/bucket/topic/secret, và điều kiện truy cập. **Cùng project hoặc cùng organization không mặc nhiên cho mọi workload đọc toàn bộ dữ liệu.**

Ví dụ: ứng dụng Cloud Run tải object xuống từ Cloud Storage thường cần quyền đọc object trên bucket đích; không cần quyền tạo bucket. Tạo topic Pub/Sub cần một permission khác với publish messages. API dịch vụ có thể chứa thao tác quản lý và dữ liệu trong cùng client, vì vậy phải đối chiếu **method và IAM permission thực tế**.

### 7.2. Location, secret và encryption

Cloud Storage có các lựa chọn regional, dual-region và multi-region; Secret Manager và Cloud KMS có thuộc tính location/replication riêng. Chọn project ở Singapore không tự giới hạn mọi dữ liệu trong một region. Nhóm ứng dụng phải kiểm tra **location của dữ liệu chính, bản sao, backup, secret và log**, cùng các ràng buộc Organization Policy mà dịch vụ hỗ trợ.

Một encryption key managed hoặc customer-managed không miễn trừ trách nhiệm về IAM, quyền sử dụng key, rotation, phục hồi key và quy trình ngừng sử dụng tài nguyên. Thao tác vô hiệu hóa hoặc xóa key sai thời điểm có thể khiến dữ liệu hợp lệ không còn giải mã được.

## 8. Bốn ranh giới phải có người sở hữu

### 8.1. Identity và authorization

Nhà cung cấp cung cấp IAM, token và cơ chế policy. Khách hàng phải quyết định:

- Danh tính nào đại diện cho ứng dụng Spring Boot ở dev, staging và production.
- Scope quyền nằm tại bucket, topic, namespace, queue, resource group, subscription hay project.
- Role nào dành cho CI/CD để tạo và cấu hình tài nguyên; role nào dành cho runtime để sử dụng dữ liệu.
- Cách thu hồi quyền, rotate credential khi cần, kiểm tra trust/cross-account/cross-project và theo dõi privileged access.

**Nguyên tắc tối thiểu:** runtime chỉ nhận quyền cần để thực hiện nghiệp vụ. Nếu ứng dụng chỉ tải hóa đơn, không cấp cho nó quyền tạo hoặc xóa toàn bộ bucket. Nếu worker chỉ nhận và acknowledge message, không cấp quyền xóa queue.

### 8.2. Network và endpoint

Nhà cung cấp vận hành hạ tầng và các lựa chọn public/private connectivity. Khách hàng cấu hình security group, VPC/VNet, firewall, private endpoint, route, DNS và TLS trong phạm vi kiểm soát. Một endpoint nằm trong mạng riêng vẫn có thể bị khai thác nếu identity, ứng dụng hoặc dữ liệu được quản lý không đúng.

Ngược lại, ứng dụng có IAM/RBAC chính xác vẫn có thể thất bại do firewall, DNS hoặc endpoint sai Region. Cần kiểm tra **network và authorization như hai lớp độc lập**.

### 8.3. Dữ liệu, encryption và secret

Nhóm ứng dụng biết dữ liệu nào là nhạy cảm và cần kiểm soát chúng:

1. **Phân loại dữ liệu:** dữ liệu cá nhân, thanh toán, token, hóa đơn, log và dữ liệu kiểm thử.
2. **Giới hạn quyền:** ai được xem, cập nhật, xóa và export dữ liệu.
3. **Mã hóa:** TLS truyền tải, encryption at rest, lựa chọn key, quyền sử dụng key.
4. **Vòng đời:** giữ dữ liệu bao lâu, xóa ở đâu, có lịch sử phiên bản/backup hay không.
5. **Vị trí:** primary, replica, backup, log và các dịch vụ phụ trợ nằm trong phạm vi địa lý được phép.

Nhiều dịch vụ có encryption at rest mặc định, nhưng chính sách của hệ thống vẫn phải xác định **chế độ mã hóa, quyền, key ownership và mục tiêu bảo vệ**. Không đưa access key, connection string hoặc secret value vào repository, image, log hay tài liệu ví dụ.

### 8.4. Runtime, mã ứng dụng và dependency

Ngay cả trên serverless, nhà cung cấp không tự sửa lỗi SQL injection, SSRF, insecure deserialization hoặc business authorization trong Spring Boot. Nhóm phát triển cần cập nhật Spring Boot/Spring Cloud và các thư viện theo BOM tương thích, quản lý CVE/SBOM, validate đầu vào, kiểm soát outbound requests, xử lý lỗi và log an toàn.

Trên VM, trách nhiệm vá OS/Java phần tự quản lý cao hơn. Trên managed runtime, provider có thể quản lý host và một số runtime; khách hàng vẫn phải biết chính sách chọn runtime version, lifecycle của container image hoặc custom runtime/layer. **Serverless giảm việc quản trị host, không loại bỏ trách nhiệm về code.**

## 9. Độ tin cậy và khả năng khôi phục cũng là trách nhiệm chia sẻ

Nhà cung cấp thường công bố SLA, đặc tính độ bền, HA và các lựa chọn backup/replication. Nhóm ứng dụng phải chọn cấu hình và xây dựng luồng nghiệp vụ có khả năng phục hồi.

| Vấn đề | Khả năng provider cung cấp | Trách nhiệm ứng dụng |
|---|---|---|
| Lỗi một máy/zone | Managed failover, regional HA hoặc redundant storage tùy dịch vụ | Chọn mode phù hợp, loại bỏ single point of failure |
| Lỗi toàn Region | Cross-region replication, secondary resource, failover tools tùy dịch vụ | Thiết kế DR, routing, danh tính và dữ liệu ở region dự phòng |
| Xóa object nhầm | Versioning, soft delete, retention hoặc backup nếu được bật | Bật đúng cấu hình, giới hạn Delete và thử restore |
| Database bị ghi dữ liệu sai | Backup, point-in-time restore theo dịch vụ | Chọn retention, kiểm tra RPO/RTO, restore và sửa logic |
| Message bị xử lý lặp | Semantics giao nhận/ack và dedup tùy dịch vụ | Idempotency, transaction, retry, DLQ và dedup theo nghiệp vụ |
| Gián đoạn API ngắn | Throttling/retry hints, load balancing | Timeout, retry có backoff/jitter, circuit breaker, giới hạn retry |
| Hết quota hoặc tăng chi phí | Metric, quota/billing API, budget alert | Giám sát, đặt cảnh báo, capacity planning, cleanup |

**RTO** là thời gian gián đoạn tối đa mục tiêu khi phục hồi; **RPO** là lượng dữ liệu có thể mất tối đa theo thời gian. HA trong một Region, geo-replication và backup bảo vệ trước các failure mode khác nhau. **Replication không thay thế backup**, vì lỗi logic hoặc dữ liệu bị xóa có thể lan sang bản sao.

~~~mermaid
flowchart TD
    U["Client"] --> LB["Load balancer / service entrypoint"]
    LB --> A["Spring Boot instance A"]
    LB --> B["Spring Boot instance B"]
    A --> DB["Managed database: HA đã cấu hình"]
    B --> DB
    DB -. "Backup/replica theo chính sách" .-> R["Restore / DR target"]
    O["Nhóm ứng dụng + platform"] --> T["Kiểm thử failover, restore, RTO/RPO"]
    T --> DB
    T --> R
~~~

Một dịch vụ có SLA cao không tự đảm bảo **end-to-end application SLO**: lỗi trong code, network, database schema, credential hoặc dependency vẫn có thể gây downtime. Cần định nghĩa và đo SLO của cả luồng người dùng, không chỉ trạng thái “healthy” của một managed service.

## 10. Tách trách nhiệm giữa IaC, Spring Boot và vận hành

Ví dụ hệ thống đơn hàng sử dụng object storage để lưu hóa đơn, message broker để xử lý đơn, managed database và secret manager để lấy thông tin kết nối.

~~~mermaid
flowchart LR
    SEC["Security / Platform: guardrails"] --> PIPE["IaC + deployment pipeline"]
    PIPE --> MGMT["Resource management APIs"]
    MGMT --> RES["Bucket, queue/topic, DB, secret"]
    APP["Spring Boot runtime"] --> ID["Workload identity"]
    ID --> DATA["Data APIs / JDBC"]
    DATA --> RES
    OPS["Operations: monitoring + restore"] --> RES
    SEC -. "Policy và review" .-> APP
~~~

Một cách phân công dễ kiểm chứng:

- **Platform/IaC:** tạo tài nguyên đúng account/subscription/project và Region, hạn chế truy cập công khai, cấu hình encryption, network, backup/replication và gán role workload.
- **Development/Spring Boot:** dùng resource ID đã cấp, kiểm tra authorization nghiệp vụ, validate input, xử lý retry/idempotency, giữ secret an toàn, cập nhật dependency và viết test.
- **Security:** định nghĩa policy/guardrail, chuẩn định danh, yêu cầu data residency, logging và rà soát quyền.
- **Operations/SRE:** giám sát, cảnh báo, xử lý incident, diễn tập khôi phục, xác minh RTO/RPO và quản lý vòng đời tài nguyên.
- **Data owner/business:** xác định dữ liệu nào được lưu, ai được phép truy cập, retention và hậu quả chấp nhận được khi dữ liệu mất hoặc gián đoạn.

Các nhiệm vụ có thể do một nhóm nhỏ kiêm nhiệm. Điều quan trọng là **mỗi kiểm soát đều có chủ sở hữu và bằng chứng hoạt động**. Không để một việc rơi vào khoảng trống giữa “cloud lo rồi” và “team khác lo”.

### 10.1. Kiểm soát phải gắn với bằng chứng

| Kiểm soát | Chủ sở hữu dự kiến | Bằng chứng cần thu thập |
|---|---|---|
| Runtime không có quyền tạo/xóa bucket | Platform + security | IAM/RBAC review, policy test trên staging |
| Hóa đơn được bảo vệ theo yêu cầu | Development + data owner | Kiểm thử authorization, metadata encryption, access logs |
| Secret không xuất hiện trong source/log | Development + security | Secret scan, review log, integration tests |
| Queue xử lý lặp an toàn | Development | Integration test duplicate/retry, metric DLQ |
| Database khôi phục đúng RPO/RTO | Operations + platform | Báo cáo restore rehearsal, backup configuration |
| Resource nằm trong khu vực được phép | Platform + compliance | IaC policy, resource location/replication inventory |
| Chi phí không tăng mất kiểm soát | Platform + operations | Budget, alert, billing dashboard và quy trình phản hồi |

## 11. Ví dụ kỹ thuật: tích hợp S3 trong Spring Boot an toàn theo trách nhiệm

Giả sử pipeline đã tạo bucket **orders-prod-invoices** tại region **ap-southeast-1**, cấu hình chính sách bảo mật và gán IAM role cho runtime. Spring Boot chỉ cần đọc/ghi object trong một prefix thuộc ứng dụng.

### 11.1. Cấu hình ứng dụng

~~~yaml
app:
  storage:
    bucket: orders-prod-invoices
    region: ap-southeast-1
    object-prefix: invoices/
~~~

Đây là **property do ứng dụng định nghĩa**, không phải cấu hình mặc định cho tất cả phiên bản Spring Cloud AWS. Phải bind và validate chúng trong code. Không đưa access key và secret key vào file này hoặc image container.

### 11.2. Bean client AWS SDK v2

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
public class StorageClientConfiguration {

    @Bean
    S3Client s3Client(@Value("${app.storage.region}") String region) {
        return S3Client.builder()
                .region(Region.of(region))
                .build();
    }
}
~~~

AWS SDK v2 mặc định dùng **credential provider chain** để tìm credential thích hợp; trên môi trường AWS nên ưu tiên IAM role/workload identity với credential ngắn hạn. Mã ví dụ cần dependency AWS SDK v2 S3 và thiết lập Spring Boot phù hợp. Cách Spring Cloud AWS auto-configure client, property và starter phụ thuộc phiên bản, nên tránh khai báo hai bean client không chủ ý và chọn BOM tương thích.

Phần ứng dụng **không cần** gọi CreateBucket khi khởi động và không cần quyền sửa bucket policy. Nếu áp dụng prefix theo tenant, code còn phải kiểm tra tenant identity và ngăn user tùy ý chọn key ngoài phạm vi được phép.

### 11.3. IAM tối thiểu cho thao tác object

Ví dụ IAM policy dưới đây minh họa quyền **GetObject/PutObject** trong đúng prefix; cần điều chỉnh theo dữ liệu và method SDK thực tế.

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::orders-prod-invoices/invoices/*"
    }
  ]
}
~~~

Policy này **không tự cấp** CreateBucket, DeleteBucket, PutBucketPolicy, ListBucket hay DeleteObject. Nếu ứng dụng dùng SSE-KMS với key riêng hoặc multipart/other APIs, có thể cần thêm permission. Bên cạnh role policy, phải kiểm tra bucket policy, KMS key policy, explicit deny và các ràng buộc cấp tổ chức. Giới hạn prefix ở IAM không thay thế **authorization nghiệp vụ** xác định user được đọc hóa đơn nào.

### 11.4. Tương đương về ý tưởng trên Azure và Google Cloud

| Mục tiêu | AWS | Azure | Google Cloud |
|---|---|---|---|
| Danh tính runtime | IAM role / workload identity | Managed identity | Service account / Workload Identity |
| Quyền đọc object | s3:GetObject trên object ARN | Storage Blob Data Reader tại container/scope phù hợp | Storage Object Viewer trên bucket |
| Quyền gửi message | sqs:SendMessage cho queue | Service Bus Data Sender cho namespace/queue thích hợp | Pub/Sub Publisher trên topic |
| Quyền đọc secret | secretsmanager:GetSecretValue | Quyền secret data phù hợp với RBAC/access policy Key Vault | Secret Manager Secret Accessor |
| Quản lý tạo tài nguyên | IAM role CI/CD riêng | Azure RBAC/IaC identity riêng | IAM provisioning service account riêng |

Bảng cho thấy **ý tưởng phân quyền**, không phải các role tương đương hoàn toàn về phạm vi và khả năng. Mỗi phương pháp xác thực, scope kế thừa, endpoint, encryption key, API và version SDK có khác biệt. Với Azure Blob dùng Entra, cần role **data plane**; với GCP, quyền xem metadata bucket không tự chứng minh quyền đọc object.

## 12. Quy trình bảo mật và kiểm thử tích hợp

### 12.1. Kiểm thử tích cực và tiêu cực

Trong test environment cô lập, nên thực hiện cả hai nhóm:

| Trường hợp | Kết quả mong muốn | Trách nhiệm chứng minh |
|---|---|---|
| Workload upload hóa đơn vào đúng bucket/container | Thành công | Dev + platform: quyền data, endpoint, encoding, retry |
| Workload đọc hóa đơn ngoài tenant/scope | Bị từ chối | Dev: business authorization; platform: scope resource |
| Workload tạo hoặc xóa bucket | Bị từ chối nếu nghiệp vụ không cần | Platform/security: quyền control plane tối thiểu |
| Worker xử lý cùng message hai lần | Không gây hai giao dịch nghiệp vụ ngoài ý muốn | Dev: idempotency, transaction và retry |
| Workload lấy secret thử nghiệm đúng phạm vi | Thành công, không log giá trị | Dev/platform: IAM/RBAC, network, secret handling |
| DB user gọi bảng không được cấp quyền | Bị từ chối | DBA/dev: SQL grants và phân quyền dữ liệu |
| Resource bị xóa/ghi đè nhầm trên staging | Có thể phục hồi đúng mục tiêu | Platform/operations: versioning, backup, restore |
| Service trong một AZ/instance bị gián đoạn | Phục hồi theo SLO đã đặt | SRE/platform: HA, routing và runbook |

Chỉ kiểm thử “upload thành công” không chứng minh bucket được bảo vệ trước truy cập công khai hoặc xóa nhầm. Chỉ bật backup không chứng minh khôi phục được. Vì thế cần kiểm tra cả **đường thành công**, **đường bị từ chối** và **khả năng phục hồi**.

### 12.2. Ba lớp kiểm tra

1. **Trong code:** unit test business authorization, input validation, idempotency, exception handling và không log secret. Quét dependency/secret trước build.
2. **Trong pipeline/IaC:** policy-as-code, kiểm tra public exposure, IAM scope, encryption, location, backup, tags/labels và budget. Dùng identity triển khai riêng.
3. **Trong cloud staging:** test runtime identity thật, private/public endpoints, quota, fault handling, backup restore, metric/alert và audit trail.

Mock/emulator chỉ giúp kiểm tra logic tích hợp; nó **không xác minh** điều kiện IAM/RBAC, network thực, data residency, backup service hay SLA của cloud provider. Để có bằng chứng vận hành, phải thử trên tài nguyên cloud có phạm vi và chi phí được kiểm soát.

### 12.3. Tín hiệu cần quan sát

Đối với từng dịch vụ, nên có các tín hiệu về 403/PermissionDenied, authentication failures, 429/throttling, latency p95/p99, queue backlog/DLQ, lỗi database connection, replication lag, backup job/restore, disk/quota, chi phí và thay đổi IAM/resource policy. Lưu request ID, trace ID và resource ID đã lọc; **không log token, secret payload hoặc dữ liệu cá nhân không cần thiết**.

Nếu một cloud provider cung cấp logging service, đó mới là **khả năng** quan sát. Nhóm vận hành phải bật các log cần thiết, cấu hình quyền truy cập log, retention, alert rule và người chịu trách nhiệm phản hồi. Không nên cho rằng mọi data access đã được audit chỉ vì có bật log quản trị.

## 13. Tình huống thực tế và cách xác định trách nhiệm

### Tình huống A: bucket hoạt động nhưng rò rỉ hóa đơn

Spring Boot upload hóa đơn vào bucket và không có lỗi. Sau đó phát hiện policy truy cập công khai quá rộng hoặc ứng dụng trả URL không cần xác thực. Provider có thể đã vận hành object storage đúng cam kết; nguyên nhân nằm ở **cấu hình quyền, phân quyền nghiệp vụ và quy trình review**. Cần giới hạn quyền, chặn public access theo yêu cầu, kiểm tra lịch sử truy cập và rà soát các URL đã phát hành; đội ứng dụng/platform chịu trách nhiệm xác minh biện pháp.

### Tình huống B: Azure SQL khỏe nhưng người dùng không thể đặt hàng

Azure SQL Database báo trạng thái dịch vụ bình thường nhưng connection pool của Spring Boot cạn hoặc migration làm khóa bảng. Đây là vấn đề vận hành ứng dụng/database workload: cần điều tra connection management, query, schema migration, timeout, retry và khả năng rollback. Đội platform cùng provider chỉ tham gia ở những lớp liên quan đến hạ tầng hay sự cố dịch vụ.

### Tình huống C: Cloud Run scale được nhưng Pub/Sub tạo nhiều giao dịch

Khi consumer bị retry sau timeout, một event có thể được xử lý lại. Pub/Sub có semantics giao nhận theo chế độ và sản phẩm; **consumer phải thiết kế idempotency**. Nếu một message trùng tạo hai hóa đơn, đội ứng dụng cần sửa transaction/dedup key và test lại, không kỳ vọng nền tảng serverless tự giải quyết tính đúng đắn nghiệp vụ.

### Tình huống D: KMS key bị vô hiệu hóa làm dữ liệu không đọc được

Dữ liệu mã hóa vẫn nằm trong managed storage, nhưng key cần thiết không còn khả dụng hoặc workload bị thu hồi quyền decrypt. Provider có thể vận hành cả storage và KMS bình thường; sự cố nằm ở **key lifecycle, policy và kế hoạch phục hồi** do khách hàng cấu hình. Giải pháp là kiểm soát thay đổi key, tách quyền quản trị và sử dụng key, cùng diễn tập phục hồi.

### Tình huống E: một Region lỗi và dịch vụ không chuyển sang DR

Cloud có thể cung cấp tính năng backup, replication và failover nhưng workload chưa bật hoặc thiếu endpoint, IAM, database replica, secret hoặc DNS ở Region dự phòng. Trách nhiệm thiết kế RTO/RPO và diễn tập chuyển vùng thuộc chủ sở hữu hệ thống; provider chịu trách nhiệm với hạ tầng và tính năng đã cam kết. Phải đọc điều khoản riêng của từng dịch vụ thay vì mặc định “multi-AZ” tương đương “multi-region”.

## 14. Những hiểu lầm cần tránh

| Nhận định sai | Cách hiểu đúng |
|---|---|
| “Dùng managed database nên không cần backup/restore test” | Provider cung cấp tính năng; khách hàng vẫn chọn retention, bảo đảm restore và mục tiêu dữ liệu |
| “Cloud đã mã hóa nên chắc chắn không thể rò rỉ dữ liệu” | Encryption không thay IAM, authorization, phân loại và kiểm soát export |
| “Dùng serverless thì provider vá cả mã Java và dependency của mình” | Host/runtime nền có thể do provider quản lý; code, package và lựa chọn runtime vẫn phải kiểm soát |
| “Tài nguyên trong private network thì không cần IAM” | Network isolation và authorization là hai lớp độc lập |
| “Một role Contributor/Owner là cách nhanh nhất để hết 403” | Phải tìm operation và permission cần thiết, cấp đúng scope, kiểm tra thêm network và endpoint |
| “Có region/zone redundancy thì không thể mất dữ liệu” | Lỗi logic, xóa nhầm, corruption và những failure mode khác vẫn cần backup, restore |
| “Cloud provider có log nghĩa là đã giám sát an toàn” | Cần bật, giữ, bảo vệ, phân tích log và đặt cảnh báo/phản hồi |
| “Provider có chứng nhận compliance nên ứng dụng tự compliant” | Chứng nhận có phạm vi; khách hàng vẫn phải chứng minh cấu hình và cách xử lý dữ liệu |
| “CI/CD và runtime có thể dùng chung admin credential cho tiện” | Tách principal giúp hạn chế blast radius và audit đúng hành động |
| “Shared fate nghĩa là Google chịu hết trách nhiệm khi dùng GCP” | Vẫn cần trách nhiệm khách hàng về data, identity, code, config và vận hành |

## 15. Checklist triển khai có thể kiểm chứng

Trước khi đưa một tích hợp Spring Boot với AWS/Azure/GCP lên production, hãy xác minh:

- **Ranh giới dịch vụ:** loại IaaS/managed/container/serverless; provider quản lý đến lớp nào, khách hàng còn điều khiển lớp nào.
- **Phân công:** mỗi kiểm soát có người sở hữu rõ ràng giữa development, platform, security, SRE và chủ sở hữu dữ liệu.
- **Danh tính:** CI/CD và runtime dùng principal tách biệt; IAM/RBAC chỉ cấp quyền dữ liệu và quản trị thực sự cần.
- **Mã ứng dụng:** BOM Spring Cloud tương thích Spring Boot, xử lý input, authorization, retry, idempotency, dependency và log an toàn.
- **Storage/messaging/database:** kiểm tra quyền, retention, versioning/soft delete, retry/DLQ, schema grants, backup và restore.
- **Secret và encryption:** secret không nằm trong code, rotation và quyền đọc được kiểm soát, key lifecycle có quy trình thay đổi.
- **Network/location:** endpoint, Region, private/public access, DNS/TLS, data residency của bản chính/bản sao/backup và log.
- **Bằng chứng:** có kiểm thử tích cực/tiêu cực trên staging, policy review, audit trail, restore rehearsal, alert và runbook.
- **Độ tin cậy:** mục tiêu RTO/RPO/SLO được định nghĩa và đo bằng kịch bản failure thực tế.
- **Chi phí:** có budget, quota và trách nhiệm theo dõi replication, egress, log retention và tài nguyên không sử dụng.

## 16. Tổng kết

Mô hình trách nhiệm chia sẻ giúp trả lời **ai phải thực hiện và kiểm chứng biện pháp nào** khi triển khai ứng dụng trên cloud. AWS, Azure và Google Cloud quản lý nhiều lớp hạ tầng và dịch vụ managed, nhưng **dữ liệu, danh tính, phân quyền, cấu hình tài nguyên, bảo mật mã ứng dụng, tính đúng đắn nghiệp vụ và kế hoạch khôi phục** vẫn cần được nhóm khách hàng chủ động thực hiện theo ranh giới từng dịch vụ.

Khi tích hợp Spring Boot với Spring Cloud AWS, Spring Cloud Azure hoặc Spring Cloud GCP, hãy biến mô hình này thành danh mục **resource → thao tác → principal → quyền → cấu hình bảo vệ → chủ sở hữu → bằng chứng kiểm tra**. Có danh mục đó, đội phát triển có thể sử dụng sức mạnh của managed services mà vẫn kiểm soát được an toàn dữ liệu, khả năng phục hồi và trách nhiệm vận hành của chính mình.
