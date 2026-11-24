# Giảm phụ thuộc và tự cấu hình không cần thiết

## 1. Vì sao tối ưu khởi động đặc biệt quan trọng với Spring Cloud Task?

**Spring Cloud Task** dành cho những ứng dụng Spring Boot có **thời gian chạy hữu hạn**: khởi động, nhận tham số, thực hiện tác vụ, cập nhật trạng thái/kết quả qua **TaskRepository** rồi kết thúc. Ứng dụng có thể được kích hoạt bằng dòng lệnh, lịch Kubernetes CronJob, API hoặc Spring Cloud Data Flow.

Với một dịch vụ web chạy nhiều ngày, chi phí khởi động thường chỉ xuất hiện khi triển khai hoặc thay Pod. Với một task chạy vài phút hoặc vài giây, chi phí này có thể lặp lại **mỗi lần lên lịch**. Nếu ứng dụng chỉ cần đọc một bảng, xuất báo cáo rồi thoát nhưng lại khởi tạo web server, JPA, bộ lập lịch, consumer message và các thread pool không sử dụng, thời gian khởi động, bộ nhớ và khả năng gặp lỗi cấu hình đều có thể tăng.

Ví dụ minh họa, **không phải số đo mặc định của Spring**:

| Thành phần của một lần chạy | Task tối giản | Task có nhiều thành phần không dùng |
| --- | ---: | ---: |
| Tạo JVM và Spring context | 1,1 giây | 4,0 giây |
| Mở kết nối và ghi metadata | 0,3 giây | 0,4 giây |
| Xử lý nghiệp vụ thực tế | 2,0 giây | 2,0 giây |
| Đóng tài nguyên/kết thúc | 0,2 giây | 0,6 giây |
| **Tổng minh họa** | **3,6 giây** | **7,0 giây** |

Ở đây, công việc nghiệp vụ không đổi nhưng tổng thời gian tăng đáng kể. Đó là lý do chương **Tối ưu và nâng cấp** cần nghiên cứu cách **giảm dependency và auto-configuration không cần thiết**.

**Nguyên tắc xuyên suốt:** giảm những thành phần không phục vụ nghiệp vụ, **không loại bỏ cơ chế ghi TaskExecution, báo lỗi, giao dịch hay giám sát** mà hệ thống cần để vận hành an toàn.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **dependency trên classpath** với **Spring Boot auto-configuration**.
2. Xác định starter/thư viện nào thực sự cần cho task CLI, task JDBC, task có Batch và task tích hợp hạ tầng.
3. Dùng Maven/Gradle phân tích dependency graph và dùng `--debug` đọc báo cáo điều kiện auto-configuration.
4. Cấu hình ứng dụng **không có web server** và loại bỏ những component scan, runner hoặc background thread không cần thiết.
5. Biết khi nào **không được** tắt `SimpleTaskAutoConfiguration` hoặc `DataSourceAutoConfiguration`.
6. Đo tác động trước/sau bằng thời gian khởi động, exit status, bộ nhớ, số connection và kiểm tra `TaskRepository`.
7. Nâng cấp BOM, Java, Boot, Cloud Task và schema có kiểm chứng thay vì đổi dependency một cách mù quáng.

## 2. Dependency khác auto-configuration ở đâu?

Một dependency là **artifact xuất hiện trên classpath**. Auto-configuration là cơ chế Spring Boot **tạo những bean phù hợp khi điều kiện thỏa mãn**: có class nhất định, có property, có/không có bean khác hoặc có một tài nguyên hạ tầng.

~~~mermaid
flowchart TD
    A["pom.xml / build.gradle"] --> B["Runtime classpath"]
    B --> C["Spring Boot auto-configuration"]
    C --> D{"Điều kiện class/bean/property phù hợp?"}
    D -->|Có| E["Tạo bean hạ tầng"]
    D -->|Không| F["Không áp dụng cấu hình đó"]
    E --> G["Thời gian tạo context / kết nối / thread"]
    B --> H["Kích thước artifact + độ phức tạp quản lý phiên bản"]
~~~

Hai việc này có tác động khác nhau:

- **Bỏ dependency:** có thể giảm classpath, kích thước image/jar, số thư viện phải vá CVE và đôi khi làm auto-configuration liên quan không còn đủ điều kiện kích hoạt.
- **Tắt một auto-configuration:** ngăn Spring Boot tự tạo nhóm bean từ các class vẫn có trên classpath; **không tự xóa dependency** khỏi jar.
- **Tắt một tính năng bằng property:** chỉ thay đổi tính năng đã được thư viện định nghĩa. Không nên đoán property có tồn tại chỉ dựa vào tên.
- **Chuyển bean sang profile/conditional configuration:** giữ code trên classpath nhưng không tạo bean khi chạy profile task tương ứng.

**Ví dụ:** đặt `spring.main.web-application-type=none` ngăn Spring Boot chạy với `WebApplicationContext`/web server, nhưng **không tự xóa** `spring-boot-starter-web` khỏi dependency graph. Nếu task hoàn toàn không cần servlet/web endpoint, nên **bỏ starter web** khỏi build thay vì chỉ tắt web application type.

## 3. Xây baseline task CLI tối giản

Ví dụ một task xử lý báo cáo hằng ngày: cần Spring Boot, Spring Cloud Task, JDBC driver kết nối metadata PostgreSQL và một service đọc/ghi dữ liệu. Không cần HTTP server, Spring MVC, WebFlux, Kafka, JPA hoặc Spring Batch khi nghiệp vụ chỉ dùng JDBC trực tiếp.

### 3.1. Phụ thuộc Maven có chủ đích

Ví dụ phần `dependencies` của `pom.xml`, với Spring Boot và Spring Cloud BOM đã được khai báo **ở các phần quản lý phiên bản phù hợp**:

~~~xml
<dependencies>
    <!-- Core của ứng dụng Spring Cloud Task hữu hạn -->
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-task</artifactId>
    </dependency>

    <!-- JDBC khi task thực sự truy cập database -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-jdbc</artifactId>
    </dependency>

    <!-- Driver PostgreSQL ở runtime -->
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>postgresql</artifactId>
        <scope>runtime</scope>
    </dependency>

    <!-- Chỉ cần cho môi trường test -->
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Đây là **mảnh POM**, không phải một `pom.xml` độc lập: phải chọn đúng bản Spring Boot/Cloud BOM, Java và plugin build. Nếu starter task đã kéo theo một dependency, Maven có thể hợp nhất bản trùng; `dependency:tree` mới cho biết runtime classpath thực tế.

**Không có các dependency sau chỉ vì “task thì nên thêm”:**

- `spring-boot-starter-web` hoặc `spring-boot-starter-webflux` khi không có nhu cầu làm HTTP server/client tương ứng.
- `spring-boot-starter-data-jpa` khi chỉ chạy SQL với `JdbcTemplate`.
- `spring-boot-starter-batch` khi tác vụ không có Spring Batch `Job`/`Step`.
- `spring-cloud-stream` và broker binder khi không nhận/gửi message qua Spring Cloud Stream.
- `spring-integration-jdbc` chỉ để cho có; chỉ cần cho những tính năng thực sự sử dụng, ví dụ single-instance locking theo yêu cầu phiên bản.
- Client discovery, Config Server, Gateway, tracing exporter, SDK cloud và actuator endpoint chưa có mục đích vận hành rõ ràng.

**Không xóa dependency mà một phần nghiệp vụ đang sử dụng chỉ vì chưa thấy import trực tiếp trong code.** Spring Boot auto-configuration, SPI, JDBC driver và một số provider được tìm qua runtime reflection/service loader; build thành công chưa chứng minh chúng không cần thiết.

### 3.2. Ứng dụng Java

~~~java
import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableTask
public class ReportTaskApplication {

    private static final Logger log =
            LoggerFactory.getLogger(ReportTaskApplication.class);

    public static void main(String[] args) {
        SpringApplication.run(ReportTaskApplication.class, args);
    }

    @Bean
    ApplicationRunner reportRunner(ReportService service) {
        return args -> {
            List<String> values =
                    args.getOptionValues("businessDate");
            if (values == null || values.size() != 1) {
                throw new IllegalArgumentException(
                        "Required --businessDate=yyyy-MM-dd");
            }
            LocalDate day = LocalDate.parse(values.get(0));

            service.generate(day); // Đồng bộ; không trả về sớm.
            log.info("REPORT_COMPLETED businessDate={}", day);
        };
    }
}
~~~

`ReportService` là một Spring bean nghiệp vụ bạn phải triển khai. Đoạn mã không cần `@RestController`, embedded Tomcat hay message consumer. Nếu `service.generate(...)` thất bại, hãy để exception được phản ánh qua cơ chế lỗi phù hợp; **không nuốt exception rồi báo thành công giả**.

### 3.3. Cấu hình tối giản

~~~yaml
spring:
  main:
    web-application-type: none
    lazy-initialization: false
  datasource:
    url: jdbc:postgresql://metadata-db.internal:5432/task_metadata
    username: task_writer
    # Password lấy từ secret môi trường, không lưu trong Git.
  cloud:
    task:
      name: report-task
      initialize-enabled: false
      closecontextEnabled: true
~~~

Ở đây:

- `web-application-type: none` khẳng định đây là tác vụ CLI không phục vụ HTTP.
- `lazy-initialization: false` thể hiện **khởi tạo bean cần thiết một cách rõ ràng/fail fast**; đừng bật lazy chỉ vì muốn con số startup thấp.
- `initialize-enabled: false` phù hợp khi schema TaskRepository **đã được tạo bằng migration**. Với DB trống, cấu hình này có thể khiến ứng dụng lỗi vì không có bảng.
- `closecontextEnabled: true` hỗ trợ đóng context sau khi runner hoàn tất và metadata cuối được cập nhật, hữu ích nếu ứng dụng có executor/thread bean cần cleanup. Đối với test `@SpringBootTest` cần giữ context để kiểm tra, có thể để `false` ở profile test.
- DB URL/tên user chỉ minh họa, không phải credential dùng thật. Dùng secret manager và cấp quyền SQL tối thiểu.

**Không tắt JDBC/DataSource khi mục tiêu vẫn là lưu lịch sử TaskExecution ở database.** Một task chạy được nghiệp vụ nhưng không ghi được repository bền vững có thể làm mất truy vết/retry an toàn.

## 4. Kiểm tra dependency graph trước khi xóa

### 4.1. Maven

Để biết dependency nào kéo theo thư viện khác:

~~~bash
mvn dependency:tree
mvn dependency:tree -Dverbose
mvn help:effective-pom
~~~

Ví dụ muốn biết vì sao Web MVC xuất hiện trong một CLI task:

~~~bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-web
~~~

`-Dverbose` có thể cung cấp thêm thông tin phụ thuộc bị xung đột hoặc bị bỏ qua theo công cụ/phiên bản plugin. Cần xem **toàn cây runtime**, không chỉ khai báo direct dependency. Nếu một starter tích hợp vô tình kéo Spring MVC, đọc vì sao nó cần starter đó trước khi thêm Maven `exclusions`.

### 4.2. Gradle

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-web --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-starter-data-jpa --configuration runtimeClasspath
~~~

Trên Windows, dùng `gradlew.bat` hoặc wrapper tương ứng. Không chạy Gradle/Maven chỉ để xác nhận một file Markdown; những lệnh trên là **bài thực hành cho người học**.

### 4.3. Quy trình quyết định xóa dependency

~~~mermaid
flowchart TD
    A["Thấy thư viện không mong muốn"] --> B["Tìm đường phụ thuộc transitively"]
    B --> C{"Nghiệp vụ / runtime SPI có cần?"}
    C -->|Có| D["Giữ, kiểm tra phiên bản và cấu hình"]
    C -->|Không| E["Xóa direct dependency hoặc loại nhánh kéo theo"]
    E --> F["Build + chạy Task với DB/schema thật"]
    F --> G{"Metadata, exit code, dữ liệu đúng?"}
    G -->|Có| H["Đo startup/memory và ghi kết quả"]
    G -->|Không| I["Khôi phục, điều tra trước khi đổi tiếp"]
~~~

**Thứ tự ưu tiên:** xóa một starter trực tiếp không cần thiết, sau đó mới cân nhắc `exclusions` transitive. Loại trừ một artifact được starter hỗ trợ chính thức mà không hiểu lý do có thể phá auto-configuration hoặc lỗi runtime trên production.

Ví dụ trước/sau ở mức ý tưởng:

~~~text
Trước:
  spring-cloud-starter-task
  spring-boot-starter-jdbc
  spring-boot-starter-web       <- task không mở HTTP server
  spring-boot-starter-data-jpa  <- chỉ dùng JdbcTemplate
  spring-cloud-starter-stream-* <- không dùng message broker

Sau:
  spring-cloud-starter-task
  spring-boot-starter-jdbc
  postgresql (runtime)
  spring-boot-starter-test (test)
~~~

Không được kết luận những thứ bị xóa luôn không cần trong mọi ứng dụng. Nếu task có endpoint nội bộ, ORM, hoặc phát sự kiện qua broker thì chúng có thể là requirement thật.

## 5. Đọc báo cáo auto-configuration thay vì đoán

Spring Boot hỗ trợ **Condition Evaluation Report** để giải thích vì sao một auto-configuration được áp dụng hoặc không áp dụng.

Chạy ứng dụng trong môi trường thử nghiệm:

~~~bash
java -jar target/report-task.jar \
  --debug \
  --businessDate=2026-11-23
~~~

`--debug` bật log phục vụ chẩn đoán, trong đó có báo cáo điều kiện auto-configuration. Một số cấu hình cũng có thể xem qua **Spring Boot Actuator `conditions` endpoint** khi actuator được cài và endpoint được cho phép.

**Không nên** thêm Actuator/web server chỉ để xem báo cáo điều kiện trong một CLI task nếu `--debug` hoặc kiểm tra lúc khởi động đã đủ. Nếu dùng endpoint trong môi trường thật, phải quản lý exposure/security; không mở endpoint chẩn đoán công khai.

### Đọc báo cáo theo câu hỏi

| Dấu hiệu trong báo cáo | Ý nghĩa khả dĩ | Bước tiếp theo |
| --- | --- | --- |
| `DataSourceAutoConfiguration` được chọn | Có JDBC/DataSource phù hợp | **Giữ** nếu TaskRepository/Batch/SQL cần DB |
| Auto-config web server được chọn | Web classpath và web application type cho phép | Task cần HTTP không? Nếu không, bỏ starter web và đặt `none` |
| JPA/Hibernate auto-config được chọn | Có JPA/Hibernate và điều kiện dữ liệu | Task có entity/ORM không? Nếu không, xét bỏ JPA starter |
| Batch auto-config được chọn | Có Spring Batch và điều kiện phù hợp | Task có Job/Step không? Có job tự chạy ngoài ý muốn không? |
| Message/Integration auto-config được chọn | Có thư viện hoặc binding tương ứng | Có dùng broker, channel, scheduled poller không? |
| Auto-config không match | Điều kiện chưa thỏa | Không vội coi đó là lỗi; có thể đúng do tính năng không dùng |

**Một dòng “positive match” không chứng minh nhiều bean đắt đỏ đã được tạo.** Cần kết hợp số bean, log khởi động, kết nối ngoài và đo thực tế. Ngược lại, một bean do `@Configuration`/`@ComponentScan` tự tạo có thể gây chi phí dù không thuộc auto-configuration report.

## 6. Khi nào được tắt auto-configuration?

Spring Boot hỗ trợ loại trừ một auto-configuration cụ thể bằng:

- Thuộc tính `spring.autoconfigure.exclude`.
- `@SpringBootApplication(exclude = ...)` khi class auto-config thực sự có trên classpath.
- `@SpringBootApplication(excludeName = "...")` khi cần loại trừ theo tên.

Đây là **công cụ có chủ đích**, không phải bước tối ưu phải áp dụng cho mọi task. Với Spring Boot 3 và 4, package của một số lớp auto-config có thể thay đổi: **phải tra đúng fully qualified class name theo phiên bản đang build**.

### 6.1. Cẩn thận với DataSourceAutoConfiguration

Ví dụ cú pháp (dòng Boot 3.x; không sao chép class import sang Boot 4 nếu package đã đổi):

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.autoconfigure.jdbc.DataSourceAutoConfiguration;

// CHỈ DÀNH CHO ỨNG DỤNG THẬT SỰ KHÔNG CẦN DATASOURCE.
@SpringBootApplication(exclude = DataSourceAutoConfiguration.class)
public class NoDatabaseApplication {
}
~~~

**Không dùng đoạn này để “tối ưu” một Spring Cloud Task vẫn cần ghi `TaskExecution` vào JDBC TaskRepository.** Ngắt cấu hình DataSource mặc định có thể khiến ứng dụng lỗi hoặc chọn một cơ chế repository khác, trái với yêu cầu theo dõi thực thi trong database.

Nếu task có nhiều DataSource, cách phù hợp có thể là cấu hình `TaskConfigurer`/transaction manager rõ ràng, **không phải** tắt toàn bộ JDBC rồi hy vọng framework tự tìm đúng cơ sở dữ liệu.

### 6.2. Tắt auto-configuration của Spring Cloud Task là thay đổi chức năng

Tài liệu Spring Cloud Task hỗ trợ:

~~~properties
spring.cloud.task.autoconfiguration.enabled=false
~~~

Hoặc loại trừ `SimpleTaskAutoConfiguration` qua annotation theo nhánh phiên bản.

**Nhưng đây không phải một mẹo tăng tốc vô hại.** Nếu vô hiệu hóa auto-configuration của Spring Cloud Task, ứng dụng có thể **không còn tự tạo/ghi TaskExecution theo vòng đời**, khiến TaskRepository, TaskExplorer, Spring Cloud Data Flow hoặc hệ thống vận hành mất lịch sử mà chúng đang kỳ vọng.

| Trường hợp | Có nên tắt Task auto-config? |
| --- | --- |
| Ứng dụng phải ghi start/end/exit code vào `TaskRepository` | **Không** |
| Task được SCDF điều phối và cần hiện lịch sử | **Không**, trừ khi có cơ chế thay thế được chứng minh |
| Bạn đã xây lifecycle/repository riêng, không cần tính năng tự động và có test xác nhận | Có thể cân nhắc |
| Chỉ muốn startup “nhanh hơn 200 ms” nhưng chưa đo tác động | **Không** |

**Điểm phân biệt quan trọng:** property `spring.cloud.task.autoconfiguration.enabled=false` vô hiệu hóa **Task auto-configuration**; `spring.main.web-application-type=none` chỉ thay đổi **kiểu ứng dụng web**. Chúng không tương đương.

### 6.3. Batch auto-run có thể là tác dụng phụ không mong muốn

Khi có `spring-boot-starter-batch`, Spring Boot có thể tự khởi chạy một `Job` duy nhất nếu các điều kiện tương ứng được thỏa mãn. Nếu task đang dùng một `ApplicationRunner` để gọi `JobLauncher` thủ công, việc **để cả hai cơ chế cùng hoạt động** có nguy cơ khởi chạy Batch Job hai lần.

Có thể kiểm soát bằng:

~~~yaml
spring:
  batch:
    job:
      enabled: false
~~~

**Chỉ dùng khi ứng dụng thực sự khởi chạy Job bằng cơ chế riêng.** Nếu mong đợi Boot tự chạy Batch job, đặt `enabled: false` sẽ khiến Job không được tự khởi chạy. Nếu task không dùng Batch thì tốt nhất **không thêm Batch starter**.

### 6.4. Lazy initialization không thay thế tối ưu kiến trúc

Spring Boot hỗ trợ:

~~~yaml
spring:
  main:
    lazy-initialization: true
~~~

Lazy initialization có thể làm **thời gian startup bề ngoài ngắn hơn** vì một số bean được tạo khi cần, nhưng:

- Lỗi cấu hình có thể chỉ xuất hiện lúc nghiệp vụ chạy.
- Chi phí tạo bean vẫn tồn tại và chuyển vào đường thực thi.
- Với CLI task mà hầu hết bean đều được dùng ngay trong runner, tổng thời gian đến khi xử lý xong **có thể không giảm**.
- Một số thành phần lifecycle/listener cần khởi tạo đúng thời điểm, nên phải xác minh bằng integration test.

Hãy tối ưu **thời gian end-to-end của task**, không chỉ một dòng log “Started application”.

## 7. Giảm công việc tự tạo bằng @Configuration và component scan

Không phải mọi chi phí startup đến từ starter. Nhiều ứng dụng tái sử dụng một package gốc lớn chứa cả web controllers, scheduled jobs, stream consumers, SDK clients và bean kiểm tra startup.

### 7.1. Tách module hoặc cấu hình theo profile

Ví dụ tách cấu hình ở cấp bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Profile;

@Configuration(proxyBeanMethods = false)
@Profile("task")
class TaskOnlyConfiguration {

    @Bean
    ReportService reportService(ReportRepository repository) {
        return new ReportService(repository);
    }
}
~~~

Cấu hình này minh họa **hướng thiết kế**, cần có `ReportService` và `ReportRepository` thật trong dự án. Profile `task` cho phép không tạo những bean chỉ cần ở profile `web` hoặc `stream`. Tuy nhiên, **profile không xóa thư viện trên classpath**: nếu muốn giảm kích thước image, hãy tách module build hoặc starter không dùng.

Các lựa chọn:

| Phương án | Có thể giảm | Giới hạn |
| --- | --- | --- |
| Tách module `task-app` khỏi `web-app` | Classpath, component scan, dependency không dùng | Cần quản lý shared code và release |
| `@Profile("task")` / `@ConditionalOnProperty` | Số bean tạo trong một lần chạy | Thư viện vẫn nằm trong artifact |
| Thu hẹp package component scan | Bean/service bị quét ngoài phạm vi | Có thể làm thiếu bean thật nếu thiết kế package kém |
| `@Configuration(proxyBeanMethods=false)` nơi phù hợp | Overhead proxy giữa `@Bean` methods | Không thay đổi dependency graph, không phù hợp nếu code gọi @Bean trực tiếp để dùng singleton semantics |
| Bỏ listener/scheduler/broker client không dùng | Thread, network connections, khởi tạo bean | Có thể mất giám sát nếu xóa nhầm tính năng |

**Không** dùng cấu hình `@ComponentScan(excludeFilters=...)` tràn lan để che một kiến trúc package chưa rõ. Ưu tiên tách các module ứng dụng theo chức năng: CLI task riêng, HTTP service riêng, batch worker riêng.

### 7.2. Không để task có background thread tồn tại sau runner

Nếu một runner gọi `ExecutorService.submit(...)` rồi trả về mà không đợi kết quả, Spring Cloud Task có thể ghi **kết thúc sớm** mặc dù công việc vẫn đang chạy. Nếu pool thread không được đóng, JVM còn có thể tiếp tục sống dù SpringApplication đã hoàn tất.

~~~java
// Ví dụ sai trong task hữu hạn:
@Bean
ApplicationRunner wrongRunner(ExecutorService pool) {
    return args -> {
        pool.submit(() -> doImportantWork());
        // Trả về ngay: TaskExecution có thể kết thúc trước nghiệp vụ.
    };
}
~~~

Thiết kế đúng là đợi kết quả nghiệp vụ và dọn tài nguyên có kiểm soát:

~~~java
// Pseudocode: executor và việc đóng được quản lý rõ ràng.
Future<?> result = pool.submit(() -> doImportantWork());
result.get(); // Chờ kết quả, exception được phản ánh.
~~~

Tùy thiết kế, dùng Spring-managed `ThreadPoolTaskExecutor` hoặc `ExecutorService` có `shutdown/awaitTermination` và deadline. `spring.cloud.task.closecontextEnabled=true` giúp đóng Spring context, **không thay thế** việc quản lý thread tự tạo bên ngoài Spring, và không làm tác vụ nền chưa xong trở thành thành công.

## 8. Tối ưu DataSource nhưng không đánh đổi metadata

Spring Cloud Task thường ghi một bản ghi lúc bắt đầu và cập nhật lúc kết thúc. Nếu dùng Spring Batch hoặc nhiều thao tác nghiệp vụ, còn có nhiều kết nối/giao dịch hơn.

Một pool quá lớn đối với hàng trăm task chạy đồng thời có thể gây quá tải database, nhưng pool quá nhỏ cũng có thể làm deadlock/chờ khi task có nhiều giao dịch đồng thời.

Ví dụ **chỉ để thử nghiệm có kiểm soát**:

~~~yaml
spring:
  datasource:
    hikari:
      maximum-pool-size: 4
      minimum-idle: 0
      connection-timeout: 10000
~~~

Các giá trị trên **không phải khuyến nghị mặc định cho mọi task**. Cần đo số kết nối đồng thời theo nhu cầu TaskRepository, JobRepository, business DataSource và worker threads. `minimum-idle=0` có thể giảm số kết nối rảnh nhưng tăng độ trễ tạo kết nối ở lần sử dụng đầu. Nếu task chỉ chạy vài giây, độ trễ mở kết nối cũng cần được đo.

### 8.1. Câu hỏi quan sát DataSource

- Trong một Pod task, peak active connections là bao nhiêu?
- Khi CronJob tạo nhiều Pod, tổng số kết nối có vượt giới hạn PostgreSQL không?
- Mỗi task dùng một database hay metadata DB và business DB riêng?
- Có transaction Manager/Batch repository chạy song song không?
- Thời gian connect/TLS handshake có đáng kể so với nghiệp vụ không?
- Có connection leak hoặc pool bị giữ sau khi task kết thúc không?

**Tối ưu tốt nhất** không nhất thiết là luôn giảm pool size xuống 1; với workload có Batch, transaction và truy vấn đồng thời, cách đó có thể làm tăng thời gian chờ.

### 8.2. Không coi H2 in-memory là cách giảm startup production

H2 nhúng hữu ích cho **unit/integration test** và một số demo. Nhưng nếu task chạy theo lịch trên nhiều Pod và cần TaskRepository bền vững, mỗi Pod dùng H2 in-memory riêng sẽ không cung cấp lịch sử chung cho SCDF/scheduler và mất dữ liệu khi process kết thúc.

Không đánh đổi khả năng giám sát, restart và phân tích lỗi chỉ vì H2 khởi động nhanh hơn trong một ví dụ nhỏ.

## 9. Đo đúng: startup, end-to-end, memory và kết quả

Nếu muốn chứng minh một thay đổi đáng giữ, cần có baseline **trước** và **sau** với cùng workload, máy, database, image layers và số lần chạy.

### 9.1. Chỉ số nên đo

| Chỉ số | Cách đọc | Vì sao cần? |
| --- | --- | --- |
| **Wall-clock từ launch đến exit** | CI, scheduler hoặc lệnh đo thời gian | Bao gồm khởi động, nghiệp vụ và shutdown |
| **Spring context startup** | Log Boot, `ApplicationReadyEvent.getTimeTaken()` ở phiên bản hỗ trợ | Phân biệt bootstrap với thời gian nghiệp vụ |
| **TaskExecution start/end duration** | `TASK_EXECUTION.START_TIME`/`END_TIME` | Trạng thái framework, không luôn bao gồm toàn bộ thời gian JVM |
| **Peak memory/RSS** | Kubernetes metrics hoặc process monitor | Xác minh giảm footprint thật |
| **Container image/jar size** | Manifest build/registry/tool đo file | Quan sát hiệu quả loại dependency |
| **Số JDBC connections** | Pool metrics/DB monitoring | Kiểm soát tải DB khi nhiều task |
| **Exit code và lỗi** | OS/Pod + `TaskRepository` | Đảm bảo không thay đổi hành vi thất bại |
| **Kết quả nghiệp vụ** | SQL, checksum, object storage | Phát hiện “nhanh nhưng làm thiếu việc” |

### 9.2. Ví dụ đo khởi động bằng Java

Có thể ghi thời gian khởi động Spring Boot khi ứng dụng phát `ApplicationReadyEvent`:

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.event.ApplicationReadyEvent;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StartupTimingListener {

    private static final Logger log =
            LoggerFactory.getLogger(StartupTimingListener.class);

    @EventListener
    public void onReady(ApplicationReadyEvent event) {
        if (event.getTimeTaken() != null) {
            log.info("SPRING_READY durationMs={}",
                    event.getTimeTaken().toMillis());
        }
    }
}
~~~

`ApplicationReadyEvent` được phát **sau khi các runner hoàn tất**, nên `getTimeTaken()` không phải “thời gian tạo bean thuần túy”. Nó bao gồm phần khởi động ứng dụng đến thời điểm sẵn sàng theo Spring Boot, có thể chứa thời gian thực hiện runner. Nếu cần phân tách chi tiết hơn, dùng **ApplicationStartup/FlightRecorderApplicationStartup** và công cụ profiling tương ứng, hoặc đặt các mốc đo riêng có kiểm soát.

### 9.3. Ví dụ đo theo tiến trình

Linux/macOS:

~~~bash
/usr/bin/time -p java -jar target/report-task.jar \
  --businessDate=2026-11-23
~~~

Windows PowerShell:

~~~powershell
Measure-Command {
    java -jar target/report-task.jar --businessDate=2026-11-23
}
~~~

Lệnh PowerShell trên đo thời gian, nhưng muốn kiểm tra **exit code** thì phải đọc `$LASTEXITCODE` ngay sau lệnh Java trong một workflow phù hợp; đừng dùng số đo thời gian như bằng chứng task thành công.

Để so sánh công bằng:

1. Chạy warm-up và nhiều lần lặp.
2. Dùng workload nghiệp vụ **cùng khối lượng** và DB có trạng thái tương đương.
3. Phân biệt cold start (image pull, JVM mới, DB connection mới) và warm start.
4. Báo cáo median/p95, không chọn một lần nhanh nhất để kết luận.
5. Kiểm tra exit code, số bản ghi đã xử lý và `TaskRepository` ở **mọi lần đo**.
6. Đo riêng thời gian chờ scheduler/Kubernetes tạo Pod, vì thay đổi dependency Java không giải quyết mọi độ trễ hạ tầng.

## 10. Kiểm chứng TaskRepository sau tối ưu

Nếu sau khi xóa dependency/auto-config mà CLI vẫn in “Done”, chưa đủ để coi tối ưu an toàn. Phải chứng minh framework còn ghi metadata.

### 10.1. Kiểm tra metadata bắt đầu và kết thúc

~~~sql
SELECT
    TASK_EXECUTION_ID,
    TASK_NAME,
    START_TIME,
    END_TIME,
    EXIT_CODE,
    ERROR_MESSAGE
FROM TASK_EXECUTION
WHERE TASK_NAME = 'report-task'
ORDER BY TASK_EXECUTION_ID DESC;
~~~

Kỳ vọng với lần chạy thành công:

- Có `TASK_EXECUTION_ID` mới, không hardcode ID đầu tiên.
- `START_TIME` và `END_TIME` được ghi khi lifecycle hoàn tất.
- `EXIT_CODE` phù hợp đường thành công thông thường (thường là 0).
- Kết quả nghiệp vụ đã được ghi đầy đủ, không chỉ log thành công.

Kỳ vọng với runner thất bại:

- Nếu TaskExecution đã được tạo và framework xử lý được sự kiện lỗi, bản ghi cần phản ánh lỗi/exit code khác 0 theo cơ chế phù hợp.
- Nếu **ApplicationContext bootstrap thất bại quá sớm**, không bảo đảm tồn tại TaskExecution; phải đọc log start/OS status.
- Nếu process bị kill bằng SIGKILL hoặc OOMKilled, có thể không có `END_TIME` cuối.

### 10.2. TaskExplorer trong kiểm thử tích hợp

Một integration test Spring Boot có thể dùng `TaskExplorer` để tìm lịch sử:

~~~java
TaskExecution latest =
        taskExplorer.getLatestTaskExecutionForTaskName("report-task");

assertThat(latest).isNotNull();
assertThat(latest.getStartTime()).isNotNull();
assertThat(latest.getEndTime()).isNotNull();
assertThat(latest.getExitCode()).isEqualTo(0);
~~~

Đây là **đoạn assert minh họa** trong một test đã có `taskExplorer` và thư viện assert; test thực tế cần khởi tạo Spring context và DataSource/schema phù hợp, cô lập dữ liệu test để không chọn nhầm execution từ một lần chạy khác.

### 10.3. Spring Batch khi có Job/Step

Nếu cần `JobRepository`, `StepExecution`, checkpoint, chunk/restart, **không được** loại bỏ Batch chỉ để giảm startup. Đồng thời kiểm tra metadata:

~~~sql
SELECT JOB_EXECUTION_ID, STATUS, EXIT_CODE,
       START_TIME, END_TIME
FROM BATCH_JOB_EXECUTION
ORDER BY JOB_EXECUTION_ID DESC;
~~~

Một Batch Job thất bại có thể cần ánh xạ ra exit code của task/process theo cấu hình `spring.cloud.task.batch.fail-on-job-failure` của phiên bản hỗ trợ. Đây là **tính đúng đắn**, không phải overhead tùy tiện được phép loại bỏ.

## 11. Nâng cấp phiên bản: dependency gọn nhưng phải tương thích

Khi nâng cấp, nhiều ứng dụng chỉ sửa một phiên bản starter rồi phát hiện lỗi `NoSuchMethodError`, bean trùng, không tìm thấy class auto-config hoặc `relation TASK_EXECUTION does not exist`. Nguyên nhân có thể nằm ở **cả bộ phiên bản** chứ không phải một thư viện.

### 11.1. Chốt ma trận trước khi thay đổi

| Thành phần | Cần ghi nhận |
| --- | --- |
| **Java runtime** | Bản Java được Spring Boot/Cloud Task hỗ trợ |
| **Spring Boot BOM** | Version Boot, mô hình auto-config, classpath và JDBC |
| **Spring Cloud release train** | BOM tương thích với Boot |
| **Spring Cloud Task** | Version Task, property và schema TaskRepository |
| **Spring Batch** | Version Batch nếu dùng job/step và schema `BATCH_*` |
| **JDBC driver + Database** | Version driver, server, dialect/transaction |
| **Deployer/SCDF** | Nếu có khởi chạy từ xa, contract artifact/task metadata |
| **Container image + plugins** | JVM base image, AOT/native build, dependency packaging |

**Không tự ghép Boot 3/Boot 4, Batch 5/Batch 6 và Cloud Task release bất kỳ.** Chọn bộ BOM được công bố tương thích và kiểm tra các API/DDL theo release thực tế.

### 11.2. Chia nâng cấp thành các bước có thể quan sát

~~~mermaid
flowchart TD
    A["Inventory BOM, dependencies, schema"] --> B["Baseline đo startup + correctness"]
    B --> C["Loại dependency không dùng, mỗi lần một nhóm"]
    C --> D["Kiểm tra auto-config + integration tests"]
    D --> E{"PASS?"}
    E -->|Không| F["Rollback thay đổi vừa thực hiện"]
    E -->|Có| G["Đo trước/sau"]
    G --> H["Nâng Boot/Cloud/Task theo BOM tương thích"]
    H --> I["Migration schema trên staging + test DB thật"]
    I --> J["Smoke test jar/Job/Kubernetes"]
    J --> K{"Kết quả và exit code đúng?"}
    K -->|Không| F
    K -->|Có| L["Triển khai theo kế hoạch + giám sát"]
~~~

**Không làm cùng lúc** thay library, đổi schema, chuyển từ H2 sang PostgreSQL và đổi cách khởi chạy; khi lỗi sẽ khó biết tác nhân. Cần backup và thử restore trước migration, xác định Job/Task đang chạy có được phép ngừng hoặc restart không.

### 11.3. Auto-configuration thay đổi khi nâng cấp

Một lớp auto-config từng được loại trừ bằng tên trong Boot 3 có thể **đổi package** ở Boot 4 hoặc không còn cần loại trừ. Nếu property `spring.autoconfigure.exclude` chứa tên class không còn là auto-configuration được nhận diện, ứng dụng có thể lỗi khi khởi động.

Cách làm:

1. Xem **Condition Evaluation Report** trên phiên bản mới.
2. Xem dependency tree và các module split/rename.
3. Kiểm tra danh sách exclusion hiện có; bỏ exclusion không còn phù hợp.
4. Kiểm tra các custom bean override và `@ConditionalOnMissingBean` interaction.
5. Chạy integration tests cho TaskRepository, runner và exit code.
6. Chạy smoke test với database/schema và container image thật.

**Không dùng các internal class nested trong auto-configuration như một public API ổn định.** Spring Boot hỗ trợ tên class auto-config để exclude, không đảm bảo cấu trúc nội bộ của chúng giữa các release.

## 12. Các tình huống tối ưu thường gặp

| Tình huống | Điều nên làm | Điều nên tránh |
| --- | --- | --- |
| Task CLI vô tình có Tomcat | Bỏ web starter nếu không cần, đặt `web-application-type=none` | Chỉ tắt port HTTP trong khi vẫn kéo cả web stack |
| Task đọc SQL đơn giản nhưng có JPA | Xem có thực sự cần entity/ORM không; cân nhắc JDBC | Loại Hibernate khi ứng dụng còn dùng JPA repository |
| Task không dùng Spring Batch | Loại Batch starter/job config | Tắt Batch job auto-run nhưng để những bean không cần |
| Task có Batch cần restart | Giữ JobRepository và schema Batch | Xóa Batch để giảm startup, mất checkpoint |
| Task không dùng broker | Loại Stream/binder và listener liên quan | Để connection broker/consumer chạy trong CLI task |
| Task có thread pool giữ JVM sống | Đóng context/executor đúng cách | `System.exit(0)` bỏ qua tình trạng nghiệp vụ |
| Task ghi metadata vào PostgreSQL | Giữ JDBC/driver/TaskRepository bền vững | Tắt DataSource hoặc dùng H2 in-memory production |
| Task cần quan sát kết quả | Giữ log/metrics cần thiết, dùng observation có chủ đích | Bỏ hết telemetry và mất dấu vết khi task lỗi |
| Startup chậm vì DB network | Đo DNS, TLS, pool và DB latency | Đổ lỗi toàn bộ cho auto-configuration |
| Nâng cấp gây lỗi auto-config | Đối chiếu BOM, import/exclusions và Condition Report | Giữ cứng tên class từ phiên bản cũ không kiểm tra |

## 13. Bài thực hành: tối ưu mà không đánh mất tính đúng đắn

### Chuẩn bị

Chọn một task CLI mẫu có `TaskRepository` JDBC bền vững, một `ApplicationRunner` đồng bộ và một bảng kết quả nghiệp vụ. Thực hiện trên **môi trường test/staging**, không chạy benchmark làm phát sinh dữ liệu thật.

### Bước A — Baseline

1. Ghi version Boot, Cloud Task, Java, DB/driver và toàn bộ runtime dependencies.
2. Chạy một lần thành công và một lần lỗi có kiểm soát.
3. Lưu kết quả `TASK_EXECUTION`, exit code, dữ liệu nghiệp vụ và log.
4. Đo wall-clock, memory, số kết nối DB và kích thước jar/image qua nhiều lần.
5. Bật `--debug` trong lab để thu thập Condition Evaluation Report, sau đó tắt log chẩn đoán.

### Bước B — Giảm dependency

1. Dùng `dependency:tree` hoặc Gradle `dependencyInsight` xác định web/JPA/Batch/Stream dependency không dùng.
2. Xóa **một nhóm nhỏ** dependency hoặc tách module.
3. Kiểm tra build và startup; chạy lại các testcase đã có.
4. Đọc SQL `TASK_EXECUTION` để xác nhận ghi cả trạng thái thành công và lỗi.
5. So sánh kết quả nghiệp vụ, thời gian và bộ nhớ.

### Bước C — Cấu hình không-web và bean có điều kiện

1. Đặt `spring.main.web-application-type=none`.
2. Thu hẹp component scan hoặc tách cấu hình bean bằng `@Profile("task")` khi hợp lý.
3. Kiểm tra không còn embedded web server, consumer/scheduler ngoài dự kiến.
4. Giữ `TaskRepository`, driver JDBC, listener và các transaction manager thực sự cần.
5. Nếu dùng `closecontextEnabled=true`, xác nhận runner hoàn thành công việc trước khi context đóng và JVM thoát đúng cách.

### Bước D — Kiểm chứng nâng cấp

1. Trên branch riêng, chọn BOM Boot/Cloud/Task tương thích.
2. Dựng metadata DB staging có schema đúng phiên bản.
3. Kiểm tra auto-config exclusion cũ và driver API, đặc biệt khi đổi thế hệ Boot.
4. Chạy integration test H2 và PostgreSQL/Testcontainers, sau đó smoke test process.
5. Chỉ giữ thay đổi khi **exit code, TaskRepository và kết quả nghiệp vụ** cùng đúng.
6. Có phương án rollback binary/schema, nhất là khi Batch Job cũ còn cần restart.

### Tiêu chí đạt bài

- [ ] Chỉ rõ những starter hiện diện và giải thích vì sao cần từng cái.
- [ ] Có runtime dependency tree/Condition Evaluation Report trước và sau.
- [ ] Không còn web server hoặc message consumer nếu task không dùng.
- [ ] Không tắt Task auto-configuration khi vẫn yêu cầu lưu TaskExecution.
- [ ] JDBC/TaskRepository và schema bền vững vẫn hoạt động sau tối ưu.
- [ ] ApplicationRunner xử lý đồng bộ và phản ánh lỗi đúng.
- [ ] Test có cả đường thành công và thất bại, không chỉ một dòng log thành công.
- [ ] Task không bị treo do thread pool sau khi công việc kết thúc.
- [ ] Có số liệu startup, end-to-end, bộ nhớ và DB connections được đo công bằng.
- [ ] Không dùng lazy initialization để che lỗi startup chưa giải quyết.
- [ ] Có bộ phiên bản BOM/Java/DB và kế hoạch migration được kiểm chứng.
- [ ] Không loại bỏ Spring Batch/observability nếu nghiệp vụ/vận hành còn cần.
- [ ] Không ghi secret vào commandline arguments, log benchmark hoặc TaskRepository.

## 14. Ghi nhớ

Với **Spring Cloud Task**, tối ưu hiệu quả nhất thường bắt đầu từ **đơn giản hóa classpath và bean được tạo**: bỏ starter web/JPA/Batch/Stream khi thật sự không dùng, cấu hình application type `none`, giới hạn component scan và tránh mở những kết nối/thread nền không liên quan. Dùng `dependency:tree`/`dependencyInsight` và **Condition Evaluation Report** để tìm nguyên nhân thay vì đoán.

Tuy nhiên, **TaskRepository, datasource và quy tắc báo lỗi là chức năng cốt lõi khi cần theo dõi thực thi**. Tắt `spring.cloud.task.autoconfiguration.enabled` hoặc `DataSourceAutoConfiguration` có thể loại bỏ đúng cơ chế mà ứng dụng phải giữ. Khi nâng cấp, phải xem **cả hệ BOM, API auto-config, metadata schema và database**, kiểm chứng bằng integration/process tests và đo thời gian **đến khi công việc thật sự kết thúc**, không chỉ thời gian Spring in log “Started”.

### Tài liệu tham khảo

- [Spring Cloud Task — Features: Disabling auto-configuration, Closing context](https://docs.spring.io/spring-cloud-task/reference/features.html)
- [Spring Cloud Task — Getting Started](https://docs.spring.io/spring-cloud-task/reference/getting-started.html)
- [Spring Boot — Auto-configuration: debug report và exclusions](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html)
- [Spring Boot — SpringApplication: WebApplicationType và lazy initialization](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot — Profiling and application startup](https://docs.spring.io/spring-boot/reference/features/spring-application.html#features.spring-application.application-startup-tracking)
- [Spring Cloud — Compatibility, release trains và Boot versions](https://spring.io/projects/spring-cloud/)
- [Spring Batch — Domain, JobRepository và restart](https://docs.spring.io/spring-batch/reference/domain.html)
