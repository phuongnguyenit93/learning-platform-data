# Quên xử lý null khi dùng Pattern Matching trong Java 21+

## 1. Vì sao đây là lỗi thường gặp?

Pattern matching giúp Java kiểm tra kiểu và phân rã dữ liệu ngắn gọn hơn, nhưng **không tự bảo đảm mọi giá trị tham chiếu đều khác `null`**. Một lỗi thường gặp là nhìn thấy biến được khai báo qua pattern và lập tức gọi phương thức lên nó, hoặc cho rằng `default` trong `switch` sẽ xử lý cả đầu vào `null`.

Ba tình huống có hành vi khác nhau:

1. **`instanceof` với selector `null`**: biểu thức trả về `false`; thân `if` không chạy.
2. **`switch` với selector `null` và không có nhánh xử lý null phù hợp**: thông thường ném `NullPointerException`, **không** tự đi vào `default`.
3. **Giá trị component `null` bên trong record pattern**: kết quả khớp phụ thuộc vào **loại component pattern và kiểu tĩnh của component**. Đặc biệt, một pattern *unconditional* có thể nhận cả component `null`.

Sự khác biệt thứ ba rất dễ bị bỏ qua. Chẳng hạn, trên Java 21:

~~~java
record TypedText(String text) {}

Object input = new TypedText(null);
if (input instanceof TypedText(String text)) {
    System.out.println(text == null); // true
}
~~~

`TypedText(String text)` là record pattern. Component của `TypedText` vốn có kiểu tĩnh `String` nên `String text` ở vị trí này là **unconditional pattern**; nó có thể khớp dù component là `null`. Vì thế không được suy luận rằng **mọi type pattern đều loại `null` ở mọi vị trí**.

Đích của bài: phân biệt null **ở selector**, null **ở record component** và null **trong domain model**; chọn cách xử lý có chủ đích, giữ điều kiện an toàn và kiểm thử các ca biên.

Bài dùng **Java 21+** để minh họa type pattern, record pattern và pattern matching trong `switch`. Các tính năng này không cần `--enable-preview` ở JDK 21.

## 2. Null trong `instanceof`: kiểm tra kiểu không phải ép kiểu

Với type pattern thông thường:

~~~java
Object maybeName = null;

if (maybeName instanceof String name) {
    System.out.println(name.toUpperCase());
} else {
    System.out.println("not a String");
}
~~~

Kết quả:

~~~text
not a String
~~~

Giá trị ngoài cùng `null` khiến `instanceof String name` trả về `false`. Vì thân `if` chỉ chạy khi pattern khớp, biến `name` có thể được sử dụng như `String` hợp lệ trong nhánh đúng; không có chuyện Java dereference `maybeName` trước khi kiểm tra.

Điều này khác với đoạn sau:

~~~java
// KHÔNG AN TOÀN nếu maybeName == null:
String name = (String) maybeName; // Ép kiểu null có thể thành công: name vẫn null
System.out.println(name.toUpperCase()); // NullPointerException
~~~

Ép kiểu tham chiếu null sang `String` không làm giá trị trở thành chuỗi thực. Do đó, thay `instanceof` bằng cast và bỏ kiểm tra null có thể đổi hành vi hoặc gây lỗi lúc chạy.

**Ghi nhớ:** `if (obj instanceof SomeType x)` là kiểm tra kiểu phù hợp với giá trị **khác null** của selector. Nó không chứng minh các trường tham chiếu **bên trong** `obj` cũng khác null.

## 3. Null trong `switch`: `default` không thay `case null`

Xét một phương thức phân loại:

~~~java
static String unsafeSwitch(Object input) {
    return switch (input) {
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

Với `unsafeSwitch("abc")`, kết quả là `"text:abc"`. Với `unsafeSwitch(42)`, kết quả là `"other"`. Nhưng **`unsafeSwitch(null)` ném `NullPointerException`**. Trong pattern switch Java 21, `default` không phải là nhánh cho selector null.

Cách xử lý khi **null là dữ liệu được chấp nhận**:

~~~java
static String safeSwitch(Object input) {
    return switch (input) {
        case null -> "missing";
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

Lúc này `safeSwitch(null)` trả về `"missing"`. Nếu nghiệp vụ không cho phép đầu vào null, cũng có thể **từ chối tường minh**:

~~~java
static String rejectNull(Object input) {
    java.util.Objects.requireNonNull(input, "input");
    return switch (input) {
        case String text -> "text:" + text;
        default -> "other";
    };
}
~~~

Cả hai đều có chủ đích: cách thứ nhất có **nhánh xử lý null**; cách thứ hai có **hợp đồng không nhận null** và thông báo cụ thể. Tránh vô tình để exception xuất hiện chỉ vì quên ca biên.

Ngay cả khi một `switch expression` trên `sealed interface` hoặc `enum` đã xử lý hết các subtype hoặc enum constant, tính **exhaustive về các giá trị khác null** không đồng nghĩa nó tự xử lý `null`. Khi thiết kế API, luôn quyết định null là input hợp lệ, input lỗi, hay trạng thái “chưa có dữ liệu”.

## 4. Record pattern và sự khác biệt giữa hai loại component pattern

Một record có thể chứa tham chiếu null nếu không tự kiểm tra trong constructor:

~~~java
record TypedText(String text) {}
record BroadText(Object text) {}
~~~

Xét ba phép khớp:

~~~java
Object typed = new TypedText(null);
Object broad = new BroadText(null);
Object actualText = new BroadText("hello");

System.out.println(typed instanceof TypedText(String s));     // true
System.out.println(broad instanceof BroadText(String s));     // false
System.out.println(actualText instanceof BroadText(String s)); // true
~~~

**Vì sao khác nhau?**

- Trong `TypedText`, component được **khai báo kiểu `String`**. Mẫu con `String s` là *unconditional* đối với component có kiểu tĩnh ấy; nó có thể nhận giá trị `null`.
- Trong `BroadText`, component được **khai báo kiểu `Object`**. Mẫu con `String s` phải kiểm tra kiểu thực tế: `null` không phải một giá trị `String` được so khớp có điều kiện; vì vậy không khớp.
- Khi `BroadText` chứa chuỗi `"hello"`, mẫu con `String s` khớp.

Đây không phải lỗi của compiler. Đó là ngữ nghĩa pattern ở **vị trí record component**, nơi điều kiện “unconditional đối với kiểu tĩnh” có ý nghĩa.

Đối với `var`:

~~~java
Object typed = new TypedText(null);

if (typed instanceof TypedText(var text)) {
    // text có kiểu tĩnh String, nhưng giá trị có thể là null.
    System.out.println(text == null); // true
}
~~~

`var` giúp suy luận kiểu từ component; nó **không** tự thực hiện non-null validation. Nếu định gọi `text.isBlank()`, cần kiểm tra `text != null` hoặc bảo đảm qua constructor đã được thực thi.

### Record pattern lồng nhau: null ở từng tầng

~~~java
record User(String name) {}
record Transfer(User sender, String reference, int amount) {}
~~~

Hai đầu vào khác nhau:

~~~java
Object missingSender = new Transfer(null, "REF-7", 3);
Object missingName = new Transfer(new User(null), "REF-7", 3);
~~~

Với mẫu `Transfer(User(var name), var reference, var amount)`:

- `missingSender` **không** khớp mẫu lồng `User(...)` vì vị trí đó cần một đối tượng `User` thực sự, không phải null.
- `missingName` có `sender` là một `User` hợp lệ về cấu trúc; `var name` có thể nhận null từ component `name` của record.
- Nếu `reference == null`, `var reference` vẫn có thể nhận null. Pattern không tự loại giá trị thiếu này.
- Nếu một selector ngoài cùng bằng null, `instanceof Transfer(...)` vẫn trả về false.

**Quy tắc tổng quát:** hãy xác định vị trí null có thể xuất hiện, kiểu tĩnh của component và pattern con ở từng tầng. Không thể áp dụng máy móc một câu “record pattern sẽ bỏ qua tất cả null”.

## 5. Kết hợp `&&` để bảo vệ phép truy cập

Một cách đơn giản để tránh `NullPointerException` là dùng **đánh giá ngắn mạch**:

~~~java
String name = null;
boolean valid = name != null && !name.isBlank();
System.out.println(valid); // false
~~~

Java đánh giá `&&` từ trái sang phải. Khi `name != null` sai, `name.isBlank()` **không được gọi**.

**Cần tránh đảo thứ tự:**

~~~java
// Có thể ném NullPointerException khi name == null:
boolean unsafe = !name.isBlank() && name != null;
~~~

Điều tương tự áp dụng cho biến record pattern ở vế bên phải:

~~~java
Object input = new User(null);

boolean valid =
        input instanceof User(var name)
        && name != null
        && !name.isBlank();
~~~

Biến `name` được sử dụng hợp lệ ở các vế sau của `&&` vì mẫu phía trước đã khớp. Guard `name != null` cần đặt **trước** phương thức `isBlank()`. Lưu ý: `User(var name)` có thể khớp ngay cả khi tên bên trong null, nên phần kiểm tra null này không dư thừa.

Không nên thay `&&` bằng `||` một cách tùy tiện:

~~~java
// CỐ Ý SAI: nếu mẫu không khớp, vế phải vẫn có thể cần chạy,
// nhưng name chưa nằm trong phạm vi hợp lệ.
if (input instanceof User(var name) || name.isBlank()) {
    // ...
}
~~~

Đây là **đoạn cố ý không biên dịch** để minh họa *flow scoping*, không phải mã chạy trong chương trình ở mục 9. Ngoài phạm vi biến, toán tử `||` còn có ý nghĩa nghiệp vụ khác hẳn `&&`, nên không thể hoán đổi chỉ để rút ngắn câu lệnh.

## 6. Dùng `when` trong `switch` mà không dereference null

Từ Java 21, `when` là guard của pattern trong `switch`. Ví dụ:

~~~java
static String classify(Object input) {
    return switch (input) {
        case null -> "null-input";

        case Transfer(User(var name), var reference, var amount)
                when name != null && !name.isBlank()
                    && reference != null && !reference.isBlank()
                    && amount > 0 ->
                "accepted:" + name + ":" + reference;

        case Transfer(var sender, var reference, var amount) ->
                "rejected-transfer";

        case User(var name) when name != null && !name.isBlank() ->
                "user:" + name;

        case User(var name) -> "unnamed-user";

        default -> "other";
    };
}
~~~

Đây là phương thức độc lập về logic nhưng cần các `record User` và `Transfer` đã khai báo ở trên; chương trình hoàn chỉnh nằm ở mục 9.

Đọc từng nhánh:

1. `case null` xử lý **selector ngoài cùng** bằng null, không để phát sinh `NullPointerException` ngoài ý muốn.
2. Mẫu `Transfer(User(var name), ...)` kiểm tra cấu trúc ở hai tầng. Khi `sender` null, nhánh này không khớp. Khi `sender` có `User` với `name == null`, mẫu cấu trúc có thể khớp nhưng **guard** từ chối.
3. Guard `name != null && !name.isBlank()` bảo vệ lời gọi phương thức. Tương tự đối với `reference`.
4. Nhánh `case Transfer(var sender, var reference, var amount)` đứng **sau** nhánh có guard, nhận mọi `Transfer` chưa thỏa điều kiện chấp nhận, bao gồm `sender == null`.
5. Hai nhánh `User` thể hiện rằng một record `User` có tên null hoặc tên trắng vẫn là một `User` về mặt kiểu, chỉ không hợp lệ theo quy tắc gắn nhãn “có tên”.
6. `default` xử lý selector **không null** không thuộc hai loại record đang xét, ví dụ một chuỗi bình thường.

Lưu ý khi refactor: nếu chuyển nhánh `Transfer(...)` tổng quát lên trước nhánh cụ thể có `when`, nhánh cụ thể có thể bị *dominated* và Java từ chối. Thứ tự từ cụ thể đến tổng quát có vai trò về mặt kiểm tra kiểu lẫn hành vi.

`when` không thay việc bảo vệ invariant ở nơi tạo object. Nó là lớp kiểm tra tại **điểm sử dụng**, hữu ích khi đầu vào có thể là dữ liệu thô hoặc chưa được xác thực.

## 7. Giải pháp ở domain model: ngăn tạo object không hợp lệ

Nếu ứng dụng đã quyết định một `User` **không bao giờ** được phép có `name == null` hoặc tên trắng, hãy thực thi điều đó ở constructor thay vì chỉ dựa vào mọi caller nhớ kiểm tra.

~~~java
record ValidatedUser(String name) {
    ValidatedUser {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("name");
        }
    }
}
~~~

Với record này:

~~~java
ValidatedUser a = new ValidatedUser("Lan"); // Hợp lệ
// new ValidatedUser(null);                 // Ném IllegalArgumentException
// new ValidatedUser("  ");                 // Ném IllegalArgumentException
~~~

Đây là đoạn minh họa constructor validation. Khi object được tạo bằng các đường đi thông thường và invariant được duy trì, code xử lý có thể **dựa vào hợp đồng domain** thay vì kiểm tra null lặp lại ở mọi nơi.

Tuy nhiên:

- Java không mặc định coi `String` là non-null. Việc một field có kiểu `String` **không đủ** để loại null.
- Record chỉ bất biến nông (*shallow immutable*); component tham chiếu đến object mutable cần được thiết kế và bảo vệ thêm để invariant không bị phá sau constructor.
- Tại ranh giới dữ liệu ngoài (JSON, DTO, hàng database, message queue), vẫn cần một bước **validation và chuyển đổi** vào domain object hợp lệ.
- Nếu null có ý nghĩa nghiệp vụ (“chưa biết”, “không cung cấp”), có thể mô hình hóa rõ bằng một subtype, trạng thái, hoặc lựa chọn thiết kế phù hợp. Đừng cố giấu null bằng cách bỏ kiểm tra trong code xử lý.
- `Objects.requireNonNull(x, "field")` hữu ích khi muốn **từ chối null tường minh**, nhưng ném `NullPointerException` có chủ đích; nếu API dùng validation exception riêng, chọn ngoại lệ theo hợp đồng.

**Chỉ dựa vào invariant khi biết rõ nó được bảo vệ ở đâu.** Nếu không thể xác nhận nguồn bảo đảm, giữ guard tại điểm sử dụng sẽ an toàn và dễ review hơn.

## 8. Nguyên tắc xử lý null theo từng vị trí

| Vị trí giá trị null | Điều gì thường xảy ra | Giải pháp |
| --- | --- | --- |
| Selector trong `obj instanceof Type x` | Kết quả `false` | Dùng nhánh `else` hoặc quy tắc từ chối phù hợp |
| Selector trong pattern `switch` | Có thể ném `NullPointerException` khi không xử lý null | Thêm `case null` hoặc từ chối sớm bằng `requireNonNull` |
| Component tham chiếu khớp `var x` | `x` vẫn có thể nhận null | `x != null` trước khi gọi method |
| Component kiểu `String` khớp mẫu `String x` unconditional | Có thể khớp ngay cả khi null | Đừng suy luận `x != null` từ riêng cú pháp này |
| Component kiểu `Object` khớp `String x` | Mẫu có điều kiện không khớp nếu component null | Phân biệt với pattern unconditional |
| Record lồng `User(...)` nhận component sender null | Mẫu record lồng không khớp | Có nhánh dự phòng hoặc kiểm tra null theo domain |
| Guard `when x != null && x.is...()` | Dereference chỉ chạy khi khác null | Giữ thứ tự ngắn mạch |
| Kết quả trả về từ hàm có thể null | Code gọi tiếp có thể NPE | Thể hiện hợp đồng, kiểm tra, hoặc đổi mô hình kết quả |

**Đừng đánh đồng “pattern không khớp” với “dữ liệu không hợp lệ”.** Ví dụ một `Transfer` thiếu sender có thể là đối tượng không hợp lệ theo domain của bạn, nhưng về mặt Java nó vẫn có kiểu `Transfer` nếu constructor cho phép. Pattern matching không thay thế validation nghiệp vụ.

## 9. Chương trình Java 21 hoàn chỉnh: 18 ca kiểm thử

Tạo tệp **`NullPatternPitfallsDemo.java`** với mã sau. Các trường hợp null được kiểm tra như dữ liệu đầu vào thực tế; đoạn gây `NullPointerException` được bắt **chủ động để chứng minh hành vi**, không để toàn bộ chương trình dừng đột ngột.

~~~java
public class NullPatternPitfallsDemo {
    record User(String name) {}
    record Transfer(User sender, String reference, int amount) {}
    record TypedText(String text) {}
    record BroadText(Object text) {}
    record TestCase(String name, Object input, String expected) {}

    private static int passed = 0;

    static void check(String name, boolean ok) {
        if (!ok) throw new AssertionError(name);
        passed++;
        System.out.println("PASS " + name);
    }

    static String classify(Object input) {
        return switch (input) {
            case null -> "null-input";
            case Transfer(User(var name), var reference, var amount)
                    when name != null && !name.isBlank()
                        && reference != null && !reference.isBlank()
                        && amount > 0 ->
                    "accepted:" + name + ":" + reference;
            case Transfer(var sender, var reference, var amount) ->
                    "rejected-transfer";
            case User(var name) when name != null && !name.isBlank() ->
                    "user:" + name;
            case User(var name) -> "unnamed-user";
            default -> "other";
        };
    }

    static String unsafeSwitch(Object input) {
        return switch (input) {
            case String text -> "text:" + text;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        TestCase[] samples = {
            new TestCase("accepted",
                    new Transfer(new User("Lan"), "REF-7", 3),
                    "accepted:Lan:REF-7"),
            new TestCase("null-sender",
                    new Transfer(null, "REF-7", 3),
                    "rejected-transfer"),
            new TestCase("null-name",
                    new Transfer(new User(null), "REF-7", 3),
                    "rejected-transfer"),
            new TestCase("blank-name",
                    new Transfer(new User("  "), "REF-7", 3),
                    "rejected-transfer"),
            new TestCase("null-reference",
                    new Transfer(new User("Lan"), null, 3),
                    "rejected-transfer"),
            new TestCase("blank-reference",
                    new Transfer(new User("Lan"), " ", 3),
                    "rejected-transfer"),
            new TestCase("zero-amount",
                    new Transfer(new User("Lan"), "REF-7", 0),
                    "rejected-transfer"),
            new TestCase("negative-amount",
                    new Transfer(new User("Lan"), "REF-7", -2),
                    "rejected-transfer"),
            new TestCase("user-name",
                    new User("Minh"), "user:Minh"),
            new TestCase("user-null-name",
                    new User(null), "unnamed-user"),
            new TestCase("user-blank-name",
                    new User(" "), "unnamed-user"),
            new TestCase("top-level-null", null, "null-input"),
            new TestCase("other-type", "hello", "other")
        };

        for (TestCase sample : samples) {
            check(sample.name(),
                    classify(sample.input()).equals(sample.expected()));
        }

        Object missing = null;
        check("instanceof-null-is-false",
                !(missing instanceof String text));

        Object typed = new TypedText(null);
        check("unconditional-component-matches-null",
                typed instanceof TypedText(String text) && text == null);

        Object broad = new BroadText(null);
        check("conditional-component-rejects-null",
                !(broad instanceof BroadText(String text)));

        check("unsafe-switch-nonnull",
                unsafeSwitch("abc").equals("text:abc"));

        try {
            unsafeSwitch(null);
            throw new AssertionError("Expected NullPointerException");
        } catch (NullPointerException expected) {
            check("switch-default-does-not-handle-null", true);
        }

        System.out.println("ALL PASSED: " + passed);
    }
}
~~~

Chạy với **JDK 21+**:

~~~bash
javac --release 21 NullPatternPitfallsDemo.java
java NullPatternPitfallsDemo
~~~

**Kết quả chuẩn:**

~~~text
PASS accepted
PASS null-sender
PASS null-name
PASS blank-name
PASS null-reference
PASS blank-reference
PASS zero-amount
PASS negative-amount
PASS user-name
PASS user-null-name
PASS user-blank-name
PASS top-level-null
PASS other-type
PASS instanceof-null-is-false
PASS unconditional-component-matches-null
PASS conditional-component-rejects-null
PASS unsafe-switch-nonnull
PASS switch-default-does-not-handle-null
ALL PASSED: 18
~~~

### Cách hiểu các ca biên

- **`top-level-null`**: `switch` đã có `case null`, nên trả về nhãn `"null-input"` như hợp đồng.
- **`null-sender`**: mẫu lồng `User(...)` thất bại khi sender null; nhánh `Transfer(...)` rộng hơn phân loại từ chối thay vì ném ngoại lệ.
- **`null-name`, `null-reference`**: record tồn tại và các biến pattern có thể nhận null; guard `!= null` loại bỏ trước khi gọi `isBlank()`.
- **`user-null-name`**: `User` là một record tồn tại, nhưng tên của nó chưa được kiểm tra ở constructor; nhánh dự phòng xử lý tên null.
- **`unconditional-component-matches-null`**: thành phần `String text` của `TypedText` có thể khớp null trong record pattern; đây là trường hợp rất dễ bị hiểu sai.
- **`conditional-component-rejects-null`**: component được khai báo `Object` của `BroadText` không khớp `String text` nếu giá trị là null.
- **`instanceof-null-is-false`**: với selector ngoài cùng null, `instanceof` trực tiếp trả false.
- **`switch-default-does-not-handle-null`**: phương thức `unsafeSwitch(null)` ném `NullPointerException`; test bắt đúng loại exception và coi đó là hành vi được dự đoán, không phải cách xử lý null được khuyến nghị.

Hàm `check` ném `AssertionError` ngay khi kỳ vọng sai. Dòng `ALL PASSED: 18` chỉ xuất hiện khi toàn bộ phép kiểm tra hoàn tất.

## 10. Kiểm thử hồi quy: đừng chỉ thử đường đi đúng

Khi sửa mã pattern matching, lập ma trận kiểm thử theo **vị trí null**, không chỉ theo loại đối tượng:

| Ca kiểm thử | Kết quả cần xem |
| --- | --- |
| Đầu vào ngoài cùng `null` cho `instanceof` | Không khớp, không có NPE |
| Đầu vào ngoài cùng `null` cho `switch` | Đi vào `case null` hoặc từ chối theo hợp đồng |
| Record ngoài đúng kiểu nhưng record con null | Nhánh mẫu lồng không khớp; fallback xử lý đúng |
| Record con tồn tại nhưng component `String` null | Guard/invariant bảo vệ dereference |
| Record có chuỗi trắng `"  "` | Xử lý theo nghiệp vụ; phân biệt trắng với null |
| Component kiểu `Object` mang null | Không nhầm với component unconditional có kiểu `String` |
| Giá trị đúng kiểu nhưng số lượng bằng 0 hoặc âm | Guard nghiệp vụ từ chối, không liên quan đến `instanceof` |
| Loại đối tượng hoàn toàn khác | Chọn `default`/fallback thích hợp |
| Pattern switch đã exhaustive về subtype | Vẫn xét null selector riêng biệt |
| Refactor `&&` hoặc `when` | Không gọi phương thức trước điều kiện bảo vệ null |

Trong bộ test tự động, nên đặt tên rõ ràng cho từng ca. Khi nhận JSON, API hoặc DTO từ bên ngoài, thử cả thiếu field, field có giá trị null, chuỗi trắng và object lồng không tồn tại; chúng có thể đi qua những đường xử lý khác nhau.

## 11. Những lỗi cần tránh khi đọc và sửa code

**Lỗi 1 — `default` được xem là nhánh xử lý null.** Trong pattern switch, `default` không có nhiệm vụ tự bắt selector null. Thêm `case null` hoặc từ chối sớm theo hợp đồng.

**Lỗi 2 — nghĩ type pattern trong record luôn loại null.** `TypedText(String text)` với component tĩnh `String` có thể khớp null. Không gọi `text.length()` nếu thiếu null-check hoặc một invariant đáng tin cậy.

**Lỗi 3 — nghĩ `var` đồng nghĩa non-null.** `var` suy luận kiểu, không kiểm tra giá trị có khác null. Một biến pattern có kiểu tĩnh `String` vẫn có thể mang null ở các vị trí được ngữ nghĩa pattern cho phép.

**Lỗi 4 — dereference trước khi kiểm tra null.** `name.isBlank() && name != null` là thứ tự sai. `name != null && !name.isBlank()` tránh NPE bằng short-circuit.

**Lỗi 5 — xử lý record con null giống component con null.** Mẫu `User(...)` lồng yêu cầu tồn tại record `User`; một `User` tồn tại nhưng chứa `name == null` lại là tình huống khác. Nên có test riêng cho từng tầng.

**Lỗi 6 — bỏ nhánh dự phòng cho record hợp lệ về kiểu nhưng không đạt validation.** Một nhánh pattern với `when` không khớp nếu guard sai; cần quyết định giá trị đi đâu tiếp theo, nhất là trong `switch`.

**Lỗi 7 — tin rằng compiler bảo vệ invariant nghiệp vụ.** Java biết kiểu và phạm vi biến, không tự biết rằng mọi `User` được tạo ra đều có tên. Constructor/factory và validation phải định nghĩa điều kiện domain.

**Lỗi 8 — biến mọi null thành chuỗi rỗng một cách âm thầm.** `null` có thể mang nghĩa “chưa cung cấp”, “không biết” hoặc lỗi dữ liệu. Thay toàn bộ bằng `""` có thể che lỗi và làm sai dữ liệu.

**Lỗi 9 — thêm `Objects.requireNonNull` mà không xem hợp đồng.** Cách này thích hợp khi null là lỗi lập trình; không thích hợp nếu API cần trả kết quả “không tìm thấy” hoặc nhánh nghiệp vụ cho thiếu dữ liệu.

**Lỗi 10 — thay đổi record constructor nhưng không chạy lại test.** Nếu mới thêm validation cấm tên null, các test trước kia dùng `new User(null)` sẽ phải được sửa theo mô hình mới. Cần kiểm tra đồng thời nơi tạo dữ liệu và nơi dùng pattern.

## 12. Checklist code review

Trước khi duyệt một thay đổi dùng `instanceof`, record pattern hoặc pattern `switch`, hãy kiểm tra:

1. Selector có thể là `null` không? Nếu có, mã đã xử lý đúng hợp đồng?
2. Có phân biệt `instanceof` với pattern `switch` về selector null?
3. Các record component kiểu tham chiếu có thể null không, kể cả khi pattern viết `String x` hoặc `var x`?
4. Có record lồng nhau có thể null không? Mẫu không khớp sẽ đi về đâu?
5. Trong `&&`/`when`, guard `!= null` đứng trước mọi lời gọi phương thức nguy hiểm?
6. Nếu thiếu null-check, đã tìm ra **invariant được thực thi** ở constructor/factory chưa?
7. Có nhánh `case` sau mẫu guarded để xử lý dữ liệu không đáp ứng điều kiện?
8. Các thông báo và kiểu ngoại lệ khi gặp null có đúng hợp đồng API?
9. Test có đủ null ngoài cùng, null từng component, chuỗi trắng, số biên và kiểu khác?
10. Các tình huống null có được giải thích bằng comment ở chỗ thực sự khó hiểu, thay vì nhắc lại cú pháp?

### Bài tập tự luyện

- Thay `case null -> "null-input"` trong `classify` bằng việc từ chối đầu vào qua `Objects.requireNonNull`. Viết lại kỳ vọng kiểm thử theo hợp đồng mới.
- Đưa `name != null` ra khỏi guard rồi chạy lại `null-name`. Giải thích vì sao có thể ném `NullPointerException` nếu `isBlank()` được gọi với null.
- Thêm compact constructor vào `User` để từ chối tên null/trắng; cập nhật test cho đúng điểm xảy ra lỗi.
- So sánh `TypedText(String text)` với `BroadText(String text)` khi component null; giải thích vai trò của **kiểu tĩnh component**.
- Viết một `switch` trên `sealed interface` với đầy đủ subtype nhưng không có `case null`, sau đó thử selector null để xác minh rằng tính exhaustive về kiểu không tự xử lý null.

**Ghi nhớ:** Pattern matching giúp giảm ép kiểu và đọc cấu trúc dữ liệu, nhưng không phải bộ lọc null tổng quát. **`instanceof` trực tiếp với null trả false; pattern `switch` phải có cách xử lý selector null rõ ràng; record component có thể nhận null ngay cả khi biến pattern có kiểu `String`.** Kết hợp guard ngắn mạch, constructor validation và test ở từng tầng sẽ giúp tránh `NullPointerException` mà không làm mờ ý nghĩa domain.