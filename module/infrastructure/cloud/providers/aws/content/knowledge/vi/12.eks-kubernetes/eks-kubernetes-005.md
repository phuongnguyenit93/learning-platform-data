# IAM Roles for Service Accounts và EKS Pod Identity

Một ứng dụng Java/Spring Boot chạy trong **Amazon Elastic Kubernetes Service (Amazon EKS)** có thể cần đọc object từ Amazon S3, lấy secret từ AWS Secrets Manager, cập nhật DynamoDB hoặc truy vấn CloudWatch. Những request đó phải được ký bằng **AWS credentials** hợp lệ và chịu kiểm tra **IAM permissions**. Nếu nhúng access key dài hạn vào Docker image, Kubernetes Secret hoặc source code, credentials dễ bị rò rỉ và khó xoay vòng; nếu mọi Pod sử dụng IAM role rộng của EC2 worker node, một Pod bị xâm nhập có thể làm lộ quyền của cả node.

Hai cơ chế EKS giải quyết bài toán danh tính cho workload là **IAM Roles for Service Accounts (IRSA)** và **EKS Pod Identity**. Cả hai gắn **Kubernetes ServiceAccount** với một **AWS IAM role** để ứng dụng nhận **temporary security credentials** mà không phải phân phối khóa tĩnh. Chúng khác nhau về luồng lấy credentials, IAM trust policy, điều kiện triển khai và khả năng quản trị đa cluster.

Đây là chủ đề của chương **Kubernetes với EKS** trong mô-đun **CLOUD_PROVIDERS_AWS**. Kiến thức liên hệ IAM, AWS STS, VPC, EC2/Fargate, EKS networking, S3, RDS, DynamoDB, serverless, CloudTrail, tính sẵn sàng, khả năng phục hồi và kiểm soát chi phí khi thiết kế ứng dụng trên AWS.

> **Nguyên tắc chính:** Kubernetes ServiceAccount là danh tính **trong cluster**; IAM role là danh tính **trên AWS**. IRSA và Pod Identity nối hai lớp danh tính, nhưng **không thay thế Kubernetes RBAC, IAM least privilege, Pod Security hoặc kiểm soát đường mạng**.

## 1. Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt Kubernetes ServiceAccount, Kubernetes RBAC, IAM role, role trust policy và role permissions policy.
2. Mô tả chính xác luồng **IRSA → projected OIDC token → STS AssumeRoleWithWebIdentity**.
3. Mô tả **EKS Pod Identity association → agent → EKS Auth AssumeRoleForPodIdentity → temporary credentials**.
4. Cấu hình hoặc đọc ví dụ IAM policy, ServiceAccount, Deployment và association cho hai cơ chế.
5. So sánh những trường hợp dùng EKS Linux EC2 nodes, EKS Auto Mode và Fargate; nhận biết các giới hạn Windows/Outposts.
6. Biết cách chọn AWS SDK Java v2 và default credential chain, kiểm tra **role đang được sử dụng thật**.
7. Giải thích Pod Identity cross-account qua **target role** và role chaining.
8. Thiết kế IAM least privilege, Kubernetes RBAC, bảo vệ IMDS, VPC endpoints, giám sát và xử lý lỗi.
9. Lập kế hoạch chuyển IRSA sang Pod Identity với rollout/rollback an toàn.
10. Chẩn đoán lỗi `AccessDenied`, sai OIDC issuer, SDK không hỗ trợ, agent không có network, sai namespace hoặc ServiceAccount.

## 2. Kubernetes ServiceAccount khác IAM role thế nào?

Giả sử một workload có danh tính Kubernetes:

~~~text
Cluster:        shop-cluster
Namespace:      shop
ServiceAccount: orders-api
Subject:        system:serviceaccount:shop:orders-api
~~~

Một Pod khai báo `spec.serviceAccountName: orders-api` để dùng ServiceAccount trong namespace `shop`. Kubernetes API server nhận diện ServiceAccount qua Kubernetes token và áp dụng **Kubernetes RBAC**. Nhưng AWS S3 API không chấp nhận “service account name” như một IAM principal. Để gọi S3, AWS SDK cần bộ credentials của một **IAM role session**.

| Thành phần | Phạm vi | Ví dụ quyền |
|---|---|---|
| **ServiceAccount** | Kubernetes cluster + namespace | Danh tính Pod khi truy cập Kubernetes API |
| **Kubernetes RBAC** | Kubernetes API resources | `get pods`, `list configmaps` |
| **IAM role trust policy** | Ai có quyền assume role | OIDC issuer và `sub/aud` hoặc service principal `pods.eks.amazonaws.com` |
| **IAM permissions policy** | Quyền sử dụng AWS APIs | `s3:GetObject` trên prefix; `dynamodb:GetItem` trên table |
| **Resource-based policy / guardrails** | Điều kiện bổ sung trên AWS resources | S3 bucket policy, KMS key policy, SCP, permissions boundary |
| **VPC/network policy** | Đường kết nối thực tế | Endpoint STS/EKS Auth/S3, DNS, Security Group, routing |

Một Pod có **IAM role hợp lệ nhưng không có đường tới S3 endpoint** sẽ timeout. Một Pod **có đường mạng hợp lệ nhưng không có `s3:GetObject`** sẽ bị từ chối. Vì vậy chẩn đoán cần tách **authentication**, **authorization** và **networking**.

### 2.1. Vì sao không dùng IAM role của worker node?

EC2 worker node có IAM instance profile phục vụ kubelet, EKS networking và các tác vụ quản lý node. Nếu container truy cập được **EC2 Instance Metadata Service (IMDS)**, nó có thể lấy node credentials, thường rộng hơn nhu cầu của ứng dụng. Cả IRSA và Pod Identity giảm nhu cầu dùng node IAM role cho workload, nhưng **không tự khóa IMDS** hoặc biến container thành ranh giới bảo mật tuyệt đối.

Cần quản lý IMDSv2, hop limit/network access phù hợp; hạn chế quyền node role, Pod Security, privileged/hostNetwork/hostPath và Kubernetes RBAC. Không trao `AdministratorAccess` cho node role chỉ vì một Pod cần đọc một file S3.

## 3. Hai luồng cấp credentials

~~~mermaid
flowchart TD
    P["Pod + Kubernetes ServiceAccount"] --> X{"Cơ chế identity"}
    X -->|"IRSA"| O["Projected OIDC web identity token"]
    O --> W["AWS SDK WebIdentity provider"]
    W --> STS["STS AssumeRoleWithWebIdentity"]
    X -->|"EKS Pod Identity"| A["EKS association + projected Pod Identity token"]
    A --> C["AWS SDK Container credentials provider"]
    C --> G["EKS Pod Identity Agent trên node"]
    G --> AUTH["EKS Auth AssumeRoleForPodIdentity"]
    AUTH --> STS2["AWS-managed STS role session"]
    STS --> T["Temporary AWS credentials"]
    STS2 --> T
    T --> S["S3 / DynamoDB / Secrets Manager"]
~~~

**Điểm giống:** Cả hai cuối cùng cho Pod sử dụng temporary credentials gồm access key ID, secret access key, session token và expiration. Chúng phải được giữ kín, làm mới tự động và sử dụng với IAM least privilege.

**Điểm khác:**

- **IRSA:** SDK chạy trong Pod lấy projected web identity token và gọi trực tiếp **AWS STS `AssumeRoleWithWebIdentity`**.
- **Pod Identity:** SDK chạy trong Pod gọi **local credentials endpoint của agent trên node**; agent gọi **EKS Auth `AssumeRoleForPodIdentity`** và nhận credentials thay mặt Pod.

## 4. Bảng so sánh lựa chọn IRSA và Pod Identity

| Tiêu chí | IRSA | EKS Pod Identity |
|---|---|---|
| Danh tính Pod | Kubernetes ServiceAccount | Kubernetes ServiceAccount |
| Ánh xạ role | Annotation `eks.amazonaws.com/role-arn` | **EKS Pod Identity association** |
| IAM trust principal | **Federated OIDC provider** theo cluster | **`pods.eks.amazonaws.com`** |
| STS operation | `AssumeRoleWithWebIdentity` | EKS Auth lấy role credentials bằng `AssumeRoleForPodIdentity` |
| OIDC provider trong IAM | Cần tạo cho cluster issuer | **Không cần** cho Pod Identity |
| Agent | Không dùng Pod Identity Agent | Cần trên Linux EC2 nodes; sẵn có trong Auto Mode |
| SDK provider | Web identity token credentials | Container credentials |
| Tái dùng role nhiều clusters | Trust phải quản lý issuer từng cluster | Trust dùng service principal chung; association theo cluster |
| Fargate Pods | **Có hỗ trợ IRSA** | **Không hỗ trợ** |
| EKS Linux EC2 worker nodes | Có | Có khi đáp ứng prerequisites |
| EKS Auto Mode | Cần kiểm tra cấu hình tương ứng | Có, cơ chế agent đã tích hợp |
| Cross-account | OIDC federation và/hoặc role chaining | Association có thể dùng **`--target-role-arn`** để role-chain |
| Java SDK | Cần hỗ trợ web identity | SDK Java v2 **≥ 2.21.30** theo tài liệu EKS |
| Quản trị nhiều SA | Quản lý annotation và OIDC trusts | Quản lý association qua EKS API |
| Phù hợp | Môi trường đang dùng IRSA, workload Fargate | Workload mới trên node type được hỗ trợ |

Với workload mới trên node hỗ trợ, **EKS Pod Identity** thường là lựa chọn thuận tiện vì không phải quản lý IAM OIDC provider trên từng cluster. **IRSA vẫn được AWS hỗ trợ**, đặc biệt với Fargate hoặc hệ thống đã chuẩn hóa OIDC. Trước khi chọn, cần kiểm tra AWS Region, EKS cluster platform version, SDK và loại compute đang sử dụng.

## 5. IRSA: OIDC issuer, projected token và trust

### 5.1. Cluster OIDC issuer

Mỗi EKS cluster có OIDC issuer URL dạng:

~~~text
https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID
~~~

Đây là **issuer minh họa**. Trong thực tế, phải dùng URL được `aws eks describe-cluster` trả về. IAM cần có **OIDC identity provider** tương ứng với URL này. Vì issuer mang định danh cluster, xóa rồi tạo cluster mới cùng tên có thể khiến IAM provider/trust cũ không còn khớp.

Projected ServiceAccount JWT có các claims quan trọng:

~~~json
{
  "iss": "https://oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID",
  "aud": ["sts.amazonaws.com"],
  "sub": "system:serviceaccount:shop:orders-api"
}
~~~

Đây là **payload giản lược để minh họa**, không phải JWT thực/đầy đủ. `iss` là issuer; `aud` ràng buộc token cho AWS STS; `sub` chỉ rõ namespace và ServiceAccount. OIDC provider/JWKS phục vụ xác minh chữ ký và token lifetime. Không sao chép token vào ticket, logs hoặc git.

### 5.2. IAM trust policy cho IRSA

Ví dụ cluster ở account `111122223333`, ServiceAccount `shop/orders-api`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustOrdersServiceAccount",
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::111122223333:oidc-provider/oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID:aud": "sts.amazonaws.com",
          "oidc.eks.ap-southeast-1.amazonaws.com/id/EXAMPLEOIDCID:sub": "system:serviceaccount:shop:orders-api"
        }
      }
    }
  ]
}
~~~

**Điều bắt buộc:** Thay account và OIDC issuer bằng giá trị thật. Trong trust, `Principal.Federated` là IAM OIDC provider ARN; các condition keys **không có `https://`** và phải đúng issuer path. Đừng mở rộng `sub` thành wildcard mọi namespace/SA chỉ để loại bỏ `AccessDenied`. Một ServiceAccount quyền cao bị dùng sai là lỗ hổng IAM nghiêm trọng.

### 5.3. Permissions policy của IAM role

Ứng dụng `orders-api` chỉ cần đọc file cấu hình tại S3:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOrdersConfiguration",
      "Effect": "Allow",
      "Action": "s3:GetObject",
      "Resource": "arn:aws:s3:::orders-config-demo/app/*"
    }
  ]
}
~~~

`s3:GetObject` sử dụng **object ARN**. Nếu muốn liệt kê bucket phải cấp thêm `s3:ListBucket` trên **bucket ARN** với condition prefix khi cần. Object mã hóa SSE-KMS có thể cần `kms:Decrypt` và key policy phù hợp. IAM role trust và permissions policy thực hiện hai chức năng khác nhau: **ai được nhận role** và **role được phép làm gì**.

## 6. IRSA: ServiceAccount và Deployment YAML

### 6.1. Annotation `role-arn`

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: shop
  annotations:
    eks.amazonaws.com/role-arn: arn:aws:iam::111122223333:role/OrdersReadOnlyIrsaRole
~~~

Namespace `shop` phải có từ trước và IAM role ARN phải là role thật với OIDC trust đã khớp `sub`. Annotation giúp EKS Pod Identity Webhook cho IRSA inject thông tin cần thiết vào Pod mới.

### 6.2. Deployment chọn ServiceAccount

~~~yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: orders-api
  namespace: shop
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
        - name: app
          image: 111122223333.dkr.ecr.ap-southeast-1.amazonaws.com/shop/orders-api:1.0.0
          ports:
            - containerPort: 8080
~~~

**Lưu ý:** Manifest là ví dụ rút gọn; deployment production còn cần image digest, resource requests/limits, readiness/liveness probes, SecurityContext, Pod security và quy trình rollout. Nếu thiếu `serviceAccountName`, Pod có thể dùng ServiceAccount mặc định thay vì `orders-api`.

### 6.3. Credentials provider trong Pod IRSA

Khi tạo Pod mới, EKS thường inject:

~~~text
AWS_ROLE_ARN=arn:aws:iam::111122223333:role/OrdersReadOnlyIrsaRole
AWS_WEB_IDENTITY_TOKEN_FILE=/var/run/secrets/eks.amazonaws.com/serviceaccount/token
~~~

AWS SDK nhận projected token và gọi `STS AssumeRoleWithWebIdentity`. Cần **network path đến STS endpoint**, ví dụ qua private STS VPC endpoint hoặc NAT phù hợp. Với private workloads, ưu tiên **regional STS endpoint**, để SDK không truy cập nhầm global endpoint không được kết nối riêng.

### 6.4. Quy trình triển khai IRSA

1. Kiểm tra EKS cluster issuer.
2. Tạo IAM OIDC provider đúng issuer nếu cluster chưa có.
3. Tạo IAM role với trust policy `sub/aud` và permissions policy tối thiểu.
4. Gắn annotation `eks.amazonaws.com/role-arn` lên ServiceAccount.
5. Cho deployment tham chiếu đúng ServiceAccount.
6. Tạo Pod mới/rollout theo quy trình để nhận token/env vars.
7. Kiểm tra `STS GetCallerIdentity` và AWS API cần thiết ở trong Pod.

Ví dụ lệnh **có tác động tới cluster**, chỉ chạy ở lab có quyền và file YAML đã được duyệt:

~~~bash
kubectl apply -f irsa-service-account.yaml
kubectl rollout restart deployment/orders-api -n shop
~~~

Tạo OIDC provider/role và chạy `kubectl apply` là hoạt động thay đổi hạ tầng thực, không thuộc lab chỉ đọc trong bài này.

## 7. EKS Pod Identity: association, agent và EKS Auth

EKS Pod Identity được cấu hình qua **EKS association** thay vì annotation IRSA. Một association kết nối:

~~~text
Cluster:        shop-cluster
Namespace:      shop
ServiceAccount: orders-api
IAM role:       arn:aws:iam::111122223333:role/OrdersReadOnlyPodRole
~~~

AWS tạo một ánh xạ do EKS quản lý. Khi Pod mới sử dụng ServiceAccount có association, EKS inject môi trường/container credential setup vào Pod; AWS SDK giao tiếp với Pod Identity Agent của node.

### 7.1. Luồng credentials

~~~mermaid
sequenceDiagram
    participant P as Pod / AWS SDK
    participant A as Pod Identity Agent
    participant E as EKS Auth API
    participant T as AWS STS
    participant S as AWS service
    P->>A: Local credential endpoint + Pod Identity token
    A->>E: AssumeRoleForPodIdentity
    E->>T: EKS-managed assume role
    T-->>E: Temporary credentials
    E-->>A: Temporary credentials
    A-->>P: Credentials để SDK cache/refresh
    P->>S: Request có chữ ký IAM role session
    S-->>P: Kết quả theo permissions policy
~~~

**Chú ý:** Pod Identity không bắt SDK trực tiếp gọi `AssumeRoleWithWebIdentity`; đây là điểm khác biệt cơ bản so với IRSA.

### 7.2. Các biến môi trường được inject

Pod Identity tạo những giá trị kiểu:

~~~text
AWS_CONTAINER_CREDENTIALS_FULL_URI=http://169.254.170.23/v1/credentials
AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE=/var/run/secrets/pods.eks.amazonaws.com/serviceaccount/eks-pod-identity-token
~~~

Token Pod Identity có audience `pods.eks.amazonaws.com`; token này dùng để agent xác thực Pod. Không nhầm token này với **IRSA OIDC token audience `sts.amazonaws.com`**.

Agent sử dụng IPv4 link-local `169.254.170.23`, và IPv6 local `fd00:ec2::23` khi được cấu hình. Nếu node tắt IPv6, agent có thể cần tắt IPv6 listener theo hướng dẫn AWS. Với HTTP proxy, thêm địa chỉ local vào `NO_PROXY`/`no_proxy`; không để token/credentials bị gửi qua proxy doanh nghiệp.

### 7.3. Điều kiện hỗ trợ

- EKS cluster/platform version hỗ trợ Pod Identity.
- Pod chạy trên **Linux EC2 worker node** được hỗ trợ, hoặc môi trường **EKS Auto Mode** tích hợp cơ chế agent.
- Với EC2 worker nodes, **EKS Pod Identity Agent** phải chạy khỏe (thường là EKS add-on `eks-pod-identity-agent`/DaemonSet).
- **Node IAM role** cho agent có quyền `eks-auth:AssumeRoleForPodIdentity`. AWS-managed `AmazonEKSWorkerNodePolicy` đã chứa quyền này; node policy tùy chỉnh cần thêm phù hợp.
- Node có network path tới **EKS Auth API** qua Internet/NAT hoặc private interface endpoint.
- SDK trong container hỗ trợ Pod Identity và không bị credentials source khác ưu tiên.

**EKS Fargate Pods không được hỗ trợ bởi EKS Pod Identity**. Không cố cài DaemonSet agent lên Fargate để “sửa”, hãy chọn IRSA. Pod Identity cũng không hỗ trợ Windows EC2 nodes, EKS Anywhere hoặc local clusters trên Outposts theo giới hạn AWS.

### 7.4. EKS Auto Mode

Ở **EKS Auto Mode**, tính năng EKS Pod Identity Agent đã tích hợp; **không cần tự tạo add-on agent**. Hãy kiểm tra cluster/node mode, SDK và association. Việc không thấy một DaemonSet `eks-pod-identity-agent` khi Auto Mode đang dùng không đủ để kết luận thiếu Pod Identity.

## 8. IAM trust policy của Pod Identity khác IRSA

Với EKS Pod Identity, IAM role tin **service principal** của EKS:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowOrdersPodIdentity",
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
          "aws:RequestTag/kubernetes-namespace": "shop",
          "aws:RequestTag/kubernetes-service-account": "orders-api"
        }
      }
    }
  ]
}
~~~

- `sts:AssumeRole` cho phép EKS Pod Identity dùng IAM role.
- `sts:TagSession` cho phép EKS gắn session tags nhận diện nguồn workload.
- Condition kiểm tra **namespace và ServiceAccount** của phiên. Có thể siết thêm cluster ARN/name hoặc condition như `aws:SourceOrgId` nếu phù hợp với AWS Organizations và tài liệu IAM.
- Role vẫn phải gắn **permissions policy** cho S3/DynamoDB/API như ở mục 5.3.

**Khác biệt với IRSA:** không có `Principal.Federated` và không có OIDC `sub/aud` conditions. Role có thể tái sử dụng giữa nhiều EKS clusters mà không cần thêm một issuer mới vào trust cho mỗi cluster; dù vậy, khi tái sử dụng cần kiểm soát trust conditions, session tags và blast radius.

### 8.1. Session tags và ABAC

Pod Identity có các session tags được AWS cấp mặc định, ví dụ:

| Session tag | Nội dung |
|---|---|
| `eks-cluster-arn` | ARN cluster |
| `eks-cluster-name` | Tên cluster |
| `kubernetes-namespace` | Namespace của Pod |
| `kubernetes-service-account` | ServiceAccount |
| `kubernetes-pod-name` | Tên Pod |
| `kubernetes-pod-uid` | UID của Pod |

IAM có thể dùng các tags này trong **ABAC (Attribute-Based Access Control)** để giới hạn resource. Nhưng không để principals khác tùy ý gán tags bắt chước `kubernetes-*`/`eks-*`, vì họ có thể vượt ranh giới đã thiết kế. Session tags + inline policies có giới hạn packed size; `PackedPolicyTooLarge` cần được xử lý bằng thu gọn chính sách hoặc thay đổi cấu hình tags theo hướng dẫn.

### 8.2. Session policy cho association

EKS Pod Identity association API hiện có thể nhận **session policy** để thu hẹp quyền áp dụng cho Pod ngoài role permissions. Session policy **không nâng quyền** vượt IAM role và cần kết hợp các resource-based policies/guardrails. Đây là tùy chọn nâng cao, không cần thiết cho ví dụ một role riêng `OrdersReadOnlyPodRole`.

## 9. Tạo Pod Identity association bằng Console/CLI

### 9.1. Cài agent cho cluster EC2 node

Trên EKS Console, chọn cluster → Add-ons → **EKS Pod Identity Agent**. Hoặc dùng CLI (lệnh **thay đổi cluster thật**):

~~~bash
aws eks create-addon \
  --cluster-name shop-cluster \
  --addon-name eks-pod-identity-agent \
  --profile dev \
  --region ap-southeast-1
~~~

Trước khi chạy, kiểm tra add-on đã tồn tại, node role, Region, cluster platform version và EKS Auth networking. Không cần cài add-on trên EKS Auto Mode.

### 9.2. ServiceAccount cho Pod Identity

~~~yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: orders-api
  namespace: shop
~~~

ServiceAccount này **không cần** annotation `eks.amazonaws.com/role-arn` như IRSA. Deployment vẫn dùng `serviceAccountName: orders-api`.

### 9.3. Tạo association qua EKS API

~~~bash
# CÓ TÁC ĐỘNG: chỉ chạy khi role/cluster đã được phê duyệt
aws eks create-pod-identity-association \
  --cluster-name shop-cluster \
  --namespace shop \
  --service-account orders-api \
  --role-arn arn:aws:iam::111122223333:role/OrdersReadOnlyPodRole \
  --profile dev \
  --region ap-southeast-1
~~~

Role chính `--role-arn` phải thuộc **AWS account của EKS cluster**, do yêu cầu IAM PassRole. Principal quản lý association cần `eks:CreatePodIdentityAssociation` và quyền **`iam:PassRole` trên đúng role** theo chính sách. Đừng cấp PassRole cho mọi role quyền cao.

Association có **eventual consistency**: một vài giây sau khi API trả thành công, cấu hình có thể chưa áp dụng ở mọi thành phần. Đừng tạo/update association trong đường xử lý request nóng của ứng dụng. Tạo Pod mới/rollout sau khi association đã sẵn sàng để nhận env vars và projected token đúng.

### 9.4. Đọc trạng thái association và agent

~~~bash
aws eks list-pod-identity-associations \
  --cluster-name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws eks list-addons \
  --cluster-name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --output json

kubectl get serviceaccount orders-api -n shop -o yaml

kubectl get daemonset eks-pod-identity-agent -n kube-system -o wide
~~~

Lệnh cuối phù hợp với cluster **chạy agent DaemonSet**. Trên Auto Mode, agent được tích hợp và có thể không hiện ra dưới dạng DaemonSet đó. Với association ID thật, dùng `aws eks describe-pod-identity-association --cluster-name ... --association-id ...` để đọc chi tiết.

## 10. Cross-account IAM: IRSA và Pod Identity

Giả sử cluster EKS ở account **A `111122223333`**, nhưng dữ liệu DynamoDB/S3 ở account **B `444455556666`**.

### 10.1. IRSA cross-account

Có hai kiểu:

1. Role IAM tại account B trust OIDC issuer của EKS cluster A, sau khi B cấu hình IAM OIDC provider phù hợp, và token `sub/aud` thỏa trust. Pod nhận credentials role B qua `AssumeRoleWithWebIdentity`; hoặc
2. Pod nhận IAM role IRSA tại A, sau đó **`AssumeRole`** sang target role B qua credentials provider và policy/trust hai account.

Cần kiểm tra quyền IAM cho bên gọi, trust của target role, SCP/permissions boundaries và bucket/KMS policies. Không giả định chỉ vì hai account cùng Organization thì được phép assume nhau.

### 10.2. Pod Identity cross-account và `target-role-arn`

Theo EKS API hiện hành, Pod Identity association có thể chỉ định **target IAM role** bằng `--target-role-arn`. EKS tự quản lý việc **role chaining**:

~~~mermaid
flowchart LR
    P["Pod shop/orders-api tại account A"] --> E["EKS Pod Identity association"]
    E --> S["Role nguồn tại A"]
    S -->|"sts:AssumeRole"| T["Target role tại B"]
    T --> D["S3 / DynamoDB tài khoản B"]
~~~

Lệnh **có tác động** (chỉ mang tính minh họa):

~~~bash
aws eks create-pod-identity-association \
  --cluster-name shop-cluster \
  --namespace shop \
  --service-account orders-api \
  --role-arn arn:aws:iam::111122223333:role/OrdersPodIdentitySourceRole \
  --target-role-arn arn:aws:iam::444455556666:role/SharedDataReadRole \
  --profile dev \
  --region ap-southeast-1
~~~

Điều kiện thiết kế:

- Source role `OrdersPodIdentitySourceRole` thuộc **account của cluster**, trust `pods.eks.amazonaws.com`, có `sts:AssumeRole` hướng đến target role.
- Target role `SharedDataReadRole` thuộc B và **trust source role A**; quyền target role chỉ cho actions/resources cần thiết.
- Nếu dùng session tags ở bước role chaining, cần xử lý `sts:TagSession`, conditions và guardrails phù hợp.
- Role chaining chịu giới hạn **session duration tối đa một giờ** ở bước assume tiếp theo và các ràng buộc refresh/quota.
- Thêm resource policies/KMS permissions cho tài nguyên B khi cần.

Trước khi ứng dụng production dùng tính năng này, kiểm tra AWS CLI/EKS API version hỗ trợ `--target-role-arn`. **Không kết luận Pod Identity không hỗ trợ cross-account** chỉ vì các tài liệu cũ mô tả phải tự viết assume role trong code.

## 11. Giới hạn nền tảng, quotas và lựa chọn

### 11.1. Hỗ trợ theo loại Pod

| Môi trường thực thi | IRSA | Pod Identity |
|---|---|---|
| Linux EC2 managed/self-managed nodes | Hỗ trợ | Hỗ trợ nếu agent và versions phù hợp |
| EKS Auto Mode | Xem cấu hình/workload cụ thể | Hỗ trợ, có agent tích hợp |
| EKS Fargate | **Hỗ trợ** | **Không hỗ trợ** |
| Windows EC2 worker nodes | Cần đánh giá tính tương thích riêng | **Không hỗ trợ** |
| EKS Anywhere | Không dùng trực tiếp cơ chế EKS-managed OIDC giống IRSA | Không hỗ trợ |
| EKS local clusters trên Outposts | Không hỗ trợ IRSA theo hạn chế AWS | Không hỗ trợ Pod Identity |

**Fargate pod execution role** là role dùng bởi Fargate runtime để chuẩn bị Pod (chẳng hạn kéo image). Nó **không tự trở thành IAM role của ứng dụng**. Với ứng dụng muốn đọc S3 trong EKS Fargate, dùng **IRSA** theo cấu hình hỗ trợ.

### 11.2. Quota và versions

- EKS hiện hỗ trợ tối đa **5.000 Pod Identity associations mỗi cluster** theo giới hạn dịch vụ công bố. Kiểm tra giới hạn/quota thực tế trước khi triển khai cực lớn.
- Một cặp namespace/ServiceAccount trong một cluster có **một association role chính**.
- Với **AWS SDK for Java 2.x**, version hỗ trợ EKS Pod Identity tối thiểu theo AWS là **2.21.30**; dùng version mới hơn có hỗ trợ bảo mật phù hợp.
- EKS cluster/platform và add-on versions phải hỗ trợ Pod Identity; không tự suy ra các Kubernetes versions cũ/Outposts hoạt động.
- Lệnh association có eventual consistency; Pod đang chạy không nhất thiết được cập nhật cùng thời điểm.

## 12. AWS SDK for Java v2: không hardcode access key

### 12.1. Kiểm tra identity bằng STS

Code chỉ sử dụng default credentials provider chain:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

public class CallerIdentity {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            GetCallerIdentityResponse result = sts.getCallerIdentity();
            System.out.println("Account: " + result.account());
            System.out.println("Principal: " + result.arn());
        }
    }
}
~~~

Cần dependency `software.amazon.awssdk:sts` và quản lý version bằng AWS SDK BOM. Kết quả in **account/ARN**, không chứa secret key/session token. Bên trong EKS, nếu cấu hình đúng, ARN sẽ có dạng `arn:aws:sts::111122223333:assumed-role/OrdersReadOnlyPodRole/...` hoặc role IRSA tương ứng.

### 12.2. Đọc S3 object

~~~java
import java.nio.file.Path;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;

public class DownloadOrdersConfig {
    public static void main(String[] args) {
        try (S3Client s3 = S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {

            s3.getObject(
                GetObjectRequest.builder()
                    .bucket("orders-config-demo")
                    .key("app/config.json")
                    .build(),
                Path.of("config.json")
            );
        }
    }
}
~~~

Đoạn code có thao tác đọc object thật nếu chạy với resources/credentials hợp lệ. Ứng dụng cần IAM `s3:GetObject`, mạng tới S3 endpoint và KMS permissions nếu object được mã hóa bằng customer-managed KMS key.

### 12.3. Thứ tự credentials provider có thể gây sai role

SDK kiểm tra **nhiều nguồn credentials theo thứ tự ưu tiên**. Nếu container còn `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` hoặc custom `StaticCredentialsProvider`, chúng có thể được chọn **trước** IRSA/Pod Identity. Với Java SDK v2, web identity provider được xét trước container credentials provider.

Nếu vừa có **IRSA annotation** vừa có **Pod Identity association**, các biến `AWS_ROLE_ARN`/`AWS_WEB_IDENTITY_TOKEN_FILE` từ IRSA có thể khiến SDK **tiếp tục dùng IRSA**, dù Pod Identity cũng hợp lệ. Trước khi kết luận “Pod Identity không hoạt động”, xác nhận **actual caller ARN**, kiểm tra biến môi trường có liên quan **theo tên, không in secret values**, gỡ cấu hình dư thừa và tạo Pod mới.

Cả hai cơ chế sử dụng **temporary credentials tự hết hạn**. Để SDK provider làm mới tự động; không copy một bộ credentials vào static config của ứng dụng chạy dài ngày.

## 13. Migrate từ IRSA sang EKS Pod Identity

Để giảm downtime và kiểm soát privilege khi di chuyển:

1. **Khảo sát:** cluster/platform version, node Linux EC2 hay Fargate, SDK version, OIDC issuer, annotation hiện hành, IAM role và permissions.
2. **Chuẩn bị:** bật EKS Pod Identity Agent ở cluster hỗ trợ (trừ Auto Mode), cấp node role `eks-auth:AssumeRoleForPodIdentity` và xác nhận EKS Auth endpoint network.
3. **Tạo role Pod Identity:** trust `pods.eks.amazonaws.com` với điều kiện namespace/SA/cluster phù hợp, permissions tối thiểu tương đương hoặc giảm so với IRSA.
4. **Tạo EKS association:** role và ServiceAccount đúng namespace; đợi eventual consistency.
5. **Giữ IRSA trong giai đoạn chuẩn bị**, tránh bỏ quyền trước khi agent/association sẵn sàng.
6. **Xóa annotation IRSA và các web identity env overrides** khỏi ServiceAccount/Pod template khi chuyển traffic.
7. **Rollout từ từ:** dùng rolling/canary deploy để Pod mới nhận injected Pod Identity credentials; không thay toàn bộ Pod production một lúc.
8. **Xác minh:** `GetCallerIdentity` và một API chỉ đọc đã được cấp quyền; theo dõi app health, error logs, CloudTrail, request latency.
9. **Rollback:** nếu Pod mới không lấy được credentials, khôi phục IRSA ServiceAccount/role trust và rollout theo runbook.
10. **Dọn có kiểm soát:** chỉ xóa OIDC trust/provider không còn dùng sau khi xác minh không có ServiceAccount khác phụ thuộc.

~~~mermaid
flowchart TD
    A["IRSA ổn định"] --> B["Kiểm tra compute + SDK + Agent"]
    B --> C["Tạo role Pod Identity và association"]
    C --> D["Gỡ annotation IRSA cho Pod mới"]
    D --> E{"Actual role và AWS API đúng?"}
    E -->|Có| F["Theo dõi và hoàn tất"]
    E -->|Không| G["Rollback IRSA, điều tra nguyên nhân"]
~~~

**Lưu ý:** Việc sửa ServiceAccount không bảo đảm **Pod hiện hữu** được inject lại env vars. Tạo Pod mới là bước cần thiết để quan sát cấu hình identity mới; cập nhật association cũng có độ trễ propagation.

## 14. Security: least privilege, RBAC, IMDS và audit

### 14.1. RBAC bảo vệ danh tính workload

Ai có thể **tạo Pod/Deployment dùng một ServiceAccount quyền cao** có thể tận dụng quyền AWS của role được gắn với SA đó. Vì vậy cần:

- Giới hạn `create/update deployments`, `create pods`, `update serviceaccounts` và thao tác namespace theo Kubernetes RBAC.
- Không gắn IAM quyền cao cho ServiceAccount `default`.
- Phân tách `shop-dev/orders-api` và `shop-prod/orders-api`; kiểm tra `sub` hoặc session tags.
- Dùng admission policy khi phù hợp để hạn chế container đặc quyền, hostPath, image không ký và ServiceAccount không được duyệt.
- Giới hạn `eks:CreatePodIdentityAssociation`, `eks:UpdatePodIdentityAssociation` và **`iam:PassRole`** theo role/cluster, không cho developer tự gắn role admin tùy ý.

Kubernetes RBAC **không phải** IAM role trust policy; cần cả hai.

### 14.2. Bảo vệ node IAM role và IMDS

Trên EKS EC2 nodes, Pod có thể truy cập IMDS nếu không được hạn chế đúng. Với `hostNetwork: true`, AWS nhấn mạnh Pod vẫn có đường tới IMDS, dù AWS SDK có thể ưu tiên IRSA/Pod Identity khi được cấu hình.

- Ưu tiên **IMDSv2** và cấu hình network/hop limit hợp lý.
- Node IAM role chỉ cấp quyền phục vụ node/agent, không chứa dữ liệu business permissions rộng.
- Pod chạy non-root, hạn chế privilege escalation, hostNetwork/hostPID/hostPath.
- Không dùng containers làm security boundary duy nhất; có quy trình cập nhật node OS/Kubernetes và ảnh container.

### 14.3. Không để credentials xuất hiện trong logs

- Không in IRSA projected JWT hoặc Pod Identity token.
- Không dùng `curl` tới local credential endpoint rồi dán response vào ticket; response có secret/token.
- Không đưa access key dài hạn vào `ConfigMap`, `Kubernetes Secret`, Docker image hoặc manifests.
- Đối chiếu **STS caller ARN/account** thay vì hiển thị secret values.
- Không ghi pod service account token vào persistent volume, snapshot hay artifact CI.

### 14.4. CloudTrail và Kubernetes audit

CloudTrail có thể ghi AWS STS/role session API activity, cùng metadata principal/session. Với Pod Identity, **session tags** về cluster, namespace, SA/pod giúp điều tra theo cấu hình. Với IRSA, role/session identity cùng STS `AssumeRoleWithWebIdentity` là điểm đối chiếu.

Kubernetes control-plane audit logs là **một nguồn riêng** để biết ai tạo/sửa ServiceAccount/Deployment. Kết hợp CloudTrail, Kubernetes audit, CloudWatch và EKS logs theo timestamp/request IDs; không giả định một công cụ ghi tất cả sự kiện ở mọi tầng.

## 15. Network: STS, EKS Auth và service endpoints

### 15.1. IRSA cần tới STS

Pod dùng IRSA gọi `AssumeRoleWithWebIdentity` qua STS. Với private subnet không có Internet egress, cân nhắc interface VPC endpoint regional:

~~~text
com.amazonaws.ap-southeast-1.sts
~~~

Dùng **regional STS endpoint**, đảm bảo Private DNS, security groups TCP 443, route/NACL và IAM policies. Nếu SDK được cấu hình gọi global STS endpoint, nó có thể không dùng được private STS endpoint regional. Khi tạo IAM OIDC provider, các mạng private-only cần xử lý riêng khả năng reach OIDC issuer/discovery endpoint từ nơi chạy thao tác quản trị.

### 15.2. Pod Identity cần EKS Auth

Pod Identity Agent cần gọi EKS Auth API. Với node không có NAT/Internet egress, tạo interface endpoint:

~~~text
com.amazonaws.ap-southeast-1.eks-auth
~~~

Đây **không phải** EKS Kubernetes API endpoint và không đồng nghĩa với endpoint `com.amazonaws.ap-southeast-1.eks` của EKS management APIs. Cần endpoint SG, Private DNS, node IAM permission `eks-auth:AssumeRoleForPodIdentity` và add-on healthy.

### 15.3. Local agent và proxy

SDK trong Pod kết nối `169.254.170.23`. Nếu Pod dùng proxy, cập nhật `NO_PROXY` cho IP local, ví dụ:

~~~text
NO_PROXY=169.254.170.23,localhost,127.0.0.1
~~~

Agent có cấu hình IPv6 listener trên địa chỉ `fd00:ec2::23`; với môi trường tắt IPv6, cần thay đổi add-on settings phù hợp. Không mở endpoint agent ra Internet; đây là link-local credential service.

### 15.4. Credentials đúng không đảm bảo đọc được S3

Giả sử Pod đã có role đúng nhưng gọi S3 timeout. Hãy xem **S3 Gateway/Interface VPC Endpoint**, NAT/route, endpoint policy và DNS. Nếu S3 trả `AccessDenied`, kiểm tra IAM permissions, bucket policy, KMS key policy, action/resource key. **STS/Pod Identity chỉ giải quyết nhận credentials**, không tự cung cấp đường truyền tới S3/DynamoDB/Secrets Manager.

## 16. Chi phí, độ sẵn sàng và đa cluster

| Thành phần | Chi phí/khả năng vận hành cần cân nhắc |
|---|---|
| EKS control plane | Phí cluster/support tier theo phiên bản |
| EC2 worker nodes, Fargate, EKS Auto Mode | Compute và storage độc lập với identity |
| STS, EKS Auth | Rate limits, retry/backoff và chính sách sử dụng APIs |
| AWS PrivateLink interface endpoints | Endpoint-hour, data processing và các khoản phí liên quan |
| NAT Gateway | Egress/data processing nếu sử dụng thay PrivateLink |
| CloudWatch, CloudTrail, EKS logs | Log/metrics ingestion, retention, truy vấn |
| S3, DynamoDB, KMS | Phí storage/API/KMS theo tài nguyên nghiệp vụ |

**Độ sẵn sàng:** IRSA phụ thuộc projected token/STS; Pod Identity còn phụ thuộc **agent** và **EKS Auth**. Đừng khởi tạo AWS SDK client/provider lại trên **mỗi request** để giảm tình trạng throttling/cold starts. SDK cần cache temporary credentials, tự refresh và retry tạm thời có backoff. Khi agent lỗi trên một node, workload trên node đó có thể không lấy được credentials mới; multi-AZ/node spread và giám sát agent quan trọng.

**Quy mô:** Pod Identity giúp đơn giản hóa trust policies khi có nhiều clusters vì dùng service principal chung, nhưng vẫn cần tạo association theo cluster/SA và giới hạn IAM role theo workload. Hệ thống nhiều cluster không nên tái dùng một role quá rộng chỉ để giảm số IAM roles.

## 17. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| IRSA `InvalidIdentityToken` | OIDC issuer/provider sai, cluster đã được tạo lại, token `aud` không phù hợp | EKS `identity.oidc.issuer`, IAM OIDC provider và trust |
| IRSA `AccessDenied` tại STS | `sub/aud` trust không khớp namespace/SA hoặc wrong role | So sánh role ARN, trust conditions, ServiceAccount annotation |
| Pod vẫn dùng node role | Không có identity injection, IMDS accessible, SDK provider chain fallback | `serviceAccountName`, caller ARN, IMDS exposure |
| Pod Identity thiếu credentials | Chưa có association, agent không chạy, node compute không được hỗ trợ | `list-pod-identity-associations`, DaemonSet/Auto Mode, node type |
| Agent không tới EKS Auth | Node role thiếu `eks-auth:AssumeRoleForPodIdentity` hoặc private endpoint/SG sai | IAM policy, `eks-auth` VPC endpoint và DNS |
| Agent không start khi IPv6 tắt | Agent cấu hình IPv6 listener mặc định | Add-on configuration disable IPv6 theo AWS docs |
| HTTP proxy làm local credentials lỗi | Không có `NO_PROXY` cho `169.254.170.23` | Proxy settings; kiểm tra kết nối an toàn |
| Pod Identity association đúng nhưng dùng IRSA | Web identity env vars/annotation cũ được ưu tiên | Kiểm tra provider precedence, rollout Pod sau khi gỡ annotation |
| Java SDK không dùng Pod Identity | Version quá cũ hoặc custom provider | Nâng AWS SDK Java v2 ≥ 2.21.30 và dùng default chain |
| Cross-account target role `AccessDenied` | Source role thiếu AssumeRole, target trust/TagSession conditions sai | Kiểm tra IAM hai account và `target-role-arn` |
| Pod gọi S3 bị `AccessDenied` | Role thiếu action, bucket/KMS policy deny | Role ARN thực tế, `s3:GetObject`, KMS/resource policies |
| Pod gọi S3 bị timeout | Thiếu S3 endpoint/network route | VPC, subnet routes, DNS, SG/NACL, NAT |
| `PackedPolicyTooLarge` | Session tags + policy payload quá lớn | Thu gọn policy/tags |
| Fargate không chạy Pod Identity | **Không hỗ trợ** | Dùng IRSA cho EKS Fargate |
| Association mới chưa áp dụng | Eventual consistency và Pod cũ chưa injection | Đợi propagation, tạo Pod mới theo runbook |
| Pod có SA đúng tên nhưng sai namespace | Cặp namespace/SA khác association/trust | `kubectl get pod ... -o yaml` và EKS associations |

### 17.1. Trình tự điều tra

1. Xác định **AWS account, Region, cluster, namespace, Pod và ServiceAccount**.
2. Xác định Pod chạy ở Linux EC2/Auto Mode hay Fargate/Windows.
3. Kiểm tra OIDC annotation/provider (IRSA) hoặc association/agent (Pod Identity).
4. Kiểm tra **actual caller ARN** và thứ tự SDK credentials providers.
5. Đối chiếu IAM role trust + permissions, bucket/KMS policies và conditions.
6. Kiểm tra network path STS/EKS Auth và service endpoints riêng.
7. Quan sát CloudTrail/EKS/CloudWatch logs; retry đúng lỗi tạm thời, không mở wildcard permissions để thử.

## 18. Lab chỉ đọc: kiểm tra IAM identity của EKS workload

**Điều kiện:** AWS CLI v2 profile `dev` được quyền đọc AWS EKS/IAM; `kubectl` được cấu hình đọc cluster `shop-cluster` tại `ap-southeast-1`. Nếu thiếu cluster, có thể phân tích JSON/YAML minh họa trong bài, không cần tạo hạ tầng.

### Bước A — Xác định caller và cluster

~~~bash
aws sts get-caller-identity \
  --profile dev \
  --output json

aws eks describe-cluster \
  --name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --query 'cluster.{Name:name,Status:status,Version:version,Issuer:identity.oidc.issuer}' \
  --output json
~~~

### Bước B — Đọc ServiceAccount và Deployment

~~~bash
kubectl get sa orders-api -n shop -o yaml

kubectl get deployment orders-api \
  -n shop \
  -o jsonpath='{.spec.template.spec.serviceAccountName}'

kubectl get pods -n shop -o wide
~~~

Kiểm tra IRSA annotation có không, deployment sử dụng ServiceAccount nào, Pod chạy ở node nào. Không suy “thiếu annotation” = “không có AWS role” nếu cơ chế là Pod Identity.

### Bước C — Xem Pod Identity associations và agent

~~~bash
aws eks list-pod-identity-associations \
  --cluster-name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --output json

aws eks list-addons \
  --cluster-name shop-cluster \
  --profile dev \
  --region ap-southeast-1 \
  --output json

kubectl get daemonset eks-pod-identity-agent \
  -n kube-system -o wide
~~~

**Nếu EKS Auto Mode**, không nhất thiết thấy DaemonSet vì agent đã tích hợp. Nếu không có association cho cặp namespace/SA, SDK không có lý do chọn Pod Identity cho Pod đó.

### Bước D — Kiểm tra IAM role

~~~bash
aws iam get-role \
  --role-name OrdersReadOnlyPodRole \
  --profile dev \
  --query 'Role.{Arn:Arn,Trust:AssumeRolePolicyDocument}' \
  --output json

aws iam list-attached-role-policies \
  --role-name OrdersReadOnlyPodRole \
  --profile dev \
  --output json
~~~

Để xem toàn bộ IAM permissions, có thể còn phải kiểm tra **inline policies** bằng `list-role-policies/get-role-policy`. Các lệnh trên chỉ đọc, nhưng vẫn cần đúng IAM quyền.

### Bước E — Xác minh identity trong Pod

Nếu container đã có AWS CLI và quyền `kubectl exec`:

~~~bash
# Thay POD_NAME bằng tên Pod thật, không chép nội dung token.
kubectl exec -n shop POD_NAME -- aws sts get-caller-identity
~~~

Nếu production container không có CLI, dùng mã Java `GetCallerIdentity`/công cụ diag được quản trị viên duyệt, chỉ ghi **ARN/account**, không ghi temporary credentials.

### Bước F — Bảng đối chiếu

| Cần xác minh | Nguồn dữ liệu | Câu hỏi |
|---|---|---|
| AWS account/cluster | `get-caller-identity` + `describe-cluster` | Có đúng môi trường không? |
| Kubernetes workload identity | Pod + Deployment + ServiceAccount | Namespace/SA đúng? |
| IRSA mapping | SA annotation + OIDC trust | `sub/aud` khớp? |
| Pod Identity mapping | EKS association + IAM trust | Association/agent hợp lệ? |
| IAM role thực tế | `sts get-caller-identity` trong Pod | SDK dùng role nào? |
| Authorization | IAM/bucket/KMS policies | Role có đúng action/resource không? |
| Networking | VPC endpoints, DNS, SG | Có thể kết nối service API không? |

## 19. Tình huống và câu hỏi tự đánh giá

### 19.1. Tình huống chọn cơ chế

**Tình huống A:** Spring Boot chạy EKS Linux managed node groups, cần đọc S3, sử dụng Java SDK v2 mới. Pod Identity thường phù hợp khi agent, IAM role và EKS Auth endpoint được chuẩn bị đúng.

**Tình huống B:** Batch job trên EKS Fargate cần đọc DynamoDB. Chọn **IRSA**, vì Pod Identity không được hỗ trợ trên Fargate.

**Tình huống C:** Cluster account A cần S3 ở account B. Với Pod Identity, có thể dùng source role ở A và `--target-role-arn` tại B; cần source AssumeRole permission và target trust. Với IRSA, dùng OIDC federation cross-account hoặc role chaining theo thiết kế.

**Tình huống D:** ServiceAccount đã có Pod Identity association nhưng caller vẫn là IRSA role cũ. Kiểm tra `AWS_ROLE_ARN`/`AWS_WEB_IDENTITY_TOKEN_FILE`, gỡ annotation IRSA, rollout Pod mới và quan sát actual caller.

### 19.2. Câu hỏi

1. Vì sao Kubernetes ServiceAccount không trực tiếp tương đương IAM role?
2. IRSA cần IAM trust principal và STS API nào?
3. `sub=system:serviceaccount:shop:orders-api` giúp hạn chế quyền ra sao?
4. Pod Identity trust principal là gì? Vì sao phải có `sts:TagSession`?
5. Ai gọi `eks-auth:AssumeRoleForPodIdentity` và IAM role nào cần quyền đó?
6. Hai biến môi trường nào giúp SDK tìm Pod Identity Agent?
7. Vì sao Pod Identity không cần IAM OIDC provider của cluster?
8. IRSA hay Pod Identity phù hợp với Fargate Pods?
9. Java SDK for Java v2 cần version tối thiểu nào để dùng Pod Identity?
10. Vì sao cùng một SA có annotation IRSA và association mới có thể vẫn dùng IRSA?
11. `--target-role-arn` có tác dụng gì khi cần dữ liệu ở account khác?
12. Một Pod gọi S3 bị timeout; có phải tăng IAM permissions là cách đầu tiên không?
13. Vai trò Kubernetes RBAC khi người dùng được quyền thay ServiceAccount/Deployment là gì?
14. Vì sao IMDS vẫn phải được bảo vệ khi đã bật IRSA/Pod Identity?
15. Khi migrate, tại sao không xóa toàn bộ IAM OIDC provider ngay lập tức?
16. Làm thế nào xác minh role thật mà không làm lộ token?

### Gợi ý đáp án

- **IRSA:** OIDC projected token → AWS STS `AssumeRoleWithWebIdentity` → temporary credentials.
- **Pod Identity:** EKS association → local agent → EKS Auth `AssumeRoleForPodIdentity` → temporary credentials.
- **Bảo mật:** IAM trust + permissions + Kubernetes RBAC + IMDS isolation + network path.
- **Vận hành:** default credentials provider chain, đúng SDK, actual role ARN, lifecycle refresh, CloudTrail, rollout/rollback.

## 20. Tài liệu AWS chính thức

1. [IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html) — Kiến trúc IRSA và OIDC.
2. [Assign IAM roles to Kubernetes service accounts](https://docs.aws.amazon.com/eks/latest/userguide/associate-service-account-role.html) — IRSA trust, annotations và manifest.
3. [Create an IAM OIDC provider for your EKS cluster](https://docs.aws.amazon.com/eks/latest/userguide/enable-iam-roles-for-service-accounts.html) — Kết nối cluster issuer tới IAM.
4. [Learn how EKS Pod Identity grants pods access to AWS services](https://docs.aws.amazon.com/eks/latest/userguide/pod-identities.html) — Giới hạn Fargate, node support và association.
5. [Understand how EKS Pod Identity works](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-how-it-works.html) — Agent, EKS Auth và environment variables.
6. [Set up the EKS Pod Identity Agent](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-agent-setup.html) — Agent add-on, node IAM, VPC endpoint.
7. [Create IAM role for EKS Pod Identity](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-role.html) — Service trust principal và session tags.
8. [Create/assign EKS Pod Identity association](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-association.html) — Association API và Console.
9. [Use EKS Pod Identity with an AWS SDK](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-minimum-sdk.html) — Java SDK v2 ≥ 2.21.30.
10. [Pod Identity target IAM roles and cross-account](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-assign-target-role.html) — Role chaining trong EKS.
11. [AWS CLI create-pod-identity-association](https://docs.aws.amazon.com/cli/latest/reference/eks/create-pod-identity-association.html) — Flags, target role và session policy.
12. [Pod Identity session tags and ABAC](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-abac.html) — Session tags và IAM conditions.
13. [EKS node IAM role](https://docs.aws.amazon.com/eks/latest/userguide/create-node-role.html) — Quyền `eks-auth:AssumeRoleForPodIdentity`.
14. [Identity and Access Management best practices for EKS](https://docs.aws.amazon.com/eks/latest/best-practices/identity-and-access-management.html) — Least privilege và IMDS.
15. [AWS SDK for Java v2 credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html) — Provider precedence và refresh.
16. [AWS STS AssumeRoleWithWebIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_AssumeRoleWithWebIdentity.html) — STS federation.
17. [Amazon EKS PrivateLink endpoints](https://docs.aws.amazon.com/eks/latest/userguide/vpc-interface-endpoints.html) — Kết nối EKS Auth API ở VPC private.
18. [Kubernetes ServiceAccounts](https://kubernetes.io/docs/concepts/security/service-accounts/) — Danh tính Kubernetes và RBAC.
19. [AWS STS Regional endpoints](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_enable-regions.html) — STS trong Region.

> **Ghi nhớ:** **IRSA** dùng OIDC token và `AssumeRoleWithWebIdentity`; **EKS Pod Identity** dùng EKS association, Pod Identity Agent và EKS Auth. Cả hai chỉ phát huy hiệu quả khi kết hợp **quyền IAM tối thiểu, RBAC, IMDS isolation, SDK tự làm mới credentials, VPC endpoints, kiểm toán và rollout có kiểm soát**.

