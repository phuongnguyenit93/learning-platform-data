# null case trong pattern switch (Java 21)

**Phạm vi:** xử lý giá trị `null` khi dùng `switch` có pattern trong Java, đặc biệt cú pháp ổn định từ **Java 21** (*pattern matching for switch*, JEP 441). Bài giải thích `case null`, `default`, `case null, default`, kiểu tham chiếu, tính bao phủ (*exhaustiveness*), guard `when` và sự khác biệt giữa `null` của đối tượng được `switch` kiểm tra với `null` nằm bên trong một record.

Trong Java, một biểu thức kiểu tham chiếu có thể mang giá trị `null`. Khi dùng `switch` để phân loại dữ liệu từ `Object`, API hoặc mô hình dữ liệu, phải xác định rõ: **`null` có phải một trường hợp hợp lệ cần xử lý hay là lỗi đầu vào phải được báo ra?** Cú pháp `case null` cho phép đưa quyết định ấy ngay vào `switch`.

## 1. Vì sao `case null` cần thiết?

Xét cách xử lý dữ liệu với `switch` expression:

```java
static String classify(Object value) {
    return switch (value) {
        case String text -> "Text: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
```

Với `classify("Java")`, kết quả là `"Text: Java"`. Với `classify(12)`, kết quả là `"Integer: 12"`. Nhưng gọi **`classify(null)`** sẽ ném **`NullPointerException`**.

Điều gây nhầm lẫn là chương trình đã có `default`. Trong Java 21, **`default` đơn lẻ không xử lý selector có giá trị `null`**. Khi giá trị dùng làm selector là `null`, Java tìm nhãn `case null`; nếu không có nhãn ấy, `switch` kết thúc bất thường với `NullPointerException`. Java không tự coi `null` là “giá trị còn lại” để chuyển xuống `default`.

Giải pháp nếu `null` được phép:

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "No value";
        case String text -> "Text: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
```

Lúc này:

| Đầu vào | Kết quả |
| --- | --- |
| `null` | `No value` |
| `"Java"` | `Text: Java` |
| `12` | `Integer: 12` |
| `3.5` | `Other` |

`case null` là một **switch label** có cú pháp riêng theo JLS `14.11.1; nó **không phải** một type pattern hoặc record pattern, và cũng không khai báo pattern variable.

## 2. Ba nhãn cần phân biệt: `case null`, `default`, `case null, default`

### 2.1. `case null`: chỉ selector `null`

```java
static String nullFirst(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s -> "STRING";
        default -> "OTHER";
    };
}
```

- `nullFirst(null)` → `"NULL"`.
- `nullFirst("abc")` → `"STRING"`.
- `nullFirst(123)` → `"OTHER"`.

Với một selector `null`, Java chọn nhãn `case null`. Không cần kiểm tra `value == null` ở ngoài trước khi vào `switch`.

### 2.2. `default`: nhánh còn lại cho giá trị khác `null`

```java
static String withoutNullCase(Object value) {
    return switch (value) {
        case String s -> "STRING";
        default -> "OTHER";
    };
}
```

`withoutNullCase(123)` trả `"OTHER"`, nhưng `withoutNullCase(null)` ném `NullPointerException`. `default` giúp cấu trúc bao phủ những giá trị **khác null** không khớp nhãn nào trước đó; nó không ngầm thay thế `case null`.

### 2.3. `case null, default`: gộp `null` và nhánh còn lại

Java 21 cho phép cú pháp đặc biệt **`case null, default`** trong **một nhãn**:

```java
static String groupRemainder(Object value) {
    return switch (value) {
        case String s -> "STRING: " + s;
        case null, default -> "MISSING OR OTHER";
    };
}
```

- `groupRemainder("A")` → `"STRING: A"`.
- `groupRemainder(null)` → `"MISSING OR OTHER"`.
- `groupRemainder(9)` → `"MISSING OR OTHER"`.

Cú pháp này rất hữu ích nếu `null` và những kiểu chưa nhận diện **thật sự cần xử lý giống nhau**. Nếu muốn phân biệt giá trị thiếu với giá trị không hợp lệ, nên tách `case null` và `default` thành hai nhánh.

Đây là hình thức được đặc tả riêng: **`case null, default` không phải danh sách hai pattern**. Theo Java 21, không thể tổng quát hóa nó thành `case null, String s` hoặc `case String s, default`.

### Bảng quyết định

| Nhãn | Nhận `null`? | Nhận một giá trị khác `null`? | Thường dùng khi |
| --- | --- | --- | --- |
| `case null` | Có | Không | Thiếu dữ liệu cần thông điệp riêng |
| `default` | Không | Có, nếu các nhãn khác không áp dụng | Giá trị không khớp các nhánh cụ thể |
| `case null, default` | Có | Có, nếu chưa được nhánh trước xử lý | Thiếu dữ liệu và giá trị lạ dùng chung một xử lý |
| `case String s` | Không | Có, khi đối tượng là `String` | Cần phân loại và dùng biến kiểu `String` |
| `case Object o` | Không | Có, với mọi đối tượng `Object` khác null | Nhánh khớp toàn bộ giá trị tham chiếu khác null |

## 3. Java chọn nhánh như thế nào khi selector là `null`?

Theo JLS Java SE 21 `14.11.1.2, trình tự khái quát:

1. Đánh giá selector expression **một lần**.
2. Nếu kết quả là **`null`**, nhãn `case null` (hoặc `case null, default`) áp dụng khi có mặt; nếu không có nhãn xử lý `null`, `switch` ném `NullPointerException`.
3. Nếu kết quả **khác `null`**, Java xét các nhãn thích hợp (hằng số hoặc pattern và guard) theo quy tắc lựa chọn nhánh.
4. `default` được xét khi không có nhãn áp dụng cho giá trị khác `null`, còn `case null, default` có thể đóng vai trò nhánh tổng hợp.

Một điểm cần nhấn mạnh: **mẫu kiểu tổng quát không cứu được `null`**:

```java
static String universalNonNull(Object value) {
    return switch (value) {
        case Object obj -> "non-null";
    };
}
```

`case Object obj` là pattern bao phủ mọi giá trị **khác null** có kiểu phù hợp với `Object`. Tuy nhiên:

- `universalNonNull("hello")` → `"non-null"`.
- `universalNonNull(null)` → **`NullPointerException`**.

Ngay cả một `case Object obj` không có guard cũng không nhận `null`. Tính bao phủ của pattern không đồng nghĩa với việc nó xử lý null selector.

## 4. `case null` và tính exhaustiveness: hai câu hỏi khác nhau

Một **`switch` expression** phải *exhaustive*: các nhãn phải bao phủ những giá trị mà Java yêu cầu theo quy tắc tĩnh. Một **enhanced `switch` statement** có pattern hoặc `case null` cũng phải exhaustive theo Java 21.

Nhưng **“exhaustive” không đồng nghĩa “không bao giờ ném `NullPointerException`”**. Ví dụ:

```java
static int stringLength(String value) {
    return switch (value) {
        case String s -> s.length();
    };
}
```

Đây là `switch` expression hợp lệ trong Java 21: với selector kiểu `String`, type pattern `String s` bao phủ các giá trị **khác null**. Nó vẫn ném `NullPointerException` nếu `value == null`.

Muốn xử lý cả null:

```java
static int safeStringLength(String value) {
    return switch (value) {
        case null -> 0;
        case String s -> s.length();
    };
}
```

`safeStringLength(null)` trả `0`; `safeStringLength("Java")` trả `4`. Không cần `default` khi tập nhãn đã exhaustive. Thậm chí thêm `default` sau một pattern tổng quát, không có guard, đã bao phủ tất cả giá trị khác null có thể gây lỗi biên dịch do quy tắc dominance; thêm `case null` là cách rõ ràng để xử lý null.

Ở chiều ngược lại, **chỉ có `case null`** không đủ cho `switch` expression có selector kiểu `Object` vì những giá trị khác null vẫn chưa được bao phủ. Cần thêm pattern thích hợp hoặc `default`.

## 5. Tại sao `case null` không phải type pattern, record pattern hay guard?

Trong Java 21, JLS phân biệt rõ:

- **Type pattern** như `String s` khớp giá trị thuộc kiểu `String` và khởi tạo biến `s`.
- **Record pattern** như `Point(int x, int y)` khớp đối tượng record phù hợp và phân rã các component.
- **`case null`** là nhãn có literal `null`, **không** phải pattern khai báo biến.
- **`when`** là guard chỉ đặt sau một **case pattern** hợp lệ, để kiểm tra điều kiện bổ sung khi pattern đã khớp.

Ví dụ:

```java
static String inspect(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s when s.isBlank() -> "blank";
        case String s -> "text: " + s;
        default -> "other";
    };
}
```

- Selector là `null` → nhánh `case null`.
- Selector là `"  "` → type pattern `String s` khớp và guard `s.isBlank()` đúng → `"blank"`.
- Selector là `"Java"` → nhánh String có guard bị bỏ qua vì guard sai; nhánh String kế tiếp áp dụng.
- Selector là `10` → `default`.

**Không viết `case null when ...`:** cú pháp Java 21 chỉ cho phép `when` gắn với nhãn **case pattern**. Nếu cần xử lý null theo một điều kiện ngoài, hãy đặt logic bên trong thân nhánh `case null -> { ... }` hoặc chuẩn bị điều kiện trước `switch`.

## 6. Phân biệt null selector và null record component

Đây là điểm dễ nhầm trong Java 21. Xét:

```java
record Box(String content) {}
```

Có **hai giá trị hoàn toàn khác nhau**:

1. `Box outer = null;` — **chính đối tượng selector** là `null`.
2. `Box outer = new Box(null);` — selector là một đối tượng `Box` **khác null**, nhưng trường component `content` có giá trị `null`.

Với record pattern:

```java
static String inspectBox(Object input) {
    return switch (input) {
        case null -> "outer-null";
        case Box(String content) ->
                content == null ? "inner-null" : "content: " + content;
        default -> "not-a-box";
    };
}
```

Kết quả:

| Giá trị | Nhánh | Kết quả |
| --- | --- | --- |
| `null` | `case null` | `outer-null` |
| `new Box(null)` | `case Box(String content)` | `inner-null` |
| `new Box("x")` | `case Box(String content)` | `content: x` |
| `123` | `default` | `not-a-box` |

Với `new Box(null)`, pattern `Box(String content)` **có thể khớp** vì type pattern cho component `String` là unconditional đối với kiểu component `String` và việc phân rã record cho phép biến ấy nhận `null`. Nhưng khi **toàn bộ selector** là `null`, record pattern `Box(...)` không khớp; `case null` mới xử lý được.

Không nên áp dụng quy tắc “`null` không khớp type pattern ở selector ngoài” một cách máy móc cho **mọi pattern lồng bên trong record**. Với một component có kiểu tham chiếu khác, pattern con không unconditional có thể không khớp `null`. Phải xét đúng kiểu tĩnh của component và quy tắc resolve pattern tại đó.

## 7. Quy tắc cú pháp và thứ tự nhãn trong Java 21

### Selector phải là kiểu tham chiếu khi dùng `case null`

```java
static String checkBoxed(Integer number) {
    return switch (number) {
        case null -> "missing";
        case 0 -> "zero";
        default -> "other number";
    };
}
```

Đây là mã hợp lệ. `Integer` là kiểu tham chiếu và có thể chứa `null`. Khi selector là `null`, Java chọn `case null` trước khi cần xử lý giá trị số.

Ngược lại:

```java
// KHÔNG BIÊN DỊCH: selector int là kiểu nguyên thủy.
// static String broken(int number) {
//     return switch (number) {
//         case null -> "missing";
//         default -> "number";
//     };
// }
```

Một biến nguyên thủy `int` không thể chứa `null`, nên nhãn `case null` không hợp lệ với selector này. Chú ý đừng nhầm biến `Integer` (có thể null) với biến `int`.

### Chỉ một `case null` và một `default`

Trong cùng một `switch` block, JLS Java 21 không cho khai báo nhiều hơn một null label hoặc nhiều hơn một default label:

```java
// KHÔNG BIÊN DỊCH:
// switch (value) {
//     case null -> System.out.println("A");
//     case null -> System.out.println("B"); // Trùng null label
//     default -> System.out.println("C");
// }
```

### `case null, default` phải ở cuối

```java
// KHÔNG BIÊN DỊCH:
// switch (value) {
//     case null, default -> System.out.println("remaining");
//     case String s -> System.out.println(s); // Không được thêm nhãn phía sau
// }
```

Dùng `case null, default` sau các trường hợp đặc biệt:

```java
static String correct(Object value) {
    return switch (value) {
        case String s -> "text";
        case Integer n -> "int";
        case null, default -> "remaining";
    };
}
```

Về cú pháp Java 21, `default` đặt trước nhãn có pattern hay `case null` cũng là lỗi; đặt `default` ở cuối là cách nhất quán, dễ đọc.

### Không gộp nhãn null với pattern có biến theo dạng danh sách

Cú pháp sau **không hợp lệ** trong Java 21:

```java
// KHÔNG BIÊN DỊCH:
// return switch (value) {
//     case null, String s -> "missing-or-string";
//     default -> "other";
// };
```

Đừng suy ra từ `case null, default` rằng có thể gộp tùy ý một literal `null` với một type pattern. Hãy tách:

```java
static String separate(Object value) {
    return switch (value) {
        case null -> "missing";
        case String s -> "string: " + s;
        default -> "other";
    };
}
```

## 8. Cách viết với `switch` statement và với `switch` expression

### `switch` expression: trả về kết quả rõ ràng

```java
static int parseLength(String input) {
    return switch (input) {
        case null -> 0;
        case String s -> s.length();
    };
}
```

Mỗi nhánh dùng `->` để trả về một giá trị; expression phải exhaustive. Cách này phù hợp khi phân loại đầu vào và tạo một kết quả.

### `switch` statement: thực hiện hành động

```java
static void printType(Object value) {
    switch (value) {
        case null -> System.out.println("missing");
        case String s -> System.out.println("text " + s.length());
        default -> System.out.println("another type");
    }
}
```

Dùng `->` giúp tránh *fall-through* vô ý. Với cú pháp dấu hai chấm `case ...:` truyền thống, nếu có case pattern khai báo biến, trình biên dịch ngăn những đường rơi qua (*fall-through*) khiến biến pattern chưa được khởi tạo. Ví dụ **không hợp lệ**:

```java
// KHÔNG BIÊN DỊCH:
// switch (value) {
//     case null:
//     case String s:
//         System.out.println(s); // Có thể tới đây từ null mà s chưa được gán.
//         break;
//     default:
//         break;
// }
```

Hãy dùng hai nhánh `case null -> ...` và `case String s -> ...` riêng biệt, hoặc gom phần xử lý chung thành phương thức không yêu cầu biến pattern.

### Phiên bản Java

- **Java 17:** pattern matching for `instanceof` đã ổn định. Pattern matching cho `switch` chưa ổn định trong Java 17 và nằm trong cơ chế preview.
- **Java 21:** pattern matching cho `switch`, bao gồm `case null`, là tính năng ổn định. Mã trong bài có thể biên dịch bằng `javac --release 21` mà không cần `--enable-preview`.
- Không suy ngược cú pháp từ bài viết về preview của Java 17–20 hoặc preview về unnamed patterns/primitive patterns ở những phiên bản khác sang cú pháp ổn định Java 21.

## 9. Ví dụ hoàn chỉnh: null, pattern, guard, record và default

Tạo tệp **`NullCasePatternSwitchDemo.java`** chứa toàn bộ mã sau. Chương trình dùng các tính năng Java 21 đã ổn định:

```java
public class NullCasePatternSwitchDemo {
    record Box(String content) {}

    static String classify(Object obj) {
        return switch (obj) {
            // Selector null có nhánh riêng.
            case null -> "selector: null";

            // Type pattern + guard.
            case String s when s.isBlank() -> "blank String";
            case String s -> "String(" + s.length() + "): " + s;

            case Integer n -> "Integer: " + n;

            // Record pattern: Box khác null nhưng component có thể null.
            case Box(String content) when content == null -> "Box(null)";
            case Box(String content) -> "Box(" + content + ")";

            default -> "Other: " + obj.getClass().getSimpleName();
        };
    }

    static String classifyRemaining(Object obj) {
        return switch (obj) {
            case String s -> "text";
            case null, default -> "other-or-null";
        };
    }

    static String requireNonNull(Object obj) {
        return switch (obj) {
            case String s -> "string";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
                null, "  ", "Java", 7,
                new Box(null), new Box("x"), 3.14
        };

        for (Object value : values) {
            System.out.println(classify(value));
        }

        System.out.println(classifyRemaining(null));
        System.out.println(classifyRemaining(5));

        try {
            System.out.println(requireNonNull(null));
        } catch (NullPointerException e) {
            System.out.println("NullPointerException");
        }
    }
}
```

**Biên dịch và chạy** tại thư mục chứa tệp bằng JDK 21 trở lên:

```bash
javac --release 21 -encoding UTF-8 NullCasePatternSwitchDemo.java
java NullCasePatternSwitchDemo
```

**Kết quả:**

```text
selector: null
blank String
String(4): Java
Integer: 7
Box(null)
Box(x)
Other: Double
other-or-null
other-or-null
NullPointerException
```

**Giải thích chính xác từng nhóm:**

1. Giá trị đầu tiên là `null` nên `case null` được chọn. Không có pattern variable nào phải được khởi tạo.
2. Chuỗi chỉ gồm khoảng trắng khớp `String s` và guard `s.isBlank()` đúng nên trả `blank String`.
3. `"Java"` qua guard đầu nhưng khớp `case String s` tiếp theo, trả độ dài 4.
4. `7` (autoboxing thành `Integer` trong mảng `Object[]`) khớp nhánh `Integer n`.
5. `new Box(null)` không có selector null; record pattern được khớp và guard kiểm tra null component, trả `Box(null)`.
6. `new Box("x")` đi đến record pattern thứ hai, trả `Box(x)`.
7. `3.14` là `Double`, nên `default` trả `Other: Double`. Trong ví dụ này, `obj.getClass()` an toàn tại `default` vì selector null đã có nhánh riêng.
8. `classifyRemaining(null)` và `classifyRemaining(5)` đều tới `case null, default`.
9. `requireNonNull(null)` không có `case null`. Dù có `default`, biểu thức vẫn ném `NullPointerException` và chương trình bắt ngoại lệ để in dòng cuối.

## 10. Thiết kế xử lý `null` trong API thực tế

Hãy chọn rõ ràng một trong các chính sách:

**Chính sách A — null là trạng thái nghiệp vụ hợp lệ.** Ví dụ, chưa có người dùng đăng nhập, chưa tìm được đối tượng hoặc đầu vào tùy chọn. Dùng `case null` và trả giá trị/đối tượng biểu diễn “không có dữ liệu” một cách nhất quán.

```java
static String displayName(Object value) {
    return switch (value) {
        case null -> "(unknown)";
        case String name when !name.isBlank() -> name;
        default -> "(invalid name)";
    };
}
```

**Chính sách B — null là lỗi hợp đồng.** Nếu API bắt buộc đầu vào khác null, có thể dùng `Objects.requireNonNull(value)` trước `switch` và để `NullPointerException` thể hiện lỗi, hoặc chọn thông báo ngoại lệ rõ ràng. Không nên thêm `case null` chỉ để che giấu dữ liệu không hợp lệ.

```java
static String nonNullDescription(Object value) {
    java.util.Objects.requireNonNull(value, "value must not be null");
    return switch (value) {
        case String s -> "text " + s;
        default -> "other";
    };
}
```

**Chính sách C — null và kiểu không nhận diện có cùng cách xử lý.** Dùng `case null, default` khi cả hai thực sự tương đương về nghĩa.

```java
static String simpleLabel(Object value) {
    return switch (value) {
        case Integer i -> "int";
        case String s -> "string";
        case null, default -> "unknown";
    };
}
```

Lựa chọn nào cũng nên có kiểm thử ít nhất cho **`null`**, một giá trị thuộc pattern, và một giá trị khác không thuộc pattern. Với record, thử thêm **record khác null có component null** để tránh bỏ sót trường hợp lồng nhau.

## 11. Lỗi thường gặp và cách tự kiểm tra

1. **Tưởng `default` bắt luôn `null`.** Không đúng trong Java 21: thiếu `case null` thì selector null gây `NullPointerException`.
2. **Tưởng `case Object o` khớp `null`.** Nó bao phủ các đối tượng khác null, không phải null selector.
3. **Cho rằng `case null` là một pattern.** Đây là một loại label riêng theo ngữ pháp `switch`, không khai báo biến và không đi kèm guard `when`.
4. **Trộn `null` với pattern trong một nhãn.** `case null, default` là hình thức đặc biệt; `case null, String s` không phải cú pháp hợp lệ trong Java 21.
5. **Đặt `case null, default` trước các nhãn khác.** Vì nhãn này là nhánh tổng hợp, không thể tiếp tục đặt các nhãn sau nó.
6. **Khai báo nhiều lần `case null`.** Mỗi switch block chỉ được có tối đa một nhãn null.
7. **Dùng `case null` với selector nguyên thủy.** Ví dụ `switch (intValue)` không thể nhận giá trị null.
8. **Nhầm null selector với record component null.** `new Box(null)` là đối tượng Box khác null; có thể khớp `case Box(String content)` theo quy tắc pattern lồng nhau.
9. **Bỏ qua exhaustiveness.** `switch` expression và enhanced `switch` statement cần bao phủ các trường hợp cần thiết, nhưng kiểm tra exhaustiveness không tự bảo đảm selector null sẽ được xử lý.
10. **Lẫn cú pháp preview với Java 21 ổn định.** Đọc đúng tài liệu JLS/JEP của phiên bản dự kiến biên dịch.

**Bài tập 1.** Dự đoán kết quả:

```java
Object x = null;
String result = switch (x) {
    case String s -> "text";
    case Integer i -> "number";
    default -> "other";
};
```

Đáp án: **ném `NullPointerException`**, không trả `"other"`.

**Bài tập 2.** Sửa mã trên để trả `"missing"` khi `x == null`, còn nhánh `default` vẫn dành cho các giá trị không thuộc `String`/`Integer`. Đáp án: thêm `case null -> "missing";`.

**Bài tập 3.** Với `Object x = new Box(null);` và nhánh `case Box(String content)`, bạn dự đoán selector có đi vào `case null` không? Đáp án: **không**; selector là một Box khác null. Trong trường hợp component String, pattern con có thể nhận null; xét `content == null` trong nhánh Box.

**Bài tập 4.** Khi nào nên dùng `case null, default` thay vì hai nhánh riêng? Đáp án: khi cả null và giá trị còn lại có cùng ý nghĩa, cùng kết quả và cùng cách xử lý theo hợp đồng nghiệp vụ.

## Tham khảo chính thức

- [JLS Java SE 21 `14.11.1 — The Switch Block](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): cú pháp `case null`, `case null, default`, guard, nhãn, dominance và exhaustiveness.
- [JLS Java SE 21 `14.11.1.2 — Determining Which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): quy tắc chọn nhãn khi selector null/khác null.
- [JLS Java SE 21 `14.11.3 — Execution of a switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.3): khi nào `switch` statement ném `NullPointerException`.
- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type pattern, record pattern và quy tắc khớp.
- [OpenJDK JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): tính năng ổn định từ Java 21 và nguyên tắc xử lý `null` trong pattern switch.
