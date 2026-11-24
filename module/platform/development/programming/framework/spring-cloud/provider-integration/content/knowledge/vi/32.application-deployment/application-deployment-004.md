# Cấp danh tính cho ứng dụng trên máy ảo, container và Kubernetes

Một ứng dụng Spring Boot thường cần truy cập nhiều dịch vụ managed: đọc object từ S3 hoặc Cloud Storage, ghi Blob Storage, gửi message tới Service Bus, SQS hoặc Pub/Sub, đọc secret từ Key Vault hay Secret Manager. Để các thao tác đó được cho phép, ứng dụng phải có một danh tính mà cloud provider nhận diện được và các quyền phù hợp trên resource đích.

Trên máy ảo, danh tính thường được gắn vào VM hoặc instance. Với container, danh tính có thể gắn riêng cho từng task hoặc service. Trên Kubernetes, một Pod dùng Kubernetes ServiceAccount và nền tảng liên kết danh tính đó với IAM role, Managed Identity hoặc Google Cloud service account. Khi cấu hình đúng, ứng dụng nhận credential ngắn hạn từ môi trường chạy và SDK tự làm mới token. Không cần đóng gói access key, client secret hay service account key vào JAR hoặc image.

Bài học thuộc chương **Triển khai ứng dụng** của mô-đun **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mô-đun thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này tập trung vào cấp danh tính cho workload trên VM, container và Kubernetes, thiết lập quan hệ tin cậy, cấp quyền tối thiểu và dùng credential provider của Java SDK trong Spring Boot.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt user identity, workload identity, Kubernetes ServiceAccount và cloud service account.
- Giải thích quan hệ giữa authentication, authorization, principal, role và resource scope.
- Cấp IAM role cho Amazon EC2, ECS task, EKS Pod và chọn giữa IRSA với EKS Pod Identity.
- Dùng system-assigned hoặc user-assigned Managed Identity trên Azure VM và container platform.
- Cấu hình Microsoft Entra Workload ID cho Pod trên AKS bằng OIDC federation.
- Gắn service account vào Compute Engine VM và Cloud Run service.
- Cấu hình Workload Identity Federation for GKE cho Kubernetes workload.
- Dùng AWS SDK credential provider chain, Azure Identity và Google Application Default Credentials.
- Tách quyền của node, agent, deployment identity và application workload.
- Bảo vệ metadata endpoint, projected token và federated trust.
- Kiểm thử identity, role assignment, token refresh và quyền truy cập data plane.

## 2. Danh tính, credential và quyền là ba khái niệm riêng

Các khái niệm này liên quan nhưng không thay thế cho nhau:

- **Identity/principal:** danh tính được cloud provider nhận diện, ví dụ IAM role, Managed Identity hoặc service account.
- **Credential:** bằng chứng để chứng minh workload đang đại diện cho principal đó, ví dụ temporary AWS credentials, Microsoft Entra access token hoặc Google OAuth access token.
- **Authentication:** xác minh credential thuộc principal nào.
- **Authorization:** quyết định principal được phép thực hiện hành động nào trên resource nào.
- **Role/policy:** tập hợp quyền được gán cho principal hoặc được dùng trong trust relationship.
- **Trust relationship:** quy định ai hoặc workload nào được phép nhận/assume một danh tính.

Ví dụ một Spring Boot consumer đọc message từ Azure Service Bus:

1. Pod chạy với Kubernetes ServiceAccount tên orders-consumer.
2. AKS phát projected OIDC token cho ServiceAccount.
3. Microsoft Entra ID kiểm tra issuer, subject và audience của token với federated identity credential.
4. Entra ID cấp access token cho Managed Identity đã liên kết.
5. Service Bus kiểm tra Azure RBAC của identity đó.
6. Chỉ khi identity có role data-plane phù hợp, consumer mới nhận được message.

Việc có token hợp lệ chưa chắc đã có quyền đọc queue. Ngược lại, gán role cho một identity không giúp ứng dụng sử dụng được nếu runtime không thể lấy credential của identity đó.

### 2.1. Phân biệt identity của người vận hành và identity của workload

| Loại danh tính | Dùng cho | Ví dụ |
|---|---|---|
| Human identity | Developer, operator, administrator đăng nhập và thao tác | Microsoft Entra user, AWS IAM Identity Center user, Google user |
| CI/CD identity | Pipeline tạo resource hoặc triển khai ứng dụng | OIDC federated role, service principal, deployment service account |
| Node identity | Agent hoặc thành phần chạy trên VM/node | EC2 instance profile, VM Managed Identity, GKE node service account |
| Workload identity | Một ứng dụng hoặc workload cụ thể | ECS task role, EKS Pod role, AKS Workload ID, Cloud Run service identity |
| Kubernetes identity | Xác thực với Kubernetes API và gắn với Pod | Kubernetes ServiceAccount |

Không dùng user account của developer làm identity production. Không dùng identity có quyền quản trị hạ tầng cho Spring Boot chỉ vì pipeline đã có sẵn credential đó.

## 3. Kiến trúc cấp danh tính cho workload

~~~mermaid
flowchart TD
    subgraph PLATFORM["Cloud / Kubernetes platform"]
        PROVISION["Create identity and trust"]
        ROLE["Grant least-privilege role"]
        TOKEN["Issue or expose short-lived credential"]
    end
    subgraph APP["Spring Boot workload"]
        POD["VM process / container / Pod"]
        SDK["Java SDK credential provider"]
        CLIENT["Service client"]
    end
    RESOURCE["Managed resource: storage / messaging / database"]
    PROVISION --> ROLE
    ROLE --> TOKEN
    TOKEN --> SDK
    POD --> SDK
    SDK --> CLIENT
    CLIENT --> RESOURCE
    ROLE --> RESOURCE
~~~

Quy trình chung:

1. Tạo principal dành riêng cho workload hoặc service.
2. Thiết lập trust để đúng compute resource hoặc OIDC subject được nhận danh tính.
3. Gán role trên đúng resource và scope.
4. Gắn identity vào VM, task, service hoặc Kubernetes ServiceAccount.
5. Khởi tạo SDK client bằng credential provider phù hợp.
6. Kiểm tra quyền bằng thao tác data-plane thực tế.
7. Theo dõi lỗi authentication/authorization và vòng đời token.

Provisioner cần quyền tạo identity và role assignment. Workload chỉ cần quyền lấy credential của chính nó và gọi dịch vụ dữ liệu. Không cấp cho workload quyền tạo role hoặc sửa trust policy.

## 4. Phạm vi danh tính trên từng loại môi trường

| Môi trường chạy | Identity gắn ở đâu? | Phạm vi quyền điển hình |
|---|---|---|
| VM/EC2/Compute Engine | Instance profile, Managed Identity, attached service account | Thường áp dụng cho process trên cùng VM |
| Container trên ECS/Fargate | Task role | Riêng từng task |
| Container trên Azure Container Apps | Managed Identity của container app/revision | Theo container app hoặc identity được chọn |
| Cloud Run | Service identity | Theo Cloud Run service/job |
| EKS | IAM role liên kết Kubernetes ServiceAccount qua IRSA hoặc Pod Identity | Theo ServiceAccount/Pod |
| AKS | Microsoft Entra Workload ID liên kết ServiceAccount | Theo ServiceAccount/Pod |
| GKE | Workload Identity Federation for GKE | Theo Kubernetes ServiceAccount hoặc IAM service account được liên kết |

Điểm cần nhớ: **Kubernetes ServiceAccount không tự động là IAM role hay Azure Managed Identity.** Nó là danh tính trong Kubernetes. Cloud provider cần cấu hình federation hoặc association để ánh xạ ServiceAccount sang principal cloud.

## 5. AWS: IAM role cho ứng dụng trên Amazon EC2

### 5.1. Instance profile

Trên Amazon EC2, ứng dụng nhận quyền thông qua IAM role gắn vào instance profile. EC2 instance profile là lớp chứa role để gắn vào instance. AWS SDK for Java 2.x có thể lấy temporary credentials từ EC2 Instance Metadata Service mà không cần access key trong file cấu hình.

Trust policy tối thiểu của role cho EC2:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ec2.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Sau khi tạo role, gắn policy chỉ cho phép ứng dụng thao tác trên bucket cần dùng. Ví dụ policy đọc object trong một prefix cụ thể:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::orders-production/incoming/*"
    }
  ]
}
~~~

Nếu ứng dụng cần liệt kê object, thêm s3:ListBucket trên ARN của bucket và giới hạn prefix bằng condition phù hợp. Không cấp s3:* trên mọi bucket chỉ để thử nghiệm.

Gắn role vào EC2 instance qua instance profile bằng IaC hoặc quy trình provisioning. Ứng dụng không cần biết access key hay secret key. Khi credential gần hết hạn, SDK lấy credential mới từ metadata service.

Một EC2 instance chỉ gắn một instance profile role tại một thời điểm; các process trên VM có thể dùng cùng role đó. Nếu nhiều ứng dụng trên cùng VM cần tập quyền khác nhau, tách workload sang compute boundary riêng hoặc dùng dịch vụ container có task role riêng. Không coi container trên EC2 là ranh giới bảo mật đủ để ngăn truy cập metadata của host.

### 5.2. Bảo vệ Instance Metadata Service

Metadata endpoint có thể cấp temporary credential của instance role. Nếu ứng dụng có lỗ hổng SSRF hoặc container không tin cậy truy cập được metadata, credential có thể bị lạm dụng.

Đối với EC2 production:

- Yêu cầu IMDSv2 bằng HttpTokens=required.
- Tắt IMDS nếu workload không cần metadata.
- Giới hạn quyền của instance role.
- Không để container không tin cậy truy cập metadata credential của host.
- Với container trên EC2, kiểm tra hop limit và network isolation; hop limit bằng 1 có thể làm một số container không nhận được response IMDSv2, nhưng tăng lên 2 không thay thế việc cô lập truy cập.
- Theo dõi MetadataNoToken trước khi chuyển instance cũ sang bắt buộc IMDSv2.

Ví dụ Launch Template metadata options:

~~~yaml
MetadataOptions:
  HttpEndpoint: enabled
  HttpTokens: required
  HttpPutResponseHopLimit: 2
~~~

Hop limit 2 là cấu hình thường cần cân nhắc khi container trên EC2 phải truy cập IMDSv2. Chỉ bật theo kiến trúc đã kiểm tra; không mở rộng hop limit tùy tiện.

## 6. AWS: phân biệt ECS task role và execution role

ECS có hai role thường bị nhầm:

- **Task execution role:** ECS agent dùng để pull image từ ECR, gửi log qua awslogs driver và lấy secret được tham chiếu trong task definition.
- **Task role:** credential được cấp cho code bên trong container để gọi AWS APIs như S3, SQS hoặc DynamoDB.

Task definition có hai trường riêng:

~~~json
{
  "family": "orders-api",
  "taskRoleArn": "arn:aws:iam::111122223333:role/orders-runtime-role",
  "executionRoleArn": "arn:aws:iam::111122223333:role/orders-task-execution-role",
  "containerDefinitions": [
    {
      "name": "orders-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/orders-api:1.0.0",
      "essential": true
    }
  ]
}
~~~

Nếu ứng dụng gọi S3, quyền s3:GetObject thuộc task role. Quyền pull image và ghi log thuộc execution role. Không thêm quyền nghiệp vụ vào execution role vì container application không sử dụng role đó theo mục đích này.

Với ECS trên EC2, container instance role phục vụ ECS agent/instance; task role vẫn là identity dành cho application container. Với Fargate, không có EC2 worker do người dùng quản lý, nhưng task role và execution role vẫn là hai khái niệm riêng.

## 7. AWS EKS: IAM Roles for Service Accounts (IRSA)

IRSA liên kết một IAM role với Kubernetes ServiceAccount thông qua OIDC federation.

Luồng hoạt động:

1. EKS cluster có OIDC issuer.
2. IAM có OIDC identity provider tương ứng với issuer.
3. IAM role trust policy cho phép token có audience và subject cụ thể assume role.
4. Kubernetes ServiceAccount được annotate với role ARN.
5. Pod khai báo serviceAccountName tương ứng.
6. EKS inject projected token và các biến môi trường cần thiết.
7. AWS SDK dùng web identity token để gọi STS AssumeRoleWithWebIdentity và nhận temporary credentials.

### 7.1. Trust policy giới hạn đúng namespace và ServiceAccount

Ví dụ trust policy IRSA:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDC"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDC:aud": "sts.amazonaws.com",
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDC:sub": "system:serviceaccount:orders:orders-api"
        }
      }
    }
  ]
}
~~~

Điều kiện sub ràng buộc role vào đúng ServiceAccount orders-api trong namespace orders. Không dùng wildcard namespace hoặc ServiceAccount nếu workload không thực sự cần chia sẻ identity.

### 7.2. Kubernetes ServiceAccount và Deployment

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::111122223333:role/orders-runtime-role
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
~~~

Role policy quyết định ứng dụng được làm gì; trust policy quyết định workload nào được nhận role. Cần cả hai. Việc annotate ServiceAccount không tự cấp quyền S3 nếu IAM policy chưa có quyền đó.

## 8. AWS EKS Pod Identity

EKS Pod Identity là cơ chế khác với IRSA. EKS tạo association giữa cluster, namespace, Kubernetes ServiceAccount và IAM role. EKS Pod Identity Agent trên node cung cấp credential cho Pod. Bạn không cần thêm annotation role ARN vào ServiceAccount như IRSA.

Trust policy cho role Pod Identity dùng service principal:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "pods.eks.amazonaws.com"
      },
      "Action": [
        "sts:AssumeRole",
        "sts:TagSession"
      ],
      "Condition": {
        "StringEquals": {
          "aws:RequestTag/kubernetes-namespace": "orders",
          "aws:RequestTag/kubernetes-service-account": "orders-api"
        }
      }
    }
  ]
}
~~~

Tạo association bằng AWS CLI:

~~~bash
aws eks create-pod-identity-association \
  --cluster-name orders-prod \
  --namespace orders \
  --service-account orders-api \
  --role-arn arn:aws:iam::111122223333:role/orders-runtime-role
~~~

Pod vẫn khai báo ServiceAccount:

~~~yaml
spec:
  serviceAccountName: orders-api
~~~

Một số điểm cần kiểm tra:

- EKS Pod Identity Agent phải được cài trên cluster, trừ các môi trường như EKS Auto Mode đã tích hợp sẵn.
- IAM role cần trust policy cho pods.eks.amazonaws.com.
- Association phải trỏ đúng cluster, namespace và ServiceAccount.
- Principal tạo association cần quyền iam:PassRole đối với IAM role được gắn.
- AWS SDK version phải hỗ trợ cơ chế credential này và dùng default credential provider chain.
- Cross-account access có thể cần role chaining hoặc cấu hình ủy quyền riêng; association cơ bản gắn role trong cùng account với cluster.

### 8.1. Chọn IRSA hay EKS Pod Identity

| Tiêu chí | IRSA | EKS Pod Identity |
|---|---|---|
| Federation | OIDC provider của cluster và STS AssumeRoleWithWebIdentity | EKS Auth service và Pod Identity Agent |
| Cấu hình ServiceAccount | Annotation role ARN | Không cần annotation role |
| Thành phần node | Projected OIDC token | Pod Identity Agent |
| Trust policy | Federated OIDC principal, subject và audience | Service principal pods.eks.amazonaws.com |
| Phạm vi | Mỗi ServiceAccount được liên kết role | Association theo cluster/namespace/ServiceAccount |
| SDK | Hỗ trợ web identity provider | Default provider chain có hỗ trợ container credentials |
| Phù hợp | Cơ chế OIDC phổ biến, tương thích rộng | Cơ chế quản lý association tập trung trên EKS |

Không cấu hình đồng thời hai cơ chế một cách tùy tiện cho cùng workload. Chọn một cơ chế, kiểm tra version SDK và kiểm thử credential thực tế trong Pod.

## 9. Azure: Managed Identity trên VM và dịch vụ container

Azure Managed Identity là danh tính do Microsoft Entra quản lý cho một Azure resource. Ứng dụng lấy access token ngắn hạn; Azure quản lý credential nền và rotation.

Có hai loại:

| Loại | Vòng đời | Khi phù hợp |
|---|---|---|
| System-assigned | Tạo cùng resource; xóa resource thì identity bị xóa | Một VM hoặc một app có identity riêng |
| User-assigned | Resource identity độc lập, có thể gắn vào nhiều resource | Nhiều instance cần cùng principal hoặc cần tách vòng đời identity |

Nếu dùng chung user-assigned identity cho nhiều VM/container, mọi workload được gắn identity đều nhận cùng tập quyền. Chỉ chia sẻ khi blast radius đó được chấp nhận.

### 9.1. Gán role data-plane

Ví dụ VM cần ghi Blob Storage. Gán role Storage Blob Data Contributor cho principal của Managed Identity ở scope storage account hoặc container phù hợp:

~~~bash
az role assignment create \
  --assignee-object-id MANAGED_IDENTITY_PRINCIPAL_ID \
  --assignee-principal-type ServicePrincipal \
  --role "Storage Blob Data Contributor" \
  --scope /subscriptions/SUBSCRIPTION_ID/resourceGroups/RG_NAME/providers/Microsoft.Storage/storageAccounts/ORDERS_STORAGE
~~~

Đây là role data-plane cho thao tác blob. Role Contributor trên resource group là quyền quản lý Azure Resource Manager và không phải lựa chọn thay thế cho quyền đọc/ghi blob.

Tương tự:
- Key Vault Secrets User cho ứng dụng chỉ đọc secret.
- Azure Service Bus Data Receiver cho consumer.
- Azure Service Bus Data Sender cho publisher.
- Azure Event Hubs Data Receiver hoặc Data Sender theo vai trò consumer/publisher.

Chọn role theo hành động thật và giới hạn scope resource.

### 9.2. Token endpoint trên Azure VM

Azure Instance Metadata Service có endpoint Managed Identity. Request REST trực tiếp cần header Metadata: true để giảm nguy cơ SSRF:

~~~bash
curl "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https%3A%2F%2Fstorage.azure.com%2F" \
  -H Metadata:true
~~~

Ứng dụng Java thường không cần gọi endpoint này bằng HTTP thủ công. Azure Identity SDK xử lý token acquisition, cache và refresh. Không log access token hoặc response chứa token.

Nếu VM có nhiều user-assigned identities, credential cần chọn identity bằng client ID hoặc resource ID. Không để SDK chọn nhầm identity mặc định khi VM gắn nhiều principal.

### 9.3. Azure Container Apps

Azure Container Apps hỗ trợ system-assigned và user-assigned Managed Identity. Nền tảng cung cấp identity endpoint cùng header bảo vệ trong environment của container. Azure Identity SDK có thể sử dụng credential tương ứng; không tự viết HTTP client lấy token nếu SDK đã hỗ trợ platform.

Với user-assigned identity, cấu hình identity được gắn vào Container App và chọn đúng client ID khi tạo credential. Không truyền client secret chỉ để thay thế Managed Identity.

Ví dụ bật system-assigned identity:

~~~bash
az containerapp identity assign \
  --name orders-api \
  --resource-group rg-orders-prod \
  --system-assigned
~~~

Lấy principal ID từ kết quả lệnh để tạo Azure RBAC role assignment trên resource đích. Nếu dùng user-assigned identity, tạo identity riêng trước rồi gắn resource ID của identity vào Container App.

## 10. Azure AKS: Microsoft Entra Workload ID

AKS Workload ID dùng OIDC federation để ánh xạ Kubernetes ServiceAccount sang user-assigned Managed Identity hoặc ứng dụng Microsoft Entra. Đây là cơ chế dành cho identity của Pod, khác với identity của node hoặc cluster control plane.

Luồng:

1. Bật OIDC issuer và Workload Identity trên AKS.
2. Lấy issuer URL của cluster.
3. Tạo user-assigned Managed Identity.
4. Tạo federated identity credential với issuer, subject và audience.
5. Gán Azure RBAC data-plane role cho Managed Identity.
6. Annotate Kubernetes ServiceAccount với client ID.
7. Gắn label bắt buộc vào Pod template.
8. Azure workload identity webhook inject projected token và các biến môi trường.
9. Azure Identity SDK dùng WorkloadIdentityCredential để đổi token lấy access token.

### 10.1. Federated identity credential

Subject phải khớp chính xác:

~~~text
system:serviceaccount:orders:orders-api
~~~

Audience thường dùng:

~~~text
api://AzureADTokenExchange
~~~

Tạo federated credential bằng Azure CLI:

~~~bash
az identity federated-credential create \
  --name orders-api-federation \
  --identity-name orders-api-identity \
  --resource-group rg-orders-prod \
  --issuer AKS_OIDC_ISSUER_URL \
  --subject system:serviceaccount:orders:orders-api \
  --audiences api://AzureADTokenExchange
~~~

Thay issuer URL bằng OIDC issuer thực tế của cluster. Federated credential chỉ cho phép đổi token sang identity; nó không tự cấp quyền đọc Key Vault hoặc gửi Service Bus message. Phải gán role riêng cho Managed Identity.

### 10.2. ServiceAccount và Pod manifest

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    azure.workload.identity/client-id: "USER_ASSIGNED_IDENTITY_CLIENT_ID"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
        azure.workload.identity/use: "true"
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
~~~

Label azure.workload.identity/use: "true" là bắt buộc để webhook mutate Pod và inject cấu hình workload identity. Nếu thay annotation của ServiceAccount, cần restart Pod để cấu hình mới có hiệu lực.

### 10.3. Java credential cho AKS Workload ID

Azure Identity cung cấp WorkloadIdentityCredential. Trong Pod, webhook cung cấp các biến môi trường như AZURE_CLIENT_ID, AZURE_TENANT_ID và AZURE_FEDERATED_TOKEN_FILE.

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.WorkloadIdentityCredential;
import com.azure.identity.WorkloadIdentityCredentialBuilder;

class AzureWorkloadCredentialFactory {

    static TokenCredential create() {
        return new WorkloadIdentityCredentialBuilder()
                .clientId(System.getenv("AZURE_CLIENT_ID"))
                .tenantId(System.getenv("AZURE_TENANT_ID"))
                .tokenFilePath(System.getenv("AZURE_FEDERATED_TOKEN_FILE"))
                .build();
    }
}
~~~

Đoạn code này dành cho Pod đã được cấu hình Microsoft Entra Workload ID. Nếu chạy trên Azure VM hoặc Container Apps dùng Managed Identity, chọn ManagedIdentityCredential hoặc credential chain phù hợp thay vì WorkloadIdentityCredential.

## 11. Google Cloud: service account trên Compute Engine VM

Compute Engine VM có thể chạy dưới một Google Cloud service account được gắn khi tạo hoặc cập nhật VM. Client library dùng Application Default Credentials (ADC) để lấy credential từ metadata server.

Nên tạo user-managed service account riêng cho ứng dụng, thay vì dùng Compute Engine default service account có thể đã được gán quyền rộng ở phạm vi project. Gán IAM role cần thiết cho service account rồi gắn vào VM.

Ví dụ tạo VM với service account:

~~~bash
gcloud compute instances create orders-worker \
  --zone asia-southeast1-b \
  --service-account orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --scopes https://www.googleapis.com/auth/cloud-platform
~~~

Access scope cloud-platform cho phép VM gọi các API Google Cloud mà IAM policy của service account cho phép. Access scope không cấp thêm IAM permission; IAM role vẫn quyết định hành động được phép. Đây là cách khuyến nghị thay vì dùng scope hẹp làm lớp authorization chính.

Ví dụ service account chỉ có quyền publish vào một topic nên nhận roles/pubsub.publisher ở scope topic hoặc project theo chính sách tổ chức. Không cấp Project Editor cho workload.

Gán quyền publish ở scope topic:

~~~bash
gcloud pubsub topics add-iam-policy-binding orders-events \
  --project PROJECT_ID \
  --member "serviceAccount:orders-runtime@PROJECT_ID.iam.gserviceaccount.com" \
  --role roles/pubsub.publisher
~~~

## 12. Google Cloud: service identity cho Cloud Run

Cloud Run service hoặc job dùng service account làm service identity khi gọi Google Cloud APIs. Nên tạo service account riêng cho mỗi workload hoặc nhóm workload có cùng quyền.

Triển khai Cloud Run với service account:

~~~bash
gcloud run deploy orders-api \
  --image asia-southeast1-docker.pkg.dev/PROJECT_ID/apps/orders-api:1.0.0 \
  --region asia-southeast1 \
  --service-account orders-runtime@PROJECT_ID.iam.gserviceaccount.com
~~~

Có hai quyền cần phân biệt:

- Deployer cần quyền gắn service account vào Cloud Run service, thường là Service Account User trên service account được chọn.
- Service identity cần IAM role trên resource mà ứng dụng truy cập, ví dụ Pub/Sub Publisher hoặc Storage Object Viewer.

Role thường dùng cho deployer là `roles/iam.serviceAccountUser` trên service account được gắn. Role này cho phép deployer thực hiện thao tác actAs; nó không cấp quyền publish/đọc dữ liệu cho chính Cloud Run service.

Không cấp role runtime cho deployer chỉ vì pipeline cần deploy service. Không dùng service account mặc định của project nếu workload cần tập quyền riêng.

## 13. Google Kubernetes Engine: Workload Identity Federation for GKE

GKE Workload Identity Federation cho phép Pod sử dụng Kubernetes ServiceAccount để nhận danh tính IAM mà không cần service account key file. GKE metadata server nhận request credential từ client library và trao đổi projected Kubernetes token lấy federated access token.

Có hai cách phổ biến:

- **Direct resource access:** gán IAM role trực tiếp cho principal đại diện cho Kubernetes ServiceAccount.
- **Impersonate Google service account:** liên kết Kubernetes ServiceAccount với Google service account; cấp roles/iam.workloadIdentityUser cho KSA trên GSA rồi gán quyền resource cho GSA.

Ví dụ cách liên kết KSA với GSA:

~~~bash
gcloud iam service-accounts add-iam-policy-binding \
  orders-runtime@PROJECT_ID.iam.gserviceaccount.com \
  --role roles/iam.workloadIdentityUser \
  --member "serviceAccount:PROJECT_ID.svc.id.goog[orders/orders-api]"
~~~

Annotate Kubernetes ServiceAccount:

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: orders
  annotations:
    iam.gke.io/gcp-service-account: orders-runtime@PROJECT_ID.iam.gserviceaccount.com
~~~

Gán quyền publish cho Google service account trên topic cần dùng, ví dụ roles/pubsub.publisher. Sau đó Pod sử dụng KSA:

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: orders
spec:
  replicas: 2
  selector:
    matchLabels:
      app: orders-api
  template:
    metadata:
      labels:
        app: orders-api
    spec:
      serviceAccountName: orders-api
      containers:
        - name: orders-api
          image: example/orders-api:1.0.0
~~~

Cả IAM policy binding trên GSA và annotation trên KSA đều cần có khi dùng mô hình liên kết này. GKE Workload Identity Federation phải được bật cho cluster/node pool tương ứng.

Không dùng service account của node làm danh tính chung cho tất cả Pod. Nếu các Pod dùng chung node identity, một workload có thể thừa hưởng quyền mà workload khác không cần.

Pod chạy với `hostNetwork: true` không đi qua GKE metadata server theo cách Workload Identity Federation for GKE dự kiến. Tránh bật host networking cho workload cần identity riêng, hoặc đánh giá kỹ cơ chế credential trước khi triển khai.

## 13.1. Dependency cho ví dụ Java SDK

Các đoạn code dưới đây cần thư viện SDK tương ứng. Dùng BOM do dự án hoặc Spring Cloud release train quản lý để giữ version tương thích; không tự trộn các version độc lập:

| Provider | Maven artifact | Mục đích |
|---|---|---|
| AWS | `software.amazon.awssdk:s3` | S3 client và AWS SDK credential provider chain |
| Azure | `com.azure:azure-identity` | ManagedIdentityCredential và WorkloadIdentityCredential |
| Google Cloud | `com.google.cloud:google-cloud-pubsub` | Pub/Sub Publisher và tích hợp ADC |

Các ví dụ Spring bean dùng chung một object cấu hình. Đăng ký record bằng ConfigurationPropertiesScan hoặc EnableConfigurationProperties:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.cloud")
public record CloudProperties(
        String region,
        String projectId,
        String topicName,
        String managedIdentityClientId) {
}
~~~

Ví dụ application.yml:

~~~yaml
app:
  cloud:
    region: ap-southeast-1
    project-id: PROJECT_ID
    topic-name: orders-events
    managed-identity-client-id:
~~~

Nếu dùng Spring Cloud AWS, Spring Cloud Azure hoặc Spring Cloud GCP starter, ưu tiên BOM tương ứng với phiên bản Spring Boot của dự án. Starter có thể auto-configure credential/client; chỉ tạo bean thủ công khi ứng dụng cần cấu hình riêng và đã kiểm tra không trùng auto-configuration.

## 14. Spring Boot và credential provider của AWS SDK for Java 2.x

AWS SDK for Java 2.x cung cấp DefaultCredentialsProvider. Provider chain tìm credential theo thứ tự, gồm system properties, environment variables, web identity token, shared profile, ECS container credentials và EC2 instance profile.

Điều này cho phép cùng một code chạy ở:
- EC2 với instance profile.
- ECS với task role.
- EKS IRSA với web identity token.
- EKS Pod Identity với container credential endpoint.
- Local development với profile dành cho developer.

Ví dụ Spring bean cho S3:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class AwsClientConfiguration {

    @Bean
    S3Client s3Client(CloudProperties properties) {
        return S3Client.builder()
                .region(Region.of(properties.region()))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }
}
~~~

Nếu không chỉ định credentialsProvider, AWS SDK cũng dùng default provider chain. Khai báo rõ giúp người đọc nhận biết ứng dụng dựa vào identity của runtime.

Lưu ý thứ tự chain: system properties và environment variables được kiểm tra trước web identity/container/instance profile. Nếu image hoặc Pod vô tình chứa AWS_ACCESS_KEY_ID và AWS_SECRET_ACCESS_KEY cũ, SDK có thể dùng chúng thay vì role được gắn cho workload. Production cần loại bỏ static credential environment variables và kiểm tra identity thực tế.

Không tạo StaticCredentialsProvider bằng access key nhúng trong code. Không mount file ~/.aws/credentials vào production Pod.

## 15. Spring Boot và Azure Identity

Azure SDK Java dùng TokenCredential. Với VM hoặc Azure-hosted service có Managed Identity, dùng ManagedIdentityCredential. Với AKS Workload ID, dùng WorkloadIdentityCredential. Local development có thể dùng DefaultAzureCredential để tìm credential từ Azure CLI hoặc IDE.

Ví dụ Managed Identity trên VM hoặc Container Apps:

~~~java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class AzureCredentialConfiguration {

    @Bean
    TokenCredential tokenCredential(CloudProperties properties) {
        var builder = new ManagedIdentityCredentialBuilder();

        if (properties.managedIdentityClientId() != null
                && !properties.managedIdentityClientId().isBlank()) {
            builder.clientId(properties.managedIdentityClientId());
        }

        return builder.build();
    }
}
~~~

Nếu VM chỉ có system-assigned identity, có thể bỏ client ID. Nếu gắn nhiều user-assigned identities, chỉ rõ client ID để chọn đúng principal.

Ví dụ local profile dùng DefaultAzureCredential:

~~~java
import com.azure.identity.DefaultAzureCredentialBuilder;

TokenCredential localCredential =
        new DefaultAzureCredentialBuilder().build();
~~~

Không để DefaultAzureCredential trong production vô tình fallback sang developer credential hoặc environment service principal nếu mục tiêu là Managed Identity. Với production, chọn credential cụ thể theo nền tảng để tránh lấy nhầm principal.

Với AKS, dùng WorkloadIdentityCredential như ví dụ ở phần 10. Spring Cloud Azure starter có thể tự cấu hình credential dựa trên môi trường và property của version đang dùng; kiểm tra đúng BOM/starter version trước khi thêm một TokenCredential bean thủ công để tránh tạo hai cấu hình cạnh tranh.

## 16. Spring Boot và Google Application Default Credentials

Google Cloud Java client libraries hỗ trợ ADC. Khi chạy trên Compute Engine, GKE có Workload Identity Federation hoặc Cloud Run, ADC lấy credential từ môi trường runtime. Code không cần đọc service account JSON key.

Trong local development, developer có thể thiết lập ADC bằng `gcloud auth application-default login`. Credential local đại diện cho developer hoặc service account được impersonate; không dùng file ADC của máy developer làm credential production.

Ví dụ Publisher cho Pub/Sub:

~~~java
import com.google.api.gax.core.FixedCredentialsProvider;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.pubsub.v1.Publisher;
import com.google.pubsub.v1.TopicName;
import java.io.IOException;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class GoogleCloudClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    Publisher ordersPublisher(CloudProperties properties)
            throws IOException {
        var credentials = GoogleCredentials.getApplicationDefault();

        return Publisher.newBuilder(
                    TopicName.of(
                        properties.projectId(),
                        properties.topicName()))
                .setCredentialsProvider(
                    FixedCredentialsProvider.create(credentials))
                .build();
    }
}
~~~

Trong nhiều Google client builders, ADC đã được dùng mặc định; đoạn code trên làm rõ credential source. Publisher cần đóng đúng lifecycle khi ứng dụng shutdown.

Không tải service account key JSON vào Kubernetes Secret để làm ADC trong production nếu có thể dùng Workload Identity Federation. Key file là credential dài hạn, khó rotation và có thể bị sao chép ra ngoài môi trường dự kiến.

## 17. Phân biệt Kubernetes RBAC với cloud IAM

Kubernetes RBAC và cloud IAM bảo vệ hai hệ thống khác nhau:

| Cơ chế | Kiểm soát | Ví dụ |
|---|---|---|
| Kubernetes RBAC | Quyền gọi Kubernetes API | Pod được đọc ConfigMap hoặc list Pod trong namespace |
| AWS IAM | Quyền gọi AWS API | Role được phép s3:GetObject |
| Azure RBAC | Quyền truy cập Azure resource/data plane | Managed Identity được phép nhận message Service Bus |
| Google Cloud IAM | Quyền gọi Google APIs và truy cập resource | Service account được phép pub/sub.publish |

Một Pod có quyền Kubernetes get pods không tự động có quyền đọc S3. Một IAM role có quyền đọc S3 cũng không tự động cho phép Pod đọc Secret hoặc Deployment trong Kubernetes API.

Tạo Kubernetes ServiceAccount riêng cho mỗi workload cần identity khác nhau. Không dùng default ServiceAccount cho toàn namespace nếu các workload có tập quyền khác nhau. Dùng namespace và subject cụ thể trong trust policy.

## 18. Bảo vệ metadata endpoint và token trong container

Credential ngắn hạn giảm rủi ro so với key dài hạn, nhưng metadata endpoint và projected token vẫn là tài sản nhạy cảm.

### 18.1. Metadata endpoint

- AWS EC2: yêu cầu IMDSv2, giới hạn hop limit và quyền instance role.
- Azure VM: IMDS token request yêu cầu header Metadata: true.
- Azure Container Apps: platform cấp IDENTITY_ENDPOINT và IDENTITY_HEADER; header này có tác dụng giảm SSRF.
- Google Cloud: metadata server cung cấp credential cho attached service account; request metadata cần header Metadata-Flavor: Google.
- Kubernetes: chỉ mount projected ServiceAccount token cho workload cần federation hoặc Kubernetes API.

Không để endpoint metadata đi qua proxy HTTP thông thường. Cấu hình proxy bypass cho link-local metadata address nếu SDK hoặc runtime cần truy cập. Chặn SSRF ở ứng dụng bằng URL allow-list, không cho user-controlled URL gọi metadata IP.

### 18.2. Token file trong Kubernetes

Projected ServiceAccount token có audience và thời hạn. Không copy token ra ConfigMap, log hoặc image. Không lưu token vào shared volume mà Pod khác có thể đọc. SDK credential provider cần hỗ trợ refresh khi token file được rotate.

Nếu workload không cần Kubernetes API và không cần federation, có thể tắt tự động mount ServiceAccount token. Nhưng nếu IRSA, AKS Workload ID hoặc GKE WIF cần projected token, phải giữ hoặc cấu hình volume projection phù hợp. Không đặt automountServiceAccountToken: false một cách máy móc rồi làm hỏng federation.

### 18.3. Tách quyền node và Pod

- Node role/service account chỉ cấp quyền cho kubelet, container runtime, logging agent hoặc thành phần node cần thiết.
- Pod role/identity cấp quyền nghiệp vụ cho ứng dụng.
- Không cho Pod dùng chung node identity làm fallback.
- Với Pod đặc biệt cần hostNetwork hoặc hostPath, review khả năng truy cập metadata và token.
- Dùng NetworkPolicy hoặc cơ chế cô lập tương ứng để hạn chế workload không tin cậy.

## 19. Least privilege và thiết kế role theo workload

Không nên tạo một identity dùng chung cho mọi microservice. Hãy thiết kế theo capability:

| Workload | Identity | Quyền ví dụ |
|---|---|---|
| orders-api | orders-api-runtime | Ghi event OrderCreated và đọc cấu hình cần thiết |
| orders-worker | orders-worker-runtime | Nhận message từ orders-processing |
| invoice-worker | invoice-worker-runtime | Đọc object hóa đơn và ghi kết quả |
| reporting-job | reporting-job-runtime | Chỉ đọc dữ liệu báo cáo |
| secret-rotation-job | secret-rotation-runtime | Cập nhật đúng secret được giao |

Các nguyên tắc:
- Một identity cho một service hoặc một nhóm workload có cùng trách nhiệm.
- Chỉ cấp action cần thiết, trên resource cụ thể.
- Tách quyền read, write, publish, consume và admin.
- Tách role provisioner khỏi role runtime.
- Không dùng wildcard resource nếu có thể giới hạn ARN/resource ID.
- Review quyền định kỳ dựa trên audit log và access analyzer.
- Xóa role assignment/association khi workload ngừng sử dụng identity.

Quyền quá rộng làm tăng blast radius khi container hoặc dependency bị xâm nhập. Identity riêng giúp thu hẹp phạm vi sự cố và dễ truy vết request.

## 20. Kiểm thử danh tính trong môi trường thực tế

Unit test có thể kiểm tra code wiring và cấu hình credential bean, nhưng không chứng minh role assignment trên cloud đúng. Cần integration test trong environment đã gắn workload identity.

| Kịch bản | Cách kiểm thử | Kết quả mong đợi |
|---|---|---|
| EC2 instance profile | Chạy app trên EC2 có role | SDK lấy temporary credentials |
| ECS task role | Gán taskRoleArn, bỏ static key | Container gọi đúng data-plane API |
| ECS execution role | Tách execution role khỏi task role | App không thừa hưởng quyền pull image/log |
| EKS IRSA | Gán OIDC trust và ServiceAccount annotation | Pod nhận role đúng |
| EKS Pod Identity | Tạo association và cài agent | Pod nhận credentials từ agent |
| Azure VM Managed Identity | Gắn identity và data-plane role | SDK lấy token và gọi resource |
| AKS Workload ID | FIC đúng issuer/subject/audience | Pod đổi token thành Entra token |
| GCP Compute Engine | Gắn service account vào VM | ADC lấy token |
| GKE WIF | Liên kết KSA với GSA hoặc IAM principal | Pod gọi API bằng identity riêng |
| Cloud Run service identity | Deploy với service account | Service truy cập đúng resource |
| Wrong audience | Dùng token với audience sai | Federation từ chối |
| Wrong subject/namespace | Dùng ServiceAccount ngoài trust policy | Không assume được role |
| Missing role | Xóa data-plane role trong test | API trả 403/permission denied |
| Token refresh | Chạy workload lâu hơn vòng đời access token | SDK tiếp tục gọi API sau refresh |
| Static key leakage | Thêm env credential giả trong test cô lập | Phát hiện provider chain chọn sai credential |

Dùng resource thử nghiệm và principal riêng cho test. Không thu hồi role, thay trust policy hoặc cố ý gây lỗi trên workload production.

## 21. Chẩn đoán lỗi authentication và authorization

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| AWS SDK Unable to load credentials | Không có role, web identity token hoặc credential provider phù hợp | Kiểm tra instance profile, task role, ServiceAccount association và SDK version |
| AWS AccessDenied | Role có credential nhưng policy thiếu action/resource | Kiểm tra trust policy, permission policy, boundary và resource policy |
| AWS dùng sai identity | Static env/system property đứng trước web identity trong provider chain | Gỡ static credential và xác minh principal |
| Azure CredentialUnavailableException | Managed Identity chưa bật hoặc Workload ID thiếu client/tenant/token file | Kiểm tra platform identity và biến môi trường |
| Azure 401 | Token audience/authority/tenant sai hoặc token hết hạn | Kiểm tra resource scope và credential configuration |
| Azure 403 | Entra token hợp lệ nhưng Azure RBAC/data-plane role thiếu | Gán đúng role ở đúng scope |
| AKS workload identity không hoạt động | OIDC issuer, FIC subject/audience hoặc Pod label sai | Đối chiếu issuer URL, namespace, ServiceAccount và label |
| GCP ADC không tìm thấy credential | VM/Cloud Run/GKE chưa có service identity | Gắn service account hoặc bật WIF |
| GCP 403 | Service account không có IAM role hoặc API chưa bật | Kiểm tra IAM binding và API enablement |
| GKE dùng quyền node | Pod không dùng KSA/WIF đúng hoặc metadata server chưa bật | Kiểm tra node pool, KSA và workload identity config |
| Token refresh thất bại | Token file không rotate, network/metadata endpoint lỗi | Kiểm tra projected volume, agent và metadata access |
| Local chạy được, production lỗi | Local developer credential che giấu cấu hình workload identity thiếu | Kiểm thử trong cùng loại runtime với production |

Phân biệt 401 và 403:
- 401 thường chỉ ra credential/token không hợp lệ hoặc không được chấp nhận.
- 403 thường chỉ ra principal đã được nhận diện nhưng thiếu quyền, hoặc policy từ chối.

Tuy nhiên, từng dịch vụ có thể biểu diễn lỗi khác nhau. Kiểm tra error code và audit log của provider thay vì chỉ dựa vào HTTP status.

## 22. Chuyển từ static credential sang workload identity

Nếu ứng dụng hiện dùng access key, client secret hoặc service account JSON key, có thể chuyển theo từng bước:

1. Xác định mọi service và resource mà credential hiện tại truy cập.
2. Tạo identity riêng cho từng workload.
3. Cấp role tối thiểu dựa trên API call thực tế.
4. Thiết lập trust/association và gắn identity vào runtime.
5. Cập nhật Spring Boot để dùng credential provider của SDK.
6. Deploy staging và kiểm tra data-plane operation.
7. Xác minh log/audit cho thấy principal mới được dùng.
8. Chuyển production theo rollout có thể rollback.
9. Thu hồi static credential cũ và xóa khỏi CI variables, secret mounts, image layers và repository history theo quy trình.
10. Theo dõi AccessDenied, token refresh và credential usage sau chuyển đổi.

Không xóa key cũ trước khi xác minh workload đã dùng identity mới. Nhưng cũng không để hai cơ chế tồn tại lâu dài mà không có thời hạn kết thúc, vì SDK có thể âm thầm chọn static credential cũ.

## 23. Checklist trước production

- **Identity:** Mỗi service có workload identity phù hợp.
- **Trust:** Trust policy/OIDC federation giới hạn đúng issuer, subject, audience, namespace và ServiceAccount.
- **Role:** Chỉ có data-plane permission cần thiết.
- **Node:** Node identity không mang quyền nghiệp vụ rộng.
- **Container:** ECS task role hoặc container app identity được cấu hình đúng.
- **Kubernetes:** Pod dùng ServiceAccount riêng, không dựa vào default identity.
- **AWS:** Phân biệt task role với execution role; kiểm tra IMDSv2 và EKS Pod Identity Agent/IRSA.
- **Azure:** Phân biệt system/user-assigned Managed Identity và AKS Workload ID; gán đúng data-plane role.
- **Google Cloud:** Dùng service account riêng cho VM/Cloud Run; bật GKE Workload Identity Federation.
- **SDK:** Dùng DefaultCredentialsProvider, ManagedIdentityCredential/WorkloadIdentityCredential hoặc ADC theo runtime.
- **Static keys:** Không có access key, client secret hoặc service account key trong JAR, image, manifest và log.
- **Metadata:** Bảo vệ IMDS/metadata endpoint khỏi SSRF và workload không tin cậy.
- **Token:** Token ngắn hạn được refresh; projected token không bị chia sẻ ngoài workload.
- **Testing:** Có positive và negative test cho trust, role, wrong subject/audience và token refresh.
- **Audit:** Có thể truy vết principal trong CloudTrail, Azure Activity/diagnostic logs hoặc Google Cloud audit logs.
- **Recovery:** Có quy trình thu hồi identity và role assignment khi workload bị xâm nhập hoặc ngừng hoạt động.

## 24. Tổng kết

Cấp danh tính cho ứng dụng là việc liên kết một workload cụ thể với principal cloud và giới hạn quyền của principal đó trên resource cần dùng. AWS sử dụng IAM role gắn vào EC2 instance profile, ECS task role hoặc Kubernetes ServiceAccount qua IRSA/EKS Pod Identity. Azure sử dụng system-assigned/user-assigned Managed Identity trên VM và container platform, hoặc Microsoft Entra Workload ID cho Pod AKS. Google Cloud sử dụng service account gắn vào Compute Engine/Cloud Run và Workload Identity Federation for GKE.

Spring Boot không cần lưu access key hoặc private key để thực hiện các thao tác cloud. AWS SDK credential chain, Azure Identity và Google ADC lấy credential ngắn hạn từ môi trường chạy rồi refresh theo vòng đời token. Khi trust relationship ràng buộc đúng workload, IAM/RBAC được giới hạn theo resource, metadata endpoint được bảo vệ và integration test xác minh principal thực tế, ứng dụng có thể truy cập dịch vụ managed với quyền tối thiểu trên VM, container và Kubernetes.

## Tài liệu tham khảo

- [AWS IAM roles for Amazon EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
- [AWS SDK for Java 2.x default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [Amazon ECS task IAM role and execution role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-role-overview.html)
- [IAM roles for service accounts in Amazon EKS](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html)
- [Create an IAM role with the trust policy required by EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-role.html)
- [Configure the EC2 Instance Metadata Service](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-options.html)
- [Managed identities for Azure virtual machines](https://learn.microsoft.com/en-us/entra/identity/managed-identities-azure-resources/how-managed-identities-work-vm)
- [Authenticate Azure-hosted Java apps with Managed Identity](https://learn.microsoft.com/en-us/azure/developer/java/sdk/identity-azure-hosted-auth)
- [Managed identities in Azure Container Apps](https://learn.microsoft.com/en-us/azure/container-apps/managed-identity)
- [Authenticate Azure-hosted Java apps with a user-assigned Managed Identity](https://learn.microsoft.com/en-us/azure/developer/java/sdk/authentication/user-assigned-managed-identity)
- [Microsoft Entra Workload ID on AKS](https://learn.microsoft.com/en-us/azure/aks/workload-identity-overview)
- [WorkloadIdentityCredentialBuilder for Azure Identity Java](https://learn.microsoft.com/en-us/java/api/com.azure.identity.workloadidentitycredentialbuilder?view=azure-java-stable)
- [Google Cloud service accounts for Compute Engine](https://docs.cloud.google.com/compute/docs/access/service-accounts)
- [Authenticate to Google Cloud APIs from GKE workloads](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/workload-identity)
- [Workload Identity Federation for GKE](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/workload-identity)
- [Configure service identity for Cloud Run](https://docs.cloud.google.com/run/docs/configuring/services/service-identity)
- [Authenticate with Google Cloud client libraries](https://docs.cloud.google.com/docs/authentication/client-libraries)
- [How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials)

