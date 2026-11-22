# Thời điểm dữ liệu được flush và độ trễ quan sát trong JFR EventStream

> **Phạm vi:** Bài Knowledge thuộc **Java 14 → EventStream**. API `jdk.jfr.consumer.EventStream` và `RecordingStream` xuất hiện trong JDK 14 (JEP 349) và tiếp tục được hỗ trợ trong các JDK hiện hành. Bài sử dụng **Java 17+** với API chính thức; không dùng preview, cơ chế legacy hoặc một giao thức streaming tự chế. Trọng tâm là phân biệt **thời điểm phát sinh event**, **thời điểm JVM flush dữ liệu** và **thời điểm callback nhận event**.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích các giai đoạn từ `Event.commit()` đến `EventStream.onEvent(...)`, tại sao hai thời điểm không trùng nhau.
2. Hiểu **batch/flush** trong JFR, ý nghĩa chính xác của callback `onFlush(Runnable)` và giới hạn thứ tự sự kiện.
3. Biết `EventStream.openRepository()` mặc định bắt đầu đọc từ **sự kiện được flush tiếp theo**, chứ không tự phát lại toàn bộ lịch sử.
4. Phân biệt `start()` và `startAsync()`, callback đến trễ do flush hay do thread/CPU/logic callback.
5. Đo **độ trễ quan sát (observation latency)** một cách có ý thức bằng `System.nanoTime()` hoặc timestamp của `RecordedEvent`, tránh khẳng định SLA mà API không cam kết.
6. Tách **không có event vì chưa được ghi** khỏi **event đã commit nhưng chưa được stream chuyển đến**, hoặc **consumer đã bỏ lỡ cửa sổ lưu trữ**.
7. Hiểu ảnh hưởng của `enable`, `threshold`, event `period`, retention `maxAge/maxSize`, backlog và xử lý callback nặng.
8. Sử dụng ví dụ Java 17+ chạy được để đo độ trễ thực tế, nghe `onFlush` và so sánh với đường **Recording → stop/dump → đọc file**.
9. Chọn chiến lược test và giám sát phù hợp với đặc tính **gần thời gian thực nhưng không phải hard real-time** của JFR.

**Thông điệp quan trọng:** `commit()` chỉ là thao tác của producer; callback `onEvent` chạy khi dữ liệu phù hợp đã được **JFR ghi, flush, đọc và phân phối**. **Không có quan hệ 1 commit = 1 callback ngay lập tức.**

## 2. Ba thời điểm thường bị nhầm lẫn

Giả sử ứng dụng phát sinh một custom event:

```java
ProbeEvent event = new ProbeEvent();
event.sequence = 42;
event.commit();
```

Đây là đoạn minh họa, giả định `ProbeEvent extends jdk.jfr.Event` đã được khai báo. Trong một recording đã enable sự kiện này, ta có ba thời điểm khác nhau:

- **`t_commit`:** producer gọi `commit()`, JFR kiểm tra điều kiện ghi và thu thập event.
- **`t_flush`:** JFR đưa dữ liệu khả dụng qua cơ chế flush/batch để consumer đọc được.
- **`t_callback`:** thread của EventStream xử lý và gọi `onEvent(...)` cho event tương ứng.

```text
Ứng dụng / producer         JFR runtime, buffers/repository       EventStream consumer
        |                                 |                             |
        | commit()                        |                             |
        +-------------------------------->| điều kiện enable/threshold  |
        |                                 | ghi/đệm dữ liệu event       |
        | tiếp tục xử lý                  |                             |
        |                                 | flush batch                |
        |                                 +---------------------------->|
        |                                 |                             | onEvent(...)
        |                                 |                             | xử lý callback
        |                                 |                             | onFlush(...) sau batch
        v                                 v                             v
      t_commit                          t_flush                       t_callback
```

Mô hình này **mang tính khái niệm**: JFR có thể xử lý sự kiện từ nhiều thread và batch/chunks; không bắt buộc có một lệnh flush tường minh cho từng event. Thứ tự `t_commit → t_flush → t_callback` diễn giải **đường đi dữ liệu** khi callback thực sự nhận được event.

Một event có thể **không đến callback** vì chưa enable, không vượt threshold, consumer chưa bắt đầu đúng lúc, dữ liệu đã bị xóa do retention, lỗi đọc, stream đóng sớm hoặc các nguyên nhân vận hành khác. Do đó bảng thời điểm chỉ áp dụng cho event **thực sự được ghi và nhận**.

### 2.1. Độ trễ quan sát bao gồm những gì?

Một phép đo đơn giản:

```text
observation latency ≈ t_callback - t_emit
                    = producer/commit overhead
                    + thời gian buffer/flush
                    + thời gian consumer nhận/đọc
                    + thời gian chờ scheduling/queue
```

Trong code thực tế, còn có chi phí đo thời gian. **Không coi tất cả chênh lệch thời gian là «flush latency»**, vì quan sát tại callback chỉ cho ta **độ trễ đầu-cuối (end-to-end)**. Không thể lấy một số đo `onEvent` để quy hoàn toàn cho JVM flush.

## 3. Sự kiện phải được ghi trước khi nói tới flush

Có sự khác biệt giữa **đã gọi `commit()`** và **đã có một event được ghi**:

| Điều kiện | Hệ quả |
| --- | --- |
| Event type chưa được recording bật | Có thể không có event để flush/stream. |
| Duration của event không đạt `threshold` | Có thể bị bỏ theo setting. |
| Producer tính payload rồi gọi `commit()` | Không có bảo đảm callback đã chạy. |
| Recording đã enable đúng type, event thỏa điều kiện | Event có thể được thu thập và sau đó xuất hiện trong batch khi flush. |
| Consumer chỉ gọi `onEvent` nhưng không có recording nào ghi | Đăng ký callback không tự sinh dữ liệu. |

Ví dụ producer với JFR:

```java
import jdk.jfr.Event;
import jdk.jfr.Name;

@Name("demo.FlushProbe")
class FlushProbe extends Event {
    public int sequence;
}
```

Trong phạm vi một phương thức:

```java
FlushProbe event = new FlushProbe();
event.sequence = 1;
event.commit();
```

Hai đoạn là **mã minh họa**, chưa phải một file có `main`. Khi tạo `RecordingStream`, cần cấu hình:

```java
stream.enable(FlushProbe.class).withoutThreshold();
```

`withoutThreshold()` loại bỏ ngưỡng thời lượng đối với loại event đó trong recording của stream. Nó **không yêu cầu JVM flush ngay** sau mỗi `commit()` và không đặt deadline cho callback. Tương tự, `withThreshold(...)` chỉ quyết định loại sự kiện nào đủ điều kiện ghi; nó không phải knob điều chỉnh khoảng thời gian batch.

### 3.1. `isEnabled()` và `shouldCommit()`

Với payload tốn kém, có thể viết:

```java
FlushProbe event = new FlushProbe();
if (event.shouldCommit()) {
    event.sequence = calculateSequence();
    event.commit();
}
```

`calculateSequence()` trong mẫu này là method giả định của ứng dụng. `shouldCommit()` giúp tránh phần việc đắt đỏ nếu event không cần ghi. Nó **không xác nhận** consumer đã nhận hoặc sẽ nhận sự kiện. Mọi kiểm chứng về observer phải nằm ở phía consumer/test, không dựa vào kết quả của producer method.

## 4. EventStream phân phối dữ liệu theo batch

Theo Javadoc chính thức của `jdk.jfr.consumer.EventStream`:

- **Events are delivered in batches**: các event được consumer nhận thành **đợt**.
- Callback `onEvent(String, Consumer<RecordedEvent>)` chạy cho những sự kiện phù hợp được phân phối.
- Callback `onFlush(Runnable)` được gọi **sau khi stream được flush**, tương ứng với ranh giới một đợt phân phối; đây là chỗ có thể tổng hợp dữ liệu trước khi chuẩn bị batch tiếp theo.
- Events **trong cùng một batch** được sắp theo thời điểm kết thúc event, nếu ordering mặc định được giữ.
- Tính **well-ordering** chỉ được bảo đảm với các events sẵn có tại thời điểm flush. Event của batch sau có thể có thời gian kết thúc **sớm hơn** event ở batch trước.
- Có thể `setOrdered(false)` nếu không cần sắp thứ tự trong batch để giảm chi phí sorting; **không** làm biến mất bước flush hoặc tạo SLA mới.

```text
JFR flush batch 1:
    event A (endTime 12:00:01.100)
    event B (endTime 12:00:01.200)
    └── onFlush(batch 1)

JFR flush batch 2:
    event C (endTime 12:00:01.150)
    event D (endTime 12:00:01.250)
    └── onFlush(batch 2)

Consumer có thể thấy: A, B, C, D
Trong batch: có sắp thứ tự.
Giữa batch: C có endTime sớm hơn B nhưng được giao sau B.
```

Sơ đồ là **dữ liệu ví dụ** minh họa giới hạn ordering, **không phải** stdout từ một lần chạy thật và không mô tả một chu kỳ flush cố định của JDK.

### 4.1. `onFlush` không phải «cưỡng bức flush»

`onFlush(() -> ...)` **đăng ký hành động được gọi sau flush**. Nó không yêu cầu JVM flush ngay tại vị trí gọi đăng ký; cũng không cung cấp API `stream.flush()` để bạn dùng làm lệnh «flush một event vừa commit».

Ví dụ:

```java
// Các câu lệnh minh họa bên trong một phương thức,
// giả định stream là EventStream / RecordingStream chưa start.
stream.onEvent("demo.FlushProbe", e -> {
    System.out.println("event=" + e.getInt("sequence"));
});

stream.onFlush(() -> {
    System.out.println("batch-end");
});
```

Số lần callback `onFlush` **không phải số lượng event**. Một batch có thể chứa nhiều events, và các lần flush có thể diễn ra trong điều kiện không giống nhau. Đừng dùng số lần `onFlush` làm công thức suy ra «có N event» hoặc «sau đúng một giây» nếu JDK không đưa ra cam kết đó.

### 4.2. Khi nào nên dùng `onFlush`?

Ranh giới batch hữu ích để **đẩy số liệu tổng hợp ra ngoài**:

```java
java.util.concurrent.atomic.AtomicInteger batchCount =
        new java.util.concurrent.atomic.AtomicInteger();

stream.onEvent("demo.FlushProbe", e -> {
    batchCount.incrementAndGet();
});

stream.onFlush(() -> {
    int events = batchCount.getAndSet(0);
    if (events > 0) {
        System.out.println("batch-events=" + events);
    }
});
```

Đây là đoạn **minh họa đặt trong phương thức**; `stream` phải tồn tại trước khi code đăng ký callback. Output biến thiên theo số event được flush. `AtomicInteger` làm ví dụ dễ mở rộng khi đọc state từ thread khác. Trong một EventStream bắt đầu bằng `startAsync()`, các registered actions được xử lý ở một thread riêng theo Javadoc.

**Không nhầm:** Callback này chỉ tổng hợp các event **đã được consumer phân phối**. Nó không xác nhận toàn bộ event producer đã commit đều có mặt trong batch. Để đối chiếu thất lạc, cần nguồn số lượng độc lập và chiến lược đối chiếu phù hợp.

## 5. `EventStream.openRepository()`: mặc định từ lần flush kế tiếp

Với:

```java
try (jdk.jfr.consumer.EventStream stream =
        jdk.jfr.consumer.EventStream.openRepository()) {
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println("cpu-event");
    });
    stream.start();
}
```

đây là **mẫu code minh họa** trong phương thức `throws Exception`. `openRepository()` dùng **disk repository của JVM hiện tại**. Theo Javadoc hiện hành, mặc định stream **bắt đầu từ event tiếp theo được Flight Recorder flush**, không đọc từ đầu mọi dữ liệu cũ của repository.

Ba hệ quả:

1. Nếu event đã xảy ra nhưng **được flush trước thời điểm bắt đầu stream mặc định**, consumer không tự động phát lại nó.
2. Nếu event đã commit nhưng **chưa được flush**, consumer có thể nhận nó sau khi bắt đầu, nếu dữ liệu phù hợp còn được giữ và đi qua batch mà stream đọc.
3. Nếu không có một recording nào đang ghi loại event bạn subscribe, gọi `onEvent` không đủ để tạo dữ liệu.

### 5.1. Muốn đọc một khoảng thời gian lịch sử

`EventStream` có `setStartTime(Instant)`, phải thiết lập **trước `start()` hoặc `startAsync()`**:

```java
import java.time.Instant;
import jdk.jfr.consumer.EventStream;

// Đoạn minh họa trong phương thức throws Exception:
try (EventStream stream = EventStream.openRepository()) {
    stream.setStartTime(Instant.now().minusSeconds(30));
    stream.onEvent("jdk.CPULoad", event -> {
        System.out.println(event.getEndTime());
    });
    stream.startAsync();

    // Công việc của ứng dụng diễn ra ở đây.
    Thread.sleep(2_000);
}
```

Đây **không phải phép bảo đảm sẽ nhận 30 giây dữ liệu quá khứ**. Khoảng lịch sử chỉ đọc được nếu recording trước đó đã ghi và **repository vẫn giữ** dữ liệu. Retention, kích thước chunks, quyền truy cập và lúc bật event đều có thể làm dữ liệu vắng mặt. Dòng `Thread.sleep` không đảm bảo callback đã chạy; nó chỉ minh họa vòng đời consumer hữu hạn.

### 5.2. So với `EventStream.openFile()`

| Cách mở stream | Nguồn | Mặc định bắt đầu ở đâu? | Đang live? |
| --- | --- | --- | --- |
| `EventStream.openRepository()` | Disk repository của JVM hiện tại | **Event được flush tiếp theo** | Có thể theo dõi liên tục nếu có nguồn dữ liệu mới |
| `EventStream.openRepository(Path)` | Repository theo đường dẫn | **Event được flush tiếp theo** | Có thể theo dõi liên tục nếu repository tiếp tục nhận dữ liệu |
| `EventStream.openFile(Path)` | File `.jfr` đã lưu | **Event đầu tiên trong file** | Không tự tạo live producer |
| `RecordingStream` | Recording do stream quản lý trong JVM hiện tại | Theo recording đang được stream bật | Ghi và tiêu thụ liên tục |

Chữ `Stream` trong `openFile` **không** có nghĩa callback được phát vào đúng thời điểm event lịch sử đã xảy ra. Event trong file có thể được phát lại rất nhanh hoặc nhanh/chậm tùy tốc độ đọc; khoảng cách **callback-time − event-time** lúc này là khoảng tuổi của dữ liệu lưu, không phải latency JFR live.

## 6. Đo độ trễ quan sát: nên đo những mốc nào?

Có ít nhất ba cách đo, với ngữ nghĩa khác nhau:

| Phép đo | Công thức gợi ý | Đo được gì? | Hạn chế |
| --- | --- | --- | --- |
| **Producer → callback trong cùng JVM** | `System.nanoTime()` ở callback trừ nanoTime ở producer | Độ trễ đầu-cuối, gồm commit/flush/dispatch/scheduling | Phải chuyển giá trị timestamp từ producer sang consumer; chỉ so được trong cùng một JVM với clock monotonic. |
| **Thời điểm event ghi trong JFR → callback** | `Duration.between(recorded.getEndTime(), Instant.now())` | Khoảng thời gian tường quan theo wall-clock từ event end đến lúc xử lý | Bị ảnh hưởng bởi thay đổi đồng hồ hệ thống, overhead, nguồn event, event duration. |
| **Từ lúc bắt đầu chờ → callback đầu tiên** | `System.nanoTime()` quanh `CountDownLatch.await()` | Thời gian chờ đến khi một callback bất kỳ xảy ra | Không trừ được producer start-up, chưa biết event nào được nhận hoặc liệu nó thuộc batch nào. |

**Định nghĩa đo rõ ràng trước khi báo số.** Nếu dùng `System.nanoTime()` ở producer ngay trước `commit()` và ở consumer khi nhận, kết quả bao gồm:

- Thời gian trong `commit()` và pipeline producer;
- Chờ dữ liệu khả dụng và flush;
- Đọc/parse/dispatch ở EventStream;
- Lịch CPU và tải callback;
- Phần overhead của chính việc đo.

Không nên đặt tên metric là `jfr_flush_latency_ms` rồi coi đó là «thời gian flush thuần», khi công thức thực sự là **end-to-end observation latency**.

### 6.1. Vì sao `System.nanoTime()` phù hợp trong cùng JVM?

`System.nanoTime()` trả thời gian monotonic tương đối, hữu ích khi trừ hai giá trị được lấy **trong cùng một JVM**. Nó không phải timestamp epoch và **không được so trực tiếp** với `Instant`/`RecordedEvent.getEndTime()` hoặc giá trị từ JVM khác.

Ví dụ:
```java
long emittedNanoTime = System.nanoTime();
// ... commit event ghi field emittedNanoTime ...
long observedNanoTime = System.nanoTime();
long elapsedNanos = observedNanoTime - emittedNanoTime;
```

Đây là ví dụ **mô tả phép đo**, không phải một chương trình độc lập. Trên máy đang tải nặng, chênh lệch có thể biến động lớn. Độ phân giải timer cũng có giới hạn; không khẳng định mọi event được callback sau chính xác một số mili-giây.

### 6.2. Dùng `RecordedEvent.getEndTime()`

`RecordedEvent` có `getStartTime()`, `getEndTime()` và `getDuration()`. Trong callback:

```java
stream.onEvent("demo.FlushProbe", e -> {
    java.time.Duration age = java.time.Duration.between(
            e.getEndTime(), java.time.Instant.now());
    System.out.println("age-ms=" + age.toMillis());
});
```

Đây là mẫu trong phương thức có biến `stream`. Kết quả phụ thuộc đồng hồ wall-clock và độ trễ đọc. Nếu event đo một khoảng dài, `getStartTime()` và `getEndTime()` mang ý nghĩa khác nhau; để phân tích «đã kết thúc bao lâu trước khi callback xử lý», dùng **end time** là hợp lý hơn.

**Không dùng timestamp wall-clock từ hai máy không đồng bộ** để suy ra độ trễ mạng/JFR với độ chính xác tuyệt đối. Với luồng từ xa, cần quản lý NTP/PTP, độ trễ transport và chiến lược đo ngoài JFR thích hợp.

## 7. Ví dụ hoàn chỉnh: đo latency thực tế của `RecordingStream`

Ví dụ này tạo custom event rồi đo **thời gian từ trước `commit()` đến callback `onEvent`**. Nó cũng đếm số lần stream gọi `onFlush` để cho thấy số event và số flush là hai đại lượng khác nhau.

Lưu file **`JfrFlushLatencyDemo.java`**:

```java
import java.time.Duration;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;

import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.consumer.RecordingStream;

public class JfrFlushLatencyDemo {
    @Name("demo.FlushLatency")
    public static class Probe extends Event {
        public int sequence;
        public long emittedNanoTime;
    }

    public static void main(String[] args) throws Exception {
        CountDownLatch firstEvent = new CountDownLatch(1);
        AtomicInteger received = new AtomicInteger();
        AtomicInteger flushCallbacks = new AtomicInteger();
        AtomicLong firstLatencyNs = new AtomicLong(-1);

        try (RecordingStream stream = new RecordingStream()) {
            stream.enable(Probe.class).withoutThreshold();
            stream.setMaxAge(Duration.ofMinutes(2));
            stream.setMaxSize(16L * 1024 * 1024);

            stream.onEvent("demo.FlushLatency", recorded -> {
                int seq = recorded.getInt("sequence");
                long started = recorded.getLong("emittedNanoTime");
                long latencyNs = System.nanoTime() - started;

                if (seq > 0) {
                    firstLatencyNs.compareAndSet(-1, latencyNs);
                    received.incrementAndGet();
                    firstEvent.countDown();
                }
            });

            stream.onFlush(() -> {
                flushCallbacks.incrementAndGet();
            });

            stream.onError(Throwable::printStackTrace);
            stream.startAsync();

            // Phát nhiều events trong cửa sổ chờ hữu hạn.
            // Không giả định commit sẽ tạo callback ngay lập tức.
            for (int i = 1; i <= 60 && firstEvent.getCount() > 0; i++) {
                Probe probe = new Probe();
                probe.sequence = i;
                probe.emittedNanoTime = System.nanoTime();
                probe.commit();
                firstEvent.await(100, TimeUnit.MILLISECONDS);
            }

            boolean seen = firstEvent.getCount() == 0;
            System.out.println("event-observed=" + seen);
            if (seen) {
                System.out.println("first-latency-ms="
                        + TimeUnit.NANOSECONDS.toMillis(
                                firstLatencyNs.get()));
            }
            System.out.println("received-so-far=" + received.get());
            System.out.println("flush-callbacks-so-far="
                    + flushCallbacks.get());
        }
    }
}
```

Biên dịch bằng JDK **17 trở lên** có hỗ trợ target 17 và module `jdk.jfr`:

```bash
javac --release 17 JfrFlushLatencyDemo.java
java JfrFlushLatencyDemo
```

**Ví dụ một lần chạy có event được nhận:** (các con số sau chỉ là **minh họa**, không phải stdout cố định)

```text
event-observed=true
first-latency-ms=850
received-so-far=1
flush-callbacks-so-far=0
```

Ở một lần chạy khác, có thể thấy:

```text
event-observed=true
first-latency-ms=1030
received-so-far=7
flush-callbacks-so-far=1
```

Hoặc nếu hết thời gian chờ trước khi có callback:

```text
event-observed=false
received-so-far=0
flush-callbacks-so-far=0
```

**Không gán một trong ba đoạn trên là «kết quả bắt buộc».** Hành vi streaming phụ thuộc tải CPU, flush, startup và điều kiện môi trường. Thậm chí `flush-callbacks-so-far` có thể vẫn bằng `0` ngay sau khi `firstEvent` đã được đếm, vì `onFlush` của batch đó thường được gọi **sau** callback `onEvent` và main thread có thể in trước.

### 7.1. Giải thích từng phần

1. `@Name("demo.FlushLatency")` đặt một tên event thống nhất với `onEvent(...)`.
2. `stream.enable(Probe.class).withoutThreshold()` bật loại custom event. `Probe` dùng hai field primitive (`int`, `long`) phù hợp JFR.
3. `setMaxAge`/`setMaxSize` giới hạn dữ liệu giữ trong repository của recording stream. **Chúng không điều khiển tần suất flush.**
4. `stream.onEvent(...)` đọc `emittedNanoTime` từ `RecordedEvent`, lấy `System.nanoTime()` ở callback và tính delta.
5. `AtomicLong.compareAndSet(-1, latencyNs)` lưu phép đo đầu tiên mà callback nhận; `AtomicInteger` giúp main thread đọc số lượng an toàn.
6. `CountDownLatch` cho main thread biết khi ít nhất một callback đã chạy; đây là công cụ đồng bộ, không phải API JFR.
7. `stream.onFlush(...)` chỉ tăng bộ đếm ranh giới flush mà consumer quan sát, không gọi hàm ép flush.
8. `startAsync()` chạy consumer ở thread khác; main thread có thể tiếp tục phát sinh events.
9. Vòng lặp có **timeout tổng hữu hạn khoảng 6 giây**, không chờ vô hạn và không hứa một event phải xuất hiện.
10. Try-with-resources gọi `close()`. Theo Javadoc, `close()` có thể dừng ngay hoặc sau flush tiếp theo và **không bảo đảm tất cả actions đã hoàn tất trước khi trả về**.

### 7.2. Hạn chế của phép đo

- Đây là **độ trễ đầu-cuối từ trước commit đến callback**, không phân tách riêng thời gian flush.
- Chỉ đo **các sự kiện đã nhận**; nếu event không được ghi hoặc mất khỏi cửa sổ quan sát, không có mẫu latency cho event đó.
- Trong ví dụ, producer có thể emit nhiều events trước khi callback đầu tiên được nhận. `firstLatencyNs` phản ánh **event đầu tiên được consumer xử lý**, không bảo đảm là event có `sequence == 1` nếu nhiều batch/ordering thay đổi.
- Thời gian do `System.nanoTime()` trả không được dùng so sánh trực tiếp giữa các JVM.
- `flushCallbacks` là số callback flush đã xảy ra **đến lúc in**, không phải số batch của tất cả events đã emit.
- Không nên tăng tần suất emit lên rất cao chỉ để «ép» một latency nhỏ; điều đó có thể tạo nhiều overhead, nhiễu benchmark và tăng tải JFR.

## 8. `onFlush` và độ trễ callback

Một câu hỏi thường gặp: «Nếu `onFlush` đã chạy thì chắc chắn mọi event từ producer đã được nhận?»

**Không.** `onFlush` chỉ báo **stream đã hoàn thành một batch/flush** theo hợp đồng của consumer. Nó không biết producer sẽ tiếp tục commit bao nhiêu event, event có qua threshold không, và không đồng nghĩa toàn bộ dữ liệu trong mọi buffer/runtime đã được chuyển giao hết.

### 8.1. Ranh giới batch hữu ích cho aggregator

Ví dụ cần tính số event một đợt:

```java
AtomicInteger inBatch = new AtomicInteger();

stream.onEvent("demo.FlushLatency", e -> {
    inBatch.incrementAndGet();
});

stream.onFlush(() -> {
    int count = inBatch.getAndSet(0);
    if (count > 0) {
        reportBatchCount(count);
    }
});
```

Đây là snippet **trong một phương thức**, với `reportBatchCount(int)` là hàm ứng dụng tự triển khai. Nó không phải chương trình Java độc lập.

Nếu callback `onEvent` lọc một loại sự kiện, `count` chỉ là số sự kiện **phù hợp** trong batch đó, không phải toàn bộ JFR events. Nếu bạn cũng đăng ký nhiều callback `onEvent` cho các loại khác, cần xác định chính sách gộp rõ.

### 8.2. Tại sao không nên thêm `Thread.sleep(100)` rồi tin đã flush?

`Thread.sleep` chỉ tạm nhường thread theo khoảng thời gian tối thiểu tương ứng; nó **không ra lệnh JFR flush**. Một người viết test có thể thấy máy mình thường nhận callback sau vài trăm mili-giây rồi vô tình biến con số đó thành giả định.

Thực tế, sự sẵn sàng dữ liệu còn phụ thuộc:

- Tải CPU và scheduling của JVM/process;
- Loại event, threshold và tần suất tạo event;
- JFR buffering/chunks, thời điểm flush và repository;
- Chi phí parse/ordering và callback;
- Retention và việc consumer có theo kịp tốc độ ghi hay không;
- Các điều kiện I/O, disk và quyền truy cập;
- Việc stream có thực sự được start và giữ sống đủ lâu.

**Hãy dùng tín hiệu đồng bộ** như `CountDownLatch`/`CompletableFuture` và deadline hợp lý trong test, nhưng vẫn nhận biết timeout là một **thất bại của điều kiện quan sát theo thời hạn**, không nhất thiết là bằng chứng event không được ghi.

## 9. Phân biệt «period của sự kiện» và «flush interval»

Trong JFR, một số loại sự kiện hệ thống có setting `period`, ví dụ `jdk.CPULoad`. API cấu hình:

```java
import java.time.Duration;

// Đoạn code minh họa với biến RecordingStream stream:
stream.enable("jdk.CPULoad").withPeriod(Duration.ofSeconds(1));
```

Điều này yêu cầu **tần suất phát sinh loại event định kỳ** theo setting, **không tạo cam kết** rằng mọi event `jdk.CPULoad` sẽ tới `onEvent` đúng mỗi 1.000 ms. Lịch phát sinh + flush + callback tạo nhiều nguồn chênh lệch.

Tương tự:

- `withThreshold(Duration.ofMillis(10))` áp dụng ngưỡng **thời lượng sự kiện**.
- `withoutStackTrace()` bỏ dữ liệu stack trace, có thể thay đổi chi phí event.
- `setOrdered(false)` bỏ sorting trong consumer, có thể giảm chi phí ở nơi ordering không quan trọng.
- `setMaxAge`/`setMaxSize` điều khiển thời gian/dung lượng **retention**, không phải flush cadence.

**Không tự phát minh `RecordingStream.setFlushInterval(...)` cho Java 17**: API `RecordingStream` Java 17 không công bố method này. Nếu dự án dùng một JDK/thư viện khác có tùy chọn flush mới, phải đọc **Javadoc/đặc tả đúng phiên bản**. Trên API EventStream chuẩn đang xét, `onFlush` là callback thông báo, không phải lệnh điều khiển flush.

## 10. Vì sao một số event «đến trễ» dù producer đã chạy xong?

Có bốn nhóm nguyên nhân cần xét:

### Nhóm A — Chưa có event hợp lệ để ghi

- Event type chưa enable trên recording.
- Event duration dưới threshold.
- Tên event trong `onEvent("...")` không trùng tên custom event thực tế.
- Callback đăng ký sai type hoặc không start stream.
- JVM cấu hình runtime không có JFR hoặc không tạo được repository.

**Kiểm tra:** Dùng recording ngắn với `enable(EventClass.class).withoutThreshold()`, thực thi producer và dump/đọc file. Nếu file không chứa event mong muốn, khoanh vùng producer/settings trước khi đổ lỗi cho stream.

### Nhóm B — Event đã ghi, nhưng chưa đi qua flush có thể quan sát

- Producer commit không đồng bộ với việc đưa dữ liệu tới consumer.
- JVM có buffering; data được chuyển theo batch.
- Stream vừa start nhưng chưa đến đợt flush có event phù hợp.
- Consumer mở repository sau một flush đã xảy ra; mặc định nó bắt đầu từ flush tiếp theo.

**Kiểm tra:** Đặt callback `onEvent` và `onFlush`, quan sát trong một khoảng chờ hữu hạn; so sánh kết quả với file dump khi cần kiểm chứng dữ liệu đã được ghi.

### Nhóm C — Consumer chậm hoặc có vấn đề xử lý

- `onEvent` làm việc nặng (gọi mạng, disk, database, log đồng bộ).
- Consumer parsing/ordering và thread scheduling bị chậm.
- Callback ném exception, nhưng lỗi không được ghi nhận.
- Ứng dụng đóng stream ngay sau `startAsync()`.

**Kiểm tra:** Giảm chi phí callback, dùng `onError(...)`, sao chép field cần thiết và chuyển sang queue có giới hạn nếu cần phân tích nặng. Dùng latch/atomic cho đồng bộ test.

### Nhóm D — Dữ liệu lịch sử không còn khả dụng

- Repository đã xoay vòng chunks theo retention.
- `setMaxAge`/`setMaxSize` quá nhỏ so với tốc độ dữ liệu.
- Stream đọc không kịp hoặc yêu cầu `setStartTime` trước khoảng dữ liệu còn lưu.
- Event chỉ nằm trong file recording khác chứ không nằm ở repository mà consumer mở.

**Kiểm tra:** Kiểm soát chính sách giữ dữ liệu và xác định chính xác nguồn `openRepository()`/`openRepository(Path)`/`openFile(Path)`. Đừng gọi `setStartTime` như phép «phục hồi» dữ liệu chưa từng ghi hoặc đã bị xóa.

## 11. So sánh với ghi file rồi đọc offline

Để phân biệt độ trễ delivery với việc event có được thu thập hay không, hãy xem chế độ **Recording → stop → dump → RecordingFile**. Khi đoạn ghi kết thúc và file dump thành công, consumer offline có thể duyệt tập dữ liệu đã được giữ trong recording.

Lưu file độc lập **`JfrOfflineVerificationDemo.java`**:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import jdk.jfr.Event;
import jdk.jfr.Name;
import jdk.jfr.Recording;
import jdk.jfr.consumer.RecordingFile;

public class JfrOfflineVerificationDemo {
    @Name("demo.Verification")
    public static class Verification extends Event {
        public int number;
    }

    private static void emit(int number) {
        Verification event = new Verification();
        event.number = number;
        event.commit();
    }

    public static void main(String[] args) throws Exception {
        Path path = Files.createTempFile("jfr-check-", ".jfr");
        try {
            try (Recording recording = new Recording()) {
                recording.setToDisk(true);
                recording.enable(Verification.class).withoutThreshold();
                recording.start();

                emit(7);
                emit(8);
                emit(9);

                recording.stop();
                recording.dump(path);
            }

            List<Integer> values = RecordingFile.readAllEvents(path)
                    .stream()
                    .filter(event -> event.getEventType().getName()
                            .equals("demo.Verification"))
                    .map(event -> event.getInt("number"))
                    .sorted()
                    .toList();

            System.out.println("saved-values=" + values);
            System.out.println("saved-count=" + values.size());
        } finally {
            Files.deleteIfExists(path);
        }
    }
}
```

```bash
javac --release 17 JfrOfflineVerificationDemo.java
java JfrOfflineVerificationDemo
```

**Stdout kỳ vọng trên JDK có JFR hoạt động và đủ quyền file:**

```text
saved-values=[7, 8, 9]
saved-count=3
```

**Giải thích:**

1. Recording chọn event `Verification` và bỏ duration threshold.
2. Producer emit ba event khi recording đang chạy.
3. `stop()` kết thúc khoảng ghi; `dump(path)` lưu file dữ liệu.
4. `RecordingFile.readAllEvents(path)` đọc **offline**; filter loại event phù hợp, rồi sort `number` cho stdout ổn định.
5. `finally` xóa file để tránh để lại dữ liệu chẩn đoán trên máy.

Đây không phải phép đo latency của streaming callback: `RecordingFile` đọc sau khi file đã được tạo. Một event tồn tại trong file nhưng không được callback nhận đúng thời hạn cho thấy cần điều tra **cửa sổ stream, flush, scheduling, retention hoặc cấu hình consumer**, thay vì kết luận producer không commit. Ngược lại, nếu file không có event, cần kiểm tra producer, enable/threshold và khoảng recording trước.

**Thực hành với file rất lớn:** `readAllEvents` tải tất cả events vào bộ nhớ; dùng `RecordingFile.hasMoreEvents()/readEvent()` để duyệt từng event nếu dataset lớn.

## 12. `start()`, `startAsync()`, `close()` và rủi ro khi dừng

| Method | Hành vi | Ảnh hưởng tới latency/quan sát |
| --- | --- | --- |
| `start()` | Xử lý callback trên thread hiện tại, thường block cho tới khi stream kết thúc | Nếu gọi ở main thread, đoạn code phía sau **chưa chạy** cho tới khi stream dừng. |
| `startAsync()` | Xử lý callback ở thread riêng | Main thread vẫn tiếp tục; phải quản lý vòng đời/đồng bộ. |
| `awaitTermination(Duration)` | Chờ stream kết thúc hoặc timeout/interruption | **Không** phải thao tác ép flush hay chờ một event cụ thể. |
| `close()` | Giải phóng tài nguyên, có thể dừng tức thời hoặc sau flush tiếp theo | **Không đảm bảo** mọi registered actions hoàn tất trước khi trả về. |
| `onClose(Runnable)` | Thông báo khi stream đóng | Không phải tín hiệu «mọi producer event đã được xử lý». |
| `onError(Consumer<Throwable>)` | Nhận lỗi bất thường của callback | Cần giám sát để không nhầm lỗi callback là chậm flush. |

**Ví dụ nguy hiểm:**

```java
try (var stream = new jdk.jfr.consumer.RecordingStream()) {
    stream.enable("jdk.CPULoad");
    stream.onEvent("jdk.CPULoad", System.out::println);
    stream.startAsync();
}
// Ra khỏi try block ngay -> stream bị close rất sớm.
```

Đoạn này là **mẫu minh họa**; callback chưa chắc có cơ hội chạy trước `close()`. Không nên dùng như một test JFR thành công/thất bại.

Khi dùng event không thường xuyên hoặc event có period dài, phải cho stream tồn tại theo khoảng quan sát đã thiết kế. Với ứng dụng chạy lâu dài, quản lý stream như một tài nguyên của service, không tạo rồi đóng ở từng request mà không có mục đích cụ thể.

## 13. Đừng nhầm loại event định kỳ với độ trễ streaming

Nếu dùng `jdk.CPULoad` với `withPeriod(Duration.ofSeconds(1))`, có hai khoảng thời gian khác nhau:

```text
Tần suất nguồn phát sự kiện:
event 1  ---------- khoảng period ---------- event 2 ...

Độ trễ nhận của mỗi event:
event 1 --buffer/flush/dispatch--> callback 1
event 2 --buffer/flush/dispatch--> callback 2
```

Khoảng period là thiết lập **khi nào JVM phát event định kỳ**; khoảng latency là **bao lâu sau khi event được phát thì consumer nhìn thấy nó**. Một event loại GC hoặc FileRead không nhất thiết có period như `CPULoad`; chúng được phát theo tình huống tương ứng.

Nếu người dùng hỏi «Tại sao mỗi giây mới thấy một dòng CPU?», đầu tiên kiểm tra setting period của `jdk.CPULoad`, rồi mới điều tra flush/latency. Đừng tự điều chỉnh `threshold` để mong rút ngắn period.

## 14. Thứ tự sự kiện và batch có thể làm số liệu sai như thế nào?

Giả sử dashboard tính khoảng cách giữa hai lần callback:

```text
callback A: event timestamp 12:00:01.100
callback B: event timestamp 12:00:01.300
callback C: event timestamp 12:00:01.200
```

Event C có timestamp sớm hơn B nhưng được nhận sau do batch khác nhau. Nếu code tính `lastTimestamp = current.getEndTime()` và giả định thời gian phải luôn tăng, nó có thể:

- Đánh dấu nhầm event là «lỗi clock».
- Tính ra khoảng âm khi so timestamp liên batch.
- Bỏ những mẫu đến trễ nhưng vẫn hợp lệ.
- Chọn sai cửa sổ aggregate.

**Cách thiết kế:** Có chính sách xử lý out-of-order data phù hợp, ví dụ gom nhóm theo event time và một khoảng chờ trễ hợp lý, hoặc chủ động chấp nhận arrival order nếu chỉ cần telemetry gần thời gian thực. Không coi ordering giữa batch là bảo đảm toàn cục của JFR.

`setOrdered(false)` thay đổi sorting trong stream; nó không làm mất `endTime` của event và không sửa thứ tự phát sinh từ producer. Chỉ dùng khi đã chứng minh downstream không phụ thuộc ordering.

## 15. Cách xác định nguồn latency khi vận hành

Một quy trình chẩn đoán hợp lý:

1. **Kiểm tra JVM/JFR sẵn sàng:** Module `jdk.jfr` có trong runtime? Repository có thể được tạo/đọc? JFR được phép truy cập?
2. **Kiểm tra event type:** Tên event chính xác? Có `@Name` tùy chỉnh, có đang enable không?
3. **Kiểm tra setting nguồn:** Threshold có loại sự kiện quá ngắn không? Event có period hay chỉ sinh khi workload xảy ra?
4. **Kiểm tra producer:** Có thật sự gọi `commit()` trong khoảng recording đang chạy không?
5. **Kiểm tra consumer:** `onEvent(...)` đăng ký trước `start()`? Stream có mở đúng repository? Đã bắt đầu/đóng đúng lúc chưa?
6. **Kiểm tra batch/flush:** `onFlush` có chạy? Có sự kiện loại khác được phân phối? Có dữ liệu sau một khoảng quan sát hợp lý không?
7. **Đối chiếu offline:** Nếu nghi event có ghi nhưng không stream, dùng recording ngắn rồi stop/dump để xem dữ liệu trong `.jfr`.
8. **Kiểm tra áp lực:** Callback có bị nghẽn bởi logging, I/O hay lock? CPU/disk có đang bận? Có cần queue có giới hạn không?
9. **Kiểm tra retention:** Repository còn dữ liệu thời điểm cần đọc? `maxAge/maxSize` có quá nhỏ không?
10. **Định nghĩa metric thật:** Ghi rõ latency đang đo producer→callback hay event end→callback. Phân tích distribution thay vì một giá trị trung bình.
11. **Kiểm thử rủi ro mất/thiếu dữ liệu:** Có nguồn count khác để đối chiếu? Streaming chỉ phản ánh events **đã quan sát**, không có counter tự động cho tất cả những events chưa ghi.
12. **Không biến quan sát thành nghiệp vụ:** Khi cần cam kết xử lý và durability, dùng hệ thống có transaction log/queue phù hợp.

### 15.1. Khi latency bất thường tăng đột ngột

Nếu latency trên stream tăng từ khoảng dưới một giây lên hàng giây, hãy kiểm tra **toàn đường đi** chứ không chỉ JVM flush:

- Workload tăng tần suất event có thể làm consumer phải decode nhiều hơn.
- Callback in từng event ra console có thể bị I/O chậm, đặc biệt khi stdout được thu qua container/logging pipeline.
- Bật nhiều event có stack traces và payload lớn có thể tăng chi phí ghi và đọc.
- GC hoặc CPU saturation có thể làm thread xử lý stream bị trì hoãn.
- Disk repository chịu tải hoặc thiếu dung lượng có thể ảnh hưởng khả năng đọc dữ liệu.
- Một event xảy ra lâu trước khi stream khởi động có thể bị đọc lại do `setStartTime`; khi đó «age lớn» là **historical age**, không phải live delivery latency.

**Cải thiện:** Giảm lượng event, lọc theo tên với `onEvent(name, ...)`, làm callback thật nhẹ, tránh parse dữ liệu không cần thiết, giới hạn retention và theo dõi số sự kiện/số batch/độ trễ theo từng khoảng. Đo lại dưới tải đại diện; không hứa một cấu hình đơn lẻ luôn làm độ trễ giảm theo tỷ lệ cố định.

## 16. Đặt metric thế nào để không đánh lừa người đọc?

Các tên minh họa:

| Metric | Mô tả chính xác | Điều không chứng minh được |
| --- | --- | --- |
| `jfr_events_observed_total` | Số event consumer đã nhận | Không phải tổng số producer đã gọi commit. |
| `jfr_stream_batches_observed_total` | Số lần callback `onFlush` đã chạy | Không phải số sự kiện hay số flush toàn JVM. |
| `jfr_observation_latency_ms` | Producer timestamp → thời điểm callback với cùng JVM | Không phải «thời gian flush thuần». |
| `jfr_event_age_at_callback_ms` | Event end timestamp → thời điểm callback wall-clock | Không phù hợp so với JVM/máy không đồng bộ. |
| `jfr_stream_callback_errors_total` | Lỗi callback quan sát được qua `onError` | Không phải toàn bộ lỗi bên producer. |
| `jfr_events_per_batch` | Count của events matching filter trong một batch | Không phải tất cả types trong repository. |

Một dashboard đáng tin phải **mô tả cơ chế đo**, đồng thời nêu rõ **mẫu dữ liệu chỉ gồm event nhận được**. Ví dụ, tính p95 latency trên các event được callback không phát hiện được một nhóm sự kiện đã mất trước khi được ghi; cần thêm nguồn count hoặc kiểm thử khác.

Với event time và processing time, hãy giữ cả hai trong dữ liệu tổng hợp khi có nhu cầu phân tích out-of-order hoặc correlation. Không chỉ lưu arrival timestamp rồi gọi đó là «thời điểm event xảy ra».

## 17. Các câu hỏi và lỗi thường gặp

| Hiểu nhầm | Sự thật | Cách xử lý |
| --- | --- | --- |
| «`commit()` xong thì `onEvent` phải chạy ngay». | Commit và callback qua buffer/flush/stream. | Dùng latch/timeout; không dựa vào synchronous delivery. |
| «`onFlush` là nút ép flush». | Nó đăng ký callback sau batch. | Không viết giả API `stream.flush()` trên EventStream. |
| «Mỗi `onFlush` tương ứng một event». | Batch có thể chứa nhiều events. | Đếm trong `onEvent`; tổng hợp ở `onFlush`. |
| «Repository stream đọc mọi event từ đầu». | Mặc định đọc từ **next flushed event**. | Dùng `setStartTime` khi cần và khi dữ liệu còn lưu. |
| «`openFile` cho thấy latency live». | Đọc file lịch sử; callback phụ thuộc tốc độ đọc. | Không trừ event-time ra để báo live latency. |
| «Không callback nghĩa là event chưa commit». | Có thể chưa flush, mismatch filter, closed stream hoặc retention. | Kiểm tra producer và offline recording. |
| «`withPeriod(1 s)` ép flush mỗi giây». | Period là thiết lập phát event định kỳ. | Phân biệt producer frequency với delivery latency. |
| «`setMaxSize` thấp giúp flush nhanh hơn». | `maxSize` giới hạn disk retention. | Cấu hình theo dung lượng, không dùng như flush controller. |
| «`startAsync` làm consumer đã sẵn sàng đồng bộ». | Consumer chạy ở thread riêng, có scheduling/race. | Đăng ký trước start, dùng timeout và dữ liệu thử lặp. |
| «`close()` đồng nghĩa mọi callback đã xong». | Javadoc phủ nhận bảo đảm đó. | Thiết kế vòng đời/đồng bộ, không mất dữ liệu quan trọng. |
| «Events được sắp theo endTime toàn stream». | Ordering bảo đảm **trong batch**. | Xử lý out-of-order giữa batch nếu cần. |
| «Một số latency đo được là pure flush delay». | End-to-end có nhiều thành phần. | Đặt đúng tên metric, đo riêng khi có công cụ phù hợp. |
| «JFR bảo đảm exactly-once delivery». | Không phải hàng đợi giao dịch. | Dùng broker/database/transaction log cho nghiệp vụ. |

## 18. Bài tập tự kiểm tra

### Bài 1 — Thứ tự thời điểm

Một custom event được emit lúc `t0`, JVM flush ở `t1`, callback xử lý ở `t2`. Có thể coi `t2 == t0` theo hợp đồng không?

**Đáp án:** Không. JFR phân phối theo batches; callback chạy khi consumer đọc được dữ liệu. Độ trễ đầu-cuối được đo từ `t0` đến `t2`, không suy ra trực tiếp `t1 − t0`.

### Bài 2 — Nếu `onFlush` chạy hai lần

Có chắc đúng hai events đã đến consumer không?

**Đáp án:** Không. `onFlush` thông báo ranh giới flush, không phải một callback cho mỗi event. Một batch có thể có nhiều events; muốn đếm event phù hợp, tăng counter trong `onEvent`.

### Bài 3 — Repository stream khởi động muộn

Một event đã flush trước khi `EventStream.openRepository()` được start ở cấu hình mặc định. Nó có được phát lại không?

**Đáp án:** Không tự động. Theo Javadoc, mặc định stream bắt đầu từ **event flush tiếp theo**. Có thể dùng `setStartTime(Instant)` trước start để yêu cầu dữ liệu lịch sử, nhưng dữ liệu phải còn trong repository.

### Bài 4 — Đo latency bằng hai API

`Duration.between(e.getEndTime(), Instant.now())` có cùng ngữ nghĩa với `System.nanoTime() − emittedNanoTime` không?

**Đáp án:** Không hoàn toàn. Phép đầu dùng wall-clock từ end time của event; phép sau đo thời gian monotonic từ mốc do producer chụp tới callback trong cùng JVM. Cả hai đều không tự tách được thời gian flush thuần.

### Bài 5 — Tại sao không thể hứa output ms cố định?

**Đáp án:** Flush/buffering, thread scheduling, CPU/GC/disk load, số event và callback processing thay đổi. Tài liệu EventStream không có SLA «callback trong N ms» cho từng commit.

### Bài 6 — Dùng `setOrdered(false)` có xử lý event ngay khi commit không?

**Đáp án:** Không. Nó điều khiển sorting của consumer; không thay thế flush/batch và không loại bỏ latency của nguồn.

### Bài 7 — `withPeriod(Duration.ofSeconds(1))` có ý nghĩa gì?

**Đáp án:** Setting period dành cho **nguồn event định kỳ** (nếu loại event hỗ trợ); không phải khoảng thời gian flush. Callback vẫn đến khi dữ liệu sẵn có và được phân phối.

### Bài 8 — Đóng stream sau một `commit()`

Nếu gọi `startAsync()`, commit một event rồi ra khỏi `try` ngay, có bảo đảm callback nhận event chưa?

**Đáp án:** Không. `close()` có thể dừng trước/sau flush theo API, và không bảo đảm tất cả registered actions đã hoàn tất trước khi trả về. Phải quản lý vòng đời và timeout.

### Bài 9 — Một sự kiện có trong file nhưng không thấy ở stream

Đây có phải lỗi producer?

**Đáp án:** Không nhất thiết. File chứng minh event đã được ghi trong khoảng recording; hãy kiểm tra stream mở muộn, next-flush default, retention, filter, thread schedule và thời điểm đóng.

### Bài 10 — Đếm latency khi dữ liệu lịch sử được đọc

`EventStream.openFile("old.jfr")` phát một event của hôm trước. `Instant.now() − getEndTime()` lớn. Có nên gọi đây là «JFR flush latency của hôm nay»?

**Đáp án:** Không. Đây chủ yếu là **tuổi của event lịch sử tại thời điểm đọc**. Phải phân biệt live observation latency với replay offline.

## 19. Nguồn tham khảo chính thức còn áp dụng

1. [Javadoc Java SE 25 — `jdk.jfr.consumer.EventStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): batch delivery, `onFlush`, `setOrdered`, `openRepository` default next flushed event, `start/startAsync` và `close`.
2. [Javadoc Java SE 17 — `EventStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/EventStream.html): API hỗ trợ trong Java 17, nền tảng biên dịch của ví dụ.
3. [Javadoc Java SE 25 — `RecordingStream`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): tạo recording cùng với live stream, `enable`, callback và giới hạn dữ liệu.
4. [Javadoc Java SE 17 — `RecordingStream`](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingStream.html): các method `setMaxAge/setMaxSize/startAsync/onFlush` ở phiên bản mục tiêu.
5. [Javadoc Java SE 25 — `jdk.jfr.Recording`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Recording.html): recording, flush tới repository, `setToDisk`, `stop`, `dump` và retention.
6. [Javadoc Java SE 25 — `jdk.jfr.consumer.RecordingFile`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordingFile.html): đọc dữ liệu `.jfr` sau khi ghi.
7. [Javadoc Java SE 25 — `jdk.jfr.consumer.RecordedEvent`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/consumer/RecordedEvent.html): `getEndTime`, `getStartTime`, `getDuration` và đọc field.
8. [Javadoc Java SE 25 — `jdk.jfr.Event`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/Event.html): `commit`, `isEnabled`, `shouldCommit` và event lifecycle.
9. [Javadoc Java SE 25 — `jdk.jfr.EventSettings`](https://docs.oracle.com/en/java/javase/25/docs/api/jdk.jfr/jdk/jfr/EventSettings.html): `withPeriod`, `withThreshold` và `withoutThreshold` là settings của event, không phải lệnh flush stream.
10. [JEP 349 — JFR Event Streaming](https://openjdk.org/jeps/349): bối cảnh đưa streaming vào Java 14; với ứng dụng mới, theo các API JDK hiện hành nêu trên.

**Ghi nhớ:** Producer gọi `Event.commit()`, nhưng EventStream **không dispatch đồng bộ ngay tại chỗ**. Dữ liệu đi qua cơ chế ghi/đệm và được cung cấp **theo batch khi flush**, rồi `onEvent` mới chạy; `onFlush` thông báo **ranh giới batch**, không cưỡng bức flush. `openRepository()` mặc định xem từ **next flushed event**, không phải toàn bộ lịch sử. Khi báo độ trễ, hãy đặt tên đúng **producer→callback** hoặc **event end→callback**, nêu rõ biến động thực tế và **không biến EventStream thành một hệ thống có SLA exactly-once hoặc hard real-time**.