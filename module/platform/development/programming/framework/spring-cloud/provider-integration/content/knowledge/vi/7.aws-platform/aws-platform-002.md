# Chọn BOM, starter và thế hệ AWS SDK phù hợp

## 1. Vấn đề cần giải quyết

Trong một dự án Spring Boot tích hợp Amazon S3, Amazon SQS hoặc AWS Secrets Manager, thêm một dependency rồi biên dịch thành công **chưa đủ** để bảo đảm ứng dụng chạy đúng. Spring Boot, Spring Cloud AWS của AWSpring và AWS SDK for Java có lịch phát hành, tập API và yêu cầu tương thích riêng. Một lựa chọn thiếu nhất quán dễ dẫn đến lỗi khi khởi động, thiếu bean, xung đột class hoặc hỏng ở runtime.

Bài học thuộc chương **Nền tảng AWS** của module **SPRING_CLOUD_PROVIDER_INTEGRATION**. Mục tiêu của module là thực hành tích hợp Spring Boot với dịch vụ managed của AWS, Azure và Google Cloud, từ quyền truy cập, storage, messaging, dữ liệu, secret đến kiểm thử và so sánh provider. Bài này tập trung vào quyết định đầu tiên trong nhánh AWS: **chọn đúng bộ phiên bản và tập dependency trước khi viết mã truy cập cloud**.

Sau bài học, bạn có thể:

- Phân biệt vai trò của **BOM**, **starter**, **AWS SDK** và dependency trực tiếp.
- Nhận diện hai thế hệ AWS SDK for Java thông qua Maven coordinates, package và API.
- Chọn một bộ phiên bản tương thích theo Spring Boot, Java, AWSpring và dịch vụ AWS cần dùng.
- Khai báo Maven/Gradle sao cho các module AWS dùng phiên bản được kiểm soát.
- Phát hiện xung đột dependency, chuẩn bị kế hoạch di trú và xác minh ứng dụng ở các mức kiểm thử.

> **Lưu ý phiên bản:** Các đoạn khai báo trong bài minh họa dòng **Spring Boot 3.x / Spring Cloud AWS 3.x / AWS SDK for Java 2.x**. Chúng không khẳng định mọi phiên bản có cùng số major là tương thích. Phải thay placeholder bằng **phiên bản phát hành cụ thể** và đối chiếu tài liệu tương thích của phiên bản AWSpring đang chọn trước khi chạy; nếu dự án ở thế hệ Spring Boot mới hơn, dùng bảng tương thích của thế hệ đó.

## 2. Bốn lớp quyết định dependency

Một dự án có thể có cả Spring Boot, AWSpring và AWS SDK trên classpath, nhưng mỗi thành phần có nhiệm vụ khác nhau.

| Thành phần | Vai trò | Ví dụ | Điều không tự thực hiện |
| --- | --- | --- | --- |
| Spring Boot | Nền tảng chạy ứng dụng Spring, auto-configuration và các starter nền tảng | `spring-boot-starter-web`, `spring-boot-starter-actuator` | Không tự cung cấp mọi tích hợp AWS |
| AWSpring / Spring Cloud AWS | Tích hợp dịch vụ AWS vào Spring bằng configuration, template, listener | `spring-cloud-aws-starter-s3`, `spring-cloud-aws-starter-sqs` | Không thay thế toàn bộ SDK hoặc tạo sẵn quyền IAM |
| AWS SDK for Java | Client gọi API AWS, ký request, xử lý response, retry/network | `software.amazon.awssdk:s3`, `software.amazon.awssdk:sqs` | Không tự biến API AWS thành Spring listener/template |
| BOM (Bill of Materials) | Quản lý **phiên bản** của một tập dependency có liên quan | `spring-cloud-aws-dependencies`, `software.amazon.awssdk:bom` | Không tự thêm module S3/SQS vào ứng dụng |

Có hai câu hỏi tách biệt:

1. **Cần chức năng nào?** Chọn đúng starter hoặc SDK module và đưa nó vào phần dependencies.
2. **Dùng phiên bản nào?** Chọn bộ phiên bản đã được quản lý bằng Spring Boot dependency management và BOM liên quan.

**BOM không phải starter.** Import BOM cho phép bỏ `<version>` trên các dependency được BOM quản lý; nó không làm `S3Template` hoặc `@SqsListener` xuất hiện nếu chưa thêm starter cần thiết. Ngược lại, thêm một starter không chứng minh các phiên bản trong toàn bộ classpath đã nhất quán nếu có override hoặc dependency cũ khác.

### 2.1. BOM trong Maven và platform trong Gradle

Trong Maven, BOM thường được import vào `<dependencyManagement>` với `type=pom` và `scope=import`. Nó xác định version được sử dụng khi dependency tương ứng được khai báo mà không có version riêng.

Trong Gradle, có thể sử dụng `platform("group:artifact:version")` hoặc cơ chế quản lý dependency tương đương để áp dụng các ràng buộc phiên bản. Các version constraint có thể tương tác với những ràng buộc khác; luôn xem **resolved dependency graph**, đừng suy luận chỉ từ file build.

Ví dụ: có import BOM quản lý phiên bản S3/SQS nhưng không khai báo starter S3 thì không có lý do để mong ứng dụng tự xuất hiện bean `S3Template`.

## 3. Nhận diện thế hệ AWS SDK for Java

AWS cung cấp hai họ SDK Java có tên gần nhau nhưng class và cách thiết kế khác nhau.

| Tiêu chí | AWS SDK for Java **1.x** | AWS SDK for Java **2.x** |
| --- | --- | --- |
| Maven group | `com.amazonaws` | `software.amazon.awssdk` |
| Module S3 điển hình | `aws-java-sdk-s3` | `s3` |
| Client S3 | `com.amazonaws.services.s3.AmazonS3` | `software.amazon.awssdk.services.s3.S3Client` hoặc `S3AsyncClient` |
| Client SQS | `AmazonSQS` / `AmazonSQSAsync` | `SqsClient` / `SqsAsyncClient` |
| Request | Thường là object có setter hoặc constructor | Thường là immutable object tạo bằng `builder()` |
| Credentials | `AWSCredentialsProvider` | `AwsCredentialsProvider` |
| Cơ chế async | API/kiến trúc của SDK 1.x | Client bất đồng bộ riêng của SDK 2.x |
| Hướng chọn cho mã mới | Thế hệ cũ, cần đánh giá di trú | Thế hệ ưu tiên khi tích hợp mới phù hợp hệ sinh thái hiện tại |

Một thao tác đọc metadata S3 bằng SDK 2.x:

~~~java
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.HeadObjectRequest;

public final class ObjectMetadataService {
    private final S3Client s3Client;

    public ObjectMetadataService(S3Client s3Client) {
        this.s3Client = s3Client;
    }

    public long sizeOf(String bucket, String key) {
        var request = HeadObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();
        return s3Client.headObject(request).contentLength();
    }
}
~~~

Ví dụ này sử dụng `S3Client` của SDK 2.x; không thể thay import `S3Client` bằng `AmazonS3` rồi giữ nguyên builder và method chain. **Di trú thế hệ SDK là thay đổi API**, không phải chỉ đổi một số version.

### 3.1. Quan hệ với Spring Cloud AWS

Trong các dòng thường gặp:

- Tích hợp **Spring Cloud AWS 2.x** gắn với hệ sinh thái Spring Boot/Spring Framework đời trước và AWS SDK Java **1.x**.
- Tích hợp **Spring Cloud AWS 3.x** thuộc AWSpring hiện đại, sử dụng AWS SDK Java **2.x**, phù hợp với hệ sinh thái Spring Boot **3.x** khi chọn đúng phiên bản tương thích.
- Khi dự án sử dụng các dòng mới hơn, không tự áp công thức “cùng major là chạy được”: tra cứu compatibility matrix, release notes, Java baseline và module support của **đúng release**.

Họ thư viện Spring Cloud AWS cũ cũng có thể xuất hiện dưới group/artifact khác với `io.awspring.cloud`. Cần tra metadata của dependency và import trong mã, không chỉ nhìn tên “AWS” hoặc “Spring Cloud”.

**Một bẫy thường gặp:** `com.amazonaws` và `software.amazon.awssdk` có thể cùng xuất hiện trong dependency graph vì một thư viện legacy vẫn kéo SDK 1.x. Maven/Gradle không tự xem hai group này là hai phiên bản của cùng một artifact để xử lý bằng quy tắc “newest wins”. Hai thế hệ có thể cùng hiện diện về mặt classpath, nhưng điều đó **không** khiến class, credential provider hoặc listener của chúng hoán đổi được. Đừng dùng cả hai do vô ý; nếu buộc phải tồn tại trong giai đoạn di trú, xác định rõ thành phần nào sở hữu client nào và kiểm thử kỹ cả đường đi runtime.

## 4. Quy trình chọn bộ phiên bản

Đừng bắt đầu từ một đoạn dependency ngẫu nhiên trên diễn đàn. Hãy chọn theo thứ tự:

~~~mermaid
flowchart TD
    A[Phiên bản Java và Spring Boot của dự án] --> B[Tra tài liệu tương thích AWSpring]
    B --> C[Chọn release Spring Cloud AWS cụ thể]
    C --> D[Chọn BOM và starter theo dịch vụ]
    D --> E[Kiểm tra AWS SDK generation và phiên bản được quản lý]
    E --> F[Phân tích resolved dependency graph]
    F --> G{Có xung đột hoặc API cũ?}
    G -->|Có| H[Điều chỉnh dependency / lập kế hoạch migration]
    H --> F
    G -->|Không| I[Kiểm thử khởi động, tích hợp và quyền AWS]
~~~

### Bước 1: Chốt baseline của dự án

Xác định:

- Phiên bản **Java/JDK** dùng biên dịch và chạy.
- Phiên bản **Spring Boot** và **Spring Framework** đi kèm.
- Ứng dụng có đang dùng **Spring Cloud release train** cho các tính năng khác hay không.
- Dependency AWS nào đã tồn tại; có thư viện cũ giữ SDK 1.x hoặc Spring Cloud AWS đời trước không.
- Mục tiêu nghiệp vụ: S3, SQS, SNS, Secrets Manager, Parameter Store hay API AWS chưa có starter phù hợp.

Spring Boot 3.x sử dụng Spring Framework 6 và Java baseline 17, kéo theo khác biệt `jakarta.*` so với nhiều thư viện cũ dựa trên `javax.*`. Khi nâng từ Boot 2.x, lỗi có thể đến từ **Spring/Jakarta** chứ không chỉ từ AWS SDK.

### Bước 2: Chọn AWSpring release tương thích

Kiểm tra tài liệu phát hành, dependency management và ma trận hỗ trợ của **AWSpring**. Cần trả lời:

- Release này hỗ trợ phiên bản Spring Boot/Spring Framework nào?
- Yêu cầu Java tối thiểu nào?
- Starter S3, SQS, Secrets Manager, Parameter Store... có sẵn và API của chúng mang namespace nào?
- AWS SDK 2.x được quản lý ở phiên bản nào? Có lưu ý quan trọng về security hoặc khả năng tương thích không?

Đây là bước cần thiết ngay cả khi dự án chỉ nâng một bản minor hoặc patch. Không dựa riêng vào tính tương đồng của số hiệu `3.x`.

### Bước 3: Chọn starter theo **tính năng thực sự dùng**

| Nhu cầu ở ứng dụng Spring Boot | Dependency AWSpring để xem xét | API Spring thường muốn dùng |
| --- | --- | --- |
| Đọc/ghi object trên S3 | `io.awspring.cloud:spring-cloud-aws-starter-s3` | `S3Template`, bean client SDK |
| Gửi/nhận message SQS | `io.awspring.cloud:spring-cloud-aws-starter-sqs` | `SqsTemplate`, `@SqsListener` |
| Publish sự kiện SNS | `io.awspring.cloud:spring-cloud-aws-starter-sns` | Tích hợp SNS nếu release hỗ trợ |
| Đọc secret thành cấu hình | `io.awspring.cloud:spring-cloud-aws-starter-secrets-manager` | Spring Config Data / cấu hình ứng dụng |
| Đọc parameter từ Systems Manager | `io.awspring.cloud:spring-cloud-aws-starter-parameter-store` | Spring Config Data / cấu hình ứng dụng |
| Gọi operation AWS chưa có template thích hợp | AWS SDK v2 module, ví dụ `software.amazon.awssdk:sts` | Client và request/response của SDK |

Tên, khả năng và cấu hình chính xác của starter phải kiểm tra với release đang chọn. Không thêm mọi starter “để dành”, vì mỗi starter có thể mở thêm auto-configuration, bean, property và dependency.

**Khi nào không cần AWSpring?** Một CLI Java truy vấn DynamoDB không sử dụng Spring hoặc một Spring Boot service chỉ gọi một operation SDK chuyên biệt hoàn toàn có thể dùng trực tiếp AWS SDK 2.x. Chỉ thêm AWSpring khi cần lợi ích thật từ integration Spring.

### Bước 4: Để một bộ quản lý version, hạn chế override

Với ứng dụng dùng AWSpring, lấy **AWSpring BOM** làm nguồn quản lý version cho các module Spring Cloud AWS. Đối với SDK module, xem phiên bản được BOM/graph giải quyết rồi mới quyết định có cần import thêm AWS SDK BOM hay override một module hay không.

Nếu dự án có Spring Boot BOM, Spring Cloud BOM và AWSpring BOM, phải xem các version cuối cùng thực sự được Maven/Gradle chọn. Import nhiều BOM không bảo đảm mọi phần tử được quản lý theo ý muốn; quy tắc ưu tiên/ghi đè khác nhau theo công cụ và cách khai báo.

### Bước 5: Chốt phiên bản cụ thể và kiểm thử

Không sử dụng dynamic version như `latest.release` hoặc `3.+` cho build cần tái lập. Ghi lại release của Spring Boot, AWSpring và các SDK module đã resolve trong tài liệu dự án hoặc dependency lock; cập nhật có kiểm soát với CI. Sau khi thay BOM, chạy lại kiểm thử tích hợp ở các luồng AWS quan trọng.

## 5. Khai báo Maven khi dùng AWSpring

Giả sử một dịch vụ Spring Boot 3.x cần thao tác S3 và SQS. Cấu hình Maven dưới đây giả định dự án **đã có** `spring-boot-starter-parent` hoặc cơ chế quản lý dependency Spring Boot thích hợp.

### 5.1. Import AWSpring BOM

~~~xml
<properties>
    <!-- Thay bằng release AWSpring cụ thể, đã xác nhận tương thích Boot/JDK -->
    <spring-cloud-aws.version>CHON_RELEASE_TUONG_THICH</spring-cloud-aws.version>
</properties>

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
~~~

`CHON_RELEASE_TUONG_THICH` là **placeholder**, không phải version hợp lệ để dùng ngay. Thay bằng số release có thật sau khi đối chiếu compatibility matrix. Với Maven, nếu chỉ thêm đoạn `dependencyManagement` mà không thêm dependencies, ứng dụng sẽ **không** tải S3/SQS starter để sử dụng.

### 5.2. Thêm đúng starter và SDK module trực tiếp khi cần

~~~xml
<dependencies>
    <!-- Tích hợp Spring với S3 -->
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-s3</artifactId>
    </dependency>

    <!-- Gửi và nhận message qua SQS bằng Spring -->
    <dependency>
        <groupId>io.awspring.cloud</groupId>
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>

    <!-- Nếu source của ứng dụng tự import S3Client của SDK -->
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>s3</artifactId>
    </dependency>
</dependencies>
~~~

Phần lớn starter kéo SDK module cần thiết **transitively**, nhưng nếu mã nguồn của chính ứng dụng dùng type `S3Client` thì khai báo dependency trực tiếp lên SDK S3 giúp thể hiện rõ thiết kế và tránh phụ thuộc ngầm vào cấu trúc transitive của starter. Điều kiện là version `software.amazon.awssdk:s3` phải được dependency management thực tế quản lý. Nếu build báo thiếu version, kiểm tra BOM và thiết lập dependency management trước khi tự gắn một số version tùy ý.

Ứng dụng dùng trực tiếp SDK sẽ import type thuộc `software.amazon.awssdk.*`:

~~~java
import io.awspring.cloud.s3.S3Template;
import io.awspring.cloud.sqs.operations.SqsTemplate;
import software.amazon.awssdk.services.s3.S3Client;
~~~

`S3Template` và `SqsTemplate` do AWSpring cung cấp; `S3Client` do SDK 2.x cung cấp. Chúng có thể cùng hiện diện trong một service Spring Boot với starter và version tương thích.

### 5.3. Thêm một SDK module cho dịch vụ chưa cần starter

Ví dụ một service chỉ cần gọi AWS STS để kiểm tra identity đang được sử dụng, có thể thêm SDK module `sts`:

~~~xml
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sts</artifactId>
</dependency>
~~~

SDK v2 cho phép chọn module theo dịch vụ, không cần “nhập cả AWS SDK”. Nếu ứng dụng có nhu cầu tích hợp Spring khác, nó vẫn có thể đồng thời dùng AWSpring starter.

## 6. Nếu chỉ dùng AWS SDK 2.x: chọn SDK BOM

Với dự án **không dùng Spring Cloud AWS**, ví dụ một tác vụ Java độc lập upload S3 hoặc một ứng dụng Spring có adapter SDK thuần, có thể import trực tiếp BOM của AWS SDK v2:

~~~xml
<properties>
    <!-- Thay bằng phiên bản SDK v2 cụ thể được phê duyệt -->
    <aws.sdk.version>CHON_RELEASE_SDK_V2</aws.sdk.version>
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
        <artifactId>s3</artifactId>
    </dependency>
    <dependency>
        <groupId>software.amazon.awssdk</groupId>
        <artifactId>sqs</artifactId>
    </dependency>
</dependencies>
~~~

Các property ở trên vẫn là placeholder cần thay bằng **release thật**. SDK BOM giúp đồng bộ các module SDK (`s3`, `sqs`, `auth`, `regions`, `sdk-core`...), giảm tình trạng dùng nhiều version không nhất quán.

**Nếu đang dùng AWSpring**, đừng mặc định import thêm SDK BOM với version mới hơn mà không đánh giá. Override lệch nhóm version SDK có thể tạo lỗi linkage khi AWSpring gọi API nội bộ/hợp đồng của SDK. Khi cần nâng SDK để xử lý lỗi bảo mật hoặc bug cụ thể, hãy kiểm tra release notes, compatibility, effective dependency graph và kiểm thử các đường đi S3/SQS/credentials.

## 7. Khai báo Gradle Kotlin DSL

Với Gradle, có thể đặt release AWSpring đã chọn trong `gradle.properties`:

~~~properties
springCloudAwsVersion=CHON_RELEASE_TUONG_THICH
~~~

Trong `build.gradle.kts`, sau khi dự án đã cấu hình plugin Spring Boot, Java và repository Maven Central:

~~~kotlin
val springCloudAwsVersion: String by project

dependencies {
    implementation(platform(
        "io.awspring.cloud:spring-cloud-aws-dependencies:$springCloudAwsVersion"
    ))

    implementation("io.awspring.cloud:spring-cloud-aws-starter-s3")
    implementation("io.awspring.cloud:spring-cloud-aws-starter-sqs")

    // Khai báo trực tiếp khi mã nguồn import SDK client.
    implementation("software.amazon.awssdk:s3")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
~~~

`platform(...)` áp dụng version constraint cho cấu hình liên quan. Nếu dùng `io.spring.dependency-management` plugin thay cho (hoặc cùng với) Gradle native platform, cần hiểu thứ tự ưu tiên của cơ chế đã chọn và kiểm tra resolved version. Không sao chép cùng lúc nhiều cách import BOM mà không có lý do rõ ràng.

Nếu **chỉ dùng AWS SDK v2**, thay platform tương ứng bằng:

~~~kotlin
val awsSdkVersion: String by project

dependencies {
    implementation(platform("software.amazon.awssdk:bom:$awsSdkVersion"))
    implementation("software.amazon.awssdk:s3")
    implementation("software.amazon.awssdk:sqs")
}
~~~

`gradle.properties` cần có `awsSdkVersion` là phiên bản SDK thực tế. Không dùng literal như `CHON_RELEASE_TUONG_THICH` trong bản build đã commit.

## 8. Nhìn dependency graph: cách biết BOM thực sự có hiệu lực

Lỗi do dependency không chỉ xảy ra ở lúc biên dịch. Có trường hợp build thành công nhưng khởi động gặp `NoSuchMethodError`, `NoClassDefFoundError` hoặc listener không được tạo do classpath pha trộn nhiều thế hệ.

### 8.1. Lệnh kiểm tra dành cho Maven

Các lệnh dưới đây dùng để kiểm tra **trong dự án của bạn**, không phải các lệnh đã được thực thi cho bài học:

~~~bash
./mvnw dependency:tree
./mvnw help:effective-pom
~~~

Trên Windows có thể sử dụng `mvnw.cmd` thay cho `./mvnw`. Từ kết quả, tìm các group:

- `io.awspring.cloud`: các starter và module Spring Cloud AWS phải thuộc bộ release đã chọn.
- `software.amazon.awssdk`: các module AWS SDK v2 phải có version nhất quán theo management.
- `com.amazonaws`: xác định thư viện nào đang kéo SDK v1; không tự động xóa khi chưa xác định nơi sử dụng.
- `org.springframework`, `org.springframework.boot`: kiểm tra thư viện Spring đang phù hợp baseline.

`dependency:tree` thể hiện module đi qua những đường phụ thuộc nào; `effective-pom` giúp xác định version do dependency management giải quyết sau khi kế thừa parent và import BOM.

### 8.2. Lệnh kiểm tra dành cho Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency software.amazon.awssdk --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-cloud-aws --configuration runtimeClasspath
~~~

Trên Windows có thể sử dụng `gradlew.bat`. `dependencyInsight` giúp xác định dependency nào yêu cầu version và vì sao Gradle chọn version sau khi áp dụng các constraint. Đối chiếu cả compile/runtime classpath nếu có dấu hiệu khác nhau.

### 8.3. Checklist đọc kết quả

| Dấu hiệu | Điều cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Nhiều phiên bản SDK v2 trong khai báo hoặc graph phức tạp | Module nào override BOM? Dependency nào yêu cầu bản khác? | Đưa các module về version được quản lý đã kiểm chứng |
| Có cả `com.amazonaws` và `software.amazon.awssdk` | Có thư viện cũ nào vẫn sử dụng SDK v1? | Di trú hoặc giữ ranh giới tạm thời một cách có chủ đích |
| `NoSuchMethodError` khi gọi SDK | API được compile và class được nạp ở runtime có tương thích không? | Xem resolved runtimeClasspath và phiên bản SDK thật sự |
| `ClassNotFoundException` cho `S3Template` | Thiếu starter/module AWSpring hay phiên bản không có API đó? | Thêm đúng starter và kiểm tra import/package |
| Không tạo bean `SqsTemplate` | Có starter SQS, điều kiện auto-configuration và config phù hợp không? | Kiểm tra condition report, starter và cấu hình |
| Lỗi `javax.*` / `jakarta.*` khi nâng Boot | Có dependency Spring đời cũ không tương thích? | Đồng bộ cả Spring stack và mã sử dụng namespace |
| 403 `AccessDenied` khi chạy AWS | Role, policy, ARN, region, KMS có đúng? | Kiểm tra IAM/resource policy; BOM không cấp quyền |

Đặc biệt, **403 không mặc nhiên là lỗi dependency**, và **một class bị thiếu không mặc nhiên là lỗi IAM**. Chẩn đoán theo tầng sẽ tiết kiệm thời gian.

## 9. Những lựa chọn dễ sai và cách tránh

### 9.1. Khai báo version riêng trên từng SDK module

Ví dụ **không nên** thiết lập các module SDK theo hai version tùy ý như sau:

~~~xml
<!-- Ví dụ phản diện: không làm theo -->
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>s3</artifactId>
    <version>VERSION_A</version>
</dependency>
<dependency>
    <groupId>software.amazon.awssdk</groupId>
    <artifactId>sqs</artifactId>
    <version>VERSION_B</version>
</dependency>
~~~

Một số module có thể vẫn biên dịch, nhưng class dùng chung như `sdk-core`, `auth` và HTTP transport có thể bị resolve theo lựa chọn khó kiểm soát. Ưu tiên dùng BOM, chỉ override khi có nguyên nhân cụ thể và kiểm thử runtime.

### 9.2. Lấy ví dụ của Spring Cloud AWS đời cũ

Code cũ có thể chứa:

~~~java
// Ví dụ nhận diện API legacy:
import com.amazonaws.services.s3.AmazonS3;
// Một số thư viện Spring Cloud AWS đời cũ dùng kiểu listener/template khác.
~~~

Trong khi mã tích hợp thế hệ 3.x thường dùng:

~~~java
import io.awspring.cloud.s3.S3Template;
import io.awspring.cloud.sqs.annotation.SqsListener;
import software.amazon.awssdk.services.s3.S3Client;
~~~

Những import này là dấu hiệu để kiểm tra migration. Không thay chỉ package rồi kỳ vọng mọi property và lifecycle giữ nguyên; khi nâng major phải rà lại cả cấu hình, listener, conversion, acknowledgement và lỗi runtime.

### 9.3. Trộn Spring Cloud BOM và AWSpring BOM mà không kiểm tra

**Spring Cloud release train BOM** phục vụ một tập dự án Spring Cloud; **AWSpring BOM** phục vụ tập Spring Cloud AWS. Chúng không phải cùng một artifact và không có nghĩa là một BOM bất kỳ sẽ quản lý toàn bộ library AWSpring mong muốn. Xác minh rõ BOM nào quản lý module nào và phiên bản nào thắng nếu trùng quy tắc.

### 9.4. Dùng starter không cần thiết

Thêm mọi starter S3/SQS/SNS/Secrets Manager có thể kéo thêm HTTP client, JSON converter, auto-configuration và yêu cầu cấu hình chưa dùng. Chọn module nhỏ nhất đáp ứng yêu cầu để dễ kiểm soát classpath, footprint và lỗi khởi động.

### 9.5. Tưởng SDK mới tự giải quyết quyền AWS

Đổi từ SDK 1.x sang 2.x không tự tạo role, policy, bucket, queue, secret hoặc VPC endpoint. Cả hai thế hệ đều cần identity và region phù hợp. Với SDK 2.x, thông thường nên để credential chain tìm temporary credentials từ IAM role dành cho workload; tránh commit access key cố định vào cấu hình.

## 10. Chiến lược nâng cấp từ SDK 1.x và Spring Cloud AWS cũ

Một dự án cũ đang dùng Spring Boot 2.x, AWSpring 2.x và `AmazonS3` thường không thể chỉ nâng `aws-java-sdk-s3` lên artifact `software.amazon.awssdk:s3`. Thay đổi đồng thời có thể liên quan tới Java baseline, Spring Framework, Spring Boot, namespace `javax`/`jakarta`, auto-configuration và API AWSpring.

Quy trình nâng cấp có kiểm soát:

1. **Kiểm kê:** liệt kê dependency AWS cũ, import `com.amazonaws.*`, bean client tự tạo, template/listener, property và test.
2. **Chọn đích:** xác định cặp release Spring Boot và AWSpring được nhà dự án hỗ trợ; xác định JDK và AWS SDK 2.x version được quản lý.
3. **Đổi build:** cập nhật BOM/starter theo bộ phiên bản, loại bỏ phụ thuộc legacy **khi các caller đã được di trú**; kiểm tra graph.
4. **Đổi mã:** chuyển SDK client, request builder, exception, sync/async code; cập nhật listener/template và config theo tài liệu của release.
5. **Đổi kiểm thử:** kiểm tra serialization, SQS acknowledgement, S3 metadata, credentials provider, timeout, retry, exception mapping.
6. **Triển khai thử:** chạy smoke test trên tài khoản và role dành cho kiểm thử; theo dõi lỗi auth, độ trễ, retry và dấu hiệu message trùng.

Nếu một thư viện bên thứ ba vẫn sử dụng SDK 1.x, cân nhắc nâng hoặc thay thư viện đó. Có thể tồn tại hai SDK trong giai đoạn chuyển đổi, nhưng sự tồn tại này phải có chủ sở hữu, giới hạn và kế hoạch loại bỏ rõ ràng.

### Những chỗ dễ phát sinh regression

| Mảng | Cần xác minh khi nâng |
| --- | --- |
| Client | `AmazonS3` → `S3Client`, `AmazonSQSAsync` → `SqsAsyncClient` và API bất đồng bộ |
| Request/response | Builder, tên field, mapping exception và phân trang |
| Retry/timeout | Mặc định SDK và cấu hình HTTP/client có thể khác |
| Serialization | Converter và type payload của SQS, JSON schema, header |
| Listener | Concurrency, acknowledgement, failure behavior, visibility timeout |
| Credential/region | Default provider chain, profile, assume-role, workload identity |
| Spring Boot | Java baseline, Spring Framework, `jakarta`, auto-configuration |

## 11. Kết nối lựa chọn dependency với bảo mật và kiểm thử

Bộ thư viện đúng là điều kiện cần cho việc gọi cloud, nhưng **không thay thế kiểm chứng trên môi trường thật**.

### 11.1. Identity và quyền

Đối với một service gửi message SQS và lưu file S3, quyền cần được cấp theo operation thực sự sử dụng, ví dụ `s3:PutObject` trên prefix object đích và `sqs:SendMessage` trên ARN queue. Consumer có thể cần `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:GetQueueAttributes` cùng quyền khác nếu luồng có gọi operation đó. Bucket policy, queue policy và KMS policy cũng có thể ảnh hưởng đến kết quả.

Chọn `spring-cloud-aws-starter-sqs` hay `software.amazon.awssdk:sqs` **không thay đổi quy tắc kiểm tra IAM**. Ở ECS, EKS hoặc EC2, nên chọn credential lấy từ role của workload; khi phát triển cục bộ có thể dùng profile phù hợp. Không lưu access key tĩnh trong repository.

### 11.2. Kiểm thử theo từng tầng

| Tầng | Kiểm chứng được | Chưa bảo đảm |
| --- | --- | --- |
| Build + dependency graph | Version, classpath và tính khả dụng của class ở thời điểm build | AWS IAM/network và hành vi service |
| Unit test | Logic nghiệp vụ, adapter và mapping khi mock SDK/template | Request thật lên S3/SQS |
| Integration test giả lập (ví dụ LocalStack) | Wiring Spring, gọi endpoint, gửi/nhận dữ liệu trong phạm vi mô phỏng | Tất cả đặc tính IAM/KMS, quota, timing và hành vi AWS |
| Smoke test trên AWS riêng | Credential thực tế, role, region, quyền tài nguyên và đường đi end-to-end | Mọi lỗi tải cao hoặc mọi tình huống edge case |

Đặc biệt sau nâng cấp `@SqsListener`, hãy thử consumer ném exception, message được phát lại, xử lý trùng và cơ chế DLQ. Một test chỉ xác nhận context Spring khởi động thành công không chứng minh luồng message vận hành an toàn.

## 12. Ba tình huống lựa chọn thực tế

### Tình huống A: Spring Boot 3.x cần S3 và SQS

- **Chọn:** release AWSpring 3.x **được xác nhận tương thích với bản Boot cụ thể**, import AWSpring BOM, thêm starter S3 và SQS.
- **Thêm SDK trực tiếp:** chỉ module ứng dụng tự dùng `S3Client`, `SqsAsyncClient` hoặc client khác; lấy version theo management đã kiểm tra.
- **Kiểm tra:** resolved dependencies, bean tạo được, credentials/region, test upload S3 và xử lý lại message SQS.

### Tình huống B: Java CLI chỉ dùng S3

- **Chọn:** AWS SDK for Java 2.x với `software.amazon.awssdk:bom` và module `s3`.
- **Không cần:** Spring Boot hoặc AWSpring nếu chương trình không dùng Spring.
- **Kiểm tra:** credential provider, region, permission và cách đóng client/network resource.

### Tình huống C: Spring Boot 2.x dùng Spring Cloud AWS và SDK 1.x

- **Không nâng tùy tiện:** riêng một starter hoặc module SDK lên 3.x/2.x khi các phần còn lại vẫn cũ.
- **Chọn:** lộ trình nâng Spring Boot/JDK và AWSpring đồng bộ theo compatibility; migrate import và cấu hình theo release.
- **Kiểm tra:** graph có legacy dependency nào còn sót, test lại S3/SQS, Spring context và hoạt động production giả lập.

## 13. Bài tập thực hành

Một nhóm có dự án Spring Boot đang triển khai dịch vụ xử lý hồ sơ:

- Người dùng upload hồ sơ lên **S3**.
- Dịch vụ tạo message thông báo lên **SQS**.
- Consumer dùng `@SqsListener` lấy message và lưu trạng thái xử lý.
- Một số API thông tin AWS cần truy cập qua client SDK trực tiếp.
- Secret được lưu tại **Secrets Manager**, role của workload có IAM policy tối thiểu.

**Yêu cầu:**

1. Ghi lại version Java, Spring Boot và AWSpring mục tiêu; chỉ rõ **nguồn tương thích** cần tra trước khi chốt release.
2. Viết dependency Maven hoặc Gradle với BOM AWSpring và các starter cần thiết. Nếu mã tự import SDK client, khai báo module SDK phù hợp; giải thích vì sao không gắn version riêng bừa bãi.
3. Chỉ ra group và package nào giúp nhận ra SDK Java v1 và v2 trong dependency tree.
4. Nêu tác động nếu một library legacy kéo `com.amazonaws:aws-java-sdk-s3` nhưng mã mới dùng `software.amazon.awssdk:s3`. Đề xuất cách di trú có kiểm soát.
5. Thiết kế kiểm tra cho lỗi `NoSuchMethodError`, lỗi thiếu `SqsTemplate` và lỗi `AccessDenied`; phân loại từng lỗi theo dependency, Spring auto-configuration hay IAM.
6. Viết ba mức kiểm thử: unit test adapter, integration test với S3/SQS giả lập, smoke test bằng role và tài nguyên AWS dành riêng; nêu giới hạn từng mức.

**Gợi ý tự đánh giá:** Một bài làm tốt có **phiên bản cụ thể được kiểm tra tương thích**, BOM đóng vai trò quản lý version, starter chỉ được thêm theo nhu cầu, SDK generation nhất quán và kế hoạch xác minh classpath lẫn IAM. Nếu chỉ trình bày được vài dòng dependency mà không giải thích lý do chọn hoặc cách kiểm tra, bài làm chưa hoàn tất.

## 14. Tổng kết

Khi tích hợp Spring Boot với AWS, chọn thư viện theo trình tự **baseline Java/Spring Boot → release AWSpring tương thích → BOM → starter theo use case → module AWS SDK cần thiết → kiểm tra dependency graph và runtime**. Spring Cloud AWS 3.x sử dụng AWS SDK for Java 2.x; mã cũ dùng `com.amazonaws` và `AmazonS3` cần lộ trình di trú rõ ràng. BOM giúp các module cùng đi theo một bộ version, starter đưa khả năng tích hợp vào Spring, còn IAM, networking, hành vi S3/SQS và kiểm thử thực tế vẫn là trách nhiệm thiết kế và vận hành của hệ thống.
