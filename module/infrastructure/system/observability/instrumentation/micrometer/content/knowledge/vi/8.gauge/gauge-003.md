# Theo dõi giá trị qua hàm đọc, kích thước collection hoặc map

Gauge là meter dùng để quan sát một giá trị có thể tăng hoặc giảm theo thời gian. Thay vì cộng dồn sự kiện, Gauge đọc trạng thái hiện tại của một đối tượng khi registry lấy mẫu hoặc khi backend scrape metrics. Đây là lựa chọn phù hợp để theo dõi số phần tử trong hàng đợi, số entry trong cache, số worker đang hoạt động hoặc một giá trị trạng thái khác.

Micrometer cho phép tạo Gauge từ một đối tượng và hàm đọc giá trị. Hàm đọc được gọi khi giá trị Gauge được lấy ra. Với collection hoặc map, hàm đọc thường là `size()`. Cách làm này giúp mã instrumentation quan sát trực tiếp cấu trúc dữ liệu mà ứng dụng đang sử dụng, nhưng cần chú ý vòng đời đối tượng, chi phí của hàm đọc và đặc tính đồng thời của collection.

## 1. Khi nào nên dùng Gauge?

Gauge trả lời câu hỏi “giá trị hiện tại là bao nhiêu?”. Giá trị có thể tăng, giảm hoặc giữ nguyên:

- Số request đang được xử lý.
- Số kết nối đang mở.
- Số job đang chờ trong queue.
- Số entry hiện có trong cache.
- Số worker đang hoạt động.
- Dung lượng bộ nhớ hoặc một chỉ số trạng thái được đọc từ thư viện.

Gauge phù hợp với trạng thái hiện tại, còn Counter phù hợp để đếm sự kiện tích lũy. Ví dụ:

| Câu hỏi | Meter phù hợp | Lý do |
| --- | --- | --- |
| Hiện có bao nhiêu job đang chờ? | Gauge | Queue có thể tăng và giảm khi producer/consumer hoạt động. |
| Có bao nhiêu job đã được xử lý kể từ khi tiến trình chạy? | Counter | Số sự kiện xử lý tích lũy và chỉ tăng. |
| Hiện có bao nhiêu kết nối đang mở? | Gauge | Kết nối có thể được mở và đóng. |
| Tổng số kết nối đã được tạo? | Counter | Mỗi lần tạo kết nối là một sự kiện. |
| Cache hiện có bao nhiêu entry? | Gauge | Số entry thay đổi khi thêm hoặc xóa dữ liệu. |
| Có bao nhiêu byte đã được gửi? | Counter | Đây là tổng lượng tích lũy. |

Không dùng Gauge để mô phỏng bộ đếm sự kiện bằng cách giữ một số rồi tăng mãi. Việc đó làm mất ngữ nghĩa của Counter và khiến các phép truy vấn theo thời gian khó diễn giải.

## 2. Gauge đọc giá trị thông qua hàm

API `Gauge.builder` nhận tên meter, đối tượng cần quan sát và một hàm chuyển đối tượng thành giá trị số. Hàm có thể là method reference hoặc lambda:

~~~java
Gauge.builder("workers.active", activeWorkers, AtomicInteger::get)
        .description("Current number of active workers")
        .register(registry);
~~~

Trong ví dụ, `activeWorkers` là một `AtomicInteger` được cập nhật bởi logic quản lý worker. Khi registry đọc Gauge, Micrometer gọi `get()` để lấy giá trị hiện tại.

Có thể dùng lambda khi cần đọc một thuộc tính:

~~~java
Gauge.builder("pool.connections.active", connectionPool,
                pool -> pool.getActiveConnections())
        .description("Current number of active pool connections")
        .register(registry);
~~~

Hàm đọc nên nhanh, không có tác dụng phụ và không thực hiện I/O. Không gọi cơ sở dữ liệu, HTTP service hoặc thao tác chờ lâu trong hàm đọc Gauge, vì việc scrape metrics có thể bị chậm hoặc gây áp lực lên ứng dụng.

### Cập nhật trạng thái được Gauge quan sát

Gauge không có thao tác `increment()` hoặc `decrement()` như Counter. Ứng dụng cập nhật đối tượng trạng thái; Gauge chỉ đọc đối tượng đó:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

public class WorkerState {

    private final AtomicInteger activeWorkers = new AtomicInteger();

    public void workerStarted() {
        activeWorkers.incrementAndGet();
    }

    public void workerStopped() {
        activeWorkers.decrementAndGet();
    }

    public int activeCount() {
        return activeWorkers.get();
    }
}
~~~

Đăng ký Gauge với cùng đối tượng `activeWorkers` hoặc với một đối tượng `WorkerState` có hàm đọc tương ứng. Cần bảo đảm logic tăng/giảm phản ánh đúng vòng đời worker, kể cả khi khởi tạo thất bại hoặc tác vụ kết thúc bằng exception.

## 3. Theo dõi kích thước Collection

Đối với collection, kích thước hiện tại thường là số phần tử đang được giữ. Có thể dùng `Collection::size` làm hàm đọc:

~~~java
Gauge.builder("worker.queue.depth", pendingJobs, Collection::size)
        .description("Current number of jobs waiting in the worker queue")
        .register(registry);
~~~

Ở đây `pendingJobs` là collection hoặc queue đang được producer và consumer sử dụng. Khi một job được thêm vào, giá trị Gauge có thể tăng; khi consumer lấy job ra, giá trị có thể giảm.

Với `BlockingQueue`, ví dụ:

~~~java
BlockingQueue<Job> pendingJobs = new ArrayBlockingQueue<>(500);

Gauge.builder("worker.queue.depth", pendingJobs, BlockingQueue::size)
        .description("Current number of jobs waiting for processing")
        .register(registry);
~~~

Độ sâu queue giúp phát hiện tình trạng producer tạo công việc nhanh hơn tốc độ consumer xử lý. Tuy nhiên, một mẫu Gauge chỉ cho biết số phần tử tại thời điểm scrape. Nếu queue tăng cao rồi giảm giữa hai lần scrape, Prometheus có thể không nhìn thấy đỉnh ngắn đó.

### Chú ý đến chi phí của `size()`

Không phải mọi collection đều tính `size()` với cùng chi phí hoặc cùng mức nhất quán:

- Với các cấu trúc như `ArrayBlockingQueue`, thao tác lấy size thường có chi phí thấp.
- Với `ConcurrentLinkedQueue`, `size()` cần duyệt các node và có thể tốn O(n); gọi thường xuyên trên queue lớn có thể gây chi phí đáng kể.
- Với collection đồng thời, kết quả có thể phản ánh trạng thái gần đúng tại một thời điểm trong lúc các thread vẫn thêm hoặc xóa phần tử.

Hãy đọc tài liệu của cấu trúc dữ liệu đang dùng trước khi đưa `size()` vào hàm scrape. Nếu việc tính size tốn kém, cân nhắc duy trì một bộ đếm trạng thái nguyên tử được cập nhật cùng thao tác enqueue/dequeue, hoặc dùng API thống kê nhẹ mà thư viện cung cấp. Bộ đếm trạng thái đó vẫn được Gauge đọc như một giá trị hiện tại.

Không nên duy trì thêm một biến đếm thủ công nếu có thể dễ dàng làm nó lệch khỏi collection. Nếu chọn cách này, mọi đường thêm, lấy, hủy và xử lý lỗi đều phải cập nhật biến trạng thái đúng một lần.

## 4. Theo dõi kích thước Map

Với Map, `Map::size` cung cấp số entry hiện có:

~~~java
Gauge.builder("cache.entries", cache, Map::size)
        .description("Current number of entries stored in the application cache")
        .register(registry);
~~~

Ví dụ khi cache được cài bằng `ConcurrentHashMap`:

~~~java
ConcurrentMap<String, CachedValue> cache = new ConcurrentHashMap<>();

Gauge.builder("cache.entries", cache, Map::size)
        .description("Current number of entries in the cache")
        .register(registry);
~~~

Khi cache thêm hoặc loại bỏ entry, Gauge phản ánh số entry hiện tại lúc được đọc. Metric này hữu ích để phát hiện cache tăng bất thường, không giải phóng dữ liệu hoặc không tuân thủ giới hạn dung lượng.

Số entry không cho biết dung lượng bộ nhớ thực tế. Một entry có thể rất nhỏ hoặc rất lớn. Nếu cần đo byte đang sử dụng, hãy dùng số liệu dung lượng do cache hoặc thư viện quản lý cung cấp, hoặc đo riêng bằng meter có đơn vị bytes. Không suy ra memory usage chỉ từ `Map.size()`.

Đối với Map đồng thời, số lượng entry có thể thay đổi ngay trong lúc scrape. Hãy coi đây là phép đo trạng thái quan sát tại thời điểm đọc, không phải ảnh chụp giao dịch nhất quán với mọi thao tác nghiệp vụ.

## 5. Vòng đời đối tượng và tham chiếu yếu

Gauge của Micrometer thường giữ tham chiếu yếu (weak reference) đến đối tượng được quan sát. Điều này giúp registry không giữ các đối tượng ứng dụng sống mãi chỉ vì đã đăng ký meter. Đổi lại, ứng dụng phải tự bảo đảm đối tượng được quan sát vẫn còn tham chiếu mạnh trong suốt thời gian Gauge cần hoạt động.

Ví dụ không an toàn:

~~~java
void registerGauge(MeterRegistry registry) {
    AtomicInteger active = new AtomicInteger();
    Gauge.builder("workers.active", active, AtomicInteger::get)
            .register(registry);
}
~~~

Sau khi phương thức kết thúc, nếu không còn tham chiếu mạnh nào khác đến `active`, garbage collector có thể thu hồi đối tượng. Khi đó Gauge không còn đọc được trạng thái và có thể xuất giá trị NaN hoặc không hữu ích tùy registry.

Cách an toàn hơn là giữ đối tượng trong một bean hoặc state holder có vòng đời dài:

~~~java
@Component
public class WorkerMetrics {

    private final AtomicInteger activeWorkers = new AtomicInteger();

    public WorkerMetrics(MeterRegistry registry) {
        Gauge.builder("workers.active", activeWorkers, AtomicInteger::get)
                .description("Current number of active workers")
                .register(registry);
    }

    public void workerStarted() {
        activeWorkers.incrementAndGet();
    }

    public void workerStopped() {
        activeWorkers.decrementAndGet();
    }
}
~~~

Trong ví dụ, bean giữ tham chiếu mạnh đến `activeWorkers`. Đối tượng tồn tại cùng vòng đời bean nên Gauge có thể tiếp tục đọc giá trị. Với collection và map, hãy giữ cấu trúc dữ liệu trong service, cache hoặc component quản lý nó; không đăng ký Gauge với một collection tạm được tạo ra chỉ để lấy size.

Không nên dùng lambda chỉ đóng trên một biến cục bộ rồi cho rằng registry sẽ giữ đối tượng đó sống. Hãy truyền đối tượng cần quan sát rõ ràng vào `Gauge.builder` và giữ nó ở nơi có vòng đời phù hợp.

## 6. An toàn luồng và tính nhất quán

Gauge thường được đọc từ một thread scrape hoặc thread thu thập metrics trong khi các thread nghiệp vụ vẫn cập nhật trạng thái. Vì vậy, đối tượng được quan sát và hàm đọc cần có cách đồng bộ phù hợp.

- Dùng `AtomicInteger`, `AtomicLong`, `LongAdder` hoặc cấu trúc dữ liệu đồng thời khi trạng thái được nhiều thread cập nhật.
- Dùng collection/map thread-safe nếu nhiều thread cùng thay đổi cấu trúc dữ liệu.
- Tránh đọc một biến primitive thông thường từ nhiều thread nếu không có cơ chế visibility phù hợp như `volatile`, atomic hoặc lock.
- Giữ hàm đọc ngắn và không chờ lock lâu.
- Chấp nhận rằng giá trị Gauge là một quan sát tại thời điểm đọc; không mặc định nó tạo ra snapshot nhất quán với nhiều cấu trúc dữ liệu.

Nếu cần một snapshot gồm nhiều trường phải nhất quán với nhau, hãy tạo một đối tượng snapshot được cập nhật nguyên tử hoặc dùng API snapshot của thư viện nguồn. Không ghép nhiều Gauge độc lập rồi giả định tất cả được đọc đúng cùng một thời điểm.

## 7. Đăng ký Gauge một lần và đặt tên có ý nghĩa

Gauge nên được đăng ký một lần trong constructor hoặc lúc khởi tạo component, không tạo lại ở mỗi request. Registry quản lý meter theo tên và tag; đăng ký lặp lại cùng một meter không tạo ra cách đo mới, còn tạo tag-value mới liên tục có thể làm cardinality tăng.

Tên Gauge nên mô tả trạng thái và đơn vị:

| Tên Micrometer | Ý nghĩa | Đơn vị gợi ý |
| --- | --- | --- |
| worker.queue.depth | Số job hiện đang chờ | jobs |
| cache.entries | Số entry hiện có trong cache | entries |
| workers.active | Số worker hiện hoạt động | workers |
| pool.connections.active | Số kết nối đang được sử dụng | connections |
| upload.bytes.pending | Số byte hiện đang chờ gửi | bytes |

Description nên giải thích chính xác trạng thái được đọc. Tránh các tên mơ hồ như `current`, `size` hoặc `value` nếu không có ngữ cảnh.

Tag chỉ nên chứa các chiều cần phân tích và có miền giá trị hữu hạn. Ví dụ queue có thể có tag `queue=emails` hoặc `queue=images` nếu hai queue được cấu hình cố định. Tránh dùng request ID, user ID, tên file hoặc URL động làm tag.

## 8. Đọc và diễn giải Gauge trong Prometheus

Với Prometheus, Gauge thường được scrape thành giá trị tại thời điểm thu thập. Ví dụ metric worker.queue.depth có thể được chuẩn hóa thành `worker_queue_depth`.

Đọc giá trị hiện tại:

~~~promql
worker_queue_depth
~~~

Nếu mỗi instance có một queue riêng và muốn xem tổng số job đang chờ trên tất cả instance:

~~~promql
sum by (service) (worker_queue_depth)
~~~

Chỉ dùng phép cộng khi các queue là các phần độc lập và tổng của chúng có ý nghĩa. Nếu muốn xem queue sâu nhất trên một service:

~~~promql
max by (service) (worker_queue_depth)
~~~

Để xem mức cao nhất trong 10 phút:

~~~promql
max_over_time(worker_queue_depth[10m])
~~~

Để xem giá trị trung bình trong cửa sổ 10 phút:

~~~promql
avg_over_time(worker_queue_depth[10m])
~~~

Không áp dụng `rate()` cho Gauge như với Counter. Gauge có thể tăng hoặc giảm tùy trạng thái; `rate()` được thiết kế cho counter tăng đơn điệu và có xử lý reset. Với Gauge, dùng giá trị hiện tại hoặc hàm tổng hợp theo cửa sổ phù hợp với câu hỏi.

Nếu scrape interval là 15 giây, một đỉnh queue chỉ tồn tại trong 2 giây có thể không được lấy mẫu. Khi cần phát hiện quá tải ngắn, có thể bổ sung Counter cho số lần queue vượt ngưỡng, histogram/summary cho thời gian chờ, hoặc cơ chế ghi nhận sự kiện riêng.

## 9. Kiểm thử Gauge với SimpleMeterRegistry

Có thể kiểm tra Gauge bằng `SimpleMeterRegistry` và một collection có thể thay đổi:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.HashMap;
import java.util.Map;

import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

class GaugeTest {

    @Test
    void gaugeReadsTheCurrentMapSize() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        Map<String, String> cache = new HashMap<>();

        Gauge.builder("cache.entries", cache, Map::size)
                .register(registry);

        assertThat(registry.get("cache.entries").gauge().value()).isEqualTo(0.0);

        cache.put("first", "value");
        cache.put("second", "value");

        assertThat(registry.get("cache.entries").gauge().value()).isEqualTo(2.0);
    }
}
~~~

Biến `cache` vẫn được giữ trong phạm vi test, vì vậy đối tượng không bị thu hồi trước khi Gauge được đọc. Bài kiểm thử xác nhận Gauge đọc trạng thái hiện tại của Map thay vì lưu một giá trị size cố định tại thời điểm đăng ký.

Với collection hoặc map được dùng đồng thời, nên bổ sung kiểm thử ở component quản lý trạng thái để xác nhận các thao tác thêm/xóa và cập nhật metric không làm sai ngữ nghĩa. Không cần kiểm tra một giá trị chính xác giữa các thao tác đồng thời nếu cấu trúc dữ liệu chỉ bảo đảm tính nhất quán yếu.

## 10. Lỗi thường gặp khi dùng Gauge

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Đăng ký Gauge với object cục bộ rồi bỏ tham chiếu | Object có thể bị garbage collector thu hồi; Gauge không còn giá trị hữu ích. | Giữ object trong field của bean hoặc state holder lâu dài. |
| Dùng Gauge để đếm tổng sự kiện | Mất ngữ nghĩa tích lũy và dễ diễn giải sai. | Dùng Counter cho sự kiện tăng dần. |
| Gọi hàm đọc tốn kém hoặc có I/O | Scrape chậm và gây tải lên ứng dụng. | Dùng hàm đọc nhanh, không có side effect; duy trì trạng thái nhẹ nếu cần. |
| Gọi size() trên collection lớn mà không xem chi phí | Lấy mẫu có thể tốn CPU hoặc duyệt nhiều phần tử. | Kiểm tra đặc tính cấu trúc dữ liệu hoặc dùng bộ đếm trạng thái được cập nhật an toàn. |
| Đọc biến không an toàn giữa nhiều thread | Giá trị có thể cũ hoặc không nhất quán. | Dùng atomic, volatile, lock hoặc collection đồng thời phù hợp. |
| Kỳ vọng thấy mọi đỉnh ngắn | Scrape có thể bỏ lỡ biến động giữa hai lần lấy mẫu. | Dùng metric sự kiện bổ sung hoặc điều chỉnh chiến lược lấy mẫu. |
| Áp dụng rate() cho Gauge | Truy vấn không phản ánh đúng ngữ nghĩa trạng thái. | Dùng giá trị hiện tại hoặc hàm tổng hợp theo cửa sổ. |
| Đưa ID động vào tag | Cardinality tăng không kiểm soát. | Chỉ dùng tag có miền giá trị hữu hạn. |

## 11. Checklist trước khi phát hành Gauge

- [ ] Giá trị được đo là trạng thái hiện tại có thể tăng hoặc giảm.
- [ ] Tên và description mô tả đúng trạng thái.
- [ ] Đối tượng được quan sát có vòng đời đủ dài và được giữ bằng tham chiếu mạnh ở nơi phù hợp.
- [ ] Hàm đọc nhanh, không có I/O và không tạo tác dụng phụ.
- [ ] Chi phí `size()` hoặc getter đã được hiểu với cấu trúc dữ liệu thực tế.
- [ ] Cập nhật và đọc trạng thái an toàn khi có nhiều thread.
- [ ] Tag có tập giá trị hữu hạn và có câu hỏi phân tích rõ ràng.
- [ ] Dashboard không dùng `rate()` cho Gauge.
- [ ] Scrape interval phù hợp với độ dài biến động cần quan sát.
- [ ] Kiểm thử xác nhận Gauge phản ánh thay đổi của đối tượng.

Gauge hữu ích khi nó đọc một trạng thái có thật, có vòng đời rõ ràng và có chi phí lấy mẫu hợp lý. Với collection hoặc map, `size()` giúp quan sát số phần tử hiện tại; với một giá trị nghiệp vụ hoặc trạng thái tùy chỉnh, hàm đọc cho phép Micrometer lấy số đo trực tiếp từ đối tượng đang được ứng dụng quản lý.
