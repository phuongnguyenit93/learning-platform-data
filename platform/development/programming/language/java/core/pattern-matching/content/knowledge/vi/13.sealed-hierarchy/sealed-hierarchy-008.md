# Sealed domain model cho event và command trong Java

## 1. Mục đích của mô hình

Trong ứng dụng nghiệp vụ Java, **command** và **domain event** không phải hai tên gọi của cùng một thứ:

- **Command** là một *yêu cầu/ý định*: “đặt đơn hàng”, “hủy đơn hàng”, “đổi địa chỉ”. Yêu cầu có thể hợp lệ về định dạng nhưng vẫn bị từ chối do trạng thái nghiệp vụ.
- **Domain event** là một *sự thật đã xảy ra*: “đơn hàng đã được đặt”, “đơn hàng đã hủy”. Event nên mô tả điều đã được chấp thuận/ghi nhận, không phải lời yêu cầu thực hiện trong tương lai.

**Sealed domain model** sử dụng `sealed interface` hoặc `sealed class` để kiểm soát **tập subtype trực tiếp** được phép của những nhóm thông điệp đó. Kết hợp với `record` và pattern matching for `switch` (Java 21), ta có thể biểu diễn **các biến thể hữu hạn** của domain một cách an toàn về kiểu.

~~~text
Client / API
     |
     v
PlaceOrder, CancelOrder             COMMAND: Muốn làm gì?
     |
     v
decide(currentState, command)       Kiểm tra quy tắc nghiệp vụ
     |           \
     |            \-- Rejection / exception: không có event thành công
     v
OrderPlaced, OrderCancelled         EVENT: Điều gì đã xảy ra?
     |
     v
apply(currentState, event)          Dựng state / projection
     |
     v
OrderState
~~~

Lợi ích quan trọng:

1. **Rõ nghĩa:** kiểu `Command` không bị nhầm với kiểu `Event`.
2. **Hữu hạn và có chủ sở hữu:** một sealed hierarchy định nghĩa những biến thể trực tiếp được phép.
3. **Payload tường minh:** mỗi `record` có trường đúng với nghiệp vụ, thay vì gói `Map<String, Object>` hoặc mã `String type` tự tạo.
4. **Exhaustiveness:** Java 21 có thể kiểm tra một `switch expression` đã xử lý đủ subtype của hierarchy đóng, không cần `default`.
5. **Dễ kiểm thử:** handler, validation, state transition và projection có thể được thử độc lập.

**Giới hạn:** `sealed` không tự biến ứng dụng thành *event sourcing*, không lưu event, không đảm bảo idempotency, transaction, thứ tự phân phối, serialization hay tương thích phiên bản. Đó là các quyết định thiết kế bổ sung.

## 2. Tách hai sealed hierarchy thay vì trộn thông điệp

Mô hình sơ lược:

~~~java
sealed interface Command permits PlaceOrder, CancelOrder {}

record PlaceOrder(String id, String sku, int quantity)
        implements Command {}

record CancelOrder(String id, String reason)
        implements Command {}

sealed interface Event permits OrderPlaced, OrderCancelled {}

record OrderPlaced(String id, String sku, int quantity)
        implements Event {}

record OrderCancelled(String id, String reason)
        implements Event {}
~~~

Đây là **những khai báo minh họa**, không phải một file có hàm `main`. Chúng có thể là các kiểu được tổ chức đúng quy tắc package/module hoặc các kiểu lồng trong một class.

| Command | Ý nghĩa | Event thành công tương ứng trong ví dụ |
| --- | --- | --- |
| `PlaceOrder(id, sku, quantity)` | Yêu cầu đặt đơn với sản phẩm/số lượng | `OrderPlaced(id, sku, quantity)` |
| `CancelOrder(id, reason)` | Yêu cầu hủy một đơn hợp lệ | `OrderCancelled(id, reason)` |

Dù record command và event có các trường giống nhau, ngữ nghĩa vẫn khác:

- `CancelOrder` có thể bị từ chối nếu đơn không tồn tại hoặc đã hủy.
- `OrderCancelled` phải được tạo sau khi nghiệp vụ xác nhận việc hủy đã xảy ra.
- Không được tự động coi “request đã đến API” là “event thành công”.
- Một command có thể tạo **0, 1 hoặc nhiều event** tùy domain. Ví dụ chính bên dưới chọn **một event cho mỗi command thành công** để dễ thấy luồng dữ liệu.

Tách `Command` và `Event` còn giúp compiler không cho phép đưa `OrderPlaced` vào handler yêu cầu `Command`, hoặc đưa `PlaceOrder` vào projector chỉ nhận `Event`.

## 3. Phiên bản Java cần dùng

| Tính năng | Chính thức từ | Vai trò |
| --- | --- | --- |
| `record` | Java 16 | Kiểu dữ liệu với component cố định, accessor, value equality |
| Pattern matching cho `instanceof` | Java 16 | `obj instanceof MyType t` |
| `sealed` và `permits` | Java 17 | Kiểm soát subtype trực tiếp |
| `switch expression` | Java 14 | Biểu thức tạo ra giá trị |
| Pattern matching cho `switch` | Java 21 | `case PlaceOrder p -> ...` |
| Record patterns | Java 21 | `case PlaceOrder(String id, String sku, int qty)` |

**Chương trình chính cần JDK 21+** vì kết hợp sealed hierarchy và record patterns trong switch. Các tính năng này đều đã chính thức, không cần `--enable-preview`.

**Java 17** vẫn dùng sealed + record được; chỉ cần dispatch bằng `instanceof` hoặc phương thức khác thay vì pattern switch Java 21. Bài có chương trình riêng tương thích Java 17 ở mục 9.

## 4. Chương trình hoàn chỉnh: sealed command → event → state

Ví dụ là một **aggregate đơn hàng trong bộ nhớ**. Mô hình có hai command, hai event và một state. Handler dùng:

- `decide(state, command)`: kiểm tra quy tắc và tạo event hoặc từ chối.
- `apply(state, event)`: dựng state mới từ event.
- `show(event)`: hiển thị event để quan sát nhánh được chọn.

Lưu **`SealedOrderDomainDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

public class SealedOrderDomainDemo {

    sealed interface Command permits PlaceOrder, CancelOrder {}

    record PlaceOrder(String id, String sku, int quantity)
            implements Command {
        PlaceOrder {
            Objects.requireNonNull(id);
            Objects.requireNonNull(sku);
            if (id.isBlank() || sku.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid order");
            }
        }
    }

    record CancelOrder(String id, String reason)
            implements Command {
        CancelOrder {
            Objects.requireNonNull(id);
            Objects.requireNonNull(reason);
            if (id.isBlank() || reason.isBlank()) {
                throw new IllegalArgumentException("invalid cancellation");
            }
        }
    }

    sealed interface Event permits OrderPlaced, OrderCancelled {}

    record OrderPlaced(String id, String sku, int quantity)
            implements Event {}

    record OrderCancelled(String id, String reason)
            implements Event {}

    record OrderState(
            String id, String sku, int quantity, boolean cancelled) {}

    // Command + state => một event, hoặc lỗi nghiệp vụ.
    static Event decide(OrderState state, Command command) {
        Objects.requireNonNull(command, "command");

        return switch (command) {
            case PlaceOrder(String id, String sku, int quantity) -> {
                if (state != null) {
                    throw new IllegalStateException("order exists");
                }
                yield new OrderPlaced(id, sku, quantity);
            }

            case CancelOrder(String id, String reason) -> {
                if (state == null
                        || !state.id().equals(id)
                        || state.cancelled()) {
                    throw new IllegalStateException("cannot cancel");
                }
                yield new OrderCancelled(id, reason);
            }
        };
    }

    // Event + state => state kế tiếp, dùng được khi replay.
    static OrderState apply(OrderState state, Event event) {
        Objects.requireNonNull(event, "event");

        return switch (event) {
            case OrderPlaced(String id, String sku, int quantity)
                    -> new OrderState(id, sku, quantity, false);

            case OrderCancelled(String id, String reason) -> {
                if (state == null || !state.id().equals(id)) {
                    throw new IllegalStateException("invalid history");
                }
                yield new OrderState(
                        id, state.sku(), state.quantity(), true);
            }
        };
    }

    static String show(Event event) {
        return switch (event) {
            case OrderPlaced(String id, String sku, int quantity)
                    -> "ORDER_PLACED " + id + " " + sku
                            + " x" + quantity;

            case OrderCancelled(String id, String reason)
                    -> "ORDER_CANCELLED " + id + " reason=" + reason;
        };
    }

    static String stateLine(String prefix, OrderState state) {
        return prefix + " " + state.id() + " "
                + (state.cancelled() ? "CANCELLED" : "ACTIVE");
    }

    public static void main(String[] args) {
        List<Command> commands = List.of(
                new PlaceOrder("O-17", "BOOK", 2),
                new CancelOrder("O-17", "customer request")
        );

        List<Event> history = new ArrayList<>();
        OrderState state = null;

        for (Command command : commands) {
            Event event = decide(state, command);
            history.add(event);
            System.out.println(show(event));
            state = apply(state, event);
        }

        System.out.println(stateLine("STATE", state));

        // Replay: dựng lại state từ các event đã phát.
        OrderState replay = null;
        for (Event event : history) {
            replay = apply(replay, event);
        }
        System.out.println(stateLine("REPLAY", replay));

        // Lệnh hủy lần hai bị từ chối.
        try {
            decide(state, new CancelOrder("O-17", "again"));
        } catch (IllegalStateException ex) {
            System.out.println("REJECTED " + ex.getMessage());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 21 hoặc mới hơn:

~~~bash
javac SealedOrderDomainDemo.java
java SealedOrderDomainDemo
~~~

Kết quả chính xác:

~~~text
ORDER_PLACED O-17 BOOK x2
ORDER_CANCELLED O-17 reason=customer request
STATE O-17 CANCELLED
REPLAY O-17 CANCELLED
REJECTED cannot cancel
~~~

### Phân tích luồng hoạt động

**Với PlaceOrder:**

1. Compact constructor của record đảm bảo `id`, `sku` không null/trống và `quantity > 0`.
2. `decide(null, PlaceOrder(...))` khớp record pattern PlaceOrder.
3. Vì aggregate chưa có state, nhánh tạo `OrderPlaced`.
4. Event được thêm vào danh sách `history`; `apply` tạo `OrderState` chưa hủy.

**Với CancelOrder:**

1. Record constructor kiểm tra id/reason.
2. `decide` kiểm tra đơn tồn tại, đúng id, chưa bị hủy.
3. Handler tạo `OrderCancelled`; `apply` trả state mới với `cancelled = true`.

**Với replay:** `apply` được gọi lần lượt trên hai event trong lịch sử, bắt đầu từ `state = null`, cho cùng trạng thái cuối. Đây là demo trong bộ nhớ chứ không phải một event store có lưu trữ bền vững.

**Với lệnh hủy lại:** `state.cancelled()` true khiến handler ném `IllegalStateException("cannot cancel")`. Không có event thành công được tạo từ lệnh đó.

### Tại sao dùng yield trong decide/apply?

Cả `decide` và `apply` dùng **switch expression** để tính một giá trị. Ở case có nhiều câu lệnh (kiểm tra state rồi tạo event), `yield value;` cung cấp kết quả cho switch expression:

~~~java
case CancelOrder(String id, String reason) -> {
    if (state == null || state.cancelled()) {
        throw new IllegalStateException("cannot cancel");
    }
    yield new OrderCancelled(id, reason);
}
~~~

Đây là **mảnh minh họa**, đầy đủ quy tắc kiểm tra id nằm trong chương trình chính. `yield` không phải `return` của phương thức: nó đưa giá trị ra khỏi switch expression. Trong một case chỉ có một expression, chẳng hạn `case OrderPlaced(...) -> new OrderState(...);`, không cần viết `yield`.

## 5. Sealed giúp switch kiểm tra exhaustive như thế nào?

Trong chương trình, hierarchy Command gồm đúng hai direct subtype là hai record:

~~~java
sealed interface Command permits PlaceOrder, CancelOrder {}
~~~

Và handler có hai case tương ứng:

~~~java
return switch (command) {
    case PlaceOrder(String id, String sku, int quantity) -> {
        // Xử lý PlaceOrder rồi yield Event.
    }
    case CancelOrder(String id, String reason) -> {
        // Xử lý CancelOrder rồi yield Event.
    }
};
~~~

Hai block ở đây là **mảnh giải thích**, không phải code độc lập để biên dịch. Trong chương trình đầy đủ, mỗi case được triển khai hoàn chỉnh.

Vì tập subtype được đóng và hai record là `final` ngầm định, compiler Java 21 có thể chứng minh switch expression đã xử lý các biến thể **Command không null**. Điều tương tự xảy ra với `Event`: hai nhánh `OrderPlaced` và `OrderCancelled` đủ để `apply`/`show` exhaustive.

### Khi thêm subtype mới

Giả sử nghiệp vụ có `ChangeAddress`. Ta cập nhật:

~~~java
sealed interface Command
        permits PlaceOrder, CancelOrder, ChangeAddress {}

record ChangeAddress(String id, String newAddress)
        implements Command {}
~~~

Đây là **thay đổi giả định**, không thêm vào file demo trừ khi bạn cũng cập nhật handler. Nếu switch `decide` vẫn chỉ có PlaceOrder và CancelOrder mà không có default, compiler sẽ báo **switch expression chưa exhaustive** sau khi cập nhật hierarchy.

Đó là lợi ích rất lớn: thay đổi danh sách biến thể buộc các điểm xử lý phải xét lại domain mới ở **compile time**, thay vì để production nhận một command mà ứng dụng chưa biết cách xử lý.

### Vì sao không thêm default một cách máy móc?

~~~java
return switch (command) {
    case PlaceOrder p -> handlePlace(p);
    case CancelOrder c -> handleCancel(c);
    default -> throw new IllegalArgumentException("unknown");
};
~~~

Đây chỉ là **mảnh minh họa** (giả sử `handlePlace`, `handleCancel` đã được khai báo). `default` có thể khiến switch **tiếp tục biên dịch** khi thêm command mới, nhưng command hợp lệ đó rơi vào fallback chung.

Đối với hierarchy được thiết kế **đóng**, nên cân nhắc **không dùng default** để compiler giúp kiểm tra exhaustiveness. Tuy nhiên, nếu boundary thực sự cần chấp nhận extension hoặc “unknown message”, default có thể là quyết định chủ đích. Cần chọn theo hợp đồng của ứng dụng.

### Runtime và thay đổi binary

Nếu một module đã biên dịch switch exhaustive, sau đó hierarchy sealed được thay đổi và phát hành không đồng bộ với consumer cũ, consumer có thể gặp subtype mới tại runtime và ném **`MatchException`** (Java 21). Thay đổi subtype là **thay đổi hợp đồng**: cần recompile, test và rollout phù hợp. Sealed không tự giải quyết vấn đề multi-version deployment.

## 6. Quy tắc permits, final và non-sealed

Một sealed supertype kiểm soát **direct subclasses/direct implementors**:

~~~java
sealed interface Command permits Create, Delete {}

record Create(String id) implements Command {}
record Delete(String id) implements Command {}
~~~

Các record là **implicitly final**, nên thỏa yêu cầu dành cho subtype trực tiếp của sealed interface. Một class trực tiếp mở rộng/triển khai sealed supertype phải được cho phép, đồng thời thể hiện chính sách kế thừa tiếp bằng `final`, `sealed` hoặc `non-sealed` (trực tiếp hoặc ngầm định như record).

Mã cố ý sai:

~~~java
sealed interface Command permits Create, Delete {}

record Create(String id) implements Command {}
record Delete(String id) implements Command {}

// COMPILE ERROR: Unlisted không thuộc permits.
record Unlisted(String id) implements Command {}
~~~

**Quy tắc package/module:** nếu sealed supertype thuộc named module, các direct permitted subclasses phải thuộc **cùng named module**. Nếu dùng unnamed module, các permitted subclasses phải ở **cùng package**. Bởi vậy, một thiết kế nhiều file/package không thể liệt kê tùy ý bất cứ subtype nào ở bất kỳ module.

### non-sealed không còn đóng mọi nhánh

~~~java
sealed interface Message permits Internal, Extension {}

record Internal(String id) implements Message {}

non-sealed interface Extension extends Message {}

final class ExternalMessage implements Extension {}
~~~

`Extension` là direct subtype được phép nhưng mở lại một nhánh. Các subtype mới có thể implement Extension theo quy tắc Java. Vì vậy không thể suy ra “mọi implementation ở mọi tầng đều nằm trong permits” nếu trong cây có `non-sealed`.

Nếu tập event/command cần hữu hạn để compiler biết các lá, ưu tiên record/final hoặc sealed hierarchy tiếp tục đóng ở các nhánh. Chỉ dùng `non-sealed` khi thiết kế có điểm extension thực sự.

**Sealed là cơ chế quản lý kiểu**, không thay thế phân quyền truy cập, kiểm tra input không tin cậy hoặc schema validation của message đi qua network.

## 7. Record: dữ liệu gọn, nhưng invariants vẫn phải thiết kế

Record tự sinh constructor/accessors/value equality; ví dụ `PlaceOrder` có accessor `id()`, `sku()`, `quantity()`. Vì record có các component fields là final, nó phù hợp để biểu diễn **message giá trị**.

Dù thế, đừng bỏ qua **validation**:

~~~java
record PlaceOrder(String id, String sku, int quantity) {
    PlaceOrder {
        java.util.Objects.requireNonNull(id);
        java.util.Objects.requireNonNull(sku);
        if (id.isBlank() || sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("invalid order");
        }
    }
}
~~~

Đây là **mảnh record minh họa**, độc lập với việc implement sealed interface. Compact constructor được dùng để kiểm tra component trước khi Java gán fields.

### Payload chứa collection phải copy nếu cần bất biến

Record chỉ bất biến **nông (shallow)**. Nếu một component trỏ đến một `ArrayList` mutable, code khác có thể sửa list sau khi event được tạo.

~~~java
record BatchCreated(String batchId, java.util.List<String> items) {
    BatchCreated {
        java.util.Objects.requireNonNull(batchId);
        items = java.util.List.copyOf(items);
    }
}
~~~

`List.copyOf` tạo một danh sách không cho sửa qua API List và không chứa null. Nếu **phần tử** là object mutable, còn phải cân nhắc deep copy hoặc kiểu value immutable cho từng phần tử.

Với event dùng làm lịch sử/audit, tránh payload có trạng thái ngầm thay đổi theo thời gian. Record giúp giảm boilerplate nhưng **không tự đảm bảo mọi object liên quan đều immutable**.

### Kiểm tra dữ liệu khác kiểm tra state

- **Tạo command:** kiểm tra dữ liệu độc lập state, như id không null, quantity dương.
- **Xử lý command:** kiểm tra điều kiện nghiệp vụ phụ thuộc state, như đơn đã tồn tại chưa, đã hủy chưa.
- **Ghi event:** chỉ tạo event thành công khi nghiệp vụ đã chấp nhận.
- **Áp dụng event:** tính state mới từ một event đã xảy ra; nếu lịch sử không hợp lệ, xử lý lỗi theo chính sách event store/replay.

Trong ví dụ, `IllegalStateException` giúp minh họa rejection. Ứng dụng lớn có thể dùng sealed `DecisionResult` với các record `Accepted`/`Rejected` hoặc loại lỗi nghiệp vụ riêng, nhưng không nhất thiết mọi mô hình đều cần một hierarchy bổ sung.

## 8. Event log, state projection và replay

Khái niệm cốt lõi:

~~~java
Event event = decide(currentState, command);
OrderState nextState = apply(currentState, event);
~~~

Trong ví dụ, `history` lưu các event thành công. Khi replay:

~~~java
OrderState replay = null;
for (Event event : history) {
    replay = apply(replay, event);
}
~~~

Với một **lịch sử hợp lệ và đúng thứ tự**, state được tái dựng mà không chạy lại `decide`. Đây là khác biệt cơ bản:

- `decide` xử lý **yêu cầu mới** và phải biết các quy tắc chấp nhận hiện tại.
- `apply` áp dụng **sự kiện đã xảy ra**; khi replay không được phát lại command hay gọi một API ngoài để quyết định lại sự thật cũ.

Để replay có thể tái lập:

1. `apply` nên **deterministic** với cùng state và event.
2. Lưu đủ dữ kiện cần cho state: ví dụ mức giá đã chốt, thời điểm nghiệp vụ, đơn vị tiền nếu chúng ảnh hưởng đến kết quả.
3. Không lấy thời gian hiện tại hoặc gọi dịch vụ bên ngoài trong mỗi lần replay nếu điều đó làm state thay đổi.
4. Có chính sách versioning để đọc những event cũ khi schema/domain rules tiến hóa.

Mô hình trong chương trình chỉ lưu `history` ở RAM. **Chưa phải** event store có persistence, snapshot, optimistic locking, khôi phục và kiểm soát event sequence.

## 9. Java 17: sealed hierarchy với instanceof pattern

Java 17 hỗ trợ sealed interfaces và records, nhưng **pattern matching for switch** chưa chính thức trong phiên bản này nếu không bật preview. Một giải pháp Java 17 thông thường là dispatch qua `instanceof` pattern.

Lưu **`SealedJava17Demo.java`**:

~~~java
public class SealedJava17Demo {

    sealed interface Command permits Register, Deactivate {}

    record Register(String userId) implements Command {}
    record Deactivate(String userId) implements Command {}

    static String route(Command command) {
        if (command instanceof Register r) {
            return "REGISTER:" + r.userId();
        }

        if (command instanceof Deactivate d) {
            return "DEACTIVATE:" + d.userId();
        }

        throw new IllegalStateException("unknown command");
    }

    public static void main(String[] args) {
        System.out.println(route(new Register("U1")));
        System.out.println(route(new Deactivate("U1")));
    }
}
~~~

~~~bash
javac SealedJava17Demo.java
java SealedJava17Demo
~~~

Đầu ra:

~~~text
REGISTER:U1
DEACTIVATE:U1
~~~

Điểm khác: chuỗi `if/instanceof` phải có fallback được viết tay. Nếu hierarchy thêm một direct subtype, Java 17 không tự kiểm tra chuỗi `if` này có xử lý đủ mọi kiểu giống như switch expression pattern Java 21.

Vì vậy nâng lên Java 21 đem lại **kiểm tra exhaustive theo kiểu của selector**, bên cạnh cú pháp record deconstruction tiện hơn.

## 10. Khi mở rộng mô hình thực tế: guard, null và nested patterns

### Guard when

Java 21 cho phép đặt điều kiện sau pattern:

~~~java
case PlaceOrder p when p.quantity() >= 10 -> "BULK";
case PlaceOrder p -> "REGULAR";
~~~

Đây là **các nhánh minh họa** trong switch expression có selector kiểu Command. Guard `when` chỉ được đánh giá **sau khi pattern khớp**. Nếu guard false, Java tiếp tục xét case sau.

Không đặt `case PlaceOrder p` tổng quát **trước** nhánh `when` đặc thù, vì case rộng sẽ dominate case guard phía sau. Một case guard runtime cũng không mặc nhiên bao phủ mọi PlaceOrder để đạt exhaustiveness.

### Null

Một sealed interface không biến null thành một instance hợp lệ. Ví dụ chính sử dụng `Objects.requireNonNull(command, "command")` trước switch để xác định hợp đồng đầu vào. Nếu muốn xử lý null như một giá trị riêng trong switch Java 21, có thể đặt `case null -> ...`.

**Đừng nhầm:** một switch exhaustive theo sealed subtype vẫn có thể ném `NullPointerException` nếu selector null và không có nhãn xử lý null.

### Record patterns lồng nhau

Có thể gói command trong envelope:

~~~java
record Envelope(Command command, String correlationId) {}
~~~

Và phân tích dạng dữ liệu lồng nhau:

~~~java
return switch (incoming) {
    case Envelope(PlaceOrder(String id, String sku, int qty),
                  String correlationId)
            -> "order=" + id + ",trace=" + correlationId;
    default -> "OTHER";
};
~~~

Đây là **mảnh switch minh họa**, giả sử `incoming` có kiểu tĩnh phù hợp và `Envelope`/`PlaceOrder` đã khai báo. Record patterns Java 21 giúp truy cập các component sau khi khớp mà không cần cast thủ công.

Chú ý: record component có thể null và Java có các quy tắc **null-matching component patterns** riêng. Nếu một component có thể null, cần validate hoặc kiểm tra trước khi gọi phương thức trên nó; không suy ra mọi component tự động không null chỉ vì record ngoài cùng đã khớp.

## 11. Production: sealed không tự giải quyết tính đúng đắn phân tán

### 11.1. Idempotency của command

Một request `PlaceOrder` có thể tới hai lần do client retry hoặc queue giao lại. Nếu mỗi lượt đều tạo một event khác nhau, hệ thống có thể ghi trùng. Thông thường cần **command ID/idempotency key** và storage có khả năng ghi nhận kết quả đã xử lý để trả lại cùng kết quả hoặc từ chối an toàn khi request lặp.

### 11.2. Ghi dữ liệu và phát event

Nếu cập nhật database thành công nhưng gửi event lên broker thất bại, hệ thống có thể mất thông báo tích hợp. Cơ chế như **transactional outbox**, giao dịch event store hoặc một workflow retry được thiết kế rõ ràng có thể cần thiết. Không có tính năng `sealed` nào tự bảo đảm **atomic commit** giữa database và broker.

### 11.3. Ordering và concurrency

`OrderCancelled` chỉ hợp lệ sau `OrderPlaced` trong state machine của ví dụ. Với nhiều worker xử lý song song, cần chính sách **expected version / optimistic concurrency**, locking hoặc single-writer để tránh hai command cùng cập nhật dựa trên state cũ.

Record immutable không có nghĩa một repository, event log hay workflow có shared mutable state sẽ tự động thread-safe.

### 11.4. Schema evolution và đa phiên bản

Khi message đi ra ngoài process, kiểu Java sealed không phải là hợp đồng wire format tự động. Có thể cần event type, schema version và ID:

~~~json
{
  "eventType": "order.placed",
  "schemaVersion": 1,
  "eventId": "evt-123",
  "orderId": "O-17",
  "payload": { "sku": "BOOK", "quantity": 2 }
}
~~~

Đây là **JSON minh họa** của event được serialize, không phải output của chương trình. Khi đổi `OrderPlaced` hoặc thêm event mới, cần kiểm tra consumer cũ, backward compatibility, upcasting/migration khi replay lịch sử, thứ tự rollout và các bài kiểm thử hợp đồng.

Thay đổi sealed hierarchy chỉ kiểm soát mã Java được biên dịch **trong phạm vi biết trước**. Một producer ngoài hệ thống vẫn có thể gửi chuỗi JSON không hợp lệ hoặc event thuộc version khác; adapter phải deserialize, validate và xử lý unsupported version.

## 12. Khi nào nên dùng sealed và khi nào không?

**Hợp lý khi** tập biến thể domain có chủ sở hữu rõ, hữu hạn, và việc thêm một loại mới là thay đổi có ý nghĩa cần cập nhật handler. Ví dụ trạng thái thanh toán, lệnh đơn hàng, kết quả nghiệp vụ hoặc sự kiện nội bộ của một bounded context.

**Cần cân nhắc khi** ứng dụng thiết kế một hệ plugin mở, cho bên thứ ba tự đăng ký subtype liên tục. Lúc đó một interface mở, registry hoặc kiến trúc handler khác có thể phù hợp hơn; dùng `non-sealed` cũng là lựa chọn có chủ ý nếu muốn mở một nhánh.

Sealed domain model không nhất thiết phải trở thành một **hierarchy chung khổng lồ** cho mọi message của doanh nghiệp. Các bounded contexts khác nhau có thể có tập command/event riêng, phiên bản riêng và adapter chuyển đổi giữa chúng.

### Tổ chức tham khảo

~~~text
domain/
  command/        Command và các biến thể
  event/          Event và các biến thể
  model/          State / Value Objects
  service/        Decider và Projector
application/
  handler/        Điều phối transaction và result
infrastructure/
  persistence/    Repository / Event Store / Outbox
  transport/      HTTP, JSON, broker adapter
~~~

Đây là **gợi ý kiến trúc**, không phải cấu trúc package bắt buộc. Hãy kiểm tra ràng buộc same module/same package của sealed hierarchy nếu quyết định tách các subtype thành top-level classes ở nhiều file.

## 13. Lỗi phổ biến

| Sai lầm | Vì sao nguy hiểm | Cách xử lý |
| --- | --- | --- |
| Coi command là event ngay khi nhận request | Có thể lưu sự thật nghiệp vụ chưa xảy ra | Xác thực, quyết định rồi mới phát event |
| Dùng `String type` và cast payload khắp code | Thiếu ràng buộc từ compiler | Dùng sealed variants + records |
| Thêm `default -> ignore` vào mọi switch | Khi thêm subtype có thể bỏ qua event hợp lệ | Tránh default khi muốn kiểm tra exhaustiveness |
| Nghĩ sealed cho phép mọi subtype trong mọi JAR | `permits` có quy tắc module/package | Đặt type trong scope được phép |
| Dùng `non-sealed` nhưng kỳ vọng tập lá đóng | Nhánh đó mở cho các subtype khác | Chỉ mở khi thực sự cần |
| Nghĩ record deep immutable | Component mutable có thể thay đổi | Defensive copy/value objects |
| Nghĩ mọi command tạo đúng một event | Lệnh có thể bị từ chối hoặc tạo nhiều event | Thiết kế result/event list theo domain |
| Nghĩ exhaustive switch xử lý null tự động | Null vẫn cần contract riêng | `requireNonNull` hoặc `case null` |
| Java 17 dùng `case Record(...)` như tính năng chính thức | Record pattern switch cần Java 21 | Dùng JDK 21+ hoặc Java 17 `instanceof` |
| Không giữ thứ tự event khi replay | State tái dựng có thể sai | Version/sequence + replay theo đúng thứ tự |
| Không có idempotency/atomicity | Retry hoặc lỗi mạng gây trùng, mất event | Idempotency key, outbox/event store |
| Thêm subtype nhưng không cập nhật consumer | Lỗi runtime/binary compatibility | Kiểm thử và rollout đồng bộ |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `CancelOrder` không đồng nghĩa với `OrderCancelled`?

**Đáp án:** Lệnh hủy là ý định. Nếu đơn không tồn tại/đã hủy, không có sự kiện hủy thành công nào nên được ghi.

**Câu 2.** Khi thêm `ChangeAddress` vào sealed `Command`, vì sao switch expression không có default lại hữu ích?

**Đáp án:** Compiler kiểm tra hierarchy kín. Một handler còn thiếu nhánh sẽ báo **not exhaustive**, giúp phát hiện nơi cần xử lý lệnh mới.

**Câu 3.** Nếu một direct subtype của sealed interface là `non-sealed`, liệu tập implementation cuối cùng còn chắc chắn hữu hạn không?

**Đáp án:** Không. Nhánh được mở có thể có thêm subtype hợp lệ mà không cần liệt kê từng subtype ở `permits` của supertype ngoài.

**Câu 4.** `case PlaceOrder(String id, String sku, int qty)` khác `case PlaceOrder p` ra sao?

**Đáp án:** Dạng đầu là record pattern giải cấu trúc các component thành biến; dạng sau bind cả đối tượng PlaceOrder. Cả hai được dùng trong switch patterns Java 21.

**Câu 5.** Có thể dùng sealed + record trong Java 17 không? Còn `case PlaceOrder p ->` trong pattern switch chính thức?

**Đáp án:** Sealed và record đều chính thức trong Java 17; pattern switch và record patterns được hoàn thiện trong Java 21. Với Java 17 nên dispatch bằng `instanceof` hoặc cách khác.

**Câu 6.** Tại sao `apply(state, event)` không nên gọi một dịch vụ lấy “giá hiện tại” khi replay event lịch sử?

**Đáp án:** Giá tại thời điểm replay có thể khác lúc event xảy ra. Replay phải có dữ liệu đủ để tái dựng kết quả lịch sử một cách xác định, không quyết định lại quá khứ bằng dữ liệu hiện tại.

**Câu 7.** Switch exhaustive theo subtype sealed nhưng selector bằng null thì sao?

**Đáp án:** Null không tự khớp một record subtype. Nếu không xử lý null riêng, switch trên reference có thể ném NPE; xác định contract bằng `Objects.requireNonNull` hoặc `case null`.

## 15. Tài liệu chuẩn

- [JLS 21 — sealed Interfaces, mục 9.1.1.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4): permits và subtype của sealed interface.
- [JLS 21 — sealed, non-sealed, final Classes, mục 8.1.1.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): chính sách kế thừa của sealed hierarchy.
- [JLS 21 — Record Classes, mục 8.10](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.10): record và compact constructor.
- [JLS 21 — Switch Statements, mục 14.11](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): case labels và matching.
- [JLS 21 — Switch Expressions, mục 15.28](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): kết quả và exhaustiveness.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): sealed type coverage, pattern guards, null và MatchException.
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409) và [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): lý do thiết kế và mốc chuẩn hóa.

**Kết luận:** Mô hình sealed cho event và command giúp tách **ý định** khỏi **sự thật đã xảy ra** bằng những kiểu record rõ nghĩa, một tập subtype được kiểm soát và các handler exhaustive với pattern switch Java 21. Để thành kiến trúc production đáng tin, vẫn phải thiết kế đúng validation, state transitions, persistence, replay, idempotency, concurrency và schema evolution.
