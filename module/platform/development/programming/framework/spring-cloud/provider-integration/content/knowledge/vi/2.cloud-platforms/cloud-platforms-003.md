# Phân biệt API quản lý tài nguyên và API truy cập dữ liệu

Một ứng dụng Spring Boot có thể **tạo được storage account nhưng không đọc được blob**, hoặc **xem được thông tin database nhưng không truy vấn được một hàng dữ liệu**. Trường hợp ngược lại cũng xảy ra: ứng dụng đọc và ghi object thành công nhưng không được phép tạo bucket mới. Nguyên nhân thường nằm ở việc nhầm lẫn hai nhóm thao tác có mục đích, quyền và cơ chế kết nối khác nhau: **API quản lý tài nguyên (management/control plane)** và **API truy cập dữ liệu (data plane)**.

Trong chương **Nền tảng đám mây**, bài học này thuộc mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với các dịch vụ managed trên **AWS, Azure và Google Cloud** bằng các thư viện Spring Cloud tương ứng. Hiểu rõ hai loại API giúp phân quyền tối thiểu, quản lý storage, messaging, database và secret đúng cách, bảo vệ thông tin xác thực, thiết kế kiểm thử tích hợp đáng tin cậy và so sánh chính xác các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Nhận diện một thao tác thuộc quản lý tài nguyên, truy cập dữ liệu, hay nằm ở ranh giới phụ thuộc từng dịch vụ.
- Phân biệt **resource provisioning**, **configuration**, **IAM/policy** với **runtime data operations**.
- Hiểu cách AWS, Azure và Google Cloud tổ chức API, quyền, endpoint và SDK cho hai nhóm thao tác.
- Giải thích vì sao xác thực thành công hoặc có quyền quản trị metadata chưa đủ để đọc, ghi object, message, hàng dữ liệu hay secret.
- Thiết kế mô hình **CI/CD hoặc Infrastructure as Code (IaC) quản lý tài nguyên; ứng dụng Spring Boot sử dụng tài nguyên** với quyền tối thiểu.
- Tách kiểm thử control plane và data plane; điều tra lỗi IAM/RBAC, network, endpoint, Region, quota và policy đúng ngữ cảnh.

## 2. Control plane và data plane là gì?

### 2.1. Management/control plane

**Control plane** là tập chức năng để **tạo, cấu hình, liệt kê, thay đổi hoặc xóa tài nguyên và các thuộc tính quản trị**. Ví dụ:

- Tạo bucket, storage account, queue, database instance hoặc secret.
- Thay đổi khả năng replication, network access, retention, encryption hoặc cấu hình throughput.
- Xem metadata triển khai: vị trí, trạng thái, quota, cấu hình dịch vụ.
- Cấp/thu hồi quyền, gắn policy, quản lý danh tính hay gán vai trò.
- Bật một API dịch vụ, tạo project hoặc thiết lập chính sách ở cấp tổ chức.

Các thao tác này thường do **platform team, IaC, pipeline triển khai hoặc nhân sự vận hành** thực hiện. Tuy nhiên, không phải mọi thao tác cấu hình đều có một endpoint quản lý riêng; cách phân loại cụ thể tùy dịch vụ.

### 2.2. Data plane

**Data plane** là tập chức năng để **xử lý dữ liệu hoặc thực thi tác vụ nghiệp vụ trên tài nguyên đã tồn tại**. Ví dụ:

- Đọc, ghi, xóa một object trong bucket/container.
- Gửi hoặc nhận message từ queue/topic/subscription.
- Thực thi câu lệnh SQL trên database.
- Truy cập giá trị secret được quản lý.
- Ghi hoặc truy vấn bản ghi trong một kho dữ liệu.

Trong ứng dụng Spring Boot, phần lớn request nghiệp vụ nên dùng **data plane** trên các tài nguyên đã được tạo và cấp quyền phù hợp.

### 2.3. Phân biệt qua mục đích của thao tác

| Câu hỏi | Management/control plane | Data plane |
|---|---|---|
| Mục đích chính | Tạo, cấu hình, quản lý vòng đời và chính sách tài nguyên | Đọc/ghi/xử lý dữ liệu nghiệp vụ |
| Chủ thể thường gọi | IaC, CI/CD, platform/admin | Ứng dụng, worker, consumer, job |
| Ví dụ storage | Tạo bucket/storage account, bật replication | Upload/download object/blob |
| Ví dụ messaging | Tạo queue/topic, cấu hình retry hoặc retention | Publish/send, pull/receive, acknowledge |
| Ví dụ database | Tạo instance, cấu hình backup/HA | Kết nối JDBC và chạy SQL |
| Ví dụ secret | Tạo secret và cấu hình replication/policy | Đọc phiên bản secret để kết nối dịch vụ |
| Rủi ro đặc trưng | Phá hủy hoặc đổi cấu hình toàn bộ tài nguyên | Lộ, sửa, xóa hoặc làm sai dữ liệu |
| Quyền tối thiểu | Các hành động quản lý đúng resource và vòng đời | Các hành động dữ liệu cụ thể trên resource |
| Kiểm thử | Tạo/đổi cấu hình, kiểm tra policy và lifecycle | Ghi/đọc/nhận, giao dịch, quyền dữ liệu |

> **Quy tắc nhận diện:** “Tôi đang điều khiển *tài nguyên nào tồn tại và vận hành ra sao*?” thường là control plane. “Tôi đang *sử dụng tài nguyên để xử lý dữ liệu*?” thường là data plane.

Ranh giới này mang tính **chức năng**, không đồng nghĩa “control plane luôn dùng REST, data plane luôn dùng TCP”. Data plane có thể dùng REST, gRPC, AMQP, JDBC hoặc giao thức khác. Một API/SDK/endpoint có thể chứa **cả thao tác quản lý lẫn thao tác dữ liệu**. Cũng có các thao tác nằm ở ranh giới: liệt kê tên object, xem queue attributes, quản lý version secret hoặc quản lý schema. Hãy dựa trên **mục đích và permission cụ thể của nhà cung cấp**, không chỉ tên phương thức.

## 3. Cùng một ứng dụng, hai luồng công việc khác nhau

Hãy xét một hệ thống đơn hàng có Spring Boot API, một hàng đợi xử lý đơn và object storage chứa hóa đơn:

~~~mermaid
flowchart TD
    Dev["Developer / Platform team"] --> CI["CI/CD + IaC"]
    CI --> CP["Management API / control plane"]
    CP --> R["Bucket, queue, database, secret"]
    App["Spring Boot REST API"] --> DP["Data API / data plane"]
    Worker["Spring Boot worker"] --> DP
    DP --> R
    I1["Deployment identity"] -. "Quyền quản lý có giới hạn" .-> CP
    I2["Runtime identity"] -. "Quyền dữ liệu tối thiểu" .-> DP
~~~

**Trước khi triển khai:** pipeline tạo các tài nguyên, cấu hình Region, encryption, backup, private network, gán role cho workload. Đây là các thao tác control plane.

**Trong khi ứng dụng chạy:** API ghi object hóa đơn và gửi message; worker nhận message, cập nhật database, đọc secret khi cần. Đây là data plane.

**Khi vận hành:** platform team có thể thay đổi retention của queue hoặc tăng khả năng dự phòng của database qua control plane, trong khi ứng dụng tiếp tục sử dụng data plane. Cần kiểm tra thay đổi cấu hình có gián đoạn hoặc ảnh hưởng dữ liệu hay không.

Một quyền cho phép **tạo bucket** không nhất thiết cho phép **đọc object bên trong**. Một quyền **đọc object** không nhất thiết cho phép **đổi policy, xóa bucket hoặc tạo tài nguyên mới**. Tách hai danh tính giúp giảm phạm vi thiệt hại khi ứng dụng bị xâm nhập.

## 4. AWS: ranh giới theo IAM action và loại tài nguyên

### 4.1. Không có một endpoint quản lý chung cho mọi AWS service

AWS có các API theo từng dịch vụ. Ví dụ Amazon S3 SDK/CLI chứa thao tác ở cả hai nhóm:

| Dịch vụ | Ví dụ management/control plane | Ví dụ data plane |
|---|---|---|
| Amazon S3 | CreateBucket, PutBucketVersioning, PutBucketReplication | PutObject, GetObject, DeleteObject |
| Amazon SQS | CreateQueue, SetQueueAttributes | SendMessage, ReceiveMessage, DeleteMessage |
| Amazon SNS | CreateTopic, SetTopicAttributes | Publish |
| Amazon RDS | CreateDBInstance, ModifyDBInstance, DescribeDBInstances | SQL qua JDBC/PostgreSQL/MySQL protocol tới endpoint DB |
| AWS Secrets Manager | CreateSecret, UpdateSecret, PutResourcePolicy | GetSecretValue, ứng dụng đọc phiên bản secret |
| Amazon DynamoDB | CreateTable, UpdateTable | GetItem, PutItem, Query, UpdateItem |

Một số thao tác như **ListBuckets/ListObjectsV2**, **DescribeQueue**, **DescribeTable**, **PutSecretValue** có thể phục vụ quản trị hoặc nghiệp vụ tùy ngữ cảnh. Bảng chỉ phân loại ví dụ điển hình; điều quyết định về bảo mật là **IAM action chính xác** mà request yêu cầu.

Đặc biệt, **RDS API quản lý DB instance không phải giao thức truy vấn SQL**. Một IAM principal có thể gọi DescribeDBInstances nhưng vẫn không thể đăng nhập database. Kết nối JDBC phải thông qua xác thực database hoặc cơ chế IAM database authentication được engine/dịch vụ hỗ trợ và cấu hình, cùng network, TLS và quyền bên trong DB.

### 4.2. IAM cho hai loại thao tác

Trong AWS, chính sách có **Action**, **Resource** và có thể có **Condition**. Ví dụ dưới đây chỉ minh họa các quyền dữ liệu S3 cho workload ghi và đọc object trong một bucket cụ thể:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::orders-prod-invoices/*"
    }
  ]
}
~~~

Chính sách này không cấp **s3:CreateBucket**, **s3:PutBucketPolicy**, **s3:DeleteBucket** hay mặc định cấp **s3:ListBucket**. Tùy SDK và nghiệp vụ, có thể cần các quyền bổ sung (ví dụ multipart upload, KMS key, list), nhưng không nên cấp rộng khi chưa xác minh nhu cầu.

Để policy thực sự có hiệu lực, còn phải xét **role trust policy**, bucket/resource policy, permission boundary, session policy, service control policy (SCP), explicit deny và các cơ chế bảo vệ liên quan. SCP thường đặt **giới hạn tối đa**, không tự cấp quyền. Bucket ở account khác hoặc KMS key riêng có thể yêu cầu cấu hình quyền bổ sung.

### 4.3. Kiểm tra AWS qua CLI

Ví dụ quản lý hoặc xem metadata tài nguyên:

~~~bash
aws sts get-caller-identity
aws s3api get-bucket-location --bucket orders-prod-invoices
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-prod \
  --attribute-names QueueArn
~~~

Ví dụ gọi data plane để đọc object (nếu có quyền):

~~~bash
aws s3api head-object \
  --bucket orders-prod-invoices \
  --key example-invoice.pdf
~~~

Lệnh **HeadObject** lấy metadata của **một object** qua data API; nó không tải body. Trong S3, quyền yêu cầu và mã lỗi có thể phụ thuộc tình huống (ví dụ bucket policy, quyền GetObject, quyền ListBucket khi object không tồn tại). Vì vậy, không thể suy luận nguyên nhân từ một mã 403/404 duy nhất. Các tên account, bucket, queue và object trong ví dụ cần thay bằng tài nguyên thực tế.

### 4.4. SDK Spring Cloud AWS và quyền runtime

Spring Cloud AWS cung cấp tích hợp cho các dịch vụ AWS tùy phiên bản và starter. Workload có thể lấy credential ngắn hạn qua IAM role của EC2, ECS, EKS hoặc môi trường chạy tương ứng. **Không nên gắn quyền tạo/xóa bucket hoặc sửa bucket policy cho Spring Boot service chỉ để upload file.**

Nếu ứng dụng được yêu cầu tạo một resource động lúc chạy (ví dụ hệ thống SaaS cấp một queue cho mỗi tenant), đó là **ngoại lệ kiến trúc có chủ đích**: cần kiểm soát namespace, quota, naming, điều kiện IAM và audit; không dùng role quản trị vô hạn.

## 5. Azure: management plane và data plane tách khá rõ

### 5.1. Azure Resource Manager (ARM)

Trong Azure, nhiều tác vụ quản lý tài nguyên đi qua **Azure Resource Manager** với endpoint quản lý thông dụng **management.azure.com**. Ví dụ:

- Tạo hoặc sửa **storage account**.
- Tạo **Service Bus namespace**, cấu hình thuộc tính và một số thực thể con qua ARM.
- Tạo **Key Vault resource**, cấu hình network/RBAC.
- Tạo **Azure SQL logical server/database**, thay đổi SKU hoặc cấu hình vận hành.

Trong khi đó, các data endpoint thường là endpoint **riêng của dịch vụ**:

| Dịch vụ | Management plane | Data plane |
|---|---|---|
| Azure Blob Storage | Quản lý storage account, redundancy, networking bằng ARM | Đọc/ghi blob tại endpoint kiểu **account.blob.core.windows.net** |
| Azure Service Bus | Tạo namespace, thay đổi thuộc tính qua ARM hoặc API quản lý được hỗ trợ | Gửi/nhận message tại namespace endpoint qua AMQP/SDK |
| Azure Key Vault | Tạo vault, cập nhật cấu hình ARM | Đọc/ghi secret, key operation tại endpoint kiểu **vault.vault.azure.net** |
| Azure SQL Database | Tạo/quản lý server, database, firewall, SKU bằng ARM | Thực thi SQL trên kết nối database |
| Azure Cosmos DB | Tạo account, database/container qua cơ chế quản trị được hỗ trợ | Đọc/ghi document/item qua SDK và data endpoint |

Một vài dịch vụ cho phép quản lý các thực thể con qua **API hoặc client SDK phục vụ chính dịch vụ**. Do đó, không thể kết luận “mọi management action trên Azure đều chỉ có tại management.azure.com”. Phân biệt theo **hành động và quyền** vẫn là cách đáng tin cậy hơn.

### 5.2. Azure RBAC: role quản trị và role dữ liệu

Azure RBAC hỗ trợ scope **management group → subscription → resource group → resource**, cùng các role cho hoạt động quản trị và dữ liệu. Role **Reader** trên một storage account thường cho phép xem thông tin quản lý, **không tự cấp quyền đọc nội dung blob bằng Microsoft Entra authentication**.

Ví dụ để Spring Boot đọc blob bằng danh tính Microsoft Entra, workload thường cần role **Storage Blob Data Reader** tại container/storage account hoặc phạm vi phù hợp. Để ghi blob, role thường phù hợp là **Storage Blob Data Contributor** tùy yêu cầu. Một service muốn xem cấu hình storage account có thể cần quyền **management-plane Reader**, nhưng không nhất thiết cần data access.

Lưu ý đặc biệt: các role quản trị có quyền **liệt kê hoặc lấy storage account key** có thể mở đường truy cập data plane bằng shared key, tùy cấu hình vô hiệu hóa Shared Key và chính sách dịch vụ. Vì vậy không thể giả định “quyền management không bao giờ gián tiếp dẫn đến quyền data”. Kiểm soát **ListKeys**, SAS, key rotation và ưu tiên cơ chế Microsoft Entra/RBAC khi thích hợp.

Với **Key Vault**, quyền data plane phụ thuộc mô hình phân quyền vault đã chọn (**Azure RBAC** hoặc **vault access policy** ở môi trường còn sử dụng). Role quản trị vault trong ARM không mặc nhiên có quyền đọc giá trị secret. Cấp quyền đúng **secret read** cho managed identity của workload, tránh đưa secret vào logs.

### 5.3. CLI xác minh hai plane

Ví dụ quản lý: lấy thuộc tính storage account bằng ARM:

~~~bash
az account show --query "{tenant:tenantId,subscription:id}"
az storage account show --name ordersprod \
  --resource-group rg-orders-prod \
  --query "{name:name,location:location,sku:sku.name}"
~~~

Ví dụ data: liệt kê blob theo quyền đăng nhập Microsoft Entra:

~~~bash
az storage blob list \
  --account-name ordersprod \
  --container-name invoices \
  --auth-mode login \
  --query "[].name" --output table
~~~

Truy vấn ARM thành công **không chứng minh** lệnh dữ liệu sẽ thành công; lệnh dữ liệu cần data-plane role và network access phù hợp. Phiên Azure CLI local thường dùng danh tính người dùng; Spring Boot chạy trên App Service, AKS hoặc VM có thể dùng **managed identity** khác và cần gán role riêng.

Một hệ thống có thể cho phép kết nối ARM qua mạng nhưng chặn Blob endpoint bằng firewall hoặc private endpoint. **Network policy và RBAC là hai lớp khác nhau**; nếu token hợp lệ và role phù hợp nhưng request bị chặn mạng, thêm quyền không giải quyết vấn đề.

## 6. Google Cloud: có thể chung service endpoint nhưng khác permission

### 6.1. Organization/project và API service

Google Cloud cung cấp **Cloud Resource Manager**, **Service Usage API**, **IAM** và nhiều API quản lý theo dịch vụ để tạo project, bật API, quản lý quyền và tài nguyên. Data plane thường nằm trong chính các service API/SDK hoặc giao thức của tài nguyên.

| Dịch vụ | Management/control plane | Data plane |
|---|---|---|
| Cloud Storage | Tạo bucket, cập nhật location/retention/lifecycle/IAM | Upload/download object, đọc/ghi object |
| Pub/Sub | Tạo topic/subscription, cấu hình retention/filters/policy | Publish messages, pull/acknowledge messages |
| Cloud SQL | Cloud SQL Admin API tạo instance, đặt backup/HA/users theo chức năng hỗ trợ | SQL qua PostgreSQL/MySQL/SQL Server protocol trên kết nối DB |
| Secret Manager | CreateSecret, UpdateSecret, cấu hình replication/IAM | AccessSecretVersion để lấy payload secret |
| BigQuery | Tạo dataset/table, cập nhật policy/cấu hình | Submit query job, đọc/ghi bảng theo cơ chế BigQuery |
| Firestore | Quản lý database/index/TTL theo API quản trị | Đọc/ghi document và transaction |

Với **Cloud Storage**, cả thao tác bucket lẫn object có thể dùng cùng SDK/client hoặc các endpoint API liên quan. Với **Pub/Sub**, thao tác tạo topic và publish message có thể nằm trong cùng API surface. Với **Secret Manager**, method tạo secret và method đọc payload secret cùng thuộc service API, nhưng quyền IAM khác nhau. Do đó, **không thể phân biệt control/data chỉ bằng hostname, tên SDK hoặc việc request dùng REST/gRPC**.

### 6.2. IAM permission và project scope

Google Cloud IAM áp dụng chính sách theo tổ chức, folder, project hoặc resource tùy dịch vụ. Ví dụ quyền **storage.buckets.create** khác với **storage.objects.get** hoặc **storage.objects.create**. Một workload chỉ cần tải object xuống không nhất thiết được cấp quyền tạo bucket.

Ví dụ service account Spring Boot có role **Storage Object Viewer** trên bucket cụ thể để đọc object. Với Pub/Sub, publisher và subscriber thường cần các role/permission khác nhau và gắn vào đúng topic/subscription. Nếu resource ở project B còn workload ở project A, cần kiểm tra principal thực tế và policy trên resource **đích**; cùng organization không tự cho phép truy cập.

Một project dùng Google Cloud API còn phải đáp ứng điều kiện bật API liên quan, quota, billing khi áp dụng, network restrictions, encryption key và organization policy. Role đúng không bảo đảm request thành công nếu dịch vụ chưa bật hoặc policy cấp tổ chức ngăn cản.

### 6.3. CLI xác minh chức năng

Ví dụ quản lý tài nguyên:

~~~bash
gcloud config get-value project
gcloud storage buckets describe gs://orders-prod-invoices \
  --format="yaml(name,location,storageClass)"
gcloud pubsub topics describe orders-events
~~~

Ví dụ truy cập dữ liệu, chỉ liệt kê object (không tải nội dung):

~~~bash
gcloud storage ls gs://orders-prod-invoices/
~~~

Kết quả phụ thuộc IAM permission của tài khoản/credential hiện tại. Quyền liệt kê object khác quyền tải object cụ thể; **đọc danh sách tên** cũng là một loại truy cập dữ liệu cần được hạn chế nếu tên object chứa thông tin nhạy cảm. Quyền gắn ở project có thể quá rộng so với nhu cầu một bucket.

Nếu Spring Boot chạy trên Cloud Run hoặc GKE, xác minh **service account của runtime**. Tài khoản active trong gcloud, Application Default Credentials (ADC) ở máy local và service account trên môi trường chạy có thể khác nhau.

## 7. Không nhầm API surface, SDK và endpoint với quyền

Một đối tượng có thể được quản lý và sử dụng bằng **cùng một client SDK**. Ngược lại, cùng một database có thể có **hai bộ API hoàn toàn khác nhau**: API tạo instance và JDBC thực thi SQL. Vì vậy, phương pháp suy luận đúng là đi từ **thao tác → resource → principal → permission → endpoint/network**.

~~~mermaid
flowchart TD
    R["Ứng dụng yêu cầu một thao tác"] --> Q{"Mục đích thao tác?"}
    Q -->|Tạo / cấu hình / xóa tài nguyên| C["Control plane operation"]
    Q -->|Xử lý dữ liệu nghiệp vụ| D["Data plane operation"]
    Q -->|Vùng giao nhau / metadata| X["Xem docs API và IAM action"]
    C --> P["Xác định permission, API và scope"]
    D --> P
    X --> P
    P --> I["Xác minh runtime principal"]
    I --> E["Xác minh endpoint, Region, network, policy"]
~~~

Cần phân biệt thêm **identity/authentication plane**: nơi phát hành token/credential, quản lý người dùng, role, service principal hoặc service account. Đây thường là các chức năng quản trị danh tính. Tuy nhiên, trong một lần gọi data plane, ứng dụng cũng phải **xác thực**. Việc endpoint phát token có thể khác endpoint quản lý tài nguyên và khác endpoint dữ liệu.

| Tình huống | Điều không nên suy luận | Điều phải xác minh |
|---|---|---|
| API trả HTTP 200 cho thao tác xem cấu hình | Ứng dụng đã có quyền data plane | Permission đọc/ghi dữ liệu đích và identity đang dùng |
| Login thành công và nhận access token | Token dùng được ở mọi API | Audience/scope/token issuer và phân quyền của resource |
| Hai API dùng cùng hostname | Chúng cần cùng role | Permission của **từng method** |
| Endpoint là private | IAM/RBAC không cần thiết | Cả xác thực, phân quyền, TLS và network |
| Có role Owner/Contributor | Luôn đọc được dữ liệu | Role definition, data actions và cơ chế key/tokens |
| Ứng dụng có quyền list hoặc describe | Có quyền get payload | Permission cụ thể cho data payload |
| Hành động có chữ Admin trong tên | Chắc chắn chỉ dùng control plane | Semantics và policy của API thực tế |

## 8. Thiết kế kiến trúc Spring Boot theo hai nhóm quyền

### 8.1. Tách provisioning khỏi runtime

Một kiến trúc dễ kiểm soát cho ứng dụng Spring Boot:

1. **Repository IaC** xác định bucket, queue/topic, database, secret metadata, network, IAM/RBAC và vị trí tài nguyên.
2. **Deployment pipeline** dùng danh tính triển khai có permission quản lý tài nguyên trong phạm vi dự án/môi trường.
3. **Spring Boot runtime** dùng danh tính workload riêng với permission đọc/ghi dữ liệu vừa đủ; resource name/endpoint được cung cấp qua cấu hình triển khai.
4. **Operations** dùng role tách biệt để điều tra, quản lý vòng đời và thay đổi cấu hình; các thao tác nhạy cảm được audit.

Ví dụ:

~~~mermaid
flowchart LR
    Git["IaC templates"] --> Deploy["CI/CD deployment"]
    Deploy --> AdminID["Deployment identity"]
    AdminID --> CloudMgmt["Cloud management APIs"]
    CloudMgmt --> S["Storage / queue / DB / secret"]
    App["Spring Boot API/worker"] --> RuntimeID["Runtime role / managed identity / service account"]
    RuntimeID --> DataAPI["Data APIs / protocols"]
    DataAPI --> S
~~~

Trong AWS có thể dùng CloudFormation/CDK/Terraform; Azure có Bicep/ARM/Terraform; Google Cloud có Terraform hoặc cơ chế IaC thích hợp. Chọn công cụ tùy hệ thống nhưng giữ nguyên tắc **cấp phát có kiểm soát** và **không cấp quyền quản trị toàn bộ cloud cho runtime**.

### 8.2. Cấu hình Spring Boot hướng vào resource đã tạo

Ví dụ cấu hình logic do ứng dụng **tự định nghĩa**:

~~~yaml
app:
  environment: production
  storage:
    container-or-bucket: orders-prod-invoices
  messaging:
    queue-or-topic: orders-prod-events
  database:
    jdbc-url: ${APP_JDBC_URL}
~~~

Những khóa dưới **app.*** không phải property tự động của mọi Spring Cloud starter. Cần bind bằng **@ConfigurationProperties** hoặc cấu hình riêng trong code. Tránh ghi credential vào YAML trong repository; dùng role/managed identity/service account và secret manager khi thích hợp. Tên resource đích, project/account, Region và endpoint cần được xác minh bởi deployment.

Spring Cloud AWS, Spring Cloud Azure và Spring Cloud GCP hỗ trợ các mô hình tích hợp khác nhau tùy phiên bản: starter, auto-configuration, SDK underlying, Spring Messaging/Integration hoặc client Java. **BOM phải tương thích với phiên bản Spring Boot**; các property và package name cần đối chiếu tài liệu cho phiên bản ứng dụng. Mô hình phân tách control/data vẫn đúng dù client cụ thể thay đổi.

### 8.3. Ví dụ AWS SDK v2: Spring Boot chỉ đọc object

Đoạn mã sau thể hiện data plane trên tài nguyên đã có; ứng dụng không cần gọi CreateBucket:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

@Service
public class InvoiceReader {
    private final S3Client s3;
    private final String bucket;

    public InvoiceReader(
            S3Client s3,
            @Value("${app.storage.container-or-bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public byte[] readInvoice(String key) {
        GetObjectRequest request = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();
        return s3.getObjectAsBytes(request).asByteArray();
    }
}
~~~

Giả định dự án đã có dependency **AWS SDK v2 S3** và bean **S3Client** được cấu hình đúng Region/credential. Phương thức này chỉ minh họa cho object nhỏ; trong thực tế, dùng streaming để tránh nạp file lớn vào heap, thêm timeout/retry, kiểm soát key từ đầu vào và xử lý lỗi. Nếu object mã hóa bằng SSE-KMS, có thể cần quyền **kms:Decrypt** bên cạnh **s3:GetObject**. Không cấp **s3:CreateBucket** hoặc **s3:PutBucketPolicy** cho service chỉ để đọc.

Đoạn code trên là ví dụ SDK dùng cùng Spring Boot; không khẳng định nó tự kích hoạt qua một Spring Cloud AWS starter cụ thể. Phần auto-configuration phụ thuộc phiên bản thư viện.

### 8.4. Ví dụ quyền theo vòng đời

| Chủ thể | AWS (minh họa) | Azure (minh họa) | Google Cloud (minh họa) |
|---|---|---|---|
| CI/CD provisioning | Role có action tạo/cập nhật tài nguyên cần thiết | RBAC quản trị resource trong scope triển khai | IAM role/permission tạo/cập nhật tài nguyên |
| Spring Boot đọc object | s3:GetObject với bucket key ARN phù hợp | Storage Blob Data Reader tại scope phù hợp | Storage Object Viewer trên bucket |
| Spring Boot gửi message | sqs:SendMessage trên queue | Azure Service Bus Data Sender | Pub/Sub Publisher trên topic |
| Worker nhận message | sqs:ReceiveMessage/DeleteMessage trên queue | Azure Service Bus Data Receiver | Pub/Sub Subscriber trên subscription |
| Service đọc secret | secretsmanager:GetSecretValue trên secret | Key Vault Secrets User hoặc quyền data tương đương theo mô hình vault | Secret Manager Secret Accessor trên secret |

Đây là **gợi ý điểm bắt đầu** cho cấp quyền, chưa đủ thay thế việc tính đúng các method SDK thực tế (ví dụ cần thêm Describe, GetQueueUrl, KMS, List, IAM conditions, token exchange, message operations). Với SQS, **DeleteMessage** là xóa message đã xử lý chứ không phải **DeleteQueue**; chỉ nhìn chữ “Delete” không đủ để xác định plane.

## 9. Xác thực, phân quyền và kết nối mạng

Một lời gọi hợp lệ đòi hỏi nhiều điều kiện độc lập:

~~~mermaid
flowchart LR
    A["Runtime identity"] --> B["Credential / token hợp lệ"]
    B --> C["IAM / RBAC / DB permission"]
    C --> D["Resource scope + policy"]
    D --> E["Endpoint + network + TLS"]
    E --> F["Quota / service state"]
    F --> G["API operation thành công"]
~~~

Sơ đồ là **checklist logic**, không mô tả thứ tự kiểm tra nội bộ cố định của mọi dịch vụ.

### 9.1. Identity khác với permission

- **AWS:** role được xác thực qua credential tạm thời, nhưng action vẫn phải được allow và không bị deny bởi các policy liên quan.
- **Azure:** managed identity có thể lấy token Microsoft Entra thành công, nhưng data-plane role trên Blob/Service Bus/Key Vault có thể chưa được cấp, hoặc token được yêu cầu cho sai resource/audience.
- **Google Cloud:** service account có thể lấy access token hợp lệ nhưng thiếu IAM permission trên bucket/topic/secret đích.
- **Database:** cloud IAM cho phép kết nối đến instance không tự cấp quyền bảng/schema trong SQL engine; cần cơ chế database authentication và authorization phù hợp.

### 9.2. Mạng và endpoint có thể khác giữa hai plane

Azure Resource Manager và Blob endpoint có thể có đường đi, DNS và firewall khác nhau. Với AWS, một số data API có VPC endpoint/PrivateLink, trong khi API quản lý/STS hoặc dịch vụ khác có yêu cầu kết nối riêng. Trên Google Cloud, API host, private access, VPC Service Controls và chính sách từng dịch vụ có thể ảnh hưởng đường đi.

**Quyền đúng mà network sai vẫn thất bại**. Ngược lại, vào được private endpoint không chứng minh được cấp phép cho dữ liệu. Khi dùng private endpoint, xác minh DNS, TLS hostname, route, firewall, IAM và Region. Các lựa chọn kết nối không tự thay đổi nơi dữ liệu lưu trữ.

### 9.3. Quota và vòng đời khác nhau

Control-plane API có thể chịu giới hạn request provisioning, rate limit, trạng thái tài nguyên hoặc delay khi thay đổi cấu hình. Data plane có throughput, request rate, concurrency, payload size, visibility timeout, transaction limit và đặc tính retry riêng. Không tạo tài nguyên mới trong mỗi request nghiệp vụ để né giới hạn data plane; cách đó làm tăng chi phí, rủi ro trạng thái và giới hạn quản trị.

## 10. Security pitfalls và anti-patterns

| Anti-pattern | Rủi ro | Cách xử lý |
|---|---|---|
| Ứng dụng Spring Boot dùng credential admin của cloud | Một lỗ hổng ứng dụng có thể tạo/xóa nhiều resource hoặc sửa policy | Workload identity chỉ có data permissions tối thiểu |
| Chạy CreateBucket/CreateQueue mỗi lần khởi động | Lỗi khi thiếu quyền, đua trạng thái, giới hạn provisioning, drift IaC | Provision bằng CI/CD trước rồi cấu hình resource ID |
| Dùng Azure ARM Reader để mong đọc blob | Phân quyền nhầm plane; request data bị từ chối | Cấp đúng Storage Blob Data Reader/Contributor |
| Dùng account key/SAS rộng khi đã có managed identity | Vô tình bỏ qua hạn chế phân quyền người dùng/role, khó truy vết | Ưu tiên Microsoft Entra RBAC; hạn chế và luân phiên key/SAS khi bắt buộc |
| Cấp role ở mức project/subscription/account không cần thiết | Workload đọc được nhiều dữ liệu ngoài ứng dụng | Gán quyền tại bucket/container/queue/secret hoặc phạm vi tối thiểu |
| Chỉ kiểm tra API trả HTTP 200/khởi tạo client | Có thể chưa thử quyền thực thi action nghiệp vụ | Kiểm tra action dữ liệu thực với test resource |
| Ghi giá trị secret hoặc token vào log để debug | Rò rỉ thông tin xác thực và dữ liệu nhạy cảm | Log resource name, operation, request ID, mã lỗi đã lọc |
| Nhầm **DeleteMessage** với **DeleteQueue** | Cấp quyền sai hoặc thiết kế luồng xử lý sai | Đối chiếu chính xác action và resource mà method tác động |
| Cho runtime sửa network/policy để tự sửa lỗi 403 | Mở rộng blast radius và khó audit | Điều tra nguyên nhân; để pipeline/platform sửa cấu hình |

Mô hình tách quyền không loại bỏ hoàn toàn rủi ro data plane: principal có quyền **xóa object**, **purge queue** hoặc **ghi đè database** vẫn có thể phá hủy dữ liệu. Vì vậy cần kiểm soát cả **data operations**, versioning, soft delete, backup, retention và audit, không chỉ control plane.

## 11. Thiết kế bài kiểm thử tích hợp có chủ đích

Để kiểm thử tích hợp Spring Boot với managed services:

1. **Chuẩn bị trước:** IaC tạo tài nguyên test trong account/subscription/project tách biệt, đặt Region, network, policy và tags/labels. Giai đoạn này cần quyền control plane.
2. **Chạy với runtime identity:** ứng dụng sử dụng role/managed identity/service account chỉ có quyền data được phép.
3. **Positive test:** ghi rồi đọc object, gửi rồi nhận message, thực thi transaction database, đọc một secret thử nghiệm có scope nhỏ.
4. **Negative test:** dưới identity runtime, thử xác minh các thao tác cấm như tạo resource mới hoặc đọc dữ liệu ngoài scope. Nên sử dụng API check quyền/dry-run/simulator khi khả dụng hoặc môi trường test cô lập để không gây tác động không mong muốn.
5. **Xác minh network:** kiểm tra endpoint, Region, DNS, private access và TLS của đường đi thực tế.
6. **Kiểm tra cleanup:** thu dọn object/message test bằng quyền data thích hợp; hủy tài nguyên test qua pipeline/provisioning identity sau khi kiểm thử kết thúc.
7. **Audit và quan sát:** đối chiếu cloud audit logs, SDK request ID và trace ứng dụng, loại bỏ secret/token khỏi log.

**Mock unit test** xác nhận code gọi đúng method nhưng không kiểm chứng IAM/RBAC, endpoint, network hoặc quota thật. **Integration test** trên cloud kiểm tra hành vi thực tế; không cần cấp quyền quản trị cho ứng dụng chỉ vì test cần tạo tài nguyên. Có thể chuẩn bị fixture bằng pipeline riêng hoặc test harness dùng credential khác một cách có kiểm soát.

### 11.1. Ma trận kiểm thử đề xuất

| Kịch bản | Kết quả kỳ vọng | Nguyên nhân cần kiểm tra nếu sai |
|---|---|---|
| Deployment identity tạo queue test | Thành công | Scope quản lý, policy, Region, quota |
| Runtime identity gửi message đúng queue | Thành công | Data permission, endpoint, network |
| Runtime identity sửa cấu hình queue | Bị từ chối nếu không có yêu cầu quản trị | Quyền control-plane bị cấp rộng |
| Runtime identity đọc blob ngoài container cho phép | Bị từ chối | Role/resource scope, inherited permission, key/SAS |
| Runtime identity đọc secret test đúng scope | Thành công | Secret/data role, token audience, vault mode |
| Runtime identity xóa database instance | Bị từ chối | Quyền management-plane và policy cấp trên |
| Kết nối JDBC rồi chạy SELECT | Theo quyền DB user cụ thể | DB auth, quyền schema/table, network |

Không kiểm thử việc xóa tài nguyên production để “chứng minh” quyền bị chặn. Dùng resource cô lập, IAM simulation/policy inspection hoặc kế hoạch thử nghiệm an toàn.

## 12. Chẩn đoán lỗi theo từng lớp

### 12.1. Quy trình điều tra

~~~mermaid
flowchart TD
    E["Cloud API call thất bại"] --> O["Xác định operation + resource ID"]
    O --> P{"Control hay data?"}
    P -->|Control| C["Role quản lý / policy / quota"]
    P -->|Data| D["Role dữ liệu / object, queue, SQL, secret permissions"]
    P -->|Không rõ| M["Đọc IAM action/method docs của provider"]
    C --> I["Xác minh principal thực tế"]
    D --> I
    M --> I
    I --> N["Kiểm tra scope, network, endpoint, Region"]
    N --> T["Test lại bằng quyền tối thiểu tại staging"]
~~~

### 12.2. Những triệu chứng phổ biến

**AWS — có quyền liệt kê bucket nhưng GetObject trả AccessDenied:** kiểm tra action s3:GetObject trên object ARN, bucket policy, KMS decrypt, explicit deny, account sở hữu object/bucket, endpoint Region và network. Quyền liệt kê tên bucket không tự cho phép đọc mọi object.

**AWS — RDS DescribeDBInstances thành công nhưng JDBC timeout:** Describe dùng API quản lý; JDBC dùng endpoint DB và giao thức riêng. Kiểm tra security group, subnet, routing, port, TLS và DB credentials. Nếu kết nối được nhưng SELECT bị từ chối, kiểm tra quyền SQL bên trong database.

**Azure — Storage Account Contributor nhưng Blob read lỗi 403:** xem role data-plane, cơ chế xác thực đang dùng (Entra token hay key/SAS), scope gán role và firewall/private endpoint. Một số role quản trị có khả năng lấy account key; cần tránh tự động chuyển sang shared key như một cách “sửa” lỗi phân quyền.

**Azure — Key Vault đã tạo được nhưng SecretClient không đọc được:** xác định vault đang dùng Azure RBAC hay access policy; kiểm tra principal runtime và quyền data secret tại vault/secret phù hợp, token audience, firewall và private endpoint.

**Google Cloud — tạo Pub/Sub topic được nhưng publish bị PermissionDenied:** xác định IAM permission publish của runtime identity trên topic đích, project thật, API enablement, organization policy và trạng thái resource. Người triển khai và workload có thể là hai service account khác nhau.

**Google Cloud — Cloud SQL Admin API xem instance được nhưng JDBC lỗi:** quyền quản lý instance không phải quyền SQL engine; cần xác minh connector/proxy nếu dùng, network, database login, TLS và user grants.

**Một số lỗi không phải thiếu quyền:** HTTP 404 do sai project/Region/resource name, 429 do quota, timeout do private DNS, endpoint bị chặn hoặc service chưa bật. Không tăng quyền IAM/RBAC trước khi xác định **operation**, **principal**, **resource** và **failure mode**.

## 13. Checklist khi tích hợp dịch vụ mới

- **Operation:** phân loại từng method SDK/API theo mục đích; ghi rõ action/permission thực sự cần.
- **Identity:** xác định danh tính CI/CD, runtime và vận hành; ưu tiên credential tạm thời, managed identity hoặc service account.
- **Scope:** cấp quyền quản trị và dữ liệu ở mức nhỏ nhất; tránh cấp Owner/Admin chỉ để đọc hoặc ghi dữ liệu.
- **Provisioning:** tạo resource, network, replica, backup, policy và key bằng IaC hoặc quy trình có audit.
- **Runtime:** chỉ cấu hình resource ID, endpoint/Region, auth và retry; kiểm tra hành vi data plane từ đúng môi trường triển khai.
- **Secret:** bảo vệ secret value; phân biệt quyền tạo/quản lý secret với quyền truy xuất payload.
- **Network:** xác nhận API host, private/public endpoint, DNS, TLS, firewall và quy tắc data location.
- **Testing:** có positive/negative test theo plane và audit request thực, dùng dữ liệu thử nghiệm cô lập.
- **Operations:** kiểm soát quota, chi phí, drift cấu hình, log và quy trình khắc phục sự cố.

## 14. Tổng kết

**Control plane** quyết định tài nguyên được tạo, cấu hình, quản lý và giới hạn ra sao. **Data plane** là các thao tác dùng tài nguyên đó để xử lý dữ liệu và yêu cầu nghiệp vụ. AWS thường đặt cả hai trong API/SDK theo dịch vụ và phân biệt bằng **IAM action**; Azure có lớp **ARM management** và các **data endpoint/role** rõ nét cho nhiều dịch vụ; Google Cloud có API quản lý tài nguyên và nhiều API dịch vụ kết hợp cả method quản lý lẫn thao tác dữ liệu, được phân biệt bằng **IAM permission**.

Khi xây dựng hệ thống Spring Boot với Spring Cloud AWS, Spring Cloud Azure hay Spring Cloud GCP, hãy xác định **ai provision resource**, **ai đọc/ghi dữ liệu**, **mỗi principal được gọi method nào**, **scope tài nguyên ở đâu** và **endpoint/network hoạt động thế nào**. Mô hình này giúp bảo vệ dữ liệu, giảm quyền dư thừa, làm rõ nguyên nhân lỗi tích hợp và tách trách nhiệm triển khai khỏi xử lý nghiệp vụ.
