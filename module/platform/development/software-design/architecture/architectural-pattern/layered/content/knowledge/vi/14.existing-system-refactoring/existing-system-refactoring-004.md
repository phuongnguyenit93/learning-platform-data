# Cải tiến hệ thống hiện có

## Chia service ôm quá nhiều trách nhiệm theo hành vi nghiệp vụ

Trong module `SOFTWARE_DESIGN_ARCHITECTURE_ARCHITECTURAL_PATTERN_LAYERED` — **Học tổ chức phần mềm theo kiến trúc phân tầng** — một service ở tầng ứng dụng có thể lớn dần qua nhiều lần bổ sung tính năng. Ban đầu nó chỉ xử lý một ca sử dụng; sau đó nhóm thêm hủy đơn, hoàn tiền, giao hàng, hóa đơn và thông báo vào cùng class vì các thao tác đều liên quan đến đơn hàng. Kết quả là một service có nhiều lý do thay đổi, nhiều dependency và nhiều nhánh điều kiện khó kiểm soát.

Cách cải tiến bền vững là chia service theo **hành vi nghiệp vụ**: nhóm những thao tác cùng phục vụ một mục tiêu, cùng chính sách và cùng nhịp thay đổi; tách những hành vi có mục tiêu hoặc điều kiện riêng. Việc chia cần giữ được hành vi hiện tại, ranh giới dữ liệu và transaction, đồng thời có thể triển khai từng bước trong hệ thống đang chạy.

Bài học này trình bày cách nhận diện service quá tải, khám phá các nhóm hành vi, thiết kế service mới và chuyển đổi an toàn trong Java/Spring. Mục tiêu không phải tạo nhiều class nhất có thể, mà làm cho mỗi ca sử dụng có điểm vào, trách nhiệm và các cộng tác viên dễ hiểu.

## 1. Nhận diện service đang ôm nhiều hành vi

Một class lớn chưa chắc đã là service quá tải. Hãy xem xét **những lý do khiến nó thay đổi**, các mục tiêu nghiệp vụ nó thực hiện và những chính sách mà nó phải biết.

Giả sử hệ thống cũ có `OrderService` với các phương thức:

```java
@Service
public class OrderService {
    private final OrderRepository orders;
    private final InventoryPort inventory;
    private final PaymentPort payments;
    private final ShippingPort shipping;
    private final InvoicePort invoices;
    private final NotificationPort notifications;

    public OrderId place(PlaceOrderCommand command) { /* ... */ }
    public void cancel(CancelOrderCommand command) { /* ... */ }
    public void refund(RefundCommand command) { /* ... */ }
    public void dispatch(DispatchCommand command) { /* ... */ }
    public void changeAddress(ChangeAddressCommand command) { /* ... */ }
    public void issueInvoice(InvoiceCommand command) { /* ... */ }
    public void resendInvoice(InvoiceCommand command) { /* ... */ }
}
```

Service này có thể đang xử lý nhiều hành vi khác nhau:

| Hành vi | Mục tiêu nghiệp vụ | Chính sách/cộng tác viên thường liên quan |
| --- | --- | --- |
| Đặt hàng | Tạo đơn hợp lệ và xác nhận yêu cầu mua | Giá, tồn kho, thanh toán, lưu đơn |
| Hủy đơn | Chuyển đơn sang trạng thái được phép hủy | Chủ sở hữu, trạng thái, thời hạn, giải phóng tồn kho |
| Hoàn tiền | Hoàn trả khoản tiền đủ điều kiện | Giao dịch thanh toán, số tiền đã thu, lịch sử hoàn tiền |
| Giao hàng | Bàn giao đơn cho đơn vị vận chuyển | Đóng gói, địa chỉ, hãng vận chuyển, trạng thái đơn |
| Đổi địa chỉ | Thay đổi điểm giao khi còn cho phép | Trạng thái vận chuyển, xác minh địa chỉ |
| Phát hành hóa đơn | Tạo chứng từ theo quy định | Thông tin thuế, mẫu hóa đơn, nhà cung cấp hóa đơn |

Các dấu hiệu cho thấy class cần được xem xét:

- Phương thức công khai phục vụ các mục tiêu khác nhau và có thể thay đổi độc lập.
- Mỗi nhóm phương thức cần một tập dependency khác nhau; thay đổi một tích hợp làm class chứa nhiều phần không liên quan phải biên dịch hoặc kiểm thử lại.
- Có nhiều nhánh theo `action`, `operationType` hoặc trạng thái để quyết định phải chạy quy trình nào.
- Một thao tác phải biết chính sách của những hành vi khác, dù không cần chúng để hoàn thành mục tiêu của mình.
- Kiểm thử một ca sử dụng phải dựng nhiều mock và dữ liệu không liên quan.
- Lỗi hoặc thay đổi ở một hành vi thường xuyên làm ảnh hưởng hành vi khác trong cùng class.

Đếm số dòng, số phương thức hoặc số dependency chỉ là tín hiệu ban đầu. Một ca sử dụng đặt hàng phức tạp có thể cần nhiều cộng tác viên nhưng vẫn là một trách nhiệm tập trung. Ngược lại, class ngắn vẫn có thể gom hai chính sách không liên quan.

## 2. Tìm ranh giới bằng hành vi nghiệp vụ

Đừng bắt đầu bằng việc chuyển từng phương thức sang một class mới. Trước tiên, hãy hiểu người dùng hoặc hệ thống bên ngoài muốn đạt kết quả gì, điều kiện nào phải đúng và dữ liệu nào bị thay đổi.

### Lập bản đồ các hành vi hiện có

Với mỗi phương thức công khai hoặc điểm vào đang được sử dụng, ghi lại:

1. **Tác nhân và mục tiêu:** ai yêu cầu thao tác và kết quả nghiệp vụ cần đạt là gì?
2. **Điều kiện trước:** trạng thái, quyền và dữ liệu nào phải tồn tại?
3. **Quy tắc quyết định:** chính sách nào quyết định thao tác được phép hay bị từ chối?
4. **Dữ liệu bị thay đổi:** aggregate, bảng hoặc tài nguyên nào được cập nhật?
5. **Tác dụng phụ:** có gọi thanh toán, kho hàng, vận chuyển, phát sự kiện hoặc gửi thông báo không?
6. **Tính nhất quán:** bước nào cần cùng thành công/thất bại trong một transaction, bước nào là quy trình bên ngoài?
7. **Lý do thay đổi:** thay đổi luật của hành vi này có thường đi cùng các hành vi khác không?

Ví dụ, `cancel` và `refund` có thể cùng liên quan đến tiền nhưng chưa chắc là cùng một hành vi. Hủy đơn là quyết định về việc đơn còn được phép tiếp tục hay không; hoàn tiền là quyết định và quy trình trả lại một khoản đã thu. Có trường hợp hủy đơn chưa thanh toán không cần hoàn tiền; có trường hợp hoàn tiền một phần mà không hủy đơn. Hai hành vi có thể phối hợp với nhau nhưng vẫn có mục tiêu và chính sách riêng.

### Nhóm theo lý do thay đổi và bất biến

Những thao tác nên ở gần nhau khi chúng:

- Cùng phục vụ một mục tiêu nghiệp vụ hoặc một quy trình không thể hiểu riêng lẻ.
- Cùng bảo vệ một nhóm bất biến và trạng thái.
- Thường được thay đổi cùng nhau vì cùng một chính sách.
- Có ranh giới giao dịch và quyền sở hữu dữ liệu tương tự.

Những thao tác nên được cân nhắc tách khi mục tiêu, chính sách, dependency hoặc nhịp thay đổi khác nhau. Ví dụ `issueInvoice` và `resendInvoice` có thể thuộc cùng một nhóm hóa đơn vì chúng chia sẻ hợp đồng với nhà cung cấp hóa đơn và chính sách chứng từ. `place` và `cancel` có thể là hai ca sử dụng riêng dù cùng thao tác trên `Order`.

Một bảng phân nhóm ban đầu có thể như sau:

| Nhóm service dự kiến | Phương thức từ service cũ | Trách nhiệm chính |
| --- | --- | --- |
| `PlaceOrderService` | `place` | Điều phối việc tạo và xác nhận đơn |
| `CancelOrderService` | `cancel` | Kiểm tra điều kiện và hủy đơn |
| `RefundOrderService` | `refund` | Điều phối quy trình hoàn tiền |
| `FulfillOrderService` | `dispatch`, có thể một phần `changeAddress` | Chuẩn bị và bàn giao đơn cho vận chuyển |
| `InvoiceService` | `issueInvoice`, `resendInvoice` | Phát hành và gửi lại hóa đơn |

Đây chỉ là giả thuyết ban đầu. Khi tìm hiểu nghiệp vụ, `changeAddress` có thể thuộc một ca sử dụng độc lập nếu có quy tắc riêng; `dispatch` có thể cần tách bước chuẩn bị và bàn giao nếu chúng có vòng đời khác nhau. Hãy để hành vi và bất biến quyết định ranh giới, không để tên class quyết định trước.

## 3. Phân biệt service điều phối với đối tượng miền

Khi tách một service lớn, không nên chuyển toàn bộ code cũ sang nhiều application service rồi để mỗi service tiếp tục chứa quy tắc nghiệp vụ phức tạp.

- **Application service** nhận yêu cầu của ca sử dụng, tải dữ liệu cần thiết, gọi domain model hoặc policy, phối hợp port và xác định ranh giới transaction.
- **Domain model** bảo vệ bất biến và quyết định chuyển trạng thái hợp lệ của đối tượng nghiệp vụ.
- **Domain service/policy** chứa quy tắc nghiệp vụ có ý nghĩa nhưng không thuộc tự nhiên về một entity cụ thể.
- **Adapter hạ tầng** thực hiện giao tiếp với JPA, HTTP client, message broker hoặc nhà cung cấp bên ngoài.

Ví dụ, `CancelOrderService` điều phối việc tải đơn và lưu lại; `Order.cancelBy(...)` quyết định đơn có thể hủy hay không. Service không nên tự sửa trường `status` ở nhiều nơi nếu mô hình miền có thể bảo vệ chuyển trạng thái đó.

```java
public class Order {
    private OrderStatus status;
    private final CustomerId customerId;

    public void cancelBy(CustomerId actor) {
        if (!customerId.equals(actor)) {
            throw new OrderAccessDeniedException();
        }
        if (status != OrderStatus.PLACED) {
            throw new OrderCannotBeCancelledException(status);
        }
        status = OrderStatus.CANCELLED;
    }
}
```

```java
@Service
public class CancelOrderService {
    private final OrderRepository orders;

    public CancelOrderService(OrderRepository orders) {
        this.orders = orders;
    }

    @Transactional
    public void handle(CancelOrderCommand command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.cancelBy(command.customerId());
        orders.save(order);
    }
}
```

Đoạn mã minh họa đã lược bỏ constructor và chi tiết mapping. Nếu thời hạn hủy, chính sách theo hạng khách hàng hoặc quy tắc hoàn tiền phức tạp hơn, có thể dùng domain policy/service riêng và gọi nó tường minh từ ca sử dụng.

## 4. Tách từng bước mà không làm thay đổi hành vi bên ngoài

Trong hệ thống đang hoạt động, các controller, job nền hoặc module khác có thể đang gọi `OrderService`. Đổi ngay tên class hoặc chữ ký public có thể làm nhiều nơi hỏng cùng lúc. Một cách chuyển đổi an toàn là giữ một façade tương thích trong thời gian di chuyển caller.

### Bước 1: bảo vệ hành vi hiện tại

Trước khi thay đổi, tạo characterization tests (kiểm thử ghi nhận hành vi) cho những luồng đang được sử dụng. Các kiểm thử này mô tả kết quả hiện tại, bao gồm cả trường hợp thành công, lỗi nghiệp vụ và tác dụng phụ quan trọng. Không cần ghi nhận mọi chi tiết triển khai; hãy bảo vệ hợp đồng mà caller đang dựa vào.

Ví dụ với hủy đơn:

- Đơn ở trạng thái được phép hủy và đúng chủ sở hữu thì chuyển sang `CANCELLED`.
- Đơn đã giao hoặc không thuộc người yêu cầu thì bị từ chối.
- Khi hủy thành công, tồn kho được giải phóng theo chính sách hiện tại.
- Không phát thông báo hủy nếu việc hủy thất bại.

Nếu hệ thống cũ có hành vi chưa rõ hoặc lỗi đang được caller phụ thuộc, cần xác định rõ đó là hợp đồng phải giữ hay lỗi cần sửa trong một thay đổi riêng. Tránh vô tình trộn refactor cấu trúc với thay đổi nghiệp vụ lớn.

### Bước 2: tạo service mới cho một hành vi có ranh giới rõ

Chọn hành vi có phạm vi nhỏ, caller dễ nhận diện và kiểm thử hiện tại đủ bao phủ. Chuyển phần điều phối của hành vi đó sang service mới. Không di chuyển những helper chỉ vì chúng đang nằm cạnh phương thức được tách; hãy xác định helper thuộc hành vi nào hoặc là thành phần dùng chung có hợp đồng ổn định.

### Bước 3: giữ façade cũ và ủy quyền

Nếu `OrderService` là API đang được nhiều caller sử dụng, giữ các phương thức cũ và ủy quyền sang service mới:

```java
@Service
@Deprecated(forRemoval = false)
public class OrderService {
    private final PlaceOrderService placeOrder;
    private final CancelOrderService cancelOrder;
    private final RefundOrderService refundOrder;

    public OrderService(
            PlaceOrderService placeOrder,
            CancelOrderService cancelOrder,
            RefundOrderService refundOrder) {
        this.placeOrder = placeOrder;
        this.cancelOrder = cancelOrder;
        this.refundOrder = refundOrder;
    }

    public OrderId place(PlaceOrderCommand command) {
        return placeOrder.handle(command);
    }

    public void cancel(CancelOrderCommand command) {
        cancelOrder.handle(command);
    }

    public void refund(RefundCommand command) {
        refundOrder.handle(command);
    }
}
```

Façade này giúp caller cũ tiếp tục hoạt động trong khi caller mới có thể phụ thuộc trực tiếp vào service theo hành vi. Mã minh họa chỉ giữ ba phương thức đại diện; khi áp dụng, cần duy trì chữ ký, kiểu trả về, ngoại lệ và các quy tắc tương thích thực tế. `@Deprecated` là tín hiệu để caller chuyển dần, không phải yêu cầu xóa ngay class.

### Bước 4: di chuyển caller theo từng đợt

Chuyển từng controller, scheduler hoặc consumer sang service mới. Sau mỗi đợt, chạy kiểm thử liên quan và quan sát log/metrics nếu có. Khi không còn caller sử dụng façade, có thể lên kế hoạch loại bỏ nó trong thay đổi riêng sau khi xác nhận không còn tích hợp ngoài nào phụ thuộc.

```text
Trước:
Controller / Job / Consumer
            |
            v
        OrderService
       /     |      \
    place  cancel  refund

Trong giai đoạn chuyển đổi:
Controller / Job / Consumer cũ -> OrderService (façade)
Controller / Job / Consumer mới -> PlaceOrderService / CancelOrderService / RefundOrderService
                                      |                |                 |
                                      +----------------+-----------------+
                                                       v
                                         Domain + Repository + Ports

Sau khi chuyển hết caller:
Controller / Job / Consumer -> các service theo hành vi
```

## 5. Giữ đúng ranh giới transaction và tác dụng phụ

Chia service có thể vô tình thay đổi cách transaction được mở hoặc kết thúc. Trước khi tách, hãy xác định transaction hiện tại bao trùm những thao tác nào, rollback xảy ra khi lỗi nào và có tác dụng phụ nào đã xảy ra trước commit.

Ví dụ, nếu `OrderService.place()` trước đây gọi repository và lưu đơn trong một transaction, service mới cần giữ ranh giới tương đương. Nếu façade có `@Transactional` còn service được gọi có `@Transactional` riêng, cần hiểu propagation và proxy Spring; không mặc định hai annotation tạo ra hai transaction độc lập hoặc tự động nâng isolation.

Không nên đặt transaction quá rộng chỉ vì tất cả hành vi cùng nằm trong một class. Ngược lại, không tách một quy trình cần tính nguyên tử thành nhiều transaction độc lập mà chưa thiết kế cách phục hồi.

Các lời gọi tới hệ thống ngoài như thanh toán, vận chuyển hoặc gửi email không nằm trong transaction cơ sở dữ liệu thông thường. Nếu một quy trình cần phối hợp nhiều hệ thống, hãy xem xét:

- Ghi trạng thái nội bộ và outbox event trong cùng transaction, rồi worker phát sự kiện sau commit.
- Dùng idempotency key để xử lý request lặp.
- Dùng saga hoặc thao tác bù trừ khi quy trình nhiều bước có thể thất bại giữa chừng.
- Giữ service theo hành vi sở hữu chính sách retry và lỗi phù hợp với use case đó.

Khi tách `cancel` và `refund`, cần làm rõ hủy đơn có tự động tạo yêu cầu hoàn tiền hay không. Nếu có, `CancelOrderService` có thể điều phối một quy trình bao gồm yêu cầu hoàn tiền hoặc phát sự kiện cho quy trình hoàn tiền; nhưng không nên lén gọi `RefundOrderService` qua một chuỗi phụ thuộc vòng. Hãy chọn một hướng điều phối rõ ràng và ghi nhận trạng thái trung gian nếu quy trình bất đồng bộ.

## 6. Xử lý logic dùng chung sau khi tách

Sau khi chia theo hành vi, có thể xuất hiện code giống nhau. Không nên lập tức gom tất cả vào `CommonOrderService` mới, vì class đó dễ trở thành service quá tải tiếp theo.

Hãy phân loại phần dùng chung:

| Loại phần dùng chung | Cách xử lý phù hợp |
| --- | --- |
| Quy tắc nghiệp vụ chung của `Order` | Đặt trong entity, value object hoặc domain policy có tên rõ |
| Truy vấn và lưu aggregate | Đặt trong repository/port và adapter dữ liệu |
| Chuyển đổi dữ liệu | Mapper tại ranh giới sở hữu hai kiểu dữ liệu |
| Tích hợp kỹ thuật với nhà cung cấp | Adapter riêng triển khai port |
| Đoạn tiện ích thuần túy, không có chính sách | Helper nhỏ, stateless nếu thực sự giảm lặp và tăng rõ ràng |
| Một quy trình được nhiều use case gọi | Tách collaborator có mục tiêu và hợp đồng rõ; cân nhắc liệu nó có phải use case riêng hay không |

Ví dụ, nhiều hành vi có thể cần tải `Order` theo ID. Repository là nơi phù hợp để cung cấp thao tác tìm kiếm; không cần tạo `LoadOrderService` chỉ bọc một lệnh `findById` nếu nó không có chính sách hoặc ranh giới độc lập. Tương tự, một hàm định dạng ngày không trở thành application service chỉ vì nhiều service sử dụng.

Nếu nhiều hành vi cùng cần một quy tắc miền, hãy giữ quy tắc ở nơi sở hữu nó để tránh sao chép. Nếu chúng chỉ tình cờ có vài dòng code giống nhau nhưng ngữ nghĩa khác, giữ riêng có thể rõ ràng hơn một abstraction tổng quát.

## 7. Kiểm thử sau khi chia service

Kiểm thử cần xác nhận hành vi vẫn đúng và ranh giới mới có ý nghĩa:

- **Characterization test:** bảo vệ các kết quả và tác dụng phụ quan trọng trước khi refactor.
- **Unit test cho domain:** xác nhận bất biến và chuyển trạng thái của `Order`, `Money` hoặc policy.
- **Unit test cho từng application service:** xác nhận service điều phối đúng collaborator, xử lý lỗi và lưu dữ liệu theo hành vi.
- **Integration test cho adapter:** xác nhận repository, transaction, payment adapter hoặc shipping adapter hoạt động đúng với công nghệ thật.
- **Contract test cho façade/caller:** xác nhận API cũ vẫn trả kết quả và lỗi tương thích trong giai đoạn di chuyển.
- **Regression test:** chạy các luồng đặt, hủy, hoàn tiền, giao hàng và hóa đơn liên quan để phát hiện ảnh hưởng chéo.

Đừng chỉ kiểm tra rằng mỗi class mới được gọi. Kiểm thử phải xác nhận kết quả nghiệp vụ: trạng thái đơn, số tiền, tồn kho, sự kiện được phát và hành vi khi một bước thất bại. Nếu thay đổi transaction hoặc tích hợp ngoài, cần có kiểm thử cho commit/rollback, retry và tác dụng phụ trùng lặp.

## 8. Những cách tách dễ gây vấn đề

### Tách theo số phương thức

Chia mỗi phương thức thành một class mà không có trách nhiệm riêng tạo ra nhiều lớp chuyển tiếp. Người đọc phải mở nhiều file để hiểu một hành vi đơn giản, còn dependency vẫn không thay đổi.

### Tách theo công nghệ thay vì hành vi

Tạo `OrderDatabaseService`, `OrderHttpService` và `OrderValidationService` có thể gom code theo công cụ, nhưng không làm rõ ai sở hữu nghiệp vụ đặt, hủy hay hoàn tiền. Công nghệ thường thuộc adapter/hạ tầng; application service nên phản ánh mục tiêu use case.

### Chia sẻ trạng thái mutable giữa các service

Không nên chuyển một service lớn thành nhiều service nhỏ nhưng cùng sửa một object trạng thái dùng chung hoặc phụ thuộc vào thứ tự gọi ngầm. Mỗi use case cần nhận đầu vào rõ ràng và tải/kiểm tra trạng thái cần thiết trong transaction phù hợp.

### Tạo phụ thuộc vòng

Nếu `CancelOrderService` gọi `RefundOrderService` và `RefundOrderService` lại gọi `CancelOrderService`, ranh giới trách nhiệm chưa rõ. Hãy xác định service nào điều phối quy trình cấp cao, hoặc đưa một policy/port chung vào vị trí hợp lý. Không giải quyết bằng cách tiêm lẫn nhau hoặc dùng service locator.

### Thay đổi nghiệp vụ cùng lúc với refactor

Nếu vừa tách class vừa thay chính sách hoàn tiền, thời hạn hủy và trạng thái giao hàng, khi kiểm thử thất bại sẽ khó xác định nguyên nhân. Ưu tiên một refactor giữ hành vi; thay đổi nghiệp vụ được thực hiện riêng với kiểm thử và review tương ứng, trừ khi sửa một lỗi cần thiết để bảo toàn hợp đồng đã xác định.

## 9. Quy trình thực hiện trong hệ thống hiện có

Một lộ trình có thể áp dụng theo từng pull request:

1. Chọn service có dấu hiệu quá tải và liệt kê tất cả caller của những hành vi liên quan bằng công cụ tìm kiếm mã nguồn.
2. Ghi lại mục tiêu, điều kiện, dữ liệu, transaction và tác dụng phụ của từng hành vi.
3. Viết characterization tests cho các luồng quan trọng và xác định rõ hành vi nào phải giữ.
4. Lập nhóm theo chính sách và lý do thay đổi; chọn một nhóm nhỏ có ranh giới rõ để tách trước.
5. Tạo application service mới, chuyển logic điều phối và đưa quy tắc về domain/policy khi phù hợp.
6. Giữ façade cũ nếu cần, ủy quyền sang service mới để caller hiện tại không bị ảnh hưởng.
7. Chuyển caller từng bước, chạy regression/integration tests và theo dõi hành vi trong môi trường phù hợp.
8. Xóa façade hoặc abstraction cũ khi không còn caller và có bằng chứng việc loại bỏ an toàn.

Sau mỗi bước, hãy xem lại đồ thị phụ thuộc: service mới có phụ thuộc vào tầng trình bày hoặc adapter cụ thể không? Hai service có tạo chu trình không? Một repository hoặc domain policy có bị đặt sai tầng không? Ranh giới mới cần làm cho hướng phụ thuộc và mục tiêu nghiệp vụ dễ đọc hơn.

## Tự kiểm tra

1. Vì sao không nên tách một `OrderService` lớn bằng cách chuyển mỗi phương thức sang một class mà chưa phân tích hành vi?
2. `cancel` và `refund` cùng liên quan đến đơn hàng và tiền. Những câu hỏi nào giúp xác định chúng là hai hành vi riêng?
3. Characterization test bảo vệ điều gì trong một refactor hệ thống hiện có?
4. Vì sao giữ façade cũ và ủy quyền sang service mới có thể giúp di chuyển caller an toàn?
5. Khi tách service, cần kiểm tra lại những khía cạnh nào của transaction và tác dụng phụ bên ngoài?
6. Nếu hai service mới gọi lẫn nhau, cần xem xét lại ranh giới hoặc hướng điều phối ra sao?

