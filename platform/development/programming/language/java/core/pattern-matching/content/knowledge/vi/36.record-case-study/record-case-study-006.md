# Kết hợp order record với sealed event

## 1. Bài toán: Order là trạng thái, event là sự kiện đã xảy ra

Trong ứng dụng đặt hàng, ta thường cần lưu trạng thái hiện tại của một đơn hàng (*order*) và giải thích vì sao trạng thái ấy thay đổi. Java 21 cho phép mô hình hóa hai vai trò đó bằng hai công cụ bổ sung:

- **`record Order`:** một *snapshot* bất biến, mô tả trạng thái hiện tại của đơn hàng: mã đơn, mặt hàng, tổng tiền, trạng thái, phiên bản/sequence và mã vận chuyển nếu có.
- **`sealed interface OrderEvent`:** tập các loại sự kiện mà domain sở hữu, ví dụ `OrderPlaced`, `PaymentCaptured`, `ParcelShipped` và `OrderCancelled`. Mỗi subtype là một record chứa dữ liệu riêng của sự kiện.
- **Pattern matching for `switch`:** phân loại từng event, lấy component bằng record pattern, kiểm tra điều kiện nghiệp vụ và tạo **Order mới** thay vì sửa trực tiếp snapshot cũ.

Ý tưởng luồng dữ liệu:

```text
OrderPlaced(id, item, seq=1)  ──>  Order(state=PLACED, seq=1)
PaymentCaptured(id, seq=2)    ──>  Order(state=PAID, seq=2)
ParcelShipped(id, code, seq=3)──>  Order(state=SHIPPED, seq=3)
```

Trong sơ đồ trên, mũi tên biểu thị việc **áp dụng một event hợp lệ lên snapshot** để tạo snapshot tiếp theo. Đây là một **event projector/reducer nhỏ** minh họa; chưa phải hệ thống event sourcing đầy đủ.

**Phân biệt quan trọng:** `CapturePayment` (command) là yêu cầu thu tiền và có thể thất bại; `PaymentCaptured` (event) khẳng định việc thu tiền đã xảy ra theo nguồn sự kiện đáng tin. Vì thế, hàm `apply` trong bài **không gọi cổng thanh toán, không gửi hàng và không ghi database**. Nó chỉ cập nhật cách biểu diễn trạng thái từ những sự kiện đã được chấp nhận.

Mục tiêu học tập là kết hợp đúng **record + sealed hierarchy + record pattern + state transition** mà vẫn bảo toàn dữ liệu và xử lý các trường hợp sai.

## 2. Thiết kế dữ liệu Order bất biến

Một record có thể biểu diễn mặt hàng:

```java
record Item(String sku, int quantity, long unitPriceCents) {
    long subtotalCents() {
        return Math.multiplyExact((long) quantity, unitPriceCents);
    }
}
```

Đây là đoạn minh họa khai báo, chưa có constructor validation. `sku` là mã hàng; `quantity` là số lượng; `unitPriceCents` biểu diễn giá tiền bằng đơn vị nhỏ nhất (ví dụ cent) thay vì dùng `double` để cộng tiền.

Chọn `long` thay vì `double` cho ví dụ tiền tệ này giúp tránh một số sai số nhị phân khi cộng các khoản tiền nguyên theo đơn vị nhỏ nhất. Nó **không** tự giải quyết tiền tệ nhiều loại, làm tròn thuế, tỷ giá hoặc việc vượt phạm vi `long`. Với hệ thống tài chính phức tạp, `BigDecimal`, tiền tệ và quy tắc rounding có thể cần được mô hình hóa rõ hơn.

Trạng thái đơn hàng:

```java
enum State {
    PLACED, PAID, SHIPPED, CANCELLED
}
```

Snapshot:

```java
record Order(
        String id,
        Item item,
        State state,
        long totalCents,
        long sequence,
        String trackingCode) {}
```

Một đối tượng `Order` đại diện cho **một trạng thái cụ thể**. Khi nhận event tiếp theo, chương trình tạo một `Order` mới có component được cập nhật.

Ví dụ logic chuyển từ `PLACED` sang `PAID`:

```java
Order paid = new Order(
        previous.id(),
        previous.item(),
        State.PAID,
        previous.totalCents(),
        nextSequence,
        null);
```

Đây là snippet minh họa: giả định `previous` đã tồn tại, `nextSequence` hợp lệ và các kiểu được khai báo. Record không có setter tự động; việc thay đổi dữ liệu được biểu diễn bằng **giá trị mới**.

### Bất biến không đồng nghĩa “mọi thứ bên trong đều immutable”

Record có các component field là `final`, nhưng một component tham chiếu vẫn có thể trỏ tới **object mutable**. Trong bài, `Item` cũng là record chỉ chứa `String` và kiểu nguyên thủy, nên mô hình dữ liệu dễ giữ ổn định. Nếu một `Order` chứa `List<MutableItem>`, chỉ dùng record **không đủ để bảo đảm deep immutability**; cần tạo bản sao bảo vệ và/hoặc dùng object bất biến.

### Trạng thái được quản lý trong domain

Case study định nghĩa:

- `PLACED`: đã tạo đơn nhưng chưa xác nhận thanh toán.
- `PAID`: đã ghi nhận thanh toán.
- `SHIPPED`: đã giao cho đơn vị vận chuyển; có tracking code.
- `CANCELLED`: đã hủy trước khi giao hàng.

Việc có được hủy sau thanh toán hay không là quyết định nghiệp vụ. Bài này **cho phép hủy ở PLACED hoặc PAID**, nhưng không cho hủy sau SHIPPED. Nếu domain cần hoàn tiền khi hủy đơn đã thanh toán, quá trình hoàn tiền là hành vi ngoài projector và phải có command/event riêng; chỉ đổi enum sang CANCELLED không có nghĩa tiền đã hoàn.

## 3. Sealed event định nghĩa tập biến thể được cho phép

Hệ thống có bốn loại event:

```java
sealed interface OrderEvent
        permits OrderPlaced, PaymentCaptured,
                ParcelShipped, OrderCancelled {}

record OrderPlaced(String orderId, Item item, long sequence)
        implements OrderEvent {}

record PaymentCaptured(String orderId, long sequence)
        implements OrderEvent {}

record ParcelShipped(
        String orderId, String trackingCode, long sequence)
        implements OrderEvent {}

record OrderCancelled(
        String orderId, String reason, long sequence)
        implements OrderEvent {}
```

Đây là các khai báo minh họa. Chương trình đầy đủ ở phần 8 bổ sung validation cho mỗi event.

**Vì sao `sealed interface` có ích ở đây?**

1. Module sở hữu domain **liệt kê rõ các subtype trực tiếp được phép**.
2. Các record implement trực tiếp đều là `final`, nên tập hình thức event ở ví dụ được kiểm soát.
3. `switch expression` trên `OrderEvent` có thể được compiler Java 21 kiểm tra **exhaustiveness**: nếu thêm subtype mới mà chưa xử lý, compiler có cơ hội báo thiếu case khi biên dịch lại.
4. Nhờ mỗi event là một record khác nhau, `ParcelShipped` phải mang tracking code, còn `PaymentCaptured` không cần tạo ra một record chung chứa nhiều field tùy chọn không liên quan.

Trong named module, subtype trực tiếp được permitted phải ở **cùng module**; trong unnamed module, chúng phải ở **cùng package** với sealed interface. Đặt các loại record lồng trong cùng một lớp như ví dụ độc lập cũng phù hợp với mục đích giảng dạy.

**Không có nghĩa sealed event tự bảo đảm mọi event là thật.** Java type system không xác thực chữ ký, nguồn phát event, thời điểm nghiệp vụ hoặc quyền của người gửi. Nếu event đi từ một nguồn không đáng tin, cần có boundary để xác thực trước khi đưa vào projector.

### Vì sao sequence nằm trong mỗi event?

`sequence` biểu diễn thứ tự dự kiến **trong cùng một đơn hàng**. Trong mô hình đơn giản:

- Event đầu tiên phải có sequence `1`.
- Event tiếp theo phải có sequence bằng `current.sequence() + 1`.
- Một event thuộc đơn khác không được áp dụng lên snapshot hiện tại.

Quy tắc này giúp phát hiện **thiếu event, event đến sai thứ tự, lặp sequence hoặc trộn nhầm order**. Nó không tự cung cấp khóa phân tán hay bảo đảm exactly-once delivery.

## 4. Record pattern giải cấu trúc event ngay trong switch

Từ Java 21, có thể dùng pattern matching for `switch` để áp dụng các event:

```java
static Order apply(Order current, OrderEvent event) {
    return switch (event) {
        case OrderPlaced(var id, var item, long seq)
                when current == null -> {
            // Kiểm tra seq đầu tiên, rồi tạo Order PLACED.
            yield createSnapshot(id, item, seq);
        }

        case OrderPlaced placed ->
                throw new IllegalStateException(
                        "Order already exists: " + placed.orderId());

        case PaymentCaptured(var id, long seq) ->
                applyPayment(current, id, seq);

        case ParcelShipped(var id, var tracking, long seq) ->
                applyShipment(current, id, tracking, seq);

        case OrderCancelled(var id, var reason, long seq) ->
                applyCancellation(current, id, reason, seq);

        case null ->
                throw new IllegalArgumentException(
                        "event must not be null");
    };
}
```

Đây là **ví dụ minh họa cấu trúc**, không phải phương thức độc lập có thể biên dịch ngay: các hàm `createSnapshot`, `applyPayment`, `applyShipment`, `applyCancellation` chỉ mang tính giải thích. Phần 8 cung cấp một phiên bản hoàn chỉnh, không dùng những hàm giả định ấy.

Các quy tắc Java cần quan sát:

- `OrderPlaced(var id, var item, long seq)` là **record pattern**. `var` suy luận kiểu component theo khai báo record; `seq` có kiểu `long`.
- `when current == null` là **guard** của case đầu. Guard chỉ được xét **sau khi record pattern khớp**.
- Khi `current != null`, guard đầu sai, nên case `OrderPlaced placed` tiếp theo xử lý việc tạo đơn trùng.
- Case rộng `OrderPlaced placed` phải đứng **sau** case có guard; đảo thứ tự có thể gây lỗi *dominated case*.
- Mỗi case `PaymentCaptured`, `ParcelShipped`, `OrderCancelled` có logic chuyển trạng thái riêng, tránh gom các event vào một `default` không rõ nghĩa.
- `case null` quy định sự kiện null là lỗi đầu vào. Một `default` không phải cách thay thế chính sách null.
- Khi dùng một `switch expression`, block case cần `yield` để cung cấp giá trị; `throw` có thể kết thúc nhánh bằng exception.

### Flow scope của biến pattern

Biến `id` và `seq` được ràng buộc bởi case `PaymentCaptured` **không tồn tại** trong nhánh `ParcelShipped`. Tên giống nhau ở case khác là **biến pattern khác**. Java kiểm tra phạm vi theo luồng khớp, nên không thể dùng dữ liệu của một event ở nhánh nơi nó không khớp.

## 5. Luật chuyển trạng thái: xử lý event đúng nghĩa

Bảng dưới đây là hợp đồng của projector trong bài:

| Event | Snapshot trước | Snapshot sau | Điều kiện bắt buộc |
| --- | --- | --- | --- |
| `OrderPlaced` | Chưa có (`null`) | `PLACED` | `sequence = 1`, item hợp lệ |
| `PaymentCaptured` | `PLACED` | `PAID` | Đúng orderId, sequence tiếp theo |
| `ParcelShipped` | `PAID` | `SHIPPED` | Tracking code hợp lệ, orderId/sequence đúng |
| `OrderCancelled` | `PLACED` | `CANCELLED` | Reason hợp lệ, orderId/sequence đúng |
| `OrderCancelled` | `PAID` | `CANCELLED` | Reason hợp lệ, orderId/sequence đúng |
| `OrderCancelled` | `SHIPPED` | Từ chối | Không cho phép hủy sau khi giao |
| `PaymentCaptured` lần thứ hai | `PAID` hoặc sau đó | Từ chối | Không chuyển lại sang PAID tùy tiện |
| `ParcelShipped` trước khi thanh toán | `PLACED` | Từ chối | Thiếu bước PAID |
| Mọi event khác `OrderPlaced` khi chưa có order | `null` | Từ chối | Thiếu sự kiện tạo ban đầu |

Cần phân biệt **hai loại lỗi**:

1. **Lỗi thứ tự/phân vùng:** sai `orderId`, thiếu sequence, trùng sequence hoặc event đến trước sự kiện tạo.
2. **Lỗi chuyển trạng thái:** event đúng ID và sequence nhưng không hợp lệ với state hiện tại, ví dụ `ParcelShipped` khi chưa thanh toán.

Cả hai đều không nên tự biến thành “bỏ qua event” nếu domain yêu cầu dữ liệu phải được áp dụng chính xác. Nếu một hệ thống cần hỗ trợ replay bỏ qua duplicate, đó phải là **chính sách idempotency rõ ràng**, không phải một `default -> current` tùy tiện.

### Tại sao cần kiểm tra orderId?

Nếu event `PaymentCaptured("O-9", 2)` vô tình được đưa vào snapshot của đơn `O-7`, sequence có thể vẫn hợp lệ nhưng dữ liệu **thuộc về đơn khác**. Kiểm tra chỉ mỗi sequence là chưa đủ. Hàm `requireNext` ở ví dụ đầy đủ kiểm tra cả ID lẫn sequence rồi mới kiểm tra/chuyển state.

### Không mutate nếu transition thất bại

Trong bài, mọi snapshot là record; `apply` chỉ tạo một `Order` mới **sau khi** xác thực điều kiện. Nếu việc áp dụng một event ném exception, object snapshot cũ vẫn giữ nguyên.

Đây là ưu điểm của cách viết reducer bất biến trong một tiến trình. Nó **không đảm bảo** một luồng side effect bên ngoài (ghi DB, gửi mail, xử lý thanh toán) sẽ tự rollback khi lỗi. Những thao tác đó phải được quản lý ở tầng khác bằng transaction và cơ chế nhất quán phù hợp.

## 6. Nested record pattern: đọc Order và Item để hiển thị

Record patterns không chỉ dùng trên event. Ta có thể phân rã ngay snapshot có record lồng:

```java
static String summary(Object value) {
    return switch (value) {
        case Order(
                var id,
                Item(var sku, var quantity, var unitPriceCents),
                var state,
                var totalCents,
                var sequence,
                var trackingCode) ->
                id + " " + sku + "x" + quantity
                        + " " + state
                        + " total=" + totalCents
                        + " seq=" + sequence
                        + (trackingCode == null
                                ? ""
                                : " tracking=" + trackingCode);

        case null -> "NO_ORDER";
        default -> "UNSUPPORTED_ORDER";
    };
}
```

Đây là phương thức Java 21 hoàn chỉnh **khi các record đã được khai báo ở cùng ngữ cảnh**. Nó cho thấy:

- Pattern ngoài khớp `Order`; pattern con `Item(var sku, var quantity, var unitPriceCents)` khớp record mặt hàng.
- Các component có kiểu cụ thể được ràng buộc; `quantity` là `int`, `unitPriceCents` là `long`.
- Giá trị `trackingCode` có thể bằng `null` ở trạng thái chưa giao; vì dùng `var`, chương trình kiểm tra null trước khi nối chuỗi.
- Nếu input không phải `Order`, `default` trả kết quả thể hiện kiểu không hỗ trợ. Điều này có chủ đích vì tham số ở đây là `Object`, **không phải** một sealed hierarchy đóng.

Đây là phép **chuyển trạng thái sang chuỗi trình bày**, tách khỏi phương thức `apply`. Việc giữ logic chiếu trạng thái và logic hiển thị ở hai nơi giúp domain không bị phụ thuộc vào định dạng của một màn hình.

**Lưu ý nested null:** Nếu component `item` của một `Order` bằng `null`, pattern lồng `Item(...)` sẽ không khớp. Trong chương trình đầy đủ, constructor `Order` không cho phép item null, nên những snapshot được tạo hợp lệ không gặp trường hợp này. Record pattern không phải thay thế cho validation của object.

## 7. Validation tại record và boundary

Record compact constructor là nơi thích hợp để xác thực **bất biến nội tại** của một sự kiện:

```java
record OrderCancelled(
        String orderId, String reason, long sequence)
        implements OrderEvent {
    OrderCancelled {
        requireNonBlank(orderId, "orderId");
        requireNonBlank(reason, "reason");
        if (sequence <= 0) {
            throw new IllegalArgumentException(
                    "sequence must be positive");
        }
    }
}
```

Đoạn minh họa trên giả định `OrderEvent` và hàm `requireNonBlank` đã được khai báo. Khi tạo `new OrderCancelled("O-7", " ", 4)`, constructor từ chối reason không có nội dung, thay vì tạo event mà projector không hiểu.

Phân biệt ba mức kiểm tra:

1. **Ở constructor event:** mã order không blank, dữ liệu bắt buộc tồn tại, sequence dương, tracking code/reason có nội dung.
2. **Ở reducer/projector:** event có thuộc đúng order không, sequence có nối tiếp không, state trước có cho phép event đó không.
3. **Ở boundary/hệ thống phát event:** danh tính nguồn, quyền, kết quả thanh toán thật, schema dữ liệu, phiên bản, chữ ký/nguồn tin cậy.

Sealed interface giúp giới hạn subtype đã khai báo trong Java nhưng không xác minh sự kiện nghiệp vụ đã diễn ra. Ngược lại, validation không chứng minh rằng event đã được ghi bền vững vào log.

### Nguyên tắc kiểm tra tiền

Với `Item` có `quantity` và `unitPriceCents`, nên kiểm tra:

- `sku` có nội dung.
- `quantity > 0`.
- `unitPriceCents >= 0` nếu domain cho phép mặt hàng miễn phí; cấm giá âm nếu âm không biểu diễn giảm giá.
- Tích số lượng và đơn giá **không tràn `long`**, ví dụ qua `Math.multiplyExact`.

Phí vận chuyển, giảm giá và thuế là các biến thể riêng cần quy tắc tính tổng rõ ràng. Đừng giả định chỉ cần `quantity * unitPrice` là đủ cho mọi hóa đơn production.

## 8. Chương trình Java 21 chạy độc lập

Tạo tệp **`OrderRecordSealedEventDemo.java`** với nội dung sau. Chương trình dùng JDK 21 trở lên, không cần preview hay thư viện ngoài.

```java
import java.util.List;
import java.util.Objects;

public class OrderRecordSealedEventDemo {
    enum State {
        PLACED, PAID, SHIPPED, CANCELLED
    }

    static void requireNonBlank(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    field + " must not be blank");
        }
    }

    static void checkEventMeta(String orderId, long sequence) {
        requireNonBlank(orderId, "orderId");
        if (sequence <= 0) {
            throw new IllegalArgumentException(
                    "sequence must be positive");
        }
    }

    record Item(String sku, int quantity, long unitPriceCents) {
        Item {
            requireNonBlank(sku, "sku");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (unitPriceCents < 0) {
                throw new IllegalArgumentException(
                        "unitPriceCents must not be negative");
            }
            Math.multiplyExact((long) quantity, unitPriceCents);
        }

        long subtotalCents() {
            return Math.multiplyExact(
                    (long) quantity, unitPriceCents);
        }
    }

    record Order(
            String id,
            Item item,
            State state,
            long totalCents,
            long sequence,
            String trackingCode) {
        Order {
            requireNonBlank(id, "orderId");
            Objects.requireNonNull(item, "item");
            Objects.requireNonNull(state, "state");

            if (sequence <= 0) {
                throw new IllegalArgumentException(
                        "sequence must be positive");
            }
            if (totalCents != item.subtotalCents()) {
                throw new IllegalArgumentException(
                        "total does not match item");
            }
            if (state == State.SHIPPED) {
                requireNonBlank(trackingCode, "trackingCode");
            } else if (trackingCode != null) {
                throw new IllegalArgumentException(
                        "trackingCode only allowed for SHIPPED");
            }
        }
    }

    sealed interface OrderEvent
            permits OrderPlaced, PaymentCaptured,
                    ParcelShipped, OrderCancelled {}

    record OrderPlaced(
            String orderId, Item item, long sequence)
            implements OrderEvent {
        OrderPlaced {
            checkEventMeta(orderId, sequence);
            Objects.requireNonNull(item, "item");
        }
    }

    record PaymentCaptured(String orderId, long sequence)
            implements OrderEvent {
        PaymentCaptured {
            checkEventMeta(orderId, sequence);
        }
    }

    record ParcelShipped(
            String orderId, String trackingCode, long sequence)
            implements OrderEvent {
        ParcelShipped {
            checkEventMeta(orderId, sequence);
            requireNonBlank(trackingCode, "trackingCode");
        }
    }

    record OrderCancelled(
            String orderId, String reason, long sequence)
            implements OrderEvent {
        OrderCancelled {
            checkEventMeta(orderId, sequence);
            requireNonBlank(reason, "reason");
        }
    }

    static Order requireNext(
            Order current, String orderId, long sequence) {
        if (current == null) {
            throw new IllegalStateException(
                    "Order not initialized: " + orderId);
        }
        if (!current.id().equals(orderId)) {
            throw new IllegalArgumentException(
                    "Event belongs to different order: " + orderId);
        }
        if (sequence != Math.addExact(current.sequence(), 1L)) {
            throw new IllegalStateException(
                    "Unexpected event sequence: " + sequence);
        }
        return current;
    }

    static Order apply(Order current, OrderEvent event) {
        return switch (event) {
            case OrderPlaced(var id, var item, long seq)
                    when current == null -> {
                if (seq != 1L) {
                    throw new IllegalStateException(
                            "First event sequence must be 1");
                }
                yield new Order(
                        id, item, State.PLACED,
                        item.subtotalCents(), seq, null);
            }

            case OrderPlaced placed ->
                    throw new IllegalStateException(
                            "Order already exists: " + placed.orderId());

            case PaymentCaptured(var id, long seq) -> {
                Order old = requireNext(current, id, seq);
                if (old.state() != State.PLACED) {
                    throw new IllegalStateException(
                            "Cannot pay order in state: " + old.state());
                }
                yield new Order(
                        old.id(), old.item(), State.PAID,
                        old.totalCents(), seq, null);
            }

            case ParcelShipped(var id, var tracking, long seq) -> {
                Order old = requireNext(current, id, seq);
                if (old.state() != State.PAID) {
                    throw new IllegalStateException(
                            "Cannot ship order in state: " + old.state());
                }
                yield new Order(
                        old.id(), old.item(), State.SHIPPED,
                        old.totalCents(), seq, tracking);
            }

            case OrderCancelled(var id, var reason, long seq) -> {
                Order old = requireNext(current, id, seq);
                if (old.state() != State.PLACED
                        && old.state() != State.PAID) {
                    throw new IllegalStateException(
                            "Cannot cancel order in state: "
                                    + old.state());
                }
                yield new Order(
                        old.id(), old.item(), State.CANCELLED,
                        old.totalCents(), seq, null);
            }

            case null ->
                    throw new IllegalArgumentException(
                            "event must not be null");
        };
    }

    // Replay a sequence of trusted and ordered events.
    static Order replay(List<? extends OrderEvent> events) {
        Order current = null;
        for (OrderEvent event : events) {
            current = apply(current, event);
        }
        return current;
    }

    // Nested record pattern: Order contains an Item record.
    static String summary(Object value) {
        return switch (value) {
            case Order(
                    var id,
                    Item(var sku, var quantity, var unitPriceCents),
                    var state,
                    var totalCents,
                    var sequence,
                    var trackingCode) ->
                    id + " " + sku + "x" + quantity
                            + " " + state
                            + " total=" + totalCents
                            + " seq=" + sequence
                            + (trackingCode == null
                                    ? ""
                                    : " tracking=" + trackingCode);

            case null -> "NO_ORDER";
            default -> "UNSUPPORTED_ORDER";
        };
    }

    static void expectFailure(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + " -> UNEXPECTED_SUCCESS");
        } catch (RuntimeException ex) {
            System.out.println(
                    name + " -> "
                            + ex.getClass().getSimpleName()
                            + ": " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        Order placed = apply(null,
                new OrderPlaced("O-7",
                        new Item("BOOK", 2, 1500L), 1));
        Order paid = apply(placed,
                new PaymentCaptured("O-7", 2));
        Order shipped = apply(paid,
                new ParcelShipped("O-7", "TR-9", 3));

        System.out.println("placed -> " + summary(placed));
        System.out.println("paid -> " + summary(paid));
        System.out.println("shipped -> " + summary(shipped));

        Order cancelled = apply(
                apply(null, new OrderPlaced(
                        "O-8", new Item("PEN", 1, 200L), 1)),
                new OrderCancelled("O-8", "Changed mind", 2));
        System.out.println("cancelled -> " + summary(cancelled));

        Order replayed = replay(List.of(
                new OrderPlaced("O-7",
                        new Item("BOOK", 2, 1500L), 1),
                new PaymentCaptured("O-7", 2),
                new ParcelShipped("O-7", "TR-9", 3)));
        System.out.println("replay-equal -> "
                + shipped.equals(replayed));

        expectFailure("wrong-sequence",
                () -> apply(paid,
                        new ParcelShipped("O-7", "TR-9", 4)));

        expectFailure("cancel-shipped",
                () -> apply(shipped,
                        new OrderCancelled("O-7", "Too late", 4)));

        expectFailure("wrong-order",
                () -> apply(shipped,
                        new PaymentCaptured("O-9", 4)));

        expectFailure("repeat-paid",
                () -> apply(paid,
                        new PaymentCaptured("O-7", 2)));

        expectFailure("missing-place",
                () -> apply(null,
                        new PaymentCaptured("O-7", 1)));

        expectFailure("null-event",
                () -> apply(shipped, null));

        expectFailure("invalid-item",
                () -> new Item(" ", 2, 100L));

        expectFailure("overflow",
                () -> new Item(
                        "BULK", Integer.MAX_VALUE, Long.MAX_VALUE));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 -encoding UTF-8 OrderRecordSealedEventDemo.java
java OrderRecordSealedEventDemo
```

**Standard output mong đợi, theo đúng thứ tự:**

```text
placed -> O-7 BOOKx2 PLACED total=3000 seq=1
paid -> O-7 BOOKx2 PAID total=3000 seq=2
shipped -> O-7 BOOKx2 SHIPPED total=3000 seq=3 tracking=TR-9
cancelled -> O-8 PENx1 CANCELLED total=200 seq=2
replay-equal -> true
wrong-sequence -> IllegalStateException: Unexpected event sequence: 4
cancel-shipped -> IllegalStateException: Cannot cancel order in state: SHIPPED
wrong-order -> IllegalArgumentException: Event belongs to different order: O-9
repeat-paid -> IllegalStateException: Unexpected event sequence: 2
missing-place -> IllegalStateException: Order not initialized: O-7
null-event -> IllegalArgumentException: event must not be null
invalid-item -> IllegalArgumentException: sku must not be blank
overflow -> ArithmeticException: long overflow
```

### Đọc kết quả từng bước

1. **`placed`** được tạo từ `OrderPlaced` đầu tiên; tổng tiền `2 × 1500 = 3000` đơn vị cent, state `PLACED`, sequence `1`.
2. **`paid`** được tạo từ snapshot `placed` và `PaymentCaptured` sequence `2`. Nó giữ nguyên id/item/tổng tiền, chỉ chuyển state và sequence. `placed` vẫn là object cũ ở trạng thái PLACED.
3. **`shipped`** nhận `ParcelShipped` sequence `3`; yêu cầu state trước là PAID và tracking code `TR-9`, rồi tạo snapshot SHIPPED.
4. **`cancelled`** là nhánh độc lập của order `O-8`, được tạo và hủy khi chưa thanh toán; state là CANCELLED, tổng tiền vẫn `200` vì projector không tự diễn giải refund.
5. **`replay-equal -> true`**: chạy lại cùng các event theo thứ tự tạo một record snapshot có component bằng nhau. Đây là minh họa tính quyết định (*determinism*) của reducer cho cùng input; không chứng minh một hệ thống phân tán đã có exactly-once processing.
6. **`wrong-sequence`** dùng event sequence `4` trên snapshot sequence `2`, trong khi sequence tiếp theo phải là `3`. Event bị từ chối, không có snapshot sai được tạo.
7. **`cancel-shipped`** có sequence và orderId hợp lệ nhưng state SHIPPED không được phép hủy theo hợp đồng; đây là **lỗi chuyển trạng thái**, không phải lỗi thứ tự.
8. **`wrong-order`** cố áp dụng sự kiện `O-9` lên snapshot `O-7`, bị từ chối ngay khi kiểm tra orderId.
9. **`repeat-paid`** có sequence cũ `2` nên bị từ chối. Nếu gửi lại cùng event theo một cơ chế idempotency có chủ đích, xử lý production có thể khác; chương trình này chỉ minh họa chính sách nghiêm ngặt.
10. **`missing-place`** cố nhận `PaymentCaptured` khi chưa có `OrderPlaced`; không thể suy ra snapshot đơn hàng từ event thanh toán đơn lẻ.
11. **`null-event`** chọn `case null` và ném `IllegalArgumentException`, không âm thầm bỏ qua event.
12. **`invalid-item`** tạo SKU chỉ chứa khoảng trắng, bị constructor `Item` từ chối.
13. **`overflow`** cố nhân hai số dương lớn vượt phạm vi `long`, bị `Math.multiplyExact` ném `ArithmeticException` thay vì nhận số tiền sai.

Phương thức `expectFailure` chỉ **in các exception dự kiến để học và kiểm thử thủ công**. Nó không biến việc xử lý event thất bại thành sự kiện thành công. Trong ứng dụng thật, lỗi cần được chuyển thành kết quả phù hợp ở ranh giới xử lý hoặc đưa vào kênh quan sát/khắc phục, thay vì luôn bắt chung rồi tiếp tục như không có gì xảy ra.

## 9. Cơ chế chính của Java 21 trong chương trình

### 9.1. Sealed hierarchy + switch exhaustive

Hàm `apply` có case cho cả bốn subtype và selector null. Vì `OrderEvent` là sealed và những subtype trực tiếp đều là record final, Java 21 có thể kiểm tra toàn bộ các trường hợp hợp lệ về **kiểu**. Không dùng `default -> current` để che việc thiếu xử lý một event.

Nếu thêm:

```java
record OrderRefunded(String orderId, long sequence)
        implements OrderEvent {}
```

thì cần cập nhật `permits OrderEvent` và chính sách reducer. Với một `switch expression` trước đó exhaustive không có default, compiler có thể báo **thiếu case** khi biên dịch lại. Đây là cách phát hiện phần code chưa hiểu event mới, chứ không phải lý do để thêm default bừa bãi.

### 9.2. Guard true/false và thứ tự case

Hai case cho `OrderPlaced`:

```java
case OrderPlaced(var id, var item, long seq)
        when current == null -> {
    // Tạo snapshot ban đầu.
    yield new Order(
            id, item, State.PLACED, item.subtotalCents(), seq, null);
}
case OrderPlaced placed ->
        throw new IllegalStateException("Order already exists");
```

Đây là **trích đoạn minh họa** của `switch`, bỏ bớt kiểm tra sequence để tập trung giải thích guard. `when current == null` chỉ đúng khi chưa có snapshot. Khi guard sai, case sau có thể khớp và báo lỗi tạo trùng. Nếu đảo case rộng lên trước, case có guard sẽ bị bao phủ (*dominated*) và có thể không biên dịch.

### 9.3. Record patterns và nested record patterns

Trong `summary`, pattern:

```java
case Order(
        var id,
        Item(var sku, var quantity, var unitPriceCents),
        var state,
        var totalCents,
        var sequence,
        var trackingCode) -> ...
```

trực tiếp đọc cấu trúc `Order` chứa `Item`. Record pattern được đánh giá bằng cách lấy các component qua accessor để ràng buộc biến có kiểu, không phải cách tạo mới record. Với input không phải `Order`, hàm hiển thị dùng `default` có ý nghĩa vì nhận `Object`.

### 9.4. Null và flow scope

- `case null` trong `apply` là chính sách **event null không hợp lệ**.
- `trackingCode` có thể null ở state PLACED/PAID/CANCELLED; `var trackingCode` có thể ràng buộc null và phải được xử lý tường minh trước khi truy cập.
- `Item(var sku,...)` không khớp nếu bản thân component `item` bằng null. Constructor `Order` từ chối trường hợp ấy.
- Những biến `id`, `seq` trong case event không thể được tham chiếu ngoài phạm vi case đã khớp.

### 9.5. Giá trị record và replay

Record cung cấp `equals`/`hashCode` dựa trên component theo hợp đồng record. Vì các component trong ví dụ là record, enum, String và primitive, việc so sánh snapshot dựng lại có ý nghĩa rõ. Nhưng snapshot bằng nhau **không chứng minh** hệ thống event log không thiếu event trung gian nếu dữ liệu không mang sequence/identifier phù hợp; cần thêm các kiểm tra domain và storage.

## 10. Replay event: đúng thứ tự, không tự đồng nghĩa exactly-once

Hàm:

```java
static Order replay(List<? extends OrderEvent> events) {
    Order current = null;
    for (OrderEvent event : events) {
        current = apply(current, event);
    }
    return current;
}
```

có tính chất quan trọng: cùng một chuỗi event hợp lệ theo thứ tự, cùng logic reducer thuần túy, thì tạo cùng snapshot theo các component (giả sử không có input phụ biến đổi theo thời gian).

**Những điều replay này chưa giải quyết:**

- **Độ bền:** danh sách `List` trong bộ nhớ không phải kho event log được lưu bền vững.
- **Concurrency:** hai event cho cùng order cần thứ tự hóa và/hoặc kiểm tra phiên bản nguyên tử khi ghi log.
- **Idempotency:** event duplicate có thể tạo lỗi sequence; hệ thống thật cần biết khi nào bỏ qua duplicate là đúng và làm sao chứng minh đó là **chính event đã xử lý**, không phải một event khác dùng cùng sequence.
- **Exactly-once side effect:** một consumer replay có thể gửi email/thanh toán lại nếu reducer lẫn side effect với logic trạng thái. Tách projector thuần túy khỏi các thao tác ngoài là thiết kế quan trọng.
- **Sửa hoặc bỏ sự kiện:** event log thường là append-only; hoàn tác nghiệp vụ được mô hình hóa bằng event mới, không tùy tiện chỉnh event lịch sử.
- **Schema evolution:** payload event cũ có thể cần chuyển đổi/phiên dịch tương thích với model mới.

### Sequence không phải idempotency key đầy đủ

Một `sequence` xác định thứ tự kỳ vọng trên một order. Trong môi trường message broker, nếu consumer nhận lại **cùng event**, có thể muốn trả lại kết quả trước đó; nhưng chỉ nhìn `sequence <= current.sequence()` rồi bỏ qua mọi event cũ là nguy hiểm, vì có thể che việc replay nhầm event hoặc xung đột dữ liệu.

Một thiết kế production có thể cần `eventId` bất biến, unique constraint, mapping idempotency/result và kiểm tra payload/hash khi cùng ID xuất hiện lần nữa. Bài demo cố ý **ném lỗi khi sequence không nối tiếp** để phơi bày lỗi thứ tự thay vì tự đoán đó là duplicate an toàn.

### Khi có nhiều order

Trong thực tế, mỗi event thuộc một aggregate/order. Ta cần định tuyến theo `orderId` để áp dụng lên snapshot tương ứng, ví dụ một map `orderId → Order` hoặc kho database phân vùng theo ID. Không nên dùng một biến `current` duy nhất cho toàn hệ thống. Ví dụ chương trình dùng `O-7` và `O-8` là hai chuỗi độc lập nhằm minh họa điểm này.

## 11. Kiểm thử chuyển trạng thái bằng bảng tình huống

Khi kết hợp records và sealed events, nên test cả **hình dạng dữ liệu** lẫn **quy tắc nghiệp vụ**:

| Ca kiểm thử | Event / snapshot trước | Mong đợi |
| --- | --- | --- |
| Tạo đơn đầu tiên | `OrderPlaced` seq=1, current=null | Snapshot PLACED, total đúng. |
| Tạo đơn với seq khác 1 | `OrderPlaced` seq=2, current=null | `IllegalStateException`. |
| Thanh toán đúng | `PaymentCaptured` seq=2 sau PLACED seq=1 | PAID, giữ item và total. |
| Thanh toán lần hai | `PaymentCaptured` khi state PAID | Từ chối; có thể là lỗi state hoặc sequence tùy dữ liệu. |
| Gửi hàng trước thanh toán | `ParcelShipped` sau PLACED | Từ chối chuyển trạng thái. |
| Gửi hàng sau thanh toán | `ParcelShipped` sau PAID | SHIPPED, có tracking. |
| Hủy sau tạo | `OrderCancelled` sau PLACED | CANCELLED. |
| Hủy sau thanh toán | `OrderCancelled` sau PAID | CANCELLED theo chính sách case study. |
| Hủy sau gửi | `OrderCancelled` sau SHIPPED | `IllegalStateException`. |
| Event sai orderId | Event `O-9` áp dụng lên `O-7` | `IllegalArgumentException`. |
| Sequence nhảy cóc | Sau seq=2 nhận seq=4 | `IllegalStateException`. |
| Event không phải OrderPlaced khi current=null | `PaymentCaptured` seq=1 | `IllegalStateException`. |
| Event null | `apply(current, null)` | `IllegalArgumentException`. |
| SKU blank hoặc quantity <=0 | Tạo `Item` | `IllegalArgumentException`. |
| Tích tiền vượt long | Item có giá và quantity cực lớn | `ArithmeticException`. |
| Replay hợp lệ | Cùng chuỗi event và snapshot ban đầu | Các snapshot cuối có component bằng nhau. |

**Không chỉ kiểm tra exception:** Khi một event bị từ chối, hãy xác minh snapshot trước đó vẫn không đổi và không có side effect bên ngoài. Điều này đặc biệt quan trọng nếu ở phiên bản production hàm xử lý được kết nối với storage hoặc message broker.

### Ví dụ unit test JUnit Jupiter

Tệp test minh họa dưới đây giả định `OrderRecordSealedEventDemo` đã có trong cùng package, đồng thời dự án cấu hình **JUnit Jupiter**. Nó **không** chạy bằng `javac` đơn lẻ khi thiếu thư viện test.

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class OrderRecordSealedEventDemoTest {
    @Test
    void placedThenPaid() {
        var item = new OrderRecordSealedEventDemo.Item(
                "BOOK", 2, 1500L);
        var placed = OrderRecordSealedEventDemo.apply(
                null,
                new OrderRecordSealedEventDemo.OrderPlaced(
                        "O-7", item, 1));
        var paid = OrderRecordSealedEventDemo.apply(
                placed,
                new OrderRecordSealedEventDemo.PaymentCaptured(
                        "O-7", 2));

        assertEquals(OrderRecordSealedEventDemo.State.PLACED,
                placed.state());
        assertEquals(OrderRecordSealedEventDemo.State.PAID,
                paid.state());
        assertEquals(3000L, paid.totalCents());
        assertEquals(1L, placed.sequence());
        assertEquals(2L, paid.sequence());
    }

    @Test
    void cannotShipBeforePayment() {
        var placed = OrderRecordSealedEventDemo.apply(
                null,
                new OrderRecordSealedEventDemo.OrderPlaced(
                        "O-1",
                        new OrderRecordSealedEventDemo.Item(
                                "PEN", 1, 200L),
                        1));
        assertThrows(IllegalStateException.class,
                () -> OrderRecordSealedEventDemo.apply(
                        placed,
                        new OrderRecordSealedEventDemo.ParcelShipped(
                                "O-1", "TR-1", 2)));
        assertEquals(OrderRecordSealedEventDemo.State.PLACED,
                placed.state());
    }

    @Test
    void rejectsDifferentOrderId() {
        var placed = OrderRecordSealedEventDemo.apply(
                null,
                new OrderRecordSealedEventDemo.OrderPlaced(
                        "O-1",
                        new OrderRecordSealedEventDemo.Item(
                                "PEN", 1, 200L),
                        1));
        assertThrows(IllegalArgumentException.class,
                () -> OrderRecordSealedEventDemo.apply(
                        placed,
                        new OrderRecordSealedEventDemo.PaymentCaptured(
                                "O-2", 2)));
    }
}
```

Với test production, thêm kiểm tra đầu vào null/blank, trình tự sai, hủy từ từng state, overflow, duplicate, khả năng replay và khi thêm subtype mới. Khi command mới, event mới hoặc state mới xuất hiện, cần cập nhật cả các consumer của event chứ không chỉ projector chính.

## 12. Thêm event mới mà không che lỗi bằng default

Giả sử domain thêm `OrderRefunded`. Việc sửa ít nhất gồm:

1. Định nghĩa **ý nghĩa nghiệp vụ**: hoàn tiền toàn phần hay một phần, từ trạng thái nào, thứ tự với cancellation, currency và số tiền là gì.
2. Thêm record với component cần thiết và validation.
3. Thêm subtype trực tiếp vào `permits OrderEvent`.
4. Biên dịch lại các `switch expression` để tìm nơi thiếu xử lý.
5. Bổ sung chuyển trạng thái hoặc projection riêng; không tự coi `OrderRefunded` như `OrderCancelled` nếu hai sự kiện khác nghĩa.
6. Cập nhật schema message, serializer/deserializer, audit, event consumer và replay.
7. Bổ sung test regression cho các luồng cũ và mới.

Đừng sửa lỗi compiler bằng:

```java
// Anti-pattern: âm thầm bỏ qua event mới.
default -> current;
```

Đây là ví dụ nhánh minh họa, không phải tệp chạy độc lập. Nếu event mới không được hỗ trợ, một lỗi có ý nghĩa hoặc cơ chế versioning tường minh thường tốt hơn việc lờ đi một sự kiện quan trọng. Trong một interface mở cho plugin, nhánh tổng quát có thể phù hợp, nhưng sealed hierarchy đóng giúp phát hiện thiếu xử lý sớm hơn.

### Thêm field vào record là thay đổi hợp đồng

Khi sửa `record OrderPlaced(...)` để thêm `currency` hoặc `eventId`, constructor, accessor, record patterns và cả định dạng payload có thể bị ảnh hưởng. Không nên giả định mọi event cũ sẽ deserialize tự động và giữ nguyên ý nghĩa. Với hệ thống có event log lâu dài, cần **schema/version migration** hoặc lớp chuyển đổi ở boundary.

## 13. Event sourcing và thực tế production

Case study mô tả một hàm reducer và replay **thuần trong bộ nhớ**. Một giải pháp event sourcing hoàn chỉnh còn phải giải quyết:

- **Event store bền vững:** append theo aggregate ID, sequence/version và kiểm soát concurrent writes.
- **Snapshot persistence:** lưu snapshot để tăng tốc replay nếu log dài; snapshot có version để không áp dụng nhầm event.
- **Concurrency control:** optimistic locking/expected version, transaction/unique constraint hoặc cơ chế serialization theo aggregate.
- **Message delivery:** at-least-once delivery và idempotent consumer là trường hợp phổ biến; không tự hứa exactly-once trên toàn hệ thống.
- **Outbox/inbox:** đồng bộ transaction lưu business state/event với việc phát message và xử lý trùng.
- **Schema evolution:** đọc lại event cũ, xử lý trường mới, rename type và kiểm tra tương thích với consumer đã triển khai.
- **Security:** bảo vệ nguồn phát event và dữ liệu nhạy cảm; record patterns không kiểm tra quyền hay tính xác thực.
- **Observability:** log/metric theo event type, aggregate ID, sequence, lỗi projector và các trường hợp không hỗ trợ, tránh làm lộ thông tin thanh toán cá nhân.
- **Điều kiện thời gian:** event time và processing time là hai khái niệm khác nhau; sử dụng timestamps từ nguồn tin cậy khi nghiệp vụ cần.

**Không đưa side effect vào reducer nếu muốn replay an toàn.** Ví dụ, trong case `PaymentCaptured` của `apply` không nên tự gọi API thanh toán, vì replay event có thể kích hoạt thanh toán lại. Payment được thực hiện ở tiến trình xử lý command rồi tạo sự kiện `PaymentCaptured` sau khi thành công; projector chỉ phản ánh kết quả đã có.

### Một event không nhất thiết thay đổi một enum duy nhất

Domain phức tạp có thể cần nhiều thuộc tính trạng thái: thanh toán, fulfillment, return/refund, fraud review, partial shipment. Khi đó một enum `State` đơn giản có thể không đủ. Dù vẫn dùng sealed events, model snapshot có thể gồm nhiều records con hoặc nhiều trạng thái độc lập để tránh “nổ” số lượng giá trị enum.

Khi mô hình mở rộng, nên giới hạn phạm vi từng aggregate và xác định invariant rõ, thay vì nhồi mọi loại sự kiện của toàn doanh nghiệp vào một `sealed interface` duy nhất.

## 14. Những lỗi thường gặp khi kết hợp record và sealed event

### Lỗi 1: Nhầm event với command

`PaymentCaptured` xác nhận một sự kiện đã xảy ra. Không được dùng việc replay `PaymentCaptured` để gọi thanh toán thực tế lần nữa. Nếu cần yêu cầu thanh toán, dùng command/service phù hợp.

### Lỗi 2: Xem record là object mutable

Record không cung cấp setter thay đổi component. Khi áp dụng event, tạo snapshot Order mới rồi lưu bản mới có kiểm soát. Đừng tạo mutable state toàn cục làm mất lợi thế của reducer.

### Lỗi 3: Dùng default nuốt event mới

`default -> current` làm log có event mới nhưng snapshot không đổi, che lỗi thiếu nhánh. Với sealed hierarchy thuộc quyền quản lý của module, hãy để compiler yêu cầu xử lý các subtype mới.

### Lỗi 4: Chỉ nhìn state, bỏ qua orderId/sequence

Một `PaymentCaptured` của order khác hoặc event nhảy cóc có thể vẫn có tên subtype hợp lệ. Compiler không biết dữ liệu đó thuộc aggregate nào; phải kiểm tra ID và sequence.

### Lỗi 5: Dùng record pattern để thay thế validation

`case OrderPlaced(var id, var item, long seq)` không chứng minh `id` có nội dung, `item` đã được xác thực ở boundary, hay event thực sự phát sinh từ nguồn đáng tin. Constructor và kiểm tra nghiệp vụ vẫn cần thiết.

### Lỗi 6: Không xử lý component null

Nested pattern `Item(...)` không khớp nếu component item là null. `var trackingCode` có thể ràng buộc null. Đọc record pattern theo đúng quy tắc null, không áp đặt một giả định chung rằng mọi biến được khớp đều khác null.

### Lỗi 7: Để totalCents sai hoặc bị overflow

`long totalCents = quantity * unitPriceCents` có thể bị tràn nếu không kiểm soát. `Math.multiplyExact` phát hiện overflow trong demo; khi domain cho phép giá trị rất lớn hoặc nhiều loại tiền, thiết kế kiểu tiền phù hợp là bắt buộc.

### Lỗi 8: Dùng sequence làm cơ chế exactly-once

Kiểm tra `seq == current + 1` phát hiện nhiều lỗi thứ tự, nhưng không đủ để chứng minh xử lý một event duy nhất đúng một lần trên các thành phần phân tán. Cần idempotency key, trạng thái bền vững và concurrency control khi triển khai.

### Lỗi 9: Test chỉ đường thành công

Một projector có thể chạy đúng với `Placed → Paid → Shipped` nhưng vẫn sai khi event thiếu, trùng, đảo thứ tự, sai order hoặc hủy sau giao. Phải test đường thất bại và bất biến snapshot.

### Lỗi 10: Quên tương thích event lịch sử

Record pattern khớp cấu trúc Java hiện tại; dữ liệu JSON/Avro/Protobuf cũ có thể có schema khác. Cần lớp decode/migrate/adapter khi đọc log lâu dài, không coi runtime type check là chiến lược versioning.

## 15. Checklist thiết kế và review

1. **Khái niệm:** Order là snapshot hiện tại, event là điều đã xảy ra, command là yêu cầu?
2. **Hệ kiểu:** `OrderEvent` sealed có tập subtype trực tiếp đúng quyền sở hữu?
3. **Dữ liệu:** Mỗi event record chứa component cần thiết, không phải nhiều field không liên quan/nullable tùy tiện?
4. **Validation:** ID, quantity, price, tracking, reason, sequence có quy tắc kiểm tra rõ?
5. **State machine:** Mỗi event được chấp nhận từ trạng thái nào và tạo trạng thái nào?
6. **Ordering:** Kiểm tra aggregate ID và expected sequence trước thay đổi?
7. **Exhaustiveness:** `switch` liệt kê event cụ thể, không dùng default giả thành công?
8. **Null:** Có chính sách cho event null và component null?
9. **Immutability:** Reducer tạo snapshot mới và không mutate snapshot cũ?
10. **Replay:** Không có side effect ngoài khi phát lại event; kết quả xác định với input giống nhau?
11. **Idempotency:** Có cơ chế cho duplicate event/retry dựa trên identity và storage, không chỉ dựa vào sequence?
12. **Concurrency:** Có version check/transaction/locking phù hợp khi nhận event đồng thời?
13. **Schema evolution:** Event cũ và consumer cũ được xử lý thế nào khi thêm type/field?
14. **Tests:** Có test happy path, state transitions sai, sequence sai, orderId sai, null và overflow?
15. **Toolchain:** Mã dùng record patterns trong `switch` được biên dịch với **JDK 21** trở lên, không bật preview khi không cần?

## 16. Tự kiểm tra

**Câu 1.** Vì sao `OrderPlaced` và `PaymentCaptured` là hai record khác nhau, thay vì một record `GenericEvent(String type, Object data)`?

**Đáp án:** Mỗi loại có cấu trúc và ý nghĩa riêng. Với sealed event, compiler biết tập subtype được phép; record patterns lấy component có kiểu rõ thay vì ép từ `Object`. Một generic payload vẫn có thể dùng ở boundary, nhưng cần decode/validate thành domain event đáng tin trước khi áp dụng.

**Câu 2.** Snapshot `Order` đang ở `PAID`, sequence `2`. Nếu nhận `ParcelShipped("O-7", "TR-9", 4)`, có được ship không?

**Đáp án:** Không theo hợp đồng của bài. Sequence tiếp theo phải là `3`. Việc loại event đúng kiểu nhưng sai thứ tự là yêu cầu domain, không phải compiler tự kiểm tra.

**Câu 3.** Nếu nhận `OrderCancelled` từ state SHIPPED với sequence đúng thì sao?

**Đáp án:** Reducer từ chối bằng `IllegalStateException` vì bài chỉ cho phép hủy từ PLACED hoặc PAID. Nếu nghiệp vụ cần hoàn hàng sau khi ship, nên thiết kế event/state khác thay vì âm thầm đổi SHIPPED sang CANCELLED.

**Câu 4.** Có thể lấy `sku` từ `Order` bằng nested record pattern mà không cast `Order` và `Item` không?

**Đáp án:** Có. `case Order(var id, Item(var sku, var quantity, var unitPriceCents), ...)` kết hợp type check và deconstruction. Tuy nhiên, record pattern vẫn gọi accessor và việc khớp nested record phải xử lý component null đúng ngữ nghĩa.

**Câu 5.** Nếu thêm `OrderRefunded` vào sealed hierarchy nhưng reducer chưa có case, cách sửa tốt nhất là gì?

**Đáp án:** Xác định ý nghĩa refund và bổ sung case cùng các quy tắc trạng thái, payload/version và test; không dùng `default -> current` để lờ đi event mới.

**Câu 6.** `replay-equal -> true` chứng minh điều gì và không chứng minh điều gì?

**Đáp án:** Nó chứng minh reducer trong ví dụ tạo snapshot có component bằng nhau từ cùng chuỗi event hợp lệ. Nó **không** chứng minh event đã được lưu bền vững, không có retry trùng, không có concurrency race hay exactly-once side effects ngoài hệ thống.

## 17. Tài liệu và tổng kết

- **JEP 395 – Records (Java 16):** https://openjdk.org/jeps/395
- **JEP 409 – Sealed Classes (Java 17):** https://openjdk.org/jeps/409
- **JEP 440 – Record Patterns (Java 21):** https://openjdk.org/jeps/440
- **JEP 441 – Pattern Matching for switch (Java 21):** https://openjdk.org/jeps/441
- **Java Language Specification 21 – Patterns (`14.30):** https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30
- **Oracle Java 21 – Pattern Matching for switch:** https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html

**Ghi nhớ:** **`Order` record** là snapshot trạng thái, còn **`sealed OrderEvent`** là một tập sự kiện domain được kiểm soát. **Record patterns + exhaustive `switch`** trong Java 21 giúp triển khai một reducer dễ đọc, phát hiện thiếu nhánh khi thêm event và tách bạch logic trạng thái với dữ liệu trình bày. Để dùng an toàn, hãy kiểm tra **orderId, sequence, trạng thái, validation, null và overflow**; khi đưa vào production cần giải quyết thêm **versioning, lưu trữ bền vững, idempotency, transaction và side effects**.
