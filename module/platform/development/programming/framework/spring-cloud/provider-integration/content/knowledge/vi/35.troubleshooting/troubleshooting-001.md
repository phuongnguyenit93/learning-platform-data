# Không tạo được bean do điều kiện auto-configuration hoặc dependency thiếu

Một ứng dụng Spring Boot có thể biên dịch thành công nhưng khi chạy lại không tìm thấy bean như S3Client, SqsTemplate, ServiceBusClientBuilder, BlobServiceClient, PubSubTemplate hoặc Storage. Nguyên nhân thường nằm ở cách Spring Boot quyết định có đăng ký auto-configuration hay không và những thư viện nào thực sự có trên runtime classpath.

Spring Boot không tự tạo tất cả bean cho mọi dịch vụ cloud. Auto-configuration chỉ đăng ký một cấu hình khi các điều kiện của nó thỏa mãn. Starter của từng provider cũng được chia theo module: thêm AWS SDK S3, Azure SDK Blob hoặc Google Cloud Java Storage trực tiếp chưa chắc đã thêm Spring auto-configuration tương ứng.

Bài này trình bày cách phân biệt bean không được đăng ký với bean khởi tạo thất bại, đọc ConditionEvaluationReport, kiểm tra dependency graph và BOM, tìm điều kiện khiến cấu hình bị bỏ qua, sau đó xử lý ví dụ trên AWS, Azure và Google Cloud.

## 1. Nhận diện đúng loại lỗi trước khi sửa

Thông báo lỗi có chữ “bean” chưa đủ để kết luận auto-configuration không chạy. Cần xem bean có bị bỏ qua, không được tìm thấy, hay đã được tạo nhưng lỗi trong quá trình khởi tạo.

| Triệu chứng | Ý nghĩa thường gặp | Hướng kiểm tra đầu tiên |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Context không có bean phù hợp với kiểu hoặc tên đang yêu cầu | Kiểm tra dependency, condition report, component scan và bean name |
| `No qualifying bean of type ... available` | Không tìm được bean thỏa kiểu hoặc qualifier | Kiểm tra kiểu thực tế, `@Qualifier`, điều kiện auto-configuration |
| `UnsatisfiedDependencyException` | Bean phụ thuộc không được resolve hoặc một bean phụ thuộc khởi tạo lỗi | Đọc chuỗi `Caused by` sâu nhất |
| `BeanCreationException` | Spring đã thử tạo bean nhưng factory method/constructor/init thất bại | Kiểm tra nguyên nhân gốc, property, endpoint, credentials |
| `NoClassDefFoundError` | Class cần thiết có lúc compile nhưng không có trên runtime classpath, hoặc phiên bản không tương thích | Kiểm tra runtime dependency tree và exclusions |
| `NoSuchMethodError` | Class có mặt nhưng phiên bản API không tương thích với thư viện gọi nó | Kiểm tra BOM và phiên bản dependency bị override |
| ApplicationContext khởi động được nhưng không có integration bean | Auto-configuration không match hoặc module chưa được bật/đưa vào classpath | Đọc report và dependency graph |

Ví dụ, nếu constructor của service yêu cầu `SqsTemplate` nhưng context không có bean đó, đây có thể là lỗi thiếu starter SQS hoặc điều kiện SQS không match. Nếu `SqsTemplate` đã được đăng ký nhưng `SqsAsyncClient` không thể lấy region, lỗi sẽ xuất hiện trong lúc tạo bean và thường có `BeanCreationException` hoặc nguyên nhân SDK sâu hơn.

**Quy tắc đầu tiên:** đừng thêm credentials, IAM role hoặc endpoint một cách ngẫu nhiên khi chưa biết bean có được đăng ký hay chưa. IAM thường ảnh hưởng đến lời gọi API lúc chạy; nó không phải nguyên nhân phổ biến khiến một bean client không được đăng ký vào Spring context.

## 2. Auto-configuration quyết định tạo bean như thế nào?

`@SpringBootApplication` bao gồm `@EnableAutoConfiguration`. Spring Boot tìm các lớp auto-configuration được khai báo bởi các thư viện trên classpath, đánh giá điều kiện của chúng rồi đăng ký các bean phù hợp.

Auto-configuration thường được đóng gói trong starter hoặc thư viện tích hợp. Khi thêm starter cho một dịch vụ, ứng dụng nhận được các module cần thiết và Spring Boot có thể phát hiện cấu hình tương ứng. Nếu chỉ thêm SDK nền tảng, ứng dụng có thể gọi API bằng cách tự tạo client, nhưng không nhất thiết có bean Spring được cấu hình sẵn.

### 2.1. Những điều kiện thường gặp

| Annotation | Spring kiểm tra điều gì? | Ví dụ nguyên nhân bean không xuất hiện |
| --- | --- | --- |
| `@ConditionalOnClass` | Class được yêu cầu có trên classpath không? | Thiếu Azure Blob SDK hoặc AWS SQS module |
| `@ConditionalOnMissingClass` | Một class có vắng mặt không? | Một integration bị tắt khi thư viện xung đột có mặt |
| `@ConditionalOnBean` | Bean phụ thuộc đã được đăng ký chưa? | Cấu hình template chỉ chạy khi có client bean |
| `@ConditionalOnMissingBean` | Đã có bean cùng kiểu/tên hay chưa? | Bean mặc định tự nhường chỗ cho bean ứng dụng |
| `@ConditionalOnProperty` | Property có tồn tại và có giá trị phù hợp không? | Module bị tắt bằng property hoặc giá trị cấu hình sai |
| `@ConditionalOnResource` | Resource/file được yêu cầu có tồn tại không? | Thiếu file cấu hình hoặc metadata |
| `@ConditionalOnWebApplication` | Context có phải ứng dụng web đúng loại không? | Cấu hình chỉ dành cho servlet app nhưng chạy reactive/non-web |
| `@ConditionalOnSingleCandidate` | Có đúng một bean phù hợp hoặc một bean primary không? | Có nhiều client cùng kiểu nhưng không có primary |
| `@ConditionalOnExpression` | Biểu thức SpEL có trả về true không? | Placeholder hoặc biểu thức điều kiện không thỏa |
| `@Profile` | Profile được kích hoạt có khớp không? | Bean chỉ khai báo trong profile cloud nhưng chạy local |

Các điều kiện có thể được đặt ở cấp lớp cấu hình hoặc từng phương thức `@Bean`. Nếu condition ở cấp lớp không match, các bean trong lớp cấu hình đó không được đăng ký. Nếu condition ở cấp phương thức không match, chỉ bean tương ứng bị bỏ qua.

### 2.2. Điều kiện classpath

Ví dụ một cấu hình yêu cầu AWS SQS client:

```java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "software.amazon.awssdk.services.sqs.SqsAsyncClient")
class SqsClientConfiguration {

    @Bean
    SqsAsyncClient sqsAsyncClient() {
        return SqsAsyncClient.builder().build();
    }
}
```

Nếu class `SqsAsyncClient` không có trên runtime classpath, Spring Boot có thể bỏ qua cấu hình này. Không có bean `SqsAsyncClient` để inject.

Điều kiện class trên lớp cấu hình được xử lý an toàn hơn so với việc tham chiếu trực tiếp kiểu class thiếu trong chữ ký của phương thức `@Bean`. Khi viết auto-configuration riêng, nên cô lập cấu hình phụ thuộc SDK trong một lớp có `@ConditionalOnClass`.

### 2.3. Điều kiện property

Ví dụ:

```java
@Configuration(proxyBeanMethods = false)
class StorageConfiguration {

    @Bean
    @ConditionalOnProperty(
            prefix = "app.storage",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false)
    StorageFacade storageFacade() {
        return new StorageFacade();
    }
}
```

Bean chỉ xuất hiện khi `app.storage.enabled=true`. Nếu property bị thiếu hoặc giá trị là `false`, method không được gọi.

Với `@ConditionalOnProperty`, khi không chỉ định `havingValue`, mặc định property phải tồn tại và không có giá trị chuỗi `false`. `matchIfMissing` mặc định là `false`. Khi có nhiều tên trong `name`, tất cả điều kiện phải match.

Đừng nhầm property bật/tắt integration với property credentials. Ví dụ một module có thể được bật nhưng client không tạo được do thiếu region; hoặc module có đủ dependency nhưng bị tắt bởi property.

### 2.4. Điều kiện bean phụ thuộc

Một bean có thể phụ thuộc vào bean khác:

```java
@Bean
@ConditionalOnBean(SqsAsyncClient.class)
@ConditionalOnMissingBean
SqsTemplate sqsTemplate(SqsAsyncClient client) {
    return SqsTemplate.newTemplate(client);
}
```

Nếu `SqsAsyncClient` không có, `SqsTemplate` cũng không được đăng ký. Khi đọc condition report, hãy truy ngược chuỗi điều kiện từ bean mong muốn về bean nền tảng đầu tiên bị thiếu.

Spring Boot khuyến nghị dùng `@ConditionalOnBean` và `@ConditionalOnMissingBean` trên các lớp auto-configuration, vì auto-configuration được xử lý sau các bean definition do người dùng khai báo. Nếu điều kiện phụ thuộc bean được đặt trong một cấu hình ứng dụng thông thường, thứ tự xử lý có thể khiến kết quả khác kỳ vọng.

### 2.5. Bean mặc định tự nhường chỗ

Đây thường là hành vi có chủ đích:

```java
@Bean
@ConditionalOnMissingBean
Clock cloudClock() {
    return Clock.systemUTC();
}
```

Nếu ứng dụng đã khai báo một bean `Clock`, auto-configuration không tạo bean mặc định nữa. Đây không phải lỗi.

Nếu vô tình khai báo một bean cùng kiểu, hoặc một cấu hình test import vào context, bean mặc định của provider có thể biến mất. Hãy kiểm tra bean names và kiểu trả về của method `@Bean` trước khi kết luận starter bị lỗi.

Khi viết custom bean, khai báo kiểu trả về đủ cụ thể để Spring condition có thể đánh giá chính xác. Nếu method trả về một interface quá rộng trong khi auto-configuration kiểm tra concrete type, điều kiện có thể không hoạt động như dự kiến.

## 3. Phân biệt starter, SDK và module auto-configuration

Mỗi provider có cách đóng gói thư viện riêng. Cần biết dependency đang thêm vào là SDK, module tích hợp Spring hay starter có auto-configuration.

| Provider | Ví dụ dependency starter theo dịch vụ | Vai trò |
| --- | --- | --- |
| AWS | `io.awspring.cloud:spring-cloud-aws-starter-s3` | Thêm tích hợp Spring Cloud AWS cho S3 và auto-configure client tương ứng |
| AWS | `io.awspring.cloud:spring-cloud-aws-starter-sqs` | Thêm tích hợp SQS, gồm các thành phần như `SqsTemplate` theo release tương ứng |
| Azure | `com.azure.spring:spring-cloud-azure-starter-storage-blob` | Thêm auto-configuration và tích hợp Azure Blob Storage |
| Azure | `com.azure.spring:spring-cloud-azure-starter-servicebus` | Thêm tích hợp Azure Service Bus |
| Google Cloud | `com.google.cloud:spring-cloud-gcp-starter-storage` | Thêm tích hợp Spring với Cloud Storage |
| Google Cloud | `com.google.cloud:spring-cloud-gcp-starter-pubsub` | Thêm tích hợp Spring với Pub/Sub |
| Google Cloud | `com.google.cloud:spring-cloud-gcp-starter-data-spanner` | Thêm tích hợp Spring Data với Spanner |

Các artifact là ví dụ của từng release line; kiểm tra BOM và tài liệu đúng phiên bản trước khi sử dụng. Starter thường kéo theo module tích hợp và dependency cần thiết. Nếu chỉ thêm SDK, ví dụ `software.amazon.awssdk:s3`, `com.azure:azure-storage-blob` hoặc `com.google.cloud:google-cloud-storage`, bạn có thể tự tạo client bằng SDK, nhưng không nên mặc định rằng Spring sẽ cung cấp template hay bean tích hợp.

### 3.1. Starter không đồng nghĩa một starter cho toàn bộ provider

Ví dụ với Google Cloud:

- `spring-cloud-gcp-starter` cung cấp các thành phần Core như project ID và credentials provider.
- `spring-cloud-gcp-starter-pubsub` mới đưa module Pub/Sub vào ứng dụng.
- `spring-cloud-gcp-starter-storage` mới đưa module Storage vào ứng dụng.

Thêm Core starter không có nghĩa `PubSubTemplate` hoặc `Storage` đã được cấu hình. Từng dịch vụ cần module tương ứng.

Với Azure, `spring-cloud-azure-starter` là starter Core; muốn tích hợp Service Bus, Blob Storage, Cosmos DB hoặc Key Vault thì thêm starter của dịch vụ tương ứng.

Với AWS, Spring Cloud AWS cũng chia starter theo dịch vụ. S3 starter và SQS starter kích hoạt những nhóm auto-configuration khác nhau.

### 3.2. BOM giữ các phiên bản tương thích

Không tự chọn version riêng cho từng starter nếu provider cung cấp BOM. BOM quản lý các phiên bản Spring integration và SDK đã được kiểm thử cùng nhau.

Ví dụ Maven cho một module AWS:

```xml
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
        <artifactId>spring-cloud-aws-starter-sqs</artifactId>
    </dependency>
</dependencies>
```

Ví dụ Maven cho Azure:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.azure.spring</groupId>
            <artifactId>spring-cloud-azure-dependencies</artifactId>
            <version>${spring-cloud-azure.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.azure.spring</groupId>
        <artifactId>spring-cloud-azure-starter-servicebus</artifactId>
    </dependency>
</dependencies>
```

Ví dụ Maven cho Google Cloud:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>com.google.cloud</groupId>
            <artifactId>spring-cloud-gcp-dependencies</artifactId>
            <version>${spring-cloud-gcp.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>com.google.cloud</groupId>
        <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
    </dependency>
</dependencies>
```

Không sao chép version của một ví dụ cũ vào ứng dụng hiện tại. Hãy đối chiếu ma trận tương thích giữa Spring Boot, Spring Cloud release train và BOM của provider. Một BOM quản lý dependency của provider không tự đảm bảo tương thích với mọi Spring Boot version.

## 4. Đọc ConditionEvaluationReport để biết bean bị bỏ qua vì sao

Spring Boot tạo `ConditionEvaluationReport` trong quá trình khởi động. Report ghi lại auto-configuration nào match, không match và lý do.

### 4.1. Bật debug khi khởi động

Chạy JAR với tham số `--debug`:

```bash
java -jar build/libs/orders-api.jar --debug
```

Hoặc chạy bằng Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments=--debug
```

Hoặc đặt JVM system property trước `-jar`:

```bash
java -Ddebug=true -jar build/libs/orders-api.jar
```

Spring Boot sẽ in condition evaluation report ra log. Tìm tên auto-configuration hoặc tên bean liên quan, sau đó đọc phần positive matches và negative matches.

Có thể tăng log riêng cho auto-configuration:

```yaml
logging:
  level:
    org.springframework.boot.autoconfigure: DEBUG
```

Không bật debug toàn bộ ứng dụng trong production lâu dài. Report có thể chứa tên class, property và thông tin cấu hình hữu ích cho người vận hành; thu thập log ở môi trường kiểm soát và không gửi secrets vào log.

### 4.2. Dùng Actuator conditions endpoint

Nếu ứng dụng có Spring Boot Actuator, endpoint `conditions` hiển thị condition report dưới dạng JSON.

Dependency Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-actuator</artifactId>
</dependency>
```

Cấu hình expose endpoint trong môi trường phát triển:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: health,info,conditions
```

Sau khi ứng dụng chạy:

```http
GET /actuator/conditions
```

Endpoint này có thể tiết lộ thông tin về cấu hình nội bộ. Chỉ expose trong local/dev hoặc sau lớp bảo vệ truy cập phù hợp; không mở công khai trên Internet chỉ để debug.

### 4.3. Cách đọc report

Một auto-configuration có thể xuất hiện ở phần positive match nếu điều kiện được thỏa. Nếu không match, report thường nêu một trong các lý do:

- Required class was not found: thiếu class/dependency.
- A bean of type ... was not found: bean phụ thuộc chưa được đăng ký.
- A bean of type ... was found: điều kiện `@ConditionalOnMissingBean` không còn thỏa vì đã có bean khác.
- Property ... did not find property ...: property bị thiếu.
- Property ... found different value: property có giá trị không đúng `havingValue`.
- Not a web application: context không phải ứng dụng web theo yêu cầu.
- Excluded by ...: cấu hình bị loại trừ hoặc không được import.

Đừng chỉ tìm tên bean trong report. Hãy tìm auto-configuration chứa bean đó, rồi xem các condition ở cấp lớp và từng method. Nếu cấu hình cha không match, các bean con sẽ không được tạo dù condition riêng của chúng có thể đúng.

## 5. Quy trình chẩn đoán theo thứ tự

Dùng quy trình sau để thu hẹp nguyên nhân. Thực hiện từng bước và ghi lại kết quả trước khi thay đổi dependency hoặc property.

### Bước 1 — Xác nhận bean đang cần tìm

Xác định chính xác:

- Kiểu bean cần inject.
- Tên bean nếu đang dùng `@Qualifier` hoặc `@Resource`.
- Module cloud chịu trách nhiệm cung cấp bean.
- Profile và cấu hình đang được kích hoạt.

Ví dụ, `SqsTemplate`, `SqsAsyncClient`, `S3Client`, `PubSubTemplate` và `Storage` là các kiểu khác nhau. Có client SDK không có nghĩa có Spring template, và ngược lại.

Có thể in các bean names theo kiểu trong một đoạn chẩn đoán tạm thời:

```java
import org.springframework.context.ApplicationContext;
import org.springframework.stereotype.Component;

@Component
public class BeanInventory {

    private final ApplicationContext context;

    public BeanInventory(ApplicationContext context) {
        this.context = context;
    }

    public void printStorageBeans() {
        String[] names = context.getBeanNamesForType(
                com.google.cloud.storage.Storage.class);

        for (String name : names) {
            System.out.println("Storage bean: " + name);
        }
    }
}
```

Chỉ log tên bean và kiểu; không log credentials hoặc token. Xóa đoạn chẩn đoán tạm sau khi hoàn tất.

### Bước 2 — Kiểm tra starter có trên runtime classpath

Kiểm tra dependency của đúng module đang chạy. Với Maven:

```bash
./mvnw dependency:tree -Dincludes="io.awspring.cloud:*,com.azure.spring:*,com.google.cloud:*"
```

Có thể lọc riêng một artifact:

```bash
./mvnw dependency:tree -Dincludes=com.google.cloud:spring-cloud-gcp-starter-pubsub
```

Với Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Kiểm tra một dependency cụ thể:

```bash
./gradlew dependencyInsight --dependency spring-cloud-gcp-starter-pubsub --configuration runtimeClasspath
```

Nếu chạy test, xem thêm `testRuntimeClasspath`. Dependency chỉ nằm trong `testImplementation` hoặc Maven `test` scope không có mặt khi chạy ứng dụng production.

Khi kiểm tra riêng Pub/Sub, property `spring.cloud.gcp.pubsub.enabled` điều khiển auto-configuration của module và mặc định là `true` trong reference hiện hành. Nếu property được đặt thành `false`, starter vẫn có thể nằm trên classpath nhưng Pub/Sub auto-configuration sẽ không tạo các bean tương ứng.

### Bước 3 — Kiểm tra dependency bị loại trừ hoặc đặt sai scope

Tìm các trường hợp:

- Starter được khai báo ở module Gradle khác, không phải module tạo executable JAR.
- Dependency dùng scope `test`, `provided` hoặc `optional` không đúng mục đích.
- Parent POM hoặc dependency management loại trừ một SDK transitive.
- Gradle dùng `compileOnly` cho thư viện cần ở runtime.
- Dependency bị exclude từ một starter tổng hợp.
- Build profile chỉ thêm starter ở một môi trường khác.
- Fat JAR hoặc container image được build từ artifact cũ.

Nếu starter có trong `compileClasspath` nhưng không có trong `runtimeClasspath`, Spring Boot có thể biên dịch được nhưng không đăng ký auto-configuration lúc chạy.

### Bước 4 — Đọc condition report

Chạy ứng dụng với `--debug` hoặc dùng Actuator `conditions`. Tìm:

1. Auto-configuration của dịch vụ.
2. Condition cấp lớp.
3. Condition của bean cần inject.
4. Bean phụ thuộc mà condition yêu cầu.
5. Property bật/tắt module.

Khi report nói class thiếu, quay lại bước 2. Khi report nói property không match, kiểm tra property source và profile. Khi report nói bean đã tồn tại, tìm bean do ứng dụng hoặc thư viện khác đăng ký.

### Bước 5 — Kiểm tra property binding và profile

Property có thể đến từ:

- `application.yml` và `application-{profile}.yml`.
- Environment variables.
- JVM system properties.
- Command-line arguments.
- Config Server hoặc external config.
- Test property sources.

Kiểm tra profile thực tế:

```bash
java -jar build/libs/orders-api.jar --spring.profiles.active=dev --debug
```

Tên property cần đúng prefix của module và đúng release line. Ví dụ, `spring.cloud.gcp.pubsub.enabled` và `spring.cloud.gcp.core.enabled` là hai cấu hình khác nhau; không giả định tắt Core cũng tắt toàn bộ module GCP hoặc ngược lại. Với provider khác, kiểm tra reference documentation để xác nhận tên property và default value.

### Bước 6 — Kiểm tra bean override và loại bean

Nếu report cho thấy `@ConditionalOnMissingBean` không match:

- Tìm bean cùng kiểu trong code ứng dụng.
- Tìm `@TestConfiguration` được import ngoài dự kiến.
- Kiểm tra `@Primary`, `@Qualifier` và tên bean.
- Kiểm tra method `@Bean` trả về interface hay concrete class.
- Xác định bean tùy chỉnh có thực sự thay thế bean mặc định hay không.

Nếu bean đã tồn tại nhưng injection vẫn thất bại, vấn đề có thể là qualifier, kiểu không tương thích hoặc nhiều candidate mà không có primary; đó không còn là lỗi auto-configuration bị bỏ qua.

### Bước 7 — Kiểm tra tương thích phiên bản

Nếu class có mặt nhưng gặp `NoSuchMethodError`, `NoClassDefFoundError`, `LinkageError` hoặc lỗi binding:

- Xem dependency tree để tìm nhiều phiên bản của cùng SDK.
- Kiểm tra provider BOM có được import không.
- Kiểm tra Spring Boot và Spring Cloud release train.
- Kiểm tra dependency bị override thủ công.
- Xác nhận Java version mà release line yêu cầu.
- Xóa output build cũ và đóng gói lại artifact sau khi sửa dependency.

Không giải quyết xung đột bằng cách nâng riêng một SDK ngẫu nhiên. Hãy dùng BOM tương thích hoặc override có chủ đích sau khi kiểm tra release notes.

## 6. Ví dụ theo provider

### 6.1. AWS: không có SqsTemplate

Giả sử service có constructor:

```java
@Service
public class OrderPublisher {

    private final SqsTemplate sqsTemplate;

    public OrderPublisher(SqsTemplate sqsTemplate) {
        this.sqsTemplate = sqsTemplate;
    }
}
```

Các bước kiểm tra:

1. Xác nhận dependency `io.awspring.cloud:spring-cloud-aws-starter-sqs` có trong runtime classpath.
2. Kiểm tra Spring Cloud AWS BOM và AWS SDK version.
3. Bật `--debug` và tìm SQS auto-configuration.
4. Kiểm tra có custom `SqsAsyncClient` hoặc `SqsTemplate` bean khiến cấu hình mặc định back off không.
5. Nếu SQS client bean đã được tạo nhưng lỗi khởi tạo, kiểm tra AWS region và credential provider chain.

Ví dụ khai báo dependency:

```xml
<dependency>
    <groupId>io.awspring.cloud</groupId>
    <artifactId>spring-cloud-aws-starter-sqs</artifactId>
</dependency>
```

Starter SQS cung cấp auto-configuration cho tích hợp SQS. Chỉ thêm AWS SDK SQS module có thể cho phép tự tạo `SqsAsyncClient`, nhưng không thay thế starter nếu ứng dụng đang mong đợi `SqsTemplate` do Spring Cloud AWS tạo.

**Phân biệt lỗi:** thiếu starter thường làm SQS auto-configuration không xuất hiện. Thiếu region hoặc credentials thường làm quá trình tạo client thất bại. Thiếu IAM permission thường chỉ xuất hiện khi gọi SQS API và trả lỗi authorization.

### 6.2. Azure: không có bean cho Service Bus hoặc Blob Storage

Với Azure, xác nhận starter đúng dịch vụ:

```xml
<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-servicebus</artifactId>
</dependency>

<dependency>
    <groupId>com.azure.spring</groupId>
    <artifactId>spring-cloud-azure-starter-storage-blob</artifactId>
</dependency>
```

Kiểm tra BOM `spring-cloud-azure-dependencies` và phiên bản Spring Boot được hỗ trợ. Starter của Azure bao gồm các dependency và logic auto-configuration cần cho module tương ứng. Chỉ thêm Azure SDK client library có thể cần code builder thủ công thay vì bean tích hợp Spring.

Khi condition report cho thấy module không được đăng ký:

- Kiểm tra starter có nằm trong runtime classpath.
- Kiểm tra class của Azure SDK mà auto-configuration yêu cầu.
- Kiểm tra property bật/tắt module và profile.
- Kiểm tra có custom bean cùng kiểu khiến auto-configuration nhường chỗ.

Nếu bean client đã được tạo nhưng kết nối thất bại, kiểm tra tenant, managed identity, credential chain, endpoint, namespace, quyền data-plane và network. Azure subscription role hoặc quyền quản trị control-plane không tự động thay thế quyền data-plane trên Service Bus/Storage.

### 6.3. Google Cloud: có Core nhưng không có PubSubTemplate

Ví dụ ứng dụng có dependency Core:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter</artifactId>
</dependency>
```

Core starter cung cấp project ID và credentials provider. Để dùng Pub/Sub integration, thêm starter dịch vụ:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-pubsub</artifactId>
</dependency>
```

Để dùng Cloud Storage integration, thêm:

```xml
<dependency>
    <groupId>com.google.cloud</groupId>
    <artifactId>spring-cloud-gcp-starter-storage</artifactId>
</dependency>
```

Nếu `PubSubTemplate` không có:

1. Xác nhận starter Pub/Sub, không chỉ Core starter, có trong runtime classpath.
2. Kiểm tra BOM Spring Framework on Google Cloud.
3. Tìm Pub/Sub auto-configuration trong condition report.
4. Kiểm tra property `spring.cloud.gcp.pubsub.enabled` theo đúng phiên bản đang dùng.
5. Kiểm tra custom `CredentialsProvider`, `PublisherFactory` hoặc `SubscriberFactory` nếu có.

Nếu `PubSubTemplate` đã tồn tại nhưng publish bị từ chối, lúc đó kiểm tra ADC principal, project/topic resource name và IAM role Publisher. IAM không phải bước đầu tiên khi bean còn chưa được đăng ký.

## 7. Các lỗi phổ biến và cách khắc phục

| Nguyên nhân | Dấu hiệu trong report/log | Cách khắc phục |
| --- | --- | --- |
| Thiếu service starter | Auto-configuration không xuất hiện hoặc class condition không match | Thêm starter đúng dịch vụ |
| Chỉ thêm SDK thuần | SDK client có thể tạo thủ công nhưng không có Spring template/bean | Thêm starter hoặc tự khai báo `@Bean` có chủ đích |
| Thiếu transitive class | `@ConditionalOnClass` không match hoặc `NoClassDefFoundError` | Kiểm tra dependency tree, exclusions và runtime scope |
| Module bị tắt bằng property | Property condition không match | Kiểm tra prefix, giá trị và property source |
| Dùng sai profile | Bean nằm trong cấu hình profile khác | Kiểm tra `spring.profiles.active` và file profile |
| Auto-configuration bị exclude | Report không có cấu hình mong đợi hoặc ghi nhận exclusion | Kiểm tra `exclude`, `excludeName` và `spring.autoconfigure.exclude` |
| Bean tùy chỉnh làm auto-config back off | `@ConditionalOnMissingBean` không match | Xác định bean tùy chỉnh có chủ đích hay vô tình |
| Thiếu bean nền tảng | `@ConditionalOnBean` không match | Tìm bean đầu tiên bị thiếu và điều kiện tạo nó |
| Nhiều bean cùng kiểu | `NoUniqueBeanDefinitionException` hoặc candidate không rõ | Dùng `@Primary` hoặc `@Qualifier` |
| BOM không tương thích | `NoSuchMethodError`, `ClassNotFoundException`, binding lỗi | Đồng bộ Spring Boot, Spring Cloud và provider BOM |
| Dependency chỉ có ở test | Test chạy được nhưng JAR production thiếu bean | Đưa starter vào runtime dependency |
| Thiếu region/endpoint | Bean client thất bại lúc khởi tạo | Cấu hình region/endpoint theo provider |
| Thiếu credentials | Client builder hoặc credential provider ném exception | Dùng identity/ADC/managed identity/role phù hợp |
| IAM thiếu quyền | Bean tồn tại, API trả 401/403 hoặc access denied | Cấp permission data-plane đúng resource |
| Network hoặc DNS lỗi | Bean tồn tại, request timeout hoặc không resolve endpoint | Kiểm tra route, firewall, DNS, proxy và private endpoint |

## 8. Kiểm tra cấu hình loại trừ auto-configuration

Auto-configuration có thể bị loại trừ bằng annotation:

```java
@SpringBootApplication(
        exclude = SomeCloudAutoConfiguration.class)
public class OrdersApplication {
}
```

Hoặc bằng tên class trong property:

```yaml
spring:
  autoconfigure:
    exclude:
      - com.example.cloud.SomeCloudAutoConfiguration
```

Khi bean provider không xuất hiện, tìm cấu hình exclude trong:

- `@SpringBootApplication` hoặc `@EnableAutoConfiguration`.
- `spring.autoconfigure.exclude` trong YAML/properties.
- Property được truyền từ command line hoặc environment.
- Cấu hình test hoặc module dùng chung.

Chỉ bỏ exclusion nếu integration thực sự cần thiết. Một số ứng dụng loại trừ auto-configuration để tự quản lý client, tránh xung đột hoặc không dùng dịch vụ đó.

## 9. Viết kiểm thử để xác nhận điều kiện auto-configuration

Nếu đội ngũ đang phát triển starter hoặc cấu hình dùng chung, nên kiểm tra điều kiện bằng `ApplicationContextRunner`. Công cụ này tạo một context nhỏ, cho phép thêm property, thêm bean hoặc loại class khỏi classpath mà không phải khởi động toàn bộ ứng dụng.

Ví dụ kiểm tra một auto-configuration tạo bean khi property được bật:

```java
class StorageFacadeAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    StorageFacadeAutoConfiguration.class));

    @Test
    void createsStorageFacadeWhenEnabled() {
        contextRunner
                .withPropertyValues("app.storage.enabled=true")
                .run(context -> {
                    assertThat(context)
                            .hasSingleBean(StorageFacade.class);
                });
    }

    @Test
    void doesNotCreateStorageFacadeWhenDisabled() {
        contextRunner
                .withPropertyValues("app.storage.enabled=false")
                .run(context -> {
                    assertThat(context)
                            .doesNotHaveBean(StorageFacade.class);
                });
    }
}
```

Cần các dependency test phù hợp với Spring Boot version, thường là `spring-boot-starter-test`.

### 9.1. Kiểm thử classpath thiếu

Spring Boot cung cấp `FilteredClassLoader` để mô phỏng trường hợp class không có trên runtime classpath:

```java
@Test
void disablesIntegrationWhenSdkClassIsMissing() {
    contextRunner
            .withClassLoader(
                    new FilteredClassLoader(RequiredCloudClient.class))
            .run(context -> {
                assertThat(context)
                        .doesNotHaveBean(StorageFacade.class);
            });
}
```

Bài test này xác nhận integration không bị kích hoạt khi SDK class không có. Nó giúp tránh lỗi liên kết class trong starter tùy chỉnh.

### 9.2. In condition report trong test

Có thể thêm listener để in report khi test:

```java
new ApplicationContextRunner()
        .withInitializer(
                ConditionEvaluationReportLoggingListener
                        .forLogLevel(LogLevel.INFO))
        .run(context -> {
            // Assert các bean cần thiết.
        });
```

Nếu auto-configuration chỉ chạy trong servlet hoặc reactive application, dùng `WebApplicationContextRunner` hoặc `ReactiveWebApplicationContextRunner` để mô phỏng đúng loại context.

## 10. Không nhầm lỗi bean với lỗi credentials, IAM và kết nối

Một integration có nhiều giai đoạn:

1. Dependency có trên classpath.
2. Auto-configuration được phát hiện.
3. Conditions match và bean definition được đăng ký.
4. Factory method/constructor tạo client bean.
5. Client lấy credentials, region/project và endpoint.
6. Request được gửi tới cloud service.
7. Provider kiểm tra IAM/RBAC và xử lý request.

Lỗi ở từng giai đoạn có dấu hiệu khác nhau:

| Giai đoạn | Ví dụ lỗi | Câu hỏi cần trả lời |
| --- | --- | --- |
| Classpath | `ClassNotFoundException` | Có starter và SDK đúng trong runtime không? |
| Auto-configuration | Bean không tồn tại | Condition nào không match? |
| Bean creation | `BeanCreationException` | Factory method hoặc property nào làm khởi tạo thất bại? |
| Authentication | Credential unavailable / invalid token | Runtime đang dùng principal nào? |
| Authorization | 401/403 / access denied | Principal có permission trên resource đích không? |
| Network | Timeout / DNS failure | Ứng dụng có kết nối được endpoint không? |
| Resource | Not found / wrong project / region | Tên resource và vị trí có chính xác không? |

Một số SDK trì hoãn việc kết nối tới cloud đến lần gọi đầu tiên. Vì vậy, bean có thể khởi tạo thành công dù IAM hoặc network chưa đúng. Chỉ một integration test gọi API thật mới chứng minh được quyền và kết nối.

## 11. Bài thực hành: tìm lý do không tạo được PubSubTemplate

Mục tiêu: sửa một ứng dụng Spring Boot đã khai báo `PubSubTemplate` trong constructor nhưng context không có bean tương ứng.

### Bước 1 — Xác nhận lỗi

Thông báo:

```text
No qualifying bean of type
'com.google.cloud.spring.pubsub.core.PubSubTemplate' available
```

Ghi lại profile đang chạy và artifact được đóng gói. Chưa thay đổi credentials hoặc IAM.

### Bước 2 — Kiểm tra runtime dependency

Chạy:

```bash
./gradlew dependencyInsight --dependency spring-cloud-gcp-starter-pubsub --configuration runtimeClasspath
```

Nếu không có dependency, thêm starter Pub/Sub vào đúng module ứng dụng. Nếu chỉ có `spring-cloud-gcp-starter`, điều đó chưa đủ để có Pub/Sub integration.

### Bước 3 — Kiểm tra BOM

Xác nhận `spring-cloud-gcp-dependencies` được import và tương thích với Spring Boot release line. Kiểm tra không có version thủ công khác nhau giữa starter và module transitive.

### Bước 4 — Bật condition report

Khởi động:

```bash
java -jar build/libs/orders-api.jar --debug
```

Tìm auto-configuration Pub/Sub và đọc negative match. Nếu class condition không match, kiểm tra dependency. Nếu property condition không match, xác nhận module có bị tắt hay không. Nếu report cho thấy một bean đã tồn tại, kiểm tra custom configuration và bean override.

### Bước 5 — Sửa nguyên nhân tìm được

Nếu thiếu starter, thêm dependency:

```kotlin
dependencies {
    implementation(
        "com.google.cloud:spring-cloud-gcp-starter-pubsub"
    )
}
```

Nếu đã có starter nhưng cấu hình bị tắt, sửa property theo reference của phiên bản đang sử dụng. Nếu có custom bean không mong muốn, điều chỉnh cấu hình đó để auto-configuration có thể tạo bean mặc định.

### Bước 6 — Xác nhận context và API

- Khởi động lại ứng dụng và xác nhận `PubSubTemplate` có trong context.
- Kiểm tra ADC principal và project/topic name.
- Chạy một integration test publish message vào project sandbox.
- Nếu API trả 403, cấp role Publisher cho đúng service account trên topic.
- Nếu API trả lỗi kết nối, kiểm tra endpoint, DNS và network.

Bài thực hành kết thúc khi đã chứng minh được cả hai điều: bean được đăng ký đúng và thao tác API chạy thành công bằng danh tính dự kiến.

## 12. Quy trình ngắn khi gặp lỗi trong môi trường production

Khi production báo thiếu bean sau một lần deploy:

1. So sánh artifact/version đang chạy với bản triển khai trước.
2. Kiểm tra runtime dependency tree hoặc SBOM của artifact.
3. Thu thập condition report từ log khởi động hoặc endpoint đã được bảo vệ.
4. Xác định condition không match hoặc dependency bị thiếu.
5. Kiểm tra property/profile và cấu hình exclude.
6. Kiểm tra thay đổi BOM, dependency scope và image build.
7. Nếu bean đã được tạo, chuyển sang kiểm tra credentials, region, endpoint, IAM và network.
8. Khôi phục dependency/BOM/configuration tương thích, build artifact mới và triển khai theo quy trình release.

Không expose Actuator conditions công khai để điều tra production. Nếu endpoint chưa được bảo vệ, dùng startup debug logs trong lần tái hiện có kiểm soát hoặc tạo bản chẩn đoán đã loại bỏ thông tin nhạy cảm.

## 13. Ghi nhớ

- `NoSuchBeanDefinitionException` thường có nghĩa context không có bean phù hợp; `BeanCreationException` thường có nghĩa Spring đã thử tạo bean nhưng khởi tạo thất bại.
- Auto-configuration chỉ chạy khi các điều kiện như classpath, bean, property, resource, profile và loại application context thỏa mãn.
- `@ConditionalOnClass` thường chỉ ra dependency thiếu; `@ConditionalOnProperty` thường chỉ ra property hoặc profile; `@ConditionalOnBean` yêu cầu bean nền tảng; `@ConditionalOnMissingBean` cho phép ứng dụng thay bean mặc định.
- Starter theo dịch vụ thường cung cấp cả module tích hợp và auto-configuration. SDK thuần có thể đủ để tự tạo client nhưng không tự tạo các Spring template/bean.
- AWS, Azure và Google Cloud đều chia starter theo dịch vụ; Core starter của provider không đồng nghĩa mọi service integration đã được đưa vào ứng dụng.
- Dùng BOM của provider và đối chiếu với Spring Boot/Spring Cloud compatibility matrix; không override SDK version tùy tiện.
- Bật `--debug` hoặc dùng Actuator `/actuator/conditions` để đọc `ConditionEvaluationReport`.
- Kiểm tra `runtimeClasspath`, dependency exclusions, scope, profile, auto-configuration exclusions và bean override.
- Credentials, region, endpoint, IAM/RBAC và network thường ảnh hưởng giai đoạn tạo client hoặc gọi API; chúng không phải nguyên nhân đầu tiên của một bean definition vắng mặt.
- Dùng `ApplicationContextRunner` và `FilteredClassLoader` để kiểm thử các điều kiện của auto-configuration.

## Tài liệu tham khảo chính thức

1. [Spring Boot — Troubleshoot Auto-configuration](https://docs.spring.io/spring-boot/how-to/application.html)
2. [Spring Boot — Creating Your Own Auto-configuration và condition annotations](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
3. [Spring Boot — Auto-configuration classes](https://docs.spring.io/spring-boot/appendix/auto-configuration-classes/)
4. [Spring Boot — Build Systems và starter dependencies](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
5. [Spring Cloud AWS 3.4 — BOM, starter dependencies và auto-configuration](https://docs.awspring.io/spring-cloud-aws/docs/3.4.0/reference/html/index.html)
6. [Spring Cloud AWS — SQS starter và SqsTemplate](https://docs.awspring.io/spring-cloud-aws/docs/3.4.1/reference/html/index.html)
7. [Spring Cloud Azure — Developer Guide, BOM và starter dependencies](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/developer-guide-overview)
8. [Spring Cloud Azure — Auto-configure Azure SDK clients](https://learn.microsoft.com/en-us/azure/developer/java/spring-framework/auto-configure-azure-sdk-clients)
9. [Spring Framework on Google Cloud — Starter dependencies](https://googlecloudplatform.github.io/spring-cloud-gcp/reference/html/)
10. [Spring Framework on Google Cloud Core — Core auto-configuration](https://googlecloudplatform.github.io/spring-cloud-gcp/8.2.0/reference/html/core.html)

Tên starter, property và điều kiện cụ thể phụ thuộc release line. Khi điều tra ứng dụng thực tế, hãy mở tài liệu của đúng phiên bản đang dùng và xem mã nguồn lớp AutoConfiguration tương ứng thay vì dựa vào bài viết hoặc ví dụ của phiên bản khác.
