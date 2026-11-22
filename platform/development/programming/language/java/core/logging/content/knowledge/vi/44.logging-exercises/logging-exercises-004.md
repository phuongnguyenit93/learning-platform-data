# Dự án thực hành: Thêm MDC vào Java Core Logging

## 1. Bài toán và mục tiêu

Một ứng dụng Java xử lý nhiều HTTP request, message hoặc background task cùng lúc. Các câu như `"Order received"`, `"Payment failed"` thường không đủ để biết bản ghi thuộc request nào, tenant nào và có liên quan tới các log ở worker thread hay không. Nếu chỉ nối `requestId` bằng tay vào từng lời gọi `logger.info(...)`, rất dễ thiếu field hoặc chép nhầm ID.

**MDC — Mapped Diagnostic Context** là một bản đồ key–value gắn với **ngữ cảnh thực thi của thread** mà logging backend có thể dùng để bổ sung vào mỗi log event. Với SLF4J và Logback, code có thể gọi `MDC.put("requestId", ...)` một lần tại boundary, sau đó cấu hình Logback dùng `%X{requestId}` để xuất giá trị vào nhiều dòng log trong scope đó.

Bài thực hành xây dựng **một dự án Maven chạy bằng Java 17**, bổ sung:

- `requestId`: định danh request để tra cứu log cùng thao tác.
- `tenantRef`: định danh tenant giả đã được hệ thống xác minh (không phải token hay chứng cứ phân quyền).
- Scope `try/finally`: bảo đảm khôi phục MDC kể cả khi có exception.
- Wrapper truyền snapshot MDC khi gửi task sang `ExecutorService`.
- Một tác vụ không có request context để kiểm chứng **không bị rò MDC** từ tác vụ trước.
- `logback.xml` với pattern `%X{key:-default}` và JUnit test để kiểm tra propagation/cleanup.

**Sau bài học**, người học biết thêm MDC vào logger thật, hiểu khác biệt giữa context trên thread và context xuyên service, sửa lỗi “request B dính requestId của A”, và xác minh bằng output thay vì chỉ dựa vào cảm giác.

> **Phạm vi:** Dự án này thực sự dùng `org.slf4j.MDC` + `logback-classic`. Nó không dùng `ThreadLocal` tự chế thay cho MDC. Các ID như `req-A` hoặc `tenant-1` là **dữ liệu giả cố định** để kết quả chạy tái lập; trong production chúng phải đến từ boundary đáng tin cậy.

## 2. Kiến thức nền: MDC và message template

### Một lời gọi log trước/sau MDC

Trước:

~~~java
LOG.info("event=order_processed");
~~~

Output có thể là:

~~~text
event=order_processed
~~~

Khi MDC đã có `requestId=req-A` và `tenantRef=tenant-1`, lời gọi **không cần đổi**, nhưng encoder có thể xuất:

~~~text
event=order_processed requestId=req-A tenantRef=tenant-1
~~~

MDC **không chỉnh sửa business event**, không biến error thành success và không thay thế các field riêng của event (`errorCode`, `durationMs`, `orderRef`...). Nó làm giàu log bằng metadata thuộc **scope xử lý**.

### Ba nguồn dữ liệu nên phân biệt

| Nguồn | Ví dụ | Cách sử dụng phù hợp |
| --- | --- | --- |
| **MDC request/message scope** | `requestId`, `tenantRef`, `correlationId` | Cùng giá trị xuyên nhiều log trong một scope |
| **Event attributes** | `event`, `errorCode`, `outcome`, `durationMs` | Trường riêng của lần ghi log; SLF4J 2.x hỗ trợ `addKeyValue` |
| **Resource/deployment** | `service.name`, `service.version`, environment | Thường lấy từ cấu hình triển khai/telemetry resource, không phải request |

`MDC.put` không tự xuất log: nó chỉ thay đổi map của thread. `%X{requestId}` trong pattern không sinh ID mới: nó chỉ đọc giá trị nếu backend có MDC và code đã đặt trường. MDC của Logback về cơ bản **không tự được truyền sang child thread hoặc thread pool**. Khi gửi task qua executor, ứng dụng phải dùng wrapper hoặc cơ chế propagation của framework.

### Khi nào cần MDC?

Dùng khi nhiều event trong **cùng một scope** nên mang những field giống nhau: requestId, correlationId, traceId/spanId do tracing instrumentation hỗ trợ, tenantRef đã xác minh, jobId. Không đưa toàn bộ request body, HTTP headers, secret hoặc object `toString()` vào MDC.

Nếu chỉ một event cần `errorCode=PAY-TIMEOUT`, hãy cân nhắc **event key–value** thay vì ghi `errorCode` vào MDC rồi quên xóa khiến event thành công tiếp theo cũng mang lỗi cũ.

## 3. Công cụ và cấu trúc dự án

Yêu cầu: **JDK 17+**, **Apache Maven 3.9+** (hoặc phiên bản tương thích các plugin), terminal và editor. Kiểm tra:

~~~bash
java -version
javac -version
mvn -version
~~~

Thư mục mẫu:

~~~text
mdc-practice/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/
    │   │   └── demo/logging/mdc/
    │   │       └── MdcProject.java
    │   └── resources/
    │       └── logback.xml
    └── test/
        └── java/
            └── demo/logging/mdc/
                └── MdcProjectTest.java
~~~

Tạo dự án Maven rỗng, tạo đúng các đường dẫn rồi chép nội dung dưới đây. Đây là **bốn file độc lập có thể sử dụng** khi đặt vào đúng vị trí, không phải một vài snippet thiếu class.

**Phiên bản dùng trong mẫu** được ghim để hành vi dễ tái lập: SLF4J API 2.0.20, Logback Classic 1.6.6, JUnit Jupiter 5.12.2, Maven Compiler Plugin 3.14.1, Surefire 3.6.1 và Exec Maven Plugin 3.5.1. SLF4J 2.x tương thích với Logback 1.6.x; Logback 1.6.x yêu cầu Java 11+ nên Java 17 dùng được. Khi đưa vào ứng dụng thật, cần cập nhật bản vá và kiểm tra CVE/compatibility theo dependency management của tổ chức; không hạ phiên bản Logback chỉ để copy ví dụ cũ.

## 4. File 1 — `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo.logging</groupId>
    <artifactId>mdc-practice</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.slf4j</groupId>
            <artifactId>slf4j-api</artifactId>
            <version>2.0.20</version>
        </dependency>
        <dependency>
            <groupId>ch.qos.logback</groupId>
            <artifactId>logback-classic</artifactId>
            <version>1.6.6</version>
        </dependency>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.12.2</version>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Giải thích dependency:**

- `slf4j-api` là API logger và MDC (`Logger`, `LoggerFactory`, `MDC`).
- `logback-classic` là **một SLF4J provider/backend** thực hiện lưu và xuất MDC qua pattern. Maven tự kéo dependency `logback-core` và các phụ thuộc phù hợp. Không thêm một SLF4J provider khác vào cùng runtime nếu không có chủ ý rõ.
- `junit-jupiter` giúp test lifecycle. `maven-surefire-plugin` chạy JUnit khi dùng `mvn test`.
- `maven-compiler-plugin` với `release=17` yêu cầu mã nguồn và class bytecode phù hợp Java 17; vẫn cần JDK phù hợp trên máy.
- `exec-maven-plugin` cho phép chạy main class trực tiếp qua Maven; không cần tạo fat JAR cho bài tập.

Khi tích hợp vào Spring Boot hoặc framework có dependency management, **ưu tiên BOM/dependency versions do framework quản lý** nếu tương thích. Đừng thêm nhiều phiên bản SLF4J/Logback khiến runtime in cảnh báo “multiple providers” hoặc thiếu method.

## 5. File 2 — `src/main/resources/logback.xml`

~~~xml
<configuration>
    <appender name="CONSOLE"
              class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%msg requestId=%X{requestId:-none} tenantRef=%X{tenantRef:-none}%n</pattern>
        </encoder>
    </appender>

    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
~~~

**Ý nghĩa từng phần:**

- `%msg`: message của sự kiện logger. Bài tập đặt `event=request_received` và các tên event khác làm message.
- `%X{requestId}` / `%X{tenantRef}`: đọc giá trị tương ứng từ MDC của event.
- `:-none`: nếu key chưa có, in `none`. Đây là **giá trị hiển thị mặc định**, không tự thêm `none` vào MDC.
- `%n`: xuống dòng theo môi trường.
- `<root level="INFO">`: nhận log INFO trở lên. Ví dụ không dùng timestamp/level/thread để output học tập cố định; production nên bổ sung thời gian, severity, service và định dạng structured phù hợp.

**Không thêm nhiều appender chỉ để thấy MDC.** Nếu root và logger con cùng gắn một console appender trong khi additivity bật, một log event có thể bị in hai lần, dễ bị nhầm là lỗi MDC. Với mục tiêu bài tập, một root appender là đủ.

Pattern này là **text key=value**, chưa phải JSON; nếu field do client điều khiển chứa whitespace/newline, dữ liệu có thể làm méo parser. Vì vậy mã demo chỉ chấp nhận ID gồm chữ, số, `_` và `-`. Khi đưa vào sản phẩm nên dùng structured encoder có escaping/redaction, không dùng text pattern làm biện pháp bảo mật duy nhất.

## 6. File 3 — `MdcProject.java`: tạo scope, truyền qua worker, dọn context

Lưu tại `src/main/java/demo/logging/mdc/MdcProject.java`:

~~~java
package demo.logging.mdc;

import java.util.Map;
import java.util.Objects;
import java.util.concurrent.Callable;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

public final class MdcProject {
    private static final Logger LOG =
            LoggerFactory.getLogger(MdcProject.class);

    // Chỉ chấp nhận ID demo an toàn cho text log.
    private static final Pattern SAFE_ID =
            Pattern.compile("[A-Za-z0-9_-]{1,64}");

    private MdcProject() {
    }

    private static void validateId(String name, String value) {
        if (value == null || !SAFE_ID.matcher(value).matches()) {
            throw new IllegalArgumentException("Invalid " + name);
        }
    }

    // Khôi phục nguyên map trước scope, kể cả khi không có key nào.
    static void restore(Map<String, String> context) {
        if (context == null || context.isEmpty()) {
            MDC.clear();
        } else {
            MDC.setContextMap(context);
        }
    }

    // Một request boundary giữ các field trong phạm vi task.call().
    static <T> T withRequest(
            String requestId, String tenantRef, Callable<T> task)
            throws Exception {

        validateId("requestId", requestId);
        validateId("tenantRef", tenantRef);
        Objects.requireNonNull(task, "task");

        Map<String, String> before = MDC.getCopyOfContextMap();
        try {
            // Bài demo tách biệt hoàn toàn request A/B.
            MDC.clear();
            MDC.put("requestId", requestId);
            MDC.put("tenantRef", tenantRef);
            return task.call();
        } finally {
            // Thực thi cả khi task lỗi hoặc bị hủy.
            restore(before);
        }
    }

    // Chụp MDC tại thread SUBMIT, cài/khôi phục tại thread CHẠY.
    static Runnable captureMdc(Runnable task) {
        Objects.requireNonNull(task, "task");
        Map<String, String> snapshot =
                MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> before =
                    MDC.getCopyOfContextMap();
            try {
                restore(snapshot);
                task.run();
            } finally {
                restore(before);
            }
        };
    }

    private static void process(
            String requestId, String tenantRef,
            ExecutorService worker) throws Exception {

        withRequest(requestId, tenantRef, () -> {
            LOG.info("event=request_received");

            Future<?> future = worker.submit(captureMdc(
                    () -> LOG.info("event=background_processed")));
            future.get();

            LOG.info("event=request_finished");
            return null;
        });
    }

    public static void main(String[] args) throws Exception {
        ExecutorService worker =
                Executors.newSingleThreadExecutor();

        try {
            process("req-A", "tenant-1", worker);
            process("req-B", "tenant-2", worker);

            // Task không thuộc request: không nhận context cũ.
            worker.submit(captureMdc(
                    () -> LOG.info("event=periodic_cleanup"))).get();
        } finally {
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }
}
~~~

### Lưu ý quan trọng về Java và MDC

1. `MDC.getCopyOfContextMap()` trả một **bản sao** map hiện tại hoặc `null` khi không có context. Không chuyển một map mutable đang dùng chung giữa các requests rồi để các thread sửa nó.
2. `withRequest(...)` lấy `before` rồi khởi tạo scope request. `finally` khôi phục caller context kể cả khi `task.call()` ném exception.
3. Bài demo **`MDC.clear()` khi vào request** để dễ quan sát không rò giá trị. **Trong ứng dụng có tracing instrumentation**, việc clear toàn map có thể xóa traceId/spanId được tích hợp trước đó. Khi đó middleware phải có chiến lược phối hợp: chỉ thay các key mà mình sở hữu hoặc kế thừa đúng trace context đã xác thực rồi khôi phục snapshot sau scope. Không copy chính xác `clear()` của bài demo vào mọi framework mà chưa hiểu chain filters.
4. `captureMdc(...)` **chụp snapshot khi gọi wrapper** (trên thread producer). Trên worker, nó cài snapshot, chạy tác vụ, cuối cùng khôi phục context cũ. Việc chỉ gọi `MDC.put(...)` trên HTTP thread **không tự** chuyển giá trị sang `ExecutorService`.
5. `newSingleThreadExecutor` cố ý dùng một worker tái sử dụng, để thử trường hợp request A/B chạy nối tiếp trên **cùng thread** — nơi rò context thường khó thấy nhất.
6. `Future.get()` buộc mỗi tác vụ hoàn tất trước log `request_finished`, nên thứ tự output xác định. Với production đa luồng, không khẳng định các event từ requests độc lập có thứ tự tuyệt đối.
7. `SAFE_ID` chỉ là validate định dạng để giảm newline/log injection. Nó **không xác minh quyền tenant**. Trong API thật, `tenantRef` phải đến từ principal/authorization hoặc envelope đáng tin sau kiểm tra, không tin trực tiếp `X-Tenant-Id` do client tự gửi.
8. `requestId` là ID tương quan, không là token cấp quyền, không là error code và không dùng thay trace ID. Trường hợp ID đầu vào không đáng tin phải có boundary tạo hoặc validate ID theo hợp đồng.
9. Trong demo, `withRequest(...)` và `captureMdc(...)` là package-private để test JUnit cùng package sử dụng; có thể đóng gói vào helper/TaskDecorator riêng trong ứng dụng lớn.
10. Wrapper này phù hợp ví dụ `Runnable`/`ExecutorService`. Với `Callable<V>`, `CompletionStage`, Reactor, virtual threads hoặc framework-managed executors, cần adapter propagation đúng loại và context framework, không dùng mã này như thư viện generic cho mọi môi trường.

### Tại sao không chỉ gọi `MDC.clear()` sau task?

`MDC.clear()` đơn thuần xóa cả context có trước của worker/caller. Với một scope lồng bên trong scope khác, điều đó làm mất các key hợp lệ của lời gọi ngoài. Chụp `before` và `restore(before)` giữ được nested scope. Tuy nhiên, nếu worker **đã có MDC rò từ code sai khác**, restore `before` không tự chữa rò đã tồn tại: điểm vào của request/task độc lập phải được quản lý sạch và kiểm thử từ đầu.

## 7. Chạy thử dự án và kiểm tra output

Từ thư mục `mdc-practice`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.logging.mdc.MdcProject
~~~

**Bảy dòng log kỳ vọng từ code và pattern đã cho:**

~~~text
event=request_received requestId=req-A tenantRef=tenant-1
event=background_processed requestId=req-A tenantRef=tenant-1
event=request_finished requestId=req-A tenantRef=tenant-1
event=request_received requestId=req-B tenantRef=tenant-2
event=background_processed requestId=req-B tenantRef=tenant-2
event=request_finished requestId=req-B tenantRef=tenant-2
event=periodic_cleanup requestId=none tenantRef=none
~~~

Các dòng trên là **output logger dự kiến** với `logback.xml` đã cung cấp, chưa tính thông điệp riêng của Maven/JVM nếu một công cụ phát diagnostics hoặc cấu hình logging khác được nạp. Luồng tương đương về scope/copy/restore và thứ tự event đã được kiểm tra bằng Java `ThreadLocal` qua JShell; ví dụ SLF4J/Logback cần được chạy bằng các dependency Maven trên môi trường người học để xác minh thực tế.

Điểm quan sát:

- Cặp `request_received`/`request_finished` cho mỗi request có cùng `requestId` và `tenantRef`.
- `background_processed` chạy trên worker nhưng vẫn giữ đúng ngữ cảnh snapshot tại thời điểm submit.
- Request B **không mang** `req-A` hoặc `tenant-1` dù tái sử dụng worker.
- `periodic_cleanup` không nằm trong request nên dùng default `none`. Nó **không có requestId giả**.
- Không cần truyền ID vào lời gọi `LOG.info(...)` ở mỗi phương thức; layout đọc MDC theo scope.

Nếu log chỉ hiện message mà không có `requestId`, kiểm tra `src/main/resources/logback.xml` có trên runtime classpath, phiên bản provider, pattern `%X` và lời gọi `MDC.put`. Nếu worker in `none` cho cả A/B, wrapper đã không được gọi **trước khi submit**, hoặc context đã bị xóa quá sớm.

## 8. File 4 — Unit test JUnit cho propagation và cleanup

Lưu ở `src/test/java/demo/logging/mdc/MdcProjectTest.java`:

~~~java
package demo.logging.mdc;

import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.slf4j.MDC;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

class MdcProjectTest {
    @Test
    void scopeRestoresCallerEvenWhenTaskThrows() {
        MDC.clear();
        MDC.put("requestId", "caller");

        try {
            assertThrows(IllegalStateException.class, () ->
                    MdcProject.withRequest(
                            "req-X", "tenant-X", () -> {
                                assertEquals(
                                        "req-X", MDC.get("requestId"));
                                assertEquals(
                                        "tenant-X", MDC.get("tenantRef"));
                                throw new IllegalStateException(
                                        "expected");
                            }));

            assertEquals("caller", MDC.get("requestId"));
            assertNull(MDC.get("tenantRef"));
        } finally {
            MDC.clear();
        }
    }

    @Test
    void copiedContextReachesWorkerButDoesNotLeak() throws Exception {
        ExecutorService worker =
                Executors.newSingleThreadExecutor();
        MDC.clear();

        try {
            MDC.put("requestId", "req-A");
            MDC.put("tenantRef", "tenant-1");

            AtomicReference<String> seen =
                    new AtomicReference<>();
            worker.submit(MdcProject.captureMdc(() ->
                    seen.set(MDC.get("requestId")
                            + "/" + MDC.get("tenantRef")))).get();

            assertEquals("req-A/tenant-1", seen.get());

            // Task kế tiếp trên cùng worker, không qua wrapper:
            // MDC của task A đã được khôi phục về trạng thái trống.
            assertNull(worker.submit(
                    () -> MDC.get("requestId")).get());

            // Thread caller vẫn giữ ngữ cảnh của A.
            assertEquals("req-A", MDC.get("requestId"));
        } finally {
            MDC.clear();
            worker.shutdown();
            if (!worker.awaitTermination(5, TimeUnit.SECONDS)) {
                worker.shutdownNow();
            }
        }
    }

    @Test
    void rejectsUnsafeIdsBeforeLogging() {
        MDC.clear();
        assertThrows(IllegalArgumentException.class, () ->
                MdcProject.withRequest(
                        "req-bad\ninjection", "tenant-1",
                        () -> null));
        assertNull(MDC.get("requestId"));
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Đầu ra Surefire phụ thuộc Maven và môi trường, nhưng **kết quả mong đợi là 3 tests, 0 failures, 0 errors**. Có thể xem báo cáo test trong `target/surefire-reports/`. Không cần snapshot toàn bộ console làm assertion, vì message timestamp/thread có thể khác nếu đổi pattern.

**Tại sao ba test này cần thiết?**

1. **Exception path**: `finally` khôi phục caller MDC ngay cả khi work bị lỗi.
2. **Executor path**: snapshot của request A đến được worker; khi task kết thúc, worker không giữ `requestId` của request A. Caller không bị thay đổi.
3. **Input validation**: chuỗi xuống dòng không được đưa vào MDC/log, tránh tạo dòng log giả.

Các test là bước nền, không thay thế integration test với HTTP filter, message consumer hoặc tracing agent thật. Với hệ thống reactive, phải test propagation trên schedulers/callbacks riêng.

### Bài tập kiểm chứng lỗi bằng cách cố tình sửa

Trong môi trường **dev/test**, thử bỏ wrapper ở lời gọi:

~~~java
// Chỉ để quan sát lỗi trong bài tập, không dùng ở bản cuối.
Future<?> future = worker.submit(
        () -> LOG.info("event=background_processed"));
~~~

Kết quả worker có thể in `requestId=none tenantRef=none` mặc dù request thread có context. Trên Logback với executor và cách đặt scope của bài, MDC không tự lan tới worker. Sau khi nhìn thấy, **khôi phục `captureMdc(...)`** và chạy lại ba test.

Thử bỏ `finally` trong `withRequest`: caller còn `requestId=req-A` sau khi xử lý, tác vụ ngoài request có thể nhận sai context. Đây là lý do cần restoration kể cả trên exception path.

**Không tạo lỗi này trên hệ thống production chỉ để kiểm tra.**

## 9. Tích hợp MDC vào ứng dụng HTTP thực

Trong ứng dụng servlet, nơi tự nhiên để thiết lập MDC là **Filter/middleware**:

~~~text
HTTP request arrives
   |
   v
Authenticate / verify tenant
   |
   v
Read-or-generate trusted requestId
   |
   v
Capture previous MDC; put requestId/tenantRef
   |
   v
Controller -> Service -> Repository logs
   |
   v
finally: restore original MDC
   |
   v
HTTP response
~~~

Pseudo-Java snippet (không phải servlet class biên dịch độc lập):

~~~java
Map<String, String> before = MDC.getCopyOfContextMap();
try {
    MDC.put("requestId", verifiedOrGeneratedRequestId);
    MDC.put("tenantRef", trustedTenantRef);
    filterChain.doFilter(request, response);
} finally {
    if (before == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(before);
    }
}
~~~

**Đoạn này khác demo `withRequest` ở chỗ nó giữ các key khác có trước** (ví dụ trace context do agent đã đặt). Chỉ áp dụng khi boundary/framework đã có cơ chế làm sạch context của request riêng và không có stale keys; nếu muốn reset các key do middleware sở hữu, hãy lưu/restore chính chúng hoặc xây scope adapter theo framework. `verifiedOrGeneratedRequestId` phải được validate về độ dài, ký tự, namespace và trust. `trustedTenantRef` phải đến từ authorization context, không lấy raw client header làm bằng chứng quyền truy cập.

Các điểm triển khai:

- Đặt middleware sao cho log của controller/service nhìn thấy MDC nhưng context được dọn sau khi request kết thúc.
- Một filter chạy trước authentication không thể khẳng định `tenantRef` đáng tin; có thể thêm sau khi principal được xác thực.
- Nếu servlet bắt đầu `async request`, thread xử lý sau có thể khác; cần propagation phù hợp và lifecycle async callback, không giả định `finally` của filter bao trùm mọi công việc bất đồng bộ.
- Một request không có user/tenant (health check) có thể bỏ trường `tenantRef` hoặc dùng giá trị được quy định, không suy đoán một tenant.
- TraceId/spanId cần lấy từ instrumentation; **không** tự tạo chuỗi giả có tên `traceId` để khiến dashboard tưởng đã có trace thực.

## 10. Tích hợp MDC trong message consumer và job

Với consumer Kafka/RabbitMQ/JMS, MDC thường được đặt khi **bắt đầu xử lý message**, dọn khi callback kết thúc. Ví dụ luồng:

~~~text
receive message
   |
   +-- validate envelope/messageId, tenant permission, correlation context
   |
   +-- MDC.put("messageId", ...)
   +-- MDC.put("tenantRef", ...)
   |
   +-- process + retry/fallback/logging
   |
   +-- finally restore/clear MDC
   |
   +-- ACK/NACK/commit theo broker contract
~~~

Không có cơ chế MDC nào tự truyền messageId/traceId qua broker. Producer phải đưa metadata tương quan vào **message headers/envelope**, consumer đọc/kiểm tra rồi mới thiết lập scope cục bộ.

Lưu ý:

- `messageId` của application có thể giữ nguyên qua redelivery; `deliveryAttempt` là field khác.
- Đừng dùng broker offset, RabbitMQ deliveryTag hoặc MDC tenantRef như một idempotency key mặc định.
- Nếu code bắt exception để retry, scope MDC phải được đóng sau mỗi attempt; không để attempt B thấy thông tin của message A.
- Nếu caller gửi task tới executor hoặc `CompletableFuture`, dùng wrapper/task decorator/context propagation phù hợp; không dựa vào tên thread để nối message.
- Log của scheduler không gắn một requestId giả nếu job không thuộc request. Dùng `jobId` hoặc `runId` được định nghĩa.

MDC là **observability metadata**, không tự cung cấp ACK, retry, transaction, durability hoặc bảo đảm exactly-once.

## 11. MDC và ThreadLocal, virtual threads, async appenders

Logback MDC có phạm vi **thread**. Điều này dẫn đến vài giới hạn:

- **Thread pool:** task chạy trên thread tái sử dụng; phải capture/restore, tránh dữ liệu cũ.
- **`CompletableFuture`:** callback có thể chạy trên thread khác hoặc ngay trên thread hoàn tất; cần propagation ở boundary tương ứng, không lấy MDC của caller tại thời điểm callback một cách tùy tiện.
- **Reactor/async frameworks:** công việc có thể nhảy scheduler liên tục; sử dụng integration/context propagation do framework cung cấp thay vì `MDC.put` tại một chỗ rồi giả định đi theo chuỗi reactive.
- **Virtual threads:** MDC vẫn là context gắn với thread đang chạy nhưng có nhiều virtual threads ngắn hạn; khả năng liên kết giữa những task không tự xuất hiện. Hãy đo tác động ThreadLocal và tuân theo framework tracing context.
- **Async appender:** sự kiện có thể được format trên thread khác sau khi request scope đã đóng. Backend cần chụp MDC trong **log event** tại thời điểm phát; đừng đọc `MDC.get("requestId")` trên thread writer rồi gán cho event nguồn. Logback hỗ trợ MDC trong event, nhưng cần kiểm tra cả pipeline cụ thể khi có custom layout/bridge.

Nếu cần truyền `Runnable`/`Callable<T>` và không muốn tự viết wrapper cho mọi chỗ, có thể dùng `TaskDecorator`/instrumentation của framework; vẫn cần test A → B → task không context trên cùng thread pool.

### `MDC.putCloseable` có đủ cho nested scopes?

SLF4J cung cấp `MDC.putCloseable(key, value)` để dùng với try-with-resources:

~~~java
// Snippet có SLF4J: thích hợp khi chỉ quản lý một key.
try (MDC.MDCCloseable ignored =
             MDC.putCloseable("requestId", "req-A")) {
    LOG.info("event=started");
}
~~~

Khi `close()`, helper **remove key đó**. Nó không hứa khôi phục **giá trị cũ của cùng key** trong nested scope. Nếu caller đã có `requestId=outer` và bên trong dùng `putCloseable` với `req-A`, sau đóng có thể **mất key** thay vì trả lại `outer`. Bài tập dùng snapshot/restore full map để tránh lỗi này.

Ngoài ra, `MDC.putCloseable` chỉ quản lý thread hiện tại, **không tự propagate** khi submit task tới executor.

## 12. Khi thêm MDC vào structured logging và OpenTelemetry

Đừng nhầm MDC với một JSON encoder hoặc trace context:

- **MDC** cung cấp map key–value trong scope thread.
- **PatternLayout `%X`** biến giá trị thành một phần của text output.
- **Structured logging encoder** có thể xuất MDC như fields JSON để filter/index chính xác.
- **OpenTelemetry logs** có `Resource`, `Attributes` và chuyên biệt `TraceId`/`SpanId`. Bridge/appender/collector có thể map MDC vào attributes, nhưng hành vi tùy instrumentation, backend và cấu hình.
- **Distributed trace** cần trace context thực được extract/inject qua HTTP/message với propagator thích hợp. Tự đặt `MDC.put("traceId", randomValue)` không tạo span và có thể khiến tìm trace thất bại.

Ví dụ với SLF4J 2.x, các field riêng của log event nên dùng fluent key–value:

~~~java
// Snippet, cần SLF4J 2.x và backend/encoder hỗ trợ.
LOG.atInfo()
   .addKeyValue("event", "order_processed")
   .addKeyValue("durationMs", 28)
   .addKeyValue("outcome", "success")
   .log("Order processing completed");
~~~

Nếu MDC đã chứa `requestId`/`tenantRef`, các event fields cùng scope và event-specific fields có thể được kết hợp **khi encoder được cấu hình hỗ trợ**. Không phải pattern từ mục 5 tự in `addKeyValue`: muốn JSON typed fields cần lựa chọn encoder/layout và test output thực.

### Không nên đưa gì vào MDC?

| Trường | Đánh giá |
| --- | --- |
| `requestId` dạng opaque, đã validate | Thường phù hợp |
| `correlationId` cho workflow | Phù hợp nếu contract rõ |
| `tenantRef` từ principal xác thực | Có thể phù hợp, nhưng cần policy phân quyền |
| `traceId` từ active tracing context | Có thể dùng khi integration phù hợp |
| `durationMs`, `outcome` riêng từng event | Thường tốt hơn ở event fields |
| Password, OTP, JWT, cookie, API key | **Không đưa vào MDC/log** |
| Full URL query, body, headers | Không đưa nguyên vẹn; dễ lộ dữ liệu |
| Email, số điện thoại, user identifier bền vững | Chỉ khi thực sự cần và được phép; cân nhắc pseudonymization |
| Raw `toString()` của request/entity | Không; dễ rất dài và lộ PII |

MDC **không phải kho lưu phiên làm việc** hay authorization context. Biết `tenantRef=tenant-1` trong log không cho phép người xem truy xuất log tenant đó; backend phải enforce RBAC/tenant isolation độc lập.

## 13. Chi phí và hiệu năng

Mỗi key MDC xuất trong mọi dòng log làm tăng dung lượng. Nếu 100.000 log events/ngày, thêm vài trăm byte cho mỗi event có thể tăng hàng chục MB/ngày trước khi index/replicate. Chỉ nên thêm trường có giá trị điều tra thật.

- Đặt MDC ở **boundary**, không viết `MDC.put(...)` trong mọi lời gọi log.
- Không nhét exception stack trace hay object lớn vào map.
- Dùng field name nhất quán và schema có chủ sở hữu.
- Không dùng `requestId`/`userId`/`messageId` làm **metric labels** trong Prometheus: cardinality gần bằng số request/đối tượng, rất tốn time series.
- Đo chi phí khi truyền context qua hàng nghìn tasks/giây; snapshot map và tạo wrapper đều có overhead. Nếu MDC có hàng chục field, đây cũng là dấu hiệu đang enrich quá mức.
- Backend có async queue có thể drop/block theo policy; MDC đúng không bảo đảm event đã được ghi bền vững.
- Nếu application log và trace được ingest qua hai tuyến, tránh duplicate ingestion không chủ đích.

MDC giúp tìm kiếm theo request, nhưng chất lượng vẫn phụ thuộc error code, event name, timestamp, storage retention và khả năng truy cập log. Thêm `requestId` không sửa được một log message không mô tả điều gì đã xảy ra.

## 14. Sự cố thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Hướng sửa |
| --- | --- | --- |
| Log chỉ có message, không có ID | `logback.xml` không được nạp hoặc pattern thiếu `%X` | Kiểm tra runtime classpath, backend và pattern |
| `requestId=none` trong controller | MDC chưa đặt trước log, hoặc bị clear sớm | Thiết lập ở đúng request boundary |
| `requestId=none` trong worker | Không capture/restore khi qua executor | Dùng `captureMdc(...)`/TaskDecorator |
| Request B mang ID của A | Không dọn MDC trên thread pool | `finally` restore/clear, test A→B→no-context |
| Sau scope lồng nhau mất ID caller | Dùng `MDC.clear()` hoặc `putCloseable` làm mất key trước | Chụp và khôi phục map/key trước scope |
| Đặt traceId nhưng không mở được trace | ID tự tạo, không có active span/exporter | Lấy context từ tracing SDK |
| Không có giá trị MDC khi dùng SLF4J | Backend thiếu provider hỗ trợ hoặc API/provider lệch phiên bản | Kiểm tra dependency tree, chọn một backend |
| Nhiều dòng console cho một event | Logger hierarchy/additivity hoặc appender trùng | Sửa routing; không đổ lỗi cho MDC |
| `tenantRef` sai hoặc bị spoof | Tin raw request header | Lấy tenant từ authenticated principal |
| Log có newline giả | Không validate input | Bound length và escape/control-character handling |
| Logger có ID nhưng JSON backend mất field | Encoder/collector không map MDC | Integration test structured output |
| MDC `errorCode` còn sau khi đã phục hồi | Đưa dữ liệu event vào scope quá dài | Dùng event key–value hoặc scope ngắn |
| Query metrics quá nặng | requestId làm label metrics | Dùng ID trong log/traces, label hữu hạn |
| Test pass nhưng production rò MDC | Framework async/callback khác demo | Test với executor/filter/consumer thực |
| Log chứa email/token từ MDC | Thêm dữ liệu nhạy cảm không có data minimization | Whitelist metadata, redaction ở nguồn |

**Cách kiểm tra dependency** khi chương trình không chạy:

~~~bash
mvn dependency:tree
~~~

Tìm `org.slf4j:slf4j-api` và **một** SLF4J backend/provider dự kiến (ví dụ `logback-classic`). Với ứng dụng đã có Spring Boot, provider có thể do starter mang theo; không thêm `slf4j-simple` cạnh Logback để “chữa lỗi” vì việc có nhiều provider có thể tạo cảnh báo hoặc hành vi chọn backend không mong muốn.

## 15. Bộ tiêu chí nghiệm thu bài tập

Một bản triển khai “Thêm MDC” được xem là đạt yêu cầu khi:

1. Dự án compile với Java 17 và dùng **SLF4J MDC thật** cùng Logback.
2. `logback.xml` có `%X{requestId:-none}` và `%X{tenantRef:-none}`.
3. Request A có đúng `req-A/tenant-1` ở cả log request và worker.
4. Request B có đúng `req-B/tenant-2`, **không** chứa context A.
5. Job không thuộc request in `requestId=none tenantRef=none`.
6. Scope có `try/finally` và caller context được restore khi có exception.
7. Worker được capture MDC **trước lúc submit** và dọn sau xử lý.
8. `mvn test` có **ba tests pass**, gồm cleanup khi throw, propagation và validate ID.
9. Không sử dụng client tenant header không xác thực để phân quyền hoặc route log.
10. Không log secret/PII quá mức; có chiến lược typed structured output nếu dùng collector.
11. Đã test trường hợp logging provider/version thực tế, không chỉ unit test nội bộ.
12. Có chú thích rõ MDC **không tự truyền qua HTTP/message broker** và không tự tạo distributed trace.

### Bài tập mở rộng có kiểm chứng

**A. Thêm `correlationId`:** đặt một ID hợp lệ cùng request, sửa pattern để hiển thị; bổ sung test rằng nó đi qua worker và không rò sang request kế. Không tạo ID mới cho mọi log event.

**B. Thêm `traceId` đúng cách:** tích hợp OpenTelemetry Java instrumentation, lấy trace/span ID từ **active context**, xuất vào log qua bridge/encoder được hỗ trợ; test rằng trace link mở được khi span được export. Không dùng chuỗi giả để chứng minh tracing.

**C. Bắt lỗi worker:** cho worker ném exception; dùng `Future.get()` tại caller để biết failure, giữ finally cleanup và chỉ ghi stack trace một lần ở boundary quyết định outcome. Không log và rethrow ở mọi tầng.

**D. Tích hợp filter Spring/Servlet:** áp dụng MDC tại request boundary thực, thiết lập `requestId` từ header đã validate hoặc server-generated, `tenantRef` từ authentication. Test hai requests trên cùng thread pool và exception path; tránh xóa context mà tracing instrumentation khác sở hữu.

**E. JSON encoder:** thay pattern text bằng encoder JSON tương thích backend và xuất MDC như fields. Viết integration test assert field `requestId`/`tenantRef` có kiểu string, không chứa newline giả và không ghi token.

## 16. Checklist đưa vào production

- [ ] Xác định scope và ownership của các MDC keys: requestId, tenantRef, correlationId, traceId.
- [ ] Tạo/validate ID ở boundary; tenant phải lấy từ thông tin đã được xác thực.
- [ ] Thiết lập MDC một lần ở đầu scope và **restore trong finally** ở mọi exit path.
- [ ] Phối hợp với tracing instrumentation để không xóa key/context do thành phần khác sở hữu.
- [ ] Chụp MDC trước khi gửi task qua thread pool; adapter tương ứng cho async/reactive/broker.
- [ ] Dùng Logback pattern/structured encoder phù hợp và test output **thật**.
- [ ] Không log secret, PII không cần thiết hoặc raw headers/payload.
- [ ] Giới hạn length/charset và tránh log injection.
- [ ] Không đặt requestId/userId vào metric labels hoặc Resource fields toàn cục.
- [ ] Kiểm thử request A→B→no-context, nested scope, exception path, cancellation và retries.
- [ ] Kiểm tra backend/provider, duplicate appenders, latency/drop và retention của log.
- [ ] Tài liệu hóa các key, schema, quyền xem log và quy tắc cập nhật dependency.

**Kết luận:** Thêm MDC đúng không chỉ là gọi `MDC.put(...)`. Cần **xác định nguồn ID đáng tin**, **chọn key hữu ích**, **bảo vệ vòng đời theo request**, **truyền context qua async boundary**, **cấu hình backend thật sự in MDC**, và **kiểm thử không rò giữa các tác vụ**. Dự án Java 17 ở trên tạo một chu trình đầy đủ để quan sát và kiểm chứng các yêu cầu đó.

### Tài liệu tham khảo

- Logback — [Mapped Diagnostic Context](https://logback.qos.ch/manual/mdc.html): cách dùng MDC, scope theo thread, khuyến nghị dọn trong `finally` và snapshot cho executor.
- Logback — [Layouts và cú pháp `%X{key:-default}`](https://logback.qos.ch/manual/layouts.html); [Logback 1.6 release notes](https://github.com/qos-ch/logback/releases).
- SLF4J — [Manual](https://www.slf4j.org/manual.html), [MDC API/Javadocs](https://www.slf4j.org/apidocs/org/slf4j/MDC.html), [Download/versions](https://www.slf4j.org/download.html).
- Maven — [Compiler Plugin](https://maven.apache.org/plugins/maven-compiler-plugin/), [Surefire](https://maven.apache.org/surefire/maven-surefire-plugin/), [Exec Maven Plugin](https://www.mojohaus.org/exec-maven-plugin/).
- JUnit — [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/).
- OpenTelemetry — [Context propagation](https://opentelemetry.io/docs/concepts/context-propagation/), [Logs Data Model](https://opentelemetry.io/docs/specs/otel/logs/data-model/).
- OWASP — [Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
