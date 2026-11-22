# Kết hợp record, enum và interface để mô hình hóa miền dữ liệu

Khi mô hình hóa một miền nghiệp vụ, ta thường cần biểu diễn dữ liệu, giới hạn các giá trị hợp lệ và định nghĩa những hành vi mà nhiều kiểu có thể cùng cung cấp. Trong Java 17+, **record**, **enum** và **interface** giải quyết ba phần việc khác nhau và có thể phối hợp trong cùng một mô hình.

- **Record** phù hợp với dữ liệu có các thành phần xác định, chẳng hạn một dòng hàng hoặc một đơn hàng. Java tự sinh accessor, equals, hashCode và toString; record cũng là kiểu final.
- **Enum** biểu diễn một tập giá trị hữu hạn, có tên và được biết trước khi biên dịch, chẳng hạn trạng thái đơn hàng hoặc phương thức giao hàng. Mỗi hằng enum có thể mang dữ liệu và triển khai hành vi riêng.
- **Interface** mô tả một khả năng hoặc hợp đồng mà nhiều kiểu có thể thực hiện. Một record hoặc enum có thể triển khai nhiều interface để được sử dụng thông qua cùng một kiểu trừu tượng.

Không nên dùng một trong ba cấu trúc cho mọi mục đích. Hãy chọn theo bản chất của dữ liệu và quy tắc nghiệp vụ, rồi kết hợp chúng khi các trách nhiệm đó giao nhau.

## 1. Tách dữ liệu, tập lựa chọn và hợp đồng

Giả sử ứng dụng cần mô hình hóa đơn hàng trực tuyến.

| Thành phần | Vai trò trong miền nghiệp vụ |
|---|---|
| OrderLine (record) | Mã hàng, số lượng, đơn giá; tự tính thành tiền |
| Order (record) | Mã đơn, các dòng hàng, phương thức giao hàng và trạng thái |
| ShippingMethod (enum) | Tập phương thức giao hàng được hỗ trợ, mỗi phương thức có phí và thời gian dự kiến |
| OrderStatus (enum) | Tập trạng thái hợp lệ và quy tắc chuyển trạng thái |
| LineAmount (interface) | Hợp đồng cho đối tượng có thể tính thành tiền |
| Labeled (interface) | Hợp đồng cung cấp nhãn hiển thị cho nhiều kiểu miền nghiệp vụ |

Mô hình này có hai lợi ích. Thứ nhất, record gom dữ liệu liên quan vào một giá trị rõ ràng. Thứ hai, enum giữ những lựa chọn có giới hạn ở một nơi và có thể gắn hành vi với từng lựa chọn. Interface cho phép phần gọi làm việc với khả năng mà một đối tượng cung cấp thay vì phụ thuộc vào lớp cụ thể.

## 2. Ví dụ hoàn chỉnh chạy trên Java 17+

Lưu toàn bộ mã sau vào tệp **OrderDomainDemo.java**. Các interface, record và enum phụ trợ được khai báo ở cấp cao nhất với phạm vi package; lớp công khai OrderDomainDemo là điểm vào chương trình.

~~~java
import java.math.BigDecimal;
import java.util.List;
import java.util.Objects;

interface Labeled {
    String label();
}

interface LineAmount {
    BigDecimal amount();
}

record OrderLine(String sku, int quantity, BigDecimal unitPrice)
        implements LineAmount {
    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }
    }

    @Override
    public BigDecimal amount() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}

enum ShippingMethod implements Labeled {
    STANDARD("Standard", new BigDecimal("3.50"), 5),
    EXPRESS("Express", new BigDecimal("9.00"), 2);

    private final String label;
    private final BigDecimal fee;
    private final int deliveryDays;

    ShippingMethod(String label, BigDecimal fee, int deliveryDays) {
        this.label = label;
        this.fee = fee;
        this.deliveryDays = deliveryDays;
    }

    @Override
    public String label() {
        return label;
    }

    public BigDecimal fee() {
        return fee;
    }

    public int deliveryDays() {
        return deliveryDays;
    }
}

enum OrderStatus implements Labeled {
    DRAFT("Draft"),
    PAID("Paid"),
    SHIPPED("Shipped"),
    CANCELLED("Cancelled");

    private final String label;

    OrderStatus(String label) {
        this.label = label;
    }

    @Override
    public String label() {
        return label;
    }

    public boolean canTransitionTo(OrderStatus next) {
        Objects.requireNonNull(next, "next");

        return switch (this) {
            case DRAFT -> next == PAID || next == CANCELLED;
            case PAID -> next == SHIPPED || next == CANCELLED;
            case SHIPPED, CANCELLED -> false;
        };
    }
}

record Order(
        String id,
        List<OrderLine> lines,
        ShippingMethod shippingMethod,
        OrderStatus status
) implements Labeled {
    public Order {
        Objects.requireNonNull(id, "id");
        Objects.requireNonNull(lines, "lines");
        Objects.requireNonNull(shippingMethod, "shippingMethod");
        Objects.requireNonNull(status, "status");

        if (id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one line");
        }

        // Make a defensive, unmodifiable copy of the supplied list.
        lines = List.copyOf(lines);
    }

    public BigDecimal subtotal() {
        return lines.stream()
                .map(OrderLine::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);
    }

    public BigDecimal total() {
        return subtotal().add(shippingMethod.fee());
    }

    @Override
    public String label() {
        return id + " - " + status.label();
    }

    public Order withStatus(OrderStatus next) {
        if (!status.canTransitionTo(next)) {
            throw new IllegalStateException(
                    "Cannot transition from " + status + " to " + next);
        }

        // Records are immutable values: return a new Order with the new status.
        return new Order(id, lines, shippingMethod, next);
    }
}

public class OrderDomainDemo {
    public static void main(String[] args) {
        Order order = new Order(
                "ORD-1001",
                List.of(
                        new OrderLine("BOOK-JAVA", 2, new BigDecimal("19.90")),
                        new OrderLine("MUG", 1, new BigDecimal("8.50"))
                ),
                ShippingMethod.EXPRESS,
                OrderStatus.PAID
        );

        System.out.println("Order: " + order.label());
        System.out.println("Items: " + order.lines().size());
        System.out.println("Subtotal: " + order.subtotal().setScale(2));
        System.out.println("Shipping: " + order.shippingMethod().label()
                + " (" + order.shippingMethod().deliveryDays()
                + " days) = " + order.shippingMethod().fee().setScale(2));
        System.out.println("Total: " + order.total().setScale(2));
        System.out.println("Transition: "
                + order.withStatus(OrderStatus.SHIPPED).label());

        List<Labeled> labels = List.of(
                order.status(),
                order.shippingMethod(),
                order
        );
        System.out.println("Labels through interface:");
        for (Labeled value : labels) {
            System.out.println("- " + value.label());
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa tệp:

~~~bash
javac OrderDomainDemo.java
java OrderDomainDemo
~~~

Kết quả chuẩn:

~~~text
Order: ORD-1001 - Paid
Items: 2
Subtotal: 48.30
Shipping: Express (2 days) = 9.00
Total: 57.30
Transition: ORD-1001 - Shipped
Labels through interface:
- Paid
- Express
- ORD-1001 - Paid
~~~

## 3. Vì sao các kiểu này phối hợp được?

### Record giữ dữ liệu và bảo vệ các bất biến cơ bản

OrderLine gom mã hàng, số lượng và đơn giá thành một giá trị. Constructor dạng compact cho phép kiểm tra dữ liệu đầu vào mà không cần viết lại toàn bộ phép gán trường. Sau khi constructor hoàn tất, các thành phần của record không thể được gán lại; Java tự cung cấp accessor như sku(), quantity() và unitPrice().

Order chứa danh sách dòng hàng, phương thức giao hàng và trạng thái. List.copyOf tạo một bản sao không thể sửa đổi của danh sách đầu vào, vì vậy bên gọi không thể thay đổi danh sách gốc rồi làm thay đổi nội dung Order. Đây là **bất biến nông**: nếu record chứa một đối tượng có thể thay đổi mà không sao chép hoặc bảo vệ đối tượng đó, trạng thái bên trong vẫn có thể bị thay đổi. Trong ví dụ này, OrderLine cũng là record và BigDecimal là bất biến nên dữ liệu dòng hàng phù hợp với cách dùng đó.

Record không tự kiểm tra mọi quy tắc nghiệp vụ. Constructor ở ví dụ kiểm tra mã đơn, số lượng, đơn giá và danh sách rỗng. Những quy tắc phụ thuộc vào dữ liệu lưu trữ, người dùng hiện tại hoặc hệ thống bên ngoài thường cần được kiểm tra ở tầng nghiệp vụ phù hợp.

### Enum biểu diễn lựa chọn hữu hạn và gắn hành vi vào lựa chọn

ShippingMethod có hai hằng được khai báo trước: STANDARD và EXPRESS. Mỗi hằng có nhãn, phí và số ngày giao dự kiến. Khi bổ sung một phương thức giao hàng mới, ta bổ sung hằng và các giá trị liên quan tại một chỗ thay vì truyền những chuỗi tự do như "express" xuyên suốt ứng dụng.

OrderStatus cũng là tập trạng thái hữu hạn. Phương thức canTransitionTo tập trung quy tắc chuyển trạng thái: đơn ở DRAFT có thể chuyển sang PAID hoặc CANCELLED; đơn ở PAID có thể chuyển sang SHIPPED hoặc CANCELLED; SHIPPED và CANCELLED là trạng thái kết thúc trong mô hình minh họa. Order.withStatus dùng quy tắc đó để từ chối chuyển đổi không hợp lệ và trả về một Order mới khi chuyển đổi hợp lệ.

Đây là quy tắc ví dụ để minh họa mô hình hóa, không phải quy trình phù hợp cho mọi hệ thống. Nghiệp vụ thực tế có thể cần thêm trạng thái, điều kiện thanh toán, quyền người dùng, kiểm soát đồng thời và lưu lịch sử chuyển trạng thái.

### Interface mô tả khả năng chung

LineAmount chỉ yêu cầu một phương thức amount(). OrderLine triển khai hợp đồng này bằng cách nhân đơn giá với số lượng. Mã tính tổng có thể gọi amount() mà không cần biết cách mỗi loại dòng hàng tính ra số tiền.

Labeled yêu cầu label(). OrderStatus, ShippingMethod và Order cùng triển khai interface đó. Vì vậy, chương trình có thể đặt các đối tượng khác kiểu vào một List&lt;Labeled&gt; rồi xử lý tất cả theo cùng một cách. Đây là đa hình: mã gọi dựa vào hợp đồng chung, còn phương thức được thực thi phụ thuộc vào kiểu đối tượng thực tế.

Interface không lưu trạng thái đối tượng như một record. Nó chủ yếu xác định những thao tác mà kiểu triển khai cam kết cung cấp. Record và enum vẫn giữ dữ liệu, còn interface cho phép sử dụng các kiểu đó thông qua một hợp đồng ổn định.

## 4. Những giới hạn cần nhớ

- **Record là final.** Không thể tạo lớp con của Order hoặc OrderLine. Nếu cần một hệ phân cấp kiểu, hãy cân nhắc interface hoặc một thiết kế khác phù hợp hơn.
- **Enum không thể kế thừa lớp miền nghiệp vụ tùy ý.** Mỗi enum đã kế thừa java.lang.Enum, nhưng có thể triển khai một hoặc nhiều interface. Dùng enum khi tập lựa chọn thực sự hữu hạn và được kiểm soát.
- **Interface không bảo đảm mọi quy tắc được thực hiện đúng.** Nó bảo đảm kiểu triển khai cung cấp các phương thức đã khai báo; tính đúng đắn của phần triển khai vẫn cần được thiết kế và kiểm thử.
- **Record không tự tạo bản sao sâu.** Các thành phần tham chiếu vẫn có thể trỏ tới đối tượng mutable. Dùng kiểu bất biến hoặc sao chép phòng vệ khi cần bảo đảm dữ liệu không đổi.
- **Không dùng double cho phép tính tiền chính xác.** Ví dụ dùng BigDecimal và tạo giá trị từ chuỗi thập phân. Hệ thống thực tế còn cần xác định đơn vị tiền, quy tắc làm tròn, thuế, chiết khấu và cách lưu số tiền.
- **Không để enum trở thành nơi chứa mọi logic.** Hành vi gắn trực tiếp với một lựa chọn hữu hạn thường hợp lý; quy trình phức tạp phụ thuộc nhiều dịch vụ nên được đặt ở thành phần nghiệp vụ phù hợp.

## 5. Cách quyết định trong một mô hình mới

1. Xác định dữ liệu nào tạo thành một giá trị có cấu trúc rõ ràng. Nếu giá trị chủ yếu gồm các thành phần xác định và không cần định danh mutable riêng, hãy cân nhắc record.
2. Xác định các lựa chọn có tập hữu hạn, ổn định hay không. Nếu đúng, enum giúp tránh chuỗi tùy ý và tập trung dữ liệu hoặc hành vi gắn với từng lựa chọn.
3. Xác định những thao tác mà nhiều kiểu cần cung cấp. Nếu phần gọi chỉ cần biết khả năng đó, hãy diễn tả nó bằng interface.
4. Đặt kiểm tra bất biến tại nơi tạo giá trị; đặt quy tắc chuyển đổi trạng thái tại mô hình hoặc dịch vụ nghiệp vụ có đủ thông tin để quyết định.
5. Kiểm tra cả đường đi hợp lệ và không hợp lệ: dữ liệu đầu vào sai, chuyển trạng thái bị cấm, tổng tiền và hành vi đa hình qua interface.

Kết hợp đúng cách giúp mô hình miền dữ liệu dễ đọc hơn: record làm rõ dữ liệu, enum giới hạn những lựa chọn đã biết, còn interface cho phép nhiều kiểu cung cấp chung một hành vi. Mỗi cấu trúc có trách nhiệm riêng nên thay đổi nghiệp vụ cũng dễ xác định hơn nơi cần chỉnh sửa.
