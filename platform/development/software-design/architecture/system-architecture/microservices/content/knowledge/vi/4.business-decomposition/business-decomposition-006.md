# Nhận diện aggregate và những bất biến cần bảo vệ cục bộ

Trong microservices, phân rã theo nghiệp vụ chỉ thực sự có ích khi mỗi service biết **dữ liệu nào mình sở hữu, quy tắc nào phải đúng ngay lập tức và thao tác nào được phép thực hiện trong một giao dịch cục bộ**. Aggregate trong Domain-Driven Design (DDD) là công cụ xác định ranh giới đó ở mức mô hình miền.

Bài này tập trung vào việc nhận diện aggregate, phân biệt bất biến cục bộ với quy tắc liên quan nhiều aggregate hoặc service, và chuyển quyết định thiết kế thành lệnh, mã nguồn, giao dịch, kiểm thử. Ví dụ xuyên suốt là hệ thống đặt hàng; cùng phương pháp có thể áp dụng cho ví điện tử, đặt chỗ, kho vận hoặc quản lý thuê bao.

## 1. Khái niệm cần phân biệt

**Entity** là đối tượng miền có danh tính bền vững theo thời gian, chẳng hạn Order, OrderLine, Subscription. Hai entity có thể mang cùng dữ liệu nhưng vẫn là hai thực thể khác nhau.

**Value Object** không có danh tính độc lập; được nhận diện bởi giá trị và thường là bất biến sau khi tạo. Ví dụ: Money, Address, DateRange. Kiểm tra tính hợp lệ khi khởi tạo value object giúp giảm số trạng thái lỗi mà aggregate phải xử lý.

**Aggregate** là một cụm entity và value object được đối xử như **một đơn vị bảo toàn tính nhất quán**. Mọi thay đổi được phép phải đi qua **aggregate root**, và các bất biến thuộc aggregate phải đúng khi giao dịch lưu trạng thái hoàn tất.

**Aggregate root** là entity đứng tại ranh giới công khai của aggregate. Thành phần bên ngoài chỉ tham chiếu root bằng ID, gọi hành vi của root và không tự ý sửa entity con bằng cách đi vòng qua root.

**Bounded context** là ranh giới ngôn ngữ và mô hình nghiệp vụ. Một bounded context có thể chứa nhiều aggregate. Bounded context, aggregate và microservice là ba loại ranh giới khác nhau: một service có thể sở hữu nhiều aggregate; một aggregate thường do một service làm nguồn dữ liệu có thẩm quyền.

**Bất biến (invariant)** là mệnh đề nghiệp vụ phải luôn đúng đối với trạng thái đã cam kết của aggregate. Ví dụ: “Đơn hàng đã xác nhận không thể thêm dòng hàng” hoặc “Số lượng của một dòng hàng phải lớn hơn 0”. Bất biến khác với mong muốn tiến trình như “Thanh toán cuối cùng sẽ được đối soát”, vốn có thể cần nhiều bước bất đồng bộ.

Hình dung ba vòng ranh giới:

~~~text
Microservice / Bounded context: Ordering
|
+-- Aggregate Order #A101
|   +-- Order root
|   +-- OrderLine #1
|   +-- OrderLine #2
|   +-- ShippingAddress snapshot
|
+-- Aggregate Order #A102
|   +-- Order root
|   +-- OrderLine #1
|
+-- Aggregate CustomerCart #C80
    +-- Cart root
    +-- CartItem ...

Service Payments và Inventory nằm ở những ranh giới sở hữu khác.
~~~

Một aggregate không đồng nghĩa với một bảng, một cây object lồng nhau, một endpoint REST hoặc toàn bộ database của service. Ranh giới của nó xuất phát từ **quy tắc nhất quán và hành vi nghiệp vụ**.

## 2. Thế nào là bất biến phải bảo vệ cục bộ?

Bất biến cục bộ là quy tắc mà root có đủ dữ liệu và quyền kiểm soát để xác minh, đồng thời có thể duy trì bằng một giao dịch trong cùng phạm vi lưu trữ.

Ví dụ đối với Order:

- Mỗi OrderLine có quantity lớn hơn 0.
- Trong một Order, mỗi SKU chỉ xuất hiện một lần; thêm cùng SKU phải cộng dồn hoặc bị từ chối theo chính sách miền.
- Không được xác nhận Order rỗng.
- Chỉ Order ở trạng thái DRAFT mới được sửa mặt hàng.
- Tổng giá trị Order bằng tổng các dòng hàng và không âm; giá chốt ở thời điểm đặt hàng được lưu dưới dạng snapshot.
- Không thể hủy Order đã chuyển sang trạng thái mà nghiệp vụ quy định là không thể hủy.

Những mệnh đề này có thể được kiểm tra bằng trạng thái của **một Order** khi thực thi lệnh tương ứng. Một số quy tắc có thể được hiện thực thành value object hoặc ràng buộc cơ sở dữ liệu để tăng chiều sâu bảo vệ.

Ngược lại, “Tồn kho phải đủ và thanh toán phải thành công trước khi giao hàng” liên quan Inventory, Payments và Fulfillment. Order không sở hữu trạng thái cập nhật tức thời của cả ba. Đừng biến tất cả thành một aggregate khổng lồ hoặc giả định có thể khóa nhiều database như một giao dịch local. Cần mô hình tiến trình, trạng thái trung gian, sự kiện, cơ chế xử lý lỗi và bù trừ phù hợp.

Câu hỏi quyết định: **Nếu hai yêu cầu đồng thời sửa hai phần dữ liệu, nghiệp vụ có đòi hỏi chúng được kiểm tra và cam kết nguyên tử cùng nhau hay không?** Nếu có, hãy xem đó là ứng viên thuộc cùng aggregate và xác minh ranh giới sở hữu. Nếu không, ưu tiên tách aggregate và kết nối bằng ID, sự kiện hoặc quy trình.

## 3. Phân loại quy tắc theo phạm vi nhất quán

| Nhóm | Ví dụ | Cách thực thi phù hợp |
| --- | --- | --- |
| Bên trong một value object | Money không nhận giá trị tiền âm trong trường hợp không cho phép | Constructor/factory kiểm tra điều kiện |
| Bên trong một aggregate | Order xác nhận phải có ít nhất một OrderLine | Phương thức hành vi của root và giao dịch lưu root |
| Giữa hai aggregate cùng service | Sau khi tạo Order cần cập nhật thống kê Customer | Có thể đồng bộ trong một transaction nếu thực sự thiết yếu; ưu tiên event nếu chỉ cần hội tụ |
| Giữa các service | Xác thực thanh toán, giữ hàng và tạo đơn vận chuyển | Saga/process manager, trạng thái chờ, event/message, retry và bù trừ |
| Quy tắc đọc/hiển thị | Tổng doanh số trên dashboard phản ánh các sự kiện đã nhận | Projection/read model, chấp nhận độ trễ được công bố |

Sự phân loại là quyết định thiết kế cần được chứng minh bằng yêu cầu nghiệp vụ. “Cùng service” không tự động có nghĩa “cùng aggregate”. “Có quan hệ khóa ngoại” cũng không chứng minh phải nằm trong cùng ranh giới giao dịch.

Đối với quy tắc liên service, cần nêu rõ trạng thái tạm thời nào hợp lệ, chờ được bao lâu, ai xử lý hết hạn và điều gì xảy ra khi một bước thất bại. Tính nhất quán cuối cùng (eventual consistency) không có nghĩa là bỏ qua bất biến; nó đòi hỏi xác định đúng bất biến nào có thể giữ cục bộ và quy trình nào cần điều phối để hội tụ.

## 4. Quy trình nhận diện aggregate từ nghiệp vụ

### Bước 1 — Xác định bounded context và từ vựng

Phỏng vấn người hiểu nghiệp vụ; liệt kê khái niệm có ý nghĩa trong ngữ cảnh như Order, Payment, StockReservation, Shipment. Tránh dùng một entity chung cho nhiều ngữ cảnh có ý nghĩa khác nhau: “Order” của bán hàng không nhất thiết giống “Order” của vận chuyển.

### Bước 2 — Thu thập lệnh và sự kiện nghiệp vụ

Đi từ hành vi, không bắt đầu bằng sơ đồ bảng. Ví dụ:

| Command | Kết quả/sự kiện mong đợi |
| --- | --- |
| AddOrderItem | OrderItemAdded |
| RemoveOrderItem | OrderItemRemoved |
| ConfirmOrder | OrderConfirmed |
| CancelOrder | OrderCancelled |
| ReserveStock | StockReserved hoặc StockReservationRejected |
| AuthorizePayment | PaymentAuthorized hoặc PaymentDeclined |

Hỏi ai phát lệnh, khi nào lệnh bị từ chối, các trạng thái cạnh tranh có thể xảy ra và bằng chứng nào cho biết thao tác thành công.

### Bước 3 — Viết bất biến bằng mệnh đề kiểm chứng được

Thay “đơn hàng hợp lệ” bằng “lệnh ConfirmOrder bị từ chối nếu số dòng hàng bằng 0”. Thay “không được bán vượt tồn” bằng “tổng số lượng đã giữ của một SKU tại kho không được vượt số lượng có thể phân bổ”, sau đó xác định aggregate ở Inventory sở hữu dữ liệu này.

Một bất biến tốt có phạm vi, điều kiện, thời điểm hiệu lực và cách xử lý khi vi phạm. Không phải mọi luật nghiệp vụ đều là bất biến tức thời; chính sách được đánh giá bằng dữ liệu từ ngoài aggregate đôi khi cần được kiểm tra ở application service và xem xét lại tại thời điểm phù hợp.

### Bước 4 — Tìm dữ liệu bắt buộc phải đổi nguyên tử

Gom những thuộc tính/đối tượng bắt buộc phải đồng bộ để không sinh trạng thái không hợp lệ. Nếu việc thêm dòng hàng đồng thời phải cập nhật tổng tiền, OrderLine và tổng Order thuộc ranh giới Order; cách an toàn hơn là tính tổng từ các dòng hoặc cập nhật trong cùng phương thức của root.

Đừng đưa toàn bộ Customer và Product vào Order chỉ vì Order cần tên khách hoặc giá sản phẩm. Sử dụng CustomerId, ProductId và snapshot thông tin cần cố định tại thời điểm đặt hàng.

### Bước 5 — Chọn root và API hành vi

Root phải có ID ổn định, quyền điều khiển trạng thái và các phương thức thể hiện ý định như addItem, confirm, cancel. Không mở setter công khai để caller sửa state hoặc children tùy ý.

Phần mềm bên ngoài tải root, gọi hành vi, lưu root trong transaction. Việc truy vấn DTO/read model có thể tối ưu độc lập mà không cần đi qua toàn bộ aggregate.

### Bước 6 — Kiểm tra xung đột đồng thời

Tìm hai lệnh có thể diễn ra cùng lúc: hai request sửa số lượng trong cùng Order, hai giao dịch giữ cùng một SKU, xác nhận và hủy cùng một Order. Chọn optimistic locking, conditional update, row lock hoặc kỹ thuật phù hợp với mức tranh chấp thực tế. Chỉ kiểm tra bằng code trước khi lưu là chưa đủ nếu hai transaction cùng đọc trạng thái cũ.

### Bước 7 — Kiểm soát kích thước và tải dữ liệu

Aggregate nên đủ nhỏ để tải và ghi hiệu quả. Nếu Order có hàng triệu lịch sử theo dõi, lịch sử đó không nên trở thành một collection bên trong Order root chỉ để tiện ánh xạ ORM. Phần dữ liệu chỉ để báo cáo hoặc không tham gia invariant có thể tách thành aggregate hay projection riêng.

### Bước 8 — Kiểm chứng qua các kịch bản lỗi

Thử lệnh lặp, lệnh đến sai thứ tự, transaction bị rollback, worker xử lý lại event, timeout kết nối service khác và thay đổi trạng thái đồng thời. Nếu ranh giới root không thể duy trì bất biến trong các tình huống này, cần xét lại mô hình hoặc cơ chế transaction.

## 5. Ví dụ: các aggregate trong luồng đặt hàng

Giả sử ứng dụng bán hàng gồm Ordering, Inventory, Payments và Shipping.

**Ordering** sở hữu Order. Nó bảo đảm trạng thái chuyển hợp lệ, dòng hàng dương, điều kiện xác nhận, tổng tiền chốt và chính sách hủy. Order giữ CustomerId, danh sách ProductId, snapshot giá, địa chỉ giao nhận. Product catalog không phải entity con của Order.

**Inventory** sở hữu quy tắc giữ tồn theo phạm vi phù hợp, chẳng hạn InventoryPosition cho một SKU tại một kho, hoặc một đơn vị tồn có khả năng khóa độc lập. Quy tắc “không giữ vượt số lượng có thể phân bổ” phải được thực thi nguyên tử ở nơi sở hữu số liệu tồn, có xử lý cạnh tranh.

**Payments** sở hữu Payment/PaymentAttempt, trạng thái giao dịch với nhà cung cấp và quy tắc không ghi nhận một lần thanh toán hai lần. Thông tin token/gateway phản hồi không nằm trong Order aggregate.

**Shipping** sở hữu Shipment và các chuyển trạng thái giao nhận; trạng thái Order chỉ phản ánh tiến độ cần cho người mua.

Ví dụ bảng quyết định:

| Quy tắc | Aggregate chịu trách nhiệm | Bảo đảm tại chỗ |
| --- | --- | --- |
| Đơn không rỗng mới xác nhận | Order | Có, trong transaction của Ordering |
| Tổng tiền bằng chi tiết giá đã chốt | Order | Có, trong Order |
| Không thay đổi dòng hàng khi đã xác nhận | Order | Có, thông qua root |
| Tổng số hàng được giữ không vượt mức khả dụng | Aggregate tồn kho thích hợp | Có, trong Inventory |
| Thanh toán không bị ghi nhận trùng | Payment/PaymentAttempt | Có, cộng với idempotency ở tích hợp |
| Chỉ giao hàng khi đơn có thanh toán và hàng đã giữ | Workflow giữa nhiều service | Theo quy trình điều phối; không phải invariant local duy nhất của Order |

Một luồng có thể là:

~~~text
Ordering: ConfirmOrder
  -> Order chuyển từ DRAFT sang PENDING_FULFILLMENT
  -> ghi OrderConfirmed vào outbox cùng transaction

Inventory: nhận OrderConfirmed
  -> thử giữ hàng
  -> phát StockReserved / ReservationRejected

Payments: xử lý yêu cầu thanh toán
  -> phát PaymentAuthorized / PaymentDeclined

Process manager / saga:
  -> khi đủ điều kiện, yêu cầu Shipping tạo Shipment
  -> nếu một bước thất bại, hủy giữ hàng hoặc hoàn tiền theo chính sách
  -> ghi nhận trạng thái cuối cùng và đường xử lý thủ công khi cần
~~~

Tên state/event chỉ là ví dụ; trình tự giữ hàng và thu tiền tùy chính sách thương mại. Điều cốt lõi là mỗi service **quyết định và cập nhật phần sở hữu của chính nó**, còn quy trình chung điều phối các kết quả đã cam kết.

## 6. Hiện thực một Order aggregate bằng Java

Ví dụ đơn giản minh họa luật bên trong aggregate. Giá đã chốt được truyền vào khi thêm sản phẩm; việc xác thực giá hiện hành hoặc áp mã khuyến mại thuộc luồng ứng dụng và chính sách miền liên quan trước khi chốt. Class bên dưới bỏ qua chi tiết ORM để tập trung vào hành vi.

~~~java
import java.math.BigDecimal;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

public final class Order {
    public enum Status { DRAFT, CONFIRMED, CANCELLED }

    private final UUID id;
    private final UUID customerId;
    private final Map<String, OrderLine> lines = new LinkedHashMap<>();
    private Status status = Status.DRAFT;
    private static final int MAX_DISTINCT_SKUS = 50;

    public Order(UUID id, UUID customerId) {
        if (id == null || customerId == null) {
            throw new IllegalArgumentException("Missing order or customer id");
        }
        this.id = id;
        this.customerId = customerId;
    }

    public void addItem(String sku, int quantity, BigDecimal unitPrice) {
        requireDraft();
        if (sku == null || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid item");
        }
        if (unitPrice == null || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid unit price");
        }

        OrderLine old = lines.get(sku);
        if (old == null) {
            if (lines.size() >= MAX_DISTINCT_SKUS) {
                throw new IllegalStateException("Order line limit reached");
            }
            lines.put(sku, new OrderLine(sku, quantity, unitPrice));
        } else {
            if (old.unitPrice().compareTo(unitPrice) != 0) {
                throw new IllegalArgumentException("Different price snapshot for SKU");
            }
            lines.put(sku, new OrderLine(
                sku, Math.addExact(old.quantity(), quantity), unitPrice));
        }
    }

    public void confirm() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Cannot confirm an empty order");
        }
        status = Status.CONFIRMED;
    }

    public void cancel() {
        if (status == Status.CANCELLED) {
            return; // idempotent local transition
        }
        if (status != Status.DRAFT && status != Status.CONFIRMED) {
            throw new IllegalStateException("Order cannot be cancelled");
        }
        status = Status.CANCELLED;
    }

    public BigDecimal total() {
        return lines.values().stream()
            .map(line -> line.unitPrice()
                .multiply(BigDecimal.valueOf(line.quantity())))
            .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public Status status() { return status; }
    public UUID id() { return id; }
    public UUID customerId() { return customerId; }

    public Map<String, OrderLine> lines() {
        return Collections.unmodifiableMap(lines);
    }

    private void requireDraft() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("Order is not editable");
        }
    }

    public record OrderLine(String sku, int quantity, BigDecimal unitPrice) {
        public OrderLine {
            if (sku == null || sku.isBlank() || quantity <= 0
                    || unitPrice == null || unitPrice.signum() < 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }
    }
}
~~~

Điểm thiết kế trong ví dụ:

1. Caller không thể sửa trực tiếp OrderLine vì bản ghi bất biến, map được che giấu và chỉ root cho phép thay đổi.
2. Root từ chối sửa sau Confirmed; các trạng thái không hợp lệ bị loại trước khi transaction commit.
3. Một SKU chỉ có một dòng trong một Order do map theo SKU. Giá chốt của SKU phải nhất quán; nếu nghiệp vụ cho phép nhiều mức giá cho cùng SKU thì khóa định danh dòng hàng phải được thiết kế khác.
4. Tổng tiền được tính từ các dòng hàng, tránh phải đồng bộ một trường tổng độc lập. Hệ thống đa tiền tệ cần Money gồm amount và currency, không được cộng tùy tiện hai currency.
5. Hàm cancel mô tả chính sách mẫu; thực tế một đơn đã thanh toán/giao hàng có thể yêu cầu quy trình hoàn tiền và nhiều trạng thái chuyển tiếp. Aggregate chỉ thực thi điều kiện dựa trên thông tin mà nó thực sự sở hữu.

Đây là code mô hình miền minh họa, chưa bao gồm mapping persistence, xác thực quyền người dùng, idempotency request, giới hạn số lượng tối đa trên một dòng, thuế, giảm giá hay event integration. Những trách nhiệm đó phải được bổ sung theo yêu cầu thực tế mà không phá vỡ ranh giới bất biến.

## 7. Transaction, đồng thời và tính toàn vẹn

### Một command ghi một aggregate

Một cách tổ chức thường dùng:

~~~text
HTTP/message handler
  -> Application service: xác thực người gọi, tải Order theo id
  -> Order.confirm(): áp dụng các bất biến
  -> Repository.save(Order): cùng local transaction
  -> Commit thành công
  -> Trả kết quả / phát tín hiệu tích hợp theo cơ chế an toàn
~~~

Application service điều phối, aggregate quyết định tính hợp lệ của thao tác. Không đặt toàn bộ luật trong controller hoặc repository; nếu một code path khác gọi service hoặc batch job thì vẫn phải đi qua cùng quy tắc miền.

### Tránh lost update

Giả sử hai yêu cầu cùng đọc Order phiên bản 7 rồi thay đổi khác nhau. Nếu cả hai cùng ghi mà không kiểm tra version, cập nhật sau có thể xóa thay đổi trước. Dùng optimistic concurrency control, ví dụ cột version và update có điều kiện:

~~~sql
UPDATE orders
SET status = :new_status, version = version + 1
WHERE order_id = :id AND version = :expected_version;
~~~

Nếu số hàng cập nhật bằng 0, transaction phải xử lý conflict, tải lại trạng thái và quyết định retry có an toàn hay trả lỗi nghiệp vụ. Ở ORM, có thể dùng cơ chế tương đương như JPA @Version. Retry mù có thể lặp side effect; chỉ retry khi command còn hợp lệ và có idempotency.

### Bất biến do nhiều request tranh cùng tài nguyên

Quy tắc “không đặt quá số ghế còn trống” hoặc “không giữ vượt tồn” dễ bị lỗi write skew nếu mỗi request chỉ kiểm tra số liệu bên ngoài vùng khóa của transaction. Hãy chọn aggregate thể hiện tài nguyên cạnh tranh, kết hợp locking/conditional update/unique constraint phù hợp mức cô lập dữ liệu. Nếu nhiều tài nguyên phải đặt nguyên tử, xác định lại yêu cầu: cần một giao dịch local có thể khóa tập tài nguyên nhỏ, hay một tiến trình giữ chỗ có thời hạn và bù trừ?

### Sự kiện phải đi cùng trạng thái đã cam kết

Nếu lưu Order rồi mới publish message, lỗi giữa hai thao tác có thể làm mất event. Transactional outbox ghi bản ghi event cùng transaction với Order; worker đưa event lên broker sau commit. Consumer phải chịu được giao hàng lặp, đến chậm và đôi khi sai thứ tự bằng event ID, version, inbox/idempotency và chính sách xử lý phù hợp. Outbox không tự tạo “exactly once end-to-end”.

## 8. Chống nhầm lẫn giữa aggregate và microservice

**Không nhất thiết một aggregate bằng một service.** Ordering có thể sở hữu Order, Cart, ReturnRequest; mỗi cái có giao dịch và bất biến riêng. Service boundary gắn với năng lực nghiệp vụ, team ownership, nhu cầu triển khai, dữ liệu và giao thức tích hợp.

**Không dùng aggregate để ép consistency giữa service.** Gắn Payment entity và Inventory entity vào Order object không biến thao tác xuyên service thành atomic transaction. Nếu service khác là chủ sở hữu thực sự, Order chỉ nên lưu ID, snapshot hoặc trạng thái được xác nhận thông qua sự kiện.

**Không tách entity con độc lập chỉ vì có ID.** OrderLine có thể có ID phục vụ UI nhưng vẫn thuộc vòng đời của Order, vì việc sửa nó thay đổi các luật của Order. Ngược lại, một AddressBookEntry của Customer có thể là aggregate riêng nếu có vòng đời, quyền sửa và mức tranh chấp riêng.

**Không chọn root theo bảng lớn nhất.** Root là điểm thực thi hành vi và bảo vệ nhất quán; tên bảng, ORM cascade hoặc cấu trúc JSON không quyết định điều này.

**Không cho phép repository sửa trực tiếp entity con.** Một lệnh SQL update OrderLine bỏ qua root có thể vô hiệu hóa các bất biến chỉ nằm trong code. Với bulk operations, hãy thiết kế cơ chế bảo vệ tương đương hoặc một quy trình miền riêng đã được xác định.

## 9. Dấu hiệu ranh giới aggregate đang có vấn đề

| Tín hiệu | Khả năng cần xem lại |
| --- | --- |
| Mỗi thao tác nhỏ phải tải hàng nghìn object con | Aggregate bao trùm dữ liệu không cần cho invariant |
| Hai yêu cầu độc lập liên tục tranh cùng lock/version | Root gộp quá nhiều luồng thay đổi |
| Luật bị lặp ở nhiều controller, worker, API | Thiếu hành vi miền tại root |
| Một command cần sửa trực tiếp database của service khác | Ranh giới sở hữu dữ liệu bị xâm phạm |
| Một invariant “local” cần gọi API ngoài để xác minh mỗi lần | Quy tắc thực chất nằm ở ngoài aggregate hoặc cần snapshot có hợp đồng rõ ràng |
| Một commit thành công nhưng domain event biến mất | Thiếu cơ chế ghi trạng thái và outbox nhất quán |
| Khóa ngoại/chia sẻ entity giữa services như chung một schema | Mô hình độc lập triển khai và quyền sở hữu chưa rõ |
| Mọi quan hệ dữ liệu đều được xem là cần transaction chung | Chưa phân biệt nhất quán tức thời với eventual consistency |

Đây là dấu hiệu để điều tra, không phải kết luận tự động. Đôi khi aggregate lớn hoặc pessimistic lock là lựa chọn đúng khi có yêu cầu nguyên tử thực sự và tải thấp.

## 10. Cách kiểm thử các bất biến

Kiểm thử bằng **command và trạng thái nhìn thấy qua root**; tránh phụ thuộc vào chi tiết setter hoặc cấu trúc lưu trữ.

| Tình huống | Kết quả mong muốn |
| --- | --- |
| Tạo dòng hàng với quantity = 0 | Bị từ chối |
| Xác nhận Order không có dòng | Bị từ chối, không đổi status |
| Xác nhận Order hợp lệ | Chuyển DRAFT sang CONFIRMED |
| Thêm hàng sau xác nhận | Bị từ chối |
| Thêm lại cùng SKU, cùng giá | Cộng số lượng hoặc tuân chính sách gộp đã chọn |
| Hai lệnh cùng dùng version cũ | Tối đa một lệnh ghi thành công; lệnh kia nhận conflict |
| Transaction ghi Order rollback | Outbox event tương ứng cũng rollback |
| Consumer nhận lặp một event | Không tạo thanh toán/giữ hàng lặp |
| Event thất bại hoặc đến trễ | Tiến trình có retry, timeout và trạng thái có thể quan sát |

Unit test phù hợp cho bất biến thuần trong root. Integration test cần để chứng minh repository, optimistic lock, transaction và unique constraint hoạt động. Test workflow giữa services cần kiểm tra các bước lỗi, retry và bù trừ; không thể thay thế bằng unit test Order.

Ví dụ kiểm thử thuần cho thao tác xác nhận:

~~~java
Order order = new Order(UUID.randomUUID(), UUID.randomUUID());

try {
    order.confirm();
    throw new AssertionError("Expected rejection");
} catch (IllegalStateException expected) {
    assert order.status() == Order.Status.DRAFT;
}

order.addItem("SKU-1", 2, new BigDecimal("10.00"));
order.confirm();
assert order.status() == Order.Status.CONFIRMED;
assert order.total().compareTo(new BigDecimal("20.00")) == 0;
~~~

Trong dự án thực tế nên dùng JUnit và assertion library thay cho Java assert, vì assert có thể bị tắt nếu JVM không bật -ea.

## 11. Bảng quyết định ngắn khi thiết kế

Với mỗi command, ghi lại các trường sau trước khi code:

| Câu hỏi | Cần trả lời |
| --- | --- |
| Bounded context sở hữu nghiệp vụ là gì? | Tên context, ngôn ngữ và trách nhiệm |
| Root nhận lệnh là gì? | Loại aggregate, aggregate ID |
| Dữ liệu nào root sở hữu trực tiếp? | Entity con, value object, snapshot |
| Bất biến nào phải đúng khi commit? | Mệnh đề cụ thể và tình huống từ chối |
| Dữ liệu nào thuộc aggregate/service khác? | ID tham chiếu, hợp đồng đọc/event |
| Mức tranh chấp thay đổi thế nào? | Khóa, version, unique constraint, retry policy |
| Transaction bao gồm những thay đổi nào? | Một atomic commit trong database được sở hữu |
| Có cần phát event tích hợp không? | Outbox, schema/version, idempotency |
| Luồng có nhiều service xử lý thế nào? | Các state, deadline, retry, compensation, giám sát |

Ví dụ quyết định cho ConfirmOrder:

~~~text
Context: Ordering
Aggregate root: Order(orderId)
Input: ConfirmOrder(orderId, expectedVersion)
Local invariants:
  - status == DRAFT
  - có ít nhất một OrderLine
  - từng quantity > 0; giá snapshot hợp lệ
Atomic write:
  - cập nhật Order, version và OrderConfirmed vào outbox
Outside boundary:
  - Inventory quyết định còn hàng hay không
  - Payments quyết định chấp nhận thanh toán
  - Saga điều phối hoàn tất hoặc từ chối đặt hàng
Concurrency:
  - optimistic lock; trả conflict nếu version không khớp
~~~

## 12. Những câu hỏi phải chốt với người làm nghiệp vụ

- “Xác nhận Order” là xác nhận yêu cầu của khách hay cam kết đã giữ được hàng? Hai định nghĩa đòi hỏi trạng thái và bất biến khác nhau.
- Một mặt hàng hết tồn có cho phép backorder hay không? Có thời gian hết hạn giữ hàng không?
- Giá dùng tại thời điểm xem giỏ hay thời điểm xác nhận? Ai có quyền đổi giá đã chốt?
- Có cho phép hủy khi payment đã authorize/capture hay shipment đã tạo không? Phải hoàn tiền theo luồng nào?
- Tính duy nhất của số đơn là toàn hệ thống, theo tenant hay theo khách? Cần unique constraint ở đúng phạm vi.
- Sự kiện được phép đến trễ bao lâu và ai xử lý khi một bước không hội tụ?
- Những thao tác nào có thể diễn ra đồng thời trên cùng aggregate? Tần suất tranh chấp có đủ lớn để cần mô hình khác?

Trả lời các câu hỏi trên giúp tránh việc lập trình viên tự đưa chính sách không được xác nhận vào setter hoặc transaction.

## 13. Bài thực hành gợi ý

Xét một ứng dụng đặt lịch khám: bệnh nhân chọn bác sĩ, ngày và khung giờ; khách có thể hủy trước một mốc thời gian; bác sĩ không được nhận hai cuộc hẹn cùng một slot.

Hãy xác định: (1) bounded context sở hữu lịch; (2) aggregate bảo vệ quy tắc không trùng slot trong giao dịch đồng thời; (3) aggregate Appointment sở hữu những chuyển trạng thái nào; (4) điều gì xảy ra khi thanh toán đặt cọc thành công nhưng giữ slot thất bại; (5) kiểm thử đồng thời nào chứng minh không double-booking.

Gợi ý: chỉ kiểm tra “slot còn trống” qua một read query rồi tạo Appointment độc lập có thể bị race condition. Cần xác định tài nguyên/khóa có thẩm quyền hoặc unique constraint phù hợp, kết hợp transaction và cơ chế xử lý thanh toán bất đồng bộ.

---

**Nguyên tắc áp dụng:** Xác định aggregate bằng **những bất biến phải đúng sau một local commit**, chọn root để kiểm soát mọi thay đổi ảnh hưởng tới chúng, và coi workflow xuyên aggregate/service là một vấn đề điều phối có trạng thái, lỗi, thời hạn và phục hồi riêng. Khi ranh giới này rõ ràng, microservices mới thực sự có quyền sở hữu dữ liệu và tính nhất quán dễ giải thích, kiểm thử, vận hành.