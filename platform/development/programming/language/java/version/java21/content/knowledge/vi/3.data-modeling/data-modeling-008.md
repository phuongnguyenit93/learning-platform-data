# Ranh giới giữa mô hình dữ liệu bằng record và đối tượng có hành vi, vòng đời

Trong Java 21, `record` và `class` đều định nghĩa kiểu tham chiếu, đều có thể chứa dữ liệu và phương thức. Điểm khác nhau nằm ở ý nghĩa mà kiểu đó muốn thể hiện: `record` mô tả một giá trị được xác định bởi các thành phần dữ liệu của nó; `class` phù hợp khi đối tượng cần kiểm soát trạng thái, bảo vệ bất biến và quản lý các chuyển đổi trong suốt vòng đời.

Đây không phải quy tắc “record chỉ có dữ liệu, class mới có hành vi”. Record vẫn có thể kiểm tra dữ liệu và cung cấp phương thức nghiệp vụ. Class cũng có thể bất biến và chỉ chứa dữ liệu. Khi thiết kế, hãy quyết định dựa trên identity, equality, khả năng thay đổi trạng thái và trách nhiệm quản lý vòng đời.

## 1. Record biểu diễn một giá trị dữ liệu

Một record khai báo rõ các thành phần tạo nên giá trị. Java tự sinh các thành phần cơ bản dựa trên khai báo đó:

- Trường thành phần tương ứng với mỗi record component; các trường này là `private final`.
- Accessor cùng tên component, ví dụ `quantity()`.
- Constructor chuẩn (canonical constructor) nhận các component.
- `equals()`, `hashCode()` và `toString()` dựa trên các component.

Ví dụ một dòng hàng trong đơn hàng:

```java
import java.math.BigDecimal;
import java.util.Objects;

public record OrderLine(
        String productCode,
        int quantity,
        BigDecimal unitPrice) {

    public OrderLine {
        Objects.requireNonNull(productCode, "productCode");
        Objects.requireNonNull(unitPrice, "unitPrice");
        productCode = productCode.trim();

        if (productCode.isEmpty()) {
            throw new IllegalArgumentException("productCode is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice cannot be negative");
        }
    }

    public BigDecimal lineTotal() {
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
```

Constructor rút gọn (compact constructor) cho phép kiểm tra hoặc chuẩn hóa tham số. Java tự gán tham số vào các trường component sau khi phần thân constructor kết thúc bình thường. Record vì vậy vẫn có thể bảo vệ điều kiện hợp lệ của dữ liệu và cung cấp hành vi tính toán gắn trực tiếp với giá trị đó.

Hai `OrderLine` có cùng `productCode`, `quantity` và `unitPrice` sẽ được xem là bằng nhau theo `equals()` mặc định của record, dựa trên quy tắc `equals()` của từng component. Đây là equality theo giá trị, phù hợp khi hai đối tượng mang cùng thông tin thì có thể thay thế cho nhau trong nghiệp vụ. Chú ý rằng `BigDecimal.equals()` phân biệt scale, nên `10.0` và `10.00` không bằng nhau; nếu nghiệp vụ xem chúng là cùng một giá trị tiền, hãy chuẩn hóa scale hoặc xác định chính sách equality phù hợp trước khi dùng record.

## 2. Class quản lý identity, trạng thái và chuyển đổi vòng đời

Khi đối tượng đại diện cho một thực thể có danh tính riêng và thay đổi theo thời gian, một class thường thể hiện ý nghĩa đó rõ hơn. Ví dụ, một đơn hàng có mã định danh, tập dòng hàng, trạng thái và thời điểm gửi. Các thao tác thay đổi phải tuân thủ quy tắc nghiệp vụ.

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

enum OrderStatus {
    DRAFT, SUBMITTED, CANCELLED
}

final class Order {
    private final UUID id;
    private final Instant createdAt;
    private final List<OrderLine> lines = new ArrayList<>();
    private OrderStatus status = OrderStatus.DRAFT;
    private Instant submittedAt;

    Order(UUID id, Instant createdAt) {
        this.id = Objects.requireNonNull(id);
        this.createdAt = Objects.requireNonNull(createdAt);
    }

    void addLine(OrderLine line) {
        requireDraft();
        lines.add(Objects.requireNonNull(line));
    }

    void submit(Instant now) {
        requireDraft();
        if (lines.isEmpty()) {
            throw new IllegalStateException("An empty order cannot be submitted");
        }
        submittedAt = Objects.requireNonNull(now);
        status = OrderStatus.SUBMITTED;
    }

    void cancel() {
        if (status == OrderStatus.CANCELLED) {
            throw new IllegalStateException("Order is already cancelled");
        }
        status = OrderStatus.CANCELLED;
    }

    List<OrderLine> lines() {
        return List.copyOf(lines);
    }

    OrderStatus status() {
        return status;
    }

    private void requireDraft() {
        if (status != OrderStatus.DRAFT) {
            throw new IllegalStateException("Only a draft order can be changed");
        }
    }
}
```

Class `Order` kiểm soát cách trạng thái thay đổi. Người gọi không thể lấy danh sách nội bộ rồi tự thêm dòng hàng hoặc thay đổi trạng thái tùy ý. `addLine()` và `submit()` kiểm tra trạng thái trước khi thực hiện; `lines()` trả về bản sao không thể sửa đổi của danh sách. Các quy tắc này giúp đối tượng duy trì invariant của chính nó.

Ví dụ chỉ minh họa một vòng đời đơn hàng tối giản. Ứng dụng thực tế cần xác định các chuyển đổi hợp lệ theo nghiệp vụ như hủy đơn đã gửi, thanh toán, hoàn tất hoặc hoàn tiền. Điều quan trọng là các chuyển đổi đó được biểu diễn qua hành vi có kiểm soát, thay vì cho phép mã bên ngoài sửa từng field độc lập.

## 3. So sánh theo ý nghĩa mô hình

| Tiêu chí | `record` | `class` đại diện thực thể có vòng đời |
|---|---|---|
| Ý nghĩa chính | Một giá trị được mô tả bởi các component | Một đối tượng có identity và trạng thái cần quản lý |
| Equality mặc định | Theo giá trị các component | `Object.equals()` dùng identity tham chiếu nếu không override |
| Dữ liệu | Component field là `private final` | Tự quyết định field nào bất biến hoặc thay đổi |
| Thay đổi | Không thể gán lại component sau khi khởi tạo | Có thể cung cấp thao tác chuyển trạng thái có kiểm soát |
| Bất biến nghiệp vụ | Có thể kiểm tra trong constructor và phương thức | Có thể bảo vệ xuyên suốt các thao tác của đối tượng |
| Kế thừa | Record là `final`, không thể kế thừa class khác; có thể implement interface | Có thể kế thừa class hoặc implement interface theo thiết kế |
| Ví dụ | `OrderLine`, `Address`, `Money`, snapshot, kết quả truy vấn | `Order`, `Account`, `Subscription`, phiên làm việc |

Bảng mô tả hai lựa chọn phổ biến, không phải giới hạn tuyệt đối. Class có thể là value object bất biến; record có thể có phương thức và quy tắc xác thực. Hãy chọn kiểu diễn đạt đúng ngữ nghĩa và cách sử dụng của dữ liệu trong miền nghiệp vụ.

## 4. Kết hợp record và class trong cùng mô hình

Thông thường không cần chọn một trong hai cho toàn bộ mô hình. Một thực thể có vòng đời có thể chứa các giá trị record bất biến, rồi xuất bản trạng thái hiện tại dưới dạng snapshot record.

```java
import java.time.Instant;
import java.util.List;
import java.util.UUID;

record OrderSnapshot(
        UUID id,
        OrderStatus status,
        List<OrderLine> lines,
        Instant createdAt,
        Instant submittedAt) {

    OrderSnapshot {
        lines = List.copyOf(lines);
    }
}
```

Trong class `Order`, có thể thêm phương thức tạo snapshot:

```java
OrderSnapshot snapshot() {
    return new OrderSnapshot(
            id, status, lines, createdAt, submittedAt);
}
```

`Order` chịu trách nhiệm thay đổi trạng thái theo nghiệp vụ. `OrderLine` biểu diễn từng dòng hàng như một giá trị. `OrderSnapshot` là ảnh chụp dữ liệu tại một thời điểm để trả về cho tầng đọc, ghi log hoặc gửi sang thành phần khác. Cách chia này giữ cho đối tượng quản lý vòng đời không bị biến thành một cấu trúc dữ liệu có thể bị sửa tùy tiện.

## 5. Chú ý về tính bất biến của record

Các component field của record là `final`, nhưng điều đó chỉ ngăn việc gán lại tham chiếu. Nó không tự làm cho đối tượng được tham chiếu trở nên bất biến.

```java
import java.util.List;

record UnsafeSnapshot(List<String> tags) {}
```

Đoạn khai báo trên không ngăn người tạo record sửa list ban đầu sau khi truyền vào, nếu list đó có thể thay đổi. Cũng không ngăn người nhận gọi `tags().add(...)` nếu component trỏ đến một list mutable.

Có thể tạo bản sao không thể sửa đổi của collection ngay trong constructor:

```java
record SafeSnapshot(List<String> tags) {
    SafeSnapshot {
        tags = List.copyOf(tags);
    }
}
```

`List.copyOf()` tạo collection không thể sửa đổi và từ chối phần tử `null`. Đây là bản sao nông: nếu phần tử bên trong là object mutable, trạng thái của các object đó vẫn có thể thay đổi. Muốn snapshot bất biến thực sự, các phần tử cũng cần bất biến hoặc phải được sao chép theo chính sách phù hợp.

Equality do record sinh ra cũng không tự động thực hiện so sánh sâu cho mọi cấu trúc. Chẳng hạn, array dùng equality mặc định theo identity của array. Với component mutable hoặc có quy tắc so sánh đặc biệt, hãy cân nhắc chuyển sang kiểu giá trị bất biến phù hợp hoặc tự định nghĩa chính sách equality một cách rõ ràng.

## 6. Chọn kiểu nào cho một yêu cầu cụ thể?

Có thể dùng các câu hỏi sau để đưa ra quyết định:

1. **Hai đối tượng có cùng dữ liệu có được xem là cùng một giá trị không?** Nếu có, record thường phù hợp. Nếu mỗi đối tượng có danh tính riêng dù dữ liệu hiện tại giống nhau, hãy xem xét class và xác định equality theo identity hoặc mã định danh nghiệp vụ.
2. **Đối tượng có thay đổi qua nhiều bước nghiệp vụ không?** Nếu có, class giúp đóng gói các thao tác và kiểm soát thứ tự chuyển trạng thái.
3. **Các thành phần có thể bất biến sau khi tạo không?** Nếu có, record là lựa chọn gọn và thể hiện rõ hợp đồng dữ liệu. Nếu trạng thái phải thay đổi, class thường phù hợp hơn.
4. **Quy tắc hợp lệ chỉ cần kiểm tra lúc tạo hay phải bảo vệ trong suốt vòng đời?** Record có thể kiểm tra điều kiện lúc khởi tạo; class có thể bảo vệ invariant qua mọi phương thức làm thay đổi trạng thái.
5. **Dữ liệu được chia sẻ ra bên ngoài theo cách nào?** Record thuận tiện cho dữ liệu đầu vào/đầu ra và snapshot, nhưng vẫn cần kiểm tra tính bất biến sâu và hợp đồng của framework serialization hoặc persistence đang sử dụng.

| Nhu cầu | Hướng thiết kế thường phù hợp |
|---|---|
| Giá trị địa chỉ gồm đường, thành phố, mã bưu chính | Record |
| Dòng hàng gồm mã sản phẩm, số lượng, đơn giá | Record |
| Yêu cầu tạo đơn hàng gửi qua API | Record làm request model nếu hợp đồng API phù hợp |
| Đơn hàng cần thêm dòng, gửi, hủy theo quy tắc | Class |
| Snapshot đơn hàng để hiển thị hoặc phát sự kiện | Record |
| Tài khoản có số dư và các giao dịch làm thay đổi số dư | Class |

## 7. Phân biệt vòng đời nghiệp vụ với vòng đời bộ nhớ

“Vòng đời” trong thiết kế mô hình ở đây là vòng đời nghiệp vụ: ví dụ đơn hàng đi từ `DRAFT` sang `SUBMITTED`, rồi có thể sang `CANCELLED`. Đây là các trạng thái mà ứng dụng chủ động quản lý.

Vòng đời bộ nhớ là chuyện khác. Cả record lẫn class đều là object Java và đều được quản lý bộ nhớ bởi JVM. Dùng record không làm object tự tồn tại lâu hơn, được giải phóng sớm hơn hoặc có cơ chế garbage collection riêng. Việc một object còn được tham chiếu hay không không quyết định trạng thái nghiệp vụ của nó.

## 8. Kết luận thiết kế

Ưu tiên record khi muốn khai báo một giá trị dữ liệu có cấu trúc rõ, equality theo component và trạng thái không cần thay đổi sau khi tạo. Ưu tiên class khi đối tượng có identity, trạng thái thay đổi, quy tắc chuyển trạng thái hoặc trách nhiệm duy trì invariant trong suốt vòng đời.

Đừng loại bỏ hành vi khỏi record một cách máy móc: xác thực và phép tính gắn với chính giá trị vẫn có thể đặt trong record. Cũng đừng chọn class chỉ vì nghĩ rằng class mới có thể bất biến. Ranh giới tốt nằm ở ngữ nghĩa của đối tượng và quyền kiểm soát trạng thái mà thiết kế cần cung cấp.

## 9. Tài liệu tham khảo

- [Java Language Specification — Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html)
- [Java Language Specification — Records](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10)
- [Java SE 21 API — java.lang.Record](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Record.html)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [Oracle — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html)
