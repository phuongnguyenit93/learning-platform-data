# Dùng pattern expression trong return (Java 21)

## 1. Mục tiêu và phạm vi

Trong Java, **`return`** trả về kết quả của một biểu thức có kiểu tương thích với kiểu trả về đã khai báo. Pattern matching giúp biểu thức xác định một giá trị có khớp kiểu/cấu trúc mong đợi hay không và, nếu có, lấy ra các biến pattern để xử lý. Kết hợp hai cơ chế này cho phép viết những phương thức gọn, dễ đọc, ít ép kiểu thủ công.

Bài học giải thích cách sử dụng pattern matching **bên trong biểu thức trả về** qua ba hình thức quan trọng:

1. `return value instanceof Type variable;` hoặc `return value instanceof Record(...);` trả kết quả `boolean`.
2. `return condition ? resultIfMatched : resultIfNotMatched;` và `return pattern && additionalCondition;` để tính giá trị dựa trên biến pattern theo đúng phạm vi hợp lệ.
3. `return switch (value) { case Pattern -> result; ... };` để trả về một kết quả dựa trên nhiều pattern, record patterns và các điều kiện `when`.

Ngoài ra còn có **guard clause**: dùng `if` với pattern, trả về sớm nếu không match và tiếp tục xử lý biến pattern ở đoạn sau.

Sau bài học, bạn sẽ hiểu cách kiểm tra kiểu, **flow scoping** của biến pattern, xử lý `null`, tính đầy đủ của nhánh `switch`, phân biệt `return` với `yield`, và tránh lỗi biên dịch khi tổ hợp `&&`/`||`.

**Yêu cầu phiên bản:** Type pattern của `instanceof` là tính năng chuẩn từ Java 16 (JEP 394). Record patterns (JEP 440) và pattern matching for `switch` (JEP 441) trở thành tính năng chuẩn trong **Java 21**. Các ví dụ đầy đủ dưới đây biên dịch với `javac --release 21`, không cần `--enable-preview`.

## 2. Trả trực tiếp boolean của pattern matching

Toán tử `instanceof` trả một giá trị `boolean`; vì vậy có thể dùng trực tiếp trong phương thức trả `boolean`:

```java
static boolean isText(Object value) {
    return value instanceof String;
}
```

Trong thực tế, type pattern giúp vừa kiểm tra kiểu vừa lấy biến để áp dụng ràng buộc bổ sung:

```java
static boolean isNonBlankText(Object value) {
    return value instanceof String text && !text.isBlank();
}
```

Nếu `value` không phải `String` (kể cả `null`), vế `instanceof` trả `false`; do `&&` đánh giá ngắn mạch, `text.isBlank()` không chạy. Nếu `value` khớp `String`, `text` được bind và phép gọi an toàn.

Với một record có nhiều component, có thể kiểm tra ngay trong biểu thức `return`:

```java
record User(String name, int age) {}

static boolean isAdult(Object value) {
    return value instanceof User(var name, var age)
            && name != null
            && !name.isBlank()
            && age >= 18;
}
```

**Giải thích:** `User(var name, var age)` kiểm tra đối tượng là `User` rồi tách hai component bằng accessor. Với `var name`, giá trị `null` vẫn có thể được bind, nên kiểm tra `name != null` là cần thiết trước khi gọi `isBlank()`. Dùng `User(String name, int age)` thì component `name` bằng `null` khiến nested type pattern `String name` không match; đây là sự khác biệt thực tế giữa `var` và type pattern.

Bảng trường hợp:

| Đầu vào | `isAdult` |
| --- | --- |
| `new User("An", 21)` | `true` |
| `new User("An", 16)` | `false` |
| `new User("", 30)` | `false` |
| `new User(null, 30)` | `false` |
| `null` hoặc một object không phải `User` | `false` |

Một **pattern** không phải một giá trị độc lập có thể trả về trực tiếp. Ví dụ `return String s;` không có ý nghĩa; biểu thức phải là `value instanceof String s`, một phép kết hợp boolean hợp lệ, toán tử ba ngôi, hoặc `switch` expression.

## 3. Kết hợp biểu thức phủ định trong `return`

Khi quy tắc cần xác định trường hợp **không hợp lệ**, có thể phủ định phép match:

```java
static boolean invalidUser(Object value) {
    return !(value instanceof User(var name, var age))
            || name == null
            || name.isBlank()
            || age < 18;
}
```

Mô hình này đúng về phạm vi biến pattern nhờ `||`:

- Nếu `!(...)` đúng, đối tượng không khớp `User`; biểu thức trả `true` ngay, các vế sau không chạy.
- Nếu `!(...)` sai, phép match `User` đã thành công; `name` và `age` tồn tại nên có thể được đọc ở các vế phải.
- Khi `name == null` đúng, `name.isBlank()` được bỏ qua, tránh `NullPointerException`.

Đây là cách viết tương đương về ý định với quy tắc `!isAdult(value)` trong ví dụ trên, nhưng minh họa rõ **flow scoping** khi phủ định pattern.

Cần tránh hai cách viết sai sau:

```java
// Sai: phía phải || có thể chạy khi String pattern thất bại.
return value instanceof String text || text.isBlank();

// Sai: phía phải && chỉ chạy khi String pattern thất bại.
return !(value instanceof String text) && text.isBlank();
```

Hai dòng trên là **ví dụ lỗi biên dịch có chủ đích**, đặt trong ngữ cảnh phương thức trả `boolean`. Không thể dùng biến `text` ở vị trí mà trình biên dịch chưa bảo đảm pattern đã match.

Đối chiếu quy tắc:

| Biểu thức `return` | Hợp lệ? | Lý do |
| --- | --- | --- |
| `return obj instanceof String s && !s.isBlank();` | Có | `s` tồn tại khi vế phải được đánh giá |
| `return !(obj instanceof String s) &#124;&#124; s.isBlank();` | Có | Vế phải chạy khi phép phủ định sai, tức match thành công |
| `return obj instanceof String s &#124;&#124; s.isBlank();` | Không | Vế phải chạy khi phép match thất bại |
| `return !(obj instanceof String s) && s.isBlank();` | Không | Vế phải chạy khi phép match thất bại |

## 4. Dùng pattern trong toán tử ba ngôi trả giá trị

Toán tử điều kiện `condition ? trueExpression : falseExpression` là một **expression**, nên có thể đặt sau `return`:

```java
static String uppercase(Object value) {
    return value instanceof String text
            ? text.toUpperCase(java.util.Locale.ROOT)
            : "not a string";
}
```

Trong nhánh `?`, pattern `String text` chắc chắn đã match, nên có thể gọi `text.toUpperCase(...)`. Nhánh `:` xử lý mọi giá trị không phải `String`, bao gồm `null`, mà không cần ép kiểu.

Record pattern tương tự:

```java
record Point(int x, int y) {}

static String pointLabel(Object value) {
    return value instanceof Point(var x, var y)
            ? "point=" + x + "," + y
            : "not a point";
}
```

Với `new Point(2, 5)`, phương thức trả `"point=2,5"`. Với `"hello"`, kết quả `"not a point"`.

Các nhánh `?` và `:` phải tạo được kết quả có kiểu phù hợp với kiểu trả về của phương thức; ví dụ trên đều là `String`. Nếu cần kiểm tra nhiều trường hợp hoặc lồng nhiều toán tử ba ngôi, một `switch` expression thường dễ đọc và dễ bảo trì hơn.

### Đừng lạm dụng ba ngôi lồng nhau

Một đoạn như `return a ? x : b ? y : z;` có thể hợp lệ, nhưng khi các biểu thức chứa nhiều record patterns và điều kiện, dễ viết sai thứ tự hoặc khó đánh giá lúc `null`. Dùng `switch` khi thực sự có nhiều nhánh theo các dạng dữ liệu khác nhau.

## 5. Guard clause: kết hợp `return` với flow scoping

Đôi khi điều kiện phủ định giúp xử lý trường hợp sai ngay đầu phương thức:

```java
static String labelOrMissing(Object value) {
    if (!(value instanceof String label)) {
        return "missing";
    }
    return "label=" + label.trim();
}
```

Điểm quan trọng: biến `label` **vẫn hợp lệ sau câu lệnh `if`**. Lý do là nếu nhánh phủ định đúng, phương thức đã trả về; mọi đường thực thi đến lệnh `return` cuối đều chứng minh `value instanceof String label` thành công.

Trường hợp kiểm tra record:

```java
static String nonNegativePoint(Object value) {
    if (!(value instanceof Point(var x, var y))) {
        return "not a point";
    }
    if (x < 0 || y < 0) {
        return "negative coordinate";
    }
    return x + "," + y;
}
```

Đây là đoạn phương thức độc lập khi `Point` đã được khai báo như ví dụ ở trên. Nó phân biệt **không match record** với **record match nhưng dữ liệu không đáp ứng điều kiện**. `Point(-1, 2)` vẫn match `Point(var x, var y)`; nó chỉ bị loại ở điều kiện kiểm tra tọa độ.

Với `if` không thoát sớm, biến pattern không tự động hợp lệ sau cả hai nhánh:

```java
if (!(value instanceof String label)) {
    System.out.println("not string");
} else {
    System.out.println(label.length()); // hợp lệ trong else
}
// Ở đây không được mặc nhiên dùng label nếu nhánh if vẫn tiếp tục.
```

**Quy tắc:** Phạm vi biến pattern phụ thuộc đường đi thực thi mà trình biên dịch chứng minh pattern đã khớp, không phụ thuộc vị trí văn bản của từ khóa `return`.

## 6. Trả trực tiếp kết quả của `switch` expression

Java 21 cho phép `switch` là một biểu thức có kết quả. Pattern matching kết hợp record patterns giúp viết phương thức trả một `String` rõ ràng:

```java
static String describe(Object value) {
    return switch (value) {
        case Point(var x, var y) when x == y -> "diagonal=" + x;
        case Point(var x, var y) -> "point=" + x + "," + y;
        case String s when !s.isBlank() -> "text=" + s.trim();
        case String s -> "blank string";
        case null -> "null";
        default -> "other";
    };
}
```

Các điểm cần chú ý:

1. `return switch (...) { ... };` là một câu lệnh `return` bao quanh **switch expression**. Dấu `;` kết thúc câu lệnh.
2. Mỗi nhánh dùng `->` tạo một giá trị `String` tương thích với kiểu trả về.
3. `case Point(var x, var y)` vừa kiểm tra record vừa tách component.
4. `when x == y` là điều kiện guard, được đánh giá khi `Point` đã match. Nhánh `Point` chuyên biệt được đặt trước nhánh tổng quát.
5. `case String s when !s.isBlank()` kiểm tra chuỗi không rỗng/không chỉ khoảng trắng; sau đó `case String s` bao các chuỗi còn lại.
6. `case null` xử lý đầu vào `null`; nếu thiếu nhánh này, việc `switch` trên một reference `null` có thể dẫn đến `NullPointerException`. `default` không tự xử lý `null`.
7. `default` làm biểu thức đầy đủ (exhaustive) với các đối tượng khác kiểu đã liệt kê.

**Khác biệt với `switch` statement:** một `switch` expression có **kết quả** và phải đầy đủ mọi trường hợp có thể xảy ra theo kiểu của selector. Các nhánh cũng phải cung cấp giá trị có kiểu phù hợp. Một `switch` statement có thể chỉ thực hiện side effect mà không có giá trị trả về cho `return`.

Ví dụ sử dụng:

```java
System.out.println(describe(new Point(3, 3))); // diagonal=3
System.out.println(describe(new Point(2, 4))); // point=2,4
System.out.println(describe(" hello "));        // text=hello
System.out.println(describe(null));             // null
```

## 7. Pattern `switch` có `sealed` type: exhaustive mà không cần `default`

Khi đầu vào có kiểu sealed với các subtype đã được khai báo rõ, trình biên dịch có thể kiểm tra tính đầy đủ dựa trên danh sách subclass được phép:

```java
sealed interface Message permits Text, Location, Unknown {}

record Text(String value) implements Message {}
record Location(int x, int y) implements Message {}
record Unknown() implements Message {}

static String classify(Message message) {
    return switch (message) {
        case null -> "null message";
        case Text(var text) when text != null && !text.isBlank() ->
                "text=" + text.trim();
        case Text(var text) -> "empty text";
        case Location(var x, var y) -> "location=" + x + "," + y;
        case Unknown u -> "unknown";
    };
}
```

Trong trường hợp trên, các nhánh `Text`, `Location`, `Unknown` phủ toàn bộ subtype của `Message`. `case Text(var text)` phía sau bao cả `Text(null)` và chuỗi blank. `case null` có ý nghĩa riêng; `null` **không phải** một subtype của `Message`.

Không có nhánh `default` mà vẫn hợp lệ, vì trình biên dịch chứng minh `switch` expression bao phủ mọi kiểu được phép. Nếu sau này thay đổi tập subtype của sealed hierarchy, source code cần được biên dịch và kiểm tra lại để giữ tính đầy đủ. Trong chương trình Java đã biên dịch, các trường hợp mất cân đối do việc thay đổi hierarchy giữa các lần biên dịch có thể phát sinh lỗi runtime; hãy giữ các thành phần triển khai cùng phiên bản.

Ưu điểm của việc không có `default` một cách tùy tiện với sealed hierarchy là compiler có thể báo thiếu nhánh khi hệ thống kiểu thay đổi, thay vì âm thầm chuyển đối tượng mới vào nhánh `default`.

## 8. Khi một nhánh cần nhiều câu lệnh: dùng `yield`

Một nhánh của switch expression có thể dùng khối `{ ... }` để tính giá trị rồi **`yield`**:

```java
static String explain(Object value) {
    return switch (value) {
        case Point(var x, var y) when x < 0 || y < 0 -> {
            String field = x < 0 ? "x" : "y";
            yield "negative " + field;
        }
        case Point(var x, var y) -> "valid point";
        case null -> "null";
        default -> "other";
    };
}
```

Ở nhánh block, `yield "negative " + field;` cung cấp **giá trị của switch expression**. Sau khi biểu thức `switch` hoàn thành, `return` bên ngoài trả giá trị đó cho phương thức.

Không viết `return` **bên trong block của switch expression** để thay thế `yield`:

```java
// CỐ Ý SAI — không biên dịch.
return switch (value) {
    case String s -> { return s.trim(); }
    default -> "other";
};
```

Ví dụ trên minh họa lỗi `attempt to return out of a switch expression`. Cách đúng:

```java
return switch (value) {
    case String s -> {
        String normalized = s.trim();
        yield normalized;
    }
    default -> "other";
};
```

Một nhánh dạng biểu thức ngắn có thể viết `case String s -> s.trim();`. Chỉ dùng block và `yield` khi có nhiều bước tính toán, biến cục bộ hoặc kiểm tra phụ thực sự làm mã rõ hơn.

## 9. Ví dụ hoàn chỉnh chạy trên Java 21

Tạo tệp **`ReturnPatternDemo.java`**. Chương trình thực hành trực tiếp cả `instanceof`/record pattern trong `return`, toán tử ba ngôi, guard clause, `switch` expression với `when` và `yield`.

```java
import java.util.Locale;

public class ReturnPatternDemo {
    record User(String name, int age) {}
    record Point(int x, int y) {}

    sealed interface Message permits Text, Location, Unknown {}
    record Text(String value) implements Message {}
    record Location(int x, int y) implements Message {}
    record Unknown() implements Message {}

    static boolean isAdult(Object value) {
        return value instanceof User(var name, var age)
                && name != null && !name.isBlank() && age >= 18;
    }

    static boolean invalidUser(Object value) {
        return !(value instanceof User(var name, var age))
                || name == null || name.isBlank() || age < 18;
    }

    static String pointLabel(Object value) {
        return value instanceof Point(var x, var y)
                ? "point=" + x + "," + y
                : "not a point";
    }

    static String uppercase(Object value) {
        return value instanceof String text
                ? text.toUpperCase(Locale.ROOT)
                : "not a string";
    }

    static String labelOrMissing(Object value) {
        if (!(value instanceof String label)) {
            return "missing";
        }
        return "label=" + label.trim();
    }

    static String describe(Object value) {
        return switch (value) {
            case Point(var x, var y) when x == y -> "diagonal=" + x;
            case Point(var x, var y) -> "point=" + x + "," + y;
            case String s when !s.isBlank() -> "text=" + s.trim();
            case String s -> "blank string";
            case null -> "null";
            default -> "other";
        };
    }

    static String classify(Message message) {
        return switch (message) {
            case null -> "null message";
            case Text(var text) when text != null && !text.isBlank() ->
                    "text=" + text.trim();
            case Text(var text) -> "empty text";
            case Location(var x, var y) -> "location=" + x + "," + y;
            case Unknown u -> "unknown";
        };
    }

    static String explain(Object value) {
        return switch (value) {
            case Point(var x, var y) when x < 0 || y < 0 -> {
                String field = x < 0 ? "x" : "y";
                yield "negative " + field;
            }
            case Point(var x, var y) -> "valid point";
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println("adult=" + isAdult(new User("An", 21)));
        System.out.println("adult=" + isAdult(new User(null, 30)));
        System.out.println("invalid=" + invalidUser(null));
        System.out.println("invalid=" + invalidUser(new User("Binh", 20)));
        System.out.println(pointLabel(new Point(2, 5)));
        System.out.println(pointLabel("plain text"));
        System.out.println(uppercase("java"));
        System.out.println(uppercase(10));
        System.out.println(labelOrMissing("  ID-7  "));
        System.out.println(labelOrMissing(null));
        System.out.println(describe(new Point(3, 3)));
        System.out.println(describe(new Point(2, 4)));
        System.out.println(describe(" hello "));
        System.out.println(describe(""));
        System.out.println(describe(null));
        System.out.println(classify(new Text(" Hello ")));
        System.out.println(classify(new Text(null)));
        System.out.println(classify(new Location(7, 8)));
        System.out.println(classify(new Unknown()));
        System.out.println(classify(null));
        System.out.println(explain(new Point(-1, 4)));
        System.out.println(explain(new Point(1, 4)));
    }
}
```

Chạy trong thư mục chứa file bằng **JDK 21 trở lên**:

```bash
javac --release 21 ReturnPatternDemo.java
java ReturnPatternDemo
```

**Kết quả tiêu chuẩn (stdout):**

```text
adult=true
adult=false
invalid=true
invalid=false
point=2,5
not a point
JAVA
not a string
label=ID-7
missing
diagonal=3
point=2,4
text=hello
blank string
null
text=Hello
empty text
location=7,8
unknown
null message
negative x
valid point
```

Cách đối chiếu:

- Hai lời gọi `isAdult` khác nhau ở điều kiện component `name != null`; `return` được đánh giá ngắn mạch và an toàn.
- `invalidUser(null)` trả `true` ngay ở vế `!(instanceof ...)`, nên không đọc biến pattern chưa bind.
- `pointLabel` và `uppercase` dùng ba ngôi: nhánh `?` chỉ chạy nếu pattern match.
- `labelOrMissing` chứng minh biến pattern vẫn tồn tại sau câu lệnh `if` có nhánh `return` khi match thất bại.
- `describe` dùng thứ tự nhánh cụ thể trước nhánh tổng quát; `null` được xử lý riêng.
- `classify` chứng minh sealed hierarchy có thể dùng `return switch` exhaustive mà không cần `default`; hai trường hợp `Text(" Hello ")` và `Text(null)` đi vào hai nhánh khác nhau.
- `explain` dùng `yield` bên trong một nhánh block để tạo giá trị được `return` ra khỏi phương thức.

## 10. Phạm vi, an toàn kiểu và khả năng đọc mã

### 10.1. Pattern variables không giống biến được khai báo ở đầu phương thức

`String s` trong `value instanceof String s` là **biến pattern**. Phạm vi của nó chỉ mở ở những đường đi mà trình biên dịch xác định match thành công. Khi `return` có nhiều toán tử, hãy kiểm tra logic short-circuit thay vì suy đoán bằng vị trí trên cùng một dòng.

Để giữ mã dễ đọc, mỗi biểu thức return nên biểu đạt một quy tắc rõ ràng. Chẳng hạn, nếu validation có quá nhiều điều kiện, cân nhắc guard clause với các lỗi riêng, hoặc các phương thức helper `isValidName(...)`, `isAllowedAge(...)` thay vì chuỗi `&&` quá dài.

### 10.2. `null` và record component `null` là hai trường hợp khác

- `null instanceof User(var name, var age)` trả `false` vì đối tượng ngoài bằng `null`.
- `new User(null, 30) instanceof User(var name, var age)` có thể match; `name` được bind thành `null`.
- `new User(null, 30) instanceof User(String name, int age)` không match ở thành phần `String name` vì type pattern không match `null`.
- Trong `switch` expression, `case null` xử lý đối tượng selector bằng `null`. Pattern `Text(var text)` có thể match một record `Text` mà component `text` bằng `null`.

### 10.3. `return switch` phải đầy đủ và kết quả phải có kiểu phù hợp

Nếu selector có kiểu `Object`, không thể mặc nhiên bao hết bằng vài case record; thường cần `default`. Nếu selector là sealed type, compiler có thể xác minh tập subtype và yêu cầu xử lý từng nhánh khi hierarchy được mở rộng. Cần thêm xử lý `null` khi muốn trả kết quả thay vì ném `NullPointerException`.

Mỗi nhánh trả cùng dạng giá trị tương thích với kiểu khai báo. Trong mã ví dụ, mọi nhánh `describe`, `classify` và `explain` đều tạo `String`; không có nhánh nào chỉ in log mà bỏ quên giá trị cần trả.

### 10.4. Một record pattern chỉ đọc cấu trúc, không sao chép giá trị

Khi return expression dùng `record Box(List<String> items)` hoặc record có mảng, việc match/tách component không tự tạo defensive copy hay làm dữ liệu bất biến. Nếu trả về một `List` lấy từ pattern, caller có thể nhận cùng tham chiếu mutable mà accessor trả. Hãy quyết định chính sách bất biến ở thiết kế kiểu dữ liệu; chỉ dùng `List.copyOf` khi muốn snapshot không sửa được của container và đã hiểu rằng đó không phải deep copy.

### 10.5. Giá trị trả về phải nhất quán với mục tiêu API

Nếu một phương thức chỉ xác định một predicate, trả `boolean` bằng `instanceof`/`&&` có thể tốt hơn `if/else` dài. Nếu phương thức cần nhiều trường hợp trả về khác nhau, `switch` expression thường phù hợp. Nếu có validation cần thông báo chi tiết, guard clause giúp kiểm soát lỗi, còn nhiều `return` riêng có thể rõ hơn so với một biểu thức phức tạp.

## 11. Những lỗi thường gặp

| Lỗi | Nguyên nhân | Sửa |
| --- | --- | --- |
| Dùng `s` ở bên phải `||` sau `value instanceof String s` | Vế phải chỉ chạy khi phép match thất bại | Dùng `&&` với pattern dương, hoặc phủ định pattern rồi dùng `||` |
| Dùng `s` ở bên phải `&&` sau `!(value instanceof String s)` | Vế phải chạy khi pattern thất bại | Đổi logic thành `!(...) &#124;&#124; ...` hoặc guard clause |
| Viết `return String s;` | Pattern không phải giá trị trả về độc lập | Trả boolean từ `instanceof`, kết quả ba ngôi hoặc `switch` |
| Quên `null` trong `return switch` | `null` không match type/record patterns | Thêm `case null` khi API muốn xử lý `null` |
| Thiếu nhánh cuối của switch expression | Switch expression phải exhaustive | Thêm `default` khi thích hợp hoặc liệt kê đủ subtype của sealed type |
| Đặt pattern tổng quát trước pattern có `when` | Nhánh cụ thể có thể bị che khuất (dominated) | Đặt nhánh đặc biệt trước nhánh tổng quát |
| Dùng `return` trong block `case -> { ... }` của switch expression | Block của switch expression tạo giá trị bằng `yield` | Dùng `yield expression;` |
| Nghĩ `User(var name, ...)` bảo đảm `name != null` | `var` có thể bind giá trị `null` | Kiểm tra `name != null` trước khi gọi method |
| Trả trực tiếp mutable component đã tách từ record | Record pattern không copy hoặc đóng băng tham chiếu | Thiết kế defensive copy khi cần |
| Dùng record pattern trên JDK 17 rồi gặp lỗi cú pháp | Record patterns chỉ là tính năng chuẩn từ JDK 21 | Biên dịch/chạy trên JDK 21+ |

## 12. Câu hỏi tự kiểm tra

**1.** Vì sao `return value instanceof String s && !s.isBlank();` không ném `NullPointerException` khi `value == null`?  
*Trả lời:* `instanceof` trả `false`, vế phải của `&&` không được đánh giá.

**2.** Biểu thức `return !(value instanceof String s) || s.isBlank();` có biên dịch không?  
*Trả lời:* Có. `s.isBlank()` chỉ chạy khi phép phủ định sai, tức `String s` đã match.

**3.** Tại sao `return value instanceof String s || s.isBlank();` sai?  
*Trả lời:* Khi `instanceof` sai, vế phải mới chạy nhưng `s` chưa có giá trị pattern hợp lệ.

**4.** Với `return value instanceof Point(var x, var y) ? x + y : -1;`, vế nào được phép dùng `x`, `y`?  
*Trả lời:* Vế sau `?` (trường hợp match thành công); vế sau `:` không được giả định pattern đã match.

**5.** Vì sao `if (!(value instanceof String s)) return "missing"; return s.trim();` hợp lệ khi nằm trong một phương thức trả `String`?  
*Trả lời:* Nhánh không match đã thoát; phần còn lại chỉ chạy khi biến `s` đã bind.

**6.** Khi nào cần `yield` trong `return switch`?  
*Trả lời:* Khi một nhánh switch expression là block và cần cung cấp kết quả của block cho biểu thức switch. `yield` khác `return` ở phạm vi điều khiển.

**7.** Vì sao sealed `Message` có thể không cần `default`?  
*Trả lời:* Compiler biết các subtype được phép và có thể chứng minh tất cả đã được xử lý bởi các case.

**8.** `case Text(var value)` có match `new Text(null)` không?  
*Trả lời:* Có. `var` có thể bind component `null`, trong khi nested type pattern như `String value` không match `null`.

## Tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
- [Java Language Specification SE 21 §6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3)
- [Java Language Specification SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [Java Language Specification SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
