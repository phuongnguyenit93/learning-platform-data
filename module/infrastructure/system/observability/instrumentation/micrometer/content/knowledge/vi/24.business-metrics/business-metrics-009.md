# Đối chiếu phép đo với tải thử nghiệm hoặc dữ liệu nghiệp vụ có kiểm soát

## Vì sao cần đối chiếu metrics với nguồn sự thật?

Một metric xuất hiện trong registry hoặc backend chưa chứng minh rằng nó đo đúng nghiệp vụ. Counter có thể tăng hai lần cho một đơn hàng do retry; Timer có thể đo thời gian submit thay vì thời gian xử lý; Gauge có thể đọc một collection không được cập nhật đồng bộ; histogram có thể thiếu bucket vì cấu hình export. Những sai lệch này vẫn tạo ra biểu đồ hợp lệ về mặt kỹ thuật nhưng dẫn đến quyết định vận hành sai.

Đối chiếu metrics là quá trình so sánh số liệu Micrometer với một nguồn sự thật độc lập và có kiểm soát. Nguồn này có thể là tải thử nghiệm biết trước số request, một tập dữ liệu nghiệp vụ xác định, bảng giao dịch, event ledger, hoặc kết quả từ một hệ thống kiểm thử có khả năng đếm chính xác.

Trong module **OBSERVABILITY_INSTRUMENTATION_MICROMETER**, ứng dụng sử dụng Counter, Gauge, Timer, DistributionSummary và tag để đo lường, tích hợp Spring Boot và xuất metrics đến hệ giám sát. Đối chiếu giúp xác nhận instrumentation đang đo đúng sự kiện, đúng ranh giới thời gian, đúng đơn vị và đúng phạm vi tổng hợp.

Cần trả lời ba câu hỏi:

1. **Đo cái gì?** Metric đại diện cho request được nhận, nghiệp vụ thành công, lần thử xử lý hay trạng thái hiện tại?
2. **Đếm ở đâu?** Sự kiện được ghi trước transaction, sau commit, khi message được nhận hay khi tác vụ hoàn tất?
3. **So với nguồn nào?** Dữ liệu kiểm thử, database, event ledger hay số liệu độc lập từ load generator?

Nếu chưa xác định được ba điều này, so sánh hai con số có thể không có ý nghĩa dù chúng cùng mang tên count.

## Xác định hợp đồng đo lường trước khi chạy thử

### Mô tả ranh giới của từng metric

Trước khi đối chiếu, hãy viết rõ hợp đồng cho từng meter:

| Thành phần | Cần xác định | Ví dụ |
|---|---|---|
| Tên meter | Tên ổn định và có ý nghĩa | orders.completed |
| Loại meter | Counter, Gauge, Timer, DistributionSummary | Counter |
| Đơn vị | requests, orders, seconds, bytes | orders |
| Sự kiện ghi nhận | Điều kiện chính xác làm meter thay đổi | Đơn hàng được commit thành công |
| Ranh giới thời gian | Bắt đầu và kết thúc đo ở đâu | Từ lúc bắt đầu xử lý đến khi commit |
| Tag | Các chiều phân loại có tập giá trị hữu hạn | outcome, channel |
| Phạm vi | Một instance, một service hay toàn hệ thống | Toàn bộ checkout service |
| Nguồn đối chiếu | Dữ liệu độc lập dùng làm ground truth | Bảng orders đã commit |
| Quy tắc retry | Đếm attempt hay business operation | Một order chỉ đếm một lần hoàn tất |
| Độ trễ dữ liệu | Khi nào số liệu được xem là ổn định | Sau khi queue đã drain |

Ví dụ, tên **orders.completed** phải có một định nghĩa duy nhất. Nếu meter tăng khi nhận request nhưng database chỉ ghi đơn hàng sau commit, nó thực chất đo số lần tiếp nhận chứ không phải số đơn hàng hoàn tất. Có thể giữ cả hai meter, nhưng cần đặt tên khác nhau như orders.accepted và orders.completed.

### Phân biệt attempt, request và business outcome

Một request có thể được thử nhiều lần do retry. Một message có thể được nhận nhiều lần do redelivery. Một đơn hàng có thể đi qua nhiều bước xử lý trước khi hoàn tất.

Các đại lượng sau không nhất thiết bằng nhau:

- Số request client gửi.
- Số request server nhận.
- Số lần handler được gọi.
- Số lần xử lý thành công.
- Số giao dịch được commit.
- Số bản ghi nghiệp vụ duy nhất.
- Số message được acknowledge.

Nếu retry được bật, số attempt có thể lớn hơn số business operation. Nếu client timeout sau khi server đã commit, client có thể gửi lại request và tạo thêm attempt dù đơn hàng chỉ được tạo một lần nhờ idempotency key.

Hãy quyết định meter cần phản ánh từng lần thử hay kết quả nghiệp vụ duy nhất. Không ép các số liệu khác ngữ nghĩa phải bằng nhau.

## Đối chiếu bằng tải thử nghiệm có kiểm soát

### Chuẩn bị môi trường thử nghiệm

Một bài load test có giá trị đối chiếu cần kiểm soát các yếu tố có thể làm thay đổi kết quả:

- Dùng môi trường cô lập hoặc namespace dữ liệu riêng.
- Xác định phiên bản ứng dụng, cấu hình Micrometer và registry.
- Ghi lại số instance, số worker và cấu hình retry.
- Dùng dataset có ID riêng để truy vấn lại sau thử nghiệm.
- Tắt hoặc cô lập traffic ngoài kịch bản nếu có thể.
- Xác định thời điểm bắt đầu, kết thúc và thời gian chờ hệ thống ổn định.
- Đảm bảo dashboard hoặc exporter đang đọc đúng service và môi trường.
- Làm rõ metric cumulative, step hay windowed trước khi lấy số.

Không nên chạy thử nghiệm trên môi trường có traffic không kiểm soát rồi so tổng counter với số request do load generator gửi. Metrics có thể bao gồm traffic khác, health check, retry hoặc background job.

### Thiết kế workload có ground truth

Một kịch bản đơn giản có thể gửi 1.000 request với kết quả dự kiến:

| Kịch bản | Số request | Kết quả dự kiến |
|---|---:|---|
| Đặt hàng thành công | 700 | 700 đơn hàng commit |
| Bị từ chối do validation | 150 | 150 request rejected, không có đơn hàng |
| Lỗi nghiệp vụ hoặc dependency | 100 | 100 lần xử lý failure |
| Timeout phía client | 50 | Cần kiểm tra server có tiếp tục xử lý hay không |
| Tổng | 1.000 | 1.000 request được phát từ test |

Các con số trong bảng là dữ liệu kịch bản, không phải kỳ vọng rằng mọi metric đều bằng 1.000. Nếu meter orders.completed chỉ tăng sau commit, kết quả dự kiến là 700. Nếu meter http.server.requests đo mọi request được server xử lý, số count có thể khác 1.000 do client timeout, retry, request không tới server hoặc instrumentation nằm ở ranh giới khác.

Với timeout, phải kiểm tra kết quả phía server. Client timeout không chứng minh server đã dừng xử lý. Một số request có thể hoàn tất sau khi client ngừng chờ.

### Chia workload thành các pha

Một bài thử nghiệm dễ phân tích nên chia thành các pha:

1. **Baseline:** khởi động ứng dụng, chờ binder và exporter ổn định, ghi lại số đo ban đầu.
2. **Warm-up:** gửi một lượng request nhỏ để khởi tạo connection pool, JIT và cache; không gộp pha này vào kết quả chính nếu không chủ đích.
3. **Load:** phát workload có số lượng và phân bố outcome đã biết.
4. **Drain:** ngừng phát request và chờ các tác vụ bất đồng bộ, queue và transaction hoàn tất.
5. **Snapshot:** lấy metrics, dữ liệu database và event ledger trong cùng phạm vi.
6. **Compare:** tính chênh lệch và xác định nguyên nhân nếu số liệu không khớp.

Nếu dùng registry step-based, cần chờ step chứa dữ liệu cuối cùng được publish. Nếu dùng Prometheus pull, cần chờ ít nhất một lần scrape sau khi workload kết thúc. Với OTLP push, cần chờ registry export và Collector xử lý xong dữ liệu.

## Đối chiếu Counter với số sự kiện dự kiến

### Kiểm tra count trong một lần chạy xác định

Giả sử mỗi đơn hàng chỉ tăng Counter sau khi transaction commit:

~~~java
@Service
public class OrderMetrics {

    private final Counter completed;

    public OrderMetrics(MeterRegistry registry) {
        this.completed = Counter.builder("orders.completed")
            .description("So don hang da commit thanh cong")
            .baseUnit("orders")
            .register(registry);
    }

    public void recordCompleted() {
        completed.increment();
    }
}
~~~

Điểm gọi recordCompleted phải tương ứng với sự kiện commit thành công. Nếu gọi trước commit rồi transaction rollback, metric sẽ tăng dù không có đơn hàng trong nguồn dữ liệu nghiệp vụ.

Trong hệ thống dùng transaction event, có thể ghi nhận sau commit bằng transaction synchronization hoặc sự kiện được phát sau khi commit. Cần chọn cơ chế phù hợp với framework và tránh ghi meter trước khi biết kết quả cuối cùng.

### So sánh với nguồn dữ liệu nghiệp vụ

Sau khi workload drain, truy vấn nguồn dữ liệu độc lập:

~~~sql
SELECT COUNT(*)
FROM orders
WHERE test_run_id = :run_id
  AND status = 'COMPLETED';
~~~

Nếu metric có tag outcome=success và chỉ đếm đơn hàng đã commit, giá trị Counter trong phạm vi test cần tương ứng với số bản ghi hoàn tất của run đó, sau khi đã xử lý đúng instance, tag và thời gian.

Không thể truy vấn Counter Micrometer theo test_run_id nếu tag này không được thiết kế và kiểm soát. Không nên thêm run ID duy nhất vào metric tag chỉ để tiện đối chiếu vì mỗi lần chạy sẽ tạo series mới. Có thể dùng dataset riêng trong database, log correlation hoặc một test registry cô lập để phân biệt run.

### Retry và idempotency

Giả sử một order được xử lý ba attempt nhưng chỉ commit một lần. Nếu Counter đo handler invocation, giá trị có thể tăng ba. Nếu Counter đo order completion duy nhất, giá trị phải tăng một.

Nên có meter riêng khi cả hai số đều có giá trị:

- orders.processing.attempts: số lần handler bắt đầu xử lý.
- orders.completed: số đơn hàng hoàn tất duy nhất.
- orders.processing.failures: số attempt thất bại.

Đừng dùng cùng một tên meter cho hai semantics. Khi đối chiếu, xác định dữ liệu ledger có lưu attempt hay chỉ lưu trạng thái cuối của business operation.

## Đối chiếu Timer với thời lượng thực tế

### Count của Timer và số operation đã đo

Timer ghi nhận một observation cho mỗi lần record hoặc mỗi sample được stop. Nếu một method chỉ được đo một lần cho mỗi operation hoàn tất, Timer count cần khớp số operation trong cùng phạm vi.

Ví dụ:

~~~java
Timer processing = Timer.builder("orders.processing")
    .description("Thoi gian xu ly mot don hang")
    .register(registry);

processing.record(() -> orderProcessor.process(command));
~~~

Nếu method ném exception, Timer.record vẫn ghi thời lượng của lần thực thi. Vì vậy, count của Timer có thể bao gồm cả success và failure. Nếu chỉ muốn đo số lần thành công, cần một Timer riêng hoặc tag outcome được chọn theo kết quả cuối cùng.

Không giả định Timer count luôn bằng Counter orders.completed. Chúng chỉ bằng nhau khi cùng đo một tập operation và cùng quy tắc kết thúc.

### So sánh tổng thời gian và mean

Timer cung cấp count và total time. Với một tập operation xác định:

~~~text
mean duration = total time / count
~~~

Có thể đối chiếu total time với bộ đo độc lập trong test harness, nhưng hai phép đo không nhất thiết trùng tuyệt đối. Test harness có thể tính cả network, serialization hoặc thời gian chờ client; Timer trong service có thể chỉ đo phần xử lý bên trong method.

Hãy xác định cùng một ranh giới bắt đầu/kết thúc trước khi so sánh. Với độ trễ thực tế, dùng tolerance thay vì yêu cầu bằng tuyệt đối vì scheduler, clock, JIT và overhead instrumentation có thể tạo sai khác nhỏ.

Ví dụ test với thời lượng được ghi xác định:

~~~java
SimpleMeterRegistry registry = new SimpleMeterRegistry();
Timer timer = registry.timer("test.operation");

timer.record(50, TimeUnit.MILLISECONDS);
timer.record(150, TimeUnit.MILLISECONDS);

assertThat(timer.count()).isEqualTo(2);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
    .isCloseTo(200.0, within(0.001));
~~~

Đây là kiểm thử API ghi nhận và chuyển đổi đơn vị. Nó không thay thế load test đo thời gian thực của ứng dụng.

### Kiểm tra histogram bucket và SLO

Nếu Timer xuất histogram, bucket là số quan sát tích lũy không vượt quá từng ngưỡng. Với các bucket 100 ms, 300 ms và +Inf:

- Bucket 100 ms phải không lớn hơn bucket 300 ms.
- Bucket 300 ms phải không lớn hơn bucket +Inf.
- Bucket +Inf phải tương ứng tổng count của histogram.
- Các bucket cần cùng đơn vị và ranh giới giữa các instance.

Nếu kịch bản tạo 700 thao tác và tất cả đều hoàn tất, tổng count trong histogram phải phản ánh 700 observation nếu Timer đo đúng tập operation đó. Số lượng trong bucket theo SLO giúp đối chiếu tỷ lệ thao tác hoàn tất dưới ngưỡng.

Ví dụ tỷ lệ hoàn tất không quá 300 ms:

~~~promql
sum(rate(orders_processing_seconds_bucket{le="0.3"}[5m]))
/
sum(rate(orders_processing_seconds_count[5m]))
~~~

Truy vấn cần điều chỉnh theo tên metric và label thực tế của exporter. Nếu không có observation trong cửa sổ, phép chia không có mẫu để diễn giải; không coi kết quả thiếu là latency bằng 0.

## Đối chiếu Gauge với snapshot trạng thái

Gauge mô tả giá trị hiện tại, chẳng hạn số job đang chờ, số connection đang active hoặc số worker đang bận. Gauge không phải bộ đếm sự kiện.

Để kiểm tra Gauge, cần chụp trạng thái nguồn và đọc Gauge gần cùng thời điểm. Ví dụ:

~~~java
AtomicInteger queueDepth = new AtomicInteger();

Gauge.builder("jobs.queue.depth", queueDepth, AtomicInteger::get)
    .register(registry);
~~~

Trong test, có thể đặt queueDepth thành 7 và xác minh Gauge trả về 7. Với queue thực tế, cần xác định size() có thread-safe và có phản ánh đúng trạng thái tại thời điểm đọc không.

Không cộng các giá trị Gauge qua nhiều lần scrape để suy ra tổng số job. Nếu queue depth dao động 10, 4, 12, đây là ba snapshot của trạng thái; tổng 26 không có ý nghĩa nghiệp vụ.

Với nhiều instance, queue depth toàn hệ thống có thể là tổng độ sâu các queue nếu mỗi job chỉ nằm trong một queue. Nhưng max queue depth có thể hữu ích hơn để phát hiện một instance bị nghẽn. Chọn phép tổng hợp theo câu hỏi vận hành.

## Đối chiếu DistributionSummary

DistributionSummary phù hợp với giá trị số như kích thước payload, số bản ghi mỗi batch hoặc dung lượng file. Mỗi lần record tạo một observation.

Với một dataset có các kích thước đã biết 100, 200 và 500 bytes:

~~~java
DistributionSummary payloadSize =
    DistributionSummary.builder("request.payload.size")
        .baseUnit("bytes")
        .register(registry);

payloadSize.record(100);
payloadSize.record(200);
payloadSize.record(500);
~~~

Kỳ vọng trong registry cumulative:

- Count bằng 3.
- Total amount bằng 800 bytes.
- Mean bằng khoảng 266,67 bytes.
- Max trong cửa sổ còn chứa mẫu bằng 500 bytes.

Max và percentile có thể chịu expiry/buffer window; count và total amount phụ thuộc temporality của registry. Khi đối chiếu cần xác định registry cumulative hay step và thống kê nào đang được so sánh.

Không so sánh tổng payload bytes với tổng số request nếu metric ghi nhận kích thước nhiều lần cho mỗi request hoặc chỉ ghi nhận sau khi request được xử lý thành công.

## Đối chiếu với database hoặc event ledger

### Chọn nguồn sự thật độc lập

Nguồn đối chiếu nên độc lập với chính code đang cập nhật metric. Nếu Counter và bảng summary cùng được tăng trong một nhánh code sai, chúng có thể cùng sai nhưng vẫn khớp nhau.

Nguồn tốt có thể là:

- Bảng giao dịch được commit.
- Event ledger bất biến.
- Bảng audit do transaction ghi nhận.
- Dataset do test harness tạo và kiểm tra sau chạy.
- Message broker offset hoặc số message đã acknowledge, nếu đó là đại lượng cần đo.

Nguồn dữ liệu phải trả lời cùng câu hỏi với metric. Nếu metric đếm order đã hoàn tất, bảng nguồn cần lọc đúng trạng thái hoàn tất và phạm vi thời gian tương ứng.

### Đồng bộ phạm vi thời gian

Một lỗi phổ biến là so metric theo thời gian scrape với database theo thời điểm tạo bản ghi. Hai hệ thống có thể dùng timestamp khác nhau:

- Event time: thời điểm sự kiện nghiệp vụ thực sự xảy ra.
- Processing time: thời điểm ứng dụng xử lý sự kiện.
- Commit time: thời điểm transaction được commit.
- Ingestion time: thời điểm dữ liệu được đưa vào hệ thống phân tích.
- Scrape/export time: thời điểm metric được thu thập hoặc gửi đi.

Với xử lý bất đồng bộ, event có thể xảy ra trước nhưng chỉ được commit sau. Nếu query database theo created_at trong khi metric tăng lúc completed, các cửa sổ có thể lệch nhau.

Nên dùng khoảng thời gian nửa mở [from, to) và một timezone thống nhất. Ghi lại timestamp bắt đầu/kết thúc của test run, đồng thời chờ queue drain hoặc độ trễ xử lý ổn định trước khi chốt kết quả.

### Eventual consistency và dữ liệu đến muộn

Một số hệ thống cập nhật database, search index hoặc data warehouse bất đồng bộ. Metrics có thể tăng ngay sau khi xử lý xong, trong khi dữ liệu phân tích xuất hiện trễ vài phút.

Nếu đối chiếu quá sớm, sẽ thấy metrics lớn hơn database. Đây có thể là độ trễ đồng bộ chứ không phải instrumentation sai.

Hãy xác định SLA cập nhật dữ liệu của nguồn đối chiếu. Có thể thực hiện polling có giới hạn đến khi dataset đạt trạng thái ổn định, hoặc dùng event ledger đồng bộ hơn. Ghi rõ thời điểm snapshot và độ trễ chấp nhận được.

### Transaction rollback và ghi metric

Nếu metric được tăng trước commit, rollback có thể khiến Counter lớn hơn số bản ghi cuối cùng. Nếu chỉ tăng sau commit, có thể tránh đếm giao dịch thất bại, nhưng cần xử lý trường hợp tiến trình dừng ngay sau commit trước khi metric được cập nhật.

Metrics trong bộ nhớ không phải hệ thống lưu trữ giao dịch bền vững. Nếu cần đối soát chính xác tuyệt đối, nguồn sự thật phải là database/event ledger; metric là tín hiệu vận hành. Transactional outbox hoặc sự kiện sau commit có thể giúp đồng bộ sự kiện, nhưng vẫn cần thiết kế idempotency và xử lý retry.

## Xử lý nhiều instance và counter reset

Khi chạy nhiều instance, mỗi instance có thể có một meter cùng tên và tag nhưng series riêng theo resource hoặc instance label. Ground truth toàn service cần so với tổng của các instance trong cùng cửa sổ.

Với cumulative counter, nên tính rate hoặc increase trên từng series trước rồi mới tổng hợp để Prometheus xử lý reset riêng của từng instance:

~~~promql
sum by (service) (
  increase(orders_completed_total[10m])
)
~~~

Không sum raw counter trước rồi mới tính rate nếu cần nhận diện reset từng instance. Nếu instance restart trong test, counter trong process mới có thể bắt đầu lại.

Với step/delta registry, cần cộng các delta thuộc cùng khoảng và xác nhận các instance dùng step tương thích. Không áp dụng query dành cho cumulative counter lên dữ liệu delta nếu backend không chuyển đổi temporality.

Nếu cùng một event được xử lý ở hai instance do retry hoặc redelivery, metrics attempt có thể tăng hai lần trong khi business ledger chỉ có một kết quả. Đây là khác biệt cần giải thích bằng semantics, không phải tự động xem là lỗi.

## Định lượng sai lệch và đặt tolerance

### Sai lệch tuyệt đối và tương đối

Khi so sánh metric với ground truth, có thể tính:

~~~text
absolute_difference = observed - expected

relative_difference =
    (observed - expected) / expected * 100%
~~~

Nếu expected bằng 0, không tính relative difference theo công thức trên; hãy dùng sai lệch tuyệt đối hoặc quy tắc riêng.

Ví dụ expected là 700 đơn hàng và metric quan sát 698:

- Sai lệch tuyệt đối: -2.
- Sai lệch tương đối: khoảng -0,286%.

Không nên tự đặt tolerance giống nhau cho mọi meter. Count của một test xác định sau khi đã drain thường cần khớp chính xác nếu semantics giống nhau. Timer duration có thể cần tolerance. Gauge snapshot cần thời điểm đọc được đồng bộ. Rate từ backend là ước lượng theo scrape interval và cửa sổ truy vấn.

### Tolerance phải xuất phát từ hệ thống

Có thể định nghĩa các loại chấp nhận:

| Loại kiểm tra | Kỳ vọng | Tolerance hợp lý |
|---|---|---|
| Counter nghiệp vụ trong test xác định | Số event commit duy nhất | Thường bằng chính xác sau drain |
| Timer count | Số observation được đo | Chính xác nếu cùng ranh giới |
| Timer total time | Tổng duration của cùng đoạn mã | Sai số nhỏ theo clock và overhead |
| Gauge | Snapshot trạng thái hiện tại | Đồng bộ thời điểm hoặc chấp nhận sai số do concurrent update |
| Rate | Throughput trong cửa sổ | Sai số do scrape interval, sampling và nội suy |
| Histogram percentile | Phân vị ước lượng từ bucket | Phụ thuộc độ rộng bucket và lượng mẫu |
| Dữ liệu warehouse | Tổng hợp nghiệp vụ đến muộn | Theo SLA đồng bộ của nguồn |

Ghi rõ tolerance trong test report. Nếu nới tolerance để test pass mà không giải thích nguồn sai lệch, test sẽ che giấu lỗi instrumentation.

## Ví dụ kiểm thử đối chiếu trong Spring Boot

Có thể viết integration test chạy một tập lệnh xác định, sau đó so registry với kết quả nghiệp vụ. Ví dụ dưới đây minh họa cách kiểm tra count và total time; fixture nghiệp vụ cần cung cấp số kết quả đã commit:

~~~java
@SpringBootTest
class OrderMetricsReconciliationTest {

    @Autowired
    OrderService orderService;

    @Autowired
    MeterRegistry registry;

    @Autowired
    OrderRepository orderRepository;

    @Test
    void metricsMatchCommittedOrders() {
        List<OrderCommand> commands = TestOrders.createSuccessfulCommands(20);

        commands.forEach(orderService::placeOrder);

        long committed = orderRepository.countByTestRunIdAndStatus(
            TestRun.currentId(),
            OrderStatus.COMPLETED
        );

        Counter counter = registry.find("orders.completed").counter();

        assertThat(counter).isNotNull();
        assertThat(counter.count()).isEqualTo((double) committed);
        assertThat(committed).isEqualTo(20);
    }
}
~~~

Đây là khung kiểm thử; tên repository, trạng thái và test fixture phải khớp ứng dụng thực tế. Cần bảo đảm registry được làm sạch hoặc test dùng meter name/tag riêng có kiểm soát để dữ liệu từ test trước không làm sai count. Không dùng test run ID duy nhất làm tag production chỉ để cô lập test.

Nếu Counter được ghi sau commit, test cần gọi service qua transaction boundary thực tế và chờ transaction hoàn tất trước khi đọc meter. Nếu event được xử lý bất đồng bộ, cần chờ consumer drain hoặc điều kiện hoàn tất thay vì sleep tùy ý.

### Kiểm tra Timer count và duration

Có thể mở rộng test để xác minh Timer đo đúng số operation:

~~~java
Timer timer = registry.find("orders.processing")
    .tag("outcome", "success")
    .timer();

assertThat(timer).isNotNull();
assertThat(timer.count()).isEqualTo(20);
assertThat(timer.totalTime(TimeUnit.MILLISECONDS))
    .isGreaterThan(0.0);
~~~

Count có thể so chính xác nếu mỗi order success tạo đúng một observation. Total time nên được so với một giới hạn hoặc phép đo tham chiếu có cùng ranh giới, không so bằng tuyệt đối với tổng thời gian wall-clock của cả test.

## Quy trình đối chiếu đầy đủ

Một quy trình có thể lặp lại cho mỗi lần thay đổi instrumentation:

1. **Đọc định nghĩa meter:** xác nhận tên, loại, đơn vị, tag và sự kiện được đo.
2. **Xác định ground truth:** chọn dataset, bảng giao dịch hoặc event ledger độc lập.
3. **Tạo run ID ở dữ liệu thử nghiệm:** dùng để lọc database/log; không đưa ID duy nhất vào metric tag.
4. **Khởi tạo registry và ghi baseline:** bảo đảm không trộn số liệu từ test trước.
5. **Chạy workload có kiểm soát:** biết số request, outcome, retry và concurrency dự kiến.
6. **Chờ hoàn tất:** drain queue, chờ commit và chờ exporter/scrape/step công bố.
7. **Chụp metrics:** lấy đúng service, instance, label và cửa sổ thời gian.
8. **Chụp nguồn nghiệp vụ:** truy vấn cùng run và cùng quy tắc thời gian.
9. **So sánh theo semantics:** count với count, duration với cùng ranh giới, Gauge với snapshot, bucket với ngưỡng.
10. **Tính sai lệch:** áp dụng tolerance đã định nghĩa trước.
11. **Điều tra chênh lệch:** kiểm tra retry, rollback, duplicate, sampling, reset, late event và cardinality.
12. **Lưu kết quả kiểm thử:** ghi phiên bản ứng dụng, registry, cấu hình và kết luận.

## Khi metrics không khớp ground truth

Không sửa Counter hoặc thêm một increment bù chỉ để dashboard khớp database. Trước hết tìm nguyên nhân ở ranh giới sự kiện và lifecycle.

| Dấu hiệu | Nguyên nhân có thể | Cách xác minh |
|---|---|---|
| Counter lớn hơn số bản ghi | Retry, duplicate delivery, metric tăng trước commit | So attempt log, idempotency key và transaction outcome |
| Counter nhỏ hơn số bản ghi | Bỏ sót nhánh success, event listener không chạy, meter bị filter | Kiểm tra code path và registry |
| Timer count lớn hơn business completion | Timer ghi cả failure hoặc retry attempt | Kiểm tra ranh giới record và tag outcome |
| Timer count nhỏ hơn request count | Chỉ đo một số route hoặc method, async chưa stop | Kiểm tra proxy, callback và instrumentation |
| Timer sum khác test harness | Khác ranh giới đo hoặc đơn vị | So start/stop point và unit conversion |
| Gauge dao động không hợp lý | Nguồn không thread-safe hoặc object bị thay thế | Kiểm tra lifecycle và concurrency |
| Histogram bucket không khớp count | Cấu hình bucket, label hoặc export khác nhau | Kiểm tra exposition và bucket +Inf |
| Backend thấp hơn registry | Export lỗi, scrape thiếu, step chưa publish | Kiểm tra exporter, Collector và thời điểm scrape |
| Database thấp hơn metrics ngay sau test | Eventual consistency hoặc transaction chưa hoàn tất | Chờ drain và SLA đồng bộ |
| Số tổng nhiều instance bị lệch | Counter reset, instance trùng hoặc query sai | Kiểm tra từng series trước aggregation |

## Cardinality trong thử nghiệm đối chiếu

Test có thể cần phân biệt các kịch bản, nhưng không nên tạo tag có giá trị duy nhất cho mỗi request hoặc mỗi lần chạy. Một test tạo 10.000 request ID và đưa tất cả vào tag có thể làm registry phát sinh 10.000 meter chỉ trong một lượt.

Dùng tag có tập giá trị hữu hạn như:

- scenario: success, validation_failure, dependency_timeout.
- outcome: success, failure, timeout.
- operation: create_order, cancel_order, refund.
- region: các vùng triển khai đã định nghĩa.

Dùng run ID trong database, log hoặc test report để lọc dữ liệu. Nếu cần kiểm thử meter theo từng kịch bản trong một registry cô lập, có thể dùng tên/tag test riêng ở môi trường test, nhưng không mang quy ước đó sang production.

## Những sai lầm thường gặp

**So mọi Counter với số request load generator gửi.** Request có thể không đến server, bị retry hoặc kết thúc trước/sau ranh giới đo. Chọn nguồn sự thật cùng semantics.

**Đối chiếu quá sớm.** Queue, transaction và exporter có thể chưa hoàn tất. Chờ điều kiện drain và publish rõ ràng.

**Đếm attempt như business completion.** Retry có thể tạo nhiều lần gọi nhưng chỉ một kết quả nghiệp vụ. Tách meter theo ý nghĩa.

**Tăng Counter trước commit rồi so với bản ghi đã commit.** Rollback tạo chênh lệch. Chọn điểm ghi phù hợp với outcome cần đo.

**Đòi Timer sum bằng wall-clock của toàn test.** Timer có thể đo từng operation, còn test harness đo cả network, queue và thời gian chờ. So cùng ranh giới.

**Cộng các Gauge qua thời gian.** Gauge là snapshot trạng thái, không phải event count.

**So max hoặc percentile mà không xét cửa sổ.** Expiry, buffer length và histogram configuration ảnh hưởng kết quả.

**Dùng run ID làm metric tag.** Cardinality tăng theo từng lần chạy. Giữ ID trong nguồn dữ liệu kiểm thử và log.

**Dùng một registry tích lũy qua nhiều test mà không có baseline.** Count cũ làm kết quả test sai. Cô lập registry hoặc tính delta đúng cách.

**Chỉ xác minh meter trong bộ nhớ.** Exporter, Collector, scrape interval và backend có thể làm dữ liệu đến trễ hoặc bị mất. Kiểm tra cả pipeline khi mục tiêu là xác nhận vận hành.

## Checklist đối chiếu metrics

Trước khi kết luận instrumentation đúng, hãy xác minh:

1. Metric có định nghĩa sự kiện và ranh giới ghi nhận rõ ràng không?
2. Nguồn ground truth có độc lập với code cập nhật metric không?
3. Workload có số lượng, outcome, retry và concurrency biết trước không?
4. Baseline và dữ liệu từ test run trước đã được cô lập chưa?
5. Counter đang đếm attempt, request hay business outcome?
6. Timer đo đúng khoảng thời gian và có count tương ứng không?
7. Gauge được so với snapshot gần cùng thời điểm không?
8. DistributionSummary dùng cùng đơn vị và cùng dataset không?
9. Histogram bucket có đơn điệu và +Inf khớp count không?
10. Transaction, async queue và eventual consistency đã ổn định chưa?
11. Metrics cumulative, step hay windowed; scrape/export đã hoàn tất chưa?
12. Nhiều instance và counter reset đã được xử lý đúng chưa?
13. Tolerance được định nghĩa trước và có lý do kỹ thuật không?
14. Tag có cardinality thấp và không chứa ID duy nhất không?
15. Kết quả đối chiếu có lưu kèm phiên bản, cấu hình và nguồn dữ liệu không?

## Kết luận

Đối chiếu metrics với tải thử nghiệm hoặc dữ liệu nghiệp vụ có kiểm soát xác nhận rằng meter phản ánh đúng sự kiện và đúng ranh giới đo. Hãy định nghĩa semantics trước, tạo workload có ground truth, chờ transaction/queue/export hoàn tất và so sánh từng loại meter với nguồn độc lập tương ứng.

Counter cần được đối chiếu với đúng loại sự kiện; Timer cần cùng tập operation và ranh giới thời gian; Gauge cần snapshot trạng thái; DistributionSummary và histogram cần cùng đơn vị cùng phạm vi mẫu. Khi số liệu lệch, kiểm tra retry, rollback, eventual consistency, reset, step, scrape và exporter trước khi thay đổi instrumentation. Một quy trình đối chiếu lặp lại được giúp phát hiện lỗi đo lường sớm và tạo niềm tin vào dashboard, SLO và cảnh báo vận hành.
