# Khởi chạy RecordingStream bất đồng bộ bằng `startAsync()`

> **Module Java 14 — RecordingStream.** `jdk.jfr.consumer.RecordingStream` được đưa vào Java 14 qua **JEP 349 (JFR Event Streaming)** như một API chính thức, không phải cú pháp preview. API vẫn áp dụng ở các JDK hiện đại; bài dùng những kiến thức còn được hỗ trợ, với ví dụ biên dịch ở mức **Java 17** bằng JDK có hỗ trợ Java Flight Recorder và được cập nhật. Không cần JDK 14 cũ, cũng không dùng `--enable-preview`.

## 1. Mục tiêu

Bạn sẽ giải thích được:

1. Vì sao `startAsync()` cho phép **luồng gọi tiếp tục chạy** và callback được xử lý ở **một luồng riêng**.
2. Khác biệt giữa `RecordingStream.start()` và `RecordingStream.startAsync()`.
3. Trình tự `enable` → `onEvent`/`onError` → `startAsync` → xử lý ứng dụng → `close`.
4. Tại sao **startAsync trả về không có nghĩa sự kiện đã đến**; JFR gửi event theo batch.
5. Cách dùng `CountDownLatch`/`AtomicReference` để chờ một event cụ thể an toàn giữa các luồng.
6. Giới hạn `close()`/`awaitTermination()`, lỗi gọi `startAsync()` lặp và xử lý exception trong callback.
7. Rủi ro giữ `RecordedEvent` ngoài callback, cách quản lý overhead và thông tin nhạy cảm.
8. Cách viết test với stdout xác định, không hardcode số sự kiện hoặc CPU load phụ thuộc môi trường.

## 2. `RecordingStream` là gì?

Java Flight Recorder (JFR) tạo event mô tả hoạt động JVM như CPU load, garbage collection, file I/O, socket I/O và sự kiện do ứng dụng tự định nghĩa. `RecordingStream` giúp **tạo recording và tiêu thụ các event của JVM hiện tại** trong lúc ứng dụng còn chạy, thay vì bắt buộc xuất một file `.jfr` rồi mới phân tích.

Các kiểu liên quan:

| Kiểu | Ý nghĩa |
| --- | --- |
| `jdk.jfr.Event` | Custom event do ứng dụng phát sinh qua `commit()`. |
| `jdk.jfr.consumer.RecordedEvent` | Đối tượng đọc thông tin event nhận được. |
| `jdk.jfr.consumer.RecordingStream` | Tạo recording và streaming event từ JVM hiện tại. |
| `jdk.jfr.consumer.EventStream` | Giao diện tiêu thụ event, đăng ký action, bắt đầu/đóng. |
| `EventStream.openFile(...)` | Đọc recording từ file, khác việc tạo `RecordingStream`. |

Import:

~~~java
import jdk.jfr.consumer.RecordingStream;
~~~

Đây là **mảnh import**, chưa phải chương trình độc lập.

Nếu một ứng dụng modular dùng `module-info.java`, có thể cần khai báo:

~~~java
module demo.monitor {
    requires jdk.jfr;
}
~~~

Đây là **mảnh module descriptor**. Các chương trình chạy từ classpath trong bài không cần file này. JVM phải có hỗ trợ JFR; nếu runtime tùy biến đã loại bỏ module `jdk.jfr` thì phải điều chỉnh môi trường, không phải bật Java preview.

## 3. `start()` và `startAsync()` khác nhau

| Thuộc tính | `start()` | `startAsync()` |
| --- | --- | --- |
| Bắt đầu xử lý event stream | Có | Có |
| Luồng thực hiện các action | **Luồng gọi `start()`** | **Một luồng riêng** của stream |
| Luồng gọi tiếp tục làm việc ngay? | Thông thường bị giữ trong xử lý tới khi stream kết thúc | **Có**, sau khi khởi động bất đồng bộ |
| Giá trị trả về | `void` | `void` |
| Trả `Future` để chờ không? | Không | Không |
| Gọi khi stream đã start/closed | `IllegalStateException` | `IllegalStateException` |

`startAsync()` **không tạo một thread mới cho từng event**, không nhận `Executor`, không biến `RecordingStream` thành `CompletableFuture`. Theo tài liệu `EventStream`, các action của stream được thực hiện trên **một luồng riêng**. Luồng đó có thể hoạt động đồng thời với `main` và các thread nghiệp vụ khác.

### Mô hình điều khiển

~~~text
Main thread                         Stream thread
-----------                         -------------
new RecordingStream()
enable(...)
onEvent(...)
onError(...)
startAsync() ---------------------> bắt đầu xử lý
startAsync trả về
main tiếp tục công việc             JFR flush batch
                                   callback onEvent(event)
...                                ...
close() --------------------------> stream bắt đầu đóng
main có thể tiếp tục                callback không chắc hoàn tất trước khi close trả về
~~~

Hai điều cần nhớ: **startAsync trả về không chứng minh event đã tới**, và **close trả về không chứng minh mọi callback đã hoàn tất**.

## 4. Trình tự sử dụng đúng

Một pattern thường gặp:

~~~java
try (RecordingStream stream = new RecordingStream()) {
    stream.enable("jdk.CPULoad")
          .withPeriod(Duration.ofSeconds(1));

    stream.onEvent("jdk.CPULoad", event -> {
        // Đọc trường cần thiết, xử lý ngắn gọn.
    });

    stream.onError(error -> {
        // Ghi nhận lỗi ở kênh chẩn đoán nội bộ.
    });

    stream.startAsync();

    doOtherWork();
}
~~~

Đây là **mảnh code minh họa**, cần import `Duration`/`RecordingStream` và định nghĩa `doOtherWork()`.

Thứ tự cần tuân thủ:

1. Tạo stream.
2. Bật event cần nghe bằng `enable("name")` hoặc `enable(MyEvent.class)`, thiết lập period/threshold phù hợp.
3. Đăng ký `onEvent`, `onError` và `onClose` (nếu cần).
4. Gọi `startAsync()` **một lần**.
5. Giữ stream sống trong khoảng thời gian giám sát; không thoát khỏi `try` ngay lập tức nếu cần thực sự nhận event.
6. Nếu cần kết quả callback, dùng **tín hiệu rõ ràng** như `CountDownLatch`.
7. Đóng stream bằng `try-with-resources` hoặc `close()` khi kết thúc.

## 5. Ví dụ 1 — Main tiếp tục khi dùng `startAsync()`

Tạo tệp **`AsyncLifecycleDemo.java`**:

~~~java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

public class AsyncLifecycleDemo {
    public static void main(String[] args) {
        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                  .withPeriod(Duration.ofSeconds(1));
            stream.onEvent("jdk.CPULoad", event -> { });

            stream.startAsync();
            System.out.println("startAsync returned");
            System.out.println("main continues");
        }
        System.out.println("stream closed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AsyncLifecycleDemo.java
java AsyncLifecycleDemo
~~~

**Stdout chính xác trong JVM có thể khởi tạo JFR:**

~~~text
startAsync returned
main continues
stream closed
~~~

Callback cố ý không in gì để kết quả không phụ thuộc event thực tế. Hai dòng đầu chứng minh `startAsync()` đã trả quyền điều khiển về cho `main`. `try-with-resources` gọi `close()` trước dòng cuối, nhưng **không có cam kết callback hoàn tất chỉ vì close trả về**.

Một mảnh code có thể không nhận event:

~~~java
try (RecordingStream stream = new RecordingStream()) {
    stream.startAsync();
} // Đóng stream ngay, chưa đăng ký callback và chưa duy trì thời gian quan sát.
~~~

Không nên lấy tình huống này để kết luận `startAsync()` không hoạt động.

## 6. Ví dụ 2 — Theo dõi CPU có giới hạn thời gian

Tạo tệp **`AsyncCpuDemo.java`**:

~~~java
import java.time.Duration;
import jdk.jfr.consumer.RecordingStream;

public class AsyncCpuDemo {
    public static void main(String[] args) throws InterruptedException {
        try (RecordingStream stream = new RecordingStream()) {
            stream.enable("jdk.CPULoad")
                  .withPeriod(Duration.ofSeconds(1));

            stream.onEvent("jdk.CPULoad", event -> {
                float load = event.getFloat("jvmUser");
                if (load >= 0.0f) {
                    System.out.println("CPU sample observed");
                }
            });

            stream.onError(error ->
                    System.err.println("JFR callback error"));

            stream.startAsync();
            System.out.println("main working");
            Thread.sleep(4_000);
        }
        System.out.println("monitor closed");
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AsyncCpuDemo.java
java AsyncCpuDemo
~~~

Hai dòng **do luồng main in khi chạy bình thường**:

~~~text
main working
monitor closed
~~~

Có thể có thêm các dòng `CPU sample observed` với số lần và thời điểm **không xác định**; vì vậy block trên **không phải toàn bộ stdout** bắt buộc. `withPeriod(Duration.ofSeconds(1))` yêu cầu chu kỳ event, không bảo đảm callback gọi đúng mỗi giây. `Thread.sleep(4_000)` tạo khoảng quan sát, **không chứng minh đã có event**.

Không hardcode tải CPU, số GC hoặc số event làm golden output: chúng phụ thuộc workload, JVM, OS, cấu hình và lịch flush.

## 7. JFR giao event theo batch: đừng nhầm thời điểm

Một chuỗi diễn biến hợp lệ:

~~~text
T0  gọi startAsync()
T1  startAsync trả về cho main
T2  event được JVM commit
T3  JFR flush một batch
T4  stream đọc và giải mã batch
T5  callback onEvent(...) được gọi
~~~

Không có lời hứa T1 = T5. Cơ chế streaming **không giao callback đồng bộ ngay tại `Event.commit()`**.

| Cách chờ | Thực sự chờ | Đã nhận event cụ thể? |
| --- | --- | --- |
| `Thread.sleep(100)` | Một khoảng thời gian | **Chưa chắc** |
| `stream.awaitTermination(Duration.ofSeconds(5))` | Stream kết thúc/đóng, timeout hoặc interrupt | **Không chứng minh** |
| `CountDownLatch.await(20, TimeUnit.SECONDS)`, callback đúng event gọi `countDown()` | Tín hiệu callback hoặc timeout | **Có nếu trả `true`** |
| `BlockingQueue.poll(timeout)`, callback đưa payload vào queue | Payload đến hoặc timeout | **Có nếu lấy được dữ liệu** |

`awaitTermination(Duration)` trả về `void`. Nó **không phải API đợi một event đến** và có thể trả về chỉ vì hết timeout.

## 8. Ví dụ 3 — Chờ custom event bằng `CountDownLatch`

Tạo tệp **`AsyncCustomEventDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.Label;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class AsyncCustomEventDemo {
    @Name("lesson.TaskDone")
    @Label("Task done")
    static class TaskDone extends Event {
        @Label("Task")
        String task;
    }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch received = new CountDownLatch(1);
        AtomicReference<String> value = new AtomicReference<>();

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(TaskDone.class).withoutThreshold();

            stream.onEvent("lesson.TaskDone", event -> {
                value.set(event.getString("task"));
                received.countDown();
            });

            stream.onError(error ->
                    System.err.println("JFR callback failed"));

            stream.startAsync();

            TaskDone emitted = new TaskDone();
            emitted.task = "build";
            emitted.commit();

            if (!received.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "No matching event before timeout");
            }

            System.out.println("received: " + value.get());
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AsyncCustomEventDemo.java
java AsyncCustomEventDemo
~~~

**Stdout chính xác nếu event tới trước timeout:**

~~~text
received: build
~~~

Nếu event không tới trước deadline, chương trình **ném ngoại lệ báo timeout**, không im lặng coi là thành công.

- `@Name("lesson.TaskDone")` đặt tên event cố định.
- `enable(TaskDone.class).withoutThreshold()` bật event mà không yêu cầu duration tối thiểu.
- `onEvent` lọc theo tên, đọc `RecordedEvent.getString("task")`, cập nhật giá trị và báo `countDown()`.
- `main` tạo và `commit()` event sau `startAsync()`.
- `CountDownLatch` đồng bộ thông tin qua hai luồng; hành động trước `countDown` *happens-before* những thao tác sau `await` thành công.

Thực hành này đáng tin hơn `Thread.sleep(200)` vì kiểm tra **đúng callback đã chạy**, không chỉ thời gian trôi qua.

## 9. Chia sẻ dữ liệu giữa callback và luồng main

Do callback chạy ở thread khác, phép đọc/ghi shared state cần visibility và synchronization.

Mảnh code **sai** vì biến local capture phải *effectively final*:

~~~java
int count = 0;
stream.onEvent("jdk.CPULoad", event -> count++);
~~~

Cách viết phù hợp hơn:

~~~java
AtomicInteger count = new AtomicInteger();
stream.onEvent("jdk.CPULoad", event -> count.incrementAndGet());
~~~

Cần import `AtomicInteger` và đã có biến `stream`. Có thể dùng `AtomicReference` cho giá trị mới nhất, `BlockingQueue` có giới hạn cho nhiều sự kiện, hoặc `CountDownLatch` khi chỉ cần một tín hiệu.

### Ví dụ 4 — Callback trên thread khác

Tạo tệp **`AsyncCallbackThreadDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class AsyncCallbackThreadDemo {
    @Name("lesson.ThreadCheck")
    static class ThreadCheck extends Event { }

    public static void main(String[] args) throws InterruptedException {
        Thread mainThread = Thread.currentThread();
        AtomicReference<Thread> callbackThread = new AtomicReference<>();
        CountDownLatch done = new CountDownLatch(1);

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(ThreadCheck.class).withoutThreshold();
            stream.onEvent("lesson.ThreadCheck", event -> {
                callbackThread.set(Thread.currentThread());
                done.countDown();
            });

            stream.startAsync();
            new ThreadCheck().commit();

            if (!done.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Event not delivered");
            }

            System.out.println(callbackThread.get() != mainThread);
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AsyncCallbackThreadDemo.java
java AsyncCallbackThreadDemo
~~~

**Stdout chính xác khi event đến trước timeout:**

~~~text
true
~~~

Đừng so tên thread như `"JFR Event Stream"` vì tên có thể đổi theo JVM/version. Điều cần khẳng định là callback đã chạy trên **luồng khác main**.

## 10. `onError` khi callback ném exception

Exception từ callback bất đồng bộ **không tự động ném lại tại chỗ `startAsync()` vốn đã trả về trong `main`**. `EventStream` có `onError(Consumer<Throwable>)`:

~~~java
stream.onError(error ->
        System.err.println("JFR processing error"));
~~~

Đây là mảnh code. Nếu không đăng ký, exception action có thể được in cùng stack trace ra `stderr`. Khi đăng ký `onError`, ứng dụng xử lý riêng. **Không để chính error handler ném exception**; tài liệu nói hành vi đó không xác định.

### Ví dụ 5 — Nhận tín hiệu từ error handler

Tạo tệp **`AsyncErrorHandlingDemo.java`**:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class AsyncErrorHandlingDemo {
    @Name("lesson.Fault")
    static class Fault extends Event { }

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch errorSeen = new CountDownLatch(1);

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(Fault.class).withoutThreshold();

            stream.onEvent("lesson.Fault", event -> {
                throw new IllegalStateException("simulated failure");
            });

            stream.onError(error -> errorSeen.countDown());

            stream.startAsync();
            new Fault().commit();

            if (!errorSeen.await(20, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Error callback not observed");
            }

            System.out.println("error callback observed");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AsyncErrorHandlingDemo.java
java AsyncErrorHandlingDemo
~~~

**Stdout chính xác khi event/error callback được giao trước timeout:**

~~~text
error callback observed
~~~

Đây là demo **cố ý ném lỗi giả** để minh họa `onError`. Trong ứng dụng thật, giữ callback ngắn gọn, không blocking lâu hoặc ghi raw event không qua kiểm soát.

## 11. `close()`, `awaitTermination()` và `stop()`

### `close()`

`RecordingStream` implements `AutoCloseable`; `try-with-resources` phù hợp cho cleanup. Tuy nhiên `EventStream.close()` nói rõ stream có thể dừng ngay hoặc sau flush tiếp theo và **không bảo đảm tất cả action đã hoàn thành trước khi trả về**.

Do đó, không coi `close()` là `Thread.join()`; nếu cần kết quả callback, hãy chờ tín hiệu của callback theo nhu cầu trước khi dùng kết quả.

### `awaitTermination(Duration)`

~~~java
stream.startAsync();
stream.awaitTermination(Duration.ofSeconds(5));
~~~

Đây là mảnh code cần xử lý `InterruptedException`. Có thể trả về do stream hoàn tất/đóng, timeout hoặc interrupt. **Không báo event X đã tới**, không trả số lượng event và không tự đóng stream chỉ vì timeout.

### `stop()`

`RecordingStream.stop()` có **từ Java 20**. Trên phiên bản hỗ trợ, nó dừng recording đã chạy và chờ tiêu thụ event còn lại. Không sử dụng trong file biên dịch với `--release 17`. Tài liệu cảnh báo **gọi `stop()` từ callback của chính stream có thể chặn vô hạn**; nếu cần nó ở Java 21/25, gọi từ luồng quản lý phù hợp.

## 12. Ví dụ 6 — Gọi `startAsync()` sai trạng thái

Tạo tệp **`AsyncStartStateDemo.java`**:

~~~java
import jdk.jfr.consumer.RecordingStream;

public class AsyncStartStateDemo {
    public static void main(String[] args) {
        try (RecordingStream stream = new RecordingStream()) {
            stream.startAsync();

            try {
                stream.startAsync();
            } catch (IllegalStateException expected) {
                System.out.println("already started");
            }
        }

        RecordingStream closed = new RecordingStream();
        closed.close();

        try {
            closed.startAsync();
        } catch (IllegalStateException expected) {
            System.out.println("already closed");
        }
    }
}
~~~

Chạy:

~~~bash
javac --release 17 AsyncStartStateDemo.java
java AsyncStartStateDemo
~~~

**Stdout chính xác trong JVM hỗ trợ JFR:**

~~~text
already started
already closed
~~~

`startAsync()` gọi lại trên instance đã started/closed ném `IllegalStateException`. Khi cần một recording mới, tạo **instance mới**, không restart một stream đã close.

## 13. `RecordedEvent` có thể tái sử dụng

Theo `EventStream`, **cùng object `RecordedEvent` có thể được giao cho nhiều callback** dưới dạng các event khác nhau. Vì vậy giữ chính object đó sau callback có thể nguy hiểm.

Mảnh code không nên dùng nếu mặc định giữ reference lâu:

~~~java
List<RecordedEvent> saved = new ArrayList<>();
stream.onEvent("jdk.CPULoad", saved::add);
~~~

**Hướng đúng:** đọc và sao chép trường thực sự cần ngay trong callback (ví dụ `event.getFloat("jvmUser")`) rồi gửi số/DTO riêng qua queue. Nếu thật sự phải giữ đối tượng `RecordedEvent`, đặt **`stream.setReuse(false)` trước start** và chấp nhận chi phí bộ nhớ/cấp phát.

## 14. Batch, overhead và bảo mật

`EventStream` giao event theo **batch**. `onFlush(Runnable)` báo sau khi một batch được flush:

~~~java
stream.onFlush(() -> {
    // Tổng hợp metric batch, xử lý nhẹ.
});
~~~

Theo tài liệu, các event trong batch được sắp theo thời điểm kết thúc, nhưng ordering tổng thể **giữa các batch không được bảo đảm**. Nếu không cần order, có thể chọn `setOrdered(false)`.

Để giảm overhead:

- Chỉ `enable` những event phục vụ mục đích giám sát.
- Chọn `withPeriod`/`withThreshold` phù hợp, không mặc định bật mọi event và in tất cả.
- Chọn `setMaxAge(Duration)` và `setMaxSize(long)` theo nhu cầu giữ dữ liệu.
- Giữ callback ngắn, tránh HTTP/file I/O blocking; có thể đẩy payload tối thiểu sang **bounded queue**.
- Không coi JFR là message queue nghiệp vụ với bảo đảm exactly-once.
- Không log raw event khi chưa phân loại: JFR event có thể chứa path, host, thread name, stack trace, metadata nhạy cảm.
- Dùng `onError`, cleanup theo lifecycle và chính sách hủy tác vụ/interrupt rõ ràng.

Mảnh cấu hình:

~~~java
stream.setMaxAge(Duration.ofMinutes(5));
stream.setMaxSize(16L * 1024 * 1024);
stream.enable("jdk.CPULoad")
      .withPeriod(Duration.ofSeconds(1));
~~~

Đây là **giá trị minh họa**, không phải ngưỡng tối ưu cho mọi production JVM.

## 15. Các lỗi thường gặp

| Sai lầm | Cách sửa |
| --- | --- |
| `startAsync()` rồi thoát `try` ngay | Giữ stream sống; close quá sớm có thể mất cơ hội nhận event. |
| Dùng `start()` nhưng muốn `main` không bị chặn | Dùng `startAsync()`. |
| Gọi `startAsync()` hai lần | Quản lý trạng thái; chỉ start một lần mỗi instance. |
| Gọi start sau close | Tạo instance mới. |
| `Thread.sleep(100)` rồi assert event đã tới | Dùng `CountDownLatch`/queue với timeout. |
| Dùng `awaitTermination` như chờ event | Nó chờ trạng thái stream, không chờ callback X. |
| Coi `close()` đã chờ hết callbacks | API không bảo đảm; dùng tín hiệu hoàn tất riêng. |
| Dùng biến mutable không đồng bộ giữa callback và main | Dùng atomic, queue, latch hoặc lock. |
| Giữ `RecordedEvent` mà không hiểu reuse | Sao chép dữ liệu hoặc `setReuse(false)`. |
| Không xử lý error callback | Đăng ký `onError` ngắn gọn, không tự throw. |
| Gọi `stop()` trong callback | Có thể deadlock; gọi từ luồng quản lý trên Java 20+. |
| Dùng `stop()` ở target Java 17 | API chưa có; dùng close/signal. |
| So đúng CPU load, số event, tên thread | Những giá trị đó không ổn định theo môi trường. |
| In toàn bộ JFR event | Có thể tốn tài nguyên và lộ dữ liệu; chỉ ghi trường được phép. |

## 16. Thực hành và QA

Chạy mỗi ví dụ độc lập:

~~~bash
javac --release 17 AsyncLifecycleDemo.java
java AsyncLifecycleDemo

javac --release 17 AsyncCpuDemo.java
java AsyncCpuDemo

javac --release 17 AsyncCustomEventDemo.java
java AsyncCustomEventDemo

javac --release 17 AsyncCallbackThreadDemo.java
java AsyncCallbackThreadDemo

javac --release 17 AsyncErrorHandlingDemo.java
java AsyncErrorHandlingDemo

javac --release 17 AsyncStartStateDemo.java
java AsyncStartStateDemo
~~~

Các ví dụ custom event có timeout: nếu event đến, stdout đúng phần đã ghi; nếu không, chương trình **thất bại rõ ràng** thay vì báo PASS. Với CPU sample, không so toàn bộ stdout vì callback bất định.

### Bài tập

1. Viết `RecordingStream` lắng nghe `jdk.CPULoad`, bắt đầu async, giữ stream trong khoảng giám sát và đóng bằng `try-with-resources`. Giải thích tại sao `startAsync()` không chờ CPU sample.
2. Thay `Thread.sleep` bằng `CountDownLatch` cho một custom event `lesson.Done`, chờ có timeout rồi kiểm tra payload.
3. Cho callback cập nhật `AtomicReference`, main đọc sau latch. Giải thích vấn đề memory visibility nếu không đồng bộ.
4. Gọi `startAsync()` hai lần và bắt `IllegalStateException`. Gọi sau `close()` và kiểm tra kết quả tương tự.
5. Trình bày vì sao `awaitTermination(Duration)` không thể chứng minh event đã tới.
6. So sánh `close()` và `stop()` (Java 20+), nhấn mạnh không gọi stop trong callback.
7. Thiết kế giám sát không làm lộ PII: lọc event, chụp trường tối thiểu, bounded queue, quyền truy cập/retention.

**Bạn đạt yêu cầu** khi hiểu: `startAsync()` chỉ **khởi động xử lý bất đồng bộ trên một luồng riêng**, không bảo đảm event đến hoặc callback hoàn thành. Luôn cấu hình trước, đồng bộ đúng sự kiện, quản lý shutdown và giới hạn tác vụ callback.

## 17. Nguồn chính thức còn áp dụng

- [Oracle Java SE 25 — RecordingStream API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): `startAsync`, lifecycle, `enable`, `stop`, `awaitTermination`.
- [Oracle Java SE 25 — EventStream API](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): callback, batch, `onError`, `onClose`, `setReuse` và giới hạn của `close`.
- [OpenJDK JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): mục tiêu tính năng và phiên bản Java 14.
- [Oracle Java SE 25 — Event](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): custom event và `commit()`.
- [Oracle Java SE 25 — RecordedEvent](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): lấy dữ liệu event nhận được.
- [Oracle Java SE 25 — CountDownLatch](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/CountDownLatch.html): đồng bộ callback và happens-before.
- [Oracle Java SE 25 — AtomicReference](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/atomic/AtomicReference.html): chia sẻ dữ liệu an toàn giữa các luồng.

**Ghi nhớ:** `RecordingStream.startAsync()` khởi chạy xử lý JFR **trên một luồng khác rồi trả quyền điều khiển cho luồng gọi**. Để dùng đúng, hãy bật event và đăng ký callback trước khi start, giữ stream sống, dùng tín hiệu callback khi cần chờ dữ liệu, xử lý thread-safety và đóng tài nguyên có chủ đích.