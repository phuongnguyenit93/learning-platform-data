# Tích hợp Object Storage Service qua SDK hoặc starter còn phù hợp

## 1. Bài toán và mục tiêu

Một ứng dụng Spring Boot quản lý đơn hàng cần lưu hóa đơn PDF, ảnh sản phẩm và tệp đính kèm của khách hàng. Ứng dụng phải upload/download object, giữ bucket ở chế độ private, giới hạn quyền truy cập theo workload, và cung cấp đường tải file cho người dùng mà không để lộ AccessKey.

Alibaba Cloud **Object Storage Service (OSS)** cung cấp bucket để lưu object. Ứng dụng Java có thể tích hợp OSS qua ba cách:

- **OSS Java SDK**: gọi API sản phẩm trực tiếp; ứng dụng tự tạo client, cấu hình credentials, region, endpoint và lifecycle.
- **Aliyun OSS Spring Boot Starter**: auto-configuration cho một số thao tác phổ biến trong Spring Boot; phù hợp khi version starter và API nó bọc tương thích với ứng dụng.
- **Presigned URL**: backend dùng SDK tạo URL có chữ ký và thời hạn; browser/mobile truyền file trực tiếp tới OSS mà không cần giữ credentials cloud.

Bài học thuộc chương **Alibaba Cloud** trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Module thực hành tích hợp Spring Boot với các dịch vụ managed của AWS, Azure, Google Cloud và Alibaba Cloud qua thư viện tương ứng; người học cần cấu hình danh tính/quyền, truy cập storage, messaging, dữ liệu, bảo vệ secret, kiểm thử tích hợp và đánh giá khác biệt giữa provider.

Sau bài này, bạn có thể:

1. Chọn SDK V1, SDK V2 hoặc starter theo trạng thái bảo trì và compatibility.
2. Cấu hình OSS client với region, endpoint và Signature Version 4.
3. Tích hợp RAM role/STS credentials vào Spring Boot và tự refresh credential.
4. Upload/download object, xử lý metadata và quản lý client lifecycle.
5. Chọn simple upload, multipart/resumable upload hoặc presigned URL.
6. Giới hạn RAM permission, bảo vệ bucket/object và tránh ghi đè dữ liệu.
7. Kiểm thử adapter OSS và chẩn đoán lỗi AccessDenied, SignatureDoesNotMatch, endpoint, timeout.

## 2. Chọn SDK hay Spring Boot Starter?

### 2.1. Ba lựa chọn và phạm vi sử dụng

| Lựa chọn | Đặc điểm | Khi phù hợp |
| --- | --- | --- |
| **OSS Java SDK V1** (artifact **aliyun-sdk-oss**) | API Java trưởng thành, nhiều ví dụ upload/download, multipart, resumable, metadata, presigned URL; cần tự cấu hình client | Ứng dụng production cần API đã được sử dụng lâu, hoặc đang nâng cấp từ tích hợp V1 |
| **OSS Java SDK V2** (artifact **alibabacloud-oss-v2**) | API được thiết kế lại, builder và request model mới, sync/async client; tài liệu OSS hiện đánh dấu SDK 2.0 là **preview** | Dự án có thể đánh giá preview, muốn thử API mới và có integration test/đường nâng cấp |
| **Aliyun OSS Spring Boot Starter** (artifact **aliyun-oss-spring-boot-starter**) | Auto-configuration theo Spring Boot; artifact hiện công bố version **1.0.0**, kéo OSS Java SDK V1 | Ứng dụng hiện hữu đã dùng starter và đã xác minh tương thích với Spring Boot đang chạy |

Tại thời điểm kiểm tra **24/11/2026**:

- Tài liệu OSS Java SDK V1 được cập nhật trong năm 2026 và hướng dẫn dependency **com.aliyun.oss:aliyun-sdk-oss:3.18.4**.
- OSS Java SDK V1 hỗ trợ Signature V4; tài liệu khuyến nghị V4 vì Signature V1 đang được loại bỏ dần.
- Tài liệu OSS Java SDK V2 vẫn gắn nhãn **preview**; Maven Central có version **0.6.1** phát hành ngày 20/10/2026.
- **aliyun-oss-spring-boot-starter** trên Maven Central là **1.0.0**; POM của starter phụ thuộc **aliyun-sdk-oss**. README dự án chỉ ghi Spring Boot 2 trở lên, không đưa ra ma trận chi tiết chứng minh tương thích Boot 3.x/4.x.

Vì vậy, bài dùng **OSS Java SDK V1 + Signature V4** để minh họa một tích hợp có tài liệu API đầy đủ. SDK V2 được giới thiệu để người học biết tình trạng preview và cách đánh giá trước khi dùng. Starter là lựa chọn có điều kiện cho ứng dụng hiện hữu; không thêm nó vào dự án mới chỉ vì tên có chữ Spring Boot.

### 2.2. Dependency coordinates

**OSS Java SDK V1:**

~~~xml
<dependency>
    <groupId>com.aliyun.oss</groupId>
    <artifactId>aliyun-sdk-oss</artifactId>
    <version>3.18.4</version>
</dependency>
~~~

Từ SDK V1 **3.17.4 trở lên** có thể dùng Signature V4 theo tài liệu nâng cấp chữ ký. Ví dụ trong bài dùng 3.18.4. Khi tạo dự án thật, kiểm tra bản mới nhất, Java baseline và dependency tree trước khi pin version.

**OSS Java SDK V2:**

~~~xml
<dependency>
    <groupId>com.aliyun</groupId>
    <artifactId>alibabacloud-oss-v2</artifactId>
    <version>0.6.1</version>
</dependency>
~~~

SDK V2 có package khác SDK V1, ví dụ **com.aliyun.sdk.service.oss2**. Không trộn OSSClient của V2 với com.aliyun.oss.OSS của V1 trong cùng một đoạn cấu hình.

**Aliyun OSS Spring Boot Starter:**

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.alibaba.cloud</groupId>
            <artifactId>aliyun-spring-boot-dependencies</artifactId>
            <version>1.0.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.alibaba.cloud</groupId>
        <artifactId>aliyun-oss-spring-boot-starter</artifactId>
    </dependency>
</dependencies>
~~~

BOM **aliyun-spring-boot-dependencies** là BOM của dự án **aliyun-spring-boot**, không phải BOM **spring-cloud-alibaba-dependencies**. POM starter OSS 1.0.0 kéo **com.aliyun.oss:aliyun-sdk-oss**. Trước khi dùng, kiểm tra effective POM, dependency tree, auto-configuration và sample của đúng starter version. Không mặc định các property hoặc bean name của starter giống với property tự định nghĩa trong bài.

### 2.3. Cây quyết định chọn tích hợp

~~~mermaid
flowchart TD
    A{"Dự án đã dùng Aliyun OSS Starter?"}
    A -->|"Có"| B{"Starter 1.0.0 đã qua test với Boot/JDK hiện tại?"}
    B -->|"Có"| C["Giữ starter và kiểm soát SDK transitive"]
    B -->|"Không"| D["Thay bằng SDK trực tiếp sau khi kiểm thử"]
    A -->|"Không"| E{"Có chấp nhận SDK V2 preview?"}
    E -->|"Có"| F["Đánh giá OSS Java SDK V2 trong staging"]
    E -->|"Không"| G["OSS Java SDK V1 + Signature V4"]
    C --> H["Tách adapter và kiểm thử OSS"]
    D --> H
    F --> H
    G --> H
~~~

Nếu ứng dụng chỉ cần upload/download object, SDK trực tiếp thường đủ. Starter có giá trị khi nó thật sự giảm cấu hình và được duy trì cho Spring Boot version đang dùng. Không để starter cũ khóa khả năng nâng cấp nền tảng.

## 3. Chuẩn bị bucket, region và quyền

### 3.1. Tạo bucket và xác định thông số

Trước khi viết code:

1. Kích hoạt OSS và tạo bucket trong region đã chọn.
2. Ghi lại **bucket name**, **region ID** và endpoint phù hợp.
3. Giữ ACL bucket/object ở **private** trừ khi có yêu cầu public rõ ràng.
4. Tạo RAM role hoặc RAM user dành riêng cho workload.
5. Cấp quyền chỉ trên bucket/prefix ứng dụng cần truy cập.
6. Chọn endpoint public hoặc internal/VPC dựa trên vị trí workload.

Ví dụ cấu hình:

~~~yaml
aliyun:
  oss:
    region: ${ALIYUN_OSS_REGION}
    endpoint: ${ALIYUN_OSS_ENDPOINT}
    bucket: ${ALIYUN_OSS_BUCKET}
    key-prefix: invoices/
~~~

- **region** là region nơi bucket được tạo, ví dụ **ap-southeast-1**.
- **endpoint** là endpoint OSS tương ứng region và network path. Workload trong cùng region/VPC có thể dùng internal endpoint khi sản phẩm hỗ trợ.
- **bucket** là tên bucket, không phải object key.
- **key-prefix** là tiền tố do ứng dụng quản lý để tách loại object.

SDK V2 có thể suy ra public endpoint từ region; nếu dùng internal endpoint, acceleration endpoint hoặc custom domain, cấu hình theo tài liệu SDK. Với SDK V1, cấu hình endpoint tường minh và region của bucket khi dùng Signature V4.

**Lưu ý cho bucket ở Chinese mainland:** chính sách OSS áp dụng từ 20/03/2025 yêu cầu người dùng OSS mới dùng custom domain/CNAME cho data API operations ở các region mainland bị ảnh hưởng; nếu dùng HTTPS phải gắn SSL certificate hợp lệ. Kiểm tra chính sách và danh sách thao tác áp dụng trong tài liệu OSS trước khi dùng default public endpoint.

### 3.2. Quyền RAM tối thiểu

Các action thường gặp:

| Nghiệp vụ | RAM action |
| --- | --- |
| Upload object | **oss:PutObject** |
| Download object | **oss:GetObject** |
| Xóa object | **oss:DeleteObject** |
| List object trong bucket | **oss:ListObjects** hoặc action list tương ứng API/phiên bản |
| Multipart upload | **oss:PutObject** và quyền liên quan theo thao tác |
| Ghi object tag | **oss:PutObjectTagging** |
| Mã hóa phía server bằng KMS | Thêm quyền KMS cần thiết, ví dụ **kms:GenerateDataKey** và/hoặc **kms:Decrypt** theo cấu hình |

Không cấp **AliyunOSSFullAccess** hoặc quyền toàn account nếu ứng dụng chỉ cần upload/download trong một prefix. Policy nên giới hạn resource theo bucket và object prefix; nếu ứng dụng không cần xóa hoặc list, không cấp các action đó.

**Trust policy** của role xác định workload nào được assume role; permission policy xác định role được phép thao tác OSS. Hai chính sách giải quyết hai câu hỏi khác nhau. Với ECS dùng instance RAM role; với ACK cân nhắc RRSA/OIDC cho từng ServiceAccount; với môi trường ngoài Alibaba Cloud dùng federation hoặc AssumeRole phù hợp.

## 4. Tích hợp OSS Java SDK V1 với Spring Boot

### 4.1. Thêm dependency

Ví dụ Maven cho Spring Boot 3 và OSS Java SDK V1:

~~~xml
<properties>
    <aliyun.oss.version>3.18.4</aliyun.oss.version>
    <aliyun.credentials.version>1.0.8</aliyun.credentials.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.aliyun.oss</groupId>
        <artifactId>aliyun-sdk-oss</artifactId>
        <version>3.18.4</version>
    </dependency>
    <dependency>
        <groupId>com.aliyun</groupId>
        <artifactId>credentials-java</artifactId>
        <version>1.0.8</version>
    </dependency>
</dependencies>
~~~

**credentials-java** hỗ trợ RAM role, ECS RAM role, OIDC role và credential provider chain. Hãy kiểm tra compatibility của version credentials library với OSS SDK và các dependency Java hiện tại. Không thêm version vào nhiều module khác nhau; quản lý tập trung bằng Maven property hoặc version catalog.

### 4.2. Cấu hình OSS client và Signature V4

Client nên được tạo một lần trong Spring context và tái sử dụng. Không tạo mới OSSClient cho mỗi request vì client quản lý HTTP connection pool.

Ví dụ bean:

~~~java
package demo.storage.config;

import com.aliyun.oss.ClientBuilderConfiguration;
import com.aliyun.oss.OSS;
import com.aliyun.oss.OSSClientBuilder;
import com.aliyun.oss.common.auth.CredentialsProvider;
import com.aliyun.oss.common.comm.SignVersion;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OssClientConfiguration {

    @Bean(destroyMethod = "shutdown")
    public OSS ossClient(
            CredentialsProvider ossCredentialsProvider,
            @Value("${aliyun.oss.endpoint}") String endpoint,
            @Value("${aliyun.oss.region}") String region) {

        ClientBuilderConfiguration clientConfig =
                new ClientBuilderConfiguration();

        // Dùng Signature V4 và khai báo region của bucket.
        clientConfig.setSignatureVersion(SignVersion.V4);

        return OSSClientBuilder.create()
                .endpoint(endpoint)
                .credentialsProvider(ossCredentialsProvider)
                .clientConfiguration(clientConfig)
                .region(region)
                .build();
    }
}
~~~

**destroyMethod = shutdown** giải phóng connection khi Spring context dừng. Giữ HTTPS và CRC data check mặc định để bảo vệ dữ liệu truyền tải và kiểm tra tính toàn vẹn. Không tắt CRC chỉ để tăng tốc khi chưa đánh giá rủi ro.

### 4.3. Credentials cho local development

Trong máy phát triển, có thể dùng environment variables cho RAM user test có quyền tối thiểu:

~~~powershell
$env:OSS_ACCESS_KEY_ID = "<RAM_USER_ACCESS_KEY_ID>"
$env:OSS_ACCESS_KEY_SECRET = "<RAM_USER_ACCESS_KEY_SECRET>"
~~~

Bean provider cho môi trường local (profile `local`):

~~~java
import com.aliyun.oss.common.auth.CredentialsProvider;
import com.aliyun.oss.common.auth.CredentialsProviderFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("local")
public class OssCredentialsConfiguration {

    @Bean
    public CredentialsProvider ossCredentialsProvider() {
        return CredentialsProviderFactory
                .newEnvironmentVariableCredentialsProvider();
    }
}
~~~

Không đưa AccessKey vào application.yml, source code, Docker image, log hoặc file được commit. Không dùng AccessKey của root account. Nếu dùng STS tĩnh, phải cập nhật token trước khi hết hạn; không để một token ngắn hạn cố định trong ứng dụng chạy lâu.

### 4.4. Credentials tự refresh bằng ECS RAM role

Khi Spring Boot chạy trên ECS/ECI, gắn instance RAM role có quyền OSS tối thiểu. Credentials tool có thể lấy STS credentials từ metadata và tự refresh. Đây là cấu hình thay thế cho local provider, dùng profile `ecs`:

~~~java
package demo.storage.config;

import com.aliyun.credentials.Client;
import com.aliyun.credentials.models.Config;
import com.aliyun.credentials.models.CredentialModel;
import com.aliyun.oss.common.auth.Credentials;
import com.aliyun.oss.common.auth.CredentialsProvider;
import com.aliyun.oss.common.auth.DefaultCredentials;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration
@Profile("ecs")
public class OssRoleCredentialsConfiguration {

    @Bean
    public Client ecsCredentialsClient() throws Exception {
        Config config = new Config();
        config.setType("ecs_ram_role");
        String roleName = System.getenv("ALIBABA_CLOUD_ECS_METADATA");
        if (roleName != null && !roleName.isEmpty()) {
            config.setRoleName(roleName);
        }
        config.setDisableIMDSv1(true);
        return new Client(config);
    }

    @Bean
    public CredentialsProvider ossCredentialsProvider(
            Client ecsCredentialsClient) {
        return new CredentialsProvider() {
            @Override
            public void setCredentials(Credentials credentials) {
                // Provider lấy credential mới từ Credentials tool.
            }

            @Override
            public Credentials getCredentials() {
                CredentialModel credential =
                        ecsCredentialsClient.getCredential();

                return new DefaultCredentials(
                        credential.getAccessKeyId(),
                        credential.getAccessKeySecret(),
                        credential.getSecurityToken());
            }
        };
    }
}
~~~

Đặt **ALIBABA_CLOUD_ECS_METADATA** bằng tên instance RAM role đã gắn cho ECS. **setDisableIMDSv1(true)** yêu cầu metadata ở chế độ bảo mật; nếu IMDSv2 không khả dụng, ứng dụng phải báo lỗi thay vì âm thầm fallback. Cấu hình này yêu cầu ECS instance thực sự được gắn role và metadata endpoint có thể truy cập từ workload.

Với ACK, thay provider bằng **oidc_role_arn**, khai báo role ARN, OIDC provider ARN và token file theo RRSA. Credentials tool lấy STS token và tự refresh. Với cross-account, dùng **ram_role_arn** và đảm bảo cả caller permission **sts:AssumeRole** lẫn trust policy của role đích đều cho phép.

## 5. Upload và download object

### 5.1. Object key và dữ liệu

OSS lưu dữ liệu theo **bucket + object key**. Object key có thể có prefix dạng thư mục, ví dụ **invoices/2026/11/order-1001.pdf**, nhưng đây là một tên object đầy đủ chứ không phải thư mục vật lý.

Không dùng nguyên filename do người dùng gửi lên làm object key. Backend nên sinh key không đoán được, kiểm tra quyền sở hữu và giới hạn loại/kích thước file trước khi upload. Object key không bao gồm tên bucket.

### 5.2. Tạo service upload

Ví dụ dùng Spring MultipartFile:

~~~java
package demo.storage;

import com.aliyun.oss.OSS;
import com.aliyun.oss.model.CannedAccessControlList;
import com.aliyun.oss.model.ObjectMetadata;
import com.aliyun.oss.model.PutObjectRequest;
import com.aliyun.oss.model.PutObjectResult;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;
import java.io.InputStream;

@Service
public class OssStorageService {

    private final OSS ossClient;
    private final String bucketName;

    public OssStorageService(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucketName) {
        this.ossClient = ossClient;
        this.bucketName = bucketName;
    }

    public String uploadInvoice(String objectKey, MultipartFile file)
            throws IOException {

        ObjectMetadata metadata = new ObjectMetadata();
        metadata.setContentLength(file.getSize());
        if (file.getContentType() != null) {
            metadata.setContentType(file.getContentType());
        }
        metadata.setObjectAcl(CannedAccessControlList.Private);

        PutObjectRequest request;
        try (InputStream input = file.getInputStream()) {
            request = new PutObjectRequest(bucketName, objectKey, input);
            request.setMetadata(metadata);

            PutObjectResult result = ossClient.putObject(request);
            return result.getETag();
        }
    }
}
~~~

Đoạn code đặt object ở chế độ private và trả về ETag để lưu cùng bản ghi nghiệp vụ. Content-Type do client gửi lên không phải bằng chứng đáng tin cậy về loại file; production cần kiểm tra nội dung file, kích thước, phần mở rộng, quyền upload và quy tắc đặt object key.

Không tự động tạo URL public từ bucket/object. Với object private, backend có thể tải nội dung qua SDK hoặc cấp presigned URL có thời hạn.

### 5.3. Download object theo stream

Không cần tải toàn bộ file vào byte[] khi file lớn. Có thể stream từ OSS sang HTTP response:

~~~java
import com.aliyun.oss.OSS;
import com.aliyun.oss.model.OSSObject;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.util.StreamUtils;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;

@Service
public class OssDownloadService {
    private final OSS ossClient;
    private final String bucketName;

    public OssDownloadService(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucketName) {
        this.ossClient = ossClient;
        this.bucketName = bucketName;
    }

    public void download(String objectKey, OutputStream responseBody)
            throws IOException {
        OSSObject object = ossClient.getObject(bucketName, objectKey);
        try (InputStream input = object.getObjectContent()) {
            StreamUtils.copy(input, responseBody);
        }
    }
}
~~~

Trước khi download, kiểm tra người dùng có quyền xem object nghiệp vụ đó. Không cho client truyền bucket name tùy ý; backend cần xác định bucket và object key từ dữ liệu đã được xác thực.

### 5.4. Xử lý metadata và ghi đè object

Một object có thể lưu metadata như Content-Type, Content-Disposition, cache control, storage class, server-side encryption và tags. Cấu hình metadata ngay khi upload nếu biết trước.

Nếu upload cùng key đã tồn tại, thao tác PutObject thông thường sẽ ghi đè nội dung. Các lựa chọn:

- Sinh object key duy nhất cho mỗi lần upload.
- Bật versioning nếu nghiệp vụ cần giữ lịch sử object.
- Dùng header **x-oss-forbid-overwrite** theo API hỗ trợ để ngăn ghi đè.
- Lưu ETag, version ID và object key trong database để đối chiếu.

Không dùng ETag như checksum SHA-256 trong mọi trường hợp; multipart upload và cách mã hóa có thể làm ý nghĩa ETag khác với hash nội dung đơn giản.

## 6. Upload file lớn, multipart và resumable upload

### 6.1. Chọn phương thức upload

| Phương thức | Mục đích | Ghi chú |
| --- | --- | --- |
| **Simple upload** | File nhỏ/vừa, một request | OSS Java SDK V1 hỗ trợ object đơn đến 5 GB |
| **Multipart upload** | Chia object thành nhiều part, có thể upload song song | Cần initiate, upload part, complete; có thể abort khi thất bại |
| **Resumable upload** | File lớn hoặc mạng không ổn định | Lưu checkpoint và tiếp tục từ phần đã hoàn tất |
| **Browser form upload** | Browser upload trực tiếp theo HTML form | Khác với presigned PUT URL |
| **Presigned PUT URL** | Client upload trực tiếp qua HTTP PUT | Backend cấp quyền tạm thời cho một object key |

OSS Java SDK V1 hỗ trợ multipart/resumable upload cho object lớn; tài liệu mô tả giới hạn multipart lên tới **48.8 TB**. Không dùng simple upload cho file lớn nếu cần khả năng phục hồi hoặc giới hạn request timeout.

### 6.2. Vòng đời multipart upload

~~~mermaid
flowchart TD
    A["InitiateMultipartUpload"] --> B["Nhận uploadId"]
    B --> C["Chia file thành part"]
    C --> D["UploadPart song song hoặc tuần tự"]
    D --> E{"Đủ part và ETag?"}
    E -->|"Có"| F["CompleteMultipartUpload"]
    E -->|"Không / lỗi"| G["AbortMultipartUpload"]
    F --> H["Object hoàn chỉnh"]
~~~

Mỗi part có số thứ tự và ETag. Khi hoàn tất, gửi danh sách part ETag hợp lệ cho CompleteMultipartUpload. Nếu quá trình thất bại, abort upload để giải phóng part chưa hoàn tất; có thể cấu hình lifecycle rule để dọn multipart upload bị bỏ quên.

Chỉ tăng concurrency khi đã đo băng thông, memory, connection pool và quota. Upload nhiều part song song có thể làm tăng throughput nhưng cũng làm tăng số kết nối và bộ nhớ đệm.

## 7. Cấp quyền tải lên/tải xuống bằng presigned URL

### 7.1. Vì sao dùng presigned URL?

Nếu mọi byte của file đều đi qua Spring Boot, backend trở thành điểm trung chuyển và có thể tiêu tốn băng thông, CPU, memory và connection. Một luồng khác:

1. Client yêu cầu backend upload file.
2. Backend xác thực user, kiểm tra nghiệp vụ và tạo object key.
3. Backend dùng OSS SDK tạo presigned URL cho PUT hoặc GET.
4. Client truyền file trực tiếp tới OSS bằng URL và HTTP method được cấp.
5. Client báo hoàn tất; backend kiểm tra object metadata/size và cập nhật trạng thái nghiệp vụ.

URL có chữ ký cho phép truy cập tạm thời vào một object theo method được ký. Người nhận URL không cần giữ AccessKey của Alibaba Cloud.

### 7.2. Ví dụ tạo URL tải xuống

~~~java
import com.aliyun.oss.OSS;
import com.aliyun.oss.HttpMethod;
import com.aliyun.oss.model.GeneratePresignedUrlRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.net.URL;
import java.util.Date;

@Service
public class OssPresignedUrlService {
    private final OSS ossClient;
    private final String bucketName;

    public OssPresignedUrlService(
            OSS ossClient,
            @Value("${aliyun.oss.bucket}") String bucketName) {
        this.ossClient = ossClient;
        this.bucketName = bucketName;
    }

    public URL createDownloadUrl(String objectKey) {
        Date expiresAt = new Date(System.currentTimeMillis() + 10 * 60 * 1000);

        GeneratePresignedUrlRequest request =
                new GeneratePresignedUrlRequest(bucketName, objectKey);
        request.setMethod(HttpMethod.GET);
        request.setExpiration(expiresAt);

        return ossClient.generatePresignedUrl(request);
    }
}
~~~

Ví dụ URL hết hạn sau 10 phút. Với Signature V4, thời hạn tối đa của presigned URL là 7 ngày; nếu credential nguồn là STS, URL không thể dùng sau khi credential hết hạn. Trong production nên dùng thời hạn ngắn theo nhu cầu, không dùng mặc định nhiều ngày cho file nhạy cảm.

### 7.3. Ví dụ tạo URL upload

Với PUT URL, backend phải quyết định object key và quyền upload. Nếu URL còn hiệu lực, nó có thể được sử dụng nhiều lần; thao tác tiếp theo trên cùng key có thể ghi đè object. Vì vậy:

- Sinh key ngẫu nhiên, gắn với user và phiên upload.
- Đặt TTL ngắn.
- Ràng buộc HTTP method và headers nếu có thể.
- Sau upload, backend kiểm tra object tồn tại, kích thước, metadata và trạng thái scan.
- Không chấp nhận object key hoặc bucket tùy ý do client gửi.
- Không dùng presigned URL làm cơ chế xác thực nghiệp vụ; nó chỉ cấp quyền tạm thời tới object.

Nếu upload trực tiếp từ browser, cấu hình CORS cho đúng origin, method và header cần thiết. Tránh wildcard origin/method nếu không có lý do.

## 8. Bảo mật object storage

### 8.1. Bucket private và dữ liệu nhạy cảm

- Giữ bucket và object private theo mặc định.
- Chỉ cấp **oss:GetObject** cho workload cần đọc; không cấp public-read để thuận tiện.
- Dùng presigned URL có TTL ngắn khi chia sẻ file tạm thời.
- Kiểm tra loại file, dung lượng, malware scanning và quyền sở hữu trước khi xử lý.
- Không dùng tên file do client gửi làm key trực tiếp.
- Cân nhắc mã hóa phía server bằng KMS, versioning và lifecycle theo yêu cầu lưu trữ.
- Không log presigned URL đầy đủ vì URL chứa chữ ký có thể được sử dụng như bearer credential cho tới khi hết hạn.

### 8.2. Quyền theo workload

| Workload | Quyền nên có |
| --- | --- |
| Invoice uploader | **oss:PutObject** trong prefix hóa đơn |
| Invoice reader | **oss:GetObject** trong prefix hóa đơn |
| Cleanup worker | **oss:ListObjects** và **oss:DeleteObject** trong prefix cần dọn |
| API cấp presigned URL GET | **oss:GetObject** trên object được phép chia sẻ |
| API cấp presigned URL PUT | **oss:PutObject** trên key đã được backend tạo |

Không cấp quyền xóa cho uploader nếu không cần. Nếu một service chỉ ghi file, nó không cần list toàn bucket. Dùng RAM role/STS để giảm thời gian sống của credentials và tránh lưu AccessKey dài hạn trong container.

### 8.3. Server-side encryption và lifecycle

Nếu bật SSE-KMS, workload cần quyền KMS tương ứng ngoài quyền OSS. Khi dùng encryption, kiểm tra key policy, region và quyền gọi KMS. Lifecycle rule có thể chuyển storage class hoặc xóa object hết hạn; thiết lập lifecycle phải phù hợp với yêu cầu lưu trữ hóa đơn, chứng từ và retention pháp lý.

## 9. Chẩn đoán lỗi và retry

### 9.1. Phân biệt lỗi client và lỗi server

OSS Java SDK V1 thường phân biệt:

- **ClientException**: lỗi ở client/network, ví dụ DNS, timeout, TLS hoặc không gửi được request.
- **OSSException**: request đã tới OSS nhưng server từ chối; có error code, message và request ID.

Các lỗi thường gặp:

| Lỗi | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| **AccessDenied** | RAM role/user thiếu action hoặc resource permission | Kiểm tra principal, policy và bucket/object prefix |
| **SignatureDoesNotMatch** | AccessKey/STS sai, thiếu token, endpoint/region/signature không khớp hoặc clock skew | Kiểm tra credential provider, region, endpoint và Signature V4 |
| **NoSuchBucket** | Bucket name sai hoặc bucket không tồn tại ở region đó | Xác nhận bucket và region |
| **NoSuchKey** | Object key sai hoặc object chưa tồn tại | Kiểm tra key được lưu trong DB |
| **InvalidAccessKeyId** | AccessKey sai, bị disable hoặc provider chọn nhầm nguồn | Kiểm tra credential source và trạng thái RAM user |
| **RequestTimeTooSkewed** | Đồng hồ máy lệch | Đồng bộ NTP/time service |
| **InvalidEndpoint** hoặc lỗi DNS | Endpoint sai sản phẩm/region hoặc network path không thông | Tra endpoint chính thức, DNS và route |
| **ClientException timeout** | Kết nối chậm, VPC route/firewall hoặc timeout quá thấp | Kiểm tra network, timeout và connection pool |
| **InvalidDigest** | Dữ liệu part không khớp checksum | Kiểm tra stream, part ETag và CRC/MD5 |

Khi bắt OSSException, ghi errorCode, requestId và thông tin operation. Khi bắt ClientException, ghi message và loại network error. Không log AccessKey, SecurityToken hoặc presigned URL.

### 9.2. Retry đúng loại lỗi

- Retry có giới hạn với timeout, lỗi mạng tạm thời và một số lỗi 5xx.
- Dùng exponential backoff và jitter để tránh nhiều worker retry đồng thời.
- Không retry liên tục AccessDenied, SignatureDoesNotMatch, NoSuchBucket hoặc NoSuchKey nếu chưa sửa cấu hình/dữ liệu.
- Với upload cùng key, timeout không luôn chứng minh object chưa được tạo; kiểm tra HeadObject/metadata hoặc dùng object key có idempotency.
- Với multipart, lưu upload ID và part state; abort upload khi nghiệp vụ hủy hoặc hết thời hạn.

SDK có retry mặc định. Không chồng nhiều tầng retry không giới hạn (HTTP client + SDK + application worker) vì có thể tạo request lặp và kéo dài thời gian lỗi.

## 10. Kiểm thử tích hợp OSS

### 10.1. Kiểm thử theo lớp

| Loại test | Mục tiêu | Cách thực hiện |
| --- | --- | --- |
| Unit test domain | Logic đặt tên object, quyền truy cập và metadata | Mock interface ObjectStorage |
| Unit test adapter | Ánh xạ request, bucket, key, metadata | Mock OSS client qua wrapper hoặc kiểm tra request |
| Spring context test | Bean OSS và credentials provider được tạo | Dùng test profile và properties giả |
| Integration test | Upload/download trên OSS test bucket | RAM role/user giới hạn, bucket riêng |
| Permission test | Role chỉ có quyền được cấp | Thử upload/download/delete theo ma trận quyền |
| Presigned URL test | URL GET/PUT hoạt động trong TTL | Kiểm tra method, expiry, object key |
| Failure test | Endpoint sai, token hết hạn, timeout | Xác minh phân loại exception và retry |

Không dùng unit test để chứng minh RAM policy hoạt động trên cloud. Integration test cần bucket riêng, object key có prefix test và dữ liệu không nhạy cảm.

### 10.2. Bài kiểm thử tối thiểu

1. Upload một file nhỏ và lưu ETag/object key vào DB.
2. Download file theo stream và so sánh nội dung.
3. Tạo presigned URL GET có TTL 10 phút, kiểm tra truy cập trước/sau khi hết hạn.
4. Cấp role chỉ có oss:PutObject, xác minh GET bị từ chối.
5. Thử bucket sai region và endpoint sai để đọc error code.
6. Upload file lớn qua multipart/resumable, sau đó mô phỏng network failure.
7. Xác nhận object private không truy cập được khi không có credentials hoặc presigned URL.
8. Kiểm tra log không chứa AccessKey, STS token hoặc URL có chữ ký.

## 11. Starter OSS: khi nào giữ và khi nào thay?

### 11.1. Dùng starter cho ứng dụng hiện hữu

Nếu ứng dụng Spring Boot cũ đã dùng **aliyun-oss-spring-boot-starter**:

1. Xác nhận artifact và BOM version trong effective POM.
2. Xác định starter tạo bean nào, property nào và SDK OSS V1 version nào.
3. Kiểm tra auto-configuration có thể nhận RAM role/STS provider cần thiết không.
4. Chạy context test, upload/download integration test và permission test.
5. Giữ starter nếu nó tương thích, được kiểm thử và giảm đáng kể mã cấu hình.

Không thêm starter đồng thời với SDK V1 theo cách tạo hai OSS client hoặc hai bộ property trùng lặp. Nếu cần dùng API mới mà starter chưa expose, có thể tạo adapter/client riêng sau khi kiểm tra xung đột dependency.

### 11.2. Khi nào chuyển sang SDK trực tiếp?

Cân nhắc chuyển sang SDK trực tiếp khi:

- Starter không công bố compatibility rõ ràng cho Spring Boot/JDK đang dùng.
- Starter kéo SDK cũ hoặc thiếu Signature V4.
- Cần RAM role/STS/OIDC provider mà starter không hỗ trợ tốt.
- Cần multipart, resumable, presigned URL, metadata hoặc API mới.
- Muốn kiểm soát client lifecycle, timeout, retry và version SDK.
- Cần nâng Boot 3/4 nhưng starter chỉ có bằng chứng kiểm thử ở Boot 2.

Khi thay starter, tạo interface nội bộ **ObjectStorage**, viết adapter dùng SDK, chạy integration test rồi chuyển dần call site. Không thay toàn bộ module cùng lúc nếu chưa có baseline test.

### 11.3. Đánh giá OSS Java SDK V2

OSS Java SDK V2 có API khác V1 và đang được tài liệu chính thức đánh dấu **preview**. Dependency hiện có trên Maven Central là **com.aliyun:alibabacloud-oss-v2:0.6.1** tại thời điểm kiểm tra. SDK V2 hỗ trợ Java 8+ theo tài liệu và cung cấp sync/async client, retry và nhiều thao tác object.

Nếu chọn V2:

- Đọc release notes và giới hạn preview của đúng version.
- Kiểm tra API cần dùng đã có sample và behavior ổn định.
- Tạo adapter tách SDK khỏi domain.
- Kiểm thử upload/download, endpoint, credentials, multipart, retry và close lifecycle.
- Pin version, kiểm tra CVE/transitive dependencies và có đường rollback về adapter V1.

Không coi version 0.6.1 là một cam kết GA. Quyết định dùng preview phải được chấp nhận theo chính sách release của dự án.

## 12. Bài tập thực hành

**Bài tập:** xây dựng InvoiceStorageAdapter trong Spring Boot để lưu và tải hóa đơn PDF từ OSS.

1. Tạo bucket private ở region test và xác định endpoint phù hợp.
2. Tạo RAM role cho ứng dụng chỉ có **oss:PutObject** và **oss:GetObject** trong prefix **invoices/**.
3. Cấu hình OSS Java SDK V1 với Signature V4 và RAM role/STS credential provider.
4. Tạo bean OSS singleton, đóng client khi Spring context dừng.
5. Viết ObjectStorage interface và adapter triển khai bằng OSS SDK.
6. Upload PDF, đặt Content-Type và ACL private, lưu ETag/object key vào database.
7. Viết download stream và endpoint tạo presigned URL GET TTL ngắn.
8. Kiểm thử quyền bị từ chối, endpoint sai, token hết hạn và network timeout.
9. Thử multipart/resumable upload cho file lớn.
10. So sánh SDK V1, SDK V2 preview và starter 1.0.0 theo API, compatibility, credentials và khả năng nâng cấp.

**Câu hỏi ôn tập:**

1. Khi nào nên dùng OSS Java SDK trực tiếp thay vì Aliyun OSS Starter?
2. Vì sao starter 1.0.0 cần được kiểm tra riêng khi ứng dụng nâng lên Spring Boot 3/4?
3. Signature V4 cần region của bucket vì sao?
4. Vì sao OSS client nên là singleton Spring bean?
5. RAM role khác AccessKey tĩnh ở credential lifecycle như thế nào?
6. Khi nào dùng simple upload, multipart/resumable upload và presigned URL?
7. Vì sao object key nên do backend sinh thay vì lấy nguyên filename từ client?
8. Presigned URL là bearer credential có thời hạn; cần giới hạn những gì?
9. OSSException khác ClientException ra sao?
10. Vì sao timeout khi upload không có nghĩa chắc chắn object chưa được tạo?
11. Tại sao không nên đặt bucket/object public chỉ để tải file thuận tiện?
12. Khi nào có thể chấp nhận OSS SDK V2 preview trong dự án?

## 13. Tài liệu tham khảo

- [OSS SDK quick start](https://www.alibabacloud.com/help/en/oss/user-guide/oss-sdk-quick-start): cấu hình region, credentials, upload/download với Java SDK V2.
- [OSS Java SDK V1](https://www.alibabacloud.com/help/en/oss/developer-reference/oss-java-sdk/): dependency, client, credentials provider, Signature V4 và exception handling.
- [OSS Java SDK V2](https://www.alibabacloud.com/help/en/oss/developer-reference/oss-sdk-for-java-2-0/): SDK V2 preview, sync/async client, credentials, endpoint và sample.
- [Alibaba OSS SDK V2 GitHub](https://github.com/aliyun/alibabacloud-oss-java-sdk-v2): source, sample và changelog.
- [Alibaba OSS SDK V1 GitHub](https://github.com/aliyun/aliyun-oss-java-sdk): source và tài liệu OSS Java SDK V1.
- [Aliyun Spring Boot Starters](https://github.com/alibaba/aliyun-spring-boot): BOM, OSS starter và sample.
- [Maven Central — aliyun-oss-spring-boot-starter](https://central.sonatype.com/artifact/com.alibaba.cloud/aliyun-oss-spring-boot-starter): version và POM transitive của starter.
- [Alibaba Cloud Credentials for Java](https://github.com/aliyun/credentials-java): RAM role, ECS role, OIDC, STS và default credential chain.
- [OSS multipart upload for Java](https://www.alibabacloud.com/help/en/oss/developer-reference/java-multipart-upload): initiate, upload part, complete và abort.
- [OSS upload files with Java SDK](https://www.alibabacloud.com/help/en/oss/developer-reference/overview-13/): simple, multipart, resumable và signed URL upload.
- [OSS presigned URL download](https://www.alibabacloud.com/help/en/oss/developer-reference/download-using-a-presigned-url): URL GET, quyền oss:GetObject và giới hạn thời hạn.
- [OSS Signature V1 to V4 migration](https://www.alibabacloud.com/help/en/oss/developer-reference/guidelines-for-upgrading-v1-signatures-to-v4-signatures): lộ trình loại bỏ Signature V1 và cách dùng V4.

**Kết quả mong đợi:** người học tích hợp được OSS vào Spring Boot bằng SDK phù hợp, cấu hình đúng region/endpoint và Signature V4, dùng RAM role/STS thay cho AccessKey hardcode, upload/download object an toàn, cấp presigned URL có thời hạn và lựa chọn starter dựa trên bằng chứng compatibility thực tế.
