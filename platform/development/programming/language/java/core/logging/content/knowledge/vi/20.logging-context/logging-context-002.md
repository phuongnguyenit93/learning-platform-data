# Request context trong Java Logging: gắn, truyền và dọn ngữ cảnh của từng yêu cầu

## 1. Request context là gì?

Trong một dịch vụ Java phục vụ nhiều HTTP request hoặc message cùng lúc, lời gọi log đơn lẻ như:

```java
log.warn("Cache miss for product {}", productId);
```

cho biết **điều gì** xảy ra, nhưng chưa đủ trả lời **xảy ra trong yêu cầu nào**. Cùng một service có thể đang xử lý hàng trăm request và các dòng log từ nhiều thread xen kẽ. Khi điều tra lỗi, người vận hành cần nhóm lại các sự kiện thuộc cùng một lần xử lý.

**Request context** là tập thông tin mô tả phạm vi thực thi của một request hoặc một đơn vị công việc, chẳng hạn `request_id`, `trace_id`, `span_id`, loại route, tenant đã được phê duyệt ghi log và thông tin ngữ cảnh kỹ thuật khác. Logging context là cách đưa những thông tin đó vào sự kiện log để lọc, liên kết và phân tích.

Ví dụ hai request được xử lý xen kẽ:

```text
INFO  request_id=req-A event=request.received
INFO  request_id=req-B event=request.received
WARN  request_id=req-A event=inventory.cache_miss
ERROR request_id=req-B event=payment.failed
INFO  request_id=req-A event=request.completed
```

Dù trình tự bị xen kẽ, ta có thể lọc `request_id=req-A` để xem hành trình request A. Không cần tách log bằng thread name hoặc suy đoán dựa trên thời gian.

Trong Java Logging, request context thường được đặt trong **MDC** (Mapped Diagnostic Context) khi dùng SLF4J/Logback hoặc **ThreadContext** khi dùng Log4j 2. Logging backend có thể lấy các giá trị này vào message text hoặc các field JSON.

**Mục tiêu không phải lưu toàn bộ HTTP request vào log.** Context cần *nhỏ, ổn định, có ý nghĩa vận hành, có vòng đời rõ ràng và không chứa thông tin nhạy cảm ngoài chính sách*.

## 2. Những loại ID không nên nhầm lẫn

| Trường | Ý nghĩa | Phạm vi thường gặp | Ví dụ |
| --- | --- | --- | --- |
| `request_id` | Định danh một lần xử lý request theo quy ước hệ thống | Một HTTP request vào gateway/service | `req-17` |
| `trace_id` | Liên kết các hoạt động thuộc một distributed trace | Qua nhiều service/process | `4bf92f3577b34da6a3ce929d0e0e4736` |
| `span_id` | Định danh một span cụ thể trong trace | Một phần công việc được instrument | `00f067aa0ba902b7` |
| `correlation_id` | ID liên kết theo quy ước nghiệp vụ/hệ thống | Một chuỗi yêu cầu hoặc message liên quan | `corr-42` |
| `job_id` | Định danh một lượt chạy job | Batch/scheduler | `job-2026-001` |
| `message_id` | Định danh một message trên broker | Hệ thống hàng đợi | `msg-83` |
| `event_code` | **Loại sự kiện**, không phải ID của request | Dùng lại giữa nhiều request | `payment.failed` |
| `order_id` | Định danh thực thể nghiệp vụ | Có thể xuất hiện qua nhiều request | `O-17` |

**Request ID không đồng nghĩa với trace ID.** Một HTTP request có thể tạo nhiều span, trong khi một distributed trace có thể bao gồm các request liên-service. Nhiều hệ thống không có tracing đầy đủ vẫn dùng request ID rất hiệu quả; ngược lại, ứng dụng có tracing chuẩn nên tái sử dụng `trace_id` từ tracing context chứ không tự phát minh một trace ID mới ở mọi method.

**Event code không phải context ID.** `event_code=payment.failed` giúp đếm/nhóm *loại lỗi*; `request_id` hoặc `trace_id` giúp tìm *một trường hợp cụ thể*. Nếu dashboard dùng request ID làm metric label, số lượng giá trị riêng (cardinality) có thể tăng quá lớn.

### Những trường nên cân nhắc trong context

Một bộ trường tối thiểu thực tế:

- `request_id`: một ID có thể tìm kiếm và truyền qua các bản ghi của request.
- `trace_id` và `span_id`: chỉ khi có tracing context thực sự, dùng định dạng của hệ thống tracing.
- `service`, `environment`: thường được gắn bởi cấu hình encoder/deployment, không nhất thiết phải `MDC.put` mỗi request.
- `http_method`: khi có nhu cầu điều tra, ví dụ `GET` hoặc `POST`.
- `http_route`: **route template** như `/orders/{id}` thay vì raw URL có token, email hoặc giá trị động.
- `tenant_id`: chỉ khi được chính sách dữ liệu cho phép, và đã xác thực phạm vi người dùng/tenant.
- `user_id`: chỉ khi thực sự cần, có cơ chế hạn chế truy cập hoặc pseudonymization theo chính sách.
- `operation`, `job_id`, `message_id`: với xử lý không phải HTTP.

**Không có quy tắc “càng nhiều context càng tốt”.** Một context chứa hàng trăm field, toàn bộ request body hoặc headers sẽ làm tăng tải và rủi ro rò rỉ dữ liệu.

## 3. Request context đi qua những tầng nào?

Xét một HTTP request đến Java service:

```text
HTTP request
    |
    v
Gateway / Server filter / Interceptor
    |
    +-- Kiểm tra hoặc tạo request ID
    +-- Nhận tracing context tin cậy
    +-- Đặt MDC/ThreadContext
    |
    v
Controller
    |
    +-- Log event=request.received
    |
    v
Service / Repository
    |
    +-- Log event=inventory.checked
    +-- Log event=payment.attempt_failed
    |
    +-- Async task / Executor -> cần propagate context rõ ràng
    |
    v
Response / completion
    |
    +-- Log event=request.completed
    |
    v
finally / lifecycle hook
    |
    +-- Khôi phục hoặc xóa request context
```

Điều quan trọng không phải chỉ đặt `MDC.put("request_id", value)` ở đầu; phải xác định **điểm kết thúc phạm vi** và cách context được chuyển qua các ranh giới bất đồng bộ.

Các tình huống thường gặp:

1. **Một request trên một thread suốt vòng đời:** MDC theo thread hoạt động thuận tiện nếu luôn cleanup.
2. **Request đổi thread qua executor/`CompletableFuture`:** thread mới có thể không nhận context, cần cơ chế propagation.
3. **Framework reactive:** công việc có thể di chuyển qua nhiều thread, phải dùng context bridge được framework/instrumentation hỗ trợ.
4. **Message consumer:** mỗi message có context riêng, không được giữ context của message trước khi worker tái sử dụng.
5. **Scheduled job:** không có HTTP request; nên dùng `job_id`/`operation_id` và không tự tạo field `request_id` giả nếu không phù hợp.
6. **Một request gọi service khác:** cần truyền correlation/tracing qua giao thức đã thống nhất, không nhầm MDC trong một JVM với context truyền qua mạng.

MDC thường chỉ là một nơi **lưu ngữ cảnh cho logging trong phạm vi thực thi hiện tại**, không phải giao thức truyền context giữa service, không tự là span và không phải nơi lưu state nghiệp vụ.

## 4. MDC của SLF4J và Logback

Với mã dùng SLF4J:

```java
import org.slf4j.MDC;

MDC.put("request_id", "req-A");
try {
    log.info("event=request.received");
    process();
} finally {
    MDC.remove("request_id");
}
```

Đây là **đoạn minh họa trong một method**, giả định đã có `log` và `process()`. `MDC.put` gắn chuỗi key/value vào context hiện tại; logging backend tương thích có thể lấy giá trị đó khi tạo event.

Một pattern Logback phổ biến:

```xml
<encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
    <pattern>%level|rid=%X{request_id}|%logger{0}|%msg%n</pattern>
    <charset>UTF-8</charset>
</encoder>
```

Nếu MDC có `request_id=req-A` thì một dòng có thể là:

```text
INFO|rid=req-A|OrderService|event=request.received
```

**Lưu ý:** chuỗi `%X{request_id}` là cú pháp của layout, không phải cú pháp thay thế tham số `{}` trong message. `%msg` lấy message của sự kiện; `%X{...}` lấy context. Một message có `order_id={}` không tự tạo field `order_id` trong MDC.

### Vì sao dùng `finally`?

Thread pool thường tái sử dụng thread. Nếu request A đặt `request_id=req-A` và không cleanup, request B chạy sau trên cùng thread có thể ghi sai:

```text
INFO|rid=req-A|PaymentService|event=payment.started
```

dù thực tế event thuộc request B. Đây là **context leakage**, làm sai điều tra, audit và liên kết trace.

Cleanup phải chạy khi request kết thúc **kể cả** controller ném exception, bị hủy hoặc timeout theo cơ chế framework. Dùng `try/finally` hoặc lifecycle hook phù hợp, không chỉ xóa context trên nhánh thành công.

### `remove`, `clear` và khôi phục context cũ

- `MDC.remove("request_id")` chỉ xóa một key; phù hợp khi mình sở hữu key đó và các key khác cần giữ.
- `MDC.clear()` xóa toàn bộ map của context hiện tại; dùng thiếu cẩn trọng có thể xóa các trường đã được instrumentation đặt.
- `MDC.getCopyOfContextMap()` lấy snapshot map hiện tại, có thể trả `null` khi không có giá trị.
- `MDC.setContextMap(map)` thay map MDC theo dữ liệu được cung cấp; khi cần trả về trạng thái không có context, dùng `MDC.clear()`.

Nếu một scope có thể **lồng nhau**, cách an toàn là lưu map trước đó, thiết lập context mới trong scope, rồi **khôi phục snapshot cũ** trong `finally`. Điều này ngăn scope con vô tình làm mất context mà scope cha đang quản lý.

Lưu ý thêm: SLF4J là facade; `MDC` hoạt động cụ thể qua adapter của provider/backend. Cần xác minh backend thực và cách nó xử lý MDC. Không suy luận rằng cùng một `MDC.put` sẽ có output giống nhau trên mọi provider.

## 5. Ví dụ Java 17 chạy đầy đủ: MDC, hai request và thread pool

Bài thực hành dưới đây mô phỏng hai request được xử lý liên tiếp. Mỗi request:

1. Đặt `request_id` và `trace_id`.
2. Ghi event bắt đầu trên main thread.
3. Gửi một công việc sang `ExecutorService`.
4. **Chụp snapshot và khôi phục MDC** khi công việc chạy trên worker thread.
5. Chờ công việc hoàn thành bằng `Future.get()`.
6. Ghi event kết thúc, rồi **khôi phục context trước request**.
7. Sau hai request, ghi một event ngoài scope để chứng minh không rò context.

Kết quả được thiết kế ổn định: một worker thread, chờ Future, pattern không chứa timestamp hoặc thread name.

### 5.1. Cấu trúc Maven

```text
request-context-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── RequestContextDemo.java
        └── resources/
            └── logback.xml
```

Yêu cầu **JDK 17 trở lên**, Maven và quyền tải dependency khi chưa có cache.

### 5.2. Tệp `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>request-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.16</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` cung cấp backend và provider SLF4J tương thích. Phiên bản cố định phục vụ **một ví dụ có thể tái lập**, không phải khẳng định về bản mới nhất hoặc phù hợp với mọi framework. Khi đưa vào ứng dụng thực, kiểm tra version management và thông báo bảo mật hiện hành.

### 5.3. Tệp `src/main/resources/logback.xml`

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <target>System.out</target>
        <encoder class="ch.qos.logback.classic.encoder.PatternLayoutEncoder">
            <pattern>%level|RequestContextDemo|rid=%X{request_id}|trace=%X{trace_id}|%msg%n</pattern>
            <charset>UTF-8</charset>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE" />
    </root>
</configuration>
```

Trong pattern trên, `RequestContextDemo` là **chuỗi literal** dùng để đầu ra của bài thực hành dễ đọc. Trong production, thường nên dùng `%logger` hoặc `%logger{0}` để lấy logger name thật, tránh hard-code tên class.

`%X{request_id}` và `%X{trace_id}` lấy giá trị MDC; khi key vắng mặt, phần chuyển đổi của pattern này được hiển thị rỗng. `%msg` là message, `%n` thêm newline.

### 5.4. Tệp `src/main/java/demo/RequestContextDemo.java`

```java
package demo;

import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class RequestContextDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(RequestContextDemo.class);

    private RequestContextDemo() {
    }

    private static void restore(Map<String, String> snapshot) {
        if (snapshot == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(snapshot);
        }
    }

    private static Runnable propagate(Runnable action) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();
            try {
                restore(captured);
                action.run();
            } finally {
                restore(previous);
            }
        };
    }

    private static void handleRequest(
            ExecutorService pool,
            String requestId,
            String traceId) throws Exception {

        Map<String, String> previous =
                MDC.getCopyOfContextMap();

        try {
            MDC.put("request_id", requestId);
            MDC.put("trace_id", traceId);

            LOG.info("event=request.started");

            Future<?> task = pool.submit(propagate(() ->
                    LOG.info("event=inventory.checked")));
            task.get();

            LOG.info("event=request.completed");
        } finally {
            restore(previous);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool =
                Executors.newSingleThreadExecutor();

        try {
            handleRequest(pool, "req-A", "trace-A");
            handleRequest(pool, "req-B", "trace-B");
            LOG.info("event=outside.request");
        } finally {
            pool.shutdown();
        }
    }
}
```

### 5.5. Biên dịch, chạy và stdout

Từ thư mục `request-context-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RequestContextDemo
```

**Bảy dòng do Logback của ứng dụng phát qua cấu hình mẫu:**

```text
INFO|RequestContextDemo|rid=req-A|trace=trace-A|event=request.started
INFO|RequestContextDemo|rid=req-A|trace=trace-A|event=inventory.checked
INFO|RequestContextDemo|rid=req-A|trace=trace-A|event=request.completed
INFO|RequestContextDemo|rid=req-B|trace=trace-B|event=request.started
INFO|RequestContextDemo|rid=req-B|trace=trace-B|event=inventory.checked
INFO|RequestContextDemo|rid=req-B|trace=trace-B|event=request.completed
INFO|RequestContextDemo|rid=|trace=|event=outside.request
```

Maven có thể bổ sung thông tin riêng; đây là **output logging của ứng dụng** khi tệp `logback.xml` trên được nạp và không có backend/provider cạnh tranh.

### 5.6. Tại sao ví dụ đúng?

- `MDC.put` thiết lập hai key trên thread xử lý request; hai sự kiện chính của mỗi request nhận context tương ứng.
- `propagate` **chụp snapshot tại thời điểm tạo Runnable**, trước khi gửi vào pool. Không dùng trực tiếp map chia sẻ bị biến đổi về sau.
- Trong worker thread, `propagate` lưu MDC cũ, áp context của request, chạy tác vụ và khôi phục MDC cũ trong `finally`. Nếu worker được tái sử dụng cho request sau, nó không còn mang `req-A`.
- `Future.get()` chờ tác vụ xong trước khi in `request.completed`, nên thứ tự trong output của demo có thể dự đoán.
- `handleRequest` lưu và khôi phục MDC của thread gọi; nếu một tầng phía ngoài đã đặt ngữ cảnh khác, nó không bị xóa toàn bộ chỉ vì một request scope kết thúc.
- Sau hai request, `event=outside.request` có cả hai field rỗng, minh họa không bị **context leakage** trên thread chính.

**Giới hạn:** đây là ví dụ minh họa cách propagate bằng snapshot cho một `Runnable`. Trong ứng dụng thật, một executor cũng nhận `Callable`, task lồng nhau, cancellation và các framework khác; cần dùng cơ chế context propagation của framework/instrumentation hoặc wrapper đầy đủ cho những đường đi thực tế. Không sao chép nguyên một wrapper tự chế để thay thế toàn bộ hệ thống tracing nếu đã có công cụ quản lý context.

## 6. Tại sao `ThreadLocal` không tự giải quyết bài toán async?

Nhiều implementation MDC ở backend Java lưu dữ liệu theo một phạm vi tương tự **thread-local**. Nguyên tắc quan trọng:

**Dữ liệu của thread A không tự xuất hiện an toàn trong thread B khi A gọi `executor.submit(...)`.**

Ví dụ sai kỳ vọng:

```java
MDC.put("request_id", "req-A");

executor.submit(() -> {
    log.info("event=work.started");
});
```

Đây là **đoạn minh họa**. Logger trong task có thể không có `request_id` vì task chạy ở thread khác. Tùy implementation/framework, nó cũng có thể mang context cũ do thread pool đã từng dùng và không được cleanup.

### Không dùng `InheritableThreadLocal` như lời giải chung

`InheritableThreadLocal` có khái niệm kế thừa lúc thread con được tạo, nhưng executor thường **tái sử dụng** thread; một worker có thể được tạo từ trước khi request bắt đầu. Kế thừa lúc tạo thread không bảo đảm context chính xác cho từng task được submit về sau.

Vì vậy, ngay cả khi một backend có cơ chế hỗ trợ copy context cho thread con, **không được suy luận rằng nó tự hoạt động đúng trên thread pool**. Hãy kiểm thử bằng hai request liên tiếp trên cùng một worker thread.

### Snapshot khi submit, restore khi chạy

Quy tắc an toàn cho Runnable/Callable:

1. Lấy context snapshot ở **thread gửi task**.
2. Truyền snapshot qua đường submit hoặc API propagation chính thức.
3. Khi worker chuẩn bị chạy, lưu context cũ của worker.
4. Áp snapshot cho thời gian thực thi task.
5. Trong `finally`, khôi phục context cũ của worker.
6. Khi task xong, thread worker không giữ context của request đó.

Không chỉ gọi `MDC.clear()` ở cuối worker trong mọi trường hợp: nếu một framework đã đặt context hợp lệ trước task, việc xóa toàn bộ có thể phá dữ liệu của nó. **Khôi phục previous snapshot** phù hợp hơn khi scope có thể lồng nhau.

### `CompletableFuture` và parallel stream

Một đoạn như:

```java
CompletableFuture.supplyAsync(() -> service.fetch(id));
```

có thể chạy trên executor riêng hoặc common pool, tùy overload và cách dùng. Đừng giả định MDC đi theo request chỉ vì task được tạo từ request thread. Với `CompletableFuture`, cần wrapper/explicit executor và propagation tại **mỗi ranh giới scheduling có liên quan**, không chỉ tại bước đầu.

Parallel stream có thể dùng nhiều worker; việc dựa vào một MDC duy nhất theo thread dễ dẫn đến log thiếu hoặc lẫn context. Nếu nghiệp vụ cần correlation, hãy chuyển ID theo dữ liệu của task hoặc tích hợp context propagation đã được kiểm thử.

### Reactive pipelines và virtual threads

Trong Reactor/WebFlux và các hệ thống reactive, callback có thể chuyển thread nhiều lần; request context thường cần được quản lý qua **Reactor Context hoặc cơ chế context propagation được tích hợp**, không chỉ một `MDC.put` tại điểm vào HTTP.

Virtual threads xuất hiện ở các phiên bản Java sau JDK 17 (không phải API sẵn có trong ví dụ Java 17), nhưng **chỉ thay mô hình thread không tự giải quyết việc truyền context giữa các tác vụ độc lập**. Dù dùng platform thread hay virtual thread, vòng đời, propagation và cleanup vẫn cần thiết kế rõ.

Không có một “MDC tự động chạy trong mọi async framework” có thể khẳng định chung.

## 7. Áp dụng tại ranh giới HTTP bằng Servlet Filter

Trong một ứng dụng Jakarta Servlet, vị trí thuận tiện để đặt context là filter chạy quanh request. Ví dụ dưới đây là **đoạn minh họa**, yêu cầu Jakarta Servlet API, một servlet container/framework và SLF4J; nó **không nằm trong dự án Maven độc lập của phần 5**.

```java
import jakarta.servlet.Filter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.ServletRequest;
import jakarta.servlet.ServletResponse;
import jakarta.servlet.http.HttpServletRequest;
import org.slf4j.MDC;

import java.io.IOException;
import java.util.Map;
import java.util.UUID;

public final class RequestIdFilter implements Filter {
    @Override
    public void doFilter(
            ServletRequest request,
            ServletResponse response,
            FilterChain chain)
            throws IOException, ServletException {

        HttpServletRequest http = (HttpServletRequest) request;
        String incoming = http.getHeader("X-Request-ID");

        String requestId = isAllowedId(incoming)
                ? incoming
                : UUID.randomUUID().toString();

        Map<String, String> previous =
                MDC.getCopyOfContextMap();

        try {
            MDC.put("request_id", requestId);
            MDC.put("http_method", http.getMethod());
            chain.doFilter(request, response);
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    }

    private static boolean isAllowedId(String value) {
        return value != null
                && value.length() >= 1
                && value.length() <= 64
                && value.matches("[A-Za-z0-9._-]+");
    }
}
```

### Điều gì cần xem xét trước khi dùng thực tế?

- **Không tin mọi header từ client.** `X-Request-ID` ở ví dụ là quy ước ứng dụng; hệ thống có thể chọn chấp nhận, thay mới hoặc ưu tiên ID do gateway tin cậy phát. Quy tắc phải được định nghĩa và thống nhất giữa các service.
- **Giới hạn format và độ dài** để ngăn newline/log injection và dữ liệu rác khổng lồ. Regex của ví dụ chỉ là một allowlist đơn giản, không phải định dạng trace ID chuẩn.
- **Không log raw URL chứa dữ liệu cá nhân hoặc token.** Nếu muốn route, sử dụng route template sau routing hoặc metadata được framework chuẩn hóa.
- **Không bao luôn việc xử lý async request chỉ bằng một `try/finally` ở filter đồng bộ.** Nếu ứng dụng dùng Servlet async dispatch hoặc kết thúc response sau khi thread ban đầu rời filter, cần gắn context ở đúng những lifecycle callback/dispatch tiếp theo và dọn đúng thời điểm.
- **Không ép mọi `ServletRequest` là `HttpServletRequest`** trong một filter được thiết kế chung cho nhiều giao thức; ví dụ chỉ dành cho ứng dụng HTTP.
- **Không coi header ID là bằng chứng xác thực.** ID giúp liên kết log, không chứng minh người gọi là ai.
- **Không tự gán `trace_id` bằng UUID nếu tracing đang dùng định dạng chuẩn khác.** Lấy từ tracing instrumentation.

Trong dự án thật, việc cài filter, thứ tự filter, response header và cách lấy status code phụ thuộc framework. Một framework có sẵn request correlation/tracing có thể đã cung cấp filter/interceptor; nên **kiểm tra trước khi viết thêm**, tránh hai lớp gán ID khác nhau hoặc ghi log hai lần.

### Request ID truyền lại cho client

Một số API trả ID liên kết trong response header để support có thể tìm log khi người dùng báo lỗi. Nếu làm vậy, hãy thống nhất tên header và format, không tiết lộ ID chứa dữ liệu riêng tư hoặc thông tin nhạy cảm. ID vẫn chỉ là mã tra cứu, **không trao quyền truy cập log** cho người giữ ID.

## 8. Từ HTTP request sang gọi service khác

Giả sử service A nhận request và gọi service B:

```text
Client -> Gateway -> Service A -> Service B -> Database
            |             |            |
            v             v            v
        request ID    trace/span    trace/span
```

Việc `MDC.put` ở service A **không tự gửi dữ liệu sang B**. Phải truyền context qua HTTP header hoặc metadata của giao thức theo thỏa thuận.

Hai chiến lược phổ biến:

- **Request/correlation ID riêng:** gateway/service đặt header như `X-Request-ID` theo hợp đồng nội bộ, downstream xác minh và sử dụng/đặt lại theo chính sách tin cậy.
- **Distributed tracing chuẩn:** instrumentation nhận/truyền W3C Trace Context qua `traceparent` và các trường liên quan, backend logging lấy `trace_id`/`span_id` từ span hiện tại.

Đừng viết regex nửa vời tự parse `traceparent` rồi đổi lại bằng chuỗi bất kỳ. W3C Trace Context có định dạng và quy tắc hợp lệ riêng; ưu tiên SDK/instrumentation tracing được hỗ trợ để tạo, nhận và truyền. Với header từ nguồn không tin cậy, cần chính sách trust boundary và giới hạn metadata.

Khi downstream trả lỗi, các log của A và B có thể dùng cùng `trace_id` nhưng mỗi service có `span_id` khác nhau. Đây là **điều đúng** trong tracing, không phải mismatch.

### Tại sao chỉ truyền request ID là chưa đủ?

Request ID giúp tra cứu theo một ID, nhưng không tự có:

- Phân cấp span và thời gian từng bước.
- Parent/child relationship.
- Phân tích latency xuyên service.
- Quyết định sampling trace.
- Cơ chế propagate baggage và ranh giới tin cậy.

Nếu cần các chức năng đó, sử dụng hệ thống tracing phù hợp. Logging request context bổ sung cho distributed tracing: **log cho chi tiết sự kiện**, trace cho quan hệ và thời gian của các bước.

## 9. Message consumer và scheduled job cũng có context

Không phải công việc nào cũng xuất phát từ HTTP.

### Message consumer

Một message có thể mang `message_id`, `correlation_id`, `traceparent` trong headers hoặc metadata. Khi consumer nhận message:

1. Kiểm tra dữ liệu context đến từ broker hoặc producer theo chính sách.
2. Thiết lập context cho **một lần xử lý message**.
3. Ghi các sự kiện bắt đầu, thành công, thất bại/retry với `event_code` rõ ràng.
4. Khi gọi service khác hoặc publish message mới, propagate context phù hợp.
5. Cleanup trong `finally` trước khi worker nhận message tiếp theo.

Ví dụ **đoạn minh họa**:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("message_id", messageId);
    MDC.put("correlation_id", correlationId);
    consumerService.handle(message);
} finally {
    if (previous == null) MDC.clear();
    else MDC.setContextMap(previous);
}
```

Đoạn trên giả định đã có `messageId`, `correlationId`, `consumerService` và `message`, không phải chương trình độc lập.

**Retry một message** có thể có cùng `message_id` hoặc `correlation_id` nhưng mỗi lượt thử là một attempt khác. Cần tách `attempt` và `event_code` để không nhầm nhiều bản ghi là nhiều message nghiệp vụ.

### Scheduled job

Một batch job nên có `job_id`, `job_run_id` hoặc `operation_id` rõ nghĩa. Không nên đặt `request_id=unknown` cho mọi job chỉ để lấp cột: khi nhiều job chạy cùng nhau, `unknown` không giúp điều tra.

Ví dụ:

```text
INFO job_run_id=run-81 event=job.started
INFO job_run_id=run-81 event=batch.processed count=100
INFO job_run_id=run-81 event=job.completed
```

Khi job chạy song song nhiều task, dùng cùng cơ chế snapshot/propgation phù hợp với async tasks, đồng thời ghi `task_id`/`partition` khi cần phân biệt.

## 10. Request context trong Log4j 2: ThreadContext

Log4j 2 có `ThreadContext` để lưu context map và stack. Nó có mục đích tương tự MDC của SLF4J, nhưng là **API và implementation riêng**.

```java
import org.apache.logging.log4j.ThreadContext;

ThreadContext.put("request_id", requestId);
try {
    log.info("event=request.received");
} finally {
    ThreadContext.remove("request_id");
}
```

Đây là đoạn minh họa trong một method đã có logger và `requestId`. Một pattern Log4j 2 có thể là:

```xml
<PatternLayout
    pattern="%level|rid=%X{request_id}|%c{1}|%m%n"
    charset="UTF-8" />
```

Thẻ `PatternLayout` thuộc Log4j 2 và cần đặt trong appender phù hợp của `log4j2.xml`. Nó không phải tệp cấu hình Logback.

### Scope với CloseableThreadContext

Log4j 2 hỗ trợ helper scoped context:

```java
import org.apache.logging.log4j.CloseableThreadContext;

try (CloseableThreadContext.Instance scope =
        CloseableThreadContext.put("request_id", requestId)) {
    log.info("event=request.started");
}
```

Đây là đoạn minh họa khi có biến `requestId` và logger Log4j 2. `try-with-resources` giúp đóng phạm vi kể cả có exception. Cần kiểm tra semantics của các key context khác trong phiên bản và hệ thống đang dùng; không cho rằng mọi thread pool tự propagate chỉ vì dùng scoped helper.

### Truyền ThreadContext qua executor

Tương tự MDC, cần snapshot context map ở thread submit và áp nó trong worker, rồi khôi phục context trước đó khi task kết thúc. Log4j 2 có các API snapshot/context data tương ứng; **không sao chép `org.slf4j.MDC` sang mã Log4j 2 mà không hiểu hướng bridge/provider**.

Nếu sử dụng SLF4J API được bridge đến Log4j 2 backend, cần kiểm tra cơ chế tương tác MDC với provider đang chạy. Không giả định việc đồng thời gọi `MDC.put` và `ThreadContext.put` luôn cần thiết hoặc không bao giờ trùng nhau; chọn một API quản lý nhất quán theo kiến trúc.

## 11. Request context và structured logging

Pattern text giúp người đọc:

```text
INFO rid=req-A trace=trace-A event=inventory.checked
```

Nhưng với hệ thống phân tích tập trung, thường hữu ích hơn nếu mỗi trường được lưu riêng:

```json
{
  "timestamp": "2026-01-01T00:00:00Z",
  "level": "INFO",
  "service": "inventory",
  "event_code": "inventory.checked",
  "request_id": "req-A",
  "trace_id": "trace-A",
  "message": "Kiểm tra tồn kho hoàn tất"
}
```

Đây là **schema minh họa**. `trace-A` chỉ là giá trị giả để học cách liên kết log, **không phải trace ID hợp lệ theo W3C**.

Điểm phân biệt:

- `MDC.put("request_id", ...)` thêm context vào scope.
- `log.atInfo().addKeyValue("event_code", ...)` gắn field của **một sự kiện** nếu dùng SLF4J 2.x.
- Encoder/JSON layout lấy dữ liệu từ event và tạo JSON.
- Collector/indexer nhận JSON và lập chỉ mục các field.

Với SLF4J 2.x:

```java
log.atInfo()
        .addKeyValue("event_code", "inventory.checked")
        .addKeyValue("sku", sku)
        .log("Đã kiểm tra tồn kho");
```

Đây là snippet minh họa. `event_code` và `sku` là field riêng của event; `request_id` từ MDC có thể xuất cùng nếu encoder hỗ trợ. **Không phải mọi PatternLayout tự chuyển chúng thành JSON**, và không phải mọi backend tự in key-value pair nếu chưa cấu hình.

### Field nào nên ở MDC, field nào nên ở event?

Một quy tắc thiết kế hữu ích:

| Ngữ cảnh | Thường đặt ở đâu? | Vì sao? |
| --- | --- | --- |
| `request_id` | MDC/ThreadContext | Lặp trong nhiều log của một lần xử lý |
| `trace_id`, `span_id` | Instrumentation/MDC context | Liên kết nhiều sự kiện |
| `service`, `environment` | Cấu hình encoder/deployment | Ổn định trong cùng tiến trình |
| `event_code` | Field của từng log event | Mỗi event có ý nghĩa riêng |
| `order_id` | Field event hoặc context phạm vi nhỏ có chủ đích | Không phải mọi event cùng service đều liên quan order |
| `error_code`, `attempt`, `duration_ms` | Field của từng event | Thay đổi theo sự kiện |
| `http_route` | Context đã được chuẩn hóa | Cùng route trong request, nhưng cần tránh raw URL |

Không có quy tắc cứng cho mọi ứng dụng; điểm quan trọng là **phạm vi của dữ liệu phải khớp phạm vi sử dụng**. Đặt `order_id` ở MDC toàn thread quá sớm có thể làm các event khác vô tình mang order ID cũ.

## 12. Bảo mật và quyền riêng tư của request context

Request context giúp truy vết dễ hơn, nhưng cũng làm dữ liệu dễ tìm kiếm hơn. Những điều không nên đưa vào MDC hoặc log:

- Password, session token, API key, bearer token, cookie.
- Header `Authorization` hoặc nguyên request headers nếu chưa được kiểm soát.
- Full request/response body chứa dữ liệu cá nhân.
- Raw URL/query string có email, mã xác thực hoặc thông tin thanh toán.
- Dữ liệu thẻ, số định danh và thông tin sức khỏe khi không được phép.
- Các object mà `toString()` vô tình xuất bí mật.
- Giá trị context chưa validate có thể chứa newline/control chars.

### Đầu vào `X-Request-ID` có thể không tin cậy

Nếu ứng dụng chấp nhận ID từ bên ngoài, kẻ gửi có thể dùng:

```text
req-1
ERROR admin-auth-success
```

Đây là ví dụ về **log injection** do giá trị chứa newline. Gắn nguyên vào pattern text có thể tạo nội dung trông giống hai bản ghi.

Phòng tránh:

1. Chỉ nhận header ở trust boundary được xác định.
2. Giới hạn **độ dài, tập ký tự và số lượng** của context entries.
3. Khi không hợp lệ, tạo ID mới theo chính sách thay vì log nguyên chuỗi độc hại.
4. Dùng encoder có escaping chuẩn, nhất là khi xuất JSON Lines.
5. Không xem ID trong log như bằng chứng người dùng đã xác thực.
6. Kiểm tra quyền đọc của log trung tâm và retention.

### Tenant và user context

`tenant_id` và `user_id` có thể là thông tin cá nhân hoặc liên quan quyền truy cập. Nếu cần để điều tra, ưu tiên ID đã xác thực từ server, không dùng `X-Tenant-ID` của client chưa kiểm chứng. Việc một ID có vẻ vô danh **không có nghĩa** được phép lưu/tra cứu không giới hạn; cần chính sách dữ liệu và retention.

### Không dùng context làm nơi lưu nghiệp vụ

MDC thích hợp cho các chuỗi nhỏ phục vụ quan sát, không phải kho lưu session, quyền hạn hoặc quyết định thanh toán. Không dựa vào `MDC.get("tenant_id")` để làm authorization nếu nguồn thật của tenant nằm trong security context riêng. Logging context có thể thiếu hoặc thay đổi theo propagation và không phải kênh security tin cậy.

## 13. Hiệu năng: context không được tăng tải quá mức

Mỗi lần phát log có thể phải snapshot MDC, format các field, encode UTF-8/JSON và ghi vào appender. Nếu context có hàng chục field lớn, mọi log event có thể mang nhiều dữ liệu không cần thiết.

Những khuyến nghị:

1. Context nên nhỏ: ID ngắn, route template, metadata kỹ thuật cần thiết.
2. Dùng giá trị string/field đơn giản; tránh serialize toàn bộ domain object vào MDC.
3. Không tạo `request_id` mới ở từng dòng log; tạo một lần ở ranh giới xử lý.
4. Không bật DEBUG/TRACE diện rộng chỉ để lấy trace ID; có thể gắn context trên các event INFO/WARN/ERROR hiện có.
5. Không đưa `request_id`/`trace_id` thành label của metric có cardinality cao; lưu ở log/tracing phù hợp.
6. Với async logging backend, hiểu thời điểm backend **capture** MDC vào event và thời điểm encoder ghi. Kiểm thử thực tế, không mặc định context sẽ được đọc ở đúng một thời điểm trên mọi backend.
7. Khi thiết lập propagation ở mọi `submit`, cân nhắc chi phí copy map và số lượng task; theo dõi hiệu năng ở đường nóng.
8. Không đẩy context chứa payload lớn vào headers của downstream service; truyền những khóa đã được hợp đồng cho phép.

**Không đồng nhất việc gọi log với việc log đã được lưu.** Context đúng không giúp chống mất log do appender queue đầy, collector chậm, disk đầy hoặc container restart. Với sự kiện nghiệp vụ quan trọng cần đúng số lần, thiết kế cơ chế ghi/gửi đáng tin riêng.

## 14. Kiểm thử request context: ngăn lẫn request là yêu cầu số một

Một test thành công không chỉ xem một log có chứa `request_id`, mà còn phải chứng minh **context không dính sang request khác**.

### Ma trận test nên có

| Tình huống | Kỳ vọng |
| --- | --- |
| Request A vào logger | Tất cả event cần thiết mang `request_id=A` |
| Request B trên cùng thread sau A | Không có event của B mang A |
| Task ở executor từ A | Event task mang context A nếu propagation được thiết kế |
| Task ở executor từ B sau A | Event task mang B, không còn A |
| Task không có request context | Không bị thừa ID từ request trước |
| Nested scope có key mới | Sau khi thoát, context scope cha được khôi phục |
| Exception trong controller/service | Cleanup chạy dù đường lỗi |
| Timeout/cancellation của async task | Task bị hủy không để worker giữ context cũ |
| Tracing bridge có trace/span | ID của event đúng theo span hiện tại |
| Input header sai format | Bị từ chối/thay mới, không tạo log injection |
| Log xuất JSON | `request_id` là field riêng, cùng kiểu qua mọi event |
| Multi-tenant request | Không ghi tenant của request trước |
| No provider/encoder mismatch | Cấu hình thực sự nạp và có field ở output |
| Two services | Context được propagate qua header/instrumentation |

### Tầng kiểm thử thứ nhất: dữ liệu context

Có thể assert `MDC.get("request_id")` trong đúng scope, và kiểm tra nó trở về trạng thái cũ trong `finally`. Đây là test **state** ở JVM, chưa chứng minh appender đã ghi field.

### Tầng kiểm thử thứ hai: sự kiện logging

Với Logback, `ListAppender<ILoggingEvent>` có thể lưu logging events để kiểm tra:

- `getLoggerName()`, `getLevel()`, `getFormattedMessage()`.
- `getMDCPropertyMap()` có request ID của sự kiện khi được ghi.
- `getThrowableProxy()` nếu đang kiểm tra lỗi.
- Số lần mỗi `event_code` trong một request.

Cần gỡ/dừng appender thử nghiệm và hoàn nguyên logger settings sau test. Tránh thay đổi logger cấu hình toàn JVM trong các test chạy song song mà không cô lập.

**ListAppender không chứng minh console/json encoder đã xuất đúng byte**. Khi cần chứng minh output thật, hãy chạy subprocess hoặc appender test với encoder thực.

### Tầng kiểm thử thứ ba: console/JSON

Với pattern text của ví dụ phần 5, có thể so sánh bảy dòng log có ID chính xác. Với JSON encoder:

- Parse từng JSON object bằng thư viện JSON đáng tin.
- Assert `request_id`, `trace_id`, `event_code`, level và logger theo schema.
- Assert field **vắng mặt hoặc null/rỗng** đúng hợp đồng khi ngoài request.
- Test newline, quote, Unicode trong message không phá ranh giới JSON Lines.
- Kiểm tra ID không đúng format bị từ chối/normalize hợp lý.
- Đảm bảo không có dữ liệu nhạy cảm giả ở bất kỳ field, message hoặc exception nào.

### Tầng kiểm thử thứ tư: collector và nhiều service

Ở staging, tạo request thử với correlation ID an toàn, gọi qua hai service và tìm tại kho trung tâm:

1. Có thể tìm tất cả event bằng `trace_id` hoặc `request_id` theo hợp đồng.
2. Event từ mỗi service có `service` và logger đúng.
3. Quan hệ trace/span hợp lý khi dùng distributed tracing.
4. Không có event của request khác bị gắn nhầm ID.
5. Không có bản ghi trùng do appender/additivity hoặc collector retry ngoài chính sách.
6. Không mất một số event vì log level/filter, queue, sampling hoặc lỗi ingest.
7. Truy vấn có khoảng thời gian và quyền đọc phù hợp.

## 15. Chẩn đoán khi request context không xuất hiện

Nên đi từ nguồn đến đích:

```text
Có tạo request/correlation ID?
     |
     +-- Chưa -> Rà soát gateway/filter/interceptor
     |
     +-- Có -> Đã đặt vào MDC/ThreadContext ở đúng scope?
                     |
                     +-- Chưa -> Kiểm tra lifecycle entry/exit
                     |
                     +-- Có -> Có đổi thread hoặc process?
                                   |
                                   +-- Có -> Kiểm tra propagation
                                   |
                                   v
                             Logging event có context?
                                   |
                                   +-- Không -> Kiểm tra backend/provider/bridge
                                   |
                                   v
                             Encoder có xuất context?
                                   |
                                   +-- Không -> Pattern %X / JSON field mapping
                                   |
                                   v
                             Collector có giữ và index field?
                                   |
                                   +-- Không -> Parser, mapping, filter, retention
                                   |
                                   v
                             Truy vấn có tìm đúng thời gian và service?
```

### Lỗi phổ biến

| Triệu chứng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Log controller có ID, log executor không có | MDC không tự propagate sang thread worker | Chụp snapshot lúc submit, áp/restore tại worker hoặc dùng framework propagation. |
| Event request B mang ID của A | Quên cleanup ở thread pool | `try/finally` và khôi phục context cũ. |
| Dòng `rid=` trống | MDC chưa đặt hoặc key trong pattern sai | Kiểm tra `request_id` vs `requestId`, scope và provider. |
| Context bị mất sau nested call | Scope con gọi `MDC.clear()` | Snapshot trước scope và restore sau scope. |
| Log ở service B không có trace ID | Chỉ đặt MDC ở service A | Truyền HTTP/message context bằng SDK/instrumentation. |
| Có hai trace ID khác nhau trên cùng request | Gateway/framework và filter tự tạo ID độc lập | Quyết định owner, quy tắc trust/propagation. |
| Giá trị ID chứa newline | Tin raw client header | Validate chiều dài/ký tự, encode đúng. |
| Có MDC nhưng JSON không có field | Encoder/provider không xuất MDC hoặc mapping sai | Kiểm tra cấu hình JSON encoder/collector thực. |
| Context có ID nhưng message không có | Message/pattern chỉ in `%msg`, không có `%X` | Bổ sung converter/context provider phù hợp. |
| Không có log trong collector | Logger level, appender, stdout/file, collector hoặc retention | Kiểm tra pipeline; context không tự sinh log. |
| Tenant ID bị nhầm giữa các request | Thread reuse, cleanup sai hoặc dữ liệu nguồn sai | Xác thực nguồn tenant và restore context ở mọi nhánh. |
| Test đơn luồng pass, production lẫn context | Code async, reactive hoặc filter lifecycle khác | Test executor reuse/cancellation và integration ở runtime thật. |
| Trace trong message nhưng không lọc được field | Chỉ ghép ID vào text | Dùng structured logging/encoder và mapping. |
| Metric bị quá nhiều nhãn | Dùng request ID làm metric label | Nhóm theo `event_code`, `service`, `result`; tra ID ở log. |
| Event báo ERROR nhiều lần | Nhiều tầng cùng log một exception | Định nghĩa ranh giới failure cuối và mã sự kiện. |

## 16. Áp dụng dần vào một ứng dụng đang chạy

Một lộ trình chuyển đổi an toàn:

1. **Chọn quy tắc ID:** cái nào do gateway phát, cái nào do tracing SDK phát; giới hạn và trust boundary.
2. **Xác định owner context:** filter/interceptor cho HTTP, consumer wrapper cho message, job runner cho batch.
3. **Thiết lập lifecycle:** snapshot trước request, đặt context, chạy nghiệp vụ, cleanup/restore ở `finally`.
4. **Liệt kê async boundaries:** executor, CompletableFuture, callback, Reactor, message queue, scheduled task; mỗi loại có đường propagation riêng.
5. **Thống nhất schema:** `request_id`/`trace_id`/`span_id` có tên và kiểu giống nhau ở mọi service.
6. **Cấu hình backend:** Logback `%X{request_id}` hoặc encoder JSON; Log4j 2 `ThreadContext`/JSON template tương ứng.
7. **Thêm event code:** giúp tìm sự kiện theo loại mà không cần parse câu message.
8. **Kiểm tra bảo mật:** allowlist và hạn chế thông tin động; không đưa token/raw URL/PII vào context.
9. **Test hai request trên cùng worker:** cố tình tái sử dụng thread để phát hiện leak.
10. **Test exception/cancellation:** chứng minh cleanup vẫn chạy.
11. **Test end-to-end:** HTTP A → B, async task, JSON collector; tra theo trace/request ID.
12. **Canary và theo dõi:** phần trăm log thiếu ID, số lỗi context mismatch, tải encoder và cardinality.
13. **Rollback có kiểm soát:** nếu schema/collector lỗi, có thể quay lại pattern trước mà không thay đổi business logic.

### Một điểm cần kiểm soát khi nâng cấp framework

Framework hoặc instrumentation có thể đã quản lý MDC/tracing. Trước khi thêm filter mới, kiểm tra:

- Có đặt `trace_id`/`span_id` tự động chưa?
- Có request ID từ gateway/header nào được chấp nhận không?
- Có hook để đặt và cleanup context ở async dispatch không?
- Có cấu hình encoder xuất MDC/ThreadContext ra JSON không?
- Có nguy cơ hai filter dùng cùng một key nhưng khác ID không?

Tích hợp với cơ chế chuẩn của framework giúp tránh hai hệ thống request context cạnh tranh và giảm code tự viết có lỗi khó phát hiện.

## 17. Bài tập thực hành

### Bài 1 — Nhận biết field

Trong các giá trị sau, trường nào dùng để **nhóm theo loại sự kiện**, trường nào dùng để **truy một request**?

```text
event_code=payment.failed
request_id=req-81
trace_id=4bf92f3577b34da6a3ce929d0e0e4736
error_code=GATEWAY_TIMEOUT
```

**Đáp án:** `event_code` và `error_code` phù hợp để nhóm loại sự kiện/lỗi khi danh mục ổn định; `request_id` và `trace_id` để truy một lần xử lý hoặc một distributed trace. Không dùng các ID động làm nhãn metric không giới hạn.

### Bài 2 — Lỗi thread pool

Một request A đặt `MDC.put("request_id", "A")` rồi gọi `executor.submit`. Task chạy trên worker không có `request_id`. Vì sao?

**Đáp án:** MDC theo scope/thread hiện tại không tự lan truyền tới executor worker. Snapshot context ở nơi submit, truyền theo API propagation được hỗ trợ, áp tại worker rồi khôi phục trong `finally`.

### Bài 3 — Lẫn ID giữa hai request

Request A và request B được xử lý tuần tự trên cùng worker. B có log mang ID của A.

**Đáp án:** Nghiên cứu cleanup của A, cách scope được kết thúc khi exception/timeout, và việc worker giữ ThreadLocal/MDC cũ. Test hai request kế tiếp với thread pool kích thước một, assert không có bản ghi của B mang A.

### Bài 4 — `clear` hay `restore`?

Một hàm con cần đặt `operation_id` riêng nhưng gọi `MDC.clear()` khi ra khỏi hàm. Vì sao không tốt?

**Đáp án:** Nó có thể xóa `request_id` và `trace_id` của scope cha. Nên lưu context trước khi vào scope và khôi phục sau khi hoàn thành, hoặc chỉ `remove` key mình sở hữu nếu không cần nested replacement.

### Bài 5 — HTTP header không đáng tin

Client gửi `X-Request-ID` dài hàng chục nghìn ký tự, có newline và token. Có nên ghi nguyên header này làm ID?

**Đáp án:** Không. Giới hạn độ dài/charset, xác định trust boundary, tạo ID mới nếu không hợp lệ, không in header độc hại; bảo đảm encoder escape và không đưa secret vào log.

### Bài 6 — Trace ID khác request ID thế nào?

Một service A gọi B và C; mỗi service có thể nhận request ID nội bộ khác nhau nhưng chia sẻ cùng trace ID. Đây có phải lỗi không?

**Đáp án:** Không nhất thiết. `trace_id` có thể bao trùm cả hành trình phân tán, còn request ID theo hợp đồng có thể chỉ tồn tại ở một gateway/hop. Nếu muốn một ID truyền xuyên suốt, phải có chính sách propagation thống nhất; không tự ép hai loại ID thành một.

### Bài 7 — Chứng minh không leak context

Với chương trình Maven ở phần 5, giải thích vì sao dòng cuối có `rid=|trace=` và cách sửa test để phát hiện lỗi.

**Đáp án:** `handleRequest` khôi phục MDC trước scope, nên sau hai lần chạy không còn request context trên main thread. Dòng cuối là sự kiện ngoài request. Có thể bổ sung assertion ở appender test về `getMDCPropertyMap()` và gọi thêm task ngoài request trên cùng worker để chứng minh worker cũng không giữ ID cũ.

### Bài 8 — Structured logging

Ứng dụng dùng `%msg%n` và có `MDC.put("request_id","req-A")`, nhưng kho log không có trường `request_id`. Phải làm gì?

**Đáp án:** MDC không tự in khi pattern không dùng `%X` và encoder JSON chưa được cấu hình. Thêm converter `%X{request_id}` cho text hoặc cấu hình JSON encoder xuất MDC thành field riêng; kiểm tra output sau ingest.

### Bài 9 — Message consumer

Một message được retry ba lần. Các lần retry có cùng `message_id` nhưng `attempt` tăng. Có phải ba message nghiệp vụ khác nhau?

**Đáp án:** Chưa chắc. `message_id` định danh message theo broker/ứng dụng; `attempt` mô tả số lần xử lý. Cần phân biệt event `attempt_failed` và `processing_failed` cuối nếu muốn đếm số message thất bại.

## 18. Checklist trước khi đưa request context vào production

- [ ] Biết ID nào là request, trace, span, correlation, event; không dùng lẫn.
- [ ] Có một owner rõ ràng tạo/nhận request ID ở ranh giới hệ thống.
- [ ] Header từ client được validate và không bị coi là nguồn xác thực.
- [ ] Context chỉ chứa key-value nhỏ, được phép lưu và có format ổn định.
- [ ] Đặt context trước khi xử lý nghiệp vụ, cleanup hoặc restore ở `finally`.
- [ ] Nested scope không xóa nhầm context scope cha.
- [ ] Task qua executor/CompletableFuture được propagate và restore đúng.
- [ ] Reactive/message/scheduler có lifecycle và propagation riêng.
- [ ] Downstream service nhận tracing/correlation qua giao thức phù hợp, không dựa vào MDC giữa JVM.
- [ ] Logging backend/provider thực sự hỗ trợ MDC/ThreadContext.
- [ ] Pattern text hoặc encoder JSON xuất đúng các trường context.
- [ ] Mọi event cần thiết có mã sự kiện/level và request/trace ID tương ứng.
- [ ] Test hai request liên tiếp trên cùng worker, test exception và cancellation.
- [ ] Test log ngoài request không chứa ID cũ.
- [ ] Không đưa raw URL, token, cookie hoặc dữ liệu nhạy cảm vào MDC.
- [ ] JSON encoding xử lý đúng newline, quote và Unicode.
- [ ] Collector tìm được trace/request ID xuyên nhiều service, có retention/quyền đọc phù hợp.
- [ ] Metric không dùng ID động làm label cardinality không giới hạn.
- [ ] Không dùng context logging làm nơi ra quyết định bảo mật/nghiệp vụ.
- [ ] Có khả năng kiểm tra và rollback nếu schema/propagation thay đổi.

**Kết luận:** Request context biến các bản ghi rời rạc thành một hành trình có thể truy vết. Trọng tâm không chỉ là `MDC.put`, mà là **đặt context đúng ranh giới → propagate qua async/qua mạng → gắn field vào event → cleanup/restore ở mọi nhánh → xác minh output và collector**. Khi phạm vi và vòng đời được thiết kế rõ, log Java hỗ trợ điều tra hiệu quả mà không làm lẫn dữ liệu giữa các request.