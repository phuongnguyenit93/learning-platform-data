# Viết guard ngắn và dễ đọc với `when` trong Java 21

## 1. Mục tiêu: guard nói rõ quy tắc, không che giấu quy tắc

Trong **pattern matching for switch** của Java 21, một nhánh `case` có thể thêm điều kiện `when` sau pattern:

```java
return switch (value) {
    case String text when text.isBlank() -> "blank";
    case String text -> "text: " + text;
    case null -> "missing";
    default -> "unsupported";
};
```

Phần `String text` là **type pattern**; `text.isBlank()` là **guard expression**. Java chỉ đánh giá guard sau khi `String text` đã khớp, nhờ vậy biến pattern `text` có thể được sử dụng an toàn trong guard.

Một guard tốt giúp người đọc trả lời nhanh hai câu hỏi:

- **Đang xét biến thể nào?** Ví dụ: `PaymentCaptured`, `String`, `LoginAttempt`.
- **Điều kiện bổ sung nào khiến biến thể này được chọn?** Ví dụ: số tiền vượt ngưỡng, chuỗi rỗng, tài khoản đủ điều kiện.

**Guard ngắn và dễ đọc** không đơn thuần là có ít ký tự. Nó phải mô tả chính xác ý định nghiệp vụ, có điều kiện dễ dự đoán, thứ tự case rõ ràng và có thể kiểm thử mà không cần hiểu hàng chục phép toán trong một dòng.

Bài này dùng Java 21 chuẩn: `when`, type patterns, record patterns và pattern `switch` đã chính thức, **không cần `--enable-preview`**.

## 2. Cơ chế `when`: pattern khớp trước, guard mới được xét

Hình dạng phổ biến:

```java
case Type variable when booleanExpression -> result
```

hoặc với record pattern:

```java
case PaymentCaptured(var paymentId, var amountVnd)
        when amountVnd >= 1_000_000L -> result
```

Diễn giải theo thứ tự:

1. Selector của `switch` được đánh giá.
2. Java xét pattern tại một nhãn `case`.
3. Nếu pattern **không khớp**, guard của nhãn đó **không được đánh giá**.
4. Nếu pattern khớp, các pattern variable được liên kết, rồi guard được đánh giá thành `boolean`.
5. Guard **true**: nhánh được chọn. Guard **false**: nhãn này không áp dụng, quá trình xét các nhãn tiếp tục.

Điều kiện sau `when` phải là biểu thức có kiểu `boolean` hoặc `Boolean` có thể unbox thành boolean. Để dễ kiểm soát, ưu tiên trả về **boolean nguyên thủy** từ các hàm guard; tránh kết quả `Boolean` có thể là `null` và gây `NullPointerException` khi unbox.

**Phân biệt với cú pháp khác:**

- `when` là phần **guard của một pattern case label**, không phải toán tử áp dụng tùy ý sau `case null`, `default` hoặc nhãn hằng số.
- Trong `if`, viết `if (obj instanceof String text && !text.isBlank())`, **không** viết `if (obj instanceof String text when ...)`.
- Cú pháp preview cũ như `case String text && text.length() > 3` đã được thay bằng `case String text when text.length() > 3` trong Java 21.
- `when` được Java 21 xử lý như contextual keyword trong ngữ cảnh phù hợp; nó không biến mọi lần xuất hiện của chuỗi `when` trong mã thành guard.

## 3. Sáu nguyên tắc viết guard dễ đọc

| Nguyên tắc | Nên làm | Tránh |
| --- | --- | --- |
| **Một ý nghĩa chính** | `when amountVnd >= LARGE_PAYMENT_VND` | Trộn phân quyền, trạng thái và tính tiền vào một guard |
| **Tên có nghĩa** | `when isEligibleForRefund(refund)` | `when check(x) && p(y)` |
| **Ít tầng logic** | `when isHighRiskAttempt(userId, attempts)` | Một chuỗi dài `&&` và `||` khó nhìn |
| **Không có side effect** | Hàm chỉ tính kết quả `boolean` | Ghi DB, gửi thông báo hoặc cập nhật state trong guard |
| **Thứ tự ưu tiên rõ** | Guard chuyên biệt trước case tổng quát | Case tổng quát đứng trước làm guard bị che |
| **Có nhánh cơ sở** | `case Paid payment -> ...` sau các nhánh guard | Chỉ có nhánh guarded khiến một số giá trị không được xử lý |

Một quy tắc hữu ích: **người review phải hiểu guard mà không phải thực hiện mô phỏng cả quy trình nghiệp vụ**. Nếu không thể, đó là lúc đặt tên cho một predicate riêng hoặc làm rõ dữ liệu domain.

## 4. Viết điều kiện đơn giản trực tiếp sau `when`

Guard ngắn và rõ nghĩa có thể viết ngay trong `case`:

```java
case String text when text.isBlank() -> "blank input";
case Integer quantity when quantity < 0 -> "invalid quantity";
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 1_000_000L -> "large payment";
```

Ba ví dụ trên là **mảnh nhãn case** trong switch phù hợp, không phải chương trình độc lập. Chúng tốt vì điều kiện được nhận ra ngay, không cần kiến thức ẩn:

- `isBlank()`: chuỗi chỉ gồm khoảng trắng hoặc rỗng.
- `quantity < 0`: số lượng âm.
- `amountVnd >= 1_000_000L`: số tiền từ một triệu VND, gồm cả đúng mốc.

Khi ngưỡng là chính sách nghiệp vụ, thay số trực tiếp bằng hằng số có tên:

```java
static final long LARGE_PAYMENT_VND = 1_000_000L;

// Trong switch:
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= LARGE_PAYMENT_VND -> "large payment";
```

Cách này tách ý nghĩa *“thanh toán lớn”* khỏi con số cấu hình cụ thể. Đừng đặt hằng số chỉ tên `LIMIT`, vì không nói rõ giới hạn của cái gì hoặc dùng đơn vị nào.

### 4.1. Đừng đưa mọi kiểm tra vào guard

Ví dụ:

```java
// MẢNH MÃ minh họa cấu trúc khó duy trì:
case PaymentCaptured(var id, var amount)
        when amount > 0
             && id != null
             && !id.isBlank()
             && amount >= 1_000_000L
             && policyAllows(id)
             && riskScore(id) < 40 -> "approved";
```

`policyAllows` và `riskScore` là các hàm giả định. Dòng mã vừa kiểm tra dữ liệu, vừa phân loại số tiền, vừa kiểm tra policy và rủi ro. Người đọc không biết điều kiện nào là bản chất của nhánh.

Hãy xem xét **tách dữ liệu hợp lệ ở ranh giới vào**, **tách phép phân loại**, và **chuyển quyết định nghiệp vụ phức tạp thành predicate có tên**. Không nhất thiết chuyển mọi điều kiện sang helper; điều kiện đơn giản nên để tại chỗ.

## 5. Dùng predicate có tên khi điều kiện biểu đạt một quy tắc domain

Giả sử cần xác định lần đăng nhập có cần cảnh báo:

```java
static final int ALERT_THRESHOLD = 3;

static boolean requiresLoginAlert(String userId, int failedAttempts) {
    return userId != null
            && !userId.isBlank()
            && failedAttempts >= ALERT_THRESHOLD;
}
```

Trong `switch`:

```java
case LoginAttempt(var userId, var failedAttempts)
        when requiresLoginAlert(userId, failedAttempts) ->
    "security alert for " + userId;
```

Tên `requiresLoginAlert` làm rõ **ý nghĩa domain**. Phần triển khai tách riêng để test được:

- Mã người dùng không được `null`.
- Mã người dùng không blank.
- Số lần thất bại ít nhất bằng ngưỡng.

Đoạn mã trên là **mảnh minh họa**; kiểu `LoginAttempt` được khai báo trong chương trình hoàn chỉnh ở mục 12.

**Khi nào nên tách helper?** Khi có một trong các dấu hiệu: điều kiện có nhiều nhóm logic, dùng lại ở nhiều nơi, cần test biên độc lập, hoặc tên helper giải thích ý nghĩa tốt hơn toàn bộ biểu thức boolean.

**Khi nào không nên tách?** Một kiểm tra `text.isBlank()` hoặc `amountVnd >= LARGE_PAYMENT_VND` rõ ràng ngay tại chỗ thường tốt hơn việc phải nhảy sang hàm `isBlankString(text)` không mang thêm giá trị.

### 5.1. Tên hàm cần diễn tả predicate, không diễn tả tác động

Nên chọn tên câu hỏi trả về `boolean`:

- `isLargePayment(amountVnd)`
- `requiresLoginAlert(userId, attempts)`
- `isRefundEligible(refund)`
- `hasActiveSubscription(customer)`

Hạn chế các tên mơ hồ như `process`, `check`, `validate`, `doWork`. Đặc biệt, `validatePayment` có thể ngụ ý ném lỗi hoặc thay đổi trạng thái; nếu chỉ trả `boolean`, `isPaymentEligible` dễ hiểu hơn.

Không nên dùng helper chỉ để **ẩn logic không an toàn**. Hàm tên `isEligible` nhưng có tác dụng phụ quan trọng vẫn khiến guard khó dự đoán.

## 6. Giữ guard thuần (pure) và rẻ

Một guard có thể được đánh giá khi pattern khớp, trước khi nhánh được chọn. Nếu guard làm thay đổi thế giới bên ngoài, việc sửa thứ tự hoặc thêm `case` có thể thay đổi số lần hoặc thời điểm xảy ra tác động.

**Không nên:**

```java
// MẢNH CÚ PHÁP nên tránh nếu reserveBalance() làm thay đổi số dư:
case PaymentRequested request
        when reserveBalance(request) -> "reserved";
```

Ví dụ `reserveBalance` là một thao tác giả định có side effect. Khi guard trả `false`, các nhánh sau vẫn có thể được xét nhưng số dư có thể đã thay đổi. Khi một case trước mới được thêm vào, guard có thể không chạy nữa và tác động cũng biến mất.

**Nên phân tách:**

1. Dùng guard để **phân loại bằng dữ liệu đã có**, tốt nhất là một predicate thuần.
2. Sau khi `switch` chọn nhánh, thực hiện thao tác tại handler hoặc bước xử lý riêng.
3. Xử lý lỗi I/O, timeout, transaction và retry bên ngoài biểu thức guard ngắn.

Ví dụ ý tưởng:

```java
// MẢNH MÃ: các hàm nghiệp vụ cần được định nghĩa riêng
switch (event) {
    case PaymentRequested request
            when isEligibleForReservation(request) ->
        reserveBalance(request);
    case PaymentRequested request ->
        rejectReservation(request);
    default -> handleOther(event);
}
```

Guard chỉ quyết định **đủ điều kiện hay không**; thao tác `reserveBalance` chỉ thực hiện trong thân nhánh đã được chọn. Nếu điều kiện eligibility phụ thuộc trạng thái có thể thay đổi, handler vẫn cần biện pháp transaction/concurrency thích hợp; một guard thuần không thể thay thế kiểm tra nguyên tử tại điểm thực thi.

### 6.1. Ngoại lệ trong guard không tự động biến thành “guard false”

Nếu predicate ném exception, `switch` không coi exception đó như `false` để tiếp tục nhánh khác. Lỗi được lan truyền theo quy tắc Java thông thường. Do đó, predicate nên có hợp đồng về `null` và lỗi rõ ràng; xử lý ngoại lệ ở lớp thích hợp thay vì che mọi lỗi bằng `catch (Exception e) { return false; }`.

## 7. Bố trí case: guard đặc biệt trước case cơ sở

Với cùng một biến thể, thường dùng mẫu:

```java
return switch (payment) {
    case null -> "missing";
    case PaymentCaptured(var id, var amountVnd)
            when amountVnd >= 1_000_000L ->
        "large payment";
    case PaymentCaptured(var id, var amountVnd) ->
        "payment";
    default -> "other event";
};
```

Đây là **mảnh ví dụ** giả sử selector có kiểu cho phép các case trên. Có ba quyết định tách biệt:

- Pattern `PaymentCaptured(...)` giới hạn subtype.
- Guard chọn nhánh có chính sách đặc biệt.
- Nhánh cùng subtype **không guard** nhận phần còn lại của subtype đó.

Nếu đảo vị trí hai nhánh:

```java
// MẢNH CÚ PHÁP CỐ Ý SAI: compiler báo dominated case
case PaymentCaptured(var id, var amountVnd) -> "payment";
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 1_000_000L -> "large payment";
```

Nhánh đầu bao phủ tất cả `PaymentCaptured`, nên nhánh có guard đứng sau không thể được chọn; đây là vấn đề **dominance**. Việc viết guard dễ đọc không đủ nếu đặt sai thứ tự.

### 7.1. Nhiều mức ưu tiên

Giả sử nghiệp vụ có ba hạng thanh toán:

```java
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 5_000_000L -> "VIP";
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 1_000_000L -> "LARGE";
case PaymentCaptured(var id, var amountVnd) -> "STANDARD";
```

Đọc từ trên xuống: số tiền từ 5 triệu nhận `VIP`; từ 1 triệu đến dưới 5 triệu nhận `LARGE`; phần còn lại nhận `STANDARD`. Nếu đảo hai guard, khoản từ 5 triệu có thể rơi vào nhánh `LARGE` trước.

Java không chứng minh mọi quan hệ toán học của các guard tùy ý; hãy **test 999.999, 1.000.000, 4.999.999, 5.000.000 và 5.000.001**. Thứ tự case thể hiện chính sách ưu tiên, không chỉ là lựa chọn định dạng.

## 8. Giữ biểu thức boolean có cấu trúc dễ hiểu

Khi một guard cần nhiều phép kiểm tra, ưu tiên một trong hai cách:

**Cách A — Một chuỗi `&&` ngắn, có thứ tự tự nhiên:**

```java
case LoginAttempt(var userId, var attempts)
        when userId != null
             && !userId.isBlank()
             && attempts >= 3 -> "alert";
```

`&&` short-circuit từ trái sang phải. Kiểm tra `userId != null` trước `userId.isBlank()` để tránh dereference `null`.

**Cách B — Một predicate có tên:**

```java
case LoginAttempt(var userId, var attempts)
        when requiresLoginAlert(userId, attempts) -> "alert";
```

Nếu guard kết hợp `&&` và `||`, nên tách nhóm rõ bằng ngoặc hoặc tách helper. Ví dụ:

```java
// MẢNH HÀM: flags are primitive booleans
static boolean requiresReview(
        boolean manualFlag,
        boolean fraudFlag,
        boolean isHighAmount) {
    return manualFlag || (fraudFlag && isHighAmount);
}
```

Khi đọc mà phải nhớ thứ tự ưu tiên toán tử mới hiểu ý định, đặt ngoặc để truyền đạt cấu trúc nghiệp vụ.

### 8.1. Không dùng phép so sánh thừa

Giả sử `isBlank()` đã trả về boolean:

```java
// Dài hơn mà không tăng nghĩa:
case String text when text.isBlank() == true -> "blank";

// Rõ ràng hơn:
case String text when text.isBlank() -> "blank";
```

Và thay vì `when !(!text.isBlank())`, hãy dùng `when text.isBlank()`. Guard ít phủ định lồng nhau dễ kiểm tra hơn.

### 8.2. Đặt tên biến giúp điều kiện đọc như câu nghiệp vụ

So sánh:

```java
case PaymentCaptured(var x, var y) when y >= 1_000_000L -> "large";
case PaymentCaptured(var paymentId, var paidAmountVnd)
        when paidAmountVnd >= LARGE_PAYMENT_VND -> "large";
```

Cách thứ hai nói rõ đại lượng nào được kiểm tra, đơn vị là gì và ngưỡng có ý nghĩa gì. Với record pattern, tên được liên kết **theo vị trí component**, nên phải xác nhận `paidAmountVnd` thực sự là component số tiền chứ không phải một giá trị khác cùng kiểu `long`.

## 9. `null` và sự khác nhau giữa pattern fail và guard false

Một pattern `case String text` chỉ khớp `String` không `null`. Nếu selector `null`, guard `text.isBlank()` **không được chạy**.

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text when text.isBlank() -> "blank";
        case String text -> "text";
        default -> "unsupported";
    };
}
```

Các giá trị khác nhau dẫn đến đường đi khác nhau:

| Giá trị | Kết quả | Giải thích |
| --- | --- | --- |
| `null` | `missing` | Khớp `case null` |
| `" "` | `blank` | Khớp `String`, guard `isBlank()` true |
| `"abc"` | `text` | Khớp `String`, guard false, nhánh `String` tiếp nhận |
| `42` | `unsupported` | Không khớp `String`, guard không chạy |

Nếu selector có thể `null` mà không có nhãn `case null` phù hợp, switch Java 21 thường ném `NullPointerException`; **`default` không thay cho `case null`**. Viết guard chỉ để xử lý `null` của selector là sai chỗ; hãy quyết định chính sách `null` riêng.

**Khác với selector**, các component trong record có thể có giá trị `null` tùy mô hình. Nếu guard gọi phương thức trên component, cần xử lý an toàn:

```java
// MẢNH CÚ PHÁP: CustomerEvent có component email có thể null
case CustomerEvent(var email)
        when email != null && !email.isBlank() ->
    "email present";
```

Record pattern `CustomerEvent(var email)` không tự bảo đảm `email` khác `null` chỉ vì selector là record; guard phải xét ràng buộc dữ liệu khi cần.

## 10. Exhaustiveness: chỉ có guard chưa chắc xử lý hết subtype

Với sealed domain:

```java
sealed interface Result permits Success, Failure {}
record Success(String value) implements Result {}
record Failure(String reason) implements Result {}
```

Một switch expression chỉ có nhánh `Success` **có guard** và nhánh `Failure` không guard có thể thiếu trường hợp `Success` không thỏa guard:

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH:
return switch (result) {
    case Success(var value) when value != null -> "ok";
    case Failure(var reason) -> "failed";
};
```

Nếu `Success.value()` là `null`, nhánh `Success` có guard không chọn, còn `Failure` không khớp. Compiler không thể coi `when value != null` như bao phủ mọi `Success`.

**Sửa** bằng một nhánh cơ sở không guard cho `Success`:

```java
return switch (result) {
    case Success(var value) when value != null -> "ok: " + value;
    case Success(var value) -> "success without value";
    case Failure(var reason) -> "failed: " + reason;
};
```

Khi các subtype của sealed hierarchy được bao phủ đầy đủ, không cần thêm `default` chỉ để thỏa compiler. Một `default` vô điều kiện có thể che thiếu nhánh khi mở rộng domain về sau.

**Ngoại lệ cần biết:** `when true` là trường hợp đặc biệt mà Java có thể coi là guard không hạn chế về bao phủ. Tuy nhiên, nếu mục tiêu là diễn đạt nhánh tổng quát, viết **không guard** thường rõ ràng hơn `when true`.

## 11. Dùng `when` đúng chỗ trong kiến trúc

Có một ranh giới thực tế giữa “phân loại dữ liệu” và “thi hành nghiệp vụ”:

```text
Input
  |
  v
Validate / normalize dữ liệu cần thiết
  |
  v
switch: match subtype + guard ngắn
  |
  +--> case A -> handler A
  +--> case B -> handler B
  +--> case C -> handler C
  |
  v
Kết quả hoặc tác động được kiểm soát
```

Nếu một guard có nhiều quy tắc thay đổi độc lập, cân nhắc:

- **Predicate có tên:** điều kiện thuần, tái sử dụng được, test đơn vị được.
- **Policy object:** khi quy tắc phụ thuộc cấu hình/các chiến lược do hệ thống quản lý.
- **Validation trước switch:** khi dữ liệu cần chuẩn hóa hoặc từ chối trước khi phân loại.
- **Handler sau switch:** khi hành động có side effect hoặc xử lý ngoại lệ phức tạp.

Ví dụ, thay vì nhét kiểm tra limit, fraud, customer eligibility và truy vấn database vào một guard cho `PaymentCaptured`, chuyển chúng sang một bước **đánh giá đủ điều kiện** có hợp đồng rõ. Switch sau đó phân loại kết quả đánh giá, không trực tiếp ra lệnh thực hiện giao dịch trong guard.

Không nên “lạm dụng clean code” bằng cách tạo 10 helper chỉ để gọi một phép `>` đơn giản. Tối ưu cho **người đọc mã ở vị trí đang dùng**.

## 12. Chương trình Java 21 hoàn chỉnh: guard ngắn, có helper và nhánh cơ sở

Lưu vào tệp **`ReadableGuardDemo.java`**:

```java
public class ReadableGuardDemo {
    private static final long LARGE_PAYMENT_VND = 1_000_000L;
    private static final int LOGIN_ALERT_THRESHOLD = 3;

    sealed interface Event
            permits PaymentCaptured, LoginAttempt, RefundRequested {}

    record PaymentCaptured(String paymentId, long amountVnd)
            implements Event {}

    record LoginAttempt(String userId, int failedAttempts)
            implements Event {}

    record RefundRequested(String refundId, long amountVnd,
                           boolean approved)
            implements Event {}

    static boolean isLargePayment(long amountVnd) {
        return amountVnd >= LARGE_PAYMENT_VND;
    }

    static boolean requiresLoginAlert(String userId, int failedAttempts) {
        return userId != null
                && !userId.isBlank()
                && failedAttempts >= LOGIN_ALERT_THRESHOLD;
    }

    static boolean isRefundReady(long amountVnd, boolean approved) {
        return approved && amountVnd > 0;
    }

    static String describe(Event event) {
        return switch (event) {
            case null -> "missing event";

            case PaymentCaptured(var paymentId, var amountVnd)
                    when isLargePayment(amountVnd) ->
                "large payment " + paymentId + ": " + amountVnd + " VND";

            case PaymentCaptured(var paymentId, var amountVnd) ->
                "payment " + paymentId + ": " + amountVnd + " VND";

            case LoginAttempt(var userId, var failedAttempts)
                    when requiresLoginAlert(userId, failedAttempts) ->
                "login alert " + userId + ": " + failedAttempts + " failures";

            case LoginAttempt(var userId, var failedAttempts) ->
                "login " + userId + ": " + failedAttempts + " failures";

            case RefundRequested(var refundId, var amountVnd, var approved)
                    when isRefundReady(amountVnd, approved) ->
                "refund ready " + refundId + ": " + amountVnd + " VND";

            case RefundRequested(var refundId, var amountVnd, var approved) ->
                "refund pending " + refundId;
        };
    }

    static void check(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expected + "; actual: " + actual);
        }
    }

    public static void main(String[] args) {
        Event[] events = {
            new PaymentCaptured("PAY-1", 1_500_000L),
            new PaymentCaptured("PAY-2", 200_000L),
            new LoginAttempt("lan", 3),
            new LoginAttempt("minh", 1),
            new RefundRequested("REF-1", 100_000L, true),
            new RefundRequested("REF-2", 0L, true),
            new RefundRequested("REF-3", 90_000L, false),
            null
        };

        for (Event event : events) {
            System.out.println(describe(event));
        }

        check("large payment PAY-1: 1500000 VND",
                describe(new PaymentCaptured("PAY-1", 1_500_000L)));
        check("payment PAY-3: 999999 VND",
                describe(new PaymentCaptured("PAY-3", 999_999L)));
        check("large payment PAY-4: 1000000 VND",
                describe(new PaymentCaptured("PAY-4", 1_000_000L)));
        check("login alert lan: 3 failures",
                describe(new LoginAttempt("lan", 3)));
        check("login : 7 failures",
                describe(new LoginAttempt("", 7)));
        check("refund pending REF-2",
                describe(new RefundRequested("REF-2", 0L, true)));
        check("missing event", describe(null));

        System.out.println("checks passed");
    }
}
```

Biên dịch và chạy bằng **JDK 21**, không bật preview:

```bash
javac --release 21 ReadableGuardDemo.java
java ReadableGuardDemo
```

**Stdout:**

```text
large payment PAY-1: 1500000 VND
payment PAY-2: 200000 VND
login alert lan: 3 failures
login minh: 1 failures
refund ready REF-1: 100000 VND
refund pending REF-2
refund pending REF-3
missing event
checks passed
```

Các chi tiết cần nhận diện:

- `PaymentCaptured(...)`, `LoginAttempt(...)`, `RefundRequested(...)` là **record patterns**.
- Các `var` bên trong là pattern component variables được suy luận kiểu từ record.
- `isLargePayment`, `requiresLoginAlert`, `isRefundReady` là **predicate thuần** có tên gắn với luật nghiệp vụ.
- Mỗi nhánh guarded đều có một nhánh **không guard cùng subtype** theo sau; nhờ vậy những giá trị không đạt điều kiện đặc biệt vẫn được xử lý.
- `case null` có chính sách rõ ràng; không cần `default` vì `Event` là sealed hierarchy đóng gồm ba record.
- `check` kiểm thử ngay dưới và đúng ngưỡng thanh toán, số lần login và trạng thái hoàn tiền; không cần bật assertions `-ea`.
- Đầu vào `LoginAttempt("", 7)` cho thấy guard từ chối cảnh báo nếu `userId` blank, nhưng nhánh tổng quát vẫn trả một mô tả: **việc từ chối dữ liệu không hợp lệ phải do validation riêng quyết định**, không được đánh đồng mọi nhánh fallback với dữ liệu hợp lệ.

Một số quy tắc nghiệp vụ trong ví dụ được đơn giản hóa để minh họa cách viết guard; trong ứng dụng thật, `isRefundReady` có thể cần những dữ kiện như trạng thái giao dịch, số tiền còn có thể hoàn, quyền và thời hạn. Những kiểm tra đó nên nằm trong policy hoặc service có hợp đồng rõ ràng, không tự ý nhét thêm vào một guard dài.

## 13. Những lỗi thường gặp khi viết guard

### Lỗi 1 — Nhánh không guard đứng trước nhánh có guard

```java
// MẢNH MÃ CỐ Ý SAI, bị dominated
case String text -> "any text";
case String text when text.isBlank() -> "blank";
```

**Sửa:** chuyển nhánh `when text.isBlank()` lên trước, nhánh `String text` xuống sau.

### Lỗi 2 — Viết `when` ở sai vị trí

```java
// MẢNH MÃ CỐ Ý SAI
if (obj instanceof String text when !text.isBlank()) {
    System.out.println(text);
}
```

**Sửa:** với `if`, dùng `&&`:

```java
if (obj instanceof String text && !text.isBlank()) {
    System.out.println(text);
}
```

### Lỗi 3 — Dùng tên pattern variable ngoài scope

```java
// MẢNH MÃ CỐ Ý SAI
switch (obj) {
    case String text when text.isBlank() -> System.out.println(text);
    default -> {}
}
System.out.println(text); // text không ở scope này
```

**Sửa:** dùng biến trong guard/thân nhánh, hoặc trả về một kết quả chung từ switch expression và dùng biến kết quả bên ngoài.

### Lỗi 4 — Không có nhánh cơ sở cho subtype khi guard false

```java
// MẢNH MÃ CỐ Ý KHÔNG BIÊN DỊCH ở switch expression trên sealed Result
return switch (result) {
    case Success(var value) when value != null -> "ok";
    case Failure(var reason) -> "failed";
};
```

**Sửa:** thêm `case Success(var value) -> ...` không guard để bao phủ phần còn lại.

### Lỗi 5 — Guard dùng `||` không có nhóm rõ ràng

```java
// Khó đọc: cần xác nhận đúng ưu tiên toán tử
when isPriorityCustomer(customer) || isUrgent(order) && hasStock(order)
```

**Sửa:** dùng ngoặc `isPriorityCustomer(customer) || (isUrgent(order) && hasStock(order))` khi đó đúng nghiệp vụ, hoặc đưa vào `requiresFastLane(customer, order)` có test.

### Lỗi 6 — Guard có side effect

```java
// MẢNH CÚ PHÁP cần tránh
case Order order when chargeCreditCard(order) -> "paid";
```

**Sửa:** guard chỉ nhận diện trường hợp; thao tác thu tiền thực hiện trong handler với transaction/idempotency thích hợp. Không biến guard false thành thất bại nghiệp vụ có thể đã gây tác động.

### Lỗi 7 — Hard-code magic number

```java
case PaymentCaptured(var id, var amountVnd)
        when amountVnd >= 1000000 -> "large";
```

**Sửa:** dùng `LARGE_PAYMENT_VND` hoặc policy có tên; xác nhận ngưỡng và đơn vị với domain trước khi triển khai.

### Lỗi 8 — Nuốt mọi lỗi bằng điều kiện trả false

```java
// MẢNH HÀM phản ví dụ, không nên viết như thế này:
static boolean isEligible(Payment payment) {
    try {
        return externalService.check(payment);
    } catch (Exception ignored) {
        return false;
    }
}
```

**Vấn đề:** `false` có thể mang nghĩa “không đủ điều kiện” nhưng ở đây còn che lỗi kết nối, timeout hoặc lỗi lập trình. Trong hệ thống thực, cần tách lỗi kỹ thuật khỏi kết quả phân loại nghiệp vụ, có cách quan sát và xử lý rõ. `Payment` và `externalService` trong mảnh mã chỉ là giả định.

## 14. Bài tập đọc mã và đáp án

**Bài 1.** Vì sao nên viết hai nhánh theo thứ tự sau?

```java
case String text when text.isBlank() -> "blank";
case String text -> "non-blank";
```

**Đáp án:** Nhánh có guard chọn trường hợp đặc biệt trước. Nhánh `String` không guard đứng sau nhận các `String` còn lại. Nếu đảo vị trí, nhánh `when` sau bị nhánh tổng quát bao phủ.

**Bài 2.** Đoạn sau có đúng kiểu Java 21 không?

```java
case Integer value && value > 10 -> "large";
```

**Đáp án:** Không. Đây là dạng gợi nhớ cú pháp preview cũ. Java 21 chuẩn viết `case Integer value when value > 10 -> "large";`.

**Bài 3.** Một guard dài gọi `queryDatabase()`, `sendEmail()` và `isEligible()` nên sửa ở đâu?

**Đáp án:** Đưa tác động I/O và gửi email ra khỏi guard, vào handler hoặc bước nghiệp vụ có quản lý lỗi. Điều kiện phân loại có thể rút thành predicate thuần có tên, được test riêng. Không coi việc bọc side effect trong một helper là đã giải quyết thiết kế.

**Bài 4.** Với `case String s when s.length() > 3`, guard có chạy khi selector là `Integer` không?

**Đáp án:** Không. Pattern `String s` thất bại nên guard không được đánh giá. Khi selector là `String`, `s` được liên kết và guard mới được xét.

**Bài 5.** Có nên dùng `default` để sửa switch sealed domain thiếu nhánh do guard false?

**Đáp án:** Thường không. Nếu mọi subtype cần được xử lý riêng, thêm nhánh không guard tương ứng thay vì `default` để compiler tiếp tục phát hiện subtype mới. Với nguồn thực sự mở kiểu `Object`, `default` là chính sách fallback hợp lý.

**Bài 6.** Khi nào giữ `when amount >= LIMIT` ngay trong case thay vì tách helper?

**Đáp án:** Khi điều kiện đơn giản, dùng một chỗ, tên biến và `LIMIT` đã thể hiện đầy đủ ý nghĩa. Tách helper khi nó là quy tắc domain nhiều bước, dùng lại hoặc cần kiểm thử độc lập.

**Bài 7.** `when userId != null && !userId.isBlank()` có tác dụng gì?

**Đáp án:** `&&` short-circuit: nếu `userId` là `null`, Java không gọi `isBlank()`; guard trả về false và switch tiếp tục thử nhánh phù hợp tiếp theo. Điều này kiểm tra component, không phải `null` của selector.

## 15. Checklist review một guard `when`

- [ ] Guard bổ sung **một điều kiện rõ nghĩa** sau khi pattern đã khớp.
- [ ] Tên pattern variable, predicate và hằng số truyền đạt đúng domain/đơn vị.
- [ ] Điều kiện ngắn được viết trực tiếp; điều kiện nhiều ý nghĩa được tách thành predicate có tên.
- [ ] Predicate không thực hiện I/O, ghi state hoặc tác động giao dịch không kiểm soát.
- [ ] Có hợp đồng rõ về `null`, exception, loại dữ liệu và giá trị biên.
- [ ] Các phép `&&`, `||`, `!` có ngoặc và thứ tự phù hợp ý định.
- [ ] Nhánh guard ưu tiên nằm trước nhánh tổng quát; không có dominance bất ngờ.
- [ ] Mỗi subtype được xử lý khi guard true **và** false, nếu domain yêu cầu exhaustive.
- [ ] Không dùng `default` để che việc thiếu nhánh trong sealed hierarchy cần xử lý đầy đủ.
- [ ] `case null` hoặc chính sách từ chối `null` được xác định riêng.
- [ ] Các ngưỡng được test ngay dưới, đúng bằng và ngay trên mốc.
- [ ] Phân biệt lỗi kỹ thuật với guard false; không âm thầm nuốt exception.

## 16. Tài liệu chính thống

- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): cú pháp guard `when`, type patterns, dominance và exhaustiveness trong Java 21.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): record pattern và biến component dùng trong guard.
- [JLS Java SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): case labels, guard, selection và dominance.
- [JLS Java SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expression và exhaustiveness.
- [JLS Java SE 21 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): phạm vi pattern variable trong biểu thức guard và nhánh.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): hướng dẫn cú pháp và ví dụ guard.
