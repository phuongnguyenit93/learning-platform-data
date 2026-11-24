# Phân tách tài nguyên phát triển, kiểm thử và sản xuất

Một ứng dụng Spring Boot có thể chạy chính xác trên máy của lập trình viên nhưng gây sự cố khi triển khai: job kiểm thử xóa object thật, consumer ở môi trường staging nhận message production, pipeline dùng nhầm danh tính cloud, hoặc cấu hình database trong profile test trỏ vào cơ sở dữ liệu đang phục vụ khách hàng. Những trường hợp này thường bắt nguồn từ **thiếu ranh giới môi trường** hơn là lỗi của API storage, messaging hay database.

Trong chương **Nền tảng đám mây** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**, bài học tập trung vào cách phân tách **development (dev), testing/integration test, staging/pre-production và production (prod)** khi tích hợp Spring Boot với dịch vụ managed của **AWS, Azure và Google Cloud** thông qua các thư viện Spring Cloud tương ứng. Mục tiêu là bảo vệ dữ liệu và secret, kiểm soát quyền truy cập, giới hạn phạm vi tác động khi lỗi, quản trị chi phí, đồng thời vẫn kiểm thử được storage, messaging, dữ liệu và các tích hợp từ xa.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích lý do cần tách môi trường và phân biệt **ranh giới quản trị**, **ranh giới IAM**, **ranh giới dữ liệu**, **ranh giới mạng** và **ranh giới vận hành**.
- Chọn mô hình tách môi trường phù hợp trên **AWS account**, **Azure subscription/resource group** và **Google Cloud project**.
- Thiết kế workload identity, service principal/service account, secret, policy và resource naming riêng cho từng môi trường.
- Xây dựng pipeline tạo tài nguyên bằng Infrastructure as Code (IaC), triển khai cùng một artifact tới các môi trường và có điểm kiểm soát trước production.
- Cấu hình Spring Boot, Spring profiles và Spring Cloud SDK để ứng dụng chỉ truy cập tài nguyên được cho phép trong đúng môi trường.
- Thiết kế kiểm thử tích hợp an toàn, dữ liệu thử nghiệm đã xử lý thông tin nhạy cảm, tài nguyên tạm thời có vòng đời và kiểm thử quyền truy cập bị từ chối.
- Phát hiện những lỗi dễ gây tác động chéo: endpoint sai, credential chung, backup/test data lẫn nhau, queue/topic chung hoặc secret production xuất hiện trong staging.

## 2. Môi trường là tập hợp ranh giới, không chỉ là tên profile

**Môi trường** là tập tài nguyên, danh tính, dữ liệu, cấu hình, network, chính sách và quy trình triển khai phục vụ một mục đích cụ thể. Các môi trường thường gặp:

| Môi trường | Mục đích chính | Dữ liệu phù hợp | Quy tắc vận hành |
|---|---|---|---|
| **Local development** | Viết mã và thử logic nhanh | Dữ liệu sinh giả, mock, emulator hoặc resource dev riêng | Quyền tối thiểu; không tự động chạm production |
| **Development (dev)** | Tích hợp thay đổi chưa ổn định | Synthetic test data; có thể reset | Tự động triển khai, dễ tạo/xóa tài nguyên theo kiểm soát |
| **Integration test / QA** | Xác nhận nhiều thành phần tương tác đúng | Fixture cô lập và có thể tái tạo | Kiểm thử có cleanup, không làm biến đổi dữ liệu thật |
| **Staging / pre-production** | Diễn tập hành vi gần production trước phát hành | Synthetic hoặc dữ liệu đã biến đổi đủ an toàn | Cấu hình và topology tương đồng production khi cần |
| **Production** | Phục vụ người dùng và dữ liệu nghiệp vụ thật | Dữ liệu thật theo chính sách | Quyền chặt, audit, backup, DR, release gate và giám sát |

Dev, QA và staging có thể được gộp ở quy mô nhỏ, nhưng **phải xác định rủi ro được chấp nhận**. Gộp môi trường để tiết kiệm không có nghĩa ứng dụng có thể dùng chung quyền quản trị hoặc dữ liệu production.

### 2.1. Những lớp cần tách

~~~mermaid
flowchart TB
    Org["Cấp tổ chức / governance"]
    Org --> D["Môi trường DEV"]
    Org --> S["Môi trường STAGING"]
    Org --> P["Môi trường PROD"]
    D --> D1["Identity + IAM"]
    D --> D2["Storage + queue + DB + secret"]
    S --> S1["Identity + IAM"]
    S --> S2["Storage + queue + DB + secret"]
    P --> P1["Identity + IAM"]
    P --> P2["Storage + queue + DB + secret"]
    CI["CI/CD - artifact chung"] --> D
    CI --> S
    CI --> P
~~~

Sơ đồ minh họa việc chia thành các phạm vi triển khai riêng. Trong thực tế phải phân quyền riêng cho pipeline trước từng môi trường; một artifact được tái sử dụng **không đồng nghĩa** một credential dùng chung.

Có thể phân ranh giới theo năm câu hỏi:

1. **Quản trị:** account/subscription/project nào sở hữu resource và ghi nhận chi phí?
2. **Danh tính và quyền:** ai được thực thi thao tác nào trên resource đích?
3. **Dữ liệu:** dữ liệu chính, replica, backup, log và message thuộc môi trường nào?
4. **Mạng:** workload kết nối đến endpoint nào, qua VPC/VNet/firewall/private endpoint nào?
5. **Thay đổi:** ai được tạo, sửa, xóa và triển khai resource/code của môi trường đó?

**Spring profile** như \`dev\` hoặc \`prod\` chỉ là cơ chế chọn cấu hình của ứng dụng. Nó **không tạo ra ranh giới bảo mật** trong IAM hoặc nền tảng cloud. Một ứng dụng với profile dev nhưng credential production vẫn có thể làm thay đổi dữ liệu production nếu chính sách cho phép.

## 3. Tại sao cần tách môi trường?

### 3.1. Giảm phạm vi tác động (blast radius)

Nếu dev và production sử dụng chung database, một migration hoặc câu lệnh xóa nhầm trên dev có thể phá hủy dữ liệu thật. Nếu tách database nhưng vẫn dùng chung IAM role quyền rộng, một lỗi cấu hình có thể cho phép truy cập nhầm. Vì thế, ranh giới phải có hiệu lực ở cả **resource** lẫn **principal và policy**.

Ví dụ, một job dọn dữ liệu test được phép xóa object trong bucket \`orders-dev-invoices\` nhưng không được phép xóa object trong \`orders-prod-invoices\`, kể cả khi lập trình viên vô tình truyền vào tên bucket production.

### 3.2. Giữ kiểm thử có thể tái lập

Kiểm thử tích hợp cần biết dữ liệu ban đầu, event được gửi đi, ai tiêu thụ event, thời điểm cleanup và điều kiện lỗi. Khi nhiều môi trường sử dụng chung queue, test có thể ăn nhầm message của production hoặc consumer thực xử lý event giả. Tách queue/topic/subscription và database giúp tạo fixture riêng, reset trạng thái và tái lập hành vi.

### 3.3. Kiểm soát thay đổi và quyền truy cập

Dev có thể cho phép triển khai liên tục; staging có thể có test gate; production cần phê duyệt phù hợp, rollback và audit. Nhóm phát triển có thể có quyền vận hành rộng hơn trong dev, trong khi production áp nguyên tắc **least privilege**, phân tách nhiệm vụ và cơ chế khẩn cấp có ghi nhận.

### 3.4. Kiểm soát chi phí, quota và hiệu năng

Một batch thử nghiệm chạy mạnh không nên chiếm hết quota, DB connections, messaging throughput hoặc chi phí của production. Việc tách account/subscription/project có thể giúp lập ngân sách và xem chi phí rõ hơn, nhưng các quota cụ thể vẫn phụ thuộc provider, Region và dịch vụ. Một số tài nguyên dùng chung cấp tổ chức vẫn có thể ảnh hưởng lẫn nhau, cần kiểm tra đúng giới hạn.

### 3.5. Bảo vệ dữ liệu và đáp ứng quy định

Production chứa dữ liệu thật, gồm cả thông tin có thể được bảo vệ theo luật hoặc chính sách nội bộ. Không mặc định copy production database sang test là an toàn. Ngay cả bản sao đã ẩn bớt trường thông tin vẫn có thể nhận dạng lại người dùng hoặc chứa secret/token nếu quá trình xử lý dữ liệu chưa đủ.

## 4. Chọn mức phân tách: từ resource đến tài khoản độc lập

Có nhiều cách đặt ranh giới, với mức cách ly khác nhau:

| Mức phân tách | Ví dụ | Ưu điểm | Giới hạn/rủi ro |
|---|---|---|---|
| **Chỉ khác prefix/name** | Hai bảng hoặc object prefix trong cùng resource | Dễ tạo và rẻ trong lab | Quyền/mạng/quota thường chia sẻ; xóa nhầm dễ lan |
| **Resource riêng, cùng cấp quản trị** | Bucket/queue/DB riêng trong cùng account/project | Resource có IAM và vòng đời riêng | Có thể chung quota, quyền cấp cha, billing và network |
| **Resource group riêng trong Azure subscription** | \`rg-orders-dev\`, \`rg-orders-prod\` | Quản lý lifecycle và RBAC theo resource group | Không tạo ranh giới subscription/billing/quota độc lập |
| **Account/subscription/project riêng** | AWS account, Azure subscription, GCP project theo env | Dễ phân quyền, quản trị, theo dõi chi phí, guardrail và giảm blast radius | Tăng công việc vận hành, IAM, network, IaC và cost governance |
| **Tổ chức/tenant độc lập khi thật cần** | Cơ cấu pháp lý, danh tính hoặc tuân thủ khác | Ranh giới danh tính/quản trị bổ sung | Độ phức tạp quản trị và tích hợp lớn |

Đối với production chứa dữ liệu hoặc tác vụ quan trọng, **một đơn vị tài nguyên chủ đạo riêng cho production** thường là điểm khởi đầu tốt. Tuy nhiên, không có một quy định bắt buộc rằng mọi ứng dụng nhỏ phải có một tổ chức cloud hoặc một subscription riêng; lựa chọn cần dựa vào dữ liệu, quy mô và khả năng vận hành.

### 4.1. Ranh giới mềm và ranh giới cứng

**Ranh giới mềm** là quy ước: đặt tên có hậu tố \`-prod\`, gắn tag \`environment=prod\`, để resource trong thư mục riêng. Quy ước giúp tổ chức và quan sát, nhưng không tự tạo quyền bị từ chối.

**Ranh giới có thể thực thi** là cơ chế như IAM/RBAC, resource policy, organization guardrail, network isolation, service perimeter, encryption-key access và deployment approval. Cần kiểm thử **một workload dev không thể đọc hoặc ghi production resource**, thay vì chỉ xem hình sơ đồ.

## 5. AWS: tách account, role và tài nguyên theo môi trường

### 5.1. AWS Organizations và account

Một mẫu phổ biến là dùng **AWS Organizations** quản trị nhiều account, đặt chúng trong organizational unit (OU) theo vai trò hoặc môi trường:

~~~mermaid
flowchart TB
    O["AWS Organizations"] --> NP["OU: NonProduction"]
    O --> PR["OU: Production"]
    NP --> DEV["AWS account: orders-dev"]
    NP --> ST["AWS account: orders-staging"]
    PR --> PRO["AWS account: orders-prod"]
    DEV --> DA["IAM role + S3/SQS/RDS dev"]
    ST --> SA["IAM role + S3/SQS/RDS staging"]
    PRO --> PA["IAM role + S3/SQS/RDS production"]
~~~

OU **nhóm account**, không trực tiếp chứa bucket hay database. AWS account thường là ranh giới quan trọng về quyền, tài nguyên và quota; các tài nguyên khu vực còn có **Region**. **Service control policy (SCP)** có thể đặt giới hạn quyền tối đa ở cấp tổ chức/OU/account nhưng **không tự cấp quyền**. Cần thêm identity/resource policy tương ứng và kiểm tra explicit deny.

Ví dụ mỗi môi trường có:
- S3 bucket hóa đơn riêng.
- SQS queue/SNS topic riêng; consumer dev không đăng ký vào topic production.
- RDS instance hoặc cluster riêng; không copy DB production thô sang dev.
- Secrets Manager secret và KMS key phù hợp với phạm vi.
- ECS task role/EKS workload identity/EC2 instance role riêng cho runtime.

### 5.2. Role của pipeline khác role runtime

Pipeline được cấp quyền **triển khai** tài nguyên trong account đích; Spring Boot runtime chỉ được cấp **data operations** cần cho ứng dụng. Một IAM role dev không được tin cậy để assume production role, trừ luồng đặc biệt được phê duyệt rõ ràng.

Một mô hình triển khai dùng OIDC hoặc một cơ chế federation phù hợp để CI/CD nhận credential **ngắn hạn**, với trust policy giới hạn repository/branch/environment và quyền trên account đích. Không đưa access key dài hạn vào repository hoặc copy credential production vào runner dev.

Mẫu quyền tối thiểu cho ứng dụng chỉ **đọc/ghi object trong một prefix dev**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:PutObject"],
      "Resource": "arn:aws:s3:::orders-dev-invoices/invoices/*"
    }
  ]
}
~~~

Đây là ví dụ role permission, không phải cấu hình đầy đủ. Nếu sử dụng KMS, multipart upload, list, policy cross-account hoặc tính năng khác, cần kiểm tra action tương ứng. Nó không cấp \`s3:CreateBucket\`, \`s3:DeleteBucket\`, \`s3:ListBucket\` hay tự cho phép truy cập bucket production. Phải xét thêm bucket policy, key policy, SCP, role trust và Region.

### 5.3. Công cụ và cách xác minh

~~~bash
# Xem account/principal đang được AWS CLI sử dụng
aws sts get-caller-identity

# Kiểm tra Region của bucket dev (metadata)
aws s3api get-bucket-location --bucket orders-dev-invoices

# Xem ARN của queue khi đã biết URL
aws sqs get-queue-attributes \
  --queue-url https://sqs.ap-southeast-1.amazonaws.com/123456789012/orders-dev \
  --attribute-names QueueArn
~~~

Lệnh trên đọc ngữ cảnh của **CLI đang dùng**, không tự xác minh IAM role của ứng dụng khi chạy trong ECS/EKS. Ứng dụng hoặc pipeline cần kiểm tra credential **thực tế** theo môi trường chạy. Các giá trị account, bucket và queue chỉ là ví dụ.

## 6. Azure: tenant, subscription, resource group và managed identity

### 6.1. Mỗi cấp có ý nghĩa khác nhau

**Microsoft Entra tenant** quản lý danh tính. **Management group** nhóm subscription để quản trị. **Subscription** là ranh giới quan trọng về resource, quota và tính phí. **Resource group** là nhóm quản lý vòng đời tài nguyên trong một subscription; gán RBAC, policy ở cấp resource group hữu ích nhưng resource group **không tạo một subscription mới**.

~~~mermaid
flowchart TD
    T["Microsoft Entra tenant"] --> MG["Management group"]
    MG --> D["Subscription: orders-dev"]
    MG --> P["Subscription: orders-prod"]
    D --> RD["Resource groups dev"]
    P --> RP["Resource groups prod"]
    RD --> SD["Blob / Service Bus / SQL / Key Vault dev"]
    RP --> SP["Blob / Service Bus / SQL / Key Vault prod"]
~~~

Với ứng dụng nhỏ có thể dùng một subscription và nhiều resource group, nhưng phải hiểu rằng subscription-level Owner/Contributor có thể có phạm vi rộng hơn nhiều so với group-level role. Với production quan trọng, subscription riêng thường làm giảm nguy cơ thao tác quản trị nhầm và giúp kiểm soát quota/chi phí, policy dễ hơn.

### 6.2. Managed identity và data role

App Service, VM, Functions hoặc các workload Azure hỗ trợ có thể dùng **Managed Identity** để lấy token mà không lưu client secret dài hạn. Mỗi môi trường cần nhận đúng identity và **data-plane role** trên resource đích:

| Dịch vụ | Workload dev | Workload production |
|---|---|---|
| Azure Blob Storage | Chỉ đọc/ghi container dev theo role cần thiết | Chỉ container prod theo role cần thiết |
| Azure Service Bus | Chỉ namespace/queue dev | Chỉ namespace/queue prod |
| Azure SQL Database | DB login/Entra user có quyền schema test | DB principal quyền tối thiểu trên production |
| Azure Key Vault | Quyền đọc secret dev | Quyền đọc secret production khi thật cần |

Role **Reader** quản lý resource không mặc nhiên cho phép đọc blob bằng Microsoft Entra. Cần role data tương ứng, ví dụ **Storage Blob Data Reader/Contributor** ở phạm vi thích hợp. Với Service Bus có **Azure Service Bus Data Sender/Receiver**. Với Key Vault, phân quyền tùy RBAC hay access policy mode, phải kiểm tra quyền data để đọc secret.

Cũng cần bảo vệ khả năng lấy **storage account keys/SAS** của các role quản trị: một số quyền quản lý có thể gián tiếp mở đường truy cập dữ liệu theo cơ chế Shared Key. Nếu tổ chức dùng auth bằng Entra, cân nhắc chính sách hạn chế Shared Key khi phù hợp dịch vụ và yêu cầu tương thích.

### 6.3. Azure CLI đọc context

~~~bash
az account show --query "{tenant:tenantId,subscription:id,name:name}"
az group list --query "[].{name:name,location:location}" --output table
az storage account show \
  --name ordersdevstore \
  --resource-group rg-orders-dev \
  --query "{name:name,location:location,sku:sku.name}"
~~~

Mặc định CLI đang trỏ vào một subscription không chứng minh ứng dụng chạy đúng subscription hay identity. Đối chiếu Azure resource ID đầy đủ, tenant/subscription và managed identity thực tế của deployment. Resource group location cũng không nhất thiết là location của mọi resource trong group.

## 7. Google Cloud: tách project và service account

### 7.1. Organization, folder, project

Một mẫu phân tách phổ biến là dùng một Google Cloud organization và các folder, dưới đó có **project** cho từng môi trường. Project là phạm vi sở hữu tài nguyên, bật service APIs và quản lý nhiều loại quota/billing; folder/organization giúp truyền chính sách quản trị theo phạm vi được hỗ trợ.

~~~mermaid
flowchart TD
    O["Google Cloud organization"] --> FD["Folder: NonProduction"]
    O --> FP["Folder: Production"]
    FD --> D["Project: orders-dev"]
    FD --> S["Project: orders-staging"]
    FP --> P["Project: orders-prod"]
    D --> DD["Service account / GCS / PubSub / Cloud SQL dev"]
    S --> SS["Service account / GCS / PubSub / Cloud SQL staging"]
    P --> PP["Service account / GCS / PubSub / Cloud SQL prod"]
    BILL["Cloud Billing account"] -. "Thanh toán project" .-> D
    BILL -. "Thanh toán project" .-> S
    BILL -. "Thanh toán project" .-> P
~~~

Một billing account có thể gắn với nhiều project; **billing account không là nút cha IAM** trong resource hierarchy. Cùng billing account hoặc organization không tự cho phép service account của project dev đọc resource thuộc project prod.

### 7.2. Service account cho workload và CI/CD

Cloud Run, GKE hoặc workload trên nền tảng khác nên sử dụng **service account riêng theo môi trường**; môi trường ngoài GCP có thể dùng Workload Identity Federation thay vì tải xuống khóa JSON lâu dài. Cấp quyền tại bucket, Pub/Sub topic/subscription, Secret Manager secret hoặc phạm vi nhỏ nhất phù hợp.

- Workload chỉ tải object: cân nhắc quyền đọc object/bucket ở scope thích hợp, ví dụ **Storage Object Viewer**.
- Producer gửi event: quyền **Pub/Sub Publisher** trên topic được phép.
- Consumer đọc và ACK event: quyền **Pub/Sub Subscriber** trên subscription được phép.
- Ứng dụng đọc secret: **Secret Manager Secret Accessor** trên secret đích.

IAM permission cụ thể, API enablement, network restrictions, location và service account của runtime đều phải đúng. Với workload ở project A nhưng tài nguyên ở project B, cần thiết lập quyền trên **tài nguyên đích** rõ ràng, không mặc định dùng chung project.

### 7.3. Kiểm tra project và bucket location

~~~bash
gcloud config get-value project
gcloud auth list --filter="status:ACTIVE" --format="value(account)"
gcloud storage buckets describe gs://orders-dev-invoices \
  --format="yaml(name,location,locationType)"
~~~

\`gcloud auth list\` hiển thị tài khoản CLI, còn **Application Default Credentials** hoặc service account của Cloud Run/GKE có thể khác. Project ID chưa đủ để xác định bucket location; cần đọc metadata của từng tài nguyên. Cấu hình message storage policy của Pub/Sub, location replication của secret hoặc backup của DB cũng cần kiểm tra riêng.

## 8. Ma trận thiết kế ranh giới cho một dịch vụ đơn hàng

Giả sử hệ thống \`orders-service\` có Spring Boot API, worker xử lý event, object storage hóa đơn, database và secret. Một phương án tham chiếu:

| Hạng mục | Dev | Integration/QA | Staging | Production |
|---|---|---|---|---|
| Cloud scope | \`orders-dev\` | \`orders-qa\` | \`orders-staging\` | \`orders-prod\` |
| Runtime identity | \`orders-runtime-dev\` | \`orders-runtime-qa\` | \`orders-runtime-staging\` | \`orders-runtime-prod\` |
| Object storage | Bucket/container riêng | Riêng và có cleanup | Riêng, cấu hình gần prod | Riêng, retention/backup phù hợp |
| Messaging | Queue/topic riêng | Queue/topic riêng | Queue/topic riêng | Queue/topic thật |
| Database | Schema/data giả, có thể reset | Database hoặc schema test cô lập | DB riêng, migration rehearsal | DB dữ liệu thật |
| Secret | Secret dev/test | Secret test | Secret staging | Secret production |
| Network | Segment dev theo nhu cầu | Segment test | Gần prod nhưng độc lập | Kiểm soát ingress/egress, private access khi cần |
| Triển khai | CI tự động | CI + test | Pipeline qua gate | Gate, audit, rollback và quản lý thay đổi |
| Dữ liệu | Synthetic | Synthetic | Synthetic/đã biến đổi an toàn | Dữ liệu được phép xử lý |
| Chi phí | Budget nhỏ, auto-cleanup | TTL cho tài nguyên test | Dự toán theo test | Budget, alert, capacity và DR |

Các tên là **minh họa**, không phải yêu cầu đặt tên do provider áp đặt. Khi cùng một resource cloud có thể chứa nhiều workload, đánh giá mức phân quyền và quota thực sự thay vì chỉ nhìn tên.

### 8.1. Nhìn vào đường truyền dữ liệu

~~~mermaid
flowchart LR
    DAPI["Spring Boot DEV"] --> DQ["Queue DEV"]
    DAPI --> DDB["DB DEV"]
    DAPI --> DS["Storage DEV"]
    PAPI["Spring Boot PROD"] --> PQ["Queue PROD"]
    PAPI --> PDB["DB PROD"]
    PAPI --> PS["Storage PROD"]
    PX["Dev identity"] -. "Không được cấp quyền" .-> PQ
~~~

Sơ đồ nói lên một kiểm thử quan trọng: nếu người quản trị vô tình đặt URL queue production trong cấu hình dev, **runtime identity dev vẫn phải bị từ chối** tại resource/policy đích. Cấu hình đúng và IAM chặn sai cần bổ trợ lẫn nhau.

## 9. Tách dữ liệu: không sao chép production thô vào test

Dữ liệu thường là ranh giới khó nhất. Các lựa chọn an toàn theo thứ tự ưu tiên:

1. **Sinh dữ liệu giả (synthetic data):** tạo user, đơn hàng, hóa đơn, sự kiện và payload không tương ứng người thật. Phù hợp cho đa số integration test.
2. **Dùng fixture do nhóm kiểm soát:** bộ dữ liệu nhỏ, có version và expected outcome, có thể tạo lại bằng migration/seed.
3. **Dùng dữ liệu đã được xử lý rủi ro riêng biệt:** chỉ khi thật cần tính chất dữ liệu production; phải đánh giá masking, tokenization, anonymization và nguy cơ tái nhận dạng, phê duyệt theo chính sách nội bộ.
4. **Dữ liệu production có kiểm soát rất chặt:** chỉ khi nghiệp vụ/tuân thủ cho phép, có thiết kế quyền, audit và phạm vi test rõ ràng; không coi đây là mặc định.

**Masking không tự đồng nghĩa anonymization.** Thay email bằng chuỗi \`masked\` nhưng giữ ID, địa chỉ, ngày sinh hay trường nối bảng có thể vẫn nhận dạng được người dùng. Cần kiểm tra cả file đính kèm, object metadata, log, event payload, backup/snapshot và secret/token đi kèm bản sao.

### 9.1. Kế hoạch seed và cleanup

Một integration test đáng tin cậy nên:

- Tạo resource test/namespace hoặc prefix riêng khi phù hợp, kèm test-run ID.
- Seed dữ liệu với ID cố định theo run để tránh trùng với job khác.
- Cố định quyền truy cập của test principal; không có quyền sang prod.
- Dọn data theo ID/run hoặc hủy resource tạm thời qua pipeline có quyền phù hợp.
- Có **TTL/lifecycle** cho tài nguyên tạm và phát hiện tài nguyên bỏ sót.
- Đảm bảo test có thể chạy song song mà không tiêu thụ cùng message hoặc cùng row.
- Không ghi secret hoặc dữ liệu nhạy cảm vào artifact/log test.

Nếu test bị hủy giữa chừng, quy trình dọn nền hoặc lifecycle phải xử lý dữ liệu còn lại. Không xóa resource rộng bằng một tiền tố không được xác minh hoặc lệnh cleanup chạy bằng identity production.

### 9.2. Testcontainers, mock và cloud integration test

**Testcontainers** hoặc emulator có thể tái tạo database/queue/storage tương thích một phần để kiểm tra logic nhanh. Chúng không chứng minh chính sách IAM/RBAC, giới hạn quota, endpoint, private networking, behavior của managed service hay data residency thực tế.

Bởi vậy cần ít nhất hai lớp: **test local rẻ và lặp lại nhanh**, cùng **integration test trên cloud test scope cô lập** để kiểm tra danh tính, quyền, mạng, service semantics và lifecycle. Không cần dùng production data để kiểm tra những điều này.

## 10. Spring Boot: profile chọn cấu hình, cloud IAM bảo vệ ranh giới

### 10.1. Tách cấu hình ứng dụng khỏi credential

Spring Boot hỗ trợ cấu hình theo profile và nguồn cấu hình khác nhau (biến môi trường, config tree, secret provider, hệ thống cấu hình). Thông tin nên tách:

- **Cấu hình không nhạy cảm:** tên bucket/container, queue/topic, Region, project ID, endpoint, feature flags.
- **Danh tính runtime:** IAM role/Managed Identity/service account được gắn vào workload theo môi trường.
- **Secret:** lấy qua manager hoặc cơ chế injection có kiểm soát; không commit mật khẩu hoặc access key.
- **Chính sách ranh giới:** IAM/RBAC, policy, firewall, quota, audit đặt trong cloud IaC, độc lập với giá trị profile.

Ví dụ dưới đây là **property tùy biến của ứng dụng**:

~~~yaml
app:
  cloud:
    environment: dev
    provider: aws
    expected-account-id: "111122223333"
    region: ap-southeast-1
  storage:
    invoice-bucket: orders-dev-invoices
  messaging:
    orders-queue-url: https://sqs.ap-southeast-1.amazonaws.com/111122223333/orders-dev
~~~

Các khóa \`app.*\` không phải property tự động dùng chung cho Spring Cloud AWS/Azure/GCP. Cần bind chúng bằng code và kiểm tra. Khi chuyển sang production, thay bằng thông tin production qua hệ thống deployment đáng tin cậy; **không chỉ đổi \`environment: prod\`** mà vẫn giữ đích dev.

Nếu dùng Spring Cloud AWS, Spring Cloud Azure hoặc Spring Cloud GCP, phải chọn **BOM/starter tương thích với phiên bản Spring Boot**. Auto-configuration, tên property và behavior credential discovery có thể khác nhau giữa thế hệ thư viện.

### 10.2. Khóa khởi động nếu AWS runtime vào nhầm account

Đây là một **guard bổ sung** trong Spring Boot sử dụng AWS SDK v2 STS. Mã minh họa kiểm tra account của credential hiệu lực trước khi ứng dụng nhận traffic. Ví dụ giả định Spring Boot 3.x, đã thêm AWS SDK v2 STS và có cấu hình \`app.cloud.expected-account-id\`.

~~~java
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.services.sts.StsClient;

@ConfigurationProperties(prefix = "app.cloud")
record CloudBoundaryProperties(
        String environment, String provider,
        String expectedAccountId, String region) {}

@Configuration
@EnableConfigurationProperties(CloudBoundaryProperties.class)
class CloudBoundaryConfiguration {

    @Bean
    StsClient stsClient() {
        return StsClient.create();
    }

    @Bean
    ApplicationRunner verifyAwsAccount(
            StsClient sts, CloudBoundaryProperties properties) {
        return args -> {
            if (!"aws".equalsIgnoreCase(properties.provider())) {
                return;
            }
            String expected = properties.expectedAccountId();
            if (expected == null || expected.isBlank()) {
                throw new IllegalStateException("Missing expected AWS account ID");
            }
            String actual = sts.getCallerIdentity().account();
            if (!expected.equals(actual)) {
                throw new IllegalStateException(
                        "Cloud account mismatch; deployment blocked");
            }
        };
    }
}
~~~

Lưu ý:

- \`GetCallerIdentity\` cho biết **account của principal đang chạy**, không chứng minh mọi bucket/queue/DB đích thuộc account đó. Trong trường hợp **cross-account role**, giá trị account trả về là account của role đã được đảm nhận.
- Mã cần được đưa vào **quy trình startup gate** theo kiến trúc thật. Nó bổ sung phát hiện cấu hình sai, không thay IAM/resource policy.
- Cấu hình expected account ID phải đến từ deployment được tin cậy, không để người dùng đầu cuối tự đặt. Account ID không phải secret nhưng vẫn là thông tin cấu hình cần quản lý.
- Kiểm tra endpoint/resource ID, Region và quyền tại resource đích vẫn cần thiết; không chỉ dựa vào hậu tố tên tài nguyên.
- Với Azure, có thể đối chiếu tenant/subscription/resource ID và managed identity; với GCP, đối chiếu project ID/number, service account và resource location. Công cụ, SDK và permission khác AWS; không áp nguyên xi mã STS.
- **Guard account không chạy** khi provider khác AWS. Ví dụ giúp minh họa nguyên tắc; các provider khác cần guard riêng thay vì cho rằng đã được kiểm tra.

### 10.3. Profile, runtime identity và endpoint có thể lệch nhau

Một lần triển khai có thể có các trạng thái:

| Spring profile | Runtime credential | Resource target | Đánh giá |
|---|---|---|---|
| dev | Role dev | Bucket dev | Hợp lệ nếu các quyền đúng |
| dev | Role dev | Bucket prod | Phải bị IAM chặn |
| prod | Role dev | Bucket prod | Lỗi cấu hình/identity, nên chặn startup |
| prod | Role prod | Bucket dev | Lỗi resource target, nên chặn cấu hình hoặc policy |
| prod | Role prod | Bucket prod | Đúng chiều danh tính/tài nguyên, vẫn cần kiểm tra RBAC/network |

Cần dựa vào **effective credentials**, không chỉ file cấu hình. Laptop đăng nhập CLI bằng user cá nhân có thể khác role của container; local profile, Azure CLI, gcloud và Application Default Credentials cũng không phải lúc nào giống workload identity của môi trường chạy.

## 11. Cấu hình CI/CD và IaC theo môi trường

### 11.1. Build một lần, triển khai theo đích

Một luồng triển khai dễ audit:

~~~mermaid
flowchart TD
    C["Commit + automated tests"] --> B["Build / scan một artifact"]
    B --> DEV["Deploy DEV bằng identity DEV"]
    DEV --> QA["Integration tests trên QA resources"]
    QA --> STG["Deploy STAGING cùng artifact"]
    STG --> G["Approval / policy / release gate"]
    G --> PRD["Deploy PROD bằng identity PROD"]
    PRD --> OBS["Health check, telemetry, rollback plan"]
~~~

Dùng cùng binary/container image digest cho các môi trường khi phù hợp để giảm chênh lệch mã. Những thứ thay đổi theo môi trường là **configuration, runtime identity, secret, endpoint và capacity**, được quản lý bởi pipeline và nền tảng.

### 11.2. IaC giúp tách và tái tạo resource

Terraform, AWS CloudFormation/CDK, Azure Bicep/ARM hoặc cơ chế IaC phù hợp của Google Cloud giúp mô tả resource định danh rõ ràng. Với Terraform, ví dụ, cần **state/backend và workspace/stack thực sự cô lập theo môi trường**; đặt \`dev\` và \`prod\` cùng một state có thể khiến thao tác plan/apply nhầm.

Một nguyên tắc quan trọng: pipeline dành cho dev chỉ có credential và quyền tạo/sửa **dev resources**. Pipeline production yêu cầu bước được xác nhận phù hợp; kiểm tra kế hoạch thay đổi (IaC plan), đánh giá xóa/recreate và migration trước khi apply.

### 11.3. Dùng federation thay cho key tĩnh khi có thể

- **AWS:** IAM role với OIDC/federation và trust policy hạn chế workflow/branch/environment.
- **Azure:** workload identity federation hoặc service connection phù hợp; Managed Identity cho runtime trên dịch vụ hỗ trợ.
- **Google Cloud:** Workload Identity Federation và service account được giới hạn theo môi trường.

Những cơ chế này giảm nhu cầu lưu static key trong CI. Vẫn phải giới hạn **trust conditions**, resource scope, thời hạn credential và audit.

### 11.4. Điều kiện vào production

Một production release nên có:
- Test unit và integration trên môi trường cô lập.
- Dependency/container security checks và secret scan.
- IaC/policy review cho IAM, network exposure, encryption, Region, replication và backup.
- Migration DB có khả năng tương thích ngược hoặc kế hoạch rollback.
- Xác nhận artifact digest, target account/subscription/project, Region và workload identity.
- Phương án rollback, health monitoring và owner xử lý sự cố.
- Cơ chế giảm tác động khi phát hành: canary, progressive rollout hoặc feature flag nếu phù hợp.

Một approval chỉ dựa trên tên job \`deploy-prod\` chưa đủ. Cần kiểm tra **đích triển khai thực tế** và quyền của token/credential mà pipeline đang sử dụng.

## 12. Secret và khóa mã hóa phải theo môi trường

Secret production như mật khẩu database, API key của đối tác, signing key hoặc token được quản lý riêng. Secret dev/test nên là giá trị thử nghiệm hoặc sandbox credential với phạm vi hẹp.

| Kiểu tài sản | Dev/test | Production | Vì sao tách |
|---|---|---|---|
| DB credentials | User/role test | DB user production | Ngăn test truy vấn dữ liệu thật |
| External API credentials | Provider sandbox account | Production integration account | Tránh giao dịch thật từ test |
| Signing/encryption key | Key riêng, vòng đời test | Key có chính sách bảo vệ riêng | Ngăn token/đối tượng test có thể dùng ở prod |
| Secret manager | Secret path/vault/project test | Secret path/vault/project prod | Phân quyền và rotation độc lập |
| Webhook endpoint | URL test | URL production | Tránh đưa event giả vào hệ thống thật |
| OAuth/OIDC client | Redirect URI/audience test | Client và audience production | Ngăn nhầm token, callback |
| Monitoring/export key | Sink test | Sink production | Tránh log nhầm hoặc trộn số liệu |

Khi cấp quyền đọc secret cho workload, phải xem **data plane permission** (ví dụ AWS Secrets Manager GetSecretValue, Azure Key Vault secret data role hoặc Google Secret Manager Secret Accessor) và encryption-key access nếu cần. Có quyền quản lý secret resource không đồng nghĩa có quyền đọc payload.

Không đặt secret thật trong biến môi trường được log ra, file \`application.yml\` commit lên Git, test fixture, ảnh container hoặc script chạy thử. Nếu secret cần xuất hiện trong runtime environment, kiểm soát quyền đọc env/process metadata và cơ chế rotate phù hợp.

## 13. Tách mạng, endpoint và vị trí lưu dữ liệu

IAM là lớp bảo vệ quan trọng, nhưng cũng cần xác định đường mạng:

- AWS: VPC/subnet/security group/route và VPC endpoint theo dịch vụ; có thể tách VPC/account theo môi trường.
- Azure: VNet, network security rules, Private Endpoint, firewall và DNS; phân tách subscription/resource group theo thiết kế.
- Google Cloud: VPC, firewall rules, Private Service Connect, VPC Service Controls hoặc cơ chế thích hợp tùy dịch vụ; phân tách project và quyền service account.

**Private endpoint không tự thay IAM/RBAC**, và không tự đưa dữ liệu về một Region khác. Tài nguyên production có thể cần network restriction, trong khi QA resource chỉ mở đường kết nối cho test runner. Nếu CI chạy bên ngoài cloud, cần thiết kế egress, firewall, private runner và DNS đúng.

### 13.1. Region, replica và residency

Production có thể yêu cầu data residency. Khi tạo staging, không mặc định rằng sử dụng Region khác hoặc chuyển backup/copy dữ liệu sang khu vực khác luôn được phép. Cần kiểm tra **dữ liệu chính, replica, backup, snapshot, object version, log, message và secret location** theo phạm vi yêu cầu.

**Cùng project/subscription/account không bảo đảm mọi resource cùng Region.** Kiểm tra metadata từng managed resource và cài đặt replication. Đối với Pub/Sub hoặc các hệ thống có API endpoint toàn cầu, endpoint không đủ để kết luận nơi message payload lưu trú.

### 13.2. Cross-environment access là ngoại lệ phải được kiểm soát

Một số hệ thống có shared services như central logging, artifact registry hoặc identity provider; có thể cần kết nối dev/staging/prod có giới hạn. Ghi rõ **luồng truy cập nào được cho phép**, principal nguồn, resource đích, action, network path và lý do. Không để runtime dev vô tình có quyền ghi vào production database/queue vì cả hai cùng tổ chức.

Nếu cần ingest bản sao production vào môi trường phân tích/test, thiết kế pipeline **một chiều**, lọc/mask dữ liệu có kiểm soát, tài khoản riêng, audit và chính sách retention/cleanup.

## 14. Quota, chi phí và việc dọn tài nguyên

Tách môi trường còn giúp quản lý tài chính: dev/test có thể dùng tier nhỏ, lịch dừng tự động và TTL cho resource tạm; production có budget, capacity planning và DR phù hợp. Tuy nhiên:

- **Dev không được tùy ý dùng production tier chỉ vì cùng biểu đồ kiến trúc.** Một số test cần giống prod về hành vi HA hoặc giới hạn; chỉ scale tương đương nơi thật sự cần.
- **Budget alert thường chỉ cảnh báo**, không phải cơ chế hard-stop tự động trên mọi cloud resource.
- **Quota có phạm vi cụ thể:** AWS account/Region, Azure subscription/Region, Google project/Region/API... tùy dịch vụ.
- **Tài nguyên không có traffic vẫn có thể có phí:** managed database, disk, premium messaging tier, reserved capacity, private networking, backup, retained logs.
- **Resource test có tag/label và hạn dùng**: \`environment=qa\`, \`service=orders\`, \`test-run-id\`, \`owner\`, \`expires-at\` khi công cụ hỗ trợ.
- **Deletion protection** có thể áp dụng cho resource production quan trọng; phải cân nhắc backup và quy trình thay đổi, không xem nó thay thế khôi phục dữ liệu.

Một job teardown của QA chỉ nên có quyền xóa resource **được tạo bởi run hoặc scope QA**. Dùng lệnh xóa với một tiền tố gần giống tên prod, hoặc sử dụng project mặc định không rõ ràng, là rủi ro cần chặn bằng resource ID và IAM.

## 15. Kịch bản kiểm thử tính cô lập

Kiểm thử phân tách môi trường là phần của **integration/security testing**, không chỉ xác nhận ứng dụng khởi động.

| Kiểm thử | Cách thực hiện trên môi trường test | Kết quả mong đợi |
|---|---|---|
| Đúng tài khoản/project/subscription | Kiểm tra effective runtime identity và resource IDs | Trùng environment manifest |
| Dev truy cập storage production | Dùng identity dev với resource ID prod trong test quyền an toàn | Bị từ chối; không đọc/ghi dữ liệu thật |
| Dev publish vào queue production | Kiểm tra chính sách quyền hoặc request được kiểm soát | Không được phép gửi |
| Staging đọc production secret | Kiểm tra policy permission theo scope | Bị từ chối |
| QA chạy migration | Chạy trên database QA được seed | Không thay đổi production schema |
| Cleanup test sau lỗi | Cố tình ngắt một run QA rồi chạy cleanup | Chỉ tài nguyên QA của run bị dọn |
| Thay target Region | Cấu hình đích không khớp trong environment QA | Deployment/startup validation thất bại |
| Cùng event ID được giao lại | Redelivery/duplicate trong queue QA | Không tạo tác dụng phụ kép |
| Pipeline prod dùng identity dev | Kiểm tra release gate/configured role | Bị chặn trước khi triển khai |
| Dùng sai key/token giữa môi trường | Test bằng token/secret test tại resource khác | Bị từ chối hoặc không hợp lệ |
| Budget/TTL của resource QA | Tạo resource có hạn dùng, kiểm tra cảnh báo | Không tồn tại resource test vô hạn ngoài kế hoạch |
| Production restore rehearsal | Khôi phục backup vào phạm vi cô lập, đúng quyền | Khôi phục được mà không ghi đè hệ thống thật |

Các bài thử **negative** nên dùng **IAM policy simulator/dry-run, quyền đọc policy hoặc resource thử nghiệm** khi có thể. Không xóa hoặc ghi lên resource production chỉ để chứng minh rằng nó bị từ chối.

### 15.1. Ma trận kiểm thử theo provider

| Yêu cầu | AWS | Azure | Google Cloud |
|---|---|---|---|
| Xác minh danh tính | STS GetCallerIdentity của workload | Managed Identity principal/tenant và token scope | Service account/ADC và project |
| Xác minh resource scope | Account ID, ARN, Region | Subscription ID, resource group, resource ID | Project ID/number, resource name/location |
| Kiểm tra chặn truy cập chéo | IAM + resource policy + SCP liên quan | Azure RBAC/role scope + network | IAM + Organization Policy/perimeter khi có |
| Kiểm tra storage đích | S3 bucket + Region | Storage account/container + location | Cloud Storage bucket + location |
| Kiểm tra messaging đích | SQS URL/SNS ARN | Service Bus namespace/queue/topic | Pub/Sub project/topic/subscription |
| Kiểm tra secret | Secrets Manager ARN, KMS key | Key Vault URI, data role/access policy | Secret resource name và IAM |
| Kiểm tra database | Endpoint/VPC + DB grants | SQL endpoint/network + DB permission | Cloud SQL endpoint/network + DB permission |

Không suy luận các bộ role hoặc cơ chế kiểm thử là hoàn toàn tương đương. Chúng thể hiện **mục tiêu cô lập tương tự** với triển khai khác nhau.

## 16. Một số lỗi thực tế và cách xử lý

### 16.1. Test chạy bằng credential production trên laptop

Developer đã đăng nhập AWS CLI/Azure CLI/gcloud vào scope production, trong khi Spring profile đang đặt \`test\`. SDK credential chain tự lấy principal đang có quyền rộng. Cần tách profile/tài khoản dev, dùng short-lived credential và kiểm tra effective identity trước khi chạy integration test; có thể chặn startup theo expected account/subscription/project.

### 16.2. Service Bus hoặc Pub/Sub consumer staging đọc message thật

Cả staging và prod dùng cùng queue/subscription hoặc IAM cấp quyền chung. Event thử nghiệm và event thật lẫn nhau; đôi khi một consumer ACK message mà consumer khác cần. Sửa bằng cách tạo resource messaging riêng, gán data role đúng, bảo vệ namespace/topic/subscription IDs trong deployment manifest, kiểm thử quyền từ chối cross-env.

### 16.3. Staging “giống prod” nhưng dùng chính database prod

Nhóm muốn dữ liệu thử giống thật nên trỏ staging JDBC URL vào database production. Migration hoặc job cleanup có thể làm sai dữ liệu. Tạo database staging độc lập và fixture, dùng bản sao đã xử lý an toàn nếu có lý do chính đáng, đồng thời xác minh database endpoint/principal khi khởi động.

### 16.4. CI/CD dùng một service account quyền Owner cho tất cả project

Runner bị lộ token hoặc pipeline sai target có thể sửa mọi môi trường. Thay bằng federation/short-lived identity tách theo environment, role tối thiểu, condition giới hạn branch/workflow, gate production và audit deployment. Resource-level policy không nên cho role CI ở dev quyền ghi prod.

### 16.5. Dọn QA bằng script quá rộng

Job test dùng wildcard \`orders-*\` rồi xóa nhầm bucket hoặc queue production. Cần project/account độc lập, tên tài nguyên được sinh và lưu theo test run, quyền teardown chỉ trên QA, kiểm tra ID trước khi xóa và deletion protection cho tài nguyên quan trọng.

### 16.6. Cùng secret dùng cho staging và production

Một secret bị lộ ở staging cho phép truy cập production API hoặc giải mã dữ liệu prod. Tách secret/key/API credential, sử dụng sandbox endpoint của bên thứ ba, gắn role/secret path theo môi trường, kiểm soát rotation và phạm vi token.

### 16.7. Network isolation đúng nhưng IAM vẫn quá rộng

Dev không kết nối được trực tiếp tới database prod nhưng có role quyền cao để sửa cấu hình firewall hoặc lấy account key. Cần bảo vệ cả **management plane** và **data plane**: ai được đổi network, lấy key, điều chỉnh IAM và ai được đọc dữ liệu.

## 17. Checklist review kiến trúc trước production

- **Resource ownership:** từng môi trường có account/subscription/project hoặc phạm vi được bảo vệ rõ ràng; ghi ID thay vì chỉ tên hiển thị.
- **Identity:** workload và CI/CD tách principal; role dev/QA không có quyền data hoặc admin lên prod.
- **Data:** database, object storage, queue, topic, secret, key, backup và log có ranh giới/vòng đời phù hợp.
- **Network:** DNS, endpoints, firewall/VPC/VNet/private access được kiểm tra theo môi trường; không dựa riêng vào tên profile.
- **Config:** có manifest nguồn đáng tin cậy cho expected environment, account/project, Region, resource IDs; guard phát hiện lệch trước traffic.
- **Release:** build artifact một lần, triển khai đúng target identity, có test gate, approval khi cần, kiểm tra IaC diff và rollback.
- **Test:** synthetic fixture, cleanup theo run ID, negative IAM tests, test duplicate/retry và restore cô lập.
- **Secret:** không dùng chung production credentials; không log hoặc commit secret; rotation và revoke làm được độc lập.
- **Resilience:** HA/backup/DR của prod theo RTO/RPO; dev/QA có giới hạn chi phí nhưng vẫn kiểm thử được hành vi cần thiết.
- **Cost:** budget/alert, labels/tags, quota, TTL và quy trình thu hồi test resources.
- **Observability:** log và metrics có environment/resource ID; audit chính sách, release, lỗi cross-env và thay đổi quyền.
- **Review:** định kỳ phát hiện resource orphan, quyền thừa, endpoint drift và ngoại lệ cross-env không còn cần.

## 18. Tổng kết

**Phân tách dev, test, staging và production là phân tách khả năng tác động vào dữ liệu và tài nguyên**, không chỉ khác tên file cấu hình. AWS thường dùng **account**; Azure thường dùng **subscription** kết hợp resource group và Entra identity; Google Cloud thường dùng **project**, folder và service account để tạo ranh giới quản trị. Ở cả ba cloud, IAM/RBAC, mạng, key, dữ liệu, endpoint và CI/CD quyết định mức cô lập thực sự.

Trong thực hành Spring Boot và Spring Cloud AWS/Azure/GCP, hãy bắt đầu từ **môi trường → principal → resource ID → quyền → dữ liệu → đường mạng → vòng đời triển khai/kiểm thử**. Khi từng ranh giới có bằng chứng kiểm chứng, nhóm phát triển có thể chạy thử nhanh mà không gây ảnh hưởng chéo lên hệ thống phục vụ khách hàng.

