# Hồ sơ AWS CLI, AWS IAM Identity Center và phát triển cục bộ

## 1. Bối cảnh và mục tiêu

Một ứng dụng Spring Boot tích hợp Amazon S3, Amazon SQS hoặc AWS Secrets Manager thường được phát triển trên máy cá nhân, kiểm thử trong môi trường riêng rồi triển khai bằng IAM role trên AWS. Trên máy developer, ứng dụng phải biết **đang sử dụng danh tính AWS nào**, **thuộc tài khoản nào**, **ở region nào**, và **quyền nào đã được cấp**. Nếu xử lý những giá trị này bằng cách chép access key vào `application.yml`, nguy cơ lộ secret và truy cập nhầm production tăng đáng kể.

Trong chương **Nền tảng AWS** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**, bài này hướng dẫn phát triển cục bộ cho ứng dụng Spring Boot sử dụng các dịch vụ managed của AWS. Đây cũng là một phần của mục tiêu rộng hơn: học cách thiết lập identity và permission, truy cập storage/messaging/dữ liệu, bảo vệ secret, kiểm thử tích hợp và so sánh với các cơ chế tương ứng trên Azure, Google Cloud.

Trọng tâm là ba thành phần:

- **AWS CLI profile:** tên cấu hình giúp chọn tài khoản, nguồn credential, region và các thiết lập khi chạy lệnh AWS CLI hoặc ứng dụng SDK.
- **AWS IAM Identity Center:** nền tảng cấp quyền truy cập AWS cho người dùng và nhóm; hỗ trợ đăng nhập tập trung để lấy temporary credential phục vụ phát triển.
- **AWS SDK for Java v2 / AWSpring:** lớp ứng dụng đọc profile và credential thông qua provider chain, sau đó dùng IAM permission thực sự khi gọi S3, SQS, STS và các dịch vụ AWS khác.

Sau bài học, bạn có thể thiết lập profile cục bộ bằng AWS CLI v2; đăng nhập IAM Identity Center; kiểm tra principal và region; chạy Spring Boot bằng profile dev; xử lý token hết hạn, xung đột environment credential và lỗi thiếu module SSO của SDK; đồng thời tổ chức kiểm thử không phụ thuộc tài khoản production.

> **Phạm vi:** Ví dụ tập trung vào AWS CLI **v2** và AWS SDK for Java **v2**, thường dùng với Spring Cloud AWS 3.x trong các bộ phiên bản Spring Boot tương thích. Lệnh, property và chi tiết vòng đời token có thể thay đổi theo release; khi triển khai thật, đối chiếu tài liệu của phiên bản đã chọn. Ví dụ về URL, account ID, permission set, bucket và queue dưới đây đều là giá trị minh họa.

## 2. Từ người dùng đến quyền truy cập tài nguyên AWS

Cần phân biệt năm khái niệm thường bị gộp làm một:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Người dùng tổ chức | `developer@example.com` | Con người đăng nhập qua hệ thống danh tính; không phải access key |
| AWS IAM Identity Center | Portal đăng nhập chung của công ty | Xác thực người dùng và cho phép truy cập các AWS account/permission set đã được phân quyền |
| Permission set | `DeveloperReadOnly` | Bộ quyền Identity Center sử dụng để provision IAM role thích hợp trong tài khoản đích |
| AWS CLI profile | `dev-sandbox` | Cấu hình cục bộ chỉ ra account, permission set, SSO session, region và nguồn credential |
| Temporary AWS credentials | Access key ID + secret access key + session token có hạn | Dữ liệu SDK dùng để ký request với AWS API |

Một **profile không phải IAM principal**. Profile chỉ cho CLI/SDK biết cách có được credentials, lựa chọn account/quyền và region. Principal thực tế được AWS nhìn thấy thường là phiên của IAM role thuộc tài khoản đích. Quyền mà phiên role đó có phụ thuộc policy, resource policy, SCP, permission boundary, KMS policy và điều kiện khác.

Ví dụ, cùng một người có thể được Identity Center cấp:

- `dev-sandbox` → tài khoản thử nghiệm, permission set có quyền upload S3 và gửi SQS.
- `prod-readonly` → tài khoản production, permission set chỉ có quyền đọc/quan sát.

Tên profile do developer đặt; tên này **không tự tạo IAM policy**. Tổ chức phải phân quyền account và permission set trước khi developer có thể đăng nhập và sử dụng.

~~~mermaid
flowchart TD
    U["Developer"] --> I["IAM Identity Center / tổ chức"]
    I --> A["Account được phân quyền"]
    A --> P["Permission set"]
    U --> C["AWS CLI v2: aws sso login"]
    C --> T["SSO session và token cache cục bộ"]
    T --> D["CLI / SDK Java v2"]
    P -. "Cấp quyền qua role của account" .-> R["Temporary AWS credentials"]
    D --> R
    R --> API["S3 / SQS / STS / Secrets Manager"]
    API --> IAM["AWS kiểm tra IAM và resource policy"]
~~~

Sơ đồ trên mô tả luồng khái niệm. Khi SDK sử dụng SSO profile, nó có thể sử dụng token SSO đã được CLI tạo để lấy temporary AWS credentials; cơ chế refresh phụ thuộc kiểu profile, SDK và session còn hiệu lực.

## 3. AWS CLI profile được lưu ở đâu?

AWS CLI và AWS SDK thường tìm cấu hình dùng chung trong thư mục `.aws` của tài khoản hệ điều hành hiện tại:

| Hệ điều hành | Thư mục thông thường | Tệp |
| --- | --- | --- |
| Linux/macOS | `~/.aws/` | `config`, `credentials` |
| Windows | `C:\Users\<user>\.aws\` | `config`, `credentials` |

Có thể thay đường dẫn bằng các biến môi trường `AWS_CONFIG_FILE` và `AWS_SHARED_CREDENTIALS_FILE`. Biến override này có ích khi chạy test hoặc container, nhưng nếu trỏ sai path, CLI/SDK có thể không nhìn thấy profile đã tạo.

### 3.1. Tệp `config`

Tệp `~/.aws/config` thường chứa region, output format và cấu hình truy cập như SSO session hoặc assume role:

~~~ini
[profile dev-sandbox]
region = ap-southeast-1
output = json

[profile prod-readonly]
region = ap-southeast-1
output = json
~~~

Tên profile được khai báo theo dạng `[profile <name>]` trong file `config`; profile mặc định được viết là `[default]`.

Một profile chỉ có `region` sẽ **chưa chắc có credential**. Nó có thể dùng một nguồn credential ở environment hoặc provider khác, nhưng muốn sử dụng Identity Center phải cấu hình SSO đầy đủ.

### 3.2. Tệp `credentials`

Tệp `~/.aws/credentials` chủ yếu dành cho các mục credential được lưu dưới tên profile, với section kiểu `[dev-sandbox]` thay vì `[profile dev-sandbox]`. Đối với cách làm truyền thống, nội dung có thể bao gồm access key ID và secret key. Với temporary credentials, có thêm session token.

Không cần và **không nên** chép access key vào `credentials` khi dự án đã dùng IAM Identity Center. Profile SSO hiện đại được cấu hình trong `config`; CLI/SDK nhận temporary credentials qua SSO session và cache.

Tuyệt đối không commit tệp `config`/`credentials` chứa thông tin nhạy cảm vào repository, không gửi lên ticket và không đưa cache SSO vào Docker image. Cache token cũng là thông tin cần bảo vệ, dù không phải secret key tĩnh.

### 3.3. Kiểm tra danh sách profile

Sau khi cài **AWS CLI v2**, có thể kiểm tra:

~~~bash
aws --version
aws configure list-profiles
aws configure list --profile dev-sandbox
aws configure get region --profile dev-sandbox
~~~

`aws configure list --profile ...` cho biết các giá trị cấu hình và nguồn của chúng, nhưng kết quả trên một số cấu hình có thể hiện một phần thông tin credential. Chỉ dùng trong terminal kiểm soát và không dán nguyên output vào issue/chat công khai.

Lệnh đọc cấu hình **không đảm bảo** profile đã đăng nhập Identity Center hay có quyền truy cập dịch vụ.

## 4. IAM Identity Center làm gì trong phát triển cục bộ?

**AWS IAM Identity Center** (trước đây gọi là AWS Single Sign-On, thường viết SSO) tích hợp với nguồn danh tính của tổ chức, quản lý nhóm/người dùng và phân quyền truy cập account AWS thông qua permission set.

Một developer thường được cung cấp từ quản trị viên:

1. **Start URL hoặc issuer URL** của IAM Identity Center instance, theo khả năng AWS CLI đang dùng.
2. **Identity Center region** (vùng của hệ thống IAM Identity Center/OIDC), có thể **khác** region của S3/SQS mà ứng dụng truy cập.
3. Danh sách **AWS account** đã được cấp quyền.
4. **Permission set** tương ứng trong từng account, ví dụ `DeveloperReadOnly` hoặc `DeveloperSandbox`.
5. Hướng dẫn đăng nhập, MFA và giới hạn phiên theo chính sách tổ chức.

Quản trị viên quyết định quyền. Developer không thể tự chọn một permission set bất kỳ hoặc tự mở quyền bằng cách sửa file profile.

### 4.1. Phân biệt ba giá trị thường bị nhầm

| Giá trị | Ví dụ | Dùng để làm gì? |
| --- | --- | --- |
| `sso_region` | `us-east-1` | Kết nối API đăng nhập IAM Identity Center/OIDC |
| `sso_account_id` | `111122223333` | Tài khoản AWS sẽ nhận role credentials |
| `region` trong profile | `ap-southeast-1` | Vùng mặc định khi gọi service AWS, ví dụ S3/SQS |

`sso_region` không nhất thiết phải trùng `region`. Chọn sai `sso_region` gây lỗi xác thực/SSO endpoint; chọn sai `region` có thể khiến API tìm queue, bucket hoặc table ở vùng khác. Chúng cần được kiểm tra độc lập.

### 4.2. Permission set và IAM role

Permission set là cấu hình do IAM Identity Center quản lý. Khi gán permission set cho người dùng/nhóm ở một AWS account, IAM Identity Center provision IAM role được quản lý trong account đó. Sau login, CLI/SDK lấy **temporary credentials của role** dựa trên account và permission set đã chọn.

Ví dụ: một người có quyền `DeveloperReadOnly` trong production không thể gửi SQS message nếu policy chỉ cho phép đọc. Đăng nhập SSO thành công không ngụ ý tác vụ `sqs:SendMessage` được cấp quyền.

## 5. Thiết lập SSO profile với AWS CLI v2

### 5.1. Điều kiện trước khi cấu hình

Cần có AWS CLI v2 trên máy, URL IAM Identity Center, region IAM Identity Center và phân quyền account/permission set. Trình duyệt/thiết bị đăng nhập có thể yêu cầu MFA. Không tự tạo access key dài hạn để thay thế cho bước đăng nhập tổ chức.

Quy trình thường dùng:

~~~bash
aws configure sso --profile dev-sandbox
~~~

Trình hướng dẫn có thể hỏi tên SSO session, Start URL hoặc issuer URL, SSO region, scope, account, role/permission set, default AWS region và output format. Chọn đúng tài khoản **sandbox** trước khi chấp nhận. Với CLI mới, wizard thường tạo section `[sso-session ...]` và liên kết đến profile.

Ví dụ cấu hình tạo ra hoặc được rà soát trong `~/.aws/config`:

~~~ini
[sso-session team-sso]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile dev-sandbox]
sso_session = team-sso
sso_account_id = 111122223333
sso_role_name = DeveloperSandbox
region = ap-southeast-1
output = json
~~~

Đây là **ví dụ minh họa**: domain, account ID và tên permission set không đại diện tài khoản có thật. `sso_role_name` phải trùng quyền mà Identity Center thực sự cấp; không phải tên có thể tùy tiện tự khai báo rồi có quyền.

Có thể tạo thêm profile chỉ đọc ở production:

~~~ini
[profile prod-readonly]
sso_session = team-sso
sso_account_id = 444455556666
sso_role_name = DeveloperReadOnly
region = ap-southeast-1
output = json
~~~

Hai profile cùng tham chiếu một `sso-session` nếu cùng dùng instance SSO, nhưng dẫn đến **AWS account hoặc permission set khác nhau**. Kiểm tra quyền cụ thể trước khi dùng; tên `prod-readonly` tự đặt không phải cơ chế bảo vệ. Chính sách IAM và quyền được provision mới quyết định khả năng ghi/xóa.

### 5.2. Đăng nhập vào IAM Identity Center

~~~bash
aws sso login --profile dev-sandbox
~~~

AWS CLI mở hoặc hướng dẫn quy trình đăng nhập. Sau khi xác thực thành công, CLI lưu token cần thiết trong cache cục bộ để làm việc với profile. Tùy phiên bản và session, lệnh đăng nhập có thể tái sử dụng session còn hợp lệ.

Sau đó xác minh danh tính:

~~~bash
aws sts get-caller-identity --profile dev-sandbox
~~~

Phản hồi chứa các trường `UserId`, `Account` và `Arn`. Đối chiếu `Account` với tài khoản sandbox được cấp và `Arn` với principal/role mong đợi. Không nên chỉ tin tên profile.

**Lưu ý:** `sts get-caller-identity` giúp xác minh principal thật, nhưng không xác nhận đã có quyền S3/SQS hoặc quyền dùng KMS. Chỉ thao tác trên tài nguyên test cụ thể mới xác thực được quyền và policy của thao tác đó.

### 5.3. Đăng xuất và hết hạn phiên

~~~bash
aws sso logout
~~~

Lệnh logout dọn credential/token SSO cached theo phạm vi được CLI hỗ trợ; không nên giả định rằng logout luôn chỉ ảnh hưởng một profile. Cần kiểm tra workflow hiện hành nếu một người dùng nhiều SSO session.

Khi phiên hoặc token hết hạn, lệnh CLI có thể yêu cầu chạy lại `aws sso login --profile dev-sandbox`. Khả năng làm mới token, cache và credential phụ thuộc **cấu hình SSO session** và phiên bản công cụ. Việc SDK làm mới temporary AWS role credentials không có nghĩa người dùng được đăng nhập vĩnh viễn.

Không giải quyết token hết hạn bằng việc copy tạm access key vào source code. Hãy đăng nhập lại và kiểm tra đồng hồ hệ thống, kết nối tới Identity Center cùng quyền account/permission set.

## 6. Chọn profile khi dùng AWS CLI

Có hai cách phổ biến: chỉ định theo lệnh hoặc theo environment.

### 6.1. Chỉ định theo từng lệnh

~~~bash
aws sts get-caller-identity --profile dev-sandbox
aws s3 ls --profile dev-sandbox --region ap-southeast-1
~~~

Thêm `--profile` làm rõ profile đang dùng cho **lệnh CLI cụ thể**. Ví dụ `aws s3 ls` còn yêu cầu role có quyền đọc/liệt kê tương ứng; nếu bị từ chối, cần kiểm tra IAM và policy thay vì kết luận SSO login thất bại.

Thực hành tốt là kiểm tra account bằng STS trước mọi thao tác ghi, xóa, tạo tài nguyên hoặc thay đổi policy.

### 6.2. Chọn profile mặc định cho terminal hiện tại

Linux/macOS với Bash:

~~~bash
export AWS_PROFILE=dev-sandbox
export AWS_REGION=ap-southeast-1

aws sts get-caller-identity
~~~

Windows PowerShell:

~~~powershell
$env:AWS_PROFILE = "dev-sandbox"
$env:AWS_REGION = "ap-southeast-1"

aws sts get-caller-identity
~~~

Những thiết lập này áp dụng cho **process shell và process con** tương ứng. IDE, Gradle daemon, terminal khác hoặc container có thể nhận môi trường khác nhau. Đặc biệt, nếu IDE đã chạy trước khi thay biến môi trường, ứng dụng khởi động từ IDE có thể không thấy giá trị mới.

Đối với AWS SDK Java v2, `AWS_PROFILE` là cách chọn profile từ shared config khi provider chain đi tới profile provider. **Nó không nhất thiết ghi đè credential từ Java system properties hoặc các biến `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`**, vốn thường được thử trước profile. Vì vậy cần xác minh danh tính ứng dụng thực tế thay vì tin rằng `AWS_PROFILE` luôn quyết định toàn bộ credential.

### 6.3. Không tự ý đặt default profile thành production

Nếu thường chuyển giữa dev/prod, không nên coi profile `default` là nơi đặt quyền ghi production. Dùng profile có tên rõ ràng, quyền tối thiểu, và cho các script thay đổi tài nguyên chỉ chạy khi đã xác nhận account/region đích.

Các lệnh như `aws configure list-profiles` và `aws sts get-caller-identity --profile ...` giúp kiểm tra khi chuyển bối cảnh; nhưng guardrail mạnh hơn vẫn là IAM policy, role chỉ đọc, sandbox account và kiểm soát quyền theo môi trường.

## 7. AWS SDK for Java v2 sử dụng SSO profile như thế nào?

Spring Cloud AWS 3.x thường dùng **AWS SDK for Java v2** bên dưới. SDK có thể đọc các file shared configuration do AWS CLI tạo và dùng profile SSO để nhận temporary credentials. SDK không “đăng nhập hộ” bằng browser theo cách một developer tương tác với `aws sso login`; thường cần chuẩn bị SSO session đã đăng nhập hoặc một cơ chế refresh được SDK hỗ trợ.

### 7.1. ProfileCredentialsProvider

Nếu muốn gọi SDK với một profile cụ thể:

~~~java
import software.amazon.awssdk.auth.credentials.ProfileCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

public final class S3DevClientFactory {
    public static S3Client create() {
        return S3Client.builder()
                .credentialsProvider(
                        ProfileCredentialsProvider.create("dev-sandbox"))
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

`ProfileCredentialsProvider` xử lý thông tin profile, có thể điều phối provider khác tùy loại cấu hình (SSO, assume role, credential process...). Nó **không tự tạo quyền IAM**. Mã trên cố định profile `dev-sandbox` nên chỉ phù hợp khi bạn thực sự muốn khóa client vào môi trường phát triển; **không dùng cứng profile này trong mã deploy chung**.

Ở production, thường không muốn client phụ thuộc vào file profile local của developer; hãy để workload identity/role và default provider chain hoạt động.

### 7.2. DefaultCredentialsProvider và AWS_PROFILE

Khi application không cấu hình credential provider riêng, AWS SDK v2 dùng chuỗi mặc định như sau:

1. Java system properties có AWS access key/secret.
2. Environment variables chứa AWS access key/secret.
3. Web identity token và role ARN.
4. Shared AWS profile.
5. Container credentials (ví dụ ECS task role).
6. EC2 instance profile qua IMDS.

Do đó, với môi trường local **không có** credential từ nguồn ưu tiên cao hơn, `AWS_PROFILE=dev-sandbox` giúp chuỗi tìm đến profile SSO. Nhưng khi container ECS có environment static key, SDK có thể chọn key đó trước task role. Đây là lý do nên tránh đặt key lâu dài trong môi trường chạy.

Ví dụ một SDK client dùng chuỗi mặc định:

~~~java
import software.amazon.awssdk.services.s3.S3Client;

try (S3Client s3 = S3Client.create()) {
    // Có thể dùng credential từ AWS_PROFILE nếu không có nguồn ưu tiên cao hơn
    // và region được xác định bằng region provider chain.
}
~~~

Client cũng cần region. Với AWS SDK Java v2, chuỗi region thông thường ưu tiên `aws.region` system property, `AWS_REGION`, region trong shared profile rồi mới tới metadata của EC2. Nếu builder hoặc AWSpring đã đặt region tường minh, region chain có thể không quyết định region của client đó.

### 7.3. SDK module cần thiết cho profile SSO

Trong ứng dụng Java v2, các profile SSO có thể cần module SDK **`sso`** và **`ssooidc`** trên runtime classpath, tùy cách tích hợp và release. Một số cấu hình giả định thêm module **`sts`** khi profile cần assume role/STS. Nếu SDK báo không thể tải SSO credentials hoặc thiếu implementation, kiểm tra version BOM và resolved dependencies.

Khai báo Maven mang tính minh họa:

~~~xml
<dependencies>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sso</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>ssooidc</artifactId>
    </dependency>
</dependencies>
~~~

Ví dụ giả định các version SDK đã được **BOM/dependency management** của dự án quản lý. Nếu không, cần import đúng SDK BOM hoặc khai báo version nhất quán đã được duyệt. Không thêm version khác nhau trên các SDK module chỉ để hết lỗi compile. Nếu chỉ làm việc với API trực tiếp khác, thêm module tương ứng (ví dụ `s3`, `sqs`, `sts`).

**Phân biệt ba lỗi**:

| Thông báo hoặc tình huống | Lớp vấn đề chính | Bước đầu kiểm tra |
| --- | --- | --- |
| CLI yêu cầu chạy `aws sso login` | Phiên/token SSO local | Session profile, đăng nhập, token cache |
| Java báo thiếu SSO provider/module | Runtime dependency | `sso`/`ssooidc` và version SDK đã resolve |
| Java nhận `AccessDenied` từ S3/SQS | IAM/resource policy | Principal/role, action, ARN, KMS và account |

### 7.4. AWSpring và Spring Boot

Trong một ứng dụng Spring Boot sử dụng AWSpring, có thể giữ mã application không phụ thuộc tên profile local. Chẳng hạn khi starter S3 đã được cấu hình:

~~~java
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;

@Service
public class DocumentMetadataReader {
    private final S3Client s3;

    public DocumentMetadataReader(S3Client s3) {
        this.s3 = s3;
    }

    public long size(String bucket, String key) {
        return s3.headObject(req -> req
                .bucket(bucket)
                .key(key))
            .contentLength();
    }
}
~~~

Đoạn trên giả định có bean `S3Client` được cấu hình từ AWSpring hoặc cấu hình Spring riêng. Khi chạy local, cung cấp `AWS_PROFILE=dev-sandbox` và region; khi chạy ECS/EKS/EC2, cung cấp role của workload. Cần kiểm tra xem cấu hình AWSpring đã override credential/region mặc định hay chưa.

Ví dụ cấu hình chỉ đặt region và tên bucket:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION}

app:
  storage:
    bucket: ${APP_DOCUMENT_BUCKET}
~~~

`APP_DOCUMENT_BUCKET` phải trỏ bucket của **môi trường đúng**. Đoạn YAML minh họa không chứa access key hoặc session token; môi trường local cung cấp identity qua SSO profile, production qua role. Nếu build đã tạo client riêng với `.credentialsProvider(...)`, cấu hình riêng đó có thể vượt qua cách SDK lựa chọn profile mặc định.

## 8. Thực hành chạy Spring Boot cục bộ với SSO

Giả sử hệ thống **Document Service** nhận yêu cầu upload biên nhận lên S3 rồi gửi event vào SQS. Nhóm cấp tài khoản AWS sandbox và permission set dành riêng cho phát triển; ứng dụng dùng Spring Boot + AWSpring.

### Bước 1: Chuẩn bị profile dev

~~~bash
aws configure sso --profile dev-sandbox
aws sso login --profile dev-sandbox
aws sts get-caller-identity --profile dev-sandbox
~~~

Đối chiếu trường `Account` của STS với account sandbox đã được tổ chức cấp. Nếu sai account, **dừng các thao tác ghi** và kiểm tra profile/session/credential override.

### Bước 2: Xác minh region riêng

~~~bash
aws configure get region --profile dev-sandbox
~~~

Nếu tài nguyên nằm ở Singapore, region mặc định của ví dụ là `ap-southeast-1`. Region của S3/SQS và region đăng nhập SSO có thể khác nhau; không tự lấy `sso_region` làm region của service AWS.

### Bước 3: Mở terminal đúng profile và region

Bash:

~~~bash
export AWS_PROFILE=dev-sandbox
export AWS_REGION=ap-southeast-1
export APP_DOCUMENT_BUCKET=example-dev-documents
export APP_EVENTS_QUEUE=example-dev-events
~~~

PowerShell:

~~~powershell
$env:AWS_PROFILE = "dev-sandbox"
$env:AWS_REGION = "ap-southeast-1"
$env:APP_DOCUMENT_BUCKET = "example-dev-documents"
$env:APP_EVENTS_QUEUE = "example-dev-events"
~~~

Các tên bucket/queue ở trên là placeholder; thay bằng tài nguyên sandbox **đã được provision**, không tạo lại tài nguyên bằng lệnh production. Nếu hệ thống yêu cầu queue URL thay cho tên queue, cung cấp đúng định dạng API/SDK cần.

### Bước 4: Chạy ứng dụng bằng IDE hoặc build tool

Khởi động ứng dụng từ **chính terminal** đã đặt biến môi trường, hoặc cấu hình Run Configuration của IDE với `AWS_PROFILE`, `AWS_REGION` và biến tên tài nguyên. Nếu IDE được chạy từ GUI và không kế thừa environment của terminal, cần set biến trong cấu hình chạy.

Ứng dụng cần dependency AWSpring starter và module SDK SSO phù hợp với phiên bản. Không phải trường hợp nào `aws sso login` thành công cũng đảm bảo JVM nhận được profile; JVM có thể dùng HOME khác, `AWS_CONFIG_FILE` khác hoặc không có module SDK cần thiết.

### Bước 5: Chạy thử trên tài nguyên có quyền hạn chế

Với role dev được cấp quyền đọc bucket sandbox, có thể dùng lệnh **ít tác động** để kiểm tra, ví dụ:

~~~bash
aws s3 ls s3://example-dev-documents --profile dev-sandbox --region ap-southeast-1
~~~

Lệnh trên yêu cầu tài nguyên thật sự tồn tại và đủ quyền. Nếu tài khoản chỉ cho phép `s3:PutObject` nhưng không có `s3:ListBucket`, `aws s3 ls` có thể bị từ chối dù thao tác ghi object cụ thể được cho phép. Test đúng operation để kết luận quyền chính xác.

Với tác vụ có side effect như `PutObject` hoặc `SendMessage`, sử dụng bucket prefix/queue sandbox dành riêng cho test, dữ liệu giả và idempotency phù hợp. Không dùng dữ liệu khách hàng thật ở môi trường local.

## 9. Xử lý lỗi thường gặp

### 9.1. Đăng nhập thành công nhưng JVM vẫn báo thiếu credential

Kiểm tra theo thứ tự:

1. CLI và ứng dụng Java chạy dưới cùng người dùng hệ điều hành chưa; có cùng đường dẫn `~/.aws/config`, cache SSO và HOME không?
2. JVM có đọc đúng `AWS_PROFILE` hoặc `aws.profile` không; có custom `ProfileCredentialsProvider`/`DefaultCredentialsProvider` được dùng không?
3. Có `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` hoặc Java system properties đang ghi đè profile không?
4. Đã có SDK v2 `sso`/`ssooidc` trên runtime classpath và SDK version nhất quán chưa?
5. Phiên SSO còn hiệu lực, user được gán account/permission set, token cache còn truy cập được không?

Đừng thử in biến môi trường credential ra console để chẩn đoán; chỉ xác nhận **có/không có** và nguồn cấu hình, tránh lộ dữ liệu bảo mật.

### 9.2. SSO session hết hạn hoặc token không làm mới được

Dấu hiệu có thể là thông báo token SSO không hợp lệ, expired, không thể lấy role credentials hoặc lỗi gọi Identity Center. Chạy lại:

~~~bash
aws sso login --profile dev-sandbox
aws sts get-caller-identity --profile dev-sandbox
~~~

Nếu vẫn lỗi, kiểm tra URL/region của session SSO, network, MFA và quyền truy cập account/permission set. Kiểm tra thời gian hệ thống nếu gặp lỗi token/signature; không tự copy cache sang máy khác.

### 9.3. Chọn đúng profile nhưng truy cập sai tài khoản

Một profile có tên `dev-sandbox` nhưng SDK dùng environment credentials ưu tiên cao hơn; hoặc profile được sửa để trỏ tới account khác. Với ứng dụng Java, `DefaultCredentialsProvider` có thứ tự nguồn riêng; CLI `--profile` không thay đổi logic provider đã cấu hình cho JVM.

**Cách xác minh:** gọi `GetCallerIdentity` bằng đúng client/credential của ứng dụng trước khi chạy thao tác ảnh hưởng dữ liệu. Nếu cần kiểm tra trong một tiện ích Java cục bộ, có thể xây `StsClient` dùng `DefaultCredentialsProvider`.

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;

public class LocalIdentityCheck {
    public static void main(String[] args) {
        try (StsClient sts = StsClient.builder()
                .credentialsProvider(DefaultCredentialsProvider.create())
                .region(Region.AP_SOUTHEAST_1)
                .build()) {
            var caller = sts.getCallerIdentity();
            System.out.println("AWS Account: " + caller.account());
            System.out.println("Principal ARN: " + caller.arn());
        }
    }
}
~~~

Lưu ý ứng dụng cần SDK module `software.amazon.awssdk:sts` trên classpath. ARN và account ID cũng có thể là dữ liệu nội bộ, nên không đưa output lên kênh public. `GetCallerIdentity` chứng minh danh tính đang dùng, không trực tiếp cho biết provider con nào trong chain đã cấp credential.

### 9.4. `AccessDenied` sau khi STS đúng account

Tài khoản đúng **không bảo đảm** permission set có đủ quyền cho operation cụ thể. Kiểm tra:

- Permission set được gán cho account và người dùng/nhóm.
- IAM policy được provision từ permission set.
- ARN bucket/object, queue hoặc secret và action yêu cầu.
- Resource policy, KMS key policy, organization SCP, permission boundary và policy điều kiện.
- Region hoặc endpoint của tài nguyên đích.

Nếu gọi S3 `PutObject` dùng SSE-KMS, quyền trên bucket có thể đúng nhưng policy/KMS permission chưa đủ. Không sửa lỗi này bằng cách tăng quyền rộng như `AdministratorAccess`; hãy xác định API và ARN bị từ chối.

### 9.5. Region sai hoặc resource không tồn tại

Kiểm tra thứ tự region của Java SDK: region đặt trực tiếp trên builder/AWSpring; rồi `aws.region`, `AWS_REGION`, region trong shared profile, EC2 metadata. Với CLI, các tùy chọn lệnh như `--region` có thể ghi đè region profile.

Ví dụ profile SSO có `region = ap-southeast-1` nhưng IDE đặt `AWS_REGION=us-east-1`. Java client sử dụng region từ environment nếu không bị cấu hình cấp cao hơn ghi đè; SQS queue ở Singapore có thể báo không tồn tại hoặc không truy cập được.

### 9.6. Container hoặc IDE không thấy file profile của host

Docker container có filesystem và environment riêng; `~/.aws` trên host không tự xuất hiện trong container. Cách xử lý khi cần local container:

- Chỉ mount **read-only** các file cấu hình/cache cần thiết trong môi trường phát triển được kiểm soát.
- Thiết lập profile/region cho process container.
- Tránh bake credential, token hoặc toàn bộ thư mục `.aws` vào image.
- Cân nhắc dùng credential endpoint an toàn hoặc cơ chế dev identity được tổ chức hỗ trợ thay vì phân phối secret.
- Không tái sử dụng cách mount local này cho ECS/EKS production; production nên dùng workload role.

Phải bảo vệ quyền truy cập file cache SSO trên host/container. Cache là credential material nhạy cảm; đừng đưa vào image, artifact hoặc log CI.

## 10. Phát triển local khác CI và production

IAM Identity Center phù hợp với **đăng nhập tương tác của con người**. Một ứng dụng sản xuất hoặc pipeline CI không nên cần người mở browser và nhập MFA mỗi lần khởi động.

| Môi trường | Cách lấy identity thường dùng | Điều cần đảm bảo |
| --- | --- | --- |
| Developer laptop | AWS CLI v2 + IAM Identity Center profile | Tài khoản sandbox, quyền tối thiểu, login/refresh rõ ràng |
| Local integration test | SDK client với endpoint LocalStack và credential giả, hoặc môi trường test riêng | Không gọi AWS thật ngoài ý muốn |
| CI bên ngoài AWS | OIDC federation/STS assume role, temporary credentials | Trust policy giới hạn repo/branch/job, tài nguyên test |
| ECS/Fargate | ECS **task role** | Phân biệt task role và task execution role |
| EKS | IRSA hoặc EKS Pod Identity tùy kiến trúc | Không inject static credential vào pod |
| EC2 | Instance profile | IMDS và quyền trên role phù hợp |

Ví dụ kiến trúc chuyển môi trường:

~~~mermaid
flowchart TD
    CODE["Cùng mã Spring Boot"] --> LOCAL["Local"]
    CODE --> TEST["Integration test"]
    CODE --> PROD["AWS workload"]
    LOCAL --> SSO["AWS_PROFILE -> SSO profile"]
    TEST --> LS["LocalStack + test credentials"]
    PROD --> IAM["ECS/EKS/EC2 role -> temporary credentials"]
    SSO --> API["AWS SDK Java v2"]
    LS --> API
    IAM --> API
    API --> AWS["S3 / SQS / Secrets Manager"]
~~~

Sơ đồ nêu **cùng mã nghiệp vụ** nhưng identity được cấp bởi môi trường khác nhau. Mục tiêu là không có nhánh kiểu `if (prod) useHardcodedKey()` trong ứng dụng.

### 10.1. Cấu hình Spring Boot theo môi trường

Một cấu hình chung có thể chỉ chứa đường dẫn tài nguyên và region:

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ${AWS_REGION}

app:
  aws:
    bucket: ${APP_DOCUMENT_BUCKET}
    queue: ${APP_EVENTS_QUEUE}
~~~

Các biến này có thể được inject từ IDE, pipeline hoặc manifest deployment. Trong môi trường local, `AWS_PROFILE` chọn profile SSO; ở production, tránh đặt `AWS_PROFILE` trỏ về cấu hình của người phát triển. Nếu có bean credentials riêng của AWSpring, kiểm tra nó có tương thích với cơ chế workload role và default provider chain không.

### 10.2. Kiểm thử LocalStack không cần SSO

Trong một integration test sử dụng emulator, nên đặt **endpoint override**, **region cố định** và **credential giả** trên SDK client chỉ trong scope test. Ví dụ:

~~~java
import java.net.URI;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

public final class LocalTestS3 {
    public static S3Client client(URI localEndpoint) {
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

Đây chỉ là credential giả dành cho giả lập local; không áp dụng trong runtime gọi AWS thật. LocalStack giúp xác minh SDK wiring, serialization và các thao tác cơ bản, nhưng **không thể chứng minh** role IAM, Identity Center, KMS và mọi hành vi production đúng. Cần thêm smoke test trên tài khoản AWS kiểm thử có quyền giới hạn.

## 11. Bảo mật khi dùng profile và SSO

### 11.1. Quyền tối thiểu cho developer

Tài khoản sandbox nên cô lập tài nguyên, giới hạn region/quota và cấp đúng operation cần cho bài học. Nếu developer chỉ cần đọc metadata S3, không cấp quyền xóa bucket; nếu cần gửi message vào queue test, chỉ cấp `sqs:SendMessage` cho ARN queue test tương ứng.

Nhớ rằng quyền trên S3 object và bucket là khác nhau, ví dụ `s3:PutObject` thường áp vào object ARN, còn `s3:ListBucket` áp vào bucket ARN. Một ứng dụng có thể upload thành công nhưng `aws s3 ls` bị từ chối do không có quyền liệt kê.

### 11.2. Bảo vệ cấu hình local

- Sử dụng MFA và điều kiện bảo mật của tổ chức khi đăng nhập Identity Center.
- Giữ thư mục `~/.aws` và SSO token cache ở quyền đọc phù hợp với user; không chia sẻ cache giữa developer.
- Không commit access key, token, cache, config nhạy cảm, log STS hoặc output diagnostic có chứa thông tin nội bộ.
- Không lưu access key lâu dài trong `application.yml`, file `.env` bị commit, Dockerfile, image layer hoặc test fixture.
- Dùng profile riêng cho dev và read-only prod; luôn xác minh AWS account trước lệnh có tác động.
- Khi nghi ngờ lộ token/credential, tuân theo quy trình xử lý sự cố của tổ chức và thu hồi/đăng xuất phiên theo cơ chế hiện có.

### 11.3. Guardrail cho các thao tác ghi

Từ ứng dụng lẫn CLI, trước khi gọi `PutObject`, `DeleteMessage`, cập nhật secret hoặc thay đổi tài nguyên, nên có các kiểm tra tự động:

1. Principal thực tế từ STS phải thuộc allowlist tài khoản dev/test.
2. Region phải thuộc tập vùng cho phép của môi trường.
3. Resource ID/ARN phải có prefix/tag quy ước cho môi trường test.
4. Operation phá hủy hoặc thay đổi policy phải đòi hỏi quyền mạnh hơn và audit rõ ràng.
5. Không dùng dữ liệu khách hàng thật trong thử nghiệm local.

**Tên profile chỉ là quy ước**, không thay thế guardrail server-side và IAM. Một profile có tên `sandbox` vẫn có thể được sửa trỏ vào production.

## 12. Liên hệ với Azure và Google Cloud

Trong thiết kế đa cloud, yêu cầu cốt lõi giống nhau: ứng dụng cần danh tính phù hợp với môi trường và quyền trên resource cụ thể. Tuy nhiên, cách đăng nhập, cache token, tìm default credential và mô hình location có khác biệt.

| Nhu cầu | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Đăng nhập tương tác developer | AWS CLI v2 + IAM Identity Center profile | Azure CLI hoặc công cụ developer identity thích hợp | Google Cloud CLI và cơ chế ADC/local auth phù hợp |
| SDK lấy credential mặc định | `DefaultCredentialsProvider` và shared AWS profile | Cơ chế credential chain như `DefaultAzureCredential` | Application Default Credentials (ADC) |
| Quyền workload | IAM task/instance/service role hoặc web identity | Managed Identity và RBAC/resource access | Service account và IAM/workload identity |
| Vị trí resource | Region AWS, endpoint/ARN dịch vụ | Resource endpoint, subscription, region | Project ID, location và endpoint dịch vụ |

Không áp dụng nguyên xi thứ tự provider của AWS SDK lên Azure hoặc GCP. Ví dụ `AWS_PROFILE` điều khiển shared AWS profile, không phải cấu hình chung cho Google Cloud Storage hoặc Azure Blob Storage. Để viết adapter đa cloud, mã nghiệp vụ có thể khai báo giao diện chung, nhưng phần cấp danh tính, permission và client configuration nên giữ theo đặc thù mỗi provider.

## 13. Bài tập thực hành có hướng dẫn

### Bài 1. Tạo hai profile và xác minh danh tính

**Giả định:** tổ chức đã cấp quyền Identity Center cho hai account test và prod read-only.

1. Dùng `aws configure sso --profile dev-sandbox` để thiết lập profile dev.
2. Đăng nhập với `aws sso login --profile dev-sandbox`.
3. Chạy `aws sts get-caller-identity --profile dev-sandbox` và kiểm tra account ID/ARN.
4. Tạo `prod-readonly` cho account production với permission set chỉ đọc.
5. Nêu cách đảm bảo ứng dụng không ghi nhầm production khi một profile bị đặt sai.

**Kết quả mong đợi:** phân biệt rõ login thành công, account được chọn, permission set được cấp và vùng AWS của resource.

### Bài 2. Phân tích ưu tiên credential

Xét một máy local có:

~~~text
AWS_PROFILE=dev-sandbox
AWS_REGION=ap-southeast-1

AWS_ACCESS_KEY_ID=<credential-cũ>
AWS_SECRET_ACCESS_KEY=<credential-cũ>
~~~

Ứng dụng Java sử dụng `DefaultCredentialsProvider` nhưng gọi S3 bị từ chối. Hãy giải thích vì sao chạy `aws sso login` không nhất thiết sửa lỗi. Đề xuất bước xác nhận nguồn credential, account và giải pháp loại bỏ key cũ khỏi environment mà không in secret.

**Gợi ý:** SDK có thể dùng environment credential trước khi đến shared profile. Cần xác minh bằng identity của client, kiểm tra env/system property, sau đó dùng SSO profile đúng. Tránh tự ghi key mới vào application để “đè” lỗi.

### Bài 3. Debug khác biệt CLI và Spring Boot

CLI chạy được:

~~~bash
aws sts get-caller-identity --profile dev-sandbox
~~~

Nhưng Spring Boot khởi động từ IDE không lấy được S3 credential. Hãy lập checklist gồm: environment IDE, `AWS_PROFILE`, user home, shared config path, cache SSO, SDK `sso`/`ssooidc` modules, bean AWSpring, region của client và lỗi IAM.

Giải thích tại sao thử lại CLI và thử Java trong **cùng môi trường process** là hai phép kiểm tra khác nhau.

### Bài 4. Thiết kế quy trình local–CI–production

Một nhóm viết Spring Boot service upload tài liệu lên S3 và publish event SQS. Hãy thiết kế:

- Local developer dùng Identity Center với profile sandbox.
- CI dùng OIDC/STS temporary credentials và account test, không cần browser.
- ECS production dùng task role và region đã cấu hình, không dùng profile của developer.
- Unit test dùng fake adapter; integration test giả lập S3/SQS với credential test; smoke test dùng IAM role riêng.

Xác định mỗi môi trường cần kiểm tra identity/account, region, bucket/queue, IAM action và các điều kiện KMS nào. Đưa ra cách ứng dụng từ chối khởi động nếu môi trường test đang trỏ vào production account.

### Bài 5. Câu hỏi suy luận

1. `aws sso login --profile dev-sandbox` thành công có chứng minh rằng application Java sẽ lấy credential từ `dev-sandbox` không? **Không**; provider chain có nguồn ưu tiên khác và cấu hình bean riêng.
2. `sso_region=us-east-1` có bắt buộc `region=us-east-1` không? **Không**; region đăng nhập và region dịch vụ độc lập.
3. Nếu `GetCallerIdentity` trả về account sandbox nhưng SQS `SendMessage` bị `AccessDenied`, nên kiểm tra gì? **Permission set/IAM, queue policy, action, ARN, region, KMS và các condition**.
4. Có nên copy thư mục `~/.aws/sso/cache` vào Docker image CI để tránh login không? **Không**; CI nên dùng workload federation/temporary role với quyền giới hạn.
5. Khi local token hết hạn, có nên tạo static access key vào `application.yml`? **Không**; đăng nhập lại Identity Center hoặc khắc phục vấn đề session/provider đúng cách.

## 14. Tổng kết

**AWS CLI profile** là cấu hình chọn cách tìm credential, account/role và region; **IAM Identity Center** là cơ chế tổ chức đăng nhập và cấp quyền truy cập account qua permission set; **AWS SDK for Java v2 và AWSpring** sử dụng credential thực tế khi ứng dụng Spring Boot gọi dịch vụ AWS. Đăng nhập thành công và có profile tên đúng chưa đủ: phải kiểm tra principal từ STS, region, policy và tài nguyên đích.

Mô hình phù hợp cho phát triển cục bộ là **AWS CLI v2 + IAM Identity Center + profile sandbox + temporary credentials**; CI và production nên dùng role/workload identity riêng. Thiết kế này tạo nền tảng an toàn để triển khai các bài tiếp theo về storage, messaging, dữ liệu, secret và kiểm thử tích hợp trên AWS, đồng thời giúp đối chiếu với identity patterns của Azure và Google Cloud.
