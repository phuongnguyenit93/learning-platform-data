# STS AssumeRole và truy cập tài nguyên khác tài khoản

## 1. Bối cảnh và mục tiêu học tập

Giả sử ứng dụng **Spring Boot** xử lý đơn hàng đang chạy trong **AWS Account A**, nhưng dữ liệu biên nhận cần đọc lại nằm ở **Amazon S3 thuộc AWS Account B**. Ứng dụng không thể lấy quyền trên bucket B chỉ bằng cách thêm starter Spring Cloud AWS, tạo `S3Client`, hay đổi `AWS_REGION`. AWS phải xác định **principal nào được quyền truy cập tài khoản B**, việc chuyển đổi danh tính có hợp lệ không và tài nguyên đích có cho phép thao tác hay không.

Bài học này thuộc chương **Nền tảng AWS** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Phạm vi toàn module là thực hành tích hợp Spring Boot với dịch vụ managed trên AWS, Azure và Google Cloud: cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá sự khác biệt giữa các provider. Riêng bài này tập trung vào **AWS Security Token Service (STS) `AssumeRole`** và cách một ứng dụng Spring Boot sử dụng **temporary credentials** để gọi tài nguyên ở tài khoản khác.

**Mục tiêu sau bài học:**

- Phân biệt truy cập trực tiếp qua resource-based policy với mô hình assume role trong tài khoản đích.
- Hiểu luồng `Account A principal → STS AssumeRole → role session ở Account B → AWS service`.
- Xây dựng **trust policy**, **identity-based policy** phía nguồn và **permissions policy** phía role đích.
- Tích hợp `StsAssumeRoleCredentialsProvider` từ **AWS SDK for Java v2** vào Spring Boot/Spring Cloud AWS, có refresh credential và quản lý vòng đời client.
- Phân biệt lỗi không assume được role với lỗi đã assume nhưng không được S3/SQS/Secrets Manager cho phép.
- Thiết kế least privilege, kiểm soát session, vùng AWS, cross-account KMS và kiểm thử end-to-end an toàn.

> **Lưu ý phiên bản:** Ví dụ Java dùng AWS SDK for Java **2.x**, phù hợp với hướng tích hợp phổ biến của Spring Cloud AWS 3.x. Các release khác nhau có thể có yêu cầu Java, Spring Boot, BOM và SDK riêng; đối chiếu tài liệu của release đang dùng trước khi áp dụng. Account ID, ARN, bucket, queue và URL trong bài chỉ là **dữ liệu giả định để học**.

## 2. Vì sao tách nhiều AWS account?

AWS Organizations và chiến lược multi-account thường dùng các account khác nhau cho phát triển, kiểm thử, production, bảo mật hoặc dữ liệu của đối tác. Ví dụ:

| Tài khoản | Account ID minh họa | Vai trò |
| --- | --- | --- |
| Account A – ứng dụng | `111122223333` | Chạy `receipt-api` bằng ECS task role |
| Account B – dữ liệu | `444455556666` | Quản lý bucket `example-partner-receipts` và IAM role đọc dữ liệu |

Lợi ích của việc tách account là có ranh giới quản trị, thanh toán, quota, IAM và chính sách tổ chức rõ hơn. Nhưng khi service A cần đọc dữ liệu B, phải cấu hình **cross-account access** có chủ đích. Hai account cùng thuộc một tổ chức AWS **không tự động** có quyền đọc tài nguyên của nhau.

Có hai mẫu truy cập phổ biến:

1. **Resource-based policy cho principal nguồn:** tài nguyên B (ví dụ S3 bucket hoặc SQS queue) cho phép một role cụ thể từ A thao tác trực tiếp. Principal vẫn là role/session của A.
2. **STS AssumeRole:** role ở A được phép assume một role do B quản lý; STS trả temporary credentials cho **role session ở B**, rồi client dùng credential đó gọi S3/SQS/Secrets Manager của B.

Không phải dịch vụ AWS nào cũng hỗ trợ resource-based policy theo cùng cách, và một số yêu cầu bảo mật khiến mô hình assume role dễ quản lý hơn. Chọn theo semantics và chính sách của từng dịch vụ.

### 2.1. So sánh hai cách truy cập

| Tiêu chí | Truy cập trực tiếp bằng resource policy | Assume role trong tài khoản đích |
| --- | --- | --- |
| Principal ký request tới tài nguyên B | Principal từ A | Session của role thuộc B |
| Điều kiện cốt lõi | Policy phía A và resource policy B cho phép thao tác phù hợp | Quyền `sts:AssumeRole` ở A; trust role B; quyền resource cho role B |
| Phù hợp khi | Dịch vụ hỗ trợ resource policy rõ ràng, chỉ một vài thao tác | Muốn role B làm ranh giới quyền tập trung, cần nhiều operation/resource |
| Có bước STS trong app? | Không bắt buộc | Có, SDK hoặc profile thực hiện |
| Cơ chế refresh role session | Không có role session B cần refresh | Phải làm mới temporary credentials của role B |
| Cần xét KMS / deny / SCP? | Có | Có |

Ví dụ S3 bucket B có thể áp bucket policy cho role A, nhưng object mã hóa SSE-KMS có thể vẫn cần cấp quyền trên KMS key. Với AssumeRole, quyền của role B thường được quản trị trong account B; bucket policy, KMS policy và các deny vẫn có thể giới hạn thêm.

## 3. Kiến trúc của STS AssumeRole giữa hai tài khoản

Một luồng điển hình:

~~~mermaid
sequenceDiagram
    participant App as Spring Boot ở Account A
    participant Base as Role nguồn A
    participant STS as AWS STS
    participant RoleB as IAM role đích B
    participant S3 as S3 bucket của B

    App->>Base: Lấy credential workload
    App->>STS: AssumeRole(RoleArn B, RoleSessionName)
    Note over STS,RoleB: Kiểm tra quyền sts:AssumeRole phía A<br/>và trust policy của role B
    STS-->>App: Temporary credentials của role session B
    App->>S3: GetObject (ký bằng credentials B)
    Note over RoleB,S3: Kiểm tra role permissions, bucket policy,<br/>KMS policy và các deny/condition liên quan
    S3-->>App: Object hoặc lỗi được xác định
~~~

**Điểm quan trọng:** STS không chuyển quyền sở hữu resource và không sao chép role B vào account A. Nó cấp **một session tạm** của IAM role B cho client đủ điều kiện. Khi gọi S3, AWS đánh giá quyền dựa trên session đó và toàn bộ chính sách áp dụng.

### 3.1. Phân biệt ba principal

- **Người hoặc workload khởi đầu:** ví dụ ECS task ở A dùng role `receipt-api-task-prod`.
- **IAM role đích:** ví dụ `arn:aws:iam::444455556666:role/partner-receipt-reader`. Role có trust policy và permissions policy.
- **Assumed-role session:** principal tạm, thường có dạng ARN `arn:aws:sts::444455556666:assumed-role/partner-receipt-reader/receipt-reader-prod`.

Cú pháp ARN của role IAM và assumed-role session **không giống nhau**. Khi xử lý CloudTrail hoặc kiểm tra STS GetCallerIdentity, hãy phân biệt role được cấu hình với session thực tế đang gửi request.

### 3.2. Điều kiện để assume role thành công

Trong tình huống cross-account thông dụng, cần đồng thời:

1. **Principal nguồn A** được identity-based policy cho phép gọi `sts:AssumeRole` trên đúng ARN role ở B.
2. **Trust policy của role B** cho phép principal nguồn A assume role bằng `sts:AssumeRole` và thỏa các điều kiện trust.
3. Không có explicit deny hoặc ràng buộc tổ chức/session khác chặn hành động assume role.
4. Nếu role B yêu cầu **ExternalId, MFA, session tags hoặc source identity**, request phải cung cấp các giá trị phù hợp.
5. Credential nguồn phải còn hiệu lực để ký STS request.

Sau khi assume thành công, **role B** còn cần quyền trên thao tác/tài nguyên cụ thể. Không được đồng nhất thành công ở bước STS với quyền đọc bucket hoặc secret.

## 4. Thiết kế policy: nguồn A, trust B, quyền B

Giả sử:

- Account A: `111122223333`.
- Source role trong A: `arn:aws:iam::111122223333:role/receipt-api-task-dev`.
- Account B: `444455556666`.
- Target role trong B: `arn:aws:iam::444455556666:role/partner-receipt-reader-dev`.
- S3 bucket trong B: `example-partner-receipts`.
- Prefix chỉ được đọc: `receipts/dev/`.

Tất cả là **dữ liệu minh họa**. Triển khai thực tế phải thay bằng ARN đúng và thực thi theo Infrastructure as Code/quy trình cấp quyền.

### 4.1. Account A: cho phép source role gọi STS AssumeRole

Identity-based permissions policy gắn lên source role trong A:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AssumePartnerReceiptReader",
      "Effect": "Allow",
      "Action": "sts:AssumeRole",
      "Resource": "arn:aws:iam::444455556666:role/partner-receipt-reader-dev"
    }
  ]
}
~~~

Policy này **không** cấp trực tiếp quyền đọc mọi S3 object ở B. Nó chỉ cho phép A yêu cầu STS assume đúng role đích. Nếu ứng dụng phải assume hai role khác nhau, liệt kê ARN cụ thể thay vì đặt `"Resource": "*"`.

Trong mô hình này, **`iam:PassRole` không thay cho `sts:AssumeRole`**. `iam:PassRole` thường liên quan việc truyền role cho một AWS service khi tạo/cấu hình tài nguyên như ECS task, còn ở đây code của ứng dụng đang yêu cầu STS tạo role session.

### 4.2. Account B: trust policy của target role

Trust policy gắn với `partner-receipt-reader-dev`:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "TrustReceiptApiTaskRole",
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/receipt-api-task-dev"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Ý nghĩa: role B chỉ nhận assume-role request được xác thực từ đúng IAM role ở A (và các điều kiện khác của policy/organization vẫn áp dụng).

Tránh mở trust thành toàn bộ account hoặc mọi principal không cần thiết. Với đối tác bên ngoài, nên cân nhắc điều kiện `sts:ExternalId`, phạm vi principal, thời hạn session và quy trình phê duyệt phù hợp.

**Trust policy là policy của IAM role**, không phải bucket policy. Đặt trust policy vào cấu hình S3 bucket sẽ không làm STS assume role thành công.

### 4.3. Account B: quyền S3 của target role

Permissions policy gắn lên chính role B:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadPartnerReceiptsOnly",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::example-partner-receipts/receipts/dev/*"
    }
  ]
}
~~~

Role B chỉ đọc được object trong prefix `receipts/dev/` khi không có policy khác chặn. Không cần `s3:ListBucket` nếu code chỉ gọi `GetObject` với key đã biết. Nếu cần liệt kê object thì cấp thêm `s3:ListBucket` trên **bucket ARN** với điều kiện prefix phù hợp.

Khi bucket thuộc cùng account B với target role B, identity-based policy của role có thể đủ cho quyền S3 cơ bản; tuy nhiên **bucket policy explicit deny**, VPC endpoint policy, KMS key policy hoặc các điều kiện tổ chức vẫn có thể ngăn truy cập. Với object mã hóa bằng customer-managed KMS key, cần xét `kms:Decrypt` và key policy theo thiết kế mã hóa.

### 4.4. Cách đọc ba policy theo thứ tự

| Giai đoạn | Vấn đề cần kiểm tra | Nằm ở đâu? |
| --- | --- | --- |
| A gọi STS | Source role A có `sts:AssumeRole` trên role B? | Identity policy A |
| STS chấp thuận | Role B có trust principal nguồn A và điều kiện phù hợp? | Trust policy B |
| Role B gọi S3 | Role B được `s3:GetObject` trên object ARN cụ thể? | Permissions policy B |
| S3/KMS trả kết quả | Có deny của bucket policy/SCP/endpoint/KMS hay không? | Các policy liên quan, account và resource |

**Sai ở bước 1/2:** không nhận được temporary credential của role B. **Sai ở bước 3/4:** STS có thể thành công nhưng thao tác `GetObject` vẫn bị `AccessDenied`. Hai nhóm lỗi phải được điều tra riêng.

## 5. Chọn nguồn credential ban đầu cho Account A

Application phải có credential nguồn hợp lệ để gọi STS.

| Môi trường chạy Spring Boot | Nguồn credential nên dùng | Điều tránh |
| --- | --- | --- |
| Laptop developer | AWS CLI profile + IAM Identity Center, permission set sandbox | Ghi static access key vào `application.yml` |
| CI bên ngoài AWS | OIDC federation/STS, role giới hạn cho job test | Access key dài hạn lưu trong pipeline |
| EC2 | Instance profile của source role A | Trộn credential từ nhiều profile/env |
| ECS/Fargate | **Task role** của service A | Nhầm task execution role với task role |
| EKS | IRSA hoặc EKS Pod Identity của Pod A | Dùng node role chung cho mọi Pod |

Với **AWS SDK for Java v2**, `DefaultCredentialsProvider` thử các nguồn theo thứ tự phổ biến: Java system properties → environment variables → web identity → shared profile → container credentials → EC2 instance profile. Vì vậy, một environment key cũ có thể ghi đè role ECS/Pod mà người vận hành đã cấu hình.

Nếu ứng dụng đang dùng source role A, SDK `StsClient` nên được tạo từ **cùng chiến lược credential nguồn** đã kiểm chứng. Đừng khởi tạo STS client với credential tĩnh lấy từ máy developer và triển khai nguyên lên production.

## 6. Chuẩn bị dependency AWS SDK v2 và Spring Cloud AWS

### 6.1. Tách trách nhiệm thư viện

**AWSpring/Spring Cloud AWS** giúp cấu hình bean, template, listener và tích hợp SDK vào ứng dụng Spring Boot. Nhưng **`AssumeRole` là API của STS trong AWS SDK**; ở mức Java, các lớp quan trọng thuộc package:

- `software.amazon.awssdk.services.sts.StsClient`.
- `software.amazon.awssdk.services.sts.model.AssumeRoleRequest`.
- `software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider`.
- `software.amazon.awssdk.auth.credentials.AwsCredentialsProvider`.

Cần phân biệt với SDK v1 có package `com.amazonaws.*`; không trộn mã mẫu hai thế hệ.

### 6.2. Maven dependency minh họa

Giả sử Spring Boot project đã chọn BOM AWSpring tương thích và dependency management đang quản lý version SDK:

~~~xml
<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>

    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sts</artifactId>
    </dependency>

    <!-- Khai báo trực tiếp khi mã ứng dụng import S3Client -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
</dependencies>
~~~

Đoạn này **chưa bao gồm** phần Spring Boot parent và BOM mà dự án thực tế cần. Nếu Maven báo version chưa được quản lý, phải bổ sung BOM hoặc version SDK đã được kiểm chứng tương thích. Không chọn tùy ý phiên bản `sts` khác với các module SDK v2 đã resolve.

Trong Gradle Kotlin DSL:

~~~kotlin
dependencies {
    // Giả định dự án đã import platform/BOM AWSpring và SDK phù hợp.
    implementation("io.awspring.cloud:spring-cloud-aws-starter-s3")
    implementation("software.amazon.awssdk:sts")
    implementation("software.amazon.awssdk:s3")
}
~~~

Ngoài compile, cần xem **runtimeClasspath**: client STS có thể dùng các module auth, HTTP và thư viện SDK liên quan. Một mismatch SDK gây lỗi runtime như `NoSuchMethodError` hoặc `NoClassDefFoundError`; hãy xem dependency tree thay vì đổ lỗi cho IAM.

## 7. Spring Boot sử dụng StsAssumeRoleCredentialsProvider

### 7.1. Vì sao chọn provider có refresh?

`AssumeRole` trả về temporary AWS credentials với thời điểm hết hạn. Nếu tự gọi STS một lần rồi đưa các string access key/secret/session token vào `StaticCredentialsProvider`, ứng dụng chạy lâu có thể gặp `ExpiredToken`.

AWS SDK for Java v2 có `StsAssumeRoleCredentialsProvider` để **lấy và làm mới** credentials của role đích. Provider này thực hiện STS call bằng **source StsClient**, rồi trả credentials role B cho client dịch vụ như S3.

~~~mermaid
flowchart LR
    A["DefaultCredentialsProvider: source role A"] --> B["StsClient"]
    B --> C["StsAssumeRoleCredentialsProvider"]
    C --> D["S3Client cross-account"]
    D --> E["S3 bucket Account B"]
    C -. "Refresh trước/khi session cần làm mới" .-> B
~~~

### 7.2. Cấu hình ứng dụng

Cấu hình chỉ chứa **role ARN và vùng**, không chứa secret:

~~~yaml
app:
  aws:
    sts:
      region: ${AWS_STS_REGION:ap-southeast-1}
    cross-account:
      role-arn: ${APP_TARGET_ROLE_ARN}
      s3-region: ${APP_TARGET_S3_REGION:ap-southeast-1}
      bucket: ${APP_TARGET_BUCKET}
~~~

`AWS_STS_REGION` xác định endpoint STS mà source client gọi, còn `APP_TARGET_S3_REGION` là vùng của bucket S3 đích. Hai region có thể khác nhau về cấu hình/kết nối, và không được nhầm với **AWS account ID** của role.

Cấu hình trên giả định các biến bắt buộc đã có khi ứng dụng chạy. Trong production, đưa role ARN/region/bucket theo deployment config hoặc secret manager phù hợp với chính sách tổ chức; không hard-code account production trong đoạn mã chung.

### 7.3. Khai báo bean STS, provider và S3 client

Một cấu hình Spring Boot có thể viết như sau:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;
import software.amazon.awssdk.services.sts.model.AssumeRoleRequest;

@Configuration
public class CrossAccountAwsConfiguration {

    @Bean(destroyMethod = "close")
    StsClient sourceStsClient(
            @Value("${app.aws.sts.region}") String stsRegion) {
        // Mặc định lấy source credentials từ môi trường chạy:
        // local profile / ECS task role / EKS workload identity / EC2 role.
        return StsClient.builder()
                .region(Region.of(stsRegion))
                .build();
    }

    @Bean(destroyMethod = "close")
    StsAssumeRoleCredentialsProvider crossAccountCredentials(
            StsClient sourceStsClient,
            @Value("${app.aws.cross-account.role-arn}") String roleArn) {

        AssumeRoleRequest request = AssumeRoleRequest.builder()
                .roleArn(roleArn)
                .roleSessionName("receipt-reader-dev")
                .durationSeconds(3600)
                .build();

        return StsAssumeRoleCredentialsProvider.builder()
                .stsClient(sourceStsClient)
                .refreshRequest(request)
                .build();
    }

    @Bean(name = "crossAccountS3Client", destroyMethod = "close")
    S3Client crossAccountS3Client(
            @Qualifier("crossAccountCredentials")
            StsAssumeRoleCredentialsProvider credentials,
            @Value("${app.aws.cross-account.s3-region}") String region) {

        return S3Client.builder()
                .region(Region.of(region))
                .credentialsProvider(credentials)
                .build();
    }
}
~~~

**Giải thích từng bước:**

1. `sourceStsClient` dùng default credentials chain nếu không cấu hình provider khác: trên ECS sẽ ưu tiên đúng task credentials khi không bị nguồn credential khác ghi đè.
2. `AssumeRoleRequest` chỉ rõ role ARN B, session name và thời hạn yêu cầu.
3. `StsAssumeRoleCredentialsProvider` chịu trách nhiệm nhận/refresh credential của **role B**.
4. `crossAccountS3Client` dùng provider B để truy cập bucket B trong vùng thích hợp.
5. Spring quản lý các bean và gọi `close()` theo lifecycle khi context đóng.

**Lưu ý auto-configuration:** nếu dự án cũng dùng starter S3 của AWSpring, việc tự tạo bean `S3Client` có thể ảnh hưởng cơ chế auto-configuration/back-off cho client mặc định. Không mặc định rằng `S3Template` hoặc các bean S3 khác sẽ sử dụng đúng role cross-account. Khi ứng dụng cần **hai client cho hai account**, hãy đặt tên/qualifier rõ ràng, kiểm tra điều kiện auto-configuration của đúng version AWSpring và cấu hình từng adapter cho client phù hợp.

Trong hệ thống nhiều target account, thường nên có một factory/cache client theo account + role + region có giới hạn và đóng client khi không dùng; không tạo một STS client/S3 client mới cho từng HTTP request.

### 7.4. Dùng client đã được gắn credential role B

Ví dụ một adapter đọc biên nhận:

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import java.nio.file.Path;

@Service
public class PartnerReceiptReader {
    private final S3Client partnerS3;
    private final String targetBucket;

    public PartnerReceiptReader(
            @Qualifier("crossAccountS3Client") S3Client partnerS3,
            @Value("${app.aws.cross-account.bucket}") String targetBucket) {
        this.partnerS3 = partnerS3;
        this.targetBucket = targetBucket;
    }

    public void download(String key, Path destination) {
        if (!key.startsWith("receipts/dev/")) {
            throw new IllegalArgumentException("Key ngoài phạm vi bài thực hành");
        }

        partnerS3.getObject(
                GetObjectRequest.builder()
                        .bucket(targetBucket)
                        .key(key)
                        .build(),
                destination);
    }
}
~~~

Ví dụ đơn giản hóa logic đường dẫn. Ứng dụng thực tế cần xử lý key validation theo nghiệp vụ, chống ghi đè file không mong muốn, giới hạn kích thước, timeout, lỗi I/O, metadata và quy định bảo mật. Kiểm tra prefix trong Java **không thay thế** IAM policy: role B cũng phải bị giới hạn về prefix.

**Quan trọng:** Provider B chỉ được gắn cho client cần truy cập B. Những client dùng tài nguyên trong A vẫn nên dùng source role A. Không thay đổi credential provider global một cách mơ hồ khiến mọi dịch vụ tự chuyển account.

## 8. Cách đơn giản hơn cho phát triển cục bộ: AWS CLI role profile

Để thử cross-account trước khi viết Java, có thể cấu hình một **source profile** đăng nhập bằng IAM Identity Center, sau đó tạo profile đích dùng `role_arn` và `source_profile`. AWS CLI/SDK sẽ làm bước assume role theo cấu hình profile.

Ví dụ `~/.aws/config`:

~~~ini
[sso-session team-sso]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile dev-source]
sso_session = team-sso
sso_account_id = 111122223333
sso_role_name = DeveloperSandbox
region = ap-southeast-1

[profile dev-target-reader]
role_arn = arn:aws:iam::444455556666:role/partner-receipt-reader-dev
source_profile = dev-source
role_session_name = local-receipt-reader
region = ap-southeast-1
~~~

Các giá trị này chỉ minh họa. Cần được Identity Center cấp permission set tương ứng và source principal có quyền assume role B; trust B phải chấp nhận role/session mà profile nguồn thực sự sử dụng.

Đăng nhập vào source profile và xác minh:

~~~bash
aws sso login --profile dev-source
aws sts get-caller-identity --profile dev-source
aws sts get-caller-identity --profile dev-target-reader
~~~

Kỳ vọng: lệnh thứ hai trả account A; lệnh thứ ba, **nếu assume role thành công**, trả account B và ARN dạng `assumed-role/...`. Không dán credential, token hoặc output nhạy cảm lên kênh công khai.

Khi chạy ứng dụng cục bộ bằng default provider chain, có thể đặt:

~~~bash
export AWS_PROFILE=dev-target-reader
export AWS_REGION=ap-southeast-1
~~~

Nếu ứng dụng dùng profile `dev-target-reader`, SDK có thể thực hiện assume role theo profile, miễn là classpath có các SDK module hỗ trợ SSO/STS phù hợp. Với profile dạng assume role, cần `sts`; với source profile Identity Center, có thể cần thêm `sso` và `ssooidc` tùy phiên bản SDK.

**Chọn một hướng rõ ràng:** nếu code đã dùng `StsAssumeRoleCredentialsProvider` để assume role B, profile nguồn được dùng cho STS client nên là **`dev-source`**. Nếu đặt `AWS_PROFILE=dev-target-reader` đồng thời code assume role B thêm lần nữa, bạn có thể vô ý tạo **role chaining**, nhận principal khác kỳ vọng hoặc làm khó chẩn đoán. Đối với bài thực hành, hãy chọn **profile tự assume role** *hoặc* **client Java tự assume role từ source profile**, rồi xác minh principal.

## 9. STS session: thời hạn, chaining và refresh

### 9.1. Temporary credentials có gì?

STS `AssumeRole` trả `Credentials` gồm:

- Access key ID.
- Secret access key.
- Session token.
- Expiration time.

Credential này là **dữ liệu bảo mật**, không phải metadata công khai. Không log, lưu file không bảo vệ, đưa vào HTTP response hoặc chèn vào CI artifacts.

`GetCallerIdentity` bằng credentials B có thể trả ARN role session, phù hợp cho việc kiểm chứng đích. Tuy nhiên, API này không chứng minh mọi resource permission trong B đã được cấp.

### 9.2. DurationSeconds và max session duration

Role B có cấu hình **maximum session duration**. `DurationSeconds` trên request phải phù hợp giới hạn STS/role. Với **role chaining** (đang dùng credentials của một assumed role để assume role tiếp), mỗi session assume-role mới bị giới hạn tối đa **1 giờ** theo quy tắc AWS STS. Vì các workload EC2/ECS/EKS thường dùng role credentials, không nên giả định request session dài nhiều giờ sẽ luôn hợp lệ trong mọi môi trường.

Đoạn code dùng `durationSeconds(3600)` để minh họa; có thể chọn thời hạn ngắn hơn theo chính sách và tần suất refresh. Cần để SDK provider refresh credentials khi gần hết hạn, thay vì tự cache kết quả STS một lần.

### 9.3. Session policies chỉ giới hạn, không mở rộng quyền

AssumeRole có thể nhận **session policy** (inline/managed) để giảm quyền thực tế của session so với permissions policy của role B. Quyền session là phép giao giữa quyền role và session policy, tiếp tục chịu ảnh hưởng của những chính sách AWS liên quan. Session policy **không thể bổ sung quyền** mà role B không có.

Ví dụ role B cho đọc `receipts/*` nhưng một session chỉ nên đọc `receipts/dev/*`: có thể dùng session policy để giới hạn thêm, bên cạnh việc thiết kế role riêng theo môi trường. Không dùng session policy làm cách thay thế cho việc giới hạn trust và role permission hợp lý.

### 9.4. SourceIdentity và session tags

Trong hệ thống có nhiều service gọi cross-account, có thể dùng `RoleSessionName`, **source identity** hoặc **session tags** để hỗ trợ truy vết và ABAC theo chính sách tổ chức. Nếu truyền session tags, role trust có thể cần cho phép `sts:TagSession`; muốn dùng source identity có thể cần `sts:SetSourceIdentity` và trust/permission phù hợp.

Các giá trị này giúp audit và policy conditions, nhưng không được xem là bằng chứng bảo mật duy nhất nếu caller có thể tự đặt chuỗi tùy ý. Nên ràng buộc điều kiện trust, danh tính nguồn và cách sinh tag theo nguồn tin cậy.

## 10. ExternalId, MFA và confused deputy

### 10.1. Khi nào cần ExternalId?

Trong mô hình **third-party access**, nhiều khách hàng có thể cho cùng một nhà cung cấp assume role vào account của họ. Khi đó phát sinh nguy cơ **confused deputy**: kẻ khác lợi dụng quyền của nhà cung cấp để thao tác vào account không thuộc họ.

Điều kiện `sts:ExternalId` trong trust policy giúp nhà cung cấp chứng minh request đang đến từ mối quan hệ khách hàng phù hợp.

Ví dụ trust policy B được tăng cường điều kiện:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::111122223333:role/receipt-api-task-dev"
      },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": {
          "sts:ExternalId": "partner-contract-example-2026"
        }
      }
    }
  ]
}
~~~

Khi đó AssumeRoleRequest phải cung cấp đúng external ID:

~~~java
AssumeRoleRequest request = AssumeRoleRequest.builder()
        .roleArn(targetRoleArn)
        .roleSessionName("receipt-reader-dev")
        .externalId("partner-contract-example-2026")
        .build();
~~~

**ExternalId không phải mật khẩu hoặc cơ chế bảo vệ thay thế trust policy.** Nó phải được thiết kế với đúng mối quan hệ nhà cung cấp/khách hàng và quy trình cấp phát; không nhầm nó với access key, OAuth token hay session token. Với hai account nội bộ có trust hạn chế rõ, ExternalId không tự động là yêu cầu bắt buộc cho mọi luồng.

### 10.2. MFA cho thao tác nhạy cảm

Một số trust policy yêu cầu điều kiện MFA. Điều đó phù hợp với thao tác của con người trong một số trường hợp; nhưng workload tự động trên ECS/EKS/EC2 không thể nhập mã MFA mỗi lần provider refresh credential.

Nếu công việc đòi hỏi kiểm soát mạnh, hãy tách **role vận hành tương tác cần MFA** khỏi **role ứng dụng tự động** có trust và permissions giới hạn, kết hợp kiểm soát deploy, audit và phê duyệt. Không xây pipeline buộc ứng dụng production chờ thao tác MFA thủ công.

## 11. Truy cập S3, SQS, Secrets Manager và KMS ở account B

### 11.1. S3: object ARN khác bucket ARN

Với `s3:GetObject`, ARN thường là:

~~~text
arn:aws:s3:::example-partner-receipts/receipts/dev/*
~~~

Nếu cần `ListObjectsV2`, quyền `s3:ListBucket` phải gắn với bucket ARN:

~~~text
arn:aws:s3:::example-partner-receipts
~~~

Có thể giới hạn prefix bằng condition tương ứng khi thiết kế `ListBucket`. Đừng cấp `s3:*` trên mọi bucket cho một service chỉ đọc biên nhận. Khi object ownership hoặc bucket policy có ràng buộc, cần kiểm tra thêm hành vi thực tế.

### 11.2. SQS: region, queue ARN và queue policy

Đối với một queue thuộc B, quyền `sqs:SendMessage` có thể được cấp cho target role B trên đúng queue ARN, ví dụ:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": "sqs:SendMessage",
      "Resource": "arn:aws:sqs:ap-southeast-1:444455556666:partner-events-dev"
    }
  ]
}
~~~

Client SQS phải trỏ đúng **region** và queue URL/name mà API tương ứng yêu cầu. Nếu thay vì AssumeRole, ứng dụng chọn cấp trực tiếp cho role A, phải xét **SQS queue resource policy** ở B cùng identity policy A. Quy tắc điều phối message, DLQ, retry, visibility timeout và idempotency không thay đổi chỉ vì request được ký bằng cross-account credentials.

### 11.3. Secrets Manager: scope secret và version

Nếu target role B đọc secret, cấp đúng `secretsmanager:GetSecretValue` trên ARN secret cần thiết. Khi dùng customer-managed KMS key, có thể cần `kms:Decrypt` và key policy tương ứng.

Đừng nhầm **secret lưu trong Secrets Manager** với **credential role của AWS**. Ứng dụng không cần đọc secret “AWS access key” từ Secrets Manager chỉ để gọi S3/SQS nếu có thể dùng STS role session. Secrets Manager thích hợp cho API token, mật khẩu database hoặc các secret nghiệp vụ thực sự cần lưu.

### 11.4. KMS cross-account: hai mặt của quyền

Khi resource ở B được mã hóa bằng customer-managed KMS key, quyền IAM trong role B có thể **chưa đủ** nếu key policy/grant không cho phép sử dụng key. Cần xem:

- Key policy và IAM permissions áp dụng cho principal thực tế của request.
- Action `kms:Decrypt`, `kms:Encrypt`, `kms:GenerateDataKey` tùy thao tác.
- Region của KMS key và dịch vụ đang sử dụng key.
- Encryption context/condition hoặc chính sách giới hạn dịch vụ nếu được cấu hình.

Một request có thể assume role thành công và có `s3:GetObject`, nhưng bị từ chối `kms:Decrypt` khi đọc object. Chẩn đoán lỗi theo cả S3 và KMS, không vội nới toàn bộ quyền S3.

## 12. Chẩn đoán sự cố cross-account theo từng chặng

### 12.1. Không assume được role

Lỗi có thể liên quan `AccessDenied` tại `sts:AssumeRole` hoặc ràng buộc trust policy. Kiểm tra:

1. **Source principal** thực tế qua STS `GetCallerIdentity` trên source credentials.
2. Source role A có identity policy `sts:AssumeRole` trên **chính xác ARN** role B không?
3. Role B trust đúng source principal/role ARN, đúng service/federated principal và các condition không?
4. Request có `ExternalId`, MFA, session tags/source identity khi trust đòi hỏi không?
5. SCP, permission boundary, session policy hoặc explicit deny có chặn không?
6. Source credential đã hết hạn hoặc vô tình bị system property/environment credential khác ghi đè không?

Nếu STS không cấp temporary credentials thì việc thêm `s3:GetObject` vào role B **chưa giải quyết lỗi AssumeRole**. Phải sửa chặng cấp quyền assume trước.

### 12.2. Assume thành công nhưng truy cập tài nguyên B bị từ chối

Kiểm tra:

- Đã dùng **credentials của role B** cho S3/SQS client hay vẫn đang gọi bằng source role A?
- Role B có permission đúng **action và resource ARN** không?
- Bucket/queue/secret policy, KMS key policy, VPC endpoint policy hoặc SCP có deny không?
- Resource nằm đúng region/account và tên/ARN chính xác không?
- Operation thực tế có gọi thêm API phụ trợ như `ListBucket`, `GetQueueUrl` hoặc `Decrypt` mà chưa được cấp không?

Một cách xác minh là tạo `StsClient` với **chính target credentials provider** rồi gọi `GetCallerIdentity`; nếu trả assumed-role ARN trong B, biết được client đang mang đúng danh tính đích.

### 12.3. Sai role chaining, token hết hạn hoặc session duration

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `ExpiredToken` sau khi chạy một thời gian | Credentials STS bị cache cứng; provider không refresh | Dùng `StsAssumeRoleCredentialsProvider` hoặc provider có refresh |
| AssumeRole yêu cầu duration quá dài | Vượt max session role hoặc giới hạn 1 giờ khi role chaining | Giảm duration và kiểm tra nguồn credential |
| STS trả đúng account nhưng ARN session khác kỳ vọng | Đang assume nhiều lần qua profile và Java code | Kiểm tra nguồn profile, role ARN và danh tính từng chặng |
| 403 S3/KMS | Role B thiếu quyền hoặc policy/resource condition chặn | Xem action, ARN, key policy, endpoint |
| Resource “không tồn tại” | Region/queue URL/key/bucket sai; thiếu quyền có thể ảnh hưởng thông báo | Đối chiếu vị trí và permissions |
| Sai account dù `AWS_PROFILE` đúng | Credential nguồn ưu tiên cao hơn profile hoặc client custom provider | Kiểm tra chain và principal từ client thật |

### 12.4. Bản đồ nhận diện lỗi

~~~mermaid
flowchart TD
    A["Ứng dụng cross-account lỗi"] --> B{"Source credentials có hợp lệ?"}
    B -->|Không| C["Sửa profile / workload role / provider chain"]
    B -->|Có| D{"STS AssumeRole thành công?"}
    D -->|Không| E["Kiểm tra sts:AssumeRole A + trust B + conditions"]
    D -->|Có| F{"Service client dùng role session B?"}
    F -->|Không| G["Sửa client/provider/qualifier"]
    F -->|Có| H{"Đúng account, region, resource?"}
    H -->|Không| I["Sửa cấu hình target ARN / region / endpoint"]
    H -->|Có| J["Kiểm tra permissions B, resource policy, KMS, SCP"]
~~~

## 13. Kiểm thử tích hợp an toàn

### 13.1. Unit test không cần gọi STS thật

Đặt giao diện nghiệp vụ tại tầng application:

~~~java
public interface ReceiptStorage {
    byte[] loadReceipt(String receiptKey);
}
~~~

Service chỉ phụ thuộc `ReceiptStorage`, còn adapter AWS dùng cross-account `S3Client`. Unit test dùng fake/mock adapter và xác minh xử lý lỗi, key validation, retry nghiệp vụ. Không dùng STS credentials thật để kiểm tra một điều kiện `if` hoặc phép chuyển đổi dữ liệu.

### 13.2. Integration test với LocalStack: giới hạn cần hiểu

Có thể dùng LocalStack hoặc emulator để kiểm tra bean, SDK client, request serialization, endpoint override và thao tác S3/SQS cơ bản. Đặt test-only endpoint, region và fake credentials tường minh để không lỡ kết nối tài khoản production.

Tuy nhiên, emulator **không chứng minh đầy đủ** IAM role trust, STS AssumeRole thật, SCP, resource policy, KMS cross-account hoặc mọi tình huống session expiration. Nếu phải kiểm thử AssumeRole end-to-end, cần tài khoản AWS sandbox riêng và quyền thực tế.

### 13.3. Smoke test trên hai account kiểm thử

Quy trình đáng tin cậy cho luồng A → B:

1. Tạo source role A và target role B riêng cho test, với trust và permission giới hạn.
2. Provision một bucket test và object giả ở B; dùng key/region cụ thể.
3. Từ **chính môi trường workload A**, xác minh principal nguồn bằng STS.
4. Gọi `AssumeRole` B bằng source credentials; xác minh assumed-role principal với cùng target credentials provider.
5. Gọi `GetObject` đúng prefix và kiểm tra dữ liệu; thử một key ngoài prefix và kỳ vọng bị từ chối khi IAM policy được thiết kế như vậy.
6. Thử sai ExternalId hoặc source principal không trusted (nếu mô hình sử dụng); bảo đảm assume thất bại.
7. Thử thao tác cần KMS trên object test nếu ứng dụng có dùng mã hóa; ghi nhận các điều kiện key policy.
8. Xóa dữ liệu kiểm thử bằng quy trình và quyền dọn dẹp riêng, không giao quyền phá hủy rộng cho runtime role.

Smoke test này xác nhận trust, quyền, region và đường đi thực tế. Nó không tự kiểm chứng khả năng chống tải cao, mọi edge case hay quy trình rotation trong nhiều ngày.

### 13.4. Theo dõi bằng log và CloudTrail

Nên ghi event name, target role ARN (đã cho phép hiển thị), service operation, region, correlation ID và loại lỗi. **Không ghi temporary access key/secret/session token.**

CloudTrail có thể hỗ trợ đối chiếu request `AssumeRole` với thao tác dịch vụ sau khi assume, cùng thông tin role session và account. Cần lưu ý **S3 object-level data events** chỉ xuất hiện theo cấu hình CloudTrail tương ứng; không mặc định mọi `GetObject` đều có log data event. Thời gian, cấu hình trail và vị trí log có thể khác nhau giữa A và B.

## 14. Bảo mật và vận hành trong ứng dụng Spring Boot

### 14.1. Ít quyền nhất ở cả hai tài khoản

- Role A chỉ được assume ARN role B thật sự cần; không cho `sts:AssumeRole` với `Resource: "*"` nếu tránh được.
- Role B chỉ có quyền trên resource/prefix/queue/secret B mà ứng dụng cần.
- Trust policy B khóa đúng principal A; áp dụng `ExternalId` ở quan hệ third-party khi thích hợp.
- Phân tách role dev/staging/prod, account IDs, resource ARNs và KMS keys; không lấy role production để chạy bài test local.
- Nếu app cần cross-account theo nhiều đối tác, cân nhắc role riêng cho từng quan hệ và audit theo role session.

### 14.2. Tính tái lập và quản lý cấu hình

Đưa role ARN, region, bucket/queue/secret ID vào cấu hình theo môi trường. Tránh cố định tên profile local trong code chung. Với AWSpring, kiểm tra cách bean auto-configuration và custom SDK client tương tác, nhất là khi ứng dụng vừa truy cập account A vừa truy cập account B.

Không tạo `StsClient` và `S3Client` mới cho mỗi request HTTP. Dùng bean/factory có lifecycle, connection reuse, retry/timeouts phù hợp; đảm bảo client và credentials provider được đóng khi ứng dụng dừng.

### 14.3. Retry và side effect

STS assume role là bước chuẩn bị credential, nhưng thao tác S3/SQS thực tế vẫn có timeout/retry. Với SQS hoặc các thao tác tạo mới, cần thiết kế idempotency theo nghiệp vụ để tránh duplicate side effect khi mạng lỗi ở thời điểm không xác định. AssumeRole **không tạo transaction phân tán** giữa account A và B.

Đối với thao tác quy mô lớn, đánh giá quota/rate limit STS, khả năng cache/refresh của provider, thời hạn session và việc dùng nhiều role. Thiết kế factory/client có giới hạn tránh burst AssumeRole không cần thiết.

## 15. Tình huống thực hành

**Đề bài:** Một hệ thống có ứng dụng Spring Boot `invoice-api` chạy trên ECS ở **Account A**, cần đọc biên nhận trên S3 thuộc **Account B** và gửi một event vào SQS thuộc B. Mã sử dụng AWS SDK v2 và Spring Cloud AWS để tích hợp với Spring. Trong dev, developer đăng nhập bằng AWS CLI + IAM Identity Center; staging/prod chạy với task role riêng.

### Nhiệm vụ A — Thiết kế chính sách

1. Vẽ luồng source ECS task role A → STS AssumeRole B → temporary credentials B → S3/SQS B.
2. Viết identity policy A cho `sts:AssumeRole` đúng ARN role B.
3. Viết trust policy B giới hạn đúng role A.
4. Viết permissions policy B: `s3:GetObject` đúng prefix và `sqs:SendMessage` đúng queue ARN. Xác định liệu cần thêm `kms:Decrypt`/`kms:GenerateDataKey` hay không.
5. Nêu tác động của SCP/resource policy và vì sao STS success không bảo đảm S3 success.

### Nhiệm vụ B — Cấu hình Spring Boot

1. Khai báo BOM/dependency tương thích, thêm `sts` và `s3`/`sqs` SDK module thực sự dùng.
2. Xây `StsAssumeRoleCredentialsProvider` dùng source role từ default credential chain, đặt role ARN B và session name.
3. Tạo client có qualifier `crossAccountS3Client`, tránh để adapter account A dùng nhầm credentials B.
4. Đưa role ARN, region, bucket/queue vào cấu hình theo môi trường; không đưa access key hoặc session token vào YAML.
5. Thiết kế quản lý vòng đời bean, credential refresh và xử lý lỗi `ExpiredToken`.

### Nhiệm vụ C — Phân tích ba lỗi

| Lỗi | Câu hỏi cần trả lời |
| --- | --- |
| `AccessDenied` khi gọi `AssumeRole` | Source A có `sts:AssumeRole`? Trust B có cho đúng source role? Điều kiện ExternalId/session policy có khớp? |
| `AssumeRole` thành công, `GetObject` thất bại | Client đã dùng session role B? Đúng object ARN/prefix? Bucket policy hoặc KMS chặn? |
| Local hoạt động nhưng ECS production lỗi | STS client đang dùng IAM Identity Center profile local hay ECS task role? Environment credential có ghi đè? Region/role ARN production có đúng? |

### Nhiệm vụ D — Đánh giá hai kiến trúc

So sánh:

- Bucket policy B trực tiếp cấp quyền cho IAM role A.
- IAM role B được A assume thông qua STS.

Nêu trade-off về quản lý trust, khả năng giới hạn quyền, truy vết role session, hỗ trợ của dịch vụ, session refresh và kiểm thử. Chỉ ra trường hợp nào một service chỉ cần resource policy mà không cần mã Java `AssumeRole` riêng.

### Tiêu chí tự đánh giá

Bài làm đạt yêu cầu khi có đủ **policy phía A, trust phía B, permissions của role B**, cấu hình region/role/session chính xác, SDK provider có refresh, không làm rò temporary credentials và kế hoạch smoke test trên hai account sandbox riêng. Cần giải thích được vì sao `iam:PassRole` không thay thế `sts:AssumeRole` và vì sao `GetCallerIdentity` không chứng minh quyền đọc mọi tài nguyên.

## 16. Liên hệ với Azure và Google Cloud

Mô hình cross-account của AWS có thể đặt cạnh những mô hình phân quyền xuyên ranh giới tổ chức/dự án trên cloud khác, nhưng **không đồng nhất API và cơ chế trust**.

| Nhu cầu | AWS | Azure | Google Cloud |
| --- | --- | --- | --- |
| Danh tính workload | IAM role, temporary STS credentials | Managed Identity / Microsoft Entra workload identity | Service account / Workload Identity Federation |
| Quyền truy cập khác ranh giới quản trị | Cross-account IAM role trust + `AssumeRole` hoặc resource policy | RBAC/resource access giữa subscription/tenant theo cơ chế danh tính phù hợp | IAM binding trên project/resource cho principal phù hợp; service-account impersonation khi thiết kế yêu cầu |
| SDK client authentication | AWS SDK `DefaultCredentialsProvider` / STS provider | Các credential provider phù hợp trong Azure SDK | Application Default Credentials/credential impersonation thích hợp |
| Điểm phải kiểm tra | Source action, target trust, permissions, SCP/resource/KMS | Tenant, identity, assignment và resource scope | Project, principal/service-account policy và resource scope |

Sự tương đồng nằm ở nguyên tắc **ủy quyền rõ danh tính và phạm vi**, không ở cú pháp role ARN, cách refresh token hay thứ tự credential chain. Với hệ thống Spring Boot đa cloud, mã nghiệp vụ nên phụ thuộc adapter; các thao tác `AssumeRole`, Azure RBAC hay GCP service account impersonation đặt tại tầng tích hợp tương ứng.

## 17. Kết luận

**STS `AssumeRole`** là cơ chế để một principal được tin cậy nhận **temporary credentials của role đích**, từ đó truy cập tài nguyên trong AWS account khác theo quyền được cấp. Trong luồng cross-account thông dụng, phải đồng bộ **`sts:AssumeRole` của source role A**, **trust policy của target role B**, và **permissions/resource/KMS policies của B**; mỗi phần có mục đích riêng.

Với Spring Boot, AWSpring giúp tích hợp client vào Spring, còn AWS SDK for Java v2 cung cấp `StsClient` và `StsAssumeRoleCredentialsProvider` để lấy và refresh role credentials. Thành công ở bước STS chỉ xác nhận có thể assume role; việc đọc/ghi S3, SQS hoặc secret còn phụ thuộc action, ARN, region, endpoint và các policy liên quan. Xác định rõ từng chặng và kiểm thử bằng chính workload identity là nền tảng an toàn cho tích hợp managed services giữa nhiều AWS account.
