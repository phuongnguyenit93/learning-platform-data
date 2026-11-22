# Thiết kế sealed command hierarchy trong Java Pattern Matching

## 1. Bài toán: từ tập câu lệnh nghiệp vụ đến mô hình kiểu an toàn

Giả sử một ứng dụng quản lý đơn hàng phải tiếp nhận bốn **lệnh** (*commands*):

1. **PlaceOrder** — tạo đơn hàng với mã đơn, mã khách và số tiền.
2. **CancelOrder** — yêu cầu hủy một đơn đã tồn tại.
3. **PackOrder** — đóng gói một đơn thành một số kiện.
4. **ShipOrder** — gửi một đơn đến địa chỉ giao hàng.

Mỗi lệnh mang **ý định yêu cầu hệ thống làm gì**, không phải khẳng định rằng việc đó đã thành công. Ví dụ, nhận `ShipOrder("O-1", ...)` không có nghĩa đơn `O-1` đã được giao đi: handler còn phải kiểm tra rằng đơn đã đóng gói và đủ điều kiện chuyển trạng thái.

Một thiết kế ban đầu có thể dùng một lớp tổng quát chứa tên thao tác và nhiều trường tùy chọn:

```java
// Ví dụ phản diện về thiết kế API; không phải chương trình độc lập.
record GenericCommand(
        String commandType,
        String orderId,
        String customerId,
        String reason,
        Integer parcelCount,
        String destinationCity) {}
```

Mô hình này cho phép những trạng thái không có nghĩa, chẳng hạn một lệnh hủy nhưng lại có `parcelCount`, một lệnh giao hàng không có địa chỉ, hoặc `commandType` bị gõ nhầm. Handler thường phải đọc chuỗi và ép kiểu/kiểm tra null thủ công.

**Sealed command hierarchy** giải quyết phần cấu trúc của vấn đề: khai báo một tập nhánh lệnh được phép bằng `sealed`, biểu diễn dữ liệu riêng của từng lệnh bằng `record`, và dùng pattern matching để phân nhánh theo **kiểu đã được compiler biết**.

Mục tiêu không phải biến mọi điều kiện nghiệp vụ thành luật của compiler. Compiler có thể bảo đảm một subtype thuộc hierarchy hợp lệ, giúp kiểm tra switch exhaustive, nhưng **không** biết trong kho dữ liệu đơn `O-1` đã được đóng gói hay chưa. Quy tắc trạng thái, ủy quyền, giao dịch và idempotency vẫn thuộc phần xử lý nghiệp vụ.

Bài sử dụng **Java 21+** để minh họa đầy đủ record patterns, pattern switch và `when` (JEP 440 và JEP 441). Riêng sealed types và records đã ổn định từ Java 17.

## 2. Command khác event và khác result

Ba khái niệm thường được đặt gần nhau nhưng không được trộn:

| Khái niệm | Ý nghĩa | Tên minh họa | Thời điểm |
| --- | --- | --- | --- |
| **Command** | Yêu cầu thực hiện một việc; có thể bị từ chối | `PlaceOrder`, `ShipOrder` | Trước khi áp dụng thay đổi |
| **Domain event** | Sự kiện đã xảy ra trong domain | `OrderPlaced`, `OrderShipped` | Sau khi thay đổi được chấp nhận |
| **Command result** | Kết quả trả cho bên gửi lệnh | `Accepted`, `Rejected` | Sau khi handler xử lý |

Một phương thức kiểu `handle(Command)` không nên được hiểu là “mọi command đều thành công”. Nếu đơn chưa tồn tại hoặc đang ở trạng thái không hợp lệ, handler có thể trả `Rejected`.

Ở ví dụ học tập, `Accepted` chỉ thể hiện **bộ xử lý trong bộ nhớ đã chấp nhận thao tác**. Không nên diễn giải nó là đơn đã được lưu bền vững vào database, message đã được giao tới broker hoặc giao dịch phân tán đã cam kết. Trong hệ thống thật, ranh giới giao dịch và ý nghĩa của kết quả phải được công bố rõ.

Cách đặt tên cũng phản ánh ý nghĩa:
- `PlaceOrder` là yêu cầu chủ động (động từ + đối tượng).
- `OrderPlaced` mô tả sự kiện đã xảy ra (quá khứ).
- `Accepted`/`Rejected` mô tả kết quả xử lý, không phải subtype của `Command`.

## 3. Thiết kế cây sealed hierarchy có nhóm lệnh con

Thay vì bắt tất cả các lệnh trực tiếp thuộc một tập phẳng, có thể nhóm những lệnh cùng chức năng:

```text
Command (sealed interface)
├── PlaceOrder       (record; final)
├── CancelOrder      (record; final)
└── FulfillmentCommand (sealed interface)
    ├── PackOrder    (record; final)
    └── ShipOrder    (record; final)

CommandResult (sealed interface)
├── Accepted         (record; final)
└── Rejected         (record; final)

Address              (record dùng làm value object)
```

Các quyết định có chủ đích:

- `Command` chỉ cho phép **ba subtype trực tiếp**: `PlaceOrder`, `CancelOrder`, `FulfillmentCommand`.
- `FulfillmentCommand` tiếp tục là `sealed` và chỉ cho phép **hai subtype trực tiếp** là `PackOrder` và `ShipOrder`.
- `PackOrder` và `ShipOrder` vẫn là subtype **gián tiếp** của `Command`.
- Mỗi lệnh cụ thể là một `record`, ngầm định `final`, nên không thể tự mở rộng theo cách làm phát sinh subtype không được dự liệu.
- `CommandResult` là một sealed hierarchy **khác** với command, để handler trả về hai khả năng có kiểu rõ.
- `Address` là value object chứ không phải command: nó mô tả dữ liệu của lệnh giao hàng.

**Cú pháp lõi:**

```java
sealed interface Command
        permits PlaceOrder, CancelOrder, FulfillmentCommand {
    String orderId();
}

sealed interface FulfillmentCommand extends Command
        permits PackOrder, ShipOrder {}

record PlaceOrder(String orderId, String customerId, long amountInCents)
        implements Command {}

record CancelOrder(String orderId, String reason)
        implements Command {}

record PackOrder(String orderId, int parcelCount)
        implements FulfillmentCommand {}

record ShipOrder(String orderId, Address destination)
        implements FulfillmentCommand {}

record Address(String city, String countryCode) {}
```

Đây là **đoạn minh họa cấu trúc**, có thể đặt trong một lớp bao ngoài cùng các khai báo hỗ trợ. Chương trình đầy đủ ở mục 7 bổ sung validation, handler và kết quả.

Để giảm trùng lặp, interface `Command` khai báo `orderId()`. Mọi record lệnh đều có component tên `orderId` kiểu `String`, vì vậy accessor do record cung cấp thỏa hợp đồng interface. Nếu lệnh nào không gắn với một đơn cụ thể, **không nên ép nó vào interface yêu cầu `orderId()`**; khi đó cần thiết kế lại hợp đồng chung hoặc tách nhóm lệnh khác.

## 4. Quy tắc sealed: `permits` chỉ liệt kê subtype trực tiếp

Một trong những khác biệt quan trọng nhất giữa sealed hierarchy và sơ đồ phân cấp tùy ý là **compiler áp đặt tập direct children**.

Ở ví dụ này:

```java
sealed interface Command
        permits PlaceOrder, CancelOrder, FulfillmentCommand {}
```

Danh sách này **không** chứa `PackOrder` hoặc `ShipOrder` vì chúng trực tiếp triển khai `FulfillmentCommand`, không trực tiếp triển khai `Command`.

Các subtype trực tiếp của sealed parent phải công bố chính sách kế thừa của chúng:
- `final`: kết thúc nhánh; record ngầm `final`.
- `sealed`: cho phép mở rộng nhưng qua một danh sách `permits` mới, có kiểm soát.
- `non-sealed`: mở rộng nhánh để nhiều subtype có thể tiếp tục xuất hiện.

Trong mô hình command, chọn `FulfillmentCommand` là `sealed` thay vì `non-sealed` để **giữ tập lệnh trong hệ thống ở trạng thái đóng và có thể kiểm chứng**. Nếu sau này cần `ReturnOrder`, `RefundOrder` hay `SchedulePickup`, chủ API phải cân nhắc kiểu nào thuộc nhóm nào và cập nhật hierarchy có chủ đích.

**Phạm vi khai báo:** Với named module, direct permitted subclasses/interfaces phải cùng module với sealed parent; với unnamed module, phải cùng package. Một plugin ngoài module không thể tự ý `implements Command` trực tiếp nếu không thuộc danh sách được phép. Nếu hệ thống thật cần plugin tự cung cấp command mới, đây là tín hiệu để cân nhắc nhánh `non-sealed` hoặc một cơ chế đăng ký handler riêng. Đừng khẳng định vừa “tập đóng exhaustively” vừa “client nào cũng thêm trực tiếp command tùy ý”.

### Không phải lúc nào một cây sâu cũng tốt

Chỉ tạo một subtype trung gian `FulfillmentCommand` nếu nó có ý nghĩa domain, chung hợp đồng/chính sách hoặc có giá trị làm nhánh dispatch. Với dự án rất nhỏ, bốn record trực tiếp trong `Command permits ...` có thể rõ hơn. Sealed hierarchy nên phản ánh **ranh giới biến thể thực**, không tạo thêm tầng chỉ để trông có kiến trúc.

## 5. Record cho dữ liệu của command và kiểm tra invariant

`record` là lựa chọn phù hợp cho command data object vì:
- Có component/constructor/accessor rõ ràng.
- Sinh `equals`, `hashCode`, `toString` theo thành phần, thuận tiện cho kiểm thử và logging có kiểm soát.
- Là `final`, hạn chế những subtype ngoài thiết kế.
- Dễ kết hợp với type pattern hoặc record pattern để lấy dữ liệu.

Tuy nhiên, `record` **không tự bảo đảm mọi dữ liệu hợp lệ**. Ví dụ:

```java
record PackOrder(String orderId, int parcelCount)
        implements FulfillmentCommand {}
```

Cú pháp ở trên vẫn cho phép `new PackOrder("", -3)`. Nên bổ sung **compact constructor** để xác định các invariant cục bộ:

```java
record PackOrder(String orderId, int parcelCount)
        implements FulfillmentCommand {
    PackOrder {
        requireText(orderId, "orderId");
        if (parcelCount <= 0) {
            throw new IllegalArgumentException(
                    "parcelCount must be positive");
        }
    }
}
```

Ở đây `requireText` là phương thức hỗ trợ của lớp bao ngoài trong chương trình đầy đủ. Validation được đặt **tại điểm tạo lệnh**, giúp handler giảm các phép kiểm tra lặp cho dữ liệu cấu trúc.

Chọn mức validation phù hợp:

| Loại kiểm tra | Ví dụ | Nơi phù hợp |
| --- | --- | --- |
| **Invariant cục bộ** | `orderId` không trống, `parcelCount > 0`, `destination != null` | Constructor/factory của command hoặc value object |
| **Quy tắc chuyển trạng thái** | Chỉ đóng gói đơn đang `PLACED` | Handler/domain service với trạng thái hiện tại |
| **Quyền hạn** | Người dùng này có được hủy đơn này không? | Authorization layer/handler |
| **Ràng buộc liên thực thể** | Đơn đã tồn tại? Địa chỉ thuộc vùng hỗ trợ? | Service/repository phù hợp |
| **Tính nhất quán đồng thời** | Hai người cùng đóng gói/hủy một đơn | Transaction/locking/optimistic concurrency control |

Không nên tải database hoặc gọi mạng **ngay trong record constructor** chỉ vì muốn bảo đảm mọi điều kiện nghiệp vụ. Command data object nên dễ tạo và deterministic. Mặt khác, nếu đầu vào bất hợp lệ, xử lý exception từ constructor phải ở tầng ánh xạ request/API phù hợp, bởi handler thậm chí **chưa nhận được command** khi constructor đã ném.

### Tránh “tên có nghĩa” nhưng chưa có kiểm tra tương ứng

Tên `amountInCents` giúp tránh nhầm đơn vị nhưng không ngăn số âm; tên `destination` không xác nhận quốc gia được giao hàng. Hợp đồng phải được hiện thực bằng kiểm tra cụ thể hoặc tài liệu đầu vào rõ ràng.

### Record là bất biến nông

Thành phần record là `final`, nhưng nếu record chứa một `List` hoặc đối tượng mutable, nội dung bên trong vẫn có thể bị thay đổi. Ví dụ nên dùng các value object bất biến hoặc sao chép phòng vệ khi nhận collection. **Không** suy ra mọi command là bất biến sâu chỉ vì khai báo `record`.

## 6. Phân biệt command model, state model và result model

Sealed command hierarchy mô tả **các loại yêu cầu có thể nhận**. Nó không nhất thiết là mô hình trạng thái của aggregate.

Trong ví dụ:
- **Command:** `PlaceOrder`, `CancelOrder`, `PackOrder`, `ShipOrder`.
- **State:** `PLACED`, `PACKED`, `SHIPPED`, `CANCELLED`.
- **Result:** `Accepted` hoặc `Rejected`.

Một trạng thái đơn hàng đơn giản:

```text
Chưa tồn tại
    │ PlaceOrder (hợp lệ)
    ▼
  PLACED ─── PackOrder ──► PACKED ─── ShipOrder ──► SHIPPED
    │                        │
    └──── CancelOrder ───────┘
             ▼
          CANCELLED
```

Các trường hợp từ chối:
- `PackOrder` hoặc `ShipOrder` khi chưa có đơn.
- `PlaceOrder` khi mã đơn đã tồn tại.
- `ShipOrder` khi đơn chưa `PACKED`.
- `CancelOrder` khi đã `SHIPPED`.
- `PackOrder` khi đơn đã `CANCELLED`.
- `CancelOrder` lặp lại khi đã `CANCELLED` (ví dụ chọn trả `Rejected`, không tự idempotent).

**Compiler không biết sơ đồ này.** Nó chỉ kiểm tra rằng `switch` đã xử lý đủ các subtype có thể nhận. Đúng nghiệp vụ cần **kiểm thử trạng thái** riêng, không chỉ test compiler exhaustiveness.

Đặc biệt, `PlaceOrder` là “yêu cầu chuyển sang PLACED” chứ không phải bản thân trạng thái PLACED. Dùng một hierarchy chung cho cả request và state thường khiến logic bị lẫn giữa “việc cần làm” và “điều đang có”.

## 7. Chương trình Java 21 hoàn chỉnh: sealed commands + handler + kết quả

Lưu toàn bộ mã sau thành **`SealedCommandHierarchyDemo.java`**. Ví dụ là chương trình **một file, chạy độc lập** trên JDK 21+, không cần framework bên ngoài. Nó giữ trạng thái bằng `HashMap` để tập trung vào mô hình kiểu và dispatch, **không** được xem là cách triển khai production có transaction/concurrency.

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class SealedCommandHierarchyDemo {
    sealed interface Command
            permits PlaceOrder, CancelOrder, FulfillmentCommand {
        String orderId();
    }

    sealed interface FulfillmentCommand extends Command
            permits PackOrder, ShipOrder {}

    record PlaceOrder(String orderId, String customerId, long amountInCents)
            implements Command {
        PlaceOrder {
            requireText(orderId, "orderId");
            requireText(customerId, "customerId");
            if (amountInCents <= 0) {
                throw new IllegalArgumentException(
                        "amountInCents must be positive");
            }
        }
    }

    record CancelOrder(String orderId, String reason)
            implements Command {
        CancelOrder {
            requireText(orderId, "orderId");
            requireText(reason, "reason");
        }
    }

    record PackOrder(String orderId, int parcelCount)
            implements FulfillmentCommand {
        PackOrder {
            requireText(orderId, "orderId");
            if (parcelCount <= 0) {
                throw new IllegalArgumentException(
                        "parcelCount must be positive");
            }
        }
    }

    record Address(String city, String countryCode) {
        Address {
            requireText(city, "city");
            requireText(countryCode, "countryCode");
        }
    }

    record ShipOrder(String orderId, Address destination)
            implements FulfillmentCommand {
        ShipOrder {
            requireText(orderId, "orderId");
            Objects.requireNonNull(destination, "destination");
        }
    }

    sealed interface CommandResult permits Accepted, Rejected {}
    record Accepted(String message) implements CommandResult {}
    record Rejected(String reason) implements CommandResult {}

    enum Status { PLACED, PACKED, SHIPPED, CANCELLED }

    static final class OrderState {
        final String customerId;
        final long amountInCents;
        Status status = Status.PLACED;

        OrderState(String customerId, long amountInCents) {
            this.customerId = customerId;
            this.amountInCents = amountInCents;
        }
    }

    static String requireText(String value, String name) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    name + " must not be blank");
        }
        return value;
    }

    static final class Handler {
        private final Map<String, OrderState> orders = new HashMap<>();

        CommandResult handle(Command command) {
            Objects.requireNonNull(command, "command");

            return switch (command) {
                case PlaceOrder(
                        var orderId, var customerId, var amountInCents) -> {
                    if (orders.containsKey(orderId)) {
                        yield new Rejected("already-exists:" + orderId);
                    }
                    orders.put(orderId,
                            new OrderState(customerId, amountInCents));
                    yield new Accepted("placed:" + orderId);
                }

                case CancelOrder(var orderId, var reason) -> {
                    OrderState state = orders.get(orderId);
                    if (state == null) {
                        yield new Rejected("not-found:" + orderId);
                    }
                    if (state.status == Status.SHIPPED) {
                        yield new Rejected("already-shipped:" + orderId);
                    }
                    if (state.status == Status.CANCELLED) {
                        yield new Rejected("already-cancelled:" + orderId);
                    }

                    state.status = Status.CANCELLED;
                    yield new Accepted("cancelled:" + orderId);
                }

                case PackOrder(var orderId, var parcelCount) -> {
                    OrderState state = orders.get(orderId);
                    if (state == null) {
                        yield new Rejected("not-found:" + orderId);
                    }
                    if (state.status != Status.PLACED) {
                        yield new Rejected(
                                "not-placeable-for-pack:" + orderId);
                    }

                    state.status = Status.PACKED;
                    yield new Accepted(
                            "packed:" + orderId + ":parcels=" + parcelCount);
                }

                case ShipOrder(var orderId, var destination) -> {
                    OrderState state = orders.get(orderId);
                    if (state == null) {
                        yield new Rejected("not-found:" + orderId);
                    }
                    if (state.status != Status.PACKED) {
                        yield new Rejected("not-packed:" + orderId);
                    }

                    state.status = Status.SHIPPED;
                    yield new Accepted("shipped:" + orderId + ":to="
                            + destination.city() + "/"
                            + destination.countryCode());
                }
            };
        }
    }

    static String show(CommandResult result) {
        return switch (result) {
            case Accepted(var message) -> "OK " + message;
            case Rejected(var reason) -> "ERR " + reason;
        };
    }

    // Pattern theo direct branches: gộp các loại fulfillment.
    static String category(Command command) {
        return switch (command) {
            case PlaceOrder placed -> "order";
            case CancelOrder cancelled -> "order";
            case FulfillmentCommand fulfillment -> "fulfillment";
        };
    }

    // Pattern có guard để phân loại PlaceOrder có giá trị lớn.
    static String priority(Command command) {
        return switch (command) {
            case PlaceOrder(var orderId, var customerId, var cents)
                    when cents >= 100_000 -> "high-value";
            case PlaceOrder(var orderId, var customerId, var cents) ->
                    "standard";
            case CancelOrder cancelled -> "cancellation";
            case FulfillmentCommand fulfillment -> "fulfillment";
        };
    }

    // Record pattern lồng nhau: ShipOrder -> Address.
    static String preview(Command command) {
        return switch (command) {
            case PlaceOrder(var id, var customerId, var cents) ->
                    "place:" + id;
            case CancelOrder(var id, var reason) ->
                    "cancel:" + id;
            case PackOrder(var id, var count) ->
                    "pack:" + id;
            case ShipOrder(var id, Address(var city, var country)) ->
                    "ship:" + id + ":" + city + "/" + country;
            case ShipOrder(var id, var destination) ->
                    "ship-missing:" + id;
        };
    }

    static void run(Handler handler, Command command) {
        System.out.println(show(handler.handle(command)));
    }

    public static void main(String[] args) {
        Handler h = new Handler();

        run(h, new PackOrder("O-1", 2));
        run(h, new PlaceOrder("O-1", "C-1", 150_000));
        run(h, new PlaceOrder("O-1", "C-1", 150_000));
        run(h, new ShipOrder("O-1", new Address("Hue", "VN")));
        run(h, new PackOrder("O-1", 2));
        run(h, new ShipOrder("O-1", new Address("Hue", "VN")));
        run(h, new CancelOrder("O-1", "customer-request"));
        run(h, new PlaceOrder("O-2", "C-2", 5_000));
        run(h, new CancelOrder("O-2", "customer-request"));
        run(h, new PackOrder("O-2", 1));

        System.out.println("category="
                + category(new PackOrder("O-3", 1)));
        System.out.println("priority="
                + priority(new PlaceOrder("O-3", "C-3", 120_000)));
        System.out.println("preview="
                + preview(new ShipOrder(
                        "O-4", new Address("Da Nang", "VN"))));

        try {
            new PlaceOrder("", "C-1", 1_000);
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        try {
            h.handle(null);
        } catch (NullPointerException ex) {
            System.out.println("null=" + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 -encoding UTF-8 SealedCommandHierarchyDemo.java
java SealedCommandHierarchyDemo
```

**Đầu ra chính xác:**

```text
ERR not-found:O-1
OK placed:O-1
ERR already-exists:O-1
ERR not-packed:O-1
OK packed:O-1:parcels=2
OK shipped:O-1:to=Hue/VN
ERR already-shipped:O-1
OK placed:O-2
OK cancelled:O-2
ERR not-placeable-for-pack:O-2
category=fulfillment
priority=high-value
preview=ship:O-4:Da Nang/VN
invalid=orderId must not be blank
null=command
```

Chương trình được kiểm tra trong môi trường compiler sử dụng `--release=21`, và các dòng stdout ở trên khớp kết quả thực thi. Không có thao tác file/database/mạng được thực hiện bởi ví dụ; nó là mô hình in-memory để học cơ chế.

## 8. Giải thích handler: compiler kiểm tra kiểu, domain kiểm tra trạng thái

### 8.1. Tại sao dùng `switch expression` trả về `CommandResult`?

Handler trả về một trong hai kiểu `Accepted` hoặc `Rejected`. Với mỗi nhánh, kết quả là một **giá trị thực sự được caller dùng**, nên `return switch (command)` diễn đạt hợp đồng rõ:

```java
CommandResult handle(Command command) {
    Objects.requireNonNull(command, "command");

    return switch (command) {
        case PlaceOrder(var orderId, var customerId, var amountInCents) -> {
            // Đọc/truy cập domain state...
            yield new Accepted("placed:" + orderId);
        }
        // Các case còn lại phải được bao phủ.
    };
}
```

Đây là **đoạn minh họa rút gọn**, không phải một switch expression độc lập đã exhaustive; hãy xem phương thức đầy đủ ở mục 7. `yield` xuất giá trị từ khối case có nhiều câu lệnh, còn `return` nằm ngoài switch trả kết quả của phương thức.

Nếu handler chủ yếu điều phối các side effects và trả về `void`, `switch statement` với các case block, handler methods và `return;` sớm có thể rõ hơn. Không ép dùng expression cho mọi command handler.

### 8.2. Khi không có đơn, kết quả thuộc domain là `Rejected`

`PackOrder("O-1", 2)` được gửi trước `PlaceOrder`, nên handler trả `Rejected("not-found:O-1")`. Đây **không** phải lỗi cú pháp hoặc pattern mismatch: kiểu PackOrder được compiler công nhận, nhưng trạng thái chưa cho phép xử lý.

### 8.3. Khi đơn đã tồn tại, tạo trùng bị từ chối

Sau lệnh tạo đầu tiên thành công, lệnh `PlaceOrder` cùng mã đơn bị từ chối `already-exists:O-1`. Đây là chính sách đơn giản của ví dụ, **không phải** cơ chế idempotency production. Trong hệ thống phân tán, command có thể cần `idempotencyKey` và record kết quả theo key để retry không tạo side effect lặp.

### 8.4. Giao hàng đòi trạng thái PACKED

`ShipOrder` trước `PackOrder` trả `not-packed:O-1`. Sau `PackOrder`, trạng thái thành `PACKED` và `ShipOrder` mới chuyển sang `SHIPPED`.

### 8.5. Hủy đơn phải xét trạng thái hiện tại

Handler cho phép hủy đơn `PLACED` hoặc `PACKED` nhưng từ chối hủy đơn `SHIPPED`. `CancelOrder.reason` đã được validate không trống; việc handler không ghi reason vào trạng thái ở ví dụ này chỉ là giản lược mô phỏng. Hệ thống thật phải quyết định lưu lý do hủy ở đâu (aggregate state, audit hoặc event) và làm rõ hợp đồng riêng.

### 8.6. Kết quả success/failure được typed

`show` dùng pattern switch trên `CommandResult`. Chỉ có `Accepted` và `Rejected`, do đó không cần ép kiểu thủ công hoặc dựa vào một flag string như `"SUCCESS"`. Khi thêm một subtype `CommandResult` mới, switch exhaustive là một điểm compiler có thể yêu cầu xem xét.

## 9. Exhaustiveness trên sealed hierarchy nhiều tầng

Mọi lệnh đều thuộc một trong bốn record cụ thể, nên trong chương trình `handle` có thể liệt kê:

```java
return switch (command) {
    case PlaceOrder(var id, var customerId, var cents) -> {
        yield /* CommandResult phù hợp */;
    }
    case CancelOrder(var id, var reason) -> {
        yield /* CommandResult phù hợp */;
    }
    case PackOrder(var id, var count) -> {
        yield /* CommandResult phù hợp */;
    }
    case ShipOrder(var id, var destination) -> {
        yield /* CommandResult phù hợp */;
    }
};
```

**Lưu ý:** đây là **sơ đồ minh họa cấu trúc**, với phần `/* ... */` không phải biểu thức Java hoàn chỉnh; không biên dịch riêng. Mã chạy được nằm ở mục 7.

Compiler biết `Command` có ba nhánh trực tiếp, trong đó `FulfillmentCommand` có đúng hai record con. Vì vậy, liệt kê `PlaceOrder`, `CancelOrder`, `PackOrder`, `ShipOrder` đủ bao phủ hierarchy hiện tại.

Một cách xử lý theo **mức nhóm** còn ngắn hơn:

```java
static String group(Command command) {
    return switch (command) {
        case PlaceOrder placed -> "commercial";
        case CancelOrder cancelled -> "commercial";
        case FulfillmentCommand fulfillment -> "fulfillment";
    };
}
```

Đây là phương thức minh họa trong ngữ cảnh các kiểu đã khai báo; nhóm `FulfillmentCommand` cho phép chỉ một case bao phủ cả PackOrder và ShipOrder. **Không thể dùng nhánh kiểu cha rộng rồi đặt nhánh con cụ thể phía sau** nếu điều đó làm nhánh con bị dominated.

### Nếu thêm command mới thì điều gì xảy ra?

Giả sử thêm:

```java
record ReturnOrder(String orderId) implements FulfillmentCommand {}
```

Muốn khai báo này hợp lệ, phải cập nhật `FulfillmentCommand permits PackOrder, ShipOrder, ReturnOrder` (hoặc tập subtype tương ứng được compiler suy ra theo cấu trúc hợp lệ). Khi đó:

- Một switch liệt kê **chỉ PackOrder và ShipOrder** trong handler sẽ thiếu subtype mới và có thể bị compiler từ chối khi **recompile**.
- Một switch đã có `case FulfillmentCommand fulfillment` vẫn xử lý được kiểu mới theo nhánh chung, nhưng logic ấy có đúng nghiệp vụ cho ReturnOrder hay không phải tự kiểm chứng.
- Các test, serialization schema, tài liệu API và versioning phải được xem lại.

Một điểm mạnh của sealed hierarchy là **buộc thay đổi tập lệnh trở thành một quyết định rõ ràng**, thay vì âm thầm nhận một chuỗi `commandType` mới ở runtime.

### Đừng thêm `default` một cách máy móc

Một `default -> new Rejected("unsupported")` trong switch xử lý tất cả lệnh có thể làm mất cơ hội compiler nhắc khi command mới được thêm. Với sealed command set cố ý đóng, liệt kê case rõ ràng thường có giá trị hơn. Nếu API có nhánh `non-sealed` cho plugin, phải thiết kế fallback có nghĩa đối với nhánh mở ấy.

## 10. Record patterns lồng nhau: chọn độ sâu phù hợp

`ShipOrder` chứa một record `Address`. Nếu chỉ cần địa chỉ như value object, cách viết nông là đủ:

```java
case ShipOrder(var orderId, var destination) -> {
    // Có thể dùng destination.city(), destination.countryCode().
}
```

Nếu cần lấy thành phần để tạo nhãn hoặc so khớp sâu:

```java
case ShipOrder(var orderId, Address(var city, var countryCode)) ->
        "ship:" + orderId + ":" + city + "/" + countryCode;
```

Hai đoạn là các nhánh **minh họa**, không phải switch đầy đủ. Mẫu lồng `Address(...)` chỉ khớp khi component `destination` là một instance `Address` **khác null**.

Trong chương trình, constructor `ShipOrder` dùng `Objects.requireNonNull(destination, "destination")`, nên một instance được tạo qua constructor hợp lệ không có `destination == null`. Tuy vậy, **compiler không dựa vào logic constructor để chứng minh mẫu lồng bao phủ cả subtype `ShipOrder`**. Vì thế phương thức `preview` có nhánh bổ sung:

```java
case ShipOrder(var id, var destination) ->
        "ship-missing:" + id;
```

Nhánh này diễn đạt trường hợp còn lại của mẫu `ShipOrder` ở cấp cấu trúc, dù bất biến constructor bình thường khiến đầu vào đó không được tạo ra qua API chuẩn.

**Không nên** nghĩ rằng `case ShipOrder(var id, Address(...))` luôn bao phủ toàn bộ `ShipOrder` chỉ vì constructor hiện tại cấm null. Kết quả compiler của pattern matching căn cứ **kiểu và tính toàn phần của pattern**, không kiểm chứng mã validation nghiệp vụ đã chạy theo một lịch sử nhất định.

Ngoài ra, nếu `Address` có custom accessor ném lỗi khi record pattern phân rã, quá trình matching có thể ném `MatchException` với nguyên nhân gốc, không đi fallback như một pattern không khớp bình thường. Để giữ command dễ dự đoán, nên dùng value object ổn định và accessor không có side effects.

## 11. Guard `when`: dùng đúng chỗ và luôn có nhánh còn lại

Phương thức `priority` trong chương trình minh họa:

```java
static String priority(Command command) {
    return switch (command) {
        case PlaceOrder(var orderId, var customerId, var cents)
                when cents >= 100_000 -> "high-value";

        case PlaceOrder(var orderId, var customerId, var cents) ->
                "standard";

        case CancelOrder cancelled -> "cancellation";
        case FulfillmentCommand fulfillment -> "fulfillment";
    };
}
```

Có hai case `PlaceOrder`:
1. Trường hợp đặc biệt có guard cho số tiền lớn.
2. Trường hợp tổng quát không guard cho các lệnh đặt hàng còn lại.

**Vì sao cần case thứ hai?** Guard chỉ khớp nếu `cents >= 100_000`. Với lệnh đặt hàng hợp lệ nhưng số tiền thấp hơn, Java phải có đường xử lý còn lại để switch vẫn exhaustive. Đặt case tổng quát **trước** case có guard là sai thứ tự vì nó có thể che khuất (*dominate*) case hẹp.

Đặt tên `cents` giúp thấy đang xét đơn vị lưu trong command; trong API đầy đủ có thể ưu tiên tên `amountInCents` nếu nhiều phép tính tiền. **Một guard phân loại** (high-value) không có nghĩa lệnh đã được chấp nhận; handler vẫn cần kiểm tra trạng thái hoặc quyền truy cập.

Nếu guard chứa việc truy xuất dữ liệu, gọi service hoặc thay đổi trạng thái, hành vi matching trở nên khó dự đoán hơn. Với quy tắc nghiệp vụ phức tạp, nên xử lý sau khi case đã khớp trong handler/domain service thay vì nhồi mọi logic vào `when`.

## 12. Chọn tên domain và tránh mất ngữ cảnh

Pattern variables trong command handler nên cho thấy **vai trò**, không chỉ kiểu dữ liệu:

| Tránh | Nên dùng | Lý do |
| --- | --- | --- |
| `id` khi có nhiều ID | `orderId`, `customerId` | Không nhầm đơn với khách hàng |
| `n` trong PackOrder | `parcelCount` | Biến đếm số kiện |
| `price` khi lưu cent | `amountInCents` | Tránh lỗi đơn vị tiền |
| `addr` trong ShipOrder | `destination` hoặc `shippingAddress` | Phân biệt đích giao với địa chỉ thanh toán |
| `reason` quá mơ hồ trong nhiều nhánh | `cancellationReason` khi cần | Nêu rõ lệnh/hành động |
| `cmd1`, `cmd2` | `placeCommand`, `cancelCommand` | Thể hiện chủ ý của biến |

Trong một case đã rõ kiểu `CancelOrder`, dùng `reason` ngắn gọn vẫn có thể đủ. Không cần đặt tên quá dài như `cancelOrderCancellationReasonValue`. Điểm quan trọng là người đọc có thể truy nguồn: component nào được bind, có cùng kiểu với component nào khác, và giá trị ấy được dùng trong quy tắc nghiệp vụ nào.

**Record pattern khớp theo thứ tự component**, không theo tên biến. Nếu hai component cùng `String`, đổi nhầm vị trí có thể vẫn biên dịch nhưng thay đổi ý nghĩa. Vì vậy test output và review model quan trọng hơn việc chỉ thấy compiler xanh.

## 13. Chính sách null và đầu vào không hợp lệ

Có ít nhất ba nơi `null` có thể xuất hiện trong case study:

1. **`Command command == null`**: không có yêu cầu nào.
2. **Component bắt buộc bằng null**: như `new ShipOrder("O-1", null)`.
3. **Dữ liệu trạng thái không tồn tại**: `orders.get(orderId) == null`.

Đó là **ba tình huống khác nhau**.

### Null command

`Handler.handle` gọi:

```java
Objects.requireNonNull(command, "command");
```

Điều này tạo hợp đồng: handler không nhận null command; lỗi là `NullPointerException` với message `"command"`. Nếu muốn API trả `Rejected("missing-command")` thay vì exception, đó là lựa chọn thiết kế khác. Có thể viết `case null` trong Java 21, nhưng không nên thêm nó chỉ để làm mất hợp đồng ban đầu.

Một switch exhaustive theo sealed type **không** tự có nghĩa xử lý selector null an toàn. Nếu không có `case null`, switch trên tham chiếu null thường ném NPE.

### Null component

`ShipOrder` bắt buộc có `destination`; constructor ném NPE khi component ấy null. `PlaceOrder`, `CancelOrder`, `PackOrder` kiểm tra chuỗi không blank và số dương bằng `IllegalArgumentException`. Các lỗi này xuất hiện **trong lúc tạo command**, trước khi handler phân nhánh.

### Không tìm thấy trạng thái

Khi đơn không tồn tại trong `Map`, đây không phải command null và không phải lỗi tạo command. Handler trả `Rejected("not-found:" + orderId)`. Điều này giữ ranh giới rõ giữa **invalid command shape** và **business rejection**.

Với tầng HTTP/API, có thể ánh xạ các loại lỗi sang HTTP status phù hợp, nhưng đó là quyết định adapter. Không suy ra trực tiếp “Rejected luôn là HTTP 400” hay “IllegalArgumentException luôn là HTTP 500”.

## 14. Cách phát triển từ ví dụ in-memory sang kiến trúc nhiều lớp

Ví dụ dùng một `Handler` giữ `Map<String, OrderState>` nhằm minh họa kỹ thuật. Hệ thống thực có thể tách các lớp:

```text
HTTP / CLI / Message Adapter
          │ parse + authenticate
          ▼
Command Factory / Validation
          │ PlaceOrder | CancelOrder | ...
          ▼
Command Handler / Application Service
          │ authorize + load aggregate
          ▼
Domain State / Domain Service
          │ kiểm tra chuyển trạng thái
          ▼
Repository / Transaction Boundary
          │ lưu thành công hoặc rollback
          ▼
CommandResult + Domain Events
          │ trả phản hồi / phát sự kiện đáng tin
          ▼
Caller / Outbox / Event Consumers
```

Tách trách nhiệm không bắt buộc mỗi ô của sơ đồ thành một class. Điểm quan trọng:

- **Command** biểu thị thông tin yêu cầu, không chứa repository hoặc service có trạng thái.
- **Handler** thực hiện dispatch và áp dụng quyền/quy trình.
- **Domain model** quyết định tính hợp lệ của chuyển trạng thái.
- **Repository/transaction** chịu trách nhiệm nhất quán khi lưu.
- **CommandResult** trình bày kết quả chấp nhận/từ chối theo ngữ nghĩa mà caller sử dụng.
- **Domain event** mô tả việc đã xảy ra và chỉ được công bố theo chiến lược nhất quán với transaction.

Một `switch` lớn trong handler có thể được tách thành các phương thức:

```java
// Đoạn minh họa: các phương thức bên dưới là handler chuyên trách.
return switch (command) {
    case PlaceOrder placed -> placeHandler.handle(placed);
    case CancelOrder cancelled -> cancelHandler.handle(cancelled);
    case PackOrder packed -> packHandler.handle(packed);
    case ShipOrder shipped -> shipHandler.handle(shipped);
};
```

Cách này vẫn tận dụng compiler exhaustiveness, nhưng logic ứng dụng cho mỗi command nằm ở handler riêng. Không cần cố phân rã mọi component ngay tại switch nếu việc giữ object `placed` giúp truyền đúng một value object xuống handler.

## 15. Kiểm thử hierarchy: compile-time và behavior là hai tầng khác nhau

### 15.1. Ma trận regression tối thiểu

| Input hoặc thao tác | Expected | Chứng minh |
| --- | --- | --- |
| `PackOrder("O-1",2)` khi chưa có đơn | `Rejected("not-found:O-1")` | Handler kiểm tra tồn tại |
| `PlaceOrder("O-1",...)` lần đầu | `Accepted("placed:O-1")` | Tạo đơn |
| PlaceOrder trùng ID | `Rejected("already-exists:O-1")` | Không tạo trùng |
| ShipOrder trước PackOrder | `Rejected("not-packed:O-1")` | Điều kiện trạng thái |
| PackOrder sau PlaceOrder | `Accepted("packed:O-1:parcels=2")` | Chuyển PLACED → PACKED |
| ShipOrder sau PackOrder | `Accepted("shipped:O-1:to=Hue/VN")` | Chuyển PACKED → SHIPPED |
| CancelOrder sau SHIPPED | `Rejected("already-shipped:O-1")` | Cấm hủy muộn |
| CancelOrder ở PLACED | `Accepted("cancelled:O-2")` | Cho phép hủy đúng trạng thái |
| PackOrder ở CANCELLED | `Rejected("not-placeable-for-pack:O-2")` | Trạng thái hủy là terminal |
| `new PlaceOrder("",...)` | `IllegalArgumentException` | Invariant constructor |
| `handler.handle(null)` | `NullPointerException` | Hợp đồng null |
| `category(new PackOrder(...))` | `"fulfillment"` | Nhánh sealed trung gian |
| `preview(new ShipOrder(...))` | `"ship:O-4:Da Nang/VN"` | Record pattern lồng |
| `priority(new PlaceOrder(...,120_000))` | `"high-value"` | Guard `when` |

Đây là kiểm thử **behavior**: giá trị đúng và trạng thái đúng. Kiểm tra compile-time lại trả lời câu hỏi khác: “Mọi command subtype đã có nhánh xử lý chưa?”

### 15.2. JUnit 5 dùng record equality

Vì `Accepted` và `Rejected` là records, có thể so sánh kết quả typed thay vì chỉ chuỗi in ra:

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SealedCommandHierarchyTest {
    @Test
    void cannotPackAnOrderBeforeItExists() {
        var handler = new SealedCommandHierarchyDemo.Handler();
        var result = handler.handle(
                new SealedCommandHierarchyDemo.PackOrder("O-1", 2));

        assertEquals(
                new SealedCommandHierarchyDemo.Rejected("not-found:O-1"),
                result);
    }

    @Test
    void placeThenPackThenShip() {
        var handler = new SealedCommandHierarchyDemo.Handler();

        assertEquals(
                new SealedCommandHierarchyDemo.Accepted("placed:O-1"),
                handler.handle(
                        new SealedCommandHierarchyDemo.PlaceOrder(
                                "O-1", "C-1", 15_000)));

        assertEquals(
                new SealedCommandHierarchyDemo.Accepted(
                        "packed:O-1:parcels=1"),
                handler.handle(
                        new SealedCommandHierarchyDemo.PackOrder("O-1", 1)));

        assertEquals(
                new SealedCommandHierarchyDemo.Accepted(
                        "shipped:O-1:to=Hue/VN"),
                handler.handle(
                        new SealedCommandHierarchyDemo.ShipOrder(
                                "O-1",
                                new SealedCommandHierarchyDemo.Address(
                                        "Hue", "VN"))));
    }

    @Test
    void rejectInvalidShapesAndNullCommand() {
        assertThrows(IllegalArgumentException.class,
                () -> new SealedCommandHierarchyDemo.PlaceOrder(
                        "", "C-1", 1_000));
        assertThrows(NullPointerException.class,
                () -> new SealedCommandHierarchyDemo.Handler().handle(null));
    }
}
```

Đây là **mã kiểm thử JUnit 5 minh họa**, không phải file standalone chỉ dùng JDK. Cần JUnit 5 trong classpath và đặt test cùng package với `SealedCommandHierarchyDemo` (các nested types/methods trong ví dụ có quyền package-private). Trong dự án thật, xuất public API hoặc tổ chức module/package có chủ đích.

### 15.3. Test lỗi thiếu case ở thời điểm biên dịch

Đoạn Java 21 sau **cố ý không biên dịch**:

```java
sealed interface SmallCommand permits OpenCommand, CloseCommand {}
record OpenCommand(String id) implements SmallCommand {}
record CloseCommand(String id) implements SmallCommand {}

class BadSwitch {
    static String classify(SmallCommand command) {
        return switch (command) {
            case OpenCommand c -> "open";
        };
    }
}
```

Compiler sẽ báo dạng:

```text
the switch expression does not cover all possible input values
```

Đây là **test cho compiler exhaustiveness**, không phải runtime unit test. Khi bổ sung case `CloseCommand` (hoặc một nhánh bao phủ hợp lệ), mã mới compile được. Ngược lại, việc compile thành công không xác nhận rằng trạng thái đơn hàng được cập nhật đúng; vì thế vẫn cần regression tests ở trên.

## 16. Những vấn đề production mà sealed hierarchy không tự giải quyết

### 16.1. Concurrency và transaction

`HashMap` trong ví dụ **không thread-safe**; hai request đồng thời có thể cùng đọc trạng thái `PLACED` hoặc cùng thấy đơn chưa tồn tại. Việc `OrderState.status` là biến mutable cũng cần bảo vệ trước truy cập đồng thời.

Trong hệ thống thật, cân nhắc transaction tại database, optimistic locking bằng `version`, unique constraint cho `orderId`, hoặc cơ chế serialize command theo aggregate. Đừng coi `sealed` là một primitive bảo đảm đồng thời.

### 16.2. Idempotency và retry

Một request có thể được gửi lại do timeout. Nếu `PlaceOrder` thành công nhưng response bị mất, retry có thể gặp `already-exists`. Kết quả này **khác** việc trả lại thành công ban đầu của một operation idempotent.

Muốn có idempotency, cần định nghĩa idempotency key, phạm vi/TTL, cách lưu kết quả và ngữ nghĩa retry, không chỉ dựa vào `equals` của record.

### 16.3. Authorization

Việc tạo `CancelOrder("O-1","...")` hợp lệ ở constructor không chứng minh caller có quyền hủy `O-1`. Tầng application cần kiểm tra identity/permissions và không tin mọi dữ liệu client tự khai báo. Sealed hierarchy hạn chế **các loại command**, không xác thực **người gửi command**.

### 16.4. Serialization và đầu vào ngoài tiến trình

JSON/message brokers không trực tiếp hiểu toàn bộ `permits` theo cách compiler Java hiểu. Cần cấu hình type discriminator, schema version và mapping từ payload sang command object một cách an toàn. Không nên mở cơ chế polymorphic deserialization cho class bất kỳ do client chỉ định tên.

### 16.5. Xử lý lỗi và giao dịch

`Rejected` là kết quả nghiệp vụ có thể dự đoán; exception từ database, network hoặc bug lập trình có thể cần cơ chế error handling riêng. Đừng gom mọi exception thành `Rejected("error")` rồi coi như transaction chắc chắn đã hoàn tất. Cũng không phát event “OrderShipped” trước khi đã bảo đảm cập nhật trạng thái bền vững theo thiết kế.

### 16.6. Observability và dữ liệu nhạy cảm

Records sinh `toString()` từ components. Không nên log nguyên command có dữ liệu khách hàng, địa chỉ, token hoặc nội dung nhạy cảm mà không lọc. Cân nhắc structured logs chỉ chứa command type, correlation ID và những trường được phép lưu.

## 17. Lựa chọn giữa closed command set và plugin mở rộng

Có hai mục tiêu kiến trúc khác nhau:

**Tập command đóng:** chủ ứng dụng kiểm soát toàn bộ lệnh, mọi thay đổi đi qua release của ứng dụng. `sealed` với các record con `final` và nhánh `sealed` trung gian là phù hợp: compiler có thể hỗ trợ kiểm tra mọi case.

**Hệ thống plugin mở:** đối tác/nhóm khác được thêm command mới mà module lõi không biết ở compile time. Dùng một interface mở rộng hoặc registry của handler có thể phù hợp hơn. Nếu nhánh là `non-sealed` thì các pattern switch phải có đường xử lý cho các subtype chưa biết — không còn bảo đảm rằng chỉ các concrete records hiện tại tồn tại.

Quyết định này nên được ghi rõ trong JavaDoc/API:
- Những direct subtypes nào được phép?
- Subtype nào đóng, subtype nào tiếp tục sealed?
- Có extension point bên ngoài module không?
- Khi thêm command mới, client có cần cập nhật code/migration không?
- Handler không nhận ra một biến thể mới sẽ trả lỗi, chuyển đến plugin dispatcher hay từ chối ngay từ khâu parse?

**Không có cấu trúc nào luôn tối ưu.** Sealed hierarchy có giá trị cao khi domain có một tập biến thể có giới hạn và chủ ứng dụng muốn compiler bắt các nhánh còn thiếu. Nó kém phù hợp nếu tính năng cốt lõi là bên ngoài tự do khai báo loại lệnh mới không cần phát hành lại mã lõi.

## 18. Tương thích Java và thay đổi API

### 18.1. Java 17 đã hỗ trợ sealed và record nhưng chưa có record patterns final

Có thể viết một phiên bản tương thích Java 17 bằng `instanceof` type patterns:

```java
static String describeJava17(
        SealedCommandHierarchyDemo.Command command) {
    if (command instanceof SealedCommandHierarchyDemo.PlaceOrder placed) {
        return "place:" + placed.orderId();
    }
    if (command instanceof SealedCommandHierarchyDemo.CancelOrder cancelled) {
        return "cancel:" + cancelled.orderId();
    }
    if (command instanceof SealedCommandHierarchyDemo.PackOrder packed) {
        return "pack:" + packed.orderId();
    }
    if (command instanceof SealedCommandHierarchyDemo.ShipOrder shipped) {
        return "ship:" + shipped.orderId();
    }
    throw new IllegalArgumentException("unsupported command");
}
```

Đây là **đoạn minh họa**, dùng các kiểu từ chương trình cùng package. Phần cú pháp `instanceof Type name` là Java 17 hợp lệ; tuy nhiên **chương trình đầy đủ ở mục 7 cần Java 21** do dùng pattern switch và record patterns. Nếu thật sự phát hành artifact Java 17, phải viết phiên bản toàn bộ module chỉ dùng tính năng Java 17 và biên dịch với `javac --release 17`.

### 18.2. Thêm một subtype là thay đổi hợp đồng API

Khi bổ sung `RefundOrder` hoặc `ReturnOrder` vào sealed set, **client recompile** có thể nhận lỗi thiếu case ở switch exhaustive. Đó là một lợi ích về tính an toàn khi phát triển, nhưng cũng là tác động cần thông báo.

Với **separate compilation** (code client được biên dịch với hierarchy cũ nhưng chạy cùng thư viện mới), một switch exhaustive đã biên dịch có thể gặp subtype mới không được dự liệu và ném `MatchException` ở runtime. Không nên cam kết binary compatibility chỉ dựa vào việc compiler bản thư viện mới pass; cần test với các phiên bản client được hỗ trợ.

### 18.3. Versioned command schema

Nếu command được lưu trong queue hoặc database để phát lại sau nhiều tháng, một subtype đã xóa/đổi tên có thể khiến dữ liệu lịch sử không giải mã được. Cần strategy cho versioning, schema migration và compatibility của message, độc lập với tính năng sealed của Java.

## 19. Anti-pattern trong thiết kế command hierarchy

### 19.1. Dùng chuỗi để dispatch thay vì kiểu

`if ("SHIP".equals(command.type())) ...` dễ sai chính tả và làm một generic object phải có rất nhiều trường optional. Sealed records thường rõ hơn cho tập lệnh đóng. Tuy nhiên, ở API wire vẫn cần loại message; có thể ánh xạ discriminator sang một command type an toàn trong adapter.

### 19.2. Tạo một record khổng lồ cho mọi command

Một `GenericCommand` có `orderId`, `amount`, `reason`, `parcelCount`, `address` dù mỗi thao tác chỉ dùng một phần tạo nhiều tổ hợp dữ liệu vô nghĩa. Tách record theo yêu cầu cụ thể giảm độ phức tạp ở handler.

### 19.3. Dùng `non-sealed` khi thực chất muốn một tập đóng

Nếu mọi implementation nội bộ được biết trước và nghiệp vụ muốn compiler nhắc khi xuất hiện lệnh mới, mở một nhánh `non-sealed` không cần thiết làm yếu tính đóng của hierarchy. Chỉ mở khi có use case extension thực.

### 19.4. Dùng `default` để bỏ qua subtype mới

Một `default -> new Rejected("unsupported")` có thể giấu việc handler chưa được cập nhật khi thêm direct subtype. Với sealed hierarchy đóng, để switch exhaustive nhắc thiếu case là một lợi thế.

### 19.5. Trộn command với event

`ShipOrder` là lời yêu cầu, `OrderShipped` là sự kiện đã xảy ra. Dùng một sealed root cho cả hai thường làm sai ranh giới thời điểm và validation. Tách các hierarchy theo vai trò.

### 19.6. Dùng pattern guard cho mọi điều kiện nghiệp vụ

`when` phù hợp với phân nhánh cục bộ, thuần và dễ đọc. Việc gọi database, kiểm tra quyền hoặc thay đổi trạng thái ngay trong guard khiến matching khó dự đoán. Nên chuyển việc đó vào handler/domain service.

### 19.7. Nghĩ sealed/record là bảo đảm authorization và concurrency

Compiler kiểm tra kiểu; transaction, idempotency và quyền truy cập đòi kiểm tra riêng. Một command có cấu trúc hợp lệ vẫn có thể bị từ chối theo trạng thái hoặc chính sách bảo mật.

### 19.8. Dùng inheritance cho các command không có hợp đồng chung

Nếu một command không có `orderId()` nhưng bị ép thêm trường giả chỉ để implement `Command`, đó là dấu hiệu abstraction sai. Xem lại hợp đồng gốc hoặc tách bounded context.

### 19.9. Phân rã record quá sâu ở dispatch layer

`case ShipOrder(var id, Address(var city, var code))` có giá trị khi handler thật sự dùng các trường. Nếu handler chỉ ủy quyền cho service chuyên trách, `case ShipOrder ship -> shipHandler.handle(ship)` thường giữ ngữ cảnh tốt hơn và tránh ràng buộc logic dispatch vào từng component.

### 19.10. Dựa hoàn toàn vào branch coverage

Test đã chạy đủ bốn subtype không bảo đảm đã kiểm tra các trạng thái từ chối, duplicate requests, null, concurrency hoặc nhập sai domain. Kiểm thử phải đi theo **ma trận command × state × validation**, không chỉ số nhánh switch.

## 20. Checklist thiết kế và review

| Câu hỏi | Dấu hiệu tốt |
| --- | --- |
| Command đại diện cho ý định hay sự kiện đã xảy ra? | Tên động từ và ngữ nghĩa request rõ |
| Tập command là đóng hay cho plugin mở rộng? | Chọn `sealed`/`non-sealed` có chủ đích |
| Các direct permitted subtypes là gì? | `permits` đúng quan hệ trực tiếp |
| Có nhóm command trung gian có ý nghĩa domain không? | `FulfillmentCommand` chia sẻ vai trò/hợp đồng |
| Mỗi command có dữ liệu riêng, đủ và đúng không? | Record components rõ, ít trường optional |
| Constructor kiểm tra gì? | Invariant cục bộ; không nhầm với database state |
| Validation của payload và authorization ở đâu? | Trước/tại handler theo ranh giới rõ |
| Result model có typed không? | `Accepted`/`Rejected` hoặc biến thể tương đương |
| Handler có exhaustive không? | Mọi loại command được xử lý bằng pattern switch |
| Có case rộng đặt trước case hẹp không? | Tránh dominance, guard có fallback |
| Null selector/component có chính sách rõ không? | Assert exception hoặc nhánh null theo hợp đồng |
| Trạng thái chuyển hợp lệ thế nào? | Có sơ đồ và unit tests |
| Retry/idempotency được giải quyết chưa? | Có chiến lược lưu kết quả/khóa trùng |
| Concurrency/transaction có được bảo vệ? | Không dựa vào HashMap mẫu như production |
| Thêm command mới có tác động gì? | Compile tests, migration, versioning, docs |
| Có kiểm thử trên Java release phù hợp không? | JDK 21+ cho pattern switch final; Java 17 nếu dùng dạng thay thế |

## 21. Bài tập và đáp án

**Bài 1 — Direct subtype.** Trong cây `Command permits PlaceOrder, CancelOrder, FulfillmentCommand`, `PackOrder` có phải subtype trực tiếp của `Command` không?

**Đáp án:** không. `PackOrder` trực tiếp implements `FulfillmentCommand`, nên là subtype gián tiếp của `Command`. Tập direct permitted subtype của `Command` chỉ có ba kiểu được liệt kê.

**Bài 2 — Vì sao dùng `sealed` cho FulfillmentCommand?** Hãy so sánh với `non-sealed`.

**Đáp án:** `sealed` giới hạn các lệnh fulfillment vào danh sách được công bố và hỗ trợ exhaustive dispatch. `non-sealed` cho phép implementation khác xuất hiện mà không phải bổ sung vào `permits` của chính nhánh ấy, hữu ích nếu có plugin nhưng làm tập concrete types mở.

**Bài 3 — Record không tự bảo vệ nghiệp vụ.** `record PackOrder(String orderId, int parcelCount)` có tự cấm `parcelCount == -2` không?

**Đáp án:** không. Cần compact constructor/factory kiểm tra số dương hoặc quy tắc phù hợp.

**Bài 4 — Compile-time khác domain validation.** Tại sao `PackOrder("O-1",2)` có kiểu hợp lệ nhưng bị trả `not-found`?

**Đáp án:** compiler bảo đảm lệnh thuộc hierarchy và dữ liệu record có kiểu phù hợp, nhưng handler phải kiểm tra đơn `O-1` tồn tại trong state repository.

**Bài 5 — Trạng thái.** Có đơn `O-1` đang `PLACED`. Tại sao `ShipOrder` bị từ chối trước `PackOrder`?

**Đáp án:** sơ đồ domain yêu cầu `PACKED` trước khi `SHIPPED`; không liên quan đến việc `ShipOrder` có nằm trong sealed hierarchy hay không.

**Bài 6 — Result model.** Vì sao dùng `CommandResult` với `Accepted`/`Rejected` thay cho chỉ trả `boolean`?

**Đáp án:** type kết quả cho phép diễn đạt nhánh được chấp nhận và bị từ chối, mang thông điệp/metadata và dùng pattern matching khi caller xử lý. `boolean` không nêu lý do lỗi và có thể gây nhầm ngữ nghĩa.

**Bài 7 — Guard.** Vì sao `case PlaceOrder(...) when cents >= 100_000` không đủ để xử lý mọi PlaceOrder?

**Đáp án:** những đơn hợp lệ có số tiền thấp hơn guard vẫn cần nhánh khác; nếu không, switch exhaustive có thể thiếu đường xử lý.

**Bài 8 — Nested record pattern.** `case ShipOrder(var id, Address(var city, var code))` có chắc bao phủ mọi `ShipOrder` nếu constructor hiện tại cấm destination null?

**Đáp án:** compiler không chứng minh invariant constructor để coi mẫu lồng là toàn phần trên mọi giá trị có kiểu `ShipOrder`. Bổ sung case `ShipOrder(var id, var destination)` làm fallback cấu trúc khi cần exhaustive.

**Bài 9 — Null.** `Handler.handle(null)` trong ví dụ trả `Rejected` hay ném exception?

**Đáp án:** ném `NullPointerException` với message `command` do `Objects.requireNonNull` được gọi trước switch. Đây là hợp đồng được chọn trong ví dụ, có thể thay bằng thiết kế khác nếu API yêu cầu.

**Bài 10 — Thêm command.** Khi thêm `ReturnOrder` vào `FulfillmentCommand permits`, tại sao `handle` cần xem lại?

**Đáp án:** switch liệt kê bốn record cũ có thể không exhaustive khi recompile. Compiler sẽ chỉ ra việc cần xử lý subtype mới; domain handler và tests phải có chính sách cụ thể cho lệnh trả hàng.

**Bài 11 — Bảo toàn trạng thái.** Với handler in-memory, hai thread đồng thời `PlaceOrder` cùng ID có được đảm bảo chỉ một lệnh thành công không?

**Đáp án:** không. `HashMap` và chuỗi kiểm tra-ghi không an toàn trong môi trường đồng thời. Hệ thống thật cần unique constraint/transaction hoặc cơ chế đồng bộ phù hợp.

**Bài 12 — Command hay event?** Sau khi handler xử lý `ShipOrder` thành công, thông điệp `OrderShipped` (nếu có) thuộc loại nào?

**Đáp án:** đó là domain event mô tả việc đã xảy ra, không phải request command. Cần bảo đảm event phát hành nhất quán với transaction.

**Bài 13 — Java version.** Sealed interface và record classes có thể dùng chính thức từ Java nào? Pattern switch/record patterns trong `handle` thì sao?

**Đáp án:** sealed types ổn định Java 17; records ổn định từ Java 16. Pattern matching for switch và record patterns chính thức từ Java 21. Ví dụ hoàn chỉnh cần `--release 21`.

**Bài 14 — Dấu hiệu thiết kế sai.** Một command `RefreshCatalog` không có orderId nhưng bị thêm `orderId = ""` chỉ để implement interface `Command`. Nên làm gì?

**Đáp án:** xem lại hợp đồng `Command` và bounded context, có thể tách hierarchy hoặc tạo root không buộc mọi command có cùng `orderId()`. Không thêm dữ liệu giả chỉ để thỏa interface.

## 22. Tóm tắt

Thiết kế sealed command hierarchy tốt dựa trên **tập lệnh rõ nghĩa và có giới hạn**, mỗi lệnh có **record data model** và validation cục bộ, handler dùng **pattern switch exhaustive** để dispatch, còn domain layer chịu trách nhiệm trạng thái và các quy tắc nghiệp vụ.

Những điều cần nhớ:

- `permits` xác định **direct** subtypes. Cấu trúc nhiều tầng giúp nhóm lệnh nhưng phải giữ đúng quan hệ trực tiếp/gián tiếp.
- `record` tạo value-like command data, không thay thế validation, authorization, transaction hoặc idempotency.
- `switch` trên sealed hierarchy giúp compiler nhắc khi thêm subtype; tránh dùng `default` chỉ để giấu việc thiếu case.
- Record pattern phân rã component theo cấu trúc; guard `when` cần đường xử lý khi guard không khớp.
- **Command khác event và result**: yêu cầu có thể bị từ chối; thành công trong ví dụ không tự có nghĩa ghi dữ liệu bền vững.
- Compiler checks và behavior tests cần đi cùng nhau. Kiểm tra cả **command type × state × invalid input**, không chỉ có một test cho mỗi case.
- Java 21+ cần cho mẫu switch/record patterns trong chương trình đầy đủ; dùng `--release` phù hợp môi trường hỗ trợ.

**Tài liệu tham khảo chính thức:**
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 395 — Records](https://openjdk.org/jeps/395)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Switch Statements và Pattern Matching](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html)
- [Java SE 21 — The javac Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
