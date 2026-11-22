# Biểu diễn event bằng sealed hierarchy trong Java

Trong một domain model, **event** biểu diễn một sự kiện **đã xảy ra** và có ý nghĩa với nghiệp vụ: đơn hàng được tạo, thanh toán đã được ghi nhận, hàng được giao, đơn bị hủy. Khi các sự kiện có cấu trúc dữ liệu khác nhau nhưng cùng thuộc một nhóm, Java cho phép mô hình hóa chúng bằng **`sealed interface` (hoặc `sealed class`) kết hợp `record`**. Sau đó, **pattern matching** trong `switch` có thể phân nhánh theo từng biến thể event và được compiler kiểm tra độ bao phủ.

Bài này thuộc **Java Core Pattern Matching → Thiết kế domain model**, tập trung vào cách thiết kế **event type hierarchy** đóng, phân rã payload bằng record patterns, xử lý event với `switch expression`, bảo đảm an toàn kiểu và phân biệt các bảo đảm compile time với validation runtime.

**Phiên bản Java:** `sealed` ổn định từ Java 17 (JEP 409), `record` từ Java 16 (JEP 395), record patterns và pattern matching for `switch` ổn định từ **Java 21** (JEP 440, JEP 441). Ví dụ hoàn chỉnh sử dụng Java 21+, không cần bật preview.

## 1. Event là gì, khác command như thế nào?

- **Command** diễn đạt một yêu cầu hoặc ý định: “Hãy tạo đơn hàng”, “Hãy giao đơn hàng”. Command có thể bị từ chối vì nghiệp vụ chưa cho phép.
- **Domain event** diễn đạt một sự thật nghiệp vụ **đã xảy ra**: `OrderPlaced`, `PaymentReceived`, `OrderShipped`, `OrderCancelled`. Tên event thường ở dạng quá khứ để người đọc phân biệt với hành động sắp thực hiện.
- **State** là trạng thái hiện tại của một aggregate; nhiều hệ thống có thể tính hoặc cập nhật state khi xử lý các event phù hợp.

Ví dụ trình tự:

```text
OrderPlaced("O-7", 12500)
    ↓
PaymentReceived("O-7", "pay-1")
    ↓
OrderShipped("O-7", "TRK-9")
    ↓
OrderState(status = SHIPPED, totalCents = 12500)
```

Đây là ví dụ về **biểu diễn event** và cập nhật state, không tự động biến ứng dụng thành hệ thống event sourcing. Event sourcing còn yêu cầu lưu event bền vững, kiểm soát phiên bản, thứ tự, replay và các bảo đảm vận hành khác.

### Tại sao không dùng một record chứa `String type`?

Một cách làm dễ gặp:

```java
// Thiết kế có nhiều trạng thái dữ liệu không hợp lệ.
record GenericEvent(
    String type,
    String orderId,
    Long totalCents,
    String paymentRef,
    String trackingCode,
    String cancellationReason
) {}
```

Với thiết kế này, `type = "ORDER_PLACED"` vẫn có thể đi kèm `trackingCode` và không có `totalCents`; compiler không biết trường nào bắt buộc cho từng loại event. Đoạn xử lý thường cần so sánh chuỗi, ép kiểu hoặc kiểm tra hàng loạt trường `null`.

**Sealed hierarchy + record** tách mỗi trường hợp thành một kiểu riêng và tránh “một đối tượng chứa mọi trường tùy chọn”. Dù vậy, compiler vẫn không thể tự bảo đảm từng giá trị component hợp lệ về mặt nghiệp vụ.

## 2. Khai báo sealed hierarchy cho họ domain event

Ví dụ Java 21+:

```java
sealed interface OrderEvent
        permits OrderPlaced, PaymentReceived, OrderShipped, OrderCancelled {
    String orderId();
}

record OrderPlaced(String orderId, long totalCents) implements OrderEvent {}
record PaymentReceived(String orderId, String paymentRef) implements OrderEvent {}
record OrderShipped(String orderId, String trackingCode) implements OrderEvent {}
record OrderCancelled(String orderId, String reason) implements OrderEvent {}
```

Các đoạn ở đây minh họa cấu trúc; chương trình độc lập có đầy đủ lớp bao ngoài ở phần 6.

### Từng phần có ý nghĩa gì?

1. **`sealed interface OrderEvent`** xác định một họ event có số biến thể được kiểm soát.
2. **`permits`** liệt kê bốn kiểu triển khai trực tiếp được phép. Một kiểu tùy ý khác không thể âm thầm `implements OrderEvent` khi không thỏa quy tắc của sealed hierarchy.
3. **`record OrderPlaced(...)`** và các record còn lại mang payload khác nhau. Record là `final` ngầm định, phù hợp với vai trò kiểu lá trong hierarchy.
4. **`String orderId();`** trên interface là hợp đồng dùng chung. Vì mỗi record đều có component `String orderId`, accessor `orderId()` được sinh ra đáp ứng phương thức của interface.
5. Các component còn lại phản ánh dữ liệu gắn với đúng sự kiện: đơn vừa đặt có tổng tiền, thanh toán có mã tham chiếu, vận chuyển có tracking code, hủy có lý do.

Nhờ có interface chung, một phương thức có thể nhận `OrderEvent` mà không cần chấp nhận mọi `Object` không liên quan:

```java
// Trích đoạn minh họa.
void publish(OrderEvent event) {
    // Hệ thống gọi từ phương thức này sẽ biết event thuộc họ OrderEvent.
}
```

Nếu nghiệp vụ có biến thể mới `OrderReturned`, phải **thêm kiểu mới vào hierarchy và xử lý những nơi phụ thuộc**. Đây là chủ đích: tập event cần được quản lý như một hợp đồng domain, không tự mở rộng tùy ý.

### Cấu trúc mã nguồn

Trong chương trình độc lập phía dưới, interface và record được khai báo **lồng trong một lớp `public`** để có thể biên dịch bằng một tệp. Trong dự án thực tế, có thể tách ra những tệp hoặc package phù hợp với quy tắc của Java về `sealed` và `permits`, và đặt mức hiển thị API theo nhu cầu. Đừng biến các type cần giữ nội bộ thành `public` chỉ vì ví dụ dùng một tệp.

## 3. Dùng `switch expression` xử lý hết các biến thể

Khi selector có kiểu tĩnh `OrderEvent`, compiler biết tập các biến thể được phép. Ta có thể viết `switch expression` **không có `default`**:

```java
// Trích đoạn nằm trong phương thức trả String, 'event' là OrderEvent.
return switch (event) {
    case OrderPlaced(var id, var total) -> "Placed: " + id;
    case PaymentReceived(var id, var ref) -> "Paid: " + id;
    case OrderShipped(var id, var code) -> "Shipped: " + id;
    case OrderCancelled(var id, var reason) -> "Cancelled: " + id;
};
```

Mỗi nhánh chứa một **record pattern**: compiler kiểm tra kiểu record và suy luận kiểu của các component; ví dụ `total` là `long`, `id` là `String`. Không cần gọi `event.getClass()` rồi ép kiểu thủ công.

**Lợi ích của exhaustive switch:** Nếu bỏ nhánh `OrderCancelled`, `switch expression` không còn bao phủ mọi biến thể `OrderEvent` và compiler sẽ báo lỗi. Nếu mở rộng hierarchy bằng một kiểu được phép mới, các switch exhaustive không có `default` có thể yêu cầu cập nhật khi biên dịch lại.

**Khi nào nên có `default`?** Nếu selector thuộc một tập mở, ví dụ `Object` chứa những kiểu không giới hạn, hoặc nghiệp vụ thực sự muốn một chính sách fallback. Đối với sealed hierarchy được thiết kế là tập đóng, một `default` quá rộng có thể **che mất tín hiệu compiler** khi thêm event mới.

### `null` có phải là biến thể thứ năm?

Không. `null` không phải một record event. Trong `switch` trên tham chiếu, nếu selector là `null` và không có nhánh xử lý phù hợp, việc đánh giá thường gây `NullPointerException`. Có thể chọn rõ một trong hai chính sách:

- Không cho phép event null, dùng `Objects.requireNonNull(event, "event")` ở đầu phương thức để từ chối ngay.
- Nếu null có ý nghĩa nghiệp vụ, dùng `case null -> ...`.

Trong chương trình mẫu, một event null là dữ liệu không hợp lệ, vì vậy sẽ bị từ chối trước `switch`. Không đánh đồng `default` với xử lý null.

## 4. Pattern guard giúp phân loại một biến thể theo dữ liệu

Có trường hợp vẫn là `OrderPlaced` nhưng muốn diễn đạt đơn giá trị cao khác với đơn thông thường:

```java
// Trích đoạn switch expression trên OrderEvent.
return switch (event) {
    case OrderPlaced(var id, var total) when total >= 10_000 ->
            "Large placement " + id;
    case OrderPlaced(var id, var total) -> "Placement " + id;
    case PaymentReceived(var id, var ref) -> "Payment " + id;
    case OrderShipped(var id, var code) -> "Shipment " + id;
    case OrderCancelled(var id, var reason) -> "Cancellation " + id;
};
```

Ở đây:

- Nhánh `OrderPlaced(...) when total >= 10_000` chạy khi vừa khớp record vừa thỏa guard.
- Nhánh `OrderPlaced(...)` đứng sau xử lý những đơn còn lại, giúp bao phủ đầy đủ biến thể này.
- Pattern variable `total` tồn tại trong guard vì compiler biết pattern đã khớp trước khi đánh giá điều kiện.
- Nếu đặt nhánh `OrderPlaced(...)` không guard **trước** nhánh có guard, nhánh sau bị che (**dominated case**) và Java có thể báo lỗi biên dịch.

Guard phù hợp để phân loại một giá trị, nhưng đừng biến `when` thành nơi thực hiện I/O, thanh toán, cập nhật cơ sở dữ liệu hoặc tác vụ có side effect. Trong một domain model dễ kiểm thử, các nhánh xử lý sự kiện nên có mục đích rõ ràng và phần phân loại nên thuần nhất có thể.

## 5. Áp dụng event vào trạng thái: compiler giúp phần nào?

Trong hệ thống đơn hàng, thứ tự thông thường có thể là:

```text
(chưa có đơn) --OrderPlaced--> PLACED
PLACED       --PaymentReceived--> PAID
PAID         --OrderShipped--> SHIPPED
PLACED/PAID  --OrderCancelled--> CANCELLED
```

Một hàm nhận **state hiện tại + event**, rồi trả về **state mới** thường được gọi là **reducer** hoặc **event application function**:

```java
// Mẫu chữ ký; định nghĩa lớp và phương thức đầy đủ ở phần 6.
static OrderState apply(OrderState state, OrderEvent event)
```

Lợi ích từ thiết kế kiểu:

- Đầu vào là `OrderEvent`, không phải chuỗi tên event không kiểm soát.
- Compiler buộc `switch expression` xử lý hết các kiểu event được phép khi không có `default`.
- Record pattern trích đúng payload của từng loại; không thể nhầm accessor `trackingCode()` của `OrderShipped` với `paymentRef()` của `PaymentReceived`.
- Kết quả trả về luôn thuộc kiểu `OrderState` nếu nhánh hoàn tất bình thường.

**Những việc compiler không tự bảo đảm:** `PaymentReceived` có thực sự đến sau `OrderPlaced` không? Một event có trùng ID với aggregate không? Tổng tiền có dương không? Tracking code có rỗng không? Người dùng có quyền hủy đơn không? Những điều này cần **validation runtime**, hợp đồng API và test.

Trong code mẫu, nếu một trạng thái chuyển không hợp lệ, hàm ném ngoại lệ rõ ràng. Trong hệ thống event sourcing thực tế, việc phát hiện chuỗi event không hợp lệ thường là tín hiệu dữ liệu lịch sử bị hỏng hoặc event không đúng phiên bản, cần chính sách vận hành và xử lý cụ thể; không nên chỉ nuốt lỗi.

## 6. Ví dụ Java 21+ hoàn chỉnh và chạy được

Tạo tệp **`SealedOrderEventsDemo.java`**:

```java
public class SealedOrderEventsDemo {
    sealed interface OrderEvent
            permits OrderPlaced, PaymentReceived, OrderShipped, OrderCancelled {
        String orderId();
    }

    record OrderPlaced(String orderId, long totalCents) implements OrderEvent {}
    record PaymentReceived(String orderId, String paymentRef) implements OrderEvent {}
    record OrderShipped(String orderId, String trackingCode) implements OrderEvent {}
    record OrderCancelled(String orderId, String reason) implements OrderEvent {}

    enum Status { PLACED, PAID, SHIPPED, CANCELLED }
    record OrderState(String orderId, Status status, long totalCents) {}

    static void requireStatus(OrderState state, Status expected) {
        if (state == null || state.status() != expected) {
            throw new IllegalStateException("Expected status " + expected);
        }
    }

    static OrderState apply(OrderState state, OrderEvent event) {
        java.util.Objects.requireNonNull(event, "event");

        if (state != null && !state.orderId().equals(event.orderId())) {
            throw new IllegalArgumentException("Mismatched order id");
        }

        return switch (event) {
            case OrderPlaced(var id, var total) -> {
                if (state != null) {
                    throw new IllegalStateException("Order already exists");
                }
                if (id == null || id.isBlank() || total <= 0) {
                    throw new IllegalArgumentException("Invalid placement");
                }
                yield new OrderState(id, Status.PLACED, total);
            }

            case PaymentReceived(var id, var paymentRef) -> {
                requireStatus(state, Status.PLACED);
                if (paymentRef == null || paymentRef.isBlank()) {
                    throw new IllegalArgumentException("Missing payment ref");
                }
                yield new OrderState(id, Status.PAID, state.totalCents());
            }

            case OrderShipped(var id, var trackingCode) -> {
                requireStatus(state, Status.PAID);
                if (trackingCode == null || trackingCode.isBlank()) {
                    throw new IllegalArgumentException("Missing tracking code");
                }
                yield new OrderState(id, Status.SHIPPED, state.totalCents());
            }

            case OrderCancelled(var id, var reason) -> {
                if (state == null
                        || state.status() == Status.SHIPPED
                        || state.status() == Status.CANCELLED) {
                    throw new IllegalStateException("Cannot cancel in current status");
                }
                if (reason == null || reason.isBlank()) {
                    throw new IllegalArgumentException("Missing cancellation reason");
                }
                yield new OrderState(id, Status.CANCELLED, state.totalCents());
            }
        };
    }

    static String describe(OrderEvent event) {
        java.util.Objects.requireNonNull(event, "event");

        return switch (event) {
            case OrderPlaced(var id, var total) when total >= 10_000 ->
                    "Large placement " + id;
            case OrderPlaced(var id, var total) -> "Placement " + id;
            case PaymentReceived(var id, var ref) -> "Payment " + id;
            case OrderShipped(var id, var code) -> "Shipment " + id;
            case OrderCancelled(var id, var reason) -> "Cancellation " + id;
        };
    }

    public static void main(String[] args) {
        OrderEvent[] timeline = {
                new OrderPlaced("O-7", 12_500),
                new PaymentReceived("O-7", "pay-1"),
                new OrderShipped("O-7", "TRK-9")
        };

        OrderState state = null;
        for (OrderEvent event : timeline) {
            state = apply(state, event);
            System.out.println(describe(event) + " -> " + state.status());
        }

        System.out.println("Final: " + state.orderId() + "/" + state.status()
                + "/" + state.totalCents());

        OrderState another = apply(null, new OrderPlaced("O-8", 500));
        another = apply(another, new OrderCancelled("O-8", "Changed mind"));
        System.out.println("Cancelled: " + another.status());

        try {
            apply(state, new OrderCancelled("O-7", "Late request"));
        } catch (IllegalStateException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }

        try {
            apply(state, new PaymentReceived("OTHER", "pay-x"));
        } catch (IllegalArgumentException ex) {
            System.out.println("Rejected: " + ex.getMessage());
        }
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac --release 21 -encoding UTF-8 SealedOrderEventsDemo.java
java SealedOrderEventsDemo
```

Đầu ra:

```text
Large placement O-7 -> PLACED
Payment O-7 -> PAID
Shipment O-7 -> SHIPPED
Final: O-7/SHIPPED/12500
Cancelled: CANCELLED
Rejected: Cannot cancel in current status
Rejected: Mismatched order id
```

### Vì sao ví dụ hoạt động như vậy?

1. `OrderPlaced("O-7", 12500)` hợp lệ khi `state == null`. Hàm `apply` tạo `OrderState` mới ở trạng thái `PLACED`. Phương thức `describe` chọn nhánh guard vì `12500 >= 10000`.
2. `PaymentReceived("O-7", "pay-1")` yêu cầu state trước là `PLACED`; reducer chuyển sang `PAID` và giữ `totalCents`.
3. `OrderShipped("O-7", "TRK-9")` yêu cầu state trước là `PAID`, nên chuyển sang `SHIPPED`.
4. Với một đơn mới `O-8`, event `OrderCancelled` được áp dụng sau khi đặt hàng; vì chưa ship và chưa hủy nên state chuyển sang `CANCELLED`.
5. Hủy `O-7` sau khi state đã `SHIPPED` bị từ chối vì quy tắc nghiệp vụ trong `apply`, **không phải vì compiler cấm tạo đối tượng `OrderCancelled`**.
6. Event `PaymentReceived("OTHER", "pay-x")` có `orderId` không khớp với state `O-7`. Hàm từ chối trước khi chọn pattern.
7. `Objects.requireNonNull(event, "event")` thể hiện rõ event `null` là dữ liệu đầu vào không hợp lệ. Vì vậy `switch` không cần `case null` để biểu diễn một loại event.

**Vì sao dùng `yield`?** Mỗi nhánh reducer có nhiều lệnh kiểm tra rồi cần sinh ra `OrderState` mới. `yield` trả giá trị của nhánh cho **`switch expression`**. `return` sẽ kết thúc phương thức; trong code trên, `return switch (...)` trả toàn bộ kết quả biểu thức.

## 7. Thiết kế event tốt: những quyết định cần rõ ràng

### 7.1. Một event = một sự thật có ý nghĩa

Đặt tên biến thể theo điều đã xảy ra, ví dụ `PaymentReceived`, không gọi `PayOrder` nếu đó thực chất là yêu cầu. Đặt component theo nội dung sự kiện và đơn vị đo:

- `totalCents` là số tiền tính bằng đơn vị nhỏ nhất; không nên đặt tên `total` khi có nguy cơ nhầm đơn vị.
- `paymentRef` là mã tham chiếu thanh toán, khác `trackingCode` của sự kiện giao hàng.
- `reason` của `OrderCancelled` có thể rỗng hoặc `null` nếu API cho phép, nhưng cần kiểm tra theo hợp đồng.

Hãy giữ event như dữ liệu mô tả quá khứ. Tránh đặt các thao tác gây side effect như gửi email, gọi cổng thanh toán vào accessor hoặc constructor của event.

### 7.2. Record bất biến ở mức tham chiếu component, nhưng không deep immutable

Record components là các thành phần không thể gán lại sau khi khởi tạo, nhưng **không tự động làm bất biến sâu** những đối tượng có thể thay đổi được mà chúng giữ tham chiếu.

```java
// Trích đoạn minh họa: tránh giữ danh sách mutable rồi để lộ ra ngoài.
record ItemsAdded(String orderId, java.util.List<String> skus) {
    ItemsAdded {
        skus = java.util.List.copyOf(skus);
    }
}
```

Với record chứa `List`, tạo bản sao bất biến khi xây dựng giúp bảo vệ nội dung danh sách khỏi sửa đổi qua tham chiếu gốc; nếu phần tử trong danh sách vẫn mutable thì cần cân nhắc deep copy tương ứng. `List.copyOf` từ chối phần tử `null` và chính danh sách `null`, nên chỉ dùng khi ràng buộc đó phù hợp domain.

Trong ví dụ chính, các component của event là `String` và kiểu nguyên thủy, dễ giữ như các **value-like immutable objects**.

### 7.3. Hợp đồng event dùng chung

Với event production, thường cần thêm metadata như `eventId`, `aggregateId`, `occurredAt`, `schemaVersion`. Có thể:

- Đặt phần metadata chung trong một **envelope** bên ngoài payload.
- Hoặc khai báo những accessor chung trên sealed interface và để record implementations cung cấp dữ liệu tương ứng.

Không nên đặt tất cả metadata vào mọi record nếu nó tạo quá nhiều lặp lại hoặc làm khó đọc. Ví dụ thiết kế envelope:

```java
// Trích đoạn độc lập (Java 21+).
record EventEnvelope(
    String eventId,
    String aggregateId,
    java.time.Instant occurredAt,
    int schemaVersion,
    OrderEvent payload
) {}
```

Lớp envelope này không bắt buộc dùng trong ví dụ reducer, nhưng phù hợp để giải thích sự tách biệt giữa **thông tin phân phối/lưu trữ** và **payload nghiệp vụ**. Có thể thêm validation cho metadata ở constructor hoặc tầng tiếp nhận.

### 7.4. Chọn sealed khi tập biến thể có chủ sở hữu rõ ràng

Sealed hierarchy thích hợp khi một module hoặc bounded context **chủ động quản lý tập biến thể**. Nếu nền tảng cho phép plugin bên ngoài định nghĩa event mới mà không sửa module gốc, sealed hierarchy đóng hoàn toàn có thể là ràng buộc không phù hợp.

Tùy mức mở rộng cần thiết, cân nhắc interface thông thường, hierarchy có nhánh `non-sealed` có kiểm soát, hoặc thiết kế giao tiếp qua schema/message envelope. Tính exhaustive của `switch` phụ thuộc chính xác vào tập kiểu được compiler biết; một nhánh mở cần cách phân nhánh tương ứng.

## 8. Evolution, versioning và ranh giới hệ thống

**Một thay đổi về code không tự nâng cấp các event đã được lưu trước đó.** Trong hệ thống có event log, message broker hoặc dữ liệu JSON, việc thêm/sửa biến thể cần được quản lý cẩn thận:

1. **Thêm biến thể mới:** compiler sẽ giúp tìm những `switch expression` exhaustive không có `default` cần xử lý biến thể đó trong mã nguồn được biên dịch lại.
2. **Thêm field mới vào record:** thay đổi canonical constructor và payload schema. Người tiêu thụ dữ liệu cũ có thể thiếu field mới; cần chính sách tương thích như default value khi deserialization, adapter, hoặc upcasting từ version cũ.
3. **Đổi tên hoặc ý nghĩa event:** có thể phá vỡ hợp đồng tích hợp. Nhiều hệ thống chọn tạo event version mới thay vì đổi nghĩa âm thầm.
4. **Truyền qua JSON/Kafka:** ở runtime, JSON không tự mang sealed subtype theo cơ chế Java; serializer/deserializer cần quy ước nhận dạng biến thể (event type discriminator), validation và xử lý sự kiện không nhận diện được.
5. **Replay và thứ tự:** reducer giả định các event cho cùng một đơn được xử lý theo thứ tự hợp lệ. Hệ thống thực tế phải xem xét ordering, concurrency, idempotency, duplicate delivery và persistence.
6. **Sự kiện đến không đúng thứ tự:** compiler chỉ kiểm tra **kiểu event** chứ không kiểm tra lịch sử nghiệp vụ. Runtime có thể từ chối, trì hoãn hoặc đưa vào cơ chế xử lý ngoại lệ theo hợp đồng hệ thống.

Nếu một event đã **thực sự xảy ra** nhưng không thể áp dụng vào state hiện tại trong quá trình replay, đó có thể là lỗi ordering, schema hoặc dữ liệu; không nên đơn giản “bỏ qua cho chạy tiếp”. Thiết kế cần chỉ rõ cách vận hành khi chuỗi sự kiện không hợp lệ.

## 9. Khi nào cần kiểm tra runtime, không trông chờ compiler?

| Vấn đề | Compiler kiểm tra được? | Cần làm thêm |
| --- | --- | --- |
| Một lớp không được phép trực tiếp triển khai `OrderEvent` | Có, theo quy tắc sealed | Thiết kế rõ mô-đun và quyền mở rộng |
| `switch expression` thiếu một permitted subtype | Có, khi thông tin kiểu cho phép kiểm tra exhaustive | Viết case tương ứng thay vì dùng default mù |
| `case OrderPlaced(...)` dùng sai số lượng component | Có | Khớp đúng record shape |
| `case` rộng che nhánh hẹp hoặc guard | Có thể phát hiện qua dominance | Đặt case cụ thể/guard trước case tổng quát |
| `paymentRef` là chuỗi rỗng hoặc `null` | Không tự biết ràng buộc nghiệp vụ | Constructor validation hoặc runtime guard |
| `PaymentReceived` đến trước `OrderPlaced` | Không | State transition validation, kiểm thử |
| Event thuộc sai `orderId` | Không | Đối chiếu aggregate ID |
| Event bị xử lý lặp (duplicate) | Không | Event ID, deduplication, idempotent handler |
| Consumer đọc event version mới từ dữ liệu lưu trữ | Không tự giải quyết | Versioned schema/adapter/upcaster và strategy cho unknown type |
| Bộ xử lý gây side effect hai lần | Không | Thiết kế transaction, outbox/inbox, retry và idempotency |

**Bài học quan trọng:** Sealed hierarchy mang lại **an toàn kiểu** và tín hiệu khi mở rộng mô hình, không đồng nghĩa với “mọi sự kiện luôn hợp lệ và theo đúng thứ tự”.

## 10. Các lỗi thường gặp khi thiết kế event hierarchy

### Lỗi 1: Một generic event với hàng loạt trường tùy chọn

Khi dùng `GenericEvent(type, orderId, payloadA, payloadB, ...)`, các tổ hợp không hợp lệ xuất hiện dễ dàng. **Khắc phục:** dùng record khác nhau cho các biến thể có payload khác nhau; lựa chọn generic envelope riêng nếu cần metadata.

### Lỗi 2: Thêm `default` cho mọi `switch` sealed

`default` có thể che nhánh event mới khi biên dịch lại. **Khắc phục:** ưu tiên các nhánh cụ thể và exhaustive switch khi tập biến thể đóng; dùng default khi muốn fallback thật sự.

### Lỗi 3: Nghĩ event bất biến thì payload luôn bất biến sâu

Một record chứa `List`, `Map` hoặc đối tượng mutable vẫn có thể lộ trạng thái thay đổi. **Khắc phục:** chọn kiểu immutable/copy hợp lý và bảo vệ invariant.

### Lỗi 4: Nhầm event với command

Tên như `CreateOrder` khiến người đọc không biết đó là yêu cầu hay sự thật đã xảy ra. **Khắc phục:** dùng `OrderPlaced` cho event, `PlaceOrder` cho command nếu hệ thống có cả hai.

### Lỗi 5: Đặt guard sau case tổng quát

Ví dụ `case OrderPlaced(var id, var total) -> ...` đứng trước `case OrderPlaced(var id, var total) when total > 10000 -> ...`. Nhánh sau bị dominated. **Khắc phục:** đặt case có guard trước nhánh cùng kiểu không guard.

### Lỗi 6: Cho rằng record pattern kiểm tra cả nghiệp vụ

`OrderPlaced(var id, var total)` có thể khớp một đối tượng với `total <= 0`; `var id` có thể nhận `null`. **Khắc phục:** validate giá trị tại boundary/constructor/reducer.

### Lỗi 7: Mặc định mọi consumer cùng phiên bản Java và schema

Một event được lưu từ phiên bản cũ không nhất thiết giải mã được bằng kiểu record hiện tại. **Khắc phục:** định nghĩa quy tắc versioning, migration, compatibility và xử lý unknown event.

### Lỗi 8: Dùng `instanceof` dài thay cho exhaustive `switch` mà không có lý do

Chuỗi `if (event instanceof A) ... else if ...` có thể hoạt động, nhưng không buộc compiler kiểm tra bao phủ đầy đủ mọi biến thể như `switch expression` exhaustive. **Khắc phục:** cân nhắc `switch` cho các xử lý phân nhánh theo tất cả subtype.

## 11. Bài tập thực hành

Giả sử một hệ thống kho có hai loại sự kiện:

```java
sealed interface InventoryEvent permits StockAdded, StockRemoved {}
record StockAdded(String sku, int units) implements InventoryEvent {}
record StockRemoved(String sku, int units) implements InventoryEvent {}
```

### Bài 1 — Viết exhaustive `switch expression`

Viết phương thức `int delta(InventoryEvent event)` trả số lượng thay đổi: cộng khi `StockAdded`, trừ khi `StockRemoved`. Không dùng `default`.

**Đáp án:**

```java
static int delta(InventoryEvent event) {
    java.util.Objects.requireNonNull(event, "event");
    return switch (event) {
        case StockAdded(var sku, var units) -> units;
        case StockRemoved(var sku, var units) -> -units;
    };
}
```

Đây là **trích đoạn phương thức**, cần đặt trong lớp chứa hoặc nhìn thấy các khai báo event tương ứng. Trong ứng dụng thực tế phải kiểm tra `units > 0` để giá trị event có ý nghĩa. Với ràng buộc đó, tránh những trường hợp số âm hoặc overflow do đầu vào bất thường.

### Bài 2 — Thêm biến thể

Thêm `record StockReserved(String sku, int units) implements InventoryEvent {}` và sửa `permits`. Điều gì xảy ra với `delta` khi chưa sửa?

**Đáp án:** `switch expression` không còn exhaustive. Compiler yêu cầu xử lý `StockReserved`. Người thiết kế phải quyết định event đặt chỗ có làm thay đổi số lượng tồn vật lý, số lượng khả dụng hay chỉ một trường dự trữ riêng; không thể tùy tiện trả `0` mà không xác định ý nghĩa nghiệp vụ.

### Bài 3 — Dùng guard

Viết `String classify(InventoryEvent event)` với event `StockAdded` có `units >= 100` được gắn nhãn `"large intake"`; các `StockAdded` còn lại là `"intake"`; `StockRemoved` là `"outflow"`.

**Đáp án:**

```java
static String classify(InventoryEvent event) {
    java.util.Objects.requireNonNull(event, "event");
    return switch (event) {
        case StockAdded(var sku, var units) when units >= 100 -> "large intake";
        case StockAdded(var sku, var units) -> "intake";
        case StockRemoved(var sku, var units) -> "outflow";
    };
}
```

Nhánh có guard đứng trước nhánh tổng quát. Cần validation riêng cho `units <= 0` nếu nghiệp vụ không cho phép.

### Bài 4 — Phân biệt compile-time và runtime

Một event `PaymentReceived("O-7", "pay-1")` được tạo trước khi đơn `O-7` tồn tại. Compiler có từ chối việc tạo record này không?

**Đáp án:** Không. Kiểu record hợp lệ nên compiler chấp nhận. Logic áp dụng event hoặc service ở runtime phải kiểm tra trạng thái và quyết định từ chối hay xử lý theo chính sách nghiệp vụ.

## 12. Checklist áp dụng vào dự án

Trước khi chọn sealed hierarchy cho event, hãy tự kiểm tra:

1. Tập biến thể có được quản lý bởi một module/bounded context rõ ràng không?
2. Tên event có biểu diễn **sự thật đã xảy ra** chứ không phải command không?
3. Mỗi event có payload tối thiểu, đúng kiểu và đúng đơn vị đo không?
4. Metadata phân phối/lưu trữ có được tách hợp lý khỏi dữ liệu nghiệp vụ không?
5. Các `switch expression` trên hierarchy có exhaustive và tránh `default` che trường hợp mới không?
6. Trường hợp `null`, input sai, duplicate, out-of-order và ID không khớp được xử lý ở đâu?
7. Có chiến lược cho event persistence, serialization, schema version và replay không?
8. Có test cho từng loại event và từng trạng thái chuyển không?

**Ghi nhớ:** `sealed` kiểm soát **những event type nào có thể tồn tại trong một hierarchy**, `record` mô tả **mỗi event mang dữ liệu gì**, còn pattern matching + `switch` diễn đạt **cách xử lý từng biến thể**. Kết hợp đúng giúp domain model dễ đọc, dễ mở rộng có kiểm soát và được compiler hỗ trợ khi tiến hóa. Quy tắc chuyển trạng thái, validation dữ liệu và vận hành event vẫn cần được thiết kế và kiểm thử riêng.

**Nguồn chính thức:** [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409), [JEP 395 — Records](https://openjdk.org/jeps/395), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html).
