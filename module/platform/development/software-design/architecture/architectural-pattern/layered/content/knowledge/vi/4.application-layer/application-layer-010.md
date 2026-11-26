# Tầng ứng dụng

## Nhận diện service quá lớn và ca sử dụng bị chia nhỏ thiếu ý nghĩa

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — tầng ứng dụng điều phối các ca sử dụng và kết nối mô hình nghiệp vụ với những cổng mà hệ thống cần. Một service ở tầng này cần đủ trách nhiệm để hoàn tất một mục tiêu nghiệp vụ, đồng thời có ranh giới đủ rõ để không trở thành nơi chứa mọi thao tác của hệ thống.

Hai kiểu thiết kế thường gây khó khăn là service phình to, ôm nhiều mục tiêu không liên quan, và ca sử dụng bị chia thành quá nhiều lớp nhỏ chỉ chuyển tiếp lời gọi. Cả hai đều làm ranh giới khó hiểu: kiểu thứ nhất gom những lý do thay đổi khác nhau vào một nơi; kiểu thứ hai khiến người đọc phải đi qua nhiều lớp mà không thấy thêm chính sách hay ý nghĩa nghiệp vụ.

Bài học này dùng ví dụ quản lý đơn hàng trong Java/Spring để nhận diện hai thái cực, chọn ranh giới phù hợp và refactor mà vẫn giữ được luồng nghiệp vụ dễ kiểm thử.

## 1. Service tầng ứng dụng chịu trách nhiệm về điều gì?

Một **ca sử dụng (use case)** mô tả một mục tiêu mà tác nhân hoặc một quy trình bên ngoài muốn đạt được, chẳng hạn đặt hàng, hủy đơn hoặc hoàn tiền. Nó thường có đầu vào, kết quả, các bước điều phối và những điều kiện nghiệp vụ cần được bảo đảm.

Một **application service** thực hiện hoặc điều phối ca sử dụng đó. Nó thường:

- Nhận dữ liệu đầu vào ở dạng command hoặc request model phù hợp với ứng dụng.
- Tải các đối tượng hoặc dữ liệu cần thiết qua repository/port.
- Gọi mô hình miền để áp dụng quy tắc nghiệp vụ.
- Điều phối các cổng như lưu trữ, thanh toán hoặc gửi thông điệp.
- Xác định ranh giới giao dịch và trả kết quả của ca sử dụng.

Service tầng ứng dụng không nên trở thành nơi chứa toàn bộ quy tắc miền chỉ vì nó là nơi dễ gọi nhất. Quy tắc thuộc về một entity, value object hoặc domain service nên được đặt trong mô hình miền khi điều đó phù hợp. Application service chủ yếu quyết định **thứ tự và cách phối hợp** các bước của ca sử dụng.

Ví dụ, `PlaceOrderService` có thể tải giỏ hàng, yêu cầu mô hình miền tạo đơn, giữ chỗ tồn kho, yêu cầu cổng thanh toán và lưu kết quả. Việc tính tổng tiền hoặc kiểm tra một chuyển trạng thái hợp lệ có thể thuộc `Order` hoặc một đối tượng chính sách miền, tùy mô hình.

Không có quy tắc rằng mỗi use case bắt buộc phải là một class riêng, hoặc một service chỉ được có đúng một phương thức. Một nhóm thao tác có thể nằm chung nếu chúng thực sự chia sẻ trách nhiệm, chính sách và lý do thay đổi. Ngược lại, một ca sử dụng phức tạp có thể cần nhiều collaborator có trách nhiệm riêng.

## 2. Nhận diện service quá lớn

Service lớn không đơn giản là class có nhiều dòng. Một class dài có thể vẫn tập trung vào một quy trình phức tạp; một class ngắn lại có thể gom những thao tác không liên quan. Hãy quan sát trách nhiệm, phụ thuộc, luồng điều kiện và các lý do khiến class phải thay đổi.

### Dấu hiệu thường gặp

| Dấu hiệu | Vì sao đáng xem xét |
| --- | --- |
| Có nhiều thao tác hướng tới các mục tiêu khác nhau, như đặt hàng, hủy đơn, hoàn tiền và phát hành hóa đơn | Các thao tác có thể có chính sách và lý do thay đổi độc lập |
| Phụ thuộc vào nhiều nhóm collaborator không liên quan, như kho hàng, thanh toán, vận chuyển, hóa đơn và hồ sơ khách hàng | Service có thể đang gom nhiều trách nhiệm hoặc điều phối nhiều quy trình riêng |
| Có nhiều nhánh theo loại thao tác, trạng thái hoặc cờ chế độ | Một phương thức có thể đang xử lý nhiều ca sử dụng hoặc nhiều biến thể nghiệp vụ khó hiểu |
| Thay đổi một tính năng buộc phải sửa những phần không liên quan trong cùng class | Mức độ kết dính có thể thấp |
| Kiểm thử một thao tác phải dựng nhiều collaborator không cần thiết cho thao tác đó | Ranh giới trách nhiệm có thể quá rộng |
| Giao dịch bao trùm nhiều thao tác không cùng mục tiêu hoặc giữ khóa lâu | Ranh giới giao dịch có thể chưa phù hợp với ca sử dụng |

Ví dụ, một `OrderService` duy nhất có các phương thức `place`, `cancel`, `refund`, `changeDeliveryAddress`, `dispatch`, `issueInvoice` và `resendInvoice`. Nó cần repository đơn hàng, cổng thanh toán, kho hàng, hãng vận chuyển, dịch vụ hóa đơn và dịch vụ thông báo. Khi thay đổi quy tắc hoàn tiền, nhóm phải đọc và kiểm thử một class vốn còn chịu trách nhiệm tạo đơn và giao hàng. Đoạn mã sau lược bỏ constructor và phần thân phương thức để làm rõ phạm vi trách nhiệm:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryPort inventory;
    private final PaymentPort payments;
    private final ShippingPort shipping;
    private final InvoicePort invoices;
    private final NotificationPort notifications;

    // place(...), cancel(...), refund(...), dispatch(...),
    // changeDeliveryAddress(...), issueInvoice(...), resendInvoice(...)
}
```

Đoạn mã trên chỉ minh họa dấu hiệu tập trung trách nhiệm. Việc một service có nhiều dependency không tự động chứng minh thiết kế sai: một ca sử dụng như đặt hàng có thể hợp lý khi cần phối hợp tồn kho, thanh toán và lưu trữ. Cần xem các dependency phục vụ cùng một mục tiêu hay bị gom lại vì tiện đặt chung.

### Câu hỏi để xác định ranh giới

Khi xem một service, hãy hỏi:

1. Các phương thức có cùng phục vụ một mục tiêu nghiệp vụ hoặc một nhóm mục tiêu gắn chặt với nhau không?
2. Chúng có dùng chung chính sách, trạng thái và các bất biến nghiệp vụ không?
3. Chúng thường thay đổi cùng nhau vì cùng một lý do không?
4. Một thao tác có cần biết collaborator hoặc trạng thái chỉ phục vụ thao tác khác không?
5. Có thể kiểm thử một ca sử dụng mà không dựng toàn bộ hệ sinh thái phụ thuộc của service không?

Nếu câu trả lời cho thấy các thao tác thuộc những mục tiêu độc lập, đó là cơ sở để tách. Nếu các phương thức chỉ là các bước liên quan của cùng một quy trình và cùng bảo vệ một bất biến, giữ chúng gần nhau có thể làm thiết kế dễ hiểu hơn.

## 3. Nhận diện use case bị chia nhỏ thiếu ý nghĩa

Ở thái cực còn lại, một quy trình đơn giản bị chia thành nhiều service hoặc handler mà mỗi lớp chỉ đổi tên lời gọi rồi chuyển tiếp. Ví dụ rút gọn sau minh họa cấu trúc phụ thuộc; các constructor và kiểu cộng tác được lược bỏ:

```java
@Service
class ValidateOrderService {
    public void validate(PlaceOrderCommand command) {
        validator.validate(command);
    }
}

@Service
class SaveOrderService {
    public void save(Order order) {
        repository.save(order);
    }
}

@Service
class PlaceOrderService {
    private final ValidateOrderService validation;
    private final CreateOrderService creation;
    private final SaveOrderService saving;

    public OrderId place(PlaceOrderCommand command) {
        validation.validate(command);
        Order order = creation.create(command);
        saving.save(order);
        return order.getId();
    }
}
```

Nếu các lớp trên không sở hữu chính sách riêng, không có hợp đồng hữu ích cho nhiều bên sử dụng và không tạo ra ranh giới giao dịch hoặc kiểm thử cần thiết, chúng chỉ làm người đọc phải lần theo thêm nhiều bước. Tên lớp mang vẻ như các ca sử dụng riêng, nhưng `ValidateOrder` và `SaveOrder` ở đây chỉ là các bước nội bộ của mục tiêu `PlaceOrder`.

### Dấu hiệu chia vụn

- Mỗi lớp chỉ gọi đúng một phương thức của repository hoặc collaborator rồi trả nguyên kết quả.
- Tên lớp là động từ kỹ thuật như `LoadX`, `SaveX`, `MapX`, `ValidateX`, nhưng không đại diện cho mục tiêu mà người dùng hoặc quy trình nghiệp vụ nhận biết.
- Để hiểu một ca sử dụng đơn giản, người đọc phải mở qua nhiều class mà không thấy thêm quy tắc, quyết định hoặc ranh giới.
- Các lớp không có người sử dụng độc lập; chỉ có một service gọi chúng ngay theo một chuỗi cố định.
- Việc tách khiến dữ liệu phải chuyển qua nhiều DTO hoặc tham số trung gian mà không có lợi ích rõ ràng.
- Kiểm thử phải mock gần như mọi lớp trong chuỗi, trong khi hành vi cần kiểm tra chỉ là một quy trình nhỏ.

Các dấu hiệu này không có nghĩa helper hoặc collaborator nhỏ là xấu. Một validator dùng chung, một bộ chuyển đổi phức tạp, một cổng tích hợp hoặc một chính sách có thể kiểm thử độc lập đều có thể là thành phần hữu ích. Điều cần đánh giá là **lớp đó có sở hữu một trách nhiệm hoặc ranh giới có ý nghĩa hay chỉ tồn tại để thêm một lần chuyển tiếp**.

## 4. Chọn độ hạt của use case theo mục tiêu nghiệp vụ

Hãy bắt đầu từ kết quả mà hệ thống cần đạt được, sau đó xác định các bước phối hợp để đạt kết quả đó. Một bước nội bộ không tự động trở thành use case riêng.

| Câu hỏi | Nghiêng về một use case độc lập | Nghiêng về bước nội bộ |
| --- | --- | --- |
| Có mục tiêu nghiệp vụ riêng không? | Có kết quả mà tác nhân/quy trình có thể yêu cầu độc lập | Chỉ phục vụ mục tiêu lớn hơn |
| Có chính sách hoặc điều kiện riêng không? | Có quy tắc và kết quả lỗi cần quản lý riêng | Chỉ thực hiện một thao tác kỹ thuật đơn giản |
| Có ranh giới giao dịch hoặc tính nhất quán riêng không? | Có thể cần cam kết và xử lý lỗi độc lập | Cần cùng giao dịch với quy trình cha |
| Có nhiều bên gọi hoặc tái sử dụng thực sự không? | Có nhiều luồng cần cùng một khả năng với hợp đồng ổn định | Chỉ có một caller và không có nhu cầu độc lập |
| Có lý do thay đổi độc lập không? | Quy tắc thay đổi theo chính sách riêng | Thường thay đổi cùng quy trình cha |

Không cần mọi tiêu chí đều đúng. Hãy cân nhắc toàn bộ bối cảnh: nghiệp vụ, quyền sở hữu dữ liệu, tính nhất quán, cách vận hành và nhu cầu kiểm thử. Tách vì “sau này có thể tái sử dụng” thường dẫn tới abstraction chưa có người dùng thật.

### Ví dụ: đặt hàng và hủy đơn

`PlaceOrder` và `CancelOrder` thường là hai mục tiêu riêng. Đặt hàng có thể kiểm tra sản phẩm, tính giá, giữ chỗ tồn kho và yêu cầu thanh toán. Hủy đơn có thể kiểm tra trạng thái hiện tại, giải phóng tồn kho và yêu cầu hoàn tiền theo chính sách. Chúng có lý do thay đổi và phối hợp cổng khác nhau, nên thường hợp lý khi có hai application service.

Ngược lại, `LoadOrderForPlacement`, `CalculateOrderSubtotalStep` và `PersistOrderAfterPlacement` có thể chỉ là các bước nội bộ của `PlaceOrder`. Chỉ tách chúng thành collaborator khi mỗi phần có logic đủ tập trung, có thể thay đổi độc lập hoặc có ranh giới cần kiểm thử riêng.

## 5. Refactor service lớn mà vẫn giữ use case rõ ràng

Một cách làm thực tế là phân loại các thao tác công khai theo mục tiêu nghiệp vụ, sau đó tách theo nhóm trách nhiệm thay vì tách theo từng dòng lệnh.

Giả sử `OrderService` đang xử lý cả đặt và hủy đơn. Có thể tách thành hai application service với cổng cần thiết cho từng luồng:

```java
@Service
public class PlaceOrderService {
    private final OrderRepository orders;
    private final InventoryPort inventory;
    private final PaymentPort payments;

    public PlaceOrderService(
            OrderRepository orders,
            InventoryPort inventory,
            PaymentPort payments) {
        this.orders = orders;
        this.inventory = inventory;
        this.payments = payments;
    }

    @Transactional
    public OrderId handle(PlaceOrderCommand command) {
        Order order = Order.place(command.items(), command.customerId());
        inventory.reserve(order.items());
        payments.authorize(order.id(), order.total());
        orders.save(order);
        return order.id();
    }
}
```

```java
@Service
public class CancelOrderService {
    private final OrderRepository orders;
    private final InventoryPort inventory;
    private final PaymentPort payments;

    public CancelOrderService(
            OrderRepository orders,
            InventoryPort inventory,
            PaymentPort payments) {
        this.orders = orders;
        this.inventory = inventory;
        this.payments = payments;
    }

    @Transactional
    public void handle(CancelOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);
        order.cancel();
        inventory.release(order.items());
        payments.requestRefund(order.id());
        orders.save(order);
    }
}
```

Đây là mã minh họa; một hệ thống thực tế cần xử lý kết quả và lỗi của các dịch vụ ngoài, cũng như quyết định cách phối hợp giao dịch cục bộ với thanh toán hoặc kho hàng. Gọi một dịch vụ bên ngoài bên trong `@Transactional` không khiến hệ thống phân tán trở thành một giao dịch ACID duy nhất. Cần thiết kế timeout, retry, idempotency hoặc quy trình bù trừ phù hợp khi nghiệp vụ yêu cầu.

Sau khi tách, mỗi service có mục tiêu rõ hơn và chỉ giữ các collaborator cần cho mục tiêu đó. Nếu hai service cùng cần một chính sách tính phí thực sự chung, có thể đưa chính sách vào domain model hoặc một collaborator có trách nhiệm rõ ràng. Không cần tạo `CalculateFeeService` chỉ để bọc một phép gọi đơn giản nếu không có ranh giới hay chính sách độc lập.

## 6. Tránh cả hai thái cực khi thiết kế mới

Trước khi thêm class, hãy mô tả ca sử dụng bằng một câu: “Khi [tác nhân/quy trình] yêu cầu [mục tiêu], hệ thống [kết quả]”. Sau đó liệt kê các quy tắc, dữ liệu và cổng mà ca sử dụng cần. Một application service có thể điều phối các bước đó; các phần có chính sách riêng được đặt ở domain hoặc collaborator phù hợp.

Khi service bắt đầu lớn lên, hãy xem xét:

1. Phương thức nào phục vụ mục tiêu khác nhau?
2. Có nhóm thao tác nào thay đổi vì một lý do khác hoặc cần collaborator khác không?
3. Có quy tắc nào thuộc domain model thay vì application service không?
4. Có bước nào chỉ chuyển tiếp mà không thêm ý nghĩa và có thể gộp lại không?
5. Sau khi tách, người đọc có thể nhận ra luồng use case từ tên và điểm vào không?

Giữ các bước liên quan trong cùng use case giúp người đọc thấy trình tự điều phối. Tách collaborator khi có một trách nhiệm đủ rõ, một chính sách có ý nghĩa, một tích hợp kỹ thuật hoặc nhu cầu kiểm thử độc lập. Một service không cần nhỏ nhất có thể; nó cần tập trung và dễ hiểu.

## 7. Kiểm thử như một cách quan sát ranh giới

Ranh giới hợp lý giúp kiểm thử tập trung vào hành vi cần bảo vệ:

- Kiểm thử domain xác nhận `Order` không cho phép chuyển trạng thái sai hoặc tính tổng tiền không đúng.
- Kiểm thử `PlaceOrderService` xác nhận ca sử dụng gọi các port theo đúng trình tự và lưu kết quả cần thiết.
- Kiểm thử `CancelOrderService` xác nhận điều kiện hủy, giải phóng tồn kho và yêu cầu hoàn tiền.
- Kiểm thử tích hợp adapter xác nhận repository, payment adapter hoặc inventory adapter giao tiếp đúng với hệ thống ngoài.

Nếu kiểm thử một service phải tạo hàng chục mock cho những thao tác không liên quan, hãy xem xét liệu service đang ôm quá nhiều mục tiêu. Nếu kiểm thử một use case phải dựng nhiều lớp chỉ chuyển tiếp để xác minh một hành vi đơn giản, hãy xem xét liệu ranh giới có bị chia vụn. Đây là tín hiệu để điều tra, không phải quy tắc máy móc: một quy trình phức tạp có thể cần nhiều collaborator thật sự.

## Tự kiểm tra

1. Vì sao số dòng hoặc số dependency không đủ để kết luận một application service quá lớn?
2. `ValidateOrderService` chỉ gọi một validator và chỉ được `PlaceOrderService` sử dụng. Cần thêm lý do nào để việc tách lớp này trở nên có ý nghĩa?
3. Vì sao `PlaceOrder` và `CancelOrder` thường có thể là hai use case riêng dù cùng thao tác trên `Order`?
4. Khi một service vừa điều phối nhiều thao tác vừa chứa quy tắc chuyển trạng thái, nên cân nhắc trách nhiệm nào thuộc application và trách nhiệm nào thuộc domain?
5. Tách một ca sử dụng thành nhiều service có thể ảnh hưởng thế nào tới ranh giới giao dịch và kiểm thử?

