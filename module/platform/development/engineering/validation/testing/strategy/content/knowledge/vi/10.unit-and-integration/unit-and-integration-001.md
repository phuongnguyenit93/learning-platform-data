# Xác định đơn vị hành vi và ranh giới cần cô lập

Thiết kế kiểm thử đơn vị và kiểm thử tích hợp bắt đầu từ một quyết định quan trọng: nhóm muốn xác minh hành vi nào, và cần kiểm soát những thành phần nào để có thể đưa ra kết luận đáng tin cậy? Nếu chọn đơn vị quá nhỏ, kiểm thử dễ gắn chặt với chi tiết triển khai và phải sửa liên tục khi mã được tái cấu trúc. Nếu chọn phạm vi quá rộng, kiểm thử trở nên chậm, phụ thuộc môi trường và khó xác định nguyên nhân khi thất bại.

Mục tiêu là chọn một **đơn vị hành vi có ý nghĩa** và xác định đúng **ranh giới cô lập** quanh nó. Kiểm thử đơn vị tập trung vào hành vi mà một đơn vị chịu trách nhiệm. Kiểm thử tích hợp xác minh các thành phần phối hợp đúng tại những ranh giới có thể phát sinh lỗi như cơ sở dữ liệu, hàng đợi, API hoặc bộ chuyển đổi. Hai loại kiểm thử bổ sung bằng chứng cho nhau trong chiến lược kiểm thử.

## 1. Đơn vị kiểm thử là đơn vị hành vi cần xác minh

Trong kiểm thử đơn vị, “đơn vị” không nhất thiết luôn là một phương thức hoặc một lớp. Nó là phạm vi nhỏ nhất có ý nghĩa đối với câu hỏi kiểm thử đang đặt ra. Tùy thiết kế phần mềm, đơn vị đó có thể là:

- Một hàm thuần thực hiện phép tính hoặc chuyển đổi dữ liệu.
- Một đối tượng miền (domain object) duy trì quy tắc và bất biến.
- Một lớp dịch vụ điều phối một hành vi qua các cộng tác viên.
- Một mô-đun nhỏ cung cấp một giao diện có trách nhiệm rõ ràng.

Điều quan trọng là kiểm thử phải có thể mô tả được hành vi quan sát được: điều kiện ban đầu, hành động, kết quả mong đợi và những tác động có liên quan. Ví dụ, thay vì kiểm tra riêng phương thức `calculateDiscount()` đã được gọi bao nhiêu lần, nhóm có thể xác minh rằng đơn hàng đủ điều kiện được giảm đúng số tiền và đơn hàng không đủ điều kiện giữ nguyên tổng tiền.

Một phương thức có thể chứa nhiều nhánh nghiệp vụ, trong khi một hành vi có thể đi qua nhiều phương thức. Vì vậy, lấy số lượng phương thức làm thước đo đơn vị kiểm thử thường dẫn đến cách chia phạm vi thiếu ý nghĩa.

### Bắt đầu từ trách nhiệm và hành vi

Để chọn đơn vị, hãy xem xét:

1. **Trách nhiệm:** thành phần nào chịu trách nhiệm cho quy tắc hoặc quyết định đang kiểm tra?
2. **Đầu vào và trạng thái:** điều kiện ban đầu nào ảnh hưởng đến hành vi?
3. **Kết quả quan sát được:** đầu ra, trạng thái mới hoặc tác động nào chứng minh hành vi đúng?
4. **Phụ thuộc:** thành phần đó cần cộng tác với những đối tượng hoặc hệ thống nào?
5. **Phạm vi lỗi:** nếu kiểm thử thất bại, có thể xác định tương đối rõ lỗi thuộc về logic đang kiểm tra hay phụ thuộc bên ngoài không?

Ví dụ, quy tắc áp dụng mã giảm giá có thể thuộc về `DiscountPolicy`. Đơn vị hành vi cần xác minh là quyết định giảm giá dựa trên hạn sử dụng, giá trị đơn hàng và nhóm khách hàng. Có thể kiểm tra quy tắc này trực tiếp bằng dữ liệu đầu vào và kết quả mong đợi, không cần dựng toàn bộ hệ thống đặt hàng.

## 2. Phân biệt kiểm thử đơn vị với kiểm thử tích hợp

Kiểm thử đơn vị và tích hợp khác nhau chủ yếu ở phạm vi và mục tiêu bằng chứng.

| Tiêu chí | Kiểm thử đơn vị | Kiểm thử tích hợp |
| --- | --- | --- |
| Phạm vi | Một đơn vị hành vi hoặc một nhóm nhỏ có ranh giới rõ | Hai hay nhiều thành phần phối hợp qua giao diện hoặc hạ tầng |
| Mục tiêu | Xác minh logic và trách nhiệm của đơn vị | Xác minh tương tác, ánh xạ dữ liệu, giao thức và ngữ nghĩa giữa các thành phần |
| Phụ thuộc | Thường được kiểm soát hoặc thay thế khi cần cô lập | Thường dùng ít nhất một phụ thuộc thật tại ranh giới đang xác minh |
| Tốc độ và độ ổn định | Thường nhanh và ít phụ thuộc môi trường | Thường chậm hơn và phụ thuộc cấu hình, hạ tầng hoặc dịch vụ |
| Lỗi thường phát hiện | Sai quy tắc nghiệp vụ, xử lý biên, chuyển trạng thái sai | Sai schema, mapping, transaction, truy vấn, thứ tự hoặc xử lý lỗi giữa các thành phần |
| Câu hỏi kết luận | Đơn vị có thực hiện đúng trách nhiệm không? | Các thành phần có phối hợp đúng trong điều kiện đã kiểm tra không? |

Một kiểm thử gọi HTTP API tự động không tự động là kiểm thử đơn vị. Nếu nó khởi động ứng dụng và xác minh dữ liệu được ghi vào cơ sở dữ liệu thật, đó thường là kiểm thử tích hợp hoặc kiểm thử dịch vụ. Tên gọi nên phản ánh phạm vi thực tế, không chỉ cách kiểm thử được chạy tự động.

Kiểm thử đơn vị có thể dùng nhiều đối tượng thật trong bộ nhớ nếu chúng nhẹ, xác định và không tạo phụ thuộc ngoài ý muốn. Ngược lại, kiểm thử tích hợp có thể dùng một số dịch vụ giả lập, nhưng cần xác định rõ ranh giới nào đang được xác minh bằng thành phần thật.

## 3. Xác định ranh giới cần cô lập

Ranh giới cô lập là điểm mà nhóm kiểm soát cách đơn vị kiểm thử tương tác với cộng tác viên. Mục đích là làm cho kiểm thử tập trung vào hành vi mục tiêu, có kết quả lặp lại và không bị ảnh hưởng bởi những yếu tố không liên quan.

Ranh giới thường xuất hiện ở:

- **Giao tiếp với hệ thống bên ngoài:** HTTP API, dịch vụ thanh toán, định danh, vận chuyển hoặc thông báo.
- **Lưu trữ:** cơ sở dữ liệu, cache, tệp hoặc kho đối tượng.
- **Giao tiếp bất đồng bộ:** hàng đợi, broker, event bus và consumer/producer.
- **Nguồn biến động:** đồng hồ hệ thống, số ngẫu nhiên, sinh ID hoặc cấu hình môi trường.
- **Tác động ngoài tiến trình:** gửi email, ghi tệp, gọi thiết bị hoặc thay đổi tài nguyên dùng chung.

Không phải mọi cộng tác viên đều cần được thay thế. Một đối tượng giá trị (value object), phép tính thuần hoặc quy tắc miền đơn giản thường nên được dùng trực tiếp vì nó là một phần của hành vi cần xác minh. Cô lập quá mức có thể khiến kiểm thử chỉ xác minh các mock được cấu hình theo giả định của chính người viết.

### Cô lập điều gì và giữ điều gì thật?

Trước khi thay thế một phụ thuộc, hãy tự hỏi:

- Phụ thuộc này có nằm trong hành vi mà kiểm thử cần đưa ra kết luận không?
- Nó có tạo ra tác động ngoài tiến trình, chậm, không ổn định hoặc khó thiết lập không?
- Có thể dùng một đối tượng thật nhẹ và xác định mà không làm kiểm thử phụ thuộc môi trường không?
- Nếu thay bằng test double, kiểm thử còn xác minh được điều gì và điều gì bị bỏ qua?

Ví dụ, khi kiểm tra quy tắc giảm giá, `Money`, `OrderLine` và `DiscountPolicy` có thể là đối tượng thật. Nếu `CheckoutService` gọi `PaymentGateway` bên ngoài, gateway có thể được thay bằng một test double để mô phỏng thành công, từ chối hoặc timeout. Kiểm thử này xác minh cách dịch vụ điều phối và phản ứng, không xác minh API của nhà cung cấp.

## 4. Các loại test double và cách sử dụng

Test double là đối tượng thay thế được dùng trong kiểm thử để kiểm soát hoặc quan sát tương tác với cộng tác viên. Các loại phổ biến có mục đích khác nhau:

| Loại | Mục đích | Ví dụ |
| --- | --- | --- |
| Dummy | Được truyền vào để đáp ứng chữ ký nhưng không được sử dụng trong hành vi kiểm thử | Đối tượng tham số không cần thiết cho trường hợp đang kiểm tra |
| Stub | Trả về dữ liệu hoặc kết quả định trước | Kho đơn hàng trả về một đơn đã biết khi được truy vấn |
| Fake | Có triển khai hoạt động đơn giản nhưng không dùng công nghệ production | Repository lưu dữ liệu trong bộ nhớ để kiểm tra logic ứng dụng |
| Spy | Ghi nhận cách nó được gọi để kiểm tra tương tác | Ghi lại sự kiện đã phát hoặc thông báo đã gửi |
| Mock | Có kỳ vọng về tương tác và xác minh lời gọi hoặc đối số | Xác minh gateway nhận đúng số tiền và mã đơn |

Trong thực tế, thư viện có thể dùng chung một đối tượng cho nhiều vai trò. Điều quan trọng là hiểu mục tiêu của nó. Stub cung cấp phản hồi; mock kiểm tra tương tác; fake mô phỏng một phần hành vi. Không nên gọi mọi đối tượng thay thế là mock.

### Khi nào nên dùng stub hoặc fake?

Dùng stub khi đơn vị cần một phản hồi cụ thể để đi qua một nhánh hành vi. Ví dụ, `PaymentGateway` trả về `DECLINED` để xác minh dịch vụ đánh dấu thanh toán thất bại và không xác nhận đơn hàng.

Dùng fake khi cần một triển khai nhẹ có hành vi hữu ích. Ví dụ, `InMemoryOrderRepository` có thể lưu đơn trong bộ nhớ để kiểm tra một dịch vụ ứng dụng thực hiện thêm, tìm và cập nhật đơn hàng. Fake giúp kiểm thử nhanh nhưng không xác minh truy vấn SQL, transaction hoặc ràng buộc của cơ sở dữ liệu thật.

### Khi nào nên dùng mock hoặc spy?

Dùng mock khi tương tác là một phần của hợp đồng hành vi cần xác minh. Ví dụ, khi thanh toán thất bại, dịch vụ không được phát sự kiện `OrderPaid`. Khi thanh toán thành công, dịch vụ phải gửi đúng mã đơn và số tiền đến gateway.

Spy hữu ích khi cần quan sát tác động nhưng vẫn muốn giữ phần lớn hành vi của đối tượng thật. Tuy nhiên, xác minh quá nhiều lời gọi nội bộ hoặc thứ tự gọi không có ý nghĩa nghiệp vụ sẽ làm kiểm thử gắn chặt với cấu trúc triển khai.

### Tránh mock mọi thứ

Nếu mọi đối tượng đều được thay bằng mock, kiểm thử có thể chạy rất nhanh nhưng không chứng minh các đối tượng thật phối hợp đúng. Mock thường phản ánh kỳ vọng mà người viết đã tự đặt ra; khi hợp đồng thực tế thay đổi, mock vẫn có thể tiếp tục trả lời theo giả định cũ.

Ưu tiên dùng đối tượng miền thật và các thành phần nhẹ. Chỉ thay thế phụ thuộc khi việc cô lập mang lại lợi ích rõ ràng, chẳng hạn kiểm soát lỗi, thời gian, dữ liệu hoặc tác động ngoài hệ thống.

## 5. Ví dụ: kiểm tra hành vi của dịch vụ thanh toán

Giả sử `CheckoutService` chịu trách nhiệm điều phối thanh toán. Nó sử dụng `OrderRepository` để đọc và cập nhật đơn hàng, `PaymentGateway` để tạo giao dịch và `EventPublisher` để phát sự kiện sau khi thanh toán thành công.

Ta muốn xác minh hành vi: khi gateway xác nhận thanh toán, đơn hàng chuyển sang trạng thái `PAID` và sự kiện `OrderPaid` được phát với đúng mã đơn.

```java
public class CheckoutService {
    private final OrderRepository orders;
    private final PaymentGateway gateway;
    private final EventPublisher events;

    public CheckoutService(
            OrderRepository orders,
            PaymentGateway gateway,
            EventPublisher events) {
        this.orders = orders;
        this.gateway = gateway;
        this.events = events;
    }

    public void checkout(String orderId) {
        Order order = orders.findById(orderId);
        PaymentResult result = gateway.charge(
            order.id(), order.total()
        );

        if (result.approved()) {
            order.markPaid(result.paymentId());
            orders.save(order);
            events.publish(new OrderPaid(order.id()));
        }
    }
}
```

Ở kiểm thử đơn vị, có thể dùng một đơn hàng thật trong bộ nhớ, stub cho gateway và spy hoặc mock cho repository cùng publisher. Kiểm thử cần tập trung vào kết quả nghiệp vụ và tương tác có ý nghĩa:

```java
@Test
void approvedPaymentMarksOrderPaidAndPublishesEvent() {
    Order order = Order.open("ORD-42", Money.of(12500, "VND"));
    OrderRepository orders = new InMemoryOrderRepository(order);
    PaymentGateway gateway = (orderId, amount) ->
        PaymentResult.approved("PAY-9");
    RecordingEventPublisher events = new RecordingEventPublisher();

    CheckoutService service =
        new CheckoutService(orders, gateway, events);

    service.checkout("ORD-42");

    assertEquals(OrderStatus.PAID,
        orders.findById("ORD-42").status());
    assertEquals(1, events.eventsOfType(OrderPaid.class).size());
}
```

Đây là mã minh họa; cách khởi tạo tiền, repository và publisher cần phù hợp với mô hình của ứng dụng thực tế. Kiểm thử xác minh trạng thái đơn và sự kiện đã ghi nhận. Một kiểm thử khác nên xác minh khi gateway từ chối thanh toán thì đơn không chuyển sang `PAID` và không phát sự kiện thành công.

Kiểm thử trên chưa chứng minh dữ liệu được ghi bền trong cơ sở dữ liệu thật, transaction hoạt động đúng hoặc thông điệp được broker phân phối. Những câu hỏi đó thuộc phạm vi kiểm thử tích hợp.

## 6. Khi nào cần giữ phụ thuộc thật?

Giữ phụ thuộc thật khi chính hành vi của nó là một phần quan trọng trong bằng chứng cần thu thập và có thể thiết lập nó một cách ổn định.

Ví dụ:

- Dùng cơ sở dữ liệu thật trong kiểm thử repository để xác minh SQL, mapping, constraint, transaction và migration.
- Dùng broker thật trong kiểm thử producer/consumer để xác minh cấu hình, serialization, acknowledgement và xử lý thông điệp trùng nếu đây là rủi ro cần kiểm tra.
- Dùng HTTP server cục bộ hoặc dịch vụ sandbox trong kiểm thử adapter để xác minh giao thức, header, timeout, parsing và ánh xạ lỗi.
- Dùng đồng hồ giả hoặc đồng hồ có thể điều khiển trong kiểm thử logic thời gian để kiểm tra hết hạn, lịch và thời điểm chuyển trạng thái.

Không nhất thiết phải kết nối tới production hoặc hệ thống bên ngoài thật. Có thể dùng container, dịch vụ thử nghiệm, server cục bộ hoặc sandbox. Điều cần thiết là thành phần thật nằm ở đúng ranh giới đang được xác minh.

## 7. Thiết kế kiểm thử tích hợp theo ranh giới

Kiểm thử tích hợp nên nhắm đến nơi có nguy cơ không tương thích hoặc có ngữ nghĩa mà test double không thể xác minh.

### Tích hợp với cơ sở dữ liệu

Kiểm tra repository hoặc adapter với loại cơ sở dữ liệu thực tế trong môi trường thử nghiệm. Các trường hợp có thể gồm:

- Lưu và đọc lại dữ liệu với kiểu, định dạng và giá trị null đúng.
- Ràng buộc duy nhất, khóa ngoại, constraint và quy tắc xóa/cập nhật.
- Transaction commit hoặc rollback khi một bước thất bại.
- Truy vấn, sắp xếp, phân trang và xử lý dữ liệu biên.
- Migration từ phiên bản schema trước và khả năng tương thích khi triển khai.

Một fake repository trong bộ nhớ không thể chứng minh SQL hoặc transaction trên cơ sở dữ liệu production hoạt động đúng. Ngược lại, không cần dùng cơ sở dữ liệu thật cho mọi kiểm thử logic ứng dụng; hãy chọn đúng câu hỏi cần xác minh.

### Tích hợp qua HTTP hoặc API

Kiểm thử adapter với server cục bộ hoặc sandbox có thể xác minh:

- Phương thức, đường dẫn, header và nội dung yêu cầu.
- Serialization, encoding, đơn vị và định dạng dữ liệu.
- Cách phân tích phản hồi thành công và lỗi.
- Timeout, kết nối bị ngắt, retry và xử lý phản hồi không hợp lệ.
- Tương thích phiên bản và hợp đồng giao tiếp.

Mock HTTP client có thể giúp kiểm tra cách ứng dụng phản ứng với phản hồi cụ thể. Nhưng cần thêm kiểm thử hợp đồng hoặc tích hợp để phát hiện sai khác giữa client và provider.

### Tích hợp với hàng đợi và sự kiện

Kiểm tra producer và consumer với broker hoặc môi trường tích hợp để xác minh:

- Tên topic/queue, schema và phiên bản thông điệp.
- Serialization/deserialization và metadata.
- Acknowledgement, retry, dead-letter queue và xử lý lỗi.
- Thông điệp trùng lặp, sai thứ tự hoặc đến muộn.
- Tính lặp an toàn và cập nhật trạng thái khi consumer xử lý lại.

Một kiểm thử gọi trực tiếp hàm xử lý thông điệp không xác minh broker phân phối hoặc lưu bền thông điệp đúng cấu hình. Cần chọn kiểm thử tích hợp cho những đặc tính phụ thuộc vào broker.

## 8. Chọn ranh giới theo rủi ro và chi phí

Không có quy tắc rằng mọi phụ thuộc đều phải mock hoặc mọi phụ thuộc đều phải thật. Quyết định cần cân bằng giữa độ tin cậy của bằng chứng, tốc độ chạy, độ ổn định, chi phí thiết lập và khả năng chẩn đoán.

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Logic miền thuần, dữ liệu đơn giản | Dùng đối tượng thật | Đây chính là hành vi cần xác minh, ít phụ thuộc ngoài |
| Phụ thuộc trả về dữ liệu có thể kiểm soát | Stub hoặc fake | Tạo điều kiện xác định và tập trung vào quyết định của đơn vị |
| Phụ thuộc có tác động ngoài hệ thống hoặc không ổn định | Test double ở kiểm thử đơn vị | Tránh gửi thông báo, thu tiền hoặc gọi dịch vụ thật trong mỗi lần chạy |
| Cần xác minh SQL, transaction hoặc schema | Thành phần lưu trữ thật trong kiểm thử tích hợp | Test double không thể xác minh hành vi hạ tầng |
| Cần xác minh giao thức hoặc schema API | Server thử nghiệm, sandbox hoặc kiểm thử hợp đồng | Xác minh ranh giới giao tiếp thực tế |
| Cần kiểm tra toàn bộ chuỗi nghiệp vụ quan trọng | Kiểm thử tích hợp hoặc hệ thống có chọn lọc | Nhiều thành phần phải phối hợp để tạo ra kết quả cuối cùng |

Rủi ro càng cao ở một ranh giới thì càng cần bằng chứng trực tiếp tại ranh giới đó. Ví dụ, nếu sai transaction có thể làm mất tiền hoặc tạo đơn trùng, kiểm thử với cơ sở dữ liệu và dịch vụ thanh toán thử nghiệm có giá trị hơn việc chỉ xác minh mock được gọi.

## 9. Những dấu hiệu cho thấy ranh giới kiểm thử chưa phù hợp

Kiểm thử có thể đang cô lập sai nếu xuất hiện các dấu hiệu:

- **Kiểm thử hỏng sau tái cấu trúc dù hành vi không đổi:** có thể kiểm thử phụ thuộc quá nhiều vào tên phương thức, thứ tự gọi hoặc cấu trúc nội bộ.
- **Một kiểm thử cần quá nhiều mock:** đơn vị có thể đang đảm nhận quá nhiều trách nhiệm hoặc ranh giới phụ thuộc chưa rõ.
- **Kiểm thử chỉ xác minh lời gọi mà không xác minh kết quả:** nhóm có thể đang kiểm tra cách triển khai thay vì hành vi có ý nghĩa.
- **Kiểm thử đơn vị thất bại vì môi trường ngoài:** một phụ thuộc chưa được cô lập khiến kiểm thử chậm hoặc không ổn định.
- **Bộ kiểm thử đơn vị luôn đạt nhưng tích hợp thường xuyên hỏng:** có thể thiếu kiểm thử ở các ranh giới dữ liệu, giao thức hoặc cấu hình.
- **Kiểm thử tích hợp quá lớn và khó chẩn đoán:** cần chia phạm vi theo ranh giới có trách nhiệm rõ hoặc bổ sung kiểm thử thành phần để khoanh vùng.
- **Fake khác xa hành vi production:** triển khai thay thế có thể che giấu khác biệt về transaction, thứ tự, đồng thời hoặc xử lý lỗi.

Khi gặp các dấu hiệu này, hãy xem lại hành vi cần xác minh, trách nhiệm của đơn vị và loại bằng chứng đang thiếu. Không nên chỉ thêm mock hoặc tăng số lượng kiểm thử mà không xem xét nguyên nhân.

## 10. Duy trì kiểm thử độc lập, xác định và dễ chẩn đoán

Một bộ kiểm thử hữu ích cần có kết quả ổn định và giải thích được. Các nguyên tắc sau giúp giảm lỗi giả và chi phí bảo trì:

- **Mỗi kiểm thử tự chuẩn bị dữ liệu:** tránh phụ thuộc vào thứ tự chạy hoặc dữ liệu do kiểm thử khác tạo ra.
- **Dọn dẹp tài nguyên:** đóng kết nối, xóa dữ liệu tạm, giải phóng cổng và tài nguyên dùng chung.
- **Kiểm soát thời gian và tính ngẫu nhiên:** dùng đồng hồ giả, seed xác định hoặc đầu vào được lưu lại khi cần.
- **Tránh phụ thuộc mạng không cần thiết:** kiểm thử đơn vị không nên gọi dịch vụ production hoặc Internet.
- **Dùng tên kiểm thử mô tả hành vi:** tên nên cho biết điều kiện và kết quả mong đợi.
- **Xác minh điều quan trọng:** assertion cần kiểm tra kết quả hoặc trạng thái có ý nghĩa; tránh kiểm tra quá nhiều chi tiết không phải hợp đồng.
- **Lưu bằng chứng khi thất bại:** thông báo lỗi cần chỉ ra dữ liệu, điều kiện, phiên bản hoặc ranh giới liên quan.

Với kiểm thử tích hợp, nên tạo môi trường có thể tái tạo, dùng dữ liệu riêng cho từng lần chạy và ghi lại phiên bản dịch vụ, schema, cấu hình. Nếu môi trường dùng chung, cần kiểm soát va chạm dữ liệu và tác động giữa các lần chạy.

## 11. Quy trình chọn đơn vị và ranh giới trong thực tế

Có thể áp dụng quy trình sau khi thêm hoặc thay đổi một hành vi:

1. **Mô tả hành vi:** viết điều kiện đầu vào, hành động và kết quả mong đợi bằng ngôn ngữ nghiệp vụ.
2. **Tìm nơi chịu trách nhiệm:** xác định lớp, mô-đun hoặc dịch vụ sở hữu quy tắc và trạng thái liên quan.
3. **Liệt kê cộng tác viên:** ghi rõ đối tượng miền, repository, client, broker, đồng hồ và các nguồn tác động ngoài.
4. **Phân loại phụ thuộc:** xác định phụ thuộc nào nhẹ và xác định, phụ thuộc nào chậm, biến động hoặc tạo tác động ngoài hệ thống.
5. **Chọn ranh giới kiểm thử đơn vị:** giữ lại đối tượng thật thuộc hành vi cần xác minh; thay thế những cộng tác viên cần kiểm soát bằng stub, fake, spy hoặc mock phù hợp.
6. **Xác định kiểm thử tích hợp bổ sung:** chọn ranh giới cần kiểm tra bằng cơ sở dữ liệu, broker, HTTP server hoặc dịch vụ sandbox thật.
7. **Định nghĩa bằng chứng:** nêu rõ trạng thái, đầu ra, tương tác hoặc dữ liệu cần xác minh và điều kiện đạt.
8. **Đánh giá lại sau khi triển khai:** nếu kiểm thử quá mong manh, nhiều mock hoặc bỏ sót lỗi tích hợp, xem lại ranh giới và bổ sung bằng chứng.

## 12. Checklist rà soát thiết kế kiểm thử

- [ ] Hành vi cần xác minh được mô tả rõ bằng điều kiện, hành động và kết quả mong đợi.
- [ ] Đơn vị kiểm thử được chọn theo trách nhiệm hành vi, không chỉ theo số lượng phương thức.
- [ ] Các đối tượng miền và giá trị thuần cần thiết được giữ thật khi phù hợp.
- [ ] Mỗi test double có mục đích rõ: dummy, stub, fake, spy hoặc mock.
- [ ] Các tương tác được xác minh là một phần có ý nghĩa của hợp đồng hành vi.
- [ ] Không có lời gọi dịch vụ production hoặc tác động ngoài ý muốn trong kiểm thử đơn vị.
- [ ] Các ranh giới quan trọng như database, API và broker có kiểm thử tích hợp phù hợp.
- [ ] Giới hạn của fake, mock, sandbox và môi trường thử nghiệm được ghi nhận.
- [ ] Kiểm thử độc lập, có thể lặp lại và dễ xác định nguyên nhân khi thất bại.
- [ ] Mỗi kiểm thử đóng góp bằng chứng cho một yêu cầu hoặc rủi ro cụ thể.

## 13. Những điểm cần ghi nhớ

- Đơn vị kiểm thử nên đại diện cho một hành vi có ý nghĩa và trách nhiệm rõ ràng; không nhất thiết là một phương thức.
- Kiểm thử đơn vị xác minh logic của đơn vị trong điều kiện có thể kiểm soát; kiểm thử tích hợp xác minh các thành phần phối hợp tại ranh giới.
- Cô lập những phụ thuộc cần kiểm soát, nhưng giữ các đối tượng miền thật khi chúng thuộc hành vi đang kiểm tra.
- Stub, fake, spy và mock có mục đích khác nhau; không nên thay thế mọi thứ bằng mock.
- Test double không chứng minh cơ sở dữ liệu, broker hoặc dịch vụ bên ngoài thật hoạt động đúng.
- Chọn kiểm thử tích hợp dựa trên rủi ro của giao diện, dữ liệu, giao thức và hạ tầng.
- Kiểm thử tốt cần độc lập, xác định, dễ chẩn đoán và gắn với bằng chứng cụ thể.

## Câu hỏi tự kiểm tra

1. Vì sao đơn vị kiểm thử không nhất thiết tương ứng với một phương thức hoặc một lớp?
2. Hãy phân biệt kiểm thử đơn vị và kiểm thử tích hợp qua ví dụ một dịch vụ đặt hàng.
3. Khi nào nên giữ đối tượng thật và khi nào nên dùng stub, fake, spy hoặc mock?
4. Một fake repository lưu dữ liệu trong bộ nhớ có thể và không thể xác minh những hành vi nào của cơ sở dữ liệu?
5. Vì sao kiểm thử đơn vị có nhiều mock vẫn có thể bỏ sót lỗi tích hợp quan trọng?
6. Hãy xác định ranh giới kiểm thử cho một hành vi trong hệ thống của bạn, liệt kê cộng tác viên cần cô lập và kiểm thử tích hợp cần bổ sung.
7. Một kiểm thử thường xuyên thất bại sau tái cấu trúc nhưng hành vi người dùng không đổi. Bạn sẽ xem xét những dấu hiệu nào để cải thiện thiết kế kiểm thử?
