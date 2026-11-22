# Đặt tên lớp, thuộc tính và phương thức trong Java OOP

**Mục tiêu:** Đọc tên là đoán được **vai trò của lớp**, **ý nghĩa và đơn vị dữ liệu**, **hành vi của phương thức**, cũng như **tác dụng phụ và hợp đồng trả về**. Tên tốt làm cho code dễ đọc, giúp phân chia trách nhiệm và giảm sai sót khi dùng API. Tên không thay thế cho thiết kế tốt, nhưng là một phần quan trọng của thiết kế.

## 1. Nguyên tắc cốt lõi: tên phải kể đúng sự thật

Xét đoạn mã:

~~~java
DataManager m = new DataManager();
m.process(x);
boolean flag = m.check();
~~~

Người đọc không thể biết `DataManager` quản lý cái gì, `process()` tạo mới hay xóa dữ liệu, `check()` đang kiểm tra điều kiện nào, hay `flag` có nghĩa gì. Tên quá mơ hồ buộc người khác mở thân hàm và lần theo nhiều lớp để hiểu.

Một phiên bản rõ nghĩa hơn:

~~~java
OrderRepository orders = new InMemoryOrderRepository();
orders.insert(order);
boolean exists = orders.findById(order.orderId()).isPresent();
~~~

Ở đây, tên cho biết repository quản lý đơn hàng, `insert()` bổ sung một đơn, `findById()` tra cứu theo mã và kết quả có thể không tồn tại. Ví dụ này vẫn đòi hỏi hợp đồng nêu rõ nếu trùng mã thì làm gì, nhưng API đã dễ hiểu hơn.

**Năm câu hỏi trước khi chốt tên:**

1. **Tên thuộc khái niệm nghiệp vụ nào?** `Order`, `Cart`, `Payment` hay một hạ tầng kỹ thuật như `OrderRepository`?
2. **Tên nêu vai trò hay chỉ kiểu dữ liệu?** `remainingSeats` hữu ích hơn `number`; `userIds` hữu ích hơn `stringList`.
3. **Người gọi có đoán được hành vi không?** `cancelReservation()` rõ hơn `handle()`.
4. **Tên có phản ánh điều kiện và kết quả không?** `findById()` gợi ý việc “có thể không tìm thấy”; `requireById()` có thể biểu đạt quy ước “thiếu thì ném lỗi” nếu được tài liệu hóa.
5. **Tên có còn đúng sau thay đổi triển khai không?** `OrderRepository` cho phép đổi từ JDBC sang API; `JdbcOrderDao` mang thông tin công nghệ và chỉ phù hợp nếu chính lớp đó thật sự là adapter JDBC.

Không nên tối ưu tên chỉ để ngắn. Một tên đủ dài nhưng cụ thể thường rẻ hơn thời gian suy luận của mỗi người đọc. Ngược lại, tên dài lặp lại thông tin đã có trong ngữ cảnh cũng làm code nặng nề.

## 2. Quy ước đặt tên chuẩn trong Java

| Thành phần | Quy ước thông dụng | Ví dụ | Ghi chú |
|---|---|---|---|
| Class | `UpperCamelCase`, thường là danh từ/cụm danh từ | `ShoppingCart`, `OrderRepository` | Chỉ ra đối tượng hoặc trách nhiệm |
| Interface | `UpperCamelCase` | `PaymentGateway`, `Runnable` | Gọi theo **hợp đồng**, không bắt buộc thêm tiền tố `I` |
| Record | `UpperCamelCase` | `Money`, `OrderLine` | Tên mô tả giá trị hoặc nhóm dữ liệu |
| Enum type | `UpperCamelCase` | `OrderStatus` | Nêu một tập trạng thái/loại |
| Enum constant | `UPPER_SNAKE_CASE` | `PENDING_PAYMENT`, `PAID` | Thường là các giá trị cố định |
| Method | `lowerCamelCase`, thường là động từ/cụm động từ | `addLine()`, `findById()` | Tên mô tả hành động hoặc truy vấn |
| Field | `lowerCamelCase` | `orderId`, `remainingSeats` | Tránh tiền tố kiểu Hungary `strName`, `mName` |
| Parameter / local variable | `lowerCamelCase` | `orderId`, `customerEmail` | Có thể ngắn khi ngữ cảnh cực rõ |
| Hằng số có tên | `UPPER_SNAKE_CASE` | `MAX_RETRY_ATTEMPTS` | Với hằng số thực sự bất biến, thường `static final` |
| Package | chữ thường, tên nhóm theo miền/chức năng | `com.example.orders` | Tránh camelCase hoặc dấu gạch dưới cho package mới |
| Generic type parameter | thường một chữ hoa có nghĩa | `T`, `E`, `K`, `V`, `ID` | Với generic phức tạp, tên dài rõ nghĩa cũng được |

Đây là **quy ước** Java được cộng đồng và hệ sinh thái dùng rộng rãi, không phải mọi tên sai style đều bị compiler từ chối. Java phân biệt chữ hoa/chữ thường: `orderId` và `OrderId` là hai identifier khác nhau.

**Phân biệt `final` và hằng số:** `private final List<Order> orders` chỉ giữ nguyên **tham chiếu** tới danh sách, các phần tử vẫn có thể thêm/xóa; không nên tự động viết `ORDERS` chỉ vì có `final`. `private static final int MAX_ITEMS = 100;` mới là dạng hằng số đặt tên `UPPER_SNAKE_CASE` điển hình. Tương tự, `private static final List<String> CODES = new ArrayList<>()` có tham chiếu không đổi nhưng nội dung vẫn mutable, nên cần xét tính bất biến thực tế trước khi xem nó là hằng số.

### Từ viết tắt và thuật ngữ

Ưu tiên tên dễ đọc như `HttpClient`, `customerId`, `paymentUrl`, `parseJson()`. Các từ viết tắt đã quen như `URL`, `HTTP`, `DTO`, `ID` có thể xuất hiện, nhưng cần **thống nhất quy ước của dự án**, nhất là tên API công khai. Các thư viện Java hiện có cả tên kiểu `URL` và `URI`; không được tùy tiện đổi tên API thư viện.

Ví dụ `getURL()` và `getUrl()` có thể dẫn đến cách JavaBeans introspection suy ra tên property khác nhau ở một số trường hợp, do quy tắc decapitalize. Khi sửa code dùng reflection, serialization hoặc binding, hãy kiểm tra hành vi thực tế chứ không chỉ đổi chữ hoa.

## 3. Đặt tên lớp: ưu tiên khái niệm và trách nhiệm

### Lớp mô hình nghiệp vụ

Tên danh từ như `Invoice`, `ShoppingCart`, `OrderLine`, `BankAccount` thường nói rõ thực thể/giá trị mà đối tượng biểu diễn. Các phương thức đi kèm bảo vệ invariant của khái niệm đó.

~~~java
final class ShoppingCart {
    // Danh sách và hành vi thuộc cùng khái niệm giỏ hàng.
}

record OrderLine(String sku, int quantity) {}
~~~

Nếu tên `Cart` đã nằm trong package `com.example.checkout.cart`, không cần luôn gọi `CheckoutShoppingCartDataModel`. Cần đủ cụ thể để không lẫn với một `Cart` khác trong cùng ngữ cảnh; tránh thêm nhiều tiền tố lặp.

### Lớp chuyên cung cấp hành vi

Một số trách nhiệm không phải “thực thể” mà là cộng tác viên:

| Tên mơ hồ | Tên gợi ý | Trách nhiệm được làm rõ |
|---|---|---|
| `OrderManager` | `OrderRepository` | Lưu, truy vấn đơn hàng |
| `PaymentHelper` | `PaymentGateway` | Giao tiếp cổng thanh toán |
| `ThingProcessor` | `InvoiceCalculator` | Tính số tiền hóa đơn |
| `ReportUtil` | `CsvReportExporter` | Kết xuất báo cáo CSV |
| `DataHandler` | `InventoryReservationService` | Nghiệp vụ giữ hàng tồn |
| `EmailStuff` | `ReceiptSender` | Gửi biên nhận |

Tên đuôi `Service`, `Manager`, `Handler`, `Processor` không bị cấm; chúng chỉ trở nên yếu khi **không nói được service làm gì**. `CheckoutService` có thể là tên tốt nếu nó thực hiện một use case checkout được xác định rõ. Không ép mọi lớp thành `SomethingService`.

**Interface:** gọi bằng khả năng/hợp đồng, ví dụ `TaxPolicy`, `ShippingGateway`, `OrderRepository`. Implementation nên thể hiện sự khác biệt có ích: `JdbcOrderRepository`, `InMemoryOrderRepository`, `StripePaymentGateway`. Không cần viết `IOrderRepository`/`OrderRepositoryImpl` theo thói quen nếu tên không mang thêm thông tin; dự án hiện có convention riêng thì giữ nhất quán trong phạm vi đó.

**Ngoại lệ:** lớp có ý nghĩa lỗi như `InsufficientBalanceException` hoặc `OrderNotFoundException` cho phép caller nắm loại lỗi; đừng dùng `MyException` hay `CustomException` khi public API có thể nói cụ thể hơn.

**Class có hậu tố `Dto`/`Request`/`Response`:** phù hợp ở biên HTTP hoặc tích hợp nếu kiểu đó là dạng vận chuyển dữ liệu. Đừng dùng DTO làm domain entity một cách vô thức; một `CreateOrderRequest` không nhất thiết bảo vệ cùng invariant với `Order`.

## 4. Đặt tên thuộc tính: ý nghĩa, số lượng, đơn vị và trạng thái

Một field nên thể hiện **dữ liệu lưu trong field là gì**:

~~~java
// Khó đọc vì thiếu ý nghĩa:
private long value;
private int t;
private boolean flag;
private List<String> data;

// Cụ thể hơn trong ngữ cảnh ví dụ:
private long balanceCents;
private int retryCount;
private boolean emailVerified;
private List<String> permittedCountryCodes;
~~~

### Danh sách và số nhiều

- Một phần tử: `order`, `customer`, `selectedProduct`.
- Nhiều phần tử: `orders`, `customerIds`, `selectedProducts`.
- Một tập hợp tra cứu: `ordersById` khi là `Map<String, Order>`; tên thể hiện **khóa** được dùng.
- `pendingOrders` nói rõ bộ lọc, trong khi `orders` chỉ nói về loại phần tử.

Không cần mang tên kiểu kỹ thuật vào mọi trường như `arrayListOfOrders` vì đổi `ArrayList` sang `LinkedList`/`List` làm tên trở nên sai. Thường khai báo theo abstraction phù hợp: `List<Order> pendingOrders`.

### Đơn vị và miền giá trị

`timeout = 500` không cho biết 500 ms, giây hay phút. Có hai hướng:

~~~java
long timeoutMillis = 500L;        // Nếu API thật sự lưu con số millis
java.time.Duration timeout =
        java.time.Duration.ofMillis(500); // Tốt khi API hỗ trợ Duration
~~~

Tương tự `balanceCents` cụ thể hơn `balance` nếu dữ liệu là số nguyên đơn vị cent; `discountRate` (tỉ lệ 0–1) và `discountPercent` (0–100) **không được sử dụng thay thế** mà không có quy ước. Với tiền tệ thực tế, có thể cần kiểu `Money(amount, currency)`, `BigDecimal` và quy tắc rounding, không chỉ đổi tên field.

### Biến boolean: đặt thành mệnh đề khẳng định dễ đọc

| Khó hiểu | Gợi ý | Khi dùng |
|---|---|---|
| `flag` | `emailVerified` | Field trạng thái |
| `status` kiểu boolean | `paymentCompleted` | Một trạng thái nhị phân xác định |
| `notInvalid` | `valid` | Tránh phủ định kép |
| `check()` | `hasAvailableSeats()` | Method truy vấn điều kiện |
| `testUser()` | `canAccessResource()` | Method trả về quyền truy cập |
| `enabledOrNot` | `isEnabled()` | Getter boolean nếu theo quy ước API |

Đọc trong câu lệnh:

~~~java
if (account.isLocked()) {
    throw new IllegalStateException("Account is locked");
}

if (cart.hasItems() && payment.canBeCaptured()) {
    // Thực hiện bước tiếp theo.
}
~~~

Lưu ý: `isEnabled()` là tên method JavaBeans thường gặp cho boolean; record `record Settings(boolean enabled)` sinh accessor `enabled()`. Đừng sửa tất cả accessor record thành `getEnabled()` chỉ để giống JavaBeans; xem yêu cầu của framework và API đang có.

## 5. Đặt tên phương thức: nói rõ thao tác và hợp đồng

Phương thức làm việc nên mang một **động từ hoặc cụm hành động**; method truy vấn có thể mang tên thuộc tính hoặc mệnh đề rõ nghĩa. Tên không chỉ mô tả “thực hiện gì”, mà còn nên giúp người dùng dự đoán có thay đổi trạng thái, I/O, lỗi hoặc kết quả rỗng không.

| Method yếu | Method rõ hơn | Lợi ích |
|---|---|---|
| `process(order)` | `placeOrder(order)` | Nêu use case |
| `handle(orderId)` | `cancelOrder(orderId)` | Nêu tác động |
| `calculate(x)` | `calculateShippingFee(destination)` | Nêu giá trị được tính |
| `update(x)` | `changeDeliveryAddress(address)` | Nêu field/invariant được sửa |
| `check(orderId)` | `existsById(orderId)` | Giá trị trả về dễ hiểu |
| `get(id)` | `findById(id)` | Thể hiện truy vấn theo ID |
| `doPayment()` | `capturePayment()` | Phân biệt giữ tiền và thu tiền |
| `run()` | `generateMonthlyStatement()` | Rõ kết quả nghiệp vụ |

### Một số tiền tố hữu ích, nhưng không phải luật cứng

- `getName()` / `name()`: đọc một thuộc tính; tuân theo JavaBeans khi framework cần.
- `isLocked()`, `hasItems()`, `canSubmit()`: truy vấn boolean.
- `findById()`: thường phù hợp khi **không tìm thấy** là kết quả bình thường, ví dụ trả `Optional<T>`.
- `requireById()` hoặc `loadRequiredById()`: có thể đặt cho quy ước **không tìm thấy thì ném exception**; phải viết rõ trong contract. Không có quy tắc Java toàn cục bắt buộc `get` hay `find` xử lý lỗi theo một cách duy nhất.
- `calculateTotal()` / `subtotalAmount()`: tính toán không chủ ý tạo tác dụng phụ.
- `createOrder()`, `placeOrder()`, `cancelOrder()`: biểu đạt hành động biến đổi trạng thái.
- `save()`, `insert()`, `update()`: phải giải thích khác biệt giữa ghi mới, cập nhật, upsert, xử lý trùng khóa và transaction; chỉ đổi tên không biến hành vi thành đúng.
- `sendEmail()`, `enqueueEmail()`, `scheduleEmail()`: phân biệt đã gọi gửi, đưa vào hàng đợi và lên lịch. Nếu chỉ publish message thì gọi `enqueue`/`publish` trung thực hơn tuyên bố đã gửi thành công.
- `validate()` có thể ném ngoại lệ hoặc trả danh sách lỗi; nếu hai hành vi tồn tại, nên có tên/hợp đồng phân biệt như `isValid()` và `validateOrThrow()`.

**Đừng giấu side effect trong tên getter:** một `getBalance()` gọi API thanh toán từ xa, thay đổi trạng thái hoặc có thể tốn vài giây là điều caller dễ bất ngờ. Nếu nghiệp vụ bắt buộc truy xuất từ xa, tên như `fetchBalance()` cùng tài liệu thời gian, lỗi, cache có thể rõ hơn.

### Tránh boolean flag điều khiển hai nghiệp vụ

~~~java
// Mơ hồ: true có nghĩa gì? Khó nhớ khi đọc lời gọi.
processOrder(order, true);

// Rõ ý định hơn nếu là hai thao tác khác nhau:
orderService.submitOrder(order);
orderService.previewOrder(order);
~~~

Nếu khác biệt chỉ là tham số cấu hình hợp lệ của một nghiệp vụ, có thể dùng enum có tên:

~~~java
enum DeliveryPriority { STANDARD, EXPRESS }

shippingService.scheduleShipment(order, DeliveryPriority.EXPRESS);
~~~

Không cần tách tất cả method có tham số boolean: hãy tách khi cờ tạo hai hành vi độc lập khiến tên chung che giấu trách nhiệm.

## 6. Ví dụ hoàn chỉnh: từ tên chung chung tới API OOP dễ hiểu

Bài toán: người dùng thêm sản phẩm vào giỏ, xem tổng tạm tính và đặt đơn. Một vài tên yếu thường thấy trong code cũ:

~~~java
// Mã Java hợp lệ nhưng tên không nói rõ trách nhiệm.
class Manager {
    private java.util.List<String> data = new java.util.ArrayList<>();
    private boolean flag;

    void add(String x) { data.add(x); }
    java.math.BigDecimal calc() { return java.math.BigDecimal.ZERO; }
    void process(String x) { flag = (x != null); }
}
~~~

Người đọc không đoán được `data` là giỏ hàng hay danh sách đơn đã lưu, `flag` biểu diễn trạng thái nào, `calc()` tính gì, `process()` có ghi dữ liệu hay không.

### Thiết kế tên và trách nhiệm mới

~~~mermaid
classDiagram
    class ShoppingCart {
        -List~CartLine~ lines
        +addProduct(String, int, BigDecimal)
        +hasItems() boolean
        +snapshot() CartSnapshot
    }
    class CartLine {
        <<record>>
        +sku
        +quantity
        +unitPrice
        +lineTotal()
    }
    class CheckoutService {
        -OrderRepository orders
        +placeOrder(String, ShoppingCart) Order
    }
    class OrderRepository {
        <<interface>>
        +insert(Order)
        +findById(String) Optional
    }
    class InMemoryOrderRepository
    ShoppingCart *-- CartLine
    CheckoutService --> ShoppingCart : đọc snapshot
    CheckoutService --> OrderRepository : lưu đơn
    InMemoryOrderRepository ..|> OrderRepository
~~~

- `ShoppingCart` là danh từ biểu diễn đối tượng nghiệp vụ; `addProduct()` nói hành động, `hasItems()` nói điều kiện, `snapshot()` nói người gọi nhận **ảnh chụp dữ liệu**.
- `CartLine` là một dòng hàng có `quantity` và `unitPrice`; `lineTotal()` nói rõ tổng riêng của dòng.
- `CheckoutService.placeOrder()` nói mục tiêu use case và tác dụng chính; `OrderRepository.insert()` nói thao tác ghi mới.
- `InMemoryOrderRepository` mô tả đặc điểm triển khai; người dùng của interface không cần biết nó lưu bằng `ConcurrentHashMap`.

**Toàn bộ mã trong tệp `NamingDemo.java`, chạy bằng Java 17+:**

~~~java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

record CartLine(String sku, int quantity, BigDecimal unitPrice) {
    CartLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");
        if (sku.isBlank() || quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException("Invalid cart line");
        }
    }

    BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

// Snapshot bất biến tại thời điểm đặt đơn.
record CartSnapshot(List<CartLine> lines, BigDecimal subtotalAmount) {
    CartSnapshot {
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(subtotalAmount, "subtotalAmount");
        lines = List.copyOf(lines);
    }
}

final class ShoppingCart {
    private final List<CartLine> lines = new ArrayList<>();

    void addProduct(String sku, int quantity, BigDecimal unitPrice) {
        lines.add(new CartLine(sku, quantity, unitPrice));
    }

    boolean hasItems() {
        return !lines.isEmpty();
    }

    CartSnapshot snapshot() {
        List<CartLine> copiedLines = List.copyOf(lines);
        BigDecimal subtotalAmount = copiedLines.stream()
                .map(CartLine::lineTotal)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new CartSnapshot(copiedLines, subtotalAmount);
    }
}

record Order(String orderId, List<CartLine> lines, BigDecimal subtotalAmount) {
    Order {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(subtotalAmount, "subtotalAmount");
        if (orderId.isBlank() || lines.isEmpty()) {
            throw new IllegalArgumentException("Invalid order");
        }
        lines = List.copyOf(lines);
    }
}

interface OrderRepository {
    void insert(Order order);              // Trùng mã thì báo lỗi
    Optional<Order> findById(String orderId); // Không thấy -> Optional.empty()
}

final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, Order> ordersById =
            new ConcurrentHashMap<>();

    @Override
    public void insert(Order order) {
        Objects.requireNonNull(order, "order");
        Order previous = ordersById.putIfAbsent(order.orderId(), order);
        if (previous != null) {
            throw new IllegalStateException("Order already exists");
        }
    }

    @Override
    public Optional<Order> findById(String orderId) {
        return Optional.ofNullable(ordersById.get(orderId));
    }
}

final class CheckoutService {
    private final OrderRepository orders;

    CheckoutService(OrderRepository orders) {
        this.orders = Objects.requireNonNull(orders, "orders");
    }

    Order placeOrder(String orderId, ShoppingCart cart) {
        Objects.requireNonNull(cart, "cart");

        CartSnapshot cartSnapshot = cart.snapshot();
        if (cartSnapshot.lines().isEmpty()) {
            throw new IllegalArgumentException("Cannot place an empty cart");
        }

        Order order = new Order(orderId,
                cartSnapshot.lines(), cartSnapshot.subtotalAmount());

        orders.insert(order);
        return order;
    }
}

public class NamingDemo {
    public static void main(String[] args) {
        ShoppingCart cart = new ShoppingCart();
        cart.addProduct("JAVA-BOOK", 2, new BigDecimal("125000"));
        cart.addProduct("NOTEBOOK", 1, new BigDecimal("30000"));

        OrderRepository orders = new InMemoryOrderRepository();
        CheckoutService checkout = new CheckoutService(orders);

        Order placedOrder = checkout.placeOrder("ORD-42", cart);

        System.out.println(placedOrder.subtotalAmount()); // 280000
        System.out.println(orders.findById("ORD-42").isPresent()); // true
    }
}
~~~

~~~bash
javac NamingDemo.java
java NamingDemo
~~~

Kết quả dự kiến:

~~~text
280000
true
~~~

Trong ví dụ:

1. `orderId` là **mã đơn**, `sku` là **mã hàng**, `quantity` là **số lượng**, `unitPrice` là **đơn giá**. Không dùng các tên `str1`, `x`, `val`.
2. `CartSnapshot` mô tả dữ liệu sao chép tại thời điểm đặt đơn. `snapshot()` dùng cùng một danh sách đã sao chép để tính subtotal, tránh tính tổng từ một nguồn khác so với danh sách được lưu.
3. `OrderRepository.insert()` đúng với hành vi từ chối trùng ID qua `putIfAbsent`, còn `findById()` thể hiện khả năng trả về `Optional.empty()`.
4. `CheckoutService.placeOrder()` trả về `Order` đã được ghi, nên caller đặt tên biến `placedOrder` thay vì `result` chung chung.
5. `BigDecimal` dùng cho phép tính tiền trong ví dụ, tránh phép tính tiền bằng `double`. Ứng dụng thật còn cần currency, rounding/scale policy, và quy tắc thuế/chiết khấu.

Đây là mẫu minh họa **đặt tên và ranh giới lớp**, không phải hệ thống đặt hàng đầy đủ: `ShoppingCart` mutable chưa bảo đảm thread safety khi nhiều luồng cùng thêm hàng; repository bộ nhớ không bền vững qua lần chạy; quy tắc duplicate ID, transaction và xác thực cần được định nghĩa thêm khi triển khai thật.

**Vì sao các tên ăn khớp nhau?** Ở lời gọi `checkout.placeOrder("ORD-42", cart)` có thể dự đoán đây là tác vụ tạo đơn; `orders.findById(...)` là truy vấn; `cart.snapshot()` tạo một bản dữ liệu ổn định để truyền sang đơn mới. Người đọc không phải mở từng thân hàm để tìm chức năng cơ bản.

## 7. Tên tốt cần đi cùng API và tính nhất quán

Một tên nghe “hay” không bù được hợp đồng sai:

~~~java
// Sai về mặt ý nghĩa: tên nói truy vấn nhưng thực tế xóa dữ liệu.
Order findById(String id) {
    return deleteOrderAndReturnOldValue(id);
}
~~~

Nếu truy vấn có side effect, cần xem lại thiết kế, không chỉ sửa tên cho hấp dẫn. Tên là **cam kết** với caller.

Trong cùng một lớp, tránh hai tên cho một ý nghĩa nếu không có khác biệt thật:

~~~java
findOrder(id);
lookupOrder(id);
getOrder(id);
fetchOrder(id);
~~~

Nếu bốn method có bốn hành vi khác nhau, cần tài liệu chỉ rõ: truy vấn bộ nhớ, truy vấn DB, fetch HTTP, hoặc ném lỗi khi thiếu. Nếu chỉ là bí danh lịch sử, giảm số bí danh để API dễ học hơn.

### Có nên thêm tên class vào tên method?

~~~java
// Lặp thừa ngữ cảnh:
cart.addCartProduct(product);
orderRepository.findOrderByOrderId(orderId);

// Tự nhiên hơn khi class đã cho biết bối cảnh:
cart.addProduct(product);
orderRepository.findById(orderId);
~~~

Tuy nhiên, `OrderRepository.findByCustomerId()` có thông tin quan trọng ở `CustomerId` vì nó phân biệt kiểu truy vấn. Không xóa thông tin chỉ để tên ngắn.

### Tên phương thức có quan hệ với exception và null

Nếu một method có thể không tìm thấy dữ liệu, hãy chọn và thực hiện **một hợp đồng nhất quán**:

~~~java
Optional<Order> findById(String orderId);  // Không tìm thấy -> empty()

Order requireById(String orderId);          // Không tìm thấy -> exception
~~~

Đây là **quy ước API được thiết kế**, không phải chuẩn Java bắt buộc. `Optional` hữu ích với kết quả “có hoặc không”; không cần bọc mọi biến hoặc field trong `Optional`. Nêu rõ lỗi từ chối và tác động của việc ghi dữ liệu, nhất là API public.

## 8. Đặt tên tham số, biến cục bộ và biến vòng lặp

Tên biến nên tỷ lệ với **phạm vi sử dụng**:

~~~java
// i là hợp lý khi chỉ là index của vòng lặp ngắn:
for (int i = 0; i < orderLines.size(); i++) {
    System.out.println(orderLines.get(i));
}

// Trong logic nghiệp vụ, hãy nói vai trò:
for (OrderLine orderLine : orderLines) {
    // ...
}
~~~

Với dữ liệu chuyển đổi, tên đầu vào và kết quả nên mô tả sự khác nhau:

~~~java
String rawEmail = request.email();
String normalizedEmail = rawEmail.strip().toLowerCase(java.util.Locale.ROOT);
~~~

Nhưng đừng chọn `normalizedEmail` nếu nghiệp vụ chưa định nghĩa việc hạ chữ hoa có hợp lệ cho toàn bộ email hay không; nhiều hệ thống thường chỉ lowercase miền (domain), và chính sách so sánh email cần nhất quán. Ví dụ trên minh họa **đặt tên dữ liệu trước/sau biến đổi**, không phải quy tắc chuẩn hóa email áp dụng cho mọi hệ thống.

Một tham số như `timeoutMillis` tốt hơn `time` nếu API chỉ chấp nhận mili giây; nếu dùng `Duration timeout` thì kiểu dữ liệu đã chứa thông tin đơn vị, tên `timeout` là đủ.

Tránh tên dễ nhầm về số học: `total` là tổng của gì, bao gồm thuế chưa? Trong thanh toán, `subtotalAmount`, `taxAmount`, `shippingFee`, `grandTotalAmount` có thể là những khái niệm khác nhau. Đừng gom tất cả thành `amount` nếu chúng đồng thời xuất hiện trong cùng phương thức.

## 9. JavaBeans, record, ORM và serialization

Đặt tên không chỉ ảnh hưởng người đọc. Một số công cụ suy ra **property names**, tên bean hoặc tên cột từ code.

### JavaBeans getter/setter

~~~java
public final class CustomerView {
    private String displayName;
    private boolean active;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }

    public boolean isActive() {
        return active;
    }
}
~~~

Nhiều framework JavaBeans nhận diện property `displayName` từ `getDisplayName()` và `active` từ `isActive()`. Tuy nhiên, behavior thực tế còn phụ thuộc thư viện/phiên bản và annotation. Không đổi chữ ký getter public tùy hứng khi có client reflection.

### Record accessor

~~~java
public record CustomerSummary(String customerId, boolean active) {}
~~~

Record tự tạo accessor `customerId()` và `active()`, không tự tạo `getCustomerId()` hoặc `isActive()`. Người dùng library cần biết kiểu là record và framework hỗ trợ record ở phiên bản nào.

### API/ORM/JSON đã phát hành

Nếu REST payload chứa field `customer_id` nhưng Java field là `customerId`, có thể đặt mapping tường minh qua annotation/mapper thay vì buộc mọi tên Java trùng định dạng JSON:

~~~java
// Ví dụ khái niệm với Jackson:
record CustomerDto(
    @com.fasterxml.jackson.annotation.JsonProperty("customer_id")
    String customerId
) {}
~~~

Tương tự, JPA có thể suy ra tên cột hoặc được cấu hình với `@Column(name = "...")`; đổi tên Java field có thể gây thay đổi mapping nếu không khóa tên theo schema. Spring cũng có thể tạo tên bean mặc định dựa trên tên class; thay tên có thể làm thay đổi wiring bằng `@Qualifier` hoặc theo tên.

**Điểm quan trọng:** Rename ở public API có thể làm hỏng source compatibility, binary compatibility, reflection, JSON contract, database mapping, cấu hình Spring, tài liệu, log parsing và script bên ngoài. Nếu mới chỉ refactor một private field không bị đọc bằng reflection, phạm vi tác động thường nhỏ hơn nhiều.

## 10. Đổi tên an toàn trên codebase đang sử dụng

Cách làm với một API tên cũ `createOrder()` cần đổi thành `placeOrder()`:

1. **Hiểu hành vi hiện tại:** tạo đối tượng trong bộ nhớ, lưu DB hay thực hiện cả workflow? Chỉ đổi tên khi tên mới đúng với semantics.
2. **Tìm usage và ranh giới công khai:** compile-time callers, overloads, method references, reflection, serialization, plugin SPI, cấu hình Spring/ORM và script.
3. **Dùng Rename Symbol của IDE:** để cập nhật symbol và reference; kiểm tra thêm những chỗ dùng chuỗi ký tự mà tool không tự nhận diện.
4. **Nếu API còn client cũ:** có thể giữ wrapper tương thích có ghi chú deprecated trong một chu kỳ migration.
5. **Chạy build/test:** compile tất cả module liên quan, test reflection/JSON/database mapping nếu có; kiểm tra API docs, ví dụ, log và metric.
6. **Khi xóa tên cũ:** chỉ thực hiện theo chính sách versioning, kiểm tra các consumer đã di chuyển.

Ví dụ wrapper công khai:

~~~java
public final class OrderApplicationService {
    public Order placeOrder(String orderId, ShoppingCart cart) {
        // Triển khai đúng use case ở đây.
        throw new UnsupportedOperationException("Illustrative body");
    }

    /** @deprecated Use {@link #placeOrder(String, ShoppingCart)}. */
    @Deprecated(since = "2.1", forRemoval = false)
    public Order createOrder(String orderId, ShoppingCart cart) {
        return placeOrder(orderId, cart);
    }
}
~~~

Đoạn wrapper chỉ minh họa **chiến lược migration** và không dùng trực tiếp với `NamingDemo.java` (trong ví dụ đầy đủ, class điều phối mang tên `CheckoutService`). Khi giữ wrapper, việc gọi `createOrder()` vẫn chạy theo contract cũ nếu `placeOrder()` có cùng ngữ nghĩa; việc đổi tên không cho phép thay đổi hành vi một cách âm thầm. Nếu hệ thống dùng các method name làm protocol hoặc key serialized, cần migration riêng.

## 11. Đo chất lượng tên bằng cách review và kiểm thử

Tên khó đo bằng một chỉ số tự động vì phụ thuộc ngữ cảnh nghiệp vụ. Có thể tự review bằng các câu hỏi:

| Câu hỏi review | Ví dụ đạt | Dấu hiệu cần sửa |
|---|---|---|
| Class thể hiện một vai trò rõ? | `ReceiptSender` | `GeneralHelper` làm 6 việc khác nhau |
| Field có ý nghĩa và đơn vị? | `retryDelayMillis` | `delay` mà không ai biết đơn vị |
| Boolean đọc như câu hỏi? | `hasOutstandingInvoices()` | `check()` |
| Method bộc lộ tác động? | `cancelSubscription()` | `processSubscription()` |
| Kết quả “có thể thiếu” rõ? | `findById(): Optional<Order>` | `get()` âm thầm trả null |
| Tên public không lộ detail không cần thiết? | `OrderRepository` | `JdbcMysqlV2Util` trong API nghiệp vụ |
| Tên đồng bộ với thực thi? | `insert()` báo trùng khóa | `find()` lại xóa dữ liệu |

Tên test cũng là tài liệu. Với JUnit Jupiter 5, dùng tên mô tả **kịch bản và kết quả**:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;
import java.math.BigDecimal;

class NamingDemoTest {
    @Test
    void placingOrderStoresAnImmutableCartSnapshot() {
        OrderRepository repository = new InMemoryOrderRepository();
        CheckoutService checkout = new CheckoutService(repository);
        ShoppingCart cart = new ShoppingCart();
        cart.addProduct("BOOK", 2, new BigDecimal("100"));

        Order placedOrder = checkout.placeOrder("O-1", cart);
        cart.addProduct("PEN", 1, new BigDecimal("10"));

        assertEquals(1, placedOrder.lines().size());
        assertEquals(0, new BigDecimal("200")
                .compareTo(placedOrder.subtotalAmount()));
        assertEquals(placedOrder, repository.findById("O-1").orElseThrow());
    }

    @Test
    void insertingDuplicateOrderIdIsRejected() {
        OrderRepository repository = new InMemoryOrderRepository();
        CheckoutService checkout = new CheckoutService(repository);

        ShoppingCart cart = new ShoppingCart();
        cart.addProduct("BOOK", 1, BigDecimal.TEN);

        checkout.placeOrder("O-2", cart);

        assertThrows(IllegalStateException.class,
                () -> checkout.placeOrder("O-2", cart));
    }

    @Test
    void addingLineWithInvalidQuantityIsRejected() {
        ShoppingCart cart = new ShoppingCart();

        assertThrows(IllegalArgumentException.class,
                () -> cart.addProduct("BOOK", 0, BigDecimal.ONE));
    }
}
~~~

Tên `placingOrderStoresAnImmutableCartSnapshot` tự nói tình huống kiểm thử; `insertingDuplicateOrderIdIsRejected` nói rõ điều kiện lỗi. Chạy test này cần JUnit Jupiter 5 được cấu hình trong project. Các test kiểm tra **hành vi thật** của ví dụ, không chỉ kiểm tra rằng code có tên method mong muốn.

Lưu ý về từ “immutable”: `Order.lines()` chứa bản sao danh sách không sửa được qua API và `CartLine` là record bất biến với các thành phần `String`, `int`, `BigDecimal` (đều bất biến). Vì vậy ảnh chụp trong **ví dụ này** giữ nguyên. Với bản sao danh sách chứa phần tử mutable, `List.copyOf` không tự tạo deep copy, nên tên `immutableSnapshot` sẽ gây hiểu nhầm nếu không có biện pháp bổ sung.

## 12. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Hướng xử lý |
|---|---|---|
| Dùng `Manager`, `Helper`, `Util` cho nhiều việc không liên quan | Khó xác định trách nhiệm lớp | Đặt tên theo capability/domain, xem lại cohesion |
| Dùng `data`, `temp`, `flag` trong scope lớn | Người đọc phải lần theo nhiều dòng | Nêu vai trò và trạng thái: `pendingOrders`, `paymentCaptured` |
| Tên phương thức che giấu I/O hoặc thay đổi trạng thái | Caller bất ngờ về hiệu năng và lỗi | Đặt tên có nghĩa hoặc ghi contract rõ |
| Viết tắt không thống nhất | Khó tìm kiếm và nhận biết cùng khái niệm | Lập từ điển thuật ngữ và convention chung |
| Thêm kiểu cụ thể vào tên domain không cần thiết | Tên sai khi đổi implementation | Đặt theo ý nghĩa, để type declaration làm phần còn lại |
| Tên dài lặp lại class/package | API khó đọc | Xóa phần trùng mà không xóa ý nghĩa |
| Đổi getter/DTO public mà không kiểm tra mapping | Lỗi JSON, bean binding, binary compatibility | Kiểm thử biên, migration/versioning |
| Tách một hành vi thành nhiều tên đồng nghĩa | API khó học, nhiều alias tồn tại | Một tên chính, deprecated wrapper tạm thời nếu cần |
| Trả kết quả trái ngụ ý của tên | Vi phạm kỳ vọng caller | Đồng bộ hợp đồng, method name và implementation |

## 13. Bài tập thiết kế tên theo miền nghiệp vụ

Một chương trình đặt lịch đang có API sau:

~~~java
class ProcessManager {
    private int n;
    private boolean f;
    private java.util.List<String> values;

    void doWork(String x);
    boolean check(String x);
    void execute(String x, boolean flag);
    String get(String x);
}
~~~

**Giả định nghiệp vụ** để tránh đoán mò: hệ thống quản lý chỗ ngồi trong lớp học. `n` là số chỗ còn lại; `f` cho biết lớp đã đóng đăng ký; `values` là các mã học viên đã ghi danh. `doWork(studentId)` ghi danh học viên; `check(studentId)` kiểm tra học viên đã ghi danh; `execute(studentId, flag)` thêm hoặc hủy ghi danh tùy flag; `get(studentId)` trả về mã xác nhận nếu học viên có đăng ký.

Hãy thực hiện:

1. Đề xuất tên class theo một trách nhiệm, ví dụ `ClassEnrollment` nếu nó giữ và bảo vệ danh sách học viên; tránh dùng `Manager` khi không cần.
2. Đổi fields thành `remainingSeats`, `registrationClosed` và `enrolledStudentIds` hoặc chọn cấu trúc dữ liệu phù hợp để không cho phép đăng ký trùng.
3. Tạo các phương thức thể hiện hành vi `enrollStudent()`, `cancelEnrollment()`, `isEnrolled()`, `findConfirmationCode()` (nếu không thấy là trường hợp bình thường, cân nhắc `Optional<String>`); thay method cờ boolean bằng hai hành vi rõ.
4. Ghi invariants: không đăng ký trùng, không âm số chỗ, không đăng ký khi đóng, hủy phải cập nhật số chỗ.
5. Viết test tên theo hành vi, chẳng hạn `enrollingStudentDecreasesAvailableSeats()`, `enrollingTwiceIsRejected()`, `closedRegistrationRejectsEnrollment()`.
6. Kiểm tra mọi tên còn đúng với hành vi đã triển khai. Nếu xác nhận chỉ được tạo khi đăng ký thành công, tên `findConfirmationCode()` không được che giấu việc tự động tạo đăng ký mới.

**Tự đánh giá:** Người chưa biết code có thể đọc lời gọi method và đoán được tác động chính không? Tên có thể dùng ổn định khi thay danh sách bằng database không? API có phân biệt rõ truy vấn với thao tác làm đổi trạng thái không?

---

**Ghi nhớ:** Đặt tên tốt là **một quyết định thiết kế**. Class nói rõ *đối tượng là gì/đảm nhận gì*, field nói rõ *dữ liệu và đơn vị*, method nói rõ *hành vi và hợp đồng*. Tên càng gần ngôn ngữ nghiệp vụ, nhất quán với Java và trung thực với tác dụng thực tế, code càng dễ đọc, kiểm thử và thay đổi.