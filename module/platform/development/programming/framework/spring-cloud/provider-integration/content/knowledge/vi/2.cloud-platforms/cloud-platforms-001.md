# Tài khoản, subscription, project, tenancy và ranh giới tài nguyên

Khi tích hợp Spring Boot với Amazon Web Services (AWS), Microsoft Azure hoặc Google Cloud, câu hỏi đầu tiên thường là “ứng dụng gọi API nào?”. Tuy nhiên, trước khi chọn Spring Cloud AWS, Spring Cloud Azure hay Spring Cloud GCP, cần xác định **ứng dụng đang chạy dưới danh tính nào, tài nguyên thuộc phạm vi quản trị nào và ai có quyền truy cập tài nguyên đó**. Một ứng dụng kết nối sai tài khoản hoặc project có thể đọc dữ liệu môi trường khác, phát sinh chi phí sai nơi, hoặc bị từ chối dù mã nguồn hoàn toàn đúng.

Bài học thuộc chương **Nền tảng đám mây**, tập trung vào các khái niệm tài khoản, subscription, project, tenant/tenancy và các ranh giới tài nguyên. Đây là nền tảng để thực hành cấu hình danh tính và quyền, tích hợp storage, messaging, dữ liệu, secret, kiểm thử tích hợp và so sánh các nhà cung cấp trong mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt **đơn vị danh tính**, **đơn vị quản trị tài nguyên**, **đơn vị thanh toán** và **đơn vị cô lập môi trường** ở ba cloud.
- Giải thích thứ bậc AWS Organizations → account; Azure tenant → management group → subscription → resource group; Google Cloud organization → folder → project.
- Xác định vì sao một workload Spring Boot có thể xác thực thành công nhưng vẫn không được phép truy cập bucket, queue, database hoặc secret.
- Thiết kế ranh giới dev, staging và production, chọn nơi cấp quyền thích hợp, áp dụng quyền tối thiểu và tránh phụ thuộc vào khóa truy cập dài hạn.
- Kiểm tra danh tính và phạm vi tài nguyên trước khi chạy ứng dụng hoặc bài kiểm thử tích hợp.

## 2. Phân biệt năm khái niệm dễ nhầm

**Identity (danh tính)** là chủ thể đang gọi dịch vụ: người dùng, IAM role, service principal, managed identity hoặc service account. Danh tính được dùng để xác thực (*authentication*), sau đó các chính sách quyết định hành động nào được phép (*authorization*).

**Tenant/tenancy** là phạm vi thuê và quản trị dịch vụ dùng chung. Từ “tenant” có cách dùng khác nhau giữa các nhà cung cấp: Azure có **Microsoft Entra tenant** là ranh giới danh tính; Google Cloud có **organization** gắn với tổ chức; AWS thường dùng **account** làm ranh giới cô lập chính. Không nên suy luận rằng ba thuật ngữ này tương đương một-một. “Multi-tenant application” còn là một khái niệm ở tầng ứng dụng, chỉ phần mềm phục vụ nhiều khách hàng; nó không bắt buộc mỗi khách hàng có một cloud account/subscription/project riêng.

**Account/subscription/project** là những đơn vị cơ bản để sở hữu và quản lý tài nguyên, nhưng vai trò chi tiết khác nhau. AWS account, Azure subscription và Google Cloud project thường là các đơn vị thích hợp để tách môi trường hoặc hệ thống.

**Resource hierarchy (phân cấp tài nguyên)** mô tả tài nguyên nằm dưới tổ chức, nhóm, tài khoản hoặc project nào. Các cấp cha thường truyền xuống chính sách quản trị, ràng buộc và quyền truy cập theo quy tắc riêng của từng cloud.

**Billing boundary (ranh giới chi phí)** là nơi tổng hợp, phân bổ hoặc giới hạn theo dõi chi phí. Ranh giới này **không tự động đồng nghĩa** với ranh giới bảo mật: nhiều account có thể thanh toán tập trung, nhiều project có thể dùng chung billing account, và một subscription vẫn có nhiều workload cần tách quyền.

| Góc nhìn | AWS | Microsoft Azure | Google Cloud |
|---|---|---|---|
| Đơn vị sở hữu tài nguyên chủ đạo | AWS account | Subscription | Project |
| Cấp tổ chức phía trên | AWS Organizations, organizational unit (OU) | Microsoft Entra tenant, management group | Organization, folder |
| Định danh phổ biến | Account ID (12 chữ số) | Subscription ID (UUID); tenant ID | Project ID, project number |
| Nhóm tài nguyên bên trong | Tài nguyên thuộc account, thường nằm trong Region; tag để phân loại | Resource group trong subscription | Tài nguyên thuộc project; folder là cấp cha của project |
| Danh tính workload thường dùng | IAM role và thông tin xác thực tạm thời | Managed identity hoặc service principal | Service account hoặc Workload Identity Federation |
| Thanh toán, phân bổ chi phí | Account; có thể consolidated billing trong Organizations | Subscription, billing account/profile và phạm vi liên quan | Billing account liên kết với project |
| Kiểm soát cấp tổ chức | Service control policy (SCP), guardrail khác | Azure Policy, RBAC, management group | Organization Policy, IAM policy |

> **Nguyên tắc:** trước một lời gọi cloud API, luôn trả lời được **ai gọi**, **gọi tài nguyên nào**, **tài nguyên thuộc phạm vi nào**, **chính sách nào cho phép hoặc chặn** và **chi phí ghi nhận ở đâu**.

## 3. AWS: account là ranh giới cô lập trọng yếu

### 3.1. Organizations, organizational unit và account

Một **AWS account** có Account ID riêng, chứa tài nguyên và là ranh giới quan trọng cho quyền, quota, cấu hình và phân bổ chi phí. **AWS Organizations** cho phép quản trị nhiều account, gom chúng vào **organizational unit (OU)** và áp dụng chính sách cấp tổ chức.

~~~mermaid
flowchart TD
    O["AWS Organizations"] --> OU1["OU: Non-production"]
    O --> OU2["OU: Production"]
    OU1 --> D["AWS account: dev"]
    OU1 --> S["AWS account: staging"]
    OU2 --> P["AWS account: production"]
    P --> S3["S3 bucket"]
    P --> Q["SQS queue"]
    P --> DB["RDS database"]
~~~

OU **không** chứa bucket hoặc database trực tiếp; nó nhóm các account. Tài nguyên thuộc một account cụ thể. Một số dịch vụ có phạm vi toàn account hoặc toàn cầu theo mô hình dịch vụ, trong khi nhiều tài nguyên khác (như SQS queue, RDS instance) có thêm phạm vi **Region**. Vì vậy, account và Region là hai chiều khác nhau: chọn đúng account nhưng sai Region vẫn có thể dẫn đến lỗi “không tìm thấy tài nguyên”.

**Service control policy (SCP)** xác định giới hạn quyền tối đa đối với các principal chịu sự điều chỉnh của SCP trong tổ chức; **SCP tự nó không cấp quyền**. Một IAM role phải được cho phép bởi các chính sách IAM/resource policy có liên quan và không bị các cơ chế chặn khác ngăn cản.

**IAM role** có thể được workload sử dụng qua EC2 instance profile, ECS task role, EKS workload identity hoặc cơ chế tương đương. Ứng dụng nên nhận **thông tin xác thực tạm thời**, thay vì đóng gói access key cố định trong file cấu hình.

### 3.2. Truy cập giữa các AWS account

Giả sử ứng dụng chạy trong account *dev* nhưng phải đọc object trong bucket thuộc account *shared-data*. Hai account không tự có quyền với nhau. Một phương án là thiết lập **cross-account AssumeRole**: role ở account đích có trust policy cho phép principal nguồn đảm nhận role, còn permission policy và resource policy liên quan cấp hành động S3 phù hợp. Bucket policy, KMS key policy, điều kiện mạng và giới hạn cấp tổ chức vẫn có thể ảnh hưởng kết quả.

Không thể kết luận “đã đăng nhập AWS” đồng nghĩa “đọc được mọi S3 bucket”. Khi debug, cần kiểm tra **principal thực tế**, **account sở hữu bucket**, **Region**, **action**, **resource ARN** và các chính sách liên quan.

## 4. Azure: tenant, subscription và resource group có vai trò riêng

### 4.1. Ba lớp không thể thay thế nhau

- **Microsoft Entra tenant** quản lý thư mục danh tính và cơ chế xác thực. Một tổ chức có thể có nhiều tenant; một subscription có liên kết với một tenant tại một thời điểm và có thể chuyển tenant theo quy trình quản trị.
- **Management group** tổ chức các subscription để áp chính sách quản trị và quyền theo cấu trúc cấp trên.
- **Subscription** là ranh giới quan trọng cho quản trị, thanh toán, nhiều quota và phân tách môi trường.
- **Resource group** là nhóm logic các tài nguyên bên trong **một subscription**, phục vụ quản trị vòng đời, RBAC, policy và thao tác triển khai. Các tài nguyên trong cùng resource group **không bắt buộc** ở cùng Region; bản thân resource group cũng có thuộc tính location cho metadata quản trị.

~~~mermaid
flowchart TD
    T["Microsoft Entra tenant"] --> M["Management group"]
    M --> D["Subscription: dev"]
    M --> P["Subscription: production"]
    P --> R1["Resource group: rg-orders"]
    P --> R2["Resource group: rg-shared"]
    R1 --> B["Storage account / Blob container"]
    R1 --> SB["Service Bus namespace / queue"]
    R2 --> KV["Key Vault"]
~~~

Azure RBAC có các phạm vi thường gặp: **management group → subscription → resource group → resource**. Quyền cấp ở phạm vi cha có thể áp dụng cho các phạm vi con. Đây là lý do cần tránh cấp quyền quá rộng ở subscription khi một dịch vụ chỉ cần thao tác với một storage account hoặc một queue.

### 4.2. Control plane khác data plane

Trong Azure, quyền **quản lý tài nguyên** và quyền **đọc/ghi dữ liệu** thường là hai nhóm riêng. Ví dụ, role **Reader** trên storage account giúp xem metadata quản trị nhưng **không mặc nhiên** cho phép đọc nội dung blob bằng Microsoft Entra ID. Workload đọc blob cần một data role thích hợp (chẳng hạn **Storage Blob Data Reader**) ở phạm vi cần thiết, cùng các điều kiện truy cập liên quan.

**Managed identity** là danh tính do Azure quản lý cho workload chạy trên dịch vụ hỗ trợ, giúp ứng dụng lấy token mà không lưu client secret dài hạn. RBAC phải được gán cho managed identity tại đúng tài nguyên hoặc cấp cha phù hợp. Nếu ứng dụng cần truy cập resource ở subscription khác, phải xem xét quyền trong subscription đích và quan hệ tenant; cùng tenant không tự động mang lại quyền. Với các tenant khác nhau, cần cấu hình thêm cơ chế tin cậy hoặc truy cập liên tenant phù hợp.

## 5. Google Cloud: project là ranh giới triển khai phổ biến

### 5.1. Organization, folder, project

Trong Google Cloud, **organization** là nút tổ chức cao nhất nếu doanh nghiệp có organization resource; **folder** là cấp nhóm tùy chọn; **project** là nơi sở hữu phần lớn tài nguyên và bật API dịch vụ. Tổ chức nhỏ hoặc môi trường thử nghiệm có thể có project không nằm dưới organization.

~~~mermaid
flowchart TD
    O["Google Cloud organization"] --> F1["Folder: Non-production"]
    O --> F2["Folder: Production"]
    F1 --> D["Project: orders-dev"]
    F2 --> P["Project: orders-prod"]
    P --> GCS["Cloud Storage bucket"]
    P --> PS["Pub/Sub topic / subscription"]
    P --> SM["Secret Manager secret"]
    BA["Cloud Billing account"] -. "Liên kết thanh toán" .-> D
    BA -. "Liên kết thanh toán" .-> P
~~~

**Project ID** là chuỗi định danh được dùng rộng rãi trong API và phải duy nhất trên phạm vi Google Cloud; **project number** là định danh số. Tên hiển thị của project khác với hai định danh này. Một project có thể liên kết với một Cloud Billing account tại một thời điểm; nhiều project có thể cùng dùng một billing account. Billing account là quan hệ thanh toán, **không phải** nút cha trong cây resource hierarchy.

**IAM policy** có thể được gán tại organization, folder, project hoặc tài nguyên cụ thể tùy dịch vụ. **Organization Policy** áp dụng các ràng buộc quản trị như hạn chế vị trí hoặc cách dùng tài nguyên; tương tự SCP ở mục tiêu guardrail, nhưng cú pháp và mô hình đánh giá **khác AWS**.

### 5.2. Service account và quyền qua project

Ứng dụng Spring Boot trên Cloud Run, GKE hoặc hạ tầng hỗ trợ thường sử dụng **service account** qua cơ chế cấp token an toàn của môi trường chạy. Nếu workload trong project A cần truy cập bucket ở project B, quản trị viên phải cấp quyền phù hợp cho principal của workload trên tài nguyên hoặc phạm vi đích; việc cả hai project thuộc cùng organization **không tự cấp quyền**.

Khi triển khai bên ngoài Google Cloud, **Workload Identity Federation** có thể giúp workload dùng danh tính từ hệ thống được tin cậy để nhận thông tin xác thực ngắn hạn, giảm nhu cầu lưu JSON service-account key. Luôn kiểm tra API cần dùng đã được bật trên project có liên quan và các điều kiện IAM, quota, vị trí dữ liệu.

## 6. Ranh giới tài nguyên: năm câu hỏi cần kiểm tra

Một “boundary” trong thực tế gồm nhiều lớp độc lập. Không có một ID nào tự xác định toàn bộ quyền và phạm vi ứng dụng.

| Ranh giới | Câu hỏi xác minh | Lỗi thường gặp khi tích hợp |
|---|---|---|
| **Identity** | Workload thật sự lấy credential/token của ai? | Laptop dùng tài khoản cá nhân, môi trường deploy dùng role/service account khác |
| **Authorization** | Principal được cấp hành động nào trên resource cụ thể? | Có quyền tạo/xem metadata, nhưng thiếu quyền đọc object/message/secret |
| **Resource ownership** | Bucket, database, queue, secret nằm ở account/subscription/project nào? | Endpoint đúng định dạng nhưng trỏ sang môi trường khác |
| **Location và network** | Resource ở Region/location nào; endpoint, VPC/VNet/firewall/private endpoint cho phép đường đi nào? | IAM đã đúng nhưng mạng từ chối kết nối, hoặc gọi sai Region |
| **Governance, billing và quota** | Chính sách cấp trên, budget, quota và nhãn chi phí áp dụng ở đâu? | API bị chặn bởi policy; quota hết; chi phí dồn vào project sai |

Các lớp này tương tác với nhau:

~~~mermaid
flowchart LR
    App["Spring Boot application"] --> ID["Runtime identity"]
    ID --> Auth["IAM / RBAC policy evaluation"]
    Auth --> Net["Network + location constraints"]
    Net --> Res["Storage / messaging / database / secret"]
    Gov["Organization guardrails"] -. "Giới hạn" .-> Auth
    Scope["Account / subscription / project"] -. "Sở hữu" .-> Res
    Scope -. "Chi phí và quota" .-> Cost["Billing / quota"]
~~~

Sơ đồ là **mô hình kiểm tra khái niệm**, không phải thứ tự đánh giá kỹ thuật cố định của mọi cloud. Một request có thể thất bại ở nhiều lớp; một lỗi HTTP 403 không đủ để xác định nguyên nhân chỉ từ tên cloud.

## 7. Thiết kế dev, staging và production

Ví dụ, nhóm phát triển dịch vụ đặt hàng có ba môi trường. Mỗi môi trường có bucket chứa hóa đơn, queue xử lý đơn, database và secret riêng. Để giảm nguy cơ tác động chéo, nên xây dựng một phạm vi quản trị chính cho mỗi môi trường:

| Môi trường | AWS | Azure | Google Cloud |
|---|---|---|---|
| Development | Account `orders-dev` | Subscription `orders-dev` với các resource group liên quan | Project `orders-dev` |
| Staging | Account `orders-staging` | Subscription `orders-staging` | Project `orders-staging` |
| Production | Account `orders-prod` | Subscription `orders-prod` | Project `orders-prod` |

Đây là **mẫu thiết kế**, không phải một yêu cầu bắt buộc của từng cloud. Quy mô nhỏ có thể gom nhiều ứng dụng trong một subscription/project; khi đó phải dùng resource-level IAM/RBAC, naming, network và policy rõ ràng. Với dữ liệu nhạy cảm hoặc nhiều nhóm độc lập, tách account/subscription/project thường giúp quản lý blast radius, quyền và chi phí dễ hơn.

Ví dụ về ma trận quyền mong muốn:

| Danh tính | Storage dev | Queue dev | Storage prod | Queue prod |
|---|---|---|---|---|
| Workload dev | Đọc/ghi cần thiết | Gửi/nhận cần thiết | Không cấp | Không cấp |
| Workload prod | Không cấp | Không cấp | Đọc/ghi cần thiết | Gửi/nhận cần thiết |
| CI/CD deployment | Triển khai theo scope dev | Triển khai theo scope dev | Chỉ qua pipeline và phê duyệt prod | Chỉ qua pipeline và phê duyệt prod |
| Nhân sự vận hành | Theo vai trò hỗ trợ | Theo vai trò hỗ trợ | Quyền tối thiểu, có kiểm soát | Quyền tối thiểu, có kiểm soát |

Tách môi trường có hiệu lực khi **cả principal lẫn tài nguyên đều tách**, chính sách cấp tổ chức hạn chế leo thang quyền và pipeline chọn chính xác đích triển khai. Đặt tên `prod` trên một resource **không tự tạo ranh giới bảo mật**. Nếu dùng shared services, cần lập sơ đồ các truy cập liên môi trường được cho phép và rà soát chúng riêng.

### 7.1. Quy tắc đặt tên và tagging/labeling

Tên nên thể hiện hệ thống, môi trường, chức năng và vị trí khi cần, ví dụ `orders-prod-events` hoặc `rg-orders-prod-sea`. Tuy nhiên, quy tắc đặt tên thực tế khác nhau theo dịch vụ (ký tự được phép, độ dài, tính duy nhất), nên phải kiểm tra ràng buộc riêng trước khi tạo resource.

Thống nhất các tag/label như `environment`, `service`, `team`, `cost-center` để lọc và phân bổ chi phí. **Tag/label không thay thế IAM/RBAC**, trừ trường hợp chính sách cụ thể chủ động dùng chúng làm điều kiện cấp quyền. Thiết lập budget và cảnh báo tại phạm vi billing hoặc đơn vị tài nguyên phù hợp; budget alert thông thường **không phải công tắc tự động chặn mọi chi tiêu**.

## 8. Áp dụng khi cấu hình Spring Boot và Spring Cloud

### 8.1. Định danh phạm vi chạy khác với cấu hình tài nguyên đích

Một ứng dụng cần ít nhất hai nhóm thông tin:

1. **Ngữ cảnh chạy:** identity thực tế do môi trường cung cấp, cloud/Region hoặc project mặc định, và phạm vi mà deployment được phép sử dụng.
2. **Đích tích hợp:** tên hoặc định danh bucket/container, queue/topic, database, secret và endpoint/Region của chúng.

Không nên đoán đích tích hợp chỉ từ tên profile Spring Boot. Profile `prod` chỉ chọn cấu hình ứng dụng; nó **không bảo đảm** credential đang thuộc production account/subscription/project. Ngược lại, chỉ có credential production cũng không tự chọn đúng storage account hoặc bucket.

| Nhu cầu Spring Boot | AWS | Azure | Google Cloud |
|---|---|---|---|
| Object storage | Amazon S3 qua Spring Cloud AWS / AWS SDK | Azure Blob Storage qua Spring Cloud Azure / Azure SDK | Cloud Storage qua Spring Cloud GCP / Google Cloud Java client |
| Messaging | SQS/SNS hoặc dịch vụ phù hợp | Service Bus hoặc dịch vụ phù hợp | Pub/Sub |
| Secret | AWS Secrets Manager / Parameter Store | Azure Key Vault | Secret Manager |
| Danh tính ưu tiên trên cloud | IAM role với credential tạm thời | Managed identity | Service account qua môi trường chạy |
| Phạm vi cần xác minh | Account ID, Region, resource ARN | Tenant ID, subscription ID, resource ID | Project ID/number, resource name/location |

Phiên bản các thư viện Spring Cloud và Spring Boot phải dùng **BOM tương thích**. Các thuộc tính cấu hình và starter cụ thể có thể thay đổi giữa các phiên bản; bài này tập trung vào ranh giới tài nguyên, không coi ví dụ minh họa là một cấu hình đầy đủ sẵn dùng cho mọi release.

Ví dụ ứng dụng dùng một tập cấu hình **do nhóm tự định nghĩa** để kiểm tra đích môi trường trước khi tạo client:

~~~yaml
app:
  deployment:
    environment: prod
    provider: aws
    expected-account-id: "123456789012" # ID ví dụ, thay bằng giá trị của hệ thống
  storage:
    bucket: orders-prod-invoices
    region: ap-southeast-1
~~~

Các thuộc tính dưới `app.*` **không phải thuộc tính cấu hình tự động của Spring Cloud**. Chúng chỉ có ý nghĩa khi ứng dụng tự bind và kiểm tra chúng. Ví dụ, với AWS SDK v2, ứng dụng có thể thực hiện bước xác nhận account lúc khởi động:

~~~java
import software.amazon.awssdk.services.sts.StsClient;

public final class AwsAccountGuard {
    public static void verifyAccount(String expectedAccountId) {
        try (StsClient sts = StsClient.create()) {
            String actual = sts.getCallerIdentity().account();
            if (!expectedAccountId.equals(actual)) {
                throw new IllegalStateException(
                    "Unexpected AWS account: " + actual);
            }
        }
    }
}
~~~

Mã minh họa cần dependency **AWS SDK v2 STS** và được gọi ở bước khởi tạo ứng dụng. Nó chỉ kiểm tra **account của credential đang dùng**, không chứng minh bucket đích thuộc account đó, không thay thế kiểm tra IAM và không kiểm tra Region. Trong kiến trúc AssumeRole, account trả về là account của role đang được đảm nhận. Với Azure/GCP, có thể thực hiện kiểm tra tương tự bằng cách đối chiếu tenant/subscription/project của workload và resource ID từ hệ thống quản lý cấu hình; không nên cho rằng mọi SDK tự xác minh quan hệ này.

### 8.2. Tìm và xác minh ngữ cảnh bằng CLI

Các lệnh sau là thao tác **đọc thông tin hiện tại**, hữu ích khi so sánh môi trường local và cấu hình deployment. Chúng yêu cầu CLI đã được cài đặt và đăng nhập hoặc được cấp credential thích hợp.

**AWS CLI**

~~~bash
aws sts get-caller-identity
aws configure get region
~~~

`get-caller-identity` cho biết principal ARN và Account ID của credential hiệu lực. Giá trị Region được thiết lập trong profile CLI không bảo đảm mọi client SDK dùng đúng Region đó; biến môi trường và cấu hình tường minh có thể ưu tiên khác nhau.

**Azure CLI**

~~~bash
az account show --query "{tenantId:tenantId,subscriptionId:id,name:name}" --output json
az group list --query "[].{name:name,location:location}" --output table
~~~

`az account show` cho biết subscription mặc định của phiên Azure CLI. Quyền của managed identity khi ứng dụng chạy trên Azure có thể **khác hoàn toàn** quyền trong phiên đăng nhập trên laptop.

**Google Cloud CLI**

~~~bash
gcloud auth list --filter="status:ACTIVE" --format="value(account)"
gcloud config get-value project
gcloud projects describe PROJECT_ID
~~~

Thay `PROJECT_ID` bằng project thực tế. Tài khoản người dùng đang active trong `gcloud`, **Application Default Credentials (ADC)** dùng bởi SDK và service account của runtime có thể khác nhau; cần xác minh loại credential mà ứng dụng thật sự sử dụng.

### 8.3. Kiểm thử tích hợp có ranh giới rõ ràng

Khi thử upload object, gửi message hoặc đọc secret từ Spring Boot:

1. Xác nhận scope của môi trường kiểm thử và principal thực thi. Dùng fixture riêng cho test, tránh dữ liệu thật.
2. Tạo hoặc tham chiếu resource test trong đúng account/subscription/project và đúng Region/location; bảo đảm role được cấp quyền tối thiểu.
3. Đặt tên/resource ID tường minh trong cấu hình test, không tái sử dụng endpoint production theo mặc định.
4. Thực hiện vòng ghi → đọc/nhận → dọn dữ liệu test, quan sát log và kiểm tra chi phí/quota liên quan.
5. Chạy lại dưới danh tính giống production ở môi trường staging; kiểm tra cả trường hợp **bị từ chối** khi cố truy cập phạm vi ngoài quyền.

**Mock/emulator/local test** giúp kiểm tra logic gọi API, nhưng không xác nhận IAM/RBAC, policy tổ chức, mạng riêng hay quota thực trên cloud. Vì vậy, tích hợp hoàn chỉnh cần một lớp kiểm thử trên hạ tầng cloud với tài nguyên cô lập và kiểm soát chi phí.

## 9. Những nhầm lẫn thường gây sự cố

| Nhận định sai | Điều cần hiểu đúng |
|---|---|
| “Đã đăng nhập đúng cloud thì có thể đọc tài nguyên” | Authentication chỉ xác định principal; authorization được xét trên action, resource, policy và điều kiện cụ thể. |
| “Azure tenant chính là subscription” | Tenant quản lý danh tính; subscription quản trị tài nguyên/thanh toán, có thể có nhiều subscription dưới một tenant. |
| “Resource group quyết định Region của mọi tài nguyên Azure” | Resource group có location riêng cho metadata; các resource bên trong có thể ở nhiều Region. |
| “Google Cloud billing account là cha của project” | Billing account được liên kết với project để tính tiền, không nằm trong cây organization/folder/project. |
| “AWS OU chứa trực tiếp bucket hoặc database” | OU nhóm account; resource thuộc một account, với phạm vi dịch vụ/Region cụ thể. |
| “Cùng organization/tenant nghĩa là các workload truy cập được nhau” | Việc cùng tổ chức không tự cấp quyền qua account, subscription hoặc project. |
| “Role Reader có thể đọc blob content” | Azure management-plane Reader không mặc nhiên có data-plane permission cho blob. |
| “Đặt profile Spring thành prod là đã cô lập production” | Spring profile không thay thế credential, phạm vi tài nguyên và policy cloud. |
| “Có IAM đúng thì kết nối chắc chắn thành công” | Network, Region, encryption key, endpoint, policy cấp cao và trạng thái dịch vụ vẫn có thể chặn. |
| “Budget alert sẽ dừng toàn bộ tài nguyên khi vượt ngưỡng” | Cảnh báo chi phí thường chỉ thông báo; muốn áp biện pháp tự động phải cấu hình riêng và hiểu tác động. |

## 10. Tình huống chẩn đoán thực tế

**Tình huống A — S3 trả AccessDenied khi chạy trên ECS:** Ứng dụng local dùng IAM user quyền rộng, còn ECS task dùng task role giới hạn. Cần lấy account/principal của task runtime, đối chiếu bucket owner, IAM policy, bucket policy và KMS policy nếu object mã hóa bằng KMS. Không giải quyết bằng cách gắn quyền quản trị toàn account.

**Tình huống B — Azure Blob hoạt động với connection string nhưng lỗi 403 khi chuyển sang managed identity:** Connection string có thể dùng cơ chế shared key, trong khi managed identity đi qua Microsoft Entra và Azure RBAC. Cần cấp đúng **data role** cho managed identity trên storage account/container và kiểm tra network/firewall. Thêm role Reader thông thường không giải quyết quyền đọc blob.

**Tình huống C — Pub/Sub không tìm thấy topic khi deploy GCP:** Ứng dụng có thể đang dùng project mặc định khác với project chứa topic. Cần kiểm tra `project-id` mà client sử dụng, tên resource đầy đủ, service account chạy workload, quyền với topic/subscription và API bật ở project thích hợp.

**Tình huống D — Dữ liệu staging xuất hiện trong production:** Profile Spring thay đổi nhưng một biến môi trường vẫn trỏ đến queue staging, hoặc pipeline deploy bằng service principal/service account được cấp quyền ở cả hai nơi. Khắc phục bằng cách tách credential, xác thực resource ID trước khi khởi động, kiểm soát quyền liên môi trường và thêm kiểm thử truy cập bị từ chối.

## 11. Checklist trước khi kết nối một dịch vụ managed

- **Danh tính:** xác định runtime principal, cách nhận token/credential và thời hạn của credential; ưu tiên cơ chế danh tính do nền tảng quản lý.
- **Quyền:** chỉ cấp action cần dùng tại resource/scope nhỏ nhất có thể; phân biệt quyền quản trị với quyền thao tác dữ liệu.
- **Tài nguyên:** ghi nhận account/subscription/project, resource ID hoặc ARN, Region/location và endpoint cụ thể; kiểm tra riêng cross-account/cross-project.
- **Bảo mật:** kiểm tra secret, encryption key, network/private endpoint, policy cấp tổ chức và nhật ký audit; không đưa khóa truy cập dài hạn vào source hoặc artifact.
- **Vận hành:** có quy tắc tách môi trường, tag/label, budget, quota, vòng đời cleanup và phương án kiểm thử tích hợp cô lập.

## 12. Kết luận và bước tiếp theo

AWS đặt trọng tâm cô lập ở **account**; Azure phân tách rõ **Entra tenant** cho danh tính, **subscription** cho quản trị/chi phí và **resource group** cho nhóm tài nguyên; Google Cloud dùng **organization/folder/project**, trong đó **project** thường là phạm vi triển khai và cấp quyền chính. Các khái niệm này có nét tương đồng nhưng khác nhau về mô hình policy, billing, quota và quan hệ giữa danh tính với tài nguyên.

Trước khi viết mã Spring Cloud AWS, Spring Cloud Azure hoặc Spring Cloud GCP, hãy vẽ sơ đồ **principal → quyền → tài nguyên → account/subscription/project → vị trí → billing** cho dịch vụ dự kiến. Khi mô hình này rõ ràng, việc tích hợp storage, messaging, database, secret và thiết kế kiểm thử sẽ dễ kiểm soát hơn, đồng thời giảm lỗi truy cập nhầm môi trường.
