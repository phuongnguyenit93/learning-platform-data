# Tenant context trong Java logging: gắn đúng tenant, không rò ngữ cảnh

## 1. Tenant context là gì?

Trong ứng dụng **multi-tenant**, một hệ thống phần mềm phục vụ nhiều tổ chức, khách hàng hoặc không gian dữ liệu được gọi là **tenant**. Cùng một dịch vụ Java và cùng một logger có thể xử lý request của `tenant-A`, `tenant-B` và hàng trăm tenant khác.

**Tenant context** là ngữ cảnh cho biết **lượt xử lý hiện tại đang liên quan tới tenant nào**, thường chứa một mã ổn định như `tenant_id`. Khi đưa vào logging, nó giúp kỹ sư phân biệt các sự kiện của nhiều tenant đi qua cùng một ứng dụng.

Ví dụ, nếu chỉ có:

```text
INFO  event=order_created order_id=ORD-101
WARN  event=payment_retry order_id=ORD-102
```

người vận hành chưa biết các đơn hàng thuộc tenant nào. Có tenant context:

```text
INFO tenant_id=tenant-A event=order_created order_id=ORD-101
WARN tenant_id=tenant-B event=payment_retry order_id=ORD-102
```

thì việc điều tra có thể được giới hạn theo tenant.

**Hai lưu ý cốt lõi:**

1. **Tenant context phục vụ quan sát và có thể hỗ trợ truyền ngữ cảnh nghiệp vụ**, nhưng **không phải cơ chế xác thực, phân quyền hay cô lập dữ liệu**. Không được cấp quyền truy cập database chỉ vì `MDC.get("tenant_id")` trả về một chuỗi.
2. **Ngữ cảnh cần đúng trong toàn bộ vòng đời và đúng thời điểm ghi log.** Nếu tenant của request trước còn sót trên một thread được tái sử dụng, hệ thống có thể ghi sai nhãn tenant cho request sau, tạo rủi ro an toàn và sai lệch điều tra.

Trong nhóm **Logging context**, tenant ID cần được xem là **trường dữ liệu động của từng sự kiện**, giống correlation ID hoặc request ID, chứ không phải tên logger, global constant hoặc tên service.

## 2. Phân biệt các loại context

| Dữ liệu | Cho biết điều gì? | Phạm vi thông thường |
| --- | --- | --- |
| `tenant_id` | Tenant liên quan tới thao tác | Request, message, job hoặc một đơn vị công việc |
| `request_id` | Một lần yêu cầu vào service | Một request |
| `correlation_id` | Một chuỗi thao tác có liên quan | Có thể xuyên nhiều service |
| `trace_id` / `span_id` | Dữ liệu tương quan theo distributed tracing | Trace và span |
| `user_id` / `actor_id` | Chủ thể thực hiện hành động | Người dùng hoặc service account |
| `service.name` | Tên dịch vụ logic | Thường ổn định trong một instance |
| `environment` | Môi trường chạy như staging/production | Deployment |
| `order_id` | Đối tượng nghiệp vụ đang xử lý | Một sự kiện hoặc chuỗi xử lý nghiệp vụ |
| `tenant_scope` | Một tác vụ thuộc một tenant hay nhiều tenant | Job hoặc event cụ thể |

**Tenant ID khác user ID.** Một user có thể là thành viên của nhiều tenant; một tenant có nhiều user. Khi người dùng chuyển workspace, tenant context của các request tiếp theo có thể khác dù `user_id` không đổi.

**Tenant ID khác trace ID.** Nhiều trace thuộc cùng tenant; một trace của gateway hoặc tác vụ quản trị còn có thể liên quan đến nhiều tenant. Không sử dụng một trace ID hoặc request ID làm đại diện cho tenant.

**Tenant ID khác service name.** Một instance `billing-service` có thể xử lý đồng thời nhiều tenant, nên không gắn tenant của request hiện tại vào **resource-level `service.name`** hoặc biến môi trường toàn cục của process.

Một sự kiện có thể được biểu diễn dưới dạng cấu trúc:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "INFO",
  "service": "order-service",
  "tenant_id": "tenant-A",
  "event": "order_created",
  "order_id": "ORD-101",
  "correlation_id": "req-7c"
}
```

Đây là **schema minh họa**, không phải output mặc định của một Java logging backend. Muốn xuất như vậy cần encoder/layout và pipeline collector tương ứng.

## 3. Tenant context phải có nguồn đáng tin

Một bài học về logging tenant không thể chỉ nói “lấy `X-Tenant-ID` trong HTTP header rồi ghi”. Trong ứng dụng multi-tenant, **chọn sai tenant từ nguồn không tin cậy vừa gây log giả vừa có thể báo hiệu lỗi phân quyền nghiêm trọng**.

Một luồng tham khảo:

```text
HTTP request / message / job
             |
             v
    Authentication boundary
   (token/session mTLS/identity)
             |
             v
    Tenant resolution + authorization
  - Tenant được yêu cầu là tenant nào?
  - Principal có quyền ở tenant đó không?
  - Tài nguyên có thuộc tenant đó không?
             |
             v
       Verified tenant ID
             |
             v
    Scoped tenant context
             |
             v
    Business code + logging
             |
             v
        Cleanup / restore
```

**Không tin mù quáng vào:**

- Header do client tự gửi như `X-Tenant-ID: tenant-admin`.
- Query parameter `?tenant=...` hoặc đường dẫn `/tenants/{tenantId}` khi chưa kiểm tra quyền.
- Cookie chưa được xác minh nguồn gốc.
- Giá trị `tenant_id` trong Baggage, MDC, trace metadata hoặc logging header từ service chưa được tin cậy.
- Dữ liệu trong LogEvent hay tên logger làm bằng chứng rằng request thực sự được ủy quyền.

Một nguyên tắc kiến trúc hợp lý:

1. Xác thực principal bằng cơ chế của ứng dụng.
2. Resolve tenant được yêu cầu bằng thông tin định danh và resource hợp lệ.
3. **Ủy quyền quyền truy cập tenant** và xác minh quan hệ tenant–resource ở tầng nghiệp vụ/DB phù hợp.
4. Chuẩn hóa mã tenant thành ID ổn định, giới hạn ký tự và độ dài.
5. Đặt mã **đã xác minh** vào logging context cho scope của công việc.
6. Xóa hoặc khôi phục context khi kết thúc.

Ví dụ `TenantContext.open(verifiedTenantId)` trong bài là một lời gọi **sau khi đã kiểm tra tenant**. Nó không tự làm bước kiểm tra quyền.

## 4. Scope: vì sao đặt rồi phải dọn?

Trong Java, nhiều cơ chế logging context sử dụng dữ liệu gắn với **thread**. Nếu một HTTP server có thread pool, một thread có thể lần lượt xử lý request của tenant A rồi tenant B.

Nếu chỉ đặt:

```java
// Minh họa lỗi: không có cleanup.
MDC.put("tenant_id", verifiedTenantId);
processRequest();
```

và quên `MDC.remove` hoặc khôi phục snapshot, request sau có thể kế thừa metadata cũ trên cùng thread, nhất là khi request sau đi qua nhánh lỗi trước khi đặt tenant mới.

Một scope an toàn cần:

- **Thiết lập** context sau khi tenant được xác minh.
- **Giữ** context trong các hàm cùng luồng cần ghi log.
- **Khôi phục giá trị cũ hoặc xóa key** sau scope, kể cả khi ném exception.
- **Không mở rộng scope** sang công việc của tenant khác.
- **Chuyển context tường minh** khi chuyển thread/async boundary.
- **Lấy snapshot đúng thời điểm** nếu cần ghi sự kiện bất đồng bộ.
- **Không tái sử dụng object context mutable** giữa những request độc lập.

Mẫu `try/finally` hoặc `try-with-resources` giúp giữ vòng đời rõ ràng:

```java
String previous = MDC.get("tenant_id");
MDC.put("tenant_id", verifiedTenantId);
try {
    processRequest();
} finally {
    if (previous == null) {
        MDC.remove("tenant_id");
    } else {
        MDC.put("tenant_id", previous);
    }
}
```

Đây là **đoạn minh họa trong một service đã có SLF4J và các biến/phương thức tương ứng**, không phải chương trình độc lập. Nó **khôi phục** context cũ khi scope lồng nhau; việc chỉ `remove` có thể xóa nhầm giá trị của scope bao ngoài.

**Chú ý:** nếu request boundary là nơi sở hữu toàn bộ MDC thì có thể quyết định `MDC.clear()` ở cuối request. Nhưng một thư viện con không nên gọi `MDC.clear()` tùy tiện vì có thể xóa trace/request ID và các trường khác do framework đặt.

## 5. Ví dụ Java 17+ độc lập: hai tenant dùng chung thread pool

Ví dụ này minh họa nguyên tắc **scope tenant context** bằng JDK thuần. Chương trình:

1. Có một `TenantContext` dùng `ThreadLocal<String>`.
2. Xử lý hai tenant lần lượt trong thread chính.
3. Gửi một tác vụ cho **cùng một worker thread** của `ExecutorService`.
4. **Chụp tenant ID ở thread gửi và đặt lại trong worker thread**.
5. Ghi LogRecord JUL với `tenant_id` được lấy tại **thời điểm tạo LogRecord**.
6. Tự động khôi phục context bằng `AutoCloseable`.
7. Cho stdout xác định để dễ kiểm tra rò tenant.

**Giới hạn:** ví dụ sử dụng hai tenant ID cố định đã được coi là hợp lệ trong bài tập. Nó **không thực hiện authentication/authorization**, không phải giải pháp tenant isolation production và không thay thế cấu hình MDC/ThreadContext khi dùng một logging backend thực tế.

Lưu toàn bộ mã thành **`TenantLoggingDemo.java`**:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.logging.Formatter;
import java.util.logging.Level;
import java.util.logging.LogRecord;
import java.util.logging.Logger;
import java.util.logging.StreamHandler;

public final class TenantLoggingDemo {
    private static final Logger LOG =
            Logger.getLogger(TenantLoggingDemo.class.getName());

    private TenantLoggingDemo() {
    }

    private static final class TenantContext {
        private static final ThreadLocal<String> CURRENT =
                new ThreadLocal<>();

        private TenantContext() {
        }

        static Scope open(String verifiedTenantId) {
            if (verifiedTenantId == null
                    || !verifiedTenantId.matches("[A-Za-z0-9_-]{1,32}")) {
                throw new IllegalArgumentException(
                        "Invalid tenant identifier");
            }

            String previous = CURRENT.get();
            CURRENT.set(verifiedTenantId);
            return new Scope(previous);
        }

        static String current() {
            return CURRENT.get();
        }

        static String required() {
            String tenant = CURRENT.get();
            if (tenant == null) {
                throw new IllegalStateException(
                        "Tenant context missing");
            }
            return tenant;
        }

        static final class Scope implements AutoCloseable {
            private final String previous;
            private final Thread owner;
            private boolean closed;

            private Scope(String previous) {
                this.previous = previous;
                this.owner = Thread.currentThread();
            }

            @Override
            public void close() {
                if (Thread.currentThread() != owner) {
                    throw new IllegalStateException(
                            "Close scope on owning thread only");
                }
                if (closed) {
                    return;
                }
                if (previous == null) {
                    CURRENT.remove();
                } else {
                    CURRENT.set(previous);
                }
                closed = true;
            }
        }
    }

    private static void event(String name, String orderId) {
        // Snapshot tenant ngay khi tạo LogRecord.
        LOG.log(Level.INFO,
                "event={0} tenant_id={1} order_id={2}",
                new Object[] {
                        name, TenantContext.required(), orderId
                });
    }

    private static void process(
            ExecutorService pool, String verifiedTenantId,
            String orderId) throws Exception {
        try (TenantContext.Scope request =
                     TenantContext.open(verifiedTenantId)) {
            event("order_received", orderId);

            // ThreadLocal không tự chuyển qua ExecutorService.
            String snapshot = TenantContext.required();

            Future<?> result = pool.submit(() -> {
                try (TenantContext.Scope task =
                             TenantContext.open(snapshot)) {
                    event("order_processed", orderId);
                }
            });
            result.get();
        }
    }

    public static void main(String[] args) throws Exception {
        LOG.setUseParentHandlers(false);
        LOG.setLevel(Level.INFO);

        Formatter formatter = new Formatter() {
            @Override
            public String format(LogRecord record) {
                return record.getLevel().getName() + " "
                        + formatMessage(record)
                        + System.lineSeparator();
            }
        };

        StreamHandler stdout =
                new StreamHandler(System.out, formatter);
        stdout.setEncoding("UTF-8");
        stdout.setLevel(Level.INFO);
        LOG.addHandler(stdout);

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            process(pool, "tenant-A", "ORD-101");
            process(pool, "tenant-B", "ORD-102");

            stdout.flush();
            System.out.println(
                    "main_context_cleared="
                    + (TenantContext.current() == null));
        } finally {
            pool.shutdown();
            LOG.removeHandler(stdout);
            stdout.flush();
            // Không close StreamHandler vì nó sẽ đóng System.out.
        }
    }
}
```

Từ thư mục chứa file, biên dịch và chạy với JDK 17+:

```bash
javac -encoding UTF-8 TenantLoggingDemo.java
java TenantLoggingDemo
```

**Stdout chính xác khi chương trình chạy bình thường:**

```text
INFO event=order_received tenant_id=tenant-A order_id=ORD-101
INFO event=order_processed tenant_id=tenant-A order_id=ORD-101
INFO event=order_received tenant_id=tenant-B order_id=ORD-102
INFO event=order_processed tenant_id=tenant-B order_id=ORD-102
main_context_cleared=true
```

**Stderr của ứng dụng:** không có bản ghi khi hoạt động bình thường. Chẩn đoán của JVM/môi trường hoặc lỗi I/O không thuộc đầu ra dự kiến.

### Phân tích từng quyết định

- `ThreadLocal<String>` lưu tenant theo thread hiện tại, không phải biến global được chia sẻ bởi mọi request.
- `TenantContext.open` kiểm tra hình thức mã tenant; **đây không phải xác minh quyền**. Trong ứng dụng thực, đầu vào phải được lấy từ kết quả resolve/authorize đáng tin.
- `Scope` nhớ giá trị trước đó và khôi phục khi đóng. Với scope lồng nhau đúng thứ tự LIFO, tenant của scope ngoài không bị xóa nhầm.
- `Scope` lưu `owner` để tránh bị đóng từ thread khác. Mỗi scope được đóng trong đúng thread nó mở.
- `TenantContext.required()` khiến một sự kiện bắt buộc có tenant không thể âm thầm ghi bằng context `null`.
- `event(...)` đưa tenant ID vào **đối số bất biến của LogRecord** tại lúc gọi. Nó không trông chờ Formatter chạy sau này vẫn đọc được ThreadLocal cũ.
- `Executors.newSingleThreadExecutor()` có một worker được **tái sử dụng** cho cả tenant A và tenant B. Worker không dựa vào việc tự kế thừa ThreadLocal; task tự thiết lập scope từ snapshot.
- `Future.get()` chờ tác vụ xong, nên thứ tự năm dòng stdout được xác định.
- `StreamHandler(System.out, formatter)` ghi stdout khi flush; JUL `ConsoleHandler` mặc định ghi stderr và không phù hợp nếu muốn chứng minh đầu ra stdout.
- `LOG.setUseParentHandlers(false)` tránh một LogRecord cũng đi qua handler cha gây bản ghi trùng.
- `stdout.flush()` trước `println` giúp giữ thứ tự quan sát; không được suy ra log đã lưu bền ở collector.
- Không đóng `StreamHandler` trong demo, vì `StreamHandler.close()` sẽ đóng `System.out` dùng chung cho tiến trình.

### Những gì demo không chứng minh

Chương trình **không** bảo đảm tenant isolation ở database, không mô phỏng request mang token thật, không kiểm thử logging backend async hay hệ thống distributed tracing, và không chứng minh tính bền của một log collector. Nó chỉ chứng minh: **hai tenant có thể dùng chung một worker thread mà từng log event vẫn nhận đúng tenant ID nếu context được truyền và dọn đúng**.

## 6. Tại sao không đọc ThreadLocal trong Formatter bất đồng bộ?

Đây là một bẫy tinh vi. Giả sử code ghi:

```java
// Ý tưởng nguy hiểm khi formatter có thể chạy ở thread khác:
String tenant = TenantContext.current();
```

Nếu đó là code trong một Formatter/Encoder được thực thi **sau này** ở thread xử lý logging async, ThreadLocal được đọc thuộc về **thread formatter**, không nhất thiết là thread tạo sự kiện. Hậu quả: tenant có thể rỗng hoặc sai.

Cách đúng về nguyên tắc:

1. **Chụp tenant khi phát sự kiện** trên thread đã được gắn context.
2. **Gắn tenant vào LogEvent/LogRecord** hoặc structured key-value/metadata được backend hỗ trợ.
3. Để async appender/encoder tuần tự hóa **dữ liệu đã được chụp**, thay vì đọc một request-scoped ThreadLocal bất kỳ khi consumer chạy.
4. Kiểm thử với backend đang dùng, vì cách snapshot context data và thời điểm chuẩn bị event tùy logging implementation.

Ví dụ `event(...)` trong bài tạo LogRecord có **tham số chứa tenant ID**, nên Formatter không phải truy cập `TenantContext.current()` để lấy tenant.

**Không dựa vào một giả định “mọi logging framework tự chụp MDC giống nhau ở mọi chế độ”.** Một số backend tối ưu async, memento, reusable events hoặc custom encoder theo cách khác nhau. Cần kiểm tra dữ liệu tenant trong log thực và behavior khi queue/backpressure.

## 7. SLF4J MDC: tenant_id trong API ghi log

Trong nhiều ứng dụng Java sử dụng SLF4J + Logback hoặc provider hỗ trợ MDC, **Mapped Diagnostic Context (MDC)** là cách phổ biến để đưa tenant ID vào nhiều dòng log cùng scope.

```java
import org.slf4j.MDC;

// verifiedTenantId đã được xác minh ở tầng authentication/authorization.
try (MDC.MDCCloseable ignored =
             MDC.putCloseable("tenant_id", verifiedTenantId)) {
    LOG.info("event=order_received order_id={}", orderId);
    LOG.info("event=order_completed order_id={}", orderId);
}
```

Đây là **snippet trong một lớp có `LOG` kiểu SLF4J**, không chạy độc lập. `putCloseable` tạo scope và khi đóng sẽ **xóa key tenant_id** trong MDC. **Nó không tự khôi phục giá trị cũ của cùng key** nếu scope được lồng trên một scope trước đó.

Với nested scope, dùng mẫu nhớ/khôi phục giá trị:

```java
String previous = MDC.get("tenant_id");
MDC.put("tenant_id", verifiedTenantId);
try {
    processTenantWork();
} finally {
    if (previous == null) {
        MDC.remove("tenant_id");
    } else {
        MDC.put("tenant_id", previous);
    }
}
```

Nếu hàm này là một thư viện con, nó không nên `MDC.clear()` vì có thể xóa `trace_id`, `request_id` hoặc metadata do request filter đặt.

### MDC không có nghĩa backend luôn hiển thị tenant

Nếu dùng **Logback PatternLayout**, có thể cấu hình:

```xml
<pattern>%d{ISO8601} %-5level tenant_id=%X{tenant_id} %logger - %msg%n</pattern>
```

Đây là **snippet của pattern trong encoder Logback**, không phải toàn bộ `logback.xml`. Phải có Logback provider, Console/File Appender và pattern encoder phù hợp.

Nếu backend dùng encoder JSON, cần xác nhận **MDC được đưa thành một trường JSON `tenant_id`**. Có những encoder đưa MDC vào object lồng nhau, có encoder cần whitelist, và có provider rất đơn giản không xuất MDC. Một lời gọi `MDC.put` thành công **không chứng minh log collector sẽ có trường tenant**.

### MDC là công cụ hỗ trợ logging, không phải TenantResolver

`MDC.get("tenant_id")` chỉ lấy một giá trị đã được đặt trong ngữ cảnh. **Không sử dụng nó như nguồn sự thật cho authorization, tenant-aware SQL filtering hoặc billing.** Đường nghiệp vụ nên nhận một đối tượng tenant/principal đã được xác minh và sử dụng thông qua API phân quyền tường minh. Việc đồng bộ tenant ID ấy vào MDC chỉ phục vụ quan sát.

## 8. Truyền MDC qua ExecutorService

SLF4J MDC thường gắn với ngữ cảnh của thread hiện tại theo adapter/backend. Khi gửi tác vụ sang pool, **không nên mặc định MDC sẽ tự truyền**. Có thể chụp snapshot của MDC từ thread nguồn:

```java
Map<String, String> captured = MDC.getCopyOfContextMap();

executor.submit(() -> {
    Map<String, String> oldWorker =
            MDC.getCopyOfContextMap();
    try {
        if (captured == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(captured);
        }
        performWork();
    } finally {
        if (oldWorker == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(oldWorker);
        }
    }
});
```

Đây là **mẫu minh họa** trong lớp đã import `java.util.Map` và `org.slf4j.MDC`, có `executor`/`performWork`. Những điểm cần hiểu:

- `getCopyOfContextMap()` tạo **bản sao**; nó có thể trả `null`.
- Snapshot là dữ liệu từ **thời điểm submit**, không phải một tham chiếu đến map được cập nhật sau này.
- Bên worker có thể mang metadata tồn tại trước đó; ví dụ **lưu và khôi phục** map đó, thay vì giữ dữ liệu từ task trước.
- `MDC.setContextMap(...)` thay thế toàn bộ context map của thread gọi, không chỉ đổi một key. Mẫu này cần có **quyền sở hữu context** rõ ràng khi áp dụng ở framework.
- Nếu task tạo các tác vụ con khác trên thread mới, cần xử lý propagation tại **mỗi async boundary**.
- Snapshot có thể chứa thông tin không nên chuyển tới task khác; cần kiểm soát field được phép truyền và trust boundary.

Trong dự án thực, nếu framework cung cấp **task decorator, context propagation library hoặc instrumentation** phù hợp thì nên dùng cơ chế đã được kiểm thử thay vì sao chép snippet ở khắp nơi. Nhưng vẫn phải hiểu mô hình snapshot–restore để tránh rò context.

## 9. Log4j2 ThreadContext: tenant map của một scope

Trong Log4j2, `org.apache.logging.log4j.ThreadContext` cung cấp **Thread Context Map** (giống MDC) và **Thread Context Stack** (NDC). Để gắn tenant ID:

```java
import org.apache.logging.log4j.ThreadContext;

String old = ThreadContext.get("tenant_id");
ThreadContext.put("tenant_id", verifiedTenantId);
try {
    LOG.info("event=order_created order_id={}", orderId);
} finally {
    if (old == null) {
        ThreadContext.remove("tenant_id");
    } else {
        ThreadContext.put("tenant_id", old);
    }
}
```

Đây là **snippet trong lớp dùng Log4j2 API**. Trong `PatternLayout` có thể in tenant:

```xml
<PatternLayout charset="UTF-8"
    pattern="%d{ISO8601} %-5p tenant_id=%X{tenant_id} %c{1} - %m%n"/>
```

Đây là **Layout XML nằm bên trong một Appender**, không phải file `log4j2.xml` hoàn chỉnh.

### CloseableThreadContext

Log4j2 có API `CloseableThreadContext`:

```java
try (CloseableThreadContext.Instance ignored =
             CloseableThreadContext.put(
                     "tenant_id", verifiedTenantId)) {
    LOG.info("event=order_created order_id={}", orderId);
}
```

Cần import `org.apache.logging.log4j.CloseableThreadContext`. Cách này cung cấp **scope quản lý tự động** cho Thread Context. Khi lồng scope hoặc kết hợp với code của framework, nên kiểm thử đúng hành vi khôi phục theo phiên bản/backend và tránh việc code ngoài scope sửa cùng một key không có quy ước.

### Thread pool với Log4j2

Tài liệu Log4j2 mô tả việc chụp `ThreadContext.getImmutableContext()` rồi dùng `CloseableThreadContext.putAll(...)` trong worker. Ý tưởng:

```java
Map<String, String> snapshot =
        ThreadContext.getImmutableContext();

executor.submit(() -> {
    try (CloseableThreadContext.Instance ignored =
                 CloseableThreadContext.putAll(snapshot)) {
        LOG.info("event=async_work_started");
        performWork();
    }
});
```

Đây là **snippet** cần import `java.util.Map` và các lớp Log4j2. `ThreadContext` và `MDC` không có nghĩa một hệ thống async bất kỳ sẽ tự chuyển dữ liệu. Với backend hoặc bridge khác nhau, mức độ hỗ trợ cũng có thể khác; luôn kiểm tra output thực.

Tài liệu Apache: https://logging.apache.org/log4j/2.x/manual/thread-context.html

## 10. Thread pool, virtual thread, reactive và CompletableFuture

### Thread pool và task reuse

Một request có thể chạy trên worker thread đã từng xử lý tenant khác. Vì thế cần **clear/restore trong `finally`**, không chỉ đặt tenant lúc thread mới sinh. Test tối thiểu: task A có tenant A, task B trên **cùng worker** có tenant B, task C không có tenant và phải không được ghi nhãn A/B.

### CompletableFuture

`CompletableFuture.supplyAsync(...)` và `thenApplyAsync(...)` có thể chạy trên những executor/thread khác. Nếu chỉ đặt `MDC.put` trước `supplyAsync`, không bảo đảm callback sẽ có context đó.

Cách thiết kế:

- Chụp **ID tenant đã xác minh** hoặc context snapshot ở điểm tạo task.
- Tại **mỗi callback async cần tenant**, mở một scope trong callback và đóng trong `finally`.
- Không giữ ThreadLocal scope từ thread submit rồi đóng scope ở thread worker; scope cần được tạo/đóng trong **cùng thread**.
- Với callback chạy inline (`thenApply`) hoặc đổi thread tùy thời điểm completion, vẫn cần thiết kế rõ ai sở hữu context.
- Khi fan-out nhiều tác vụ, truyền snapshot immutable thay vì chia sẻ một map mutable.

### Virtual threads trong JDK 21+

Virtual thread giúp tạo nhiều tác vụ nhẹ, nhưng **không thay thế khái niệm context scope**. ThreadLocal vẫn gắn với thread hiện tại; chuyển một request sang một virtual thread khác không có nghĩa context của thread nguồn tự chuyển đúng như kỳ vọng. Thiết kế truyền context tường minh hoặc dùng abstraction của framework; không dựa vào default của `InheritableThreadLocal` để sửa mọi trường hợp.

Bài chạy chính dùng **Java 17**, không yêu cầu virtual threads.

### Reactive programming

Với Reactor, RxJava hoặc các luồng reactive khác, callback có thể thực thi trên nhiều thread. **ThreadLocal không phải luôn là nơi lưu context đúng cho toàn bộ chuỗi xử lý.** Với Project Reactor, một thiết kế thường dùng **Reactor Context** và bridge/context propagation tích hợp phù hợp, thay vì đặt MDC một lần ở thread nhận request rồi hy vọng nó theo mọi tín hiệu.

**Nguyên tắc chung:** context phải đi theo **đơn vị công việc**, không mặc định đi theo một OS/JVM thread suốt cả request.

## 11. Tenant trong scheduled job, message consumer và batch

HTTP request không phải nguồn duy nhất tạo log. Một hệ thống SaaS có thể chạy:

- Scheduler xử lý dữ liệu của tenant A mỗi giờ.
- Message consumer nhận `order_created` từ hàng đợi.
- Retry worker xử lý lại một đơn hàng cũ.
- Nightly batch chạy lần lượt qua nhiều tenant.
- Tác vụ quản trị toàn hệ thống không thuộc một tenant cụ thể.

### Message consumer

Giả sử một message có `tenant_id`. **Đọc trường không đồng nghĩa tenant đã được tin cậy.** Consumer cần:

1. Xác minh nguồn phát/identity và quyền của sender theo thiết kế hệ thống.
2. Resolve tenant của message và xác minh quan hệ với tài nguyên hoặc event.
3. Mở tenant scope trong **phạm vi xử lý message**.
4. Đưa tenant ID vào các sự kiện có giá trị vận hành.
5. Đóng scope dù xử lý thành công, retry hay đưa vào dead-letter queue.
6. Truyền tenant/trace metadata có chính sách khi sinh message mới.

Một message sai tenant có thể là lỗi bảo mật, bug định tuyến hoặc dữ liệu bị hỏng; không chỉ là “thiếu trường log”.

### Batch nhiều tenant

Nếu một job lặp qua tenant A rồi tenant B:

```text
job started (scope toàn hệ thống)
  |
  +-- scope tenant A -> tenant A events -> close
  |
  +-- scope tenant B -> tenant B events -> close
  |
job completed (scope toàn hệ thống)
```

Không gắn một `tenant_id` bất kỳ cho toàn bộ batch. Những sự kiện toàn hệ thống có thể dùng `scope_type=SYSTEM` hoặc `tenant_scope=MULTI` **nếu schema đã quy định**; những sự kiện làm việc với từng tenant nên có scope tenant chính xác.

Một task quản trị có quyền thao tác nhiều tenant **không nên** dùng logging context làm cơ chế vượt qua tầng authorization. Quyền của actor và tenant mục tiêu cần được xác minh bằng dữ liệu nghiệp vụ đáng tin cậy.

### Retry, DLQ và replay

Khi retry, tenant context phải gắn với **đơn vị công việc được retry**, không phải request mới nhất hoặc tenant của worker đang rảnh. Đồng thời `message_id`, `attempt`, `reason_code` nên được ghi để người vận hành phân biệt nhiều lần thử cùng một việc. Một giao dịch có thể tạo nhiều dòng log; không đếm số log thành công làm số giao dịch chính thức.

## 12. Tenant ID trong JSON structured logging

Một event có thể được mô tả bằng JSON như:

```json
{
  "timestamp": "2026-11-09T12:00:00Z",
  "level": "WARN",
  "service": "billing-service",
  "tenant_id": "tenant-B",
  "event": "invoice_retry_scheduled",
  "invoice_id": "INV-7",
  "attempt": 2,
  "reason_code": "UPSTREAM_TIMEOUT",
  "trace_id": "b3c9a1"
}
```

Đây là **schema ứng dụng minh họa**. Để pipeline tìm được `tenant_id` như field, cần **backend/encoder/collector** thực sự lưu field đó, không chỉ in text `tenant_id=...`.

So sánh:

```text
WARN tenant_id=tenant-B event=invoice_retry_scheduled
```

với object JSON ở trên:

- Text dễ đọc trực tiếp, nhưng collector có thể phải tách trường.
- JSON giúp giữ field/type rõ hơn nếu encoder đúng, nhưng **chỉ khi parser thật sự giải mã và lập chỉ mục**.
- Một số hệ thống ghi MDC vào `contextMap` hoặc một object lồng nhau, không phải root `tenant_id`. Query cần đúng đường field.
- Nếu `tenant_id` bị bỏ trống trong encoder, việc đã gọi `MDC.put` không làm nó xuất hiện một cách kỳ diệu.
- Nếu tenant ID có ký tự đặc biệt, JSON encoder phải escape đúng, và chương trình cần giới hạn đầu vào để tránh dữ liệu không đáng tin.

Với Log4j2 có thể dùng `JsonTemplateLayout` từ artifact `log4j-layout-template-json`, cấu hình template có resolver/context fields tương ứng; với Logback chọn JSON encoder phù hợp. Không khẳng định template mặc định của mọi backend có cùng field hoặc path.

### Trường có kiểu ổn định

`tenant_id` thường là **string identifier**, kể cả khi giá trị nhìn giống số. Dùng `"tenant_id":"000123"` sẽ giữ được số 0 đầu, còn number `123` không có tính chất đó.

Đừng biến `tenant_id` thành tên JSON key, như `"tenant-A":true`, vì tạo **schema biến động không giới hạn**. Tenant nên là một **giá trị của field có tên ổn định**.

## 13. Tenant ID và cardinality: index/labels/metrics

Trong hệ thống log tập trung, tenant có thể rất nhiều. **High cardinality** là đặc điểm một trường có nhiều giá trị phân biệt. Việc đưa tenant ID vào structured log có thể hữu ích, nhưng **không đồng nghĩa nên đưa nó vào mọi indexed label**.

### Ví dụ với Loki

Loki thường tổ chức log streams bằng tập nhãn (*labels*). Nếu mỗi `tenant_id`, `request_id` hoặc `order_id` đều trở thành một indexed label, số tổ hợp nhãn có thể tăng rất nhanh và gây chi phí/hiệu năng xấu.

Phương án thường hợp lý:

- Labels có số giá trị tương đối nhỏ: `service`, `environment`, `cluster` hoặc `namespace`.
- `tenant_id` để trong log body hay **structured metadata** nếu kiến trúc và phiên bản hỗ trợ, rồi truy vấn bằng cơ chế phù hợp.
- Chỉ dùng tenant làm label nếu đã đo cardinality, có nhu cầu rõ và được vận hành chấp thuận.

**Không coi “tenant_id phải query được” đồng nghĩa “tenant_id phải là label index”.** Các backend có chiến lược indexing, phân vùng và structured metadata khác nhau.

### Metrics và tracing

Một metric như `http_requests_total{tenant_id="..."}` có thể nổ số chuỗi thời gian khi số tenant lớn. Không đem quy tắc log sang metric mà bỏ qua cardinality.

Với tracing, tenant ID có thể là span attribute khi phù hợp với chính sách dữ liệu, nhưng không tự xuất hiện trong mọi span chỉ vì MDC có `tenant_id`. Cần instrumentation/processor thêm attribute một cách chủ động và cân nhắc quyền riêng tư.

## 14. OpenTelemetry: baggage không phải tenant authorization

OpenTelemetry có các khái niệm:

- **Span context** như trace/span IDs để tương quan.
- **Baggage**: key-value có thể được truyền qua process/service boundary.
- **Span/log attributes**: metadata được gắn vào telemetry data.
- **Resource**: metadata của thực thể phát telemetry như `service.name`.

Một ứng dụng có thể muốn truyền tenant context giữa các service qua header hoặc Baggage. Điều này cần rất thận trọng:

1. Baggage có thể được **tự động truyền tiếp** qua những network calls do instrumentation thực hiện.
2. Baggage có thể đến từ **nguồn không tin cậy** hoặc bị sửa; **không có built-in integrity check** để đảm bảo đây là tenant đã xác minh.
3. Không đưa secret hoặc PII không cần thiết vào Baggage; dữ liệu có thể bị chuyển tới third-party endpoint.
4. Dữ liệu trong Baggage **không tự biến thành log/span attribute** nếu instrumentation không bổ sung.
5. Trace context hỗ trợ chẩn đoán, **không cấp quyền truy cập tenant**.
6. Khi service nhận Baggage, phải đối chiếu lại với identity và authorization của request/message.
7. Nếu nhiều tenant dùng chung service instance, tenant động không nên bị gán thành `service.name` hoặc một resource attribute có nghĩa toàn tiến trình.
8. Nếu cần propagation, dùng ID ổn định, giới hạn kích thước, xem xét chỉ truyền trong trusted boundary và không rò sang dịch vụ ngoài.

**Ví dụ sai về mặt bảo mật:** lấy `baggage.tenant_id` từ request công khai rồi dùng nó để lọc SQL, hoặc dùng làm bằng chứng rằng caller có quyền đọc đơn hàng của tenant đó.

**Ví dụ đúng về ý tưởng:** identity đã được xác thực và kiểm tra quyền xác định tenant A; code lưu tenant A trong đối tượng nghiệp vụ tin cậy, đồng thời gắn tenant A vào logging context và chỉ truyền những metadata được phép qua đường distributed tracing.

Tài liệu OpenTelemetry về rủi ro Baggage: https://opentelemetry.io/docs/concepts/signals/baggage/

## 15. Tenant context và ranh giới bảo mật dữ liệu

Một field `tenant_id` trong log không thay thế được những cơ chế như:

- Authentication và token validation.
- Authorization theo tenant và từng tài nguyên.
- Tenant-aware query hoặc row-level security được thiết kế/kiểm tra đúng.
- Tách database/schema/storage theo kiến trúc.
- Access control của log viewer và index.
- Kiểm soát đường xuất log, secret và retention.

### Không dùng MDC làm security principal

Ví dụ phản diện:

```java
// Sai về mô hình an ninh: MDC là metadata, không phải bằng chứng quyền.
String tenantId = MDC.get("tenant_id");
repository.findAllByTenantId(tenantId);
```

Đây là **mã minh họa nguy hiểm**, không phải giải pháp nên triển khai. Bất kỳ code nào có thể đặt MDC trong cùng luồng đều có thể làm thay đổi giá trị; hơn nữa một context bị rò từ request trước có thể khiến query được xây với tenant sai.

Tầng nghiệp vụ nên dùng một đối tượng **VerifiedTenant/AuthenticatedPrincipal** từ boundary tin cậy, với chính sách quyền rõ ràng. Chỉ sau đó đồng bộ một trường an toàn (ví dụ opaque ID) vào log context.

### Log viewer phải có quyền riêng

Một hệ thống search log dùng chung có thể chứa sự kiện của hàng nghìn tenant. **Filter ở giao diện** kiểu `tenant_id=tenant-A` không tự bảo đảm người dùng không xem được log tenant B. Nếu tenant tự xem log, phải có cơ chế authorization của **kho log và API truy vấn**, xử lý đúng người dùng/tenant, không chỉ CSS hoặc dropdown.

Tenant ID được lưu trong log còn có thể là dữ liệu nhạy cảm theo chính sách tổ chức. Cần xem xét pseudonymization, hạn chế khả năng liên kết với người dùng hoặc công ty cụ thể và thời gian lưu trữ.

## 16. Chọn một mã tenant phù hợp để ghi

Một mã tenant tốt cho logging thường:

1. **Ổn định** trong thời gian cần điều tra.
2. **Không hiển thị thông tin nhạy cảm** như email, số điện thoại hoặc tên khách hàng đầy đủ.
3. **Có dạng chuẩn và giới hạn độ dài**, ví dụ opaque ID hoặc slug nội bộ đã được kiểm soát.
4. **Không dễ gây log injection**, không chứa newline/control characters.
5. **Không dễ nhầm với user ID** hoặc service ID.
6. **Nhất quán qua các service** trong cùng pipeline.
7. **Có quy tắc xử lý tenant bị xóa/merge/split** để log lịch sử còn có thể được hiểu.
8. **Không bị tái sử dụng cho tenant khác** nếu nó là ID được dùng để audit/truy vấn lịch sử.
9. **Có chính sách mapping** khi hệ thống upstream và downstream dùng namespace tenant khác nhau.

Không nhất thiết mọi tenant ID phải là UUID, nhưng nếu dùng numeric ID trong JSON nên cân nhắc xuất **string** để bảo toàn định danh và tránh parser chuyển kiểu.

**Đặc biệt tránh** đưa tên đầy đủ của tổ chức hoặc dữ liệu người dùng vào một tag hiển thị công khai. Opaque tenant ID giúp giảm lộ thông tin nhưng không tự động làm dữ liệu vô hại; kho log vẫn có thể liên kết ID với tài khoản cụ thể.

## 17. Tenant context và các mức log

`tenant_id` là một **trường ngữ cảnh**, không phải mức `INFO`, `WARN` hoặc `ERROR`. Mức log phải phản ánh tình huống kỹ thuật/nghiệp vụ, không dựa trên “tenant này là khách hàng quan trọng” nếu chưa có chính sách vận hành được kiểm soát.

Ví dụ:

| Tình huống | Mức log tham khảo | Trường tenant cần có? |
| --- | --- | --- |
| Order được tạo thành công | `INFO` | Có, nếu sự kiện thuộc tenant và policy cho phép |
| Từ chối theo rule hợp lệ | `INFO` | Có, để phân biệt nguồn |
| Cache không dùng được, fallback thành công | `WARN` hoặc `DEBUG` tùy vận hành | Có nếu ảnh hưởng tenant |
| Thanh toán thất bại ngoài dự kiến | `ERROR` tại ranh giới xử lý | Có, nhưng không ghi dữ liệu thẻ/token |
| App startup trước khi có request | `INFO` | Không, đây là sự kiện toàn hệ thống |
| Background task xử lý nhiều tenant | Tùy sự kiện | Per-tenant log có ID, summary dùng `scope_type=SYSTEM` hoặc `MULTI` theo schema |
| Authentication thất bại trước khi xác minh tenant | `INFO`/`WARN` theo chính sách | Không gán tenant từ header chưa tin cậy |

**Không ép có tenant ID cho mọi LogEvent.** Log khởi động ứng dụng, cấu hình global hoặc lỗi hệ thống trước authentication có thể không có tenant cụ thể. Điều quan trọng là phân biệt **“không có tenant vì không áp dụng”** với **“thiếu tenant do bug ở request đã được xác minh”**.

Một schema tốt có thể quy định:

- Với `event=order_created`, `tenant_id` **bắt buộc**.
- Với `event=service_started`, `tenant_id` **không áp dụng**.
- Với `event=auth_rejected`, không lấy tenant ID từ dữ liệu client chưa xác minh; nếu cần có `requested_tenant_id` thì phải đánh dấu là **untrusted** và có chính sách riêng.

## 18. Propagation xuyên service và thông điệp

Với một request đi từ API gateway qua `order-service` tới `billing-service`:

```text
Caller
  |
  v
Gateway (authenticate + authorize)
  |
  v
Order service ----> Billing service
  |                        |
  v                        v
Log tenant_id=tenant-A   Log tenant_id=tenant-A
  |                        |
  +------------+-----------+
               |
               v
       Central log collector
```

Để đạt cùng tenant ID đáng tin:

1. Gateway phải xác minh identity và quyền của tenant được yêu cầu.
2. Downstream phải có **trust model**: xác minh service caller, token/delegation hoặc chính sách xác thực lại, không lấy header từ Internet làm sự thật.
3. Tầng giao tiếp truyền tenant identity/context bằng cơ chế đã được hệ thống phê duyệt; không tự thêm một header công khai rồi tin tất cả.
4. Từng service resolve/verify tenant phù hợp quyền của nó trước khi xử lý.
5. Logging layer lấy tenant **đã verify** trong scope của từng service.
6. Nếu có trace_id/correlation_id, dùng để liên kết các bản ghi mà không lấy nó làm bằng chứng quyền tenant.
7. Trên async/message boundary, message phải mang đủ metadata nghiệp vụ và quyền đã được thiết kế để có thể kiểm tra/resolve lại.
8. Khi response hoàn tất, request context được đóng; callback/tác vụ tồn tại lâu hơn phải có scope độc lập.

### Không truyền toàn bộ MDC một cách mù quáng qua mạng

MDC có thể chứa `user_id`, thông tin request, header đã bị sanitize hoặc các trường nội bộ. **Không sao chép toàn bộ MDC thành HTTP headers** rồi gửi tới bên thứ ba. Chọn whitelist của những trường được phép propagation, đi qua cơ chế bảo mật thích hợp, và biết điểm nào là trust boundary.

## 19. Kiểm thử chống rò tenant context

Khi thay đổi filter, middleware, executor hoặc logging backend, cần **kiểm thử đồng thời lẫn bất đồng bộ**. Các ca sau có giá trị cao:

| Ca thử | Mong đợi |
| --- | --- |
| Request A, tenant A | Mọi event tenant-scoped có `tenant_id=A` |
| Sau A, request B trên **cùng worker** | Event của B chỉ mang `tenant_id=B`, không phải A |
| Request thiếu tenant sau khi worker từng xử lý A | Không tự gán A; trả lỗi hoặc log theo chính sách xác thực |
| Exception giữa handler | `finally` vẫn khôi phục/clear context |
| Return sớm | Scope tự đóng qua `try-with-resources` |
| Hai scope lồng nhau A → B → A | Sau scope B, context quay lại A |
| ExecutorService có task sau completion | Context mới không kế thừa context cũ |
| CompletableFuture nhiều callback | Mỗi callback có tenant đúng nếu cần |
| Callback chạy trên thread khác | Tenant không được suy ra bằng ThreadLocal của submitter |
| Scheduler chạy job nhiều tenant | Event per-tenant đúng, summary không mạo nhận tenant |
| Message có tenant giả mạo | Không tin metadata chưa xác minh; authorization từ chối |
| Request thuộc tenant A nhưng resource thuộc B | Tầng nghiệp vụ từ chối; không bị logging context che lỗi |
| MDC adapter/backend thay đổi | Field tenant vẫn xuất hiện khi pipeline yêu cầu |
| JSON encoder gặp dấu nháy/newline | Một event JSON hợp lệ, không bị chẻ thành nhiều event |
| Collector không parse MDC | Test ingestion thất bại để phát hiện sớm |
| Trace/Baggage đi ra third-party | Không rò tenant metadata trái chính sách |
| Log viewer query tenant khác | Bị từ chối bởi authorization ở API/kho log |
| Tenant ID cardinality cao | Không tạo số indexed labels/metrics series vượt giới hạn |
| Logging queue async và load lớn | Không nhầm tenant giữa các sự kiện; đánh giá drop/backpressure |
| Thread context bị disabled trong runtime | Tín hiệu kiểm thử/giám sát phát hiện thiếu tenant field |

### Test một worker tái sử dụng

Ví dụ phần 5 minh họa hai tenant chạy trên **một thread pool chỉ có một worker**. Đây là test rất đáng có bởi bug rò MDC thường không xuất hiện khi mỗi request dùng một thread mới, nhưng xuất hiện ngay khi thread được tái sử dụng.

### Test nested scope

Trong một phương thức có `TenantContext.open("tenant-A")`, mở scope phụ `tenant-B` nếu thật sự được quyền thực hiện hoạt động cross-tenant, sau đó xác nhận khi thoát scope phụ, context trở lại A. Phải nhớ **logging context restore không cấp quyền cross-tenant**; test authorization và resource ownership vẫn độc lập.

### Test với collector thật

Một pattern có `%X{tenant_id}` có thể hiển thị ID trong terminal, nhưng collector có thể lưu thành raw message không có field riêng. Kiểm tra bằng truy vấn thực `tenant_id=tenant-A` và xác nhận backend lưu kiểu trường, vị trí và quyền truy cập đúng.

## 20. Những lỗi phổ biến cần tránh

**1. Đọc tenant từ header rồi tin ngay.** Client có thể giả mạo metadata. Tenant phải được resolve/authorize từ nguồn đáng tin.

**2. Dùng MDC làm căn cứ SQL authorization.** Logging context không phải security principal hoặc tenant isolation.

**3. Đặt tenant trong biến `static` mutable.** Nhiều request đồng thời có thể overwrite lẫn nhau.

**4. Không xóa MDC/ThreadContext trong `finally`.** Thread pool reuse khiến request sau có thể mang tenant ID của request trước.

**5. Chỉ gọi `MDC.putCloseable` trong scope lồng nhau rồi nghĩ nó khôi phục giá trị cũ.** SLF4J MDCCloseable **remove key** khi close, không tự restore previous value.

**6. Tạo scope trên thread A rồi close trên thread B.** Scope gắn với execution context phải được mở/đóng đúng phạm vi; ví dụ Java 17 có kiểm tra thread owner.

**7. Tin ThreadLocal tự truyền qua ExecutorService.** Phải chụp và áp context trong worker hoặc dùng cơ chế propagation framework.

**8. Đọc ThreadLocal lúc async formatter xử lý.** Thread formatter có thể khác thread tạo sự kiện; nên chụp context vào LogEvent.

**9. Copy toàn bộ MDC qua HTTP headers.** Có thể lộ secret/PII hoặc làm sai trust boundary; whitelist field cần thiết.

**10. Coi Baggage là bằng chứng quyền tenant.** OpenTelemetry Baggage không có integrity check mặc định và có thể đến từ nguồn không tin cậy.

**11. Dùng tenant ID làm logger name.** Tạo rất nhiều logger; giữ logger theo lớp/service, tenant là metadata của LogEvent.

**12. Đưa tenant vào `service.name` của tài nguyên telemetry dùng chung.** Resource của một instance có thể phục vụ nhiều tenant, không nên thay đổi động theo request.

**13. Đưa `tenant_id` thành mọi indexed label và metric dimension.** Có thể làm nổ cardinality; đo và chọn structured metadata/attributes phù hợp.

**14. Ghi tên khách hàng/email thay opaque tenant ID.** Tăng rủi ro dữ liệu nhạy cảm và khả năng liên kết log với người thật.

**15. Chỉ kiểm tra console text có tenant nhưng không kiểm tra JSON collector.** Encoder có thể bỏ MDC hoặc đặt field ở path khác.

**16. Gắn tenant của request hiện tại cho toàn bộ batch đa tenant.** Mỗi đơn vị công việc phải có scope đúng, summary toàn hệ thống không nên mạo nhận tenant.

**17. Chỉ test thành công, không test exception/early return/retry.** Context leak thường phát sinh ở nhánh thoát bất thường.

**18. Đếm số log theo tenant thành số giao dịch đã commit.** Log có thể mất, lặp hoặc bị filter; cần nguồn nghiệp vụ chính thức.

**19. Cho tenant tự truy vấn index dùng chung chỉ bằng filter ở UI.** Cần server-side authorization, storage ACL và kiểm thử ngăn truy cập chéo.

**20. Dùng ID trống rồi thay mặc định `tenant-A`.** Fail-open bằng một tenant mặc định có thể gây gán nhầm dữ liệu. Với thao tác cần tenant, nên fail-closed hoặc phân biệt rõ sự kiện toàn hệ thống.

## 21. Checklist triển khai trong ứng dụng Java

### A. Nguồn dữ liệu và quyền

- Tenant ID do **trusted resolver** xác định sau authentication/authorization.
- Có kiểm tra quyền truy cập resource thuộc tenant được chọn.
- Có quy ước cho system event, system admin và multi-tenant job.
- Không dùng MDC/ThreadContext để thay thế security context.

### B. Scope và propagation

- Đặt tenant context tại request/message/job boundary sau khi đã verify.
- Dùng `try/finally` hoặc `try-with-resources` để khôi phục/clear.
- Khi submit task, dùng immutable snapshot hoặc context propagation mechanism phù hợp.
- Với reactive/virtual threads, kiểm tra mô hình context của framework, không dựa vào ThreadLocal tùy tiện.
- Không để global mutable tenant ID hay logger name động.

### C. Log format và collector

- `tenant_id` được xuất thành field rõ ràng khi cần truy vấn.
- Giá trị đúng kiểu string và không có CR/LF hoặc dữ liệu không an toàn.
- Encoder lưu đúng timestamp, level, event, trace/correlation ID.
- Structured log có schema và cách xử lý field thiếu rõ.
- Collector lưu field theo path thống nhất; query và alert sử dụng đúng field.
- Đã kiểm tra khối lượng lưu trữ và cardinality index/labels.

### D. Bảo mật và vận hành

- Không ghi bí mật/PII không cần thiết.
- Hạn chế quyền đọc log theo tenant khi có self-service log viewing.
- Có retention, encryption/transport security và audit truy cập kho log.
- Theo dõi missing-tenant field trên các sự kiện tenant-scoped.
- Có test chống context leak khi dùng thread pool, exception, retry, async và deployment.
- Không dùng log làm nguồn trạng thái giao dịch được bảo đảm.

## 22. Câu hỏi tự kiểm tra

1. **Tenant context là gì?** Metadata xác định tenant của **đơn vị công việc hiện tại**; thường được gắn vào LogEvent để chẩn đoán.
2. **Vì sao không dùng `MDC.get("tenant_id")` để phân quyền database?** MDC là logging metadata có thể thay đổi, không phải danh tính đã được xác thực/ủy quyền.
3. **Nguồn tenant nào đáng tin?** Kết quả tenant resolution và authorization qua boundary của hệ thống, không phải header do client tự cung cấp.
4. **Một logger `static final` có dùng cho nhiều tenant không?** Có. Logger theo lớp dùng chung, tenant phải là context của mỗi sự kiện.
5. **ThreadLocal có tự truyền qua ExecutorService không?** Không, không được giả định; cần capture/apply context hoặc mechanism của framework.
6. **Tại sao phải dọn MDC khi request kết thúc?** Tránh request sau trên thread được tái sử dụng nhận nhầm tenant trước.
7. **`MDC.putCloseable` có khôi phục giá trị cũ của key không?** Không tự động; close remove key. Nested scope cần restore thủ công khi thích hợp.
8. **`MDC.getCopyOfContextMap()` có thể trả gì khi không có context?** Có thể `null`; cần xử lý tình huống đó.
9. **Vì sao không đọc ThreadLocal từ async Formatter?** Formatter có thể chạy trên thread khác so với nguồn sự kiện.
10. **Để xuất tenant từ Logback PatternLayout cần gì?** Backend hỗ trợ MDC và pattern như `%X{tenant_id}`.
11. **Trong Log4j2, API nào quản lý context map?** `ThreadContext`; có thể dùng `CloseableThreadContext` theo scope.
12. **`tenant_id` và `trace_id` có giống nhau không?** Không. Tenant mô tả phân vùng dữ liệu, trace mô tả luồng thực thi.
13. **Baggage OpenTelemetry có bảo đảm không bị giả mạo không?** Không; không dùng như chứng cứ quyền tenant.
14. **Có nên đưa tenant ID vào `service.name` cho mỗi request không?** Không nếu service instance phục vụ nhiều tenant; đó không phải tên dịch vụ.
15. **Có nên đưa request ID và tenant ID vào indexed labels Loki không?** Thường không với giá trị cardinality cao; cân nhắc metadata/query khác.
16. **Khi job chạy nhiều tenant, ghi context thế nào?** Per-tenant event gắn đúng tenant, sự kiện tổng dùng scope system/multi theo schema.
17. **Một log không có tenant ID có luôn sai không?** Không. Sự kiện toàn hệ thống hoặc trước xác thực có thể không có tenant; nhưng event tenant-scoped bắt buộc phải có.
18. **Đặt tenant ID vào text log đã đủ để collector truy vấn `tenant_id` chưa?** Chưa; parser/encoder phải lưu field đúng schema.
19. **Một request thuộc A có thể được truy vấn dữ liệu B chỉ vì MDC=B không?** Không được phép; authorization và resource ownership phải ngăn độc lập.
20. **Vì sao test hai tenant dùng một worker thread hữu ích?** Phát hiện lỗi scope không được dọn khi thread được tái sử dụng.
21. **Dùng `try-with-resources` có tự giải quyết propagation qua callback async không?** Không. Phải mở scope thích hợp trong mỗi callback/thread.
22. **Một dòng `payment_completed` gắn tenant A có đủ để xác nhận giao dịch A thành công không?** Không. Trạng thái nghiệp vụ chính thức mới là bằng chứng.

## 23. Tài liệu tham khảo

- SLF4J `MDC` Javadoc: https://www.slf4j.org/api/org/slf4j/MDC.html
- Logback MDC manual: https://logback.qos.ch/manual/mdc.html
- Apache Log4j 2, Thread Context: https://logging.apache.org/log4j/2.x/manual/thread-context.html
- Apache Log4j 2, JSON Template Layout: https://logging.apache.org/log4j/2.x/manual/json-template-layout.html
- OpenTelemetry, Baggage và lưu ý bảo mật: https://opentelemetry.io/docs/concepts/signals/baggage/
- OpenTelemetry, Logs Data Model: https://opentelemetry.io/docs/specs/otel/logs/data-model/
- Grafana Loki, Labels: https://grafana.com/docs/loki/latest/get-started/labels/
- Java 17, `ThreadLocal`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html
- Java 17, `ExecutorService`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ExecutorService.html

**Ghi nhớ:** **tenant context là metadata để ghi log chính xác, không phải công cụ phân quyền**. Lấy tenant ID từ nguồn **đã xác minh**, đặt nó trong **scope có vòng đời rõ**, **restore/clear** sau request, **truyền tường minh** qua async/thread pool và đảm bảo encoder/collector thật sự giữ trường `tenant_id`. Tránh rò context, dữ liệu nhạy cảm và cardinality không kiểm soát. Quyền truy cập tenant luôn phải được bảo vệ bởi lớp authentication/authorization và dữ liệu nghiệp vụ độc lập với logging.
