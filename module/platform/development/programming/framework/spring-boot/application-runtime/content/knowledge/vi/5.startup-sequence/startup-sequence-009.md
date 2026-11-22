# Các nhánh thất bại và dọn dẹp khi chuỗi khởi động Spring Boot bị gián đoạn

## 1. Vấn đề cần hiểu

Một lần gọi **SpringApplication.run(...)** đi qua nhiều công đoạn: chuẩn bị **Environment**, dựng **ApplicationContext**, nạp định nghĩa bean, **refresh**, khởi động hạ tầng web hoặc thành phần nền, thực thi **ApplicationRunner/CommandLineRunner**, rồi mới công bố ứng dụng sẵn sàng. Exception ở mỗi công đoạn có thể làm lần startup thất bại.

Phân tích lỗi khởi động cần trả lời bốn câu hỏi: **thất bại xảy ra ở giai đoạn nào**, **context đã tồn tại/refresh xong chưa**, **tài nguyên nào đã được tạo và ai sở hữu chúng**, và **hệ thống gọi có nhận biết lỗi bằng log, readiness, exit code hay không**.

Một ứng dụng có thể đã bind cổng HTTP hoặc log “Started ...” nhưng runner vẫn chưa hoàn tất. Một context có thể đã được tạo nhưng chưa đủ an toàn để lấy bean. Ngược lại, có những lỗi xảy ra trước cả khi context tồn tại. Vì vậy không có một callback cleanup chung có thể bảo đảm dọn mọi tài nguyên trong tất cả tình huống.

## 2. Bản đồ các giai đoạn khởi động

Spring Boot công bố các sự kiện quan trọng theo thứ tự logic thông thường:

1. **ApplicationStartingEvent**: ứng dụng bắt đầu; chưa có Environment hoặc ApplicationContext.
2. **ApplicationEnvironmentPreparedEvent**: Environment đã được chuẩn bị ở mức phù hợp, trước khi tạo context.
3. **ApplicationContextInitializedEvent**: context đã được tạo và initializer đã chạy; bean definitions chưa được nạp đầy đủ.
4. **ApplicationPreparedEvent**: context đã được chuẩn bị và nạp bean definitions, nhưng chưa refresh.
5. **Context refresh**: Spring hoàn thiện bean factory, dependency injection, non-lazy singletons, callback khởi tạo và hạ tầng liên quan. Với ứng dụng web, web server thường được thiết lập trong quá trình này.
6. **ApplicationStartedEvent**: context đã refresh thành công; startup runners chưa chạy.
7. **AvailabilityChangeEvent (LivenessState.CORRECT)** xuất hiện theo chuỗi sự kiện mặc định.
8. **ApplicationRunner/CommandLineRunner**: các tác vụ cần chạy khi startup được gọi.
9. **ApplicationReadyEvent**: runner hoàn tất thành công.
10. **AvailabilityChangeEvent (ReadinessState.ACCEPTING_TRAFFIC)**: ứng dụng công bố đã sẵn sàng nhận lưu lượng.

Khi exception làm gián đoạn quá trình **SpringApplication.run(...)**, Spring Boot chuyển sang đường xử lý thất bại, thường thông báo **ApplicationFailedEvent**. Các sự kiện nằm sau điểm lỗi trên đường thành công sẽ không được bảo đảm xảy ra.

~~~text
STARTING
   |
   v
ENVIRONMENT -> CREATE CONTEXT -> PREPARE -> REFRESH
    |                 |             |          |
    +-----------------+-------------+----------+---> FAILURE
                                                   |
                         STARTED -> RUNNERS -> READY
                             |          |
                             +----------+------------> FAILURE
~~~

Đây là sơ đồ khái niệm, không phải log bắt buộc theo từng dòng. **ApplicationFailedEvent** là một dấu hiệu về lỗi startup; bản thân nó không chứng minh toàn bộ tài nguyên đã được dọn xong.

## 3. Các nhánh thất bại và hệ quả

| Thời điểm | Ví dụ nguyên nhân | Trạng thái context | Việc cần chú ý |
| --- | --- | --- | --- |
| Trước khi chuẩn bị Environment | Exception trong mã main hoặc listener bootstrap | Có thể chưa tồn tại | Tự dọn tài nguyên đã cấp phát bên ngoài Spring |
| Environment/config | Lỗi nạp cấu hình, property không hợp lệ hoặc nguồn cấu hình không truy cập được | Có thể chưa tồn tại | Không phụ thuộc @PreDestroy của bean chưa tạo |
| Tạo/chuẩn bị context | Initializer ném exception, lỗi cấu hình sớm | Có thể đã tạo, chưa refresh | Không giả định có thể gọi getBean(...) |
| Trong refresh | BeanCreationException, dependency injection, lỗi khởi tạo singleton, web port bị chiếm | Đã tạo nhưng refresh lỗi | Spring hủy các singleton đã quản lý; kiểm tra phần tài nguyên ngoài container |
| Sau refresh, trước ready | ApplicationRunner/CommandLineRunner ném exception | Context đã refresh | Spring Boot xử lý lỗi và đóng context; callback destroy phù hợp được gọi |
| Sau khi ready | HTTP request, consumer hoặc scheduler nền thất bại | Context đã chạy | Thường là lỗi runtime, cần xử lý theo request/event và chính sách vận hành |

### 3.1. Trước khi có ApplicationContext

Trong các lỗi xảy ra rất sớm, **ApplicationFailedEvent.getApplicationContext() có thể là null**. Vì container chưa được dựng hoàn chỉnh, listener dạng **@EventListener** nằm trong một bean không thể được xem là cách bắt mọi lỗi trước startup. Nếu tự mở socket/tệp/thread ngay trong main hoặc trước khi gọi run(...), phải dùng **try/finally** hoặc **try-with-resources** trong phạm vi tự sở hữu tài nguyên đó.

Đừng gọi **context.getBean(...)** trong listener báo lỗi nếu context null hoặc chưa refresh. Không cố “tiếp tục” startup trong trạng thái chưa được kiểm chứng.

### 3.2. Context refresh thất bại

Trong refresh, Spring có thể đã khởi tạo các singleton và mở connection pool, web server, executor hoặc resource. Nếu một bước tiếp theo ném exception, Spring Framework thực hiện đường hủy những singleton đã tạo và đã được container quản lý. Spring Boot sau đó tiếp tục xử lý startup failure.

Tuy nhiên:

- **@PreDestroy**, **DisposableBean.destroy()** và **@Bean(destroyMethod=...)** phụ thuộc vào bean đã được tạo và đăng ký vòng đời phù hợp.
- Nếu một **constructor hoặc factory method** mở tài nguyên rồi ném exception trước khi trả về bean hoàn chỉnh, container có thể chưa nắm được tài nguyên đó để gọi destroy.
- Tài nguyên tạo bằng static initializer, thread tự chạy hoặc đối tượng được khởi tạo ngoài Spring phải có cơ chế đóng riêng.
- Nếu lỗi do cổng web đã bị chiếm, cần xử lý port conflict hoặc cấu hình đúng; không được nuốt exception để công bố service sẵn sàng dù thiếu server.

### 3.3. Runner thất bại sau refresh

**ApplicationStartedEvent** được công bố trước khi gọi các startup runner. Nếu một **CommandLineRunner** hoặc **ApplicationRunner** ném exception:

- Refresh context đã thành công, nhưng **ApplicationReadyEvent** không xuất hiện theo nhánh thành công.
- Spring Boot thực hiện failure handling và đóng context đã được tạo trong lần khởi động.
- Callback hủy bean quản lý tài nguyên được thực thi khi phù hợp.
- Các tác dụng phụ mà runner đã tạo bên ngoài Spring (ghi DB, gửi message, tạo file, gọi API) **không tự rollback chỉ nhờ context.close()**.
- Web server có thể đã mở cổng trong khoảng thời gian trước lỗi; cần **readiness** thích hợp để không nhận traffic khi startup còn dang dở.

### 3.4. Lỗi sau khi ứng dụng đã ready

Một request HTTP ném exception, tác vụ scheduler nền lỗi hoặc consumer không xử lý được message **không mặc nhiên trở thành lỗi startup**. **ApplicationFailedEvent không phải nơi thu thập mọi exception runtime**.

Cần dùng chính sách xử lý lỗi cho từng request/event: exception handler, retry/backoff, transaction, dead-letter queue, timeout, health/readiness và giám sát. Chỉ dừng cả tiến trình nếu lỗi khiến ứng dụng không còn đủ điều kiện hoạt động và chính sách vận hành yêu cầu.

## 4. Cách Spring Boot báo lỗi khởi động

**ApplicationFailedEvent** thông báo SpringApplication không hoàn tất startup; event mang exception và context đang được tạo **nếu có**. Mục tiêu là nhận diện lần khởi động thất bại, ghi telemetry tối thiểu hoặc hỗ trợ chẩn đoán.

**FailureAnalyzer** xử lý những exception nhận diện được để đưa ra mô tả và hành động khắc phục, ví dụ lỗi **port 8080 đã bị chiếm**. Kết quả có thể được trình bày qua **FailureAnalysisReporter**. Không phải mọi exception đều có FailureAnalyzer, và analyzer **không tự sửa lỗi**.

| Cơ chế | Vai trò | Điều không thể giả định |
| --- | --- | --- |
| ApplicationFailedEvent | Tín hiệu startup thất bại | Context luôn khác null hoặc mọi cleanup đã hoàn tất |
| FailureAnalyzer | Diễn giải exception thành nguyên nhân và hướng sửa | Tự retry hoặc sửa cấu hình |
| Error log và cause chain | Chẩn đoán nguồn lỗi thực tế | Log ngoài cùng luôn là nguyên nhân gốc |
| @PreDestroy, DisposableBean, destroyMethod | Dọn bean đã được quản lý | Dọn mọi đối tượng tạo dở và tài nguyên ngoài Spring |
| try/finally, try-with-resources | Đóng tài nguyên trong phạm vi code cấp phát | Thay thế toàn bộ vòng đời container |
| Exit code và trạng thái workload | Báo thất bại cho tiến trình cha, CI, scheduler | Cho biết đủ nguyên nhân nghiệp vụ |

### Listener cần được đăng ký đủ sớm

Các event trước khi tạo context không thể được bảo đảm nhận bằng listener chỉ đăng ký qua bean. Nếu cần quan sát startup failure từ sớm, hãy gắn listener qua **SpringApplication.addListeners(...)** trước **run(...)**, hoặc cơ chế đăng ký listener sớm do Spring Boot hỗ trợ.

Listener nên gọn, chịu được context null, không mở tài nguyên mới khó đóng, không ghi dữ liệu nhạy cảm, không thực hiện network I/O dài. Nếu listener thất bại trong lúc ghi báo cáo lỗi, tình huống khắc phục sẽ khó hơn.

## 5. Thiết kế cleanup đúng mức sở hữu

### 5.1. Để Spring quản lý bean có tài nguyên

Khi một resource được tạo và sống cùng context, đăng ký callback rõ ràng:

~~~java
@Bean(destroyMethod = "close")
MyClient myClient() {
    return new MyClient();
}
~~~

**Đây là mã minh họa**: MyClient là kiểu nghiệp vụ giả định có phương thức close(); chưa phải chương trình độc lập. Tùy tài nguyên, có thể sử dụng **@PreDestroy**, **DisposableBean** hoặc **SmartLifecycle**. Không đăng ký nhiều cơ chế đóng trùng cho cùng một resource nếu việc đóng không idempotent.

**Điều kiện quan trọng:** container chỉ quản lý bean sau khi quá trình tạo đủ thành công. Một bean đang tạo dở có thể đã gây tác dụng phụ nhưng chưa được Spring quản lý đầy đủ.

### 5.2. Tự dọn nếu một phần quá trình tạo thất bại

Giả sử một factory method mở kết nối rồi tiếp tục cấu hình; nếu bước cấu hình thất bại, cần đóng tài nguyên đã mở tại chỗ:

~~~java
Resource resource = openResource();
try {
    configureResource(resource);
    return resource;
} catch (RuntimeException | Error failure) {
    try {
        resource.close();
    } catch (Exception closeFailure) {
        failure.addSuppressed(closeFailure);
    }
    throw failure;
}
~~~

**Đây là pseudocode Java**, vì Resource/openResource/configureResource là tên đại diện cho API riêng của ứng dụng. Nó minh họa nguyên tắc quan trọng: **không chờ Spring gọi destroyMethod nếu factory method chưa trả về bean thành công**. Khi cleanup cũng lỗi, dùng **addSuppressed(...)** để giữ nguyên exception gốc.

Nếu resource được quản lý bằng **try-with-resources**, ưu tiên dạng đó khi không cần trả quyền sở hữu tài nguyên cho Spring hoặc đối tượng khác.

### 5.3. Cleanup kỹ thuật khác rollback nghiệp vụ

Đóng **ApplicationContext**, connection pool hoặc executor không hoàn tác mọi hiệu ứng bên ngoài. Nếu startup runner đã ghi dữ liệu, gửi Kafka event, gọi API hoặc tạo file trước khi lỗi, retry có thể tạo ra kết quả trùng.

Hãy áp dụng transaction đúng ranh giới, outbox, idempotency key, checkpoint và quy trình bù trừ khi phù hợp. Đừng xóa dữ liệu chỉ để “dọn lỗi” nếu dữ liệu đó đã được hệ thống khác sử dụng. Quyết định rollback cần dựa trên hợp đồng nghiệp vụ.

### 5.4. Tránh System.exit trong bean

Một bean gọi **System.exit(0)** khi gặp lỗi có thể làm hệ thống điều phối tưởng startup thành công; đồng thời bỏ qua logic báo lỗi cấp SpringApplication. Hãy để lỗi bắt buộc làm startup thất bại được ném lên và báo rõ. Với job CLI cần mã thoát riêng, dùng **ExitCodeGenerator**, **ExitCodeExceptionMapper** hoặc **SpringApplication.exit(...)** ở phạm vi phù hợp với hợp đồng tiến trình.

## 6. Ví dụ Spring Boot 3.x/Java 17+: hai nhánh lỗi có thể tái hiện

Ví dụ sau là **một ứng dụng Spring Boot 3.x độc lập**, sử dụng Java 17+ và dependency **spring-boot-starter**. Tạo tệp **src/main/java/example/StartupFailureDemo.java**:

~~~java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.event.ApplicationFailedEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class StartupFailureDemo {

    public static void main(String[] args) {
        SpringApplication app = new SpringApplication(StartupFailureDemo.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        app.addListeners((ApplicationListener<ApplicationFailedEvent>) event -> {
            System.out.println("EVENT_FAILED");
            System.out.println("CONTEXT_PRESENT="
                    + (event.getApplicationContext() != null));
        });

        // Chi duoc gan khi SpringApplication.run(...) thanh cong.
        ConfigurableApplicationContext context = app.run(args);
        context.close();
    }

    @Bean(destroyMethod = "close")
    DemoResource demoResource() {
        return new DemoResource();
    }

    @Bean
    StartupGuard startupGuard(DemoResource resource, Environment environment) {
        String phase = environment.getProperty("demo.fail-phase", "none");
        if ("refresh".equals(phase)) {
            throw new IllegalStateException("demo refresh failure");
        }
        return new StartupGuard();
    }

    @Bean
    CommandLineRunner startupWork(
            StartupGuard guard, Environment environment) {
        return args -> {
            System.out.println("RUNNER_ENTER");
            String phase = environment.getProperty("demo.fail-phase", "none");
            if ("runner".equals(phase)) {
                throw new IllegalStateException("demo runner failure");
            }
        };
    }

    static final class StartupGuard {
    }

    static final class DemoResource implements AutoCloseable {
        DemoResource() {
            System.out.println("RESOURCE_OPEN");
        }

        @Override
        public void close() {
            System.out.println("RESOURCE_CLOSE");
        }
    }
}
~~~

Mô hình được tổ chức để quan sát vòng đời:

- **DemoResource** được khởi tạo như bean, với **destroyMethod="close"**.
- **StartupGuard** phụ thuộc vào DemoResource, nên resource được tạo trước khi kiểm tra nhánh lỗi **refresh**.
- **startupWork** phụ thuộc StartupGuard, nên runner chỉ hoạt động nếu refresh thành công.
- Listener **ApplicationFailedEvent** được gắn trực tiếp vào SpringApplication trước **run(...)**.
- **context.close()** trong main chỉ chạy khi **run(...) trả về thành công**. Ở đường thất bại, Spring Boot xử lý và đóng context theo cơ chế startup failure của nó.

### Chạy thử

Dự án sử dụng Spring Boot Gradle plugin; các lệnh tương ứng:

~~~bash
./gradlew bootRun
./gradlew bootRun --args="--demo.fail-phase=refresh"
./gradlew bootRun --args="--demo.fail-phase=runner"
~~~

Trên Windows PowerShell, thay **./gradlew** bằng **.\gradlew.bat**.

### Kết quả cần tìm trong log/stdout

| Chế độ | Những tín hiệu do code tự in | Điều được chứng minh |
| --- | --- | --- |
| Không chỉ định demo.fail-phase | RESOURCE_OPEN, RUNNER_ENTER, RESOURCE_CLOSE | Refresh/runner thành công; main đóng context |
| demo.fail-phase=refresh | RESOURCE_OPEN, RESOURCE_CLOSE, EVENT_FAILED | Bean lỗi trong refresh; runner không được gọi |
| demo.fail-phase=runner | RESOURCE_OPEN, RUNNER_ENTER, EVENT_FAILED, RESOURCE_CLOSE | Refresh xong, runner ném exception; xảy ra startup failure |

**Bảng mô tả các dòng cần xuất hiện, không áp đặt thứ tự tuyệt đối của mọi dòng.** Trong nhánh refresh, Spring Framework có thể destroy bean đã tạo trong quá trình hủy refresh trước khi listener lỗi được gọi. Các log Spring Boot/Gradle có thể xen kẽ và có stack trace; không có một stdout hoàn toàn cố định.

**RESOURCE_CLOSE trong nhánh refresh** cho thấy **DemoResource** đã được quản lý thành công trước khi bean **StartupGuard** lỗi. Nó không chứng minh rằng Spring sẽ tự dọn mọi resource được constructor tạo dở.

**EVENT_FAILED ở nhánh runner** xảy ra mặc dù context đã refresh. **ApplicationStartedEvent** có thể đã được công bố, nhưng **ApplicationReadyEvent** không được công bố theo nhánh thành công.

### Kiểm chứng sâu hơn

Muốn kiểm thử tự động, có thể thêm listener cho **ApplicationStartedEvent** và **ApplicationReadyEvent** đã đăng ký sớm, rồi kiểm tra runner lỗi không phát ready. Ngoài log, hãy xác nhận resource thực sự giải phóng: connection pool trả kết nối, socket không còn giữ cổng, executor đã shutdown và thread nền không chặn JVM thoát.

Không dùng ví dụ này để đánh giá rollback DB/message: nó chỉ tạo resource giả và ném exception có chủ đích.

## 7. Readiness, liveness và graceful shutdown

**Liveness** biểu thị ứng dụng còn ở trạng thái nền tảng có thể xem là sống; **readiness** biểu thị instance có thể nhận lưu lượng. Theo chuỗi sự kiện Spring Boot, readiness thường được công bố **ACCEPTING_TRAFFIC sau khi startup runners hoàn tất**. Việc web server đã bind cổng không đồng nghĩa instance đã ready.

Khi một service đang chạy bình thường nhận tín hiệu dừng, có thể sử dụng graceful shutdown trên hạ tầng web hỗ trợ:

~~~yaml
server:
  shutdown: graceful
spring:
  lifecycle:
    timeout-per-shutdown-phase: 20s
~~~

Tuy nhiên, **startup failure** có thể xảy ra khi bean/lifecycle processor/web server chưa khởi tạo xong. Vì vậy không mặc định mọi quy trình graceful shutdown của một service đã sẵn sàng sẽ áp dụng nguyên vẹn trong lúc refresh thất bại. Cleanup phụ thuộc vào giai đoạn bị lỗi.

**ApplicationFailedEvent** là tín hiệu chẩn đoán thất bại; **@PreDestroy** là một cơ chế dọn bean; **graceful shutdown** là chính sách dừng có kiểm soát. Chúng giải quyết các phần việc khác nhau.

## 8. Exit code và vận hành khi khởi động lỗi

Đối với CLI/job, **exit code 0** thường biểu thị thành công và **mã khác 0** biểu thị lỗi. Exception startup không được xử lý thường khiến tiến trình Java thất bại, nhưng cần bảo đảm các thread ngoài container không giữ JVM sống và wrapper/IDE/Gradle chuyển mã thoát phù hợp.

Với service, không nên bắt lỗi khởi tạo rồi giả vờ chạy bình thường. Một service chưa sẵn sàng phải được đánh dấu chưa ready hoặc startup fail, để scheduler/container orchestrator xử lý theo chính sách.

Những lỗi thiết kế dễ gây hậu quả:

- **Bắt exception trong runner nhưng không ném lại**, khiến Spring có thể tiếp tục đến ApplicationReadyEvent dù bước khởi tạo bắt buộc thất bại.
- **Gọi System.exit(0) trong catch**, che mất lỗi startup.
- **Throw exception mới mà bỏ cause**, làm mất nguồn lỗi thật.
- **Retry vô hạn ngay trong startup**, giữ readiness ở trạng thái chờ và gây tải lên dependency; nên có timeout và backoff hữu hạn.
- **Tạo thread trực tiếp mà không có cơ chế stop**, khiến JVM sống sau khi khởi động thất bại.
- **Nhầm close context với rollback nghiệp vụ**, dẫn tới lặp message, trùng bản ghi hoặc tác vụ ngoài hệ thống chưa được thu hồi.
- **Dùng readiness thay cho lỗi nghiệp vụ từng request**, khiến một request 500 bị diễn giải nhầm là toàn bộ ứng dụng đã chết.

Khi thao tác trong runner là điều kiện bắt buộc để service nhận traffic, để failure được phản ánh trong startup. Nếu công việc có thể chạy sau khi service sẵn sàng, thiết kế riêng luồng nền, health và giám sát cho công việc đó.

## 9. Quy trình điều tra lỗi thực tế

1. **Đọc exception gốc** trong cause chain; phân biệt wrapper như BeanCreationException với nguyên nhân thật (port, binding, dependency, kết nối).
2. **Xác định giai đoạn cuối đã hoàn tất** dựa vào event/log: Environment, ContextPrepared, refresh, ApplicationStartedEvent, runner, ApplicationReadyEvent.
3. **Xem FailureAnalysis** nếu có. Ví dụ lỗi port đã sử dụng cần sửa conflict hoặc cấu hình; không giải bằng cách nuốt exception.
4. Nếu cần chi tiết điều kiện auto-configuration, có thể bật **--debug** cho lần khởi động chẩn đoán hoặc mức DEBUG của **ConditionEvaluationReportLoggingListener**. Tránh tiết lộ secret khi chia sẻ log.
5. **Kiểm tra bean/resource cleanup**: callback destroy có chạy, socket/thread/executor có còn tồn tại, có resource nào tạo dở hoặc nằm ngoài container không.
6. **Đối chiếu tác dụng phụ bên ngoài**: DB đã commit, API đã nhận request, message đã gửi, file đã ghi hay chưa; chuẩn bị retry/idempotency thích hợp.
7. **Xác nhận tình trạng vận hành**: exit code đúng, instance chưa ready không nhận traffic, lỗi không bị che bởi wrapper.
8. **Tái chạy có kiểm soát** cả nhánh thành công và nhánh lỗi, quan sát resource được giải phóng.

| Câu hỏi | Điều cần làm rõ |
| --- | --- |
| Context đã tồn tại và refresh xong chưa? | Khả năng dùng bean lifecycle và bước startup đã đạt |
| Có ApplicationStartedEvent nhưng thiếu ApplicationReadyEvent? | Kiểm tra runner hoặc failure sau refresh |
| Resource được tạo xong hay đang tạo dở? | Phân biệt container cleanup với cleanup cục bộ |
| Bean có destroy method/@PreDestroy đúng không? | Xác nhận phần vòng đời Spring quản lý |
| Lỗi xuất hiện sau ApplicationReadyEvent? | Xử lý runtime thay vì gán nhầm startup |
| Có tác dụng phụ DB/broker/file đã xảy ra? | Đánh giá rollback, idempotency, checkpoint |
| Có thread ngoài Spring giữ JVM sống? | Kiểm tra shutdown của executor/worker tự tạo |

## 10. Những nhầm lẫn cần tránh

**“ApplicationFailedEvent luôn có context.”** Sai; lỗi sớm có thể xảy ra trước khi context được tạo.

**“@PreDestroy luôn chạy cho bất kỳ tài nguyên nào đã mở.”** Sai; resource phải được đăng ký đúng vòng đời của bean hoặc tự cleanup tại nơi cấp phát.

**“Thấy ApplicationStartedEvent là đã ready.”** Sai; event này xảy ra trước startup runners.

**“Đóng ApplicationContext sẽ xóa hoặc rollback dữ liệu bên ngoài.”** Sai; context.close() không tự hoàn tác file, message hay API call.

**“Lỗi HTTP request sau ready luôn phát ApplicationFailedEvent.”** Sai; đó thường là lỗi runtime có luồng xử lý riêng.

**“Bật graceful shutdown thì lỗi refresh nào cũng cleanup hoàn hảo.”** Sai; trạng thái context có thể chưa hoàn chỉnh.

**“Bắt exception cho app sống tiếp là cách tăng độ bền.”** Chỉ đúng khi lỗi thực sự có thể chịu được; nếu dependency bắt buộc thất bại, công bố ready có thể dẫn tới xử lý sai.

## 11. Tự kiểm tra

1. **Bean A mở connection thành công, bean B lỗi trong refresh.** Spring có thể hủy A nếu A đã được container quản lý đúng; resource tạo dở trong B cần cleanup riêng.
2. **ApplicationStartedEvent đã phát nhưng CommandLineRunner ném exception.** Startup vẫn fail; ApplicationReadyEvent không xuất hiện theo nhánh thành công.
3. **Lỗi ở Environment trước khi tạo context.** Không được giả định listener có thể lấy bean qua DI.
4. **Request HTTP trả 500 sau khi service ready.** Thường là lỗi request/runtime, không mặc nhiên là startup failure.
5. **Runner tạo file rồi ném exception.** Context close không tự xóa file; phải theo chính sách nghiệp vụ.
6. **Cổng đã lắng nghe nhưng readiness chưa ACCEPTING_TRAFFIC.** Hoàn toàn có thể; chờ startup runner hoàn tất.

**Ghi nhớ:** Muốn xử lý đúng một startup failure, phải biết **lỗi nằm ở đâu trong chuỗi khởi động, bean nào đã được Spring quản lý và tác dụng phụ nào còn nằm ngoài Spring**. Kết hợp callback hủy của bean với try/finally cho resource tạo dở, báo lỗi trung thực và thử nghiệm nhánh thất bại có chủ đích.

### Tài liệu tham khảo

- [Spring Boot — SpringApplication: Startup Failure và Application Events](https://docs.spring.io/spring-boot/reference/features/spring-application.html)
- [Spring Boot 3.3 — SpringApplication API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html)
- [Spring Boot — ApplicationFailedEvent API](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/context/event/ApplicationFailedEvent.html)
- [Spring Framework — Bean lifecycle và context](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
