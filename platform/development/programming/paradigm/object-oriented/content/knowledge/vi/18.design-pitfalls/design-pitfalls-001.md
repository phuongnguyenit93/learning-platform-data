# Lớp ôm quá nhiều trách nhiệm (God Class): nhận biết và refactor đúng cách

> **Chủ đề:** OOP → Lỗi thiết kế → Lớp ôm quá nhiều trách nhiệm.  
> **Mục tiêu:** Hiểu vì sao một lớp có thể trở thành điểm nghẽn bảo trì, phân biệt “lớp dài” với “lớp nhiều trách nhiệm”, phát hiện các dấu hiệu qua lý do thay đổi và mức liên kết giữa các phương thức, rồi refactor bằng Java thành các phần có ranh giới rõ mà vẫn giữ nguyên hành vi nghiệp vụ.

## 1. “Lớp ôm quá nhiều trách nhiệm” nghĩa là gì?

**God Class** (đôi khi gọi *Blob*, *Large Class* hoặc *Bloaters* trong các phân loại code smell) là một dấu hiệu thiết kế: một lớp gom quá nhiều việc đáng lẽ cần thay đổi, kiểm thử và phát triển tương đối độc lập. Nó có thể biết quá nhiều về các phần còn lại của hệ thống, chứa lượng lớn trạng thái không liên quan và điều phối mọi thay đổi thông qua chính mình.

Ví dụ một `OrderManager` vừa:

- xác thực dữ liệu đơn hàng;
- tính giá, thuế và khuyến mãi;
- lưu đơn vào database;
- gọi cổng thanh toán;
- gửi email thông báo;
- tạo PDF hóa đơn;
- định dạng dữ liệu cho REST API.

Chỉ cần đổi công thức thuế, đổi hệ quản trị cơ sở dữ liệu hoặc sửa template email đều có thể phải mở cùng file `OrderManager.java`. Những thay đổi có **nguyên nhân khác nhau** va chạm trong một lớp.

Vấn đề chính không phải “bao nhiêu dòng là quá nhiều?”. **Một lớp 500 dòng xử lý một thuật toán có tính gắn kết cao có thể hợp lý**, trong khi một lớp 100 dòng vừa tính thuế, gửi email và gọi HTTP có thể đã có quá nhiều trách nhiệm.

Một tiêu chí thực tế là **lý do để thay đổi**: lớp có đang phải thay đổi vì nhiều quyết định nghiệp vụ hoặc nhiều nhóm người/phần hệ thống khác nhau hay không?

## 2. Vì sao kiểu thiết kế này xuất hiện?

Lúc ban đầu, để hoàn thành nhanh một chức năng, người viết thường đặt validation, tính toán, persistence và notification vào một phương thức. Khi có yêu cầu mới, họ bổ sung thêm một nhánh `if` hoặc một dependency vào cùng lớp vì “mọi thứ liên quan đơn hàng đã ở đây”.

Qua thời gian, lớp dần trở thành điểm tập trung kiến thức:

~~~mermaid
flowchart LR
    C["OrderManager"]
    C --> V["Validation"]
    C --> P["Pricing / Tax"]
    C --> D["Database"]
    C --> M["Email / SMS"]
    C --> F["PDF / CSV"]
    C --> A["API response"]
    C --> T["Payment gateway"]
~~~

Các trách nhiệm này cùng liên quan đến **đơn hàng**, nhưng không nhất thiết cùng một **lý do để thay đổi**. Chỉ dùng một tên miền nghiệp vụ chung như `Order` không chứng minh rằng chúng phải nằm trong một lớp.

Một số nguyên nhân phổ biến là thiếu ranh giới module, sợ tạo thêm lớp, copy-paste, sự phụ thuộc trực tiếp vào framework hoặc SDK, deadline gấp, và quá ít kiểm thử để refactor an toàn.

### Phân biệt thuật ngữ

| Thuật ngữ | Trọng tâm | Quan hệ với God Class |
|---|---|---|
| **God Class / Blob** | Biết và làm quá nhiều việc, thường ảnh hưởng rộng | Dạng điển hình của lớp ôm nhiều trách nhiệm |
| **Large Class** | Kích thước lớn: nhiều dòng, field, method | Một dấu hiệu để điều tra, **chưa đủ** kết luận |
| **Low Cohesion** | Các field/method không cùng phục vụ một mục đích nhất quán | Bằng chứng khá mạnh nếu đi kèm nhiều lý do thay đổi |
| **High Coupling** | Phụ thuộc trực tiếp vào nhiều class hoặc module khác | Làm phạm vi ảnh hưởng của thay đổi lớn hơn |
| **SRP violation** | Một module phục vụ nhiều actor/lý do thay đổi độc lập | Cách diễn giải nguyên lý thiết kế đằng sau nhiều God Class |
| **Anemic Domain Model** | Domain object ít hành vi nghiệp vụ, logic dồn vào service | Có thể đi cùng God Service, nhưng là vấn đề khác |

Một class dài **không đương nhiên** là God Class. Ngược lại, một lớp “manager” rất ngắn nhưng chuyển hàng chục yêu cầu cho các API khác nhau cũng có thể là trung tâm phụ thuộc quá rộng.

## 3. Dấu hiệu nhận biết qua code và lịch sử thay đổi

Quan sát mã nguồn và hỏi:

| Dấu hiệu | Ví dụ | Hệ quả |
|---|---|---|
| Nhiều lý do sửa cùng một file | Đổi thuế, SQL, email đều sửa `OrderManager` | Merge conflict, review khó, regression khó khoanh vùng |
| Field thành từng nhóm tách biệt | `dbConnection`, `mailClient`, `pdfWriter`, `taxRate` | Trạng thái của lớp có thể không cùng phục vụ một mục đích |
| Phương thức không dùng chung dữ liệu | `sendEmail()` không dùng dữ liệu của `calculateTax()` | Tính gắn kết thấp |
| Public API phình to | `createOrder`, `exportCsv`, `resetPassword`, `syncWarehouse` | Client phải nhìn thấy nhiều năng lực không cần thiết |
| Branch và side effect trộn lẫn | Tính giá giữa các lệnh gọi DB và HTTP | Test chậm, khó tái hiện lỗi |
| Khó khởi tạo trong unit test | Muốn test phép cộng phải cấu hình DB/mail/SDK | Trách nhiệm chưa được cô lập |
| Thay đổi nhỏ gây ảnh hưởng rộng | Sửa email template làm test tính giá lỗi | Ranh giới giữa các việc yếu |

Dấu hiệu mạnh nhất thường là **nhiều thay đổi không liên quan liên tục chạm cùng một lớp**. Khi audit, nên xem lịch sử thay đổi, các use case thực tế và dependency graph; không vội đoán chỉ từ tên `*Manager` hoặc `*Service`.

### “Một trách nhiệm” không đồng nghĩa “một phương thức”

Theo **Single Responsibility Principle (SRP)**, một module nên có một lý do thay đổi có tính nhất quán. Một `PriceCalculator` vẫn có thể có các phương thức `calculateSubtotal`, `calculateDiscount`, `calculateTax` nếu chúng cùng thuộc **chính sách tính giá** và thực sự thay đổi cùng nhau.

Ngược lại, chia một method 100 dòng thành 10 private methods **không tự giải quyết God Class** nếu cùng một lớp vẫn làm cả tính tiền, SQL và SMTP.

## 4. Mã có mùi thiết kế: tất cả trong một lớp

Đoạn sau là **ví dụ cố ý chưa tốt**, minh họa một ứng dụng đặt hàng:

~~~java
import java.math.BigDecimal;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record Item(String sku, int quantity, BigDecimal unitPrice) {}

final class AllInOneOrderService {
    private final Map<String, BigDecimal> fakeDatabase = new HashMap<>();

    String placeOrder(
            String orderId, String email, List<Item> items) {

        // 1. Validate input.
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing order ID");
        }

        // 2. Calculate price.
        BigDecimal total = BigDecimal.ZERO;
        for (Item item : items) {
            total = total.add(item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())));
        }

        // 3. Persist (giả lập).
        fakeDatabase.put(orderId, total);

        // 4. Notify (giả lập).
        System.out.println("[DEMO MAIL] " + email + ": " + orderId);

        // 5. Format text for a caller.
        return "Order " + orderId + " total = " + total;
    }
}
~~~

Đây là một snippet minh họa *code smell*, **không phải triển khai production**: nó chưa validate `items`, số lượng, đơn giá, trùng mã đơn và lỗi khi gửi thông báo. Những thiếu sót đó cũng thể hiện một vấn đề: càng nhiều việc nằm trong cùng hàm, càng dễ bỏ sót hợp đồng ở các ranh giới.

Giả sử cần đổi email sang SMS. Ta phải sửa chính lớp chứa công thức tính giá. Nếu thay `HashMap` bằng JPA, vẫn sửa cùng lớp. Nếu muốn unit test giá của hai mặt hàng mà không sinh thông báo, test phải tìm cách né side effect.

Có thể thêm hàng loạt private method, nhưng **các nguyên nhân thay đổi vẫn sống chung trong `AllInOneOrderService`**.

## 5. Thiết kế lại: chia theo ranh giới trách nhiệm

Một hướng refactor là giữ một **use case điều phối** tương đối mỏng, còn các chính sách và tích hợp độc lập được đặt ở đúng nơi:

~~~mermaid
flowchart TD
    UI["Caller / Controller"] --> UC["PlaceOrderUseCase"]
    UC --> PR["PriceCalculator"]
    UC --> REPO["OrderRepository (port)"]
    UC --> NOTI["OrderNotifier (port)"]
    MEMORY["InMemoryOrderRepository"] -.->|"implements"| REPO
    MAIL["ConsoleOrderNotifier"] -.->|"implements"| NOTI
    DB["Adapter DB thật sau này"] -.->|"implements"| REPO
~~~

Cách chia này có ý nghĩa cụ thể:

- **`PriceCalculator`:** tính số tiền từ các mặt hàng, không biết database hoặc người nhận email.
- **`OrderRepository`:** hợp đồng lưu kết quả đơn hàng; adapter quyết định lưu vào đâu.
- **`OrderNotifier`:** hợp đồng phát thông báo; adapter quyết định dùng email/SMS/log demo.
- **`PlaceOrderUseCase`:** chịu trách nhiệm **quy trình đặt hàng**: nhận yêu cầu hợp lệ → tính tiền → tạo kết quả → yêu cầu lưu → yêu cầu thông báo.
- **Composition root:** tạo và nối các đối tượng; đây là nơi được phép biết implementation hạ tầng.

**Lưu ý:** Việc use case gọi nhiều cộng tác viên không tự động khiến nó thành God Class. **Điều phối các bước của một use case** có thể là **một trách nhiệm gắn kết**. Vấn đề xuất hiện khi use case tự chứa logic SQL, quy tắc giá, SMTP, PDF và vô số use case không liên quan.

## 6. Ví dụ Java 17 hoàn chỉnh, chạy độc lập

Ví dụ này dùng đơn vị tiền có hai chữ số thập phân để dễ quan sát phép tính; **quy ước làm tròn và đơn vị tiền** trong ứng dụng thật phải do yêu cầu nghiệp vụ xác định. Các adapter là mô phỏng tại bộ nhớ/console, không có tác vụ gửi email hoặc ghi database thật.

Lưu vào **`ResponsibilityDemo.java`**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

// Value object: quy tắc hợp lệ của một mặt hàng.
record OrderItem(String sku, int quantity, BigDecimal unitPrice) {
    OrderItem {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (!sku.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid sku");
        }
        if (quantity <= 0 || unitPrice.signum() < 0) {
            throw new IllegalArgumentException(
                    "Invalid quantity or price");
        }

        try {
            unitPrice = unitPrice.setScale(
                    2, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException(
                    "Unit price has fractions below 0.01", ex);
        }
    }
}

// Dữ liệu đầu vào của một use case.
record PlaceOrderRequest(
        String orderId,
        String customerEmail,
        List<OrderItem> items) {
    PlaceOrderRequest {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(customerEmail, "customerEmail");
        Objects.requireNonNull(items, "items");

        if (!orderId.matches("[A-Z0-9-]+")) {
            throw new IllegalArgumentException("Invalid order ID");
        }
        if (customerEmail.isBlank()) {
            throw new IllegalArgumentException("Missing email");
        }
        items = List.copyOf(items);
        if (items.isEmpty()) {
            throw new IllegalArgumentException("Empty order");
        }
    }
}

record OrderReceipt(String orderId, BigDecimal total) {}

// Chính sách tính tiền: không biết lưu trữ hoặc thông báo.
final class PriceCalculator {
    BigDecimal calculate(List<OrderItem> items) {
        Objects.requireNonNull(items, "items");

        BigDecimal total = BigDecimal.ZERO.setScale(2);
        for (OrderItem item : items) {
            total = total.add(item.unitPrice()
                    .multiply(BigDecimal.valueOf(item.quantity())));
        }
        return total;
    }
}

// Hai port mô tả những việc use case cần.
interface OrderRepository {
    void save(OrderReceipt receipt);
}

interface OrderNotifier {
    void orderPlaced(String customerEmail, OrderReceipt receipt);
}

// Use case: giữ trình tự nghiệp vụ, không chứa công thức/SDK.
final class PlaceOrderUseCase {
    private final PriceCalculator calculator;
    private final OrderRepository repository;
    private final OrderNotifier notifier;

    PlaceOrderUseCase(
            PriceCalculator calculator,
            OrderRepository repository,
            OrderNotifier notifier) {
        this.calculator = Objects.requireNonNull(
                calculator, "calculator");
        this.repository = Objects.requireNonNull(
                repository, "repository");
        this.notifier = Objects.requireNonNull(
                notifier, "notifier");
    }

    OrderReceipt execute(PlaceOrderRequest request) {
        Objects.requireNonNull(request, "request");

        BigDecimal total = calculator.calculate(request.items());
        OrderReceipt receipt = new OrderReceipt(
                request.orderId(), total);

        // Quy trình có thứ tự rõ, mỗi dependency sở hữu một việc.
        repository.save(receipt);
        notifier.orderPlaced(request.customerEmail(), receipt);
        return receipt;
    }
}

// Adapter lưu tại bộ nhớ, minh họa — không thread-safe.
final class InMemoryOrderRepository implements OrderRepository {
    private final Map<String, OrderReceipt> storage = new HashMap<>();

    @Override
    public void save(OrderReceipt receipt) {
        Objects.requireNonNull(receipt, "receipt");

        if (storage.putIfAbsent(receipt.orderId(), receipt) != null) {
            throw new IllegalStateException("Duplicate order ID");
        }
    }

    OrderReceipt findRequired(String id) {
        OrderReceipt found = storage.get(id);
        if (found == null) {
            throw new IllegalArgumentException("Order not found");
        }
        return found;
    }
}

// Adapter mô phỏng gửi thông báo, không in email của khách hàng.
final class ConsoleOrderNotifier implements OrderNotifier {
    @Override
    public void orderPlaced(
            String customerEmail, OrderReceipt receipt) {
        Objects.requireNonNull(customerEmail, "customerEmail");
        System.out.printf(
                "[DEMO] Created %s, total=%s%n",
                receipt.orderId(),
                receipt.total().toPlainString());
    }
}

public class ResponsibilityDemo {
    public static void main(String[] args) {
        var repository = new InMemoryOrderRepository();
        var notifier = new ConsoleOrderNotifier();

        var useCase = new PlaceOrderUseCase(
                new PriceCalculator(),
                repository,
                notifier);

        var request = new PlaceOrderRequest(
                "ORD-42",
                "customer@example.com",
                List.of(
                        new OrderItem(
                                "SKU-1", 2, new BigDecimal("50.00")),
                        new OrderItem(
                                "SKU-2", 1, new BigDecimal("25.50"))
                ));

        OrderReceipt receipt = useCase.execute(request);

        System.out.println("Receipt: " + receipt);
        System.out.println("Saved: "
                + repository.findRequired("ORD-42").total());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac ResponsibilityDemo.java
java ResponsibilityDemo
~~~

Kết quả dự kiến:

~~~text
[DEMO] Created ORD-42, total=125.50
Receipt: OrderReceipt[orderId=ORD-42, total=125.50]
Saved: 125.50
~~~

Ví dụ dùng `record` của Java 17 để thể hiện dữ liệu có giá trị và ranh giới đơn giản; **record không tự bảo đảm mọi bất biến**, vì thế constructor kiểm tra điều kiện cần thiết. `List.copyOf` tạo một snapshot cấu trúc danh sách và từ chối phần tử null; `OrderItem` là record với các component bất biến, do đó dữ liệu ví dụ không có phần tử có thể thay đổi trạng thái.

Một số quyết định của bản demo được cố ý giới hạn:

- `customerEmail` chỉ kiểm tra không rỗng, **chưa phải validation email hoàn chỉnh**. Trong thực tế cần chính sách kiểm tra và xác minh riêng.
- `InMemoryOrderRepository` không lưu xuống đĩa, không thread-safe và chưa có transaction.
- `ConsoleOrderNotifier` **không gửi email**. Nó chỉ mô phỏng side effect để chứng minh ranh giới.
- `OrderReceipt` là kết quả use case đơn giản; với ứng dụng có trạng thái đơn hàng, thanh toán, vận chuyển, cần domain model phù hợp.
- Đặt tên class và module sao cho sự phụ thuộc hướng tới những hợp đồng ổn định. Không nhất thiết mỗi triển khai đều phải có một interface nếu không có nhu cầu thay thế.

### Trước và sau refactor: điều gì thực sự thay đổi?

| Thay đổi của hệ thống | Khi dồn vào `AllInOneOrderService` | Sau refactor |
|---|---|---|
| Đổi công thức giá | Sửa trong cùng lớp chứa DB/email | Sửa `PriceCalculator` và test giá |
| Đổi nơi lưu dữ liệu | Sửa logic truy cập DB trong lớp nghiệp vụ | Thay adapter của `OrderRepository` |
| Chuyển từ email sang SMS | Sửa logic thông báo ở cùng lớp nghiệp vụ | Thay adapter của `OrderNotifier` |
| Kiểm tra mặt hàng không hợp lệ | Nằm lẫn trong một hàm lớn | Thể hiện invariant ở `OrderItem` |
| Thay thứ tự nghiệp vụ: lưu trước thông báo | Dễ nằm lẫn side effect | Xem rõ trong `PlaceOrderUseCase.execute` |
| Unit test riêng công thức giá | Có thể vướng khởi tạo DB/mail | Tạo trực tiếp `new PriceCalculator()` |

**Điểm cần nhớ:** Refactor **không chỉ là chia file**. Ta phải tạo ra các ranh giới mà tại đó *mỗi phần sở hữu một quyết định*, và các phần còn lại sử dụng nó qua hợp đồng rõ ràng.

## 7. Trách nhiệm của lớp khác trách nhiệm của use case

Đến đây có thể xuất hiện một câu hỏi: “`PlaceOrderUseCase` gọi ba dependency, vậy nó có quá nhiều trách nhiệm không?”

**Chưa chắc.** Đặt một đơn hàng **bản thân nó là một quy trình** bao gồm tính tiền, lưu và thông báo. Use case có thể chịu trách nhiệm thực thi **một kịch bản nghiệp vụ có trình tự**, còn từng cộng tác viên chịu trách nhiệm cho chi tiết chuyên biệt.

Nhưng nếu cùng `PlaceOrderUseCase` bắt đầu có `cancelOrder`, `refund`, `generateMonthlyReport`, `syncWarehouse`, `createPromoCampaign` và hàng chục field trạng thái khác nhau, nó có thể đang thành **God Service**. Cần xem các yêu cầu có cùng lý do thay đổi hay thuộc nhiều luồng khác nhau.

Không nên hiểu SRP như một quy tắc máy móc “mỗi class chỉ có một method”, “mỗi class tối đa 100 dòng”, hay “mỗi method tối đa ba dependency”. Đó là các chỉ dấu tham khảo, không phải định nghĩa trách nhiệm.

### Domain object nên giữ hành vi nào?

Tách hết mọi hành vi khỏi entity có thể làm xuất hiện mô hình thiếu hành vi (*anemic domain model*), nơi mọi ràng buộc và thay đổi trạng thái bị dồn vào service khác. Ví dụ, một `BankAccount` có thể tự bảo vệ quy tắc rút tiền hợp lệ vì đó là **trách nhiệm liên kết chặt với trạng thái của tài khoản**:

~~~java
import java.math.BigDecimal;
import java.util.Objects;

final class BankAccount {
    private BigDecimal balance;

    BankAccount(BigDecimal initial) {
        Objects.requireNonNull(initial);
        if (initial.signum() < 0) {
            throw new IllegalArgumentException("Negative initial balance");
        }
        this.balance = initial;
    }

    void withdraw(BigDecimal amount) {
        Objects.requireNonNull(amount);
        if (amount.signum() <= 0 || amount.compareTo(balance) > 0) {
            throw new IllegalArgumentException("Invalid withdrawal");
        }
        balance = balance.subtract(amount);
    }

    BigDecimal balance() {
        return balance;
    }
}
~~~

Đây là **hành vi hợp lý bên trong domain object**, không phải dấu hiệu lớp ôm quá nhiều việc. `BankAccount` sẽ bắt đầu đáng ngờ nếu tự gọi SMTP, xây báo cáo CSV hoặc tự biết mật khẩu kết nối database.

## 8. Những lỗi khi refactor God Class

### 8.1. Chia lớp nhưng chỉ chuyển lời gọi qua lại

Ví dụ không giải quyết vấn đề:

~~~java
class OrderFacade {
    private final LegacyOrderManager manager = new LegacyOrderManager();

    void saveOrder() {
        manager.doEverything();
    }
}
~~~

Một wrapper đẹp tên không tách policy và side effect nếu `LegacyOrderManager` vẫn làm tất cả. Hãy xác định **logic nào thật sự được chuyển giao quyền sở hữu** và kiểm tra dependency sau thay đổi.

### 8.2. Tách nhỏ đến mức mất khả năng đọc luồng nghiệp vụ

Nếu mỗi dòng tính giá tạo thành một class (`AddItemService`, `MultiplyQuantityService`, `RoundTotalService`...) mà không có lý do thay đổi riêng, số lượng abstraction có thể làm việc đọc code chậm hơn. Hãy gom các bước có cùng mục đích vào một đối tượng gắn kết.

### 8.3. Dời tất cả sang một “Utils” tĩnh

~~~java
OrderUtils.validate(...);
OrderUtils.calculate(...);
OrderUtils.save(...);
OrderUtils.sendMail(...);
~~~

Đổi `OrderManager` thành `OrderUtils` vẫn tập trung trách nhiệm, thậm chí khó inject dependency hoặc kiểm thử side effect. Method `static` hợp lý cho hàm thuần nhỏ, nhưng “utils” không nên là nơi chứa mọi chính sách và adapter.

### 8.4. Tạo interface cho mọi class

Một interface chỉ có đúng một implementation không tự tạo giá trị nếu nó không phân tách ranh giới ổn định/biến động hoặc giúp kiểm thử. `PriceCalculator` trong ví dụ là class thường vì tính giá là phần cần kiểm thử trực tiếp, chưa cần nhiều thuật toán. `OrderRepository` và `OrderNotifier` là abstraction có ý nghĩa do ngăn use case phụ thuộc vào cơ chế lưu/gửi cụ thể.

### 8.5. Bỏ sót ranh giới giao dịch khi di chuyển code

Ví dụ chạy lần lượt:

~~~java
repository.save(receipt);
notifier.orderPlaced(email, receipt);
~~~

Nếu `save` thành công rồi `orderPlaced` ném exception, **đơn đã được lưu nhưng thông báo chưa được gửi**. Việc chia class không tự giải quyết atomicity, retry hay idempotency.

Trong hệ thống thực, có thể dùng **transactional outbox**: lưu đơn hàng và sự kiện cần phát trong cùng một giao dịch database, rồi một worker gửi sự kiện có khả năng retry và xử lý trùng. Thiết kế chi tiết tùy yêu cầu nhất quán; không nên giả định transaction DB có thể bao trùm email hoặc mọi HTTP side effect.

Tương tự, nếu giá đang được tính từ dữ liệu có thể thay đổi, phải xác định phiên bản bảng giá/tỷ lệ thuế tại thời điểm tạo đơn, tránh làm lệch kết quả sau refactor.

## 9. Kiểm thử để refactor an toàn

Trước khi sửa lớp lớn, cần biết **hành vi nào phải được bảo toàn**. Với code legacy chưa có test, có thể dùng *characterization tests* (kiểm thử ghi nhận hành vi hiện hữu) để khóa các quy tắc cần giữ, sau đó viết test cô lập cho phần được tách ra.

Ví dụ sau dùng JUnit Jupiter 5 và các class từ `ResponsibilityDemo.java`. Đặt trong `ResponsibilityDemoTest.java` cùng package, thêm dependency `org.junit.jupiter:junit-jupiter` và test runner phù hợp:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class ResponsibilityDemoTest {
    @Test
    void priceIsIndependentOfDatabaseAndNotification() {
        var calculator = new PriceCalculator();

        BigDecimal total = calculator.calculate(List.of(
                new OrderItem("SKU-1", 2, new BigDecimal("50.00")),
                new OrderItem("SKU-2", 1, new BigDecimal("25.50"))
        ));

        assertEquals(new BigDecimal("125.50"), total);
    }

    @Test
    void useCasePersistsBeforeNotifying() {
        var events = new ArrayList<String>();

        OrderRepository repository = receipt ->
                events.add("saved:" + receipt.orderId());

        OrderNotifier notifier = (email, receipt) ->
                events.add("notified:" + receipt.orderId());

        var useCase = new PlaceOrderUseCase(
                new PriceCalculator(), repository, notifier);

        var request = new PlaceOrderRequest(
                "ORD-42",
                "customer@example.com",
                List.of(new OrderItem(
                        "SKU-1", 1, new BigDecimal("10.00"))));

        var receipt = useCase.execute(request);

        assertEquals(new BigDecimal("10.00"), receipt.total());
        assertEquals(List.of(
                "saved:ORD-42",
                "notified:ORD-42"
        ), events);
    }

    @Test
    void notificationDoesNotRunWhenPersistenceFails() {
        AtomicInteger notifications = new AtomicInteger();

        OrderRepository brokenRepository = receipt -> {
            throw new IllegalStateException("Storage failure");
        };
        OrderNotifier notifier = (email, receipt) ->
                notifications.incrementAndGet();

        var useCase = new PlaceOrderUseCase(
                new PriceCalculator(), brokenRepository, notifier);

        var request = new PlaceOrderRequest(
                "ORD-99",
                "customer@example.com",
                List.of(new OrderItem(
                        "SKU-1", 1, new BigDecimal("10.00"))));

        assertThrows(IllegalStateException.class,
                () -> useCase.execute(request));
        assertEquals(0, notifications.get());
    }

    @Test
    void invalidQuantityIsRejectedBeforeUseCase() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderItem(
                        "SKU-1", 0, new BigDecimal("10.00")));
    }
}
~~~

**Giá trị của các test:**

- `PriceCalculator` được test **không cần** giả lập DB hay email.
- Test orchestration xác nhận **thứ tự** yêu cầu lưu rồi mới thông báo.
- Nếu repository thất bại, notifier chưa được gọi, nên lỗi luồng dễ nhận thấy.
- Bất biến của `OrderItem` được kiểm tra ở đúng nơi tạo value object.

Những test này không chứng minh lưu trữ thật hay gửi email thật đã hoạt động. Adapter dùng JDBC/JPA/HTTP/SMTP cần integration test ở ranh giới tương ứng. Với thay đổi giao dịch, cần thêm test cho retry, race condition, thông báo trùng và yêu cầu idempotency.

## 10. Cách refactor từng bước, giảm nguy cơ thay đổi hành vi

Một quy trình thực tế khi gặp lớp lớn đang chạy production:

1. **Xác định các chức năng và client:** Ai gọi method nào? Dữ liệu/side effect đi đâu? Đánh dấu các quy tắc có rủi ro cao (tiền, trạng thái, phân quyền, transaction).
2. **Ghi nhận hành vi hiện tại:** Characterization tests hoặc test tích hợp cho các luồng quan trọng; phân biệt bug cần sửa riêng với hành vi đang được phụ thuộc.
3. **Phân nhóm lý do thay đổi:** Pricing, persistence, notification, validation, presentation...; dùng dependency và field usage để xác nhận thay vì dựa vào tên class.
4. **Trích xuất logic thuần trước:** Chuyển phép tính xác định (pure logic) thành class/phương thức có test độc lập. Ít rủi ro hơn dịch chuyển transaction hoặc network call.
5. **Tách cổng giao tiếp ra khỏi use case:** Mô tả `OrderRepository`, `OrderNotifier` đúng theo nhu cầu của caller; tạo adapter cho code cũ khi cần.
6. **Di chuyển side effect có kiểm soát:** Giữ thứ tự tác vụ, điều kiện lỗi và chính sách retry như hợp đồng, tránh phát thông báo hai lần.
7. **Thu gọn lớp cũ:** Cho nó chỉ còn trách nhiệm thực sự của use case hoặc chuyển caller sang API mới; xóa luồng cũ khi không còn ai dùng.
8. **Kiểm tra thay đổi:** Chạy test module/unit/integration phù hợp, so sánh kết quả nghiệp vụ, đo log và truy vấn. Chỉ tối ưu hiệu năng khi có bằng chứng.

Refactor an toàn thường gồm **nhiều thay đổi nhỏ có thể review**, thay vì viết lại toàn bộ lớp hàng nghìn dòng một lần. Nếu có ràng buộc tương thích API, có thể giữ một adapter chuyển tiếp tạm thời và lên kế hoạch loại bỏ nó sau khi caller đã chuyển.

### Sơ đồ luồng sau khi tách

~~~mermaid
sequenceDiagram
    actor Client
    participant U as PlaceOrderUseCase
    participant P as PriceCalculator
    participant R as OrderRepository
    participant N as OrderNotifier
    Client->>U: execute(request)
    U->>P: calculate(items)
    P-->>U: total
    U->>R: save(receipt)
    R-->>U: hoàn tất
    U->>N: orderPlaced(email, receipt)
    N-->>U: hoàn tất
    U-->>Client: receipt
    Note over U,N: Nếu notify lỗi sau save, cần chính sách nhất quán/retry riêng
~~~

## 11. Khi nào KHÔNG cần chia lớp?

Các dấu hiệu gợi ý **nên giữ lại** một lớp:

- Mọi method thực sự phục vụ một invariant/thuật toán gắn kết, thay đổi theo cùng chính sách.
- Việc chia thêm lớp chỉ tạo nhiều đối tượng chuyển lời gọi qua lại mà không giảm coupling hay làm test dễ hơn.
- Thành phần là một value object hoặc aggregate có quy tắc nghiệp vụ bao quanh cùng một trạng thái.
- Bài toán rất nhỏ, thuật toán rõ ràng và chưa có trục biến thiên thực tế; refactor chưa đem lại lợi ích tương xứng.
- Một class có nhiều method vì triển khai giao thức đầy đủ, nhưng vẫn có ranh giới trách nhiệm rõ.

Đừng ra quyết định chỉ bằng **LOC (lines of code), số method, cyclomatic complexity hoặc tên `Manager`**. Chúng giúp tìm nơi cần xem xét; quyết định thiết kế phải dựa trên cohesion, coupling, nguyên nhân thay đổi, khả năng kiểm thử và ảnh hưởng tới nghiệp vụ.

## 12. Bài tập thực hành: tách lớp UserManager

Cho một lớp giả định:

~~~java
class UserManager {
    void register(String email, String password) { /* ... */ }
    boolean authenticate(String email, String password) { /* ... */ }
    void sendWelcomeEmail(String email) { /* ... */ }
    String exportUserCsv() { /* ... */ }
    void cleanupInactiveUsers() { /* ... */ }
}
~~~

Đừng lập tức biến năm method thành năm class. Hãy phân tích:

- Quy tắc đăng ký và xác thực thuộc cùng chính sách nào, có trường hợp cần tách không?
- Password hashing, mật khẩu và session/token cần ranh giới bảo mật nào?
- Email và CSV là trách nhiệm nghiệp vụ hay adapter của hệ thống?
- Xóa user không hoạt động có phải batch job riêng với transaction/audit yêu cầu khác?
- Những actor/nhóm yêu cầu nào khiến `UserManager` phải thay đổi?

**Yêu cầu:** Vẽ sơ đồ quan hệ sau khi tách, tạo interface chỉ tại ranh giới cần thay thế, đặt tên use case phù hợp, và viết ít nhất ba bài test: dữ liệu đăng ký sai, thành công lưu user, email thất bại sau lưu. Xác định rõ chính sách nghiệp vụ cho trường hợp email thất bại (đăng ký có được coi là thành công không? có retry/outbox không?).

### Câu hỏi tự kiểm tra

1. Vì sao “class nhiều dòng” chỉ là dấu hiệu, chưa phải bằng chứng God Class?
2. Nếu đổi SQL và công thức khuyến mãi đều sửa `OrderManager`, điều đó nói gì về lý do thay đổi?
3. Chia một method lớn thành 10 private methods có tự bảo đảm SRP không?
4. Lớp `PlaceOrderUseCase` gọi ba dependency có nhất thiết là God Class không? Vì sao?
5. Vì sao không nên tách cả phép kiểm tra số dư và rút tiền ra khỏi `BankAccount` nếu invariant thuộc chính account?
6. Interface và DI giúp gì khi chuyển database/mail adapter? Chúng có tự giải quyết transaction không?
7. Vì sao `repository.save` thành công nhưng `notifier.orderPlaced` thất bại cần một chính sách riêng?
8. Khi nào nên dừng refactor để tránh sinh hàng chục lớp chuyển tiếp không mang trách nhiệm thật?

**Kết luận:** Lớp ôm quá nhiều trách nhiệm làm các quyết định độc lập dính chặt vào nhau, khiến sửa một nơi gây ảnh hưởng nhiều nơi. Refactor tốt là **tìm các ranh giới thay đổi thực sự**, đặt logic và side effect đúng nơi, giữ use case điều phối gắn kết, đồng thời dùng kiểm thử và hợp đồng nghiệp vụ để bảo toàn kết quả. **Số class không phải chỉ số chất lượng**; khả năng hiểu, sửa và kiểm chứng hành vi mới là điều quan trọng.