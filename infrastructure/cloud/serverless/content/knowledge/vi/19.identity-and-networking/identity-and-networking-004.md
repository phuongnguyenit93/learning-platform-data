# Cấp thông tin xác thực tạm thời thay cho khóa tĩnh

Trong chương **Danh tính và mạng**, thông tin xác thực (credential) là bằng chứng mà một workload dùng để chứng minh danh tính khi gọi dịch vụ khác. Một Java function có thể cần đọc object, ghi database, gửi message, lấy secret hoặc gọi API nội bộ. Nếu nhúng access key và secret key dài hạn vào mã nguồn hay file cấu hình, mỗi lần sao chép, build hoặc triển khai đều có thể làm lộ quyền truy cập.

Cách an toàn hơn là cấp danh tính cho workload và để nền tảng phát hành credential tạm thời với phạm vi quyền hạn giới hạn. Credential có thời hạn, có thể được làm mới qua provider, và không cần được lưu thành bí mật cố định trong repository. Trên AWS, Lambda thường dùng execution role và AWS Security Token Service (STS); trên các nền tảng khác có workload identity, managed identity hoặc cơ chế federation tương đương.

Bài học thuộc module **CLOUD_SERVERLESS**, tập trung vào phát triển và triển khai ứng dụng serverless, đặc biệt là Java function kích hoạt bởi HTTP, thông điệp hoặc sự kiện. Người học xử lý trigger, trạng thái, quyền truy cập, retry, idempotency, cold start, mở rộng và chi phí để xác định khi nào nên dùng FaaS. Quản lý credential tạm thời là nền tảng để function truy cập dịch vụ an toàn khi số execution environment thay đổi liên tục.

## 1. Vì sao khóa tĩnh là rủi ro?

Một access key dài hạn thường gồm access key ID và secret access key. Một số dịch vụ còn yêu cầu session token nếu credential thuộc một phiên tạm thời. Khi dùng khóa dài hạn, ứng dụng có thể tiếp tục truy cập cho đến khi khóa bị thu hồi hoặc vô hiệu hóa.

Các rủi ro thường gặp:

- Khóa bị commit nhầm vào Git hoặc xuất hiện trong log.
- Khóa được sao chép vào file cấu hình, image hoặc artifact triển khai.
- Nhiều developer và service dùng chung một khóa nên khó truy vết ai đã thực hiện hành động.
- Khóa có quyền rộng hơn nhu cầu của một function.
- Việc xoay vòng khóa đòi hỏi cập nhật nhiều nơi và có thể gây downtime.
- Một khóa bị lộ có thể bị sử dụng từ bất kỳ nơi nào đáp ứng điều kiện xác thực, không nhất thiết từ workload ban đầu.

Đưa khóa vào environment variable không tự động làm nó an toàn. Environment variable vẫn có thể bị đọc bởi process, debugger, crash dump, cấu hình triển khai hoặc người có quyền xem cấu hình. Nếu giá trị là khóa dài hạn, rủi ro tồn tại cho đến khi khóa bị thu hồi.

Credential tạm thời giảm thời gian hữu dụng của credential bị lộ và cho phép giới hạn quyền theo phiên. Tuy nhiên, nếu attacker lấy được credential tạm thời khi nó còn hiệu lực, họ vẫn có thể sử dụng quyền của phiên đó. Vì vậy cần kết hợp thời hạn ngắn, quyền tối thiểu, bảo vệ runtime và giám sát.

## 2. Credential tạm thời gồm những gì?

Một bộ credential tạm thời thường có:

| Thành phần | Vai trò |
|---|---|
| Access key ID hoặc token identifier | Xác định credential |
| Secret access key hoặc token proof | Chứng minh quyền sở hữu credential |
| Session token hoặc bearer token | Mang thông tin phiên hoặc token được cấp |
| Expiration | Thời điểm credential hết hiệu lực |

Với AWS STS, bộ credential thường gồm access key ID, secret access key và session token, kèm thời điểm hết hạn. Khi dùng AWS API, SDK phải gửi đủ các thành phần cần thiết; chỉ có access key ID và secret access key là chưa đủ đối với một session credential.

Credential tạm thời được phát hành cho một danh tính hoặc một phiên assume role. Thời hạn có thể được cấu hình trong giới hạn của dịch vụ và loại phiên. Không nên hardcode thời điểm hết hạn hoặc tự lưu ba giá trị credential trong application config.

Một token có thời hạn không đồng nghĩa mọi thao tác được cho phép. Credential xác định danh tính; policy và resource policy mới quyết định danh tính đó được làm gì trên tài nguyên nào.

## 3. Phân biệt xác thực, phân quyền và danh tính workload

Ba câu hỏi cần được giải quyết riêng:

1. **Authentication:** Ai hoặc workload nào đang gọi dịch vụ?
2. **Authorization:** Danh tính đó được phép thực hiện hành động nào trên tài nguyên nào?
3. **Credential delivery:** Workload nhận và làm mới bằng chứng xác thực bằng cách nào?

Ví dụ, Java Lambda có thể chạy với execution role tên OrderFunctionRole. Role đó cho phép đọc một prefix trong S3 và ghi message vào một queue. AWS cấp credential tạm thời cho function để SDK ký request. Khi SDK gọi S3, AWS xác thực credential, sau đó kiểm tra policy để quyết định có cho phép GetObject trên object được yêu cầu hay không.

Không nên nhầm credential của function với credential của người dùng cuối. Người dùng gửi JWT đến API; API xác thực JWT và tạo principal nội bộ. Lambda vẫn dùng execution role riêng để truy cập AWS resource. Hai danh tính có thể cùng xuất hiện trong một request nhưng phục vụ hai ranh giới bảo mật khác nhau.

## 4. Ba danh tính cần tách trong serverless

Trong một hệ thống có pipeline triển khai và function runtime, thường có ít nhất ba danh tính:

| Danh tính | Dùng khi nào | Ví dụ quyền |
|---|---|---|
| Deployment identity | CI/CD tạo hoặc cập nhật function | Đẩy artifact, cập nhật cấu hình, gắn execution role |
| Workload identity | Function đang chạy | Đọc S3, ghi DynamoDB, gửi message |
| Caller identity | Người dùng hoặc service gọi function | Gọi API, truy cập nghiệp vụ theo tenant |

Deployment identity không nên được dùng bên trong function. Một pipeline có thể có quyền cập nhật Lambda và truyền execution role, nhưng function chỉ nên nhận quyền runtime cần thiết.

Workload identity không nên có quyền quản trị IAM hoặc sửa role của chính nó nếu nghiệp vụ không yêu cầu. Caller identity không nên được tin cậy chỉ vì request đã đến được function; adapter vẫn phải xác thực caller và kiểm tra quyền trên dữ liệu.

~~~mermaid
flowchart TB
    CI["CI/CD identity"] -->|"deploy code / configure role"| L["Lambda function"]
    IAM["IAM trust policy"] -->|"issues temporary credentials"| L
    L -->|"signed API request"| AWS["S3 / Queue / Database"]
    USER["End user token"] --> API["API Gateway / HTTP adapter"]
    API -->|"verified principal"| L
    L -->|"authorization check"| APP["Application use case"]
~~~

Việc tách ba danh tính giúp audit log trả lời được hai câu hỏi khác nhau: ai đã triển khai function và function đã thực hiện hành động nào trong runtime.

## 5. IAM role và execution role của AWS Lambda

Lambda execution role là IAM role mà Lambda assume khi chạy function. Role có hai phần cấu hình quan trọng:

- **Trust policy:** xác định principal nào được phép assume role. Với execution role, trust policy thường cho phép dịch vụ Lambda assume role.
- **Permissions policy:** xác định function được phép gọi API nào và trên resource nào.

Trust policy mẫu:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": "lambda.amazonaws.com"
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
~~~

Đây là trust relationship minh họa cho role được Lambda service sử dụng. Permission policy là tài liệu riêng. Ví dụ, nếu function chỉ cần đọc object từ một bucket prefix, policy nên giới hạn hành động và ARN đến đúng phạm vi thay vì cấp quyền S3 toàn account.

Một policy quyền tối thiểu có thể có dạng:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:GetObject"],
      "Resource": "arn:aws:s3:::company-orders/incoming/*"
    }
  ]
}
~~~

Ví dụ chưa bao gồm quyền ghi log, giải mã KMS hoặc các dependency khác. Khi triển khai thật, bổ sung đúng quyền cần thiết cho từng thao tác và kiểm tra resource policy, bucket policy, KMS key policy cùng các điều kiện liên quan.

### 5.1. Lambda execution role khác resource-based policy

Execution role quyết định Lambda có thể làm gì khi chạy. Resource-based policy của function quyết định principal bên ngoài nào được phép invoke function. Ví dụ, API Gateway hoặc một event source có thể cần quyền invoke function; điều đó không đồng nghĩa function có quyền đọc database.

Không dùng execution role để mô tả quyền gọi function từ bên ngoài. Hãy cấu hình đúng cả quyền invoke và quyền runtime.

## 6. Lambda tự cung cấp credential tạm thời

Khi function được gắn execution role, Lambda service quản lý việc assume role và cung cấp credential tạm thời cho execution environment. Java AWS SDK có thể lấy credential thông qua default credentials provider chain.

Ứng dụng không cần tạo access key dài hạn trong IAM user, không cần copy secret vào source code và không cần tự gọi STS để assume chính execution role của mình.

Một số nguyên tắc:

- Gắn execution role lúc tạo hoặc cập nhật function.
- Chỉ cấp các quyền runtime cần thiết.
- Dùng AWS SDK default credential provider chain.
- Không truyền access key/secret key vào constructor client.
- Không tự lưu credential vào file hoặc database.
- Không log credential hoặc session token.

Credential provider của SDK chịu trách nhiệm tìm nguồn credential phù hợp. Cách phân phối cụ thể do runtime và môi trường quyết định; ứng dụng nên dùng abstraction của SDK thay vì tự đọc hoặc tự ghép các biến môi trường.

## 7. Dùng AWS SDK for Java 2.x mà không có khóa tĩnh

Khi tạo AWS service client, chỉ định region và để SDK chọn credential provider:

~~~java
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

public final class StorageClients {
    private StorageClients() {
    }

    public static S3Client createS3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .build();
    }
}
~~~

Khi không chỉ định credentials provider, AWS SDK for Java 2.x tự dùng default credentials provider chain. Trong Lambda, SDK lấy credential từ execution role mà runtime cung cấp. Khi chạy local, provider chain có thể tìm profile developer hoặc nguồn credential khác đã được cấu hình. Không cần thay code giữa local và production chỉ để đổi access key.

Có thể tạo client một lần ở cấp class để tái sử dụng trong execution environment:

~~~java
public final class OrderHandler {
    private static final S3Client S3 =
            StorageClients.createS3Client();

    public OrderResult handle(OrderEvent event) {
        // Dùng S3 client đã được khởi tạo.
        return new OrderResult(event.orderId(), "ACCEPTED");
    }
}
~~~

Các kiểu OrderEvent và OrderResult là DTO minh họa. Tái sử dụng client giúp tránh khởi tạo kết nối và credential provider trong từng invocation. SDK service client là immutable/thread-safe theo thiết kế của SDK; vẫn cần kiểm tra tài liệu cho client cụ thể và đóng client khi ứng dụng thực sự kết thúc nếu môi trường có vòng đời shutdown rõ ràng.

Không làm như sau:

~~~java
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

AwsBasicCredentials credentials = AwsBasicCredentials.create(
        "AKIA...",
        "long-lived-secret");

S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(
                StaticCredentialsProvider.create(credentials))
        .build();
~~~

Đoạn trên minh họa anti-pattern vì đưa khóa tĩnh vào code. StaticCredentialsProvider phù hợp khi ứng dụng có credential cố định được cung cấp có chủ đích trong một số test hoặc tình huống đặc biệt; không nên dùng nó để lưu credential tạm thời rồi bỏ qua khả năng refresh.

## 8. Default credentials provider chain

AWS SDK for Java 2.x có DefaultCredentialsProvider để tìm credential từ các nguồn được hỗ trợ. Tùy môi trường và phiên bản SDK, các nguồn có thể gồm:

- Java system properties.
- Environment variables.
- Web identity token và role ARN.
- AWS shared profile hoặc credential process.
- Container credential endpoint.
- Instance metadata service.

SDK dùng provider chain để ứng dụng có thể chạy trong nhiều môi trường mà không nhúng credential vào code. Thứ tự và chi tiết provider có thể khác theo SDK version; khi cần kiểm soát chặt, hãy đọc tài liệu đúng phiên bản đang dùng.

Điều quan trọng: default chain không biến một khóa dài hạn thành khóa an toàn. Nếu developer export access key dài hạn vào environment, SDK vẫn có thể sử dụng credential đó. Mục tiêu là cấu hình môi trường để cung cấp workload identity hoặc credential tạm thời, không phải chỉ đổi nơi lưu khóa.

Trên Lambda, execution role là nguồn danh tính runtime. Trên máy developer, dùng AWS IAM Identity Center/SSO hoặc profile phù hợp. Trong CI/CD, ưu tiên OIDC federation hoặc cơ chế credential tạm thời thay cho IAM user key.

## 9. Credential refresh và vòng đời execution environment

Temporary credential có thời điểm hết hạn. Ứng dụng cần bảo đảm request ký bằng credential còn hiệu lực. Khi dùng provider có khả năng refresh, SDK có thể lấy credential mới theo cơ chế của provider.

Các nguyên tắc quan trọng:

- Giữ credential provider thay vì chỉ giữ một object credential đã resolve.
- Không đọc credential một lần rồi tự cache ba trường vô thời hạn.
- Không tạo StaticCredentialsProvider từ session credential nếu cần refresh.
- Dùng SDK provider chuyên biệt cho AssumeRole hoặc Web Identity.
- Xử lý lỗi refresh, network timeout và clock skew.
- Đặt timeout và retry có giới hạn khi gọi STS hoặc endpoint credential.

Trong Lambda, execution environment có thể được tái sử dụng cho nhiều invocation và bị kết thúc bất cứ lúc nào. Credential runtime được nền tảng quản lý; application không nên giả định process tồn tại đủ lâu để tự lưu credential hoặc refresh bằng một thread nền không được bảo đảm chạy.

### 9.1. Không giữ credential đã hết hạn

Một lỗi phổ biến là gọi resolveCredentials một lần lúc cold start, lấy access key/secret/session token rồi giữ chúng trong static field. Sau khi credential hết hạn, request tiếp theo có thể nhận lỗi token hết hạn hoặc chữ ký không hợp lệ.

Thay vào đó, truyền provider cho AWS SDK client. Provider biết cách lấy credential mới khi cần theo loại provider. Với STS assume role hoặc web identity, dùng provider hỗ trợ refresh thay vì tự quản lý thời điểm gọi STS.

### 9.2. Retry không thay thế refresh

Retry request với cùng credential đã hết hạn thường không giải quyết được lỗi. Nếu lỗi là credential expiration, cần refresh credential rồi mới thử lại. Nếu lỗi là AccessDenied, retry thường không có ích vì policy vẫn từ chối. Phân biệt lỗi xác thực, phân quyền và lỗi mạng để tránh retry vô hạn.

## 10. AssumeRole qua AWS STS khi cần quyền khác

Một function đôi khi cần truy cập tài nguyên ở account khác hoặc cần một bộ quyền hẹp hơn cho một tác vụ. Có thể dùng STS AssumeRole để nhận credential tạm thời của role đích.

Ví dụ sử dụng AWS SDK for Java 2.x:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.auth.StsAssumeRoleCredentialsProvider;
import software.amazon.awssdk.services.sts.model.AssumeRoleRequest;

public final class CrossAccountCredentials implements AutoCloseable {
    private final StsClient stsClient;
    private final StsAssumeRoleCredentialsProvider provider;

    private CrossAccountCredentials(
            StsClient stsClient,
            StsAssumeRoleCredentialsProvider provider) {
        this.stsClient = stsClient;
        this.provider = provider;
    }

    public static CrossAccountCredentials create() {
        StsClient sts = StsClient.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();

        AssumeRoleRequest request = AssumeRoleRequest.builder()
                .roleArn("arn:aws:iam::123456789012:role/ReadReportsRole")
                .roleSessionName("reports-reader")
                .build();

        StsAssumeRoleCredentialsProvider provider =
                StsAssumeRoleCredentialsProvider.builder()
                .stsClient(sts)
                .refreshRequest(request)
                .build();

        return new CrossAccountCredentials(sts, provider);
    }

    public AwsCredentialsProvider provider() {
        return provider;
    }

    @Override
    public void close() {
        provider.close();
        stsClient.close();
    }
}
~~~

Đây là ví dụ khung. Role nguồn phải có quyền sts:AssumeRole trên role đích và trust policy của role đích phải tin cậy role nguồn. Giữ CrossAccountCredentials sống cùng service client sử dụng provider; gọi close khi ứng dụng kết thúc. Trong Lambda, có thể khởi tạo resource holder và service client một lần cho execution environment để tái sử dụng, rồi đóng khi runtime có cơ hội shutdown. Không tạo cặp client/provider mới trong từng invocation.

Không assume role chỉ vì request gửi lên một role ARN. Role đích phải được cố định hoặc lấy từ cấu hình tin cậy, và policy phải giới hạn tài nguyên. Không để client cuối tự chọn role tùy ý.

### 10.1. Trust policy và permission policy

AssumeRole cần hai phía đồng ý:

- Caller policy cho phép principal nguồn gọi sts:AssumeRole trên role đích.
- Trust policy của role đích cho phép principal nguồn assume role.

Sau đó permissions policy của role đích quyết định session được làm gì. Một phía thiếu quyền hoặc trust không khớp sẽ khiến STS từ chối.

Khi một bên thứ ba được phép assume role trong account của bạn, có thể cần external ID trong trust condition để giảm rủi ro confused deputy. External ID phải được cấp và xác minh theo hợp đồng tích hợp; không lấy giá trị tùy ý từ request công khai.

### 10.2. Session policy và session tags

AssumeRole có thể nhận session policy để thu hẹp quyền của phiên và session tags để hỗ trợ attribute-based access control (ABAC) khi policy tài nguyên sử dụng tag. Session policy không cấp thêm quyền vượt quá quyền role; nó có thể giới hạn quyền hiệu lực.

Không đưa tenant ID do người dùng tự gửi thành session tag nếu chưa xác thực. Session tag là một phần của ngữ cảnh phân quyền và có thể làm thay đổi quyền truy cập tài nguyên.

## 11. Workload identity federation và OIDC

Khi workload chạy ngoài AWS — ví dụ CI/CD, Kubernetes hoặc một cloud khác — không nên tạo IAM user key chỉ để pipeline gọi AWS. Có thể dùng OpenID Connect (OIDC) hoặc một cơ chế federation để đổi token danh tính bên ngoài lấy credential AWS tạm thời.

Luồng khái niệm:

1. Workload chứng minh danh tính với identity provider.
2. Identity provider cấp OIDC token có issuer, audience và subject.
3. Workload gửi token cho STS.
4. STS kiểm tra trust policy và điều kiện token.
5. STS cấp credential tạm thời cho IAM role.
6. AWS SDK dùng credential đó để gọi dịch vụ.

~~~mermaid
sequenceDiagram
    participant W as CI/CD hoặc workload
    participant IDP as OIDC Identity Provider
    participant STS as AWS STS
    participant S as AWS Service
    W->>IDP: Yêu cầu identity token
    IDP-->>W: OIDC token ngắn hạn
    W->>STS: AssumeRoleWithWebIdentity
    STS->>STS: Kiểm tra issuer, audience, subject
    STS-->>W: Temporary role credentials
    W->>S: API request có chữ ký
    S-->>W: Kết quả theo IAM policy
~~~

Trust policy nên ràng buộc issuer, audience và subject cụ thể. Ví dụ, pipeline chỉ được assume role từ một repository và branch đã xác định; không cho phép mọi token từ cùng identity provider assume role.

### 11.1. Java SDK dùng web identity token

AWS SDK for Java 2.x hỗ trợ web identity token credentials provider. Khi môi trường cung cấp role ARN và token file theo convention được SDK hỗ trợ, DefaultCredentialsProvider có thể chọn provider này.

Có thể cấu hình tường minh:

~~~java
import software.amazon.awssdk.auth.credentials.WebIdentityTokenFileCredentialsProvider;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.regions.Region;

S3Client s3 = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(
                WebIdentityTokenFileCredentialsProvider.create())
        .build();
~~~

Provider đọc token file và trao đổi token để lấy credential tạm thời theo cấu hình môi trường. Không tự đọc token rồi ghi ra log hoặc đưa vào artifact. Cần kiểm tra phiên bản SDK và các biến cấu hình mà runtime/OIDC integration cung cấp.

### 11.2. Giới hạn trust theo claims

Một trust policy OIDC nên ràng buộc tối thiểu:

- Issuer đúng identity provider đã đăng ký.
- Audience đúng dịch vụ nhận token.
- Subject đúng repository, branch, workflow, namespace hoặc service account.
- Các claim bổ sung nếu quy trình yêu cầu.

Không dùng wildcard rộng như mọi repository hoặc mọi namespace nếu chỉ một workload cần quyền. Khi thay đổi branch hoặc service account, cập nhật trust policy có kiểm soát.

## 12. Workload identity trong Kubernetes

Trong Kubernetes, pod cần truy cập cloud API. Cách cũ thường là lưu access key trong Kubernetes Secret và mount vào container. Cách này vẫn tạo khóa dài hạn, cần rotation và có thể bị đọc bởi workload hoặc người có quyền truy cập secret.

Trên EKS, IAM Roles for Service Accounts (IRSA) cho phép gắn IAM role với Kubernetes service account qua OIDC. Pod nhận web identity token và AWS SDK trao đổi token đó để lấy credential tạm thời.

Trên Kubernetes ở nền tảng khác, có thể dùng workload identity federation hoặc credential broker phù hợp. Nguyên tắc chung:

- Mỗi workload hoặc service account có danh tính riêng.
- Token có audience và subject được giới hạn.
- Role chỉ có quyền cần thiết.
- Không chia sẻ một credential rộng cho toàn cluster.
- Pod không được truy cập token của service account khác.
- Tắt automount service account token nếu workload không cần.

Không nhầm Kubernetes service account với IAM role. Service account xác định danh tính trong cluster; federation map danh tính đó sang cloud principal.

## 13. Tương đương trên Google Cloud và Azure

Ý tưởng workload identity không chỉ có trên AWS. Các cloud provider có cơ chế cấp credential ngắn hạn cho workload.

| Nền tảng | Cơ chế thường dùng | Java integration |
|---|---|---|
| AWS Lambda | IAM execution role, STS | AWS SDK default credentials provider |
| Google Cloud Functions/Cloud Run | Service account gắn với workload, metadata server, Application Default Credentials | Google Auth Library |
| Google Cloud bên ngoài | Workload Identity Federation | Application Default Credentials với federation config |
| Azure Functions/App Service | Managed Identity | Azure Identity SDK |
| Azure bên ngoài | Workload identity federation/service principal federation | Azure Identity SDK |

### 13.1. Google Cloud Application Default Credentials

Trên Google Cloud, workload có thể chạy với service account được gắn vào runtime. Google client library dùng Application Default Credentials (ADC) để tìm credential phù hợp, thường thông qua metadata server trong môi trường Google Cloud.

Ví dụ Java:

~~~java
import com.google.auth.oauth2.GoogleCredentials;
import com.google.cloud.storage.Storage;
import com.google.cloud.storage.StorageOptions;

GoogleCredentials credentials =
        GoogleCredentials.getApplicationDefault();

Storage storage = StorageOptions.newBuilder()
        .setCredentials(credentials)
        .build()
        .getService();
~~~

Ở môi trường local, ADC có thể dùng credential của developer đã đăng nhập bằng công cụ Google Cloud. Ở môi trường production, nên gắn service account có quyền tối thiểu hoặc dùng Workload Identity Federation thay cho file JSON key dài hạn.

Không đóng gói service account JSON key vào JAR, container image hoặc source repository. Nếu tổ chức bắt buộc dùng key trong một trường hợp đặc biệt, cần quản lý trong secret manager, hạn chế quyền và có rotation rõ ràng.

### 13.2. Azure Managed Identity

Trên Azure, Managed Identity cho phép resource có danh tính do nền tảng quản lý. Java SDK có thể dùng Azure Identity để lấy token mà không cần lưu client secret trong ứng dụng.

Ví dụ:

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;

DefaultAzureCredential credential =
        new DefaultAzureCredentialBuilder().build();

BlobServiceClient blobClient =
        new BlobServiceClientBuilder()
                .endpoint("https://example.blob.core.windows.net")
                .credential(credential)
                .buildClient();
~~~

DefaultAzureCredential hỗ trợ nhiều nguồn credential theo môi trường, bao gồm các nguồn developer và managed identity. Trong production, cần kiểm soát rõ identity được chọn; nếu muốn chỉ dùng managed identity, có thể cấu hình ManagedIdentityCredential tương ứng. Quyền truy cập dữ liệu được cấp qua Azure RBAC hoặc cơ chế phù hợp với dịch vụ.

## 14. Credential cho người dùng cuối khác workload identity

Một Java function có thể vừa dùng workload identity để gọi AWS, vừa xử lý request của người dùng có JWT. Hai loại credential này không nên bị trộn.

Ví dụ:

- Client gửi access token tới API Gateway.
- API Gateway hoặc function xác thực token và tạo principal.
- Application kiểm tra principal có quyền thao tác trên orderId và tenant hay không.
- Function dùng execution role để ghi dữ liệu hoặc phát event.

Không lấy token của người dùng rồi dùng nó như credential AWS. Cũng không dùng execution role của function để suy ra người dùng cuối có quyền truy cập mọi dữ liệu mà function có thể đọc.

Nếu cần truy cập cloud resource thay mặt người dùng, phải thiết kế delegated authorization hoặc token exchange theo cơ chế được cloud provider hỗ trợ, với audience, scope và policy rõ ràng. Không tự chuyển tiếp bearer token tới dịch vụ không phải audience của token.

## 15. Least privilege và giới hạn phạm vi credential

Credential tạm thời có thể vẫn rất nguy hiểm nếu role có quyền quá rộng. Least privilege là nguyên tắc cấp đúng hành động, đúng tài nguyên, đúng điều kiện và trong thời gian cần thiết.

Nên:

- Tách role theo function hoặc nhóm chức năng có ranh giới rõ.
- Giới hạn Action và Resource.
- Dùng condition theo tag, encryption context, source ARN hoặc network khi phù hợp.
- Tránh wildcard trên hành động quản trị.
- Tách quyền đọc và ghi.
- Giới hạn assume role và role chaining.
- Dùng session policy để thu hẹp quyền khi cần.
- Rà soát quyền dựa trên CloudTrail và hoạt động thực tế.

Một role dùng chung cho hàng chục function khiến sự cố ở một function có thể ảnh hưởng toàn bộ nhóm. Khi một function chỉ cần đọc object, không nên dùng role có quyền xóa bucket hoặc sửa IAM policy.

### 15.1. Quyền deployment khác quyền runtime

Pipeline thường cần quyền cập nhật function và iam:PassRole để gắn execution role vào Lambda. Quyền PassRole phải giới hạn đúng role được phép truyền. Không cấp cho pipeline quyền truyền bất kỳ role nào trong account.

Execution role không nên có quyền cập nhật code hoặc thay đổi trust policy. Tách quyền deploy và quyền runtime giúp giảm tác động khi một credential bị lộ.

## 16. Network path tới dịch vụ cấp credential

Credential provider có thể cần kết nối tới endpoint để trao đổi token hoặc refresh session. Network policy vì vậy ảnh hưởng trực tiếp đến khả năng lấy credential.

Với AWS:

- STS có regional endpoint và global endpoint; chọn endpoint theo cấu hình Region và chính sách tổ chức.
- Workload trong private subnet có thể cần NAT hoặc VPC interface endpoint phù hợp để gọi STS.
- Web identity federation cần truy cập STS và token file được mount an toàn.
- Container credential endpoint hoặc metadata endpoint cần được SDK truy cập đúng cách.
- DNS, route table, security group và network ACL có thể làm request tới endpoint thất bại.

Không phải mọi credential refresh trong Lambda đều cần function tự gọi STS trực tiếp. Khi Lambda cấp execution role, nền tảng quản lý credential runtime. Chỉ cấu hình đường mạng tới STS khi ứng dụng hoặc SDK thực sự cần gọi STS, ví dụ AssumeRole hoặc Web Identity trong workload.

Nếu function được gắn VPC, không mặc định function có internet access. Một function trong private subnet thường cần NAT gateway hoặc VPC endpoint để gọi dịch vụ bên ngoài. Cần phân biệt endpoint cho AWS service với endpoint của third-party identity provider.

## 17. Xử lý lỗi credential và phân loại sự cố

Một số lỗi phổ biến:

| Dấu hiệu | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| Unable to load credentials | Không tìm thấy nguồn credential | Kiểm tra execution role, provider chain và môi trường |
| ExpiredToken | Session credential hết hạn | Dùng provider có refresh, kiểm tra clock và vòng đời |
| InvalidClientTokenId | Credential sai hoặc không còn hợp lệ | Xác minh nguồn credential và account |
| SignatureDoesNotMatch | Secret/token sai, request canonicalization hoặc clock skew | Kiểm tra provider, đồng hồ và request signing |
| AccessDenied | Credential hợp lệ nhưng policy không cho phép | Kiểm tra IAM, resource policy, SCP và permission boundary |
| STS timeout | Không truy cập được endpoint hoặc network bị chặn | Kiểm tra DNS, route, NAT/VPC endpoint và timeout |
| AssumeRole denied | Trust policy hoặc caller policy không khớp | Kiểm tra principal, action, conditions và role ARN |

Không retry vô hạn với AccessDenied hoặc trust policy sai. Đó thường là lỗi cấu hình hoặc quyền. Với lỗi mạng tạm thời, dùng retry có backoff và giới hạn. Với expired credential, để provider refresh credential rồi thực hiện lại theo khả năng của SDK.

Không ghi credential hoặc token vào log khi điều tra. Có thể ghi provider type, role ARN đã được làm sạch, AWS request ID, operation và error code. Tránh ghi toàn bộ exception nếu message chứa URL hoặc thông tin nhạy cảm.

## 18. Kiểm tra danh tính runtime an toàn

Trong quá trình debug, cần biết function đang chạy dưới role nào. AWS STS GetCallerIdentity có thể trả account, ARN và user ID của caller hiện tại. Đây là cách xác minh danh tính đã được chọn, không phải cách cấp thêm quyền.

Có thể gọi trong môi trường kiểm thử hoặc lúc khởi tạo có kiểm soát:

~~~java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

try (StsClient sts = StsClient.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build()) {

    GetCallerIdentityResponse identity =
            sts.getCallerIdentity();

    System.out.println("Account: " + identity.account());
    System.out.println("Arn: " + identity.arn());
}
~~~

Ví dụ chỉ in thông tin định danh không bí mật. Không gọi GetCallerIdentity ở mọi invocation nếu không cần vì đây vẫn là một network request. Trong production, có thể ghi thông tin role/ARN đã được xác minh ở thời điểm startup hoặc theo quy trình chẩn đoán được kiểm soát.

## 19. Bảo vệ token và credential trong ứng dụng

Credential tạm thời vẫn phải được bảo vệ như bí mật. Các nguyên tắc:

- Không ghi access key, secret, session token hoặc bearer token vào log.
- Không trả credential trong HTTP response hoặc message.
- Không serialize credential vào DTO nghiệp vụ.
- Không lưu credential trong database như trạng thái lâu dài.
- Không đưa token file vào image hoặc artifact.
- Hạn chế quyền đọc process environment và filesystem.
- Dùng TLS để bảo vệ credential khi truyền qua network.
- Hạn chế debug endpoint hoặc heap dump ở production.
- Xóa credential khỏi test fixture trước khi commit.
- Dùng secret manager cho secret thực sự cần tồn tại lâu, như mật khẩu legacy hoặc private key bên thứ ba.

Không nên tự mã hóa một khóa dài hạn rồi lưu cạnh ứng dụng như thể đã loại bỏ rủi ro. Nếu ứng dụng có thể giải mã khóa, attacker chiếm được cùng runtime hoặc quyền giải mã cũng có thể lấy được khóa.

## 20. Kiểm thử local, CI/CD và production

Mỗi môi trường cần một nguồn credential phù hợp:

| Môi trường | Cách khuyến nghị |
|---|---|
| Developer workstation | IAM Identity Center/SSO hoặc profile developer có quyền giới hạn |
| Unit test | Fake client/provider hoặc stub, không cần cloud key thật |
| Integration test | Role tạm thời hoặc sandbox account riêng |
| CI/CD | OIDC federation hoặc credential tạm thời |
| AWS Lambda production | Execution role |
| Google Cloud runtime | Service account/workload identity và ADC |
| Azure runtime | Managed Identity |

Không copy khóa production xuống laptop để debug. Nếu cần truy cập dữ liệu production, dùng quy trình break-glass hoặc role có phê duyệt, thời hạn và audit phù hợp.

Unit test có thể inject provider giả:

~~~java
import software.amazon.awssdk.auth.credentials.AwsCredentials;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;

public final class TestCredentialsProvider
        implements AwsCredentialsProvider {

    @Override
    public AwsCredentials resolveCredentials() {
        return AwsBasicCredentials.create(
                "test-access-key",
                "test-secret-key");
    }
}
~~~

Chỉ dùng credential giả trong test và không để chúng có quyền truy cập cloud thật. Với test sử dụng session credential, có thể dùng AwsSessionCredentials giả với session token không có giá trị; tuyệt đối không lấy token thật từ production để đưa vào test.

## 21. Di chuyển từ khóa tĩnh sang workload identity

Một kế hoạch migration an toàn có thể gồm:

1. Kiểm kê nơi đang dùng access key dài hạn: source code, environment, CI secret, file cấu hình, container image và secret store.
2. Xác định mỗi workload cần hành động và tài nguyên nào.
3. Tạo role hoặc workload identity riêng với quyền tối thiểu.
4. Cấu hình trust relationship cho Lambda, OIDC provider, service account hoặc managed identity.
5. Chuyển code sang SDK default credential provider hoặc provider hỗ trợ refresh.
6. Triển khai vào môi trường test và xác minh caller identity.
7. Kiểm thử các thao tác được phép và bị từ chối.
8. Triển khai dần sang production, theo dõi AccessDenied và lỗi refresh.
9. Thu hồi khóa tĩnh cũ sau khi xác nhận không còn workload phụ thuộc.
10. Kiểm tra repository, lịch sử CI và artifact để loại bỏ bản sao credential đã lộ.

Nếu một khóa đã từng được commit hoặc chia sẻ, xóa file khỏi nhánh hiện tại chưa đủ. Cần rotate hoặc revoke credential vì bản sao có thể còn trong Git history, log, cache hoặc artifact.

## 22. Những lỗi thường gặp

**Đặt access key trong source code:** Khóa có thể bị commit hoặc đóng gói. Dùng workload identity và provider của SDK.

**Đưa khóa vào environment variable rồi coi là an toàn:** Environment variable vẫn là nơi lưu credential dài hạn. Chuyển sang credential tạm thời do runtime cấp.

**Dùng IAM user cho Lambda:** Tạo khóa dài hạn không cần thiết. Gắn execution role cho function.

**Dùng một role quá rộng cho nhiều function:** Một function bị xâm nhập có thể tác động nhiều tài nguyên. Tách role và giới hạn quyền.

**Nhầm trust policy với permissions policy:** Role có thể được assume nhưng không có quyền gọi API, hoặc ngược lại. Kiểm tra cả hai phía.

**Giữ credential đã resolve trong static field:** Credential hết hạn nhưng ứng dụng vẫn dùng giá trị cũ. Giữ credential provider có khả năng refresh.

**Tự assume role cho mọi invocation:** Tăng latency và áp lực STS. Chỉ assume role khi cần ranh giới quyền riêng; tái sử dụng provider/client đúng vòng đời.

**Tin role ARN từ request:** Client có thể yêu cầu assume role khác. Role đích phải đến từ cấu hình tin cậy và policy giới hạn.

**Không cấp đường mạng tới STS:** Provider cần gọi STS nhưng function trong private subnet không có route. Cấu hình NAT hoặc VPC endpoint phù hợp.

**Retry AccessDenied liên tục:** Lỗi policy không tự hết. Phân loại lỗi và sửa quyền/trust policy.

**Ghi token vào log để debug:** Log có thể trở thành nguồn rò rỉ credential. Chỉ ghi error code, request ID và metadata không nhạy cảm.

**Không thu hồi khóa cũ:** Workload đã chuyển đổi nhưng khóa dài hạn vẫn còn hiệu lực. Revoke và kiểm tra nơi sử dụng.

## 23. Checklist trước khi đưa workload lên production

- [ ] Function có execution role hoặc workload identity riêng.
- [ ] Deployment identity, workload identity và caller identity được tách biệt.
- [ ] Trust policy chỉ cho đúng service hoặc workload assume role.
- [ ] Permissions policy chỉ cấp hành động và tài nguyên cần thiết.
- [ ] Java SDK dùng DefaultCredentialsProvider hoặc provider phù hợp.
- [ ] Không có access key dài hạn trong source, artifact hoặc image.
- [ ] Credential provider được tái sử dụng và hỗ trợ refresh.
- [ ] Không cache credential đã resolve qua thời điểm hết hạn.
- [ ] AssumeRole/OIDC có trust condition giới hạn issuer, audience và subject.
- [ ] Session policy hoặc session tags được dùng đúng mục đích nếu cần.
- [ ] Role runtime không có quyền deploy hoặc sửa IAM nếu không cần.
- [ ] Network tới STS/metadata/identity endpoint được cấu hình đúng.
- [ ] Không log credential, token hoặc session secret.
- [ ] Lỗi xác thực, phân quyền và network được phân loại riêng.
- [ ] Có kiểm thử quyền được phép và quyền bị từ chối.
- [ ] Có CloudTrail hoặc audit phù hợp để truy vết hành động.
- [ ] Khóa tĩnh cũ đã được revoke sau migration.
- [ ] Developer và CI/CD dùng danh tính tạm thời thay vì khóa production.

## Kết luận

Credential tạm thời cho phép workload chứng minh danh tính mà không phải lưu khóa dài hạn trong code hoặc artifact. Trên AWS Lambda, execution role kết hợp với STS và AWS SDK credential provider là cách thông dụng; OIDC federation phù hợp cho workload ngoài AWS và CI/CD. Google Cloud ADC/workload identity và Azure Managed Identity áp dụng cùng nguyên tắc trên nền tảng tương ứng.

Để triển khai an toàn, cần tách danh tính deploy, danh tính workload và danh tính caller; giới hạn trust policy và permissions policy; dùng provider có khả năng refresh; bảo đảm network tới endpoint cần thiết; và không ghi credential vào log. Credential ngắn hạn giảm cửa sổ rủi ro, nhưng quyền tối thiểu, kiểm soát danh tính và audit vẫn là các lớp bảo vệ bắt buộc.

