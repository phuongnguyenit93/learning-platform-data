# Kiểm chứng cùng một phép đo trên các registry có ngữ nghĩa công bố khác nhau

Micrometer giữ API đo lường tương đối nhất quán giữa các backend, nhưng mỗi `MeterRegistry` có thể công bố thời gian và số liệu tích lũy theo cách khác nhau. Có registry xuất count và tổng thời gian dưới dạng giá trị tích lũy; registry kiểu step có thể chuẩn hóa chênh lệch trong mỗi chu kỳ thành tốc độ trên giây. Ngoài ra, đơn vị thời gian cơ sở cũng phụ thuộc registry: một backend có thể dùng giây, backend khác dùng mili giây.

Vì vậy, khi kiểm chứng cùng một phép đo trên nhiều registry, không nên so sánh trực tiếp các con số thô trong output. Cần xác định ngữ nghĩa công bố, chuẩn hóa đơn vị và so sánh cùng một khoảng thời gian. `FunctionTimer` là ví dụ rõ nhất cho khác biệt này: nó quan sát hai hàm tích lũy từ nguồn dữ liệu, sau đó để registry quyết định cách biểu diễn phù hợp với backend.

## 1. Cùng một phép đo có thể có nhiều cách công bố

Giả sử một cache theo dõi số lần đọc và tổng thời gian đọc. Sau một thời gian hoạt động, nguồn dữ liệu có:

- Tổng số lần đọc: 1.000.
- Tổng thời gian đọc: 250 giây.

Một registry kiểu cumulative có thể công bố trực tiếp hai giá trị tích lũy đó. Một registry kiểu step với chu kỳ 10 giây có thể công bố tốc độ phát sinh trong chu kỳ vừa qua. Nếu trong 10 giây vừa rồi có 100 lần đọc và tổng thời gian đọc tăng thêm 25 giây, giá trị step-normalized tương ứng là:

| Đại lượng | Giá trị tích lũy | Chênh lệch trong 10 giây | Giá trị step-normalized |
|---|---:|---:|---:|
| Số lần đọc | 1.000 | 100 | 10 lần/giây |
| Tổng thời gian đọc | 250 giây | 25 giây | 2,5 giây/giây |
| Thời gian trung bình mỗi lần đọc | 250 ms | 25 giây / 100 lần | 250 ms |

Các con số tích lũy và step-normalized khác nhau, nhưng cùng mô tả một nguồn hoạt động. Khi lấy tỷ lệ tổng thời gian trên số lần đọc, cả hai cách biểu diễn đều cho thời gian trung bình 250 ms.

Đây là lý do cần phân biệt **giá trị nguồn**, **đơn vị công bố** và **cửa sổ thời gian**. Nếu chỉ nhìn vào con số 10 hoặc 1.000 mà không biết registry đang xuất rate hay cumulative count, rất dễ diễn giải sai throughput.

## 2. Registry quyết định base time unit

Các API Timer có overload nhận `TimeUnit` khi ghi hoặc đọc thời gian; cũng có thể truyền `Duration` khi ghi. Timer tự chuyển đổi giá trị sang đơn vị cơ sở mà registry sử dụng khi công bố.

Các API quan trọng:

~~~java
timer.record(250, TimeUnit.MILLISECONDS);
timer.record(Duration.ofMillis(250));

double millis = timer.totalTime(TimeUnit.MILLISECONDS);
double seconds = timer.totalTime(TimeUnit.SECONDS);
TimeUnit publishedUnit = timer.baseTimeUnit();
~~~

Ví dụ, cùng một thời lượng 250 ms có thể được biểu diễn thành:

| Đơn vị đọc | Giá trị tương đương |
|---|---:|
| Nanoseconds | 250.000.000 |
| Microseconds | 250.000 |
| Milliseconds | 250 |
| Seconds | 0,25 |

Giá trị được ghi vào Timer vẫn là cùng một thời lượng. Registry chỉ chọn đơn vị cơ sở phù hợp với hệ thống nhận.

Không giả định tất cả registry đều dùng giây hoặc mili giây. Hãy đọc `baseTimeUnit()` từ meter cụ thể hoặc gọi `totalTime(TimeUnit)` với đơn vị chung khi cần so sánh. Với `FunctionTimer`, quy tắc tương tự áp dụng cho `totalTime(TimeUnit)` và `baseTimeUnit()`.

Đơn vị của nguồn dữ liệu cũng cần khai báo chính xác. Khi tạo FunctionTimer, tham số `totalTimeFunctionUnit` mô tả đơn vị mà hàm tổng thời gian trả về. Nó không phải đơn vị đầu ra của registry.

## 3. Timer ghi nhận sự kiện; FunctionTimer quan sát bộ tích lũy

Hai loại meter có mục đích gần nhau nhưng lấy dữ liệu theo cách khác:

| Đặc điểm | Timer | FunctionTimer |
|---|---|---|
| Nguồn dữ liệu | Ứng dụng ghi từng lần thực thi | Một object cung cấp hàm count và tổng thời gian tích lũy |
| Cách cập nhật | Gọi `record()`, `recordCallable()` hoặc dừng `Timer.Sample` | Micrometer đọc các hàm nguồn khi cần |
| Dữ liệu yêu cầu | Thời lượng từng lần thực thi | Count và total time đã tích lũy |
| Tính đơn điệu | Timer quản lý số lần và tổng thời gian | Ứng dụng phải bảo đảm hai hàm nguồn không giảm |
| Trường hợp phù hợp | Mã ứng dụng kiểm soát trực tiếp từng thao tác | Thư viện hoặc thành phần đã cung cấp bộ đếm và tổng thời gian tích lũy |

Nếu ứng dụng có thể đo từng thao tác, Timer thường là lựa chọn tự nhiên:

~~~java
Timer timer = Timer.builder("cache.get")
        .description("Cache lookup duration")
        .register(registry);

timer.record(() -> cache.get(key));
~~~

Nếu cache hoặc thư viện đã cung cấp tổng số lần gọi và tổng thời gian từ lúc khởi động, FunctionTimer có thể quan sát trực tiếp các hàm đó mà không cần ghi lại từng thao tác vào Timer.

Không dùng DistributionSummary thay cho Timer chỉ vì cả hai đều hỗ trợ phân phối. Timer tự xử lý đơn vị thời gian theo registry; DistributionSummary dành cho đại lượng số không phải thời gian.

## 4. FunctionTimer yêu cầu hai hàm tích lũy đơn điệu

FunctionTimer theo dõi:

1. Hàm count: tổng số lần sự kiện xảy ra.
2. Hàm total time: tổng thời gian của tất cả sự kiện.

Hai hàm phải giữ nguyên hoặc tăng theo thời gian, không được giảm. Micrometer không thể tự xác minh tính đơn điệu của nguồn dữ liệu; khi đăng ký FunctionTimer, ứng dụng cam kết rằng các hàm được cung cấp có ngữ nghĩa này.

Registry đọc count và total time qua hai hàm riêng. Trong hệ thống có cập nhật đồng thời, hai lần đọc có thể không xảy ra đúng cùng một thời điểm, nên một snapshot có thể có sai khác rất nhỏ giữa count và tổng thời gian. Đây là số đo vận hành để quan sát xu hướng, không phải bản ghi giao dịch dùng cho đối soát chính xác.

Ví dụ một nguồn dữ liệu:

~~~java
import java.util.concurrent.atomic.AtomicLong;

final class CacheGetStats {
    private final AtomicLong count = new AtomicLong();
    private final AtomicLong totalNanos = new AtomicLong();

    void record(long elapsedNanos) {
        if (elapsedNanos < 0) {
            throw new IllegalArgumentException("elapsedNanos must be non-negative");
        }

        count.incrementAndGet();
        totalNanos.addAndGet(elapsedNanos);
    }

    long count() {
        return count.get();
    }

    double totalNanos() {
        return totalNanos.get();
    }
}
~~~

Đăng ký FunctionTimer trên nguồn đó:

~~~java
CacheGetStats stats = new CacheGetStats();

FunctionTimer cacheGetTimer = FunctionTimer
        .builder(
                "cache.get.latency",
                stats,
                CacheGetStats::count,
                CacheGetStats::totalNanos,
                TimeUnit.NANOSECONDS
        )
        .description("Cache get operations and cumulative latency")
        .tags("cache", "catalog")
        .register(registry);
~~~

Tham số `TimeUnit.NANOSECONDS` cho biết `totalNanos()` trả về tổng thời gian tính bằng nanosecond. Registry sẽ chuyển đổi tổng thời gian sang base time unit của nó.

Nguồn dữ liệu phải có vòng đời đủ dài để registry đọc được. Không truyền một giá trị primitive hoặc wrapper bất biến như `Long` trực tiếp làm object quan sát rồi kỳ vọng giá trị tự thay đổi. Cũng không đăng ký lại cùng tên và tag với object mới để thay nguồn cũ; registry quản lý một meter cho mỗi định danh.

## 5. Vì sao count và total time phải đơn điệu?

Registry kiểu cumulative có thể xuất trực tiếp count và tổng thời gian của nguồn. Registry kiểu step cần so sánh giá trị mới với giá trị ở bước trước để tính chênh lệch.

Giả sử nguồn có:

| Mốc | Count tích lũy | Total time tích lũy |
|---|---:|---:|
| Đầu bước | 900 | 225 giây |
| Cuối bước | 1.000 | 250 giây |

Chênh lệch trong bước là 100 lần và 25 giây. Nếu nguồn bị reset về 0 ở giữa hai lần đọc, registry step có thể nhìn thấy một giá trị giảm và không thể suy ra số sự kiện thực tế đã xảy ra. Tương tự, nếu tổng thời gian bị thay bằng một giá trị nhỏ hơn, chênh lệch không còn phản ánh tổng thời gian mới phát sinh.

Không dùng FunctionTimer nếu nguồn dữ liệu reset bộ đếm theo ngày, theo batch hoặc mỗi khi reconnect mà không có cơ chế duy trì bộ tích lũy đơn điệu. Có thể dùng Timer để ghi từng sự kiện, hoặc tạo một bộ tích lũy đơn điệu ở tầng ứng dụng nếu cần quan sát tổng dài hạn.

## 6. Registry cumulative và registry step-normalized

Micrometer hỗ trợ các registry có cách xuất khác nhau. Một khác biệt quan trọng là cumulative so với step-normalized:

| Ngữ nghĩa | Registry cumulative | Registry kiểu step |
|---|---|---|
| Giá trị count | Tổng từ khi nguồn bắt đầu | Chênh lệch trong bước, chuẩn hóa thành rate |
| Tổng thời gian | Tổng tích lũy từ nguồn | Chênh lệch tổng thời gian trong bước, chuẩn hóa theo giây |
| Sau khi không có sự kiện | Giá trị tích lũy vẫn giữ nguyên | Rate của bước không có sự kiện có thể về 0 |
| Phía backend | Thường dùng hàm rate/increase để tính tốc độ hoặc delta | Giá trị đã được chuẩn hóa theo chu kỳ xuất |
| Điều cần kiểm tra | Reset nguồn và cách query | Step duration, thời điểm rollover và cách backend nhận rate |

`StepMeterRegistry` là lớp nền cho các registry xuất theo chu kỳ. Nó chuẩn hóa count và sum thành rate trên giây trong khoảng publishing interval. `StepFunctionTimer` được dùng để triển khai FunctionTimer cho nhóm registry này.

Không nên kết luận mọi backend push đều có cùng hành vi chỉ vì chúng dùng HTTP push hoặc gửi theo lịch. Hãy kiểm tra registry implementation và cấu hình thực tế. Một số registry cho phép chọn cumulative hoặc delta temporality; cách chuyển đổi phụ thuộc implementation.

## 7. Ví dụ cùng nguồn FunctionTimer trên hai registry

Một nguồn dữ liệu có thể được đăng ký riêng vào nhiều registry. Mỗi registry có meter riêng nhưng cùng đọc một object trạng thái:

~~~java
CacheGetStats stats = cache.getStats();

FunctionTimer prometheusTimer = FunctionTimer
        .builder(
                "cache.get.latency",
                stats,
                CacheGetStats::count,
                CacheGetStats::totalNanos,
                TimeUnit.NANOSECONDS
        )
        .tags("cache", "catalog")
        .register(prometheusRegistry);

FunctionTimer pushTimer = FunctionTimer
        .builder(
                "cache.get.latency",
                stats,
                CacheGetStats::count,
                CacheGetStats::totalNanos,
                TimeUnit.NANOSECONDS
        )
        .tags("cache", "catalog")
        .register(pushRegistry);
~~~

Trong ví dụ, hai registry dùng cùng tên, tag và nguồn dữ liệu. Prometheus registry thường công bố giá trị cumulative; registry kế thừa StepMeterRegistry công bố count và tổng thời gian theo rate/giây của bước. Cả hai đều biết tổng thời gian nguồn trả về bằng nanosecond và tự chuyển đổi sang đơn vị cơ sở của mình.

Không dùng chính đối tượng FunctionTimer của registry thứ nhất cho registry thứ hai. Meter thuộc registry nơi nó được đăng ký. Hãy đăng ký cùng nguồn dữ liệu vào từng registry, hoặc dùng CompositeMeterRegistry nếu muốn quản lý nhiều registry dưới một facade.

## 8. Diễn giải cùng một kết quả qua cumulative và step

Giả sử nguồn dữ liệu ghi nhận:

- 1.000 lần đọc từ lúc khởi động.
- Tổng thời gian đọc 250 giây từ lúc khởi động.
- Trong bước 10 giây vừa qua, có thêm 100 lần đọc.
- Trong cùng bước, tổng thời gian tăng thêm 25 giây.

Registry cumulative có thể biểu diễn:

| Measurement | Giá trị |
|---|---:|
| Count | 1.000 lần |
| Total time | 250 giây |
| Mean | 250 ms/lần |

Registry step có thể biểu diễn:

| Measurement | Giá trị |
|---|---:|
| Count rate | 10 lần/giây |
| Total time rate | 2,5 giây/giây |
| Mean | 250 ms/lần |

Để kiểm tra hai registry, hãy chuyển các giá trị về cùng ý nghĩa:

- Count cumulative cần lấy chênh lệch giữa hai mốc nếu muốn so với count của một step.
- Count step rate cần nhân với thời lượng step để ước tính số lần trong step.
- Total time cumulative cần lấy chênh lệch nếu muốn so với step.
- Total time step rate cần nhân với thời lượng step để ước tính tổng thời gian trong step.
- Mean duration có thể so sánh trực tiếp sau khi quy đổi về cùng TimeUnit.

Không so sánh count tích lũy 1.000 với count rate 10 lần/giây rồi kết luận một registry mất dữ liệu. Chúng đang biểu diễn hai đại lượng khác nhau.

## 9. Chuẩn hóa đơn vị trước khi so sánh

Với Timer hoặc FunctionTimer, hãy dùng API đọc có tham số đơn vị:

~~~java
double totalMillis = functionTimer.totalTime(TimeUnit.MILLISECONDS);
double totalSeconds = functionTimer.totalTime(TimeUnit.SECONDS);
TimeUnit baseUnit = functionTimer.baseTimeUnit();
~~~

Khi so sánh:

~~~java
assertThat(timerA.totalTime(TimeUnit.MILLISECONDS))
        .isCloseTo(timerB.totalTime(TimeUnit.MILLISECONDS),
                within(1.0));
~~~

Đây là ví dụ so sánh hai Timer đo cùng một khoảng thời gian và cùng ngữ nghĩa cumulative. Nếu một meter là step-normalized, cần đưa dữ liệu về cùng cửa sổ trước khi so sánh.

Không đọc `Measurement.getValue()` rồi giả định mọi registry trả về cùng đơn vị. Với các meter thời gian, xem `baseTimeUnit()`, `getId().getBaseUnit()` và quy ước của exporter. Một số backend còn thêm hậu tố vào tên chuỗi thời gian, ví dụ `_seconds`; hậu tố tên không thay thế việc kiểm tra đơn vị thực tế.

## 10. Kiểm thử Timer với MockClock

`Timer.Sample` lấy thời điểm bắt đầu từ clock của registry. Dùng `MockClock` giúp kiểm thử thời lượng mà không phải chờ thời gian thực:

~~~java
MockClock clock = new MockClock();

SimpleMeterRegistry simpleRegistry =
        new SimpleMeterRegistry(SimpleConfig.DEFAULT, clock);

PrometheusMeterRegistry prometheusRegistry =
        new PrometheusMeterRegistry(PrometheusConfig.DEFAULT, clock);

Timer simpleTimer = Timer.builder("job.duration").register(simpleRegistry);
Timer prometheusTimer = Timer.builder("job.duration").register(prometheusRegistry);

Timer.Sample simpleSample = Timer.start(simpleRegistry);
Timer.Sample prometheusSample = Timer.start(prometheusRegistry);

clock.add(250, TimeUnit.MILLISECONDS);

simpleSample.stop(simpleTimer);
prometheusSample.stop(prometheusTimer);

assertThat(simpleTimer.totalTime(TimeUnit.MILLISECONDS))
        .isCloseTo(250.0, within(1.0));
assertThat(prometheusTimer.totalTime(TimeUnit.MILLISECONDS))
        .isCloseTo(250.0, within(1.0));
~~~

Hai Timer được tạo trong hai registry khác nhau nhưng dùng cùng clock giả. Cả hai sample đo cùng một khoảng 250 ms. Khi đọc, cả hai được quy đổi về milliseconds để phép so sánh có cùng đơn vị.

Kiểm thử này xác minh việc ghi và chuyển đổi thời gian ở lớp Micrometer. Nó chưa xác minh chuỗi dữ liệu cuối cùng của mọi exporter; với Prometheus, có thể kiểm tra thêm scrape output để xác nhận tên và đơn vị công bố.

## 11. Kiểm thử FunctionTimer với nguồn dữ liệu tích lũy

Có thể kiểm tra FunctionTimer bằng SimpleMeterRegistry:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
CacheGetStats stats = new CacheGetStats();

FunctionTimer timer = FunctionTimer
        .builder(
                "cache.get.latency",
                stats,
                CacheGetStats::count,
                CacheGetStats::totalNanos,
                TimeUnit.NANOSECONDS
        )
        .register(registry);

stats.record(TimeUnit.MILLISECONDS.toNanos(100));
stats.record(TimeUnit.MILLISECONDS.toNanos(150));

assertThat(timer.count()).isEqualTo(2.0);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
        .isCloseTo(250.0, within(1.0));
assertThat(timer.mean(TimeUnit.MILLISECONDS))
        .isCloseTo(125.0, within(1.0));
~~~

Kiểm thử này xác minh nguồn count và tổng thời gian được đọc đúng, đồng thời xác minh đơn vị nguồn nanosecond được chuyển đổi sang milliseconds. SimpleMeterRegistry là registry tối giản, phù hợp cho unit test và giữ giá trị trong bộ nhớ; nó không mô phỏng mọi hành vi xuất theo step của backend push.

## 12. Kiểm chứng registry step bằng clock và publishing interval

Đối với registry kế thừa StepMeterRegistry, kiểm thử cần xét đến ranh giới step:

1. Tạo registry với một MockClock và step duration cố định, ví dụ 10 giây.
2. Đăng ký FunctionTimer trên cùng nguồn dữ liệu tích lũy.
3. Ghi nhận một nhóm sự kiện và cập nhật count/total time của nguồn.
4. Di chuyển MockClock qua ranh giới step để registry rollover.
5. Xác minh count và total time được chuẩn hóa thành rate trên giây cho bước đã hoàn tất.
6. Không có sự kiện trong bước kế tiếp thì xác minh rate của bước mới có thể về 0.

Không kiểm thử step registry bằng cách đọc meter ngay sau khi ghi rồi mặc định giá trị đã rollover. Giá trị có thể thuộc bước hiện tại hoặc bước trước tùy clock và thời điểm publish. Hãy đồng bộ thời điểm kiểm thử với step boundary.

Nếu không muốn tự tạo test registry, hãy dùng implementation push thực tế và cấu hình step ngắn trong integration test. Cần kiểm soát clock, scheduler và publisher để kết quả có thể lặp lại.

## 13. Kiểm tra output của Prometheus

Prometheus thường nhận các chuỗi thời gian cumulative. Với Timer, registry Prometheus xuất thời lượng theo giây và các chuỗi count/sum tương ứng. Hãy kiểm tra endpoint scrape thay vì suy ra từ cách hiển thị trong log.

Ví dụ một Timer có tên logic `job.duration` có thể được biểu diễn thành các chuỗi như:

~~~text
job_duration_seconds_count
job_duration_seconds_sum
~~~

Với FunctionTimer, count và total time cũng được xuất theo định dạng Prometheus của registry. Khi cần throughput, dùng PromQL `rate()` hoặc `increase()` trên chuỗi cumulative:

~~~promql
rate(cache_get_latency_seconds_count[5m])
~~~

Tốc độ tổng thời gian tích lũy:

~~~promql
rate(cache_get_latency_seconds_sum[5m])
~~~

Thời gian trung bình trên mỗi lần gọi trong cửa sổ:

~~~promql
rate(cache_get_latency_seconds_sum[5m])
/
rate(cache_get_latency_seconds_count[5m])
~~~

Không áp dụng `rate()` lần nữa cho một giá trị mà registry đã chuẩn hóa thành rate mỗi giây. Với registry kiểu step, hãy dùng query phù hợp với loại dữ liệu đã xuất và hướng dẫn của backend.

## 14. Clock và thời gian trong kiểm thử

Micrometer dùng Clock của registry để đo thời gian và quản lý các cấu trúc phụ thuộc thời gian. `Timer.Sample` bắt đầu từ clock của registry; các registry step cũng dùng clock để xác định thời điểm rollover.

Một số nguyên tắc:

- Dùng cùng MockClock cho các registry khi muốn so sánh cùng một khoảng thời gian giả lập.
- Không dùng `Thread.sleep()` trong unit test để tạo khoảng thời gian đo; test sẽ chậm và phụ thuộc lịch hệ điều hành.
- Phân biệt thời gian trôi qua với thời điểm lịch. Khi đo duration, dùng Timer hoặc Sample thay vì tự lấy hiệu hai giá trị `System.currentTimeMillis()`.
- Khi kiểm thử registry step, điều khiển cả clock lẫn step boundary.
- Khi kiểm thử exporter push, tách việc ghi số đo khỏi việc chờ publisher và kiểm tra payload.

Clock giúp kiểm thử lặp lại, nhưng không thay thế kiểm thử tích hợp. Backend thực tế còn có chu kỳ scrape/push, quy tắc đặt tên, đơn vị và aggregation temporality riêng.

## 15. CompositeMeterRegistry và việc đọc giá trị thời gian

CompositeMeterRegistry cho phép một meter được phân phối tới nhiều registry con. Mỗi registry con có thể có base time unit và cách xuất riêng.

Khi cần so sánh hoặc đọc giá trị, nên truy vấn meter trên từng registry con và yêu cầu cùng đơn vị:

~~~java
Timer prometheusTimer = prometheusRegistry.get("job.duration").timer();
Timer otherTimer = otherRegistry.get("job.duration").timer();

double prometheusMillis = prometheusTimer.totalTime(TimeUnit.MILLISECONDS);
double otherMillis = otherTimer.totalTime(TimeUnit.MILLISECONDS);
~~~

Không giả định một giá trị `Measurement` thô lấy từ composite luôn có đơn vị giống nhau giữa các child registry. Với TimeGauge hoặc FunctionTimer, hãy dùng API đọc có đơn vị rõ ràng và kiểm tra base unit của từng meter.

Nếu cần xuất cùng một phép đo đến nhiều backend, CompositeMeterRegistry tiện cho instrumentation chung. Nhưng khi kiểm chứng kết quả, vẫn cần xem output của từng registry con vì chúng có thể dùng cumulative/step semantics, base unit và naming convention khác nhau.

## 16. Những lỗi thường gặp

**So sánh số thô giữa registry giây và registry mili giây.** Quy đổi về một TimeUnit chung trước khi so sánh.

**So sánh count cumulative với count rate.** Một bên là tổng từ lúc bắt đầu, bên kia là tốc độ của một step. Hãy quy về cùng cửa sổ thời gian.

**Dùng nguồn FunctionTimer có thể reset.** Step registry cần giá trị tăng đơn điệu để tính delta. Dùng Timer hoặc bộ tích lũy đơn điệu nếu nguồn có reset.

**Khai báo sai đơn vị totalTimeFunction.** Nếu nguồn trả về nanosecond nhưng khai báo MILLISECONDS, thời lượng sẽ sai lệch nhiều bậc độ lớn.

**Áp dụng rate hai lần.** Cumulative registry cần rate/increase ở backend như Prometheus; registry step có thể đã xuất rate mỗi giây.

**Đọc giá trị step trước rollover rồi kết luận bị mất dữ liệu.** Đồng bộ test với step boundary và publishing interval.

**Dùng Timer cho nguồn đã có bộ tích lũy count và total time nhưng không muốn ghi từng event.** FunctionTimer phù hợp với nguồn dữ liệu dạng này.

**Dùng FunctionTimer khi ứng dụng kiểm soát từng lần thực thi.** Timer thường đơn giản và ít giả định hơn.

**Đăng ký cùng FunctionTimer bằng object mới với cùng tên/tag.** Registry giữ meter đã đăng ký đầu tiên. Giữ một object thống kê ổn định và cập nhật chính object đó.

## 17. Checklist kiểm chứng giữa các registry

Trước khi kết luận hai registry công bố cùng một phép đo, hãy xác minh:

- [ ] Cả hai meter dùng cùng nguồn dữ liệu hoặc cùng một tập sự kiện.
- [ ] Tên và tag đại diện cho cùng ý nghĩa.
- [ ] Loại meter giống nhau hoặc có ngữ nghĩa tương đương.
- [ ] Đơn vị nguồn của FunctionTimer được khai báo chính xác.
- [ ] Base time unit của từng meter đã được xác định.
- [ ] Cumulative và step-normalized được phân biệt.
- [ ] Count và total time được đưa về cùng cửa sổ trước khi so sánh.
- [ ] Mean duration được quy đổi về cùng TimeUnit.
- [ ] Clock và step boundary được kiểm soát trong test.
- [ ] Scrape/push output đã được kiểm tra ở lớp exporter.
- [ ] Không áp dụng rate hai lần và không dùng tag cardinality cao.

## 18. Kết luận

Micrometer giữ API instrumentation thống nhất, nhưng registry quyết định base time unit và cách công bố dữ liệu. Với Timer, hãy ghi duration bằng TimeUnit rõ ràng và đọc lại bằng một đơn vị chung. Với FunctionTimer, cung cấp hai hàm count và total time tích lũy đơn điệu, đồng thời khai báo đúng đơn vị của tổng thời gian nguồn.

Registry cumulative có thể xuất tổng tích lũy; registry kiểu step có thể chuẩn hóa chênh lệch trong chu kỳ thành rate mỗi giây. Khi kiểm chứng cùng một phép đo, cần chuẩn hóa đơn vị và cửa sổ thời gian, kiểm soát clock/step boundary và kiểm tra output của exporter. Làm đúng các bước này giúp tránh nhầm lẫn giữa count với rate, giây với mili giây và giá trị tích lũy với số liệu theo chu kỳ.

## Tài liệu tham khảo

- [Micrometer – Timers and Function-tracking Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
- [Micrometer – Registry](https://docs.micrometer.io/micrometer/reference/concepts/registry.html)
- [Micrometer – Custom Meter Registry](https://docs.micrometer.io/micrometer/reference/guides/custom-meter-registry.html)
- [Micrometer – StepMeterRegistry API](https://javadoc.io/doc/io.micrometer/micrometer-core/latest/io/micrometer/core/instrument/step/package-summary.html)
