# Độ an toàn luồng và chi phí của hàm đọc Gauge

`Gauge` trong Micrometer biểu diễn một giá trị trạng thái tại thời điểm hệ thống thu thập metrics. Khác với counter được tăng tại mỗi sự kiện, gauge giữ một tham chiếu đến đối tượng trạng thái và gọi hàm đọc để lấy giá trị hiện tại khi registry hoặc exporter đọc meter.

Vì hàm đọc có thể chạy trên luồng thu thập metrics trong lúc các luồng nghiệp vụ vẫn đang cập nhật trạng thái, hàm này cần an toàn khi đọc đồng thời và có chi phí thấp. Một callback chậm, có I/O hoặc tranh chấp khóa có thể làm chậm quá trình scrape metrics và ảnh hưởng cả hệ thống giám sát. Một callback đọc dữ liệu không đồng bộ có thể trả về giá trị không nhất quán hoặc phát sinh lỗi khi trạng thái thay đổi.

Trong module OBSERVABILITY_INSTRUMENTATION_MICROMETER, bài này tập trung vào hai thuộc tính quan trọng của gauge: **đọc an toàn giữa nhiều luồng** và **đọc nhanh, không tạo tải phụ đáng kể**. Các ví dụ sử dụng Java và `MeterRegistry`, phù hợp với component Spring Boot.

## 1. Gauge được đọc khi thu thập metrics

Gauge không lưu lại mọi thay đổi của trạng thái. Nó cung cấp giá trị hiện tại thông qua một hàm đọc. Ví dụ, nếu gauge đo số request đang xử lý, giá trị có thể thay đổi từ 2 lên 5 rồi về 3 giữa hai lần scrape. Backend chỉ nhìn thấy giá trị tại những thời điểm thu thập; nó có thể không quan sát được các giá trị trung gian.

```java
AtomicInteger inFlight = new AtomicInteger();

Gauge.builder("app.requests.inflight", inFlight, AtomicInteger::get)
        .description("Number of requests currently being processed")
        .register(registry);
```

Ở đây, `AtomicInteger::get` là hàm đọc. Micrometer gọi hàm này khi cần lấy giá trị gauge. Việc gọi `inFlight.incrementAndGet()` hoặc `decrementAndGet()` trong luồng nghiệp vụ chỉ cập nhật trạng thái; nó không lập tức gửi một sample mới đến backend.

Điều này tạo ra hai hệ quả:

- Gauge phù hợp với trạng thái hiện tại như số tác vụ đang chạy, độ dài hàng đợi hoặc số kết nối đang mở.
- Gauge không phù hợp để đếm sự kiện cần lưu lại đầy đủ. Nếu một sự kiện tăng rồi giảm giữa hai lần scrape, backend có thể không thấy sự kiện đó. Hãy dùng `Counter` hoặc meter phù hợp để ghi nhận sự kiện tích lũy.

## 2. Hàm đọc cần an toàn khi nhiều luồng truy cập

Trong ứng dụng server, nhiều request hoặc worker có thể cập nhật cùng một trạng thái. Trong khi đó, luồng scrape có thể đọc gauge bất kỳ lúc nào. Không nên giả định callback luôn chạy trên cùng luồng với nơi cập nhật dữ liệu.

Hãy dùng đối tượng hoặc cơ chế đồng bộ phù hợp với dữ liệu cần đo:

- `AtomicInteger` hoặc `AtomicLong` cho một giá trị số đơn lẻ cần đọc và cập nhật đồng thời.
- `AtomicReference` cho một snapshot bất biến gồm nhiều trường liên quan.
- Cấu trúc dữ liệu concurrent khi cần đọc trực tiếp một trạng thái được chia sẻ.
- Một cơ chế lock ngắn, có giới hạn khi không thể dùng snapshot hoặc atomic, và phải đánh giá tác động khi luồng scrape chờ lock.

Không đọc trực tiếp field mutable thông thường nếu các luồng khác ghi vào field đó mà không có quy tắc visibility hoặc đồng bộ. Việc đọc và ghi một biến `int` riêng lẻ có thể không bị xé giá trị trên JVM, nhưng điều đó không bảo đảm luồng đọc nhìn thấy cập nhật mới nhất hoặc nhiều field có quan hệ được nhìn thấy như một trạng thái nhất quán.

### 2.1. Dùng AtomicInteger cho số tác vụ đang chạy

Ví dụ sau theo dõi số tác vụ đang xử lý. Giá trị được tăng trước khi bắt đầu và giảm trong `finally` để không bị giữ sai khi thao tác phát sinh exception:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Supplier;
import org.springframework.stereotype.Component;

@Component
public class RequestConcurrencyMetrics {
    private final AtomicInteger inFlight = new AtomicInteger();

    public RequestConcurrencyMetrics(MeterRegistry registry) {
        Gauge.builder("app.requests.inflight", inFlight, AtomicInteger::get)
                .description("Number of requests currently being processed")
                .register(registry);
    }

    public <T> T measure(Supplier<T> operation) {
        inFlight.incrementAndGet();
        try {
            return operation.get();
        } finally {
            inFlight.decrementAndGet();
        }
    }
}
```

`AtomicInteger` cho phép nhiều luồng cập nhật giá trị bằng các thao tác nguyên tử. Hàm đọc `get()` nhanh, không cần duy trì một khóa do ứng dụng quản lý và trả về một giá trị số có thể dùng làm sample.

Nếu số lượng có thể vượt giới hạn `int`, hãy dùng `AtomicLong`. Nếu chỉ cần một số đo xấp xỉ trong môi trường cập nhật rất dày, `LongAdder.sum()` có thể giảm tranh chấp ghi; cần hiểu rằng kết quả đọc trong lúc cập nhật đồng thời là một snapshot xấp xỉ, không phải một phép đọc nguyên tử cho toàn bộ các ô nội bộ. Với số tác vụ đang chạy mà cần duy trì chính xác cân bằng tăng/giảm, thường nên chọn `AtomicInteger` hoặc `AtomicLong`.

### 2.2. Dùng AtomicReference cho snapshot nhiều trường

Khi gauge cần đọc dữ liệu gồm nhiều trường có liên quan, ví dụ độ dài hàng đợi và thời gian chờ lâu nhất, đọc từng field riêng có thể ghép các giá trị thuộc hai thời điểm khác nhau. Có thể tạo một snapshot bất biến rồi thay toàn bộ snapshot bằng `AtomicReference`:

```java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.stereotype.Component;

@Component
public class QueueSnapshotMetrics {
    private record QueueSnapshot(long depth, long oldestWaitMillis) {}

    private final AtomicReference<QueueSnapshot> snapshot =
            new AtomicReference<>(new QueueSnapshot(0, 0));

    public QueueSnapshotMetrics(MeterRegistry registry) {
        Gauge.builder("app.queue.depth", snapshot,
                        ref -> ref.get().depth())
                .description("Current number of queued items")
                .register(registry);

        Gauge.builder("app.queue.oldest.wait", snapshot,
                        ref -> ref.get().oldestWaitMillis())
                .description("Age of the oldest queued item in milliseconds")
                .register(registry);
    }

    public void update(long depth, long oldestWaitMillis) {
        snapshot.set(new QueueSnapshot(depth, oldestWaitMillis));
    }
}
```

Luồng cập nhật tạo một record bất biến mới và thay tham chiếu bằng một thao tác nguyên tử. Mỗi callback lấy một snapshot nhất quán cho trường nó đọc. Hai gauge vẫn được scrape ở những thời điểm riêng, nhưng từng lần đọc không thấy một đối tượng snapshot bị sửa dở.

Ví dụ dùng `record`, yêu cầu Java 16 trở lên. Với phiên bản Java cũ hơn, có thể dùng một class bất biến có constructor và getter tương đương.

### 2.3. Đọc cấu trúc dữ liệu concurrent

Nếu trạng thái đã được lưu trong một cấu trúc dữ liệu thread-safe, callback có thể đọc API cung cấp snapshot hoặc số lượng hiện tại của cấu trúc đó. Tuy nhiên, cần xem xét chi phí của đúng phương thức được gọi.

Ví dụ, `ConcurrentLinkedQueue.size()` phải duyệt các node và có chi phí O(n), vì vậy gọi nó mỗi lần scrape có thể gây tải đáng kể khi hàng đợi lớn. Một cấu trúc như `LinkedBlockingQueue` có bộ đếm nội bộ cho kích thước, nhưng giá trị vẫn là trạng thái tại một thời điểm và có thể thay đổi ngay sau khi đọc. Hãy kiểm tra hợp đồng và độ phức tạp của phương thức trên cấu trúc đang dùng.

Nếu việc tính số lượng đòi hỏi duyệt một tập lớn, hãy duy trì một bộ đếm hoặc snapshot trong luồng cập nhật thay vì tính lại toàn bộ trong callback gauge. Việc cập nhật bộ đếm cần được gắn với kết quả thao tác thành công để tránh đếm thừa hoặc thiếu khi enqueue/dequeue đồng thời.

## 3. Hàm đọc Gauge cần nhanh và không có tác dụng phụ

Callback gauge được gọi trong đường thu thập metrics. Vì vậy, hãy coi nó là một hàm đọc ngắn, chỉ lấy một giá trị đã sẵn sàng. Một callback tốt thường chỉ đọc atomic, một snapshot hoặc một thuộc tính có chi phí hằng số.

Nên:

- Đọc một field atomic hoặc một snapshot đã được tính trước.
- Trả về ngay một giá trị số, không thay đổi trạng thái nghiệp vụ.
- Dùng phép đọc có chi phí ổn định, dễ ước lượng.
- Bảo đảm callback xử lý được trạng thái chưa sẵn sàng hoặc không có dữ liệu theo một quy ước rõ ràng.
- Để logic tính toán nặng chạy ở luồng nghiệp vụ hoặc luồng cập nhật riêng, rồi lưu kết quả vào snapshot.

Tránh:

- Gọi database, HTTP client, filesystem hoặc message broker từ callback.
- Duyệt toàn bộ collection lớn hoặc tổng hợp dữ liệu qua nhiều partition ở mỗi lần scrape.
- Chờ `Future.get()`, `join()` hoặc chờ semaphore/latch.
- Lấy khóa đang được giữ trong một đoạn nghiệp vụ dài.
- Tạo object lớn, stream hoặc danh sách tạm cho mỗi lần đọc.
- Ghi log ở mỗi lần callback được gọi hoặc sửa trạng thái trong callback.

Ví dụ không nên dùng:

```java
Gauge.builder("app.orders.pending", orderRepository,
        repository -> repository.countByStatus("PENDING"))
    .register(registry);
```

Hàm đọc trên thực hiện truy vấn database mỗi lần gauge được thu thập. Khi có nhiều gauge hoặc nhiều lần scrape, nó tạo thêm tải lên database và có thể làm scrape chậm hoặc timeout. Hãy cập nhật một snapshot hoặc bộ đếm trong luồng thay đổi trạng thái rồi để callback chỉ đọc giá trị đó.

## 4. Không giữ khóa lâu trong callback

Nếu trạng thái chỉ có thể đọc an toàn khi giữ lock, callback có thể làm luồng scrape chờ một luồng nghiệp vụ đang xử lý. Khi lock bị giữ lâu, việc thu thập metrics có thể bị trì hoãn; nếu nhiều callback cùng chờ lock, endpoint metrics có thể phản hồi chậm.

Ưu tiên snapshot bất biến và `AtomicReference` cho trạng thái cần đọc nhanh. Nếu bắt buộc phải dùng lock, hãy giữ critical section thật ngắn, không thực hiện I/O hoặc gọi code bên ngoài khi đang giữ lock, và không dùng lock có thể chờ không giới hạn trong callback.

Ví dụ cách đọc snapshot thay cho việc khóa một cấu trúc lớn:

```java
private final AtomicReference<QueueSnapshot> current =
        new AtomicReference<>(new QueueSnapshot(0, 0));

public double queueDepthForGauge() {
    return current.get().depth();
}
```

Phương thức đọc chỉ lấy tham chiếu hiện tại và một trường primitive. Luồng cập nhật chịu trách nhiệm tạo snapshot mới khi dữ liệu thay đổi.

## 5. Quản lý vòng đời đối tượng được Gauge tham chiếu

Micrometer gauge thường giữ weak reference đến đối tượng được đo. Điều này tránh để registry vô tình giữ sống mọi object mà ứng dụng từng đăng ký. Nếu không còn tham chiếu mạnh nào đến object, garbage collector có thể thu hồi nó; gauge khi đó có thể trả về `NaN`.

Vì vậy, đối tượng được đo nên được giữ bởi một bean hoặc một thành phần có vòng đời phù hợp:

```java
@Component
public class WorkerPoolMetrics {
    private final AtomicInteger activeWorkers = new AtomicInteger();

    public WorkerPoolMetrics(MeterRegistry registry) {
        Gauge.builder("app.worker.active", activeWorkers,
                        AtomicInteger::get)
                .description("Number of active workers")
                .register(registry);
    }
}
```

Field `activeWorkers` giữ tham chiếu mạnh trong suốt vòng đời bean. Nếu đối tượng chỉ được tạo thành biến cục bộ trong constructor rồi không được lưu lại, không nên giả định registry sẽ giữ nó sống.

Một số phiên bản Micrometer cung cấp tùy chọn `strongReference(true)` trên gauge builder. Tùy chọn này làm registry giữ tham chiếu mạnh đến object được đo. Chỉ dùng khi đã cân nhắc vòng đời và nguy cơ giữ object lâu hơn dự kiến; cách dễ kiểm soát nhất thường là để component sở hữu field trạng thái rõ ràng.

Khi bean hoặc đối tượng được đo bị thay thế, hãy bảo đảm gauge được đăng ký lại theo lifecycle phù hợp hoặc cập nhật cùng object đang được giữ. Không tạo object mới ở mỗi lần đọc rồi kỳ vọng gauge tự chuyển sang theo dõi object đó.

## 6. Xử lý giá trị không hợp lệ và trạng thái chưa sẵn sàng

Callback nên luôn có một quy ước rõ ràng cho trạng thái khởi tạo, thiếu dữ liệu hoặc đã dừng. Ví dụ, một queue chưa nhận item có thể trả về `0`; một bộ đếm chưa được khởi tạo cũng có thể bắt đầu từ `0` nếu đó là ý nghĩa đúng của metric.

Không nên dùng `null` làm giá trị số hoặc trả về một giá trị đặc biệt như `-1` nếu dashboard và alert không hiểu ý nghĩa của nó. Nếu không thể đo được trạng thái, hãy cân nhắc biểu diễn trạng thái đo lường bằng một metric riêng hoặc để sample không hợp lệ theo quy ước backend, thay vì trộn sentinel vào số liệu nghiệp vụ.

Tránh để callback ném exception do dereference một đối tượng có thể null. Nếu trạng thái có thể chưa tồn tại, giữ một đối tượng trạng thái khởi tạo với giá trị mặc định hoặc đọc một snapshot có null handling rõ ràng.

## 7. Kiểm thử thread-safety và hành vi đọc

Unit test với `SimpleMeterRegistry` có thể xác minh callback đọc giá trị hiện tại và phản ánh cập nhật sau đó:

```java
import static org.assertj.core.api.Assertions.assertThat;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class GaugeReadTest {
    @Test
    void readsLatestAtomicValue() {
        try (var registry = new SimpleMeterRegistry()) {
            AtomicInteger inFlight = new AtomicInteger(2);

            Gauge.builder("app.requests.inflight", inFlight,
                            AtomicInteger::get)
                    .register(registry);

            assertThat(registry.get("app.requests.inflight")
                    .gauge().value()).isEqualTo(2.0);

            inFlight.set(5);

            assertThat(registry.get("app.requests.inflight")
                    .gauge().value()).isEqualTo(5.0);
        }
    }
}
```

Test gọi `value()` để lấy sample tại thời điểm kiểm tra. Nó xác nhận gauge đọc trạng thái hiện tại, thay vì lưu giá trị cũ tại thời điểm đăng ký.

Với thành phần xử lý request đồng thời, có thể viết test nhiều worker cùng gọi `measure()` rồi kiểm tra bộ đếm trở về 0 sau khi mọi tác vụ hoàn tất. Test nên dùng latch hoặc future với timeout hữu hạn, luôn giải phóng worker trong `finally`, và tránh assert giá trị gauge ở một thời điểm ngẫu nhiên khi các worker vẫn đang chạy.

Ngoài unit test, nên kiểm tra:

- Callback không thực hiện I/O hoặc gọi repository/client.
- Đối tượng được gauge đo vẫn còn tham chiếu mạnh trong suốt thời gian cần đo.
- Nhiều luồng cập nhật không làm số đo âm hoặc mất cập nhật ngoài ý muốn.
- Callback đọc snapshot không thấy cấu trúc mutable bị sửa dở.
- Scrape endpoint vẫn phản hồi trong giới hạn thời gian khi số lượng gauge tăng.

## 8. Ước lượng chi phí của callback

Chi phí của một callback không chỉ là thời gian của một lần gọi. Nó được lặp lại theo số gauge được thu thập và tần suất thu thập của registry hoặc backend.

Ví dụ, nếu một endpoint thu thập 500 gauge mỗi 15 giây, hệ thống có khoảng 33 lần đọc gauge mỗi giây trung bình trên toàn endpoint. Nếu mỗi callback mất 20 ms và các callback chạy tuần tự, chỉ riêng thời gian đọc đã có thể lên tới khoảng 10 giây cho một lần scrape. Một callback 1 ms có chi phí nhỏ hơn nhiều, nhưng khi số gauge và số target tăng, tổng chi phí vẫn cần được quan sát.

Có thể ước lượng đơn giản:

\[
T_{scrape} \approx \sum_{i=1}^{G} T_i + T_{export}
\]

Trong đó `G` là số gauge được đọc, `T_i` là thời gian callback thứ `i`, và `T_export` là thời gian định dạng/ghi dữ liệu. Đây là mô hình gần đúng; exporter có thể có cách thu thập và xử lý khác nhau. Mục đích là nhấn mạnh rằng callback có chi phí lặp lại trong đường scrape.

Hãy đo thời gian scrape thực tế ở môi trường tương tự production, quan sát timeout và CPU, đồng thời xác định callback đắt nhất khi endpoint chậm. Đừng thêm logic tính toán nặng vào gauge chỉ vì một phép tính đơn lẻ có vẻ nhanh trong unit test.

## 9. Những lỗi thường gặp

- **Dùng field mutable không đồng bộ:** luồng scrape có thể đọc giá trị cũ hoặc trạng thái không nhất quán.
- **Gọi database trong callback:** scrape gây tải phụ lên database và có thể timeout.
- **Duyệt collection lớn:** callback có độ phức tạp O(n) làm thời gian scrape tăng theo kích thước dữ liệu.
- **Giữ lock dài:** luồng scrape có thể chờ nghiệp vụ hoặc gây tranh chấp khóa.
- **Không giữ object được đo:** weak reference khiến gauge có thể trở thành `NaN` sau garbage collection.
- **Dùng Gauge để đếm sự kiện:** các biến động giữa hai lần scrape có thể bị bỏ lỡ; dùng counter cho sự kiện tích lũy.
- **Tạo object trong hàm đọc:** gây cấp phát bộ nhớ và tăng áp lực garbage collection mỗi lần scrape.
- **Không xử lý trạng thái khởi tạo:** callback dereference null hoặc trả về giá trị không có ý nghĩa.
- **Cho rằng callback chỉ chạy một luồng:** hàm đọc phải an toàn khi chạy đồng thời với cập nhật và các lần thu thập.

## 10. Checklist cho Gauge an toàn và nhẹ

- [ ] Xác định rõ đây là trạng thái hiện tại, không phải tổng sự kiện.
- [ ] Dùng `AtomicInteger`, `AtomicLong`, `AtomicReference` hoặc cấu trúc thread-safe phù hợp.
- [ ] Giữ đối tượng được gauge đo bằng field hoặc một chủ sở hữu có vòng đời rõ ràng.
- [ ] Callback chỉ đọc một giá trị có chi phí thấp và ổn định.
- [ ] Không thực hiện I/O, chờ future, duyệt collection lớn hoặc giữ lock lâu.
- [ ] Không sửa trạng thái nghiệp vụ trong callback.
- [ ] Quy định giá trị khi trạng thái chưa sẵn sàng hoặc không có dữ liệu.
- [ ] Kiểm thử callback đọc được cập nhật mới bằng `SimpleMeterRegistry`.
- [ ] Kiểm thử đường cập nhật đồng thời và bảo đảm bộ đếm cân bằng.
- [ ] Quan sát thời gian scrape và chi phí khi số lượng gauge tăng.

Gauge hữu ích khi callback đọc được một trạng thái hiện tại bằng thao tác ngắn, an toàn giữa nhiều luồng và không tạo tải phụ. Hãy để luồng nghiệp vụ cập nhật trạng thái thread-safe, còn luồng thu thập metrics chỉ đọc một giá trị đã sẵn sàng. Cách tổ chức này giúp số liệu đáng tin cậy và tránh biến endpoint metrics thành một nguồn tải mới cho ứng dụng.
