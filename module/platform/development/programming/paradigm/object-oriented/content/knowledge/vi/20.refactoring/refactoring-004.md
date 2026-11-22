# Di chuyển hành vi về đối tượng chịu trách nhiệm trong Java OOP

## 1. Bài toán: dữ liệu ở một lớp, phép xử lý lại nằm ở lớp khác

Trong lập trình hướng đối tượng, mỗi đối tượng nên chịu trách nhiệm về những hành vi gắn trực tiếp với trạng thái và quy tắc mà nó nắm giữ. Một dấu hiệu thiết kế chưa tốt xuất hiện khi lớp A thường xuyên lấy dữ liệu của lớp B, rồi tự thực hiện phần lớn phép tính hay quyết định vốn thuộc về B.

Ví dụ: dịch vụ thanh toán phải đi qua từng dòng hàng, lấy đơn giá và số lượng, tự nhân để ra thành tiền, cộng tổng rồi áp dụng giảm giá của đơn hàng. Dịch vụ này đang biết quá nhiều về cấu trúc bên trong của đơn hàng.

Mùi mã này thường được gọi là **Feature Envy** (một phương thức quá quan tâm đến dữ liệu của đối tượng khác). Cách tái cấu trúc phù hợp trong nhiều trường hợp là **Move Method — chuyển phương thức/hành vi tới đối tượng sở hữu thông tin và quy tắc liên quan**. Đôi khi cần chia một phương thức lớn thành nhiều hành vi nhỏ rồi chuyển chúng tới những đối tượng khác nhau.

Mục tiêu là:
- Đưa tính toán thành tiền về **OrderLine**, vì nó biết đơn giá và số lượng.
- Đưa tổng tiền và chính sách giảm giá cố định của đơn về **Order**, vì nó sở hữu các dòng hàng và thông tin ưu đãi.
- Giữ thao tác gọi cổng thanh toán trong **CheckoutService**, vì đây là trách nhiệm phối hợp với hệ thống bên ngoài.
- Duy trì kết quả, lỗi và hợp đồng được kiểm thử trong quá trình refactor.

**Không có quy tắc "mọi phương thức phải nằm trong lớp giữ dữ liệu".** Chọn nơi đặt hành vi dựa trên trách nhiệm nghiệp vụ, tính kết dính, mức phụ thuộc và khả năng thay đổi.

## 2. Nhìn vào thiết kế trước khi refactor

Đoạn mã minh họa dưới đây dùng hai lớp dữ liệu kiểu cũ. Phần tính tiền nằm hoàn toàn trong một dịch vụ:

~~~java
import java.util.List;

record LegacyLine(String sku, long priceVnd, int quantity) {}

record LegacyOrder(
        String id,
        boolean vip,
        List<LegacyLine> lines) {}

final class LegacyCheckoutService {
    long calculatePayable(LegacyOrder order) {
        long subtotal = 0;

        for (LegacyLine line : order.lines()) {
            subtotal += line.priceVnd() * line.quantity();
        }

        if (order.vip()) {
            return subtotal - subtotal / 10;
        }
        return subtotal;
    }
}
~~~

Đây là mã lược giản để thấy vị trí trách nhiệm, chưa có xác thực dữ liệu hoặc kiểm tra tràn số. Logic nghiệp vụ minh họa: khách VIP giảm **10% của tổng tiền**, phần giảm làm tròn xuống theo đơn vị VND.

Vấn đề không nằm ở cú pháp vòng lặp. Vấn đề là LegacyCheckoutService biết cách định giá từng dòng hàng, biết cách cộng đơn và biết quy tắc ưu đãi. Khi OrderLine thay đổi cách tính thành tiền hoặc đơn hàng thêm quy tắc mới, lớp dịch vụ phải sửa dù vai trò chính của nó chỉ là điều phối checkout.

Một dấu hiệu thường gặp là chuỗi truy vấn:

~~~text
service → order.lines() → line.priceVnd()
                        → line.quantity()
                        → tính toán ngoài đối tượng dữ liệu
~~~

Thiết kế mong muốn:

~~~text
CheckoutService → Order.payableVnd()
                      ├── Order.subtotalVnd()
                      │      └── OrderLine.subtotalVnd()
                      └── Quy tắc giảm giá của đơn
~~~

Điểm khác biệt: lớp gọi yêu cầu **đối tượng làm việc của nó**, thay vì lấy hết dữ liệu để tự làm thay. Tư tưởng này thường được diễn đạt bằng nguyên tắc *Tell, Don't Ask*.

## 3. Xác định đúng chủ sở hữu hành vi

| Hành vi | Đặt ở đâu? | Vì sao? |
| --- | --- | --- |
| Nhân đơn giá với số lượng | OrderLine | Cả hai dữ liệu và bất biến của dòng hàng nằm tại đây |
| Cộng các dòng hàng | Order | Order sở hữu danh sách OrderLine |
| Tính số tiền phải trả theo ưu đãi VIP cố định của đơn | Order | Quy tắc gắn với trạng thái VIP của đơn trong ví dụ |
| Gọi API thu tiền | CheckoutService / PaymentGateway | Có tác dụng phụ, liên quan quy trình và hạ tầng |
| In hóa đơn dạng PDF hoặc JSON | Formatter / Presenter / Serializer | Quy tắc biểu diễn bên ngoài, không phải nghiệp vụ tính tiền |
| Tính khuyến mãi thay đổi theo chiến dịch/coupon phức tạp | DiscountPolicy hoặc PricingService chuyên trách | Quy tắc có vòng đời và nguồn dữ liệu độc lập với Order |

**Câu hỏi quyết định:** Đối tượng nào phải biết ít nhất về bên ngoài nhưng vẫn có đủ dữ liệu và trách nhiệm để thực hiện hành vi đúng? Nếu hành vi cần dữ liệu của nhiều aggregate hay gọi I/O, một domain service/application service có thể hợp lý hơn phương thức của entity.

~~~mermaid
classDiagram
    class OrderLine {
        -String sku
        -long unitPriceVnd
        -int quantity
        +subtotalVnd() long
    }
    class Order {
        -String id
        -boolean vip
        -List~OrderLine~ lines
        +subtotalVnd() long
        +payableVnd() long
    }
    class CheckoutService {
        -PaymentGateway gateway
        +checkout(Order) boolean
    }
    class PaymentGateway {
        <<interface>>
        +charge(String, long) boolean
    }
    Order "1" *-- "1..*" OrderLine
    CheckoutService --> Order : yêu cầu số tiền
    CheckoutService --> PaymentGateway : yêu cầu thanh toán
~~~

Ở đây mối quan hệ Order–OrderLine là quan hệ sở hữu về mặt mô hình. Order giữ một bản sao bất biến của danh sách để bên ngoài không thay đổi nội dung thông qua danh sách đã truyền vào.

## 4. Ví dụ sau refactor: chương trình Java 17 chạy được

Ví dụ dùng JDK 17, Maven và JUnit 5. Mỗi lớp public nằm trong tệp tương ứng.

~~~text
move-behavior-oop/
├── pom.xml
└── src/
    ├── main/java/vn/example/
    │   ├── OrderLine.java
    │   ├── Order.java
    │   ├── PaymentGateway.java
    │   ├── CheckoutService.java
    │   └── Main.java
    └── test/java/vn/example/
        ├── OrderTest.java
        └── CheckoutServiceTest.java
~~~

### 4.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0">
    <modelVersion>4.0.0</modelVersion>
    <groupId>vn.example</groupId>
    <artifactId>move-behavior-oop</artifactId>
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

### 4.2. Đưa phép tính dòng hàng vào OrderLine

**src/main/java/vn/example/OrderLine.java**

~~~java
package vn.example;

/** Một dòng hàng có số lượng dương và đơn giá không âm. */
public record OrderLine(String sku, long unitPriceVnd, int quantity) {
    public OrderLine {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (unitPriceVnd < 0) {
            throw new IllegalArgumentException(
                    "unitPriceVnd must not be negative");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive");
        }
    }

    /** Thành tiền theo VND; báo lỗi nếu vượt miền long. */
    public long subtotalVnd() {
        return Math.multiplyExact(unitPriceVnd, (long) quantity);
    }
}
~~~

Những chi tiết đáng chú ý:

- Record giữ trạng thái bất biến (các thành phần của record là final).
- Quy tắc quantity > 0, unitPriceVnd >= 0 được kiểm soát tại nơi tạo dòng hàng.
- OrderLine trả lời được câu hỏi "dòng hàng này có thành tiền bao nhiêu?" mà không cần lớp ngoài lấy hai trường rồi nhân.
- Math.multiplyExact ném ArithmeticException khi kết quả vượt miền long; toán tử nhân thông thường có thể tràn số âm/dương âm thầm.

Ta cho phép đơn giá 0 để biểu diễn hàng tặng; điều này là **một lựa chọn hợp đồng** của ví dụ, không phải quy tắc bắt buộc cho mọi hệ thống.

### 4.3. Đưa tổng tiền và quy tắc VIP về Order

**src/main/java/vn/example/Order.java**

~~~java
package vn.example;

import java.util.List;
import java.util.Objects;

public final class Order {
    private final String id;
    private final boolean vip;
    private final List<OrderLine> lines;

    public Order(String id, boolean vip, List<OrderLine> lines) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        Objects.requireNonNull(lines, "lines");
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("order must have lines");
        }

        this.id = id;
        this.vip = vip;
        // Tạo snapshot bất biến; List.copyOf cũng từ chối phần tử null.
        this.lines = List.copyOf(lines);
    }

    public String id() {
        return id;
    }

    public long subtotalVnd() {
        long result = 0L;
        for (OrderLine line : lines) {
            result = Math.addExact(result, line.subtotalVnd());
        }
        return result;
    }

    /** VIP giảm 10%; tiền giảm làm tròn xuống VND. */
    public long payableVnd() {
        long subtotal = subtotalVnd();
        long discount = vip ? subtotal / 10 : 0L;
        return subtotal - discount;
    }
}
~~~

Order chịu trách nhiệm phối hợp các dòng hàng để xác định giá trị của **chính đơn hàng đó**. Không cần đưa danh sách lines công khai để lớp CheckoutService duyệt. Cần xem xét trước khi thêm getter trả trạng thái nội bộ: một API truy vấn phục vụ hiển thị có thể hợp lệ, nhưng không nên dùng getter đó để lặp lại quy tắc tính tiền ở những lớp khác.

Trong phương thức payableVnd(), phép chia nguyên làm tròn xuống phần tiền giảm. Ví dụ subtotal 99 VND thì VIP giảm 9 VND, phải trả 90 VND. Khi nghiệp vụ đổi sang quy tắc làm tròn khác, thay đổi nên được kiểm thử rõ ràng.

### 4.4. Giữ hành vi điều phối tại CheckoutService

**src/main/java/vn/example/PaymentGateway.java**

~~~java
package vn.example;

@FunctionalInterface
public interface PaymentGateway {
    /** true nếu chấp nhận thanh toán, false nếu từ chối. */
    boolean charge(String orderId, long amountVnd);
}
~~~

**src/main/java/vn/example/CheckoutService.java**

~~~java
package vn.example;

import java.util.Objects;

public final class CheckoutService {
    private final PaymentGateway gateway;

    public CheckoutService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway, "gateway");
    }

    public boolean checkout(Order order) {
        Objects.requireNonNull(order, "order");
        return gateway.charge(order.id(), order.payableVnd());
    }
}
~~~

CheckoutService vẫn có một trách nhiệm rõ ràng: tổ chức hành động thanh toán. Nó không giữ phép nhân, vòng lặp cộng tiền hoặc nhánh VIP. Khi cần thay cổng thanh toán thật bằng fake trong unit test, ta tiêm implementation PaymentGateway khác.

**src/main/java/vn/example/Main.java**

~~~java
package vn.example;

import java.util.List;

public class Main {
    public static void main(String[] args) {
        Order order = new Order(
                "DH-100",
                true,
                List.of(
                        new OrderLine("BOOK", 100_000, 2),
                        new OrderLine("PEN", 30_000, 1)));

        PaymentGateway demoGateway = (id, amount) -> {
            System.out.println(
                    "Payment request: " + id + " = " + amount + " VND");
            return true;
        };

        CheckoutService service = new CheckoutService(demoGateway);

        System.out.println("Subtotal: " + order.subtotalVnd());
        System.out.println("Payable: " + order.payableVnd());
        System.out.println("Accepted: " + service.checkout(order));
    }
}
~~~

Chạy từ thư mục dự án:

~~~bash
mvn test
mvn -q -DskipTests package
java -cp target/classes vn.example.Main
~~~

Kết quả mong đợi:

~~~text
Subtotal: 230000
Payable: 207000
Payment request: DH-100 = 207000 VND
Accepted: true
~~~

Ở bản demo, PaymentGateway chỉ in thông tin và trả true; đây không phải giao dịch thanh toán thật. Đối tượng Order có thể tự xác định tiền phải trả, còn lớp điều phối chỉ giao tiếp với cổng thanh toán.

## 5. Viết kiểm thử bảo vệ hành vi khi di chuyển phương thức

Refactor đúng nghĩa phải giữ nguyên hành vi bên ngoài theo **hợp đồng đã chọn**. Trước khi di chuyển mã trong một dự án đang hoạt động, nên có những test đặc trưng (characterization tests) xác định giá trị và nhánh hiện tại. Sau khi di chuyển, test ở cấp đối tượng và cấp luồng phải tiếp tục đạt.

**src/test/java/vn/example/OrderTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class OrderTest {
    @Test
    void subtotalComesFromOrderLines() {
        Order order = new Order("O-1", false, List.of(
                new OrderLine("A", 100_000, 2),
                new OrderLine("B", 30_000, 1)));

        assertEquals(230_000L, order.subtotalVnd());
        assertEquals(230_000L, order.payableVnd());
    }

    @Test
    void vipDiscountIsAppliedOnceAtOrderLevel() {
        Order order = new Order("O-2", true, List.of(
                new OrderLine("A", 100_000, 2),
                new OrderLine("B", 30_000, 1)));

        assertEquals(230_000L, order.subtotalVnd());
        assertEquals(207_000L, order.payableVnd());
    }

    @Test
    void fractionalDiscountIsRoundedDownInVnd() {
        Order order = new Order("O-3", true, List.of(
                new OrderLine("A", 99, 1)));

        assertEquals(99L, order.subtotalVnd());
        assertEquals(90L, order.payableVnd());
    }

    @Test
    void orderDoesNotChangeWhenInputListChanges() {
        List<OrderLine> input = new ArrayList<>();
        input.add(new OrderLine("A", 100, 1));

        Order order = new Order("O-4", false, input);
        input.add(new OrderLine("B", 200, 1));

        assertEquals(100L, order.payableVnd());
    }

    @Test
    void validatesItsOwnInvariants() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("X", -1, 1));
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine("X", 10, 0));
        assertThrows(IllegalArgumentException.class,
                () -> new OrderLine(" ", 10, 1));
        assertThrows(IllegalArgumentException.class,
                () -> new Order("O-5", false, List.of()));
        assertThrows(IllegalArgumentException.class,
                () -> new Order("", false,
                        List.of(new OrderLine("X", 1, 1))));
    }

    @Test
    void rejectsOverflowInsteadOfSilentlyWrapping() {
        OrderLine line = new OrderLine("X", Long.MAX_VALUE, 2);
        assertThrows(ArithmeticException.class, line::subtotalVnd);

        Order order = new Order("O-6", false, List.of(
                new OrderLine("A", Long.MAX_VALUE, 1),
                new OrderLine("B", 1, 1)));

        assertThrows(ArithmeticException.class, order::subtotalVnd);
    }
}
~~~

**src/test/java/vn/example/CheckoutServiceTest.java**

~~~java
package vn.example;

import static org.junit.jupiter.api.Assertions.*;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class CheckoutServiceTest {
    @Test
    void passesComputedAmountToGatewayExactlyOnce() {
        List<String> calls = new ArrayList<>();
        PaymentGateway gateway = (id, amount) -> {
            calls.add(id + ":" + amount);
            return true;
        };

        Order order = new Order("DH-100", true, List.of(
                new OrderLine("BOOK", 100_000, 2),
                new OrderLine("PEN", 30_000, 1)));

        CheckoutService service = new CheckoutService(gateway);

        assertTrue(service.checkout(order));
        assertEquals(List.of("DH-100:207000"), calls);
    }

    @Test
    void preservesPaymentRejection() {
        List<Long> charged = new ArrayList<>();
        PaymentGateway gateway = (id, amount) -> {
            charged.add(amount);
            return false;
        };

        Order order = new Order("DH-101", false, List.of(
                new OrderLine("PEN", 30_000, 2)));

        assertFalse(new CheckoutService(gateway).checkout(order));
        assertEquals(List.of(60_000L), charged);
    }

    @Test
    void nullOrderIsRejectedBeforeCallingGateway() {
        List<String> calls = new ArrayList<>();
        PaymentGateway gateway = (id, amount) -> {
            calls.add(id);
            return true;
        };

        CheckoutService service = new CheckoutService(gateway);

        assertThrows(NullPointerException.class,
                () -> service.checkout(null));
        assertTrue(calls.isEmpty());
    }
}
~~~

Đây là **9 phương thức @Test** (6 test Order và 3 test CheckoutService). Khi chạy đúng cấu trúc Maven trên, bộ test dự kiến có 9 lượt và không có failure/error.

Các test cấp Order chứng minh trách nhiệm đã được chuyển đúng nơi và phép tính vẫn chính xác. Các test CheckoutService chứng minh luồng bên ngoài tiếp tục dùng đúng số tiền, truyền đúng mã đơn và không gọi cổng thanh toán sai trường hợp. Test không cần truy cập trường private của Order.

| Kiểm thử | Trách nhiệm được kiểm tra | Sai sót có thể phát hiện |
| --- | --- | --- |
| subtotalComesFromOrderLines | Order tổng hợp các thành tiền từ OrderLine | Quên dòng hàng hoặc tính nhầm số lượng |
| vipDiscountIsAppliedOnceAtOrderLevel | Giảm 10% một lần trên tổng đơn | Giảm hai lần hoặc tính sai phạm vi |
| fractionalDiscountIsRoundedDownInVnd | Làm tròn theo hợp đồng | Sai 1 VND ở biên |
| orderDoesNotChangeWhenInputListChanges | Đóng gói và snapshot bất biến | Thay đổi đơn từ bên ngoài |
| validatesItsOwnInvariants | Bất biến ở chủ sở hữu dữ liệu | Cho dữ liệu sai đi sâu vào quy trình |
| rejectsOverflowInsteadOfSilentlyWrapping | Phép tính có kiểm tra tràn | Thành tiền âm vì overflow |
| passesComputedAmountToGatewayExactlyOnce | Điều phối vẫn đúng sau refactor | Gửi số tiền cũ, gọi gateway lặp |
| preservesPaymentRejection | Giữ ngữ nghĩa kết quả | Đổi false thành true |
| nullOrderIsRejectedBeforeCallingGateway | Không gây tác dụng phụ khi đầu vào null | Gọi phụ thuộc với dữ liệu không hợp lệ |

## 6. Các bước refactor an toàn trong hệ thống hiện có

Thực hiện trên một thay đổi nhỏ, có thể kiểm chứng:

1. **Khoanh vùng hành vi.** Xác định phương thức đang đọc nhiều trường của đối tượng khác. Hỏi nó thực sự tính/ra quyết định dựa trên dữ liệu nào, và có gây I/O không.
2. **Chốt hợp đồng cũ.** Viết hoặc giữ test cho các trường hợp phổ biến, biên, lỗi, làm tròn và các caller quan trọng. Với tính toán tiền, kiểm tra tràn số và đơn vị tiền tệ.
3. **Tạo phương thức tại đối tượng đích.** Bắt đầu với OrderLine.subtotalVnd(); cho phương thức cũ gọi phương thức mới để có thể kiểm chứng từng bước.
4. **Di chuyển phần tổng hợp.** Thêm Order.subtotalVnd() rồi Order.payableVnd(). Chuyển những chi tiết tính tiền ra khỏi lớp điều phối.
5. **Chỉnh caller.** CheckoutService hỏi order.payableVnd() thay vì duyệt order.lines() và kiểm tra trạng thái VIP.
6. **Chạy kiểm thử mỗi bước.** Đảm bảo kết quả, số lần tương tác, exception và quy tắc rounding không đổi khi chuyển.
7. **Dọn đường gọi cũ.** Nếu phương thức cũ là API công khai, cân nhắc giữ adapter ủy quyền trong giai đoạn chuyển đổi; khi caller đã chuyển hết và không còn yêu cầu tương thích, loại bỏ hàm tính trùng. Nếu là API nội bộ, có thể xóa ngay khi đã xác minh không còn caller.
8. **Đánh giá lại thiết kế.** Xem coupling, cohesion, vòng đời đối tượng, quyền thay đổi dữ liệu và liệu phương thức đích có thật sự hiểu quy tắc nghiệp vụ.

Có thể dùng trình tự nhỏ thay vì chuyển cả một khối mã lớn. Các IDE Java hỗ trợ thao tác *Move Instance Method*, nhưng công cụ tự động không hiểu đầy đủ ranh giới nghiệp vụ: vẫn phải kiểm thử và rà soát API.

~~~mermaid
flowchart TD
    A["Phát hiện Feature Envy"] --> B["Xác định dữ liệu và chủ sở hữu quy tắc"]
    B --> C["Chốt test hành vi hiện tại"]
    C --> D["Chuyển phép tính nhỏ vào OrderLine"]
    D --> E["Chuyển tổng hợp vào Order"]
    E --> F["Đổi CheckoutService thành điều phối"]
    F --> G["Chạy test và rà soát caller"]
    G --> H{"Giữ hợp đồng?"}
    H -->|Không| I["Sửa sai lệch, kiểm tra biên"]
    I --> G
    H -->|Có| J["Dọn phương thức trùng và kết thúc"]
~~~

## 7. Mối liên hệ với các nguyên tắc OOP

**Encapsulation (đóng gói).** Đối tượng có thể bảo vệ bất biến khi chính nó thực hiện thao tác trên dữ liệu mình sở hữu. Caller không cần biết danh sách dòng hàng được lưu bằng ArrayList, cấu trúc bất biến hay cơ chế lazy loading.

**High Cohesion (kết dính cao).** Phép tính thành tiền nằm cùng đơn giá và số lượng. Quy tắc tổng tiền nằm cùng toàn bộ đơn hàng. Mỗi thay đổi liên quan có xu hướng tập trung vào lớp thích hợp.

**Low Coupling (liên kết lỏng).** CheckoutService chỉ phụ thuộc vào giao diện nghiệp vụ gọn của Order: id() và payableVnd(), thay vì từng getter trên các dòng hàng và quy tắc VIP. Chuyển nhiều dòng code sang đối tượng khác nhưng vẫn yêu cầu caller đọc cùng lượng dữ liệu không thực sự cải thiện coupling.

**Single Responsibility Principle (SRP).** Lý do thay đổi liên quan giá trị dòng hàng thuộc OrderLine; lý do thay đổi quy tắc tính tổng cơ bản thuộc Order; thay đổi quy trình thu tiền thuộc CheckoutService. SRP không có nghĩa mỗi lớp chỉ được có một phương thức.

**Information Expert (nguyên tắc GRASP).** Giao trách nhiệm cho đối tượng có đủ thông tin để làm tốt nhiệm vụ. Đây là hướng dẫn hữu ích để chọn nơi đặt phương thức, nhưng phải cân bằng với ranh giới transaction, security, phân quyền, hiệu năng và domain.

**Tell, Don't Ask.** Hãy gọi một hành vi biểu đạt ý định như order.payableVnd() thay vì hỏi hết dữ liệu rồi tự suy luận. Tuy nhiên, đọc dữ liệu qua API truy vấn cho UI, báo cáo hoặc serialization là nhu cầu chính đáng; không phải getter nào cũng là mùi mã.

## 8. Khi nào KHÔNG nên chuyển phương thức?

| Tình huống | Vì sao không nên chuyển vội | Phương án cân nhắc |
| --- | --- | --- |
| Hành vi sử dụng nhiều domain object ngang vai trò | Không có một đối tượng tự nhiên chịu toàn bộ quy tắc | Domain service / policy riêng |
| Thuật toán phụ thuộc API mạng, database, gửi email | Entity sẽ mang phụ thuộc I/O và khó kiểm soát transaction | Application service hoặc adapter |
| Quy tắc khuyến mãi thường đổi, cần nhiều chiến lược | Nhồi toàn bộ điều kiện vào Order làm lớp phình to | DiscountPolicy / Strategy |
| Logic định dạng màn hình hoặc xuất file | Làm domain object phụ thuộc giao diện hiển thị | Presenter / formatter |
| Di chuyển tạo phụ thuộc vòng giữa các lớp | Kết dính có thể giảm, thiết kế khó hiểu hơn | Tách collaborator hoặc xem lại ranh giới |
| Phương thức đọc nhiều dữ liệu từ hai aggregate lớn | Có thể gây nạp dư dữ liệu hoặc phá transaction boundary | Query service, domain service hoặc DTO chuyên dụng |
| Mã logic thực sự dùng trạng thái của đối tượng nguồn | Chuyển sẽ làm đích phải phụ thuộc ngược lại nguồn | Giữ tại nguồn hoặc trích thành phần nhỏ |

Một nguyên tắc thực hành: **chuyển phần có cùng lý do thay đổi, không di chuyển máy móc chỉ vì thấy nhiều dấu chấm getter**.

Ví dụ, nếu giảm giá được tính theo mã chiến dịch từ nhiều hệ thống, việc đưa toàn bộ chiến dịch vào Order sẽ khiến Order phụ thuộc vào API coupon. Giải pháp hợp lý có thể là PricingPolicy tính mức giảm và Order quản lý các bất biến của đơn; CheckoutService phối hợp các bước cần thiết.

## 9. Bài tập mở rộng

**Bài 1 — Phát hiện hành vi đặt sai chỗ.** Giả sử ReportService duyệt danh sách OrderLine để tính số lượng sản phẩm. Hãy phân biệt hai nhu cầu:
- Nếu muốn biết tổng số lượng của **một đơn**, cân nhắc Order.totalQuantity().
- Nếu muốn tổng số lượng đã bán trong **một khoảng thời gian từ nhiều đơn**, báo cáo/query service có thể là chủ sở hữu hợp lý.

**Bài 2 — Refactor giỏ hàng.** Tạo CartItem(price, quantity) và Cart(items). Ban đầu CartService tính tổng; sau đó chuyển phép tính từng dòng vào CartItem và phép cộng vào Cart. Viết test bảo vệ trường hợp giỏ rỗng, số lượng không hợp lệ, tràn số và thay đổi danh sách đầu vào.

**Bài 3 — Chính sách giảm giá có thể thay đổi.** Thêm interface DiscountPolicy với phương thức tính số tiền giảm. Thử thiết kế để Order chịu trách nhiệm tổng hợp còn chính sách giảm giá do một đối tượng chuyên trách đảm nhiệm. Xác định rõ chính sách nào được cung cấp tại construction hoặc khi định giá, và tránh lưu giá không còn hợp lệ theo thời gian.

**Bài 4 — Xử lý migration API.** Nếu một module khác vẫn gọi PriceService.calculatePayable(order), hãy giữ tạm phương thức cũ ủy quyền cho order.payableVnd(), đánh dấu deprecated khi phù hợp, chuyển caller rồi xóa khi đã kiểm tra tác động tương thích.

**Tự đánh giá:** Sau refactor, một phương thức dùng dữ liệu của đối tượng nào thì trách nhiệm chủ yếu nằm tại đối tượng đó; các lớp điều phối hiểu ít hơn về chi tiết nội bộ; hành vi bên ngoài được test bảo vệ; và không phát sinh phụ thuộc vòng hay nhồi thêm I/O vào domain object.