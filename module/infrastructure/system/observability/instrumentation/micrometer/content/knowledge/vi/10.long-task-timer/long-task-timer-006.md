# Đo tác vụ định kỳ, xử lý lô hoặc làm mới dữ liệu kéo dài

`LongTaskTimer` trong Micrometer dùng để quan sát những thao tác có thể chạy trong thời gian dài và vẫn đang thực thi tại thời điểm hệ thống thu thập metrics. Ví dụ gồm tác vụ đồng bộ dữ liệu, làm mới cache, xử lý batch, tạo báo cáo hoặc chạy một quy trình bảo trì.

Khác với `Timer`, vốn ghi nhận thời lượng sau khi thao tác kết thúc, `LongTaskTimer` cung cấp thông tin về các tác vụ đang hoạt động. Trong khi tác vụ chưa hoàn tất, hệ thống có thể biết có bao nhiêu tác vụ đang chạy, tổng thời gian đã trôi qua của chúng và thời gian của tác vụ đang chạy lâu nhất. Điều này giúp phát hiện một batch bị treo hoặc một lần làm mới dữ liệu kéo dài bất thường mà không cần chờ tác vụ kết thúc.

## 1. Khi nào cần LongTaskTimer?

Một Timer thông thường rất phù hợp để đo thời gian của một request hoặc một lời gọi dịch vụ. Nhưng với một tác vụ chạy vài phút hoặc vài giờ, nếu chỉ quan sát Timer, dashboard thường chưa có mẫu thời lượng cho đến khi tác vụ hoàn tất. Khi tác vụ bị kẹt, người vận hành có thể không thấy được thời gian đang trôi qua.

`LongTaskTimer` bổ sung góc nhìn trong khi công việc còn chạy. Nó hữu ích khi cần trả lời:

- Hiện có bao nhiêu lần chạy của tác vụ đang hoạt động?
- Các tác vụ đang hoạt động đã chạy tổng cộng bao lâu?
- Tác vụ nào đang chạy lâu nhất, xét theo thời lượng hiện tại?
- Một lần đồng bộ hoặc xử lý batch có vượt quá thời gian kỳ vọng không?
- Một lịch chạy định kỳ có bị chồng lấn vì lần trước chưa kết thúc không?

Các ví dụ phù hợp:

| Tác vụ | Thông tin cần theo dõi |
|---|---|
| Làm mới cache toàn hệ thống | Số lần refresh đang chạy và thời gian đã chạy |
| Đồng bộ dữ liệu từ hệ thống ngoài | Tác vụ đồng bộ nào đang kéo dài |
| Xử lý batch lớn | Có bao nhiêu batch đang thực thi, batch lâu nhất |
| Tạo báo cáo cuối ngày | Một lần tạo báo cáo đã chạy bao lâu |
| Tác vụ bảo trì định kỳ | Tác vụ có bị chồng lấn hoặc không kết thúc đúng hạn không |

Không cần dùng LongTaskTimer cho mọi hàm. Với thao tác ngắn và hoàn tất nhanh, Timer thường phù hợp hơn. Hãy chọn LongTaskTimer khi thời gian thực thi đang diễn ra là tín hiệu vận hành cần quan sát.

## 2. LongTaskTimer đo những gì?

LongTaskTimer theo dõi các sample đang hoạt động. Mỗi lần gọi `start()` tạo một sample đại diện cho một lần chạy. Khi sample được dừng, lần chạy đó không còn được tính là active.

Các thông tin chính gồm:

- `activeTasks()`: số sample hiện đang hoạt động.
- `duration(TimeUnit)`: tổng thời lượng đã trôi qua của các sample đang hoạt động, theo đơn vị được yêu cầu.
- `max(TimeUnit)`: thời lượng lớn nhất trong các sample đang hoạt động.

Ví dụ, nếu hai batch đang chạy được 30 giây và 50 giây:

| Chỉ số | Giá trị |
|---|---:|
| Active tasks | 2 |
| Tổng duration đang hoạt động | 80 giây |
| Max duration đang hoạt động | 50 giây |

Đây là các số đo tại thời điểm lấy mẫu. Khi batch 50 giây kết thúc, sample của nó được dừng; active task count giảm và max duration có thể trở thành thời lượng của batch còn lại. LongTaskTimer không giữ lịch sử thời lượng của các tác vụ đã kết thúc như một Timer thông thường.

Tổng duration đang hoạt động có thể lớn hơn thời gian thực của một khoảng đồng hồ khi có nhiều tác vụ chạy song song. Ví dụ, ba tác vụ cùng chạy 20 giây tạo ra tổng active duration khoảng 60 giây, trong khi thời gian thực đã trôi qua chỉ là 20 giây.

## 3. Đăng ký LongTaskTimer

Đăng ký meter bằng builder và giữ lại đối tượng để tái sử dụng:

~~~java
@Component
final class DataRefreshMetrics {
    private final LongTaskTimer refreshTimer;

    DataRefreshMetrics(MeterRegistry registry) {
        this.refreshTimer = LongTaskTimer.builder("data.refresh")
                .description("Time spent in active data refresh tasks")
                .register(registry);
    }

    LongTaskTimer.Sample startRefresh() {
        return refreshTimer.start();
    }
}
~~~

Tên `data.refresh` mô tả một loại thao tác ổn định. Không đưa thời điểm chạy, request ID hoặc ID batch vào tên meter. Nếu cần phân biệt một vài loại refresh, dùng tag có tập giá trị nhỏ, chẳng hạn `source=inventory` hoặc `source=pricing`.

Registry quản lý meter theo định danh. Vì vậy, nên đăng ký LongTaskTimer một lần khi khởi tạo component rồi dùng lại trong các lần chạy. Không tạo một registry mới hoặc meter mới cho mỗi batch.

## 4. Bắt đầu và kết thúc sample đúng cách

Khi tác vụ bắt đầu, gọi `start()`; khi tác vụ kết thúc, gọi `stop()`. Phải bảo đảm sample được dừng cả khi tác vụ ném exception:

~~~java
LongTaskTimer.Sample sample = refreshTimer.start();
try {
    refreshData();
} finally {
    sample.stop();
}
~~~

Khối `finally` là điểm quan trọng. Nếu chỉ dừng sample ở nhánh thành công, một exception có thể để lại tác vụ được báo cáo là đang chạy mãi dù công việc đã kết thúc. Khi đó active task count và duration sẽ sai.

Có thể đóng gói vòng đời sample trong component metrics để các caller dùng nhất quán:

~~~java
@Component
final class DataRefreshMetrics {
    private final LongTaskTimer refreshTimer;

    DataRefreshMetrics(MeterRegistry registry) {
        this.refreshTimer = LongTaskTimer.builder("data.refresh")
                .description("Time spent in active data refresh tasks")
                .register(registry);
    }

    void recordRefresh(Runnable operation) {
        LongTaskTimer.Sample sample = refreshTimer.start();
        try {
            operation.run();
        } finally {
            sample.stop();
        }
    }
}
~~~

Service gọi `recordRefresh(...)` cho đúng phần công việc cần đo:

~~~java
@Service
final class CatalogRefreshService {
    private final DataRefreshMetrics metrics;
    private final CatalogRepository repository;

    CatalogRefreshService(
            DataRefreshMetrics metrics,
            CatalogRepository repository) {
        this.metrics = metrics;
        this.repository = repository;
    }

    void refreshCatalog() {
        metrics.recordRefresh(() -> repository.refreshFromSource());
    }
}
~~~

Đoạn code minh họa dùng Runnable để làm rõ vòng đời. Nếu thao tác cần trả về kết quả, có thể tạo sample trong phương thức service và trả kết quả từ khối try, đồng thời vẫn gọi `stop()` trong finally.

## 5. Đo tác vụ định kỳ và phát hiện chồng lấn

Một tác vụ định kỳ có thể bắt đầu lần mới trước khi lần trước hoàn tất, tùy scheduler và cách cấu hình. LongTaskTimer giúp nhận biết tình huống này qua số lượng sample đang hoạt động.

Ví dụ:

~~~java
@Component
final class InventoryRefreshJob {
    private final LongTaskTimer timer;
    private final InventorySynchronizer synchronizer;

    InventoryRefreshJob(
            MeterRegistry registry,
            InventorySynchronizer synchronizer) {
        this.timer = LongTaskTimer.builder("inventory.refresh")
                .description("Active inventory refresh executions")
                .register(registry);
        this.synchronizer = synchronizer;
    }

    @Scheduled(fixedDelayString = "PT5M")
    void refresh() {
        LongTaskTimer.Sample sample = timer.start();
        try {
            synchronizer.refresh();
        } finally {
            sample.stop();
        }
    }
}
~~~

Nếu scheduler cho phép các lần chạy chồng lấn, `activeTasks()` có thể lớn hơn một. Điều này có thể là dấu hiệu lần chạy trước kéo dài hơn chu kỳ dự kiến, hoặc scheduler đang dùng nhiều thread. Nếu ứng dụng chỉ cho phép một lần chạy tại một thời điểm, active task count thường là 0 hoặc 1.

LongTaskTimer chỉ cho biết số lần chạy đang hoạt động; nó không tự ngăn chồng lấn. Nếu nghiệp vụ yêu cầu không chạy song song, cần cấu hình scheduler, khóa phân tán hoặc cơ chế điều phối phù hợp. Metrics giúp phát hiện và chẩn đoán, không thay thế cơ chế đồng bộ.

## 6. Đặt ranh giới đo phù hợp cho batch

Với một batch lớn, cần quyết định đo toàn bộ batch hay từng giai đoạn. Đo toàn bộ giúp thấy một lần xử lý có đang kéo dài hay không. Đo từng giai đoạn giúp tìm bước gây chậm.

Ví dụ batch gồm tải dữ liệu, kiểm tra, ghi dữ liệu:

~~~java
void executeBatch() {
    LongTaskTimer.Sample batch = batchTimer.start();
    try {
        loadInput();
        validateInput();
        persistOutput();
    } finally {
        batch.stop();
    }
}
~~~

Nếu cần biết riêng giai đoạn tải dữ liệu có bị treo hay không, có thể thêm một LongTaskTimer khác với tên ổn định như `batch.load`. Không nên tạo một timer cho từng record trong batch; việc đó làm số meter tăng và tạo thêm chi phí không cần thiết.

Khi một batch gồm nhiều worker chạy song song, hãy quyết định sample đại diện cho toàn bộ batch hay từng worker. Nếu đo cả batch lẫn worker, đặt tên khác nhau để người đọc không nhầm tổng duration của worker với thời lượng thực của batch.

## 7. Xử lý tác vụ bất đồng bộ và executor

Với tác vụ được đưa vào executor, thời điểm bắt đầu đo nên là lúc worker thực sự bắt đầu chạy, không phải lúc submit công việc vào hàng đợi.

~~~java
executor.submit(() -> {
    LongTaskTimer.Sample sample = taskTimer.start();
    try {
        processBatch();
    } finally {
        sample.stop();
    }
});
~~~

Nếu start sample trước `submit()`, thời gian chờ trong executor queue cũng bị tính là thời gian tác vụ đang hoạt động, mặc dù worker chưa bắt đầu xử lý. Nếu muốn quan sát thời gian chờ, hãy đo riêng bằng một meter cho queue wait hoặc theo dõi độ sâu hàng đợi bằng Gauge.

Với tác vụ bất đồng bộ trả về `CompletableFuture`, sample phải sống đến khi công việc thực sự hoàn tất:

~~~java
CompletableFuture<Void> refreshAsync() {
    LongTaskTimer.Sample sample = refreshTimer.start();

    try {
        return synchronizer.refreshAsync()
                .whenComplete((result, error) -> sample.stop());
    } catch (RuntimeException error) {
        sample.stop();
        throw error;
    }
}
~~~

`whenComplete` chạy khi future hoàn tất thành công hoặc thất bại nên sample được dừng trong cả hai trường hợp. Khối catch xử lý trường hợp phương thức tạo future ném lỗi đồng bộ trước khi trả về.

Nếu future có thể bị cancel, cần xác minh cancellation thực sự dẫn đến completion callback. Với executor hoặc API bất đồng bộ tùy chỉnh, hãy bảo đảm mọi đường kết thúc — thành công, exception, timeout và cancellation — đều dừng sample đúng một lần.

Không gọi `stop()` ngay sau khi tạo future nếu tác vụ vẫn đang chạy. Làm vậy sẽ khiến LongTaskTimer ngừng quan sát quá sớm.

## 8. Phân biệt LongTaskTimer và Timer

Hai meter có mục tiêu bổ sung cho nhau:

| Đặc điểm | Timer | LongTaskTimer |
|---|---|---|
| Thời điểm ghi nhận | Khi thao tác hoàn tất | Trong khi thao tác đang chạy |
| Số lần thực thi | Count của các lần đã ghi | Số sample đang hoạt động |
| Thời lượng | Thời lượng các lần đã hoàn tất | Thời lượng hiện tại của các lần đang chạy |
| Phân bố thời lượng lịch sử | Có thể cấu hình histogram/percentile | Không phải mục đích chính |
| Phát hiện tác vụ bị treo | Thường phải chờ tác vụ kết thúc mới có mẫu | Có thể quan sát duration đang tăng |
| Ví dụ | Thời gian một request HTTP | Batch đồng bộ đang chạy 20 phút |

Nếu cần cả hai góc nhìn, có thể ghi nhận cùng một thao tác bằng hai meter có tên khác nhau: LongTaskTimer để theo dõi trạng thái active và Timer để lưu thời lượng sau khi hoàn tất. Chỉ làm vậy khi cả hai câu hỏi đều cần thiết; tránh tạo các meter trùng ý nghĩa.

Ví dụ:

~~~java
LongTaskTimer.Sample active = longTaskTimer.start();
Timer.Sample completed = Timer.start(registry);

try {
    refreshData();
} finally {
    active.stop();
    completed.stop(completedTimer);
}
~~~

Trong ví dụ này, LongTaskTimer cung cấp thông tin trong khi refresh đang chạy. Timer ghi nhận thời lượng hoàn chỉnh khi khối finally chạy. Nếu tác vụ thất bại, Timer vẫn ghi thời lượng của lần thực thi; có thể phân loại kết quả bằng tag hữu hạn hoặc meter riêng nếu cần phân biệt success/failure.

## 9. Quan sát duration và active tasks trong dashboard

LongTaskTimer cung cấp các phép đo đang hoạt động cho registry xuất dữ liệu. Tên và cấu trúc chuỗi thời gian cụ thể phụ thuộc backend và naming convention. Khi dùng Prometheus hoặc hệ thống khác, hãy kiểm tra endpoint scrape hoặc dữ liệu nhận thực tế để biết tên metric được xuất.

Dashboard cho một tác vụ làm mới dữ liệu có thể hiển thị:

- Số lần refresh đang chạy.
- Tổng active duration của các lần refresh.
- Active duration lớn nhất.
- Timer hoàn tất để xem thời lượng của những lần refresh đã kết thúc.
- Counter riêng để đếm số lần refresh thành công hoặc thất bại.

Không diễn giải tổng active duration như thời gian thực của cả quy trình khi có nhiều lần chạy song song. Ví dụ, hai tác vụ cùng chạy 5 phút tạo tổng active duration khoảng 10 phút.

Một cảnh báo có thể dựa trên việc thời lượng đang hoạt động vượt ngưỡng kỳ vọng. Chẳng hạn, nếu refresh thường kết thúc trong 2 phút nhưng một sample đang hoạt động đã kéo dài 15 phút, đây là dấu hiệu cần điều tra. Ngưỡng cần dựa trên SLA, kích thước batch và biến động hợp lệ của dữ liệu.

## 10. Cardinality và tag

LongTaskTimer có thể được đăng ký với các tag có tập giá trị nhỏ:

~~~java
LongTaskTimer refresh = LongTaskTimer.builder("data.refresh")
        .tag("source", "inventory")
        .tag("mode", "full")
        .register(registry);
~~~

Tag như `source=inventory|pricing` hoặc `mode=full|incremental` hữu ích khi danh mục được giới hạn.

Không đưa task ID, batch ID, request ID, user ID hoặc timestamp vào tag. Một LongTaskTimer với một bộ tag mới cho mỗi lần chạy có thể tạo ra rất nhiều chuỗi thời gian. Nếu cần theo dõi một task cụ thể, hãy dùng log hoặc tracing với correlation ID phù hợp; metrics nên tổng hợp theo nhóm ổn định.

## 11. Kiểm thử LongTaskTimer

Có thể dùng `SimpleMeterRegistry` để kiểm tra số tác vụ đang hoạt động và việc dừng sample:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
LongTaskTimer timer = LongTaskTimer.builder("batch.execute")
        .register(registry);

LongTaskTimer.Sample sample = timer.start();

assertThat(timer.activeTasks()).isEqualTo(1);

sample.stop();

assertThat(timer.activeTasks()).isZero();
~~~

Kiểm thử đảm bảo sample được tạo khi bắt đầu và không còn active sau khi stop.

Nên kiểm tra thêm đường lỗi:

~~~java
LongTaskTimer.Sample sample = timer.start();
try {
    throw new IllegalStateException("batch failed");
} finally {
    sample.stop();
}
~~~

Trong test thực tế, bắt exception bên ngoài khối này rồi xác minh `activeTasks()` trở về 0. Điều đó xác nhận finally luôn dừng sample khi thao tác lỗi.

Các trường hợp nên bao phủ:

1. Một tác vụ bắt đầu làm active task count tăng lên một.
2. Nhiều tác vụ đồng thời làm count phản ánh số sample đang chạy.
3. Khi một tác vụ kết thúc, count giảm tương ứng.
4. Exception không để sample ở trạng thái active.
5. Future hoàn tất hoặc bị cancel đều dừng sample theo đúng lifecycle của API bất đồng bộ.
6. Tag không chứa ID động.

Không cần kiểm tra chính xác duration bằng cách so sánh với một số mili giây cố định trong unit test, vì lịch thực thi của test có thể thay đổi. Nếu cần kiểm tra duration, dùng khoảng thời gian rộng và xác minh đơn vị/giá trị theo cách ổn định.

## 12. Những lỗi thường gặp

**Dùng Timer cho tác vụ rất dài rồi chờ tác vụ hoàn tất mới xem được thời lượng.** Nếu cần thấy tác vụ đang chạy, dùng LongTaskTimer.

**Không dừng sample trong finally.** Exception có thể khiến tác vụ đã kết thúc vẫn bị báo cáo active. Luôn bảo đảm sample được stop ở mọi đường kết thúc.

**Bắt đầu sample lúc submit thay vì lúc worker chạy.** Thời gian chờ trong executor queue bị tính nhầm là thời gian thực thi. Start sample bên trong phần thân tác vụ.

**Dừng sample ngay sau khi tạo future.** Tác vụ vẫn chạy nhưng metrics không còn theo dõi. Dừng trong callback completion hoặc cơ chế tương đương.

**Cho rằng LongTaskTimer ngăn tác vụ chạy chồng lấn.** Nó chỉ quan sát số lần chạy active. Cần scheduler, lock hoặc cơ chế điều phối để kiểm soát concurrency.

**Diễn giải tổng duration như thời gian đồng hồ.** Nhiều sample chạy song song làm tổng duration lớn hơn thời gian thực. Dùng max duration nếu muốn xem lần chạy active lâu nhất.

**Dùng LongTaskTimer để lưu lịch sử thời lượng hoàn tất.** Khi sample dừng, nó không còn là active task. Dùng Timer nếu cần thống kê thời lượng các lần đã hoàn tất.

**Đưa ID từng tác vụ vào tag.** Điều này tạo cardinality cao. Dùng tag có tập giá trị nhỏ và log/trace cho định danh cụ thể.

## 13. Checklist triển khai

Trước khi dùng LongTaskTimer, hãy kiểm tra:

- [ ] Tác vụ đủ dài để cần quan sát khi còn đang chạy.
- [ ] Meter được đăng ký một lần và tái sử dụng.
- [ ] Mỗi lần chạy tạo đúng một sample.
- [ ] Sample được dừng trong finally hoặc callback hoàn tất tương đương.
- [ ] Với async, sample sống đến khi công việc thực sự kết thúc.
- [ ] Thời gian chờ trong executor queue được đo riêng nếu cần.
- [ ] Active task count được hiểu là số sample đang chạy, không phải số lần chạy lịch sử.
- [ ] Timer được dùng bổ sung nếu cần lịch sử thời lượng sau khi hoàn tất.
- [ ] Tag có cardinality thấp và không chứa task ID.
- [ ] Dashboard phân biệt tổng active duration và thời lượng lớn nhất.

## 14. Kết luận

LongTaskTimer giúp quan sát các tác vụ dài ngay khi chúng còn đang chạy. Mỗi lần thực thi bắt đầu một sample và phải dừng sample khi công việc kết thúc, kể cả khi có exception, timeout hoặc cancellation. Các số đo active task count, tổng active duration và max duration giúp nhận biết tác vụ kéo dài, chồng lấn hoặc có dấu hiệu bị kẹt.

Với tác vụ định kỳ, xử lý batch và làm mới dữ liệu, hãy đặt ranh giới sample đúng phần công việc thực sự được thực thi. Bắt đầu sample bên trong worker đối với tác vụ bất đồng bộ, giữ tag ở cardinality thấp và kết hợp Timer nếu cần phân bố thời lượng của các lần đã hoàn tất. Cách triển khai này cung cấp tín hiệu vận hành trong lúc chờ tác vụ hoàn thành.
