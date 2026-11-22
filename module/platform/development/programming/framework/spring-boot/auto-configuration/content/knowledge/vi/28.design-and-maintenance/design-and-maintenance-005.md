# Không tạo tài nguyên bên ngoài chỉ để kiểm tra điều kiện kích hoạt

> **Spring Boot Auto Configuration → Thiết kế và bảo trì.** Bài học giải thích vì sao condition của auto-configuration chỉ nên quyết định cấu hình có được áp dụng dựa trên thông tin cấu hình và trạng thái cục bộ đã có. Một condition không nên gọi dịch vụ từ xa, tạo database table, bucket, queue hay topic chỉ để xem tính năng có thể bật hay không. Ví dụ thực hành dùng Spring Boot 3.3.13 và Java 17: feature archive được bật bằng property, client được tạo mà không kết nối mạng, và một transport giả xác nhận không có request nào trong lúc ApplicationContext refresh.

## 1. Nguyên tắc: condition quyết định cấu hình, không quản lý hạ tầng

Auto-configuration trả lời câu hỏi: **với classpath, Environment và các bean definitions hiện có, những bean nào nên được đăng ký?**

Ví dụ:
- Người dùng có bật feature bằng property không?
- Thư viện cần thiết có trên classpath không?
- Một bean nền mà integration cần đã được đăng ký chưa?
- Một file cấu hình có trong classpath hoặc một vị trí resource được Spring hỗ trợ không?
- Ứng dụng là servlet, reactive hay non-web context?

Các câu hỏi này liên quan đến cấu hình và trạng thái mà Spring có thể đánh giá khi xây dựng ApplicationContext.

Một condition không nên tự tạo tài nguyên bên ngoài để trả lời câu hỏi bật/tắt. Ví dụ, đừng tạo bucket S3, database schema, bảng, Kafka topic, message queue, remote tenant hoặc cloud project chỉ để xác định bean có được đăng ký hay không.

Điều đó trộn lẫn ba trách nhiệm khác nhau:

1. **Activation — kích hoạt feature:** quyết định bean/configuration có được đăng ký dựa trên property, classpath, bean definitions và cấu hình hiện có.
2. **Provisioning — cấp phát tài nguyên:** tạo hoặc cập nhật hạ tầng như database, bucket, topic, queue, schema hoặc service account.
3. **Availability — kiểm tra khả năng sử dụng:** xác định dịch vụ bên ngoài đang hoạt động, có thể kết nối và đáp ứng yêu cầu vận hành hay không.

Ba việc có thể liên quan đến cùng một integration, nhưng có vòng đời, quyền truy cập và cách kiểm thử khác nhau. Condition nên làm việc thứ nhất. Provisioning thuộc quy trình quản lý hạ tầng hoặc một hành động khởi tạo được thiết kế rõ ràng. Availability thuộc health/readiness hoặc bước xác minh kết nối có chủ đích.

## 2. Vì sao tạo tài nguyên trong condition là nguy hiểm?

Giả sử một thư viện muốn bật tính năng lưu trữ archive khi bucket đã tồn tại. Một custom condition được viết theo ý tưởng:

~~~java
// ANTI-PATTERN: pseudocode, không phải implementation để sử dụng.
public boolean matches(ConditionContext context,
                       AnnotatedTypeMetadata metadata) {
    return cloudAdmin.createBucketIfMissing("notice-archive");
}
~~~

Condition này vừa kiểm tra trạng thái vừa thay đổi hạ tầng. Việc tạo bucket trở thành tác dụng phụ của quá trình parse cấu hình. Điều đó gây ra nhiều vấn đề.

### 2.1. Khởi động ứng dụng làm thay đổi hạ tầng ngoài dự kiến

Người vận hành chỉ định bật ứng dụng, nhưng quá trình refresh context lại tạo bucket hoặc topic. Một thay đổi cấu hình tưởng như vô hại có thể tạo tài nguyên tính phí, thay đổi quyền truy cập hoặc ảnh hưởng đến ứng dụng khác.

Đặc biệt nguy hiểm nếu tài nguyên có tên dùng chung giữa nhiều môi trường hoặc nhiều instance. Một instance staging có thể vô tình tạo tài nguyên trong project production nếu credential hoặc endpoint cấu hình sai.

### 2.2. Condition có thể được đánh giá trong nhiều context và nhiều lần

Không nên dựa vào giả định rằng một condition chỉ chạy đúng một lần trong toàn bộ vòng đời hệ thống. Có thể có nhiều ApplicationContext, test context, parent/child context, lần khởi động lại hoặc các lần đánh giá ở những giai đoạn xử lý cấu hình khác nhau.

Nếu mỗi lần đánh giá lại tạo tài nguyên:
- Có thể xảy ra nhiều yêu cầu tạo đồng thời.
- Có thể tạo nhiều tài nguyên nếu tên không ổn định.
- Có thể gặp race condition khi nhiều instance khởi động cùng lúc.
- Có thể để lại tài nguyên khi context khởi động thất bại sau đó.
- Test có thể làm thay đổi tài khoản cloud hoặc database dùng chung.

Ngay cả API tạo tài nguyên có tính idempotent cũng không làm cho condition trở thành nơi phù hợp để provision. Idempotency giảm một số rủi ro lặp lại; nó không giải quyết quyền sở hữu tài nguyên, chi phí, race condition, rollback hoặc trách nhiệm xóa.

### 2.3. Condition trở nên chậm và phụ thuộc mạng

Một condition gọi HTTP, database hoặc cloud control plane sẽ phụ thuộc:
- DNS và TLS.
- Network latency.
- Credential và token refresh.
- Rate limit.
- Timeout.
- Dịch vụ bên ngoài đang lỗi.
- Proxy, firewall và cấu hình môi trường.

Khi dịch vụ ngoài chậm, ApplicationContext refresh cũng chậm. Khi dịch vụ ngoài tạm thời không truy cập được, condition có thể trả no-match dù feature đã được cấu hình đúng.

Điều này làm startup không ổn định và khó tái lập. Condition vốn nên là một phép đánh giá cấu hình nhanh, nhưng lại biến thành một thao tác I/O.

### 2.4. Kết quả condition có thể che giấu lỗi cấu hình

Nếu condition gọi dịch vụ và trả false khi không kết nối được, Spring có thể bỏ qua bean. Ứng dụng tiếp tục khởi động mà không có feature mà người vận hành nghĩ rằng đã bật.

Ngược lại, nếu condition tạo tài nguyên thành công rồi trả true, người dùng có thể không biết ứng dụng vừa thay đổi hạ tầng. Khi resource creation thất bại, lỗi xuất hiện như lỗi khởi động Spring dù nguyên nhân thực chất là quyền cấp phát hoặc cloud control plane.

Tốt hơn là thể hiện rõ:
- Feature có được bật hay không.
- Cấu hình endpoint/credential có hợp lệ hay không.
- Resource có được provision hay không.
- Dịch vụ có sẵn sàng hay không.

### 2.5. Quyền của ứng dụng bị mở rộng không cần thiết

Runtime identity của ứng dụng thường chỉ cần quyền sử dụng tài nguyên, chẳng hạn ghi object vào bucket hoặc gửi message vào queue. Nếu condition có thể tạo tài nguyên, ứng dụng cần thêm quyền quản trị như create bucket, create topic, create schema hoặc tạo IAM policy.

Quyền quản trị hạ tầng lớn hơn nhiều so với quyền vận hành ứng dụng. Tách provisioning khỏi runtime giúp áp dụng least privilege: pipeline/hạ tầng có quyền tạo, còn workload chỉ có quyền sử dụng.

## 3. Condition nên kiểm tra những gì?

Spring Boot cung cấp các condition chuẩn để quyết định có áp dụng configuration hay bean hay không.

| Condition | Điều được kiểm tra | Không chứng minh điều gì |
| --- | --- | --- |
| `@ConditionalOnProperty` | Giá trị trong Spring Environment | Remote service đang hoạt động |
| `@ConditionalOnClass` | Class có trên runtime classpath | Credential hoặc dịch vụ bên ngoài hợp lệ |
| `@ConditionalOnMissingClass` | Class không có trên classpath | Tài nguyên cloud không tồn tại |
| `@ConditionalOnBean` | Bean phù hợp đã có trong BeanFactory | Bean đó kết nối được database hoặc broker |
| `@ConditionalOnMissingBean` | Chưa có bean phù hợp tại thời điểm đánh giá | Có thể an toàn tạo tài nguyên bên ngoài |
| `@ConditionalOnResource` | Resource tại location được Spring resolve có tồn tại | Có thể tạo bucket, queue hoặc database table |
| `@ConditionalOnWebApplication` | Loại application context | HTTP server hoặc endpoint bên ngoài đang healthy |

Các condition này trả lời câu hỏi về cấu hình, classpath, bean registry hoặc resource location. Chúng không phải công cụ provisioning hạ tầng.

### 3.1. Dùng property để bật feature

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnProperty(
        prefix = "acme.archive",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = false
)
static class ArchiveEnabledConfiguration {
}
~~~

Feature chỉ được áp dụng khi property có giá trị true. Khi thiếu property hoặc false, cấu hình bị bỏ qua.

Property này thể hiện ý định của người vận hành. Nó không tự xác nhận endpoint có truy cập được hay bucket đã tồn tại.

### 3.2. Dùng classpath condition cho integration tùy chọn

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(name = "com.vendor.archive.ArchiveSdk")
static class ArchiveSdkConfiguration {
}
~~~

Điều kiện này kiểm tra SDK có trong runtime classpath. Nó không tải SDK từ mạng và không tạo tài nguyên cloud.

Khi optional library vắng mặt, nested configuration được bỏ qua. Các bean core không phụ thuộc SDK vẫn có thể hoạt động.

### 3.3. Dùng bean condition cho dependency đã đăng ký

~~~java
@Bean
@ConditionalOnBean(DataSource.class)
@ConditionalOnMissingBean(ArchiveRepository.class)
ArchiveRepository archiveRepository(DataSource dataSource) {
    return new JdbcArchiveRepository(dataSource);
}
~~~

Ở đây Spring kiểm tra bean DataSource có trong BeanFactory và chưa có ArchiveRepository thay thế. Condition không chạy câu SQL để kiểm tra schema, không tạo database hoặc table.

Nếu schema cần được migration, hãy dùng migration tool hoặc một bước provisioning rõ ràng. Sự tồn tại của DataSource bean không đồng nghĩa schema đã sẵn sàng.

### 3.4. Dùng resource condition cho file cấu hình thực sự

Ví dụ:

~~~java
@Configuration(proxyBeanMethods = false)
@ConditionalOnResource(
        resources = "classpath:/acme/archive-defaults.json"
)
static class ArchiveDefaultsConfiguration {
}
~~~

Condition này kiểm tra một resource location mà Spring có thể resolve, ví dụ file trong classpath hoặc một location theo quy ước Resource của Spring. Nó không tạo file, bucket, database table hoặc topic.

Đừng dùng một resource condition để thay thế quy trình provisioning cho tài nguyên cloud. Nếu cần kiểm tra remote availability, hãy dùng health/readiness hoặc một bước kiểm tra kết nối riêng.

### 3.5. Custom Condition chỉ đọc trạng thái cấu hình cục bộ

Khi annotation chuẩn không đủ, custom condition có thể đọc Environment hoặc kiểm tra classloader:

~~~java
public final class OnArchiveModeCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        return context.getEnvironment().getProperty(
                "acme.archive.mode",
                "disabled"
        ).equalsIgnoreCase("enabled");
    }
}
~~~

Condition này chỉ đọc property, không tạo bean, không gọi dịch vụ ngoài và không thay đổi hạ tầng.

Nếu custom condition chỉ kiểm tra một boolean property, ConditionalOnProperty thường đơn giản và dễ hiểu hơn. Chỉ viết custom condition khi có quy tắc thực sự cần thiết.

## 4. Tách activation, provisioning và availability

Một thiết kế rõ ràng đặt từng trách nhiệm vào đúng nơi.

| Trách nhiệm | Câu hỏi | Cơ chế phù hợp |
| --- | --- | --- |
| Activation | Có nên đăng ký ArchiveClient không? | Property/classpath/bean conditions |
| Provisioning | Bucket hoặc schema đã được tạo chưa, nếu chưa thì ai tạo? | IaC, migration, pipeline hoặc provisioner được bật rõ ràng |
| Availability | Endpoint có phản hồi và resource có dùng được không? | Health indicator, readiness hoặc startup validator |
| Runtime operation | Ghi object hoặc gửi message có thành công không? | Client call với timeout/retry phù hợp |

### 4.1. Activation không cần kết nối đến dịch vụ

Nếu người dùng đặt:

~~~properties
acme.archive.enabled=true
acme.archive.endpoint=https://archive.example.test/objects
~~~

Spring có thể đăng ký ArchiveClient dựa trên property và cấu hình endpoint. Tạo một object client không nhất thiết phải gửi HTTP request.

Constructor có thể:
- Lưu endpoint.
- Tạo HTTP client cục bộ.
- Thiết lập timeout.
- Kiểm tra giá trị cấu hình có hợp lệ về mặt cú pháp.
- Nhận transport đã được inject.

Constructor không nên:
- Gửi request để tạo bucket.
- Tạo database table.
- Tạo queue hoặc topic.
- Upload một object giả để xem endpoint có hoạt động.
- Gọi remote API chỉ để quyết định bean có tồn tại không.

### 4.2. Provisioning là một workflow riêng

Tài nguyên bên ngoài thường được quản lý bởi:
- Terraform, CloudFormation hoặc công cụ Infrastructure as Code khác.
- Kubernetes operator hoặc manifest.
- Database migration như Flyway/Liquibase.
- Pipeline triển khai.
- Một lệnh quản trị hoặc job provisioning riêng.
- Một provisioner trong ứng dụng nếu sản phẩm thực sự sở hữu vòng đời tài nguyên đó.

Nếu ứng dụng có trách nhiệm tạo resource, hãy biểu diễn hành động này như một workflow tường minh. Workflow cần xác định ai sở hữu resource, tên và namespace, quyền tạo/xóa, idempotency, rollback, cleanup và hành vi khi resource đã tồn tại.

Không giấu provisioning bên trong Condition.matches(...), ConditionalOnProperty hoặc factory method chỉ nhằm quyết định có đăng ký bean hay không.

### 4.3. Availability thuộc health và readiness

Một dịch vụ có thể được cấu hình đúng nhưng tạm thời không truy cập được. Điều đó không nhất thiết có nghĩa bean client không nên tồn tại.

Các lựa chọn:
- Health indicator kiểm tra trạng thái dịch vụ khi Actuator health được truy vấn.
- Readiness probe báo ứng dụng chưa sẵn sàng nhận traffic khi dependency bắt buộc không dùng được.
- Startup validator thực hiện một phép kiểm tra có timeout nếu contract yêu cầu fail-fast.
- Runtime client xử lý lỗi kết nối, retry và circuit breaker theo chính sách nghiệp vụ.

Health check nên kiểm tra trạng thái bằng thao tác đọc/health endpoint. Nó không nên tạo tài nguyên mới chỉ để biến health thành UP.

Nếu tài nguyên bắt buộc phải tồn tại trước khi ứng dụng chạy, provisioning pipeline nên tạo nó trước deployment. Ứng dụng có thể fail-fast nếu cấu hình bắt buộc không hợp lệ hoặc báo readiness DOWN nếu resource không sẵn sàng, theo contract đã công bố.

### 4.4. Không biến lỗi availability thành no-match

Giả sử property bật feature nhưng cloud service đang timeout. Nếu custom condition trả false, bean biến mất và ứng dụng có thể khởi động trong trạng thái thiếu tính năng.

Đó là hai kết quả khác nhau:
- Property false: người dùng chủ động tắt feature.
- Property true nhưng service timeout: feature được bật, dependency hiện không khả dụng.

Nên giữ hai trạng thái này tách biệt. Condition quyết định bean có được cấu hình hay không; health/readiness thể hiện dependency có sẵn sàng hay không.

## 5. Ví dụ anti-pattern: tạo bucket trong Condition

Một implementation sai có thể trông như sau:

~~~java
// ANTI-PATTERN: pseudocode để nhận diện lỗi thiết kế.
public final class OnArchiveBucketCondition implements Condition {

    @Override
    public boolean matches(
            ConditionContext context,
            AnnotatedTypeMetadata metadata) {

        CloudAdminClient admin = createAdminClient(context);

        if (!admin.bucketExists("notice-archive")) {
            admin.createBucket("notice-archive");
        }

        return admin.bucketExists("notice-archive");
    }
}
~~~

Các vấn đề:
1. matches cần network I/O và có thể block context refresh.
2. Condition cần credential có quyền quản trị.
3. Tạo bucket là side effect ngoài ý định của activation.
4. Hai instance khởi động cùng lúc có thể cạnh tranh tạo resource.
5. Nếu context thất bại ở bean khác, bucket vẫn còn.
6. Test unit cần cloud client hoặc tài nguyên cloud thật.
7. Remote service down có thể làm condition trả no-match.
8. Không có chỗ rõ ràng để quản lý ownership, cleanup và chi phí.

Sửa thiết kế bằng cách:
- Condition chỉ kiểm tra property hoặc classpath.
- Bean client được tạo mà không kết nối.
- Provisioning được thực hiện trước deployment hoặc qua một lệnh/job riêng.
- Health/readiness kiểm tra khả năng sử dụng sau khi resource đã được provision.

## 6. Ví dụ hoàn chỉnh: ArchiveClient không tạo resource khi context refresh

Lab tạo một client HTTP để gửi nội dung tới archive endpoint. Mục tiêu:
- Feature chỉ bật khi acme.archive.enabled=true.
- Bean được tạo mà không gọi endpoint.
- HTTP request chỉ được gửi khi code nghiệp vụ gọi ArchiveClient.put(...).
- Test dùng transport giả để chứng minh không có request trong lúc ApplicationContext refresh.

Ví dụ dùng Java 17, vì java.net.http.HttpClient có sẵn trong JDK 11 trở lên.

### 6.1. Cấu trúc thư mục

~~~text
archive-autoconfigure/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/acme/archive/
    │   │   ├── ArchiveClient.java
    │   │   ├── ArchiveProperties.java
    │   │   ├── ArchiveTransport.java
    │   │   └── JdkArchiveTransport.java
    │   ├── java/com/acme/archive/autoconfigure/
    │   │   └── ArchiveAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/acme/archive/autoconfigure/
            └── ArchiveAutoConfigurationTest.java
~~~

### 6.2. pom.xml

Tệp pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.acme.archive</groupId>
    <artifactId>archive-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

spring-boot-autoconfigure cung cấp annotation và cơ chế auto-configuration. spring-boot-starter-test cung cấp JUnit 5, AssertJ và ApplicationContextRunner cho test.

Không cần SDK cloud hoặc database driver vì lab chỉ mô tả HTTP client. Nếu integration thực tế cần một SDK tùy chọn, hãy khai báo dependency theo đúng module và bảo vệ các tham chiếu đến SDK bằng nested configuration class-level condition.

### 6.3. ArchiveProperties.java

Tệp src/main/java/com/acme/archive/ArchiveProperties.java:

~~~java
package com.acme.archive;

import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "acme.archive")
public class ArchiveProperties {

    private URI endpoint;

    private Duration connectTimeout = Duration.ofSeconds(2);

    private Duration requestTimeout = Duration.ofSeconds(5);

    public URI getEndpoint() {
        return endpoint;
    }

    public void setEndpoint(URI endpoint) {
        this.endpoint = endpoint;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public void setConnectTimeout(Duration connectTimeout) {
        this.connectTimeout = connectTimeout;
    }

    public Duration getRequestTimeout() {
        return requestTimeout;
    }

    public void setRequestTimeout(Duration requestTimeout) {
        this.requestTimeout = requestTimeout;
    }
}
~~~

Properties chứa cấu hình, không chứa logic gọi remote service. Endpoint được yêu cầu khi feature bật; timeout có giá trị mặc định.

### 6.4. ArchiveTransport.java

Tệp src/main/java/com/acme/archive/ArchiveTransport.java:

~~~java
package com.acme.archive;

import java.io.IOException;
import java.net.URI;

public interface ArchiveTransport {

    int put(URI endpoint, String content)
            throws IOException, InterruptedException;
}
~~~

Interface này tách cách gửi request khỏi client nghiệp vụ. Test có thể thay transport thật bằng implementation giả để ghi nhận request.

### 6.5. JdkArchiveTransport.java

Tệp src/main/java/com/acme/archive/JdkArchiveTransport.java:

~~~java
package com.acme.archive;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;

public class JdkArchiveTransport implements ArchiveTransport {

    private final HttpClient httpClient;
    private final Duration requestTimeout;

    public JdkArchiveTransport(
            Duration connectTimeout,
            Duration requestTimeout) {

        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(connectTimeout)
                .build();

        this.requestTimeout = requestTimeout;
    }

    @Override
    public int put(URI endpoint, String content)
            throws IOException, InterruptedException {

        HttpRequest request = HttpRequest.newBuilder(endpoint)
                .timeout(requestTimeout)
                .header("Content-Type", "text/plain; charset=utf-8")
                .PUT(HttpRequest.BodyPublishers.ofString(content))
                .build();

        HttpResponse<Void> response = httpClient.send(
                request,
                HttpResponse.BodyHandlers.discarding()
        );

        return response.statusCode();
    }
}
~~~

Constructor chỉ tạo HttpClient cục bộ và lưu timeout. Nó không gửi request, không kiểm tra endpoint và không tạo tài nguyên từ xa.

Network I/O chỉ xảy ra trong put(...), khi một thao tác nghiệp vụ thực sự yêu cầu ghi archive. Request có timeout riêng để tránh chờ vô hạn.

### 6.6. ArchiveClient.java

Tệp src/main/java/com/acme/archive/ArchiveClient.java:

~~~java
package com.acme.archive;

import java.io.IOException;
import java.net.URI;

public class ArchiveClient {

    private final ArchiveTransport transport;
    private final URI endpoint;

    public ArchiveClient(ArchiveTransport transport, URI endpoint) {
        this.transport = transport;
        this.endpoint = endpoint;
    }

    public int put(String content)
            throws IOException, InterruptedException {

        return transport.put(endpoint, content);
    }
}
~~~

Client giữ transport và endpoint. Không có kiểm tra availability hoặc provisioning trong constructor. Khi người dùng gọi put, client mới thực hiện thao tác từ xa.

### 6.7. ArchiveAutoConfiguration.java

Tệp src/main/java/com/acme/archive/autoconfigure/ArchiveAutoConfiguration.java:

~~~java
package com.acme.archive.autoconfigure;

import com.acme.archive.ArchiveClient;
import com.acme.archive.ArchiveProperties;
import com.acme.archive.ArchiveTransport;
import com.acme.archive.JdkArchiveTransport;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class ArchiveAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnProperty(
            prefix = "acme.archive",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = false
    )
    @EnableConfigurationProperties(ArchiveProperties.class)
    static class EnabledArchiveConfiguration {

        @Bean
        @ConditionalOnMissingBean(ArchiveTransport.class)
        ArchiveTransport archiveTransport(ArchiveProperties properties) {
            return new JdkArchiveTransport(
                    properties.getConnectTimeout(),
                    properties.getRequestTimeout()
            );
        }

        @Bean
        @ConditionalOnMissingBean(ArchiveClient.class)
        ArchiveClient archiveClient(
                ArchiveTransport transport,
                ArchiveProperties properties) {

            if (properties.getEndpoint() == null) {
                throw new IllegalStateException(
                        "Set acme.archive.endpoint when "
                                + "acme.archive.enabled=true"
                );
            }

            return new ArchiveClient(
                    transport,
                    properties.getEndpoint()
            );
        }
    }
}
~~~

Cấu hình được chia thành hai tầng:
- Outer auto-configuration không thực hiện provisioning hoặc network I/O.
- Nested configuration chỉ được áp dụng khi property bật.

Khi feature tắt hoặc property thiếu:
- Nested configuration không được đăng ký.
- ArchiveProperties, ArchiveTransport và ArchiveClient mặc định không xuất hiện.
- Không có client nào được tạo để gọi remote service.

Khi feature bật:
- Properties được bind.
- Transport và client được tạo.
- Endpoint thiếu sẽ làm startup fail với thông báo cấu hình rõ ràng.
- Endpoint có mặt nhưng remote service chưa phản hồi không làm context tự gọi mạng. Việc kiểm tra availability thuộc bước riêng.

ConditionalOnMissingBean cho phép ứng dụng thay transport hoặc client mặc định bằng implementation riêng.

### 6.8. AutoConfiguration.imports

Tạo file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Nội dung:

~~~text
com.acme.archive.autoconfigure.ArchiveAutoConfiguration
~~~

Đây là resource để Spring Boot phát hiện auto-configuration trong JAR. Test dùng AutoConfigurations.of(...) nạp class trực tiếp; việc kiểm tra metadata trong JAR cần một consumer test riêng nếu module được phát hành cho ứng dụng khác.

## 7. Test chứng minh context refresh không gọi dịch vụ ngoài

Tệp src/test/java/com/acme/archive/autoconfigure/ArchiveAutoConfigurationTest.java:

~~~java
package com.acme.archive.autoconfigure;

import java.io.IOException;
import java.net.URI;

import com.acme.archive.ArchiveClient;
import com.acme.archive.ArchiveProperties;
import com.acme.archive.ArchiveTransport;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class ArchiveAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ArchiveAutoConfiguration.class
                    ));

    static class RecordingArchiveTransport implements ArchiveTransport {

        private int calls;
        private URI lastEndpoint;
        private String lastContent;

        @Override
        public int put(URI endpoint, String content) throws IOException {
            calls++;
            lastEndpoint = endpoint;
            lastContent = content;
            return 201;
        }
    }

    @Test
    void featureIsDisabledWhenPropertyIsMissing() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).doesNotHaveBean(ArchiveClient.class);
            assertThat(context).doesNotHaveBean(ArchiveTransport.class);
            assertThat(context).doesNotHaveBean(ArchiveProperties.class);
        });
    }

    @Test
    void falsePropertyDoesNotRegisterArchiveBeans() {
        runner.withPropertyValues("acme.archive.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(ArchiveClient.class);
                    assertThat(context).doesNotHaveBean(ArchiveTransport.class);
                });
    }

    @Test
    void contextRefreshDoesNotCallRemoteTransport() {
        RecordingArchiveTransport transport =
                new RecordingArchiveTransport();

        runner.withPropertyValues(
                "acme.archive.enabled=true",
                "acme.archive.endpoint=https://archive.example.test/objects",
                "acme.archive.connect-timeout=1s",
                "acme.archive.request-timeout=3s"
        ).withBean(ArchiveTransport.class, () -> transport)
         .run(context -> {
             assertThat(context).hasNotFailed();
             assertThat(context).hasSingleBean(ArchiveClient.class);

             ArchiveClient client = context.getBean(ArchiveClient.class);

             // Context đã refresh nhưng chưa có thao tác HTTP nào.
             assertThat(transport.calls).isZero();

             int status;
             try {
                 status = client.put("invoice-42");
             }
             catch (InterruptedException ex) {
                 Thread.currentThread().interrupt();
                 throw new AssertionError(ex);
             }
             catch (IOException ex) {
                 throw new AssertionError(ex);
             }

             // Request chỉ xảy ra sau lời gọi nghiệp vụ rõ ràng.
             assertThat(status).isEqualTo(201);
             assertThat(transport.calls).isEqualTo(1);
             assertThat(transport.lastEndpoint)
                     .isEqualTo(URI.create(
                             "https://archive.example.test/objects"
                     ));
             assertThat(transport.lastContent).isEqualTo("invoice-42");
         });
    }

    @Test
    void enabledFeatureRequiresEndpointConfiguration() {
        runner.withPropertyValues("acme.archive.enabled=true")
                .run(context -> {
                    assertThat(context).hasFailed();
                    assertThat(rootCause(context.getStartupFailure())
                            .getMessage())
                            .contains("acme.archive.endpoint");
                });
    }

    private static Throwable rootCause(Throwable failure) {
        Throwable current = failure;

        while (current.getCause() != null
                && current.getCause() != current) {
            current = current.getCause();
        }

        return current;
    }
}
~~~

Test sử dụng RecordingArchiveTransport thay cho HTTP thật. Sau khi context refresh:
- ArchiveClient đã tồn tại.
- Transport chưa nhận request nào.
- Chỉ sau khi test gọi client.put(...), counter mới tăng lên một.

Đây là bằng chứng trực tiếp rằng activation không cần gọi dịch vụ bên ngoài. Test cũng xác nhận property thiếu hoặc false không đăng ký bean, và cấu hình endpoint thiếu được báo rõ khi feature bật.

### 7.1. Chạy test

Từ thư mục chứa pom.xml:

~~~bash
mvn clean test
~~~

Kỳ vọng bốn test PASS. Test không cần cloud account, bucket thật, database hoặc HTTP server.

Nếu một test thất bại:
- Kiểm tra ArchiveAutoConfiguration có condition đúng prefix/property không.
- Kiểm tra EnableConfigurationProperties nằm trong nested configuration được bảo vệ.
- Kiểm tra ArchiveClient constructor có gọi transport không.
- Kiểm tra JdkArchiveTransport constructor có gửi request hoặc gọi API provisioning không.
- Kiểm tra test đã đăng ký fake transport trước khi factory method mặc định được áp dụng.

## 8. Kiểm tra resource hiện hữu khác với tạo resource

Có trường hợp ứng dụng cần biết resource đã tồn tại trước khi nhận traffic. Ví dụ bucket, table hoặc queue phải được provision trước.

Điều đó không có nghĩa condition nên tạo resource. Hãy chọn cách xử lý theo mục tiêu:

| Mục tiêu | Hành động phù hợp |
| --- | --- |
| Chỉ quyết định feature có được bật | Đọc property hoặc kiểm tra classpath/bean |
| Xác nhận file cấu hình local có mặt | Dùng ConditionalOnResource hoặc kiểm tra resource trong cấu hình |
| Kiểm tra bucket đã được tạo | Dùng health/startup validator đọc trạng thái, không tạo bucket |
| Tạo bucket nếu chưa có theo quy trình triển khai | IaC hoặc provisioner được bật rõ ràng |
| Xác nhận database schema đã migration | Chạy migration/version check riêng |
| Tạo Kafka topic | Provisioning pipeline hoặc topic-management workflow |
| Kiểm tra broker có phản hồi | Health/readiness hoặc client operation có timeout |
| Tạo remote tenant/project | Workflow quản trị riêng với quyền và audit rõ ràng |

### 8.1. Nếu resource phải tồn tại trước startup

Có thể có contract fail-fast:
1. Feature được bật bằng property.
2. Bean client được đăng ký.
3. Một startup validator thực hiện phép kiểm tra read-only với timeout giới hạn.
4. Nếu resource không tồn tại, ứng dụng dừng với thông báo cụ thể.

Đây là validation có chủ đích, không phải condition. Nó vẫn tạo network I/O và ảnh hưởng startup, nên chỉ dùng nếu yêu cầu vận hành thật sự cần.

Nếu resource có thể unavailable tạm thời mà ứng dụng vẫn nên chạy, dùng readiness để báo trạng thái chưa sẵn sàng. Không âm thầm trả condition no-match và làm bean biến mất.

### 8.2. Nếu ứng dụng sở hữu provisioning

Nếu sản phẩm chủ động tạo resource, hãy đặt nó trong một component có contract rõ ràng, ví dụ:
- ArchiveProvisioner.ensureContainerExists().
- Một ApplicationRunner chỉ được bật bởi property riêng.
- Một CLI command chạy trước khi deploy workload.
- Một migration job chạy với identity có quyền DDL.

Phải xác định:
- Ai sở hữu resource và ai được phép xóa?
- Tên resource có namespace theo environment/application không?
- API tạo có idempotent không?
- Nếu hai instance chạy cùng lúc thì xử lý thế nào?
- Nếu provisioning thành công nhưng context thất bại thì cleanup ra sao?
- Có audit log và metric cho thao tác không?
- Runtime workload có thể bỏ quyền create sau khi provision không?

Điểm cốt lõi: người vận hành phải biết một hành động provisioning đang diễn ra. Không để nó xảy ra như tác dụng phụ của việc đánh giá condition.

## 9. Kiểm thử activation mà không cần tài nguyên thật

Một bộ auto-configuration test nên xác minh logic đăng ký bean bằng context nhỏ, dữ liệu giả và classloader được kiểm soát.

### 9.1. ApplicationContextRunner cho property và bean conditions

ApplicationContextRunner cho phép tạo context với từng bộ property và bean definitions. Mỗi lần run(...) tạo một context kiểm thử riêng.

Ví dụ:
- Property thiếu: feature không bật.
- Property false: feature không bật.
- Property true: bean client xuất hiện.
- User bean đã tồn tại: auto-configuration back off.
- Bean dependency thiếu: integration bean không xuất hiện.

Các test này không cần cloud account hoặc database thật vì chúng kiểm tra activation contract, không kiểm tra network protocol.

### 9.2. Dùng fake transport hoặc mock

Fake transport ghi nhận:
- Có bao nhiêu lần gọi.
- Endpoint nào được gửi.
- Payload nào được gửi.
- Kết quả hoặc exception nào được trả.

Trong test mẫu, counter bằng 0 ngay sau context refresh và chỉ tăng sau ArchiveClient.put(...).

Đây là cách tốt để phát hiện ai đó vô tình thêm HTTP call vào constructor hoặc factory method trong một lần refactor sau này.

### 9.3. Dùng FilteredClassLoader cho optional library

Nếu integration phụ thuộc SDK tùy chọn, có thể mô phỏng class vắng mặt:

~~~java
runner.withClassLoader(
        new FilteredClassLoader("com.vendor.archive")
).run(context -> {
    assertThat(context).hasNotFailed();
    assertThat(context).doesNotHaveBean(ArchiveClient.class);
});
~~~

Test này kiểm tra classpath condition và optional boundary. Nó không cần tải SDK, kết nối cloud hoặc tạo tài nguyên.

### 9.4. Khi nào dùng Testcontainers?

Testcontainers phù hợp cho integration test cần xác minh hành vi thực tế với database, broker hoặc dịch vụ tương thích chạy trong môi trường test.

Trong trường hợp đó:
- Container/resource là fixture do test chủ động tạo.
- Dùng dữ liệu và tên riêng cho test.
- Chạy migration hoặc setup ở bước test setup.
- Xóa container/resource sau test.
- Không để test unit/condition dùng chung cloud resource của production.

Một integration test có thể tạo database test để xác minh migration. Điều đó khác hoàn toàn việc tạo database chỉ để quyết định auto-configuration có được đăng ký hay không.

### 9.5. Kiểm tra provisioning riêng

Nếu provisioning là một phần của sản phẩm:
- Test idempotency của provisioner.
- Test quyền thiếu hoặc API trả lỗi.
- Test hai request tạo đồng thời.
- Test cleanup và rollback.
- Test resource đã tồn tại từ trước.
- Test audit/metric và thông báo lỗi.

Không gộp những test này vào ApplicationContextRunner test chỉ để kiểm tra condition.

## 10. Cách đọc lỗi khi condition và resource bị trộn lẫn

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Context refresh chậm vài giây | Condition gọi HTTP/database/cloud API | Bỏ I/O khỏi condition; đo bằng log/profiler |
| Feature biến mất khi cloud tạm down | Condition biến availability thành no-match | Giữ activation theo property; dùng health/readiness |
| Mỗi lần test tạo thêm bucket/topic | Condition có side effect | Dùng fake cho condition test; provisioning riêng |
| Ứng dụng cần quyền create bucket để khởi động | Runtime identity đang làm việc quản trị | Tách provisioning identity và runtime identity |
| Test unit cần cloud credentials | Condition phụ thuộc cloud admin client | Condition chỉ đọc cấu hình cục bộ |
| Context fail sau khi resource đã được tạo | Provisioning nằm trong config refresh | Đưa provisioning sang workflow có rollback/cleanup |
| Resource được tạo nhưng bean không được đăng ký | Condition tiếp theo no-match hoặc bean creation fail | Tách bước provision khỏi bước activation |
| Startup lúc nhanh lúc chậm | Condition phụ thuộc network/remote service | Không gọi mạng trong condition |
| Bucket tồn tại nhưng service không truy cập được | Existence và availability bị nhầm | Kiểm tra quyền, endpoint và health riêng |
| Client được tạo dù feature tắt | Bean nằm ngoài nested configuration có condition | Đặt bean trong configuration được bảo vệ |

Khi đọc Condition Evaluation Report, chú ý:
- Condition no-match vì property false là hành vi cấu hình.
- Condition no-match vì class thiếu là hành vi classpath.
- ConditionalOnBean no-match vì bean chưa được đăng ký là hành vi BeanFactory.
- Remote timeout không nên xuất hiện như lý do activation condition nếu thiết kế tách đúng.

Nếu condition report cho biết custom condition đã truy vấn remote service, hãy xem đó là dấu hiệu cần tách trách nhiệm.

## 11. Những lỗi thiết kế phổ biến

1. **Tạo bucket trong Condition.matches.** Context refresh làm thay đổi cloud infrastructure.
2. **Chạy CREATE TABLE IF NOT EXISTS trong condition.** Condition vừa quyết định cấu hình vừa thực hiện migration.
3. **Tạo Kafka topic để kiểm tra broker có hoạt động không.** Việc tạo topic không phải health check.
4. **Gửi message thử vào queue để quyết định có đăng ký bean không.** Có thể tạo dữ liệu rác hoặc kích hoạt consumer.
5. **Upload object giả để xác minh bucket.** Đây là thao tác nghiệp vụ có side effect.
6. **Gọi remote health endpoint từ condition.** Startup phụ thuộc network và trạng thái tạm thời.
7. **Trả no-match khi remote timeout.** Feature đã bật nhưng bean biến mất do availability.
8. **Tạo tài nguyên trong constructor của client.** Chỉ việc khởi tạo bean đã làm thay đổi hạ tầng.
9. **Đưa provisioning vào @Bean factory method.** Factory method có thể chạy lại theo context khác và khó quản lý rollback.
10. **Dùng @ConditionalOnBean như kiểm tra kết nối.** Annotation chỉ kiểm tra bean definitions, không xác minh remote service.
11. **Dùng @ConditionalOnResource cho bucket hoặc topic.** Resource condition không phải công cụ quản lý cloud resource.
12. **Cho runtime identity quyền quản trị quá rộng.** Ứng dụng không cần quyền create/delete chỉ để kích hoạt feature.
13. **Không phân biệt property false với remote service down.** Hai trạng thái cần thông báo và xử lý khác nhau.
14. **Không có timeout cho health/startup validation.** Kiểm tra read-only cũng có thể làm startup treo.
15. **Dùng tài nguyên production trong test activation.** Test có thể sửa hoặc xóa dữ liệu thật.
16. **Chỉ test nhánh feature bật.** Cần xác nhận feature tắt không tạo client hoặc transport.
17. **Không kiểm tra request count sau context refresh.** Có thể bỏ sót network call trong constructor.
18. **Giả định idempotent nghĩa là side effect an toàn.** Vẫn có chi phí, quyền, race và ownership.
19. **Tạo resource nhưng không có cleanup policy.** Resource rác tồn tại sau test hoặc deployment lỗi.
20. **Dùng custom condition cho một property đơn giản.** ConditionalOnProperty rõ ràng hơn và dễ kiểm tra.
21. **Đưa provisioning và readiness vào cùng một boolean.** Một resource có thể đã provision nhưng service đang unavailable.
22. **Nuốt lỗi provisioning rồi tiếp tục như feature đã bật.** Trạng thái ứng dụng không còn phản ánh hạ tầng thực tế.

## 12. Quy trình thiết kế an toàn

1. Viết rõ feature được bật bằng property nào và default là gì.
2. Liệt kê dependency classpath cần thiết cho integration.
3. Liệt kê bean definitions mà integration cần.
4. Dùng condition chuẩn để quyết định configuration/bean có được đăng ký.
5. Đảm bảo Condition.matches không gọi network, không tạo file hoặc resource bên ngoài và không thay đổi trạng thái.
6. Giữ constructor/factory method tạo client không thực hiện provisioning.
7. Đưa endpoint, timeout và credential vào configuration properties.
8. Kiểm tra cấu hình thiếu bằng validation/fail-fast với thông báo rõ ràng.
9. Đưa resource provisioning vào IaC, migration hoặc workflow được bật tường minh.
10. Dùng health/readiness hoặc startup validator riêng nếu cần xác minh availability.
11. Giới hạn quyền runtime vào quyền sử dụng resource; tách quyền provision.
12. Viết ApplicationContextRunner tests cho property/classpath/bean combinations.
13. Dùng fake transport để xác nhận context refresh không gửi request.
14. Dùng FilteredClassLoader khi kiểm tra optional dependency.
15. Dùng Testcontainers hoặc môi trường tích hợp riêng khi cần xác minh protocol/resource thật.
16. Đo startup và kiểm tra log để phát hiện I/O không mong muốn trong refresh.

## 13. Checklist nghiệm thu

- [ ] Condition chỉ đọc property, classpath, bean definitions hoặc resource location cần thiết.
- [ ] Không có create/update/delete resource trong Condition.matches.
- [ ] Không có HTTP/database/cloud control-plane call trong condition.
- [ ] Feature activation tách biệt với provisioning và availability.
- [ ] ConditionalOnProperty có prefix, name, havingValue và matchIfMissing rõ ràng.
- [ ] Optional class được bảo vệ bằng classpath condition ở phạm vi phù hợp.
- [ ] ConditionalOnBean chỉ được dùng để kiểm tra bean đã đăng ký.
- [ ] ConditionalOnResource chỉ dùng cho resource location mà Spring có thể resolve.
- [ ] Constructor và factory method không tạo bucket, table, topic hoặc queue.
- [ ] Client chỉ thực hiện I/O khi thao tác nghiệp vụ được gọi.
- [ ] Timeout được cấu hình cho kết nối và request.
- [ ] Endpoint/credential thiếu được báo lỗi rõ ràng khi feature bật.
- [ ] Provisioning có owner, quyền, idempotency, audit và cleanup policy.
- [ ] Runtime identity không có quyền quản trị chỉ để condition hoạt động.
- [ ] Health/readiness phản ánh availability riêng.
- [ ] Test feature thiếu property và feature false.
- [ ] Test feature true với fake transport.
- [ ] Test xác nhận không có request trong context refresh.
- [ ] Test xác nhận request chỉ xảy ra khi gọi client.
- [ ] Test optional class thiếu nếu integration dùng dependency tùy chọn.
- [ ] Test provisioning riêng nếu ứng dụng sở hữu vòng đời resource.
- [ ] Không dùng production resource trong unit test.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Condition của auto-configuration nên quyết định điều gì?  
**Đáp án:** Có nên áp dụng configuration/đăng ký bean dựa trên property, classpath, bean definitions và trạng thái cấu hình phù hợp hay không.

**Câu 2.** Vì sao không tạo bucket trong Condition.matches?  
**Đáp án:** Vì condition bị biến thành thao tác provisioning có side effect, cần quyền quản trị, phụ thuộc network, có thể chạy trong nhiều context và để lại tài nguyên khi startup thất bại.

**Câu 3.** ConditionalOnProperty có chứng minh remote endpoint hoạt động không?  
**Đáp án:** Không. Nó chỉ kiểm tra giá trị trong Spring Environment.

**Câu 4.** ConditionalOnBean(DataSource.class) có chứng minh database schema đã tồn tại không?  
**Đáp án:** Không. Nó kiểm tra bean DataSource trong BeanFactory, không chạy migration hoặc xác minh schema.

**Câu 5.** ConditionalOnResource dùng để làm gì?  
**Đáp án:** Kiểm tra resource tại location mà Spring có thể resolve. Nó không tạo cloud bucket, database table hoặc message topic.

**Câu 6.** Nếu feature được bật nhưng dịch vụ ngoài đang down, nên xử lý thế nào?  
**Đáp án:** Giữ activation theo cấu hình; thể hiện availability qua health/readiness hoặc một startup validator có timeout nếu contract yêu cầu fail-fast.

**Câu 7.** Provisioning nên được đặt ở đâu?  
**Đáp án:** IaC, migration, pipeline, job quản trị hoặc một provisioner được bật rõ ràng và có lifecycle/permission riêng.

**Câu 8.** Làm thế nào chứng minh context refresh không gọi dịch vụ ngoài?  
**Đáp án:** Inject fake/recording transport, khởi động context và assert số request bằng 0; sau đó gọi client và xác nhận counter tăng.

**Câu 9.** Có được dùng Testcontainers để tạo database test không?  
**Đáp án:** Có, khi đó database là fixture của integration test và được quản lý setup/teardown riêng. Không dùng nó trong condition chỉ để quyết định bean activation.

**Câu 10.** Vì sao runtime identity không nên có quyền create bucket chỉ để khởi động?  
**Đáp án:** Provisioning là quyền quản trị hạ tầng. Runtime workload thường chỉ cần quyền sử dụng tài nguyên đã được provision; tách quyền giúp giảm phạm vi ảnh hưởng nếu credential bị lộ.

## 15. Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 Reference — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnProperty](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnProperty.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnResource](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnResource.html).
- [Spring Boot 3.3.13 Javadoc — ConditionalOnBean](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnBean.html).
- [Spring Framework 6.1 Javadoc — Condition](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Condition.html).
- [Spring Boot 3.3.13 Javadoc — ApplicationContextRunner](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html).
- [Spring Boot Reference — Testing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing).