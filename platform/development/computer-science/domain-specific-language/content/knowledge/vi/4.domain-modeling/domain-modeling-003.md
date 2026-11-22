# Ranh giới aggregate

## 1. Aggregate trong mô hình miền

Trong thiết kế hướng miền (*Domain-Driven Design — DDD*), **aggregate** là một cụm đối tượng miền được xem như một đơn vị nhất quán khi thay đổi dữ liệu. Cụm này có thể chứa một hoặc nhiều entity và value object. Mỗi aggregate có đúng một **aggregate root** (đối tượng gốc), là điểm truy cập công khai để phần còn lại của hệ thống yêu cầu thay đổi trạng thái bên trong cụm.

**Ranh giới aggregate** xác định những đối tượng nào thuộc cùng một đơn vị nhất quán, những quy tắc nghiệp vụ nào phải được bảo vệ cùng nhau và những thao tác nào phải đi qua aggregate root. Đây là quyết định mô hình miền quan trọng: nó ảnh hưởng đến tính đúng đắn của nghiệp vụ, cách tổ chức giao dịch, khả năng xử lý đồng thời và hiệu năng của ứng dụng.

Ví dụ trong hệ thống bán hàng:

- Một `Order` có thể là aggregate root.
- Các `OrderLine` thuộc về đơn hàng và không được sửa độc lập từ bên ngoài.
- `Money` có thể là value object được dùng trong đơn hàng và từng dòng hàng.
- `Customer`, `Product` và `Inventory` có thể là các aggregate riêng, với root và vòng đời riêng.

Không phải mọi đối tượng có liên hệ với nhau đều phải nằm trong cùng một aggregate. Ranh giới nên được đặt quanh những quy tắc cần được bảo đảm nhất quán ngay trong cùng một lần thay đổi.

## 2. Aggregate root và các đối tượng bên trong

### 2.1. Aggregate root

Aggregate root là entity đại diện cho aggregate. Nó chịu trách nhiệm:

- Là cổng truy cập từ bên ngoài vào trạng thái của aggregate.
- Kiểm tra và bảo vệ các invariant (bất biến nghiệp vụ) của aggregate.
- Điều phối thay đổi trên các entity và value object bên trong.
- Xác định những thao tác nghiệp vụ hợp lệ tại thời điểm hiện tại.
- Là đối tượng được repository lưu và tải như một đơn vị miền.

Phần mã bên ngoài nên gọi hành vi của root thay vì lấy một đối tượng con rồi sửa trực tiếp. Ví dụ, thay vì cho phép controller thay đổi `orderLine.quantity`, hệ thống gọi `order.changeQuantity(lineId, newQuantity)`. Root có thể kiểm tra trạng thái đơn hàng, số lượng hợp lệ và ảnh hưởng đến tổng tiền trước khi chấp nhận thay đổi.

### 2.2. Entity và value object bên trong aggregate

Một aggregate có thể chứa nhiều loại đối tượng:

- **Entity:** có danh tính ổn định và vòng đời. `OrderLine` có thể là entity nếu từng dòng hàng cần một định danh riêng để cập nhật hoặc theo dõi.
- **Value object:** được xác định bởi các giá trị của nó, thường bất biến. `Money`, `Address` hoặc `Quantity` có thể là value object.
- **Các đối tượng hỗ trợ:** cấu trúc hoặc quy tắc nội bộ chỉ có ý nghĩa trong aggregate đó.

Đối tượng bên trong không có quyền tự tạo ra một đường truy cập công khai để hệ thống sửa nó ngoài sự kiểm soát của root. Điều này không có nghĩa mọi trường đều phải được đặt trực tiếp trong root; root có thể ủy quyền cho entity con thực hiện một phần hành vi, miễn là invariant chung vẫn được bảo vệ.

### 2.3. Minh họa cấu trúc

```text
                 Order Aggregate
        +--------------------------------+
        | Order (Aggregate Root)         |
        | - orderId                      |
        | - status                       |
        | - lines                        |
        | - total                        |
        |                                |
        |   +------------------------+   |
        |   | OrderLine              |   |
        |   | - productId            |   |
        |   | - quantity             |   |
        |   | - unitPrice: Money     |   |
        |   +------------------------+   |
        |                                |
        |   Money / Address / ...        |
        +--------------------------------+
                  ^
                  | tham chiếu bằng ID
                  |
        +--------------------+   +--------------------+
        | Customer Aggregate |   | Product Aggregate  |
        | Customer (root)    |   | Product (root)     |
        +--------------------+   +--------------------+
```

Sơ đồ chỉ là một mô hình minh họa. Một thiết kế khác có thể đặt địa chỉ giao hàng thành một value object trong `Order`, dù địa chỉ ban đầu được lấy từ `Customer`. Quyết định phụ thuộc vào quy tắc và vòng đời dữ liệu của miền.

## 3. Ranh giới aggregate bảo vệ điều gì?

### 3.1. Invariant nghiệp vụ

Invariant là điều kiện phải luôn đúng đối với mô hình miền tại những thời điểm được quy định. Ví dụ:

- Đơn hàng đã xác nhận phải có ít nhất một dòng hàng.
- Số lượng trong mỗi dòng hàng phải lớn hơn 0.
- Tổng tiền đơn hàng phải khớp với các dòng hàng và quy tắc tính giá đã áp dụng.
- Đơn hàng đã giao không được chuyển ngược về trạng thái đang soạn.
- Một tài khoản không được có số dư thấp hơn giới hạn cho phép.

Nếu nhiều đối tượng phải thay đổi cùng nhau để giữ một invariant, đó là dấu hiệu chúng có thể thuộc cùng một aggregate. Root là nơi cung cấp các hành vi để cập nhật chúng theo một quy trình được kiểm soát.

Ví dụ, khi thêm một dòng hàng vào đơn, hệ thống phải cập nhật danh sách dòng hàng và tính lại tổng tiền. Nếu tổng tiền là dữ liệu được lưu trữ, root phải bảo đảm hai thay đổi này không tạo ra một trạng thái không hợp lệ sau khi giao dịch hoàn tất.

### 3.2. Ranh giới nhất quán và giao dịch

Aggregate thường được dùng làm ranh giới nhất quán giao dịch: một thao tác cập nhật phải đưa aggregate từ một trạng thái hợp lệ sang một trạng thái hợp lệ khác. Theo cách tiếp cận DDD phổ biến, nên thiết kế một giao dịch nghiệp vụ chỉ cập nhật một aggregate. Đây là nguyên tắc thiết kế nhằm giảm khóa, xung đột đồng thời và sự phụ thuộc giữa các cụm dữ liệu.

Điều đó không có nghĩa mọi hệ thống đều bắt buộc chỉ được ghi một aggregate trong một giao dịch cơ sở dữ liệu. Có những yêu cầu cần tính nhất quán tức thời giữa nhiều dữ liệu; nhóm có thể chọn một giao dịch rộng hơn nếu hạ tầng hỗ trợ và đánh đổi là chấp nhận được. Tuy nhiên, khi làm như vậy, mô hình sẽ có thêm liên kết chặt chẽ và khó mở rộng hơn. Trong nhiều miền nghiệp vụ, có thể giữ invariant bên trong từng aggregate rồi điều phối thay đổi giữa các aggregate bằng sự kiện miền và quy trình nhất quán cuối cùng (*eventual consistency*).

### 3.3. Không đồng nhất với ranh giới lưu trữ

Aggregate là khái niệm mô hình miền, không phải một bảng cơ sở dữ liệu. Một aggregate có thể được lưu trong nhiều bảng, hoặc được lưu dưới dạng tài liệu trong một document database. Ngược lại, một bảng có thể chứa dữ liệu phục vụ nhiều mô hình truy vấn khác nhau.

Việc một ORM cho phép điều hướng từ entity này sang entity khác cũng không quyết định ranh giới aggregate. Ranh giới phải xuất phát từ invariant và quy tắc nghiệp vụ, sau đó mới ánh xạ sang cấu trúc lưu trữ phù hợp.

## 4. Nguyên tắc thiết kế ranh giới

### 4.1. Đặt các invariant cần nhất quán cùng nhau vào một aggregate

Hãy tìm những quy tắc mà hệ thống phải bảo đảm ngay khi một thao tác hoàn tất. Nếu một quy tắc liên quan đến nhiều đối tượng và mọi đối tượng phải được cập nhật nguyên tử để quy tắc không bị vi phạm, hãy cân nhắc đặt chúng trong cùng một aggregate.

Ví dụ, nếu `Order` phải luôn có tổng tiền phù hợp với danh sách `OrderLine`, hai phần này thường thuộc cùng aggregate. Root có thể thêm, xóa hoặc đổi số lượng dòng hàng và cập nhật tổng tiền trong cùng một giao dịch.

### 4.2. Giữ aggregate nhỏ và tập trung

Một aggregate lớn khiến mỗi thay đổi phải tải và có thể khóa nhiều dữ liệu. Nó làm tăng khả năng hai thao tác độc lập tranh chấp cùng một aggregate, đồng thời khiến invariant khó hiểu hơn. Hãy chỉ đưa vào những đối tượng cần thiết để bảo vệ quy tắc nhất quán của aggregate.

Kích thước nhỏ không phải mục tiêu tuyệt đối. Nếu tách một đối tượng ra khiến invariant quan trọng không thể được bảo đảm đúng lúc, việc giữ nó trong aggregate có thể hợp lý hơn. Cần cân bằng tính đúng đắn với chi phí tải dữ liệu và xử lý đồng thời.

### 4.3. Tham chiếu aggregate khác bằng định danh

Khi một aggregate cần biết về aggregate khác, thường nên lưu định danh của root kia thay vì giữ tham chiếu đối tượng có thể điều hướng sâu vào toàn bộ đồ thị. Ví dụ, `OrderLine` lưu `productId`, còn `Order` lưu `customerId`.

Cách này giúp mỗi aggregate có vòng đời và quyền sở hữu dữ liệu rõ ràng. Khi cần thông tin sản phẩm để hiển thị, ứng dụng có thể truy vấn `Product` qua repository hoặc một read model. Nếu đơn hàng cần giữ giá tại thời điểm đặt hàng, nó nên lưu snapshot `unitPrice` đã chốt thay vì luôn đọc giá hiện tại từ `Product`.

### 4.4. Chỉ truy cập qua aggregate root

Phần bên ngoài không nên sửa trực tiếp entity con hoặc lưu entity con độc lập như thể nó là root. Repository thường được định nghĩa cho aggregate root, ví dụ `OrderRepository`, chứ không tạo `OrderLineRepository` để các thành phần tùy ý cập nhật dòng hàng.

Điều này giữ cho các lệnh nghiệp vụ đi qua một điểm có thể kiểm tra invariant. Với các truy vấn đọc, ứng dụng có thể dùng projection hoặc read model riêng để lấy dữ liệu hiệu quả mà không phải tải toàn bộ aggregate.

### 4.5. Không kéo dữ liệu vào chỉ vì có quan hệ

Một quan hệ trong sơ đồ lớp hoặc khóa ngoại trong cơ sở dữ liệu không tự động có nghĩa hai đối tượng phải cùng aggregate. Hãy đặt câu hỏi: chúng có cần thay đổi cùng nhau để bảo đảm một invariant tức thời không? Nếu câu trả lời là không, có thể chúng nên nằm trong hai aggregate.

Ví dụ, một đơn hàng có thể tham chiếu khách hàng, nhưng việc khách hàng đổi số điện thoại không nhất thiết phải cập nhật hoặc khóa mọi đơn hàng trước đó. Dữ liệu liên hệ hiện tại có thể thuộc `Customer`; thông tin giao hàng đã chốt cho đơn hàng có thể là snapshot thuộc `Order`.

## 5. Ví dụ: thiết kế aggregate cho hệ thống bán hàng

### 5.1. Xác định các quy tắc

Giả sử hệ thống có các yêu cầu:

1. Đơn hàng phải có ít nhất một dòng hàng trước khi xác nhận.
2. Mỗi dòng hàng có số lượng dương và đơn giá đã được chốt.
3. Đơn hàng đã xác nhận không được tùy ý thêm hoặc xóa dòng hàng.
4. Số lượng tồn kho không được giảm xuống dưới 0.
5. Thông tin khách hàng có thể thay đổi độc lập với các đơn hàng cũ.

Các quy tắc 1–3 liên quan chặt chẽ đến trạng thái và các dòng hàng của một đơn hàng, nên phù hợp với `Order` aggregate. Quy tắc 4 liên quan đến tồn kho của sản phẩm, có thể thuộc `Inventory` aggregate riêng. Quy tắc 5 cho thấy `Customer` có vòng đời riêng và không cần nằm trong `Order`.

Một mô hình khái quát:

| Aggregate | Aggregate root | Dữ liệu chính và invariant |
|---|---|---|
| Order | `Order` | Trạng thái đơn, các dòng hàng, tổng tiền; quy tắc xác nhận và sửa đơn |
| Inventory | `InventoryItem` hoặc `Stock` | Số lượng khả dụng; không cho phép tồn kho âm |
| Customer | `Customer` | Thông tin và trạng thái khách hàng |
| Product | `Product` | Mô tả, mã hàng và thông tin sản phẩm |

Tên root cụ thể tùy ngôn ngữ miền. Trong một số hệ thống, tồn kho được mô hình hóa theo kho và sản phẩm, nên aggregate có thể mang tên `StockItem` hoặc `InventoryPosition`.

### 5.2. Cài đặt hành vi của Order root

Đoạn Java dưới đây minh họa cách root kiểm soát thay đổi. Đây là mã khung giản lược để giải thích mô hình; các constructor, kiểu ID và phần lưu trữ được rút gọn.

```java
public final class Order {
    private final OrderId id;
    private final CustomerId customerId;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;
    private Money total = Money.zero("VND");

    public void addItem(ProductId productId, int quantity, Money unitPrice) {
        ensureDraft();
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        lines.add(new OrderLine(productId, quantity, unitPrice));
        recalculateTotal();
    }

    public void changeQuantity(OrderLineId lineId, int quantity) {
        ensureDraft();
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        OrderLine line = findLine(lineId);
        line.changeQuantity(quantity);
        recalculateTotal();
    }

    public void confirm() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("An order needs at least one line");
        }

        recalculateTotal();
        status = OrderStatus.CONFIRMED;
    }

    private void ensureDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Order can no longer be changed");
        }
    }

    private void recalculateTotal() {
        total = lines.stream()
            .map(OrderLine::subtotal)
            .reduce(Money.zero("VND"), Money::add);
    }

    // findLine, getters and persistence details are omitted.
}
```

Điểm quan trọng trong ví dụ là các thao tác `addItem`, `changeQuantity` và `confirm` thuộc về `Order`. Root kiểm tra trạng thái, xác thực số lượng và cập nhật tổng tiền. Nếu `OrderLine` có phương thức thay đổi số lượng, phương thức đó nên được giới hạn trong phạm vi mô hình để bên ngoài không gọi trực tiếp và bỏ qua kiểm tra của `Order`.

### 5.3. Điều phối giữa Order và Inventory

Khi xác nhận đơn, hệ thống có thể cần giữ hoặc trừ tồn kho. Nếu `Order` và `Inventory` là hai aggregate, không nên để `Order` đi sâu vào đối tượng tồn kho rồi sửa trực tiếp. Một quy trình ứng dụng có thể:

1. Gọi hành vi xác nhận hoặc tạo yêu cầu giữ hàng trên `Order`.
2. Phát hành sự kiện miền như `OrderConfirmationRequested` hoặc một command giữ hàng.
3. Một handler xử lý yêu cầu trên `Inventory` aggregate bằng hành vi `reserve(quantity)`.
4. Nếu giữ hàng thành công, phát sự kiện `InventoryReserved`; quy trình tiếp tục hoàn tất đơn.
5. Nếu không đủ hàng, quy trình có thể từ chối đơn hoặc chuyển đơn sang trạng thái cần xử lý, theo chính sách nghiệp vụ.

Tên sự kiện và thứ tự chính xác tùy quy trình. Có thể dùng saga/process manager để điều phối nhiều bước, và transactional outbox để bảo đảm sự kiện được phát đi đáng tin cậy sau khi thay đổi dữ liệu đã commit.

Vì hai aggregate có thể được cập nhật ở những thời điểm khác nhau, hệ thống cần mô hình hóa các trạng thái trung gian như `PENDING_INVENTORY`, `CONFIRMED` hoặc `REJECTED` nếu nghiệp vụ cần. Đây là cách thể hiện rõ eventual consistency thay vì giả định toàn bộ quy trình luôn xảy ra trong một thao tác nguyên tử.

## 6. Ranh giới aggregate và tính nhất quán cuối cùng

### 6.1. Khi invariant vượt qua nhiều aggregate

Một số quy tắc nghiệp vụ liên quan đến nhiều aggregate. Ví dụ, khách hàng không được có quá ba đơn hàng đang xử lý. Nếu các đơn hàng thuộc những aggregate khác nhau, việc kiểm tra và tạo đơn đồng thời có thể khiến hai yêu cầu cùng đọc số lượng hiện tại rồi đều vượt qua giới hạn.

Đây là dấu hiệu cần xem xét lại mô hình:

- Quy tắc có thật sự cần được bảo đảm tuyệt đối tại đúng thời điểm tạo đơn không?
- Có thể chuyển dữ liệu đếm hoặc quyền quyết định vào một aggregate điều phối như `CustomerOrderQuota` không?
- Có thể chấp nhận xử lý bất đồng bộ rồi bù trừ khi vượt giới hạn không?
- Có cần một giao dịch cơ sở dữ liệu bao trùm nhiều aggregate, và hệ thống có chấp nhận sự phụ thuộc đó không?

Không có câu trả lời chung cho mọi miền. Điều quan trọng là không giả vờ một invariant liên aggregate đã được bảo đảm chỉ vì mỗi aggregate riêng lẻ có kiểm tra hợp lệ.

### 6.2. Domain event và quy trình phối hợp

Khi một aggregate hoàn tất thay đổi, nó có thể ghi nhận domain event mô tả sự việc đã xảy ra, ví dụ `OrderPlaced`. Application layer hoặc event handler có thể dùng sự kiện để yêu cầu aggregate khác thực hiện hành vi tương ứng.

Domain event thường biểu diễn một sự thật trong miền; command biểu diễn yêu cầu thực hiện hành động. Phân biệt hai khái niệm giúp quy trình rõ ràng:

```text
Order.place()
    |
    v
OrderPlaced (domain event)
    |
    v
Handler / Process Manager
    |
    +----> Inventory.reserve()
    |           |
    |           +----> InventoryReserved
    |
    +----> Payment.requestAuthorization()
                |
                +----> PaymentAuthorized / PaymentRejected
```

Quy trình có thể có nhiều bước, thất bại từng phần, retry và bù trừ. Ví dụ nếu thanh toán thất bại sau khi giữ hàng, hệ thống cần phát lệnh giải phóng tồn kho. Vì vậy, thiết kế aggregate nên đi cùng thiết kế trạng thái quy trình và cách xử lý lỗi.

### 6.3. Eventual consistency không có nghĩa là bỏ qua tính đúng đắn

Nhất quán cuối cùng có nghĩa các aggregate có thể tạm thời phản ánh những thời điểm khác nhau, rồi hội tụ sau khi các sự kiện hoặc lệnh phối hợp được xử lý. Nó không cho phép bỏ qua invariant nội bộ. Mỗi aggregate vẫn phải bảo vệ những quy tắc thuộc phạm vi của chính nó.

Nếu giao diện cần hiển thị trạng thái trong lúc chờ xử lý, hãy biểu diễn trạng thái đang chờ rõ ràng. Cần định nghĩa timeout, retry, xử lý sự kiện trùng lặp và hành động bù trừ để quy trình không mắc kẹt.

## 7. Aggregate boundary và truy cập dữ liệu

### 7.1. Repository dành cho aggregate root

Repository cung cấp cách tải và lưu aggregate như một đơn vị miền. Ví dụ:

```java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
```

Application service điều phối use case, tải root, gọi hành vi miền rồi yêu cầu lưu:

```java
public final class ConfirmOrderHandler {
    private final OrderRepository orders;

    public void handle(ConfirmOrder command) {
        Order order = orders.findById(command.orderId())
            .orElseThrow(OrderNotFoundException::new);

        order.confirm();
        orders.save(order);
    }
}
```

Ví dụ lược bỏ transaction manager và xử lý domain event để tập trung vào ranh giới. Trong ứng dụng thực tế, tải root, thay đổi và lưu thường nằm trong một transaction do application layer hoặc framework quản lý.

### 7.2. Truy vấn không nhất thiết phải tải aggregate

Quy tắc truy cập qua root chủ yếu áp dụng cho việc thay đổi trạng thái. Các màn hình đọc thường cần dữ liệu tổng hợp từ nhiều aggregate. Có thể dùng query service, projection, view hoặc CQRS read model để trả dữ liệu phù hợp mà không phải tải toàn bộ đồ thị đối tượng miền.

Ví dụ, màn hình lịch sử đơn hàng có thể truy vấn trực tiếp mã đơn, ngày tạo, tên sản phẩm và tổng tiền từ một read model. Việc đọc này không đồng nghĩa được phép cập nhật `OrderLine` trực tiếp trong cơ sở dữ liệu.

### 7.3. Ánh xạ sang cơ sở dữ liệu

Một ORM có thể ánh xạ `Order` và `OrderLine` thành hai bảng có quan hệ khóa ngoại. Repository tải root cùng các đối tượng con cần thiết; khi lưu, ORM hoặc lớp persistence ghi các thay đổi tương ứng. Nếu aggregate quá lớn, tải toàn bộ dữ liệu mỗi lần sẽ gây chi phí đáng kể.

Một số lưu ý khi triển khai:

- Chỉ tải các thành phần cần thiết để thực hiện hành vi của aggregate.
- Dùng cascade persistence có chủ đích; không để thao tác lưu vô tình xóa hoặc sửa dữ liệu của aggregate khác.
- Tránh để entity con được cập nhật qua nhiều repository độc lập.
- Xem xét optimistic locking bằng version để phát hiện hai giao dịch cùng sửa một aggregate.
- Với cập nhật đồng thời, xác định cách xử lý xung đột: báo người dùng thử lại, tải lại và áp dụng lại lệnh, hoặc dùng chiến lược khóa phù hợp.

## 8. Những sai lầm thường gặp

### 8.1. Gom mọi đối tượng liên quan vào một aggregate lớn

Một `Order` chứa trực tiếp toàn bộ `Customer`, `Product`, `Inventory`, `Payment` và lịch sử giao hàng có vẻ thuận tiện vì có thể điều hướng đến mọi dữ liệu. Nhưng mỗi thay đổi có thể phải tải hoặc khóa quá nhiều đối tượng; những phần có vòng đời độc lập lại bị gắn chặt vào đơn hàng.

Hãy phân biệt dữ liệu cần snapshot trong đơn hàng với dữ liệu hiện hành thuộc aggregate khác. Ví dụ, lưu tên sản phẩm và đơn giá tại thời điểm mua nếu cần bảo toàn hóa đơn lịch sử; không nhất thiết nhúng toàn bộ `Product` aggregate vào `Order`.

### 8.2. Chia quá nhỏ, khiến invariant bị phân tán

Nếu mỗi `OrderLine` là một aggregate độc lập nhưng quy tắc yêu cầu tổng tiền và trạng thái xác nhận của cả đơn phải luôn nhất quán, hệ thống phải điều phối nhiều aggregate cho một thao tác thường xuyên. Điều đó có thể làm tăng độ phức tạp và tạo ra trạng thái trung gian không mong muốn.

Hãy giữ các đối tượng cùng tham gia một invariant tức thời trong một aggregate khi điều đó hợp lý.

### 8.3. Bỏ qua root và sửa entity con trực tiếp

Nếu controller, repository hoặc một service bất kỳ được phép lấy `OrderLine` rồi cập nhật số lượng trực tiếp, nó có thể bỏ qua kiểm tra trạng thái đơn và việc tính lại tổng tiền. Hãy cung cấp hành vi ở root và giới hạn khả năng sửa trực tiếp của đối tượng con.

### 8.4. Dùng quan hệ ORM để quyết định mô hình miền

Việc hai entity có quan hệ `@OneToMany` hoặc `@ManyToOne` chỉ mô tả ánh xạ lưu trữ. Nó không chứng minh hai entity cần thuộc cùng aggregate. Nếu ranh giới được thiết kế chỉ theo sự thuận tiện của ORM, mô hình dễ bị chi phối bởi cấu trúc bảng thay vì nghiệp vụ.

### 8.5. Giả định eventual consistency tự giải quyết mọi xung đột

Tách aggregate giúp giảm phạm vi nhất quán tức thời, nhưng hệ thống vẫn phải xử lý yêu cầu trùng lặp, sự kiện đến sai thứ tự, timeout, retry và hành động bù trừ. Mỗi quy trình liên aggregate cần có trạng thái và chính sách lỗi rõ ràng.

### 8.6. Đặt invariant ở application service thay vì miền

Application service có thể điều phối use case, nhưng không nên trở thành nơi duy nhất bảo vệ invariant của aggregate. Nếu quy tắc chỉ nằm trong một handler, một đường gọi khác có thể bỏ qua nó. Hãy đặt hành vi và điều kiện hợp lệ cốt lõi trong root hoặc các đối tượng miền mà root kiểm soát.

## 9. Quy trình xác định ranh giới aggregate

Khi mô hình hóa một miền mới, có thể thực hiện theo các bước sau:

1. **Liệt kê quy tắc nghiệp vụ:** ghi lại điều kiện phải đúng trước và sau mỗi hành động quan trọng.
2. **Xác định các thay đổi nguyên tử:** tìm dữ liệu phải được cập nhật cùng nhau để không vi phạm invariant.
3. **Nhóm đối tượng theo tính nhất quán:** tạo các cụm ứng viên; chọn một entity đại diện làm root cho mỗi cụm.
4. **Xác định API của root:** mô tả các hành vi nghiệp vụ hợp lệ, đầu vào, điều kiện và kết quả.
5. **Tách tham chiếu đến aggregate khác:** ưu tiên định danh của root; xác định dữ liệu snapshot cần giữ tại thời điểm nghiệp vụ.
6. **Xác định giao dịch và đồng thời:** quyết định phạm vi transaction, cơ chế khóa hoặc version, và cách xử lý xung đột.
7. **Thiết kế quy trình liên aggregate:** dùng command, domain event, process manager hoặc saga khi cần phối hợp nhiều bước.
8. **Kiểm tra với tình huống thực tế:** thử các ca thay đổi đồng thời, lỗi giữa chừng, hủy thao tác và dữ liệu lớn để xem ranh giới có phù hợp không.

Ranh giới aggregate có thể được điều chỉnh khi hiểu biết về miền sâu hơn. Nếu thường xuyên phải tải nhiều aggregate chỉ để giữ một invariant, có thể ranh giới hiện tại chưa hợp lý. Nếu một aggregate có quá nhiều dữ liệu và xung đột cập nhật cao, có thể cần tách nó, đồng thời thiết kế lại quy tắc liên quan.

## 10. Kết luận

Ranh giới aggregate xác định phạm vi mà mô hình miền bảo vệ tính nhất quán khi thay đổi. Aggregate root là cổng truy cập và chịu trách nhiệm bảo vệ invariant của cụm đối tượng; các thành phần bên trong được thay đổi thông qua hành vi do root kiểm soát. Aggregate khác thường được tham chiếu bằng định danh và phối hợp qua command, domain event hoặc quy trình nghiệp vụ.

Khi thiết kế, hãy bắt đầu từ invariant và vòng đời nghiệp vụ. Giữ trong cùng aggregate những dữ liệu cần thay đổi nhất quán cùng nhau, đồng thời giữ các aggregate tập trung để giảm phụ thuộc và xung đột đồng thời. Ranh giới phù hợp giúp mô hình dễ hiểu, giao dịch rõ ràng và hệ thống có thể phát triển mà không làm suy yếu các quy tắc của miền.
