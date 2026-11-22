# Chi phí khám phá ứng viên, đọc metadata, đánh giá điều kiện và khởi tạo bean

> **Spring Boot Auto Configuration → Hiệu năng và AOT.** Bài học phân tích chi phí khởi động theo từng giai đoạn: khám phá auto-configuration candidates, đọc metadata, đánh giá conditions, đăng ký bean definitions và khởi tạo bean. Ta sẽ dùng metadata processor để lọc sớm cấu hình không phù hợp, đo startup bằng ApplicationStartup/Actuator và phân biệt tối ưu runtime thông thường với Spring AOT và GraalVM Native Image. Ví dụ thực hành dùng Java 17+, Maven và Spring Boot 3.3.13.

## 1. Bức tranh tổng thể: auto-configuration tốn thời gian ở đâu?

Khi ứng dụng gọi `SpringApplication.run(...)`, Spring Boot chuẩn bị Environment, tạo ApplicationContext, nạp cấu hình, đăng ký bean definitions, khởi tạo các singleton eager, chạy lifecycle callbacks và cuối cùng gọi ApplicationRunner/CommandLineRunner. Auto-configuration tham gia vào phần xử lý cấu hình và đăng ký bean definitions của quy trình đó.

Có thể chia phần liên quan đến auto-configuration thành năm giai đoạn:

~~~text
Classpath và Environment
        |
        v
1. Khám phá candidates
   Đọc AutoConfiguration.imports từ các JAR
        |
        v
2. Lọc và đọc metadata
   Exclusions, ordering, spring-autoconfigure-metadata
        |
        v
3. Đánh giá conditions
   Classpath, property, bean, resource, web application...
        |
        v
4. Đăng ký bean definitions
   Configuration classes, @Bean methods, imports
        |
        v
5. Khởi tạo bean
   Constructor/factory method, dependency graph,
   BeanPostProcessor, lifecycle, kết nối tài nguyên
        |
        v
ApplicationReadyEvent
~~~

Đây là mô hình để phân tích, không phải năm bước có thời gian cố định hay một thứ tự chi tiết tuyệt đối cho mọi callback. Spring có thể xử lý nhiều configuration class theo quan hệ import và ordering; các bean được tạo theo dependency graph.

| Giai đoạn | Công việc | Nguồn chi phí thường gặp |
| --- | --- | --- |
| Khám phá candidates | Tìm và đọc danh sách auto-configuration trong classpath | Số JAR, số resource imports, số candidate |
| Đọc/lọc metadata | Loại candidate sớm khi điều kiện có thể kiểm tra từ metadata | Đọc resource, phân tích class metadata, lọc và sắp xếp |
| Đánh giá conditions | Chạy các condition của class và bean method | Số condition, classpath lookup, property lookup, custom condition |
| Đăng ký bean definitions | Parse configuration, import cấu hình và tạo bean definitions | Số configuration, số bean definitions, component scan, post-processors |
| Khởi tạo bean | Tạo singleton, inject dependency, chạy init callbacks | Constructor nặng, I/O, proxy, migration, network call, vòng phụ thuộc |

**Không phải mọi candidate đều tạo bean.** Một auto-configuration có thể được phát hiện nhưng bị loại bởi condition. Một configuration có thể match nhưng bean method lại bị ConditionalOnMissingBean chặn. Một bean definition được đăng ký nhưng có thể chỉ được khởi tạo khi cần nếu lazy.

Cũng cần phân biệt thời gian khởi động Spring với thời gian tiến trình/JVM khởi động. Class loading, JIT, GC, logging, server startup và ứng dụng tự gọi dịch vụ ngoài đều có thể chiếm thời gian ngoài phần auto-configuration.

## 2. Khám phá ứng viên: AutoConfiguration.imports

Spring Boot 3 dùng file:

~~~text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Mỗi dòng chứa tên đầy đủ của một auto-configuration class. Khi ứng dụng bật auto-configuration, Boot tìm các file này trên classpath và hợp nhất danh sách candidate từ các JAR.

Ví dụ một thư viện:

~~~text
com.acme.notice.autoconfigure.NoticeAutoConfiguration
com.acme.notice.autoconfigure.NoticeJdbcAutoConfiguration
com.acme.notice.autoconfigure.NoticeMetricsAutoConfiguration
~~~

Candidate discovery là cơ chế import cấu hình đã được công bố. Nó không phải là component scan toàn bộ package của mọi thư viện. Đây là lý do thư viện nên đăng ký đúng các auto-configuration cần thiết trong imports file và tránh dùng ComponentScan rộng để tìm thêm cấu hình.

Chi phí ở giai đoạn này phụ thuộc vào:
- Số JAR và số imports resource trên classpath.
- Số candidate được khai báo.
- Số candidate trùng lặp hoặc bị exclude.
- Số quan hệ before/after cần sắp xếp.
- Số thư viện mang theo auto-configuration mà ứng dụng không sử dụng.

Một starter kéo nhiều integration tùy chọn có thể làm tăng classpath và số candidate phải xem xét. Nếu người dùng chỉ cần core, việc kéo thêm JDBC, Kafka, Elasticsearch, metrics và web integrations có thể làm công việc khởi động phức tạp hơn dù phần lớn bean cuối cùng không được tạo.

### 2.1. Không nhầm imports với component scan

@SpringBootApplication thường bao gồm @ComponentScan cho package ứng dụng và các package con. Auto-configuration của thư viện được phát hiện bằng imports metadata.

Thư viện nên:
- Đặt auto-configuration trong package riêng.
- Đăng ký class bằng AutoConfiguration.imports.
- Dùng @Import để đưa các configuration nội bộ cụ thể vào khi cần.
- Tránh component scan rộng trong thư viện vì có thể phát hiện nhiều component ngoài dự kiến và làm tăng số bean definitions.

Auto-configuration được sắp xếp bằng before, after, beforeName, afterName hoặc annotation ordering tương ứng. Ordering chỉ quyết định thứ tự định nghĩa bean; nó không quyết định thứ tự tạo mọi instance. Việc khởi tạo sau đó vẫn phụ thuộc dependency graph và @DependsOn.

### 2.2. Tối ưu candidate set từ dependency graph

Một số cách giảm công việc ngay từ đầu:
- Tạo starter core chỉ kéo dependency lõi.
- Tách JDBC, Kafka, JSON hoặc metrics thành integration/starter riêng khi chúng thực sự tùy chọn.
- Không khai báo một auto-configuration cho tính năng không thuộc artifact đó.
- Tránh duplicate imports hoặc các class cấu hình cũ còn được đăng ký sau khi thay thế.
- Loại dependency không cần khỏi ứng dụng thay vì trông chờ condition loại bỏ tất cả chi phí của nó.

Việc tách module có thể giảm số candidate và dependency cần xử lý, nhưng không nên chia module chỉ để giảm một vài dòng imports. Hãy dựa trên khả năng tùy chọn, hợp đồng dependency và cách consumer sử dụng thư viện.

## 3. Metadata: lọc sớm candidate trước khi đánh giá đầy đủ

Spring Boot có một annotation processor dành cho auto-configuration. Processor thu thập một số condition có thể suy ra từ metadata của class và ghi vào:

~~~text
META-INF/spring-autoconfigure-metadata.properties
~~~

Khi file này có mặt, Boot có thể lọc sớm các auto-configuration không phù hợp trước khi phải xử lý đầy đủ từng candidate. Việc lọc sớm này giúp giảm startup time, đặc biệt khi thư viện có nhiều auto-configuration.

Có ba loại metadata thường bị nhầm:

| File | Vai trò | Có trực tiếp lọc auto-configuration candidates không? |
| --- | --- | --- |
| META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports | Khai báo danh sách auto-configuration classes | Có, đây là nguồn candidate |
| META-INF/spring-autoconfigure-metadata.properties | Metadata condition để lọc sớm một số candidate | Có, hỗ trợ eager filtering |
| META-INF/spring-configuration-metadata.json | Mô tả configuration properties cho IDE, autocomplete và tài liệu | Không, chủ yếu hỗ trợ người cấu hình ứng dụng |

spring-autoconfigure-metadata.properties không thay thế imports file và cũng không thay thế việc đánh giá condition đầy đủ. Nó chỉ giúp Boot bỏ qua sớm những candidate mà metadata đủ thông tin để kết luận không match. Custom condition hoặc điều kiện phụ thuộc trạng thái runtime vẫn cần được đánh giá theo cơ chế thông thường.

### 3.1. Bật annotation processor trong Maven

Trong module chứa auto-configuration classes, cấu hình spring-boot-autoconfigure-processor trong annotation processor path. Ví dụ với Spring Boot 3.3.13 và Maven Compiler Plugin 3.13.0:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>org.springframework.boot</groupId>
                        <artifactId>spring-boot-autoconfigure-processor</artifactId>
                        <version>3.3.13</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Processor chạy lúc compile. Trong thư viện có nhiều module, hãy cấu hình nó ở module sở hữu auto-configuration, không cần đưa processor vào runtime dependencies của consumer.

Với Gradle, khai báo processor trong cấu hình annotationProcessor:

~~~groovy
dependencies {
    annotationProcessor "org.springframework.boot:spring-boot-autoconfigure-processor"
}
~~~

### 3.2. Kiểm tra metadata đã được sinh

Sau khi build module auto-configuration:

~~~bash
mvn clean package
~~~

Có thể kiểm tra file trong thư mục output:

~~~text
target/classes/META-INF/spring-autoconfigure-metadata.properties
~~~

Hoặc kiểm tra JAR thư viện:

~~~bash
jar tf target/acme-autoconfigure-1.0.0.jar
~~~

Trên Windows có thể lọc kết quả:

~~~powershell
jar tf target/acme-autoconfigure-1.0.0.jar | findstr /I spring-autoconfigure-metadata
~~~

Trên Bash:

~~~bash
jar tf target/acme-autoconfigure-1.0.0.jar | grep spring-autoconfigure-metadata
~~~

Khi đóng gói thành executable Boot JAR, resource của ứng dụng có thể nằm dưới BOOT-INF/classes/; còn JAR thư viện thông thường có resource ở gốc JAR. Hãy kiểm tra đúng artifact đang phát hành.

Không tự viết hoặc chỉnh sửa metadata sinh tự động để thay đổi logic. Nếu file không được tạo, kiểm tra annotation processor có chạy trong module chứa auto-configuration hay không.

### 3.3. Condition nào có thể được lọc sớm?

Processor có thể thu thập các condition mà nó nhận diện được từ annotation metadata, ví dụ một số điều kiện classpath hoặc property. Nó không thể dự đoán tùy ý mọi logic Java trong custom Condition.

Ví dụ:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.acme.optional.OptionalClient")
@ConditionalOnProperty(
        prefix = "acme.notice",
        name = "enabled",
        havingValue = "true"
)
public class NoticeAutoConfiguration {
}
~~~

Các annotation tường minh giúp Boot và processor đọc được ý định cấu hình. Nếu custom condition thực hiện truy vấn database, đọc file tùy ý hoặc gọi dịch vụ mạng, processor không thể biến toàn bộ logic đó thành metadata tĩnh.

### 3.4. Không nhầm metadata với điều kiện thực tế

Metadata hỗ trợ lọc sớm; condition runtime vẫn là nguồn quyết định cuối cùng. Vì vậy:
- Không bỏ @ConditionalOnClass chỉ vì đã bật processor.
- Không giả định custom condition sẽ được bỏ qua hoàn toàn.
- Không dùng metadata như cơ chế thay thế test condition.
- Khi nâng cấp Boot hoặc thay annotation, build lại và kiểm tra artifact.
- Không kết luận ứng dụng đã tối ưu chỉ vì file metadata tồn tại; cần đo startup trước/sau.

## 4. Chi phí đánh giá conditions

Sau khi candidate được tìm thấy và lọc sớm, Spring Boot đánh giá các condition còn lại.

Các condition phổ biến:
- @ConditionalOnClass / @ConditionalOnMissingClass: kiểm tra classpath.
- @ConditionalOnProperty: kiểm tra Environment.
- @ConditionalOnBean / @ConditionalOnMissingBean: kiểm tra bean definitions đã biết ở thời điểm đánh giá.
- @ConditionalOnResource: kiểm tra resource.
- @ConditionalOnWebApplication: kiểm tra loại application context.
- Custom Condition: chạy logic do thư viện tự định nghĩa.

Một condition đơn giản thường rất rẻ. Nhưng số lượng condition lớn, custom logic phức tạp hoặc classpath rất rộng có thể cộng dồn thành chi phí đáng kể.

### 4.1. Ưu tiên condition nhanh và xác định

Nên ưu tiên:
- Kiểm tra class bằng @ConditionalOnClass.
- Kiểm tra feature flag bằng @ConditionalOnProperty.
- Kiểm tra bean bằng @ConditionalOnBean khi cần.
- Tách integration thành nested configuration để condition loại bỏ đúng nhóm bean.
- Dùng custom condition chỉ khi annotation chuẩn không diễn đạt được quy tắc.

Tránh custom condition làm các việc sau:
- Quét hàng nghìn class hoặc package trong mỗi lần đánh giá.
- Đọc và parse file lớn nếu chỉ cần một property.
- Mở kết nối database hoặc HTTP.
- Chờ network response.
- Tạo ApplicationContext phụ.
- Gọi getBean() để khởi tạo object chỉ nhằm quyết định có đăng ký bean hay không.
- Lặp lại cùng một phép tính tốn kém cho nhiều configuration mà không có lý do.

Condition nên trả lời câu hỏi về cấu hình và môi trường một cách nhanh, có thể lặp lại và không tạo side effect.

### 4.2. Đặt condition ở phạm vi phù hợp

Nếu cả nhóm bean cần cùng một dependency, đặt condition trên nested configuration:

~~~java
@AutoConfiguration
public class NoticeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.acme.jdbc.NoticeJdbcAdapter")
    static class JdbcConfiguration {

        @Bean
        @ConditionalOnMissingBean
        NoticeHistoryWriter noticeHistoryWriter() {
            return new NoticeHistoryWriter();
        }
    }
}
~~~

Nếu chỉ một bean cần điều kiện riêng, đặt condition trên factory method. Tránh condition quá rộng làm một integration tùy chọn vô tình chặn các bean độc lập khác.

### 4.3. Cẩn thận với SpEL condition tham chiếu bean

@ConditionalOnExpression hữu ích cho biểu thức đơn giản, nhưng tham chiếu bean trong biểu thức có thể khiến bean đó được khởi tạo rất sớm trong quá trình refresh. Khi đó bean có thể chưa được xử lý đầy đủ bởi các BeanPostProcessor, ví dụ configuration properties binding hoặc proxy.

Nếu chỉ cần kiểm tra property, dùng @ConditionalOnProperty. Nếu cần bean dependency, dùng @ConditionalOnBean hoặc @ConditionalOnMissingBean ở đúng giai đoạn. Không dùng SpEL để gọi một bean chỉ nhằm tính toán điều kiện cấu hình.

### 4.4. Điều kiện bean phụ thuộc thứ tự định nghĩa

@ConditionalOnBean và @ConditionalOnMissingBean đánh giá các bean definitions đã được xử lý cho tới thời điểm đó. Vì thế:
- Auto-configuration nên được nạp sau các bean definitions do người dùng khai báo.
- Dùng @AutoConfiguration(after = ...) khi một auto-configuration phụ thuộc bean definitions của cấu hình khác.
- Đặt điều kiện ở bean method nếu chỉ factory method đó cần dependency.
- Khai báo return type của @Bean càng cụ thể càng tốt để condition nhìn thấy loại bean chính xác.

Ordering của auto-configuration điều khiển thứ tự đăng ký bean definitions. Nó không đảm bảo bean được khởi tạo theo cùng thứ tự.

## 5. Đăng ký bean definitions và khởi tạo bean là hai chi phí khác nhau

Khi configuration class được xử lý, Spring đăng ký bean definitions. Bean definition mô tả:
- Bean class hoặc factory method.
- Scope.
- Constructor/factory method arguments.
- Dependency.
- Lazy/eager behavior.
- Init và destroy callbacks.
- Các metadata phục vụ injection và post-processing.

Đăng ký definition chưa đồng nghĩa với tạo instance. Một context có thể có hàng trăm bean definitions nhưng chỉ một phần được khởi tạo nếu chúng là lazy hoặc chưa được yêu cầu.

Mặc định, các singleton không lazy thường được khởi tạo trong quá trình refresh. Khi khởi tạo một bean, Spring có thể phải:
1. Tạo các dependency của bean.
2. Chọn constructor hoặc factory method.
3. Thực hiện dependency injection.
4. Áp dụng BeanPostProcessor.
5. Tạo proxy nếu cần.
6. Gọi các callback khởi tạo như @PostConstruct hoặc InitializingBean.
7. Thực hiện công việc khởi tạo do ứng dụng viết.

Đây là nơi một constructor nhỏ có thể dẫn đến thời gian khởi động lớn nếu nó mở kết nối, chạy migration, tải schema, gọi HTTP hoặc chờ một dịch vụ bên ngoài.

### 5.1. Giữ constructor và factory method nhẹ

Ví dụ không nên làm:

~~~java
@Bean
RemoteCatalog remoteCatalog() {
    RemoteCatalog catalog = new RemoteCatalog();
    catalog.connectToRemoteServer();
    catalog.downloadAllSchemas();
    catalog.warmUpEveryCache();
    return catalog;
}
~~~

Mỗi lần refresh context, các thao tác này có thể kéo dài startup và khiến ứng dụng phụ thuộc trực tiếp vào độ trễ của dịch vụ ngoài.

Thiết kế tốt hơn:
- Constructor chỉ gán dependency và state cần thiết.
- Dùng timeout rõ ràng cho I/O.
- Nạp dữ liệu tối thiểu cần cho readiness.
- Tách warm-up không bắt buộc khỏi quá trình tạo bean.
- Dùng cache hoặc tài nguyên được chuẩn bị trước nếu phù hợp.
- Nếu khởi tạo bất đồng bộ, chỉ đánh dấu ứng dụng ready sau khi các năng lực bắt buộc đã sẵn sàng.

Không chuyển mọi công việc sang background chỉ để rút ngắn con số startup. Nếu ứng dụng nhận traffic trước khi dependency bắt buộc sẵn sàng, lỗi sẽ chuyển từ startup sang request đầu tiên.

### 5.2. Lazy initialization chỉ trì hoãn instance creation

Có thể đánh dấu một bean lazy:

~~~java
@Bean
@Lazy
ExpensiveReportClient expensiveReportClient() {
    return new ExpensiveReportClient();
}
~~~

Hoặc bật lazy initialization toàn ứng dụng:

~~~properties
spring.main.lazy-initialization=true
~~~

Lazy có thể giảm thời gian refresh vì bean chưa được yêu cầu sẽ chưa được tạo. Tuy nhiên, nó không loại bỏ:
- Candidate discovery.
- Đọc imports metadata.
- Condition evaluation.
- Đăng ký bean definitions.
- Chi phí khi bean được sử dụng lần đầu.

Trade-off:
- Startup có thể nhanh hơn.
- Request đầu tiên dùng bean có thể chậm hơn.
- Lỗi cấu hình hoặc lỗi kết nối có thể chỉ xuất hiện khi bean được gọi.
- Một bean tưởng như không dùng lúc startup có thể được yêu cầu ngay ở request đầu tiên.

Dùng lazy cho bean ít được sử dụng hoặc công việc tùy chọn. Giữ eager cho thành phần cần xác thực sớm để readiness có ý nghĩa.

### 5.3. Đừng nhầm lazy với ordering

@AutoConfigureBefore và @AutoConfigureAfter sắp xếp quá trình định nghĩa bean của auto-configuration. @DependsOn ảnh hưởng thứ tự khởi tạo giữa các bean. @Lazy trì hoãn tạo instance.

Ba cơ chế này giải quyết ba vấn đề khác nhau. Không dùng ordering để che dependency thiếu, không dùng @DependsOn cho mọi bean và không dùng lazy để che một lỗi khởi tạo bắt buộc.

## 6. Chiến lược tối ưu theo từng giai đoạn

| Giai đoạn | Việc nên làm | Điều cần tránh |
| --- | --- | --- |
| Candidate discovery | Starter tối thiểu, tách integration tùy chọn, imports chính xác | Kéo mọi integration vào mọi ứng dụng |
| Metadata | Bật spring-boot-autoconfigure-processor trong module auto-config | Giả định mọi custom condition đều được lọc sớm |
| Condition | Condition chuẩn, nhanh, đặt đúng phạm vi | I/O, quét classpath rộng hoặc khởi tạo bean trong condition |
| Bean definitions | Configuration nhỏ, @Import cụ thể, return type chính xác | Component scan rộng và nhiều definition trùng |
| Bean creation | Constructor nhẹ, timeout, lazy có chọn lọc, giảm I/O | Network call không timeout, migration/warm-up không kiểm soát |
| Đo lường | ApplicationStartup, Actuator startup, JFR | Tối ưu dựa trên cảm giác hoặc một lần đo đơn lẻ |

Trình tự hợp lý là đo trước, xác định giai đoạn chiếm nhiều thời gian, sửa nguyên nhân lớn nhất, sau đó đo lại trong cùng điều kiện. Không nên tối ưu candidate count nếu phần lớn thời gian đang nằm ở database migration hoặc một bean gọi HTTP mất vài giây.

## 7. Đo startup bằng ApplicationStartup và Actuator

Spring Framework cung cấp ApplicationStartup và StartupStep để ghi lại các bước trong lifecycle của Spring. Spring Boot có BufferingApplicationStartup, giữ lại các bước cùng timestamp và duration trong một buffer giới hạn.

Để bật ghi nhận, tạo SpringApplication thay vì gọi static run(...) trực tiếp:

~~~java
package demo.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication
public class StartupDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupDemoApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
~~~

Capacity 2048 là giới hạn số step được buffer trong ví dụ. Nếu ứng dụng tạo nhiều step hơn, các step mới có thể không được ghi khi buffer đầy. Có thể điều chỉnh capacity hoặc lọc/drain step tùy mục đích quan sát.

### 7.1. Expose startup endpoint

Thêm Actuator và cấu hình:

~~~properties
management.endpoints.web.exposure.include=health,startup
~~~

Khi SpringApplication dùng BufferingApplicationStartup, endpoint startup có thể cung cấp dữ liệu JSON về các bước khởi động.

Lấy snapshot:

~~~bash
curl http://localhost:8080/actuator/startup
~~~

Endpoint cũng hỗ trợ POST để drain các step đã ghi:

~~~bash
curl -X POST http://localhost:8080/actuator/startup
~~~

Response chứa các trường như:
- springBootVersion.
- timeline.startTime.
- timeline.events.
- timeline.events[].duration.
- timeline.events[].startupStep.name.
- timeline.events[].startupStep.tags.

Một step có thể cho biết tên như spring.beans.instantiate và tag beanName để xác định bean đang được tạo. Tên và số lượng step phụ thuộc phiên bản Boot, loại context và ứng dụng.

**Bảo vệ endpoint startup.** Không expose thông tin quản trị này công khai nếu không cần. Dữ liệu startup có thể tiết lộ tên bean, package, thư viện và cấu trúc nội bộ.

### 7.2. Đọc startup timeline theo câu hỏi

Khi xem timeline, hãy tìm:
- Step nào có duration dài nhất?
- Có nhiều bean cùng loại đang khởi tạo lặp lại không?
- Bean nào đang chờ I/O hoặc dependency?
- Thời gian nằm trong Spring context refresh hay trong runner do ứng dụng viết?
- Có một bean khởi tạo rất sớm mà lẽ ra không cần cho readiness không?

Một step dài không nhất thiết là lỗi auto-configuration. Ví dụ, spring.beans.instantiate có thể dài vì constructor bean gọi database. Cần kết hợp step với log, code và profiling để tìm nguyên nhân.

### 7.3. Dùng Java Flight Recorder khi cần mức chi tiết thấp hơn JVM

BufferingApplicationStartup ghi các bước của Spring. Nó không thay thế profiler CPU, allocation, GC, class loading hoặc thread blocking.

Có thể dùng JFR khi chạy ứng dụng:

~~~bash
java -XX:StartFlightRecording:filename=startup.jfr,duration=10s -jar target/acme-startup-demo-1.0.0.jar
~~~

JFR hữu ích để:
- Tìm method tiêu tốn CPU.
- Xem class loading.
- Quan sát GC và allocation.
- Phát hiện thread bị block.
- Đối chiếu các sự kiện JVM với thời điểm Spring tạo bean.

Không nên kết luận từ một lần đo. So sánh nhiều lần trong cùng JDK, JVM flags, classpath, cấu hình, phần cứng và trạng thái phụ thuộc ngoài. Ghi rõ cold start hay warm start; không so sánh hai lần chạy có cache hoặc database khác nhau.

## 8. Ví dụ thực hành hoàn chỉnh: đo startup của một auto-configuration

Ví dụ sau tạo một ứng dụng Spring Boot nhỏ:
- Auto-configuration được nạp qua AutoConfiguration.imports.
- Bean AcmeClient được tạo khi acme.enabled=true.
- Ứng dụng dùng BufferingApplicationStartup.
- Actuator cung cấp endpoint /actuator/startup.

### 8.1. Cấu trúc thư mục

~~~text
acme-startup-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   ├── demo/app/
        │   │   ├── StartupDemoApplication.java
        │   │   └── AcmeController.java
        │   └── demo/acme/
        │       ├── AcmeClient.java
        │       └── autoconfigure/
        │           └── AcmeAutoConfiguration.java
        └── resources/
            ├── application.properties
            └── META-INF/spring/
                └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Package demo.acme.autoconfigure nằm ngoài package scan demo.app. Vì vậy, bean từ thư viện được đăng ký nhờ imports metadata, không phải do component scan vô tình tìm thấy configuration.

### 8.2. pom.xml

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

    <groupId>demo.acme</groupId>
    <artifactId>acme-startup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-actuator</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Trong dự án thư viện nhiều module, cấu hình annotation processor trong module autoconfigure. Ở lab một module, plugin được cấu hình ngay trong project để tạo spring-autoconfigure-metadata.properties.

### 8.3. AcmeClient.java

Tệp src/main/java/demo/acme/AcmeClient.java:

~~~java
package demo.acme;

public record AcmeClient(String state) {

    public String status() {
        return "acme:" + state;
    }
}
~~~

Client chỉ giữ state để output có thể dự đoán. Nó không thực hiện network call, nên thời gian startup của lab không bị chi phối bởi dịch vụ ngoài.

### 8.4. AcmeAutoConfiguration.java

Tệp src/main/java/demo/acme/autoconfigure/AcmeAutoConfiguration.java:

~~~java
package demo.acme.autoconfigure;

import demo.acme.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true",
        matchIfMissing = true
)
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient() {
        return new AcmeClient("ready");
    }
}
~~~

Class-level property condition cho phép processor ghi nhận điều kiện có thể lọc sớm. ConditionalOnMissingBean giữ khả năng ứng dụng thay thế client mặc định. AutoConfiguration vốn dùng proxyBeanMethods=false, phù hợp với auto-configuration không cần gọi chéo @Bean method thông qua proxy.

### 8.5. Đăng ký imports metadata

Tệp src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports có nội dung:

~~~text
demo.acme.autoconfigure.AcmeAutoConfiguration
~~~

Đây là resource giúp Boot phát hiện class. spring-autoconfigure-metadata.properties được processor tạo riêng để hỗ trợ lọc condition sớm.

### 8.6. StartupDemoApplication.java

Tệp src/main/java/demo/app/StartupDemoApplication.java:

~~~java
package demo.app;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

@SpringBootApplication(scanBasePackages = "demo.app")
public class StartupDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(StartupDemoApplication.class);

        application.setApplicationStartup(
                new BufferingApplicationStartup(2048)
        );

        application.run(args);
    }
}
~~~

scanBasePackages giới hạn component scan vào package của ứng dụng. Auto-configuration nằm ngoài package này nên phải được nạp qua imports file.

### 8.7. AcmeController.java

Tệp src/main/java/demo/app/AcmeController.java:

~~~java
package demo.app;

import demo.acme.AcmeClient;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AcmeController {

    private final ObjectProvider<AcmeClient> clients;

    public AcmeController(ObjectProvider<AcmeClient> clients) {
        this.clients = clients;
    }

    @GetMapping("/demo")
    public String demo() {
        AcmeClient client =
                clients.getIfAvailable(() -> new AcmeClient("disabled"));

        return client.status();
    }
}
~~~

ObjectProvider cho phép endpoint trả kết quả ngay cả khi property tắt auto-configuration. Nếu feature được bật mặc định, bean từ auto-configuration trả về acme:ready.

### 8.8. application.properties

Tệp src/main/resources/application.properties:

~~~properties
acme.enabled=true
management.endpoints.web.exposure.include=health,startup
~~~

Endpoint startup cần BufferingApplicationStartup; chỉ thêm Actuator dependency mà không cấu hình ApplicationStartup phù hợp sẽ không tạo timeline như mong đợi.

### 8.9. Build và chạy

Từ thư mục có pom.xml:

~~~bash
mvn clean package
java -jar target/acme-startup-demo-1.0.0.jar
~~~

Gọi endpoint ứng dụng:

~~~bash
curl http://localhost:8080/demo
~~~

Response body:

~~~text
acme:ready
~~~

Lấy startup timeline:

~~~bash
curl http://localhost:8080/actuator/startup
~~~

Response là JSON chứa springBootVersion, timeline.startTime và các timeline.events. Duration, số event và tag phụ thuộc máy, JDK, classpath và nội dung ứng dụng; không có một con số thời gian cố định để chép vào README.

Thử tắt auto-configuration bằng command line:

~~~bash
java -jar target/acme-startup-demo-1.0.0.jar --acme.enabled=false
~~~

Sau đó gọi /demo, response body mong đợi:

~~~text
acme:disabled
~~~

Test này minh họa bean condition hoạt động theo property. Nó không chứng minh hiệu năng được cải thiện bao nhiêu; muốn đo, hãy so sánh startup timeline ở cùng môi trường trước và sau thay đổi.

## 9. Spring AOT: chuyển một phần công việc sang build time

Spring AOT (Ahead-of-Time) phân tích ApplicationContext trong quá trình build để tạo các asset giúp runtime khởi động với cấu hình đã được xử lý trước.

AOT có thể tạo:
- Java source code cho việc khôi phục bean definitions.
- Bytecode, ví dụ cho dynamic proxies.
- RuntimeHints cho reflection, resource loading, serialization và JDK proxies.
- ApplicationContextInitializer để nạp cấu hình đã được xử lý.

Trong AOT processing, Spring chuẩn bị BeanFactory và xử lý bean definitions nhưng không khởi tạo toàn bộ bean instance như một lần chạy ứng dụng thông thường. Các quyết định cấu hình có thể được mã hóa vào code được sinh ra.

### 9.1. AOT khác metadata processor như thế nào?

| Cơ chế | Thời điểm | Đối tượng xử lý | Tác dụng |
| --- | --- | --- | --- |
| spring-boot-autoconfigure-processor | Compile module thư viện | Annotation condition trên auto-configuration classes | Sinh metadata để lọc sớm candidate không phù hợp |
| Spring AOT process-aot | Build ứng dụng | ApplicationContext của ứng dụng cụ thể | Sinh code và hints cho cấu hình bean của ứng dụng |
| GraalVM Native Image | Build native executable | Bytecode và asset AOT | Tạo executable native có thể khởi động nhanh và thường dùng ít memory hơn JVM |

Processor của thư viện giúp nhiều consumer lọc candidate tốt hơn khi chạy JVM. AOT lại phân tích một ứng dụng cụ thể với classpath và Environment đã biết. Native Image là bước biên dịch executable từ ứng dụng đã chuẩn bị phù hợp cho AOT.

AOT không phải tên khác của spring-autoconfigure-metadata.properties; hai cơ chế có phạm vi và thời điểm khác nhau.

### 9.2. Cấu hình process-aot bằng Maven

Có thể thêm execution process-aot cho Spring Boot Maven Plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>process-aot</id>
            <goals>
                <goal>process-aot</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

Khi build, plugin chuẩn bị ApplicationContext, đánh giá conditions trong môi trường build và ghi generated sources/classes/resources vào target/spring-aot/.

Với Maven project dùng spring-boot-starter-parent, profile native có thể giúp cấu hình các bước AOT/native build. Cần có GraalVM hoặc Buildpacks/Native Build Tools phù hợp để tạo native image.

Ví dụ kích hoạt native profile:

~~~bash
mvn -Pnative package
~~~

Sau khi JAR đã chứa AOT generated assets, có thể chạy trên JVM với AOT initialization để kiểm tra generated code:

~~~bash
java -Dspring.aot.enabled=true -jar target/acme-startup-demo-1.0.0.jar
~~~

Lệnh JVM AOT chỉ có ý nghĩa khi artifact đã được build kèm AOT assets. Nếu JAR không có generated code, bật system property không tự tạo code ở runtime.

### 9.3. Conditions được đánh giá ở build time

Đây là giới hạn quan trọng nhất khi bật AOT.

Ví dụ:

~~~java
@ConditionalOnProperty(
        prefix = "acme",
        name = "enabled",
        havingValue = "true"
)
@Bean
AcmeClient acmeClient() {
    return new AcmeClient("ready");
}
~~~

Khi process-aot chạy, Boot đánh giá condition dựa trên Environment tại build time. Nếu acme.enabled=true khi build, bean được đưa vào cấu hình đã sinh. Khi chạy AOT, không thể trông đợi đổi property thành false để loại bean đó khỏi cấu hình đã sinh.

Các giới hạn chính:
- Classpath phải được xác định đầy đủ khi build.
- Profile ảnh hưởng bean definitions phải được chọn khi build.
- Property ảnh hưởng sự tồn tại của bean qua @Conditional được đánh giá ở build time.
- Bean definitions không nên thay đổi tùy ý lúc runtime.
- Cơ chế đăng ký singleton động hoặc instance supplier tùy biến có thể không được AOT chuyển đổi.
- Bean type nên khai báo càng cụ thể càng tốt để AOT biết đầy đủ metadata.

Nếu hai môi trường cần tập bean khác nhau, có thể tạo hai artifact/build với Environment tương ứng. Không nên tạo một artifact AOT rồi kỳ vọng mọi điều kiện bật/tắt bean sẽ thay đổi tự do lúc runtime.

Các property chỉ thay đổi giá trị cấu hình của một bean đã được xác định cần được phân biệt với property làm bean có hay không. Giới hạn AOT tập trung vào những quyết định ảnh hưởng bean definitions.

### 9.4. RuntimeHints cho native image

Native image cần biết trước các thao tác động như reflection, đọc resource, serialization và tạo JDK proxy. Spring tự suy luận được nhiều trường hợp, nhưng thư viện vẫn có thể cần cung cấp hints.

Ví dụ đăng ký resource và reflection:

~~~java
package demo.acme.autoconfigure;

import demo.acme.AcmePayload;

import org.springframework.aot.hint.MemberCategory;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public class AcmeRuntimeHints implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern("acme/templates/*.txt");

        hints.reflection().registerType(
                AcmePayload.class,
                MemberCategory.INVOKE_DECLARED_CONSTRUCTORS,
                MemberCategory.INVOKE_PUBLIC_METHODS
        );
    }
}
~~~

Kích hoạt registrar bằng @ImportRuntimeHints trên configuration:

~~~java
package demo.acme.autoconfigure;

import org.springframework.context.annotation.Configuration;
import org.springframework.aot.hint.annotation.ImportRuntimeHints;

@Configuration(proxyBeanMethods = false)
@ImportRuntimeHints(AcmeRuntimeHints.class)
class AcmeNativeHintsConfiguration {
}
~~~

Đây là ví dụ minh họa; AcmePayload cần tồn tại trong dự án nếu muốn biên dịch code. Chỉ đăng ký đúng những thành viên thực sự được gọi qua reflection. Hints dư thừa có thể làm native image lớn hơn và che giấu thiết kế động không cần thiết.

Có thể kiểm thử hints bằng RuntimeHintsPredicates thay vì đợi tới native compilation mới phát hiện thiếu resource hoặc reflection entry.

### 9.5. AOT không loại bỏ chi phí tạo bean

Ngay cả khi dùng AOT:
- Bean instance vẫn phải được tạo ở runtime.
- Constructor và init callback vẫn chạy.
- Database connection và network call vẫn có chi phí.
- Server vẫn cần khởi động.
- Cache vẫn cần warm-up nếu ứng dụng yêu cầu.
- Code nghiệp vụ vẫn chạy như bình thường.

AOT chủ yếu chuyển việc khám phá, phân tích cấu hình và tạo một phần code khởi tạo từ runtime sang build time. Nó không làm cho một constructor mất 3 giây trở thành constructor không tốn thời gian.

### 9.6. Native image và JVM AOT có trade-off khác nhau

Native image thường có startup nhanh và memory footprint nhỏ hơn JVM tương ứng, nhưng:
- Build native image tốn thời gian và tài nguyên hơn.
- Reflection/resource/proxy cần hints phù hợp.
- Một số thư viện hoặc pattern động chưa tương thích hoàn toàn.
- Debug và profiling có khác biệt so với JVM.
- Cần test executable native thực tế, không chỉ test JVM.

JVM AOT vẫn chạy trên JVM và giữ hệ sinh thái JVM, nhưng dùng generated initialization code. Native image biên dịch thành executable riêng. Hãy đo trên workload và môi trường triển khai thực tế trước khi chọn.

## 10. Đọc kết quả và chọn đúng công cụ

| Triệu chứng | Công cụ nên dùng | Điều cần tìm |
| --- | --- | --- |
| Nhiều auto-configuration candidates | Kiểm tra imports và dependency tree | JAR nào đóng góp candidate không cần thiết |
| Candidate bị đánh giá nhiều lần | spring-autoconfigure-metadata.properties | Processor có sinh metadata và filter sớm được không |
| Condition custom chậm | Condition report, log và profiler | Condition nào làm I/O, scan hoặc tính toán nặng |
| Nhiều bean definitions | Actuator /beans, startup steps | Configuration hoặc component scan nào đăng ký quá nhiều bean |
| Một bean khởi tạo lâu | /actuator/startup, JFR | Constructor, init callback, dependency hoặc network call |
| Startup JVM vẫn nhiều parse/configuration | AOT processing và AOT JVM run | Generated initialization code có giảm bước runtime không |
| Native image thiếu class/resource | Native build log, RuntimeHints tests, tracing agent | Reflection, resource, serialization hoặc proxy chưa được khai báo |

Condition Evaluation Report trả lời vì sao một condition match hoặc no-match. Startup endpoint trả lời step nào tốn thời gian. JFR cho biết JVM đang làm gì ở mức CPU, allocation, class loading và GC. Không dùng một công cụ để trả lời mọi câu hỏi.

## 11. Quy trình tối ưu startup có thể lặp lại

1. Ghi baseline bằng cùng JDK, JVM flags, classpath, profile và cấu hình triển khai.
2. Dùng BufferingApplicationStartup để thu timeline.
3. Xác định thời gian nằm ở candidate/condition, bean creation, server startup hay runner của ứng dụng.
4. Kiểm tra imports và dependency tree để tìm starter/integration không cần.
5. Bật annotation processor trong module auto-configuration.
6. Xem condition nào có custom logic tốn kém hoặc phạm vi quá rộng.
7. Kiểm tra các bean khởi tạo chậm bằng timeline và JFR.
8. Làm constructor/init callback nhẹ, thêm timeout và tách warm-up tùy chọn.
9. Chỉ dùng lazy khi chấp nhận chi phí chuyển sang lần sử dụng đầu tiên.
10. Đo lại trong cùng môi trường và so sánh step duration.
11. Nếu mục tiêu triển khai phù hợp, build AOT và chạy AOT-processed JVM.
12. Nếu chọn native image, bổ sung RuntimeHints và test executable native.
13. Lặp lại sau mỗi thay đổi lớn về dependency, Boot version hoặc module integration.

Khi benchmark, ghi lại cả total startup và các step quan trọng. Đừng chỉ so sánh một con số tổng; nếu tổng giảm nhưng request đầu tiên tăng mạnh do lazy initialization, cần quyết định dựa trên mục tiêu latency thực tế.

## 12. Những lỗi phổ biến khi tối ưu auto-configuration

1. **Nghĩ rằng mọi candidate đều tạo bean.** Candidate có thể bị loại bởi metadata hoặc condition.
2. **Nhầm imports file với autoconfigure metadata.** Một file khai báo candidates; file kia hỗ trợ lọc sớm conditions.
3. **Nhầm configuration metadata với autoconfigure metadata.** spring-configuration-metadata.json chủ yếu phục vụ IDE và tài liệu properties.
4. **Không bật annotation processor.** Thư viện có thể thiếu metadata filter sớm.
5. **Đưa processor vào runtime dependencies.** Processor là công cụ compile-time, không phải dependency ứng dụng cần khi chạy.
6. **Cho rằng processor xử lý mọi custom condition.** Chỉ condition mà processor có thể thu thập từ metadata mới được lọc sớm.
7. **Dùng component scan rộng trong thư viện.** Có thể đăng ký component ngoài dự kiến và làm tăng số bean definitions.
8. **Viết custom condition có I/O.** Một condition chờ database hoặc HTTP làm cấu hình chậm và khó tái lập.
9. **Tham chiếu bean trong @ConditionalOnExpression.** Bean có thể bị khởi tạo quá sớm và chưa được post-process đầy đủ.
10. **Dùng ordering để điều khiển instance creation.** Ordering auto-configuration chỉ ảnh hưởng bean definition order.
11. **Đưa công việc nặng vào constructor.** Mỗi lần khởi tạo bean có thể kéo dài refresh.
12. **Dùng lazy cho mọi bean mà không đo.** Chi phí và lỗi có thể chuyển sang request đầu tiên.
13. **Nhầm bean definition với bean instance.** Có definition không có nghĩa instance đã được tạo.
14. **Không đo phần runner và startup callback.** ApplicationRunner/CommandLineRunner cũng có thể kéo dài thời gian trước readiness.
15. **Bỏ qua external I/O.** Database migration, remote call hoặc cache warm-up có thể lớn hơn chi phí auto-configuration.
16. **Chỉ đo một lần.** JIT, file cache, database state và tải máy làm số đo dao động.
17. **So sánh hai môi trường khác nhau.** Khác JDK, memory, profile hoặc dependency sẽ làm kết quả không công bằng.
18. **Cho rằng AOT vẫn đánh giá property condition lúc runtime.** Bean-presence conditions đã được đánh giá khi build AOT.
19. **Cho rằng AOT tự giải quyết mọi reflection.** Một số dynamic access và resource vẫn cần RuntimeHints.
20. **Cho rằng native image luôn phù hợp.** Build cost, compatibility và quy trình vận hành cũng cần được cân nhắc.
21. **Không test native executable.** JVM test không chứng minh native image có đủ hints.
22. **Expose startup endpoint công khai.** Dữ liệu nội bộ về bean và startup steps cần được bảo vệ.
23. **Chỉ nhìn total startup.** Cần xem step để biết thời gian nằm ở parse, bean creation hay I/O.
24. **Tối ưu khi chưa có baseline.** Có thể làm code phức tạp hơn mà không cải thiện điểm nghẽn thực tế.

## 13. Checklist nghiệm thu hiệu năng và AOT

- [ ] Đã xác định candidate đến từ những imports file nào.
- [ ] Imports chỉ chứa auto-configuration thực sự thuộc artifact.
- [ ] Starter không kéo integration tùy chọn không cần thiết.
- [ ] Không dùng component scan rộng trong thư viện auto-configuration.
- [ ] spring-boot-autoconfigure-processor được cấu hình trong module chứa auto-config.
- [ ] Đã kiểm tra META-INF/spring-autoconfigure-metadata.properties sau build.
- [ ] Không nhầm file auto-config metadata với configuration metadata JSON.
- [ ] Condition custom không thực hiện I/O hoặc khởi tạo bean.
- [ ] Condition được đặt đúng phạm vi class/nested configuration/bean method.
- [ ] Bean definitions không bị đăng ký trùng.
- [ ] Constructor và init callback không có công việc nặng không cần thiết.
- [ ] I/O có timeout và có chiến lược readiness rõ ràng.
- [ ] Lazy initialization được dùng có chọn lọc và đã đo first-use latency.
- [ ] Startup timeline được ghi bằng BufferingApplicationStartup.
- [ ] Startup endpoint chỉ được expose trong phạm vi quản trị được bảo vệ.
- [ ] JFR được dùng khi cần xem CPU, allocation, GC hoặc class loading.
- [ ] Baseline và kết quả sau tối ưu được đo trong cùng môi trường.
- [ ] AOT build dùng đúng profile và Environment.
- [ ] Các property/profile ảnh hưởng bean presence được cố định khi AOT build.
- [ ] RuntimeHints đã bao phủ reflection/resource/serialization/proxy cần thiết.
- [ ] Đã chạy AOT-processed JVM nếu dùng AOT.
- [ ] Đã test native executable nếu triển khai Native Image.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** AutoConfiguration.imports dùng để làm gì?  
**Đáp án:** Khai báo danh sách auto-configuration classes mà Spring Boot có thể phát hiện từ JAR trên classpath.

**Câu 2.** spring-autoconfigure-metadata.properties khác imports file thế nào?  
**Đáp án:** Imports khai báo candidates; autoconfigure metadata hỗ trợ lọc sớm một số candidate dựa trên condition mà processor thu thập được.

**Câu 3.** spring-configuration-metadata.json có lọc auto-configuration không?  
**Đáp án:** Không. Nó chủ yếu cung cấp metadata cho IDE, autocomplete và tài liệu configuration properties.

**Câu 4.** Vì sao nên dùng spring-boot-autoconfigure-processor?  
**Đáp án:** Processor thu thập condition metadata lúc compile để Boot có thể eager-filter các auto-configuration không match, giảm công việc lúc startup.

**Câu 5.** Candidate đã được phát hiện có nghĩa là bean đã được tạo chưa?  
**Đáp án:** Chưa. Candidate có thể bị condition loại; configuration có thể đăng ký definitions nhưng bean instance chỉ được tạo theo scope, lazy và dependency.

**Câu 6.** Lazy initialization có loại bỏ condition evaluation không?  
**Đáp án:** Không. Nó trì hoãn tạo instance; candidate discovery, condition evaluation và bean-definition registration vẫn diễn ra.

**Câu 7.** Dùng công cụ nào để xem thời gian từng Spring startup step?  
**Đáp án:** Cấu hình BufferingApplicationStartup và đọc Actuator /actuator/startup; dùng JFR cho profiling sâu hơn ở JVM.

**Câu 8.** AOT đánh giá @ConditionalOnProperty ở thời điểm nào?  
**Đáp án:** Khi build AOT, theo Environment của quá trình build. Điều kiện ảnh hưởng bean presence không thể được kỳ vọng bật/tắt tự do lúc runtime của artifact AOT.

**Câu 9.** AOT có làm constructor nặng trở nên miễn phí không?  
**Đáp án:** Không. Bean instance vẫn được tạo lúc runtime; constructor, I/O và init callbacks vẫn tốn thời gian.

**Câu 10.** RuntimeHints dùng để làm gì?  
**Đáp án:** Cung cấp thông tin cho native image về reflection, resource loading, serialization và JDK proxies mà Spring/GraalVM không thể suy ra đầy đủ.

## 15. Tài liệu tham khảo chính thức

- [Spring Boot 3.3.13 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html).
- [Spring Boot 3.3.13 — Ahead-of-Time Processing Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html).
- [Spring Boot 3.3.13 — Application Startup Actuator Endpoint](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/startup.html).
- [Spring Boot 3.3.13 — BufferingApplicationStartup API](https://docs.spring.io/spring-boot/3.3/api/kotlin/spring-boot-project/spring-boot/org.springframework.boot.context.metrics.buffering/-buffering-application-startup/index.html).
- [Spring Boot 3.3.13 — Advanced Native Images Topics and RuntimeHints](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html).
- [Spring Boot 3.3.13 — GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/index.html).
- [Spring Framework — Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html).