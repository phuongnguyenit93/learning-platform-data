# Checklist xử lý null khi dùng Java Pattern Matching (Java 21+)

## 1. Mục tiêu: kiểm tra đúng hợp đồng, không chỉ tránh NullPointerException

Một lần refactor từ chuỗi kiểm tra kiểu cũ sang `instanceof` pattern, record pattern hoặc pattern `switch` có thể làm thay đổi cách chương trình xử lý `null`. Dấu hiệu dễ thấy là `NullPointerException`, nhưng lỗi nghiêm trọng hơn đôi khi là **âm thầm coi dữ liệu thiếu thành thành công** hoặc **chọn sai nhánh nghiệp vụ**.

Checklist này dành cho lúc viết code, review pull request, chuyển đổi code Java cũ và thiết kế test cho các nhánh pattern. Mục tiêu là trả lời rõ:

1. Giá trị `null` xuất hiện ở **selector ngoài cùng** hay ở **component bên trong record**?
2. `null` là một giá trị được hợp đồng cho phép, một lỗi dữ liệu cần trả về có cấu trúc, hay một vi phạm tiền điều kiện lập trình?
3. Pattern có thực sự khớp với null ở vị trí đó hay không?
4. Guard có kiểm tra null **trước khi dereference** và có đường dự phòng cho khi guard sai?
5. `switch expression` đã xử lý đủ subtype, trường hợp null và trường hợp loại khác theo đúng kiểu selector?
6. Có test xác minh riêng **null selector**, **null record lồng**, **null component**, **guard false** và **default** không?

**Điểm cốt lõi:** không có một quy tắc “thêm `case null` vào mọi switch” áp dụng cho toàn bộ ứng dụng. `case null` là một lựa chọn **hợp đồng API**. Khi đầu vào bắt buộc khác null, `Objects.requireNonNull` và ngoại lệ rõ ràng có thể phù hợp hơn.

Bài dùng **Java 21+**, phiên bản mà record pattern và pattern matching trong `switch` đã ổn định, không cần bật preview. Những ví dụ minh họa ngắn sẽ được phân biệt với chương trình Java hoàn chỉnh ở mục 9.

## 2. Checklist quyết định trong 30 giây

Trước khi đọc từng dòng `case`, xác định **chính sách**:

| Câu hỏi review | Nếu “Có” | Hành động phù hợp |
| --- | --- | --- |
| Selector có thể vắng mặt theo hợp đồng không? | Có | `case null` trả kết quả nghiệp vụ/validation được mô tả rõ |
| Selector bắt buộc phải tồn tại? | Có | Từ chối tường minh ở ranh giới, chẳng hạn `requireNonNull` |
| Selector là object nhưng một field bên trong có thể null? | Có | Validate component, dùng guard hoặc constructor/factory invariant |
| Một record lồng có thể không tồn tại? | Có | Xử lý nhánh outer record fallback; `case null` ngoài cùng không thay thế được |
| Guard gọi phương thức trên biến pattern? | Có | Bảo đảm biến khác null **trước khi gọi** |
| `default` đang được dùng để “bắt mọi thứ”? | Có | Kiểm tra riêng selector null, độ bao phủ subtype và kiểu chưa hỗ trợ |
| Selector là `sealed interface`? | Có | Dùng các nhánh bao phủ đầy đủ, cân nhắc bỏ `default` để compiler nhắc khi thêm subtype |
| Có nhiều trường cùng sai? | Có | Xác định thứ tự ưu tiên lỗi, đặt guard theo thứ tự và test |
| Có chuyển từ `instanceof` sang `switch`? | Có | Test lại null, vì hai cấu trúc không có hành vi mặc định giống nhau |

Một chính sách rõ thường viết được thành một câu:

> “Ở ranh giới nhận event từ ngoài, event null trả `INVALID:event`; trong API nội bộ, event null là lỗi gọi API; trường `referral` null là tùy chọn; trường `account` null hoặc `account.id` null là lỗi dữ liệu.”

Khi chưa thể viết câu trên, **chưa nên chọn `case null` hay `default` chỉ để làm chương trình biên dịch**.

## 3. Phân loại vị trí null: một bảng kiểm tra quan trọng

Cùng chữ `null`, nhưng các ngữ cảnh pattern khác nhau:

| Vị trí | Ví dụ | Hành vi hoặc rủi ro |
| --- | --- | --- |
| Selector của `instanceof` | `Object x = null; x instanceof String s` | `false`; biến mẫu không được dùng ở đường không khớp |
| Selector của pattern `switch` | `switch (x)` với `x == null` | Không tự chạy `default`; thường ném `NullPointerException` nếu không có nhánh null phù hợp |
| Selector được xử lý tường minh | `case null -> invalid("event")` | Chọn nhánh null theo contract |
| Record ngoài cùng tồn tại, record con null | `Signup(null, "web", null)` | `Signup(Account(...))` không khớp; cần nhánh `Signup(...)` rộng hơn |
| Record con tồn tại, field null | `Signup(Account(null), "web", null)` | `var id` nhận null; guard cần kiểm tra |
| Component được mô hình là tùy chọn | `referral == null` | Có thể là hợp lệ và được diễn giải có chủ đích |
| Component có kiểu tĩnh `String`, dùng unconditional component pattern | `TypedText(String text)` với text null | Có thể khớp, biến `text` vẫn null |
| Component có kiểu tĩnh `Object`, dùng conditional `String` pattern | `OpenText(String text)` với text null | Pattern con không khớp |
| Context bắt buộc do caller cung cấp | `routeRequired(null)` | Từ chối sớm; không nên giả vờ là event hợp lệ |

**Đừng đồng nhất** “mẫu record con không khớp” với “guard trả false”. Nếu record con là null, guard của nhánh chứa record pattern lồng **chưa được gọi**. Nếu record con tồn tại nhưng field bên trong null, record pattern có thể khớp và guard được đánh giá.

### Ví dụ ngắn: trước và sau khi thêm null policy

~~~java
// Đoạn phương thức minh họa độc lập về cú pháp:
static String describe(Object value) {
    return switch (value) {
        case String s when !s.isBlank() -> "text:" + s;
        case String s -> "blank-text";
        default -> "other";
    };
}
~~~

`describe("abc")` cho `"text:abc"`; `describe(" ")` cho `"blank-text"`; `describe(10)` cho `"other"`. Nhưng **`describe(null)` ném NPE**, không phải `"other"`.

Nếu contract yêu cầu nhận input thiếu và trả tên trạng thái:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when !s.isBlank() -> "text:" + s;
        case String s -> "blank-text";
        default -> "other";
    };
}
~~~

Nếu contract yêu cầu selector luôn tồn tại, thay vì trả `"missing"`, có thể giữ các nhánh và đặt:

~~~java
java.util.Objects.requireNonNull(value, "value");
~~~

**Checklist:** mỗi thay đổi null policy phải đi kèm cập nhật Javadoc/API contract, ca test null và xác nhận hành vi của caller.

## 4. Kiểm tra `instanceof`, type pattern và flow scoping

`instanceof` trả false khi toán hạng bên trái null:

~~~java
Object input = null;

if (input instanceof String text) {
    System.out.println(text.length());
} else {
    System.out.println("not-text");
}
~~~

Output:

~~~text
not-text
~~~

`text` chỉ có phạm vi hữu ích trên đường chương trình đã chứng minh pattern khớp. Khi dùng toán tử logic:

~~~java
if (input instanceof String text && !text.isBlank()) {
    System.out.println("valid");
}
~~~

Vế phải `&&` chỉ được đánh giá nếu `instanceof String text` đúng. Đây là mẫu code an toàn khi chính selector có thể null.

**Không suy luận sai sang `||`**:

~~~java
// Không hợp lệ: ở vế phải của ||, text không được bảo đảm đã được gán.
// if (input instanceof String text || text.isBlank()) { ... }
~~~

Không dùng một biến pattern ngoài phạm vi mà compiler cho phép. Và đừng nhầm cơ chế này với record component pattern, nơi một `var` có thể nhận null sau khi record ngoài khớp.

### Câu hỏi dành cho reviewer

- Người viết có dựa vào `instanceof` để loại null **selector** hay đang vô tình tưởng nó loại mọi null **component**?
- Có dùng `&&` thay vì `||` ở nơi biến pattern chỉ có phạm vi nếu nhánh trái khớp?
- Có thay một `if (x instanceof T)` cũ bằng `switch (x)` và vô tình đổi hành vi null không?
- Có cast thủ công hoặc gọi method trước khi kiểm tra null/kiểu?

## 5. Checklist cho record pattern lồng

Dữ liệu ví dụ:

~~~java
record Account(String id) {}
record Signup(Account account, String source, String referral) {}
~~~

Xét bốn input:

~~~java
new Signup(null, "web", null);
new Signup(new Account(null), "web", null);
new Signup(new Account("A1"), null, null);
new Signup(new Account("A1"), "web", null);
~~~

Mỗi trường hợp cần một ý nghĩa rõ:

1. **Account null:** không có object con; pattern `Signup(Account(var id), ...)` không khớp.
2. **Account.id null:** object con có tồn tại; `Account(var id)` khớp, và `id` nhận null.
3. **Source null:** `var source` nhận null, cần kiểm tra validation.
4. **Referral null:** nếu referral là trường tùy chọn, null có thể **hợp lệ**, không nhất thiết phải từ chối.

Một `case null` trên `Signup` selector **không bắt** ba trường hợp component null đó, vì object `Signup` vẫn tồn tại.

### Thiết kế nhánh an toàn theo độ đặc hiệu

~~~java
return switch (event) {
    case null -> invalid("event");

    case Signup(Account(var id), var source, var referral)
            when blank(id) -> invalid("accountId");

    case Signup(Account(var id), var source, var referral)
            when blank(source) -> invalid("source");

    case Signup(Account(var id), var source, var referral) ->
            ok("signup:" + id + ":" + source + ":"
                    + optionalReferral(referral));

    case Signup(var account, var source, var referral) ->
            invalid("account");

    // Các variant Event khác...
};
~~~

Đây là **khung minh họa trong `switch`**, có comment thay các nhánh còn lại nên không phải phương thức độc lập. Mục 9 chứa toàn bộ phiên bản biên dịch được.

Vì sao thứ tự này có ích?

- Các guard validation **trước** nhánh thành công không guard.
- Nhánh `Signup(Account(...))` không guard đứng sau validation bao phủ mọi Signup có `Account` khác null, kể cả khi referral null.
- Nhánh `Signup(var account, ...)` rộng hơn đặt sau cùng, tiếp nhận Signup có `account == null`.
- Nếu đưa nhánh `Signup(var account, ...)` lên trước, các nhánh cụ thể phía sau có thể bị báo *dominated*.
- Trong bài, khi cả `accountId` và `source` sai, lỗi `accountId` được ưu tiên vì guard của nó xuất hiện trước. Đây là chính sách **có chủ đích**, cần test.

### Đừng dereference trong guard trước khi kiểm tra null

~~~java
// Sai khi id có thể null:
// case Signup(Account(var id), var source, var referral)
//     when !id.isBlank() -> ...

// Null-safe:
static boolean blank(String text) {
    return text == null || text.isBlank();
}
~~~

`||` đánh giá ngắn mạch: khi `text == null`, Java không chạy `text.isBlank()`. Nếu dùng `&&` để kiểm tra giá trị hợp lệ, hãy đặt `text != null` trước lời gọi phương thức.

## 6. Một bẫy nâng cao: component pattern kiểu String vẫn có thể nhận null

Hai record:

~~~java
record TypedText(String text) {}
record OpenText(Object text) {}
~~~

Nếu component của record được khai báo trực tiếp là `String`, pattern con `String text` có thể là **unconditional pattern**, và Java 21 cho phép nó khớp cả giá trị component null:

~~~java
Object typed = new TypedText(null);

boolean matched =
        typed instanceof TypedText(String text) && text == null;

// matched == true
~~~

Ngược lại, record có component kiểu tĩnh `Object` yêu cầu một phép kiểm tra kiểu `String` có điều kiện:

~~~java
Object open = new OpenText(null);

boolean matched =
        open instanceof OpenText(String text);

// matched == false
~~~

So sánh thêm:

~~~java
Object nothing = null;
boolean matchesTopLevel = nothing instanceof String text;
// matchesTopLevel == false
~~~

**Ba kết quả không mâu thuẫn nhau.** Selector ngoài cùng khác với record component; component pattern unconditional khác với conditional pattern trên `Object`. Do đó, checklist review cần xem **kiểu khai báo của component**, không chỉ nhìn thấy từ khóa `String` hoặc `var` rồi tự kết luận đã loại null.

Khi phần thân case gọi `text.length()`, hãy hỏi **constructor/factory có thực thi invariant non-null chưa?** Nếu không, cần guard hoặc validation. Record là kiểu dữ liệu, không tự tạo non-null contract cho component tham chiếu.

## 7. Checklist cho `switch` exhaustive, `when` và `default`

Với tập command đóng:

~~~java
sealed interface Event permits Signup, Invoice, Logout {}
~~~

Ba subtype record là final; một `switch expression` xử lý đủ cả ba nhánh có thể exhaustive. Tuy vậy phải kiểm tra **mẫu có guard** và **component lồng**.

### Quy tắc thực hành

- **Một case có `when` không được coi là bao phủ toàn bộ subtype.** Nếu guard false, phải có nhánh sau xử lý.
- **Record pattern lồng có thể không khớp khi record con null.** Bổ sung fallback cho outer record nếu input chưa được validate.
- **Nhánh rộng đứng sau nhánh hẹp.** Điều này vừa hợp logic vừa tránh lỗi dominated.
- **`case null` là xử lý null selector; `default` không tự thay thế nó.** Có thể chủ động ghép `case null, default` nếu muốn chung một kết quả, nhưng cần document rõ việc gộp hai ý nghĩa.
- **Không thêm `default` chỉ để né lỗi compiler** khi tập subtype là sealed. Một fallback rộng che việc quên xử lý subtype mới.
- **Exhaustive không đồng nghĩa payload hợp lệ.** Compiler biết kiểu nào đã được bao phủ, không chứng minh mọi `Account.id` khác null hay mọi `Invoice.cents` dương.

Ví dụ phương thức strict:

~~~java
static Decision routeRequired(Event event) {
    java.util.Objects.requireNonNull(event, "event");

    return switch (event) {
        case Signup s -> route(s);
        case Invoice i -> route(i);
        case Logout l -> route(l);
    };
}
~~~

Phương thức này có **chính sách khác** với `route(Event event)` có `case null`: nó từ chối selector null ngay đầu vào, nhưng dùng lại logic validate bên trong cho mọi event khác null.

### Khi nào thêm `case null` là sai mục tiêu?

Nếu event là tham số bắt buộc ở API nội bộ và null chứng tỏ caller quên khởi tạo, trả `OK:"ignored"` hoặc một mã “không có việc” có thể che bug. Hãy giữ việc từ chối tường minh hoặc ánh xạ một ngoại lệ theo convention dự án.

Nếu boundary nhận dữ liệu không đáng tin cho phép request thiếu, `case null -> invalid("event")` có thể đúng, vì **lỗi dữ liệu được dự kiến** và người gọi nhận được loại kết quả có thể xử lý.

## 8. Test matrix nên có trước khi chấp nhận PR

Bài thực hành dùng ba event:

- `Signup(Account account, String source, String referral)`: account và source bắt buộc, referral tùy chọn.
- `Invoice(Account account, long cents)`: account hợp lệ, số tiền dương.
- `Logout(String sessionId)`: sessionId không null/không trắng.

Những case tối thiểu cần bao phủ:

| Nhóm | Input điển hình | Kỳ vọng |
| --- | --- | --- |
| Selector null | `route(null)` | `INVALID:event` |
| Selector strict null | `routeRequired(null)` | `NullPointerException` |
| Record hợp lệ | `Signup(Account("A1"),"web",null)` | Thành công, referral mặc định `none` |
| Optional field | Referral null hoặc trắng | Theo contract, không bị coi sai toàn bộ event |
| Record con null | `Signup(null,"web",null)` | `INVALID:account` |
| Component null | `Signup(Account(null),"web",null)` | `INVALID:accountId` |
| Component trắng | `Signup(Account(" "),"web",null)` | `INVALID:accountId` |
| Required field null | Source null | `INVALID:source` |
| Nhiều field sai | Account ID null và source rỗng | Ưu tiên `INVALID:accountId` |
| Số biên | `Invoice(Account("A2"),1)` | Thành công |
| Số không hợp lệ | Cents bằng 0 hoặc âm | `INVALID:cents` |
| Variant còn lại | `Logout(null)` | `INVALID:sessionId` |
| Selector kiểu khác | `classifyRaw(42)` | Fallback `other-type` |
| Guard false | Chuỗi trắng | Fallback `blank-text` |
| `instanceof` null | `null instanceof String` | `false` |
| Unconditional component pattern | `TypedText(String text)`, component null | Có thể khớp và `text == null` |
| Conditional component pattern | `OpenText(String text)`, component null | Không khớp |
| Thiếu `case null` | Pattern `switch` có `default` nhưng selector null | NPE như dự kiến |

### Kiểm tra hồi quy

Đừng chỉ test “không còn NPE”. Một sửa đổi có thể khiến mọi đường đi trả giá trị mặc định nhưng vẫn sai nghiệp vụ. Cần test **đúng mã lỗi, tên field và đường fallback**.

Nếu chuyển từ `if (x instanceof T)` sang pattern `switch`, kiểm tra các ca null trước và sau migration để xác định đây là **thay đổi hợp đồng có chủ đích**, không phải regression.

## 9. Chương trình Java 21 hoàn chỉnh: 29 phép kiểm tra

Chép mã sau vào **`NullChecklistDemo.java`**. Chương trình không cần thư viện ngoài JDK.

~~~java
public class NullChecklistDemo {
    sealed interface Event permits Signup, Invoice, Logout {}

    record Account(String id) {}
    record Signup(Account account, String source, String referral)
            implements Event {}
    record Invoice(Account account, long cents) implements Event {}
    record Logout(String sessionId) implements Event {}

    enum Code { OK, INVALID }
    record Decision(Code code, String detail) {}
    record TypedText(String text) {}
    record OpenText(Object text) {}

    static Decision ok(String detail) {
        return new Decision(Code.OK, detail);
    }

    static Decision invalid(String field) {
        return new Decision(Code.INVALID, field);
    }

    static boolean blank(String value) {
        return value == null || value.isBlank();
    }

    static String optionalReferral(String value) {
        return blank(value) ? "none" : value;
    }

    static Decision route(Event event) {
        return switch (event) {
            case null -> invalid("event");

            case Signup(Account(var id), var source, var referral)
                    when blank(id) -> invalid("accountId");

            case Signup(Account(var id), var source, var referral)
                    when blank(source) -> invalid("source");

            case Signup(Account(var id), var source, var referral) ->
                    ok("signup:" + id + ":" + source
                            + ":" + optionalReferral(referral));

            case Signup(var account, var source, var referral) ->
                    invalid("account");

            case Invoice(Account(var id), var cents)
                    when blank(id) -> invalid("accountId");

            case Invoice(Account(var id), var cents)
                    when cents <= 0 -> invalid("cents");

            case Invoice(Account(var id), var cents) ->
                    ok("invoice:" + id + ":" + cents);

            case Invoice(var account, var cents) ->
                    invalid("account");

            case Logout(var sid)
                    when blank(sid) -> invalid("sessionId");

            case Logout(var sid) ->
                    ok("logout:" + sid);
        };
    }

    static Decision routeRequired(Event event) {
        java.util.Objects.requireNonNull(event, "event");

        return switch (event) {
            case Signup s -> route(s);
            case Invoice i -> route(i);
            case Logout l -> route(l);
        };
    }

    static String classifyRaw(Object raw) {
        return switch (raw) {
            case null -> "missing";
            case String s when !s.isBlank() -> "text:" + s;
            case String s -> "blank-text";
            default -> "other-type";
        };
    }

    static String missingNullCase(Object raw) {
        return switch (raw) {
            case String s -> "text:" + s;
            default -> "other-type";
        };
    }

    static int passed = 0;

    static void check(String label, boolean result) {
        if (!result) throw new AssertionError(label);
        passed++;
        System.out.println("PASS " + label);
    }

    static void checkEvent(String label, Event event, Decision expected) {
        boolean same = expected.equals(route(event));
        if (event != null) {
            same &= expected.equals(routeRequired(event));
        }
        check(label, same);
    }

    static void checkRaw(String label, Object input, String expected) {
        check(label, expected.equals(classifyRaw(input)));
    }

    static void checkNpe(String label, Runnable action) {
        try {
            action.run();
            throw new AssertionError("Expected NPE: " + label);
        } catch (NullPointerException expected) {
            check(label, true);
        }
    }

    public static void main(String[] args) {
        checkEvent("missing-event",
                null, invalid("event"));

        checkEvent("signup-no-referral",
                new Signup(new Account("A1"), "web", null),
                ok("signup:A1:web:none"));
        checkEvent("signup-referral",
                new Signup(new Account("A1"), "app", "promo"),
                ok("signup:A1:app:promo"));
        checkEvent("signup-blank-referral",
                new Signup(new Account("A1"), "web", " "),
                ok("signup:A1:web:none"));
        checkEvent("signup-null-account",
                new Signup(null, "web", null),
                invalid("account"));
        checkEvent("signup-null-id",
                new Signup(new Account(null), "web", null),
                invalid("accountId"));
        checkEvent("signup-blank-id",
                new Signup(new Account(" "), "web", null),
                invalid("accountId"));
        checkEvent("signup-null-source",
                new Signup(new Account("A1"), null, null),
                invalid("source"));
        checkEvent("signup-blank-source",
                new Signup(new Account("A1"), " ", null),
                invalid("source"));
        checkEvent("signup-two-bad-fields",
                new Signup(new Account(null), "", null),
                invalid("accountId"));

        checkEvent("invoice-ok",
                new Invoice(new Account("A1"), 250),
                ok("invoice:A1:250"));
        checkEvent("invoice-minimum",
                new Invoice(new Account("A2"), 1),
                ok("invoice:A2:1"));
        checkEvent("invoice-null-account",
                new Invoice(null, 10),
                invalid("account"));
        checkEvent("invoice-null-id",
                new Invoice(new Account(null), 10),
                invalid("accountId"));
        checkEvent("invoice-blank-id",
                new Invoice(new Account(" "), 10),
                invalid("accountId"));
        checkEvent("invoice-zero",
                new Invoice(new Account("A1"), 0),
                invalid("cents"));
        checkEvent("invoice-negative",
                new Invoice(new Account("A1"), -5),
                invalid("cents"));

        checkEvent("logout-ok",
                new Logout("S1"), ok("logout:S1"));
        checkEvent("logout-null-id",
                new Logout(null), invalid("sessionId"));
        checkEvent("logout-blank-id",
                new Logout(" "), invalid("sessionId"));

        checkRaw("raw-null", null, "missing");
        checkRaw("raw-text", "hello", "text:hello");
        checkRaw("raw-blank", " ", "blank-text");
        checkRaw("raw-other", 42, "other-type");

        Object missing = null;
        check("instanceof-null-false",
                !(missing instanceof String s));

        Object typed = new TypedText(null);
        check("typed-component-null",
                typed instanceof TypedText(String text)
                        && text == null);

        Object open = new OpenText(null);
        check("open-component-null",
                !(open instanceof OpenText(String text)));

        checkNpe("required-null",
                () -> routeRequired(null));
        checkNpe("switch-default-null",
                () -> missingNullCase(null));

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

### Biên dịch và chạy

Cần JDK 21 trở lên:

~~~bash
javac --release 21 NullChecklistDemo.java
java NullChecklistDemo
~~~

**Output khi toàn bộ ca kiểm tra thành công:**

~~~text
PASS missing-event
PASS signup-no-referral
PASS signup-referral
PASS signup-blank-referral
PASS signup-null-account
PASS signup-null-id
PASS signup-blank-id
PASS signup-null-source
PASS signup-blank-source
PASS signup-two-bad-fields
PASS invoice-ok
PASS invoice-minimum
PASS invoice-null-account
PASS invoice-null-id
PASS invoice-blank-id
PASS invoice-zero
PASS invoice-negative
PASS logout-ok
PASS logout-null-id
PASS logout-blank-id
PASS raw-null
PASS raw-text
PASS raw-blank
PASS raw-other
PASS instanceof-null-false
PASS typed-component-null
PASS open-component-null
PASS required-null
PASS switch-default-null
ALL PASSED: 29
~~~

### Cách giải thích kết quả

- **20 ca event đầu:** kiểm tra selector null, payload hợp lệ và không hợp lệ, optional referral, record con null, component null/trắng và thứ tự ưu tiên lỗi. Với event khác null, hàm `checkEvent` còn so kết quả của cả `route` và `routeRequired` trên **cùng input**.
- **4 ca classifyRaw:** kiểm tra trực tiếp `case null`, String có nội dung, String trắng và kiểu khác đi vào `default`.
- **`instanceof-null-false`:** xác nhận null selector không khớp type pattern trực tiếp.
- **`typed-component-null` và `open-component-null`:** chứng minh hai dạng component pattern có ngữ nghĩa null khác nhau.
- **2 ca kiểm tra NPE:** xác nhận API strict từ chối null và pattern switch có `default` nhưng thiếu `case null` vẫn ném NPE.

Mỗi phép kiểm tra gọi `check`, sẽ ném `AssertionError` nếu kết quả sai. Vì vậy `ALL PASSED: 29` chỉ xuất hiện nếu tất cả ca đã đạt. Bộ test chứng minh **hành vi Java trong những tình huống đã nêu**, không thay thế test integration của parser/JSON hay các quy tắc nghiệp vụ đầy đủ trong hệ thống thật.

## 10. Checklist tại ranh giới DTO, parsing và domain

Không phải mọi `null` ở code Java đều đến từ cùng một nguồn. Trước khi viết pattern `switch` trong tầng domain, kiểm tra dữ liệu đã trải qua những bước nào.

~~~text
HTTP / message / file / CLI
         |
         v
Parse nguồn đầu vào
         |
         v
Phân biệt missing field, explicit null, sai kiểu, chuỗi rỗng
         |
         v
Validate và ánh xạ sang domain hoặc kết quả lỗi
         |
         v
Pattern matching trên domain subtype
         |
         v
Handler nghiệp vụ và kết quả
~~~

Đặc biệt:

- **Field vắng mặt** trong JSON và **field hiện diện với giá trị null** có thể khác nhau về hợp đồng API. Nếu parser đã quy cả hai thành Java null, `case null` không thể khôi phục thông tin này.
- **Body thiếu** và **body hợp lệ nhưng chứa field null** khác nhau. Một `case null` trên DTO chỉ bắt trường hợp object DTO không tồn tại.
- **Validation ở constructor** có thể loại dữ liệu sai trước khi pattern chạy. Nếu constructor không cho phép Account null, nhánh fallback cho Account null có thể là phòng vệ ở boundary chứ không phải đường thường xuyên của domain.
- **`Optional`** có thể diễn đạt một số giá trị có thể vắng mặt, nhưng không tự quyết định việc null là lỗi hay hợp lệ; không nên thay mọi field/parameter thành `Optional` mà không xem API contract.
- **Lỗi hạ tầng** hoặc bug khiến một biến bất ngờ null không tự trở thành lỗi input; đừng catch mọi `NullPointerException` rồi trả `INVALID`.

Reviewer nên yêu cầu chỉ rõ **điểm nào chịu trách nhiệm validate** và **sau điểm đó những invariant nào có thể được các pattern dựa vào**.

## 11. Checklist thứ tự ưu tiên lỗi và phạm vi guard

Một mẫu có nhiều điều kiện sai đồng thời cần chính sách ưu tiên:

~~~java
case Signup(Account(var id), var source, var referral)
        when blank(id) -> invalid("accountId");

case Signup(Account(var id), var source, var referral)
        when blank(source) -> invalid("source");
~~~

Nếu `id == null` và `source == ""`, nhánh đầu thắng. Đó không phải một tính chất riêng của null, mà do **thứ tự xét nhánh**. Nếu dự án cần trả **tất cả lỗi validation cùng lúc**, cách viết switch quyết định một kết quả đầu tiên như trên có thể không đáp ứng; cần bộ validator gom nhiều lỗi trước khi dispatch.

**Reviewer cần hỏi:**

1. Validation nào có độ ưu tiên cao?
2. Nếu nhiều lỗi cùng tồn tại, API trả lỗi đầu tiên hay toàn bộ danh sách?
3. Guard có phụ thuộc vào phép kiểm tra null đặt trước không?
4. Record con null khiến pattern không khớp hay guard false?
5. Có nhánh không guard bao phủ phần còn lại của subtype?
6. Có cần log/metric cho nhánh thất bại không, và log có lộ thông tin nhạy cảm không?

Không dùng các hàm có side effect trong `when` nếu chỉ cần điều kiện. Việc debug, log hoặc thay đổi thứ tự case có thể khiến side effect diễn ra khác dự kiến.

## 12. Lỗi thường gặp cần chặn trong code review

**1. Thêm `default -> success` để né null.** Trong pattern switch Java 21, `default` không tự xử lý selector null. Hơn nữa, trả success cho dữ liệu thiếu có thể che lỗi nguồn vào.

**2. Dùng `case String s when s == null` để nhận null selector.** Type pattern ở selector không khớp null; guard đó không chạy cho selector null.

**3. Cho rằng record pattern đảm bảo mọi component non-null.** `var id` và cả unconditional component pattern có thể khớp giá trị null tùy kiểu tĩnh của component.

**4. Chỉ thêm `case null` ngoài cùng rồi bỏ qua record con.** `Signup(null,...)` không đi vào `case null` khi selector `Signup` vẫn tồn tại. Phải xử lý trường `account` riêng.

**5. Đặt nhánh rộng trước nhánh guarded.** Compiler có thể báo dominated case hoặc nhánh cụ thể không còn có thể chọn. Giữ cụ thể trước, fallback sau.

**6. Viết `id.isBlank()` trước `id != null`.** Cách này có thể NPE ngay trong guard. Dùng hàm `blank` null-safe hoặc toán tử `&&`/`||` đúng thứ tự.

**7. Coi `sealed` là validation.** `sealed` giới hạn subtype; nó không bắt buộc account ID không trắng hay tiền invoice dương.

**8. Thêm `default` vào sealed switch chỉ để qua compile.** Có thể che lỗi khi thêm subtype mới. Compiler exhaustiveness là lợi ích cần tận dụng.

**9. Thay đổi chính sách null mà không đổi test và tài liệu.** Từ NPE sang `INVALID:event` là thay đổi có thể quan sát được với caller, không chỉ là sửa syntax.

**10. Bắt rộng `RuntimeException` rồi trả lỗi “thiếu dữ liệu”.** Bug, timeout, lỗi dependency và validation không phải một loại lỗi.

**11. Đồng nhất optional và required field.** `referral == null` có thể hợp lệ; `account == null` có thể sai. Cần xét từng field theo nghiệp vụ.

**12. Quên phân biệt missing và explicit null từ dữ liệu ngoài.** Cần quyết định ở tầng parsing; pattern chỉ nhìn thấy giá trị đã được chuyển thành Java object.

**13. Viết test chỉ cho happy path.** Không có ca null selector, null record con và guard false thì một refactor nhìn đúng vẫn có thể làm đổi behavior.

**14. Bỏ qua hành vi của API strict.** `routeRequired(null)` đáng ra ném exception; sửa thành một kết quả thành công có thể che bug caller.

## 13. Mẫu checklist dùng trực tiếp trong pull request

Áp dụng cho mỗi pattern `switch` hoặc `instanceof` mới:

### A. Hợp đồng dữ liệu

- [ ] Đã xác định selector có nullable không.
- [ ] Đã ghi rõ null là giá trị domain hợp lệ, dữ liệu sai hay vi phạm API.
- [ ] Đã phân biệt field optional và field required.
- [ ] Đã xác định nguồn dữ liệu và nơi thực hiện validation.
- [ ] Đã kiểm tra các invariant constructor/factory được code thực thi, không chỉ ghi comment.

### B. Tính đúng đắn của pattern

- [ ] `instanceof` trực tiếp có hành vi null đúng ý định.
- [ ] Pattern `switch` có `case null` hoặc từ chối null tường minh nếu cần.
- [ ] `default` không bị hiểu nhầm là cách mặc định bắt null.
- [ ] Record lồng có fallback nếu object con có thể null.
- [ ] Component null có guard hoặc invariant bảo vệ trước dereference.
- [ ] Nhánh có `when` đứng trước nhánh rộng hơn cùng loại.
- [ ] Mọi subtype `sealed` được bao phủ, hạn chế `default` che thiếu case.
- [ ] Thứ tự ưu tiên lỗi khi nhiều field sai đã được quyết định.

### C. Kiểm thử

- [ ] Có test selector null.
- [ ] Có test subtype bình thường cho mọi variant.
- [ ] Có test record con null.
- [ ] Có test component null và chuỗi trắng cho các field bắt buộc.
- [ ] Có test field tùy chọn null.
- [ ] Có test guard false và nhánh fallback.
- [ ] Có test kiểu không hỗ trợ nếu selector rộng.
- [ ] Có test exception của API strict, không chỉ test kết quả nullable.
- [ ] Có test đầu vào nhiều lỗi đồng thời để bảo vệ thứ tự ưu tiên.
- [ ] Với refactor code cũ, đã xác định thay đổi behavior nào là có chủ đích.

### D. Bảo trì

- [ ] Javadoc/API contract nêu rõ null policy và nguồn validation.
- [ ] Log không lộ dữ liệu nhạy cảm và không biến exception thành validation vô cớ.
- [ ] Khi thêm subtype mới, compiler/test có thể cảnh báo chỗ chưa xử lý.
- [ ] Không có catch rộng che bug hoặc lỗi hạ tầng.

## 14. Bài tập luyện checklist

**Bài 1 — thay đổi chính sách null.** Sửa `route(Event)` để từ chối null bằng `Objects.requireNonNull`. Cập nhật ca `missing-event` thành test exception và giải thích vì sao đây là thay đổi hợp đồng, không chỉ đổi một dòng.

**Bài 2 — validation ở constructor.** Thêm compact constructor cho `Signup`, `Invoice` và `Logout` để từ chối dữ liệu sai trước khi gọi `route`. Liệt kê các test trước đây trả `INVALID` nhưng giờ phải mong chờ constructor ném ngoại lệ. Chọn ranh giới phù hợp cho hệ thống thật.

**Bài 3 — biểu diễn nhiều lỗi.** Thay chiến lược “lỗi đầu tiên thắng” bằng validator gom `accountId` và `source` khi cả hai sai. Giữ nguyên null policy của selector.

**Bài 4 — bổ sung variant.** Thêm subtype `Suspend(String reason)` vào `Event`. Biên dịch lại và quan sát các `switch expression` thiếu case. Thêm test reason null/trắng.

**Bài 5 — record lồng sâu hơn.** Thay `Account(String id)` thành `Account(Profile profile)` với `Profile(String id)`. Thử ba ca: Account null, Profile null và Profile.id null; chỉ ra case nào có pattern khớp và guard có chạy hay không.

**Bài 6 — phân biệt missing/explicit null.** Mô phỏng DTO có thể cho biết field `referral` vắng mặt, explicit null hay chuỗi. Thiết kế một kiểu kết quả rõ nghĩa cho parser trước khi chuyển sang domain; giải thích vì sao `String referral` đơn thuần không đủ nếu protocol cần phân biệt ba trường hợp.

**Bài 7 — bài tập review.** Tìm lỗi trong đoạn sau:

~~~java
// Minh họa mã sai: không dùng trực tiếp trong production.
static String bad(Object raw) {
    return switch (raw) {
        case Signup(Account(var id), var source, var referral)
                when !id.isBlank() -> "accepted";
        default -> "ignored";
    };
}
~~~

Gợi ý: điều kiện `!id.isBlank()` không an toàn khi `id == null`; `default` không tự xử lý selector null; thiếu quy tắc với `source`, referral optional và account null; “ignored” có thể che dữ liệu sai. Hãy sửa theo contract rõ ràng, viết test null ở cả ba tầng rồi so với bảng quyết định đầu bài.

**Ghi nhớ:** Checklist xử lý null không kết thúc ở câu hỏi “có `case null` chưa?”. Phải xác định **null ở đâu, được phép hay không, được xử lý bởi pattern nào, guard có an toàn không, nhánh dự phòng có đúng không và test đã xác nhận đủ chưa**. Với Java 21, cách làm bền vững là kết hợp hợp đồng API rõ ràng, `sealed` để kiểm tra exhaustiveness, guard null-safe, validation cho component và ma trận kiểm thử có chủ đích.