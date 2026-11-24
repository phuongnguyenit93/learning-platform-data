# Vai trò IAM cho EC2, ECS và EKS theo môi trường triển khai

## 1. Bối cảnh: cùng một ứng dụng, các cách cấp danh tính khác nhau

Một dịch vụ Spring Boot cần đọc object từ Amazon S3, gửi message tới Amazon SQS và lấy secret từ AWS Secrets Manager. Khi chạy trên máy phát triển, lập trình viên có thể dùng hồ sơ AWS CLI và IAM Identity Center. Khi triển khai lên **Amazon EC2**, **Amazon ECS** hoặc **Amazon EKS**, ứng dụng nên nhận **temporary AWS credentials thông qua IAM role dành cho workload**.

Đó là kiến thức trọng tâm của chương **Nền tảng AWS**, thuộc module **SPRING_CLOUD_PROVIDER_INTEGRATION**: học cách kết nối Spring Boot với dịch vụ managed trên AWS, Azure và Google Cloud, từ danh tính và quyền đến storage, messaging, dữ liệu, secret, kiểm thử và so sánh provider. Bài này đi sâu vào cách cấp quyền AWS đúng cho từng nền tảng chạy ứng dụng, từ đó giúp các bài thực hành Spring Cloud AWS sử dụng được IAM mà không cần nhúng access key vào source.

**Sau bài học, bạn có thể:**

- Giải thích IAM role, trust policy, permissions policy, role session và temporary credentials.
- Phân biệt **EC2 instance profile**, **ECS task role** với **task execution role**, và hai cơ chế danh tính Pod trên **EKS: IRSA và EKS Pod Identity**.
- Quyết định nên gán role ở cấp máy, task hay Kubernetes service account.
- Thiết kế quyền tối thiểu cho S3, SQS, Secrets Manager và KMS theo môi trường dev/test/prod.
- Xác minh ứng dụng Spring Boot/AWSpring đang sử dụng principal nào; xử lý lỗi `AccessDenied`, thiếu credential, cấu hình trust và credential bị ghi đè.
- Tổ chức kiểm thử và giám sát mà không lấy nhầm credential của tài khoản khác.

> **Phạm vi kỹ thuật:** Bài tập trung vào AWS SDK for Java **v2** và cách nó được Spring Cloud AWS của **AWSpring** sử dụng. Các ví dụ ARN, account ID, namespace, queue và bucket đều chỉ để minh họa; phải thay bằng tài nguyên đã provision và tài liệu tương thích của phiên bản dịch vụ đang dùng. Bài hướng dẫn mô hình và cấu hình, không tự tạo tài nguyên AWS.

## 2. Khái niệm cơ sở: IAM role cấp quyền bằng cách nào?

**IAM role** là một IAM identity có thể được một principal đủ điều kiện **assume** để nhận **temporary security credentials**. Không giống IAM user lưu access key dài hạn, role thường được sử dụng thông qua **STS role session** với credential có thời hạn.

Một IAM role có hai mặt cần phân biệt:

1. **Trust policy:** Ai/cái gì *được phép assume* role, bằng cơ chế nào, và dưới điều kiện nào?
2. **Permissions policy:** Sau khi assume role, session *được phép thực hiện operation nào* trên resource nào, với điều kiện gì?

Ngoài hai mặt đó, kết quả ủy quyền thực tế có thể còn chịu ảnh hưởng của **resource-based policy**, **service control policy (SCP)** ở AWS Organizations, **permissions boundary**, **session policy**, **KMS key policy** và các điều kiện truy cập khác. Một policy ghi `Allow` không bảo đảm request luôn thành công nếu có deny hoặc ràng buộc khác.

~~~mermaid
flowchart LR
    W["Workload Spring Boot"] --> CP["Nguồn credential theo nền tảng"]
    CP --> STS["Role session / temporary credentials"]
    T["Trust policy"] -. "Quy định ai được nhận role session" .-> STS
    STS --> SDK["AWS SDK for Java v2"]
    SDK --> API["S3 / SQS / Secrets Manager"]
    P["Role permissions policy"] -. "Quy định action và resource" .-> API
    R["Resource/KMS/SCP/condition"] -. "Có thể hạn chế thêm" .-> API
~~~

Ví dụ một role được trust bởi dịch vụ ECS nhưng chỉ có quyền `s3:GetObject` sẽ **không** tự gửi được message SQS. Ngược lại, một IAM role có policy `sqs:SendMessage` nhưng trust policy không cho đúng task/service account assume role thì workload không lấy được credential của role đó.

### 2.1. Role, profile, service account và instance profile khác nhau ra sao?

| Thuật ngữ | Thuộc hệ nào | Vai trò |
| --- | --- | --- |
| IAM role | AWS IAM | Principal được assume; permissions và trust được quản lý trong AWS |
| STS role session | AWS STS | Phiên dùng temporary AWS credentials của role |
| Instance profile | EC2/IAM | Cơ chế gắn IAM role vào EC2 instance để workload lấy credential qua IMDS |
| ECS task role | ECS/IAM | Role cung cấp credential cho mã chạy trong container của ECS task |
| ECS task execution role | ECS/IAM | Role dành cho ECS agent/nền tảng phục vụ khởi chạy task |
| Kubernetes service account | Kubernetes/EKS | Danh tính Kubernetes được dùng để liên kết Pod với quyền AWS qua IRSA hoặc Pod Identity |
| AWS CLI profile | Cấu hình trên máy | Chỉ định nguồn credential, account/role và region; không tự cấp IAM permission |

**Một role không phải một access key.** Workload nhận credential tạm từ cơ chế nền tảng/SDK. SDK ký request bằng credential đó và AWS kiểm tra quyền khi service nhận request.

## 3. Nguyên tắc thiết kế trước khi chọn EC2, ECS hay EKS

Một luồng triển khai an toàn cần trả lời năm câu hỏi:

1. **Workload nào cần gọi AWS?** Ví dụ `receipt-api` chỉ ghi biên nhận lên S3 và gửi event SQS; `receipt-worker` chỉ nhận event và đọc object.
2. **Chạy ở môi trường nào?** Dev, staging, production có account, role, ARN, region và dữ liệu khác nhau.
3. **Nền tảng cấp credential qua đâu?** EC2 instance profile, ECS task credentials, EKS web identity (IRSA) hoặc EKS Pod Identity.
4. **Operation nào cần thiết?** `s3:PutObject` khác `s3:ListBucket`; `sqs:SendMessage` khác `sqs:ReceiveMessage`.
5. **Điều gì cần kiểm chứng ở runtime?** Principal từ STS, region, endpoint, ARN tài nguyên, IAM/resource/KMS policies và hành vi retry/refresh.

Không gán quyền vào một role quá rộng chỉ vì nhiều service dùng chung cluster hoặc máy EC2. Càng nhiều workload chia sẻ role, phạm vi ảnh hưởng khi có lỗi hay lộ credential càng lớn. Với ECS, thường phân quyền **theo task definition/service**; với EKS, **theo service account**; với EC2, instance profile đại diện **cho cả instance**, cần xem lại mức cô lập khi nhiều ứng dụng cùng chạy.

### 3.1. So sánh nhanh cách cấp credential

| Nền tảng | Role nên dùng cho mã ứng dụng | Đường lấy credential | Phạm vi cần lưu ý |
| --- | --- | --- | --- |
| EC2 | IAM role gắn với **instance profile** | EC2 Instance Metadata Service (IMDS) | Các process có thể truy cập credential của instance đều có thể nhận quyền role |
| ECS trên EC2/Fargate | **Task role** | Endpoint credential riêng do ECS cấp cho task/container | Tách quyền theo task; bảo vệ ranh giới giữa task và host |
| EKS dùng IRSA | IAM role gắn với **Kubernetes service account** | Web identity token → AWS STS `AssumeRoleWithWebIdentity` | Trust policy ràng buộc cluster OIDC issuer, namespace và service account |
| EKS dùng Pod Identity | IAM role liên kết với **service account** qua EKS association | Pod Identity Agent/credential endpoint → EKS Auth | Agent, association, SDK hỗ trợ và quyền của node/agent phải phù hợp |

Không có “role Spring Boot” riêng: Spring Boot/AWSpring dùng các credentials được môi trường và AWS SDK cung cấp. Định nghĩa permission vẫn là công việc của AWS IAM và hạ tầng.

## 4. EC2: IAM role thông qua instance profile

### 4.1. Luồng credential

Khi một ứng dụng Spring Boot chạy trực tiếp trên EC2:

1. Quản trị viên tạo IAM role có **trust policy cho EC2**.
2. Role được đưa vào **instance profile** và gắn với EC2 instance.
3. EC2 metadata service cung cấp temporary credentials của instance role thông qua IMDS.
4. AWS SDK for Java v2 có thể lấy credentials thông qua `InstanceProfileCredentialsProvider` trong default credentials chain.
5. SDK ký request và service AWS kiểm tra quyền IAM/resource policy của role.

~~~mermaid
flowchart TD
    EC2["EC2 instance"] --> APP["Spring Boot process"]
    EC2 --> IP["Instance profile / IAM role"]
    IP --> IMDS["IMDS: temporary credentials"]
    APP --> SDK["AWS SDK v2"]
    SDK --> IMDS
    SDK --> S3["S3 / SQS / Secrets Manager"]
~~~

### 4.2. Trust policy mẫu cho EC2

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

Policy này xác định dịch vụ EC2 được assume role. Nó **không cấp** quyền `s3:PutObject` hoặc `sqs:SendMessage`; các quyền đó nằm ở permissions policy riêng.

**Instance profile là thành phần riêng**: trong triển khai hạ tầng, không chỉ tạo role mà còn phải có instance profile và association tương ứng. Nếu tạo role xong nhưng không gắn đúng instance profile, application trên instance có thể không nhìn thấy credential như kỳ vọng.

### 4.3. IMDS, IMDSv2 và rủi ro cô lập

IMDS cung cấp metadata và credential cho workload trên EC2. **IMDSv2** dùng token phiên khi truy cập metadata và là cơ chế nên được cấu hình theo chính sách bảo mật của tổ chức. Tuy nhiên, IMDSv2 **không biến mọi process trên cùng instance thành các principal độc lập**: nếu nhiều process có đường truy cập metadata/credential, chúng có thể dùng cùng instance role.

Các lưu ý:

- Gắn instance profile với quyền tối thiểu phù hợp toàn bộ workload trên instance.
- Không cho ứng dụng log nội dung credentials từ IMDS.
- Không mở proxy hay endpoint metadata ra mạng ngoài; kiểm soát SSRF, firewall và quyền của các process.
- Nếu chạy container trên EC2, chú ý việc container có thể truy cập IMDS của host nếu mạng không được cô lập thích hợp.
- Không giả định client sẽ luôn dùng instance role: environment credentials, system properties hoặc profile có thể được SDK ưu tiên trước IMDS.

**Khi nên cân nhắc mô hình khác:** nếu nhiều service có nhu cầu IAM khác nhau cùng chạy trên một máy, ECS task roles hoặc EKS Pod identities thường cho granularity rõ ràng hơn so với instance role dùng chung.

## 5. ECS: phân biệt task role và task execution role

Amazon ECS quản lý task/container chạy trên EC2 hoặc Fargate. Điểm dễ nhầm nhất là **hai role có mục đích khác nhau**.

| Loại role | Ai sử dụng chính? | Ví dụ quyền |
| --- | --- | --- |
| **Task role** (thuộc tính `taskRoleArn`) | Mã ứng dụng trong ECS task | `s3:GetObject`, `s3:PutObject`, `sqs:SendMessage`, `secretsmanager:GetSecretValue` |
| **Task execution role** (thuộc tính `executionRoleArn`) | ECS agent/nền tảng khởi chạy task | Kéo image từ ECR, gửi log tới CloudWatch Logs, lấy secret được tham chiếu lúc khởi chạy tùy cấu hình |

Một Spring Boot service dùng `S3Client` phải được cấp quyền S3 qua **task role**, không nên gán toàn bộ quyền S3 cho execution role rồi kỳ vọng mã chạy trong container tự kế thừa chúng.

### 5.1. Trust policy cho role của ECS task

Ví dụ trust policy tối thiểu minh họa service principal:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "ecs-tasks.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Khi triển khai thực tế, cân nhắc điều kiện `aws:SourceAccount` và `aws:SourceArn` thích hợp theo hướng dẫn ECS để giảm nguy cơ confused deputy. Cấu hình trust và permissions policy phải được đánh giá riêng, tránh mở rộng principal hoặc resource chỉ để vượt qua lỗi.

### 5.2. Hai ARN trong task definition

Một phần minh họa task definition:

~~~json
{
  "family": "receipt-api",
  "taskRoleArn": "arn:aws:iam::111122223333:role/receipt-api-task-dev",
  "executionRoleArn": "arn:aws:iam::111122223333:role/ecs-task-execution-dev",
  "containerDefinitions": [
    {
      "name": "receipt-api",
      "image": "111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/receipt-api:example",
      "essential": true,
      "memory": 512
    }
  ]
}
~~~

Đây là **trích đoạn minh họa**, không phải một task definition hoàn chỉnh cho mọi launch type/network mode. Một deployment ECS thực tế còn cần cấu hình CPU/memory, runtime, networking, logging, image tag và các trường bắt buộc theo launch type.

### 5.3. ECS cấp credential cho ứng dụng thế nào?

ECS cung cấp credential endpoint cho task. SDK v2 `ContainerCredentialsProvider` đọc thông tin endpoint phù hợp từ môi trường container, ví dụ biến `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` khi được ECS thiết lập, và lấy **temporary credentials của task role**. Khi gần hết hạn, provider được thiết kế để cập nhật credentials từ nền tảng thay vì yêu cầu application giữ static key.

Cần chú ý:

- Không tự ghi `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` vào task definition. Nguồn environment được thử **trước** container credentials trong `DefaultCredentialsProvider`, có thể dẫn tới dùng principal khác task role.
- Không nhầm secret từ Secrets Manager inject vào environment lúc task start với credential của task role: **task execution role** có thể đọc secret để inject theo cấu hình ECS; **application task role** cần quyền riêng nếu application trực tiếp gọi API Secrets Manager.
- Với ECS trên EC2, node/EC2 instance có thể có instance role dùng cho ECS agent; nó khác với task role. Cần kiểm soát việc container truy cập node metadata và thiết kế cô lập hợp lý.
- Nếu task không được gán task role, đừng ngầm dựa vào quyền của EC2 host; nhất là khi chuyển workload sang Fargate, giả định đó có thể hỏng.

### 5.4. Chia role theo workload

Nếu hệ thống có hai service:

- `receipt-api`: ghi biên nhận vào S3 và phát sự kiện SQS.
- `receipt-worker`: nhận message SQS và đọc biên nhận.

Nên có **hai task role khác nhau** để giới hạn IAM theo use case. Khi một service bị lỗi hoặc bị lộ credential, quyền không tự mở rộng sang hành vi của service còn lại.

## 6. EKS: IAM role cho Kubernetes workload

Amazon EKS chạy Kubernetes; các workload thường được tổ chức theo namespace, Deployment, Pod và **ServiceAccount**. Kubernetes service account **không tự là AWS IAM role**. Cần cơ chế nối danh tính Kubernetes với quyền AWS.

Hai mô hình phổ biến:

1. **IAM Roles for Service Accounts (IRSA):** Kubernetes service account được liên kết đến IAM role; Pod nhận projected web identity token; SDK dùng STS `AssumeRoleWithWebIdentity`.
2. **EKS Pod Identity:** EKS quản lý association giữa service account và IAM role; Pod Identity Agent cung cấp credential endpoint để SDK lấy temporary credentials thông qua cơ chế EKS Auth.

Không bật đồng thời nhiều cơ chế cho cùng ứng dụng mà không xác định rõ precedence và đường credential thực tế. Cũng không cấp toàn bộ quyền ứng dụng cho node IAM role vì Pod có thể bị chuyển node và quyền không được phân tách.

### 6.1. EKS IRSA: OIDC trust gắn với service account

Mô hình IRSA:

~~~mermaid
flowchart TD
    SA["Kubernetes ServiceAccount: payments/receipt-api"] --> POD["Pod dùng serviceAccountName"]
    OIDC["EKS OIDC issuer + IAM OIDC provider"] --> JWT["Projected web identity token"]
    POD --> JWT
    JWT --> STS["STS AssumeRoleWithWebIdentity"]
    ROLE["IAM role trust policy: sub + aud"] --> STS
    STS --> TEMP["Temporary role credentials"]
    TEMP --> SDK["AWS SDK v2 WebIdentityTokenFileCredentialsProvider"]
    SDK --> SQS["S3 / SQS / Secrets Manager"]
~~~

Để triển khai IRSA đúng cần:

1. Xác định OIDC issuer của EKS cluster; đăng ký OIDC identity provider tương ứng trong IAM.
2. Tạo IAM role có trust policy giới hạn **OIDC provider, namespace và service account cụ thể**.
3. Gắn permissions policy tối thiểu cho role.
4. Annotate đúng Kubernetes ServiceAccount với ARN role.
5. Bảo đảm Pod dùng đúng `serviceAccountName`; kiểm tra token projection/SDK runtime và STS dependency nếu cần.
6. Xác minh principal trong Pod bằng STS và thử đúng action/resource.

#### Trust policy IRSA minh họa

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE:aud": "sts.amazonaws.com",
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLE:sub": "system:serviceaccount:payments:receipt-api"
        }
      }
    }
  ]
}
~~~

`111122223333` và `EXAMPLE` là placeholder minh họa. Điều kiện `sub` đang buộc đúng **namespace `payments` và service account `receipt-api`**. Tránh dùng wildcard kiểu cho phép mọi service account trong cluster khi chỉ một workload cần quyền.

#### ServiceAccount và Deployment minh họa

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: receipt-api
  namespace: payments
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::111122223333:role/receipt-api-irsa-dev
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: receipt-api
  namespace: payments
spec:
  replicas: 1
  selector:
    matchLabels:
      app: receipt-api
  template:
    metadata:
      labels:
        app: receipt-api
    spec:
      serviceAccountName: receipt-api
      containers:
        - name: app
          image: 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/receipt-api:example
~~~

Đây là cấu trúc Kubernetes rút gọn; khi triển khai thực tế còn cần yêu cầu bảo mật, tài nguyên, readiness, logging và cấu hình image thích hợp. Các giá trị account/role chỉ để minh họa.

Với IRSA, cơ chế EKS webhook thường cấu hình `AWS_ROLE_ARN` và `AWS_WEB_IDENTITY_TOKEN_FILE` cho container, để `WebIdentityTokenFileCredentialsProvider` của SDK v2 lấy role credentials. **Cần SDK v2 và các module STS hỗ trợ phù hợp**. Nếu environment chứa static credentials, default chain có thể chọn environment trước web identity và bỏ qua role đã annotate.

### 6.2. EKS Pod Identity: association và Pod Identity Agent

EKS Pod Identity dùng **association** được quản lý qua EKS để liên kết namespace/service account với IAM role. Trong mô hình này, service account không cần dùng annotation IRSA để chỉ tới role. Một **Pod Identity Agent** tương thích trên cluster/node cung cấp đường lấy credential cho SDK trong Pod.

Trust policy minh họa cho role Pod Identity:

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
      ]
    }
  ]
}
~~~

Ví dụ tạo association bằng AWS CLI, khi IAM role, cluster, namespace và service account đã tồn tại:

~~~bash
aws eks create-pod-identity-association \
  --cluster-name training-eks \
  --namespace payments \
  --service-account receipt-api \
  --role-arn arn:aws:iam::111122223333:role/receipt-api-pod-dev \
  --region ap-southeast-1
~~~

Lệnh trên là **lệnh minh họa có tác động tới AWS**; không chạy trên tài khoản thật khi chưa được phép. Cần kiểm tra quyền của người cấu hình association, trust policy, trạng thái Pod Identity Agent và việc Pod được khởi động lại khi cấu hình danh tính thay đổi. Tính khả dụng và điều kiện hỗ trợ của Pod Identity phụ thuộc loại node, phiên bản cluster/add-on và cấu hình nền tảng.

Với EKS Pod Identity, SDK thường sử dụng đường **container credential provider** qua các biến endpoint/token do nền tảng cung cấp. Nó **khác** đường web identity/STS trực tiếp của IRSA. Nếu Pod không lấy được credentials, kiểm tra:

- Pod Identity association chính xác với cluster, namespace và service account.
- Agent đã được cài và hoạt động trên node phù hợp.
- Node/agent có quyền gọi EKS Auth API cần thiết.
- IAM role trust cho principal `pods.eks.amazonaws.com` cùng những action cần thiết.
- SDK/runtime hỗ trợ container credential endpoint và không bị nguồn credential ưu tiên cao hơn ghi đè.

### 6.3. IRSA và Pod Identity: chọn theo tình huống

| Tiêu chí | IRSA | EKS Pod Identity |
| --- | --- | --- |
| Liên kết role | Annotation trên Kubernetes service account + IAM OIDC trust | EKS Pod Identity association với service account |
| Principal tin cậy | Federated OIDC provider của cluster | `pods.eks.amazonaws.com` |
| Credential path | Token file → SDK STS web identity | Pod Identity Agent/endpoint → EKS Auth |
| SDK provider thường dùng | `WebIdentityTokenFileCredentialsProvider` | `ContainerCredentialsProvider` |
| Thành phần cần quản lý | IAM OIDC provider, trust claim `sub`/`aud`, token projection | Pod Identity association, agent, trust role và quyền EKS Auth |
| Phạm vi triển khai | Cần xem hỗ trợ workload, OIDC, phiên bản SDK | Cần xem hỗ trợ node/agent/cluster và SDK theo môi trường |

Không khẳng định cơ chế nào luôn “an toàn hơn” hay “nhanh hơn” trong mọi trường hợp. Cả hai cần permissions policy tối thiểu, trust đúng, cấu hình workload identity rõ ràng và kiểm chứng quyền trên resource.

### 6.4. Không dùng node role cho toàn bộ Pod

EKS node (ví dụ EC2 managed node group) có IAM role phục vụ node/kubelet và những tác vụ nền tảng. Nếu Pod có thể truy cập IMDS của node và SDK không lấy được web identity/Pod Identity, có nguy cơ ứng dụng dùng credential của **node role** ngoài ý muốn. Hãy kiểm soát truy cập metadata của node và sử dụng Pod role phù hợp; đừng cấp quyền rộng cho node role để mọi Pod sử dụng chung.

**Kubernetes RBAC không phải AWS IAM.** Một ServiceAccount được Kubernetes cho phép đọc ConfigMap không có nghĩa nó được AWS cho phép đọc S3. Cần thiết kế cả hai lớp quyền theo đúng hành vi của workload.

## 7. Permissions policy thực hành: S3 và SQS

Giả sử `receipt-api` cần:

- Ghi object vào bucket `example-dev-receipts`, chỉ trong prefix `receipts/`.
- Gửi message vào queue `receipt-events-dev` ở `ap-southeast-1`, tài khoản `111122223333`.

Một **identity-based permissions policy** minh họa:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "WriteReceiptObjects",
      "Effect": "Allow",
      "Action": ["s3:PutObject"],
      "Resource": "arn:aws:s3:::example-dev-receipts/receipts/*"
    },
    {
      "Sid": "PublishReceiptEvents",
      "Effect": "Allow",
      "Action": ["sqs:SendMessage"],
      "Resource": "arn:aws:sqs:ap-southeast-1:111122223333:receipt-events-dev"
    }
  ]
}
~~~

Đây là quyền ứng dụng minh họa. Phần hạ tầng phải tạo bucket/queue thật, kiểm tra chính sách mặc định và mã hóa. Nếu S3 dùng **SSE-KMS**, application có thể cần quyền KMS liên quan trên đúng KMS key, ví dụ `kms:GenerateDataKey` và tùy thao tác `kms:Decrypt`. Nếu SQS/Secrets Manager được mã hóa bằng customer-managed key, cần xét quyền KMS và key policy riêng. Không cấp `kms:*` trên mọi key để xử lý lỗi tạm thời.

**Lưu ý về ARN:**

- `s3:PutObject` thường áp trên **object ARN**, ví dụ `arn:aws:s3:::bucket/prefix/*`.
- `s3:ListBucket` áp trên **bucket ARN**, ví dụ `arn:aws:s3:::bucket`, và nếu cần hạn chế prefix thì phải xét condition phù hợp.
- SQS action áp trên **queue ARN**, chứa region và account ID.
- Secret Manager action nên giới hạn đúng secret ARN/nhóm secret theo quy ước.

### 7.1. Role cho producer khác role cho consumer

Một consumer đọc queue `receipt-events-dev` và truy xuất biên nhận S3 có quyền khác:

| Workload | Các operation cần đánh giá | Rủi ro khi cấp quá rộng |
| --- | --- | --- |
| `receipt-api` | `s3:PutObject`, `sqs:SendMessage` | Có thể ghi/xóa ngoài phạm vi nghiệp vụ nếu cấp `s3:*` hoặc `sqs:*` |
| `receipt-worker` | `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes`, có thể `sqs:ChangeMessageVisibility`; `s3:GetObject` | Có thể đọc mọi object hoặc thao tác queue khác nếu role dùng chung |
| Spring Boot lấy secret lúc runtime | `secretsmanager:GetSecretValue` cho secret cần thiết; quyền KMS thích hợp | Lộ secret của ứng dụng khác nếu dùng wildcard rộng |

Các quyền chính xác phụ thuộc API/SDK và listener container thực tế. Ví dụ khi SQS listener dùng thao tác lấy queue URL hoặc thay đổi visibility, cần xác minh action tương ứng, không chỉ `ReceiveMessage`. Cần cấp những quyền thật sự có sử dụng, rồi kiểm thử đường đi end-to-end.

## 8. Phân tách role theo dev, staging và production

Cùng một image Spring Boot có thể được deploy vào nhiều môi trường, nhưng **identity và resource phải tách theo môi trường**.

| Môi trường | Cách cấp danh tính thường gặp | Tài nguyên đích | Guardrail |
| --- | --- | --- | --- |
| Laptop | AWS CLI profile + IAM Identity Center của account sandbox | Bucket/queue/secret dev | Temporary credential, MFA, account allowlist |
| CI integration test | OIDC/STS role của account test hoặc emulator | Tài nguyên test hoặc LocalStack | Chặn gọi production; scope account/role |
| EC2 dev | Instance profile role dev | ARN dev | Hạn chế tài nguyên và IMDS |
| ECS staging | Task role riêng của service staging | ARN staging | Không dùng execution role thay application role |
| EKS staging | IRSA/Pod Identity role riêng theo service account | ARN staging | Trust chặt namespace/service account, kiểm tra Pod principal |
| Production | Role workload production theo nguyên tắc least privilege | ARN production | Quy trình deploy, audit, permissions boundary/SCP phù hợp |

Nếu công ty sử dụng nhiều AWS account, cần xác định account ID dự kiến cho từng môi trường. **Vai trò đúng ở sai account vẫn có thể tạo hậu quả không mong muốn** nếu policy hoặc cross-account trust cho phép thao tác.

### 8.1. Cross-account access

Một service trong account A có thể cần đọc S3 object ở account B. Lúc đó cần thiết kế rõ:

- Role và trust policy giữa các account, hoặc resource-based policy cho phép đúng principal trong account A theo mô hình dịch vụ.
- Quyền gọi `sts:AssumeRole` ở phía gọi và trust cho role đích nếu dùng assume role.
- Resource/KMS policies ở account B.
- Region/endpoint của tài nguyên; token session duration và quyền thật sự sau assume role.

Không tự cho SDK dùng một IAM role khác chỉ vì nhận HTTP 403; ứng dụng phải có cơ chế cross-account được cấu hình có chủ đích. Việc gộp quyền tất cả account vào một role mặc định làm tăng nguy cơ vượt phạm vi truy cập.

### 8.2. Tách quyền triển khai và quyền runtime

Quyền tạo/cập nhật IAM role, gán instance profile, cập nhật ECS task definition, tạo EKS association hoặc sửa Kubernetes ServiceAccount là quyền **triển khai/hạ tầng**. Chúng không nên tự động có trong **application runtime role**.

Ví dụ:

- Pipeline/CD có thể cần quyền cập nhật ECS service và truyền role cho task theo phạm vi kiểm soát (`iam:PassRole` nếu operation yêu cầu).
- `receipt-api` khi chạy chỉ cần quyền ghi S3 và gửi SQS.
- ECS execution role cần quyền hỗ trợ khởi chạy task, riêng với task role.
- Kubernetes deployment controller có quyền thích hợp để tạo Pod, nhưng application Pod chỉ nên có IAM role với quyền nghiệp vụ.

## 9. Spring Cloud AWS và AWS SDK nhận role như thế nào?

Trong AWS SDK for Java v2, `DefaultCredentialsProvider` kiểm tra các nguồn credential theo thứ tự thường gặp:

1. Java system properties chứa access key/secret key.
2. Environment variables chứa access key/secret key.
3. Web identity token/role ARN (hữu ích với IRSA).
4. Shared AWS profile.
5. Container credentials (ECS task role, EKS Pod Identity khi cấu hình phù hợp).
6. EC2 instance profile thông qua IMDS.

Role của nền tảng **không tự thắng mọi nguồn**. Nếu Docker image hoặc JVM arguments có static access key, SDK có thể sử dụng chúng thay vì role đã gắn cho task/Pod/instance. Vì vậy, trên AWS nên bỏ các credential static không cần thiết khỏi runtime và để mặc định tự nhận temporary credentials từ môi trường.

### 9.1. Cấu hình Spring Boot đơn giản

Với AWSpring và các starter cần thiết, ứng dụng có thể dùng region và resource name qua cấu hình:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION}

app:
  aws:
    receipt-bucket: ${APP_RECEIPT_BUCKET}
    event-queue: ${APP_EVENT_QUEUE}
~~~

Đoạn này **không chứa access key**. Khi chạy trên EC2/ECS/EKS, AWS SDK dùng credential provider chain hoặc cấu hình bean Spring Cloud AWS tương ứng. `AWS_REGION`, tên bucket/queue phải được cấp trong môi trường chạy; không phải biến tự xuất hiện ở mọi môi trường.

### 9.2. Dùng SDK client do Spring quản lý

~~~java
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;

@Service
public class ReceiptMetadataService {
    private final S3Client s3Client;

    public ReceiptMetadataService(S3Client s3Client) {
        this.s3Client = s3Client;
    }

    public long sizeOf(String bucket, String key) {
        return s3Client.headObject(request -> request
                .bucket(bucket)
                .key(key))
            .contentLength();
    }
}
~~~

Khi tích hợp đúng starter hoặc bean configuration, `S3Client` có thể được inject từ Spring. Với Spring Cloud AWS, cần kiểm tra phiên bản, starter và điều kiện auto-configuration cụ thể. **AWSpring không cấp IAM permission**; nó chỉ giúp khởi tạo bean/client và tích hợp cơ chế Spring với SDK.

### 9.3. Khi tự tạo AWS SDK client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class AwsClients {
    @Bean
    S3Client s3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

Ở ví dụ này, nếu không đặt `credentialsProvider(...)`, SDK vẫn có thể sử dụng default credential chain; region lại đã được cấu hình tường minh. Khi ứng dụng deploy qua nhiều vùng, nên đưa region vào cấu hình môi trường hoặc quản lý client theo từng region thay vì ghi cứng trong mã chung.

Nếu tự khai báo bean `AwsCredentialsProvider`/client theo cơ chế AWSpring, hãy xem nó có override chain mặc định không. Việc tạo `StaticCredentialsProvider` chứa key trong source cho production có thể làm mất cơ chế cấp/refresh temporary credentials từ role.

### 9.4. Refresh credential

Credentials từ EC2 instance profile, ECS task role, IRSA và Pod Identity thường có **thời hạn**. Các provider mặc định của SDK được thiết kế để cập nhật credential phù hợp với từng nguồn khi cần. Không gọi `resolveCredentials()` một lần rồi chuyển kết quả vào `StaticCredentialsProvider` cho vòng đời application dài; ứng dụng có thể gặp `ExpiredToken`.

Nếu ứng dụng tự assume role qua STS, cần sử dụng credential provider có cơ chế refresh phù hợp và đóng tài nguyên đúng cách.

## 10. Xác minh role thực tế và xử lý lỗi

### 10.1. Dùng STS GetCallerIdentity

Một cách xác minh principal của **client đang chạy** là gọi STS:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;

public class CurrentAwsIdentity {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            var identity = sts.getCallerIdentity();
            System.out.println("Account: " + identity.account());
            System.out.println("Principal: " + identity.arn());
        }
    }
}
~~~

Ví dụ cần SDK module `software.amazon.awssdk:sts`. STS client ở đây dùng default credentials nếu không bị cấu hình khác override. Nếu service S3/SQS dùng custom provider, STS client kiểm tra **default chain** chưa chắc phản ánh cùng principal: cần cấu hình STS bằng **cùng provider thực tế** hoặc quan sát thông tin request/CloudTrail theo quy trình an toàn.

`GetCallerIdentity` cho biết account/ARN của principal, **không xác thực được quyền cụ thể** trên S3 hoặc SQS, và cũng không chỉ rõ provider con nào trong default chain đã được chọn. ARN/account ID có thể là thông tin nội bộ; hạn chế in ra log công khai.

### 10.2. Bảng chẩn đoán theo tầng

| Hiện tượng | Khả năng cần kiểm tra | Cách xác minh |
| --- | --- | --- |
| Không tìm được credentials | Role/instance profile chưa gắn; ECS task role thiếu; IRSA token hoặc Pod Identity agent/association lỗi | Kiểm tra nền tảng và provider chain; xác minh endpoint/token một cách an toàn |
| ECS startup lấy image thất bại | Execution role thiếu quyền ECR/log/secret lúc khởi chạy | Kiểm tra task execution role và sự kiện ECS |
| ECS app gọi S3 403 | Task role không đủ quyền hoặc credential bị override | STS principal từ app, IAM/resource/KMS policy |
| EKS IRSA `AccessDenied` khi assume role | OIDC provider, trust `sub`/`aud` hoặc service account sai | So sánh issuer/namespace/SA, trust policy và token projection |
| EKS Pod Identity không lấy credential | Agent/association/trust role/EKS Auth access hoặc SDK không phù hợp | Kiểm tra association, agent, runtime environment |
| EC2 không nhận instance credentials | Instance profile/IMDS bị tắt hoặc metadata không truy cập được | Kiểm tra association, IMDSv2, host/network |
| Chạy app dưới role sai | Java system property/environment key/profile đang ưu tiên trước workload provider | Kiểm tra cấu hình process; xác nhận STS principal thực tế |
| `ExpiredToken` | Credential tạm bị cache cứng hoặc provider không refresh | Kiểm tra SDK provider/session/token lifecycle |
| `NoSuchKey` hoặc `QueueDoesNotExist` | Resource/region/queue URL/key sai | Đối chiếu ARN, region, endpoint và cấu hình ứng dụng |

**Phân biệt lỗi lấy credential và lỗi IAM:**

- **Chưa lấy được credentials:** SDK không có dữ liệu để ký request, thường lỗi provider/STS/metadata.
- **Lấy được credential nhưng bị từ chối:** Request đến AWS nhưng IAM/resource/SCP/KMS hoặc condition từ chối.
- **Sai region/endpoint:** Request có thể được ký hợp lệ bằng role đúng nhưng vẫn không tới resource mong muốn.
- **Sai role:** Có credential hoạt động, nhưng thuộc principal/account khác ý định, thường vì precedence hoặc cấu hình hạ tầng.

Không khắc phục `AccessDenied` bằng cách thêm `AdministratorAccess` cho role khi chưa xác định action/resource/condition bị thiếu.

### 10.3. CloudTrail và dấu vết kiểm toán

CloudTrail có thể giúp liên kết request với principal và role session. Khi phân tích sự cố, xem event source, action, thời gian, region, principal/session identity, resource và error code, trong phạm vi logging đã cấu hình. CloudTrail không phải nhật ký có sẵn mọi chi tiết cho tất cả data events: với S3 object-level data events, cần bật cấu hình event tương ứng nếu muốn quan sát.

Khi EKS Pod Identity dùng session tagging, tag phiên có thể hỗ trợ phân biệt thông tin workload theo khả năng của cơ chế và cấu hình thực tế. Không biến tag thành bằng chứng duy nhất nếu không kiểm tra trust và IAM policy.

## 11. Kiểm thử quyền theo từng môi trường

Viết unit test cho logic nghiệp vụ **không cần** có quyền AWS thật. Với local integration test, có thể dùng LocalStack hoặc emulator cùng static **test credentials giả**, endpoint override và region test. Nhưng chỉ smoke test trên môi trường AWS thật mới xác nhận được IAM role, trust, metadata/agent, KMS và resource policy thực tế.

| Mức kiểm thử | Kiểm chứng chính | Điều không thể kết luận |
| --- | --- | --- |
| Unit test với fake/mock adapter | Service gọi đúng nghiệp vụ và ánh xạ lỗi | Identity, IAM, mạng và endpoint AWS |
| Local integration với LocalStack | Wiring Spring/AWS SDK, serialization, S3/SQS cơ bản | Phần lớn trust policy, IMDS/IRSA/Pod Identity và toàn bộ semantics AWS |
| Smoke test AWS dev/staging | Role thực tế, region, ARN, IAM/resource/KMS, gọi request thật | Mọi lỗi tải lớn và mọi tình huống vận hành |
| Kiểm thử lỗi và quan sát | Retry, message trùng, token refresh, báo động AccessDenied | Tính đúng đắn của toàn bộ production nếu chỉ thử một kịch bản |

### 11.1. Mô phỏng lỗi cấp credential

Các tình huống đáng thử:

- ECS service chạy bằng task role đúng, nhưng tạo một môi trường test có override credential ưu tiên cao; xác nhận hệ thống phát hiện account/role sai.
- EKS Pod dùng service account không có IRSA annotation hoặc association, xác nhận ứng dụng **không âm thầm lấy node role** ngoài ý muốn.
- EC2 instance profile không gắn hoặc metadata không truy cập được; xác nhận startup hoặc health check báo lỗi rõ.
- Credential tạm thay đổi theo thời gian; chạy tác vụ dài và bảo đảm provider refresh hợp lệ.
- Có quyền S3 nhưng thiếu quyền KMS; xác nhận log phân biệt nguyên nhân và không mở rộng IAM tùy tiện.

Các bài thử lỗi này phải được thực hiện trên môi trường kiểm thử cách ly, không tháo role đang phục vụ production.

### 11.2. Smoke test role và tài nguyên đích

Trên dev/staging, chạy từ **chính workload**:

1. Xác minh account/role ARN thực tế qua STS (cùng credential source).
2. Xác nhận region và ARN tài nguyên đúng với môi trường.
3. Thực hiện thao tác nhỏ có kiểm soát, ví dụ `PutObject` vào prefix test, `SendMessage` lên queue test.
4. Kiểm tra lỗi IAM/KMS/network và kết quả nghiệp vụ.
5. Dọn tài nguyên test theo quyền/scope được cấp và xác nhận không có side effect vào production.

Tránh chạy smoke test bằng credentials của máy developer rồi kết luận role ECS/EKS đã đúng; khi đó bạn đang kiểm tra **hai principal khác nhau**.

## 12. Những lỗi thiết kế thường gặp

### 12.1. Gán mọi quyền lên EC2 instance role

Mô hình này đơn giản ban đầu nhưng làm nhiều process có thể chia sẻ quyền. Khi cần cô lập service, xem xét tách instance/role hoặc chuyển sang ECS task roles hay EKS workload identities; đồng thời kiểm soát đường truy cập IMDS.

### 12.2. Gán quyền ứng dụng vào ECS execution role

Execution role có thể cho ECS agent kéo image nhưng ứng dụng không tự dùng role đó để gọi S3/SQS. Hãy đặt quyền ứng dụng lên `taskRoleArn` và kiểm tra STS principal từ container.

### 12.3. Gán quyền nghiệp vụ cho EKS node role

EKS node role phục vụ node. Nếu mọi Pod dựa vào nó, các service có thể vượt phạm vi lẫn nhau. Dùng IRSA hoặc Pod Identity với service account và trust chính xác, kiểm soát truy cập node IMDS.

### 12.4. Mở trust policy quá rộng

IRSA với điều kiện `sub` chấp nhận mọi namespace hoặc Pod Identity role không giới hạn association phù hợp làm tăng phạm vi giả mạo/sử dụng. Hãy thu hẹp đúng workload và kết hợp IAM/resource policy. Với ECS/EC2, chỉ dùng principal dịch vụ và condition thích hợp; không đặt mọi principal có quyền assume role.

### 12.5. Lưu access key vào application.yml

Tạo static IAM user key để “fix” ECS/EKS credential khiến application bỏ qua workload identity, khó xoay vòng và dễ rò rỉ. Cách xử lý đúng là tìm lỗi role/trust/metadata/agent, sau đó để SDK provider chain hoạt động.

### 12.6. Đồng nhất region, account và role

Role có thể thuộc account đúng nhưng S3 bucket ở region khác; queue URL hoặc secret ARN có thể trỏ account/region khác. Quyền IAM, endpoint và cấu hình tài nguyên cần kiểm tra **riêng**.

## 13. Tình huống thực hành tổng hợp

**Đề bài:** Hệ thống Spring Boot có hai ứng dụng:

- `receipt-api` nhận file từ người dùng, lưu vào `s3://example-dev-receipts/receipts/` và gửi event lên queue `receipt-events-dev`.
- `receipt-worker` nhận message, tải file về để xử lý và đánh dấu kết quả trong một kho dữ liệu riêng.

Nhóm hiện chạy local với AWS CLI profile, dự định triển khai lên EC2 dev, ECS staging và EKS production. Mỗi môi trường có account và resource riêng, Java ứng dụng sử dụng Spring Cloud AWS và AWS SDK v2.

### Nhiệm vụ A — Chọn role theo nền tảng

1. Với **EC2 dev**, vẽ quan hệ `IAM role → instance profile → EC2 → IMDS → SDK client`. Giải thích rủi ro khi API và worker cùng instance.
2. Với **ECS staging**, định nghĩa `taskRoleArn` riêng cho API và worker, `executionRoleArn` phù hợp cho ECS agent. Nêu quyền ứng dụng thuộc role nào.
3. Với **EKS production**, chọn IRSA hoặc Pod Identity dựa vào hỗ trợ của cluster/agent. Định nghĩa namespace và service account riêng cho mỗi ứng dụng, trust tương ứng và phạm vi quyền.
4. Với **local**, dùng IAM Identity Center profile sandbox. Không nhúng access key vào cấu hình Spring.

### Nhiệm vụ B — Thiết kế quyền tối thiểu

Điền bảng quyền:

| Workload | S3 | SQS | Secrets Manager/KMS |
| --- | --- | --- | --- |
| `receipt-api` | Ghi đúng prefix `receipts/*` | `SendMessage` lên queue đích | Chỉ đọc secret/KMS cần thật sự sử dụng |
| `receipt-worker` | Đọc đúng prefix/object phục vụ xử lý | Receive/Delete/GetQueueAttributes/ChangeMessageVisibility nếu dùng | Chỉ đọc secret/KMS cần thật sự sử dụng |

Đối chiếu chính sách thực tế và quyền của từng SDK operation. Không dùng wildcard `Action:"*"` hoặc `Resource:"*"` theo thói quen.

### Nhiệm vụ C — Debug sự cố

1. ECS API báo 403 khi `PutObject`, nhưng role `ecs-task-execution-dev` đã có quyền S3. Vì sao vẫn lỗi?
2. EKS Pod IRSA được annotate nhưng STS báo assume role thất bại. Cần đối chiếu những điều kiện `sub`, `aud`, OIDC provider và service account nào?
3. Pod Identity role đúng nhưng Pod báo không tìm credentials. Kiểm tra association, agent, node/EKS Auth và provider precedence thế nào?
4. EC2 role có đủ quyền SQS nhưng application chạy với access key khác từ environment. Phân tích thứ tự provider chain và hậu quả.
5. Production role đúng account nhưng SQS URL trỏ staging. Tại sao phải kiểm tra cả region, queue ARN và policy?

### Nhiệm vụ D — Kế hoạch kiểm thử

Thiết kế một bộ:

- Unit test cho adapter S3/SQS.
- LocalStack integration test với credential giả và endpoint test.
- Smoke test trên từng nền tảng bằng role thực sự, kèm `GetCallerIdentity`, xác nhận account/region và operation tối thiểu.
- Test token refresh, lỗi IAM và sự kiện retry/duplicate của SQS.
- Giám sát bằng log an toàn, metric và CloudTrail nơi có cấu hình phù hợp.

**Tiêu chí đánh giá:** Sơ đồ phải cho thấy đúng **principal ứng dụng** của từng nền tảng, role/trust/permissions policy tách bạch, resource ARN giới hạn theo môi trường, và có kiểm chứng **chính role đang được workload sử dụng** thay vì chỉ dựa vào profile/tên role trong tài liệu.

## 14. So sánh khái niệm với Azure và Google Cloud

Mục tiêu đa cloud của module yêu cầu hiểu nguyên tắc chung: workload nên dùng **managed/workload identity** để lấy credential ngắn hạn, rồi áp quyền tối thiểu lên resource. Nhưng mỗi provider có cách cấp identity và phân quyền riêng.

| Nhu cầu | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Workload trên VM | EC2 instance profile IAM role | Managed Identity cho VM | Service account gắn với Compute Engine VM |
| Container/orchestrator | ECS task role; EKS IRSA/Pod Identity | Managed Identity / workload identity cho môi trường container/AKS | Workload Identity Federation for GKE |
| SDK credential mặc định | `DefaultCredentialsProvider` | Chuỗi credential như `DefaultAzureCredential` | Application Default Credentials (ADC) |
| Phân quyền tài nguyên | IAM identity/resource policies, KMS/SCP theo trường hợp | Azure RBAC và chính sách dịch vụ | IAM roles/bindings, điều kiện và chính sách dịch vụ |

Bảng chỉ so sánh khái niệm, **không** đồng nhất permission syntax hay credential chain giữa các cloud. Chẳng hạn Kubernetes ServiceAccount trên EKS không thể tự dùng cấu hình IAM của GKE. Khi triển khai ứng dụng Spring Boot đa cloud, hãy tách nghiệp vụ khỏi adapter và cấu hình identity riêng cho từng provider.

## 15. Ghi nhớ

Với **EC2**, role của ứng dụng đi qua **instance profile** và IMDS, thường có mức cô lập ở cấp instance. Với **ECS**, mã ứng dụng dùng **task role**, còn **task execution role** phục vụ hạ tầng khởi chạy. Với **EKS**, ứng dụng nên có identity theo **Kubernetes service account**, qua **IRSA** (OIDC/web identity/STS) hoặc **Pod Identity** (association/agent/EKS Auth) tùy nền tảng.

Cả ba trường hợp đều dùng **temporary credentials** và IAM permissions thực sự. Spring Cloud AWS cùng AWS SDK Java v2 hỗ trợ lấy và sử dụng credential, nhưng không thay thế việc thiết kế trust policy, least privilege, resource/KMS policy, region, tài nguyên và kiểm thử. Chọn role đúng cho từng workload và môi trường là bước nền tảng trước khi tích hợp S3, SQS, secret, database hoặc so sánh cách làm tương tự trên Azure và Google Cloud.
