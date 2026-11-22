# Đo thời gian xử lý event đồng bộ trong Spring Framework

## 1. Vì sao cần đo?

Với Spring Framework Application Events, một lời gọi `publishEvent(...)` có thể kích hoạt nhiều listener. Trong cấu hình đồng bộ mặc định, listener chạy trên thread của publisher và có thể làm phương thức phát sự kiện chậm đi. Nếu một request HTTP đang chờ lời gọi này hoàn tất, mỗi listener chậm đều có thể góp vào thời gian phản hồi.

Ví dụ sau khi tạo đơn hàng, ứng dụng phát `OrderPlacedEvent`. Listener kiểm tra tồn kho mất khoảng 30 ms, listener ghi biên nhận mất khoảng 15 ms; thời gian phát sự kiện có thể tăng thêm khoảng 45 ms cộng chi phí dispatch và công việc liên quan. Số đo thực tế phải được quan sát, vì môi trường chạy, JIT, I/O, số lượng listener và lỗi đều ảnh hưởng.

**Mục tiêu bài học:** đo được thời gian phía publisher chờ sự kiện, thời gian riêng từng listener, kiểm tra chúng có thực sự chạy đồng bộ hay không, và diễn giải kết quả đúng để tìm nút thắt hiệu năng.

## 2. Phải phân biệt ba khoảng thời gian

| Khoảng đo | Đặt đồng hồ ở đâu? | Ý nghĩa |
| --- | --- | --- |
| **Thời gian `publishEvent`** | Ngay trước và sau `publisher.publishEvent(event)` | Thời gian caller bị chiếm bởi thao tác phát sự kiện, bao gồm dispatch và những listener thực sự chạy đồng bộ trong lời gọi |
| **Thời gian một listener** | Ngay đầu và cuối thân phương thức listener, hoặc ở lớp instrumentation bao quanh lời gọi | Độ trễ xử lý của consumer cụ thể, có thể gồm DB/HTTP nếu listener chờ chúng |
| **Thời gian nghiệp vụ đầu cuối** | Từ mốc bắt đầu nghiệp vụ đến mốc hoàn tất thật sự của các tác vụ liên quan | Có thể bao gồm transaction commit, hàng đợi, task chạy sau, retry; không mặc nhiên bằng thời gian `publishEvent` |

Trong chế độ **đồng bộ, tuần tự** thông thường, có thể hình dung:

```text
Publisher:
  t0
  | kiểm tra kiểu event, tìm listener |
  | Listener A: 30 ms             |
  | Listener B: 15 ms             |
  | dispatch/overhead             |
  t1  -> publishEvent trả về

elapsed(publishEvent) = t1 - t0
```

Thời gian `publishEvent` thường xấp xỉ tổng các lượt xử lý đồng bộ cộng phần overhead. **Không mặc định bằng đúng tổng thời gian listener**: còn có lookup, adapter, AOP interceptor, event lồng nhau, ghi log và phần đo nằm ở ranh giới khác nhau.

Nếu một listener gọi `publishEvent` lần nữa và chờ các listener của event con, thời gian của listener cha **đã chứa** thời gian event con. Cộng thời gian listener cha và con có thể đếm trùng. Với lỗi ném ra giữa chừng, một số listener có thể chưa chạy nên không thể giả định toàn bộ fan-out đã hoàn tất.

## 3. Điều kiện để phép đo phản ánh xử lý đồng bộ

Spring mặc định dùng `SimpleApplicationEventMulticaster`, thường gọi các listener trong thread phát sự kiện. Khi đó `publishEvent` chờ các listener đồng bộ hoàn tất. Tuy nhiên giao diện `ApplicationEventPublisher` chỉ hứa chuyển giao event cho cơ chế phát sự kiện; nó không bắt buộc mọi cấu hình phải chạy đồng bộ.

Cần xác định rõ cấu hình thực tế:

1. Kiểm tra có cấu hình bean `applicationEventMulticaster` với `TaskExecutor` bất đồng bộ không. Nếu có, `publishEvent` có thể chỉ đo thời gian giao task, không đo thời gian task chạy.
2. Kiểm tra listener có `@Async` kết hợp `@EnableAsync` không. Phương thức listener có thể chạy ở executor khác và tiếp tục sau khi publisher trả về.
3. Kiểm tra có `@TransactionalEventListener` không. Với `AFTER_COMMIT`, listener được kích hoạt theo mốc transaction, thường sau lời gọi `publishEvent` trong transaction; đồng hồ quanh `publishEvent` không đại diện thời gian làm việc của listener sau commit.
4. Kiểm tra có dispatch lồng nhau, proxy AOP hoặc listener thực hiện I/O chặn thread không; những thứ này thay đổi phạm vi cần đo.

**Lưu ý:** Spring có thể gọi các listener khác nhau theo thứ tự nhất định, nhưng bài toán đo thời gian không nên phụ thuộc vào thứ tự được suy đoán. Muốn tìm listener tốn thời gian nhất, phải đặt phép đo ở chính listener hoặc có công cụ instrumentation phù hợp.

## 4. Dùng đồng hồ phù hợp

Để đo **duration**, dùng `System.nanoTime()`:

```java
long started = System.nanoTime();
try {
    performWork();
} finally {
    long elapsedNanos = System.nanoTime() - started;
    double elapsedMillis = elapsedNanos / 1_000_000.0;
    // Gửi elapsedMillis/nanos tới metric hoặc log phù hợp.
}
```

Đoạn trên là minh họa bên trong một phương thức có `performWork()` được định nghĩa ở ứng dụng, không phải chương trình Java độc lập.

- `System.nanoTime()` dành cho tính khoảng thời gian tương đối, không biểu diễn ngày giờ tuyệt đối. Nó phù hợp hơn `System.currentTimeMillis()` cho latency vì mốc đồng hồ tường có thể bị điều chỉnh.
- Dùng **hiệu giữa hai lần gọi** `nanoTime()`; không diễn giải giá trị trả về riêng lẻ như Unix timestamp.
- Dùng `try/finally` để ghi thời gian ngay cả khi logic ném ngoại lệ. Nếu cần phân biệt thành công/thất bại, lưu thêm outcome; đo đủ thời gian không có nghĩa thao tác thành công.
- Chuyển từ nanosecond sang millisecond bằng chia `1_000_000.0` để giữ phần thập phân. Chia số nguyên `/ 1_000_000` làm mất độ chính xác dưới 1 ms.
- Dùng tên metric/log nhất quán; tránh tự gọi `nanoTime()` ở nhiều chỗ rồi ghép số đo có điểm bắt đầu/kết thúc khác nhau.

Với Spring, có thể dùng `StopWatch` để chẩn đoán cục bộ hoặc Micrometer `Timer` để thu thập số liệu theo thời gian. Dù dùng công cụ nào, trước hết vẫn phải quyết định chính xác **ranh giới của khoảng đo**.

## 5. Ví dụ đầy đủ Java 17+ với Spring Context

Ví dụ chạy được sau đây có hai `@EventListener` đồng bộ. Mỗi listener tự đo duration trong `finally`; caller đo tổng thời gian `publishEvent`. `Thread.sleep(...)` chỉ mô phỏng tác vụ chậm có thể quan sát, **không phải khuyến nghị đặt sleep trong mã production**.

Cấu trúc thư mục:

```text
sync-event-timing/
├── build.gradle
└── src/main/java/demo/SyncEventTimingDemo.java
```

Nội dung `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
}

application {
    mainClass = 'demo.SyncEventTimingDemo'
}
```

Nội dung `src/main/java/demo/SyncEventTimingDemo.java`:

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class SyncEventTimingDemo {

    public record OrderPlacedEvent(String orderId) {}

    public record Sample(String listener, long elapsedNanos, boolean success) {}

    public static final class TimingStore {
        private final List<Sample> samples = new ArrayList<>();

        public synchronized void record(
                String listener, long elapsedNanos, boolean success) {
            samples.add(new Sample(listener, elapsedNanos, success));
        }

        public synchronized List<Sample> snapshot() {
            return List.copyOf(samples);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public TimingStore timingStore() {
            return new TimingStore();
        }

        @Bean
        public InventoryListener inventoryListener(TimingStore store) {
            return new InventoryListener(store);
        }

        @Bean
        public ReceiptListener receiptListener(TimingStore store) {
            return new ReceiptListener(store);
        }
    }

    public static final class InventoryListener {
        private final TimingStore store;

        public InventoryListener(TimingStore store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlacedEvent event) {
            long started = System.nanoTime();
            boolean success = false;
            try {
                simulateWork(30);
                success = true;
            } finally {
                store.record(
                    "inventory",
                    System.nanoTime() - started,
                    success
                );
            }
        }
    }

    public static final class ReceiptListener {
        private final TimingStore store;

        public ReceiptListener(TimingStore store) {
            this.store = store;
        }

        @EventListener
        public void onOrderPlaced(OrderPlacedEvent event) {
            long started = System.nanoTime();
            boolean success = false;
            try {
                simulateWork(15);
                success = true;
            } finally {
                store.record(
                    "receipt",
                    System.nanoTime() - started,
                    success
                );
            }
        }
    }

    private static void simulateWork(long millis) {
        try {
            Thread.sleep(millis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Work interrupted", ex);
        }
    }

    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(Config.class)) {

            TimingStore store = context.getBean(TimingStore.class);
            OrderPlacedEvent event = new OrderPlacedEvent("ORD-101");

            long publishedAt = System.nanoTime();
            context.publishEvent(event);
            long publishNanos = System.nanoTime() - publishedAt;

            System.out.printf(
                Locale.ROOT,
                "publishEvent: %.3f ms%n",
                publishNanos / 1_000_000.0
            );

            for (Sample sample : store.snapshot()) {
                System.out.printf(
                    Locale.ROOT,
                    "%s listener: %.3f ms, success=%s%n",
                    sample.listener(),
                    sample.elapsedNanos() / 1_000_000.0,
                    sample.success()
                );
            }
        }
    }
}
```

Chạy với JDK 17+ và Gradle đã được cài:

```bash
gradle run --quiet
```

**Một kết quả minh họa** có thể trông như sau; các số mili-giây sẽ **khác ở mỗi lần chạy**, và thứ tự hai dòng listener không phải hợp đồng ứng dụng:

```text
publishEvent: 51.304 ms
inventory listener: 31.085 ms, success=true
receipt listener: 15.101 ms, success=true
```

Điều có thể dự đoán từ code, nếu không phát sinh lỗi:
- Có đúng **hai bản ghi** trong `TimingStore`, một cho `inventory`, một cho `receipt`.
- Cả hai có `success=true`.
- Duration tổng của `publishEvent` chứa thời gian chạy hai listener đồng bộ và phần overhead khác. Nó có xu hướng lớn hơn mỗi duration riêng lẻ, nhưng không nên assert một số mili-giây cố định.
- Không nhất thiết in đúng `51.304`, `31.085` hoặc `15.101`; scheduler, JIT, GC, chi phí Spring và máy chạy đều tác động. `Thread.sleep(30)` chỉ yêu cầu chờ ít nhất khoảng thời gian đó, không tạo phép đo chuẩn xác 30 ms.

Trong ví dụ, `TimingStore` lưu ở RAM để dễ kiểm tra. Trong ứng dụng production, không giữ vô hạn toàn bộ mẫu đo trong `List`: dùng hệ thống metric với các thống kê tổng hợp có giới hạn bộ nhớ. Phần đo nằm **bên trong** body mỗi listener nên không tính chi phí Spring chọn listener, chuyển tham số, proxy và interceptors chạy trước khi body bắt đầu.

## 6. Xử lý khi listener ném ngoại lệ

Có hai câu hỏi tách biệt: “listener mất bao lâu trước khi lỗi?” và “toàn bộ event đã được xử lý hết chưa?”.

Với `SimpleApplicationEventMulticaster` đồng bộ mặc định và không cài `ErrorHandler`, một listener ném runtime exception có thể làm `publishEvent` ném lỗi và **dừng lượt dispatch**, khiến listener đứng sau chưa được gọi. Vì vậy, nếu chỉ ghi log sau dòng `publishEvent` như ví dụ chính, lỗi sẽ khiến log tổng không được in.

Trong ứng dụng cần đo cả trường hợp lỗi, hãy đặt thời gian publisher vào `finally`:

```java
long started = System.nanoTime();
boolean success = false;
try {
    publisher.publishEvent(event);
    success = true;
} finally {
    long elapsed = System.nanoTime() - started;
    reportPublishDuration(elapsed, success);
}
```

Đây là **đoạn minh họa**, giả định `publisher`, `event` và `reportPublishDuration(...)` đã được khai báo. `finally` ghi duration dù có exception; exception gốc vẫn được lan truyền vì không bị nuốt. Tương tự, body listener nên ghi duration và outcome trong `finally` như ví dụ Java đầy đủ.

Nếu chọn cấu hình `SimpleApplicationEventMulticaster.setErrorHandler(...)` để bắt lỗi và tiếp tục gọi listener khác, đừng nhầm “`publishEvent` trả về bình thường” với “tất cả tác vụ nghiệp vụ thành công”. Hệ thống đo cần ghi lỗi ở từng consumer; handler nuốt lỗi có thể khiến caller không nhìn thấy failure.

## 7. Dùng Micrometer Timer trong ứng dụng thực tế

Đối với dịch vụ chạy dài ngày, đo bằng một log đơn lẻ rất khó thấy p95/p99 hoặc xu hướng khi tải tăng. Micrometer `Timer` phù hợp để ghi duration và đếm số lượt xử lý, có thể xuất sang hệ thống monitoring theo cấu hình của ứng dụng.

Dưới đây là **mẫu tích hợp** bên trong một listener đã có `MeterRegistry` và service nghiệp vụ. Đoạn này cần dependency Micrometer, cấu hình đăng ký registry và các kiểu của ứng dụng; nó **không phải file Java chạy độc lập** như ví dụ ở mục 5:

```java
@EventListener
public void onOrderPlaced(OrderPlacedEvent event) {
    Timer.Sample sample = Timer.start(meterRegistry);
    String outcome = "success";
    try {
        inventoryService.reserve(event.orderId());
    } catch (RuntimeException ex) {
        outcome = "error";
        throw ex;
    } finally {
        sample.stop(
            Timer.builder("business.event.listener.duration")
                .description("Time spent processing a synchronous listener")
                .tag("event", "OrderPlaced")
                .tag("listener", "inventory")
                .tag("outcome", outcome)
                .register(meterRegistry)
        );
    }
}
```

Phần trên sử dụng `io.micrometer.core.instrument.Timer` và `MeterRegistry`, giả định các field và kiểu đã được inject đúng. Nếu muốn đếm lỗi đặc biệt hay phân loại lỗi, bổ sung counter có nhãn cardinality thấp. Với `Timer`, kiểm tra các số liệu được registry/monitoring hỗ trợ: **count**, tổng duration, tốc độ xử lý, max và percentile/histogram khi đã cấu hình. Tránh tự coi mọi backend tự động xuất p95/p99 nếu chưa bật phân phối tương ứng.

Khuyến nghị đặt tên và tag:

| Thành phần | Gợi ý | Vì sao |
| --- | --- | --- |
| Metric | `business.event.listener.duration` | Phân biệt thời gian listener với thời gian publisher |
| Tag `event` | `OrderPlaced` | Nhóm theo loại sự kiện |
| Tag `listener` | `inventory`, `receipt` | Biết consumer nào chậm |
| Tag `outcome` | `success`, `error` | Phân biệt độ trễ xử lý thành công và lỗi |
| Tránh dùng tag | `orderId`, `userId`, `eventId` | Giá trị gần như vô hạn, làm bùng số lượng time series |

Muốn đo cả thời gian publisher, tạo metric riêng, ví dụ `business.event.publish.duration` quanh `publishEvent`. Đừng dùng cùng tên metric cho hai ranh giới đo khác nhau vì người xem sẽ hiểu sai. Muốn điều tra một sự kiện cụ thể, có thể ghi `eventId` trong **log hoặc trace có lấy mẫu**, thay vì biến nó thành tag metric. Phải cân nhắc bảo vệ dữ liệu nhạy cảm.

Spring Framework không nên được giả định tự tạo sẵn một observation có ngữ nghĩa mong muốn cho mọi phương thức `@EventListener`. Hãy xác minh instrumentation có thật hoặc thêm phép đo có chủ đích ở listener/service.

## 8. Phân tích số liệu để tìm nút thắt

Khi một request chậm, xem đồng thời:
1. **Duration `publishEvent`:** nó có chiếm tỷ lệ đáng kể trong request hay không?
2. **Duration theo listener:** consumer nào tăng p95/p99, tăng max hoặc có failure rate cao?
3. **Số listener thực sự chạy:** một listener mới có được đăng ký và làm tăng thời gian tổng không?
4. **Tài nguyên phía dưới:** thời gian DB query, chờ connection pool, HTTP ngoài, lock hoặc I/O có nằm bên trong listener?
5. **Điều kiện đo:** cold start/JIT, tải đồng thời, GC, warmup, máy/VM/container và tranh chấp tài nguyên có làm số đo lệch không?

Ví dụ nếu `publishEvent` tăng từ khoảng 20 ms lên 180 ms, còn một listener có p95 khoảng 160 ms do truy vấn database, ưu tiên xem truy vấn và connection pool của listener đó. Nếu mọi listener riêng lẻ vẫn nhanh nhưng publisher chậm, kiểm tra chi phí khác giữa hai mốc đo (AOP, nested events, adapter, chọn listener, logging, blocking phía caller) và bảo đảm các số liệu đang đo cùng phạm vi.

**Không cộng percentile:** p95 của A + p95 của B không bằng p95 của tổng một cách tổng quát, vì phần trăm thứ 95 có thể xảy ra ở các lượt event khác nhau. Muốn hiểu latency đầu cuối, đo trực tiếp trên đường đi đầu cuối và phân tích trace/mẫu liên quan.

Nên quan sát cả tải: một listener 30 ms trên luồng request có thể chấp nhận ở tần suất thấp nhưng trở thành nút thắt khi nhiều request cùng giữ thread. Việc chọn bất đồng bộ có thể giảm thời gian block publisher, song yêu cầu riêng về queue, throughput, retry và độ bền.

## 9. Các trường hợp dễ đo sai

### 9.1. Listener bất đồng bộ

Với `@Async` hoặc multicaster sử dụng executor, đồng hồ quanh `publishEvent` có thể kết thúc khi task vừa được lên lịch. Thời gian 2 ms của publisher **không nói** listener đã hoàn thành trong 2 ms. Hãy đo riêng thời gian trong task và, nếu cần end-to-end, lưu mốc phát, mốc bắt đầu thực thi và mốc hoàn tất để tách **queue wait** khỏi **processing time**. Chú ý mốc của `nanoTime()` chỉ so sánh đáng tin trong môi trường đồng hồ tương ứng; giữa nhiều máy/tiến trình, cần timestamp, trace và xử lý lệch đồng hồ phù hợp.

### 9.2. Listener gắn với transaction

`@EventListener` đồng bộ thường có thể chạy trong transaction của publisher trước commit. Còn `@TransactionalEventListener(phase = AFTER_COMMIT)` có lifecycle khác: nếu publisher phát trong transaction, thời gian đo ngay quanh `publishEvent` không bao gồm công việc sau commit. Muốn đo tác vụ sau commit, đặt timer bên trong listener hoặc service chạy sau commit. Không gộp hai loại latency mà không chú thích.

### 9.3. Chỉ đo đường thành công

Không đặt đồng hồ kết thúc sau tác vụ mà không có `finally`, vì lỗi có thể khiến lần đo biến mất khỏi dữ liệu. Với nhiều listener, nếu một listener đồng bộ ném lỗi và dừng dispatch, số lượng sample thiếu là tín hiệu quan trọng, không nên tự điền duration bằng 0 cho listener chưa được gọi.

### 9.4. Đo logging, I/O hoặc cả startup rồi gán cho listener

`System.out.println`, format string, khởi tạo `ApplicationContext`, tải class, tạo kết nối hoặc ghi file có thể gây trễ lớn. Hãy đặt mốc ở đúng ranh giới muốn đo; ở ví dụ chính, việc dựng context diễn ra **trước** đồng hồ `publishEvent`. Không lấy kết quả một lượt cold start làm benchmark production.

### 9.5. Log mỗi sự kiện ở tải lớn

In mỗi phép đo với số thập phân có thể tạo overhead, cạnh tranh lock của logger, nhiều I/O và làm sai latency đang nghiên cứu. Trong production, dùng Timer hoặc lấy mẫu log/trace. Số liệu phải đủ để giải thích mà không làm hệ thống chậm đáng kể.

### 9.6. Cho rằng đồng bộ là bằng chứng tác vụ đã hoàn thành bền vững

Khi `publishEvent` trả về trong cấu hình đồng bộ mặc định, các listener đồng bộ được gọi thành công theo đường thực thi hiện tại. Nhưng điều đó **không tự bảo đảm** transaction đã commit, message/email đã được lưu bền vững, hoặc một side effect ngoài hệ thống chắc chắn giao thành công. Cần phân biệt kết thúc phương thức với kết quả nghiệp vụ.

## 10. Kiểm thử và đánh giá hiệu năng

**Kiểm thử hành vi:** Trong cấu hình chỉ có listener đồng bộ, tạo hai handler có thể quan sát, publish một event, rồi xác minh cả hai hoàn thành trước khi `publishEvent` trả về. Test duration nên kiểm tra giá trị được ghi, count và outcome, **không assert số mili-giây chính xác**, vì CI chạy nhanh/chậm không ổn định.

**Kiểm thử lỗi:** Cho một handler ném lỗi, kiểm tra duration được ghi trong `finally` và xác minh cách lỗi lan truyền theo cấu hình multicaster. Nếu có `ErrorHandler` riêng, test đúng chính sách ghi lỗi/tiếp tục dispatch.

**Benchmark:** Warm up để hạn chế ảnh hưởng JIT, lặp đủ mẫu, tăng tải theo các mức ổn định và nhìn phân phối p50/p95/p99. Muốn so thuật toán thuần Java ở cấp microbenchmark, cân nhắc JMH; muốn đo đường event chạy thật, dùng integration/load test với ứng dụng và tài nguyên tương ứng. Tách thời gian service nghiệp vụ khỏi overhead instrumentation nếu nghi ngờ timer/log đang chi phối kết quả.

**Báo động:** Thiết lập SLO dựa trên nhu cầu request/transaction. Ví dụ, nếu budget riêng cho event đồng bộ là 50 ms, có thể theo dõi p95 hoặc tỷ lệ sự kiện vượt 50 ms theo một cửa sổ đo thích hợp; ngưỡng này chỉ minh họa, cần xác định bằng yêu cầu của hệ thống thực tế.

## 11. Checklist áp dụng

- Đã xác nhận các listener cần đo thực sự chạy đồng bộ trên thread publisher chưa?
- Mốc đo `publishEvent` có bao quanh đúng lời gọi, không ôm cả startup/HTTP/serialization ngoài ý muốn không?
- Mỗi listener có đồng hồ riêng, sử dụng `System.nanoTime()` và ghi outcome trong `finally` không?
- Có phân biệt queue wait, handler execution, transaction commit, nested events và end-to-end latency không?
- Có thu thập duration đủ nhiều lần và xem p95/p99, max, throughput, lỗi thay vì dựa vào một log đơn lẻ không?
- Các tag metric có cardinality thấp, số liệu không bị chi phí log làm méo đáng kể không?
- Nếu listener lỗi giữa chừng, phép đo có cho biết listener nào đã chạy và listener nào chưa chạy không?
- Khi thay cấu hình sang bất đồng bộ hoặc `AFTER_COMMIT`, dashboard và tên metric có còn diễn giải đúng không?

**Kết luận thực hành:** đo `publishEvent` để biết caller bị giữ bao lâu; đo bên trong từng `@EventListener` để quy trách nhiệm thời gian xử lý; và đo đường đi đầu cuối khi có transaction, tác vụ sau commit hoặc bất đồng bộ. Ba số liệu trả lời ba câu hỏi khác nhau.

## Tài liệu tham khảo

- [Spring Framework — Additional Capabilities of the ApplicationContext (Events)](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework API — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
