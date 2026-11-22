# Thiết kế API theo hành động thay vì công bố setter của mô hình

Trong Domain-Driven Design (DDD), API là ranh giới để người dùng hoặc hệ thống khác yêu cầu một khả năng nghiệp vụ. Vì vậy, API nên thể hiện điều caller muốn đạt được, chẳng hạn đặt hàng, xác nhận đơn, hủy đơn, phê duyệt yêu cầu hoặc hoàn tiền. API không nên vô tình biến cấu trúc nội bộ của Domain Model thành một tập setter công khai để client tự thay đổi trạng thái.

Ví dụ, thay vì cho client gửi PATCH để đặt trực tiếp trạng thái đơn hàng thành CONFIRMED, API có thể cung cấp hành động xác nhận đơn. Application nhận yêu cầu, tải Order Aggregate, gọi hành vi confirm(), lưu thay đổi và trả kết quả. Aggregate tự kiểm tra đơn có đủ điều kiện xác nhận hay không. Client chỉ yêu cầu một hành động; nó không quyết định trạng thái nội bộ sẽ được gán bằng cách nào.

Thiết kế theo hành động không có nghĩa mọi API phải là RPC tùy ý. Có thể giữ cấu trúc resource-oriented của HTTP, dùng POST trên một resource hành động hoặc resource con khi cần biểu diễn chuyển trạng thái nghiệp vụ. Với dữ liệu thực sự có thể chỉnh sửa độc lập, PUT hoặc PATCH vẫn phù hợp. Điều cần tránh là ánh xạ máy móc mọi setter của mô hình thành một endpoint công khai.

## 1. API là hợp đồng của khả năng nghiệp vụ

Một API tốt trả lời được ba câu hỏi:

- Caller có thể yêu cầu hệ thống thực hiện điều gì?
- Điều kiện nào quyết định yêu cầu có được chấp nhận không?
- Kết quả nào được trả về sau khi hệ thống xử lý?

Những câu hỏi này gắn API với use case và ngôn ngữ nghiệp vụ. Ví dụ trong một Bounded Context bán hàng:

| Ý định của caller | Hành động API có thể biểu diễn |
|---|---|
| Tạo một đơn hàng | Đặt hàng |
| Chốt đơn nháp | Xác nhận đơn |
| Ngừng xử lý đơn chưa giao | Hủy đơn |
| Ghi nhận đơn đã bàn giao vận chuyển | Đánh dấu đã gửi |
| Hoàn lại khoản đã thu | Hoàn tiền |
| Duyệt một yêu cầu | Phê duyệt yêu cầu |

Tên hành động nên dùng thuật ngữ mà chuyên gia nghiệp vụ và đội phát triển cùng hiểu. Nếu nghiệp vụ gọi là xác nhận đơn, API nên diễn đạt confirm order thay vì update status.

### 1.1. API không phải bản sao của Domain Model

Domain Model có thể có hàng chục phương thức nội bộ để bảo vệ bất biến, tính toán hoặc phối hợp các đối tượng. Không phải phương thức nào cũng là khả năng cần công bố cho caller.

Ví dụ, Order có thể có các phương thức:

- addLine()
- removeLine()
- recalculateSubtotal()
- changeStatusInternally()
- confirm()
- cancel()

Một API công khai không nên tự động tạo endpoint cho từng phương thức. API chỉ nên công bố những hành động mà actor hoặc hệ thống tích hợp thực sự cần yêu cầu. Một số phương thức chỉ là chi tiết triển khai bên trong Aggregate.

### 1.2. Hành động thể hiện ý định, setter chỉ thể hiện thao tác

So sánh:

| API dựa trên setter | API theo ý định nghiệp vụ |
|---|---|
| PATCH /orders/123 với status=CONFIRMED | POST /orders/123/confirmations |
| PATCH /orders/123 với status=CANCELLED | POST /orders/123/cancellations |
| PATCH /loan-requests/456 với approved=true | POST /loan-requests/456/approvals |
| PATCH /shipments/789 với delivered=true | POST /shipments/789/delivery-confirmations |

Ở cột bên phải, caller yêu cầu một hành động. Hệ thống có thể từ chối nếu điều kiện không hợp lệ và có thể ghi nhận người thực hiện, thời điểm, lý do hoặc sự kiện nghiệp vụ.

## 2. Vì sao không nên công bố setter của mô hình?

Một setter thường thay đổi một thuộc tính đơn lẻ. Nhưng một chuyển trạng thái nghiệp vụ thường liên quan đến nhiều điều kiện, nhiều thuộc tính và các side effect có ý nghĩa.

Ví dụ, xác nhận đơn hàng có thể yêu cầu:

- Đơn đang ở trạng thái DRAFT.
- Đơn có ít nhất một dòng hàng hợp lệ.
- Giá và điều kiện bán đã được chốt.
- Hàng đã được giữ hoặc quy trình giữ hàng đã chấp nhận.
- Người thực hiện có quyền xác nhận.

Khi xác nhận thành công, hệ thống có thể:

- Chuyển trạng thái đơn.
- Ghi thời điểm xác nhận.
- Lưu người xác nhận.
- Ghi nhận Domain Event OrderConfirmed.
- Khởi động bước thanh toán hoặc xử lý tiếp theo.

Một request đặt status=CONFIRMED không diễn đạt đủ những điều kiện và kết quả này.

### 2.1. Setter công khai dễ phá vỡ bất biến

Giả sử Aggregate có:

~~~java
public void setStatus(OrderStatus status) {
    this.status = status;
}
~~~

Nếu API hoặc Application gọi setter này trực tiếp, bất kỳ luồng nào cũng có thể đặt Order thành CONFIRMED, SHIPPED hoặc CANCELLED mà không đi qua quy tắc tương ứng.

Thay vào đó, Aggregate cung cấp hành vi có ý nghĩa:

~~~java
public void confirm() {
    if (status != OrderStatus.DRAFT) {
        throw new OrderCannotBeConfirmed(status);
    }
    if (lines.isEmpty()) {
        throw new EmptyOrderCannotBeConfirmed();
    }

    status = OrderStatus.CONFIRMED;
    confirmedAt = clock.instant();
    raise(new OrderConfirmed(id, confirmedAt));
}
~~~

Hành vi này kiểm tra điều kiện, thay đổi trạng thái, ghi nhận thời điểm và phát sinh sự kiện miền. Các chi tiết được bảo vệ bên trong Aggregate Root.

### 2.2. Setter làm lộ cấu trúc lưu trữ

Nếu API được thiết kế theo từng field của Entity, client sẽ phụ thuộc vào tên thuộc tính và cấu trúc nội bộ. Khi Domain thay đổi từ một status đơn giản sang state machine hoặc nhiều Value Object, API có thể phải thay đổi theo.

API theo use case giữ hợp đồng ổn định hơn vì nó diễn đạt ý định nghiệp vụ. Bên trong, Domain có thể thay đổi cách thực hiện miễn là hành vi và kết quả công khai vẫn giữ đúng cam kết.

### 2.3. Setter tạo nguy cơ mass assignment

Nếu request được bind thẳng vào Entity hoặc DTO có quá nhiều field, caller có thể gửi thêm các field mà endpoint không định cho phép thay đổi, chẳng hạn:

- status
- approvedBy
- discountRate
- totalAmount
- paymentState
- internalNote

API nên dùng request DTO chỉ chứa dữ liệu caller được phép cung cấp. Các giá trị do hệ thống quyết định phải được lấy từ nguồn đáng tin cậy hoặc tính trong Domain.

## 3. Resource-oriented API vẫn có thể biểu diễn hành động

Thiết kế theo hành động không bắt buộc bỏ REST. HTTP cung cấp các method và resource để biểu diễn thao tác. Có thể chọn một trong các cách đặt route nhất quán.

### 3.1. Resource con biểu diễn kết quả hành động

Một cách thường dùng là tạo resource con đại diện cho hành động hoặc kết quả:

~~~http
POST /orders/123/confirmations
POST /orders/123/cancellations
POST /loan-requests/456/approvals
POST /shipments/789/delivery-confirmations
~~~

Ví dụ POST /orders/123/confirmations có thể tạo một bản ghi xác nhận hoặc yêu cầu xác nhận được xử lý. Cách này phù hợp khi hành động có dữ liệu riêng như lý do, người thực hiện, thời điểm hoặc kết quả cần truy vấn.

### 3.2. Action endpoint rõ ràng

Một số API chọn route thể hiện trực tiếp động từ:

~~~http
POST /orders/123/confirm
POST /orders/123/cancel
POST /loan-requests/456/approve
~~~

Cách này dễ đọc và phù hợp với API thiên về command. Nó vẫn có thể sử dụng HTTP method đúng mục đích: POST yêu cầu server thực hiện một hành động.

### 3.3. Chọn một quy ước nhất quán

Không có một mẫu URL duy nhất phù hợp với mọi tổ chức. Hãy chọn cách biểu diễn nhất quán trong API và xem xét:

- Hành động có tạo một resource kết quả riêng không?
- Có cần truy vấn lịch sử hoặc trạng thái xử lý của hành động không?
- Hành động có dữ liệu đầu vào riêng không?
- Có thể thực hiện đồng bộ trong request hay cần xử lý bất đồng bộ?
- API hiện tại đang dùng quy ước resource nào?

Tránh tạo route tùy tiện như /doConfirmOrder hoặc /changeStatusToConfirmed. Tên route cần ổn định, dễ hiểu và gắn với resource hoặc use case.

## 4. Phân biệt cập nhật thuộc tính với chuyển trạng thái nghiệp vụ

Không phải mọi PATCH đều sai. Có những thuộc tính thực sự được phép chỉnh sửa độc lập, ví dụ tên hiển thị, ghi chú giao hàng hoặc địa chỉ nhận hàng trong một giai đoạn nhất định.

Điểm phân biệt là liệu việc thay đổi field có mang ý nghĩa nghiệp vụ riêng và cần bảo vệ điều kiện hay không.

| Thay đổi | API phù hợp thường gặp |
|---|---|
| Sửa tên hiển thị của hồ sơ | PATCH /customers/123 |
| Thay đổi địa chỉ giao khi đơn còn nháp | PATCH /orders/123/delivery-address |
| Xác nhận đơn hàng | POST /orders/123/confirmations |
| Hủy đơn và cung cấp lý do | POST /orders/123/cancellations |
| Phê duyệt khoản vay | POST /loan-requests/456/approvals |
| Ghi nhận đã giao hàng | POST /shipments/789/delivery-confirmations |

### 4.1. PUT và PATCH vẫn có chỗ đứng

- PUT thường thay thế toàn bộ representation của resource theo hợp đồng API.
- PATCH thường áp dụng một phần thay đổi lên resource.
- POST thường tạo resource hoặc yêu cầu thực hiện một hành động.

Các method có semantics HTTP riêng. Không nên dùng PUT/PATCH như một đường tắt để bỏ qua quy tắc miền. Nếu một thay đổi có thể làm chuyển state machine, nên cân nhắc một use case có tên.

### 4.2. Field update cũng cần hành vi miền

Ngay cả khi API cho phép PATCH một field, Application không nên gọi setter tùy tiện nếu thay đổi đó chịu điều kiện nghiệp vụ.

Ví dụ:

~~~java
public void changeDeliveryAddress(Address newAddress) {
    if (status != OrderStatus.DRAFT) {
        throw new AddressCannotBeChangedAfterConfirmation();
    }
    deliveryAddress = Objects.requireNonNull(newAddress);
}
~~~

API PATCH /orders/123/delivery-address có thể gọi use case ChangeOrderDeliveryAddress. Application tải Order, chuyển DTO thành Address Value Object, gọi changeDeliveryAddress() và lưu Aggregate. Quy tắc vẫn nằm trong Domain.

## 5. Mô hình hóa state transition trong Aggregate

Một Aggregate thường có vòng đời hoặc state machine. Không phải mọi trạng thái đều có thể chuyển sang mọi trạng thái khác.

Ví dụ:

~~~mermaid
flowchart TD
    DRAFT -->|confirm| CONFIRMED
    DRAFT -->|cancel| CANCELLED
    CONFIRMED -->|cancel, if allowed| CANCELLED
    CONFIRMED -->|ship| SHIPPED
    SHIPPED -->|deliver| DELIVERED
~~~

Aggregate Root là nơi bảo vệ các chuyển trạng thái hợp lệ:

~~~java
public void ship(ShipmentId shipmentId) {
    if (status != OrderStatus.CONFIRMED) {
        throw new OrderCannotBeShipped(status);
    }
    this.shipmentId = Objects.requireNonNull(shipmentId);
    this.status = OrderStatus.SHIPPED;
    raise(new OrderShipped(id, shipmentId));
}
~~~

Không nên để client gửi PATCH status=SHIPPED. Client yêu cầu đánh dấu gửi hàng hoặc xác nhận bàn giao; hệ thống kiểm tra điều kiện và thực hiện hành vi.

### 5.1. Chuyển trạng thái có thể cần nhiều dữ liệu

Một hành động như cancel có thể cần:

- Lý do hủy.
- Actor thực hiện.
- Nguồn yêu cầu.
- Thời điểm yêu cầu.
- Mã tham chiếu từ hệ thống ngoài.

Các dữ liệu này thuộc request DTO hoặc command, sau đó được chuyển thành kiểu miền phù hợp. Không nên dùng một field status để thay thế toàn bộ ý nghĩa của hành động.

## 6. Luồng từ HTTP API đến Aggregate

Một luồng phổ biến trong DDD:

1. Controller nhận request và xác thực cấu trúc dữ liệu.
2. Controller chuyển request thành command có ý nghĩa use case.
3. Application kiểm tra quyền ở mức use case và tải Aggregate.
4. Application gọi hành vi miền.
5. Aggregate kiểm tra bất biến, đổi trạng thái và ghi nhận Domain Event.
6. Application lưu Aggregate trong transaction phù hợp.
7. Application trả kết quả; adapter chuyển thành HTTP response.

~~~mermaid
sequenceDiagram
    actor Client
    participant API as API Controller
    participant App as Application Service
    participant Repo as Repository
    participant Order as Order Aggregate
    Client->>API: POST /orders/123/confirmations
    API->>API: Validate request shape
    API->>App: ConfirmOrderCommand
    App->>Repo: findById(orderId)
    Repo-->>App: Order
    App->>Order: confirm(actor, time)
    Order->>Order: Check invariants
    Order->>Order: Change state and record event
    App->>Repo: save(order)
    App-->>API: ConfirmOrderResult
    API-->>Client: 200 / 201 response
~~~

Controller không cần biết Order thay đổi những field nào. Application không tự đặt status. Aggregate không biết HTTP, URL hoặc JSON.

## 7. Ví dụ: API xác nhận đơn hàng

Giả sử một đơn chỉ được xác nhận khi:

- Đang ở trạng thái DRAFT.
- Có ít nhất một dòng hàng.
- Địa chỉ giao hàng hợp lệ.

### 7.1. Request DTO

Nếu hành động xác nhận không cần dữ liệu bổ sung, request body có thể rỗng. Nếu cần ghi chú hoặc thông tin xác nhận, dùng DTO riêng:

~~~java
public record ConfirmOrderRequest(
        String confirmationNote
) {}
~~~

Không nhận status mới từ client. Trạng thái tiếp theo do Aggregate quyết định.

### 7.2. Command

~~~java
public record ConfirmOrderCommand(
        OrderId orderId,
        String confirmationNote
) {}
~~~

Actor ID được lấy từ security context đã xác thực ở Application, không nhận một actorId tùy ý trong body. Command phản ánh yêu cầu của use case và chỉ chứa dữ liệu cần thiết để xử lý yêu cầu.

### 7.3. Aggregate

~~~java
public final class Order extends AggregateRoot {
    private final OrderId id;
    private final List<OrderLine> lines;
    private final Address deliveryAddress;
    private OrderStatus status;
    private Instant confirmedAt;
    private UserId confirmedBy;
    private String confirmationNote;

    public void confirm(UserId actorId, Instant now, String note) {
        if (status != OrderStatus.DRAFT) {
            throw new OrderCannotBeConfirmed(status);
        }
        if (lines.isEmpty()) {
            throw new EmptyOrderCannotBeConfirmed();
        }
        if (!deliveryAddress.isDeliverable()) {
            throw new InvalidDeliveryAddress();
        }

        status = OrderStatus.CONFIRMED;
        confirmedAt = Objects.requireNonNull(now);
        confirmedBy = Objects.requireNonNull(actorId);
        confirmationNote = note;
        raise(new OrderConfirmed(id, confirmedAt, actorId));
    }
}
~~~

Ví dụ minh họa các kiểu miền và lớp AggregateRoot được giả định đã có. Trong ứng dụng thực tế, quy tắc địa chỉ có thể được bảo vệ bởi Address Value Object hoặc một chính sách miền phù hợp. Aggregate ghi nhận sự kiện sau khi hành vi thành công.

### 7.4. Application Service

~~~java
public final class ConfirmOrderService {
    private final OrderRepository orders;
    private final CurrentUser currentUser;
    private final Clock clock;

    public ConfirmOrderService(
            OrderRepository orders,
            CurrentUser currentUser,
            Clock clock
    ) {
        this.orders = orders;
        this.currentUser = currentUser;
        this.clock = clock;
    }

    public ConfirmOrderResult handle(ConfirmOrderCommand command) {
        Order order = orders.findById(command.orderId())
                .orElseThrow(() -> new OrderNotFound(command.orderId()));

        order.confirm(
                currentUser.id(),
                clock.instant(),
                command.confirmationNote()
        );
        orders.save(order);

        return new ConfirmOrderResult(
                order.id(),
                order.status(),
                order.confirmedAt()
        );
    }
}
~~~

Ví dụ cho thấy Application tải Aggregate, cung cấp actor và thời điểm, gọi hành vi và lưu kết quả. Nếu command chứa actorId, use case cần bảo đảm giá trị đó được tạo từ danh tính đã xác thực chứ không phải dữ liệu do caller tự khai.

### 7.5. Controller

~~~java
@RestController
@RequestMapping("/orders")
public final class OrderController {
    private final ConfirmOrderService confirmOrder;

    @PostMapping("/{orderId}/confirmations")
    public ResponseEntity<ConfirmOrderResponse> confirm(
            @PathVariable String orderId,
            @Valid @RequestBody ConfirmOrderRequest request
    ) {
        ConfirmOrderResult result = confirmOrder.handle(
                new ConfirmOrderCommand(
                        new OrderId(orderId),
                        request.confirmationNote()
                )
        );

        return ResponseEntity.ok(
                new ConfirmOrderResponse(
                        result.orderId().value(),
                        result.status().name(),
                        result.confirmedAt()
                )
        );
    }
}
~~~

Đây là ví dụ rút gọn về cấu trúc, không phải một controller hoàn chỉnh để sao chép nguyên trạng. ConfirmOrderService lấy actor từ CurrentUser, một adapter cung cấp danh tính đã xác thực. Controller chỉ xử lý giao thức và mapping.

## 8. Thiết kế API hủy đơn có lý do

Hủy đơn là ví dụ rõ về lý do API nên thể hiện hành động. Một request có thể gồm:

~~~java
public record CancelOrderRequest(
        @NotBlank
        @Size(max = 500)
        String reason
) {}
~~~

Route:

~~~http
POST /orders/123/cancellations
Content-Type: application/json

{
  "reason": "Customer requested cancellation"
}
~~~

Application chuyển request thành CancelOrderCommand, lấy actor đã xác thực, tải Order và gọi:

~~~java
order.cancel(
        new CancellationReason(command.reason()),
        actor.id(),
        clock.instant()
);
~~~

Aggregate quyết định đơn có thể hủy ở trạng thái hiện tại không. Nếu đã giao hàng, hành động có thể bị từ chối hoặc phải chuyển sang quy trình trả hàng. API không nên cho client đặt trực tiếp status=CANCELLED.

## 9. API action không có nghĩa là đưa mọi thao tác thành endpoint

Không nên biến mọi phương thức trong Domain thành endpoint. Chỉ công bố hành động khi nó đại diện cho một mục tiêu hoặc khả năng mà actor cần sử dụng.

Ví dụ không nên:

~~~http
POST /orders/123/set-status
POST /orders/123/recalculate-total
POST /orders/123/set-confirmed-at
POST /orders/123/set-customer-id
~~~

Những route này vẫn lộ cấu trúc nội bộ dưới hình thức động từ. Chúng không thể hiện mục tiêu nghiệp vụ rõ ràng.

Nên cân nhắc:

~~~http
POST /orders/123/confirmations
POST /orders/123/cancellations
POST /orders/123/refunds
~~~

Các hành động như tính lại tổng tiền có thể là chi tiết nội bộ được thực hiện khi thêm hoặc sửa dòng hàng. Không cần công bố nếu caller không có lý do nghiệp vụ để yêu cầu riêng.

## 10. Authorization theo hành động

Khi API công bố hành động, quyền truy cập có thể gắn với ý nghĩa cụ thể:

| Hành động | Quyền có thể cần |
|---|---|
| Xem đơn | order:read |
| Sửa địa chỉ khi còn nháp | order:edit |
| Xác nhận đơn | order:confirm |
| Hủy đơn | order:cancel |
| Hoàn tiền | payment:refund |
| Phê duyệt yêu cầu | request:approve |

Không nên chỉ kiểm tra caller có quyền PATCH resource hay không. Một người có quyền sửa ghi chú có thể không có quyền phê duyệt hoặc hoàn tiền.

Application hoặc authorization policy kiểm tra actor có quyền thực hiện use case. Aggregate tiếp tục bảo vệ bất biến miền. Hai lớp kiểm tra này không thay thế nhau:

- Authorization trả lời actor có được phép yêu cầu hành động không.
- Domain trả lời hành động có hợp lệ trong trạng thái và điều kiện nghiệp vụ hiện tại không.

## 11. Validation đầu vào và quy tắc miền

API cần phân biệt:

### Structural validation

Kiểm tra request có đúng hình dạng:

- Trường bắt buộc có mặt.
- Lý do không rỗng.
- Chuỗi không vượt giới hạn.
- Mã định danh đúng định dạng.
- Kiểu dữ liệu có thể parse.

### Semantic validation

Kiểm tra ý nghĩa nghiệp vụ:

- Đơn có thể xác nhận không?
- Đơn đã giao có thể hủy không?
- Yêu cầu đã được phê duyệt trước đó chưa?
- Tài khoản có đủ số dư để chuyển tiền không?
- Người dùng có thể đổi địa chỉ ở giai đoạn hiện tại không?

Structural validation thường ở adapter/request boundary. Semantic validation thuộc Aggregate, Value Object, Domain Service hoặc Policy phù hợp. Không nên chỉ kiểm tra ở Controller vì use case có thể được gọi từ message consumer hoặc adapter khác.

## 12. Mã phản hồi HTTP cho hành động

Mã HTTP nên phản ánh kết quả giao tiếp và trạng thái xử lý:

| Tình huống | Mã có thể dùng | Ghi chú |
|---|---:|---|
| Hành động hoàn tất đồng bộ | 200 OK | Có thể trả response mô tả trạng thái mới. |
| Tạo resource kết quả | 201 Created | Ví dụ tạo cancellation record. |
| Đã nhận yêu cầu xử lý bất đồng bộ | 202 Accepted | Trả operation ID hoặc URL theo dõi. |
| Request sai cấu trúc | 400 Bad Request | Validation tại ranh giới. |
| Không tìm thấy Aggregate | 404 Not Found | Theo hợp đồng API. |
| Xung đột với trạng thái hiện tại | 409 Conflict | Ví dụ đơn đã giao nên không thể hủy. |
| Không được phép | 403 Forbidden | Actor không có quyền. |
| Thiếu hoặc sai xác thực | 401 Unauthorized | Theo cơ chế authentication. |
| Không thỏa điều kiện nghiệp vụ | 422 Unprocessable Content | Có thể dùng nếu quy ước API phân biệt với conflict. |

Không có một mapping duy nhất cho mọi ứng dụng. Điều quan trọng là chọn quy ước nhất quán và trả mã lỗi ổn định để client có thể xử lý.

### 12.1. Không trả thành công chỉ vì request đã đến server

Nếu hành động được xử lý bất đồng bộ, 202 Accepted có nghĩa server đã nhận yêu cầu để xử lý, không có nghĩa nghiệp vụ đã hoàn tất. Response nên có operation ID hoặc resource để client theo dõi trạng thái.

## 13. Idempotency cho action endpoint

POST thường không được xem là idempotent theo HTTP semantics. Nhưng một số hành động nghiệp vụ cần chịu được client retry do timeout hoặc mất kết nối.

Ví dụ client gửi yêu cầu hoàn tiền, server thực hiện thành công nhưng response bị mất. Client gửi lại; nếu hệ thống thực hiện refund lần nữa thì có thể gây thiệt hại.

Một cách là nhận Idempotency-Key:

~~~http
POST /payments/456/refunds
Idempotency-Key: refund-request-789
Content-Type: application/json

{
  "amount": "250000",
  "currency": "VND",
  "reason": "Order cancelled"
}
~~~

Application lưu key và kết quả trong transaction hoặc cơ chế phù hợp. Khi cùng key được gửi lại, hệ thống trả lại kết quả đã ghi nhận thay vì thực hiện side effect lần nữa.

Idempotency key cần được ràng buộc với actor, operation và nội dung request phù hợp. Nếu cùng key nhưng payload khác, API nên từ chối thay vì âm thầm trả kết quả cũ.

Không nên giả định mọi action endpoint đều tự động idempotent. Hãy xác định theo rủi ro của nghiệp vụ.

## 14. Concurrency và cập nhật trạng thái

Hai caller có thể cùng yêu cầu một hành động trên cùng Aggregate:

~~~text
Request A: confirm order-123
Request B: cancel order-123
~~~

Nếu cả hai cùng tải version cũ, hệ thống cần cơ chế bảo vệ cập nhật đồng thời. Có thể dùng:

- Optimistic locking với version của Aggregate.
- Conditional update tại persistence.
- Pessimistic locking khi yêu cầu phù hợp.
- State transition check trong Aggregate.

Ví dụ optimistic locking:

~~~http
POST /orders/123/confirmations
If-Match: "order-v7"
~~~

Nếu phiên bản hiện tại không còn là v7, server có thể trả 412 Precondition Failed hoặc một lỗi xung đột theo hợp đồng. Dù có If-Match, Aggregate vẫn phải kiểm tra trạng thái hợp lệ vì version check không thay thế quy tắc miền.

## 15. Hành động bất đồng bộ và trạng thái trung gian

Một số hành động không thể hoàn thành ngay trong HTTP request:

- Phê duyệt cần nhiều bước.
- Thanh toán chờ nhà cung cấp phản hồi.
- Gửi hàng chờ hãng vận chuyển xác nhận.
- Quy trình cần phối hợp nhiều Bounded Context.

API có thể trả 202 Accepted và một operation resource:

~~~http
POST /orders/123/confirmations

HTTP/1.1 202 Accepted
Location: /operations/op-789
~~~

Client truy vấn:

~~~http
GET /operations/op-789
~~~

Response có thể cho biết:

~~~json
{
  "operationId": "op-789",
  "status": "PENDING",
  "submittedAt": "2026-11-18T10:15:00Z"
}
~~~

Application hoặc Process Manager điều phối workflow và cập nhật trạng thái operation. Không nên trả CONFIRMED ngay khi mới nhận yêu cầu nếu các bước nghiệp vụ chưa hoàn tất.

## 16. API action và Domain Event

Action endpoint nhận một ý định; Domain Event ghi nhận một sự việc đã xảy ra.

Ví dụ:

~~~text
POST /orders/123/cancellations
        |
        v
CancelOrderCommand
        |
        v
Order.cancel()
        |
        v
OrderCancelled Domain Event
~~~

Command có thể bị từ chối. Domain Event chỉ được ghi nhận sau khi hành vi thành công. Application lưu Aggregate và sự kiện theo chiến lược transaction; Integration Event có thể được công bố sau commit hoặc qua Transactional Outbox.

Không nên phát OrderCancelled ngay khi Controller nhận request. Request chưa chứng minh rằng đơn đã được hủy.

## 17. Không để API trở thành một lớp CRUD tổng quát

CRUD là cách hữu ích để quản lý dữ liệu đơn giản, nhưng không phải mọi Aggregate đều phù hợp với CRUD tự do.

Một bảng so sánh:

| Kiểu CRUD trực tiếp | Use case có ý nghĩa |
|---|---|
| Update status | Confirm, Cancel, Reject, Ship |
| Update approved flag | Approve hoặc Reject request |
| Update payment state | Capture, Refund, Void payment |
| Update inventory quantity | Receive stock, Reserve, Release reservation |
| Delete subscription | Cancel subscription hoặc End subscription |

Các hành động bên phải có thể ghi nhận lý do, actor, thời điểm, sự kiện và lịch sử. Chúng thể hiện quy trình nghiệp vụ tốt hơn một phép cập nhật field.

### 17.1. Không phải CRUD nào cũng sai

CRUD vẫn phù hợp với dữ liệu tham chiếu hoặc cấu hình có vòng đời đơn giản, ví dụ:

- Sửa tên nhãn hiển thị.
- Cập nhật mô tả một danh mục.
- Thay đổi một tùy chọn giao diện.

Nhưng khi thao tác có điều kiện, chuyển trạng thái, side effect hoặc ý nghĩa kiểm toán, hãy mô hình hóa thành hành động rõ ràng.

## 18. DTO của action nên chứa dữ liệu cần thiết

Mỗi hành động có thể có request DTO riêng:

| Hành động | Request DTO có thể gồm |
|---|---|
| ConfirmOrder | Ghi chú xác nhận nếu cần |
| CancelOrder | Lý do hủy |
| ApproveLoan | Hạn mức, ghi chú phê duyệt theo quyền |
| RefundPayment | Số tiền, lý do, tham chiếu giao dịch |
| ShipOrder | Mã vận đơn, đơn vị vận chuyển |

Không nên tạo một DTO tổng quát có mọi trường optional như:

~~~java
public record UpdateOrderRequest(
        String status,
        String cancellationReason,
        String shipmentId,
        String paymentState,
        String approvedBy,
        BigDecimal discount
) {}
~~~

DTO này cho phép nhiều tổ hợp field không hợp lệ và khiến API khó xác định caller đang yêu cầu hành động gì. Tách request theo use case giúp validation, authorization và audit rõ hơn.

## 19. Audit và lịch sử hành động

Action endpoint thường tạo cơ hội ghi nhận lịch sử nghiệp vụ:

- Ai thực hiện?
- Hành động gì?
- Khi nào?
- Vì lý do gì?
- Trạng thái trước và sau là gì?
- Yêu cầu đến từ kênh nào?
- Có correlation ID nào để truy vết không?

Không nên tin actor ID do client gửi. Actor phải đến từ security context đã xác thực. Lý do và metadata cần được xác thực theo chính sách và tránh lưu dữ liệu nhạy cảm không cần thiết.

Audit record có thể được ghi cùng transaction với thay đổi nghiệp vụ nếu cần tính nguyên tử. Domain Event có thể cung cấp thông tin cho lịch sử hoặc downstream, nhưng audit compliance có thể cần cơ chế lưu trữ riêng với retention và quyền truy cập cụ thể.

## 20. Thiết kế API cho nhiều loại actor

Cùng một hành động có thể được gọi bởi người dùng, nhân viên nội bộ hoặc hệ thống tích hợp. Không nhất thiết tạo nhiều endpoint nếu use case giống nhau và authorization có thể phân biệt actor.

Ví dụ:

- Khách hàng yêu cầu hủy đơn.
- Nhân viên hỗ trợ hủy đơn theo yêu cầu khách.
- Hệ thống chống gian lận yêu cầu khóa đơn.

Các actor có thể có quyền và lý do khác nhau. Application xác định danh tính và quyền; Domain bảo vệ bất biến và chính sách nghiệp vụ. Nếu quy trình thực sự khác nhau, có thể tách use case hoặc command riêng thay vì thêm nhiều flag khó hiểu vào một request.

## 21. Tổ chức controller và application service

Controller nên mỏng:

~~~java
@PostMapping("/{orderId}/cancellations")
public ResponseEntity<CancelOrderResponse> cancel(
        @PathVariable String orderId,
        @Valid @RequestBody CancelOrderRequest request
) {
    CancelOrderResult result = cancelOrder.handle(
            new CancelOrderCommand(
                    new OrderId(orderId),
                    new CancellationReason(request.reason())
            )
    );
    return ResponseEntity.ok(cancelMapper.toResponse(result));
}
~~~

Application Service thể hiện trình tự:

~~~java
public CancelOrderResult handle(CancelOrderCommand command) {
    Order order = orders.findById(command.orderId())
            .orElseThrow(() -> new OrderNotFound(command.orderId()));

    order.cancel(command.reason(), currentUser.id(), clock.instant());
    orders.save(order);

    return CancelOrderResult.from(order);
}
~~~

Aggregate sở hữu quy tắc:

~~~java
public void cancel(
        CancellationReason reason,
        UserId actorId,
        Instant occurredAt
) {
    if (status != OrderStatus.DRAFT && status != OrderStatus.CONFIRMED) {
        throw new OrderCannotBeCancelled(status);
    }
    status = OrderStatus.CANCELLED;
    cancellationReason = reason;
    cancelledBy = actorId;
    cancelledAt = occurredAt;
    raise(new OrderCancelled(id, reason, actorId, occurredAt));
}
~~~

Các đoạn code là minh họa, các kiểu và dependency được giả định đã tồn tại. Controller xử lý HTTP, Application điều phối, Aggregate bảo vệ quy tắc. Mỗi lớp có một lý do thay đổi rõ ràng.

## 22. Kiểm thử API theo hành động

Kiểm thử nên xác nhận hợp đồng và hành vi:

### API contract test

- Route và HTTP method đúng.
- Request DTO chỉ nhận trường được công bố.
- Response có schema ổn định.
- Mã lỗi và cấu trúc lỗi nhất quán.

### Application test

- Command được chuyển đến đúng use case.
- Aggregate được tải theo ID.
- Hành vi được gọi và kết quả được lưu.
- Hệ thống ngoài chỉ được gọi khi workflow yêu cầu.

### Domain test

- Hành động hợp lệ chuyển trạng thái đúng.
- Hành động không hợp lệ bị từ chối.
- Trạng thái không bị thay đổi khi hành động thất bại.
- Domain Event chỉ được ghi nhận khi hành động thành công.

### Authorization test

- Actor có quyền được phép thực hiện.
- Actor thiếu quyền bị từ chối.
- Quyền sửa field không tự động cho phép thực hiện hành động nhạy cảm.

Ví dụ bảng test:

| Trạng thái hiện tại | Hành động | Kết quả mong đợi |
|---|---|---|
| DRAFT | Confirm | CONFIRMED |
| CONFIRMED | Confirm lần nữa | Trả kết quả idempotent hoặc conflict theo policy |
| SHIPPED | Cancel | Bị từ chối hoặc chuyển sang quy trình return |
| DRAFT | Cancel | CANCELLED |
| DELIVERED | Ship | Bị từ chối |

## 23. Những sai lầm thường gặp

### Công bố status setter qua PATCH

Client có thể tạo ra trạng thái không hợp lệ và bỏ qua quy tắc của Aggregate. Hãy công bố hành động nghiệp vụ.

### Tạo endpoint cho mọi phương thức Domain

Không phải phương thức nội bộ nào cũng là khả năng của API. Chỉ công bố use case mà actor thực sự cần.

### Dùng action route nhưng vẫn bỏ qua Domain

Route /confirm không có ích nếu Application chỉ gọi setStatus(CONFIRMED). Hành vi Aggregate vẫn phải bảo vệ bất biến.

### Dồn mọi thay đổi vào một UpdateRequest

DTO quá rộng với nhiều field optional làm mờ ý định và tăng nguy cơ mass assignment. Dùng request riêng cho các hành động khác nhau.

### Nhầm authorization với business rule

Actor có quyền confirm không có nghĩa mọi Order đều có thể confirm. Cả quyền truy cập và điều kiện miền đều phải được kiểm tra.

### Cho rằng POST luôn an toàn khi retry

POST có thể tạo side effect lặp. Hãy dùng idempotency key hoặc business invariant phù hợp.

### Dùng action endpoint cho mọi field đơn giản

Một thuộc tính thực sự có thể chỉnh sửa độc lập vẫn có thể dùng PATCH. Không cần tạo command endpoint cho mọi lần sửa mô tả.

### Để controller chứa state transition

Controller không nên tự đọc status, quyết định trạng thái tiếp theo và gán field. Nó chỉ chuyển yêu cầu tới use case.

### Không xác định kết quả bất đồng bộ

Nếu hành động cần nhiều context hoặc thời gian dài, không trả kết quả hoàn tất khi mới tiếp nhận. Dùng 202 và operation resource khi phù hợp.

## 24. Quy trình thiết kế API theo hành động

Khi thiết kế một endpoint thay đổi dữ liệu, hãy đi theo các bước:

1. **Xác định ý định của actor:** họ muốn hoàn thành mục tiêu nghiệp vụ nào?
2. **Xác định resource và Aggregate sở hữu:** đối tượng nào có trách nhiệm bảo vệ trạng thái?
3. **Xác định chuyển trạng thái hợp lệ:** điều kiện trước, sau và các bất biến liên quan.
4. **Thiết kế route và HTTP method:** resource con hoặc action endpoint theo quy ước nhất quán.
5. **Thiết kế Request DTO:** chỉ nhận dữ liệu caller được phép cung cấp.
6. **Thiết kế Command:** chuyển request thành use case có ý nghĩa.
7. **Thiết kế Application Service:** tải Aggregate, kiểm tra quyền, gọi hành vi và lưu.
8. **Thiết kế Domain behavior:** Aggregate kiểm tra điều kiện và ghi nhận event nếu cần.
9. **Xác định lỗi, idempotency và concurrency:** xử lý retry, conflict và cập nhật đồng thời.
10. **Thiết kế Response:** trả trạng thái/kết quả thực tế, hoặc operation resource nếu bất đồng bộ.
11. **Kiểm thử contract, application, domain và authorization.**

~~~mermaid
flowchart TD
    A[Actor muốn đạt mục tiêu] --> B[Xác định use case và resource]
    B --> C[Xác định Aggregate sở hữu]
    C --> D[Xác định điều kiện và state transition]
    D --> E[Thiết kế action route và Request DTO]
    E --> F[Map thành Command]
    F --> G[Application điều phối]
    G --> H[Aggregate thực hiện hành vi]
    H --> I{Hợp lệ?}
    I -->|Không| J[Trả lỗi nghiệp vụ]
    I -->|Có| K[Lưu Aggregate và Domain Event]
    K --> L[Trả kết quả hoặc operation status]
~~~

## 25. Checklist thiết kế

- [ ] API diễn đạt mục tiêu nghiệp vụ mà caller muốn đạt được.
- [ ] Không công bố setter hoặc field trạng thái nội bộ như một cách điều khiển Aggregate.
- [ ] Resource và route có tên rõ, nhất quán.
- [ ] PUT/PATCH chỉ dùng cho dữ liệu thực sự được phép cập nhật theo hợp đồng.
- [ ] Chuyển trạng thái nghiệp vụ được biểu diễn bằng use case/action phù hợp.
- [ ] Request DTO chỉ chứa dữ liệu caller được phép gửi.
- [ ] Actor và quyền được lấy từ nguồn xác thực, không tin dữ liệu tự khai.
- [ ] Application tải Aggregate và điều phối use case.
- [ ] Aggregate bảo vệ bất biến và chuyển trạng thái.
- [ ] Domain Event chỉ được ghi nhận sau hành vi thành công.
- [ ] Retry và duplicate được xử lý theo yêu cầu idempotency.
- [ ] Cập nhật đồng thời có cơ chế version/concurrency phù hợp.
- [ ] Lỗi nghiệp vụ và lỗi giao thức được ánh xạ nhất quán.
- [ ] Hành động bất đồng bộ trả trạng thái pending và cách theo dõi phù hợp.
- [ ] Có kiểm thử API contract, Application, Domain và authorization.

## 26. Kết luận

Thiết kế API theo hành động giúp hợp đồng giao tiếp phản ánh ý định nghiệp vụ thay vì phơi bày các setter của mô hình. Caller yêu cầu xác nhận, hủy, phê duyệt, giao hàng hoặc hoàn tiền; Application điều phối use case; Aggregate kiểm tra bất biến, thực hiện chuyển trạng thái và ghi nhận sự kiện. API có thể dùng resource con hoặc action route, trong khi PUT/PATCH vẫn phù hợp với các thuộc tính thực sự được phép chỉnh sửa độc lập.

Không cần biến mọi phương thức Domain thành endpoint, cũng không nên gom mọi thay đổi vào một request DTO tổng quát. Hãy bắt đầu từ mục tiêu của actor, xác định Aggregate sở hữu quy tắc, rồi thiết kế route, command, response và cơ chế bảo vệ phù hợp. Cách này giữ API ổn định theo ngôn ngữ nghiệp vụ, hạn chế mass assignment và cho phép mô hình miền tiến hóa mà không làm lộ cấu trúc nội bộ.
