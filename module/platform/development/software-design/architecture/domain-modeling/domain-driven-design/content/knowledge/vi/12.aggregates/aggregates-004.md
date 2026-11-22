# Thiết kế aggregate nhỏ theo nhu cầu nhất quán thực tế

Trong Domain-Driven Design (DDD), **Aggregate** là ranh giới nhất quán bao quanh một nhóm đối tượng miền. Mọi thay đổi từ bên ngoài đi qua **Aggregate Root**, đối tượng chịu trách nhiệm bảo vệ các bất biến của toàn bộ Aggregate. Khi thiết kế Aggregate, mục tiêu không phải gom càng nhiều Entity có quan hệ với nhau càng tốt, mà là xác định nhóm dữ liệu và hành vi nào thực sự cần được thay đổi như một đơn vị nhất quán.

Một Aggregate nhỏ thường dễ hiểu, dễ kiểm thử, giảm xung đột cập nhật và cho phép các phần của hệ thống phát triển độc lập hơn. Tuy nhiên, “nhỏ” không chỉ có nghĩa là ít thuộc tính hoặc ít đối tượng. Ranh giới đúng phải bảo vệ được các quy tắc cần đúng ngay tại thời điểm giao dịch. Nếu tách quá nhỏ, bất biến bị đẩy ra ngoài và cần phối hợp nhiều Aggregate cho một thay đổi đáng lẽ phải nguyên tử. Nếu gom quá lớn, mọi thay đổi không liên quan đều tranh chấp cùng một ranh giới nhất quán.

Vì vậy, hãy bắt đầu từ **nhu cầu nhất quán thực tế**: quy tắc nào phải được bảo đảm ngay lập tức, ai sở hữu quy tắc đó, dữ liệu nào phải thay đổi cùng nhau và điều gì có thể được xử lý sau thông qua sự kiện hoặc quy trình phối hợp.

## 1. Aggregate và ranh giới nhất quán

Một Aggregate là một cụm đối tượng được xem như một đơn vị khi thực hiện thay đổi nghiệp vụ. Bên ngoài chỉ tương tác với cụm thông qua Aggregate Root. Các đối tượng bên trong có thể là Entity hoặc Value Object tùy vai trò và vòng đời.

Ví dụ, một đơn hàng có thể gồm:

- **Order**: Aggregate Root, có định danh và quản lý vòng đời đơn hàng.
- **OrderLine**: dòng hàng, chứa sản phẩm, số lượng và giá được ghi nhận cho giao dịch.
- **Money**: Value Object biểu diễn số tiền và đơn vị tiền tệ.
- **Address**: Value Object biểu diễn địa chỉ giao hàng tại thời điểm đặt.

Khi thêm một dòng hàng, Order kiểm tra đơn còn được phép chỉnh sửa và dữ liệu dòng hàng hợp lệ. Bên ngoài không tự sửa danh sách dòng hàng hoặc cập nhật trạng thái trực tiếp. Các thay đổi phải đi qua hành vi của Root để các quy tắc được bảo vệ.

### 1.1. Ranh giới nhất quán là gì?

Ranh giới nhất quán xác định phạm vi mà các bất biến cần được duy trì ngay trong một lần thay đổi. Nếu một hành động làm thay đổi trạng thái của Aggregate, khi giao dịch hoàn tất thì Aggregate phải ở trạng thái hợp lệ theo các quy tắc của nó.

Ví dụ, nếu nghiệp vụ yêu cầu tổng tiền của đơn hàng luôn bằng tổng giá trị các dòng hàng, thay đổi số lượng hoặc thêm dòng phải cập nhật kết quả tính tiền theo cùng một thao tác logic. Một cách đơn giản là tính tổng từ các dòng thay vì lưu một giá trị tổng có thể lệch. Nếu cần lưu tổng để tối ưu truy vấn, Root phải bảo đảm mọi thay đổi liên quan cập nhật nó nhất quán.

Không phải mọi quan hệ dữ liệu đều cần nằm trong cùng một Aggregate. Khách hàng đặt đơn, sản phẩm xuất hiện trong đơn và kho giữ hàng đều có liên hệ nghiệp vụ, nhưng điều đó không tự động có nghĩa chúng phải thuộc một Aggregate duy nhất.

### 1.2. Aggregate không phải cây object graph

Một mô hình hướng đối tượng có thể có nhiều tham chiếu lồng nhau. Aggregate được xác định bởi quy tắc nhất quán, không phải bởi việc các đối tượng có thể gọi được nhau.

Ví dụ, Order có thể tham chiếu đến Customer, Product và Shipment. Nhưng nếu mỗi đối tượng có vòng đời, quy tắc và tần suất thay đổi riêng, gom tất cả vào một Aggregate sẽ làm ranh giới quá rộng. Thường chỉ cần lưu định danh của Aggregate khác và phối hợp qua hợp đồng hoặc sự kiện.

## 2. Vì sao nên thiết kế Aggregate nhỏ?

Aggregate lớn khiến một thay đổi cục bộ có thể tải, khóa hoặc ghi lại nhiều dữ liệu không liên quan. Khi nhiều người dùng cùng cập nhật các đối tượng trong cùng Aggregate, xung đột lạc quan hoặc tranh chấp khóa có thể tăng. Kiểm thử cũng khó hơn vì cần dựng một lượng lớn dữ liệu và hiểu nhiều quy tắc không cùng trách nhiệm.

Thiết kế Aggregate nhỏ mang lại một số lợi ích:

- **Giảm phạm vi giao dịch:** chỉ tải và thay đổi dữ liệu cần thiết để bảo vệ các bất biến liên quan.
- **Giảm cạnh tranh cập nhật:** các thao tác độc lập có thể tác động lên các Aggregate khác nhau.
- **Làm rõ quyền sở hữu:** mỗi Root chịu trách nhiệm cho một nhóm quy tắc cụ thể.
- **Giảm phụ thuộc:** một thay đổi không cần kéo theo việc tải toàn bộ object graph.
- **Dễ kiểm thử:** có thể kiểm tra hành vi và bất biến của một Aggregate với phạm vi dữ liệu rõ ràng.
- **Hỗ trợ mở rộng:** các phần có nhịp thay đổi khác nhau có thể được lưu trữ, xử lý hoặc triển khai độc lập hơn.

Tuy nhiên, không nên theo đuổi kích thước nhỏ bằng mọi giá. Nếu một quy tắc cần được bảo đảm đồng bộ mà nhóm đã tách dữ liệu ra nhiều Aggregate, hệ thống có thể phải xử lý trạng thái trung gian, lỗi từng phần và eventual consistency. Chi phí đó có thể lớn hơn lợi ích của việc tách.

## 3. Bắt đầu từ bất biến, không bắt đầu từ bảng dữ liệu

Một cách thiết kế phổ biến nhưng dễ gây sai lệch là tạo một Aggregate cho mỗi bảng hoặc gom các bảng có khóa ngoại với nhau. DDD yêu cầu nhóm bắt đầu từ quy tắc nghiệp vụ.

Hãy hỏi:

1. Những điều kiện nào phải luôn đúng sau khi một hành động nghiệp vụ hoàn tất?
2. Hành động nào có thể làm thay đổi các điều kiện đó?
3. Dữ liệu nào cần được đọc và thay đổi cùng nhau để bảo đảm chúng?
4. Ai có quyền quyết định thay đổi có hợp lệ không?
5. Quy tắc cần được bảo đảm ngay trong giao dịch hay có thể được hoàn tất sau?

Ví dụ với tồn kho:

- Số lượng có thể bán không được âm.
- Không thể giữ nhiều hơn số lượng còn khả dụng.
- Một yêu cầu giữ hàng phải được chấp nhận toàn bộ hoặc từ chối theo chính sách.

Những quy tắc này thuộc năng lực quản lý tồn kho. Một Aggregate như InventoryItem có thể quản lý số lượng đang có, số lượng đã giữ và các hành vi giữ/giải phóng. Order không cần tải toàn bộ dữ liệu kho để tự sửa số lượng.

## 4. Phân biệt bất biến tức thời và quy tắc có thể hoàn tất sau

Đây là bước quan trọng nhất khi chọn ranh giới Aggregate.

### 4.1. Bất biến cần được bảo đảm ngay

Một quy tắc cần nhất quán tức thời khi nghiệp vụ không chấp nhận trạng thái trung gian sau khi một hành động hoàn tất. Ví dụ:

- Một đơn hàng không được xác nhận nếu không có dòng hàng hợp lệ.
- Một dòng hàng không được có số lượng bằng hoặc nhỏ hơn không.
- Một tài khoản không được ghi nhận giao dịch rút tiền làm số dư âm nếu chính sách không cho phép thấu chi.
- Một lần giữ hàng không được làm lượng hàng đã giữ vượt quá lượng có thể giữ.

Nếu các dữ liệu cần thiết thuộc cùng một Aggregate, Root có thể kiểm tra và thay đổi chúng trong một giao dịch. Nếu một bất biến đòi hỏi dữ liệu thuộc nhiều Aggregate, cần xem lại cách phân chia trách nhiệm hoặc xác định liệu quy tắc đó thực sự cần được bảo đảm tức thời.

### 4.2. Quy tắc có thể được phối hợp sau

Một số quy tắc có thể chấp nhận trạng thái trung gian trong thời gian ngắn, miễn là quy trình cuối cùng đưa hệ thống về trạng thái đúng và có cách xử lý thất bại. Ví dụ:

- Khi đơn được xác nhận, gửi email thông báo có thể diễn ra sau.
- Báo cáo doanh thu có thể cập nhật sau khi giao dịch hoàn tất.
- Search Index có thể nhận thay đổi sản phẩm qua sự kiện và cập nhật trễ.
- Dịch vụ chăm sóc khách hàng có thể nhận thông báo đơn bị hủy sau khi Order đã lưu trạng thái mới.

Các việc này không cần nằm trong Aggregate của Order. Có thể dùng Domain Event, message broker, Transactional Outbox hoặc quy trình phối hợp phù hợp.

### 4.3. Không biến eventual consistency thành lý do bỏ qua bất biến

Eventual consistency phù hợp với những quy tắc cho phép hoàn tất sau. Nó không phải giải pháp để né một bất biến quan trọng. Ví dụ, nếu doanh nghiệp tuyệt đối không cho phép bán vượt tồn kho, việc chỉ phát OrderPlaced rồi hy vọng Inventory cập nhật sau có thể tạo ra nhiều đơn được chấp nhận hơn số lượng thực có.

Trong trường hợp đó, Inventory phải có một thao tác giữ hàng nguyên tử để quyết định yêu cầu nào được chấp nhận. Order có thể ở trạng thái chờ cho đến khi nhận kết quả. Sự phối hợp giữa hai Aggregate cần mô hình hóa rõ, thay vì giả định cả hai thay đổi trong một giao dịch duy nhất.

## 5. Quy trình thiết kế một Aggregate nhỏ

Có thể thực hiện theo các bước sau:

### Bước 1: Chọn một hành vi nghiệp vụ cụ thể

Đừng bắt đầu từ câu hỏi “có những Entity nào?”. Hãy chọn một hành vi như xác nhận đơn, giữ hàng, phê duyệt yêu cầu hoặc rút tiền. Mô tả ai khởi tạo, mục tiêu và kết quả cần đạt.

### Bước 2: Liệt kê các bất biến liên quan

Viết các điều kiện phải đúng trước và sau hành động. Tránh các mô tả chung chung như “dữ liệu phải hợp lệ”. Hãy diễn đạt điều kiện có thể kiểm chứng, chẳng hạn “số lượng giữ của một mặt hàng không vượt quá số lượng có thể bán”.

### Bước 3: Xác định chủ sở hữu quy tắc

Hỏi khái niệm nào chịu trách nhiệm bảo vệ bất biến. Nếu quy tắc nói về vòng đời đơn hàng, Order có thể là Root. Nếu quy tắc nói về khả năng giữ hàng, InventoryItem hoặc một Aggregate tồn kho phù hợp có thể là chủ sở hữu.

### Bước 4: Gom dữ liệu tối thiểu cần cho bất biến

Chỉ đưa các đối tượng và giá trị cần thiết để Root bảo vệ quy tắc vào Aggregate. Không thêm Customer, Product hoặc toàn bộ Shipment chỉ vì chúng có liên kết trong cơ sở dữ liệu.

### Bước 5: Thiết kế hành vi trên Aggregate Root

Mọi thay đổi bên ngoài cần đi qua các phương thức có tên theo nghiệp vụ. Root kiểm tra điều kiện, thay đổi các đối tượng con và ghi nhận sự kiện miền nếu cần.

### Bước 6: Xác định cách tham chiếu Aggregate khác

Thông thường dùng ID thay vì giữ tham chiếu object trực tiếp đến Root khác. Khi cần dữ liệu hoặc hành vi của Aggregate khác, Application hoặc Domain Service phối hợp qua Repository, port hoặc hợp đồng tích hợp.

### Bước 7: Xác định giao dịch và xử lý cạnh tranh

Làm rõ phạm vi giao dịch, cách xử lý hai yêu cầu đồng thời, optimistic locking hoặc cơ chế khóa phù hợp. Kiểm tra xem bất biến có thể bị phá vỡ bởi cập nhật đồng thời hay không.

### Bước 8: Xác định phần có thể xử lý bất đồng bộ

Những công việc không cần hoàn tất cùng giao dịch có thể được phát sinh qua Domain Event và xử lý sau. Cần quy định cách retry, idempotency, thứ tự và xử lý lỗi.

### Bước 9: Kiểm chứng bằng tình huống thực tế

Thử luồng thành công, bị từ chối, dữ liệu biên và hai yêu cầu đồng thời. Nếu cần quá nhiều truy vấn hoặc điều phối để bảo vệ một quy tắc, xem lại ranh giới.

## 6. Ví dụ: Order là một Aggregate nhỏ

Giả sử nghiệp vụ đặt ra các quy tắc:

- Đơn hàng nháp có thể thêm hoặc xóa dòng hàng.
- Đơn phải có ít nhất một dòng hợp lệ trước khi xác nhận.
- Dòng hàng ghi nhận giá tại thời điểm đặt để lịch sử không thay đổi khi Catalog cập nhật giá.
- Tổng tiền đơn được tính từ các dòng hàng.
- Đơn đã xác nhận không thể sửa danh sách dòng theo luồng đặt hàng thông thường.

Order có thể là Aggregate Root, còn OrderLine là thành phần bên trong. Product được tham chiếu bằng ProductId; Order không cần giữ toàn bộ Product Aggregate.

~~~mermaid
classDiagram
    class Order {
      +OrderId id
      +OrderStatus status
      +addLine(line)
      +removeLine(productId)
      +confirm()
      +total()
    }
    class OrderLine {
      +ProductId productId
      +ProductName nameSnapshot
      +Money unitPrice
      +Quantity quantity
      +subtotal()
    }
    class Money {
      +amount
      +currency
      +add(other)
      +multiply(quantity)
    }
    Order "1" *-- "1..*" OrderLine
    OrderLine --> Money
~~~

Sơ đồ cho thấy Order sở hữu vòng đời của các dòng hàng trong phạm vi đơn. Các Value Object như Money và Quantity biểu diễn giá trị với quy tắc riêng.

### 6.1. Ví dụ mã Java

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public final class Order {
    private final OrderId id;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;

    public Order(OrderId id) {
        this.id = Objects.requireNonNull(id);
    }

    public void addLine(OrderLine line) {
        requireDraft();
        lines.add(Objects.requireNonNull(line));
    }

    public void removeLine(ProductId productId) {
        requireDraft();
        OrderLine line = lines.stream()
                .filter(item -> item.productId().equals(productId))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("Line not found"));

        lines.remove(line);
    }

    public void confirm() {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("An empty order cannot be confirmed");
        }
        status = OrderStatus.CONFIRMED;
    }

    public Money total() {
        return lines.stream()
                .map(OrderLine::subtotal)
                .reduce(Money.zero("VND"), Money::add);
    }

    public List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    public OrderId id() {
        return id;
    }

    public OrderStatus status() {
        return status;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only draft orders can be changed");
        }
    }

    public record OrderId(String value) {
        public OrderId {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Order ID is required");
            }
        }
    }

    public record ProductId(String value) {
        public ProductId {
            if (value == null || value.isBlank()) {
                throw new IllegalArgumentException("Product ID is required");
            }
        }
    }

    public record Quantity(int value) {
        public Quantity {
            if (value <= 0) {
                throw new IllegalArgumentException("Quantity must be positive");
            }
        }
    }

    public record Money(BigDecimal amount, String currency) {
        public Money {
            Objects.requireNonNull(amount);
            Objects.requireNonNull(currency);
            if (amount.signum() < 0 || currency.isBlank()) {
                throw new IllegalArgumentException("Invalid money value");
            }
        }

        public static Money zero(String currency) {
            return new Money(BigDecimal.ZERO, currency);
        }

        public Money add(Money other) {
            requireSameCurrency(other);
            return new Money(amount.add(other.amount), currency);
        }

        public Money multiply(Quantity quantity) {
            return new Money(
                    amount.multiply(BigDecimal.valueOf(quantity.value())),
                    currency
            );
        }

        private void requireSameCurrency(Money other) {
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("Currency mismatch");
            }
        }
    }

    public record OrderLine(
            ProductId productId,
            String nameSnapshot,
            Money unitPrice,
            Quantity quantity
    ) {
        public OrderLine {
            Objects.requireNonNull(productId);
            Objects.requireNonNull(nameSnapshot);
            Objects.requireNonNull(unitPrice);
            Objects.requireNonNull(quantity);
        }

        public Money subtotal() {
            return unitPrice.multiply(quantity);
        }
    }

    public enum OrderStatus {
        DRAFT, CONFIRMED
    }
}
~~~

Đây là ví dụ minh họa độc lập về ranh giới và hành vi. Trong ứng dụng thật, các kiểu có thể được tách thành file riêng; cần bổ sung chính sách về thuế, chiết khấu, làm tròn tiền, quyền chỉnh sửa, sự kiện miền và lưu trữ. Ví dụ cũng giả định các dòng hàng dùng cùng đơn vị tiền tệ.

### 6.2. Vì sao Product không nằm trong Order Aggregate?

Order cần biết sản phẩm nào được đặt, nhưng không cần sở hữu toàn bộ thông tin hiện tại của Product. Product có thể được quản lý trong Catalog Context và thay đổi độc lập. Order lưu ProductId cùng các dữ liệu snapshot cần thiết cho giao dịch, như tên và giá tại thời điểm đặt.

Nếu Order giữ tham chiếu trực tiếp đến Product Aggregate, việc đọc hoặc thay đổi đơn có thể kéo theo tải và phụ thuộc vào Catalog. Khi giá sản phẩm thay đổi, lịch sử đơn cũng có nguy cơ phản ánh sai nếu chỉ đọc dữ liệu hiện tại.

### 6.3. Vì sao tổng tiền được tính từ dòng hàng?

Trong ví dụ, tổng tiền là dữ liệu suy ra từ các dòng nên được tính khi cần. Điều này tránh tình trạng tổng tiền bị lệch sau khi thêm hoặc xóa dòng. Nếu hiệu năng yêu cầu lưu tổng tiền, Order phải cập nhật tổng cùng mọi thay đổi dòng hàng và có kiểm thử bảo vệ bất biến.

## 7. Ví dụ: Inventory là Aggregate riêng

Giả sử tồn kho có các quy tắc:

- Số lượng khả dụng không được âm.
- Không thể giữ nhiều hơn số lượng có thể bán.
- Một yêu cầu giữ hàng phải được quyết định nguyên tử.
- Giữ hàng có thể hết hạn và cần được giải phóng.

Inventory có vòng đời và nhịp thay đổi độc lập với Order. Nhiều đơn hàng có thể cùng yêu cầu giữ một sản phẩm, vì vậy dữ liệu tồn kho cần một điểm sở hữu có thể xử lý cạnh tranh.

Một mô hình minh họa:

~~~java
public final class InventoryItem {
    private final ProductId productId;
    private int onHand;
    private int reserved;

    public InventoryItem(ProductId productId, int onHand) {
        if (onHand < 0) {
            throw new IllegalArgumentException("On-hand quantity cannot be negative");
        }
        this.productId = productId;
        this.onHand = onHand;
    }

    public void reserve(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        if (onHand - reserved < quantity) {
            throw new IllegalStateException("Insufficient available inventory");
        }
        reserved += quantity;
    }

    public void release(int quantity) {
        if (quantity <= 0 || quantity > reserved) {
            throw new IllegalArgumentException("Invalid release quantity");
        }
        reserved -= quantity;
    }

    public int available() {
        return onHand - reserved;
    }
}
~~~

Đây là minh họa rút gọn cho một InventoryItem; hệ thống thật cần định nghĩa cách phân biệt kho, vị trí, lô hàng, hàng đang vận chuyển và thời hạn giữ. Việc cập nhật đồng thời cần được bảo vệ bằng giao dịch và cơ chế kiểm soát cạnh tranh như optimistic locking hoặc khóa phù hợp.

Order chỉ gửi yêu cầu giữ hàng qua một cổng hoặc Application Service. Inventory quyết định chấp nhận hay từ chối. Order không được tự sửa reserved của Inventory.

## 8. Phối hợp nhiều Aggregate mà không gom chúng lại

Khi một use case cần thay đổi nhiều Aggregate, Application có thể điều phối các bước và dùng sự kiện để thông báo kết quả. Không nên mở rộng Aggregate chỉ để có một giao dịch lớn nếu các quy tắc thực tế thuộc những chủ sở hữu khác nhau.

Ví dụ quy trình đặt hàng:

1. Order được tạo ở trạng thái chờ giữ hàng.
2. Application gửi yêu cầu giữ từng mặt hàng đến Inventory.
3. Inventory kiểm tra khả năng giữ và trả kết quả.
4. Nếu giữ hàng thành công, Order có thể chuyển sang trạng thái chờ thanh toán hoặc xác nhận theo chính sách.
5. Nếu giữ hàng thất bại, Order được từ chối hoặc hủy theo quy trình.
6. Nếu thanh toán thất bại sau khi giữ hàng, Application yêu cầu Inventory giải phóng lượng đã giữ.

~~~mermaid
sequenceDiagram
    participant A as Application
    participant O as Order Aggregate
    participant I as Inventory Aggregate
    participant P as Payment
    A->>O: place()
    O-->>A: OrderPlaced
    A->>I: reserve(items)
    alt Đủ hàng
        I-->>A: InventoryReserved
        A->>P: requestPayment()
        P-->>A: PaymentReceived
        A->>O: confirm()
    else Không đủ hàng
        I-->>A: ReservationRejected
        A->>O: reject(reason)
    end
~~~

Sơ đồ là một luồng minh họa. Nếu các bước chạy bất đồng bộ, hệ thống cần mô hình hóa trạng thái chờ và xử lý sự kiện lặp, đến muộn hoặc thất bại. Với quy trình nhiều bước kéo dài, có thể dùng Saga hoặc Process Manager để điều phối và thực hiện hành động bù trừ.

### 8.1. Tham chiếu Aggregate khác bằng ID

Một Aggregate thường tham chiếu Aggregate khác bằng định danh thay vì giữ một object reference trực tiếp. Ví dụ:

- Order lưu CustomerId và ProductId.
- Shipment lưu OrderId.
- Payment lưu OrderId.

Khi cần dữ liệu, Application tải Aggregate liên quan qua Repository hoặc dùng một read model phù hợp. Cách này giúp tránh object graph lớn và làm rõ quyền sở hữu.

### 8.2. Không dùng một giao dịch lớn để che giấu ranh giới sai

Nếu một hành động phải tải hàng chục Aggregate và cập nhật tất cả trong một giao dịch, có thể nhóm đang gom quá nhiều trách nhiệm hoặc chưa phân biệt bất biến tức thời với quy tắc có thể hoàn tất sau. Hãy kiểm tra lại chính sách trước khi tăng kích thước Aggregate.

Tuy nhiên, nếu nghiệp vụ thực sự yêu cầu một bất biến được bảo đảm nguyên tử trên cùng tập dữ liệu, nhóm cần xem xét đặt chúng trong cùng một Aggregate hoặc chọn một cơ chế nhất quán khác được thiết kế có chủ đích. Không nên tách chỉ để đạt tiêu chí “mỗi Aggregate một Entity”.

## 9. Repository và quyền truy cập Aggregate

Repository thường được thiết kế quanh Aggregate Root. Bên ngoài tải Root rồi gọi hành vi của nó; không truy cập trực tiếp đối tượng con để sửa trạng thái.

Ví dụ:

~~~java
public interface OrderRepository {
    Optional<Order> findById(OrderId id);
    void save(Order order);
}
~~~

Không nhất thiết cần OrderLineRepository nếu OrderLine chỉ tồn tại bên trong Order Aggregate và không có vòng đời độc lập. Việc tạo Repository riêng cho từng bảng hoặc từng Entity con có thể làm lộ cấu trúc lưu trữ và bỏ qua ranh giới nhất quán.

Repository giúp mô hình làm việc với Aggregate mà không cần biết cơ sở dữ liệu. Cách triển khai có thể lưu toàn Aggregate trong nhiều bảng hoặc tài liệu, miễn là giữ được quy tắc và giao dịch cần thiết.

## 10. Kiểm soát cập nhật đồng thời

Aggregate nhỏ giúp giảm phạm vi cạnh tranh nhưng không loại bỏ vấn đề hai yêu cầu cùng cập nhật một Aggregate.

Ví dụ, hai khách cùng đặt mặt hàng cuối cùng. Cả hai yêu cầu đều có thể đọc available = 1. Nếu cả hai sau đó ghi reserved = reserved + 1 mà không có kiểm soát đồng thời, hệ thống có thể giữ hai đơn vị dù chỉ có một.

Một số cơ chế thường dùng:

- **Optimistic locking:** lưu version của Aggregate; khi ghi, chỉ chấp nhận nếu version chưa bị thay đổi bởi giao dịch khác.
- **Pessimistic locking:** khóa bản ghi hoặc tài nguyên trong thời gian giao dịch khi mức cạnh tranh và yêu cầu nhất quán phù hợp.
- **Atomic conditional update:** thực hiện cập nhật có điều kiện ở cơ sở dữ liệu, ví dụ chỉ tăng lượng giữ nếu số lượng khả dụng vẫn đủ.
- **Idempotency:** nhận diện yêu cầu lặp để một lệnh giữ hàng hoặc thanh toán không bị áp dụng nhiều lần.

Chọn cơ chế dựa trên mức độ cạnh tranh, yêu cầu độ trễ, công nghệ lưu trữ và hậu quả của việc chấp nhận sai. Các cơ chế này là chi tiết triển khai của ranh giới nhất quán; chúng không thay thế việc xác định đúng Aggregate.

## 11. Dấu hiệu Aggregate đang quá lớn hoặc quá nhỏ

### 11.1. Dấu hiệu Aggregate quá lớn

- Một thay đổi nhỏ phải tải nhiều đối tượng không liên quan.
- Nhiều luồng nghiệp vụ độc lập thường xuyên cập nhật cùng một Root.
- Xung đột optimistic locking xảy ra thường xuyên dù các thay đổi không liên quan.
- Aggregate có nhiều collection lớn hoặc object graph sâu.
- Một Root phải bảo vệ các quy tắc thuộc nhiều năng lực nghiệp vụ khác nhau.
- Chỉ một phần nhỏ của Aggregate cần thay đổi trong hầu hết use case.
- Nhóm khó giải thích vì sao các đối tượng phải nhất quán trong cùng một giao dịch.

Hướng xử lý là tìm các bất biến thực sự cần được bảo vệ cùng nhau, tách phần còn lại thành Aggregate độc lập và phối hợp qua ID, sự kiện hoặc Application Service.

### 11.2. Dấu hiệu Aggregate quá nhỏ

- Một hành động nghiệp vụ thường xuyên phải cập nhật nhiều Aggregate để bảo vệ một bất biến vốn phải đúng ngay.
- Caller phải biết quá nhiều chi tiết nội bộ và tự điều phối các bước thay đổi.
- Hệ thống có nhiều trạng thái trung gian không có ý nghĩa với nghiệp vụ.
- Một quy tắc quan trọng chỉ được kiểm tra ở Application và có thể bị bỏ qua bởi luồng khác.
- Việc xử lý lỗi từng phần trở nên phức tạp hơn giá trị đạt được từ việc tách.

Hướng xử lý là xem xét đưa dữ liệu cần thiết vào cùng Aggregate hoặc thiết kế lại chính sách để quy tắc có thể được bảo đảm bằng một thao tác nguyên tử tại chủ sở hữu thích hợp.

## 12. Những sai lầm thường gặp

### 12.1. Tạo một Aggregate cho mỗi bảng

Bảng dữ liệu phản ánh cách lưu trữ, không tự nói lên ranh giới nhất quán. Nhiều bảng có thể thuộc một Aggregate; một bảng cũng có thể chứa dữ liệu phục vụ nhiều khái niệm tùy thiết kế. Hãy bắt đầu từ bất biến và hành vi.

### 12.2. Gom toàn bộ quan hệ khóa ngoại vào một Aggregate

Customer, Product, Order và Shipment có thể liên kết trong cơ sở dữ liệu nhưng có vòng đời và quy tắc khác nhau. Gom chúng lại làm mọi thay đổi trở nên phụ thuộc.

### 12.3. Dùng Aggregate để thay thế transaction toàn hệ thống

Aggregate bảo vệ nhất quán trong ranh giới của nó. Nó không tự tạo giao dịch ACID xuyên nhiều dịch vụ hoặc nhiều cơ sở dữ liệu. Các quy trình liên ngữ cảnh cần thiết kế phối hợp riêng.

### 12.4. Dùng Domain Event cho mọi thay đổi nhỏ

Sự kiện có ích khi sự việc có ý nghĩa với nghiệp vụ hoặc cần phối hợp giữa các phần. Phát sự kiện cho mọi phép gán nội bộ làm tăng độ phức tạp và khiến mô hình khó hiểu.

### 12.5. Để đối tượng con bị sửa trực tiếp

Nếu caller có thể thay đổi OrderLine ngoài Root, bất biến của Order không còn được bảo vệ. Hãy đóng gói collection và chỉ cung cấp các hành vi cần thiết.

### 12.6. Tạo Aggregate Root chỉ để có Repository

Không phải mọi đối tượng đều cần trở thành Aggregate. Đối tượng con có thể thuộc vòng đời của Root và không cần Repository riêng. Chỉ tạo Root khi có ranh giới nhất quán và trách nhiệm nghiệp vụ rõ.

### 12.7. Hiểu “nhỏ” là phải ít dòng code

Một Aggregate có thể có nhiều hành vi nhưng vẫn nhỏ về phạm vi nhất quán. Ngược lại, một lớp ít dòng code vẫn có thể là Root quá lớn nếu nó sở hữu nhiều bất biến không liên quan. Hãy đánh giá theo trách nhiệm và dữ liệu cần thay đổi cùng nhau.

## 13. Checklist thiết kế Aggregate

- [ ] Đã chọn hành vi nghiệp vụ cụ thể làm điểm bắt đầu.
- [ ] Các bất biến phải đúng ngay sau giao dịch đã được viết rõ.
- [ ] Đã xác định Aggregate Root chịu trách nhiệm bảo vệ từng bất biến.
- [ ] Chỉ đưa vào Aggregate dữ liệu cần thiết cho các bất biến đó.
- [ ] Các đối tượng con không thể bị sửa trực tiếp từ bên ngoài Root.
- [ ] Aggregate khác được tham chiếu bằng ID khi phù hợp.
- [ ] Repository được thiết kế quanh Root, không phải từng bảng hoặc từng đối tượng con.
- [ ] Đã xác định phần nào cần nhất quán tức thời và phần nào có thể xử lý sau.
- [ ] Đã xác định cách phối hợp nhiều Aggregate và xử lý lỗi từng phần.
- [ ] Đã xem xét cập nhật đồng thời, optimistic locking và idempotency.
- [ ] Kích thước Aggregate không gây tải dữ liệu hoặc tranh chấp không cần thiết.
- [ ] Các tình huống thành công, bị từ chối và cạnh tranh đã được kiểm thử.

## 14. Kết luận

Thiết kế Aggregate nhỏ là quá trình tìm ranh giới tối thiểu đủ để bảo vệ những bất biến cần được duy trì ngay trong một giao dịch. Hãy bắt đầu từ hành vi nghiệp vụ, xác định quy tắc, tìm chủ sở hữu và chỉ gom dữ liệu cần thiết vào cùng Aggregate. Aggregate Root kiểm soát mọi thay đổi; các Aggregate khác thường được tham chiếu bằng ID và phối hợp qua Application Service, Domain Event hoặc quy trình phù hợp.

Một Aggregate quá lớn làm tăng phụ thuộc và cạnh tranh cập nhật; một Aggregate quá nhỏ khiến bất biến bị phân tán và quy trình phối hợp trở nên phức tạp. Ranh giới tốt cân bằng được nhu cầu nhất quán, quyền sở hữu nghiệp vụ, chi phí giao dịch và cách hệ thống cần tiến hóa. Kích thước đúng vì thế được quyết định bởi quy tắc thực tế, không phải bởi số lượng lớp hay bảng dữ liệu.
