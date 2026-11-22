# Log event có cấu trúc trong Spring Framework Application Events

**Log event có cấu trúc (structured event logging)** là cách ghi lại việc một application event được phát, tiếp nhận và xử lý bằng những trường có tên, kiểu và ý nghĩa ổn định, thay vì chỉ ghép mọi thông tin vào một câu văn. Trong hệ sinh thái Spring, điều này đặc biệt có ích vì cùng một sự kiện nghiệp vụ có thể được xử lý bởi nhiều `@EventListener`, chạy đồng bộ, bất đồng bộ hoặc chỉ sau khi transaction commit.

Ví dụ, thay vì ghi:

~~~text
INFO Received order event ORD-123 from someone, trace abc
~~~

ta ghi một JSON log record có thể truy vấn theo `event_type`, `event_id`, `aggregate_id`, `correlation_id`, `handler` và `processing_phase`:

~~~json
{
  "@timestamp": "2026-11-11T05:00:00.000Z",
  "level": "INFO",
  "message": "domain_event_observed",
  "event_type": "order.paid",
  "event_id": "evt-123",
  "aggregate_type": "order",
  "aggregate_id": "ORD-123",
  "correlation_id": "corr-456",
  "handler": "order-paid-audit",
  "processing_phase": "received",
  "schema_version": 1
}
~~~

Đây là **JSON minh họa các trường nghiệp vụ**, không phải mẫu khẳng định mọi phiên bản logging backend xuất đúng toàn bộ keys hoặc timestamp trong hình. Spring Boot có thể thêm `logger_name`, `thread_name`, `process.pid` và các trường khác tùy định dạng. Thời điểm trong ví dụ chỉ có mục đích minh họa; log thực tế do backend sinh timestamp lúc ghi.

Mục tiêu không phải tạo ra nhiều log nhất, mà là tạo **dữ liệu quan sát được**, nhất quán để trả lời: “Event nào, thuộc aggregate nào, bắt nguồn từ thao tác nào, được handler nào xử lý ở giai đoạn nào, thành công hay thất bại?”

## 1. Phân biệt domain event, application event và log record

Ba đối tượng khác nhau:

| Khái niệm | Vai trò | Ví dụ |
| --- | --- | --- |
| **Domain event** | Diễn tả một sự thật nghiệp vụ đã phát sinh trong mô hình domain | `OrderPaid(orderId)` |
| **Application event** | Đối tượng được `ApplicationEventPublisher` chuyển đến các listener trong Spring context | Publish một Java record `OrderPaid` |
| **Structured log record** | Bản ghi vận hành có metadata để tìm kiếm, lọc, phân tích | `event_type=order.paid`, `processing_phase=received` |

Một application event được phát trong bộ nhớ **không tự trở thành** log. Spring không tự sinh record đầy đủ về từng domain event với những field do ta mong muốn. Cần ghi log ở các điểm có nghĩa hoặc dùng instrumentation phù hợp.

Ngược lại, log record **không thể thay thế** event bus, transactional outbox, message broker hay event store. Dòng log “event đã được phát” không chứng minh broker đã nhận, listener đã xử lý xong hoặc database đã commit.

### Những câu hỏi operability thường gặp

- Trong 15 phút gần đây, có bao nhiêu event loại `order.paid` thực sự được listener nhận?
- Event `evt-123` đã đi qua những handlers nào? Có handler nào lỗi hoặc bị retry?
- Sau khi trace `corr-456` phát lệnh thanh toán, tất cả log liên quan thuộc những service nào?
- Một aggregate `ORD-123` có log `received` nhưng thiếu `processed` hay không?
- Có duplicate delivery cùng `event_id` xảy ra hay không?
- Sau rollback có còn log “đã gửi mail” hay không, và nhãn phase có phản ánh đúng lifecycle?

Không thể trả lời chính xác bằng cách search chuỗi con mơ hồ hoặc dựa vào thứ tự lẫn lộn trong stdout của nhiều replica. Structured fields giúp câu truy vấn rõ ràng hơn, nhưng vẫn cần thiết kế ngữ nghĩa và thu thập log ổn định.

## 2. Thiết kế schema field cho event log

Mỗi tổ chức có thể chọn snake_case, camelCase hoặc các chuẩn như Elastic Common Schema (ECS). Quan trọng nhất là **ổn định và thống nhất**. Một schema thực dụng cho Spring application events:

| Trường | Kiểu gợi ý | Ý nghĩa |
| --- | --- | --- |
| `@timestamp` | timestamp ISO-8601 | Thời điểm backend ghi log, thường được encoder tự tạo |
| `level` hoặc `log.level` | string | Mức độ log theo format backend |
| `message` | string | Mã thông điệp ổn định, ví dụ `domain_event_observed` |
| `event_type` | string | Tên nghiệp vụ ổn định như `order.paid`, không lệ thuộc package Java |
| `event_id` | string/UUID | Danh tính một logical event, giữ nguyên qua retry/redelivery |
| `aggregate_type` | string | Loại aggregate, ví dụ `order` |
| `aggregate_id` | string | ID aggregate liên quan |
| `correlation_id` | string | Kết nối log của cùng request/workflow |
| `causation_id` | string, optional | ID event/command gây ra event này |
| `handler` | string | Tên listener/consumer ổn định, không nhất thiết FQCN |
| `processing_phase` | enum-like string | `published`, `received`, `processed`, `failed`, `skipped`, ... |
| `attempt` | number, optional | Số lần thử xử lý của cơ chế retry thực |
| `duration_ms` | number, optional | Thời gian xử lý đo thật, không suy đoán |
| `schema_version` | integer | Version của schema domain event hoặc log contract, nêu rõ định nghĩa |
| `trace_id`, `span_id` | string, optional | Liên kết với distributed tracing khi có instrumentation |

**Phân biệt hai thời điểm:** `event_occurred_at` trong payload mô tả lúc sự kiện nghiệp vụ được tạo; `@timestamp` trong log mô tả lúc có log record. Event queue, transaction và async execution có thể khiến hai giá trị khác xa nhau.

**Phân biệt hai ID:** `event_id` xác định một logical event, còn `correlation_id` liên kết nhiều event/log cùng một quy trình. Khi event B do event A tạo ra, dùng `causation_id` để thể hiện quan hệ nhân quả; không dùng cùng `event_id` cho cả hai event độc lập.

**Phân biệt level và outcome:** `INFO`/ `WARN`/ `ERROR` là mức độ quan tâm; `processing_phase=failed` hoặc `outcome=failure` là dữ liệu nghiệp vụ/vận hành. Không phải mọi lần bỏ qua có chủ đích đều là lỗi.

### Ví dụ câu truy vấn

Với hệ thống tìm kiếm hỗ trợ truy vấn theo field, một ý tưởng filter có thể là:

~~~text
service.name = "order-service"
AND event_type = "order.paid"
AND processing_phase = "failed"
~~~

Cú pháp chính xác tùy Logstash/Elastic/Kibana/OpenSearch/Loki/Datadog và mappings của tổ chức; đây chỉ là **mô hình điều kiện**, không phải câu lệnh chạy nguyên xi trên tất cả hệ thống.

## 3. Dùng Spring Boot structured logging có sẵn

Từ **Spring Boot 3.4**, Boot hỗ trợ structured logging JSON sẵn có. Trong Spring Boot 3.5, có thể chọn các format `ecs`, `logstash` hoặc `gelf`; ứng dụng dùng starter logging mặc định thường có Logback.

Ví dụ `src/main/resources/application.properties`:

~~~properties
spring.application.name=order-service
logging.structured.format.console=logstash
logging.level.example.events=INFO
~~~

Khi chạy, các log qua framework được xuất thành từng JSON record theo định dạng Logstash thay vì pattern text mặc định. Nếu cần output vào file riêng:

~~~properties
logging.structured.format.file=logstash
logging.file.name=logs/order-service.json
~~~

Hai dòng thứ hai là **cấu hình tùy chọn**, không bắt buộc cho ví dụ console. Tránh bật đồng thời nhiều appender trùng cùng đích hoặc tự tạo thêm JSON encoder khi Boot đã xuất JSON.

Chọn ECS:

~~~properties
spring.application.name=order-service
logging.structured.format.console=ecs
logging.structured.ecs.service.environment=staging
~~~

Với ECS, cấu trúc các trường nền tảng có thể khác Logstash (ví dụ `log.level` thay cho `level`). **Không hardcode phụ thuộc vào một đường dẫn JSON** trước khi xác định encoder. Spring Boot tích hợp các trường MDC và key-value từ SLF4J fluent logging vào JSON với ECS/Logstash.

**Lưu ý cấu hình Logback custom:** nếu project đã tự khai báo `logback-spring.xml`, property `logging.structured.format.console` có thể không đủ để thay đổi một appender encoder đã cố định. Cần cập nhật custom logging configuration để tôn trọng `CONSOLE_LOG_STRUCTURED_FORMAT` theo tài liệu Boot, rồi kiểm thử JSON đầu ra.

### Vì sao không tự nối chuỗi JSON vào log message?

Cách dễ sai:

~~~java
log.info("{\"event_id\":\"" + id + "\",\"status\":\"ok\"}");
~~~

Mã trên chỉ là trích đoạn **không nên dùng**: `message` có thể chứa một chuỗi JSON lồng trong log JSON của backend, dữ liệu đầu vào không được escape đầy đủ, kiểu số thành chuỗi, dễ injection và khó truy vấn. Hãy dùng **logging API truyền key-value fields**, giao việc JSON serialization cho backend.

## 4. SLF4J 2 fluent API: addKeyValue(...)

SLF4J 2 cho phép đính kèm key-value trực tiếp lên một log statement:

~~~java
log.atInfo()
    .setMessage("domain_event_observed")
    .addKeyValue("event_type", "order.paid")
    .addKeyValue("event_id", event.eventId())
    .addKeyValue("aggregate_id", event.orderId())
    .addKeyValue("handler", "order-paid-audit")
    .addKeyValue("processing_phase", "received")
    .log();
~~~

Đây là **trích đoạn** trong một listener có biến `log` và `event`. Khi dùng backend hỗ trợ structured logging, các cặp key-value có thể thành trường JSON độc lập. Với pattern console thông thường, cùng API vẫn hoạt động, nhưng backend có thể trình bày theo format khác. Tức là `addKeyValue` **không tự bảo đảm JSON** nếu không bật structured encoder.

So sánh:

~~~java
// Khó phân tích theo trường:
log.info("Event {} for order {} handled by {}",
    event.eventId(), event.orderId(), "order-paid-audit");

// Có cấu trúc: type và ý nghĩa của dữ liệu tách khỏi message.
log.atInfo()
    .setMessage("domain_event_observed")
    .addKeyValue("event_id", event.eventId())
    .addKeyValue("aggregate_id", event.orderId())
    .addKeyValue("handler", "order-paid-audit")
    .log();
~~~

Hai đoạn là **phương án thay thế**, không cần log cả hai cho cùng một hành động. Duy trì `message` là một action code ổn định thay vì mỗi event sinh một câu văn chứa dữ liệu động; giá trị động đặt vào fields.

## 5. Ví dụ hoàn chỉnh Java 17+: log một Spring application event thành JSON

Bộ ví dụ dưới dùng **Spring Boot 3.5.x**, Java 17+, SLF4J 2, Logback mặc định và JUnit 5. Khi chạy ứng dụng, một `CommandLineRunner` publish `OrderPaid`; một `@EventListener` ghi **một** log record chứa event metadata dưới dạng JSON. Test publish thêm một event có ID riêng rồi parse log thật bằng Jackson.

### 5.1. settings.gradle

~~~groovy
rootProject.name = 'structured-event-logging'
~~~

### 5.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-json'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot plugin quản lý dependency versions; không cần tự thêm một `slf4j-api` hoặc Logback provider lệch phiên bản. Nếu project đã có Spring Boot starter khác hoặc BOM của tổ chức, tận dụng bộ dependency tương thích đang dùng.

### 5.3. application.properties

Tạo file `src/main/resources/application.properties`:

~~~properties
spring.application.name=order-service
logging.structured.format.console=logstash
logging.level.example.events=INFO
~~~

Cấu hình này vừa dùng cho `bootRun`, vừa được load vào môi trường của test theo `@SpringBootTest`.

### 5.4. EventLogApplication.java

Tạo file `src/main/java/example/events/EventLogApplication.java`:

~~~java
package example.events;

import java.time.Instant;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

@SpringBootApplication
public class EventLogApplication {

    public static void main(String[] args) {
        SpringApplication.run(EventLogApplication.class, args);
    }

    @Bean
    CommandLineRunner publishDemoEvent(
            ApplicationEventPublisher publisher) {
        return args -> publisher.publishEvent(new OrderPaid(
            "evt-demo-001",
            "ORD-001",
            "corr-demo-001",
            1,
            Instant.parse("2026-11-11T05:00:00Z")
        ));
    }
}

// Immutable payload, không phải Logback/JSON object.
record OrderPaid(
    String eventId,
    String orderId,
    String correlationId,
    int schemaVersion,
    Instant occurredAt
) { }

@Component
class OrderPaidLogListener {

    private static final Logger log =
        LoggerFactory.getLogger(OrderPaidLogListener.class);

    @EventListener
    public void onOrderPaid(OrderPaid event) {
        log.atInfo()
            .setMessage("domain_event_observed")
            .addKeyValue("event_type", "order.paid")
            .addKeyValue("event_id", event.eventId())
            .addKeyValue("aggregate_type", "order")
            .addKeyValue("aggregate_id", event.orderId())
            .addKeyValue("correlation_id", event.correlationId())
            .addKeyValue("schema_version", event.schemaVersion())
            .addKeyValue("event_occurred_at",
                event.occurredAt().toString())
            .addKeyValue("handler", "order-paid-audit")
            .addKeyValue("processing_phase", "received")
            .log();
    }
}
~~~

`OrderPaid` ở đây là Java record (không kế thừa `ApplicationEvent`). Spring có thể publish đối tượng payload như một application event và map tới `@EventListener(OrderPaid)`. Listener `OrderPaidLogListener` ghi **mốc nhận event**; nó không chứng minh transaction DB commit hay consumer bên ngoài đã xử lý xong.

Nếu chạy từ project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Trên Windows PowerShell, dùng `./gradlew.bat bootRun`. Giữa các JSON log line lúc khởi động, sẽ có dòng **có hình dạng tương tự** (các trường do Boot thêm hoặc thứ tự khóa có thể khác):

~~~json
{"@timestamp":"2026-11-11T05:30:00Z","@version":"1","message":"domain_event_observed","logger_name":"example.events.OrderPaidLogListener","thread_name":"main","level":"INFO","event_type":"order.paid","event_id":"evt-demo-001","aggregate_type":"order","aggregate_id":"ORD-001","correlation_id":"corr-demo-001","schema_version":1,"event_occurred_at":"2026-11-11T05:00:00Z","handler":"order-paid-audit","processing_phase":"received"}
~~~

**Đây là output minh họa, không phải stdout nguyên văn của một lần chạy thực tế.** `@timestamp` và các metadata hệ thống thực tế được tạo tại thời điểm logging; giá trị `event_occurred_at` do record event cung cấp, nên hai timestamp có thể khác nhau.

## 6. Kiểm thử JSON log thực tế với OutputCaptureExtension

Không chỉ assert rằng listener đã được gọi. Để xác nhận **structured logging contract**, test nên kiểm tra một dòng JSON có đủ trường và đúng kiểu dữ liệu. Spring Boot cung cấp `OutputCaptureExtension` và `CapturedOutput` để thu stdout/stderr trong JUnit 5.

Tạo file `src/test/java/example/events/StructuredEventLogTest.java`:

~~~java
package example.events;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Instant;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
import org.springframework.context.ApplicationEventPublisher;

@SpringBootTest(
    classes = EventLogApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ExtendWith(OutputCaptureExtension.class)
class StructuredEventLogTest {

    @Autowired ApplicationEventPublisher publisher;
    @Autowired ObjectMapper mapper;

    @Test
    void eventLogContainsQueryableFieldsAndNoCredentials(
            CapturedOutput output) throws Exception {

        publisher.publishEvent(new OrderPaid(
            "evt-test-249",
            "ORD-249",
            "corr-test-249",
            1,
            Instant.parse("2026-11-11T05:00:00Z")
        ));

        String jsonLine = output.getOut()
            .lines()
            .filter(line -> line.startsWith("{"))
            .filter(line -> line.contains(
                "\"event_id\":\"evt-test-249\""))
            .findFirst()
            .orElseThrow(() -> new AssertionError(
                "No structured event log found"
            ));

        JsonNode log = mapper.readTree(jsonLine);

        assertEquals(
            "domain_event_observed",
            log.path("message").asText()
        );
        assertEquals("order.paid", log.path("event_type").asText());
        assertEquals("evt-test-249", log.path("event_id").asText());
        assertEquals("ORD-249", log.path("aggregate_id").asText());
        assertEquals(
            "corr-test-249",
            log.path("correlation_id").asText()
        );
        assertEquals("received", log.path("processing_phase").asText());
        assertEquals(1, log.path("schema_version").asInt());
        assertEquals("INFO", log.path("level").asText());

        assertTrue(log.has("@timestamp"));
        assertFalse(log.has("password"));
        assertFalse(log.has("access_token"));
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests "example.events.StructuredEventLogTest"
~~~

Windows PowerShell:

~~~powershell
./gradlew.bat test --tests "example.events.StructuredEventLogTest"
~~~

**Điều test thực sự chứng minh:**

1. Event được publish thông qua `ApplicationEventPublisher`, listener được Spring gọi bằng cơ chế thật.
2. JSON log do **logging backend** phát ra có `message` và các khóa nghiệp vụ truy vấn được, không chỉ có một chuỗi mô phỏng JSON.
3. `schema_version` được kiểm tra như số, các ID được kiểm tra như text; không phụ thuộc thứ tự các thuộc tính JSON.
4. Test tìm một log event có `event_id` riêng, không nhầm với log startup hoặc demo event của `CommandLineRunner`.
5. Không có hai khóa nhạy cảm `password`, `access_token` trong record **được kiểm tra**.

Test kiểm tra **một record cụ thể**, không chứng minh mọi log trên toàn hệ thống đã được redacted. Muốn bảo đảm privacy, phải có thêm kiểm thử với dữ liệu nhạy cảm, code review, logging policy và kiểm soát đầu vào.

Nếu project có cấu hình Logback/Log4j2 tùy biến, `CapturedOutput` có thể cần cấu hình phù hợp để appender ghi vào stream mà test bắt được. Dùng Spring Boot logging mặc định như ví dụ giúp tránh khác biệt đó. Tùy phiên bản và cách chạy test, Gradle có thể không in toàn bộ JSON lên stdout của build; assertion đọc trực tiếp đối tượng `CapturedOutput`, không dựa vào log text của Gradle.

## 7. Ghi log theo lifecycle: published, received, processed, failed

Một event có thể đi qua nhiều listener và nhiều boundary. **Log từng mốc theo ý nghĩa đúng, không gán nhãn thành công quá sớm.**

~~~text
Command xử lý
   |
   +-- domain event tạo ra
   +-- publishEvent(event)
          |
          +-- @EventListener A nhận --> xử lý --> log processed / failed
          |
          +-- @EventListener B nhận --> xử lý --> log processed / failed
          |
          +-- @TransactionalEventListener(AFTER_COMMIT)
                  |
                  +-- callback sau commit --> log observed_after_commit
                  +-- external side effect thành công --> log delivery_succeeded
~~~

Trong dispatch đồng bộ mặc định, `publishEvent` có thể gọi listener ngay trong thread publisher, trước khi database commit. Trong `@Async`, caller có thể trả về trước khi listener chạy. Với `@TransactionalEventListener`, callback gắn với phase của transaction. Do vậy, không nên dùng một nhãn `event_sent` cho tất cả mốc.

| Điểm ghi | Message/phase ví dụ | Có thể kết luận gì? | Không nên kết luận |
| --- | --- | --- | --- |
| Trước `publishEvent` | `event_publish_requested` | Application code có ý định publish | Listener đã nhận |
| Listener bắt đầu | `domain_event_observed` / `received` | Listener đã được gọi | Xử lý xong |
| Sau xử lý thành công | `domain_event_processed` / `processed` | Handler hoàn thành công việc được log | Toàn bộ transaction đã commit |
| Trong `catch` | `domain_event_failed` / `failed` | Handler đã ghi nhận lỗi | Hệ thống đã retry thành công |
| Callback `AFTER_COMMIT` | `after_commit_handler_started` | DB transaction nguồn đã commit | Email/broker đã nhận |
| Sau ack của broker | `integration_event_published` | Theo semantics ack của broker đã cấu hình | Consumer downstream đã xử lý xong |

Đặc biệt: khi một `@EventListener` đồng bộ ném exception, `publishEvent` có thể ném exception ngược đến service. Nếu code ghi “published successfully” **trước** lời publish và sau đó rollback, log đó vẫn tồn tại; cần đặt nhãn `attempted` hoặc `publish_requested`, không nói “business_committed”.

### Ghi lỗi theo cấu trúc

Khi listener gặp exception, đừng ném cả payload và exception message nhạy cảm vào log:

~~~java
try {
    handler.process(event);
} catch (RuntimeException ex) {
    log.atError()
        .setMessage("domain_event_processing_failed")
        .addKeyValue("event_type", "order.paid")
        .addKeyValue("event_id", event.eventId())
        .addKeyValue("handler", "order-paid-audit")
        .addKeyValue("processing_phase", "failed")
        .setCause(ex)
        .log();
    throw ex;
}
~~~

Đây là **trích đoạn**, cần khai báo `handler`, `event` và `log`. `setCause(ex)` cho backend ghi thông tin exception/stack trace theo cấu hình, có thể chứa dữ liệu nhạy cảm từ message/stack. Với môi trường nhiều dữ liệu nhạy cảm, cần chính sách masking, kiểm soát loại exception và giới hạn stack traces. Đừng tự động bỏ `throw ex` nếu lỗi phải làm transaction rollback theo nghiệp vụ.

## 8. Correlation ID, trace ID và MDC

**Correlation ID** thường do application hoặc API gateway tạo để nối các bước cùng một workflow. **Trace ID/span ID** đến từ hệ thống distributed tracing khi đã bật instrumentation. Chúng có thể liên quan nhưng không đồng nhất: một correlation ID có thể trải qua nhiều traces, retry và message broker.

Để thêm một field dùng chung cho nhiều log trong cùng luồng đồng bộ, SLF4J có `MDC` (Mapped Diagnostic Context):

~~~java
try (MDC.MDCCloseable ignored =
        MDC.putCloseable("correlation_id", correlationId)) {
    log.info("business_step_started");
    publisher.publishEvent(event);
}
~~~

Đây là trích đoạn, cần `org.slf4j.MDC` và các biến `correlationId`, `publisher`, `event`. `MDC.putCloseable` giúp remove field trong `close()`; nó không tự mang context qua thread pool hoặc process boundary. Nếu trước đó trong MDC đã có cùng key, code cần xem xét cơ chế khôi phục giá trị cũ thay vì assume xóa luôn là đúng.

Trong Spring Boot ECS/Logstash JSON, giá trị MDC có thể được đưa vào structured log. Tuy nhiên, **khi listener được chạy `@Async`**, MDC thường là thread-local, không tự truyền qua executor. Có thể dùng `TaskDecorator`/Micrometer Context Propagation khi phù hợp và đã cấu hình, hoặc đặt `correlation_id` trong immutable event payload rồi đính kèm bằng `addKeyValue` ngay tại listener. Cách sau ổn định hơn khi event được chuyển sang broker hoặc xử lý lại ở thời điểm khác.

### Ví dụ một listener async chỉ lấy correlation từ payload

~~~java
@Async("eventExecutor")
@EventListener
public void onOrderPaid(OrderPaid event) {
    log.atInfo()
        .setMessage("domain_event_observed")
        .addKeyValue("event_id", event.eventId())
        .addKeyValue("correlation_id", event.correlationId())
        .addKeyValue("handler", "async-notification")
        .addKeyValue("processing_phase", "received")
        .log();
}
~~~

Đoạn này là **phương án thay thế**, không thêm cùng lúc vào ứng dụng demo nếu chỉ muốn một handler. Cần cấu hình `@EnableAsync` và bean `eventExecutor`. Không kỳ vọng `@Async` tự mang `SecurityContext`, MDC hay transaction thread-bound từ publisher sang worker. Tên `correlation_id` trong event phải xuất phát từ nguồn đáng tin cậy ở tầng ứng dụng.

## 9. Privacy, security và chi phí log

Một event payload có thể chứa email, địa chỉ, token, thông tin thanh toán hoặc các trường có tính nhạy cảm. Structured logging **làm dữ liệu dễ truy vấn hơn**, cũng có thể làm dữ liệu nhạy cảm dễ bị tìm thấy hơn nếu thiết kế sai.

**Nên log:** ID sự kiện, loại sự kiện, loại aggregate, ID aggregate đã đánh giá độ nhạy, correlation ID, handler, mốc xử lý, duration, trạng thái lỗi đã phân loại.

**Không nên log mặc định:** password, access token, authorization header, refresh token, API key, dữ liệu thẻ, raw request/response payload, toàn bộ serialized entity, bản ghi chứa PII không cần thiết.

Khi ID aggregate là dữ liệu nhạy cảm, cân nhắc pseudonymization/hashing phù hợp với mục tiêu truy vấn, kiểm soát quyền đọc log và retention theo chính sách. Không dùng `event.toString()` làm message nếu record chứa trường bí mật.

### Cardinality và logging volume

- `event_type`, `handler`, `processing_phase`: thường có cardinality tương đối thấp, hợp cho grouping/aggregation.
- `event_id`, `aggregate_id`, `correlation_id`: thường cardinality cao, hữu ích cho truy vết; tránh biến chúng thành **metric labels** một cách tùy tiện.
- Một luồng hàng nghìn event/giây với nhiều listeners có thể tạo lượng log lớn. Chọn mức log, sampling và retention theo yêu cầu. Không sampling mù các sự kiện audit hoặc security-critical phải lưu theo quy định.
- Không dùng log JSON như database có transactional consistency hoặc nguồn sự thật cho billing/ledger.

Một event có thể được xử lý nhiều lần vì retry hoặc duplicate delivery. Khi log đó là retry lần 3, giữ cùng `event_id` nhưng thêm `attempt=3`; không cấp event ID mới mỗi lần retry nếu muốn tìm lại lịch sử cùng logical event.

## 10. Kết hợp log, metrics và distributed tracing

Observability không chỉ có log. Ba tín hiệu bổ sung:

| Signal | Câu hỏi trả lời tốt | Ví dụ |
| --- | --- | --- |
| **Log** | Event cụ thể đã xảy ra gì? | `event_id=evt-123`, `handler=order-paid-audit`, `processing_phase=failed` |
| **Metric** | Bao nhiêu event/s? Tỉ lệ lỗi, độ trễ thế nào? | Counter theo `event_type`, `handler`, outcome; timer xử lý |
| **Trace** | Event di chuyển qua những bước và service nào? | Span publish/consume với trace/span IDs |

Một design hữu ích: record có `event_id` và `correlation_id` để tìm từng trường hợp; metric đếm theo `event_type` và `handler` (không theo event ID); tracing liên kết các hoạt động đồng bộ/async có instrumentation phù hợp.

Spring Boot Actuator/Micrometer giúp bổ sung metrics/tracing, nhưng **bật structured logging không tự tạo span cho mọi domain event**. Nếu cần span, hãy tạo/propagate context qua observation/tracing infrastructure. Tương tự, khi message qua broker, cần truyền context theo headers thích hợp; không nhầm với serialize nguyên MDC hoặc SecurityContext.

## 11. Các lỗi thiết kế phổ biến

**1. Chỉ đổi sang JSON mà giữ message tự do.** Dòng có `message: "Order ORD-123 paid"` vẫn buộc parser tách chuỗi. Đặt message code ổn định, các giá trị trong fields.

**2. Gọi `log.info(event.toString())`.** Vừa khó tìm theo trường, vừa dễ làm lộ payload. Log một tập field đã được phép.

**3. Ghi `event_id` mới mỗi lần retry.** Mất khả năng nối các attempt; giữ logical event ID và log attempt riêng.

**4. Lẫn event timestamp và log timestamp.** `event_occurred_at` là dữ liệu nghiệp vụ; `@timestamp` là thời điểm ghi log, không nhất thiết bằng nhau.

**5. Ghi `processing_phase=processed` trước khi handler hoàn thành.** Khi exception xảy ra sau đó, log gây hiểu nhầm. Chỉ log `processed` sau khi bước tương ứng thực sự thành công.

**6. Ghi `committed` chỉ vì gọi `publishEvent`.** Trong `@Transactional`, event có thể được publish trước commit và rollback sau đó. Chỉ dùng nhãn phản ánh transaction completion đã xác nhận.

**7. Dựa vào MDC trong async listener mà không propagate.** Thread worker có thể thiếu MDC hoặc reuse context cũ. Đặt correlation ID trong event hoặc dùng context propagation có test.

**8. Log stack trace hoặc payload nhạy cảm nguyên vẹn.** Lộ PII/token vào kho log có nhiều người truy cập. Áp dụng redaction, classification, retention, RBAC và code review.

**9. Gắn `event_id` làm metric label.** Cardinality tăng không giới hạn; dùng các chiều đo tổng hợp có danh mục nhỏ.

**10. Tin rằng structured log chứng minh delivery bền vững.** Log không thay thế outbox, broker ack, idempotency hoặc event store.

**11. Trộn logging providers không tương thích.** SLF4J 2, Logback và Spring Boot nên dùng bộ dependency đồng bộ; một project có nhiều logging backends có thể sinh duplicate hoặc format sai.

**12. Test chỉ assert `output.contains("evt-123")`.** Có thể match raw message trong text pattern, không chứng minh JSON fields. Parse JSON và assert keys, types, một record đúng event ID.

## 12. Checklist triển khai

- [ ] Xác định event types và các handler cần được quan sát, không log vô tội vạ mọi object.
- [ ] Có một schema field ổn định: `event_type`, `event_id`, `aggregate_id`, `correlation_id`, `handler`, `processing_phase`.
- [ ] Có quy tắc đặt `event_id` khi retry và phân biệt `causation_id`/ `correlation_id`.
- [ ] Dùng SLF4J fluent `addKeyValue` hoặc MDC có kiểm soát; backend thực sự xuất JSON.
- [ ] Thống nhất ECS, Logstash hoặc schema của log platform; không giả định tên keys đồng nhất giữa các format.
- [ ] Không log raw credentials/PII; có masking và retention.
- [ ] Nhãn phase phản ánh đúng synchronous/async/transaction boundary.
- [ ] Không suy rằng `@Async` tự propagate MDC, tracing hay SecurityContext.
- [ ] Có integration test kiểm tra JSON output, types, IDs và trường nhạy cảm.
- [ ] Có metrics/tracing bổ sung khi cần, với cardinality được kiểm soát.
- [ ] Không dùng log thay cho event store, outbox hoặc durable delivery.

## 13. Câu hỏi tự kiểm tra

**Câu 1:** Vì sao `log.info("Order " + orderId + " paid")` chưa phải structured event logging?

Vì `orderId` bị nhúng vào message tự do; hệ thống cần parse chuỗi để truy vấn. Structured logging đặt `aggregate_id` thành trường riêng và dùng message code ổn định.

**Câu 2:** Dùng `addKeyValue(...)` có tự động tạo JSON không?

Không. API biểu diễn dữ liệu có cấu trúc; backend/encoder quyết định format output. Trong Spring Boot 3.5 có thể bật `logging.structured.format.console=logstash` hoặc `ecs`.

**Câu 3:** `event_id` và `correlation_id` khác nhau thế nào?

`event_id` định danh một event; `correlation_id` nối nhiều hoạt động/event trong một workflow. Qua retry của cùng logical event nên giữ `event_id` nhưng có thể tăng `attempt`.

**Câu 4:** Có thể gọi event là “đã commit” ngay sau `publishEvent` không?

Không. Lời publish trong Spring event system không tự xác nhận database transaction đã commit; synchronous listener có thể chạy trước commit và event source còn có thể rollback.

**Câu 5:** Vì sao `MDC.put(...)` không đủ cho một async listener?

MDC thường gắn với thread; `@Async` chuyển sang executor thread. Cần propagate context đúng hoặc mang correlation ID trong immutable event payload.

**Câu 6:** Có thể dùng `event_id` làm metric label để đếm lỗi không?

Không nên: mỗi ID gần như duy nhất làm metrics cardinality bùng nổ. Metric gom theo type/handler/outcome; dùng log để điều tra event ID cụ thể.

**Điểm cần nhớ:** structured logging cho Spring application events cần **schema ổn định, field có kiểu rõ ràng, metadata tương quan, nhãn lifecycle trung thực, bảo vệ dữ liệu nhạy cảm và integration test parse JSON thực**. Nó làm observability tốt hơn nhưng không làm application event trở nên bền vững hay thay thế transaction/message delivery guarantees.

## Tài liệu tham khảo

- [Spring Boot 3.5 — Logging: Structured Logging](https://docs.spring.io/spring-boot/3.5/reference/features/logging.html)
- [Spring Boot — Test Utilities: OutputCaptureExtension](https://docs.spring.io/spring-boot/3.5/reference/testing/test-utilities.html)
- [Spring Blog — Structured logging in Spring Boot 3.4](https://spring.io/blog/2024/08/23/structured-logging-in-spring-boot-3-4/)
- [SLF4J 2 — Fluent Logging API](https://www.slf4j.org/manual.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
