# Lựa chọn Gauge cho độ sâu hàng đợi, số kết nối hoặc tác vụ đang chạy

Gauge phù hợp khi cần quan sát một giá trị trạng thái có thể tăng hoặc giảm theo thời gian. Trong ứng dụng Java, các ví dụ thường gặp là số phần tử đang chờ trong hàng đợi, số kết nối đang được sử dụng trong connection pool hoặc số tác vụ đang chạy đồng thời.

Gauge cho biết giá trị hiện tại tại thời điểm registry thu thập hoặc xuất metrics. Nó không lưu lại mọi lần giá trị thay đổi. Vì vậy, cần chọn một đối tượng trạng thái có vòng đời phù hợp, bảo đảm đối tượng còn được tham chiếu và cung cấp cách đọc giá trị an toàn. Gauge hữu ích để nhìn thấy mức tải tức thời; Counter và Timer phù hợp hơn khi cần đếm sự kiện hoặc đo thời gian đã xảy ra.

## 1. Gauge đo trạng thái hiện tại

Gauge là meter dùng để quan sát một giá trị có thể tăng hoặc giảm. Ví dụ:

- Độ sâu hàng đợi: số phần tử đang chờ được xử lý.
- Kết nối đang hoạt động: số kết nối hiện đang được mượn hoặc sử dụng.
- Tác vụ đang chạy: số công việc đã bắt đầu nhưng chưa hoàn tất.
- Bộ nhớ đang được sử dụng hoặc số phiên đang mở, nếu nguồn dữ liệu cung cấp giá trị trạng thái phù hợp.

~~~mermaid
flowchart LR
    A["Trạng thái trong ứng dụng"] --> B["Gauge"]
    B --> C["MeterRegistry"]
    C --> D["Thu thập / export"]
    D --> E["Backend metrics"]
    E --> F["Dashboard và cảnh báo"]
~~~

Giả sử queue có 12 phần tử ở lần thu thập thứ nhất, 7 phần tử ở lần thứ hai và 20 phần tử ở lần thứ ba. Gauge xuất các giá trị hiện tại tương ứng với những thời điểm đó. Nó không tự lưu lại toàn bộ quá trình queue đã tăng từ 7 lên 20 qua những thao tác enqueue/dequeue nào.

| Câu hỏi vận hành | Meter phù hợp |
| --- | --- |
| Hiện tại có bao nhiêu phần tử đang chờ? | Gauge |
| Hiện tại có bao nhiêu kết nối đang được sử dụng? | Gauge |
| Hiện tại có bao nhiêu tác vụ chưa hoàn tất? | Gauge |
| Có bao nhiêu tác vụ đã hoàn tất từ khi tiến trình chạy? | Counter |
| Mỗi tác vụ mất bao lâu? | Timer |
| Kích thước payload của các tác vụ có phân phối ra sao? | DistributionSummary |

Không dùng Gauge để thay thế Counter cho số sự kiện tích lũy. Một giá trị tăng đơn điệu như tổng số đơn đã tạo thường được biểu diễn bằng Counter; số đơn đang nằm trong hàng đợi hoặc số đơn đang xử lý mới là trạng thái phù hợp với Gauge.

## 2. Đăng ký Gauge bằng Gauge.builder

API phổ biến là Gauge.builder(name, stateObject, valueFunction). Hàm valueFunction đọc giá trị từ stateObject khi registry cần thu thập số đo.

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.BlockingQueue;

@Component
public class QueueMetrics {

    private final BlockingQueue<Job> queue;

    public QueueMetrics(
        BlockingQueue<Job> queue,
        MeterRegistry registry
    ) {
        this.queue = queue;

        Gauge.builder("jobs.queue.depth", queue, BlockingQueue::size)
            .description("Số công việc hiện đang chờ trong hàng đợi")
            .tag("queue", "default")
            .register(registry);
    }
}
~~~

Trong ví dụ:

- queue là đối tượng đang giữ trạng thái thực tế.
- BlockingQueue::size là hàm đọc số phần tử tại thời điểm thu thập.
- jobs.queue.depth là tên meter thể hiện độ sâu hàng đợi.
- tag queue=default giúp nhận diện hàng đợi trong ứng dụng.

Gauge không sao chép giá trị size vào một bộ đếm riêng. Nó giữ liên kết tới đối tượng được quan sát và gọi hàm đọc khi cần lấy giá trị. Vì vậy, đối tượng được đo phải có vòng đời đủ dài để Gauge tiếp tục truy cập.

Nếu queue là bean do Spring quản lý và được giữ trong field của component, vòng đời này thường phù hợp với vòng đời ứng dụng. Không đăng ký Gauge với một queue tạm chỉ tồn tại trong biến cục bộ rồi để biến đó hết phạm vi sau khi khởi tạo.

## 3. Chọn Gauge cho độ sâu hàng đợi

Queue depth cho biết lượng công việc đang chờ, giúp phát hiện worker xử lý chậm hoặc tốc độ tiếp nhận lớn hơn tốc độ tiêu thụ. Một ví dụ với queue có giới hạn:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

@Component
public class JobQueue {

    private final BlockingQueue<Job> queue =
        new ArrayBlockingQueue<>(500);

    public JobQueue(MeterRegistry registry) {
        Gauge.builder("jobs.queue.depth", queue, BlockingQueue::size)
            .description("Số công việc đang chờ")
            .tag("queue", "email")
            .register(registry);
    }

    public boolean submit(Job job) {
        return queue.offer(job);
    }

    public Job poll() {
        return queue.poll();
    }
}
~~~

Khi worker lấy một phần tử bằng poll(), độ sâu queue giảm. Khi submit thêm phần tử thành công, độ sâu tăng. Gauge đọc trạng thái đó tại thời điểm thu thập mà không cần gọi increment hoặc decrement trong từng thao tác.

### Diễn giải queue depth

Queue depth cần được đọc cùng với giới hạn queue và tốc độ xử lý:

- Queue nhỏ và ổn định có thể là trạng thái bình thường.
- Queue tăng liên tục có thể cho thấy worker thiếu năng lực hoặc phụ thuộc phía sau đang chậm.
- Queue thường xuyên gần giới hạn có thể dẫn đến từ chối công việc hoặc backpressure.
- Queue bằng 0 không nhất thiết có nghĩa hệ thống khỏe; có thể không có tải hoặc worker đang không nhận được công việc.

Nên xem queue depth cùng counter số công việc được nhận/từ chối, timer thời gian chờ hoặc thời gian xử lý và các metrics lỗi. Gauge cung cấp ảnh chụp trạng thái, còn những meter khác giải thích nguyên nhân và xu hướng.

Lưu ý hiệu năng: chi phí gọi size() phụ thuộc loại queue. Một số cấu trúc dữ liệu cung cấp size nhanh, trong khi một số implementation có thể phải duyệt phần tử. Chọn nguồn đọc trạng thái có chi phí phù hợp với tần suất scrape/export; tránh tính toán nặng trong hàm đọc Gauge.

## 4. Chọn Gauge cho số kết nối

Connection pool thường có các trạng thái như:

- active: số kết nối đang được sử dụng.
- idle: số kết nối đang rảnh trong pool.
- pending: số yêu cầu đang chờ một kết nối.
- maximum: giới hạn kết nối tối đa.

Nếu thư viện pool đã tích hợp Micrometer hoặc Spring Boot Actuator cung cấp metrics, nên ưu tiên binder/tích hợp sẵn. Cách này giúp dùng đúng nguồn trạng thái mà thư viện quản lý và tránh đăng ký metric trùng tên.

Khi cần tự instrument một pool, có thể dùng Gauge đọc trực tiếp các getter của đối tượng pool:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;

public class ConnectionPoolMetrics {

    private final ConnectionPool pool;

    public ConnectionPoolMetrics(
        ConnectionPool pool,
        MeterRegistry registry
    ) {
        this.pool = pool;

        Gauge.builder(
            "app.db.connections.active",
            pool,
            ConnectionPool::activeConnections
        ).description("Số kết nối database đang được sử dụng")
         .tag("pool", "primary")
         .register(registry);

        Gauge.builder(
            "app.db.connections.idle",
            pool,
            ConnectionPool::idleConnections
        ).description("Số kết nối database hiện đang rảnh")
         .tag("pool", "primary")
         .register(registry);

        Gauge.builder(
            "app.db.connections.pending",
            pool,
            ConnectionPool::pendingRequests
        ).description("Số yêu cầu đang chờ kết nối database")
         .tag("pool", "primary")
         .register(registry);
    }
}
~~~

ConnectionPool ở đây là kiểu đại diện cho thư viện pool của ứng dụng; tên getter thực tế phụ thuộc thư viện. Chỉ đăng ký những trạng thái mà pool cung cấp một cách đáng tin cậy. Nếu thư viện đã có meter tương đương, hãy dùng meter sẵn có thay vì tạo thêm một bộ đo trùng lặp.

### Đọc các chỉ số pool cùng nhau

Active connections gần bằng maximum trong thời gian dài có thể báo hiệu pool đang bão hòa. Pending requests tăng cho thấy các luồng cần kết nối đang phải chờ. Idle connections bằng 0 không phải lúc nào cũng là lỗi; cần xem cùng tải, thời gian chờ và giới hạn pool.

Không chỉ dựa vào active connections để kết luận database chậm. Kết nối có thể đang được giữ bởi code ứng dụng quá lâu, transaction kéo dài hoặc tải tăng đột biến. Kết hợp Gauge với Timer đo thời gian lấy kết nối và thời gian query để tìm nguyên nhân.

## 5. Chọn Gauge cho tác vụ đang chạy

Số tác vụ đang chạy là trạng thái có thể tăng khi bắt đầu và giảm khi hoàn tất. Có thể dùng AtomicInteger làm nguồn trạng thái:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.MeterRegistry;
import org.springframework.stereotype.Component;

import java.util.concurrent.Callable;
import java.util.concurrent.atomic.AtomicInteger;

@Component
public class TaskMetrics {

    private final AtomicInteger runningTasks = new AtomicInteger();

    public TaskMetrics(MeterRegistry registry) {
        Gauge.builder(
            "jobs.running",
            runningTasks,
            AtomicInteger::get
        ).description("Số tác vụ hiện đang thực thi")
         .register(registry);
    }

    public <T> T track(Callable<T> task) throws Exception {
        runningTasks.incrementAndGet();
        try {
            return task.call();
        } finally {
            runningTasks.decrementAndGet();
        }
    }
}
~~~

AtomicInteger cung cấp phép cập nhật và đọc an toàn khi nhiều thread cùng thay đổi số tác vụ. Khối finally bảo đảm giảm số lượng cả khi task trả về bình thường lẫn khi ném exception.

Không dùng một biến int thông thường rồi tăng/giảm từ nhiều thread mà không đồng bộ. Cập nhật đồng thời có thể làm mất thay đổi và khiến Gauge hiển thị số lượng sai.

### Với tác vụ bất đồng bộ

Nếu công việc được submit và hoàn tất ở các thread khác nhau, phải giữ bộ đếm tăng cho đến khi callback hoàn tất. Đồng thời cần xử lý trường hợp executor từ chối công việc:

~~~java
public CompletableFuture<Result> submit(Callable<Result> task) {
    runningTasks.incrementAndGet();

    try {
        return CompletableFuture.supplyAsync(() -> {
            try {
                return task.call();
            } catch (Exception ex) {
                throw new CompletionException(ex);
            } finally {
                runningTasks.decrementAndGet();
            }
        }, executor);
    } catch (RejectedExecutionException ex) {
        // Công việc chưa chạy nên cần hoàn lại số lượng đã tăng.
        runningTasks.decrementAndGet();
        throw ex;
    }
}
~~~

Ví dụ cần các field executor và runningTasks được quản lý trong cùng component. Trong luồng thực tế, hãy bảo đảm mỗi tác vụ chỉ tăng một lần và chỉ giảm một lần. Nếu có nhiều nhánh timeout, cancellation hoặc retry, xác định rõ nhánh nào chịu trách nhiệm kết thúc để không giảm bộ đếm hai lần.

## 6. Vòng đời đối tượng được Gauge quan sát

Gauge thường giữ tham chiếu yếu (weak reference) đến đối tượng được quan sát. Điều này tránh việc chỉ vì đăng ký Gauge mà Micrometer giữ một đối tượng không còn được ứng dụng sử dụng. Tuy nhiên, nếu không còn tham chiếu mạnh nào đến state object, garbage collector có thể thu hồi đối tượng đó.

Khi đối tượng đã bị thu hồi, Gauge có thể trả về NaN vì không còn đọc được giá trị. Backend có thể hiển thị khoảng trống hoặc giá trị không hợp lệ tùy định dạng và cách xử lý.

Ví dụ không nên làm:

~~~java
// Không giữ lại AtomicInteger sau khi đăng ký.
Gauge.builder(
    "jobs.running",
    new AtomicInteger(),
    AtomicInteger::get
).register(registry);
~~~

Đối tượng AtomicInteger chỉ được tạo inline. Sau khi không còn tham chiếu mạnh, nó có thể bị garbage collector thu hồi. Thay vào đó, lưu state object trong field của bean hoặc một đối tượng có vòng đời đủ dài:

~~~java
private final AtomicInteger runningTasks = new AtomicInteger();

public TaskMetrics(MeterRegistry registry) {
    Gauge.builder(
        "jobs.running",
        runningTasks,
        AtomicInteger::get
    ).register(registry);
}
~~~

Đối với queue hoặc connection pool, component giữ queue/pool trong field thường đã cung cấp tham chiếu mạnh cần thiết. Không tạo Gauge trên đối tượng tạm thời nếu không có chủ thể nào giữ đối tượng đó.

## 7. Gauge và tính nhất quán khi đọc trạng thái đồng thời

Hàm đọc Gauge có thể được gọi trong khi ứng dụng đang thay đổi trạng thái. Nguồn dữ liệu nên cung cấp cách đọc an toàn theo concurrency model của nó:

- Dùng AtomicInteger hoặc AtomicLong cho một giá trị đếm được cập nhật từ nhiều thread.
- Dùng collection concurrent hoặc queue phù hợp khi quan sát kích thước hàng đợi.
- Dùng getter chính thức của connection pool thay vì duy trì một bộ đếm song song dễ lệch với pool thật.
- Giữ hàm đọc đơn giản, nhanh và không có side effect.

Gauge không bảo đảm snapshot nguyên tử của nhiều trường trạng thái độc lập. Ví dụ, active, idle và pending được đọc ở những thời điểm rất gần nhau nhưng không nhất thiết tạo thành một snapshot đồng bộ tuyệt đối. Không nên giả định phép cộng các Gauge riêng lẻ luôn bằng một tổng chính xác tại cùng một thời điểm.

Với một trạng thái được tính từ nhiều trường, hãy dùng API snapshot nhất quán nếu thư viện cung cấp. Nếu không, chấp nhận sai khác nhỏ do concurrency và giải thích rõ cách diễn giải metric.

## 8. Tags và cardinality của Gauge

Gauge vẫn chịu ảnh hưởng của cardinality như mọi meter khác. Mỗi tổ hợp tên và tags có thể tạo một meter/chuỗi thời gian riêng. Chọn tags có tập giá trị nhỏ và ổn định:

| Nên dùng | Tránh dùng |
| --- | --- |
| queue=email, queue=report | queue_id duy nhất cho từng request |
| pool=primary, pool=replica | connection_id |
| worker_group=thumbnail, worker_group=export | task_id hoặc user_id |
| region=ap-southeast-1 | request_id hoặc session_id |

Nếu ứng dụng có hàng nghìn queue động được tạo theo từng khách hàng, không đăng ký Gauge riêng cho mỗi queue nếu không có giới hạn rõ ràng. Có thể đo tổng số phần tử, nhóm theo loại queue hoặc chỉ instrument các pool/queue quan trọng.

## 9. Không dùng Gauge cho mọi đại lượng

Gauge phù hợp với trạng thái hiện tại, nhưng một số câu hỏi cần meter khác:

| Nhu cầu | Lựa chọn | Lý do |
| --- | --- | --- |
| Số tác vụ hiện đang chạy | Gauge | Giá trị có thể tăng/giảm theo vòng đời tác vụ |
| Tổng số tác vụ đã chạy | Counter | Đại lượng tích lũy |
| Tốc độ hoàn tất tác vụ | Counter kết hợp phép tính rate ở backend | Cần theo dõi số sự kiện theo thời gian |
| Thời gian chờ trong queue | Timer | Đo khoảng thời gian mỗi tác vụ chờ |
| Kích thước payload xử lý | DistributionSummary | Quan sát phân phối của các giá trị |
| Số kết nối đang hoạt động | Gauge | Trạng thái hiện tại của pool |
| Tổng số kết nối được tạo | Counter | Sự kiện tạo kết nối tích lũy |

Không tạo Gauge bằng cách giữ một biến tổng số sự kiện đã xảy ra nếu Counter thể hiện đúng semantics hơn. Counter có thể được backend xử lý đúng theo quy tắc reset và tính rate; Gauge thì được hiểu là giá trị có thể lên xuống.

## 10. Kiểm thử Gauge với SimpleMeterRegistry

Có thể dùng SimpleMeterRegistry để kiểm tra Gauge đọc đúng trạng thái hiện tại:

~~~java
import io.micrometer.core.instrument.Gauge;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;
import org.junit.jupiter.api.Test;

import java.util.concurrent.atomic.AtomicInteger;

import static org.assertj.core.api.Assertions.assertThat;

class GaugeMetricsTest {

    @Test
    void gaugeReadsCurrentValueFromStateObject() {
        SimpleMeterRegistry registry = new SimpleMeterRegistry();
        AtomicInteger runningTasks = new AtomicInteger(2);

        Gauge gauge = Gauge.builder(
            "jobs.running",
            runningTasks,
            AtomicInteger::get
        ).register(registry);

        assertThat(gauge.value()).isEqualTo(2.0);

        runningTasks.incrementAndGet();

        assertThat(gauge.value()).isEqualTo(3.0);

        registry.close();
    }
}
~~~

Kiểm thử chứng minh Gauge đọc giá trị mới từ cùng state object thay vì giữ một bản sao tại thời điểm đăng ký. Có thể bổ sung các tình huống:

- Queue tăng sau khi submit và giảm sau khi poll.
- Bộ đếm tác vụ trở về 0 sau khi task hoàn tất hoặc ném exception.
- Executor từ chối task thì bộ đếm không bị tăng mãi.
- Gauge của connection pool phản ánh các getter hiện tại.
- State object được giữ tham chiếu mạnh trong suốt vòng đời meter.
- Tags không chứa định danh có cardinality cao.

Kiểm thử đơn vị với SimpleMeterRegistry xác nhận hàm đọc và cách cập nhật trạng thái. Để xác minh metrics thực sự được export, cần kiểm tra endpoint hoặc registry đích trong integration test.

## 11. Cách chọn nguồn dữ liệu Gauge

Trước khi đăng ký Gauge, hãy xác định:

1. Đại lượng có thực sự là trạng thái hiện tại, có thể tăng hoặc giảm không?
2. Đối tượng nào là nguồn dữ liệu đáng tin cậy nhất?
3. Đối tượng đó có vòng đời dài hơn Gauge và được giữ tham chiếu mạnh không?
4. Hàm đọc có an toàn khi nhiều thread cập nhật đồng thời không?
5. Việc đọc giá trị có nhanh và không gây side effect không?
6. Tags có tập giá trị hữu hạn và hữu ích cho truy vấn không?
7. Có metrics Counter hoặc Timer bổ sung để giải thích xu hướng không?

Với queue depth, hãy quan sát queue thực tế. Với connection count, ưu tiên getter hoặc binder của connection pool. Với số tác vụ đang chạy, dùng một bộ đếm trạng thái thread-safe và bảo đảm tăng/giảm đúng một lần. Khi nguồn dữ liệu và vòng đời được chọn đúng, Gauge cung cấp ảnh chụp trạng thái đáng tin cậy để phát hiện tắc nghẽn, bão hòa và biến động tải trong ứng dụng Java.
