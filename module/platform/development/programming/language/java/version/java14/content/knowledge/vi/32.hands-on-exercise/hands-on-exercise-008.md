# Thực hành tổng hợp: Quan sát tác vụ bằng RecordingStream và sự kiện JFR tự định nghĩa

## 1. Mục tiêu thực hành và bối cảnh

Một ứng dụng Java có thể chạy nhiều tác vụ xử lý dữ liệu. Khi theo dõi hệ thống, ta muốn biết **tác vụ nào**, **đã xử lý bao nhiêu mục**, **có thành công không**, **kéo dài bao lâu** và **có thể xem lại thông tin này khi cần không**, mà không phụ thuộc hoàn toàn vào các lệnh `System.out.println` nằm rải rác trong code.

**Java Flight Recorder (JFR)** là cơ chế ghi dữ liệu sự kiện được tích hợp trong JVM. Thư viện `jdk.jfr` cho phép ứng dụng định nghĩa event của riêng mình; `jdk.jfr.consumer.RecordingStream` cho phép đăng ký callback để **nhận các event từ JVM hiện tại trong khi chương trình đang hoạt động**.

Bài này xây một chương trình độc lập, thực sự chạy được, theo chuỗi:

```text
Tác vụ Java
  |
  +-- Tạo TaskEvent extends jdk.jfr.Event
  +-- Gán taskId / items / success
  +-- begin() -> thực hiện công việc -> end()
  +-- shouldCommit() -> commit()
                          |
                          v
                    Flight Recorder
                          |
                   flush theo các batch
                          |
                          v
                 RecordingStream
                   onEvent(name, e)
                          |
              đọc và copy các field
                          |
                          v
                    Observation
                          |
               kiểm thử bằng CountDownLatch
                          |
               +----------+-----------+
               |                      |
               v                      v
        console/số liệu       RecordingStream.dump
                               (Java 17 trở lên)
                                      |
                                 file .jfr
                                      |
                              RecordingFile
```

Sau bài này, người học có thể:

1. Định nghĩa **JFR event riêng** bằng `extends Event` và các annotation metadata.
2. Phân biệt **event producer** và **RecordingStream consumer**.
3. Bật event bằng `enable(Class)`, lọc bằng `onEvent(String, Consumer)`.
4. Khởi động `startAsync()`, ghi event bằng `commit()` và quan sát kết quả qua `RecordedEvent`.
5. Dùng `begin()`, `end()`, `shouldCommit()` để ghi nhận thời lượng/threshold.
6. Kiểm thử luồng bất đồng bộ bằng `CountDownLatch`, `AtomicReference`, timeout và assertion.
7. Quản lý `onError`, `setReuse`, giới hạn repository và vòng đời `close()`.
8. Với JDK 17+, ghi file `.jfr` để kiểm tra bằng `RecordingFile` hoặc công cụ `jfr`.
9. Nhận diện các lỗi quan trọng: event chưa bật, tên filter sai, callback nặng, JFR chậm theo batch, dữ liệu nhạy cảm, hiểu nhầm version.

### Phiên bản vẫn được hỗ trợ

| Thành phần | Từ phiên bản | Ghi chú hiện hành |
| --- | --- | --- |
| `jdk.jfr.Event` và custom events | Java 9 | API chính thức, còn hỗ trợ |
| `RecordingStream` / JFR Event Streaming | **Java 14**, JEP 349 | Cơ chế chính của bài, còn được hỗ trợ |
| `RecordingStream.startAsync`, `onEvent`, `enable` | Java 14 | Dùng trong demo cơ sở |
| `EventStream.onMetadata` | Java 16 | API bổ sung, không dùng trong demo Java 14 |
| `RecordingStream.dump(Path)` | **Java 17** | Chỉ có trong demo nâng cao Java 17+ |
| `RecordingStream.stop()` | Java 20 | Không dùng để giả lập Java 14/17; chú ý deadlock khi gọi trong callback |

**Special Note:** Bài chỉ hướng dẫn API Java/JFR còn áp dụng hiện nay. Các mốc trước chỉ để giải thích tương thích, không dạy cơ chế thử nghiệm hoặc lệnh legacy. **Không dùng `--enable-preview`** để chạy RecordingStream hay sự kiện custom.

## 2. JFR event khác gì log thông thường?

Một dòng log thường là chuỗi: người đọc hoặc parser phải phân tích text để tìm tên tác vụ, thời gian và trạng thái. Một **JFR event** chứa:

- **Event type/name**: ví dụ `lesson.TaskObserved`.
- **Event metadata**: label, category, mô tả các field.
- **Field có kiểu**: `String taskId`, `long items`, `boolean success`.
- **Thông tin thời gian**: start time, end time, duration khi ứng dụng ghi đúng.
- **Thông tin bổ sung theo settings**: stack trace và thread context khi bật.

Consumer có thể truy cập qua những phương thức có kiểu như `getString("taskId")` và `getLong("items")`; không phải parse một dòng string.

**Không coi JFR là message queue nghiệp vụ**: JFR phục vụ quan sát/profiling, có settings `enabled`, `threshold`, cơ chế batching và retention. Event JFR không phải lời hứa tất cả giao dịch sẽ được giao exactly-once cho một consumer hoặc bền vững như bản ghi database. Các tác vụ nghiệp vụ vẫn cần transaction, queue và cơ chế lưu trữ phù hợp nếu đó là yêu cầu.

### Producer và consumer chạy ở đâu?

`new RecordingStream()` tạo một recording stream **cho JVM hiện tại**. Nó không tự quan sát một JVM khác trên máy hoặc trong mạng. Với các tình huống giám sát JVM bên ngoài, phải chọn những API/tool được thiết kế cho remote/recording file/repository và đúng quyền truy cập.

**Producer** tạo `TaskEvent` và gọi `commit`. **Consumer** nhìn thấy `RecordedEvent` sau khi JFR flush dữ liệu. Không phải cùng một instance Java.

## 3. Định nghĩa custom event đúng cách

Ví dụ lớp:

```java
import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;

@Name("lesson.TaskObserved")
@Label("Task completed")
@Category({"Learning", "Tasks"})
@StackTrace(false)
class TaskEvent extends Event {
    @Label("Task ID")
    String taskId;

    @Label("Items processed")
    long items;

    @Label("Success")
    boolean success;
}
```

Đây là **class độc lập minh họa**; file demo hoàn chỉnh phía dưới dùng nested class với cùng cấu trúc.

| Thành phần | Vai trò |
| --- | --- |
| `extends Event` | Đăng ký kiểu sự kiện custom với JFR |
| `@Name` | Định danh event để dùng với `onEvent(name,...)` |
| `@Label` | Nhãn dễ đọc trong các công cụ JFR |
| `@Category` | Phân nhóm sự kiện |
| `@StackTrace(false)` | Không ghi stack trace mặc định khi không cần |
| `String taskId` | Định danh tác vụ do producer điền |
| `long items` | Số đơn vị đã xử lý |
| `boolean success` | Kết quả nghiệp vụ |

**`@Label` không thay thế `@Name`.** Nếu tên type là `lesson.TaskObserved`, callback dùng đúng tên đó để lọc, không dùng `Task completed`.

### Kiểu field được hỗ trợ

JFR event field hỗ trợ các kiểu primitive `boolean`, `char`, `byte`, `short`, `int`, `long`, `float`, `double` và một số reference type: `String`, `Thread`, `Class`. **Array, `List`, `Map`, enum, object tự định nghĩa và nhiều reference type khác không tự động trở thành JFR event field hợp lệ**. Static/transient fields không được ghi như instance event fields.

Nếu cần quan sát danh sách 10.000 records, thường hãy ghi `long items = 10_000`, không đưa nguyên danh sách đối tượng vào field JFR. Với lỗi nghiệp vụ, ghi **mã lỗi an toàn** thay vì cả exception, request payload hoặc secret.

### Tên type và class loader

`RecordingStream.enable(TaskEvent.class)` bật đúng class event được biết đến. `enable("lesson.TaskObserved")` bật theo tên; nếu nhiều class loader định nghĩa event cùng tên, thao tác theo tên có thể ảnh hưởng nhiều types. Trong chương trình tự tạo event, ưu tiên `enable(Class)` khi có class trong scope.

## 4. Vòng đời sự kiện: bắt đầu, kết thúc và commit

Trong producer:

```java
TaskEvent task = new TaskEvent();
task.taskId = "job-42";
task.begin();
try {
    long count = doWork();
    task.items = count;
    task.success = true;
} finally {
    task.end();
    if (task.shouldCommit()) {
        task.commit();
    }
}
```

Đây là **snippet**, giả sử `doWork()` và `TaskEvent` đã được định nghĩa; nó minh họa trình tự API chứ không là class chạy độc lập.

- `new TaskEvent()` chỉ tạo đối tượng, **chưa phát event**.
- `begin()` đánh dấu thời điểm bắt đầu tác vụ.
- `end()` đánh dấu thời điểm kết thúc; phải được gọi sau begin khi chủ động đo duration.
- `isEnabled()` cho biết hiện có recording bật loại event; hữu ích để tránh thu thập payload tốn kém khi event tắt.
- `shouldCommit()` kiểm tra event có được bật và đạt ngưỡng duration được cấu hình không.
- `commit()` ghi event và field vào JFR, sau đó consumer có thể nhận nó.

Một **instant event** có thể chỉ gán field rồi gọi `commit()`. Nhưng khi quan sát thời lượng tác vụ, `begin/end` giúp ghi duration có ý nghĩa.

### Thất bại nghiệp vụ và event

Ở tác vụ có thể ném exception, dùng `try/catch/finally` để quyết định có emit một event `success=false` hay không. Tránh để telemetry làm mất stack trace lỗi gốc hoặc nuốt exception. JFR callback `onError` lại là thứ khác: nó xử lý lỗi **trong stream/consumer**, không tự phản ánh thất bại của business task.

### Threshold

```java
stream.enable(TaskEvent.class)
      .withThreshold(java.time.Duration.ofMillis(50));
```

Snippet này yêu cầu ghi những event đủ duration theo threshold; tác vụ ngắn có thể không được commit/nhận. Để kiểm thử một event rất ngắn, dùng:

```java
stream.enable(TaskEvent.class)
      .withoutThreshold()
      .withoutStackTrace();
```

Không mặc định dùng `withoutThreshold()` cho mọi production workload. Nó có thể làm phát sinh quá nhiều dữ liệu khi tác vụ diễn ra với tần suất rất cao.

## 5. Ví dụ cơ sở tương thích Java 14 — nhận event tự định nghĩa

Tạo file **`BasicJfr14Demo.java`**:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class BasicJfr14Demo {
    @Name("lesson.BasicTask")
    static class BasicTask extends Event {
        String taskId;
        long count;
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch seen = new CountDownLatch(1);
        AtomicReference<String> value = new AtomicReference<>();

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(BasicTask.class).withoutThreshold();
            stream.onEvent("lesson.BasicTask", e -> {
                value.set(e.getString("taskId")
                        + ":" + e.getLong("count"));
                seen.countDown();
            });

            stream.startAsync();

            BasicTask event = new BasicTask();
            event.taskId = "t-1";
            event.count = 3;
            event.commit();

            if (!seen.await(20, TimeUnit.SECONDS)) {
                throw new AssertionError("JFR event timeout");
            }
            if (!"t-1:3".equals(value.get())) {
                throw new AssertionError(
                        "Wrong event: " + value.get());
            }
            System.out.println("seen=" + value.get());
        }
    }
}
```

Biên dịch và chạy bằng JDK có JFR:

```bash
javac --release 14 -encoding UTF-8 BasicJfr14Demo.java
java --add-modules jdk.jfr BasicJfr14Demo
```

**Stdout đã kiểm chứng trên Windows JDK 24 khi build target Java 14:**

```text
seen=t-1:3
```

### Tại sao hoạt động?

1. `BasicTask extends Event` khai báo loại sự kiện mới.
2. `@Name("lesson.BasicTask")` đặt tên loại event.
3. `enable(BasicTask.class)` bật nó.
4. `onEvent("lesson.BasicTask", ...)` đăng ký callback theo đúng tên.
5. `startAsync()` bắt đầu stream ở thread khác.
6. Producer gán `taskId/count` và `commit()`.
7. Consumer đọc `getString("taskId")` và `getLong("count")`.
8. `CountDownLatch` báo callback đã nhận event, không phải đợi “ước chừng” bằng `sleep`.
9. Assertion so sánh `t-1:3` xác nhận payload.
10. `try-with-resources` luôn đóng stream sau khi test.

**Đây là chương trình đầy đủ, không cần file ngoài hoặc API preview.** Để test tương thích, `--release 14` là cờ biên dịch; chương trình vẫn chạy trên JDK cài đặt thực tế có module `jdk.jfr`.

### Vì sao timeout có thể xảy ra?

Callback được gọi **bất đồng bộ theo batch**, không có cam kết sẽ xảy ra ngay khi `commit()` trả về. Nếu setting lọc event, stream chưa start hoặc JFR không khả dụng, nó cũng không đến. Một timeout 20 giây trong bài test là **giới hạn kiểm thử** chứ không phải lời hứa event luôn đến trong 20 giây ở production.

## 6. Ví dụ tổng hợp Java 17+: TaskEvent, snapshot, kiểm thử và file .jfr

Đây là bài thực hành chính. Nó thực hiện toàn bộ chuỗi: tự định nghĩa event, phát event của một tác vụ, nhận giá trị có kiểu ở callback, dùng snapshot bất biến, xác minh một file JFR có đúng event, đóng tài nguyên an toàn.

**Vì sao target Java 17?** Chương trình dùng `RecordingStream.dump(Path)`, một API **có từ Java 17**. Không dùng `--release 14` cho toàn bộ chương trình này. Những phần `RecordingStream`, `Event` và callback trước đó vẫn dùng được từ Java 14.

Tạo file **`TaskJfrObserverDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

import jdk.jfr.Category;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.StackTrace;
import jdk.jfr.consumer.RecordedEvent;
import jdk.jfr.consumer.RecordingFile;
import jdk.jfr.consumer.RecordingStream;

public class TaskJfrObserverDemo {
    static final String EVENT_NAME = "lesson.TaskObserved";

    @Name(EVENT_NAME)
    @Label("Task completed")
    @Category({"Learning", "Tasks"})
    @StackTrace(false)
    static class TaskEvent extends Event {
        @Label("Task ID")
        String taskId;

        @Label("Items processed")
        long items;

        @Label("Success")
        boolean success;
    }

    static final class Observation {
        final String type;
        final String taskId;
        final long items;
        final boolean success;
        final boolean durationNonNegative;

        Observation(String type, String taskId, long items,
                    boolean success, boolean durationNonNegative) {
            this.type = type;
            this.taskId = taskId;
            this.items = items;
            this.success = success;
            this.durationNonNegative = durationNonNegative;
        }
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch received = new CountDownLatch(1);
        AtomicReference<Observation> result =
                new AtomicReference<>();
        AtomicReference<Throwable> callbackError =
                new AtomicReference<>();

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(TaskEvent.class)
                    .withoutThreshold()
                    .withoutStackTrace();

            stream.setReuse(true);
            stream.setMaxAge(Duration.ofMinutes(1));
            stream.setMaxSize(8 * 1024 * 1024);

            stream.onError(error -> {
                callbackError.compareAndSet(null, error);
                received.countDown();
            });

            stream.onEvent(EVENT_NAME, event -> {
                try {
                    result.set(new Observation(
                            event.getEventType().getName(),
                            event.getString("taskId"),
                            event.getLong("items"),
                            event.getBoolean("success"),
                            !event.getDuration().isNegative()));
                } catch (Throwable error) {
                    callbackError.compareAndSet(null, error);
                } finally {
                    received.countDown();
                }
            });

            stream.startAsync();

            TaskEvent task = new TaskEvent();
            task.taskId = "job-42";
            task.begin();
            try {
                long processed = 0;
                for (int i = 0; i < 7; i++) {
                    processed++;
                }
                task.items = processed;
                task.success = true;
            } finally {
                task.end();
                if (task.shouldCommit()) {
                    task.commit();
                }
            }

            if (!received.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "JFR event delivery timed out");
            }
            if (callbackError.get() != null) {
                throw new IllegalStateException(
                        "JFR callback failed", callbackError.get());
            }

            Observation observation = result.get();
            if (observation == null ||
                    !EVENT_NAME.equals(observation.type) ||
                    !"job-42".equals(observation.taskId) ||
                    observation.items != 7 ||
                    !observation.success ||
                    !observation.durationNonNegative) {
                throw new AssertionError("Received event mismatch");
            }

            Path jfrFile = Files.createTempFile(
                    "task-observed-", ".jfr");
            try {
                stream.dump(jfrFile);

                boolean found = false;
                for (RecordedEvent item :
                        RecordingFile.readAllEvents(jfrFile)) {
                    if (EVENT_NAME.equals(
                            item.getEventType().getName()) &&
                            "job-42".equals(
                            item.getString("taskId")) &&
                            item.getLong("items") == 7) {
                        found = true;
                        break;
                    }
                }

                if (!found) {
                    throw new AssertionError(
                            "Missing event in dump");
                }
                System.out.println(
                        "recordingFileContainsEvent=" + found);
            } finally {
                Files.deleteIfExists(jfrFile);
            }

            System.out.println("eventType=" + observation.type);
            System.out.println("taskId=" + observation.taskId);
            System.out.println("items=" + observation.items);
            System.out.println("success=" + observation.success);
            System.out.println("durationNonNegative="
                    + observation.durationNonNegative);
            System.out.println("callbackError=false");
        }
    }
}
```

### Biên dịch và chạy

```bash
javac --release 17 -encoding UTF-8 TaskJfrObserverDemo.java
java --add-modules jdk.jfr TaskJfrObserverDemo
```

**Stdout chính xác đã kiểm chứng trên Windows JDK 24:**

```text
recordingFileContainsEvent=true
eventType=lesson.TaskObserved
taskId=job-42
items=7
success=true
durationNonNegative=true
callbackError=false
```

Chương trình kiểm tra các điều kiện trước khi in, nên nếu event sai type/field hoặc callback chưa nhận được, nó sẽ ném exception chứ không in kết quả thành công giả. Thời lượng cụ thể **không được hardcode** vì tùy máy và tải; phép kiểm tra chỉ yêu cầu duration không âm.

## 7. Phân tích chương trình theo từng pha

### Pha 1 — Bật loại event

```java
stream.enable(TaskEvent.class)
      .withoutThreshold()
      .withoutStackTrace();
```

`enable(Class)` chọn custom class, `withoutThreshold` tránh việc tác vụ vài microsecond bị loại; `withoutStackTrace` giảm dữ liệu không cần thiết khi chỉ muốn xem taskId, items và success. Trong production có thể đặt threshold cao hơn nếu chỉ quan tâm tác vụ chậm.

Đăng ký `onEvent(EVENT_NAME,...)` **trước** khi start. Callback được cung cấp một `RecordedEvent`, không phải `TaskEvent`.

### Pha 2 — Kiểm soát vòng đời và retention

```java
stream.setMaxAge(Duration.ofMinutes(1));
stream.setMaxSize(8 * 1024 * 1024);
stream.startAsync();
```

`setMaxAge` và `setMaxSize` giới hạn lượng dữ liệu giữ trong repository của recording stream; tài liệu `RecordingStream` cảnh báo nếu cả hai đều không giới hạn, kích thước recording có thể tăng rất lớn trong hệ thống chạy lâu.

**8 MiB là retention budget**, không có nghĩa JVM chỉ dùng 8 MiB RAM và không có nghĩa mọi event được giữ vĩnh viễn. Với ứng dụng thật, cân nhắc event rate, disk budget, thời gian giữ cần thiết và bảo mật repository.

`startAsync()` làm các callbacks chạy từ thread riêng. Trái lại `start()` xử lý actions trong thread hiện tại và có thể block; nếu main cần tiếp tục tạo event, `startAsync()` là lựa chọn hợp lý.

### Pha 3 — Producer phát event

```java
TaskEvent task = new TaskEvent();
task.taskId = "job-42";
task.begin();
try {
    long processed = 0;
    for (int i = 0; i < 7; i++) {
        processed++;
    }
    task.items = processed;
    task.success = true;
} finally {
    task.end();
    if (task.shouldCommit()) {
        task.commit();
    }
}
```

`taskId` là identifier, `items` là kết quả số lượng, `success` là kết quả tác vụ. `begin/end` đo duration, `shouldCommit()` kiểm tra event có được ghi theo settings không, `commit()` nộp event cho JFR.

**Không được suy từ `task.commit()` rằng callback đã chạy xong.** JFR chuyển event tới callback theo các batches và các thời điểm flush khác nhau.

### Pha 4 — Callback biến `RecordedEvent` thành snapshot

```java
stream.onEvent(EVENT_NAME, event -> {
    result.set(new Observation(
            event.getEventType().getName(),
            event.getString("taskId"),
            event.getLong("items"),
            event.getBoolean("success"),
            !event.getDuration().isNegative()));
    received.countDown();
});
```

Đây là **snippet rút gọn chỉ minh họa đoạn thành công**; chương trình đầy đủ có `try/catch/finally` để tránh bỏ sót lỗi. `RecordedEvent` có metadata, field và duration; nó không tự biết “taskId” như một method Java mà truy cập bằng tên field.

`AtomicReference<Observation>` giữ snapshot giữa consumer thread và main thread. `CountDownLatch.countDown()` đánh dấu callback đã xử lý. `await(20, TimeUnit.SECONDS)` chờ có giới hạn.

### Pha 5 — Phân biệt onError và task failure

```java
stream.onError(error -> {
    callbackError.compareAndSet(null, error);
    received.countDown();
});
```

`onError` báo lỗi của stream/consumer action. Trạng thái `task.success=false` là thông tin **nghiệp vụ do producer ghi**. Không nên coi chúng là cùng một thứ.

Callback đầy đủ có `try/catch` để lưu lỗi, tránh che mất stack trace và không in `callbackError=false` nếu thực sự đã có lỗi. Trong production, hãy có logging/metrics có kiểm soát, tránh bỏ qua lỗi consumer.

### Pha 6 — Lưu tệp JFR (Java 17+)

```java
Path file = Files.createTempFile("task-observed-", ".jfr");
try {
    stream.dump(file);
    // RecordingFile có thể đọc lại event đã lưu.
} finally {
    Files.deleteIfExists(file);
}
```

`dump(Path)` **chỉ có từ Java 17**, yêu cầu stream đã start nhưng chưa close. Javadoc khuyến nghị cấu hình `setMaxAge` hoặc `setMaxSize` trước khi start; nếu retention không được giữ phù hợp, dump có thể thiếu dữ liệu mong đợi.

Trong demo, code đọc file bằng `RecordingFile.readAllEvents(file)`, tìm event `lesson.TaskObserved` với `job-42` và `items=7`. Đây là **file nhỏ** do chính ứng dụng tạo. Javadoc không khuyến khích `readAllEvents` cho recording lớn vì có thể tốn nhiều RAM; khi đó dùng `RecordingFile.hasMoreEvents()/readEvent()` theo kiểu đọc tuần tự.

**Tệp tạm đã được xóa sau khi test.** Không hướng dẫn mở tệp này bằng `jfr` sau khi demo kết thúc mà chưa sửa đường dẫn/chính sách cleanup.

## 8. `setReuse(true)` và lỗi giữ tham chiếu RecordedEvent

`EventStream` có thể tái sử dụng **một đối tượng `RecordedEvent` để biểu diễn nhiều event khác nhau**. Với `setReuse(true)`, callback không nên giữ `RecordedEvent` sau khi kết thúc action.

Sai:

```java
// Anti-pattern: queue có thể lưu đối tượng đã bị tái sử dụng.
stream.onEvent(EVENT_NAME, recorded ->
        queue.add(recorded));
```

Snippet này giả định có một `queue`; không phải chương trình độc lập. Nếu một worker xử lý object sau callback, các field có thể không còn đại diện cho event ban đầu.

Đúng:

```java
stream.onEvent(EVENT_NAME, recorded -> {
    String taskId = recorded.getString("taskId");
    long items = recorded.getLong("items");
    queue.offer(new TaskSnapshot(taskId, items));
});
```

Đây là snippet có class `TaskSnapshot` và queue do ứng dụng tự định nghĩa; nên dùng **bounded queue** có kiểm soát. Bài test dùng `Observation` immutable final fields nên sau callback có thể đọc an toàn.

Một lựa chọn khác là `stream.setReuse(false)` để mỗi event được cấp một object riêng, đổi lại có thể tăng allocation. Dù vậy, đừng giữ vô hạn dữ liệu sự kiện trong bộ nhớ chỉ vì reuse đã tắt.

## 9. Callback nhanh và quản lý tải

`RecordingStream.startAsync()` phân phối actions trong một thread riêng. Nếu callback liên tục làm HTTP request, ghi database, `Thread.sleep` hoặc chờ khóa dài, quá trình xử lý sự kiện có thể bị chậm.

Một kiến trúc tốt cho ứng dụng lớn:

```text
JFR onEvent (thread đọc stream)
    |
    +-- Chỉ đọc field và copy snapshot
    +-- queue.offer(snapshot)  [không block]
    |
    v
Hàng đợi giới hạn 1_000 snapshots
    |
    +-- worker độc lập xử lý/tổng hợp/log
    |
    +-- khi queue đầy: tăng droppedCount
         + cảnh báo và chính sách sampling
```

Các con số trong sơ đồ là **ví dụ**, không phải thông số mặc định của JFR. Bài cơ sở không cần queue riêng vì callback chỉ copy vài field.

Các nguyên tắc production:

1. Giữ callback **nhanh và có giới hạn thời gian**.
2. Không gọi xử lý nặng hoặc blocking I/O trực tiếp trong callback nếu không kiểm soát độ trễ.
3. Giám sát consumer lag, queue depth và số sự kiện bị drop.
4. Không giữ `RecordedEvent` có thể được reuse ngoài callback.
5. Không dùng `onEvent` để commit dữ liệu nghiệp vụ bắt buộc.
6. Nếu cần chính sách backpressure mạnh hơn, chọn cơ chế telemetry/queue chuyên dụng.
7. Tránh log toàn bộ event/stack trace nếu có thể chứa dữ liệu nhạy cảm.

### `onFlush` không phải trigger cho một giao dịch

`onFlush(Runnable)` được gọi sau khi một batch đã được flush, có thể phục vụ tổng hợp/đẩy metrics. Nó **không có nghĩa business task đã commit**, cũng không bảo đảm một message đã được gửi exactly once. Nếu cần thứ tự, dùng sequence number/ID từ producer và logic xử lý bổ sung.

## 10. Các tình huống bật/tắt event

**Quan sát tất cả tác vụ trong demo:**

```java
stream.enable(TaskEvent.class).withoutThreshold();
```

**Chỉ quan sát tác vụ có duration từ 100 ms trở lên:**

```java
stream.enable(TaskEvent.class)
      .withThreshold(Duration.ofMillis(100));
```

**Vô hiệu loại event theo class:**

```java
stream.disable(TaskEvent.class);
```

Đây là **ba snippet thay thế** trong code đã có `stream` và `TaskEvent`. Không thực hiện chúng đồng thời trong một bài test rồi kỳ vọng tất cả task được ghi.

### Vì sao `shouldCommit` có thể false?

- Không có recording bật event.
- Event bị disable bởi settings.
- Duration chưa đạt threshold cấu hình.
- Một số điều kiện của event/recording khiến event chưa đủ điều kiện ghi.

Nếu `shouldCommit()` false, code có thể bỏ `commit()`. Với những event có payload tốn kém, có thể kiểm tra `isEnabled()` sớm để tránh tạo chuỗi/thu thập chi tiết không cần thiết, rồi `shouldCommit()` trước `commit()`.

### Đừng dùng `withPeriod` để tự chạy job

`withPeriod` cấu hình periodic event theo cơ chế event được thiết kế định kỳ. Nó **không tự chạy công việc nghiệp vụ hay gọi `commit()` trên custom event** của bạn mỗi giây. Với custom task event, producer phải phát event khi thực sự có tác vụ.

### Tránh kỳ vọng điều kiện ngưỡng chính xác từng mili-giây

`Thread.sleep(100)` có thể bị jitter theo scheduler, CPU và load. Nếu test threshold, chọn biên đủ xa ngưỡng hoặc kiểm tra bằng số liệu duration, không viết assertion dựa trên độ chính xác tuyệt đối của một lần sleep.

## 11. Quan sát tác vụ thất bại

Trong thực tế, task có thể ném exception. Một pattern hợp lý:

```java
// Snippet trong service: processBatch(), safeTaskId và TaskEvent
// được khai báo ở chương trình thật.
TaskEvent task = new TaskEvent();
task.taskId = safeTaskId;
task.begin();
try {
    task.items = processBatch();
    task.success = true;
} catch (RuntimeException failure) {
    task.success = false;
    // Ghi log lỗi theo chính sách; không nhúng exception/user payload.
    throw failure;
} finally {
    task.end();
    if (task.shouldCommit()) {
        task.commit();
    }
}
```

Chú ý:

- `finally` thực hiện khi thành công hoặc lỗi.
- `success=false` là **giá trị sự kiện do producer quyết định**, không liên quan `onError` của consumer.
- Không để việc quan sát che mất exception nghiệp vụ gốc nếu telemetry thất bại.
- Nếu `processBatch()` có side effect, JFR event không thể tự thực hiện rollback.
- Không ghi mật khẩu, access token, dữ liệu cá nhân hay nội dung request nhạy cảm vào JFR.

## 12. Đọc lại sự kiện và công cụ JFR

Ba cách quan sát có thể kết hợp:

| Nhu cầu | API/công cụ | Đặc điểm |
| --- | --- | --- |
| Quan sát khi process đang chạy | `RecordingStream.onEvent` | Callback trong JVM hiện tại |
| Phân tích recording nhỏ đã lưu | `RecordingFile.readAllEvents` | Thuận tiện nhưng nạp nhiều event vào RAM |
| Phân tích recording lớn | `RecordingFile` với `hasMoreEvents/readEvent` | Duyệt tuần tự |
| Xem bằng CLI/JMC | `jfr print`, JDK Mission Control | Cần file JFR thực tế |

Nếu có file `task-observed.jfr` được giữ lại sau dump:

```bash
jfr print --events lesson.TaskObserved task-observed.jfr
```

Không áp lệnh này trực tiếp vào file tạm của demo nếu demo đã xóa. Để thử, thay code tạo/xóa file bằng một đường dẫn được xác nhận có thể ghi, rồi giữ file sau khi dump.

Đọc tuần tự file:

```java
// Snippet: Path recordingPath trỏ đến file JFR đáng tin.
try (RecordingFile recording = new RecordingFile(recordingPath)) {
    while (recording.hasMoreEvents()) {
        RecordedEvent event = recording.readEvent();
        if ("lesson.TaskObserved".equals(
                event.getEventType().getName())) {
            // Xử lý event hợp lệ.
        }
    }
}
```

Chỉ đọc **JFR file từ nguồn đáng tin cậy** như cảnh báo của Javadoc; không tùy tiện phân tích file lạ có kích thước lớn hoặc chứa dữ liệu nhạy cảm.

## 13. Phân biệt version để không dạy API lỗi thời/sai phiên bản

**Java 14** đã có `RecordingStream`, `Event`, `start/startAsync`, `onEvent`, `enable`, `setMaxAge`, `setMaxSize` và các API cơ sở dùng trong `BasicJfr14Demo`. Chương trình đó đã được kiểm thử bằng `javac --release 14`.

**Java 17** bổ sung `RecordingStream.dump(Path)`. Chương trình `TaskJfrObserverDemo` dùng API này nên phải compile target `--release 17` hoặc cao hơn. Nếu thử `--release 14`, compiler có thể báo **cannot find symbol: method dump(Path)**. Đây là **giới hạn phiên bản API**, không phải do event không hợp lệ.

**Java 20** bổ sung `RecordingStream.stop()`; đây là phương thức hiện còn được hỗ trợ, nhưng không thể sử dụng trực tiếp khi target Java 14/17. Javadoc cũng cảnh báo gọi `stop()` **bên trong callback `onEvent`** có thể block vô hạn vì chờ chính quá trình xử lý event.

**`EventStream.onMetadata`** được bổ sung sau Java 14; khi viết tool phải chạy trên Java 14, không sử dụng các bổ sung JDK mới mà không kiểm tra version. Ngược lại, trong project target 21/25, dùng API mới có thể hợp lý nếu đã đọc đúng Javadoc.

**Không dùng** preview flag hoặc cách khởi chạy JFR từ hướng dẫn incubator cũ để thay `RecordingStream` chuẩn. JFR streaming theo JEP 349 đã là API chính thức.

## 14. Chẩn đoán các lỗi thường gặp

| Lỗi/hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Không thấy event | Chưa `enable`, `start` hoặc `commit` | Kiểm tra vòng đời và điều kiện ghi |
| `onEvent` không chạy | Tên filter khác `@Name` | Dùng hằng `EVENT_NAME` nhất quán |
| Callback nhận chậm | JFR phân phối theo batches | Dùng latch, timeout, đo latency thực |
| Timeout bài test | Threshold lọc, repository không hoạt động, callback lỗi | Xem `shouldCommit`, settings, `onError` |
| `getString("taskId")` lỗi | Field name/type không tồn tại | Kiểm tra event definition và metadata |
| Field `List`/`Map` không xuất hiện | Không phải loại field JFR hỗ trợ | Ghi primitive/String được chọn |
| `getDuration` không như mong muốn | Không gọi `begin/end` cho tác vụ | Đặt timing đúng phạm vi |
| `start()` làm main block | Start đồng bộ ở thread hiện tại | Dùng `startAsync()` trong demo |
| Giá trị callback thay đổi sau khi nhận | `RecordedEvent` có thể bị reuse | Tạo immutable snapshot ngay trong callback |
| Ứng dụng chậm khi có nhiều JFR events | Event rate/stack trace/callback quá nặng | Threshold, sampling, queue bounded |
| `onError` không ghi nhận lỗi tác vụ | Nó xử lý lỗi stream, không phải business | Ghi `success=false` trong producer |
| Không đọc được `dump(Path)` ở Java 14 | API chỉ có từ Java 17 | Dùng target Java 17+ hoặc bỏ bước dump |
| `dump` sau khi close | Stream không còn mở để dump | Dump khi stream đã start và chưa close |
| `RecordingFile.readAllEvents` dùng nhiều RAM | Đọc tất cả event vào list | Chuyển sang đọc tuần tự |
| Gọi `stop()` trong `onEvent` treo | Stop đợi xử lý events; có thể deadlock | Điều khiển lifecycle từ thread khác |
| Không tìm thấy file sau demo | Demo xóa file tạm ở `finally` | Lưu ra path mong muốn nếu cần giữ |
| JFR không khởi tạo | JVM thiếu JFR hoặc repository không khả dụng | Dùng full JDK phù hợp, kiểm tra lỗi tạo stream |
| Logging lộ dữ liệu | Event chứa payload nhạy cảm | Giới hạn field, quyền và retention |

### Quy trình điều tra ngắn

1. Trước hết kiểm tra **module JFR và việc tạo `RecordingStream`**.
2. Soát **tên `@Name`, `enable`, `onEvent`**.
3. Kiểm tra producer đã gọi **`commit`** chưa.
4. Với event nhanh, thử **`withoutThreshold`** trong môi trường test.
5. Bắt **`onError`** và lưu Throwable.
6. Dùng **latch có timeout** thay cho sleep cố định.
7. Kiểm tra types qua `getString/getLong/getBoolean`.
8. Nếu dùng reuse, chỉ giữ snapshot.
9. Với file recording, kiểm tra **stream.dump trước close** và retention.
10. Nếu cần chính xác thời gian/delivery, đo metrics của pipeline thay vì suy đoán.

## 15. Kiểm thử và tiêu chí chấp nhận của bài tổng hợp

| Hạng mục | Bằng chứng |
| --- | --- |
| Event riêng được định nghĩa | Có class `TaskEvent extends Event`, `@Name` và field |
| Producer ghi event | `begin/end/shouldCommit/commit` |
| Stream được bật và chạy | `enable(TaskEvent.class)`, `startAsync()` |
| Consumer nhận đúng type | `eventType=lesson.TaskObserved` |
| Consumer nhận đúng tác vụ | `taskId=job-42` |
| Consumer nhận số lượng | `items=7` |
| Consumer nhận trạng thái | `success=true` |
| Duration có nghĩa | `durationNonNegative=true` |
| Callback không báo lỗi | `callbackError=false` |
| File ghi chứa event | `recordingFileContainsEvent=true` |
| Tài nguyên được đóng | `try-with-resources`, file xóa trong `finally` |
| Java 14 cơ sở còn tương thích | `javac --release 14` và `seen=t-1:3` |
| Java 17 tổng hợp đúng | `javac --release 17` và stdout ở phần 6 |

**Không suy rộng kết quả**: một lần chạy có callback thành công không chứng minh JFR có độ trễ bằng 0, không chứng minh chính xác mọi nguồn hệ điều hành, và không biến event thành bản ghi nghiệp vụ đã commit bền vững.

## 16. Checklist khi áp dụng

- [ ] Class event đặt tên ổn định, tránh trùng namespace?
- [ ] Field chỉ dùng kiểu JFR hỗ trợ và không chứa thông tin nhạy cảm?
- [ ] `@Name` và chuỗi `onEvent` trùng chính xác?
- [ ] `enable` xảy ra trước `startAsync`?
- [ ] Producer thật sự gọi `commit`; threshold có phù hợp?
- [ ] `begin/end` bao đúng khoảng thời gian cần đo?
- [ ] Consumer đọc đúng kiểu field?
- [ ] Có xử lý `onError` và timeout callback?
- [ ] `RecordedEvent` được copy trước khi callback kết thúc nếu reuse?
- [ ] Có giới hạn retention `setMaxAge/setMaxSize`?
- [ ] Callback đủ nhẹ, không làm network/database blocking?
- [ ] Đã xác nhận tập hợp metrics cần lưu, queue bounded nếu offload?
- [ ] Đã phân biệt `close` với `stop` và đúng phiên bản?
- [ ] Nếu dùng `dump`, target Java 17+ và stream chưa close?
- [ ] Nếu muốn phân tích file sau chạy, file được giữ lại có chủ đích?
- [ ] Với JFR file lớn, dùng streaming reader thay `readAllEvents`?
- [ ] Đã test cả task thành công, lỗi, filtering và callback failure?
- [ ] Đã phân biệt telemetry với business queue/transaction?
- [ ] Không deserialize hoặc parse file JFR từ nguồn không tin cậy?
- [ ] Không dạy preview/legacy thay cho API hiện hành?

## 17. Câu hỏi tự kiểm tra

**1. `new RecordingStream()` nghe các event của process nào?**

Của **JVM hiện tại**, không tự động mọi JVM ở nơi khác.

**2. `@Name` và `@Label` dùng thay nhau trong `onEvent` được không?**

Không. `onEvent(name,...)` lọc theo event type name do `@Name` định nghĩa, không theo label hiển thị.

**3. Chỉ `new TaskEvent()` có đủ để consumer nhìn thấy event?**

Không. Producer phải điền field và gọi `commit()` khi event có thể được ghi theo settings.

**4. Vì sao `startAsync` có ích hơn `start` trong chương trình vừa làm việc vừa theo dõi?**

`startAsync` xử lý callback ở thread riêng; `start` xử lý trong thread hiện tại và có thể block.

**5. Tại sao demo dùng `CountDownLatch` thay vì `Thread.sleep(100)`?**

Latch đợi một **điều kiện xác định** là callback đã được thực hiện hoặc timeout; sleep chỉ đo thời gian.

**6. `RecordedEvent.getDuration` là thời gian nào?**

Là duration của **event producer** dựa trên `begin/end`, không phải thời gian chờ callback hoặc thời gian consumer xử lý.

**7. `setReuse(true)` có thể gây lỗi gì?**

Nếu giữ tham chiếu `RecordedEvent` sau callback, nó có thể bị dùng lại cho event khác. Nên copy field thành snapshot.

**8. `onError` có phải event có `success=false` không?**

Không. `onError` báo lỗi stream/action; `success` là trường trạng thái do producer thiết lập.

**9. `RecordingStream.dump(Path)` có thể biên dịch với `--release 14`?**

Không. `dump` được bổ sung **từ Java 17**; phần RecordingStream cơ sở có từ Java 14.

**10. Tại sao `jfr print` không tìm thấy file sau khi chạy demo nâng cao?**

Vì demo dùng file tạm và xóa file trong `finally`. Muốn xem sau chạy phải giữ output path.

**11. JFR event có thay message queue giao dịch đảm bảo exactly-once không?**

Không. Nó phục vụ observability/profiling và có settings/filtering/retention riêng.

**12. Có nên ghi token hoặc dữ liệu người dùng vào các JFR custom fields không?**

Không. Chỉ ghi thông tin cần thiết đã được đánh giá bảo mật và chính sách retention.

## 18. Nguồn tài liệu chính thức, còn áp dụng

- [Oracle Java 25 API — RecordingStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): `enable`, `start/startAsync`, `dump(Path)`, `setReuse`, `setMaxAge/Size`, version và lifecycle.
- [Oracle Java 25 API — EventStream](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): callbacks, event batching, `onError`, `onFlush`, `setReuse` và close semantics.
- [Oracle Java 25 API — Event](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): tự tạo event, field types, `begin/end`, `shouldCommit` và `commit`.
- [Oracle Java 25 API — EventSettings](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): cấu hình threshold/stack trace.
- [Oracle Java 25 API — RecordedEvent](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html) và [RecordedObject](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): đọc metadata, duration và field có kiểu.
- [Oracle Java 25 API — RecordingFile](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc JFR recording theo list/stream và cảnh báo về file lớn.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): mốc bổ sung RecordingStream ở Java 14.
- [Oracle Java 14 API — RecordingStream](https://docs.oracle.com/en/java/javase/14/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): xác minh API gốc từ Java 14.
- [Oracle Java 17 API — RecordingStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): xác minh `dump(Path)` có từ Java 17.

**Kết luận:** Quan sát một tác vụ bằng JFR cần cả **producer phát `Event` có cấu trúc** và **RecordingStream bật đúng event, đăng ký callback, khởi động và quản lý vòng đời**. `startAsync` cho phép chương trình tiếp tục xử lý, `CountDownLatch` giúp kiểm thử ổn định, snapshot tránh sai dữ liệu khi `RecordedEvent` được reuse, còn `dump(Path)` của Java 17+ đưa dữ liệu ra file. Luôn tách rõ **quan sát JFR** khỏi bảo đảm giao dịch, độ trễ tức thời và quản lý dữ liệu nhạy cảm.
