# Biểu diễn command payload bằng record: case study Java 21+

## 1. Bối cảnh: một yêu cầu nghiệp vụ có dữ liệu gì?

Giả sử một ứng dụng quản lý giỏ hàng nhận các yêu cầu:

- **Tạo giỏ** với mã `cartId`.
- **Thêm sản phẩm** với mã giỏ và danh sách dòng sản phẩm (`sku`, `quantity`).
- **Thanh toán** giỏ theo mã.
- **Hủy giỏ** với một lý do.

Các yêu cầu này là **command**: chúng thể hiện ý định cần xử lý, chứ không khẳng định hành động đã xảy ra. Một command có thể bị từ chối vì dữ liệu sai, thiếu quyền, giỏ không tồn tại hoặc trạng thái không cho phép.

Trong hệ thống thực tế, thông điệp command còn có metadata như mã request, actor/correlation ID, thời điểm hoặc schema version. Cần phân biệt:

- **Command payload:** dữ liệu nghiệp vụ mô tả *làm gì và với đối tượng nào*, ví dụ `AddProducts("C-1", [Line("SACH",2)])`.
- **Command envelope:** lớp bao ngoài chứa metadata và payload, ví dụ `Envelope(requestId, actorId, payload)`.
- **Domain state/aggregate:** trạng thái giỏ hàng đang được xử lý; nó không phải payload.
- **Event:** thông điệp khẳng định điều gì **đã xảy ra** sau khi xử lý thành công, ví dụ `ProductsAdded`; event không đồng nghĩa command.

**Vấn đề của bài học:** dùng **Java record** để tạo payload có kiểu tĩnh rõ, có dữ liệu ổn định sau khi tạo, kiểm tra được cấu trúc và dễ dispatch bằng pattern matching. Bài dùng Java **21+** để kết hợp record, sealed interface, record patterns và `switch`; record bản thân đã là tính năng chuẩn từ Java 16.

## 2. Vì sao record phù hợp với command payload?

Một payload cần thể hiện một tập dữ liệu đã biết. Ví dụ tối giản:

~~~java
record AddOneProduct(String cartId, String sku, int quantity) {}

AddOneProduct payload = new AddOneProduct("C-1", "SACH", 2);
System.out.println(payload.cartId());  // C-1
System.out.println(payload.sku());     // SACH
System.out.println(payload.quantity());// 2
~~~

Java record tự cung cấp các thành phần theo hợp đồng của record class:

1. **Các component** trong header, ví dụ `String cartId`, `int quantity`.
2. **Canonical constructor** để khởi tạo đủ component (có thể tùy biến kiểm tra dữ liệu).
3. **Accessor** như `cartId()`, `quantity()`, không phải getter JavaBeans mặc định `getCartId()`.
4. `equals()` và `hashCode()` dựa trên giá trị component; `toString()` để chẩn đoán thuận tiện.
5. Các field giữ dữ liệu component là `private final`. Một record là `final`, không thể có class con.

**Lợi ích khi làm payload:** dữ liệu phải được truyền rõ tại chỗ tạo; không cần một object có nhiều setter và trạng thái trung gian thiếu field; handler nhận được một cấu trúc ổn định và có thể so khớp pattern dễ dàng.

**Không nên hiểu quá mức:** record **không tự bảo đảm** mọi giá trị đều hợp lệ, không tự xác thực quyền, không tự serialize JSON bằng thư viện bất kỳ và không tự trở nên *deeply immutable* khi chứa tham chiếu đến object mutable.

## 3. Payload và envelope: tách nghiệp vụ khỏi metadata vận chuyển

Một cách đặt kiểu rõ ràng:

~~~java
sealed interface Payload permits CreateCart, AddProducts, Checkout, CancelCart {}

record CreateCart(String cartId) implements Payload {}

record Line(String sku, int quantity) {}

record AddProducts(String cartId, List<Line> lines) implements Payload {}

record Checkout(String cartId) implements Payload {}

record CancelCart(String cartId, String reason) implements Payload {}

record Envelope(String requestId, String actorId, Payload payload) {}
~~~

Các đoạn code trên minh họa **hình dạng dữ liệu** (cần import `java.util.List`) và chưa thêm validation. Chương trình đầy đủ ở mục 9 sẽ triển khai tất cả trong cùng một top-level class.

Tại sao không đưa `requestId`, `actorId` vào mọi payload?

- `AddProducts` chỉ cần định danh giỏ và các dòng hàng: đây là dữ liệu thuộc chính yêu cầu nghiệp vụ.
- `requestId` thường là metadata dùng correlation/tracing, và đôi khi là cơ sở cho chính sách idempotency.
- `actorId` mô tả người thực hiện, thường được lấy từ **authentication context đáng tin**, không nên tin chuỗi actor mà client tự nhập trong JSON.
- Metadata như timestamp, tenant, trace ID, version có thể thay đổi theo môi trường vận chuyển mà không đổi ý nghĩa của payload.

Tách envelope giúp handler nhận thông tin chung một lần:

~~~java
static String logLabel(Envelope message) {
    return message.requestId() + " / " +
           message.payload().getClass().getSimpleName();
}
~~~

Đây là đoạn minh họa phụ thuộc vào định nghĩa `Envelope` ở trên; không phải chương trình độc lập.

**Không có một chuẩn duy nhất buộc mọi hệ thống phải dùng envelope.** Nếu ứng dụng nhỏ hoặc command chỉ tồn tại trong nội bộ cùng process, record payload đơn lẻ có thể đủ. Tách envelope hữu ích khi có API, hàng đợi, tracing, audit hoặc nhiều loại command cùng chia sẻ metadata.

## 4. Thiết kế một hierarchy payload đóng bằng `sealed interface`

~~~java
sealed interface Payload
        permits CreateCart, AddProducts, Checkout, CancelCart {}
~~~

Mỗi loại command payload là một record riêng:

~~~java
record CreateCart(String cartId) implements Payload {}
record Checkout(String cartId) implements Payload {}
record CancelCart(String cartId, String reason) implements Payload {}
~~~

**Ưu điểm:**

- Compiler biết tập subtype được cho phép, nên dễ kiểm tra switch expression có xử lý đủ trường hợp hay chưa.
- Mỗi record có những component liên quan trực tiếp tới một intent; không cần một “MegaCommand” gồm `type` và hàng loạt field nullable.
- Code gọi handler có thể nhận một `Payload` chung, trong khi các cấu trúc cụ thể vẫn type-safe.
- Khi thêm subtype `ApplyCoupon`, những chỗ switch exhaustive trên `Payload` có thể bị compiler yêu cầu cập nhật.

**Giới hạn thiết kế:** sealed interface chủ động **đóng** danh sách subtype; không phù hợp với API plugin cho phép bên ngoài tạo subtype tùy ý nếu không có chiến lược mở rộng rõ ràng.

Tên command nên có động từ diễn tả ý định: `CreateCart`, `AddProducts`, `Checkout`, `CancelCart`; event tương ứng nên có tên quá khứ như `CartCreated`, `ProductsAdded`, `CartCheckedOut`. Hai loại thông điệp có vai trò khác nhau dù cả hai đều có thể dùng record.

## 5. Bảo vệ dữ liệu payload bằng compact canonical constructor

Record cho phép kiểm tra và chuẩn hóa tham số ngay khi tạo:

~~~java
static String requireText(String text, String name) {
    if (text == null || text.isBlank())
        throw new IllegalArgumentException(name + " không được trống");
    return text.strip();
}

record CreateCart(String cartId) implements Payload {
    public CreateCart {
        cartId = requireText(cartId, "cartId");
    }
}

record Line(String sku, int quantity) {
    public Line {
        sku = requireText(sku, "sku");
        if (quantity <= 0)
            throw new IllegalArgumentException("quantity phải > 0");
    }
}
~~~

Đây là các đoạn trích để giải thích constructor; nếu đặt ngoài class cần có sẵn kiểu `Payload` và phương thức `requireText` trong phạm vi thích hợp.

Trong **compact constructor**:

1. Các tên `cartId`, `sku`, `quantity` là tham số tương ứng với record components.
2. Ta có thể kiểm tra và gán lại tham số trước khi chúng được lưu vào record fields.
3. Sau phần thân compact constructor, Java tự khởi tạo các field component từ các tham số tương ứng.
4. Không cần và không được tùy tiện gán thủ công `this.cartId = ...` theo cách của canonical constructor đầy đủ trong compact constructor.

Lỗi dữ liệu nên được phát hiện **tại thời điểm tạo payload** khi đó là điều kiện đúng với mọi payload: ID không được rỗng, số lượng phải dương, danh sách thêm hàng không được rỗng.

**Đừng biến compact constructor thành application handler.** Việc một giỏ có tồn tại không, đã checkout chưa, kho đủ hàng không và actor có được phép không phụ thuộc trạng thái bên ngoài: cần xử lý ở tầng nghiệp vụ/application.

## 6. Record có collection: defensive copy là yêu cầu thực tế

Một record có component tham chiếu không tự bảo đảm nội dung object được tham chiếu bất biến. Ví dụ không an toàn:

~~~java
record UnsafeAddProducts(String cartId, List<Line> lines) {}

List<Line> source = new ArrayList<>();
source.add(new Line("SACH", 2));
UnsafeAddProducts command = new UnsafeAddProducts("C-1", source);
source.add(new Line("BUT", 4));

// command.lines() giờ thấy cả "BUT".
~~~

Nếu dữ liệu payload bị thay đổi giữa lúc enqueue và xử lý, hệ thống có thể thực hiện **khác với yêu cầu ban đầu**. Điều này làm khó log/audit, retry và unit test.

Với `List`, nên sao chép phòng vệ trong constructor:

~~~java
record AddProducts(String cartId, List<Line> lines) implements Payload {
    public AddProducts {
        cartId = requireText(cartId, "cartId");
        lines = List.copyOf(Objects.requireNonNull(lines, "lines"));
        if (lines.isEmpty())
            throw new IllegalArgumentException("lines không được rỗng");
    }
}
~~~

`List.copyOf` tạo một danh sách không cho chỉnh sửa thông qua API `List`, tách khỏi các cập nhật cấu trúc danh sách đầu vào. Nó từ chối `null` list và các phần tử null. Đây **là sao chép nông**: nếu phần tử bên trong còn mutable, trạng thái phần tử vẫn có thể thay đổi. Trong ví dụ, phần tử `Line` là record chỉ chứa `String` và `int`, nên cấu trúc phù hợp cho một payload ổn định.

Tương tự, nếu payload chứa array, `Map`, `Set` hay nested mutable object, cần đánh giá cách sao chép và cách accessor trả dữ liệu. Một field `final` chỉ cố định **tham chiếu**, không phải toàn bộ đồ thị object.

## 7. Phân biệt kiểm tra payload và kiểm tra nghiệp vụ

Đây là ranh giới review quan trọng.

| Điều kiện | Kiểm tra ở đâu? | Vì sao? |
| --- | --- | --- |
| `cartId` là chuỗi không trống | Compact constructor/value object | Luôn cần đúng với mọi payload loại này |
| `sku` không rỗng; `quantity > 0` | `Line` constructor | Không cần database để xác định |
| `lines` có ít nhất một phần tử và không chứa null | `AddProducts` constructor | Bảo vệ cấu trúc thông điệp |
| Giỏ có tồn tại không | Handler/repository | Cần trạng thái lưu trữ |
| Actor có quyền với giỏ không | Authentication/authorization + handler | Cần danh tính đáng tin và quyền nghiệp vụ |
| Giỏ đang `DRAFT` không | Domain/application handler | Phụ thuộc trạng thái hiện tại |
| Giỏ có sản phẩm trước checkout không | Domain/application handler | Phụ thuộc aggregate |
| Có bị xử lý trùng request không | Application/infrastructure, persistence | Cần trạng thái request/idempotency bền vững |

Có thể dùng cùng một `AddProducts("C-1", ...)` hợp lệ về cấu trúc nhưng **không hợp lệ để thực thi** nếu giỏ `C-1` đã checkout. Đây không phải là lỗi của Java record.

Cần phân biệt **validation fail** và **business rule fail** trong API error handling: hai loại lỗi có thể map sang mã phản hồi, log và chính sách retry khác nhau.

## 8. Dispatch payload bằng record pattern trong `switch`

Java 21 cho phép handler phân phối theo **kiểu record** và tách các component trực tiếp:

~~~java
static String describe(Payload payload) {
    return switch (payload) {
        case CreateCart(var cartId) ->
            "Tạo giỏ " + cartId;

        case AddProducts(var cartId, var lines) ->
            "Thêm " + lines.size() + " dòng vào " + cartId;

        case Checkout(var cartId) ->
            "Thanh toán " + cartId;

        case CancelCart(var cartId, var reason) ->
            "Hủy " + cartId + ": " + reason;
    };
}
~~~

- `case AddProducts(var cartId, var lines)` sử dụng đúng **thứ tự khai báo component**, không so khớp theo tên biến.
- `var` suy luận kiểu từ record components; trong `AddProducts`, `lines` có kiểu tĩnh `List<Line>`.
- Trong case record, compiler đã biết subtype cụ thể nên không cần cast thủ công.
- Với `sealed interface Payload` và bốn subtype đã được xử lý, switch expression **exhaustive**; không cần `default`. Điều này giúp bắt việc thêm subtype mới mà chưa xử lý.

**Về null:** `switch (payload)` với selector tham chiếu null ném `NullPointerException` nếu thiếu `case null`; `default` cũng không tự bắt null. Trong chương trình thực hành bên dưới, `Envelope` cấm payload null bằng `Objects.requireNonNull(payload, "payload")`, nên handler có tiền điều kiện rõ ràng. Khi nhận dữ liệu bên ngoài, vẫn phải bảo đảm constructor/validation thực sự được gọi.

Pattern matching chỉ quyết định **đi vào nhánh nào**. Nó không tự bảo đảm payload được phép cập nhật state; đó vẫn là trách nhiệm handler.

## 9. Ví dụ Java 21+ hoàn chỉnh: payload, envelope, handler và trạng thái giỏ

Lưu thành tệp **`CommandPayloadRecordDemo.java`**:

~~~java
import java.util.*;

public class CommandPayloadRecordDemo {
    sealed interface Payload
            permits CreateCart, AddProducts, Checkout, CancelCart {}

    static String requireText(String text, String name) {
        if (text == null || text.isBlank())
            throw new IllegalArgumentException(
                    name + " không được trống");
        return text.strip();
    }

    record CreateCart(String cartId) implements Payload {
        public CreateCart {
            cartId = requireText(cartId, "cartId");
        }
    }

    record Line(String sku, int quantity) {
        public Line {
            sku = requireText(sku, "sku");
            if (quantity <= 0)
                throw new IllegalArgumentException(
                        "quantity phải > 0");
        }
    }

    record AddProducts(String cartId, List<Line> lines)
            implements Payload {
        public AddProducts {
            cartId = requireText(cartId, "cartId");
            lines = List.copyOf(
                    Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty())
                throw new IllegalArgumentException(
                        "lines không được rỗng");
        }
    }

    record Checkout(String cartId) implements Payload {
        public Checkout {
            cartId = requireText(cartId, "cartId");
        }
    }

    record CancelCart(String cartId, String reason)
            implements Payload {
        public CancelCart {
            cartId = requireText(cartId, "cartId");
            reason = requireText(reason, "reason");
        }
    }

    record Envelope(String requestId, String actorId, Payload payload) {
        public Envelope {
            requestId = requireText(requestId, "requestId");
            actorId = requireText(actorId, "actorId");
            Objects.requireNonNull(payload, "payload");
        }
    }

    enum Status { DRAFT, CHECKED_OUT, CANCELLED }

    record Cart(String id, String ownerId,
                List<Line> lines, Status status) {
        public Cart {
            id = requireText(id, "id");
            ownerId = requireText(ownerId, "ownerId");
            lines = List.copyOf(
                    Objects.requireNonNull(lines, "lines"));
            Objects.requireNonNull(status, "status");
        }
    }

    static final class Handler {
        private final Map<String, Cart> carts = new HashMap<>();

        String apply(Envelope envelope) {
            Objects.requireNonNull(envelope, "envelope");

            String detail = switch (envelope.payload()) {
                case CreateCart(var id) -> {
                    if (carts.containsKey(id))
                        throw new IllegalStateException(
                                "Giỏ đã tồn tại: " + id);

                    carts.put(id, new Cart(
                            id, envelope.actorId(),
                            List.of(), Status.DRAFT));
                    yield "Tạo giỏ " + id;
                }

                case AddProducts(var id, var newLines) -> {
                    Cart cart = requireDraftOwner(
                            id, envelope.actorId());

                    List<Line> combined =
                            new ArrayList<>(cart.lines());
                    combined.addAll(newLines);
                    carts.put(id, new Cart(
                            id, cart.ownerId(),
                            combined, Status.DRAFT));

                    yield "Thêm " + newLines.size()
                            + " dòng vào " + id;
                }

                case Checkout(var id) -> {
                    Cart cart = requireDraftOwner(
                            id, envelope.actorId());
                    if (cart.lines().isEmpty())
                        throw new IllegalStateException("Giỏ rỗng");

                    carts.put(id, new Cart(
                            id, cart.ownerId(),
                            cart.lines(), Status.CHECKED_OUT));
                    yield "Thanh toán " + id;
                }

                case CancelCart(var id, var reason) -> {
                    Cart cart = requireDraftOwner(
                            id, envelope.actorId());
                    carts.put(id, new Cart(
                            id, cart.ownerId(),
                            cart.lines(), Status.CANCELLED));

                    yield "Hủy giỏ " + id + ": " + reason;
                }
            };

            return envelope.requestId() + ": " + detail;
        }

        private Cart requireDraftOwner(String id, String actorId) {
            Cart cart = carts.get(id);
            if (cart == null)
                throw new IllegalStateException(
                        "Không tìm thấy giỏ: " + id);
            if (!cart.ownerId().equals(actorId))
                throw new SecurityException("Không có quyền");
            if (cart.status() != Status.DRAFT)
                throw new IllegalStateException(
                        "Giỏ không ở DRAFT");
            return cart;
        }

        Cart find(String id) {
            return Objects.requireNonNull(carts.get(id), "cart");
        }
    }

    public static void main(String[] args) {
        Handler handler = new Handler();

        List<Line> mutable = new ArrayList<>();
        mutable.add(new Line("SACH", 2));
        AddProducts add = new AddProducts(" C-1 ", mutable);
        mutable.add(new Line("BUT", 4));

        System.out.println(
                "Dòng trong payload: " + add.lines().size());

        System.out.println(handler.apply(new Envelope(
                "R-1", "U-1", new CreateCart(" C-1 "))));
        System.out.println(handler.apply(new Envelope(
                "R-2", "U-1", add)));
        System.out.println(handler.apply(new Envelope(
                "R-3", "U-1", new Checkout("C-1"))));

        System.out.println(handler.find("C-1").status()
                + " / " + handler.find("C-1").lines().size());

        try {
            handler.apply(new Envelope("R-4", "U-1",
                    new AddProducts("C-1",
                            List.of(new Line("BUT", 1)))));
        } catch (IllegalStateException e) {
            System.out.println(
                    "Lỗi nghiệp vụ: " + e.getMessage());
        }

        try {
            new Line("SAI", 0);
        } catch (IllegalArgumentException e) {
            System.out.println(
                    "Lỗi dữ liệu: " + e.getMessage());
        }

        System.out.println(handler.apply(new Envelope(
                "R-5", "U-2", new CreateCart("C-2"))));

        try {
            handler.apply(new Envelope("R-6", "U-99",
                    new AddProducts("C-2",
                            List.of(new Line("SACH", 1)))));
        } catch (SecurityException e) {
            System.out.println(
                    "Lỗi quyền: " + e.getMessage());
        }

        System.out.println(handler.apply(new Envelope(
                "R-7", "U-2",
                new CancelCart("C-2", " Đổi ý "))));

        System.out.println(handler.find("C-2").status());
        System.out.println("Payload bằng nhau: "
                + add.equals(new AddProducts(
                        "C-1", List.of(new Line("SACH", 2)))));
    }
}
~~~

Biên dịch và chạy bằng JDK 21 trở lên:

~~~bash
javac --release 21 -encoding UTF-8 CommandPayloadRecordDemo.java
java CommandPayloadRecordDemo
~~~

Đầu ra:

~~~text
Dòng trong payload: 1
R-1: Tạo giỏ C-1
R-2: Thêm 1 dòng vào C-1
R-3: Thanh toán C-1
CHECKED_OUT / 1
Lỗi nghiệp vụ: Giỏ không ở DRAFT
Lỗi dữ liệu: quantity phải > 0
R-5: Tạo giỏ C-2
Lỗi quyền: Không có quyền
R-7: Hủy giỏ C-2: Đổi ý
CANCELLED
Payload bằng nhau: true
~~~

### 9.1. Vì sao 12 dòng đầu ra có ý nghĩa?

- **`Dòng trong payload: 1`:** source `ArrayList` được thêm phần tử sau khi payload tạo, nhưng `AddProducts.lines` vẫn có một dòng nhờ `List.copyOf`.
- **`R-1...R-3`:** ba request metadata khác nhau bao quanh payload tương ứng. `cartId` được `strip()` nên " C-1 " và "C-1" cùng một ID logic.
- **`CHECKED_OUT / 1`:** handler đã cập nhật giỏ qua immutable state snapshot, không sửa trực tiếp record cũ.
- **`Lỗi nghiệp vụ`:** payload `AddProducts` hợp lệ nhưng không thể áp dụng trên giỏ đã `CHECKED_OUT`.
- **`Lỗi dữ liệu`:** `Line("SAI", 0)` bị constructor từ chối **trước** khi vào handler.
- **`Lỗi quyền`:** kiểm tra actor không trùng owner trong handler demo; đây chỉ là minh họa **sau khi đã giả định actorId đến từ nguồn tin cậy**.
- **`R-7...CANCELLED`:** cùng kiểu envelope dùng được cho payload hủy giỏ.
- **`Payload bằng nhau: true`:** record `AddProducts` so sánh theo component; hai `Line` giống giá trị và hai list cùng nội dung nên bằng nhau.

### 9.2. Những gì demo cố tình không triển khai

Đây là mô phỏng **in-memory**, không phải hệ thống đặt hàng production:

- Không có HTTP/JSON serializer, message broker hoặc API thực.
- Không xác thực actorId bằng token/session: `Envelope.actorId` được đưa trực tiếp từ code test.
- Không có database, transaction, optimistic locking hoặc đảm bảo an toàn khi nhiều thread cùng cập nhật.
- Không kiểm tra tồn kho, giá tiền, ngân sách, hoặc các quy tắc xử lý nghiệp vụ đầy đủ.
- Không chống xử lý trùng `requestId`. Câu `R-1` chỉ là mã correlation trong demo, không phải idempotency key được hệ thống thực thi.
- Không phát domain event hay lưu audit log. Chuỗi "Thanh toán ..." chỉ là **kết quả handler**, chưa phải bằng chứng một payment gateway đã thanh toán tiền.

Hãy giữ các giới hạn này khi áp dụng ý tưởng ra môi trường thật.

## 10. Payload không đồng nghĩa domain aggregate hoặc event

### 10.1. Payload là yêu cầu

~~~java
new Checkout("C-1")
~~~

Payload này không chứa toàn bộ thông tin giỏ, vì nó chỉ cần định danh aggregate để yêu cầu checkout.

### 10.2. State là sự thật hiện tại của aggregate

~~~java
record Cart(String id, String ownerId,
            List<Line> lines, Status status) {}
~~~

Trong demo, `Cart` là immutable state snapshot. Ứng dụng production có thể sử dụng entity/class domain model giàu hành vi hơn, persistence mapping hoặc event-sourced aggregate; không nên chọn record làm entity chỉ vì ngắn.

### 10.3. Event là điều đã xảy ra

~~~java
record CartCheckedOut(String cartId, String actorId) {}
~~~

Một event như trên nên chỉ được tạo/phát **sau khi** handler đã thành công và hoàn thành các yêu cầu transaction/outbox phù hợp. Một `Checkout` command thất bại không được tự động biến thành `CartCheckedOut`.

**Quy tắc thiết kế:** command thường đặt tên **động từ yêu cầu**, event đặt tên mô tả **kết quả đã xảy ra**. Hai message có thể có data giống nhau ở một vài field nhưng có semantics, timing, retry và nguồn tin cậy khác nhau.

## 11. Mẫu payload quá rộng dễ gây lỗi gì?

Một anti-pattern phổ biến:

~~~java
// Anti-pattern minh họa: một kiểu có quá nhiều trường không liên quan.
record MegaCommand(
        String type,
        String cartId,
        String sku,
        Integer quantity,
        List<Line> lines,
        String reason,
        String requestId) {}
~~~

Nếu `type == "CHECKOUT"`, nhiều field trở thành null hoặc bị bỏ qua; nếu `type == "ADD"`, field `reason` vô nghĩa. Khi thêm command mới, số tổ hợp không hợp lệ tăng và validation dựa trên chuỗi trở nên khó kiểm soát.

Tách thành records cho từng intent:

~~~java
sealed interface Payload permits CreateCart, AddProducts, Checkout, CancelCart {}
record CreateCart(String cartId) implements Payload {}
record Checkout(String cartId) implements Payload {}
record CancelCart(String cartId, String reason) implements Payload {}
record AddProducts(String cartId, List<Line> lines) implements Payload {}
~~~

Các khai báo trên là hình dạng API không kèm implementation chi tiết; xem mã đã validate ở mục 9.

**Trade-off:** mỗi command type tăng số lớp/record cần quản lý. Điều này đáng giá khi nghiệp vụ có các cấu trúc khác nhau; với một tool nhỏ có một operation, không nhất thiết phải tạo sealed hierarchy.

## 12. Từ JSON/API đến record payload: ranh giới deserialize

Một yêu cầu từ bên ngoài có thể có cấu trúc JSON như sau:

~~~json
{
  "requestId": "R-2",
  "type": "ADD_PRODUCTS",
  "payload": {
    "cartId": "C-1",
    "lines": [{ "sku": "SACH", "quantity": 2 }]
  }
}
~~~

Đây chỉ là **ví dụ schema của transport**, không phải mã Java chạy được. Khi nhận nó:

1. Parser/serializer đọc JSON và kiểm tra cấu trúc, kiểu số, trường bắt buộc, kích thước tối đa của collection.
2. Adapter ánh xạ trường `type` sang subtype payload cụ thể, ví dụ `"ADD_PRODUCTS" -> AddProducts`.
3. Tạo các `Line` và `AddProducts` bằng canonical constructors, để invariant nội tại được kiểm tra.
4. Xác thực người gửi và thiết lập `actorId` từ **context tin cậy**; không tin một `actorId` tự khai trong payload.
5. Tạo `Envelope(requestId, trustedActorId, payload)` và đưa vào handler.
6. Handler kiểm tra quyền/nghiệp vụ rồi cập nhật state trong transaction thích hợp.
7. Chuyển kết quả hoặc exception sang response/error code rõ, không lộ thông tin nội bộ nhạy cảm.

Một hàm mapping giản lược để thấy ý tưởng:

~~~java
// Pseudocode Java: không phải hàm độc lập, phụ thuộc DTO/parser.
// Payload payload = switch (dto.type()) {
//     case "CREATE_CART" -> new CreateCart(dto.cartId());
//     case "ADD_PRODUCTS" -> new AddProducts(
//             dto.cartId(), mapValidatedLines(dto.lines()));
//     case "CHECKOUT" -> new Checkout(dto.cartId());
//     case "CANCEL_CART" -> new CancelCart(
//             dto.cartId(), dto.reason());
//     default -> throw new IllegalArgumentException("Unknown type");
// };
~~~

**Không có quy tắc** mọi JSON library tự động khôi phục sealed subtype/record payload mà không cần cấu hình polymorphic mapping hoặc discriminator. Tùy Jackson, JSON-B hay framework khác, cần đọc tài liệu version và kiểm tra tính tương thích của constructor, field names, unknown properties và validation.

### Boundary validation không chỉ là record constructor

Một payload có thể hợp lệ theo Java types nhưng vẫn không an toàn để xử lý:

- Chuỗi dài hàng triệu ký tự gây quá tải.
- Collection cực lớn làm tăng thời gian/memory.
- ID có định dạng sai hoặc chứa ký tự không mong muốn.
- Request giả actorId khác nếu boundary không xác thực.
- Trường unknown bị bỏ qua làm client tưởng rằng một tính năng đã được áp dụng.
- Integer overflow, giá trị cực lớn hoặc số âm vượt quy tắc chi tiết.

Hãy xác định max-size, schema version, kiểm tra trường bắt buộc và phân quyền tại **ranh giới phù hợp**, thay vì nghĩ record đã giải quyết hết.

## 13. Idempotency: record equality và requestId không đủ

Record tạo `equals()` theo component, nhưng **value equality không đồng nghĩa xử lý exactly-once**. Ví dụ:

~~~java
AddProducts a = new AddProducts(
        "C-1", List.of(new Line("SACH", 2)));
AddProducts b = new AddProducts(
        "C-1", List.of(new Line("SACH", 2)));

System.out.println(a.equals(b)); // true
~~~

Hai object bằng nhau theo giá trị, nhưng chúng có thể là **hai yêu cầu thêm hàng hợp lệ khác nhau**; không thể mặc định bỏ qua lần thứ hai vì `equals() == true`.

Ngay cả envelope có `requestId`:

~~~java
record Envelope(String requestId, String actorId, Payload payload) {}
~~~

việc chứa field này chưa tự làm hệ thống idempotent. Trong production, nếu client retry do timeout hoặc broker phát lại message, cần chính sách như:

- Một idempotency key ổn định qua retry của **cùng một yêu cầu logic**.
- Phạm vi duy nhất rõ ràng, ví dụ theo tenant/actor/operation.
- Lưu kết quả hoặc trạng thái đã xử lý cùng transaction/unique constraint phù hợp.
- Định nghĩa hành vi khi cùng key nhưng payload khác nhau.
- Chiến lược xử lý concurrent duplicate requests.
- Thời hạn lưu và semantics của response khi gặp duplicate.

Demo dùng `requestId` để **ghi nhãn kết quả** và không có cơ chế lưu/truy vấn key, nên **không** được xem là minh chứng về idempotency hoặc exactly-once delivery.

## 14. Schema evolution: thêm component làm thay đổi hợp đồng

Giả sử ban đầu:

~~~java
record CreateCart(String cartId) implements Payload {}
~~~

Sau đó business yêu cầu thêm currency:

~~~java
record CreateCart(String cartId, String currency) implements Payload {}
~~~

Đây không chỉ là sửa hiển thị; thay đổi header record có thể ảnh hưởng:

- Canonical constructor signature và code gọi tại compile time.
- Record components và accessor được expose.
- `equals()`, `hashCode()` và `toString()`.
- Deserialization/serialization schema của message.
- Record patterns `case CreateCart(var cartId)` nay **sai số component** nếu không cập nhật.
- Các message cũ đang nằm trong queue hoặc lưu để replay.

**Chiến lược khuyến nghị:**

1. Ghi rõ phiên bản contract ở API/message schema, không suy đoán chỉ từ Java class name.
2. Có **adapter/migrator** chuyển bản tin cũ sang payload nội bộ hiện tại nếu yêu cầu backward compatibility.
3. Đặt default có kiểm soát khi business cho phép; không tự gán currency hay tenant làm phát sinh hành vi sai.
4. Test round-trip với serializer và fixture cho cả phiên bản cũ/mới.
5. Khi đổi subtype trong sealed hierarchy, xem lại tất cả exhaustive pattern switches.
6. Phân biệt **model tiến hóa trong process** với **schema trao đổi qua mạng/queue**; chúng có chu kỳ triển khai không giống nhau.

Không nên chỉ thêm component rồi tin rằng record tự backward compatible với mọi client/producer cũ.

## 15. Pattern matching trên payload: lợi ích và giới hạn

### Lợi ích

- Mỗi case được kiểm tra kiểu, tách component rõ ràng.
- Hạn chế cast thủ công và chuỗi `if (type.equals(...))`.
- Với hierarchy sealed, compiler giúp phát hiện chỗ chưa xử lý subtype.
- `when` có thể diễn đạt điều kiện phân nhánh đơn giản trên dữ liệu đã match.
- Record patterns lồng nhau thuận tiện khi payload có nested record cấu trúc rõ.

### Cần thận trọng

- Record pattern chỉ match theo cấu trúc record, **không chạy lại constructor** để validate.
- Guard có thể gây side effect nếu bạn gọi service/mutation trong `when`; nên giữ guard đơn giản và thuần nếu có thể.
- Nested pattern `case SomePayload(NestedRecord(...))` không khớp khi component chứa nested record bằng null; cần fallback/validation nếu null là dữ liệu hợp lệ.
- `case null` xử lý selector null, **không** bắt tất cả field/component null bên trong record.
- Type erasure làm generic argument không luôn kiểm chứng được ở runtime, ví dụ `Object` không thể tùy ý bị kiểm tra thành `Box<String>` có tham số cụ thể.
- Dispatch một hành vi cốt lõi bằng switch trên mọi implementation đôi khi tăng coupling so với polymorphism. Chọn cấu trúc đúng trách nhiệm, không áp dụng pattern chỉ vì cú pháp mới.
- Lỗi compiler về dominance, arity và exhaustiveness là tín hiệu quan trọng cần sửa; thêm `default` tùy tiện có thể che subtype mới.

## 16. Test matrix cho command payload

Các test nên đi qua **ba tầng**:

### Tầng A — payload constructor/invariant

| Input | Kỳ vọng |
| --- | --- |
| `CreateCart(null)` | Từ chối với `IllegalArgumentException` |
| `CreateCart("   ")` | Từ chối |
| `CreateCart(" C-1 ")` | Chuẩn hóa thành `"C-1"` |
| `Line("SACH", 0)` | Từ chối `quantity <= 0` |
| `AddProducts("C-1", List.of())` | Từ chối danh sách rỗng |
| `AddProducts("C-1", null)` | Từ chối reference null |
| `AddProducts("C-1", listMutable)` rồi mutate list | Payload đã tạo không thay đổi |
| `Envelope("R-1", "U-1", null)` | Từ chối null payload |

### Tầng B — handler/domain rules

| Trạng thái và yêu cầu | Kỳ vọng |
| --- | --- |
| Tạo giỏ mới | Tạo `DRAFT` thành công |
| Tạo ID giỏ đã tồn tại | Từ chối trùng ID theo policy |
| Thêm hàng vào giỏ `DRAFT` cùng owner | Thành công |
| Checkout giỏ `DRAFT` nhưng rỗng | Từ chối |
| Checkout giỏ có hàng | Chuyển sang `CHECKED_OUT` |
| Thêm hàng sau checkout | Từ chối do state |
| Actor khác owner cố sửa giỏ | Từ chối quyền |
| Hủy giỏ `DRAFT` đúng owner | Chuyển sang `CANCELLED` |
| Hủy một giỏ đã `CANCELLED` | Từ chối hoặc trả kết quả theo policy đã chốt |

### Tầng C — API/message boundary

| Test | Mục đích |
| --- | --- |
| Không có `type` hoặc `type` không biết | Không tạo sai subtype |
| JSON thiếu field bắt buộc | Phát hiện lỗi schema/validation |
| Collection quá lớn | Giới hạn tài nguyên |
| Request dùng actorId tự khai khác danh tính xác thực | Không vượt qua ủy quyền |
| Message phiên bản cũ | Backward compatibility theo chính sách |
| Gửi lại cùng requestId | Kiểm tra idempotency **nếu hệ thống có triển khai** |
| Hai request đồng thời trên một giỏ | Kiểm tra transaction/concurrency |
| Serializer round-trip | Bảo toàn subtype, field và dữ liệu Unicode |

Đừng chỉ test “mỗi `case` được chạy một lần”. Với `when`, cần test guard đúng/sai, các đường short-circuit của `&&`/`||`, null selector và null component. Coverage tool chỉ hỗ trợ quan sát đường code, không chứng minh tất cả invariant.

## 17. Các lỗi thường gặp khi đưa payload record vào ứng dụng

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Payload và state entity là cùng một class/record | Nhầm yêu cầu với trạng thái có vòng đời | Tách payload và aggregate |
| Payload chứa `Repository`, `Connection` hoặc service | Coupling hạ tầng, khó serialize/test | Giữ record là dữ liệu; handler dùng dependency |
| Đưa `actorId` từ client vào rồi tin ngay | Có thể sửa dữ liệu người khác | Lấy principal đáng tin từ auth context |
| Chỉ kiểm tra `cartId` trong handler, tạo record sai tự do | Thông điệp không có invariant ổn định | Validate cấu trúc ngay khi tạo |
| Cho rằng `final` làm `List` bất biến sâu | Payload có thể đổi sau khi enqueue | Defensive copy và immutable elements |
| Dùng một `MegaCommand` có vô số field nullable | Nhiều tổ hợp dữ liệu không hợp lệ | Tách record theo từng intent |
| Cho rằng `requestId` là idempotency | Gửi trùng vẫn có thể chạy nhiều lần | Thiết kế dedup bền vững |
| Tưởng `record.equals` giúp chống duplicate | Hai yêu cầu giống dữ liệu có thể đều hợp lệ | Tách value equality khỏi business idempotency |
| Thêm component vào record mà không cập nhật consumer | Constructor/pattern/schema có thể hỏng | Versioning, adapter, contract tests |
| Dùng `default` trong sealed switch cho mọi subtype mới | Có thể che thiếu xử lý use case mới | Tận dụng exhaustive switch |
| Dùng `case null` và nghĩ mọi component đều non-null | NPE bên trong case | Kiểm tra component/constructor invariant |
| Tin `switch` là bước kiểm tra quyền | Case chỉ chọn kiểu, không xác thực actor | Authorize ở handler/domain |
| Mọi payload xử lý bằng map không khóa | Race, lost update | Transaction/versioning/concurrency control |
| Log cả payload nguyên văn chứa secret | Rò rỉ dữ liệu | Redaction và logging policy |
| Dùng record chỉ vì ngắn dù cần entity mutable/proxy ORM | Không phù hợp vòng đời/identity | Chọn domain class phù hợp |

## 18. Code review checklist cho payload record

Một PR thêm/sửa command payload nên được review theo checklist:

- [ ] Payload class có **tên theo intent**, component tối thiểu nhưng đủ dữ liệu nghiệp vụ.
- [ ] Metadata transport/request được để trong envelope/context hợp lý, không trộn không cần thiết với payload.
- [ ] Record constructors kiểm tra non-null, blank, range, collection size và invariant nội tại.
- [ ] Mutable nested data được sao chép phòng vệ; record elements có semantics bất biến phù hợp.
- [ ] Caller không thể mutate payload sau khi gửi chỉ thông qua alias vào collection.
- [ ] Sealed hierarchy và pattern switch exhaustive đúng theo phạm vi API.
- [ ] Record patterns đúng **thứ tự và số component**, guard không có side effect ngoài dự kiến.
- [ ] Selector null và nullable components có chính sách rõ.
- [ ] Handler kiểm tra existence, authorization và state; không đặt nghiệp vụ phụ thuộc DB vào constructor.
- [ ] Có test phân biệt **lỗi dữ liệu**, **lỗi quyền** và **lỗi trạng thái**.
- [ ] requestId/correlation ID không bị quảng cáo là idempotency nếu chưa triển khai.
- [ ] JSON/schema version, backward compatibility, concurrency và error mapping được xem xét nếu command đi qua network/queue.
- [ ] Thông tin nhạy cảm không bị log thô qua `toString()`.
- [ ] Có test đầy đủ ở boundary + handler, không chỉ một ví dụ `new Record(...)`.

Checklist giúp giữ ranh giới rõ giữa **command payload là dữ liệu** và **handler là nơi thực thi ý định**.

## 19. Bài tập và đáp án gợi ý

**Bài 1 — Thiết kế payload.** Thêm yêu cầu `ApplyCoupon(cartId, couponCode)` vào hệ thống. Những field nào thuộc payload? Nếu cần requestId/actorId, đặt ở đâu? Thay đổi nào cần có trong sealed hierarchy và handler?

**Bài 2 — Defensive copy.** Với `record Batch(List<Line> lines) {}`, hãy viết compact constructor chống việc nguồn list bị mutate sau khi record được tạo. `List.copyOf` có bảo vệ khi phần tử là `Line` mutable không?

**Bài 3 — Validation vs domain rule.** Vì sao `quantity > 0` nên kiểm tra khi tạo `Line`, còn `cart.status() == DRAFT` nên kiểm tra ở handler? Nếu đặt cả hai trong payload constructor sẽ có vấn đề gì?

**Bài 4 — Idempotency.** Client gửi hai request `AddProducts` cùng cartId/lines nhưng **requestId khác nhau**. `equals()` của payload có thể là `true`. Hệ thống có nên tự bỏ request thứ hai không? Nếu client retry cùng requestId sau timeout thì cần hệ thống hỗ trợ gì?

**Bài 5 — Versioning.** Thêm `currency` vào `CreateCart`. Những tác động đối với constructor, record pattern, serializer và consumer cũ cần được xét?

**Bài 6 — Permission.** Một client gửi `Envelope("R-10", "ADMIN", payload)`. Điều gì khiến `actorId == "ADMIN"` trong record **không** phải bằng chứng có quyền? Hãy mô tả cách dùng principal đã xác thực để tạo envelope ở boundary.

**Gợi ý:**

~~~java
// Bài 1: sketch trong cùng hierarchy:
record ApplyCoupon(String cartId, String couponCode)
        implements Payload {
    public ApplyCoupon {
        cartId = requireText(cartId, "cartId");
        couponCode = requireText(couponCode, "couponCode");
    }
}

// Bài 2:
record Batch(List<Line> lines) {
    public Batch {
        lines = List.copyOf(Objects.requireNonNull(lines));
    }
}
~~~

- Bài 1: payload chứa `cartId` và `couponCode`; requestId/actorId là metadata thích hợp cho envelope/context. Thêm `ApplyCoupon` vào `permits` và thêm nhánh dispatch; handler còn phải kiểm tra trạng thái giỏ và tính hợp lệ coupon theo nghiệp vụ.
- Bài 2: `List.copyOf` bảo vệ **cấu trúc list** chứ không deep-copy phần tử mutable. Trong demo `Line` là record đơn giản, nên an toàn hơn.
- Bài 3: quantity là invariant dữ liệu độc lập; state cần đọc giỏ hiện tại và có thể thay đổi theo thời gian, không nên buộc payload constructor truy cập repository.
- Bài 4: không tự dedup theo payload equality; cần idempotency key có semantic được định nghĩa và lưu kết quả/trạng thái xử lý bền vững nếu nghiệp vụ yêu cầu.
- Bài 5: constructor signature, pattern arity, wire schema và back-compat đều cần cập nhật/migration.
- Bài 6: actorId từ client có thể giả mạo. Xác thực principal bằng nguồn tin cậy rồi xây envelope hoặc truyền principal vào handler qua context server-side.

## 20. Tổng kết

Biểu diễn **command payload bằng record** tốt khi:

1. **Payload chỉ là dữ liệu của ý định nghiệp vụ**, không chứa service, transaction hoặc mutable entity.
2. **Constructor bảo vệ invariant nội tại**; `List.copyOf` và immutable element records giúp tránh aliasing ngoài ý muốn.
3. **Envelope tách metadata khỏi payload**; thông tin danh tính cần đến từ nguồn xác thực đáng tin.
4. **Sealed hierarchy + record pattern switch** giúp phân phối type-safe và tận dụng exhaustiveness trong Java 21.
5. **Handler áp dụng nghiệp vụ lên state**: kiểm tra quyền, trạng thái, resource existence, transaction/concurrency.
6. **Test các trường hợp bình thường và thất bại**, không đánh đồng value equality, correlation ID và idempotency.
7. **Version wire schema có chủ đích**, đặc biệt khi thêm record components hoặc subtype mới.

### Tài liệu tham khảo

- [JEP 395 — Records](https://openjdk.org/jeps/395): semantics record class, component/accessor/constructor và value-oriented data.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): giới hạn tập subtype của interface.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): deconstruction record trong pattern matching (Java 21).
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): switch pattern, `case null` và exhaustiveness (Java 21).
- [Oracle Java 21 — Record Classes](https://docs.oracle.com/en/java/javase/21/language/records.html).
- [Oracle Java 21 — Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html).
- [Java SE 21 List.copyOf API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
