# Lựa chọn ứng dụng không có máy chủ web khi triển khai Spring Cloud Task

## 1. Bài toán: tác vụ chạy xong phải kết thúc, không phải chờ HTTP request

**Spring Cloud Task** được dùng để xây dựng các ứng dụng Spring Boot có thời gian chạy **hữu hạn**: nhập dữ liệu, chốt số liệu, đồng bộ danh mục, chạy đối soát, xuất báo cáo hoặc khởi chạy một **Spring Batch Job**. Khi cấu hình đúng, mỗi lần chạy có thể tạo một `TaskExecution` trong `TaskRepository` để theo dõi tên tác vụ, thời gian bắt đầu/kết thúc, mã thoát và tham số.

Ví dụ ứng dụng `daily-close-task` được CronJob gọi lúc 02:00 để chốt doanh thu ngày trước đó. Vòng đời mong muốn:

1. JVM khởi động, đọc cấu hình và kết nối các thành phần cần thiết.
2. Spring Cloud Task ghi nhận lần thực thi vào repository.
3. `ApplicationRunner` hoặc `CommandLineRunner` gọi nghiệp vụ chốt ngày.
4. Nghiệp vụ hoàn tất hoặc phát sinh lỗi; framework có cơ hội ghi metadata cuối.
5. Spring context đóng, tiến trình trả mã thoát cho CronJob/Job controller.

Không bước nào bắt buộc ứng dụng phải nhận request HTTP. Nếu vô tình mang `spring-boot-starter-web` vào classpath và để Spring Boot tự chọn kiểu web, embedded Tomcat hoặc một web server khác có thể được khởi chạy, tiếp tục giữ tiến trình sống dù runner đã hoàn thành. Khi đó bộ điều phối có thể nhìn thấy Pod **Running** quá lâu thay vì một Job có trạng thái hoàn tất.

Lựa chọn thường phù hợp cho loại ứng dụng này là **`WebApplicationType.NONE`**, kết hợp cơ chế hoàn tất/thoát tiến trình rõ ràng và quản lý công việc nền đúng cách.

> **Nguyên tắc:** Một ứng dụng Spring Cloud Task không cần biến thành web service chỉ để có `main(...)`, Dependency Injection, DataSource, transaction, Actuator library hoặc khả năng gọi HTTP ra hệ thống khác. `NONE` tắt **máy chủ web nhúng**, không tắt toàn bộ Spring Framework hay mọi kết nối mạng.

## 2. Ba kiểu WebApplicationType và lựa chọn phù hợp

Spring Boot phân biệt ba chế độ ứng dụng:

| Chế độ | ApplicationContext / web server | Phù hợp | Rủi ro khi dùng cho task hữu hạn |
|---|---|---|---|
| `NONE` | Context không phải web; **không khởi động embedded web server** | CLI, batch, ETL, đối soát, Spring Cloud Task hữu hạn | Không có HTTP endpoint để gọi trạng thái trực tiếp; phải dùng log/repository/bộ điều phối |
| `SERVLET` | Servlet web context với embedded web server khi cấu hình phù hợp | REST API, dashboard, callback HTTP | Có thể giữ JVM sống sau khi runner xong |
| `REACTIVE` | Reactive web context với embedded reactive web server | HTTP reactive gateway/service | Vẫn là tiến trình server thường trực, khác lifecycle Job |

Spring Boot có thể **suy ra kiểu ứng dụng từ classpath**. Khi thư viện Spring MVC có mặt, Boot thường tạo servlet web context nếu không được chỉ dẫn khác; khi chỉ có WebFlux, Boot có thể chọn reactive. Do đó **không nên phụ thuộc vào classpath một cách tình cờ** để quyết định một task có chạy web server hay không.

Các trường hợp thực tế:

- **Một task xuất file theo ngày:** dùng `NONE`.
- **Một ứng dụng luôn lắng nghe `POST /run-report`:** đó là web API; nên có service nhận request **riêng** rồi khởi chạy Job/task hữu hạn, thay vì dùng một tiến trình để làm cả hai mà không có kế hoạch lifecycle.
- **Một task gọi REST API của hệ thống khác:** vẫn có thể dùng `NONE`; HTTP client chủ động gửi request không đòi hỏi mở cổng inbound.
- **Một ứng dụng vừa có `@RestController` vừa cần chạy batch theo lịch:** cân nhắc tách thành **control plane web service** và **worker/task application** để mỗi thành phần có chức năng và chu kỳ sống rõ ràng.

Đặc biệt, cấu hình `server.port=-1` **không giống** `spring.main.web-application-type=none`. Spring Boot mô tả `server.port=-1` là tắt endpoint HTTP nhưng **vẫn tạo web application context**; trong khi `NONE` yêu cầu context không phải web và không khởi chạy máy chủ web nhúng. `server.port=0` lại là chọn cổng ngẫu nhiên, **vẫn là web server**.

## 3. Luồng xử lý của ứng dụng không web

~~~mermaid
flowchart TD
    A["CLI / CronJob / Scheduler"] --> B["JVM khởi chạy Spring Boot"]
    B --> C["ApplicationContext không-web"]
    C --> D["TaskRepository ghi lần chạy"]
    D --> E["ApplicationRunner / CommandLineRunner"]
    E --> F["Service thực hiện nghiệp vụ"]
    F --> G{"Kết quả?"}
    G -- "Thành công" --> H["Commit output + chờ mọi việc bắt buộc"]
    G -- "Exception" --> I["Lỗi được lan lên lifecycle"]
    H --> J["Framework xử lý kết thúc TaskExecution"]
    I --> J
    J --> K["Đóng context và tài nguyên"]
    K --> L["JVM trả exit code"]
    L --> M["Job controller / scheduler ghi nhận kết quả"]
~~~

Đây là sơ đồ logic, không bảo đảm từng callback và lần ghi repository diễn ra theo đúng một thứ tự cố định trong mọi phiên bản. Cần hiểu:

- **Spring Cloud Task quan sát vòng đời ứng dụng và runner**, không tự giám sát mọi `Thread` hoặc `CompletableFuture` được tạo riêng.
- **Spring Batch** nếu được sử dụng sẽ có `JobRepository` độc lập để theo dõi Job/Step/checkpoint; `TaskRepository` không thay nó.
- **Dữ liệu nghiệp vụ** phải được commit trong nơi lưu thích hợp, không phải chỉ được ghi vào `TaskExecution`.
- Nếu JVM bị `SIGKILL` hoặc crash trước lúc ghi kết thúc, metadata có thể chưa có `END_TIME`; không nên suy diễn trạng thái nghiệp vụ chỉ từ đó.

Một ứng dụng không có web server vẫn có thể chạy sai: nếu runner nuốt exception, khởi chạy luồng nền rồi trả về, hoặc có bộ scheduler chạy mãi, nó sẽ không còn đúng tính chất **hữu hạn**. Vì vậy chọn `NONE` là **điều kiện kiến trúc**, chưa phải toàn bộ giải pháp vòng đời.

## 4. Cấu hình tối thiểu: web-application-type=none

Trong `application.yml`:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-close-task
  cloud:
    task:
      name: daily-close-task
~~~

Hoặc `application.properties`:

~~~properties
spring.main.web-application-type=none
spring.application.name=daily-close-task
spring.cloud.task.name=daily-close-task
~~~

Lưu ý: `spring.cloud.task.name` nằm trong nhóm `spring.cloud.task`, còn `spring.main.web-application-type` thuộc **Spring Boot**. Hai property có trách nhiệm khác nhau.

Có thể chỉ định ở command line khi chạy:

~~~bash
java -jar daily-close-task.jar \
  --spring.main.web-application-type=none \
  --date=2026-11-23
~~~

Hoặc cấu hình ở mức Java API:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;

public class DailyCloseTaskApplication {
    public static void main(String[] args) {
        SpringApplication application =
            new SpringApplication(DailyCloseTaskApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.run(args);
    }
}
~~~

Ví dụ Java API minh họa cách đặt chế độ, **chưa phải class ứng dụng đầy đủ**: dự án cần `@SpringBootApplication`, logic runner, dependency Spring Cloud Task và cơ chế đóng context/thoát tiến trình. Không nên sao chép riêng đoạn này mà bỏ đi phần khởi tạo task thực tế.

**Thực hành tốt:** đặt `spring.main.web-application-type=none` rõ ràng trong cấu hình deployment và tránh thêm web starter nếu không có nhu cầu. Như vậy kể cả dependency transitively thêm web classes, task vẫn không vô tình biến thành một server.

## 5. Dependencies: tránh kéo embedded server vào ứng dụng task

Một ứng dụng Spring Cloud Task điển hình thường cần:

- Spring Boot core/autoconfiguration.
- Spring Cloud Task starter, đúng BOM và phiên bản tương thích với Spring Boot.
- DataSource/driver nếu dùng `TaskRepository` bền vững qua JDBC.
- Spring Batch khi công việc cần Job/Step/checkpoint.
- Spring JDBC/JPA hoặc HTTP client tùy nghiệp vụ.

Ví dụ ý tưởng dependency (Gradle Groovy DSL; version được quản lý bởi Spring Boot/Spring Cloud BOM tương thích):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.cloud:spring-cloud-starter-task'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    // Chỉ thêm khi thực sự cần Job/Step của Spring Batch:
    // implementation 'org.springframework.boot:spring-boot-starter-batch'
}
~~~

Đây là **đoạn dependencies**, không phải một file build hoàn chỉnh. Dự án vẫn cần plugin, version/BOM, repository và cấu hình build riêng. Với các dòng Spring Cloud/Boot mới hoặc cũ, cần kiểm tra artifact và ma trận tương thích trước khi kết luận chính xác.

Nếu không cần endpoint HTTP, **không có lý do mặc định phải thêm `spring-boot-starter-web`**. Nếu một thư viện client kéo web stack vào, `WebApplicationType.NONE` vẫn là hàng rào cấu hình để không bật embedded server.

Không nên chỉ dùng `spring.main.lazy-initialization=true` hoặc vô hiệu hóa `TomcatServletWebServerFactory` để “khắc phục”; đó là những vấn đề khác. Lựa chọn chính xác và dễ quan sát hơn là **`web-application-type=none`**.

## 6. Viết ứng dụng Spring Cloud Task hữu hạn bằng ApplicationRunner

Ví dụ minh họa dùng Spring Boot, Spring Cloud Task và một service nghiệp vụ. Runner nhận ngày xử lý từ CLI, gọi service và chỉ trả về khi phần việc bắt buộc hoàn tất.

~~~java
package example.task;

import java.time.LocalDate;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.task.configuration.EnableTask;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.stereotype.Service;

@SpringBootApplication
@EnableTask
public class DailyCloseTaskApplication {

    public static void main(String[] args) {
        ConfigurableApplicationContext context =
            SpringApplication.run(DailyCloseTaskApplication.class, args);

        int exitCode = SpringApplication.exit(context);
        System.exit(exitCode);
    }

    @Bean
    ApplicationRunner closeDayRunner(CloseDayService service) {
        return args -> {
            List<String> dates = args.getOptionValues("date");

            if (dates == null || dates.size() != 1
                    || dates.get(0) == null || dates.get(0).isBlank()) {
                throw new IllegalArgumentException(
                    "Required argument: --date=yyyy-MM-dd");
            }

            LocalDate businessDate = LocalDate.parse(dates.get(0));

            // Chỉ trả về khi nghiệp vụ đã hoàn tất hoặc ném lỗi.
            service.closeDay(businessDate);
        };
    }
}

@Service
class CloseDayService {

    private static final Logger log =
        LoggerFactory.getLogger(CloseDayService.class);

    void closeDay(LocalDate businessDate) {
        log.info("Closing business date {}", businessDate);

        // Thay bằng transaction, validation, tính toán và lưu kết quả thật.
        // Nếu phần việc thất bại, ném exception, không nuốt lỗi.

        log.info("Close-day processing completed for {}", businessDate);
    }
}
~~~

**Ý nghĩa vòng đời:**

1. Spring Boot tạo `ApplicationContext`, còn `@EnableTask` bật cấu hình Spring Cloud Task cho version hỗ trợ.
2. `ApplicationRunner` được gọi trong quá trình khởi động và chạy nghiệp vụ hữu hạn.
3. `SpringApplication.exit(context)` đóng context, thu thập exit code từ các `ExitCodeGenerator` thích hợp và chạy callback đóng tài nguyên.
4. `System.exit(exitCode)` đưa mã thoát ra hệ điều hành/container để scheduler biết tiến trình kết thúc.

Ví dụ cố ý để service nghiệp vụ là **khung minh họa**, không giả định báo cáo đã thật sự được chốt chỉ vì một dòng log. Production phải thêm business repository, transaction, kiểm tra idempotency, timeout và test.

### Điều xảy ra khi runner ném exception

Nếu `service.closeDay(...)` ném một exception không được xử lý, `SpringApplication.run(...)` có thể kết thúc bằng exception **trước khi trả về context cho biến `context`**. Khi đó dòng `SpringApplication.exit(context)` nằm sau `run(...)` không được thực thi. Spring Boot có xử lý lỗi khởi động/exit code riêng; cần kiểm chứng mã thoát thực tế với release đang sử dụng.

Không khuyến khích bắt toàn bộ exception ở runner rồi chỉ log:

~~~java
try {
    service.closeDay(businessDate);
} catch (Exception exception) {
    log.error("Close day failed", exception);
    // Sai nếu tiếp tục trả về bình thường:
    // bộ điều phối có thể thấy mã thoát thành công.
}
~~~

Nếu ứng dụng cần mã thoát nghiệp vụ cụ thể, áp dụng `ExitCodeGenerator`, exception tương ứng hoặc exit-code mapping được Spring Boot hỗ trợ theo phiên bản. **Thông điệp lỗi trong log không thay cho mã thoát của tiến trình.**

## 7. Tại sao cần cả SpringApplication.exit và System.exit?

Một ứng dụng `NONE` có thể **tự kết thúc** khi không còn luồng non-daemon và context không giữ tiến trình sống. Tuy nhiên, chỉ trông chờ JVM tự thoát dễ làm kết quả khác nhau khi thêm scheduler, executor, connection pool hoặc thư viện mới.

Hai lời gọi đảm nhiệm hai việc khác nhau:

| Lệnh | Tác dụng chính | Không tự đảm bảo |
|---|---|---|
| `SpringApplication.exit(context)` | Đóng Spring context và tính toán mã thoát thông qua cơ chế Spring Boot | JVM chắc chắn chấm dứt ngay |
| `System.exit(code)` | Yêu cầu JVM kết thúc với mã truyền cho OS | Mọi công việc nền/transaction đều đã hoàn tất |
| `Runtime.getRuntime().halt(code)` | Dừng JVM mà bỏ qua shutdown sequence thông thường | Cleanup, flush, TaskRepository end metadata |

Với CLI task, mẫu `System.exit(SpringApplication.exit(context))` thường phù hợp vì scheduler cần một **exit status có thể quan sát**. Nhưng đừng gọi `System.exit(0)` từ giữa service nghiệp vụ, vì có thể cắt ngang transaction, listener, future và logic kết thúc. Chỉ nên đưa logic thoát vào tầng entrypoint và sau khi runner thực sự kết thúc.

Spring Boot thường đăng ký JVM shutdown hook để đóng context trong tình huống shutdown có kiểm soát. **SIGKILL, crash JVM, OOMKill hoặc mất máy không bảo đảm hook/callback chạy**, do đó TaskExecution có thể không được chốt. Không nên đặt nghĩa vụ ghi kết quả nghiệp vụ duy nhất ở `@PreDestroy` hoặc shutdown hook.

## 8. Không mở HTTP endpoint vẫn có thể dùng những tính năng nào?

`WebApplicationType.NONE` **không vô hiệu hóa** toàn bộ Spring Boot:

| Tính năng | Dùng được trong non-web? | Ghi chú |
|---|---|---|
| Dependency Injection/`@Bean`/`@Service` | Có | Context Spring bình thường |
| `@Transactional` với DataSource | Có | Cần transaction manager tương ứng |
| Spring Cloud Task / `TaskRepository` | Có | Cần dependency và repository thích hợp |
| Spring Batch Job/Step | Có | Dùng cho công việc có checkpoint |
| Outgoing HTTP/`RestClient`/`WebClient` | Có | Không cần embedded server để gọi ra ngoài |
| Messaging client, object storage SDK | Có | Kiểm soát timeout và đóng tài nguyên |
| Logs, structured tracing, metrics nội bộ | Có | Xuất/thu gom qua cơ chế không cần inbound HTTP |
| `@RestController` phục vụ request | **Không** như web server | Không có endpoint inbound hoạt động |
| `/actuator/health` qua HTTP | **Không** theo chế độ NONE | Không có web server để phục vụ HTTP |
| `server.port` | Không phải lựa chọn chính | Không dùng port config thay cho `NONE` |

Non-web không đồng nghĩa **offline**: task vẫn có thể mở outbound connection tới database/API/broker và vẫn cần chính sách mạng, certificate, secret, retry và timeout.

### Khi thật sự cần HTTP status endpoint?

Nếu yêu cầu là “bên ngoài phải gọi `GET /health` trong suốt thời gian xử lý”, hãy xem xét:

- Dùng **một web service điều phối** có HTTP endpoints, chỉ chịu trách nhiệm nhận yêu cầu và kích hoạt task.
- Giữ **task worker không web**; theo dõi qua TaskRepository, Kubernetes Job, logs và metrics/traces gửi ra collector.
- Nếu nhất thiết cần cùng JVM phục vụ HTTP, phải chấp nhận đó là kiến trúc hybrid và thiết kế rõ khi nào server đóng, cách graceful shutdown và cách xác định trạng thái Job; không coi nó tự động là một task hữu hạn tiêu chuẩn.

Với batch ngắn hạn, HTTP readiness/liveness thường không mang lại cùng giá trị như ở server lâu dài; probe quá nghiêm có thể giết task khi nó đang xử lý nặng.

## 9. Các luồng nền có thể giữ JVM sống dù không có web server

Bật `NONE` chỉ loại embedded web server; nó **không tự dừng mọi background thread**.

Ví dụ runner sai:

~~~java
@Bean
ApplicationRunner badRunner(ReportService service) {
    return args -> {
        new Thread(service::generateReport, "report-thread").start();

        // Runner trả về trước khi báo cáo thật sự xong.
    };
}
~~~

Với thread non-daemon, tiến trình có thể tiếp tục sống; với daemon, công việc có thể bị bỏ dở khi JVM thoát. Cả hai đều không phải một lời cam kết hoàn tất.

Các nguồn việc nền cần đặc biệt kiểm tra:

- `@Async`, `TaskExecutor`, `ExecutorService` hoặc `CompletableFuture`.
- `@Scheduled` liên tục hoặc một scheduler không được tắt.
- Listener có vòng nhận message/broker và duy trì connection.
- Consumer nhận việc vô hạn, vòng lặp polling không có điều kiện dừng.
- Async Spring Batch JobLauncher hoặc job vẫn `STARTING/STARTED`.
- Thread tự quản lý không được join/close.

### Mẫu chờ toàn bộ công việc bắt buộc

~~~java
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;

void processPartitions(
        List<Integer> partitions,
        Executor executor,
        PartitionService service) {

    CompletableFuture<?>[] futures = partitions.stream()
        .map(partition -> CompletableFuture.runAsync(
            () -> service.process(partition), executor))
        .toArray(CompletableFuture[]::new);

    // Lỗi từ một partition sẽ được phản ánh lên caller.
    CompletableFuture.allOf(futures).join();
}
~~~

Cần quản lý lifecycle và giới hạn pool executor. `join()` chờ các future hoàn tất nhưng không tự áp deadline; có thể kết hợp timeout và cancellation theo chính sách, đồng thời tránh để worker bị treo I/O. Nếu `join()` ném `CompletionException`, không nuốt nó rồi báo thành công.

**Điểm hoàn tất nên nằm ở tầng nghiệp vụ/runner**, không phải trong hook dọn dẹp hay kiểm tra “đã gửi task cho executor”.

## 10. Spring Cloud Task + Spring Batch trong ứng dụng không web

Spring Batch cũng thích hợp với process non-web. Một ứng dụng chạy Job theo lịch thường không cần endpoint HTTP để quản lý từng Step. Tuy nhiên, cần tránh **khởi chạy Job hai lần**:

- Spring Boot có cơ chế auto-launch một Job lúc startup.
- Ứng dụng có thể tự gọi `JobLauncher` trong `ApplicationRunner`.
- Nếu sử dụng cả hai cách, Job có thể bị launch trùng hoặc gặp lỗi JobInstance đã chạy/hoàn tất.

Khi chủ động điều phối từ runner, cấu hình:

~~~yaml
spring:
  main:
    web-application-type: none
  batch:
    job:
      enabled: false
~~~

Runner tự đọc tham số, xây identifying JobParameters, gọi Job và **kiểm tra trạng thái terminal `JobExecution`**, không mặc định lời gọi launcher trả về là Job đã thành công. Nếu JobLauncher bất đồng bộ, cần chờ/poll đến khi Job kết thúc với timeout phù hợp.

Khi dùng auto-launch của Spring Boot, theo phiên bản Spring Cloud Task Batch có thể hỗ trợ:

~~~properties
spring.cloud.task.batch.fail-on-job-failure=true
~~~

Property này giúp kết quả Job thất bại được phản ánh vào mã thoát task theo cơ chế integration tương ứng. Cần kiểm tra dependency/phiên bản và test cả đường thành công lẫn thất bại.

Lưu ý: `JobRepository` của Spring Batch và `TaskRepository` của Spring Cloud Task **không thay thế nhau**. Chúng có thể chia sẻ DataSource hoặc dùng các schema khác, nhưng phải được cấu hình nhất quán và có migration phù hợp trước khi Job chạy.

## 11. Cấu hình DataSource và TaskRepository cho deployment thực tế

Không-web chỉ mô tả cách tạo ApplicationContext. Khi cần theo dõi kết quả tác vụ **qua nhiều lần chạy và restart**, metadata phải được lưu trong kho bền vững thích hợp.

Ví dụ cấu hình PostgreSQL dùng environment variables:

~~~yaml
spring:
  main:
    web-application-type: none
  application:
    name: daily-close-task
  datasource:
    url: ${TASK_DB_URL}
    username: ${TASK_DB_USER}
    password: ${TASK_DB_PASSWORD}
  cloud:
    task:
      name: daily-close-task
~~~

Ba placeholder `${TASK_DB_URL}`, `${TASK_DB_USER}` và `${TASK_DB_PASSWORD}` được chuyển thành cú pháp Spring property placeholder khi lưu tài liệu. Runtime cần có biến môi trường và quyền truy cập DB phù hợp.

Các bước bắt buộc cho production:

1. Chọn version Spring Boot, Spring Cloud Task và driver JDBC tương thích.
2. Tạo các bảng/sequence của TaskRepository qua migration/schema đúng **dialect và version**.
3. Cấp quyền tài khoản runtime tối thiểu cần thiết; tránh cho user task quyền DDL không cần thiết.
4. Đặt cấu hình kết nối, timeout và pool size phù hợp với số task đồng thời.
5. Xác minh chạy thành công/thất bại có TaskExecution với tên, start/end và exit code như kỳ vọng.
6. Bảo vệ credentials bằng Secret/secret manager, không in toàn bộ argument hoặc environment vào log.

Nếu task chạy 10 Pod đồng thời, mỗi Pod tạo pool 10 connection thì hệ thống có thể mở tới khoảng 100 connection chỉ riêng những task đó. Cần giới hạn pool size và concurrency theo năng lực CSDL.

**Không dựa vào TaskExecution để bảo đảm idempotency:** mỗi retry có thể tạo ID mới. Để chốt doanh thu ngày, nên có khóa nghiệp vụ duy nhất như `(tenant_id, business_date, revision)` trong bảng kết quả, và kiểm tra trước khi ghi tác động ra ngoài.

## 12. Đóng gói ứng dụng không web thành JAR và Docker image

### Chạy JAR trực tiếp

~~~bash
java -jar daily-close-task.jar --date=2026-11-23
~~~

Khi kết thúc, xem **exit code** từ shell:

~~~bash
# Bash / sh sau khi java kết thúc:
echo $?
~~~

Trên PowerShell:

~~~powershell
java -jar daily-close-task.jar --date=2026-11-23
$LASTEXITCODE
~~~

Một task thành công theo chính sách thường trả mã 0; mã khác 0 báo lỗi cho scheduler. Không giả định mọi exception đều được map thành một mã cụ thể nếu ứng dụng chưa cấu hình và kiểm thử.

### Dockerfile tối giản

~~~dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY target/daily-close-task.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
~~~

Image và đường dẫn JAR chỉ là ví dụ; cần chọn Java version phù hợp với Spring Boot release, có build pipeline tạo JAR, quét lỗ hổng và cấu hình user không đặc quyền.

**Dạng exec của `ENTRYPOINT` rất quan trọng**: JVM nhận signal trực tiếp hơn so với shell wrapper không chuyển tiếp tín hiệu. Nếu phải dùng shell script, dùng `exec java -jar ...` ở bước cuối và có xử lý signal đúng. Tránh đặt `java -jar ... &` rồi để shell cha làm PID 1 mà không quản lý việc chờ/thoát.

Không cần `EXPOSE 8080`, không cần Service/Ingress chỉ để chạy một Job không phục vụ HTTP. Container vẫn cần outbound network tới DB/API theo yêu cầu.

## 13. Kubernetes Job: tài nguyên phù hợp hơn Deployment server

Với task hữu hạn, **Kubernetes Job** là loại workload thường phù hợp hơn `Deployment`. Job controller quan sát tiến trình hoàn tất và có thể tạo Pod thay thế khi cần. Một `Deployment` mong muốn giữ các replica lâu dài; khi process thoát 0, nền tảng vẫn cố duy trì Pod, dễ tạo vòng chạy lặp không mong muốn.

Ví dụ Job chạy một lần:

~~~yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: daily-close-20261123
spec:
  backoffLimit: 2
  activeDeadlineSeconds: 1800
  ttlSecondsAfterFinished: 86400
  template:
    spec:
      restartPolicy: Never
      terminationGracePeriodSeconds: 45
      containers:
        - name: daily-close-task
          image: registry.example.org/finance/daily-close-task:1.0.0
          args:
            - "--date=2026-11-23"
          env:
            - name: SPRING_MAIN_WEB_APPLICATION_TYPE
              value: "none"
            - name: TASK_DB_URL
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: jdbc-url
            - name: TASK_DB_USER
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: username
            - name: TASK_DB_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: daily-close-db
                  key: password
          resources:
            requests:
              cpu: "250m"
              memory: "384Mi"
            limits:
              cpu: "1"
              memory: "768Mi"
~~~

Ví dụ giả định Kubernetes Secret `daily-close-db` đã có các key tương ứng và image ở registry có thể được pull; đây không phải manifest tự tạo Secret.

Các trường quan trọng:

| Trường | Ý nghĩa | Lưu ý |
|---|---|---|
| `restartPolicy: Never` | Container thất bại làm Pod thất bại; Job có thể tạo Pod mới | Dễ quan sát các Pod đã lỗi |
| `backoffLimit: 2` | Giới hạn số lần thất bại/retry theo Job controller | Mỗi retry có thể tạo TaskExecution mới và lặp tác động nghiệp vụ |
| `activeDeadlineSeconds: 1800` | Giới hạn thời gian hoạt động tổng của Job | Quá deadline, Job bị đánh dấu lỗi, dù chưa hết backoff |
| `terminationGracePeriodSeconds: 45` | Cơ hội dừng có kiểm soát trước kill | Không bảo đảm worker luôn có trọn 45 giây |
| `ttlSecondsAfterFinished` | Dọn Job/Pod sau khi hoàn tất theo TTL controller | Cần log/metadata lưu ngoài trước khi dọn |
| `resources.requests/limits` | Dự trù và giới hạn CPU/RAM | JVM heap và native memory cần phù hợp |

Kubernetes có thể khởi chạy **cùng một chương trình nhiều lần**, thậm chí một số trường hợp có nhiều Pod gần nhau trong một Job. Vì vậy ứng dụng phải thiết kế **idempotency và an toàn khi chạy đồng thời**; chỉ có `parallelism=1` hoặc `backoffLimit` không thay thế khóa nghiệp vụ.

### Theo dõi Job bằng kubectl

~~~bash
kubectl get job daily-close-20261123
kubectl describe job daily-close-20261123
kubectl get pods -l job-name=daily-close-20261123
kubectl logs job/daily-close-20261123
~~~

Selector label có thể khác theo phiên bản/controller; kiểm tra labels thực tế khi truy vấn. `kubectl logs job/...` thường lấy logs theo đối tượng Job khi được hỗ trợ. TaskRepository vẫn cần được kiểm tra để biết các lần chạy nội bộ và mã thoát ghi nhận được.

## 14. Khi cần lịch chạy lặp: CronJob nhưng ứng dụng vẫn không web

**Kubernetes CronJob** có thể tạo một Job mới theo lịch. Mỗi Job sẽ chạy ứng dụng non-web và kết thúc, thay vì duy trì một web server 24/7.

Ví dụ cấu trúc cơ bản:

~~~yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: daily-close
spec:
  schedule: "0 2 * * *"
  timeZone: "Asia/Ho_Chi_Minh"
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      backoffLimit: 2
      template:
        spec:
          restartPolicy: Never
          containers:
            - name: daily-close-task
              image: registry.example.org/finance/daily-close-task:1.0.0
              args:
                - "--mode=previous-business-day"
~~~

Manifest minh họa giả định ứng dụng hiểu `--mode=previous-business-day` và có logic tính ngày nghiệp vụ theo timezone đã thống nhất. Chỉ đặt `timeZone` cho CronJob **không tự biến mọi Java `LocalDate.now()` thành ngày trong múi giờ đó**; runtime còn phải dùng timezone/ngày xử lý rõ ràng.

`concurrencyPolicy: Forbid` giúp tránh chồng lấn các Job do **cùng CronJob** tạo ra; nó không chặn một lần chạy thủ công, một CronJob khác hoặc hệ thống ngoài kích hoạt cùng business key. Cũng không bảo đảm chính xác một lần: lịch có thể bị bỏ lỡ hoặc kích hoạt thêm trong những điều kiện cụ thể. Tiếp tục dùng unique business key và idempotency.

**Phân biệt:** CronJob **định lịch**, Kubernetes Job **điều phối một lần chạy**, Spring Cloud Task **ghi metadata của JVM task**, và service nghiệp vụ **lưu kết quả thật**. Bốn cấp đều có trách nhiệm riêng.

## 15. Quan sát một ứng dụng không mở HTTP port

Không có `/actuator/health` qua HTTP không đồng nghĩa không giám sát được. Với Job hữu hạn, dùng những nguồn quan sát phù hợp:

| Nguồn | Câu hỏi trả lời |
|---|---|
| Exit code của process/container | Lần chạy kỹ thuật thành công hay thất bại theo chính sách? |
| Kubernetes Job/Pod status | Có tạo Pod được không, có retry/OOMKill/deadline không? |
| Structured logs | TaskExecution ID, business key, lỗi gốc, thời gian xử lý? |
| Spring Cloud TaskRepository | Lần chạy nào đã bắt đầu/kết thúc, exit code, exit message? |
| Spring Batch JobRepository nếu có | Job/Step nào lỗi, checkpoint/restart đến đâu? |
| Business database/output | Kết quả có thật sự được commit không, có bị trùng không? |
| Outbound telemetry | Trace/metric được xuất ra collector bằng giao thức phù hợp? |

Với task ngắn hạn, **metrics có thể phải được push/flush trước khi tiến trình thoát**. Không đặt tất cả thông tin quan sát chỉ ở endpoint Prometheus dạng pull `/actuator/prometheus` khi không chạy web server; collector có thể không bao giờ scrape kịp.

Một quy ước log hữu ích:

~~~text
task.started taskName=daily-close taskExecutionId=418 businessDate=2026-11-23
task.completed taskExecutionId=418 businessDate=2026-11-23 result=APPLIED
~~~

Đây là cấu trúc log **đề xuất**, không phải output mặc định. Không in password, token, nội dung nhạy cảm hoặc toàn bộ arguments vào log.

### Trạng thái TaskRepository có thể khác trạng thái Pod

Khi process chết sau khi commit dữ liệu nhưng trước khi ghi metadata `END_TIME`, bạn có thể thấy:

- Pod Failed hoặc bị OOMKilled.
- TaskExecution còn thiếu `END_TIME`.
- Business result lại đã được commit hoàn toàn.

Không sửa trực tiếp TaskRepository hoặc chạy lại mù quáng. Cần kiểm tra output và khóa idempotency trước khi cho Job retry.

## 16. Những lỗi thiết kế và cấu hình phổ biến

| Triệu chứng | Nguyên nhân thường gặp | Hướng xử lý |
|---|---|---|
| Runner xử lý xong nhưng Pod vẫn Running | Embedded web server, scheduler hoặc non-daemon thread giữ JVM | Đặt `NONE`, loại web starter không cần thiết, quản lý executor/context |
| Log có “Tomcat started on port ...” | Boot đang chạy `SERVLET` | Kiểm tra classpath, active profile, `spring.main.web-application-type` có hiệu lực |
| `server.port=-1` nhưng vẫn có web context | Chưa chuyển sang `NONE` | Dùng `spring.main.web-application-type=none` |
| `@RestController` không nhận request | Ứng dụng đã chọn `NONE` | Tách API điều phối thành web service riêng |
| `/actuator/health` không truy cập được | Không có máy chủ HTTP | Quan sát qua process/Job/TaskRepository hoặc dùng một control plane riêng |
| Exit code là 0 dù nghiệp vụ lỗi | Runner bắt rồi nuốt exception, async chưa xong | Để lỗi lan lên, chờ future, ánh xạ exit code |
| Job báo Completed nhưng output thiếu | Chỉ gửi việc nền, không đợi completion | Đặt điểm hoàn tất nghiệp vụ và commit rõ ràng |
| Job tự chạy lại vô hạn | Dùng Deployment thay Job, cấu hình restart không phù hợp | Dùng Kubernetes Job/CronJob và kiểm soát backoff |
| TaskRepository không có bản ghi | DataSource/schema sai hoặc JVM chết quá sớm | Kiểm tra migration, connection, logs và Job status |
| Có nhiều TaskExecution trùng ngày | Scheduler/Job retry cùng ý định | Unique business key, idempotency và giới hạn concurrency |
| Bị OOMKill dù không có web server | Heap, native memory, batch size hoặc concurrency quá lớn | Giảm memory footprint, chỉnh giới hạn JVM/container |
| `@Scheduled` giữ task chạy mãi | Vô tình thiết kế worker luôn bật lịch nội bộ | Để CronJob/scheduler ngoài khởi chạy tiến trình hữu hạn |
| Liveness probe làm task restart | Áp health probe web-service cho batch | Dùng Job status và deadline; probe phải phản ánh lifecycle task |
| SIGTERM nhưng không cleanup được | Entrypoint shell không forward signal hoặc hết grace period | Dùng exec-form ENTRYPOINT, giới hạn thời gian shutdown |
| Tham số ngày bị sai timezone | Tính ngày trên clock mặc định khác scheduler | Chọn timezone/snapshot và business date rõ ràng |

### Kiểm tra không có HTTP server bằng thực nghiệm

Không chỉ đọc YAML; kiểm tra **cấu hình hiệu lực lúc chạy**. Trên môi trường thử:

1. Chạy ứng dụng bằng JAR với `--spring.main.web-application-type=none`.
2. Quan sát logs: không có thông báo server khởi động hoặc bind cổng.
3. Kiểm tra process không lắng nghe cổng HTTP mà không có nhu cầu.
4. Xác minh runner thực sự xử lý rồi tiến trình thoát với mã phù hợp.
5. Kiểm tra TaskExecution sau lần chạy và dữ liệu nghiệp vụ đã commit.

Đừng coi việc `curl localhost:8080` thất bại là bằng chứng duy nhất: ứng dụng có thể mở cổng khác hoặc còn thread sống; phải quan sát tiến trình và các socket thực tế.

## 17. Lựa chọn triển khai theo yêu cầu sản phẩm

| Yêu cầu | Kiến trúc gợi ý |
|---|---|
| Nhập file theo lịch và thoát | Non-web Spring Cloud Task + CronJob/Kubernetes Job |
| Chạy theo yêu cầu từ UI | Web API điều phối + task non-web được launch qua scheduler/SCDF/TaskLauncher |
| Nhiều bước có checkpoint | Non-web Spring Cloud Task + Spring Batch |
| Chạy lại sau lỗi hạ tầng | Job/CronJob có backoff + business idempotency |
| Yêu cầu HTTP phục vụ liên tục | Web service riêng, không ép task hữu hạn thành server |
| Worker xử lý message vô hạn | Service/consumer dài hạn hoặc worker đặc thù, không mô hình hóa sai thành task một lần |
| Hệ thống đã có Spring Cloud Data Flow | Đăng ký task app non-web, launch theo arguments/properties/deployer và quan sát execution |
| Cần audit qua nhiều lần chạy | TaskRepository bền vững cùng structured log, retention policy |
| Cần nội bộ biết “đang sống” | Process/Job status, heartbeat/metrics thích hợp; không nhất thiết HTTP liveness endpoint |

Một task thường sẽ được triển khai **không web khi sản phẩm của nó là kết quả dữ liệu hoặc side effect cần hoàn thành**, chứ không phải một API endpoint phải phục vụ request lâu dài.

## 18. Checklist trước khi đưa task non-web vào production

- `spring.main.web-application-type=none` được cấu hình rõ ràng và được xác minh lúc runtime.
- Không kéo dependency web server không cần thiết; nếu có vẫn không để tự bật server.
- `ApplicationRunner`/`CommandLineRunner` xác định điểm hoàn tất thực sự, không fire-and-forget.
- Mã thoát của JVM phản ánh đúng thành công/thất bại; không nuốt exception.
- Có cơ chế đóng context/executor và graceful shutdown có deadline.
- TaskRepository dùng DataSource/schema có migration, quyền và cấu hình pool hợp lệ.
- Có business key/idempotency cho retry, chạy bù hoặc chạy đồng thời.
- Nếu có Spring Batch, xác định rõ auto-launch hay custom launcher, kiểm tra JobExecution.
- Container dùng exec-form entrypoint; chọn Kubernetes Job/CronJob thay Deployment khi thích hợp.
- `backoffLimit`, `activeDeadlineSeconds`, CPU/RAM và retention phù hợp khối lượng việc.
- Không đưa secret vào CLI, TaskExecution arguments hay log.
- Có kế hoạch giám sát không phụ thuộc inbound HTTP endpoint.
- Đã kiểm thử run thành công, lỗi nghiệp vụ, OOM/timeout, SIGTERM/SIGKILL và retry.
- Đã kiểm tra kết quả nghiệp vụ sau crash thay vì chỉ nhìn TaskExecution.

**Kết luận:** Đối với Spring Cloud Task có thời gian chạy hữu hạn, **`WebApplicationType.NONE` là lựa chọn triển khai mặc định hợp lý** khi ứng dụng không phục vụ HTTP. Nó loại máy chủ web nhúng, giảm nguy cơ giữ JVM sống ngoài ý muốn và giúp mô hình Job/CronJob tự nhiên hơn. Tuy nhiên, **không-web không tự bảo đảm kết thúc đúng**: runner phải chờ công việc, exception phải ảnh hưởng exit code, context phải được đóng, và kết quả nghiệp vụ phải an toàn trước retry. Kết hợp các nguyên tắc đó với TaskRepository và bộ điều phối sẽ tạo ra một tác vụ có thể quan sát, khôi phục và vận hành ổn định.

### Tài liệu tham khảo

- [Spring Boot — Disabling the Web Server](https://docs.spring.io/spring-boot/how-to/webserver.html)
- [Spring Boot — SpringApplication: Web Environment and Application Exit](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Cloud Task — Reference Guide](https://docs.spring.io/spring-cloud-task/reference/)
- [Kubernetes — Jobs](https://kubernetes.io/docs/concepts/workloads/controllers/job/)
- [Kubernetes — CronJob](https://kubernetes.io/docs/concepts/workloads/controllers/cron-jobs/)
