# Thực hành tổng hợp: Viết switch expression trên sealed type (Java 21)

## 1. Mục tiêu học tập và bài toán

Trong Java 21, `switch expression` có thể dùng **type patterns**, **record patterns**, **guard `when`** và danh sách các subtype của một kiểu **`sealed`**. Khi các nhánh bao phủ được toàn bộ hierarchy, compiler có thể xác nhận switch expression **exhaustive** mà không cần thêm `default` chỉ để cho code biên dịch.

Bài thực hành tổng hợp này không dừng ở một ví dụ `switch` trả chuỗi. Người học sẽ:

1. Thiết kế một **sealed hierarchy nhiều tầng** theo nghiệp vụ.
2. Viết một `switch expression` trả chuỗi, bao phủ mọi subtype cụ thể.
3. Phân rã record bằng record pattern và xử lý một record con có thể bằng `null`.
4. Viết hai case cho cùng một kiểu với `when`, trong đó case có guard đứng **trước** case không guard.
5. So sánh với cách viết switch theo subtype **trung gian** để gom nhóm.
6. Trả về một **kiểu kết quả có cấu trúc** bằng switch expression và `yield` khi case cần nhiều câu lệnh.
7. Kiểm thử `null`, ngưỡng, nhánh dự phòng, exhaustiveness và dominance bằng dữ liệu xác định.
8. Hiểu hành vi khi hierarchy thay đổi và cách biến lỗi compiler thành lợi thế kiểm soát API.

**Điều kiện chạy:** JDK 21 trở lên cho record patterns và pattern matching for switch bản chính thức (JEP 440, JEP 441). Sealed classes/interfaces đã chính thức từ Java 17 (JEP 409). Ví dụ có thể được biên dịch với `javac --release 21` và không sử dụng tính năng preview.

### Bối cảnh nghiệp vụ

Một ứng dụng thanh toán nhận các **kết quả sự kiện thanh toán**:

- `Authorized`: khoản thanh toán đã được chấp thuận, có mã giao dịch và tổng tiền.
- `Declined`: bị từ chối, có mã giao dịch và mã lý do.
- `AnalystReview`: cần nhân viên phân tích xem lại.
- `FraudAlert`: có tín hiệu rủi ro gian lận cần kiểm tra.

Hai loại cuối cùng thuộc nhóm `ReviewEvent`. Ta muốn hiển thị tóm tắt sự kiện, phân loại thành nhóm nghiệp vụ, và tạo hành động cho giao diện hoặc hàng chờ review.

Đây là bài tập về **phân nhánh trên tập kiểu đóng**, không phải cài đặt hệ thống thanh toán thực. Những chuỗi `"approved"` và `"fraud"` trong ví dụ chỉ là nhãn mô phỏng; không được hiểu là xác nhận giao dịch ngân hàng hay quyết định chống gian lận thật.

## 2. Đọc cây sealed trước khi viết switch

Mô hình kiểu:

```text
PaymentEvent (sealed interface)
├── Authorized      (record, final)
├── Declined        (record, final)
└── ReviewEvent     (sealed interface)
    ├── AnalystReview  (record, final)
    └── FraudAlert     (record, final)

Money (record value object; không phải PaymentEvent)

Decision (sealed interface kết quả hành động)
├── Screen       (record, final)
└── ReviewTicket (record, final)
```

Phần khai báo:

```java
sealed interface PaymentEvent
        permits Authorized, Declined, ReviewEvent {
    String paymentId();
}

sealed interface ReviewEvent extends PaymentEvent
        permits AnalystReview, FraudAlert {}

record Money(long cents, String currencyCode) {}

record Authorized(String paymentId, Money total)
        implements PaymentEvent {}

record Declined(String paymentId, String reasonCode)
        implements PaymentEvent {}

record AnalystReview(String paymentId, String reviewQueue)
        implements ReviewEvent {}

record FraudAlert(String paymentId, int riskScore)
        implements ReviewEvent {}
```

Đây là **đoạn minh họa cấu trúc**, có thể dùng bên trong một lớp bao ngoài như chương trình đầy đủ ở mục 9.

**Các quan hệ cần nhớ:**

- `PaymentEvent` có ba **direct permitted subtypes**: `Authorized`, `Declined`, `ReviewEvent`.
- `AnalystReview` và `FraudAlert` **không** xuất hiện trực tiếp trong `PaymentEvent permits`; chúng là subtype gián tiếp qua `ReviewEvent`.
- `ReviewEvent` lại `sealed`, nên tập con trực tiếp của nó bị giới hạn vào hai record.
- Record class là `final` ngầm định; vì vậy không có subtype sâu hơn của `Authorized`, `Declined`, `AnalystReview` hay `FraudAlert` theo cách kế thừa thông thường.
- Mỗi record có component `paymentId` kiểu `String` và accessor `paymentId()` do record tạo, đáp ứng hợp đồng của interface.
- `Money` không thuộc hierarchy; nó là giá trị thành phần của `Authorized`.

**Kết luận kiểu học thuật nhưng rất thực dụng:** nếu selector có kiểu tĩnh `PaymentEvent`, mọi **instance khác `null`** hợp lệ đều phải thuộc một trong bốn record lá trong mô hình hiện tại. Vì vậy switch có thể liệt kê bốn lá, hoặc dùng một case `ReviewEvent` bao phủ hai lá cuối.

## 3. Trước hết, viết phiên bản switch đơn giản theo subtype

Một mục tiêu đầu tiên là phân loại mỗi sự kiện:

```java
static String group(PaymentEvent event) {
    return switch (event) {
        case Authorized authorized -> "completed";
        case Declined declined -> "failed";
        case ReviewEvent review -> "manual";
    };
}
```

Phương thức này nằm trong chương trình mẫu ở mục 9, nơi các kiểu đã khai báo. Nó minh họa **type pattern**: `case Authorized authorized` kiểm tra kiểu và ràng buộc một tham chiếu `authorized`, nhưng không phân rã record.

Tại sao chỉ có ba case khi hierarchy có bốn record lá?

- `Authorized` được xử lý riêng.
- `Declined` được xử lý riêng.
- Mọi `AnalystReview` và `FraudAlert` đều là `ReviewEvent`, nên `case ReviewEvent review` bao phủ cả hai.

Compiler biết mối quan hệ ấy từ `sealed` và `permits`. Với selector kiểu `PaymentEvent`, đây là một **switch expression exhaustive** cho các giá trị khác `null`.

Nếu nghiệp vụ chỉ cần biết sự kiện thuộc nhóm hoàn tất/thất bại/xem xét thủ công, cách gom nhóm này thường **dễ đọc hơn** việc liệt kê mọi record lá. Nhưng nếu cần xử lý khác nhau theo từng subtype, phải thêm các case cụ thể thay vì gom tất cả vào `ReviewEvent`.

### So sánh với if/else

```java
static String groupIfElse(PaymentEvent event) {
    if (event instanceof Authorized) {
        return "completed";
    }
    if (event instanceof Declined) {
        return "failed";
    }
    if (event instanceof ReviewEvent) {
        return "manual";
    }
    throw new IllegalArgumentException("unhandled event");
}
```

Đây là đoạn Java minh họa có thể đặt trong lớp chứa các type tương ứng. Chuỗi `if` ở đây phải dùng một nhánh cuối để thể hiện đường không nhận diện; compiler không có cùng yêu cầu exhaustiveness theo hierarchy như với switch expression. Việc đổi sang `switch` làm **ý định bao phủ toàn bộ loại sự kiện** rõ ràng hơn.

## 4. Chuyển từ type pattern sang record pattern

Để hiển thị nội dung chi tiết, ta không chỉ cần biết `Authorized` có tồn tại mà còn cần đọc `paymentId` và `Money`.

### 4.1. Type pattern lấy nguyên record

```java
case Authorized authorized ->
        "approved:" + authorized.paymentId();
```

Đây là nhãn `case` minh họa trong switch. Nó giữ nguyên object `authorized` và dùng accessor một cách tường minh.

### 4.2. Record pattern lấy thành phần

```java
case Authorized(var paymentId, var total) ->
        "approved:" + paymentId;
```

`var paymentId` được suy ra kiểu `String`, còn `var total` được suy ra kiểu `Money`. Record pattern khớp các component theo **thứ tự khai báo trong record**, không phải theo tên biến.

### 4.3. Record pattern lồng nhau

```java
case Authorized(
        var paymentId,
        Money(var cents, var currencyCode)) ->
        "approved:" + paymentId + ":" + cents + " " + currencyCode;
```

Mẫu `Money(...)` chỉ khớp khi component `total` của `Authorized` là một record `Money` khác `null`. Đây là **mẫu hẹp hơn** so với `Authorized(var paymentId, var total)`.

Điều cần kiểm tra: nếu `Authorized` được tạo với `total == null`, mẫu lồng `Money(...)` không khớp. Bản thân selector vẫn là `Authorized`, không phải selector `null`. Vì thế, nếu muốn xử lý trường hợp này thay vì bỏ sót, cần một case `Authorized` tổng quát hơn sau các case hẹp.

## 5. Thêm guard `when` và sắp xếp case đúng thứ tự

Ta muốn hiển thị `Authorized` có số tiền từ 100.000 cent trở lên là loại `large`:

```java
case Authorized(
        var paymentId, Money(var cents, var currencyCode))
        when cents >= 100_000 ->
        "approved:large:" + paymentId + ":" + cents
                + " " + currencyCode;

case Authorized(
        var paymentId, Money(var cents, var currencyCode)) ->
        "approved:" + paymentId + ":" + cents
                + " " + currencyCode;

case Authorized(var paymentId, var total) ->
        "approved:missing-total:" + paymentId;
```

Ba nhãn này là **một phần của switch đầy đủ**, không phải file độc lập. Thứ tự mang ý nghĩa:

1. **Mẫu hẹp nhất + guard:** `Money` tồn tại và `cents >= 100_000`.
2. **Mẫu lồng không guard:** `Money` tồn tại nhưng không đạt ngưỡng.
3. **Mẫu Authorized tổng quát:** bao phủ tình huống còn lại, ví dụ `total == null`.

Nếu đặt case `Authorized(var paymentId, var total)` lên trước, nó bao phủ mọi `Authorized` khác `null` và các case `Authorized` hẹp phía sau có thể bị compiler từ chối do **dominance**. Nếu đặt mẫu `Money(...)` không guard lên trước mẫu có guard, mẫu có guard cũng có thể bị che phủ.

**Guard không phải kiểm tra hợp lệ toàn bộ domain.** Trong mô hình ví dụ, `Money` không kiểm định số tiền hoặc currency code. Mẫu và guard chỉ phân loại theo số đã có. Trong sản phẩm thật, nên có constructor/factory kiểm tra amount, mã tiền tệ và các ràng buộc nghiệp vụ.

### Tại sao không chỉ viết một case `Authorized` với nhiều if?

Có thể làm vậy, nhưng hai case có guard giúp thể hiện rõ chiến lược phân loại ngay tại cấu trúc `switch`. Nếu logic điều kiện nhiều bước, có I/O hoặc tác dụng phụ, một case tổng quát với helper function thuần hoặc xử lý trong body thường **dễ bảo trì hơn** guard dài.

## 6. Viết switch expression đầy đủ, không dùng `default`

Đây là lõi của bài:

```java
static String render(PaymentEvent event) {
    return switch (event) {
        case null -> "event:null";

        case Authorized(var paymentId, Money(var cents, var currencyCode))
                when cents >= 100_000 ->
                "approved:large:" + paymentId + ":" + cents
                        + " " + currencyCode;

        case Authorized(var paymentId, Money(var cents, var currencyCode)) ->
                "approved:" + paymentId + ":" + cents
                        + " " + currencyCode;

        case Authorized(var paymentId, var total) ->
                "approved:missing-total:" + paymentId;

        case Declined(var paymentId, var reasonCode) ->
                "declined:" + paymentId + ":" + reasonCode;

        case AnalystReview(var paymentId, var reviewQueue) ->
                "review:" + paymentId + ":" + reviewQueue;

        case FraudAlert(var paymentId, var riskScore)
                when riskScore >= 90 ->
                "fraud:critical:" + paymentId + ":" + riskScore;

        case FraudAlert(var paymentId, var riskScore) ->
                "fraud:hold:" + paymentId + ":" + riskScore;
    };
}
```

Tại sao compiler có thể chấp nhận switch expression này mà **không cần `default`**?

- `Authorized`: các case về `Authorized` cuối cùng có case tổng quát bao phủ toàn kiểu.
- `Declined`: có một case bao phủ cả subtype.
- `ReviewEvent` được chia thành `AnalystReview` và `FraudAlert`, và mỗi loại có case bao phủ.
- `FraudAlert` có case guard rủi ro cao và case còn lại không guard.
- `case null` xử lý selector null một cách tường minh. Dù exhaustiveness theo sealed hierarchy chỉ nói về instance khác null, chính sách null của hàm này cũng rõ ràng.

Không nên thay toàn bộ các case cuối bằng `default -> "unknown"` chỉ để tránh compiler báo thiếu subtype mới. Với sealed hierarchy cố ý đóng, **sự thiếu vắng `default` là một chủ đích thiết kế**: nếu sau này thêm direct subtype, compiler sẽ yêu cầu người duy trì xem xét hành vi.

### Tại sao cần phân biệt `null` ở hai vị trí?

- `render(null)`: selector bằng `null`, chạy `case null` → `"event:null"`.
- `render(new Authorized("P-102", null))`: selector là `Authorized` hợp lệ nhưng component `total` bằng `null`. Mẫu `Money(...)` không khớp; case `Authorized(var paymentId, var total)` xử lý → `"approved:missing-total:P-102"`.

Không thể dùng `case null` để tự động xử lý mọi record component bằng null.

## 7. Viết switch expression trả về một kiểu kết quả, không chỉ String

Với bài tập thực tế hơn, một switch expression có thể trả **giá trị domain có cấu trúc**:

```java
sealed interface Decision permits Screen, ReviewTicket {}

record Screen(String text) implements Decision {}

record ReviewTicket(String paymentId, int priority)
        implements Decision {}
```

Ở đây:

- `Screen`: thông điệp cần hiển thị.
- `ReviewTicket`: yêu cầu đưa vào hàng chờ xem xét, có mã giao dịch và mức ưu tiên.
- `Decision` cũng là sealed type, giúp code xử lý kết quả exhaustively.

Một phương thức ra quyết định:

```java
static Decision decide(PaymentEvent event) {
    Objects.requireNonNull(event, "event");

    return switch (event) {
        case Authorized(var paymentId, var total) -> {
            if (total == null) {
                yield new Screen(
                        "payment-data-missing:" + paymentId);
            }
            yield new Screen("receipt:" + paymentId);
        }

        case Declined(var paymentId, var reasonCode) ->
                new Screen("retry:" + paymentId + ":" + reasonCode);

        case AnalystReview(var paymentId, var reviewQueue) ->
                new ReviewTicket(paymentId, 50);

        case FraudAlert(var paymentId, var riskScore)
                when riskScore >= 90 -> {
            int priority = Math.min(100, riskScore);
            yield new ReviewTicket(paymentId, priority);
        }

        case FraudAlert(var paymentId, var riskScore) ->
                new ReviewTicket(paymentId, 60);
    };
}
```

Đây là một phương thức thuộc lớp có `import java.util.Objects;` và các kiểu đã khai báo; chương trình đầy đủ ở mục 9 chứa đủ các phần ấy.

### `yield` dùng khi nào?

Ở `case ... -> new Screen(...)`, biểu thức bên phải arrow tự cung cấp giá trị của switch expression. Khi một nhánh có **nhiều câu lệnh**, dùng block `{ ... }`; một lệnh `yield expression;` cung cấp giá trị của nhánh đó.

```java
case FraudAlert(var paymentId, var riskScore)
        when riskScore >= 90 -> {
    int priority = Math.min(100, riskScore);
    yield new ReviewTicket(paymentId, priority);
}
```

- `yield` trả một **giá trị từ switch expression**.
- `return` trong ngữ cảnh này là để trả giá trị từ **phương thức**, nằm bên ngoài hoặc bao quanh toàn biểu thức.
- `break` không dùng để “trả giá trị” của switch expression. `break` truyền thống có chức năng khác trong switch statement.
- Các case cùng switch phải tạo ra giá trị có kiểu phù hợp để suy luận kiểu kết quả (ở đây các record đều implements `Decision`).

### Hai kiểu null policy trong cùng một bài

`render(null)` trả chuỗi `"event:null"`. Trong khi đó, `decide(null)` **cố ý ném `NullPointerException`** nhờ `Objects.requireNonNull(event, "event")`. Sự khác nhau là **hợp đồng API**: render hiển thị trạng thái vắng đầu vào; decide chỉ nhận sự kiện thực.

Cả hai đều hợp lệ nếu được tài liệu hóa và kiểm thử rõ. Đừng thêm `case null` hoặc `Objects.requireNonNull` một cách máy móc mà không biết chính sách mong muốn.

## 8. Kết hợp switch thứ hai trên sealed result

Sau `decide`, caller có thể hiển thị loại `Decision`:

```java
static String decisionLabel(Decision decision) {
    return switch (decision) {
        case Screen(var text) ->
                "screen:" + text;
        case ReviewTicket(var paymentId, var priority) ->
                "ticket:" + paymentId + ":priority=" + priority;
    };
}
```

Hai case tương ứng với hai record lá trong sealed interface `Decision`, nên switch expression được compiler kiểm tra exhaustiveness. Đây là lợi ích của **tập kiểu có giới hạn ở cả đầu vào lẫn đầu ra**, nhưng đừng nhầm “kiểu đúng” với “kết quả nghiệp vụ đúng”: ưu tiên 60 hay 97 trong ví dụ vẫn là rule do người viết quy định.

Mô hình này hợp với các kịch bản “đọc event → quyết định UI/action”:

```text
PaymentEvent (sealed)
          │
          ▼ switch expression + guard
Decision (sealed)
          │
          ▼ switch expression
Chuỗi UI / dữ liệu gửi hệ thống tiếp theo
```

Trong ứng dụng thật, nếu việc tạo `ReviewTicket` có side effect như gửi message hoặc ghi database, hãy tách **quyết định thuần** ra khỏi **thực hiện side effect**, và cân nhắc transaction/outbox. Bài minh họa chỉ tạo một record kết quả, chưa thực sự ghi ticket.

## 9. Chương trình Java 21 hoàn chỉnh, chạy độc lập

Lưu toàn bộ chương trình thành **`SealedSwitchPractice.java`**. Đây là ví dụ dùng duy nhất JDK, không cần Maven/JUnit để chạy. Những phương thức `check` và `expectNpe` cung cấp assertion nhằm báo lỗi khi output hoặc null policy không đúng.

```java
import java.util.Objects;
import java.util.function.Supplier;

public class SealedSwitchPractice {
    sealed interface PaymentEvent
            permits Authorized, Declined, ReviewEvent {
        String paymentId();
    }

    sealed interface ReviewEvent extends PaymentEvent
            permits AnalystReview, FraudAlert {}

    record Money(long cents, String currencyCode) {}
    record Authorized(String paymentId, Money total)
            implements PaymentEvent {}
    record Declined(String paymentId, String reasonCode)
            implements PaymentEvent {}
    record AnalystReview(String paymentId, String reviewQueue)
            implements ReviewEvent {}
    record FraudAlert(String paymentId, int riskScore)
            implements ReviewEvent {}

    sealed interface Decision permits Screen, ReviewTicket {}
    record Screen(String text) implements Decision {}
    record ReviewTicket(String paymentId, int priority)
            implements Decision {}

    static String render(PaymentEvent event) {
        return switch (event) {
            case null -> "event:null";

            case Authorized(var paymentId, Money(var cents, var currencyCode))
                    when cents >= 100_000 ->
                    "approved:large:" + paymentId + ":"
                            + cents + " " + currencyCode;

            case Authorized(var paymentId, Money(var cents, var currencyCode)) ->
                    "approved:" + paymentId + ":"
                            + cents + " " + currencyCode;

            case Authorized(var paymentId, var total) ->
                    "approved:missing-total:" + paymentId;

            case Declined(var paymentId, var reasonCode) ->
                    "declined:" + paymentId + ":" + reasonCode;

            case AnalystReview(var paymentId, var reviewQueue) ->
                    "review:" + paymentId + ":" + reviewQueue;

            case FraudAlert(var paymentId, var riskScore)
                    when riskScore >= 90 ->
                    "fraud:critical:" + paymentId + ":" + riskScore;

            case FraudAlert(var paymentId, var riskScore) ->
                    "fraud:hold:" + paymentId + ":" + riskScore;
        };
    }

    static String group(PaymentEvent event) {
        return switch (event) {
            case Authorized authorized -> "completed";
            case Declined declined -> "failed";
            case ReviewEvent review -> "manual";
        };
    }

    static Decision decide(PaymentEvent event) {
        Objects.requireNonNull(event, "event");

        return switch (event) {
            case Authorized(var paymentId, var total) -> {
                if (total == null) {
                    yield new Screen("payment-data-missing:" + paymentId);
                }
                yield new Screen("receipt:" + paymentId);
            }

            case Declined(var paymentId, var reasonCode) ->
                    new Screen("retry:" + paymentId + ":" + reasonCode);

            case AnalystReview(var paymentId, var reviewQueue) ->
                    new ReviewTicket(paymentId, 50);

            case FraudAlert(var paymentId, var riskScore)
                    when riskScore >= 90 -> {
                int priority = Math.min(100, riskScore);
                yield new ReviewTicket(paymentId, priority);
            }

            case FraudAlert(var paymentId, var riskScore) ->
                    new ReviewTicket(paymentId, 60);
        };
    }

    static String decisionLabel(Decision decision) {
        return switch (decision) {
            case Screen(var text) -> "screen:" + text;
            case ReviewTicket(var paymentId, var priority) ->
                    "ticket:" + paymentId + ":priority=" + priority;
        };
    }

    static int passed = 0;

    static void check(String name, String expected, String actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(name + " expected=" + expected
                    + " actual=" + actual);
        }
        passed++;
        System.out.println("PASS " + name + "=" + actual);
    }

    static void expectNpe(String name, Supplier<String> call) {
        try {
            call.get();
            throw new AssertionError(name
                    + " should throw NullPointerException");
        } catch (NullPointerException expected) {
            passed++;
            System.out.println("PASS " + name + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        var high = new Authorized(
                "P-100", new Money(125_000, "USD"));
        var standard = new Authorized(
                "P-101", new Money(2_500, "USD"));
        var withoutTotal = new Authorized("P-102", null);
        var declined = new Declined("P-103", "expired");
        var analyst = new AnalystReview("P-104", "risk");
        var critical = new FraudAlert("P-105", 97);
        var lowRisk = new FraudAlert("P-106", 45);

        check("null-selector", "event:null", render(null));
        check("high-amount",
                "approved:large:P-100:125000 USD", render(high));
        check("standard-amount",
                "approved:P-101:2500 USD", render(standard));
        check("missing-record",
                "approved:missing-total:P-102", render(withoutTotal));
        check("declined",
                "declined:P-103:expired", render(declined));
        check("analyst",
                "review:P-104:risk", render(analyst));
        check("critical",
                "fraud:critical:P-105:97", render(critical));
        check("hold",
                "fraud:hold:P-106:45", render(lowRisk));

        check("group-authorized", "completed", group(high));
        check("group-declined", "failed", group(declined));
        check("group-review", "manual", group(analyst));
        check("group-fraud", "manual", group(critical));
        expectNpe("group-null", () -> group(null));

        check("decision-authorized", "screen:receipt:P-100",
                decisionLabel(decide(high)));
        check("decision-missing", "screen:payment-data-missing:P-102",
                decisionLabel(decide(withoutTotal)));
        check("decision-declined", "screen:retry:P-103:expired",
                decisionLabel(decide(declined)));
        check("decision-review", "ticket:P-104:priority=50",
                decisionLabel(decide(analyst)));
        check("decision-critical", "ticket:P-105:priority=97",
                decisionLabel(decide(critical)));
        check("decision-hold", "ticket:P-106:priority=60",
                decisionLabel(decide(lowRisk)));
        expectNpe("decision-null",
                () -> decisionLabel(decide(null)));

        System.out.println("TOTAL=" + passed);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 21 -encoding UTF-8 SealedSwitchPractice.java
java SealedSwitchPractice
```

**Đầu ra chính xác khi toàn bộ 20 assertion đạt:**

```text
PASS null-selector=event:null
PASS high-amount=approved:large:P-100:125000 USD
PASS standard-amount=approved:P-101:2500 USD
PASS missing-record=approved:missing-total:P-102
PASS declined=declined:P-103:expired
PASS analyst=review:P-104:risk
PASS critical=fraud:critical:P-105:97
PASS hold=fraud:hold:P-106:45
PASS group-authorized=completed
PASS group-declined=failed
PASS group-review=manual
PASS group-fraud=manual
PASS group-null=NullPointerException
PASS decision-authorized=screen:receipt:P-100
PASS decision-missing=screen:payment-data-missing:P-102
PASS decision-declined=screen:retry:P-103:expired
PASS decision-review=ticket:P-104:priority=50
PASS decision-critical=ticket:P-105:priority=97
PASS decision-hold=ticket:P-106:priority=60
PASS decision-null=NullPointerException
TOTAL=20
```

Mẫu đã được chạy và đối chiếu kết quả ở chế độ compiler `--release=21`. Chương trình in `TOTAL=20` chỉ sau khi mọi phép `check(...)` và `expectNpe(...)` thành công. Nếu expected sai, `AssertionError` làm chương trình dừng, vì vậy không thể chỉ nhìn thấy một vài dòng `PASS` rồi cho rằng toàn bộ bài test thành công.

**Môi trường chạy:** `--release 21` kiểm tra mức tương thích ngôn ngữ/API và class file khi biên dịch; nó không tự có nghĩa JVM đang thực thi đúng phiên bản 21. Khi dự án triển khai trên Java 21, nên chạy các test bằng runtime Java 21 thật trong CI.

## 10. Giải thích lần lượt các nhóm test đã chạy

### 10.1. `render`: exhaustive + null + record pattern

| Test | Input đại diện | Expected | Nhánh cần kiểm chứng |
| --- | --- | --- | --- |
| `null-selector` | `null` | `event:null` | `case null` |
| `high-amount` | `Authorized(..., Money(125000, USD))` | `approved:large:...` | Authorized + Money + `when` đạt |
| `standard-amount` | `Authorized(..., Money(2500, USD))` | `approved:...` | Authorized + Money, guard không đạt |
| `missing-record` | `Authorized(..., null)` | `approved:missing-total:...` | Authorized fallback |
| `declined` | `Declined` | `declined:...` | Subtype trực tiếp |
| `analyst` | `AnalystReview` | `review:...` | Subtype gián tiếp qua ReviewEvent |
| `critical` | `FraudAlert(score=97)` | `fraud:critical:...` | Guard `score >= 90` |
| `hold` | `FraudAlert(score=45)` | `fraud:hold:...` | FraudAlert không guard |

Dù `PaymentEvent` chỉ permits trực tiếp ba nhánh, switch chi tiết có **bốn record leaves**, và nhờ các case guard/fallback nó có nhiều nhãn hơn số subtype.

Điều này hoàn toàn bình thường: một subtype có thể có **nhiều case** miễn là không case nào bị dominated và toàn bộ pattern set bao phủ những giá trị có thể gặp.

### 10.2. `group`: tổng quát hóa một nhánh trung gian

`group(analyst)` và `group(critical)` đều trả `manual`. Chúng chứng minh một case kiểu `ReviewEvent` bao phủ các subtype của nhánh đó. `group(null)` lại **ném `NullPointerException`** vì không có `case null`.

### 10.3. `decide`: trả typed result, dùng `yield`

- Authorized có `Money` → `Screen("receipt:P-100")`.
- Authorized có `total == null` → `Screen("payment-data-missing:P-102")`.
- Declined → `Screen("retry:P-103:expired")`.
- AnalystReview → `ReviewTicket("P-104", 50)`.
- FraudAlert mức 97 → `ReviewTicket("P-105", 97)`, được tạo trong block có `yield`.
- FraudAlert mức 45 → `ReviewTicket("P-106", 60)`.
- `decide(null)` → NPE ở `Objects.requireNonNull` trước khi switch được đánh giá.

Chức năng `decisionLabel` tiếp tục dùng switch expression trên sealed type `Decision`, giúp phân biệt màn hình hiển thị với ticket một cách typed.

**Ranh giới nghiệp vụ:** điểm `riskScore` và mức ưu tiên đang là quy tắc minh họa. Điểm số không được validate thuộc [0,100] trong record; production phải định nghĩa và kiểm tra ranh giới, không suy luận rằng mọi `FraudAlert` đều mang score hợp lệ chỉ vì record đã khai báo `int`.

## 11. Bài kiểm tra lỗi compile: thiếu nhánh exhaustive

Để hiểu vì sao sealed hierarchy hữu ích, hãy **cố tình** viết switch expression thiếu một subtype.

Ví dụ Java 21 **cố ý không biên dịch**:

```java
sealed interface Pay permits AcceptedPayment, ReviewPayment {}

record AcceptedPayment() implements Pay {}

sealed interface ReviewPayment extends Pay
        permits NeedsAnalyst, NeedsFraud {}

record NeedsAnalyst() implements ReviewPayment {}
record NeedsFraud() implements ReviewPayment {}

class MissingCase {
    static String check(Pay x) {
        return switch (x) {
            case AcceptedPayment p -> "ok";
            case NeedsAnalyst p -> "analyst";
        };
    }
}
```

Vì `NeedsFraud` vẫn là một subtype hợp lệ của `Pay` qua `ReviewPayment`, switch chưa exhaustive. Compiler Java 21 báo một diagnostic dạng:

```text
the switch expression does not cover all possible input values
```

**Mục đích của thí nghiệm:** thấy rằng compiler không bỏ qua subtype gián tiếp. Nếu một sealed node mở tiếp một sealed branch, compiler vẫn có thể kiểm tra độ bao phủ qua nhánh đó.

Có hai cách sửa hợp lệ tùy yêu cầu:
- Thêm `case NeedsFraud p -> "fraud";` để xử lý riêng.
- Hoặc thay việc xử lý các kiểu review cụ thể bằng `case ReviewPayment p -> "review";` nếu mọi review có thể dùng cùng hành vi.

Không nên thêm `default -> "other"` chỉ để bỏ qua việc chưa quyết định xử lý một subtype mà domain đã định nghĩa rõ. `default` có thể hữu ích ở API mở/đầu vào thật sự cần fallback nhưng với sealed hierarchy đóng, nó làm yếu tín hiệu review khi kiểu mới xuất hiện.

## 12. Bài kiểm tra lỗi compile: case bị dominated

Pattern switch còn có quy tắc về **dominance**. Ví dụ sau **cố ý không biên dịch** trên Java 21:

```java
sealed interface Pay permits AcceptedPayment, ReviewPayment {}

record AcceptedPayment() implements Pay {}

sealed interface ReviewPayment extends Pay
        permits NeedsAnalyst, NeedsFraud {}

record NeedsAnalyst() implements ReviewPayment {}
record NeedsFraud() implements ReviewPayment {}

class DominatedCase {
    static String check(Pay x) {
        return switch (x) {
            case AcceptedPayment p -> "ok";
            case ReviewPayment p -> "all-reviews";
            case NeedsFraud p -> "fraud";
        };
    }
}
```

`case ReviewPayment p` đứng trước đã khớp mọi `NeedsFraud`. Vì vậy `case NeedsFraud p` phía sau là **unreachable theo quan hệ pattern** và compiler báo dạng:

```text
this case label is dominated by a preceding case label
```

**Cách sửa theo mục tiêu nghiệp vụ:**

```java
return switch (x) {
    case AcceptedPayment p -> "ok";
    case NeedsFraud p -> "fraud";
    case ReviewPayment p -> "other-review";
};
```

Đây là đoạn minh họa bên trong một phương thức có `Pay x`. Mẫu **cụ thể** nằm trước mẫu **rộng**. Khi `ReviewPayment` là sealed với đúng `NeedsAnalyst` và `NeedsFraud`, case rộng bao phủ cả các giá trị review còn lại.

Nhớ rằng dominance là lỗi **compile-time**: không có stdout runtime để kiểm thử cho một đoạn chưa biên dịch được. Nên dùng một ví dụ cực nhỏ và đọc thông báo compiler, thay vì chạy cả hệ thống rồi suy đoán.

## 13. Switch expression khác switch statement ở điểm nào?

### 13.1. Switch expression tạo một giá trị

```java
String message = switch (event) {
    case Authorized approved -> "approved";
    case Declined declined -> "declined";
    case ReviewEvent review -> "review";
};
```

Đây là đoạn minh họa sử dụng biến `PaymentEvent event` và các kiểu cùng mô hình, cần đặt trong phạm vi hợp lệ. Các nhánh đều cung cấp kết quả, và switch expression phải exhaustive.

### 13.2. Switch statement thực thi câu lệnh

```java
switch (event) {
    case Authorized approved -> System.out.println("approved");
    case Declined declined -> System.out.println("declined");
    case ReviewEvent review -> System.out.println("review");
}
```

Đây là switch **statement** với arrow cases. Nó phù hợp khi mục tiêu là hành động và side effects, thay vì lấy một giá trị. Enhanced switch statement sử dụng pattern trong Java 21 cũng phải đáp ứng những yêu cầu exhaustiveness của Java, khác với cách nghĩ đơn giản “statement thiếu case vẫn luôn hợp lệ”.

### 13.3. `yield` khác `return` và `break`

| Từ khóa/cú pháp | Vai trò chính | Trong bài |
| --- | --- | --- |
| `case Type t -> expression` | Tạo giá trị nhánh không cần block | `case Declined(...) -> new Screen(...)` |
| `yield expression;` | Trả giá trị của **switch expression** từ một block | Tạo `ReviewTicket` sau khi tính `priority` |
| `return expression;` | Trả về từ **phương thức** | `return switch (event) { ... };` |
| `break;` | Điều khiển luồng trong switch statement/loop, không dùng làm giá trị trả của switch expression | Không thay `yield` |

Một lỗi thường gặp khi chuyển từ switch statement cũ sang expression là giữ lại `break` như cách “thoát case” rồi mong switch trả giá trị. Với expression, cần một biểu thức hoặc `yield` trên các đường hoàn tất bình thường của block.

## 14. Null policy, record component và guard: ba điều phải test khác nhau

**Selector null:** `switch (event)` nhận `event == null`. Nếu có `case null` như trong `render`, case đó được chọn. Nếu không, như `group`, switch trên tham chiếu null thông thường ném `NullPointerException`. `default` không tự là null handler.

**Record component null:** `new Authorized("P-102", null)` là một object `Authorized`, nên không chạy `case null`. Mẫu `Money(...)` không khớp component null; case `Authorized(var paymentId, var total)` vẫn khớp và `total` nhận null. Đây là lý do testcase `missing-record` quan trọng.

**Guard false:** `FraudAlert("P-106",45)` vẫn là kiểu FraudAlert, record pattern khớp nhưng `when riskScore >= 90` là false. Java chuyển tới case `FraudAlert` không guard. Không được nhầm guard false với selector null hoặc subtype sai.

### Khi guard tự ném exception

Nếu một guard gọi phương thức không an toàn trên component có thể null, exception phát sinh trong lúc đánh giá `when` sẽ lan truyền theo quy tắc biểu thức, không phải một lần matching false. Nên dùng toán tử `&&` short-circuit và điều kiện theo đúng thứ tự:

```java
case Authorized(var id, Money(var cents, var currencyCode))
        when currencyCode != null && !currencyCode.isBlank() ->
        "valid-currency:" + id;
```

Đây là nhãn `case` minh họa. Nó chỉ kiểm tra chuỗi không trống; trong production, kiểm tra mã tiền tệ có được hỗ trợ hay không là vấn đề domain riêng.

### Khi accessor của record ném lỗi

Record pattern truy xuất component bằng accessor; một accessor tùy chỉnh có thể ném exception. Trong Java 21, lỗi từ accessor khi pattern matching được bọc bằng `MatchException` với `getCause()` chứa lỗi gốc. Điều này khác “không khớp do component null”. Thiết kế record đơn giản, kiểm tra dữ liệu khi xây dựng và tách I/O khỏi accessor sẽ làm hành vi switch dễ dự đoán.

## 15. Bộ test hồi quy nên bao phủ những đường nào?

Chương trình đầy đủ chứa 20 assertion, chia thành ba nhóm. Khi mở rộng bài tập trong hệ thống thật, có thể dùng ma trận:

| Loại test | Cách dựng dữ liệu | Assertion nên có |
| --- | --- | --- |
| Một direct subtype | `Declined("P-103","expired")` | `render` trả đúng chuỗi |
| Một indirect subtype | `AnalystReview("P-104","risk")` | `group` trả `manual` |
| Một subtype gián tiếp khác | `FraudAlert("P-105",97)` | `render` và `group` đúng |
| Guard true | 100.000 cent trở lên | Nhánh large được chọn |
| Guard false | Dưới 100.000 cent | Nhánh standard được chọn |
| Guard ranh giới | 99.999 và 100.000 cent | Phân biệt trước/sau ngưỡng chính xác |
| Nested record present | `Authorized(..., Money(...))` | Phân rã đúng các component |
| Nested record null | `Authorized(..., null)` | Nhánh fallback, không nhầm selector null |
| Selector null có case | `render(null)` | `event:null` |
| Selector null không case | `group(null)` | `NullPointerException` |
| Switch expression trả record | `decide(critical)` | `ReviewTicket` có priority như mong đợi |
| Block có `yield` | `FraudAlert(score=97)` | Priority 97, không rơi vào fallback |
| Type-specific fallback | `FraudAlert(score=45)` | Priority 60 |
| Compiler completeness | Cố xóa case thuộc subtype | Lỗi thiếu exhaustive |
| Compiler dominance | Đặt case `ReviewEvent` trước `FraudAlert` | Lỗi dominated case |
| API evolution | Thêm direct permitted subtype mới | Recompile và review toàn bộ exhaustive switch |

Hai mục cuối thuộc **compile tests**, không phải runtime test; chúng có thể được xác minh bằng một đoạn nguồn nhỏ cố ý không biên dịch. Đừng ghi nhận chúng như “unit test runtime PASS” chỉ vì lệnh `javac` trả lỗi như dự kiến.

### Chú ý phép thử ranh giới

Trong chương trình đầy đủ, ca high dùng 125.000 và ca standard dùng 2.500 nên hai đường guard đã được kiểm tra. Khi đưa vào production, nên thêm **99.999 và 100.000** để phát hiện lỗi thay `>=` thành `>` hoặc đổi ngưỡng. Dùng dữ liệu biên giúp test có ý nghĩa hơn việc chỉ thêm nhiều giá trị xa ngưỡng.

## 16. Dùng JUnit 5 cho các phép thử độc lập

Nếu dự án có JUnit 5, thay helper `check` bằng `assertEquals` và `assertThrows`. Ví dụ dưới đây là **lớp test minh họa** cần JUnit 5 trên test classpath và nằm cùng package với `SealedSwitchPractice` (các nested types/methods ví dụ có phạm vi package-private):

```java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SealedSwitchJUnitTest {
    @Test
    void sealedSwitchCoversReviewSubtypes() {
        var analyst =
                new SealedSwitchPractice.AnalystReview("P-1", "risk");
        var fraud = new SealedSwitchPractice.FraudAlert("P-2", 97);

        assertAll(
                () -> assertEquals("manual",
                        SealedSwitchPractice.group(analyst)),
                () -> assertEquals("manual",
                        SealedSwitchPractice.group(fraud)),
                () -> assertEquals("fraud:critical:P-2:97",
                        SealedSwitchPractice.render(fraud))
        );
    }

    @Test
    void nestedRecordNullAndNullSelectorAreDifferent() {
        var missing =
                new SealedSwitchPractice.Authorized("P-3", null);

        assertAll(
                () -> assertEquals("approved:missing-total:P-3",
                        SealedSwitchPractice.render(missing)),
                () -> assertEquals("event:null",
                        SealedSwitchPractice.render(null))
        );
    }

    @Test
    void guardBoundaryIsInclusive() {
        var below = new SealedSwitchPractice.Authorized(
                "P-4", new SealedSwitchPractice.Money(99_999, "USD"));
        var at = new SealedSwitchPractice.Authorized(
                "P-5", new SealedSwitchPractice.Money(100_000, "USD"));

        assertAll(
                () -> assertEquals("approved:P-4:99999 USD",
                        SealedSwitchPractice.render(below)),
                () -> assertEquals("approved:large:P-5:100000 USD",
                        SealedSwitchPractice.render(at))
        );
    }

    @Test
    void groupWithoutNullCaseRejectsNull() {
        assertThrows(NullPointerException.class,
                () -> SealedSwitchPractice.group(null));
    }

    @Test
    void decisionCanBeComparedStructurally() {
        var fraud = new SealedSwitchPractice.FraudAlert("P-6", 95);
        assertEquals(
                new SealedSwitchPractice.ReviewTicket("P-6", 95),
                SealedSwitchPractice.decide(fraud));
    }
}
```

Chỉ khi JUnit được cài đặt trong dự án mới có thể chạy lớp test này. Ngược lại, chương trình `SealedSwitchPractice.java` ở mục 9 là ví dụ độc lập chỉ dùng thư viện chuẩn Java.

**Điểm đáng học:** dùng `assertEquals` trực tiếp trên records `ReviewTicket` là hợp lý, vì record tạo `equals` dựa trên component. Không cần chuyển record thành chuỗi chỉ để kiểm tra hai giá trị có cùng nội dung.

## 17. Khi thêm subtype mới, đừng dùng `default` để giấu lỗi thiết kế

Một sealed hierarchy có thể được mở rộng bằng cách sửa chính cấu trúc `permits`. Giả sử cần thêm một loại `Chargeback` trực tiếp thuộc `PaymentEvent`.

Ví dụ minh họa việc thay khai báo (không được ghép nguyên vẹn với `permits` cũ nếu chưa sửa định nghĩa):

```java
sealed interface PaymentEvent
        permits Authorized, Declined, ReviewEvent, Chargeback {
    String paymentId();
}

record Chargeback(String paymentId, String disputeId)
        implements PaymentEvent {}
```

Khi biên dịch lại `render` hoặc `decide` mà chưa có case `Chargeback`, compiler có thể báo thiếu exhaustive. Điều đó **đúng với mục tiêu của tập kiểu đóng**: yêu cầu người duy trì xác định hiển thị và hành động cho chargeback thay vì âm thầm gửi chúng vào một nhánh `"unknown"`.

Với **separate compilation** (client được build với phiên bản hierarchy cũ nhưng runtime nạp thư viện mới), một switch đã được biên dịch exhaustive theo tập cũ có thể ném `MatchException` khi nhận subtype chưa biết. Đây là một rủi ro tương thích cần kiểm thử; không được kết luận tất cả client cũ đều chạy đúng vì class mới vẫn implements cùng root.

Nếu mở một nhánh `non-sealed`, các subtype có thể được bên ngoài bổ sung mà không cần sửa `permits` của sealed root. Điều này có ích cho plugin nhưng khi đó phải thiết kế case tổng quát tương ứng, và **không thể giả định tập concrete subtype là đóng**.

### Không phải lúc nào switch exhaustive cũng cần record pattern sâu

Nếu chỉ phân nhóm, `case ReviewEvent review` thích hợp hơn hai case riêng cho AnalystReview và FraudAlert. Nếu cần dùng đúng component, `case FraudAlert(var id, var score)` cung cấp dữ liệu tại case. Nếu đang điều phối tới handler/service khác, `case FraudAlert alert -> fraudHandler.handle(alert)` giữ nguyên object và đôi khi dễ bảo trì hơn.

Mức phân rã nên do **nhu cầu xử lý** quyết định, không phải do cú pháp record pattern cho phép lấy tất cả fields.

## 18. Các lỗi thường gặp khi làm bài

### 18.1. Chỉ xử lý hai direct records, quên sealed subtype trung gian

`PaymentEvent` không chỉ có `Authorized` và `Declined`; nó còn có `ReviewEvent`. Nếu switch thiếu case cho ReviewEvent hoặc cả các con của nó, compiler có thể báo không exhaustive.

### 18.2. Chỉ liệt kê một subtype của ReviewEvent

`AnalystReview` không bao phủ `FraudAlert`. Cần case FraudAlert hoặc một case `ReviewEvent` bao quát đúng nghiệp vụ.

### 18.3. Dùng `default` để làm mã compile nhanh

Với hierarchy đóng, cách này có thể che việc thêm subtype mới. Nếu thực sự cần fallback, tài liệu hóa rõ vì sao và test hành vi với subtype mới.

### 18.4. Đặt case rộng trước case hẹp

`case ReviewEvent review` đứng trước `case FraudAlert alert` làm case phía sau bị dominated; tương tự `case Authorized(var id, var money)` đứng trước mẫu `Authorized(..., Money(...))`.

### 18.5. Quên nhánh khi guard false

`case FraudAlert(var id, var score) when score >= 90` không bao phủ FraudAlert có score nhỏ hơn; phải có case khác cho nhóm còn lại nếu không có đường tổng quát hợp lệ.

### 18.6. Dùng `case null` để xử lý null bên trong record

`case null` chỉ khớp selector null. Component `total == null` là trường hợp của record pattern và fallback trên `Authorized`.

### 18.7. Cho rằng `record` tự validate dữ liệu

`Money(-1, null)` vẫn có thể được tạo trong ví dụ vì record không khai báo validation. Tên biến `cents` và sealed hierarchy không tự bảo đảm giá trị hợp lệ.

### 18.8. Nhầm ý nghĩa của `yield`

`yield` trong block case trả giá trị của switch expression, không phải thoát toàn bộ method giống `return`.

### 18.9. Nghĩ compile pass là behavior đúng

Compiler bảo đảm loại pattern hợp lệ và exhaustiveness theo typing; không xác nhận ngưỡng 100.000, lý do từ chối hay priority 60 đúng nghiệp vụ. Cần regression tests.

### 18.10. Chỉ test một subtype và bỏ qua dữ liệu biên

Có một phép test cho `Authorized` không đủ. Cần kiểm tra guard true/false, null nested record, các subtype gián tiếp, null selector và nhánh result.

### 18.11. Viết code Java 21 rồi compile dưới `--release 17`

Sealed classes và record classes đã có trong Java 17, nhưng record pattern cùng pattern matching for switch theo cú pháp bài này chính thức Java 21. Dùng JDK hỗ trợ `--release 21`, không lạm dụng các preview flags lịch sử.

### 18.12. Dùng pattern matching để thay thế kiểm tra quyền hoặc I/O

Switch expression chỉ là cơ chế phân nhánh theo kiểu/điều kiện. Xác thực người gửi, lưu giao dịch, ghi review ticket, retry và bảo mật phải được thiết kế ở tầng tương ứng. Một `Decision` trả record không tự chứng minh side effect đã xảy ra.

## 19. Bài tập tự luyện (có đáp án)

**Bài 1 — Nhận diện subtype trực tiếp.** Hỏi `PaymentEvent permits Authorized, Declined, ReviewEvent` có bao nhiêu direct permitted subtypes? `FraudAlert` có phải direct subtype không?

**Đáp án:** ba. FraudAlert là subtype gián tiếp qua ReviewEvent.

**Bài 2 — Exhaustiveness theo nhánh trung gian.** Có thể viết `case Authorized`, `case Declined`, `case ReviewEvent` mà không liệt kê FraudAlert/AnalystReview không?

**Đáp án:** có, nếu muốn xử lý cả nhóm review cùng một nhánh. Case ReviewEvent bao phủ cả hai record con của nó.

**Bài 3 — Guard false.** `FraudAlert("P",45)` có vào `when riskScore >= 90` không? Điều gì xảy ra sau đó?

**Đáp án:** không; case FraudAlert không guard ở phía sau được chọn và trả `fraud:hold:P:45` theo `render`.

**Bài 4 — Giá trị biên.** Với `cents == 100_000`, chuỗi của Authorized có chữ `large` không? Vì sao?

**Đáp án:** có, vì guard dùng toán tử `>=` chứ không phải `>`.

**Bài 5 — Record con null.** `render(new Authorized("P",null))` có chạy `case null` không?

**Đáp án:** không. Selector là Authorized không null. Mẫu Money lồng không khớp, case Authorized tổng quát trả `approved:missing-total:P`.

**Bài 6 — Null policy.** Tại sao `render(null)` và `group(null)` không giống nhau?

**Đáp án:** render có `case null` nên trả `event:null`; group không có, nên switch trên null ném NullPointerException.

**Bài 7 — Thiếu case.** Nếu xóa nhánh FraudAlert không guard và chỉ giữ FraudAlert có guard score >=90, switch có đủ exhaustive không?

**Đáp án:** không, vì FraudAlert có score thấp hơn vẫn có thể xuất hiện. Phải thêm nhánh không guard hoặc một mẫu bao phủ khác.

**Bài 8 — Dominance.** Đặt `case ReviewEvent review` trước `case AnalystReview analyst` trong cùng switch có hợp lệ không?

**Đáp án:** không; AnalystReview đã bị mẫu ReviewEvent rộng hơn khớp trước, nên case cụ thể phía sau bị dominated.

**Bài 9 — `yield`.** Tại sao case FraudAlert critical trong `decide` dùng `yield` thay vì `break`?

**Đáp án:** đó là block của switch expression cần tạo một giá trị kiểu Decision. `yield new ReviewTicket(...)` cung cấp giá trị, còn `break` không cung cấp giá trị switch expression.

**Bài 10 — Result typed.** Vì sao `ReviewTicket("P",95)` là một giá trị tốt để dùng với `assertEquals`?

**Đáp án:** đó là record, có `equals` theo component, nên có thể so sánh cấu trúc mà không cần chuyển thành String.

**Bài 11 — API evolution.** Nếu thêm direct subtype Chargeback vào `PaymentEvent`, switch hiện tại có cần cập nhật không?

**Đáp án:** các switch exhaustive không có case mới hoặc fallback hợp lệ có thể fail khi recompile. Phải xác định semantics cho Chargeback, cập nhật test/tài liệu và xem xét client binary cũ.

**Bài 12 — Chọn mức pattern.** Nếu phương thức chỉ cần biết có phải nhóm review hay không, viết `case ReviewEvent review` hay hai record patterns con?

**Đáp án:** case ReviewEvent là đủ và thường rõ hơn. Chỉ phân rã record con nếu thật sự cần dữ liệu riêng của subtype.

**Bài 13 — Validation.** `new Money(-100, null)` có bị compiler từ chối vì giá trị không hợp lệ không?

**Đáp án:** không. Các kiểu `long`/`String` hợp lệ về cú pháp; cần constructor/factory validation nếu domain yêu cầu amount không âm và currencyCode hợp lệ.

**Bài 14 — Cải tiến.** Viết thêm hai assertion cho `render` với `Money(99_999,"USD")` và `Money(100_000,"USD")`. Nên trả gì?

**Đáp án:** với paymentId tương ứng `P-4` và `P-5`: `approved:P-4:99999 USD` và `approved:large:P-5:100000 USD`. Các assertion này bảo vệ ranh giới khi ai đó vô tình thay `>=` thành `>`.

## 20. Checklist hoàn thành bài thực hành

- [ ] Xác định rõ sealed root và **tất cả direct permitted subtypes**.
- [ ] Nếu có sealed subtype trung gian, xét các con của nó hoặc dùng case rộng cho cả nhánh.
- [ ] Tách record dữ liệu khỏi hierarchy nếu nó không biểu thị một biến thể của sealed root.
- [ ] Mỗi `switch expression` có kiểu kết quả rõ và mọi đường chạy hợp lệ đều cung cấp giá trị.
- [ ] Mẫu hẹp và guard phải đứng trước mẫu rộng không guard để tránh dominance.
- [ ] Nếu dùng record pattern lồng, có đường xử lý khi record con bằng null nếu domain cho phép.
- [ ] Chính sách selector null được xác định riêng: `case null` hoặc NPE theo hợp đồng.
- [ ] Với block nhiều statement, dùng `yield` để tạo giá trị từ switch expression.
- [ ] Không thêm `default` chỉ để lấp một lỗ exhaustive chưa giải quyết theo domain.
- [ ] Kiểm thử ít nhất mỗi subtype, guard true/false, ranh giới, null, và result.
- [ ] Phân biệt code runnable với ví dụ cố ý tạo compile error.
- [ ] Biên dịch với `javac --release 21` và test bằng runtime đích.
- [ ] Nếu hierarchy thay đổi, cập nhật handler, tests, tài liệu và kiểm tra compatibility.

**Kết luận:** Viết switch expression trên sealed type là bài toán **thiết kế miền kiểu + lựa chọn độ chi tiết pattern + hợp đồng null/guard + kiểm chứng exhaustive**. Giá trị lớn nhất không phải tiết kiệm vài dòng `if`, mà là để compiler cùng các regression tests giúp người duy trì nhìn thấy khi một biến thể mới chưa có cách xử lý.

**Tài liệu tham khảo chính thức:**
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409)
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification 21 — Switch Expressions (`15.28)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java Language Specification 21 — Patterns (`14.30)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30)
