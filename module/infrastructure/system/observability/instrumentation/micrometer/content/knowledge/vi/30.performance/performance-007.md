# Dọn meter của tài nguyên động và kiểm soát thời gian sống

## Vì sao meter của tài nguyên động cần được dọn?

Micrometer thường được dùng với các meter tồn tại suốt vòng đời ứng dụng: số request, thời gian xử lý HTTP, bộ nhớ JVM hoặc số kết nối của một pool ổn định. Các meter này thường được đăng ký một lần khi Spring context khởi động và được cập nhật trong suốt thời gian ứng dụng chạy.

Một số ứng dụng còn tạo và hủy tài nguyên trong lúc chạy, chẳng hạn worker pool, queue, partition, scheduler hoặc connector được nạp động. Nếu mỗi tài nguyên tạo meter riêng, registry có thể tích lũy meter sau khi tài nguyên đã biến mất. Hệ quả là bộ nhớ tăng, số time series tăng, scrape/export chậm hơn và dữ liệu cũ tiếp tục xuất hiện như thể tài nguyên vẫn còn hoạt động.

Cần quản lý vòng đời meter cùng vòng đời tài nguyên:

1. **Create:** đăng ký meter cho tài nguyên khi nó được tạo.
2. **Update:** ghi nhận số liệu trong khi tài nguyên còn hoạt động.
3. **Quiesce:** ngừng nhận công việc mới và chờ các lần cập nhật đang chạy hoàn tất.
4. **Remove:** gỡ các meter do tài nguyên sở hữu khỏi registry.
5. **Release:** giải phóng tham chiếu đến nguồn dữ liệu và handle meter.

Không phải mọi tài nguyên động đều cần meter riêng. Nếu số tài nguyên lớn hoặc thay đổi liên tục, hãy ưu tiên metrics tổng hợp với tag có tập giá trị hữu hạn. Chỉ tạo meter riêng khi số lượng tài nguyên được giới hạn và việc quan sát từng tài nguyên mang lại giá trị vận hành rõ ràng.

## Danh tính meter và lý do meter không tự biến mất

### Registry định danh meter bằng tên và tag

Một meter được nhận diện chủ yếu qua tên và tập tag. Hai lần đăng ký có cùng danh tính trong cùng registry thường trả về cùng meter đã đăng ký. Khi tag thay đổi, một meter khác có thể được tạo.

Ví dụ, mỗi worker pool tạo một Gauge:

~~~java
Gauge.builder("worker.active", pool, WorkerPool::activeCount)
    .tag("pool", poolName)
    .register(registry);
~~~

Nếu ứng dụng tạo pool A, B rồi C, registry có thể giữ ba meter tương ứng. Khi pool B bị đóng, meter của B không tự biến mất chỉ vì object pool đã ngừng hoạt động. Ứng dụng phải quản lý việc gỡ meter nếu muốn loại nó khỏi registry.

### MeterRegistry không tự theo dõi vòng đời object nghiệp vụ

MeterRegistry quản lý meter, không quản lý vòng đời của worker pool, queue hoặc plugin. Việc tài nguyên bị đóng, bị garbage collection hoặc bị xóa khỏi một map nghiệp vụ không đồng nghĩa meter đã được remove.

Gauge thường giữ weak reference đến object được quan sát, nên object nguồn có thể bị garbage collection nếu ứng dụng không còn strong reference. Khi đó Gauge có thể không còn đọc được giá trị mong muốn. Với Counter và Timer, meter có thể tiếp tục tồn tại trong registry dù không còn object nghiệp vụ nào cập nhật nó.

Do đó, cần phân biệt:

- **Vòng đời object:** tài nguyên được tạo, sử dụng và đóng.
- **Vòng đời meter:** meter được đăng ký, cập nhật và gỡ khỏi registry.
- **Vòng đời time series backend:** dữ liệu đã gửi có thể tiếp tục được lưu theo retention và quy tắc của backend.

Gỡ meter khỏi registry chỉ điều khiển dữ liệu được công bố trong tương lai. Nó không phải lệnh xóa lịch sử đã lưu ở Prometheus, OTLP backend hoặc hệ thống giám sát khác.

## Khi nào nên tạo meter riêng cho tài nguyên động?

Meter riêng có ích khi số lượng tài nguyên nhỏ, có giới hạn và cần chẩn đoán từng tài nguyên. Ví dụ:

- Một vài worker pool có tên cố định.
- Một số queue được tạo theo cấu hình triển khai.
- Một nhóm connector/plugin có số lượng bị giới hạn.
- Một số partition kỹ thuật ổn định cần theo dõi riêng.

Meter riêng thường không phù hợp với:

- Mỗi HTTP request hoặc session.
- Mỗi user, order, payment hoặc message.
- Mỗi tenant nếu số tenant lớn hoặc thay đổi liên tục.
- Mỗi file, job ID hoặc correlation ID.
- Tài nguyên tạm thời được tạo hàng nghìn lần mỗi phút.

Nếu mỗi tài nguyên có một tag value duy nhất, mỗi vòng đời có thể tạo thêm một series. Dù meter được remove ở ứng dụng, backend vẫn có thể giữ dữ liệu lịch sử. Tạo và hủy meter liên tục làm tăng churn, gây khó cho truy vấn và tiêu tốn chi phí ingest.

### Ưu tiên metric tổng hợp khi có thể

Nếu chỉ cần số worker đang hoạt động toàn hệ thống, một Gauge tổng hợp thường đủ:

~~~java
@Component
public class WorkerFleetMetrics {

    private final AtomicInteger activePools = new AtomicInteger();

    public WorkerFleetMetrics(MeterRegistry registry) {
        Gauge.builder(
                "worker.pools.active",
                activePools,
                AtomicInteger::get
            )
            .description("Number of active worker pools")
            .register(registry);
    }

    public void poolStarted() {
        activePools.incrementAndGet();
    }

    public void poolStopped() {
        activePools.decrementAndGet();
    }
}
~~~

Một meter theo dõi tổng số pool đang hoạt động có cardinality ổn định, bất kể pool được tạo và hủy bao nhiêu lần. Cần bảo đảm mỗi pool chỉ gọi start/stop một lần và không để giá trị âm khi có lỗi lifecycle.

Nếu cần phân loại, dùng tag như pool.type hoặc role với tập giá trị hữu hạn. Không dùng pool.id động trừ khi số pool được giới hạn và việc xem từng pool là yêu cầu rõ ràng.

## API gỡ meter khỏi registry

Micrometer MeterRegistry cung cấp các thao tác remove theo meter hoặc Meter.Id và thao tác clear cho toàn registry. Trong quản lý tài nguyên động, nên gỡ đúng meter do tài nguyên sở hữu.

~~~java
registry.remove(meter);
registry.remove(meter.getId());
~~~

Giữ reference meter khi đăng ký giúp việc gỡ chính xác và tránh phải dựng lại tên/tag ở thời điểm đóng tài nguyên. Nếu chỉ giữ Meter.Id, cần bảo đảm ID được lấy từ chính meter đã đăng ký và thuộc đúng registry.

### Remove khác với clear

| API | Phạm vi | Trường hợp sử dụng |
|---|---|---|
| remove(meter) | Một meter cụ thể | Đóng một tài nguyên sở hữu meter đó |
| remove(meter.getId()) | Meter có danh tính tương ứng | Gỡ meter khi chỉ lưu Meter.Id |
| clear() | Toàn bộ meter trong registry | Chỉ dùng khi thực sự muốn reset toàn registry trong test hoặc lifecycle riêng |

Không gọi clear() để dọn một worker pool. Registry dùng chung có thể chứa JVM, HTTP, database pool, cache và metrics nghiệp vụ của nhiều component. Clear có thể xóa cả những meter mà tài nguyên đang hoạt động khác cần.

### MeterFilter không thay thế remove

MeterFilter quyết định meter có được chấp nhận hoặc biến đổi khi đăng ký. Filter không phải cơ chế dọn meter đã tồn tại theo vòng đời tài nguyên.

Các giới hạn cardinality như maximumAllowableMetrics hoặc maximumAllowableTags cũng không tự quản lý thời điểm tài nguyên đóng. Chúng là hàng rào bảo vệ khi đăng ký meter mới, không phải thay thế cho cleanup.

## Quản lý meter bằng một handle sở hữu rõ ràng

### Một handle cho mỗi tài nguyên

Có thể tạo một object đại diện cho các meter thuộc về một tài nguyên. Handle giữ registry, meter references, nguồn Gauge và trạng thái đóng. Khi tài nguyên dừng, handle thực hiện cleanup đúng một lần.

Ví dụ worker pool có số lượng giới hạn và tên thuộc nhóm cấu hình:

~~~java
public final class WorkerPoolMetrics implements AutoCloseable {

    private final MeterRegistry registry;
    private final Counter completed;
    private final Gauge activeGauge;
    private final AtomicInteger activeWorkers = new AtomicInteger();

    private boolean closed;

    public WorkerPoolMetrics(
            MeterRegistry registry,
            String poolName
    ) {
        this.registry = registry;

        this.completed = Counter.builder("worker.tasks.completed")
            .tag("pool", poolName)
            .register(registry);

        this.activeGauge = Gauge.builder(
                "worker.active",
                activeWorkers,
                AtomicInteger::get
            )
            .tag("pool", poolName)
            .register(registry);
    }

    public synchronized void taskCompleted() {
        if (!closed) {
            completed.increment();
        }
    }

    public synchronized void updateActiveWorkers(int count) {
        if (!closed) {
            activeWorkers.set(count);
        }
    }

    @Override
    public synchronized void close() {
        if (closed) {
            return;
        }

        closed = true;
        registry.remove(completed);
        registry.remove(activeGauge);
    }
}
~~~

Handle sở hữu hai meter và nguồn dữ liệu của Gauge. close() idempotent nên gọi nhiều lần cũng không lặp cleanup. Các method ghi nhận đồng bộ với close() trong ví dụ để không có lần ghi mới sau khi meter bị remove.

Đồng bộ bằng synchronized giúp minh họa thứ tự lifecycle rõ ràng, nhưng lock có thể ảnh hưởng hot path nếu record được gọi với tần suất rất cao. Trong hệ thống tải lớn, có thể dùng giao thức dừng nhận việc và drain các writer đang chạy trước khi gọi close(), thay vì khóa từng lần ghi. Dù chọn cách nào, phải bảo đảm không còn writer sử dụng meter sau khi cleanup hoàn tất.

Tên poolName trong ví dụ phải thuộc tập giá trị giới hạn. Nếu poolName được tạo tự do với hàng nghìn hoặc hàng triệu giá trị, hãy chuyển sang meter tổng hợp hoặc tag theo pool type/role.

### Quản lý handle ở nơi tạo tài nguyên

Component tạo worker pool cũng nên sở hữu handle metrics tương ứng:

~~~java
public final class ManagedWorkerPool implements AutoCloseable {

    private final ExecutorService executor;
    private final WorkerPoolMetrics metrics;

    public ManagedWorkerPool(
            MeterRegistry registry,
            String poolName,
            int threads
    ) {
        this.executor = Executors.newFixedThreadPool(threads);
        this.metrics = new WorkerPoolMetrics(registry, poolName);
    }

    public void submit(Runnable task) {
        executor.submit(() -> {
            try {
                task.run();
            } finally {
                // Cap nhat trang thai theo lifecycle thuc te.
            }
        });
    }

    @Override
    public void close() {
        executor.shutdown();
        try {
            if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                executor.shutdownNow();
                if (!executor.awaitTermination(30, TimeUnit.SECONDS)) {
                    throw new IllegalStateException(
                        "Worker pool did not terminate; metrics remain registered"
                    );
                }
            }
            metrics.close();
        } catch (InterruptedException ex) {
            executor.shutdownNow();
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Interrupted while draining worker pool; metrics remain registered",
                ex
            );
        }
    }
}
~~~

Đoạn mã minh họa quan hệ sở hữu và chờ executor drain. Nếu hết thời gian chờ hoặc thread đóng bị interrupt, close ném lỗi và giữ meter đã đăng ký để task còn chạy không ghi vào meter đã bị remove. Chủ sở hữu cần xử lý tình trạng shutdown chưa hoàn tất rồi gọi lại cleanup sau khi executor đã terminated. Trong hệ thống thực tế, thời hạn chờ và chính sách shutdownNow phải phù hợp với loại công việc.

Nếu executor không thể drain trong thời gian cho phép, cần quyết định rõ có bỏ qua metrics của task còn lại hay giữ meter cho đến khi task kết thúc. Không để handle đóng trong khi callback vẫn tiếp tục cập nhật meter.

## Đồng bộ cleanup với các lần ghi đang diễn ra

### Tránh race giữa record và remove

Một race condition có thể xảy ra:

1. Thread A kiểm tra tài nguyên còn hoạt động.
2. Thread B đóng tài nguyên và remove meter.
3. Thread A tiếp tục increment trên reference cũ.

Meter object đã bị remove vẫn có thể còn được giữ bởi reference trong Thread A. Việc gọi increment trên reference đó không tự đăng ký lại meter vào registry, nhưng measurement có thể không còn được scrape/export. Điều này tạo khoảng trống hoặc mất số liệu cuối.

Cần có giao thức lifecycle:

- Ngừng nhận công việc mới.
- Đánh dấu tài nguyên đang đóng.
- Chờ các writer đang chạy hoàn tất.
- Ghi nhận các số liệu cuối cùng cần thiết.
- Remove meter.
- Xóa các reference không còn cần thiết.

Có thể dùng lock, reference count, Phaser, structured task lifecycle hoặc cơ chế drain sẵn có của executor. Chọn giải pháp theo concurrency model của tài nguyên.

### Không để cleanup làm hỏng nghiệp vụ

Metrics là telemetry. Nếu cleanup thất bại hoặc meter đã bị remove, không nên làm hỏng thao tác đóng tài nguyên hoặc giao dịch nghiệp vụ chính.

Ghi log hoặc tăng một metric tổng hợp về lỗi cleanup nếu cần. Không tạo một meter mới cho từng lỗi cleanup vì điều đó có thể làm tăng cardinality đúng lúc hệ thống đang gặp vấn đề.

## Gauge và thời gian sống của object nguồn

Gauge thường đọc giá trị từ object được đăng ký và Micrometer giữ weak reference đến object nguồn. Điều này giúp registry không giữ toàn bộ object nghiệp vụ sống mãi, nhưng cũng có nghĩa ứng dụng phải giữ strong reference trong thời gian Gauge cần hoạt động.

Trong handle ví dụ, field activeWorkers giữ object nguồn sống trong suốt vòng đời handle. Khi handle đóng, registry.remove(activeGauge) gỡ Gauge; sau đó handle và nguồn AtomicInteger có thể được giải phóng nếu không còn tham chiếu khác.

Không nên đăng ký Gauge bằng một object tạm thời rồi để nó mất tham chiếu:

~~~java
Gauge.builder(
        "worker.active",
        new AtomicInteger(0),
        AtomicInteger::get
    )
    .register(registry);
~~~

Object được truyền vào có thể bị garbage collection vì không còn strong reference. Gauge khi đó có thể trả về giá trị không còn hữu ích.

Không dùng supplier Gauge để thực hiện database query hoặc network call. Khi registry scrape hoặc export, callback có thể được gọi ngoài dự kiến; một callback chậm vừa tăng chi phí thu thập vừa tạo tải phụ lên dependency.

## Tài nguyên động có cùng Meter.Id

### Hai chủ sở hữu không nên remove meter dùng chung

Nếu hai handle đăng ký meter cùng tên và cùng tag trong một registry, registry có thể trả về cùng meter. Khi một handle đóng và remove meter đó, handle còn lại có thể mất meter khỏi registry dù tài nguyên thứ hai vẫn hoạt động.

Vì vậy, meter có lifecycle riêng cần có một chủ sở hữu rõ ràng. Tránh nhiều resource handle cùng sở hữu cùng Meter.Id.

Nếu nhiều tài nguyên thực sự cần cập nhật cùng một meter tổng hợp, hãy tạo một component metrics trung tâm sở hữu meter đó. Các tài nguyên gọi component trung tâm để ghi nhận; không để từng resource tự remove meter chung.

Nếu bắt buộc chia sẻ meter giữa nhiều owner, cần quản lý reference count hoặc lifecycle trung tâm: chỉ remove khi owner cuối cùng đã kết thúc. Cách đơn giản và an toàn hơn thường là một owner duy nhất.

### Không tái sử dụng ID một cách tùy tiện

Khi một tài nguyên đóng và tài nguyên mới dùng lại cùng tên/tag, meter mới có thể được tạo với giá trị bắt đầu lại. Backend có thể quan sát một khoảng trống hoặc một lần reset tùy cách scrape/export và temporality.

Counter nên được hiểu là tích lũy trong vòng đời meter/series. Nếu mục tiêu là tổng số sự kiện xuyên suốt nhiều vòng đời tài nguyên, hãy dùng meter tổng hợp sống lâu thay vì remove và tạo lại counter theo từng resource.

## Ảnh hưởng của remove đến backend

Remove một meter khỏi registry ngăn registry công bố meter đó trong các lần scrape/export tiếp theo. Tuy nhiên, lịch sử đã gửi đến backend vẫn chịu retention và semantics của backend.

Với Prometheus pull, series không còn xuất hiện ở lần scrape thành công tiếp theo có thể được đánh dấu stale theo quy tắc của Prometheus. Dữ liệu lịch sử vẫn có thể được truy vấn trong retention window.

Với OTLP push hoặc backend khác, dữ liệu đã gửi thường được giữ theo chính sách retention của backend. Registry.remove không phải API xóa time series từ xa. Không giả định rằng meter bị remove sẽ xóa ngay dashboard hoặc dữ liệu lịch sử.

Khi tạo lại cùng metric name và label set, backend có thể tiếp tục nhìn thấy cùng series identity nhưng giá trị counter bắt đầu lại. Hãy kiểm tra cách backend xử lý khoảng trống, reset, start timestamp và temporality trước khi diễn giải rate/increase.

## Nhiều registry và CompositeMeterRegistry

Một ứng dụng có thể xuất meter tới nhiều backend. Khi dùng CompositeMeterRegistry hoặc nhiều registry độc lập, cần xác định meter được đăng ký và remove ở registry nào.

Không giả định rằng giữ một Meter reference ở một registry tùy chỉnh rồi remove sẽ tự động dọn mọi registry khác. Hành vi của composite và registry thành phần phụ thuộc cách chúng được kết nối và phiên bản Micrometer.

Các nguyên tắc thực tế:

- Dùng cùng một lifecycle owner cho meter được xuất đến nhiều backend.
- Xác định registry nào sở hữu meter và reference dùng để remove.
- Kiểm tra meter còn tồn tại trong registry thành phần sau cleanup.
- Không gọi clear() trên registry dùng chung chỉ để dọn một resource.
- Kiểm thử hành vi remove với đúng loại registry triển khai.

Nếu một backend còn hiển thị dữ liệu sau khi registry khác đã remove, đó có thể là khác biệt về thời điểm export hoặc retention, không nhất thiết là remove thất bại.

## Khi nào không nên remove meter?

Không phải meter nào cũng nên bị gỡ khi một object kết thúc. Meter của JVM, HTTP server, connection pool ứng dụng hoặc service-level business Counter thường thuộc vòng đời ứng dụng và cần tồn tại lâu hơn một request hoặc một tài nguyên ngắn hạn.

Chỉ remove khi meter thực sự thuộc tài nguyên có vòng đời riêng và việc giữ nó sau khi resource đóng không còn giá trị.

Một số trường hợp nên giữ meter tổng hợp:

- Tổng số job hoàn tất trong service.
- Tổng số lỗi theo loại operation.
- Số queue đang hoạt động.
- Tổng throughput của worker fleet.
- Timer theo operation type thay vì theo từng worker instance.

Nếu cần quan sát lịch sử một resource đã đóng, cân nhắc lưu sự kiện hoặc metadata vào hệ thống phù hợp. Metrics không phải kho lưu trữ vòng đời tài nguyên chi tiết.

## Kiểm thử cleanup với SimpleMeterRegistry

Có thể dùng SimpleMeterRegistry để xác minh meter xuất hiện khi tạo handle và biến mất sau close:

~~~java
@Test
void removesMetersWhenResourceCloses() {
    SimpleMeterRegistry registry = new SimpleMeterRegistry();

    WorkerPoolMetrics metrics =
        new WorkerPoolMetrics(registry, "critical");

    metrics.taskCompleted();

    assertThat(registry.find("worker.tasks.completed")
        .tag("pool", "critical")
        .counter()).isNotNull();

    metrics.close();

    assertThat(registry.find("worker.tasks.completed")
        .tag("pool", "critical")
        .counter()).isNull();

    assertThat(registry.find("worker.active")
        .tag("pool", "critical")
        .gauge()).isNull();
}
~~~

Test này xác minh registry không còn trả về meter sau cleanup. Có thể bổ sung test gọi close hai lần để xác nhận idempotency và test rằng các registry khác trong ứng dụng vẫn giữ meter của chúng.

### Kiểm thử race giữa writer và close

Với tài nguyên đồng thời, tạo nhiều writer và đóng resource trong khi workload đang chạy. Kết quả cần xác minh:

- Không có writer mới sau khi resource chuyển sang trạng thái closing.
- Các writer đã bắt đầu được drain hoặc kết thúc theo chính sách.
- Không có exception làm hỏng nghiệp vụ do meter đã remove.
- Cleanup chỉ xảy ra sau khi không còn writer hợp lệ.
- Meter không bị đăng ký lại ngoài ý muốn.
- Các meter không thuộc resource vẫn tồn tại.

Dùng CountDownLatch, Phaser hoặc công cụ đồng bộ trong test để điều khiển thứ tự. Tránh phụ thuộc Thread.sleep vì khó tái hiện race ổn định.

### Kiểm thử cardinality và churn

Chạy một chu kỳ tạo/đóng nhiều resource trong registry cô lập. Kiểm tra số meter sau mỗi giai đoạn:

1. Tạo N resource có danh tính hợp lệ.
2. Xác nhận số meter tăng theo số resource dự kiến.
3. Đóng toàn bộ resource.
4. Xác nhận meter động được remove.
5. Xác nhận meter tổng hợp và meter ứng dụng vẫn tồn tại.
6. Lặp lại chu kỳ để phát hiện meter bị rò rỉ hoặc đăng ký trùng.

Ngoài số meter trong registry, kiểm tra số series và kích thước payload ở exporter/backend nếu mục tiêu là đánh giá toàn bộ pipeline.

## Những sai lầm thường gặp

**Nghĩ rằng object bị garbage collection thì meter tự mất.** Registry quản lý meter độc lập với vòng đời object nghiệp vụ. Gỡ meter rõ ràng khi resource đóng.

**Gọi clear() để dọn một resource.** clear() có thể xóa meter của mọi component dùng chung registry. Remove đúng meter do resource sở hữu.

**Remove trước khi writer kết thúc.** Reference cũ vẫn có thể được cập nhật sau khi meter bị gỡ, làm mất measurement cuối. Dừng nhận việc và drain writer trước cleanup.

**Tạo meter riêng cho mỗi request hoặc user.** Cardinality và churn tăng rất nhanh. Dùng meter tổng hợp với tag hữu hạn.

**Để nhiều handle sở hữu cùng Meter.Id.** Một handle remove có thể ảnh hưởng handle khác. Dùng owner duy nhất hoặc lifecycle/reference count trung tâm.

**Giữ Gauge source bằng biến cục bộ.** Weak reference có thể khiến object bị thu hồi. Giữ strong reference trong handle hoặc component sống đủ lâu.

**Cho rằng remove xóa dữ liệu backend.** Remove chỉ ảnh hưởng registry local; backend giữ lịch sử theo retention riêng.

**Dùng MeterFilter thay cho cleanup.** Filter chủ yếu áp dụng khi đăng ký; nó không dọn meter đã tồn tại theo lifecycle.

**Remove Counter service-level khi một worker kết thúc.** Counter tổng hợp thuộc vòng đời service, không thuộc worker riêng. Chọn đúng owner cho từng meter.

**Không kiểm thử composite registry.** Registry thành phần có thể có lifecycle khác. Xác minh remove trên đúng cấu hình triển khai.

## Checklist quản lý vòng đời meter

Trước khi tạo meter cho tài nguyên động, hãy xác minh:

1. Tài nguyên có số lượng hữu hạn và thật sự cần meter riêng không?
2. Có thể dùng metric tổng hợp với tag hữu hạn thay thế không?
3. Meter có owner duy nhất và lifecycle rõ ràng không?
4. Handle có giữ Meter reference hoặc Meter.Id để remove chính xác không?
5. Tài nguyên có ngừng nhận việc mới trước khi cleanup không?
6. Writer đang chạy có được drain trước remove không?
7. close() có idempotent và không làm hỏng nghiệp vụ không?
8. Gauge source có strong reference trong suốt vòng đời cần đo không?
9. Meter dùng chung có nguy cơ bị một owner khác remove không?
10. Chỉ remove meter của resource, không clear toàn registry, đúng không?
11. Đã xác minh hành vi với registry/composite thực tế chưa?
12. Đã hiểu remove không xóa lịch sử backend và có thể tạo counter reset/churn chưa?
13. Test có bao phủ cleanup, race, cardinality và lặp create/close không?

## Kết luận

Meter của tài nguyên động cần có lifecycle owner rõ ràng. Đăng ký khi resource được tạo, cập nhật trong thời gian hoạt động, ngừng writer và drain công việc trước khi remove từng meter bằng reference hoặc Meter.Id. Giữ Gauge source sống đủ lâu, không dùng clear() trên registry dùng chung và không để nhiều owner cùng remove một Meter.Id.

Chỉ tạo meter riêng khi số tài nguyên được giới hạn và việc quan sát từng tài nguyên có giá trị. Với tài nguyên thay đổi liên tục, ưu tiên metrics tổng hợp và tag hữu hạn để giảm cardinality cùng series churn. Cuối cùng, nhớ rằng remove chỉ dừng công bố từ registry; dữ liệu lịch sử ở backend vẫn tuân theo retention và semantics riêng. Kiểm thử cả cleanup, concurrency và hành vi registry thực tế để bảo đảm meter không tồn tại lâu hơn tài nguyên mà nó đại diện.
