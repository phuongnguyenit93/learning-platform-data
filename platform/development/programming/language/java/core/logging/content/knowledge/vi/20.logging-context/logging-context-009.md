# Xóa context đúng lúc trong Java logging

## 1. Vấn đề cần giải quyết

**Logging context** là các thông tin đi kèm sự kiện log, chẳng hạn `requestId`, `traceId`, `tenantId` hoặc `jobId`. Chúng giúp tìm các bản ghi thuộc cùng một giao dịch mà không phải nối các thông tin đó vào từng message.

Ví dụ:

```text
INFO  requestId=REQ-A Start order
WARN  requestId=REQ-A Inventory low
INFO  requestId=REQ-B Start order
```

Trong các thư viện logging Java, context thường được quản lý qua **MDC (Mapped Diagnostic Context)** của SLF4J/Logback hoặc **ThreadContext** của Log4j2. Các giá trị thường gắn với thread đang chạy, chứ không phải tự động thuộc về một HTTP request trừ khi ứng dụng chủ động quản lý phạm vi.

**Xóa context đúng lúc** là việc dọn hoặc khôi phục những giá trị tạm thời ngay khi **đơn vị công việc sở hữu chúng** kết thúc.

```text
Thread worker-1:
  Request A: đặt requestId=REQ-A
             log với REQ-A
             quên xóa
  Request B: không đặt requestId
             log bị gắn nhầm REQ-A    <-- lỗi rò context
```

Đây là lỗi nghiêm trọng về tính chính xác của log: dashboard có thể gán sự cố cho sai request, sai tenant hoặc nhầm một lỗi thanh toán của B thành lỗi của A. Nó còn có thể khiến dữ liệu nhạy cảm bị phân loại/lưu dưới sai nhãn.

**Quy tắc cần nhớ:** ai tạo context phải xác định **phạm vi sở hữu**, **thread thực thi**, **cách truyền qua async** và **cách cleanup trên mọi đường thoát**.

### Mục tiêu bài học

Sau bài này, bạn sẽ biết:

- Khi nào dùng `remove`, `clear` và **restore** giá trị cũ.
- Sự khác biệt giữa `SLF4J MDC.putCloseable` và `Log4j2 CloseableThreadContext`.
- Cách đặt/dọn context trong request, message listener, job và thread pool.
- Vì sao `ExecutorService` và `CompletableFuture` cần capture/propagate/cleanup ở đúng thread.
- Cách kiểm thử hai request liên tiếp trên cùng worker bằng chương trình Java 17.
- Các lỗi về NDC stack, async servlet, reactive code, bảo mật và dữ liệu log đã được lưu.

## 2. Cơ chế: MDC và ThreadContext

### SLF4J MDC

SLF4J có API `org.slf4j.MDC`:

```java
MDC.put("requestId", "REQ-A");
String id = MDC.get("requestId");
MDC.remove("requestId");
```

Đây là snippet đặt trong method và cần `import org.slf4j.MDC;`. Mỗi key/value thông thường là chuỗi; việc lưu trữ thực tế do **MDC adapter/provider** quyết định.

Các API cần nhớ:

| API SLF4J | Tác dụng |
| --- | --- |
| `MDC.put(key, value)` | Đặt giá trị trên context hiện tại |
| `MDC.get(key)` | Lấy giá trị |
| `MDC.remove(key)` | Xóa một key |
| `MDC.clear()` | Xóa tất cả mapping hiện tại |
| `MDC.getCopyOfContextMap()` | Lấy snapshot map; có thể là `null` |
| `MDC.setContextMap(map)` | Thay map hiện tại bằng nội dung map được truyền |
| `MDC.putCloseable(key, value)` | Đặt key và trả về đối tượng tự **remove key** khi đóng |

SLF4J là một facade, vì vậy **có MDC trong source code chưa bảo đảm log chứa context**. Backend phải hỗ trợ, và layout/encoder phải xuất các key tương ứng.

### Log4j2 ThreadContext

Log4j2 có `org.apache.logging.log4j.ThreadContext`:

```java
ThreadContext.put("requestId", "REQ-A");
String id = ThreadContext.get("requestId");
ThreadContext.remove("requestId");
```

Log4j2 hỗ trợ hai cấu trúc:

- **Map / MDC**: các cặp `requestId=REQ-A`, `tenantId=tenant-a`.
- **Stack / NDC**: chuỗi thao tác lồng nhau, ví dụ `checkout → payment → authorize`.

Thao tác xóa cũng phải phù hợp với cấu trúc: `ThreadContext.clearMap()` chỉ dọn map; `ThreadContext.clearAll()` dọn map **và stack**. Nếu một helper chỉ sở hữu key `operation` thì không nên `clearAll()` vì nó có thể xóa context của caller.

### Tại sao thread pool nguy hiểm?

Thread pool giữ và tái sử dụng các thread. Một `ThreadLocal`/MDC map sai có thể sống lâu hơn request sở hữu nó. Đặt context ở main thread không có nghĩa worker thread đã nhận được giá trị ấy; xóa trên main thread cũng không làm sạch worker.

```text
Caller thread (request A)
  MDC.put("requestId","REQ-A")
  submit(task)   ─────────────────► Worker thread
  MDC.remove("requestId")           task có context riêng
                                    phải tự đặt + cleanup
```

**Tính chất có thể phụ thuộc backend và cấu hình inheritance**, nhưng không nên dựa vào việc thread tự kế thừa context khi dùng pool, đặc biệt khi worker được tạo từ trước và tái sử dụng lâu dài.

## 3. Cleanup theo vòng đời công việc

| Công việc | Đặt context | Dọn context |
| --- | --- | --- |
| HTTP request đồng bộ | Sau khi xác định request ID, trước khi handler xử lý | Trong `finally` bao quanh phần xử lý request |
| Một message từ queue | Khi bắt đầu xử lý message | Sau log cuối của message, dù thành công hay lỗi |
| Scheduled job | Đầu mỗi lần chạy job | Khi job kết thúc |
| Một task trong executor | Trên worker khi bắt đầu task | Trên **chính worker** trong `finally` |
| Một scope lồng nhau | Khi vào hàm con | Khi thoát hàm con, **khôi phục** context cha |
| Callback/reactive signal | Trong scope callback có thể chạy thread khác | Khi callback kết thúc |
| Unit test | Setup/scope của test | `finally`/teardown, không ảnh hưởng test sau |

Một lỗi thường gặp là dọn quá sớm:

```java
MDC.remove("requestId");
log.error("Request failed", exception);
```

Dòng ERROR lúc này có thể không còn request ID. Thường nên log ở boundary **khi context vẫn còn**, rồi dọn trong `finally`.

Ngược lại, nếu kết thúc request A mà chưa dọn trước lúc thread phục vụ request B, log B có thể mang `REQ-A`.

## 4. Mẫu cơ bản: try/finally

**Không an toàn:**

```java
MDC.put("requestId", requestId);
process();
MDC.remove("requestId");
```

Nếu `process()` ném exception, lệnh remove bị bỏ qua.

**An toàn hơn khi bạn sở hữu key đó:**

```java
MDC.put("requestId", requestId);
try {
    process();
} finally {
    MDC.remove("requestId");
}
```

Đây là snippet trong một method có biến `requestId` và hàm `process` được cung cấp, không phải file Java độc lập. `finally` chạy khi xử lý kết thúc bình thường, return sớm hoặc ném exception theo luồng Java thông thường. Nó không thể bảo đảm chạy nếu JVM bị kill cưỡng bức hoặc mất điện.

Khi cần log exception:

```java
MDC.put("requestId", requestId);
try {
    process();
} catch (RuntimeException ex) {
    log.error("Request failed", ex);
    throw ex;
} finally {
    MDC.remove("requestId");
}
```

Dòng log ERROR được tạo **trước cleanup**, có thể gắn đúng request ID; `Throwable` vẫn được truyền nguyên cho logger. Đừng nối `ex.getMessage()` thành text rồi bỏ Throwable nếu hệ thống cần stack trace.

### Phân biệt remove và clear

`MDC.remove("requestId")` chỉ xóa một key; `MDC.clear()` xóa toàn bộ context map do adapter quản lý trên thread hiện tại.

Trong một request filter **sở hữu toàn bộ MDC của thread**, clear ở boundary có thể phù hợp. Nhưng một thư viện con chỉ thêm `operation` **không được tự ý clear toàn bộ**, vì nó có thể phá `traceId`, `tenantId` hay những key thuộc caller.

## 5. SLF4J MDC.putCloseable: tự remove nhưng không tự restore

SLF4J cung cấp một scope kiểu try-with-resources:

```java
try (MDC.MDCCloseable ignored =
             MDC.putCloseable("requestId", "REQ-A")) {
    log.info("Processing");
}
```

Sau khi kết thúc scope, đối tượng `MDCCloseable` **xóa key `requestId`**. Đây là hành vi theo tài liệu API SLF4J.

**Bẫy khi lồng scope cùng key:**

```java
MDC.put("requestId", "REQ-PARENT");

try (MDC.MDCCloseable child =
             MDC.putCloseable("requestId", "REQ-CHILD")) {
    log.info("Child work");
}

log.info("Parent resumed");
```

Sau close, `requestId` **không tự quay về `REQ-PARENT`**. `MDCCloseable.close()` remove key, không khôi phục giá trị cũ.

Do đó:

- Dùng `putCloseable` khi một scope sở hữu **key mới** chưa tồn tại trước đó.
- Nếu key đã có và cần được giữ, lưu giá trị trước rồi khôi phục.
- Không mặc định mọi API closeable của các framework có cùng semantics.

## 6. Nested scope: khôi phục context của caller

Giả sử request đang có `operation=checkout`, một bước con tạm đặt `operation=payment`. Nếu chỉ remove khi xong, các log còn lại của request sẽ mất `operation=checkout`.

**Mẫu an toàn cho một key SLF4J:**

```java
String oldOperation = MDC.get("operation");

MDC.put("operation", "payment");
try {
    log.info("Payment step");
} finally {
    if (oldOperation == null) {
        MDC.remove("operation");
    } else {
        MDC.put("operation", oldOperation);
    }
}
```

Đây là snippet có biến `log` đã được khai báo. Nếu ban đầu key tồn tại, giá trị cũ được trả lại; nếu chưa tồn tại, key được xóa.

**Khi cần thay toàn bộ map tạm thời:**

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.clear();
    MDC.put("requestId", "REQ-CHILD");
    doChildWork();
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

Snippet này cần `java.util.Map` và method `doChildWork` của ứng dụng. `getCopyOfContextMap` trả bản sao, có thể null; `setContextMap` thay toàn bộ map, nên chỉ sử dụng khi chủ đích khôi phục một snapshot.

**Hai chế độ ownership cần tách rõ:**

1. **Top-level boundary:** sở hữu toàn bộ map của một request/job trên thread được quản lý; có thể clear khi kết thúc.
2. **Borrowed scope:** thư viện/hàm con được gọi khi caller đã có context; phải giữ nguyên hoặc restore phần không thuộc phạm vi mình.

Cleanup không đúng kiểu có thể gây hai lỗi trái nhau: để sót dữ liệu của scope cũ hoặc xóa nhầm context của scope cha.

## 7. Log4j2 CloseableThreadContext có cơ chế restore

Log4j2 cung cấp `CloseableThreadContext`, cho phép đặt các key và stack element tạm thời bằng try-with-resources:

```java
ThreadContext.put("operation", "checkout");

try (CloseableThreadContext.Instance ignored =
             CloseableThreadContext
                 .put("operation", "payment")
                 .put("requestId", "REQ-A")) {
    LOG.info("Inside payment");
}

// operation trở về "checkout";
// requestId mới bị remove.
```

Đây là snippet trong class có `LOG` và import từ `org.apache.logging.log4j`.

**Khác với `MDC.putCloseable` của SLF4J**, `CloseableThreadContext.put` ghi nhớ giá trị trước của các key mà scope sửa và **restore khi close**. Các key mới bị loại; key bị ghi đè được trả về giá trị cũ.

Log4j2 còn có **stack/NDC**:

```java
try (CloseableThreadContext.Instance ignored =
             CloseableThreadContext
                 .put("requestId", "REQ-A")
                 .push("checkout")
                 .push("payment")) {
    LOG.info("Within nested operations");
}
```

Các phần tử được push trong scope sẽ được pop khi close. Nếu dùng API `ThreadContext.push(...)` trực tiếp, hãy cân bằng `pop()` trong `finally`. Nếu chỉ gọi `clearMap()`, các phần tử NDC vẫn có thể tồn tại.

Chỉ gọi `ThreadContext.clearAll()` tại ranh giới mà code thật sự **sở hữu cả map và stack**, không phải trong một helper chỉ quản lý một key.

## 8. Ví dụ Log4j2 Java 17: không rò giữa hai request và một worker

Chương trình dưới đây chạy hai request mô phỏng `REQ-A` và `REQ-B`. Mỗi request phát log trên main thread và chuyển một phần việc sang **một worker thread dùng lại**. Context được chụp ở nơi submit, đặt trên worker và restore sau khi xử lý.

### 8.1. Cấu trúc dự án

```text
context-cleanup-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ContextCleanupDemo.java
        └── resources/
            └── log4j2.xml
```

### 8.2. Tệp pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>context-cleanup-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-api</artifactId>
            <version>2.24.3</version>
        </dependency>
        <dependency>
            <groupId>org.apache.logging.log4j</groupId>
            <artifactId>log4j-core</artifactId>
            <version>2.24.3</version>
            <scope>runtime</scope>
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

Version được ghim để ví dụ có cấu hình rõ ràng, không phải khẳng định đây là phiên bản mới nhất hoặc phù hợp mọi production. Khi dùng thật, kiểm tra bản vá và đồng bộ `log4j-api`/`log4j-core`.

### 8.3. Tệp src/main/resources/log4j2.xml

```xml
<?xml version="1.0" encoding="UTF-8"?>
<Configuration status="WARN">
    <Appenders>
        <Console name="Console" target="SYSTEM_OUT">
            <PatternLayout pattern="%level|%X{requestId}|%msg%n"/>
        </Console>
    </Appenders>

    <Loggers>
        <Root level="info">
            <AppenderRef ref="Console"/>
        </Root>
    </Loggers>
</Configuration>
```

`%X{requestId}` in giá trị từ ThreadContext map. Nếu key không có, vị trí giữa hai dấu `|` sẽ trống. Đây là pattern tối giản cho demo; production nên thêm timestamp, logger name, thread, exception khi thích hợp.

### 8.4. Tệp src/main/java/demo/ContextCleanupDemo.java

```java
package demo;

import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.apache.logging.log4j.CloseableThreadContext;
import org.apache.logging.log4j.LogManager;
import org.apache.logging.log4j.Logger;
import org.apache.logging.log4j.ThreadContext;

public final class ContextCleanupDemo {
    private static final Logger LOG =
            LogManager.getLogger(ContextCleanupDemo.class);

    public static void main(String[] args) throws Exception {
        // Chỉ làm ở startup của chương trình demo độc lập.
        ThreadContext.clearAll();

        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            // Khởi động worker khi caller chưa có requestId.
            pool.submit(ThreadContext::clearAll).get();

            runRequest("REQ-A", pool);
            runRequest("REQ-B", pool);

            System.out.println(
                    "main-context=" + ThreadContext.get("requestId"));
            System.out.println("done");
        } finally {
            pool.shutdown();
            ThreadContext.clearAll();
        }
    }

    private static void runRequest(
            String requestId, ExecutorService pool) throws Exception {

        try (CloseableThreadContext.Instance ignored =
                     CloseableThreadContext.put("requestId", requestId)) {

            LOG.info("begin");

            // Snapshot tại caller, trước khi submit task.
            Map<String, String> captured =
                    new HashMap<>(ThreadContext.getImmutableContext());

            Future<?> task = pool.submit(() -> {
                // Giá trị worker đã có trước task được bảo toàn.
                Map<String, String> oldWorker =
                        new HashMap<>(ThreadContext.getImmutableContext());

                ThreadContext.clearMap();
                try {
                    ThreadContext.putAll(captured);
                    LOG.info("worker");
                } finally {
                    // Xóa context của task trên chính worker.
                    ThreadContext.clearMap();
                    ThreadContext.putAll(oldWorker);
                }
            });

            task.get();
            LOG.info("end");
        }

        // Thoát scope: requestId của main phải biến mất.
        LOG.info("after scope");

        String workerAfter = pool.submit(
                () -> ThreadContext.get("requestId")).get();

        System.out.println(
                "main-after-" + requestId + "="
                        + ThreadContext.get("requestId"));
        System.out.println(
                "worker-after-" + requestId + "=" + workerAfter);
    }
}
```

### 8.5. Biên dịch và chạy

Cần JDK 17+ và Maven, đứng ở thư mục `context-cleanup-demo`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ContextCleanupDemo
```

**Các dòng do ứng dụng và Console appender tạo ra**, không tính thông báo riêng của Maven/plugin:

```text
INFO|REQ-A|begin
INFO|REQ-A|worker
INFO|REQ-A|end
INFO||after scope
main-after-REQ-A=null
worker-after-REQ-A=null
INFO|REQ-B|begin
INFO|REQ-B|worker
INFO|REQ-B|end
INFO||after scope
main-after-REQ-B=null
worker-after-REQ-B=null
main-context=null
done
```

Ví dụ dùng `newSingleThreadExecutor()` và `Future.get()` để task chạy theo thứ tự kiểm chứng được. Worker được khởi tạo trước khi caller đặt context, rồi được dùng lại cho A và B. Vì vậy phép thử thể hiện **tái sử dụng worker thread thật**, không chỉ tạo một thread mới cho mỗi request.

`ThreadContext.get(...)` trả `null` khi không có key; phép nối chuỗi Java in chữ `null`. Trong JSON logging thực tế, trường không có có thể bị bỏ hoặc được biểu diễn khác, tùy schema/encoder.

### 8.6. Tại sao code đúng?

**Caller thread** dùng `CloseableThreadContext.put`:

1. A mở scope `REQ-A`.
2. Logger thấy A khi `begin` và `end`.
3. Scope đóng và requestId bị xóa/khôi phục.
4. Log `after scope` không có ID.
5. B mở scope mới và không thừa hưởng `REQ-A`.

**Worker thread**:

1. Chụp `oldWorker` trước task để biết trạng thái do caller/framework khác có thể sở hữu.
2. Dọn map hiện tại trong lúc install context của task.
3. Đặt snapshot `captured` lấy từ caller.
4. Tạo log trong task.
5. Trong `finally`, xóa context của task và restore `oldWorker`.
6. Task sau không mang context A do task trước để lại.

**Giới hạn có chủ đích:** ví dụ chỉ quản lý **map** của ThreadContext. Nếu ứng dụng dùng **NDC stack** thì phải có chính sách push/pop/restore riêng. Snapshot/restore cũng không tự chữa context đã bị leak **trước khi wrapper chạy**; top-level boundary của worker vẫn phải thực thi trách nhiệm cleanup.

## 9. Anti-pattern: dọn ở caller, bỏ sót worker

Đoạn sai:

```java
ThreadContext.put("requestId", "REQ-A");
pool.submit(() -> LOG.info("Do work"));
ThreadContext.remove("requestId");
```

Chỉ remove ở **caller thread**, còn task chạy ở worker có context độc lập. Nó có thể không thấy `REQ-A` hoặc thấy một giá trị stale khác.

Một đoạn sai khác ngay trên worker:

```java
pool.submit(() -> {
    ThreadContext.put("requestId", "REQ-A");
    LOG.info("Task A");
    // Quên remove/restore.
}).get();

pool.submit(() -> {
    LOG.info("Task B"); // Có thể bị gắn nhầm REQ-A.
}).get();
```

Cả hai snippet giả định code đã có `pool` và `LOG`; không phải file độc lập. Nếu pool chỉ có một thread, task B có thể nhận context cũ.

**Cách sửa:** capture ở thread submit nếu cần propagate; đặt context và cleanup **trong try/finally của task**. Không coi việc caller gọi `Future.get()` hoặc `shutdown()` là phép xóa mọi ThreadLocal trong worker.

## 10. CompletableFuture: cleanup đúng trên continuation

`CompletableFuture.supplyAsync`, `thenApplyAsync` và các callback có thể chạy ở nhiều thread. Một ví dụ sai:

```java
MDC.put("requestId", requestId);
try {
    return CompletableFuture.supplyAsync(this::loadData);
} finally {
    MDC.remove("requestId");
}
```

Snippet trong method này có thể dọn MDC ở caller **trước khi task async chạy xong**. Nó cũng **không tự truyền** context vào task chạy ở worker.

Một utility SLF4J giúp capture/restore context map:

```java
import java.util.Map;
import java.util.function.Supplier;
import org.slf4j.MDC;

static <T> Supplier<T> withMdc(Supplier<T> delegate) {
    Map<String, String> captured = MDC.getCopyOfContextMap();

    return () -> {
        Map<String, String> previous = MDC.getCopyOfContextMap();

        try {
            if (captured == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(captured);
            }
            return delegate.get();
        } finally {
            if (previous == null) {
                MDC.clear();
            } else {
                MDC.setContextMap(previous);
            }
        }
    };
}
```

Đây là **mã utility minh họa**: đặt method vào một class Java, có `delegate` thực tế và import đầy đủ. `captured` được lấy ở **caller khi tạo wrapper**, còn `previous` được lấy **trên worker khi task bắt đầu**. Sau khi chạy, context worker được restore ngay cả khi task ném lỗi.

Sử dụng:

```java
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(
                withMdc(() -> loadData()),
                executor);
```

`loadData` và `executor` do ứng dụng cung cấp. **Mỗi continuation ở thread khác** có thể cần scope propagation riêng. Một wrapper ở future đầu tiên không tự lan context qua mọi callback sau đó.

Ngoài ra, `CompletableFuture` hủy, timeout hoặc lỗi có thể không khiến task dừng ngay. `Future.get(timeout)` timeout ở caller **không chứng minh task worker đã thoát và chạy cleanup**; phải kiểm tra vòng đời task, xử lý interrupt và finally đúng cách.

## 11. Servlet, message consumer và reactive code

### Servlet/filter đồng bộ

Một pattern thường gặp:

```java
String requestId = verifiedOrGeneratedRequestId();

MDC.put("requestId", requestId);
try {
    filterChain.doFilter(request, response);
} finally {
    MDC.remove("requestId");
}
```

Đây là **pseudo-code** cho servlet filter; cần API Servlet, request/response và hàm tạo ID của dự án. Một filter thực tế phải nhận diện các nhánh lỗi/dispatch và dọn ở ranh giới thread phù hợp.

**Không tin vô điều kiện vào header request ID từ client.** Giá trị có thể dài bất thường, chứa ký tự điều khiển, newline hoặc chuỗi giả mạo; nên xác thực, normalize hoặc sinh ID từ server.

### Async servlet

Một filter có thể return sau khi bắt đầu xử lý async nhưng request chưa hoàn tất. Dọn context trên **thread filter** lúc nó rời scope vẫn đúng; việc truyền ID và dọn trên **thread chạy async** phải do task/framework tích hợp riêng. Giữ MDC của filter thread sống tới khi callback kết thúc sẽ khiến thread đó có thể phục vụ request mới với context cũ.

### Message consumer

Mỗi message cần scope riêng:

```java
for (Message message : batch) {
    MDC.put("messageId", message.id());
    try {
        handle(message);
    } finally {
        MDC.remove("messageId");
    }
}
```

Đây là snippet minh họa, không phải file Java độc lập; `Message` và `handle` do ứng dụng định nghĩa. Nếu chỉ clear sau **cả batch**, message B có thể giữ ID của A khi B không đặt đủ các key.

### Reactor/WebFlux

Trong reactive pipeline, code có thể nhảy giữa scheduler/thread. MDC dựa trên ThreadLocal **không thay thế Reactor Context**. Nên dùng cơ chế context propagation do framework hỗ trợ, rồi thiết lập MDC chỉ trong phạm vi callback/signal cần ghi log và khôi phục sau callback.

Đừng bê nguyên pattern `MDC.put` trước khi bắt đầu subscription rồi `clear` lúc future kết thúc trên một thread bất kỳ. Thread tạo subscription, thread xử lý và thread hoàn tất có thể khác nhau.

## 12. NDC stack và context lồng nhau

Log4j2 có context stack:

```java
ThreadContext.push("checkout");
try {
    ThreadContext.push("payment");
    try {
        LOG.info("Authorizing");
    } finally {
        ThreadContext.pop();
    }
} finally {
    ThreadContext.pop();
}
```

Snippet này nằm trong class có Log4j2 `LOG`. Mỗi `push` phải được cân bằng bằng `pop`, kể cả khi throw exception. Nếu quên, stack có thể tích lũy những operation cũ trên thread được tái sử dụng.

Có thể ưu tiên `CloseableThreadContext.push(...)` cùng try-with-resources để giảm nguy cơ quên pop. Không mặc định rằng `ThreadContext.clearMap()` cũng dọn stack; nếu boundary thực sự sở hữu cả hai, có thể dùng `ThreadContext.clearAll()`.

Với SLF4J, MDC map là khái niệm phổ biến; các API deque/stack và mức hỗ trợ thực phụ thuộc adapter. Không mặc định cú pháp Log4j2 NDC có thể sử dụng nguyên xi cho mọi SLF4J backend.

## 13. AsyncAppender không đồng nghĩa async business task

Hai trường hợp phải phân biệt:

- **Async business task:** code nghiệp vụ chạy ở worker khác; worker cần context đúng **khi tạo log event**.
- **Async logging:** logger tạo event trên thread hiện tại, rồi backend chuyển event qua queue tới appender. Backend có thể **chụp context vào event** khi event được phát.

Do đó, không phải giữ `MDC` trên request thread cho tới khi file đã flush xong. Quan trọng là context đúng **tại thời điểm tạo event** và được dọn khi request/task scope kết thúc. Một event đã snapshot context có thể tiếp tục được ghi sau khi ThreadLocal ở caller đã được cleanup.

Tuy nhiên, khả năng giữ context của event còn phụ thuộc backend, version, bridge và encoder. Nếu log bất đồng bộ thiếu field, phải kiểm tra chỗ tạo event, propagate context, chính sách snapshot và layout; không mặc định nguyên nhân là `MDC.remove` chạy quá nhanh.

## 14. Test với một ThreadLocal thuần JDK 17

Để thấy bản chất tái sử dụng thread mà không cần tải thư viện logging, tạo file `ThreadLocalCleanupDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class ThreadLocalCleanupDemo {
    private static final ThreadLocal<String> CONTEXT =
            new ThreadLocal<>();

    private static String task(String id) {
        CONTEXT.set(id);
        try {
            return CONTEXT.get();
        } finally {
            CONTEXT.remove();
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            System.out.println(
                    "A=" + pool.submit(() -> task("REQ-A")).get());
            System.out.println(
                    "after-A=" + pool.submit(CONTEXT::get).get());

            System.out.println(
                    "B=" + pool.submit(() -> task("REQ-B")).get());
            System.out.println(
                    "after-B=" + pool.submit(CONTEXT::get).get());
        } finally {
            pool.shutdown();
        }
    }
}
```

Chạy bằng JDK 17+:

```bash
javac ThreadLocalCleanupDemo.java
java ThreadLocalCleanupDemo
```

**Stdout chính xác:**

```text
A=REQ-A
after-A=null
B=REQ-B
after-B=null
```

Đây là **mô hình ThreadLocal đơn giản để học**, không phải implementation bắt buộc của SLF4J MDC hay Log4j2 ThreadContext. Nếu bỏ `CONTEXT.remove()`, các task `after-A` và `after-B` trên cùng worker có thể thấy giá trị còn sót từ tác vụ trước.

### Những ca test cần có trong ứng dụng thật

1. Request A thành công, sau scope không còn ID.
2. Request A throw exception, finally vẫn dọn context.
3. Request B chạy **cùng worker** nhưng không có ID, log không chứa `REQ-A`.
4. Nested scope đổi key rồi phục hồi giá trị cha.
5. Một job chạy `CompletableFuture` có context đúng trên worker.
6. Task được cancel/timeout không tạo rò state khi cuối cùng dừng.
7. Map snapshot null không làm helper throw `NullPointerException`.
8. Layout/JSON encoder xuất `requestId` khi có và bỏ đúng khi không có.
9. Nếu dùng NDC, stack không tăng sau mỗi request.
10. Không có key nhạy cảm hoặc tenant ID sai trong log của request kế tiếp.

## 15. Bảo mật: stale context không chỉ gây khó đọc log

Một sự cố mẫu:

```text
Worker xử lý tenant A -> put tenantId=A -> quên dọn
Worker xử lý tenant B -> không set tenantId đúng
Log của B bị gắn tenantId=A
```

Trong hệ thống quan sát, dữ liệu này có thể được phân vùng, tìm kiếm hoặc cấp quyền xem theo tenant. Gắn nhầm tenant ID có thể khiến điều tra và dashboard sai, thậm chí làm lộ thông tin vận hành giữa khách hàng.

**Nguyên tắc:**

- Logging context chỉ là **metadata quan sát**, không phải nguồn chân lý cho xác thực/phân quyền.
- Không dùng `MDC.get("tenantId")` làm cơ chế authorization.
- Không lưu password, cookie, API key, token, mã thẻ hoặc PII nhạy cảm trong MDC.
- Validate/normalize các ID lấy từ client; chống newline/log injection và giới hạn độ dài.
- Chỉ propagate những key thực sự cần cho async task.
- Nếu code của thư viện khác sở hữu context, không `clear()` tùy tiện.
- Áp dụng retention và quyền xem phù hợp cho file/collector log.

**Xóa context trong JVM không xóa dữ liệu đã được ghi vào file hoặc gửi tới collector.** Khi event đã phát, việc bảo vệ/xóa dữ liệu đó thuộc chính sách storage, redaction và retention riêng.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân khả dĩ | Hướng xử lý |
| --- | --- | --- |
| B mang requestId của A | Quên cleanup trên thread pool worker | Finally/closeable trong từng task; test cùng worker |
| Caller có MDC nhưng worker không có | Không capture/propagate ở submit | Chụp snapshot ở caller, install khi task chạy |
| Dọn ở main nhưng worker còn ID | Hai thread có state riêng | Dọn trên chính worker |
| Helper làm mất traceId của caller | Gọi `MDC.clear()` toàn map dù chỉ sở hữu một key | Remove key do mình sở hữu hoặc restore snapshot |
| Nested MDC.putCloseable làm mất giá trị cha | SLF4J close xóa key chứ không restore | Lưu giá trị cũ rồi đặt lại |
| CloseableThreadContext không tự dọn | Quên gọi close/không dùng try-with-resources | Scope đúng, đảm bảo close |
| NDC stack tích lũy | Push mà thiếu pop | Finally hoặc closeable scope |
| Async callback không có context | Continuation chạy thread khác | Propagate/scope ở mỗi continuation cần log |
| Context vẫn thấy trong log async sau clear | Event đã snapshot trước cleanup | Có thể là đúng; phân biệt event và current thread |
| Test dùng lại thread có ID cũ | Không clear/restore trong test teardown | Cleanup test boundary |
| JSON logging thiếu field requestId | Layout/encoder không xuất MDC hoặc event tạo trước put | Kiểm tra pattern và thời điểm |
| Future timeout nhưng worker vẫn log | Caller hết đợi không có nghĩa worker đã dừng | Thiết kế cancel/interrupt/cleanup ở worker |
| Log sai tenant | Stale MDC hoặc dữ liệu client không tin cậy | Cleanup đúng, validate ID, không dùng MDC làm auth |

### Checklist debug

1. Code gọi `SLF4J MDC` hay `Log4j2 ThreadContext`?
2. Ai sở hữu context và ai dọn trên **thread nào**?
3. Có `try/finally` trên mọi nhánh throw/return không?
4. Có scope con ghi đè key đã tồn tại không?
5. Có thread pool, callback, message consumer hoặc reactive scheduler không?
6. Snapshot được lấy **trước khi submit** chưa?
7. Worker đã **restore context cũ** hoặc clear theo đúng ownership chưa?
8. Context map và stack có được xử lý tách biệt khi dùng NDC không?
9. Layout `%X{requestId}` hoặc JSON encoder có xuất các trường cần thiết không?
10. Chạy thử A rồi B **trên cùng worker** và quan sát không còn stale ID.

## 17. Tự kiểm tra kiến thức

**Câu 1.** Vì sao cần cleanup dù HTTP request đã return?  
**Đáp án:** Thread có thể được dùng cho request khác; MDC còn sót khiến log sau bị gắn nhầm.

**Câu 2.** Vì sao phải dùng `finally`?  
**Đáp án:** Để cleanup không bị bỏ qua khi return sớm hoặc exception được ném theo luồng Java thông thường.

**Câu 3.** `MDC.remove` và `MDC.clear` khác nhau thế nào?  
**Đáp án:** Remove một key, clear mọi mapping trên context hiện tại.

**Câu 4.** `MDC.putCloseable` có restore giá trị đã có không?  
**Đáp án:** Không. SLF4J close remove key. Với nested key cần tự lưu/restore.

**Câu 5.** `CloseableThreadContext.put` của Log4j2 có gì khác?  
**Đáp án:** Nó khôi phục giá trị cũ cho key bị ghi đè khi close và xóa các key mới.

**Câu 6.** Đặt MDC trên thread submit có đủ cho `ExecutorService` không?  
**Đáp án:** Không. Phải có cơ chế truyền context phù hợp và cleanup trên thread thực thi.

**Câu 7.** Nếu worker đã có leaked ID trước task, snapshot/restore có tự chữa leak đó?  
**Đáp án:** Không. Nó restore trạng thái ban đầu, kể cả trạng thái sai; cần top-level boundary đáng tin dọn sạch.

**Câu 8.** `ThreadContext.clearMap` có xóa NDC stack không?  
**Đáp án:** Không. Map và stack có lifecycle riêng.

**Câu 9.** Xóa MDC trước khi log exception cuối có hậu quả gì?  
**Đáp án:** Event ERROR có thể thiếu request/trace ID cần cho điều tra.

**Câu 10.** Vì sao một future timeout không bảo đảm worker đã cleanup?  
**Đáp án:** Timeout chỉ kết thúc việc chờ của caller; task có thể vẫn đang chạy.

**Câu 11.** Có cần giữ MDC tới lúc AsyncAppender flush xong không?  
**Đáp án:** Không như một quy tắc chung. Điều quan trọng là context đã được gắn vào event khi tạo, backend xử lý snapshot đúng.

**Câu 12.** Có thể dùng MDC thay cho security context để phân quyền tenant không?  
**Đáp án:** Không. Logging context chỉ là metadata để quan sát; quyền phải được kiểm soát bằng cơ chế xác thực/authorization độc lập.

**Câu 13.** Xóa MDC có xóa các trường context đã được ghi trong log file không?  
**Đáp án:** Không. Những event đã phát có vòng đời và chính sách lưu riêng.

**Ghi nhớ:** **Đặt context là mở scope, dọn hoặc khôi phục là đóng scope.** Làm đúng trên **thread sở hữu**, ở **finally/closeable scope**, sau khi các event cần context đã được tạo. Với thread pool và async, phải **capture → propagate → process → restore/cleanup**. SLF4J `MDC.putCloseable` xóa key khi đóng; Log4j2 `CloseableThreadContext` khôi phục key cũ. Tránh both stale context lẫn xóa nhầm dữ liệu của caller.

**Tham khảo chính thức:**

- [SLF4J MDC API](https://www.slf4j.org/api/org/slf4j/MDC.html)
- [Log4j2 Thread Context](https://logging.apache.org/log4j/2.x/manual/thread-context.html)
- [Log4j2 CloseableThreadContext API](https://logging.apache.org/log4j/2.x/javadoc/log4j-api/org/apache/logging/log4j/CloseableThreadContext.html)
- [Logback Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html)
