# Giám sát tác vụ định kỳ, xử lý thông điệp hoặc thư viện tích hợp khi được hỗ trợ

## Mục tiêu

Micrometer không yêu cầu ứng dụng tự tạo mọi metric. Nhiều thành phần Java và framework đã có binder hoặc integration để đưa số liệu vận hành vào MeterRegistry. Ví dụ, executor có thể cung cấp số worker đang chạy và số tác vụ trong hàng đợi; Spring có thể tạo Observation cho mỗi lần chạy một phương thức @Scheduled; thư viện messaging có thể ghi thời gian publish hoặc xử lý message.

Các integration này chỉ hoạt động khi loại tài nguyên, thư viện và phiên bản đang dùng được hỗ trợ. Cần phân biệt ba phạm vi:

- **Pool metrics:** trạng thái của executor hoặc scheduler như active threads, queue size, pool size và số tác vụ hoàn tất.
- **Task/message metrics:** thời gian thực thi một job hoặc xử lý một message, cùng kết quả thành công hay thất bại.
- **Library metrics:** thống kê do client hoặc thư viện cung cấp, chẳng hạn Kafka client, RabbitMQ connection factory, Hibernate hoặc Spring Integration.

Sau bài này, bạn có thể chọn binder phù hợp, bật quan sát tác vụ định kỳ, đọc metrics xử lý message, nhận biết điều kiện auto-configuration của Spring Boot và kiểm tra số liệu mà không đăng ký trùng meter.

## Các cách tích hợp built-in

Micrometer và Spring Boot có nhiều cách đưa số liệu vào registry:

| Cơ chế | Vai trò | Ví dụ |
|---|---|---|
| MeterBinder | Đăng ký một nhóm meter từ một đối tượng có sẵn | ExecutorServiceMetrics, JVM binders |
| Executor wrapper | Bọc executor để đo cả thời gian tác vụ | ExecutorServiceMetrics.monitor(...) |
| Observation | Ghi nhận một hoạt động có điểm bắt đầu, kết thúc và metadata | Tác vụ @Scheduled, publish/process message |
| Library listener/integration | Lắng nghe vòng đời hoặc hoạt động của thư viện | Kafka producer/consumer, RabbitMQ, Hibernate |
| Spring Boot auto-configuration | Tự nối các integration được hỗ trợ vào MeterRegistry | ThreadPoolTaskScheduler, JmsTemplate, DataSource |

Một thư viện có hỗ trợ metrics không có nghĩa mọi hành vi của thư viện đều được đo. Hãy đọc rõ metric nào được tạo, điều kiện bật, tag mặc định và phạm vi thời gian mà metric đại diện.

## Giám sát executor và scheduler

### ExecutorServiceMetrics theo dõi điều gì?

Micrometer cung cấp ExecutorServiceMetrics trong package binder.jvm để theo dõi các executor được hỗ trợ, chủ yếu là ThreadPoolExecutor và ForkJoinPool.

Với ThreadPoolExecutor, các meter thường gặp gồm:

| Meter | Loại | Ý nghĩa |
|---|---|---|
| executor | Timer | Thời gian chạy tác vụ khi dùng executor wrapper |
| executor.idle | Timer | Thời gian tác vụ chờ trong queue trước khi chạy |
| executor.completed | FunctionCounter | Tổng số tác vụ hoàn tất, giá trị xấp xỉ |
| executor.active | Gauge | Số thread hiện đang thực thi tác vụ |
| executor.queued | Gauge | Số tác vụ đang chờ trong queue |
| executor.queue.remaining | Gauge | Sức chứa queue còn lại theo khả năng hiện tại |
| executor.pool.size | Gauge | Số thread hiện có trong pool |
| executor.pool.core | Gauge | Kích thước core của pool |
| executor.pool.max | Gauge | Số thread tối đa được phép |

Các giá trị này giúp phát hiện pool bão hòa. Ví dụ, active tiến gần pool.max trong khi queued tăng liên tục có thể cho thấy tốc độ nhận tác vụ cao hơn tốc độ xử lý.

Với ForkJoinPool, nhóm meter khác nhau và có thêm thông tin như steals, running, parallelism hoặc delayed tùy loại pool và phiên bản Java. Không giả định mọi loại executor đều xuất ra cùng một tập meter.

### Binder trực tiếp và monitor wrapper

Có hai cách dùng phổ biến:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tags;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;

ExecutorServiceMetrics binder = new ExecutorServiceMetrics(
        executorService,
        "image-processing",
        Tags.of("role", "background")
);
binder.bindTo(registry);
~~~

Cách này đăng ký các meter trạng thái của executor. Nó không tự đo thời lượng từng tác vụ được gửi vào executor.

Nếu muốn có thêm Timer cho thời gian thực thi và thời gian chờ trong queue, dùng monitor(...). Phương thức trả về một executor wrapper; hãy gửi mọi tác vụ qua đối tượng được trả về:

~~~java
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;

import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

ScheduledExecutorService scheduler = ExecutorServiceMetrics.monitor(
        registry,
        new ScheduledThreadPoolExecutor(2),
        "maintenance",
        Tag.of("task.group", "scheduled")
);

scheduler.scheduleWithFixedDelay(
        this::removeExpiredRecords,
        0,
        1,
        TimeUnit.MINUTES
);
~~~

Wrapper này đo trạng thái pool và thời gian thực thi tác vụ. Các meter được đăng ký cho executor wrapper sẽ được gỡ khi wrapper được shutdown. Vì vậy, hãy shutdown đối tượng trả về:

~~~java
scheduler.shutdown();
if (!scheduler.awaitTermination(30, TimeUnit.SECONDS)) {
    scheduler.shutdownNow();
}
~~~

Không tiếp tục submit task qua executor gốc sau khi đã bọc. Làm vậy sẽ bỏ qua instrumentation và có thể khiến số liệu không bao phủ toàn bộ công việc.

Không đăng ký đồng thời binder và wrapper cho cùng executor với cùng tên/tag nếu không có chủ đích. Hai lần bind có thể tạo xung đột meter identity hoặc làm số liệu khó diễn giải.

### Spring Boot tự instrument task executor và task scheduler

Khi có Spring Boot Actuator và Micrometer phù hợp, Spring Boot tự instrument các bean ThreadPoolTaskExecutor và ThreadPoolTaskScheduler nếu executor nền ThreadPoolExecutor có thể truy cập được. Metrics được gắn tag name theo bean name.

Ví dụ một scheduler do ứng dụng khai báo:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskScheduler;

@Configuration(proxyBeanMethods = false)
public class TaskSchedulingConfiguration {

    @Bean
    ThreadPoolTaskScheduler maintenanceScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(3);
        scheduler.setThreadNamePrefix("maintenance-");
        scheduler.setWaitForTasksToCompleteOnShutdown(true);
        return scheduler;
    }
}
~~~

Bean này được Spring Boot nhận diện và instrument theo tên maintenanceScheduler khi điều kiện auto-configuration phù hợp. Không cần tạo một ExecutorServiceMetrics binder thứ hai cho cùng scheduler.

Nếu ứng dụng dùng SimpleAsyncTaskExecutor hoặc scheduler không dựa trên ThreadPoolExecutor, các meter về kích thước pool và queue có thể không có. Hãy xác minh loại executor thực tế thay vì suy ra từ việc ứng dụng có @Async hoặc @Scheduled.

### Pool metrics không thay thế task metrics

ExecutorServiceMetrics cho biết pool đang hoạt động thế nào. Nó không tự trả lời:

- Một công việc nghiệp vụ cụ thể chạy thành công hay thất bại?
- Job định kỳ có chạy đúng thời điểm dự kiến không?
- Công việc đã bị bỏ qua hoặc trễ lịch bao lâu?
- Một message đã chờ trong broker bao lâu trước khi consumer nhận?

Để đo thời gian và kết quả từng lần chạy, dùng Observation của Spring Framework hoặc instrument nghiệp vụ riêng. Để đo backlog, hãy dùng queue depth hoặc consumer lag do broker/client cung cấp nếu có.

## Giám sát từng lần chạy @Scheduled bằng Observation

Spring Framework hỗ trợ Observation cho mỗi lần thực thi phương thức @Scheduled từ Spring Framework 6.1. Observation có tên mặc định tasks.scheduled.execution và có thể tạo Timer metrics cũng như trace khi hệ thống observation được cấu hình.

Để bật ghi nhận, gắn ObservationRegistry vào ScheduledTaskRegistrar:

~~~java
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;
import org.springframework.scheduling.annotation.SchedulingConfigurer;
import org.springframework.scheduling.config.ScheduledTaskRegistrar;

@Configuration(proxyBeanMethods = false)
@EnableScheduling
public class SchedulingObservationConfiguration implements SchedulingConfigurer {
    private final ObservationRegistry observationRegistry;

    public SchedulingObservationConfiguration(
            ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    @Override
    public void configureTasks(ScheduledTaskRegistrar taskRegistrar) {
        taskRegistrar.setObservationRegistry(observationRegistry);
    }
}
~~~

Một job có thể được viết như sau:

~~~java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

@Component
public class ReconciliationJob {

    @Scheduled(fixedDelay = 60_000)
    public void reconcile() {
        // Đọc trạng thái và đối chiếu dữ liệu cần xử lý.
    }
}
~~~

Mỗi lần gọi reconcile() sẽ có một observation. Các low-cardinality key mặc định gồm:

| Key | Ý nghĩa |
|---|---|
| code.function | Tên phương thức được lập lịch |
| code.namespace | Tên đầy đủ của lớp chứa phương thức |
| error | Tên lớp exception hoặc none |
| outcome | SUCCESS, ERROR hoặc UNKNOWN |

Những tag này giúp phân biệt job và kết quả mà không tạo một series cho mỗi lần chạy. Không thêm thời điểm chạy, request ID hoặc dữ liệu đầu vào riêng của từng lần chạy làm metric tag.

### Observation đo thời gian chạy, không đo độ trễ lịch

tasks.scheduled.execution đo thời gian thực thi của mỗi lần gọi. Nó không tự cho biết task bắt đầu muộn bao nhiêu so với thời điểm cron dự kiến, có lần chạy nào bị bỏ qua hay khoảng cách giữa hai lần hoàn tất có bất thường hay không.

Nếu cần đo schedule lag, hãy so sánh thời điểm bắt đầu thực tế với thời điểm dự kiến hoặc tạo metric nghiệp vụ riêng. Nếu cần biết công việc hoàn tất đúng hạn, hãy theo dõi thêm thời điểm thành công gần nhất hoặc một SLO cho chu kỳ chạy.

## Giám sát xử lý thông điệp

### JMS publish và process

Spring Boot có thể instrument các JmsTemplate và phương thức @JmsListener có sẵn trong application context. Hai observation thường gặp là:

- jms.message.publish: thời gian gửi message đến broker.
- jms.message.process: thời gian ứng dụng xử lý message đã nhận.

Spring Framework cung cấp Jakarta JMS instrumentation khi dependency Micrometer Jakarta tương ứng có mặt và ObservationRegistry được cấu hình cho thành phần JMS. Trong Spring Boot, auto-configuration nối các integration được hỗ trợ cho JmsTemplate và listener.

Hai phép đo này trả lời thời gian gửi và thời gian xử lý. Chúng không đo thời gian message nằm chờ trong broker trước khi được giao cho consumer. Muốn theo dõi backlog hoặc tuổi message, cần dùng số liệu broker hoặc metadata thời điểm enqueue.

### Kafka listener và KafkaTemplate

Spring for Apache Kafka cung cấp Timer cho listener và thao tác gửi qua KafkaTemplate khi Micrometer được phát hiện trên classpath và application context có một MeterRegistry. Các timer thường có tên:

| Meter | Ý nghĩa | Tag tiêu biểu |
|---|---|---|
| spring.kafka.listener | Thời gian xử lý một lần gọi listener | name, result, exception |
| spring.kafka.template | Thời gian gửi qua KafkaTemplate | name, result, exception |

Với container chạy đồng thời, tag name của listener có thể được thêm hậu tố theo từng thread/container con. Điều này giúp xem phân bố thời gian theo consumer worker.

Spring Kafka cũng có MicrometerConsumerListener và MicrometerProducerListener để quản lý KafkaClientMetrics khi producer/consumer được tạo hoặc đóng. Spring Boot tự đăng ký listener cho các factory được auto-configure. Với factory tự tạo, cần kiểm tra xem listener đã được nối hay chưa.

Từ Spring Kafka 3.0, có thể bật Observation cho KafkaTemplate và listener container. Khi observationEnabled được bật, các Timer cũ do integration quản lý sẽ được thay bằng metrics do Observation quản lý. Không bật cả hai chỉ với mục đích tạo thêm một bộ Timer cho cùng thao tác.

Nếu listener xử lý batch, mặc định có thể chỉ tạo một observation cho cả batch. Nếu cần observation từng record, kiểm tra cấu hình recordObservationsInBatch của phiên bản Spring Kafka đang dùng. Không diễn giải một observation batch thành số lượng message riêng lẻ.

### RabbitMQ và Spring Integration

Spring Boot tự instrument các RabbitMQ connection factory có sẵn với metric tên rabbitmq. Đây là số liệu của connection factory và client; không mặc định đồng nghĩa với thời gian xử lý nghiệp vụ của từng message.

Spring Integration cung cấp Micrometer support khi có MeterRegistry bean. Metrics được xuất dưới prefix spring.integration. Các channel, handler hoặc component cụ thể có thể có meter tùy cấu hình và loại integration.

Khi cần latency của handler hoặc nghiệp vụ sau khi nhận message, hãy kiểm tra Observation support của integration đang dùng. Nếu thành phần không tự tạo observation, có thể instrument điểm xử lý bằng Observation hoặc Timer.

## Một số thư viện có built-in metrics

Spring Boot và Micrometer có nhiều integration khác ngoài executor và messaging:

| Thành phần | Điều kiện hoặc cách bật | Nhóm metric |
|---|---|---|
| JVM | Spring Boot auto-configuration hoặc JVM binders | Memory, buffer pool, GC, thread, class loading |
| DataSource | DataSource có metadata provider được hỗ trợ | Active, idle, min/max connections; Hikari có prefix riêng |
| Hibernate | Có hibernate-micrometer và bật hibernate.generate_statistics | Thống kê Hibernate theo EntityManagerFactory |
| Spring Data Repository | Spring Boot auto-configuration | Thời gian và trạng thái invocation |
| MongoDB | MongoClient auto-configured | Command timer và connection pool gauges |
| Kafka | Spring Kafka factory listeners hoặc auto-configuration | Producer/consumer client metrics và listener/template timers |
| RabbitMQ | RabbitMQ connection factory được auto-configure | Connection/client metrics |
| Spring Integration | Có MeterRegistry bean | Metrics của các integration component |

Ví dụ bật Hibernate statistics:

~~~yaml
spring:
  jpa:
    properties:
      "[hibernate.generate_statistics]": true
~~~

Đồng thời cần có dependency org.hibernate.orm:hibernate-micrometer trong runtime classpath. Chỉ bật property mà thiếu integration dependency thì không đủ để tạo Hibernate metrics.

Không phải mọi thư viện đều có binder. Nếu không có integration chính thức, hãy kiểm tra thư viện có listener, callback hoặc statistics API hay không. Khi cần, viết binder nhỏ đọc trạng thái nguồn hoặc tạo Observation tại ranh giới thao tác. Không dùng reflection hoặc truy cập nội bộ không ổn định chỉ để cố lấy metrics.

## Cách kiểm tra metrics đã được đăng ký

### Dùng Actuator metrics endpoint

Spring Boot cung cấp endpoint chẩn đoán /actuator/metrics. Endpoint này không nhất thiết được expose qua HTTP mặc định; cần cấu hình exposure phù hợp:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,metrics
~~~

Liệt kê meter name:

~~~http
GET /actuator/metrics
~~~

Đọc một meter và lọc theo tag:

~~~http
GET /actuator/metrics/executor.active?tag=name:maintenanceScheduler
GET /actuator/metrics/tasks.scheduled.execution
GET /actuator/metrics/jms.message.process
~~~

Tên ở Actuator endpoint là tên meter Micrometer trước khi registry chuyển sang naming convention của backend. Ví dụ Prometheus có thể chuyển dấu chấm thành dấu gạch dưới. Hãy xem tên thực tế tại endpoint export hoặc backend.

### Diễn giải cùng lúc pool, task và message

Một dashboard vận hành nên đặt các nhóm metric cạnh nhau:

| Quan sát | Cách diễn giải |
|---|---|
| executor.active gần pool.max, executor.queued tăng | Pool có thể thiếu năng lực xử lý |
| executor.idle tăng | Tác vụ chờ lâu trước khi được chạy |
| tasks.scheduled.execution tăng | Bản thân job định kỳ chạy lâu hơn |
| outcome=ERROR tăng | Job định kỳ thường xuyên thất bại |
| spring.kafka.listener duration tăng | Listener xử lý chậm hơn |
| Kafka consumer lag tăng | Message tích lũy chưa được xử lý kịp |
| jms.message.process duration tăng | Thời gian xử lý message trong ứng dụng tăng |
| RabbitMQ queue depth tăng | Broker đang giữ nhiều message chờ |

Một Timer xử lý message có thể tăng trong khi queue depth vẫn thấp; ngược lại, listener có thể xử lý nhanh nhưng consumer không đủ số worker để theo kịp tốc độ đến. Hãy kết hợp metric từ ứng dụng với metric của broker.

## Kiểm thử binder executor

SimpleMeterRegistry phù hợp để xác minh meter do ExecutorServiceMetrics đăng ký:

~~~java
import io.micrometer.core.instrument.Tag;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.binder.jvm.ExecutorServiceMetrics;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.ScheduledThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

import static org.assertj.core.api.Assertions.assertThat;

class ExecutorMetricsTest {
    @Test
    void monitorRecordsTaskExecutionAndRemovesMetersOnShutdown() throws Exception {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        ScheduledExecutorService executor = ExecutorServiceMetrics.monitor(
                registry,
                new ScheduledThreadPoolExecutor(1),
                "test-scheduler",
                Tag.of("role", "test")
        );

        try {
            executor.submit(() -> { }).get(5, TimeUnit.SECONDS);

            Timer execution = registry.get("executor")
                    .tag("name", "test-scheduler")
                    .timer();
            assertThat(execution.count()).isEqualTo(1);
        } finally {
            executor.shutdown();
            assertThat(registry.find("executor")
                    .tag("name", "test-scheduler")
                    .timer()).isNull();
            executor.awaitTermination(5, TimeUnit.SECONDS);
            registry.close();
        }
    }
}
~~~

Test này xác minh wrapper đo một lần thực thi. Trong integration test, hãy xác minh meter được gỡ khi executor shutdown và không còn task nào tiếp tục ghi qua executor gốc.

### Kiểm thử message integration

SimpleMeterRegistry không thay thế được kiểm thử với broker thật. Với JMS hoặc Kafka, nên có integration test xác nhận:

1. Publish một message thử nghiệm.
2. Listener nhận và xử lý message.
3. Timer hoặc Observation tương ứng tăng count.
4. Nhánh xử lý lỗi được phản ánh trong outcome/result.
5. Các tag giữ cardinality thấp.
6. Đóng producer, consumer hoặc listener container không để lại meter động ngoài vòng đời mong muốn.

Nếu dùng batch listener, xác nhận count phản ánh một batch hay từng record theo cấu hình. Không giả định hai chế độ có cùng semantics.

## Kiểm soát tag và cardinality

Built-in integration thường cung cấp tag mặc định có ý nghĩa như executor bean name, listener name, result hoặc exception class. Khi bổ sung tag, hãy giữ tập giá trị hữu hạn.

Không dùng các giá trị sau làm metric tag:

- Message ID hoặc correlation ID duy nhất.
- User ID, email hoặc customer ID.
- Nội dung message hoặc payload.
- Raw exception message.
- URL đầy đủ chứa query string hoặc dữ liệu cá nhân.

Nếu cần truy vết một message riêng, dùng trace/log correlation. Metrics nên dùng destination, listener, operation, result hoặc nhóm lỗi có số lượng hữu hạn.

## Những lỗi thường gặp

**Nhầm pool metrics với business metrics.** executor.active và executor.queued mô tả pool; chúng không xác nhận job hoàn tất đúng hạn.

**Cho rằng mọi @Scheduled đều tự có Observation.** Cần Spring Framework hỗ trợ và ObservationRegistry được gắn vào ScheduledTaskRegistrar.

**Dùng binder nhưng kỳ vọng có task Timer.** ExecutorServiceMetrics.bindTo() đăng ký số liệu pool; dùng monitor() để bọc executor và đo thời gian task.

**Đo message processing như queue wait.** Timer của listener đo thời gian xử lý trong ứng dụng, không phải thời gian message nằm trong broker.

**Bật Observation và Timer legacy cùng lúc.** Một số integration thay Timer bằng Observation khi bật observationEnabled. Kiểm tra semantics trước khi cộng hoặc so sánh count.

**Tự đăng ký meter trùng với auto-configuration.** Spring Boot có thể đã instrument executor, Kafka factory hoặc DataSource. Kiểm tra registry trước khi thêm binder thủ công.

**Kỳ vọng mọi thư viện đều có binder.** Built-in metrics phụ thuộc loại thư viện, dependency, phiên bản và cách tạo bean. Với integration không được hỗ trợ, cần instrument thủ công.

**Đưa message ID vào tag.** Mỗi message tạo một series mới, làm cardinality tăng rất nhanh.

## Checklist triển khai

1. Xác định đang cần pool health, task execution, message processing hay client/library metrics.
2. Kiểm tra loại executor hoặc thư viện có nằm trong phạm vi hỗ trợ không.
3. Ưu tiên Spring Boot auto-configuration nếu bean đã được hỗ trợ.
4. Dùng ExecutorServiceMetrics.bindTo() cho pool metrics hoặc monitor() khi cần task timers.
5. Với @Scheduled, gắn ObservationRegistry vào ScheduledTaskRegistrar và kiểm tra Spring Framework version.
6. Với JMS/Kafka, xác minh integration, observationEnabled và listener/template factory.
7. Phân biệt processing duration, queue wait, queue depth và consumer lag.
8. Không bind thủ công lần thứ hai nếu auto-configuration đã tạo cùng meter.
9. Giữ tag có cardinality thấp và không chứa định danh từng message.
10. Kiểm tra /actuator/metrics và endpoint export của backend.
11. Viết unit test cho binder và integration test cho broker khi cần.
12. Xác minh vòng đời executor, listener và client để tránh meter tồn tại ngoài tài nguyên.

## Kết luận

Built-in metrics giúp quan sát executor, scheduler, message integration và thư viện mà không phải tự đo mọi thao tác. ExecutorServiceMetrics cho biết trạng thái pool và có thể bọc executor để đo thời gian task; Spring Observation đo từng lần chạy @Scheduled; JMS và Kafka có integration cho publish/process; Spring Boot còn tự nối một số binder và client metrics khi dependency cùng loại bean được hỗ trợ. Hãy kiểm tra điều kiện auto-configuration, phân biệt thời gian xử lý với backlog, giữ tag có cardinality thấp và kiểm thử vòng đời của thành phần được instrument.

## Tài liệu tham khảo

- [Micrometer - JVM and Executor Metrics](https://docs.micrometer.io/micrometer/reference/reference/jvm.html): JVM binders, ExecutorServiceMetrics, monitor và các meter của executor.
- [Spring Boot - Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): task execution, JMS, DataSource, Hibernate, RabbitMQ, Kafka, Spring Integration và các auto-configured metrics.
- [Spring Framework - Observability Support](https://docs.spring.io/spring-framework/reference/integration/observability.html): Observation, tác vụ @Scheduled và JMS publish/process.
- [Spring for Apache Kafka - Monitoring](https://docs.spring.io/spring-kafka/reference/kafka/micrometer.html): listener/template timers, native Kafka client metrics và Observation.
- [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes): phiên bản giới thiệu Observation instrumentation cho @Scheduled.
