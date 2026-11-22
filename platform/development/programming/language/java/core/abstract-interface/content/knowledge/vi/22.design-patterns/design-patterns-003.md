# Strategy: thay thuật toán qua interface trong Java

**Strategy** là mẫu thiết kế hành vi cho phép định nghĩa một nhóm thuật toán, đóng gói từng thuật toán thành một triển khai riêng và thay thế chúng mà không phải viết lại đối tượng sử dụng thuật toán. Trong Java, interface thường là điểm chung để các chiến lược tuân theo cùng một hợp đồng.

Ví dụ, một màn hình thanh toán có thể tính giá bằng nhiều chính sách giảm giá. Nếu mỗi chính sách được viết thành một lớp triển khai cùng interface, chương trình có thể chọn chính sách phù hợp lúc chạy. Lớp thanh toán không cần biết chi tiết cách từng chính sách tính toán.

## 1. Bài toán mà Strategy giải quyết

Giả sử ứng dụng có ba cách giảm giá: không giảm, giảm theo phần trăm và giảm một số tiền cố định. Nếu gom tất cả vào một phương thức lớn với nhiều nhánh **if/else**, mỗi lần thêm chính sách mới, ta phải sửa phương thức đó. Khi số chính sách tăng, lớp điều phối sẽ biết quá nhiều chi tiết và khó kiểm thử.

Một cách triển khai ban đầu có thể trông như sau:

~~~java
BigDecimal totalFor(
        BigDecimal subtotal,
        String discountType) {
    if (discountType.equals("NONE")) {
        return subtotal;
    } else if (discountType.equals("PERCENT")) {
        return subtotal.multiply(new BigDecimal("0.90"));
    } else if (discountType.equals("FIXED")) {
        return subtotal.subtract(new BigDecimal("15.00"));
    }
    throw new IllegalArgumentException("Unknown discount type");
}
~~~

Đây chỉ là đoạn minh họa cho vấn đề: logic của nhiều thuật toán bị tập trung vào một nơi, chuỗi định danh có thể gõ sai, và việc thêm một thuật toán đòi hỏi sửa mã điều phối. Đoạn này cũng chưa xử lý đầy đủ quy tắc tiền tệ, chẳng hạn giới hạn tổng tiền không âm.

Strategy tách từng thuật toán thành một triển khai riêng. Lớp sử dụng giữ một tham chiếu đến interface, rồi gọi phương thức của interface để thực hiện hành vi đã chọn.

## 2. Cấu trúc của Strategy

Một thiết kế Strategy thường có ba vai trò:

1. **Strategy interface**: khai báo hợp đồng chung, ví dụ **DiscountStrategy**.
2. **Concrete strategies**: các lớp như **NoDiscount**, **PercentageDiscount** và **FixedDiscount**, mỗi lớp hiện thực một thuật toán.
3. **Context**: đối tượng sử dụng thuật toán. Trong ví dụ này, **Checkout** gọi interface mà nó được cung cấp và có thể nhận chiến lược khác trong lúc chạy.

Luồng gọi:

~~~mermaid
classDiagram
    class DiscountStrategy {
        <<interface>>
        +discountFor(subtotal) BigDecimal
        +name() String
    }
    class NoDiscount
    class PercentageDiscount
    class FixedDiscount
    class Checkout {
        -strategy DiscountStrategy
        +setStrategy(strategy)
        +totalFor(subtotal) BigDecimal
    }
    DiscountStrategy <|.. NoDiscount
    DiscountStrategy <|.. PercentageDiscount
    DiscountStrategy <|.. FixedDiscount
    Checkout --> DiscountStrategy : delegates to
~~~

Mũi tên quan trọng trong thiết kế là **Checkout** phụ thuộc vào **DiscountStrategy**, không phụ thuộc trực tiếp vào một lớp giảm giá cụ thể. Các chiến lược cụ thể đều đáp ứng cùng hợp đồng nên có thể được truyền vào **Checkout** thay thế cho nhau.

## 3. Ví dụ hoàn chỉnh với Java 17+

Ví dụ dùng **BigDecimal** để tính tiền thay vì **double**, vì số thập phân thông thường không luôn biểu diễn chính xác bằng số dấu phẩy động nhị phân. Mỗi chiến lược chỉ quyết định số tiền giảm; **Checkout** áp dụng giới hạn để mức giảm không âm và không vượt quá giá ban đầu.

Lưu toàn bộ mã sau vào tệp **StrategyDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

interface DiscountStrategy {
    BigDecimal discountFor(BigDecimal subtotal);

    String name();
}

final class NoDiscount implements DiscountStrategy {
    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return BigDecimal.ZERO;
    }

    @Override
    public String name() {
        return "No discount";
    }
}

final class PercentageDiscount implements DiscountStrategy {
    private final BigDecimal rate;

    PercentageDiscount(BigDecimal rate) {
        Objects.requireNonNull(rate, "rate");
        if (rate.compareTo(BigDecimal.ZERO) < 0
                || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException(
                    "rate must be between 0 and 1");
        }
        this.rate = rate;
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return subtotal.multiply(rate)
                .setScale(2, RoundingMode.HALF_UP);
    }

    @Override
    public String name() {
        return rate.multiply(new BigDecimal("100"))
                .stripTrailingZeros().toPlainString() + "% off";
    }
}

final class FixedDiscount implements DiscountStrategy {
    private final BigDecimal amount;

    FixedDiscount(BigDecimal amount) {
        Objects.requireNonNull(amount, "amount");
        if (amount.compareTo(BigDecimal.ZERO) < 0) {
            throw new IllegalArgumentException(
                    "amount must not be negative");
        }
        this.amount = amount.setScale(2, RoundingMode.HALF_UP);
    }

    @Override
    public BigDecimal discountFor(BigDecimal subtotal) {
        return amount;
    }

    @Override
    public String name() {
        return amount.toPlainString() + " off";
    }
}

final class Checkout {
    private DiscountStrategy strategy;

    Checkout(DiscountStrategy strategy) {
        setStrategy(strategy);
    }

    void setStrategy(DiscountStrategy strategy) {
        this.strategy = Objects.requireNonNull(
                strategy, "strategy");
    }

    BigDecimal totalFor(BigDecimal subtotal) {
        Objects.requireNonNull(subtotal, "subtotal");
        if (subtotal.compareTo(BigDecimal.ZERO) < 0) {
            throw new IllegalArgumentException(
                    "subtotal must not be negative");
        }

        BigDecimal discount = strategy.discountFor(subtotal);
        discount = discount.max(BigDecimal.ZERO).min(subtotal);
        return subtotal.subtract(discount)
                .setScale(2, RoundingMode.HALF_UP);
    }

    String strategyName() {
        return strategy.name();
    }
}

public class StrategyDemo {
    public static void main(String[] args) {
        BigDecimal subtotal = new BigDecimal("100.00");
        Checkout checkout = new Checkout(new NoDiscount());

        System.out.println(checkout.strategyName() + ": "
                + checkout.totalFor(subtotal).toPlainString());

        checkout.setStrategy(
                new PercentageDiscount(new BigDecimal("0.10")));
        System.out.println(checkout.strategyName() + ": "
                + checkout.totalFor(subtotal).toPlainString());

        checkout.setStrategy(
                new FixedDiscount(new BigDecimal("15.00")));
        System.out.println(checkout.strategyName() + ": "
                + checkout.totalFor(subtotal).toPlainString());
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~text
javac StrategyDemo.java
java StrategyDemo
~~~

Kết quả stdout:

~~~text
No discount: 100.00
10% off: 90.00
15.00 off: 85.00
~~~

### Đọc ví dụ theo từng bước

- **DiscountStrategy** định nghĩa hai thao tác mà mọi chiến lược phải cung cấp: tính số tiền giảm và trả về tên chiến lược.
- **NoDiscount**, **PercentageDiscount** và **FixedDiscount** thực hiện các thuật toán khác nhau nhưng cùng kiểu interface.
- **Checkout** là context. Nó gọi **strategy.discountFor(...)** mà không cần kiểm tra chiến lược hiện tại thuộc lớp nào.
- **setStrategy(...)** cho phép thay thuật toán lúc chạy. Sau khi thay, cùng một lời gọi **totalFor(...)** sẽ sử dụng hành vi của chiến lược mới.
- **Objects.requireNonNull** chặn việc truyền tham chiếu null; các constructor của chiến lược kiểm tra những tham số có thể làm thuật toán mất ý nghĩa.
- **Checkout** bảo đảm mức giảm nằm trong khoảng từ 0 đến giá ban đầu. Quy tắc này giữ cho tổng tiền không âm ngay cả khi một chiến lược được thêm vào sau này có lỗi.

Việc thay thế chỉ cần tuân thủ interface. Không cần sửa mã của **Checkout** khi thêm một chiến lược mới như giảm giá thành viên hoặc ưu đãi theo mùa.

## 4. Interface, kế thừa và composition

Strategy thường kết hợp **interface với composition**. Context chứa một đối tượng chiến lược và ủy quyền một phần công việc cho nó:

~~~java
private DiscountStrategy strategy;
~~~

Quan hệ này khác với kế thừa. **Checkout** không cần **extends PercentageDiscount**; nó có thể sử dụng bất kỳ đối tượng nào triển khai **DiscountStrategy**. Nhờ vậy, lựa chọn thuật toán không bị gắn cứng vào cây kế thừa của context.

Interface làm hợp đồng chung rõ ràng. Mỗi chiến lược vẫn có thể có trường và constructor riêng để giữ tham số cần thiết, như **rate** hoặc **amount**. Context chỉ dựa vào các phương thức công khai của interface.

## 5. Chọn chiến lược như thế nào?

Trong ứng dụng thực tế, việc chọn chiến lược thường dựa trên cấu hình, loại yêu cầu, trạng thái nghiệp vụ hoặc dữ liệu người dùng. Ví dụ, tầng dịch vụ có thể quyết định chính sách giảm giá rồi truyền đối tượng chiến lược vào **Checkout**.

Không nên để dữ liệu bên ngoài trực tiếp tạo tên lớp tùy ý bằng reflection. Thay vào đó, hãy ánh xạ giá trị cấu hình đã được kiểm tra sang những chiến lược được phép:

~~~java
DiscountStrategy strategy = switch (campaignType) {
    case "NONE" -> new NoDiscount();
    case "TEN_PERCENT" ->
            new PercentageDiscount(new BigDecimal("0.10"));
    case "FIXED_15" ->
            new FixedDiscount(new BigDecimal("15.00"));
    default -> throw new IllegalArgumentException(
            "Unsupported campaign: " + campaignType);
};
~~~

Đây là một đoạn trích để minh họa cách chọn, không phải chương trình độc lập. Nó giả định biến **campaignType** đã được khai báo và kiểm tra theo mô hình dữ liệu của ứng dụng. Việc chọn chiến lược có thể dùng **switch**, factory hoặc dependency injection; điểm cốt lõi của Strategy là phần sử dụng thuật toán làm việc qua interface.

## 6. Khi nào nên dùng Strategy?

Strategy phù hợp khi:

- Có nhiều thuật toán hoặc chính sách có thể thay thế nhau.
- Muốn chọn hành vi khi chạy thay vì cố định hành vi trong một chuỗi điều kiện lớn.
- Muốn kiểm thử từng thuật toán độc lập và kiểm thử context bằng một chiến lược giả.
- Muốn thêm biến thể mới mà giảm số thay đổi trong lớp đang sử dụng thuật toán.
- Các thuật toán có cùng mục đích nhưng khác cách thực hiện, ví dụ tính phí giao hàng, xác thực, định tuyến, nén dữ liệu hoặc lựa chọn chính sách giá.

Strategy có thể là quá mức cần thiết khi chỉ có một thuật toán ổn định và không có nhu cầu mở rộng. Thêm interface và nhiều lớp chỉ để bọc một phép tính đơn giản có thể làm chương trình khó đọc hơn. Hãy tạo các chiến lược riêng khi chúng biểu diễn những lựa chọn thực sự trong miền nghiệp vụ hoặc khi sự biến đổi đó có khả năng xuất hiện.

## 7. Lợi ích và đánh đổi

**Lợi ích**

- Giảm phụ thuộc giữa context và thuật toán cụ thể.
- Thêm thuật toán bằng một lớp triển khai interface mới.
- Kiểm thử các thuật toán riêng rẽ dễ hơn.
- Tránh để một lớp context phình to với nhiều nhánh điều kiện cho những hành vi thay thế nhau.

**Đánh đổi**

- Tăng số kiểu và đối tượng trong chương trình.
- Cần nơi quyết định chiến lược nào được dùng; interface không tự chọn chiến lược.
- Nếu có quá nhiều biến thể nhỏ, việc tìm lớp đang thực thi hành vi có thể mất thời gian.
- Thay chiến lược trong lúc chạy cần được quản lý cẩn thận nếu context được chia sẻ giữa nhiều luồng. Ví dụ này giả định mỗi **Checkout** được dùng theo cách tuần tự; nếu chia sẻ một instance giữa nhiều luồng, cần thiết kế việc cập nhật và đọc chiến lược sao cho an toàn.

## 8. Lỗi thường gặp

- **Đặt các nhánh if/else vào context rồi gọi đó là Strategy.** Nếu mọi thuật toán vẫn nằm trong một phương thức điều phối, phần thay đổi chưa được tách ra.
- **Cho context phụ thuộc trực tiếp vào lớp triển khai.** Khởi tạo chiến lược ở một composition root, factory hoặc tầng cấu hình, rồi truyền vào context qua interface.
- **Đưa quá nhiều trách nhiệm vào interface.** Chỉ khai báo những thao tác chung mà context thật sự cần; các chi tiết riêng có thể nằm trong từng chiến lược.
- **Bỏ qua kiểm tra tham số.** Một chiến lược giảm giá phần trăm cần xác định miền giá trị hợp lệ; các thuật toán về tiền cần thống nhất cách làm tròn.
- **Nhầm Strategy với việc chỉ đổi dữ liệu.** Tham số cấu hình có thể thay đổi kết quả của cùng một thuật toán. Strategy đặc biệt hữu ích khi có những cách thực hiện riêng biệt cần thay thế qua cùng hợp đồng.
- **Quên nơi lựa chọn chiến lược.** Mẫu này tách nơi sử dụng khỏi thuật toán; nó không loại bỏ nhu cầu quyết định thuật toán nào phù hợp với mỗi yêu cầu.

## 9. Cách ghi nhớ

Strategy biến các thuật toán có thể thay thế thành những đối tượng tuân theo cùng một interface. Context giữ tham chiếu đến interface và ủy quyền công việc, nên có thể đổi thuật toán mà không cần viết lại context.

Khi áp dụng, hãy xác định phần nào thường xuyên thay đổi, đặt hợp đồng tối thiểu cho phần đó, viết mỗi thuật toán thành một triển khai riêng và để một tầng phù hợp quyết định chiến lược được sử dụng. Chỉ dùng mẫu này khi lợi ích từ việc tách và thay thế thuật toán lớn hơn chi phí của các kiểu bổ sung.
