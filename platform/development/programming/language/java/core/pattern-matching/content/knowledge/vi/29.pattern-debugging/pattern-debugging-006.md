# Kiểm tra null trước pattern: debugging Java Pattern Matching (Java 21)

Khi debug **`NullPointerException` (NPE)** trong mã dùng pattern matching, câu hỏi đầu tiên không phải “đã có `instanceof` chưa?” mà là: **`null` nằm ở cấp nào, phép kiểm tra nào chạy trước, và có phép truy cập nào được thực hiện trên giá trị có thể `null`?** Các tình huống dễ nhầm gồm: selector của `switch` bằng `null`; đối tượng record ngoài bằng `null`; record con bên trong bằng `null`; thành phần tham chiếu của một record khác `null` mang giá trị `null`; và guard `when` gọi phương thức trên giá trị vừa tách mà chưa kiểm tra.

Bài tập trung vào thao tác **kiểm tra `null` trước pattern** để xác định nguyên nhân lỗi, chọn thứ tự guard an toàn và giữ đúng hợp đồng nghiệp vụ.

**Môi trường:** ví dụ hoàn chỉnh dùng **JDK 21 trở lên**. `instanceof` type pattern ổn định từ Java 16 (JEP 394), record patterns và pattern matching cho `switch` ổn định từ Java 21 (JEP 440, JEP 441). Không cần `--enable-preview`.

## 1. Bảng phân biệt bốn vị trí null

Giả sử:

```java
record Text(String value) {}
record Packet(Text nested, Object payload) {}
```

| Giá trị đang xét | Pattern/biểu thức | Kết quả hoặc hành vi |
| --- | --- | --- |
| `null` | `input instanceof Text t` | `false`; không ràng buộc `t` |
| `null` | `input instanceof Text(var value)` | `false`; record ngoài không khớp |
| `new Text(null)` | `input instanceof Text(var value)` | `true`; `value == null` |
| `new Text(null)` | `input instanceof Text(String value)` | `true`; `value == null` |
| `new Packet(null, "data")` | `input instanceof Packet(Text(var x), var p)` | `false`; record con `Text` là `null` |
| `new Packet(null, "data")` | `input instanceof Packet(var nested, var p)` | `true`; `nested == null` |
| Selector `null` | `switch (input)` không có `case null` | Ném `NullPointerException` |
| Selector `null` | `switch (input)` có `case null` | Nhánh `case null` xử lý theo code |

**Điểm mấu chốt:** Pattern ở **cấp ngoài cùng** của `instanceof` không khớp một selector `null`. Nhưng **component pattern** nằm bên trong record pattern có quy tắc riêng: `var` hoặc type pattern không điều kiện với kiểu khai báo của component có thể ràng buộc giá trị `null`. `Text(String value)` khớp `new Text(null)` vì component đã khai báo kiểu `String` và `String value` là pattern không điều kiện cho kiểu đó.

Ngược lại, nếu có `record Box(Object value) {}`, thì `Box(String s)` không khớp `new Box(null)`: `String s` không phải pattern không điều kiện cho thành phần có kiểu khai báo `Object`. Khi debug, **luôn xem kiểu khai báo của component**, không chỉ nhìn kiểu ghi trong pattern.

Các đoạn minh họa ở những mục đầu dùng định nghĩa record tương ứng; chương trình độc lập ở mục 9 khai báo đầy đủ.

## 2. instanceof: kiểm tra kiểu đã bao gồm trường hợp selector null

Mẫu cũ:

```java
Object input = getInput(); // getInput() được giả định đã tồn tại.

if (input != null && input instanceof String) {
    String text = (String) input;
    System.out.println(text.length());
}
```

Có thể viết gọn bằng type pattern:

```java
if (input instanceof String text) {
    System.out.println(text.length());
}
```

Nếu `input == null`, biểu thức `input instanceof String text` trả `false`, nhánh không chạy và `text` không được ràng buộc. Không có NPE chỉ vì dùng toán tử `instanceof` trên một giá trị `null`.

**Khi nào vẫn cần kiểm tra `null` riêng?**

- Khi hệ thống phải phân biệt `null` (thiếu dữ liệu) với kiểu không phù hợp.
- Khi muốn ném exception hoặc trả thông điệp chuyên biệt cho `null`.
- Khi phải ghi log/metric riêng cho trường hợp thiếu đầu vào.
- Khi phần logic phía sau dùng một selector trong `switch` mà `null` phải được xử lý rõ ràng.

Ví dụ giữ nguyên ba nhánh khác nhau:

```java
static String explain(Object input) {
    if (input == null) {
        return "missing input";
    }
    if (input instanceof String text) {
        return "text=" + text;
    }
    return "unexpected type";
}
```

**Không nên gọi `input.getClass()` để debug trước khi biết `input != null`:** chính lời gọi `getClass()` sẽ ném NPE. Muốn ghi kiểu một cách an toàn:

```java
String kind = input == null ? "null" : input.getClass().getSimpleName();
System.out.println("type=" + kind);
```

Khi input là biểu thức có side effect, hãy đọc vào biến cục bộ **một lần** trước khi log và kiểm tra. Hai lời gọi `getInput()` liên tiếp không nhất thiết trả về cùng một đối tượng.

## 3. switch pattern matching: case null khác default

Với `instanceof`, selector `null` trả `false`. Nhưng với **pattern switch** Java 21, nếu selector là `null` mà không có nhãn xử lý `null`, `switch` mặc định **ném NPE**. Đừng suy ra rằng `default` sẽ nhận `null`.

Ví dụ có thể gây NPE:

```java
static String unsafeSwitch(Object value) {
    return switch (value) {
        case String text -> "text";
        default -> "other";
    };
}
```

`unsafeSwitch(null)` không trả `"other"` mà ném `NullPointerException`.

Cách 1 — xử lý rõ `null` trong switch:

```java
static String safeSwitch(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "text=" + text;
        default -> "other";
    };
}
```

Cách 2 — bảo vệ selector trước switch:

```java
static String checkBeforeSwitch(Object value) {
    if (value == null) {
        return "missing";
    }
    return switch (value) {
        case String text -> "text=" + text;
        default -> "other";
    };
}
```

Cả hai an toàn với `null`. Chọn cách nào tùy kiến trúc: nếu `null` là một nhánh phân loại có ý nghĩa, `case null` giúp tập trung xử lý; nếu `null` là đầu vào không hợp lệ, thường tốt hơn là từ chối trước `switch` hoặc dùng `Objects.requireNonNull(value, "value")` với thông điệp phù hợp.

**Lưu ý:** `case null` xử lý **giá trị selector** của chính switch; nó **không** tự bắt những thành phần `null` nằm bên trong record selector.

## 4. Record pattern: đối tượng ngoài null khác component null

Xét:

```java
record Text(String value) {}
Object a = null;
Object b = new Text(null);
```

Hai phép kiểm tra khác nhau:

```java
System.out.println(a instanceof Text(var value)); // false
System.out.println(b instanceof Text(var value)); // true
```

Với `b`, record `Text` tồn tại nên record pattern khớp, và `var value` nhận `null`. **Pattern khớp không đồng nghĩa biến tham chiếu tách được khác `null`.**

Ví dụ có nguy cơ NPE:

```java
if (b instanceof Text(var text)) {
    System.out.println(text.strip()); // NPE khi text == null.
}
```

Sửa bằng cách kiểm tra chính **component `text`** trước khi dereference:

```java
if (b instanceof Text(var text) && text != null) {
    System.out.println(text.strip());
}
```

Hoặc khi cần phân loại đầy đủ:

```java
if (b instanceof Text(var text)) {
    if (text == null) {
        System.out.println("value is missing");
    } else if (text.isBlank()) {
        System.out.println("value is blank");
    } else {
        System.out.println(text.strip());
    }
}
```

Kiểm tra này không lặp dư công việc của record pattern: pattern kiểm tra **cấu trúc**, còn `text != null` kiểm tra **giá trị thành phần**.

### Phân biệt String type pattern ở hai vị trí

```java
Object direct = null;
Object wrapped = new Text(null);

System.out.println(direct instanceof String s);          // false
System.out.println(wrapped instanceof Text(String text)); // true
```

Vị trí **cấp ngoài** của `String s` và vị trí **component** của `String text` tuân theo quy tắc khớp `null` khác nhau. Phần component có kiểu khai báo `String` và pattern `String text` là không điều kiện đối với kiểu đó.

Đây là nguyên nhân phổ biến khiến code vẫn đi vào một `case Text(String text)`, sau đó NPE tại `text.length()`. Khi debug, hãy xác định nơi dereference xảy ra thay vì kết luận “pattern hỏng”.

## 5. Record pattern lồng nhau: null record con làm pattern không khớp

Ví dụ:

```java
record Packet(Text nested, Object payload) {}
```

Một record ngoài có thể tồn tại nhưng thành phần record con bằng `null`:

```java
Object input = new Packet(null, "data");

if (input instanceof Packet(Text(var inner), var payload)) {
    System.out.println(inner); // Không chạy: nested == null.
}
```

Tại sao không chạy? `Packet(...)` ở cấp ngoài khớp, nhưng nested record pattern `Text(var inner)` yêu cầu thành phần `nested` là một đối tượng `Text` khác `null`.

Nếu muốn xử lý record con thiếu, **không tách tiếp bằng nested record pattern ngay**; trước tiên lấy nguyên thành phần:

```java
if (input instanceof Packet(var nested, var payload)) {
    if (nested == null) {
        System.out.println("missing nested Text");
    } else {
        System.out.println("nested Text is present");
    }
}
```

Trường hợp khác: `new Packet(new Text(null), "data")` có record `nested` khác `null`, nên `Packet(Text(var inner), var payload)` **khớp**; nhưng `inner == null`. Đây là hai cấp null khác nhau:

| Input | Nested record pattern `Packet(Text(var inner), var p)` | Kết luận |
| --- | --- | --- |
| `new Packet(null, "data")` | Không khớp | Thiếu record con `Text` |
| `new Packet(new Text(null), "data")` | Khớp | Record `Text` tồn tại, `inner == null` |
| `new Packet(new Text("OK"), null)` | Khớp | Record con hợp lệ; `payload == null` vẫn có thể nhận qua `var p` |

**Kỹ thuật debug:** đi từ ngoài vào trong, ghi nhận cho từng cấp: đối tượng có tồn tại không, kiểu runtime có đúng không, thành phần nào có thể null, và guard nào thực sự chạy.

## 6. Thứ tự case null và guard when để tránh NPE

Ta có thể phân biệt selector null, thành phần null, chuỗi blank và chuỗi có nội dung bằng pattern switch:

```java
static String classifyText(Object input) {
    return switch (input) {
        case null -> "NULL_SELECTOR";
        case Text(String text) when text == null -> "NULL_TEXT_COMPONENT";
        case Text(String text) when text.isBlank() -> "BLANK_TEXT";
        case Text(var text) -> "TEXT=" + text;
        default -> "OTHER";
    };
}
```

Thứ tự có ý nghĩa:

1. `case null` bắt selector null; không gọi bất kỳ accessor nào.
2. `case Text(String text) when text == null` bắt record `Text` tồn tại nhưng component null.
3. `case Text(String text) when text.isBlank()` chỉ gọi `isBlank()` sau khi nhánh null-component trước đó đã xử lý trường hợp null.
4. `case Text(var text)` bắt mọi `Text` còn lại; nhánh rộng phải đứng **sau** nhánh chuyên biệt.
5. `default` dành cho kiểu input khác.

**Không được đảo hai guard đầu** nếu guard đầu gọi phương thức trên giá trị có thể null:

```java
// Đoạn này CÓ THỂ NÉM NPE với new Text(null):
// case Text(String text) when text.isBlank() -> "BLANK_TEXT";
// case Text(String text) when text == null -> "NULL_TEXT_COMPONENT";
```

Compiler kiểm tra pattern có ràng buộc biến hợp lệ hay không; compiler **không** mặc định chứng minh `text` khác null chỉ vì pattern đã khớp thành phần. Mọi phép gọi trên `text` vẫn chịu nguy cơ NPE như biến tham chiếu bình thường.

Đối với nhiều `case` có cùng record pattern, luôn đặt **guard chuyên biệt trước case rộng không có guard**. Nếu case rộng ở trước, compiler có thể báo lỗi *dominated case*. Nếu guard chuyên biệt ở trước nhưng dereference chưa an toàn, compiler có thể cho biên dịch và lỗi chỉ phát sinh khi chạy.

## 7. Guard trong if: && giúp kiểm tra null đúng thứ tự

Mẫu an toàn với short-circuit:

```java
static String safeNonBlank(Object input) {
    if (input instanceof Text(var text)
            && text != null
            && !text.isBlank()) {
        return "NON_BLANK=" + text.strip();
    }
    return "OTHER_OR_BLANK";
}
```

Các giá trị được thử theo thứ tự:

- `input == null`: `instanceof` sai; bỏ qua cả `text != null` và `isBlank()`.
- `input` sai kiểu: cũng dừng trước khi đánh giá các vế sau.
- `input == new Text(null)`: record pattern khớp nhưng `text != null` sai; `isBlank()` **không chạy**, nên an toàn.
- `input == new Text("  hello  ")`: cả ba điều kiện đúng; trả `NON_BLANK=hello`.

Đừng đảo thứ tự thành `!text.isBlank() && text != null`, vì `isBlank()` có thể được gọi trước khi null check.

### Phủ định và early return

Có thể viết rõ từng bước khi đang debug:

```java
static String process(Object input) {
    if (!(input instanceof Text box)) {
        return "not a Text";
    }
    String text = box.value();
    if (text == null) {
        return "missing value";
    }
    return text.strip();
}
```

Sau guard phủ định có `return`, `box` được đảm bảo đã khớp và dùng được. Nhưng `box.value()` có thể null, nên check tiếp vẫn cần thiết.

Tránh nhầm **flow scoping** với **null safety**: compiler chứng minh biến pattern đã được ràng buộc không có nghĩa mọi thành phần tham chiếu đều khác null.

## 8. Quy trình debug từng bước khi gặp NullPointerException

Khi gặp NPE gần một pattern, kiểm tra theo thứ tự sau.

1. **Xác định chính xác dòng ném NPE.** Đọc stack trace và stack frame đầu tiên thuộc code ứng dụng. NPE có thể xảy ra tại `switch (selector)`, tại guard `when` hoặc tại phép gọi như `text.strip()` trong case body; các nguyên nhân khác nhau.
2. **Giữ nguyên biểu thức đầu vào một lần.** Nếu selector là `getInput()`, cân nhắc `Object snapshot = getInput();` để log và phân loại cùng một giá trị. Tránh gọi lại getter có thể thay đổi trạng thái.
3. **Kiểm tra selector trước.** Ghi `snapshot == null`. Nếu `switch` không có `case null`, đây có thể là nguyên nhân trực tiếp.
4. **Kiểm tra kiểu ngoài.** Với `instanceof`, selector null/sai kiểu đơn thuần làm điều kiện sai; nếu là `switch`, kiểm tra loại selector đã được case nào xử lý.
5. **Kiểm tra từng thành phần record.** Phân biệt record con null và trường dữ liệu của record con null; kiểm tra giá trị tham chiếu trước khi gọi phương thức.
6. **Theo dõi thứ tự guards.** Xem guard nào có thể nhận một biến null từ pattern không điều kiện, hoặc dùng biến khi `&&`/`||` đánh giá chưa bảo đảm.
7. **Tạo test tái hiện nhỏ nhất.** Thử selector null, record ngoài null, component null, nested record null, giá trị blank và giá trị hợp lệ. Mỗi ca phải có kết quả kỳ vọng độc lập.
8. **Chọn chính sách sửa lỗi.** Trả nhánh thiếu dữ liệu, từ chối bằng exception có thông điệp, hay áp dụng giá trị mặc định? Phải tuân theo contract nghiệp vụ, không chỉ “bịt” NPE.
9. **Chạy regression tests.** Sau sửa, đảm bảo dữ liệu hợp lệ vẫn đi đúng case, null không rơi vào nhánh sai và không xuất hiện dominated case hoặc thiếu exhaustiveness.

### Ghi log có kiểm soát

Ví dụ cần ghi loại selector:

```java
Object snapshot = obtainInput(); // Minh họa; obtainInput() cần được định nghĩa.
String typeName = snapshot == null
        ? "<null>"
        : snapshot.getClass().getSimpleName();
System.out.println("selectorType=" + typeName);
```

Đây chỉ là **mẫu minh họa**, không phải chương trình độc lập. Trong ứng dụng thật, tránh log dữ liệu cá nhân hoặc toàn bộ nội dung payload nhạy cảm. Chỉ ghi mã trường hợp/kiểu cần thiết để chẩn đoán, kèm correlation id phù hợp.

**Không dùng `catch (NullPointerException e)` như phương pháp xử lý null mặc định** nếu biết rõ field nào cần kiểm tra: bắt NPE rộng có thể che lỗi lập trình khác. Trong mã nghiệp vụ, ưu tiên null guard rõ ràng và test để giữ đúng ngữ nghĩa.

## 9. Chương trình Java 21 hoàn chỉnh đã kiểm chứng

Lưu nguyên nội dung thành tệp **`NullPatternDebugDemo.java`**:

```java
public class NullPatternDebugDemo {
    sealed interface Input permits Text, Count, Packet {}
    record Text(String value) implements Input {}
    record Count(int value) implements Input {}
    record Packet(Text nested, Object payload) implements Input {}
    record Check(String name, Input input, String expected) {}

    static String classify(Input input) {
        return switch (input) {
            case null -> "NULL_SELECTOR";
            case Text(String value) when value == null -> "NULL_TEXT_COMPONENT";
            case Text(String value) when value.isBlank() -> "BLANK_TEXT";
            case Text(var value) -> "TEXT=" + value;
            case Count(int n) when n == 0 -> "ZERO";
            case Count(int n) -> "COUNT=" + n;
            case Packet(Text(String inner), var payload) when inner == null ->
                    "NULL_NESTED_COMPONENT";
            case Packet(Text(var inner), var payload) -> "NESTED_TEXT=" + inner;
            case Packet(var nested, var payload) -> "NULL_NESTED_RECORD";
        };
    }

    static String classifyUsingIf(Input input) {
        if (input == null) return "NULL_SELECTOR";
        if (input instanceof Text(var value)) {
            if (value == null) return "NULL_TEXT_COMPONENT";
            if (value.isBlank()) return "BLANK_TEXT";
            return "TEXT=" + value;
        }
        if (input instanceof Count(int n)) {
            if (n == 0) return "ZERO";
            return "COUNT=" + n;
        }
        if (input instanceof Packet(Text(var inner), var payload)) {
            if (inner == null) return "NULL_NESTED_COMPONENT";
            return "NESTED_TEXT=" + inner;
        }
        if (input instanceof Packet(var nested, var payload)) {
            return "NULL_NESTED_RECORD";
        }
        throw new IllegalStateException("Unexpected subtype");
    }

    static String withoutNullCase(Input input) {
        return switch (input) {
            case Text(var value) -> "text";
            case Count(var n) -> "count";
            case Packet(var nested, var payload) -> "packet";
        };
    }

    static String unsafeComponentRead(Object value) {
        if (value instanceof Text(var text)) {
            return text.strip();
        }
        return "OTHER";
    }

    static String safeNonBlank(Object value) {
        if (value instanceof Text(var text)
                && text != null
                && !text.isBlank()) {
            return "NON_BLANK=" + text.strip();
        }
        return "OTHER_OR_BLANK";
    }

    static void assertEquals(String name, String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + ": expected " + expected + ", got " + actual);
        }
    }

    public static void main(String[] args) {
        Check[] tests = {
            new Check("selector-null", null, "NULL_SELECTOR"),
            new Check("text-component-null", new Text(null), "NULL_TEXT_COMPONENT"),
            new Check("text-empty", new Text(""), "BLANK_TEXT"),
            new Check("text-spaces", new Text("  "), "BLANK_TEXT"),
            new Check("text-value", new Text("Java"), "TEXT=Java"),
            new Check("count-zero", new Count(0), "ZERO"),
            new Check("count-negative", new Count(-1), "COUNT=-1"),
            new Check("packet-nested-null", new Packet(null, "data"), "NULL_NESTED_RECORD"),
            new Check("packet-inner-null", new Packet(new Text(null), "data"), "NULL_NESTED_COMPONENT"),
            new Check("packet-normal", new Packet(new Text("OK"), null), "NESTED_TEXT=OK")
        };

        for (Check test : tests) {
            assertEquals(test.name(), test.expected(), classify(test.input()));
            assertEquals("if-" + test.name(), test.expected(), classifyUsingIf(test.input()));
        }
        System.out.println("PASS cases=" + tests.length);
        System.out.println("PASS switch-if-agreement=" + tests.length);
        System.out.println("instanceof-null=" + (null instanceof Text));
        Object box = new Text(null);
        System.out.println("record-pattern-null-component="
                + (box instanceof Text(String value)));
        System.out.println("safe-guard=" + safeNonBlank(box));
        System.out.println("safe-value=" + safeNonBlank(new Text("  hello  ")));

        try {
            withoutNullCase(null);
            throw new AssertionError("Expected NPE for switch null");
        } catch (NullPointerException expected) {
            System.out.println("switch-without-case-null=NPE");
        }
        try {
            unsafeComponentRead(box);
            throw new AssertionError("Expected NPE for null component");
        } catch (NullPointerException expected) {
            System.out.println("unsafe-component-read=NPE");
        }
    }
}
```

Biên dịch và chạy bằng **JDK 21 trở lên**:

```bash
javac --release 21 -encoding UTF-8 NullPatternDebugDemo.java
java NullPatternDebugDemo
```

**Stdout chính xác:**

```text
PASS cases=10
PASS switch-if-agreement=10
instanceof-null=false
record-pattern-null-component=true
safe-guard=OTHER_OR_BLANK
safe-value=NON_BLANK=hello
switch-without-case-null=NPE
unsafe-component-read=NPE
```

Các kết quả có thể diễn giải như sau:

1. **`PASS cases=10`**: bảng gồm 10 input (selector null, component null, blank, số và nested null) đều đạt kết quả kỳ vọng bằng kiểm tra `assertEquals`.
2. **`PASS switch-if-agreement=10`**: trên cùng 10 input, cách phân loại bằng `switch` và bằng `if` cho kết quả trùng với oracle của từng case, không chỉ so sánh hai implementation với nhau.
3. **`instanceof-null=false`**: `null` không khớp type pattern ngoài.
4. **`record-pattern-null-component=true`**: `new Text(null)` vẫn khớp `Text(String value)` do component pattern không điều kiện đối với kiểu đã khai báo.
5. **`safe-guard=OTHER_OR_BLANK`**: `Text(null)` bị loại tại `text != null`, không gọi `isBlank()`.
6. **`safe-value=NON_BLANK=hello`**: chuỗi hợp lệ đi qua cả ba điều kiện `&&` và được `strip()`.
7. **`switch-without-case-null=NPE`**: có `switch expression` exhaustive với các subtype của `Input` nhưng vẫn ném NPE vì thiếu `case null`.
8. **`unsafe-component-read=NPE`**: pattern đã khớp `Text` nhưng `text.strip()` dereference một component null.

Chương trình **cố ý bắt hai NPE** ở cuối để chứng minh sự khác biệt giữa nguyên nhân do selector null và do component null; đây không phải khuyến nghị bắt NPE rộng trong code sản phẩm. Kết quả chạy thực tế gồm đúng tám dòng như trên.

## 10. Nên chọn null guard hay bất biến trong model?

Có hai cách thiết kế khác nhau tùy nghiệp vụ.

### Chấp nhận component có thể null

Nếu `new Text(null)` là trạng thái hợp lệ (ví dụ dữ liệu chưa điền), model có thể giữ `Text(String value)` và logic phân loại cần các nhánh `value == null` như mục 9. Test phải bao gồm cả selector null lẫn component null.

### Cấm component null ngay từ constructor

Nếu dữ liệu text bắt buộc phải tồn tại, định nghĩa record theo hướng *fail fast*:

```java
record RequiredText(String value) {
    RequiredText {
        java.util.Objects.requireNonNull(value, "value");
    }
}
```

Khi đó `new RequiredText(null)` ném NPE có thông điệp `"value"` ngay tại lúc tạo đối tượng; logic xử lý về sau có thể dựa vào invariant của model. Tuy nhiên, nếu một phần hệ thống đã cho phép null như dữ liệu nghiệp vụ, áp dụng `requireNonNull` có thể đổi contract, nên cần xem lại yêu cầu và kiểm thử trước khi refactor.

**Không nên che dữ liệu thiếu bằng chuỗi rỗng một cách tự động**: `null` (không biết/chưa có), `""` (chuỗi rỗng) và `"   "` (toàn whitespace) có thể mang ý nghĩa nghiệp vụ khác nhau.

## 11. Lỗi thường gặp khi debugging null và pattern

1. **Thêm `input != null` ở mọi `instanceof` mà không xem mục đích.** Type pattern ngoài vốn không khớp null. Null guard riêng chỉ cần khi có hành vi nghiệp vụ khác.
2. **Mong `default` của switch bắt selector null.** Pattern switch Java 21 mặc định ném NPE nếu selector null và không có `case null`.
3. **Cho rằng `case null` bảo vệ mọi record component.** Nó chỉ xử lý selector của chính `switch`, không xử lý field bên trong.
4. **Cho rằng record pattern khớp thì component cũng khác null.** `Text(String value)` có thể khớp `Text(null)`; giá trị `value` vẫn null.
5. **Dùng nested record pattern rồi bỏ sót nhánh con null.** `Packet(Text(var x), var p)` không khớp nếu `nested == null`. Dùng `Packet(var nested, var p)` khi cần kiểm tra riêng.
6. **Viết guard gọi phương thức trước null check.** `text.isBlank()` có thể ném NPE trước khi guard `text == null` ở case tiếp theo được xét.
7. **Nhầm `&&` với `||`.** `text != null && text.isBlank()` an toàn theo thứ tự, còn `text != null || text.isBlank()` có thể gọi `isBlank()` khi text null.
8. **Đặt case tổng quát trước case đặc biệt.** `case Text(var value)` không guard ở đầu nhóm có thể che các nhánh `Text(...) when ...` sau đó và gây lỗi dominated case lúc biên dịch.
9. **Dùng `getClass()`/`toString()` trên input chưa được kiểm tra.** Lời gọi phương thức trên null có thể tạo NPE ngay trong code debug.
10. **Gộp record ngoài null, record con null và component null thành một test.** Chúng là những đường đi riêng, cần oracle và mô tả lỗi riêng.
11. **Bắt mọi NPE để “sửa” vấn đề.** Điều đó có thể che bug khác. Ưu tiên xác định chính xác phép dereference cần bảo vệ hoặc áp dụng invariant.
12. **Chỉ sửa để hết exception mà không test happy path.** Một null guard quá rộng có thể làm mất các nhánh hợp lệ. Hãy chạy test cả giá trị null, blank và có nội dung.
13. **Đổi contract khi thêm `requireNonNull` vào constructor.** Chặn null có thể đúng với model mới nhưng làm thay đổi dữ liệu hợp lệ trong hệ thống hiện hữu.
14. **Chạy ví dụ record pattern dưới JDK 17.** Các record patterns và `switch` có pattern trong bài yêu cầu Java 21 trở lên.

## 12. Bài tập tự kiểm tra

**Câu 1.** `Object value = null;`. Hai phép kiểm tra dưới đây cho kết quả gì?

```java
value instanceof Text t
value instanceof Text(var inner)
```

*Đáp án:* Cả hai đều `false` vì giá trị **đối tượng ngoài** bằng `null`.

**Câu 2.** `Object value = new Text(null);`. Vì sao `value instanceof Text(String inner)` có thể khớp, nhưng `inner.strip()` vẫn có thể ném NPE?

*Đáp án:* `String inner` là component type pattern không điều kiện với trường `String value`, nên nó có thể nhận null; phép gọi `strip()` trên biến đã ràng buộc nhưng đang null gây NPE.

**Câu 3.** `new Packet(null, "data")` có khớp `Packet(Text(var x), var p)` không? Nên dùng pattern nào để kiểm tra thiếu record con?

*Đáp án:* Không. Nested record pattern `Text(...)` không khớp record con null. Dùng `Packet(var nested, var p)` rồi kiểm tra `nested == null`.

**Câu 4.** Vì sao thêm `default -> "other"` không phải cách chắc chắn xử lý selector null trong Java 21 pattern switch?

*Đáp án:* Với selector null, pattern switch mặc định ném NPE nếu không có `case null`. Cần chủ động xử lý `null` ở trước switch hoặc dùng nhãn `case null`.

**Câu 5.** Đâu là thứ tự an toàn khi phân loại `Text` bằng `when`: kiểm tra `text.isBlank()` trước hay `text == null` trước?

*Đáp án:* Kiểm tra `text == null` trước, vì component của `Text` có thể null. Khi nhánh null đã được xử lý, guard `isBlank()` mới an toàn.

**Câu 6.** Nếu domain cấm `Text.value == null`, cách sửa nên nằm ở đâu để không lặp guard trong mọi service?

*Đáp án:* Có thể đặt `Objects.requireNonNull(value, "value")` trong constructor record và bổ sung test constructor từ chối null. Nhưng phải xác nhận điều đó phù hợp contract nghiệp vụ, vì nó thay đổi tập input hợp lệ.

**Tham khảo chính thức:** [JEP 394 – Pattern Matching for instanceof](https://openjdk.org/jeps/394), [JEP 440 – Record Patterns](https://openjdk.org/jeps/440), [JEP 441 – Pattern Matching for switch](https://openjdk.org/jeps/441), [Oracle Java 21 – Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html), [Oracle Java 21 – Record Patterns](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html), [JLS Java 21 – Patterns `14.30](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30).
