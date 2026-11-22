# Phân biệt chỉ số được thu tự động với phép đo cần cấu hình hoặc thư viện bổ sung

## 1. “Có Actuator” chưa trả lời được câu hỏi “đang đo cái gì?”

Khi thêm Actuator, bạn có thể thấy nhiều tên chỉ số mà chưa viết một dòng đo lường nào. Điều đó dễ dẫn tới hai hiểu lầm: mọi thao tác trong ứng dụng đều đã được đo, hoặc chỉ cần mở một endpoint là số liệu còn thiếu sẽ xuất hiện.

Để đọc đúng hệ thống, cần xác định **ai tạo phép đo, phép đo quan sát ranh giới nào và điều kiện nào làm cho tích hợp đó hoạt động**. Có những chỉ số hạ tầng được Spring Boot đăng ký sẵn; có những tích hợp chỉ hoạt động khi xuất hiện thư viện và bean phù hợp; cũng có câu hỏi nghiệp vụ mà ứng dụng phải chủ động định nghĩa phép đo.

Bài này lấy **Spring Boot 3.3.x, Micrometer 1.13.x và Java 17+** làm phạm vi. Ví dụ chạy với JDK 21 và ghim Boot 3.3.0 để giữ môi trường thực hành xác định. Khi dùng dòng phiên bản khác, cần đọc tài liệu của dòng đó thay vì chuyển nguyên tên thuộc tính hay điều kiện tự cấu hình sang phiên bản mới.

Một số thuật ngữ dùng trong bài:

| Thuật ngữ | Ý nghĩa trong luồng đo lường |
| --- | --- |
| Instrumentation | Phần mã hoặc tích hợp thực sự quan sát sự kiện/trạng thái |
| Meter | Đối tượng đo của Micrometer, chẳng hạn Timer, Counter hoặc Gauge |
| MeterRegistry | Nơi đăng ký meter và nối với cách lưu/xuất số liệu |
| Binder | Thành phần gắn một tập phép đo của một tài nguyên vào registry |
| Endpoint | Giao diện để đọc thông tin của ứng dụng qua HTTP/JMX |
| Backend giám sát | Hệ thống thu thập, lưu lịch sử và truy vấn số liệu bên ngoài ứng dụng |

Tự cấu hình thường giúp nối các thành phần đã được hỗ trợ. Nó không tự hiểu “đơn hàng hợp lệ”, “thanh toán thành công” hoặc “một lượt xử lý tệp” có nghĩa gì trong nghiệp vụ của bạn.

## 2. Tách các khâu trước khi tìm chỉ số còn thiếu

```text
Có tài nguyên hoặc sự kiện cần quan sát
    → Có instrumentation phù hợp
    → Có meter được đăng ký vào registry đang dùng
    → Có mẫu đo/trạng thái để đọc
    → Có đường đọc hoặc xuất số liệu
    → Có hệ thống bên ngoài thu thập và lưu lịch sử nếu cần
```

Các khâu liên quan nhưng không thay thế nhau:

- **Thu thập/ghi nhận:** lời gọi HTTP hoàn tất, bộ nhớ JVM thay đổi hoặc mã ứng dụng ghi một Timer.
- **Đăng ký:** meter xuất hiện trong registry với tên, loại và bộ nhãn xác định.
- **Công khai endpoint:** cho phép một giao diện quản trị được truy cập qua HTTP/JMX.
- **Xuất và lưu:** dùng registry/bộ xuất tương ứng và cấu hình hệ thống giám sát nhận số liệu.

Vì thế, endpoint `metrics` không được expose không chứng minh JVM chưa được đo. Ngược lại, endpoint mở được cũng không chứng minh có phép đo cho mọi phương thức service. Một counter bằng 0, một meter chưa tồn tại và một yêu cầu HTTP bị từ chối truy cập là ba tình trạng khác nhau.

Trong Boot 3.3, endpoint có quy tắc enable/exposure riêng; mặc định chỉ `health` được expose qua HTTP. Thay đổi exposure chỉ xử lý đường truy cập đó. Xem [quy tắc endpoint của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

## 3. Hiểu “tự động” là “tự động khi đủ điều kiện”

Khi đánh giá một chỉ số, hãy phân nó vào nhóm phù hợp:

| Nhóm | Cách xuất hiện | Ví dụ câu hỏi cần kiểm tra |
| --- | --- | --- |
| Có tích hợp sẵn, điều kiện thông thường đã có | Boot đăng ký khi khởi tạo môi trường phù hợp | Registry đã có chỉ số bộ nhớ JVM chưa? |
| Có tích hợp sẵn, phụ thuộc công nghệ/bean | Chỉ xuất hiện khi ứng dụng dùng tài nguyên được hỗ trợ | Có DataSource/pool hoặc executor phù hợp không? |
| Có tích hợp sẵn, cần bật điều kiện riêng | Phải bật cấu hình của công nghệ hoặc chọn đúng cách tạo đối tượng | Tomcat MBean registry đã bật chưa? |
| Cần mô-đun/bộ xuất bổ sung | Dependency cung cấp phần tích hợp còn thiếu | Đã có thư viện Hibernate metrics hoặc registry Prometheus chưa? |
| Cần ứng dụng định nghĩa phép đo | Mã nghiệp vụ hoặc instrumentation tùy biến quyết định ranh giới | Một lần “đặt hàng thành công” được xác định ở đâu? |

Các nhóm có thể kết hợp. Hibernate là ví dụ vừa cần mô-đun metrics phù hợp vừa cần bật thống kê. Prometheus cần registry tương ứng, đường scrape được mở và một máy chủ Prometheus thực sự thu thập. Không nên phân loại một công nghệ chỉ bằng một ô “có/không tự động”.

### Những trường hợp thường có tích hợp sẵn

| Phạm vi | Tên/nhóm thường gặp | Điều không được suy ra từ tên đó |
| --- | --- | --- |
| JVM | `jvm.memory.used`, `jvm.threads.*`, `jvm.gc.*` | Không phải mọi chỉ số đều có trên mọi JVM/GC |
| Tiến trình, hệ thống | `process.*`, `system.*`, `disk.*` | Khả năng đọc phụ thuộc hệ điều hành và môi trường chạy |
| HTTP server có tích hợp | `http.server.requests` | Không đồng nghĩa đã đo mọi bước nghiệp vụ bên trong request |
| Executor/scheduler được hỗ trợ | `executor.*` | Không bao phủ mọi đối tượng Executor tự tạo ở bất kỳ đâu |
| Pool kết nối được hỗ trợ | `jdbc.connections.*`, chỉ số riêng của pool khi có | Không phải thời gian thực thi từng câu SQL |

JVM có các binder cho bộ nhớ, GC, lớp và luồng; danh sách meter thực tế phụ thuộc tài nguyên của tiến trình. Xem [các binder JVM của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/reference/jvm.html).

Với executor trong Boot 3.3, đường tích hợp thông thường là các bean `ThreadPoolTaskExecutor`/`ThreadPoolTaskScheduler` có `ThreadPoolExecutor` bên dưới phù hợp. Một biến cục bộ chứa pool tự tạo không phải bằng chứng pool đó đã được bind. Xem [TaskExecutorMetricsAutoConfiguration](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/autoconfigure/metrics/task/TaskExecutorMetricsAutoConfiguration.html).

Với DataSource, việc đọc các thuộc tính pool cần metadata/provider được hỗ trợ. Những số đo về số kết nối đang dùng hoặc nhàn rỗi không tự trở thành phép đo độ trễ truy vấn. Xem [cấu hình provider metadata của DataSource](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/jdbc/metadata/DataSourcePoolMetadataProvidersConfiguration.html).

Đối chiếu tên chỉ số và tích hợp cụ thể theo [Supported Metrics and Meters của Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html#actuator.metrics.supported). Không dùng bảng này như một danh sách cam kết rằng mọi meter đều xuất hiện ngay sau khi ứng dụng khởi động; Timer theo sự kiện thường chỉ có sau khi có đường thực thi tương ứng.

## 4. Các điều kiện dễ bị bỏ sót

### 4.1. Tomcat: có HTTP metrics chưa chắc có toàn bộ Tomcat metrics

Ở Boot 3.3, nhóm `tomcat.*` cần Tomcat MBean registry được bật. Ví dụ cấu hình:

```properties
server.tomcat.mbeanregistry.enabled=true
```

Đây là điều kiện riêng của nhóm Tomcat; không cần dùng nó như một lời giải chung cho việc thiếu `http.server.requests`. HTTP request observation và thống kê bên trong container quan sát các phạm vi khác nhau. Chỉ áp dụng cấu hình này khi ứng dụng thực sự dùng Tomcat.

### 4.2. Hibernate: cần mô-đun metrics và thống kê

Trong dự án Boot 3.3 đang dùng JPA/Hibernate, thêm dependency do BOM quản lý phiên bản:

```groovy
implementation 'org.hibernate.orm:hibernate-micrometer'
```

Đồng thời bật statistics trên EntityManagerFactory được cấu hình tương ứng:

```properties
spring.jpa.properties.hibernate.generate_statistics=true
```

Chỉ có `spring-boot-starter-data-jpa` không đủ để kết luận nhóm `hibernate.*` đã sẵn sàng. Thêm dependency nhưng chưa bật thống kê cũng thiếu điều kiện. Đo pool kết nối, lời gọi repository và thống kê ORM là những góc quan sát khác nhau.

Các điều kiện Tomcat/Hibernate ở trên được nêu trong [tích hợp metrics Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html). Không bật thêm mọi thống kê chỉ để làm dashboard đủ ô; hãy chọn điều cần quan sát và đánh giá chi phí của cấu hình đó.

### 4.3. Cache: còn phụ thuộc loại cache, statistics và thời điểm tạo

Một cache manager tồn tại chưa chứng minh mọi cache đều đã có số liệu. Cần nhà cung cấp/binder phù hợp, khả năng thống kê được bật theo thư viện khi cần, và cache đã được gắn vào registry. Với Boot 3.3, các cache đã cấu hình khi khởi động là đường tự bind thông thường; cache tạo động sau đó cần được xem xét đăng ký riêng.

Boot cung cấp `CacheMetricsRegistrar.bindCacheToRegistry(...)` cho đường đăng ký tường minh. Giá trị trả về cho biết cache có được hỗ trợ và bind thành công hay không; không nên gọi xong rồi bỏ qua kết quả. Xem [API CacheMetricsRegistrar](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/actuate/metrics/cache/CacheMetricsRegistrar.html).

Đọc đúng loại cache thực tế trước khi thêm cấu hình. Tên một thuộc tính bật statistics của nhà cung cấp này không phải hợp đồng chung cho mọi thư viện cache.

### 4.4. HTTP client: tạo đối tượng theo đường đã được cấu hình

Để nhận tích hợp của Boot, dùng builder được inject như `RestTemplateBuilder`, `RestClient.Builder` hoặc `WebClient.Builder` theo loại client. Đối tượng được tạo trực tiếp bằng constructor/static factory rồi không áp dụng phần tùy biến quan sát có thể bỏ qua tích hợp đó.

Ví dụ đoạn cấu hình bổ sung trong một ứng dụng đã có Spring Web:

```java
@Bean
RestClient downstreamClient(RestClient.Builder builder) {
    return builder.build();
}
```

Đây là fragment cấu hình, cần import `org.springframework.context.annotation.Bean` và `org.springframework.web.client.RestClient`; nó không phải một chương trình độc lập. “Có thư viện HTTP trên classpath” và “đối tượng đang gửi request đã được instrument” là hai việc phải kiểm tra riêng.

## 5. Ví dụ chạy được: ba nguồn gốc khác nhau của meter

Dự án sau dùng JDK 21 và Gradle 8.5. Lần đầu phân giải dependency cần Maven Central; Gradle phải được cài hoặc có wrapper tương thích trong dự án. Ví dụ dùng plugin `application`, nên tác vụ chạy là `run`.

```text
metrics-boundary-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/demo/
    │   ├── MetricsBoundaryApplication.java
    │   └── DemoController.java
    └── resources/application.properties
```

**`settings.gradle`**

```groovy
rootProject.name = 'metrics-boundary-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.3.0')
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

application {
    mainClass = 'demo.MetricsBoundaryApplication'
}
```

**`src/main/resources/application.properties`**

```properties
management.endpoints.web.exposure.include=health,metrics
spring.main.banner-mode=off
spring.main.log-startup-info=false
logging.level.root=OFF
```

**`src/main/java/demo/MetricsBoundaryApplication.java`**

```java
package demo;

import io.micrometer.core.annotation.Timed;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class MetricsBoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(MetricsBoundaryApplication.class, args);
    }

    @Bean
    PricingService pricingService() {
        return new PricingService();
    }

    @Bean
    ApplicationRunner experiment(PricingService pricing, MeterRegistry registry) {
        return args -> {
            pricing.calculate(2);
            boolean annotationMeterPresent =
                    registry.find("demo.price.calculate").timer() != null;

            Timer duration = Timer.builder("demo.price.duration")
                    .description("Duration of explicit price calculations")
                    .tag("operation", "calculate")
                    .register(registry);

            duration.record(() -> { pricing.calculate(2); });
            duration.record(() -> { pricing.calculate(3); });

            boolean jvmMeterPresent =
                    !registry.find("jvm.memory.used").gauges().isEmpty();

            System.out.println("JVM_MEMORY_PRESENT=" + jvmMeterPresent);
            System.out.println("ANNOTATION_ONLY_PRESENT=" + annotationMeterPresent);
            System.out.println("MANUAL_DURATION_COUNT=" + duration.count());
        };
    }

    public static class PricingService {
        @Timed("demo.price.calculate")
        public int calculate(int quantity) {
            return Math.multiplyExact(quantity, 100);
        }
    }
}
```

**`src/main/java/demo/DemoController.java`**

```java
package demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DemoController {
    @GetMapping("/demo/ping")
    public String ping() {
        return "ok";
    }
}
```

Chạy lần đầu không mở web server để kiểm tra riêng registry và phép đo:

```shell
gradle --console=plain run --args="--spring.main.web-application-type=none"
```

Ba dòng do ứng dụng in ra là:

```text
JVM_MEMORY_PRESENT=true
ANNOTATION_ONLY_PRESENT=false
MANUAL_DURATION_COUNT=2
```

Gradle có thể in thêm thông tin tác vụ; ba dòng trên là stdout của phần thực nghiệm. Không có thời lượng cố định trong output vì tốc độ chạy phụ thuộc máy và JVM.

Giải thích từng dòng:

1. **JVM_MEMORY_PRESENT=true:** ứng dụng không tự gọi binder bộ nhớ, nhưng Boot đã đăng ký meter JVM qua cấu hình tự động phù hợp.
2. **ANNOTATION_ONLY_PRESENT=false:** `PricingService` là bean và đã được gọi, nhưng dependency/cấu hình ban đầu chưa có cơ chế AOP xử lý `@Timed` trên service tùy ý. Annotation đơn lẻ không tự thực thi phép đo.
3. **MANUAL_DURATION_COUNT=2:** hai khối lệnh được bọc bằng `Timer.record(...)` được ghi tường minh. Tổng số lần gọi `calculate` là ba, nhưng Timer này chỉ bao quanh hai lần.

Do đó, “một phương thức đã chạy ba lần” không tự kéo theo “mọi timer liên quan phải có count bằng ba”. Phải nhìn vị trí ghi phép đo.

`registry.find(...)` chỉ tra cứu meter đã đăng ký. Nếu dùng `registry.timer("tên-cần-tìm")` để kiểm tra có meter chưa, bạn có thể tự tạo một Timer mới, khiến kết quả kiểm tra không còn chứng minh tích hợp đã tạo nó.

Ví dụ không thêm database, Prometheus hoặc một máy chủ giám sát bên ngoài. Những thành phần đó không phải điều kiện để quan sát sự khác biệt cơ bản giữa binder tự động, annotation chưa được xử lý và phép đo tường minh.

## 6. Mở HTTP để quan sát phép đo tự động của web

Chạy lại ứng dụng ở chế độ web mặc định:

```shell
gradle --console=plain run
```

Ứng dụng giữ web server hoạt động. Mở terminal khác và tạo sự kiện:

```shell
curl http://localhost:8080/demo/ping
curl http://localhost:8080/actuator/metrics
```

Lệnh gọi `/demo/ping` trả nội dung `ok`. Trên Windows PowerShell, dùng `curl.exe` nếu `curl` đang là alias. Đọc nhóm request của riêng route vừa gọi:

```shell
curl --get http://localhost:8080/actuator/metrics/http.server.requests --data-urlencode "tag=uri:/demo/ping"
curl http://localhost:8080/actuator/metrics/demo.price.duration
```

Trong tiến trình mới và chỉ một lần gọi `/demo/ping`, tìm thống kê `COUNT` của request có nhãn URI tương ứng. Timer thủ công `demo.price.duration` vẫn có hai lần ghi từ runner, vì controller ping không ghi thêm vào Timer này.

Bản thân các lần gọi Actuator cũng có thể tạo HTTP metrics. Vì vậy, không lấy tổng `http.server.requests` chưa lọc rồi quy toàn bộ cho một endpoint nghiệp vụ. Dùng `availableTags` để xem các giá trị nhãn thực tế khi cần chẩn đoán.

Endpoint nhận tên Micrometer gốc như `http.server.requests`; tên hiển thị sau chuyển đổi ở backend giám sát có thể khác. Endpoint `metrics` phục vụ chẩn đoán meter đã ghi nhận, không phải kho lịch sử để scrape thay cho backend. Xem [REST API metrics của Boot 3.3](https://docs.spring.io/spring-boot/3.3/api/rest/actuator/metrics.html).

Nếu chạy trong môi trường đã đổi management port, base path hoặc có Spring Security, phải dùng đúng địa chỉ và quyền truy cập. Một phản hồi 401/403 không đủ để kết luận instrumentation bị thiếu. Ví dụ thực hành không thêm cấu hình bảo mật của một hệ thống triển khai thật.

## 7. Bổ sung cơ chế xử lý @Timed và so sánh trước–sau

Để `@Timed` trên service trong ví dụ được Spring AOP xử lý, bổ sung dependency sau vào cùng khối `dependencies`:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-aop'
```

Tạo thêm **`src/main/java/demo/TimingConfiguration.java`**:

```java
package demo;

import io.micrometer.core.aop.TimedAspect;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class TimingConfiguration {
    @Bean
    TimedAspect timedAspect(MeterRegistry registry) {
        return new TimedAspect(registry);
    }
}
```

Sau đó chạy lại ở chế độ không có web server bằng lệnh ở mục 5. Ba dòng ban đầu đổi thành:

```text
JVM_MEMORY_PRESENT=true
ANNOTATION_ONLY_PRESENT=true
MANUAL_DURATION_COUNT=2
```

Giờ meter `demo.price.calculate` tồn tại sau lời gọi đầu tiên. Khi cả runner chạy xong, annotation đã quan sát **ba** lần gọi `calculate`: một lần gọi trực tiếp trước đó và hai lần nằm trong các khối `Timer.record`. Timer thủ công vẫn chỉ đếm **hai** lần.

Nếu muốn kiểm tra thêm ngay cuối runner, có thể bổ sung dòng chẩn đoán sau:

```java
System.out.println("ANNOTATED_TIMER_COUNT=" + registry.get("demo.price.calculate").timer().count());
```

Trong biến thể có aspect này, dòng bổ sung in `ANNOTATED_TIMER_COUNT=3`. Đây là hai meter khác tên đo các phạm vi được lựa chọn; không cộng hai số đếm để tuyên bố đã có năm lần xử lý giá.

Micrometer cung cấp `TimedAspect` để xử lý annotation qua AOP. Với Spring AOP, lời gọi phải đi qua proxy phù hợp; tự tạo đối tượng bằng `new`, tự gọi nội bộ qua `this`, hoặc cấu trúc phương thức/lớp không thể được proxy như dự định đều cần được kiểm tra. Các tích hợp chuyên biệt có thể hỗ trợ annotation theo cơ chế riêng, nên không suy luận từ annotation trên repository sang mọi service. Xem [cơ chế TimedAspect của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/timers.html#_the_timed_annotation).

Trong mã thật, chọn ranh giới đo theo câu hỏi cần trả lời. Nếu hai cơ chế cùng đo một thao tác với cùng mục đích, cần tránh ghi chồng hoặc đặt tên/diễn giải khiến người đọc cộng trùng sự kiện.

## 8. Prometheus là phần bổ sung cho đường xuất số liệu

Bài thực hành ban đầu không cần Prometheus để có meter. Khi muốn Prometheus scrape ứng dụng, thêm registry tương ứng vào dự án:

```groovy
implementation 'io.micrometer:micrometer-registry-prometheus'
```

Mở endpoint scrape bên cạnh các endpoint đang dùng:

```properties
management.endpoints.web.exposure.include=health,metrics,prometheus
```

Chạy ứng dụng ở chế độ web và kiểm tra:

```shell
curl http://localhost:8080/actuator/prometheus
```

Cần phân biệt ba việc: dependency cung cấp registry/bộ xuất, endpoint cung cấp dữ liệu cho việc scrape, và máy chủ Prometheus có cấu hình target để thực sự thu thập. Chỉ ghi chữ `prometheus` trong exposure không tự cài registry. Endpoint trả được dữ liệu cũng không tự dựng một máy chủ lưu lịch sử.

Tên meter có thể được chuyển sang quy ước của Prometheus và Timer có thể sinh nhiều chuỗi thống kê. Khi tìm metric ở backend, đối chiếu tên thực tế được xuất thay vì dùng tên sau chuyển đổi để gọi `/actuator/metrics/{name}`. Xem [tích hợp Prometheus của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

Tương tự, có một registry tự cấu hình không có nghĩa mọi backend đều đã có tài khoản, địa chỉ và quyền nhận dữ liệu. Cấu hình kết nối/export của backend nào phải được kiểm tra theo backend đó.

## 9. Có Timer chưa đồng nghĩa đã có mọi thống kê mong muốn

Một Timer cơ bản cung cấp số sự kiện và tổng thời gian; các thống kê phân bố phụ thuộc cấu hình và khả năng registry/backend. Nếu dashboard muốn histogram hoặc các ngưỡng độ trễ, đó là một yêu cầu cấu hình thêm, không phải lý do để đo lại cùng request bằng một Timer thứ hai.

Ví dụ cấu hình bổ sung cho các timer HTTP được hỗ trợ:

```properties
management.metrics.distribution.percentiles-histogram.http.server.requests=true
management.metrics.distribution.slo.http.server.requests=100ms,300ms,1s
```

Các dòng này cấu hình thống kê của phép đo đã có; chúng không tự tạo request, không thêm registry Prometheus và không thay thế cấu hình scrape. Không phải phản hồi JSON của endpoint `metrics` sẽ tự biến thành toàn bộ histogram; kiểm tra dữ liệu phân bố ở bộ xuất/backend hỗ trợ nó.

Bộ lọc meter còn có thể từ chối đăng ký, đổi tên/nhãn hoặc chỉnh thống kê. Do đó, một meter thiếu dù mã instrumentation đã chạy có thể liên quan đến filter. Xem [MeterFilter của Micrometer 1.13](https://docs.micrometer.io/micrometer/reference/1.13/concepts/meter-filters.html).

Mỗi bộ giá trị nhãn có thể mở rộng số chuỗi số liệu. Chọn nhãn có tập giá trị giới hạn và ý nghĩa ổn định, chẳng hạn loại thao tác; không đưa ID đơn hàng, địa chỉ email hoặc thông báo lỗi tự do vào nhãn chỉ để tìm một lần xử lý. Histogram nhân thêm số chuỗi, nên cần cân nhắc đồng thời phạm vi áp dụng và số giá trị nhãn.

## 10. Metrics, observation và tracing có quan hệ nhưng không thay thế nhau

Instrumentation có thể dùng Micrometer Observation để tạo dữ liệu cho metrics và, khi có hạ tầng tracing phù hợp, cho traces. Điều đó không có nghĩa một Timer tự tạo bất kỳ sẽ tự sinh trace, hoặc chỉ thêm Actuator là trace đã được gửi tới một nơi lưu trữ.

Cần kiểm tra riêng: có observation nào được tạo, handler nào xử lý nó, có tích hợp tracing hay không và exporter có kết nối backend không. Các giá trị ít biến thể phù hợp cho metric tags; thông tin có nhiều giá trị như danh tính từng yêu cầu cần được xử lý theo đúng cơ chế và chính sách dữ liệu tương ứng. Xem [Observability trong Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

Phạm vi thời gian cũng cần được xác định. Ví dụ trong bài là tính toán đồng bộ; `Timer.record` bao quanh khối lệnh thực hiện ngay. Nếu khối lệnh chỉ gửi một công việc bất đồng bộ rồi trả về, phép đo khối lệnh đó không tự trở thành thời gian hoàn tất công việc. Với chuỗi phản ứng, phải kiểm tra việc đăng ký thực thi và tín hiệu kết thúc thay vì chỉ thời điểm tạo publisher.

Tương tự, chỉ số pool JDBC không tự chứa thời gian từng SQL. Khi cần quan sát JDBC/R2DBC ở một mức khác, phải chọn tích hợp tương ứng, kiểm tra dependency và ranh giới nó hỗ trợ; không suy luận mức bao phủ đó từ việc đã có số kết nối.

## 11. Chẩn đoán theo bằng chứng thay vì thêm dependency hàng loạt

| Biểu hiện | Điều cần kiểm tra trước | Cách kiểm chứng phù hợp |
| --- | --- | --- |
| Không có meter trong registry | Điều kiện auto-configuration, bean/thư viện, filter, mã tạo phép đo | Tra cứu registry và tạo đúng một sự kiện có kiểm soát |
| Có meter nhưng chưa có sự kiện | Đường mã thực sự đã chạy chưa, đã kết thúc chưa | Ghi số trước/sau cùng một thao tác |
| Có meter trong ứng dụng nhưng HTTP không đọc được | Enable/exposure, địa chỉ, management port, xác thực | Kiểm tra cấu hình endpoint và phản hồi HTTP |
| HTTP client không có số liệu | Client đang dùng đã nhận customization quan sát chưa | Kiểm tra nơi tạo client và dùng builder được inject |
| Cache/pool cụ thể không có số liệu | Loại tài nguyên, binder/provider, thống kê, thời điểm tạo | Xác nhận tài nguyên cụ thể và khả năng bind |
| Meter có ở Actuator nhưng backend trống | Registry/exporter, kết nối, scrape target, tên/nhãn truy vấn | Đối chiếu dữ liệu xuất và cấu hình backend |
| Count lớn hơn dự kiến | Nhiều đường gọi, runner/tác vụ nền, nhiều nhãn hoặc đo chồng | Lọc đúng bộ nhãn, so sánh chênh lệch trước/sau |

Có thể bật báo cáo điều kiện tự cấu hình khi chẩn đoán, chẳng hạn chạy với `--debug`. Báo cáo giúp giải thích điều kiện nào không khớp; nó không thay thế việc xác nhận có mẫu đo sau một lời gọi thực tế. Trong ví dụ đã tắt log để stdout dễ đọc, hãy bỏ dòng `logging.level.root=OFF` khi cần xem log chẩn đoán.

Tránh hai cách sửa gây nhiễu: mở toàn bộ endpoint để tìm một Timer chưa từng được tạo, hoặc tự tạo meter cùng tên chỉ để làm nó xuất hiện trong danh sách. Cả hai đều không chứng minh đường tích hợp ban đầu đã hoạt động.

## 12. Bài tập kiểm chứng khả năng phân biệt

Làm từng tình huống trên một lần khởi động mới để không trộn cấu hình hoặc số đếm của các lần chạy:

1. **Giữ cấu hình ban đầu:** giải thích vì sao JVM meter có mặt, annotation meter vắng mặt và Timer thủ công có count 2 dù phương thức chạy ba lần.
2. **Bỏ metrics khỏi exposure:** kiểm tra ba dòng registry trong chế độ không có web vẫn giống ban đầu; khi chạy web, phân biệt đường truy cập endpoint với việc meter đã được đăng ký.
3. **Thêm starter AOP cùng TimedAspect:** xác nhận annotation meter được tạo và đếm ba lần, còn Timer thủ công vẫn đếm hai lần.
4. **Chỉ thêm prometheus vào exposure, chưa thêm registry:** giải thích vì sao một tên endpoint trong cấu hình không cung cấp thư viện/bộ xuất còn thiếu. Sau khi bổ sung registry, kiểm tra riêng endpoint scrape và target ở máy chủ Prometheus.
5. **Giả sử muốn biết số lần thanh toán thành công:** xác định nơi nghiệp vụ thực sự hoàn tất rồi đề xuất phép đo/nhãn hữu hạn. Không dùng tổng HTTP 2xx hoặc số kết nối pool để thay thế định nghĩa nghiệp vụ đó.

Khi đánh giá một metric, ghi rõ phiên bản, nguồn tạo phép đo, điều kiện hoạt động, ranh giới được quan sát và đường đọc/xuất. Những thông tin đó giúp giải thích vì sao một chỉ số xuất hiện tự động trong môi trường này nhưng cần cấu hình hoặc thư viện bổ sung trong môi trường khác.
