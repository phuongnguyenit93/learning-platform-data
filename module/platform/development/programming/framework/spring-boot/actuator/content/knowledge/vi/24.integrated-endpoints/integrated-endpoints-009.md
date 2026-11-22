# Đánh giá điều kiện dependency, bean và quyền truy cập của từng endpoint tích hợp

## 1. Một URL endpoint hoạt động nhờ nhiều điều kiện khác nhau

Thêm `spring-boot-starter-actuator` không bảo đảm mọi endpoint tích hợp đều có URL gọi được hoặc đều trả dữ liệu có ích.

Ví dụ, cùng một biểu hiện “không đọc được HTTP exchanges” có thể đến từ các nguyên nhân khác nhau:

- Không có bean lưu HTTP exchanges.
- Endpoint bị tắt hoặc chưa công bố qua HTTP.
- Đang gọi sai cổng quản trị.
- Yêu cầu bị lớp bảo mật chặn.
- Endpoint đọc được nhưng kho chưa ghi nhận yêu cầu nào.

Cách đánh giá đúng là tách các lớp điều kiện:

~~~text
Dependency có trong runtime classpath
                ↓
Bean và hạ tầng ứng dụng cần thiết đã được tạo
                ↓
Endpoint được bật và đủ điều kiện tự cấu hình
                ↓
Endpoint được công bố qua đúng kênh HTTP/JMX
                ↓
Đúng địa chỉ, đường dẫn, method và tham số
                ↓
Được xác thực, phân quyền và đáp ứng CSRF nếu áp dụng
                ↓
Thao tác có nguồn dữ liệu/tài nguyên runtime phù hợp
~~~

Sơ đồ là mô hình để điều tra, không phải cam kết rằng mọi bộ lọc bảo mật chạy sau định tuyến trong nội bộ framework. Trong một ứng dụng cụ thể, lớp bảo mật có thể xử lý yêu cầu trước khi biết nó có ánh xạ endpoint phù hợp hay không.

**Dependency**, **bean**, **enabled**, **exposure** và **quyền truy cập** trả lời những câu hỏi khác nhau. Bài này dùng Spring Boot **3.3.x**, với thí nghiệm cố định **3.3.0** và Java **17 trở lên**.

## 2. Phân biệt năm khái niệm trước khi đọc cấu hình

| Khái niệm | Câu hỏi cần trả lời | Bằng chứng phù hợp |
| --- | --- | --- |
| Dependency | Lớp thư viện cần thiết có trong tiến trình đang chạy không? | Runtime dependency graph, nội dung bản đóng gói |
| Bean/hạ tầng | Đối tượng mà endpoint dùng có được tạo và cấu hình đúng không? | ApplicationContext, báo cáo điều kiện, log khởi tạo |
| Enabled | Cấu hình có cho phép endpoint được bật không? | `management.endpoint.<id>.enabled` và cấu hình mặc định |
| Exposure | Endpoint có được đưa ra kênh HTTP/JMX đang xét không? | `management.endpoints.<channel>.exposure.*`, ánh xạ thực tế |
| Quyền và khả năng thực thi | Người gọi có được thực hiện đúng thao tác, và thao tác có dữ liệu/tài nguyên không? | Security configuration, request/response, tình trạng nguồn dữ liệu |

Một dependency chỉ khai báo ở `testImplementation` không chứng minh nó có trong ứng dụng triển khai. Tương tự, nhìn thấy một lớp trong file JAR không chứng minh bean tương ứng đã được tạo.

Tự cấu hình thường kết hợp các điều kiện như:

- `@ConditionalOnClass`: có lớp cần thiết.
- `@ConditionalOnBean`: đã có bean cần thiết.
- `@ConditionalOnMissingBean`: nhường quyền cho cấu hình do ứng dụng cung cấp.
- `@ConditionalOnWebApplication`: đúng loại ứng dụng web.
- `@ConditionalOnAvailableEndpoint`: đáp ứng điều kiện bật/công bố endpoint.

Không đọc một annotation riêng lẻ rồi bỏ qua các điều kiện còn lại. Nếu ứng dụng cung cấp endpoint hoặc hạ tầng riêng, tự cấu hình mặc định có thể chủ ý không chạy.

Trong Boot 3.3, endpoint được xem là available khi được bật và được công bố; điều kiện dependency/bean riêng vẫn phải thỏa mãn. Nguồn: [mô hình endpoint của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html).

## 3. Bảng đánh giá các endpoint theo nguồn dữ liệu và điều kiện nền tảng

Các bảng dưới đây dùng để nhận diện điều kiện chính của các endpoint tích hợp trong nhánh Boot 3.3. Chúng **không thay thế** việc đối chiếu annotation và cấu hình hiệu lực của phiên bản vá đang chạy. Quyền GET/POST/DELETE trong ứng dụng là chính sách bảo mật do ứng dụng thiết lập, không có một role mặc định chung cho từng dòng.

### 3.1. Endpoint dựa chủ yếu vào context, môi trường hoặc hạ tầng JVM

| Endpoint | Dependency/bean/hạ tầng cần xét | Điều cần đánh giá tiếp |
| --- | --- | --- |
| `health` | Hạ tầng health và các contributor do Boot/ứng dụng cấu hình | Trạng thái và quyền xem chi tiết; HTTP `503` có thể phản ánh health xấu |
| `info` | Các `InfoContributor` và nguồn thông tin tương ứng | `200 {}` có thể chỉ là chưa có thông tin được đóng góp |
| `beans` | ApplicationContext và các bean trong context | Thông tin cấu trúc ứng dụng cần được giới hạn người xem |
| `conditions` | Báo cáo điều kiện của cơ chế tự cấu hình | Dùng để giải thích vì sao cấu hình khớp/không khớp, không phải danh sách lỗi bắt buộc sửa |
| `env` | `Environment` của ứng dụng | Quyền gọi và chính sách hiển thị giá trị là hai lớp riêng |
| `configprops` | Hạ tầng configuration properties và các bean tương ứng | Không có nhóm cấu hình mong đợi có thể do bean chưa được tạo/bind |
| `mappings` | Các thành phần cung cấp ánh xạ trong stack web/context đang dùng | Đọc đúng context/cổng; không suy mọi mapping là API công khai |
| `scheduledtasks` | Hạ tầng và các đối tượng cung cấp tác vụ đã đăng ký | Có endpoint chưa có nghĩa ứng dụng có tác vụ định kỳ để liệt kê |
| `loggers` | `LoggingSystem` phù hợp và đang được bật | Đọc logger và đổi mức log có mức quyền/tác động khác nhau |
| `threaddump` | Hạ tầng chẩn đoán luồng của runtime JVM | Quyền đọc thông tin luồng và chi phí thu thập; không cần tự tạo HTTP controller thay thế |

Đối với nhóm này, “không cần thư viện nghiệp vụ tùy chọn” không có nghĩa “không có điều kiện nào”. Ví dụ `loggers` vẫn phụ thuộc hệ thống logging, và nội dung `info` vẫn phụ thuộc các contributor/nguồn dữ liệu.

### 3.2. Endpoint gắn với thư viện hoặc bean chuyên biệt

| Endpoint | Điều kiện chính cần xác minh | Phân biệt quan trọng |
| --- | --- | --- |
| `auditevents` | Bean `AuditEventRepository` | Có cơ chế xác thực không tự bảo đảm đã có kho audit cho endpoint |
| `httpexchanges` | Bean `HttpExchangeRepository` | Kho tồn tại khác với có dữ liệu đã ghi; kho trong bộ nhớ có giới hạn lưu giữ |
| `metrics` | Hạ tầng Micrometer, bean `MeterRegistry` | Có registry khác với có đúng meter cần hỏi |
| `prometheus` | `micrometer-registry-prometheus` và registry/hạ tầng Prometheus tương ứng | Có `metrics` không tự tạo endpoint scrape Prometheus |
| `caches` | Lớp `CacheManager` của Spring; endpoint nhận các manager trong context | Boot 3.3 có thể tạo endpoint với tập manager rỗng; không ép “phải có một CacheManager” thành điều kiện tạo bean |
| `flyway` | Lớp và bean `Flyway` | Chỉ thêm driver cơ sở dữ liệu chưa tạo ra một Flyway bean phù hợp |
| `liquibase` | Lớp và bean `SpringLiquibase` | Một cơ sở dữ liệu có lịch sử migration không đồng nghĩa ứng dụng đang cấu hình Liquibase |
| `quartz` | Lớp và bean Quartz `Scheduler` | Tác vụ `@Scheduled` không tự trở thành Quartz job |
| `integrationgraph` | Spring Integration và hạ tầng Integration đã được khởi tạo | Chỉ có tên thư viện chưa chứng minh các thành phần Integration đã được đăng ký |
| `sessions` | Spring Session và kho đúng stack: `SessionRepository` hoặc `ReactiveSessionRepository` | Tra theo username còn cần khả năng chỉ mục tương ứng; đọc/xóa theo ID là khả năng khác |

Các điều kiện `Flyway`, `SpringLiquibase`, `Scheduler` và Integration có thể đối chiếu tại mã tự cấu hình của [Flyway](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/flyway/FlywayEndpointAutoConfiguration.java), [Liquibase](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/liquibase/LiquibaseEndpointAutoConfiguration.java), [Quartz](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/quartz/QuartzEndpointAutoConfiguration.java) và [Integration Graph](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/integration/IntegrationGraphEndpointAutoConfiguration.java).

Với `sessions`, cần lưu ý phiên bản: bảng tổng quan Boot 3.3 mô tả yêu cầu Servlet, nhưng [mã v3.3.0](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/session/SessionsEndpointAutoConfiguration.java) đã có nhánh Servlet và reactive. Khi tài liệu tổng quan và mã khác nhau, phải kiểm tra đúng stack và implementation đang triển khai.

Riêng `metrics` và `prometheus`, cần phân biệt registry tổng quát với registry phục vụ một hệ thống giám sát cụ thể. Tham khảo [tự cấu hình Micrometer và các registry của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 3.3. Endpoint còn phụ thuộc cách khởi động hoặc tài nguyên runtime

| Endpoint | Điều kiện cần xét | Điều không được suy luận |
| --- | --- | --- |
| `startup` | Dùng `BufferingApplicationStartup` đúng lúc khởi tạo ứng dụng | Công bố endpoint không thể thu lại các bước khởi động chưa từng được ghi |
| `logfile` | Có cấu hình tệp log hoặc tệp ngoài phù hợp; tệp cần đọc được | Log xuất ra console không tự thành một file để endpoint tải |
| `heapdump` | Kênh web và runtime JVM hỗ trợ cơ chế dump tương ứng | GET vẫn có thể tạo tác động đáng kể về tài nguyên và tạo dữ liệu nhạy cảm |
| `shutdown` | Bị tắt mặc định; cần bật/công bố và mô hình triển khai được hỗ trợ | Không dùng endpoint này như phép thử đọc; đây là thao tác dừng ứng dụng |
| `sbom` | Có trong Boot 3.3; nội dung phụ thuộc các tài nguyên SBOM được cung cấp/cấu hình | Có endpoint không tự chứng minh đã sinh tài liệu thành phần phần mềm |

`logfile` là ví dụ điển hình của hai lớp điều kiện: bean endpoint có thể được tạo khi cấu hình tệp thỏa mãn, nhưng yêu cầu đọc vẫn cần tài nguyên thực tế. Xem [tự cấu hình LogFileWebEndpoint](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/logging/LogFileWebEndpointAutoConfiguration.java).

Với `startup`, ứng dụng cần chọn cơ chế ghi từ trước khi chạy, chẳng hạn đoạn ghép vào phương thức khởi động đã có:

~~~java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setApplicationStartup(new BufferingApplicationStartup(2048));
application.run(args);
~~~

Đoạn này dùng `SpringApplication` của Boot và `BufferingApplicationStartup` từ `org.springframework.boot.context.metrics.buffering`; nó không phải chương trình Java độc lập. Điều kiện endpoint nằm tại [StartupEndpointAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/startup/StartupEndpointAutoConfiguration.java).

## 4. Đọc enabled và exposure như hai quyết định độc lập

Ví dụ cấu hình quản trị cho một ứng dụng web hiện có:

~~~yaml
management:
  server:
    port: 9090
    address: 127.0.0.1
  endpoints:
    enabled-by-default: false
    web:
      base-path: /manage
      exposure:
        include: health,info,httpexchanges
  endpoint:
    health:
      enabled: true
    info:
      enabled: true
    httpexchanges:
      enabled: true
~~~

Địa chỉ cần kiểm tra cho HTTP exchanges là:

~~~text
http://localhost:9090/manage/httpexchanges
~~~

Cấu hình trên chưa tạo `HttpExchangeRepository` và chưa thiết lập chính sách quyền truy cập. Nó chỉ giải quyết các lựa chọn bật/công bố và địa chỉ quản trị.

Một bean dùng cho lab có thể được đăng ký trong lớp `@Configuration` của ứng dụng:

~~~java
@Bean
HttpExchangeRepository httpExchangeRepository() {
    return new InMemoryHttpExchangeRepository();
}
~~~

Đoạn này cần import `Bean`, `HttpExchangeRepository` và `InMemoryHttpExchangeRepository` tương ứng. Kho trong bộ nhớ phục vụ thí nghiệm/chẩn đoán ngắn hạn, không mặc nhiên là kho lịch sử bền vững.

Ba quy tắc cần kiểm tra:

1. `enabled=true` không tự đưa endpoint ra HTTP.
2. `exposure.include` không tự bật endpoint đã bị tắt.
3. `exposure.exclude` được ưu tiên hơn `include`.

Nếu endpoint còn được công bố qua JMX, việc loại khỏi HTTP không nhất thiết làm endpoint bean biến mất. Phải phân biệt **bean tồn tại** với **có ánh xạ HTTP**. Thí nghiệm phần sau giới hạn cấu hình để không có một kênh công bố khác giữ endpoint được kiểm tra.

## 5. Thí nghiệm Java kiểm chứng điều kiện tạo endpoint

Ví dụ dùng `ApplicationContextRunner` để tạo các context nhỏ, thay đổi từng điều kiện rồi đóng context. Đây là công cụ của thư viện kiểm thử Boot; chương trình chạy độc lập để quan sát tự cấu hình, **không mở máy chủ HTTP**.

Nó chỉ nạp hai lớp tự cấu hình được chỉ định. Vì vậy, kết quả chứng minh các điều kiện của những cấu hình đó, không thay thế phép thử định tuyến hoặc bảo mật của toàn ứng dụng.

### 5.1. Dependency

Trong thư mục lab riêng, tạo `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.0</version>
        <relativePath/>
    </parent>
    <groupId>learning</groupId>
    <artifactId>endpoint-conditions-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-actuator-autoconfigure</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-test</artifactId>
        </dependency>
        <dependency>
            <groupId>org.assertj</groupId>
            <artifactId>assertj-core</artifactId>
        </dependency>
    </dependencies>
</project>
~~~

Các dependency kiểm thử được đặt trên classpath biên dịch của chương trình lab vì nó chạy bằng `main`. Trong ứng dụng thật, không chuyển thư viện kiểm thử sang runtime chỉ để có endpoint.

### 5.2. Chương trình đầy đủ

Đặt `EndpointConditionsDemo.java` cùng cấp với `pom.xml`:

~~~java
import org.springframework.boot.actuate.autoconfigure.cache.CachesEndpointAutoConfiguration;
import org.springframework.boot.actuate.autoconfigure.web.exchanges.HttpExchangesEndpointAutoConfiguration;
import org.springframework.boot.actuate.cache.CachesEndpoint;
import org.springframework.boot.actuate.web.exchanges.HttpExchangeRepository;
import org.springframework.boot.actuate.web.exchanges.InMemoryHttpExchangeRepository;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

public class EndpointConditionsDemo {
    public static void main(String[] args) {
        var base = new ApplicationContextRunner().withConfiguration(
                AutoConfigurations.of(
                        HttpExchangesEndpointAutoConfiguration.class,
                        CachesEndpointAutoConfiguration.class));

        var exposed = base.withPropertyValues(
                "management.endpoints.web.exposure.include=httpexchanges,caches");
        var withRepository = exposed.withBean(
                HttpExchangeRepository.class, InMemoryHttpExchangeRepository::new);

        show("exposed, no repository", exposed);
        show("exposed, with repository", withRepository);
        show("disabled", withRepository.withPropertyValues(
                "management.endpoint.httpexchanges.enabled=false"));
        show("excluded from web", withRepository.withPropertyValues(
                "management.endpoints.web.exposure.exclude=httpexchanges"));
        show("default exposure", base.withBean(
                HttpExchangeRepository.class, InMemoryHttpExchangeRepository::new));
        show("enabled explicitly, default exposure", base.withBean(
                HttpExchangeRepository.class, InMemoryHttpExchangeRepository::new)
                .withPropertyValues("management.endpoint.httpexchanges.enabled=true"));

        exposed.run(context -> {
            if (context.getStartupFailure() != null) {
                throw new IllegalStateException(context.getStartupFailure());
            }
            var caches = context.getBean(CachesEndpoint.class);
            System.out.println("caches without CacheManager: managers="
                    + caches.caches().getCacheManagers().size());
        });
    }

    private static void show(String label, ApplicationContextRunner runner) {
        runner.run(context -> {
            if (context.getStartupFailure() != null) {
                throw new IllegalStateException(context.getStartupFailure());
            }
            System.out.println(label + ": httpexchanges bean="
                    + context.containsBean("httpExchangesEndpoint"));
        });
    }
}
~~~

Thí nghiệm dựa trên điều kiện bean của [HttpExchangesEndpointAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/web/exchanges/HttpExchangesEndpointAutoConfiguration.java) và cách nhận tập cache manager của [CachesEndpointAutoConfiguration](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/cache/CachesEndpointAutoConfiguration.java).

### 5.3. Biên dịch và chạy

Yêu cầu JDK 17+, Maven; lần đầu lấy dependency cần kết nối kho Maven.

Windows PowerShell:

~~~powershell
mvn -q dependency:build-classpath "-Dmdep.outputFile=classpath.txt"
$conditionsClasspath = (Get-Content -LiteralPath .\classpath.txt -Raw).Trim()
javac --release 17 -cp "$conditionsClasspath" EndpointConditionsDemo.java
java -cp ".;$conditionsClasspath" EndpointConditionsDemo
~~~

Linux/macOS:

~~~shell
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
conditions_classpath="$(cat classpath.txt)"
javac --release 17 -cp "$conditions_classpath" EndpointConditionsDemo.java
java -cp ".:$conditions_classpath" EndpointConditionsDemo
~~~

Stdout:

~~~text
exposed, no repository: httpexchanges bean=false
exposed, with repository: httpexchanges bean=true
disabled: httpexchanges bean=false
excluded from web: httpexchanges bean=false
default exposure: httpexchanges bean=false
enabled explicitly, default exposure: httpexchanges bean=false
caches without CacheManager: managers=0
~~~

Diễn giải:

- Chỉ công bố `httpexchanges` mà thiếu kho dữ liệu không tạo endpoint bean.
- Khi có kho và cấu hình công bố, endpoint bean được tạo.
- Tắt endpoint hoặc loại khỏi web đều làm điều kiện không khớp trong phạm vi context đang xét.
- Có kho và bật tường minh vẫn không đủ khi dùng exposure mặc định không chọn endpoint đó.
- `caches` tồn tại và trả tập manager rỗng. Đây là bằng chứng rằng không được áp một quy tắc “mọi endpoint dữ liệu đều phải có ít nhất một bean nguồn” cho tất cả endpoint.

## 6. Quyền gọi URL khác với quyền xem giá trị bên trong

Sau khi xác nhận endpoint có ánh xạ, tiếp tục xem chính sách bảo mật.

### 6.1. Xác thực và phân quyền

- **Xác thực:** người gọi là ai, hoặc có thông tin xác thực hợp lệ không.
- **Phân quyền:** người gọi được thực hiện thao tác cụ thể nào.
- **Hiển thị dữ liệu:** nội dung nào được trả cho người gọi đã được phép vào endpoint.

Ba việc không đồng nhất. Một tài khoản được GET `env` vẫn có thể chỉ thấy giá trị đã che; người được đọc logger không nhất thiết được thay đổi mức log.

Các endpoint `env`, `configprops` và `quartz` có chính sách `show-values`; `health` có các thiết lập hiển thị chi tiết/thành phần. Không dùng `show-values=always` như cách “sửa lỗi 403”: nó không tạo quyền truy cập URL mà thay đổi nội dung được hiển thị.

Ví dụ chính sách cần xây cho từng nhóm thao tác:

| Nhóm/thao tác | Điều cần quyết định |
| --- | --- |
| `health` tối thiểu | Ai được đọc trạng thái; ai được xem chi tiết |
| `info`, `metrics`, `prometheus` | Người vận hành/hệ thống giám sát nào cần truy cập |
| `beans`, `conditions`, `mappings`, `env`, `configprops` | Ai được đọc thông tin cấu trúc/cấu hình |
| `auditevents`, `httpexchanges`, `sessions` | Ai được đọc dữ liệu liên quan hoạt động/người dùng |
| `flyway`, `liquibase`, `quartz`, `integrationgraph`, `scheduledtasks`, `startup`, `sbom` | Ai cần quan sát nguồn dữ liệu hoặc hạ tầng tương ứng |
| `loggers` khi đổi mức log; `caches`/`sessions` khi xóa | Quyền thay đổi trạng thái, khác với chỉ đọc |
| `logfile`, `threaddump`, `heapdump` | Quyền thu thập chẩn đoán và phạm vi dữ liệu/tài nguyên được phép |
| `shutdown` | Quyền dừng ứng dụng, cần được xem riêng với mọi quyền đọc |

Đây là các quyết định chính sách của ứng dụng, không phải tên role mà Boot tự cấp sẵn.

### 6.2. Cấu hình SecurityFilterChain riêng cần bao phủ cả ứng dụng

Nếu có Spring Security và ứng dụng chưa cung cấp `SecurityFilterChain`, Boot có cơ chế bảo vệ Actuator mặc định. Khi tự khai báo chain, cần tự chịu trách nhiệm cho phạm vi mà cấu hình mặc định nhường lại.

Ví dụ dưới đây là **cấu hình minh họa cho ứng dụng Servlet có Spring Security**, dùng các role do hệ thống xác thực hiện có cung cấp:

~~~java
import org.springframework.boot.actuate.autoconfigure.security.servlet.EndpointRequest;
import org.springframework.boot.actuate.health.HealthEndpoint;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration(proxyBeanMethods = false)
public class ActuatorSecurityConfiguration {
    @Bean
    @Order(1)
    SecurityFilterChain actuatorChain(HttpSecurity http) throws Exception {
        http.securityMatcher(EndpointRequest.toAnyEndpoint());
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(EndpointRequest.to(HealthEndpoint.class)).permitAll()
                .requestMatchers(EndpointRequest.to("info", "metrics", "prometheus"))
                    .hasAnyRole("ACTUATOR_VIEW", "ACTUATOR_ADMIN")
                .anyRequest().hasRole("ACTUATOR_ADMIN"));
        http.httpBasic(withDefaults());
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .anyRequest().authenticated());
        http.httpBasic(withDefaults());
        return http.build();
    }
}
~~~

Ví dụ chỉ cấp nhóm quan sát cho `info`, `metrics`, `prometheus`; các endpoint còn lại yêu cầu quyền quản trị kể cả khi dùng GET, ngoại trừ health tối thiểu được cho phép ở trên. Matcher dùng ID endpoint nên không hard-code base path; xem [API EndpointRequest](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/security/servlet/EndpointRequest.html).

Cấu hình này không tự tạo tài khoản và không tự gán role. `hasRole("ACTUATOR_ADMIN")` xét authority theo quy ước tiền tố `ROLE_` của Spring Security.

Chain đầu chỉ xét phạm vi Actuator; chain sau bao phủ yêu cầu còn lại. Trước khi ghép vào ứng dụng đã có các chain, phải đối chiếu thứ tự và phạm vi hiện tại thay vì thêm một chain trùng trách nhiệm.

### 6.3. CSRF là điều kiện riêng của thao tác thay đổi

Cấu hình minh họa giữ bảo vệ CSRF mặc định. Do đó, người có role quản trị nhưng gửi POST/DELETE mà thiếu token CSRF hợp lệ vẫn có thể nhận `403`.

Không suy từ “GET thành công” rằng DELETE cũng sẽ thành công. Cũng không tắt CSRF toàn ứng dụng chỉ để bỏ qua bước xác định nguyên nhân.

Nếu một API chỉ dành cho máy khách không phải trình duyệt cần chiến lược khác, phải quyết định theo mô hình xác thực và phạm vi endpoint cụ thể. Nguồn: [bảo mật và CSRF của Actuator trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.security).

## 7. Đánh giá đến mức thao tác và dữ liệu, không chỉ tên endpoint

Một endpoint có thể có nhiều thao tác với yêu cầu khác nhau.

Ví dụ:

- `caches`: đọc danh sách khác với DELETE làm rỗng cache.
- `sessions`: đọc/xóa theo ID khác với tìm theo principal khi cần kho chỉ mục.
- `loggers`: đọc mức log khác với thay đổi mức log.
- `health`: đọc trạng thái tối thiểu khác với xem đầy đủ chi tiết.
- `metrics`: đọc tên meter khác với hỏi một meter hoặc tổ hợp tag cụ thể có tồn tại không.

Với mỗi thao tác cần ghi lại:

~~~text
ID endpoint
+ HTTP method và đường dẫn
+ dependency/runtime cần thiết
+ bean nguồn dữ liệu
+ cấu hình enabled/exposure hiệu lực
+ quyền người gọi và điều kiện CSRF
+ tài nguyên/tham số cụ thể
+ bằng chứng phản hồi
~~~

Không cần mở mọi endpoint để kiểm tra một chức năng. Ví dụ, muốn xác nhận scrape Prometheus thì kiểm tra đúng registry, cấu hình endpoint và quyền của máy scrape; không dùng `include: "*"` như một phương pháp chẩn đoán mặc định.

Cũng cần phân biệt kiểu phản hồi: nhiều endpoint trả JSON, nhưng Prometheus phục vụ định dạng scrape, heap dump trả dữ liệu chẩn đoán dạng tệp và logfile trả nội dung log. Header `Accept` hoặc method không phù hợp có thể tạo lỗi khác với lỗi quyền.

## 8. Chẩn đoán theo bằng chứng từ trong ra ngoài

### 8.1. Xác nhận đúng bản chạy và dependency runtime

Trong dự án Gradle, có thể dùng báo cáo runtime classpath hoặc `dependencyInsight` theo module đang chạy để kiểm tra thư viện và phiên bản thực tế.

Không chỉ đọc dependency khai báo ở root build, vì cấu hình theo module, dependency tùy chọn, exclusion hoặc bản đóng gói có thể khác. Không tự thêm một thư viện nếu endpoint không cần nó: endpoint vắng mặt còn có thể do bean/cấu hình/bảo mật.

### 8.2. Đọc báo cáo điều kiện tạo bean

Trong lab, có thể bật báo cáo điều kiện khi khởi động:

~~~shell
java -jar app.jar --debug
~~~

`app.jar` ở đây là tên bản đóng gói của ứng dụng đang kiểm tra. Khi dùng trong dự án thật, gọi đúng tệp đã xây và cấu hình của môi trường đó.

Tìm lớp tự cấu hình tương ứng và đọc nguyên nhân cụ thể: thiếu lớp, thiếu bean, endpoint không available hay đã có bean do ứng dụng cung cấp.

Nếu endpoint `conditions` đã sẵn sàng và người gọi có quyền, nó là một nguồn khác để đọc báo cáo. Nếu chính endpoint đó chưa truy cập được, dùng log khởi động; không tạo vòng lặp “phải vào conditions mới biết vì sao conditions không mở”.

### 8.3. Kiểm tra kênh và địa chỉ công bố

Xác nhận cổng, base path, context path, đường dẫn qua proxy và HTTP/JMX đang xét. Endpoint bean trong context chưa đủ làm bằng chứng có URL HTTP.

Trang khám phá `/actuator` hoặc base path đã đổi có thể hỗ trợ tìm liên kết. Tuy nhiên, trang khám phá có thể bị tắt hoặc bị chặn; thiếu liên kết không phải bằng chứng duy nhất về việc bean có tồn tại hay không.

### 8.4. Kiểm tra request và bảo mật

Ghi lại đúng HTTP method, đường dẫn, query/body, header cần thiết, danh tính/role và mã phản hồi. Không ghi mật khẩu, token hoặc cookie thật vào báo cáo chẩn đoán.

| Phản hồi/biểu hiện | Cách đọc ban đầu |
| --- | --- |
| Không kết nối được | Xem tiến trình, cổng, mạng, TLS trước khi xét endpoint bean |
| `401` hoặc chuyển hướng đăng nhập | Kiểm tra cơ chế xác thực và entry point được cấu hình |
| `403` | Kiểm tra quyền và CSRF; không tự coi là bằng chứng đã xác thực thành công |
| `404` | Có thể sai đường dẫn, chưa có ánh xạ, không có đối tượng đích hoặc bị lớp khác che |
| `405` | Xem lại HTTP method mà thao tác hỗ trợ |
| `400` | Xem tham số bắt buộc, binding và giá trị đầu vào |
| `406`/`415` | Kiểm tra hợp đồng media type và body |
| `200` nhưng rỗng/đã che | Kiểm tra nguồn dữ liệu hoặc chính sách hiển thị, không tự xem là lỗi exposure |
| `503` từ health | Đọc trạng thái health; không đồng nhất với lỗi phân quyền |

Đây là các hướng điều tra, không phải ánh xạ một-một tuyệt đối giữa mã HTTP và nguyên nhân.

### 8.5. Xác nhận dữ liệu và tác động runtime

Sau khi vào được endpoint, kiểm tra đúng nguồn: repository có dữ liệu chưa, meter đã được đăng ký chưa, tệp có tồn tại/đọc được chưa, kho session có lập chỉ mục đúng chưa.

Không dùng POST/DELETE làm phép thử vô hại. Một request hợp lệ có thể làm thay đổi log level, xóa cache, xóa session hoặc dừng tiến trình. Chọn dữ liệu và môi trường thí nghiệm phù hợp với thao tác cần chứng minh.

## 9. Thực hành đánh giá ba tình huống

### Tình huống A: httpexchanges trả 404 dù đã include

Trước hết kiểm tra endpoint được bật chưa và có `HttpExchangeRepository` không. Nếu thiếu kho, việc sửa quyền hoặc thêm lại cùng một cấu hình include không giải quyết điều kiện tạo bean.

Sau khi có kho, tiếp tục kiểm tra HTTP mapping và quyền. Nếu nhận `200` với danh sách trống, chuyển sang kiểm tra việc ghi nhận/lưu giữ dữ liệu.

### Tình huống B: metrics gọi được nhưng prometheus không có

Không kết luận toàn bộ Actuator hỏng. Xác minh dependency và registry Prometheus tương ứng, điều kiện tự cấu hình, exposure của chính `prometheus`, rồi quyền của máy scrape.

Một `MeterRegistry` khác vẫn có thể làm `metrics` hoạt động mà không cung cấp đường scrape Prometheus.

### Tình huống C: GET sessions thành công nhưng DELETE bị 403

Xác nhận hai yêu cầu dùng cùng danh tính và đúng phạm vi quyền. Sau đó kiểm tra CSRF của DELETE. Chưa có bằng chứng để sửa dependency Spring Session hoặc tạo lại bảng session chỉ từ mã `403`.

**Bài tập tự kiểm tra:**

- Vì sao `enabled=true` và `include=httpexchanges` vẫn chưa đủ khi thiếu bean repository?
- Tại sao `caches` với danh sách manager rỗng khác với endpoint không được tạo?
- Một endpoint bean còn tồn tại qua JMX nhưng không có URL HTTP: cần kiểm tra cấu hình nào?
- Người dùng GET được `env` nhưng chỉ thấy giá trị đã che: phải phân biệt những lớp quyền/chính sách nào?
- Vì sao không nên dùng một kết quả `404` để quyết định ngay rằng dependency đang thiếu?

Kết quả đánh giá nên chỉ ra **điều kiện nào đã có bằng chứng, điều kiện nào chưa thỏa và thao tác cụ thể đang kiểm tra**, thay vì chỉ ghi “endpoint không chạy”.
