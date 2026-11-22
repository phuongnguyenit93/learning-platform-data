# Pattern switch trên interface sealed trong Java 21

## 1. Vì sao kết hợp `sealed interface` với pattern `switch`?

Khi hệ thống có một nhóm biến thể nghiệp vụ xác định trước, `sealed interface` cho phép mô tả **những kiểu nào được phép triển khai interface**. Pattern matching for `switch` trong Java 21 cho phép phân nhánh trực tiếp theo các kiểu đó, liên kết biến ở từng nhánh và — khi các trường hợp được bao phủ — nhờ compiler kiểm tra tính **exhaustive**.

Ví dụ một quy trình thanh toán có ba kết quả:

```java
sealed interface PaymentState permits Pending, Captured, Rejected {}

record Pending(String paymentId) implements PaymentState {}
record Captured(String paymentId, long amountVnd) implements PaymentState {}
record Rejected(String paymentId, String reason) implements PaymentState {}
```

`PaymentState` là kiểu cha. `Pending`, `Captured` và `Rejected` là ba subtype trực tiếp được phép. Dùng `switch`:

```java
static String status(PaymentState state) {
    return switch (state) {
        case Pending pending -> "PENDING";
        case Captured captured -> "CAPTURED";
        case Rejected rejected -> "REJECTED";
    };
}
```

Đây là các **mảnh mã dùng chung**, có thể đưa vào một lớp hoặc tệp Java hợp lệ. Chương trình hoàn chỉnh ở mục 13 sẽ có đủ định nghĩa và cách chạy.

Lợi ích chính không chỉ là ít câu `if/else`:

- **Kiểu domain nói rõ tập biến thể**: những subtype nào là kết quả thanh toán hợp lệ.
- **Nhánh switch gần với ngôn ngữ nghiệp vụ**: mỗi `case` đại diện một trạng thái.
- **Compiler hỗ trợ phát hiện thiếu nhánh** khi thêm một subtype vào hierarchy đóng rồi biên dịch lại code phụ thuộc.
- **Không cần ép kiểu thủ công**: type/record pattern liên kết dữ liệu đúng kiểu trong thân nhánh.
- **Dễ bổ sung chính sách cho từng subtype** bằng guard, nhánh cơ sở và hàm xử lý riêng.

**Ranh giới quan trọng:** `sealed` kiểm soát quan hệ kế thừa trực tiếp, không tự kiểm tra dữ liệu component hay tất cả bất biến nghiệp vụ. Một `Captured` vẫn có thể có số tiền âm hoặc component `null` nếu constructor không kiểm tra.

## 2. Cú pháp và điều kiện tạo sealed hierarchy

Một `sealed interface` khai báo tập subtype trực tiếp bằng `permits`:

```java
sealed interface Message permits TextMessage, ImageMessage {}

record TextMessage(String text) implements Message {}
record ImageMessage(String imageUrl) implements Message {}
```

Phân biệt:

| Thành phần | Tác dụng |
| --- | --- |
| `sealed interface Message` | Interface giới hạn những lớp/interface được phép trực tiếp mở rộng |
| `permits TextMessage, ImageMessage` | Danh sách các direct permitted subtypes |
| `implements Message` | Bản thân subtype có tham gia hierarchy |
| `record TextMessage(...)` | Một implementation là record; record luôn `final` |
| `case TextMessage text ->` | Type pattern nhận dạng một biến thể |
| `case TextMessage(var content) ->` | Record pattern, vừa nhận dạng vừa lấy component |

Một direct subtype của sealed class/interface phải khai báo rõ một trong các trạng thái thích hợp: **`final`, `sealed` hoặc `non-sealed`**, ngoại trừ các trường hợp kiểu có đặc tính tương ứng theo ngôn ngữ như `record` (tự `final`).

Ví dụ dùng lớp thường:

```java
sealed interface Command permits CreateCommand, PluginCommand {}

final class CreateCommand implements Command {}

non-sealed class PluginCommand implements Command {}
```

`CreateCommand` đóng, không cho phép subclass. `PluginCommand` lại mở để có thể có subclass khác. Điều này ảnh hưởng cách nghĩ về số lượng biến thể runtime, nhưng một `case PluginCommand plugin ->` vẫn bao phủ **mọi đối tượng** thuộc `PluginCommand` hoặc subtype của nó.

### 2.1. Quy tắc module/package cần nhớ

Các subtype được phép của sealed type phải nằm trong **cùng module** nếu hierarchy thuộc named module; khi code thuộc unnamed module, chúng phải ở **cùng package**. `permits` không phải cơ chế cấp quyền cho một subtype tùy ý trong mọi module khác.

Trong bài tập nhỏ, đặt interface và các record như nested types trong cùng một `public class` là một cách đơn giản để có chương trình độc lập, biên dịch trực tiếp bằng `javac`.

### 2.2. `permits` chỉ liệt kê subtype trực tiếp

Giả sử:

```java
sealed interface Event permits OrderEvent, AuditEvent {}
sealed interface OrderEvent extends Event permits OrderPlaced {}
record OrderPlaced(String id) implements OrderEvent {}
final class AuditEvent implements Event {}
```

`OrderPlaced` là subtype trực tiếp được phép của **`OrderEvent`**, không nhất thiết là phần tử trực tiếp trong danh sách `permits` của **`Event`**. Khi đọc switch trên `Event`, phải nhìn đúng cây kiểu, không chỉ một danh sách tên.

## 3. Type pattern: phân nhánh theo subtype của interface

Khi selector có kiểu tĩnh là sealed interface, Java 21 hỗ trợ **type patterns** trực tiếp trong case:

```java
static String shortLabel(PaymentState state) {
    return switch (state) {
        case Pending pending -> "waiting";
        case Captured captured -> "paid";
        case Rejected rejected -> "failed";
    };
}
```

Đọc `case Captured captured` như sau:

1. Kiểm tra giá trị runtime có thuộc kiểu `Captured` không.
2. Nếu đúng, liên kết pattern variable `captured` kiểu `Captured`.
3. Chỉ trong phần nhánh phù hợp mới được dùng `captured.paymentId()`, `captured.amountVnd()`, v.v.

Đoạn mã không cần:

```java
if (state instanceof Captured) {
    Captured captured = (Captured) state;
}
```

vì pattern đã gộp phần kiểm tra và liên kết biến có kiểu.

**Đặt tên pattern variable rõ nghĩa:** `captured`, `pending`, `rejected` có ích hơn `x`, `obj` khi nội dung nhánh dài. Tên `captured` là biến, không phải một pattern khác hay cách sửa quy tắc bao phủ.

## 4. Exhaustiveness: compiler biết đủ các biến thể khi nào?

Một **switch expression** phải bao phủ đầy đủ các giá trị phù hợp. Với selector kiểu sealed `PaymentState` ở trên, ba record subtype `Pending`, `Captured`, `Rejected` tạo thành tập đóng; một case không guard cho **mỗi** subtype đủ để switch được kiểm tra exhaustive:

```java
static int categoryCode(PaymentState state) {
    return switch (state) {
        case Pending pending -> 1;
        case Captured captured -> 2;
        case Rejected rejected -> 3;
    };
}
```

Không cần `default`. Đây là điểm mạnh của thiết kế sealed + switch: nếu sau này thêm `Refunded` vào `permits` và biên dịch lại các nơi dùng `PaymentState`, compiler có thể báo switch không còn exhaustive, buộc người sửa xem xét quy tắc xử lý `Refunded`.

### 4.1. Vì sao không nên thêm `default` một cách máy móc?

```java
static String category(PaymentState state) {
    return switch (state) {
        case Pending pending -> "PENDING";
        default -> "OTHER";
    };
}
```

Đoạn này có thể biên dịch nhưng `Captured` và `Rejected` bị gom chung vào `OTHER`. Sau khi thêm subtype mới, code tiếp tục trả `OTHER` mà không bắt người bảo trì cập nhật. Nếu mọi biến thể thanh toán cần đối xử khác nhau, `default` đang **che thiếu sót nghiệp vụ**.

**Lựa chọn thiết kế:**

- Một tập variant **đóng**, mỗi loại có semantics riêng: ưu tiên **không có `default`**, liệt kê các pattern cần thiết.
- Một nguồn **mở** như `Object`, dữ liệu bên ngoài hoặc protocol có loại chưa hỗ trợ: `default -> "UNSUPPORTED"` là chính sách fallback hữu ích.
- Một subtype `non-sealed` mở rộng vô hạn: có thể dùng type pattern bao phủ chính subtype đó và mọi lớp con, chứ không thể chỉ liệt kê vài lớp con mà hy vọng đã exhaustive.

### 4.2. Không phải mọi `switch` đều có cùng yêu cầu

`switch` **expression** luôn cần exhaustive. Trong Java 21, `switch` **statement có pattern labels** thuộc nhóm *enhanced switch statement* và cũng chịu quy tắc exhaustiveness. Với switch statement cổ điển chỉ dùng hằng số, quy tắc có thể khác. Đừng lấy kinh nghiệm từ `switch(int)` cũ để suy ra một pattern switch được phép bỏ qua mọi subtype tùy ý.

Ví dụ hai cách sử dụng:

```java
// Trả về giá trị (switch expression):
String result = switch (state) {
    case Pending p -> "P";
    case Captured c -> "C";
    case Rejected r -> "R";
};

// Điều phối side effect (switch statement; handler giả định):
switch (state) {
    case Pending p -> onPending(p);
    case Captured c -> onCaptured(c);
    case Rejected r -> onRejected(r);
}
```

Đoạn thứ hai chỉ là **mảnh mã minh họa**, các handler `onPending`, `onCaptured`, `onRejected` phải được định nghĩa trong ứng dụng.

## 5. `null` vẫn phải có chính sách riêng

Một type pattern thông thường như `case Captured captured` **không match selector `null`**. Java 21 cho phép thêm `case null`:

```java
static String statusOrMissing(PaymentState state) {
    return switch (state) {
        case null -> "MISSING";
        case Pending pending -> "PENDING";
        case Captured captured -> "CAPTURED";
        case Rejected rejected -> "REJECTED";
    };
}
```

`sealed` giúp biết toàn bộ subtype hợp lệ, nhưng nó không tự quy định `null` là một trạng thái nghiệp vụ.

Nếu `null` là lỗi của caller, cũng có thể từ chối sớm:

```java
java.util.Objects.requireNonNull(state, "state");

String label = switch (state) {
    case Pending p -> "PENDING";
    case Captured c -> "CAPTURED";
    case Rejected r -> "REJECTED";
};
```

Trong pattern switch Java 21, nếu selector `null` mà không có nhãn phù hợp, có thể xảy ra `NullPointerException`; `default` không nên được coi là cơ chế tự động bắt `null`.

**Phân biệt rõ:** “đã bao phủ mọi subtype” (exhaustiveness) và “đã có chính sách cho null” là hai vấn đề khác nhau. Một phương thức có thể exhaustive nhưng vẫn cố ý ném lỗi khi nhận `null`.

## 6. Record pattern: vừa chọn subtype vừa giải cấu trúc dữ liệu

Với các subtype được khai báo bằng record, Java 21 có thể lấy component ngay ở case:

```java
static String detail(PaymentState state) {
    return switch (state) {
        case null -> "missing";
        case Pending(var paymentId) ->
            "pending " + paymentId;
        case Captured(var paymentId, var amountVnd) ->
            "captured " + paymentId + ": " + amountVnd + " VND";
        case Rejected(var paymentId, var reason) ->
            "rejected " + paymentId + ": " + reason;
    };
}
```

`Captured(var paymentId, var amountVnd)` là một **record pattern**. Java nhận kiểu `Captured`, rồi liên kết hai component **theo thứ tự record declaration**.

Nếu record khai báo `Captured(String paymentId, long amountVnd)`, biến đầu có kiểu suy luận `String`, biến thứ hai có kiểu suy luận `long`. Không cần cast. Nếu đổi nhầm tên hay thứ tự, có thể xảy ra lỗi ngữ nghĩa khi nhiều component cùng kiểu: compiler kiểm tra kiểu, nhưng không biết `senderId` bị đặt vào vị trí của `receiverId` là sai nghiệp vụ.

### 6.1. Khi nào dùng type pattern thay vì record pattern?

Chọn theo nhu cầu của nhánh:

| Mục tiêu | Cú pháp nên cân nhắc |
| --- | --- |
| Chỉ cần phân loại biến thể | `case Captured captured ->` |
| Cần truy cập vài thuộc tính có accessor, không muốn deconstruct tất cả | `case Captured captured -> captured.amountVnd()` |
| Cần trực tiếp mọi component | `case Captured(var paymentId, var amountVnd) ->` |
| Cần match cấu trúc lồng nhau | `case Captured(var id, Money(var amount)) ->` |

Một record pattern giải cấu trúc **toàn bộ danh sách component** của record theo vị trí. Nếu chỉ cần một field trong record nhiều component, dùng type pattern và accessor có thể gọn, ít phụ thuộc thứ tự record declaration hơn.

## 7. Nested record pattern: lưu ý khi component là null

Giả sử một trạng thái thanh toán chứa record tiền:

```java
record Money(long amountVnd) {}
record Captured(String paymentId, Money money) implements PaymentState {}
```

Đoạn này là **mô hình thay thế** cho record `Captured` hai component ở các ví dụ trước; không ghép hai khai báo `Captured` khác nhau vào cùng một tệp. Mục 13 sử dụng mô hình `Captured(String paymentId, Money money)`.

Một nested record pattern:

```java
case Captured(String paymentId, Money(long amountVnd)) ->
    "captured " + paymentId + " for " + amountVnd + " VND";
```

phải match cả `Captured` và component `Money`. Nếu `money` là `null`, nested `Money(...)` **không match**. Vì thế, khi muốn xử lý mọi `Captured`, nên có nhánh type pattern cơ sở:

```java
case Captured(String id, Money(long amount))
        when amount > 0 -> "valid captured payment";
case Captured captured -> "captured with missing or invalid money";
```

Nhánh `Captured captured` đứng cuối bao phủ các `Captured` còn lại, gồm trường hợp `money = null`. Mẫu này minh họa một ý tưởng quan trọng: **sealed hierarchy không bảo đảm một nested record pattern sẽ match mọi giá trị thuộc subtype**, vì component và guard có thể thất bại.

Đừng đặt `case Captured captured` trước nested record pattern; nhánh chung sẽ che nhánh cụ thể (dominance).

## 8. Guard `when` trên sealed subtype

Trong Java 21, guard cho phép chia một subtype thành các trường hợp nghiệp vụ:

```java
case Captured(var paymentId, var amountVnd)
        when amountVnd >= 1_000_000L ->
    "large captured payment";
case Captured(var paymentId, var amountVnd) ->
    "normal captured payment";
```

Đây là **mảnh code** dùng kiểu `Captured(String paymentId, long amountVnd)` ở mục 1, không dùng phiên bản `Captured(..., Money)` của mục 7. Guard chỉ chạy sau khi record pattern đã khớp, nên `amountVnd` có giá trị hợp lệ trong điều kiện `when`.

Đặc điểm cần nhớ:

- `when` là guard, không phải một subtype mới.
- Pattern variables được đưa vào scope của guard và thân case tương ứng.
- Case có guard **đứng trước** case tổng quát không guard.
- Khi guard sai, Java tiếp tục tìm nhãn phù hợp; case tổng quát sẽ xử lý subtype còn lại.
- Guard dùng điều kiện số học tùy ý không được compiler phân tích toàn bộ về bao phủ; test logic và thứ tự ưu tiên riêng.

### 8.1. Guard không thay thế coverage của subtype

Đoạn sau **không exhaustive** cho `Captured` nếu chỉ có guarded case:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH: thiếu Captured khi guard false
return switch (state) {
    case Pending pending -> "pending";
    case Captured captured when captured.amountVnd() > 0 -> "captured";
    case Rejected rejected -> "rejected";
};
```

Nếu `Captured.amountVnd() <= 0`, nhánh guarded không chọn. Sửa bằng một case `Captured` không guard ở phía sau hoặc một chính sách bổ sung được thiết kế rõ ràng.

### 8.2. Dominance: thứ tự case rất quan trọng

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH: bị dominated
return switch (state) {
    case Captured captured -> "any captured";
    case Captured captured when captured.amountVnd() > 0 ->
        "positive captured";
    default -> "other";
};
```

Nhánh `Captured` đầu tiên đã bao phủ mọi giá trị thuộc subtype đó. Đảo thứ tự hai nhánh để nhánh có guard được xét trước.

Nếu có nhiều guard (ví dụ ưu tiên `>= 5_000_000` rồi `>= 1_000_000`), cần sắp từ nhánh chuyên biệt đến tổng quát và test ở các ngưỡng. Không nên coi “compiler không báo dominance” là bằng chứng mọi thứ tự `when` đều đúng.

## 9. Không dùng default để che lỗi khi thêm subtype mới

Một thay đổi nghiệp vụ phổ biến là thêm trạng thái **`Refunded`**:

```java
// MẢNH MÃ cho thay đổi domain; cần cập nhật permits tương ứng:
record Refunded(String paymentId, long refundedAmountVnd)
        implements PaymentState {}
```

Bạn phải cập nhật:

```java
sealed interface PaymentState
        permits Pending, Captured, Rejected, Refunded {}
```

Khi biên dịch lại, các switch expression không có `default` vốn chỉ xử lý ba subtype sẽ cần xem xét `Refunded`.

Nếu chỉ sửa lỗi compiler bằng:

```java
default -> "unknown";
```

thì hệ thống có thể trả `unknown` cho hoàn tiền mà không ghi audit hoặc thông báo như yêu cầu. Hãy bổ sung trường hợp riêng:

```java
case Refunded refund -> "REFUNDED";
```

**Lưu ý khi chỉnh sửa:** mảnh `Refunded` và danh sách `permits` này là ví dụ hướng dẫn mở rộng. Chúng không nằm trong chương trình `SealedPatternSwitchDemo.java` ở mục 13, vì chương trình đó cố ý chỉ dùng ba subtype để minh họa trạng thái hiện tại.

## 10. Trường hợp `non-sealed`: tập lớp con có thể mở nhưng switch vẫn rõ

Một permitted subtype có thể là `non-sealed`:

```java
sealed interface Job permits InternalJob, ExternalJob {}
record InternalJob(String id) implements Job {}
non-sealed interface ExternalJob extends Job {}

final class PartnerJob implements ExternalJob {}
final class VendorJob implements ExternalJob {}
```

Đây là **mảnh các khai báo Java**. `PartnerJob`, `VendorJob` chỉ là hai trong các implementation có thể có của `ExternalJob`; ứng dụng có thể thêm các implementation khác.

Một switch trên `Job` vẫn có thể exhaustive nhờ type pattern dành cho **toàn bộ nhánh mở**:

```java
static String route(Job job) {
    return switch (job) {
        case InternalJob internal -> "internal";
        case ExternalJob external -> "external";
    };
}
```

`case ExternalJob external` không chỉ match `PartnerJob` và `VendorJob`, mà match cả những subtype tương lai của `ExternalJob`.

**Không nên** liệt kê `PartnerJob` và `VendorJob` rồi kết luận đã xử lý hết nhánh `ExternalJob`; bởi `ExternalJob` là `non-sealed`, có thể có những implementation khác.

Khi muốn xử lý Partner/Vendor riêng:

```java
return switch (job) {
    case InternalJob internal -> "internal";
    case PartnerJob partner -> "partner";
    case VendorJob vendor -> "vendor";
    case ExternalJob external -> "other external";
};
```

Thứ tự này đặt các lớp con cụ thể trước pattern cha `ExternalJob`. Nếu đặt `ExternalJob external` trước, các case `PartnerJob`, `VendorJob` phía sau có thể bị dominated.

## 11. Generic sealed interface: giữ đúng kiểu tĩnh của selector

Sealed hierarchies cũng có thể có type parameter:

```java
sealed interface ApiResult<T> permits Ok, ErrorResult {}

record Ok<T>(T value) implements ApiResult<T> {}
record ErrorResult<T>(String reason) implements ApiResult<T> {}
```

Khi xử lý `ApiResult<String>`, kiểu tĩnh của selector vẫn quan trọng. Java dùng thông tin generic sẵn có tại compile time và quy tắc pattern applicability để xác định pattern nào hợp lệ; type erasure **không biến tất cả `ApiResult<T>` thành kiểu có thể kiểm tra tùy ý theo `T` ở runtime**.

Ví dụ hướng thiết kế an toàn:

```java
// MẢNH MÃ: r là ApiResult<String>
return switch (r) {
    case Ok<?> ok -> "ok: " + ok.value();
    case ErrorResult<?> error -> "error: " + error.reason();
};
```

Dùng `<?> ` để nhận một biến thể generic mà không khẳng định JVM đã kiểm tra type argument cụ thể. Nếu cần áp dụng hành vi đặc thù của `String`, hãy dựa vào kiểu tĩnh ở biên API hoặc kiểm tra riêng giá trị đã lấy ra khi dữ liệu đến từ nguồn tổng quát.

Ở generic sealed hierarchy có thể có trường hợp thông số kiểu khiến một subtype không thể xuất hiện ở selector cụ thể, nên exhaustiveness có thể tinh vi hơn “cứ thấy tên trong `permits` là phải có một case”. Hãy để compiler kiểm tra theo **kiểu selector thực tế** và tránh unchecked casts.

## 12. Kiến trúc: switch ngắn ở lớp điều phối, logic dài ở handler

Pattern switch trên sealed interface đặc biệt hữu ích ở **application boundary**, nơi cần chuyển một event/result thành response, nhãn audit hoặc handler:

```java
// MẢNH MÃ: các handler cần được định nghĩa trong ứng dụng
switch (paymentState) {
    case Pending pending -> onPending(pending);
    case Captured captured -> onCaptured(captured);
    case Rejected rejected -> onRejected(rejected);
}
```

Nhìn vào switch là thấy mọi loại kết quả. Nhưng nhánh `onCaptured` có thể cần truy vấn transaction, gửi biên lai, cập nhật ledger và xử lý lỗi. Những bước này không nên dồn vào một block `case` dài.

### 12.1. Ba trách nhiệm nên tách

| Trách nhiệm | Vị trí gợi ý |
| --- | --- |
| Khai báo biến thể, dữ liệu, bất biến | `sealed interface` và record/class domain |
| Chọn hành vi theo subtype | `switch` pattern, giữ các nhánh ngắn |
| Thực thi tác động / quy tắc phức tạp | Handler, policy hoặc service độc lập |

Không phải mọi switch đều phải được thay bằng visitor hoặc polymorphism. Nếu việc thường xuyên thay đổi là **thêm một phép biến đổi** trên tập subtype ổn định, một switch expression mới thường đơn giản và có thể được compiler kiểm tra. Nếu mọi hành vi gắn chặt vào subtype và thay đổi cùng subtype, polymorphism có thể thích hợp hơn. Chọn dựa trên **trách nhiệm và hướng thay đổi**, không dựa vào quy tắc “switch là code smell”.

### 12.2. Tránh biến `sealed` thành “đóng băng domain” sai nghĩa

`sealed` giới hạn inheritance, nhưng không có nghĩa dữ liệu component không đổi, business state luôn hợp lệ hay hệ thống không còn phát triển. Khi thêm subtype hợp lệ, phải cập nhật mô hình và phân tích lại các switch phụ thuộc — đó là **mục tiêu có chủ đích** của cơ chế này.

Nếu một hệ plugin phải cho bên thứ ba tự mở rộng nhiều implementation mà bạn không kiểm soát, sealed top-level bao phủ toàn bộ plugin có thể không phù hợp. Có thể dùng nhánh `non-sealed` hoặc một thiết kế registration/interface mở ở ranh giới riêng.

## 13. Chương trình Java 21 hoàn chỉnh

Tệp **`SealedPatternSwitchDemo.java`** sau đây cho thấy cả **type pattern**, **record pattern lồng nhau**, **guard `when`**, **case cơ sở**, **null policy** và **exhaustiveness không cần `default`**. Mọi cú pháp được dùng đều chính thức trên Java 21.

```java
public class SealedPatternSwitchDemo {
    private static final long LARGE_PAYMENT_VND = 1_000_000L;

    sealed interface PaymentState
            permits Pending, Captured, Rejected {}

    record Money(long amountVnd) {}

    record Pending(String paymentId) implements PaymentState {}

    record Captured(String paymentId, Money money)
            implements PaymentState {}

    record Rejected(String paymentId, String reason)
            implements PaymentState {}

    static String describe(PaymentState state) {
        return switch (state) {
            case null -> "missing";

            case Captured(String paymentId, Money(long amountVnd))
                    when amountVnd >= LARGE_PAYMENT_VND ->
                "large captured " + paymentId
                    + ": " + amountVnd + " VND";

            case Captured(String paymentId, Money(long amountVnd)) ->
                "captured " + paymentId
                    + ": " + amountVnd + " VND";

            case Captured captured ->
                "captured " + captured.paymentId() + ": missing money";

            case Pending(String paymentId) ->
                "pending " + paymentId;

            case Rejected(String paymentId, String reason) ->
                "rejected " + paymentId + ": " + reason;
        };
    }

    static String status(PaymentState state) {
        return switch (state) {
            case null -> "NULL";
            case Pending pending -> "PENDING";
            case Captured captured -> "CAPTURED";
            case Rejected rejected -> "REJECTED";
        };
    }

    static long settledAmountVnd(PaymentState state) {
        return switch (state) {
            case null -> 0L;

            case Captured captured when captured.money() != null ->
                captured.money().amountVnd();

            case Captured captured -> 0L;
            case Pending pending -> 0L;
            case Rejected rejected -> 0L;
        };
    }

    static void check(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                "Expected [" + expected + "] but got [" + actual + "]");
        }
    }

    public static void main(String[] args) {
        PaymentState[] states = {
            new Pending("PAY-1"),
            new Captured("PAY-2", new Money(750_000L)),
            new Captured("PAY-3", new Money(1_500_000L)),
            new Captured("PAY-4", null),
            new Rejected("PAY-5", "insufficient funds"),
            null
        };

        for (PaymentState state : states) {
            System.out.println(describe(state)
                + " | " + status(state)
                + " | settled=" + settledAmountVnd(state));
        }

        check("large captured PAY-X: 1000000 VND",
            describe(new Captured("PAY-X", new Money(1_000_000L))));

        check("captured PAY-Y: 999999 VND",
            describe(new Captured("PAY-Y", new Money(999_999L))));

        check("captured PAY-4: missing money",
            describe(new Captured("PAY-4", null)));

        check("REJECTED",
            status(new Rejected("PAY-5", "insufficient funds")));

        if (settledAmountVnd(
                new Captured("PAY-6", new Money(42L))) != 42L) {
            throw new AssertionError("Incorrect settled amount");
        }

        System.out.println("checks passed");
    }
}
```

Biên dịch và chạy bằng **JDK 21**:

```bash
javac --release 21 SealedPatternSwitchDemo.java
java SealedPatternSwitchDemo
```

Kết quả stdout:

```text
pending PAY-1 | PENDING | settled=0
captured PAY-2: 750000 VND | CAPTURED | settled=750000
large captured PAY-3: 1500000 VND | CAPTURED | settled=1500000
captured PAY-4: missing money | CAPTURED | settled=0
rejected PAY-5: insufficient funds | REJECTED | settled=0
missing | NULL | settled=0
checks passed
```

**Vì sao chương trình được tổ chức như vậy?**

1. `PaymentState` là sealed interface, ba permitted subtypes đều là record, nên tập biến thể trực tiếp đã đóng.
2. `describe` ưu tiên nested record pattern có guard cho số tiền lớn, sau đó nested record pattern chung, rồi type pattern `Captured captured` để nhận trường hợp `money == null`.
3. `status` chỉ cần phân loại subtype, nên type patterns ngắn hơn record patterns.
4. `settledAmountVnd` biểu thị quy tắc riêng cho số tiền đã thu, kiểm tra `money != null` trước khi đọc `amountVnd`.
5. Ba switch expressions đều exhaustive mà không cần `default`. `case null` thể hiện chính sách “đầu vào thiếu” thay vì để NPE.
6. `check` là hàm kiểm tra có thể chạy trực tiếp, không cần bật `-ea` hay thư viện test.
7. Chương trình cố tình cho phép `Captured(..., null)` để minh họa việc sealed subtype **không tự bảo đảm component hợp lệ**. Ứng dụng thanh toán thật nên cân nhắc kiểm tra bất biến này ngay ở constructor và có cơ chế biểu diễn lỗi dữ liệu rõ ràng.

## 14. Những lỗi biên dịch và logic thường gặp

### Lỗi 1 — Quên một subtype của sealed hierarchy

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH: thiếu Rejected
return switch (state) {
    case Pending p -> "pending";
    case Captured c -> "captured";
};
```

Nếu `state` có kiểu `PaymentState` với ba permitted record, switch expression này không exhaustive. **Sửa:** thêm `case Rejected rejected -> ...` theo yêu cầu nghiệp vụ.

### Lỗi 2 — Chỉ có guarded case cho một subtype

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH: thiếu Captured khi guard false
return switch (state) {
    case Pending p -> "pending";
    case Captured c when c.money() != null -> "captured";
    case Rejected r -> "rejected";
};
```

**Sửa:** thêm `case Captured c -> "captured without money";` phía sau guarded case.

### Lỗi 3 — Nhánh tổng quát làm nhánh cụ thể bị dominated

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
return switch (state) {
    case Captured c -> "captured";
    case Captured(String id, Money(long amount)) ->
        "captured with amount"; // Dominated!
    default -> "other";
};
```

**Sửa:** đưa nested record pattern lên trước, đặt `case Captured c` phía sau để nhận phần còn lại.

### Lỗi 4 — Đặt default khiến subtype mới bị nuốt

```java
return switch (state) {
    case Pending p -> "pending";
    default -> "other";
};
```

Đây có thể không phải lỗi cú pháp, nhưng rất nguy hiểm với sealed domain mà mỗi subtype cần xử lý riêng. **Sửa:** liệt kê hết subtype thay vì dùng default vô điều kiện.

### Lỗi 5 — Tưởng `sealed` đồng nghĩa mọi component khác null

```java
// MẢNH MÃ: chỉ an toàn khi có bất biến money != null
case Captured captured ->
    captured.money().amountVnd();
```

Nếu component `money` là `null`, gọi `amountVnd()` sẽ ném `NullPointerException`. **Sửa:** kiểm tra/validate dữ liệu, hoặc có nhánh riêng khi thiếu tiền như chương trình hoàn chỉnh.

### Lỗi 6 — Dùng type pattern quá rộng trước subtype

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH
return switch (state) {
    case PaymentState any -> "any";
    case Captured captured -> "captured"; // Dominated
};
```

`PaymentState any` khớp mọi subtype của selector có kiểu `PaymentState`. Đây không còn là thiết kế phân nhánh theo subtype. Chỉ dùng pattern tổng quát khi thật sự muốn gom mọi biến thể còn lại và không tạo nhánh hẹp đứng sau.

### Lỗi 7 — Coi subtype `non-sealed` là tập con cố định

Nếu `ExternalJob` là `non-sealed`, đừng giả định `PartnerJob` và `VendorJob` là hai implementation duy nhất. **Sửa:** có type pattern `ExternalJob external` bao phủ các implementation khác nếu chính sách cần exhaustive.

### Lỗi 8 — Lạm dụng cast và instanceof thay cho pattern switch

```java
if (state instanceof Pending) {
    Pending p = (Pending) state;
    // ...
} else if (state instanceof Captured) {
    Captured c = (Captured) state;
    // ...
}
```

Cách viết này có thể dùng được, nhưng khi thêm subtype mới nó không cho cùng khả năng kiểm tra exhaustiveness của một switch expression trên sealed hierarchy. **Sửa:** khi mục đích là ánh xạ mọi variant thành một kết quả, ưu tiên pattern switch.

### Lỗi 9 — Cho rằng null là một subtype đã được permits

Không có `NullPayment` trừ khi chính bạn tạo một kiểu domain như vậy. Giá trị `null` không tự trở thành một subtype trong `permits`. **Sửa:** quyết định dùng `case null`, kiểm tra trước hay từ chối bằng exception.

## 15. Cách kiểm thử và bảo trì khi thêm subtype

Compiler giúp kiểm tra hình dạng type hierarchy, nhưng **không kiểm tra tính đúng đắn nghiệp vụ** của mỗi nhánh.

Một kế hoạch test phù hợp:

| Tình huống | Điều cần kiểm tra |
| --- | --- |
| Từng subtype | `Pending`, `Captured`, `Rejected` nhận kết quả riêng đúng |
| Các ngưỡng guard | 999.999; 1.000.000; 1.000.001 VND |
| Nested component `null` | `Captured(..., null)` được xử lý có chủ đích |
| Selector `null` | Chính sách “missing” hoặc lỗi theo hợp đồng |
| Thêm `Refunded` | Những switch exhaustive cần cập nhật đều được rà soát |
| Trường hợp `non-sealed` | Các implementation tương lai vẫn đi đúng nhánh chung |
| Tích hợp nhiều module | Các binary được biên dịch/triển khai tương thích |

Đặc biệt, **đừng đặt `default` chỉ để qua compile test** khi compiler báo thiếu subtype mới. Trong môi trường quản lý phiên bản, thay đổi các permitted subtypes và biên dịch riêng các module có thể khiến mã đã biên dịch chạy trên hierarchy mới; nếu switch exhaustive cũ không tìm được nhánh phù hợp, Java 21 có thể phát sinh `MatchException`. Cần biên dịch lại và test compatibility thay vì chỉ tin vào một bản build cũ.

### 15.1. Các bước khi bổ sung một trạng thái

1. Định nghĩa subtype mới bằng record hoặc class có bất biến dữ liệu rõ ràng.
2. Cập nhật `permits` của sealed interface, hoặc nhánh sealed con tương ứng.
3. Biên dịch lại các module phụ thuộc hierarchy.
4. Xem mọi switch expression/statement trên type đó có cần case mới không.
5. Xác định trạng thái mới ảnh hưởng tới format, audit, xử lý giao dịch và error policy ra sao.
6. Viết test độc lập cho case mới và test integration.
7. Kiểm tra `default` vô tình che thiếu xử lý; xem xét chiến lược versioning khi triển khai.

**Không tự hiểu** “thêm subtype” chỉ là thêm một case vào mỗi switch giống nhau. Các switch ở presentation, audit và business workflow có thể cần những hành vi khác nhau.

## 16. Bài tập kèm đáp án

### Bài 1. Tại sao không cần default?

```java
sealed interface Document permits PdfDocument, TextDocument {}
record PdfDocument(byte[] bytes) implements Document {}
record TextDocument(String text) implements Document {}
```

**Hỏi:** Một switch expression trên `Document` có hai case `PdfDocument` và `TextDocument` có thể exhaustive không?

**Đáp án:** Có. Hai subtype trực tiếp đều là record `final`; nếu mỗi case không guard và bao phủ subtype tương ứng, switch expression exhaustive, không cần `default`. Xử lý selector `null` là quyết định riêng.

### Bài 2. Guard có làm biến thể được bao phủ hết không?

```java
case PdfDocument pdf when pdf.bytes().length > 0 -> "nonempty";
```

**Hỏi:** Case trên có bao phủ mọi `PdfDocument` không?

**Đáp án:** Không. Nếu `bytes()` có độ dài 0, guard false; nếu `bytes()` là `null`, guard còn có thể ném exception. Hãy thêm case `PdfDocument pdf -> ...` phía sau hoặc xác định bất biến dữ liệu và policy rõ ràng.

### Bài 3. Khi thêm subtype `HtmlDocument`?

**Đáp án:** Cập nhật permitted subtype của sealed interface, sau đó biên dịch lại mọi switch exhaustive phụ thuộc. Những switch thiếu case mới sẽ cần sửa. Không nên thêm `default -> ""` để che thiếu yêu cầu nghiệp vụ.

### Bài 4. `non-sealed` có nghĩa gì với switch?

```java
sealed interface Job permits ExternalJob {}
non-sealed interface ExternalJob extends Job {}
```

**Đáp án:** `ExternalJob` có thể có nhiều implementation tương lai; một `case ExternalJob external -> ...` bao phủ toàn bộ nhánh đó. Chỉ liệt kê hai implementation hiện có không bảo đảm exhaustive.

### Bài 5. Type pattern và record pattern dùng lúc nào?

**Đáp án:** Dùng `case Captured captured` khi cần subtype hoặc accessor một vài thành phần. Dùng `case Captured(var id, Money(var amount))` khi cần match cấu trúc và lấy các component trực tiếp. Với nested pattern, phải có phương án khi component `null` hoặc không khớp.

### Bài 6. `null` có bị `default` nhận tự động không?

**Đáp án:** Không được giả định như vậy. Pattern switch Java 21 có quy tắc null riêng; thêm `case null` nếu muốn ánh xạ null thành trạng thái bình thường, hoặc từ chối bằng `Objects.requireNonNull`.

### Bài 7. Có nên đặt `case PaymentState state` đầu tiên để “bắt tất cả” không?

**Đáp án:** Không nếu cần phân biệt subtype. Pattern tổng quát này bao phủ các subtype và làm các nhánh hẹp phía sau bị dominated. Nếu cần một fallback chung, đặt nó cuối và cân nhắc tác động của việc mất exhaustive checking chi tiết.

## 17. Checklist khi code review

- [ ] `sealed interface` phản ánh một **tập biến thể domain** thực sự cần đóng?
- [ ] Các direct permitted subtypes hợp lệ và có `final`/`sealed`/`non-sealed` phù hợp?
- [ ] Switch selector giữ kiểu tĩnh sealed interface thay vì bị làm rộng thành `Object`?
- [ ] Các `case` không guard bao phủ đủ subtype; không có `default` đang nuốt variant mới?
- [ ] Chính sách `null` được quyết định riêng?
- [ ] Type pattern hay record pattern được chọn theo dữ liệu mà nhánh cần dùng?
- [ ] Nested record pattern có cơ chế cho component `null` hoặc không khớp?
- [ ] Các guard `when` được đặt trước nhánh chung và có test ngưỡng?
- [ ] Không có dominance do supertype hoặc type pattern tổng quát đứng trước?
- [ ] Nhánh `non-sealed` được bao phủ bằng type pattern đủ rộng?
- [ ] Business logic dài được tách ra handler/policy, không chất vào từng case?
- [ ] Khi thêm subtype mới, các switch và module phụ thuộc được biên dịch, test và triển khai tương thích?
- [ ] Các tên pattern variable phản ánh đúng domain, trạng thái và đơn vị?

## 18. Tài liệu chính thức

- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409): mục đích, khai báo `sealed`, `permits` và quy tắc subtype.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): pattern `case`, guard `when`, exhaustiveness, dominance, `null` trong Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): giải cấu trúc record và nested record pattern trong Java 21.
- [JLS Java SE 21 §9.1.1.4 — sealed Interfaces](https://docs.oracle.com/javase/specs/jls/se21/html/jls-9.html#jls-9.1.1.4): điều kiện khai báo sealed interface và subtype được phép.
- [JLS Java SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): switch blocks, case labels, dominance và exhaustiveness.
- [JLS Java SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): kết quả và tính exhaustive của switch expression.
- [JLS Java SE 21 §14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type pattern, record pattern, pattern applicability.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): ví dụ Java 21 với sealed hierarchy và case patterns.
