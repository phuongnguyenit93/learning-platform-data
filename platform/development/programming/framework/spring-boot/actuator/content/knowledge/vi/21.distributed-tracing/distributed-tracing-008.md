# Liên kết log với traceId, spanId và MDC

Khi một thao tác đi qua nhiều dịch vụ, dòng log “xử lý thất bại” chỉ cho biết điều gì vừa xảy ra tại một nơi. Muốn tìm toàn bộ đường đi của thao tác đó, ta cần một định danh chung. Muốn biết dòng log thuộc bước xử lý nào trên đường đi ấy, ta cần thêm định danh của bước. Trong ứng dụng Spring Boot có Micrometer Tracing, `traceId` và `spanId` cung cấp hai mối liên kết này; MDC giúp hệ thống ghi log đưa chúng vào từng dòng mà không phải truyền hai tham số qua mọi phương thức.

Bài dùng Spring Boot 3.3.x, Java 21, SLF4J 2 và Logback. Trọng tâm là hiểu ngữ cảnh tại thời điểm ghi log, đọc đúng ID và giữ ngữ cảnh khi chuyển luồng. Phần thí nghiệm MDC độc lập cũng dùng được với Java 17 trở lên.

## 1. Hiểu các thành phần trước khi cấu hình

| Thành phần | Ý nghĩa | Câu hỏi nó giúp trả lời |
| --- | --- | --- |
| Trace | Đường đi của một thao tác được theo dõi, có thể qua nhiều dịch vụ | Những bước nào cùng thuộc một lần xử lý? |
| `traceId` | Định danh của trace | Cần tìm những log nào để dựng lại đường đi đó? |
| Span | Một đơn vị công việc được đo trong trace, có thể có quan hệ cha–con | Bước cụ thể nào đang được thực hiện? |
| `spanId` | Định danh của một span | Dòng log này thuộc span nào? |
| Ngữ cảnh trace (trace context) | Thông tin mà thư viện truy vết dùng để xác định trace/span hiện hành và truyền quan hệ giữa các bước | Công việc tiếp theo sẽ nối vào đâu? |
| MDC, viết tắt của Mapped Diagnostic Context | Tập cặp khóa–giá trị phục vụ ghi log; với Logback, dữ liệu gắn với luồng hiện tại | Khi ghi log ở đây, có những dữ liệu chẩn đoán nào để in kèm? |

Các span trong cùng trace dùng chung `traceId`; mỗi span có `spanId` riêng trong trace đó. Xem [khái niệm trace và span của OpenTelemetry](https://opentelemetry.io/docs/concepts/signals/traces/).

Điểm dễ nhầm: MDC chỉ là nơi hệ thống ghi log đọc dữ liệu. Gán một chuỗi vào khóa `traceId` không tạo ra trace thật. Tương tự, gán `spanId` không bắt đầu phép đo, không ghi quan hệ cha–con và không gửi span đến hệ thống lưu trace.

Một mã nghiệp vụ như `orderId`, hoặc mã yêu cầu do ứng dụng quy định như `requestId`, cũng không tự trở thành `traceId`. Chúng có thể được ghi thêm để tìm kiếm theo các hướng khác nhau.

### Đọc một ví dụ

Giả sử dịch vụ đơn hàng nhận yêu cầu, rồi gọi dịch vụ kho. Đây là log minh họa; các ID được chọn để dễ theo dõi:

```text
service=orders    trace=0123456789abcdef0123456789abcdef span=1111111111111111 received
service=orders    trace=0123456789abcdef0123456789abcdef span=2222222222222222 checking-stock
service=inventory trace=0123456789abcdef0123456789abcdef span=3333333333333333 stock-found
service=orders    trace=0123456789abcdef0123456789abcdef span=1111111111111111 completed
```

Bốn dòng cùng `traceId` nên có thể tìm theo một lần xử lý. Các `spanId` khác nhau cho thấy những bước khác nhau. Dòng cuối quay về span ban đầu vì phạm vi thực thi của bước gọi kho đã kết thúc. Không được suy ra quan hệ cha–con chỉ bằng cách nhìn giá trị số của ID; quan hệ đó nằm trong dữ liệu span.

## 2. Vì sao logger biết trace hiện hành?

Một luồng xử lý đồng bộ điển hình có các bước:

```text
Nhận yêu cầu HTTP
  → thư viện trích xuất ngữ cảnh truyền đến hoặc tạo trace mới
  → thiết lập span hiện hành trong một phạm vi thực thi
  → tích hợp truy vết đưa traceId/spanId tương ứng vào MDC
  → logger tạo sự kiện log
  → mẫu Logback đọc MDC và in các ID
  → đóng phạm vi: khôi phục ngữ cảnh trước đó
```

“Phạm vi” (scope) là khoảng thực thi mà một span được coi là hiện hành. Bắt đầu span và đặt span vào scope là hai thao tác có liên quan nhưng khác nhau. Một span đã được tạo chưa có nghĩa mọi log sau đó đều thuộc span ấy.

Micrometer cung cấp `Tracer.SpanInScope` để quản lý phạm vi. Khi đóng scope của span con, ngữ cảnh cha được khôi phục; khi kết thúc toàn bộ yêu cầu, thư viện phải dọn hoặc khôi phục ngữ cảnh tương ứng. Tham khảo [API quản lý span và scope của Micrometer](https://docs.micrometer.io/tracing/reference/api.html).

Với Logback, MDC không phải bản đồ dùng chung cho cả ứng dụng. Hai luồng có thể cùng dùng khóa `traceId` nhưng giữ giá trị khác nhau. Tuy nhiên, một luồng trong nhóm luồng sẽ được dùng cho nhiều công việc nối tiếp. Nếu mã tự đưa dữ liệu vào MDC mà không khôi phục đúng, công việc sau có thể nhận nhầm dữ liệu của công việc trước. [Tài liệu MDC của Logback](https://logback.qos.ch/manual/mdc.html) giải thích cơ chế theo luồng và việc luồng con không tự nhận bản sao MDC của luồng cha.

Có ba việc cần phân biệt:

- **Liên kết log:** đưa ID vào log để tìm kiếm.
- **Truyền ngữ cảnh:** mang ngữ cảnh qua lời gọi mạng hoặc chuyển luồng để bước sau tiếp nối đúng trace.
- **Xuất trace:** gửi dữ liệu span đến Zipkin hoặc một hệ thống thu thập trace.

Thành công ở một việc chưa chứng minh hai việc còn lại hoạt động.

## 3. Quan sát trực tiếp trong Spring Boot 3.3.x

### 3.1. Chuẩn bị một ứng dụng thực hành

Trong một dự án Spring Boot 3.3.x độc lập đã có Gradle Wrapper, Java 21 và cơ chế quản lý phiên bản phụ thuộc của Spring Boot, thêm các phụ thuộc sau. Đây là đoạn bổ sung vào `build.gradle`, không phải toàn bộ tệp build:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave'
    implementation 'io.zipkin.reporter2:zipkin-reporter-brave'
}
```

Ví dụ chọn Brave làm thư viện truy vết và Zipkin làm nơi nhận span. Dùng một bridge phù hợp, để Spring Boot quản lý các phiên bản tương thích. Starter Actuator một mình chưa cung cấp đầy đủ thư viện truy vết cho ví dụ này. Không thêm Spring Cloud Sleuth chỉ để lấy ID trong ứng dụng Boot 3.

Cấu hình thực hành trong `src/main/resources/application.yml`:

```yaml
spring:
  application:
    name: log-correlation-demo

management:
  tracing:
    sampling:
      probability: 1.0
  zipkin:
    tracing:
      endpoint: http://localhost:9411/api/v2/spans

logging:
  include-application-name: false
  pattern:
    correlation: "[${spring.application.name:},%X{traceId:-},%X{spanId:-}] "
```

Chạy Zipkin tại địa chỉ trên nếu muốn xem cây span. `probability: 1.0` phục vụ quan sát trong phòng thực hành; việc chọn mẫu cho hệ thống thật phụ thuộc tải và nhu cầu vận hành. Không cần mở thêm một endpoint Actuator để MDC xuất hiện.

Spring Boot 3.3 tích hợp các ID này vào mẫu log mặc định khi dùng Micrometer Tracing. `logging.pattern.correlation` dùng để tùy chỉnh phần hiển thị; khoảng trắng cuối chuỗi giúp tách nó khỏi phần logger tiếp theo. Các phụ thuộc và cấu hình liên quan được mô tả trong [tài liệu tracing của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

### 3.2. Tạo span con và theo dõi log trước–trong–sau

Dùng lớp ứng dụng hoàn chỉnh sau trong dự án thực hành, tại `src/main/java/demo/LogCorrelationApplication.java`:

```java
package demo;

import java.util.Map;

import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LogCorrelationApplication {
    private static final Logger log =
            LoggerFactory.getLogger(LogCorrelationApplication.class);

    private final Tracer tracer;

    public LogCorrelationApplication(Tracer tracer) {
        this.tracer = tracer;
    }

    public static void main(String[] args) {
        SpringApplication.run(LogCorrelationApplication.class, args);
    }

    @GetMapping("/demo/log-correlation")
    public Map<String, String> demonstrate() {
        log.info("received");

        Span child = tracer.nextSpan().name("prepare-result").start();
        try (Tracer.SpanInScope scope = tracer.withSpan(child)) {
            log.info("preparing");
        } catch (RuntimeException ex) {
            child.error(ex);
            throw ex;
        } finally {
            child.end();
        }

        log.info("completed");
        Span current = tracer.currentSpan();
        if (current == null) {
            return Map.of("traceId", "none", "spanId", "none");
        }
        return Map.of(
                "traceId", current.context().traceId(),
                "spanId", current.context().spanId());
    }
}
```

Khởi động bằng `./gradlew bootRun` trên Linux/macOS hoặc `.\gradlew.bat bootRun` trên PowerShell. Từ cửa sổ lệnh khác, gọi:

```bash
curl http://localhost:8080/demo/log-correlation
```

Trong Windows, có thể dùng `curl.exe` để gọi đúng chương trình curl.

Khi tracing của HTTP server đang hoạt động, ba thông điệp ứng dụng có quan hệ:

```text
received   → trace T, span P
preparing  → trace T, span C
completed  → trace T, span P
```

Đây là mô tả quan hệ, không phải stdout cố định: ID, thời gian, luồng và các dòng khởi động thay đổi theo lần chạy. JSON trả về chứa ID của span HTTP hiện hành tại thời điểm cuối phương thức. Việc trả ID chỉ phục vụ quan sát trong ví dụ này.

Trong đoạn mã:

1. HTTP instrumentation thiết lập span cha trước khi vào controller.
2. `nextSpan()` dùng ngữ cảnh hiện hành để tạo span con; `start()` bắt đầu span đó.
3. `withSpan(child)` làm span con hiện hành trong khối `try`.
4. Đóng `SpanInScope` khôi phục span cha trước dòng `completed`.
5. `child.end()` kết thúc span do mã này tạo. Không kết thúc span HTTP do thư viện quản lý.

Đặt log bên ngoài scope của span con rồi mong nó có `spanId` của span con là sai về phạm vi thực thi. Cũng không nên tự `MDC.put("traceId", ...)` hoặc `MDC.put("spanId", ...)` để “sửa” ví dụ: như vậy log có thể hiển thị ID khác với tracer thật.

### 3.3. Hiểu cú pháp mẫu log

Trong Logback, `%X{traceId}` đọc khóa `traceId` từ MDC của sự kiện log. `%X{traceId:-}` cho phần thay thế rỗng nếu thiếu khóa; `%X{traceId:-none}` dùng chữ `none` khi thiếu.

Mẫu chỉ đọc giá trị đã có, không sinh ID. Nếu ứng dụng dùng `logback-spring.xml` riêng và mẫu console/file không chứa phần correlation hoặc `%X{...}`, thay đổi thuộc tính trên chưa chắc tác động đến mẫu đó. Hãy kiểm tra appender thực sự nhận sự kiện. Ví dụ phần mẫu trong cấu hình Logback tùy chỉnh có thể là:

```xml
<pattern>%d{HH:mm:ss.SSS} [%thread] %-5level trace=%X{traceId:-none} span=%X{spanId:-none} %logger{36} - %msg%n</pattern>
```

Đây chỉ là phần tử `pattern` bên trong encoder, không phải tệp cấu hình Logback hoàn chỉnh. Khi xuất log JSON, cần cấu hình encoder hỗ trợ MDC để ghi thành trường riêng; mẫu console dạng văn bản không tự biến thành cấu hình JSON.

## 4. Thí nghiệm MDC độc lập: dữ liệu hiển thị không phải trace thật

Thí nghiệm sau chủ động điền các chuỗi ID cố định để cô lập cơ chế MDC. Nó không dùng Micrometer, không tạo span thật và không truyền HTTP. Trong ứng dụng có tracing, hãy để tích hợp truy vết quản lý hai khóa này như ví dụ ở phần 3.

Chuẩn bị một thư mục thực hành có `MdcDemo.java` và thư mục `lib/` chứa ba JAR tương thích: `slf4j-api`, `logback-classic`, `logback-core`. Một bộ dùng cho thí nghiệm là SLF4J `2.0.13`, Logback Classic/Core `1.5.6`; đây là bộ phiên bản để tái lập ví dụ, không phải chỉ dẫn chọn phiên bản mới nhất. Chỉ đặt một bộ thư viện ghi log trong `lib/`.

Chương trình cấu hình Logback ngay trong mã để bỏ phần thời gian và tạo đầu ra xác định:

```java
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.LoggerContext;
import ch.qos.logback.classic.encoder.PatternLayoutEncoder;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.ConsoleAppender;

public class MdcDemo {
    private static final Logger log = LoggerFactory.getLogger(MdcDemo.class);

    public static void main(String[] args) throws Exception {
        configureLogging();
        MDC.clear();
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            MDC.put("traceId", "0123456789abcdef0123456789abcdef");
            MDC.put("spanId", "1111111111111111");
            log.info("parent");

            String previousSpan = MDC.get("spanId");
            try {
                MDC.put("spanId", "2222222222222222");
                log.info("child");
            } finally {
                MDC.put("spanId", previousSpan);
            }
            log.info("parent-again");

            pool.submit(() -> log.info("worker-without-copy")).get();

            Map<String, String> captured = MDC.getCopyOfContextMap();
            pool.submit(() -> {
                Map<String, String> previous = MDC.getCopyOfContextMap();
                try {
                    restore(captured);
                    log.info("worker-with-copy");
                } finally {
                    restore(previous);
                }
            }).get();

            pool.submit(() -> log.info("worker-after-cleanup")).get();
        } finally {
            MDC.clear();
            pool.shutdown();
        }
        log.info("outside");
    }

    private static void restore(Map<String, String> values) {
        if (values == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(values);
        }
    }

    private static void configureLogging() {
        LoggerContext context = (LoggerContext) LoggerFactory.getILoggerFactory();
        context.reset();

        PatternLayoutEncoder encoder = new PatternLayoutEncoder();
        encoder.setContext(context);
        encoder.setPattern("%msg trace=%X{traceId:-none} span=%X{spanId:-none}%n");
        encoder.start();

        ConsoleAppender<ILoggingEvent> appender = new ConsoleAppender<>();
        appender.setContext(context);
        appender.setEncoder(encoder);
        appender.start();

        ch.qos.logback.classic.Logger root =
                context.getLogger(Logger.ROOT_LOGGER_NAME);
        root.setLevel(Level.INFO);
        root.addAppender(appender);
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp. Trên PowerShell/Windows:

```powershell
javac --release 17 -encoding UTF-8 -cp "lib/*" MdcDemo.java
java -cp ".;lib/*" MdcDemo
```

Trên Linux/macOS, lệnh biên dịch giống trên; lệnh chạy dùng dấu `:` ngăn phần tử classpath:

```bash
java -cp ".:lib/*" MdcDemo
```

Đầu ra của chương trình:

```text
parent trace=0123456789abcdef0123456789abcdef span=1111111111111111
child trace=0123456789abcdef0123456789abcdef span=2222222222222222
parent-again trace=0123456789abcdef0123456789abcdef span=1111111111111111
worker-without-copy trace=none span=none
worker-with-copy trace=0123456789abcdef0123456789abcdef span=1111111111111111
worker-after-cleanup trace=none span=none
outside trace=none span=none
```

Chú ý bốn điều từ kết quả:

- `child` chỉ đổi khóa `spanId` trong MDC; `parent-again` cho thấy giá trị cũ đã được khôi phục.
- `worker-without-copy` không có hai khóa mặc dù luồng gửi việc đang có chúng.
- `worker-with-copy` nhìn thấy bản sao đã chụp trước khi gửi việc.
- `worker-after-cleanup` chạy trên cùng luồng của executor nhưng không giữ ID của công việc trước.

Các lệnh `.get()` làm thí nghiệm chờ từng công việc xong để thứ tự đầu ra ổn định. Mã sao chép MDC ở đây chỉ kiểm chứng việc mang dữ liệu ghi log sang luồng khác. Nó không chuyển ngữ cảnh của tracer, không tạo quan hệ span và không bảo đảm lời gọi HTTP trong luồng đó nối đúng trace.

`configureLogging()` đặt lại cấu hình logger chỉ để thí nghiệm có đầu ra xác định. Không sao chép thao tác đặt lại cấu hình này vào ứng dụng Spring Boot đang chạy.

## 5. Khi dùng @Async, executor hoặc Reactor

### 5.1. Truyền ngữ cảnh khi đổi luồng

Chuyển sang luồng khác là một ranh giới cần xử lý. Ví dụ `CompletableFuture.runAsync(...)` không truyền executor sẽ dùng nhóm luồng mặc định; không nên mặc định nó nhận ngữ cảnh của yêu cầu HTTP.

Trong Spring Framework 6.1, `ContextPropagatingTaskDecorator` hỗ trợ chụp và khôi phục ngữ cảnh qua các accessor đã đăng ký trong Micrometer Context Propagation. Có thể gắn nó vào executor do ứng dụng quản lý. Đây là lớp cấu hình bổ sung cho dự án Spring Boot ở phần 3:

```java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
public class TraceTaskConfiguration {
    @Bean("traceExecutor")
    public ThreadPoolTaskExecutor traceExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("trace-demo-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
```

Spring quản lý khởi tạo và đóng bean executor này. Gửi công việc vào chính bean `traceExecutor` khi ngữ cảnh nguồn còn hiện hành; decorator chụp ngữ cảnh ở lúc giao việc và khôi phục trong lúc chạy. Với HTTP observation do Spring Boot cấu hình, đây là cách giữ ngữ cảnh quan sát qua executor. Xem [API ContextPropagatingTaskDecorator của Spring 6.1](https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html).

Nếu dùng `@Async("traceExecutor")`, cần bật `@EnableAsync` và gọi qua proxy Spring, thường từ bean khác. Một lời gọi nội bộ như `this.sendAsync()` không đi qua proxy mặc định, nên chưa chứng minh mã chạy bất đồng bộ hay dùng executor đã cấu hình.

Decorator không tự biết mọi biến `ThreadLocal` và mọi khóa MDC tùy ý. Ngữ cảnh nào được truyền phụ thuộc các `ThreadLocalAccessor` đã đăng ký. Với khóa nghiệp vụ tự thêm, phải cấu hình accessor hoặc cơ chế truyền riêng phù hợp. Đừng suy ra rằng có `traceId` là mọi khóa MDC cũng được sao chép.

Micrometer mô tả rõ thao tác chụp giá trị, thiết lập chúng trong scope và khôi phục giá trị trước đó khi scope đóng trong [ví dụ Context Propagation](https://docs.micrometer.io/context-propagation/reference/usage.html). Chụp ngữ cảnh bên trong luồng đích sau khi ngữ cảnh nguồn đã mất sẽ không lấy lại được thông tin nguồn.

Ngoài việc kiểm tra ID, cần phân biệt:

- **Tiếp tục ngữ cảnh hiện hành:** mã ở luồng đích có thể vẫn ghi cùng `spanId` nếu không mở span khác.
- **Tạo bước được đo riêng:** tạo span/observation con trong phạm vi thích hợp; khi đó `traceId` được giữ và `spanId` thay đổi.

Đổi tên luồng, dùng `@Async` hoặc dùng virtual thread không tự tạo span con.

### 5.2. Trong luồng xử lý phản ứng

Với Reactor, một chuỗi xử lý có thể đổi luồng nhiều lần. Không nên `MDC.put(...)` lúc lắp ráp `Mono` rồi giả định mọi toán tử chạy sau đó đều đọc được dữ liệu ấy. Ngữ cảnh Reactor và thời điểm thực thi khác với việc giữ dữ liệu trên một luồng.

Trong Spring Boot 3.3, có thể bật chế độ truyền ngữ cảnh tự động cho Reactor:

```yaml
spring:
  reactor:
    context-propagation: auto
```

Cấu hình này hỗ trợ khôi phục các giá trị `ThreadLocal` được tích hợp từ ngữ cảnh phản ứng. Nó không thay thế tracing bridge, instrumentation hoặc việc đăng ký accessor cho dữ liệu tùy chỉnh. Cần kiểm tra log ngay tại toán tử thực thi, nhất là quanh `publishOn`, `subscribeOn` và những ranh giới do mã tự tạo. Tham khảo [phần truyền ngữ cảnh của Spring Boot 3.3](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

## 6. Thêm dữ liệu nghiệp vụ vào MDC mà không làm hỏng trace

Giả sử cần gắn một mã đơn hàng vào các log của một đoạn xử lý đồng bộ. Hãy dùng khóa riêng như `orderId`, giữ giá trị trước đó và khôi phục trong `finally`. Đoạn mã sau là phương thức để đặt trong một lớp dịch vụ đã có biến `log` và import `org.slf4j.MDC`:

```java
public void processOrder(String orderId) {
    String previousOrderId = MDC.get("orderId");
    try {
        MDC.put("orderId", orderId);
        log.info("processing-order");
    } finally {
        if (previousOrderId == null) {
            MDC.remove("orderId");
        } else {
            MDC.put("orderId", previousOrderId);
        }
    }
}
```

Muốn thấy khóa này, mẫu log cần có `%X{orderId:-}`, hoặc encoder JSON cần xuất trường tương ứng. Khóa trong MDC cũng không tự trở thành thuộc tính span.

Có thể dùng `MDC.putCloseable(...)` để tự xóa khóa khi rời khối `try`. Tuy nhiên, đối tượng đóng này xóa khóa, không khôi phục một giá trị cũ bị ghi đè. Với các phạm vi lồng nhau cùng khóa, cách lưu và khôi phục như trên thể hiện đúng yêu cầu. Xem [API MDC của SLF4J](https://www.slf4j.org/apidocs/org/slf4j/MDC.html).

Những nguyên tắc thực tế:

- Chỉ quản lý khóa do đoạn mã sở hữu; tránh `MDC.clear()` ở cuối một hàm dịch vụ vì nó xóa cả `traceId`, `spanId` và dữ liệu của lớp gọi.
- Không ghi đè hai khóa tracing bằng `requestId`, UUID mới hoặc ID nghiệp vụ. Khi cần thêm mã yêu cầu riêng, dùng tên khóa riêng.
- Một khóa MDC cục bộ không tự được truyền qua mạng. Dữ liệu bổ sung cần truyền giữa dịch vụ có thể dùng cơ chế baggage được cấu hình; phải xác định rõ trường nào được truyền và trường nào được đưa vào log.
- Giữ dữ liệu ghi log nhỏ và phù hợp mục đích chẩn đoán; không đưa mật khẩu hoặc token vào MDC.
- Không dùng `traceId` hay `orderId` làm nhãn metric có số lượng giá trị tăng theo mỗi yêu cầu. Tìm kiếm từng lần xử lý là nhiệm vụ của log/trace.

## 7. Liên kết log giữa các dịch vụ

Cùng in hai trường có cùng tên chưa đủ để nối trace qua mạng. Dịch vụ gọi phải đưa ngữ cảnh vào yêu cầu gửi đi, dịch vụ nhận phải trích xuất bằng định dạng tương thích.

Một định dạng phổ biến là W3C Trace Context, dùng header `traceparent` với cấu trúc gồm phiên bản, trace ID, parent ID và cờ trace. MDC là dữ liệu cục bộ phục vụ ghi log; nó không phải header HTTP. Không tự lấy `MDC.get("traceId")` rồi coi chuỗi đó là toàn bộ `traceparent`. Chi tiết định dạng nằm trong [đặc tả W3C Trace Context](https://www.w3.org/TR/trace-context/).

Trong Spring Boot, hãy tạo HTTP client qua builder do Boot cấu hình, chẳng hạn `RestClient.Builder`, `RestTemplateBuilder` hoặc `WebClient.Builder`, để nhận tích hợp quan sát và truyền ngữ cảnh. Khi tự tạo client ngoài đường cấu hình ấy, phải tự kiểm chứng instrumentation tương ứng.

Có thể kiểm tra theo đường đi sau:

1. Tìm `traceId` của yêu cầu ở dịch vụ A.
2. Kiểm tra lời gọi A → B dùng client được tích hợp truy vết.
3. Kiểm tra B trích xuất đúng ngữ cảnh gửi đến.
4. So sánh `traceId` trong log A và B, rồi đối chiếu cây span tại hệ thống truy vết.

Các dịch vụ cùng trace thường có các span khác nhau. Không yêu cầu `spanId` của A phải bằng `spanId` của B. Khi thời gian trên các máy lệch nhau, thứ tự sắp xếp log theo dấu thời gian cũng không đủ để chứng minh quan hệ nhân quả; cần đối chiếu các span và quan hệ giữa chúng.

## 8. Chẩn đoán theo triệu chứng

| Triệu chứng | Cần kiểm tra | Cách xử lý phù hợp |
| --- | --- | --- |
| Log khởi động không có ID | Khi đó đã có span hiện hành chưa? | Chấp nhận trường rỗng nếu chưa xử lý công việc có tracing; không tạo ID giả chỉ để lấp chỗ trống |
| Log trong controller không có ID | Bridge, cấu hình tracing, HTTP instrumentation và mẫu appender thực tế | Xác nhận span hiện hành bằng `tracer.currentSpan()`, rồi kiểm tra MDC và mẫu hiển thị |
| Tracer có span nhưng console không in ID | Mẫu console/file hoặc encoder JSON có đọc đúng khóa không? | Sửa cấu hình hiển thị của đúng nơi ghi log |
| Chỉ mất ID sau khi chuyển sang executor | Executor thực tế có truyền ngữ cảnh không? | Gắn cơ chế truyền ngữ cảnh và gửi việc qua đúng executor |
| Công việc mới mang ID của công việc cũ | Dữ liệu trên luồng dùng lại có được khôi phục không? | Dọn trong `finally` và kiểm tra cả khi có ngoại lệ |
| Log A và B có `traceId` khác nhau | Lời gọi mạng có đưa và nhận ngữ cảnh tương thích không? | Kiểm tra client, header, proxy trung gian và cấu hình truyền ngữ cảnh |
| Log có ID nhưng tìm trace không thấy | Quyết định chọn mẫu, exporter, endpoint nhận, bộ thu thập, thời gian lưu | Kiểm tra riêng luồng xuất trace; không kết luận MDC sai chỉ từ việc thiếu trace |
| Một yêu cầu đổi `spanId` giữa các dòng | Có bước xử lý con hoặc scope lồng nhau không? | Đối chiếu cây span; đây có thể là hành vi đúng |
| Sau khối span con, log vẫn dùng ID con | Scope có được đóng trên đúng luồng không? | Dùng quản lý phạm vi tự động và tách đóng scope khỏi kết thúc span |

Một trace không được chọn để ghi/xuất vẫn có thể mang ngữ cảnh và ID phục vụ liên kết log. Ngược lại, việc đổi mức log không quyết định span nào được xuất. Để kiểm tra toàn bộ đường đi, cần xem cả cấu hình logging lẫn cấu hình tracing và hệ thống nhận span.

Nếu ứng dụng tự đưa log vào một hàng đợi rồi chỉ đọc MDC ở luồng tiêu thụ, ngữ cảnh có thể đã thay đổi. Phải chụp dữ liệu liên quan tại lúc tạo sự kiện hoặc dùng cơ chế ghi log bất đồng bộ có hỗ trợ ngữ cảnh của sự kiện; đừng đọc MDC của luồng tiêu thụ để đoán ngữ cảnh luồng nguồn.

## 9. Thực hành kiểm tra khả năng giải thích

### Bài tập 1: Nhận diện phạm vi

Chạy ví dụ Spring Boot hai lần, mỗi lần gọi endpoint một yêu cầu độc lập và không truyền ngữ cảnh từ bên ngoài. Trong mỗi lần gọi, tìm ba thông điệp `received`, `preparing`, `completed`.

Kết quả cần giải thích được: ba dòng trong một lần gọi dùng chung trace; dòng ở span con có ID span khác; sau đó quay về span HTTP. Hai yêu cầu độc lập thường tạo trace khác nhau. Không lấy ID cụ thể của một lần chạy làm đáp án cố định.

### Bài tập 2: Làm lộ lỗi dùng lại luồng

Trong bản sao của thí nghiệm `MdcDemo`, bỏ thao tác `restore(previous)` trong `finally` của công việc có sao chép MDC. Giữ executor chỉ có một luồng.

Dự đoán trước khi chạy: `worker-after-cleanup` sẽ còn thấy hai ID đã sao chép, vì cùng luồng đó chưa được dọn. Khôi phục `finally` và xác nhận dòng này trở lại `trace=none span=none`.

### Bài tập 3: Phân biệt lỗi hiển thị và lỗi ngữ cảnh

Trong dự án Spring Boot thực hành, giữ nguyên tracing và thay phần correlation bằng chuỗi không chứa `%X`. Quan sát log rồi kiểm tra giá trị trả về từ endpoint.

Điều cần rút ra: không in ID trong mẫu log không có nghĩa span hiện hành đã mất. Ngược lại, tự ghi một chuỗi có tên `traceId` trong MDC cũng chưa chứng minh có trace thật. Hãy kiểm tra đúng tầng: tracer xác định ngữ cảnh, MDC cung cấp dữ liệu cho logger, mẫu log quyết định cách hiển thị, còn exporter chịu trách nhiệm gửi span.
