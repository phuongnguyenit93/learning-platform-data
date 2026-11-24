# Giá trị tích lũy, thời gian sống tiến trình và tốc độ phát sinh sự kiện

Counter trong Micrometer dùng để đếm số lần một sự kiện xảy ra. Giá trị của Counter tăng theo thời gian và không giảm trong vòng đời của meter. Ví dụ, ứng dụng có thể đếm số đơn hàng được tạo, số lần xác thực thất bại hoặc số thông điệp đã xử lý.

Giá trị Counter trong tiến trình là tổng số lần đã ghi nhận kể từ khi meter được tạo hoặc registry bắt đầu hoạt động. Khi tiến trình khởi động lại, bộ đếm trong bộ nhớ thường bắt đầu lại từ đầu. Vì vậy, giá trị tích lũy tại một thời điểm và tốc độ phát sinh sự kiện là hai cách nhìn khác nhau: count cho biết tổng số sự kiện mà tiến trình đã ghi nhận, còn rate cho biết sự kiện đang xảy ra nhanh đến mức nào trong một khoảng thời gian.

Hiểu đúng hai khái niệm này giúp xây dựng dashboard và cảnh báo có ý nghĩa, đặc biệt khi ứng dụng chạy nhiều instance hoặc thường xuyên được triển khai lại.

## 1. Counter biểu diễn điều gì?

Counter là một meter đơn điệu: giá trị chỉ tăng khi ứng dụng ghi nhận sự kiện. Với API Micrometer, có thể tăng một đơn vị hoặc tăng theo một lượng dương:

~~~java
Counter ordersCreated = meterRegistry.counter("orders.created");

ordersCreated.increment();
ordersCreated.increment(3.0);
~~~

Sau hai lệnh trên, Counter đã tăng tổng cộng bốn đơn vị. Giá trị không đại diện cho trạng thái hiện tại của hệ thống; nó biểu diễn tổng số sự kiện đã ghi nhận trong vòng đời của meter.

Các ví dụ phù hợp với Counter:

- Số đơn hàng đã được chấp nhận.
- Số lần gửi thông điệp thành công.
- Số lần xác thực bị từ chối.
- Số lần một cache miss xảy ra.
- Số lần một tác vụ nền hoàn tất.

Sự kiện cần có định nghĩa rõ ràng. Ví dụ, `orders.created` có thể chỉ tăng khi đơn hàng đã được tạo thành công và được ghi nhận ở điểm nghiệp vụ đã chọn. Nếu tăng Counter trước khi thao tác lưu dữ liệu thành công, số đo có thể bao gồm cả các lần thất bại.

Counter không phù hợp để biểu diễn:

- Số kết nối hiện đang mở.
- Số tác vụ đang chờ trong hàng đợi.
- Số người dùng đang trực tuyến tại thời điểm hiện tại.
- Dung lượng bộ nhớ hiện đang sử dụng.
- Số phần tử đang tồn tại trong cache.

Đây là các trạng thái có thể tăng hoặc giảm. Hãy dùng Gauge để quan sát giá trị hiện tại. Nếu cần đếm số lần trạng thái chuyển đổi, chẳng hạn số lần kết nối được mở, đó lại là một sự kiện phù hợp với Counter.

## 2. Giá trị tích lũy trong vòng đời tiến trình

Counter thường tích lũy từ khi meter được đăng ký trong tiến trình. Ví dụ, một instance của dịch vụ xử lý đơn hàng có thể ghi nhận:

| Thời điểm | Sự kiện mới | Giá trị Counter |
|---|---:|---:|
| Khi tiến trình bắt đầu | 0 | 0 |
| Sau đơn hàng thứ nhất | 1 | 1 |
| Sau ba đơn hàng tiếp theo | 3 | 4 |
| Sau hai đơn hàng tiếp theo | 2 | 6 |

Giá trị sáu có nghĩa instance đã ghi nhận sáu sự kiện kể từ khi bộ đếm bắt đầu. Nó không có nghĩa hệ thống chỉ có sáu đơn hàng trong cơ sở dữ liệu.

Ví dụ một thành phần đo lường:

~~~java
@Component
final class OrderMetrics {
    private final Counter created;

    OrderMetrics(MeterRegistry registry) {
        this.created = Counter.builder("orders.created")
                .description("Number of orders created successfully")
                .register(registry);
    }

    void recordCreated() {
        created.increment();
    }
}
~~~

Service nghiệp vụ gọi `recordCreated()` tại đúng điểm mà sự kiện được xem là đã xảy ra:

~~~java
@Service
final class OrderService {
    private final OrderRepository repository;
    private final OrderMetrics metrics;

    OrderService(OrderRepository repository, OrderMetrics metrics) {
        this.repository = repository;
        this.metrics = metrics;
    }

    Order create(CreateOrderCommand command) {
        Order saved = repository.save(Order.from(command));
        metrics.recordCreated();
        return saved;
    }
}
~~~

Trong ví dụ này, Counter tăng sau khi thao tác lưu trả về thành công. Vị trí ghi nhận cần phản ánh đúng định nghĩa nghiệp vụ của sự kiện. Nếu nghiệp vụ coi một đơn hàng được tạo khi transaction commit, cần cân nhắc ghi nhận sau commit hoặc qua cơ chế sự kiện phù hợp để tránh đếm cả transaction rollback.

### Counter được reset khi tiến trình khởi động lại

Counter của Micrometer thường được lưu trong bộ nhớ của tiến trình. Khi JVM dừng và một tiến trình mới khởi động, registry mới tạo meter mới; giá trị tích lũy trong bộ nhớ của tiến trình trước không tự được khôi phục.

Ví dụ một instance có thể trải qua các giai đoạn:

~~~text
Tiến trình A: 0 -> 10 -> 25 -> dừng
Tiến trình B: 0 -> 4 -> 9 -> tiếp tục chạy
~~~

Giá trị chuyển từ 25 xuống 0 là hệ quả của việc tiến trình mới bắt đầu một vòng đời mới. Đây không phải sự kiện nghiệp vụ làm giảm số đơn hàng đã tạo.

Điều này có ý nghĩa khi đọc biểu đồ. Nếu nhìn vào một chuỗi Counter thô, sau lần khởi động lại có thể thấy giá trị giảm. Backend như Prometheus nhận biết các lần reset Counter để các hàm như `rate()` và `increase()` tính toán phù hợp qua điểm reset.

Counter trong ứng dụng là telemetry của tiến trình, không phải sổ cái bền vững. Nếu ứng dụng dừng đột ngột trước lần scrape tiếp theo, một phần số tăng trong bộ nhớ có thể chưa được backend quan sát. Không dùng Counter làm nguồn dữ liệu duy nhất cho hóa đơn, thanh toán, kiểm toán hoặc đối soát nghiệp vụ. Những dữ liệu đó cần được lưu bằng cơ chế bền vững của hệ thống nghiệp vụ.

## 3. Phân biệt count và rate

Count và rate trả lời hai câu hỏi khác nhau:

- **Count:** đã ghi nhận bao nhiêu sự kiện trong một khoảng hoặc trong vòng đời meter?
- **Rate:** sự kiện đang phát sinh với tốc độ bao nhiêu trong một đơn vị thời gian?

Giả sử một instance ghi nhận 600 sự kiện trong 10 phút. Tổng count là 600; tốc độ trung bình trong khoảng đó là:

\[
\text{rate} = \frac{600\ \text{events}}{600\ \text{seconds}} = 1\ \text{event/second}
\]

Nếu 600 sự kiện xảy ra dồn trong một phút đầu rồi không có sự kiện nào trong chín phút còn lại, count vẫn là 600 nhưng tốc độ thay đổi đáng kể theo từng cửa sổ thời gian. Vì vậy, biểu đồ rate hữu ích để theo dõi lưu lượng và phát hiện đột biến.

| Đại lượng | Ý nghĩa | Câu hỏi vận hành |
|---|---|---|
| Counter count | Tổng sự kiện đã ghi nhận | Instance này đã xử lý bao nhiêu sự kiện kể từ khi bắt đầu? |
| Increase trong một khoảng | Số sự kiện ước tính trong cửa sổ | Trong 15 phút qua đã có bao nhiêu sự kiện? |
| Rate | Số sự kiện trung bình trên một đơn vị thời gian | Mỗi giây hệ thống đang xử lý bao nhiêu sự kiện? |

Không lấy giá trị Counter hiện tại chia cho thời gian chạy rồi coi đó là tốc độ hiện tại. Phép chia đó chỉ tạo ra tốc độ trung bình từ lúc meter bắt đầu, có thể che khuất thay đổi gần đây. Hãy dùng rate trên một cửa sổ thời gian phù hợp với mục tiêu quan sát.

## 4. Ghi nhận Counter đúng thời điểm và đúng một lần

Counter nên tăng khi sự kiện đã đạt đến trạng thái mà định nghĩa đo lường yêu cầu. Đặt lệnh tăng ở sai vị trí sẽ khiến số liệu không phản ánh hành vi thực tế.

Ví dụ:

~~~java
PaymentResult result = paymentGateway.charge(command);

if (result.isApproved()) {
    approvedPayments.increment();
} else {
    declinedPayments.increment();
}
~~~

Trong ví dụ này, hai Counter phân biệt kết quả nghiệp vụ. Nếu muốn dùng chung một meter, có thể thêm tag `outcome` với tập giá trị hữu hạn:

~~~java
Counter approved = Counter.builder("payments.processed")
        .tag("outcome", "approved")
        .register(registry);

Counter declined = Counter.builder("payments.processed")
        .tag("outcome", "declined")
        .register(registry);
~~~

Hai cách trên đều có thể dùng. Dùng một tên kèm tag thường thuận tiện cho truy vấn tổng hợp theo kết quả; tên riêng có thể dễ đọc trong những hệ thống có quy ước metric tách biệt. Hãy chọn một cách thống nhất cho cùng một nhóm chỉ số.

### Tránh đếm hai lần do retry

Một request có thể được thử lại nhiều lần. Cần xác định muốn đếm số lần thử hay số nghiệp vụ cuối cùng thành công.

- Nếu muốn đếm mọi lần gọi gateway, tăng Counter tại mỗi lần gọi.
- Nếu muốn đếm số giao dịch được chấp nhận, chỉ tăng sau khi có kết quả chấp nhận theo định nghĩa nghiệp vụ.
- Nếu retry có thể tạo nhiều lần xử lý cùng một sự kiện, dùng idempotency hoặc cơ chế sự kiện nghiệp vụ để bảo đảm vị trí ghi nhận đúng.

Không tăng Counter ở cả tầng controller, service và repository cho cùng một sự kiện rồi cộng các meter đó như thể chúng là ba loại sự kiện riêng. Mỗi phép đo phải có một ranh giới rõ ràng.

### Counter và xử lý đồng thời

Micrometer thiết kế meter để có thể được cập nhật từ các luồng xử lý đồng thời. Ứng dụng có thể gọi `increment()` từ nhiều thread mà không cần tự bảo vệ bằng một biến số nguyên dùng chung. Tuy nhiên, vẫn phải đặt lệnh tăng ở đúng điểm nghiệp vụ và tránh ghi trùng do logic retry hoặc gọi lặp.

## 5. Dùng Counter cùng Timer như thế nào?

Timer cũng có count: số lần một thao tác được ghi nhận. Timer còn lưu tổng thời lượng và có thể cung cấp phân bố hoặc histogram tùy cấu hình.

Nếu câu hỏi là “có bao nhiêu lần gọi thanh toán và mất bao lâu?”, Timer thường đã đủ:

~~~java
Timer authorization = Timer.builder("payment.authorization")
        .register(registry);

authorization.record(() -> paymentGateway.authorize(command));
~~~

Không cần tạo thêm Counter chỉ để đếm đúng số lần `payment.authorization` được ghi nhận. Counter riêng có thể cần thiết khi nó biểu diễn một sự kiện khác, chẳng hạn số giao dịch được phê duyệt, số lần từ chối do chính sách hoặc số lần retry.

| Nhu cầu | Meter phù hợp |
|---|---|
| Đếm số đơn hàng được tạo | Counter |
| Đếm số lần gọi dịch vụ và đo thời gian gọi | Timer |
| Đếm số lần thanh toán được chấp nhận, độc lập với số lần gọi gateway | Counter |
| Đo số công việc hiện đang chờ | Gauge |

Hãy tránh ghi hai meter cho cùng một ý nghĩa. Việc đo trùng làm dashboard khó diễn giải và có thể khiến người vận hành cộng nhầm số liệu.

## 6. Chuyển Counter thành tốc độ bằng Prometheus

Với Prometheus, registry thường xuất Counter dưới dạng một chuỗi thời gian tích lũy, thường có hậu tố `_total`. Ví dụ, Counter logic `orders.created` có thể được xuất thành `orders_created_total`. Tên cuối cùng phụ thuộc naming convention và phiên bản registry.

Prometheus scrape giá trị Counter theo chu kỳ. Mỗi sample là giá trị tích lũy mà instance báo cáo tại thời điểm scrape. PromQL cung cấp các hàm để tính toán trên chuỗi sample đó.

### rate(): tốc độ trung bình mỗi giây

~~~promql
rate(orders_created_total[5m])
~~~

`rate()` ước tính số sự kiện trung bình mỗi giây trong cửa sổ năm phút, có xử lý các lần Counter reset. Cửa sổ cần đủ dài để chứa nhiều sample scrape. Nếu cửa sổ quá ngắn so với scrape interval, kết quả có thể không ổn định hoặc không có đủ dữ liệu.

Để tổng hợp tốc độ của tất cả instance:

~~~promql
sum(rate(orders_created_total[5m]))
~~~

Thứ tự này quan trọng: tính rate trên từng chuỗi thời gian trước, sau đó mới cộng các rate. Mỗi instance có thể khởi động lại ở thời điểm khác nhau; `rate()` cần nhìn thấy reset trên từng chuỗi để tính đúng.

### increase(): số sự kiện trong cửa sổ

~~~promql
increase(orders_created_total[1h])
~~~

`increase()` ước tính số sự kiện phát sinh trong một giờ. Do Prometheus chỉ lấy mẫu theo chu kỳ, kết quả có thể là số thập phân vì hàm ngoại suy về hai đầu cửa sổ. Đây là số liệu quan sát ước tính, không phải bản ghi giao dịch chính xác.

Tổng số sự kiện ước tính của tất cả instance:

~~~promql
sum(increase(orders_created_total[1h]))
~~~

### Tốc độ theo tag

Nếu Counter có tag `outcome`, Prometheus có thể xuất label tương ứng:

~~~promql
sum by (outcome) (rate(payments_processed_total[5m]))
~~~

Truy vấn này cho biết tốc độ xử lý theo từng kết quả. Tên metric và label cụ thể phải được kiểm tra tại endpoint scrape vì registry có thể chuẩn hóa chúng.

### Tỷ lệ thất bại

Giả sử Counter `payments.processed` có hai giá trị `outcome=approved` và `outcome=declined`, có thể tính tỷ lệ declined:

~~~promql
sum(rate(payments_processed_total{outcome="declined"}[5m]))
/
sum(rate(payments_processed_total[5m]))
~~~

Nếu mẫu số bằng không, biểu thức không tạo ra tỷ lệ hữu ích. Dashboard hoặc alert nên xử lý trường hợp không có lưu lượng, chẳng hạn hiển thị no data hoặc dùng biểu thức có điều kiện phù hợp với quy ước của đội vận hành.

## 7. Scrape interval và cửa sổ tính rate

Prometheus không quan sát mọi lần gọi `increment()`. Nó chỉ lấy mẫu giá trị Counter khi scrape. Vì thế, backend nhìn thấy các điểm tích lũy cách nhau theo scrape interval, sau đó ước tính tốc độ giữa các điểm.

Ví dụ với scrape interval 15 giây:

| Thời điểm scrape | Giá trị Counter |
|---|---:|
| 10:00:00 | 100 |
| 10:00:15 | 112 |
| 10:00:30 | 121 |
| 10:00:45 | 145 |

Các sample cho biết Counter tăng 12, 9 và 24 trong ba khoảng 15 giây. Tốc độ trung bình tương ứng là 0,8; 0,6 và 1,6 sự kiện mỗi giây. Truy vấn rate trên cửa sổ dài hơn sẽ làm mượt dao động ngắn hạn.

Lựa chọn cửa sổ phụ thuộc mục tiêu:

- Cửa sổ ngắn phản ứng nhanh nhưng nhạy với dao động và số sample ít.
- Cửa sổ dài ổn định hơn nhưng có thể làm chậm việc nhận biết thay đổi đột ngột.
- Cửa sổ nên tương thích với scrape interval và khoảng thời gian đánh giá dashboard/alert.

Đối với dashboard lưu lượng, cửa sổ năm phút là điểm bắt đầu phổ biến. Với cảnh báo, cần chọn cửa sổ phù hợp thời gian phản ứng và tránh báo động chỉ vì một khoảng scrape bị trễ.

## 8. Nhiều instance và tổng hợp Counter

Trong môi trường nhiều replica, mỗi tiến trình có Counter riêng. Ví dụ:

| Instance | Counter hiện tại |
|---|---:|
| `orders-1` | 120 |
| `orders-2` | 95 |
| `orders-3` | 210 |

Tổng các giá trị sample hiện tại là 425, nhưng con số đó chỉ cộng các giá trị tích lũy kể từ khi từng instance bắt đầu. Nếu một instance mới vừa được tạo và hai instance khác đã chạy nhiều ngày, tổng này không tương đương với tổng số đơn hàng trong cơ sở dữ liệu hoặc tổng số đơn hàng của toàn bộ lịch sử hệ thống.

Để theo dõi throughput toàn hệ thống, hãy tính rate từng chuỗi thời gian rồi cộng:

~~~promql
sum(rate(orders_created_total[5m]))
~~~

Không nên cộng Counter thô trước khi áp dụng `rate()`:

~~~promql
rate(sum(orders_created_total)[5m:])
~~~

Cách tính trên có thể che mất reset của từng instance vì việc cộng diễn ra trước khi hàm rate phân tích chuỗi. Hãy giữ từng chuỗi riêng đến khi đã tính rate hoặc increase.

Khi có label `instance`, `pod` hoặc `service`, có thể nhóm theo một chiều để điều tra:

~~~promql
sum by (instance) (rate(orders_created_total[5m]))
~~~

Truy vấn này giúp phát hiện một instance có throughput khác biệt. Tuy nhiên, tránh giữ label có giá trị thay đổi liên tục hoặc tạo ra số lượng chuỗi thời gian quá lớn.

## 9. Cardinality và tag cho Counter

Counter thường được phân loại bằng các tag có tập giá trị nhỏ:

~~~java
Counter processed = Counter.builder("orders.processed")
        .tag("outcome", outcome)
        .tag("channel", channel)
        .register(registry);
~~~

Các giá trị như `outcome=success|failure` hoặc `channel=web|mobile|partner` có thể kiểm soát được nếu danh mục được giới hạn.

Không gắn các giá trị sau vào tag metrics:

- Order ID hoặc customer ID.
- Request ID, trace ID hoặc session ID.
- Email, số điện thoại hoặc tên người dùng.
- URL đầy đủ có path hoặc query string động.
- Nội dung exception hoặc thông báo lỗi tùy ý.

Nếu một Counter có 3 outcome, 4 channel và 5 region, số chuỗi thời gian tối đa từ ba chiều này có thể lên đến 60 cho mỗi instance. Khi thêm chiều có hàng triệu giá trị, số chuỗi tăng không kiểm soát. Hãy dự tính cardinality từ số lượng giá trị của từng tag trước khi triển khai.

Đặt tên meter ổn định và đưa chiều phân loại vào tag. Không tạo tên khác nhau cho từng order hoặc request.

## 10. Kiểm thử Counter

Có thể dùng `SimpleMeterRegistry` để xác minh Counter tăng đúng:

~~~java
class OrderMetricsTest {
    private final SimpleMeterRegistry registry = new SimpleMeterRegistry();

    @Test
    void incrementsWhenOrderIsCreated() {
        Counter counter = Counter.builder("orders.created")
                .register(registry);

        counter.increment();
        counter.increment(2.0);

        assertThat(counter.count()).isEqualTo(3.0);
    }
}
~~~

Ngoài phép kiểm tra giá trị, nên kiểm tra ranh giới sự kiện:

1. Khi tạo đơn hàng thành công, Counter tăng đúng một lần.
2. Khi validation thất bại trước khi tạo đơn, Counter không tăng.
3. Khi transaction rollback, số đo không được ghi như thể đơn hàng đã được tạo thành công nếu định nghĩa sự kiện là sau commit.
4. Khi retry, Counter phản ánh đúng điều muốn đo: số lần thử hay số giao dịch thành công.
5. Tag chỉ dùng tập giá trị đã định nghĩa.

Với Prometheus registry, cần có kiểm thử tích hợp để xác minh tên xuất ra, label và định dạng Counter. Unit test bằng SimpleMeterRegistry không chứng minh rằng backend nhận dữ liệu đúng.

## 11. Cảnh báo và dashboard dựa trên Counter

Counter thô thường hữu ích khi điều tra tổng số tích lũy trong vòng đời instance. Với giám sát vận hành, rate và tỷ lệ thường hữu ích hơn vì chúng phản ánh xu hướng trong một cửa sổ thời gian.

Ví dụ, dashboard có thể hiển thị:

- Số đơn hàng được tạo mỗi giây.
- Số lần xử lý thất bại mỗi giây.
- Tỷ lệ lỗi trong tổng số lần xử lý.
- Số sự kiện ước tính trong 1 giờ.

Truy vấn tốc độ xử lý:

~~~promql
sum(rate(orders_processed_total[5m]))
~~~

Truy vấn tốc độ thất bại:

~~~promql
sum(rate(orders_processed_total{outcome="failure"}[5m]))
~~~

Truy vấn tỷ lệ lỗi:

~~~promql
sum(rate(orders_processed_total{outcome="failure"}[5m]))
/
sum(rate(orders_processed_total[5m]))
~~~

Nếu cần hiển thị phần trăm, nhân kết quả tỷ lệ với 100. Cần xác định rõ mẫu số có bao gồm tất cả kết quả hay chỉ các kết quả được xem là hoàn tất. Nếu mẫu số có cả request đang chạy hoặc bị bỏ qua, tỷ lệ sẽ có ý nghĩa khác.

Không cảnh báo chỉ dựa trên việc Counter không tăng nếu hệ thống vốn không có lưu lượng vào thời điểm đó. Có thể kết hợp điều kiện về lưu lượng kỳ vọng, health check hoặc lịch hoạt động. Với dịch vụ luôn phải nhận request, một khoảng thời gian không có sự kiện có thể là dấu hiệu cần điều tra, nhưng phải được xác nhận bằng ngữ cảnh vận hành.

## 12. Các lỗi thường gặp

**Dùng Counter để biểu diễn trạng thái hiện tại.** Counter không giảm khi hàng đợi được xử lý hoặc kết nối đóng. Dùng Gauge cho trạng thái hiện tại.

**Cho rằng Counter giữ tổng số sự kiện vĩnh viễn.** Giá trị trong tiến trình thường reset khi tiến trình khởi động lại và có thể mất phần chưa được scrape. Dùng kho dữ liệu nghiệp vụ bền vững cho đối soát.

**Diễn giải count như rate.** Giá trị tích lũy lớn không có nghĩa tốc độ hiện tại cao. Dùng rate hoặc increase với cửa sổ phù hợp.

**Cộng các Counter thô của nhiều instance rồi mới tính rate.** Cách này có thể che khuất reset của từng instance. Tính rate theo từng chuỗi rồi mới cộng.

**Tăng Counter trước khi sự kiện thực sự xảy ra.** Đặt phép tăng sau điểm nghiệp vụ được xác định là thành công, hoặc ghi nhận riêng số lần thử và số lần hoàn tất.

**Đếm trùng ở nhiều tầng.** Xác định một ranh giới instrumentation cho mỗi sự kiện để tránh một nghiệp vụ tạo nhiều lần tăng không chủ ý.

**Tạo tag có cardinality cao.** Không đưa ID động hoặc dữ liệu người dùng vào label metrics.

**Tạo Counter trùng với Timer count.** Nếu Timer đã đếm số lần của thao tác, chỉ tạo Counter khác khi nó biểu diễn một sự kiện nghiệp vụ khác.

## 13. Checklist thiết kế Counter

Trước khi thêm Counter, hãy tự kiểm tra:

- [ ] Sự kiện được đếm có định nghĩa rõ ràng và có thời điểm ghi nhận cụ thể.
- [ ] Giá trị chỉ tăng; nếu cần quan sát trạng thái có thể tăng hoặc giảm, dùng Gauge.
- [ ] Meter được đăng ký một lần và tái sử dụng.
- [ ] Counter không được xem là dữ liệu nghiệp vụ bền vững.
- [ ] Đã phân biệt count, increase và rate trong dashboard.
- [ ] Với Prometheus, rate được tính trên từng chuỗi trước khi tổng hợp nhiều instance.
- [ ] Retry và transaction rollback không làm số đo sai ngữ nghĩa.
- [ ] Tag có tập giá trị nhỏ, ổn định và không chứa định danh động.
- [ ] Không ghi trùng số lần với Timer count nếu cùng một ý nghĩa.

## 14. Kết luận

Counter cung cấp giá trị tích lũy của các sự kiện đã ghi nhận trong vòng đời meter hoặc tiến trình. Giá trị này tăng theo thời gian và thường bắt đầu lại khi tiến trình mới được tạo. Để hiểu tốc độ phát sinh sự kiện, hãy dùng rate trên một cửa sổ thời gian; để ước tính số sự kiện trong một khoảng, dùng increase.

Trong hệ thống nhiều instance, tính rate hoặc increase cho từng chuỗi Counter trước khi tổng hợp để xử lý đúng các lần reset. Chọn điểm tăng Counter theo ranh giới nghiệp vụ, giữ tag ở cardinality thấp và dùng kho dữ liệu bền vững cho dữ liệu cần độ chính xác kiểm toán. Khi đó, Counter trở thành tín hiệu vận hành đáng tin cậy để theo dõi throughput, lỗi và xu hướng xử lý.
