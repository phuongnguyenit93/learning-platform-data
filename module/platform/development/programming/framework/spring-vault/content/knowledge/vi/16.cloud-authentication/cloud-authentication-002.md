# Nguồn AWS credentials và quyền của danh tính chạy ứng dụng

> **Chương:** Xác thực cloud  
> **Ngữ cảnh Spring Vault:** Khi ứng dụng Java đăng nhập HashiCorp Vault bằng AWS IAM authentication, điều quan trọng không chỉ là ký được yêu cầu STS `GetCallerIdentity`. Ta còn phải biết **bộ AWS credentials nào đã được chọn**, nó đại diện cho **IAM principal nào**, principal được phép nhận credentials theo **trust policy** nào và principal đó được ánh xạ tới **Vault auth role/ACL policy** ra sao.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt `AwsCredentials`, `AwsCredentialsProvider`, **default provider chain**, IAM role và temporary role session.
2. Biết AWS SDK for Java 2.x tìm credentials từ system properties, environment variables, web identity, shared profiles, container credentials và EC2 instance metadata theo thứ tự nào.
3. Đối chiếu nguồn credentials trong **EC2, ECS/Fargate, Lambda, EKS IRSA, EKS Pod Identity và local development**; nhận diện trường hợp credentials từ nguồn không mong đợi “che” danh tính workload.
4. Phân biệt **AWS trust policy**, **AWS permissions policy**, **Vault AWS auth role binding** và **Vault ACL policy**; thiết kế nguyên tắc quyền tối thiểu.
5. Cấu hình Spring Vault `AwsIamAuthentication` sử dụng provider có khả năng làm mới temporary credentials; đọc KV v2 sau khi nhận Vault token.
6. Xử lý khi AWS credentials, Vault login token hoặc secret lease hết hạn, và chẩn đoán các lỗi sai principal/STS/permission.
7. Lập ma trận kiểm thử tích hợp và checklist an toàn để xác minh ứng dụng đang chạy đúng danh tính dự kiến.

## 1. Câu hỏi gốc: “Ứng dụng đang ký bằng danh tính AWS nào?”

Giả sử cùng một bản build `orders-service` được chạy trên laptop, ECS Fargate và EKS. Trong Java, ba nơi đều dùng:

~~~java
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;

AwsCredentialsProvider provider = DefaultCredentialsProvider.create();
~~~

Code như nhau, nhưng **danh tính AWS có thể khác hoàn toàn**:

- Trên **laptop**, SDK có thể đọc profile `orders-dev` với credentials của role thử nghiệm.
- Trên **ECS task**, SDK có thể đọc temporary credentials của **task role** qua endpoint credentials do ECS agent cung cấp.
- Trên **EKS**, SDK có thể lấy credentials bằng **IRSA web identity** hoặc **EKS Pod Identity agent**, tùy cơ chế cluster và pod được cấu hình.
- Nếu một image mang theo `AWS_ACCESS_KEY_ID` và `AWS_SECRET_ACCESS_KEY`, biến môi trường có thể được chọn **trước** nguồn credentials do container agent cấp. Ứng dụng tưởng đang dùng task role, nhưng thực tế đã ký bằng principal khác.

Đó là lý do triển khai Vault AWS IAM auth phải bắt đầu từ **nguồn credentials** và **quyền của workload**, không chỉ từ tên `role` trong cấu hình Spring Vault.

### 1.1. Năm đối tượng khác nhau

| Đối tượng | Ví dụ | Vai trò thật |
|---|---|---|
| **IAM role** | `arn:aws:iam::123456789012:role/OrdersRuntimeRole` | Danh tính có trust policy và permissions policy trong AWS |
| **Role session** | `arn:aws:sts::123456789012:assumed-role/OrdersRuntimeRole/order-task-42` | Danh tính của một phiên assume role cụ thể; thường dùng temporary credentials |
| **AWS credentials** | Access key ID, secret access key, và session token nếu là temporary credentials | Khả năng ký AWS SigV4; không phải Vault token |
| **Vault AWS auth role** | `auth/aws/role/orders-iam` | Định nghĩa AWS principals được phép đăng nhập Vault và policies/token TTL sẽ nhận |
| **Vault login token** | Giá trị do `auth/aws/login` phát hành | Bearer token dùng để gọi `VaultOperations` đối với Vault secrets engines |

**AWS role không phải Vault role.** AWS permissions policy cũng **không** tự cấp quyền `secret/data/...` trong Vault. Hai hệ thống có mô hình phân quyền riêng, nối với nhau qua quá trình xác thực AWS IAM của Vault.

## 2. Bộ AWS credentials có những thành phần nào?

### 2.1. Long-term credentials so với temporary credentials

| Thành phần | Long-term IAM user credentials | Temporary role credentials |
|---|---|---|
| Access key ID | Có | Có |
| Secret access key | Có | Có |
| Session token | Thông thường không | **Có** |
| Thời hạn sử dụng | Không tự hết hạn theo TTL phiên, cần rotation/revoke quản trị | Có expiration do cơ chế role/STS phát hành |
| Nguồn cấp | Tạo và quản trị trong IAM | STS, EC2 instance profile, ECS task role, Lambda, EKS integration... |
| Khuyến nghị cho workload | Tránh dùng nếu có thể | **Ưu tiên** workload identity và temporary credentials |

Một temporary credentials set là **bộ ba đi cùng nhau**. Chỉ lấy access key ID và secret access key mà bỏ session token có thể gây `InvalidClientTokenId` hoặc `ExpiredToken`. Không tự lưu lâu dài các trường này trong `application.yml`, Git, container image hay cache không có kiểm soát.

### 2.2. Provider khác với credentials snapshot

Trong AWS SDK for Java v2:

- `AwsCredentials` biểu diễn một **bộ credentials tại thời điểm lấy ra**.
- `AwsSessionCredentials` bao gồm thêm session token cho credentials tạm thời.
- `AwsCredentialsProvider` có phương thức `resolveCredentials()` để cung cấp credentials theo cơ chế của provider.
- `DefaultCredentialsProvider` thử lần lượt các nguồn; provider chuyên biệt có thể hỗ trợ refresh temporary credentials theo cơ chế của nó.

Nếu chỉ resolve một lần lúc startup và truyền một `AwsCredentials` cố định vào cấu hình, ta có thể **đánh mất khả năng tự thay credential** khi phiên AWS hết hạn. Vì vậy, khi tích hợp Spring Vault AWS IAM nên ưu tiên khai báo **`credentialsProvider(...)`**, không hard-code `AwsBasicCredentials` hoặc giữ mãi một snapshot `AwsSessionCredentials`.

~~~mermaid
flowchart LR
    ID["AWS workload identity<br/>task / pod / instance / function"] --> P["AwsCredentialsProvider"]
    P -->|"resolve/refresh khi cần"| C["Temporary AWS credentials"]
    C --> S["Spring Vault<br/>ký AWS SigV4"]
    S --> V["Vault auth/aws/login"]
    V --> T["AWS STS<br/>GetCallerIdentity"]
    T --> V
    V -->|"Vault login token"| A["VaultOperations<br/>KV / Transit / PKI"]
~~~

Trong flow Vault IAM, client lấy AWS credentials để **ký** STS `GetCallerIdentity` request; Vault nhận request đã ký và kiểm tra nó bằng AWS STS. Secret access key không phải giá trị được gửi trực tiếp trong payload login. Tuy nhiên, **request đã ký và Vault token vẫn nhạy cảm**, cần được bảo vệ khỏi replay, logging và tiết lộ qua traces.

## 3. DefaultCredentialsProvider: chuỗi tìm kiếm của AWS SDK Java 2.x

AWS SDK v2 sử dụng `DefaultCredentialsProvider` để lần lượt tìm credentials. **Nguồn đầu tiên cung cấp đủ cấu hình sẽ được chọn**; SDK không mặc nhiên ưu tiên ECS/EKS role chỉ vì đang chạy trong container.

### 3.1. Thứ tự nguồn cần thuộc

| Ưu tiên | Provider trong Java SDK v2 | Nguồn dữ liệu | Trường hợp thường gặp |
|---|---|---|---|
| **1** | `SystemPropertyCredentialsProvider` | JVM properties: `aws.accessKeyId`, `aws.secretAccessKey`, tùy trường hợp `aws.sessionToken` | Ứng dụng được khởi chạy bằng `-D...`, hệ thống build/test |
| **2** | `EnvironmentVariableCredentialsProvider` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` | Container env, CI, công cụ vận hành |
| **3** | `WebIdentityTokenFileCredentialsProvider` | `AWS_WEB_IDENTITY_TOKEN_FILE`, `AWS_ROLE_ARN`, session name nếu có | **EKS IRSA** hoặc workload federation tương tự |
| **4** | `ProfileCredentialsProvider` | Shared `~/.aws/config` và `~/.aws/credentials`, `AWS_PROFILE` hoặc profile mặc định | Local dev; SSO/IAM Identity Center, assume role chain |
| **5** | `ContainerCredentialsProvider` | ECS/container credentials endpoint và authorization token tương ứng | **ECS/Fargate task role** và **EKS Pod Identity** |
| **6** | `InstanceProfileCredentialsProvider` | EC2 Instance Metadata Service (IMDS) | **EC2 instance profile** |

Thứ tự trên áp dụng cho **AWS SDK for Java 2.x**. AWS SDK v1 có chi tiết khác; không sao chép máy móc hướng dẫn `DefaultAWSCredentialsProviderChain` của v1 vào source dùng class `software.amazon.awssdk.*` của v2.

Trong bước profile, SDK có thể sử dụng SSO, credentials từ profile, `source_profile`/`role_arn`, `credential_process` hoặc web identity được khai báo theo cấu hình. Đây là **một provider** nhưng có nhiều nhánh nội bộ; “profile” không nhất thiết đồng nghĩa một access key tĩnh.

### 3.2. Credentials shadowing — lỗi dễ bị bỏ qua

Giả sử pod EKS đã được cấu hình IRSA đúng, nhưng image chứa:

~~~text
AWS_ACCESS_KEY_ID=AKIA...                 # ví dụ cấu trúc, không phải khóa thật
AWS_SECRET_ACCESS_KEY=...                # tuyệt đối không commit giá trị thật
AWS_ROLE_ARN=arn:aws:iam::123456789012:role/OrdersRuntimeRole
AWS_WEB_IDENTITY_TOKEN_FILE=/var/run/secrets/eks.amazonaws.com/serviceaccount/token
~~~

`EnvironmentVariableCredentialsProvider` đứng **trước** `WebIdentityTokenFileCredentialsProvider`. Nếu hai biến access key cung cấp credentials hợp lệ, SDK có thể ký bằng credentials từ **environment**, dù pod có đủ cấu hình IRSA. Vault có thể từ chối vì principal thực không khớp role, hoặc nguy hiểm hơn, cấp token theo một role khác nếu policy quá rộng.

Vì vậy:

1. Không đóng gói AWS static credentials vào Docker image hoặc manifest của workload đã có role identity.
2. Không chỉ nhìn thấy `AWS_ROLE_ARN` rồi kết luận code đang dùng IRSA.
3. Kiểm tra **principal thực tế** bằng cách chẩn đoán an toàn trong môi trường được phép.
4. Dùng các Vault role bindings theo principal **cụ thể** để phát hiện cấu hình lệch.

### 3.3. Khi không có nguồn hợp lệ

Nếu không một provider nào tìm được credentials, SDK thường báo `SdkClientException` với thông tin kiểu `Unable to load credentials from any of the providers in the chain`. Đây là **lỗi AWS credential resolution**, xảy ra **trước hoặc trong quá trình ký IAM login**, không phải lỗi Vault policy trên KV.

Khắc phục ở nơi chạy ứng dụng: task role/instance profile, pod association, profile/SSO, token web identity, IAM trust, quyền đọc metadata endpoint, JVM properties hoặc env bị override. Không sửa bằng cách đặt Vault root token vào code.

## 4. Nguồn credentials theo từng môi trường chạy

### 4.1. EC2: instance profile và IMDS

EC2 instance có thể được gắn **IAM instance profile** chứa IAM role. AWS cung cấp temporary credentials cho instance qua **Instance Metadata Service**. `InstanceProfileCredentialsProvider` của AWS SDK có thể lấy và làm mới credentials, sau đó Spring Vault dùng để ký IAM login.

~~~text
EC2 instance
  -> Instance profile: OrdersRuntimeRole
  -> IMDSv2 / instance metadata
  -> Temporary AWS credentials
  -> SigV4 GetCallerIdentity
  -> Vault auth/aws -> Vault token
~~~

Điểm vận hành:

- Ưu tiên **IMDSv2**, cấu hình metadata hop limit và chặn truy cập IMDS không cần thiết từ tiến trình/container khác.
- Không dùng IAM role quá rộng cho EC2 chỉ vì nhiều ứng dụng cùng nằm trên một host; phải cân nhắc ranh giới tin cậy giữa workloads.
- Hạn chế SSRF và quyền truy cập metadata endpoint; ai lấy được temporary credentials của role có thể ký request dưới danh tính tương ứng trong thời hạn hiệu lực.
- Kiểm tra credentials trên instance thực, vì system properties/env/profile có thể ưu tiên trước IMDS.

### 4.2. ECS/Fargate: task role khác task execution role

ECS thường có **hai loại IAM role** cần phân biệt:

| Loại role | Dùng cho | Có nên là danh tính ký IAM login của ứng dụng? |
|---|---|---|
| **Task role** | AWS API do code chạy **bên trong container** gọi | **Có**: đây thường là principal ứng dụng muốn dùng |
| **Task execution role** | Nhiệm vụ do ECS agent thực hiện như pull image, gửi logs, lấy một số tài nguyên deployment | **Không mặc nhiên**: không phải role ứng dụng có thể dùng tùy ý |

Với task role, ECS agent cấp temporary credentials qua container credentials endpoint; AWS SDK v2 sử dụng `ContainerCredentialsProvider`. Các biến như `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` cho SDK biết nơi lấy credentials.

Hãy cấp role riêng cho các task cần quyền Vault khác nhau. Nếu nhiều task cùng task role, Vault IAM authentication nhìn thấy cùng AWS principal và **không tự biết đó là dịch vụ nào**. Tách task roles và Vault auth roles/policies khi ranh giới ứng dụng đòi hỏi.

### 4.3. Lambda: execution role

AWS Lambda gắn **execution role** cho function và cung cấp temporary credentials cho runtime. AWS SDK có thể lấy từ environment/runtime chain, sau đó Spring Vault dùng chúng để ký IAM login.

Các cân nhắc riêng:

- Execution environment có thể được tái sử dụng giữa nhiều invocation; provider và Vault session manager có thể tồn tại trong bộ nhớ process.
- Không tạo lại toàn bộ Vault client/token/session trong mỗi request Lambda nếu cơ chế khởi tạo của ứng dụng không yêu cầu; nhưng cũng không cache một credentials snapshot đã hết hạn.
- Thời hạn function và timeout khi gọi Vault/STS cần được cân đối với latency cold start và mạng/VPC.
- Tách Lambda execution role theo function/nhóm chức năng khi quyền khác nhau, thay vì một shared role có Vault policy quá rộng.

### 4.4. EKS IRSA: web identity trước khi ký Vault login

**IAM Roles for Service Accounts (IRSA)** dùng ServiceAccount của Kubernetes kết hợp OIDC federation để workload nhận temporary AWS credentials. Có **hai bước xác thực AWS/Vault khác nhau**:

~~~mermaid
sequenceDiagram
    autonumber
    participant P as EKS Pod
    participant C as AWS SDK Web Identity Provider
    participant S as AWS STS
    participant V as Vault auth/aws
    participant K as Vault KV

    P->>C: Đọc ServiceAccount OIDC token + AWS_ROLE_ARN
    C->>S: AssumeRoleWithWebIdentity
    S-->>C: Temporary AWS credentials của role
    C-->>P: Credentials hiện hành
    P->>P: Ký GetCallerIdentity bằng SigV4
    P->>V: Gửi signed request đến auth/aws/login
    V->>S: Verify signed GetCallerIdentity qua STS
    S-->>V: ARN / Account / UserId
    V-->>P: Vault token theo IAM principal binding
    P->>K: GET KV theo Vault ACL policy
~~~

Trong IRSA, `AWS_WEB_IDENTITY_TOKEN_FILE` là đường dẫn tới **Kubernetes projected OIDC token**; `AWS_ROLE_ARN` là IAM role muốn assume. Web identity provider trao đổi token này với STS để nhận temporary AWS credentials; sau đó Spring Vault ký thêm một STS `GetCallerIdentity` request để đăng nhập Vault. Đừng nhầm token OIDC, AWS session token và Vault login token thành một thứ.

Cần có:

- OIDC issuer/provider của cluster được cấu hình và tin cậy ở IAM.
- IAM role trust policy cho đúng ServiceAccount, namespace và audience; không bind bừa mọi ServiceAccount trong cluster.
- ServiceAccount/pod được chú thích hoặc gắn association IRSA phù hợp theo thiết lập EKS.
- SDK có khả năng xử lý web identity và dependency STS cần thiết; mạng/DNS đến STS cho bước `AssumeRoleWithWebIdentity`.

**Phân biệt với Vault Kubernetes auth:** Kubernetes auth của Vault kiểm tra Kubernetes ServiceAccount JWT trực tiếp theo cấu hình auth method `kubernetes`. AWS IAM auth yêu cầu **AWS credentials để ký** STS request. Ứng dụng EKS có thể chọn một trong hai tùy trust model; không có nghĩa phải sử dụng đồng thời.

### 4.5. EKS Pod Identity: container provider, không phải IRSA

**EKS Pod Identity** liên kết Kubernetes ServiceAccount với IAM role qua EKS Pod Identity association. EKS Pod Identity agent cung cấp temporary credentials cho pod qua **container credentials provider**. Khác IRSA, SDK không cần tự gọi `AssumeRoleWithWebIdentity` bằng projected token IRSA để lấy credentials; agent và EKS Auth service thực hiện chu trình cung cấp credentials của Pod Identity.

AWS SDK nhận cấu hình container provider từ các biến như:

~~~text
AWS_CONTAINER_CREDENTIALS_FULL_URI
AWS_CONTAINER_AUTHORIZATION_TOKEN_FILE
~~~

Điểm khác biệt:

| Nội dung | EKS IRSA | EKS Pod Identity |
|---|---|---|
| Cách cấp AWS credentials | SDK dùng OIDC web identity token để gọi `AssumeRoleWithWebIdentity` | Pod Identity agent/EKS Auth cấp credentials qua container endpoint |
| Provider điển hình | `WebIdentityTokenFileCredentialsProvider` | `ContainerCredentialsProvider` |
| Thiết lập IAM | OIDC provider + trust policy cho ServiceAccount subject/audience | EKS Pod Identity association + role trust phù hợp với service `pods.eks.amazonaws.com` |
| Tác động precedence | Đứng trước profile/container/IMDS | Đứng **sau** system props, env, web identity và profile |
| Điều kiện SDK | SDK hỗ trợ web identity/STS flow | SDK hỗ trợ EKS Pod Identity/container credentials |

Với Java SDK v2, hãy sử dụng bản tương thích EKS Pod Identity; AWS ghi nhận hỗ trợ từ **2.21.30** trở lên. Khi di chuyển từ IRSA sang Pod Identity, phải loại bỏ **nguồn credentials ưu tiên cao hơn** nếu muốn container provider thực sự được chọn.

### 4.6. Local development và CI

Trên laptop có thể sử dụng AWS IAM Identity Center/SSO hoặc profile assume role của tài khoản test. Ví dụ:

~~~bash
# Chỉ chọn tên profile; không đặt access key/password vào câu lệnh.
export AWS_PROFILE=orders-dev
aws sts get-caller-identity --profile orders-dev
~~~

Lệnh CLI cho biết principal của **lần gọi CLI** với profile tương ứng, hữu ích để chẩn đoán. Nhưng nó **không chứng minh** JVM dùng cùng credentials: JVM system properties/env/web identity hoặc cách chọn profile có thể khác. Khi test Java, cần xác minh nguồn provider ở process Java và không log access key/secret/session token.

Trong CI, ưu tiên OIDC/workload federation hoặc assume role tạm thời theo hệ thống CI được hỗ trợ, thay vì static AWS access keys lưu lâu dài trong secret variables. Phân tách role CI khỏi role production runtime; CI có thể có quyền triển khai, nhưng không nên mặc nhiên có Vault policy đọc secret production.

## 5. AWS trust policy, permissions policy và Vault policy khác nhau

Để một ứng dụng đăng nhập Vault bằng IAM, **ít nhất ba lần quyết định quyền** xảy ra:

~~~mermaid
flowchart TB
    W["Workload: ECS task / EKS pod / EC2 / Lambda"] --> T{"1. AWS trust policy<br/>Có được nhận/assume role?"}
    T -->|"Được phép"| C["Temporary AWS credentials<br/>cho IAM role"]
    C --> A{"2. Vault AWS auth role<br/>IAM principal có được login?"}
    A -->|"Bound ARN khớp"| V["Vault token + policies + TTL"]
    V --> P{"3. Vault ACL<br/>Có quyền với path/operation?"}
    P -->|"Có"| E["KV / Database / Transit / PKI"]
    T -->|"Không"| X["Không nhận credentials của role"]
    A -->|"Không"| Y["Vault login bị từ chối"]
    P -->|"Không"| Z["Vault API 403"]
~~~

### 5.1. Trust policy: ai có thể assume role?

Trust policy là **resource-based policy của IAM role**. Nó quyết định AWS principal/service hoặc federated principal nào có thể assume role theo hành động `sts:AssumeRole`, `sts:AssumeRoleWithWebIdentity` hay cơ chế liên quan.

Ví dụ trust policy dạng khái niệm cho một **ECS task role**:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "Service": "ecs-tasks.amazonaws.com" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "aws:SourceAccount": "123456789012"
        },
        "ArnLike": {
          "aws:SourceArn": "arn:aws:ecs:ap-southeast-1:123456789012:*"
        }
      }
    }
  ]
}
~~~

Đây là **một ví dụ cho ECS**, không dùng cho IRSA/Pod Identity/Lambda/EC2. Trust principal và conditions phải thay theo nền tảng và hướng dẫn AWS. Việc cấu hình trust sai có thể làm workload không nhận được role credentials hoặc cho phép workload ngoài dự kiến assume role.

### 5.2. Permissions policy: role được phép gọi API AWS nào?

Permissions policy của role kiểm soát các hành động AWS mà **role đã được assume** có thể thực hiện, ví dụ `s3:GetObject` trên một bucket hoặc `kms:Decrypt` trên key được phép.

Để chứng minh danh tính với Vault AWS IAM:

- Client ký `GetCallerIdentity` bằng credentials của role.
- AWS STS xác minh chữ ký và trả caller identity.
- AWS `sts:GetCallerIdentity` **không yêu cầu một allow permission riêng để trả thông tin caller identity** theo tài liệu AWS.
- **Không cần cấp `AdministratorAccess` hoặc `iam:*` cho workload** chỉ để login Vault.

Nếu một role còn cần S3/DynamoDB/KMS vì nghiệp vụ, hãy cấp **các AWS actions và resources cụ thể** cho nhu cầu đó. Các quyền AWS này độc lập với quyền đọc KV ở Vault.

### 5.3. Vault AWS auth role: principal nào được login?

Ví dụ quản trị viên Vault tạo role:

~~~bash
# Lệnh dành cho Vault operator trong môi trường test/được ủy quyền.
vault write auth/aws/role/orders-iam \
  auth_type=iam \
  bound_iam_principal_arn="arn:aws:iam::123456789012:role/OrdersRuntimeRole" \
  token_policies="orders-payment-read" \
  token_ttl="20m" \
  token_max_ttl="1h"
~~~

`bound_iam_principal_arn` ràng buộc **IAM principal** của signed STS request với Vault role. Role name `orders-iam` là tên ở **Vault**, không phải IAM role name. Với temporary role sessions, STS có thể trả `arn:aws:sts::123456789012:assumed-role/OrdersRuntimeRole/<session-name>`; Vault dùng cơ chế nhận diện/canonicalization role để so với IAM principal binding.

**Nguy cơ wildcard:** Bind `arn:aws:iam::123456789012:role/*` có thể cho **mọi role trong tài khoản** đáp ứng login role đó (tùy điều kiện khác). Nếu role bị gắn Vault policy đọc secret nhạy cảm, một AWS workload ít tin cậy hơn có thể nhận quyền Vault ngoài dự kiến. Chọn ARN cụ thể, môi trường tách riêng và dùng các điều kiện ràng buộc bổ sung nếu thực sự cần.

Một số cấu hình Vault resolve ARN sang **AWS unique ID** để giảm nguy cơ role bị xóa/tạo lại cùng tên và tiếp tục thừa hưởng quyền. Việc này có thể cần quyền và kết nối từ **Vault server** đến các AWS IAM APIs để resolve role/user; đây không phải lý do cấp `iam:GetRole` rộng cho **ứng dụng nghiệp vụ**.

### 5.4. Vault ACL: sau login được làm gì?

Giả sử KV v2 mount `secret/`, key logic `prod/orders/payment`:

~~~hcl
# orders-payment-read.hcl
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

Policy áp trên Vault token sau IAM login. Nó **không** cho đọc key `secret/data/prod/inventory/payment`, không cho `list` metadata của cả mount và không cho Transit decrypt.

Trong KV v2:

~~~text
Java key logic:  prod/orders/payment
Vault API:       GET /v1/secret/data/prod/orders/payment
Vault ACL:       secret/data/prod/orders/payment
Capability:      read
~~~

Nếu login thành công mà đọc KV bị `403`, cần xem **Vault token policies và API path**, không mặc định tăng AWS IAM permissions.

## 6. Spring Vault: truyền đúng `AwsCredentialsProvider` vào client auth

### 6.1. Cơ sở cấu hình

Trong Spring Vault, `AwsIamAuthentication` dùng AWS credentials để ký STS `GetCallerIdentity` request và login tại Vault auth method `aws` hoặc mount khác. Ví dụ dưới đây dành cho Spring Vault API tương thích **AWS SDK for Java 2.x** (chẳng hạn Spring Vault 4.1.x). Với phiên bản cũ sử dụng AWS SDK v1, **không trộn class `com.amazonaws.*` và `software.amazon.awssdk.*`**.

Giả định Vault Ops đã:

1. Bật AWS auth method tại `auth/aws`, cấu hình việc xác minh AWS identity và endpoint STS.
2. Tạo Vault role `orders-iam` ràng buộc `arn:aws:iam::123456789012:role/OrdersRuntimeRole`.
3. Gắn policy `orders-payment-read` vào Vault role.
4. Bật KV v2 mount `secret` và tạo key `prod/orders/payment`.
5. Cấu hình signed `X-Vault-AWS-IAM-Server-ID` để hạn chế replay giữa các Vault deployments.

### 6.2. Ví dụ Java cấu hình beans

~~~java
import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AwsIamAuthentication;
import org.springframework.vault.authentication.AwsIamAuthenticationOptions;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;

@Configuration
public class AwsWorkloadVaultConfiguration extends AbstractVaultConfiguration {

    private final AwsCredentialsProvider awsCredentials =
        DefaultCredentialsProvider.create();

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(
            URI.create("https://vault.internal.example:8200"));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        AwsIamAuthenticationOptions options =
            AwsIamAuthenticationOptions.builder()
                .path("aws")                      // Auth mount trong Vault
                .role("orders-iam")                // Vault role, KHÔNG phải AWS role
                .serverId("vault.internal.example")
                .credentialsProvider(awsCredentials)
                .region(Region.AP_SOUTHEAST_1)
                .endpointUri(URI.create(
                    "https://sts.ap-southeast-1.amazonaws.com/"))
                .build();

        return new AwsIamAuthentication(options, vaultClient());
    }
}
~~~

Điểm cần kiểm soát:

- `DefaultCredentialsProvider.create()` **không chỉ định role**. Nó lấy credentials từ nguồn AWS runtime có ưu tiên cao nhất. Do đó, **deployment identity** là phần không thể thiếu của cấu hình.
- `.role("orders-iam")` là **Vault auth role**. AWS principal thực tế phải khớp `bound_iam_principal_arn` phía Vault.
- `.serverId(...)` phải khớp giá trị `iam_server_id_header_value` do Vault Ops thiết lập để header `X-Vault-AWS-IAM-Server-ID` được ký trong STS request.
- `.region(...)` và `.endpointUri(...)` trong ví dụ cùng trỏ tới **regional STS**. Region ký SigV4 và STS endpoint phải được chọn nhất quán.
- `vaultClient()` phải sử dụng HTTPS với truststore/CA và hostname verification hợp lệ; ngoài ra cần connect/read timeout phù hợp.
- `AbstractVaultConfiguration` quản lý các bean Spring Vault; business service không nên tự gọi login lại theo từng HTTP request khi đã có session manager được cấu hình đúng.

Trong code production, nên quản lý `AwsCredentialsProvider` theo lifecycle của ứng dụng, tránh resolve một lần rồi giữ `AwsCredentials` snapshot vĩnh viễn. Với provider có quản lý tài nguyên riêng, đóng tài nguyên khi shutdown theo API tương ứng. Đừng log kết quả `resolveCredentials()` để debug.

### 6.3. Đọc KV v2 sau khi đăng nhập IAM

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersPaymentSecretReader {

    private final VaultKeyValueOperations kv;

    public OrdersPaymentSecretReader(VaultOperations vaultOperations) {
        this.kv = vaultOperations.opsForKeyValue(
            "secret", KeyValueBackend.KV_2);
    }

    public String readRequiredKey() {
        VaultResponse response = kv.get("prod/orders/payment");
        if (response == null) {
            throw new IllegalStateException("Required secret not found");
        }
        Object value = response.getRequiredData().get("api-key");
        if (!(value instanceof String key) || key.isBlank()) {
            throw new IllegalStateException("Required secret field missing");
        }
        return key; // Dùng nội bộ, không log hoặc trả trong REST response.
    }
}
~~~

Tại thời điểm này, `VaultOperations` dùng **Vault login token** có ACL policy, chứ không ký từng lần đọc KV bằng AWS access key. Nếu key tĩnh được bên thứ ba phát hành, thay version KV **không tự revoke** key cũ ở nhà phát hành; ứng dụng phải thiết kế refresh/cache và rotation riêng.

### 6.4. Cấu hình nếu dùng Spring Cloud Vault

Nếu chủ yếu nạp secret làm cấu hình Spring Boot, có thể chọn Spring Cloud Vault phiên bản tương thích:

~~~yaml
spring:
  application:
    name: orders-service
  config:
    import: "vault://"
  cloud:
    vault:
      uri: "https://vault.internal.example:8200"
      authentication: AWS_IAM
      aws-iam:
        aws-path: aws
        role: orders-iam
        server-name: vault.internal.example
        region: ap-southeast-1
        endpoint-uri: https://sts.ap-southeast-1.amazonaws.com/
      kv:
        enabled: true
        backend: secret
~~~

`vault://` sẽ nạp **config contexts** theo cấu hình Spring Cloud Vault/ứng dụng, không mặc nhiên đọc `prod/orders/payment` nếu context path chưa được khai báo đúng. Cần kiểm chứng đường dẫn source và policy, đồng thời nhớ rằng một bean đã bind property không nhất thiết tự đổi khi KV secret rotate.

## 7. Xác minh danh tính thật mà không tiết lộ credentials

Để kiểm tra một ứng dụng đang dùng đúng AWS role, cần phân biệt **chẩn đoán principal** với **in ra credentials**:

### 7.1. Trên môi trường thử nghiệm

CLI hỗ trợ kiểm tra caller identity:

~~~bash
# Chỉ chạy trong môi trường test với quyền được cấp.
aws sts get-caller-identity --profile orders-dev
~~~

Ví dụ kết quả giả:

~~~json
{
  "UserId": "AROAEXAMPLEID:orders-dev-session",
  "Account": "123456789012",
  "Arn": "arn:aws:sts::123456789012:assumed-role/OrdersRuntimeRole/orders-dev-session"
}
~~~

`Arn` và `Account` có thể nhạy cảm theo quy định nội bộ; chỉ chia sẻ trong kênh chẩn đoán được phép. Không in `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN` hoặc toàn bộ `AwsCredentials` vào log.

**Giới hạn:** CLI dùng `--profile` có thể nhận credentials khác Java SDK. Một phương pháp đáng tin cậy hơn là xác minh principal **ngay trong môi trường Java test với cùng provider** hoặc đối chiếu metadata/audit phía Vault khi IAM login thành công.

### 7.2. Java diagnostic dùng đúng provider

Đoạn minh họa dưới đây chỉ dành cho **test/diagnostic**; nó chủ động gọi AWS STS `GetCallerIdentity` từ chính tiến trình Java (khác với flow Vault IAM bình thường, nơi Vault server gửi signed request tới STS):

~~~java
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;

public final class CheckWorkloadIdentity {

    public static void main(String[] args) {
        AwsCredentialsProvider provider = DefaultCredentialsProvider.create();
        try (StsClient sts = StsClient.builder()
                .credentialsProvider(provider)
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            var identity = sts.getCallerIdentity();
            // Chỉ xuất hiện trên console test có kiểm soát; không in credentials.
            System.out.println("AWS caller ARN: " + identity.arn());
        }
    }
}
~~~

Để chạy code này cần AWS SDK `sts` module tương thích và network tới STS từ tiến trình test. Việc client chẩn đoán gọi STS không chứng minh Vault IAM auth đã cấu hình đúng; bước tiếp theo vẫn phải login Vault với role thích hợp và thử policy âm tính. Nếu không được phép xuất ARN ra console, dùng kiểm tra assertion trên ARN rồi chỉ ghi kết quả pass/fail.

### 7.3. Tách metadata danh tính khỏi dữ liệu bí mật

Những điều có thể kiểm chứng an toàn hơn việc log raw key:

- AWS account/role **dự kiến** theo manifest/IaC đã được duyệt.
- Vault auth role và policies gắn vào Vault token theo kiểm toán được kiểm soát.
- Việc đọc `secret/data/prod/orders/payment` thành công trong khi path của service khác trả 403.
- Login thất bại với AWS principal khác, dù principal đó có một số quyền AWS khác.

Đừng dựng một REST endpoint kiểu `/debug/aws-credentials` trả object `AwsCredentials`. Nếu cần debug, thực hiện qua công cụ vận hành được ủy quyền và tắt sau khi kiểm tra.

## 8. Vòng đời credentials: ba đồng hồ và hai cơ chế làm mới

~~~mermaid
flowchart TB
    A["AWS temporary credentials<br/>Expiration do AWS quyết định"] --> B["SigV4 request mới<br/>để IAM login Vault"]
    B --> C["Vault login token<br/>TTL theo Vault role"]
    C --> D["Vault API với ACL policy"]
    D --> E["KV secret tĩnh<br/>version do KV quản lý"]
    D --> F["Database credential động<br/>lease TTL riêng"]
    D --> G["Transit / PKI operations"]
~~~

| Đối tượng | Ai phát hành? | Ai làm mới/thu hồi? | Nếu hết hạn thì sao? |
|---|---|---|---|
| **AWS role session credentials** | AWS STS/runtime/provider | AWS provider refresh khi nguồn còn hợp lệ, AWS role/session lifecycle | Không ký được **login mới** khi credentials không còn hợp lệ |
| **STS request đã ký** | Spring Vault/SigV4 signer dùng AWS credentials | Tạo mới mỗi lần login cần thiết | Timestamp/signature cũ không dùng vô hạn; cần tạo request mới |
| **Vault login token** | Vault auth/token subsystem | `SessionManager` có thể renew/re-login theo cấu hình và token type | Vault API có thể từ chối token expired/revoked |
| **API key trong KV v2** | Nhà phát hành key và KV lưu lại | Secret owner + app refresh; revoke tại nhà phát hành | Key có thể bị nhà phát hành từ chối ngay cả khi KV vẫn đọc được |
| **Database dynamic secret** | Vault Database engine/DB backend | Lease renew/reissue/revoke theo policy; app thay pool | DB có thể không chấp nhận credential cũ |

### 8.1. Khi AWS credentials hết hạn nhưng Vault token còn hiệu lực

Nếu `SessionManager` đã có Vault token hợp lệ, app có thể tiếp tục gọi Vault bằng token đó mà **không cần ký lại STS request ngay**. Nhưng khi token cần re-login, provider phải cung cấp **AWS credentials hợp lệ**. Do đó:

- Không cache bộ temporary AWS credentials cố định suốt đời JVM.
- Không nhầm việc token Vault được renew với việc role session AWS được gia hạn.
- Xác minh provider có thể lấy credentials mới từ agent/metadata/STS, tránh phụ thuộc credentials được injected thủ công với TTL đã qua.
- Với EKS IRSA, bảo đảm projected token, IAM/OIDC trust và đường tới STS cho `AssumeRoleWithWebIdentity`.
- Với ECS/EKS Pod Identity, bảo đảm agent/credentials endpoint hoạt động và không bị source ưu tiên cao hơn che mất.

### 8.2. Token Vault khác secret lease

Một Vault token còn hạn **không** làm database credential đã cấp trước đó tự tăng lease TTL. Nếu dùng `SecretLeaseContainer` của Spring Vault, phải đăng ký secret có lease và xử lý sự kiện renew/rotate đúng theo engine. Ứng dụng còn phải **thay connection pool** hoặc client đang dùng username/password; không giả định thông tin trong `Environment` tự cập nhật mọi bean.

Với Transit, việc rotate key versions không phải renew DB credential; với PKI, certificate có X.509 validity và cần reload TLS context trước hạn. Đọc KV thành công cũng không bảo đảm payment API key còn hợp lệ ở nhà cung cấp.

## 9. Các rủi ro bảo mật liên quan đến nguồn credentials

### 9.1. Role dùng chung quá nhiều workload

Nếu mười ECS tasks/EKS pods cùng dùng IAM role `SharedAppsRole` và Vault auth role cho phép `SharedAppsRole` đọc secret của tất cả service, một workload bị chiếm quyền có thể đọc secret của các workload khác. Vault IAM authentication chứng minh **AWS principal**, không chứng minh chính xác tên container hay nghiệp vụ đang chạy.

Giảm thiểu:

1. IAM role **riêng theo workload hoặc nhóm quyền đồng nhất**.
2. Vault auth role/policy riêng theo service, environment và key/operation.
3. Trust policy kiểm soát ai được assume role; không dùng wildcard rộng không cần thiết.
4. Quyền phía Vault chỉ `read` key cần dùng hoặc `update` Transit encrypt khi service chỉ mã hóa.
5. Negative test: một workload không đọc được key của workload khác.

### 9.2. Static credentials vô tình ghi đè temporary role credentials

JVM `-Daws.accessKeyId` và environment `AWS_ACCESS_KEY_ID` được xét **trước** container/provider IAM role. Điều này tạo **credential shadowing**:

- Source code/chạy test tưởng có role tối thiểu, nhưng build server inject access key có quyền rộng.
- Khi deploy lên ECS/EKS, image mang env cũ làm AWS principal sai với Vault role.
- Một test pass trên laptop bằng profile admin nhưng fail trong production vì workload role thiếu ràng buộc.

Kiểm tra image/deployment configuration, biến môi trường do CI cung cấp và JVM startup args mà không in giá trị bí mật. Đặt giám sát ở mức expected principal/role, không ghi raw credentials.

### 9.3. Truy cập credential endpoint từ workload không tin cậy

Trong EC2, IMDS access có thể bị lạm dụng qua SSRF hoặc tiến trình khác; trong container platforms, quyền truy cập agent/credentials endpoint và cách cô lập pod/task ảnh hưởng mức độ an toàn. Cấu hình IMDSv2, network restrictions, Linux process/container isolation và quyền của service accounts theo hướng dẫn nền tảng.

**Temporary không có nghĩa vô hại**: credential bị đánh cắp có thể dùng được đến hết TTL hoặc khi bị revoke, trong phạm vi IAM role. Ngăn credential exfiltration và giới hạn IAM permissions vẫn là yêu cầu bắt buộc.

### 9.4. Replay signed IAM login request

Khi Spring Vault ký STS `GetCallerIdentity` request, payload đã ký là một **login proof** có thể bị phát lại trong cửa sổ hợp lệ nếu lộ ra. Hãy:

- Sử dụng HTTPS tới Vault với kiểm tra CA/hostname.
- Cấu hình `iam_server_id_header_value` trên Vault và `serverId(...)` ở Spring Vault để ký header `X-Vault-AWS-IAM-Server-ID`.
- Dùng Server-ID khác nhau giữa các Vault deployments hoặc môi trường có ranh giới tin cậy khác nhau.
- Không log raw `iam_request_headers`, SigV4 `Authorization`, AWS session token hoặc Vault token.
- Giới hạn thời gian và phạm vi quyền của Vault token sau login.

Server-ID giảm khả năng **replay giữa các Vault deployments**; không thay thế least privilege hoặc ngăn attacker khi họ đã kiểm soát AWS role credentials để tự ký request mới.

## 10. Chẩn đoán theo lớp khi AWS IAM login hoặc đọc KV lỗi

| Biểu hiện | Khả năng cao | Bước kiểm tra an toàn |
|---|---|---|
| `Unable to load credentials from any of the providers` | Không có nguồn credentials hợp lệ trong SDK chain | Task/instance/pod role, env/system props, IRSA token file, profile/SSO, agent/IMDS |
| `ExpiredToken`, `InvalidClientTokenId` | Temporary credentials hết hạn hoặc thiếu session token | Provider refresh, nguồn AWS runtime, network STS, session credentials trọn bộ |
| Login ký được nhưng ARN không khớp role | Credentials được lấy từ **nguồn ưu tiên khác** | Kiểm tra principal thực trong process test, đối chiếu `bound_iam_principal_arn` |
| IRSA `AccessDenied` ở `AssumeRoleWithWebIdentity` | IAM role trust, OIDC issuer, `sub`/`aud`, service account hoặc STS | Kiểm tra trust policy và projected token; không in token OIDC |
| EKS Pod Identity không cấp credentials | Association/agent/SDK hoặc env ưu tiên cao hơn | Kiểm tra Pod Identity association, agent, container endpoint và provider chain |
| ECS task role không đúng | Task definition đang thiếu task role hoặc nhầm execution role | Kiểm tra `taskRoleArn`, ECS metadata và ARN test |
| EC2 IMDS credentials không lấy được | Instance profile/IMDSv2/hop limit/network | Kiểm tra metadata options, process network/containers |
| SigV4 signature lỗi | Region, STS endpoint, Host, timestamp, credentials hoặc signed headers | Xác minh endpoint + Region khớp và đồng hồ chính xác |
| Vault server không gọi được STS | Egress/proxy/DNS/VPC endpoint phía Vault | SRE/Vault Ops kiểm tra mạng từ Vault tới AWS STS |
| Vault IAM login bị từ chối dù STS hợp lệ | Vault auth role, bound ARN, AWS unique ID, Server-ID | Vault Ops kiểm tra role binding và audit theo metadata an toàn |
| Vault login thành công, KV trả `403` | Vault token ACL thiếu `read` trên KV v2 API path | Đối chiếu `secret/data/prod/orders/payment` và token policies |
| KV trả `404` hoặc field thiếu | Sai mount, key, backend KV v1/v2, secret bị xóa | Xác minh key logic và schema dữ liệu |
| App tiếp tục dùng API key cũ | Refresh/cache chưa đồng bộ | Kiểm tra rotation KV và HTTP client/downstream |

### 10.1. Một quy trình chẩn đoán theo thứ tự

~~~text
1. Workload có IAM role/trust policy đúng không?
2. AWS SDK v2 thực sự chọn provider nào trong process Java?
3. AWS credentials còn hiệu lực và là của ARN dự kiến không?
4. Với IRSA/Pod Identity, bước cấp temporary credentials có hoạt động không?
5. STS endpoint/Region/TLS/time sync có đúng không?
6. Signed request và Server-ID có khớp cấu hình auth/aws không?
7. Vault có xác minh được identity và bind vào Vault auth role không?
8. Vault login token đã được cấp đúng policies/TTL chưa?
9. ACL cho đúng secrets engine API path chưa?
10. Secret sau khi đọc đã được refresh và dùng đúng ở downstream chưa?
~~~

**Không sửa sai principal bằng cách nới Vault role thành wildcard; không sửa policy 403 bằng root token.** Kết quả debug phải phân biệt lỗi AWS credentials, Vault authentication, Vault authorization và lỗi sử dụng credential ở hệ thống đích.

## 11. Giám sát và vận hành an toàn

### 11.1. Các tín hiệu hữu ích

| Vị trí | Theo dõi | Không log |
|---|---|---|
| AWS workload/provider | Lỗi resolve/refresh credentials, thời điểm authentication failure, expected role được chọn | AWS secret access key, session token, web identity token |
| Spring Vault client | IAM login success/failure, lỗi renewal/re-login, latency tới Vault, 403/404/timeout | SigV4 Authorization header, login payload, Vault token, secret value |
| Vault server | Auth denials, role/policy mismatch, audit events, STS connectivity, token issuance health | Audit data ở nơi công khai hoặc thông tin bí mật không cần thiết |
| Secret consumer | Payment 401, DB login failure, connection pool rollover, TLS cert expiry | API key, DB password, private key, plaintext Transit |

Việc đặt tên metric label cũng là một quyết định bảo mật. Có thể dùng service/environment/error-class khi được cho phép, nhưng tránh giá trị credentials, token và những định danh nhạy cảm không cần thiết.

### 11.2. Ai chịu trách nhiệm với vấn đề nào?

- **Platform/Cloud team:** cấp IAM workload role, trust policy, container/metadata provider và network tới STS.
- **Vault Ops/Security:** auth/aws mount, bound principal ARN, unique ID handling, Server-ID, policies, token TTL, audit và network từ Vault tới STS.
- **App Dev:** cấu hình `DefaultCredentialsProvider`/Spring Vault theo SDK version, TLS, retry/timeout, sử dụng secret an toàn, rotation/cache, monitoring.
- **Secret owner:** phát hành/thu hồi key tại hệ thống đích hoặc quản trị policy vòng đời tương ứng.

Một IAM login thành công chỉ chứng minh danh tính và điều kiện Vault auth role. Nó không tự chứng minh Java không làm lộ secret, AWS role có đúng least privilege cho các AWS APIs khác, hay database credential đang được rotate hợp lệ.

## 12. Kiểm thử tích hợp trên môi trường AWS/Vault được ủy quyền

Unit test mock `VaultOperations` có thể kiểm tra logic xử lý field nhưng **không chứng minh** provider chain thật chọn đúng IAM role, trust policy cho phép assume role, STS xác minh SigV4, hay Vault áp đúng bound principal.

Chuẩn bị một môi trường **test cô lập**, với AWS IAM role và Vault test instance, KV v2 key giả, role/policy giới hạn. Không dùng credential production, root token hoặc secret thật trong test fixture.

| Case | Điều kiện | Kết quả cần xác minh |
|---|---|---|
| **Provider đúng trên EC2/ECS/EKS** | Workload role được cấp hợp lệ, không có env override | Java resolve credentials của principal dự kiến |
| **Precedence / shadowing** | Có thêm system properties hoặc env credentials trong môi trường test an toàn | Phát hiện việc đổi principal; Vault role không vô tình chấp nhận wildcard |
| **IRSA trust policy** | Pod đúng/sai ServiceAccount hoặc namespace | Chỉ đúng OIDC subject/audience assume được role |
| **EKS Pod Identity** | Association/agent/SDK phù hợp | Container credentials provider cấp role dự kiến |
| **ECS task role** | Task có task role và execution role riêng | IAM login dùng **task role** của ứng dụng |
| **AWS session expiration** | Temporary credentials được rotate theo cơ chế test | Provider lấy credentials mới khi cần login lại, không giữ snapshot hết hạn |
| **Vault IAM login happy path** | Bound ARN đúng, Server-ID đúng, STS kết nối được | Vault token có policies/TTL dự kiến |
| **Sai AWS principal** | Workload test dùng IAM role khác | Vault auth role từ chối login |
| **Sai Server-ID** | Signed header khác cấu hình Vault | Login bị từ chối, không leak signed request |
| **Sai STS Region/endpoint** | Signature và endpoint không nhất quán | Lỗi có kiểm soát, không nới quyền |
| **Vault không tới STS** | Tạo lỗi network trên Vault **test** | Retry hữu hạn/timeout rõ, không fallback credential admin |
| **KV v2 read** | Policy chỉ `read` tại `secret/data/prod/orders/payment` | `OrdersPaymentSecretReader` đọc được field giả |
| **Negative ACL** | Dùng cùng token đọc key service khác | Vault trả `403` |
| **Vault token revoked** | Revoke token thử nghiệm khi AWS role vẫn hợp lệ | Session xử lý renew/re-login hoặc fail theo thiết kế |
| **Audit/log/trace** | Ghi telemetry khi login/read/lỗi | Không có AWS credentials, signed request, Vault token hoặc API key |

### 12.1. Kịch bản end-to-end mẫu

~~~text
GIVEN:
  AWS test role OrdersRuntimeRole có trust policy cho đúng workload
  AWS SDK v2 trong Java dùng DefaultCredentialsProvider
  Vault test auth/aws role orders-iam bind đúng role ARN
  Signed Server-ID giữa Spring Vault và Vault trùng nhau
  KV v2 mount secret/, key prod/orders/payment chứa api-key giả
  Policy chỉ read tại secret/data/prod/orders/payment

WHEN:
  Spring Vault cần lấy token và đăng nhập bằng AWS IAM
THEN:
  Provider resolve AWS temporary credentials hợp lệ
  Spring Vault ký STS GetCallerIdentity và login Vault
  Vault kiểm tra ARN, cấp token có policy đúng

WHEN:
  OrdersPaymentSecretReader.readRequiredKey() được gọi
THEN:
  Ứng dụng đọc api-key giả qua KV v2, không trả key trong REST response
  Token không đọc được KV path ngoài scope

WHEN:
  AWS role thay đổi/temporary credentials hết hạn hoặc Vault token bị revoke
THEN:
  Hệ thống làm mới credentials và re-login nếu hợp lệ
  Hoặc từ chối thao tác có kiểm soát, không dùng root token
~~~

Nếu không thể dùng AWS STS thật, có thể mock provider hoặc client để kiểm thử cách Java xử lý lỗi. Ghi rõ đó là **unit/component test**; không tuyên bố đã kiểm chứng end-to-end IAM auth.

## 13. Bài tập tình huống

### Tình huống A — ECS task đã gắn role đúng nhưng Vault nhận principal khác

Task definition có `taskRoleArn` chuẩn, nhưng deployment injected `AWS_ACCESS_KEY_ID` và `AWS_SECRET_ACCESS_KEY` từ CI. Vì environment provider đứng trước container credentials provider, JVM có thể ký bằng credentials từ CI. Cách xử lý: bỏ nguồn override không cần thiết, xác minh principal của process test, giữ Vault role binding chặt; không tăng quyền Vault.

### Tình huống B — EKS IRSA đã được cấu hình nhưng `AssumeRoleWithWebIdentity` bị từ chối

Pod có `AWS_ROLE_ARN` và projected token, nhưng IAM role trust policy chỉ cho ServiceAccount ở namespace khác hoặc OIDC provider/audience sai. SDK không nhận được AWS credentials, vì thế không thể ký Vault IAM login. Sửa **trust policy/ServiceAccount binding** trước khi điều tra Vault ACL.

### Tình huống C — EKS Pod Identity không được chọn dù association đã tạo

Workload còn `AWS_WEB_IDENTITY_TOKEN_FILE`/`AWS_ROLE_ARN` của IRSA hoặc profile credentials có ưu tiên cao hơn container provider. SDK có thể chọn source đó thay vì Pod Identity. Di chuyển cần kiểm tra provider chain trong runtime, cập nhật/loại cấu hình cũ và thử lại IAM principal.

### Tình huống D — AWS role có quyền DynamoDB nhưng Vault KV trả 403

AWS permissions policy cho `dynamodb:Query`, Vault IAM login thành công, sau đó `kv.get(...)` trả 403. Quyền DynamoDB không cấp quyền Vault KV. Kiểm tra Vault token policy `read` tại `secret/data/prod/orders/payment` và path mà Java gửi.

### Tình huống E — AWS credentials đã rotate nhưng phiên Vault token vẫn chạy

AWS SDK provider có thể nhận temporary credentials mới, trong khi Vault token hiện tại vẫn hợp lệ và client tiếp tục đọc KV. Khi Vault token hết hạn hoặc cần re-login, Spring Vault sẽ cần một **signed request mới** với AWS credentials đang hợp lệ. Hãy kiểm tra cả hai vòng đời; không copy credentials snapshot cũ để ký mãi.

### Tình huống F — Hai ứng dụng cùng IAM role nhưng cần hai quyền Vault khác nhau

Vault AWS auth xác minh cùng principal nên không tự biết đó là `orders-api` hay `billing-job`. Tạo IAM roles **riêng** cho workload với trust policy tương ứng, và Vault auth roles/policies giới hạn từng path/operation; không dựa vào tên container tự khai báo để cấp quyền rộng.

## 14. Tổng kết

**Nguồn AWS credentials là một phần của ranh giới bảo mật Spring Vault.** Với cùng code Java và `DefaultCredentialsProvider`, danh tính thực tế phụ thuộc vào môi trường chạy và **thứ tự provider chain**. Trên cloud, nên cấp **temporary credentials theo workload identity** và kiểm tra principal thực tế; tránh static access keys trong source, image hoặc system properties/environment có thể vô tình ghi đè role dự kiến.

Để IAM authentication với Vault an toàn, cần đồng thời:

1. **AWS trust:** đúng workload được nhận/assume IAM role.
2. **AWS credentials provider:** JVM chọn đúng nguồn và có thể refresh temporary credentials.
3. **Vault AWS auth:** signed STS request chứng minh đúng principal, bound role ARN/Server-ID được cấu hình chặt.
4. **Vault ACL:** Vault token chỉ được thao tác đúng KV/Transit/PKI/Database path cần thiết.
5. **Ứng dụng Java:** dùng secret nội bộ, không rò token/credentials, xử lý renewal, lease, rotation và lỗi hợp lý.

### Câu hỏi tự kiểm tra

1. `DefaultCredentialsProvider` của AWS SDK Java v2 xét những nhóm nguồn nào theo thứ tự?
2. Vì sao env `AWS_ACCESS_KEY_ID` có thể khiến một ECS task **không dùng task role** đã được cấu hình?
3. Trong ECS, `taskRoleArn` và `executionRoleArn` khác nhau thế nào?
4. IRSA và EKS Pod Identity cấp credentials thông qua hai cơ chế SDK nào?
5. Vai trò của `AWS_WEB_IDENTITY_TOKEN_FILE` và `AWS_ROLE_ARN` trong IRSA là gì?
6. **Trust policy**, **permissions policy**, **Vault auth role** và **Vault ACL policy** quyết định bốn điều gì khác nhau?
7. Vì sao một IAM role có `s3:GetObject` không mặc nhiên có quyền đọc KV secret?
8. Khi Vault login thành công nhưng đọc KV v2 bị 403, đường dẫn ACL nào cần kiểm tra?
9. Vì sao nên truyền `AwsCredentialsProvider` vào Spring Vault thay vì giữ một temporary `AwsSessionCredentials` snapshot?
10. Khi Vault token còn hiệu lực nhưng AWS credentials đã hết hạn, request KV hiện tại và lần **re-login** sau có thể khác nhau thế nào?
11. Rủi ro gì xảy ra nếu các workload khác nhau cùng assume một AWS role được Vault bind với wildcard?
12. Những test nào phải có AWS STS và Vault thật, và test nào có thể chỉ mock provider?

## Tài liệu tham khảo chính thức

- [AWS SDK for Java 2.x — Default Credentials Provider Chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [AWS SDK for Java 2.x — DefaultCredentialsProvider Javadoc](https://sdk.amazonaws.com/java/api/latest/software/amazon/awssdk/auth/credentials/DefaultCredentialsProvider.html)
- [AWS SDK for Java 2.x — Troubleshooting Credentials](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/troubleshooting.html)
- [Amazon ECS — Task IAM Role](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/task-iam-roles.html)
- [Amazon EC2 — IAM Roles for EC2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html)
- [Amazon EKS — IAM Roles for Service Accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [Amazon EKS — Pod Identity and SDK Integration](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-minimum-sdk.html)
- [Amazon EKS — How Pod Identity Works](https://docs.aws.amazon.com/eks/latest/userguide/pod-id-how-it-works.html)
- [AWS — STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)
- [AWS — IAM Role Trust Policies](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_roles_terms-and-concepts.html)
- [Spring Vault — AWS IAM Authentication](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — AwsIamAuthenticationOptions Builder](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthenticationOptions.AwsIamAuthenticationOptionsBuilder.html)
- [Spring Vault — VaultTemplate](https://docs.spring.io/spring-vault/reference/vault/imperative-template.html)
- [Spring Cloud Vault — Authentication](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)
- [HashiCorp Vault — AWS Authentication](https://developer.hashicorp.com/vault/docs/auth/aws)
- [HashiCorp Vault — AWS Auth HTTP API](https://developer.hashicorp.com/vault/api-docs/auth/aws)
- [HashiCorp Vault — Vault ACL Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)

> **Giới hạn và tương thích phiên bản:** Code dùng Java API Spring Vault tương thích AWS SDK for Java v2 (ví dụ Spring Vault 4.1.x); các bản cũ có thể dùng SDK v1 và khác API. Nguồn credentials, thứ tự provider, EKS Pod Identity và IAM role behavior cũng phụ thuộc phiên bản AWS SDK/nền tảng. Tên role, account ID, URL và API key trong bài đều giả định. Khi triển khai thật, hãy đối chiếu dependency, trust policy, Vault AWS auth role và integration tests trong môi trường được cấp quyền trước khi phát hành production.
