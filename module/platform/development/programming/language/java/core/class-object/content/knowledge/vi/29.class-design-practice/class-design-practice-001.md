# Chọn trách nhiệm của lớp trước khi chọn trường và phương thức trong Java

## 1. Tư duy quan trọng nhất

Khi bắt đầu viết Java, ta rất dễ đi theo trình tự: nghĩ ra tên class → thêm vài fields → sinh getters/setters → thêm methods để dùng các fields đó. Cách làm này có thể tạo ra một class hợp lệ về cú pháp nhưng **không có lý do tồn tại rõ ràng**, hoặc đẩy business rules ra ngoài đối tượng sở hữu dữ liệu.

Thứ tự thiết kế thường tốt hơn là:

1. Hiểu **vấn đề và kết quả nghiệp vụ** mà phần mềm phải tạo ra.
2. Xác định **trách nhiệm**: ai biết điều gì, ai được quyết định điều gì, ai phối hợp với ai.
3. Tìm **ranh giới thay đổi**, tính kết dính (*cohesion*), phụ thuộc (*coupling*) và ownership của dữ liệu.
4. Chọn **class/interface/record/service** phù hợp với trách nhiệm đó.
5. Từ trách nhiệm, xác định **bất biến** (*invariants*), trạng thái tối thiểu cần giữ và hành vi cần công bố.
6. **Sau cùng** mới thiết kế fields, constructors, methods, access modifiers và tests.

Ví dụ, một giỏ hàng cần “thêm sản phẩm với số lượng hợp lệ và tính tổng” thì trước tiên nên hỏi **ai bảo vệ số lượng**, **giá nằm ở đâu**, **ai sở hữu các dòng hàng**, **ai quyết định giá cuối cùng**, trước khi lập tức tạo các fields như `name`, `count`, `total` hay các methods `setCount()`, `setTotal()`.

> **Nguyên tắc:** Class là nơi tập hợp **dữ liệu và hành vi phục vụ một trách nhiệm có ý nghĩa**; không chỉ là túi chứa fields hay một danh sách methods ngẫu nhiên.

Nội dung thuộc module Java Core – Class/Object, tập trung vào thiết kế hướng đối tượng thực hành. Các ví dụ độc lập có tên tệp, lệnh `javac`/`java` cho Java 17+ và kết quả xác định. Những mảnh mã chỉ dùng để thảo luận được ghi rõ là minh họa.

## 2. “Trách nhiệm của lớp” thực sự là gì?

Trách nhiệm là **một nghĩa vụ của đối tượng hoặc thành phần phần mềm** đối với hệ thống. Nó có thể là:

- **Biết** một phần trạng thái có ý nghĩa: tài khoản biết số dư của chính nó.
- **Bảo vệ bất biến**: số lượng dòng hàng phải lớn hơn 0.
- **Thực hiện hành vi**: giỏ hàng thêm/bớt sản phẩm và tính tổng.
- **Quyết định theo chính sách**: bộ tính phí quyết định phụ phí dựa trên một chiến lược.
- **Phối hợp**: một application service nhận yêu cầu, gọi domain objects và lưu kết quả.
- **Tích hợp**: repository truy xuất storage; gateway gửi thông điệp ra hệ thống bên ngoài.
- **Biểu diễn giá trị**: một Money, Address hoặc DateRange kiểm tra sự hợp lệ và mang value semantics.

Câu hỏi hữu ích:

> “Nếu trách nhiệm này bị thực hiện sai, **đối tượng/thành phần nào** phải bị sửa vì nó là chủ sở hữu tự nhiên của quy tắc?”

Chẳng hạn, nếu số lượng item âm bị lọt vào Order, đó thường là vấn đề ở class đại diện item/order hoặc hành vi tạo/thêm item, chứ không nên phụ thuộc vào việc mỗi caller nhớ tự kiểm.

### Trách nhiệm khác thao tác kỹ thuật

“Có method `setX`”, “có field `x`”, “có getter” không phải mô tả nghiệp vụ tốt. “Duy trì một số dư không âm”, “tính khoản tiền phải thanh toán”, “bảo đảm đơn hàng đã gửi thì không sửa được” mới là những trách nhiệm có thể kiểm chứng.

## 3. Bắt đầu từ use case, không bắt đầu từ sơ đồ fields

Giả sử yêu cầu:

> “Người mua có thể thêm sản phẩm vào giỏ; số lượng phải dương. Giỏ hiển thị tổng tiền. Khi thanh toán, hệ thống ghi đơn và gửi thông báo xác nhận.”

Trước khi viết Java, chia thành các nhóm quyết định:

| Câu hỏi nghiệp vụ | Trách nhiệm ứng viên |
| --- | --- |
| Sản phẩm được nhận diện bằng gì? | ProductId/Product |
| Giá đơn vị có hợp lệ không? | Money hoặc product pricing representation |
| Một dòng hàng phải có quantity bao nhiêu? | CartLine/Cart |
| Ai sở hữu các dòng giỏ hàng? | ShoppingCart |
| Ai tính tổng từ các dòng? | ShoppingCart hoặc PriceCalculator, tùy pricing rules |
| Ai lưu đơn vào database? | OrderRepository |
| Ai gửi email/SMS? | NotificationGateway |
| Ai điều phối checkout qua nhiều thành phần? | CheckoutService |
| Ai định dạng HTML/JSON? | Presentation/serializer component |

Đây là **danh sách ứng viên**, chưa phải quyết định bắt buộc tạo chín classes. Trong bài tập nhỏ, một vài trách nhiệm có thể hợp lý nằm chung; trong hệ lớn, cần tách bởi **những lý do thay đổi thực sự khác nhau**.

Đừng chọn số lớp theo số danh từ trong đề. Hãy tìm những trách nhiệm cần bảo vệ, được dùng lại hoặc thay đổi độc lập.

## 4. Hỏi “lý do thay đổi” để xác định ranh giới

Single Responsibility Principle (SRP) thường được diễn giải là một class nên có **một lý do thay đổi có tính kết dính**. Không nên hiểu máy móc rằng một class chỉ được có một method hoặc một thao tác.

Ví dụ:

- Quy tắc “quantity phải dương” thay đổi do domain bán hàng.
- Format hóa đơn thay đổi do yêu cầu giao diện.
- Gửi email thay đổi do nhà cung cấp dịch vụ.
- Schema database thay đổi do cơ sở dữ liệu.
- Công thức VAT thay đổi do chính sách thuế.

Nếu một class vừa bảo vệ quantity, vừa viết SQL, vừa tạo HTML và gửi SMTP, nó chịu **nhiều loại thay đổi không liên quan**.

### Dấu hiệu class có trách nhiệm quá rộng

- Khi sửa giao diện, phải sửa domain class.
- Khi đổi database, phải sửa logic tổng tiền.
- Unit test một quy tắc nhỏ phải mở network hoặc database thật.
- Constructor yêu cầu rất nhiều dependencies không cùng mục tiêu.
- Methods dùng các nhóm fields gần như không giao nhau.
- Người đọc không thể mô tả class bằng một câu rõ nghĩa.

Tuy nhiên, **nhiều methods cùng hỗ trợ một invariant** vẫn có thể thuộc một class có trách nhiệm tốt.

## 5. Ví dụ phản diện: một class làm tất cả

Đây là **mảnh mã minh họa** cho một thiết kế khó bảo trì; không có các service thực tế để chạy:

```java
class OrderManager {
    String customerEmail;
    java.util.List<String> productIds;
    int[] quantities;

    void validateQuantities() { /* domain rules */ }
    int computePrice() { /* pricing */ return 0; }
    void saveJdbc() { /* database */ }
    void sendSmtp() { /* network */ }
    String renderHtml() { /* presentation */ return ""; }
}
```

Các vấn đề:

1. Một object chịu cả **business rules, persistence, network và UI formatting**.
2. Có nhiều fields dễ bị đặt ở trạng thái không nhất quán: danh sách product IDs và quantities có thể lệch số phần tử.
3. `computePrice()` trả số nguyên nhưng không rõ đơn vị tiền.
4. Tests khó cô lập hành vi; thay một provider làm ảnh hưởng lớp chính.
5. Không rõ ai sở hữu lifecycle của connection/email client.
6. Khi một feature mới xuất hiện, mọi lập trình viên có xu hướng bổ sung thêm vào OrderManager.

**Hướng sửa không phải chỉ đổi tên** thành `OrderService`. Cần phân ranh giới “ai biết”, “ai quyết định”, “ai lưu/gửi”, rồi dịch chuyển state và behavior về nơi sở hữu thích hợp.

## 6. Phiên bản nhỏ: đối tượng giữ đúng một invariant

Bắt đầu bằng yêu cầu đơn giản: một dòng đặt hàng có **tên mặt hàng**, **đơn giá không âm** và **số lượng dương**; thành tiền được tính từ hai giá trị.

Tạo **`OrderLineResponsibilityDemo.java`**:

```java
import java.util.Objects;

final class OrderLine {
    private final String item;
    private final int unitPrice;
    private final int quantity;

    OrderLine(String item, int unitPrice, int quantity) {
        this.item = Objects.requireNonNull(item);
        if (item.isBlank()) {
            throw new IllegalArgumentException("blank item");
        }
        if (unitPrice < 0) {
            throw new IllegalArgumentException("negative price");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("invalid quantity");
        }
        this.unitPrice = unitPrice;
        this.quantity = quantity;
    }

    String item() {
        return item;
    }

    int quantity() {
        return quantity;
    }

    int subtotal() {
        return Math.multiplyExact(unitPrice, quantity);
    }
}

public class OrderLineResponsibilityDemo {
    public static void main(String[] args) {
        OrderLine line = new OrderLine("Notebook", 12, 3);

        System.out.println(line.item());
        System.out.println(line.quantity());
        System.out.println(line.subtotal());
    }
}
```

```bash
javac OrderLineResponsibilityDemo.java
java OrderLineResponsibilityDemo
```

```text
Notebook
3
36
```

### Tại sao đây là trách nhiệm rõ ràng?

`OrderLine` có nghĩa: **biểu diễn một dòng hàng hợp lệ và cung cấp giá trị tính từ dòng đó**. Những fields xuất hiện vì cần hoàn thành trách nhiệm, không phải vì dự đoán trước rất nhiều getter/setter.

- `item`: danh tính/nhãn của dòng.
- `unitPrice`: mức giá dùng khi tính subtotal.
- `quantity`: số đơn vị.
- `subtotal()`: hành vi nhất quán với state.
- Constructor: ranh giới đảm bảo object không được tạo trong trạng thái sai.

Ví dụ dùng số nguyên như đơn vị tiền nhỏ nhất cho bài học; hệ thật cần quy định currency, overflow và pricing policy. `Math.multiplyExact` giúp tránh integer overflow âm thầm.

## 7. Tại sao không tạo `setQuantity()` chỉ vì có field quantity?

Nếu tất cả fields đều có setter công khai, caller có thể đưa object vào trạng thái không hợp lệ:

```java
// line.setQuantity(-100);
// line.setUnitPrice(-5);
```

Đây là lời gọi minh họa tới các setter **không tồn tại** trong thiết kế OrderLine ở trên.

Nếu nghiệp vụ **cho phép đổi số lượng**, hãy thêm hành vi có ý nghĩa và kiểm ràng buộc:

```java
void changeQuantity(int nextQuantity) {
    if (nextQuantity <= 0) {
        throw new IllegalArgumentException("invalid quantity");
    }
    this.quantity = nextQuantity;
}
```

Đây là **mảnh method** cho phiên bản OrderLine có field quantity **không final**. Không chèn nó nguyên dạng vào class trước vì class trước cố ý bất biến.

**Câu hỏi trước khi thêm setter:** “Ai được phép thay? Thay lúc nào? Sau khi thanh toán còn được không? Thay một field có cần cập nhật fields khác không?” Các câu trả lời quyết định **method semantics và state model**, không phải IDE generator.

## 8. Trách nhiệm dẫn tới bất biến, rồi bất biến dẫn tới fields

Một cách ghi thiết kế:

```text
Trách nhiệm:
  "Giỏ hàng sở hữu các dòng hàng và tính tổng"

Bất biến:
  "Không có dòng với số lượng <= 0"
  "Không công bố collection nội bộ mutable"
  "Tổng = tổng subtotal của các dòng"

State tối thiểu:
  List<OrderLine> lines

Methods:
  addLine(...)
  total()
  lines() trả snapshot
```

Sơ đồ này là **mô hình**, không phải Java runnable.

Nếu tổng có thể tính từ lines bất cứ khi nào, không nhất thiết lưu field `cachedTotal`. Lưu giá trị dẫn xuất chỉ nên làm khi có nhu cầu hiệu năng được chứng minh và có cơ chế invalidation nhất quán.

### Tránh trạng thái trùng lặp

Nếu có cả `List<OrderLine>` lẫn `int itemCount` và `int total`, mỗi thay đổi lines phải đồng bộ thêm hai fields. Điều này làm tăng số invariants cần giữ. Bắt đầu từ state tối thiểu thường dễ đúng hơn.

## 9. Chương trình đầy đủ: Cart là chủ sở hữu lines

Tạo **`ShoppingCartResponsibilityDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;

record CartLine(String item, int unitPrice, int quantity) {
    CartLine {
        if (item == null || item.isBlank()) {
            throw new IllegalArgumentException("item");
        }
        if (unitPrice < 0 || quantity <= 0) {
            throw new IllegalArgumentException("price/quantity");
        }
    }

    int subtotal() {
        return Math.multiplyExact(unitPrice, quantity);
    }
}

final class ShoppingCart {
    private final List<CartLine> lines = new ArrayList<>();

    void add(String item, int unitPrice, int quantity) {
        lines.add(new CartLine(item, unitPrice, quantity));
    }

    int total() {
        int result = 0;
        for (CartLine line : lines) {
            result = Math.addExact(result, line.subtotal());
        }
        return result;
    }

    List<CartLine> lines() {
        return List.copyOf(lines);
    }
}

public class ShoppingCartResponsibilityDemo {
    public static void main(String[] args) {
        ShoppingCart cart = new ShoppingCart();
        cart.add("Pen", 3, 2);
        cart.add("Book", 10, 1);

        System.out.println(cart.total());
        System.out.println(cart.lines().size());

        try {
            cart.lines().clear();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot cannot be cleared");
        }

        System.out.println(cart.lines().size());
    }
}
```

```bash
javac ShoppingCartResponsibilityDemo.java
java ShoppingCartResponsibilityDemo
```

```text
16
2
snapshot cannot be cleared
2
```

**Tách trách nhiệm:**

- `CartLine` biểu diễn một dòng hàng hợp lệ và tính subtotal của chính dòng ấy.
- `ShoppingCart` sở hữu collection, bổ sung lines và tính tổng từ các lines.
- Caller không thể sửa trực tiếp list nội bộ qua accessor vì `List.copyOf` trả collection unmodifiable.
- CartLine record có primitive/String components nên không giữ một mutable element cần defensive copy sâu.
- `Math.addExact`/`multiplyExact` giúp ví dụ không silently overflow.

**Giới hạn:** Đây là cart đơn giản, không có currency, thuế, promotion, inventory reservations hay concurrent updates. Không cố nhét mọi chính sách vào CartLine trước khi có use case thực sự.

## 10. Ranh giới owner: ai được bảo vệ dữ liệu?

Giả sử Cart có field:

```java
private final List<CartLine> lines = new ArrayList<>();
```

Nếu trả thẳng reference:

```java
List<CartLine> lines() {
    return lines;
}
```

caller có thể `clear()`, `add(null)` hoặc sửa những điều mà Cart chưa kiểm. Điều đó làm responsibility “Cart duy trì lines hợp lệ” không còn thuộc Cart nữa.

**Một tiêu chí chọn fields/methods:** Nếu lớp sở hữu invariant của collection, nó cũng phải sở hữu **đường mutation**. API có thể cho phép đọc snapshot/copy hoặc unmodifiable view tùy hợp đồng, nhưng đừng phơi bày mutable internals nếu class cần kiểm soát state.

### Phân biệt snapshot với view

`List.copyOf(lines)` cho một unmodifiable snapshot structure tại thời điểm gọi. `Collections.unmodifiableList(lines)` trả một view không cho caller mutate qua view, nhưng **vẫn phản ánh thay đổi sau đó ở list gốc**.

Chọn theo ý nghĩa API: cần ảnh chụp ở thời điểm gọi hay muốn quan sát state hiện tại chỉ để đọc?

## 11. Tính kết dính (cohesion): những method có phục vụ cùng mục tiêu?

Một class có cohesion tốt khi members góp phần phục vụ một trách nhiệm nhất quán.

Ví dụ một `TemperatureRange` có thể có:

- `contains(value)`
- `overlaps(other)`
- `span()`
- `lower()/upper()`

Dù có bốn methods, chúng đều liên quan phạm vi nhiệt độ và cùng invariants min/max.

Ngược lại, thêm `sendEmail()` vào TemperatureRange làm thay đổi lý do class tồn tại: thao tác gửi email thuộc infrastructure/notification concern, không thuộc representation của khoảng nhiệt độ.

### “Một trách nhiệm” không có nghĩa “chỉ một method”

Class ShoppingCart có thể có `add`, `remove`, `clear`, `total`, `itemCount` và những hành vi nghiệp vụ hợp lý khác mà vẫn cohesive, vì tất cả phục vụ state và lifecycle của giỏ hàng.

Không nên tách thành `CartAddManager`, `CartRemoveManager`, `CartCountManager` chỉ vì muốn mỗi class có một method. Đó là **over-fragmentation**: tăng số components và coupling mà không tạo ranh giới trách nhiệm thực sự.

## 12. Coupling: vì sao cần cân nhắc phụ thuộc?

**Coupling** là mức độ một class biết và phụ thuộc vào các classes khác. Một class domain phụ thuộc trực tiếp vào JDBC, SMTP và HTTP controller framework sẽ khó đổi và khó test.

Ví dụ có coupling cao:

```java
class Invoice {
    void saveToDatabase() {
        // JDBC details
    }

    void sendByEmail() {
        // SMTP details
    }
}
```

Đây là **minh họa thiết kế**, không phải implementation đầy đủ.

Khi email provider đổi, phải sửa Invoice; khi database đổi, cũng sửa Invoice. Những thay đổi infrastructure không nên làm thay đổi trách nhiệm “hóa đơn biểu diễn khoản phải thanh toán”.

### Một cách phân ranh giới

- `Invoice`: biết dữ liệu và quy tắc giá trị của hóa đơn.
- `InvoiceRepository`: hợp đồng truy xuất/lưu trữ Invoice.
- `NotificationSender`: hợp đồng gửi thông báo.
- `CheckoutService`: phối hợp quy trình có sử dụng invoice/repository/sender.

**Tránh cực đoan:** Với script nhỏ chỉ in một kết quả, không nhất thiết tạo nhiều interface và service. Tách khi các lý do thay đổi, tests hoặc deployment boundary thực sự có giá trị.

## 13. Chương trình: tách nghiệp vụ tính giá khỏi việc thông báo

Tạo **`SeparationOfResponsibilitiesDemo.java`**:

```java
import java.util.List;

record Line(String name, int price, int quantity) {
    Line {
        if (price < 0 || quantity <= 0) {
            throw new IllegalArgumentException("line");
        }
    }

    int amount() {
        return Math.multiplyExact(price, quantity);
    }
}

final class Invoice {
    private final List<Line> lines;

    Invoice(List<Line> lines) {
        this.lines = List.copyOf(lines);
    }

    int total() {
        int sum = 0;
        for (Line line : lines) {
            sum = Math.addExact(sum, line.amount());
        }
        return sum;
    }
}

interface ReceiptSender {
    void send(int total);
}

final class ConsoleReceiptSender implements ReceiptSender {
    @Override
    public void send(int total) {
        System.out.println("receipt:" + total);
    }
}

final class CheckoutService {
    private final ReceiptSender sender;

    CheckoutService(ReceiptSender sender) {
        this.sender = sender;
    }

    void checkout(Invoice invoice) {
        int total = invoice.total();
        sender.send(total);
    }
}

public class SeparationOfResponsibilitiesDemo {
    public static void main(String[] args) {
        Invoice invoice = new Invoice(List.of(
                new Line("Notebook", 8, 2),
                new Line("Pen", 2, 3)
        ));

        CheckoutService checkout =
                new CheckoutService(new ConsoleReceiptSender());

        checkout.checkout(invoice);
        System.out.println(invoice.total());
    }
}
```

```bash
javac SeparationOfResponsibilitiesDemo.java
java SeparationOfResponsibilitiesDemo
```

```text
receipt:22
22
```

**Diễn giải:**

- `Line` quyết định amount của một dòng.
- `Invoice` quyết định tổng của các lines.
- `ReceiptSender` là interface chỉ nói **gửi receipt**, không biết Invoice được tính thế nào.
- `ConsoleReceiptSender` dùng console như một adapter demo thay cho email/HTTP.
- `CheckoutService` phối hợp lấy tổng và nhờ sender gửi.
- Thay cách gửi không buộc sửa Invoice hoặc Line.

**Giới hạn nghiệp vụ:** Đây chưa phải checkout thật: không xử lý payment, transaction, retry, lưu order hay failure semantics. Việc tách class **không tự** giải quyết consistency khi gửi email thất bại.

## 14. Entity, value object, service: các vai trò thường gặp

Không phải mọi class đều là một entity hoặc một “manager”. Khi lựa chọn responsibility, hãy nhận diện **vai trò khái niệm**:

| Vai trò | Trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Entity | Duy trì identity, lifecycle và quy tắc liên quan | Customer, Order |
| Value object | Biểu diễn một giá trị với validation/value semantics | Money, DateRange |
| Domain service | Thực hiện quy tắc domain liên quan nhiều objects, không thuộc tự nhiên một entity | PricingPolicy, TransferPolicy |
| Application service | Điều phối use case, transaction, repository/gateway calls | CheckoutService |
| Repository | Truy xuất/lưu aggregate theo contract | OrderRepository |
| Adapter/gateway | Giao tiếp HTTP/DB/email/file | EmailSender, JdbcOrderRepository |
| Controller/UI | Nhận input, tạo response, chuyển đổi DTO | CheckoutController |
| DTO/record | Vận chuyển dữ liệu theo contract | CheckoutRequest, Receipt |
| Utility | Thuật toán thuần, không mang identity hoặc lifecycle | Checksums, ParsingHelpers |

Đây là **gợi ý kiến trúc**, không phải yêu cầu mỗi ứng dụng Java phải dùng đúng các tầng này. Một vai trò được chọn vì trách nhiệm, không vì suffix “Service/Manager/Util”.

## 15. Khi nào dùng `record` thay vì class thường?

Java 17 record phù hợp với những **data carriers** có value-oriented semantics đơn giản:

```java
record Coordinate(int x, int y) {}
record CustomerId(String value) {}
```

Record tự sinh canonical constructor/accessors/equals/hashCode/toString theo components (trừ khi custom). Nó rất tốt cho IDs, coordinates và request/response messages phù hợp.

Nhưng câu hỏi đầu tiên vẫn là trách nhiệm:

- Object này chỉ cần **mang một giá trị** hay có identity dài hạn?
- Có cần invariant được kiểm qua constructor không?
- Components có mutable arrays/lists cần defensive copying không?
- Có cần thay state/lifecycle không?
- Equality theo value hay identity?

**Không chọn record chỉ để tránh viết boilerplate** nếu object cần mutable identity và lifecycle rõ. Ngược lại, đừng viết class mutable với setters công khai cho một value object vốn nên bất biến.

## 16. Ví dụ value object: khoảng số hợp lệ

Tạo **`RangeValueObjectDemo.java`**:

```java
record IntRange(int min, int max) {
    IntRange {
        if (min > max) {
            throw new IllegalArgumentException(
                    "min greater than max");
        }
    }

    boolean contains(int value) {
        return min <= value && value <= max;
    }

    int length() {
        return Math.subtractExact(max, min);
    }
}

public class RangeValueObjectDemo {
    public static void main(String[] args) {
        IntRange range = new IntRange(2, 8);

        System.out.println(range.contains(5));
        System.out.println(range.contains(9));
        System.out.println(range.length());
        System.out.println(new IntRange(2, 8).equals(range));
    }
}
```

```bash
javac RangeValueObjectDemo.java
java RangeValueObjectDemo
```

```text
true
false
6
true
```

Class/record được tạo vì **khái niệm khoảng có nghĩa riêng**, không vì hai fields `min` và `max` tình cờ xuất hiện cùng nhau. Nó giữ invariant `min <= max` và cung cấp behavior liên quan trực tiếp.

### Câu hỏi làm rõ semantics

`length()` ở ví dụ là **độ chênh max - min**, không phải số số nguyên nằm trong khoảng đóng (số phần tử sẽ là max-min+1, có thể overflow). Tên method và định nghĩa business phải thống nhất; method name không tự quyết định semantics.

## 17. Thiết kế Money: responsibility lớn hơn một primitive

Tiền thường mang **amount và currency**; phép cộng hai đồng tiền khác nhau không hợp lệ nếu chưa chuyển đổi có policy. Một field `double price` một mình khó bảo vệ điều đó.

Tạo **`MoneyResponsibilityDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.Currency;
import java.util.Objects;

record Money(BigDecimal amount, Currency currency) {
    Money {
        Objects.requireNonNull(amount, "amount");
        Objects.requireNonNull(currency, "currency");
    }

    Money add(Money other) {
        Objects.requireNonNull(other);
        if (!currency.equals(other.currency)) {
            throw new IllegalArgumentException(
                    "currency mismatch");
        }
        return new Money(amount.add(other.amount), currency);
    }

    Money multiply(int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("quantity");
        }
        return new Money(
                amount.multiply(BigDecimal.valueOf(quantity)),
                currency);
    }
}

public class MoneyResponsibilityDemo {
    public static void main(String[] args) {
        Currency vnd = Currency.getInstance("VND");
        Money price = new Money(new BigDecimal("10000"), vnd);

        Money total = price.multiply(3);
        Money shipping =
                new Money(new BigDecimal("5000"), vnd);

        System.out.println(total.add(shipping).amount());
        System.out.println(total.currency().getCurrencyCode());
    }
}
```

```bash
javac MoneyResponsibilityDemo.java
java MoneyResponsibilityDemo
```

```text
35000
VND
```

### Vì sao trách nhiệm quyết định methods?

`Money` chịu trách nhiệm thực hiện những phép toán **giữ nguyên currency invariant**. Method `add` từ chối khác currency. Một method `sendEmail()` hoặc `saveJdbc()` không phục vụ trách nhiệm này.

**Giới hạn:** Ví dụ không tự áp dụng rounding scale hay giới hạn không âm; chính sách tiền tệ thật phải quyết định quy tắc này. `BigDecimal` phù hợp decimal arithmetic nhưng không thể thay quyết định domain về conversion/tax/rounding.

## 18. Ai sở hữu hành vi? Đặt method gần dữ liệu nó bảo vệ

Xét quy tắc “không cho rút vượt số dư”. Có hai hướng:

**Thiết kế dễ sai:**

```java
// account.setBalance(account.getBalance() - amount);
```

Nếu caller trực tiếp sửa balance, mỗi chỗ dùng phải nhớ kiểm, đồng thời có thể xảy ra race nếu cập nhật đồng thời.

**Thiết kế hướng trách nhiệm:**

```java
account.withdraw(amount);
```

Account quản lý invariant và có thể dùng một operation rõ nghĩa.

### Ví dụ đầy đủ

Tạo **`AccountResponsibilityDemo.java`**:

```java
final class Account {
    private int balance;

    Account(int openingBalance) {
        if (openingBalance < 0) {
            throw new IllegalArgumentException("opening");
        }
        balance = openingBalance;
    }

    void deposit(int amount) {
        requirePositive(amount);
        balance = Math.addExact(balance, amount);
    }

    void withdraw(int amount) {
        requirePositive(amount);
        if (amount > balance) {
            throw new IllegalArgumentException(
                    "insufficient balance");
        }
        balance -= amount;
    }

    int balance() {
        return balance;
    }

    private static void requirePositive(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
    }
}

public class AccountResponsibilityDemo {
    public static void main(String[] args) {
        Account account = new Account(100);
        account.deposit(50);
        account.withdraw(20);

        System.out.println(account.balance());

        try {
            account.withdraw(200);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println(account.balance());
    }
}
```

```bash
javac AccountResponsibilityDemo.java
java AccountResponsibilityDemo
```

```text
130
insufficient balance
130
```

`Account` không có public setter cho balance, vì trách nhiệm của nó là **duy trì số dư hợp lệ qua hành vi nghiệp vụ**. Với withdraw lỗi, method không sửa state trước khi ném exception; account vẫn có balance 130.

**Phạm vi:** Ví dụ đơn luồng, dùng integer units. Trong banking thực, cần đồng bộ, giao dịch bền vững và money type/currency policy. Thiết kế class tốt là điều kiện cần, không tự là cơ sở dữ liệu ACID.

## 19. Khi trách nhiệm trải trên hai objects, đừng ép một đối tượng làm hết

“Chuyển tiền từ A sang B” liên quan **hai accounts** và yêu cầu **tính nhất quán của cả hai**. Một Account có thể chịu trách nhiệm rút/nạp hợp lệ, nhưng operation transfer có thể thuộc một service/aggregate có quyền điều phối atomicity.

Mảnh minh họa:

```java
class TransferService {
    void transfer(Account from, Account to, int amount) {
        // Kiểm nghiệp vụ, điều phối rút/nạp,
        // transaction/rollback theo storage model.
    }
}
```

**Chưa phải implementation chuyển tiền an toàn.** Nếu gọi `from.withdraw` xong rồi `to.deposit` lỗi, hệ thống có thể bị thay đổi một phía. Chỉ tách trách nhiệm thành TransferService **không** tự tạo atomic transaction; phải chọn storage/transaction boundary và failure handling.

### Câu hỏi ownership

- Account biết invariant của từng account.
- Transfer orchestration chịu trách nhiệm **toàn bộ thay đổi liên-account**.
- Repository/transaction manager chịu trách nhiệm persistence/concurrency.
- Notification service gửi thông báo sau khi transaction hoàn tất theo workflow thích hợp.

Điều quan trọng là **xác định trách nhiệm trước**, rồi mới chọn fields và methods; đừng nhét transaction SQL vào Account chỉ vì Account có balance.

## 20. Phân biệt entity và value object qua identity/lifecycle

Một `Customer` entity có thể đổi email nhưng giữ cùng CustomerId. Một `EmailAddress` value object có thể được thay bằng giá trị khác; không cần giữ entity identity riêng cho địa chỉ email.

| Câu hỏi | Entity | Value object |
| --- | --- | --- |
| Đối tượng có identity độc lập state? | Thường có | Thường không |
| Có lifecycle chuyển trạng thái? | Có thể | Thường biểu diễn giá trị bất biến |
| Equality kỳ vọng? | Theo ID/domain identity | Theo value components |
| Fields là gì? | State cần cho invariants/lifecycle | Các components định nghĩa giá trị |
| Methods là gì? | Commands/query của entity | Validation/value operations |
| Có dùng record? | Thường cân nhắc class | Record thường phù hợp |

**Không biến bảng này thành luật ngôn ngữ:** Java không có keyword `entity`, và có nhiều thiết kế hợp lệ. Vai trò là cách suy luận domain để chọn abstraction.

## 21. Đi từ trách nhiệm đến public API tối thiểu

Với OrderLine ở đầu bài, public-facing API có thể chỉ cần:

```java
int subtotal();
int quantity();
String item();
```

Không cần mặc nhiên sinh `setItem`, `setQuantity`, `setSubtotal` hoặc `getEverythingAsMap`.

**Nguyên tắc quyền truy cập nhỏ nhất:** Giữ fields `private` và chỉ expose hành vi cần thiết. Một class có thể dùng package-private methods trong bài tập để ngắn; library API public phải cân nhắc contracts và module boundaries rõ.

Mỗi public method là một lời hứa:

- Input hợp lệ gồm những gì?
- Có thể ném exception nào?
- Object state có đổi không?
- Có trả alias của mutable internals không?
- Thread safety ra sao?
- Có giữ backward compatibility khi method đổi không?

Một API nhỏ và giàu ý nghĩa thường dễ duy trì hơn một tập setters/getters tràn lan.

## 22. Chọn method bằng câu hỏi “người dùng class muốn làm gì?”

Thay vì liệt kê CRUD trực tiếp cho mọi field:

```java
order.setStatus("PAID");
order.setPaidAt(time);
```

hãy suy ra hành vi:

```java
order.markPaid(time);
```

Đây là các **mảnh mã minh họa**. Method `markPaid` có thể kiểm:

- Current status có cho phép thanh toán không?
- Timestamp có hợp lệ không?
- Có ngăn cập nhật lần hai không?
- Những fields nào phải thay đổi đồng bộ?

Class chịu trách nhiệm **transition bất biến** nên sở hữu method chuyển trạng thái. Nếu status bị sửa từ nhiều setters riêng, caller có thể quên cập nhật paidAt hoặc chuyển từ state không cho phép.

## 23. Ví dụ state transition có trách nhiệm rõ

Tạo **`OrderLifecycleResponsibilityDemo.java`**:

```java
enum OrderStatus {
    NEW, PAID, CANCELLED
}

final class Order {
    private OrderStatus status = OrderStatus.NEW;

    void pay() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                    "only NEW order can be paid");
        }
        status = OrderStatus.PAID;
    }

    void cancel() {
        if (status != OrderStatus.NEW) {
            throw new IllegalStateException(
                    "only NEW order can be cancelled");
        }
        status = OrderStatus.CANCELLED;
    }

    OrderStatus status() {
        return status;
    }
}

public class OrderLifecycleResponsibilityDemo {
    public static void main(String[] args) {
        Order order = new Order();

        order.pay();
        System.out.println(order.status());

        try {
            order.cancel();
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println(order.status());
    }
}
```

```bash
javac OrderLifecycleResponsibilityDemo.java
java OrderLifecycleResponsibilityDemo
```

```text
PAID
only NEW order can be cancelled
PAID
```

**Lý do class Order tồn tại:** Quản lý một order và transitions hợp lệ. Fields và methods được suy ra từ trách nhiệm **không cho phép trạng thái sai**, không từ nhu cầu có một mutable enum property.

**Đừng nhầm:** Một enum status chưa mô tả tất cả business workflows; với hệ thật còn có payment ID, thời điểm thanh toán, idempotency, refunds, persistence transaction và đồng bộ. Chỉ thêm state khi yêu cầu làm rõ trách nhiệm.

## 24. Tránh “anemic domain model” một cách có hiểu biết

*Anemic domain model* thường chỉ một kiểu thiết kế mà entities chủ yếu có fields và getters/setters, trong khi toàn bộ business rules bị đẩy ra services thao tác trực tiếp lên state.

Ví dụ nguy cơ:

```java
class OrderData {
    public int amount;
    public String status;
}

class OrderLogic {
    void pay(OrderData order) {
        order.status = "PAID";
    }
}
```

Hai classes này chỉ là **mảnh minh họa**. Chúng cho phép caller tự thay `status` thành bất kỳ string nào; không có owner rõ để bảo vệ state transition.

Nhưng **không phải mọi DTO mỏng đều sai**: một request/response record chỉ mang dữ liệu qua boundary có thể hoàn toàn đúng trách nhiệm. Tách biệt:

- DTO: mục đích là **vận chuyển dữ liệu**.
- Domain object: mục đích có thể bao gồm **duy trì invariants và business behavior**.

Đừng ép DTO phải có domain business logic; cũng đừng biến domain entity thành mutable data bag nếu nó cần tự bảo vệ các quy tắc của chính nó.

## 25. Phân chia trách nhiệm theo thay đổi, không theo kỹ thuật “mọi method 1 class”

Nếu nhiều methods dùng chung fields và bảo vệ cùng một invariant, tách quá nhỏ sẽ làm tăng coupling:

```text
CartAddService → CartStateHolder
CartRemoveService → CartStateHolder
CartTotalService → CartStateHolder
CartValidator → CartStateHolder
```

Mô hình này có thể khiến CartStateHolder phơi bày mutable collection để nhiều helpers phối hợp, làm suy yếu encapsulation.

Một class `ShoppingCart` duy nhất có `add/remove/total` có thể **cohesive hơn**. Ngược lại, một `NotificationSender` độc lập phục vụ network I/O có lý do thay đổi riêng, nên nên tách khỏi Cart.

### Một cách hỏi thực dụng

“Nếu có bug về giỏ hàng, developer sẽ sửa một nơi có kiến thức đầy đủ hay phải theo dấu qua hàng chục classes nhỏ? Nếu đổi email provider, có phải sửa Cart không?”

Hai câu hỏi giúp cân bằng tránh **God Object** và **overengineering**.

## 26. “God class” thường bắt đầu bằng trách nhiệm mơ hồ

Những tên như `Manager`, `Helper`, `Utils`, `Processor` tự thân không sai, nhưng dễ trở thành nơi chứa thao tác bất kỳ nếu không có một sentence contract rõ.

Ví dụ một `ApplicationManager` quản lý user auth, pricing, sending email, database, PDF, logging và caches không có một thay đổi tập trung.

**Bộ lọc tên trách nhiệm:**

- Có thể diễn tả “Class X chịu trách nhiệm Y” mà không dùng “và nhiều thứ khác”?
- Các methods có cùng vocabulary domain?
- Có nhóm fields bị sử dụng bởi gần như chỉ một số methods riêng biệt không?
- Nếu một requirement thay đổi, vùng code bị sửa có giới hạn rõ không?
- Dependencies của class có phản ánh đúng nhiệm vụ không?

Không cần đặt suffix theo một khuôn cố định; hãy chọn tên thể hiện khái niệm hoặc vai trò có thể giải thích được.

## 27. Chọn collaborator thay vì nhồi mọi logic vào một class

Một trách nhiệm lớn có thể cần cộng tác:

```text
CheckoutService
   ├── ShoppingCart       (state và item invariants)
   ├── PricePolicy        (pricing rules)
   ├── OrderRepository    (persistence)
   └── ReceiptSender      (notification)
```

Đây là sơ đồ khái niệm.

`CheckoutService` chịu **workflow orchestration**, nhưng không cần biết SQL columns hay SMTP headers. Nó có thể phụ thuộc vào interfaces thể hiện capability thay vì cụ thể classes.

**Tránh tạo phụ thuộc hai chiều không cần thiết** như `Cart → CheckoutService → Cart` hoặc `Order → EmailSender → Order` nếu điều đó làm ownership rối. Mỗi cạnh nên có lý do nghiệp vụ.

## 28. Interface chỉ nên xuất hiện khi có một hợp đồng hữu ích

Đừng tạo `IUserService` và `UserServiceImpl` cho mọi class chỉ vì “theo chuẩn”. Interface có giá trị khi:

- Có hoặc dự kiến có **nhiều implementations mang semantics hợp lý**.
- Caller cần mock/fake adapter qua một stable contract.
- Boundary giữa domain/application và infrastructure cần đảo chiều dependency.
- Plugin extension point được công bố cho bên ngoài.
- API muốn diễn đạt capability độc lập concrete class.

Với một value object `Money`, interface `MoneyInterface` thường không thêm giá trị nếu không có biến thể/contract cần trừu tượng hóa.

**Chọn abstraction theo responsibility và nhu cầu thay đổi**, không theo số lớp mong muốn.

## 29. Ví dụ dependency injection không cần framework

Tạo **`InjectedPolicyDemo.java`**:

```java
interface ShippingCost {
    int costFor(int itemCount);
}

final class FlatShipping implements ShippingCost {
    @Override
    public int costFor(int itemCount) {
        if (itemCount < 0) {
            throw new IllegalArgumentException("item count");
        }
        return itemCount == 0 ? 0 : 15;
    }
}

final class FreeShipping implements ShippingCost {
    @Override
    public int costFor(int itemCount) {
        if (itemCount < 0) {
            throw new IllegalArgumentException("item count");
        }
        return 0;
    }
}

final class OrderQuote {
    private final ShippingCost shipping;

    OrderQuote(ShippingCost shipping) {
        this.shipping = java.util.Objects.requireNonNull(
                shipping);
    }

    int total(int goodsAmount, int itemCount) {
        if (goodsAmount < 0) {
            throw new IllegalArgumentException("goods amount");
        }
        return Math.addExact(goodsAmount,
                shipping.costFor(itemCount));
    }
}

public class InjectedPolicyDemo {
    public static void main(String[] args) {
        OrderQuote standard =
                new OrderQuote(new FlatShipping());
        OrderQuote promoted =
                new OrderQuote(new FreeShipping());

        System.out.println(standard.total(100, 2));
        System.out.println(promoted.total(100, 2));
    }
}
```

```bash
javac InjectedPolicyDemo.java
java InjectedPolicyDemo
```

```text
115
100
```

`OrderQuote` chịu trách nhiệm **tạo báo giá có shipping**, `ShippingCost` chịu trách nhiệm **chọn chính sách phí**. Hai concerns có thể thay đổi độc lập, nên interface/injection có lý do rõ.

Không cần Spring hoặc framework injection để có responsibility separation. Constructor injection và một interface Java 17 bình thường đã đủ cho ví dụ.

## 30. Chọn field từ “phải nhớ cái gì giữa hai lời gọi?”

Một field nên được thêm vì class có **trạng thái cần lưu qua methods** hoặc vì cần giữ một collaborator.

Hỏi cho từng candidate:

1. Nếu bỏ field này, trách nhiệm còn được thực hiện đúng không?
2. Field lưu **state gốc** hay chỉ là giá trị tính lại?
3. Field thuộc **đối tượng này** hay nên nằm ở một object khác?
4. Field có cần thay đổi theo thời gian không?
5. Field có thể được suy ra từ fields khác không?
6. Có cơ chế ngăn bất biến sai khi field thay đổi không?
7. Field có phải external resource cần đóng không?
8. Có đang vô tình giữ một object graph lớn vượt lifecycle?

Ví dụ subtotal của OrderLine tính từ `price × quantity`; lưu cả `subtotal` có thể làm dư state. Ngược lại, order status là thông tin trạng thái lifecycle, không thể luôn suy ra từ tổng tiền.

### Field của một dependency cũng phải có trách nhiệm

`private final Clock clock` có thể hợp lý nếu class cần thời gian có thể kiểm thử. `private final List<RandomUtil> helpers` khó giải thích nếu class không có nhiệm vụ liên quan trực tiếp.

## 31. Constructor không chỉ là chỗ gán fields

Constructor có thể được dùng để:

- Xác định các dependencies bắt buộc.
- Validate arguments trước khi công bố instance.
- Chuẩn hóa representation.
- Tạo defensive copies cho dữ liệu mutable nếu object sở hữu state.
- Bảo đảm object bắt đầu tại một trạng thái hợp lệ.

Nên tránh:

- Gửi email/network I/O không thuộc trách nhiệm construction.
- Đưa `this` vào global registry trước khi invariant hoàn tất.
- Gọi overridable methods khi subclass state chưa initialized.
- Tạo hidden database transactions nếu class chỉ đại diện value.
- Cho phép constructors với hàng chục optional parameters mà không làm rõ domain.

**Thiết kế constructor tốt xuất phát từ invariant và required collaborators**, không phải từ số field mà IDE muốn khởi tạo.

## 32. Ví dụ constructor kiểm điều kiện trước khi mutate state

Tạo **`RegistrationResponsibilityDemo.java`**:

```java
import java.util.Objects;

final class Registration {
    private final String username;
    private final int age;

    Registration(String username, int age) {
        String checkedName =
                Objects.requireNonNull(username, "username")
                        .trim();

        if (checkedName.isEmpty()) {
            throw new IllegalArgumentException("username");
        }
        if (age < 0) {
            throw new IllegalArgumentException("age");
        }

        this.username = checkedName;
        this.age = age;
    }

    String label() {
        return username + ":" + age;
    }
}

public class RegistrationResponsibilityDemo {
    public static void main(String[] args) {
        Registration a =
                new Registration("  Lan  ", 20);
        System.out.println(a.label());

        try {
            new Registration("   ", 21);
        } catch (IllegalArgumentException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

```bash
javac RegistrationResponsibilityDemo.java
java RegistrationResponsibilityDemo
```

```text
Lan:20
username
```

Lớp có trách nhiệm **giữ một registration hợp lệ và normalized**. Constructor làm rõ invariant; không cần expose setter cho username/age nếu requirements không cho phép thay sau creation.

Chọn chính sách trimming có chủ đích. Với usernames thật, normalization có thể có Unicode/case/security rules khác; bài học là **quy tắc thuộc về nơi sở hữu dữ liệu**.

## 33. Chọn method trả dữ liệu: giảm nguy cơ “đưa chìa khóa nhà”

Nếu class giữ mutable array:

```java
final class Measurements {
    private final int[] samples;

    Measurements(int[] samples) {
        this.samples = samples.clone();
    }

    int[] samples() {
        return samples.clone();
    }
}
```

Đây là **khai báo hợp lệ minh họa**: constructor và accessor đều clone primitive array, ngăn external aliases mutate state.

Trách nhiệm “giữ một snapshot số đo” dẫn đến:

- Input defensive copy.
- Output defensive copy.
- Không expose `setSamples`.
- Xác định null policy (mẫu chưa check null; null sẽ ném NullPointerException khi clone).
- Nếu cần equality theo contents, bổ sung appropriate `equals/hashCode` semantics.

**Không sao chép mọi thứ bằng phản xạ.** Nếu class biểu diễn shared mutable buffer có contract riêng, defensive copy có thể không phù hợp. Quan trọng là **ownership rõ và API giữ đúng trách nhiệm**.

## 34. Chọn cách đặt hành vi “nơi có đủ thông tin”

Một quy tắc chỉ dùng state của một object thường phù hợp đặt vào chính object ấy:

- `OrderLine.subtotal()` dùng unitPrice và quantity.
- `IntRange.contains(value)` dùng min và max.
- `Money.add(other)` kiểm cùng currency.

Một use case liên quan nhiều subsystems thường cần coordinator:

- Checkout cần inventory, payment, order persistence.
- Transfer cần hai accounts và transaction semantics.
- Send receipt cần data + outbound notification.

**Không có công thức “method luôn nằm ở object có nhiều fields nhất”.** Hãy hỏi object nào **sở hữu invariant**, ai có đủ thông tin, và điều gì sẽ thay đổi cùng quy tắc.

## 35. Đừng đặt business rule ở tầng giao diện chỉ vì dễ viết

Một HTTP controller có thể nhận request và kiểm **hình thức input** như số lượng, cấu trúc JSON, nhưng domain invariant quan trọng không nên chỉ nằm ở controller:

```java
// Controller:
if (request.quantity() <= 0) {
    // HTTP 400
}
```

Mảnh code này minh họa validation tại boundary, nhưng domain class cũng phải bảo vệ invariant của nó nếu có caller khác từ CLI, batch job hoặc tests.

**Hai lớp kiểm có thể cùng tồn tại:**

- Boundary validation → thông điệp lỗi dễ hiểu và response format đúng.
- Domain validation → không cho tồn tại domain state sai dù caller bỏ qua controller.

Trách nhiệm lớp miền không bị thay thế bằng một `if` ở UI.

## 36. Tránh “feature envy”: method ở class khác cứ đào fields nội bộ

Dấu hiệu:

```java
int total = 0;
for (CartLine line : cart.getLines()) {
    total += line.getQuantity() * line.getUnitPrice();
}
```

Đây là **mảnh minh họa** dùng getter giả định. Nếu nhiều callers đều tính total bằng cách đào Cart fields, nên cân nhắc `cart.total()` để gom logic và invariant vào nơi tự nhiên.

Nhưng nếu tổng phụ thuộc vào **tax, currency exchange, promotion policy** bên ngoài Cart, một `QuoteCalculator` hoặc service có thể phù hợp hơn; Cart không cần ôm mọi biến thể chính sách.

**Tư duy cân bằng:** Đưa hành vi gần state nó bảo vệ, nhưng không làm đối tượng phụ thuộc vào mọi chính sách môi trường.

## 37. Một responsibility có thể cần nhiều methods, và một method có thể dùng nhiều collaborators

Đừng suy luận:

- 1 trách nhiệm = 1 method.
- 1 class = 1 dependency.
- 1 use case = 1 class.
- 1 danh từ = 1 object.

Ví dụ ShoppingCart có add/total/lines; tất cả phục vụ trách nhiệm quản lý giỏ. CheckoutService có thể có dependencies vào Cart, Repository, PaymentGateway; chúng cùng phục vụ orchestration của **một use case**, miễn class không bắt đầu chứa pricing internals, SQL và email templating.

**Dấu hiệu tốt:** Có thể viết test cho hành vi của class bằng inputs/outputs và fake collaborators mà không phải gọi cả hệ thống.

## 38. Test từ trách nhiệm trước khi test fields

Một class có trách nhiệm “không cho rút vượt số dư” thì test nên kiểm:

1. Số dư ban đầu hợp lệ.
2. Deposit hợp lệ làm tăng số dư.
3. Withdraw hợp lệ làm giảm số dư.
4. Withdraw vượt balance bị từ chối.
5. Khi thao tác fail, state vẫn đúng.
6. Các edge cases như zero/negative amount được xử lý.

Không nên chỉ test getter/setter “set 5 rồi get 5” vì điều đó không chứng minh invariant.

### Runnable self-test cho BankAccount

Tạo **`AccountResponsibilitySelfTest.java`**:

```java
final class BankAccount {
    private long cents;

    BankAccount(long initialCents) {
        if (initialCents < 0) {
            throw new IllegalArgumentException("initial");
        }
        cents = initialCents;
    }

    void deposit(long amount) {
        requirePositive(amount);
        cents = Math.addExact(cents, amount);
    }

    void withdraw(long amount) {
        requirePositive(amount);
        if (amount > cents) {
            throw new IllegalArgumentException("insufficient");
        }
        cents -= amount;
    }

    long balance() {
        return cents;
    }

    private static void requirePositive(long amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
    }
}

public class AccountResponsibilitySelfTest {
    static void check(boolean result, String label) {
        if (!result) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        BankAccount account = new BankAccount(100);

        account.deposit(30);
        check(account.balance() == 130, "deposit");

        account.withdraw(20);
        check(account.balance() == 110, "withdraw");

        try {
            account.withdraw(200);
            throw new AssertionError("missing rejection");
        } catch (IllegalArgumentException expected) {
            check(account.balance() == 110,
                    "state unchanged on failure");
        }

        System.out.println("account responsibility PASS");
    }
}
```

```bash
javac AccountResponsibilitySelfTest.java
java AccountResponsibilitySelfTest
```

```text
account responsibility PASS
```

`check` tự ném AssertionError, không cần bật `-ea`. Test chứng minh hành vi trách nhiệm cơ bản, không chứng minh thread safety/transactional persistence trong ngân hàng thực.

## 39. Thiết kế để test không phải tạo interface cho mọi class

Một value object `Money` có thể test trực tiếp, không cần mock Money. Một stateful `ShoppingCart` có thể test trực tiếp với CartLine.

Một application service có external dependencies có thể cần interfaces/fakes để test.

Tạo **`CheckoutWithFakeDemo.java`**:

```java
interface OrderStore {
    void save(String id);
}

final class RecordingStore implements OrderStore {
    private String savedId;

    @Override
    public void save(String id) {
        savedId = id;
    }

    String savedId() {
        return savedId;
    }
}

final class Checkout {
    private final OrderStore store;

    Checkout(OrderStore store) {
        this.store = store;
    }

    void submit(String orderId) {
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("order id");
        }
        store.save(orderId);
    }
}

public class CheckoutWithFakeDemo {
    public static void main(String[] args) {
        RecordingStore fake = new RecordingStore();
        Checkout checkout = new Checkout(fake);

        checkout.submit("ORD-5");
        System.out.println(fake.savedId());
    }
}
```

```bash
javac CheckoutWithFakeDemo.java
java CheckoutWithFakeDemo
```

```text
ORD-5
```

**Điểm thiết kế:** Checkout có trách nhiệm validation/order submission orchestration; OrderStore có trách nhiệm lưu. Fake RecordingStore làm test không cần database. Interface tồn tại vì **boundary có nhiều cách triển khai**, không vì mọi class bắt buộc có interface.

## 40. Một use case có thể thay đổi: class thiết kế phải thích ứng

Ví dụ ban đầu tổng tiền chỉ là tổng các lines. Yêu cầu mới có VAT và mã giảm giá.

Có hai hướng:

1. Nếu rules nhỏ, ổn định và thuộc domain Cart, class Cart có thể tự xử lý sau khi thiết kế lại invariants.
2. Nếu policies thay đổi theo thị trường, campaign hoặc tenant, tách `PricingPolicy` nhận input từ Cart và trả quote phù hợp.

**Không chọn trước 15 strategies khi chưa có variation thực.** Nhưng cũng không đặt hàm `calculateAllTaxesAndEmailAndExport` vào ShoppingCart khi yêu cầu đã cho thấy lý do thay đổi độc lập.

### Ma trận thay đổi

| Khi requirement thay đổi | Nơi nên xem trước |
| --- | --- |
| Quantity phải lớn hơn 0 | CartLine/Cart |
| Đổi cách tính shipping | ShippingCost policy |
| Đổi email provider | ReceiptSender adapter |
| Đổi DB schema | OrderStore implementation |
| Đổi HTML invoice | Presentation/formatter |
| Thêm trạng thái đơn | Order lifecycle |
| Thêm currency policy | Money/pricing contract |
| Thay trang web checkout | UI/controller |
| Thêm retry gửi mail | Notification workflow |
| Thêm tax theo quốc gia | Tax/Pricing policy |

Ma trận này giúp kiểm xem trách nhiệm được đặt đúng: **thay đổi cùng một lý do nên tập trung**, thay đổi không liên quan không nên lan qua nhiều domain classes.

## 41. Chú ý data ownership khi đi qua nhiều lớp

Một service nhận `List<CartLine>` từ controller. Ai có quyền mutate list? Nếu Cart muốn giữ snapshot, constructor phải copy list; nếu Order cần ảnh chụp giá, có thể phải copy price fields vào OrderLine snapshot thay vì giữ tham chiếu tới mutable CatalogProduct.

Những câu hỏi thiết kế:

- Input là mutable hay immutable?
- Có giữ reference sau method return không?
- Ai sở hữu object được đưa vào?
- API trả view hay defensive copy?
- Domain invariant có bị external mutation phá không?
- Có cần phân biệt **live data** với **historical snapshot**?

**Trách nhiệm quyết định ownership**, ownership quyết định field representation, constructor copying và accessor behavior.

## 42. Biến dữ liệu có tên thành domain type khi có invariant chung

Một string có thể biểu diễn email, product ID, currency code, file path, order status... Nếu chỉ dùng `String` ở mọi nơi, dễ tráo nhầm những giá trị có nghĩa khác nhau.

Khi có validation hay operations lặp lại, cân nhắc value object:

Tạo **`ProductIdResponsibilityDemo.java`**:

```java
record ProductId(String value) {
    ProductId {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("product id");
        }
        value = value.trim();
    }
}

final class Product {
    private final ProductId id;
    private final String name;

    Product(ProductId id, String name) {
        this.id = java.util.Objects.requireNonNull(id);
        this.name = java.util.Objects.requireNonNull(name);
    }

    ProductId id() {
        return id;
    }

    String name() {
        return name;
    }
}

public class ProductIdResponsibilityDemo {
    public static void main(String[] args) {
        Product product =
                new Product(new ProductId("  SKU-7  "), "Pen");

        System.out.println(product.id().value());
        System.out.println(product.name());
    }
}
```

```bash
javac ProductIdResponsibilityDemo.java
java ProductIdResponsibilityDemo
```

```text
SKU-7
Pen
```

ProductId biểu diễn và bảo vệ **một định danh sản phẩm hợp lệ**. Không dùng chung với CustomerId chỉ vì cả hai đều là String. Tuy nhiên, không cần tạo wrapper cho mọi String nếu không có domain distinction đáng giá; cân nhắc độ rõ ràng và độ phức tạp.

## 43. Lớp chịu trách nhiệm đọc input không nhất thiết chịu trách nhiệm lưu domain state

Một CLI/HTTP controller có thể parse input và gọi service:

```text
CLI/HTTP adapter:
  "Đọc request, parse, trả lỗi giao thức"

Application service:
  "Điều phối use case"

Domain objects:
  "Giữ trạng thái và invariants"

Repository/gateway:
  "Lưu trữ và tích hợp hệ ngoài"
```

Đây là phân chia định hướng. Một số ứng dụng nhỏ có thể giản lược. Quan trọng là **business rules không bị giấu trong một nơi chỉ có hiệu lực cho một giao diện**, nếu hệ thống có nhiều entry points.

Nếu một ứng dụng ban đầu là CLI rồi thêm web API, domain model tốt giúp reuse logic mà không copy-paste validation từ CLI sang controller.

## 44. Cân bằng SOLID trong phạm vi Java Core

Một số nguyên lý liên quan:

- **SRP:** một class không gánh các lý do thay đổi không liên quan.
- **OCP:** thiết kế extension points theo nhu cầu; không bắt buộc mọi class mở inheritance.
- **LSP:** subtype cần giữ contract của base, nếu chọn inheritance.
- **ISP:** interfaces nhỏ, gắn capability rõ, không ép client dùng methods không cần.
- **DIP:** high-level policy có thể phụ thuộc abstraction ở infrastructure boundaries.

Nhưng ở bước đầu, đừng dùng acronym để thay thế tư duy. Với mỗi class hãy phát biểu:

> “Class này chịu trách nhiệm ___; nó phải giữ bất biến ___; nó hợp tác với ___; những thay đổi về ___ không nên buộc sửa nó.”

Một câu hoàn chỉnh như vậy hữu ích hơn việc đo số interfaces hay số methods theo chuẩn máy móc.

## 45. Khi nào không cần tạo thêm lớp?

Không phải mọi phép toán đều đòi type mới.

- Một phép tính thuần đơn giản dùng một lần có thể là private method.
- Một biến tạm để tăng khả năng đọc không cần class.
- Một DTO 2–3 fields không có invariant phức tạp có thể là record nhỏ.
- Một thao tác gắn chặt vào Order có thể là method của Order.
- Một quy tắc policy thay đổi riêng có thể cần class/interface độc lập.
- Một tập thao tác không có state có thể là utility function/library nếu không có domain abstraction giá trị.

**Tiêu chí:** Tách class khi có **trách nhiệm rõ, invariant riêng, vòng đời riêng, policy thay đổi độc lập hoặc nhu cầu reuse/test hợp lý**. Tránh cả god class lẫn “class cho mỗi dòng”.

## 46. Code review: so sánh trước và sau

### Trước: data bag với getters/setters tự do

```java
class SubscriptionData {
    public String status;
    public int remainingDays;
}
```

Caller có thể viết:

```java
subscription.status = "EXPIRED";
subscription.remainingDays = 365;
```

Đây là các **mảnh minh họa**; không bảo đảm status và remainingDays đồng bộ.

### Sau: trách nhiệm quản lý trạng thái

Một hướng là:

```java
final class Subscription {
    private int remainingDays;

    Subscription(int remainingDays) {
        if (remainingDays < 0) {
            throw new IllegalArgumentException("days");
        }
        this.remainingDays = remainingDays;
    }

    void consumeDay() {
        if (remainingDays > 0) {
            remainingDays--;
        }
    }

    boolean expired() {
        return remainingDays == 0;
    }
}
```

Status `expired` được **suy ra** từ remainingDays, không phải một string field dễ lệch trạng thái.

**Nhưng:** Nếu domain cần trạng thái SUSPENDED/CANCELLED không thể suy ra từ days, phải có state model khác. Không nên cố loại field state chỉ để đạt “ít fields”. Hãy để **nghiệp vụ quyết định representation**.

## 47. Chương trình runnable: state tối thiểu của Subscription

Tạo **`SubscriptionResponsibilityDemo.java`**:

```java
final class Subscription {
    private int remainingDays;

    Subscription(int remainingDays) {
        if (remainingDays < 0) {
            throw new IllegalArgumentException("days");
        }
        this.remainingDays = remainingDays;
    }

    void consumeDay() {
        if (remainingDays > 0) {
            remainingDays--;
        }
    }

    boolean expired() {
        return remainingDays == 0;
    }

    int remainingDays() {
        return remainingDays;
    }
}

public class SubscriptionResponsibilityDemo {
    public static void main(String[] args) {
        Subscription subscription = new Subscription(2);

        System.out.println(subscription.expired());
        subscription.consumeDay();
        subscription.consumeDay();
        subscription.consumeDay();

        System.out.println(subscription.remainingDays());
        System.out.println(subscription.expired());
    }
}
```

```bash
javac SubscriptionResponsibilityDemo.java
java SubscriptionResponsibilityDemo
```

```text
false
0
true
```

Không có setter public hoặc duplicate status field. Method consumeDay không cho remainingDays âm. Đây là ví dụ trách nhiệm “quản lý số ngày còn lại và trạng thái hết hạn” dẫn trực tiếp tới field và methods tối thiểu.

## 48. Refactor theo trách nhiệm: một quy trình an toàn

Khi class hiện tại đã rất lớn, tránh rewrite toàn bộ một lượt. Có thể đi theo các bước:

1. **Liệt kê behaviors đang có**, không chỉ fields.
2. Viết mô tả **trách nhiệm và invariants** mà các behaviors thực hiện.
3. Nhóm members theo lý do thay đổi, objects dữ liệu liên quan và external dependencies.
4. Viết regression tests cho observable behavior hiện tại.
5. Chọn một responsibility độc lập (ví dụ email rendering) để extract.
6. Giữ contracts tương thích hoặc tạo adapters khi refactor.
7. Chuyển ownership của state và methods sao cho không còn public mutable aliases.
8. Update callers từng bước.
9. Kiểm code flow khi exception/concurrency xảy ra.
10. Review class cũ có còn trách nhiệm rõ không; tránh class mới chỉ forwarding vô nghĩa.
11. Đo test complexity và coupling trước/sau thay đổi.
12. Chỉ tối ưu performance khi đã có bằng chứng; refactor có thể thay allocation và interfaces.

**Không refactor chỉ vì “class hơn 300 dòng”.** Dòng code là tín hiệu có thể xem xét, nhưng trách nhiệm và mức gắn kết mới quyết định.

## 49. Bài tập 1: chọn trách nhiệm từ câu chuyện đặt phòng

Yêu cầu:

> Khách chọn phòng và ngày lưu trú; hệ thống kiểm ngày hợp lệ, tính giá theo chính sách mùa, xác nhận booking, lưu DB và gửi email.

Hãy xác định trách nhiệm ứng viên trước khi viết fields.

### Một lời giải hợp lý

| Trách nhiệm | Type gợi ý |
| --- | --- |
| Ngày bắt đầu/trả phòng hợp lệ | `StayPeriod` value object |
| Identity và lifecycle đặt phòng | `Booking` entity |
| Giá theo mùa/loại phòng | `PricingPolicy` |
| Điều phối xác nhận | `BookingService` |
| Lưu đơn | `BookingRepository` |
| Gửi xác nhận | `ConfirmationSender` |
| Nhận HTTP và trả status | `BookingController` |

Không bắt buộc tất cả classes nếu bài tập nhỏ. **Câu hỏi kiểm tra:** Nếu đổi email provider, có phải sửa cách tính giá phòng không? Nếu câu trả lời “có”, ranh giới responsibilities có thể đang sai.

### State sau cùng

`StayPeriod` có thể giữ arrival/departure và kiểm departure sau arrival. `Booking` giữ bookingId/status/period, không nên giữ trực tiếp JDBC connection chỉ để “tiện lưu”.

## 50. Bài tập 2: trước khi chọn field `total`

Giỏ hàng có `List<CartLine>` và field `int total`. Khi thêm/bớt item, lập trình viên luôn phải cập nhật total. Hãy hỏi:

- Total có **được tính lại** từ lines dễ dàng không?
- Có cần query total rất thường xuyên với dữ liệu lớn không?
- Nếu cache total, ai invalidates?
- Khi update thất bại, total và lines còn nhất quán không?
- Có tax/discount phụ thuộc thời gian hoặc cấu hình ngoài Cart không?

**Hướng giải:** Đầu tiên tính total từ lines. Chỉ thêm cached total khi có nhu cầu và thiết kế rõ invariants/atomic updates. Field không nên được tạo chỉ vì “màn hình cần hiển thị total”.

## 51. Bài tập 3: đặt method đúng nơi

Cho các thao tác:

- `order.cancel()`
- `sendEmail(order)`
- `orderRepository.save(order)`
- `money.add(otherMoney)`
- `parseHttpRequest(body)`
- `shoppingCart.total()`

Hãy chia:

| Hành vi | Owner thường hợp lý | Lý do |
| --- | --- | --- |
| Hủy order nếu trạng thái cho phép | Order | State transition invariant |
| Gửi email | NotificationSender/Gateway | I/O và provider |
| Lưu order | OrderRepository | Persistence |
| Cộng tiền cùng currency | Money | Value invariant |
| Parse request | HTTP adapter/parser | Giao thức bên ngoài |
| Tính tổng của lines | ShoppingCart | Dữ liệu state do Cart sở hữu |

**Lưu ý:** Giá có promotion/tax đặc biệt có thể cần pricing service, không nên ép mọi loại total vào Cart.

## 52. Bài tập 4: kiểm thử class mà không đo getters

Đề bài: `Ticket` có sức chứa tối đa, khi bán vé không được vượt capacity. Thiết kế trách nhiệm rồi triển khai.

### Lời giải runnable

Tạo **`TicketResponsibilityExercise.java`**:

```java
final class TicketInventory {
    private final int capacity;
    private int sold;

    TicketInventory(int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity");
        }
        this.capacity = capacity;
    }

    void sell(int quantity) {
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity");
        }
        if (quantity > capacity - sold) {
            throw new IllegalStateException("not enough seats");
        }
        sold += quantity;
    }

    int remaining() {
        return capacity - sold;
    }
}

public class TicketResponsibilityExercise {
    public static void main(String[] args) {
        TicketInventory inventory = new TicketInventory(5);

        inventory.sell(2);
        System.out.println(inventory.remaining());

        try {
            inventory.sell(4);
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }

        System.out.println(inventory.remaining());
    }
}
```

```bash
javac TicketResponsibilityExercise.java
java TicketResponsibilityExercise
```

```text
3
not enough seats
3
```

Trách nhiệm `TicketInventory` là bảo đảm `0 <= sold <= capacity`. Vì vậy fields cần là capacity/sold; methods cần là sell/remaining và constructor validation. Không cần public setters cho sold/capacity.

**Phạm vi:** Ví dụ đơn luồng. Bán vé đồng thời đòi synchronization/transaction phù hợp; không thể dựa vào một `if` không atomic trong nhiều threads hoặc processes.

## 53. Self-test: class bảo vệ invariant qua nhiều thao tác

Tạo **`InventoryInvariantSelfTest.java`**:

```java
final class Inventory {
    private final int capacity;
    private int used;

    Inventory(int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity");
        }
        this.capacity = capacity;
    }

    void allocate(int amount) {
        if (amount <= 0) {
            throw new IllegalArgumentException("amount");
        }
        if (amount > capacity - used) {
            throw new IllegalStateException("full");
        }
        used += amount;
    }

    void release(int amount) {
        if (amount <= 0 || amount > used) {
            throw new IllegalArgumentException("release");
        }
        used -= amount;
    }

    int available() {
        return capacity - used;
    }
}

public class InventoryInvariantSelfTest {
    static void check(boolean condition, String label) {
        if (!condition) {
            throw new AssertionError(label);
        }
    }

    public static void main(String[] args) {
        Inventory inventory = new Inventory(10);

        inventory.allocate(6);
        check(inventory.available() == 4, "allocate");

        inventory.release(2);
        check(inventory.available() == 6, "release");

        try {
            inventory.allocate(7);
            throw new AssertionError("expected full");
        } catch (IllegalStateException expected) {
            check(inventory.available() == 6,
                    "no partial update");
        }

        System.out.println("inventory invariant PASS");
    }
}
```

```bash
javac InventoryInvariantSelfTest.java
java InventoryInvariantSelfTest
```

```text
inventory invariant PASS
```

`Inventory` chịu trách nhiệm số lượng đã phân phối không vượt capacity và không xuống âm. Tests kiểm hành vi và invariant, không chỉ “field có getter”. `check` ném AssertionError trực tiếp, nên không cần `-ea`.

## 54. Một checklist theo thứ tự trước khi gõ `class`

### A. Hiểu domain

- [ ] Tôi có thể diễn đạt use case thành một kết quả quan sát được không?
- [ ] Tôi đã xác định actors, inputs, outputs và failure cases?
- [ ] Tôi biết những quy tắc không bao giờ được vi phạm?
- [ ] Tôi đã phân biệt dữ liệu gốc, dữ liệu suy ra và dữ liệu bên ngoài?

### B. Xác định trách nhiệm

- [ ] Mỗi class ứng viên có một mục đích có thể viết thành một câu?
- [ ] Tôi biết ai sở hữu từng invariant?
- [ ] Tôi có thể mô tả lý do class này phải thay đổi?
- [ ] Class không trộn domain rules với persistence/UI/I/O khi chúng thay đổi độc lập?
- [ ] Tôi chưa tách lớp chỉ vì method dài 10 dòng hay class có nhiều methods?
- [ ] Tôi chưa chọn chữ `Manager` chỉ vì không xác định được responsibility?

### C. Chọn cấu trúc

- [ ] Tôi đã xét entity, value object, service, repository, adapter, DTO tùy domain?
- [ ] Có cần class hay record là đủ?
- [ ] Có cần interface thực sự hay chỉ thêm boilerplate?
- [ ] Có nên dùng composition thay inheritance?
- [ ] Các dependencies có đi qua boundary cần thiết không?
- [ ] Ai sở hữu lifecycle của external collaborators/resources?

### D. Sau đó mới thiết kế members

- [ ] Field nào thật sự cần để hoàn thành trách nhiệm?
- [ ] Field nào suy ra được nên không phải lưu?
- [ ] Fields có `private` và immutable khi phù hợp?
- [ ] Constructor kiểm đúng required invariants?
- [ ] Method names diễn tả hành vi nghiệp vụ?
- [ ] Public setter có phá invariant hoặc ownership không?
- [ ] Collection/array mutable có bị lộ reference ra ngoài không?
- [ ] Failure path có giữ state nhất quán không?
- [ ] API rõ null policy, overflow, exceptions, concurrency scope?
- [ ] Mỗi public method có contract có thể test?

### E. Kiểm tra và chỉnh thiết kế

- [ ] Tests bắt nguồn từ responsibility chứ không chỉ getters/setters?
- [ ] Có example success và failure?
- [ ] Có thể test class không cần toàn hệ thống?
- [ ] Thay database/email provider có làm domain model phải đổi không?
- [ ] Khi thêm feature mới, trách nhiệm sẽ mở rộng hợp lý hay biến thành god class?
- [ ] Đang overengineering thành hàng chục class không có purpose rõ?
- [ ] Tôi có thể giải thích thiết kế bằng ngôn ngữ domain cho người khác?

## 55. Những sai lầm thường gặp

| Sai lầm | Vì sao nguy hiểm | Hướng sửa |
| --- | --- | --- |
| Chọn fields trước khi hiểu use case | State không phục vụ domain | Viết responsibilities/invariants trước |
| Class chỉ có setters mặc định | Caller phá state hợp lệ | Expose domain methods |
| God class làm SQL, email, UI, pricing | Coupling cao, nhiều lý do thay đổi | Tách boundaries hợp lý |
| Tách một class cho từng method | Over-fragmentation | Nhóm behavior cùng invariant |
| Public mutable list getter | Caller bỏ qua validation | Snapshot/controlled methods |
| Lưu field total dù suy ra từ lines | Dễ lệch dữ liệu | Derived method, cache khi có chính sách |
| Dùng `double` cho money vô tư | Precision/currency issues | Money domain type |
| Chỉ validate ở controller | Batch/CLI callers vượt qua domain rules | Domain invariants ở domain object |
| Method `saveToDatabase` trong value object | Storage concern không thuộc value | Repository/adapter |
| Interface cho mọi class | Boilerplate, abstraction giả | Interface khi có contract/variation |
| Dùng inheritance cho mọi reuse | Coupling/subtype contract khó bảo vệ | Composition khi phù hợp |
| Dùng `static` làm nơi chứa state chung | Ownership/lifecycle mờ | Scoped object hoặc service có policy |
| Constructor công bố `this` sớm | Partially initialized objects | Hoàn tất invariants trước publication |
| Method trả mutable array internals | State bị sửa ngoài kiểm soát | Defensive copying/contract |
| Không tính failure path | State dở dang, resource leak | Atomic operations/cleanup |
| Cho domain entity biết HTTP/database details | Khó test, thay technology gây domino | Phân tách adapter |
| Nhầm DTO mỏng với domain object | Đẩy bừa logic qua boundary | Rõ vai trò từng model |
| Tạo class chỉ theo danh từ | Quá nhiều cấu trúc không ý nghĩa | Tìm behavior/ownership |
| Test chỉ getter/setter | Không bảo vệ business invariants | Test success/failure/state |
| Một method dài nên nhất định tạo class | Dễ tách vụn cohesion | Extract method/class theo trách nhiệm |
| Quy định class phải dưới N dòng | Metric không phản ánh trách nhiệm | Xem reasons to change và coupling |
| Không xác định giao dịch giữa hai entities | Partial updates có thể sai | Transaction boundary rõ |
| Tưởng private fields đủ để đúng domain | Private không tự validate | Constructor/domain commands |

## 56. Câu hỏi ôn tập có đáp án

**1.** Vì sao chọn trách nhiệm trước fields/methods?

*Vì trách nhiệm quyết định state nào cần giữ, invariant nào phải bảo vệ và behaviors nào thuộc về class. Làm ngược dễ sinh mutable data bag hoặc class làm quá nhiều.*

**2.** Trách nhiệm có phải tên method không?

*Không. Trách nhiệm là nghĩa vụ có ý nghĩa như quản lý giỏ hàng và bảo vệ quantity; methods là cách thực hiện nghĩa vụ đó.*

**3.** Một class có bảy methods có vi phạm SRP không?

*Không mặc nhiên. Nếu bảy methods phục vụ một cohesive responsibility thì vẫn hợp lý.*

**4.** Tại sao public setter cho `balance` có thể là thiết kế yếu?

*Caller có thể bỏ qua quy tắc rút/nạp, đưa balance vào trạng thái không hợp lệ.*

**5.** Method `withdraw` nên nằm ở đâu?

*Thường ở Account vì Account sở hữu invariant số dư.*

**6.** Ai nên xử lý chuyển tiền giữa hai Accounts?

*Một thành phần có trách nhiệm điều phối và bảo đảm transaction semantics; Account vẫn giữ invariant từng tài khoản.*

**7.** Khi nào không cần field total?

*Khi total là giá trị dẫn xuất từ lines, tính lại đủ rẻ và dễ giữ nhất quán.*

**8.** Khi nào có thể cân nhắc cached total field?

*Khi có yêu cầu hiệu năng thực, có chính sách cập nhật/invalidation đúng và tests bảo đảm invariant.*

**9.** Vì sao Cart không nên expose mutable List nội bộ?

*Caller có thể sửa state mà Cart không kiểm.*

**10.** Domain model khác DTO ở điểm nào?

*Domain model có thể chịu invariants/behavior; DTO chủ yếu vận chuyển dữ liệu theo boundary contract.*

**11.** Record có luôn phù hợp entity identity/lifecycle không?

*Không; record thường thích hợp value-oriented carrier, còn entity mutable có thể cần class với lifecycle rõ.*

**12.** Vì sao Money có thể là một value object?

*Nó gắn amount với currency, kiểm compatibility và định nghĩa arithmetic semantics.*

**13.** Vì sao Invoice không nên trực tiếp gửi SMTP?

*Thông báo qua provider là một trách nhiệm infrastructure thay đổi độc lập với giá trị hóa đơn.*

**14.** Repository chịu trách nhiệm gì?

*Lưu và truy xuất dữ liệu/domain aggregates qua một contract phù hợp.*

**15.** Application service có vai trò gì?

*Điều phối một use case và các collaborators, không nhất thiết sở hữu mọi business rule.*

**16.** Tại sao không tạo interface cho mọi class?

*Interface chỉ có giá trị khi có một contract/variation/boundary thực sự, không phải chỉ để có thêm file.*

**17.** Cohesion tốt nghĩa là gì?

*Các members hợp tác phục vụ mục tiêu/invariant liên quan chặt chẽ.*

**18.** Coupling cao gây hậu quả gì?

*Một thay đổi lan qua nhiều classes, khó test và khó thay collaborators.*

**19.** Có thể dùng composition để tránh mở inheritance không?

*Có. Một final class có thể nhận strategy/interface để biến đổi behavior.*

**20.** Constructor nên bắt nguồn từ đâu?

*Từ required data/dependencies và invariants cần bảo vệ khi tạo object.*

**21.** Nếu một class có nhiều nhóm methods không dùng chung state, nên xem xét gì?

*Có thể đang gộp nhiều trách nhiệm; thử nhóm theo lý do thay đổi và extract boundary phù hợp.*

**22.** Khi nào không nên tách class?

*Khi logic nhỏ, chỉ phục vụ một trách nhiệm hiện có, và extraction chỉ làm tăng forwarding/coupling.*

**23.** Trách nhiệm của lớp có liên quan tới access modifiers không?

*Có. Lớp sở hữu invariant nên giới hạn những đường bên ngoài có thể sửa state.*

**24.** Vì sao phải test khi thao tác thất bại?

*Để xác nhận object không bị để lại ở trạng thái dở dang và invariant vẫn đúng.*

**25.** Một field `static` có luôn sai không?

*Không. Sai khi lifecycle/ownership hoặc phạm vi chia sẻ không phù hợp; static có thể đúng cho constants hoặc shared services có contract rõ.*

**26.** Nên chọn class theo số danh từ trong yêu cầu không?

*Không. Cần xem dữ liệu, behavior, invariants, identity và lý do thay đổi.*

**27.** Trong bài giỏ hàng, CartLine và Cart phân trách nhiệm thế nào?

*CartLine giữ một dòng hợp lệ/tính subtotal; Cart sở hữu tập dòng và thao tác trên giỏ.*

**28.** Business validation ở controller có thay thế validation trong domain model không?

*Không, nếu domain invariant phải giữ với mọi entry points.*

**29.** Bảng “một lý do thay đổi” có phải luật toán học không?

*Không. Nó là công cụ review ranh giới trách nhiệm theo stakeholders/reasons, cần dùng phán đoán.*

**30.** Câu hỏi đầu tiên cần trả lời trước khi viết field là gì?

*“Object/class này phải chịu trách nhiệm bảo vệ hoặc thực hiện điều gì, và vì sao nó là owner tự nhiên của trách nhiệm đó?”*

## 57. Tài liệu tham khảo hướng đọc thêm

- *The Java Language Specification, Java SE 17*: https://docs.oracle.com/javase/specs/jls/se17/html/index.html — quy tắc class, object, constructors, methods và access control.
- *Java SE 17 API – `java.lang.Record`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html — tính chất record ở mức ngôn ngữ/API.
- *Java SE 17 API – `List.copyOf`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html — unmodifiable snapshot semantics.
- *Java SE 17 API – `Math.addExact` / `multiplyExact`*: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html — fail-fast khi số nguyên tràn.

Các tài liệu nguyên lý thiết kế hướng đối tượng như SRP, GRASP (*Information Expert*, *Creator*, *Controller*, *Low Coupling*, *High Cohesion*) có thể giúp hệ thống hóa cách suy nghĩ, nhưng không thay cho việc phân tích **use case, invariants và ownership thực tế** của dự án.

---

**Ghi nhớ cuối bài:** Đừng bắt đầu thiết kế Java class bằng câu hỏi “class này có bao nhiêu fields/getters/setters?”. Hãy bắt đầu từ **trách nhiệm có ý nghĩa**, những **bất biến** không được vi phạm, **ai sở hữu state**, và **lý do thay đổi**. Từ đó mới chọn class/record/interface/service, fields tối thiểu, constructor validation và methods diễn tả hành vi nghiệp vụ. Đặt operations gần state và invariants mà chúng bảo vệ; tách persistence, presentation và external I/O khi chúng thay đổi độc lập; dùng collaboration/composition để tránh class ôm mọi việc. **Không cực đoan** tách một method thành một class hoặc tạo interface cho mọi đối tượng. Một thiết kế tốt cho phép nói rõ “class này chịu trách nhiệm gì, không chịu trách nhiệm gì”, và cho phép kiểm điều ấy bằng tests thành công, tests thất bại và các invariants có thể quan sát.