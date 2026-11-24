# Amazon S3-compatible endpoint, path-style access và khác biệt với AWS S3

## Mục tiêu học tập

Trong module **SPRING_CLOUD_PROVIDER_INTEGRATION**, Spring Boot tích hợp các dịch vụ managed của AWS, Azure và Google Cloud để xử lý storage, messaging, dữ liệu, danh tính và quyền. Trong phát triển hoặc triển khai private cloud, ứng dụng cũng có thể cần kết nối một hệ thống object storage hỗ trợ **S3-compatible API**. Tuy nhiên, hỗ trợ một phần API S3 không đồng nghĩa hệ thống đó có endpoint, quyền, chữ ký, tính năng và hành vi giống hoàn toàn Amazon S3.

Bài học tập trung vào ba nội dung:

1. **S3-compatible endpoint:** địa chỉ API của dịch vụ object storage triển khai một phần hoặc phần lớn giao thức S3.
2. **Path-style và virtual-hosted-style addressing:** hai cách đặt bucket trong HTTP URL.
3. **Khác biệt với AWS S3:** khác biệt về SigV4, Region, API, quyền, encryption, versioning, lifecycle, checksum, consistency và presigned URL.

Sau bài này, bạn có thể cấu hình AWS SDK for Java v2/Spring Cloud AWS để trỏ tới endpoint tùy chỉnh, chọn path-style khi provider yêu cầu, kiểm thử upload/download/presigned URL và đánh giá khả năng tương thích trước khi chuyển ứng dụng sang object storage khác.

> **Phạm vi:** Ví dụ sử dụng AWS SDK for Java v2 (package `software.amazon.awssdk`) và Spring Cloud AWS hiện đại (namespace `io.awspring.cloud`). Chọn phiên bản thư viện tương thích với Spring Boot thực tế. Endpoint MinIO/local chỉ là ví dụ phát triển; không sử dụng credentials mặc định trong production.

## 1. S3-compatible có nghĩa là gì?

Amazon S3 cung cấp API object storage để tạo bucket, upload/download object, liệt kê key, xóa, quản lý multipart, metadata và nhiều tính năng khác. Một số hệ thống object storage khác triển khai **một tập API tương thích S3**, cho phép dùng AWS SDK hoặc công cụ S3 để kết nối.

Ví dụ về các hệ thống có thể cung cấp S3-compatible API:

- **MinIO:** object storage thường được triển khai trong local, Kubernetes hoặc hạ tầng riêng.
- **Ceph Object Gateway (RADOS Gateway):** giao diện object storage tương thích S3 trong cụm Ceph.
- **LocalStack:** mô phỏng một số dịch vụ AWS, trong đó có S3, để phát triển và kiểm thử.
- **Các dịch vụ object storage của nhà cung cấp khác:** có thể cung cấp endpoint S3-compatible với phạm vi tính năng và điều kiện riêng.

**S3-compatible không phải chứng nhận mọi API và hành vi AWS S3 đều được hỗ trợ.** Provider có thể hỗ trợ PUT/GET/LIST nhưng không hỗ trợ đầy đủ Object Lock, conditional multipart completion, một số checksum, lifecycle filter, KMS integration hoặc policy condition của AWS.

### 1.1. Vì sao cần endpoint tùy chỉnh?

Nếu không cấu hình endpoint, AWS SDK thường chọn endpoint AWS theo Region. Khi kết nối MinIO hoặc một S3-compatible service, ứng dụng cần chỉ rõ **base endpoint** của dịch vụ.

~~~text
AWS S3:
https://s3.ap-southeast-1.amazonaws.com

MinIO local:
http://localhost:9000

S3-compatible service trong private network:
https://object-storage.internal.example
~~~

Địa chỉ trên là ví dụ. Endpoint thực tế do hạ tầng/provider cung cấp; nó có thể gồm scheme, hostname và port. Không tự ghép bucket hoặc object key vào endpoint cấu hình: SDK sẽ định tuyến bucket/key theo addressing style.

### 1.2. Endpoint, bucket và key là ba thành phần riêng

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| Endpoint | `http://localhost:9000` | Máy chủ API mà client kết nối |
| Bucket | `training-files` | Không gian chứa object |
| Object key | `documents/demo.txt` | Tên định danh object trong bucket |

Endpoint là nơi kết nối; bucket/key là tài nguyên được truy cập. **Không đặt endpoint thành `http://localhost:9000/training-files` rồi lại yêu cầu SDK thêm bucket**, vì có thể lặp path hoặc ký request sai.

## 2. Hai kiểu addressing: virtual-hosted-style và path-style

Khi gửi request S3, bucket có thể nằm trong **hostname** hoặc nằm trong **path** của URL.

### 2.1. Virtual-hosted-style

Bucket được đưa vào hostname:

~~~text
https://training-files.s3.ap-southeast-1.amazonaws.com/documents/demo.txt
        └──── bucket ────┘
~~~

Với custom endpoint, mô hình có thể là:

~~~text
https://training-files.storage.example.com/documents/demo.txt
        └── bucket là subdomain ──┘
~~~

Một số provider cần DNS wildcard hoặc cấu hình routing để subdomain bucket trỏ về cùng dịch vụ.

### 2.2. Path-style

Bucket được đặt ở đầu path sau hostname:

~~~text
https://s3.ap-southeast-1.amazonaws.com/training-files/documents/demo.txt
                                     └bucket─┘└──── object key ────┘
~~~

Với MinIO local:

~~~text
http://localhost:9000/training-files/documents/demo.txt
                    └bucket─┘└──── object key ────┘
~~~

Path-style thường thuận tiện cho local development hoặc endpoint không hỗ trợ bucket subdomain. SDK cần biết bucket phải nằm trong path để tạo request đúng.

### 2.3. So sánh hai kiểu

| Tiêu chí | Virtual-hosted-style | Path-style |
| --- | --- | --- |
| Bucket nằm ở đâu? | Trong hostname | Trong URL path |
| Ví dụ | `https://bucket.storage.example/key` | `https://storage.example/bucket/key` |
| Yêu cầu DNS | Có thể cần wildcard/subdomain cho bucket | Chỉ cần hostname endpoint |
| TLS certificate | Phải hợp lệ với hostname có bucket | Có thể dùng certificate cho endpoint chung |
| Localhost/port | Khó mô phỏng nhiều subdomain nếu không cấu hình DNS | Dễ dùng `localhost:9000/bucket/key` |
| Tương thích provider | Phụ thuộc cách provider định tuyến | Phụ thuộc provider hỗ trợ path-style |
| AWS S3 | Virtual-hosted-style là dạng phổ biến | Path-style là dạng legacy/compatibility; cần kiểm tra hỗ trợ theo endpoint và bucket type |

### 2.4. Bucket có dấu chấm và TLS

Nếu dùng virtual-hosted-style với bucket chứa dấu chấm, ví dụ `my.files.backup`, hostname sẽ có nhiều label:

~~~text
my.files.backup.s3.ap-southeast-1.amazonaws.com
~~~

Certificate wildcard kiểu `*.s3.ap-southeast-1.amazonaws.com` có thể không khớp hostname nhiều cấp theo quy tắc TLS wildcard. Điều này có thể làm HTTPS validation thất bại trong một số cấu hình. Path-style giữ hostname ở endpoint chung và đưa bucket vào path, nên tránh một số vấn đề hostname đó nếu provider hỗ trợ.

**Không tắt certificate validation để chữa lỗi TLS.** Hãy chọn addressing style, bucket naming và certificate đúng với provider.

## 3. Cấu hình AWS SDK for Java v2 và Spring Cloud AWS

### 3.1. Dependency

Với Maven, import BOM Spring Cloud AWS phù hợp phiên bản Spring Boot và thêm S3 starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>io.awspring.cloud</groupId>
            <artifactId>spring-cloud-aws-dependencies</artifactId>
            <version>${spring-cloud-aws.version}</version>
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

`spring-cloud-aws.version` là property cần khai báo theo ma trận tương thích của dự án. Starter hỗ trợ cấu hình client S3 và các thành phần tích hợp Spring. Khi cần endpoint/addressing style đặc thù, cấu hình bean client phù hợp thay vì chỉ đổi bucket name.

### 3.2. Property riêng cho S3-compatible endpoint

Có thể tách endpoint và addressing style theo Spring profile:

~~~yaml
# application-local.yml
spring:
  cloud:
    aws:
      region:
        static: us-east-1

app:
  storage:
    bucket: training-files
    s3:
      endpoint: http://localhost:9000
      path-style: true
~~~

Đây là **property do ứng dụng tự định nghĩa**; `app.storage.s3.endpoint` và `path-style` không phải tên property chuẩn áp dụng cho mọi bản Spring Cloud AWS. `us-east-1` trong local là Region dùng để ký request theo cấu hình emulator, không có nghĩa dữ liệu local nằm trong AWS Region đó.

Production AWS có thể dùng profile riêng không khai báo endpoint, để SDK sử dụng endpoint chuẩn theo Region. Không để cấu hình local vô tình được kích hoạt trong production.

### 3.3. Tạo `S3Client` với `endpointOverride` và `pathStyleAccessEnabled`

AWS SDK v2 cung cấp `S3Configuration.pathStyleAccessEnabled(true)` để chọn path-style addressing. `endpointOverride` chỉ định base endpoint:

~~~java
import java.net.URI;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3Configuration;

@Configuration(proxyBeanMethods = false)
public class CompatibleS3ClientConfiguration {

    @Bean
    public S3Client s3Client(
            @Value("${spring.cloud.aws.region.static}") String region,
            @Value("${app.storage.s3.endpoint}") String endpoint,
            @Value("${app.storage.s3.path-style:true}") boolean pathStyle) {

        return S3Client.builder()
                .region(Region.of(region))
                .endpointOverride(URI.create(endpoint))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .serviceConfiguration(
                        S3Configuration.builder()
                                .pathStyleAccessEnabled(pathStyle)
                                .build())
                .build();
    }
}
~~~

**Giải thích:**

- `endpointOverride` thay endpoint AWS mặc định bằng endpoint đã cấu hình.
- `region` vẫn cần thiết vì AWS SDK dùng Region trong quá trình ký request Signature Version 4; nhiều provider S3-compatible yêu cầu một giá trị Region cụ thể hoặc chấp nhận giá trị mặc định theo tài liệu của họ.
- `pathStyleAccessEnabled(true)` đưa bucket vào URL path. Nếu provider hỗ trợ virtual-hosted-style và DNS phù hợp, có thể cấu hình `false`.
- `DefaultCredentialsProvider` lấy credentials từ AWS SDK provider chain. Với MinIO local, cung cấp access key/secret riêng qua environment/profile; không dùng khóa local trong production.
- Bean này là ví dụ **thay thế/cấu hình client auto-configured**. Trong ứng dụng thực, bảo đảm chỉ có một bean `S3Client` phù hợp hoặc dùng `@Qualifier` rõ ràng nếu cần nhiều endpoint/client.

Nếu starter đã tự cấu hình `S3Client`, khai báo bean tùy chỉnh có thể khiến auto-configuration back off tùy cơ chế/phiên bản. Hãy kiểm tra điều kiện auto-configuration của bản Spring Cloud AWS đang dùng để tránh hai bean cùng tên hoặc inject nhầm client.

### 3.4. Khi nào không cần path-style?

Nếu provider hỗ trợ virtual-hosted-style, có DNS wildcard và certificate hợp lệ, có thể tắt path-style:

~~~java
.serviceConfiguration(
        S3Configuration.builder()
                .pathStyleAccessEnabled(false)
                .build())
~~~

Không chọn path-style chỉ vì URL khác AWS. Hãy đối chiếu yêu cầu provider: có dịch vụ chỉ hỗ trợ virtual-hosted-style, có dịch vụ chỉ hỗ trợ path-style và có dịch vụ hỗ trợ cả hai. Cần kiểm thử hostname, TLS, routing và chữ ký thực tế.

## 4. Credentials và Signature Version 4

### 4.1. S3-compatible vẫn có thể yêu cầu ký request

AWS SDK thường ký request S3 bằng **AWS Signature Version 4 (SigV4)**. Một S3-compatible provider có thể hỗ trợ SigV4 nhưng vẫn có khác biệt:

- Region ký có thể là Region cụ thể, giá trị mặc định hoặc `auto` theo tài liệu provider.
- Provider có thể yêu cầu access key/secret riêng thay cho AWS IAM role.
- Session token hoặc STS credentials có thể không được hỗ trợ giống AWS.
- Một số provider có yêu cầu riêng về canonical request, payload checksum, header hoặc thời điểm ký.
- Endpoint, host và path phải khớp chính xác giữa request đã ký và request được gửi.

**Không suy rằng dùng AWS SDK đồng nghĩa dùng AWS IAM.** SDK chỉ là client thực hiện giao thức; danh tính và quyền được xác định bởi provider mà endpoint đang kết nối.

### 4.2. Credentials cho local MinIO

Ví dụ môi trường local:

~~~powershell
$env:AWS_ACCESS_KEY_ID = "local-dev-access"
$env:AWS_SECRET_ACCESS_KEY = "local-dev-secret"
$env:AWS_REGION = "us-east-1"
$env:S3_ENDPOINT = "http://localhost:9000"
~~~

Các giá trị chỉ minh họa cho local. Credentials thực tế cần được tạo riêng trong MinIO và cấp quyền tối thiểu cho bucket thử nghiệm. Không commit chúng vào Git, không dùng cùng credentials ở nhiều môi trường và không đưa secret vào log.

### 4.3. Lỗi Region và chữ ký

Nếu nhận lỗi kiểu `SignatureDoesNotMatch`, `AuthorizationHeaderMalformed` hoặc lỗi xác thực tương tự, kiểm tra lần lượt:

1. Endpoint đúng scheme/host/port và provider yêu cầu đúng endpoint API.
2. Region của client phù hợp signing Region của provider.
3. Access key/secret có đúng với tài khoản/tenant của endpoint.
4. Path-style hay virtual-hosted-style khớp cách provider route bucket.
5. Không có proxy/gateway thay đổi host/path/query sau khi request được ký.
6. Đồng hồ hệ thống đủ chính xác để timestamp ký không bị lệch quá giới hạn provider chấp nhận.
7. Header, checksum và payload signing tương thích với phiên bản provider.

Không giải quyết lỗi chữ ký bằng cách tắt TLS hoặc gửi request không ký nếu provider yêu cầu authentication.

## 5. Dùng cùng service Spring Boot với endpoint cấu hình theo môi trường

Một service nghiệp vụ có thể tiếp tục gọi `S3Client` cho cả AWS S3 và endpoint tương thích, miễn là API cần dùng được provider hỗ trợ:

~~~java
import org.springframework.stereotype.Service;

import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;

@Service
public class ObjectStorageService {
    private final S3Client s3;
    private final String bucket;

    public ObjectStorageService(
            S3Client s3,
            @org.springframework.beans.factory.annotation.Value(
                    "${app.storage.bucket}") String bucket) {
        this.s3 = s3;
        this.bucket = bucket;
    }

    public void upload(String trustedKey, byte[] content) {
        s3.putObject(
                PutObjectRequest.builder()
                        .bucket(bucket)
                        .key(trustedKey)
                        .build(),
                RequestBody.fromBytes(content));
    }

    public byte[] downloadSmallObject(String trustedKey) {
        return s3.getObjectAsBytes(
                GetObjectRequest.builder()
                        .bucket(bucket)
                        .key(trustedKey)
                        .build())
                .asByteArray();
    }
}
~~~

Service minh họa dùng `byte[]` cho object nhỏ; file lớn nên dùng streaming hoặc Transfer Manager. `trustedKey` phải được lấy sau khi ứng dụng kiểm tra user/tenant. Nếu provider không hỗ trợ API mà service gọi, cần fallback/adapter hoặc không bật chức năng đó cho provider tương ứng.

### 5.1. Nhiều provider trong cùng ứng dụng

Nếu ứng dụng kết nối đồng thời AWS và MinIO, tạo hai client bean có tên và qualifier rõ ràng:

~~~java
@Bean("awsS3Client")
S3Client awsS3Client() {
    return S3Client.builder()
            .region(Region.AP_SOUTHEAST_1)
            .credentialsProvider(DefaultCredentialsProvider.create())
            .build(); // Endpoint AWS mặc định theo Region.
}

@Bean("localS3Client")
S3Client localS3Client() {
    return S3Client.builder()
            .region(Region.US_EAST_1)
            .endpointOverride(URI.create("http://localhost:9000"))
            .credentialsProvider(DefaultCredentialsProvider.create())
            .serviceConfiguration(S3Configuration.builder()
                    .pathStyleAccessEnabled(true)
                    .build())
            .build();
}
~~~

Ví dụ chỉ tập trung vào hai cấu hình client; code production cần tách property theo từng provider và quản lý lifecycle qua Spring. Khi inject, dùng `@Qualifier("awsS3Client")` hoặc `@Qualifier("localS3Client")` để tránh chọn nhầm.

Không quyết định provider dựa trên chuỗi bucket/key do người dùng gửi. Provider/endpoint phải do cấu hình server và logic nghiệp vụ đáng tin cậy lựa chọn.

## 6. Presigned URL và addressing style

Presigned URL là nơi khác biệt endpoint/addressing style dễ lộ ra nhất. Presigner ký **host + path + query + signed headers**. Nếu backend tạo URL trỏ đến `localhost` trong container nhưng browser chạy trên máy host hoặc máy khác, URL có thể không truy cập được.

### 6.1. Presigner phải dùng cùng endpoint và addressing style

Khi dùng custom endpoint, cấu hình `S3Presigner` nhất quán với `S3Client`:

~~~java
import java.net.URI;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;

@Configuration(proxyBeanMethods = false)
public class CompatibleS3PresignerConfiguration {

    @Bean
    public S3Presigner s3Presigner() {
        return S3Presigner.builder()
                .region(Region.US_EAST_1)
                .endpointOverride(URI.create("http://localhost:9000"))
                .credentialsProvider(DefaultCredentialsProvider.create())
                .serviceConfiguration(
                        S3Configuration.builder()
                                .pathStyleAccessEnabled(true)
                                .build())
                .build();
    }
}
~~~

Trong production, không hard-code endpoint/Region như ví dụ; dùng cùng bộ cấu hình với client. Nếu presigner dùng virtual-hosted-style nhưng client dùng path-style, URL có thể được tạo với host/path khác dự kiến.

### 6.2. URL được ký cho host nào thì client phải gọi host đó

Giả sử backend ký:

~~~text
http://localhost:9000/training-files/documents/a.txt?...signature...
~~~

Nếu browser cần truy cập qua hostname khác, ví dụ `https://storage.example.com`, **không thay host thủ công** trong URL sau khi ký. Host là một phần của canonical request; thay host thường làm chữ ký không còn hợp lệ. Hãy cấu hình presigner tạo URL ngay từ đầu với hostname mà client thực sự truy cập được, đồng thời bảo đảm DNS/TLS/routing dẫn đến cùng storage.

Trong môi trường Docker, `localhost` bên trong container là **chính container đó**, không phải máy host hoặc container khác. Nếu browser chạy ngoài Docker, URL trả về phải dùng hostname/port mà browser có thể truy cập, ví dụ domain dev hoặc hostname được expose qua reverse proxy. Proxy không được tùy ý thay path/host theo cách phá chữ ký.

### 6.3. CORS là một lớp riêng

Browser gửi PUT/GET cross-origin còn chịu quy tắc CORS của endpoint/provider. Dù presigned URL hợp lệ, trình duyệt vẫn có thể chặn JavaScript đọc response nếu provider chưa cấu hình:

- Allowed origin đúng domain frontend.
- Allowed method (GET/PUT/HEAD) phù hợp.
- Allowed headers gồm Content-Type và các header ký cần thiết.
- Expose response headers như `ETag` khi JavaScript cần đọc chúng.

CORS không thay thế chữ ký và không cấp quyền truy cập object. Một request curl thành công nhưng browser thất bại thường cần kiểm tra preflight/CORS, ngoài IAM và signature.

## 7. S3-compatible không có nghĩa mọi tính năng S3 đều giống nhau

### 7.1. Ma trận tính năng cần xác minh

| Tính năng | AWS S3 | S3-compatible provider |
| --- | --- | --- |
| PUT/GET/HEAD cơ bản | API chuẩn AWS | Thường là nền tảng tương thích |
| ListObjectsV2, continuation token | Có | Kiểm tra phiên bản API và semantics |
| Multipart upload | Có | Kiểm tra Create/UploadPart/Complete/Abort, giới hạn part và retry |
| Presigned URL SigV4 | Có | Kiểm tra signing Region, host, path-style và signed headers |
| Conditional PUT (If-Match/If-None-Match) | Có hỗ trợ theo API/điều kiện cụ thể | Có thể khác hoặc chưa hỗ trợ đầy đủ |
| Versioning/delete marker | Có | Có thể hỗ trợ một phần hoặc khác semantics |
| Lifecycle | Có nhiều loại rule | Có thể chỉ hỗ trợ subset hoặc khác timing |
| SSE-S3/SSE-KMS/DSSE-KMS | Tích hợp sâu với S3/KMS | Không mặc nhiên có cùng KMS/key policy |
| Object Lock/retention/legal hold | Có | Phụ thuộc provider; không suy từ tên API |
| ACL/Object Ownership/Block Public Access | Có semantics AWS | Có thể không đầy đủ hoặc ánh xạ khác |
| Event notifications | Tích hợp với nhiều dịch vụ AWS | Thường khác destination, payload và retry |
| S3 Select, replication, access points | Tính năng AWS chuyên biệt | Thường không được hỗ trợ hoặc có khác biệt |

Trước khi thay AWS S3 bằng provider khác, cần kiểm **API cụ thể ứng dụng thực sự gọi**, không chỉ hỏi “có hỗ trợ S3-compatible không?”.

### 7.2. Những khác biệt thường ảnh hưởng trực tiếp đến ứng dụng

**Authentication và authorization**

AWS S3 dùng IAM identity policy, bucket policy, SCP, KMS key policy và condition key. S3-compatible service có thể dùng access key riêng, user/bucket policy theo mô hình riêng hoặc chỉ hỗ trợ một phần SigV4. Không mang nguyên policy AWS sang provider khác rồi giả định quyền có cùng semantics.

**Encryption**

AWS SSE-KMS gắn với AWS KMS và các permission `kms:GenerateDataKey`, `kms:Decrypt`. Provider khác có thể có KMS riêng, mã hóa mặc định do dịch vụ quản lý hoặc chỉ hỗ trợ server-side encryption cơ bản. Không gửi header SSE-KMS của AWS nếu endpoint không hỗ trợ.

**Versioning và lifecycle**

Một provider có thể có versioning nhưng không triển khai delete marker giống AWS; lifecycle có thể thiếu noncurrent version expiration hoặc khác thời điểm thực thi. Nếu nghiệp vụ phụ thuộc khả năng restore, phải test PUT/DELETE/version-specific GET thực tế.

**Consistency và concurrency**

AWS S3 cung cấp strong read-after-write consistency cho các API object thông dụng; không mặc định mọi provider S3-compatible có cùng bảo đảm. Với dữ liệu quan trọng, kiểm tra semantics sau PUT/DELETE, LIST, conditional write và concurrent requests. Dùng database/index nghiệp vụ làm nguồn trạng thái nếu cần transaction hoặc thứ tự rõ ràng.

**Checksum và ETag**

ETag không phải lúc nào cũng là MD5 ở AWS S3, nhất là multipart hoặc một số cấu hình mã hóa. Provider khác có thể định nghĩa ETag khác. Nếu cần toàn vẹn byte, sử dụng checksum được cả hai bên hỗ trợ và test end-to-end, không dùng ETag như một checksum phổ quát.

**Metadata, tagging và HTTP behavior**

Cách chuẩn hóa Content-Type, metadata header, tags, Content-Disposition, Cache-Control và response error có thể khác. Client nên kiểm thử giá trị nhận lại qua HEAD/GET, đặc biệt khi chuyển dữ liệu từ provider này sang provider khác.

## 8. Phân biệt AWS S3 với Azure Blob Storage và Google Cloud Storage

AWS S3-compatible provider có thể dùng chung một phần AWS SDK, nhưng Azure Blob Storage và Google Cloud Storage có SDK/API riêng. Bảng dưới đây giúp xác định ranh giới abstraction:

| Khái niệm nghiệp vụ | Amazon S3 | Azure Blob Storage | Google Cloud Storage |
| --- | --- | --- | --- |
| Đơn vị chứa | Bucket | Storage account + container | Bucket |
| Định danh object | Object key | Blob name | Object name |
| Java SDK | AWS SDK v2 / Spring Cloud AWS | Azure Storage Blob SDK / Spring Cloud Azure | Google Cloud Storage Java client / Spring Cloud GCP |
| Upload lớn | Multipart upload | Block blob: stage blocks + commit block list | Resumable upload |
| Phân trang | ListObjectsV2 + continuation token | Paged iterable/continuation | Page token |
| Conditional write | ETag conditions như If-Match | Blob request conditions | Generation/metageneration preconditions |
| Identity | IAM role/credentials | Managed identity + Azure RBAC | Service account + Google IAM |
| Mã hóa khóa khách hàng quản lý | SSE-KMS | CMK qua Key Vault theo cấu hình | CMEK qua Cloud KMS |
| Link tạm | Presigned URL | SAS | Signed URL |

Một **domain interface** có thể dùng chung thao tác nghiệp vụ như upload/download/delete, nhưng implementation nên là adapter riêng:

~~~java
public interface ObjectStoragePort {
    StoredObject upload(
            String trustedKey,
            java.io.InputStream content,
            long contentLength,
            String contentType);

    void downloadTo(
            String trustedKey,
            java.io.OutputStream destination)
            throws java.io.IOException;

    void delete(String trustedKey);
}
~~~

`StoredObject` là kiểu miền do ứng dụng định nghĩa. Adapter AWS dùng `S3Client`/`S3Template`, adapter Azure dùng Blob client và adapter GCP dùng Storage client. Không cố đưa mọi tính năng provider-specific như version ID, lifecycle rule, retention, KMS key hoặc event notification vào một interface nhỏ nếu ngữ nghĩa không tương đương.

## 9. Kiểm thử S3-compatible endpoint

### 9.1. Test contract cơ bản

Với mỗi endpoint, nên có một bộ contract test dùng bucket/prefix riêng:

1. Tạo bucket test hoặc xác minh bucket tồn tại theo quyền được cấp.
2. PUT một object nhỏ với Content-Type và metadata.
3. HEAD object và kiểm tra size/metadata.
4. GET object và so sánh byte/checksum với nguồn.
5. LIST bằng prefix và thử continuation token khi có nhiều trang.
6. DELETE object và xác minh trạng thái theo semantics provider.
7. Thử multipart upload/complete/abort nếu ứng dụng cần file lớn.
8. Tạo và dùng presigned GET/PUT URL từ **máy client thực tế**, không chỉ trong cùng container.
9. Test lỗi credentials, sai Region, endpoint sai, path-style sai và TLS certificate không hợp lệ.

Không phải mọi provider đều hỗ trợ tất cả các bước; ghi rõ tính năng nào là **required**, **optional** hoặc **unsupported** cho mỗi adapter.

### 9.2. Ma trận kiểm thử local và provider thật

| Môi trường | Mục đích | Điều cần lưu ý |
| --- | --- | --- |
| Unit test/mock SDK | Kiểm tra logic tạo request, key, xử lý lỗi | Không xác minh wire protocol hay chữ ký thật |
| LocalStack | Phát triển/test một số API AWS trong local | Mô phỏng không thay thế kiểm thử AWS thật hoặc mọi S3-compatible service |
| MinIO local | Kiểm tra endpoint, path-style, PUT/GET/LIST, multipart theo phiên bản | Không đại diện cho IAM/KMS/lifecycle của AWS |
| Ceph RGW hoặc provider đích | Xác minh compatibility với endpoint thực | Test API, auth, Region, versioning, policy và giới hạn cụ thể |
| AWS sandbox | Xác minh AWS behavior chính thức | Dùng role/bucket riêng, dọn dữ liệu và theo dõi chi phí |

### 9.3. Kiểm thử bằng AWS SDK v2

Ví dụ test contract đơn giản (dùng bucket test đã được chuẩn bị):

~~~java
String key = "compat-test/" + java.util.UUID.randomUUID() + ".txt";
byte[] expected = "hello-compatible-storage".getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

s3.putObject(
        PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType("text/plain")
                .build(),
        RequestBody.fromBytes(expected));

var metadata = s3.headObject(b -> b.bucket(bucket).key(key));
if (metadata.contentLength() != expected.length) {
    throw new AssertionError("Content-Length không khớp");
}

byte[] actual = s3.getObjectAsBytes(b -> b
        .bucket(bucket)
        .key(key)).asByteArray();

if (!java.util.Arrays.equals(expected, actual)) {
    throw new AssertionError("Nội dung object không khớp");
}
~~~

Đây là logic minh họa; trong integration test cần dùng assertion framework, tạo key ngẫu nhiên và dọn object trong `finally`/teardown. Nếu bucket bật versioning, cleanup có thể cần xử lý version thay vì chỉ DELETE key hiện hành.

### 9.4. Kiểm thử presigned URL qua browser

Một test chỉ gọi URL bằng curl không kiểm chứng đầy đủ luồng browser. Cần kiểm tra:

- URL trả về dùng host mà browser có thể phân giải và kết nối.
- Scheme HTTPS/TLS certificate hợp lệ ở môi trường staging/production.
- Bucket nằm đúng vị trí trong host/path theo addressing style.
- Signed headers được browser gửi nguyên vẹn.
- CORS cho phép origin, method và header cần thiết.
- Reverse proxy/DNS không rewrite host/path sau khi ký.
- URL không bị log hoặc chia sẻ ngoài phạm vi người dùng được cấp.

**Không sửa host trong URL sau khi presign** để “cho browser truy cập được”; cấu hình presigner phải dùng endpoint public/accessible chính xác ngay từ đầu.

## 10. Lỗi thường gặp và cách chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Connection refused | Endpoint/port sai, service chưa chạy, container không route được | Kiểm tra endpoint từ đúng môi trường chạy ứng dụng |
| DNS resolution failed | Hostname bucket hoặc endpoint không phân giải | Kiểm DNS, virtual-hosted/path-style và network |
| TLS hostname mismatch | Certificate không khớp hostname bucket/subdomain | Kiểm addressing style và certificate; không tắt TLS validation |
| 404 bucket/object | Bucket chưa tạo, key sai, path-style không phù hợp | Kiểm bucket, key và URL thực tế |
| SignatureDoesNotMatch | Region, credentials, host/path, signed headers hoặc clock sai | Kiểm SigV4 canonical request và endpoint |
| AuthorizationHeaderMalformed | Region ký không đúng provider yêu cầu | Chọn signing Region theo tài liệu endpoint |
| InvalidRequest / unsupported header | Provider không hỗ trợ một header/API S3 mới | Tách capability, bỏ header chỉ khi use case không cần |
| Multipart Complete lỗi | Semantics ETag/part order/part size khác hoặc thiếu hỗ trợ | Test từng API multipart; kiểm part ETag và giới hạn |
| Presigned URL không dùng được ngoài container | URL chứa localhost hoặc hostname nội bộ | Cấu hình endpoint mà browser truy cập được trước khi ký |
| Curl được, browser lỗi | CORS/preflight hoặc header bị browser chặn | Kiểm CORS, expose ETag và signed headers |
| HEAD/GET sau PUT không thấy object | Consistency hoặc API compatibility khác kỳ vọng | Test semantics provider và không mặc định giống AWS |

Khi log lỗi, ghi operation, provider/endpoint alias, bucket/prefix theo chính sách, HTTP status, request ID nếu provider trả về và mã lỗi. Không ghi access key, secret, presigned URL đầy đủ hoặc payload nhạy cảm.

## 11. Chiến lược triển khai đa môi trường

Một ứng dụng Spring Boot có thể dùng cùng domain service, nhưng cấu hình storage phải được quản lý theo môi trường:

~~~text
local:
  endpoint = http://localhost:9000
  pathStyle = true
  credentials = local-only
  bucket = training-files

integration:
  endpoint = endpoint của S3-compatible test
  pathStyle = theo provider
  credentials = secret của test environment
  bucket = test-bucket

production AWS:
  endpoint = AWS endpoint mặc định theo Region
  pathStyle = theo cấu hình AWS SDK phù hợp
  credentials = IAM workload role
  bucket = production bucket
~~~

**Không đưa credentials hoặc endpoint production vào file local committed.** Endpoint có thể là cấu hình không nhạy cảm, nhưng việc thay endpoint có thể khiến dữ liệu được gửi đến một hệ thống khác; nên quản lý nó qua cấu hình được kiểm soát, allowlist host và tách profile.

### 11.1. Checklist trước khi chuyển provider

- API cần dùng có được hỗ trợ không: PUT/GET/HEAD/LIST/delete/multipart/conditional writes?
- Endpoint yêu cầu virtual-hosted hay path-style? DNS và TLS đã hoạt động chưa?
- Region ký SigV4 và credentials có đúng không?
- Presigned URL có hoạt động từ browser/client ngoài container không?
- CORS, signed headers, Content-Type và ETag có tương thích không?
- Versioning, lifecycle, encryption, retention, object lock và event notification có cùng semantics không?
- Consistency sau PUT/DELETE và pagination khi object thay đổi có đáp ứng nghiệp vụ không?
- Multipart giới hạn kích thước part, số part, retry và abort thế nào?
- IAM/policy của provider có thể diễn đạt least privilege và audit cần thiết không?
- Đã có contract test trên **endpoint đích thực tế** và AWS sandbox khi cần so sánh chưa?

## 12. Bài tập thực hành

### Bài A — Kết nối MinIO bằng path-style

Chạy một S3-compatible service trong môi trường local và cấu hình Spring Boot với endpoint `http://localhost:9000`, Region ký phù hợp, credentials local riêng và `pathStyleAccessEnabled(true)`. Tạo bucket, upload file nhỏ, HEAD và download. Quan sát URL request để xác nhận bucket nằm trong path.

### Bài B — So sánh virtual-hosted-style

Nếu môi trường có DNS wildcard cho bucket subdomain, tắt path-style và thử PUT/GET. So sánh hostname, TLS certificate và cách routing. Thử bucket có dấu chấm để hiểu ảnh hưởng certificate wildcard.

### Bài C — Presigned URL ngoài container

Tạo presigned GET URL từ ứng dụng chạy trong Docker. Nếu URL chứa `localhost` hoặc hostname chỉ container nhìn thấy, hãy thay cấu hình endpoint public/dev-accessible **trước khi ký**. Dùng browser hoặc curl trên máy host để tải file; xác minh không sửa URL sau khi ký.

### Bài D — Kiểm tra API compatibility

Tạo contract test PUT/GET/HEAD/LIST/DELETE trên AWS S3 và một S3-compatible endpoint. Nếu ứng dụng cần multipart, versioning hoặc conditional PUT, thêm test riêng cho từng tính năng. Ghi lại khác biệt thay vì đánh đồng mọi endpoint.

### Bài E — Thiết kế adapter đa cloud

Tạo `ObjectStoragePort` trong domain. Viết adapter AWS dùng `S3Client`, adapter Azure dùng Blob SDK và adapter GCP dùng Storage SDK. Xác định các capability cần bật riêng (versioning, lifecycle, encryption, presigned URL, multipart) và thiết kế cách báo `unsupported` rõ ràng.

### Câu hỏi tự kiểm tra

1. S3-compatible API có bảo đảm hỗ trợ mọi tính năng của AWS S3 không?
2. `endpointOverride` khác bucket/key như thế nào?
3. Path-style và virtual-hosted-style đặt bucket ở đâu trong URL?
4. Khi nào path-style hữu ích với MinIO/local endpoint?
5. Vì sao Region vẫn cần khi dùng custom endpoint và SigV4?
6. Tại sao không được sửa host của presigned URL sau khi ký?
7. Bucket có dấu chấm có thể gặp vấn đề gì với TLS wildcard certificate?
8. Vì sao AWS SDK có thể kết nối S3-compatible nhưng IAM policy AWS không nhất thiết dùng được?
9. Những khác biệt nào cần test với multipart, versioning, lifecycle và checksum?
10. Vì sao ETag không nên được coi là MD5 phổ quát?
11. Một URL chạy bằng curl nhưng không chạy trên browser cần kiểm tra lớp nào?
12. Làm sao phân biệt lỗi endpoint/network với lỗi chữ ký hoặc quyền?
13. Những chức năng nào nên nằm trong domain interface và chức năng nào cần provider adapter?
14. Vì sao cần contract test trên endpoint đích thực tế thay vì chỉ dựa vào LocalStack/MinIO?

**Kết quả mong đợi:** người học cấu hình được Spring Boot/AWS SDK v2 kết nối tới một S3-compatible endpoint, lựa chọn đúng path-style hoặc virtual-hosted-style, hiểu vai trò endpoint/Region/credentials/Signature V4 và xác định các giới hạn tương thích trước khi chuyển ứng dụng giữa AWS S3 và các object storage provider khác.

