# Đối tượng số bất biến và việc đăng ký lại cùng danh tính

Gauge trong Micrometer đo một giá trị tại thời điểm registry thu thập metrics. Khác với Counter tích lũy sự kiện, Gauge thường biểu diễn trạng thái có thể tăng hoặc giảm, chẳng hạn độ sâu hàng đợi, số kết nối đang mở hoặc số tác vụ đang hoạt động.

Để Gauge phản ánh được trạng thái mới, đối tượng mà nó quan sát phải cung cấp giá trị có thể thay đổi trong suốt thời gian meter tồn tại. Một lỗi thường gặp là đăng ký Gauge với một đối tượng số bất biến như `Integer`, `Long` hoặc `Double`, sau đó tạo một đối tượng số mới và đăng ký lại cùng tên, cùng tag với hy vọng giá trị sẽ được thay thế. Registry quản lý meter theo danh tính của nó; khi cùng một meter đã tồn tại, lần đăng ký sau thường nhận lại meter cũ và không thay đối tượng đang được quan sát. Kết quả là Gauge vẫn đọc giá trị ban đầu.

Bài này giải thích mối liên hệ giữa đối tượng được quan sát, tính bất biến của Number và việc registry tái sử dụng meter. Cách triển khai phù hợp là giữ một đối tượng mutable có vòng đời đủ dài, cập nhật trạng thái bên trong đối tượng đó và để Gauge đọc giá trị mới qua hàm truy xuất.

## 1. Gauge đọc trạng thái hiện tại

Gauge là meter dùng để quan sát một giá trị tại thời điểm lấy mẫu. Ví dụ:

- Số phần tử hiện có trong hàng đợi.
- Số kết nối database đang mở.
- Số tác vụ đang chạy.
- Số luồng đang hoạt động.
- Dung lượng bộ đệm hiện tại.

Giá trị Gauge có thể tăng hoặc giảm. Nếu hàng đợi nhận thêm công việc, độ sâu tăng; khi worker lấy công việc ra xử lý, độ sâu giảm. Vì vậy, Gauge phù hợp với trạng thái hiện tại của một tài nguyên.

Gauge không ghi lại mọi thay đổi xảy ra giữa hai lần scrape. Nếu độ sâu hàng đợi tăng từ 10 lên 100 rồi giảm về 10 trước lần scrape tiếp theo, backend có thể chỉ quan sát giá trị 10 ở cả hai lần lấy mẫu. Nếu cần đếm số lần hàng đợi tăng, hãy ghi một Counter riêng; nếu cần phân bố thời gian một công việc chờ, cân nhắc Timer.

## 2. Đối tượng được Gauge quan sát

Khi đăng ký Gauge bằng builder, ứng dụng cung cấp:

1. Tên meter và các tag.
2. Đối tượng cần quan sát.
3. Hàm đọc một giá trị số từ đối tượng đó.

Ví dụ với một đối tượng hàng đợi:

~~~java
Gauge.builder("orders.queue.depth", queue, Queue::size)
        .description("Current number of orders waiting in the queue")
        .register(registry);
~~~

Registry giữ Gauge đã đăng ký. Khi cần lấy giá trị, Gauge gọi hàm `Queue::size` trên đối tượng được cung cấp. Vì vậy, nếu chính đối tượng queue thay đổi nội dung, Gauge có thể đọc kích thước mới mà không cần đăng ký meter lần nữa.

Hàm đọc nên nhẹ, nhanh và không có side effect. Không thực hiện truy vấn mạng, gọi database hoặc phép tính tốn kém trong hàm đọc Gauge, vì backend có thể lấy mẫu nhiều meter trong mỗi chu kỳ scrape.

### Đối tượng cần có vòng đời đủ dài

Micrometer Gauge thường giữ tham chiếu yếu đến đối tượng được quan sát. Cách này giúp registry không giữ mọi đối tượng ứng dụng sống mãi chỉ vì có một Gauge trỏ tới chúng.

Do đó, ứng dụng phải giữ tham chiếu mạnh đến đối tượng cần đo trong suốt thời gian muốn quan sát. Nếu đối tượng bị garbage collector thu hồi, Gauge không còn dữ liệu để đọc và có thể trả về `NaN`.

Ví dụ nên giữ đối tượng queue trong một bean sống cùng ứng dụng:

~~~java
@Component
final class OrderQueueMetrics {
    private final BlockingQueue<Order> queue;

    OrderQueueMetrics(BlockingQueue<Order> queue, MeterRegistry registry) {
        this.queue = queue;

        Gauge.builder("orders.queue.depth", this.queue, BlockingQueue::size)
                .description("Current number of orders waiting")
                .register(registry);
    }
}
~~~

Field `queue` giữ tham chiếu mạnh trong suốt vòng đời bean. Gauge có thể đọc kích thước hiện tại của chính queue đó.

## 3. Vì sao Number bất biến không phù hợp để cập nhật Gauge?

Các lớp như `Integer`, `Long`, `Double` và `BigDecimal` là bất biến: sau khi tạo, giá trị bên trong đối tượng không thay đổi. Một phép gán số mới không cập nhật đối tượng cũ; nó chỉ làm biến tham chiếu đến một đối tượng khác.

Ví dụ:

~~~java
Integer depth = Integer.valueOf(10);
depth = Integer.valueOf(20);
~~~

Sau phép gán, biến `depth` tham chiếu đến giá trị 20. Đối tượng Integer ban đầu vẫn có giá trị 10. Nếu Gauge đã đăng ký với đối tượng Integer ban đầu, thay đổi biến cục bộ không thay đổi đối tượng mà Gauge đang quan sát.

Ví dụ đăng ký sai với một giá trị Integer:

~~~java
Integer queueDepth = Integer.valueOf(10);

Gauge.builder("orders.queue.depth", queueDepth, Integer::doubleValue)
        .register(registry);

queueDepth = Integer.valueOf(20);
~~~

Gauge vẫn quan sát đối tượng Integer được truyền lúc đăng ký, có giá trị 10. Phép gán `queueDepth = Integer.valueOf(20)` chỉ thay đổi biến tham chiếu trong mã ứng dụng. Nó không thay đối tượng đã được gắn vào Gauge.

Vấn đề không nằm ở việc `Integer` không phải Number. Integer có thể cung cấp giá trị số cho Gauge, nhưng nó không thể thay đổi giá trị sau khi được tạo. Nếu trạng thái thay đổi theo thời gian, cần một đối tượng có thể cập nhật.

## 4. Đăng ký lại cùng danh tính không thay đối tượng được quan sát

MeterRegistry quản lý meter đã đăng ký theo định danh, thường được xác định bởi tên và bộ tag trong một registry. Khi ứng dụng đăng ký lại một Gauge có cùng tên và cùng tag, registry sẽ tái sử dụng meter hiện có thay vì tạo một meter mới cạnh tranh cùng danh tính.

Điều này có ích vì cùng một phép đo không bị nhân đôi mỗi khi nhiều thành phần yêu cầu nó. Tuy nhiên, điều đó cũng có nghĩa là đăng ký lại Gauge bằng một đối tượng mới không thay thế đối tượng mà Gauge cũ đang quan sát.

Ví dụ:

~~~java
Gauge.builder("orders.queue.depth", Integer.valueOf(10), Integer::doubleValue)
        .register(registry);

Gauge.builder("orders.queue.depth", Integer.valueOf(20), Integer::doubleValue)
        .register(registry);
~~~

Hai builder dùng cùng tên và cùng bộ tag rỗng trong cùng registry. Lần đăng ký thứ hai không thay Gauge cũ bằng đối tượng Integer mới. Meter đã đăng ký trước đó tiếp tục được dùng, vì thế giá trị quan sát vẫn gắn với đối tượng ban đầu.

Điều tương tự xảy ra nếu đối tượng mới là một AtomicInteger khác:

~~~java
AtomicInteger first = new AtomicInteger(10);
AtomicInteger second = new AtomicInteger(20);

Gauge.builder("orders.queue.depth", first, AtomicInteger::get)
        .register(registry);

Gauge.builder("orders.queue.depth", second, AtomicInteger::get)
        .register(registry);
~~~

Hai biến `first` và `second` được giữ tham chiếu mạnh trong phạm vi ví dụ. Điều này giúp minh họa riêng hành vi tái sử dụng meter mà không bị nhầm với việc đối tượng bị garbage collector thu hồi.

Không nên kỳ vọng lần đăng ký thứ hai chuyển Gauge sang AtomicInteger mới. Registry nhận diện đây là cùng một meter theo tên và tag; object đã gắn với meter hiện có vẫn là object đầu tiên.

Quy tắc cần nhớ:

- Cùng registry, cùng tên và cùng tag: yêu cầu đăng ký lại thường trả về meter hiện có.
- Khác tag: đó là một định danh meter khác và có thể tạo một chuỗi thời gian khác.
- Registry khác: meter thuộc registry khác, không dùng chung đối tượng meter đã đăng ký ở registry đầu tiên.
- Cùng tên và tag nhưng loại meter không tương thích: có thể phát sinh xung đột đăng ký; không dùng một định danh cho các ý nghĩa hoặc loại meter khác nhau.

## 5. Cách đúng: giữ một đối tượng mutable và cập nhật chính đối tượng đó

Một cách phổ biến là dùng `AtomicInteger` hoặc `AtomicLong`. Đây là các đối tượng mutable, có thể thay đổi giá trị bên trong mà không thay đổi tham chiếu đối tượng.

~~~java
@Component
final class OrderQueueMetrics {
    private final AtomicInteger queueDepth = new AtomicInteger();

    OrderQueueMetrics(MeterRegistry registry) {
        Gauge.builder("orders.queue.depth", queueDepth, AtomicInteger::get)
                .description("Current number of orders waiting")
                .register(registry);
    }

    void onOrderEnqueued() {
        queueDepth.incrementAndGet();
    }

    void onOrderDequeued() {
        queueDepth.updateAndGet(depth -> Math.max(0, depth - 1));
    }
}
~~~

Ở đây:

- Gauge được đăng ký một lần trong constructor.
- Field `queueDepth` giữ cùng một đối tượng AtomicInteger trong suốt vòng đời bean.
- Các sự kiện enqueue/dequeue cập nhật giá trị bên trong đối tượng.
- Gauge gọi `AtomicInteger::get` khi lấy mẫu và đọc giá trị mới nhất.

Không cần gọi `Gauge.builder(...).register(registry)` sau mỗi lần queue thay đổi. Chỉ cập nhật đối tượng đang được quan sát.

Nếu trạng thái có thể thay đổi đồng thời từ nhiều thread, AtomicInteger cung cấp các thao tác cập nhật an toàn cho những trường hợp đơn giản. Với trạng thái phức tạp hơn, dùng cấu trúc đồng bộ phù hợp và bảo đảm hàm đọc trả về một giá trị nhất quán.

## 6. Dùng một đối tượng trạng thái thay vì Number bất biến

Không phải lúc nào trạng thái cũng là một số nguyên đơn giản. Có thể tạo một đối tượng quản lý trạng thái và để Gauge đọc qua phương thức:

~~~java
final class WorkerPoolState {
    private final AtomicInteger activeWorkers = new AtomicInteger();

    int activeWorkers() {
        return activeWorkers.get();
    }

    void workerStarted() {
        activeWorkers.incrementAndGet();
    }

    void workerStopped() {
        activeWorkers.decrementAndGet();
    }
}
~~~

Đăng ký Gauge trên chính đối tượng trạng thái:

~~~java
final class WorkerPoolMetrics {
    private final WorkerPoolState state = new WorkerPoolState();

    WorkerPoolMetrics(MeterRegistry registry) {
        Gauge.builder("worker.pool.active", state, WorkerPoolState::activeWorkers)
                .description("Number of active workers")
                .register(registry);
    }

    void workerStarted() {
        state.workerStarted();
    }

    void workerStopped() {
        state.workerStopped();
    }
}
~~~

Khi worker bắt đầu hoặc dừng, ứng dụng gọi các phương thức cập nhật trên `state`. Gauge luôn đọc từ cùng một đối tượng `WorkerPoolState`.

Một cách khác là giữ tham chiếu đến AtomicInteger bên trong component sở hữu trạng thái. Không tạo một Integer mới cho mỗi lần cập nhật rồi hy vọng Gauge tự theo dõi biến tham chiếu mới.

## 7. Dùng AtomicReference khi cần thay đổi giá trị tham chiếu

Nếu trạng thái cần giữ một giá trị Number có thể thay thế, có thể dùng `AtomicReference` làm đối tượng mutable ổn định:

~~~java
final class QueueDepthGauge {
    private final AtomicReference<Integer> currentDepth =
            new AtomicReference<>(10);

    QueueDepthGauge(MeterRegistry registry) {
        Gauge.builder(
                "orders.queue.depth",
                currentDepth,
                reference -> reference.get().doubleValue()
        ).register(registry);
    }

    void update(int depth) {
        currentDepth.set(depth);
    }
}
~~~

Gauge quan sát đối tượng AtomicReference được giữ trong field của `QueueDepthGauge`. Đối tượng đó không bị thay thế; giá trị bên trong được thay bằng Integer mới. Hàm đọc gọi `get()` để lấy giá trị hiện tại rồi chuyển thành số double.

Cách này hữu ích khi giá trị được tính toán hoặc thay thế như một object. Với một bộ đếm số đơn giản, AtomicInteger hoặc AtomicLong thường rõ ràng hơn.

Nếu AtomicReference có thể chứa `null`, cần xác định hành vi khi đọc null. Không để hàm Gauge ném exception trong lúc scrape. Có thể giữ giá trị mặc định, hoặc dùng một kiểu trạng thái bảo đảm luôn có số hợp lệ.

## 8. Đăng ký lại cùng meter trong nhiều thành phần

Có trường hợp nhiều bean cùng cần tham chiếu đến một Gauge. Hãy thống nhất một nơi sở hữu trạng thái và một nơi đăng ký meter, sau đó inject component đó vào các thành phần cần cập nhật.

~~~java
@Component
final class QueueState {
    private final AtomicInteger depth = new AtomicInteger();

    QueueState(MeterRegistry registry) {
        Gauge.builder("jobs.queue.depth", depth, AtomicInteger::get)
                .description("Current number of jobs waiting")
                .register(registry);
    }

    void increment() {
        depth.incrementAndGet();
    }

    void decrement() {
        depth.updateAndGet(value -> Math.max(0, value - 1));
    }
}
~~~

Các worker chỉ gọi `increment()` và `decrement()` trên bean `QueueState`. Chúng không cần tự đăng ký lại Gauge. Điều này tránh tình trạng mỗi worker tạo một đối tượng trạng thái riêng nhưng lại dùng cùng tên và tag, khiến registry chỉ giữ Gauge đầu tiên.

Nếu thực sự cần một Gauge riêng cho từng nhóm có ý nghĩa, hãy biểu diễn nhóm bằng tag có tập giá trị hữu hạn, ví dụ `queue=priority` hoặc `queue=standard`. Mỗi nhóm cần có một đối tượng trạng thái sống đủ lâu. Không dùng ID ngẫu nhiên hoặc ID công việc làm tag để tạo Gauge riêng cho từng đối tượng.

## 9. Common tags và danh tính Gauge

Định danh Gauge có thể bao gồm cả common tags được áp dụng bởi registry. Vì vậy, hai lời gọi builder trông có cùng tên và tag riêng vẫn có thể trở thành hai meter khác nhau nếu registry bổ sung các common tags khác nhau trước khi đăng ký.

Ví dụ:

~~~java
registry.config().commonTags("application", "order-service");

Gauge.builder("orders.queue.depth", queueDepth, AtomicInteger::get)
        .tag("queue", "priority")
        .register(registry);
~~~

Các tag chung như `application` và tag riêng `queue` cùng góp phần phân loại chuỗi thời gian. Hãy cấu hình common tags trước khi đăng ký meter và giữ tập giá trị ổn định.

Không thay đổi common tags theo từng request hoặc tenant nếu việc đó tạo ra cardinality không kiểm soát. Nếu cần quan sát nhiều queue, chọn một chiều phân loại có số lượng hữu hạn và quản lý các đối tượng trạng thái tương ứng.

## 10. Gauge có thể trả về NaN hoặc giá trị không hữu ích

Vì Gauge có thể giữ tham chiếu yếu đến đối tượng, đối tượng bị thu hồi có thể khiến giá trị đo không còn hợp lệ. Một số hàm đọc cũng có thể trả về `NaN` khi không có dữ liệu hoặc khi đối tượng không còn tồn tại.

Khi thấy Gauge hiển thị `NaN` hoặc biến mất khỏi kết quả thu thập, hãy kiểm tra:

1. Đối tượng được quan sát có còn được ứng dụng giữ tham chiếu mạnh không?
2. Gauge có được đăng ký với đối tượng tạm thời chỉ sống trong một phương thức không?
3. Hàm đọc có trả về giá trị hợp lệ và không ném exception không?
4. Một Gauge khác cùng tên và tag có được đăng ký trước đó, khiến registry giữ object cũ không?
5. Có filter hoặc cấu hình exporter nào làm meter không được xuất không?

Ví dụ không nên dùng một đối tượng tạm thời:

~~~java
void registerQueueGauge(MeterRegistry registry) {
    AtomicInteger temporaryDepth = new AtomicInteger(5);

    Gauge.builder("orders.queue.depth", temporaryDepth, AtomicInteger::get)
            .register(registry);
}
~~~

Khi phương thức kết thúc, nếu không có tham chiếu mạnh nào khác đến `temporaryDepth`, garbage collector có thể thu hồi nó. Hãy chuyển trạng thái thành field của bean sống lâu hơn.

## 11. Kiểm thử Gauge và hành vi đăng ký trùng

SimpleMeterRegistry giúp kiểm tra Gauge có đọc được giá trị mới từ cùng một đối tượng mutable hay không:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
AtomicInteger depth = new AtomicInteger(10);

Gauge.builder("orders.queue.depth", depth, AtomicInteger::get)
        .register(registry);

assertThat(registry.get("orders.queue.depth").gauge().value())
        .isEqualTo(10.0);

depth.set(25);

assertThat(registry.get("orders.queue.depth").gauge().value())
        .isEqualTo(25.0);
~~~

Kiểm thử này xác nhận Gauge đọc giá trị mới từ cùng một AtomicInteger.

Có thể kiểm tra hành vi đăng ký cùng danh tính bằng hai đối tượng khác nhau:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

AtomicInteger first = new AtomicInteger(10);
AtomicInteger second = new AtomicInteger(20);

Gauge.builder("orders.queue.depth", first, AtomicInteger::get)
        .register(registry);

Gauge.builder("orders.queue.depth", second, AtomicInteger::get)
        .register(registry);

assertThat(registry.get("orders.queue.depth").gauge().value())
        .isEqualTo(10.0);
~~~

Ví dụ cho thấy lần đăng ký thứ hai không thay object đã gắn với Gauge hiện có. Nếu ứng dụng cần giá trị 20, phải cập nhật object `first` đang được quan sát hoặc thiết kế lại nơi sở hữu trạng thái; đăng ký object `second` với cùng danh tính không thực hiện việc thay thế.

Một bộ kiểm thử đầy đủ nên xác minh:

- Gauge đọc giá trị ban đầu đúng.
- Cập nhật cùng đối tượng mutable làm giá trị Gauge thay đổi.
- Đăng ký lại cùng tên và tag với object mới không được hiểu là thay object cũ.
- Đối tượng được quan sát có vòng đời đủ dài.
- Các tag phân biệt nhóm Gauge được giới hạn và chuẩn hóa.
- Hàm đọc nhanh, an toàn khi được gọi từ luồng thu thập metrics.

## 12. Lựa chọn giữa Number, Atomic và đối tượng trạng thái

| Cách lưu trạng thái | Có thay đổi giá trị bên trong? | Phù hợp với Gauge cập nhật? | Ghi chú |
|---|---|---|---|
| `Integer`, `Long`, `Double` | Không | Không phù hợp nếu giá trị cần đổi | Đối tượng bất biến; đăng ký mới cùng danh tính không thay object cũ |
| `AtomicInteger` | Có | Có | Phù hợp với số nguyên thay đổi đồng thời |
| `AtomicLong` | Có | Có | Phù hợp với số lớn hoặc bộ đếm trạng thái dạng long |
| `AtomicReference<Integer>` | Có thể thay giá trị tham chiếu | Có | Cần bảo đảm giá trị bên trong không null |
| Đối tượng trạng thái riêng | Tùy cách triển khai | Có | Dùng hàm đọc để truy xuất trạng thái; giữ object sống đủ lâu |
| Collection hoặc queue mutable | Có | Có | Hàm đọc có thể lấy size; cân nhắc chi phí và tính nhất quán |

Không phải cứ dùng Atomic là tốt hơn trong mọi trường hợp. Hãy chọn cấu trúc phù hợp với cách trạng thái được cập nhật. Nếu trạng thái đã được quản lý bởi queue hoặc connection pool, có thể quan sát trực tiếp đối tượng đó thay vì tạo thêm một biến số độc lập dễ lệch với trạng thái thật.

## 13. Các lỗi thường gặp

**Đăng ký Gauge với Integer rồi gán biến sang Integer mới.** Gauge vẫn quan sát đối tượng ban đầu. Dùng AtomicInteger hoặc một object mutable và cập nhật object đó.

**Tạo AtomicInteger mới rồi đăng ký lại cùng tên và tag.** Registry có thể tái sử dụng Gauge cũ; object mới không tự thay object đang được quan sát. Giữ một object trạng thái ổn định.

**Đăng ký Gauge trong mỗi lần enqueue/dequeue.** Việc đăng ký lặp không phải cách cập nhật giá trị. Đăng ký một lần, sau đó thay đổi trạng thái.

**Không giữ tham chiếu mạnh đến object.** Gauge có thể trả về NaN khi object bị garbage collector thu hồi. Để object trong field của bean hoặc thành phần có vòng đời phù hợp.

**Dùng Gauge để đếm tổng số sự kiện.** Gauge là snapshot của trạng thái hiện tại. Dùng Counter cho sự kiện tích lũy.

**Đặt logic tốn kém trong hàm đọc.** Hàm đọc được gọi khi lấy mẫu metrics. Giữ nó nhanh, không có side effect và không phụ thuộc mạng.

**Tạo một Gauge cho mỗi ID động.** Cách này làm cardinality tăng nhanh. Dùng các tag có tập giá trị hữu hạn hoặc một số meter đại diện cho nhóm.

## 14. Checklist khi đăng ký Gauge

Trước khi đưa Gauge vào ứng dụng, hãy xác minh:

- [ ] Giá trị cần đo là trạng thái hiện tại có thể tăng hoặc giảm.
- [ ] Đối tượng được quan sát có thể cung cấp giá trị mới qua hàm đọc.
- [ ] Nếu dùng Number, đối tượng có thể thay đổi giá trị bên trong; không dựa vào việc thay biến tham chiếu.
- [ ] Cùng một meter được đăng ký một lần và object được quan sát được tái sử dụng.
- [ ] Đã hiểu registry không thay object khi đăng ký lại cùng tên và tag.
- [ ] Ứng dụng giữ tham chiếu mạnh đến object trong suốt thời gian cần đo.
- [ ] Hàm đọc nhanh, an toàn và không có side effect.
- [ ] Tag có cardinality thấp và mô tả nhóm trạng thái ổn định.
- [ ] Unit test xác minh cả cập nhật object lẫn hành vi đăng ký trùng.

## 15. Kết luận

Gauge đọc giá trị hiện tại từ một đối tượng được đăng ký cùng tên và tag. Khi dùng Number bất biến như Integer hoặc Long, Gauge chỉ nhìn thấy giá trị của đối tượng tại thời điểm đăng ký. Việc gán một Number mới vào biến hoặc đăng ký lại cùng danh tính không thay thế đối tượng mà registry đang giữ cho Gauge.

Hãy giữ một đối tượng mutable có vòng đời đủ dài, ví dụ AtomicInteger, AtomicLong, AtomicReference hoặc một object trạng thái riêng. Đăng ký Gauge một lần, cập nhật chính đối tượng đó và để hàm đọc lấy giá trị mới. Cách làm này giữ danh tính meter ổn định, giúp Gauge phản ánh đúng trạng thái và tránh tạo meter trùng hoặc cardinality không cần thiết.
