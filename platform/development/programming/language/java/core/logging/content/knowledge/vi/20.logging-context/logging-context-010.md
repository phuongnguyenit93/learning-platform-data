# Tránh context lỗi thời trong Java Logging

**Context lỗi thời** (*stale logging context*) xảy ra khi metadata được gắn cho một request, job, transaction hoặc trace **tiếp tục xuất hiện trong những log không còn thuộc ngữ cảnh đó**. Ví dụ, thread xử lý xong request A nhưng vẫn giữ `requestId=req-A`; thread pool tái sử dụng chính thread ấy cho request B, khiến log của B bị ghi sai ID. Trong Java, tình huống này thường liên quan đến **MDC (Mapped Diagnostic Context)** của SLF4J/Logback, **ThreadContext** của Log4j 2, các wrapper `ThreadLocal` hoặc cách quản lý scope không nhất quán.

Vấn đề không chỉ là log “khó đọc”. Context lỗi thời có thể gây **truy vết sai, cảnh báo thiếu chính xác, điều tra nhầm khách hàng, rò rỉ metadata giữa các request/tenant**, hoặc khiến sự kiện của một giao dịch được gán vào giao dịch khác. Để tránh điều đó, context phải được quản lý theo đúng **vòng đời**, được **đặt/khôi phục/xóa có kỷ luật**, và được **truyền một cách tường minh khi đổi ngữ cảnh thực thi**.

Bài này tập trung vào cách ngăn context cũ bị dùng lại, không nhầm với bài đặt tên field hay xuất JSON. Các ví dụ dùng Java 17+, SLF4J/Logback và lưu ý tương đương cho Log4j 2.

## 1. Context nào dễ trở nên lỗi thời?

Trong log ứng dụng, context thường chứa metadata giúp liên kết sự kiện:

| Context field | Vòng đời hợp lý | Nguy cơ nếu giữ quá lâu |
| --- | --- | --- |
| `requestId` | Một HTTP request hoặc tác vụ tương đương | Log request B mang ID của A |
| `traceId` / `spanId` | Trace/span thực sự đang hoạt động | Tìm nhầm trace/span, khó đối chiếu với tracing |
| `tenantId` | Request, job hoặc operation thuộc một tenant | Gán hành vi của tenant B cho tenant A |
| `jobId` | Một job hoặc một lần xử lý message | Job mới bị ghi dưới ID job đã kết thúc |
| `orderId` / `paymentId` | Operation hoặc từng event cụ thể | Log thao tác trên đối tượng khác bị gán sai |
| `retryAttempt` | Một lần thử trong quá trình retry | Event sau retry vẫn mang số lần thử cũ |
| `userRole` | Context bảo mật đã được xác minh trong request | Quyền/role được hiểu sai khi user khác dùng thread |
| `operationName` | Một scope nhỏ của tác vụ | Log ngoài scope bị gắn tên bước đã kết thúc |

Không phải mọi field đều nên được đặt trong MDC. `service`, `environment` hay `instanceId` thường là **resource metadata** tương đối ổn định cho toàn bộ tiến trình, thích hợp gắn bằng cấu hình logging/collector. `durationMs`, `outcome` và `errorCode` thường phản ánh **từng sự kiện**, không phải context cần tồn tại trong suốt request.

**Quy tắc:** field chỉ được giữ trong phạm vi mà giá trị còn đúng. Nếu một request xử lý nhiều đơn hàng, `requestId` có thể giữ nguyên, nhưng `orderId` phải thay theo operation hoặc xuất trực tiếp tại từng log event.

## 2. Cơ chế hình thành stale context

### 2.1. ThreadLocal và thread pool

Nhiều MDC adapter lưu map các key–value theo **thread hiện tại**. Thread pool tái sử dụng worker thread, trong khi việc kết thúc một request **không nhất thiết hủy thread**. Nếu thiếu cleanup, map cũ vẫn còn cho công việc kế tiếp.

```text
Thread pool worker-1
    |
    | Request A: MDC.put("requestId", "req-A")
    | Log: requestId=req-A  event=request.started
    | Request A kết thúc, quên MDC.remove/clear
    |
    v
Cùng worker-1 xử lý request B
    | Request B không thiết lập được requestId
    | Log: requestId=req-A  event=request.started  <-- SAI
    |
    v
Request C tiếp tục tái sử dụng worker-1 ...
```

MDC thường là **dữ liệu gắn theo thread**, không phải “biến toàn cục cho toàn JVM”, nhưng thread tái sử dụng làm lỗi trông giống dữ liệu bị lẫn giữa các request. Nếu gọi `MDC.clear()` trên **thread khác**, bạn không tự động xóa MDC của worker đang giữ dữ liệu cũ.

### 2.2. Exception hoặc early return bỏ qua cleanup

```java
// SAI: đoạn minh họa; MDC, LOG và requestId đã tồn tại.
MDC.put("requestId", requestId);
LOG.info("event=request.started");
processRequest();  // Có thể throw trước dòng remove bên dưới.
MDC.remove("requestId");
```

Nếu `processRequest()` ném exception, dòng `remove` không chạy. `return` sớm, cancel hoặc timeout ở một nhánh cũng gây lỗi tương tự khi cleanup không nằm trong `finally`.

### 2.3. Nested scope ghi đè nhưng không khôi phục giá trị cũ

Ví dụ một request đang có `operationId=checkout-1`, một tác vụ con đặt `operationId=payment-2`. Nếu tác vụ con gọi `MDC.remove("operationId")` khi xong, context của scope ngoài cũng bị mất. Nếu không gọi remove, log sau đó vẫn mang `payment-2`. **Xóa và khôi phục không hoàn toàn là cùng một thao tác.**

### 2.4. Context truyền không đúng khi xử lý bất đồng bộ

MDC của thread gọi không mặc nhiên có trên thread chạy `ExecutorService` hoặc `CompletableFuture`. Một lỗi thường gặp là “lấy” context của thread worker khi task bắt đầu, lúc đó worker có thể đang giữ context cũ. Đúng ra phải **chụp context hợp lệ tại thời điểm submit**, truyền snapshot sang task, rồi **khôi phục trạng thái trước đó của worker** sau khi task kết thúc.

### 2.5. Context thay đổi nhưng event được xử lý muộn

Logging có thể được xử lý bất đồng bộ. Nếu code dựa vào một map mutable dùng chung và lúc serialize mới đọc map ấy, event của request A có thể được gắn metadata đã bị thay bằng request B. Framework logging đúng thường có cơ chế chụp dữ liệu event; với wrapper/encoder tùy chỉnh, cần kiểm tra **thời điểm snapshot** thay vì giả định mọi đối tượng map đã bất biến.

## 3. Hậu quả trong vận hành và bảo mật

| Triệu chứng | Điều người vận hành có thể hiểu nhầm | Tác động |
| --- | --- | --- |
| Log B mang `requestId=req-A` | Lỗi B do A gây ra | Điều tra nhầm request |
| `traceId` giữ từ tác vụ trước | Event thuộc một distributed trace khác | Không nối được log với span đúng |
| `tenantId` lỗi thời | Hành vi ở tenant B thuộc tenant A | Nguy cơ nhầm lẫn dữ liệu và quyền truy cập |
| `orderId` không được reset | Tất cả bước đều xử lý một đơn hàng | Báo cáo sai đường đi nghiệp vụ |
| Worker thiếu context mới | Event async không thể nối với request caller | Mất khả năng correlation |
| MDC leak trên thread pool | Một lần lỗi làm sai nhiều request tiếp theo | Lỗi lan rộng và khó tái hiện |
| Context quá lớn hoặc chứa secret | Log/encoder và storage thu thêm dữ liệu | Tốn tài nguyên, rủi ro bảo mật |

**Stale context là lỗi về tính đúng đắn của metadata**, khác với việc ghi trùng log do appender additivity hay việc chọn sai level. Cùng một message có thể vẫn đúng về mặt nghiệp vụ, nhưng nếu context sai thì truy vấn và audit dựa vào metadata trở nên không đáng tin.

## 4. Nguyên tắc quan trọng nhất: scope + finally

Hãy coi context giống một tài nguyên có vòng đời:

1. **Bắt đầu scope:** xác định request/job/operation, validate các ID cần dùng.
2. **Lưu trạng thái trước đó** nếu có thể có nested scope.
3. **Thiết lập đúng context** cho công việc đang làm.
4. **Thực hiện nghiệp vụ và log** trong scope.
5. **Khôi phục hoặc xóa trong `finally`**, kể cả khi có exception.
6. **Không dùng context cũ để lấp field thiếu**; nếu request không có trace, xử lý absent/null theo schema thay vì lấy trace từ thread.

Mẫu mã **SLF4J MDC** cho scope gốc của một request:

```java
// Đoạn minh họa: MDC, LOG và requestId đã được khai báo.
java.util.Map<String, String> previous =
        org.slf4j.MDC.getCopyOfContextMap();

try {
    // Ranh giới request: loại dữ liệu cũ do pooled thread có thể giữ.
    org.slf4j.MDC.clear();
    org.slf4j.MDC.put("requestId", requestId);
    LOG.info("event=request.started");
    processRequest();
} finally {
    if (previous == null) {
        org.slf4j.MDC.clear();
    } else {
        org.slf4j.MDC.setContextMap(previous);
    }
}
```

Đoạn trên **không phải chương trình độc lập**; trong ứng dụng thật, `LOG`, `requestId` và `processRequest()` phải tồn tại. Nó minh họa ranh giới **root request scope**: dữ liệu ngữ cảnh trước scope được lưu và khôi phục; context của request mới được xác định rõ trước khi phát log.

**Lưu ý quan trọng:** nếu `previous` đã chứa context cũ do một bug trước đó, khôi phục toàn bộ `previous` cũng có thể khôi phục dữ liệu lỗi thời. Tại ranh giới nhận request của server, nên có chính sách làm sạch worker thread và phát hiện context không mong đợi; việc restore snapshot chỉ là mô hình tốt cho **nested scope hợp lệ** hoặc wrapper không sở hữu toàn bộ vòng đời thread. Đừng coi snapshot cũ là “đúng” nếu nó đã sai từ đầu.

## 5. `remove(key)`, `clear()` và restore khác nhau

| Thao tác | Ý nghĩa | Dùng khi nào |
| --- | --- | --- |
| `MDC.put(key, value)` | Gắn/ghi đè giá trị trên thread hiện tại. | Bắt đầu scope hoặc thêm metadata |
| `MDC.remove(key)` | Xóa một key của thread hiện tại. | Scope thật sự sở hữu một key, không có giá trị cũ cần giữ |
| `MDC.clear()` | Xóa toàn bộ MDC trên thread hiện tại. | Ranh giới request/job mà thread phải bắt đầu “sạch” |
| `MDC.getCopyOfContextMap()` | Lấy snapshot các cặp key–value hiện tại. | Trước khi thay scope hoặc submit async task |
| `MDC.setContextMap(map)` | Đặt map context từ snapshot. | Khôi phục/cài snapshot trong scope có kiểm soát |

**Không dùng `clear()` tùy tiện giữa một request hợp lệ**, vì nó có thể xóa `traceId`, `spanId` hoặc metadata mà framework tracing đang giữ. Ngược lại, chỉ gọi `remove("requestId")` có thể chưa đủ nếu request đã gắn thêm `tenantId`, `userType` hoặc `operationId`. Sự lựa chọn phải theo **ai sở hữu context** và **scope nào đã đặt những key đó**.

MDC của SLF4J còn có `putCloseable(key, value)`. Ví dụ:

```java
// Đoạn minh họa trong một method dùng SLF4J.
try (org.slf4j.MDC.MDCCloseable ignored =
             org.slf4j.MDC.putCloseable("operationId", operationId)) {
    LOG.info("event=operation.started");
}
```

`MDCCloseable` hỗ trợ cleanup một key khi đóng scope, nhưng **không tự bảo đảm khôi phục giá trị cũ đã bị ghi đè**. Nếu lồng nhiều scope trên cùng key, hãy dùng helper lưu giá trị trước đó và restore chính xác; tránh giả định close tương đương snapshot/restore.

## 6. Nested context: giữ field của scope ngoài

Giả sử request đang có:

```text
requestId=req-A
operationId=checkout
```

Khi vào một thao tác thanh toán, code cần tạm đặt `operationId=payment`. Sau khi thanh toán kết thúc, `operationId` phải quay về `checkout` chứ không mất hoàn toàn hoặc giữ giá trị `payment`.

Mẫu SLF4J cho **một key lồng nhau**:

```java
// Mã minh họa trong method có LOG, paymentId, xử lý nghiệp vụ.
String before = org.slf4j.MDC.get("operationId");

try {
    org.slf4j.MDC.put("operationId", "payment");
    LOG.info("event=payment.started paymentId={}", paymentId);
    processPayment();
} finally {
    if (before == null) {
        org.slf4j.MDC.remove("operationId");
    } else {
        org.slf4j.MDC.put("operationId", before);
    }
}
```

Đoạn trên **không độc lập**; các biến/method còn lại được ứng dụng cung cấp. Việc khôi phục giá trị cũ giúp logger ở caller tiếp tục thấy `operationId=checkout`.

Đối với nhiều key, có thể viết một helper tạo scope chụp snapshot hoặc sử dụng API có scope của framework. Cần chọn mức độ bao bọc phù hợp: helper phục hồi **mọi key** có thể vô tình ghi đè context được thay đổi hợp lệ trong scope; helper phục hồi **một key** chỉ phù hợp khi scope sở hữu duy nhất key đó.

**Không để tên operation hoặc tenant gắn vĩnh viễn theo thread**. Thread là cơ chế thực thi; request và operation mới là chủ sở hữu ngữ nghĩa của context.

## 7. Thread pool: vì sao lỗi thường xuất hiện ngẫu nhiên?

Thread pool làm lỗi khó tái hiện vì mỗi request có thể chạy trên thread khác nhau. Có hôm request B chạy trên một worker sạch nên bình thường; hôm khác nó trúng đúng worker vừa xử lý request A và bị dính context cũ.

Ví dụ mã cố tình sai (**không sử dụng trong production**):

```java
// SAI: executor và LOG đã có, requestId lấy từ request.
executor.execute(() -> {
    org.slf4j.MDC.put("requestId", requestId);
    LOG.info("event=task.started");
    processTask();
    // Quên cleanup khi success hoặc exception.
});
```

Nếu `executor` là fixed/single thread pool, thread sau có thể tiếp tục thấy requestId cũ.

**Cách đúng:** ở tác vụ xử lý request, xác định scope rõ, dùng `finally` để cleanup/restore; ở task nhận qua executor, không assume MDC caller tự có. Nếu không có context mới, task phải dùng ngữ cảnh đúng của nó (ví dụ `jobId`) hoặc không có requestId.

### Dùng `InheritableThreadLocal` có giải quyết được không?

Không nên dựa vào `InheritableThreadLocal` để truyền MDC qua **thread pool**. Inheritance thường diễn ra lúc thread con được tạo, trong khi pooled worker có thể đã tồn tại từ lâu và được dùng cho nhiều request. Context mới của request tại thời điểm submit không tự áp dụng lên worker đã có. Việc kế thừa tự động còn có thể mang dữ liệu không cần thiết sang thread không liên quan.

Với Java 21+ virtual threads, nguyên tắc scope/propagation vẫn quan trọng; không suy ra rằng dùng virtual thread khiến mọi framework MDC tự dọn hoặc truyền context chính xác. Ví dụ chạy của bài sử dụng Java 17 và `ExecutorService` thông thường.

## 8. Propagation bất đồng bộ: chụp lúc submit, cài trong task, khôi phục sau

Mẫu tổng quát:

```text
Thread nhận request:
  context=req-A
  |
  +-- snapshot (req-A) khi submit
  |
  v
Executor worker:
  oldContext = snapshot hiện tại của worker
  setContext(req-A)
  try { chạy task, phát log }
  finally { restore(oldContext) }

Caller:
  finally { kết thúc scope req-A }
```

Nếu chụp context bên trong worker **sau khi task đã được queue và caller đã cleanup**, snapshot có thể rỗng hoặc chứa dữ liệu của worker trước đó. Chụp đúng **khi tạo/submitting task**, rồi truyền một bản sao không dùng chung mutable state.

Mẫu wrapper dùng SLF4J:

```java
// Mã minh họa trong class đã import Map, Runnable và MDC.
static Runnable withCapturedMdc(Runnable task) {
    java.util.Map<String, String> captured =
            org.slf4j.MDC.getCopyOfContextMap();

    return () -> {
        java.util.Map<String, String> workerBefore =
                org.slf4j.MDC.getCopyOfContextMap();
        try {
            if (captured == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(captured);
            }
            task.run();
        } finally {
            if (workerBefore == null) {
                org.slf4j.MDC.clear();
            } else {
                org.slf4j.MDC.setContextMap(workerBefore);
            }
        }
    };
}
```

Đoạn này là **helper minh họa**, có thể đặt trong class Java có dependency SLF4J phù hợp. Tại task boundary, cần quyết định liệu restore giá trị cũ của worker có phải hành vi mong muốn hay không. Trong wrapper generic, restore là đúng để không phá scope hợp lệ của caller/host; trong một worker dành riêng cho request mới, có thể yêu cầu clear trước và sau, đồng thời giám sát trạng thái bất thường.

**Nhớ:** `captured` được giữ trong closure của task. Nếu queue tồn đọng lâu, context vẫn có thể tồn tại trong bộ nhớ cho tới lúc task chạy hoặc bị hủy. Không đưa token/secret, object nặng hoặc toàn bộ request vào context; chỉ giữ các ID/metadata cần thiết và áp dụng timeout/cancellation phù hợp.

## 9. Ví dụ Java 17 chạy độc lập: chứng minh không rò context giữa hai request

Bài thực hành sử dụng **SLF4J 2.x + Logback Classic** để minh họa chính hành vi của MDC trong logging thực tế, không tự giả lập bằng một `ThreadLocal` tùy chỉnh. Chương trình tạo **một executor chỉ có một worker thread** để buộc hai request dùng lại cùng thread; nhờ đó phép thử bắt được stale context nếu code quên cleanup.

Mỗi request có vòng đời rõ. Snapshot MDC được chụp trên thread caller trước khi task submit, cài trên worker, rồi khôi phục worker MDC trong `finally`. Sau hai request, chương trình submit một tác vụ không có context để chứng minh worker không giữ lại `req-A` hoặc `req-B`.

Dùng JDK 17 và Maven. Ví dụ cố định `logback-classic:1.5.18`, **không khẳng định đây là bản mới nhất**. Các dự án production cần chọn phiên bản được duy trì, đã vá lỗ hổng và tương thích với SLF4J/JDK hiện tại.

### 9.1. Cấu trúc thư mục

```text
stale-context-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── StaleContextDemo.java
        └── resources/
            └── logback.xml
```

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>stale-context-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.5.18</version>
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
                <configuration>
                    <mainClass>demo.StaleContextDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`logback-classic` kéo theo những dependency Logback Core và SLF4J API cần thiết theo Maven. Đừng thêm `slf4j-simple` hoặc provider SLF4J khác vào runtime của demo, vì có thể tạo xung đột provider, khiến cấu hình Logback không được chọn.

### 9.3. src/main/resources/logback.xml

```xml
<configuration>
    <appender name="STDOUT"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level | requestId=%X{requestId:-none} | %msg%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
```

Pattern dùng `%X{requestId:-none}` để in MDC key `requestId`, hoặc in `none` khi key không tồn tại. Không có timestamp/thread trong pattern nên output mẫu xác định. Đây là cấu hình **text** phục vụ demo, không phải JSON structured logging; muốn JSON cần encoder tương ứng.

### 9.4. src/main/java/demo/StaleContextDemo.java

```java
package demo;

import java.util.Map;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class StaleContextDemo {
    private static final Logger LOG =
            LoggerFactory.getLogger(StaleContextDemo.class);

    private static void restore(Map<String, String> snapshot) {
        if (snapshot == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(snapshot);
        }
    }

    // Chỉ dùng ở ranh giới request gốc do ứng dụng sở hữu.
    private static void withRequest(
            String requestId,
            Runnable action
    ) {
        Map<String, String> previous = MDC.getCopyOfContextMap();
        try {
            MDC.clear();
            MDC.put("requestId", requestId);
            action.run();
        } finally {
            restore(previous);
        }
    }

    // Phải được gọi trên thread đang có context trước submit.
    private static Runnable captureForWorker(Runnable action) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> before =
                    MDC.getCopyOfContextMap();
            try {
                restore(captured);
                action.run();
            } finally {
                restore(before);
            }
        };
    }

    private static void await(Future<?> task) {
        try {
            task.get();
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Task interrupted", ex);
        } catch (ExecutionException ex) {
            throw new IllegalStateException("Task failed", ex);
        }
    }

    public static void main(String[] args) {
        ExecutorService executor = Executors.newSingleThreadExecutor();

        try {
            withRequest("req-A", () -> {
                LOG.info("event=request.started");
                await(executor.submit(captureForWorker(
                        () -> LOG.info("event=work.completed")
                )));
            });

            withRequest("req-B", () -> {
                LOG.info("event=request.started");
                await(executor.submit(captureForWorker(
                        () -> LOG.info("event=work.completed")
                )));
            });

            // Task thứ ba không nhận request context.
            await(executor.submit(
                    () -> LOG.info("event=worker.idle")
            ));
        } finally {
            executor.shutdown();
        }
    }
}
```

### 9.5. Biên dịch và chạy

Mở terminal tại thư mục chứa `pom.xml`; cần JDK 17 và Maven, lần đầu có thể cần mạng để tải dependencies:

```bash
mvn -q compile exec:java
```

**Các dòng log do chương trình phát ra trên stdout**, không tính thông báo Maven hoặc cảnh báo môi trường (nếu có):

```text
INFO | requestId=req-A | event=request.started
INFO | requestId=req-A | event=work.completed
INFO | requestId=req-B | event=request.started
INFO | requestId=req-B | event=work.completed
INFO | requestId=none | event=worker.idle
```

### 9.6. Giải thích đầu ra và cách kiểm chứng

1. `withRequest("req-A", ...)` thiết lập request scope trên main thread, thực hiện log trong scope và khôi phục MDC trong `finally`.
2. `captureForWorker(...)` được gọi **trước `executor.submit(...)`**, tức trên main thread khi MDC đang là `req-A`. Snapshot của request A được cài lên worker trong lúc task chạy.
3. `await(Future.get())` buộc task A hoàn tất trước khi bắt đầu request B. Đây là điều kiện giúp output được xác định về thứ tự trong ví dụ.
4. `captureForWorker` khôi phục MDC của worker trong `finally`. Vì worker mới ban đầu không có context, nó trở về trạng thái không có requestId sau task A.
5. Request B cũng truyền snapshot `req-B`, vì vậy sự kiện `work.completed` thứ hai không thể mang nhầm `req-A`.
6. `Executors.newSingleThreadExecutor()` dùng lại cùng một worker thread cho cả hai task. Không có cơ chế tự động tạo một thread mới cho mỗi request để che lỗi stale context.
7. Task `worker.idle` không gắn request context. Nó chạy sau hai `Future.get()`, nên pattern in `requestId=none`. Đây là dấu hiệu cụ thể rằng worker không bị giữ ID của request trước.
8. `executor.shutdown()` được gọi trong `finally` để giải phóng tài nguyên của demo. Với service sống lâu, executor và logging lifecycle thường được quản lý bởi framework.
9. `restore(previous)` ở main thread và `restore(before)` ở worker là hai hành động độc lập. MDC là theo thread; dọn ở main thread **không tự dọn** worker thread.

**Điều demo không bao quát:** trong một ứng dụng HTTP framework, scope của tracing có thể đã được quản lý bởi instrumentation; không nên thay thế bừa tất cả context bằng `MDC.clear()` nếu middleware khác sở hữu các key như `traceId`. Hãy tích hợp theo cơ chế chính thức của framework và review ai chịu trách nhiệm cleanup. Ví dụ cũng không có chủ đích đo hiệu năng của thread pool hay bảo đảm độ bền logging.

## 10. Log4j 2 ThreadContext: nguyên tắc tương đương

Log4j 2 sử dụng `org.apache.logging.log4j.ThreadContext` để chứa context map/stack gắn với ngữ cảnh thực thi:

```java
// Mã minh họa, LOG và requestId đã được khai báo.
org.apache.logging.log4j.ThreadContext.put(
        "requestId", requestId
);
try {
    LOG.info("event=request.started");
    processRequest();
} finally {
    org.apache.logging.log4j.ThreadContext.remove("requestId");
}
```

Đây là mã **không độc lập**. Với nested scope, phải lưu giá trị cũ trước khi ghi đè và khôi phục lại, không chỉ remove. Tương tự với Executor, truyền **context snapshot** qua task boundary theo API Log4j 2 hoặc cơ chế context propagation của framework, rồi khôi phục/clear trong `finally`.

Log4j 2 có các API context và tính năng scope tùy phiên bản; không suy ra chính xác hành vi của MDC SLF4J sang mọi kiểu backend Log4j 2 mà không kiểm chứng. Nếu dùng SLF4J làm facade và Log4j 2 làm backend, kiểm tra provider/bridge và đường truyền context thực tế.

Đối với context stack của Log4j 2, nguyên tắc push/pop phải cân bằng; thiếu pop có thể khiến giá trị từ operation trước vẫn nằm ở stack. Không đặt context vào stack khi không biết scope nào sẽ chịu trách nhiệm giải phóng.

## 11. HTTP filter, interceptor và phạm vi sở hữu context

Trong ứng dụng web, ranh giới thích hợp để khởi tạo `requestId` thường là **filter/interceptor/middleware**. Thay vì gọi `MDC.put(...)` trong từng controller rồi hy vọng dọn sạch, hãy thiết kế:

```text
Request enters
  |
  +-- validate / issue requestId
  +-- establish request/tracing scope
  |
  v
Controller -> Service -> Repository
  |
  +-- submit async tasks with explicit context propagation
  |
  v
finally:
  close scope / restore or clear owned context
```

Các lưu ý:

- **Không tin mù quáng header correlation ID từ client.** Kiểm tra độ dài, ký tự cho phép, chuẩn định danh và chính sách tạo ID mới khi input không hợp lệ.
- **Không đặt token, session cookie hoặc toàn bộ header vào MDC**, vì nhiều appender có thể xuất mọi field MDC cho mọi event, làm lan dữ liệu nhạy cảm.
- **Ranh giới async request:** khi servlet/request chuyển sang async mode hoặc callback chạy sau khi thread xử lý ban đầu trả về pool, cần hiểu chính xác lifecycle của framework. Cleanup tại một filter đồng bộ không bảo đảm callback sau đó có đủ context nếu không propagate.
- **Không override traceId của tracer.** Nếu OpenTelemetry/tracing framework quản lý trace/span context, lấy giá trị từ active span và để instrumentation chịu trách nhiệm propagation/cleanup tương ứng.
- **Context B không được chứa A ngay từ đầu.** Scope request mới phải thiết lập giá trị mới chính xác hoặc biểu diễn missing theo schema, không dựa vào giá trị được “thừa hưởng” từ pooled thread.
- Nếu một thư viện/framework đã thiết lập MDC, tránh dùng `MDC.clear()` bừa bãi ở tầng thấp khiến xóa cả key không thuộc mình.

## 12. Scheduler, message consumer và batch job

Không phải stale context chỉ xảy ra ở HTTP server. Ví dụ `ScheduledExecutorService` chạy cùng một worker cho hàng nghìn lần tick; message consumer nhận nhiều message liên tiếp trên một thread; batch processor lặp qua nhiều item trong cùng job.

### Scheduled job

- Mỗi lần chạy cần `runId` hoặc `jobId` đúng lần thực thi.
- Đặt context tại đầu `run()`, dọn trong `finally`.
- Nếu task bị cancel/timeout, vẫn cần cơ chế dọn scope khi control flow kết thúc.
- Không gán lại `requestId` của request HTTP đã kích hoạt job nếu job về sau có vòng đời độc lập; có thể dùng `correlationId` của quy trình nếu được định nghĩa rõ.

### Message consumer

- Không coi `messageId` của message A còn hợp lệ khi polling message B.
- Khi retry, chỉ gắn `attempt` cho lần xử lý hiện tại, xóa/khôi phục trước item tiếp theo.
- Nếu requeue/redirect message sang thread khác, phải truyền context đúng hoặc khởi tạo context mới từ message metadata đã được xác thực.

### Batch loop

```java
// Đoạn minh họa: LOG và jobs đã được khai báo.
for (Job job : jobs) {
    String prior = org.slf4j.MDC.get("jobId");
    try {
        org.slf4j.MDC.put("jobId", job.id());
        LOG.info("event=job.started");
        process(job);
    } finally {
        if (prior == null) {
            org.slf4j.MDC.remove("jobId");
        } else {
            org.slf4j.MDC.put("jobId", prior);
        }
    }
}
```

Mã này không độc lập, chỉ minh họa **mỗi item có scope riêng**. Nếu `job.id()` có thể null, phải xử lý theo contract của MDC API và schema trước khi `put`. Một lỗi trong một item không được khiến item kế tiếp tiếp tục giữ jobId sai.

## 13. CompletableFuture, reactive và context propagation

Với `CompletableFuture.supplyAsync(...)` hoặc `thenApplyAsync(...)`, callback có thể chạy trên một executor hoặc common pool không mang MDC của caller. Ngay cả một callback không có hậu tố `Async` đôi khi có thể chạy trên thread hoàn tất stage trước đó — vì vậy không nên **suy luận ngữ cảnh đúng chỉ từ tên method**.

Các cách phù hợp tùy hệ thống:

1. **Decorator/wrapper cho task** chụp context lúc tạo task, thiết lập/restore khi task chạy.
2. **TaskDecorator/ContextPropagator** do framework cung cấp (nếu có), được gắn tập trung vào executor.
3. **Tracing instrumentation** truyền trace/span context theo hợp đồng của observability stack.
4. **Reactive Context** của framework phản ứng, thay vì phụ thuộc vào một `ThreadLocal` xuyên nhiều thread.
5. **Per-event explicit attributes** cho dữ liệu chỉ thuộc một lần log, giảm phụ thuộc vào thread context.

Không tự viết một bộ propagation cho tất cả framework chỉ bằng cách copy `MDC.getCopyOfContextMap()` nếu hệ thống có tracing/security context riêng. Cần xem xét thêm context của trace, identity, locale và transaction; đồng thời tránh mang những dữ liệu nhạy cảm không cần thiết sang task nền.

**Đặc biệt:** logging async (AsyncAppender/AsyncLogger) khác với nghiệp vụ async. Appender có thể chụp MDC của một `LogEvent` ngay lúc phát log nhưng **không tự truyền context sang task của `CompletableFuture` trước khi task ấy gọi logger**.

## 14. Context snapshot phải an toàn và có ý nghĩa

Một snapshot tốt nên:

- Được tạo **ở nguồn** khi scope đang hợp lệ, không phải “mượn” dữ liệu còn sót trên worker.
- Chứa **các key được phép** và giá trị đã được validate; không giữ request body, token hoặc object nặng.
- Được truyền như **bản sao**, không dùng chung một mutable map bị thread khác thay đổi.
- Có **vòng đời giới hạn**: task timeout/cancel không khiến context được giữ trong queue vô hạn.
- Được **cài tạm thời**, xử lý, rồi khôi phục/clear trong `finally`.
- Có kế hoạch cho **context không tồn tại**: null/absent theo schema, không lấy giá trị cũ.
- Tuân theo **trace/span hiện tại**; không dùng `requestId` giả làm `traceId`.

Trong pipeline có structured JSON logging, việc context được truyền đúng chưa đủ. Encoder/collector phải xuất đúng field name/type. Nếu `requestId` trong MDC nhưng encoder chỉ ghi `message`, query theo field `requestId` vẫn không hoạt động. Đây là lỗi **schema/encoding**, không phải stale context.

## 15. Kiểm thử khả năng chống stale context

### 15.1. Bắt buộc thử tái sử dụng cùng một worker thread

Đừng chỉ gửi hai request song song và thấy “có vẻ đúng”; chúng có thể chạy trên hai thread khác nhau nên bug chưa lộ. Dùng **single-thread executor** hoặc cấu hình test tương đương:

```text
Worker #1:
  Request A: requestId=req-A
  Request A ends
  Request B: requestId=req-B
  Request B ends
  Task without request: requestId absent

PASS:
  Log A mang req-A.
  Log B mang req-B.
  Log cuối không mang req-A hoặc req-B.
```

Demo ở mục 9 cố ý dùng single-thread executor và `Future.get()` để kiểm tra chính trường hợp này.

### 15.2. Kiểm thử exception và early return

Cho `processRequest()` throw một exception có kiểm soát. Ở task kế tiếp trên cùng worker, kiểm tra rằng `MDC.get("requestId")` không còn giá trị cũ. Nếu wrapper khôi phục snapshot hợp lệ của caller, so sánh với trạng thái trước scope, không nhất thiết lúc nào cũng phải rỗng.

### 15.3. Kiểm thử nested scopes

Đặt `operationId=checkout`, vào scope tạm `operationId=payment`, sau đó xác nhận trả về `checkout`. Kiểm tra cả nhánh bình thường và nhánh có exception. Chỉ kiểm tra “không có field payment” là chưa đủ nếu bạn vô tình xóa field checkout.

### 15.4. Kiểm thử propagation và cancellation

Test executor task được submit khi caller có context, chạy sau khi caller đã cleanup và bảo đảm nó dùng snapshot đúng. Đồng thời kiểm tra cancellation, timeout và task fault không để lại context trên worker. Nếu task không chạy vì bị cancel, closure chứa snapshot có thể còn được giữ trong queue/tracker một thời gian; thiết kế lifecycle tránh giữ dữ liệu nhạy cảm không cần thiết.

### 15.5. Kiểm thử dữ liệu JSON thực tế

Với structured logging, parse output sau encoder và assert:

```text
event=request.started, requestId=req-A
event=work.completed, requestId=req-A
event=request.started, requestId=req-B
event=work.completed, requestId=req-B
event=worker.idle, requestId absent hoặc null theo schema
```

Không chỉ assert chuỗi `"req-B"` có xuất hiện. Cần xác nhận **đúng key**, value, event, kiểu dữ liệu và producer. Với Logback pattern text ở demo, `none` là giá trị trình bày cho thiếu key, không có nghĩa JSON sẽ chứa literal `"none"`.

## 16. Những lỗi thường gặp và hướng xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách sửa |
| --- | --- | --- |
| Log request B mang `req-A` | Worker thread còn MDC từ A. | Clear/restore context tại ranh giới request, test reuse một thread. |
| Context còn sau exception | Cleanup đặt sau call có thể throw. | Dùng `try/finally` hoặc scoped API. |
| Logger ở task con thiếu requestId | Chỉ set MDC trên caller thread. | Capture khi submit, set/restore trong worker. |
| Sửa bằng cách set MDC bên trong callback sau khi đã chạy | Context nguồn đã bị cleanup hoặc worker có giá trị cũ. | Truyền snapshot/correlation ID từ thời điểm tạo task. |
| Nested operation mất context ngoài | `remove(key)` thay vì restore giá trị trước. | Lưu giá trị cũ và khôi phục trong `finally`. |
| Dùng `MDC.clear()` trong service method làm mất trace | Service không sở hữu toàn bộ MDC. | Chỉ xóa key mình quản lý, dùng scope có ownership. |
| `putCloseable` đóng xong không còn giá trị cũ | Close chỉ cleanup key, không phục hồi snapshot như kỳ vọng. | Helper restore key hoặc map. |
| Tưởng `InheritableThreadLocal` truyền đúng qua pool | Pool worker được tạo trước request. | Propagation explicit hoặc task decorator của framework. |
| Context của task async bị thay khi caller đi tiếp | Dùng chung mutable map hoặc chụp sai thời điểm. | Snapshot bất biến tại submit, tránh share map. |
| `traceId` không nối với tracing | ID tự đặt hoặc context trace cũ. | Lấy từ tracer active, propagation chính thức. |
| ID bị lẫn giữa tenant | Không cleanup tenantId, quá nhiều field request trong MDC. | Scope riêng, allowlist và test cross-tenant. |
| AsyncAppender không “sửa” stale context | Nhầm async output với async execution. | Xử lý context trước khi task gọi logger. |
| Có context trên MDC nhưng JSON thiếu field | Encoder không xuất MDC hoặc schema map sai. | Cấu hình structured encoder và kiểm tra JSON thực tế. |
| Một event có context đúng nhưng outcome sai | Đặt outcome ở request scope rồi quên cập nhật sau retry. | Phát outcome ở event nơi có kết quả cuối. |
| Cảnh báo có dữ liệu nhạy cảm trong log | Gắn token, cookie hoặc header vào MDC. | Tránh/loại field nhạy cảm tại nguồn, retention và phân quyền. |
| Log trùng từ appender/root | Lỗi additivity/handler, không phải stale MDC. | Kiểm tra cấu hình appender và propagation riêng. |

## 17. Checklist trước khi triển khai

- [ ] Có xác định **owner** của từng context key: request, trace, job, operation hay resource?
- [ ] Ở đầu request/job, context được thiết lập từ dữ liệu tin cậy, không “kế thừa” ID còn sót?
- [ ] Mỗi đường đi có `finally` hoặc scope close, kể cả exception và early return?
- [ ] Nested scope biết **khôi phục** field cũ thay vì chỉ remove?
- [ ] Không gọi `MDC.clear()` tại lớp không sở hữu toàn bộ context?
- [ ] Các pooled worker thread có kiểm thử reuse liên tiếp request A rồi B?
- [ ] Snapshot khi submit async task có đúng thời điểm và không dùng chung mutable map?
- [ ] Executor/CompletableFuture/reactive/tracing propagation được tích hợp có kiểm chứng?
- [ ] Trường hợp không có requestId/traceId xử lý absent/null đúng schema, không dùng giá trị cũ?
- [ ] Token, session cookie, password, header và payload không cần thiết không nằm trong MDC?
- [ ] Context ID đã được validate độ dài và ký tự khi đến từ bên ngoài?
- [ ] Mọi producer thống nhất `requestId`, `traceId`, `tenantId` và kiểu dữ liệu?
- [ ] Structured encoder thực sự xuất context thành field nếu dashboard cần truy vấn theo field?
- [ ] Có test exception, nested scope, cancellation, task không context và cross-tenant?
- [ ] Có khả năng phát hiện worker còn context trước khi nhận task mới mà lẽ ra phải sạch?

## 18. Câu hỏi tự kiểm tra

1. Vì sao pooled thread làm stale MDC xuất hiện ngay cả khi code chỉ dùng một `ThreadLocal`?
2. Tại sao cleanup sau `processRequest()` nhưng ngoài `finally` là không đủ?
3. Với nested scope, `remove("operationId")` có luôn đúng không?
4. Tại sao `MDC.clear()` của main thread không xóa MDC trong executor worker?
5. Chụp snapshot bên trong worker sau khi caller đã cleanup có rủi ro gì?
6. AsyncAppender có tự truyền requestId cho `CompletableFuture` không?
7. Tại sao `InheritableThreadLocal` không bảo đảm context đúng khi dùng thread pool?
8. Trong Java 17 demo, vì sao `event=worker.idle` được mong đợi có `requestId=none`?
9. Khi nào nên dùng `MDC.clear()` và khi nào nên khôi phục một key cũ?
10. Nếu request không có active trace, có nên giữ traceId từ request trước để truy vết dễ hơn không?
11. Tại sao cùng field `tenantId` sai có thể trở thành rủi ro bảo mật, không chỉ lỗi dashboard?
12. Một test chỉ thấy event `req-B` có mặt có đủ chứng minh context của B không bị lẫn không?

**Kết luận:** Để **tránh context lỗi thời**, cần quản lý MDC/ThreadContext như **trạng thái có phạm vi và chủ sở hữu**, không phải chỗ lưu metadata vĩnh viễn của thread. **Thiết lập đúng lúc, chụp snapshot trước khi đổi thread, cleanup/restore trong `finally`, tách context theo request/operation và kiểm thử tái sử dụng thread** là những biện pháp quan trọng nhất. Những quy tắc đó giữ correlation chính xác, giảm nguy cơ gán nhầm log cho request hoặc tenant khác và bảo vệ khả năng điều tra sự cố.