# Trộn logic nghiệp vụ vào guard: lỗi thường gặp trong Java Pattern Matching

Khi dùng **pattern matching cho `switch`**, Java cho phép đặt một biểu thức Boolean sau từ khóa **`when`** để kiểm tra điều kiện bổ sung ngay tại nhánh `case`. Đây là tính năng hữu ích, nhưng cũng dễ dẫn đến lỗi thiết kế: **đưa quá nhiều logic nghiệp vụ, đặc biệt là thao tác có tác dụng phụ (side effect), vào guard**. Kết quả là một nhánh trông giống phép kiểm tra đơn giản lại có thể thay đổi dữ liệu, gọi dịch vụ bên ngoài, tạo giao dịch hoặc ném ngoại lệ khó theo dõi.

Bài học thuộc **Java Core Pattern Matching → Lỗi thường gặp**. Mục tiêu là hiểu chính xác `when` hoạt động ra sao, phân biệt **điều kiện nghiệp vụ thuần túy** với **hành động nghiệp vụ**, biết khi nào nên dùng helper predicate, khi nào nên tách validation và khi nào nên chuyển nghiệp vụ ra khỏi phần guard để code rõ ràng và dễ kiểm thử.

**Phạm vi phiên bản:** Pattern matching for `switch` được hoàn thiện trong **Java 21** (JEP 441), record patterns cũng được hoàn thiện trong Java 21 (JEP 440). Các ví dụ đầy đủ chạy với **JDK 21 trở lên**, không cần bật preview.

## 1. Guard `when` có nhiệm vụ gì?

Một `case` có pattern kiểm tra kiểu hoặc cấu trúc của selector. **Guard** kiểm tra thêm một điều kiện sau khi pattern đã khớp:

~~~java
// Trích đoạn Java 21+; 'value' là Object đã được khai báo.
String result = switch (value) {
    case Integer number when number > 0 -> "Positive: " + number;
    case Integer number -> "Non-positive: " + number;
    case null -> "Missing";
    default -> "Other type";
};
~~~

Cách đọc từ trên xuống:

1. Nếu `value` là một `Integer` khác `null`, Java ràng buộc nó vào pattern variable `number`.
2. Chỉ sau khi type pattern **khớp**, Java mới kiểm tra guard `number > 0`.
3. Nếu guard đúng, chọn nhánh `"Positive"`. Nếu guard sai, **chưa chọn nhánh**; Java tiếp tục xét những case thích hợp phía sau.
4. Vì thế, `Integer.valueOf(0)` và số âm sẽ được nhánh `case Integer number` không guard xử lý.
5. `case null` xử lý selector `null`; `default` nhận những kiểu còn lại.

Guard trả về **`boolean`**. Nó không phải một khối xử lý sự kiện, không phải transaction boundary và không tự quản lý retry hay rollback.

### Có được phép gọi phương thức trong guard không?

Có. Cú pháp sau **hợp lệ** nếu `isEligible(...)` trả về `boolean`:

~~~java
// Trích đoạn minh họa: isEligible là một phương thức kiểm tra thuần túy.
case OrderSubmitted(var orderId, var units)
        when isEligible(orderId, units) -> ...
~~~

Java **không bắt buộc** phương thức trong guard phải thuần túy (pure). Tuy nhiên, về thiết kế, nên bảo đảm một guard chỉ kiểm tra điều kiện và không tự gây ra những hành động khó đảo ngược.

**Điểm cần phân biệt:** “Không trộn logic nghiệp vụ vào guard” **không có nghĩa là cấm mọi điều kiện có ý nghĩa nghiệp vụ**. Ví dụ `when amountCents > 0`, `when quantity >= 100` hay `when isVip(customer)` có thể hợp lý nếu chúng là phép kiểm tra **thuần túy, rẻ và dễ hiểu**. Vấn đề xuất hiện khi guard biến thành nơi **thực hiện quy trình nghiệp vụ** như thu tiền, ghi database, gửi email, cập nhật tồn kho hoặc quyết định một chuỗi trạng thái có nhiều lý do lỗi.

## 2. Tại sao hành động nghiệp vụ trong guard là nguy hiểm?

Xét một cách viết cố ý **không nên áp dụng**:

~~~java
// ANTI-PATTERN, chỉ minh họa ý tưởng, không phải chương trình độc lập.
// 'paymentGateway' và 'order' chỉ là các dependency giả định.
String result = switch (order) {
    case PayOrder(var id, var amount)
            when paymentGateway.charge(id, amount) -> "Payment accepted";
    case PayOrder(var id, var amount) -> "Payment not accepted";
    default -> "Unsupported";
};
~~~

Thoạt nhìn, guard dường như chỉ kiểm tra “có thể thanh toán không?”. Nhưng `charge(...)` thường là **hành động gửi yêu cầu thu tiền**, không phải một predicate. Khi `case` được xét, phương thức có thể đã gọi dịch vụ bên ngoài **trước khi** nhánh được chọn.

Những rủi ro cụ thể:

- **Side effect ngay cả khi guard trả `false`:** một request hoặc thao tác ghi có thể đã thực hiện trước khi Java chuyển sang case kế tiếp.
- **Không có rollback tự động:** `switch` không biết thu tiền, ghi audit hay thay đổi tồn kho đã xảy ra; nó không tự hoàn tác nếu guard không thỏa.
- **Khó hiểu đường chạy:** nhìn vào `case ... when ...`, người bảo trì khó nhận ra thao tác I/O đang xảy ra ngay trong điều kiện.
- **Khó kiểm thử:** muốn kiểm tra chọn nhánh nào lại phải mock payment gateway, database, clock hoặc message broker.
- **Thứ tự case thành thứ tự gọi dịch vụ:** sắp xếp lại guard để refactor cú pháp có thể làm thay đổi thứ tự hành động trong hệ thống.
- **Ngoại lệ không có nghĩa là guard sai:** khi helper ném ngoại lệ, việc chọn nhánh không đơn giản “chuyển sang case kế tiếp”.
- **Retry và kiểm tra lặp:** khi phương thức bao ngoài được gọi lại hoặc một guard được đặt trong nhiều đường chạy, side effect có thể được thực hiện nhiều lần. Không nên dựa vào việc một guard “chỉ được gọi đúng một lần cho toàn bộ nghiệp vụ”.

Nguyên tắc: **guard nên quyết định nhánh nào phù hợp; phần thân nhánh hoặc service rõ trách nhiệm mới thực hiện hành động nghiệp vụ**.

## 3. Hiểu chính xác khi guard sai, đúng hoặc ném ngoại lệ

Với Java 21+:

~~~java
// Trích đoạn minh họa, 'input' là Object.
String message = switch (input) {
    case String text when text.isBlank() -> "Blank text";
    case String text -> "Text: " + text;
    case null -> "No text";
    default -> "Different type";
};
~~~

- Nếu selector là `"   "`, type pattern khớp và guard đúng: chọn `"Blank text"`.
- Nếu selector là `"hello"`, type pattern khớp nhưng guard sai: tiếp tục sang `case String text`, chọn `"Text: hello"`.
- Nếu selector là một `Integer`, type pattern `String` không khớp: những guard của hai case `String` **không chạy**.
- Nếu selector là `null`, các type pattern không khớp; nhánh `case null` xử lý.

Điều quan trọng là: **guard không phải một khối `try/catch`**. Nếu dùng:

~~~java
// Chỉ minh họa một guard có thể ném ngoại lệ.
case String text when parseRemotePolicy(text) -> "Allowed";
~~~

và `parseRemotePolicy(text)` ném một ngoại lệ, `switch` **hoàn tất bất thường** theo đường ngoại lệ, trừ khi ngoại lệ được xử lý bên trong lời gọi hoặc ở bên ngoài `switch`. Nó **không** mặc nhiên coi guard là `false` để chọn case phía sau.

Nếu việc tra cứu policy có thể thất bại do mạng hoặc I/O, hãy thực hiện bước đó **ngoài phép phân loại**, xử lý lỗi minh bạch và chỉ đưa kết quả đã xác định vào quyết định.

## 4. Minh họa tác dụng phụ của guard bằng code chạy được

Ví dụ sau cố tình tạo một guard **không thuần túy** để quan sát cơ chế. Nó không truy cập mạng hay database; side effect chỉ là tăng bộ đếm.

Tạo tệp **`SideEffectGuardDemo.java`**:

~~~java
public class SideEffectGuardDemo {
    private static int calls;

    static boolean badCheck(int number) {
        calls++;                 // Side effect: thay đổi trạng thái.
        return number > 0;
    }

    static String route(Object input) {
        return switch (input) {
            case Integer number when badCheck(number) -> "positive";
            case Integer number -> "not positive";
            case null -> "missing";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(route(-2));
        System.out.println("Calls: " + calls);
        System.out.println(route(4));
        System.out.println("Calls: " + calls);
    }
}
~~~

Biên dịch/chạy với JDK 21+:

~~~bash
javac --release 21 SideEffectGuardDemo.java
java SideEffectGuardDemo
~~~

Kết quả:

~~~text
not positive
Calls: 1
positive
Calls: 2
~~~

Phân tích:

1. Lần đầu, `input` là `-2`, được autobox thành `Integer` khi truyền cho `Object`. Pattern `Integer number` khớp.
2. Java gọi `badCheck(-2)`. Bộ đếm `calls` **tăng từ 0 lên 1**, rồi hàm trả `false`.
3. Vì guard sai, nhánh `"positive"` không được chọn. Nhánh `case Integer number` phía sau trả `"not positive"`, **nhưng side effect của guard vẫn tồn tại**.
4. Lần sau, `badCheck(4)` tăng bộ đếm lên 2 rồi trả `true`. Nhánh đầu được chọn.

Đây là phiên bản thu nhỏ của vấn đề “thu tiền trong guard nhưng trả về `false`”: hệ quả đã xảy ra, dù nhánh đầu không được chọn. `calls` chỉ là một bộ đếm minh họa; trong thực tế rủi ro có thể là ghi trùng, gửi thông báo sai hoặc tác động đến trạng thái bên ngoài.

**Không nên sửa bằng cách giấu side effect sâu hơn trong helper.** Đổi tên `badCheck` thành `isAllowed` không làm nó trở thành hàm thuần túy nếu bên trong vẫn ghi dữ liệu.

## 5. Guard nên chứa loại điều kiện nào?

Một guard **phù hợp** thường có các đặc tính:

- **Thuần túy:** với cùng đầu vào không thay đổi, kết quả kiểm tra không gây cập nhật trạng thái bên ngoài.
- **Rõ ý nghĩa:** người đọc nhìn vào điều kiện là hiểu vì sao nhánh được chọn.
- **Rẻ, có thời gian chạy dễ dự đoán:** không gọi mạng, database hay chờ resource từ bên ngoài.
- **An toàn với `null`:** kiểm tra trước khi gọi phương thức trên component có thể null.
- **Không phụ thuộc vào thứ tự side effect giữa các case.**

Ví dụ phù hợp:

~~~java
// Trích đoạn Java 21+: các record khai báo tương ứng.
case Submitted(var id, var units, var priceCents)
        when id != null && !id.isBlank()
             && units > 0 && priceCents > 0 ->
        "Valid submission";
~~~

Điều kiện kiểm tra mã đơn, số lượng và giá trị đơn vị đều là phép kiểm tra **thuần túy**. Dùng guard để phân loại hợp lệ/không hợp lệ ở mức cơ bản là hợp lý, miễn là có nhánh xử lý các dữ liệu không qua guard.

Ví dụ **đáng xem xét lại**:

~~~java
// ANTI-PATTERN: minh họa, không phải code độc lập.
case Submitted(var id, var units, var priceCents)
        when checkQuota(id)
             && reserveInventory(id, units)
             && writeAuditLog(id)
             && notifyWarehouse(id) ->
        "Accepted";
~~~

Tuy tất cả helper trên có thể trả về `boolean`, việc đặt chúng trong `when` làm luồng nghiệp vụ và side effect bị ràng buộc vào **thứ tự short-circuit của biểu thức điều kiện**. Nếu `reserveInventory` thành công nhưng `notifyWarehouse` thất bại, nhánh fallback được chọn không có nghĩa lượng hàng đã giữ sẽ được trả lại.

**Thiết kế lại:** điều kiện chỉ nên dựa trên dữ liệu hoặc kết quả đã được tính rõ ràng; những bước thay đổi trạng thái phải nằm ở một luồng xử lý có transaction/idempotency/error handling được thiết kế riêng.

### Predicate có tên vẫn cần kiểm tra bên trong

Nếu điều kiện bắt đầu dài, ta có thể tách thành helper:

~~~java
static boolean isValidOrder(String id, int units, long unitPriceCents) {
    return id != null && !id.isBlank()
            && units > 0 && unitPriceCents > 0;
}

// Trích đoạn một nhánh case Java 21+.
case Submitted(var id, var units, var priceCents)
        when isValidOrder(id, units, priceCents) ->
        new Decision(DecisionType.ACCEPT_SUBMISSION, id);
~~~

Tên `isValidOrder` chỉ nên được dùng khi helper **chỉ kiểm tra**. Nếu helper gọi database, thực hiện ghi, tạo payment, sửa cache hay phát sự kiện, tên đó gây hiểu nhầm. Những rule nghiệp vụ phụ thuộc dữ liệu không sẵn có (ví dụ hạn mức hiện tại trong hệ thống khác) thường nên được thu thập/xác thực ở tầng service trước khi đi tới quyết định thuần túy.

## 6. Tách ba bước: kiểm tra, quyết định, hành động

Một cấu trúc dễ đọc và dễ test:

~~~text
Input / Event
      |
      v
[Kiểm tra kiểu và dữ liệu có thể tính thuần túy]
      |
      v
[Quyết định / Decision]  <-- pattern + when (nếu phù hợp)
      |
      v
[Thực hiện hành động]    <-- lưu trạng thái, audit, I/O, notification
      |
      v
[Trả kết quả]
~~~

Không nhất thiết ứng dụng nào cũng cần đủ ba lớp riêng biệt. Nhưng **ranh giới giữa quyết định và side effect phải hiển thị được trong code**.

Ví dụ:

- `decide(event)`: nhận event, trả `Decision`; không ghi log, không gọi API.
- `execute(event, audit)`: gọi `decide`, rồi **thực hiện hành động** dựa trên decision.
- Nếu xử lý thật có tính giao dịch, service bên ngoài phải quản lý **transaction, duplicate delivery, retry, quyền truy cập và idempotency**. `switch` không tự giải quyết các vấn đề đó.

Điểm quan trọng là một `Decision` có thể kiểm tra bằng unit test thuần túy; người kiểm thử không cần khởi tạo gateway hay database chỉ để biết sự kiện nào được phân loại là hợp lệ.

## 7. Ví dụ hoàn chỉnh Java 21+: guard thuần túy, hành động tách riêng

Tạo tệp **`GuardSeparationDemo.java`**:

~~~java
public class GuardSeparationDemo {
    sealed interface OrderEvent permits Submitted, CancelRequested {}

    record Submitted(String orderId, int units, long unitPriceCents)
            implements OrderEvent {}

    record CancelRequested(String orderId, String reason)
            implements OrderEvent {}

    enum DecisionType {
        ACCEPT_SUBMISSION, REJECT_SUBMISSION,
        ACCEPT_CANCELLATION, REJECT_CANCELLATION
    }

    record Decision(DecisionType type, String orderId) {}

    static boolean validOrderId(String id) {
        return id != null && !id.isBlank();
    }

    static boolean validReason(String reason) {
        return reason != null && !reason.isBlank();
    }

    static Decision decide(OrderEvent event) {
        if (event == null) {
            throw new IllegalArgumentException("event required");
        }

        return switch (event) {
            case Submitted(var id, var units, var unitPriceCents)
                    when validOrderId(id) && units > 0 && unitPriceCents > 0 ->
                    new Decision(DecisionType.ACCEPT_SUBMISSION, id);

            case Submitted(var id, var units, var unitPriceCents) ->
                    new Decision(DecisionType.REJECT_SUBMISSION, id);

            case CancelRequested(var id, var reason)
                    when validOrderId(id) && validReason(reason) ->
                    new Decision(DecisionType.ACCEPT_CANCELLATION, id);

            case CancelRequested(var id, var reason) ->
                    new Decision(DecisionType.REJECT_CANCELLATION, id);
        };
    }

    static String execute(OrderEvent event, java.util.List<String> audit) {
        Decision decision = decide(event);

        return switch (decision.type()) {
            case ACCEPT_SUBMISSION -> {
                audit.add("submitted:" + decision.orderId());
                yield "Submitted " + decision.orderId();
            }
            case REJECT_SUBMISSION -> "Rejected submission";
            case ACCEPT_CANCELLATION -> {
                audit.add("cancelled:" + decision.orderId());
                yield "Cancellation accepted " + decision.orderId();
            }
            case REJECT_CANCELLATION -> "Rejected cancellation";
        };
    }

    public static void main(String[] args) {
        var audit = new java.util.ArrayList<String>();

        System.out.println(execute(new Submitted("O-1", 3, 500), audit));
        System.out.println(execute(new Submitted("O-2", 0, 500), audit));
        System.out.println(execute(
                new CancelRequested("O-1", "customer request"), audit));
        System.out.println(execute(new CancelRequested("O-1", "  "), audit));
        System.out.println(execute(new Submitted(null, 2, 100), audit));
        System.out.println("Audit: " + audit);

        try {
            execute(null, audit);
        } catch (IllegalArgumentException ex) {
            System.out.println("Null: " + ex.getMessage());
        }
    }
}
~~~

Chạy bằng JDK 21+:

~~~bash
javac --release 21 -encoding UTF-8 GuardSeparationDemo.java
java GuardSeparationDemo
~~~

Kết quả:

~~~text
Submitted O-1
Rejected submission
Cancellation accepted O-1
Rejected cancellation
Rejected submission
Audit: [submitted:O-1, cancelled:O-1]
Null: event required
~~~

### Đọc code theo trách nhiệm

**A. Domain types:** `sealed interface OrderEvent` mô hình hóa hai loại event. Record giữ payload theo kiểu riêng. Bản thân việc tạo record `Submitted(null, 2, 100)` không bị compiler ngăn; invariant cần được kiểm tra ở runtime hoặc constructor theo hợp đồng domain.

**B. `validOrderId` / `validReason`:** là các predicate chỉ đọc dữ liệu, không sửa trạng thái. Chúng an toàn với `null` nhờ `&&` short-circuit. Không có network request hoặc thao tác ghi trong hai helper.

**C. `decide`:** `case Submitted(... ) when ...` và `case CancelRequested(...) when ...` chỉ phân loại. Nếu guard không thỏa, case không guard cùng record xử lý trường hợp bị từ chối. Hai loại record được bao phủ đầy đủ; `switch expression` không cần `default` khi selector có kiểu tĩnh `OrderEvent` sealed đã bao phủ.

**D. `execute`:** quyết định được tính xong mới thực hiện `audit.add(...)` trong nhánh được chọn. Những quyết định từ chối không ghi audit trong ví dụ này. Đây là lựa chọn minh họa, **không phải chính sách audit chuẩn cho mọi hệ thống** — nhiều ứng dụng vẫn cần audit cả các yêu cầu bị từ chối, nhưng nên diễn đạt mục đích và thời điểm ghi rõ ràng.

**E. `null`:** `decide(null)` ném `IllegalArgumentException("event required")` trước khi chạy `switch`, vì vậy không cần `case null` trong `switch` của `decide`. Ngược lại, `null` vẫn được thử trong hàm `main` để minh họa cách báo lỗi.

**F. Giới hạn ví dụ:** `CancelRequested("O-1", ...)` chỉ được kiểm tra cấu trúc ID và lý do. Chương trình này **không** kiểm tra đơn hàng đang tồn tại, chủ sở hữu hay trạng thái được phép hủy. Trong production, cần một service xác thực trạng thái thực tế trước khi thực hiện hủy và phối hợp với transaction. Không được hiểu `DecisionType.ACCEPT_CANCELLATION` trong ví dụ là đủ để cấp quyền hủy đơn ngoài hệ thống thực tế.

## 8. Khi nào nên bỏ `when` và dùng helper trả kết quả chi tiết?

Một guard Boolean chỉ trả lời **“đúng hay sai”**. Nếu hệ thống phải phân biệt nhiều lý do từ chối, ép tất cả vào một điều kiện dài sẽ làm mất thông tin.

Ví dụ yêu cầu:

- Mã đơn thiếu → `INVALID_ID`.
- Số lượng không dương → `INVALID_UNITS`.
- Đơn giá không hợp lệ → `INVALID_PRICE`.

Trong trường hợp đó, có thể viết một helper **thuần túy** trả về validation result:

~~~java
// Ví dụ độc lập về ý tưởng; đặt trong lớp chứa các khai báo phù hợp.
enum ValidationCode {
    OK, INVALID_ID, INVALID_UNITS, INVALID_PRICE
}

static ValidationCode validateSubmitted(
        String orderId, int units, long unitPriceCents) {
    if (orderId == null || orderId.isBlank()) {
        return ValidationCode.INVALID_ID;
    }
    if (units <= 0) {
        return ValidationCode.INVALID_UNITS;
    }
    if (unitPriceCents <= 0) {
        return ValidationCode.INVALID_PRICE;
    }
    return ValidationCode.OK;
}
~~~

Sau đó xử lý rõ kết quả trong một nhánh thay vì gắn ba bốn tầng business rule vào guard:

~~~java
// Trích đoạn trong switch expression trả ValidationCode.
case Submitted(var id, var units, var price) ->
        validateSubmitted(id, units, price);
~~~

Hoặc trong một phương thức chuyên biệt:

~~~java
// Trích đoạn; Submitted và ValidationCode đã được định nghĩa.
static ValidationCode validateEvent(Submitted event) {
    return validateSubmitted(
            event.orderId(), event.units(), event.unitPriceCents());
}
~~~

Cách này thuận tiện cho unit tests: từng loại lỗi có tên và tính thứ tự kiểm tra rõ ràng. Nếu cần tạo thông điệp thân thiện với người dùng, có thể chuyển `ValidationCode` thành thông điệp ở tầng presentation. **Không** nên thực hiện hành động ghi dữ liệu bên trong `validateSubmitted`.

### Khi nào giữ `when`?

Giữ guard nếu đó là **bộ lọc đơn giản** và có một nhánh kế tiếp rõ ràng:

~~~java
// Trích đoạn Java 21+, 'input' là Object.
String size = switch (input) {
    case Integer count when count >= 100 -> "large";
    case Integer count -> "small";
    case null -> "missing";
    default -> "unsupported";
};
~~~

Không cần tạo một service chỉ để kiểm tra `count >= 100`. Mục tiêu là **độ rõ ràng**, không phải “cấm logic nghiệp vụ xuất hiện trong điều kiện”.

## 9. Guard, phạm vi biến và thứ tự case

### Pattern variable nằm trong phạm vi của guard

~~~java
// Trích đoạn Java 21+: 'input' có kiểu Object.
String label = switch (input) {
    case String text when !text.isBlank() -> "Text: " + text;
    case String text -> "Blank text";
    case null -> "Missing";
    default -> "Other";
};
~~~

`text` chỉ được dùng sau khi pattern `String text` đã khớp. Compiler theo dõi phạm vi biến trong guard và nhánh. Pattern không khớp thì guard tương ứng không được đánh giá.

### Case tổng quát phải đứng sau case có guard

Đoạn sau **không biên dịch** do dominance:

~~~java
// CỐ Ý SAI: case String không guard đứng trước nhánh có guard.
String label = switch (input) {
    case String text -> "Anything String";
    case String text when text.isBlank() -> "Blank"; // Bị che.
    case null -> "Missing";
    default -> "Other";
};
~~~

Mọi giá trị khớp `case String text when ...` đều đã bị nhánh `case String text` trước đó bao phủ. Sắp **case có guard trước**, case cùng type không guard sau.

Không nên đưa một side effect vào guard chỉ để “buộc nhánh này được xem trước” hoặc “dùng thứ tự case làm thứ tự thực hiện workflow”. Thứ tự case dùng để **phân loại**, không phải thay thế orchestration có chủ đích.

### Những guard có điều kiện giao nhau

Ví dụ:

~~~java
// Trích đoạn: 'input' có kiểu Object.
String label = switch (input) {
    case Integer n when n >= 100 -> "at least 100";
    case Integer n when n >= 50 -> "50 to 99";
    case Integer n -> "below 50";
    case null -> "missing";
    default -> "not integer";
};
~~~

Số `120` cũng thỏa `n >= 50` nhưng sẽ được nhánh **đầu tiên phù hợp** xử lý. Trường hợp này là có chủ đích; nhưng nếu guard là những chính sách phức tạp, các điều kiện giao nhau có thể khiến kết quả phụ thuộc vào thứ tự mà người bảo trì không nhận ra. Khi đó, helper phân loại hoặc bảng quyết định minh bạch có thể tốt hơn.

## 10. `null` và exception trong guard

Đây là nguồn lỗi rất phổ biến khi record patterns lấy dữ liệu tham chiếu:

~~~java
record Customer(String name) {}

// Trích đoạn Java 21+, 'input' là Object.
String label = switch (input) {
    case Customer(var name) when name != null && !name.isBlank() ->
            "Customer: " + name;
    case Customer(var name) -> "Missing customer name";
    case null -> "No customer";
    default -> "Other";
};
~~~

Lưu ý:

- `Customer(var name)` khớp một `Customer` khác `null`, kể cả khi **component `name` là `null`**.
- `name != null && !name.isBlank()` đảm bảo không gọi `isBlank()` trên `null`; `&&` đánh giá vế phải chỉ khi vế trái đúng.
- Nếu guard viết thành `!name.isBlank()` và `name == null`, `NullPointerException` có thể xảy ra trong lúc kiểm tra guard, **không** tự chuyển sang `case Customer(var name)`.
- `case null` xử lý selector `input == null`, khác với component `Customer.name == null`.

Tương tự, nếu một guard gọi helper có thể ném `IllegalStateException` hay một unchecked exception khác, người gọi phải nhận và xử lý ngoại lệ theo hợp đồng của chương trình. `switch` không tự coi ngoại lệ là điều kiện Boolean `false`.

### Guard có thể đọc trạng thái bên ngoài không?

Java cho phép, nhưng nên cân nhắc. Ví dụ kiểm tra **thời gian hiện tại**, số lượng trong kho hay trạng thái quyền truy cập của user từ service có thể thay đổi giữa lần kiểm tra và lần thực hiện. Ngay cả khi guard chỉ đọc mà không ghi, nó vẫn có thể tạo **time-of-check/time-of-use (TOCTOU) problem**.

Hướng xử lý tùy nghiệp vụ: lấy snapshot/version rõ ràng, validate lại trong cùng transaction, sử dụng optimistic locking hoặc thực hiện một thao tác nguyên tử trong service chuyên trách. Đừng tin rằng vì guard trả `true` thì điều kiện ngoài hệ thống vẫn còn đúng ở thời điểm ghi.

## 11. Các trường hợp gây nhầm với transaction và retry

Giả sử workflow thực tế cần kiểm tra tồn kho, giữ hàng và tạo đơn. Một guard như:

~~~java
// ANTI-PATTERN: chỉ minh họa, tên phương thức biểu thị side effect.
case Submitted(var id, var units, var price)
        when inventory.reserve(id, units) && payment.charge(id, price) ->
        "accepted";
~~~

sẽ khiến hành động `inventory.reserve` xảy ra trước `payment.charge`. Nếu hành động đầu thành công nhưng hành động sau trả `false`, `switch` chọn nhánh khác nhưng việc giữ hàng **có thể vẫn tồn tại**. Nếu phương thức bị gọi lại sau timeout, có nguy cơ thao tác lặp.

Tốt hơn, nghiệp vụ nên được diễn đạt trong **application service** với thứ tự, transaction và chính sách retry cụ thể:

~~~java
// Pseudocode có chủ đích; không phải chương trình Java độc lập.
// Các dependency/service và transaction API là giả định.
Decision decision = classifyPurely(event);
if (decision.accepted()) {
    service.processAtomically(event); // Thực hiện side effect có kiểm soát.
}
~~~

Với hệ thống phân tán, “atomically” không tự xuất hiện chỉ bằng cách gọi một phương thức. Có thể cần saga, outbox/inbox, idempotency keys hoặc giải pháp transaction tương ứng. Tên hàm chỉ để làm rõ **chỗ đặt trách nhiệm**, không cam kết một lời gọi đơn lẻ bảo đảm exactly-once.

Một điểm nữa: log chẩn đoán trong guard **cũng là side effect**, dù nhẹ hơn thu tiền. Ghi log cho mục đích debug đôi khi chấp nhận được, nhưng nếu audit log có giá trị pháp lý/kinh doanh thì nó là một phần workflow và không nên bị giấu trong predicate.

## 12. Bảng lỗi và cách sửa

| Lỗi thường gặp | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| `when gateway.charge(...)` | Có thể thu tiền trước khi nhánh được chọn; khó rollback | Guard chỉ quyết định, service thực hiện charge rõ ràng |
| `when repository.save(...)` | Thao tác ghi xảy ra trong điều kiện | Đưa lưu dữ liệu vào case body hoặc service |
| Helper tên `isEligible` nhưng gửi email | Tên giả tạo cảm giác thuần túy | Tách `isEligible` và `notify` |
| Guard gọi API có timeout | Lỗi/ngoại lệ ảnh hưởng phân nhánh, độ trễ khó đoán | Lấy dữ liệu hoặc xử lý lỗi ở service trước khi phân loại |
| Guard trả false sau khi đã tăng counter/giữ hàng | Side effect vẫn tồn tại dù case không được chọn | Dùng predicate thuần túy, hành động sau decision |
| `case T var -> ...` trước `case T var when ...` | Case guard bị dominated | Đặt case guard trước case không guard |
| Chỉ có case có guard, không có fallback cho subtype | Có thể không exhaustive hoặc bỏ sót giá trị không thỏa điều kiện | Bổ sung case cùng type không guard hoặc nhánh xử lý phù hợp |
| Gọi `name.isBlank()` khi component có thể `null` | Ném `NullPointerException` trong guard | Kiểm tra `name != null && ...` |
| Nén nhiều lý do từ chối thành một Boolean | Mất thông tin lỗi, khó test | Trả `ValidationResult`/`Decision` có mã lý do |
| Guard đọc trạng thái thay đổi liên tục rồi body ghi sau | TOCTOU, quyết định dựa trên dữ liệu cũ | Transaction, versioning hoặc recheck có kiểm soát |
| Cho rằng guard false sẽ rollback | Giao thức `switch` không quản lý side effects | Thiết kế rollback/compensation rõ ràng |
| Coi compiler cho phép là kiến trúc đúng | Java không cấm side-effecting helper trong `when` | Code review, test, và tách trách nhiệm |

Không cần thay mọi guard thành helper. Hãy ưu tiên thay đổi **những guard có trạng thái, I/O, điều kiện khó đọc, hoặc phải trả lỗi chi tiết**.

## 13. Bài tập tự luyện

### Bài 1. Nhận diện guard có side effect

Đoạn sau có vấn đề gì?

~~~java
// Pseudocode minh họa.
case Payment(var id, var amount)
        when sendEmail(id) && charge(amount) -> "Success";
~~~

**Đáp án:** `sendEmail` và `charge` có thể gây side effect ngay trong điều kiện chọn nhánh. Nếu `sendEmail` trả `true` nhưng `charge` trả `false` hoặc ném ngoại lệ, email có thể đã được gửi. Nên phân loại theo thông tin thuần túy, còn gửi email/charge thực hiện ở service với transaction và error handling phù hợp.

### Bài 2. Viết guard hợp lý

Cho record:

~~~java
record Registration(String username, int age) {}
~~~

Với `Object input`, trả `"Eligible"` nếu `username` không `null`, không trắng và `age >= 18`; trả `"Invalid registration"` với `Registration` còn lại; `"Missing"` nếu selector `null`; `"Other"` với kiểu khác.

**Đáp án:**

~~~java
// Trích đoạn Java 21+.
String label = switch (input) {
    case Registration(var username, var age)
            when username != null && !username.isBlank() && age >= 18 ->
            "Eligible";
    case Registration(var username, var age) -> "Invalid registration";
    case null -> "Missing";
    default -> "Other";
};
~~~

Guard chỉ đọc dữ liệu của record, không ghi dữ liệu, phù hợp với mục đích phân loại đơn giản.

### Bài 3. Side effect khi guard `false`

Trong `SideEffectGuardDemo`, tại sao sau `route(-2)`, kết quả là `"not positive"` mà `calls` vẫn tăng?

**Đáp án:** Pattern `Integer number` đã khớp nên `badCheck(-2)` được gọi. Lệnh `calls++` chạy trước khi hàm trả `false`. Guard sai chỉ khiến case đầu không được chọn, **không đảo ngược** các lệnh đã thực thi trong guard.

### Bài 4. Cần mã lỗi chi tiết

Một validation cần trả `INVALID_ID`, `INVALID_QUANTITY`, `OUT_OF_STOCK`. Có nên viết một biểu thức `when isValidId(id) && isValidQuantity(qty) && reserveStock(qty)` không?

**Đáp án:** Không. `reserveStock` là thao tác có side effect. Nếu muốn trả mã lỗi cụ thể, hãy tách validation thuần túy thành một hàm `ValidationResult` hoặc các bước rõ ràng. Việc giữ hàng cần service chuyên trách, xử lý số lượng tồn kho, transaction/concurrency và khả năng thất bại tại thời điểm ghi.

### Bài 5. Khi nào dùng predicate có tên?

Giả sử guard chứa:

~~~java
when id != null && !id.isBlank()
    && units > 0 && priceCents > 0
~~~

Khi nào nên tách thành `when validOrder(id, units, priceCents)`?

**Đáp án:** Khi tên `validOrder` làm rõ quy tắc hoặc logic được tái sử dụng/test độc lập, và helper **không gây side effect**. Không nhất thiết tách nếu biểu thức ngắn, rõ và chỉ xuất hiện một chỗ. Nếu validation cần trả lý do lỗi, nên dùng kiểu kết quả chi tiết thay vì Boolean.

## 14. Checklist review guard trong codebase

Khi review một `case ... when ...`, hãy đặt những câu hỏi này:

1. Guard có chỉ **đọc** và kiểm tra dữ liệu không, hay thực hiện update/insert/send/charge/reserve?
2. Nếu guard trả `false`, **đã có tác dụng phụ nào xảy ra** chưa?
3. Nếu helper trong guard ném ngoại lệ, người gọi có biết đường lỗi và xử lý đúng không?
4. Predicate có an toàn với `null` và có dùng short-circuit đúng không?
5. Guard có rẻ và dễ hiểu không, hay đang giấu chuỗi kiểm tra/phụ thuộc bên ngoài?
6. Case có guard có được đặt trước case tổng quát cùng type không? Có fallback đúng cho những giá trị không qua guard không?
7. Nếu nhiều guard cùng đúng, thứ tự ưu tiên nhánh có được chủ động thiết kế và test không?
8. Nếu policy dựa trên dữ liệu thay đổi, kết quả kiểm tra có thể lỗi thời trước thao tác ghi không?
9. Nếu cần nhiều thông điệp lỗi, Boolean guard có đủ mô tả hay nên dùng validation result?
10. Có thể tách rõ **`decide` thuần túy** khỏi **`execute` có side effect** để test và bảo trì dễ hơn không?

## 15. Tổng kết

- `when` là **điều kiện bổ sung để chọn nhánh sau khi pattern khớp**, không phải nơi thực hiện workflow nghiệp vụ.
- Guard có thể chứa **điều kiện nghiệp vụ đơn giản và thuần túy**. Không cần xóa hết business predicates chỉ vì chúng có ý nghĩa domain.
- Side effect trong guard có thể xảy ra **dù điều kiện trả `false`**; ngoại lệ từ guard **không tự chuyển thành fallback**.
- Đặt kiểm tra thuần túy và quyết định trong phần phù hợp của `switch`; đưa ghi dữ liệu, thanh toán, gửi thông báo, audit quan trọng và transaction vào **phần thân xử lý/service rõ trách nhiệm**.
- Khi validation phức tạp hoặc cần lý do lỗi chi tiết, dùng helper thuần túy trả `Decision`/`ValidationResult` thay vì một chuỗi guard khó đọc.
- Compiler hỗ trợ type checking, scope, dominance và exhaustiveness; **compiler không chứng minh guard không có side effect** hay workflow an toàn giao dịch.
- Kiểm thử cả trường hợp pattern khớp, guard đúng/sai, `null`, ngoại lệ, concurrency và retry theo hợp đồng hệ thống.

**Tài liệu tham khảo chính thức:** [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441), [JEP 440 — Record Patterns](https://openjdk.org/jeps/440), [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html).
