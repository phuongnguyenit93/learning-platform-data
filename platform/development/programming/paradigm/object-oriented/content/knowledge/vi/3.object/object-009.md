# Theo dõi tương tác của các đối tượng trong một tình huống (Java OOP)

Khi chương trình hướng đối tượng xử lý một yêu cầu, công việc thường được chia cho nhiều **đối tượng (object)**. Mỗi đối tượng giữ một phần trạng thái và đảm nhận một trách nhiệm. Để hiểu chương trình thực sự chạy như thế nào, ta cần theo dõi **đối tượng nào nhận lời gọi, gọi tiếp đối tượng nào, dữ liệu nào được truyền đi, kết quả nào trả về và trạng thái nào thay đổi**.

Bài này dùng một tình huống đặt hàng nhỏ để đi từ mã Java đến bảng diễn tiến và **UML sequence diagram**. Những kỹ năng đó hữu ích khi đọc code người khác, debug, giải thích luồng xử lý trong phỏng vấn và thiết kế hệ thống có nhiều lớp.

## 1. Theo dõi đối tượng là theo dõi điều gì?

Giả sử người dùng đặt mua **2 quyển sách**. Hệ thống cần:

1. Lấy tổng tiền từ giỏ hàng.
2. Kiểm tra và giữ số lượng trong kho.
3. Gọi bộ xử lý thanh toán.
4. Tạo thông tin đơn hàng nếu thanh toán thành công.
5. Gửi thông báo.
6. Trả đơn hàng cho đoạn code đã yêu cầu đặt hàng.

Các công việc này thuộc các đối tượng khác nhau:

| Đối tượng | Trách nhiệm | Trạng thái quan trọng |
| --- | --- | --- |
| `Cart` | Cung cấp mặt hàng, số lượng, đơn giá, tính tổng | SKU, số lượng, đơn giá |
| `Inventory` | Quản lý số lượng tồn của từng mã hàng | Bản đồ SKU → số lượng |
| `PaymentGateway` | Mô phỏng việc chấp nhận/từ chối thanh toán | Cấu hình kết quả mô phỏng |
| `OrderService` | Điều phối trình tự đặt hàng | Tham chiếu đến các đối tượng cộng tác |
| `Order` | Mang dữ liệu về đơn hàng đã tạo | Mã đơn, mặt hàng, số lượng, tiền, mã giao dịch |
| `Notifier` | Gửi thông báo về đơn hàng | Trong ví dụ chỉ in log |

**Lưu ý về cấp độ:** `Cart`, `Inventory` hay `OrderService` là *lớp* (class); `new Cart(...)`, `new Inventory(...)` là các *đối tượng cụ thể*. Các mũi tên trong sơ đồ tương tác diễn tả **lời gọi giữa những instance tại thời điểm chạy**, không phải quan hệ kế thừa giữa các class.

Một đoạn theo dõi tốt trả lời được năm câu hỏi:

- **Ai khởi phát?** Ví dụ `main` gọi `OrderService.checkout(cart)`.
- **Ai nhận?** Biến `service` đang trỏ tới một instance `OrderService`.
- **Thông điệp/lời gọi là gì?** Tên phương thức và đối số, ví dụ `inventory.reserve("BOOK", 2)`.
- **Kết quả nào được trả về?** Giá trị trả về hoặc ngoại lệ, ví dụ `"TX-001"`.
- **Sau lời gọi, điều gì thay đổi?** Tồn kho từ 5 xuống 3; một `Order` mới được tạo.

## 2. Ví dụ đầy đủ: đặt hàng có nhiều đối tượng cộng tác

Chạy bằng **Java 11 trở lên**. Lưu toàn bộ đoạn mã vào một tệp `ObjectInteractionDemo.java`; mã chỉ dùng thư viện chuẩn Java.

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ObjectInteractionDemo {

    // Ghi lại thứ tự các sự kiện để quan sát luồng chạy.
    static class Trace {
        private static int step = 0;

        static void log(String message) {
            System.out.printf("%02d %s%n", ++step, message);
        }
    }

    // Giỏ hàng chứa một mặt hàng cho ví dụ dễ theo dõi.
    static class Cart {
        final String sku;
        final int quantity;
        final BigDecimal unitPrice;

        Cart(String sku, int quantity, BigDecimal unitPrice) {
            if (sku == null || sku.isBlank()) {
                throw new IllegalArgumentException("SKU không hợp lệ");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (unitPrice.signum() <= 0) {
                throw new IllegalArgumentException("Đơn giá phải dương");
            }
            this.sku = sku;
            this.quantity = quantity;
            this.unitPrice = unitPrice;
        }

        BigDecimal total() {
            BigDecimal amount = unitPrice.multiply(
                    BigDecimal.valueOf(quantity)
            );
            Trace.log("Cart.total() -> " + amount.toPlainString());
            return amount;
        }
    }

    // Chỉ Inventory có trách nhiệm thay đổi tồn kho.
    static class Inventory {
        private final Map<String, Integer> stock = new HashMap<>();

        Inventory(String sku, int initialQuantity) {
            if (initialQuantity < 0) {
                throw new IllegalArgumentException("Tồn kho âm");
            }
            stock.put(sku, initialQuantity);
        }

        int available(String sku) {
            return stock.getOrDefault(sku, 0);
        }

        void reserve(String sku, int quantity) {
            Trace.log("Inventory.reserve(" + sku + ", " + quantity + ")");
            if (quantity <= 0) {
                throw new IllegalArgumentException("Số lượng phải dương");
            }
            int before = available(sku);
            if (before < quantity) {
                throw new IllegalStateException("Không đủ hàng");
            }
            stock.put(sku, before - quantity);
            Trace.log("Inventory: " + sku + " từ " + before
                    + " còn " + available(sku));
        }

        void release(String sku, int quantity) {
            Trace.log("Inventory.release(" + sku + ", " + quantity + ")");
            stock.put(sku, available(sku) + quantity);
            Trace.log("Inventory: " + sku + " trở lại "
                    + available(sku));
        }
    }

    static class PaymentDeclinedException extends RuntimeException {
        PaymentDeclinedException() {
            super("Thanh toán bị từ chối");
        }
    }

    static class PaymentGateway {
        private final boolean approved;

        PaymentGateway(boolean approved) {
            this.approved = approved;
        }

        String pay(BigDecimal amount) {
            Trace.log("PaymentGateway.pay(" + amount.toPlainString() + ")");
            if (!approved) {
                Trace.log("PaymentGateway: từ chối");
                throw new PaymentDeclinedException();
            }
            Trace.log("PaymentGateway: thành công TX-001");
            return "TX-001";
        }
    }

    static class Order {
        final String id;
        final String sku;
        final int quantity;
        final BigDecimal amount;
        final String transactionId;

        Order(String id, Cart cart, BigDecimal amount,
              String transactionId) {
            this.id = id;
            this.sku = cart.sku;
            this.quantity = cart.quantity;
            this.amount = amount;
            this.transactionId = transactionId;
        }
    }

    static class Notifier {
        void send(Order order) {
            Trace.log("Notifier.send(" + order.id + ")");
        }
    }

    // OrderService phối hợp những đối tượng khác.
    static class OrderService {
        private final Inventory inventory;
        private final PaymentGateway payment;
        private final Notifier notifier;

        OrderService(Inventory inventory, PaymentGateway payment,
                     Notifier notifier) {
            this.inventory = inventory;
            this.payment = payment;
            this.notifier = notifier;
        }

        Order checkout(Cart cart) {
            Trace.log("OrderService.checkout()");

            BigDecimal total = cart.total();
            inventory.reserve(cart.sku, cart.quantity);

            final String transactionId;
            try {
                transactionId = payment.pay(total);
            } catch (PaymentDeclinedException ex) {
                inventory.release(cart.sku, cart.quantity);
                Trace.log("OrderService: hủy do thanh toán thất bại");
                throw ex;
            }

            Order order = new Order("ORD-001", cart, total, transactionId);
            Trace.log("OrderService: tạo " + order.id);
            notifier.send(order);
            return order;
        }
    }

    public static void main(String[] args) {
        Cart cart = new Cart("BOOK", 2, new BigDecimal("100000"));
        Inventory inventory = new Inventory("BOOK", 5);
        PaymentGateway payment = new PaymentGateway(true);
        Notifier notifier = new Notifier();

        OrderService service =
                new OrderService(inventory, payment, notifier);

        Trace.log("Main: gọi checkout(cart)");
        Order order = service.checkout(cart);
        Trace.log("Main: nhận " + order.id);

        System.out.println("Tồn cuối: " + inventory.available("BOOK"));
    }
}
~~~

Để chạy:

~~~bash
javac ObjectInteractionDemo.java
java ObjectInteractionDemo
~~~

Kết quả với `new PaymentGateway(true)`:

~~~text
01 Main: gọi checkout(cart)
02 OrderService.checkout()
03 Cart.total() -> 200000
04 Inventory.reserve(BOOK, 2)
05 Inventory: BOOK từ 5 còn 3
06 PaymentGateway.pay(200000)
07 PaymentGateway: thành công TX-001
08 OrderService: tạo ORD-001
09 Notifier.send(ORD-001)
10 Main: nhận ORD-001
Tồn cuối: 3
~~~

Ví dụ cố ý dùng một sản phẩm và mã đơn/giao dịch cố định để dễ quan sát. Trong ứng dụng thực, mã đơn và mã giao dịch cần được sinh hoặc nhận từ nguồn có bảo đảm phù hợp; tồn kho, thanh toán và thông báo thường cần cơ chế lưu trữ, xử lý lỗi, giao dịch và đồng thời phức tạp hơn.

## 3. Đọc diễn tiến thực thi từ đầu đến cuối

Bảng sau mô tả các **thông điệp chính** và sự thay đổi của mô hình, thay vì chỉ nhìn vào từng dòng code rời rạc.

| Bước | Bên gọi → bên nhận | Phương thức/hoạt động | Kết quả và tác động |
| --- | --- | --- | --- |
| 1 | `Main → OrderService` | `checkout(cart)` | Bắt đầu yêu cầu đặt hàng |
| 2 | `OrderService → Cart` | `total()` | Trả về `BigDecimal("200000")` |
| 3 | `OrderService → Inventory` | `reserve("BOOK", 2)` | Giảm tồn `BOOK` từ 5 xuống 3 |
| 4 | `OrderService → PaymentGateway` | `pay(200000)` | Trả mã giao dịch `"TX-001"` |
| 5 | `OrderService` | `new Order(...)` | Tạo một đối tượng `Order` mới |
| 6 | `OrderService → Notifier` | `send(order)` | Gửi thông báo (ở đây chỉ log) |
| 7 | `OrderService → Main` | `return order` | Trả tham chiếu đến `Order` đã tạo |

Một bước có thể có **nhiều dòng log**. Ví dụ lời gọi `Inventory.reserve` được log ở bước 04, còn bước 05 log trạng thái mới sau khi xử lý. Số thứ tự trong console biểu thị **thứ tự sự kiện được ghi lại**, không nhất thiết bằng số lượng đối tượng hoặc số lượng lần gọi phương thức.

Một cách hữu ích để tự kiểm tra là viết bảng trạng thái:

| Thời điểm | `cart.quantity` | `inventory.available("BOOK")` | Thanh toán | `order` |
| --- | ---: | ---: | --- | --- |
| Trước `checkout` | 2 | 5 | Chưa gọi | Chưa có |
| Sau `cart.total()` | 2 | 5 | Chưa gọi | Chưa có |
| Sau `reserve` | 2 | 3 | Chưa gọi | Chưa có |
| Sau `pay` thành công | 2 | 3 | Đã duyệt `TX-001` | Chưa được tạo |
| Sau `new Order` | 2 | 3 | Đã duyệt | `ORD-001` |
| Sau `return` | 2 | 3 | Đã duyệt | Biến `order` ở `main` trỏ đến đơn mới |

Lưu ý: `Cart.total()` chỉ tính và trả về một giá trị; nó **không** làm giảm tồn kho. Việc giảm tồn thuộc trách nhiệm của `Inventory.reserve`. Phân biệt như vậy giúp xác định đúng nơi phát sinh lỗi.

## 4. UML sequence diagram: ai gọi ai, theo thứ tự nào?

Sequence diagram mô tả sự tương tác theo **trục thời gian từ trên xuống dưới**. Mỗi cột đứng cho một đối tượng/actor; mũi tên ngang biểu diễn lời gọi hoặc phản hồi. Đối chiếu với nhánh thành công của chương trình:

~~~mermaid
sequenceDiagram
    actor Main
    participant Service as OrderService
    participant Cart
    participant Stock as Inventory
    participant Pay as PaymentGateway
    participant Notice as Notifier

    Main->>Service: checkout(cart)
    activate Service
    Service->>Cart: total()
    Cart-->>Service: 200000
    Service->>Stock: reserve("BOOK", 2)
    Stock-->>Service: hoàn tất, tồn còn 3
    Service->>Pay: pay(200000)
    Pay-->>Service: "TX-001"
    Note over Service: new Order("ORD-001", ...)
    Service->>Notice: send(order)
    Notice-->>Service: hoàn tất
    Service-->>Main: order
    deactivate Service
~~~

Cách đọc:

- **`Main → OrderService`**: đối tượng điều phối nhận yêu cầu từ code gọi.
- **`OrderService → Cart`**: hỏi dữ liệu/tổng tiền, nhận kết quả.
- **`OrderService → Inventory`**: yêu cầu thao tác trên trạng thái tồn kho.
- **`OrderService → PaymentGateway`**: yêu cầu thanh toán và nhận mã giao dịch.
- **`OrderService → Notifier`**: chuyển đối tượng đơn hàng cho bộ thông báo.
- **Mũi tên trả về `order`**: đối tượng `Order` không tự nhân đôi khi được trả về; phương thức trả lại một **giá trị tham chiếu**.

Các mũi tên trong ví dụ là **lời gọi đồng bộ**: bên gọi chờ phương thức được gọi hoàn tất rồi thực thi tiếp. Khi dùng hàng đợi, sự kiện bất đồng bộ, callback hoặc nhiều luồng, sơ đồ và cách lập luận về thứ tự cần được điều chỉnh theo cơ chế thực tế.

## 5. Các đối tượng giữ tham chiếu tới nhau ra sao?

Trong constructor:

~~~java
OrderService service =
        new OrderService(inventory, payment, notifier);
~~~

`service` là biến tham chiếu đến instance `OrderService`. Trong object đó có các field `inventory`, `payment` và `notifier` cũng giữ tham chiếu tới ba instance được tạo trong `main`.

~~~mermaid
flowchart LR
    M["Biến service ở main"] --> S["OrderService instance"]
    V["Biến inventory ở main"] --> I["Inventory instance"]
    S -->|inventory| I
    S -->|payment| P["PaymentGateway instance"]
    S -->|notifier| N["Notifier instance"]
~~~

Vì `service.inventory` và biến `inventory` ở `main` cùng trỏ tới một instance nên:

~~~java
inventory.reserve("BOOK", 1);
~~~

và:

~~~java
// Bên trong OrderService:
this.inventory.reserve("BOOK", 1);
~~~

đều thao tác trên **cùng kho** nếu được gọi trong trạng thái hợp lệ. Đây là ví dụ về **nhiều tham chiếu cùng trỏ đến một đối tượng** phát sinh tự nhiên trong luồng tương tác.

Khi `OrderService.checkout` gọi `notifier.send(order)`, tham số `order` của `send` cũng nhận một bản sao giá trị tham chiếu đến **cùng đối tượng Order** được tạo trong `checkout`. Java truyền đối số **theo giá trị (pass-by-value)**, kể cả khi giá trị được truyền là tham chiếu.

Hai tham chiếu trỏ cùng instance không có nghĩa là chúng là cùng một *biến*. Gán lại một biến tham chiếu không tự thay giá trị tham chiếu trong biến còn lại.

## 6. Theo dõi đường đi khi có ngoại lệ: thanh toán thất bại

Nếu thay trong `main`:

~~~java
PaymentGateway payment = new PaymentGateway(false);
~~~

`PaymentGateway.pay` sẽ ném `PaymentDeclinedException`. `OrderService.checkout` bắt đúng loại ngoại lệ này, gọi `inventory.release` để hoàn trả số hàng đã giữ, rồi ném lại ngoại lệ. Không tạo `Order`, không gọi `Notifier`.

Để quan sát kết quả mà chương trình không kết thúc bằng stack trace, trong `main` thay phần gọi `checkout` và in tồn cuối bằng:

~~~java
Trace.log("Main: gọi checkout(cart)");
try {
    Order order = service.checkout(cart);
    Trace.log("Main: nhận " + order.id);
} catch (PaymentDeclinedException ex) {
    Trace.log("Main: nhận lỗi " + ex.getMessage());
}
System.out.println("Tồn cuối: " + inventory.available("BOOK"));
~~~

Kết quả nhánh này:

~~~text
01 Main: gọi checkout(cart)
02 OrderService.checkout()
03 Cart.total() -> 200000
04 Inventory.reserve(BOOK, 2)
05 Inventory: BOOK từ 5 còn 3
06 PaymentGateway.pay(200000)
07 PaymentGateway: từ chối
08 Inventory.release(BOOK, 2)
09 Inventory: BOOK trở lại 5
10 OrderService: hủy do thanh toán thất bại
11 Main: nhận lỗi Thanh toán bị từ chối
Tồn cuối: 5
~~~

~~~mermaid
sequenceDiagram
    actor Main
    participant Service as OrderService
    participant Stock as Inventory
    participant Pay as PaymentGateway

    Main->>Service: checkout(cart)
    Note over Service: total = 200000
    Service->>Stock: reserve("BOOK", 2)
    Stock-->>Service: tồn còn 3
    Service->>Pay: pay(200000)
    Pay--xService: PaymentDeclinedException
    Service->>Stock: release("BOOK", 2)
    Stock-->>Service: tồn trở lại 5
    Service--xMain: ném lại ngoại lệ
~~~

Đối chiếu **đường thành công** và **đường thất bại**:

| Điều kiện | Gọi `release`? | Tạo `Order`? | Gọi `Notifier`? | Tồn cuối |
| --- | --- | --- | --- | ---: |
| Thanh toán được duyệt | Không | Có | Có | 3 |
| Thanh toán bị từ chối | Có | Không | Không | 5 |
| Không đủ tồn ngay khi `reserve` | Không trong nhánh catch này | Không | Không | Không giảm so với ban đầu |

**Giới hạn ví dụ:** hoàn trả tồn kho ở đây chỉ mô phỏng một nhánh thất bại cụ thể trong chương trình **đơn luồng, trong bộ nhớ**. Ứng dụng thực phải xét lỗi mạng, timeout, thanh toán thành công nhưng mất phản hồi, nhiều người mua đồng thời, tính idempotent và giao dịch bền vững. Việc gọi `release` sau mọi lỗi một cách máy móc có thể sai, đặc biệt khi không biết chắc phía thanh toán đã xử lý hay chưa. Thông báo cũng thường được gửi bất đồng bộ và có cơ chế thử lại sau khi đơn hàng được lưu thành công.

## 7. Call stack giúp giải thích thứ tự chạy

Giả sử đang đứng trong `Inventory.reserve` khi vừa được gọi từ `OrderService.checkout`:

~~~text
[Đỉnh call stack]
Inventory.reserve(...)
OrderService.checkout(...)
ObjectInteractionDemo.main(...)
[Đáy call stack]
~~~

Lúc phương thức `reserve` trả về, frame tương ứng kết thúc và luồng chạy tiếp ở `checkout` sau dòng gọi `reserve`. Sau đó `checkout` gọi `PaymentGateway.pay`; trên stack xuất hiện frame của `pay`, rồi quay về `checkout` khi `pay` hoàn tất.

Call stack trả lời câu hỏi **“hiện tại phương thức nào đang gọi phương thức nào?”**. Trong khi đó:

- **Object diagram** trả lời “những instance nào tồn tại và tham chiếu tới nhau?”.
- **Sequence diagram** trả lời “những lời gọi xảy ra theo trình tự nào?”.
- **Bảng trạng thái** trả lời “giá trị trong từng đối tượng đổi ra sao?”.
- **Log/breakpoint** cung cấp bằng chứng thực thi cụ thể để so với kỳ vọng.

Không nên lẫn lộn **một frame trên stack** với **một đối tượng**. Một phương thức có thể được gọi nhiều lần trên cùng instance, và nhiều phương thức khác nhau có thể tác động lên một instance được chia sẻ.

## 8. Thực hành debug một luồng tương tác

Trong IntelliJ IDEA, Eclipse hoặc VS Code có Java Debugger, hãy đặt breakpoint tại những điểm sau:

1. `OrderService.checkout`, ngay trước dòng `cart.total()`: kiểm tra tham số `cart` đang trỏ đến instance nào và có `quantity = 2` hay không.
2. `Inventory.reserve`, trước `stock.put(...)`: kiểm tra `sku`, `quantity`, `before = 5`.
3. Sau `inventory.reserve(...)` trong `checkout`: kiểm tra kho còn 3.
4. Trong `PaymentGateway.pay`: xem `amount = 200000` và biến `approved`.
5. Ngay trước `return order`: kiểm tra `order.id`, `order.amount`, `order.transactionId` cùng tồn kho cuối.

Khi debug, **Step Into** đi vào phương thức được gọi; **Step Over** thực thi lời gọi rồi quay lại dòng tiếp theo; **Step Out** chạy đến khi phương thức hiện tại trả quyền điều khiển cho bên gọi.

Một bảng ghi chép rất hiệu quả khi điều tra lỗi:

| Thời điểm | Đối tượng đang thực thi | Method | Input | Output/exception | Trạng thái trước → sau |
| --- | --- | --- | --- | --- | --- |
| T1 | `Cart` | `total` | Không có đối số | 200000 | Không đổi |
| T2 | `Inventory` | `reserve` | BOOK, 2 | Hoàn tất | 5 → 3 |
| T3 | `PaymentGateway` | `pay` | 200000 | TX-001 | Không đổi trong ví dụ |
| T4 | `OrderService` | `checkout` | `cart` | `order` | Tạo đối tượng đơn |
| T5 | `Notifier` | `send` | `order` | Hoàn tất | Chỉ log |

Trong ứng dụng lớn, hãy bổ sung **request ID/correlation ID** vào log để nối đúng các bước của cùng một yêu cầu; nếu nhiều request chạy đồng thời, chỉ dựa vào thứ tự các dòng log có thể dẫn đến kết luận sai. Tuy nhiên, không cần log mật khẩu, số thẻ hoặc dữ liệu nhạy cảm để hiểu lời gọi đối tượng.

## 9. Những nhầm lẫn dễ mắc

### Nhầm đối tượng chịu trách nhiệm cập nhật

Nếu giá trị tồn kho sai, cần kiểm tra nơi cập nhật `Inventory`, ví dụ `reserve` và `release`, thay vì chỉ nhìn nơi `main` in ra kết quả. `main` chỉ quan sát trạng thái.

### Nhầm lời gọi trả về với việc tạo đối tượng

~~~java
Order order = service.checkout(cart);
~~~

`checkout` tạo một `Order` và trả về tham chiếu tới nó. Câu lệnh ở `main` **không tự tạo thêm một Order thứ hai**. Tương tự, truyền `order` cho `Notifier.send` không tự nhân bản đối tượng.

### Nhầm thứ tự code trong một phương thức với toàn bộ luồng

Trong `checkout`, các dòng mã chạy tuần tự, nhưng mỗi lời gọi như `reserve` lại kích hoạt mã bên trong một đối tượng khác. Muốn biết trạng thái cuối phải đi **vào bên trong các phương thức nhận lời gọi**, không chỉ đọc tên phương thức.

### Chỉ vẽ nhánh thành công

Nếu `reserve` ném `IllegalStateException`, `payment.pay` và `new Order` sẽ không chạy. Nếu `pay` ném `PaymentDeclinedException`, nhánh `catch` chạy và `Order` chưa được tạo. Sơ đồ chỉ mô tả thành công mà bỏ qua ngoại lệ có thể che mất vấn đề rất quan trọng.

### Cho rằng diagram là bằng chứng đầy đủ

Sơ đồ là mô hình do người thiết kế hoặc người đọc lập ra. Muốn xác minh chương trình thực chạy đúng sơ đồ, cần đối chiếu **mã, breakpoint, log và trạng thái**. Với luồng bất đồng bộ hoặc nhiều luồng, trình tự hoàn thành có thể khác giả định ban đầu.

## 10. Bài luyện tập và đáp án

**Bài 1.** Giỏ có `quantity = 2`, tồn ban đầu `5`. Chạy nhánh thành công, sau `reserve` còn bao nhiêu và ai thực hiện cập nhật?

**Đáp án:** Còn 3. Instance `Inventory` cập nhật trạng thái khi `OrderService` gọi `reserve("BOOK", 2)`.

**Bài 2.** Vì sao `Main` quan sát được tồn bằng 3 dù thao tác trừ tồn xảy ra trong `OrderService`?

**Đáp án:** Biến `inventory` ở `main` và field `inventory` bên trong `service` trỏ đến **cùng một instance**. `Inventory.reserve` thay đổi trạng thái instance đó.

**Bài 3.** Nếu `new PaymentGateway(false)`, lời gọi `Notifier.send` có chạy không? Vì sao?

**Đáp án:** Không. `pay` ném `PaymentDeclinedException`, `catch` trả tồn và ném lại; luồng không đến phần tạo đơn/gửi thông báo.

**Bài 4.** `OrderService` gọi `notifier.send(order)`. `Notifier` có nhận bản sao độc lập của toàn bộ `Order` không?

**Đáp án:** Không. Java truyền bản sao **giá trị tham chiếu** vào tham số, ban đầu cả bên gọi và bên nhận đều trỏ cùng đối tượng `Order`.

**Bài 5.** Nếu muốn phân biệt hai lần checkout chạy đồng thời, điều gì cần bổ sung vào trace?

**Đáp án:** Một correlation/request ID gắn với từng checkout và được truyền theo các bước; trong chương trình nhiều luồng, cần thêm thông tin thread/request tùy hạ tầng. Counter `Trace.step` trong ví dụ đơn luồng không bảo đảm mô tả đúng nhiều request đồng thời.

**Bài 6.** Khi lỗi “đã thu tiền nhưng chưa tạo đơn”, nên theo dõi những tương tác nào?

**Gợi ý đáp án:** Bắt đầu từ `PaymentGateway.pay` trả gì, có timeout/ngoại lệ không, `OrderService` xử lý gì sau đó, có gọi `new Order`, lưu đơn bền vững (nếu hệ thống thực có repository), và có nhánh thử lại/bù trừ hay không. Không suy đoán chỉ từ một dòng log “pay called”.

## Tự hệ thống hóa

Muốn phân tích một tình huống OOP, có thể lần lượt: **liệt kê các instance → tìm điểm bắt đầu → lần theo các lời gọi và giá trị trả về → ghi trạng thái trước/sau → xét nhánh lỗi → kiểm chứng bằng debugger/log → biểu diễn lại bằng sequence diagram**.

Một sơ đồ tốt luôn gắn tên phương thức và đối tượng nhận lời gọi với **một tác động cụ thể**. Chính sự kết hợp giữa luồng gọi và trạng thái đối tượng mới giúp giải thích chính xác chương trình OOP vận hành.