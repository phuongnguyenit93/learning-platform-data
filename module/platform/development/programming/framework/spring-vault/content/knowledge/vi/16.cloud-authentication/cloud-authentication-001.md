# AWS IAM và yêu cầu ký để chứng minh danh tính

> **Chương:** Xác thực cloud  
> **Trong module Spring Vault:** Tìm hiểu cách ứng dụng Java sử dụng danh tính workload AWS để đăng nhập HashiCorp Vault bằng yêu cầu AWS Signature Version 4 (SigV4), nhận Vault token có policy giới hạn, rồi dùng `VaultTemplate`/`VaultOperations` truy cập secret. Bài tập trung vào **AWS IAM authentication**, không phải cách Vault phát hành AWS access key bằng AWS secrets engine.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích cơ chế chứng minh danh tính bằng yêu cầu AWS STS `GetCallerIdentity` **đã ký**, thay vì gửi AWS secret access key trực tiếp đến Vault.
2. Vẽ luồng: AWS credential provider → Spring Vault `AwsIamAuthentication` → Vault auth endpoint → AWS STS → Vault token → Vault policy → KV/Transit/PKI.
3. Phân biệt **AWS IAM role**, **Vault AWS auth role**, **Vault ACL policy**, **AWS session credentials** và **Vault login token**.
4. Thiết lập thử nghiệm an toàn gồm AWS workload role, cấu hình auth mount/role phía Vault, `X-Vault-AWS-IAM-Server-ID` và cấu hình Java/Spring Cloud Vault tương ứng.
5. Đọc secret KV v2 sau khi login bằng IAM, hiểu các API path và capability cần cấp.
6. Chẩn đoán lỗi AWS credentials, sai Region/STS endpoint, chữ ký SigV4, ARN binding, token TTL, policy 403 và TLS.
7. Thiết kế kiểm thử tích hợp và giám sát để giảm replay, credential exposure và cấp quyền quá rộng.

## 1. Tại sao ứng dụng Spring trên AWS cần IAM auth với Vault?

Một `orders-service` chạy trên Amazon ECS, EC2, Lambda hoặc EKS cần lấy API key thanh toán từ HashiCorp Vault. Có hai phương án:

- **Cách yếu:** chép một Vault root token hoặc token dùng chung vào image/`application.yml`, rồi để mọi instance dùng nó.
- **Cách phù hợp hơn:** ứng dụng sử dụng **danh tính AWS đã được nền tảng cấp** cho workload (chẳng hạn ECS task role hoặc EC2 instance profile role) để chứng minh mình là ai. Vault xác minh danh tính này và phát **Vault token ngắn hạn với policy quyền tối thiểu**.

AWS IAM auth giúp giảm nhu cầu phân phối **một bí mật Vault tĩnh ban đầu** cho từng instance. Nó **không loại bỏ mọi bí mật**: AWS credentials vẫn tồn tại tại runtime hoặc qua cơ chế cấp phát tạm thời, Vault token vẫn là bearer token phải bảo vệ, và những API key ứng dụng đọc về vẫn có thể bị lộ nếu bị log.

Ví dụ hợp đồng mong muốn:

| Đối tượng | Ví dụ giả định | Vai trò |
|---|---|---|
| AWS account | `123456789012` | Tài khoản sở hữu IAM role của workload |
| AWS IAM role | `arn:aws:iam::123456789012:role/OrdersRuntimeRole` | Danh tính mà `orders-service` đang sử dụng để ký yêu cầu |
| Vault auth mount | `auth/aws` | Nơi Vault tiếp nhận IAM login |
| Vault AWS auth role | `orders-iam` | Ràng buộc các AWS principal được phép login |
| Vault ACL policy | `orders-payment-read` | Chỉ cho đọc key KV đã quy định |
| KV v2 mount | `secret/` | Nơi đặt secret tĩnh |
| KV key logic | `prod/orders/payment` | Đường dẫn dữ liệu nghiệp vụ |

**Cần phân biệt hai chữ “role”:** `OrdersRuntimeRole` được tạo trong **AWS IAM**; `orders-iam` được tạo trong **Vault auth/aws** để ánh xạ AWS principal đến một tập Vault policies. Chúng không tự sinh ra nhau và không bắt buộc trùng tên.

## 2. Ba lớp danh tính và quyền truy cập

| Lớp | Dùng chứng từ nào? | Ai kiểm tra? | Quyền nằm ở đâu? |
|---|---|---|---|
| **AWS identity** | AWS access key ID + secret access key, thường kèm session token tạm thời; SDK có thể lấy từ AWS runtime | AWS STS xác minh chữ ký và trả danh tính caller | AWS IAM trust relationship/policies quyết định role được cấp và các quyền AWS khác |
| **Vault login** | Yêu cầu `GetCallerIdentity` được ký SigV4, đóng gói gửi vào `auth/aws/login` | Vault dùng STS để xác minh rồi so với Vault auth role | `bound_iam_principal_arn` và các ràng buộc của role |
| **Vault secrets access** | Vault token nhận sau khi login thành công | Vault server kiểm tra mỗi API request | ACL policy trên path/capability, ví dụ `read` tại `secret/data/...` |

Đừng nhầm:

1. **AWS session token** (trong bộ AWS credentials tạm thời) là một phần thông tin AWS dùng để xác minh quyền ký request; nó không phải Vault token.
2. **Vault token** được Vault phát hành sau login, dùng ở `X-Vault-Token` trên những API request tiếp theo; nó không dùng để gọi AWS STS như AWS credentials.
3. **Vault policy** không tự cấp quyền AWS `s3:GetObject` hoặc `dynamodb:Query`. Ngược lại, một IAM role có quyền truy cập S3 không mặc nhiên được quyền đọc mọi KV path trong Vault.
4. **Spring Security user JWT** (nếu service có REST API) là chứng từ xác thực người dùng đầu cuối, không tự được dùng làm Vault token hay AWS IAM credentials.

### Ví dụ tách trách nhiệm

Người dùng gọi REST endpoint thanh toán bằng JWT → Spring Security kiểm tra quyền người dùng → business service sử dụng `VaultOperations` với Vault token của **orders-service** → Vault policy chỉ cho đọc API key → orders-service gọi đối tác thanh toán. Vault thấy danh tính workload đã login, không tự đánh giá người dùng có sở hữu đơn hàng hay không.

## 3. SigV4: vì sao ký một yêu cầu STS lại chứng minh được danh tính?

### 3.1. Khái niệm yêu cầu được ký

AWS Signature Version 4 tạo chữ ký dựa trên nhiều thành phần của HTTP request, trong đó có HTTP method, canonical URI/query, các headers được ký, hash của payload, thời gian, service và Region. Việc tạo chữ ký yêu cầu khả năng truy cập **secret access key** tương ứng với AWS credential.

Trong Vault AWS IAM authentication, client **chuẩn bị nhưng không tự gửi trực tiếp yêu cầu STS**:

1. Tạo HTTP request tới AWS STS cho action `GetCallerIdentity`.
2. Ký request đó bằng AWS SigV4, thường với credential tạm thời do AWS workload role cấp.
3. Đóng gói **method, URL, body, headers** của request đã ký trong body login gửi tới Vault.
4. Vault kiểm tra cấu trúc/ràng buộc request rồi **gửi yêu cầu STS đã ký tới AWS**.
5. STS xác minh chữ ký và trả danh tính AWS caller (Account/Arn/UserId); Vault đối chiếu với role được cấu hình.
6. Nếu phù hợp, Vault cấp token gắn policies/TTL; client sử dụng token đó để gọi Vault API.

**AWS secret access key không được gửi trực tiếp đến Vault trong IAM login.** Tuy nhiên, request đã ký là **bằng chứng có thể bị lợi dụng nếu bị đánh cắp trong cửa sổ hiệu lực**, vì vậy vẫn phải bảo vệ TLS, nội dung request, logs và chống replay.

### 3.2. Sơ đồ sequence

~~~mermaid
sequenceDiagram
    autonumber
    participant W as Spring Boot workload
    participant A as AWS credential provider
    participant S as Spring Vault AwsIamAuthentication
    participant V as Vault auth/aws
    participant T as AWS STS
    participant K as Vault KV v2 + ACL

    W->>S: Yêu cầu xác thực Vault
    S->>A: Lấy AWS credentials hiện hành
    A-->>S: Access key ID + secret key + session token (nếu có)
    S->>S: Tạo POST GetCallerIdentity<br/>ký AWS SigV4 + Server-ID
    S->>V: POST /v1/auth/aws/login<br/>role + signed STS request
    V->>T: Gửi request STS đã ký tới AWS
    T-->>V: Caller identity: Account, Arn, UserId
    V->>V: Kiểm tra IAM principal binding<br/>và cấu hình Vault role
    alt Principal hợp lệ
        V-->>S: Vault token + policies + TTL
        S-->>W: Vault login token
        W->>K: GET /v1/secret/data/prod/orders/payment<br/>X-Vault-Token
        K-->>W: Secret hoặc 403/404 theo policy
    else Principal không hợp lệ hoặc chữ ký lỗi
        V-->>S: Login bị từ chối
    end
~~~

**Điểm mạng thường bị hiểu sai:** client Java cần liên lạc với Vault và nguồn AWS credentials của workload; trong flow IAM này, **Vault server cần có đường mạng đến AWS STS** vì Vault là bên gửi signed request đi xác minh. Client không bắt buộc trực tiếp gọi STS cho hành động `GetCallerIdentity` qua luồng xác thực này. Nếu STS bị chặn ở mạng của Vault, login vẫn thất bại dù pod kết nối được tới Vault.

### 3.3. SigV4 bảo vệ những phần nào?

| Thành phần của STS request | Tác dụng |
|---|---|
| HTTP method | Gắn chữ ký với thao tác; flow IAM này sử dụng POST |
| URL/Host STS | Gắn chữ ký với endpoint AWS STS được chọn |
| Body action/version | Chỉ định `Action=GetCallerIdentity&Version=2011-06-15` |
| `Authorization` SigV4 | Chứa thông tin credential scope, danh sách signed headers và chữ ký; **không phải** AWS secret key |
| `X-Amz-Date` | Gắn timestamp vào yêu cầu đã ký |
| `X-Amz-Security-Token` | Có mặt khi dùng AWS temporary session credentials |
| `X-Vault-AWS-IAM-Server-ID` | Header bổ sung được **ký**, giúp ràng buộc signed request với Vault server dự kiến |

Ở phía AWS STS, `GetCallerIdentity` trả thông tin về caller mà chữ ký xác nhận. Vault dùng identity đó để kiểm tra **ai là người ký**, không chỉ tin vào một chuỗi ARN do client tự khai báo.

## 4. Payload IAM login: bốn trường được ký, không phải AWS password

Vault nhận login tại endpoint mặc định:

~~~text
POST https://vault.internal.example:8200/v1/auth/aws/login
Content-Type: application/json
~~~

Body khái niệm:

~~~json
{
  "role": "orders-iam",
  "iam_http_request_method": "POST",
  "iam_request_url": "<BASE64_URL_STS_DA_KY>",
  "iam_request_body": "<BASE64_BODY_GET_CALLER_IDENTITY>",
  "iam_request_headers": "<BASE64_JSON_CAC_HEADER_DA_KY>"
}
~~~

Các chuỗi trong dấu ngoặc là **placeholder**, không phải payload có thể gửi để login. Thư viện Spring Vault/AWS SDK sẽ tạo và ký dữ liệu thật tại runtime. Khi sử dụng API trực tiếp, phải bảo đảm từng trường phản ánh **chính xác request đã ký**, vì thay header/body sau khi ký có thể làm chữ ký không hợp lệ.

| Trường login | Ý nghĩa |
|---|---|
| `role` | Tên Vault auth role sẽ dùng để đối chiếu IAM principal và phát policies |
| `iam_http_request_method` | Method của signed STS request, thông thường `POST` |
| `iam_request_url` | URL của STS request, được Base64 hóa để đóng gói |
| `iam_request_body` | Body chứa hành động `GetCallerIdentity`, Base64 hóa |
| `iam_request_headers` | Headers của request đã ký (định dạng mà Vault API chấp nhận), bao gồm SigV4 header |

**Base64 là cách biểu diễn byte, không phải mã hóa bảo mật.** Nếu log toàn bộ login payload thì attacker có thể lấy bằng chứng đã ký còn hiệu lực; không cho payload xuất hiện trong application logs, HTTP traces, exception details hay hệ thống theo dõi có quyền truy cập rộng.

Lưu ý: những trường này mô tả **signed request gửi cho STS**, không phải yêu cầu đọc `secret/data/...`. Sau khi login, client gửi **Vault token** trong các Vault API request bình thường; không cần ký mọi lần đọc KV bằng AWS SigV4.

## 5. Chống replay bằng `X-Vault-AWS-IAM-Server-ID`

### 5.1. Replay là gì?

Giả sử attacker sao chép được signed `GetCallerIdentity` request do một workload hợp lệ gửi để login. AWS SigV4 kiểm tra thời gian nên request không dùng được vô hạn, nhưng trong **cửa sổ còn hiệu lực**, một bản sao vẫn có thể bị thử gửi lại.

Nếu hai Vault deployments cùng chấp nhận một AWS principal và không phân biệt signed request dành cho đâu, attacker có thể thử **phát lại login request lấy từ môi trường dev sang Vault prod**. Đây là một trong những mối đe dọa mà Vault hỗ trợ giảm thiểu.

### 5.2. Gắn signed request với một Vault server dự kiến

Đội Vault Ops cấu hình:

~~~bash
# Chỉ dành cho người quản trị và môi trường được ủy quyền.
# Giá trị phải khớp chính xác ở phía client.
vault write auth/aws/config/client \
  iam_server_id_header_value="vault.internal.example"
~~~

Spring Vault cấu hình `serverId("vault.internal.example")`. Client thêm `X-Vault-AWS-IAM-Server-ID` vào signed STS request; header phải có mặt trong **SignedHeaders** được AWS kiểm tra. Khi login, Vault yêu cầu giá trị header trùng với cấu hình trên.

Điểm cần nhớ:

- Header này **không phải** một mật khẩu và **không thay thế** TLS hoặc Vault ACL policies.
- Phải được đưa vào phần **được ký**, chứ không chỉ gắn một header tùy ý sau khi ký.
- Tên server thường dùng DNS công bố của Vault, nhưng điều kiện thực sự là **giá trị cấu hình Vault và client phải giống nhau**.
- Dev/test/prod nên có giá trị riêng để hạn chế khả năng phát lại giữa môi trường.
- Cửa sổ thời gian SigV4, bảo vệ endpoint TLS, không log signed payload và least-privilege IAM/Vault roles là những lớp bảo vệ bổ sung; không một biện pháp đơn lẻ là tuyệt đối.

~~~mermaid
flowchart TB
    R["Signed STS request<br/>từ workload dev"] --> DEV["Vault dev<br/>Server-ID = vault-dev.example"]
    R -. "Replay sang prod" .-> PROD["Vault prod<br/>Server-ID = vault-prod.example"]
    DEV --> OK["Giá trị khớp<br/>và signature hợp lệ"]
    PROD --> NO["Server-ID không khớp<br/>login bị từ chối"]
~~~

Không sử dụng cùng một server ID cho mọi Vault deployment chỉ vì muốn đơn giản hóa cấu hình.

## 6. Điều kiện cần có ở phía AWS

### 6.1. Cấp danh tính cho workload, không hard-code AWS key

AWS SDK có thể nhận credentials qua một `AwsCredentialsProvider`, thường là chuỗi nguồn mặc định của SDK. Tùy nền tảng:

| Nơi chạy | Nguồn danh tính thường dùng | Ghi chú bảo mật |
|---|---|---|
| EC2 | Instance profile gắn IAM role | Hạn chế quyền truy cập instance metadata; vận hành IMDSv2 theo chính sách |
| ECS/Fargate | ECS task role, container credential endpoint | Phân biệt **task role** cho app với **task execution role** của hạ tầng |
| Lambda | Execution role cung cấp temporary credentials | Không nhúng static access keys vào deployment package |
| EKS | IRSA (web identity) hoặc EKS Pod Identity tùy cluster | Service account/pod phải được gắn đúng AWS role, SDK lấy temporary credentials theo cơ chế tương ứng |
| Laptop/test | AWS profile/SSO hoặc assumed role thử nghiệm | Dùng account/role test; xác nhận role hiện tại, tránh dùng credential admin |

Với EKS, đừng đồng nhất **AWS IAM auth của Vault** với **Vault Kubernetes auth**. Một pod EKS có thể đăng nhập Vault bằng signed AWS STS request nếu nó có AWS role phù hợp; hoặc dùng Kubernetes ServiceAccount JWT qua auth method `kubernetes` của Vault. Đây là hai đường xác thực khác nhau.

Trong production, nên ưu tiên **temporary AWS credentials** do AWS workload identity cấp. `DefaultCredentialsProvider` rất tiện, nhưng cũng có thể chọn environment variables, shared profile hoặc nguồn khác theo thứ tự ưu tiên SDK: nếu image/pod vô tình chứa credentials mạnh hơn ở một nguồn ưu tiên cao, ứng dụng có thể ký bằng **principal ngoài dự kiến**. Cần kiểm tra ARN thực tế của workload ở môi trường test, không suy từ tên role trong code.

### 6.2. Không nhầm IAM permissions với Vault ACL

AWS IAM policies/trust policies quyết định role nào có thể được assume và AWS APIs nào role có thể gọi. Vault role binding quyết định **AWS principal nào được login**. Vault ACL policies quyết định **Vault paths nào token được phép thao tác sau login**.

Đặc biệt, cơ chế `sts:GetCallerIdentity` dùng để xác thực caller không đồng nghĩa workload cần quyền quản trị IAM hoặc quyền đọc mọi tài nguyên AWS. Tổ chức phải kiểm soát trust relationship của role, vì nếu attacker chiếm được khả năng assume role, họ có thể tạo signed request để đăng nhập Vault trong phạm vi role binding.

### 6.3. Kiểm tra ARN principal

Khi một AWS role được assume, STS có thể trả ARN dạng:

~~~text
arn:aws:sts::123456789012:assumed-role/OrdersRuntimeRole/<session-name>
~~~

Trong cấu hình Vault, bạn thường bind bằng **IAM role ARN chuẩn**:

~~~text
arn:aws:iam::123456789012:role/OrdersRuntimeRole
~~~

Vault AWS auth hiểu danh tính role/assumed-role theo cơ chế của nó. Đừng tùy ý hard-code một session ARN có tên session thay đổi mỗi lần deployment. Với role nằm trong IAM path đặc biệt, wildcard hoặc cross-account, cần đối chiếu đúng semantics ARN/unique ID của bản Vault triển khai.

## 7. Thiết lập phía Vault: auth mount, role, policy, Server-ID

Phần này là **lệnh mẫu cho đội quản trị trên Vault test/được ủy quyền**, không phải thứ mà business application tự làm lúc khởi động. Giả sử:

- AWS IAM principal của `orders-service` là `arn:aws:iam::123456789012:role/OrdersRuntimeRole`.
- Vault public DNS name là `vault.internal.example`.
- Auth mount là `aws`, KV v2 mount là `secret`.
- Dữ liệu cần đọc là KV key `prod/orders/payment`, chỉ có field `api-key`.

### 7.1. Bật auth method và cấu hình server ID

~~~bash
# Chạy một lần bởi Vault operator khi auth/aws chưa tồn tại.
vault auth enable -path=aws aws

# Bật ràng buộc signed request với Vault server dự kiến.
vault write auth/aws/config/client \
  iam_server_id_header_value="vault.internal.example"
~~~

Nếu auth method đã được mount ở path khác, ví dụ `aws-prod`, endpoint login là `auth/aws-prod/login` và Spring Vault phải khai báo `.path("aws-prod")`. Không được nhầm path **auth mount** với path **KV secrets engine**.

### 7.2. Policy tối thiểu để đọc KV v2

Ví dụ nội dung file policy `orders-payment-read.hcl` được kiểm soát bởi đội vận hành:

~~~hcl
# secret/ là KV v2 mount; data/ nằm trong Vault ACL API path.
path "secret/data/prod/orders/payment" {
  capabilities = ["read"]
}
~~~

Áp policy thông qua công cụ quản trị Vault:

~~~bash
vault policy write orders-payment-read orders-payment-read.hcl
~~~

Ví dụ chỉ đọc **một key**, không cấp `list` toàn bộ Vault, không cho ghi/xóa secret, không cấp `transit/decrypt` hoặc `sys/*`.

### 7.3. Gắn AWS IAM principal vào Vault role

~~~bash
vault write auth/aws/role/orders-iam \
  auth_type=iam \
  bound_iam_principal_arn="arn:aws:iam::123456789012:role/OrdersRuntimeRole" \
  token_policies="orders-payment-read" \
  token_ttl="20m" \
  token_max_ttl="1h"
~~~

Ý nghĩa:

| Tùy chọn Vault role | Mục đích |
|---|---|
| `auth_type=iam` | Chấp nhận IAM signed STS requests, **không** phải auth type `ec2` |
| `bound_iam_principal_arn` | Danh sách AWS IAM principal được phép login bằng role này |
| `token_policies` | Policies gắn vào Vault token sau login |
| `token_ttl` | TTL tăng theo từng lần cấp/renew token trong giới hạn tương ứng |
| `token_max_ttl` | Trần thời gian hiệu lực cho token theo cấu hình |

Để giảm cấp quyền quá rộng, bind **ARN cụ thể**, tránh wildcard kiểu `arn:aws:iam::123456789012:*` khi không có yêu cầu bảo mật đã đánh giá. Đặt role riêng cho môi trường prod/test và từng workload cần phân quyền khác nhau.

**Lưu ý quan trọng về AWS unique ID:** Ở những phiên bản Vault hỗ trợ, `resolve_aws_unique_ids` cho role IAM thường mặc định bật; Vault có thể cần quyền/khả năng gọi `iam:GetRole` hoặc `iam:GetUser` **khi cấu hình hoặc cập nhật role** để ánh xạ ARN sang unique ID. Điều này giúp tránh việc role bị xóa rồi tạo lại cùng tên tự động thừa hưởng quyền. Nếu gặp lỗi tạo role do không resolve được ID, giải quyết quyền/trust hoặc cấu hình AWS phù hợp; **không tùy tiện tắt kiểm tra unique ID** để vượt lỗi.

**Đường mạng của Vault:** Vault phải gửi signed `GetCallerIdentity` tới AWS STS endpoint thích hợp và nhận response. Nếu Vault hoạt động trong mạng riêng, cần egress/proxy/VPC endpoint hoặc cấu hình tương ứng đã được kiểm thử. Nếu có thêm kiểm tra IAM role metadata, quyền AWS cần thiết ở phía Vault phụ thuộc cấu hình auth method.

## 8. Spring Vault Java: cấu hình `AwsIamAuthentication`

### 8.1. Thành phần cần thiết

Trong ứng dụng Spring Boot:

- Spring Vault client, ví dụ dependency `org.springframework.vault:spring-vault-core` với phiên bản tương thích.
- AWS SDK for Java để cung cấp credentials và ký SigV4. Với **Spring Vault 4.1.x**, API Javadoc của `AwsIamAuthenticationOptions` dùng AWS SDK **v2** (`software.amazon.awssdk.auth.credentials.AwsCredentialsProvider`); dependency liên quan là `software.amazon.awssdk:auth` (quản lý version bằng BOM phù hợp).
- Vault endpoint HTTPS với CA trust, hostname verification và connect/read timeouts.
- IAM principal runtime đã được cấp qua EC2/ECS/Lambda/EKS hoặc cơ chế AWS phù hợp.
- Auth mount/role và Vault policy đã được tạo **trên Vault server**.

**Chú ý phiên bản:** Một số ví dụ tài liệu lịch sử của Spring Vault sử dụng class AWS SDK v1 như `BasicAWSCredentials` hoặc `InstanceProfileCredentialsProvider`. Không trộn chúng vào code dựa trên Java API của Spring Vault 4.1.x dùng AWS SDK v2. Chọn dependency và API theo đúng version dự án.

### 8.2. Cấu hình Spring Vault theo AWS role

Ví dụ dưới đây minh họa Spring Vault 4.1.x và AWS SDK v2. Các DNS và role name là giả:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Configuration;
import org.springframework.vault.authentication.AwsIamAuthentication;
import org.springframework.vault.authentication.AwsIamAuthenticationOptions;
import org.springframework.vault.authentication.ClientAuthentication;
import org.springframework.vault.client.VaultEndpoint;
import org.springframework.vault.config.AbstractVaultConfiguration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;

@Configuration
public class AwsIamVaultConfiguration extends AbstractVaultConfiguration {

    @Override
    public VaultEndpoint vaultEndpoint() {
        return VaultEndpoint.from(
            URI.create("https://vault.internal.example:8200"));
    }

    @Override
    public ClientAuthentication clientAuthentication() {
        AwsIamAuthenticationOptions options =
            AwsIamAuthenticationOptions.builder()
                .path("aws")                   // Vault auth mount
                .role("orders-iam")             // Vault auth role
                .serverId("vault.internal.example")
                .credentialsProvider(DefaultCredentialsProvider.create())
                .region(Region.AP_SOUTHEAST_1) // Khớp Region của STS
                .endpointUri(URI.create(
                    "https://sts.ap-southeast-1.amazonaws.com/"))
                .build();

        return new AwsIamAuthentication(options, vaultClient());
    }
}
~~~

Các giá trị phải ăn khớp:

- `.path("aws")` tương ứng `auth/aws/login` phía Vault, **không** tương ứng mount KV `secret`.
- `.role("orders-iam")` là **Vault AWS auth role** đã bind AWS principal.
- `.serverId("vault.internal.example")` phải khớp `iam_server_id_header_value` của Vault và được ký cùng STS request.
- `DefaultCredentialsProvider` lấy AWS credentials theo cơ chế AWS SDK; không tạo sẵn một IAM role. Khi test, xác minh provider trả đúng principal.
- `.region(...)` là vùng dùng để tạo **SigV4 signature**; `.endpointUri(...)` trong ví dụ trỏ tới STS của cùng Region. Region, endpoint URI và cấu hình phía Vault phải tương thích; không chọn ngẫu nhiên hoặc trộn endpoint global với Region không phù hợp.
- `vaultClient()` là client HTTP do `AbstractVaultConfiguration` cung cấp theo cách cấu hình. TLS trust và timeouts phải được kiểm soát trong cấu hình client thực tế.

**Không gọi `clientAuthentication().login()` từ controller mỗi lần có request người dùng.** Session manager của Spring Vault thực hiện việc cung cấp token/renewal/re-login theo cấu hình và loại token. Một IAM login thành công không có nghĩa mọi secrets engine đều được quyền truy cập; từng request vẫn chịu Vault policy.

### 8.3. Sử dụng `VaultOperations` sau khi IAM login

Giả sử KV v2 mount `secret/`, key logic `prod/orders/payment` chứa `api-key`:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.vault.core.VaultKeyValueOperations;
import org.springframework.vault.core.VaultKeyValueOperationsSupport.KeyValueBackend;
import org.springframework.vault.core.VaultOperations;
import org.springframework.vault.support.VaultResponse;

@Service
public class OrdersPaymentSecretReader {

    private final VaultKeyValueOperations kv;

    public OrdersPaymentSecretReader(VaultOperations vault) {
        this.kv = vault.opsForKeyValue("secret", KeyValueBackend.KV_2);
    }

    public String requiredPaymentKey() {
        VaultResponse response = kv.get("prod/orders/payment");
        if (response == null) {
            throw new IllegalStateException("Payment secret is unavailable");
        }
        Object value = response.getRequiredData().get("api-key");
        if (!(value instanceof String key) || key.isBlank()) {
            throw new IllegalStateException("Payment secret field is missing");
        }
        return key;
    }
}
~~~

Đường đi thực tế:

~~~text
Java:        kv.get("prod/orders/payment")
HTTP:        GET /v1/secret/data/prod/orders/payment
ACL policy:  secret/data/prod/orders/payment
Capability:  read
~~~

API KV của Spring Vault nhận **key logic**; đoạn `data/` được xử lý theo KV v2. Policy path không có `/v1/`. Không ghi `VaultResponse` hoặc `api-key` vào log hay trả key về cho frontend.

## 9. Spring Cloud Vault: cùng cơ chế AWS IAM, cách cấu hình khác

Nếu ứng dụng chủ yếu cần **nạp secret như property khi khởi động**, Spring Cloud Vault có thể khai báo AWS IAM authentication và Config Data import:

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

Điều kiện:

1. Có dependency Spring Cloud Vault và AWS SDK tương thích, không chỉ có Spring Security.
2. Đã cấu hình contexts/mounts mà Spring Cloud Vault thực sự đọc; `spring.application.name` và profile có thể ảnh hưởng key paths. Ví dụ không ngụ ý nó tự đọc `prod/orders/payment` nếu chưa được cấu hình đúng context.
3. Cơ chế AWS credentials/runtime, Vault server ID, ARN binding, TLS và policies vẫn phải khớp.
4. `Environment` và bean đã bind secret có thể giữ giá trị cũ sau rotation; Spring Cloud Vault không tự đảm bảo mọi HTTP client/database pool thay secret đồng thời.

**Phân biệt `spring.cloud.vault.aws-iam.*` với `spring.cloud.vault.aws.*`:** nhóm `aws-iam` dùng **đăng nhập Vault** bằng AWS IAM; cấu hình AWS **secrets backend** là bài toán khác, dùng Vault phát hành AWS credentials. Hai cơ chế có thể cùng dùng trong một hệ thống, nhưng không phải cùng endpoint hay cùng vòng đời.

## 10. AWS IAM auth và AWS-EC2 auth không phải một

Trong cùng auth method `aws` của Vault có hai loại chính:

| Tiêu chí | `auth_type=iam` | `auth_type=ec2` |
|---|---|---|
| Bằng chứng | Signed STS `GetCallerIdentity` bằng AWS SigV4 | Instance identity document của EC2 và chữ ký AWS phù hợp |
| Danh tính chủ yếu | IAM user hoặc IAM role/assumed role | EC2 instance/AMI và các ràng buộc EC2 |
| Môi trường | EC2, ECS, Lambda, EKS và workload khác có AWS credentials | EC2 |
| Vault role binding | Thường `bound_iam_principal_arn` | Các điều kiện EC2 như AMI, instance profile, instance ID... tùy role |
| Chống replay | Timestamp SigV4 + signed Server-ID và các lớp bảo vệ khác | Nonce/TOFU và các cơ chế cho instance identity |
| Spring Vault class | `AwsIamAuthentication` | `AwsEc2Authentication` |

Một Vault role có `auth_type=ec2` không thể được dùng như role IAM chỉ bằng cách đổi tên. Trong môi trường EC2 bạn có thể chọn một trong hai theo nhu cầu kiểm tra principal hay instance; với Lambda/ECS thường IAM auth phù hợp hơn khi có role identity.

AWS IAM authentication không tự chứng minh ứng dụng chạy từ **một pod hoặc một máy duy nhất**: nó chứng minh **khả năng ký bằng credential của AWS principal**. Nếu nhiều workloads cùng assume một IAM role, chúng có thể cùng thỏa role binding của Vault. Muốn tách quyền, hãy cấp IAM roles và Vault roles riêng, đồng thời giới hạn trust relationships.

## 11. Ba loại thời hạn không được gộp làm một

~~~mermaid
flowchart LR
    A["AWS temporary credentials<br/>có hạn theo AWS STS/session"] --> B["Ký login request SigV4<br/>có timestamp"]
    B --> C["Vault login token<br/>TTL theo Vault auth role"]
    C --> D["Đọc KV / gọi Transit / PKI"]
    D --> E["Secret động của engine<br/>có lease riêng nếu được cấp"]
~~~

| Thứ có vòng đời | Ai cấp/thu hồi? | Hết hạn ảnh hưởng gì? |
|---|---|---|
| **AWS temporary credentials** | AWS runtime/STS theo role/trust | Không ký được IAM login mới nếu provider không lấy được credentials hợp lệ |
| **Signed IAM login request** | AWS SDK tạo SigV4 tại thời điểm login | Không dùng được sau cửa sổ hợp lệ; không được cache như token vĩnh viễn |
| **Vault token** | Vault auth/token subsystem theo role | Không thể gọi Vault API khi token hết hạn/bị revoke; cần renew hoặc login lại khi đủ điều kiện |
| **KV secret tĩnh** | Secret owner/hệ thống phát hành rồi lưu tại KV | API key có thể bị revoke ở phía nhà phát hành, không theo TTL Vault token |
| **Dynamic database credential** | Database secrets engine theo lease | DB username/password có thể không còn được chấp nhận; cần thay pool/kết nối |
| **PKI certificate** | Vault PKI/CA theo X.509 validity | Cần cấp lại/nạp vào TLS context trước khi hết hạn |

`LifecycleAwareSessionManager` có thể gia hạn hoặc đăng nhập lại khi Vault token đủ điều kiện theo cấu hình. Nếu AWS temporary credentials không còn được provider cấp nữa, một lần **re-login** sau TTL cũng có thể thất bại; ứng dụng không được trông chờ token cũ tồn tại mãi. Gia hạn Vault token không đồng nghĩa gia hạn database secret lease, và việc đổi KV version không thu hồi API key cũ ở bên thứ ba.

## 12. Bảo mật: ranh giới cần thiết ngoài SigV4

### 12.1. Least privilege hai bên

- Ở **AWS**, role/trust policies phải chỉ cho đúng workload assume role. Không dùng chung một AWS role có quyền rộng cho mọi ứng dụng.
- Ở **Vault auth/aws**, bind cụ thể `bound_iam_principal_arn` và cấp Vault role/policies riêng cho từng service/môi trường.
- Ở **Vault ACL**, cấp `read` tại đúng KV path hoặc `update` tại Transit encrypt path, không dùng `path "*"` để vượt lỗi.
- Ở **ứng dụng**, không cho người dùng đầu cuối tùy ý đưa một Vault path rồi sử dụng quyền của workload để lấy secret; kiểm tra Spring Security/ownership riêng.

### 12.2. Bảo vệ signed request và bearer token

1. HTTPS giữa Spring Vault client và Vault, kiểm tra CA và hostname; Vault kết nối AWS STS qua TLS hợp lệ.
2. Không log `Authorization` của STS request, `X-Amz-Security-Token`, `iam_request_headers`, `X-Vault-Token`, AWS secret access key hoặc Vault response chứa secret.
3. Bật signed `X-Vault-AWS-IAM-Server-ID` riêng cho từng Vault deployment.
4. Dùng AWS temporary credentials từ role/identity provider và hạn chế môi trường/process có thể đọc chúng.
5. Đặt Vault token TTL hợp lý, kiểm soát renewability/revocation và cảnh báo login bất thường.
6. Bảo vệ audit sink; audit phía Vault không thay việc scrub log/trace phía Java.

### 12.3. Quyền vận hành Vault AWS auth cũng cần kiểm soát

Quyền chỉnh `auth/aws/role/*`, `auth/aws/config/client` và ACL policies có thể làm thay đổi ai được login. Không trao quyền quản trị những endpoint này cho token của ứng dụng nghiệp vụ. Quá trình tạo role phải qua review/automation được ủy quyền, có audit và negative test.

## 13. Chẩn đoán lỗi theo từng lớp

| Triệu chứng | Lớp cần kiểm tra | Gợi ý nguyên nhân và hướng xử lý |
|---|---|---|
| `Unable to load credentials`/không có credentials | AWS SDK/runtime | Instance/task/pod chưa được cấp role, profile sai, credentials provider bị env override, metadata không truy cập được |
| `ExpiredToken` hoặc `InvalidClientTokenId` từ AWS | AWS temporary credentials/STS | Credentials hết hạn, session token không đi kèm, provider chưa refresh |
| `SignatureDoesNotMatch`/request signature lỗi | SigV4/STS | Region, Host, method, body, signed headers, timestamp hoặc credentials không khớp |
| Chữ ký valid nhưng Vault login bị từ chối | Vault auth role | Sai `role`, `auth_type`, `bound_iam_principal_arn` hoặc unique-ID resolution |
| Sai `X-Vault-AWS-IAM-Server-ID` | Vault/client binding | Server ID trên Spring Vault không khớp `iam_server_id_header_value` hoặc header không nằm trong SignedHeaders |
| Vault kết nối được nhưng STS timeout | Vault server → AWS STS | Vault egress, DNS, proxy, STS endpoint/Region, firewall hoặc sự cố AWS |
| Vault login thành công nhưng KV trả 403 | Vault ACL | Token có policy không cho `read` trên `secret/data/prod/orders/payment`; auth và authorization là hai bước khác nhau |
| KV trả 404/null | KV engine/path | Mount khác tên, KV v1/v2 nhầm, key bị xóa hoặc không có field |
| TLS handshake lỗi đến Vault | Java HTTP/TLS | CA trust, hostname/certificate không khớp, certificate hết hạn, đồng hồ hệ thống |
| Token Vault hết hạn/revoke | Session/token lifecycle | `SessionManager` renewal/re-login theo loại token; không retry vô hạn cùng token |
| Credentials hoạt động ở laptop nhưng không ở ECS | Runtime identity | Local profile có role khác task role; cần kiểm tra principal của môi trường thật |

**Thứ tự chẩn đoán hữu ích:**

~~~text
1. Workload có lấy được AWS credentials đúng role không?
2. Region/endpoint STS và đồng hồ có đúng không?
3. SigV4 signed request và Server-ID có khớp Vault config không?
4. Vault server có đến được AWS STS không?
5. ARN caller có khớp Vault auth role binding không?
6. Vault đã cấp token với đúng policies và TTL chưa?
7. Policy có cho đúng KV/Transit/PKI API path không?
8. Ứng dụng dùng secret đã nhận có đúng vòng đời không?
~~~

**Không sửa lỗi AWS credential chain bằng cách hard-code một access key quản trị**; không sửa Vault 403 bằng root token hoặc policy wildcard. Xác định lớp lỗi rồi sửa đúng cấu hình/role.

## 14. Kiểm thử tích hợp đúng vòng xác thực

Mock `VaultOperations` chỉ chứng minh Java xử lý response giả, không chứng minh SigV4 thực sự được STS chấp nhận hoặc Vault áp role đúng. Dùng **Vault test instance** tách biệt cùng AWS test IAM role/account được cho phép; tránh dùng production principal, production secret và token root để chạy test ứng dụng.

### 14.1. Ma trận test nên có

| Kiểm thử | Dữ liệu/điều kiện | Kết quả mong đợi |
|---|---|---|
| IAM happy path | AWS workload role đúng; Vault auth role bind đúng; Server-ID đúng | Login thành công, nhận Vault token có TTL/policy dự kiến |
| Sai IAM role | Workload ký bằng principal khác | Vault không cấp token cho role `orders-iam` |
| Thiếu AWS credentials | Không có provider/role hợp lệ trong test process | Login thất bại rõ, không fallback sang token hard-coded |
| Sai Server-ID | Client ký giá trị dev, Vault yêu cầu prod | Login bị từ chối |
| Sai STS Region/endpoint | Cấu hình không khớp signature/STS | Login bị từ chối, có telemetry nguyên nhân an toàn |
| Vault không đến được STS | Chặn egress từ test Vault | Có timeout/lỗi có kiểm soát; không retry vô hạn |
| Policy đúng KV v2 | Token chỉ `read` tại `secret/data/prod/orders/payment` | Java đọc đúng field giả |
| Negative policy | Token đó truy cập key khác/Transit decrypt | Vault trả 403 |
| Token TTL/revoke | Token hết hạn hoặc bị revoke; AWS credentials vẫn hợp lệ | Client renew/re-login hoặc fail phù hợp; không lộ token |
| AWS role session đổi | Provider cấp temporary credentials mới hợp lệ | Login mới thành công theo role binding, không phụ thuộc session name cố định |
| Vault TLS lỗi | CA trust hoặc hostname sai | Client từ chối kết nối, không tắt verification |
| Log/trace/audit | Bật logging test phù hợp | Không chứa AWS key, signed login payload, Vault token hoặc plaintext KV |

### 14.2. Kịch bản end-to-end

~~~text
GIVEN:
  - Vault test server với auth/aws và signed Server-ID = vault-test.example
  - AWS IAM test role được bind với Vault role orders-iam-test
  - KV v2 mount secret/ và key prod/orders/payment với giá trị giả
  - Vault policy chỉ cho read key đó
  - Spring Vault client cấu hình AWS SDK provider, role, Region và TLS

WHEN:
  - Spring Vault tạo signed GetCallerIdentity request rồi login Vault
  - OrdersPaymentSecretReader.requiredPaymentKey() được gọi

THEN:
  - STS xác minh IAM caller, Vault trả token giới hạn quyền
  - Java đọc được field api-key giả qua KV v2
  - Secret/token không xuất hiện ở REST response, log hay trace
  - Đọc key khác hoặc dùng sai AWS principal phải bị từ chối

WHEN:
  - Token Vault hết hạn hoặc Vault không liên lạc được với STS

THEN:
  - Client renew/re-login hoặc fail đúng chính sách
  - Không fallback sang root token hay plaintext
~~~

Để test **không cần liên hệ AWS**, có thể mock `ClientAuthentication`/`VaultOperations` và kiểm thử logic Java, nhưng đó là **unit test**, không chứng minh integration IAM SigV4. Khi xác minh thật AWS STS, chỉ chạy test trên tài khoản/hạ tầng được phép và tránh ghi raw request vào report.

## 15. Bài tập tình huống

### Tình huống A — Có quyền AWS S3 nhưng Vault trả 403

`orders-service` chạy bằng IAM role có `s3:GetObject`. AWS IAM login vào Vault thành công, nhưng đọc KV trả 403. Hãy kiểm tra **Vault ACL** trên `secret/data/prod/orders/payment` và policies của Vault token. Quyền S3 không phải quyền Vault KV; không cần tăng S3 permissions để sửa 403.

### Tình huống B — EKS pod assume đúng role nhưng login Vault thất bại

Đã có IRSA/Pod Identity, nhưng Vault auth role bind ARN của một IAM role khác hoặc thiếu quyền resolve unique ID ở bước cấu hình. Hãy lấy caller identity theo kênh chẩn đoán an toàn của môi trường test, đối chiếu ARN chuẩn của role, Vault role binding và cấu hình STS. Đừng kết luận “EKS không hỗ trợ AWS IAM auth”.

### Tình huống C — Replay yêu cầu từ dev sang prod

Hai Vault instances cùng cho một IAM principal login. Attacker có signed request từ dev và thử gửi sang prod. Khi hai nơi **yêu cầu Server-ID khác nhau và header đã được ký**, request dev không đáp ứng yêu cầu prod; đây là lý do dùng `X-Vault-AWS-IAM-Server-ID`. Tuy vậy, nếu attacker chiếm hẳn AWS credentials/khả năng ký của principal, cần revoke/rotate credentials, sửa trust policy và áp least privilege; Server-ID không tự loại bỏ tất cả rủi ro.

### Tình huống D — Token Vault còn hiệu lực nhưng AWS credentials đã đổi

Spring Vault có Vault token còn TTL nên những lần gọi KV tiếp theo không nhất thiết phải login IAM lại ngay. Khi token hết hạn hoặc client cần re-login, AWS credential provider phải cấp được credentials mới hợp lệ. Cần theo dõi **cả vòng đời AWS credentials lẫn Vault token**, không nhầm session token của AWS với Vault token.

### Tình huống E — Spring Cloud Vault nạp secret thành công nhưng HTTP client dùng key cũ

Đã login IAM và nạp KV vào Spring `Environment`, sau đó API key được rotate. Client HTTP tạo lúc startup vẫn giữ bản cũ. Đó là bài toán refresh/rebuild client và phối hợp thu hồi key với nhà cung cấp, **không** phải lỗi SigV4. Khả năng nạp secret lúc bootstrap không đồng nghĩa tất cả bean tự nhận phiên bản KV mới.

## 16. Tổng kết và câu hỏi tự kiểm tra

**AWS IAM authentication của Vault** biến khả năng ký một yêu cầu AWS STS `GetCallerIdentity` bằng credentials của workload thành **bằng chứng danh tính**. Spring Vault giúp Java chuẩn bị request SigV4 và login; Vault server dùng AWS STS để xác minh, đối chiếu IAM principal với Vault auth role rồi phát Vault token theo policy. Sau đó, `VaultTemplate`/`VaultOperations` dùng Vault token để truy cập KV, Transit, PKI hoặc engine khác trong phạm vi cho phép.

Năm điểm cốt lõi:

1. AWS IAM role, Vault auth role và Vault ACL policy là ba đối tượng riêng.
2. Chữ ký SigV4 là bằng chứng đối với một request cụ thể; **không** gửi secret access key trực tiếp tới Vault.
3. `X-Vault-AWS-IAM-Server-ID` phải được **ký** và khớp cấu hình Vault để hạn chế replay giữa deployments.
4. Vault **phải có đường tới AWS STS** để xác minh IAM login; Java phải có AWS credentials hợp lệ để ký.
5. AWS temporary credential TTL, Vault login token TTL và secret lease TTL là những vòng đời khác nhau.

**Câu hỏi tự kiểm tra:**

1. Tại sao Vault cần gửi signed `GetCallerIdentity` request tới STS thay vì tin chuỗi ARN mà client khai báo?
2. Tên `OrdersRuntimeRole` trong IAM và `orders-iam` trong Vault giống và khác nhau thế nào?
3. Các trường `iam_request_url`, `iam_request_body`, `iam_request_headers` và `iam_http_request_method` mô tả request nào?
4. Vì sao `X-Vault-AWS-IAM-Server-ID` phải nằm trong `SignedHeaders` thay vì được thêm sau khi ký?
5. Khi IAM login thành công nhưng đọc KV v2 bị 403, hãy kiểm tra path và capability nào?
6. Trong ECS và EKS, AWS SDK lấy credentials bằng những cơ chế workload nào?
7. Tại sao AWS session token không phải Vault login token? Khi hai token hết hạn tại những thời điểm khác nhau, hệ thống phải làm gì?
8. Một EC2 instance profile có phải chỉ có cách AWS-EC2 auth hay cũng có thể dùng AWS-IAM auth?
9. Nếu Vault server mất kết nối đến STS nhưng client Java vẫn đến được Vault, IAM login có thể hoạt động không?
10. Những test nào phải chạy với AWS STS và Vault thật thay vì chỉ mock `VaultOperations`?

## Tài liệu tham khảo chính thức

- [Spring Vault — Authentication Methods (AWS-IAM)](https://docs.spring.io/spring-vault/reference/vault/authentication.html)
- [Spring Vault — AwsIamAuthentication Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthentication.html)
- [Spring Vault — AwsIamAuthenticationOptions Builder Javadoc](https://docs.spring.io/spring-vault/reference/api/java/org/springframework/vault/authentication/AwsIamAuthenticationOptions.AwsIamAuthenticationOptionsBuilder.html)
- [Spring Cloud Vault — Authentication Methods](https://docs.spring.io/spring-cloud-vault/reference/authentication.html)
- [HashiCorp Vault — AWS Auth Method](https://developer.hashicorp.com/vault/docs/auth/aws)
- [HashiCorp Vault — AWS Auth Method HTTP API](https://developer.hashicorp.com/vault/api-docs/auth/aws)
- [HashiCorp Vault — ACL Policies](https://developer.hashicorp.com/vault/docs/concepts/policies)
- [HashiCorp Vault — Token Concepts](https://developer.hashicorp.com/vault/docs/concepts/tokens)
- [AWS — STS GetCallerIdentity](https://docs.aws.amazon.com/STS/latest/APIReference/API_GetCallerIdentity.html)
- [AWS — STS Regional Endpoints](https://docs.aws.amazon.com/IAM/latest/UserGuide/id_credentials_temp_region-endpoints.html)
- [AWS — Signature Version 4 Signing Process](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html)
- [AWS SDK for Java 2.x — Credentials Chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)

> **Lưu ý phiên bản:** Phần Java minh họa API Spring Vault 4.1.x với AWS SDK v2. Các bản Spring Vault cũ có thể dùng loại AWS SDK khác, và một số hành vi Vault AWS auth (role binding, unique-ID resolution, STS endpoint/Region, token policy) phụ thuộc phiên bản/cấu hình. Mọi tài khoản, URL, tên role và ARN trong bài chỉ là ví dụ giả; khi triển khai production phải xác minh dependency, role/trust policy, Vault auth configuration, TLS và kiểm thử tích hợp trên môi trường được ủy quyền.
