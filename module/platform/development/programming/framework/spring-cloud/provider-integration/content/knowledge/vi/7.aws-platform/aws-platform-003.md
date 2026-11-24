# DefaultCredentialsProvider và chuỗi tìm region

## 1. Vì sao ứng dụng Spring Boot cần hiểu credential và region?

Ứng dụng Spring Boot có thể được viết rất ngắn để lưu tệp lên Amazon S3 hoặc nhận thông điệp từ Amazon SQS nhờ Spring Cloud AWS của **AWSpring**. Tuy nhiên, trước khi gửi được một yêu cầu AWS, client phải giải quyết hai câu hỏi độc lập:

1. **Đang gọi AWS với danh tính nào?** SDK cần credential thích hợp để ký và xác thực request. Danh tính sau cùng được ràng buộc bởi IAM role, policy và tài nguyên.
2. **Đang gọi vào vùng AWS nào?** SDK cần một `Region` để xây dựng endpoint vùng và ký request đúng ngữ cảnh dịch vụ.

Đây là kiến thức nền của chương **Nền tảng AWS** trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**: thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure, Google Cloud; quản lý danh tính và quyền, storage, messaging, dữ liệu, secret và kiểm thử tích hợp. Trong bài này, trọng tâm là cơ chế mặc định của **AWS SDK for Java 2.x**, nền tảng mà Spring Cloud AWS 3.x thường sử dụng.

**Mục tiêu học tập**:

- Mô tả đúng thứ tự mà `DefaultCredentialsProvider` thử các nguồn credential.
- Phân biệt credential, IAM permission, AWS account, profile, role và region.
- Giải thích thứ tự tìm region của `DefaultAwsRegionProviderChain` và khi nào nên chỉ định region tường minh.
- Cấu hình Spring Boot/AWSpring trên laptop, CI, ECS, EKS và EC2 mà không đưa access key dài hạn vào mã nguồn.
- Chẩn đoán chính xác các nhóm lỗi: thiếu credential, sai region/endpoint, `AccessDenied`, token hết hạn và resource không tồn tại.
- Viết kiểm thử có thể tái lập mà không vô tình dùng credential production.

> **Phạm vi phiên bản:** Tên lớp, biến môi trường và thứ tự tìm kiếm mô tả **AWS SDK for Java v2**. Hệ sinh thái AWSpring, Spring Boot và các môi trường AWS thay đổi theo phiên bản. Trước khi áp dụng cho production, kiểm tra tài liệu của đúng bản SDK/AWSpring đang dùng và xem cấu hình bean nào có thể ghi đè mặc định.

## 2. Hai chuỗi tìm kiếm khác nhau

`DefaultCredentialsProvider` giải quyết **credential**. `DefaultAwsRegionProviderChain` giải quyết **region**. Chúng không đồng nghĩa và không thay thế cho nhau.

~~~mermaid
flowchart LR
    APP["Spring Boot service"] --> AWS["AWSpring auto-configuration / AWS SDK v2 client"]
    AWS --> C["Credentials provider"]
    AWS --> R["Region provider"]
    C --> ID["Access key ID + secret + optional session token"]
    R --> REG["Region, ví dụ ap-southeast-1"]
    ID --> SIGN["Ký yêu cầu"]
    REG --> SIGN
    SIGN --> API["AWS service endpoint"]
    API --> IAM["AWS xác thực và đánh giá IAM/resource policy"]
~~~

Về mặt khái niệm, một SDK client cần cấu hình tương tự:

~~~java
S3Client client = S3Client.builder()
        .credentialsProvider(credentialsProvider)
        .region(region)
        .build();
~~~

Khi không truyền `credentialsProvider(...)` hoặc `region(...)`, nhiều client SDK v2 sử dụng provider chain mặc định tương ứng. **Credential hợp lệ không ngụ ý region hợp lệ**, và biết region cũng không tạo ra quyền IAM.

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Credential | Access key, secret key, session token | Chất liệu để SDK xác thực/ký request |
| Principal | IAM role dành cho ECS task | Danh tính AWS được đánh giá quyền |
| Policy | Cho phép `s3:PutObject` vào một ARN | Quyền của principal và chính sách trên resource |
| Region | `ap-southeast-1` | Vùng endpoint/dịch vụ được truy cập |
| Profile | `dev-sandbox` | Tên một tập cấu hình cục bộ, có thể chứa cách lấy credential và region |
| Endpoint | URL của service hoặc giả lập LocalStack | Đích mạng của client; có liên hệ với region nhưng không phải chính region |

**Ví dụ:** Có credential từ role production nhưng region được đặt thành `us-east-1` trong khi queue SQS chỉ tồn tại ở `ap-southeast-1`. SDK vẫn có thể lấy credential và ký request; yêu cầu sau đó lỗi do endpoint/queue/vùng không phù hợp. Đây không phải lý do để tạo thêm access key.

## 3. DefaultCredentialsProvider là gì?

Trong AWS SDK for Java v2, `software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider` là provider dựng sẵn, đại diện cho **một chuỗi các nguồn credential**. Nó lần lượt thử các nguồn theo thứ tự ưu tiên; nguồn đầu tiên trả về credential hợp lệ cho bước resolve sẽ được dùng.

Việc gọi:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;

var provider = DefaultCredentialsProvider.create();
~~~

không tạo IAM user, không đăng nhập vào AWS và không cấp quyền cho ứng dụng. Provider chỉ biết **cách lấy credential tại runtime**. Các credential có thể là cặp key cố định ở môi trường phát triển hoặc temporary credential từ role/workload identity khi chạy thật.

### 3.1. Thứ tự tìm credential trong SDK v2

Với `DefaultCredentialsProvider` tiêu chuẩn, thứ tự được mô tả như sau:

| Ưu tiên | Provider con | Nguồn dữ liệu chính | Trường hợp thường gặp |
| --- | --- | --- | --- |
| 1 | `SystemPropertyCredentialsProvider` | Java system properties `aws.accessKeyId`, `aws.secretAccessKey`; token nếu có | Ứng dụng Java được khởi chạy với `-D...` |
| 2 | `EnvironmentVariableCredentialsProvider` | `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`; `AWS_SESSION_TOKEN` nếu credential tạm | Shell, container, CI |
| 3 | `WebIdentityTokenFileCredentialsProvider` | `AWS_WEB_IDENTITY_TOKEN_FILE` + `AWS_ROLE_ARN`, hoặc Java system properties tương ứng | EKS IRSA, OIDC/web identity |
| 4 | `ProfileCredentialsProvider` | Profile trong AWS shared config/credentials files | Máy cá nhân, AWS CLI profile, role/SSO qua profile |
| 5 | `ContainerCredentialsProvider` | Endpoint credential do môi trường container công bố, thường qua `AWS_CONTAINER_CREDENTIALS_RELATIVE_URI` / `AWS_CONTAINER_CREDENTIALS_FULL_URI` | ECS task role và một số cơ chế workload identity cho container |
| 6 | `InstanceProfileCredentialsProvider` | IAM role thông qua EC2 Instance Metadata Service (IMDS) | EC2 instance profile |

Các nguồn được kiểm tra **theo thứ tự**, không phải cộng gộp credential. Nếu nguồn ưu tiên cao cung cấp credential, các nguồn thấp hơn thường không được dùng cho lần resolve đó. Việc cache provider đã dùng có thể làm ứng dụng tiếp tục dùng nguồn được chọn cho các lần resolve sau.

~~~mermaid
flowchart TD
    A["DefaultCredentialsProvider"] --> B{"Java system properties có credential?"}
    B -->|Có| Z["Dùng credential"]
    B -->|Không| C{"AWS_* credential ở environment?"}
    C -->|Có| Z
    C -->|Không| D{"Web identity token + role ARN?"}
    D -->|Có| Z
    D -->|Không| E{"Shared AWS profile có credential?"}
    E -->|Có| Z
    E -->|Không| F{"Container credential endpoint?"}
    F -->|Có| Z
    F -->|Không| G{"EC2 instance profile qua IMDS?"}
    G -->|Có| Z
    G -->|Không| H["Không tìm được credential -> lỗi resolve"]
~~~

**Lưu ý điều kiện phụ:** Một số loại provider, chẳng hạn web identity, assume role và đăng nhập SSO thông qua profile, cần các SDK module hỗ trợ STS/SSO phù hợp trên classpath. Nếu thiếu module cần thiết hoặc cấu hình nguồn sai, chuỗi không thể “tự sửa” lỗi. Thông điệp lỗi thực tế thường liệt kê những provider đã thử và nguyên nhân tương ứng.

### 3.2. Java system properties khác environment variables

Hai cơ chế là hai nguồn ưu tiên **khác nhau**:

~~~text
# Java system property; minh họa cú pháp, KHÔNG chèn secret thật vào command:
-Daws.accessKeyId=EXAMPLE -Daws.secretAccessKey=EXAMPLE

# Environment variable; tên được SDK Java v2 nhận diện:
AWS_ACCESS_KEY_ID
AWS_SECRET_ACCESS_KEY
AWS_SESSION_TOKEN
~~~

Không đưa key thật vào tham số command, log, CI output hoặc repository; chúng có thể bị lộ qua lịch sử shell/process metadata. Mục đích ví dụ chỉ là nhận diện tên và ưu tiên. Với production trên AWS, ưu tiên IAM role và temporary credential.

Nếu container đồng thời có `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` **và** ECS task role, SDK có thể dùng credential từ environment trước khi đến container credential endpoint. Đây là một nguyên nhân phổ biến khiến application “đang gắn đúng role nhưng vẫn dùng tài khoản khác”.

### 3.3. Web identity trong EKS và các workload OIDC

Web identity cho phép workload chứng minh danh tính qua token từ hệ thống bên ngoài, rồi dùng AWS STS để nhận temporary AWS credential. Trong EKS, **IAM Roles for Service Accounts (IRSA)** thường cung cấp:

~~~text
AWS_ROLE_ARN
AWS_WEB_IDENTITY_TOKEN_FILE
~~~

SDK/STS đọc token, gọi cơ chế assume role phù hợp và nhận credential tạm. Token file cần tồn tại và trust policy của IAM role phải cho phép đúng identity/OIDC provider.

**Không nhầm IRSA với EKS Pod Identity.** IRSA thường đi qua web identity provider; EKS Pod Identity có cơ chế agent/container credential endpoint tương ứng. Cả hai đều hướng tới temporary credential mà không nhúng secret cố định vào ứng dụng, nhưng đường đi provider là khác nhau.

### 3.4. AWS profile là nhiều kiểu credential, không chỉ access key

`ProfileCredentialsProvider` đọc profile từ shared config và credentials files (theo cấu hình thông thường tại `~/.aws/config` và `~/.aws/credentials`). Profile có thể mô tả:

- Credential tĩnh hoặc credential có session token trong môi trường phát triển.
- SSO/IAM Identity Center, với token được chuẩn bị bằng quy trình đăng nhập phù hợp.
- Assume role dựa vào `source_profile` hoặc credential source.
- `credential_process` cung cấp credential theo định dạng được SDK hỗ trợ.

Ví dụ file `~/.aws/config` chỉ chứa cấu hình vùng và tên profile, **không chứa secret**:

~~~ini
[profile dev-sandbox]
region = ap-southeast-1
output = json
~~~

Trước khi chạy ứng dụng cục bộ, có thể chọn profile bằng biến môi trường:

~~~bash
export AWS_PROFILE=dev-sandbox
~~~

Trên Windows PowerShell, có thể dùng:

~~~powershell
$env:AWS_PROFILE = "dev-sandbox"
~~~

Việc chọn profile không tự đăng nhập, không tạo credential, không thêm IAM permission. Nếu profile dựa vào SSO, cần thực hiện đăng nhập bằng quy trình được tổ chức cho phép. Nếu profile chỉ có region mà không có nguồn credential hợp lệ, SDK vẫn có thể không tìm được credential.

**Điểm cần nhớ:** tên profile ảnh hưởng cả việc SDK chọn cấu hình credential *và* profile được tra khi tìm region, nhưng hai chuỗi tra cứu vẫn độc lập; một trong hai có thể bị ghi đè bằng nguồn ưu tiên cao hơn.

### 3.5. Temporary credential được làm mới như thế nào?

Temporary AWS credential gồm access key ID, secret access key và **session token**, có thời điểm hết hạn. Provider cho role (web identity, ECS task, EC2 instance profile, assume role theo profile...) được thiết kế để có thể nhận và làm mới credential theo khả năng của nguồn.

Không copy kết quả từ `resolveCredentials()` vào một `StaticCredentialsProvider` để dùng cả ngày; hành động đó có thể làm mất cơ chế refresh và gây `ExpiredToken`. Tương tự, không cache chuỗi access key/secret token trong biến global và tự gắn token vào request.

Nếu tổ chức sử dụng STS assume role theo cách lập trình riêng, cần thiết kế vòng đời/refresh của `StsAssumeRoleCredentialsProvider`, thay vì tự gọi assume role một lần lúc startup rồi giữ mãi kết quả.

## 4. Chuỗi tìm region của AWS SDK for Java v2

Các client theo vùng của AWS SDK cần biết region khi xây dựng và ký request. Với mặc định của SDK v2, chuỗi `DefaultAwsRegionProviderChain` có thứ tự tìm kiếm cơ bản:

| Ưu tiên | Nguồn region | Ví dụ | Ghi chú |
| --- | --- | --- | --- |
| Trước chuỗi | `.region(Region...)` được đặt trực tiếp trên client builder | `Region.AP_SOUTHEAST_1` | Cấu hình tường minh có ưu tiên hơn region chain của client |
| 1 | Java system property `aws.region` | `-Daws.region=ap-southeast-1` | Ưu tiên trên environment |
| 2 | Environment variable `AWS_REGION` | `AWS_REGION=ap-southeast-1` | Phù hợp container/CI |
| 3 | Region trong shared AWS profile | `region = ap-southeast-1` | Theo profile được chọn; thường ở `~/.aws/config` |
| 4 | EC2 instance metadata (IMDS) | Vùng của EC2 instance đang chạy | Chỉ khả dụng khi metadata có thể truy cập và được phép |

Nếu không có nguồn phù hợp, SDK có thể báo không xác định được region, ví dụ lỗi liên quan `SdkClientException` khi xây dựng client hoặc thực thi request. **Không có cơ chế “tự suy ra mọi region” chỉ từ access key**.

Một số công cụ và ngôn ngữ AWS hỗ trợ `AWS_DEFAULT_REGION`. Với **AWS SDK for Java v2**, không nên phụ thuộc riêng vào tên đó để cấu hình region: dùng `AWS_REGION`, `aws.region`, profile hoặc builder tường minh theo tài liệu SDK. Đây là bẫy dễ gặp khi chuyển từ AWS CLI hoặc SDK ngôn ngữ khác.

### 4.1. Explicit region và endpoint override có ý nghĩa khác nhau

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

try (S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .build()) {
    // S3 client dùng default credential chain nếu không có override riêng.
}
~~~

`.region(...)` chọn region mà client dùng để xác định endpoint/ký yêu cầu. Trong kiểm thử local, `.endpointOverride(...)` cho phép gọi một URL khác, nhưng **vẫn cần region để signing** và xử lý request. Endpoint không phải cách thay thế hoàn toàn cho region.

### 4.2. Lỗi region không phải lỗi credential

Ví dụ người phát triển dùng:

~~~text
AWS_PROFILE=dev-sandbox
AWS_REGION=us-east-1
~~~

trong khi `~/.aws/config` của profile ghi `region = ap-southeast-1`. Region lấy từ biến môi trường có ưu tiên cao hơn profile, nên client mặc định có thể dùng `us-east-1`. Nếu SQS queue chỉ tồn tại tại Singapore, request có thể truy vấn sai vùng hoặc thất bại.

Một trường hợp ngược lại: `AWS_REGION` đúng nhưng credential từ một environment key cũ đã hết quyền. Sửa region không giải quyết được `AccessDenied`. Hãy chẩn đoán hai đường này riêng.

## 5. AWSpring và Spring Boot tương tác với provider chain ra sao?

Spring Cloud AWS tích hợp SDK thông qua bean/auto-configuration và properties của Spring Boot. Trong dòng AWSpring 3.x thông dụng, có thể cấu hình region tường minh cho các bean mà AWSpring quản lý:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION}

app:
  storage:
    bucket: ${APP_S3_BUCKET}
  messaging:
    queue: ${APP_SQS_QUEUE}
~~~

Ví dụ trên yêu cầu ứng dụng có biến môi trường `AWS_REGION`, `APP_S3_BUCKET`, `APP_SQS_QUEUE`; chúng **không tự được tạo**. Đường dẫn `spring.cloud.aws.region.static` thuộc cấu hình của AWSpring, không phải Java system property `aws.region` của SDK; AWSpring có thể dùng nó để cấu hình bean SDK của mình.

Khi cấu hình Spring Boot chỉ rõ một region hoặc khi ứng dụng tự khai báo bean client:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

@Configuration
class AwsClientConfiguration {
    @Bean
    S3Client s3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

bean trên dùng region đã đặt trực tiếp trên builder, kể cả `AWS_REGION` bên ngoài khác. Credential mặc định vẫn được dùng vì không cấu hình provider riêng.

**Ranh giới quan trọng:** AWSpring có cơ chế để cấu hình credential profile, static key, region và custom bean tùy phiên bản. Khi một `AwsCredentialsProvider` hoặc bean client được cấu hình tường minh, mặc định của SDK có thể bị thay thế. Vì vậy, nếu thấy credential/region thực tế khác kỳ vọng, hãy kiểm tra **cả** Spring properties, bean cấu hình riêng, Java system properties và môi trường runtime.

Không thêm các property chứa access key/secret key tĩnh vào `application.yml` hoặc commit file `application-prod.yml` chứa secret. Trên AWS, ưu tiên để workload identity/role cung cấp temporary credential và để ứng dụng sử dụng provider chain mặc định.

### 5.1. Mã SDK v2 dùng mặc định đầy đủ

Nếu đã cấu hình credential và region qua môi trường hoặc profile, client có thể đơn giản như sau:

~~~java
import software.amazon.awssdk.services.s3.S3Client;

try (S3Client s3 = S3Client.create()) {
    // Khi cần gọi S3, SDK sử dụng credential và region mặc định.
}
~~~

`S3Client.create()` tiện cho ứng dụng SDK thuần; trong ứng dụng Spring Boot dùng AWSpring, thường ưu tiên inject bean `S3Client` do Spring quản lý nếu starter/config đã cung cấp. Điều này giữ nhất quán cấu hình, lifecycle, tracing và tùy chỉnh.

Ví dụ service:

~~~java
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;

@Service
public class FileInfoService {
    private final S3Client s3;

    public FileInfoService(S3Client s3) {
        this.s3 = s3;
    }

    public long fileSize(String bucket, String key) {
        return s3.headObject(req -> req.bucket(bucket).key(key))
                 .contentLength();
    }
}
~~~

Ứng dụng cần có starter/module tạo bean `S3Client` hoặc bean được cấu hình chủ đích, cùng quyền IAM phù hợp để đọc metadata đối tượng.

### 5.2. Khi nào cố định region trong cấu hình?

- **Nên cấu hình tường minh** nếu ứng dụng chuyên phục vụ bucket/queue/table trong một region rõ ràng, triển khai đa môi trường hoặc không chạy trên EC2.
- **Có thể dùng chain** nếu hạ tầng triển khai chuẩn hóa `AWS_REGION`/profile và ứng dụng đã có kiểm tra cấu hình startup.
- **Không nên ghi cứng region cho mọi tài nguyên** trong ứng dụng truy cập đa vùng: cần xây client theo từng region/nguồn tài nguyên và kiểm soát rõ endpoint.

Trong kiến trúc đa region, không nên thay đổi `AWS_REGION` toàn cục trong quá trình chạy để chuyển client. SDK client được cấu hình khi xây dựng; tạo các client với region riêng hoặc dùng factory phù hợp, và quản lý vòng đời chúng.

## 6. Cấu hình theo từng môi trường chạy

| Môi trường | Cách lấy credential nên ưu tiên | Cách xác định region | Sai lầm thường gặp |
| --- | --- | --- | --- |
| Máy phát triển | AWS profile, SSO/IAM Identity Center, assume role theo profile | `AWS_REGION` hoặc region trong profile | Environment key cũ ghi đè profile |
| Local container | Profile/SSO được mount và cấp quyền phù hợp, hoặc credential tạm do công cụ dev cung cấp | `AWS_REGION` tường minh | Container không có config/profile file của host |
| ECS/Fargate | **Task role**, thông qua container credential provider | Thường dùng `AWS_REGION` từ môi trường triển khai | Nhầm task execution role với application task role |
| EKS với IRSA | Web identity token + role ARN | `AWS_REGION` hoặc cấu hình ứng dụng | Thiếu trust policy / STS module cần thiết |
| EKS Pod Identity | Credential endpoint do agent cung cấp | `AWS_REGION` hoặc config rõ ràng | Cho rằng cơ chế giống hệt IRSA |
| EC2 | Instance profile qua IMDS | `AWS_REGION`/profile hoặc IMDS nếu khả dụng | IMDS bị tắt/chặn, instance role sai quyền |
| CI ngoài AWS | OIDC federation/assume role hoặc credential tạm qua hệ thống CI | Biến môi trường của job | Lưu access key dài hạn trong CI secret |
| Test LocalStack | Static credential giả **chỉ trong test**, cùng endpoint override | Region giả lập được chọn tường minh | Để test endpoint/credential lọt vào production |

### 6.1. ECS task role và task execution role

ECS dùng **task execution role** cho những việc của nền tảng như lấy image hoặc gửi log theo cấu hình; **task role** mới là principal mà mã ứng dụng trong container thường dùng để gọi S3, SQS, Secrets Manager. Nếu có `AccessDenied`, kiểm tra role thực sự được gắn làm task role; đừng chỉ nhìn execution role.

ECS thường cung cấp đường lấy temporary credential cho container qua endpoint và biến môi trường do nền tảng quản lý. SDK v2 `ContainerCredentialsProvider` nhận credential từ endpoint này khi những nguồn ưu tiên cao hơn không cung cấp credential.

### 6.2. EKS và tầm quan trọng của precedence

Nếu Pod đã cấu hình IRSA đúng nhưng image chứa `AWS_ACCESS_KEY_ID`, provider môi trường có thể chiếm ưu tiên trước web identity. Pod có thể gửi request bằng IAM principal khác kỳ vọng.

Kiểm tra các yếu tố:

- Service account, role ARN, OIDC provider và trust policy (với IRSA).
- Pod identity association/agent và endpoint credential được cung cấp (với Pod Identity).
- Environment variable hoặc JVM system property có đang override provider chain không.
- STS dependency cần thiết khi cơ chế sử dụng STS; quyền thực tế ở target S3/SQS/KMS.

Không copy credential từ node vào Pod; việc này làm suy yếu ranh giới IAM giữa workload.

### 6.3. EC2, IMDS và điều kiện mạng

IMDS cung cấp metadata và temporary credential của instance profile theo chính sách/hạ tầng EC2. SDK cần được phép truy cập metadata endpoint; nếu IMDS bị tắt, network policy chặn hoặc instance không có role phù hợp, `InstanceProfileCredentialsProvider` có thể không lấy được credential.

Nếu chạy ngoài EC2, không kỳ vọng IMDS luôn có sẵn. SDK có thể thử nguồn này ở cuối chain và báo lỗi; cách khắc phục đúng là cấu hình nguồn credential hợp lệ cho môi trường hiện tại.

## 7. Chẩn đoán an toàn khi gặp lỗi credential và region

Phương pháp hiệu quả là xác định trước **client được Spring/SDK tạo ra sao**, sau đó kiểm tra **nguồn credential, region, IAM và resource** theo thứ tự.

### 7.1. Không tìm thấy credential

Dấu hiệu thường gặp: `Unable to load credentials from any of the providers in the chain` hoặc `SdkClientException` có danh sách provider đã thử.

Hướng điều tra:

1. Kiểm tra SDK là v2 và đúng provider có đang được dùng không; có custom bean/`credentialsProvider(...)` ghi đè không.
2. Kiểm tra loại môi trường: local profile/SSO, ECS task role, EKS web identity/Pod Identity, EC2 instance profile.
3. Kiểm tra các tên biến môi trường và Java system property cần thiết, **chỉ xác nhận biến có tồn tại**; không in secret.
4. Với SSO/assume-role: kiểm tra phiên đăng nhập, trust policy và sự hiện diện của SDK module hỗ trợ.
5. Với container/EC2: kiểm tra cấu hình role, credential endpoint/IMDS và quyền truy cập endpoint từ workload.

**Không sửa bằng cách hard-code credential vào source**. Việc này có thể tạm che lỗi cấu hình nhưng gây rủi ro bảo mật và xoay vòng secret.

### 7.2. Có credential nhưng không có quyền

`AccessDeniedException`, HTTP 403 hoặc lỗi access denied tương ứng cho thấy request đến được AWS nhưng không được cho phép hoặc không đáp ứng ràng buộc policy. Cần phân tích:

- Principal AWS thực tế là ai.
- Operation và resource ARN cụ thể có được IAM identity policy cho phép không.
- Bucket/queue/secret resource policy có giới hạn khác không.
- Nếu mã hóa bằng KMS customer-managed key, có đủ key policy/quyền tương ứng không.
- SCP, permission boundary, session policy hoặc điều kiện theo VPC endpoint/IP/tags có đang chặn không.

Credential chain **không tự chuyển sang một nguồn ưu tiên thấp hơn chỉ vì principal đang dùng nhận 403**. Đây là lỗi quyền của credential đã chọn, không phải dấu hiệu để tiếp tục thử IAM role khác.

### 7.3. Region không được tìm thấy hoặc sai vùng

Dấu hiệu: `Unable to load region from any of the providers in the chain`, lỗi endpoint, resource không tồn tại, mismatch chữ ký hoặc chuyển hướng giữa vùng tùy dịch vụ.

Kiểm tra:

- Client builder có `.region(...)` hay bean do AWSpring tạo đã đặt region không.
- `aws.region` (Java system property) và `AWS_REGION` (environment) giá trị nào có ưu tiên hơn.
- Profile được chọn là profile nào, có khai báo region không.
- Bucket/queue/table thực tế tồn tại ở vùng nào; queue URL/ARN có chứa region đích nào.
- Có endpoint override chỉ nên dùng cho test hay không.

**Sai region có thể dẫn đến thông báo lỗi giống “không tìm thấy tài nguyên”.** Không vội tạo lại bucket/queue trước khi xác minh region.

### 7.4. Xác định AWS principal mà không in credential

Với quyền truy cập STS phù hợp, dùng `GetCallerIdentity` để xác nhận account và ARN đang được client sử dụng:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;

public class IdentityCheck {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            var identity = sts.getCallerIdentity();
            System.out.println("Account: " + identity.account());
            System.out.println("Caller ARN: " + identity.arn());
        }
    }
}
~~~

Ví dụ cần module Maven/Gradle `software.amazon.awssdk:sts`; region phải được chọn phù hợp với endpoint STS dùng ở môi trường của bạn. Đừng log access key, secret key hoặc session token; account ID và ARN cũng có thể là thông tin nội bộ nên tránh đưa vào log public.

`GetCallerIdentity` trả danh tính của credential được dùng, **không chỉ ra trực tiếp provider con nào trong chain đã chọn**. Hãy kết hợp với cấu hình workload và log chẩn đoán đã được lọc để tìm nguồn credential, thay vì coi STS là công cụ truy nguyên provider.

## 8. Kiểm thử provider chain mà không dùng nhầm tài khoản thật

Không nên để kiểm thử tự ý dùng `DefaultCredentialsProvider` của máy developer hoặc CI rồi gọi cloud thật. Test cần có cấu hình cô lập và biết rõ resource nào sẽ bị truy cập.

### 8.1. Unit test: fake adapter, không cần AWS credential

Với logic nghiệp vụ, tách adapter giao tiếp AWS khỏi service. Unit test mock adapter hoặc mock client và xác nhận xử lý dữ liệu, mapping và lỗi; không cần SDK resolve credential hoặc region. Đây là cách chạy nhanh, ổn định, không gây chi phí cloud.

### 8.2. Integration test: endpoint và credential test tường minh

Khi dùng LocalStack hoặc service emulator tương tự, tạo client test với endpoint giả lập và credential giả. Ví dụ:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

public class LocalS3ClientFactory {
    public static S3Client create(URI localEndpoint) {
        return S3Client.builder()
                .endpointOverride(localEndpoint)
                .region(Region.US_EAST_1)
                .credentialsProvider(StaticCredentialsProvider.create(
                        AwsBasicCredentials.create("test", "test")))
                .serviceConfiguration(S3Configuration.builder()
                        .pathStyleAccessEnabled(true)
                        .build())
                .build();
    }
}
~~~

Trong test thật, `localEndpoint` phải lấy từ instance LocalStack/container do test khởi tạo. Bộ `test/test` chỉ dành cho môi trường giả lập, **không được dùng làm AWS credential thật**. Client test cần được đóng khi hết vòng đời test.

Thử hai nhóm tình huống:

- **Wiring:** bean S3/SQS, conversion, tên bucket/queue, endpoint override và region của test hoạt động.
- **Lỗi:** bucket/queue không tồn tại, client lỗi mạng, message bị xử lý trùng, quyền bị từ chối trong môi trường mô phỏng phù hợp.

LocalStack và emulator không mô phỏng đầy đủ policy, STS, IMDS, role hoặc mọi khác biệt vùng của AWS. Không lấy kết quả test giả lập làm bằng chứng IAM production đúng.

### 8.3. Smoke test trên tài khoản AWS riêng

Sau integration test, chạy một smoke test hạn chế với:

1. Một role **chỉ dành cho môi trường test** và tài nguyên AWS test có kiểm soát chi phí.
2. Region chỉ định tường minh, bucket/queue test đã được provision.
3. Credential lấy qua IAM role/OIDC tương ứng môi trường CI hoặc workload, không commit static key.
4. Thao tác nhỏ kiểm chứng gọi STS xác định principal, S3/SQS và dọn tài nguyên test khi thích hợp.
5. Assert account, ARN hoặc resource đích trước thao tác có tác động; không để test có khả năng sửa/xóa dữ liệu production.

Bài kiểm thử này xác minh quyền IAM, network, region, mã hóa và hành vi thực tế tốt hơn unit test hoặc emulator, nhưng vẫn không thay thế kiểm thử tải và vận hành lâu dài.

## 9. Bảo mật, secret và vận hành

### 9.1. Quy tắc cấu hình danh tính

- **Ưu tiên temporary credential và IAM role** cho workload chạy trên AWS.
- Không ghi access key dài hạn trong Git, Dockerfile, artifact build, các file `application*.yml` được chia sẻ hoặc log.
- Không đặt lại key toàn cục bằng `System.setProperty(...)` ở runtime để “đổi tài khoản”; cách này ảnh hưởng process và dễ tạo race condition.
- Nếu cần gọi cross-account, thiết kế STS assume role hoặc profile role rõ ràng, có trust policy và session duration hợp lý.
- Credential cho **đăng nhập** và quyền **thao tác tài nguyên** là hai lớp. IAM policy, bucket policy, KMS và network policy vẫn cần kiểm thử.

### 9.2. Quy tắc cấu hình region

- Cấu hình vùng theo môi trường triển khai và theo vị trí thực của resource.
- Với ứng dụng dùng nhiều region, quản lý client theo từng region thay vì phụ thuộc một biến toàn cục.
- Bảo đảm các adapter storage, queue, database và secret dùng đúng region/resource ID.
- Trong CI, set region tường minh để không phụ thuộc profile mặc định của runner.

### 9.3. Quan sát và xử lý sự cố

Log nên ghi **dịch vụ, operation, region dự kiến, request ID/correlation ID và loại lỗi**, nhưng cần loại bỏ credential, session token và nội dung secret. Bật log SDK chi tiết chỉ trong môi trường kiểm soát và xem chính sách che thông tin nhạy cảm. Đo metric về số lỗi `AccessDenied`, số lỗi cấu hình region và retry/network để nhanh chóng phát hiện lỗi khi chuyển role hoặc khi triển khai sang vùng khác.

Thay credential provider có thể làm thay đổi principal mà IAM đang đánh giá. Bất kỳ thay đổi liên quan role, profile, env hoặc config bean nào cũng nên được kiểm thử trước khi rollout.

## 10. Liên hệ với Azure và Google Cloud

Module tích hợp Spring Boot trong phạm vi đa cloud cũng cần nhận diện cùng một nhu cầu tổng quát: **ứng dụng cần một danh tính và một vị trí tài nguyên/endpoint để gọi dịch vụ managed**. Nhưng tên provider và thứ tự tìm nguồn của mỗi hệ sinh thái khác nhau.

| Hệ sinh thái | Cơ chế danh tính thường gặp | Cách xác định vị trí/resource |
| --- | --- | --- |
| AWS SDK Java v2 / AWSpring | `DefaultCredentialsProvider`, IAM role, STS, profile | `DefaultAwsRegionProviderChain` hoặc region tường minh |
| Azure SDK / Spring Cloud Azure | Các cơ chế như `DefaultAzureCredential` và Managed Identity, tùy thư viện/phiên bản | Endpoint của resource, subscription và region triển khai dịch vụ |
| Google Cloud client libraries / Spring Cloud GCP | **Application Default Credentials (ADC)** và service account/workload identity | Project ID, location và endpoint theo từng dịch vụ |

Đây là **so sánh khái niệm**, không có nghĩa các chain có thứ tự, chính sách hoặc semantics giống nhau. Ví dụ, AWS `AWS_REGION` không phải biến môi trường chung điều khiển Azure Storage hoặc Google Cloud Storage. Khi thiết kế adapter đa cloud, nên tách mã nghiệp vụ khỏi cấu hình identity và location cụ thể của từng provider.

## 11. Bài tập thực hành

**Bối cảnh:** Một dịch vụ Spring Boot lưu hợp đồng vào S3 và gửi sự kiện lên SQS. Dịch vụ chạy ở máy developer, CI và ECS production. Hệ thống sử dụng AWSpring và AWS SDK for Java v2.

### Yêu cầu 1: dự đoán provider được chọn

Với từng tình huống dưới đây, hãy cho biết provider có khả năng được dùng đầu tiên và giải thích:

| Tình huống | Cấu hình có sẵn |
| --- | --- |
| A | Local có profile `dev` hợp lệ, không có static key ở environment |
| B | ECS task role đúng nhưng container có `AWS_ACCESS_KEY_ID` và `AWS_SECRET_ACCESS_KEY` hợp lệ của tài khoản khác |
| C | EKS IRSA có `AWS_ROLE_ARN` + token file, không có credential từ system properties/environment |
| D | EC2 có instance profile, không có nguồn credential nào ưu tiên cao hơn |
| E | CI không có role, profile, token hoặc key hợp lệ |

**Gợi ý:** A → profile; B → environment; C → web identity; D → IMDS/instance profile; E → lỗi không tìm được credential. Kết quả trong thực tế vẫn phụ thuộc việc nguồn đã được cấu hình chính xác và SDK có các module hỗ trợ cần thiết.

### Yêu cầu 2: tìm region

Một developer đặt:

~~~text
Java property: aws.region=eu-west-1
Environment:   AWS_REGION=ap-southeast-1
AWS profile:   region=us-east-1
~~~

Client `S3Client.create()` sẽ ưu tiên region nào? Nếu dùng `S3Client.builder().region(Region.US_WEST_2).build()` thì sao?

**Đáp án kiểm tra:** Với client mặc định, `aws.region` ở Java system property được ưu tiên, nên là `eu-west-1`. Với builder chỉ định `Region.US_WEST_2`, region client là `us-west-2`. Cả hai kết quả độc lập với credential chain.

### Yêu cầu 3: chẩn đoán sự cố thực tế

1. ECS task báo `AccessDenied` dù task role đã có `s3:PutObject`. Xác minh credential nào được chọn và có environment key ghi đè không; sau đó kiểm tra ARN object, bucket policy và KMS.
2. Local IDE báo `Unable to load region` nhưng `aws sso login` đã thành công. Kiểm tra region trong profile, `AWS_REGION` hoặc bean client; SSO chỉ giải quyết một phần bài toán danh tính.
3. Pod EKS IRSA lỗi không tìm credential. Kiểm tra token file, role ARN, trust policy, STS module, provider override và quyền truy cập STS.
4. Integration test chạy thành công với LocalStack nhưng production thất bại khi gọi SQS. Kiểm tra IAM/queue policy, vùng của queue, URL/ARN, listener configuration và credential provider của workload.

### Yêu cầu 4: thiết kế cấu hình an toàn

Đề xuất cách cấu hình cho ba môi trường:

- **Local:** `AWS_PROFILE` chỉ đến profile dev-sandbox, region từ config hoặc `AWS_REGION`.
- **CI:** OIDC/temporary role credential và `AWS_REGION` tường minh; tài nguyên test độc lập.
- **ECS:** task role, region được xác định rõ, không có environment static key.

Giải thích cách phát hiện sớm nếu ứng dụng kết nối nhầm account hoặc region, và cách xác minh qua `GetCallerIdentity`, log đã lọc và smoke test.

## 12. Ghi nhớ

**DefaultCredentialsProvider** chọn nguồn credential theo ưu tiên: **Java system properties → environment variables → web identity → shared profile → container credentials → EC2 instance profile**. **DefaultAwsRegionProviderChain** tìm region theo ưu tiên: **Java system property `aws.region` → `AWS_REGION` → shared profile → EC2 metadata**, trừ khi client đã được đặt region trực tiếp. Spring Cloud AWS có thể cấu hình bean/region/credential theo properties hoặc cấu hình riêng, nên phải kiểm tra cả phần Spring lẫn SDK khi chẩn đoán.

Áp dụng đúng hai chuỗi này giúp ứng dụng Spring Boot dùng role an toàn trên AWS, chạy ổn định qua nhiều môi trường, kết nối đúng vùng tài nguyên và phân biệt được lỗi identity, IAM, endpoint với lỗi logic nghiệp vụ. Đây là nền tảng để mở rộng sang S3, SQS, secrets, database và so sánh integration patterns giữa AWS, Azure và Google Cloud.
