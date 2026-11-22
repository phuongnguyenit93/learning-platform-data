# Sơ đồ lớp UML: thành viên và quan hệ trong thiết kế OOP Java

> **Mục tiêu:** Đọc, vẽ và kiểm tra sơ đồ lớp (*UML class diagram*) gồm tên lớp, thuộc tính, phương thức, phạm vi truy cập, kiểu dữ liệu, bội số và các quan hệ giữa lớp. Biết chuyển sơ đồ thành Java và nhận ra những điều sơ đồ chỉ **mô tả** chứ Java/UML không tự thực thi.

## 1. Sơ đồ lớp giúp trả lời câu hỏi nào?

Một sơ đồ lớp là **mô hình cấu trúc tĩnh**: hệ thống có những khái niệm nào, mỗi khái niệm có trạng thái và hành vi gì, và các khái niệm liên hệ với nhau như thế nào.

Chẳng hạn với ứng dụng bán hàng, yêu cầu “khách hàng đặt đơn, mỗi đơn chứa nhiều dòng hàng, mỗi dòng chọn một sản phẩm, thanh toán qua cổng thanh toán” cần trả lời:

- `Customer`, `Order`, `OrderLine`, `Product` nên có những dữ liệu nào?
- Ai **sở hữu** các dòng đơn hàng, ai chỉ **tham chiếu** đến sản phẩm?
- Một khách hàng có thể có bao nhiêu đơn? Một đơn có thể chưa có dòng khi còn là bản nháp không?
- Những hành vi nào cần đặt vào `Order` để bảo vệ quy tắc nghiệp vụ?
- `CheckoutService` phụ thuộc vào `PaymentGateway` như thế nào, và implementation thay thế được bằng cách nào?

Sơ đồ lớp hỗ trợ **trao đổi thiết kế, phân chia trách nhiệm, nhận diện liên kết và review kiến trúc**. Nó không phải sơ đồ tuần tự thực thi: muốn mô tả thứ tự gọi khi checkout, dùng *sequence diagram* hoặc *activity diagram* thích hợp hơn.

Sơ đồ có thể xuất hiện ở ba mức:

| Mức mô hình | Trọng tâm | Chi tiết nên thể hiện |
|---|---|---|
| **Phân tích miền nghiệp vụ** | Các khái niệm và quy tắc | `Order` chứa `OrderLine`; `Customer` đặt `Order` |
| **Thiết kế phần mềm** | Trách nhiệm, API, phụ thuộc | `Order.addLine(...)`, `PaymentGateway.charge(...)`, bội số |
| **Triển khai** | Cấu trúc code gần với Java | visibility, kiểu cụ thể, constructor, collection, interface, static |

Đừng đưa mọi getter, setter, DTO, kiểu thư viện và dependency hạ tầng vào một sơ đồ phân tích đơn giản. Chỉ đưa vào những thành viên và quan hệ cần thiết để giải thích quyết định thiết kế của sơ đồ đó.

## 2. Hình hộp lớp gồm những thành viên nào?

Cách vẽ phổ biến dùng một hình chữ nhật chia ba ngăn: **tên lớp**, **thuộc tính**, **phương thức**.

~~~text
┌──────────────────────────────────────┐
│                Order                 │  (1) Tên lớp
├──────────────────────────────────────┤
│ - id: String                         │  (2) Thuộc tính
│ - lines: List<OrderLine>             │
│ - status: OrderStatus                │
├──────────────────────────────────────┤
│ + addLine(p: Product, qty: int): void│  (3) Phương thức
│ + totalCents(): long                 │
│ + confirm(): void                    │
└──────────────────────────────────────┘
~~~

Các quy ước UML thường dùng:

- **Tên lớp** ở ngăn trên cùng; lớp trừu tượng có thể viết nghiêng hoặc gắn nhãn `«abstract»`.
- **Thuộc tính** biểu diễn trạng thái: `visibility name: Type [multiplicity] = defaultValue {property}`. Không cần mọi thành phần trong một sơ đồ.
- **Phương thức/operation** biểu diễn dịch vụ/hành vi: `visibility name(parameter: Type = default): ReturnType`. Có thể có nhiều tham số.
- Có thể **ẩn ngăn** hoặc ẩn thành viên không liên quan để sơ đồ dễ đọc; đó là thay đổi mức chi tiết trình bày, không có nghĩa lớp không có những phương thức ấy.
- UML phân biệt *operation* (hợp đồng có thể gọi) với *method* (cách triển khai). Trong tài liệu hướng Java, người học thường gọi chung là “phương thức”, nhưng không nên suy diễn rằng sơ đồ luôn mô tả body của phương thức.

### Ký hiệu phạm vi truy cập

| UML | Ý nghĩa | Java gần tương ứng |
|---|---|---|
| `+` | Public | `public` |
| `-` | Private | `private` |
| `#` | Protected | `protected` |
| `~` | Package visibility | Không ghi modifier (package-private) |

Một điểm dễ nhầm: Java `protected` cho phép truy cập trong cùng package và từ subclass theo những quy tắc riêng; không thể xem nó đồng nhất hoàn toàn với mọi đặc tả truy cập trong mọi ngôn ngữ UML.

Để mô hình hóa **thuộc tính dẫn xuất**, UML thường dùng dấu `/` trước tên, ví dụ `/totalCents: long`: giá trị tính từ các dòng hàng, không nhất thiết có field `totalCents` được lưu. Với giá trị bất biến/read-only, có thể dùng thuộc tính ràng buộc như `{readOnly}`. Thành viên `static` thường được **gạch dưới** trong UML chuẩn; ở code Java tương ứng `static`. Tool vẽ có thể cung cấp cú pháp riêng cho các biểu diễn này, nên cần biết giới hạn của công cụ.

### Ví dụ UML bằng Mermaid

~~~mermaid
classDiagram
    class Order {
        -String id
        -List~OrderLine~ lines
        -OrderStatus status
        +addLine(Product product, int quantity) void
        +totalCents() long
        +confirm() void
    }
~~~

Mermaid phù hợp README vì có thể giữ sơ đồ cùng phiên bản với tài liệu. Tuy nhiên một số tính năng UML chi tiết, đặc biệt định dạng text, thuộc tính phái sinh hay constraint phức tạp, có thể không được thể hiện chính xác bằng mọi renderer Mermaid. Với các chi tiết quan trọng, hãy bổ sung mô tả bằng văn bản ngay bên cạnh.

## 3. Đọc thuộc tính và operation một cách chính xác

Các dòng thuộc tính minh họa:

~~~text
- id: UUID
- capacity: int = 30
- members: Set<Member> [0..*]
- /remainingSeats: int {readOnly}
~~~

Diễn giải:

- `id` có kiểu định danh `UUID` và được che giấu phía ngoài.
- `capacity` có giá trị mặc định trong mô hình là 30 (không đồng nghĩa Java chắc chắn đã gán 30 nếu code khác sơ đồ).
- `members` giữ nhiều tham chiếu `Member`; multiplicity `[0..*]` biểu thị số lượng kết quả/thành phần mong đợi trong mô hình.
- `remainingSeats` là giá trị **tính ra** và chỉ đọc; code Java có thể triển khai bằng method `remainingSeats()` thay vì field.

Các dòng phương thức minh họa:

~~~text
+ enroll(student: Student): EnrollmentReceipt
+ findById(id: UUID): Optional<Member>
- validateCapacity(requested: int): void
# onStatusChanged(old: Status, next: Status): void
~~~

UML đặt **tên tham số trước kiểu**, trong khi Java viết `Type parameterName`. Ví dụ:

~~~java
public EnrollmentReceipt enroll(Student student) {
    // implementation
    throw new UnsupportedOperationException("Example signature only");
}
~~~

`Optional<Member>` là kiểu Java của **kết quả trả về**, không phải bội số trên association UML. Không nên suy luận từ `Optional` rằng entity bắt buộc được lưu trữ dưới dạng một collection, hay từ `List<>` rằng quan hệ bắt buộc là aggregation.

### Interface, abstract class, enum

~~~mermaid
classDiagram
    class PaymentGateway {
        <<interface>>
        +charge(String orderId, long amountCents) void
    }
    class AbstractDiscountPolicy {
        <<abstract>>
        +discount(long amount) long
    }
    class OrderStatus {
        <<enumeration>>
        DRAFT
        CONFIRMED
    }
~~~

Với Java:

- `interface` xác định hợp đồng hành vi; lớp cụ thể dùng `implements`.
- `abstract class` có thể chứa trạng thái và phương thức đã triển khai, đồng thời khai báo abstract method.
- `enum` là tập giá trị hữu hạn có thể sở hữu hành vi; đưa vào sơ đồ nếu trạng thái chuyển đổi hoặc giá trị được giới hạn là phần quan trọng của thiết kế.
- Không nhất thiết phải tạo abstract class hoặc interface cho mọi class. Chỉ dùng khi cần hợp đồng chung hoặc điểm thay thế có ý nghĩa.

## 4. Bảng phân biệt các loại quan hệ UML

Đầu mũi tên và hình thoi chứa ý nghĩa khác nhau; **không nên dùng mọi loại đường chỉ để trang trí**.

| Quan hệ | Dấu hiệu UML / Mermaid | Ý nghĩa | Java thường gặp |
|---|---|---|---|
| **Association** (liên kết) | `--` hoặc `-->` | Đối tượng có liên kết với đối tượng khác | Field/tham chiếu hoặc mô hình nghiệp vụ |
| **Shared aggregation** (tập hợp) | `o--` | Toàn thể–bộ phận theo nghĩa gom nhóm, quyền sở hữu không mạnh | `Team` tham chiếu `Employee` độc lập |
| **Composition** (hợp thành) | `*--` | Toàn thể sở hữu part; part thuộc tối đa một composite tại một thời điểm | `Order` sở hữu `OrderLine` |
| **Generalization** (kế thừa) | `<|--` | Subclass là một dạng của superclass | `extends` |
| **Realization** (hiện thực hợp đồng) | `<|..` | Lớp hiện thực interface | `implements` |
| **Dependency** (phụ thuộc) | `<..` / `..>` | Một phần tử sử dụng phần tử khác để định nghĩa/thực hiện | Tham số, local variable, method call |
 
Đặc trưng nên ghi nhớ:

**Association:** Quan hệ cấu trúc hai đối tượng có liên hệ. Đường **không mũi tên** biểu thị association nhưng không tự mô tả hướng điều hướng; một mũi tên chỉ khả năng điều hướng/hướng quan hệ trong cách biểu diễn. **Không mặc định hai phía phải giữ field tham chiếu nhau.**

**Aggregation:** Hình thoi **rỗng ở phía toàn thể**, ví dụ đội nhóm và nhân viên. Chuẩn UML dành cho shared aggregation ít ngữ nghĩa ràng buộc hơn composition; nếu không có nhu cầu nhấn mạnh whole–part, association thường rõ và ít gây hiểu nhầm hơn.

**Composition:** Hình thoi **đặc ở phía whole**. Part chịu quan hệ sở hữu mạnh; không được đồng thời thuộc hai composite. Chính luật nghiệp vụ và API phải bảo vệ điều này. Trong Java, GC không tự “xóa part ngay lúc whole bị xóa”; nếu dùng DB, cascade/orphan removal cũng phải cấu hình có chủ đích.

**Generalization:** Mũi **tam giác rỗng chỉ về superclass**. Quan hệ `Car extends Vehicle` chỉ hợp lý khi `Car` thực sự tuân thủ hợp đồng của `Vehicle`. Kế thừa để “vay code” thường làm thiết kế khó bảo trì.

**Realization:** Đường **nét đứt kết thúc bằng tam giác rỗng** về interface. `StripeGateway implements PaymentGateway` là minh họa, nhưng không ngụ ý mọi interface phải có nhiều implementation.

**Dependency:** Đường **nét đứt và mũi tên thường** chỉ về phía được sử dụng. Nó thường mô tả việc lớp nhận tham số hoặc gọi API khác mà **không nhất thiết lưu tham chiếu dài hạn**. Đừng tự đồng nhất dependency với composition.

Một cách nhớ ngắn: **đường liên kết** thể hiện quan hệ đối tượng, **hình thoi** thể hiện toàn thể–bộ phận, **tam giác rỗng** thể hiện kiểu cha/hợp đồng, **đường nét đứt đơn giản** thể hiện phụ thuộc sử dụng.

## 5. Bội số, tên vai trò, hướng điều hướng

Multiplicity diễn tả có bao nhiêu đối tượng ở một đầu liên kết cho **một đối tượng phía kia**.

| Bội số UML | Cách đọc |
|---|---|
| `1` | Chính xác một |
| `0..1` | Không có hoặc một |
| `*` hay `0..*` | Không hoặc nhiều |
| `1..*` | Ít nhất một |
| `2..5` | Từ hai đến năm (bao gồm hai đầu) |

Ví dụ:

~~~mermaid
classDiagram
    Customer "1" <-- "0..*" Order : places
    Order "1" *-- "0..*" OrderLine : owns
    OrderLine "0..*" --> "1" Product : refers to
~~~

Cách hiểu các quan hệ:

- **Một `Order` thuộc về đúng một `Customer`**; một khách hàng có thể có 0 hoặc nhiều đơn.
- **Một `OrderLine` thuộc về đúng một `Order`**; đơn nháp có thể có 0 dòng. Nếu đơn đã xác nhận phải có từ một dòng trở lên, đó là một **ràng buộc trạng thái** cần kiểm tra riêng.
- **Mỗi `OrderLine` tham chiếu một `Product`**; một sản phẩm có thể được chọn trong nhiều dòng của nhiều đơn hàng. Bản ghi sản phẩm độc lập và **không** là part bị xóa cùng đơn.

**Hình thoi ở phía `Order`**, không phải phía `OrderLine`. Với những quan hệ có role name (ví dụ `customer`, `lines`) có thể đặt tên tại đầu association để truyền đạt mục đích; mỗi công cụ dựng sơ đồ có mức hỗ trợ nhãn role khác nhau.

Ví dụ API Java tương ứng:

~~~java
final class Order {
    private final Customer customer;          // Order --> 1 Customer
    private final List<OrderLine> lines;       // Order *-- 0..* OrderLine
    // ...
}
~~~

Trong Java, **cú pháp field không tự enforce bội số**: `Customer customer` vẫn có thể null nếu constructor cho phép; `List<OrderLine>` vẫn có thể chứa phần tử được tạo từ đơn khác nếu API không kiểm tra. Muốn bảo vệ mô hình, phải kiểm tra invariant, ngăn sửa collection trực tiếp, và bổ sung constraint ở DB nếu cần.

## 6. Ví dụ thiết kế hoàn chỉnh: khách hàng – đơn hàng – thanh toán

Yêu cầu giả định:

1. Khách hàng có thể tạo nhiều đơn; đơn thuộc một khách hàng.
2. Mỗi đơn giữ **các dòng riêng** có sản phẩm, số lượng và đơn giá được chốt lúc thêm.
3. Sản phẩm trong catalog vẫn tồn tại độc lập khi một đơn bị hủy/xóa.
4. Đơn nháp có thể chưa có dòng; đơn không rỗng mới được xác nhận.
5. Checkout gửi yêu cầu thanh toán qua interface để có thể đổi adapter.

### Sơ đồ lớp

~~~mermaid
classDiagram
    direction LR
    class Customer {
        <<entity>>
        +String id
        +String name
    }
    class Product {
        <<entity>>
        +String sku
        +String name
        +long priceCents
    }
    class Order {
        -String id
        -Customer customer
        -List~OrderLine~ lines
        -Status status
        +addLine(Product product, int quantity) void
        +totalCents() long
        +isEmpty() boolean
        +confirm() void
        +status() Status
    }
    class OrderLine {
        -Product product
        -int quantity
        -long unitPriceCents
        +subtotalCents() long
    }
    class CheckoutService {
        -PaymentGateway gateway
        +checkout(Order order) void
    }
    class PaymentGateway {
        <<interface>>
        +charge(String orderId, long amountCents) void
    }
    class ConsolePaymentGateway {
        +charge(String orderId, long amountCents) void
    }

    Customer "1" <-- "0..*" Order : places
    Order "1" *-- "0..*" OrderLine : owns
    OrderLine "0..*" --> "1" Product : refers to
    CheckoutService ..> Order : checkout parameter
    CheckoutService --> PaymentGateway : injected dependency
    ConsolePaymentGateway ..|> PaymentGateway : implements
~~~

Phân tích từng lựa chọn:

- `Customer` được `Order` tham chiếu, nhưng có thể tồn tại không cần đơn: **association**. Sơ đồ không đòi hỏi `Customer` giữ collection đơn ở chiều ngược lại.
- `OrderLine` là part do `Order` tạo và quản lý: **composition**. Mỗi dòng là một mục riêng của một đơn; không chia sẻ cùng instance dòng giữa hai đơn.
- `Product` là thực thể/cấu trúc tham chiếu độc lập, không phải child của một đơn: **association**.
- `CheckoutService` gọi các hành vi của `Order` qua tham số method: dùng **dependency**. Nó giữ `PaymentGateway` trong field do constructor cung cấp: association/dependency được mô hình hóa bằng đường có hướng.
- `ConsolePaymentGateway` hiện thực interface `PaymentGateway`: **realization**. Thay adapter khác mà không sửa giao diện checkout.
- Các stereotype `«entity»` ở `Customer` và `Product` nhấn mạnh danh tính ổn định theo `id`/`sku` và vòng đời độc lập với `Order`. Ví dụ Java dùng `record` làm biểu diễn bất biến đơn giản; `record` không tự quyết định một đối tượng miền là entity hay value object.

### Mã Java 17+ chạy trong một tệp

Tạo tệp **`OrderDiagramDemo.java`** với toàn bộ nội dung sau:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

// Độc lập với vòng đời của một Order.
record Customer(String id, String name) {
    Customer {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(name, "name");
        if (id.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException("Invalid customer");
        }
    }
}

record Product(String sku, String name, long priceCents) {
    Product {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(name, "name");
        if (sku.isBlank() || name.isBlank() || priceCents < 0) {
            throw new IllegalArgumentException("Invalid product");
        }
    }
}

// Chủ sở hữu vòng đời của từng dòng đơn.
final class Order {
    enum Status { DRAFT, CONFIRMED }

    private final String id;
    private final Customer customer;
    private final List<OrderLine> lines = new ArrayList<>();
    private Status status = Status.DRAFT;

    // Chỉ Order có thể tạo một dòng; không cung cấp API đổi owner.
    private static final class OrderLine {
        private final Product product;
        private final int quantity;
        private final long unitPriceCents;

        private OrderLine(Product product, int quantity) {
            this.product = Objects.requireNonNull(product, "product");
            if (quantity <= 0) {
                throw new IllegalArgumentException("Quantity must be positive");
            }
            this.quantity = quantity;
            this.unitPriceCents = product.priceCents(); // Chốt đơn giá
            Math.multiplyExact(unitPriceCents, quantity); // Kiểm tra tràn số
        }

        private long subtotalCents() {
            return Math.multiplyExact(unitPriceCents, quantity);
        }
    }

    Order(String id, Customer customer) {
        this.id = Objects.requireNonNull(id, "id");
        this.customer = Objects.requireNonNull(customer, "customer");
        if (id.isBlank()) {
            throw new IllegalArgumentException("Order id is blank");
        }
    }

    String id() {
        return id;
    }

    Customer customer() {
        return customer;
    }

    Status status() {
        return status;
    }

    boolean isEmpty() {
        return lines.isEmpty();
    }

    int lineCount() {
        return lines.size();
    }

    // Command: Owner kiểm tra và tạo part trong phạm vi của mình.
    void addLine(Product product, int quantity) {
        ensureDraft();
        lines.add(new OrderLine(product, quantity));
    }

    // Query: Tính tổng không sửa trạng thái.
    long totalCents() {
        long total = 0;
        for (OrderLine line : lines) {
            total = Math.addExact(total, line.subtotalCents());
        }
        return total;
    }

    void confirm() {
        ensureDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("Cannot confirm empty order");
        }
        status = Status.CONFIRMED;
    }

    private void ensureDraft() {
        if (status != Status.DRAFT) {
            throw new IllegalStateException("Order is not a draft");
        }
    }
}

// Interface là hợp đồng, không có quan hệ sở hữu OrderLine.
interface PaymentGateway {
    void charge(String orderId, long amountCents);
}

final class ConsolePaymentGateway implements PaymentGateway {
    @Override
    public void charge(String orderId, long amountCents) {
        System.out.printf("Charge %s: %d cents%n", orderId, amountCents);
    }
}

// Use case nhận Order làm tham số, giữ dependency qua constructor.
final class CheckoutService {
    private final PaymentGateway gateway;

    CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    void checkout(Order order) {
        Objects.requireNonNull(order, "order");

        if (order.status() != Order.Status.DRAFT || order.isEmpty()) {
            throw new IllegalStateException("Order not ready");
        }

        long amount = order.totalCents();
        gateway.charge(order.id(), amount);
        order.confirm();
    }
}

public class OrderDiagramDemo {
    public static void main(String[] args) {
        Customer customer = new Customer("C-01", "Linh");
        Product book = new Product("JAVA", "Java Book", 125_000);
        Product notebook = new Product("NOTE", "Notebook", 30_000);

        Order order = new Order("O-100", customer);
        order.addLine(book, 2);
        order.addLine(notebook, 1);

        System.out.println(order.totalCents()); // 280000
        CheckoutService checkout =
                new CheckoutService(new ConsolePaymentGateway());
        checkout.checkout(order);
        System.out.println(order.status()); // CONFIRMED
        System.out.println(order.customer().name()); // Linh
    }
}
~~~

Chạy:

~~~bash
javac OrderDiagramDemo.java
java OrderDiagramDemo
~~~

Kết quả dự kiến:

~~~text
280000
Charge O-100: 280000 cents
CONFIRMED
Linh
~~~

Với sơ đồ ở trên, những điểm cần chú ý khi so code với UML:

- `Order.customer` là **private field**, nhưng đối tượng `Customer` có thể vẫn tồn tại và được tham chiếu độc lập.
- `OrderLine` là một **private nested class**; sơ đồ tách thành một hình hộp riêng để người đọc hiểu cấu trúc thành phần.
- `Order.addLine(...)` không trả ra `OrderLine`, ngăn caller lấy part của đơn A gắn sang đơn B.
- `Product.priceCents` dùng ở thời điểm tạo dòng và được chốt lại trong `unitPriceCents`. Một thiết kế bán hàng thực cần quy định thêm giá khuyến mãi, thuế, tiền tệ, làm tròn và hiệu lực bảng giá.
- `CheckoutService` không kế thừa `PaymentGateway`, mà cộng tác với một instance của interface.
- `Order.confirm()` chuyển trạng thái sang `CONFIRMED` nhưng không tự giải quyết toàn bộ giao dịch phân tán.

**Phạm vi của ví dụ:** Đây là luồng một luồng (single-thread), mô phỏng thanh toán bằng console. Nếu payment gateway thật đã charge xong nhưng ứng dụng lỗi trước khi lưu `CONFIRMED`, có thể xảy ra trạng thái không nhất quán. Hệ thống thật cần chiến lược transaction, idempotency và đối soát. Sơ đồ lớp không thể hiện đầy đủ các tình huống thời gian như vậy.

## 7. Từ Java sang UML: tránh vẽ nhầm quan hệ

Đoạn Java sau:

~~~java
final class ReportService {
    private final ReportRepository repository;

    ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    Report generate(long id) {
        Report report = repository.findById(id);
        return report;
    }
}
~~~

Có thể mô hình hóa `ReportService → ReportRepository` là một quan hệ định hướng vì service **giữ field tham chiếu**. Tuy nhiên, `Report` chỉ xuất hiện trong tham số/giá trị trả về của operation: tùy mức chi tiết có thể xem là dependency, không nhất thiết là association dài hạn.

~~~mermaid
classDiagram
    class ReportService
    class ReportRepository {
        <<interface>>
    }
    class Report
    ReportService --> ReportRepository : collaborator
    ReportService ..> Report : uses as result
~~~

Một số quy tắc ánh xạ hữu ích:

| Dấu hiệu code | Có thể biểu diễn bằng | Điều còn phải hỏi |
|---|---|---|
| `private B b;` | Association từ A sang B | B có thể null? Có owner hay chỉ tham chiếu? |
| `List<B> members;` | Association với multiplicity nhiều | Có chia sẻ? Ai quản lý lifecycle? |
| `new B()` trong A | Có thể gợi ý composition | Có thực sự sở hữu độc quyền B không? |
| `A extends B` | Generalization | A có giữ hợp đồng thay thế cho B không? |
| `A implements I` | Realization | I là hợp đồng ở tầng nào? |
| B là local variable hoặc tham số method | Dependency | Quan hệ có ý nghĩa đủ lớn để đưa lên sơ đồ không? |
| `@OneToMany` trong JPA | Association với multiplicity | Cascade, orphan removal, ownership phía DB có đúng domain? |

**Không có suy luận tự động** “có field ⇒ composition”. Một `Order` có field `Customer` nhưng không sở hữu vòng đời của khách hàng. Và “không có field ⇒ không liên quan”: method có tham số `Customer` vẫn tạo dependency ở cấp mã nguồn.

## 8. Kế thừa, interface và tính thay thế trong sơ đồ

Ví dụ minh họa độc lập về các kiểu quan hệ giữa các lớp:

~~~mermaid
classDiagram
    class Animal {
        <<abstract>>
        +move() void
    }
    class Dog {
        +move() void
    }
    class Identifiable {
        <<interface>>
        +id() String
    }
    class Shelter {
        +register(Identifiable animal) void
    }
    Animal <|-- Dog : extends
    Identifiable <|.. Dog : implements
    Shelter ..> Identifiable : parameter
~~~

Trong Java:

~~~java
abstract class Animal {
    abstract void move();
}

interface Identifiable {
    String id();
}

final class Dog extends Animal implements Identifiable {
    private final String name;

    Dog(String name) {
        this.name = name;
    }

    @Override void move() {
        System.out.println("Running");
    }

    @Override public String id() {
        return name;
    }
}

final class Shelter {
    void register(Identifiable animal) {
        System.out.println(animal.id());
    }
}
~~~

**Đọc chính xác đường UML:**

- `Dog --|> Animal` là **generalization**: Dog là subtype của Animal.
- `Dog ..|> Identifiable` là **realization**: Dog hiện thực interface.
- `Shelter ..> Identifiable` là **dependency**: shelter nhận tham số kiểu contract; sơ đồ này không khẳng định shelter lưu trữ mọi animal.

Khi vẽ inheritance, cần kiểm tra nguyên tắc thay thế (*Liskov Substitution Principle*): một `Dog` phải đáp ứng kỳ vọng của `Animal`. Đừng kế thừa chỉ để dùng lại helper method.

## 9. Checklist chất lượng cho sơ đồ lớp

Một sơ đồ hữu ích không nhất thiết có nhiều lớp. Khi review, kiểm tra:

1. **Phạm vi và mức độ chi tiết:** Sơ đồ nói về domain, thiết kế hay implementation? Có đang trộn các mức quá nhiều không?
2. **Tên lớp:** Dùng danh từ nghiệp vụ hoặc vai trò kỹ thuật rõ ràng, tránh `Manager`/`Util` cho tập hợp trách nhiệm không liên quan.
3. **Thuộc tính:** Đặt đúng nơi sở hữu trạng thái và invariant. Field có bị public không cần thiết không?
4. **Operation:** Có đặt hành vi ở đúng chủ thể không? Những thao tác thay đổi trạng thái có nêu intent rõ không?
5. **Visibility:** Public API vừa đủ? Helper nội bộ nên private/protected/package-private?
6. **Kiểu dữ liệu:** Các kiểu đơn vị như tiền, định danh, thời gian có được xác định rõ? Có dùng `double` cho tiền một cách thiếu kiểm soát không?
7. **Multiplicity:** Nhãn `1`, `0..1`, `0..*`, `1..*` có được giải thích và enforced khi cần không?
8. **Hướng quan hệ:** Mũi tên đi đúng hướng phụ thuộc/điều hướng? Hình thoi đặt ở đầu whole?
9. **Ownership:** Quan hệ whole–part là association, shared aggregation hay composition? Có lý do nghiệp vụ đủ mạnh để dùng hình thoi đặc?
10. **Kế thừa/realization:** Tam giác rỗng hướng về superclass/interface? Có quan hệ *is-a* và hợp đồng subtype?
11. **Vòng phụ thuộc:** Có đường A → B → A không cần thiết? Có thể trích xuất policy/port hoặc điều phối ở tầng trên?
12. **Tính nhất quán với code:** Có method, field, kiểu, quyền truy cập quan trọng nào khác với sơ đồ mà chưa cập nhật?
13. **Giới hạn biểu diễn:** Điều kiện giao dịch, concurrency, state transition và lỗi vận hành có cần sơ đồ khác hoặc ghi chú?

Một sơ đồ bỏ bớt thuộc tính nội bộ để tập trung vào domain không phải “sai”. Nhưng **quan hệ sai loại hoặc multiplicity không tương thích với yêu cầu nghiệp vụ** có thể khiến người triển khai đưa ra quyết định kiến trúc sai.

## 10. Sai lầm thường gặp khi vẽ sơ đồ lớp

| Lỗi | Vì sao chưa đúng | Cách sửa |
|---|---|---|
| Đặt hình thoi ở phía part | Đảo ngữ nghĩa toàn thể–bộ phận | Đặt hình thoi tại đầu whole |
| Vẽ composition vì có `List<T>` | Collection không nói lên ownership | Xác minh vòng đời và tính độc quyền |
| Vẽ inherit để tái sử dụng một method | Mô hình hóa sai kiểu *is-a* | Dùng collaboration/delegation khi hợp lý |
| Quên multiplicity | Không biết 0, 1 hay nhiều đối tượng | Ghi và giải thích bội số hai đầu |
| Vẽ dependency như association lâu dài | Làm sơ đồ gợi ý object giữ state | Chọn nét đứt nếu chỉ sử dụng ngắn hạn |
| Mặc định getter/setter cho mọi field | Rò rỉ trạng thái, phá đóng gói | Dùng hành vi miền và query cần thiết |
| Tất cả field/method đều public | Caller dễ sửa invariant của đối tượng | Dùng visibility nhỏ nhất hợp lý |
| Nhồi đủ database table lên sơ đồ domain | Đánh mất ý nghĩa và trách nhiệm lớp | Tách domain model với ERD/persistence mapping |
| Cho rằng UML ép code thi hành rule | Sơ đồ chỉ là mô tả | Viết validation, test và DB constraint cần thiết |
| Bỏ qua code thay đổi sau khi vẽ | Tài liệu trở nên sai lệch | Duy trì sơ đồ và code qua review/version control |

## 11. Kiểm thử những điều sơ đồ hứa hẹn

Sơ đồ tự nó không chạy được. Hãy chọn **invariant của các quan hệ** và kiểm tra chúng bằng hành vi Java.

Với `OrderDiagramDemo.java` ở trên, có thể tạo `OrderDiagramTest.java` dùng JUnit Jupiter 5:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class OrderDiagramTest {
    @Test
    void oneOrderOwnsItsLinesAndKeepsCustomerReference() {
        Customer customer = new Customer("C-01", "Linh");
        Product product = new Product("JAVA", "Java Book", 125_000);
        Order first = new Order("O-1", customer);
        Order second = new Order("O-2", customer);

        first.addLine(product, 2);
        second.addLine(product, 1);

        assertSame(customer, first.customer());
        assertSame(customer, second.customer());
        assertEquals(1, first.lineCount());
        assertEquals(1, second.lineCount());
        assertEquals(250_000L, first.totalCents());
        assertEquals(125_000L, second.totalCents());
    }

    @Test
    void checkoutChangesStatusOnlyAfterSuccessfulCharge() {
        Order order = new Order(
                "O-3", new Customer("C-02", "Minh"));
        order.addLine(new Product("N", "Notebook", 30_000), 1);

        final long[] amountCharged = {0L};
        PaymentGateway gateway = (id, amount) -> amountCharged[0] = amount;

        new CheckoutService(gateway).checkout(order);

        assertEquals(30_000L, amountCharged[0]);
        assertEquals(Order.Status.CONFIRMED, order.status());
        assertThrows(IllegalStateException.class,
                () -> order.addLine(
                        new Product("P", "Pen", 1000), 1));
    }

    @Test
    void chargeFailureDoesNotConfirmOrder() {
        Order order = new Order(
                "O-4", new Customer("C-03", "An"));
        order.addLine(new Product("JAVA", "Java Book", 125_000), 1);

        PaymentGateway failingGateway = (id, amount) -> {
            throw new IllegalStateException("Gateway unavailable");
        };

        assertThrows(IllegalStateException.class,
                () -> new CheckoutService(failingGateway).checkout(order));
        assertEquals(Order.Status.DRAFT, order.status());
    }

    @Test
    void emptyOrderCannotBeConfirmed() {
        Order order = new Order(
                "O-5", new Customer("C-04", "Hoa"));
        assertThrows(IllegalStateException.class, order::confirm);
    }
}
~~~

Test xác nhận những gì có ý nghĩa trên mô hình: các đơn chia sẻ tham chiếu khách hàng/sản phẩm độc lập, giữ **dòng riêng**, tổng tiền đúng, trạng thái không bị chuyển khi cổng thanh toán báo lỗi, và đơn rỗng không thể xác nhận.

**Giới hạn:** Test không thể chứng minh “không bao giờ có line được chia sẻ” trong mọi phiên bản code, nhưng API đang dùng private nested `OrderLine` và không lộ phương thức gắn lại part. Test cũng không bảo đảm giao dịch thanh toán thực hoàn toàn rollback được khi gặp lỗi mạng giữa quá trình xử lý; cần integration test và chiến lược đối soát thích hợp.

## 12. Một quy trình vẽ class diagram từ yêu cầu

~~~mermaid
flowchart TD
    A[Đọc tình huống sử dụng và quy tắc] --> B[Chọn khái niệm có identity/state]
    B --> C[Phân trách nhiệm và invariant]
    C --> D[Đặt thuộc tính và operation]
    D --> E[Chọn association / ownership / kiểu cha]
    E --> F[Ghi multiplicity và visibility]
    F --> G[Đối chiếu use case, Java và test]
    G --> H{Thể hiện đủ, không mâu thuẫn?}
    H -->|Chưa| C
    H -->|Rồi| I[Chốt sơ đồ cho mức thiết kế đã chọn]
~~~

**Cách làm thực tế:**

1. **Thu thập use case:** ví dụ “Khách hàng thêm sản phẩm vào đơn nháp và thanh toán”. Xác định happy path và ngoại lệ như đơn rỗng, số lượng không hợp lệ, thanh toán lỗi.
2. **Chọn đối tượng có trách nhiệm:** `Order` chịu trách nhiệm bảo vệ trạng thái và danh sách dòng; `PaymentGateway` làm cổng tích hợp.
3. **Chỉ ra dữ liệu phải được sở hữu:** dòng hàng riêng của mỗi đơn so với tham chiếu sản phẩm chung.
4. **Xác định API cần gọi:** `addLine`, `totalCents`, `confirm`, `checkout`, `charge`; tránh thêm setter công khai cho `status` và `lines`.
5. **Chọn loại quan hệ:** composition cho Order–Line; association cho Order–Customer/Product; realization cho gateway implementation; dependency cho use case sử dụng Order.
6. **Ghi multiplicity:** cân nhắc cả trạng thái nháp và trạng thái xác nhận; bổ sung constraint riêng nếu bội số thay đổi theo trạng thái.
7. **Kiểm chứng bằng Java và test:** object nào được tạo ở đâu? Ai được sửa? Có test bảo vệ invariant? Mã có thay đổi sơ đồ nào không?

**Không cần vẽ mọi thứ**: nếu sơ đồ quá nhiều lớp hoặc mũi tên, hãy tách theo bounded context, use case hoặc mức thiết kế, đồng thời ghi rõ quan hệ nào bị lược bỏ.

## 13. Bài tập vận dụng: thư viện và phiếu mượn

**Yêu cầu mẫu:** Thư viện quản lý `BookTitle` và từng bản sách vật lý `BookCopy`. Một `Member` có thể mượn nhiều bản sách theo các `Loan`, nhưng mỗi bản vật lý chỉ được một lượt mượn **đang hoạt động** tại một thời điểm. Phiếu mượn chứa ngày mượn, hạn trả, trạng thái.

Hãy thực hiện:

1. Viết các lớp/mối quan hệ tối thiểu: `BookTitle`, `BookCopy`, `Member`, `Loan`. Quyết định danh tính của từng loại: ISBN mô tả đầu sách, copy ID mô tả bản vật lý, loan ID mô tả lượt mượn.
2. Vẽ một sơ đồ class có thuộc tính, operation và visibility. Ghi rõ tên và kiểu tham số ở `borrowCopy(member, copy)`, `returnCopy()`, `isAvailable()`.
3. Gắn multiplicity cho quan hệ `BookTitle–BookCopy`, `Member–Loan` và `Loan–BookCopy`. Lưu ý “một bản sách có nhiều Loan **lịch sử**” khác “tối đa một Loan **đang hoạt động**”.
4. Chọn association/aggregation/composition chỉ khi xác nhận vòng đời. Nếu xóa đầu sách khỏi catalog có phải hủy luôn bản vật lý không? Nếu xóa thành viên có cần giữ lịch sử mượn vì quy định lưu trữ không?
5. Viết Java model bảo vệ quy tắc “một bản không thể có hai loan active đồng thời”, thiết kế command và query phù hợp.
6. Kiểm thử một lượt mượn thành công, mượn trùng bản chưa trả, trả sách, và hai yêu cầu mượn cạnh tranh; ghi rõ cơ chế DB transaction nếu chạy nhiều node.

**Câu hỏi tự đánh giá:** Nhìn vào sơ đồ, một đồng đội mới có xác định được **ai sở hữu dữ liệu nào**, **phương thức nào bảo vệ bất biến**, **một instance liên kết tối đa bao nhiêu instance khác**, và **phụ thuộc đi về phía nào** không?

---

**Ghi nhớ:** Sơ đồ lớp mạnh ở việc diễn đạt **thành viên và quan hệ** có ý nghĩa: tên lớp và trách nhiệm; thuộc tính, operation và phạm vi truy cập; association, aggregation, composition, generalization, realization, dependency; cùng multiplicity và hướng điều hướng. Hãy đọc sơ đồ như một **hợp đồng thiết kế cần được Java và kiểm thử bảo vệ**, không như hình vẽ tự động bảo đảm mọi quy tắc.