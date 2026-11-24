# Mô tả hạ tầng bằng mã và truyền đầu ra cấu hình cho ứng dụng

Một ứng dụng Spring Boot thường không tự biết tên queue, topic, bucket, database hay endpoint của từng môi trường. Những giá trị này chỉ có sau khi hạ tầng được tạo. Infrastructure as Code (IaC) khai báo và cấp phát tài nguyên; **outputs** của deployment trả về định danh và endpoint để bước triển khai ứng dụng cấu hình đúng môi trường. Khi khởi động, Spring Boot bind các giá trị đó thành cấu hình có kiểu rồi khởi tạo SDK client bằng workload identity.

Bài này tập trung vào hợp đồng output giữa IaC và ứng dụng. AWS CloudFormation, Azure Bicep, Terraform và Google Cloud Infrastructure Manager có cú pháp, định dạng kết quả và cách xử lý dữ liệu nhạy cảm khác nhau. Pipeline cần chuẩn hóa các khác biệt này, xác thực output trước khi deploy, chuyển giá trị không nhạy cảm vào configuration store và giữ secret trong secret manager. Spring Boot nhận cấu hình qua externalized configuration, kiểm tra thiếu hoặc sai giá trị trước khi nhận traffic và sử dụng resource đã provision.

Bài học thuộc chương **Triển khai ứng dụng** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vai trò của IaC outputs trong hợp đồng giữa pipeline hạ tầng và pipeline ứng dụng.
- Khai báo output có tên, kiểu dữ liệu, mô tả và phạm vi rõ ràng.
- Lấy output từ CloudFormation, Bicep, Terraform và Google Cloud Infrastructure Manager.
- Phân biệt output công khai, output nhạy cảm và secret reference.
- Chuẩn hóa output đa cloud thành configuration contract có phiên bản.
- Chuyển output sang environment variables, ConfigMap hoặc file cấu hình runtime.
- Bind cấu hình bằng Spring Boot ConfigurationProperties và validate khi startup.
- Hiểu thứ tự ưu tiên của property sources và quy tắc relaxed binding.
- Dùng config tree hoặc secret manager để cấp secret mà không đưa secret vào IaC output.
- Kiểm thử output contract, config binding, identity và khả năng truy cập resource.
- Xử lý thay đổi output có tương thích ngược và rollout nhiều phiên bản.

## 2. Output là hợp đồng giữa hạ tầng và ứng dụng

IaC mô tả resource cần tồn tại; output trả về các giá trị mà bước tiếp theo cần dùng. Sau khi tạo một messaging resource, pipeline ứng dụng có thể cần:

- Resource ID hoặc ARN để audit và gán quyền.
- Endpoint hoặc hostname để SDK kết nối.
- Topic, queue, subscription hoặc container name.
- Region, project, account hoặc subscription.
- Workload identity resource ID hoặc principal ID để gắn vào compute platform.
- Secret reference để runtime đọc credential từ nơi lưu trữ chuyên dụng.

Không phải mọi output đều phải đưa vào Spring Boot. Một số output chỉ dành cho pipeline hoặc platform automation. Ví dụ principal ID có thể cần cho bước tạo role assignment, còn runtime chỉ cần endpoint và tên destination.

Một output contract tốt trả lời được bốn câu hỏi:

1. Giá trị này thuộc resource nào và environment nào?
2. Ứng dụng hoặc pipeline nào cần dùng?
3. Kiểu dữ liệu và định dạng của giá trị là gì?
4. Khi giá trị thay đổi, consumer có thể tiếp tục hoạt động hay phải rollout lại?

### 2.1. Phân loại output

| Loại | Ví dụ | Consumer |
|---|---|---|
| Resource identifier | ARN, Azure resource ID, project resource name | Pipeline, audit, IAM/RBAC |
| Endpoint | HTTPS URL, FQDN, hostname | Spring Boot SDK client |
| Destination name | Topic, queue, bucket, container | Spring Boot business service |
| Deployment metadata | Region, environment, contract version | Pipeline và ứng dụng |
| Identity reference | Role ARN, managed identity client ID, service account email | Deployment platform |
| Secret reference | Key Vault URI, Secrets Manager ARN, Secret Manager resource name | Runtime secret integration |
| Secret value | Password, private key, SAS token, connection string có key | Secret manager; không đưa vào output thông thường |

Không đưa secret value vào output contract. Endpoint và resource name thường không phải secret, nhưng vẫn có thể tiết lộ cấu trúc nội bộ; chỉ cấp cho consumer cần thiết và không ghi toàn bộ output vào log công khai.

## 3. Thiết kế output contract đa cloud

Mỗi provider có naming convention riêng. Ứng dụng không nên phải hiểu tên output của từng template hoặc cú pháp CLI của từng cloud. Pipeline có thể chuyển output riêng của provider sang một cấu trúc trung gian thống nhất.

Ví dụ contract JSON cho dịch vụ xử lý đơn hàng:

~~~json
{
  "contractVersion": 1,
  "service": "orders",
  "environment": "production",
  "cloudProvider": "azure",
  "region": "southeastasia",
  "messaging": {
    "endpoint": "orders-prod.servicebus.windows.net",
    "destination": "order-events"
  },
  "storage": {
    "endpoint": "https://ordersstateprod.blob.core.windows.net",
    "container": "order-checkpoints"
  },
  "database": {
    "host": "orders-prod.database.example",
    "port": 5432
  },
  "identity": {
    "mode": "workload"
  }
}
~~~

Contract này chỉ chứa thông tin kết nối và định danh không nhạy cảm. Không có client secret, account key hoặc SAS token. Ứng dụng dùng identity được gắn vào runtime để lấy token.

### 3.1. Quy ước đặt tên

| Nên dùng | Tránh dùng | Lý do |
|---|---|---|
| messagingEndpoint | value1 | Nêu rõ vai trò |
| ordersTopicName | topic | Tránh mơ hồ khi có nhiều topic |
| checkpointContainerName | container | Thể hiện workload |
| contractVersion | version | Phân biệt version contract với app version |
| workloadIdentityResourceId | identity | Nêu rõ loại định danh |
| secretReference | password | Truyền tham chiếu, không truyền secret |

Không dùng output name chứa thông tin thay đổi theo từng lần chạy như timestamp hoặc random deployment ID trừ khi đó thực sự là một phần của resource identity.

### 3.2. Output nên là giá trị nguyên thủy hay object?

Output nguyên thủy dễ tiêu thụ trong CLI và pipeline. Object giúp gom các giá trị liên quan nhưng consumer phải hiểu schema của object.

- Dùng output riêng cho endpoint, name, ID thường xuyên được tham chiếu.
- Dùng object cho một nhóm cấu hình có version và ownership rõ ràng.
- Không phụ thuộc thứ tự field trong JSON object.
- Không dùng một output khổng lồ chứa toàn bộ metadata của platform.
- Có thể xuất cả resource ID và endpoint nếu hai giá trị phục vụ hai mục đích khác nhau.

## 4. AWS CloudFormation: khai báo và đọc Outputs

CloudFormation có phần Outputs trong template. Giá trị được hiển thị trong tab Outputs của stack và có thể lấy bằng lệnh describe-stacks. Output cũng có thể được export để stack khác tham chiếu.

Ví dụ:

~~~yaml
Resources:
  OrdersQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-processing

  OrdersBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: orders-state-production
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

Outputs:
  OrdersQueueUrl:
    Description: Queue URL used by the orders runtime
    Value: !Ref OrdersQueue

  OrdersQueueArn:
    Description: Queue ARN used for IAM policy scope
    Value: !GetAtt OrdersQueue.Arn

  OrdersBucketName:
    Description: Bucket name used by the orders runtime
    Value: !Ref OrdersBucket
~~~

Sau khi stack hoàn tất, lấy output bằng AWS CLI:

~~~bash
aws cloudformation describe-stacks \
  --stack-name orders-infrastructure-production \
  --query 'Stacks[0].Outputs' \
  --output json
~~~

Kết quả là danh sách output có OutputKey, OutputValue và có thể có ExportName. Pipeline có thể chọn đúng key:

~~~bash
QUEUE_URL="$(aws cloudformation describe-stacks \
  --stack-name orders-infrastructure-production \
  --query "Stacks[0].Outputs[?OutputKey=='OrdersQueueUrl'].OutputValue | [0]" \
  --output text)"

BUCKET_NAME="$(aws cloudformation describe-stacks \
  --stack-name orders-infrastructure-production \
  --query "Stacks[0].Outputs[?OutputKey=='OrdersBucketName'].OutputValue | [0]" \
  --output text)"
~~~

Nếu output không tồn tại, CLI có thể trả None hoặc giá trị rỗng tùy query/format. Pipeline cần kiểm tra giá trị trước khi export; không để ứng dụng nhận chuỗi None như endpoint hợp lệ.

### 4.1. Export và import giữa các stack

Stack nền tảng có thể export một output:

~~~yaml
Outputs:
  SharedVpcId:
    Description: VPC used by application stacks
    Value: !Ref ApplicationVpc
    Export:
      Name: platform-production-vpc-id
~~~

Stack khác tham chiếu bằng Fn::ImportValue:

~~~yaml
Resources:
  ApplicationSubnet:
    Type: AWS::EC2::Subnet
    Properties:
      VpcId:
        Fn::ImportValue: platform-production-vpc-id
      CidrBlock: 10.20.10.0/24
~~~

Export và Fn::ImportValue tạo quan hệ phụ thuộc mạnh trong cùng AWS account và Region. Khi stack khác đang import một output, CloudFormation ngăn xóa stack export hoặc thay đổi giá trị export cho tới khi các import được gỡ bỏ. Với cross-account hoặc cross-Region, cân nhắc Fn::GetStackOutput hoặc một cơ chế chia sẻ contract khác.

Output không tự động cập nhật cấu hình runtime của một process đang chạy. Khi endpoint hoặc resource name đổi, pipeline phải tạo configuration revision và rollout ứng dụng tương ứng.

### 4.2. Giới hạn bảo mật của CloudFormation Outputs

CloudFormation không che hoặc mã hóa giá trị trong Outputs. Người có quyền xem stack outputs có thể đọc giá trị. Không đưa password, private key, access key hoặc connection string có secret vào đây. Nếu cần truyền credential, lưu trong AWS Secrets Manager hoặc SSM Parameter Store và truyền ARN/name tham chiếu.

Stack outputs cũng chỉ có sau khi thao tác stack hoàn tất; không dùng chúng như một service discovery endpoint mà runtime phải truy vấn liên tục.

## 5. Azure Bicep: outputs, module và deployment history

Bicep định nghĩa output theo cú pháp:

~~~bicep
output outputName dataType = value
~~~

Ví dụ module tạo storage account và trả endpoint cùng tên container:

~~~bicep
param storageName string
param location string = resourceGroup().location

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
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
  name: 'order-checkpoints'
  properties: {
    publicAccess: 'None'
  }
}

@description('Resource ID consumed by platform automation.')
output storageAccountId string = storage.id

@description('Blob endpoint consumed by the Spring Boot runtime.')
output blobEndpoint string = storage.properties.primaryEndpoints.blob

@description('Checkpoint container name.')
output checkpointContainerName string = checkpointContainer.name
~~~

Sau khi deployment thành công, lấy outputs bằng Azure CLI:

~~~bash
az deployment group show \
  --resource-group rg-orders-production \
  --name orders-infrastructure \
  --query properties.outputs \
  --output json
~~~

Kết quả có object theo tên output, thường chứa type và value. Pipeline cần lấy đúng trường value và kiểm tra type mong đợi trước khi tạo application configuration.

### 5.1. Outputs từ Bicep module

Một file Bicep có thể gọi module khác và đọc output qua moduleName.outputs.outputName:

~~~bicep
module storage './modules/storage.bicep' = {
  name: 'orders-storage'
  params: {
    storageName: storageName
    location: location
  }
}

output blobEndpoint string = storage.outputs.blobEndpoint
output containerName string = storage.outputs.checkpointContainerName
~~~

Cách chia module cho phép module storage sở hữu resource và contract output riêng; module ứng dụng chỉ nhận các giá trị cần dùng.

### 5.2. Secure outputs

Bicep hỗ trợ decorator @secure() cho output kiểu string hoặc object từ phiên bản Bicep 0.35.1. Giá trị secure output không được lưu trong deployment history và không được ghi vào log/hiển thị như output thường. Tính năng này có ích khi module cần chuyển một giá trị nhạy cảm cho module cha.

Dù vậy, thiết kế ứng dụng nên ưu tiên secret reference tới Azure Key Vault và Managed Identity. Không biến output thành kênh truyền password tới pipeline nếu runtime có thể đọc secret trực tiếp bằng identity. Khi phải dùng secure output, bảo đảm mọi bước tiếp theo cũng xử lý giá trị như secret và không ghi vào log.

## 6. Terraform: output block và cảnh báo sensitive

Terraform khai báo output ở root module:

~~~hcl
output "orders_topic_id" {
  description = "Pub/Sub topic resource ID for the orders publisher"
  value       = google_pubsub_topic.orders.id
}

output "orders_subscription_name" {
  description = "Subscription name consumed by the orders worker"
  value       = google_pubsub_subscription.orders.name
}

output "state_bucket_name" {
  description = "Bucket used for application state"
  value       = google_storage_bucket.application_state.name
}
~~~

Sau khi apply, đọc output:

~~~bash
terraform output
terraform output orders_topic_id
terraform output -json
~~~

Lệnh terraform output -json hữu ích cho automation vì trả object có value, type và metadata sensitive. Pipeline có thể parse bằng jq, nhưng phải lọc output không nhạy cảm và kiểm tra sensitive trước khi export.

Ví dụ:

~~~bash
set -euo pipefail

TF_OUTPUTS="$(terraform output -json)"

TOPIC_ID="$(printf '%s' "$TF_OUTPUTS" \
  | jq -er '.orders_topic_id | select(.sensitive == false) | .value')"

BUCKET_NAME="$(printf '%s' "$TF_OUTPUTS" \
  | jq -er '.state_bucket_name | select(.sensitive == false) | .value')"
~~~

### 6.1. Sensitive không có nghĩa là không lưu

Output có thể được đánh dấu:

~~~hcl
output "database_password" {
  description = "Database credential"
  value       = random_password.database.result
  sensitive   = true
}
~~~

Sensitive = true giúp Terraform che giá trị trong một số output CLI và plan/apply display. Nó **không loại bỏ giá trị khỏi Terraform state**. Khi gọi terraform output -json hoặc -raw, sensitive value có thể được hiển thị plaintext. Bất kỳ ai đọc được state cũng có thể tiếp cận dữ liệu được lưu trong đó.

Terraform có output ephemeral trong các phiên bản hỗ trợ để tránh ghi một số giá trị vào state/plan, nhưng có giới hạn nơi giá trị được phép sử dụng. Không nên dùng ephemeral như lý do để chuyển secret qua pipeline mà không có threat model. Với ứng dụng Spring Boot, tốt nhất chỉ output secret reference và để workload identity đọc secret từ secret manager.

## 7. Google Cloud Infrastructure Manager và Terraform outputs

Google Cloud Infrastructure Manager triển khai cấu hình Terraform và quản lý deployment/revision. Trong kết quả apply, ApplyResults có map outputs; mỗi output có value và cờ sensitive.

Terraform module có thể khai báo:

~~~hcl
output "orders_topic_name" {
  description = "Topic consumed by the orders publisher"
  value       = google_pubsub_topic.orders.name
}

output "orders_subscription_name" {
  description = "Subscription consumed by the orders worker"
  value       = google_pubsub_subscription.orders.name
}

output "orders_bucket_name" {
  description = "Storage bucket used by the application"
  value       = google_storage_bucket.orders.name
}
~~~

Ví dụ cấu trúc output trong kết quả apply:

~~~json
{
  "outputs": {
    "orders_topic_name": {
      "sensitive": false,
      "value": "orders-events"
    },
    "orders_subscription_name": {
      "sensitive": false,
      "value": "orders-processing"
    },
    "orders_bucket_name": {
      "sensitive": false,
      "value": "orders-state-production"
    }
  }
}
~~~

Pipeline dùng kết quả apply hoặc API response của Infrastructure Manager để lấy output map. Lệnh gcloud infra-manager deployments describe dùng để xem trạng thái deployment và revision; không nên giả định mọi output đều có mặt trong mọi dạng mô tả deployment. Đọc đúng ApplyResults.outputs hoặc nguồn Terraform output tương ứng với workflow đang dùng.

Cờ sensitive là metadata để automation biết output có nhạy cảm hay không; pipeline vẫn phải kiểm soát quyền đọc, log và nơi lưu kết quả. Không xem cờ này như một secret manager.

## 8. So sánh output giữa bốn công cụ

| Tiêu chí | CloudFormation | Bicep/ARM | Terraform | Google Cloud Infrastructure Manager |
|---|---|---|---|---|
| Khai báo | Outputs | output name type = value | output block | Terraform output block |
| Kết quả | Stack outputs | Deployment outputs | Terraform state/output | ApplyResults outputs |
| Cách đọc phổ biến | describe-stacks | az deployment group show | terraform output -json | Apply result/API outputs |
| Output module | Nested stack/module hoặc export/import | module.outputs.name | Child module outputs | Terraform module outputs |
| Sensitive handling | Không tự che output | @secure() cho string/object theo version hỗ trợ | sensitive = true, state vẫn giữ giá trị | Có cờ sensitive trong output metadata |
| Cross-module reference | Export/import hoặc stack output | Bicep module output | Module output | Terraform module output |
| Rủi ro cần nhớ | Không đưa secret vào Outputs | Output thường có thể hiện trong deployment history | JSON/raw có thể hiện plaintext; state nhạy cảm | Kiểm tra sensitive và quyền truy cập apply result |

Các công cụ đều trả về output, nhưng output không tự trở thành environment variable của Spring Boot. Pipeline hoặc deployment platform phải thực hiện bước chuyển đổi.

## 9. Chuẩn hóa output thành configuration manifest

Một cách triển khai dễ kiểm thử là tạo một manifest JSON/YAML sau khi IaC apply thành công. Manifest là artifact của pipeline, chứa contract version, environment và những giá trị không nhạy cảm.

Ví dụ YAML:

~~~yaml
contractVersion: 1
service: orders
environment: production
cloudProvider: azure
region: southeastasia
resources:
  messaging:
    endpoint: orders-prod.servicebus.windows.net
    destination: order-events
  storage:
    endpoint: https://ordersstateprod.blob.core.windows.net
    container: order-checkpoints
  database:
    host: orders-prod.database.example
    port: 5432
identity:
  mode: workload
~~~

Không đưa password, client secret, private key hoặc connection string có shared key vào manifest. Nếu cần secret, manifest có thể chứa reference:

~~~yaml
secrets:
  databaseCredential:
    provider: azure-key-vault
    reference: https://orders-vault.vault.azure.net/secrets/orders-db
~~~

Manifest nên:
- Có contractVersion.
- Có service và environment.
- Có schema được kiểm tra trước khi publish.
- Không chứa secret value.
- Có owner và thời gian tạo trong metadata artifact hoặc pipeline attestation.
- Được lưu với access control và retention phù hợp.
- Được gắn với deployment revision đã tạo ra outputs.

Không dùng manifest làm nguồn sự thật độc lập lâu dài nếu có thể truy xuất từ IaC deployment. Nó là artifact chuyển tiếp để deploy ứng dụng một cách xác định.

## 10. Chuyển outputs sang environment variables

Spring Boot có thể đọc cấu hình từ environment variables. Pipeline có thể chuyển các output đã chuẩn hóa thành tên biến môi trường.

Ví dụ mapping:

| Output contract | Environment variable | Spring property |
|---|---|---|
| resources.messaging.endpoint | APP_CLOUD_MESSAGING_ENDPOINT | app.cloud.messaging.endpoint |
| resources.messaging.destination | APP_CLOUD_MESSAGING_DESTINATION | app.cloud.messaging.destination |
| resources.messaging.queueUrl | APP_CLOUD_MESSAGING_QUEUEURL | app.cloud.messaging.queue-url |
| resources.storage.endpoint | APP_CLOUD_STORAGE_ENDPOINT | app.cloud.storage.endpoint |
| resources.storage.container | APP_CLOUD_STORAGE_CONTAINER | app.cloud.storage.container |
| resources.storage.bucketName | APP_CLOUD_STORAGE_BUCKETNAME | app.cloud.storage.bucket-name |
| resources.database.host | APP_CLOUD_DATABASE_HOST | app.cloud.database.host |
| resources.database.port | APP_CLOUD_DATABASE_PORT | app.cloud.database.port |
| deployment.region | APP_CLOUD_REGION | app.cloud.region |
| deployment.projectId | APP_CLOUD_PROJECTID | app.cloud.project-id |
| identity.mode | APP_CLOUD_IDENTITY_MODE | app.cloud.identity.mode |

Spring Boot relaxed binding chuyển property dạng canonical sang environment variable bằng cách thay dấu chấm bằng dấu gạch dưới, bỏ dấu gạch nối và viết hoa. Ví dụ app.cloud.messaging.queue-url thành APP_CLOUD_MESSAGING_QUEUEURL. Vì vậy hãy thống nhất property name và mapping trong pipeline; không tự tạo tên biến tùy ý rồi mong binder đoán đúng.

### 10.1. Lấy output CloudFormation trong pipeline

Ví dụ Bash lấy queue URL và bucket name rồi export cho bước deploy:

~~~bash
set -euo pipefail

STACK_NAME="orders-infrastructure-production"

STACK_OUTPUTS="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --query 'Stacks[0].Outputs' \
  --output json)"

QUEUE_URL="$(printf '%s' "$STACK_OUTPUTS" \
  | jq -er '.[] | select(.OutputKey == "OrdersQueueUrl") | .OutputValue')"

BUCKET_NAME="$(printf '%s' "$STACK_OUTPUTS" \
  | jq -er '.[] | select(.OutputKey == "OrdersBucketName") | .OutputValue')"

test -n "$QUEUE_URL"
test -n "$BUCKET_NAME"

export APP_CLOUD_MESSAGING_QUEUEURL="$QUEUE_URL"
export APP_CLOUD_STORAGE_BUCKETNAME="$BUCKET_NAME"
~~~

Đây là ví dụ minh họa cho pipeline shell. SQS queue URL là địa chỉ của queue cụ thể, không phải endpoint chung của dịch vụ SQS; vì vậy nó được bind vào queue-url riêng. Tương tự, S3 bucket name và Azure Blob container name là hai loại destination khác nhau, không nên gộp thành một trường nếu ứng dụng cần dùng cả hai provider.

### 10.2. Lấy output Bicep trong pipeline

~~~bash
set -euo pipefail

DEPLOYMENT_OUTPUTS="$(az deployment group show \
  --resource-group rg-orders-production \
  --name orders-infrastructure \
  --query properties.outputs \
  --output json)"

BLOB_ENDPOINT="$(printf '%s' "$DEPLOYMENT_OUTPUTS" \
  | jq -er '.blobEndpoint.value')"

CONTAINER_NAME="$(printf '%s' "$DEPLOYMENT_OUTPUTS" \
  | jq -er '.checkpointContainerName.value')"

test -n "$BLOB_ENDPOINT"
test -n "$CONTAINER_NAME"

export APP_CLOUD_STORAGE_ENDPOINT="$BLOB_ENDPOINT"
export APP_CLOUD_STORAGE_CONTAINER="$CONTAINER_NAME"
~~~

Nếu output có cấu trúc hoặc kiểu khác với dự kiến, jq -e giúp pipeline dừng thay vì export giá trị rỗng. Không in toàn bộ deployment outputs ra log nếu chúng có thể chứa dữ liệu nhạy cảm.

### 10.3. Lấy output Terraform trong pipeline

~~~bash
set -euo pipefail

TF_OUTPUTS="$(terraform output -json)"

TOPIC_NAME="$(printf '%s' "$TF_OUTPUTS" \
  | jq -er '.orders_topic_name | select(.sensitive == false) | .value')"

SUBSCRIPTION_NAME="$(printf '%s' "$TF_OUTPUTS" \
  | jq -er '.orders_subscription_name | select(.sensitive == false) | .value')"

export APP_CLOUD_MESSAGING_TOPIC="$TOPIC_NAME"
export APP_CLOUD_MESSAGING_SUBSCRIPTION="$SUBSCRIPTION_NAME"
~~~

Nếu một output bị đánh dấu sensitive, filter sẽ không trả giá trị và pipeline thất bại. Đây là hành vi có chủ ý: secret phải được xử lý qua secret manager, không được vô tình biến thành environment variable thông thường.

### 10.4. Google Cloud Infrastructure Manager

Khi dùng Infrastructure Manager, pipeline lấy map outputs từ kết quả apply/API. Mỗi entry có dạng sensitive và value; chỉ chuyển các entry được đánh dấu không nhạy cảm. Lưu deployment name và revision để truy vết output nào đã được dùng khi deploy ứng dụng.

Dùng gcloud infra-manager deployments describe để xác minh deployment đã ở trạng thái thành công và xác định revision hiện hành. Việc trích xuất outputs cần dùng đúng kết quả apply hoặc API response của workflow, không parse một trường output giả định từ response khác.

## 11. Spring Boot externalized configuration

Spring Boot cho phép cùng một artifact chạy ở nhiều môi trường bằng cách đọc cấu hình từ các nguồn bên ngoài JAR:

- application.yml hoặc application.properties.
- File cấu hình đặt cạnh artifact.
- Environment variables.
- Java system properties và command-line arguments.
- SPRING_APPLICATION_JSON.
- Configuration tree được mount từ volume/secret.
- Config data được import từ nguồn cấu hình hỗ trợ.

Các property source có thứ tự ưu tiên. Environment variables có thể ghi đè giá trị trong file cấu hình đóng gói trong JAR; command-line arguments thường có ưu tiên cao hơn. Vì vậy, không hardcode endpoint production vào artifact và kỳ vọng nó luôn được giữ nguyên khi deploy.

Ví dụ file mặc định:

~~~yaml
app:
  cloud:
    provider: local
    region: local
    project-id: local-project
    messaging:
      endpoint: localhost
      destination: orders-local
      queue-url: http://localhost:4566/000000000000/orders-local
    storage:
      endpoint: http://localhost:10000/devstoreaccount1
      container: orders-local
      bucket-name: orders-local
~~~

Ở production, deployment platform inject các environment variables đã lấy từ output contract để ghi đè các giá trị local/default.

### 11.1. Cấu hình từ file ngoài JAR

Có thể mount một file application-production.yml vào container và chỉ định:

~~~bash
SPRING_CONFIG_ADDITIONALLOCATION="optional:file:/etc/orders-config/"
SPRING_PROFILES_ACTIVE="production"
~~~

Dùng spring.config.additional-location khi muốn bổ sung file ngoài JAR; spring.config.location thay thế các location mặc định nên cần cẩn thận hơn. Không đặt các file cấu hình production có secret trong image layer hoặc repository.

### 11.2. Configuration tree cho secret

Spring Boot hỗ trợ configtree: để đọc file trong một thư mục như các property. Ví dụ volume mount:

~~~text
/run/secrets/
  database/
    username
    password
~~~

Cấu hình import:

~~~yaml
spring:
  config:
    import: optional:configtree:/run/secrets/
~~~

Các file sẽ được bind thành property theo đường dẫn. Đây là lựa chọn phù hợp khi platform mount secret volume; cũng có thể dùng secret integration của cloud provider để runtime identity đọc secret trực tiếp.

## 12. Bind output contract bằng ConfigurationProperties

Không nên inject hàng chục giá trị rời rạc bằng Value. Dùng ConfigurationProperties để tạo một object có cấu trúc, kiểu dữ liệu và validation.

Nếu dự án chưa có Jakarta Validation, thêm dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Ví dụ:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.cloud")
public record CloudRuntimeProperties(
        @NotBlank String provider,
        @NotBlank String region,
        String projectId,
        @NotNull @Valid Messaging messaging,
        @NotNull @Valid Storage storage,
        @NotNull @Valid Database database) {

    @AssertTrue(message = "projectId is required when cloud provider is gcp")
    public boolean isProjectIdConfiguredForProvider() {
        return !"gcp".equalsIgnoreCase(provider)
                || (projectId != null && !projectId.isBlank());
    }

    public record Messaging(
            String endpoint,
            String destination,
            String queueUrl) {

        @AssertTrue(message = "Configure a messaging endpoint, destination or queue URL")
        public boolean isDestinationConfigured() {
            return (endpoint != null && !endpoint.isBlank())
                    || (destination != null && !destination.isBlank())
                    || (queueUrl != null && !queueUrl.isBlank());
        }
    }

    public record Storage(
            String endpoint,
            String container,
            String bucketName) {

        @AssertTrue(message = "Configure a storage endpoint, container or bucket name")
        public boolean isStorageLocationConfigured() {
            return (endpoint != null && !endpoint.isBlank())
                    || (container != null && !container.isBlank())
                    || (bucketName != null && !bucketName.isBlank());
        }
    }

    public record Database(
            @NotBlank String host,
            @Positive int port) {
    }
}
~~~

Đăng ký properties bằng scan:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

Khi property bắt buộc bị thiếu hoặc không hợp lệ, Spring Boot báo lỗi binding/validation và dừng startup. Điều này tốt hơn để ứng dụng chạy rồi mới phát hiện endpoint rỗng khi xử lý request.

### 12.1. Không trộn output contract với credential

CloudRuntimeProperties chỉ chứa endpoint, destination và tên resource. Credential được tạo bằng SDK credential chain tương ứng với provider. Ví dụ Azure dùng DefaultAzureCredential, AWS dùng default credentials provider chain, Google Cloud dùng Application Default Credentials hoặc Workload Identity.

Không thêm accessKey, clientSecret, sasToken vào record này nếu ứng dụng có thể lấy token bằng workload identity. Nếu buộc phải dùng secret, bind secret từ config tree/secret integration riêng và bảo vệ property source.

## 13. Tạo SDK client từ cấu hình đã bind

Ví dụ Azure Event Grid publisher. Bean này chỉ đăng ký trong profile Azure/Event Grid và output contract phải cung cấp messaging endpoint:

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
            CloudRuntimeProperties properties,
            TokenCredential credential) {
        return new EventGridPublisherClientBuilder()
                .endpoint(properties.messaging().endpoint())
                .credential(credential)
                .buildEventGridEventPublisherClient();
    }
}
~~~

Ví dụ thể hiện nguyên tắc wiring. Nếu messaging.endpoint là hostname của Service Bus hoặc URL của một dịch vụ khác, phải dùng SDK client builder tương ứng; không dùng Event Grid client cho mọi messaging service.

Với AWS S3, Spring service có thể inject S3Client được tạo bằng S3Client.builder() và default credentials provider. Với Google Pub/Sub, dùng client được khởi tạo bằng Application Default Credentials hoặc workload identity. Trong cả ba trường hợp, endpoint/resource name đến từ config contract, credential đến từ identity runtime.

Ví dụ AWS SDK for Java v2: region lấy từ output/config contract, còn credential provider lấy credential chain của workload. SDK tự chọn endpoint dịch vụ theo region trong trường hợp không cấu hình endpoint tùy chỉnh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class S3ClientConfiguration {

    @Bean
    S3Client s3Client(CloudRuntimeProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~

Ví dụ Google Cloud Pub/Sub: project ID và topic name đến từ cấu hình đã bind; Publisher dùng Application Default Credentials để lấy danh tính runtime:

~~~java
import com.google.cloud.pubsub.v1.Publisher;
import com.google.pubsub.v1.TopicName;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class PubSubClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    Publisher ordersPublisher(CloudRuntimeProperties properties)
            throws IOException {
        return Publisher.newBuilder(TopicName.of(
                properties.projectId(),
                properties.messaging().destination())).build();
    }
}
~~~

Các ví dụ yêu cầu dependency tương ứng của AWS SDK for Java v2 (S3) hoặc Google Cloud Pub/Sub client library. Trong ứng dụng thực tế, chỉ đăng ký client bean cho provider/profile đang chạy; không khởi tạo cả ba client nếu deployment chỉ dùng một cloud.

Client thường nên là singleton bean được tái sử dụng theo lifecycle ứng dụng. Không tạo SDK client cho từng request hoặc gọi API quản trị để tạo resource trong business handler.

## 14. Kiểm tra contract trước khi deploy

Pipeline không nên chỉ kiểm tra output có tồn tại. Cần validate cấu trúc và giá trị:

- contractVersion nằm trong tập version ứng dụng hỗ trợ.
- service và environment khớp deployment target.
- Provider đúng với image/config profile.
- Endpoint dùng scheme/hostname hợp lệ.
- Destination name không rỗng.
- Resource ID thuộc account/subscription/project được mong đợi.
- Output nhạy cảm không xuất hiện trong manifest.
- Tất cả property bắt buộc của Spring Boot có mapping.
- Resource đã hoàn tất provisioning và role assignment đã được tạo.
- Workload identity được gắn vào compute platform trước smoke test.

Có thể dùng JSON Schema hoặc một bước validation nhỏ trong pipeline để kiểm tra manifest. Không dùng logic kiểu “nếu rỗng thì tạo resource”; thiếu output là lỗi của provisioning/configuration pipeline cần sửa tại nguồn.

### 14.1. Contract versioning

Khi thay đổi tên hoặc cấu trúc output:
- Tăng contractVersion nếu consumer cần thay đổi.
- Có thể thêm field optional mà không phá consumer cũ.
- Không đổi ý nghĩa một field đang dùng mà vẫn giữ nguyên version.
- Duy trì một khoảng tương thích khi rollout nhiều phiên bản.
- Ghi nhận producer IaC revision và consumer application version.
- Có test xác minh manifest mới bind được vào ứng dụng.

Nếu đổi messaging.destination sang một object lồng nhau, ứng dụng cũ có thể không bind được. Tạo contract version mới hoặc giữ field cũ trong giai đoạn chuyển tiếp.

## 15. Rollout khi output thay đổi

Thay output có thể đồng nghĩa endpoint, queue hoặc resource đã thay đổi. Pipeline nên phối hợp provisioning và application rollout theo thứ tự:

1. Provision resource mới.
2. Cấp quyền cho workload identity trên resource mới.
3. Chờ role assignment/network propagation.
4. Xuất output contract mới.
5. Deploy ứng dụng đọc output mới.
6. Chạy readiness/smoke test.
7. Chuyển traffic hoặc producer sang resource mới.
8. Xác minh backlog và dữ liệu cũ đã được xử lý.
9. Thu hồi quyền cũ và xóa resource cũ trong change riêng.

Không thay output của resource đang phục vụ rồi xóa resource cũ ngay. Queue có thể còn message, database có thể còn transaction hoặc consumer cũ vẫn đang chạy. Output version phải gắn với một rollout có thể rollback.

## 16. Output, secret reference và secret value

| Giá trị | Ví dụ | Nơi lưu |
|---|---|---|
| Endpoint | Event Grid URL, Pub/Sub endpoint | IaC output/config manifest |
| Resource ID | ARN, Azure resource ID, project resource name | IaC output |
| Destination | Queue/topic/container name | IaC output/config manifest |
| Workload identity reference | Role ARN, managed identity client ID | IaC output hoặc deployment metadata |
| Secret reference | Key Vault URI, Secrets Manager ARN, Secret Manager version path | Config manifest hoặc platform secret reference |
| Secret value | Password, private key, shared access key | Secret manager, không phải output thường |

Cần lưu ý khác biệt:
- CloudFormation Outputs không che giá trị.
- Terraform sensitive chỉ che một số cách hiển thị; state vẫn lưu giá trị và JSON/raw output có thể lộ.
- Bicep có secure outputs theo version hỗ trợ, nhưng secret vẫn nên được quản lý qua Key Vault/identity khi có thể.
- Infrastructure Manager đánh dấu output sensitive trong kết quả apply; pipeline vẫn phải giới hạn quyền và không log payload.

Không giả định output bị redacted đồng nghĩa giá trị không thể bị truy cập. Kiểm tra quyền đọc deployment history, Terraform state, pipeline artifact và log.

## 17. Quyền đọc outputs và pipeline artifact

Output có thể chứa thông tin nội bộ như endpoint private, resource IDs và tên destination. Cần giới hạn:
- Ai có quyền đọc CloudFormation stack outputs.
- Ai có quyền đọc Azure deployment history.
- Ai có quyền đọc Terraform state và Infrastructure Manager deployment results.
- Ai có quyền tải manifest artifact.
- Job nào được phép inject output vào application deployment.
- Log nào được phép in output và metadata.

Tách artifact theo environment và service. Không để pipeline dev tải manifest production hoặc ghi đè config artifact của service khác. Nếu output được truyền giữa nhiều job, dùng artifact store có access control và retention phù hợp.

## 18. Readiness và startup validation trong Spring Boot

Spring Boot nên xác minh config có đầy đủ và hợp lệ trước khi nhận traffic. Có thể chia thành:

- **Configuration validation:** field bắt buộc không rỗng, URL/port hợp lệ, provider được hỗ trợ.
- **Client construction:** SDK client có thể được tạo từ endpoint và credential chain.
- **Connectivity check:** kiểm tra kết nối tới dependency khi phù hợp.
- **Authorization check:** xác minh workload identity có quyền data-plane cần thiết.
- **Readiness:** chỉ báo ready khi ứng dụng đủ điều kiện nhận traffic.
- **Liveness:** chỉ phản ánh process có còn hoạt động; không nên restart pod chỉ vì một cloud dependency tạm thời unavailable.

Không gọi create topic/queue/bucket trong readiness. Nếu resource chưa tồn tại, readiness phải báo lỗi để pipeline/platform sửa IaC hoặc output mapping.

Không phải dependency nào cũng cần được ping trong startup. Với dịch vụ có throttling hoặc startup dependency tạm thời, có thể dùng retry có giới hạn và readiness state thay vì làm startup treo vô hạn.

## 19. CI/CD pipeline mẫu

Một pipeline có thể có các stage sau:

~~~mermaid
flowchart TD
    SRC["IaC source"] --> VALIDATE["Lint and validate"]
    VALIDATE --> PLAN["Plan / what-if / change set"]
    PLAN --> APPROVE["Review infrastructure diff"]
    APPROVE --> APPLY["Apply IaC"]
    APPLY --> OUTPUT["Collect provider outputs"]
    OUTPUT --> CONTRACT["Normalize and validate contract"]
    CONTRACT --> ARTIFACT["Publish config artifact"]
    ARTIFACT --> DEPLOY["Deploy Spring Boot"]
    DEPLOY --> BIND["Bind and validate config"]
    BIND --> SMOKE["Identity and connectivity smoke test"]
    SMOKE --> TRAFFIC["Enable traffic"]
~~~

Các bước cần lưu ý:

1. Validate IaC source và schema output.
2. Tạo plan/change set/what-if để review.
3. Apply resource và role assignment.
4. Chờ provisioning hoàn tất.
5. Lấy output từ đúng deployment revision.
6. Chuẩn hóa output thành manifest có contract version.
7. Loại bỏ secret value; kiểm tra trường sensitive.
8. Publish artifact theo environment.
9. Inject environment variables/config files vào deployment.
10. Deploy ứng dụng và xác minh config binding.
11. Chạy smoke test bằng workload identity.
12. Chỉ chuyển traffic khi readiness đạt yêu cầu.

Có thể build application image song song với IaC plan để tiết kiệm thời gian, nhưng không deploy revision phụ thuộc resource trước khi resource, role và network đã sẵn sàng.

## 20. Kiểm thử output contract và cấu hình ứng dụng

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| Output có đủ field | Apply IaC vào môi trường test | Manifest chứa các field bắt buộc |
| Output thiếu field | Xóa output trong fixture test | Contract validation thất bại |
| Output sai type | Trả port dạng text hoặc endpoint dạng object | Schema validation thất bại |
| Output sai environment | Dùng manifest dev cho deployment prod | Pipeline từ chối |
| Output sensitive | Đánh dấu output sensitive | Không được export vào manifest thường |
| CloudFormation stack in progress | Đọc outputs khi stack chưa hoàn tất | Pipeline chờ hoặc fail có kiểm soát |
| Bicep module output | Đổi tên output module | Consumer contract test phát hiện mismatch |
| Terraform sensitive JSON | Đánh dấu sensitive rồi chạy output -json | Pipeline không export value |
| Infrastructure Manager result | Đọc ApplyResults outputs | Chỉ dùng entry có sensitive=false |
| Spring config binding | Inject environment variables vào test context | ConfigurationProperties bind đúng |
| Missing required property | Bỏ endpoint hoặc destination | Application context fail validation |
| Override precedence | Cấp env var khác file YAML | Giá trị env var được dùng |
| Identity | Chạy integration test bằng workload identity | Chỉ thao tác data-plane được cấp quyền |
| Wrong resource | Cấp endpoint/resource name không tồn tại | Readiness/smoke test thất bại rõ ràng |
| Rollout output version | Deploy manifest version mới | Ứng dụng hỗ trợ hoặc từ chối version có chủ đích |

Unit test có thể dùng ApplicationContextRunner hoặc SpringBootTest để xác minh binding/validation. Integration test cần chạy trong cloud test environment để xác minh IAM/RBAC, endpoint, network và resource thực tế.

## 21. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Environment variable rỗng | Pipeline query sai output key | Validate manifest trước deploy |
| App bind sai property | Tên biến không theo relaxed binding | Chuẩn hóa mapping property/env |
| Spring dùng giá trị trong JAR | Chưa inject env var hoặc property name sai | Kiểm tra property source và configprops |
| CloudFormation output không có | Stack chưa hoàn tất hoặc key sai | Chờ stack complete, kiểm tra describe-stacks |
| Bicep output null | Resource conditional hoặc module output sai | Kiểm tra điều kiện và output expression |
| Terraform output bị che | Output marked sensitive | Không lấy secret từ output; dùng secret manager |
| Terraform state lộ credential | Secret được lưu trong state | Rotate credential và bảo vệ backend state |
| GCP output thiếu | Đọc deployment metadata thay vì apply result outputs | Dùng ApplyResults hoặc nguồn output đúng |
| App nhận 403 | Workload identity thiếu data-plane role | Kiểm tra role và propagation |
| App nhận 404 | Endpoint/destination sai hoặc resource chưa tồn tại | So sánh output với resource ID thực tế |
| Dev dùng resource prod | Manifest/artifact bị dùng nhầm môi trường | Tách artifact và policy theo environment |
| Đổi endpoint gây downtime | Chuyển output mà không rollout tương thích | Provision mới, deploy, cutover, rồi retire cũ |

## 22. Checklist trước production

- **Output contract:** Có tên, kiểu, mô tả, version và owner.
- **Provider mapping:** CloudFormation/Bicep/Terraform/Infrastructure Manager outputs được chuẩn hóa.
- **Validation:** Pipeline kiểm tra required fields, types, environment và resource scope.
- **Sensitive data:** Không có secret value trong output thường, manifest, log hoặc image.
- **Access control:** Chỉ pipeline/job cần thiết được đọc output và artifact.
- **Spring binding:** ConfigurationProperties có validation và fail fast.
- **Property precedence:** Environment/config override được kiểm thử.
- **Identity:** SDK client dùng workload identity/credential chain phù hợp.
- **Runtime:** Ứng dụng chỉ sử dụng resource đã provision.
- **Readiness:** Kết nối/quyền được kiểm tra mà không tự tạo resource.
- **Versioning:** Output contract có version và quy tắc tương thích.
- **Rollout:** Có kế hoạch khi endpoint/resource name thay đổi.
- **Secrets:** Chỉ truyền secret reference; runtime đọc secret theo quyền tối thiểu.
- **Audit:** Biết IaC revision, output artifact và application revision tương ứng.
- **Testing:** Có test thiếu output, sai type, sai env, sensitive output, 403/404 và config binding.
- **Recovery:** Có rollback/cutover và giữ resource cũ đủ lâu để xử lý dữ liệu còn tồn đọng.

## 23. Tổng kết

IaC outputs là hợp đồng dữ liệu giữa bước cấp phát hạ tầng và bước triển khai ứng dụng. CloudFormation trả stack outputs; Bicep trả deployment/module outputs; Terraform trả output values từ state; Google Cloud Infrastructure Manager trả map outputs trong kết quả apply. Pipeline cần đọc đúng nguồn, kiểm tra kiểu và environment, chuẩn hóa thành configuration contract rồi truyền các giá trị không nhạy cảm vào Spring Boot.

Spring Boot externalized configuration cho phép cùng một artifact chạy ở nhiều môi trường. Dùng ConfigurationProperties để bind và validate endpoint/resource name; dùng environment variables, file config hoặc config tree để cấp giá trị. Secret nên được tham chiếu qua Key Vault, Secrets Manager hoặc Secret Manager và đọc bằng workload identity. Khi output contract có version, pipeline có kiểm tra, và ứng dụng fail fast khi thiếu cấu hình, việc triển khai Spring Boot trên AWS, Azure và Google Cloud trở nên lặp lại, dễ kiểm toán và an toàn hơn.

## Tài liệu tham khảo

- [CloudFormation Outputs syntax](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/outputs-section-structure.html)
- [Export and import CloudFormation outputs](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/using-cfn-stack-exports.html)
- [Outputs in Bicep](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/outputs)
- [Bicep modules and module outputs](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/modules)
- [Use Bicep to manage secrets](https://learn.microsoft.com/en-us/azure/azure-resource-manager/bicep/scenarios-secrets)
- [Terraform output values](https://developer.hashicorp.com/terraform/language/values/outputs)
- [Terraform output block reference](https://developer.hashicorp.com/terraform/language/block/output)
- [Infrastructure Manager ApplyResults](https://docs.cloud.google.com/infrastructure-manager/docs/reference/rest/v1/ApplyResults)
- [View Infrastructure Manager deployments](https://docs.cloud.google.com/infrastructure-manager/docs/view-deployments)
- [Spring Boot externalized configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html)

