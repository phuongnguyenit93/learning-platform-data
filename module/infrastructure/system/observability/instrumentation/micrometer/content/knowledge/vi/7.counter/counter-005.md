# Đếm các kết quả thành công, thất bại hoặc bị từ chối

Micrometer Counter dùng để đếm số sự kiện đã xảy ra. Trong xử lý nghiệp vụ, một Counter có thể ghi nhận số lần một thao tác hoàn tất thành công, thất bại do lỗi kỹ thuật hoặc bị từ chối theo quy tắc nghiệp vụ. Ba kết quả này cần được phân loại rõ ràng để dashboard phản ánh đúng hành vi của ứng dụng.

Một thiết kế thường dùng là một tên meter chung, chẳng hạn **orders.process**, kèm tag **result** có các giá trị **success**, **failure** và **rejected**. Mỗi lần xử lý chỉ ghi nhận một kết quả cuối cùng. Cách tổ chức này giúp so sánh các outcome trong cùng một nhóm số liệu, tính tỷ lệ thành công và phát hiện xu hướng lỗi mà vẫn giữ tập khóa tag ổn định.

## 1. Counter đo sự kiện tích lũy

Counter là meter có giá trị tăng dần theo các sự kiện được ghi nhận. Mỗi lần gọi **increment()** làm số đếm tăng thêm một. Giá trị Counter không được giảm; Counter phù hợp với số lần một việc đã xảy ra, ví dụ:

- Số đơn hàng được tạo thành công.
- Số lần xử lý đơn hàng gặp lỗi kỹ thuật.
- Số yêu cầu bị từ chối do dữ liệu không hợp lệ.
- Số message được tiêu thụ hoặc số lần gọi đến một dependency.
- Số bản ghi được xử lý nếu mỗi lần cập nhật biểu thị số bản ghi đã hoàn tất.

Counter thường được lưu như một giá trị tích lũy trong vòng đời tiến trình. Khi ứng dụng khởi động lại, giá trị trong bộ nhớ của tiến trình mới bắt đầu lại theo registry mới. Hệ thống giám sát cần xử lý hiện tượng reset này khi tính tốc độ hoặc mức tăng trong một khoảng thời gian.

~~~java
Counter completedOrders = Counter.builder("orders.created")
    .description("Số đơn hàng được tạo thành công")
    .register(meterRegistry);

completedOrders.increment();
~~~

Đoạn mã tăng bộ đếm một lần sau khi một đơn hàng được tạo thành công. Tên meter mô tả sự kiện được đếm; description giúp người vận hành hiểu số liệu khi kiểm tra registry hoặc metadata của backend.

Counter có thể tăng theo một lượng dương khi một lần cập nhật đại diện cho nhiều sự kiện, ví dụ một batch xử lý thành công 20 bản ghi. Khi đó cần đặt tên và mô tả meter để người đọc hiểu đơn vị đếm là bản ghi, không phải số batch. Không dùng Counter để giảm số lượng đang tồn tại hoặc biểu diễn trạng thái hiện tại.

## 2. Phân loại kết quả nghiệp vụ

Để đếm outcome, trước tiên cần thống nhất ý nghĩa của từng kết quả. Một cách phân loại phổ biến là:

| Kết quả | Ý nghĩa | Ví dụ |
|---|---|---|
| **success** | Thao tác hoàn tất theo yêu cầu | Đơn hàng được tạo và ghi nhận thành công |
| **failure** | Thao tác không hoàn tất do lỗi kỹ thuật hoặc lỗi thực thi | Timeout khi gọi dịch vụ thanh toán, lỗi cơ sở dữ liệu |
| **rejected** | Yêu cầu bị từ chối theo quy tắc nghiệp vụ hoặc chính sách | Thiếu thông tin bắt buộc, vượt hạn mức, trạng thái không cho phép |

**rejected** cần được phân biệt với **failure**. Một yêu cầu không hợp lệ bị từ chối có thể là kết quả nghiệp vụ dự kiến, không nhất thiết là sự cố của hệ thống. Nếu gộp tất cả trường hợp bị từ chối vào failure, tỷ lệ lỗi kỹ thuật sẽ bị thổi phồng và cảnh báo khó phản ánh đúng tình trạng dịch vụ.

Ba outcome phải có định nghĩa rõ ràng và loại trừ nhau tại ranh giới được đo. Với một thao tác xử lý đơn hàng, ứng dụng có thể ghi đúng một trong ba kết quả. Nếu cần thêm trạng thái như **cancelled**, hãy xác định đó là outcome riêng hay thuộc nhóm nghiệp vụ khác trước khi đưa vào schema.

Cần phân biệt đối tượng được đếm:

- **Request**: mỗi HTTP request được ghi nhận một kết quả.
- **Attempt**: mỗi lần thử thực thi được ghi nhận, bao gồm cả retry.
- **Operation**: một thao tác nghiệp vụ logic có thể gồm nhiều attempt.
- **Item**: mỗi bản ghi hoặc đơn vị dữ liệu được xử lý.

Không dùng một meter với nhiều cách hiểu. Nếu cần đếm cả attempt lẫn operation cuối cùng, nên tạo meter có tên riêng, chẳng hạn **orders.process.attempts** và **orders.process**, để người đọc không nhầm đơn vị.

## 3. Dùng một Counter name với tag result

Có thể dùng một meter name và tag **result** để phân loại kết quả. Tất cả outcome dùng cùng tập khóa tag; chỉ giá trị của **result** thay đổi.

~~~java
public enum OrderOutcome {
    SUCCESS("success"),
    FAILURE("failure"),
    REJECTED("rejected");

    private final String tagValue;

    OrderOutcome(String tagValue) {
        this.tagValue = tagValue;
    }

    public String tagValue() {
        return tagValue;
    }
}
~~~

Component instrumentation đăng ký trước các Counter cần dùng:

~~~java
public final class OrderMetrics {

    private final Counter success;
    private final Counter failure;
    private final Counter rejected;

    public OrderMetrics(MeterRegistry registry) {
        this.success = Counter.builder("orders.process")
            .description("Số kết quả xử lý đơn hàng")
            .tag("result", OrderOutcome.SUCCESS.tagValue())
            .register(registry);

        this.failure = Counter.builder("orders.process")
            .description("Số kết quả xử lý đơn hàng")
            .tag("result", OrderOutcome.FAILURE.tagValue())
            .register(registry);

        this.rejected = Counter.builder("orders.process")
            .description("Số kết quả xử lý đơn hàng")
            .tag("result", OrderOutcome.REJECTED.tagValue())
            .register(registry);
    }

    public void record(OrderOutcome outcome) {
        switch (outcome) {
            case SUCCESS -> success.increment();
            case FAILURE -> failure.increment();
            case REJECTED -> rejected.increment();
        }
    }
}
~~~

Các Counter có cùng tên **orders.process** và cùng một khóa **result**. Registry phân biệt từng meter bằng giá trị tag. Việc đăng ký trước giúp schema xuất hiện nhất quán ngay từ lúc khởi động, kể cả khi một outcome chưa xảy ra trong khoảng thời gian quan sát.

Trong ứng dụng Spring Boot, **MeterRegistry** thường được cấu hình và quản lý như bean. Hãy inject registry vào component instrumentation qua constructor. Không tạo một registry riêng trong mỗi service hoặc mỗi request, vì dữ liệu có thể bị phân tán vào nhiều registry và không được backend scrape như dự kiến.

## 4. Ghi nhận đúng một kết quả cuối cùng

Điểm ghi Counter nên nằm ở ranh giới mà ứng dụng có thể xác định outcome của thao tác. Ví dụ, service xử lý đơn hàng có thể ghi success khi nghiệp vụ hoàn tất, rejected khi quy tắc nghiệp vụ từ chối yêu cầu và failure khi quá trình thực thi gặp lỗi.

~~~java
public Order create(CreateOrderCommand command) {
    try {
        Order order = orderService.create(command);
        orderMetrics.record(OrderOutcome.SUCCESS);
        return order;
    } catch (OrderRejectedException exception) {
        orderMetrics.record(OrderOutcome.REJECTED);
        throw exception;
    } catch (RuntimeException exception) {
        orderMetrics.record(OrderOutcome.FAILURE);
        throw exception;
    }
}
~~~

Ví dụ minh họa việc phân loại outcome tại một điểm xử lý. Trong ứng dụng thật, cần điều chỉnh kiểu exception và ranh giới bắt lỗi theo hợp đồng của service. Nếu nghiệp vụ trả về kết quả từ chối bằng một object thay vì ném exception, hãy kiểm tra kết quả đó và ghi **REJECTED** ở nhánh tương ứng.

Một số nguyên tắc giúp tránh đếm sai:

- Ghi đúng một outcome cho mỗi đơn vị xử lý đã chọn.
- Chỉ ghi success sau khi thao tác thực sự hoàn tất theo định nghĩa của nghiệp vụ.
- Không ghi failure rồi tiếp tục ghi success cho cùng một operation logic nếu failure chỉ là một attempt đã retry thành công.
- Nếu đo số lần thử, dùng một meter riêng cho attempt và ghi nhận mỗi lần thử theo định nghĩa đó.
- Không ghi Counter trong cả controller lẫn service nếu cả hai cùng mô tả một sự kiện; việc này sẽ đếm hai lần.
- Đảm bảo các nhánh từ chối và lỗi đều đi qua điểm ghi nhận chung, kể cả khi exception được chuyển tiếp lên tầng trên.

### Retry và outcome cuối cùng

Giả sử một đơn hàng được thử ba lần: hai lần timeout, lần thứ ba thành công. Nếu Counter **orders.process** mô tả kết quả cuối cùng của một operation logic, chỉ tăng **success** một lần. Nếu muốn biết dependency đang timeout bao nhiêu lần, hãy ghi riêng Counter cho số attempt hoặc lỗi dependency.

| Ý nghĩa meter | Sự kiện được đếm trong ví dụ retry |
|---|---:|
| **orders.process** với **result=success** | 1 operation thành công |
| **orders.process.attempts** | 3 attempt |
| **orders.dependency.errors** với **dependency=payment** | 2 timeout nếu cả hai attempt đều timeout |

Tên meter và description cần nêu rõ đếm operation, attempt hay item. Nếu không, số liệu giữa các dashboard sẽ khó đối chiếu.

## 5. Thống nhất tập khóa tag và giới hạn giá trị

Với một tên meter, mọi outcome cần dùng cùng tập khóa tag. Ví dụ, nếu **orders.process** dùng **result** và **channel**, cả success, failure và rejected đều phải có cả hai khóa. Không thêm tag **exception** chỉ ở nhánh failure.

Giá trị tag nên được giới hạn trong tập hữu hạn:

| Khóa | Giá trị được phép |
|---|---|
| **result** | **success**, **failure**, **rejected**, có thể thêm **unknown** nếu cần fallback |
| **channel** | **web**, **mobile**, **batch**, **unknown** |

Không dùng thông điệp exception, request ID, order ID hoặc URL chứa định danh làm tag. Các giá trị này có thể tạo ra số lượng chuỗi thời gian rất lớn. Nếu cần phân tích nguyên nhân chi tiết của một lần xử lý cụ thể, trace hoặc log có cấu trúc phù hợp hơn.

Ví dụ ghi Counter với hai tag:

~~~java
registry.counter(
    "orders.process",
    "result", outcome.tagValue(),
    "channel", normalizeChannel(channel)
).increment();
~~~

**normalizeChannel** cần chuyển mọi giá trị đầu vào về tập giá trị đã định nghĩa. Kể cả khi **channel** bị thiếu, meter vẫn phải có khóa **channel** với giá trị như **unknown**. Quy tắc này giúp mọi meter cùng tên duy trì schema ổn định.

## 6. Counter, Timer và Gauge có vai trò khác nhau

Counter phù hợp để đếm số sự kiện, Timer phù hợp để đo thời gian và số lần một hoạt động diễn ra, còn Gauge phù hợp để đọc giá trị hiện tại.

| Câu hỏi | Meter nên dùng | Ví dụ |
|---|---|---|
| Có bao nhiêu lần xử lý thành công? | Counter | **orders.process{result="success"}** |
| Tỷ lệ xử lý thất bại đang tăng hay giảm? | Counter kết hợp truy vấn rate | Số failure mỗi giây trong 5 phút |
| Một lần xử lý mất bao lâu? | Timer | **orders.process.duration** |
| Hiện có bao nhiêu đơn đang chờ? | Gauge | **orders.pending** |
| Có bao nhiêu lần Timer đã ghi nhận? | **Timer.count()** | Số lần đo thời gian |

Timer đã cung cấp số lần ghi nhận thông qua **count()** cùng dữ liệu thời lượng. Nếu mục tiêu chỉ là đếm số lần một hoạt động được đo thời gian, không cần thêm Counter trùng lặp mà không có lý do. Counter riêng vẫn có ích khi đếm một sự kiện có ngữ nghĩa khác với lần gọi Timer, ví dụ kết quả nghiệp vụ cuối cùng.

Không dùng Counter để theo dõi số request đang chạy hoặc số kết nối hiện tại, vì những giá trị này có thể tăng rồi giảm. Hãy dùng Gauge hoặc meter chuyên biệt cho trạng thái hiện thời.

## 7. Đọc count, rate và increase

Giá trị **count()** của Counter là tổng số lần tăng kể từ khi meter bắt đầu trong tiến trình hiện tại. Khi vận hành, thường cần biết tốc độ sự kiện thay vì chỉ nhìn tổng tích lũy.

Với backend Prometheus, một registry có thể chuyển tên **orders.process** thành tên xuất như **orders_process_total**. Tên chính xác phụ thuộc NamingConvention và cấu hình exporter. Ví dụ truy vấn sau giả định tên đã được xuất như vậy:

~~~promql
sum by (result) (
  rate(orders_process_total[5m])
)
~~~

Biểu thức này tính tốc độ tăng trung bình trong cửa sổ 5 phút và nhóm theo outcome. Có thể dùng **increase** để ước tính tổng số sự kiện trong một khoảng:

~~~promql
sum by (result) (
  increase(orders_process_total[1h])
)
~~~

Để tính tỷ lệ failure trong tổng số kết quả:

~~~promql
sum(rate(orders_process_total{result="failure"}[5m]))
/
sum(rate(orders_process_total[5m]))
~~~

Nếu tổng lưu lượng bằng 0, biểu thức tỷ lệ có thể không có giá trị hữu ích; dashboard nên xử lý trường hợp không có mẫu hoặc mẫu số bằng 0. Khi có nhiều instance, cần tổng hợp các chuỗi trước khi tính tỷ lệ để phản ánh toàn dịch vụ. Không lấy trung bình các tỷ lệ riêng của từng instance nếu lưu lượng giữa các instance khác nhau đáng kể.

**rate** và **increase** xử lý Counter reset do tiến trình khởi động lại trong phạm vi dữ liệu scrape mà Prometheus quan sát được. Chúng giúp phân tích số liệu tích lũy, nhưng không biến Counter trong bộ nhớ thành sổ cái giao dịch bền vững.

## 8. Counter không phải sổ ghi nhận giao dịch

Counter phục vụ quan sát vận hành. Giá trị có thể mất khi tiến trình dừng, khi registry bị thay thế hoặc khi dữ liệu chưa kịp xuất. Vì vậy, không dùng Counter làm nguồn dữ liệu duy nhất cho kế toán, đối soát thanh toán hoặc báo cáo nghiệp vụ cần độ chính xác lưu trữ lâu dài.

Cũng cần xem xét thời điểm tăng Counter trong giao dịch cơ sở dữ liệu. Nếu tăng Counter trước khi transaction commit rồi transaction rollback, metrics có thể ghi nhận một thao tác thành công dù dữ liệu nghiệp vụ chưa được lưu. Nếu số liệu cần mô tả kết quả đã commit, hãy ghi nhận sau commit bằng cơ chế transaction synchronization phù hợp. Dù vậy, metrics vẫn có thể mất cập nhật khi tiến trình gặp sự cố giữa commit và lần ghi Counter; yêu cầu nhất quán tuyệt đối cần được giải quyết bằng dữ liệu nghiệp vụ bền vững hoặc mô hình outbox, không dựa vào Counter.

## 9. Kiểm thử Counter theo từng outcome

Dùng SimpleMeterRegistry để kiểm tra số đếm và tag của từng outcome mà không cần kết nối backend bên ngoài.

~~~java
@Test
void recordsEachOrderOutcomeWithTheExpectedTag() {
    try (SimpleMeterRegistry registry = new SimpleMeterRegistry()) {
        OrderMetrics metrics = new OrderMetrics(registry);

        metrics.record(OrderOutcome.SUCCESS);
        metrics.record(OrderOutcome.SUCCESS);
        metrics.record(OrderOutcome.FAILURE);
        metrics.record(OrderOutcome.REJECTED);

        assertEquals(
            2.0,
            registry.get("orders.process")
                .tag("result", "success")
                .counter()
                .count()
        );

        assertEquals(
            1.0,
            registry.get("orders.process")
                .tag("result", "failure")
                .counter()
                .count()
        );

        assertEquals(
            1.0,
            registry.get("orders.process")
                .tag("result", "rejected")
                .counter()
                .count()
        );
    }
}
~~~

Bài kiểm thử xác nhận các nhánh outcome làm tăng đúng Counter. Có thể mở rộng kiểm thử để xác minh:

- Mỗi operation chỉ ghi một kết quả cuối cùng.
- Một lần retry không làm tăng outcome cuối cùng nhiều lần.
- Giá trị tag luôn thuộc tập đã quy định.
- Các meter cùng tên có cùng tập khóa tag.
- Một nhánh rejected không bị tính thành failure kỹ thuật.
- Component ghi Counter không tạo registry mới hoặc đóng registry được inject.

Khi kiểm thử tích hợp với Prometheus hoặc backend khác, cần xác minh cả tên metric xuất, tag/label và cách backend xử lý reset. Việc test bằng SimpleMeterRegistry chỉ xác nhận logic đăng ký và tăng Counter trong bộ nhớ.

## 10. Những lỗi thường gặp

| Lỗi | Tác động | Cách xử lý |
|---|---|---|
| Đếm success trước khi nghiệp vụ hoàn tất | Báo thành công dù thao tác còn lỗi | Ghi sau khi xác định kết quả cuối |
| Gộp rejected vào failure | Tỷ lệ lỗi kỹ thuật bị sai | Tách outcome theo ý nghĩa nghiệp vụ |
| Ghi cùng sự kiện ở nhiều tầng | Counter tăng nhiều lần | Chọn một ranh giới instrumentation |
| Đếm từng retry vào Counter outcome cuối | Tăng số failure dù operation đã thành công | Tách attempt và operation |
| Dùng Counter cho số lượng hiện tại | Không thể giảm khi trạng thái thay đổi | Dùng Gauge |
| Đưa exception message vào tag | Cardinality tăng mạnh | Dùng nhóm lỗi hữu hạn |
| Dùng cùng tên cho event khác ý nghĩa | Dashboard và cảnh báo gây hiểu nhầm | Đặt tên meter riêng theo đơn vị đếm |
| Dùng Counter như dữ liệu giao dịch bền vững | Mất hoặc lệch dữ liệu khi process dừng | Lưu nghiệp vụ trong kho dữ liệu bền vững |

## 11. Checklist triển khai

Trước khi đưa Counter outcome vào ứng dụng, hãy xác nhận:

- [ ] Đã xác định rõ đơn vị đếm là request, attempt, operation hay item.
- [ ] **success**, **failure** và **rejected** có định nghĩa nghiệp vụ rõ ràng.
- [ ] Các outcome loại trừ nhau tại ranh giới đo và một operation chỉ ghi một kết quả cuối.
- [ ] Counter chỉ tăng khi sự kiện thực sự xảy ra.
- [ ] Cùng một tên meter sử dụng cùng tập khóa tag ở mọi nhánh.
- [ ] Giá trị tag là tập hữu hạn và không chứa định danh riêng hoặc thông điệp tự do.
- [ ] Retry được đo riêng nếu cần phân tích số lần thử.
- [ ] Không trùng lặp Counter với Timer hoặc instrumentation ở tầng khác.
- [ ] Truy vấn dashboard dùng rate/increase phù hợp với mục tiêu.
- [ ] Metrics không được dùng thay cho dữ liệu giao dịch cần lưu trữ bền vững.

Counter giúp ứng dụng trả lời câu hỏi có bao nhiêu sự kiện thành công, thất bại hoặc bị từ chối. Để số liệu đáng tin cậy, hãy định nghĩa outcome và đơn vị đếm trước, ghi nhận đúng một lần tại ranh giới nghiệp vụ, giữ tag ổn định và dùng truy vấn rate để đọc xu hướng. Khi đó, Counter trở thành tín hiệu vận hành hữu ích cho việc theo dõi lưu lượng, chất lượng xử lý và sức khỏe của dịch vụ.

