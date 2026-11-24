# Tách việc cấp phát tài nguyên khỏi thao tác xử lý nghiệp vụ

Một ứng dụng Spring Boot có thể cần Event Hubs, Event Grid, Service Bus, Blob Storage, S3, SQS, Pub/Sub, Cloud Storage hoặc database managed để xử lý nghiệp vụ. Các tài nguyên này phải được tạo, cấu hình và cấp quyền trước khi ứng dụng sử dụng. Nếu để từng instance tự tạo tài nguyên khi khởi động hoặc trong luồng xử lý request, ứng dụng sẽ phải giữ quyền quản trị rộng, nhiều replica có thể tranh chấp khi tạo cùng một resource, startup phụ thuộc vào thao tác quản trị và việc thay đổi hạ tầng trở nên khó kiểm soát.

Cách tổ chức phù hợp là tách **provisioning** khỏi **runtime**. Pipeline hạ tầng dùng Infrastructure as Code (IaC) để tạo tài nguyên, network, identity và role assignment. Pipeline ứng dụng triển khai artifact đã build. Khi chạy, Spring Boot chỉ nhận endpoint, resource ID, tên queue/topic/container và credential của workload identity để gọi data plane API phục vụ nghiệp vụ. Việc tạo hoặc thay đổi tài nguyên được quản lý bằng quy trình triển khai riêng, có kiểm tra thay đổi và kiểm soát vòng đời.

Bài học thuộc chương **Triển khai ứng dụng** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào ranh giới giữa cấp phát tài nguyên và xử lý nghiệp vụ, cách quản lý hạ tầng bằng IaC, phân tách quyền control plane/data plane, truyền outputs vào cấu hình Spring Boot và vận hành nhiều môi trường.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt provisioning, application deployment và business runtime.
- Giải thích vì sao ứng dụng không nên tự tạo cloud resource trong mỗi lần startup hoặc request.
- Mô tả ranh giới control plane và data plane của AWS, Azure và Google Cloud.
- Chọn CloudFormation, Bicep, Terraform hoặc Google Cloud Infrastructure Manager cho từng quy trình.
- Khai báo resource, dependency, output và identity bằng IaC.
- Tách quyền của pipeline provisioner khỏi quyền của workload runtime.
- Truyền endpoint/resource name từ pipeline vào Spring Boot bằng externalized configuration.
- Dùng Managed Identity, IAM role hoặc Workload Identity thay cho credential quản trị tĩnh.
- Quản lý database migration và secret theo lifecycle riêng.
- Kiểm soát drift, thay đổi phá hủy, chi phí và thứ tự rollout.
- Kiểm thử rằng ứng dụng chỉ sử dụng các resource đã được provision và không có quyền tạo resource ngoài dự kiến.

## 2. Ba loại công việc cần tách biệt

Một hệ thống cloud-native thường có ba loại thay đổi khác nhau:

| Loại công việc | Nội dung | Thời điểm thực hiện | Danh tính điển hình |
|---|---|---|---|
| **Infrastructure provisioning** | Tạo VPC/VNet, subnet, storage, queue, topic, Event Hubs, database, key vault, identity, role assignment | Trước khi triển khai workload hoặc khi thay đổi hạ tầng | Pipeline provisioner hoặc platform team |
| **Application deployment** | Build image/JAR, deploy revision, cấu hình replicas, health probe, rollout/rollback | Mỗi lần phát hành phiên bản ứng dụng | CI/CD deploy identity |
| **Business runtime** | Gửi event, nhận message, đọc/ghi object, truy vấn database, xử lý request | Khi ứng dụng đang phục vụ | Workload identity của ứng dụng |

Ba loại công việc có thể chạy trong cùng một pipeline tổng thể, nhưng cần có bước, quyền và trạng thái riêng. Ví dụ, pipeline release có thể gọi module IaC trước rồi mới deploy ứng dụng; điều đó không có nghĩa Java service phải gọi API quản trị để tạo Event Hub mỗi khi có request.

### 2.1. Provisioning

Provisioning mô tả trạng thái mong muốn của hạ tầng:
- Resource nào phải tồn tại?
- Resource thuộc subscription/account/project và region nào?
- Cấu hình network, encryption, retention, capacity và backup ra sao?
- Workload identity nào được phép gửi/nhận dữ liệu?
- Ai có quyền thay đổi hoặc xóa resource?
- Resource có cần giữ lại khi stack/module bị xóa không?

Provisioning cần có lịch sử thay đổi, review, plan/preview và khả năng tái tạo môi trường.

### 2.2. Application deployment

Application deployment đưa artifact đã build tới compute platform như Kubernetes, App Service, ECS, Cloud Run hoặc VM. Deployment cấu hình image/version, environment variables, secret references, replicas, probes và rollout strategy.

Deploy một phiên bản mới không nên tạo lại storage account, queue hoặc database. Nếu một ứng dụng cần đổi resource, thay đổi đó phải xuất hiện rõ trong change của IaC và config contract.

### 2.3. Business runtime

Runtime chỉ sử dụng các resource đã được cấp:
- Gửi event tới topic có sẵn.
- Đọc message từ queue/subscription có sẵn.
- Ghi object vào bucket/container có sẵn.
- Gọi database có sẵn.
- Đọc secret theo quyền của workload.
- Phản hồi lỗi rõ ràng khi resource chưa tồn tại hoặc identity thiếu quyền.

SDK client builder thường chỉ tạo client object và cấu hình kết nối. Lệnh như create bucket, create queue, create topic, create container hoặc tạo role assignment mới là thao tác provisioning. Không nhầm việc khởi tạo SDK client với việc tạo cloud resource.

## 3. Kiến trúc tách provisioning và runtime

~~~mermaid
flowchart TD
    DEV["Platform / application team"] --> CODE["IaC source + application source"]
    CODE --> PIPE["CI/CD pipeline"]
    PIPE --> VALIDATE["Validate, policy check, plan / what-if"]
    VALIDATE --> APPROVE["Review infrastructure change"]
    APPROVE --> PROVISION["Provision resources + identity + RBAC"]
    PROVISION --> OUTPUTS["Resource outputs / config contract"]
    OUTPUTS --> DEPLOY["Deploy application artifact"]
    DEPLOY --> RUNTIME["Spring Boot runtime"]
    RUNTIME --> DATA["Existing managed resources"]
    RUNTIME --> OBS["Logs, metrics, traces"]
    PROVISION --> AUDIT["Infrastructure state / audit"]
    DEPLOY --> AUDIT
~~~

Luồng này tạo ra một hợp đồng rõ ràng giữa platform và application:

1. IaC xác định resource và cấu hình mong muốn.
2. Pipeline kiểm tra thay đổi trước khi áp dụng.
3. Provisioner tạo resource và gán quyền cho workload identity.
4. Pipeline thu thập output không nhạy cảm như endpoint, resource ID và tên destination.
5. Application deployment đưa các giá trị đó vào cấu hình môi trường.
6. Spring Boot khởi tạo SDK client bằng credential runtime.
7. Business handler chỉ gọi data plane API.

Nếu provisioning thất bại, pipeline dừng trước khi deploy revision phụ thuộc vào resource đó. Nếu ứng dụng không thể kết nối resource, readiness check và smoke test phát hiện lỗi trước khi nhận traffic.

## 4. Vì sao không tạo cloud resource trong luồng nghiệp vụ?

Để application tự tạo resource có thể thuận tiện trong một demo nhỏ, nhưng gây ra nhiều vấn đề khi chạy production:

- **Quyền quá rộng:** ứng dụng phải có quyền quản lý resource, tạo policy hoặc gán role thay vì chỉ có quyền gửi/nhận dữ liệu.
- **Race condition:** nhiều pod khởi động cùng lúc có thể đồng thời tạo queue, container hoặc subscription.
- **Startup chậm:** ứng dụng phải chờ API quản trị, retry và eventual consistency trước khi sẵn sàng.
- **Khó kiểm soát chi phí:** mỗi lần deploy hoặc request có thể tạo resource mới ngoài dự kiến.
- **Drift:** cấu hình do code runtime tạo ra không còn được quản lý trong IaC state/template.
- **Lifecycle không rõ:** không biết resource nào được giữ lại, resource nào có thể xóa khi scale down.
- **Khó audit:** thao tác quản trị lẫn với hoạt động nghiệp vụ, khó xác định ai đã thay đổi hạ tầng.
- **Khó rollback:** rollback ứng dụng không tự đưa resource về trạng thái cũ một cách an toàn.

Ví dụ, một handler tạo storage container nếu chưa tồn tại trước khi upload file. Khi có 20 replica, tất cả có thể cùng gọi create-if-not-exists. Dù SDK hỗ trợ thao tác idempotent, ứng dụng vẫn cần quyền quản trị, tạo thêm coupling và có thể che giấu việc pipeline chưa provision đúng resource.

Trong production, container phải được tạo bởi IaC. Runtime chỉ lấy client cho container đã biết và ghi object. Nếu container bị thiếu, ứng dụng báo lỗi readiness/operation để platform sửa provisioning.

## 5. Control plane và data plane

Cloud provider thường tách API quản lý tài nguyên khỏi API sử dụng dữ liệu.

| Cloud | Control plane / management API | Data plane / runtime API |
|---|---|---|
| AWS | CloudFormation, EC2, IAM, S3 control APIs, SQS CreateQueue | S3 GetObject/PutObject, SQS SendMessage/ReceiveMessage, EventBridge PutEvents |
| Azure | Azure Resource Manager, Microsoft.Resources/deployments, role assignments | Blob data operations, Service Bus Data Sender/Receiver, Event Hubs send/receive |
| Google Cloud | Resource Manager, Cloud APIs quản lý project/resource/IAM | Pub/Sub publish/pull, Cloud Storage object operations, database queries |

Tên API cụ thể thay đổi theo dịch vụ, nhưng nguyên tắc quyền vẫn giống nhau:

- Provisioner cần quyền tạo/cập nhật resource và role assignment trong scope được giao.
- Runtime cần quyền thao tác dữ liệu cần thiết trên các resource đã tồn tại.
- Runtime không nên có quyền Owner, Contributor, Project Editor hoặc IAM administrator chỉ để gửi event hoặc ghi object.
- Quyền đọc metadata resource có thể cần cho health check, nhưng không đồng nghĩa cần quyền tạo/xóa resource.

### 5.1. Ví dụ phân tách quyền

| Tác vụ | Provisioner | Spring Boot runtime |
|---|---:|---:|
| Tạo Event Hub/queue/topic | Có | Không |
| Tạo storage account/bucket | Có | Không |
| Tạo database server/instance | Có | Không |
| Gán IAM/RBAC role | Có theo scope | Không |
| Gửi event | Có thể | Có nếu nghiệp vụ cần |
| Nhận message | Có thể | Có nếu nghiệp vụ cần |
| Đọc/ghi object | Có thể | Chỉ quyền object cần thiết |
| Đọc secret runtime | Không bắt buộc | Chỉ secret được cấp |
| Xóa resource production | Quy trình riêng có kiểm soát | Không |

Một pipeline provisioner có thể dùng quyền rộng hơn workload nhưng phải giới hạn theo environment, subscription/account/project và module. Quyền cấp phát cũng cần review, audit và tách khỏi quyền deploy ứng dụng.

## 6. Chọn công cụ IaC trên AWS, Azure và Google Cloud

| Provider | Công cụ thường dùng | Đặc điểm |
|---|---|---|
| AWS | CloudFormation, AWS CDK, Terraform | CloudFormation quản lý resource theo stack; CDK tổng hợp source code thành template; Terraform dùng provider và state |
| Azure | Bicep/ARM, Terraform | Bicep là ngôn ngữ khai báo cho Azure Resource Manager, hỗ trợ module và what-if |
| Google Cloud | Terraform, Google Cloud Infrastructure Manager | Infrastructure Manager dùng Terraform configuration để quản lý deployment/revision và preview hạ tầng |
| Multi-cloud | Terraform hoặc công cụ IaC đa provider | Dùng chung workflow nhưng vẫn phải hiểu khác biệt IAM, network, storage và lifecycle từng cloud |

Không cần ép mọi cloud dùng cùng một DSL nếu platform đã có công cụ chuẩn. Điều quan trọng là tất cả resource production đều có source of truth, review và pipeline quản lý.

### 6.1. AWS CloudFormation

CloudFormation template mô tả resource; một stack là đơn vị tạo, cập nhật và xóa tập resource. Change set cho phép xem trước tài nguyên sẽ thêm, sửa, thay thế hoặc xóa trước khi thực thi. Drift detection so sánh trạng thái thực tế với template và parameters được quản lý.

Ví dụ CloudFormation rút gọn:

~~~yaml
AWSTemplateFormatVersion: '2010-09-09'
Description: Provision resources for the order application

Resources:
  OrdersEventBus:
    Type: AWS::Events::EventBus
    Properties:
      Name: orders-events

  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-processing
      VisibilityTimeout: 60

  OrdersBucket:
    Type: AWS::S3::Bucket
    Properties:
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256

Outputs:
  EventBusName:
    Value: !Ref OrdersEventBus
  QueueUrl:
    Value: !Ref OrdersQueue
  BucketName:
    Value: !Ref OrdersBucket
~~~

Template trên mô tả resource và outputs. IAM role/policy của workload nên được định nghĩa trong module riêng hoặc phần tài nguyên bảo mật được review. Không đưa access key vào Outputs; output nên là tên/ARN/URL không nhạy cảm cần cho deploy config.

### 6.2. Azure Bicep

Bicep khai báo resource Azure bằng cú pháp declarative. Azure Resource Manager xử lý dependency giữa các resource; module giúp chia hạ tầng thành các phần có thể tái sử dụng. What-if preview cho biết resource/property nào có thể được tạo, sửa hoặc xóa trước khi deploy.

Ví dụ provision Event Hubs và Blob container làm checkpoint store:

~~~bicep
param location string = resourceGroup().location
param namespaceName string
param eventHubName string
param storageAccountName string

resource namespace 'Microsoft.EventHub/namespaces@2024-01-01' = {
  name: namespaceName
  location: location
  sku: {
    name: 'Standard'
    tier: 'Standard'
    capacity: 1
  }
}

resource eventHub 'Microsoft.EventHub/namespaces/eventhubs@2024-01-01' = {
  parent: namespace
  name: eventHubName
  properties: {
    partitionCount: 4
    messageRetentionInDays: 7
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageAccountName
  location: location
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    supportsHttpsTrafficOnly: true
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource checkpointContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: 'eventhub-checkpoints'
  properties: {
    publicAccess: 'None'
  }
}

output namespaceName string = namespace.name
output eventHubName string = eventHub.name
output storageAccountName string = storage.name
output checkpointContainerName string = checkpointContainer.name
~~~

Đây là ví dụ hạ tầng rút gọn; production cần bổ sung network/private endpoint, diagnostic settings, tags, SKU/capacity, retention, backup và role assignment theo tiêu chuẩn platform. Event Hubs namespace và Blob Storage được tạo ở provisioning stage. Spring Boot không cần quyền tạo chúng.

Pipeline có thể chạy what-if trước khi deploy:

~~~bash
az deployment group what-if \
  --resource-group rg-orders-prod \
  --template-file main.bicep \
  --parameters namespaceName=orders-prod eventHubName=order-events storageAccountName=ordersstateprod
~~~

Sau khi review kết quả, pipeline mới thực hiện deployment. What-if là dự báo thay đổi, không phải bằng chứng tuyệt đối rằng mọi tác động runtime đã được mô phỏng; đọc kỹ các thay đổi Create, Modify, Delete và các cảnh báo chưa đánh giá được.

### 6.3. Google Cloud Terraform và Infrastructure Manager

Terraform mô tả resource Google Cloud; Infrastructure Manager là dịch vụ quản lý deployment Terraform trên Google Cloud. Service hỗ trợ lưu cấu hình ở Cloud Storage, Git repository hoặc local directory, quản lý deployment/revision và preview deployment. Infrastructure Manager quản lý hạ tầng; việc deploy application lên Cloud Run/GKE hoặc compute khác là một quy trình riêng.

Ví dụ Terraform rút gọn:

~~~hcl
resource "google_pubsub_topic" "orders" {
  name = "orders-events"
}

resource "google_pubsub_subscription" "orders_consumer" {
  name  = "orders-processing"
  topic = google_pubsub_topic.orders.id

  ack_deadline_seconds = 30
}

resource "google_storage_bucket" "application_state" {
  name                        = var.state_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false
}

output "orders_topic_id" {
  value = google_pubsub_topic.orders.id
}

output "orders_subscription_id" {
  value = google_pubsub_subscription.orders_consumer.id
}

output "state_bucket_name" {
  value = google_storage_bucket.application_state.name
}
~~~

Terraform cần backend state được quản lý và bảo vệ, phân quyền truy cập state, locking theo backend hỗ trợ và quy trình plan/apply. Không lưu state production trong laptop cá nhân hoặc commit file state có thể chứa dữ liệu nhạy cảm vào Git.

### 6.4. Outputs là hợp đồng giữa provisioning và deployment

Các output có thể gồm:
- Resource ID/ARN.
- Service endpoint hoặc FQDN.
- Tên queue, topic, subscription, bucket hoặc container.
- Region/project/subscription/account.
- Identity resource ID hoặc principal ID để tham chiếu khi gán quyền.
- Tên secret reference, không phải secret value.

Pipeline đọc outputs và đưa chúng vào deployment configuration. Không dùng output để truyền private key, password, SAS token hoặc connection string có secret. Nếu ứng dụng dùng workload identity, phần lớn trường hợp chỉ cần endpoint/resource name và credential chain.

## 7. Thiết kế module IaC và dependency

Không nên đặt toàn bộ hạ tầng của một tổ chức vào một file lớn khó review. Có thể chia theo trách nhiệm:

| Module | Resource điển hình | Chủ sở hữu |
|---|---|---|
| Network | VPC/VNet, subnet, route, private endpoint, firewall | Platform/network |
| Identity | Managed identity, service account, IAM role, role assignment | Platform/security |
| Messaging | Event Grid, Event Hubs, Service Bus, SNS/SQS, Pub/Sub | Messaging/platform |
| Storage | S3, Blob Storage, Cloud Storage, encryption, lifecycle | Platform/data |
| Database | Managed DB, subnet integration, backup, parameter group | Data/platform |
| Observability | Log group, diagnostic setting, metric alert, dashboard | SRE/platform |
| Application deployment | Container app, Kubernetes workload, service, ingress | Application/platform |

Module cần khai báo input/output rõ ràng. Ví dụ module messaging nhận principal ID của workload và trả event endpoint, topic name cùng resource ID. Module identity không cần biết business payload; module application không cần tạo queue.

### 7.1. Dependency graph

Một deployment có thể có quan hệ phụ thuộc:

~~~mermaid
flowchart TD
    NET["Network and private endpoints"] --> DATA["Storage / database / messaging"]
    ID["Workload identity"] --> RBAC["Data-plane role assignments"]
    DATA --> RBAC
    DATA --> OUTPUT["Resource outputs"]
    RBAC --> OUTPUT
    OUTPUT --> APP["Deploy Spring Boot"]
    APP --> SMOKE["Readiness and smoke test"]
    SMOKE --> TRAFFIC["Enable traffic"]
~~~

Tạo network và identity trước; tạo resource; gán quyền; xuất config; sau đó deploy ứng dụng. Nếu resource và role assignment được deploy song song không đúng dependency, ứng dụng có thể khởi động trước khi role assignment lan truyền.

Role assignment thường có độ trễ propagation. Pipeline có thể có bước kiểm tra readiness với retry/backoff có giới hạn, nhưng không nên cấp quyền quản trị cho runtime chỉ để né thời gian propagation.

## 8. Tách danh tính provisioner và workload runtime

Một hệ thống an toàn có ít nhất hai danh tính riêng:

**Provisioner identity**
- Được pipeline sử dụng để tạo/cập nhật hạ tầng.
- Có quyền management plane trong scope cần thiết.
- Có thể gán role cho workload identity nếu quy trình được cho phép.
- Có audit log và approval đối với thay đổi production.
- Không được nhúng vào image hoặc environment của ứng dụng.

**Workload identity**
- Được Spring Boot sử dụng khi chạy.
- Có quyền data plane đúng với nghiệp vụ.
- Không có quyền tạo/xóa queue, bucket, topic hoặc IAM policy.
- Có thể khác nhau theo service, environment và workload.
- Không dùng chung một principal có quyền rộng cho toàn bộ ứng dụng.

Ví dụ role theo provider:

| Provider | Provisioner | Runtime |
|---|---|---|
| AWS | CloudFormation deployment role, IAM deployment permissions | ECS task role, EKS IRSA/Pod Identity hoặc EC2 instance profile với S3/SQS/EventBridge actions cần thiết |
| Azure | Service principal/workload identity có quyền deploy ARM/Bicep và role assignment theo scope | Managed Identity/Workload Identity với Event Hubs Data Receiver, Service Bus Data Sender/Receiver, Storage Blob Data Contributor theo nhu cầu |
| Google Cloud | CI service account có quyền tạo resource và IAM binding trong project/folder được giao | Workload service account với Pub/Sub Publisher/Subscriber, Storage Object User hoặc role hẹp hơn |

Không cấp quyền chỉ dựa trên tên dịch vụ. Xác định chính xác hành động ứng dụng thực hiện, scope resource và role built-in/custom phù hợp. Ví dụ consumer chỉ đọc message thì không cần quyền publish; service chỉ ghi object thì không cần quyền xóa bucket.

## 9. Truyền resource outputs vào Spring Boot

Spring Boot hỗ trợ externalized configuration từ YAML/properties, environment variables, command line và các nguồn cấu hình khác. Dùng một contract có kiểu để nhận các giá trị do provisioning pipeline xuất ra.

Ví dụ cấu hình runtime:

~~~yaml
app:
  cloud:
    provider: azure
    event-grid-endpoint: https://orders-prod.region.eventgrid.azure.net/api/events
    event-hub-namespace: orders-prod.servicebus.windows.net
    event-hub-name: order-events
    checkpoint-storage-endpoint: https://ordersstateprod.blob.core.windows.net
    checkpoint-container: eventhub-checkpoints
~~~

Các giá trị trên là ví dụ không chứa secret. Trong production, pipeline thay chúng bằng outputs của môi trường tương ứng hoặc inject từ config service. Không đóng cứng tên resource production trong JAR.

### 9.1. Bind cấu hình bằng ConfigurationProperties

Để kiểm tra các annotation Jakarta Validation khi bind cấu hình, thêm starter validation nếu dự án chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

~~~java
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.cloud")
public record CloudResourceProperties(
        @NotBlank String provider,
        @NotBlank String eventGridEndpoint,
        @NotBlank String eventHubNamespace,
        @NotBlank String eventHubName,
        @NotBlank String checkpointStorageEndpoint,
        @NotBlank String checkpointContainer) {
}
~~~

Đăng ký properties:

~~~java
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(CloudResourceProperties.class)
class CloudResourceConfiguration {
}
~~~

Khi thiếu endpoint hoặc tên resource, validation làm ứng dụng fail fast ngay lúc bind configuration. Đây là lỗi cấu hình cần được phát hiện trong deploy stage, không phải lý do để runtime tự tạo resource.

### 9.2. Inject credential chain và tạo SDK client

Ví dụ Azure dùng DefaultAzureCredential:

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AzureIdentityConfiguration {

    @Bean
    DefaultAzureCredential defaultAzureCredential() {
        return new DefaultAzureCredentialBuilder().build();
    }
}
~~~

Ví dụ publisher client được tạo từ endpoint đã provision:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.messaging.eventgrid.EventGridEvent;
import com.azure.messaging.eventgrid.EventGridPublisherClient;
import com.azure.messaging.eventgrid.EventGridPublisherClientBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class EventGridClientConfiguration {

    @Bean
    EventGridPublisherClient<EventGridEvent> eventGridPublisher(
            CloudResourceProperties properties,
            TokenCredential credential) {
        return new EventGridPublisherClientBuilder()
                .endpoint(properties.eventGridEndpoint())
                .credential(credential)
                .buildEventGridEventPublisherClient();
    }
}
~~~

Client builder tạo đối tượng client để gọi endpoint đã tồn tại; nó không tạo Event Grid topic. Identity runtime phải có EventGrid Data Sender trên topic. Nếu topic chưa được provision hoặc endpoint sai, thao tác gửi sẽ thất bại và cần xử lý như lỗi cấu hình/kết nối.

### 9.3. Business service chỉ sử dụng client

~~~java
import com.azure.core.util.BinaryData;
import com.azure.messaging.eventgrid.EventGridEvent;
import com.azure.messaging.eventgrid.EventGridPublisherClient;
import org.springframework.stereotype.Service;

@Service
class OrderEventPublisher {
    private final EventGridPublisherClient<EventGridEvent> publisher;

    OrderEventPublisher(
            EventGridPublisherClient<EventGridEvent> publisher) {
        this.publisher = publisher;
    }

    public void publish(OrderCreated order) {
        EventGridEvent event = new EventGridEvent(
                "/orders/" + order.orderId(),
                "com.example.orders.created",
                BinaryData.fromObject(order),
                "1.0")
                .setId(order.eventId());

        publisher.sendEvent(event);
    }
}

record OrderCreated(
        String eventId,
        String orderId,
        long totalAmount) {
}
~~~

Business service không gọi API quản lý topic, không tạo role assignment và không lưu connection string. Event ID do nghiệp vụ/outbox tạo ổn định để consumer có thể deduplicate khi publisher retry.

## 10. Runtime nên fail fast hay retry?

Tách provisioning không có nghĩa ứng dụng không kiểm tra resource. Runtime vẫn cần xác minh cấu hình và khả năng truy cập, nhưng cách phản ứng phải phù hợp loại lỗi.

| Tình huống | Hành vi runtime |
|---|---|
| Thiếu endpoint hoặc resource name | Fail fast khi bind configuration |
| Resource không tồn tại | Báo lỗi rõ ràng; deployment/readiness thất bại |
| Identity thiếu data-plane role | Báo 403/authorization failure; platform sửa role assignment |
| Network/private endpoint chưa sẵn sàng | Retry có giới hạn hoặc readiness chưa healthy |
| Dịch vụ throttling/tạm thời unavailable | Retry theo SDK policy, backoff và deadline |
| Event payload không hợp lệ | Từ chối/quarantine theo nghiệp vụ |
| Resource cần thay đổi capacity/retention | Tạo change IaC riêng, review rồi deploy |

Không tự tạo resource khi gặp 404 hoặc 403. 404 có thể là endpoint sai, resource bị xóa hoặc deployment chưa hoàn tất; 403 thường là identity/scope sai. Nếu runtime tự tạo resource khi gặp lỗi, nó che giấu nguyên nhân và mở rộng quyền ngoài ý muốn.

Readiness check có thể kiểm tra kết nối/metadata bằng quyền read-only nếu SDK và dịch vụ hỗ trợ. Liveness check chỉ nên xác định process còn hoạt động, tránh restart toàn bộ pod chỉ vì một dịch vụ cloud tạm thời chậm.

## 11. Không để binder hoặc framework tự động provision production resource ngoài ý muốn

Một số SDK, Spring Cloud binder hoặc framework có thể hỗ trợ auto-create destination, queue, topic, subscription hoặc container tùy provider và cấu hình. Tính năng này hữu ích trong local development, integration test hoặc môi trường ephemeral.

Trong production:
- Kiểm tra tài liệu binder/starter đang dùng để biết behavior auto-provision.
- Tắt auto-create nếu IaC là source of truth.
- Đảm bảo queue/topic/subscription được tạo trước khi deploy ứng dụng.
- Nếu framework yêu cầu resource tồn tại, fail startup/readiness rõ ràng.
- Không cấp quyền create destination cho workload chỉ để binder tự tạo.
- Đặt tên destination trong deployment config và kiểm tra đúng environment.

Không có một property tắt auto-create chung cho mọi Spring Cloud provider. Tên property và behavior khác nhau giữa Spring Cloud AWS, Spring Cloud Azure và Spring Cloud GCP; phải kiểm tra đúng binder version đang dùng.

## 12. Quản lý database schema migration riêng

Database server/instance, subnet, firewall, backup, encryption và credential store thuộc provisioning. Bảng, index, constraint và schema version thuộc vòng đời dữ liệu của ứng dụng.

Không nên để mỗi replica chạy DDL hoặc tự tạo database schema khi startup production:
- Nhiều replica có thể chạy migration đồng thời.
- Runtime identity phải có quyền DDL rộng.
- Một migration phá vỡ backward compatibility có thể làm phiên bản cũ đang chạy lỗi.
- Rollback application không tự rollback dữ liệu an toàn.

Dùng Flyway/Liquibase hoặc migration job riêng:
1. Provision database và runtime/migration identities.
2. Deploy migration job với quyền DDL giới hạn.
3. Chạy migration có lock/version tracking.
4. Kiểm tra migration thành công.
5. Deploy application revision tương thích với schema mới.
6. Thu hồi hoặc không cấp DDL permission cho runtime identity.

Cấu hình Hibernate production thường dùng validate/none thay vì update/create. Chọn chiến lược migration tương thích ngược (expand-and-contract) khi cần rollout nhiều phiên bản đồng thời.

## 13. Secret và configuration không phải cùng một loại output

IaC outputs thường chứa endpoint, resource ID, tên queue/topic và các giá trị không nhạy cảm. Secret như password, private key, SAS token, connection string có shared key và client secret phải được lưu trong secret manager.

| Loại giá trị | Ví dụ | Cách truyền |
|---|---|---|
| Resource identifier | ARN, resource ID, project ID | IaC output → deployment config |
| Endpoint | FQDN, URL, region | IaC output → environment/config |
| Destination name | Queue/topic/container | IaC output → ConfigurationProperties |
| Secret reference | Key Vault secret URI, Secrets Manager ARN, Secret Manager resource name | Config reference → runtime identity đọc secret |
| Secret value | Password, private key, SAS token | Secret manager hoặc mounted secret, không ghi vào output/log |
| Workload identity | Managed identity ID, service account binding | IaC tạo; platform gắn vào workload |

Ưu tiên workload identity để runtime lấy token ngắn hạn từ cloud identity provider. Nếu phải dùng secret, ứng dụng cần đọc theo quyền tối thiểu, có rotation, audit và không log giá trị.

Spring Boot hỗ trợ externalized configuration và configuration tree. Có thể mount secret thành file hoặc dùng secret integration phù hợp nền tảng. Không đưa secret vào command line vì có thể xuất hiện trong process list hoặc log pipeline.

## 14. Tách môi trường và ownership

Dev, test, staging và production cần resource boundary riêng:
- AWS account/OU, Azure subscription/resource group, Google Cloud project/folder.
- Network, storage, queue/topic và database riêng theo environment.
- Workload identity riêng, không dùng principal production trong dev.
- IaC state/backend tách biệt và quyền đọc state hạn chế.
- Resource tags/labels ghi owner, environment, cost center và service.
- Retention, backup, deletion protection và alert khác nhau theo criticality.

Tên resource có thể theo quy ước gồm service, environment, region và purpose. Tránh tạo resource name ngẫu nhiên mỗi lần deploy; tên ổn định giúp app config, RBAC, monitoring và audit nhất quán.

Ownership cần rõ:
- Platform team sở hữu network, baseline security và reusable modules.
- Application team sở hữu resource-specific parameters, event contract và runtime behavior.
- Security team review role assignment, secret access và network exposure.
- SRE/operations sở hữu alert, backup, recovery và runbook.

## 15. Cập nhật resource mà không làm gián đoạn nghiệp vụ

Thay đổi IaC có thể sửa thuộc tính tại chỗ, thay thế resource hoặc xóa resource. Cần phân loại trước khi apply.

| Loại thay đổi | Ví dụ | Cách xử lý |
|---|---|---|
| Non-breaking | Thêm tag, tăng capacity trong giới hạn | Preview, apply, quan sát |
| Config change | Retention, network rule, encryption | Kiểm tra tác động và compatibility |
| Replacement | Đổi thuộc tính khiến resource phải tạo lại | Tạo resource mới, migrate/cutover |
| Destructive | Xóa bucket, queue, database | Backup, retention, approval, recovery plan |
| Identity change | Thay role assignment hoặc workload principal | Cấp quyền mới trước, deploy, rồi thu hồi quyền cũ |

Không giả định update IaC luôn là thao tác in-place. Đọc change set/plan/what-if để biết resource nào bị replace hoặc delete. Với resource lưu dữ liệu, cấu hình retain/deletion protection/backup phù hợp; không để việc xóa stack vô tình xóa dữ liệu production.

### 15.1. Blue-green cho resource có trạng thái

Khi cần thay queue/topic/database hoặc storage:
1. Provision resource mới bằng module IaC.
2. Gán quyền cho workload identity.
3. Xuất endpoint/name mới.
4. Deploy consumer/publisher tương thích với cả resource cũ và mới nếu cần.
5. Đồng bộ/backfill dữ liệu hoặc chuyển traffic theo chiến lược đã chọn.
6. Quan sát metric và xác nhận không còn producer/consumer dùng resource cũ.
7. Giữ resource cũ trong khoảng rollback đã định.
8. Xóa resource cũ bằng một change riêng sau khi xác minh.

Đừng xóa resource cũ ngay trong cùng lần rollout nếu ứng dụng còn phiên bản cũ đang chạy hoặc event chưa xử lý hết.

## 16. Drift detection và thay đổi ngoài IaC

Drift xảy ra khi resource thực tế khác với source of truth IaC, thường do thay đổi trực tiếp qua console/CLI hoặc một automation khác.

Cách phát hiện theo provider:
- AWS CloudFormation: drift detection và drift-aware change sets.
- Azure Bicep/ARM: what-if để xem thay đổi dự kiến trước deployment; Azure Policy có thể kiểm tra cấu hình tuân thủ.
- Google Cloud Infrastructure Manager: preview deployment và quản lý deployment/revision dựa trên Terraform configuration.
- Terraform: plan so sánh state/config với provider; cần lưu ý state có thể chưa phản ánh mọi thay đổi ngoài băng.

Quy trình xử lý drift:
1. Phát hiện và xác định resource/property khác biệt.
2. Xác định thay đổi do incident, thao tác thủ công hay IaC module lỗi.
3. Quyết định cập nhật source of truth hay đưa resource về trạng thái đã khai báo.
4. Review tác động, đặc biệt là network, encryption, IAM và data retention.
5. Áp dụng thay đổi qua pipeline.
6. Ghi nhận audit và cập nhật runbook nếu cần.

Không tự động overwrite mọi drift trong production mà không review. Một thay đổi thủ công có thể là biện pháp khắc phục incident; IaC apply có thể ghi đè thay đổi đó.

## 17. CI/CD pipeline đề xuất

Một pipeline có thể tổ chức như sau:

~~~mermaid
flowchart TD
    SRC["Commit application + IaC"] --> CHECK["Lint, unit test, policy checks"]
    CHECK --> PLAN["IaC plan / change set / what-if"]
    PLAN --> REVIEW["Review infrastructure diff"]
    REVIEW --> APPLY["Provision / update resources"]
    APPLY --> EXPORT["Publish non-secret outputs"]
    EXPORT --> BUILD["Build and scan application artifact"]
    BUILD --> DEPLOY["Deploy application revision"]
    DEPLOY --> READY["Readiness and smoke tests"]
    READY --> ROUTE["Enable traffic / complete rollout"]
    READY -->|Failure| ROLLBACK["Rollback application revision"]
~~~

Một số tổ chức build artifact song song với plan hạ tầng để tiết kiệm thời gian; nhưng không deploy revision trước khi resource và quyền cần thiết đã sẵn sàng.

### 17.1. Các bước cần kiểm soát

- **Lint/validate:** kiểm tra cú pháp template, module, dependency và version.
- **Policy check:** chặn public storage, wildcard IAM, encryption thiếu hoặc region không được phép.
- **Plan/preview:** tạo plan, CloudFormation change set hoặc Bicep what-if.
- **Review:** đọc các thay đổi Create/Modify/Replace/Delete và role assignment.
- **Apply:** dùng provisioner identity có scope giới hạn.
- **Output:** xuất endpoint/resource name, không xuất secret value.
- **Deploy:** inject config và workload identity vào ứng dụng.
- **Readiness:** kiểm tra app khởi động, kết nối và có quyền data plane.
- **Smoke test:** gửi/nhận event hoặc đọc/ghi object thử trong scope test.
- **Observe:** theo dõi error rate, latency, backlog, cost và drift.

Production apply thường cần approval phù hợp với mức độ ảnh hưởng. Dev/test có thể tự động hơn nếu tài nguyên được cô lập và chi phí/cleanup đã kiểm soát.

## 18. Kiểm thử ranh giới provisioning/runtime

Cần kiểm tra cả hai phía: IaC tạo đúng resource và ứng dụng không có quyền tạo resource.

| Kiểm thử | Cách thực hiện | Kết quả mong đợi |
|---|---|---|
| IaC validation | Lint/validate template/module | Cấu hình hợp lệ |
| Plan review | Thay đổi một resource trong branch | Diff cho thấy đúng resource/property |
| Provisioning integration | Deploy vào subscription/account/project test | Resource tồn tại và outputs đúng |
| RBAC test | Dùng workload identity runtime | Chỉ thao tác data plane được cho phép |
| Negative permission test | Thử create/delete resource bằng runtime identity | Bị từ chối |
| Runtime startup | Deploy Spring Boot với outputs đã cấp | Configuration bind thành công |
| Missing resource | Dùng tên container/queue sai trong test | Readiness/operation báo lỗi, app không tự tạo resource |
| Missing permission | Thu hồi role data-plane trong test | Lỗi authorization rõ ràng |
| Rollout | Deploy revision mới dùng cùng resource | Không tạo resource trùng |
| Drift | Thay đổi test resource ngoài IaC | Drift/plan phát hiện thay đổi |
| Destroy | Xóa environment test | Data retention và cleanup đúng policy |

Local development có thể dùng Testcontainers, LocalStack, Azurite hoặc emulator phù hợp để tạo tài nguyên ephemeral. Đây là provisioning dành cho test harness, không phải logic business production. Nên giữ cấu hình local tách biệt và không dùng credential production.

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Pod tạo queue/container lúc startup | Auto-provision được bật hoặc code gọi create-if-not-exists | Tắt auto-create production; provision qua IaC |
| App nhận 403 khi gửi event | Runtime identity thiếu data-plane role hoặc sai scope | Kiểm tra principal và role assignment |
| App nhận 404 | Endpoint/name sai hoặc resource chưa được provision | Kiểm tra pipeline output và deployment config |
| Deploy thành công nhưng app chưa ready | Role assignment chưa propagate hoặc network chưa sẵn sàng | Có readiness retry có giới hạn; kiểm tra RBAC/network |
| Nhiều resource trùng tên hậu tố ngẫu nhiên | Tạo resource theo mỗi deployment | Dùng naming convention và IaC state ổn định |
| Thay đổi stack xóa dữ liệu | Không cấu hình retain/backup/deletion protection | Review delete/replace và lifecycle policy |
| Plan luôn báo thay đổi | Drift, computed field hoặc output không ổn định | Điều tra diff; không apply mù quáng |
| Dev app truy cập production | Dùng chung principal/config/state | Tách environment và identity |
| Secret xuất hiện trong pipeline log | Output/command line chứa secret | Dùng secret reference, mask log và rotate |
| Runtime cần quyền Contributor | Code đang tạo resource hoặc đọc management API không cần thiết | Chuyển provisioning sang pipeline, thu hẹp quyền |
| Database migration chạy trên mọi pod | Migration gắn vào startup của từng replica | Chuyển sang migration job có lock/version |
| Rollback app không hoạt động | Resource/schema mới không tương thích bản cũ | Dùng expand-and-contract và rollout có compatibility |

## 20. Checklist trước production

- **Ownership:** Có owner cho từng resource/module và runbook vận hành.
- **IaC:** Resource production được khai báo và quản lý qua source of truth.
- **Separation:** Provisioning, application deployment và business runtime có bước và danh tính riêng.
- **Control plane:** Chỉ provisioner có quyền tạo/cập nhật/xóa resource.
- **Data plane:** Runtime chỉ có quyền gửi/nhận/đọc/ghi đúng nghiệp vụ.
- **Identity:** Managed Identity, IAM role hoặc Workload Identity được gắn đúng workload.
- **Outputs:** Endpoint/resource ID được truyền qua config; không có secret value trong output.
- **Configuration:** Spring Boot bind cấu hình bằng ConfigurationProperties và validate bắt buộc.
- **Auto-provision:** Binder/SDK auto-create được kiểm tra và tắt trong production khi IaC quản lý resource.
- **Database:** Migration chạy qua job có kiểm soát; runtime không giữ DDL quyền rộng.
- **Network:** Private endpoint, firewall, DNS, TLS và egress được khai báo.
- **Lifecycle:** Backup, retention, deletion protection và replacement strategy rõ ràng.
- **Change review:** Plan/change set/what-if được xem trước; destructive changes có approval.
- **Drift:** Có lịch phát hiện và quy trình xử lý drift.
- **Testing:** Có negative test chứng minh runtime không thể tạo/xóa resource.
- **Observability:** Provisioning audit, runtime errors, readiness và resource metrics được theo dõi.
- **Cost:** Tag/label, budget, quota và cleanup policy được cấu hình.
- **Recovery:** Có rollback/cutover và kế hoạch phục hồi khi resource provisioning thất bại.

## 21. Tổng kết

Tách việc cấp phát tài nguyên khỏi thao tác xử lý nghiệp vụ tạo ra ranh giới rõ giữa **control plane** và **data plane**. IaC pipeline dùng CloudFormation, Bicep, Terraform hoặc Google Cloud Infrastructure Manager để tạo resource, network, identity và role assignment. Application pipeline triển khai artifact và truyền outputs không nhạy cảm vào Spring Boot. Runtime chỉ sử dụng SDK client với workload identity và quyền data plane tối thiểu.

Cách tổ chức này giảm quyền quản trị trong ứng dụng, tránh race khi nhiều replica khởi động, giúp review thay đổi hạ tầng và kiểm soát lifecycle resource. Khi resource thiếu hoặc quyền sai, ứng dụng báo lỗi rõ ràng để deployment/platform xử lý; nó không tự mở rộng quyền hay tạo hạ tầng trong request nghiệp vụ. Kết hợp IaC plan/preview, externalized configuration, managed identity, database migration job, drift detection và negative permission test sẽ giúp hệ thống Spring Boot tích hợp AWS, Azure và Google Cloud có thể triển khai lặp lại, kiểm toán và vận hành an toàn.

## Tài liệu tham khảo

- [AWS CloudFormation stacks](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/stacks.html)
- [AWS CloudFormation change sets](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-updating-stacks-changesets.html)
- [AWS CloudFormation drift detection](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/detect-drift-stack.html)
- [What is Bicep?](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/overview)
- [Bicep What-If preview](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/deploy-what-if)
- [Bicep outputs](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/outputs)
- [Google Cloud Infrastructure Manager overview](https://docs.cloud.google.com/infrastructure-manager/docs/overview)
- [Infrastructure as Code on Google Cloud](https://docs.cloud.google.com/docs/terraform/iac-overview)
- [Azure Event Grid client library for Java](https://learn.microsoft.com/en-us/java/api/overview/azure/messaging-eventgrid-readme?view=azure-java-stable)
- [Spring Boot externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)

