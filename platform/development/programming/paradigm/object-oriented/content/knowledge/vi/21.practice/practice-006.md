# Bài tập nhận diện lỗi thiết kế trong Java OOP

## 1. Mục tiêu bài thực hành

Một chương trình có thể **biên dịch được, cho ra kết quả đúng với một vài đầu vào**, nhưng thiết kế vẫn khiến nó khó mở rộng, khó kiểm thử và dễ phát sinh lỗi khi yêu cầu thay đổi. Ngược lại, không phải đoạn mã dài hay có nhiều câu lệnh điều kiện đều là thiết kế kém.

Trong bài này, bạn sẽ đóng vai người review code: đọc một đoạn Java, xác định dấu hiệu bất ổn, giải thích hậu quả, phân loại mức độ ảnh hưởng, đề xuất chỉnh sửa phù hợp và viết kiểm thử để bảo vệ hành vi.

Kết quả cần đạt:

- Phân biệt **lỗi hành vi (bug)**, **mùi mã (code smell)**, **vi phạm hợp đồng** và **lựa chọn thiết kế có thể chấp nhận được**.
- Nhận diện những vấn đề OOP thường gặp: dữ liệu bị lộ, trách nhiệm quá nhiều, phụ thuộc trực tiếp implementation, lớp kế thừa sai quan hệ, mã trùng lặp, điều kiện phân nhánh theo loại đối tượng, trạng thái toàn cục và những phép toán tiền không an toàn.
- Đưa ra bằng chứng cụ thể từ mã thay vì chỉ gắn nhãn “vi phạm SOLID”.
- Tái cấu trúc một ví dụ thành các đối tượng có trách nhiệm rõ ràng.
- Viết JUnit test chứng minh logic nghiệp vụ còn đúng sau refactor.

**Nguyên tắc chấm bài:** Đừng dừng ở câu “đoạn này vi phạm SRP”. Hãy nêu **dòng nào**, **điều gì có thể sai**, **thay đổi nào sẽ làm mã dễ hỏng**, **cách cải thiện** và **test nào xác minh điều đó**.

## 2. Quy trình nhận diện lỗi thiết kế

Khi xem một class, hãy hỏi lần lượt:

1. **Nó có trách nhiệm gì?** Có bao nhiêu lý do độc lập khiến nó phải thay đổi?
2. **Ai sở hữu trạng thái?** Có ai bên ngoài được sửa dữ liệu mà bỏ qua bất biến không?
3. **Nó phụ thuộc vào gì?** Interface hay implementation cụ thể? Tự tạo HTTP client, repository, đồng hồ, file?
4. **Quy tắc nằm ở đâu?** Đối tượng tự xử lý dữ liệu mình sở hữu, hay lớp khác lấy nhiều getter rồi tính thay?
5. **Đa hình có được sử dụng đúng không?** Có chuỗi if/instanceof phân biệt loại đối tượng để tự quyết định hành vi?
6. **Có sự phụ thuộc ẩn không?** Static mutable state, singleton toàn cục, thứ tự gọi phương thức, thời gian hệ thống?
7. **Đâu là hành vi thực sự sai?** Tràn số, trạng thái không nhất quán, thiếu validation, lỗi trong nhánh thất bại?
8. **Cách sửa có xứng đáng với độ phức tạp mới không?** Một lớp đơn giản không cần bốn interface chỉ để làm phép cộng.

### Phân biệt mức độ

| Nhận định | Có nghĩa là gì? | Ví dụ |
| --- | --- | --- |
| Bug đã xác định | Một trường hợp cụ thể tạo kết quả sai hợp đồng | Số tiền kiểu long tràn số thành giá trị âm |
| Rủi ro thiết kế | Chưa chắc gây bug hôm nay nhưng thay đổi rất khó | Lớp nghiệp vụ tự new một adapter HTTP |
| Code smell | Dấu hiệu cần điều tra, chưa phải kết luận tuyệt đối | Phương thức dài, nhiều switch, nhiều tham số |
| Trade-off có chủ ý | Quyết định đơn giản với phạm vi và giới hạn rõ | Dùng một lớp nhỏ thay vì tạo hierarchy không cần thiết |

Không có quy tắc “cứ hơn 20 dòng là sai” hoặc “cứ thấy if là phải thay bằng đa hình”. Phải dựa trên trách nhiệm, nhu cầu thay đổi và bằng chứng.

## 3. Bài tập 1 — Đọc mã và tìm vấn đề

Giả sử ứng dụng bán hàng có đoạn Java sau. Đây là **mã cố ý có vấn đề để phân tích**; chưa có đủ validation và cơ chế an toàn tài chính.

~~~java
import java.util.List;

interface Gateway {
    boolean charge(String orderId, long amountVnd);
}

final class ConsoleGateway implements Gateway {
    @Override
    public boolean charge(String orderId, long amountVnd) {
        System.out.println("Charge " + orderId + ": " + amountVnd);
        return true;
    }
}

final class CheckoutManager {
    // Tất cả đối tượng CheckoutManager cùng dùng chung biến này.
    static long totalPaidVnd = 0;

    boolean checkout(
            String orderId,
            List<long[]> items,
            boolean vip) {

        long amount = 0;

        for (long[] item : items) {
            // item[0] = đơn giá; item[1] = số lượng
            amount += item[0] * item[1];
        }

        if (vip) {
            amount = amount - amount / 10;
        }

        if (amount <= 0) {
            return false;
        }

        Gateway gateway = new ConsoleGateway();
        boolean accepted = gateway.charge(orderId, amount);

        if (accepted) {
            totalPaidVnd += amount;
        }
        return accepted;
    }
}
~~~

### Yêu cầu tự làm trước khi xem lời giải

Ghi ít nhất sáu nhận xét theo mẫu:

| Vị trí | Dấu hiệu quan sát được | Hậu quả hoặc tình huống hỏng | Đề xuất | Test chứng minh |
| --- | --- | --- | --- | --- |
| Ví dụ: new ConsoleGateway() | Phụ thuộc trực tiếp implementation | Unit test luôn gọi adapter demo; khó mô phỏng bị từ chối | Inject Gateway qua constructor | Fake Gateway trả false; xác minh không ghi nhận thanh toán |

Bạn cần trả lời:

- Thông tin “đơn giá” và “số lượng” có đủ rõ ràng trong List<long[]> không? Điều gì xảy ra nếu phần tử chỉ có một số?
- Phép nhân/cộng có kiểm tra tràn long không?
- Nếu khách có hai đơn hàng khác nhau, phương thức có thể tái sử dụng quy tắc tính giá dễ dàng không?
- Phần nào là **nghiệp vụ của đơn hàng**, phần nào là **điều phối thanh toán**, phần nào là **ghi nhận doanh số**?
- Nếu hệ thống thêm một cổng thanh toán mới, có cần sửa CheckoutManager không?
- Nếu hai test chạy song song, totalPaidVnd có là dữ liệu đáng tin cậy không?
- Chương trình xử lý thế nào với items = null, phần tử null, số lượng âm, mã đơn trống?
- Có nhất thiết phải thay mọi đoạn mã bằng design pattern không?

### Gợi ý đáp án có giải thích

| Vấn đề | Bản chất | Vì sao đáng quan tâm | Hướng sửa |
| --- | --- | --- | --- |
| List<long[]> và các chỉ số 0, 1 | Primitive Obsession / dữ liệu khó hiểu | Dễ đảo đơn giá–số lượng, thiếu bất biến của dòng hàng | Tạo OrderLine với tên trường và validation |
| amount được tính trong CheckoutManager | Trách nhiệm lẫn lộn, có dấu hiệu Feature Envy | Dịch vụ thanh toán phải biết cách tính giá | Đưa phép tính dòng hàng vào OrderLine, tổng vào Order |
| amount += item[0] * item[1] | **Bug tiềm ẩn có thể tái hiện** khi overflow | long trong Java mặc định tràn mà không báo lỗi | Math.multiplyExact và Math.addExact |
| new ConsoleGateway() | Coupling với implementation | Test không thể điều khiển kết quả cổng thanh toán | Constructor injection với Gateway |
| static long totalPaidVnd | Shared mutable state | Các instance và test ảnh hưởng nhau; cập nhật không đồng bộ | Tách repository/ledger có vòng đời và cơ chế nhất quán rõ |
| Không kiểm tra đầu vào | Thiếu bảo vệ bất biến | Có thể NPE, ArrayIndexOutOfBoundsException hoặc giá trị sai | Constructor/value object validate |
| Một phương thức vừa định giá, gọi cổng, thống kê | Nhiều lý do thay đổi (SRP) | Đổi chính sách giá cũng phải sửa luồng thanh toán | Tách Order, CheckoutService và SalesLedger |
| Trả false cho amount <= 0 | Hợp đồng chưa rõ | Dữ liệu sai bị trộn với trường hợp thanh toán bị từ chối | Phân biệt validation exception và từ chối của gateway |

Vấn đề về overflow có thể minh họa độc lập:

~~~java
long wrong = Long.MAX_VALUE + 1;
System.out.println(wrong); // -9223372036854775808

Math.addExact(Long.MAX_VALUE, 1); // ArithmeticException
~~~

Lưu ý: **Không phải mọi mùi mã tự động là bug.** Ví dụ static có thể phù hợp với hằng số bất biến. Rủi ro ở đây là **static mutable** dùng để lưu trạng thái giao dịch. Cũng không nên khẳng định mọi class đặt tên Manager đều kém; phải xét nội dung.

## 4. Bài tập 2 — Refactor theo trách nhiệm OOP

Đề xuất tách thành ba phần:

- **OrderLine / Order:** sở hữu dữ liệu và quy tắc tính tiền.
- **PaymentGateway:** hợp đồng gửi yêu cầu thanh toán; có thể thay implementation khi kiểm thử.
- **SalesLedger:** hợp đồng ghi nhận kết quả thanh toán đã được chấp nhận.
- **CheckoutService:** điều phối, không tự duyệt đơn để tính tiền hoặc sở hữu tổng doanh số toàn cục.

~~~mermaid
classDiagram
    class OrderLine {
      +String sku
      +long unitPriceVnd
      +int quantity
      +subtotalVnd() long
    }
    class Order {
      -String orderId
      -List~OrderLine~ lines
      -boolean vip
      +payableVnd() long
      +id() String
    }
    class PaymentGateway {
      <<interface>>
      +charge(orderId, amountVnd) boolean
    }
    class SalesLedger {
      <<interface>>
      +recordPaid(orderId, amountVnd) void
    }
    class CheckoutService {
      -PaymentGateway gateway
      -SalesLedger ledger
      +checkout(order) boolean
    }
    Order "1" *-- "1..*" OrderLine
    CheckoutService --> Order
    CheckoutService --> PaymentGateway
    CheckoutService --> SalesLedger
~~~

Quy tắc ví dụ:
- Đơn có ít nhất một dòng hàng; đơn giá và số lượng phải dương; mã đơn và mã sản phẩm không trống.
- Tổng tiền bằng tổng của đơn giá × số lượng.
- Khách VIP giảm 10% trên tổng tiền; số tiền giảm được làm tròn xuống VND bằng chia số nguyên.
- Cổng thanh toán trả true thì ghi nhận thanh toán; trả false thì không ghi.
- Khi tính toán bị overflow phải dừng trước khi gửi yêu cầu thanh toán.

### 4.1. Dự án chạy được với Java 17 + Maven + JUnit 5

~~~text
design-review-lab/
├── pom.xml
└── src/
    ├── main/java/example/
    │   ├── OrderLine.java
    │   ├── Order.java
    │   ├── PaymentGateway.java
    │   ├── SalesLedger.java
    │   ├── CheckoutService.java
    │   └── Demo.java
    └── test/java/example/
        └── DesignReviewTest.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>design-review-lab</artifactId>
    <version>1.0-SNAPSHOT</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.junit.jupiter</groupId>
            <artifactId>junit-jupiter</artifactId>
            <version>5.11.4</version>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.5.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**src/main/java/example/OrderLine.java**

~~~java
package example;

public record OrderLine(String sku, long unitPriceVnd, int quantity) {
    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (unitPriceVnd <= 0 || quantity <= 0) {
            throw new IllegalArgumentException(
                    "Price and quantity must be positive");
        }
    }

    public long subtotalVnd() {
        return Math.multiplyExact(unitPriceVnd, (long) quantity);
    }
}
~~~

**src/main/java/example/Order.java**

~~~java
package example;

import java.util.List;
import java.util.Objects;

public final class Order {
    private final String id;
    private final List<OrderLine> lines;
    private final boolean vip;

    public Order(String id, List<OrderLine> lines, boolean vip) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Order must have lines");
        }
        this.id = id;
        this.lines = List.copyOf(lines);
        this.vip = vip;
    }

    public String id() {
        return id;
    }

    public long payableVnd() {
        long subtotal = 0;
        for (OrderLine line : lines) {
            subtotal = Math.addExact(subtotal, line.subtotalVnd());
        }
        long discount = vip ? subtotal / 10 : 0;
        return subtotal - discount;
    }
}
~~~

**src/main/java/example/PaymentGateway.java**

~~~java
package example;

@FunctionalInterface
public interface PaymentGateway {
    boolean charge(String orderId, long amountVnd);
}
~~~

**src/main/java/example/SalesLedger.java**

~~~java
package example;

@FunctionalInterface
public interface SalesLedger {
    void recordPaid(String orderId, long amountVnd);
}
~~~

**src/main/java/example/CheckoutService.java**

~~~java
package example;

import java.util.Objects;

public final class CheckoutService {
    private final PaymentGateway gateway;
    private final SalesLedger ledger;

    public CheckoutService(PaymentGateway gateway, SalesLedger ledger) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
        this.ledger = Objects.requireNonNull(ledger, "ledger");
    }

    public boolean checkout(Order order) {
        Objects.requireNonNull(order, "order");

        // Tính trước khi gọi phụ thuộc có tác dụng phụ.
        long amount = order.payableVnd();

        boolean approved = gateway.charge(order.id(), amount);
        if (approved) {
            ledger.recordPaid(order.id(), amount);
        }
        return approved;
    }
}
~~~

**src/main/java/example/Demo.java**

~~~java
package example;

import java.util.List;

public final class Demo {
    public static void main(String[] args) {
        Order order = new Order("DH-101", List.of(
                new OrderLine("BOOK", 100_000, 2),
                new OrderLine("PEN", 30_000, 1)), true);

        PaymentGateway gateway = (id, amount) -> {
            System.out.println("Charge " + id + ": " + amount);
            return true; // Adapter minh họa, không thu tiền thật.
        };

        SalesLedger ledger = (id, amount) ->
                System.out.println("Recorded " + id + ": " + amount);

        CheckoutService checkout = new CheckoutService(gateway, ledger);

        System.out.println("Payable: " + order.payableVnd());
        System.out.println("Accepted: " + checkout.checkout(order));
    }
}
~~~

Tại thư mục có pom.xml, chạy:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes example.Demo
~~~

Đầu ra dự kiến:

~~~text
Payable: 207000
Charge DH-101: 207000
Recorded DH-101: 207000
Accepted: true
~~~

Các interface ở đây giúp tách việc **định giá**, **gọi cổng thanh toán** và **ghi nhận**. Trong sản phẩm thật, sự cố xảy ra sau khi thu tiền nhưng trước khi ghi vào ledger đòi hỏi cơ chế giao dịch bền vững, đối soát/idempotency hoặc transactional outbox; chỉ tách lớp không thể tự đảm bảo tính nhất quán phân tán.

## 5. Bài tập 3 — Viết test chứng minh cải thiện

Sau refactor, test nên xác minh **hành vi nhìn được từ phía caller** và **các tương tác có tác dụng phụ**. Không cần mock chính CheckoutService.

**src/test/java/example/DesignReviewTest.java**

~~~java
package example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

class DesignReviewTest {
    private Order regularOrder() {
        return new Order("DH-1", List.of(
                new OrderLine("BOOK", 100_000, 2),
                new OrderLine("PEN", 30_000, 1)), false);
    }

    @Test
    void lineOwnsItsSubtotal() {
        OrderLine line = new OrderLine("BOOK", 100_000, 2);
        assertEquals(200_000L, line.subtotalVnd());
    }

    @Test
    void orderOwnsPriceAndVipRule() {
        Order regular = regularOrder();
        Order vip = new Order("DH-2", List.of(
                new OrderLine("BOOK", 100_000, 2),
                new OrderLine("PEN", 30_000, 1)), true);

        assertEquals(230_000L, regular.payableVnd());
        assertEquals(207_000L, vip.payableVnd());
    }

    @Test
    void approvedPaymentIsRecordedExactlyOnce() {
        List<String> charges = new ArrayList<>();
        List<String> records = new ArrayList<>();

        PaymentGateway gateway = (id, amount) -> {
            charges.add(id + ":" + amount);
            return true;
        };
        SalesLedger ledger = (id, amount) ->
                records.add(id + ":" + amount);

        CheckoutService service = new CheckoutService(gateway, ledger);

        assertTrue(service.checkout(regularOrder()));
        assertEquals(List.of("DH-1:230000"), charges);
        assertEquals(List.of("DH-1:230000"), records);
    }

    @Test
    void rejectedPaymentMustNotBeRecorded() {
        AtomicInteger gatewayCalls = new AtomicInteger();
        AtomicInteger ledgerCalls = new AtomicInteger();

        PaymentGateway gateway = (id, amount) -> {
            gatewayCalls.incrementAndGet();
            return false;
        };
        SalesLedger ledger = (id, amount) ->
                ledgerCalls.incrementAndGet();

        CheckoutService service = new CheckoutService(gateway, ledger);

        assertFalse(service.checkout(regularOrder()));
        assertEquals(1, gatewayCalls.get());
        assertEquals(0, ledgerCalls.get());
    }

    @Test
    void invalidDataIsRejectedAtConstruction() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("X", -1, 2));
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("X", 100, 0));
        assertThrows(IllegalArgumentException.class,
                () -> new Order(" ", List.of(
                        new OrderLine("X", 100, 1)), false));
        assertThrows(IllegalArgumentException.class,
                () -> new Order("O-1", List.of(), false));
    }

    @Test
    void overflowIsReportedBeforeCallingGateway() {
        Order huge = new Order("DH-HUGE", List.of(
                new OrderLine("X", Long.MAX_VALUE, 2)), false);

        AtomicInteger calls = new AtomicInteger();
        PaymentGateway gateway = (id, amount) -> {
            calls.incrementAndGet();
            return true;
        };
        SalesLedger ledger = (id, amount) ->
                fail("Ledger should not be called");

        CheckoutService service = new CheckoutService(gateway, ledger);

        assertThrows(ArithmeticException.class,
                () -> service.checkout(huge));
        assertEquals(0, calls.get());
    }

    @Test
    void inputListChangesCannotModifyOrder() {
        List<OrderLine> input = new ArrayList<>();
        input.add(new OrderLine("X", 100, 1));
        Order order = new Order("DH-3", input, false);

        input.add(new OrderLine("Y", 200, 1));

        assertEquals(100L, order.payableVnd());
    }
}
~~~

Bộ ví dụ có **7 phương thức @Test**. Lệnh mvn test được kỳ vọng hoàn tất không có test thất bại khi sao chép đủ các tệp đã nêu.

### Các kiểm thử phản ánh mùi mã nào?

| Test | Bằng chứng mang lại |
| --- | --- |
| lineOwnsItsSubtotal | Phép tính dòng hàng nằm tại chính đối tượng chứa dữ liệu |
| orderOwnsPriceAndVipRule | Quy tắc định giá không bị lặp trong CheckoutService |
| approvedPaymentIsRecordedExactlyOnce | Hai dependency được gọi đúng dữ liệu khi thanh toán được chấp nhận |
| rejectedPaymentMustNotBeRecorded | Có thể chủ động mô phỏng cổng thanh toán từ chối |
| invalidDataIsRejectedAtConstruction | Trạng thái sai bị chặn ở ranh giới tạo đối tượng |
| overflowIsReportedBeforeCallingGateway | Lỗi số học không tạo yêu cầu thanh toán sai |
| inputListChangesCannotModifyOrder | Đối tượng không bị thay đổi gián tiếp qua List bên ngoài |

**Đừng suy luận quá mức từ test:** Các test này kiểm tra quy tắc nghiệp vụ và tính điều phối trong bộ nhớ. Chúng chưa xác minh một adapter thanh toán HTTP hay ledger database thật, càng không đảm bảo xử lý đúng concurrent updates hoặc giao dịch phân tán.

## 6. Bài tập 4 — Chọn giải pháp cho các đoạn mã ngắn

Hãy tự ghi vấn đề, ảnh hưởng và cách sửa trước khi đọc gợi ý. Mỗi trường hợp có thể có nhiều cách hợp lý tùy yêu cầu.

### Tình huống A — Đối tượng bị sửa trạng thái tùy ý

~~~java
class Customer {
    public String email;
    public boolean active;
}

class CustomerService {
    void activate(Customer customer) {
        customer.active = true;
    }
}
~~~

**Câu hỏi:** Nếu yêu cầu kích hoạt chỉ được thực hiện khi email hợp lệ, ai phải đảm bảo bất biến? Việc để public field khiến code bên ngoài có thể bỏ qua kiểm tra như thế nào?

**Gợi ý:** Chuyển field về private, thêm constructor hoặc phương thức thiết lập email có validation, và cân nhắc customer.activate() nếu hành vi thực sự thuộc về Customer. Không bắt buộc dùng setter cho mọi field.

### Tình huống B — Dùng kế thừa chỉ để tái sử dụng mã

~~~java
class EmailSender {
    void sendEmail(String to, String message) {}
}

class OrderService extends EmailSender {
    void confirm(String address) {
        sendEmail(address, "Order confirmed");
    }
}
~~~

**Câu hỏi:** “OrderService là một loại EmailSender” có đúng không? Nếu chuyển từ email sang SMS, ai sẽ phải thay đổi?

**Gợi ý:** Dùng kết hợp qua MessageSender interface; OrderService nhận đối tượng gửi thông điệp qua constructor. Điều này không có nghĩa kế thừa luôn sai; sai ở quan hệ phân loại thiếu ý nghĩa.

### Tình huống C — Kiểu con phá hợp đồng của kiểu cha

~~~java
class Bird {
    void fly() { System.out.println("Flying"); }
}
class Penguin extends Bird {
    @Override
    void fly() {
        throw new UnsupportedOperationException();
    }
}
~~~

**Câu hỏi:** Một hàm nhận Bird và gọi fly() có thể dùng Penguin an toàn không?

**Gợi ý:** Mô hình Bird chỉ chứa những hành vi chung thực sự; tách năng lực Flyable cho các loại có thể bay. Đây là tín hiệu của vi phạm Liskov Substitution Principle; sửa mô hình hợp đồng thay vì ép Penguin bay.

### Tình huống D — Tách loại đối tượng bằng instanceof

~~~java
interface Discount {}
class VipDiscount implements Discount {}
class HolidayDiscount implements Discount {}

long discountAmount(Discount d, long subtotal) {
    if (d instanceof VipDiscount) {
        return subtotal / 10;
    }
    if (d instanceof HolidayDiscount) {
        return subtotal / 5;
    }
    return 0;
}
~~~

**Câu hỏi:** Khi thêm loại giảm giá mới, phải sửa bao nhiêu nơi chứa instanceof? Có nên cho mỗi chiến lược tự tính?

**Gợi ý:** Nếu từng loại có cùng một hành vi biến thiên, khai báo method trên interface: long discount(long subtotal), rồi triển khai tại các loại. Tuy nhiên, một switch đơn giản cho đầu vào đóng/ổn định không tự động là lỗi; đánh giá tần suất mở rộng và vị trí sở hữu quy tắc.

### Tình huống E — Phụ thuộc ngầm qua thứ tự lời gọi

~~~java
class ReportBuilder {
    private String title;

    void setTitle(String title) { this.title = title; }

    String render() {
        return title.toUpperCase();
    }
}
~~~

**Câu hỏi:** Điều gì xảy ra nếu caller gọi render() trước setTitle()? Thiết kế có đang cho phép trạng thái chưa hợp lệ không?

**Gợi ý:** Yêu cầu title trong constructor, kiểm tra trước khi khởi tạo; hoặc xác định trạng thái “chưa thiết lập” và xử lý hợp lệ. Không phải mọi builder đều sai — builder có thể hữu ích cho đối tượng nhiều trường tùy chọn, miễn build() xác nhận bất biến.

### Tình huống F — Abstraction dư thừa

~~~java
interface AdditionStrategy {
    int add(int a, int b);
}

class StandardAddition implements AdditionStrategy {
    public int add(int a, int b) {
        return a + b;
    }
}
~~~

**Câu hỏi:** Khi nào interface này có giá trị? Nếu không có nhiều chiến lược cộng hoặc ranh giới thay thế cần thiết, có đáng tạo thêm abstraction không?

**Gợi ý:** Đơn giản hóa khi interface chỉ làm người đọc phải mở nhiều file mà không cung cấp lợi ích thực. “Nhiều abstraction” cũng là một dạng chi phí bảo trì.

## 7. Bài tập 5 — Phân biệt refactor với thay đổi hành vi

Một thay đổi **refactor** thường được kỳ vọng cải thiện cấu trúc trong khi giữ nguyên hành vi quan sát được theo hợp đồng hiện hành. Không nên âm thầm đổi luật nghiệp vụ dưới nhãn refactor.

Xem ba thay đổi:

| Thay đổi | Refactor thuần túy? | Vì sao? |
| --- | --- | --- |
| Di chuyển phép tính dòng hàng sang OrderLine nhưng kết quả như cũ | Có, nếu không đổi dữ liệu, rounding và lỗi được công bố | Chỉ đổi nơi đặt trách nhiệm |
| Đổi giảm VIP từ 10% sang 15% | Không | Đổi quy tắc nghiệp vụ |
| Thay phép cộng thường bằng Math.addExact | Có thể là sửa lỗi/siết hợp đồng, không mặc nhiên giữ nguyên hành vi với overflow | Trước đây overflow trả số sai; nay ném exception |
| Đổi trường public thành private và bỏ getter | Có thể là breaking change | Caller có thể không biên dịch |
| Inject PaymentGateway qua constructor | Thường là refactor trong phạm vi nội bộ | Nhưng signature khởi tạo thay đổi; phải kiểm tra caller |
| Đổi thứ tự xử lý các bước có tác dụng phụ | Cần xét hợp đồng | Có thể phá nghiệp vụ dù kết quả cuối giống nhau |

Với ví dụ của bài, ta **vừa refactor cấu trúc vừa cải thiện validation và xử lý overflow**. Vì vậy phải mô tả rõ sự thay đổi hợp đồng: dữ liệu không hợp lệ giờ bị từ chối sớm, overflow ném lỗi. Không được tuyên bố toàn bộ hành vi trước/sau giống nhau với mọi đầu vào.

Các test quan trọng trước khi sửa có thể gồm:
- Khách thường và khách VIP với giá trị tiền hợp lệ.
- Cổng thanh toán chấp nhận hoặc từ chối.
- Số tiền ghi nhận bằng số tiền đã gửi tới cổng.
- Lỗi về dữ liệu đầu vào và số học, khi đã thống nhất kết quả mong muốn.
- Cả hai trường hợp có và không có tác dụng phụ.

## 8. Bài tập 6 — Review yêu cầu mới trước khi viết code

Người quản lý muốn thêm ba tính năng:
1. Áp dụng mã khuyến mãi theo chiến dịch.
2. Đổi cổng thanh toán theo môi trường thử nghiệm và production.
3. Ghi lịch sử thành công/thất bại của các giao dịch.

**Nhiệm vụ:** Với thiết kế trước và sau khi refactor, hãy đề xuất nơi thay đổi. Đánh dấu những lớp hiện tại có nguy cơ trở thành **God Object** nếu đưa toàn bộ tính năng vào một nơi.

Một phương án:

| Yêu cầu | Lớp hoặc thành phần phù hợp | Vì sao? |
| --- | --- | --- |
| Khuyến mãi có chính sách độc lập, nhiều biến thể | DiscountPolicy/PricingService chuyên trách | Quy tắc thay đổi khác vòng đời Order |
| Cổng thanh toán theo môi trường | Composition root và các PaymentGateway adapter | CheckoutService không chọn implementation |
| Lịch sử giao dịch | TransactionRepository/PaymentRecorder | Trách nhiệm lưu trữ và truy xuất tách khỏi tính giá |
| Kiểm tra tính hợp lệ của từng dòng hàng | OrderLine | Bất biến gắn với chính dòng hàng |
| Kiểm soát thứ tự các bước thanh toán | CheckoutService hoặc application service | Đây là trách nhiệm điều phối use case |

Nếu một chức năng cần dữ liệu từ nhiều aggregate hoặc cần gọi dịch vụ ngoài, không nên ép hết vào entity chỉ để “đúng OOP”. Vị trí đúng là nơi có trách nhiệm và ranh giới thay đổi hợp lý.

## 9. Thang đánh giá bài làm

Đánh giá chất lượng review theo năm tiêu chí, mỗi tiêu chí từ 0 đến 2 điểm:

| Tiêu chí | 0 điểm | 1 điểm | 2 điểm |
| --- | --- | --- | --- |
| Nhận diện | Chỉ bình luận chung chung | Nêu vấn đề nhưng thiếu vị trí | Chỉ đúng vùng mã và dấu hiệu cụ thể |
| Hậu quả | Không có tình huống minh họa | Nêu rủi ro mơ hồ | Nêu được input, thay đổi hoặc caller gây lỗi |
| Giải pháp | Đề xuất mẫu thiết kế tùy tiện | Đúng hướng nhưng thêm phụ thuộc không cần thiết | Giải pháp rõ trách nhiệm, cân bằng độ phức tạp |
| Kiểm thử | Không có test | Chỉ happy path | Có happy path, biên, lỗi và bất biến |
| Đánh giá thay đổi | Tuyên bố mọi thay đổi đều là refactor | Nhìn thấy vài khác biệt | Phân biệt tương thích API, bug fix và đổi nghiệp vụ |

Tổng tối đa **10 điểm**. Điểm cao không phụ thuộc vào số lượng design pattern bạn sử dụng; mã đơn giản và giải thích rõ thường tốt hơn việc thêm lớp chỉ cho “đủ SOLID”.

### Checklist trước khi kết thúc review

- [ ] Tách được lỗi có thể chứng minh khỏi mùi mã cần cân nhắc.
- [ ] Với mỗi nhận xét, chỉ ra được bằng chứng trong Java code.
- [ ] Xác định đúng chủ sở hữu dữ liệu và quy tắc nghiệp vụ.
- [ ] Không tự động dùng kế thừa hoặc interface khi không cần.
- [ ] Có test bảo vệ nhánh thành công, từ chối và lỗi/biên.
- [ ] Không che giấu thay đổi hành vi dưới tên gọi refactor.
- [ ] Có cách kiểm tra tác động tới caller và hệ thống bên ngoài.
- [ ] Đánh giá được cái giá của lớp/interface mới trước khi quyết định tách.

**Kết quả học tập:** Khi gặp một class “chạy được nhưng khó sửa”, bạn có thể biến cảm giác khó chịu thành nhận xét kỹ thuật có bằng chứng, đề xuất thay đổi với phạm vi rõ ràng và dùng kiểm thử để đánh giá kết quả — đó là kỹ năng cốt lõi của việc nhận diện lỗi thiết kế OOP.