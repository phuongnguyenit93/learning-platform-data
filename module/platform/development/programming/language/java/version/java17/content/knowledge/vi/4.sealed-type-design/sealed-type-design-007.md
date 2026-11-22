# Giữ bất biến miền dữ liệu và kiểm tra đầu vào khi thiết kế với `sealed` trong Java 17

Trong một mô hình miền dữ liệu (*domain model*), có những trạng thái và tổ hợp dữ liệu **không bao giờ được phép xuất hiện**. Chẳng hạn, một đơn hàng đã giao không thể trở lại trạng thái nháp; dòng hàng có số lượng phải lớn hơn 0; thời điểm giao hàng không thể sớm hơn thời điểm xác nhận; và một đơn hàng bị hủy không thể đồng thời được coi là đang giao.

Java 17 cung cấp `sealed class` và `sealed interface` để **kiểm soát những kiểu con được phép tồn tại**. Khi kết hợp `sealed` với `record`, constructor có kiểm tra dữ liệu và các phương thức chuyển trạng thái, ta có thể diễn đạt nhiều quy tắc miền dữ liệu ngay trong cấu trúc chương trình. Tuy nhiên, `sealed` **chỉ giới hạn cây kiểu**: nó không tự kiểm tra giá trị các trường, không tự ngăn chuyển trạng thái sai, và không thay thế việc xác thực dữ liệu đi vào hệ thống.

Bài này tập trung vào cách phân chia trách nhiệm giữa **tập biến thể hợp lệ**, **bất biến của từng biến thể**, **bất biến trong vòng đời đối tượng** và **kiểm tra đầu vào ở ranh giới hệ thống**, sử dụng các tính năng đã chính thức trong Java 17.

## 1. Bất biến miền dữ liệu là gì?

**Bất biến (invariant)** là điều kiện phải đúng ở mọi thời điểm đối tượng miền được coi là hợp lệ. Nó khác một điều kiện kiểm tra chỉ áp dụng khi người dùng nhập dữ liệu trên giao diện.

Với một đơn hàng, ta có thể có các quy tắc:

| Quy tắc | Loại bất biến | Nơi phù hợp để bảo vệ |
| --- | --- | --- |
| Trạng thái chỉ thuộc `Draft`, `Confirmed`, `Shipped`, `Cancelled` | Tập kiểu được phép | `sealed interface State` cùng các kiểu con được cấp phép. |
| Dòng hàng có SKU không rỗng và số lượng lớn hơn 0 | Bất biến của giá trị | Constructor `Line`. |
| Danh sách dòng hàng không rỗng, không có SKU trùng | Bất biến của một trạng thái | Constructor của `Draft`, `Confirmed`, `Shipped` hoặc hàm kiểm tra dùng chung. |
| `Shipped.shippedAt` không trước `confirmedAt` | Bất biến liên quan nhiều trường | Constructor `Shipped`. |
| Chỉ `Draft` mới được xác nhận; chỉ `Confirmed` mới được giao | Bất biến của chuyển trạng thái | Phương thức nghiệp vụ trên aggregate `Order`. |
| Không thay đổi dữ liệu bên trong trạng thái sau khi tạo | Bất biến về sở hữu dữ liệu | `record` và sao chép phòng vệ các cấu trúc mutable. |
| Yêu cầu gửi từ API có đúng định dạng, quyền truy cập và ràng buộc nghiệp vụ không | Kiểm tra ở ranh giới và quy tắc theo ngữ cảnh | DTO, application service và domain model, tùy từng loại điều kiện. |

Điểm cần nhớ: **cấu trúc kiểu**, **giá trị** và **chuyển trạng thái** là ba mức kiểm soát khác nhau. Không có một từ khóa Java duy nhất thực hiện tất cả các mức đó.

## 2. `sealed` đóng tập biến thể, không tự bảo đảm dữ liệu hợp lệ

Xem khai báo đơn giản:

```java
sealed interface OrderState permits Draft, Confirmed, Shipped, Cancelled {}

record Draft(String cartId) implements OrderState {}

record Confirmed(String confirmationId) implements OrderState {}

record Shipped(String trackingCode) implements OrderState {}

record Cancelled(String reason) implements OrderState {}
```

Trong cùng phạm vi khai báo hợp lệ, kiểu không được liệt kê trong `permits` không thể trực tiếp triển khai `OrderState`. Ví dụ một kiểu `UnknownState implements OrderState` không được cấp phép sẽ bị trình biên dịch từ chối. Các `record` ở trên ngầm định `final`, vì vậy không thể bị kế thừa để tạo các biến thể mới phía dưới.

Nhưng các khai báo này vẫn cho phép tạo:

```java
new Draft(null);
new Confirmed("");
new Shipped("   ");
```

Các đối tượng trên có **kiểu hợp lệ** nhưng **dữ liệu không hợp lệ** nếu miền yêu cầu mã và chuỗi không được để trống. Do đó, `sealed` giải quyết câu hỏi **"Những dạng trạng thái nào tồn tại?"**, còn constructor/factory giải quyết câu hỏi **"Một trạng thái cụ thể được tạo bằng dữ liệu nào?"**.

### Giới hạn kế thừa trực tiếp và `non-sealed`

Các kiểu con trực tiếp của một kiểu `sealed` phải được cấp phép và phải tiếp tục chính sách kế thừa theo một trong các cách `final`, `sealed` hoặc `non-sealed`. Một `record` vốn là `final`; với class hoặc interface khác, có thể chọn mở rộng tiếp.

```java
sealed interface Event permits KnownEvent, ExtensionEvent {}

record KnownEvent(String id) implements Event {}

non-sealed interface ExtensionEvent extends Event {}
```

`Event` chỉ cấp phép hai **kiểu con trực tiếp**, nhưng các lớp khác vẫn có thể triển khai `ExtensionEvent`. Nếu thiết kế yêu cầu **tập biến thể thực sự đóng**, phải xét toàn bộ cây kiểu và tránh mở một nhánh bằng `non-sealed` ngoài ý muốn.

Trong Java 17, kiểu con trực tiếp được cấp phép phải ở **cùng named module** với kiểu `sealed` gốc, hoặc **cùng package** nếu thuộc unnamed module. Đóng một cây kiểu không đồng nghĩa tạo ra một lớp bảo mật: `sealed` không thay cho kiểm tra quyền, xác thực yêu cầu hay ranh giới tin cậy.

## 3. Thiết kế trạng thái đơn hàng theo kiểu "mỗi biến thể chỉ giữ dữ liệu phù hợp"

Giả sử một đơn hàng có vòng đời:

```text
                confirm                 ship
    Draft  ----------------> Confirmed ---------> Shipped
      |                         |
      | cancel                  | cancel
      v                         v
   Cancelled <------------------+

    Shipped và Cancelled là các trạng thái kết thúc.
```

Các dữ liệu hợp lệ của từng trạng thái:

| Biến thể | Dữ liệu cần có | Bất biến |
| --- | --- | --- |
| `Draft` | Danh sách dòng hàng | Có ít nhất một dòng, các SKU không trùng, mỗi số lượng dương. |
| `Confirmed` | Mã xác nhận, thời gian xác nhận, danh sách dòng hàng | Mã không rỗng, thời gian khác `null`, danh sách hợp lệ. |
| `Shipped` | Mã xác nhận, thời gian xác nhận/giao, danh sách dòng hàng | Thời gian giao không trước thời gian xác nhận, các trường còn lại hợp lệ. |
| `Cancelled` | Lý do hủy | Lý do hủy không rỗng. |

Cách này tránh một đối tượng kiểu:

```java
// Minh họa thiết kế dễ tạo trạng thái vô nghĩa:
class MutableOrderData {
    boolean shipped;
    boolean cancelled;
    String confirmationId;
    String trackingCode;
    String cancellationReason;
}
```

Với cách dùng nhiều cờ độc lập, có thể xảy ra `shipped == true` **và** `cancelled == true`, hoặc `shipped == true` nhưng không có thời gian giao. Khi các trạng thái có dữ liệu khác nhau, một `sealed interface` cùng các biến thể riêng biệt thể hiện hợp đồng rõ hơn.

**Tuy nhiên, tách biến thể mới chỉ bảo vệ cấu trúc.** Vẫn cần kiểm tra các giá trị bên trong từng biến thể và không cho thay đổi trạng thái bằng các đường đi không hợp lệ.

## 4. Ví dụ hoàn chỉnh trên Java 17

Ví dụ dưới đây khai báo một aggregate `Order` giữ trường `state` ở chế độ `private`, các biến thể trạng thái cũng được giấu bên trong lớp miền. Đầu vào của mỗi trạng thái được kiểm tra ngay khi tạo, và mọi thay đổi trạng thái đi qua phương thức nghiệp vụ của `Order`.

Lưu thành `OrderInvariantDemo.java`:

```java
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;

public final class OrderInvariantDemo {
    private OrderInvariantDemo() {}

    // Giá trị dùng chung. Record không thể bị kế thừa.
    public record Line(String sku, int quantity) {
        public Line {
            sku = requireText(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException("quantity must be positive");
            }
        }
    }

    // Tập trạng thái hợp lệ nằm dưới quyền kiểm soát của mô hình miền.
    private sealed interface State
            permits Draft, Confirmed, Shipped, Cancelled {
    }

    private record Draft(List<Line> lines) implements State {
        Draft {
            lines = requireLines(lines);
        }
    }

    private record Confirmed(
            String confirmationId,
            Instant confirmedAt,
            List<Line> lines) implements State {

        Confirmed {
            confirmationId = requireText(confirmationId, "confirmationId");
            Objects.requireNonNull(confirmedAt, "confirmedAt");
            lines = requireLines(lines);
        }
    }

    private record Shipped(
            String confirmationId,
            Instant confirmedAt,
            Instant shippedAt,
            List<Line> lines) implements State {

        Shipped {
            confirmationId = requireText(confirmationId, "confirmationId");
            Objects.requireNonNull(confirmedAt, "confirmedAt");
            Objects.requireNonNull(shippedAt, "shippedAt");
            if (shippedAt.isBefore(confirmedAt)) {
                throw new IllegalArgumentException(
                        "shippedAt must not be before confirmedAt");
            }
            lines = requireLines(lines);
        }
    }

    private record Cancelled(String reason) implements State {
        Cancelled {
            reason = requireText(reason, "reason");
        }
    }

    // Aggregate chỉ đưa ra các thao tác nghiệp vụ được cho phép.
    public static final class Order {
        private State state;

        public Order(List<Line> lines) {
            state = new Draft(lines);
        }

        public void confirm(String confirmationId, Instant confirmedAt) {
            if (!(state instanceof Draft draft)) {
                throw new IllegalStateException("Only Draft can be confirmed");
            }

            // Constructor của Confirmed kiểm tra dữ liệu trước khi gán state.
            state = new Confirmed(confirmationId, confirmedAt, draft.lines());
        }

        public void ship(Instant shippedAt) {
            if (!(state instanceof Confirmed confirmed)) {
                throw new IllegalStateException("Only Confirmed can be shipped");
            }

            state = new Shipped(
                    confirmed.confirmationId(),
                    confirmed.confirmedAt(),
                    shippedAt,
                    confirmed.lines());
        }

        public void cancel(String reason) {
            if (state instanceof Draft || state instanceof Confirmed) {
                state = new Cancelled(reason);
                return;
            }

            throw new IllegalStateException(
                    "Only Draft or Confirmed can be cancelled");
        }

        public String status() {
            if (state instanceof Draft) return "DRAFT";
            if (state instanceof Confirmed) return "CONFIRMED";
            if (state instanceof Shipped) return "SHIPPED";
            if (state instanceof Cancelled) return "CANCELLED";
            throw new IllegalStateException("Unhandled order state");
        }
    }

    private static String requireText(String text, String fieldName) {
        String normalized = Objects.requireNonNull(text, fieldName).strip();
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException(fieldName + " must not be blank");
        }
        return normalized;
    }

    private static List<Line> requireLines(List<Line> input) {
        // List.copyOf từ chối null trong danh sách và tạo bản sao không sửa được.
        List<Line> copy = List.copyOf(Objects.requireNonNull(input, "lines"));
        if (copy.isEmpty()) {
            throw new IllegalArgumentException("order must contain at least one line");
        }

        Set<String> seenSkus = new HashSet<>();
        for (Line line : copy) {
            if (!seenSkus.add(line.sku())) {
                throw new IllegalArgumentException("duplicate sku: " + line.sku());
            }
        }
        return copy;
    }

    public static void main(String[] args) {
        List<Line> external = new ArrayList<>();
        external.add(new Line(" BOOK-17 ", 2));

        Order order = new Order(external);
        external.clear(); // Không thể làm rỗng danh sách bên trong Draft.
        System.out.println(order.status()); // DRAFT

        order.confirm("CONF-100", Instant.parse("2026-02-01T10:00:00Z"));
        System.out.println(order.status()); // CONFIRMED

        order.ship(Instant.parse("2026-02-02T10:00:00Z"));
        System.out.println(order.status()); // SHIPPED

        try {
            order.cancel("Change of mind");
        } catch (IllegalStateException ex) {
            System.out.println(ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng JDK 17:

```bash
javac --release 17 OrderInvariantDemo.java
java OrderInvariantDemo
```

Đầu ra dự kiến:

```text
DRAFT
CONFIRMED
SHIPPED
Only Draft or Confirmed can be cancelled
```

Ví dụ minh họa các cơ chế bổ trợ nhau:

1. **`sealed`**: chỉ bốn record được khai báo có thể trực tiếp triển khai `State`; vì các record là `final`, các trạng thái lá không có subtype bổ sung.
2. **Constructor của `Line` và các record trạng thái**: không nhận giá trị vi phạm bất biến, kể cả khi đối tượng được tạo từ một đường gọi khác trong mã miền.
3. **Sao chép `List.copyOf`**: không giữ tham chiếu đến một `ArrayList` mà caller có thể sửa sau khi tạo trạng thái.
4. **Trường `state` riêng tư**: caller không thể tự gán một đối tượng trạng thái tùy ý cho `Order`.
5. **Phương thức `confirm`, `ship`, `cancel`**: kiểm soát chuyển trạng thái, nên không thể gọi `ship` khi vẫn là `Draft`, cũng không thể `cancel` khi đã `Shipped`.
6. **Gán sau khi tạo trạng thái mới thành công**: khi constructor ném exception do dữ liệu sai, phép gán `state = new ...` không xảy ra, tránh trạng thái thay đổi dở dang đối với những thao tác đơn giản này.

Ở đây `Order` là aggregate mutable có chủ đích, còn các trạng thái nội bộ là những giá trị không thay đổi sau khi tạo. Cách kết hợp này cho phép thực hiện nghiệp vụ thay đổi trạng thái qua hành vi có kiểm soát mà không cung cấp setter công khai cho từng trường.

## 5. Constructor là nơi giữ bất biến của từng giá trị

Trong Java 17, `record` phù hợp để biểu diễn các biến thể chủ yếu mang dữ liệu. Record tự sinh accessor, `equals`, `hashCode` và `toString` dựa trên các thành phần đã khai báo. Với **compact constructor**, ta có thể chuẩn hóa và kiểm tra tham số trước khi Java gán chúng vào trường của record:

```java
record ProductCode(String value) {
    ProductCode {
        value = Objects.requireNonNull(value, "value").strip();
        if (value.isEmpty()) {
            throw new IllegalArgumentException("Product code must not be blank");
        }
    }
}
```

`Objects.requireNonNull` ở đây yêu cầu `import java.util.Objects;`. Sau constructor, `new ProductCode("  P-17  ").value()` trả về `"P-17"`. Accessor record chuẩn là `value()`, không phải `getValue()`.

### Kiểm tra sớm và giữ đối tượng ở trạng thái hợp lệ

Nếu một giá trị **không thể hợp lệ trong bất cứ ngữ cảnh nào**, kiểm tra ngay trong constructor hoặc factory của kiểu giá trị đó. Ví dụ:

- `quantity <= 0` không hợp lệ với dòng đơn hàng: kiểm tra trong `Line`.
- `sku` rỗng hoặc chỉ toàn dấu cách: kiểm tra trong kiểu mã SKU hoặc `Line`.
- `shippedAt` có trước `confirmedAt`: kiểm tra ngay trong `Shipped`, vì đây là quan hệ giữa chính các thành phần của biến thể.
- Danh sách không có dòng hoặc có SKU trùng: kiểm tra khi tạo một trạng thái chứa danh sách đó.

Làm vậy giúp mọi caller sử dụng cùng quy tắc. Nếu chỉ kiểm tra tại controller rồi cho phép nơi khác tạo record với dữ liệu sai, logic nội bộ, test hoặc quá trình khôi phục dữ liệu có thể vô tình tạo một giá trị không hợp lệ.

Phân biệt các exception thường dùng:

| Tình huống | Một lựa chọn thường dùng | Ý nghĩa |
| --- | --- | --- |
| Giá trị truyền vào là `null`, trong khi hợp đồng yêu cầu khác `null` | `NullPointerException` từ `Objects.requireNonNull` | Thiếu một giá trị bắt buộc. |
| Có giá trị nhưng vi phạm quy tắc của tham số | `IllegalArgumentException` | Ví dụ số lượng bằng 0, mã trống, thời gian sai thứ tự. |
| Dữ liệu tham số hợp lệ nhưng thao tác không phù hợp trạng thái hiện tại | `IllegalStateException` | Ví dụ gọi `ship` trên đơn chưa được xác nhận. |

Đây là các lựa chọn phù hợp cho một API Java thông thường, **không phải ánh xạ HTTP**. Tầng API có thể chuyển lỗi đầu vào thành phản hồi `400` hoặc `422` theo hợp đồng cụ thể, còn xung đột trạng thái có thể thành `409`. Mã HTTP không nên được suy ra một cách máy móc chỉ từ tên exception của Java.

### Một record không đồng nghĩa bất biến sâu

Các trường của record là `private final`, nhưng một trường kiểu `List<T>` hoặc mảng có thể trỏ đến một cấu trúc thay đổi được. Ví dụ sau vẫn có lỗ hổng nếu không sao chép:

```java
record UnsafeCart(List<String> skus) {}

List<String> source = new java.util.ArrayList<>();
source.add("A");
UnsafeCart cart = new UnsafeCart(source);
source.clear();
// cart.skus() đã bị thay đổi gián tiếp.
```

Một cách an toàn hơn cho danh sách chuỗi là:

```java
record SafeCart(List<String> skus) {
    SafeCart {
        skus = List.copyOf(Objects.requireNonNull(skus, "skus"));
    }
}
```

`List.copyOf` tạo một danh sách không cho thay đổi qua API `List`, nhưng đây là **bất biến nông**: nếu các phần tử là object mutable, nội dung của chúng vẫn có thể thay đổi. Nếu component là **array**, phải tính đến sao chép phòng vệ ở cả đầu vào và accessor, vì `final` không ngăn sửa các phần tử của array. Với mô hình dữ liệu cần bất biến sâu, thường nên ưu tiên những phần tử bản thân đã bất biến, như `String`, `Instant`, value object có kiểm tra dữ liệu, hoặc record chỉ chứa những thành phần bất biến tương ứng.

## 6. Bất biến chuyển trạng thái cần logic nghiệp vụ riêng

Cho dù cây kiểu chỉ có `Draft`, `Confirmed`, `Shipped` và `Cancelled`, điều đó **không ngăn** một đoạn mã tạo trực tiếp `Shipped` từ dữ liệu đầu vào chưa từng trải qua xác nhận, nếu constructor của `Shipped` được công khai. `sealed` không lưu lịch sử đối tượng và không biết lệnh nghiệp vụ nào đã xảy ra.

Vì vậy cần phân biệt hai khái niệm:

- **Trạng thái tự hợp lệ**: mọi giá trị của `Shipped` có `confirmedAt`, `shippedAt` hợp lệ và danh sách dòng hàng hợp lệ.
- **Quá trình tạo ra trạng thái hợp lệ**: chỉ được đưa một đơn hàng từ `Confirmed` sang `Shipped` bằng thao tác nghiệp vụ cho phép.

Trong ví dụ chính, `State` và các record trạng thái là `private`, còn `Order` chỉ cung cấp `confirm`, `ship` và `cancel`. Cách này đặt các phép chuyển ở cùng một nơi, ngăn caller sửa `state` trực tiếp.

Nếu hệ thống cần nhiều quy tắc hơn, có thể đưa logic chuyển trạng thái vào các phương thức nghiệp vụ có tên rõ như `approve`, `reject`, `pay`, `refund`, thay vì setter kiểu `setState`. Việc chọn method nên theo **ngôn ngữ miền**, vì `setState(SHIPPED)` không nói rõ điều kiện để giao hàng hoặc tác dụng đi kèm.

### Nếu phải trả trạng thái cho bên ngoài thì sao?

Với hệ thống có API công khai, thường cần một biểu diễn chỉ đọc để hiển thị cho client. Có thể trả về **DTO/snapshot đã được chuyển đổi** từ aggregate, thay vì trả thẳng tham chiếu tới cấu trúc trạng thái có thể khởi tạo từ bên ngoài. Nếu một sealed hierarchy công khai cho phép mọi caller tạo bản ghi mới, các constructor của biến thể vẫn phải kiểm tra dữ liệu; nhưng việc kiểm soát **vòng đời aggregate** thuộc trách nhiệm của aggregate/service chứ không nằm ở `permits`.

### Lưu ý tính đồng thời

`Order` trong ví dụ là **mutable và không được thiết kế cho truy cập đồng thời từ nhiều luồng**. Nếu hai luồng cùng thực hiện `confirm` hoặc `cancel`, kiểm tra trạng thái rồi gán giá trị cần được thực hiện theo một cơ chế đồng bộ hoặc giao dịch phù hợp. Với ứng dụng có cơ sở dữ liệu và nhiều phiên xử lý, thường còn cần transaction, optimistic locking/version, hoặc ràng buộc ở persistence layer để ngăn cập nhật cạnh tranh. `sealed`, record và constructor hợp lệ không tự giải quyết race condition.

## 7. Kiểm tra đầu vào ở ranh giới: parse, validate, rồi mới tạo domain object

Các giá trị từ HTTP request, dòng CSV, message queue, file cấu hình hoặc cơ sở dữ liệu đều có thể thiếu, sai định dạng hoặc không phù hợp với miền. Nên tách các bước:

```text
Request thô / JSON / Message
           |
           v
      Parse / deserialize
           |
           v
  Kiểm tra cấu trúc, kiểu, định dạng
           |
           v
  Tạo value object + record miền
  (constructor bảo vệ bất biến)
           |
           v
  Gọi phương thức aggregate
  (kiểm tra chuyển trạng thái)
           |
           v
     Lưu / phát sự kiện / phản hồi
```

Ví dụ một DTO từ API có thể chứa dữ liệu chưa được kiểm tra:

```java
record CreateLineRequest(String sku, Integer quantity) {}
```

Lựa chọn `Integer` ở DTO giúp mô tả trường số lượng **có thể vắng mặt** trong yêu cầu bên ngoài. Khi chuyển DTO thành `Line` của miền, cần kiểm tra `null` và chuyển sang `int` chỉ sau khi dữ liệu hợp lệ:

```java
static OrderInvariantDemo.Line toDomain(CreateLineRequest request) {
    Objects.requireNonNull(request, "request");

    Integer quantity = request.quantity();
    if (quantity == null) {
        throw new IllegalArgumentException("quantity is required");
    }

    return new OrderInvariantDemo.Line(request.sku(), quantity);
}
```

Trong đoạn minh họa này, cần import `java.util.Objects`. Việc gọi `new Line(...)` tiếp tục kiểm tra SKU và số lượng dương, nên invariant không phụ thuộc vào việc DTO có được kiểm tra ở controller hay không. Đối với DTO số lượng lớn hoặc nhiều lớp validation, có thể sử dụng Bean Validation cùng các ràng buộc được dự án hỗ trợ, nhưng vẫn nên bảo vệ **quy tắc cốt lõi của miền** trong constructor/factory và hành vi nghiệp vụ; annotation ở request layer không thay thế được chúng.

### Kiểm tra giá trị và kiểm tra theo ngữ cảnh

Không phải quy tắc nào cũng thuộc constructor:

| Điều kiện | Đặt kiểm tra ở đâu? | Lý do |
| --- | --- | --- |
| SKU không rỗng | Value object hoặc record `Line` | Đúng trong mọi ngữ cảnh sử dụng SKU. |
| Số lượng dương | `Line` | Bất biến cục bộ, không cần truy cập hệ thống khác. |
| SKU có tồn tại trong catalog hiện tại | Application/domain service và repository | Phụ thuộc dữ liệu có thể thay đổi theo thời gian. |
| Người gọi được phép xác nhận đơn này | Tầng xác thực/phân quyền và use case | Phụ thuộc danh tính và chính sách truy cập. |
| Chỉ được giao một đơn đã xác nhận | Aggregate `Order` | Phụ thuộc trạng thái hiện tại của đơn. |
| Không giao trước ngày xác nhận | Constructor `Shipped` | Quan hệ nội tại giữa các trường của biến thể. |
| Không xác nhận trùng cùng mã trên hệ thống | Persistence/transaction và ràng buộc duy nhất | Phụ thuộc nhiều đối tượng hoặc nhiều giao dịch. |

Ranh giới đầu vào có trách nhiệm báo lỗi rõ, đủ ngữ cảnh cho người gọi, nhưng **domain model vẫn phải tự bảo vệ trạng thái hợp lệ** trước mọi đường khởi tạo được phép. Không nên chỉ dựa vào kiểm tra phía giao diện người dùng hoặc một controller duy nhất.

## 8. Các biến thể `sealed` nên có dữ liệu đúng với ý nghĩa miền

Một lỗi thiết kế phổ biến là biến một record thành "túi trường tùy chọn":

```java
record PaymentResult(
        boolean success,
        String transactionId,
        String rejectionReason) {}
```

Kiểu trên cho phép tổ hợp `success = true`, `transactionId = null`, `rejectionReason = "Rejected"`, và nhiều tổ hợp vô nghĩa khác. Nếu dữ liệu thật sự có **hai hình dạng khác nhau**, có thể diễn đạt:

```java
sealed interface PaymentResult permits Approved, Rejected {}

record Approved(String transactionId) implements PaymentResult {
    Approved {
        transactionId = Objects.requireNonNull(transactionId, "transactionId").strip();
        if (transactionId.isEmpty()) {
            throw new IllegalArgumentException("transactionId is required");
        }
    }
}

record Rejected(String reason) implements PaymentResult {
    Rejected {
        reason = Objects.requireNonNull(reason, "reason").strip();
        if (reason.isEmpty()) {
            throw new IllegalArgumentException("reason is required");
        }
    }
}
```

Đoạn code dùng `java.util.Objects`. Trong Java 17, các record này không thể kế thừa class tùy ý (vì record ngầm định kế thừa `java.lang.Record`), nhưng có thể `implements PaymentResult`; vì vậy `sealed interface` là một lựa chọn tự nhiên cho kiểu tổng với các biến thể record.

Mô hình này loại bỏ khả năng một **cùng giá trị** vừa là `Approved` vừa là `Rejected` và buộc dữ liệu cần thiết của mỗi trường hợp nằm trong đúng biến thể. Tuy nhiên, việc quyết định **khi nào** được chấp thuận, khoản tiền có đủ không, hay giao dịch đã được ghi nhận chưa vẫn là logic nghiệp vụ ngoài phạm vi `sealed`.

## 9. Xử lý biến thể an toàn trong Java 17

Trong Java 17, pattern matching với `instanceof` là tính năng chính thức:

```java
static String message(PaymentResult result) {
    Objects.requireNonNull(result, "result");

    if (result instanceof Approved approved) {
        return "Paid: " + approved.transactionId();
    }
    if (result instanceof Rejected rejected) {
        return "Rejected: " + rejected.reason();
    }
    throw new IllegalStateException("Unhandled payment result");
}
```

Pattern `Approved approved` vừa kiểm tra kiểu vừa tạo biến có kiểu `Approved`, nhờ vậy không cần ép kiểu thủ công. Chú ý `instanceof` với `null` trả về `false`; trong ví dụ, đầu vào `null` được từ chối tường minh.

**Giới hạn quan trọng trên Java 17:** chuỗi `if (result instanceof ...)` **không được trình biên dịch kiểm tra tính bao phủ mọi kiểu con của sealed hierarchy**. Nếu thêm một biến thể mới như `Pending` vào `permits`, code xử lý cũ vẫn có thể biên dịch và chỉ thất bại khi chạy vào nhánh dự phòng. Vì vậy, khi thêm/bớt biến thể, cần rà soát các vị trí xử lý liên quan.

Pattern matching cho `switch` và **record patterns** chỉ được chính thức hóa từ Java 21. Trong Java 17, pattern `switch` vẫn là tính năng preview, không nên dựa vào cú pháp preview cũ cho ví dụ thực hành hoặc mã Java 17 ổn định. Nếu cần xử lý phân nhánh theo kiểu trên Java 17, `instanceof` pattern matching là lựa chọn phù hợp và đã chính thức.

## 10. Bất biến khi khôi phục dữ liệu, giải tuần tự hóa và tích hợp framework

Việc dữ liệu được lưu trong database hoặc đi qua hệ thống ngoài không bảo đảm nó hợp lệ khi được nạp lại. Ví dụ một record trạng thái có thể được khôi phục từ JSON, JPA entity, hàng dữ liệu SQL hoặc message queue. Với thiết kế miền chặt chẽ, nên có một **đường tái tạo có kiểm tra**:

1. Đọc dữ liệu thô thành kiểu trung gian có thể biểu diễn giá trị thiếu hoặc sai.
2. Phân biệt rõ biến thể dựa trên trường phân loại được định nghĩa trong hợp đồng dữ liệu (ví dụ `kind = "CONFIRMED"`).
3. Tạo value object và trạng thái thông qua constructor/factory có kiểm tra.
4. Kiểm tra thêm các bất biến liên quan trạng thái khác, phiên bản aggregate hoặc dữ liệu tham chiếu nếu cần.
5. Báo lỗi cụ thể hoặc đưa dữ liệu hỏng vào luồng xử lý lỗi, tránh âm thầm tạo một đối tượng miền hợp lệ giả.

Ví dụ khi lưu một tập biến thể sealed dưới dạng JSON, nhiều thư viện yêu cầu cấu hình rõ cách nhận diện subtype hoặc mapping DTO; `sealed` không tự quyết định định dạng JSON hay schema cơ sở dữ liệu. Trong Java 17, record có cơ chế canonical constructor và các accessor riêng, nhưng mức độ hỗ trợ record/sealed của từng thư viện phụ thuộc **phiên bản và cấu hình thư viện**. Không nên giả định mọi framework đều tự hiểu `permits` và áp dụng tất cả kiểm tra nghiệp vụ.

Đối với cơ sở dữ liệu, constraint như `NOT NULL`, `CHECK`, `UNIQUE` và foreign key có thể hỗ trợ giữ dữ liệu hợp lệ khi có nhiều tác nhân ghi. Chúng bổ sung cho invariant trong Java: constructor bảo vệ object trong bộ nhớ, trong khi transaction/constraint bảo vệ tính nhất quán xuyên yêu cầu và giữa các tiến trình.

### Thay đổi mô hình qua thời gian

Thêm một biến thể mới vào cây `sealed` có thể làm thay đổi hợp đồng API và dữ liệu đã lưu. Cần cân nhắc:

- Đầu đọc dữ liệu cũ có xử lý được tag của biến thể mới không?
- Những nơi dùng `if/instanceof` đã có nhánh cho biến thể mới chưa?
- Việc thêm bất biến mới có làm dữ liệu lịch sử không còn hợp lệ không?
- Có cần migration hoặc cơ chế chấp nhận dữ liệu cũ và chuyển sang dạng hợp lệ mới không?

Một cây kiểu đóng giúp hình dung toàn bộ các dạng dữ liệu hiện tại, nhưng **không tự làm cho quá trình thay đổi schema trở nên tương thích**.

## 11. Kiểm thử những đường tạo trạng thái và chuyển trạng thái

Có hai nhóm tình huống quan trọng cần kiểm chứng trong một hệ thống thực tế:

**Đối tượng hợp lệ được tạo thành công:**

- Dòng hàng `Line("A", 1)` hợp lệ.
- `Order` được tạo với ít nhất một dòng hợp lệ, SKU duy nhất.
- `Draft → Confirmed → Shipped` thành công khi thời gian giao không sớm hơn thời gian xác nhận.
- `Draft → Cancelled` và `Confirmed → Cancelled` thành công khi lý do hủy hợp lệ.

**Đối tượng hoặc thao tác không hợp lệ bị từ chối:**

- SKU trống, số lượng bằng 0 hoặc âm.
- Danh sách dòng hàng `null`, rỗng, có phần tử `null` hoặc trùng SKU.
- Mã xác nhận trống hoặc thời điểm xác nhận `null`.
- Thời điểm giao hàng sớm hơn thời điểm xác nhận.
- `Draft → Shipped`, `Shipped → Cancelled`, `Cancelled → Confirmed`.
- Caller sửa danh sách ban đầu sau khi tạo `Order` mà trạng thái bên trong vẫn không bị sửa gián tiếp.

Ví dụ một bài test JUnit Jupiter khi dự án đã cấu hình JUnit 5:

```java
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.*;

class OrderInvariantTest {
    @Test
    void invalidQuantityIsRejectedAtCreation() {
        assertThrows(IllegalArgumentException.class,
                () -> new OrderInvariantDemo.Line("A", 0));
    }

    @Test
    void cannotShipBeforeConfirmation() {
        var order = new OrderInvariantDemo.Order(
                List.of(new OrderInvariantDemo.Line("A", 1)));

        assertThrows(IllegalStateException.class,
                () -> order.ship(Instant.parse("2026-02-01T10:00:00Z")));
        assertEquals("DRAFT", order.status());
    }

    @Test
    void failedTransitionKeepsPreviousState() {
        var order = new OrderInvariantDemo.Order(
                List.of(new OrderInvariantDemo.Line("A", 1)));
        order.confirm("CONF-1", Instant.parse("2026-02-02T10:00:00Z"));

        assertThrows(IllegalArgumentException.class,
                () -> order.ship(Instant.parse("2026-02-01T10:00:00Z")));
        assertEquals("CONFIRMED", order.status());
    }
}
```

Những bài test này chứng minh **hành vi từ chối dữ liệu sai và giữ nguyên trạng thái khi thao tác thất bại**. Chúng không thể thay thế việc kiểm tra ở runtime, transaction hoặc dữ liệu ngoài hệ thống. Nếu hệ thống chạy đồng thời hoặc sử dụng persistence, cần có kiểm thử phù hợp cho cạnh tranh cập nhật và khôi phục trạng thái.

## 12. Những hiểu lầm dễ gây lỗi thiết kế

| Hiểu lầm | Thực tế trên Java 17 | Hướng xử lý |
| --- | --- | --- |
| "Đã `sealed` là dữ liệu luôn hợp lệ" | `sealed` chỉ kiểm soát các kiểu con trực tiếp. | Kiểm tra các trường trong constructor/factory và điều kiện chuyển trạng thái trong aggregate. |
| "`record` là immutable hoàn toàn" | Trường tham chiếu `final` không làm object bên trong bất biến. | Sao chép phòng vệ và dùng phần tử bất biến khi cần. |
| "Mọi biến thể phải public để pattern match" | Có thể giữ biến thể `private` bên trong miền và cung cấp API đọc phù hợp. | Phân biệt kiểu nội bộ với DTO/snapshot công khai. |
| "Chỉ cần validate tại HTTP controller" | Domain object có thể được tạo qua test, worker, dữ liệu lưu trữ và code nội bộ. | Giữ invariant cốt lõi ngay trong domain model. |
| "`permits` đóng mọi lớp cháu/chắt" | Nhánh `non-sealed` vẫn cho phép mở rộng tiếp. | Xem toàn bộ cây và chọn chính sách kế thừa phù hợp. |
| "`instanceof` đầy đủ các nhánh sẽ được compiler kiểm tra" | Chuỗi `if/instanceof` trong Java 17 không có exhaustiveness checking cho sealed. | Rà soát khi bổ sung biến thể và có nhánh lỗi rõ ràng. |
| "Giá trị hợp lệ đồng nghĩa lịch sử chuyển trạng thái hợp lệ" | Một giá trị `Shipped` đúng trường dữ liệu chưa chứng minh `Order` từng đi qua `Confirmed`. | Chỉ cho chuyển trạng thái qua phương thức nghiệp vụ và bảo vệ trạng thái nội bộ. |
| "`sealed` ngăn được race condition" | Không có cơ chế đồng bộ hay transaction được thêm vào nhờ từ khóa này. | Dùng đồng bộ, transaction hoặc optimistic locking khi cần. |
| "Java 17 dùng được `switch` theo type pattern như Java 21" | Type-pattern `switch` chưa là tính năng chính thức ở Java 17. | Dùng `instanceof` pattern matching đã chính thức trong Java 17. |

## 13. Cách áp dụng vào một mô hình miền mới

Khi bắt đầu một yêu cầu có nhiều trường hợp dữ liệu, có thể lần lượt xác định:

1. **Liệt kê các biến thể thực sự khác nhau.** Chỉ tạo một biến thể khi nó có ý nghĩa nghiệp vụ hoặc dữ liệu riêng; nếu các trường hợp chỉ là những nhãn không có payload khác nhau, `enum` có thể đơn giản hơn.
2. **Quyết định cây kiểu có cần đóng không.** Nếu mọi biến thể do nhóm kiểm soát, `sealed interface` là ứng viên phù hợp; nếu API chủ ý cho người khác mở rộng subtype, cần cân nhắc ảnh hưởng của việc `sealed`.
3. **Đặt bất biến cục bộ vào value object/record.** Bao gồm khác `null`, không rỗng, giới hạn giá trị, quan hệ giữa các trường và sao chép phòng vệ.
4. **Đặt bất biến vòng đời vào aggregate.** Chỉ phơi bày hành vi nghiệp vụ phù hợp; không mở setter cho trạng thái nội bộ nếu setter có thể tạo trạng thái trái quy tắc.
5. **Đặt kiểm tra theo ngữ cảnh ở đúng tầng.** Quyền truy cập, tồn tại dữ liệu, điều kiện liên đối tượng hoặc yêu cầu giao dịch cần service/repository/DB hỗ trợ.
6. **Chỉ đưa object hợp lệ vào miền.** Parse và kiểm tra dữ liệu đầu vào, khởi tạo bằng constructor/factory, rồi thực hiện các thao tác trên aggregate.
7. **Xem xét cả trường hợp bị từ chối.** Không chỉ kiểm tra đường thành công; dữ liệu không hợp lệ và chuyển trạng thái sai phải có hành vi được xác định rõ.

**Nguyên tắc cốt lõi:** `sealed` giới hạn **hình dạng hợp lệ của miền**, constructor và record bảo vệ **giá trị hợp lệ của mỗi hình dạng**, còn aggregate cùng các phương thức nghiệp vụ bảo vệ **quá trình thay đổi hợp lệ theo thời gian**. Khi kiểm tra đầu vào và dữ liệu khôi phục được nối vào các lớp bảo vệ này, ứng dụng Java 17 có thể giảm đáng kể các trạng thái vô nghĩa và tập trung quy tắc miền ở những nơi có thể kiểm soát được.
