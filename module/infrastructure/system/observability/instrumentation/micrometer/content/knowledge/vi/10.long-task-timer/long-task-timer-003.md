# Bắt đầu, giữ mẫu và dừng một tác vụ đúng vòng đời

## LongTaskTimer theo dõi công việc còn đang chạy

Micrometer cung cấp **LongTaskTimer** để quan sát thời lượng của những tác vụ vẫn đang thực thi. Loại meter này phù hợp với batch job, tác vụ đồng bộ dữ liệu, xử lý báo cáo, tiến trình import/export, tác vụ nền hoặc một request có thể kéo dài đáng kể.

Điểm quan trọng của LongTaskTimer là nó làm cho trạng thái của tác vụ đang chạy có thể quan sát được trước khi tác vụ hoàn tất. Khi sample được bắt đầu, LongTaskTimer tính tác vụ đó vào số tác vụ đang hoạt động và theo dõi thời gian đã trôi qua. Khi sample dừng, tác vụ không còn đóng góp vào các phép đo đang hoạt động.

Điều này khác với **Timer** thông thường. Timer ghi nhận một lần đo khi thao tác kết thúc, nhờ đó có thể phân tích count, tổng thời gian và phân phối thời lượng của các thao tác đã hoàn tất. LongTaskTimer tập trung vào những tác vụ hiện vẫn đang chạy: số tác vụ đang hoạt động, tổng thời gian đã trôi qua của chúng và thời lượng lớn nhất trong nhóm đang hoạt động theo cách registry xuất dữ liệu.

Nếu cần vừa nhìn thấy công việc đang chạy bao lâu, vừa phân tích độ trễ sau khi hoàn tất, có thể dùng cả LongTaskTimer và Timer cho cùng một luồng công việc. Hai meter trả lời hai câu hỏi vận hành khác nhau.

## Vòng đời của một sample

### Bắt đầu tác vụ

Đầu tiên, đăng ký một LongTaskTimer trên MeterRegistry:

~~~java
LongTaskTimer batchTimer = LongTaskTimer.builder("batch.reconciliation.running")
    .description("Thoi gian cac tac vu doi soat dang chay")
    .tag("job_type", "reconciliation")
    .register(registry);
~~~

Khi một lần chạy bắt đầu, gọi **start()** để tạo sample:

~~~java
LongTaskTimer.Sample sample = batchTimer.start();
~~~

Sample đại diện cho một lần thực thi cụ thể. Nó ghi nhận mốc bắt đầu và làm cho tác vụ xuất hiện trong các phép đo đang hoạt động của LongTaskTimer.

### Giữ sample trong suốt thời gian xử lý

Sample phải được giữ theo vòng đời của đúng tác vụ đã bắt đầu. Có thể giữ nó trong biến cục bộ nếu tác vụ đồng bộ, hoặc trong đối tượng context của lần chạy nếu tác vụ đi qua nhiều phương thức hay callback bất đồng bộ.

Không dùng một sample dùng chung cho nhiều lần chạy. Nếu hai batch job chạy đồng thời, mỗi lần chạy phải có sample riêng để LongTaskTimer theo dõi độc lập.

### Dừng khi tác vụ thực sự kết thúc

Khi công việc hoàn tất, gọi **stop()** trên sample:

~~~java
LongTaskTimer.Sample sample = batchTimer.start();

try {
    reconciliationJob.execute();
} finally {
    sample.stop();
}
~~~

Đặt stop trong finally giúp kết thúc sample cả khi công việc ném exception. Khi stop được gọi, sample kết thúc và không còn được tính vào số tác vụ đang hoạt động.

Một sample không được stop sẽ tiếp tục được xem là đang chạy trong suốt thời gian registry còn quan sát nó. Nếu quên stop ở nhánh lỗi, metric active tasks có thể cao hơn thực tế và thời lượng đang hoạt động tiếp tục tăng. Vì vậy, stop là một phần bắt buộc của lifecycle, tương tự việc giải phóng tài nguyên sau khi sử dụng.

## Theo dõi nhiều tác vụ đồng thời

LongTaskTimer hỗ trợ nhiều sample đang hoạt động cùng lúc. Mỗi lần gọi start tạo một lần thực thi riêng, không cần chờ sample trước dừng.

Ví dụ, một dịch vụ có thể chạy nhiều tác vụ import đồng thời:

~~~java
LongTaskTimer importTimer = LongTaskTimer.builder("data.import.running")
    .description("Thoi gian cac tac vu import dang chay")
    .register(registry);

LongTaskTimer.Sample first = importTimer.start();
LongTaskTimer.Sample second = importTimer.start();

// Hai tác vụ đang chạy đồng thời.
first.stop();

// Tác vụ thứ hai vẫn đang chạy.
second.stop();
~~~

Trong khoảng thời gian cả hai sample hoạt động, số tác vụ đang chạy là 2. Sau khi sample thứ nhất dừng, số tác vụ đang hoạt động giảm còn 1. Khi sample thứ hai dừng, số tác vụ đang hoạt động trở về 0.

Các phép đo về thời gian đang hoạt động được tính từ các sample hiện chưa dừng. Tổng thời gian đang hoạt động có thể lớn hơn thời gian thực đã trôi qua của tiến trình khi nhiều tác vụ chạy đồng thời. Ví dụ, hai tác vụ cùng chạy 10 giây có tổng thời gian hoạt động xấp xỉ 20 giây. Đây là tổng thời gian công việc, không phải thời gian tường đồng hồ của toàn hệ thống.

Không diễn giải tổng thời gian hoạt động như thời gian một tác vụ đơn lẻ. Nếu cần xem tác vụ đang chạy lâu nhất, dùng phép đo max mà LongTaskTimer cung cấp hoặc biểu diễn tương ứng của registry.

## Đọc các số đo đang hoạt động

LongTaskTimer cung cấp các số liệu để quan sát trạng thái của các sample chưa dừng:

- **activeTasks:** số sample đang hoạt động.
- **duration:** tổng thời gian đã trôi qua của các sample đang hoạt động.
- **max:** thời lượng lớn nhất trong các sample đang hoạt động.

Có thể đọc các giá trị từ đối tượng LongTaskTimer trong mã Java:

~~~java
long active = batchTimer.activeTasks();
double activeSeconds = batchTimer.duration(TimeUnit.SECONDS);
double longestActiveSeconds = batchTimer.max(TimeUnit.SECONDS);
~~~

Các giá trị này thay đổi khi sample bắt đầu, thời gian trôi qua và sample dừng. Registry xuất chúng theo quy ước của backend. Tên metric, đơn vị, kiểu dữ liệu và cách truy vấn cụ thể có thể khác giữa Prometheus, OTLP hoặc nền tảng giám sát khác; cần kiểm tra đầu ra của registry đang dùng.

Vì duration và max chỉ phản ánh các tác vụ còn hoạt động, khi tác vụ dừng thì đóng góp của nó được loại khỏi các phép đo hiện tại. LongTaskTimer không phải kho lịch sử thời lượng của mọi tác vụ đã hoàn tất.

## LongTaskTimer và Timer khác nhau thế nào?

| Câu hỏi vận hành | LongTaskTimer | Timer |
|---|---|---|
| Hiện có bao nhiêu tác vụ đang chạy? | Có, qua active tasks | Không trực tiếp |
| Tác vụ hiện tại đã chạy bao lâu? | Có, khi sample còn hoạt động | Chỉ ghi nhận sau khi hoàn tất |
| Tác vụ nào đang chạy lâu nhất? | Có thể quan sát max của các tác vụ đang hoạt động | Không biểu diễn trực tiếp trạng thái đang chạy |
| Tổng số lần hoàn tất trong một khoảng thời gian | Không phải mục đích chính | Có, qua count |
| Phân phối độ trễ của tác vụ đã hoàn tất | Không phải mục đích chính | Có, khi cấu hình thống kê phù hợp |
| Quan sát một tác vụ kéo dài qua nhiều lần scrape | Có | Chỉ có kết quả sau khi stop/record |

Ví dụ, với một batch import mất 15 phút, LongTaskTimer cho phép dashboard hiển thị rằng tác vụ đang chạy và đã kéo dài bao lâu trong suốt 15 phút. Timer thông thường chỉ ghi nhận thời lượng khi batch import hoàn tất.

Nếu chỉ dùng Timer, trong lúc batch import chạy, backend chưa có observation hoàn tất để cho biết nó đang kéo dài bất thường. Nếu chỉ dùng LongTaskTimer, sau khi batch import dừng, số liệu trạng thái đang chạy không còn giữ lại phân phối của những lần import đã hoàn tất. Hai loại meter có thể bổ sung cho nhau.

## Dùng LongTaskTimer cùng Timer

Khi cần cả trạng thái đang chạy và thống kê sau hoàn tất, hãy đăng ký hai meter riêng:

~~~java
LongTaskTimer runningTimer = LongTaskTimer.builder("batch.reconciliation.running")
    .tag("job_type", "reconciliation")
    .register(registry);

Timer completedTimer = Timer.builder("batch.reconciliation.duration")
    .description("Thoi gian hoan tat moi lan doi soat")
    .tag("job_type", "reconciliation")
    .publishPercentileHistogram()
    .register(registry);
~~~

Ở mỗi lần thực thi, bắt đầu cả hai phép đo và dừng đúng lifecycle:

~~~java
LongTaskTimer.Sample runningSample = runningTimer.start();
Timer.Sample completedSample = Timer.start(registry);

try {
    reconciliationJob.execute();
} finally {
    runningSample.stop();
    completedSample.stop(completedTimer);
}
~~~

LongTaskTimer phản ánh tác vụ trong thời gian nó đang chạy. Timer ghi nhận một observation khi tác vụ kết thúc, kể cả khi kết thúc bằng exception trong ví dụ này. Nếu muốn phân biệt success và failure, có thể chọn Timer có tag outcome ở thời điểm stop, nhưng tag phải đến từ một tập giá trị hữu hạn và nhất quán.

Không dùng cùng một tên meter cho hai loại meter khác nhau. Chọn tên thể hiện rõ mục đích, ví dụ hậu tố **.running** cho trạng thái tác vụ đang hoạt động và **.duration** cho thời lượng hoàn tất. Quy ước tên cụ thể cần phù hợp naming convention của backend.

## Xử lý exception, timeout và cancellation

### Luôn dừng sample trong finally

Một tác vụ có thể kết thúc bình thường hoặc ném exception. Nếu stop chỉ được gọi sau câu lệnh thành công, sample sẽ bị bỏ quên khi có lỗi.

Mẫu cơ bản:

~~~java
LongTaskTimer.Sample sample = longTaskTimer.start();

try {
    executeLongRunningTask();
} finally {
    sample.stop();
}
~~~

Nếu cần ghi nhận nguyên nhân kết thúc, có thể cập nhật một biến trạng thái trước khi rời khối try/catch/finally và dùng một Counter hoặc Timer riêng để phân loại số lần hoàn tất. LongTaskTimer vẫn tập trung vào trạng thái đang chạy; không biến nó thành meter lưu mọi loại outcome.

### Dừng khi công việc thực sự ngừng

Với timeout, cần phân biệt thời điểm timeout được yêu cầu và thời điểm tác vụ thực sự ngừng tiêu thụ tài nguyên. Nếu chỉ gửi tín hiệu cancel nhưng worker vẫn tiếp tục chạy, dừng sample ngay có thể khiến metrics báo tác vụ đã kết thúc trong khi công việc vẫn đang chạy.

Hãy gắn stop với lifecycle thực tế của worker hoặc tiến trình. Nếu hệ thống có bước cleanup, đóng kết nối hoặc chờ worker kết thúc, cần xác định rõ khoảng đo bao gồm những bước nào.

Khi có nhiều đường kết thúc cạnh tranh như callback hoàn tất và timeout, bảo đảm chỉ một đường gọi stop. Có thể dùng một trạng thái hoàn tất nguyên tử hoặc primitive completion của framework để điều phối. Không gọi stop hai lần cho cùng một sample.

### Không để sample tồn tại vô hạn

Nếu một tác vụ bị treo và không có timeout, cancellation hoặc cơ chế phát hiện lỗi, LongTaskTimer sẽ tiếp tục báo nó đang hoạt động. Đây có thể là tín hiệu hữu ích để phát hiện task bị kẹt, nhưng cũng có thể là lỗi instrumentation nếu ứng dụng đã kết thúc công việc mà quên stop.

Nên có quy tắc lifecycle rõ ràng: ai tạo sample, ai sở hữu sample, đường nào được phép dừng và điều gì xảy ra nếu component hoặc worker bị hủy. Với tác vụ có thể tồn tại lâu hơn request khởi tạo, không gắn sample với vòng đời ngắn của request nếu tác vụ vẫn tiếp tục sau khi request kết thúc.

## Theo dõi tác vụ bất đồng bộ

### Giữ sample trong context của tác vụ

Khi công việc chạy bất đồng bộ, phương thức submit thường trả về trước khi worker hoàn tất. Nếu stop ngay sau submit, sample chỉ đo thời gian đưa tác vụ vào hệ thống, không đo toàn bộ thời gian chạy.

Ví dụ với CompletableFuture:

~~~java
LongTaskTimer.Sample sample = longTaskTimer.start();

CompletableFuture<Result> future = service.executeAsync(command);

future.whenComplete((result, error) -> {
    sample.stop();
});
~~~

Callback hoàn tất là nơi phù hợp để stop nếu future đại diện cho toàn bộ công việc cần đo. Nếu future chỉ đại diện cho bước submit hoặc một giai đoạn trung gian, hãy chọn điểm bắt đầu và kết thúc khác phù hợp với câu hỏi vận hành.

Sample không cần được lưu trong ThreadLocal. Nó có thể được truyền hoặc giữ trong context của tác vụ và được stop từ callback chạy trên thread khác. Cách này tránh phụ thuộc vào việc tác vụ có tiếp tục chạy trên cùng thread hay không.

Nếu callback có thể được gọi bởi nhiều cơ chế completion cạnh tranh, vẫn cần bảo đảm sample chỉ được stop một lần. Với CompletableFuture thông thường, whenComplete được gọi khi future hoàn tất; nhưng nếu ứng dụng tự kết hợp timeout, cancel và callback riêng, phải kiểm tra lifecycle thực tế.

### Đo riêng thời gian chờ và thời gian thực thi

Một tác vụ nền thường trải qua nhiều giai đoạn:

1. Được submit vào executor.
2. Chờ trong hàng đợi.
3. Worker bắt đầu thực thi.
4. Xử lý nghiệp vụ.
5. Cleanup và hoàn tất.

Nếu LongTaskTimer bắt đầu tại thời điểm submit và dừng khi hoàn tất, nó đo toàn bộ thời gian từ lúc submit đến khi kết thúc, bao gồm cả thời gian chờ. Điều đó có thể đúng nếu mục tiêu là thời gian end-to-end của công việc.

Nếu mục tiêu là phát hiện worker xử lý chậm, hãy bắt đầu sample khi worker thực sự bắt đầu chạy. Nếu cần theo dõi queue wait, đo giai đoạn chờ bằng Timer riêng. Ranh giới đo phải được tài liệu hóa để dashboard không diễn giải nhầm thời gian chờ thành thời gian xử lý.

## Tích hợp LongTaskTimer trong Spring Boot

Trong Spring Boot, nên inject MeterRegistry qua constructor và đăng ký LongTaskTimer một lần trong component quản lý tác vụ:

~~~java
@Component
public class ReconciliationMetrics {

    private final LongTaskTimer running;

    public ReconciliationMetrics(MeterRegistry registry) {
        this.running = LongTaskTimer.builder("batch.reconciliation.running")
            .description("Thoi gian tac vu doi soat dang chay")
            .tag("job_type", "reconciliation")
            .register(registry);
    }

    public LongTaskTimer.Sample start() {
        return running.start();
    }
}
~~~

Service thực hiện tác vụ giữ sample và kết thúc nó theo lifecycle:

~~~java
LongTaskTimer.Sample sample = metrics.start();

try {
    reconciliationJob.execute();
} finally {
    sample.stop();
}
~~~

Cách này tách phần khai báo meter khỏi logic xử lý nghiệp vụ. Registry do Spring quản lý, còn sample thuộc về từng lần chạy.

Nếu có nhiều loại job, dùng tag như job_type với tập giá trị hữu hạn. Không tạo tag theo job ID, file name hoặc customer ID. Những giá trị riêng cho từng lần chạy làm cardinality tăng theo số lượng tác vụ và có thể tạo ra chi phí lớn cho backend.

## Tần suất scrape và khả năng quan sát

LongTaskTimer được thiết kế để quan sát các tác vụ còn chạy qua nhiều lần lấy mẫu. Tuy nhiên, nó vẫn phụ thuộc chu kỳ scrape hoặc push của registry.

Một tác vụ bắt đầu và kết thúc hoàn toàn giữa hai lần scrape có thể không xuất hiện trong các mẫu active task. Với tác vụ kéo dài nhiều phút, nhiều lần scrape sẽ quan sát được trạng thái và thời gian đã trôi qua. Với tác vụ chỉ kéo dài vài mili giây, LongTaskTimer thường không đem lại lợi ích đáng kể; Timer thông thường phù hợp hơn để ghi nhận thời lượng sau khi hoàn tất.

Nếu cần phát hiện tác vụ vượt quá một ngưỡng thời gian, có thể xây dựng cảnh báo dựa trên duration hoặc max của các tác vụ đang hoạt động. Cần xác minh tên và đơn vị metric mà registry xuất, đồng thời tránh nhầm tổng duration của nhiều tác vụ với thời gian của một tác vụ riêng lẻ.

Tần suất scrape quá thưa có thể làm cảnh báo phát hiện chậm. Tần suất quá dày làm tăng chi phí thu thập. Chọn chu kỳ phù hợp với thời gian chạy thông thường, thời gian tối đa được phép và mục tiêu phát hiện task bị treo.

## Cardinality và phân nhóm tác vụ

LongTaskTimer thường đại diện cho một nhóm tác vụ có cùng ý nghĩa. Tag giúp phân biệt nhóm, chẳng hạn:

- job_type: reconciliation, report, import.
- component: billing, inventory, analytics.
- region: một vùng triển khai có tập giá trị hữu hạn.

Không đưa task ID, request ID, file path đầy đủ hoặc thông tin định danh người dùng vào tag. Nếu mỗi lần chạy tạo một bộ tag riêng, số time series sẽ tăng theo số lượng tác vụ và gây áp lực lên backend.

Nếu cần biết chính xác tác vụ cụ thể nào đang bị treo, metrics có thể chỉ ra nhóm và mức độ bất thường. Chi tiết định danh nên được tra cứu qua log hoặc trace bằng correlation ID, thay vì biến mỗi task thành một chuỗi metric riêng.

Trong môi trường nhiều instance, active tasks thường là trạng thái cục bộ của từng instance. Tổng hợp thành số tác vụ toàn hệ thống chỉ hợp lý khi mỗi sample tương ứng một tác vụ thực và không bị nhân đôi do retry hoặc xuất nhiều backend. Khi xem max hoặc duration, cần hiểu phép tổng hợp backend áp dụng cho các instance và tag.

## Kiểm thử vòng đời LongTaskTimer

Có thể dùng SimpleMeterRegistry để kiểm tra số tác vụ hoạt động trước và sau khi stop:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();

LongTaskTimer timer = LongTaskTimer.builder("test.long.task")
    .register(registry);

LongTaskTimer.Sample first = timer.start();
LongTaskTimer.Sample second = timer.start();

assertThat(timer.activeTasks()).isEqualTo(2);

first.stop();

assertThat(timer.activeTasks()).isEqualTo(1);

second.stop();

assertThat(timer.activeTasks()).isEqualTo(0);
~~~

Kiểm thử này xác nhận mỗi lần start tạo một sample hoạt động riêng và stop làm giảm số tác vụ đang hoạt động.

Có thể bổ sung kiểm thử cho các tình huống:

1. Tác vụ hoàn tất bình thường.
2. Tác vụ ném exception nhưng finally vẫn stop.
3. Tác vụ bị timeout hoặc cancellation.
4. Tác vụ bất đồng bộ dừng trong callback.
5. Nhiều tác vụ chạy đồng thời và hoàn tất theo thứ tự khác nhau.
6. Đường completion cạnh tranh không làm stop một sample nhiều lần.
7. LongTaskTimer và Timer cùng ghi nhận đúng vai trò nếu ứng dụng cần cả trạng thái đang chạy lẫn thời lượng hoàn tất.

Không nên kiểm tra thời lượng bằng một giá trị chính xác phụ thuộc tốc độ máy trong unit test thông thường. Nếu cần xác minh thời gian, dùng clock có thể kiểm soát hoặc kiểm tra các quan hệ hợp lý. Kiểm thử exporter riêng để xác nhận tên metric, đơn vị và cách backend biểu diễn active tasks, duration và max.

## Những sai lầm thường gặp

**Dùng Timer thay cho LongTaskTimer khi cần quan sát công việc đang chạy.** Timer thông thường ghi nhận khi thao tác hoàn tất; dashboard không thấy duration đang tăng của một tác vụ chưa kết thúc.

**Dùng LongTaskTimer để thay thế Timer hoàn toàn.** Khi sample dừng, nó không còn đóng góp vào số đo active. Nếu cần count, phân phối và percentile của các tác vụ đã hoàn tất, hãy dùng Timer bổ sung.

**Quên stop sample ở nhánh exception.** Tác vụ đã kết thúc nhưng vẫn được báo đang hoạt động. Dùng finally hoặc lifecycle completion tương đương.

**Dùng một sample cho nhiều lần chạy.** Mỗi sample đại diện cho một lần thực thi. Tác vụ đồng thời cần các sample độc lập.

**Stop ngay khi gửi tác vụ vào executor.** Thời lượng đo chỉ phản ánh bước submit. Hãy stop khi công việc thực sự kết thúc nếu mục tiêu là đo thời gian chạy.

**Stop khi mới yêu cầu cancellation.** Worker có thể vẫn đang cleanup hoặc tiếp tục chạy. Gắn stop với thời điểm công việc thực sự ngừng.

**Tạo tag riêng cho từng task.** Cardinality tăng theo số lần chạy. Dùng tag nhóm có tập giá trị hữu hạn và tra cứu chi tiết qua log/trace.

**Hiểu tổng duration là thời gian tường đồng hồ.** Nhiều tác vụ đồng thời làm tổng thời gian công việc lớn hơn thời gian thực đã trôi qua. Cần chọn phép đo phù hợp với câu hỏi.

**Không kiểm tra tần suất scrape.** Tác vụ ngắn có thể bắt đầu và kết thúc giữa hai lần lấy mẫu. Dùng Timer để lưu thời lượng hoàn tất của những tác vụ đó.

## Checklist thiết kế LongTaskTimer

Trước khi đưa LongTaskTimer vào vận hành, hãy xác minh:

1. Tác vụ đủ dài và cần quan sát khi vẫn đang chạy không?
2. Mỗi lần thực thi có sample riêng không?
3. Sample được tạo đúng tại ranh giới bắt đầu cần đo không?
4. Sample được giữ đến khi công việc thực sự kết thúc không?
5. Mọi đường thành công, exception, timeout và cancellation đều stop đúng một lần không?
6. Với tác vụ bất đồng bộ, sample có được giữ trong context đến callback hoàn tất không?
7. Có cần Timer riêng để ghi nhận count và phân phối thời lượng sau hoàn tất không?
8. Tần suất scrape có phù hợp với thời gian chạy và mục tiêu cảnh báo không?
9. Tag có cardinality thấp và biểu diễn nhóm tác vụ ổn định không?
10. Kiểm thử có bao phủ nhiều sample đồng thời và các đường kết thúc không?

## Kết luận

LongTaskTimer giúp quan sát các tác vụ còn đang chạy bằng cách bắt đầu một sample khi công việc bắt đầu và dừng sample khi công việc thực sự kết thúc. Trong thời gian sample hoạt động, registry có thể xuất số tác vụ đang chạy, tổng thời gian đã trôi qua và thời lượng lớn nhất của nhóm tác vụ đang hoạt động.

Hãy tạo sample riêng cho từng lần thực thi, giữ sample qua toàn bộ vòng đời đồng bộ hoặc bất đồng bộ và bảo đảm stop đúng một lần trong mọi đường kết thúc. Dùng Timer bổ sung khi cần phân tích các tác vụ đã hoàn tất, chọn chu kỳ scrape phù hợp và giữ tag có cardinality được kiểm soát. Khi ranh giới start/stop phản ánh đúng công việc, LongTaskTimer trở thành tín hiệu hữu ích để phát hiện tác vụ kéo dài hoặc bị treo.
