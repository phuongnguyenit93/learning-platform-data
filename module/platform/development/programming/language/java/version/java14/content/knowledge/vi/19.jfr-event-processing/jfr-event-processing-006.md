# Chụp dữ liệu cần thiết trước khi chuyển sang luồng xử lý khác trong JFR

## 1. Mục tiêu: xử lý bất đồng bộ nhưng không đánh mất ý nghĩa của sự kiện

Khi dùng **Java Flight Recorder (JFR)**, ứng dụng có thể nhận sự kiện qua `jdk.jfr.consumer.EventStream` hoặc `RecordingStream` bằng callback `onEvent(...)`. Callback nên xử lý nhanh để không làm chậm luồng tiêu thụ các đợt sự kiện. Một cách phổ biến là chuyển dữ liệu cần xử lý nặng (ghi database, tính metric, phân tích, gom báo cáo) sang một **executor/worker thread** khác.

Nhưng có một bẫy: **không nên đưa trực tiếp tham chiếu `RecordedEvent` từ callback vào hàng đợi để đọc sau**. Theo hợp đồng `EventStream` trong các JDK hiện đại, **mặc định cùng một đối tượng `RecordedEvent` có thể được tái sử dụng cho nhiều sự kiện**. Sau khi callback hoàn tất, đối tượng đó có thể được dùng để biểu diễn sự kiện khác. Vì vậy một lambda chạy chậm ở worker có nguy cơ nhìn thấy giá trị không còn thuộc về sự kiện ban đầu.

Giải pháp ưu tiên là **chụp (snapshot) những trường thực sự cần ngay bên trong callback** thành một đối tượng dữ liệu độc lập, đủ bất biến, rồi **chỉ chuyển snapshot** sang worker.

Bài này thuộc nhóm **Xử lý sự kiện JFR**. Những quy tắc về `EventStream` và `RecordedEvent` bắt đầu từ Java 14 và vẫn còn áp dụng. Ví dụ thực hành dùng **Java 17+**, bao gồm `record` đã ổn định từ Java 16, không dùng API preview hay kiến thức legacy.

**Đích đến sau bài học:**

- Giải thích được vì sao giữ tham chiếu `RecordedEvent` sau callback có thể sai.
- Biết lấy trường sự kiện bằng `getInt`, `getString`, `getEndTime`, `getEventType()` ngay khi callback đang xử lý.
- Thiết kế một snapshot có các trường rõ nghĩa và bất biến, tránh giữ cả graph đối tượng không cần thiết.
- Chuyển snapshot an toàn tới executor/queue, xử lý giới hạn hàng đợi và lỗi công việc.
- Phân biệt phương án snapshot với `stream.setReuse(false)` cùng chi phí của mỗi cách.
- Dùng chương trình Java 17+ có kết quả xác định để kiểm chứng việc xử lý trên thread khác.

## 2. Cơ chế gây lỗi: RecordedEvent có thể được tái sử dụng

### 2.1. Callback hoạt động ra sao?

Ví dụ một stream nhận sự kiện custom:

~~~java
stream.onEvent("demo.Task", event -> {
    System.out.println(event.getInt("id"));
});
~~~

Đây là **đoạn minh họa**, giả định `stream` là `EventStream` đã mở và loại `demo.Task` có trường `id` kiểu `int`. Callback nhận một `RecordedEvent` đại diện cho sự kiện đang được stream gửi đến.

Trong thời gian callback chạy, bạn có thể đọc các trường của `event`. Khi callback kết thúc, **không được giả định rằng cùng đối tượng đó vẫn luôn đại diện cho sự kiện cũ** nếu stream giữ chế độ reuse mặc định.

Javadoc `EventStream` nói rõ:

- Theo mặc định một đối tượng `RecordedEvent` **có thể** đại diện cho nhiều sự kiện khác nhau.
- Đối tượng ấy có thể được chuyển tới cùng một handler nhiều lần, hoặc nhiều handler khác nhau.
- Khi `setReuse(true)`, handler **không nên giữ tham chiếu tới event sau khi callback kết thúc**.
- Nếu thật sự cần giữ đối tượng event qua thời gian callback, có thể cấu hình `setReuse(false)` để một đối tượng `RecordedEvent` mới được cấp phát cho mỗi event.

Từ **“có thể”** rất quan trọng. Một bài thử ngắn đôi khi không thấy lỗi chỉ vì runtime chưa tái sử dụng object theo cách dễ quan sát. Đây không phải bằng chứng mã giữ tham chiếu an toàn.

### 2.2. Đoạn code nguy hiểm

~~~java
// Ví dụ CỐ Ý SAI về vòng đời dữ liệu.
stream.onEvent("demo.Task", event -> {
    executor.execute(() -> {
        int id = event.getInt("id");
        saveTask(id);
    });
});
~~~

Đây là đoạn minh họa với `executor` và `saveTask(int)` do ứng dụng cung cấp. Nó có thể **biên dịch hợp lệ**, nhưng sai ở thiết kế: lambda của worker **giữ tham chiếu `event`**, không giữ giá trị `id` đã chụp. Worker chạy lúc nào không xác định; đến khi worker gọi `getInt("id")`, callback có thể đã trả về và stream có thể dùng lại đối tượng `RecordedEvent`.

Điều kiện “lambda là biểu thức hợp lệ của Java” hoặc “biến `event` là effectively final” **không có nghĩa nội dung object được capture cũng bất biến**. Trong Java, lambda ở trên chỉ giữ **tham chiếu** tới đối tượng event.

### 2.3. Dòng thời gian dễ nhớ

~~~text
Thread đọc JFR            Worker thread
       |                        |
       | callback event A       |
       | event.id = 10          |
       |-------- queue(event) ->| (chưa chạy)
       | callback A kết thúc    |
       |                        |
       | stream có thể reuse    |
       | cùng RecordedEvent      |
       | cho event B (id=20)    |
       |                        | worker đọc event.id
       |                        | có thể thấy 20 thay vì 10
       v                        v
  Dữ liệu sai do truyền tham chiếu có vòng đời ngắn
~~~

Đây là sơ đồ **nguy cơ theo hợp đồng API**, không phải cam kết JVM luôn luôn tái sử dụng đúng lúc này.

## 3. Mẫu chuẩn: đọc dữ liệu trước, chuyển snapshot sau

Thay vì chuyển cả đối tượng JFR, hãy trích trường cần dùng **ngay trong callback**:

~~~java
stream.onEvent("demo.Task", event -> {
    int id = event.getInt("id");
    String state = event.getString("state");
    java.time.Instant occurredAt = event.getEndTime();

    TaskSnapshot snapshot =
            new TaskSnapshot(id, state, occurredAt);

    executor.execute(() -> process(snapshot));
});
~~~

Đây là **đoạn code minh họa**, với `TaskSnapshot`, `executor`, `process` cần được định nghĩa trong ứng dụng. Ba giá trị được lấy ra khi `event` còn đang ở trong callback; worker chỉ giữ tham chiếu đến `snapshot`.

Nếu Java 17+, một kiểu snapshot phù hợp:

~~~java
record TaskSnapshot(
        int id,
        String state,
        java.time.Instant occurredAt
) {}
~~~

Với các trường trên:

- `int` là primitive: giá trị được sao chép, không giữ tham chiếu đến vùng dữ liệu event.
- `String` là đối tượng bất biến theo hợp đồng Java. Sau khi trích `getString`, giá trị chuỗi có thể được giữ trong snapshot.
- `Instant` cũng là kiểu bất biến, biểu diễn timestamp đã đọc từ event.
- `record` giúp khai báo dữ liệu với các component fields `private final` và accessor rõ ràng. Không cần tự viết setters.
- Việc xuất bản snapshot sang worker qua `ExecutorService.execute(...)` sử dụng cơ chế chuyển giao thread-safe của executor; hành động trước khi submit xảy ra trước lúc công việc tương ứng được thực thi theo hợp đồng memory consistency của `Executor`.

**Quy tắc vàng:** **Mọi phép đọc `RecordedEvent` cần thiết cho tác vụ bất đồng bộ phải diễn ra trước khi callback trả về; worker không cần và không nhận tham chiếu `RecordedEvent`.**

### Không phải mọi snapshot đều tự động bất biến sâu

Một `record` chỉ bảo đảm các trường thành phần không thể được gán lại sau khi khởi tạo; nó **không tự động deep-copy** những đối tượng mutable. Nếu muốn giữ một danh sách:

~~~java
record TraceSnapshot(java.util.List<String> frames) {
    TraceSnapshot {
        frames = java.util.List.copyOf(frames);
    }
}
~~~

Đây là một record độc lập dùng được trong Java 17. `List.copyOf` tạo danh sách không thể sửa đổi qua API `List`, nhưng chỉ sao chép **tham chiếu phần tử**, không tự deep-copy từng phần tử mutable. Với phần tử `String` bất biến, ví dụ phù hợp. Nếu nguồn là một mảng `byte[]`, cần cân nhắc `clone()`/`Arrays.copyOf(...)` ở **cả phía nhận và trả** nếu API công bố mảng có thể thay đổi.

## 4. Chụp chính xác những trường nào?

Đừng giải mã toàn bộ JFR event chỉ vì có thể. Chọn dữ liệu theo **mục tiêu xử lý ở downstream**.

| Nhu cầu downstream | Dữ liệu nên chụp trong callback | Lưu ý |
|---|---|---|
| Tính số sự kiện | Tên event, loại kết quả hoặc một counter | Không nhất thiết cần stack trace |
| Ghép theo tác vụ | Request/task ID từ custom event | ID phải được ứng dụng phát sinh rõ nghĩa |
| Phân tích độ trễ | `getStartTime()`, `getEndTime()` hoặc `getDuration()` | Dùng `Instant`/`Duration` bất biến; không lấy thời điểm worker chạy làm thời điểm event |
| Theo dõi loại sự kiện | `getEventType().getName()` | Trả chuỗi tên loại event; kiểm tra schema khi xử lý nhiều event types |
| Metric lỗi | Trường code/trạng thái từ event như `getString("status")` | Chỉ đọc trường có trong metadata của loại event đó |
| Chẩn đoán thread | Chỉ các thuộc tính thread thực sự cần, trích ngay trong callback | Đừng giữ nguyên object `RecordedThread` theo quán tính |
| Chẩn đoán stack | Các string/tên phương thức hoặc giá trị dẫn xuất cần thiết | Stack có thể không được ghi; hạn chế dung lượng và thông tin nhạy cảm |

Một snapshot đơn giản thường gồm:

~~~java
record EventSummary(
        String eventType,
        java.time.Instant endTime,
        String status,
        int requestId
) {}
~~~

Kiểu trên chỉ là **schema minh họa**; `status` và `requestId` là custom fields, không có trên mọi JFR event hệ thống. Nếu xử lý hỗn hợp `jdk.CPULoad`, `jdk.GarbageCollection` và custom events, đừng gọi cùng một field name cho mọi loại mà không xem `event.hasField(...)`, event metadata hoặc kiểm tra schema tương ứng.

### Các giá trị tham chiếu phức tạp

`RecordedEvent` có thể cung cấp `getThread()`, `getStackTrace()`, `getEventType()` hoặc các giá trị lồng nhau. Để tạo snapshot **không phụ thuộc vòng đời stream**, nên chuyển chúng thành **giá trị đơn giản đã chọn lọc**: string, số, `Instant`, `Duration`, và collection copy phòng vệ của những giá trị bất biến đó.

Tránh đặt trực tiếp `RecordedEvent`, `RecordedObject`, `RecordedThread`, `RecordedStackTrace` hay cả một cấu trúc metadata nặng vào snapshot **nếu worker chỉ cần vài trường**. `setReuse(false)` có thể thay đổi cách cấp phát event object, nhưng không giải quyết bài toán bộ nhớ, quyền riêng tư hay lựa chọn trường không cần thiết.

## 5. Sai và đúng khi dùng lambda hoặc queue

### Sai: chụp tham chiếu, không chụp giá trị

~~~java
stream.onEvent("demo.Task", event -> {
    queue.offer(event);
});
~~~

Dạng này giữ object `RecordedEvent` sau callback. Nếu stream còn ở chế độ reuse, consumer nhận sau có thể đọc nội dung thuộc sự kiện khác. Đây là lỗi **semantic lifetime**, không chỉ là vấn đề `queue` có thread-safe hay không. Một `BlockingQueue<RecordedEvent>` không tự sửa lỗi dữ liệu.

### Đúng: chụp giá trị rồi gửi

~~~java
stream.onEvent("demo.Task", event -> {
    int id = event.getInt("id");
    String state = event.getString("state");
    java.time.Instant endedAt = event.getEndTime();

    TaskSnapshot snapshot =
            new TaskSnapshot(id, state, endedAt);

    if (!queue.offer(snapshot)) {
        rejected.incrementAndGet();
    }
});
~~~

Đây là **mảnh code minh họa**: `queue` là một `BlockingQueue<TaskSnapshot>` **có giới hạn kích thước**, còn `rejected` là `AtomicInteger` được định nghĩa bởi ứng dụng. `offer` trả ngay nếu queue đầy, không mặc định chặn callback. Phải quyết định chính sách khi `false`: tăng metric lỗi, sampling, ghi bản tóm tắt hoặc phát cảnh báo với giới hạn tần suất; không âm thầm bỏ sự kiện quan trọng.

### Đúng: dùng executor

~~~java
stream.onEvent("demo.Task", event -> {
    TaskSnapshot snapshot = new TaskSnapshot(
            event.getInt("id"),
            event.getString("state"),
            event.getEndTime()
    );

    try {
        worker.execute(() -> process(snapshot));
    } catch (java.util.concurrent.RejectedExecutionException ex) {
        onRejected(snapshot);
    }
});
~~~

Đây là đoạn minh họa: `worker`, `process` và `onRejected` do ứng dụng định nghĩa. `worker.execute(...)` sẽ chuyển quyền thực hiện công việc theo cơ chế của executor, nhưng không đảm bảo tác vụ được nhận trong mọi tình huống. Với executor có hàng đợi hữu hạn và `AbortPolicy`, quá tải có thể sinh `RejectedExecutionException`; chương trình cần xử lý.

**Quan trọng:** không đưa công việc nặng vào `onRejected(...)` của callback nếu như vậy lại khiến luồng đọc JFR bị chặn; lựa chọn chính sách phụ thuộc mức độ cần thiết của dữ liệu và ngân sách tài nguyên.

## 6. Chương trình Java 17+ đầy đủ: snapshot rồi giao việc sang worker

Ví dụ dưới đây cố ý dùng **`EventStream.openFile(...)` trên file JFR vừa tạo**, thay vì phụ thuộc vào thời gian flush khi mở repository live. Điều này giúp đầu ra **ổn định và dễ tái lập** khi học quy tắc snapshot. Chính ngữ nghĩa `EventStream.onEvent` và reuse được áp dụng giống nhau khi dùng `openRepository()` hoặc `RecordingStream`.

Chương trình:

1. Tạo một recording trên JVM và bật custom event `demo.SnapshotEvent`.
2. Phát sinh ba event với ID `1, 2, 3`, dừng recording và dump vào file tạm `.jfr`.
3. Mở file bằng `EventStream.openFile`.
4. Trong từng callback, chụp `id`, `phase` và `endTime` thành **record `Snapshot`**.
5. Gửi **snapshot** đến một executor có queue hữu hạn, để worker thread xử lý.
6. Đợi executor hoàn tất; kiểm tra số callback, số snapshot đã nhận, rejection count và xử lý khác thread.
7. Xóa file/thư mục tạm sau khi chạy.

Tạo file **`JfrSnapshotHandoffDemo.java`**:

~~~java
import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.EventStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;

public class JfrSnapshotHandoffDemo {
    @Name("demo.SnapshotEvent")
    static final class SnapshotEvent extends Event {
        int id;
        String phase;
    }

    record Snapshot(int id, String phase, Instant endedAt) {}

    public static void main(String[] args) throws Exception {
        Path directory = Files.createTempDirectory("jfr-handoff-");
        Path capture = directory.resolve("capture.jfr");

        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(SnapshotEvent.class)
                        .withThreshold(Duration.ZERO)
                        .withoutStackTrace();
                recording.start();

                for (int i = 1; i <= 3; i++) {
                    SnapshotEvent event = new SnapshotEvent();
                    event.id = i;
                    event.phase = "done-" + i;
                    event.commit();
                }

                recording.stop();
                recording.dump(capture);
            }

            var processed =
                    new ConcurrentSkipListMap<Integer, Snapshot>();
            AtomicInteger callbacks = new AtomicInteger();
            AtomicInteger rejected = new AtomicInteger();
            AtomicBoolean differentThread = new AtomicBoolean();

            ThreadPoolExecutor worker = new ThreadPoolExecutor(
                    1, 1, 0L, TimeUnit.MILLISECONDS,
                    new ArrayBlockingQueue<>(16),
                    new ThreadPoolExecutor.AbortPolicy()
            );

            try {
                try (EventStream stream = EventStream.openFile(capture)) {
                    stream.onEvent("demo.SnapshotEvent", event -> {
                        Snapshot snapshot = new Snapshot(
                                event.getInt("id"),
                                event.getString("phase"),
                                event.getEndTime()
                        );
                        Thread callbackThread = Thread.currentThread();
                        callbacks.incrementAndGet();

                        try {
                            worker.execute(() -> {
                                differentThread.set(
                                        Thread.currentThread() != callbackThread
                                );
                                processed.put(snapshot.id(), snapshot);
                            });
                        } catch (RejectedExecutionException ex) {
                            rejected.incrementAndGet();
                        }
                    });
                    stream.start();
                }
            } finally {
                worker.shutdown();
                if (!worker.awaitTermination(10, TimeUnit.SECONDS)) {
                    worker.shutdownNow();
                    throw new IllegalStateException("worker did not terminate");
                }
            }

            System.out.println("callbacks=" + callbacks.get());
            System.out.println("processed=" + processed.size());
            System.out.println("rejected=" + rejected.get());
            System.out.println("differentThread=" + differentThread.get());
            for (Snapshot snapshot : processed.values()) {
                System.out.println(
                        snapshot.id() + "=" + snapshot.phase()
                        + ", timePresent=" + (snapshot.endedAt() != null)
                );
            }
        } finally {
            Files.deleteIfExists(capture);
            Files.deleteIfExists(directory);
        }
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên; JVM phải có module JFR:

~~~bash
javac --release 17 JfrSnapshotHandoffDemo.java
java JfrSnapshotHandoffDemo
~~~

**Standard output đã kiểm chứng bằng biên dịch/chạy thực tế:**

~~~text
callbacks=3
processed=3
rejected=0
differentThread=true
1=done-1, timePresent=true
2=done-2, timePresent=true
3=done-3, timePresent=true
~~~

### Vì sao từng kết quả xuất hiện?

- **`callbacks=3`:** ba `SnapshotEvent` đã được ghi, dump, đọc và callback lọc theo đúng tên `demo.SnapshotEvent`.
- **`processed=3`:** executor đã xử lý cả ba snapshot được chuyển giao.
- **`rejected=0`:** queue hữu hạn 16 phần tử không bị quá tải trong ví dụ chỉ có ba event.
- **`differentThread=true`:** lambda chạy trong executor khác thread của callback. Điều này được kiểm tra bằng **đối tượng `Thread`**, không đoán dựa vào tên thread vốn phụ thuộc hệ thống.
- **`1/2/3=done-*`:** thông tin đã chụp trong callback được giữ đúng đến khi worker xử lý. `ConcurrentSkipListMap` hiển thị theo ID tăng dần, tránh dựa vào thứ tự callback như một bằng chứng về thứ tự toàn JVM.
- **`timePresent=true`:** `getEndTime()` trả một `Instant` cho event; chương trình không in timestamp cố định vì timestamp phụ thuộc thời điểm chạy.

Ví dụ dùng một **single-thread worker** và `ConcurrentSkipListMap` để có kết quả dễ hiểu. Nếu có nhiều worker, thứ tự hoàn tất công việc có thể khác thứ tự event nhận được; nếu nghiệp vụ cần thứ tự, phải thiết kế cơ chế tuần tự hóa hoặc sắp xếp phù hợp.

**Giới hạn:** đầu ra mẫu giả định JFR khả dụng, ghi file tạm thành công và máy không gặp sự cố I/O/timeout. Nếu quyền ghi bị từ chối, JFR bị vô hiệu hoặc worker không kết thúc trong timeout, chương trình sẽ báo lỗi thay vì in đủ các dòng này. Phần minh họa không khẳng định mọi môi trường có cùng thời gian chạy hay kích thước file.

## 7. Vì sao phải đóng stream trước khi chờ worker hoàn tất?

Trong ví dụ, `stream.start()` đọc hết file và hoàn tất việc gọi các callback. Sau khi đọc, stream được đóng; executor đã nhận những snapshot cần xử lý và có thể được `shutdown()`, `awaitTermination(...)`.

Cần phân biệt ba cột mốc:

| Cột mốc | Nghĩa | Chưa bảo đảm điều gì? |
|---|---|---|
| Callback `onEvent` trả về | Snapshot đã được tạo và **đã thử gửi** tới queue/executor | Worker đã xử lý xong |
| EventStream kết thúc hoặc đóng | Reader không tiếp tục gửi event mới | Mọi tác vụ trong executor đã hoàn tất |
| Executor `awaitTermination(...)` thành công sau `shutdown()` | Các task đã được worker xử lý đến khi executor kết thúc | Tác vụ đã thành công về nghiệp vụ nếu task tự bắt lỗi/ghi dữ liệu không đúng |

`EventStream.close()` **không bảo đảm** mọi callback hoặc công việc downstream đã hoàn thành trước khi trả về; điều này được Java API nêu rõ. Vì vậy, đừng dùng “stream đã close” như một dấu hiệu duy nhất để gửi thông báo “đã xử lý xong tất cả sự kiện”.

### Nếu dùng startAsync() trên live stream

Với `startAsync()`, callback chạy ở thread riêng. Luồng chính phải chủ động quản lý vòng đời: khi nào ngừng nhận event, khi nào đóng stream, khi nào ngừng nhận thêm task và khi nào chờ worker hoàn tất. Trong dịch vụ thật, có thể cần một **handoff coordinator** để ngăn submit sau khi executor đã `shutdown()`; chỉ bắt `RejectedExecutionException` và đếm số từ chối chưa đủ nếu mọi event đều quan trọng.

Khi dùng `start()` trên file như ví dụ, trình tự đơn giản hơn: các callback đọc file chạy trong thread gọi, và sau khi stream kết thúc, không còn callback mới nào gửi task.

## 8. setReuse(false) có thể dùng khi nào?

`EventStream.setReuse(boolean)` cho phép đổi việc reuse event object:

~~~java
try (EventStream stream = EventStream.openFile(file)) {
    stream.setReuse(false);
    stream.onEvent("demo.Task", event -> {
        queue.offer(event);
    });
    stream.start();
}
~~~

Đây là **đoạn minh họa**, với `file` và `queue` cần được định nghĩa, không phải chương trình độc lập. Khi `setReuse(false)`, một `RecordedEvent` mới được cấp phát cho mỗi event. Vì vậy, theo hợp đồng JFR, có thể giữ tham chiếu event sau callback mà **không gặp lỗi do chính stream reuse object event**.

Tuy nhiên, việc chọn cách này có các đánh đổi:

- Tạo thêm object trên đường xử lý, tăng cấp phát và áp lực GC khi lưu lượng sự kiện lớn.
- Giữ cả metadata/graph liên quan trong khi worker có thể chỉ cần vài số và chuỗi.
- Có thể giữ dữ liệu nhạy cảm lâu hơn trong bộ nhớ hoặc gửi qua queue một cách không cần thiết.
- Không tự cấp quyền truy cập an toàn cho các đối tượng mutable tùy ý khác do ứng dụng gắn vào xử lý.
- **Không giải quyết** vấn đề queue đầy, worker chậm, exception trong task hay shutdown không đúng thứ tự.
- Cần cấu hình **trước khi bắt đầu stream** để hành vi rõ ràng và có thể kiểm thử.

**Khuyến nghị thiết kế:** ưu tiên **chụp snapshot trường cần thiết trong callback**. Chỉ xem xét `setReuse(false)` khi thực sự cần giữ nguyên `RecordedEvent` để xử lý sâu ở nơi khác và đã đánh giá chi phí cấp phát, bộ nhớ và chính sách dữ liệu.

### Câu hỏi: setReuse(false) có giống snapshot không?

**Không.** `setReuse(false)` thay đổi hợp đồng **cấp phát đối tượng event** ở reader. Snapshot là việc ứng dụng **chọn lọc, trích xuất, chuẩn hóa và công bố dữ liệu** cho công việc khác. Snapshot có thể giảm dữ liệu giữ lại, đổi kiểu thành DTO bất biến và kiểm soát quyền riêng tư tốt hơn.

## 9. Giữ snapshot an toàn khi có tham chiếu và collection

### 9.1. Primitive, String, Instant và Duration

Các kiểu `int`, `long`, `boolean` là giá trị sao chép. `String`, `Instant` và `Duration` bất biến nên rất phù hợp để đưa vào snapshot.

~~~java
record MetricSnapshot(
        String eventType,
        java.time.Instant startedAt,
        java.time.Duration duration,
        long count
) {}
~~~

Đây là kiểu độc lập. Nếu đọc từ một sự kiện hợp lệ:

~~~java
MetricSnapshot snapshot = new MetricSnapshot(
        event.getEventType().getName(),
        event.getStartTime(),
        event.getDuration(),
        event.getLong("count")
);
~~~

Đoạn này **minh họa** trong callback của một event có trường `count` kiểu `long`; không phải tất cả event đều có trường đó. Đừng tự suy rằng `getLong("count")` sẽ thành công với event khác.

### 9.2. Mảng và đối tượng mutable

Nếu dữ liệu trung gian là `byte[]`, copy-in/copy-out cần được xem xét. Ví dụ:

~~~java
import java.util.Arrays;

record PayloadSnapshot(byte[] bytes) {
    PayloadSnapshot {
        bytes = Arrays.copyOf(bytes, bytes.length);
    }

    @Override
    public byte[] bytes() {
        return Arrays.copyOf(bytes, bytes.length);
    }
}
~~~

Đây là một **record độc lập**. Hai copy tạo hàng rào phòng vệ trước thay đổi bên ngoài. Lưu ý: array có `equals` theo tham chiếu, nên record với component array không tự có **value equality theo nội dung**; nếu cần so sánh snapshot theo giá trị, phải thiết kế `equals/hashCode` hoặc một wrapper phù hợp. Mục đích ở đây là minh họa **độc lập dữ liệu khi qua thread**, không phải tạo kiểu value object hoàn chỉnh cho mảng.

### 9.3. Collection và deep copy

Với `List<String>`, `List.copyOf` thường đủ để có danh sách không thể sửa đổi và các phần tử bất biến. Với `List<MutableFrame>`, nó chỉ tạo bản sao **nông**; nếu phần tử còn mutable, snapshot vẫn có thể đổi ý nghĩa. Hãy chuyển mỗi phần tử thành DTO bất biến trước khi `List.copyOf`.

### 9.4. Không giữ đối tượng dùng lại từ buffer/pool

Quy tắc không chỉ dành cho JFR: buffer từ pool, iterator view hoặc object được tái sử dụng thường có vòng đời ngắn. Nếu worker cần dữ liệu sau callback, hãy trích hoặc sao chép theo đúng hợp đồng nguồn. Với `ByteBuffer`, `duplicate()` hay `slice()` có thể vẫn chia sẻ vùng dữ liệu nền, nên chúng **không tương đương** sao chép byte độc lập.

## 10. Hàng đợi hữu hạn và chiến lược quá tải

Snapshot đã đúng nhưng pipeline vẫn có thể hỏng nếu tạo vô hạn công việc khi số event/giây vượt khả năng xử lý.

**Nguyên tắc:**

1. Chọn queue **có giới hạn rõ ràng**, dựa trên tốc độ event, kích thước trung bình của snapshot, lượng RAM và độ trễ cho phép.
2. Đo số snapshot đã nhận, đã xử lý, bị từ chối, backlog và thời gian nằm trong queue.
3. Xác định chính sách khi quá tải, tránh `DiscardPolicy` âm thầm bỏ dữ liệu nếu việc bỏ sự kiện ảnh hưởng tính chính xác.
4. `AbortPolicy` giúp phát hiện đầy queue bằng `RejectedExecutionException`. Trong code mẫu, callback tăng `rejected`.
5. `CallerRunsPolicy` có thể khiến tác vụ được chạy **ngay trên thread đọc JFR**, làm chậm callback và khiến stream bị tụt hậu; không chọn nó một cách vô thức.
6. `BlockingQueue.put(...)` có thể chặn vô hạn khi queue đầy. Trong callback JFR, điều này có nguy cơ khiến đường đọc event bị treo khi downstream dừng hoặc gặp sự cố.
7. Nếu cho phép sampling/drop có chủ đích, ghi số đã bỏ và mô tả chính sách; nếu không được phép mất dữ liệu, cần thiết kế cơ chế lưu bền vững, retry hoặc backpressure có giám sát rõ ràng.

Một nguyên tắc đánh giá dung lượng: nếu queue giữ `N` snapshot, mỗi snapshot chiếm trung bình `B` byte cả dữ liệu tham chiếu và overhead, ngân sách tối thiểu của phần payload xấp xỉ `N × B`, chưa kể overhead của queue, worker và vật thể được tham chiếu. Không đặt queue capacity theo cảm tính rồi coi đó là giới hạn tổng RAM.

### Tại sao bài demo dùng ConcurrentSkipListMap?

Việc đọc event từ JFR và thực thi task không đồng nghĩa thứ tự hoàn tất của các task luôn giống thứ tự phát sinh. Trong chương trình học, `ConcurrentSkipListMap` lưu theo ID để in kết quả ổn định. Với production, chọn cấu trúc theo yêu cầu thật: `ConcurrentHashMap` khi chỉ cần tra cứu, queue có thứ tự khi cần xử lý lần lượt, hoặc một hệ thống phân vùng theo khóa nếu cần duy trì thứ tự cho từng request.

**Không suy ra quan hệ nhân quả chỉ từ thứ tự callback.** JFR có thể giao event theo batch; thời điểm phát sinh, kết thúc và hoàn tất xử lý downstream là các khái niệm riêng.

## 11. Chụp timestamp nào? Khi worker chạy thì event đã xảy ra

Một sự kiện JFR có `getStartTime()`, `getEndTime()` và `getDuration()`:

- `getStartTime()`: thời điểm bắt đầu sự kiện.
- `getEndTime()`: thời điểm kết thúc sự kiện.
- `getDuration()`: độ dài sự kiện; với event tức thời có thể bằng zero.
- `Instant.now()` trong worker: **thời điểm worker đang xử lý**, không tự trở thành thời điểm event phát sinh.

Đừng ghi lại timestamp bằng `Instant.now()` ở worker rồi gọi đó là `eventTime`: queue có thể làm trễ vài giây hoặc lâu hơn, khiến các biểu đồ thời gian bị lệch. Snapshot nên lưu timestamp JFR trước khi bàn giao; nếu cần đo độ trễ pipeline, lưu **thêm** thời điểm enqueue và processedAt với tên phân biệt.

Ví dụ schema:

~~~java
record TimedSnapshot(
        String kind,
        java.time.Instant eventEndedAt,
        java.time.Instant enqueuedAt,
        int id
) {}
~~~

Trong callback, có thể lấy `event.getEndTime()` và `Instant.now()` khi enqueue, sau đó worker lấy thời điểm xử lý để đo **latency của pipeline**. Đây là thông tin khác với **duration của sự kiện trong JVM**.

## 12. Callback lỗi và thread safety

### 12.1. Đọc field không tồn tại

Không gọi `event.getInt("id")` trên loại event không có field `id`. API có `event.hasField("id")`, nhưng đối với event được lọc theo tên, cách tốt là biết trước schema của event.

~~~java
stream.onEvent(event -> {
    if (event.getEventType().getName().equals("demo.Task")
            && event.hasField("id")) {
        long id = event.getLong("id");
        // Chụp snapshot với kiểu trường tương ứng.
    }
});
~~~

Đây là đoạn **minh họa** cho custom event có trường `id` kiểu `long`. Việc có field không bảo đảm giá trị thuộc đúng kiểu bạn đang mong đợi; người xử lý cần thống nhất schema ở nguồn.

### 12.2. onError và ngoại lệ trong callback

~~~java
stream.onError(error -> {
    System.err.println("JFR callback error: "
            + error.getClass().getSimpleName());
});
~~~

Dạng này cần được đăng ký trước khi stream bắt đầu. Nếu không có handler, EventStream có thể in stack trace xuống `stderr`. Tuy nhiên, **callback exception không giống task exception**: khi đã chuyển sang executor, exception xảy ra ở worker có thể không được chuyển về `EventStream.onError`. Bạn phải theo dõi lỗi và kết quả task riêng ở downstream.

Nếu dùng `execute(...)`, exception chưa xử lý trong worker có thể được báo bởi cơ chế xử lý uncaught exception của thread; nếu dùng `submit(...)`, exception thường được lưu trong `Future` và cần `get()`/giám sát rõ ràng. Đừng coi “executor không ném lỗi ở chỗ submit” là bằng chứng công việc đã thành công.

### 12.3. Thread-safe handoff

Một biến thường như:

~~~java
int processedCount = 0;
~~~

không nên được nhiều thread cùng tăng bằng `processedCount++` mà không có đồng bộ phù hợp. Trong bài demo, `AtomicInteger` theo dõi callback và rejection; `AtomicBoolean` lưu kết quả kiểm tra thread; `ConcurrentSkipListMap` nhận kết quả từ worker.

`record` với các component phù hợp giúp dữ liệu snapshot ổn định, nhưng khi có **nhiều worker** cùng cập nhật một collection chứa snapshot, bản thân collection vẫn phải có cơ chế đồng bộ/thread-safe hoặc được truy cập theo mô hình sở hữu rõ ràng.

### 12.4. Callback phải đủ nhẹ

Tác vụ callback nên ưu tiên:

- Kiểm tra tên/schema event khi cần.
- Trích xuất ít trường thực sự cần.
- Tạo snapshot ngắn, không có object graph khổng lồ.
- Gửi snapshot vào queue/executor với quy tắc từ chối rõ ràng.
- Trả về nhanh để reader có thể tiếp tục.

Không thực hiện database transaction dài, HTTP blocking, thao tác file dung lượng lớn hoặc log quá nhiều trong một callback nhận hàng nghìn event/giây khi chưa đánh giá ảnh hưởng.

## 13. Live stream và file stream: snapshot giống nhau, timing khác nhau

Có các lựa chọn thường dùng:

| API | Nguồn dữ liệu | Cách khởi chạy | Lưu ý cho snapshot |
|---|---|---|---|
| `EventStream.openFile(Path)` | File `.jfr` đã dump | `start()` hoặc `startAsync()` | Callback vẫn có thể nhận đối tượng `RecordedEvent` được reuse |
| `EventStream.openRepository()` | Repository JVM hiện tại | `start()` hoặc `startAsync()` | Mặc định đọc từ event được flush tiếp theo; phải có recording phù hợp |
| `EventStream.openRepository(Path)` | Disk repository được chỉ định | `start()` hoặc `startAsync()` | Chỉ mở repository đáng tin cậy |
| `RecordingStream` | Recording do stream quản lý | `enable(...)`, `onEvent(...)`, `start...` | Có thể vừa bật event vừa tiêu thụ, vẫn cần snapshot khi giao việc sang worker |

**Không nên chỉ lấy tên class `RecordedEvent` rồi tin rằng đối tượng là bản ghi vĩnh viễn**. Với `EventStream`, hợp đồng reuse vẫn áp dụng dù dữ liệu xuất phát từ file hay repository.

### Đoạn chuyển đổi sang RecordingStream

~~~java
try (jdk.jfr.consumer.RecordingStream stream =
        new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.CPULoad");
    stream.onEvent("jdk.CPULoad", event -> {
        double machineTotal = event.getFloat("machineTotal");
        executor.execute(() -> consumeMachineLoad(machineTotal));
    });
    stream.startAsync();
    // Duy trì vòng đời ứng dụng và đóng stream ở thời điểm phù hợp.
}
~~~

Đây là **đoạn minh họa**, với `executor` và `consumeMachineLoad(double)` do ứng dụng cung cấp. Nó thể hiện việc chụp primitive `double` **trước khi gửi**. Không đặt một `try` kết thúc ngay sau `startAsync()` trong ứng dụng thật vì như vậy stream có thể đóng trước khi có event mới.

## 14. Các lỗi phổ biến khi chuyển xử lý JFR sang thread khác

| Sai lầm | Triệu chứng hoặc rủi ro | Cách sửa |
|---|---|---|
| `executor.execute(() -> event.getInt("id"))` | Worker đọc event sau callback; object có thể bị reuse | Đọc `id` trước, chỉ capture giá trị |
| Cho `RecordedEvent` trực tiếp vào `BlockingQueue` | Queue thread-safe nhưng payload có vòng đời không an toàn | Dùng snapshot bất biến, hoặc cân nhắc `setReuse(false)` đúng điều kiện |
| Cho rằng `setReuse(false)` làm mọi xử lý bất đồng bộ tự an toàn | Vẫn có queue đầy, memory pressure, task failures | Thiết kế handoff, shutdown và error handling |
| Snapshot chứa `List<MutableItem>` nhưng chỉ `List.copyOf` | Phần tử bên trong có thể đổi | Chuyển từng phần tử thành value bất biến |
| Chuyển `byte[]` gốc mà không copy | Worker hoặc producer có thể thay đổi cùng mảng | `Arrays.copyOf`, copy-in/out khi cần |
| Lưu lại cả stack trace/metadata dù không cần | Tăng memory, overhead, nguy cơ lộ thông tin | Chỉ trích trường thiết yếu |
| Dùng `Instant.now()` ở worker làm event timestamp | Sai lệch khi queue có độ trễ | Chụp `getEndTime()` trong callback |
| Executor dùng queue không giới hạn | Tích lũy task, nguy cơ out-of-memory | Hàng đợi hữu hạn, giám sát backlog |
| Đặt `BlockingQueue.put` blocking vô thời hạn trong callback | Reader bị nghẽn, khó shutdown | Có timeout/chính sách quá tải có giám sát |
| Dùng `CallerRunsPolicy` mà không xét hậu quả | Worker task chạy ngay trên callback thread | Đánh giá backpressure và số event |
| Bỏ qua `RejectedExecutionException` | Mất sự kiện âm thầm | Đếm lỗi, cảnh báo, áp dụng chính sách rõ |
| Coi `EventStream.close()` là “worker xong” | Báo cáo sớm, dữ liệu downstream chưa ghi | `shutdown` và `awaitTermination`/Future theo yêu cầu |
| Mọi event đều `getString("status")` | Lỗi nếu field không tồn tại/khác kiểu | Lọc event name/schema và dùng getter phù hợp |
| Callback in log mọi event | Lãng phí tài nguyên, có thể chậm stream | Sampling, batch, metric thay vì log per-event |
| Bắt exception ở `onError` nhưng bỏ qua lỗi task executor | Không nhìn thấy lỗi downstream | Theo dõi `Future`, worker handler, completion metrics |

## 15. Checklist thiết kế trong production

1. **Đầu vào:** sự kiện đến từ `openFile`, `openRepository` hay `RecordingStream`? Có bật đúng event type không?
2. **Schema:** đã biết rõ tên, kiểu, khả năng null của từng field muốn chụp chưa?
3. **Snapshot:** các field được đọc từ `RecordedEvent` ngay trong callback và không giữ tham chiếu event sau callback?
4. **Bất biến:** primitive, `String`, `Instant` và collection copy phòng vệ đã phù hợp chưa?
5. **Dữ liệu nhạy cảm:** snapshot có mang thông tin không cần thiết hoặc bí mật không?
6. **Thread safety:** queue/executor an toàn khi chuyển task; collection và counter dùng chung được đồng bộ chưa?
7. **Ordering:** nghiệp vụ có cần xử lý theo thời gian event hoặc theo khóa hay chỉ cần tổng hợp?
8. **Overload:** queue có giới hạn và chính sách reject/drop/retry rõ ràng chưa?
9. **Lỗi:** lỗi trong callback, lúc submit và trong worker có được quan sát riêng không?
10. **Shutdown:** luồng JFR có được đóng, producer ngừng submit và executor được chờ hoàn tất hợp lý không?
11. **Kiểm thử:** đã có test cho nhiều sự kiện liên tiếp, worker chậm, queue đầy, field thiếu, event null và tắt stream chưa?
12. **Đo lường:** đã có số callback/processed/rejected cùng độ trễ pipeline chưa?

## 16. Tự kiểm tra kiến thức

**Câu 1.** Vì sao `stream.onEvent("demo.Task", event -> executor.execute(() -> save(event.getInt("id"))))` có thể sai dù queue của executor thread-safe?

**Đáp án:** Lambda giữ tham chiếu `RecordedEvent` và đọc `id` về sau. EventStream có thể reuse đối tượng khi callback kết thúc; queue thread-safe không thay đổi vòng đời payload. Phải đọc `id` trong callback thành biến `int`/snapshot trước khi enqueue.

**Câu 2.** Nếu dùng `setReuse(false)`, có bắt buộc phải dùng snapshot nữa không?

**Đáp án:** Không bắt buộc chỉ để tránh **reuse của đối tượng event**. Tuy nhiên snapshot vẫn thường tốt hơn vì giảm dữ liệu giữ lại, giảm phụ thuộc API JFR, có thể phòng vệ dữ liệu mutable và tạo hợp đồng DTO rõ nghĩa. Vẫn phải xử lý queue, lỗi và shutdown.

**Câu 3.** Có thể lấy `event.getEndTime()` ở worker để đảm bảo timestamp đúng không?

**Đáp án:** Không nên nếu worker giữ `RecordedEvent` với reuse mặc định. Hãy lấy `Instant endedAt = event.getEndTime()` trong callback rồi truyền `endedAt`.

**Câu 4.** Một `record Snapshot(List<MutableData> items)` có tự động an toàn khi gửi sang thread khác không?

**Đáp án:** Không. Trường `final` chỉ ngăn gán lại tham chiếu; danh sách/phần tử có thể mutable. Cần copy, chuyển thành kiểu bất biến hoặc xác lập ownership/đồng bộ phù hợp.

**Câu 5.** Tại sao ví dụ dùng `ThreadPoolExecutor` với `ArrayBlockingQueue<>(16)` thay vì queue không giới hạn?

**Đáp án:** Để chặn việc tồn đọng vô hạn khi producer sinh event nhanh hơn consumer. Khi quá tải, `AbortPolicy` từ chối tác vụ; callback đếm `rejected` để phát hiện thay vì âm thầm bỏ.

**Câu 6.** `callbacks=3` và `processed=2` trong một pipeline có thể có ý nghĩa gì?

**Đáp án:** Ba callback đã diễn ra, nhưng chỉ có hai snapshot được xử lý đến thời điểm đo. Có thể có task bị reject, task chưa hoàn tất, lỗi worker hoặc shutdown quá sớm. Phải xem thêm `rejected`, backlog, task failures và trạng thái termination.

**Câu 7.** Đóng EventStream có bảo đảm mọi task gửi sang executor hoàn tất không?

**Đáp án:** Không. Vòng đời stream và vòng đời downstream là hai thành phần khác nhau. Cần quản lý `shutdown()`, `awaitTermination(...)`/`Future` hoặc cơ chế tương đương riêng.

**Câu 8.** Vì sao không nên in `RecordedStackTrace` nguyên vẹn trong mọi callback?

**Đáp án:** Có thể tăng chi phí xử lý, lưu dữ liệu không cần thiết và làm lộ class/method names hay thông tin runtime. Chỉ lấy dữ liệu stack thực sự cần, theo chính sách bảo mật và ngân sách hiệu năng.

**Câu 9.** Cùng ba snapshot có thể được xử lý trên ba thread khác nhau; thứ tự hoàn thành có nhất thiết là 1–2–3 không?

**Đáp án:** Không. Nếu dùng nhiều worker, thời gian thực thi khác nhau làm thứ tự hoàn tất khác nhau. Dùng thứ tự/khóa/timestamp rõ ràng nếu nghiệp vụ yêu cầu.

**Câu 10.** Java record có phải lúc nào cũng immutable sâu không?

**Đáp án:** Không. Record component fields là `final` nhưng kiểu tham chiếu bên trong có thể mutable. Cần chọn kiểu giá trị bất biến hoặc copy phòng vệ theo mức độ bảo đảm mong muốn.

## 17. Tài liệu tham khảo hiện hành

- [Oracle Java SE 17 — EventStream](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): hợp đồng tái sử dụng `RecordedEvent`, `setReuse(boolean)`, `onEvent`, `onError`, `startAsync` và `close`.
- [Oracle Java SE 17 — RecordedEvent](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getEventType`, `getStartTime`, `getEndTime`, `getDuration` và trường sự kiện.
- [Oracle Java SE 17 — RecordedObject](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedObject.html): `getInt`, `getString`, `getLong`, `hasField` và các getter khác.
- [Oracle Java SE 17 — Recording](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/Recording.html): bật custom event, ghi và dump recording để đọc thử.
- [Oracle Java SE 17 — Executor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/Executor.html): hợp đồng chuyển công việc giữa thread và memory consistency.
- [Oracle Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html): queue hữu hạn, `AbortPolicy` và handling công việc bị từ chối.
- [Oracle Java SE 17 — java.lang.Record](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html): record component fields và giới hạn của shallow immutability.

**Tổng kết:** Đối với **Xử lý sự kiện JFR**, hãy **đọc đúng những trường cần dùng từ `RecordedEvent` trong callback, đưa chúng vào một snapshot đủ bất biến rồi mới gửi sang executor/queue**. Không capture trực tiếp event object ở lambda chạy sau callback khi stream có reuse mặc định. `setReuse(false)` là lựa chọn thay thế có chi phí, không thay thế thiết kế snapshot, hàng đợi hữu hạn, quản lý lỗi và shutdown đúng.