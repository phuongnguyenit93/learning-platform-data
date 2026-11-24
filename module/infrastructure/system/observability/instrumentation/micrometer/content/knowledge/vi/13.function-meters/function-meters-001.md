# Khi nào dùng phép đo đọc từ bộ thống kê có sẵn của đối tượng

## Function meter đọc số liệu đã được đối tượng duy trì

Micrometer cung cấp **function meter** để lấy số liệu từ các hàm đọc trên một đối tượng có sẵn. Thay vì gọi Micrometer mỗi khi một sự kiện xảy ra, registry đọc các bộ thống kê mà đối tượng nguồn đã tích lũy khi thu thập metrics.

Hai loại function meter thường dùng là:

- **FunctionCounter:** đọc một giá trị đếm tích lũy, chẳng hạn tổng số cache hit, số message đã nhận hoặc số lần một thư viện thực hiện thao tác.
- **FunctionTimer:** đọc số lần hoàn tất và tổng thời gian tích lũy của các thao tác từ một đối tượng đã tự thống kê.

Cách này hữu ích khi thư viện hoặc thành phần nền tảng đã cung cấp số liệu thống kê đáng tin cậy, nhưng không phát callback cho từng sự kiện để ứng dụng ghi vào Counter hoặc Timer thông thường. Ứng dụng chỉ cần cung cấp đối tượng nguồn và các hàm đọc giá trị.

Function meter phù hợp với mô hình **đọc thống kê có sẵn**. Nó không tạo ra lịch sử sự kiện mới, không lưu từng observation vào Micrometer và không thay thế đối tượng nguồn chịu trách nhiệm cập nhật số liệu.

## Khi nào nên chọn function meter?

Nên cân nhắc function meter khi có đủ các điều kiện sau:

1. Đối tượng nguồn đã duy trì thống kê tích lũy trong quá trình hoạt động.
2. Ứng dụng có thể đọc các giá trị đó qua những hàm ổn định, nhẹ và an toàn khi thu thập.
3. Các giá trị có ngữ nghĩa phù hợp với FunctionCounter hoặc FunctionTimer.
4. Giá trị đếm và tổng thời gian không giảm trong vòng đời của meter.
5. Đối tượng nguồn được giữ sống đủ lâu để registry tiếp tục đọc.

Ví dụ, một thư viện cache có thể cung cấp tổng số hit và miss; một client thư viện có thể cung cấp số lần gọi và tổng thời gian gọi; một bộ xử lý có thể duy trì tổng số bản ghi đã hoàn tất. Nếu những thống kê đó đã tồn tại, function meter giúp xuất chúng mà không phải duy trì một bộ đếm Micrometer song song.

Không nên dùng function meter chỉ vì có thể đọc được một số nguyên từ đối tượng. Nếu giá trị biểu diễn trạng thái hiện tại và có thể tăng giảm, Gauge phù hợp hơn. Nếu ứng dụng kiểm soát trực tiếp từng sự kiện hoặc thời lượng, Counter và Timer thông thường thường rõ ràng hơn.

## FunctionCounter: đọc bộ đếm tích lũy

### Nguyên lý

**FunctionCounter** đọc một giá trị số từ đối tượng nguồn và biểu diễn nó như một bộ đếm tăng đơn điệu. Micrometer lấy giá trị qua hàm được cung cấp khi registry thu thập metrics.

Ví dụ, đối tượng thống kê đã có tổng số request:

~~~java
public final class RequestStats {
    private final AtomicLong totalRequests = new AtomicLong();

    public void requestReceived() {
        totalRequests.incrementAndGet();
    }

    public double totalRequests() {
        return totalRequests.get();
    }
}
~~~

Đăng ký FunctionCounter trên đối tượng đó:

~~~java
RequestStats stats = new RequestStats();

FunctionCounter.builder(
        "service.requests",
        stats,
        RequestStats::totalRequests
    )
    .description("Tong so request da tiep nhan")
    .baseUnit("requests")
    .register(registry);
~~~

Khi request đến, thành phần sở hữu RequestStats cập nhật số liệu bằng requestReceived. Micrometer không cần nhận thêm một lệnh increment cho mỗi request. Khi scrape hoặc collect, function meter đọc totalRequests từ đối tượng nguồn.

Nếu giá trị tăng từ 100 lên 125 giữa hai lần thu thập, backend nhận được các giá trị tích lũy tương ứng. Backend có thể tính tốc độ dựa trên chênh lệch giữa các mẫu theo thời gian.

### Giá trị phải tăng đơn điệu

FunctionCounter có semantics của một bộ đếm tích lũy. Giá trị trả về phải không giảm trong vòng đời của meter. Nếu hàm đọc trả về 100 ở lần thu thập trước rồi 20 ở lần sau do đối tượng bị reset, dữ liệu không còn tuân thủ semantics counter.

Một số backend có thể xem mức giảm là counter reset, nhưng việc reset đối tượng giữa vòng đời meter có thể khiến rate, tổng số hoặc cảnh báo trở nên khó diễn giải. Không nên dựa vào backend để sửa một nguồn dữ liệu có semantics không nhất quán.

Nếu đối tượng nguồn có thể reset, có các lựa chọn:

- Dùng Gauge nếu giá trị thực sự là trạng thái hiện tại có thể tăng và giảm.
- Tạo một vòng đời meter mới với danh tính phù hợp khi một bộ thống kê mới thực sự bắt đầu, đồng thời kiểm soát tag để không tạo cardinality không giới hạn.
- Giữ bộ đếm tích lũy qua các lần reset của thành phần nếu nghiệp vụ yêu cầu tổng số liên tục.
- Dùng Counter thông thường nếu ứng dụng có thể ghi nhận từng sự kiện và cần kiểm soát rõ lifecycle của bộ đếm.

Không đưa ID ngẫu nhiên hoặc generation duy nhất vào tag mỗi lần reset chỉ để né vấn đề counter giảm. Cách đó có thể tạo ra vô số time series.

### Không gọi increment trên FunctionCounter

FunctionCounter được cập nhật thông qua đối tượng nguồn. Ứng dụng không tăng trực tiếp FunctionCounter bằng increment như Counter thông thường.

Nếu vừa cập nhật đối tượng nguồn vừa tăng một Counter khác cho cùng một sự kiện, hai số liệu có thể bị ghi trùng hoặc lệch nhau khi một nhánh xử lý quên cập nhật. Hãy chọn một nguồn sự thật cho số đếm.

## FunctionTimer: đọc count và tổng thời gian tích lũy

### Nguyên lý

**FunctionTimer** lấy hai thống kê từ một đối tượng nguồn:

- Số lần thao tác đã hoàn tất.
- Tổng thời gian tích lũy của những thao tác đó.

Đối tượng nguồn phải tự cập nhật hai giá trị này. Micrometer đọc chúng khi registry thu thập metrics, sau đó registry chuyển đổi và xuất theo quy ước của backend.

Ví dụ, một thư viện xử lý tác vụ có bộ thống kê riêng:

~~~java
public final class OperationStats {
    private final AtomicLong count = new AtomicLong();
    private final AtomicLong totalNanos = new AtomicLong();

    public void completed(long elapsedNanos) {
        count.incrementAndGet();
        totalNanos.addAndGet(elapsedNanos);
    }

    public long count() {
        return count.get();
    }

    public double totalTimeNanos() {
        return totalNanos.get();
    }
}
~~~

Đăng ký FunctionTimer:

~~~java
OperationStats stats = new OperationStats();

FunctionTimer.builder(
        "storage.operation",
        stats,
        OperationStats::count,
        OperationStats::totalTimeNanos,
        TimeUnit.NANOSECONDS
    )
    .description("So lan va tong thoi gian thao tac storage")
    .register(registry);
~~~

Khi thao tác hoàn tất, thành phần sở hữu stats gọi completed với thời lượng đã đo. FunctionTimer không cần được gọi record cho từng thao tác; nó đọc count và totalTime từ stats.

Đơn vị truyền vào builder phải đúng với đơn vị mà hàm totalTime trả về. Trong ví dụ, hàm trả về nano giây nên đơn vị được khai báo là NANOSECONDS. Nếu đối tượng nguồn trả mili giây, phải khai báo MILLISECONDS. Không khai báo đơn vị khác với đơn vị dữ liệu thực tế.

### Có thể suy ra thời gian trung bình

Từ count và total time, hệ thống có thể suy ra thời gian trung bình:

~~~text
mean duration = total time / count
~~~

Ví dụ, đối tượng nguồn báo count là 200 và tổng thời gian là 10 giây. Thời gian trung bình là 50 mili giây.

FunctionTimer không giữ lại thời lượng của từng thao tác. Vì vậy, chỉ từ count và tổng thời gian không thể khôi phục chính xác max, p95, p99 hoặc histogram của các thời lượng riêng lẻ. Nếu cần phân tích phân phối độ trễ, hãy dùng Timer có record từng observation hoặc một nguồn thống kê có histogram phù hợp.

### Count và total time cần cùng vòng đời

Hai giá trị của FunctionTimer phải mô tả cùng một tập thao tác đã hoàn tất. Nếu count tăng trước khi total time được cập nhật, một lần scrape đúng vào khoảng giữa có thể đọc được trạng thái chưa nhất quán. Khi tính toán trung bình, sự không đồng bộ này có thể làm số liệu dao động.

Nên cập nhật count và total time theo một cơ chế đồng bộ phù hợp với nguồn dữ liệu. Nếu thư viện cung cấp snapshot nhất quán hoặc một đối tượng stats chuyên dụng, hãy ưu tiên API đó. Nếu hai hàm đọc độc lập trên các biến nguyên tử, cần hiểu rằng chúng vẫn có thể được đọc ở hai thời điểm hơi khác nhau.

Cả count và total time cần có tính tích lũy, không giảm trong vòng đời meter. Nếu thư viện reset bộ thống kê hoặc tái tạo đối tượng, hãy xác định cách chuyển đổi vòng đời đó trước khi đưa FunctionTimer vào dashboard.

## Function meter khác Counter, Timer và Gauge thế nào?

| Nhu cầu | Meter phù hợp | Ai cập nhật số liệu? |
|---|---|---|
| Ghi nhận mỗi sự kiện mới | Counter | Mã ứng dụng gọi increment |
| Đọc tổng sự kiện đã được đối tượng khác tích lũy | FunctionCounter | Đối tượng nguồn cập nhật; Micrometer đọc hàm |
| Ghi thời lượng từng thao tác hoàn tất | Timer | Mã ứng dụng gọi record hoặc sample.stop |
| Đọc count và tổng thời gian từ thống kê sẵn có | FunctionTimer | Đối tượng nguồn cập nhật; Micrometer đọc hai hàm |
| Đọc trạng thái hiện tại có thể tăng và giảm | Gauge | Đối tượng nguồn cung cấp giá trị hiện tại |

Chọn theo nơi sở hữu dữ liệu:

- Nếu ứng dụng kiểm soát từng sự kiện, Counter là lựa chọn trực tiếp.
- Nếu một thư viện đã có bộ đếm tích lũy và chỉ cung cấp hàm đọc, FunctionCounter tránh việc duy trì một bộ đếm trùng lặp.
- Nếu ứng dụng đo từng thời lượng, Timer cung cấp các phép đo trực tiếp và có thể cấu hình histogram/percentile.
- Nếu thư viện đã tổng hợp count và total time, FunctionTimer có thể xuất các thống kê đó.
- Nếu giá trị là trạng thái hiện tại, Gauge phản ánh đúng semantics hơn một counter.

FunctionCounter và FunctionTimer vẫn là meter được registry thu thập theo chu kỳ. Chúng không làm cho số liệu xuất hiện ngay tại thời điểm đối tượng nguồn thay đổi; giá trị mới sẽ được quan sát ở lần collect hoặc scrape tiếp theo.

## Đối tượng nguồn và tham chiếu mạnh

Function meter thường giữ tham chiếu yếu đến đối tượng nguồn, tương tự một số meter đọc hàm từ object. Ứng dụng phải giữ tham chiếu mạnh đến đối tượng đó trong suốt vòng đời cần đo.

Ví dụ, nên giữ stats trong field của component:

~~~java
@Component
public class StorageMetrics {

    private final OperationStats stats = new OperationStats();

    public StorageMetrics(MeterRegistry registry) {
        FunctionTimer.builder(
                "storage.operation",
                stats,
                OperationStats::count,
                OperationStats::totalTimeNanos,
                TimeUnit.NANOSECONDS
            )
            .register(registry);
    }

    public OperationStats stats() {
        return stats;
    }
}
~~~

Field stats giữ đối tượng nguồn sống cùng component. Nếu chỉ tạo một object tạm thời trong lúc đăng ký rồi không còn tham chiếu mạnh nào khác, garbage collector có thể thu hồi object. Khi đó function meter không còn đọc được dữ liệu; backend có thể nhận giá trị không hợp lệ hoặc không có mẫu tùy registry.

Không nên lưu đối tượng nguồn trong một biến cục bộ chỉ tồn tại trong constructor rồi giả định registry sẽ giữ nó sống. Hãy để component, thư viện hoặc một đối tượng quản lý vòng đời sở hữu tham chiếu mạnh.

## Hàm đọc phải nhẹ và an toàn

Function meter gọi các hàm đọc khi registry thu thập metrics. Các hàm này nên:

- Trả về nhanh từ bộ thống kê đã có.
- Không gọi HTTP hoặc truy vấn cơ sở dữ liệu.
- Không chờ lock dài hoặc thực hiện thao tác I/O.
- Không làm thay đổi số liệu khi được đọc.
- An toàn khi được gọi đồng thời với luồng cập nhật của đối tượng nguồn.

Không thực hiện công việc nặng bên trong function đọc. Nếu thư viện chỉ cung cấp API lấy snapshot tốn kém, hãy cân nhắc cập nhật snapshot định kỳ ở một luồng riêng rồi để function meter đọc giá trị đã chuẩn bị, đồng thời tài liệu hóa độ trễ của snapshot.

Hàm đọc phải có tính quan sát thuần túy. Nếu mỗi lần scrape lại làm tăng count hoặc reset thống kê, kết quả sẽ phụ thuộc tần suất scrape và không còn phản ánh sự kiện nghiệp vụ.

## Tích hợp function meter trong Spring Boot

Trong Spring Boot, nên inject MeterRegistry và đăng ký function meter một lần trong component quản lý đối tượng thống kê:

~~~java
@Component
public class CacheMetrics {

    private final CacheStats stats;

    public CacheMetrics(MeterRegistry registry, CacheStats stats) {
        this.stats = stats;

        FunctionCounter.builder(
                "cache.hits",
                stats,
                CacheStats::hitCount
            )
            .description("Tong so cache hit")
            .baseUnit("hits")
            .register(registry);

        FunctionCounter.builder(
                "cache.misses",
                stats,
                CacheStats::missCount
            )
            .description("Tong so cache miss")
            .baseUnit("misses")
            .register(registry);
    }
}
~~~

CacheStats đại diện cho đối tượng thống kê do cache hoặc component quản lý. Khi cache xử lý hit hoặc miss, chính đối tượng đó cập nhật bộ đếm. FunctionCounter chỉ đọc hai giá trị tích lũy để xuất metrics.

Nếu dùng thư viện bên ngoài, hãy kiểm tra semantics và lifecycle của thống kê mà thư viện cung cấp. Một số thống kê có thể chỉ được bật khi cấu hình cụ thể; một số có thể reset khi cache bị invalidate hoặc thay thế. Không giả định tên phương thức có chữ count đồng nghĩa với counter tích lũy không reset.

Với Spring Boot, dependency injection giúp giữ đối tượng nguồn và registry trong cùng application context. Cách này cũng giúp thay thế nguồn thống kê bằng fake hoặc fixture khi kiểm thử.

## Cardinality và danh tính meter

Function meter vẫn tuân theo quy tắc định danh meter bằng tên và tag. Nếu đăng ký một FunctionCounter cho từng object với tag chứa ID duy nhất, số time series sẽ tăng theo số đối tượng.

Nên dùng tag biểu diễn nhóm hữu hạn như cache_name, storage_type, operation hoặc region. Không dùng user ID, request ID, file path đầy đủ hoặc ID của từng task làm tag chỉ để phân biệt đối tượng nguồn.

Nếu cần đo riêng từng đối tượng có vòng đời ngắn, metrics thường không phải lựa chọn thích hợp. Có thể dùng log, trace hoặc một hệ thống lưu trạng thái chuyên biệt để tra cứu chi tiết.

Cũng cần tránh đăng ký nhiều function meter có cùng tên và tag nhưng trỏ đến các object khác nhau. Registry định danh meter theo tên, loại và tag; đăng ký trùng danh tính không tạo ra các series độc lập theo ý muốn. Nếu nhiều nguồn cần được tổng hợp, hãy tạo một đối tượng tổng hợp có semantics rõ ràng hoặc phân biệt bằng tag có tập giá trị được kiểm soát.

## Kiểm thử FunctionCounter và FunctionTimer

### Kiểm tra FunctionCounter đọc giá trị nguồn

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
AtomicLong sourceCount = new AtomicLong(10);

FunctionCounter counter = FunctionCounter.builder(
        "test.events",
        sourceCount,
        AtomicLong::doubleValue
    )
    .register(registry);

assertThat(counter.count()).isEqualTo(10.0);

sourceCount.addAndGet(5);

assertThat(counter.count()).isEqualTo(15.0);
~~~

Kiểm thử này xác nhận FunctionCounter đọc giá trị mới từ đối tượng nguồn. Không gọi increment trên FunctionCounter; thay đổi sourceCount mới là hành động làm số liệu thay đổi.

### Kiểm tra FunctionTimer đọc count và total time

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
OperationStats stats = new OperationStats();

FunctionTimer timer = FunctionTimer.builder(
        "test.operation",
        stats,
        OperationStats::count,
        OperationStats::totalTimeNanos,
        TimeUnit.NANOSECONDS
    )
    .register(registry);

stats.completed(TimeUnit.MILLISECONDS.toNanos(100));
stats.completed(TimeUnit.MILLISECONDS.toNanos(300));

assertThat(timer.count()).isEqualTo(2);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
    .isEqualTo(400.0);
~~~

Kiểm thử này xác nhận FunctionTimer đọc count và tổng thời gian từ cùng nguồn stats, đồng thời chuyển đổi thời gian theo đơn vị yêu cầu khi đọc.

Ngoài kiểm thử đơn vị, cần kiểm tra exporter thực tế để xác nhận tên metric, đơn vị và kiểu dữ liệu mà backend nhận được. FunctionTimer có thể được biểu diễn thành count và total time theo quy ước của registry; không giả định mọi backend đều xuất tên hoặc hậu tố giống nhau.

Nên có các trường hợp kiểm thử cho:

1. Nguồn thống kê ban đầu bằng 0.
2. Giá trị tăng sau khi có thao tác mới.
3. Không có thao tác mới giữa hai lần scrape.
4. Đối tượng nguồn còn được giữ sống trong suốt vòng đời meter.
5. Nguồn không reset hoặc giảm giá trị bất ngờ.
6. Count và total time được cập nhật nhất quán.
7. Hàm đọc không thực hiện I/O hoặc tác dụng phụ.
8. Exporter xuất đúng đơn vị và dữ liệu mà dashboard truy vấn.

## Những sai lầm thường gặp

**Dùng FunctionCounter cho giá trị có thể giảm.** FunctionCounter đại diện cho bộ đếm tích lũy đơn điệu. Với trạng thái hiện tại, dùng Gauge.

**Dùng FunctionTimer khi chỉ có một giá trị thời gian trung bình.** FunctionTimer cần count và total time tích lũy từ cùng tập thao tác. Một giá trị trung bình đơn lẻ không đủ để biểu diễn hai thống kê này.

**Vừa đọc thống kê nguồn vừa tăng Counter riêng cho cùng sự kiện.** Điều này có thể tạo số liệu trùng hoặc lệch. Chọn một nguồn sự thật.

**Reset đối tượng nguồn trong khi meter vẫn tồn tại.** Giá trị FunctionCounter hoặc FunctionTimer có thể giảm, phá vỡ semantics tích lũy. Xác định lifecycle hoặc chọn loại meter khác.

**Không giữ tham chiếu mạnh đến đối tượng nguồn.** Garbage collector có thể thu hồi object khiến function meter không đọc được dữ liệu. Giữ object trong field hoặc component quản lý.

**Đưa thao tác nặng vào hàm đọc.** Scrape có thể bị chậm hoặc tạo tải phụ. Hàm đọc nên nhẹ, nhanh và không có tác dụng phụ.

**Kỳ vọng FunctionTimer có percentile hoặc max của từng thao tác.** Nó chỉ đọc count và total time. Muốn histogram hoặc percentile, cần nguồn phân phối phù hợp hoặc Timer ghi từng observation.

**Đăng ký meter cho từng object với tag duy nhất.** Cardinality tăng nhanh. Ưu tiên meter theo nhóm và dùng log/trace cho định danh chi tiết.

## Checklist lựa chọn function meter

Trước khi đăng ký function meter, hãy xác minh:

1. Đối tượng nguồn đã duy trì thống kê cần thiết chưa?
2. Hàm đọc có trả về count hoặc total time tích lũy đúng semantics không?
3. FunctionCounter có giá trị không giảm trong vòng đời meter không?
4. FunctionTimer có count và total time từ cùng tập thao tác không?
5. Đơn vị của total time có được khai báo đúng không?
6. Đối tượng nguồn có được giữ bằng tham chiếu mạnh không?
7. Hàm đọc có nhẹ, an toàn đa luồng và không có tác dụng phụ không?
8. Có tránh ghi trùng bằng Counter hoặc Timer khác cho cùng sự kiện không?
9. Tag có tập giá trị hữu hạn và danh tính meter có ổn định không?
10. Kiểm thử có xác nhận cả giá trị nguồn lẫn dữ liệu sau khi xuất không?

## Kết luận

FunctionCounter và FunctionTimer phù hợp khi một đối tượng hoặc thư viện đã duy trì thống kê tích lũy và Micrometer chỉ cần đọc chúng khi thu thập metrics. FunctionCounter đọc một bộ đếm không giảm; FunctionTimer đọc số lần hoàn tất và tổng thời gian tích lũy.

Hãy chọn function meter khi nguồn dữ liệu đã có sẵn và có semantics phù hợp. Giữ đối tượng nguồn sống đủ lâu, bảo đảm hàm đọc nhẹ và an toàn, không reset số liệu trong vòng đời meter, đồng thời chuẩn hóa đơn vị và tag. Nếu ứng dụng cần ghi từng sự kiện hoặc từng thời lượng, Counter và Timer thông thường sẽ rõ ràng hơn; nếu cần trạng thái có thể tăng giảm, Gauge là lựa chọn phù hợp.
