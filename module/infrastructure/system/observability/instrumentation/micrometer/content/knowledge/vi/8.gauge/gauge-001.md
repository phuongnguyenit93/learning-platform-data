# Gauge lấy giá trị hiện tại của đối tượng được theo dõi

## Gauge đo trạng thái tại thời điểm quan sát

Micrometer cung cấp **Gauge** để quan sát giá trị hiện tại của một đối tượng hoặc một trạng thái trong ứng dụng Java. Gauge phù hợp với những đại lượng có thể tăng, giảm hoặc thay đổi theo thời gian, chẳng hạn số request đang xử lý, số message trong hàng đợi, số kết nối đang mở, số tác vụ đang chạy hoặc số phần tử hiện có trong cache.

Điểm cốt lõi của Gauge là **nó đọc trạng thái hiện tại khi được quan sát**. Gauge không lưu lại mọi lần thay đổi của đối tượng. Nếu số request đang hoạt động lần lượt là 2, 5, 3 rồi 4 giữa hai lần scrape, backend có thể chỉ nhìn thấy giá trị 2 ở lần scrape đầu và 4 ở lần tiếp theo. Các giá trị trung gian không tự động trở thành chuỗi lịch sử.

Điều này khiến Gauge khác với Counter và Timer. Counter ghi nhận sự kiện tích lũy; Timer ghi nhận thời lượng của các thao tác; Gauge phản ánh một trạng thái đang tồn tại tại thời điểm đọc. Chọn đúng loại meter giúp truy vấn và cảnh báo giữ được ý nghĩa vận hành.

## Khi nào nên dùng Gauge?

Gauge thích hợp khi câu hỏi vận hành có dạng: "Hiện tại có bao nhiêu?", "Mức sử dụng đang là bao nhiêu?" hoặc "Giá trị đang ở trạng thái nào?".

Các ví dụ thường gặp:

| Trạng thái cần quan sát | Đại lượng Gauge | Ý nghĩa |
|---|---|---|
| Request đang xử lý | Số request đang hoạt động | Mức tải đồng thời tại thời điểm scrape |
| Hàng đợi công việc | Số phần tử đang chờ | Mức backlog hiện tại |
| Kết nối đang mở | Số kết nối hiện có | Mức sử dụng pool tại thời điểm quan sát |
| Cache | Số entry hiện có | Quy mô cache hiện tại |
| Tác vụ đang chạy | Số tác vụ chưa hoàn tất | Công việc đang chiếm tài nguyên |
| Dung lượng bộ nhớ đang sử dụng | Số byte đang dùng | Trạng thái bộ nhớ tại thời điểm lấy mẫu |

Một số đại lượng nhìn giống số đếm nhưng có ngữ nghĩa khác nhau. Tổng số request đã nhận là một bộ đếm tích lũy và nên dùng Counter. Số request đang xử lý là trạng thái hiện tại và phù hợp với Gauge. Tổng thời gian xử lý request là dữ liệu thời lượng và phù hợp với Timer.

Không chọn Gauge chỉ vì giá trị có kiểu số. Hãy xác định trước số đo đại diện cho sự kiện đã xảy ra, thời lượng đã hoàn tất hay trạng thái đang tồn tại.

## Cách Gauge lấy giá trị từ đối tượng

### Đăng ký Gauge với một đối tượng có thể thay đổi

Gauge thường được tạo bằng một đối tượng nguồn và một hàm đọc giá trị của đối tượng đó. Hàm đọc trả về một số có thể chuyển thành double.

Ví dụ theo dõi số request đang hoạt động:

~~~java
AtomicInteger activeRequests = new AtomicInteger();

Gauge.builder(
        "http.server.active.requests",
        activeRequests,
        AtomicInteger::get
    )
    .description("So request dang duoc xu ly")
    .register(registry);
~~~

Mỗi khi request bắt đầu, ứng dụng tăng giá trị; khi request kết thúc, ứng dụng giảm giá trị:

~~~java
activeRequests.incrementAndGet();
try {
    handleRequest();
} finally {
    activeRequests.decrementAndGet();
}
~~~

Khi registry hoặc backend đọc Gauge, Micrometer gọi hàm lấy giá trị trên đối tượng nguồn. Nếu giá trị hiện tại là 7, Gauge cung cấp số 7 cho lần quan sát đó. Sau khi một request kết thúc, giá trị có thể giảm xuống 6 ở lần đọc tiếp theo.

Trong ứng dụng thực tế, đối tượng nguồn nên là trạng thái mà component quản lý và cập nhật nhất quán. Có thể dùng AtomicInteger hoặc AtomicLong cho bộ đếm trạng thái đơn giản, hoặc dùng một collection/thread-safe object khi cần quan sát kích thước hay thuộc tính của đối tượng.

### Theo dõi kích thước của collection hoặc queue

Gauge không nhất thiết phải theo dõi một biến số nguyên. Nó có thể quan sát một thuộc tính của đối tượng:

~~~java
BlockingQueue<Job> pendingJobs = new LinkedBlockingQueue<>();

Gauge.builder(
        "worker.queue.depth",
        pendingJobs,
        BlockingQueue::size
    )
    .description("So job dang cho trong hang doi")
    .register(registry);
~~~

Khi backend lấy mẫu, Micrometer gọi phương thức size trên queue và đọc số phần tử tại thời điểm đó. Ứng dụng không cần tăng hoặc giảm một biến Gauge riêng mỗi khi enqueue hoặc dequeue, miễn là đối tượng được quan sát chính là nguồn trạng thái cần đo.

Nếu queue được thay thế trong quá trình chạy, cần đảm bảo Gauge vẫn quan sát đúng đối tượng hiện hành. Một Gauge đã đăng ký với đối tượng queue cũ không tự động chuyển sang một queue mới chỉ vì biến ứng dụng được gán lại. Khi cần thay nguồn, nên thiết kế một state holder ổn định hoặc đăng ký lại meter theo cơ chế được kiểm soát.

## Giữ tham chiếu mạnh đến đối tượng nguồn

### Vì sao Gauge có thể trả về NaN?

Micrometer thường giữ tham chiếu yếu (weak reference) đến đối tượng nguồn của Gauge. Cách này tránh việc một meter vô tình giữ sống các đối tượng ứng dụng chỉ vì chúng được đo lường.

Hệ quả là ứng dụng phải giữ tham chiếu mạnh (strong reference) đến đối tượng nguồn trong suốt thời gian Gauge cần theo dõi nó. Nếu đối tượng nguồn không còn tham chiếu mạnh ở nơi khác, garbage collector có thể thu hồi đối tượng. Khi đó Gauge không còn đọc được giá trị và có thể trả về NaN. Backend có thể hiển thị giá trị không hợp lệ, bỏ qua mẫu hoặc xử lý theo quy tắc riêng.

Ví dụ sau có nguy cơ sai:

~~~java
Gauge.builder(
        "worker.active",
        new AtomicInteger(0),
        AtomicInteger::get
    )
    .register(registry);
~~~

Đối tượng AtomicInteger được tạo ngay trong lời gọi và không có biến hoặc field nào giữ tham chiếu mạnh đến nó. Sau khi đăng ký, không nên giả định rằng Gauge sẽ giữ đối tượng sống mãi.

Cách an toàn hơn là giữ đối tượng trong field của component:

~~~java
@Component
public class WorkerMetrics {

    private final AtomicInteger activeWorkers = new AtomicInteger();

    public WorkerMetrics(MeterRegistry registry) {
        Gauge.builder(
                "worker.active",
                activeWorkers,
                AtomicInteger::get
            )
            .description("So worker dang hoat dong")
            .register(registry);
    }

    public void workerStarted() {
        activeWorkers.incrementAndGet();
    }

    public void workerFinished() {
        activeWorkers.decrementAndGet();
    }
}
~~~

Field activeWorkers giữ tham chiếu mạnh trong suốt vòng đời của WorkerMetrics. Gauge có thể tiếp tục đọc giá trị hiện tại miễn là component và đối tượng nguồn còn tồn tại.

Quy tắc cần nhớ là **giữ đối tượng nguồn sống đủ lâu**, không phải chỉ giữ đối tượng Gauge trả về. Việc lưu handle Gauge trong một field có thể hữu ích cho quản lý meter, nhưng tự nó không thay thế tham chiếu mạnh đến đối tượng nguồn.

### Đối tượng nguồn phải phản ánh trạng thái thực

Nếu Gauge theo dõi một collection, collection đó cần là nguồn dữ liệu chính xác cho trạng thái cần quan sát. Nếu ứng dụng duy trì một biến đếm riêng, biến đó phải được cập nhật trên mọi đường thành công, thất bại, timeout và hủy tác vụ.

Một biến đếm trạng thái bị bỏ sót thao tác decrement có thể tăng mãi dù số request thực tế đã giảm. Ngược lại, decrement hai lần có thể khiến Gauge âm. Cần thiết kế cập nhật trạng thái trong các khối try/finally hoặc cơ chế lifecycle tương đương để bảo đảm mọi đường thoát đều cân bằng.

Với nhiều luồng cùng cập nhật, dùng cấu trúc đồng bộ hoặc thread-safe phù hợp. Không dùng một biến long hoặc int thông thường được nhiều thread đọc/ghi mà không có cơ chế đồng bộ, vì kết quả có thể không nhất quán hoặc có data race.

## Gauge chỉ quan sát khi được đọc

### Tần suất scrape ảnh hưởng độ phân giải

Gauge không phát sự kiện mỗi khi giá trị thay đổi. Registry đọc giá trị khi backend scrape hoặc khi exporter lấy mẫu để gửi dữ liệu. Vì vậy, tần suất thu thập ảnh hưởng khả năng quan sát biến động.

Ví dụ, hàng đợi tăng lên 100 phần tử rồi giảm về 0 trong khoảng giữa hai lần scrape. Nếu không có lần đọc nào trong lúc backlog đạt 100, dashboard có thể không bao giờ hiển thị đỉnh đó.

Điều này không có nghĩa Gauge đọc sai. Gauge trả lời câu hỏi về trạng thái tại thời điểm quan sát. Nếu cần ghi nhận mọi sự kiện enqueue/dequeue, tổng số tác vụ hoặc số lần hàng đợi vượt ngưỡng, cần thêm Counter hoặc một cơ chế sự kiện phù hợp. Nếu cần phân phối thời gian chờ của từng tác vụ, hãy đo bằng Timer.

Có thể điều chỉnh chu kỳ scrape hoặc push để quan sát thường xuyên hơn, nhưng thu thập quá dày làm tăng chi phí ingest, lưu trữ và truy vấn. Chọn tần suất theo tốc độ thay đổi và mục tiêu vận hành.

### Gauge không lưu lịch sử các trạng thái trung gian

Giả sử số kết nối đang mở thay đổi như sau:

~~~text
Thoi gian:  10:00:00  10:00:01  10:00:02  10:00:03
Gia tri:         2         8         5         3
Scrape:          *                             *
~~~

Backend chỉ quan sát được giá trị tại những thời điểm scrape. Nếu chỉ scrape lúc 10:00:00 và 10:00:03, dữ liệu có thể ghi nhận 2 rồi 3; các giá trị 8 và 5 không xuất hiện trong chuỗi dữ liệu.

Nếu yêu cầu là phát hiện đỉnh số kết nối hoặc backlog trong một khoảng thời gian, cần chọn chu kỳ thu thập phù hợp hoặc bổ sung một meter thống kê khác. Không thể suy ra chính xác giá trị cực đại đã xảy ra giữa hai lần scrape chỉ từ các mẫu Gauge còn lại.

## Gauge và các loại meter khác

| Nhu cầu | Meter nên dùng | Lý do |
|---|---|---|
| Tổng số request đã nhận | Counter | Số sự kiện tích lũy |
| Số request đang xử lý | Gauge | Trạng thái đồng thời hiện tại |
| Thời gian xử lý mỗi request | Timer | Ghi nhận thời lượng và phân phối |
| Kích thước payload từng request | DistributionSummary | Ghi nhận phân phối giá trị |
| Số lần hàng đợi được thêm phần tử | Counter | Sự kiện enqueue tích lũy |
| Số phần tử đang nằm trong hàng đợi | Gauge | Kích thước hiện tại |
| Số lần hàng đợi vượt ngưỡng | Counter | Sự kiện vượt ngưỡng |
| Thời gian một tác vụ nằm trong hàng đợi | Timer | Thời lượng chờ của từng tác vụ |

Một hệ thống có thể dùng nhiều meter cho cùng một thành phần vì mỗi meter trả lời một câu hỏi khác nhau. Ví dụ, với worker pool, Gauge đo số worker đang bận, Counter đo tổng số job hoàn tất và Timer đo thời gian xử lý mỗi job. Không nên ép tất cả các số đo vào một Gauge duy nhất.

Gauge thường không có ý nghĩa khi áp dụng hàm rate như với Counter. Nếu muốn biết tốc độ tăng của một trạng thái, có thể phân tích chuỗi Gauge theo thời gian, nhưng kết quả là tốc độ biến thiên của trạng thái và phải được diễn giải khác với tốc độ sự kiện. Đối với số lượng sự kiện, hãy dùng Counter và hàm rate phù hợp.

## Tích hợp Gauge trong Spring Boot

Trong Spring Boot, nên đăng ký Gauge một lần khi component được khởi tạo và inject MeterRegistry qua constructor. Đối tượng nguồn được giữ trong field để tránh bị garbage collector thu hồi.

Ví dụ theo dõi số tác vụ đang hoạt động:

~~~java
@Component
public class TaskMetrics {

    private final AtomicInteger activeTasks = new AtomicInteger();

    public TaskMetrics(MeterRegistry registry) {
        Gauge.builder(
                "task.active",
                activeTasks,
                AtomicInteger::get
            )
            .description("So tac vu dang hoat dong")
            .tag("component", "worker")
            .register(registry);
    }

    public void execute(Task task) {
        activeTasks.incrementAndGet();
        try {
            task.run();
        } finally {
            activeTasks.decrementAndGet();
        }
    }
}
~~~

Khi component được tạo, Gauge được đăng ký trên registry do Spring cung cấp. Mỗi lần task bắt đầu, trạng thái tăng; trong mọi trường hợp kết thúc, finally giảm trạng thái. Khi registry lấy mẫu, nó đọc giá trị hiện tại của activeTasks.

Nếu ứng dụng có nhiều worker hoặc nhiều loại tác vụ, có thể dùng tag có tập giá trị hữu hạn như component hoặc task_type. Không tạo một tag mới cho từng task ID, request ID hoặc user ID vì số chuỗi dữ liệu sẽ tăng theo số đối tượng được xử lý.

Với queue do Spring hoặc thư viện khác quản lý, có thể đăng ký Gauge trên chính queue nếu có quyền truy cập đến đối tượng đó và API đọc kích thước phù hợp. Cần giữ tham chiếu queue ổn định trong component quản lý.

## Đồng bộ và hiệu năng của hàm đọc Gauge

Hàm đọc Gauge được gọi khi registry lấy mẫu. Hàm này nên nhẹ, nhanh, không chặn và không tạo tác dụng phụ.

Nên ưu tiên:

- Đọc một AtomicInteger hoặc AtomicLong.
- Đọc size hoặc một thuộc tính trạng thái có chi phí thấp.
- Dùng API thread-safe nếu đối tượng được nhiều luồng cập nhật.
- Trả về giá trị có ý nghĩa ngay cả khi hệ thống đang khởi tạo hoặc dừng.

Tránh thực hiện truy vấn cơ sở dữ liệu, gọi HTTP, chờ lock dài hoặc duyệt một cấu trúc dữ liệu rất lớn trong hàm đọc Gauge. Những thao tác đó có thể làm chậm chu kỳ scrape, giữ thread thu thập metrics hoặc tạo tải phụ lên hệ thống đang được giám sát.

Không cập nhật trạng thái bên trong hàm đọc Gauge. Supplier chỉ nên quan sát, không tăng/giảm bộ đếm hay thực hiện nghiệp vụ. Nếu mỗi lần đọc đều làm thay đổi giá trị, số đo sẽ phụ thuộc vào tần suất scrape và không còn phản ánh trạng thái thực.

Nếu cần tính toán phức tạp, có thể cập nhật một giá trị tổng hợp riêng trong luồng nghiệp vụ hoặc tác vụ nền, sau đó để Gauge đọc giá trị đã được chuẩn bị. Cần cân nhắc độ mới của giá trị tổng hợp và bảo đảm đồng bộ khi nhiều luồng cập nhật.

## Tổng hợp Gauge giữa nhiều instance

Khi chạy nhiều instance, mỗi instance thường xuất một Gauge cho trạng thái cục bộ. Việc tổng hợp các giá trị này phải dựa trên ý nghĩa của đại lượng.

Ví dụ, tổng số phần tử đang chờ trên tất cả hàng đợi có thể được tính bằng tổng Gauge của từng instance nếu mỗi queue là một phần riêng biệt. Nhưng mức sử dụng CPU hoặc độ dài queue trung bình có thể cần phép tổng hợp khác. Với số worker đang hoạt động trên mỗi instance, tổng có thể hữu ích để biết số worker đang bận toàn hệ thống; giá trị max có thể hữu ích để tìm instance chịu tải cao nhất.

Không mặc định rằng mọi Gauge đều có thể cộng. Nếu mỗi instance báo phần trăm sử dụng pool, cộng phần trăm giữa các instance không có ý nghĩa. Có thể cần tính trung bình có trọng số theo dung lượng pool hoặc hiển thị từng instance riêng.

Các tag như service, region, instance hoặc pool giúp phân biệt nguồn đo. Tag phải có cardinality phù hợp với vòng đời và quy mô triển khai. Với instance động, cần hiểu cách backend loại bỏ series cũ khi instance dừng để tránh dữ liệu cũ bị nhầm thành trạng thái hiện tại.

## Kiểm thử Gauge

Có thể dùng SimpleMeterRegistry để xác minh Gauge đọc giá trị hiện tại từ đối tượng nguồn:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
AtomicInteger activeTasks = new AtomicInteger(3);

Gauge.builder("task.active", activeTasks, AtomicInteger::get)
    .register(registry);

assertThat(registry.get("task.active")
    .gauge()
    .value()).isEqualTo(3.0);

activeTasks.set(5);

assertThat(registry.get("task.active")
    .gauge()
    .value()).isEqualTo(5.0);
~~~

Kiểm thử này xác nhận Gauge đọc giá trị mới từ cùng đối tượng nguồn thay vì giữ một bản sao giá trị tại thời điểm đăng ký.

Với component thực tế, nên kiểm tra:

1. Gauge được đăng ký đúng tên và tag.
2. Giá trị ban đầu phản ánh trạng thái ban đầu.
3. Các thao tác tăng, giảm hoặc thay đổi collection làm Gauge phản ánh giá trị mới.
4. Các đường thành công, exception, timeout và hủy tác vụ đều cập nhật trạng thái cân bằng.
5. Đối tượng nguồn còn được giữ sống trong vòng đời cần quan sát.
6. Hàm đọc không thực hiện I/O hoặc thao tác chặn.
7. Exporter thực tế xuất được giá trị và dashboard diễn giải đúng đơn vị.

SimpleMeterRegistry kiểm tra hành vi ở lớp Micrometer. Nó không chứng minh backend sẽ scrape đúng chu kỳ, giữ series cũ hay hiển thị giá trị NaN theo cách nào. Các chi tiết đó cần được kiểm tra ở tầng exporter và backend.

## Cardinality và vòng đời của Gauge

Gauge thường được tạo cho một đối tượng hoặc một nhóm trạng thái. Nếu ứng dụng tạo Gauge cho từng user, từng request hoặc từng job rồi gắn ID duy nhất vào tag, số time series sẽ tăng nhanh và tạo áp lực lên bộ nhớ, ingest, lưu trữ và truy vấn.

Nên ưu tiên các nhóm có tập giá trị hữu hạn, chẳng hạn queue_name, pool, component hoặc outcome. Nếu cần theo dõi trạng thái của hàng triệu đối tượng riêng lẻ, metrics thường không phải công cụ phù hợp; log, trace hoặc hệ thống lưu trữ trạng thái chuyên biệt có thể đáp ứng tốt hơn.

Cũng cần xác định thời điểm đối tượng nguồn kết thúc vòng đời. Nếu object bị thu hồi, Gauge không còn đọc được giá trị. Nếu một đối tượng mới thay thế đối tượng cũ, cần cập nhật cơ chế đăng ký hoặc sử dụng một state holder ổn định để Gauge tiếp tục quan sát đúng nguồn.

Không đăng ký lại Gauge trong mỗi request hoặc mỗi lần cập nhật trạng thái. Hãy đăng ký một lần cho mỗi danh tính meter ổn định và cập nhật đối tượng nguồn. Micrometer quản lý meter theo tên, tag và loại; đăng ký lặp cùng danh tính không tạo ra một chuỗi độc lập cho từng lần gọi.

## Những sai lầm thường gặp

**Dùng Gauge để đếm tổng sự kiện.** Gauge phản ánh trạng thái hiện tại. Tổng số request hoặc job đã hoàn tất nên dùng Counter.

**Không giữ tham chiếu đến đối tượng nguồn.** Gauge có thể mất khả năng đọc khi đối tượng bị garbage collector thu hồi và trả về NaN. Giữ đối tượng trong field hoặc một cấu trúc quản lý vòng đời phù hợp.

**Giả định Gauge ghi lại mọi thay đổi.** Gauge chỉ được đọc khi scrape hoặc lấy mẫu. Các trạng thái trung gian giữa hai lần đọc có thể không xuất hiện.

**Tạo một biến đếm nhưng quên giảm ở nhánh lỗi.** Trạng thái sẽ bị lệch theo thời gian. Dùng try/finally hoặc cơ chế lifecycle tương đương để cân bằng.

**Dùng supplier chậm hoặc có tác dụng phụ.** Hàm đọc Gauge nên nhẹ và chỉ quan sát. Tránh I/O, lock dài hoặc cập nhật nghiệp vụ trong supplier.

**Cộng mọi Gauge giữa các instance.** Chỉ tổng hợp khi đại lượng có ý nghĩa cộng được. Phần trăm hoặc mức sử dụng tương đối thường cần cách tổng hợp khác.

**Tạo tag có giá trị duy nhất cho từng đối tượng.** Cardinality tăng mạnh và làm chi phí giám sát khó kiểm soát. Dùng nhóm hữu hạn hoặc công cụ quan sát khác cho định danh chi tiết.

## Checklist thiết kế Gauge

Trước khi đưa Gauge vào vận hành, hãy xác minh:

1. Giá trị có thực sự biểu diễn trạng thái hiện tại không?
2. Nếu cần đếm sự kiện hoặc đo thời lượng, đã chọn Counter hoặc Timer phù hợp chưa?
3. Đối tượng nguồn có được giữ bằng tham chiếu mạnh trong suốt vòng đời cần đo không?
4. Hàm đọc có nhanh, an toàn khi chạy đồng thời và không có tác dụng phụ không?
5. Mọi đường bắt đầu/kết thúc tác vụ có cập nhật trạng thái cân bằng không?
6. Tần suất scrape có đủ để quan sát biến động quan trọng không?
7. Có chấp nhận bỏ lỡ các giá trị đỉnh giữa hai lần scrape không?
8. Phép tổng hợp giữa các instance có phù hợp với ngữ nghĩa của đại lượng không?
9. Tag có tập giá trị hữu hạn và cardinality được kiểm soát không?
10. Kiểm thử có xác nhận Gauge đọc giá trị mới và exporter thực sự xuất số đo không?

## Kết luận

Gauge của Micrometer cung cấp một phép quan sát trạng thái hiện tại của đối tượng tại thời điểm registry lấy mẫu. Nó phù hợp với số request đang hoạt động, kích thước hàng đợi, số kết nối đang mở và những đại lượng có thể tăng giảm trong quá trình ứng dụng chạy.

Để Gauge đáng tin cậy, hãy giữ tham chiếu mạnh đến đối tượng nguồn, dùng dữ liệu thread-safe, giữ hàm đọc nhẹ và chỉ quan sát, đồng thời phân biệt trạng thái hiện tại với sự kiện tích lũy và thời lượng. Tần suất scrape, cardinality và cách tổng hợp giữa các instance cũng phải phù hợp với ý nghĩa của số đo.
