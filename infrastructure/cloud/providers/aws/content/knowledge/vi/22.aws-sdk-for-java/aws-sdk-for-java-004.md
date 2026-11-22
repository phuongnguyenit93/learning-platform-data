# Region provider chain, endpoint và AWS Signature Version 4

> **Chương:** AWS SDK cho Java  
> **Module:** CLOUD_PROVIDERS_AWS — khám phá hệ sinh thái AWS qua hạ tầng Region/AZ, IAM, VPC, dịch vụ tính toán, lưu trữ, cơ sở dữ liệu, tích hợp và serverless. Người học rèn khả năng chọn dịch vụ, thiết kế và triển khai ứng dụng an toàn, có khả năng giám sát, phục hồi và kiểm soát chi phí.

## Mục tiêu học tập

Một ứng dụng Java chạy trên máy cá nhân, CI pipeline, Amazon ECS và Amazon EC2 có thể gọi cùng một dịch vụ AWS, nhưng các môi trường khác nhau về **Region, credentials, network và endpoint**. Nếu ứng dụng hard-code hostname hoặc tự ký HTTP request, nó dễ gọi nhầm Region, dùng sai partition, tạo chữ ký không hợp lệ hoặc làm lộ secret.

**AWS SDK for Java 2.x** xử lý phần lớn công việc này qua provider chains, endpoint rules và request signers. Bài học tập trung vào ba câu hỏi:

1. SDK xác định **Region** từ đâu, theo thứ tự nào, và khi nào cấu hình tường minh có hiệu lực?
2. SDK chọn **service endpoint** ra sao, khi nào cần endpoint override, FIPS, dual-stack hoặc endpoint đặc biệt?
3. **AWS Signature Version 4 (SigV4)** ký request thế nào, vì sao Region/service/headers/body/timestamp phải khớp?

Sau bài học, bạn có thể:

- Phân biệt Region của service, Region của SSO login, Availability Zone và AWS partition.
- Mô tả default Region provider chain của Java SDK v2 và cấu hình profile.
- Phân biệt Region provider chain với credentials provider chain.
- Cấu hình Region tường minh, `Region.of(...)` và `DefaultAwsRegionProviderChain`.
- Hiểu endpoint resolution, `endpointOverride`, FIPS, dual-stack và service-specific endpoint rules.
- Thiết kế kết nối LocalStack/custom endpoint mà vẫn hiểu signing Region.
- Trình bày canonical request, string to sign, credential scope, signing key và signature của SigV4.
- Hiểu temporary credentials, session token, presigned URLs và SigV4a.
- Xử lý lỗi NoRegion, UnknownHost, SignatureDoesNotMatch, InvalidSignatureException và clock skew.
- Viết Java SDK v2 code theo least privilege, reuse client, không log credentials và có kiểm thử cấu hình.

## 1. Region, endpoint và chữ ký liên hệ thế nào?

### 1.1. Ba quyết định riêng nhưng phải nhất quán

| Thành phần | Câu hỏi | Ví dụ |
|---|---|---|
| **Region** | API request thuộc Region nào? | `ap-southeast-1` |
| **Endpoint** | HTTP request gửi tới hostname/URL nào? | `dynamodb.ap-southeast-1.amazonaws.com` |
| **Signing context** | Request được ký với credentials, Region và service scope nào? | `AWS4-HMAC-SHA256 / ap-southeast-1 / dynamodb` |

Region thường ảnh hưởng cả **endpoint resolution** và **credential scope của SigV4**. Vì vậy, đổi endpoint URL mà không hiểu signing Region có thể dẫn đến lỗi xác thực.

~~~mermaid
flowchart TD
    APP[Java application] --> CFG[Client configuration]
    CFG --> R[Region provider]
    CFG --> C[Credentials provider]
    R --> E[Endpoint resolution]
    R --> S[Signing Region]
    C --> S
    E --> HTTP[HTTP request]
    S --> SIGN[SigV4 signer]
    HTTP --> SEND[Signed request]
    SIGN --> SEND
    SEND --> AWS[AWS service endpoint]
~~~

Với service clients tiêu chuẩn, SDK tự thực hiện các bước này. Người phát triển chủ yếu chọn đúng **Region, credentials provider, endpoint behavior và HTTP client**.

### 1.2. Region không phải Availability Zone

**AWS Region** là khu vực địa lý độc lập gồm nhiều Availability Zones. **Availability Zone (AZ)** là vị trí hạ tầng riêng biệt trong một Region. Java SDK service client thường cấu hình **Region**, không phải AZ.

~~~text
Region: ap-southeast-1
  AZ: ap-southeast-1a
  AZ: ap-southeast-1b
  AZ: ap-southeast-1c
~~~

Các suffix AZ như `a`, `b`, `c` có mapping có thể khác giữa AWS accounts. Không dùng AZ name của một account như định danh global cố định.

### 1.3. Chọn Region theo yêu cầu workload

Cần xem xét:

- Vị trí người dùng và latency;
- Data residency, compliance và chính sách lưu trữ;
- Dịch vụ/engine/instance types có sẵn;
- AZs và disaster recovery requirements;
- Giá, data transfer và các dependencies;
- VPC connectivity, private endpoints và cross-Region traffic.

Một Region hỗ trợ S3 không có nghĩa mọi tính năng của mọi service đều có mặt ở đó. Kiểm tra service availability, feature availability và quota trước khi triển khai.

### 1.4. AWS partition

AWS có nhiều **partitions**, ví dụ:

| Partition | Ví dụ Region | DNS suffix phổ biến |
|---|---|---|
| `aws` | `ap-southeast-1`, `us-east-1` | `amazonaws.com` |
| `aws-cn` | `cn-north-1` | `amazonaws.com.cn` |
| `aws-us-gov` | `us-gov-west-1` | `amazonaws.com` |

ARN thường có cấu trúc:

~~~text
arn:<partition>:<service>:<region>:<account-id>:<resource>
~~~

Ví dụ minh họa:

~~~text
arn:aws:dynamodb:ap-southeast-1:111122223333:table/LearningCore
arn:aws-cn:dynamodb:cn-north-1:111122223333:table/LearningCore
~~~

Không hard-code DNS suffix hoặc ARN partition `aws` vào thư viện dùng chung cho China/GovCloud. SDK và endpoint rules hiểu Region/partition; ứng dụng nên dùng ARN/Region từ cấu hình tin cậy.

## 2. Default Region provider chain của Java SDK v2

### 2.1. Vì sao có provider chain?

Ứng dụng có thể chạy trên developer laptop, CI, ECS, EKS, EC2 hoặc Lambda. Mỗi môi trường có cách cung cấp Region khác nhau. Thay vì viết nhiều nhánh cấu hình, Java SDK v2 cung cấp **DefaultAwsRegionProviderChain** để tìm Region theo thứ tự đã định nghĩa.

### 2.2. Thứ tự provider chain

Default Region provider chain của Java SDK 2.x lần lượt kiểm tra:

1. **JVM system property** `aws.region`;
2. **Environment variable** `AWS_REGION`;
3. **AWS shared config file** — Region của profile được chọn;
4. **EC2 instance metadata service (IMDS)** — Region của EC2 instance khi metadata truy cập được.

~~~mermaid
flowchart TD
    A[Resolve Region] --> B{JVM property aws.region?}
    B -->|Có| R1[Use system property]
    B -->|Không| C{Environment AWS_REGION?}
    C -->|Có| R2[Use AWS_REGION]
    C -->|Không| D{Selected profile has region?}
    D -->|Có| R3[Use shared config profile region]
    D -->|Không| E{EC2 IMDS available?}
    E -->|Có| R4[Use EC2 instance Region]
    E -->|Không| F[No Region found / exception]
~~~

**Giá trị đầu tiên hợp lệ được tìm thấy sẽ thắng.** Ví dụ, `aws.region=us-west-2` trong JVM system properties được ưu tiên hơn `AWS_REGION=ap-southeast-1`.

### 2.3. Không nhầm AWS_REGION và AWS_DEFAULT_REGION

Với Java SDK v2 default Region provider chain, environment variable được tài liệu hóa là:

~~~text
AWS_REGION=ap-southeast-1
~~~

`AWS_DEFAULT_REGION` thường gặp trong AWS CLI và một số công cụ khác, nhưng **không nên mặc định rằng Java SDK v2 đọc nó như AWS_REGION**. Nếu Java app cần Region từ environment, dùng `AWS_REGION` hoặc cấu hình Region rõ ràng.

Không giả định các SDK ngôn ngữ khác có cùng provider chain hoặc cùng thứ tự.

### 2.4. Cấu hình JVM system property

Chạy ứng dụng:

~~~bash
java -Daws.region=ap-southeast-1 -jar application.jar
~~~

Hoặc trước khi build client:

~~~java
System.setProperty("aws.region", "ap-southeast-1");
~~~

Đặt system property trước khi SDK resolve Region và tạo client. Tránh sửa global system properties trong lúc ứng dụng đang chạy: clients đã tạo không tự động đổi Region theo cấu hình mới.

### 2.5. Cấu hình environment variable

Linux/macOS:

~~~bash
export AWS_REGION=ap-southeast-1
java -jar application.jar
~~~

PowerShell:

~~~powershell
$env:AWS_REGION = "ap-southeast-1"
java -jar application.jar
~~~

Environment variables là cấu hình ở process scope. Region thường không phải secret nhưng vẫn cần quản lý để tránh deploy nhầm môi trường.

### 2.6. Shared config file và profile

Ví dụ `~/.aws/config`:

~~~ini
[default]
region = ap-southeast-1
output = json

[profile dev]
region = ap-southeast-1
output = yaml

[profile staging]
region = ap-southeast-2

[profile prod]
region = ap-southeast-1
~~~

Profile được chọn bằng `AWS_PROFILE` hoặc JVM system property `aws.profile`:

~~~bash
export AWS_PROFILE=dev
~~~

Trong shared config, tên profile không có tiền tố `profile` đối với `[default]`, còn named profiles dùng `[profile dev]`. Region trong selected profile là nguồn của Region provider chain khi các nguồn ưu tiên cao hơn không có.

**Lưu ý:** Region profile nằm trong **shared config file** `~/.aws/config`; file `~/.aws/credentials` chủ yếu lưu credentials. Đừng đặt Region vào credentials file rồi giả định SDK sẽ đọc nó từ đó.

### 2.7. Đường dẫn config file tùy chỉnh

| Biến | Ý nghĩa |
|---|---|
| `AWS_PROFILE` | Chọn profile |
| `AWS_CONFIG_FILE` | Đường dẫn shared config file |
| `AWS_SHARED_CREDENTIALS_FILE` | Đường dẫn shared credentials file |
| `AWS_REGION` | Region cho Java SDK v2 default chain |
| `AWS_DEFAULT_REGION` | Thường dùng bởi AWS CLI/tooling; không dựa vào nó cho Java SDK v2 |

Không commit shared credentials file vào repository. Với laptop, sử dụng profile/SSO theo chính sách tổ chức; production ưu tiên workload role.

### 2.8. sso_region không phải Region của service client

Một profile IAM Identity Center có thể chứa:

~~~ini
[profile dev-sso]
sso_session = company
sso_account_id = 111122223333
sso_role_name = Developer
region = ap-southeast-1
sso_region = ap-southeast-2
sso_start_url = https://example.awsapps.com/start

[sso-session company]
sso_region = ap-southeast-2
sso_start_url = https://example.awsapps.com/start
sso_registration_scopes = sso:account:access
~~~

`sso_region` dùng cho **IAM Identity Center/SSO service** để lấy token; `region` là Region mặc định của AWS service clients khi profile được chọn. Hai giá trị có thể khác nhau.

Đăng nhập theo quy trình tổ chức, ví dụ `aws sso login --profile dev-sso`, rồi Java SDK dùng profile/SSO credentials provider phù hợp. Không coi `sso_region` là Region của DynamoDB/S3.

### 2.9. IMDS trên EC2

Khi các nguồn trước không có Region, SDK có thể lấy metadata của EC2 instance qua **Instance Metadata Service (IMDS)**.

- IMDSv2 dùng token; instance metadata options có thể yêu cầu token;
- IMDS có thể bị tắt/chặn bởi instance configuration, proxy hoặc network controls;
- Container/proxy settings phải tránh chuyển metadata request ra ngoài không cần thiết;
- Không dựa vào IMDS nếu chạy local laptop hoặc runtime không phải EC2;
- Không tăng quyền metadata access chỉ để che lỗi thiếu Region.

Nếu không tìm thấy Region từ provider nào, SDK ném lỗi kiểu **Unable to load region from any of the providers in the chain**. Hãy cấu hình một nguồn Region hợp lệ hoặc truyền Region tường minh.

## 3. Region provider chain khác credentials provider chain

### 3.1. Hai chain giải quyết hai câu hỏi

| Provider chain | Trả lời | Ví dụ |
|---|---|---|
| Region provider | Gọi AWS ở Region nào? | `ap-southeast-1` |
| Credentials provider | Dùng identity nào để ký/xác thực? | IAM role, SSO, access key session |

Có Region **không có nghĩa có credentials**. Có credentials **không có nghĩa SDK biết Region**. Một client thường cần cả hai để gửi signed request.

### 3.2. Default credentials provider chain

`DefaultCredentialsProvider` của Java SDK v2 tìm credentials qua các nguồn, gồm:

- JVM system properties;
- Environment variables;
- Web identity token / role credentials;
- Shared profile/configuration, gồm các providers được profile khai báo;
- Container credentials;
- EC2 instance profile credentials qua IMDS.

Profile có thể dùng IAM Identity Center/SSO, assume-role, credential process và các cơ chế được SDK hỗ trợ khi có dependencies/cấu hình tương ứng.

**Đừng trộn thứ tự Region chain với credentials chain.** Region chain tìm `aws.region`, `AWS_REGION`, shared config Region và IMDS; credentials chain tìm danh tính/secret credentials theo cơ chế riêng.

### 3.3. Workload identity thay cho long-lived access keys

| Môi trường | Nguồn credentials thường dùng |
|---|---|
| Developer laptop | IAM Identity Center/SSO profile hoặc profile được tổ chức quản lý |
| CI workload | OIDC federation → assume role, nếu nền tảng hỗ trợ |
| Amazon ECS | Task role |
| Amazon EKS | EKS Pod Identity hoặc IRSA theo kiến trúc |
| Amazon EC2 | Instance profile role |
| AWS Lambda | Execution role |

Không nhúng `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` vào Java source, Docker image, Maven settings hoặc log. Credentials tạm thời có expiration và session token; SDK provider cần refresh theo cơ chế tương ứng.

### 3.4. Cấu hình credentials provider rõ ràng

Default provider:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;

DefaultCredentialsProvider credentialsProvider =
    DefaultCredentialsProvider.create();
~~~

Profile cụ thể:

~~~java
import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;

ProfileCredentialsProvider profileProvider =
    ProfileCredentialsProvider.builder()
        .profileName("dev")
        .build();
~~~

Dùng explicit profile khi công cụ developer cần rõ profile; production service nên dùng role provider phù hợp runtime. Không hard-code profile `dev` trong ứng dụng triển khai lên ECS/EC2/Lambda.

### 3.5. Web identity và container credentials

Trong container/EKS, workload identity giúp mỗi workload có IAM role giới hạn. Tránh mount shared credentials file của node vào tất cả pods hoặc cấp một node role rộng cho mọi ứng dụng.

Một số providers cần endpoint/metadata environment variables do runtime inject. Không tự đặt `AWS_CONTAINER_CREDENTIALS_*` hoặc `AWS_WEB_IDENTITY_TOKEN_FILE` bằng tay nếu không hiểu trust policy/token audience.

### 3.6. Kiểm tra Region và identity riêng rẽ

Một startup diagnostic có thể log:

~~~text
service=dynamodb
region=ap-southeast-1
credential_source=task-role (category only)
endpoint_mode=standard
~~~

Chỉ log nguồn/cấu hình ở mức không nhạy cảm. Không log access key, secret, session token, SSO cache, credential object hoặc Authorization header. Để kiểm tra caller identity, dùng STS `GetCallerIdentity` theo network/policy; response chứa account/ARN nên cũng cần xử lý như metadata nội bộ.

## 4. Cấu hình Region trong Java SDK v2

### 4.1. Truyền Region tường minh

Cách dễ dự đoán nhất:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();
~~~

`builder.region(...)` ghi đè Region provider chain cho client đó. Phù hợp khi deployment Region cố định và được inject từ configuration đã kiểm soát.

### 4.2. Dùng default Region provider chain để kiểm tra effective Region

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.regions.providers.DefaultAwsRegionProviderChain;

Region region = new DefaultAwsRegionProviderChain().getRegion();

DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .region(region)
    .build();
~~~

Khi builder không có Region, SDK cũng dùng default chain nội bộ. Gọi chain tường minh hữu ích nếu cần **log/validate effective Region** trước khi khởi tạo nhiều service clients.

Nếu chain không tìm thấy Region, xử lý lỗi startup với thông báo cấu hình rõ ràng; không fallback ngầm sang `us-east-1` trừ khi đó là quyết định kiến trúc đã duyệt.

### 4.3. Region mới hoặc chưa có enum constant

Dùng factory `Region.of("region-name")`:

~~~java
Region region = Region.of("ap-southeast-5");
~~~

Điều này cho phép sử dụng Region string ngay cả khi SDK version chưa có constant tương ứng, miễn service/endpoint hỗ trợ và SDK endpoint rules xử lý đúng. Tuy nhiên, nên nâng SDK lên version hỗ trợ Region mới để nhận endpoint metadata, signing behavior và bug fixes.

**Không suy ra Region hợp lệ chỉ vì Region object tạo được.** Service/feature availability vẫn phải được AWS hỗ trợ.

### 4.4. Nhiều service clients dùng một Region config

~~~java
Region region = Region.of(configuredRegion);

try (DynamoDbClient dynamoDb = DynamoDbClient.builder()
         .region(region)
         .build();
     S3Client s3 = S3Client.builder()
         .region(region)
         .build();
     SqsClient sqs = SqsClient.builder()
         .region(region)
         .build()) {
    // Reuse clients for application operations.
}
~~~

Service clients là thread-safe và nên được **reuse** trong vòng đời ứng dụng. Không tạo client cho từng HTTP request; mỗi client có HTTP connection pool, retry/configuration và lifecycle riêng.

### 4.5. Một ứng dụng có thể gọi nhiều Regions

~~~java
S3Client mediaS3 = S3Client.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();

DynamoDbClient metadataDb = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_2)
    .build();
~~~

Đừng dùng một Region global cho mọi client nếu kiến trúc multi-Region. Đặt tên cấu hình theo service/workload để tránh nhầm. Cross-Region requests có thể tăng latency/data transfer và có yêu cầu IAM/network khác.

### 4.6. Không thay đổi Region sau khi build

Region được cố định trong client configuration khi build. Muốn gọi Region khác, tạo **client riêng cho Region đó** và reuse client, thay vì sửa global `AWS_REGION` trong lúc chạy.

Không tạo một static global DynamoDB client với Region lấy từ user input. Nếu tenant ở nhiều Regions, cần routing layer có allowlist, mapping tin cậy và quản lý client lifecycle/cache.

## 5. Endpoint resolution trong Java SDK v2

### 5.1. Endpoint là gì?

Endpoint là URL/hostname của AWS service API. Ví dụ:

~~~text
https://dynamodb.ap-southeast-1.amazonaws.com
https://s3.ap-southeast-1.amazonaws.com
https://sqs.ap-southeast-1.amazonaws.com
~~~

Endpoint có thể gồm scheme, host, port và path/base path. SDK dùng **service endpoint rules** để chọn endpoint theo:

- Service;
- Region và partition;
- Endpoint parameters;
- FIPS/dual-stack flags;
- ARN/resource Region cho một số services;
- Endpoint override nếu được cấu hình;
- Service-specific behavior như S3 addressing/access points.

**Không hard-code hostname theo mẫu** `service.region.amazonaws.com` cho mọi service. Có service global, endpoint rules đặc biệt, partition-specific DNS suffix hoặc ARN-based routing.

### 5.2. Region quyết định endpoint mặc định

Khi client được build với Region `ap-southeast-1`, SDK endpoint rules thường chọn endpoint tương ứng Region:

~~~java
DynamoDbClient dynamoDb = DynamoDbClient.builder()
    .region(Region.AP_SOUTHEAST_1)
    .build();
~~~

SDK xử lý endpoint host và signing context. Ứng dụng nên truyền **Region** thay vì tự nối chuỗi URL, trừ khi cần endpoint override có chủ đích.

### 5.3. Endpoint override

`endpointOverride(URI)` dùng khi cần gửi request tới URL cụ thể, ví dụ LocalStack, mock server, gateway tương thích hoặc private test endpoint:

~~~java
import java.net.URI;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3 = S3Client.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create("http://localhost:4566"))
    .build();
~~~

**Region vẫn cần thiết** vì SDK dùng nó trong signing context, dù host đã bị override. Custom endpoint có thể yêu cầu service/Region signing behavior riêng; endpoint override không loại bỏ SigV4.

### 5.4. Endpoint override không tự tạo network connectivity

Đặt endpoint URL tới `http://localhost:4566` không làm LocalStack tự chạy. Đặt private endpoint DNS không tự cấu hình VPC routes, SG, TLS trust hoặc DNS resolution.

Trước khi dùng endpoint override, xác minh:

1. Hostname resolve được từ runtime;
2. Port mở và network route đúng;
3. TLS certificate/CA hợp lệ nếu HTTPS;
4. Endpoint nói đúng protocol/API;
5. Signing service/Region phù hợp;
6. IAM/authentication mode được endpoint hỗ trợ;
7. Client timeout/retry không che lỗi kết nối.

### 5.5. FIPS endpoints

Một số AWS services/Regions hỗ trợ endpoint **FIPS (Federal Information Processing Standards)**.

- Chỉ bật khi service/Region hỗ trợ;
- Không tự thêm chuỗi `-fips` vào hostname theo phỏng đoán;
- SDK service client/endpoint rules có thể cung cấp cấu hình FIPS;
- FIPS endpoint không tự làm mọi dữ liệu/ứng dụng tuân thủ toàn bộ compliance standard.

### 5.6. Dual-stack endpoints

Dual-stack endpoint hỗ trợ **IPv4 và IPv6** khi service/Region/network hỗ trợ. Nó không có nghĩa runtime tự chuyển toàn bộ traffic qua IPv6; DNS, VPC, routes, firewall và client network stack vẫn phải cho phép.

FIPS và dual-stack có thể kết hợp khi endpoint rules hỗ trợ. Không hard-code hostname suffix để bật dual-stack.

### 5.7. Service-specific endpoint rules

Một số service có logic đặc biệt:

- **Amazon S3:** virtual-hosted/path-style addressing, access point ARNs, Multi-Region Access Points, accelerate và dual-stack;
- **STS:** global/regional endpoint choices và signing Region behavior theo cấu hình;
- **DynamoDB/SQS/Lambda:** thường dùng endpoint theo Region, nhưng vẫn cần service/partition endpoint rules;
- **IAM/Route 53/CloudFront:** có endpoint scope/behavior đặc biệt; kiểm tra service documentation thay vì áp dụng mẫu regional hostname chung.

SDK v2 có endpoint rules để xử lý nhiều trường hợp. Với custom endpoint hoặc ARN Region routing, hãy test đúng request thực tế.

### 5.8. Endpoint discovery

Một số services có **endpoint discovery** hoặc trả về endpoint riêng theo resource/operation. Đây là khả năng service-specific, không phải mọi service client đều tự tìm endpoint riêng.

Khi service API trả endpoint metadata, SDK có thể hỗ trợ discovery/caching theo cấu hình và client. Đọc hướng dẫn đúng service; không lưu endpoint vô thời hạn hoặc bỏ qua expiry/refresh semantics.

## 6. Endpoint behavior cho S3 và các trường hợp đặc biệt

### 6.1. Virtual-hosted-style và path-style

S3 có hai cách biểu diễn bucket/object trong URL:

~~~text
Virtual hosted:
https://my-bucket.s3.ap-southeast-1.amazonaws.com/folder/file.txt

Path style:
https://s3.ap-southeast-1.amazonaws.com/my-bucket/folder/file.txt
~~~

Virtual-hosted style là cách phổ biến. Path-style support có giới hạn/behavior theo S3 features và endpoint; không mặc định mọi bucket/feature đều dùng được path style.

### 6.2. Access Point ARN và Multi-Region Access Point

S3 Access Point ARN và Multi-Region Access Point ARN có thể yêu cầu **endpoint rules** đặc biệt. SDK hiểu ARN/Region routing nếu dùng client/configuration phù hợp.

Đừng tự parse ARN rồi ghép hostname khi SDK đã có endpoint resolver; việc này dễ sai partition, DNS suffix, signing Region và SigV4a requirements.

### 6.3. Accelerate, dual-stack và FIPS

Các tùy chọn S3 như accelerate, dual-stack, path style và FIPS có điều kiện hỗ trợ riêng. Không bật mọi option cùng lúc nếu chưa kiểm tra combinations. Bucket naming, TLS certificate hostname và S3 access point ARN có thể ảnh hưởng endpoint selection.

### 6.4. LocalStack và endpoint giả lập

LocalStack hữu ích cho integration tests nhưng **không phải AWS thật**:

- Không phải mọi service APIs/features/quotas đều mô phỏng đầy đủ;
- IAM enforcement, eventual consistency và retry semantics có thể khác;
- Endpoint override thường nằm trong test profile, không dùng production;
- Dữ liệu LocalStack không chứng minh endpoint/credentials production đã cấu hình đúng.

~~~java
S3Configuration s3Configuration = S3Configuration.builder()
    .pathStyleAccessEnabled(true)
    .build();

S3Client localS3 = S3Client.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create("http://localhost:4566"))
    .serviceConfiguration(s3Configuration)
    .build();
~~~

`S3Configuration.pathStyleAccessEnabled(true)` là cấu hình riêng của S3; chỉ dùng nếu endpoint giả lập yêu cầu path-style. Với production S3, để SDK áp dụng endpoint rules phù hợp.

### 6.5. Không log endpoint URLs có query secrets

Một số custom gateway/presigned URLs có query parameters chứa authentication material. Tránh log toàn bộ URL, Authorization headers hoặc request signing details. Log service, Region, endpoint mode và request ID/correlation ID đã redact.

## 7. AWS Signature Version 4: mục đích và phạm vi

### 7.1. Vì sao AWS ký request?

SigV4 giúp AWS xác minh credentials ký request, HTTP method/URI/query/headers, payload hash (khi payload signing được dùng), ngày/Region/service scope và session token của temporary credentials.

SigV4 **không phải encryption**. HTTPS/TLS bảo vệ dữ liệu khi truyền; SigV4 xác thực request và integrity của phần được ký. Request có chữ ký hợp lệ vẫn cần IAM policy cho phép action/resource.

### 7.2. Chuỗi bước tổng quát

~~~text
HTTP request
  -> Canonical Request
  -> SHA-256 hash of Canonical Request
  -> String to Sign
  -> Derived Signing Key
  -> HMAC-SHA256 Signature
  -> Authorization header or presigned query parameters
~~~

### 7.3. SDK tự ký request

Với service clients tiêu chuẩn, SDK v2 lấy credentials qua provider, lấy timestamp UTC, tạo canonical request, signing key/signature, thêm Authorization/session token và gửi request qua HTTP client.

**Không tự viết SigV4 signer trong business code** và không tự đặt Authorization header nếu đang dùng AWS SDK service client. Manual signing dễ sai encoding, headers, payload hashing, session token, clock skew và endpoint routing.

### 7.4. SigV4 không thay IAM authorization

Request có chữ ký đúng nhưng role không có `dynamodb:PutItem` vẫn nhận `AccessDeniedException`. SigV4 chứng minh request được ký bởi credentials; IAM/resource policy/SCP/KMS/endpoint policy quyết định quyền hành động.

| Lỗi | Ý nghĩa thường gặp |
|---|---|
| `SignatureDoesNotMatch` / `InvalidSignatureException` | Chữ ký hoặc canonicalization/signing scope không khớp |
| `ExpiredToken` / `InvalidClientTokenId` | Credentials hết hạn/sai/không hợp lệ |
| `AccessDenied` | Credentials nhận diện được nhưng policy không cho phép hoặc policy condition chặn |

## 8. SigV4: Canonical Request

### 8.1. Cấu trúc

Một canonical request có dạng:

~~~text
HTTPMethod
CanonicalURI
CanonicalQueryString
CanonicalHeaders

SignedHeaders
HashedPayload
~~~

Các dòng được ngăn bằng newline theo đặc tả. Canonical headers kết thúc bằng newline, nên có một dòng trống trước SignedHeaders trong cách biểu diễn thường thấy.

### 8.2. HTTP method

Dùng method thực tế: `GET`, `POST`, `PUT`, `DELETE`, v.v. Method phải khớp request gửi đi. Không ký `POST` rồi đổi sang `GET` sau đó.

### 8.3. Canonical URI

Canonical URI là path đã encode theo quy tắc SigV4:

- Path encoding phải đúng UTF-8/percent-encoding;
- Không tự normalize dấu slash tùy tiện;
- S3 có quy tắc path đặc biệt, SDK xử lý theo service;
- Không double-encode hoặc decode rồi encode lại bằng proxy nếu không hiểu signer behavior.

Request tới object key có ký tự đặc biệt có thể thất bại nếu gateway thay đổi `%2F`, `%20`, dấu `+` hoặc Unicode sau khi ký.

### 8.4. Canonical query string

Query parameters được encode và sắp xếp theo quy tắc SigV4, bao gồm key/value. Không giả định thứ tự query ban đầu được giữ nguyên trong canonical form.

~~~text
GET /?Action=ListUsers&Version=2010-05-08
~~~

Canonical query string được tạo từ encoded parameter pairs theo thứ tự đã quy định. Nếu có duplicate parameters hoặc giá trị rỗng, phải tuân theo quy tắc encoding/sorting chính xác.

### 8.5. Canonical headers

Headers được chuẩn hóa:

- Header names viết thường;
- Sắp xếp theo thứ tự từ điển;
- Trim và chuẩn hóa whitespace;
- Các headers quan trọng gồm `host` và những `x-amz-*` liên quan theo request;
- `SignedHeaders` liệt kê header names đã ký, phân cách bằng dấu chấm phẩy.

Ví dụ:

~~~text
content-type:application/x-amz-json-1.0
host:dynamodb.ap-southeast-1.amazonaws.com
x-amz-date:20261120T035000Z
x-amz-target:DynamoDB_20120810.GetItem
~~~

Nếu reverse proxy thay `Host`, đổi header được ký, thay body hoặc normalize sai whitespace sau khi signer chạy, AWS có thể không xác minh được chữ ký.

### 8.6. Hashed payload

Thông thường payload hash là:

~~~text
Hex(SHA256(request body bytes))
~~~

Với request body rỗng, hash vẫn là SHA-256 của chuỗi bytes rỗng. Một số service/operation/streaming modes có quy tắc payload khác, ví dụ unsigned payload hoặc chunked signing. **Không hard-code `UNSIGNED-PAYLOAD` cho mọi service**; SDK áp dụng quy tắc phù hợp.

### 8.7. Canonical request phải khớp request thật

Một lỗi phổ biến là ký body đã serialize nhưng sau đó JSON serializer/proxy đổi bytes/encoding. SigV4 bảo vệ hash của body bytes theo signing mode; chỉ thay một byte cũng có thể làm signature khác.

Dùng SDK request model thay vì ký JSON thủ công. Nếu đi qua API gateway/reverse proxy, đảm bảo không thay đổi headers/path/query/body đã ký.

## 9. String to Sign, credential scope và signing key

### 9.1. String to Sign

String to Sign có cấu trúc:

~~~text
AWS4-HMAC-SHA256
YYYYMMDD'T'HHMMSS'Z'
YYYYMMDD/region/service/aws4_request
Hex(SHA256(CanonicalRequest))
~~~

Ví dụ:

~~~text
AWS4-HMAC-SHA256
20261120T035000Z
20261120/ap-southeast-1/dynamodb/aws4_request
<canonical-request-sha256-hex>
~~~

Timestamp và credential scope phải phù hợp ngày/Region/service của request.

### 9.2. Credential scope

Credential scope có bốn phần:

~~~text
<date>/<region>/<service>/aws4_request
~~~

Ví dụ:

~~~text
20261120/ap-southeast-1/dynamodb/aws4_request
~~~

Nếu client gửi tới DynamoDB Region `ap-southeast-1` nhưng signer dùng `ap-southeast-2`, scope có thể không khớp endpoint và request bị từ chối. Nếu endpoint override dùng custom host, vẫn cần signing Region/service phù hợp với AWS-compatible endpoint.

### 9.3. Derive signing key

SigV4 dùng HMAC-SHA256 theo từng bước:

~~~text
kDate    = HMAC-SHA256("AWS4" + SecretAccessKey, YYYYMMDD)
kRegion  = HMAC-SHA256(kDate, Region)
kService = HMAC-SHA256(kRegion, Service)
kSigning = HMAC-SHA256(kService, "aws4_request")
~~~

`SecretAccessKey` là secret. Derived signing keys cũng là material nhạy cảm; không log hoặc persist chúng.

### 9.4. Tạo signature

~~~text
Signature = Hex(
    HMAC-SHA256(kSigning, StringToSign)
)
~~~

AWS nhận Authorization header, tính lại canonical request/scope/signature bằng credentials tương ứng rồi so khớp. Nếu mọi phần chính xác và credentials hợp lệ, request đi tiếp tới bước authorization.

### 9.5. Authorization header

Dạng minh họa:

~~~text
Authorization: AWS4-HMAC-SHA256
 Credential=AKIAEXAMPLE/20261120/ap-southeast-1/dynamodb/aws4_request,
 SignedHeaders=content-type;host;x-amz-date;x-amz-target,
 Signature=<signature-hex>
~~~

Access key ID có thể xuất hiện trong Credential scope, nhưng **secret access key không bao giờ được gửi**. Signature không phải secret credential thay thế access key; vẫn phải bảo vệ headers và tokens.

## 10. Temporary credentials và session token

### 10.1. STS credentials gồm ba thành phần

Credentials tạm thời thường có:

~~~text
AccessKeyId
SecretAccessKey
SessionToken
Expiration
~~~

SDK provider phải cung cấp đủ credentials và refresh theo thời gian. Khi ký request bằng temporary credentials, request cần có **session token** (thường là header `X-Amz-Security-Token` hoặc query parameter trong presigned URL).

### 10.2. Vì sao session token quan trọng?

Nếu request ký đúng access key/secret nhưng thiếu session token hoặc token đã hết hạn, AWS có thể trả `InvalidToken`, `ExpiredToken` hoặc lỗi tương ứng.

Không tự copy chỉ access key và secret từ role session rồi bỏ token. Dùng `DefaultCredentialsProvider`, web identity/container/instance profile provider hoặc provider phù hợp để SDK quản lý đầy đủ credential tuple.

### 10.3. Credential refresh

- IAM role credentials có expiration và provider tự refresh khi được hỗ trợ;
- SSO credentials cần session/login hợp lệ và SDK dependencies/provider hỗ trợ;
- Static credentials không tự rotate;
- Custom credentials provider phải xử lý refresh, thread safety, expiration và errors.

Không tạo `StaticCredentialsProvider` từ temporary credentials một lần rồi giữ application chạy nhiều giờ mà không refresh. Hãy để SDK dùng provider runtime.

## 11. Presigned URLs

### 11.1. Presigned URL là gì?

Presigned URL là URL đã được ký để người sở hữu URL có thể thực hiện một request cụ thể trong thời gian có hạn, thường dùng upload/download S3 mà không cấp AWS credentials trực tiếp cho client.

URL có thể chứa query parameters như:

~~~text
X-Amz-Algorithm
X-Amz-Credential
X-Amz-Date
X-Amz-Expires
X-Amz-SignedHeaders
X-Amz-Security-Token (nếu temporary credentials)
X-Amz-Signature
~~~

**Presigned URL là bearer capability**: ai có URL đều có thể dùng trong phạm vi method/resource/expiry đã ký. Không log, gửi vào analytics hoặc để URL công khai sau khi không còn cần.

### 11.2. Expiration

Với SigV4 S3 presigned URLs, giới hạn `X-Amz-Expires` tối đa phổ biến là **7 ngày (604800 giây)** khi dùng signing credentials đủ thời hạn. Nếu URL được ký bằng temporary credentials, URL **hết hiệu lực khi credentials hết hạn**, kể cả thời gian Expires dài hơn.

Policy, object/bucket state, credential revocation và service conditions cũng có thể khiến URL không dùng được trước expiration. Dùng thời hạn ngắn nhất phù hợp workflow.

### 11.3. Java S3Presigner

~~~java
import java.time.Duration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

S3Presigner presigner = S3Presigner.builder()
    .region(Region.AP_SOUTHEAST_1)
    .credentialsProvider(DefaultCredentialsProvider.create())
    .build();

GetObjectRequest getObject = GetObjectRequest.builder()
    .bucket("private-course-assets")
    .key("courses/c1/lesson-1.pdf")
    .build();

GetObjectPresignRequest presignRequest =
    GetObjectPresignRequest.builder()
        .signatureDuration(Duration.ofMinutes(10))
        .getObjectRequest(getObject)
        .build();

String url = presigner.presignGetObject(presignRequest)
    .url()
    .toExternalForm();
~~~

Đây là ví dụ presign download. Production cần validate người dùng có quyền truy cập object, không chỉ biết bucket/key; bucket private và role có `s3:GetObject` giới hạn prefix/resource. Đóng `S3Presigner` khi ứng dụng shutdown.

### 11.4. Presigned PUT

Để upload, ký `PutObjectRequest` với `signatureDuration` phù hợp và truyền đúng headers đã ký. Nếu request cần Content-Type, checksum hoặc encryption headers, client upload phải gửi đúng giá trị; thay header sau khi ký có thể làm signature mismatch.

### 11.5. Presigned URL không phải proxy

Client dùng presigned URL truy cập S3 trực tiếp; application server không nhất thiết truyền file qua mình. Cần cân nhắc CORS cho browser, object key random/opaque, upload size, checksum, malware scanning và lifecycle. URL không tự giới hạn số lần sử dụng theo nghĩa one-time.

## 12. SigV4a và multi-Region signing

### 12.1. SigV4 và SigV4a khác nhau

**SigV4** ký với một Region cụ thể trong credential scope. **SigV4a** là biến thể hỗ trợ multi-Region requests với thuật toán/signing behavior khác, được dùng bởi một số tính năng như S3 Multi-Region Access Points và các services/features AWS hỗ trợ.

Không tự thay `AWS4-HMAC-SHA256` bằng chuỗi khác hoặc ép SigV4a cho mọi request. SDK chọn signer/endpoint behavior phù hợp khi API và resource yêu cầu.

### 12.2. ARN và multi-Region routing

Một số ARN chứa Region; một số resources/service APIs có routing behavior đặc biệt. Với S3 MRAP, SDK có thể dùng endpoint và SigV4a để định tuyến theo khả năng multi-Region. Đừng tự lấy ARN Region hoặc hostname rồi giả định đó là signing Region trong mọi API.

### 12.3. SigV4a không xóa ranh giới partition

SigV4a không xóa ranh giới partition, IAM, network hoặc resource policy. Resource phải được hỗ trợ trong partition/service configuration tương ứng. Không suy ra request signed multi-Region có thể đi xuyên commercial, China và GovCloud tùy ý.

## 13. Java SDK v2: dependencies và client lifecycle

### 13.1. Maven BOM và service modules

Ví dụ Maven:

~~~xml
<properties>
  <aws.sdk.version>2.x.y</aws.sdk.version>
</properties>

<dependencyManagement>
  <dependencies>
    <dependency>
      <groupId>software.amazon.awssdk</groupId>
      <artifactId>bom</artifactId>
      <version>${aws.sdk.version}</version>
      <type>pom</type>
      <scope>import</scope>
    </dependency>
  </dependencies>
</dependencyManagement>

<dependencies>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>auth</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>regions</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>dynamodb</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
  </dependency>
  <dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sts</artifactId>
  </dependency>
</dependencies>
~~~

`2.x.y` là placeholder, không phải version phát hành. Chọn một SDK v2 version đã được kiểm tra trong project, import BOM để các modules đồng bộ. Không trộn SDK v1 (`com.amazonaws`) với v2 (`software.amazon.awssdk`) trong cùng cách cấu hình.

Nếu profile dùng IAM Identity Center/SSO, thêm các SDK modules cần thiết cho SSO provider theo hướng dẫn của SDK version đang dùng. Việc có file profile SSO không tự đảm bảo application classpath đã có SSO modules.

### 13.2. Client factory và reuse

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;

public final class AwsClients implements AutoCloseable {
    private final DefaultCredentialsProvider credentials;
    private final DynamoDbClient dynamoDb;
    private final S3Client s3;
    private final StsClient sts;

    public AwsClients(Region region) {
        this.credentials = DefaultCredentialsProvider.create();

        this.dynamoDb = DynamoDbClient.builder()
            .region(region)
            .credentialsProvider(credentials)
            .build();

        this.s3 = S3Client.builder()
            .region(region)
            .credentialsProvider(credentials)
            .build();

        this.sts = StsClient.builder()
            .region(region)
            .credentialsProvider(credentials)
            .build();
    }

    public DynamoDbClient dynamoDb() { return dynamoDb; }
    public S3Client s3() { return s3; }
    public StsClient sts() { return sts; }

    @Override
    public void close() {
        dynamoDb.close();
        s3.close();
        sts.close();
        credentials.close();
    }
}
~~~

Trong production, quản lý clients qua dependency injection/application lifecycle; không tạo factory cho từng request. Clients thread-safe và nên reuse. Nếu dùng chung credentials provider, chỉ đóng provider khi mọi clients đã ngừng sử dụng nó.

### 13.3. Validate effective Region khi startup

~~~java
import java.util.Set;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.regions.providers.DefaultAwsRegionProviderChain;

Region region = new DefaultAwsRegionProviderChain().getRegion();

Set<String> allowed = Set.of("ap-southeast-1", "ap-southeast-2");
if (!allowed.contains(region.id())) {
    throw new IllegalStateException("Configured AWS Region is not allowed");
}

log.info("AWS service Region configured: {}", region.id());
~~~

`getRegion()` có thể ném exception nếu không resolve được; hãy translate thành lỗi startup rõ ràng. Allowlist phù hợp app có deployment Region cố định; không hard-code allowlist nếu app được thiết kế multi-Region và có config policy riêng.

Không log credentials. Nếu account/Region là metadata nội bộ, log theo policy của tổ chức.

### 13.4. Endpoint override trong test profile

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.dynamodb.DynamoDbClient;

DynamoDbClient testClient = DynamoDbClient.builder()
    .region(Region.US_EAST_1)
    .endpointOverride(URI.create("http://localhost:4566"))
    .credentialsProvider(
        StaticCredentialsProvider.create(
            AwsBasicCredentials.create("test", "test")))
    .build();
~~~

Đây là **test-only credentials và endpoint**. Không dùng `AwsBasicCredentials` static trong production. LocalStack thường chấp nhận dummy credentials, nhưng điều đó không chứng minh AWS IAM policy/STS/credential refresh production hoạt động.

Đặt endpoint override trong test configuration tách biệt, không để biến môi trường của developer vô tình đi vào production container.

### 13.5. HTTP client và timeout

SDK v2 hỗ trợ synchronous và asynchronous HTTP clients. Chọn theo concurrency, streaming, application framework và operational requirements:

- Sync clients dùng HTTP implementation được cấu hình, ví dụ Apache hoặc URLConnection;
- Async clients thường dùng Netty/AWS CRT theo dependency/configuration;
- Đặt connection timeout, API call timeout và attempt timeout phù hợp SLO;
- Reuse HTTP connection pools;
- Không tắt TLS verification;
- Retry chỉ với lỗi phù hợp, lưu ý idempotency của writes.

Không dùng timeout cực lớn để che network failure. Cũng không retry toàn bộ exception indiscriminately; lỗi cấu hình/authorization không tự biến mất khi retry.

## 14. AWS CLI và Java SDK: cấu hình có thể khác nhau

### 14.1. Kiểm tra Region/identity qua CLI

Các lệnh **chỉ đọc**:

~~~bash
aws configure list
aws configure get region --profile dev
aws sts get-caller-identity --region ap-southeast-1
~~~

`aws configure list` hiển thị nguồn cấu hình của CLI, không chứng minh Java SDK v2 dùng cùng mọi giá trị. CLI và Java SDK có thể khác provider chain/version/configuration.

### 14.2. Kiểm tra environment variables

Linux/macOS:

~~~bash
printenv AWS_REGION
printenv AWS_PROFILE
~~~

PowerShell:

~~~powershell
Get-ChildItem Env:AWS_REGION
Get-ChildItem Env:AWS_PROFILE
~~~

Không dump toàn bộ environment trong logs/CI output vì có thể lộ secret variables.

### 14.3. Đọc profile config

~~~ini
[profile dev]
region = ap-southeast-1
output = json
credential_process = /usr/local/bin/company-credential-helper

[profile staging]
region = ap-southeast-2
role_arn = arn:aws:iam::111122223333:role/StagingDeveloper
source_profile = default
~~~

Nếu dùng `credential_process`, helper phải an toàn, thực thi được từ môi trường Java và trả output theo protocol; không ghi credentials vào stdout/stderr ngoài định dạng yêu cầu. Với production, ưu tiên workload roles.

### 14.4. Vì sao CLI thành công nhưng Java SDK thất bại?

Các nguyên nhân thường gặp:

- CLI profile được chọn qua `AWS_PROFILE` nhưng Java process không nhận biến đó;
- CLI dùng `AWS_DEFAULT_REGION`, Java SDK cần `AWS_REGION`/profile/explicit Region;
- CLI version hỗ trợ SSO/credential process nhưng Java SDK thiếu module/dependency hoặc version phù hợp;
- Java chạy trong container không mount config/cache;
- Java process có `-Daws.region` khác environment;
- SDK v1/v2 hoặc service module versions không đồng bộ;
- Proxy, trust store, DNS và HTTP client khác CLI;
- Java client có endpoint override hoặc signing Region khác.

**Đừng chỉ kiểm tra bằng `aws sts get-caller-identity` rồi kết luận Java app dùng cùng identity.** Hãy chẩn đoán ngay trong runtime Java theo nguồn credentials/Region đã redact.

## 15. Chẩn đoán lỗi Region và endpoint

### 15.1. NoRegion / Unable to load region

Nguyên nhân:

- Không có `aws.region`, `AWS_REGION` hoặc profile Region;
- Profile không được chọn đúng;
- Java process không nhìn thấy `~/.aws/config`;
- IMDS không khả dụng;
- `AWS_CONFIG_FILE` trỏ sai path.

Cách xử lý:

1. Log profile name ở mức được phép, không log secrets;
2. Kiểm tra `AWS_REGION`;
3. Kiểm tra JVM system property;
4. Đọc selected profile trong shared config;
5. Nếu EC2, kiểm tra IMDS options/network;
6. Hoặc truyền `.region(Region...)` rõ ràng.

### 15.2. UnknownHostException / connection timeout

Kiểm tra:

- Hostname có được endpoint rules tạo đúng không;
- DNS resolver và VPC DNS settings;
- PrivateLink interface endpoint/Private DNS;
- Route tables, NACL, SG, proxy;
- Service Region và endpoint availability;
- Endpoint override có bị để sót trong production config không.

DNS resolve thành công vẫn chưa chứng minh port/TLS/IAM hoạt động.

### 15.3. Unsupported Region / endpoint

SDK version cũ có thể chưa biết endpoint metadata cho Region/service mới. Cập nhật AWS SDK v2 lên version được tổ chức hỗ trợ. `Region.of(...)` tạo Region object nhưng không tự thêm service support hoặc endpoint rules mới.

### 15.4. Endpoint Region khác signing Region

Triệu chứng có thể là signature mismatch/authorization error. Kiểm tra:

- Client `.region(...)`;
- Region trong endpoint hostname;
- Custom endpoint's expected signing Region;
- ARN Region và service-specific routing;
- STS regional/global endpoint configuration nếu liên quan.

Không “fix” bằng cách thử random Region cho đến khi request thành công; điều đó có thể gửi dữ liệu sai Region.

### 15.5. FIPS/dual-stack endpoint không tồn tại

Service/Region/partition có thể chưa hỗ trợ combination yêu cầu. Kiểm tra AWS service endpoints documentation, SDK endpoint rules và DNS. Không hard-code suffix thay cho cấu hình FIPS/dual-stack.

## 16. Chẩn đoán lỗi SigV4 và credentials

### 16.1. SignatureDoesNotMatch

Kiểm tra theo thứ tự:

1. Signing Region và endpoint Region;
2. Service signing name (`dynamodb`, `s3`, `execute-api`...) có đúng không;
3. Đồng hồ UTC của máy có lệch không;
4. HTTP method/path/query có bị proxy thay đổi không;
5. Headers đã ký có bị thay đổi hoặc loại bỏ không;
6. Payload bytes có đổi sau khi ký không;
7. Temporary session token có được gửi không;
8. Access key và secret có thuộc cùng một credentials tuple không;
9. S3 path encoding/virtual-hosted style có đúng không.

Không gửi Authorization header hoặc secret key cho người khác để debug. Dùng SDK wire logging chỉ trong sandbox và **redact** sensitive headers/body.

### 16.2. Clock skew

SigV4 request có timestamp UTC; đồng hồ lệch có thể khiến AWS từ chối request. Đồng bộ host/container node qua NTP/time synchronization service. Không đổi timestamp thủ công hoặc tắt signature verification.

### 16.3. ExpiredToken / InvalidToken

Kiểm tra expiration và session token; credentials provider có refresh đúng không; SSO login đã hết hạn không; container/instance role endpoint có truy cập được không. Với static temporary credentials, thay bằng provider tự refresh.

### 16.4. AccessDenied không phải lúc nào cũng là chữ ký sai

Request có thể đã ký thành công nhưng bị chặn bởi:

- IAM identity policy;
- Resource policy (S3 bucket, SQS queue, KMS key, Lambda permission...);
- SCP/permission boundary/session policy;
- VPC endpoint policy;
- KMS key policy;
- Explicit Deny/condition;
- Region/resource/account mismatch.

Dùng CloudTrail và IAM policy evaluation theo quyền được cấp; không cấp AdministratorAccess để thử.

### 16.5. Bảng phân biệt lỗi

| Lỗi | Tầng | Hướng xử lý |
|---|---|---|
| NoRegion | Configuration | Region provider chain/profile |
| UnknownHost | DNS/network | Hostname, VPC DNS, endpoint |
| Connect timeout | Network | Routes, SG/NACL, port |
| TLS handshake/cert error | Transport security | CA bundle, hostname, trust store |
| SignatureDoesNotMatch | SigV4 canonicalization/scope | Region, service, timestamp, request bytes |
| ExpiredToken | Credentials | Refresh/session login |
| AccessDenied | Authorization | IAM/resource/SCP/KMS/endpoint policy |
| ThrottlingException | Service quota/load | Backoff, capacity, request patterns |
| SerializationException | Protocol/model | SDK module/version/request model |

## 17. Security best practices

### 17.1. Least privilege

- Dùng IAM roles cho workloads;
- Chỉ cho phép actions/resources cần thiết;
- Tách roles theo service/environment;
- Giới hạn S3 prefixes, DynamoDB tables/indexes và KMS keys;
- Không nhúng long-lived keys;
- Không dùng AdministratorAccess cho ứng dụng.

### 17.2. Region allowlisting và data residency

Nếu ứng dụng chỉ được phép hoạt động tại Singapore/Australia, validate Region từ deployment configuration trước khi build client. Đừng cho request người dùng truyền `region=...` trực tiếp và tạo client theo giá trị tùy ý.

### 17.3. TLS và endpoint security

- Dùng HTTPS/TLS cho AWS endpoints;
- Không disable certificate verification;
- PrivateLink endpoints cần kiểm tra Private DNS, SG và endpoint policy;
- Custom endpoint phải thuộc trust boundary;
- Không để endpoint override do untrusted input kiểm soát vì có thể tạo SSRF.

### 17.4. Không log secrets hoặc request signature

Cần redact:

- Authorization;
- X-Amz-Security-Token;
- Access key/session token;
- Presigned URL query string;
- Sensitive request body;
- SSO cache/token files.

Có thể log service, operation, Region, request ID, latency, retry count và endpoint mode đã chuẩn hóa.

### 17.5. Presigned URL là quyền truy cập

- Thời hạn ngắn;
- Method và object key cụ thể;
- S3 bucket private;
- Validate authorization trước khi ký;
- Không dùng URL làm user identity;
- Không log/forward URL cho hệ thống không tin cậy;
- Có checksum, content-type/size policy và malware scanning khi upload.

## 18. Kiểm thử Region, endpoint và SigV4

### 18.1. Unit tests cho configuration

Có thể test thứ tự ưu tiên bằng **process riêng** vì system properties/environment variables là global process configuration. Không thay environment giữa các test song song rồi mong kết quả ổn định.

| Case | System property | Env | Profile | Kỳ vọng |
|---|---|---|---|---|
| 1 | `aws.region=us-west-2` | `AWS_REGION=ap-southeast-1` | `eu-west-1` | `us-west-2` |
| 2 | none | `AWS_REGION=ap-southeast-1` | `eu-west-1` | `ap-southeast-1` |
| 3 | none | none | `region=eu-west-1` | `eu-west-1` |
| 4 | none | none | none, no IMDS | NoRegion exception |
| 5 | explicit builder Region | any | any | Explicit Region |

Không chạy case 4 trên EC2 có IMDS nếu muốn kiểm chứng “không có provider”; isolate environment hoặc inject test provider.

### 18.2. Endpoint tests

- Default endpoint cho service + Region;
- China/GovCloud partition nếu ứng dụng hỗ trợ;
- Endpoint override trong test profile;
- FIPS/dual-stack combinations được service hỗ trợ;
- S3 access point/MRAP ARN;
- PrivateLink DNS và network path;
- Kiểm tra custom endpoint không bật trong production ngoài ý muốn.

### 18.3. SigV4 integration tests

Dùng AWS sandbox hoặc service emulator có hỗ trợ phù hợp:

- Request có signed headers hợp lệ;
- Temporary credentials có session token;
- Expired token và clock skew được phân loại;
- Proxy không sửa path/query/host/body;
- Presigned URL method/expiry/headers khớp;
- IAM AccessDenied khác signature failure;
- Không in credentials/Authorization trong test report.

### 18.4. Kiểm tra caller identity trong Java

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

try (StsClient sts = StsClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build()) {
    GetCallerIdentityResponse identity = sts.getCallerIdentity();
    log.info("AWS account={}, arn={}",
        identity.account(), identity.arn());
}
~~~

`GetCallerIdentity` giúp xác định AWS principal mà client đang dùng. Dù action thường không cần IAM allow explicit, network/endpoint vẫn phải hoạt động. Account/ARN có thể là metadata nội bộ; chỉ log ở mức được phép.

## 19. Bài tập tình huống

### 19.1. Đề bài

Một Java 17 Spring Boot service chạy ở ba môi trường:

- Developer laptop sử dụng IAM Identity Center profile `dev`;
- CI sử dụng OIDC assume role;
- Production chạy trên ECS task role ở `ap-southeast-1`.

Service gọi DynamoDB và S3. Integration test dùng LocalStack. Một số khách hàng ở Australia có metadata đặt ở `ap-southeast-2`. Ứng dụng cần presigned S3 download URL trong 10 phút.

Hãy thiết kế:

1. Region config cho từng service/environment;
2. Credentials provider cho laptop/CI/ECS;
3. Endpoint override chỉ bật trong test;
4. DynamoDB/S3 clients reuse theo Region;
5. SigV4 signing context đúng service/Region;
6. Presigned URL expiry/authorization;
7. Logging/monitoring không lộ secrets;
8. Fail-fast nếu production cấu hình nhầm Region.

### 19.2. Cấu hình tham khảo

~~~text
Developer laptop:
  AWS_PROFILE=dev
  ~/.aws/config profile dev region=ap-southeast-1
  IAM Identity Center login via AWS CLI

CI:
  OIDC -> assume role
  AWS_REGION=ap-southeast-1
  no long-lived static keys

Production ECS:
  Task role
  AWS_REGION=ap-southeast-1
  no shared credentials file
  private VPC endpoint/network as required

LocalStack test:
  endpointOverride=http://localhost:4566
  Region=us-east-1 (test signing context)
  dummy test credentials
  isolated test data only
~~~

Australia workload:

~~~text
DynamoDB client for Singapore -> ap-southeast-1
DynamoDB client for Australia -> ap-southeast-2
S3 presigner -> Region of the bucket/resource selected by trusted config
~~~

Không lấy Region từ untrusted request parameter. Hãy resolve tenant-to-Region mapping từ backend config/metadata có xác thực.

### 19.3. Phân tích thiết kế

- **Laptop:** profile `dev` chứa Region và SSO configuration; SDK dùng profile credentials provider phù hợp.
- **CI:** OIDC federation cấp role credentials tạm thời; không lưu static access keys.
- **ECS:** task role cấp credentials; environment/config xác định Region; không mount developer credentials.
- **LocalStack:** endpoint override chỉ được kích hoạt trong test profile, dùng dummy credentials và dữ liệu giả.
- **Multi-Region:** build/reuse clients riêng cho `ap-southeast-1` và `ap-southeast-2`; mapping Region do backend quyết định.
- **Presigned URL:** kiểm tra authorization tới object trước khi ký; thời hạn 10 phút; không log URL.
- **SigV4:** SDK tự ký với credentials và Region tương ứng; không tự ghép Authorization header.

### 19.4. Câu hỏi tự đánh giá

1. Default Region provider chain của Java SDK v2 kiểm tra những nguồn nào và theo thứ tự nào?
2. `aws.region` và `AWS_REGION` khác nhau ra sao?
3. `AWS_DEFAULT_REGION` có phải biến environment chuẩn của Java SDK v2 default Region chain không?
4. Region provider chain khác credentials provider chain thế nào?
5. `AWS_PROFILE` chọn profile nào? Region của profile thường được lưu ở file nào?
6. `sso_region` khác `region` của service client như thế nào?
7. Khi nào SDK dùng IMDS để lấy Region?
8. Vì sao `Region.of(...)` không đảm bảo service/Region được hỗ trợ?
9. Tại sao explicit `.region(...)` ghi đè default chain?
10. Vì sao endpoint override vẫn cần Region?
11. Endpoint resolution khác việc hard-code hostname như thế nào?
12. FIPS và dual-stack có tự bảo đảm compliance/IPv6 connectivity không?
13. Canonical request gồm những thành phần nào?
14. Vì sao Host header và signed headers phải giữ nguyên sau khi ký?
15. Credential scope gồm date, Region, service và chuỗi nào?
16. Signing key được derive qua những bước nào?
17. Temporary credentials cần thêm trường gì ngoài access key và secret?
18. SigV4 có phải mã hóa dữ liệu thay cho TLS không?
19. Vì sao request signature đúng vẫn có thể bị AccessDenied?
20. Presigned URL là bearer capability và cần bảo vệ ra sao?
21. Vì sao temporary credentials có thể làm presigned URL hết hạn sớm hơn X-Amz-Expires?
22. SigV4a khác SigV4 ở mục đích/Region handling nào?
23. Vì sao AWS CLI thành công không chứng minh Java SDK dùng cùng profile/Region?
24. Khi nào nên reuse SDK clients thay vì build theo từng request?
25. Vì sao không nên tự viết SigV4 signer trong business code?

### 19.5. Đáp án gợi ý

1. JVM `aws.region` → `AWS_REGION` → selected shared config profile → EC2 IMDS.
2. Một là JVM system property, một là environment variable; system property được ưu tiên trước.
3. Không nên dựa vào `AWS_DEFAULT_REGION` cho Java SDK v2; dùng `AWS_REGION`/profile/explicit Region.
4. Region chain chọn Region; credentials chain chọn identity/secret credentials.
5. `AWS_PROFILE` chọn profile; Region nằm trong `~/.aws/config`.
6. `sso_region` cho Identity Center service; `region` cho AWS service client mặc định.
7. Khi các provider trước không tìm thấy Region và EC2 metadata khả dụng.
8. Object tạo được không đồng nghĩa AWS service endpoint/feature tồn tại.
9. Builder explicit config được dùng cho client thay vì resolve chain.
10. Region vẫn dùng trong signing scope và service behavior.
11. SDK dùng service rules/partition/features; hostname thủ công dễ sai.
12. Không; phải kiểm tra service support, routes, DNS, policy và compliance tổng thể.
13. Method, canonical URI, canonical query, canonical headers, signed headers, payload hash.
14. Vì signature được tính trên canonical representation; thay đổi sau ký làm hash/signature lệch.
15. `aws4_request`.
16. Secret+date → Region → service → `aws4_request`.
17. Session token và expiration.
18. Không; TLS mã hóa transport, SigV4 ký/xác thực request.
19. IAM/resource/SCP/KMS/VPC endpoint policy có thể deny.
20. Ai có URL có thể dùng request đã ký; hạn ngắn, không log/chia sẻ công khai.
21. URL không thể sống lâu hơn credentials đã dùng để ký.
22. SigV4 scope theo Region cụ thể; SigV4a hỗ trợ multi-Region signing theo tính năng.
23. CLI và Java SDK có thể đọc biến/profile/dependencies khác nhau.
24. SDK clients thread-safe và quản lý HTTP pools; reuse giảm overhead/churn.
25. Canonicalization, session tokens, endpoint rules, streaming và clock skew dễ sai.

## 20. Checklist triển khai production

### Region và identity

- [ ] Region được xác định tường minh hoặc từ provider chain đã kiểm thử.
- [ ] Không dựa vào `AWS_DEFAULT_REGION` cho Java SDK v2 nếu chưa xác minh behavior.
- [ ] Profile được chọn đúng; `region` và `sso_region` không bị nhầm.
- [ ] Workload credentials dùng SSO/OIDC/task role/instance role phù hợp.
- [ ] Không có long-lived access keys trong source, image, CI logs.
- [ ] Region/partition được allowlist theo data residency/compliance.

### Endpoint và network

- [ ] Service endpoint được SDK resolve theo Region/partition rules.
- [ ] `endpointOverride` chỉ bật trong môi trường cần thiết.
- [ ] Endpoint override vẫn có signing Region đúng.
- [ ] FIPS/dual-stack chỉ bật khi service/Region hỗ trợ.
- [ ] PrivateLink/DNS/SG/routes/TLS đã được test từ runtime.
- [ ] S3 addressing/access point/MRAP behavior đã được kiểm thử.
- [ ] Không log full presigned URLs hoặc auth query strings.

### SigV4 và security

- [ ] SDK signer được sử dụng thay manual Authorization header.
- [ ] Region, service signing name, timestamp và credential scope nhất quán.
- [ ] Temporary credentials có session token và refresh.
- [ ] Host/path/query/body/headers không bị proxy thay đổi sau ký.
- [ ] Clock sync/NTP hoạt động.
- [ ] TLS certificate/hostname verification bật.
- [ ] Least privilege được áp dụng; signature không bị nhầm là IAM authorization.
- [ ] Secrets, Authorization, session tokens và presigned URL được redact.

### Reliability và operations

- [ ] SDK clients reuse và đóng theo application lifecycle.
- [ ] Timeout/retry/backoff theo SLO và idempotency.
- [ ] Startup validation báo rõ lỗi Region/profile/endpoint.
- [ ] CloudTrail/metrics/request IDs được dùng để chẩn đoán.
- [ ] Unit/integration tests bao gồm Region precedence, endpoint override và SigV4.
- [ ] LocalStack/test credentials không đi vào production.
- [ ] SDK version/BOM được quản lý và cập nhật theo dependency policy.

**Kết quả mong đợi:** người học có thể cấu hình đúng Region và endpoint cho Java SDK v2 trên laptop, CI và AWS workloads; phân biệt Region/credentials chains; giải thích và xử lý SigV4 signing; sử dụng presigned URLs an toàn; và chẩn đoán lỗi endpoint/signature mà không làm lộ credentials.

## Tài liệu AWS chính thức

- [AWS SDK for Java 2.x — Region selection](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/region-selection.html)
- [AWS SDK for Java 2.x — Credentials](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials.html)
- [AWS SDK for Java 2.x — Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [AWS SDK for Java 2.x — Configuration and profiles](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-profiles.html)
- [AWS SDK for Java 2.x — Endpoint configuration](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/endpoint-config.html)
- [AWS SDK for Java 2.x — Endpoint discovery](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/endpoint-discovery.html)
- [AWS SDK for Java 2.x — FIPS endpoints](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/fips-endpoints.html)
- [AWS SDK for Java 2.x — Dual-stack endpoints](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/dualstack-endpoints.html)
- [AWS SDK for Java 2.x — IAM Identity Center credentials](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-sso.html)
- [AWS SDK for Java 2.x — Best practices](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/best-practices.html)
- [AWS Signature Version 4 signing process](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-signing-elements.html)
- [Create a canonical request for SigV4](https://docs.aws.amazon.com/IAM/latest/UserGuide/create-signed-request.html)
- [Derive a signing key for SigV4](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-create-signed-request.html)
- [Signing AWS API requests](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv.html)
- [SigV4 presigned URL considerations](https://docs.aws.amazon.com/AmazonS3/latest/userguide/using-presigned-url.html)
- [AWS Signature Version 4A](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_sigv-signing-elements.html)
- [AWS service endpoints and quotas](https://docs.aws.amazon.com/general/latest/gr/aws-service-information.html)
- [AWS partitions and ARNs](https://docs.aws.amazon.com/IAM/latest/UserGuide/reference-arns.html)
- [Amazon EC2 instance metadata and IMDSv2](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/configuring-instance-metadata-service.html)
- [AWS Pricing Calculator](https://calculator.aws/)

> **Lưu ý áp dụng:** Các profile, Region, account IDs, hostnames, credentials, endpoint URLs và code trong bài là **ví dụ đào tạo**. Không dùng credentials giả định trong production. Endpoint availability, signer behavior và SDK APIs có thể thay đổi theo service/Region/SDK version; hãy xác minh tài liệu AWS hiện hành, thử nghiệm trong sandbox, bảo vệ secrets và tuân thủ quy trình phê duyệt thay đổi.

