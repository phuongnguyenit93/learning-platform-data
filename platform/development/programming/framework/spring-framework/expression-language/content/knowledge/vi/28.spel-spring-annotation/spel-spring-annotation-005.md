# SpEL trong @EventListener condition

Spring Framework cho phép dùng Spring Expression Language (SpEL) trong thuộc tính **condition** của annotation **@EventListener**. Điều kiện được đánh giá khi một event phù hợp được phát tới listener. Chỉ khi kết quả là Boolean true, method listener mới được gọi.

Tính năng này hữu ích khi nhiều event cùng kiểu nhưng chỉ một số event cần kích hoạt một handler cụ thể. Ví dụ, listener chỉ xử lý đơn hàng có tổng tiền vượt ngưỡng, chỉ nhận thông báo thuộc một kênh nhất định hoặc chỉ chạy khi một feature đang được bật.

Điều kiện là một biểu thức SpEL, vì vậy có thể đọc thuộc tính của event, tham số method, biến trong evaluation context và bean được phân giải bởi Spring. Cần giữ điều kiện ngắn gọn, dễ kiểm thử và tránh gọi method có tác dụng phụ trong lúc lọc event.

## 1. @EventListener và thuộc tính condition

### 1.1. Khai báo listener cơ bản

Một method được đánh dấu bằng @EventListener sẽ được Spring đăng ký làm event listener:

~~~java
@Component
public class OrderEventListener {

    @EventListener
    public void handleOrderPlaced(OrderPlacedEvent event) {
        // Xử lý event
    }
}
~~~

Khi ứng dụng publish một event có kiểu phù hợp, Spring gọi method listener theo cơ chế event multicaster.

Có thể phát event qua ApplicationEventPublisher:

~~~java
@Component
public class OrderService {

    private final ApplicationEventPublisher publisher;

    public OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void placeOrder(OrderPlacedEvent event) {
        publisher.publishEvent(event);
    }
}
~~~

Event có thể là lớp kế thừa ApplicationEvent hoặc một object thông thường được publish làm payload event. Spring hỗ trợ publish object event từ các phiên bản hiện đại của framework.

### 1.2. Thêm condition

Thuộc tính condition nhận một chuỗi biểu thức SpEL:

~~~java
@EventListener(condition = "#a0.total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
    // Chỉ xử lý đơn hàng có total >= 100
}
~~~

Khi event phù hợp với kiểu tham số của method được phát:

1. Spring xác định listener có thể nhận event.
2. Biểu thức condition được đánh giá trong context dành cho listener.
3. Nếu kết quả là true, method được gọi.
4. Nếu kết quả là false, method bị bỏ qua đối với event đó.

Condition chỉ quyết định method listener cụ thể có được gọi hay không. Nó không hủy event, không ngăn các listener khác nhận event và không thay đổi việc event đã được publish.

### 1.3. Condition mặc định

Nếu không khai báo condition, listener không có bộ lọc SpEL bổ sung:

~~~java
@EventListener
public void handleAllOrders(OrderPlacedEvent event) {
}
~~~

Có thể hiểu condition mặc định là không đặt điều kiện lọc theo biểu thức. Khi cần lọc, hãy thêm condition trực tiếp vào annotation thay vì tạo nhiều nhánh if giống nhau ở đầu method.

## 2. Truy cập event và method arguments

### 2.1. Dùng #a0 và #p0

Trong condition, các đối số của listener method có thể được truy cập bằng chỉ số:

~~~java
@EventListener(condition = "#a0.total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
}
~~~

**#a0** tham chiếu argument đầu tiên. **#p0** là cách viết tương thích cho cùng vị trí tham số.

Với listener nhận một event argument, #a0 thường là cách rõ ràng và ổn định để truy cập payload mà method sẽ nhận.

### 2.2. Dùng #root.args

Evaluation context của event listener cung cấp các argument dưới dạng mảng qua root object:

~~~java
@EventListener(condition = "#root.args[0].total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
}
~~~

Có thể dùng **args** thay cho **#root.args** trong ngữ cảnh biểu thức phù hợp:

~~~java
@EventListener(condition = "args[0].total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
}
~~~

Cách viết #a0 ngắn hơn cho tham số đầu tiên; #root.args hữu ích khi cần thể hiện rõ đang truy cập danh sách argument.

### 2.3. Dùng tên tham số

Spring có thể cho phép truy cập argument bằng tên tham số nếu metadata tên tham số được giữ lại và ParameterNameDiscoverer xác định được tên đó:

~~~java
@EventListener(condition = "#orderEvent.total >= 100")
public void handleLargeOrder(OrderPlacedEvent orderEvent) {
}
~~~

Để việc khám phá tên tham số đáng tin cậy, hãy cấu hình build giữ metadata tên tham số, ví dụ tùy chọn **-parameters** của Java compiler. Khả năng khám phá cũng phụ thuộc phiên bản Spring và cách class được biên dịch.

Nếu không chắc tên tham số có được giữ hay không, dùng #a0 hoặc #p0 để tránh condition phụ thuộc metadata biên dịch.

### 2.4. #root.event và event

Event expression context cũng cung cấp event hiện tại qua root object:

~~~java
#root.event
~~~

Có thể dùng thuộc tính của event thông qua root event nếu kiểu event và accessor cho phép. Trong khi đó:

- **#root.event** tham chiếu event đang được xử lý.
- **#root.args** là các argument đã phân giải cho listener method.
- **#a0** hoặc **#p0** tham chiếu argument đầu tiên.
- **#root** là root object dành cho việc đánh giá condition.

Với payload event được truyền vào tham số method, dùng #a0 hoặc tên tham số thường giúp biểu thức bám sát đúng object mà method nhận. Khi cần truy cập metadata của event Spring, kiểm tra kiểu thực tế của event được cung cấp trong context.

## 3. Viết điều kiện theo thuộc tính event

### 3.1. Lọc theo trạng thái

Giả sử event có các getter JavaBean:

~~~java
public class OrderPlacedEvent {

    private final String orderId;
    private final String status;
    private final BigDecimal total;

    public OrderPlacedEvent(
            String orderId,
            String status,
            BigDecimal total) {
        this.orderId = orderId;
        this.status = status;
        this.total = total;
    }

    public String getOrderId() {
        return orderId;
    }

    public String getStatus() {
        return status;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

Listener chỉ nhận đơn hàng đã thanh toán:

~~~java
@EventListener(condition = "#a0.status == 'PAID'")
public void handlePaidOrder(OrderPlacedEvent event) {
    // Xử lý đơn đã thanh toán
}
~~~

SpEL truy cập property status qua property accessor, thường dựa trên getter getStatus().

### 3.2. Kết hợp nhiều điều kiện

Có thể kết hợp AND, OR và phép so sánh:

~~~java
@EventListener(
    condition = "#a0.status == 'PAID' && #a0.total >= 100"
)
public void handleQualifiedOrder(OrderPlacedEvent event) {
}
~~~

Listener chỉ chạy khi cả trạng thái và tổng tiền đều thỏa mãn.

Ví dụ dùng OR:

~~~java
@EventListener(
    condition = "#a0.status == 'PAID' || #a0.status == 'SETTLED'"
)
public void handleCompletedOrder(OrderPlacedEvent event) {
}
~~~

Khi biểu thức có nhiều nhóm logic, dùng dấu ngoặc và xuống dòng để thể hiện đúng cấu trúc nghiệp vụ.

### 3.3. Lọc theo chuỗi

Có thể so sánh mã kênh, loại sự kiện hoặc tên trạng thái:

~~~java
@EventListener(condition = "#a0.channel == 'WEB'")
public void handleWebOrder(OrderPlacedEvent event) {
}
~~~

Phép bằng String phân biệt chữ hoa và chữ thường. Nếu domain yêu cầu không phân biệt hoa thường, hãy chuẩn hóa dữ liệu trước khi publish hoặc dùng method so sánh phù hợp, đồng thời bảo vệ trường hợp null.

Ví dụ:

~~~java
@EventListener(
    condition = "#a0.channel != null && #a0.channel.equalsIgnoreCase('web')"
)
public void handleWebOrder(OrderPlacedEvent event) {
}
~~~

Không nên đặt một chuỗi chuẩn hóa dài trong nhiều annotation. Nếu quy tắc được tái sử dụng, hãy chuẩn hóa event ở nơi tạo event hoặc đưa ra một predicate có tên rõ ràng.

### 3.4. Lọc theo giá trị số

SpEL hỗ trợ các phép so sánh số:

~~~java
@EventListener(condition = "#a0.total > 1000")
public void handleHighValueOrder(OrderPlacedEvent event) {
}
~~~

Khi total là BigDecimal, hãy kiểm thử biểu thức với kiểu thực tế và phiên bản Spring đang dùng. Tránh chuyển số tiền thành double chỉ để so sánh nếu nghiệp vụ yêu cầu độ chính xác thập phân.

Ngưỡng nên đến từ cấu hình hoặc dữ liệu đã được xác thực nếu cần thay đổi theo môi trường. Không hard-code nhiều ngưỡng khác nhau trong các listener khi chúng cùng đại diện cho một chính sách nghiệp vụ.

## 4. Xử lý null trong condition

### 4.1. Kiểm tra null trước khi truy cập sâu

Nếu event có thể chứa một trường null, hãy đặt null guard trước:

~~~java
@EventListener(
    condition = "#a0.customer != null && #a0.customer.active"
)
public void handleActiveCustomerOrder(OrderPlacedEvent event) {
}
~~~

Toán tử AND đánh giá ngắn mạch. Nếu customer là null, vế truy cập active không được đánh giá.

### 4.2. Dùng safe navigation

Có thể dùng safe navigation ở property path khi phiên bản Spring hỗ trợ:

~~~java
@EventListener(
    condition = "#a0.customer?.active == true"
)
public void handleActiveCustomerOrder(OrderPlacedEvent event) {
}
~~~

Safe navigation xử lý receiver null tại vị trí có ?. Nó không xử lý property sai tên, method không tồn tại hoặc mọi exception phát sinh từ code được gọi.

### 4.3. Giá trị Boolean có thể null

Nếu property là Boolean wrapper thay vì primitive boolean, giá trị có thể null. Viết điều kiện rõ ràng:

~~~java
@EventListener(condition = "#a0.enabled == true")
public void handleEnabledEvent(MyEvent event) {
}
~~~

Cách này chỉ nhận trường hợp enabled là true. null và false đều không thỏa điều kiện.

Không nên dùng phủ định đơn giản nếu chưa xác định ý nghĩa của null. Ví dụ, enabled != true có thể bao gồm cả false và null; điều đó có thể không đúng với quy tắc nghiệp vụ.

### 4.4. Condition không phải validation

Nếu event thiếu dữ liệu bắt buộc, việc condition trả false chỉ làm listener bị bỏ qua. Nó không tự báo lỗi validation cho nơi publish event.

Hãy validate event trước khi publish hoặc tại application service. Condition phù hợp để chọn listener theo chính sách, không nên dùng làm cơ chế duy nhất để bảo đảm dữ liệu hợp lệ.

## 5. Dùng bean trong condition

### 5.1. Tham chiếu bean Spring

Event listener condition được đánh giá trong context có hỗ trợ bean resolution của Spring. Có thể tham chiếu bean bằng cú pháp **@beanName**:

~~~java
@EventListener(
    condition = "@featureFlags.isEnabled('order-alerts') && #a0.total > 0"
)
public void handleOrderAlert(OrderPlacedEvent event) {
}
~~~

Ví dụ này kiểm tra feature flag rồi kiểm tra total của event. Bean phải được đăng ký trong ApplicationContext và có method phù hợp.

### 5.2. Dùng bean như một policy

Nếu quy tắc phức tạp, có thể đưa phần quyết định vào một policy bean:

~~~java
@Component
public class OrderEventPolicy {

    public boolean shouldNotify(OrderPlacedEvent event) {
        return event.getTotal() != null
                && event.getTotal().compareTo(new BigDecimal("100")) >= 0;
    }
}
~~~

Listener:

~~~java
@EventListener(
    condition = "@orderEventPolicy.shouldNotify(#a0)"
)
public void notifyQualifiedOrder(OrderPlacedEvent event) {
}
~~~

Cách này giúp annotation ngắn hơn và policy có thể được kiểm thử trực tiếp bằng unit test.

### 5.3. Giữ method trong condition không có tác dụng phụ

Condition có thể được đánh giá trước khi listener method chạy. Nếu method được gọi trong condition gửi email, ghi database hoặc thay đổi trạng thái, hành động đó vẫn xảy ra ngay cả khi phần còn lại của condition khiến listener bị bỏ qua.

Vì vậy, method dùng trong condition nên là predicate thuần hoặc chỉ đọc, có chi phí thấp và kết quả xác định. Hãy để hành động nghiệp vụ trong listener method sau khi condition đã cho phép xử lý.

### 5.4. Không lạm dụng bean reference

Không nên gọi nhiều service trong một condition dài. Điều đó khiến việc quyết định listener có chạy hay không phụ thuộc vào nhiều thành phần và khó chẩn đoán khi có lỗi.

Nếu cần nhiều dữ liệu, hãy tính toán trước khi publish event hoặc đóng gói dữ liệu cần thiết vào event. Dùng policy bean khi quy tắc có ý nghĩa riêng và cần được chia sẻ.

## 6. Kết hợp nhiều listener với condition khác nhau

Một event có thể được gửi tới nhiều listener. Mỗi listener có condition riêng:

~~~java
@Component
public class OrderEventListeners {

    @EventListener(condition = "#a0.total >= 1000")
    public void handleHighValueOrder(OrderPlacedEvent event) {
        // Xử lý đơn giá trị cao
    }

    @EventListener(condition = "#a0.channel == 'WEB'")
    public void handleWebOrder(OrderPlacedEvent event) {
        // Xử lý đơn từ kênh web
    }

    @EventListener(condition = "#a0.status == 'CANCELLED'")
    public void handleCancelledOrder(OrderPlacedEvent event) {
        // Xử lý đơn bị hủy
    }
}
~~~

Khi một event được publish:

- Listener thứ nhất chỉ chạy nếu total đạt ngưỡng.
- Listener thứ hai chỉ chạy nếu channel là WEB.
- Listener thứ ba chỉ chạy nếu status là CANCELLED.

Một event có thể thỏa nhiều condition và kích hoạt nhiều listener. Condition của một listener không loại event khỏi những listener khác.

Nếu các listener cần thứ tự xử lý, hãy tìm hiểu cơ chế ordering như @Order và bảo đảm thứ tự đó phù hợp với yêu cầu. Không nên dựa vào thứ tự khai báo method trong source để suy luận thứ tự listener.

## 7. Condition với event payload và kiểu event

### 7.1. Event là object thông thường

Spring cho phép publish một object thông thường:

~~~java
publisher.publishEvent(
        new OrderPlacedEvent("O-100", "PAID", new BigDecimal("150"))
);
~~~

Listener nhận payload event theo kiểu tham số:

~~~java
@EventListener(condition = "#a0.status == 'PAID'")
public void handlePaidOrder(OrderPlacedEvent event) {
}
~~~

Dùng argument của method để truy cập dữ liệu payload giúp biểu thức bám sát chữ ký listener.

### 7.2. Lọc theo kiểu event

Việc xác định listener có nhận được event hay không trước hết dựa vào kiểu tham số và quy tắc phân giải event của Spring. Condition là bước lọc bổ sung sau khi listener được xem là phù hợp với event.

Không dùng condition để thay thế thiết kế kiểu event. Nếu hai nhóm sự kiện có cấu trúc hoặc ý nghĩa khác nhau, nên tạo các event class riêng để hệ thống định tuyến rõ ràng hơn.

### 7.3. Generic event

Với event generic, Spring có hỗ trợ phân giải kiểu trong một số trường hợp thông qua ResolvableType và kiểu tham số của listener. Tuy nhiên, generic type ở runtime có thể bị ảnh hưởng bởi type erasure và cách event được tạo.

Nếu listener phụ thuộc vào kiểu payload cụ thể, hãy kiểm thử việc phân giải event type trong ứng dụng thực tế. Condition chỉ nên kiểm tra nội dung sau khi listener đã nhận đúng loại event.

## 8. Condition và xử lý bất đồng bộ

### 8.1. Kết hợp @Async

Listener có thể được đánh dấu @Async nếu ứng dụng bật cơ chế async:

~~~java
@Async
@EventListener(condition = "#a0.total >= 100")
public void handleLargeOrder(OrderPlacedEvent event) {
    // Xử lý bất đồng bộ
}
~~~

Condition vẫn là tiêu chí quyết định listener có được gọi hay không. Việc chạy method bất đồng bộ không làm condition trở thành một cơ chế retry hoặc xử lý lỗi.

Cần cấu hình executor, giới hạn queue và chính sách từ chối task phù hợp. Không nên giả định event listener async sẽ tự bảo đảm event được xử lý bền vững sau khi ứng dụng dừng.

### 8.2. Exception trong async listener

Với listener bất đồng bộ, exception phát sinh trong method thường không được truyền ngược về thread đã publish event. Cần cấu hình xử lý lỗi cho executor hoặc AsyncUncaughtExceptionHandler theo nhu cầu.

Lỗi khi đánh giá condition là một giai đoạn khác với lỗi trong method async. Hãy quan sát log và kiểm thử cả hai trường hợp, đặc biệt khi condition gọi policy bean.

### 8.3. Khi cần xử lý bền vững

@EventListener là cơ chế event trong bộ nhớ của Spring application. Nếu nghiệp vụ yêu cầu bảo đảm giao nhận qua restart, retry, deduplication hoặc xử lý phân tán, hãy dùng message broker hoặc transactional outbox phù hợp. Condition trong annotation chỉ lọc việc gọi listener trong quy trình event hiện tại.

## 9. Condition và giá trị trả về của listener

Một @EventListener method có thể trả về object thay vì void. Spring có thể publish giá trị trả về như một event mới theo quy tắc của event listener adapter.

Condition quyết định method có được gọi hay không. Nếu condition false, method không chạy và không có giá trị trả về từ lần gọi đó để publish tiếp.

Nếu method trả về collection hoặc array, framework có thể publish các phần tử như các event riêng theo semantics được hỗ trợ. Hãy kiểm tra tài liệu của phiên bản Spring đang dùng nếu dựa vào hành vi này.

Không dùng condition như một bộ lọc toàn cục cho event được publish tiếp theo. Nó chỉ áp dụng cho listener method mang annotation đó.

## 10. Kiểm thử @EventListener condition

### 10.1. Kiểm thử bằng ApplicationContext

Có thể tạo một context kiểm thử, publish event và xác nhận listener chỉ được gọi khi condition đúng.

Ví dụ listener:

~~~java
@Component
public class OrderEventListener {

    private final List<String> handled = new ArrayList<>();

    @EventListener(condition = "#a0.total >= 100")
    public void handle(OrderPlacedEvent event) {
        handled.add(event.getOrderId());
    }

    public List<String> getHandled() {
        return handled;
    }
}
~~~

Test có thể publish một event dưới ngưỡng và một event đạt ngưỡng:

~~~java
publisher.publishEvent(
        new OrderPlacedEvent("O-LOW", "PAID", new BigDecimal("50"))
);

publisher.publishEvent(
        new OrderPlacedEvent("O-HIGH", "PAID", new BigDecimal("150"))
);
~~~

Sau khi event được xử lý đồng bộ, chỉ O-HIGH được ghi nhận.

Với context async, cần chờ hoặc đồng bộ test theo executor thay vì giả định listener hoàn tất ngay sau publishEvent.

### 10.2. Các trường hợp cần kiểm thử

Nên bao gồm:

- Condition true: listener được gọi.
- Condition false: listener bị bỏ qua.
- Giá trị nằm đúng tại ngưỡng so sánh.
- Property null và Boolean wrapper null.
- Chuỗi khác chữ hoa/chữ thường.
- Biểu thức dùng #a0, #p0 và tên tham số.
- Bean policy có mặt và hoạt động đúng.
- Bean hoặc method trong condition ném exception.
- Nhiều listener có condition độc lập.
- Event không phù hợp kiểu tham số.
- Listener async và chính sách xử lý lỗi.
- Listener trả về event tiếp theo nếu ứng dụng dùng chức năng này.

Không chỉ kiểm tra số lần gọi. Hãy xác nhận đúng event nào được xử lý để phát hiện condition viết sai hoặc nhầm tham số.

### 10.3. Kiểm thử policy riêng

Nếu condition gọi policy bean, kiểm thử policy như một class Java thông thường:

~~~java
assertTrue(policy.shouldNotify(highValueOrder));
assertFalse(policy.shouldNotify(lowValueOrder));
~~~

Sau đó có một integration test nhỏ xác nhận annotation gọi đúng policy và Spring đánh giá condition như mong đợi.

Cách tách này giúp lỗi ở logic nghiệp vụ không bị nhầm với lỗi cấu hình event listener hoặc SpEL.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Listener không chạy | Condition trả false hoặc event không khớp kiểu | Kiểm tra kiểu event và giá trị condition |
| Không tìm thấy tên tham số | Metadata tên tham số không được giữ | Dùng #a0/#p0 hoặc bật -parameters |
| Lỗi khi truy cập property | Getter/property sai tên hoặc receiver null | Kiểm tra event model và thêm null guard |
| Condition không trả Boolean hợp lệ | Biểu thức trả kiểu khác hoặc không chuyển đổi được | Viết biểu thức Boolean rõ ràng |
| Bean reference không được phân giải | Bean chưa đăng ký hoặc tên sai | Kiểm tra ApplicationContext và bean name |
| Condition gọi service quá chậm | Predicate thực hiện truy vấn hoặc I/O | Tính trước dữ liệu hoặc dùng policy nhẹ |
| Nhiều listener cùng chạy | Một event thỏa nhiều condition | Thiết kế condition độc lập và rõ mục tiêu |
| Async listener hoàn tất muộn | Executor xử lý ở thread khác | Đồng bộ test và cấu hình executor |
| Event bị bỏ qua mà không có validation error | Condition chỉ lọc listener | Validate event trước khi publish |
| Condition lỗi bị hiểu là false | Exception bị bắt quá rộng ở tầng ngoài | Phân loại lỗi evaluate và ghi log phù hợp |

Không nên bắt mọi exception khi đánh giá condition rồi trả false. Cách đó có thể làm event bị bỏ qua âm thầm khi biểu thức sai, bean lỗi hoặc dữ liệu không đúng cấu trúc.

## 12. Nguyên tắc thiết kế condition dễ bảo trì

Một condition tốt nên ngắn, có kết quả Boolean rõ ràng và chỉ đọc dữ liệu cần thiết.

- Dùng #a0 hoặc #p0 khi cần truy cập event argument ổn định.
- Dùng tên tham số khi build giữ metadata và tên đó làm biểu thức dễ hiểu hơn.
- Dùng #root.event hoặc #root.args khi cần thể hiện rõ cấu trúc event context.
- Đặt null guard trước truy cập sâu.
- Dùng bean policy cho quy tắc dài hoặc được tái sử dụng.
- Giữ method được gọi từ condition thuần, nhẹ và không có tác dụng phụ.
- Không dùng condition thay cho validation, authorization hoặc durable messaging.
- Kiểm thử true, false, null, lỗi resolution và nhiều listener cùng nhận event.

Nếu condition trở thành một biểu thức dài với nhiều lời gọi service, hãy chuyển phần quyết định sang một policy có tên rõ ràng. Annotation chỉ nên thể hiện ngắn gọn tiêu chí listener được phép xử lý event.

## 13. Tổng kết

Thuộc tính **condition** của **@EventListener** cho phép dùng SpEL để quyết định một listener method có được gọi cho event phù hợp hay không.

- **#a0** và **#p0** truy cập argument đầu tiên; **#root.args** truy cập danh sách argument.
- **#root.event** tham chiếu event hiện tại trong event expression context.
- Có thể dùng tên tham số nếu metadata được giữ và Spring khám phá được tên.
- Có thể kết hợp property, toán tử logic, null check và bean policy.
- Condition false chỉ bỏ qua listener đó; các listener khác vẫn có thể nhận event.
- Condition không thay thế validation, authorization, retry hoặc bảo đảm giao nhận bền vững.
- Với listener async, cần cấu hình executor và xử lý exception riêng.
- Giữ condition ngắn, chỉ đọc và dễ kiểm thử.

Dùng condition khi cần lọc event theo dữ liệu đã có. Với quy tắc nghiệp vụ phức tạp, hãy đặt logic trong policy/service Java và để condition gọi một predicate nhẹ, có tên rõ nghĩa.