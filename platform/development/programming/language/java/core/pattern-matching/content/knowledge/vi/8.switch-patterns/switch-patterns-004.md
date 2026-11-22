# Type pattern trong nhãn `case` của `switch`

> **Module:** Java Core Pattern Matching → Switch pattern. Bài sử dụng **Java 21+**, phiên bản đầu tiên mà *pattern matching for switch* là tính năng chính thức, không cần `--enable-preview`. Trong Java 17–20, tính năng này từng ở trạng thái preview với cú pháp/quy tắc có thay đổi; không sao chép nguyên ví dụ Java 21 để biên dịch bằng `--release 17`.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Đọc và viết nhãn `case String text ->`, `case Integer number ->` trong `switch` statement hoặc expression.
- Xác định **selector** (giá trị được đem so khớp), **type pattern** (kiểu cần thử + biến được bind) và **kiểu tĩnh** của pattern variable.
- Giải thích thứ tự xét các nhãn `case`, guard `when`, phạm vi biến theo nhánh, trường hợp `null`, và khi nào compiler báo **dominated case** hoặc **non-exhaustive switch**.
- Chọn thứ tự pattern từ cụ thể đến tổng quát, có nhánh xử lý tất cả kiểu còn lại, và kiểm tra code bằng JDK 21.

## 1. Type pattern trong `case` là gì?

**Type pattern** có cấu trúc:

~~~text
TênKiểu tênBiến
~~~

Ví dụ `String text` hoặc `Integer number`. Khi đặt sau từ khóa `case` trong `switch`, pattern sẽ được thử với **giá trị của biểu thức selector**:

~~~java
static String describe(Object value) {
    return switch (value) {
        case String text -> "Text: " + text.toUpperCase();
        case Integer number -> "Integer: " + number;
        default -> "Other";
    };
}
~~~

Đây là **mã minh họa phương thức** đặt trong một lớp; chưa phải chương trình độc lập. Trong đoạn này:

- `value` là **biểu thức selector** của `switch`; kiểu tĩnh của nó là `Object`.
- `case String text` là một **case label chứa type pattern**. Khi giá trị runtime là một `String`, nó match và tạo biến `text` có kiểu tĩnh `String`.
- `case Integer number` xử lý một giá trị runtime tương thích `Integer`; biến `number` có kiểu tĩnh `Integer`.
- `default` xử lý **các giá trị không phải `null`** và chưa khớp pattern nào trước đó. `null` cần xử lý riêng nếu có thể xuất hiện; xem phần 5.
- `->` chỉ cách diễn đạt một nhánh hiện đại: với switch expression, biểu thức bên phải được dùng làm **giá trị kết quả**.

So sánh với `instanceof`:

~~~java
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Cả hai sử dụng type pattern `String text`, nhưng `instanceof` trả kết quả của phép thử kiểu trong điều kiện; `switch` chọn **một trong nhiều nhãn `case`** để xử lý. Trong `case`, bạn không cần viết thêm `(String) value` vì biến `text` đã có kiểu đúng.

## 2. Runtime chọn nhãn `case` theo thứ tự nào?

Một cách hiểu hữu ích cho pattern switch trong Java 21:

1. **Đánh giá selector một lần** để lấy giá trị (`switch (value)`).
2. Xét các nhãn `case` theo thứ tự mã nguồn, từ trên xuống theo các quy tắc matching của switch.
3. Với nhãn `case T variable`, kiểm tra giá trị selector có **tương thích với kiểu `T`** hay không. Nếu match, biến `variable` được khởi tạo.
4. Nếu có `when guard`, đánh giá guard **chỉ sau khi pattern match**. Guard trả `false` thì thử nhãn phù hợp kế tiếp.
5. Chọn nhánh được match (hoặc `default` khi thích hợp), rồi thực hiện phần thân của nhánh. Với cú pháp `->`, không có rơi xuyên (*fall-through*) từ một nhánh sang nhánh kế tiếp.
6. Nếu selector là `null`, quy tắc xử lý đặc biệt ở phần 5 áp dụng trước khi xem đó như một object bình thường.

Ví dụ:

~~~java
static String inspect(Object value) {
    return switch (value) {
        case String s when s.isEmpty() -> "empty string";
        case String s -> "string with length " + s.length();
        case Number n -> "number " + n;
        default -> "other object";
    };
}
~~~

- Với `"Java"`: pattern `String s` đầu tiên match, nhưng `s.isEmpty()` là `false`; nhánh `String s` kế tiếp được chọn.
- Với `""`: pattern đầu tiên match và guard `true`; chương trình trả `"empty string"`.
- Với `Integer.valueOf(5)`: không match `String`, nhưng match `Number` (vì `Integer extends Number`).
- Với `new Object()`: `default` được chọn.

**Điểm quan trọng:** `case String s` có thể xuất hiện nhiều lần khi một nhánh có guard và nhánh còn lại xử lý các giá trị cùng kiểu chưa được guard chấp nhận. Hai pattern variable `s` nằm ở hai nhánh riêng, nên không có xung đột tên.

## 3. Kiểu tĩnh của selector quyết định pattern nào hợp lệ

Giống `instanceof`, compiler kiểm tra **tính áp dụng của type pattern** dựa trên kiểu tĩnh của selector; runtime mới quyết định giá trị có match hay không.

~~~java
static String classify(CharSequence sequence) {
    return switch (sequence) {
        case String s -> "String length=" + s.length();
        case StringBuilder b -> "builder length=" + b.length();
        default -> "another sequence";
    };
}
~~~

`sequence` có kiểu tĩnh `CharSequence`. Cả `String` và `StringBuilder` đều triển khai `CharSequence`, nên compiler có thể chấp nhận hai type pattern đó. Một giá trị `StringBuilder` match nhãn thứ hai; một `String` match nhãn thứ nhất. `default` là đường xử lý các triển khai `CharSequence` khác.

Ngược lại, mã sau **cố ý không biên dịch**:

~~~java
static String broken(Integer value) {
    return switch (value) {
        case String text -> "text"; // ERROR: kiểu String không tương thích.
        default -> "other";
    };
}
~~~

Vì selector có kiểu tĩnh `Integer`, một type pattern kiểm tra `String` là không phù hợp theo quy tắc của Java. Compiler không cho một phép match vô nghĩa được đưa vào mã nguồn.

### Type pattern dùng kiểu tham chiếu trong Java 21

Khi muốn phân biệt các giá trị được đóng hộp trong selector kiểu `Object`, viết:

~~~java
static String kind(Object value) {
    return switch (value) {
        case Integer n -> "Integer";
        case Long n -> "Long";
        default -> "Different type";
    };
}
~~~

Đây là **mã minh họa trong lớp**. Với Java 21, không dùng `case int n` hoặc `case long n` thay cho các wrapper pattern ở ví dụ trên: các pattern trên kiểu primitive chưa phải cú pháp Java 21 chính thức. Đây là vấn đề phiên bản, độc lập với `int` có thể xuất hiện như hằng số trong `switch` kiểu số truyền thống.

**Không tự ép kiểu:** Sau `case Integer n`, có thể dùng `n.intValue()`, `n + 1`, v.v.; không cần `(Integer) value`. Kiểu `n` được xác lập từ pattern.

## 4. Pattern variable sống trong guard và nhánh tương ứng

Type pattern **khai báo biến** khi match, và compiler áp dụng **flow scoping** để giới hạn nơi sử dụng.

~~~java
static String title(Object input) {
    return switch (input) {
        case String text when !text.isBlank() ->
                "title=" + text.trim();
        case String text ->
                "empty or blank";
        default ->
                "not text";
    };
}
~~~

- Trong guard `when !text.isBlank()`, biến `text` đã được tạo từ `String text` và chắc chắn có kiểu `String`.
- Trong biểu thức ở bên phải `->`, `text` của nhánh đó cũng hợp lệ.
- Biến `text` của nhánh đầu **không dùng được bên ngoài nhánh** để xử lý `default`, hoặc ở vị trí sau câu lệnh `switch`.
- Nhánh `case String text` kế tiếp có thể khai báo **một biến `text` khác**, vì hai case arm tách biệt.
- Nếu bạn dùng `case Integer number` ở nhánh khác, nó có tên/kiểu riêng.

Cú pháp `case Type variable -> ...` cũng dùng trong **switch statement**:

~~~java
static void print(Object input) {
    switch (input) {
        case String text -> System.out.println(text.length());
        case Integer number -> System.out.println(number + 1);
        default -> System.out.println("other");
    }
}
~~~

Sự khác biệt ở đây là statement thực thi tác dụng phụ và không trả giá trị của `switch`, còn switch expression `return switch (...) { ... };` phải tạo một giá trị trên mọi nhánh.

### Nhãn dạng `:` và lý do nên ưu tiên `->` khi học pattern

Java 21 vẫn hỗ trợ cách viết `case String text:` trong switch statement, nhưng quy tắc kiểm soát scope và **fall-through** của những nhãn mang pattern variable có thể khiến chương trình bị compiler từ chối khi một luồng thực thi có nguy cơ đi vào nhánh mà biến pattern chưa được khởi tạo.

Ví dụ với từng nhánh `->` như bài này cho thấy rõ biến nào chỉ thuộc nhánh nào, và tránh rủi ro rơi xuyên giữa các nhãn. Nếu phải đọc code dạng `:`, hãy kiểm tra luồng vào nhãn, việc `break`/`yield` và phạm vi biến trước khi sửa.

## 5. `null`: `default` không tự bắt giá trị null

Đối với switch pattern của Java 21, `null` cần được xử lý có chủ ý:

~~~java
static String describe(Object value) {
    return switch (value) {
        case null -> "null value";
        case String s -> "string=" + s;
        default -> "other";
    };
}
~~~

`case null` là **nhãn đặc biệt**, không phải type pattern. Nó xử lý selector `null` trước khi các type pattern thông thường được xem xét. Nếu bỏ `case null`, một pattern switch với selector `null` thông thường ném `NullPointerException`; **`default` không bắt `null`**.

Ví dụ sau **biên dịch** nhưng có thể ném `NullPointerException` khi truyền `null`:

~~~java
static String withoutNullCase(Object value) {
    return switch (value) {
        case String s -> "string";
        default -> "default";
    };
}

// withoutNullCase(null) -> NullPointerException.
~~~

Nếu muốn dùng một nhánh cho cả các đối tượng còn lại và `null`, cú pháp Java 21 cho phép:

~~~java
static String withCombinedDefault(Object value) {
    return switch (value) {
        case String s -> "string";
        case null, default -> "other or null";
    };
}
~~~

**Phân biệt:** `case String s` không match `null`. `case null` chỉ có nhiệm vụ bắt null; `case null, default` gộp tình huống null và các trường hợp còn lại trong một nhánh, không đưa ra biến pattern mới.

## 6. Dominance: nhãn tổng quát không được che nhãn cụ thể ở phía sau

**Dominance** là quy tắc compiler dùng để ngăn một nhãn `case` trở thành nhánh không thể đến được vì **mọi giá trị mà nó xử lý** đã bị một nhãn trước đó bao phủ.

Mã sau **cố ý không biên dịch**:

~~~java
static String brokenOrder(Object value) {
    return switch (value) {
        case CharSequence seq -> "character sequence";
        case String text -> "string"; // ERROR: bị nhánh trước che phủ.
        default -> "other";
    };
}
~~~

Bởi `String implements CharSequence`, mọi đối tượng `String` đều match `CharSequence`; nhánh `String` đặt sau không bao giờ được chọn.

**Sửa bằng cách đặt nhánh cụ thể trước:**

~~~java
static String correctOrder(Object value) {
    return switch (value) {
        case String text -> "string=" + text;
        case CharSequence seq -> "other sequence=" + seq.length();
        default -> "other";
    };
}
~~~

Đến nhánh `CharSequence`, mọi `String` đã được xử lý; chỉ còn `StringBuilder` hoặc các triển khai khác.

### Guard và dominance

Mã sau **cố ý lỗi biên dịch**:

~~~java
static String brokenGuardOrder(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isBlank() -> "blank"; // ERROR: bị che phủ.
        default -> "other";
    };
}
~~~

Một nhánh `case String s` **không có guard** ở trên đã xử lý toàn bộ `String`. Vì vậy, đặt nhánh được guard sau nó là vô nghĩa.

Cách đúng:

~~~java
static String correctGuardOrder(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "other string";
        default -> "not a string";
    };
}
~~~

Với guard có điều kiện thông thường, compiler không thể giả định nó luôn đúng. Vì thế một nhánh hẹp hơn có guard có thể đứng trước nhánh tổng quát cùng kiểu. Trường hợp guard có điều kiện hằng `true` được ngôn ngữ xem xét đặc biệt khi xác định dominance.

**Thực hành:** sắp xếp theo thứ tự từ **kiểu cụ thể → kiểu rộng hơn → default**, đồng thời đặt các guard cho trường hợp đặc biệt trước trường hợp cùng kiểu không có guard.

## 7. Exhaustiveness: một switch pattern cần bao phủ trường hợp nào?

**Switch expression** phải có cách tạo ra kết quả cho mọi giá trị thuộc tập kiểu hợp lệ của selector. Với **enhanced switch statement** có type pattern trong Java 21, yêu cầu exhaustiveness cũng áp dụng. Khác với một số switch statement truyền thống chỉ dùng hằng số, pattern switch thiếu nhánh phù hợp có thể lỗi biên dịch.

Mã sau **cố ý không biên dịch**:

~~~java
static String incomplete(Object value) {
    return switch (value) {
        case String text -> text;
        // ERROR: còn vô số loại Object chưa được xử lý.
    };
}
~~~

Sửa bằng `default`:

~~~java
static String complete(Object value) {
    return switch (value) {
        case String text -> text;
        default -> "not text";
    };
}
~~~

Sửa kiểu khác bằng một type pattern **bao phủ mọi đối tượng không null**:

~~~java
static String completeWithType(Object value) {
    return switch (value) {
        case null -> "null";
        case String text -> "String=" + text;
        case Object any -> "Object=" + any.getClass().getSimpleName();
    };
}
~~~

- `case Object any` là pattern bao phủ mọi giá trị **không null** có thể được gán cho `Object`. Không cần thêm `default`.
- `case null` vẫn cần nếu chức năng mong muốn xử lý null mà không ném exception. Tính đầy đủ của các nhánh cho giá trị tham chiếu không null và xử lý `null` là hai ý khác nhau.
- Đừng đặt `case Object any` trước `case String text`: nhánh `String` sẽ bị dominance.
- Đừng thêm `default` **sau** nhánh `case Object any` trong ngữ cảnh kiểu selector `Object`: nhánh tổng quát đã bao phủ những giá trị thông thường còn lại, và compiler có thể từ chối một nhánh dư thừa.

### Kiểu `sealed`: compiler có thể suy ra các trường hợp đầy đủ

Java 21 có thể xét tập subclass được phép của một kiểu `sealed` để xác định switch có exhaustive hay không. Ví dụ **độc lập với chương trình ở phần 9**, đặt trong một lớp như sau:

~~~java
public class SealedCaseExample {
    sealed interface Shape permits Circle, Square {}
    record Circle(int radius) implements Shape {}
    record Square(int edge) implements Shape {}

    static String label(Shape shape) {
        return switch (shape) {
            case Circle c -> "circle=" + c.radius();
            case Square s -> "square=" + s.edge();
        };
    }

    public static void main(String[] args) {
        System.out.println(label(new Circle(3)));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac --release 21 SealedCaseExample.java
java SealedCaseExample
~~~

**Stdout:**

~~~text
circle=3
~~~

Không cần `default` vì các subclass được phép `Circle` và `Square` đều đã có nhánh. Đây là ví dụ về exhaustiveness dựa trên **hệ thống kiểu**, không phải một thủ thuật runtime. Nếu cần xử lý `null` theo nghiệp vụ, thêm `case null`; thiếu nhãn này, giá trị null không tự trở thành một `Shape` match.

## 8. Những cách viết không tương đương nhau

| Cách viết | Là type pattern? | Ý nghĩa |
| --- | --- | --- |
| `case String text ->` | **Có** | Nếu selector là `String`, bind `text` kiểu `String` |
| `case Integer n ->` | **Có** | Match wrapper `Integer` và bind `n` |
| `case String s when s.isBlank() ->` | **Có, với guard** | Match `String` trước, rồi kiểm tra điều kiện |
| `case null ->` | Không | Bắt giá trị `null` riêng |
| `default ->` | Không | Bắt các giá trị không null chưa được chọn |
| `case null, default ->` | Không | Gộp nhãn null và default |
| `case "READY" ->` | Không | Nhãn hằng chuỗi trong những ngữ cảnh selector cho phép |
| `case Point(int x, int y) ->` | Không phải **type pattern đơn** | Đây là **record pattern**, phân rã record; là chủ đề riêng |
| `case int n ->` | Không hợp lệ theo Java 21 chính thức | Đừng nhầm với `case 1 ->` là nhãn hằng trong switch số |

**Không thể gom tùy ý nhiều type patterns có binding khác nhau** vào một nhãn dạng `case String s, Integer i ->` rồi giả định cả `s` và `i` đều luôn được khởi tạo. Java 21 có quy tắc kiểm soát fall-through và pattern bindings; cách diễn đạt rõ nhất là dùng các case arm riêng:

~~~java
static String separate(Object input) {
    return switch (input) {
        case String s -> "String " + s;
        case Integer i -> "Integer " + i;
        default -> "Other";
    };
}
~~~

Ở đây **mỗi nhánh sở hữu biến pattern của riêng nó**. Có thể đặt cùng tên ở các nhánh độc lập, chẳng hạn `case String value ->` và `case Integer value ->`, nhưng việc đặt tên theo kiểu (`text`, `number`) thường giúp đọc code dễ hơn.

## 9. Ví dụ Java 21 hoàn chỉnh: type pattern, guard và null

Lưu toàn bộ mã vào **`SwitchTypeCaseExample.java`**:

~~~java
public class SwitchTypeCaseExample {

    static String describe(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank text";
            case String s -> "text: " + s.toUpperCase();
            case Integer n when n > 0 -> "positive int: " + n;
            case Integer n -> "int: " + n;
            case Number n -> "number: " + n;
            default -> "other";
        };
    }

    static String classify(CharSequence cs) {
        return switch (cs) {
            case null -> "null";
            case String s -> "String length=" + s.length();
            case StringBuilder b -> "builder length=" + b.length();
            default -> "another sequence";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe("  "));
        System.out.println(describe(7));
        System.out.println(describe(-2));
        System.out.println(describe(2.5));
        System.out.println(describe(new Object()));
        System.out.println(describe(null));
        System.out.println(classify(new StringBuilder("abc")));
    }
}
~~~

Biên dịch/chạy bằng **JDK 21+** và dùng chế độ nguồn Java 21:

~~~bash
javac --release 21 SwitchTypeCaseExample.java
java SwitchTypeCaseExample
~~~

**Stdout chính xác:**

~~~text
text: JAVA
blank text
positive int: 7
int: -2
number: 2.5
other
null
builder length=3
~~~

Diễn giải:

1. `"Java"` match `String`; guard `isBlank()` sai, nên vào nhánh `String s` thứ hai. `s` có kiểu `String` nên gọi được `toUpperCase()`.
2. `"  "` (hai dấu cách) match guard `String s when s.isBlank()`, in `blank text`.
3. `7` khi truyền vào tham số `Object` được autobox thành `Integer`; guard `n > 0` đúng nên in `positive int: 7`.
4. `-2` vẫn match `Integer`, nhưng guard `n > 0` sai; nhánh `Integer n` tiếp theo in `int: -2`.
5. `2.5` là `Double`, thuộc `Number`, nên in `number: 2.5`.
6. `new Object()` không match các type pattern cụ thể và đi tới `default`.
7. `null` được xử lý tường minh qua `case null`; không ném `NullPointerException`.
8. `new StringBuilder("abc")` có kiểu runtime `StringBuilder` và selector `cs` có kiểu tĩnh `CharSequence`, nên nhánh `StringBuilder b` in `builder length=3`.

**Khi dùng chương trình riêng:** hãy giữ đúng tên tệp và public class. Đoạn này không cần `--enable-preview` nếu biên dịch theo Java 21 như hướng dẫn.

## 10. Những lỗi thường gặp và cách sửa

### Lỗi 1 — Đặt nhánh tổng quát trước nhánh cụ thể

~~~java
return switch (value) {
    case Number n -> "number";
    case Integer i -> "integer"; // ERROR: Integer đã thuộc Number.
    default -> "other";
};
~~~

**Sửa:** xử lý `Integer` trước `Number`.

### Lỗi 2 — Đặt nhánh không guard trước nhánh có guard cùng kiểu

~~~java
return switch (value) {
    case String s -> "any string";
    case String s when s.length() > 10 -> "long"; // ERROR: bị che phủ.
    default -> "other";
};
~~~

**Sửa:** đặt `case String s when s.length() > 10` trước `case String s`.

### Lỗi 3 — Quên exhaustiveness

~~~java
return switch (value) {
    case String s -> s;
};
~~~

Nếu `value` có kiểu tĩnh `Object`, compiler từ chối vì còn nhiều kiểu khác. **Sửa:** thêm `default` hoặc pattern bao phủ toàn bộ tập giá trị thuộc kiểu selector.

### Lỗi 4 — Nghĩ rằng default luôn xử lý null

~~~java
return switch (value) {
    case String s -> s;
    default -> "other";
};
~~~

**Khi `value == null`:** thường ném `NullPointerException` trong Java 21. **Sửa:** thêm `case null` nếu null là đầu vào hợp lệ.

### Lỗi 5 — Dùng biến pattern ngoài nhánh match

~~~java
switch (value) {
    case String s -> System.out.println(s.length());
    default -> System.out.println("other");
}
System.out.println(s); // ERROR: s không thuộc scope ở đây.
~~~

**Sửa:** dùng `s` trong nhánh được bind, hoặc đưa kết quả cần giữ ra biến khác bằng switch expression trả giá trị.

### Lỗi 6 — Dùng kiểu không áp dụng được cho selector

~~~java
Integer number = 3;
return switch (number) {
    case String s -> "string"; // ERROR: không tương thích về kiểu.
    default -> "other";
};
~~~

**Sửa:** chọn pattern có quan hệ kiểu hợp lệ hoặc thay đổi kiểu đầu vào nếu thực sự cần xử lý nhiều loại.

### Lỗi 7 — Nhầm bản Java và cú pháp preview cũ

Trên Java 21, guard dùng `when`, ví dụ `case String s when s.length() > 3 ->`. Một số ví dụ preview cũ từng dùng cú pháp `&&` trong nhãn guard; không sao chép nguyên sang Java 21. Nếu dùng JDK 17 để biên dịch bài Java 21, sẽ gặp lỗi phiên bản hoặc preview. Hãy biên dịch bằng `javac --release 21` trên JDK 21+.

### Lỗi 8 — Coi type pattern là cast có thể dùng mọi nơi

`case String s` chỉ sinh biến `s` khi nhánh tương ứng match. Nó không sửa kiểu tĩnh của selector `value` vốn là `Object` và không khiến một nhánh khác tự sử dụng được `s`. Muốn làm việc với biến đúng kiểu trong nhánh khác, cần một pattern/binding riêng.

## 11. Quy trình tự phân tích một pattern switch

Khi đọc một đoạn `switch` có type patterns, hãy làm theo thứ tự:

1. **Đọc selector:** `switch (expression)`; kiểu tĩnh của biểu thức là gì, nó có thể nhận `null` không?
2. **Đọc từng nhãn:** `case T variable`, `case null`, hằng số, hay `default`? Type pattern là nhãn nào?
3. **Kiểm tra tương thích kiểu:** selector có thể downcast sang kiểu pattern không? Một `Integer` không thể được dùng như `String`.
4. **Đánh giá thứ tự và guard:** nhánh nào có thể match trước? Có `when` để giới hạn một trường hợp? Nhánh tổng quát có che mất nhánh hẹp không?
5. **Kiểm tra exhaustiveness và null:** mọi kiểu hợp lệ có đường xử lý chưa? Nếu `null` được phép, đã có `case null` chưa?
6. **Kiểm tra flow scoping:** biến pattern có được khai báo và sử dụng trong đúng guard/arm không? Có cast thừa hoặc truy cập ngoài scope không?
7. **Dự đoán stdout theo giá trị runtime** bằng cách chạy qua từng case theo đúng thứ tự và điều kiện.

## 12. Bài tập và đáp án

**Câu 1.** Với `Object x = "abc";` và `switch (x)` có `case String s -> s.length()`, `s` có kiểu tĩnh gì? Có cần cast `x` trước khi dùng `s.length()` không?

**Câu 2.** Vì sao `case CharSequence cs` đứng trước `case String s` làm compiler từ chối nhánh sau? Sửa bằng cách nào?

**Câu 3.** Với `Object x = "";`, các nhãn sau trả gì và vì sao?

~~~java
case String s when s.isEmpty() -> "empty";
case String s -> "non-empty";
default -> "other";
~~~

**Câu 4.** Nếu chuyển nhánh `case String s -> "non-empty"` lên trước nhánh có guard trong câu 3, trình biên dịch xử lý thế nào?

**Câu 5.** Với `switch (value)` trên selector kiểu `Object` có `case String s` và `default`, truyền `null` sẽ vào nhánh nào trên Java 21?

**Câu 6.** Vì sao `return switch (value) { case Integer i -> "number"; };` không hợp lệ khi `value` là `Object`? Hãy nêu hai hướng xử lý hợp lệ.

**Câu 7.** Hai nhãn `case String value ->` và `case Integer value ->` trong hai arm riêng có thể tái sử dụng tên `value` không? Biến pattern này có dùng được sau `switch` không?

**Câu 8.** `StringBuilder` implements `CharSequence`. Với selector kiểu `CharSequence` chứa `new StringBuilder("ab")`, `case String s` hay `case StringBuilder b` được chọn nếu đặt các nhãn theo thứ tự đó?

**Câu 9.** Tại sao type pattern `case Integer n` khác nhãn hằng `case 1`? `case int n` có phải cú pháp chuẩn Java 21 không?

**Câu 10.** Với kiểu `sealed Shape permits Circle, Square`, vì sao switch có hai nhãn `case Circle c` và `case Square s` có thể là exhaustive mà không cần `default`? Điều đó có tự làm `null` match một nhãn không?

### Đáp án

1. `s` có kiểu `String` từ pattern; không cần cast.
2. `CharSequence` bao phủ mọi `String` nên nhánh sau bị dominance. Đặt `String` trước `CharSequence`.
3. Trả `"empty"`: kiểu `String` match và guard `isEmpty()` là `true`.
4. Nhánh có guard bị che; compiler báo dominated case.
5. Không phải `default`; nếu không có `case null`, switch pattern thường ném `NullPointerException`.
6. Không exhaustive vì còn nhiều kiểu `Object` khác. Thêm `default`, hoặc bổ sung pattern bao phủ các kiểu còn lại (ví dụ `case Object o`) theo thứ tự hợp lệ.
7. Có, hai case arm độc lập có scope riêng; không dùng được pattern variable ấy ở ngoài `switch`.
8. `case String s` không match `StringBuilder`; `case StringBuilder b` được chọn.
9. `Integer n` kiểm tra **kiểu runtime và bind biến**; `case 1` so sánh một giá trị hằng trong switch hợp lệ. Primitive type pattern `case int n` chưa là tính năng chuẩn Java 21.
10. Compiler biết tập subtype được phép của sealed type và đã bao phủ đủ `Circle`, `Square`. `null` vẫn là trường hợp riêng; muốn xử lý null, dùng `case null`.

## Nguồn chính thức để đối chiếu

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): type patterns, guards, null, dominance, exhaustiveness và các ví dụ.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): phạm vi tính năng chính thức trong JDK 21 và thay đổi so với preview.
- [Java Language Specification 21, `14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): nhãn case, pattern switch, dominance, exhaustiveness.
- [Java Language Specification 21, `15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): chọn nhánh, kiểm tra exhaustiveness và giá trị của switch expression.
- [Java Language Specification 21, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type pattern và cơ chế matching.
- [Java Language Specification 21, `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): phạm vi pattern variable.
