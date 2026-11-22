# Điều kiện bảo vệ `when` và thứ tự nhãn mẫu — Java 17+

## 1. Bản chất bài học và lưu ý phiên bản

Khi dùng **pattern matching trong `switch`**, ta có thể chọn nhánh dựa trên **kiểu dữ liệu** và thêm **điều kiện bảo vệ** (*guard*) để chỉ chấp nhận mẫu thỏa ràng buộc bổ sung. Cú pháp phổ biến:

~~~java
// Java 21 trở lên: switch pattern matching ổn định.
case String text when text.length() >= 5 -> ...
~~~

Ý nghĩa: trước hết selector phải khớp mẫu `String text`; **chỉ khi đó** Java mới đánh giá `text.length() >= 5`. Nếu guard false, tiếp tục tìm nhãn case sau.

**Phân biệt phiên bản rất quan trọng:**

| JDK | Trạng thái và cú pháp |
|---|---|
| Java 17 | Pattern matching cho `instanceof` **ổn định**; pattern matching cho `switch` là **preview** (JEP 406), guard preview dùng dạng `case String s && condition`, **không có cú pháp `when`** |
| Java 21+ | Pattern matching cho `switch` **ổn định** (JEP 441); viết `case String s when condition -> ...`, không cần preview |

Vì vậy **không thể biên dịch `case ... when ...` bằng `javac --release 17`**. Bài này có hai chương trình hoàn chỉnh:

1. **JDK 17+**: dùng `instanceof` pattern kết hợp `if/else` và `&&`, biểu diễn cùng logic và kiểm chứng được trên Java 17.
2. **JDK 21+**: dùng trực tiếp `switch` với `when`, đúng cú pháp mà đề bài hỏi.

Không sử dụng cú pháp Java 21 trong đoạn mã được ghi là chạy trên JDK 17.

## 2. `when` kiểm tra điều kiện sau khi mẫu khớp

Ví dụ Java 21:

~~~java
static String classify(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isBlank() -> "BLANK";
        case String s when s.length() >= 5 -> "LONG_TEXT";
        case String s -> "SHORT_TEXT";
        default -> "OTHER";
    };
}
~~~

Luồng đối với `value = "example"`:

1. Không khớp `case null`.
2. Khớp kiểu `String` ở nhãn có `s.isBlank()`, nhưng guard false.
3. Tiếp tục nhãn kế tiếp: khớp `String` và `s.length() >= 5` true.
4. Chọn `"LONG_TEXT"`; **không xét** các nhãn phía dưới.

Nếu `value = 42`, Java không gọi `s.isBlank()` hay `s.length()`, vì mẫu `String s` không khớp. Biến mẫu `s` thuộc phạm vi của **guard** và **thân nhánh được chọn**, không tồn tại vô điều kiện cho mọi case.

~~~mermaid
flowchart TD
    A["Đánh giá selector một lần"] --> B{"Mẫu nhãn đầu khớp?"}
    B -- "Không" --> F["Thử nhãn tiếp theo"]
    B -- "Có" --> C{"Có when và guard true?"}
    C -- "Không" --> F
    C -- "Có / không có guard" --> D["Chọn nhánh và chạy thân nhánh"]
    F --> B
    D --> E["Rời switch rule/expression"]
~~~

Sơ đồ nêu nguyên tắc chung; với guard false, Java **không thực hiện thân nhánh** dù kiểu mẫu đã khớp.

## 3. `when` phải đi kèm nhãn mẫu phù hợp

Ví dụ đúng trong Java 21:

~~~java
case String text when !text.isBlank() -> "TEXT"
case Integer number when number > 0 -> "POSITIVE_INTEGER"
~~~

Các biểu thức sau `when` phải là điều kiện **`boolean`** (hoặc giá trị `Boolean` có thể được unbox), và được kiểm tra theo luật ngôn ngữ như một biểu thức điều kiện thông thường.

**Không đặt `when` lên một nhãn hằng theo cùng cách:**

~~~java
// Không phải cú pháp guarded pattern Java 21:
// case 10 when someBoolean -> "TEN";
~~~

Nếu cần kiểm tra thêm điều kiện trên giá trị 10, có thể dùng mẫu kiểu kèm guard (khi hợp ngữ cảnh), hoặc tốt hơn là dùng `if` nếu nghiệp vụ chỉ là phép so sánh một số và điều kiện phụ.

Một guard có thể kết hợp nhiều điều kiện:

~~~java
case String text when !text.isBlank()
        && text.length() <= 20 -> "VALID_TEXT"
~~~

Bên trong guard, `text` đã được biết là String **khác null**, nhưng các method trong guard vẫn có thể tạo tác dụng phụ hoặc ném ngoại lệ nếu chúng làm việc khác. Hãy ưu tiên guard ngắn, thuần túy và dễ kiểm thử.

## 4. Thứ tự nhãn mẫu ảnh hưởng đến kết quả

Hai guard có thể **cùng true** cho một giá trị. Nhánh khớp đầu tiên theo thứ tự nhãn được chọn.

~~~java
return switch (value) {
    case String s when s.startsWith("A") -> "STARTS_A";
    case String s when s.length() >= 5 -> "LONG";
    case String s -> "OTHER_STRING";
    default -> "NOT_STRING";
};
~~~

Với `"AppleTree"`, hai guard đầu đều true, nhưng kết quả là `"STARTS_A"` vì nhãn ấy đứng trước. Với `"Mexico"`, guard đầu false, guard thứ hai true, kết quả `"LONG"`.

**Lời khuyên:** sắp các điều kiện **ưu tiên cao hoặc đặc thù hơn** lên trước. Viết bảng quy tắc khi có nhiều guard giao nhau:

| Đầu vào | `startsWith("A")` | `length >= 5` | Nhãn được chọn |
|---|---|---|---|
| `"AppleTree"` | true | true | `STARTS_A` (đầu tiên) |
| `"Alex"` | true | false | `STARTS_A` |
| `"Mexico"` | false | true | `LONG` |
| `"Go"` | false | false | `OTHER_STRING` |
| `42` | Không xét guard String | Không xét | `NOT_STRING` |

Đổi thứ tự hai nhãn có guard có thể **đổi kết quả**, ngay cả khi chương trình vẫn biên dịch hợp lệ.

## 5. Dominance: compiler phát hiện nhãn bị che khuất

Một nhãn kiểu rộng không có guard có thể bao phủ hết nhãn kiểu hẹp đứng sau. Ví dụ `CharSequence` bao gồm `String`, nên thứ tự sau không biên dịch trên Java 21:

~~~java
// case CharSequence cs -> "SEQUENCE";
// case String s -> "STRING"; // Bị dominated.
~~~

Đảo thứ tự thành `case String s` rồi `case CharSequence cs` để giữ cả hai đường. Cùng kiểu mẫu, `case String s -> ...` đặt trước `case String s when s.length() >= 5 -> ...` cũng làm nhãn guarded bị che; hãy đặt nhãn có guard trước nhãn chung.

Giữa **hai guard tùy ý**, compiler thường không thể suy luận mọi quan hệ bao hàm của điều kiện. Hai guard cùng true vẫn biên dịch được và **thứ tự quyết định kết quả** như ở mục 4. Phần về coverage/exhaustiveness của chương phân tích sâu hơn nhãn bị che và trường hợp cần `default`.

## 6. Phân biệt guard false với type mismatch

Giả sử:

~~~java
return switch (value) {
    case Integer n when n < 0 -> "NEGATIVE_INT";
    case Integer n -> "OTHER_INT";
    case Number n -> "OTHER_NUMBER";
    default -> "OTHER";
};
~~~

- `Integer.valueOf(-2)`: khớp Integer, guard `n < 0` true → `NEGATIVE_INT`.
- `Integer.valueOf(0)`: khớp Integer nhưng guard false → thử nhãn Integer kế tiếp → `OTHER_INT`.
- `Double.valueOf(2.5)`: **không khớp** mẫu Integer → khớp `Number` → `OTHER_NUMBER`.
- `"Go"`: không khớp Integer/Number → `OTHER`.

Mẫu `Integer n` đã bảo đảm `n` không null và là `Integer` khi guard được xét, nên `n < 0` có thể unbox để so sánh an toàn trong trường hợp này.

**Đừng nhầm** “guard false” với “selector không đúng kiểu”: cả hai đều dẫn tới việc thử nhãn sau, nhưng việc guard có được đánh giá hay không thì khác.

## 7. `null` cần nhãn riêng hoặc guard trước switch

Với switch pattern matching Java 21, có thể dùng:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s when s.isBlank() -> "BLANK";
    case String s -> "TEXT";
    default -> "OTHER";
};
~~~

Đừng giả định `default` tự xử lý `null` theo mọi hình thức switch. Nếu switch không có nhãn xử lý null phù hợp, selector null có thể gây `NullPointerException`.

Trong Java 17 ổn định, pattern matching cho `switch` chưa là tính năng ổn định; cách dễ hiểu là kiểm tra trước bằng `if (value == null)` rồi mới dùng `instanceof`.

**Chú ý:** một mẫu kiểu `String s` thông thường không khớp null, vì vậy `s.isBlank()` không chạy cho null. Tránh đặt logic xử lý null trong thân nhánh String rồi mong nó được gọi khi selector null.

## 8. Mối liên hệ với flow scoping và `instanceof` của Java 17

Trong Java 17, pattern matching ổn định cho `instanceof` có thể biểu đạt điều kiện tương đương:

~~~java
static String classify17(Object value) {
    if (value == null) return "NULL";
    if (value instanceof String s && s.isBlank()) return "BLANK";
    if (value instanceof String s && s.length() >= 5) return "LONG_TEXT";
    if (value instanceof String s) return "SHORT_TEXT";
    return "OTHER";
}
~~~

Tại `value instanceof String s && s.length() >= 5`, vế phải `&&` chỉ chạy khi mẫu đã khớp. Đây là **flow scoping**, tức compiler chỉ cho dùng `s` tại nơi có thể chứng minh mẫu đã khớp.

Java 17 **không cần** `when` để dạy quy tắc đặt guard sau bước kiểm tra kiểu.

**Hai điểm khác nhau:**

- Chuỗi `if` có thể lặp lại phép `instanceof`; switch Java 21 diễn đạt nhiều nhãn mẫu trên cùng selector.
- Java 21 áp dụng **dominance** cho thứ tự nhãn mẫu trong switch; nếu một pattern không guard rộng đứng trước mẫu con, lỗi có thể được phát hiện ngay lúc biên dịch. Với `if`, điều kiện rộng đứng trước thường là lỗi logic không được compiler cảnh báo.

## 9. `when` khác `if` đặt bên trong case

Một nhãn có guard:

~~~java
case String s when s.length() >= 5 -> "LONG_TEXT"
~~~

chỉ được chọn khi **cả kiểu String và guard** cùng đạt.

Nhưng nếu viết:

~~~java
case String s -> {
    if (s.length() >= 5) {
        yield "LONG_TEXT";
    }
    yield "SHORT_TEXT";
}
~~~

thì **mọi String** đều chọn nhãn `case String s`; các nhãn case phía sau sẽ không có cơ hội xử lý String đó. Guard `when` vì vậy không đơn thuần là cách làm gọn một `if` nằm trong case: guard false có nghĩa là **tiếp tục thử nhãn khác**.

Dùng `when` khi việc không thỏa điều kiện cần chuyển quyền lựa chọn sang case khác. Dùng `if` trong thân case khi bạn đã chủ định chọn nhãn đó và xử lý thêm **bên trong**.

## 10. `switch` expression, statement và tính đầy đủ

Guarded patterns sử dụng được khi viết switch **expression** trả một giá trị hoặc switch **statement** thực hiện hành động, theo cú pháp phù hợp.

Switch expression Java 21 cần có nhánh để bao phủ mọi selector. Với `Object`, cách dễ hiểu là cung cấp `default` và xử lý null theo chính sách:

~~~java
String kind = switch (value) {
    case null -> "NULL";
    case String s when !s.isBlank() -> "TEXT";
    case String s -> "BLANK";
    default -> "OTHER";
};
~~~

Một guard tùy ý không thể được xem là luôn true để thay cho nhánh bao quát, vì `when` có thể false.

**Không viết `case String s when ...` sau `case String s`**, vì nhãn tổng quát không guard sẽ che nhãn có guard.

Nếu nhánh cần nhiều câu lệnh, dùng khối `-> { ... yield result; }` trong switch expression; `yield` cung cấp **giá trị của switch expression**, không thay thế `when`.

## 11. Guard có side effect: thứ tự quan sát được

Với Java 21:

~~~java
static boolean trace(String text) {
    System.out.println("guard:" + text);
    return text.length() > 2;
}

static String choose(Object value) {
    return switch (value) {
        case String s when trace(s) -> "MATCH";
        case null -> "NO_MATCH";
        default -> "NO_MATCH";
    };
}
~~~

- `choose(42)`: **không gọi** `trace`, vì mẫu String không khớp.
- `choose("Go")`: có gọi `trace("Go")`, guard false và đi tới default.
- `choose("Java")`: có gọi `trace("Java")`, guard true và trả MATCH.

Nếu nhiều nhãn có guard đều có side effect, **đổi thứ tự nhãn có thể đổi side effect và kết quả**. Vì vậy, hạn chế gọi method thay đổi trạng thái trong guard; chỉ để lại điều kiện boolean cần thiết.

Nếu guard ném ngoại lệ, đó không phải kết quả false: exception được truyền theo luồng xử lý ngoại lệ. Đừng kỳ vọng switch âm thầm thử nhãn kế tiếp sau một exception.

## 12. Chương trình chạy độc lập trên JDK 17+

File **`PatternGuardOrderDemo17.java`** dùng `instanceof` pattern và `if`; không chứa cú pháp `when`, nên **biên dịch trên Java 17 và các JDK mới hơn**.

~~~java
public final class PatternGuardOrderDemo17 {
    private PatternGuardOrderDemo17() {}

    static String describe(Object value) {
        if (value == null) return "NULL";
        if (value instanceof String s && s.isBlank()) return "BLANK";
        if (value instanceof String s && s.length() >= 5) {
            return "LONG_TEXT:" + s.strip();
        }
        if (value instanceof String s) return "TEXT:" + s;
        if (value instanceof Integer n && n < 0) return "NEGATIVE_INT";
        if (value instanceof Integer n) return "INT:" + n;
        if (value instanceof Number n) {
            return "NUMBER:" + n.getClass().getSimpleName();
        }
        return "OTHER";
    }

    static String priority(Object value) {
        if (value instanceof String s && s.startsWith("A")) {
            return "STARTS_A";
        }
        if (value instanceof String s && s.length() >= 5) return "LONG";
        if (value instanceof String) return "OTHER_STRING";
        return "NOT_STRING";
    }

    static boolean traced(String name, boolean allowed) {
        System.out.println("guard called:" + name);
        return allowed;
    }

    static String trace(Object value) {
        if (value instanceof String s && traced(s, s.length() > 2)) {
            return "MATCH";
        }
        return "NO_MATCH";
    }

    public static void main(String[] args) {
        Object[] inputs = {
            null, "   ", " example ", "Go",
            Integer.valueOf(-2), Integer.valueOf(0),
            Double.valueOf(2.5), Boolean.TRUE
        };
        for (Object value : inputs) {
            System.out.println("describe=" + describe(value));
        }

        System.out.println("priority Alex=" + priority("Alex"));
        System.out.println("priority AppleTree=" + priority("AppleTree"));
        System.out.println("priority Mexico=" + priority("Mexico"));
        System.out.println("priority Go=" + priority("Go"));
        System.out.println("priority null=" + priority(null));

        System.out.println("trace int=" + trace(7));
        System.out.println("trace Go=" + trace("Go"));
        System.out.println("trace Java=" + trace("Java"));
    }
}
~~~

**Bash (Linux/macOS), JDK 17+:**

~~~bash
javac --release 17 -encoding UTF-8 PatternGuardOrderDemo17.java
java -cp . PatternGuardOrderDemo17
~~~

**PowerShell (Windows), JDK 17+:**

~~~powershell
javac --release 17 -encoding UTF-8 .\PatternGuardOrderDemo17.java
java -cp . PatternGuardOrderDemo17
~~~

### Exact expected stdout trên JDK 17+

~~~text
describe=NULL
describe=BLANK
describe=LONG_TEXT:example
describe=TEXT:Go
describe=NEGATIVE_INT
describe=INT:0
describe=NUMBER:Double
describe=OTHER
priority Alex=STARTS_A
priority AppleTree=STARTS_A
priority Mexico=LONG
priority Go=OTHER_STRING
priority null=NOT_STRING
trace int=NO_MATCH
guard called:Go
trace Go=NO_MATCH
guard called:Java
trace Java=MATCH
~~~

**Giải thích:** `trace(7)` không gọi guard; `trace("Go")` gọi guard nhưng trả false; `trace("Java")` gọi guard và trả true. Các nhánh `if` theo thứ tự thể hiện logic tương đương các nhãn có `when` trong Java 21.

## 13. Chương trình dùng `when` thật sự trên JDK 21+

File **`PatternWhenDemo21.java`** (JDK 21 trở lên, không bật preview):

~~~java
public final class PatternWhenDemo21 {
    private PatternWhenDemo21() {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s when s.length() >= 5 -> "LONG_TEXT:" + s.strip();
            case String s -> "TEXT:" + s;
            case Integer n when n < 0 -> "NEGATIVE_INT";
            case Integer n -> "INT:" + n;
            case Number n -> "NUMBER:" + n.getClass().getSimpleName();
            default -> "OTHER";
        };
    }

    static String priority(Object value) {
        return switch (value) {
            case null -> "NOT_STRING";
            case String s when s.startsWith("A") -> "STARTS_A";
            case String s when s.length() >= 5 -> "LONG";
            case String s -> "OTHER_STRING";
            default -> "NOT_STRING";
        };
    }

    static boolean traced(String name, boolean allowed) {
        System.out.println("guard called:" + name);
        return allowed;
    }

    static String trace(Object value) {
        return switch (value) {
            case null -> "NO_MATCH";
            case String s when traced(s, s.length() > 2) -> "MATCH";
            default -> "NO_MATCH";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            null, "   ", " example ", "Go",
            Integer.valueOf(-2), Integer.valueOf(0),
            Double.valueOf(2.5), Boolean.TRUE
        };
        for (Object value : inputs) {
            System.out.println("describe=" + describe(value));
        }

        System.out.println("priority Alex=" + priority("Alex"));
        System.out.println("priority AppleTree=" + priority("AppleTree"));
        System.out.println("priority Mexico=" + priority("Mexico"));
        System.out.println("priority Go=" + priority("Go"));
        System.out.println("priority null=" + priority(null));

        System.out.println("trace int=" + trace(7));
        System.out.println("trace Go=" + trace("Go"));
        System.out.println("trace Java=" + trace("Java"));
    }
}
~~~

**Bash (Linux/macOS), JDK 21+:**

~~~bash
javac --release 21 -encoding UTF-8 PatternWhenDemo21.java
java -cp . PatternWhenDemo21
~~~

**PowerShell (Windows), JDK 21+:**

~~~powershell
javac --release 21 -encoding UTF-8 .\PatternWhenDemo21.java
java -cp . PatternWhenDemo21
~~~

**Exact expected stdout:** giống **toàn bộ 18 dòng** của ví dụ JDK 17 ở mục 12, từ `describe=NULL` đến `trace Java=MATCH`. Hai ví dụ áp dụng **cùng thứ tự quy tắc**, chỉ khác cách diễn đạt cú pháp.

**Không làm điều này:** thử biên dịch file `PatternWhenDemo21.java` với `--release 17`; compiler Java 17 không hiểu cú pháp `when` của switch pattern.

## 14. Lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách phù hợp |
|---|---|---|
| Viết `case String s when ...` và cho là Java 17 ổn định | Java 17 không hỗ trợ cú pháp đó | JDK 21+ hoặc `if` + `instanceof` Java 17 |
| Đặt nhãn `String s` không guard trước nhãn `String s when ...` | Nhãn sau bị dominated, lỗi compile | Nhãn guarded trước, nhãn chung sau |
| Đặt `CharSequence cs` trước `String s` | Nhãn String phía sau bị dominated | Mẫu cụ thể trước, mẫu rộng sau |
| Hai guard giao nhau nhưng cho rằng thứ tự không quan trọng | Kết quả đổi theo nhãn đầu tiên đúng | Đặt ưu tiên rõ ràng, test vùng giao |
| Nghĩ guard chạy cả khi mẫu không khớp | Dễ suy sai về NPE/side effect | Guard chỉ chạy sau khi mẫu khớp |
| Guard false nhưng nghĩ switch kết thúc | Bỏ mất cơ hội xét nhãn sau | Guard false → tiếp tục tìm nhãn phù hợp |
| Đặt `when` sau nhãn hằng giống guarded pattern | Cú pháp không hợp lệ | Dùng pattern hoặc `if` |
| Dùng `default` để mong nhận `null` không cần kiểm tra | Có thể NPE với selector null | Thêm `case null` trên JDK 21, hoặc null guard |
| Chỉ có các case có guard, không có nhãn bao quát | Switch expression có thể thiếu kết quả | Thêm case tổng quát/`default` |
| Đưa side effect vào guard | Thứ tự nhãn thay đổi hành vi | Dùng điều kiện thuần, tách side effect |
| Nghĩ `when` tương đương `if` bên trong nhánh đã chọn | Guard false thử case khác; if bên trong không | Chọn đúng ngữ nghĩa |
| Trộn cú pháp `case:` và `case ->` tùy tiện | Lỗi compile | Chọn một kiểu nhãn nhất quán |

## 15. Bài tập có đáp án

### Bài A — dự đoán ưu tiên guard

~~~java
// JDK 21+
String category = switch ("Apple") {
    case String s when s.startsWith("A") -> "A";
    case String s when s.length() >= 5 -> "LONG";
    default -> "OTHER";
};
System.out.println(category);
~~~

**Đáp án:** `A`. `"Apple"` thỏa cả hai điều kiện, nhưng nhãn đứng trước được chọn.

### Bài B — tìm lỗi dominance

~~~java
// JDK 21+, KHÔNG BIÊN DỊCH:
// switch (value) {
//     case Number n -> "NUMBER";
//     case Integer i -> "INTEGER";
//     default -> "OTHER";
// }
~~~

**Đáp án:** mẫu `Number n` đứng trước đã bao phủ mọi `Integer`; phải đặt `case Integer i` trước `case Number n`.

### Bài C — guard false phải làm gì?

~~~java
// JDK 21+
String result = switch ("Go") {
    case String s when s.length() >= 5 -> "LONG";
    case String s -> "SHORT";
    default -> "OTHER";
};
System.out.println(result);
~~~

**Đáp án:** `SHORT`. Mẫu String khớp ở case đầu nhưng guard false, nên Java xét tiếp case String tổng quát.

### Bài D — viết tương đương Java 17

Muốn: String blank → BLANK; String không blank → TEXT; kiểu khác → OTHER.

**Đáp án:**

~~~java
static String categorize(Object value) {
    if (value instanceof String s && s.isBlank()) return "BLANK";
    if (value instanceof String) return "TEXT";
    return "OTHER";
}
~~~

Không cần pattern switch preview trên Java 17.

### Bài E — null và guard

~~~java
// Java 21+
String label = switch ((Object) null) {
    case null -> "NULL";
    case String s when s.isBlank() -> "BLANK";
    default -> "OTHER";
};
System.out.println(label);
~~~

**Đáp án:** `NULL`. Nhãn `case null` xử lý null; guard String không được gọi.

## 16. Checklist và kết luận

- [ ] Biết `when` là guard của nhãn pattern switch ổn định từ JDK 21, **không phải cú pháp Java 17**.
- [ ] Biết Java 17 có thể dùng `instanceof` pattern kết hợp `&&` và `if` để diễn đạt cùng điều kiện.
- [ ] Hiểu guard chỉ chạy sau khi mẫu kiểu khớp; biến mẫu dùng được trong guard và nhánh.
- [ ] Hiểu guard false dẫn đến xét nhãn sau, không chạy thân nhánh hiện tại.
- [ ] Biết các nhãn có guard có thể giao nhau và nhãn khớp đầu tiên được chọn.
- [ ] Nhận diện dominance: nhãn rộng không guard trước nhãn hẹp có thể làm code không compile.
- [ ] Đặt nhãn mẫu cụ thể và guarded trước nhãn bao quát không guard.
- [ ] Xử lý null theo cách phù hợp phiên bản; không mặc định default nhận null.
- [ ] Hiểu `when` khác `if` đặt bên trong một case đã được chọn.
- [ ] Bảo đảm switch expression có nhánh bao phủ dữ liệu và kiểu kết quả phù hợp.
- [ ] Tránh side effect trong guard, test các giá trị sát ngưỡng và vùng giao nhau của điều kiện.
- [ ] Chạy `PatternGuardOrderDemo17.java` bằng JDK 17+ và `PatternWhenDemo21.java` bằng JDK 21+ rồi đối chiếu stdout.

**Kết luận:** Guard `when` cho phép bổ sung điều kiện sau một mẫu kiểu trong switch Java 21+. Khi mẫu khớp nhưng guard false, Java thử các nhãn tiếp theo; bởi vậy **thứ tự nhãn mẫu là một phần của ý nghĩa chương trình**. Mẫu tổng quát không guard có thể *dominate* nhãn hẹp hoặc guarded đặt sau và bị compiler từ chối. Trên Java 17, dùng `instanceof` pattern với `if`/`&&` để có cùng logic mà không cần preview.