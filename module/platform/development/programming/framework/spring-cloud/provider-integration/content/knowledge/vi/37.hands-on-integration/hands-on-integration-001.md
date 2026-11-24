# Kết nối đầu tiên tới một dịch vụ bằng danh tính có quyền tối thiểu

## 1. Mục tiêu của bài thực hành

Một ứng dụng Spring Boot không nên kết nối tới dịch vụ cloud bằng tài khoản quản trị hoặc access key được chép vào file cấu hình. Ứng dụng cần một danh tính runtime riêng, nhận credentials ngắn hạn từ môi trường chạy và chỉ được cấp các quyền cần cho nghiệp vụ.

Trong bài này, bạn xây dựng một endpoint Spring Boot đọc metadata của một object đã biết tên trong object storage. Cùng một hợp đồng nghiệp vụ được triển khai qua ba provider:

- Amazon S3 với Spring Cloud AWS và AWS SDK for Java 2.x.
- Google Cloud Storage với Spring Framework on Google Cloud.
- Azure Blob Storage với Spring Cloud Azure và Azure Identity.

Bạn chọn một provider để chạy lab đầu tiên. Hai adapter còn lại giúp bạn so sánh cách mỗi cloud cấp danh tính, gán quyền và tạo client.

Bài học thuộc chương **Thực hành tổng hợp** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure và Google Cloud qua các thư viện Spring Cloud tương ứng; học cấu hình danh tính và quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa các cloud provider. Bài này xây nền tảng cho những bài tích hợp tiếp theo: ứng dụng có thể xác thực với cloud, truy cập đúng tài nguyên và chứng minh rằng quyền ghi không được cấp ngoài nhu cầu.

Sau khi hoàn thành, bạn có thể:

- Phân biệt authentication và authorization.
- Tạo danh tính runtime riêng cho một workload Spring Boot.
- Dùng credentials provider mặc định hoặc workload identity thay cho key dài hạn.
- Cấp quyền đọc object ở đúng bucket/container và đúng phạm vi.
- Cấu hình Spring Cloud AWS, Spring Framework on Google Cloud hoặc Spring Cloud Azure.
- Dùng một interface nghiệp vụ chung và adapter theo từng provider.
- Kiểm tra request đọc thành công và request ghi bị từ chối.
- Chẩn đoán lỗi credentials, IAM, endpoint, region và resource scope.

> **Phạm vi lab:** Bài dùng thao tác đọc metadata của một object đã biết tên (HEAD/GET properties). Không cần list bucket/container, upload, overwrite hoặc delete. Ví dụ dùng Java 17+ để có record; nếu dự án dùng Java thấp hơn, thay record bằng class thông thường. Hãy chọn BOM tương thích với Spring Boot đang dùng, không sao chép version từ một provider sang provider khác.

## 2. Kiến trúc và hợp đồng nghiệp vụ

Ta dùng một tình huống nhỏ: dịch vụ document API cần biết kích thước, Content-Type và version token của một file trước khi đưa file vào pipeline xử lý.

~~~mermaid
flowchart LR
    CLIENT["Client / curl"] --> API["Spring Boot API"]
    API --> PORT["ObjectMetadataReader"]
    PORT --> AWS["S3 adapter"]
    PORT --> GCP["GCS adapter"]
    PORT --> AZURE["Azure Blob adapter"]
    AWS --> S3["Amazon S3"]
    GCP --> GCS["Google Cloud Storage"]
    AZURE --> BLOB["Azure Blob Storage"]
    ID["Runtime identity"] -. "Temporary credentials / token" .-> AWS
    ID -. "ADC access token" .-> GCP
    ID -. "Microsoft Entra token" .-> AZURE
~~~

Hợp đồng nghiệp vụ không cần biết provider đang dùng:

~~~java
public record ObjectMetadataView(
        String provider,
        String objectKey,
        long sizeBytes,
        String contentType,
        String versionToken) {
}

public interface ObjectMetadataReader {
    ObjectMetadataView readConfiguredObject();
}
~~~

Version token là giá trị do provider trả về: ETag ở S3/Azure hoặc generation ở GCS. Không giả định các token này có cùng format hoặc cùng semantics.

Endpoint kiểm tra:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/storage")
public class StorageMetadataController {

    private final ObjectMetadataReader metadataReader;

    public StorageMetadataController(ObjectMetadataReader metadataReader) {
        this.metadataReader = metadataReader;
    }

    @GetMapping("/sample")
    public ObjectMetadataView sample() {
        return metadataReader.readConfiguredObject();
    }
}
~~~

Endpoint chỉ đọc một object đã cấu hình. Không nhận bucket/container hoặc object key tùy ý từ query parameter. Khi đưa vào sản phẩm thật, hãy xác thực người gọi API và kiểm tra quyền nghiệp vụ trước khi trả metadata.

## 3. Authentication và authorization

Hai bước này giải quyết hai câu hỏi khác nhau:

- **Authentication:** request đến từ danh tính nào? Ví dụ IAM role AWS, service account Google Cloud hoặc managed identity của Azure.
- **Authorization:** danh tính đó được phép làm gì trên tài nguyên nào? Ví dụ đọc object trong một bucket, nhận message từ một queue hoặc truy vấn một bảng.

~~~mermaid
sequenceDiagram
    participant App as Spring Boot
    participant Identity as Identity provider
    participant Policy as IAM / RBAC
    participant Service as Managed service

    App->>Identity: Lấy credential/token
    Identity-->>App: Credential ngắn hạn
    App->>Service: Gửi request có xác thực
    Service->>Policy: Kiểm tra principal, action, resource
    Policy-->>Service: Allow / Deny
    Service-->>App: Metadata hoặc lỗi authorization
~~~

Có ba loại danh tính thường xuất hiện trong một lần triển khai:

1. **Developer identity:** người phát triển chạy ứng dụng trên máy cá nhân.
2. **Deployer/provisioning identity:** tài khoản tạo bucket, cấu hình IAM, tạo service hoặc gán role.
3. **Runtime identity:** danh tính mà process Spring Boot sử dụng khi gọi dịch vụ cloud.

Runtime identity không nên kế thừa toàn bộ quyền của người triển khai. Nếu deployer có quyền tạo bucket, sửa IAM và xóa dữ liệu thì điều đó không có nghĩa ứng dụng đang chạy cũng cần các quyền này.

## 4. Quyền tối thiểu cho thao tác đọc metadata

Lab chỉ cần đọc metadata của một object đã biết tên. Bảng dưới đây cho biết quyền cần thiết và những quyền không cần cấp.

| Provider | Runtime identity | Quyền đọc cần thiết | Quyền không cấp trong lab |
| --- | --- | --- | --- |
| AWS S3 | IAM role của workload | s3:GetObject trên object ARN | s3:PutObject, s3:DeleteObject, s3:ListBucket |
| Google Cloud Storage | Service account/workload identity | storage.objects.get trên bucket | storage.objects.create, storage.objects.update, storage.objects.delete |
| Azure Blob Storage | Managed identity hoặc service principal | Storage Blob Data Reader ở container scope | Storage Blob Data Contributor, Storage Blob Data Owner |

Một số role dựng sẵn còn có quyền phụ:

- AWS s3:GetObject đủ cho HEAD object đã biết key. Không cần s3:ListBucket nếu ứng dụng không liệt kê bucket. Khi object không tồn tại và principal thiếu s3:ListBucket, S3 có thể trả 403 thay vì 404.
- Google roles/storage.objectViewer chứa cả storage.objects.get và storage.objects.list. Nếu muốn loại bỏ quyền list, có thể tạo custom role chỉ chứa storage.objects.get rồi gán ở bucket scope.
- Azure Storage Blob Data Reader cho phép đọc và liệt kê blob. Gán role ở container scope giúp giới hạn phạm vi; nếu cần quyền hẹp hơn, xem xét custom Azure RBAC role và scope phù hợp.

Lưu ý: các permission đọc dữ liệu này không phải permission chỉ đọc metadata. Ví dụ, s3:GetObject cho phép lấy nội dung object; storage.objects.get cho phép đọc object data; Storage Blob Data Reader cũng cho phép đọc nội dung blob. Lab chỉ gọi API HEAD/properties để không tải body, nhưng IAM vẫn cấp quyền đọc dữ liệu. Nếu người dùng API chỉ được xem một số metadata đã chọn, hãy lọc field ở tầng ứng dụng và không trả object name hoặc metadata nhạy cảm.

Không nhầm role quản lý tài nguyên với role truy cập dữ liệu. Ví dụ, Azure Contributor quản lý resource không mặc nhiên cấp quyền đọc blob data; cần data role như Storage Blob Data Reader.

## 5. Chọn dependency và BOM

Các provider có BOM riêng. Trong lab một provider, chỉ cần thêm starter tương ứng. Nếu một ứng dụng thật phải tích hợp nhiều provider cùng lúc, hãy tách adapter thành module hoặc profile phù hợp, kiểm tra dependency convergence và chạy integration test cho từng tổ hợp.

### 5.1. AWS

Spring Cloud AWS 3.x dùng AWS SDK for Java 2.x:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AWS_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>
</dependencies>
~~~

Starter tự cấu hình S3Client, region provider và credentials provider. Dùng BOM tương thích với Spring Boot; không thêm một version AWS SDK riêng nếu không có lý do cụ thể.

### 5.2. Google Cloud

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_GCP_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-storage</artifactId>
    </dependency>
</dependencies>
~~~

Starter tự cấu hình bean Storage dựa trên CredentialsProvider của Spring Framework on Google Cloud. Client library sử dụng Application Default Credentials (ADC) để tìm danh tính phù hợp với môi trường.

### 5.3. Azure

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>YOUR_COMPATIBLE_SPRING_CLOUD_AZURE_VERSION</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
    </dependency>
</dependencies>
~~~

Spring Cloud Azure hỗ trợ tích hợp Blob Storage với Spring Resource abstraction. Trong ví dụ adapter bên dưới, ta dùng BlobServiceClient và DefaultAzureCredential trực tiếp để nhìn rõ điểm kết nối giữa identity và SDK. Có thể dùng starter/resource abstraction thay cho việc tự xây dựng client khi dự án đã chuẩn hóa cách cấu hình Azure.

**Quy tắc chọn version:** kiểm tra bảng tương thích Spring Boot/Spring Cloud của đúng BOM trước khi build. Không đặt cùng một số version cho cả AWS, Google và Azure chỉ vì chúng đều là Spring integration library.

## 6. Chuẩn bị tài nguyên mẫu

Tạo một bucket hoặc container test cho lab và một object có key cố định:

~~~text
bucket/container: training-documents-lab
object key:       incoming/sample.txt
content type:     text/plain
content:          first cloud integration
~~~

Tài nguyên cần được tạo trước bởi người có quyền provisioning. Runtime identity của ứng dụng chỉ đọc object này.

Có thể dùng file text nhỏ để kiểm tra. Không dùng dữ liệu khách hàng hoặc dữ liệu nhạy cảm trong bài thực hành đầu tiên.

Tách các thông tin cấu hình khỏi source code:

~~~yaml
app:
  storage:
    aws:
      bucket: training-documents-lab
      key: incoming/sample.txt
    gcp:
      bucket: training-documents-lab
      key: incoming/sample.txt
    azure:
      endpoint: https://YOUR_STORAGE_ACCOUNT.blob.core.windows.net
      container: training-documents-lab
      blob: incoming/sample.txt
~~~

Các property có thể cùng tồn tại trong file mẫu, nhưng chỉ adapter thuộc profile đang chạy được kích hoạt. Trong môi trường thật, lưu cấu hình môi trường bằng deployment config hoặc secret/config management phù hợp.

## 7. Nhánh A — Amazon S3 với Spring Cloud AWS

### 7.1. Tạo IAM policy chỉ đọc object

Tạo policy dành riêng cho ứng dụng. Resource ARN giới hạn đúng object:

~~~json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ReadOneTrainingObject",
      "Effect": "Allow",
      "Action": [
        "s3:GetObject"
      ],
      "Resource": "arn:aws:s3:::training-documents-lab/incoming/sample.txt"
    }
  ]
}
~~~

Nếu ứng dụng cần đọc mọi object dưới prefix incoming/, đổi resource thành arn:aws:s3:::training-documents-lab/incoming/*. Chỉ thêm s3:ListBucket khi nghiệp vụ thật sự cần liệt kê object; permission đó áp dụng lên bucket ARN, không phải object ARN.

Không thêm s3:PutObject hoặc s3:DeleteObject. Nếu sau này ứng dụng đọc bytes từ object được mã hóa bằng SSE-KMS, cần đánh giá thêm kms:Decrypt trên KMS key và key policy. Lab hiện chỉ gọi HEAD để lấy metadata.

### 7.2. Gắn role cho workload

Tạo IAM role với trust policy phù hợp môi trường chạy, rồi gắn policy đọc object ở trên.

| Môi trường | Cách cung cấp danh tính |
| --- | --- |
| EC2 | Instance profile chứa IAM role |
| ECS | Task role gắn vào task definition |
| EKS | IAM Roles for Service Accounts (IRSA) hoặc cơ chế Pod Identity được tổ chức chọn |
| Local development | AWS IAM Identity Center/SSO profile |

Không gắn quyền vào EC2 instance role dùng chung nếu ứng dụng thực tế chạy trên ECS task hoặc EKS pod có thể nhận role riêng. Task role/IRSA giúp tách quyền giữa workload.

Đăng nhập local bằng SSO:

~~~bash
aws configure sso --profile storage-reader
aws sso login --profile storage-reader
~~~

Chọn profile trong terminal chạy Spring Boot:

~~~bash
export AWS_PROFILE=storage-reader
~~~

PowerShell:

~~~powershell
$env:AWS_PROFILE = "storage-reader"
~~~

AWS SDK dùng default credentials provider chain. Spring Cloud AWS cũng tự cấu hình DefaultCredentialsProvider, có thể lấy credentials từ profile, web identity, ECS task credentials hoặc EC2 instance profile. Không đặt access key/secret key tĩnh trong application.yml.

### 7.3. Cấu hình region

~~~yaml
spring:
  cloud:
    aws:
      region:
        static: ap-southeast-1
~~~

Thay region theo bucket. Nếu đã dùng biến môi trường AWS_REGION hoặc region provider của môi trường, có thể không cần khai báo giá trị cố định trong file.

### 7.4. Viết adapter đọc metadata

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;
import software.amazon.awssdk.services.s3.model.HeadObjectResponse;

@Component
@Profile("aws")
public class S3ObjectMetadataReader implements ObjectMetadataReader {

    private final S3Client s3Client;
    private final String bucket;
    private final String key;

    public S3ObjectMetadataReader(
            S3Client s3Client,
            @Value("${app.storage.aws.bucket}") String bucket,
            @Value("${app.storage.aws.key}") String key) {
        this.s3Client = s3Client;
        this.bucket = bucket;
        this.key = key;
    }

    @Override
    public ObjectMetadataView readConfiguredObject() {
        HeadObjectResponse response = s3Client.headObject(
                HeadObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build());

        return new ObjectMetadataView(
                "aws-s3",
                key,
                response.contentLength(),
                response.contentType(),
                response.eTag());
    }
}
~~~

HeadObject đọc metadata mà không tải body. API này cần quyền s3:GetObject trên object. Không gọi listObjectsV2 chỉ để tìm object đã biết tên.

### 7.5. Kiểm tra danh tính và quyền

Kiểm tra AWS identity từ cùng profile:

~~~bash
aws sts get-caller-identity --profile storage-reader
~~~

Kiểm tra metadata object:

~~~bash
aws s3api head-object \
  --bucket training-documents-lab \
  --key incoming/sample.txt \
  --profile storage-reader
~~~

Nếu lệnh thứ hai trả metadata, danh tính hiện tại có quyền đọc object. Nếu chạy Spring Boot trên EC2/ECS/EKS, SDK sẽ lấy role credentials của workload; kết quả get-caller-identity từ máy developer không chứng minh role production đã được gắn đúng.

## 8. Nhánh B — Google Cloud Storage

### 8.1. Tạo service account riêng

Ví dụ:

~~~bash
gcloud iam service-accounts create spring-storage-reader \
  --project=training-platform-dev \
  --display-name="Spring Storage Reader"
~~~

Danh tính runtime có dạng:

~~~text
spring-storage-reader@training-platform-dev.iam.gserviceaccount.com
~~~

Không cấp Owner, Editor hoặc Storage Admin cho service account này.

### 8.2. Cấp quyền chỉ đọc

Cách đơn giản là gán roles/storage.objectViewer ở bucket scope:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://training-documents-lab \
  --member="serviceAccount:spring-storage-reader@training-platform-dev.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"
~~~

Role này chứa cả storage.objects.get và storage.objects.list. Nếu muốn loại bỏ quyền list, tạo custom role chỉ có storage.objects.get:

~~~bash
gcloud iam roles create gcsObjectReader \
  --project=training-platform-dev \
  --title="GCS Object Reader" \
  --description="Read object data and metadata without listing objects" \
  --permissions=storage.objects.get \
  --stage=GA
~~~

Gán custom role ở bucket:

~~~bash
gcloud storage buckets add-iam-policy-binding \
  gs://training-documents-lab \
  --member="serviceAccount:spring-storage-reader@training-platform-dev.iam.gserviceaccount.com" \
  --role="projects/training-platform-dev/roles/gcsObjectReader"
~~~

Quyền storage.objects.get cho phép đọc object và metadata. Nó không cấp create, update, delete hoặc list. Tạo custom role cần quyền quản trị IAM phù hợp; đó là công việc của provisioning identity.

### 8.3. Local ADC và production service identity

Để chạy local bằng user account đã được cấp quyền đọc bucket:

~~~bash
gcloud auth application-default login
~~~

ADC là cơ chế credential discovery của Google Cloud client libraries. Credentials tạo bằng gcloud auth login cho CLI khác với credentials tạo bằng gcloud auth application-default login cho ứng dụng.

Nếu muốn local test bằng đúng service account, có thể dùng impersonation:

~~~bash
gcloud auth application-default login \
  --impersonate-service-account=spring-storage-reader@training-platform-dev.iam.gserviceaccount.com
~~~

User thực hiện impersonation cần quyền tạo token cho service account. Không tải service account JSON key về máy chỉ để chạy lab.

Khi deploy Cloud Run, gắn service account làm service identity:

~~~bash
gcloud run deploy document-api \
  --image=REGION-docker.pkg.dev/training-platform-dev/apps/document-api:latest \
  --region=asia-southeast1 \
  --service-account=spring-storage-reader@training-platform-dev.iam.gserviceaccount.com
~~~

Trong production trên Google Cloud, ưu tiên service identity gắn với workload và ADC qua metadata server. Không đặt GOOGLE_APPLICATION_CREDENTIALS trỏ tới key JSON trên Cloud Run.

### 8.4. Cấu hình starter và adapter

Starter tự tạo Storage bean:

~~~java
import com.google.cloud.storage.Blob;
import com.google.cloud.storage.BlobId;
import com.google.cloud.storage.Storage;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("gcp")
public class GcsObjectMetadataReader implements ObjectMetadataReader {

    private final Storage storage;
    private final String bucket;
    private final String key;

    public GcsObjectMetadataReader(
            Storage storage,
            @Value("${app.storage.gcp.bucket}") String bucket,
            @Value("${app.storage.gcp.key}") String key) {
        this.storage = storage;
        this.bucket = bucket;
        this.key = key;
    }

    @Override
    public ObjectMetadataView readConfiguredObject() {
        Blob blob = storage.get(BlobId.of(bucket, key));

        if (blob == null) {
            throw new IllegalStateException(
                    "Không tìm thấy object đã cấu hình");
        }

        return new ObjectMetadataView(
                "google-cloud-storage",
                key,
                blob.getSize(),
                blob.getContentType(),
                String.valueOf(blob.getGeneration()));
    }
}
~~~

Cấu hình project nếu starter cần giá trị tường minh:

~~~yaml
spring:
  cloud:
    gcp:
      project-id: training-platform-dev
~~~

Không đưa private key vào spring.cloud.gcp.storage.credentials.encoded-key. Cấu hình credential file/encoded key chỉ dành cho những tình huống cần thiết và phải được quản lý như secret; workload identity/ADC thường là lựa chọn tốt hơn.

### 8.5. Kiểm tra quyền

Kiểm tra identity đang dùng cho gcloud CLI:

~~~bash
gcloud auth list
~~~

Kiểm tra object:

~~~bash
gcloud storage objects describe \
  gs://training-documents-lab/incoming/sample.txt
~~~

Lưu ý: lệnh gcloud sử dụng credential của CLI; ứng dụng Spring dùng ADC. Hai credential có thể là hai principal khác nhau. Hãy xác minh principal runtime qua cấu hình Cloud Run/GKE/VM và audit logs khi cần.

## 9. Nhánh C — Azure Blob Storage

### 9.1. Tạo managed identity

Trên môi trường Azure như App Service, Container Apps hoặc VM, bật system-assigned managed identity hoặc tạo user-assigned managed identity. Managed identity là principal trong Microsoft Entra ID; ứng dụng không phải lưu client secret.

Nếu dùng user-assigned identity, ghi lại principal/object ID và client ID. Nếu dùng system-assigned identity, lấy principal ID sau khi bật identity trên resource.

### 9.2. Gán role ở container scope

Scope của một container có dạng:

~~~text
/subscriptions/SUBSCRIPTION_ID/resourceGroups/RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/STORAGE_ACCOUNT/blobServices/default/containers/training-documents-lab
~~~

Gán role Storage Blob Data Reader cho managed identity:

~~~bash
az role assignment create \
  --assignee-object-id=MANAGED_IDENTITY_PRINCIPAL_ID \
  --assignee-principal-type=ServicePrincipal \
  --role="Storage Blob Data Reader" \
  --scope="/subscriptions/SUBSCRIPTION_ID/resourceGroups/RESOURCE_GROUP/providers/Microsoft.Storage/storageAccounts/STORAGE_ACCOUNT/blobServices/default/containers/training-documents-lab"
~~~

Nếu test local bằng tài khoản developer, đăng nhập Azure CLI và gán role đọc dữ liệu ở container scope cho đúng Microsoft Entra user. Không dùng Storage Blob Data Contributor chỉ để đọc metadata.

Storage Blob Data Reader là built-in role dễ dùng cho lab nhưng bao gồm quyền đọc và list blob. Khi cần quyền hẹp hơn, có thể thiết kế custom role với data action phù hợp và scope phù hợp.

### 9.3. Local và production credentials

Local development:

~~~bash
az login
az account show
~~~

DefaultAzureCredential có thể sử dụng Azure CLI credential khi chạy trên máy developer. Khi deploy lên Azure, credential chain có thể dùng managed identity hoặc workload identity được cấu hình cho workload.

Không dùng storage account key hoặc connection string chứa account key trong application.yml. Ai có account key thường có quyền truy cập rộng trên storage account, vượt xa nhu cầu đọc một container.

### 9.4. Cấu hình BlobServiceClient

~~~java
import com.azure.identity.DefaultAzureCredential;
import com.azure.identity.DefaultAzureCredentialBuilder;
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.BlobServiceClientBuilder;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("azure")
public class AzureBlobConfiguration {

    @Bean
    BlobServiceClient blobServiceClient(
            @Value("${app.storage.azure.endpoint}") String endpoint) {

        DefaultAzureCredential credential =
                new DefaultAzureCredentialBuilder().build();

        return new BlobServiceClientBuilder()
                .endpoint(endpoint)
                .credential(credential)
                .buildClient();
    }
}
~~~

Ví dụ dùng Azure Identity trực tiếp để làm rõ credential. Nếu ứng dụng dùng cấu hình auto-configuration của Spring Cloud Azure, inject client đã được starter cấu hình và tránh tạo thêm một credential chain khác.

### 9.5. Adapter đọc metadata

~~~java
import com.azure.storage.blob.BlobServiceClient;
import com.azure.storage.blob.models.BlobProperties;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("azure")
public class AzureBlobMetadataReader implements ObjectMetadataReader {

    private final BlobServiceClient blobServiceClient;
    private final String container;
    private final String blobName;

    public AzureBlobMetadataReader(
            BlobServiceClient blobServiceClient,
            @Value("${app.storage.azure.container}") String container,
            @Value("${app.storage.azure.blob}") String blobName) {
        this.blobServiceClient = blobServiceClient;
        this.container = container;
        this.blobName = blobName;
    }

    @Override
    public ObjectMetadataView readConfiguredObject() {
        BlobProperties properties = blobServiceClient
                .getBlobContainerClient(container)
                .getBlobClient(blobName)
                .getProperties();

        return new ObjectMetadataView(
                "azure-blob-storage",
                blobName,
                properties.getBlobSize(),
                properties.getContentType(),
                String.valueOf(properties.getETag()));
    }
}
~~~

Cấu hình endpoint và target:

~~~yaml
app:
  storage:
    azure:
      endpoint: https://YOUR_STORAGE_ACCOUNT.blob.core.windows.net
      container: training-documents-lab
      blob: incoming/sample.txt
~~~

### 9.6. Kiểm tra quyền

Nếu local user được gán role ở container scope, có thể kiểm tra bằng Azure CLI:

~~~bash
az storage blob show \
  --account-name STORAGE_ACCOUNT \
  --container-name training-documents-lab \
  --name incoming/sample.txt \
  --auth-mode login
~~~

Nếu ứng dụng chạy bằng managed identity, xác minh identity của resource đang chạy và role assignment ở đúng scope. Không kết luận quyền production chỉ từ một lệnh local dùng user developer.

## 10. Chạy một profile tại một thời điểm

Mỗi adapter được kích hoạt bằng Spring profile. Chạy AWS:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=aws
~~~

Chạy Google Cloud:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=gcp
~~~

Chạy Azure:

~~~bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=azure
~~~

Nếu chạy bằng JAR:

~~~bash
java -jar app.jar --spring.profiles.active=aws
~~~

Không kích hoạt đồng thời ba profile trong lab này vì cả ba adapter cùng triển khai ObjectMetadataReader. Nếu ứng dụng cần truy cập nhiều provider đồng thời, đặt tên bean/qualifier riêng hoặc dùng routing strategy theo cấu hình nghiệp vụ thay vì phụ thuộc vào một bean duy nhất.

Endpoint kiểm tra:

~~~bash
curl http://localhost:8080/api/storage/sample
~~~

Kết quả mẫu:

~~~json
{
  "provider": "google-cloud-storage",
  "objectKey": "incoming/sample.txt",
  "sizeBytes": 25,
  "contentType": "text/plain",
  "versionToken": "1730000000000000"
}
~~~

versionToken và sizeBytes thực tế phụ thuộc object đã tạo. AWS trả ETag, GCS trả generation, Azure trả ETag. Không so sánh các giá trị version token giữa provider như thể chúng là cùng một định danh.

## 11. Chứng minh quyền ghi không được cấp

Một bài lab least-privilege cần kiểm tra cả thao tác được phép và thao tác bị từ chối.

| Kiểm tra | Kỳ vọng |
| --- | --- |
| Đọc metadata object đã cấu hình | Thành công |
| Đọc object khác ngoài resource scope | Bị từ chối |
| Liệt kê bucket/container | Bị từ chối nếu role được thiết kế chỉ đọc một object |
| Upload object mới | Bị từ chối |
| Overwrite object | Bị từ chối |
| Xóa object | Bị từ chối |

Cách kiểm thử đáng tin cậy nhất là chạy một integration test dùng đúng client và runtime identity của ứng dụng:

~~~java
assertDoesNotThrow(() -> metadataReader.readConfiguredObject());

// Dùng một object key riêng trong test để xác nhận quyền ghi bị từ chối.
// Không chạy test ghi trên dữ liệu thật.
assertThrows(Exception.class, () -> storageWriteProbe.tryCreateProbeObject());
~~~

storageWriteProbe là adapter test-only; triển khai tương ứng bằng PutObject, Storage.create hoặc BlobClient.upload. Trong môi trường production, không expose endpoint ghi chỉ để thử permission.

Nếu kiểm tra bằng CLI, bảo đảm CLI đang dùng đúng principal với ứng dụng. Một tài khoản administrator trên máy developer có thể upload thành công dù runtime role của ứng dụng bị giới hạn; kết quả đó không chứng minh cấu hình ứng dụng sai.

## 12. Nguyên tắc bảo mật khi đưa vào ứng dụng thật

### 12.1. Không lưu credentials dài hạn trong source code

Tránh các cấu hình sau:

- AWS access key/secret key commit trong repository.
- Service account JSON key được đóng gói vào container image.
- Azure storage account key hoặc connection string trong application properties.
- Token được copy thủ công vào biến môi trường rồi dùng lâu dài.

Dùng credentials provider của SDK và identity gắn với workload. Credentials tạm thời được refresh theo cơ chế của provider.

### 12.2. Tách quyền provisioning và runtime

Provisioning identity có thể tạo bucket, container, IAM role và role assignment. Runtime identity chỉ được quyền đọc object theo nghiệp vụ. Quyền quản trị không nên được kế thừa tự động vào process Spring Boot.

### 12.3. Thu hẹp resource scope

- AWS: giới hạn object ARN hoặc prefix ARN.
- Google Cloud: gán role ở bucket hoặc managed-folder scope; tránh cấp ở project nếu chỉ cần một bucket.
- Azure: gán data role ở container scope; tránh gán ở subscription hoặc resource group khi không cần.

### 12.4. Không cho client điều khiển resource tùy ý

Nếu endpoint nhận bucket name, container, object key hoặc provider từ client mà không kiểm tra, ứng dụng có thể trở thành confused deputy: người dùng lợi dụng runtime identity của backend để đọc tài nguyên mà họ không được phép.

Với lab, object key được cấu hình cố định. Trong hệ thống thực, map document ID sang bucket/key trong database sau khi kiểm tra tenant ownership và authorization.

### 12.5. Không log dữ liệu xác thực

Log provider, request ID, object ID nội bộ, HTTP status và thời gian xử lý. Không log secret, access token, service account key, account key hoặc nội dung file. Metadata như object name và Content-Type cũng cần tuân theo chính sách dữ liệu của hệ thống.

## 13. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| AWS Unable to load credentials | Không có profile, role hoặc web identity token phù hợp | Kiểm tra AWS_PROFILE, SSO login, task role/instance profile/IRSA |
| AWS AccessDenied khi HeadObject | Thiếu s3:GetObject trên object ARN hoặc bucket policy deny | Kiểm tra identity thực tế, IAM policy, bucket policy và resource ARN |
| AWS object không tồn tại nhưng trả 403 | Principal không có s3:ListBucket nên S3 không tiết lộ object existence | Xác minh object key bằng provisioning identity; không cấp list chỉ để đổi mã lỗi nếu không cần |
| AWS region/redirect error | Region client khác region bucket | Kiểm tra spring.cloud.aws.region.static hoặc region provider |
| GCP DefaultCredentialsProvider không tìm thấy credentials | Chưa thiết lập ADC hoặc runtime chưa gắn service account | Chạy ADC local hoặc cấu hình service identity |
| GCP 403 storage.objects.get | Role gán nhầm service account, sai bucket scope hoặc IAM deny | Kiểm tra principal runtime và IAM policy của bucket |
| GCP dùng nhầm user credential | ADC local khác gcloud CLI credential hoặc khác service identity production | Kiểm tra ADC, impersonation và cấu hình Cloud Run/GKE |
| Azure 403 AuthorizationPermissionMismatch | Thiếu data role hoặc role chỉ cấp ở management plane | Gán Storage Blob Data Reader ở container scope |
| Azure DefaultAzureCredential không xác thực | Credential chain không tìm được Azure CLI/managed/workload identity | Kiểm tra az login, managed identity và environment credential |
| Azure role vừa gán nhưng vẫn 403 | Azure RBAC chưa propagation hoặc gán nhầm principal | Kiểm tra principal/object ID, scope và chờ role assignment có hiệu lực |
| Cả ba provider đều trả 404 | Bucket/container/object key sai hoặc object chưa được tạo | Kiểm tra tên tài nguyên, prefix và phân biệt object key với filesystem path |
| API trả metadata nhưng client không được phép gọi API | Cloud IAM chỉ bảo vệ backend tới storage, không xác thực người dùng của ứng dụng | Thêm Spring Security/API authentication và domain authorization |

Khi chẩn đoán, kiểm tra theo thứ tự: endpoint/region, credential provider, principal thực tế, resource scope, action permission, rồi mới kiểm tra code. Không xử lý lỗi 403 bằng cách cấp quyền Administrator hoặc Owner.

## 14. Kiểm thử tự động và quan sát

### 14.1. Unit test

Mock SDK client và kiểm tra adapter:

- Adapter dùng đúng bucket/container và object key từ cấu hình.
- AWS gọi headObject.
- GCS gọi Storage.get(BlobId).
- Azure gọi BlobClient.getProperties().
- Metadata được ánh xạ về ObjectMetadataView.
- Object không tồn tại được chuyển thành lỗi nghiệp vụ phù hợp.
- Không có phương thức upload/delete trong interface chỉ đọc.

### 14.2. Integration test

Dùng tài nguyên test riêng và danh tính test có đúng role của workload:

1. Tạo object mẫu.
2. Gán quyền read-only ở resource scope.
3. Chạy Spring Boot bằng provider profile.
4. Gọi endpoint metadata và xác minh kết quả.
5. Thử đọc object ngoài phạm vi được cấp.
6. Thử upload/overwrite/delete bằng cùng identity và xác minh bị từ chối.
7. Thu hồi role rồi xác minh request đọc thất bại.
8. Gán lại role và xác minh service hoạt động sau khi IAM propagation hoàn tất.
9. Dọn tài nguyên test bằng provisioning identity.

Không dùng mock để kết luận IAM hoạt động. Chỉ integration test trên cloud thật hoặc môi trường giả lập có mô hình IAM tương ứng mới xác minh được permission boundary.

### 14.3. Quan sát runtime

Ghi nhận:

- Provider/profile đang chạy.
- Tên bucket/container đã được cấu hình (nếu được phép log).
- Object ID nội bộ và version token.
- Request latency và số lần retry.
- HTTP status hoặc exception category.
- Principal/service identity qua audit log của provider.

Không log access token hoặc raw credentials. Khi có sự cố, đối chiếu log ứng dụng với CloudTrail, Cloud Audit Logs hoặc Azure Activity/Storage diagnostic logs để xác định principal và resource bị từ chối.

## 15. So sánh mô hình danh tính giữa ba cloud

| Khía cạnh | AWS | Google Cloud | Azure |
| --- | --- | --- | --- |
| Danh tính workload | IAM role | Service account hoặc federated workload identity | Managed identity hoặc service principal |
| Credential provider | AWS SDK default credentials chain | Application Default Credentials | DefaultAzureCredential |
| Credential runtime | STS temporary credentials | OAuth access token ngắn hạn | Microsoft Entra access token |
| Local development | IAM Identity Center/SSO profile | ADC user credentials hoặc service account impersonation | Azure CLI/Developer credential |
| Kubernetes | EKS IRSA/Pod Identity | GKE Workload Identity Federation | AKS Workload Identity |
| Quyền đọc object | s3:GetObject | storage.objects.get | Storage Blob Data Reader hoặc custom role |
| Resource scope | Object ARN/prefix/bucket | Bucket/managed folder/project | Blob/container/storage account |
| Audit | AWS CloudTrail | Cloud Audit Logs | Azure Activity/Storage diagnostic logs |

Các khái niệm tương đương về mục đích nhưng không giống nhau về API và semantics. Không chuyển nguyên role hoặc policy của provider này sang provider khác. Hãy chuẩn hóa interface nghiệp vụ ở tầng ứng dụng, còn identity, credential chain và IAM policy giữ theo từng provider.

## 16. Bài tập mở rộng

**Bối cảnh:** Dịch vụ document API cần đọc file hóa đơn trong prefix incoming/ và trả metadata để frontend hiển thị trước khi tải file.

### Nhiệm vụ A — Chọn provider

1. Chọn AWS S3, Google Cloud Storage hoặc Azure Blob Storage.
2. Tạo bucket/container test và upload một file incoming/sample.txt.
3. Ghi lại region/location, bucket/container và object key.
4. Tạo runtime identity riêng cho ứng dụng.

### Nhiệm vụ B — Cấp quyền tối thiểu

1. Chỉ cấp quyền đọc object.
2. Giới hạn quyền ở bucket/container hoặc object/prefix cần thiết.
3. Không cấp quyền tạo, ghi đè, xóa hoặc quản trị tài nguyên.
4. Giải thích role dựng sẵn có bao gồm quyền list hay không.
5. Nếu cần, tạo custom role chỉ chứa permission đọc.

### Nhiệm vụ C — Kết nối Spring Boot

1. Thêm provider starter và BOM tương thích.
2. Cấu hình region/endpoint/bucket/object.
3. Dùng credentials provider mặc định của SDK.
4. Viết adapter implement ObjectMetadataReader.
5. Chạy profile tương ứng và gọi /api/storage/sample.
6. Xác minh size, Content-Type và version token.

### Nhiệm vụ D — Kiểm tra security boundary

- Thử đọc object ngoài resource scope.
- Thử upload object mới.
- Thử overwrite object mẫu.
- Thử delete object mẫu.
- Xác minh các thao tác không cần thiết đều bị từ chối.
- Thu hồi quyền đọc và quan sát lỗi.
- Kiểm tra audit log cho principal runtime.

### Nhiệm vụ E — So sánh provider

- Chuyển sang một provider khác mà không đổi controller hoặc interface nghiệp vụ.
- Viết adapter mới và cấu hình identity tương ứng.
- Ghi lại khác biệt về credential chain, role scope, permission và error response.
- Đánh giá cách tổ chức multi-cloud module/profile để tránh dependency và configuration xung đột.

**Tiêu chí đạt:** Ứng dụng đọc được metadata của object bằng workload identity; IAM chỉ cấp quyền đọc ở resource scope phù hợp; không dùng credential dài hạn trong source code; các thao tác ghi/xóa bị từ chối; và adapter provider không làm thay đổi hợp đồng nghiệp vụ.

## 17. Ghi nhớ

- Authentication xác định principal; authorization xác định principal được phép thực hiện action nào trên resource nào.
- Runtime identity phải tách khỏi deployer/provisioning identity.
- AWS dùng IAM role và default credentials provider; Google Cloud dùng service account/workload identity với ADC; Azure dùng managed identity/workload identity với DefaultAzureCredential.
- S3 HeadObject cần s3:GetObject trên object; không cần s3:ListBucket khi đã biết key.
- GCS cần storage.objects.get; roles/storage.objectViewer còn bao gồm list, nên custom role có thể hẹp hơn.
- Azure Storage Blob Data Reader là data role; gán ở container scope và không nhầm với Contributor ở management plane.
- Không đưa AWS keys, service account JSON key, Azure account key hoặc token vào source code.
- Một integration test phải xác minh cả thao tác allow và deny bằng đúng runtime identity.
- Giữ interface nghiệp vụ ổn định, còn SDK, credentials và IAM policy nằm trong adapter theo provider.

### Tài liệu tham khảo

- [Spring Cloud AWS — Getting started, credentials and S3](https://docs.awspring.io/spring-cloud-aws/docs/3.4.2/reference/html/index.html)
- [AWS SDK for Java 2.x — Default credentials provider chain](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/credentials-chain.html)
- [AWS SDK for Java 2.x — IAM role credentials on EC2](https://docs.aws.amazon.com/sdk-for-java/latest/developer-guide/ec2-iam-roles.html)
- [Amazon S3 — HeadObject API permissions](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)
- [AWS IAM — Roles for Amazon ECS tasks](https://docs.aws.amazon.com/AmazonECS/latest/developerguide/security-iam-roles.html)
- [AWS EKS — IAM roles for service accounts](https://docs.aws.amazon.com/eks/latest/userguide/iam-roles-for-service-accounts.html)
- [Spring Framework on Google Cloud — Cloud Storage](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/storage.html)
- [Google Cloud — Application Default Credentials](https://docs.cloud.google.com/docs/authentication/application-default-credentials)
- [Cloud Run — Service identity](https://docs.cloud.google.com/run/docs/securing/service-identity)
- [Cloud Storage — IAM roles and permissions](https://docs.cloud.google.com/storage/docs/access-control/iam)
- [Cloud Storage — Read objects](https://docs.cloud.google.com/storage/docs/reading-objects)
- [Spring Cloud Azure — Authentication](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/authentication)
- [Spring Cloud Azure — Blob Storage starter for Spring Boot](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/configure-spring-boot-starter-java-app-with-azure-storage)
- [Azure Blob Storage — Assign a role for data access](https://learn.microsoft.com/en-us/azure/storage/blobs/assign-azure-role-data-access)
- [Azure Blob Storage — Java quickstart and DefaultAzureCredential](https://learn.microsoft.com/en-us/azure/storage/blobs/storage-java-how-to-use-blob-storage)
