# Kiểm thử ngữ cảnh MDC trong Java Logging

## 1. Mục tiêu của việc kiểm thử MDC

**Mapped Diagnostic Context (MDC)** là cơ chế của logging API giúp gắn các cặp key–value như requestId, traceId, jobId hoặc messageId vào ngữ cảnh hiện tại. Khi logger/encoder hỗ trợ và được cấu hình đúng, nhiều event log của cùng tác vụ có thể được tìm cùng một ID.

Ví dụ mong muốn:

~~~text
INFO  requestId=req-42 event=request_started
WARN  requestId=req-42 event=retry_scheduled
INFO  requestId=req-42 event=request_completed
~~~

**Kiểm thử ngữ cảnh MDC** không chỉ là gọi MDC.put rồi assert MDC.get trả đúng. Các lỗi nghiêm trọng thường xuất hiện ở ranh giới:

- Log event có ID đúng **tại lúc logger được gọi** hay không.
- Sau scope, giá trị cũ được **khôi phục** hay bị xóa/lưu lại ngoài ý muốn.
- Khi handler ném exception, cleanup vẫn chạy.
- Khi chuyển ExecutorService hoặc CompletableFuture, context có được propagate hợp lệ.
- Khi thread pool dùng lại worker, log của request B không mang requestId của A.
- Khi nhiều tác vụ đồng thời, ID không lẫn giữa hai thread.
- AsyncAppender có chụp MDC trước khi caller đổi/clear hay không.
- JSON/text encoder có thực sự xuất trường MDC; collector có parse đúng hay không.
- Các key có chứa dữ liệu cá nhân/token bị chặn trước khi phát log.

Điểm cốt lõi: **đúng trạng thái trên thread không tự chứng minh nội dung đã nằm trong log event hoặc output của pipeline**. Cần kiểm thử từng tầng và hiểu provider đang dùng.

## 2. API và semantics cần biết

SLF4J có các thao tác MDC phổ biến:

| API | Ý nghĩa | Cách kiểm thử |
| --- | --- | --- |
| MDC.put(key, value) | Đặt hoặc ghi đè một key | Trong scope giá trị mới được nhìn thấy |
| MDC.get(key) | Đọc key trên ngữ cảnh hiện tại | Mỗi task/thread nhìn ID thích hợp |
| MDC.remove(key) | Bỏ key riêng lẻ | Không còn key sau scope nếu trước đó chưa có |
| MDC.clear() | Xóa tất cả MDC của thread hiện tại | Không dùng để xóa bừa context của caller |
| MDC.getCopyOfContextMap() | Lấy bản sao map context | Snapshot không thay đổi ngoài ý muốn sau capture |
| MDC.setContextMap(map) | Thay context hiện tại bằng map | Context worker được activate và restore |
| MDC.putCloseable(key,value) | Quản lý vòng đời key qua close | Không giả định tự restore nested previous value |
| Logback ILoggingEvent.getMDCPropertyMap() | Truy vấn MDC của một event | Đọc/chụp tại thời điểm an toàn |

SLF4J là **facade/API**, Logback hoặc Log4j 2 mới là implementation cụ thể. Cách adapter lưu và chụp MDC có thể khác nhau theo phiên bản. Các test sử dụng Logback ILoggingEvent không phải test provider-independent.

MDC phổ biến dựa trên **ThreadLocal** và không tự đi theo task chạy trên executor thread khác. Child thread, inherited context, virtual threads, thread pool và reactive pipeline phải được hiểu theo provider/framework tương ứng; không lấy việc kiểm tra trên một thread để kết luận propagation ở mọi thread.

Với key không tồn tại, test nên ưu tiên **assertNull(MDC.get("requestId"))**. Không ràng buộc quá mức vào việc **getCopyOfContextMap()** trả null hay map rỗng, vì chi tiết này có thể phụ thuộc adapter/state.

## 3. Ba cấp độ kiểm thử

| Cấp độ | Điều cần khẳng định | Công cụ |
| --- | --- | --- |
| **Scope/state** | put/get/restore/remove chính xác | JUnit assertion trên MDC |
| **Logging-event** | Event giữ MDC đúng ở lúc ghi, không đọc nhầm state sau đó | Logback appender chụp event |
| **Pipeline/end-to-end** | Text/JSON encoder, async queue, stdout/file/collector có field đúng | Integration test với logging config thật |

Một test chỉ gọi MDC.get có thể PASS dù pattern thiếu %X{requestId}. Một test ILoggingEvent có MDC đúng có thể PASS dù JSON encoder bỏ field hoặc collector làm mất nó. Ngược lại, chỉ tìm chuỗi requestId trong output có thể false-positive nếu ID xuất hiện trong message text thay vì MDC structured field.

Thiết kế test dựa vào contract: nếu yêu cầu mỗi event ERROR có traceId, assertion nên kiểm tra field của **event đã phát** và serialized output, không chỉ biến MDC của method.

## 4. Vòng đời scope và nested restore

Một helper SLF4J điển hình:

~~~java
import org.slf4j.MDC;

void withRequestId(String id, Runnable work) {
    String previous = MDC.get("requestId");
    try {
        MDC.put("requestId", id);
        work.run();
    } finally {
        if (previous == null) {
            MDC.remove("requestId");
        } else {
            MDC.put("requestId", previous);
        }
    }
}
~~~

Đoạn này là **mã tích hợp**, cần SLF4J dependency và class của ứng dụng. Nó chỉ sở hữu requestId nên không xóa traceId/jobId do thành phần khác đặt. Tests nên bao phủ:

1. Trước scope không có ID; trong scope thấy req-A; sau scope key biến mất.
2. Trước scope có outer; scope con thấy inner; sau scope con khôi phục outer.
3. Handler ném RuntimeException; finally vẫn khôi phục previous.
4. Caller có traceId; scope không làm mất traceId.
5. Gọi helper nhiều lần nối tiếp không giữ lại ID của lần trước.
6. Nếu key trước đó không tồn tại, dùng remove thay vì ghi chuỗi literal "null".

**MDC.putCloseable** tiện khi một scope chỉ cần remove key khi đóng. Nhưng với nested scope ghi đè cùng key, không nên giả định close tự khôi phục giá trị cũ; lưu previous rồi restore như trên là cách dễ kiểm tra.

**MDC.clear()** có thể phù hợp tại boundary sở hữu toàn bộ map, nhưng không phù hợp trong một thư viện chỉ có quyền đối với một key, vì nó có thể xóa traceId/baggage do caller quản lý.

## 5. Ví dụ Java 17 độc lập: nguyên lý context scope

Ví dụ đầu tiên chỉ dùng JDK 17, mô phỏng context bằng ThreadLocal. **Nó không phải SLF4J MDC**, và không thay thế test provider thật; nó giúp nhìn rõ nested restore và finally.

Tạo file **MdcScopeConceptDemo.java**:

~~~java
public class MdcScopeConceptDemo {
    private static final ThreadLocal<String> REQUEST = new ThreadLocal<>();

    private static void withId(String id, Runnable work) {
        String previous = REQUEST.get();
        try {
            REQUEST.set(id);
            work.run();
        } finally {
            if (previous == null) {
                REQUEST.remove();
            } else {
                REQUEST.set(previous);
            }
        }
    }

    private static String current() {
        String value = REQUEST.get();
        return value == null ? "<absent>" : value;
    }

    public static void main(String[] args) {
        System.out.println("before=" + current());
        withId("req-outer", () -> {
            System.out.println("outer=" + current());
            withId("req-inner", () ->
                    System.out.println("inner=" + current()));
            System.out.println("restored=" + current());
        });
        System.out.println("after=" + current());
    }
}
~~~

Chạy:

~~~bash
javac MdcScopeConceptDemo.java
java MdcScopeConceptDemo
~~~

Stdout xác định:

~~~text
before=<absent>
outer=req-outer
inner=req-inner
restored=req-outer
after=<absent>
~~~

Đầu ra cho thấy nested scope có thể thay context tạm thời mà không xóa giá trị trước đó. Trong production, phải dùng đúng MDC adapter và propagation framework; ví dụ thuần JDK chỉ giải thích nguyên tắc.

## 6. Chuẩn bị Maven, JUnit 5, SLF4J và Logback

Bộ kiểm thử tiếp theo chạy bằng **Java 17 + JUnit 5 + SLF4J 2.0 + Logback 1.5**. Các version dưới đây là **ví dụ minh họa tương thích**, không nhất thiết là phiên bản mới nhất. Dự án dùng Spring Boot hoặc BOM khác nên chọn dependencies tương ứng với runtime để tránh provider conflict.

Cấu trúc:

~~~text
mdc-test-demo/
  pom.xml
  src/test/java/example/MdcContextTest.java
~~~

File **pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>mdc-test-demo</artifactId>
  <version>1.0-SNAPSHOT</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.slf4j</groupId>
      <artifactId>slf4j-api</artifactId>
      <version>2.0.13</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>ch.qos.logback</groupId>
      <artifactId>logback-classic</artifactId>
      <version>1.5.6</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.10.2</version>
      <scope>test</scope>
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
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
~~~

Test chỉ dùng logging API ở test scope nên Logback có thể là test dependency. Ứng dụng production có thể cung cấp provider ở runtime theo quy định riêng.

**Lưu ý:** Logback-specific test sử dụng class **ch.qos.logback.classic.Logger** và ILoggingEvent. Nếu thay backend sang Log4j 2, cần chuyển cơ chế capture hoặc test output trung lập với provider; không cast ép một implementation không có trên classpath.

## 7. Bẫy khi test ListAppender: lazy MDC snapshot

Một đoạn test phổ biến tạo Logback ListAppender rồi giữ reference của ILoggingEvent, nhưng chỉ gọi **getMDCPropertyMap()** sau khi ứng dụng đã thay hoặc xóa MDC.

Vấn đề: một số thông tin của event có thể được **chuẩn bị hoặc lấy trễ** bởi implementation. Nếu lấy MDC quá muộn, test có thể phụ thuộc vào timing hoặc đọc không đúng thời điểm mà câu logger được gọi.

Giải pháp khi viết test appender:

1. Ở ngay phương thức append, gọi **event.prepareForDeferredProcessing()**.
2. Đọc **event.getMDCPropertyMap()** khi event đang được xử lý.
3. Tạo **bản sao không thay đổi** của các key/value cần kiểm tra.
4. Chụp formatted message, level và các trường liên quan.
5. Sau đó mới cho code ứng dụng đổi/clear MDC.

Không sửa trực tiếp event hoặc map của adapter. Với async logging, yêu cầu giữ đúng context của **producer thread tại thời điểm tạo event**, không dùng MDC của background appender worker.

## 8. JUnit 5: bộ test hoàn chỉnh trên Logback

Tạo file **src/test/java/example/MdcContextTest.java**:

~~~java
package example;

import ch.qos.logback.classic.Level;
import ch.qos.logback.classic.Logger;
import ch.qos.logback.classic.spi.ILoggingEvent;
import ch.qos.logback.core.AppenderBase;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.slf4j.LoggerFactory;
import org.slf4j.MDC;

import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.*;

class MdcContextTest {
    record Snapshot(String message, Level level,
                    Map<String, String> mdc) {}

    static final class CaptureAppender extends AppenderBase<ILoggingEvent> {
        final List<Snapshot> events = new CopyOnWriteArrayList<>();

        @Override
        protected void append(ILoggingEvent event) {
            event.prepareForDeferredProcessing();
            Map<String, String> values = event.getMDCPropertyMap();
            Map<String, String> copy =
                    values == null ? Map.of() : Map.copyOf(values);
            events.add(new Snapshot(
                    event.getFormattedMessage(),
                    event.getLevel(), copy));
        }
    }

    private Logger logger;
    private CaptureAppender appender;

    @BeforeEach
    void setUp() {
        MDC.clear();
        logger = (Logger) LoggerFactory.getLogger(
                "example.mdc." + UUID.randomUUID());
        logger.setLevel(Level.INFO);
        logger.setAdditive(false);

        appender = new CaptureAppender();
        appender.setContext(logger.getLoggerContext());
        appender.start();
        logger.addAppender(appender);
    }

    @AfterEach
    void tearDown() {
        logger.detachAppender(appender);
        appender.stop();
        logger.setLevel(null);
        logger.setAdditive(true);
        MDC.clear();
    }

    private static void withRequestId(String id, Runnable work) {
        String previous = MDC.get("requestId");
        try {
            MDC.put("requestId", id);
            work.run();
        } finally {
            if (previous == null) {
                MDC.remove("requestId");
            } else {
                MDC.put("requestId", previous);
            }
        }
    }

    private static Runnable withCapturedMdc(Runnable work) {
        Map<String, String> captured = MDC.getCopyOfContextMap();
        Map<String, String> snapshot =
                captured == null ? null : Map.copyOf(captured);

        return () -> {
            Map<String, String> previous =
                    MDC.getCopyOfContextMap();
            try {
                if (snapshot == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(snapshot);
                }
                work.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }

    @Test
    void eventCapturesMdcAtLoggingTime() {
        MDC.put("requestId", "req-42");
        logger.info("first");

        MDC.put("requestId", "req-99");
        logger.warn("second");

        MDC.remove("requestId");
        logger.info("third");

        assertEquals(3, appender.events.size());
        assertEquals("req-42",
                appender.events.get(0).mdc().get("requestId"));
        assertEquals("req-99",
                appender.events.get(1).mdc().get("requestId"));
        assertFalse(appender.events.get(2).mdc()
                .containsKey("requestId"));
        assertEquals(Level.WARN, appender.events.get(1).level());
        assertEquals("third", appender.events.get(2).message());
    }

    @Test
    void nestedScopeRestoresContextEvenOnFailure() {
        MDC.put("requestId", "outer");
        MDC.put("traceId", "trace-7");

        withRequestId("inner", () -> {
            assertEquals("inner", MDC.get("requestId"));
            logger.info("nested");
        });

        assertEquals("outer", MDC.get("requestId"));
        assertEquals("trace-7", MDC.get("traceId"));
        assertEquals("inner",
                appender.events.get(0).mdc().get("requestId"));

        MDC.remove("requestId");
        assertThrows(IllegalStateException.class, () ->
                withRequestId("temporary", () -> {
                    throw new IllegalStateException("expected");
                }));

        assertNull(MDC.get("requestId"));
        assertEquals("trace-7", MDC.get("traceId"));
    }

    @Test
    void executorTaskDoesNotLeakMdc() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(MDC::clear).get();
            MDC.put("requestId", "req-worker");

            assertNull(pool.submit(
                    () -> MDC.get("requestId")).get());

            pool.submit(withCapturedMdc(
                    () -> logger.info("worker-event"))).get();

            assertEquals("req-worker",
                    appender.events.get(0).mdc().get("requestId"));
            assertNull(pool.submit(
                    () -> MDC.get("requestId")).get());
            assertEquals("req-worker", MDC.get("requestId"));
        } finally {
            pool.shutdownNow();
        }
    }

    @Test
    void exceptionRestoresWorkersPreviousContext() throws Exception {
        ExecutorService pool = Executors.newSingleThreadExecutor();
        try {
            pool.submit(() -> MDC.put("requestId", "worker-old"))
                    .get();
            MDC.put("requestId", "caller-new");

            assertThrows(ExecutionException.class, () ->
                    pool.submit(withCapturedMdc(() -> {
                        assertEquals("caller-new",
                                MDC.get("requestId"));
                        throw new IllegalArgumentException("failure");
                    })).get());

            assertEquals("worker-old", pool.submit(
                    () -> MDC.get("requestId")).get());
            assertEquals("caller-new", MDC.get("requestId"));
        } finally {
            pool.submit(MDC::clear).get();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy từ thư mục chứa pom.xml:

~~~bash
mvn test
~~~

**Kết quả kỳ vọng:** Maven kết thúc với exit code 0, **4 test methods** hoàn tất không có assertion failure. Chi tiết dòng summary/stdout do Maven/Surefire in ra có thể khác theo môi trường; không giả định một chuỗi console cố định cho lệnh này.

### Ý nghĩa từng test

- **eventCapturesMdcAtLoggingTime:** ba log event có requestId lần lượt req-42, req-99 và absent. Assert dựa trên **event snapshot**, không dựa vào MDC hiện tại sau khi các dòng đã được phát.
- **nestedScopeRestoresContextEvenOnFailure:** scope con khôi phục outer, giữ traceId trace-7 và dọn requestId sau exception.
- **executorTaskDoesNotLeakMdc:** worker ban đầu không tự kế thừa requestId của caller; wrapper truyền đúng khi task chạy; sau task worker không giữ requestId.
- **exceptionRestoresWorkersPreviousContext:** worker có giá trị worker-old; task nhận caller-new và ném lỗi; finally khôi phục worker-old, caller vẫn giữ caller-new.

Test appender dùng **prepareForDeferredProcessing** và **Map.copyOf** để freeze dữ liệu; CopyOnWriteArrayList giúp thu events an toàn khi có nhiều thread. Logger được tạo với tên riêng, **setAdditive(false)** để không chuyển event đến root appenders; fixture tự detach/stop sau test.

**Giới hạn:** đây là kiểm thử Logback với JUnit, không thử Kafka/HTTP, không chứng minh JSON encoder cuối cùng xuất MDC, và không bảo đảm mọi logging backend có đúng semantics Logback.

## 9. Isolation của test và shared logging state

Có hai vùng trạng thái riêng:

**MDC context** thường thuộc thread; cần cleanup trong try/finally hoặc sau mỗi task. **Logger configuration/appender** thuộc logger context và có thể được chia sẻ giữa nhiều tests.

Cách giảm flakiness:

- Dùng logger riêng cho test và một appender được start/stop đúng vòng đời.
- Tránh thay root logger level và xóa các appender toàn cục, vì test khác có thể bị ảnh hưởng.
- Dọn MDC trên test thread trước/sau từng case.
- Đối với worker thread, cleanup **trong task**, không giả định MDC.clear() của test thread làm sạch worker.
- Dùng test-owned ExecutorService và shutdown trong finally.
- Khi chạy parallel tests, không dùng một static ListAppender chung nếu không có lọc/đồng bộ.
- Nếu cần kiểm thử MDC của event async, chụp dữ liệu đúng lúc và chờ consumer hoàn tất bằng cơ chế xác định.

Nếu một test chỉ pass khi chạy riêng nhưng fail khi cả suite chạy, hãy kiểm tra shared logger/ThreadLocal/provider setup trước khi tăng timeout hoặc thêm Thread.sleep.

## 10. Propagation qua ExecutorService

Đối với task bất đồng bộ, cần **capture tại caller** rồi **activate tại worker**:

~~~text
Caller: MDC(requestId=req-A)
    |
    | getCopyOfContextMap()
    v
Runnable + captured snapshot
    |
    v
Worker:
    previous = worker MDC snapshot
    setContextMap(captured)
    run task
    finally restore previous or clear
    |
    v
Worker nhận task tiếp theo
~~~

Test cần xác minh:

1. Snapshot được lấy lúc submit, trước khi caller đổi context.
2. Worker nhìn ID từ snapshot, không phải ID tình cờ sót lại.
3. Task xong bình thường thì worker trở về state trước đó.
4. Task ném exception thì finally vẫn restore.
5. Caller vẫn giữ MDC gốc, worker không sửa trực tiếp map của caller.
6. Task B dùng cùng worker nhưng ID khác không bị lẫn.
7. Khi context caller không có một key, wrapper không tạo giá trị cũ giả.

**Đừng dùng InheritableThreadLocal như propagation strategy mặc định cho thread pool.** Worker thread có thể được tạo từ trước hoặc reuse nhiều task.

Framework như Spring TaskDecorator, Micrometer Context Propagation hoặc OpenTelemetry cung cấp cơ chế tích hợp; nên dùng đúng framework và kiểm thử ngữ nghĩa của nó thay vì triển khai nhiều wrapper chồng nhau.

## 11. CompletableFuture và reactive callbacks

Các thao tác supplyAsync, thenApplyAsync và callback của CompletableFuture có thể chạy trên thread khác. Vì vậy:

- Chỉ định **test-owned executor** khi cần kiểm soát điều kiện.
- Capture context ở boundary submit hoặc gắn decorator do framework cung cấp.
- Test một callback sau khi caller đổi MDC: callback vẫn dùng context của nhiệm vụ được giao.
- Kiểm tra các nhánh exceptionally/handle/whenComplete, không chỉ thenApply thành công.
- Kiểm thử propagation qua retry/cancellation với đồng bộ rõ ràng.
- Không assert thứ tự log toàn cục của các future độc lập nếu không có happens-before.

Ở reactive frameworks như Reactor, **Reactor Context** không đồng nhất với ThreadLocal. MDC bridge phải được thiết kế theo instrumentation/operator context có sẵn; một test servlet kiểu ThreadLocal không đủ chứng minh reactive pipeline không leak.

## 12. Thread pool reuse và kiểm tra context leak

Một regression scenario rất có giá trị:

~~~text
worker-1: request A -> log A -> cleanup
worker-1: request B -> log B -> cleanup
worker-1: task C (no requestId) -> log C
~~~

Assert:

- Event A có req-A, event B có req-B.
- Event C **không có requestId**, nếu contract không yêu cầu.
- Sau mỗi task, worker không còn giá trị cũ.
- Caller ngoài executor không bị thay đổi context.
- Nếu task A ném exception, task B vẫn sạch.

Dùng **single-thread executor** giúp chắc chắn A/B cùng worker. Dùng Future.get() để xác định đã hoàn tất rồi mới kiểm tra; **Thread.sleep không phải phép đồng bộ đáng tin**. Nếu test concurrency với nhiều thread, nên dùng CountDownLatch/CyclicBarrier và deadline để ép overlap mà không phụ thuộc scheduler timing.

Đừng "chữa" test leak bằng cách thêm MDC.clear() thủ công trước task B khi code production không có bước tương ứng. Test phải chứng minh chính lớp quản lý scope của ứng dụng thực hiện cleanup.

## 13. Kiểm thử concurrency

Với hai tasks A/B chạy đồng thời:

~~~text
Thread-1: event=A1 requestId=req-A
Thread-2: event=B1 requestId=req-B
Thread-1: event=A2 requestId=req-A
Thread-2: event=B2 requestId=req-B
~~~

Không assert một thứ tự dòng log toàn cục nếu không có thứ tự được bảo đảm. Thay vào đó:

- Gắn ID riêng cho mỗi tác vụ và correlation key ổn định.
- Capture snapshot với appender thread-safe.
- Lọc/group events theo ID và kiểm tra mọi event của A mang req-A.
- Kiểm tra không event nào vừa mang key/ID của A và B sai scope.
- Dùng latch/barrier để các tasks thật sự overlap; không dùng sleep ngẫu nhiên.
- Đặt deadline và cleanup executor khi test kết thúc.

Một lỗi khó phát hiện là hai futures đều dùng chung một **mutable Map** làm snapshot. Nếu caller tiếp tục sửa map sau submit, task có thể nhận state mới. Dùng snapshot bản sao trước submit, và test trường hợp caller thay ID ngay sau khi enqueue.

## 14. Exception, timeout, cancellation và retry

MDC cleanup cần được đảm bảo ở mọi đường thoát:

| Tình huống | Assertion nên có |
| --- | --- |
| Return bình thường | Context được khôi phục |
| RuntimeException | Finally chạy, previous value giữ nguyên |
| Checked exception được wrap | Restore vẫn xảy ra |
| Future.get timeout | Chỉ caller timeout; task có thể còn chạy |
| Cancellation trước khi chạy | Snapshot không bị giữ ngoài lifecycle cần thiết |
| Cancellation trong khi chạy | Nếu task thực sự kết thúc, finally cleanup |
| Retry ở executor khác | Mỗi attempt có ID đúng và không lẫn task |
| DLQ/replay | messageId được bảo toàn theo contract |

**Future.cancel(true) không bảo đảm task dừng tức thì** nếu công việc không hợp tác với interruption. Khi test timeout, đừng kiểm tra worker MDC rỗng ngay khi caller nhận TimeoutException; cần chờ task kết thúc và finally chạy.

Khi retry, **messageId** có thể giữ nguyên còn attemptNo thay đổi. Không sử dụng static field toàn process để lưu ID của một message.

## 15. Kiểm thử tại HTTP filter/interceptor

Trong servlet-based Spring MVC hoặc Java web application:

1. Request A gắn validated requestId, controller/service log mang ID A.
2. Request B dùng thread reuse không mang ID A.
3. Header không hợp lệ chứa newline hoặc quá dài được từ chối/cấp ID mới theo policy.
4. Controller ném exception; filter finally vẫn restore.
5. Servlet async hoặc callback chuyển thread có propagation tương thích.
6. Tracing SDK tạo traceId thật và MDC log field khớp trace context.
7. Response correlation header và log ID có thể được đối chiếu nếu contract yêu cầu.

Có thể dùng MockMvc hoặc HTTP integration test, nhưng **assert response header không thay thế assert log event MDC**. Trường hợp framework cung cấp auto-propagation, cần test đúng cấu hình runtime.

Với WebFlux/Reactor, không áp giả định MDC theo thread trên mọi operator; phải test Reactor Context và context-propagation bridge thực tế.

## 16. Kiểm thử trong message consumer

Trong message-driven services, messageId/trace context thường đến từ headers/envelope:

~~~text
Broker receive
   |
   v
Validate envelope and IDs
   |
   v
Activate MDC scope
   |
   v
Handler -> log events -> business commit
   |
   v
ACK / retry / DLQ
   |
   v
Restore MDC
~~~

Test theo contract:

- Message A có ID đúng trong event của handler.
- Message B chạy sau trên cùng worker không nhận ID của A.
- Handler lỗi và retry vẫn dọn context.
- Nếu redelivery, logical messageId giữ nguyên, attemptNo khác theo policy.
- Message con mang correlation/causation context được cho phép.
- Deserialize error xảy ra trước khi có payload vẫn log broker metadata an toàn, không dump raw secret.
- Không đánh đồng ACK/offset commit với kiểm tra MDC đúng; cần inspect event hoặc output thật.

Trường hợp message batch/fan-out cần test ID theo từng message, không dùng một MDC map của cả batch nếu mỗi record cần correlation riêng.

## 17. Kiểm thử encoder JSON/text

Ví dụ pattern text Logback:

~~~text
%d{ISO8601} %-5level request=%X{requestId} trace=%X{traceId} %logger - %msg%n
~~~

Nếu pattern chỉ có %msg, MDC vẫn có thể nằm trong event mà không xuất hiện trong output. Vì vậy pipeline test nên:

1. Nạp **logback-test.xml** hoặc cấu hình encoder production tương ứng.
2. Tạo event với MDC thực.
3. Flush/stop appender hoặc chờ hoàn tất với cơ chế được hỗ trợ.
4. Đọc text/JSON output từ test sink.
5. Parse trường cụ thể và assert requestId, traceId, eventCode đúng kiểu/giá trị.
6. Test field absent khi ngoài scope.
7. Kiểm tra không xuất password, token, raw Authorization, PII không được phép.

Ví dụ JSON kỳ vọng:

~~~json
{
  "level": "ERROR",
  "event": "order_failed",
  "requestId": "req-42",
  "traceId": "trace-7",
  "errorCode": "INVENTORY_TIMEOUT"
}
~~~

Đây là **schema minh họa**, không phải output mặc định của Logback. JSON serializer phải xử lý escaping; **encoding đúng không tự đồng nghĩa redaction**.

Không chỉ grep một substring lớn: ID có thể xuất hiện trong message text nhưng thiếu field MDC có cấu trúc. Parse JSON và assert theo schema thực của collector.

## 18. AsyncAppender, snapshot và backpressure

Với async logging, event được tạo trên request thread nhưng được format/ghi bởi worker sau đó:

~~~text
caller: MDC=req-A -> logger.info -> MDC.clear
                         |
                         v
                    async queue
                         |
                         v
                   log writer
~~~

Event đúng phải mang req-A **tại thời điểm logger phát**, không đọc context rỗng của writer. Kiểm tra:

- Ghi event với req-A, đổi sang req-B hoặc clear ngay, rồi kiểm tra event output vẫn là req-A.
- Bảo đảm async appender chụp hoặc chuẩn bị field cần thiết trước khi queue.
- Chờ queue drain/flush đúng cơ chế, không dựa vào Thread.sleep cố định.
- Đo chính sách **backpressure** khi queue đầy: block, drop hoặc discard tùy cấu hình.
- Kiểm tra shutdown flush và log drop metric ở tải cao.
- Không giả định async sẽ giữ mọi ERROR nếu provider cấu hình discard hoặc process bị kill.

**ListAppender giữ raw ILoggingEvent reference có thể tạo test sai** nếu không prepare rồi snapshot MDC trong append. Bộ test JUnit ở mục 8 đã chụp dữ liệu ngay để giảm rủi ro đó.

## 19. Những lỗi kiểm thử thường gặp

| Anti-pattern | Vì sao không đủ | Cách thay thế |
| --- | --- | --- |
| Chỉ assert MDC.get sau put | Không biết logger đã ghi field chưa | Kiểm tra event MDC snapshot |
| Đọc event.getMDCPropertyMap quá muộn | Có thể gặp lazy preparation/timing | prepareForDeferredProcessing ngay khi append |
| Chỉ clear MDC của test thread | Worker có context riêng | Cleanup trong task và test reuse worker |
| Dùng root logger/appenders chung | Shared state làm test nhiễu | Logger riêng, teardown |
| Test concurrency bằng sleep | Dễ flaky | Latch, barrier, Future.get |
| Assert total ordering của log song song | Scheduler không bảo đảm | Group events theo correlation ID |
| Dùng InheritableThreadLocal với thread pool | Không gắn context theo mỗi task | Capture/activate/restore |
| Tin rằng putCloseable tự restore nested old | Có thể chỉ remove key | Lưu previous, restore trong finally |
| Test traceId bằng string giả | Không chứng minh distributed tracing | Kiểm tra inject/extract, SDK context |
| Bật INFO/ERROR nhưng test DEBUG event | Event có thể bị filter | Cấu hình level rõ |
| Chỉ kiểm tra console text | Encoder có thể bỏ field, sampling/drop | Event test + output integration |
| Đặt token/payload vào MDC để test | Có thể rò dữ liệu trong CI log | Dùng dữ liệu giả, allowlist |

## 20. Checklist cho CI và production

| Hạng mục | Tiêu chí |
| --- | --- |
| MDC state | put/get/remove và nested restore đúng |
| Cleanup | try/finally bảo đảm cả success, exception, cancellation |
| Context ownership | Không xóa key do caller/framework sở hữu |
| Event capture | Test chụp MDC tại thời điểm log |
| Provider | Backend và version test tương thích runtime |
| Thread pool | Không có context leak giữa task A/B |
| Propagation | Executor/CompletableFuture dùng scope/decorator phù hợp |
| Concurrency | Test overlap ổn định, không assert ordering vô căn cứ |
| HTTP/message boundaries | Tạo và khôi phục ID theo request/delivery |
| Trace correlation | traceId thực, có propagation qua headers/SDK khi cần |
| Encoder | JSON/text xuất field đúng và field absent ngoài scope |
| Async | Snapshot, flush và queue overflow policy đã được test |
| Test fixture | Appender detach/stop; executor shutdown; state cleanup |
| Privacy | ID validated; không lộ secret, PII hoặc log forging |
| Observability | Có cách phân biệt thiếu MDC, thiếu event, collector drop |

## 21. Cách điều tra khi test thất bại

Nếu event thiếu requestId:

1. Kiểm tra MDC.put có xảy ra **trước logger call** không.
2. Kiểm tra logger level/filter có thực sự phát event không.
3. Kiểm tra appender test đã start và được attach đúng logger chưa.
4. Kiểm tra snapshot MDC có được chụp trước khi caller clear không.
5. Nếu callback/worker khác thread, kiểm tra capture và activate context.
6. Kiểm tra provider SLF4J/Logback được bind đúng dependency.
7. Nếu event snapshot đúng nhưng JSON thiếu ID, kiểm tra encoder schema.
8. Nếu production thiếu log, kiểm tra async drop, collector parse, sampling và retention.

Nếu request B mang ID của A, kiểm tra cleanup của worker và chạy single-thread executor để tái hiện chắc chắn. Đừng "sửa" bằng cách chỉ dọn MDC trong test mà production không có.

**Kết luận:** kiểm thử ngữ cảnh MDC đáng tin phải chứng minh **đúng dữ liệu trong log event, scope/exception cleanup, isolation giữa các worker threads, propagation tại ranh giới async, và output của encoder/collector**. Dùng JUnit 5 cùng Logback appender chụp snapshot để có assertion xác định; dùng integration tests để xác minh toàn bộ pipeline theo môi trường thật.