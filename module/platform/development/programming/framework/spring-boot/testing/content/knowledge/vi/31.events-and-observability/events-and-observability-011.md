# CapturedOutput hoặc công cụ ghi log thử nghiệm khi log là hành vi cần chứng minh

## 1. Khi nào log là một hành vi cần đưa vào bài kiểm thử?

Thông thường, test nên chứng minh **kết quả nghiệp vụ**: đơn hàng đã lưu, endpoint trả đúng JSON, transaction rollback, message được gửi, hoặc sự kiện được phát. Log chỉ là tín hiệu chẩn đoán, có thể thay đổi theo logger/backend/formatter và không nên là điều kiện duy nhất để tuyên bố nghiệp vụ thành công.

Tuy nhiên, trong nhóm **Sự kiện và observability** của Spring Boot, log đôi lúc chính là một phần của **hợp đồng quan sát (observability contract)**. Ví dụ:

- Một batch job thất bại phải phát sự kiện log `job_failed` ở mức `ERROR`, có `jobId` và loại lỗi phù hợp để đội vận hành tìm được nguyên nhân.
- Một validation/business rejection phải được ghi ở `WARN`, không bị ngụy trang thành `INFO job_completed`.
- Khi xử lý request bất đồng bộ, log phải giữ `correlationId`/trace context để ghép các bước trong cùng một flow.
- Một bước xử lý đã hoàn tất phải ghi một event có tên/fields ổn định phục vụ alert, audit pipeline hoặc support runbook.
- **Credential, bearer token, password, payment secret và dữ liệu cá nhân nhạy cảm không được xuất hiện** trong những log events mà ứng dụng kiểm soát.
- Hợp đồng structured JSON logging phải có các trường machine-readable mà downstream queries/alerts thực sự sử dụng.

Đối với các yêu cầu này, log là thứ đáng test **trực tiếp**, song cần chọn đúng mức quan sát:

1. `OutputCaptureExtension` + `CapturedOutput` để kiểm văn bản thực sự được ghi vào **`System.out` và `System.err`** trong JUnit 5.
2. Logback `ListAppender<ILoggingEvent>` (hoặc một appender test riêng) để kiểm **log event** ở trước formatter: level, logger name, message template, rendered message, arguments, MDC và throwable.
3. Queue-based test appender để đợi log từ background thread với **timeout**, tránh race trên async code.
4. Integration test của structured JSON encoder/formatter hoặc collector pipeline khi **JSON/log ingestion** cũng thuộc hợp đồng.

**Giới hạn quan trọng:** Assert thấy một dòng INFO ở stdout **không chứng minh** log đã tới Elasticsearch/Loki/Cloud Logging, metric đã tăng, trace đã được export, hoặc sự kiện audit đã được lưu bền vững. Mỗi boundary cần kiểm thử riêng nếu requirement đòi.

### Mục tiêu của bài

Sau bài, bạn có thể:

- Giải thích khác biệt giữa `System.out/err`, SLF4J, Logback/Log4j2, appenders, encoders và log aggregation.
- Dùng `@ExtendWith(OutputCaptureExtension.class)` và inject `CapturedOutput` vào JUnit 5 test method.
- Phân biệt `output.getOut()`, `output.getErr()`, `output.getAll()` và `assertThat(output)`.
- Biết lúc nào log console capture đủ và lúc nào cần quan sát sự kiện logger gốc.
- Dùng Logback `ListAppender` với `getLevel()`, `getLoggerName()`, `getMessage()`, `getFormattedMessage()`, `getArgumentArray()`, `getMDCPropertyMap()` và `getThrowableProxy()`.
- Attach/stop/detach test appender đúng lifecycle, không làm nhiễm các bài kiểm thử khác.
- Kiểm log async bằng `BlockingQueue`/`Future.get(timeout)` mà không dùng `Thread.sleep`.
- Kiểm correlation ID/MDC cleanup/propagation, log level, exception type, redaction và structured JSON fields.
- Viết assertions ổn định, không phụ thuộc timestamp, PID, thứ tự output của các threads khác hoặc log format không thuộc hợp đồng.
- Phân biệt test log event với kiểm **business event** hoặc **durable audit record**.
- Chạy dự án mẫu **Java 17 + Spring Boot 3.5.16 + Maven + JUnit Jupiter + AssertJ + SLF4J/Logback**.

## 2. Logging pipeline trong Spring Boot

### 2.1. Dòng dữ liệu thực tế

~~~text
Ứng dụng
  |
  +-- System.out.println(...) -------------------------+
  |                                                    |
  +-- System.err.println(...) -------------------------+--> System streams
  |                                                    |         |
  +-- SLF4J Logger.info/warn/error(...)                |         v
            |                                          |    OutputCaptureExtension
            v                                          |    CapturedOutput
        Logging implementation                         |    (chỉ bắt stream)
        Logback mặc định qua Boot starters              |
            |                                          |
            +-- logger level/filter                     |
            +-- ILoggingEvent (template/args/MDC/error) |
                    |                                  |
                    +-- ListAppender (test event)      |
                    |                                  |
                    +-- ConsoleAppender/encoder -------+
                    |
                    +-- File/Socket/Async/remote appender
                                     |
                                     v
                          Log collector/aggregator
                          index, retention, alerts
~~~

Spring Boot mặc định dùng Logback khi bạn dùng những starters thông thường. Boot tự cấu hình log về console và có thể cấu hình file. Java Util Logging (JUL), Log4j2 và các adapter khác có thể được route khác nhau tùy classpath/logging configuration.

`CapturedOutput` **không phải** một “logger spy”. Nó quan sát những gì đi qua hai global streams. Nếu logger:
- Ghi trực tiếp vào file hoặc network appender;
- Bị level filter chặn;
- Dùng async appender chưa flush;
- Đã bind output stream cũ khi JVM redirect streams;
- Hoặc dùng test logging configuration không có console appender;

thì `CapturedOutput` có thể **không thấy** sự kiện, dù logging subsystem đã xử lý nó theo cách khác.

Ngược lại, `ListAppender` attach vào Logback logger nhìn thấy `ILoggingEvent` **khi logger dispatch event tới appender**. Nó không chứng minh encoder đã xuất đúng JSON hoặc collector đã nhận event.

### 2.2. Các tầng của một log event

| Tầng | Ví dụ cần xác minh | Công cụ phù hợp |
| --- | --- | --- |
| Quyết định log | Job fail phải gọi `log.error` | Appender event |
| Level | `WARN` chứ không phải `INFO` | `ILoggingEvent.getLevel()` |
| Logger | `com.example.logging.JobLogService` | `getLoggerName()` |
| Message template | `event=job_completed jobId={} itemsProcessed={}` | `getMessage()` |
| Rendered message | `event=job_completed jobId=run1 itemsProcessed=2` | `getFormattedMessage()` |
| Arguments | Job ID, count | `getArgumentArray()` |
| Throwable | Root exception class/message | `getThrowableProxy()` |
| MDC | `correlationId=run1` | `getMDCPropertyMap()` |
| Console text | INFO line thực xuất ra terminal | `CapturedOutput.getOut()/getAll()` |
| Structured JSON | JSON level, MDC, event, timestamp | Captured JSON + Jackson parse |
| Centralized ingestion | Event vào index/stream đúng tenant | Collector/shipper integration |
| Durable audit | Record được lưu, query/recover được | Database/outbox/readback |

Không dùng một công cụ để kết luận về tất cả các tầng.

### 2.3. Event business khác log event

Một `ApplicationEventPublisher.publishEvent(new OrderCreated(...))` là Spring application event; một `log.info("order created")` là log event. Chúng có vòng đời và guarantees khác nhau.

- Application event có thể có synchronous/asynchronous listeners theo cấu hình.
- Log event có thể bị filter/sample/drop, format lại, đẩy sang file/collector.
- Durable domain event dùng outbox/broker thường cần retry và idempotent delivery.
- Không dùng “đã thấy log” làm bằng chứng listener business đã commit transaction hoặc outbox đã publish tới broker.

Nếu lesson yêu cầu **kiểm log vì log là hợp đồng**, hãy kiểm log; nếu requirement là business event durable, assert business event storage/queue/consumer, log chỉ hỗ trợ chẩn đoán.

## 3. Khi nào nên và không nên assert log?

### 3.1. Trường hợp nên assert

- Hệ thống có runbook yêu cầu event key `job_failed` và `jobId`.
- Alert được tạo bằng log query `level=ERROR AND event=job_failed`.
- Compliance/security policy yêu cầu **không** in raw token hoặc password.
- Một warning là tín hiệu được sản phẩm cam kết khi dùng fallback/degraded mode.
- Correlation ID phải tồn tại để trace các bước trong request/job.
- Exception type/reason code phải phân biệt lỗi permanent vs retryable.
- Structured log là API cho pipeline giám sát downstream.

### 3.2. Trường hợp không nên biến log thành assertion chính

- Controller trả HTTP 200 và đúng JSON; không cần assert “Started controller” nếu không thuộc contract.
- Repository lưu entity; cần query committed state, không chỉ dòng “Saved entity”.
- Message producer gửi thành công; kiểm broker acknowledgment/consumer receipt, không chỉ “Publishing message”.
- Lỗi transaction; cần kiểm rollback, không chỉ dòng “Rollback”.
- Unit test phép cộng; kiểm result, không phụ thuộc log debug nội bộ.
- Log của Spring/Tomcat/Hibernate thay đổi qua patch version nhưng không liên quan app contract.

**Quy tắc review:** Mỗi log assertion nên trả lời câu “Nếu log này biến mất hoặc sai trường, người dùng/đội vận hành/collector sẽ chịu hậu quả nào?”. Nếu không có câu trả lời cụ thể, test có thể gây maintenance noise.

### 3.3. Một test thường cần hai loại assertion

Ví dụ job bị từ chối:

~~~text
Business assertion: result = REJECTED, không có side effect.
Observability assertion: WARN event=job_rejected, jobId đúng,
                        reason=invalid_input, không có job_completed.
~~~

Chỉ có log assertion có thể PASS dù job thực sự tạo data sai. Chỉ có business assertion có thể PASS trong khi alert pipeline thiếu event critical. Khi cả hai là requirement, kiểm cả hai.

## 4. CapturedOutput và OutputCaptureExtension của Spring Boot

### 4.1. Thành phần chính xác

Spring Boot test module cung cấp:

~~~java
import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;
~~~

`OutputCaptureExtension` là **JUnit Jupiter extension**, đăng ký bằng:

~~~java
@ExtendWith(OutputCaptureExtension.class)
class StreamTest {
    @Test
    void writesExpectedOutput(CapturedOutput output) {
        System.out.println("job finished");
        assertThat(output.getOut()).contains("job finished");
    }
}
~~~

Đoạn trên là snippet cần thêm imports JUnit/AssertJ, không phải file độc lập ở mục project. Nó không cần `@SpringBootTest` nếu chỉ muốn capture stdout/stderr hoặc test một POJO.

`CapturedOutput` là interface mở quyền đọc nội dung đã capture:
- `getOut()`: văn bản từ `System.out`.
- `getErr()`: văn bản từ `System.err`.
- `getAll()`: tổng hai streams theo thứ tự mà cơ chế capture quan sát.
- Bản thân `CapturedOutput` implement `CharSequence`, nên `assertThat(output).contains(...)` tiện để kiểm tổng output.

Nó **không** có ý nghĩa “trả tất cả events từ mọi logger”, “đợi async logs tự động” hay “chỉ các logs từ method dưới test”. Hai stream là tài nguyên **global trong JVM**.

### 4.2. Ghi ra stream và log qua backend không đồng nghĩa

~~~java
System.out.println("STATUS_OK");
System.err.println("STATUS_ERROR");
logger.info("event=job_completed");
~~~

- Hai lời gọi `System.*.println` sẽ xuất hiện trên streams nếu capture đang active.
- `logger.info` chỉ xuất hiện trong `CapturedOutput` nếu backend/appender được cấu hình ghi tới stream đang được capture và event không bị filter.
- Trong Spring Boot mặc định với Logback console, capture log text thường phù hợp.
- Trong ứng dụng custom Logback/Log4j2/JUL, cần kiểm stream binding, appender type và initialization.

Bởi vậy khi mục tiêu là `level=ERROR` hoặc `MDC.correlationId`, **log event appender** thường đáng tin hơn dò một dòng text đã render.

### 4.3. Đúng phạm vi JUnit lifecycle

Khai báo extension ở class; inject `CapturedOutput` vào method. Extension quản lý capture trong lifecycle test. Không tự đóng hay restore `System.out` bên trong test; extension có trách nhiệm đó.

Nếu phải test console messages phát ra trong **Spring ApplicationContext startup**, cần chú ý thứ tự tạo context, Boot logging initialization, JUnit extensions và context caching. Một context được reuse có thể không khởi động lại ở test method thứ hai, nên không có startup message mới để capture. Đừng assert “Started Application” trong mỗi test method như một điều kiện business.

### 4.4. Tránh assert toàn bộ output

Không làm:

~~~java
assertThat(output.getAll()).isEqualTo(
        "2026-11-08 15:00:00 INFO main JobLogService ...");
~~~

Timestamp, timezone, PID, thread, whitespace, ANSI colors, app name và logger abbreviation có thể thay đổi. Hãy kiểm **marker/event name và fields ổn định** mà contract yêu cầu.

Ví dụ:

~~~java
assertThat(output.getAll())
        .contains("event=job_completed")
        .contains("jobId=run_42");
~~~

Dù vậy, nếu hai dòng khác nhau chứa hai fragments, cách assert trên **toàn output** chưa chứng minh chúng nằm cùng event. Dùng appender hoặc parse từng line và lọc theo `jobId` khi sự kết hợp fields quan trọng.

### 4.5. Không dùng substring quá mơ hồ

~~~java
assertThat(output).contains("failed");
~~~

“failed” có thể đến từ stacktrace/framework startup, một test khác, hay message hoàn toàn khác. Dùng một marker cụ thể như `event=job_failed jobId=run_42 category=dependency_timeout`, hoặc query events theo logger/level/message template.

### 4.6. OutputCaptureExtension không thay logging configuration

Nếu bạn đặt `logging.level.com.example=ERROR`, một lời gọi `log.info` không được phát xuống appender. `CapturedOutput` không thể làm INFO “hiện ra”. Test phải cấu hình logger level đúng với contract đang kiểm, nhưng không nâng toàn bộ root logger lên DEBUG chỉ để bắt được một dòng.

## 5. Cách dùng Logback ListAppender

### 5.1. Tại sao cần ListAppender?

Với Logback backend mặc định của Spring Boot 3.5, `ch.qos.logback.core.read.ListAppender<ILoggingEvent>` là appender test đơn giản lưu các log events vào list. Nó cho phép assert **dữ liệu event trước formatting**:

~~~java
Logger logger = (Logger) LoggerFactory.getLogger(JobLogService.class);

ListAppender<ILoggingEvent> appender = new ListAppender<>();
appender.setContext(logger.getLoggerContext());
appender.start();
logger.addAppender(appender);

try {
    service.execute("job_1", "test-credential", false);
    assertThat(appender.list)
            .anySatisfy(event ->
                    assertThat(event.getLevel())
                            .isEqualTo(Level.INFO));
}
finally {
    logger.detachAppender(appender);
    appender.stop();
}
~~~

Đây là snippet; imports và class thật có ở lab bên dưới.

`appender.list` lưu **events của logger được attach**. Nếu attach vào **root logger**, test có thể nhận rất nhiều events từ framework/other beans, khiến assertions yếu và nhiễu. Nên attach vào logger của **class cụ thể** khi contract thuộc class đó.

### 5.2. Mỗi phần của ILoggingEvent có ý nghĩa riêng

| API | Ý nghĩa | Assertion đáng tin |
| --- | --- | --- |
| `getLevel()` | INFO/WARN/ERROR | WARN cho validation rejection |
| `getLoggerName()` | Tên logger | Event phát từ service cần kiểm |
| `getMessage()` | Message template gốc | Kiểm marker/placeholder convention |
| `getFormattedMessage()` | Message sau SLF4J formatting | Kiểm jobId/reason/count |
| `getArgumentArray()` | Các arguments truyền vào logger | Kiểm giá trị thực, không phụ thuộc timestamp |
| `getMDCPropertyMap()` | MDC snapshot của event | Correlation ID đã gán đúng |
| `getThrowableProxy()` | Throwable metadata | Event ERROR có exception type đúng |
| `getThreadName()` | Thread phát event | Hữu ích trong async test khi requirement |
| `getTimeStamp()` | Thời điểm event | Dùng time ranges khi thật sự cần; không exact timestamp |

Message template có thể được xem là một **event schema text tối giản** khi downstream tìm theo prefix. Với structured logging chuẩn hơn, hãy dùng JSON encoder/fields để tránh parse một chuỗi tự do.

### 5.3. Attach trước hành động, detach sau hành động

Một appender chỉ thu events xảy ra sau khi nó được attach, không truy ngược logs cũ. Trong JUnit:
- `@BeforeEach`: tạo, start, attach.
- Test method: trigger action, await completion, inspect events.
- `@AfterEach`: detach, stop; kể cả khi assertion fail.

Không sửa root logger level hoặc gắn appender mà không tháo; test sau có thể nhận logs của test trước, gây memory leak và kết quả không lặp lại.

### 5.4. ListAppender không là wait primitive cho async

`ListAppender.list` là một list phục vụ đọc events khi đã emit xong. Nếu worker trên thread khác chưa chạy, lập tức gọi `appender.list.size()` có thể trả 0. Poll list không đồng bộ giữa threads cũng không phải cách an toàn mặc định.

Đối với async, dùng:
- `Future.get(timeout)` hoặc completion stage để biết worker đã xong.
- Hoặc một `BlockingQueue` được appender test đưa events vào rồi `poll(timeout)`.
- Nếu backend dùng asynchronous appender/encoder, đợi tiêu chí ở **đúng tầng** cần kiểm.

Lab có riêng một appender dùng `LinkedBlockingQueue` để minh họa.

## 6. Thiết kế log contract để test ít flaky

### 6.1. Event names và fields ổn định

Với batch job, thay vì:

~~~text
I think maybe item processing is finished for customer ABC
~~~

nên ưu tiên một contract rõ:

~~~text
event=job_started jobId=run_42
event=job_completed jobId=run_42 itemsProcessed=2
event=job_rejected jobId=run_43 reason=invalid_input
event=job_failed jobId=run_44 category=dependency_timeout
~~~

Không nhất thiết giữ nguyên cả câu tiếng Anh; điều quan trọng là tên sự kiện, business correlation ID, error category, version/schema và level được quản lý.

### 6.2. Level phù hợp

| Hành vi | Mức thường hợp lý | Lý do |
| --- | --- | --- |
| Bắt đầu job thường lệ | INFO/DEBUG theo volume | Truy vết startup |
| Hoàn tất job thành công | INFO hoặc event telemetry có sampling | Quan sát thành công |
| Input validation bị từ chối | WARN hoặc INFO theo business semantics | Không nhầm infrastructure error |
| Dependency timeout làm job fail | ERROR nếu cần operational response | Báo sự cố có nguyên nhân |
| Retry bình thường với backoff | WARN/INFO có count | Tránh bão ERROR khi recoverable |
| Chi tiết step-by-step thường lệ | DEBUG/TRACE | Không tạo noise production |
| Thông tin bí mật | **Không log** | Bảo mật |

Mức log là policy, không phải quy tắc cố định mọi domain. Một invalid user request có thể là INFO thay vì WARN ở traffic volume lớn; test theo **contract đã chọn**, không suy WARN luôn đúng.

### 6.3. Correlation ID và MDC

Mapped Diagnostic Context (MDC) giữ key/value theo logging context, thường thread-bound. Một `correlationId` giúp liên kết event giữa các bước.

~~~java
String previous = MDC.get("correlationId");
MDC.put("correlationId", jobId);
try {
    // Work and log events.
}
finally {
    if (previous == null) {
        MDC.remove("correlationId");
    }
    else {
        MDC.put("correlationId", previous);
    }
}
~~~

Vì thread pools tái sử dụng threads, **không cleanup MDC** có thể làm log của request A bị gắn correlation ID request B. Nếu code library/servlet filter đã sở hữu MDC, không tự xóa value của caller; pattern trên **khôi phục previous value**.

Không tự động giả định MDC sẽ propagate sang `@Async`, `CompletableFuture`, Reactor hoặc executor threads. Cần `TaskDecorator`/context propagation mechanism phù hợp và integration test đúng execution path.

### 6.4. Không log credential

Tránh:

~~~java
log.info("Calling gateway with token={}", bearerToken);
log.error("Payment failed request={}", fullRequestDto, exception);
~~~

DTO `toString()`/exception message có thể chứa password, authorization header, customer name, account details hoặc payment data. Dùng allowlist safe fields:
- event name;
- non-sensitive synthetic/biz IDs theo policy;
- status/reason code;
- latency bucket, retry attempt;
- exception class/category;
- trace/correlation ID.

Nếu log exception cùng stacktrace, cần review error message/cause vì **exception itself** cũng có thể chứa secret. Negative test “không thấy token trong logger event của service” tốt, nhưng không chứng minh mọi gateway/framework log đều đã được redacted.

### 6.5. Chống log injection

Untrusted input có newline hoặc ANSI control characters có thể làm text log thành nhiều dòng giả:

~~~text
jobId=order_42
ERROR Admin login succeeded
~~~

Để giảm rủi ro:
- Validate/sanitize những identifiers được log.
- Ưu tiên structured logging/encoder escape đúng.
- Giới hạn độ dài untrusted values.
- Không dùng raw request body làm audit message.
- Test malicious newline/CRLF payload nếu threat model yêu cầu.

Trong lab, `JobLogService` chỉ nhận `jobId` bằng chữ/số/`_`/`-` và tối đa 64 ký tự.

## 7. Dự án Java 17 + Spring Boot 3.5.16: kiểm đúng log behavior

### 7.1. Kịch bản

Một service xử lý job đồng bộ có ba outcomes:
- `COMPLETED`: phát `INFO job_started` rồi `INFO job_completed`.
- `REJECTED`: phát `INFO job_started` rồi `WARN job_rejected`.
- Exception: phát `INFO job_started` rồi `ERROR job_failed` kèm `IllegalStateException`, sau đó rethrow.

Cả ba:
- Gắn `correlationId=jobId` vào MDC trong phạm vi xử lý.
- Khôi phục MDC cũ khi xong.
- Không log `credential` là một tham số nhạy cảm có chủ đích.
- Cho phép kiểm outcome **và** event log.

Ba lớp JUnit:
1. `OutputCaptureExamplesTest` chứng minh hoạt động `getOut/getErr/getAll` trên streams.
2. `LogbackEventAssertionsTest` dùng `ListAppender` với Spring-managed bean để assert level, message, MDC, Throwable và secrets.
3. `AsyncLogEventTest` dùng queue-backed test appender để đợi log từ một worker thread, tránh đọc list quá sớm.

Không cần Docker/Redis/broker/HTTP server. Logback là provider mặc định qua Spring Boot starter, không có dependency/version Log4j2 tùy ý trong main lab.

### 7.2. Cây file

~~~text
spring-boot-log-contract-lab/
├── pom.xml
├── src/main/
│   ├── java/com/example/logcontract/
│   │   ├── LogContractApplication.java
│   │   └── JobLogService.java
│   └── resources/
│       └── application.properties
└── src/test/java/com/example/logcontract/
    ├── OutputCaptureExamplesTest.java
    ├── LogbackEventAssertionsTest.java
    └── AsyncLogEventTest.java
~~~

### 7.3. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>

  <groupId>com.example</groupId>
  <artifactId>spring-boot-log-contract-lab</artifactId>
  <version>1.0.0</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
~~~

`spring-boot-starter` kéo `spring-boot-starter-logging`/Logback và SLF4J. `spring-boot-starter-test` cung cấp JUnit Jupiter, AssertJ và `OutputCaptureExtension`. Logback classes như `ListAppender` có sẵn trên test classpath. Nếu dự án thực dùng Log4j2 và đã exclude Logback, **không** thể cast logger sang `ch.qos.logback.classic.Logger`; dùng test appender của Log4j2 tương ứng.

Không thêm spring-boot-starter-web vì bài kiểm log của service thuần, không cần HTTP request hoặc embedded servlet container.

### 7.4. application.properties

`src/main/resources/application.properties`:

~~~properties
spring.application.name=log-contract-lab
spring.main.web-application-type=none

# Duy trì các event INFO/WARN/ERROR của service trong demo.
logging.level.com.example.logcontract=INFO

# Không đưa ANSI escape codes vào console text tests.
spring.output.ansi.enabled=never
~~~

Cấu hình này giúp output text dễ đọc. Nó không ép root logger DEBUG, không ghi credentials, không bật file appender riêng. `spring.main.web-application-type=none` giúp integration test khởi tạo context nhanh.

### 7.5. LogContractApplication.java

`src/main/java/com/example/logcontract/LogContractApplication.java`:

~~~java
package com.example.logcontract;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LogContractApplication {

    public static void main(String[] args) {
        SpringApplication.run(LogContractApplication.class, args);
    }
}
~~~

Không tự ghi test data trong main method, không expose log collector. Bài học tập trung observability behavior của một bean.

### 7.6. JobLogService.java

`src/main/java/com/example/logcontract/JobLogService.java`:

~~~java
package com.example.logcontract;

import java.util.Objects;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.stereotype.Service;

@Service
public class JobLogService {

    private static final Logger log =
            LoggerFactory.getLogger(JobLogService.class);

    public String execute(
            String jobId,
            String credential,
            boolean reject) {

        String safeId = checkedId(jobId);
        Objects.requireNonNull(credential, "credential");

        String previous = MDC.get("correlationId");
        MDC.put("correlationId", safeId);

        try {
            log.info("event=job_started jobId={}", safeId);

            if (reject) {
                log.warn(
                        "event=job_rejected jobId={} reason=invalid_input",
                        safeId);
                return "REJECTED";
            }

            // Demo: xử lý hai items, không có external side effect.
            log.info(
                    "event=job_completed jobId={} itemsProcessed={}",
                    safeId, 2);

            return "COMPLETED";
        }
        finally {
            restoreCorrelationId(previous);
        }
    }

    public void failUnexpectedly(
            String jobId,
            String credential) {

        String safeId = checkedId(jobId);
        Objects.requireNonNull(credential, "credential");

        String previous = MDC.get("correlationId");
        MDC.put("correlationId", safeId);

        try {
            log.info("event=job_started jobId={}", safeId);

            IllegalStateException failure =
                    new IllegalStateException(
                            "simulated dependency timeout");

            log.error(
                    "event=job_failed jobId={} category=dependency_timeout",
                    safeId,
                    failure);

            throw failure;
        }
        finally {
            restoreCorrelationId(previous);
        }
    }

    private static String checkedId(String jobId) {
        if (jobId == null
                || !jobId.matches("[A-Za-z0-9_-]{1,64}")) {
            throw new IllegalArgumentException(
                    "invalid job identifier");
        }
        return jobId;
    }

    private static void restoreCorrelationId(String previous) {
        if (previous == null) {
            MDC.remove("correlationId");
        }
        else {
            MDC.put("correlationId", previous);
        }
    }
}
~~~

### 7.7. Vì sao service được thiết kế như vậy?

**Event convention**:
- `event=job_started`, `event=job_completed`, `event=job_rejected`, `event=job_failed` là các machine-searchable markers.
- `jobId` là một synthetic safe ID trong ví dụ.
- `itemsProcessed=2` là số lượng được báo khi thành công.
- `reason=invalid_input` và `category=dependency_timeout` là stable reason codes.

**Outcome độc lập log**:
- `execute` trả `COMPLETED`/`REJECTED`.
- `failUnexpectedly` ném đúng exception.
- Test phải assert outcome/exception **và** log event.

**Credential redaction**:
- `credential` có mặt vì method giả lập một boundary có secret.
- Code cố tình **không đưa credential** vào SLF4J arguments, MDC hoặc exception message.
- Kiểm secret absence chỉ bao phủ các events của service trong test, không chứng minh mọi hệ thống logging đều an toàn.

**MDC**:
- Dùng `try/finally` để tránh leak khi method throw.
- Khôi phục previous value của caller thay vì luôn `remove`.
- Thực thi trên thread hiện tại; khi chuyển sang executor/`@Async`, phải propagate context đúng requirement.

**Log injection**:
- `checkedId` reject IDs có newline/CRLF hoặc ký tự ngoài whitelist.
- Không log ID trước khi validation.
- Đây là defensive sample, không thay domain-specific schema/PII handling.

**Throwable**:
- `log.error("... {}", safeId, failure)` truyền exception ở vị trí cuối, SLF4J/Logback ghi throwable metadata.
- Lab không dùng exception message chứa credential.
- Một log event ERROR vẫn không thay thế việc application propagate error đúng hợp đồng; method ném lại exception.

### 7.8. OutputCaptureExamplesTest.java

`src/test/java/com/example/logcontract/OutputCaptureExamplesTest.java`:

~~~java
package com.example.logcontract;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.boot.test.system.CapturedOutput;
import org.springframework.boot.test.system.OutputCaptureExtension;

import static org.assertj.core.api.Assertions.assertThat;

@ExtendWith(OutputCaptureExtension.class)
class OutputCaptureExamplesTest {

    @Test
    void capturesStdoutAndStderrSeparately(
            CapturedOutput output) {

        System.out.println("STDOUT_ONLY_MARKER_390");
        System.err.println("STDERR_ONLY_MARKER_390");

        assertThat(output.getOut())
                .contains("STDOUT_ONLY_MARKER_390")
                .doesNotContain("STDERR_ONLY_MARKER_390");

        assertThat(output.getErr())
                .contains("STDERR_ONLY_MARKER_390")
                .doesNotContain("STDOUT_ONLY_MARKER_390");

        assertThat(output.getAll())
                .contains("STDOUT_ONLY_MARKER_390")
                .contains("STDERR_ONLY_MARKER_390");

        // CapturedOutput implements CharSequence.
        assertThat(output)
                .contains("STDOUT_ONLY_MARKER_390");
    }

    @Test
    void checksStableTextWithoutTimestampAssumptions(
            CapturedOutput output) {

        System.out.println(
                "event=demo_started jobId=demo_390");
        System.out.println(
                "event=demo_completed jobId=demo_390");

        assertThat(output.getOut())
                .contains("event=demo_started jobId=demo_390")
                .contains("event=demo_completed jobId=demo_390")
                .doesNotContain(
                        "event=demo_failed jobId=demo_390");
    }
}
~~~

**Điều được chứng minh chính xác:**
- Extension capture hai system streams.
- `getOut`/`getErr` được phân biệt.
- `getAll` chứa cả hai outputs.
- Test không yêu cầu Spring context, Docker hay logging backend.
- Test không kiểm `INFO/WARN/ERROR` của Logback — đó là công việc của appender tests bên dưới.

Nếu bạn muốn kiểm **console-rendered text do SLF4J sinh ra**, có thể đặt `@ExtendWith(OutputCaptureExtension.class)` trên một `@SpringBootTest` class và trigger service, rồi assert `output.getAll()` chứa stable event marker. Với custom logging backend, phải bảo đảm ConsoleAppender thực sự ghi vào stream đang capture. Nếu không, dùng event appender như phần sau; đừng sửa business test cho “xanh” bằng cách `System.out.println` một message thay thế logger.

### 7.9. LogbackEventAssertionsTest.java

`src/test/java/com/example/logcontract/LogbackEventAssertionsTest.java`:

~~~java
package com.example.logcontract;

import java.util.stream.Collectors;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.read.ListAppender;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class LogbackEventAssertionsTest {

    @Autowired
    JobLogService service;

    private Logger serviceLogger;
    private ListAppender<ILoggingEvent> appender;

    @BeforeEach
    void attachAppender() {
        serviceLogger = (Logger) LoggerFactory.getLogger(
                JobLogService.class);

        appender = new ListAppender<>();
        appender.setContext(
                serviceLogger.getLoggerContext());
        appender.setName("TEST_JOB_EVENTS");
        appender.start();

        serviceLogger.addAppender(appender);
    }

    @AfterEach
    void detachAppender() {
        if (serviceLogger != null && appender != null) {
            serviceLogger.detachAppender(appender);
            appender.stop();
        }
    }

    private ILoggingEvent findEvent(String eventName) {
        return appender.list.stream()
                .filter(event -> event.getFormattedMessage()
                        .contains("event=" + eventName + " "))
                .findFirst()
                .orElseThrow(() ->
                        new AssertionError(
                                "missing event: " + eventName));
    }

    @Test
    void completionHasInfoLevelExactArgumentsAndMdc() {
        String jobId = "job_success_390";

        String result = service.execute(
                jobId, "secret_not_for_logs", false);

        assertThat(result).isEqualTo("COMPLETED");
        assertThat(appender.list).hasSize(2);

        ILoggingEvent completed =
                findEvent("job_completed");

        assertThat(completed.getLevel())
                .isEqualTo(Level.INFO);

        assertThat(completed.getLoggerName())
                .isEqualTo(JobLogService.class.getName());

        assertThat(completed.getMessage())
                .isEqualTo(
                        "event=job_completed jobId={} itemsProcessed={}");

        assertThat(completed.getArgumentArray())
                .containsExactly(jobId, 2);

        assertThat(completed.getFormattedMessage())
                .isEqualTo(
                        "event=job_completed jobId="
                                + jobId + " itemsProcessed=2");

        assertThat(completed.getMDCPropertyMap())
                .containsEntry("correlationId", jobId);

        assertThat(MDC.get("correlationId"))
                .isNull();
    }

    @Test
    void rejectedJobWarnsAndDoesNotReportCompletion() {
        String jobId = "job_rejected_390";

        String result = service.execute(
                jobId, "secret_not_for_logs", true);

        assertThat(result).isEqualTo("REJECTED");
        assertThat(appender.list).hasSize(2);

        ILoggingEvent rejected =
                findEvent("job_rejected");

        assertThat(rejected.getLevel())
                .isEqualTo(Level.WARN);

        assertThat(rejected.getFormattedMessage())
                .contains("jobId=" + jobId)
                .contains("reason=invalid_input");

        assertThat(rejected.getMDCPropertyMap())
                .containsEntry("correlationId", jobId);

        assertThat(appender.list)
                .noneMatch(event ->
                        event.getFormattedMessage()
                                .contains("event=job_completed "));
    }

    @Test
    void unexpectedFailureContainsErrorAndThrowable() {
        String jobId = "job_failed_390";

        assertThatThrownBy(() ->
                service.failUnexpectedly(
                        jobId, "secret_not_for_logs"))
                .isInstanceOf(IllegalStateException.class)
                .hasMessage("simulated dependency timeout");

        ILoggingEvent failed =
                findEvent("job_failed");

        assertThat(failed.getLevel())
                .isEqualTo(Level.ERROR);

        assertThat(failed.getFormattedMessage())
                .contains("jobId=" + jobId)
                .contains("category=dependency_timeout");

        assertThat(failed.getThrowableProxy())
                .isNotNull();

        assertThat(failed.getThrowableProxy()
                .getClassName())
                .isEqualTo(
                        "java.lang.IllegalStateException");

        assertThat(failed.getMDCPropertyMap())
                .containsEntry("correlationId", jobId);

        // finally phải chạy ngay cả khi throw.
        assertThat(MDC.get("correlationId"))
                .isNull();
    }

    @Test
    void credentialIsNotInServiceLogMessages() {
        String secret = "Bearer_SUPER_SECRET_390";

        service.execute("job_redaction_390", secret, false);

        String messages = appender.list.stream()
                .map(ILoggingEvent::getFormattedMessage)
                .collect(Collectors.joining("\n"));

        assertThat(messages)
                .contains("event=job_completed")
                .doesNotContain(secret);

        assertThat(appender.list)
                .allSatisfy(event ->
                        assertThat(event.getMDCPropertyMap())
                                .doesNotContainValue(secret));
    }

    @Test
    void methodRestoresExistingCallerMdcValue() {
        String original = MDC.get("correlationId");
        MDC.put("correlationId", "caller_390");

        try {
            service.execute(
                    "inner_job_390", "secret", false);

            assertThat(MDC.get("correlationId"))
                    .isEqualTo("caller_390");

            ILoggingEvent completed =
                    findEvent("job_completed");

            assertThat(completed.getMDCPropertyMap())
                    .containsEntry(
                            "correlationId", "inner_job_390");
        }
        finally {
            if (original == null) {
                MDC.remove("correlationId");
            }
            else {
                MDC.put("correlationId", original);
            }
        }
    }

    @Test
    void unsafeIdentifierIsRejectedBeforeAnyLog() {
        assertThatThrownBy(() ->
                service.execute(
                        "job_390\nFAKE_ERROR",
                        "secret", false))
                .isInstanceOf(
                        IllegalArgumentException.class)
                .hasMessage("invalid job identifier");

        assertThat(appender.list).isEmpty();
    }
}
~~~

### 7.10. Phân tích Logback appender test

**Test completion**:
- Assert business result `COMPLETED`.
- Event `job_completed` có `INFO`.
- Logger name đúng class service.
- Template và argument array đúng: `jobId` + `itemsProcessed=2`.
- Formatted message đúng, không cần phụ thuộc timestamp/thread/PID.
- MDC tại thời điểm log có `correlationId=jobId`.
- Sau khi method xong, thread caller không giữ MDC cũ.

**Test reject**:
- Business result `REJECTED`.
- Có `WARN job_rejected` với reason code.
- Không có `job_completed` trong events của service thuộc test.
- Không cần dựa vào output text của framework.

**Test error**:
- Method thực sự throw `IllegalStateException`.
- Có `ERROR job_failed` và `ThrowableProxy` đúng exception class.
- MDC tồn tại trong event dù method sau đó rethrow.
- Cleanup chạy trong `finally`.

**Test secret**:
- Raw credential không có trong rendered messages và MDC values của events captured.
- Đây là **negative regression test hữu ích nhưng giới hạn phạm vi**: không kiểm logger khác, stacktrace từ thư viện, file appender hay collector output. Nếu credential được in trong request DTO/HTTP client logs ở layer khác, phải test layer đó riêng.

**Test MDC restore**:
- Nếu caller đã có correlation ID, method không phá context của caller.
- Log event bên trong method có job-specific ID.
- Đây là contract mạnh hơn việc chỉ assert MDC null sau execution.

**Test log injection**:
- CRLF trong `jobId` bị reject trước khi phát event.
- Một ID không đúng schema không được in nguyên văn.
- Production còn cần escape/truncate user-provided messages ở những field khác.

**Isolation:** `@BeforeEach` attaches trên logger riêng; `@AfterEach` detaches ngay cả nếu test assertion fail. Mặc định JUnit Jupiter chạy các methods tuần tự; nếu project bật parallel execution, dùng `@ResourceLock`/test isolation để tránh hai tests sửa cùng logger global trong JVM.

### 7.11. AsyncLogEventTest.java

Một số job dispatch qua `ExecutorService`, `@Async` hoặc messaging listener và log trên thread khác. Kiểm event **trước khi worker hoàn tất** sẽ race. Để minh họa, class này chạy service trên một Java executor và dùng `QueueAppender` test-specific:

`src/test/java/com/example/logcontract/AsyncLogEventTest.java`:

~~~java
package com.example.logcontract;

import java.time.Duration;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;

import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class AsyncLogEventTest {

    @Autowired
    JobLogService service;

    static final class QueueAppender
            extends AppenderBase<ILoggingEvent> {

        private final BlockingQueue<ILoggingEvent> queue =
                new LinkedBlockingQueue<>();

        @Override
        protected void append(ILoggingEvent event) {
            // Snapshot MDC/arguments khi xử lý ở thread hiện tại.
            event.prepareForDeferredProcessing();
            queue.offer(event);
        }

        ILoggingEvent await(Duration timeout)
                throws InterruptedException {
            return queue.poll(
                    timeout.toMillis(),
                    TimeUnit.MILLISECONDS);
        }
    }

    @Test
    void logFromWorkerThreadIsObservedWithBoundedWait()
            throws Exception {

        Logger logger = (Logger) LoggerFactory.getLogger(
                JobLogService.class);

        QueueAppender appender = new QueueAppender();
        appender.setContext(logger.getLoggerContext());
        appender.setName("ASYNC_TEST_QUEUE");
        appender.start();
        logger.addAppender(appender);

        ExecutorService executor =
                Executors.newSingleThreadExecutor();

        try {
            Future<String> work = executor.submit(
                    () -> service.execute(
                            "async_390",
                            "secret",
                            false));

            // Wait for business completion; do not sleep.
            assertThat(work.get(
                    5, TimeUnit.SECONDS))
                    .isEqualTo("COMPLETED");

            ILoggingEvent first =
                    appender.await(Duration.ofSeconds(3));
            ILoggingEvent second =
                    appender.await(Duration.ofSeconds(3));

            assertThat(first).isNotNull();
            assertThat(second).isNotNull();

            assertThat(first.getFormattedMessage())
                    .contains("event=job_started ")
                    .contains("jobId=async_390");

            assertThat(second.getFormattedMessage())
                    .contains("event=job_completed ")
                    .contains("jobId=async_390");

            assertThat(second.getLevel())
                    .isEqualTo(Level.INFO);

            assertThat(second.getMDCPropertyMap())
                    .containsEntry(
                            "correlationId", "async_390");
        }
        finally {
            executor.shutdownNow();
            logger.detachAppender(appender);
            appender.stop();
        }
    }
}
~~~

### 7.12. Vì sao QueueAppender tốt hơn Thread.sleep?

- Worker được submit rồi `Future.get(timeout)` bảo đảm action đã trả hoặc lỗi/timeout.
- Appender tự capture events khi chúng được ghi; `BlockingQueue.poll(timeout)` chỉ chờ **event thực**.
- Không phụ thuộc vào máy CI chạy nhanh/chậm trong một fixed sleep.
- `prepareForDeferredProcessing()` giúp chụp phần deferred data như MDC trước khi thread phát log hoàn thành và dọn context.
- Test đọc event-level data, không phải chờ một console stream async flush theo hy vọng.
- `finally` đóng executor và tháo appender để không làm nhiễm tests khác.

**Caveat:** Class này minh họa work chạy trên Java `ExecutorService`, **chưa phải** kiểm `@Async` annotation và Spring TaskExecutor/TaskDecorator configuration. Nếu production dùng `@Async`, phải thêm integration test thật qua Spring proxy, cấu hình executor context propagation, xử lý `CompletableFuture`/`AsyncUncaughtExceptionHandler` và verify event tương ứng. Không tuyên bố executor sample đã chứng minh propagation ở mọi async framework.

### 7.13. Chạy project

Từ thư mục `spring-boot-log-contract-lab`:

~~~bash
mvn -q clean test

mvn -q -Dtest=OutputCaptureExamplesTest test
mvn -q -Dtest=LogbackEventAssertionsTest test
mvn -q -Dtest=AsyncLogEventTest test
~~~

Dự kiến JUnit methods:
- `OutputCaptureExamplesTest`: 2 methods.
- `LogbackEventAssertionsTest`: 6 methods.
- `AsyncLogEventTest`: 1 method.
- **Tổng cộng 9 methods**.

Khi thực thi thành công, Maven exit code bằng 0 và Surefire reports ở `target/surefire-reports`. Dòng console cụ thể của Spring Boot phụ thuộc môi trường, nhưng assertions ở lab không yêu cầu toàn bộ logger format hay timestamp cố định.

**Trạng thái QA của code mẫu:** API/imports/lifecycle đã được rà soát cho Java 17, Spring Boot 3.5, Logback, JUnit 5; **Maven/JUnit chưa được thực thi trong quá trình biên soạn**. Khi áp dụng, chạy `mvn clean test` trong dự án và xem test reports thay vì tự xem đây là kết quả PASS đã đo được.

### 7.14. Vì sao không dùng @SpringBootTest ở mọi class?

`OutputCaptureExamplesTest` chỉ kiểm streams bằng pure JUnit extension, không cần khởi tạo Spring context. Hai classes còn lại autowire service từ context thật để kiểm event emission của Spring-managed bean. Mỗi tầng có chi phí khác nhau; không kéo context lên chỉ để gọi `System.out.println`.

## 8. CapturedOutput khi kiểm SLF4J console logs

### 8.1. Ví dụ kết hợp trong Spring Boot

Khi app dùng console appender tương thích với capture:

~~~java
@SpringBootTest
@ExtendWith(OutputCaptureExtension.class)
class JobConsoleLogTest {

    @Autowired
    JobLogService service;

    @Test
    void successWritesContractMarker(
            CapturedOutput output) {

        String result = service.execute(
                "console_390", "synthetic_secret", false);

        assertThat(result).isEqualTo("COMPLETED");

        assertThat(output.getAll())
                .contains(
                        "event=job_completed jobId=console_390");
    }
}
~~~

Đây là **snippet mở rộng**, không phải file trong runnable lab. Nó cho thấy cách test **rendered console log** khi that's the requirement. Nếu custom appender/Log4j2/JUL không gửi event vào captured stream, test không nhìn thấy event; đó là vấn đề tầng logging configuration, không chứng minh service chưa gọi logger.

### 8.2. Phân biệt getOut và getErr cho level ERROR

Không có quy tắc phổ quát “`log.error` luôn ở `System.err`”. Logback ConsoleAppender mặc định có thể ghi cả INFO/WARN/ERROR vào stdout tùy cấu hình. Khi muốn kiểm **level ERROR**, dùng `ILoggingEvent.getLevel()`; đừng assert `output.getErr()` có ERROR rồi coi đó là logging contract nếu backend chưa thiết lập stderr routing rõ.

Ngược lại, một `System.err.println("ERROR")` là output trên stderr, nhưng **không** phải một SLF4J ERROR event với logger name, MDC hay Throwable.

### 8.3. Một snapshot không phải stream riêng của service

`CapturedOutput.getAll()` chứa mọi stdout/stderr được capture trong test lifecycle: logging của framework, test fixture, System.out trực tiếp, worker khác và có thể cả third-party code. Vì vậy:
- Dùng unique job ID.
- Filter đúng line/event marker.
- Tránh assert global log count.
- Không phụ thuộc full output equality.
- Không chạy song song những tests cùng sửa `System.out/err` nếu không có isolation.

## 9. Java Util Logging và Log4j2: các trường hợp cần cấu hình thêm

### 9.1. Java Util Logging (JUL)

Spring Boot `OutputCaptureExtension` docs lưu ý JUL có thể cần reset logging configuration để console output được capture ổn định:

~~~java
@AfterEach
void resetJulLogging() throws Exception {
    java.util.logging.LogManager
            .getLogManager()
            .readConfiguration();
}
~~~

Đây là **snippet dành cho dự án thực sự dùng JUL**, không thuộc main Logback lab. JUL `ConsoleHandler` có thể đã được khởi tạo và giữ stream cũ. Không thêm reset JUL tùy tiện vào mọi test Logback; reset/reconfigure logger global có thể gây tác dụng phụ tới các tests khác.

Nếu ứng dụng chạy qua Spring Boot Logback adapter cho JUL, xác định log route thực tế trước khi chọn fix.

### 9.2. Log4j2 ConsoleAppender follow=true

Theo Spring Boot Javadoc của OutputCaptureExtension, Log4j2 nên cấu hình console appender theo stream hiện hành bằng `follow="true"` để capture tin cậy:

~~~xml
<Appenders>
  <Console name="Console"
           target="SYSTEM_OUT"
           follow="true">
    <PatternLayout pattern="%d %-5p %c - %m%n"/>
  </Console>
</Appenders>
~~~

Đây là đoạn trong `log4j2-spring.xml`/Log4j2 config; cần cấu hình `Loggers` tham chiếu appender và dependency Log4j2 tương ứng. Đừng nhét XML này vào Logback `logback-spring.xml`; chúng là hai backend khác nhau.

Nếu dự án dùng Log4j2:
- Exclude `spring-boot-starter-logging`/Logback một cách đúng.
- Thêm `spring-boot-starter-log4j2`.
- Dùng appender/listener của Log4j2 để capture structured events.
- Chạy test riêng cho formatter/JSON output khi đó là contract.

### 9.3. Vì sao reset/reconfigure logging global có rủi ro?

LoggingSystem thường là process-global hoặc Spring ApplicationContext-level infrastructure. Nếu hai test classes chạy song song và một class thay logger level/appender/streams, class kia có thể thấy events bị lọc hoặc bắt nhầm. Dùng isolated test JVM, sequential execution, `@ResourceLock` hoặc test appender có scope chặt nếu project bật parallel.

## 10. Structured logging: kiểm JSON thay vì grep text khi cần

### 10.1. Spring Boot 3.5 hỗ trợ structured log formats

Spring Boot 3.5 có các format structured logging sẵn có như:
- **Elastic Common Schema (ECS)**;
- **Logstash JSON**;
- **Graylog Extended Log Format (GELF)**.

Ví dụ bật ECS cho console:

~~~properties
logging.structured.format.console=ecs
logging.structured.ecs.service.name=inventory-test
~~~

Đây là **cấu hình tùy chọn** khi kiểm structured JSON. Không bật nó đồng thời với các default-text assertions của project lab nếu không thay cách parse/assert; Boot logging config có thể là state global và context caching.

### 10.2. JSON là contract của field, không phải toàn bộ line

Với ECS, một line JSON có thể gồm:

~~~json
{
  "@timestamp": "2026-11-08T00:00:00Z",
  "log": {
    "level": "INFO",
    "logger": "com.example.logcontract.JobLogService"
  },
  "message": "event=job_completed jobId=job_390 itemsProcessed=2",
  "correlationId": "job_390",
  "service": {
    "name": "inventory-test"
  }
}
~~~

Đây là **shape minh họa**, không phải stdout được đo thực sự. Trường cụ thể như process/thread/ecs.version có thể thêm. Phần `@timestamp` chỉ là ví dụ; test không assert chính xác ngày giờ.

Spring Boot structured logging có thể đưa MDC values vào JSON output; field names có thể được tùy biến. Downstream collector có thể tiếp tục rename/drop fields, nên việc JSON local hợp lệ chưa chứng minh index schema sau ingestion.

### 10.3. Assertion đúng với Jackson

Khi đã bật structured JSON output trong một test profile/fork phù hợp, parse từng line thay vì so nguyên chuỗi:

~~~java
String line = output.getOut().lines()
        .filter(value ->
                value.contains("event=job_completed"))
        .findFirst()
        .orElseThrow();

JsonNode node = new ObjectMapper().readTree(line);

assertThat(node.path("log").path("level").asText())
        .isEqualTo("INFO");

assertThat(node.path("message").asText())
        .contains("jobId=job_390");

assertThat(node.path("correlationId").asText())
        .isEqualTo("job_390");
~~~

Đây là **snippet mở rộng**; cần Jackson dependencies/imports và `CapturedOutput output` được inject, không thuộc Maven lab tối giản. Với `spring-boot-starter-json` hoặc `jackson-databind` trong test scope mới có `ObjectMapper`; không giả định `spring-boot-starter` thuần luôn chứa Jackson.

Đừng parse cả `CapturedOutput.getAll()` thành một JSON document khi có nhiều log lines hoặc framework startup text. Filter event line, verify line là JSON và assert specific fields. Nếu `event` nằm trong structured key-value pairs riêng, parse field đó thay vì grep `message`.

### 10.4. SLF4J 2 fluent key-value pairs

Spring Boot 3.5 structured logging có thể nhận key/value do SLF4J fluent API cung cấp:

~~~java
log.atInfo()
        .addKeyValue("event", "job_completed")
        .addKeyValue("jobId", "job_390")
        .addKeyValue("itemsProcessed", 2)
        .log("Job completed");
~~~

Snippet ở method có `Logger log`. Trong structured logging, các key/value pairs có thể đi thành JSON fields; còn với default text formatter, không nhất thiết thấy chúng trong console message nếu pattern không render. Khi contract là fields, assert event key/value pairs hoặc JSON encoder output, **không** giả định `CapturedOutput.contains("event=job_completed")` sẽ thấy một fluent key/value chưa được formatter render.

### 10.5. Kiểm schema/backward compatibility

Nếu alert sử dụng `correlationId` và `event=job_failed`:
- Field bị rename sẽ làm query hỏng.
- Level đổi ERROR→INFO có thể làm alert không kích hoạt.
- JSON invalid sau logging config update sẽ làm ingestion fail.
- MDC bị drop khi async switching sẽ mất correlation.
- Secret/PII có thể lọt qua encoder tùy field allowlist.
- Timestamp parse/timezone theo collector có thể ảnh hưởng dashboard.

Tạo contract tests cho **những fields mà downstream thực sự phụ thuộc**. Không khóa mọi field của ECS mặc định vào snapshot test vì Boot patch version có thể thêm metadata hợp lệ.

## 11. MDC và async logging: những ranh giới phải kiểm

### 11.1. MDC thường gắn với thread

Trong servlet handler, MDC có thể được set bởi filter/interceptor/tracing instrumentation. Nếu code dùng `CompletableFuture.supplyAsync(...)` mà không truyền context, worker thread có thể không giữ correlation ID. Điều đó không phải do CapturedOutput mất log, mà do **context propagation**.

~~~text
request-thread: MDC correlationId=abc
   |
   +-- submit task to executor
                   |
                   v
            worker-thread
            MDC có thể rỗng
            (trừ khi được propagate)
~~~

### 11.2. TaskDecorator là một hướng tiếp cận

Trong Spring TaskExecutor, một `TaskDecorator` có thể chụp MDC map của caller trước khi submit và restore nó ở worker khi chạy. Cần dọn MDC cũ của pooled worker sau execution và tránh leak.

Ví dụ minh họa ý tưởng:

~~~java
public final class MdcTaskDecorator
        implements org.springframework.core.task.TaskDecorator {

    @Override
    public Runnable decorate(Runnable task) {
        var callerContext = MDC.getCopyOfContextMap();

        return () -> {
            var previous = MDC.getCopyOfContextMap();

            try {
                if (callerContext == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(callerContext);
                }
                task.run();
            }
            finally {
                if (previous == null) {
                    MDC.clear();
                }
                else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

Đây là **snippet mở rộng**; cần import `org.slf4j.MDC` và Spring TaskExecutor/TaskDecorator registration. Nó không nằm trong runnable lab. Với Micrometer context propagation, Reactor hoặc Java virtual threads, mechanism phù hợp có thể khác; phải test hệ thống thật.

### 11.3. Async Logback Appender cũng có queue

`AsyncAppender` trong Logback có thể enqueue events rồi write ra console/file sau. Test chỉ chờ business `CompletableFuture` có thể kết thúc **trước** khi console output xuất hiện. Khi cần:
- Test **application emitted log event**: attach test appender gần logger/queue phù hợp.
- Test **encoder/console delivery**: đợi/flush đúng logging pipeline với deadline.
- Test **collector ingestion**: query test collector/index sau ingestion với bounded wait.

Không dùng `Thread.sleep(3000)` rồi coi như đã chứng minh delivery.

### 11.4. Correlation ID không phải secret

Correlation ID thường là identifier phục vụ trace, nhưng có thể gián tiếp liên kết tới user/tenant. Không đưa raw email, phone, token hoặc password vào MDC để “dễ tìm log”. Với business IDs, tuân thủ data classification và retention policies.

### 11.5. Negative assertion trong async là khó

~~~java
assertThat(output.getAll())
        .doesNotContain("event=job_failed");
~~~

Nếu worker chưa hoàn tất, assertion có thể PASS dù lỗi sẽ được log sau 200 ms. Một negative assertion đáng tin cần **completion signal** hoặc observation window có semantics rõ. Với method đồng bộ của lab, return/exception là boundary phù hợp; với async, đợi `Future.get` và event queue; với external collector, đợi stabilization/ingestion watermark khi requirement quan trọng.

## 12. Assert log level, error và stack trace thế nào?

### 12.1. Level là field chứ không phải substring

Không làm:

~~~java
assertThat(output.getAll()).contains("ERROR");
~~~

“ERROR” có thể nằm trong payload, tên class hoặc startup line không liên quan. Logback event:

~~~java
assertThat(failedEvent.getLevel())
        .isEqualTo(Level.ERROR);
~~~

đúng hơn khi mục tiêu là `log.error` từ class cụ thể. Nếu contract là text console với `ERROR` field, parse line/formatter riêng.

### 12.2. ThrowableProxy khác raw Throwable

Logback `ILoggingEvent.getThrowableProxy()` là proxy metadata của exception cho logging layer. Không cần so sánh toàn stack trace (line numbers đổi theo refactor). Test:
- Exception class.
- Error category/reason code.
- Có/cách lược bỏ stack trace theo policy.
- Không có token/PII trong messages.

Nếu mục tiêu là stacktrace body exact layout của logging configuration, test encoder output chuyên biệt; không trộn với unit test business.

### 12.3. Một exception có thể có nhiều logs

Một failure có thể được log tại service, controller advice và retry handler; double logging tạo noise và sai alert count. Khi contract yêu cầu **một terminal failure event cho một operation**, test cần scope theo `eventId`/`jobId` và check số terminal events ở boundary có trách nhiệm.

Không khẳng định one-ERROR-per-request trên toàn JVM khi nhiều framework layers hoặc parallel requests có logs khác. Có thể chọn kiến trúc “log once at boundary, rethrow with context” để giảm duplicate noise.

### 12.4. Preserve throwable nguyên nhân

Khi catch:

~~~java
catch (RemoteServiceException ex) {
    log.error(
            "event=job_failed category=remote_dependency",
            ex);
    throw ex;
}
~~~

Snippet này cần định nghĩa `RemoteServiceException`. Exception parameter cuối giúp logger ghi throwable. Nếu viết `log.error("... {}", ex.getMessage())`, stack trace/type có thể không được attach. Nhưng cũng không log raw exception nếu nó chứa credentials; sanitize hoặc dùng structured error code theo security policy.

## 13. Test log volume và sampling

### 13.1. Không biến INFO thành spam

Một service xử lý 100.000 items/giây và log INFO mỗi item có thể tạo chi phí/latency, làm collector đầy và che terminal events. Nếu requirement là observability tổng hợp:
- Dùng metrics counter/histogram cho high-cardinality quantities phù hợp.
- Dùng trace sampling cho detailed workflows.
- Chỉ log structured terminal warnings/errors hoặc sampled successes.
- Có `eventId` và correlation để investigate.

### 13.2. Metrics khác logs

Nếu requirement là “job failure counter tăng”, test Micrometer `MeterRegistry`/`SimpleMeterRegistry` chứ không assert dòng “counter++”. Nếu requirement là OpenTelemetry span attribute, test tracer/exporter in-memory; logs chỉ là tín hiệu bổ sung.

### 13.3. Log sampling ảnh hưởng test expectations

Nếu logger ứng dụng sampling events, một test luôn đòi mỗi success có INFO log có thể mâu thuẫn design. Kiểm sampling policy ở tầng phù hợp hoặc tắt sampling **trong test config có chủ đích** và không suy tỷ lệ production từ một sample nhỏ.

### 13.4. Log ordering không có total order đa luồng

Trong một thread đồng bộ, events được gọi theo thứ tự code. Khi có hai workers, không assert `first global line job A, second global line job B` nếu scheduler không bảo đảm. Partition/trace theo correlation ID, assert order **trong từng operation** nếu requirement; hoặc kiểm set events bất kể thứ tự.

## 14. So sánh ba cách chụp log

| Công cụ | Có ưu điểm gì? | Nhược điểm/cạm bẫy | Chọn khi |
| --- | --- | --- | --- |
| `CapturedOutput` | Ít cấu hình, thuộc Spring Boot test, test stdout/stderr | Global streams, phụ thuộc console appender, dễ dính format/timing | Console text là contract |
| Logback `ListAppender` | Event-level assertions: level, logger, MDC, args, throwable | Tied to Logback, mutable list, cần attach/detach | Service log behavior là contract |
| Custom queue appender | Thread-safe bounded wait với async event | Thêm test utility, quản lý lifecycle | Background/async log needs |
| Log4j2 test appender | Event-level trong Log4j2 | Backend-specific imports/config | App dùng Log4j2 |
| Structured JSON capture | Kiểm contract machine-readable | Cần Boot encoder config, parser, line filtering | Collector queries depend on JSON schema |
| Test collector/OTLP sink | Chứng minh ingestion/delivery | Chậm, nhiều dependencies và retries | Logs/traces phải đến sink ngoài |
| Mockito verify(Logger) | Có thể kiểm method call nếu inject logger abstraction | Static final logger khó mock, không kiểm formatter/MDC/actual appenders | Chỉ một wrapper logger có DI contract rõ |

**Ưu tiên:** Nếu chỉ cần “log ERROR có category/id và throwable”, Logback event appender tốt hơn so full console string. Nếu cần “dòng JSON ra stdout hợp chuẩn ingest”, capture + JSON parser. Nếu log không thuộc contract, **đừng bắt log để test behavior khác**.

## 15. Các anti-pattern làm test logging thiếu giá trị

### 15.1. Assert raw full log line

Timestamp, PID, thread và ANSI change làm test fail qua patch upgrades. Chỉ assert stable fields, level, event IDs.

### 15.2. Assert một từ quá chung

`contains("error")` có thể match log framework/fixture khác. Dùng event marker + unique correlation ID hoặc appender theo logger.

### 15.3. Chờ async bằng sleep

Log có thể chưa phát sau 1 giây hoặc đã xuất ở 10 ms. Dùng Future/BlockingQueue/poll timeout.

### 15.4. Attach appender vào root logger và không dọn

Nhiễm events toàn JVM, memory leak, duplicate capture giữa tests. Attach vào logger hẹp và detach trong finally/@AfterEach.

### 15.5. Thay logger level global không restore

Các tests chạy sau có thể thấy INFO bị filter hoặc DEBUG xuất hiện thêm. Không thay root logger tùy tiện. Nếu thay để test policy, save previous level và restore sau test; hạn chế parallel.

### 15.6. Dùng getErr để chứng minh ERROR

ERROR event có thể ghi ra stdout. Kiểm `getLevel()` từ event, không suy từ destination stream.

### 15.7. Unit test verify mock logger mà gọi là log integration

Mockito verify chỉ chứng minh gọi method của một mock; không chứng minh event đã qua SLF4J/Logback/formatting. Có thể hợp lệ khi logger wrapper là dependency explicitly injected, nhưng ghi đúng phạm vi.

### 15.8. Chỉ assert log khi cần database side effect

“Saved order” có thể được ghi trước transaction rollback. Query data thật, logs chỉ là diagnostic.

### 15.9. Sử dụng @SpringBootTest cho println đơn giản

Tốn thời gian context startup. Plain JUnit + OutputCaptureExtension đủ cho stream capture.

### 15.10. Gọi @SpringBootTest là bằng chứng capture startup logs

Context có thể được cache; startup chỉ một lần. Test startup event cần test process/context lifecycle phù hợp.

### 15.11. OutputCapture dùng với custom file-only appender

CapturedOutput không nhìn thấy file logs nếu không đi qua System.out/err. Dùng appender/file-sink/collector test tương ứng.

### 15.12. Logback ListAppender đọc khi worker chưa xong

Một mutable list không tự là await condition. Dùng Future/queue latching; đọc sau completion hoặc custom thread-safe appender.

### 15.13. Quên MDC cleanup

Thread pool reuse có thể leak user/correlation context. Có test old-MDC restoration và exception path; dùng try/finally.

### 15.14. Structured JSON test so sánh nguyên chuỗi

Metadata/time/order fields đổi hợp lệ sẽ làm test brittle. Parse JSON và assert schema-required fields.

### 15.15. Test redaction chỉ trên một method rồi tuyên bố toàn hệ thống an toàn

Exception, access log, HTTP client debug, SQL bind logs và collector có thể vẫn chứa secrets. Chọn threat model, các layer cần test và scan riêng.

### 15.16. Log trực tiếp toàn DTO hoặc Authorization header

Dễ lộ PII/tokens, vi phạm privacy/security. Dùng allowlist event fields và log-sanitization test.

### 15.17. Xem log là durable audit event

Logs có thể bị drop/sampled/retained ngắn. Nếu cần legally durable audit trail, dùng audit data store/outbox/retention/access controls và test readback.

### 15.18. Đếm events trên toàn JVM

Framework và concurrent tests thêm logs, gây false positive/false negative. Lọc logger + event ID/test run ID.

### 15.19. Không xử lý JUL/Log4j2 stream binding

ConsoleHandler/Appender có thể giữ stream cũ. Với JUL reset theo docs; Log4j2 ConsoleAppender `follow=true`. Không áp config của backend này sang backend khác.

### 15.20. Bật parallel test trong khi redirect System streams toàn cục

Mỗi test có thể thấy output của test khác hoặc làm stream restore sai. Dùng JUnit resource locks/sequential class hoặc fork isolation; không giả định OutputCapture tự tách stream theo thread.

## 16. Chẩn đoán khi CapturedOutput trống hoặc assertions thất bại

| Hiện tượng | Nguyên nhân khả dĩ | Cách kiểm |
| --- | --- | --- |
| `getOut()` trống khi log.info | Logger level/filter chặn | Kiểm INFO enabled/logger config |
| `getErr()` trống khi log.error | Console appender ghi stdout | Kiểm event level qua appender |
| Event có trong ListAppender nhưng CapturedOutput trống | Appender file/stream binding/capture lifecycle | Kiểm backend, console config, initialization |
| JUL logging không được capture | ConsoleHandler giữ System.err cũ | Reset JUL theo OutputCaptureExtension docs |
| Log4j2 logging không được capture | ConsoleAppender không follow stream | `follow=true` |
| @SpringBootTest test không thấy startup message | Context cached/created trước capture | Chạy dedicated startup test/process |
| ListAppender không thấy event | Attach sai logger/class hoặc level filter | Kiểm logger hierarchy, exact class, filter |
| ListAppender thấy quá nhiều events | Attach root/shared logger | Attach service logger hẹp |
| INFO event có nhưng test fail vì format | Exact line assertion quá brittle | Assert event fields hoặc stable substring |
| MDC trong event rỗng | Chưa set hoặc mất qua async thread | Kiểm MDC scope/context propagation |
| MDC còn trên thread sau method | Không cleanup | Try/finally + restore previous |
| Async test thỉnh thoảng rỗng | Assert trước worker/event completion | Future.get + BlockingQueue await |
| Test pass dù credential bị leak nơi khác | Chỉ capture một logger/sink | Mở rộng log sources và redaction validation |
| JSON parse fail | Text logs/ANSI/startup lines lẫn JSON | Isolate profile/fork, filter JSON line |
| Test khác fail sau log test | Appender/level/global stream không được restore | @AfterEach/finally, avoid parallel |
| “job_completed” xuất hiện khi thực tế fail | App log quá sớm trước commit | Di chuyển terminal event sau confirmation; assert business state |
| Error event bị duplicate | Multiple layers log cùng exception | Define log-once boundary và test correlation |
| Maven test xanh nhưng logs sai | Chưa kiểm log behavior | Add contract-specific assertions |
| Collector không nhận event dù console test pass | Shipper/transport/ingest failure | Test sink delivery/index query riêng |

### 16.1. Debug theo thứ tự

1. Log nào là requirement? Event name/level/fields/formatter/collector?
2. Service thật có vào nhánh log không? Assert business outcome.
3. Logging backend là Logback, Log4j2, JUL hay adapter?
4. Logger/level/filter có cho phép event phát ra không?
5. Nếu dùng CapturedOutput, appender có ghi đúng System.out/err không?
6. Nếu dùng ListAppender, đã attach đúng logger **trước** action chưa?
7. Test có chạy async không? Đã đợi completion đúng cách chưa?
8. Test có chạy parallel/global stream modification không?
9. MDC có set và restore đúng không?
10. Với structured output, JSON có field/encoding mong đợi không?
11. Với collector, test đã quan sát sink thực hay chỉ console?
12. Có log secret, PII hoặc error payload nhạy cảm không?

## 17. Bài tập thực hành

1. Chạy `OutputCaptureExamplesTest` và phân biệt `getOut`, `getErr`, `getAll`.
2. Thêm một `System.err.println` và kiểm nó không tự tạo Logback `Level.ERROR`.
3. Viết CapturedOutput test đối với console log INFO khi dùng Spring Boot default Logback; giải thích những điều kiện khiến test trống.
4. Thay toàn bộ log-line equality bằng assertions trên event name/job ID.
5. Attach `ListAppender` vào logger của `JobLogService`; kiểm level và message template.
6. Phân biệt `getMessage()` với `getFormattedMessage()` và `getArgumentArray()`.
7. Trong completion branch, bỏ `jobId` khỏi logger format; xem regression assertion nào fail.
8. Đổi level của job rejection từ WARN sang INFO; kiểm test level bắt sai.
9. Giả lập exception và xác nhận ERROR event có `ThrowableProxy` đúng type.
10. Bỏ MDC cleanup trong một nhánh thử nghiệm; kiểm test restore bắt lỗi.
11. Dùng caller MDC có sẵn, verify service khôi phục chính xác value trước call.
12. Thêm correlationId vào hai log events nhưng tách sang executor thread; kiểm propagation.
13. Dùng queue appender để đợi event từ worker thread mà không sleep.
14. Thử đọc ListAppender ngay sau submit nhưng trước Future.get; giải thích race.
15. Bật JUnit parallel cho hai test chung logger để thấy nguy cơ nhiễm state; sau đó thêm resource isolation.
16. Thêm check không có token synthetic trong formatted messages/MDC/exception.
17. Tạo jobId có newline/CRLF; verify input bị reject trước khi log.
18. Bật `logging.structured.format.console=ecs` trong test profile/process riêng, parse JSON với Jackson.
19. Kiểm ECS `log.level`, `message`, `correlationId`, nhưng không assert exact timestamp.
20. Dùng SLF4J fluent `addKeyValue` và kiểm JSON field eventName thay vì grep string.
21. Đổi sang Log4j2 test fixture, cấu hình ConsoleAppender `follow=true` và chạy OutputCapture.
22. Dùng JUL ConsoleHandler, thử reset configuration sau test để capture ổn định.
23. Tạo log-once policy: exception ở service và controller advice không tạo hai terminal events cho cùng jobId.
24. Thay logging success INFO bằng sampling, xác định test nào phải đổi theo contract.
25. Viết collector integration test: phát log, await ingest, query index theo correlation ID.
26. Dùng Micrometer `SimpleMeterRegistry` để test failure metric riêng, không suy metric từ log.
27. Thiết kế durable audit trail qua database/outbox, phân biệt với console log capture.
28. Viết test verify secret redaction trên HTTP client/access log khi authorization header có mặt.
29. Xây checklist log retention, sampling, structured schema và correlation ID cho on-call dashboard.
30. Review một test chỉ assert “ERROR” trên stdout; refactor thành level + logger + reason code + outcome assertions.

## 18. Checklist trước khi merge

- [ ] Log thực sự là hành vi quan sát theo requirement, không chỉ implementation detail?
- [ ] Test vẫn assert business outcome/side effect/exception riêng?
- [ ] Chọn đúng tầng: system streams, Logback event, JSON encoder hay collector?
- [ ] `OutputCaptureExtension` đăng ký ở JUnit5 class và `CapturedOutput` inject đúng?
- [ ] Phân biệt `getOut`, `getErr`, `getAll`?
- [ ] Không coi getErr là equivalent của ERROR level?
- [ ] ConsoleAppender/backend thực sự ghi vào stream được capture?
- [ ] Test không phụ thuộc full timestamp/PID/thread/ANSI format?
- [ ] Có stable event name và unique jobId/correlationId?
- [ ] Assertions gắn fields đúng **cùng một event** nếu contract cần?
- [ ] Appender attach đúng logger và trước hành động?
- [ ] Appender detach/stop sau test, kể cả failure?
- [ ] Không chỉnh global root logger level mà quên restore?
- [ ] Nếu dùng ListAppender với async, có completion synchronization?
- [ ] Có bounded queue/future await thay fixed sleep?
- [ ] MDC set/propagate/restore đúng, không leak qua thread pool?
- [ ] Exception event có đúng level, reason/category, throwable?
- [ ] Success/rejection/failure branches không phát terminal event sai?
- [ ] Đã kiểm secrets/PII không có trong log surfaces thuộc scope?
- [ ] Input untrusted có được sanitize/escape để chống CRLF injection?
- [ ] Nếu structured JSON, parse fields thay vì so raw line?
- [ ] JSON field names/version theo downstream contract?
- [ ] JUL/Log4j2 console capture có cấu hình backend phù hợp?
- [ ] Test không dựa vào startup logs bị Spring TestContext cache?
- [ ] Parallel JUnit classes có isolation cho System streams/shared logger?
- [ ] Log sampling/retention/ingestion được test ở đúng tầng khi cần?
- [ ] Không coi console log là durable audit/queue event?
- [ ] Maven/JUnit reports thực sự chạy và có exit code thành công?
- [ ] Không in dữ liệu thật của người dùng/credentials trong fixtures?
- [ ] Các assertions đủ cụ thể nhưng không brittle trước đổi formatter hợp lệ?

**Kết luận:** Khi log là hợp đồng observability, kiểm nó trực tiếp với công cụ đúng ranh giới. `OutputCaptureExtension` và `CapturedOutput` hữu ích cho văn bản `System.out/err` hoặc console-rendered logs; Logback `ListAppender` tốt hơn khi cần kiểm level, template, arguments, MDC và throwable; queue-based appender hỗ trợ log bất đồng bộ có bounded wait. Hãy tránh snapshot toàn bộ log, tránh dùng log thay business outcome, quản lý global streams/logger state cẩn thận và kiểm structured JSON hoặc collector khi thực sự cần. Một bài kiểm thử logging có giá trị nhất khi chỉ thất bại vì **hợp đồng quan sát bị vi phạm**, không vì timestamp, thread hay console formatter thay đổi.

## 19. Tài liệu chính thức và tham khảo

- Spring Boot 3.5 — Test Utilities / OutputCaptureExtension: https://docs.spring.io/spring-boot/3.5/reference/testing/test-utilities.html
- Spring Boot 3.5 — CapturedOutput API (getOut/getErr/getAll): https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/system/CapturedOutput.html
- Spring Boot 3.5 — OutputCaptureExtension API: https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/system/OutputCaptureExtension.html
- Spring Boot 3.5 — Logging, Logback defaults, MDC and structured formats: https://docs.spring.io/spring-boot/3.5/reference/features/logging.html
- Spring Boot 3.5 — Logging How-to, Log4j2 configuration: https://docs.spring.io/spring-boot/3.5/how-to/logging.html
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Observability: https://docs.spring.io/spring-boot/3.5/reference/actuator/observability.html
- SLF4J — User manual (logger, MDC, fluent API): https://www.slf4j.org/manual.html
- Logback — Appenders manual: https://logback.qos.ch/manual/appenders.html
- Logback — MDC manual: https://logback.qos.ch/manual/mdc.html
- Logback — ILoggingEvent API: https://logback.qos.ch/apidocs/ch.qos.logback.classic/ch/qos/logback/classic/spi/ILoggingEvent.html
- Logback — ListAppender API: https://logback.qos.ch/apidocs/ch.qos.logback.core/ch/qos/logback/core/read/ListAppender.html
- JUnit Jupiter 5 — Extension Model: https://junit.org/junit5/docs/current/user-guide/#extensions
- JUnit Jupiter 5 — Parallel Execution and @ResourceLock: https://junit.org/junit5/docs/current/user-guide/#writing-tests-parallel-execution
