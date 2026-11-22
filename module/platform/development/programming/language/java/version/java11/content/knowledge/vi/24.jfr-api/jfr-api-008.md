# Java 11 — begin, end, commit và thời lượng nghiệp vụ trong JFR API

**Chủ đề:** Java 11 → **JFR API (Java Flight Recorder)**. Bài học giải thích cách dùng `jdk.jfr.Event.begin()`, `end()` và `commit()` để ghi lại **thời lượng xử lý nghiệp vụ**, cùng cách sử dụng `isEnabled()`, `shouldCommit()`, `@Threshold` và `RecordingFile`. Mọi API trong ví dụ thuộc **Java 11** và còn áp dụng hiện nay; không dùng API JFR nội bộ hoặc phương thức chỉ xuất hiện trên JDK mới hơn.

**Mục tiêu:** Sau bài, bạn tự định nghĩa event, đo đúng phạm vi một business operation, bảo toàn cả trường hợp thành công và thất bại bằng `try/finally`, phân biệt ngưỡng thu thập JFR với timeout, xuất/đọc file `.jfr`, viết test xác định outcome và kiểm tra duration mà không lệ thuộc chính xác từng mili-giây. Hai chương trình Java đầy đủ dưới đây đã được biên dịch với `javac --release 11` và chạy thật trên JDK 24; việc chạy trên runtime JDK 11 cần được bổ sung trong CI nếu production sử dụng đúng Java 11.

## 1. Vì sao cần đo thời lượng nghiệp vụ?

Một request tạo đơn hàng có thể gồm xác thực, xếp hàng, kiểm tra inventory, ghi database, gọi thanh toán và serialize response. Không phải tất cả đều thuộc cùng một business stage:

~~~text
HTTP request arrival
   authenticate      [-----]
   wait queue                 [----------]
   business operation                    [---- begin ---------------- end ----]
   inventory                             [----]
   database                                    [----------]
   payment                                               [---------]
   response serialization                                                        [---]
HTTP response complete

JFR OrderProcessing event:                    timestamp -------- duration -------- timestamp
                                                                                     |
                                                                                   commit
~~~

Nếu event `OrderProcessing` chỉ bắt đầu ở service method và kết thúc khi kết quả business đã sẵn sàng, `RecordedEvent.getDuration()` đo **đúng đoạn begin→end đó**. Nó không tự bao gồm HTTP decode, queue wait hay serialization ngoài phạm vi.

**Các loại thời gian cần phân biệt:**

| Loại | Phạm vi | Cách sử dụng |
| --- | --- | --- |
| **Business duration** | Đoạn code do lập trình viên đánh dấu bằng begin/end. | Custom JFR Event. |
| **End-to-end request latency** | Từ lúc nhận request đến mốc trả response theo API contract. | HTTP instrumentation/metrics/tracing. |
| **CPU time** | Thời gian CPU thực sự được thread/process dùng. | Thread CPU time/JFR CPU-related events. |
| **Queue wait** | Từ lúc enqueue đến lúc worker bắt đầu. | Queue metric hoặc event riêng. |
| **Distributed trace duration** | Qua nhiều process/service và context. | Distributed tracing; JFR không tự truyền span context. |

JFR events giúp xem business operation cùng timeline với GC, CPU samples, allocation, thread states và I/O. Nhưng chúng không thay thế metrics dùng tính SLO/SLA khi recording có thể tắt, lọc ngưỡng hoặc không đầy đủ.

## 2. Vòng đời `Event`: begin, end, commit

Mỗi event instance thường đại diện cho **một lần chạy** một nghiệp vụ:

~~~java
OrderEvent event = new OrderEvent();
event.operation = "create-order";
event.begin();
try {
    createOrder();
    event.result = "OK";
} catch (RuntimeException ex) {
    event.result = "FAILED";
    throw ex;
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.commit();
    }
}
~~~

**Đây là đoạn minh họa**, `OrderEvent` và `createOrder` do ứng dụng khai báo; chương trình chạy độc lập nằm ở mục 6.

| API Java 11 | Tác dụng |
| --- | --- |
| `begin()` | Bắt đầu thời gian của event. |
| `end()` | Kết thúc thời gian event; chỉ gọi sau begin. |
| `commit()` | Ghi field values, timestamp và duration vào hệ thống Flight Recorder theo recording settings. |
| `isEnabled()` | True khi ít nhất một recording đang chạy và loại event được bật. |
| `shouldCommit()` | True khi event được bật và duration đủ ngưỡng đã cấu hình. |

`begin()` và `end()` **không trực tiếp xuất file JFR**. `commit()` gửi event đến hệ thống ghi. `Recording.dump(path)` mới là hoạt động xuất cả recording thành file `.jfr`; không được dump cho từng request như một phép logging thông thường.

### 2.1. Có thể bỏ end không?

Javadoc Java 11 cho phép:

~~~java
event.begin();
doBusinessWork();
event.commit();
~~~

Nếu đã `begin()` mà chưa `end()`, `commit()` **tự kết thúc thời gian event**. Tuy vậy, đoạn này **không có finally**: nếu nghiệp vụ ném exception, event chưa chắc được ghi. Ngoài ra, nếu bạn làm thêm việc tạo metadata trước commit, khoảng đó cũng nằm trong duration.

Mẫu tốt hơn:

~~~java
event.begin();
try {
    doBusinessWork();
} finally {
    event.end();
}
event.details = collectSmallMetadata();
event.commit();
~~~

Các đoạn này là **minh họa không độc lập**. Trong production, bảo đảm exception khi thu thập metadata không che lỗi nghiệp vụ; nếu metadata có chi phí lớn, gọi `shouldCommit()` ngay sau `end()` và chỉ enrich nếu event đủ điều kiện.

### 2.2. Instant event khác duration event

Nếu chỉ muốn ghi “đã invalidated cache”, không có khoảng thời gian ý nghĩa, có thể:

~~~java
CacheInvalidatedEvent event = new CacheInvalidatedEvent();
event.cacheGroup = "products";
event.commit();
~~~

Đây là **instant event**, không phải phép đo thời lượng một transaction. Không gọi begin/end giả chỉ để tạo duration gần 0. `Event` có thể dùng cho instant hoặc duration tùy cách sử dụng.

## 3. Thời lượng thực sự đo được

~~~text
t0: event.begin()
      thực hiện business code
      chờ lock / database / Thread.sleep
      compute CPU
t1: event.end()
      format metadata cho JFR
t2: event.commit()

duration = t1 - t0
không phải t2 - t0
~~~

Duration là **elapsed time**, bao gồm cả thời gian đang chờ I/O, thread scheduling hoặc GC pause nếu xảy ra trong đoạn đo. Nó **không phải CPU time**. Với `Thread.sleep(35)`, thời lượng quan sát được có thể là 35ms hoặc cao hơn; đừng assert `getDuration().toMillis() == 35` trong automated test.

**Phạm vi business phải được định nghĩa rõ ràng:**

- `OrderCore`: bắt đầu trước validate/inventory; kết thúc khi business result hình thành.
- `OrderTransaction`: nếu chỉ coi thành công sau DB commit, phải end **sau commit**.
- `OrderEnqueueWait`: đo từ enqueue tới dequeue, khác thời gian execution.
- `DbRead`: begin trước query, end khi kết quả truy xuất xong theo contract.
- `HttpRequestTotal`: có thể rộng hơn `OrderCore`, gồm queue, routing và response flush theo điểm end.

Không dùng cùng tên event nhưng các service đặt begin/end khác nhau rồi so sánh như thể có cùng semantics.

## 4. Định nghĩa custom event bằng Java 11

`jdk.jfr.Event` cho phép khai báo các fields cùng annotations. Ví dụ:

~~~java
@Name("demo.OrderProcessing")
@Label("Order processing")
@Description("Duration of a single business operation")
@Category({"Application", "Orders"})
@Threshold("10 ms")
@StackTrace(false)
public static class OrderEvent extends Event {
    @Label("Operation")
    public String operation;

    @Label("Result")
    public String result;

    @Label("Item count")
    public int itemCount;

    @Label("Error code")
    public String errorCode;
}
~~~

Đây là một class lồng hợp lệ bên trong class chứa các imports cần thiết. `@Name` dùng để nhận diện event type trong recording; `@Label`/`@Description` phục vụ hiển thị; `@Category` phân nhóm; `@Threshold` đặt ngưỡng mặc định; `@StackTrace(false)` tránh stack trace không cần thiết trong hot path.

**Field types JFR Java 11 hỗ trợ:** primitive `boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double`, cùng `String`, `Thread`, `Class`. Không mặc định `List`, `Map`, enum, array hay object business sẽ được serialize; fields không hỗ trợ có thể bị bỏ qua.

Metadata tốt nên là **operation code cố định, result, error code và số lượng**. Không ghi raw SQL, request body, token, email, password hoặc message exception có PII vào `String` event field.

### 4.1. Dữ liệu thời lượng gắn trực tiếp với event

`RecordedEvent.getDuration()` đã có sẵn khi ghi bằng begin/end. Không cần tự thêm field `long durationMs` để ghi lại y hệt duration. `@Timespan(Timespan.MILLISECONDS)` hữu ích nếu bạn thực sự có **một field long đo thời gian phụ** như `databaseWaitMillis`. Nó chỉ gắn metadata đơn vị cho field, không tạo `Event` duration thay thế begin/end.

## 5. Nhánh lỗi phải được ghi, nhưng exception vẫn truyền lên

Đoạn sau bảo vệ event ở success và failure:

~~~java
OrderEvent event = new OrderEvent();
event.operation = "reserve-stock";
event.begin();
try {
    reserveStock();
    event.result = "OK";
    event.errorCode = "NONE";
} catch (ValidationException ex) {
    event.result = "FAILED";
    event.errorCode = "VALIDATION";
    throw ex;
} catch (RuntimeException ex) {
    event.result = "FAILED";
    event.errorCode = "INTERNAL";
    throw ex;
} finally {
    event.end();
    if (event.shouldCommit()) event.commit();
}
~~~

Đây là **đoạn minh họa**, các hàm và exception class do app định nghĩa.

Một lỗi vận hành hay gặp: code chỉ set `result=OK` lúc tạo event, sau đó throw trước khi thay đổi result, khiến JFR báo thành công giả. Hãy **chỉ set OK khi công việc thành công**, set FAILED/CANCELLED/TIMEOUT theo nguyên nhân thực tế trong các nhánh tương ứng, và không nuốt exception vì mục đích instrumentation.

`finally` không bảo đảm chạy nếu process/JVM chết bất ngờ hoặc việc xử lý treo mãi. Thiếu event trong file **không chứng minh** nghiệp vụ chưa chạy; cần thêm in-flight metrics, timeout và recovery policy.

## 6. Demo Java 11 hoàn chỉnh: hai nghiệp vụ và đọc lại JFR

Chương trình không dùng thư viện ngoài JDK. Nó ghi:
- Một business operation thành công với `result=OK`, `itemCount=3`.
- Một operation ném `IllegalArgumentException`, vẫn ghi `result=FAILED` và `errorCode=VALIDATION`.
- Hai events có duration dương, không assert số mili-giây chính xác.
- Recording được `stop`/`dump`, đọc qua `RecordingFile.readAllEvents` rồi xóa file tạm.

**Tệp `BusinessJfrDemo.java`:**

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import jdk.jfr.Category;
import jdk.jfr.Description;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;
import jdk.jfr.Threshold;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class BusinessJfrDemo {
    private BusinessJfrDemo() {}

    @Name("demo.OrderProcessing")
    @Label("Order processing")
    @Description("Duration of a single business operation")
    @Category({"Application", "Orders"})
    @Threshold("10 ms")
    @StackTrace(false)
    public static class OrderEvent extends Event {
        @Label("Operation")
        public String operation;

        @Label("Result")
        public String result;

        @Label("Item count")
        public int itemCount;

        @Label("Error code")
        public String errorCode;
    }

    static String process(boolean reject) {
        OrderEvent event = new OrderEvent();
        event.operation = "process-order";
        event.begin();
        try {
            Thread.sleep(35); // Mô phỏng công việc, không dùng trong production.
            if (reject) {
                throw new IllegalArgumentException("Business validation failed");
            }
            event.itemCount = 3;
            event.result = "OK";
            event.errorCode = "NONE";
            return "ok";
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            event.result = "INTERRUPTED";
            event.errorCode = "INTERRUPTED";
            throw new IllegalStateException("Processing interrupted", interrupted);
        } catch (IllegalArgumentException expected) {
            event.result = "FAILED";
            event.errorCode = "VALIDATION";
            throw expected;
        } finally {
            event.end();
            if (event.shouldCommit()) {
                event.commit();
            }
        }
    }

    public static void main(String[] args) throws Exception {
        Path file = Files.createTempFile("business-jfr-demo-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(OrderEvent.class)
                    .withThreshold(Duration.ZERO)
                    .withoutStackTrace();
                recording.start();

                if (!"ok".equals(process(false))) {
                    throw new AssertionError("Success branch failed");
                }
                try {
                    process(true);
                    throw new AssertionError("Error branch should throw");
                } catch (IllegalArgumentException expected) {
                    if (!"Business validation failed".equals(
                            expected.getMessage())) {
                        throw expected;
                    }
                }
                recording.stop();
                recording.dump(file);
            }

            List<RecordedEvent> found = new ArrayList<>();
            for (RecordedEvent event : RecordingFile.readAllEvents(file)) {
                if ("demo.OrderProcessing".equals(event.getEventType().getName())) {
                    found.add(event);
                }
            }
            if (found.size() != 2) {
                throw new AssertionError("Expected two business events: " +
                    found.size());
            }

            int ok = 0, failed = 0, positiveDuration = 0;
            for (RecordedEvent event : found) {
                if (!"process-order".equals(event.getString("operation"))) {
                    throw new AssertionError("Unexpected operation");
                }
                if (event.getDuration().compareTo(Duration.ZERO) > 0) {
                    positiveDuration++;
                }
                String result = event.getString("result");
                if ("OK".equals(result) &&
                        event.getInt("itemCount") == 3 &&
                        "NONE".equals(event.getString("errorCode"))) {
                    ok++;
                } else if ("FAILED".equals(result) &&
                        "VALIDATION".equals(event.getString("errorCode"))) {
                    failed++;
                } else {
                    throw new AssertionError("Unexpected event fields");
                }
            }
            if (ok != 1 || failed != 1 || positiveDuration != 2) {
                throw new AssertionError("JFR content mismatch");
            }
            System.out.println("events=2");
            System.out.println("successful=1");
            System.out.println("failed=1");
            System.out.println("positive.duration.events=2");
            System.out.println("business.scope=process-order");
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 11 -encoding UTF-8 BusinessJfrDemo.java
java BusinessJfrDemo
~~~

**Stdout chính xác đã kiểm chứng:**

~~~text
events=2
successful=1
failed=1
positive.duration.events=2
business.scope=process-order
~~~

**Giải thích kết quả:**

1. Chương trình tạo `OrderEvent` cho mỗi lần `process`, gọi `begin` trước sleep/công việc.
2. Nhánh thành công trả `ok` và ghi `itemCount=3`.
3. Nhánh lỗi ném lại exception, nhưng `finally` vẫn gọi `end/commit`.
4. `recording.enable(OrderEvent.class).withThreshold(Duration.ZERO)` ghi đè ngưỡng mặc định 10ms để ghi mọi event test đủ điều kiện.
5. `RecordingFile.readAllEvents` đọc file đã dump; chỉ filter `demo.OrderProcessing` nên không phụ thuộc các JDK events khác trong recording.
6. `RecordedEvent.getDuration()` được so với `Duration.ZERO` chứ không so exact milliseconds.
7. Recording/file tạm được đóng và xóa sau test.

**QA mã:** Ví dụ đã biên dịch bằng `javac --release 11`, chạy trên JDK 24 với stdout đúng. Không giả định nó đã được thực thi trên JDK11 thực trong lượt thử; CI production nên có job JDK11 riêng.

## 7. `isEnabled()` khác `shouldCommit()`

`isEnabled()` phản ánh **event type đang được bật** bởi ít nhất một recording đang chạy. `shouldCommit()` xét thêm **duration đã đủ threshold chưa**. Vì vậy:

| Điều kiện | `isEnabled()` | `shouldCommit()` sau `end` |
| --- | --- | --- |
| Không recording đang chạy | false | false |
| Event type disabled | false | false |
| Enabled nhưng duration dưới threshold | true | false |
| Enabled và duration đạt threshold | true | true |
| Enabled và threshold 0 | true | true, theo các điều kiện JFR thông thường |

**Đừng gọi `shouldCommit()` trước `end()` để đoán kết quả**, vì duration còn chưa chốt. Dùng nó **sau end** để tránh tính metadata tốn chi phí cho event không được thu. Dùng `isEnabled()` để tránh khởi tạo những fields bổ sung không cần thiết khi recording tắt, nhưng không được làm thay đổi business behavior.

~~~java
OrderEvent event = new OrderEvent();
event.begin();
try {
    performBusinessOperation();
} finally {
    event.end();
    if (event.shouldCommit()) {
        event.operation = safeShortOperationCode();
        event.commit();
    }
}
~~~

Đây là đoạn minh họa, cần định nghĩa các hàm ứng dụng và gán outcome nếu muốn theo dõi thất bại.

### 7.1. Threshold là filter, không phải timeout

- `@Threshold("10 ms")`: default threshold khi không bị recording config ghi đè.
- `recording.enable(OrderEvent.class).withThreshold(Duration.ofMillis(50))`: threshold của recording đó.
- `withThreshold(Duration.ZERO)`: bỏ ngưỡng tối thiểu để test hoặc ghi events ngắn.
- `withoutStackTrace()`: tắt thu thập stack trace cho event trong recording.

**Threshold 50ms không hủy operation sau 50ms** và không giới hạn duration event dài chỉ còn 50ms. Business timeout, cancellation, retry và alerting là logic/policy riêng.

Nếu có **nhiều recordings**, mỗi recording có threshold riêng; không suy từ một annotation rằng mọi recording sẽ lưu cùng tập events.

## 8. Demo thứ hai — đo tác dụng của threshold

Chương trình tạo một `MeasuredEvent` rất ngắn với hai recordings tuần tự:
1. Threshold 1 giờ: `shouldCommit=false`, không có event được ghi.
2. Threshold 0: `shouldCommit=true`, event được ghi.

Threshold 1 giờ là **giá trị thử nghiệm rất lớn** nhằm tránh test flaky vì scheduler, không phải đề xuất vận hành.

**Tệp `JfrThresholdDemo.java`:**

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Label;
import jdk.jfr.Threshold;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;

public final class JfrThresholdDemo {
    @Name("demo.ThresholdExample")
    @Label("Business threshold")
    @Threshold("5 ms")
    public static class MeasuredEvent extends Event {
        public String operation;
    }

    static boolean emit(String value) {
        MeasuredEvent event = new MeasuredEvent();
        event.operation = value;
        event.begin();
        event.end();
        boolean eligible = event.shouldCommit();
        if (eligible) event.commit();
        return eligible;
    }

    static int count(Path file) throws Exception {
        int found = 0;
        for (RecordedEvent e : RecordingFile.readAllEvents(file)) {
            if ("demo.ThresholdExample".equals(e.getEventType().getName())) {
                found++;
            }
        }
        return found;
    }

    public static void main(String[] args) throws Exception {
        Path high = Files.createTempFile("jfr-high-threshold-", ".jfr");
        Path zero = Files.createTempFile("jfr-zero-threshold-", ".jfr");
        try {
            boolean highEligible;
            try (Recording recording = new Recording()) {
                recording.enable(MeasuredEvent.class)
                    .withThreshold(Duration.ofHours(1));
                recording.start();
                highEligible = emit("short");
                recording.stop();
                recording.dump(high);
            }
            boolean zeroEligible;
            try (Recording recording = new Recording()) {
                recording.enable(MeasuredEvent.class)
                    .withThreshold(Duration.ZERO);
                recording.start();
                zeroEligible = emit("short");
                recording.stop();
                recording.dump(zero);
            }
            int highCount = count(high);
            int zeroCount = count(zero);
            if (highEligible || !zeroEligible || highCount != 0
                    || zeroCount != 1) {
                throw new AssertionError("Unexpected threshold filtering");
            }
            System.out.println("threshold.1h.shouldCommit=" + highEligible);
            System.out.println("threshold.1h.events=" + highCount);
            System.out.println("threshold.0.shouldCommit=" + zeroEligible);
            System.out.println("threshold.0.events=" + zeroCount);
        } finally {
            Files.deleteIfExists(high);
            Files.deleteIfExists(zero);
        }
    }
}
~~~

Lệnh:

~~~bash
javac --release 11 -encoding UTF-8 JfrThresholdDemo.java
java JfrThresholdDemo
~~~

**Stdout chính xác đã kiểm chứng:**

~~~text
threshold.1h.shouldCommit=false
threshold.1h.events=0
threshold.0.shouldCommit=true
threshold.0.events=1
~~~

`@Threshold("5 ms")` đặt default, nhưng mỗi recording gọi `withThreshold` để định cấu hình riêng. Chương trình đã biên dịch và chạy trên JDK24 với target source/API 11; không suy rằng mọi release/provider có cùng timing vi mô.

## 9. Đọc `RecordedEvent` và thời lượng nghiệp vụ

`RecordingFile.readAllEvents(Path)` thuận tiện cho file nhỏ. Dùng `RecordedEvent` lấy:

| Phương thức | Giá trị |
| --- | --- |
| `getEventType().getName()` | Event identifier, ví dụ `demo.OrderProcessing`. |
| `getStartTime()` | Timestamp lúc bắt đầu event. |
| `getEndTime()` | Timestamp lúc kết thúc. |
| `getDuration()` | `java.time.Duration` elapsed của event. |
| `getString("result")` | Field outcome. |
| `getInt("itemCount")` | Numeric event field. |
| `getThread()` | Thread metadata (nếu có). |
| `getStackTrace()` | Stack trace nếu được ghi. |

Ví dụ:

~~~java
for (RecordedEvent e : RecordingFile.readAllEvents(file)) {
    if ("demo.OrderProcessing".equals(e.getEventType().getName())) {
        Duration elapsed = e.getDuration();
        String result = e.getString("result");
        System.out.println(result + ": " + elapsed.toMillis() + " ms");
    }
}
~~~

**Đoạn minh họa:** output biến thiên theo tốc độ thực, không ghi giá trị cố định vào expected stdout.

**File lớn:** `readAllEvents` đưa mọi event vào bộ nhớ; nếu file vài GB, dùng streaming reader:

~~~java
try (RecordingFile input = new RecordingFile(path)) {
    while (input.hasMoreEvents()) {
        RecordedEvent event = input.readEvent();
        if ("demo.OrderProcessing".equals(event.getEventType().getName())) {
            consume(event);
        }
    }
}
~~~

`consume` và `path` do ứng dụng định nghĩa. Không đọc file JFR không đáng tin cậy mà thiếu hạn mức/tài nguyên; file ghi có thể chứa stack traces, class names, paths và dữ liệu nội bộ.

## 10. Kết thúc event khi có `CompletableFuture`

Một lỗi phổ biến với async:

~~~java
event.begin();
CompletableFuture<Result> future = service.startAsync();
event.end(); // SAI nếu muốn đo đến khi future hoàn tất.
event.commit();
return future;
~~~

Nếu method `startAsync` chỉ trả future ngay, thời lượng đo trên **chỉ là thời gian submit task**, không phải end-to-end business processing.

Mẫu minh họa tốt hơn:

~~~java
OrderEvent event = new OrderEvent();
event.operation = "async-order";
event.begin();

CompletableFuture<Result> future;
try {
    future = service.startAsync();
} catch (RuntimeException startFailure) {
    event.result = "FAILED";
    event.errorCode = "START";
    event.end();
    if (event.shouldCommit()) event.commit();
    throw startFailure;
}

return future.whenComplete((result, failure) -> {
    event.result = failure == null ? "OK" : "FAILED";
    event.errorCode = failure == null ? "NONE" : "ASYNC";
    event.end();
    if (event.shouldCommit()) event.commit();
});
~~~

**Đoạn minh họa**, `Result`/`service` là các kiểu/hàm ứng dụng. Nếu cancellation/timeout có đường xử lý độc lập với callback, dùng terminal state (ví dụ `AtomicBoolean.compareAndSet`) để bảo đảm **mỗi event chỉ end/commit một lần**. Nếu future không bao giờ kết thúc, chưa chắc có event; cần timeout/watchdog để bảo vệ nghiệp vụ.

JFR event **không tự là distributed trace**, và callback có thể chạy ở thread khác; không xem thread gắn với event như toàn bộ các threads từng tham gia. Nếu cần correlation xuyên process, kết hợp tracing có trace/span context và đồng hồ được quản lý.

## 11. Instrumentation không được đổi logic nghiệp vụ

**Sai:**

~~~java
if (event.isEnabled()) {
    validateOrder(); // Không chạy khi JFR tắt.
}
~~~

**Đúng:**

~~~java
validateOrder();
if (event.isEnabled()) {
    event.operation = safeOperationCode(); // Chỉ metadata tùy chọn.
}
~~~

Nếu JFR tắt, business logic vẫn phải chạy y hệt. Dùng `isEnabled` và `shouldCommit` để bỏ **chi phí instrumentation tùy chọn**, không dùng chúng làm cờ điều kiện của authorization, transaction hoặc validation.

JFR có overhead cấp phát event object, thu thập stack trace, metadata, buffer và file; nên chọn event type hữu ích, threshold phù hợp, tắt stack trace không cần, tránh String lớn và đo performance trong workload thật. Không mở/stop/dump recording cho từng call.

## 12. Tính percentile từ JFR có thể sai khi có threshold

~~~text
10.000 business operations:
  9.900 operations chạy 10–40 ms
    100 operations chạy 150–500 ms

threshold = 100 ms
  recording có thể chỉ chứa 100 operations chậm

p95(recorded events) KHÁC p95(10.000 operations).
~~~

Nếu JFR chỉ thu thập sự kiện chậm, phân bố trong file đã bị **lọc đầu vào**. Không dùng percentile của tập sự kiện đã lọc làm latency SLO toàn service. Dùng metrics histogram/counters tính SLA, và JFR để tìm nguyên nhân sự kiện chậm.

Một event có duration dương cũng không cho biết service lỗi hay thành công nếu bạn không ghi `result`; vì vậy fields outcome/errors là cần thiết. `RecordedEvent.getDuration()` cũng không tự cho biết đã mất bao nhiêu thời gian ở CPU, database hoặc remote API.

## 13. Test tự động bằng JUnit Jupiter 5.x

JUnit là dependency ngoài JDK. Nếu dự án đã có Jupiter 5.x và test runner tương thích Java 11, có thể lưu `BusinessJfrDemoTest.java` cùng package với `BusinessJfrDemo.java`:

~~~java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.stream.Collectors;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BusinessJfrDemoTest {
    @Test
    void bothBusinessOutcomesHaveDuration() throws Exception {
        Path file = Files.createTempFile("jfr-test-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.enable(BusinessJfrDemo.OrderEvent.class)
                    .withThreshold(Duration.ZERO);
                recording.start();
                assertEquals("ok", BusinessJfrDemo.process(false));
                assertThrows(IllegalArgumentException.class,
                    () -> BusinessJfrDemo.process(true));
                recording.stop();
                recording.dump(file);
            }

            List<RecordedEvent> events =
                RecordingFile.readAllEvents(file).stream()
                    .filter(e -> "demo.OrderProcessing".equals(
                        e.getEventType().getName()))
                    .collect(Collectors.toList());

            assertEquals(2, events.size());
            assertEquals(1, events.stream()
                .filter(e -> "OK".equals(e.getString("result"))).count());
            assertEquals(1, events.stream()
                .filter(e -> "FAILED".equals(e.getString("result"))).count());
            assertTrue(events.stream().allMatch(
                e -> e.getDuration().compareTo(Duration.ZERO) > 0));
        } finally {
            Files.deleteIfExists(file);
        }
    }
}
~~~

**Chú ý:** JUnit test được trình bày như ví dụ source compatible Java 11, **không được chạy riêng trong lượt này**; hai demo standalone phía trên đã được biên dịch/thực thi. Test JFR cần chạy trên môi trường CI có quyền tạo recording/file và module `jdk.jfr`.

### 13.1. Test matrix nên có

| Case | Kỳ vọng |
| --- | --- |
| Success | Có event OK, duration >0. |
| Validation failure | Có event FAILED, exception vẫn truyền lên. |
| Recording disabled | `isEnabled() == false`, business vẫn chạy. |
| Threshold cao | `shouldCommit() == false` cho event ngắn. |
| Threshold 0 | Event ngắn có thể được ghi. |
| Không gọi begin | Instant event, không coi là duration của business call. |
| Begin nhưng commit không end | Implicit end tại commit. |
| Async future | End khi future hoàn tất, không ở return. |
| File lớn | Dùng `RecordingFile` streaming để giảm heap. |
| JDK 11 runtime | Biên dịch và chạy trên JVM target thực, không chỉ `--release 11`. |

## 14. Đọc recording trong vận hành

JDK có `jfr` command-line utility. Với file `recording.jfr` thực sự đã lưu (demo tự xóa file tạm):

~~~bash
jfr summary recording.jfr
jfr print --events demo.OrderProcessing recording.jfr
~~~

Có thể mở file trong JDK Mission Control để quan sát timeline của business events cùng GC, thread, CPU và I/O. Nếu không thấy event, kiểm theo thứ tự: recording đã start đúng thời điểm, event enabled, threshold, tên `@Name`, scope begin/end, file đúng process và quá trình stop/dump/retention.

**Bảo mật:** JFR files có thể chứa stack traces, class names, thread names, đường dẫn, custom fields và thông tin nội bộ. Đặt quyền đọc, retention, encryption-at-rest/quy trình chia sẻ theo chính sách; không upload raw recordings sản phẩm ra public issue mà chưa kiểm.

## 15. Các lỗi triển khai phổ biến

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Chỉ `commit()` nhưng gọi đó là duration | Instant event. | `begin/end` quanh business work. |
| `begin` sau nửa logic | Duration thiếu bước đầu. | Đặt đúng scope. |
| `end` trước transaction commit | Không đo DB commit. | End theo hợp đồng “thành công”. |
| Không có `finally` | Mất events ở nhánh exception. | Catch status + finally end/commit. |
| Set `result=OK` ngay từ đầu | Failure có thể bị báo OK. | Set sau success. |
| Bỏ `end` rồi tính metadata chậm trước commit | Duration kéo dài sai. | End trước enrichment. |
| `shouldCommit` trước `end` | Kiểm threshold khi duration chưa chốt. | Gọi sau end. |
| `isEnabled` thay `shouldCommit` | Event bật vẫn có thể bị threshold lọc. | Hiểu hai phép kiểm. |
| Dùng threshold như business timeout | Work không tự dừng. | Timeout/cancel riêng. |
| Dump recording sau mọi request | Overhead lớn. | Commit event, dump theo vòng đời. |
| Dùng một Event cho nhiều threads | Race, sai fields/span. | Mỗi operation một event. |
| Đo future tới khi method trả | Không bao gồm async completion. | End ở terminal callback. |
| Tính p95 từ events bị lọc | Bias nghiêm trọng. | Metrics không bị threshold lọc cho SLO. |
| Dùng `getDuration` như CPU time | Sai vì elapsed gồm wait. | CPU/thread diagnostics riêng. |
| Fields là `Map`/`List` | Không được serialize như mong đợi. | Primitive và String ngắn. |
| Ghi token/email/raw SQL | Lộ PII trong recording. | Error/operation code an toàn. |
| `readAllEvents` cho file rất lớn | Chiếm heap. | Dùng `hasMoreEvents/readEvent`. |
| Test JDK24 rồi tuyên bố JVM11 đã kiểm | Chưa chứng minh runtime đích. | CI JDK11. |

## 16. Bài tập áp dụng

1. **Scope:** Vẽ ba event `OrderTotal`, `DbWrite`, `PaymentCall`; giải thích vì sao duration chồng nhau và không cộng đơn giản.
2. **Exception:** Viết mẫu có `try/finally` để luôn ghi result FAILED nếu business ném `IllegalArgumentException` mà không nuốt exception.
3. **Threshold:** Recording ghi đè `@Threshold("10 ms")` bằng 100ms. Event 50ms có được ghi vào recording đó không? **Không**.
4. **Enabled vs shouldCommit:** Recording bật, event 3ms, threshold 10ms: `isEnabled()==true`, `shouldCommit()==false` sau end.
5. **Implicit end:** Trong `begin(); work(); metadata(); commit();`, metadata có bị tính vào duration không? **Có** khi không end trước.
6. **Runnable:** Chạy `BusinessJfrDemo.java`, kiểm đúng hai events và năm dòng stdout. Vì sao không assert exact 35ms?
7. **Threshold demo:** Đổi threshold 1 giờ thành 50ms và thêm work khoảng 100ms, giải thích rủi ro flaky của timing test.
8. **Async:** Với future hoàn thành sau 700ms, chọn điểm `end` và cách tránh double commit khi bị timeout/cancel.
9. **Privacy:** Đổi raw user IDs/exception strings thành operation/result/errorCode có cardinality thấp.
10. **SLA:** Vì sao JFR thu chỉ slow events không dùng tính p95 toàn bộ traffic?
11. **Streaming:** Đọc file JFR lớn bằng `RecordingFile` theo từng event và filter tên custom event.
12. **CI:** Lập ma trận thử trên runtime JDK11 và một JDK mới, kiểm custom event, threshold, dump/read và schema.

## 17. Checklist và nguồn

**Checklist:** Chọn scope đúng; tạo event instance riêng; `begin` trước work, `end` đúng điểm business completion; outcome ghi trước commit kể cả lỗi; `shouldCommit` sau end; threshold có chủ đích; recording start/stop/dump độc lập business; duration không bị lầm với CPU, timeout hay SLO; file và fields không rò PII; có test Java 11 runtime và file JFR thật.

**Nguồn chính thức:**

- [Java SE 11 — jdk.jfr.Event](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Event.html): begin, end, commit, isEnabled, shouldCommit.
- [Java SE 11 — jdk.jfr package](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/package-summary.html): định nghĩa events, supported field types và threshold settings.
- [Java SE 11 — jdk.jfr.Recording](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/Recording.html): recording lifecycle.
- [Java SE 11 — EventSettings](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): withThreshold, withoutStackTrace.
- [Java SE 11 — RecordingFile](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc events từ file JFR.
- [Java SE 11 — RecordedEvent](https://docs.oracle.com/en/java/javase/11/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): timestamps, duration và fields.
- [JEP 328 — Flight Recorder](https://openjdk.org/jeps/328): JFR thuộc nền tảng JDK.

**Ghi nhớ:** `begin()` xác định thời điểm bắt đầu, `end()` **chốt thời lượng nghiệp vụ**, còn `commit()` ghi event (và tự kết thúc nếu chưa gọi end). `isEnabled()` chỉ phản ánh event được bật; `shouldCommit()` còn xét threshold. Để quan sát đúng, phải xác định scope, bảo toàn lỗi bằng finally, đọc duration từ `RecordedEvent` và không đánh đồng elapsed time với CPU, timeout, SLA hay distributed tracing.