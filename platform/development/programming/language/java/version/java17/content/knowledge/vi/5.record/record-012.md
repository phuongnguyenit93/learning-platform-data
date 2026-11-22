# Chọn `record` hay `class` cho DTO và mô hình miền trong Java 17

Java 17 cho phép khai báo một kiểu mang dữ liệu bằng `record` thay vì viết `class` cùng constructor, các trường `final`, accessor, `equals`, `hashCode` và `toString` thủ công. Nhưng sự ngắn gọn về cú pháp **không phải tiêu chí đủ** để chuyển tất cả class thành record.

Khi thiết kế ứng dụng, cần trả lời trước: đối tượng này **đại diện cho một giá trị**, **một thông điệp truyền dữ liệu**, hay **một thực thể có danh tính và vòng đời riêng**? Đối tượng có cần thay đổi trạng thái theo các thao tác nghiệp vụ không? Có cần kế thừa class hoặc đáp ứng hợp đồng của framework không?

Một cách phân chia thường hiệu quả:

- Dùng **record** cho DTO đơn giản, kết quả tính toán, thông điệp và *value object* có thành phần xác định, đặc biệt khi tính bằng nhau dựa trên dữ liệu.
- Dùng **class** cho entity và aggregate có danh tính ổn định, vòng đời, trạng thái thay đổi hoặc yêu cầu cài đặt/phân tầng mà record không đáp ứng.
- Dùng **immutable class** nếu cần bất biến nhưng phải kiểm soát cấu trúc, cách biểu diễn hoặc hợp đồng `equals` khác với đặc tính record.

Đây là **hướng chọn thiết kế**, không phải quy tắc bắt buộc. Một domain entity bất biến cũng có thể là class; một record có thể chứa hành vi nghiệp vụ và kiểm tra invariant. Đừng đánh đồng “DTO = record” hay “domain = class”.

## 1. Record thực sự có những đặc tính gì ở Java 17?

`record` đã là tính năng chính thức từ Java 16, vì vậy sử dụng ổn định trên Java 17, không cần `--enable-preview`.

Ví dụ:

```java
public record UserSummary(long id, String displayName) {}
```

Khai báo này mô tả hai **record component**: `id` và `displayName`. Trình biên dịch tự cung cấp:

- Các trường tương ứng được lưu dưới dạng `private final`.
- **Canonical constructor** nhận `long id` và `String displayName`.
- Accessor `id()` và `displayName()`; đây không phải getter theo quy ước `getId()`.
- `equals(Object)` và `hashCode()` dựa trên tất cả component.
- `toString()` biểu diễn tên record và các component.

Cách dùng:

```java
UserSummary first = new UserSummary(42, "Lan");
UserSummary second = new UserSummary(42, "Lan");

System.out.println(first.id());           // 42
System.out.println(first.displayName());  // Lan
System.out.println(first.equals(second)); // true
System.out.println(first);                // UserSummary[id=42, displayName=Lan]
```

Khác với class thông thường, record có một số ràng buộc thiết kế:

| Thuộc tính | `record` trong Java 17 | `class` thông thường |
| --- | --- | --- |
| Khai báo dữ liệu | Danh sách component trong phần đầu record là trạng thái được công bố | Có thể tự chọn trường, API và phần biểu diễn nội bộ |
| Kế thừa class khác | Không; record ngầm định `final`, kế thừa `java.lang.Record` | Có thể kế thừa class nếu hợp đồng cho phép |
| Triển khai interface | Có, kể cả `sealed interface` nếu được cấp phép | Có |
| Trường instance bổ sung | Không được khai báo trường instance ngoài các component | Có thể thêm trường, cache hoặc trạng thái nội bộ |
| Thay giá trị component | Không có setter tự sinh; trường là `final` | Có thể bất biến hoặc mutable tùy thiết kế |
| `equals` / `hashCode` mặc định | Dựa trên các component | Mặc định từ `Object` là theo identity, trừ khi override |
| Constructor | Có canonical constructor, compact constructor và các constructor phụ hợp lệ | Tự chọn constructor, factory và quy tắc khởi tạo |
| Cấu trúc biểu diễn | Trở thành phần đáng chú ý trong hợp đồng công khai | Có thể ẩn, đổi hoặc tái cấu trúc linh hoạt hơn |

Record vẫn là **class** trong hệ kiểu Java. Record có thể định nghĩa phương thức, triển khai interface, có static member, khai báo generic, kiểm tra dữ liệu và triển khai hành vi. Nó không chỉ là “struct chứa field”.

### Compact constructor giúp bảo vệ dữ liệu

Record có thể kiểm tra và chuẩn hóa component trong compact constructor:

```java
import java.util.Locale;
import java.util.Objects;

public record ProductCode(String value) {
    public ProductCode {
        value = Objects.requireNonNull(value, "value")
                .strip()
                .toUpperCase(Locale.ROOT);
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Product code must not be blank");
        }
    }
}
```

Trong compact constructor, ta chỉnh **tham số** `value`; sau khi code kiểm tra chạy, Java tự gán tham số cuối cùng vào trường record. Quy tắc chuyển chữ hoa chỉ phù hợp nếu **miền nghiệp vụ quy định mã sản phẩm không phân biệt hoa/thường**. Không chuẩn hóa dữ liệu tùy tiện nếu việc viết hoa có ý nghĩa trong miền.

Khi một giá trị vi phạm quy tắc không thể tồn tại ở bất kỳ ngữ cảnh nào, kiểm tra ngay trong constructor/factory giúp mọi nơi khởi tạo đều nhận cùng bất biến. Tuy nhiên, các điều kiện phụ thuộc cơ sở dữ liệu, quyền người dùng hoặc trạng thái của aggregate thường thuộc service/aggregate, không nên nhét tất cả vào constructor của record.

## 2. DTO: vì sao record thường hợp?

**DTO (Data Transfer Object)** chuyên mang dữ liệu giữa các tầng hoặc qua một ranh giới: kết quả HTTP API, message, kết quả truy vấn, thông tin trả về từ service hoặc dữ liệu nhập vào use case.

Một DTO thường có cấu trúc xác định, không cần setter và được tạo rồi đọc. Record phù hợp vì định nghĩa cấu trúc rõ ràng, ít mã lặp và dễ theo dõi giá trị.

### DTO đầu ra

```java
import java.util.List;
import java.util.Objects;

public record OrderResponse(
        String orderId,
        String status,
        List<LineResponse> lines,
        long totalCents) {

    public OrderResponse {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(status, "status");
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
        if (totalCents < 0) {
            throw new IllegalArgumentException("totalCents must not be negative");
        }
    }
}

record LineResponse(String productCode, int quantity, long unitPriceCents) {}
```

`OrderResponse` thể hiện chính xác các trường trả về của một endpoint, còn `LineResponse` mô tả dữ liệu của từng dòng. Các component có accessor cùng tên, ví dụ `response.orderId()` và `response.lines()`.

`List.copyOf` bảo vệ danh sách khỏi việc bị caller sửa gián tiếp qua chính danh sách gốc; danh sách được giữ trong record cũng không cho phép sửa bằng `add` hoặc `clear`. Nhưng đây là **bất biến nông**: nếu phần tử có trạng thái mutable, việc sửa phần tử vẫn có thể làm thay đổi nội dung quan sát được. Ở ví dụ trên, `LineResponse` chỉ chứa `String` và kiểu nguyên thủy nên không có vấn đề đó.

### DTO đầu vào

Ví dụ yêu cầu tạo một dòng đơn hàng:

```java
public record AddLineRequest(String productCode, Integer quantity) {}
```

DTO đầu vào thường mô tả những gì **caller đã gửi**, kể cả dữ liệu còn thiếu hoặc chưa hợp lệ. Chọn `Integer` thay vì `int` có thể giúp đại diện trường `quantity` vắng mặt dưới dạng `null`; tuy nhiên, hành vi phân biệt vắng mặt, JSON `null` và giá trị mặc định còn phụ thuộc thư viện deserialize và cấu hình mapping.

Ở tầng chuyển đổi sang miền:

```java
static OrderLine toDomain(AddLineRequest request) {
    Objects.requireNonNull(request, "request");
    if (request.quantity() == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    return new OrderLine(
            new ProductCode(request.productCode()),
            request.quantity());
}
```

Đoạn chuyển đổi giả định các kiểu `OrderLine` và `ProductCode` đã được định nghĩa trong mô hình miền, đồng thời đã import `java.util.Objects`. `OrderLine` phải tự kiểm tra số lượng dương. Như vậy:

1. **DTO** nhận cấu trúc dữ liệu đến từ ranh giới.
2. **Parser/validator** kiểm tra kiểu, trường bắt buộc, định dạng và các lỗi cần báo cho caller.
3. **Value object** của miền kiểm tra những bất biến luôn phải đúng.
4. **Aggregate/service** kiểm tra các điều kiện phụ thuộc trạng thái hoặc ngữ cảnh nghiệp vụ.

Nếu yêu cầu API phải nhận các bản cập nhật từng phần, một DTO record có thể vẫn phù hợp, nhưng cần thiết kế kỹ để phân biệt “không gửi trường” với “gửi `null` nhằm xóa giá trị”. Record component đơn thuần thường **không đủ** để biểu đạt ba trạng thái *absent*, *explicit null* và *value*; có thể cần kiểu bao, mô hình patch riêng hoặc cơ chế deserialize chuyên biệt.

### Record không tự tạo hợp đồng JSON hay validation

Java language chỉ định cấu trúc record và các phương thức, **không quy định JSON**. Thư viện như Jackson có thể serialize/deserialize record ở các phiên bản hỗ trợ, nhưng tên trường, alias, null handling, constructor binding, polymorphism và annotation phụ thuộc **thư viện cùng cấu hình thực tế**.

Tương tự, annotation Bean Validation (`@NotNull`, `@Size`, `@Positive`...) có thể được gắn vào DTO nếu dự án dùng validation framework hỗ trợ, nhưng gắn annotation **không có nghĩa** mọi lệnh `new SomeRecord(...)` tự động gọi bộ xác thực. Khi dữ liệu là invariant cốt lõi của miền, constructor/factory vẫn cần bảo vệ nó hoặc phải có cơ chế xây dựng object có kiểm soát tương đương.

## 3. Mô hình miền: tách *value object* khỏi entity/aggregate

Trong Domain-Driven Design, hai nhóm đối tượng thường có ý nghĩa rất khác:

- **Value object**: nhận diện bằng **giá trị**. Hai giá trị có các thuộc tính giống nhau được xem là tương đương theo quy tắc miền. Ví dụ mã sản phẩm, khoảng ngày, tọa độ, một số loại số tiền, trạng thái bất biến.
- **Entity**: có **danh tính ổn định** xuyên suốt các thay đổi. Hai đơn hàng có cùng nội dung vẫn là hai đơn hàng khác nhau nếu có mã định danh khác nhau. Aggregate quản lý các thao tác và bất biến liên quan nhiều đối tượng trong phạm vi của nó.

Vì `record` sinh `equals`/`hashCode` theo **toàn bộ component**, nó thường là ứng viên tốt cho value object; entity có danh tính và vòng đời thường rõ ràng hơn khi dùng class.

| Tình huống miền | Lựa chọn gợi ý | Lý do |
| --- | --- | --- |
| `ProductCode("P-17")` | `record` | Dữ liệu nhỏ, giá trị xác định, có thể chuẩn hóa và kiểm tra |
| Một tọa độ hoặc cấu hình đọc | `record` | Các component tạo nên giá trị; thay đổi thường tạo giá trị mới |
| Kết quả `Success` / `Failure` của nghiệp vụ | `record` cùng `sealed interface` khi phù hợp | Mỗi biến thể mang các component khác nhau, có thể xử lý theo kiểu |
| Đơn hàng có ID và trạng thái chuyển từ nháp sang đã gửi | `class` | Có danh tính, vòng đời và hành vi thay đổi trạng thái |
| Tài khoản có số dư, quy tắc ghi nợ, ghi có | `class` hoặc aggregate phù hợp | Các phép thay đổi cần được kiểm soát theo nghiệp vụ, giao dịch và tính đồng thời |
| Đối tượng vừa bất biến vừa cần ẩn biểu diễn nội bộ hoặc hỗ trợ inheritance | `class` | Record công bố các component và ngầm định `final` |

### Value object bằng record

```java
import java.util.Currency;
import java.util.Objects;

public record Money(long minorUnits, Currency currency) {
    public Money {
        Objects.requireNonNull(currency, "currency");
    }

    public Money plus(Money other) {
        Objects.requireNonNull(other, "other");
        if (!currency.equals(other.currency())) {
            throw new IllegalArgumentException("Currency mismatch");
        }
        return new Money(Math.addExact(minorUnits, other.minorUnits()), currency);
    }
}
```

`Money` không đổi giá trị hiện tại khi cộng: `plus` trả về **một Money mới**. `Math.addExact` phát hiện tràn số nguyên; phép cộng chỉ cho phép hai số tiền cùng đơn vị tiền tệ. `minorUnits` là đơn vị nhỏ nhất theo mô hình đã chọn, ví dụ cent ở một số loại tiền; hệ thống thực tế cần xác định rõ quy tắc đơn vị và làm tròn theo từng loại tiền, không tự giả định mọi loại tiền đều có hai chữ số thập phân. Việc cho phép số âm hay số dương thuộc bất biến cụ thể của miền (giá trị điều chỉnh, hoàn tiền, khoản phải thu...).

Điểm quan trọng: value object **có hành vi nghiệp vụ**. Không cần đổi nó thành class chỉ vì có phương thức `plus`, `overlaps`, `contains` hoặc `isValidFor`; record vẫn có thể mô tả một giá trị với các phép toán có ý nghĩa.

### Entity/aggregate bằng class

Giả sử đơn hàng cần:

- Mã định danh không đổi trong suốt vòng đời.
- Chỉ thêm dòng hàng khi còn ở trạng thái nháp.
- Chỉ nộp đơn khi đã có ít nhất một dòng.
- Chỉ cung cấp **snapshot** cho bên ngoài, không lộ danh sách nội bộ để caller tùy tiện sửa.

Một class có trường riêng tư và các phương thức nghiệp vụ diễn đạt mô hình này rõ hơn một record với các component public accessor. Mô hình có thể dùng **class cho aggregate**, **record cho value object nội bộ** và **record cho DTO đầu ra** cùng lúc; không cần ép tất cả về cùng một dạng.

## 4. Ví dụ hoàn chỉnh: record cho DTO và value object, class cho đơn hàng

Ví dụ dưới đây dùng các tính năng đã chính thức trên Java 17, không cần thư viện bên ngoài. Lưu thành `RecordClassChoiceDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.UUID;

public class RecordClassChoiceDemo {

    // DTO đầu vào: giữ dữ liệu đến từ caller, có thể thiếu quantity.
    public record AddLineRequest(String productCode, Integer quantity) {}

    // Value object: bất biến giá trị luôn được kiểm tra khi khởi tạo.
    public record ProductCode(String value) {
        public ProductCode {
            value = Objects.requireNonNull(value, "value")
                    .strip()
                    .toUpperCase(Locale.ROOT);
            if (value.isEmpty()) {
                throw new IllegalArgumentException("productCode must not be blank");
            }
        }
    }

    // DTO đầu ra: chỉ mang dữ liệu cần trả về bên ngoài.
    public record LineView(String productCode, int quantity, long unitPriceCents) {}

    public record OrderView(
            String orderId,
            String status,
            List<LineView> lines,
            long totalCents) {

        public OrderView {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(status, "status");
            lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
            if (totalCents < 0) {
                throw new IllegalArgumentException("totalCents must not be negative");
            }
        }
    }

    // Aggregate: có danh tính và thay đổi trạng thái theo hành vi nghiệp vụ.
    public static final class Order {
        private enum Status { DRAFT, SUBMITTED }

        private record OrderLine(
                ProductCode productCode,
                int quantity,
                long unitPriceCents) {

            private OrderLine {
                Objects.requireNonNull(productCode, "productCode");
                if (quantity <= 0) {
                    throw new IllegalArgumentException("quantity must be positive");
                }
                if (unitPriceCents < 0) {
                    throw new IllegalArgumentException("price must not be negative");
                }
            }
        }

        private final UUID id;
        private final List<OrderLine> lines = new ArrayList<>();
        private Status status = Status.DRAFT;

        public Order(UUID id) {
            this.id = Objects.requireNonNull(id, "id");
        }

        public void addLine(ProductCode code, int quantity, long unitPriceCents) {
            if (status != Status.DRAFT) {
                throw new IllegalStateException("Cannot add lines after submission");
            }
            lines.add(new OrderLine(code, quantity, unitPriceCents));
        }

        public void submit() {
            if (status != Status.DRAFT) {
                throw new IllegalStateException("Order was already submitted");
            }
            if (lines.isEmpty()) {
                throw new IllegalStateException("Cannot submit an empty order");
            }
            status = Status.SUBMITTED;
        }

        public OrderView snapshot() {
            List<LineView> views = new ArrayList<>();
            long total = 0;

            for (OrderLine line : lines) {
                total = Math.addExact(total,
                        Math.multiplyExact(line.quantity(), line.unitPriceCents()));
                views.add(new LineView(
                        line.productCode().value(),
                        line.quantity(),
                        line.unitPriceCents()));
            }

            return new OrderView(
                    id.toString(), status.name(), views, total);
        }
    }

    public static void main(String[] args) {
        AddLineRequest request = new AddLineRequest(" p-17 ", 2);
        if (request.quantity() == null) {
            throw new IllegalArgumentException("quantity is required");
        }

        Order order = new Order(
                UUID.fromString("00000000-0000-0000-0000-000000000017"));
        order.addLine(new ProductCode(request.productCode()),
                request.quantity(), 1_250);

        System.out.println(order.snapshot().status());
        order.submit();

        OrderView response = order.snapshot();
        System.out.println(response.status());
        System.out.println(response.totalCents());
        System.out.println(response.lines().get(0).productCode());
    }
}
```

Chạy bằng JDK 17:

```bash
javac --release 17 RecordClassChoiceDemo.java
java RecordClassChoiceDemo
```

Kết quả mong đợi:

```text
DRAFT
SUBMITTED
2500
P-17
```

Trong ví dụ:

1. `AddLineRequest` nhận dữ liệu đầu vào, **chưa tuyên bố** mọi tổ hợp đầu vào đều là giá trị miền hợp lệ.
2. `ProductCode` là value object: cùng mã được chuẩn hóa thì bằng nhau theo giá trị.
3. `OrderLine` là record nội bộ, từ chối số lượng không dương và giá âm.
4. `Order` là class có ID và các phương thức `addLine`/`submit`. Caller không thể sửa trạng thái bằng setter hoặc truy cập trực tiếp danh sách `lines`.
5. `OrderView` và `LineView` là các snapshot/DTO. Sau khi tạo `OrderView`, cập nhật `Order` không làm thay đổi snapshot cũ. Danh sách trong `OrderView` được sao chép phòng vệ.

Đây là ví dụ một aggregate hoạt động trong bộ nhớ, chưa xử lý giao dịch hoặc truy cập đồng thời; ứng dụng thực tế có thể cần transaction và optimistic locking khi nhiều tiến trình cùng sửa một đơn hàng. Điểm thiết kế đáng chú ý là mỗi kiểu giữ đúng **trách nhiệm của nó**, không phải một lựa chọn record/class áp dụng cho toàn bộ dự án.

## 5. Record không đồng nghĩa bất biến sâu

Một record không có setter tự sinh và các trường component là `final`. Nhưng **tham chiếu cuối cùng** không có nghĩa **đối tượng được tham chiếu không đổi**:

```java
import java.util.ArrayList;
import java.util.List;

record UnsafeTags(List<String> values) {}

List<String> original = new ArrayList<>(List.of("java"));
UnsafeTags tags = new UnsafeTags(original);
original.add("changed");

System.out.println(tags.values()); // [java, changed]
```

Để giữ dữ liệu của một DTO/value object không bị sửa qua danh sách gốc:

```java
import java.util.List;
import java.util.Objects;

record Tags(List<String> values) {
    public Tags {
        values = List.copyOf(Objects.requireNonNull(values, "values"));
    }
}
```

`List.copyOf` tạo danh sách không cho chỉnh sửa và từ chối phần tử `null`. Tuy nhiên, khi phần tử là kiểu có thể thay đổi như `List<MutableAddress>`, vẫn có khả năng sửa object trong danh sách. Muốn bất biến sâu cần chọn kiểu phần tử bất biến hoặc sao chép phù hợp, kể cả những cấu trúc lồng nhau.

### Chú ý đặc biệt với mảng

```java
record Bytes(byte[] data) {}
```

`Bytes` không tự sao chép mảng. Caller có thể sửa mảng sau khi tạo record, và accessor `data()` trả lại tham chiếu mảng. Bên cạnh đó, `equals` được sinh cho component kiểu mảng sẽ so sánh **tham chiếu của mảng**, không so sánh sâu từng byte. Với kiểu biểu diễn bằng mảng, cần tự thiết kế cơ chế sao chép và equality thích hợp hoặc thay bằng một kiểu giá trị bất biến khác; **record không tự giải quyết các việc này**.

## 6. Bình đẳng theo giá trị và bình đẳng theo danh tính

Hai record cùng loại, có các component tương đương thường được xem là bằng nhau theo hợp đồng `equals` được sinh:

```java
record Point(int x, int y) {}

Point a = new Point(3, 5);
Point b = new Point(3, 5);
System.out.println(a.equals(b)); // true
```

Nếu mô hình đơn hàng là `record Order(long id, String status, long total)`, một thay đổi `status` hoặc `total` tạo ra record mới **không bằng** bản cũ, dù hai giá trị vẫn nói về cùng một đơn hàng có ID 123. Điều này có thể mâu thuẫn với cách entity định nghĩa **đồng nhất theo ID**. Với entity, cần xác định chủ động hợp đồng equality/identity, đặc biệt khi dùng ORM, proxy và ID được cấp sau khi lưu.

Ngược lại, không phải class nào cũng mang identity: một `final class Color` bất biến có thể chủ động override `equals`/`hashCode` theo giá trị và vẫn đúng. Chọn kiểu dựa trên **ngữ nghĩa miền** rồi mới xét cú pháp.

### Khi nào không nên dùng equality do record sinh?

- Chỉ một phần component có ý nghĩa với equality, trong khi các component khác là dữ liệu bổ trợ.
- Một component là mảng cần so sánh nội dung.
- Một giá trị cần chuẩn hóa trước khi so sánh, như mã không phân biệt hoa/thường.
- Đối tượng có identity cố định dù trạng thái thay đổi.

Record có thể tự khai báo `equals` và `hashCode` khi cần, nhưng nếu phải thay đổi sâu hợp đồng dữ liệu và equality mặc định, hãy cân nhắc liệu **immutable class** có biểu đạt mô hình rõ hơn không. Khi dùng record làm khóa trong `HashMap`/`HashSet`, các component và equality phải ổn định theo thời gian; không nên giữ tham chiếu mutable khiến giá trị quan sát được thay đổi.

## 7. Cấu trúc công khai của record ảnh hưởng tới khả năng tiến hóa API

Khi viết:

```java
public record CustomerView(String name, String email) {}
```

hai component là một phần rõ ràng của API: caller có thể sử dụng canonical constructor `new CustomerView(name, email)` và accessor `name()`, `email()`. Nếu sau đó đổi thành:

```java
public record CustomerView(String name, String email, String phone) {}
```

constructor hai tham số cũ không còn được record tự sinh. Các caller Java có thể cần sửa mã hoặc nhà phát triển phải tạo thêm constructor phụ tương thích:

```java
public record CustomerView(String name, String email, String phone) {
    public CustomerView(String name, String email) {
        this(name, email, null);
    }
}
```

Constructor phụ của record phải ủy quyền tới constructor canonical theo quy định của Java. Việc thêm component còn thay đổi hợp đồng `equals`, `hashCode`, `toString`, thành phần phản chiếu qua reflection và có thể ảnh hưởng đến serialization/binding trong framework.

Class thông thường có thể dễ dàng hơn khi cần **ẩn trường nội bộ**, giữ constructor/factory cũ và thay đổi biểu diễn mà không tác động toàn bộ API. Dù vậy, bất cứ sự thay đổi nào trong DTO gửi qua HTTP/JSON/message cũng cần xem xét **tương thích với consumer**, không chỉ khả năng biên dịch của Java; việc thêm trường JSON có thể chấp nhận được với một số client nhưng gây lỗi với client yêu cầu schema nghiêm ngặt.

Gợi ý: DTO cho API ổn định nên có chiến lược version/schema rõ ràng, và mapper nên tách domain model khỏi representation công khai khi nhu cầu phát triển của hai phía khác nhau.

## 8. Yêu cầu framework có thể quyết định việc dùng class

### REST và thư viện JSON

Các record phù hợp cho request/response DTO khi framework hỗ trợ Java records và đã được cấu hình tương ứng. Trước khi áp dụng trong dự án hiện có, cần kiểm tra **phiên bản thư viện serialization thực tế**, cách mapping constructor/component, annotation, null handling và polymorphic type handling. Không nên giả định thư viện nào cũng hỗ trợ record như nhau chỉ vì chương trình chạy trên JDK 17.

Đặc biệt, record dùng làm **response** thường ít ràng buộc hơn record dùng làm **request patch**: response thể hiện một snapshot hoàn chỉnh; patch thường cần biểu diễn các mức độ hiện diện của trường.

### JPA/Hibernate và entity lưu trữ

JPA entity thông thường cần hợp đồng về constructor, danh tính, vòng đời và quản lý trạng thái; nhiều cách sử dụng còn dựa vào proxy, lazy loading hoặc cơ chế dirty checking. Record là `final`, không có constructor không đối số do record tự sinh và chỉ có trường component `final`, nên **không phải lựa chọn entity JPA thông thường, có tính di động tốt**.

Với JPA entity, class thường tự nhiên hơn:

```java
// Phác họa cấu trúc entity, không phải ví dụ chạy độc lập.
@Entity
public class OrderEntity {
    @Id
    private Long id;

    private String status;

    protected OrderEntity() {
        // Constructor cho persistence provider.
    }

    // Các thao tác và ánh xạ theo hợp đồng của ứng dụng.
}
```

Các annotation trong đoạn này thuộc JPA API mà dự án đã chọn; ví dụ chỉ minh họa cách entity class đáp ứng constructor cho provider. **Domain entity** và **persistence entity** không nhất thiết là cùng một class: trong kiến trúc có tách tầng, repository có thể chuyển từ entity JPA sang mô hình miền với các quy tắc riêng.

Một số provider và phiên bản framework hỗ trợ record cho projection DTO, constructor result hoặc những trường hợp giá trị đặc biệt; khả năng đó **không đồng nghĩa** mọi record đều có thể thay thế entity JPA. Khi dùng `@Embeddable`, projection hoặc các tính năng đặc thù, cần xét tài liệu của phiên bản provider thực tế.

### JavaBeans và thư viện dựa vào getter/setter

Một số thư viện, bộ tạo form hoặc mapper cũ dựa trên quy ước JavaBeans `getName()`, `setName()` và constructor không tham số. Accessor tự sinh của record là `name()`, không phải `getName()`; vì thế cần kiểm tra thư viện có hỗ trợ record component/canonical constructor không. Không nên thêm các setter giả vào record hoặc đổi toàn bộ mô hình chỉ để phù hợp một thư viện vốn có thể được cấu hình bằng mapper phù hợp.

## 9. Record không phải một cách tối ưu hiệu năng mặc định

Cả record lẫn class đều là kiểu tham chiếu trong Java 17 và được tạo dưới dạng object như các kiểu class thông thường. **Record không mặc nhiên được cấp phát trên stack, không tự có kích thước nhỏ hơn, không tự tránh cấp phát hay tự có thời gian truy cập nhanh hơn class tương đương**.

Lợi ích chính của record là **hợp đồng dữ liệu rõ, mã khai báo ngắn và các phương thức chuẩn sinh đồng nhất**. Nếu tối ưu bộ nhớ hoặc hiệu năng là yêu cầu quan trọng, cần đo đạc với workload thực tế và JVM đang dùng; không chọn record chỉ vì giả định nó nhanh hơn.

Tương tự, record không đồng nghĩa với *value type* cấp JVM. Những tính năng ngôn ngữ/JVM đang được phát triển ở các phiên bản khác không được suy diễn thành đặc tính sẵn có trong Java 17.

## 10. Dùng record với `sealed` cho kết quả nghiệp vụ nhiều biến thể

Một trường hợp đáng cân nhắc là dùng **sealed interface** cho tập kết quả có thể có, và record cho dữ liệu của từng biến thể:

```java
import java.util.Objects;

sealed interface PaymentResult permits Paid, Declined {}

record Paid(String transactionId) implements PaymentResult {
    Paid {
        transactionId = Objects.requireNonNull(transactionId, "transactionId").strip();
        if (transactionId.isEmpty()) {
            throw new IllegalArgumentException("transactionId is required");
        }
    }
}

record Declined(String reason) implements PaymentResult {
    Declined {
        reason = Objects.requireNonNull(reason, "reason").strip();
        if (reason.isEmpty()) {
            throw new IllegalArgumentException("reason is required");
        }
    }
}
```

Ở đây `sealed` kiểm soát những biến thể trực tiếp được phép triển khai `PaymentResult`, còn constructor record kiểm tra **giá trị** của từng biến thể. Nếu cần logic thay đổi của một khoản thanh toán đang xử lý (id, retries, status transition), một aggregate class khác vẫn có thể quản lý vòng đời đó.

Trên Java 17, pattern matching với `instanceof` có thể xử lý kết quả:

```java
static String describe(PaymentResult result) {
    Objects.requireNonNull(result, "result");
    if (result instanceof Paid paid) {
        return "Paid: " + paid.transactionId();
    }
    if (result instanceof Declined declined) {
        return "Declined: " + declined.reason();
    }
    throw new IllegalStateException("Unhandled result");
}
```

Chuỗi `if/instanceof` **chưa được compiler Java 17 kiểm tra tính exhaustive** theo cây sealed. Khi thêm một kiểu con được cấp phép, phải rà lại các nơi xử lý. Pattern matching cho `switch` và record patterns chỉ chính thức từ Java 21, nên không dùng cú pháp Java 21 trong ví dụ yêu cầu biên dịch Java 17 ổn định.

## 11. Bảo mật dữ liệu và `toString()` sinh tự động

Record sinh `toString()` chứa tên các component và giá trị tương ứng. Điều này tiện trong log và debug đối với dữ liệu không nhạy cảm, nhưng có thể **vô tình đưa thông tin nhạy cảm vào log**:

```java
record LoginRequest(String username, String password) {}

LoginRequest request = new LoginRequest("lan", "secret");
// Không log thẳng request khi có password/token/thông tin nhạy cảm.
```

Khi DTO chứa bí mật hoặc thông tin cá nhân, cần chọn chính sách logging phù hợp: tránh log object toàn phần, chủ động redaction và hạn chế dữ liệu trả về. Có thể override `toString()` nếu cần, nhưng **không chỉ dựa vào `toString()`** để che thông tin trên mọi đường serialization, debug và monitoring.

## 12. Khi một immutable class phù hợp hơn record

Không phải cứ bất biến là record. Ví dụ một kiểu muốn che cách lưu dữ liệu bằng một cache hoặc muốn cung cấp nhiều biểu diễn nhưng chỉ cam kết một tập phương thức:

```java
import java.util.Objects;

public final class NormalizedCode {
    private final String normalized;

    private NormalizedCode(String normalized) {
        this.normalized = normalized;
    }

    public static NormalizedCode of(String raw) {
        String value = Objects.requireNonNull(raw, "raw").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("code must not be blank");
        }
        return new NormalizedCode(value);
    }

    public String asText() {
        return normalized;
    }

    @Override
    public boolean equals(Object other) {
        return this == other || (other instanceof NormalizedCode code
                && normalized.equals(code.normalized));
    }

    @Override
    public int hashCode() {
        return normalized.hashCode();
    }
}
```

Kiểu `NormalizedCode` vẫn là **value object bất biến**, nhưng nó tự quyết định API `of`/`asText`, constructor private và cách biểu diễn. Record có thể có các factory bổ sung, nhưng canonical constructor và các component/accessor của record luôn là một phần cốt lõi trong hợp đồng của nó. Khi muốn **không công bố danh sách component** hoặc khi equality phải độc lập với những trường kỹ thuật bổ sung, class có thể là lựa chọn phù hợp hơn.

Nếu chọn class vì cần bất biến, đừng quên tự thực hiện các trách nhiệm record thường cung cấp: trường `final`, kiểm tra constructor/factory, không để lộ tham chiếu mutable, và `equals`/`hashCode` chính xác khi cần equality theo giá trị.

## 13. Sai lầm thường gặp khi chuyển DTO hoặc domain class thành record

| Sai lầm | Vì sao có vấn đề | Cách xử lý |
| --- | --- | --- |
| Chuyển toàn bộ entity sang record vì ít code hơn | Entity thường có identity, lifecycle, persistence mapping và hành vi cập nhật | Đánh giá entity/aggregate riêng; class thường rõ hơn |
| Coi mọi record tự bất biến sâu | Component kiểu list, array hoặc object mutable vẫn thay đổi được gián tiếp | Copy phòng vệ và chọn component bất biến |
| Chỉ kiểm tra DTO trong controller | Domain object có thể được tạo từ nhiều đường khác | Đặt invariant cốt lõi trong value object/aggregate |
| Dùng record cho API public nhưng thường xuyên đổi component | Canonical constructor và accessor của record là hợp đồng trực tiếp | Tách API DTO khỏi domain; có versioning/mapping khi cần |
| Nghĩ record tự tương thích mọi thư viện JSON/ORM | Khả năng mapping phụ thuộc phiên bản và cấu hình framework | Kiểm tra integration thực tế, dùng class/mapper khi phù hợp |
| Dùng record cho entity có trạng thái đổi liên tục rồi tạo lại ở mọi thao tác | Equality, identity và quản lý lifecycle có thể trở nên khó hiểu | Cân nhắc class aggregate hoặc mô hình state bất biến có kiểm soát |
| Dùng record chứa array làm khóa map | Array mutable và equality mặc định theo tham chiếu | Dùng representation bất biến và equality thích hợp |
| Log DTO record chứa password/token | `toString()` có thể đưa component vào log | Redact và kiểm soát logging/serialization |
| Cho rằng record phải là DTO thuần, không được có phương thức | Record có thể định nghĩa hành vi và invariant | Dùng record cho value object có hành vi phù hợp |
| Cho rằng class không thể bất biến | Class có thể `final`, field `final`, constructor/factory kiểm tra | Dùng immutable class khi cần ẩn biểu diễn |
| Cho rằng record luôn tối ưu CPU/RAM hơn class | Java 17 vẫn cấp phát và quản lý record như object tham chiếu | Chọn vì ngữ nghĩa; benchmark nếu hiệu năng quan trọng |

## 14. Quy trình quyết định trong dự án Java 17

Với một kiểu mới, có thể ra quyết định theo trình tự:

1. **Kiểu đó đại diện cho dữ liệu hay một đối tượng có vòng đời?** Nếu chủ yếu là dữ liệu được tạo rồi đọc, cân nhắc record. Nếu có identity, mutation và state transition, ưu tiên xem xét class.
2. **Hai instance có nên bằng nhau khi component bằng nhau?** Nếu có, record khá tự nhiên. Nếu equality dựa trên ID hoặc hợp đồng khác, thiết kế class/equality có chủ đích.
3. **Dữ liệu có thể thay đổi gián tiếp qua collection/array không?** Nếu có, xây dựng chiến lược sao chép phòng vệ. Record không tự bảo vệ nội dung mutable.
4. **Kiểu này có nằm ở ranh giới API không?** Nếu là DTO, phân biệt request/response; xem schema, null/missing field, validation và sự phát triển phiên bản.
5. **Framework yêu cầu constructor hoặc cơ chế inheritance/proxy không?** Nếu có, kiểm tra khả năng hỗ trợ record cụ thể; JPA entity thường chọn class.
6. **Kiểu có các bất biến nghiệp vụ riêng không?** Dùng constructor/factory để từ chối giá trị không hợp lệ; dùng service/aggregate cho quy tắc theo ngữ cảnh.
7. **Cấu trúc component có phải hợp đồng công khai mong muốn không?** Nếu cần che cách biểu diễn hoặc thay đổi nó độc lập với API, immutable class thường dễ tiến hóa hơn.

### Mẫu lựa chọn nhanh

```text
Kiểu đang thiết kế
        |
        +-- Cần ID/lifecycle/state transition? -- Có --> class entity/aggregate
        |                                            (có thể dùng record nội bộ)
        |
        +-- Chủ yếu truyền dữ liệu qua API? ------ Có --> record DTO nếu
        |                                            framework/schema phù hợp
        |
        +-- Value object có component rõ ràng? -- Có --> record + constructor
        |                                            kiểm tra invariant
        |
        +-- Cần ẩn cấu trúc, kế thừa class,
            hoặc equality/cài đặt đặc biệt? ---- Có --> class (có thể immutable)
```

Mẫu này là công cụ định hướng, không thay thế việc xem xét yêu cầu cụ thể. Một ứng dụng hoàn toàn có thể dùng **record cho DTO đầu vào/đầu ra**, **record cho value object**, **sealed interface cho các kết quả nhiều biến thể**, và **class cho aggregate/entity**. Trên Java 17, cách phân chia này giữ được lợi ích cú pháp ngắn gọn của record mà vẫn bảo toàn ngữ nghĩa, bất biến và vòng đời của mô hình miền.
