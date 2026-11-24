# Không tìm thấy danh tính hoặc chọn nhầm tài khoản, tenant, project

Ứng dụng Spring Boot có thể kết nối tới endpoint cloud nhưng vẫn bị từ chối truy cập, hoặc request thành công nhưng chạy dưới một tài khoản ngoài dự kiến. Lỗi thường xuất hiện khi SDK tự chọn credentials từ nhiều nguồn: biến môi trường, profile CLI, workload identity, managed identity, service account hoặc metadata server.

Khi tích hợp AWS, Azure và Google Cloud trong cùng một ứng dụng, cần xác định hai điều độc lập cho mỗi request:

- **Danh tính nào đang ký request?** Ví dụ AWS IAM role, Microsoft Entra service principal/managed identity hoặc Google service account/federated principal.
- **Request đang nhắm tới tài nguyên và phạm vi nào?** Ví dụ AWS account và region, Azure tenant/subscription/resource, Google Cloud project và resource name.

Chọn đúng project hoặc subscription không tự đổi danh tính. Xác thực bằng đúng service account cũng không tự chọn đúng project chứa bucket hoặc topic. Bài này hướng dẫn truy tìm credential source thực tế, xác minh principal, sửa cấu hình tài khoản/tenant/project và phân biệt lỗi authentication với authorization.

## 1. Phân biệt danh tính và ngữ cảnh tài nguyên

| Provider | Danh tính xác thực | Ngữ cảnh chọn tài nguyên | Ví dụ |
| --- | --- | --- | --- |
| AWS | IAM user, IAM role, assumed role session hoặc web identity | AWS account, region, ARN/resource ID | Role orders-runtime trong account 123456789012; bucket ở ap-southeast-1 |
| Azure | Microsoft Entra user, service principal, managed identity hoặc federated workload identity | Tenant, subscription, resource group, resource ID và Azure cloud | Managed identity trong tenant A; Storage Account thuộc subscription B |
| Google Cloud | User, service account hoặc federated principal | Project ID/number, folder/organization và resource name | Service account của project app-prod ghi object vào bucket thuộc archive-prod |

Các khái niệm có quan hệ nhưng không thay thế nhau:

- **AWS account ID** xác định account sở hữu IAM principal hoặc resource. **Region** xác định vị trí dịch vụ; region không phải danh tính.
- **Azure tenant ID** xác định Microsoft Entra directory nơi principal được xác thực. **Subscription ID** xác định phạm vi quản lý tài nguyên Azure; một tenant có thể có nhiều subscription.
- **Google Cloud Project ID** xác định project context của API hoặc resource. **Principal** được lấy từ credentials; project ID không quyết định tài khoản nào ký request.
- **Resource name đầy đủ** có thể chỉ rõ project/account/resource khác với project mặc định của ứng dụng.
- **Quota/billing project** có thể khác project sở hữu resource và cũng không đổi principal.

Khi nhận lỗi 403, hãy ghi lại cả principal thực tế và resource đích. Khi thấy dữ liệu được ghi vào nhầm account/project, kiểm tra credential source lẫn resource identifier.

## 2. Quy trình chẩn đoán chung trong Spring Boot

Thực hiện theo thứ tự để tránh thay credentials khi lỗi thực ra nằm ở resource context:

1. Xác định service client phát sinh lỗi: AWS S3/SQS, Azure Blob/Service Bus hay Google Cloud Storage/Pub/Sub.
2. Xác định bean/client được inject, tên qualifier, cấu hình profile và property đang hoạt động.
3. Xác định credential provider mà client sử dụng: default chain, credential tường minh, CLI credential, managed identity hay workload identity.
4. Xác minh principal bằng công cụ hoặc API của chính provider.
5. Xác minh account/tenant/project/subscription và region/resource name.
6. Nếu principal và resource đều đúng, kiểm tra IAM/RBAC/data-plane permission, API enablement, endpoint và network.
7. Lặp lại phép kiểm tra trong đúng môi trường chạy ứng dụng: cùng container, pod, VM, service definition và environment variables.

Một lệnh CLI chạy trên máy phát triển không chứng minh Java process đang dùng cùng credentials. Ứng dụng có thể nhận biến môi trường khác từ IDE, Docker Compose, Kubernetes, systemd, CI/CD hoặc nền tảng triển khai.

## 3. AWS: xác định IAM principal mà SDK for Java 2.x đang dùng

### 3.1. Thứ tự Default Credentials Provider Chain

AWS SDK for Java 2.x dùng `DefaultCredentialsProvider` khi client không chỉ định credentials provider riêng. Chain tìm credentials theo thứ tự:

1. Java system properties: `aws.accessKeyId`, `aws.secretAccessKey`, `aws.sessionToken`.
2. Environment variables: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`.
3. Web identity token: `AWS_WEB_IDENTITY_TOKEN_FILE`, `AWS_ROLE_ARN` và session name tùy chọn.
4. Shared credentials/config files thông qua profile provider.
5. ECS container credentials endpoint.
6. EC2 instance profile qua Instance Metadata Service (IMDS).

Provider đầu tiên tìm được credentials hợp lệ sẽ kết thúc quá trình tìm kiếm. Vì vậy, biến môi trường còn sót từ máy local hoặc CI có thể khiến ứng dụng dùng IAM user/role khác thay cho task role hoặc EC2 instance role mà bạn dự định sử dụng.

Ví dụ: container chạy trên ECS có task role orders-runtime, nhưng Docker image hoặc task definition vẫn truyền AWS_ACCESS_KEY_ID và AWS_SECRET_ACCESS_KEY. SDK sẽ tìm thấy biến môi trường trước ECS container credentials và dùng identity từ cặp khóa đó.

### 3.2. Xác minh identity bằng AWS STS

Chạy trong cùng môi trường và profile mà bạn muốn kiểm tra:

```bash
aws configure list
aws sts get-caller-identity
```

Nếu dùng profile cụ thể:

```bash
aws configure list --profile orders-prod
aws sts get-caller-identity --profile orders-prod
```

`aws configure list` cho biết profile, region và nguồn cấu hình của các giá trị. Access key được che một phần; không chia sẻ output có thông tin nhạy cảm.

`aws sts get-caller-identity` trả về:

- `Account`: AWS account của caller.
- `Arn`: ARN của IAM user hoặc role session.
- `UserId`: định danh caller.

Ví dụ ARN có thể là `arn:aws:sts::123456789012:assumed-role/orders-runtime/session-name`. ARN dạng `assumed-role` cho biết request đang dùng role session; hãy đối chiếu account ID và role name với môi trường mong đợi.

API `GetCallerIdentity` không yêu cầu IAM permission thông thường để trả về thông tin caller. Đây là phép kiểm tra hữu ích trước khi điều tra quyền truy cập resource.

Để xác minh đúng credential provider mà Java client đang dùng, có thể gọi STS bằng chính provider được truyền vào client:

```java
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.sts.StsClient;
import software.amazon.awssdk.services.sts.model.GetCallerIdentityResponse;

AwsCredentialsProvider credentialsProvider =
        DefaultCredentialsProvider.create();

try (StsClient sts = StsClient.builder()
        .region(Region.US_EAST_1)
        .credentialsProvider(credentialsProvider)
        .build()) {
    GetCallerIdentityResponse caller = sts.getCallerIdentity();
    System.out.printf("AWS caller account=%s arn=%s%n",
            caller.account(), caller.arn());
}
```

Nếu S3 client dùng một provider tường minh khác, hãy truyền chính provider đó vào STS client. Ví dụ cần AWS SDK STS module cùng phiên bản với các AWS SDK module còn lại. Chỉ log account/ARN khi cần chẩn đoán; tuyệt đối không log credentials hoặc session token.

### 3.3. Kiểm tra nguồn credentials bị ưu tiên nhầm

Kiểm tra tên biến môi trường, không in giá trị secret:

```bash
env | cut -d= -f1 | grep -E '^(AWS_PROFILE|AWS_REGION|AWS_DEFAULT_REGION|AWS_ACCESS_KEY_ID|AWS_WEB_IDENTITY_TOKEN_FILE|AWS_ROLE_ARN|AWS_CONTAINER_CREDENTIALS_RELATIVE_URI)$'
```

Trên Windows PowerShell:

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -in @('AWS_PROFILE','AWS_REGION','AWS_DEFAULT_REGION','AWS_ACCESS_KEY_ID','AWS_WEB_IDENTITY_TOKEN_FILE','AWS_ROLE_ARN') } | Select-Object -ExpandProperty Name
```

Chỉ cần thấy `AWS_ACCESS_KEY_ID` có giá trị đã đủ để điều tra xem có static credentials được inject không; không cần in hoặc gửi secret key. Nếu ứng dụng cần ECS task role, EC2 instance profile hoặc EKS web identity, loại bỏ static credentials không còn cần thiết khỏi deployment configuration.

`AWS_PROFILE` chọn profile khi SDK đi tới profile provider trong chain. Nó không bảo đảm profile sẽ thắng credentials ở các bước ưu tiên cao hơn như Java system properties hoặc environment credentials. Khi muốn kiểm tra profile, dùng cùng `--profile` với AWS CLI và bảo đảm Java process không có nguồn credentials ưu tiên khác.

### 3.4. Region là cấu hình riêng

Credentials xác định IAM principal; region chọn endpoint dịch vụ. Có thể kiểm tra region đang được CLI sử dụng bằng:

```bash
aws configure list
aws configure list --profile orders-prod
```

Trong Spring Cloud AWS, cấu hình region tĩnh có thể được đặt theo release line, ví dụ:

```yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
```

Khi tự tạo SDK client, chỉ định region rõ ràng:

```java
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

S3Client s3Client = S3Client.builder()
        .region(Region.AP_SOUTHEAST_1)
        .credentialsProvider(DefaultCredentialsProvider.create())
        .build();
```

Nếu dùng bucket ở region khác, xác minh region bucket và endpoint/redirect của API. Không đổi IAM role chỉ để xử lý lỗi region mismatch.

### 3.5. Phân biệt identity, trust policy và resource policy

- **Credentials provider** tìm identity mà SDK dùng.
- **AssumeRole trust policy** quyết định principal nào được phép nhận role.
- **Identity policy** cấp quyền cho role/user gọi dịch vụ.
- **Resource policy** trên bucket/queue/key có thể cho phép hoặc từ chối principal.
- **SCP, permission boundary và session policy** có thể giới hạn quyền hiệu lực.

Nếu STS trả về đúng ARN nhưng S3 trả AccessDenied, identity đã được xác định; hãy kiểm tra bucket policy, IAM policy, KMS key policy, SCP và quyền data-plane. Nếu STS trả về account/role khác, sửa credential chain trước.

## 4. Azure: xác định tenant, principal và subscription

### 4.1. DefaultAzureCredential chọn credential theo chain

Azure Identity Java cung cấp `DefaultAzureCredential`, một chain gồm nhiều nguồn xác thực. Theo tài liệu hiện hành, chain mặc định thử lần lượt:

1. `EnvironmentCredential`.
2. `WorkloadIdentityCredential`.
3. `ManagedIdentityCredential`.
4. `IntelliJCredential`.
5. `VisualStudioCodeCredential` khi thành phần broker cần thiết được cài.
6. `AzureCliCredential`.
7. `AzurePowerShellCredential`.
8. `AzureDeveloperCliCredential`.
9. Broker credential nếu dependency broker được cài đặt.

Thứ tự và các credential khả dụng phụ thuộc phiên bản `azure-identity` cùng cấu hình builder. Chain dừng khi một credential lấy được token. Token hợp lệ không đồng nghĩa principal đó có quyền trên Storage Account hoặc Service Bus đang gọi.

Một tình huống dễ gặp: máy dev đã đặt `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET` cho một service principal cũ. `EnvironmentCredential` đứng trước Managed Identity và Azure CLI, nên Java có thể tiếp tục dùng service principal đó dù bạn vừa đăng nhập `az login` bằng tài khoản khác.

### 4.2. Kiểm tra tenant và subscription của Azure CLI

Xem subscription mặc định và tenant:

```bash
az account show --query "{tenantId:tenantId, subscriptionId:id, subscriptionName:name, user:user.name}" --output json
```

Liệt kê subscription mà tài khoản hiện tại có thể truy cập:

```bash
az account list --all --output table
```

Đăng nhập vào tenant mong muốn:

```bash
az login --tenant TENANT_ID
```

Chọn subscription cụ thể cho các lệnh Azure CLI:

```bash
az account set --subscription SUBSCRIPTION_ID
az account show
```

`az account set` thay đổi subscription mặc định của Azure CLI. Nó không đổi tenant hoặc principal của một credential được tạo tường minh trong Java, và không tự cấp quyền trên resource.

Nếu subscription mới vừa được cấp mà chưa xuất hiện, làm mới phiên CLI bằng đăng nhập lại và kiểm tra quyền truy cập subscription. Nếu vẫn không thấy subscription, cần xác minh subscription có thuộc tenant mà tài khoản đang đăng nhập và tài khoản có role phù hợp hay không.

### 4.3. Kiểm tra EnvironmentCredential và Workload Identity

Kiểm tra tên các biến môi trường, không in secret:

```bash
env | cut -d= -f1 | grep -E '^(AZURE_TENANT_ID|AZURE_CLIENT_ID|AZURE_CLIENT_SECRET|AZURE_CLIENT_CERTIFICATE_PATH|AZURE_FEDERATED_TOKEN_FILE)$'
```

Trên Windows PowerShell:

```powershell
Get-ChildItem Env: | Where-Object { $_.Name -in @('AZURE_TENANT_ID','AZURE_CLIENT_ID','AZURE_CLIENT_SECRET','AZURE_CLIENT_CERTIFICATE_PATH','AZURE_FEDERATED_TOKEN_FILE') } | Select-Object -ExpandProperty Name
```

Các biến này có thể cấu hình service principal hoặc workload identity. Nếu chạy trên Azure VM/App Service/Container Apps với managed identity, hãy kiểm tra không có biến môi trường service principal cũ khiến chain dừng trước managed identity.

Với AKS Workload Identity, kiểm tra `AZURE_TENANT_ID`, `AZURE_CLIENT_ID` và `AZURE_FEDERATED_TOKEN_FILE` có trỏ đúng tenant, application/user-assigned identity và projected token file của pod không. Kiểm tra federated identity credential trên Entra application/managed identity có subject và audience khớp Kubernetes ServiceAccount.

### 4.4. Chọn đúng managed identity

Azure có system-assigned và user-assigned managed identity:

- **System-assigned:** vòng đời gắn với resource Azure; khi xóa resource, identity cũng bị xóa.
- **User-assigned:** là resource riêng, có thể gắn vào nhiều Azure resource; ứng dụng thường chọn bằng Client ID.

Nếu VM hoặc App Service có nhiều user-assigned identities, chỉ bật managed identity chung có thể chưa đủ để xác định identity cần dùng. Có thể cấu hình client ID rõ ràng.

Ví dụ Java chọn user-assigned managed identity:

```java
import com.azure.core.credential.TokenCredential;
import com.azure.identity.ManagedIdentityCredentialBuilder;

String managedIdentityClientId = System.getenv("AZURE_CLIENT_ID");

TokenCredential credential = new ManagedIdentityCredentialBuilder()
        .clientId(managedIdentityClientId)
        .build();
```

Đây là credential tường minh. Nếu dùng Spring Cloud Azure, các property toàn cục tương ứng có thể là:

```yaml
spring:
  cloud:
    azure:
      credential:
        managed-identity-enabled: true
        client-id: USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID
      profile:
        tenant-id: AZURE_TENANT_ID
        subscription-id: AZURE_SUBSCRIPTION_ID
```

`client-id` có ý nghĩa theo kiểu credential được chọn; trong cấu hình managed identity, nó dùng để chọn user-assigned identity. `tenant-id` chọn tenant cho các luồng xác thực có tenant. `subscription-id` đặt subscription context cho các integration cần Azure Resource Manager. Chúng không phải một giá trị có thể thay thế lẫn nhau.

### 4.5. Bật log để xem credential chain đã chọn gì

Trong môi trường local hoặc staging, bật log cho Azure Identity:

```yaml
logging:
  level:
    com.azure.identity: DEBUG
```

Log có thể cho biết EnvironmentCredential, WorkloadIdentityCredential, ManagedIdentityCredential hoặc AzureCliCredential đã thử và credential nào lấy được token. Không bật log body/headers nhạy cảm ở production; không ghi access token ra log.

Ở phiên bản `azure-identity` hỗ trợ, có thể dùng `AZURE_TOKEN_CREDENTIALS` để giới hạn nhóm credential hoặc chỉ định credential cụ thể. Các giá trị và version tối thiểu được nêu trong tài liệu Azure Identity Java. Không đặt biến này theo ví dụ của phiên bản khác mà chưa kiểm tra dependency đang chạy.

### 4.6. Tenant, subscription và data-plane RBAC

Một access token có issuer/tenant và principal cụ thể. Azure subscription là phạm vi quản lý tài nguyên. Ví dụ:

- Azure Resource Manager có thể cần subscription ID để tìm hoặc quản lý resource.
- Blob Storage cần quyền data-plane như Storage Blob Data Reader/Contributor trên account/container.
- Service Bus cần role data-plane phù hợp như Azure Service Bus Data Sender/Receiver.
- Key Vault cần quyền data-plane phù hợp với mô hình access policy hoặc Azure RBAC.

Có subscription Contributor không đồng nghĩa tự động có quyền đọc nội dung blob hoặc gửi message qua Service Bus. Nếu token lấy được nhưng API trả 403, kiểm tra tenant, principal object ID, role assignment scope và loại role control-plane/data-plane.

## 5. Google Cloud: phân biệt gcloud CLI, ADC và project

### 5.1. ADC tìm credentials theo thứ tự

Google Cloud Client Libraries sử dụng Application Default Credentials (ADC). Thứ tự tìm credentials hiện hành là:

1. Biến môi trường `GOOGLE_APPLICATION_CREDENTIALS`.
2. File ADC được tạo bởi `gcloud auth application-default login`.
3. Service account gắn với runtime, được lấy qua metadata server.

Nếu `GOOGLE_APPLICATION_CREDENTIALS` trỏ tới file JSON cũ, ADC sẽ dùng file đó trước cả local ADC file và attached service account. Điều này thường làm Cloud Run/GCE/GKE chạy dưới identity khác với service account dự kiến.

`GOOGLE_APPLICATION_CREDENTIALS` có thể trỏ tới credential configuration của Workload Identity Federation/Workforce Identity Federation hoặc service account key. Không nên dùng service account key dài hạn nếu workload identity hoặc attached service account đáp ứng được yêu cầu.

### 5.2. gcloud CLI account không phải ADC identity

Các lệnh sau kiểm tra danh tính mà Google Cloud CLI đang dùng:

```bash
gcloud auth list
gcloud config list
gcloud config get-value account
```

Chọn account CLI đã được xác thực:

```bash
gcloud config set account developer@example.com
```

Nhưng Google Cloud Client Libraries dùng ADC. ADC được thiết lập riêng:

```bash
gcloud auth application-default login
```

Hai bộ credentials này độc lập. `gcloud auth list` có thể hiển thị user A đang active trong CLI trong khi Java application dùng ADC của user B hoặc service account impersonation.

Nếu muốn local Java chạy bằng service account impersonation, có thể tạo ADC bằng:

```bash
gcloud auth application-default login --impersonate-service-account=orders-runtime@provider-integration-prod.iam.gserviceaccount.com
```

Người đăng nhập cần quyền impersonate service account tương ứng. ADC này vẫn khác active account của gcloud CLI.

### 5.3. Project mặc định không đổi principal

Kiểm tra project đang dùng trong cấu hình gcloud:

```bash
gcloud config get-value project
gcloud config list
```

Đổi project mặc định của gcloud CLI:

```bash
gcloud config set project provider-integration-prod
```

Trong Spring Framework on Google Cloud, project mặc định có thể được đặt bằng:

```yaml
spring:
  cloud:
    gcp:
      project-id: provider-integration-prod
```

Hoặc qua biến môi trường:

```bash
export GOOGLE_CLOUD_PROJECT="provider-integration-prod"
```

`gcloud config set project` thay project mặc định của gcloud CLI; nó không tự sửa `spring.cloud.gcp.project-id`, resource name đầy đủ hoặc principal của ADC. Một service account ở project A vẫn có thể truy cập bucket thuộc project B nếu IAM policy cho phép.

Khi publish Pub/Sub, resource name đầy đủ giúp chỉ rõ project sở hữu topic:

```text
projects/messaging-prod/topics/orders-created
```

Nếu topic nằm trong project khác với project mặc định, kiểm tra cả tên topic lẫn IAM binding trên topic. Đừng sửa credentials chỉ vì request đang gửi tới project khác.

### 5.4. Xác minh runtime service account

Trên Cloud Run, Compute Engine hoặc GKE, xác định service account gắn với workload:

- Cloud Run: kiểm tra service account của revision đang phục vụ traffic.
- Compute Engine: kiểm tra service account gắn với VM và access scopes nếu còn áp dụng.
- GKE: kiểm tra Kubernetes ServiceAccount, Workload Identity Federation for GKE và binding tới Google service account nếu dùng impersonation.
- Workload bên ngoài Google Cloud: kiểm tra `GOOGLE_APPLICATION_CREDENTIALS` có trỏ tới external account credential configuration đúng pool/provider hay không.

Để xác định principal thực sự gọi API, kiểm tra Cloud Audit Logs của resource/service tương ứng. Các trường `principalEmail` hoặc `principalSubject` giúp đối chiếu danh tính đã thực hiện request. Không log access token để cố xác định principal.

## 6. Cấu hình Spring Boot khi một ứng dụng dùng nhiều cloud provider

Một ứng dụng có thể có một client AWS, một client Azure và một client Google Cloud. Mỗi client cần một credential source và resource context riêng. Không truyền credential object của provider này sang SDK provider khác.

Ví dụ khai báo cấu hình theo môi trường:

```yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
    azure:
      credential:
        managed-identity-enabled: false
        client-id: USER_ASSIGNED_MANAGED_IDENTITY_CLIENT_ID
      profile:
        tenant-id: AZURE_TENANT_ID
        subscription-id: AZURE_SUBSCRIPTION_ID
    gcp:
      project-id: provider-integration-dev

app:
  cloud:
    azure:
      blob-endpoint: https://ordersarchive.blob.core.windows.net
    aws:
      bucket: orders-archive
    gcp:
      bucket: orders-archive
```

Các property trên chọn region, tenant, subscription, project và endpoint. Chúng không chứa credentials bí mật. Identity vẫn đến từ AWS provider chain, Azure credential chain và Google ADC.

Nếu cần tạo client riêng, dùng bean name/qualifier rõ ràng:

```java
@Configuration
public class CloudClientConfiguration {

    @Bean("ordersS3Client")
    S3Client ordersS3Client() {
        return S3Client.builder()
                .region(Region.AP_SOUTHEAST_1)
                .credentialsProvider(DefaultCredentialsProvider.create())
                .build();
    }

    @Bean("ordersBlobClient")
    BlobServiceClient ordersBlobClient() {
        TokenCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint("https://ordersarchive.blob.core.windows.net")
                .credential(credential)
                .buildClient();
    }

    @Bean("ordersGcsClient")
    Storage ordersGcsClient() throws IOException {
        return StorageOptions.newBuilder()
                .setProjectId("provider-integration-dev")
                .build()
                .getService();
    }
}
```

Đây là ví dụ khi ứng dụng tự quản lý client. Nếu starter đã tạo client mặc định, không khai báo bean trùng kiểu một cách vô tình; dùng `@Qualifier` để inject đúng client. Client Google Cloud trong ví dụ dùng ADC; client Azure dùng DefaultAzureCredential; client AWS dùng DefaultCredentialsProvider.

Ví dụ inject client cụ thể:

```java
@Service
public class CloudArchiveService {

    private final S3Client s3Client;
    private final BlobServiceClient blobServiceClient;
    private final Storage storage;

    public CloudArchiveService(
            @Qualifier("ordersS3Client") S3Client s3Client,
            @Qualifier("ordersBlobClient") BlobServiceClient blobServiceClient,
            @Qualifier("ordersGcsClient") Storage storage) {
        this.s3Client = s3Client;
        this.blobServiceClient = blobServiceClient;
        this.storage = storage;
    }
}
```

Trong production, ưu tiên AWS task/instance role hoặc web identity, Azure managed/workload identity và Google attached service account/WIF. Không đưa static key, client secret hoặc service account JSON vào image hay source control chỉ để làm cho ba client dùng chung một cấu hình.

## 7. Phân biệt authentication, authorization và resource context

| Giai đoạn | Câu hỏi | Dấu hiệu lỗi |
| --- | --- | --- |
| Credential discovery | SDK có tìm được credentials không? | AWS Unable to load credentials; Azure CredentialUnavailableException; Google không tìm thấy credentials |
| Authentication | Identity provider có cấp token/credentials không? | Invalid client secret, expired token, tenant mismatch, STS assume-role failure |
| Identity selection | Principal nào thực sự được chọn? | STS ARN, Entra principal hoặc Audit Log khác kỳ vọng |
| Resource context | Request nhắm đúng account/project/subscription/region không? | Resource not found, wrong region, wrong project, subscription/resource ID mismatch |
| Authorization | Principal có quyền trên resource không? | AccessDenied, AuthorizationPermissionMismatch, PERMISSION_DENIED, HTTP 403 |
| Network/endpoint | Client có tới đúng endpoint không? | DNS, TLS, timeout, private endpoint hoặc proxy failure |

Một số tình huống:

- AWS GetCallerIdentity trả đúng role nhưng S3 AccessDenied: kiểm tra IAM/resource policy, KMS, SCP và bucket account.
- Azure DefaultAzureCredential lấy token thành công nhưng Blob trả 403: kiểm tra tenant/principal và Storage Blob Data role trên đúng account/container.
- Google ADC lấy credentials thành công nhưng Pub/Sub trả PERMISSION_DENIED: kiểm tra principal và Publisher role trên topic đúng project.
- Tài nguyên không tìm thấy: kiểm tra account/project/region/resource name trước khi thay đổi IAM.
- Không tìm thấy credentials: kiểm tra chain, biến môi trường và metadata endpoint trước khi sửa role trên resource.

## 8. Bảng troubleshooting theo triệu chứng

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra và sửa |
| --- | --- | --- |
| AWS dùng IAM user thay vì EC2/ECS role | System property hoặc environment credentials được ưu tiên | Kiểm tra aws.accessKeyId, AWS_ACCESS_KEY_ID; bỏ nguồn static cũ nếu không cần |
| AWS dùng nhầm account khi chạy local | Profile mặc định hoặc AWS_PROFILE không đúng; environment credentials ghi đè profile | Chạy aws configure list và aws sts get-caller-identity với profile dự kiến |
| AWS SDK báo không tìm thấy credentials | Không có profile, web identity, container credentials hoặc instance role hợp lệ | Đọc toàn bộ provider chain error; kiểm tra IMDS/ECS endpoint và role attachment |
| AWS assume role bị từ chối | Trust policy, source identity hoặc external ID sai | Kiểm tra role ARN, trust relationship, source credentials và sts:AssumeRole |
| AWS gọi sai region | AWS_REGION, profile region hoặc cấu hình client override | Kiểm tra aws configure list và region truyền vào builder |
| Azure lấy token từ Azure CLI user thay vì managed identity | Environment/workload identity không match hoặc managed identity unavailable; chain tiếp tục tới CLI | Bật com.azure.identity DEBUG và xác định credential trả token |
| Azure dùng nhầm service principal | AZURE_CLIENT_ID/TENANT_ID/CLIENT_SECRET cũ vẫn tồn tại | Kiểm tra biến môi trường; xóa cấu hình không còn dùng và xác minh lại chain |
| Azure không tìm thấy subscription | CLI đăng nhập nhầm tenant hoặc user chưa được cấp subscription | Chạy az account show, az account list, đăng nhập tenant đúng rồi chọn subscription |
| Azure lấy token đúng nhưng Blob/Service Bus 403 | Thiếu data-plane RBAC hoặc role được cấp ở scope khác | Kiểm tra principal object ID, role assignment và scope resource |
| Azure dùng nhầm user-assigned identity | Có nhiều managed identity nhưng client ID không được chỉ định | Đặt client ID của identity cần dùng trong credential builder/property |
| Google dùng user cũ trên local | GOOGLE_APPLICATION_CREDENTIALS hoặc ADC file cũ được ưu tiên | Kiểm tra env var, thiết lập lại ADC và xác minh principal qua audit log |
| Google dùng service account key thay vì attached identity | Env var trỏ tới JSON key | Bỏ key file khỏi runtime và dùng attached service account/WIF |
| Google CLI đúng account nhưng Java sai account | gcloud CLI credentials khác ADC | Chạy gcloud auth application-default login cho local ADC; kiểm tra ADC source riêng |
| Google gọi nhầm project | spring.cloud.gcp.project-id, GOOGLE_CLOUD_PROJECT hoặc resource name sai | Kiểm tra project mặc định và full resource name |
| Google project đúng nhưng 403 | Principal thiếu role trên resource hoặc project khác | Kiểm tra Audit Logs và IAM policy trên bucket/topic/secret |
| Nhiều cloud client dùng chung một bean credentials | Cấu hình chung hoặc bean override không đúng | Tạo credential/client bean riêng, đặt qualifier theo provider |
| Local chạy nhưng deployed runtime sai identity | Máy local có CLI credentials hoặc env khác runtime | Kiểm tra ngay trong container/pod/service runtime và audit log |
| Sau rotate credentials ứng dụng vẫn dùng identity cũ | Client hoặc process giữ provider/configuration cũ; env chưa cập nhật | Xác nhận credential refresh behavior, restart/rollout theo cách nền tảng yêu cầu |

## 9. Bài thực hành: xác minh ba identity trước khi gọi dịch vụ

Mục tiêu: Orders API ghi object vào AWS S3, Azure Blob Storage và Google Cloud Storage. Mỗi provider dùng identity riêng; mỗi resource có thể thuộc account/project khác với nơi triển khai ứng dụng.

### Bước 1 — Ghi lại danh tính dự kiến

| Provider | Danh tính runtime | Resource context |
| --- | --- | --- |
| AWS | IAM role orders-runtime | Account 123456789012, bucket orders-archive, region ap-southeast-1 |
| Azure | User-assigned managed identity orders-runtime | Tenant TENANT_ID, subscription SUBSCRIPTION_ID, Storage Account ordersarchive |
| Google Cloud | Service account orders-runtime@provider-integration-prod.iam.gserviceaccount.com | Project archive-prod, bucket orders-archive |

Các giá trị là ví dụ. Thay bằng account ID, tenant, subscription, project, region và resource thực tế.

### Bước 2 — Xác minh AWS caller

```bash
aws configure list
aws sts get-caller-identity
```

Xác nhận Account và Arn chứa account/role mong muốn. Nếu không đúng, kiểm tra Java system properties, environment variables, web identity, profile và container/instance metadata theo đúng thứ tự chain.

### Bước 3 — Xác minh Azure tenant và subscription

```bash
az account show --query "{tenantId:tenantId, subscriptionId:id, user:user.name}" --output json
az account list --all --output table
```

Chọn subscription phục vụ resource management nếu cần:

```bash
az account set --subscription SUBSCRIPTION_ID
```

Sau đó bật log Azure Identity trong ứng dụng staging để xác nhận credential source thực sự cấp token. Kiểm tra Client ID của user-assigned managed identity và role data-plane trên Storage Account.

### Bước 4 — Xác minh Google ADC và project

```bash
gcloud auth list
gcloud config list
gcloud config get-value project
```

Các lệnh này xác minh gcloud CLI. Nếu Java dùng ADC local, xác nhận riêng bằng:

```bash
gcloud auth application-default login
```

Nếu triển khai trên Google Cloud, kiểm tra service account gắn với runtime và `GOOGLE_APPLICATION_CREDENTIALS` không ghi đè nguồn metadata dự kiến. Đối chiếu principal thực tế trong Cloud Audit Logs sau request test.

### Bước 5 — Kiểm tra resource và permission

- AWS: ghi object thử vào đúng bucket; xác nhận bucket policy và IAM role cho phép thao tác.
- Azure: ghi blob thử vào đúng container; xác nhận role Storage Blob Data Contributor hoặc quyền hẹp hơn phù hợp.
- Google Cloud: ghi object thử vào đúng bucket; xác nhận role Storage Object Creator trên bucket.

Không dùng quyền Owner/Administrator để thử. Dùng đúng runtime identity và quyền tối thiểu dự kiến của ứng dụng.

### Bước 6 — Ghi nhận kết quả

Với mỗi request, lưu lại:

- Provider và client bean name.
- Principal/account/tenant/project được xác minh.
- Resource identifier đầy đủ.
- Kết quả API và request/correlation ID.
- IAM/RBAC scope đã kiểm tra.

Không lưu access token, secret key, client secret hoặc nội dung credential file vào log hay báo cáo.

## 10. Nguyên tắc vận hành để tránh chọn nhầm danh tính

- Tách identity theo workload và môi trường; không dùng một tài khoản admin cho mọi dịch vụ.
- Tránh static credentials trong environment nếu nền tảng đã cung cấp role, managed identity, workload identity hoặc attached service account.
- Dùng explicit profile/credential khi cần chẩn đoán local; production nên có một nguồn identity rõ ràng.
- Loại bỏ biến môi trường credential cũ khỏi IDE, shell, container image, CI variables và service definition.
- Đặt region, tenant, subscription, project và resource name bằng cấu hình riêng; không suy ra chúng từ email hoặc ARN của principal.
- Nếu ứng dụng dùng nhiều cloud provider, tạo client/credential bean riêng và inject bằng `@Qualifier`.
- Bật credential-chain logging trong local/staging khi cần; không ghi token hoặc secret.
- Kiểm tra identity thực tế bằng STS, Azure Identity diagnostics và Google Cloud Audit Logs.
- Sau khi đổi role, managed identity, WIF binding hoặc ADC, xác nhận lại principal và quyền bằng request test.
- Cấp quyền tại resource scope nhỏ nhất; phân biệt control-plane với data-plane permission.

## 11. Ghi nhớ

- Identity và resource context là hai cấu hình khác nhau: AWS role khác region; Azure principal khác tenant/subscription; Google service account khác project.
- AWS SDK for Java 2.x thử system properties, environment, web identity, profile, ECS và EC2 metadata theo thứ tự. Biến static có thể shadow task/instance role.
- `aws sts get-caller-identity` cho biết account và ARN thực tế; `aws configure list` giúp tìm nguồn region/profile/credentials.
- Azure `DefaultAzureCredential` thử Environment, Workload Identity, Managed Identity và các developer credentials theo chain. Chain dừng khi lấy được token, kể cả token thuộc tài khoản không có quyền trên resource.
- `az account set` đổi subscription mặc định của CLI; nó không đổi principal của một Java credential đã tạo tường minh.
- Spring Cloud Azure có property riêng cho tenant, subscription, client ID và managed identity; chọn đúng tenant/principal rồi kiểm tra data-plane RBAC.
- Google ADC ưu tiên `GOOGLE_APPLICATION_CREDENTIALS`, sau đó local ADC file, cuối cùng attached service account. Env var trỏ file cũ có thể shadow identity runtime.
- `gcloud auth list` và `gcloud config set project` quản lý gcloud CLI; Java Cloud Client Libraries dùng ADC. Hai bộ credentials không đồng nhất.
- `spring.cloud.gcp.project-id` hoặc `GOOGLE_CLOUD_PROJECT` chọn project context; resource name đầy đủ có thể chỉ project khác; không thay đổi principal.
- Khi xác thực thành công nhưng API trả 403, kiểm tra IAM/RBAC trên resource. Khi principal sai, sửa credential chain trước khi thay quyền.

## Tài liệu tham khảo chính thức

1. [AWS SDK for Java 2.x — Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
2. [AWS STS — GetCallerIdentity](https://docs.aws.amazon.com/cli/latest/reference/sts/get-caller-identity.html)
3. [AWS CLI — configure list và nguồn cấu hình](https://docs.aws.amazon.com/cli/latest/reference/configure/list.html)
4. [Azure Identity Java — Credential chains và DefaultAzureCredential](https://learn.microsoft.com/en-us/azure/developer/java/sdk/authentication/credential-chains)
5. [Azure CLI — đăng nhập và chọn subscription](https://learn.microsoft.com/en-us/cli/azure/authenticate-azure-cli-interactively)
6. [Azure CLI — quản lý subscription](https://learn.microsoft.com/en-us/cli/azure/manage-azure-subscriptions-azure-cli)
7. [Spring Cloud Azure — Global configuration properties](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configuration-properties-global)
8. [Google Cloud — How Application Default Credentials works](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
9. [Google Cloud CLI — Authenticate for the gcloud CLI](https://docs.cloud.google.com/sdk/docs/authenticate)
10. [Google Cloud CLI — gcloud auth list](https://docs.cloud.google.com/sdk/gcloud/reference/auth/list)
11. [Spring Framework on Google Cloud — Core configuration](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/core.html)

Thứ tự credential chain và property phụ thuộc phiên bản SDK/provider. Khi xử lý ứng dụng thực tế, đối chiếu dependency version đang chạy với tài liệu tương ứng; đặc biệt kiểm tra biến môi trường và profile trong đúng tiến trình Java thay vì chỉ kiểm tra terminal tương tác.
