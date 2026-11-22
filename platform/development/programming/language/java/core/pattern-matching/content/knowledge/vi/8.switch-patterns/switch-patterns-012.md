# Cấu trúc switch dễ mở rộng trong Java 21

## 1. Mục tiêu: mở rộng hành vi mà không làm switch khó kiểm soát

Một `switch` bắt đầu với hai hoặc ba trường hợp thường rất dễ đọc. Nhưng khi nghiệp vụ tăng số biến thể, thêm điều kiện ưu tiên, xử lý `null` hoặc tích hợp nhiều dịch vụ, một `switch` có thể trở thành chỗ tập trung quá nhiều thay đổi.

**Cấu trúc switch dễ mở rộng** là cách tổ chức mà người bảo trì có thể:

- Nhìn vào danh sách `case` để hiểu những biến thể dữ liệu hiện có.
- Biết nơi nào phải cập nhật khi thêm một biến thể mới.
- Nhờ compiler phát hiện thiếu nhánh khi làm việc với một **tập biến thể đóng**.
- Thêm điều kiện đặc biệt mà không vô tình che khuất trường hợp tổng quát.
- Tách phần **chọn nhánh** khỏi phần **xử lý nghiệp vụ dài**.
- Test mỗi biến thể, chính sách `null` và các ngưỡng điều kiện.

Trong Java 21, các công cụ phù hợp gồm **pattern matching for switch** (JEP 441), **record patterns** (JEP 440), **sealed types**, `switch` expression, `when` guard và switch rules dạng mũi tên `->`.

Ví dụ dạng ý tưởng:

```java
return switch (event) {
    case OrderCreated(var orderId, var customerId) -> ...;
    case PaymentCaptured(var orderId, var amountVnd) -> ...;
    case OrderCancelled(var orderId, var reason) -> ...;
};
```

Đây là **mảnh cú pháp** để thấy cách chia nhánh theo biến thể domain; dấu `...` không phải Java expression hoàn chỉnh. Ở chương trình chạy được phía dưới, các nhánh trả về giá trị thật và tất cả kiểu được khai báo đầy đủ.

**Điểm quan trọng:** dùng pattern `switch` không tự động biến thiết kế thành dễ mở rộng. Khả năng bảo trì phụ thuộc vào **kiểu của selector**, **quy tắc bao phủ nhánh**, **thứ tự case**, **phân chia trách nhiệm** và **kiểm thử**.

## 2. Nhận diện các thành phần trong switch pattern

| Thành phần | Cú pháp mẫu | Vai trò |
| --- | --- | --- |
| Switch expression | `String message = switch (event) { ... };` | Biến một giá trị đầu vào thành một kết quả |
| Switch statement | `switch (event) { case ... -> handle(); }` | Điều phối hành động |
| Type pattern | `case PaymentCaptured payment ->` | Kiểm tra subtype, liên kết cả đối tượng |
| Record pattern | `case PaymentCaptured(var id, var amount) ->` | Kiểm tra record và giải cấu trúc component |
| Guard | `case PaymentCaptured(var id, var amount) when amount > 0 ->` | Thêm điều kiện sau khi pattern đã khớp |
| Null label | `case null ->` | Quy định xử lý selector bằng `null` |
| Default label | `default ->` | Fallback cho các giá trị khác không có nhánh phù hợp |
| Sealed hierarchy | `sealed interface Event permits A, B` | Giới hạn tập subtype được phép |

`when` là **guard**, không phải loại pattern mới. `case null` và `default` là nhãn, không phải type/record pattern. Các biến như `amount` hoặc `id` trong pattern chỉ có scope tại vị trí được Java chứng minh match thành công.

## 3. Cấu trúc domain bằng sealed interface và record

Giả sử một hệ thống cần phản ứng với ba loại sự kiện đơn hàng:

```java
sealed interface OrderEvent
        permits OrderCreated, PaymentCaptured, OrderCancelled {}

record OrderCreated(String orderId, String customerId)
        implements OrderEvent {}

record PaymentCaptured(String orderId, long amountVnd)
        implements OrderEvent {}

record OrderCancelled(String orderId, String reason)
        implements OrderEvent {}
```

Đây là **mảnh khai báo**, có thể đặt trong một source file ở phạm vi thích hợp. Phần chương trình hoàn chỉnh bên dưới đặt chúng thành các nested declarations của một class.

Mỗi biến thể nói rõ dữ liệu riêng:

- `OrderCreated`: mã đơn và mã khách hàng.
- `PaymentCaptured`: mã đơn và số tiền đã thu tính bằng VND.
- `OrderCancelled`: mã đơn và lý do hủy.

`sealed` giới hạn các subtype trực tiếp của `OrderEvent`. Các `record` là `final`, nên ví dụ tạo thành một **tập biến thể đóng** phù hợp để compiler kiểm tra exhaustiveness.

Đây là tiền đề quan trọng: nếu selector chỉ mang kiểu `Object`, compiler không thể biết domain của bạn chỉ có ba biến thể. Nếu selector có kiểu tĩnh `OrderEvent`, tập subtype được phép đã thể hiện ngay trong mô hình.

### 3.1. Switch expression xử lý toàn bộ subtype

```java
static String code(OrderEvent event) {
    return switch (event) {
        case OrderCreated created -> "CREATED";
        case PaymentCaptured payment -> "CAPTURED";
        case OrderCancelled cancelled -> "CANCELLED";
    };
}
```

Mỗi nhánh khớp một subtype được phép. Với kiểu `OrderEvent`, đây là `switch` expression **exhaustive**, không cần `default`.

**Chú ý `null`:** ba type pattern trên không nhận `null`. Gọi switch với selector `null` mà không xử lý riêng có thể dẫn tới `NullPointerException`. Exhaustiveness về subtype không có nghĩa là tự xử lý `null`.

Nếu `null` là đầu vào hợp lệ của API:

```java
static String codeOrMissing(OrderEvent event) {
    return switch (event) {
        case null -> "MISSING";
        case OrderCreated created -> "CREATED";
        case PaymentCaptured payment -> "CAPTURED";
        case OrderCancelled cancelled -> "CANCELLED";
    };
}
```

Còn nếu `null` là lỗi lập trình, có thể dùng `Objects.requireNonNull(event)` trước switch và không cần biến lỗi thành một status bình thường.

## 4. Bỏ default khi muốn compiler nhắc xử lý subtype mới

Với **domain đóng** mà mọi subtype đều cần cách xử lý riêng, không thêm `default` chỉ để đoạn mã luôn biên dịch.

Giả sử ngày mai xuất hiện:

```java
record OrderReturned(String orderId, String reason)
        implements OrderEvent {}
```

Đồng thời danh sách `permits` của `OrderEvent` được cập nhật để chấp nhận `OrderReturned`. Khi biên dịch lại các module cùng hierarchy mới, một switch expression chỉ có ba case cũ sẽ bị compiler yêu cầu xử lý đủ trường hợp. Đó là tín hiệu bảo trì tích cực.

Nếu switch có:

```java
default -> "OTHER";
```

thì subtype mới có thể bị lặng lẽ đưa vào nhánh chung. Điều này có thể không chấp nhận được khi hành vi mới đòi hỏi cập nhật audit, tính tiền, thông báo hoặc phân quyền.

**Nguyên tắc thực hành:**

- **Domain đóng:** xử lý từng subtype, ưu tiên exhaustive switch không có `default` khi cần đảm bảo không bỏ sót biến thể.
- **Domain mở:** `default` hữu ích để thể hiện chính sách với dữ liệu chưa hỗ trợ.
- **Từ dữ liệu bên ngoài:** thường nên kiểm tra và chuyển đổi sang mô hình domain trước; không giữ `Object` xuyên suốt lõi nghiệp vụ.

Đây là hai kiểu ví dụ tương phản:

```java
// Domain đóng (mảnh ví dụ):
switch (event) {
    case OrderCreated created -> handleCreated(created);
    case PaymentCaptured payment -> handlePayment(payment);
    case OrderCancelled cancelled -> handleCancelled(cancelled);
}

// Đầu vào mở (mảnh ví dụ):
switch (payload) {
    case null -> handleMissing();
    case String text -> handleText(text);
    case byte[] bytes -> handleBytes(bytes);
    default -> handleUnsupported(payload);
}
```

Các hàm `handle...` là placeholder **nghiệp vụ mang tính minh họa**, không phải chương trình tự chạy; các hàm thực tế phải được định nghĩa. Khác biệt quan trọng ở đây là chính sách bao phủ nhánh, không phải tên hàm.

### 4.1. Giới hạn của exhaustiveness khi runtime lệch phiên bản

Compiler kiểm tra theo các kiểu mà nó biết **khi biên dịch**. Nếu một thư viện sealed hierarchy được cập nhật độc lập sau khi mã switch đã biên dịch, có thể xảy ra trường hợp runtime gặp subtype mới mà mã cũ không nhận diện. Trong Java 21, switch exhaustive nhưng không tìm thấy nhánh khớp trong hoàn cảnh tương thích bất thường có thể ném `MatchException`.

Vì vậy, exhaustive checking **không thay thế** việc biên dịch lại các module liên quan, kiểm thử tích hợp và quản lý phiên bản khi triển khai.

## 5. Record pattern giúp case thể hiện dữ liệu cần sử dụng

Khi một nhánh chỉ cần các component của record, record pattern giúp người đọc thấy ngay đầu vào:

```java
static String describe(OrderEvent event) {
    return switch (event) {
        case null -> "missing event";
        case OrderCreated(var orderId, var customerId) ->
            "created " + orderId + " for " + customerId;
        case PaymentCaptured(var orderId, var amountVnd) ->
            "paid " + orderId + ": " + amountVnd + " VND";
        case OrderCancelled(var orderId, var reason) ->
            "cancelled " + orderId + ": " + reason;
    };
}
```

`OrderCreated(var orderId, var customerId)` là một **record pattern**. Java lấy component theo **thứ tự khai báo** của record, không dựa trên tên biến `orderId` hay `customerId`. Đặt tên phù hợp với domain giúp ngăn hiểu nhầm khi nhiều component có cùng kiểu `String`.

Khi chỉ cần phân loại subtype mà **không cần component**, type pattern có thể đơn giản hơn:

```java
case OrderCreated created -> "CREATED"
```

Đừng giải cấu trúc toàn bộ record một cách máy móc nếu nhánh không sử dụng những giá trị đó. Mục tiêu là diễn đạt vừa đủ thông tin để bảo trì.

### 5.1. Khi nested patterns bắt đầu khó đọc

Nếu dữ liệu có record lồng nhiều tầng, một pattern dài có thể hữu ích để lấy đúng thành phần:

```java
record Customer(String id, String displayName) {}
record Delivery(Customer customer, String trackingCode) {}

// Mảnh biểu thức minh họa:
if (value instanceof Delivery(
        Customer(var customerId, var customerName),
        var trackingCode)) {
    System.out.println(customerName + ": " + trackingCode);
}
```

Nhưng khi nested record pattern làm một case trải dài hàng chục dòng, hãy cân nhắc liên kết toàn bộ đối tượng `Delivery delivery` rồi chuyển cho một hàm có tên rõ nghĩa. Một cấu trúc dễ mở rộng cần cân bằng giữa **khả năng nhìn thấy dữ liệu cần dùng** và **độ gọn của switch**.

## 6. Guard when: mở rộng trường hợp mà không làm mất nhánh chung

Nghiệp vụ có thể cần phân biệt giao dịch từ `1_000_000` VND trở lên:

```java
static String paymentLabel(OrderEvent event) {
    return switch (event) {
        case null -> "missing";
        case PaymentCaptured(var orderId, var amountVnd)
                when amountVnd >= 1_000_000L ->
            "large payment " + orderId;
        case PaymentCaptured(var orderId, var amountVnd) ->
            "payment " + orderId + ": " + amountVnd + " VND";
        case OrderCreated created -> "order created";
        case OrderCancelled cancelled -> "order cancelled";
    };
}
```

**Luồng lựa chọn:**

1. Java thử pattern `PaymentCaptured(...)`.
2. Nếu khớp, guard `amountVnd >= 1_000_000L` được đánh giá.
3. Guard đúng thì chọn nhánh `large payment`.
4. Guard sai thì nhánh `PaymentCaptured(...)` tổng quát ở sau vẫn có thể nhận sự kiện.

`when` không phải pattern mới mà là phần điều kiện của nhãn `case`. `amountVnd` là pattern variable có phạm vi ở guard và nhánh phù hợp.

### 6.1. Dominance: đặt nhánh rộng trước nhánh hẹp sẽ lỗi

**Mảnh mã cố ý không biên dịch:**

```java
return switch (event) {
    case PaymentCaptured(var id, var amount) -> "payment";
    case PaymentCaptured(var id, var amount)
            when amount >= 1_000_000L -> "large payment"; // Dominated
    default -> "other";
};
```

Nhánh đầu đã bao phủ **mọi** `PaymentCaptured`. Nhánh thứ hai không thể chạy và bị compiler từ chối bởi quy tắc **dominance**.

Cách sửa: nhánh có guard hoặc nhánh cụ thể đứng trước; sau đó mới là nhánh tổng quát. Đây là quy tắc bảo trì quan trọng mỗi lần bổ sung một case mới.

### 6.2. Mốc biên và các guard chồng lấn

Khi có các mức:

```java
case PaymentCaptured(var id, var amount)
        when amount >= 5_000_000L -> "VIP";
case PaymentCaptured(var id, var amount)
        when amount >= 1_000_000L -> "LARGE";
case PaymentCaptured(var id, var amount) -> "STANDARD";
```

đặt mức ưu tiên cao nhất trước, mức còn lại sau, và nhánh tổng quát cuối cùng. Nếu đảo hai guard, số tiền trên 5 triệu có thể rơi vào nhánh `LARGE`.

Compiler không chứng minh tất cả ý nghĩa toán học hoặc tính rời nhau của các điều kiện `when`; cần **test mốc biên**.

## 7. Switch expression và switch statement khác nhau ở nhiệm vụ

Chọn cấu trúc theo việc cần **giá trị kết quả** hay **tác động**.

### 7.1. Dùng switch expression để trả về một giá trị

```java
static String eventType(OrderEvent event) {
    return switch (event) {
        case null -> "MISSING";
        case OrderCreated created -> "CREATED";
        case PaymentCaptured payment -> "PAYMENT";
        case OrderCancelled cancelled -> "CANCELLED";
    };
}
```

Ưu điểm: một biểu thức có kết quả xác định, không phải khai báo `String result = ""` rồi gán nhiều lần. Với sealed hierarchy, compiler giúp kiểm tra nhánh không bị thiếu. Switch expression buộc các đường đi hợp lệ cung cấp kết quả hoặc ném ngoại lệ.

### 7.2. Dùng switch statement để điều phối handler

```java
// MẢNH MÃ: các phương thức xử lý được định nghĩa trong ứng dụng
switch (event) {
    case null -> rejectMissingEvent();
    case OrderCreated created -> processCreated(created);
    case PaymentCaptured payment -> processPayment(payment);
    case OrderCancelled cancelled -> processCancelled(cancelled);
}
```

Ưu điểm: nhìn một chỗ biết sự kiện nào được chuyển tới handler nào. Việc cập nhật database, gửi thông báo và kiểm tra policy nên ở các phương thức có tên rõ ràng thay vì dồn tất cả vào cùng một `case`.

Một switch statement dùng pattern cũng có quy tắc bao phủ dành cho enhanced switch; tuy vậy, khi xử lý một kết quả phân loại, switch expression thường có cấu trúc phù hợp hơn.

### 7.3. Arrow rules tránh fall-through ngoài ý muốn

Dạng switch cũ dùng `case ...:` có thể rơi tiếp xuống nhánh khác nếu quên `break`:

```java
switch (kind) {
    case 1:
        System.out.println("one");
        break;
    case 2:
        System.out.println("two");
        break;
    default:
        System.out.println("other");
}
```

Với `case 1 -> ...` và `case 2 -> ...`, từng rule không tự chạy sang rule kế tiếp. Khi mở rộng nhiều nhánh, arrow rules thường làm ý định phân nhánh rõ ràng hơn.

## 8. Nhánh nhiều dòng: dùng yield, không biến switch thành khối khổng lồ

Switch expression dùng `yield` để tạo giá trị khi một case cần block nhiều câu lệnh:

```java
static String formatted(OrderEvent event) {
    return switch (event) {
        case null -> "missing";
        case OrderCreated(var orderId, var customerId) -> {
            String prefix = "Order " + orderId;
            yield prefix + " belongs to " + customerId;
        }
        case PaymentCaptured(var orderId, var amountVnd) ->
            "Paid " + orderId + ": " + amountVnd + " VND";
        case OrderCancelled(var orderId, var reason) ->
            "Cancelled " + orderId + ": " + reason;
    };
}
```

Trong block của switch expression, `yield value;` mang giá trị ra switch. Không sử dụng `break value;` kiểu một số cú pháp thử nghiệm cũ. Còn bên ngoài, `return switch (...) { ... };` trả giá trị của switch expression từ phương thức.

**Về thiết kế:** một block lớn vài chục dòng với truy vấn DB, gửi email, thay đổi state và định dạng chuỗi sẽ rất khó mở rộng dù dùng `yield` đúng. Hãy tách logic:

```java
// MẢNH MÃ minh họa cấu trúc, các hàm mô tả phải được triển khai:
return switch (event) {
    case null -> "missing";
    case OrderCreated created -> formatCreated(created);
    case PaymentCaptured payment -> formatPayment(payment);
    case OrderCancelled cancelled -> formatCancelled(cancelled);
};
```

Mỗi handler có thể test độc lập; switch chỉ quyết định **đường đi**.

## 9. Chính sách null, fallback và kiểu selector

Không có một chính sách `null` đúng cho mọi hệ thống.

| Trường hợp | Cách biểu đạt nên cân nhắc |
| --- | --- |
| `null` đại diện việc thiếu sự kiện được dự kiến | `case null -> "missing"` |
| `null` là vi phạm hợp đồng của API | `Objects.requireNonNull(event)` trước switch |
| Nguồn là `Object` từ bên ngoài | `case null` và `default` có ý nghĩa rõ ràng |
| Nguồn là sealed domain đóng | Xử lý mọi subtype và cân nhắc không có `default` |

Ví dụ dữ liệu kiểu mở:

```java
static String accept(Object payload) {
    return switch (payload) {
        case null -> "MISSING";
        case String text -> "TEXT";
        case byte[] bytes -> "BINARY";
        default -> "UNSUPPORTED";
    };
}
```

Ở đây `Object` có thể chứa vô số kiểu, nên `default` có nghĩa **từ chối loại chưa hỗ trợ**. Nó không phải nhánh thay thế `case null`; một switch không có xử lý `null` thích hợp có thể ném `NullPointerException`.

Đừng luôn trả `"unknown"` cho `null` chỉ vì muốn chương trình “không lỗi”. Trong domain giao dịch quan trọng, thiếu sự kiện có thể cần một exception hoặc kết quả từ chối rõ ràng.

### 9.1. Sealed interface không nhất thiết luôn là tập lá đóng

Một permitted subtype có thể là `non-sealed`, cho phép xuất hiện các subclass khác. Nếu domain có phần mở, việc xử lý một vài subtype cụ thể có thể chưa bao phủ mọi đối tượng runtime. Có thể cần một type pattern tổng quát ở vị trí thích hợp hoặc thay đổi mô hình.

Với domain events thường gặp, sealed interface + các record subtype `final` giúp tập biến thể đóng và rõ ràng hơn.

## 10. Mở rộng bằng cách thay đổi domain một lần, rà soát các switch liên quan

Quy trình khi thêm `OrderReturned` vào một hệ thống có ba loại sự kiện:

1. **Định nghĩa subtype** và component phù hợp, chẳng hạn `record OrderReturned(String orderId, String returnReason)`.
2. **Cập nhật sealed hierarchy** để subtype mới được phép implements `OrderEvent`.
3. **Biên dịch lại toàn bộ code liên quan**, quan sát những switch exhaustive báo thiếu trường hợp.
4. **Định nghĩa chính sách riêng ở từng nơi dùng switch**: audit, hiển thị, gửi thông báo, định tuyến có thể không xử lý giống nhau.
5. **Thêm test** cho subtype mới, lỗi đầu vào và các tương tác với handler cũ.
6. **Kiểm tra default không mong muốn** đang che trường hợp mới.
7. **Đảm bảo triển khai cùng phiên bản phù hợp**, nhất là khi domain model và application nằm ở các module/thư viện khác nhau.

Một `default -> null` để lấp lỗi “non-exhaustive switch” có thể khiến mã biên dịch nhưng không làm hệ thống đúng hơn. Hãy coi cảnh báo thiếu nhánh là yêu cầu làm rõ nghiệp vụ.

### 10.1. Khi thêm guard mới

Nếu luật thay đổi từ một ngưỡng thành nhiều ngưỡng:

- Xác định đơn vị `amountVnd` và các mốc ranh giới.
- Đặt nhánh cụ thể hơn trước nhánh tổng quát.
- Test giá trị ngay dưới, đúng bằng và ngay trên từng mốc.
- Tránh guard có tác dụng phụ; không thực hiện thanh toán hay ghi state bên trong `when`.
- Đảm bảo fallback cho cùng subtype không bị loại bỏ ngoài ý muốn.

Đây là cách thay đổi tập trung, tránh viết lại toàn bộ switch.

## 11. Khi switch quá dài: chọn handler, policy hoặc polymorphism

Một switch pattern có ích khi nó là **bản đồ biến thể → hành vi**. Nhưng switch rất dài có thể cho thấy một lớp đang ôm quá nhiều trách nhiệm.

**Tín hiệu cần tách:**

- Mỗi `case` chứa các bước truy vấn, kiểm tra nghiệp vụ, lưu trữ và gửi thông báo.
- Cùng phép kiểm tra domain xuất hiện ở nhiều switch lớn nhưng không thống nhất.
- Guard phải gọi dịch vụ bên ngoài, có thể ném exception hoặc thay đổi state.
- Muốn test một nhánh phải mock hàng loạt dependency không liên quan.

Cách tổ chức thường hiệu quả:

```java
// MẢNH MÃ: service/handler được định nghĩa ở application layer
static void dispatch(OrderEvent event) {
    switch (event) {
        case null -> rejectMissing();
        case OrderCreated created -> onCreated(created);
        case PaymentCaptured paid -> onPaymentCaptured(paid);
        case OrderCancelled cancelled -> onCancelled(cancelled);
    }
}
```

Bản thân switch dễ quét mắt; business logic được tách sang handler.

Khi điều kiện guard có logic phức tạp hoặc dùng ở nhiều nơi, tách thành **policy method thuần** có tên rõ, chẳng hạn `classifyAmount(long amountVnd)`. Tách như vậy tạo một điểm kiểm thử ngưỡng và không lặp quy tắc trong nhiều nhánh.

**Có nên bỏ switch để dùng polymorphism?** Không bắt buộc. Khi mỗi subtype sở hữu hành vi riêng và ít operation bên ngoài, polymorphism có thể hợp lý. Nhưng nếu việc cần làm là render DTO, ghi audit hay thực hiện thao tác ở ranh giới ứng dụng, switch trên sealed domain rất rõ ràng và ít làm domain phụ thuộc hạ tầng.

Hãy xem thứ gì thường được mở rộng hơn:

- **Thêm subtype:** sealed + exhaustive switch giúp chỉ ra các chỗ cần sửa.
- **Thêm operation lên một tập subtype ổn định:** thêm một switch ở application boundary có thể tự nhiên hơn thay đổi mọi subtype.
- **Thêm luật phân loại phức tạp:** tách policy hoặc state model để khỏi chồng chất guard.

## 12. Chương trình Java 21 hoàn chỉnh: hai switch, một domain

Lưu vào tệp **`ExtensibleSwitchDemo.java`**. Các tính năng pattern sử dụng ở đây đã chính thức trong Java 21, không cần preview.

```java
public class ExtensibleSwitchDemo {
    sealed interface OrderEvent
            permits OrderCreated, PaymentCaptured, OrderCancelled {}

    record OrderCreated(String orderId, String customerId)
            implements OrderEvent {}

    record PaymentCaptured(String orderId, long amountVnd)
            implements OrderEvent {}

    record OrderCancelled(String orderId, String reason)
            implements OrderEvent {}

    static String describe(OrderEvent event) {
        return switch (event) {
            case null -> "missing event";
            case OrderCreated(var orderId, var customerId) ->
                "created " + orderId + " for " + customerId;
            case PaymentCaptured(var orderId, var amountVnd)
                    when amountVnd >= 1_000_000L ->
                "large payment " + orderId + ": "
                        + amountVnd + " VND";
            case PaymentCaptured(var orderId, var amountVnd) ->
                "payment " + orderId + ": "
                        + amountVnd + " VND";
            case OrderCancelled(var orderId, var reason) ->
                "cancelled " + orderId + ": " + reason;
        };
    }

    static String auditCode(OrderEvent event) {
        return switch (event) {
            case null -> "NO_EVENT";
            case OrderCreated created -> "CREATED";
            case PaymentCaptured paid -> "CAPTURED";
            case OrderCancelled cancelled -> "CANCELLED";
        };
    }

    static void verify(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected [" + expected + "], got [" + actual + "]");
        }
    }

    public static void main(String[] args) {
        OrderEvent[] events = {
            new OrderCreated("ORD-1", "CUS-7"),
            new PaymentCaptured("ORD-1", 1_500_000L),
            new PaymentCaptured("ORD-2", 300_000L),
            new OrderCancelled("ORD-3", "out of stock"),
            null
        };

        for (OrderEvent event : events) {
            System.out.println(
                    describe(event) + " | " + auditCode(event));
        }

        verify("created ORD-1 for CUS-7",
                describe(new OrderCreated("ORD-1", "CUS-7")));
        verify("large payment ORD-1: 1500000 VND",
                describe(new PaymentCaptured("ORD-1", 1_500_000L)));
        verify("payment ORD-2: 300000 VND",
                describe(new PaymentCaptured("ORD-2", 300_000L)));
        verify("large payment ORD-X: 1000000 VND",
                describe(new PaymentCaptured("ORD-X", 1_000_000L)));
        verify("missing event", describe(null));
        verify("CANCELLED",
                auditCode(new OrderCancelled("ORD-3", "out of stock")));

        System.out.println("checks passed");
    }
}
```

Biên dịch và chạy với **JDK 21**:

```bash
javac --release 21 ExtensibleSwitchDemo.java
java ExtensibleSwitchDemo
```

Kết quả stdout:

```text
created ORD-1 for CUS-7 | CREATED
large payment ORD-1: 1500000 VND | CAPTURED
payment ORD-2: 300000 VND | CAPTURED
cancelled ORD-3: out of stock | CANCELLED
missing event | NO_EVENT
checks passed
```

**Vì sao chương trình thể hiện cấu trúc mở rộng tốt:**

- `OrderEvent` mô tả rõ tập biến thể bằng `sealed`.
- `describe` dùng record pattern để lấy dữ liệu và chỉ đặt guard ở `PaymentCaptured`.
- Nhánh có guard đứng **trước** nhánh `PaymentCaptured` tổng quát.
- `auditCode` chỉ dùng type pattern, vì không cần giải cấu trúc record.
- Cả hai switch không dùng `default`, cho phép compiler hỗ trợ nhận diện subtype bị thiếu khi domain mở rộng.
- `case null` diễn đạt rõ chính sách; không bị nhầm với một subtype.
- `verify` cung cấp kiểm tra độc lập, không cần bật `-ea` hoặc thư viện test ngoài.

### 12.1. Kiểm tra ranh giới của guard

Với `amountVnd >= 1_000_000L`, các giá trị quan trọng là:

| Giá trị VND | Kết quả mong đợi |
| ---: | --- |
| 999.999 | `payment` thông thường |
| 1.000.000 | `large payment` |
| 1.000.001 | `large payment` |

Mã `verify` trong `main` đã kiểm tra trường hợp đúng ngưỡng. Trong ứng dụng thật, nên bổ sung các trường hợp còn lại vào unit test tự động để phát hiện lỗi `>` và `>=`.

## 13. Tổ chức file và test khi số lượng biến thể tăng

Một cấu trúc source code khả thi với domain lớn hơn:

```text
orders/
  domain/
    OrderEvent.java
    OrderCreated.java
    PaymentCaptured.java
    OrderCancelled.java
  application/
    OrderEventDispatcher.java
    OrderEventFormatter.java
  test/
    OrderEventFormatterTest.java
    OrderEventDispatcherTest.java
```

Đây là **sơ đồ tùy chọn**, không phải quy tắc bắt buộc. Java có quy định riêng về file chứa các top-level `public` types; khi thiết kế file thật, cần tổ chức theo các quy định này. Với ví dụ nhỏ, nested records trong một class vẫn hoàn toàn phù hợp.

Sự phân chia cần thể hiện:

- **Domain:** các biến thể và bất biến dữ liệu.
- **Application:** định tuyến và phối hợp nghiệp vụ.
- **Presentation:** kết quả hiển thị hoặc DTO.
- **Tests:** xác minh hành vi cho mỗi biến thể và policy.

Không nên để domain record phụ thuộc trực tiếp vào lớp gửi email hoặc giao diện chỉ vì một switch đang nằm sai tầng kiến trúc.

### 13.1. Những trường hợp cần test

| Nhóm test | Nội dung |
| --- | --- |
| Mỗi subtype | `OrderCreated`, `PaymentCaptured`, `OrderCancelled` |
| Guard boundaries | Ngay dưới, đúng bằng, ngay trên mỗi ngưỡng |
| Null policy | `null` có thông điệp hoặc exception đúng hợp đồng |
| Record components | Thứ tự ID, số tiền và reason không bị đảo |
| Sau khi thêm subtype | Compiler và test xác nhận các switch/handler đã được cập nhật |
| Integration | Kết quả từ handler thật, audit, lưu trữ, các tác động nghiệp vụ |

Compile check trong CI và test có vai trò khác nhau: **compiler** xác nhận cấu trúc kiểu/case phù hợp, còn **test** xác nhận kết quả đúng yêu cầu nghiệp vụ.

## 14. Những lỗi bảo trì thường gặp

### 14.1. Thêm default để che thiếu nhánh

```java
// Có thể biên dịch nhưng dễ nuốt subtype mới:
return switch (event) {
    case OrderCreated created -> "created";
    default -> "other";
};
```

Nếu domain đóng và mọi biến thể cần xử lý riêng, hãy liệt kê subtype cụ thể. `default` nên được giữ khi có chính sách fallback thật sự.

### 14.2. Đặt case rộng trước case chuyên biệt

```java
// CỐ Ý SAI: nhánh có guard bị dominated
case PaymentCaptured(var id, var amount) -> "payment";
case PaymentCaptured(var id, var amount)
        when amount > 1_000_000L -> "large";
```

Sửa bằng cách đưa guard lên trước. Kiểm tra cả giá trị ngưỡng theo nghiệp vụ.

### 14.3. Dùng selector quá rộng

Nếu có `OrderEvent` mà lại viết `switch ((Object) event)`, bạn đánh mất thông tin exhaustive về tập subtype được phép. Đừng làm yếu kiểu tĩnh chỉ để tiện viết `default`.

### 14.4. Lấy null làm một “unknown” vô hại

Một `null` có thể là lỗi lập trình hoặc dữ liệu ngoài thiếu. Đừng tự động trả chuỗi trống rồi cho luồng nghiệp vụ tiếp tục như thể đã xử lý một event hợp lệ.

### 14.5. Guard có side effect hoặc logic quá dài

```java
// Minh họa cấu trúc nên tránh khi hasPermission có side effect:
case OrderCreated created when hasPermission(created) -> ...
```

Nếu `hasPermission` truy vấn mạng, làm thay đổi state hoặc phụ thuộc nhiều dịch vụ, việc tăng guard làm luồng phân nhánh khó dự đoán. Thực hiện kiểm tra quyền bằng policy rõ ràng, kiểm soát lỗi và thứ tự thao tác.

### 14.6. Không cập nhật test khi thêm subtype

Compiler có thể bắt switch không exhaustive, nhưng không đảm bảo nội dung thông báo, chi phí, số tiền hoặc handler được xử lý đúng. Sau khi thêm một subtype, phải viết test nghiệp vụ tương ứng.

### 14.7. Tưởng phải chuyển mọi switch sang polymorphism

Chuyển từ một switch rõ ràng sang nhiều class handler trừu tượng không tự làm thiết kế tốt hơn. Nếu switch chủ yếu phân loại dữ liệu hoặc chuyển thành DTO, giữ switch ở application boundary thường dễ hiểu hơn. Chỉ tăng số lớp khi có nhu cầu thay đổi và tái sử dụng rõ ràng.

## 15. Bài tập và đáp án

**Bài 1 — Nên có default hay không?**

Cho domain:

```java
sealed interface Alert permits EmailAlert, SmsAlert {}
record EmailAlert(String email) implements Alert {}
record SmsAlert(String phone) implements Alert {}
```

Bạn cần biểu thức chuyển mỗi loại alert thành thông điệp riêng. Viết một `case EmailAlert` cộng `default` hay hai case cụ thể?

**Đáp án:** Với yêu cầu xử lý riêng tất cả subtype của domain đóng, nên dùng hai case cụ thể, không mặc định `default`. Khi thêm subtype mới, compiler có thể nhắc nơi cần xử lý. Đừng quên quy định riêng cho `null`.

**Bài 2 — Thứ tự guard:**

```java
case PaymentCaptured(var id, var amount) -> "payment";
case PaymentCaptured(var id, var amount) when amount >= 1_000_000L ->
    "large";
```

**Đáp án:** Sai do dominance. Nhánh tổng quát đứng trước che nhánh guard. Đảo thứ tự và test tại ngưỡng 1.000.000.

**Bài 3 — Switch expression trả về gì nếu case có block?**

```java
case OrderCreated(var id, var customerId) -> {
    String label = id + ":" + customerId;
    yield label;
}
```

**Đáp án:** `yield label;` cung cấp giá trị cho switch expression. `return switch (...) { ... };` ở bên ngoài biểu thức mới trả kết quả từ phương thức.

**Bài 4 — Khi nào dùng type pattern thay record pattern?**

**Đáp án:** Khi chỉ cần biết biến thể, dùng `case OrderCancelled cancelled ->`; khi cần trực tiếp `orderId` và `reason`, dùng `case OrderCancelled(var orderId, var reason) ->`. Cả hai hợp lệ; chọn cú pháp truyền đạt rõ mục đích.

**Bài 5 — Compile check có đủ chưa?**

**Đáp án:** Chưa. Exhaustiveness kiểm tra có nhánh cho các subtype hợp lệ, không xác nhận nhánh đó áp dụng đúng quy tắc nghiệp vụ. Cần test output, ngưỡng, `null` và handler.

**Bài 6 — Nếu dữ liệu đầu vào thật sự là Object từ ngoài?**

**Đáp án:** Có thể dùng switch có `case null`, các pattern được hỗ trợ và `default -> "UNSUPPORTED"`. Sau kiểm tra, nên chuyển sang type domain rõ ràng trước khi xử lý sâu để không mất khả năng kiểm tra kiểu.

## 16. Checklist code review

- [ ] Selector có kiểu tĩnh phù hợp domain, không bị làm rộng thành `Object` vô cớ.
- [ ] Tập subtype đóng được mô hình bằng `sealed` khi phù hợp.
- [ ] Switch expression xử lý đầy đủ biến thể; không có `default` che nhánh mới nếu cần exhaustive checking.
- [ ] Chính sách `null` được xác định rõ.
- [ ] Nhánh có guard hoặc pattern hẹp đứng trước nhánh tổng quát, không bị dominated.
- [ ] Các guard ngắn, không có side effect khó đoán, được test tại giá trị biên.
- [ ] Record patterns giữ đúng thứ tự component và tên biến phản ánh nghiệp vụ.
- [ ] Switch expression dùng `yield` đúng khi case cần block nhiều dòng.
- [ ] Nhánh không chứa quá nhiều trách nhiệm; handler/policy được tách khi cần.
- [ ] Khi thêm subtype, đã kiểm tra các switch, handler và test liên quan.
- [ ] Các module cùng dùng sealed hierarchy được biên dịch/triển khai tương thích.

## 17. Tài liệu tiêu chuẩn

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): switch pattern, guard, dominance, null và exhaustiveness trong Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record patterns chính thức ở Java 21.
- [Java Language Specification 21, §14.11 — switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): cú pháp nhãn, switch rules, kiểm tra bao phủ và hành vi switch statement.
- [Java Language Specification 21, §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): quy tắc switch expression và tính exhaustive.
- [Java Language Specification 21, §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type/record pattern và cách khớp.
- [Java Language Specification 21, §8.1.1.2 — sealed Classes](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2): giới hạn các subtype trong sealed hierarchy.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): ví dụ và quy tắc thực tế.
