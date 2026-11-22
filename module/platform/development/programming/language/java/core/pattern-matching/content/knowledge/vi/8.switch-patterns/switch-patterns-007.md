# `default` trong pattern `switch` của Java

## 1. Vai trò của `default` là gì?

Trong **pattern matching for `switch`** (chính thức từ Java 21), các nhánh `case` có thể so khớp kiểu đối tượng, record pattern và điều kiện bảo vệ `when`. Nhãn `default` cung cấp **nhánh dự phòng** khi không có nhãn `case` khác áp dụng cho giá trị selector.

```java
static String describe(Object value) {
    return switch (value) {
        case String text -> "String: " + text;
        case Integer number -> "Integer: " + number;
        default -> "Other value";
    };
}
```

Với giá trị **khác `null`**:
- `"Java"` chọn `case String text`.
- `42` chọn `case Integer number`.
- `3.14` (một `Double`) không khớp hai pattern đã liệt kê, nên chọn `default`.

**Ngoại lệ quan trọng:** trong Java 21, `default` **tự nó không xử lý selector `null`**. Nếu selector là `null` và không có `case null`, `switch` ném `NullPointerException`. Muốn xử lý `null` một cách tường minh, cần thêm `case null` hoặc sử dụng dạng kết hợp `case null, default`.

`default` không khai báo pattern variable; vì thế không có biến như `text` hay `number` để dùng trong thân nhánh này. Khi cần một giá trị tổng quát, ta vẫn có thể tham chiếu selector đã được lưu vào biến bên ngoài (sau khi cân nhắc `null` và side effect).

## 2. Phân biệt ba bước: khớp pattern, kiểm tra guard, chọn `default`

Một `switch` có pattern xét các nhãn theo quy tắc áp dụng của ngôn ngữ. Với nhãn có `when`, cần pattern khớp **và** guard trả về `true` thì nhãn ấy mới được chọn.

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String s when s.isBlank() -> "blank text";
        case String s -> "text:" + s;
        case Integer n when n > 0 -> "positive int:" + n;
        default -> "other";
    };
}
```

Điểm cần hiểu:

1. `case null` xử lý selector đúng bằng `null`.
2. `case String s when s.isBlank()` chỉ áp dụng cho giá trị là `String` và toàn bộ ký tự thuộc loại khoảng trắng theo `String.isBlank()`, bao gồm chuỗi rỗng.
3. Nếu selector là `"Java"`, pattern `String s` ở nhánh đầu khớp nhưng guard `s.isBlank()` sai, nên `switch` xét tiếp `case String s` **không có guard**. Nhánh này được chọn.
4. Nếu selector là số nguyên dương như `7`, nhánh `Integer n when n > 0` được chọn.
5. Nếu selector là `-2`, type pattern `Integer n` khớp nhưng guard sai; vì không còn nhãn khác áp dụng, `default` được chọn.
6. Nếu selector là `3.14`, không pattern `String` hoặc `Integer` nào khớp, nên `default` được chọn.

Không nên hiểu `default` là “chỉ chạy khi mọi phép kiểm tra kiểu đều sai”. Nhánh `default` còn có thể chạy khi **một type pattern khớp nhưng guard không thỏa và không có nhánh nào khác tiếp nhận giá trị đó**.

| Giá trị selector | Nhánh được chọn | Kết quả |
| --- | --- | --- |
| `null` | `case null` | `null` |
| `"   "` | `case String s when s.isBlank()` | `blank text` |
| `"Java"` | `case String s` | `text:Java` |
| `7` | `case Integer n when n > 0` | `positive int:7` |
| `-2` | `default` sau guard sai | `other` |
| `3.14` | `default` vì không khớp pattern | `other` |

`case String s` **không bị coi là trùng hay bị nhánh trước che khuất** trong ví dụ này: nhánh trước có `when s.isBlank()` nên chỉ nhận một phần các chuỗi; nhánh sau tiếp nhận phần còn lại.

## 3. Chương trình Java 21 chạy độc lập

Lưu toàn bộ mã vào file **`PatternSwitchDefaultDemo.java`**:

```java
public class PatternSwitchDefaultDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank text";
            case String s -> "text:" + s;
            case Integer n when n > 0 -> "positive int:" + n;
            default -> "other";
        };
    }

    static String combined(Object value) {
        return switch (value) {
            case String s -> "string:" + s;
            case null, default -> "other-or-null";
        };
    }

    static String withoutNullCase(Object value) {
        return switch (value) {
            case String s -> "string:" + s;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {null, "   ", "Java", 7, -2, 3.14};

        for (Object value : inputs) {
            System.out.println(classify(value));
        }

        System.out.println(combined(null));
        System.out.println(combined(123));

        try {
            System.out.println(withoutNullCase(null));
        } catch (NullPointerException ex) {
            System.out.println("NullPointerException");
        }
    }
}
```

Biên dịch và chạy với JDK 21 hoặc mới hơn:

```bash
javac --release 21 PatternSwitchDefaultDemo.java
java PatternSwitchDefaultDemo
```

Đầu ra chính xác:

```text
null
blank text
text:Java
positive int:7
other
other
other-or-null
other-or-null
NullPointerException
```

Chương trình chứng minh đồng thời bốn quy tắc: guard có thể dẫn đến fallback; `default` xử lý các giá trị non-null không được nhánh khác tiếp nhận; `case null, default` xử lý được cả `null`; và `default` đứng riêng **không** ngăn `NullPointerException` do selector `null`.

## 4. `default` có bắt `null` không?

**Không, nếu dùng `default` đơn lẻ.** Java 21 duy trì hành vi tương thích với các `switch` trước đây: selector `null` mà không có nhãn `case null` vẫn gây `NullPointerException`, kể cả khi có `default`.

```java
static String label(Object value) {
    return switch (value) {
        case String s -> s;
        default -> "other";
    };
}

// label(12)   => "other"
// label(null) => NullPointerException
```

Điều này khác với suy nghĩ phổ biến rằng “default bắt tất cả”. Phạm vi dự phòng của `default` đơn lẻ là các **giá trị non-null** chưa được nhánh khác xử lý.

Có hai cách xử lý `null`:

**Cách A: `case null` độc lập**, khi muốn phân biệt rõ dữ liệu thiếu với dữ liệu thuộc kiểu khác:

```java
return switch (value) {
    case null -> "missing value";
    case String s -> "text:" + s;
    default -> "unsupported type";
};
```

**Cách B: `case null, default` kết hợp**, khi `null` và các kiểu còn lại có **cùng chính sách xử lý**:

```java
return switch (value) {
    case String s -> "text:" + s;
    case null, default -> "anything else";
};
```

`case null, default` là một nhãn kết hợp đặc biệt, áp dụng cho `null` và mọi giá trị chưa được những nhãn trước đó tiếp nhận. Đây là cú pháp hợp lệ trong Java 21. Không được kết hợp `null` với một pattern khai báo biến theo kiểu `case null, String s ->`: sự kết hợp đó không hợp lệ vì nhánh `null` sẽ không có giá trị để khởi tạo `s`.

**Quy tắc lựa chọn:** muốn báo lỗi hoặc xử lý riêng `null`, viết `case null`; muốn dùng chung đường xử lý, viết `case null, default`. Không bỏ qua khả năng `null` chỉ vì đã có `default`.

## 5. `default` và tính đầy đủ của `switch` (exhaustiveness)

### 5.1. `switch` expression phải đầy đủ

Một `switch` expression phải có khả năng tạo ra giá trị (hoặc ném ngoại lệ) cho mọi giá trị thuộc miền kiểu mà compiler xét là có thể có. Ví dụ:

```java
// SAI với Java 21: switch expression không exhaustive.
// static String classify(Object value) {
//     return switch (value) {
//         case String s -> "text";
//         case Integer n -> "integer";
//     };
// }
```

Kiểu tĩnh `Object` còn rất nhiều khả năng như `Double`, `Boolean`, `List`... Nếu không có pattern đủ rộng hoặc `default`, compiler từ chối mã vì chưa bao phủ hết.

Thêm `default` sẽ cho phép biên dịch:

```java
static String classify(Object value) {
    return switch (value) {
        case String s -> "text";
        case Integer n -> "integer";
        default -> "other";
    };
}
```

Ở mức **compile time**, `default` giúp chứng minh tính đầy đủ đối với các giá trị non-null còn lại. Điều đó **không** thay thế việc xử lý `null` nếu runtime có thể truyền vào `null`.

### 5.2. Enhanced `switch` statement cũng phải đầy đủ

Trong Java 21, `switch` statement là **enhanced** nếu dùng pattern label, `case null`, hoặc selector có kiểu ngoài các kiểu `switch` cũ được hỗ trợ. Loại statement này cũng **bắt buộc exhaustive**.

```java
static void printType(Object value) {
    switch (value) {
        case String s -> System.out.println("String: " + s);
        case Integer n -> System.out.println("Integer: " + n);
        default -> System.out.println("Other");
    }
}
```

Nếu bỏ `default`, statement trên không có nhánh xử lý cho nhiều kiểu `Object` còn lại và không biên dịch.

Ngược lại, một **legacy `switch` statement** không dùng pattern/null trên kiểu selector truyền thống như `int`, `String` hoặc enum có thể thiếu `default` mà vẫn biên dịch:

```java
static void printNumber(int n) {
    switch (n) {
        case 1 -> System.out.println("one");
        case 2 -> System.out.println("two");
        // Legacy statement: không bắt buộc default.
    }
}
```

Vì vậy, không nên áp dụng máy móc quy tắc của legacy `switch` cho pattern `switch` mới. `switch` expression luôn đòi hỏi exhaustiveness; enhanced `switch` statement cũng vậy.

## 6. Không phải pattern `switch` nào cũng cần `default`

Nếu các pattern hoặc constant đã **bao phủ hoàn toàn kiểu selector**, `switch` vẫn có thể exhaustive mà không cần `default`.

Trường hợp điển hình là **sealed hierarchy**: compiler biết các subtype được phép. Trong Java 21:

```java
sealed interface Shape permits Circle, Rectangle {}

record Circle(int radius) implements Shape {}

record Rectangle(int width, int height) implements Shape {}

static String kind(Shape shape) {
    return switch (shape) {
        case Circle c -> "circle:" + c.radius();
        case Rectangle r -> "rectangle:" + (r.width() * r.height());
    };
}
```

Dù không có `default`, compiler thấy tất cả concrete subtype trực tiếp được phép của `Shape` đã được bao phủ. Đoạn minh họa trên là các khai báo phải đặt trong cùng ngữ cảnh chương trình Java hợp lệ (hoặc dùng chương trình đầy đủ ngay bên dưới).

**Chương trình Java 21 độc lập** (`ShapeSwitchDemo.java`):

```java
public class ShapeSwitchDemo {
    sealed interface Shape permits Circle, Rectangle {}

    record Circle(int radius) implements Shape {}

    record Rectangle(int width, int height) implements Shape {}

    static String describe(Shape shape) {
        return switch (shape) {
            case Circle c -> "circle:" + c.radius();
            case Rectangle r -> "rectangle:" + (r.width() * r.height());
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Circle(2)));
        System.out.println(describe(new Rectangle(3, 4)));

        try {
            System.out.println(describe(null));
        } catch (NullPointerException ex) {
            System.out.println("null => NullPointerException");
        }
    }
}
```

Chạy:

```bash
javac --release 21 ShapeSwitchDemo.java
java ShapeSwitchDemo
```

Kết quả:

```text
circle:2
rectangle:12
null => NullPointerException
```

Có ba bài học ở đây:

1. **Exhaustive không đồng nghĩa với phải có `default`:** sealed hierarchy có thể được bao phủ bởi các pattern cụ thể.
2. **Exhaustive cũng không tự xử lý `null`:** truyền `null` mà không có `case null` vẫn gây `NullPointerException`.
3. **Không viết `default` đôi khi tốt hơn cho bảo trì:** nếu sau này thêm subtype được phép vào `Shape` và biên dịch lại source, compiler có thể yêu cầu cập nhật `switch` để xử lý subtype mới. Một `default` quá chung sẽ che đi tín hiệu này. Với thay đổi nhị phân xảy ra ngoài quá trình biên dịch lại, runtime Java 21 có thể ném `MatchException` khi giá trị không khớp bộ nhánh mà binary cũ tưởng là exhaustive; đừng xem `default` là cơ chế kiểm tra sự tiến hóa của sealed hierarchy.

Tương tự, một `switch` expression trên `enum` có thể không cần `default` nếu đã liệt kê hết các enum constant:

```java
enum State { NEW, DONE }

static String name(State state) {
    return switch (state) {
        case NEW -> "new";
        case DONE -> "done";
    };
}
```

Thêm `default` không phải lúc nào cũng sai, nhưng có thể làm mất cảnh báo hữu ích khi thêm constant hoặc subtype mới. Quyết định nên dựa vào việc bạn muốn xử lý các trường hợp tương lai bằng fallback hay muốn cập nhật từng nhánh một cách tường minh.

## 7. `default` không thay thế quy tắc dominance

Trong pattern `switch`, nhánh trước có thể **bao phủ** một nhánh sau: compiler báo lỗi nếu một nhánh không bao giờ được chọn do bị nhánh trước *dominate*.

```java
// SAI: String cũng là CharSequence; case String bị case trước che.
// static String invalid(Object value) {
//     return switch (value) {
//         case CharSequence cs -> "sequence";
//         case String s -> "string";
//         default -> "other";
//     };
// }
```

**Sửa:** đặt pattern cụ thể trước pattern rộng:

```java
static String describe(Object value) {
    return switch (value) {
        case String s -> "string";
        case CharSequence cs -> "sequence";
        default -> "other";
    };
}
```

Trong ví dụ hợp lệ, `String` được chọn bởi nhánh đầu; các `CharSequence` khác như `StringBuilder` có thể được nhánh sau tiếp nhận.

Một pattern không guard mà **unconditional cho kiểu selector** có thể thực hiện vai trò bao phủ tương tự `default`. Vì vậy, không được viết đồng thời một `case Object obj` vô điều kiện trên selector `Object` và một `default` riêng như hai nhánh dự phòng; compiler từ chối vì nhánh dự phòng bị che:

```java
// SAI: hai nhánh tổng quát trùng phạm vi non-null.
// return switch (value) {
//     case Object obj -> "object";
//     default -> "other";
// };
```

Cần lưu ý thêm **vị trí của `default`**: trong pattern `switch`, nên đặt `default` sau các pattern và `case null`. Theo JLS Java 21, `default` không được đặt trước một nhánh `case` có pattern hoặc `null` literal. Dạng `case null, default` cũng phải là nhánh cuối. Tổ chức theo thứ tự *cụ thể → tổng quát → dự phòng* giúp code dễ đọc và tránh lỗi dominance.

## 8. Guard `when` không được thay bằng `default` để giữ biến mẫu

Ví dụ sau phân loại các số nguyên:

```java
static String sign(Object value) {
    return switch (value) {
        case Integer n when n > 0 -> "positive: " + n;
        case Integer n when n < 0 -> "negative: " + n;
        case Integer n -> "zero";
        default -> "not integer";
    };
}
```

Ở đây `Integer n` không guard tiếp nhận trường hợp `0`; `default` chỉ nhận giá trị non-null không phải `Integer`. Phải dùng nhánh riêng nếu cần truy cập `n` ở trường hợp guard khác. Không thể viết:

```java
// SAI: n không được khai báo trong default.
// return switch (value) {
//     case Integer n when n > 0 -> "positive: " + n;
//     default -> "zero or other: " + n;
// };
```

Lý do: `default` có thể được chọn khi `value` là `String`, `Boolean` hoặc bất kỳ kiểu khác, nên không thể dùng `n` từ pattern thất bại ở đây. Nếu muốn mọi `Integer` đều có cùng tên biến, thêm `case Integer n` không guard sau các nhánh guard.

Một `switch` chỉ gồm các **guarded pattern** có thể không exhaustive vì compiler không thể bảo đảm điều kiện guard luôn trả về `true` cho mọi giá trị. `default` là một cách giải quyết; cách khác là thêm pattern unguarded bao phủ toàn bộ trường hợp còn lại.

**Tách bạch:** “nhánh bị guard loại” là kết quả logic khi chạy; “non-exhaustive” là lỗi bao phủ kiểu ở compile time. `default` có thể giải quyết yêu cầu bao phủ, đồng thời nhận các giá trị cụ thể còn sót lại, nhưng không biến `when` sai thành đúng.

## 9. Record pattern: component không khớp cũng có thể đi tới `default`

Trong Java 21, record pattern cho phép kiểm tra cả kiểu record lẫn các component. Một giá trị có thể đúng kiểu record nhưng pattern lồng bên trong không khớp:

```java
record Envelope(Object content) {}

static String unpack(Object input) {
    return switch (input) {
        case Envelope(String s) -> "text:" + s;
        case Envelope(Integer n) -> "number:" + n;
        case null -> "null input";
        default -> "unsupported content or type";
    };
}
```

Đây là đoạn minh họa đặt trong ngữ cảnh khai báo record hợp lệ, yêu cầu Java 21.

- `new Envelope("Java")` khớp `Envelope(String s)`.
- `new Envelope(5)` khớp `Envelope(Integer n)`.
- `new Envelope(null)` là record **khác null**, nhưng component `null` không khớp type pattern `String` hoặc `Integer`; đi tới `default`.
- `new Envelope(3.14)` cũng đi tới `default`.
- Selector `null` thì đi tới `case null`.

Điều này cho thấy `default` có thể tiếp nhận một **record có kiểu đúng nhưng dữ liệu bên trong không đáp ứng các pattern cụ thể**, chứ không chỉ các lớp hoàn toàn khác record.

Nếu phân loại dữ liệu đầu vào tùy ý, nên đặt thông điệp fallback có ý nghĩa (ví dụ “unsupported payload”) để người học không hiểu nhầm rằng mọi `Envelope` đều hợp lệ.

## 10. Dùng `default ->` hay `default:`?

Pattern `switch` hỗ trợ **switch rules** (dấu `->`) và **switch labeled statement groups** (dấu `:`), nhưng cách kiểm soát luồng khác nhau.

**Dạng `->`** thường rõ hơn và tránh fall-through:

```java
static String name(Object value) {
    return switch (value) {
        case String s -> "string:" + s;
        default -> "other";
    };
}
```

Nếu nhánh là block trong `switch` expression, dùng `yield` để trả giá trị:

```java
static int score(Object value) {
    return switch (value) {
        case String s -> s.length();
        default -> {
            int fallback = -1;
            yield fallback;
        }
    };
}
```

Trong `switch` statement, `default ->` có thể chứa lời gọi phương thức hoặc block lệnh thông thường:

```java
static void print(Object value) {
    switch (value) {
        case String s -> System.out.println(s);
        default -> System.out.println("Unsupported");
    }
}
```

**Dạng `:`** là statement group truyền thống; phải quản lý `break` và fall-through. Với nhánh pattern khai báo biến, fall-through vào nhánh cần pattern variable chưa được khởi tạo có thể là **lỗi biên dịch**. Vì thế, các ví dụ trong bài dùng `->` để thể hiện rõ một giá trị được chọn dẫn tới một nhánh duy nhất.

`default` không tự tạo giá trị cho một switch expression. Nếu nhánh `default -> { ... }` có block, phải `yield` một giá trị phù hợp hoặc hoàn thành đột ngột bằng ngoại lệ; một block chỉ in log rồi kết thúc mà không trả giá trị sẽ lỗi biên dịch.

## 11. Xử lý fallback trong thực tế: trả giá trị, ném ngoại lệ hay ghi nhận kiểu lạ?

Lựa chọn hành vi của `default` phụ thuộc ý nghĩa dữ liệu:

**Trả về giá trị thay thế** khi kiểu khác là tình huống dự kiến:

```java
static String display(Object value) {
    return switch (value) {
        case null -> "(missing)";
        case String s -> s;
        case Number n -> n.toString();
        default -> "(unsupported)";
    };
}
```

**Ném ngoại lệ có chủ đích** khi kiểu khác biểu thị vi phạm contract:

```java
static String requiredText(Object value) {
    return switch (value) {
        case String s -> s;
        case null -> throw new IllegalArgumentException("Missing text");
        default -> throw new IllegalArgumentException(
            "Unsupported type: " + value.getClass().getName()
        );
    };
}
```

`value.getClass()` an toàn trong nhánh `default` ở đây vì `case null` đã xử lý `null` và `default` đơn lẻ chỉ nhận non-null.

**Ghi nhận loại dữ liệu bất thường** (telemetry/log) khi dữ liệu đi qua ranh giới hệ thống, nhưng tránh im lặng nuốt lỗi thật. Nếu `default` chỉ trả chuỗi `"unknown"` cho mọi kiểu ngoài dự kiến, API có thể mất thông tin về một payload mới hoặc sai. Ngược lại, ở đường hiển thị UI, giá trị fallback là lựa chọn tốt để ứng dụng tiếp tục hoạt động.

Một nguyên tắc thực tế: với hệ kiểu **mở** như `Object`, `default` thường cần thiết. Với hệ kiểu **đóng** như sealed hierarchy có tập subtype đã được kiểm soát, nên cân nhắc bỏ `default` để compiler giúp phát hiện trường hợp mới.

## 12. Lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Cho rằng `default` tự xử lý `null` | Selector `null` không đi tới `default` đơn lẻ | Thêm `case null` hoặc `case null, default` |
| Thiếu `default` trong `switch(Object)` chỉ có vài pattern | Không exhaustive | Thêm nhánh dự phòng hoặc pattern đủ rộng |
| Dùng `default` để truy cập biến `s` khai báo ở `case String s` | `default` không có scope của `s` | Thêm nhánh `case String s` riêng hoặc dùng selector ngoài |
| Đặt `case CharSequence` trước `case String` | Pattern trước dominate pattern sau | Đặt kiểu cụ thể trước |
| Đặt `default` trước pattern trong Java 21 | Vi phạm quy tắc vị trí nhãn | Đặt `default` cuối |
| Dùng `case Object o` không guard và thêm `default` trên `Object` | Một pattern unconditional đã bao phủ các giá trị non-null | Chọn một hướng fallback |
| Nghĩ guard sai là lỗi compile time | Guard thường được đánh giá khi chạy | Thêm nhánh unguarded hoặc `default` cho kết quả guard không đạt |
| Thêm `default` vô điều kiện vào sealed `switch` | Có thể che việc thiếu xử lý subtype mới khi biên dịch lại | Đánh giá lợi ích exhaustiveness cụ thể |
| Dùng `case null, String s` | Không thể gắn `s` cho đường `null` | Dùng `case null` riêng hoặc `case null, default` |
| Nhầm `switch` statement legacy với enhanced | Quy tắc exhaustive khác nhau | Xem có pattern/null label và kiểu selector hay không |

## 13. Bài tập và đáp án

**Bài 1.** Đoạn sau có biên dịch không, và `classify(-1)` trả về gì?

```java
static String classify(Object x) {
    return switch (x) {
        case Integer n when n > 0 -> "positive";
        default -> "other";
    };
}
```

**Đáp án:** Có (Java 21+). `-1` là `Integer`, pattern khớp nhưng guard sai; `default` trả `"other"`. Nếu gọi với `null`, vẫn ném `NullPointerException` vì không có `case null`.

**Bài 2.** Vì sao đoạn sau lỗi biên dịch?

```java
// return switch (obj) {
//     case String s -> "string";
//     case Integer n -> "integer";
// };
```

**Đáp án:** Nếu `obj` có kiểu tĩnh `Object`, `switch` expression chưa exhaustive; thiếu nhiều kiểu khác. Thêm `default` hoặc một pattern khác bao phủ các trường hợp còn lại.

**Bài 3.** Với `switch (obj) { case String s -> ...; case null, default -> ...; }`, nhánh thứ hai nhận những giá trị nào?

**Đáp án:** Nhận selector `null` và mọi giá trị chưa được `case String s` nhận; ví dụ `new Object()` hoặc `12`. Đây là nhãn kết hợp hợp lệ.

**Bài 4.** Với `sealed interface Shape permits Circle, Rectangle`, đã có hai nhánh `case Circle` và `case Rectangle` không guard. Có bắt buộc thêm `default` không?

**Đáp án:** Không, nếu hai nhánh bao phủ toàn bộ các subtype được phép và compiler xác nhận exhaustive. Tuy nhiên, `null` vẫn cần `case null` nếu muốn xử lý mà không ném `NullPointerException`.

**Bài 5.** Trong `switch(Object)`, đặt `case CharSequence cs` trước `case String s` và thêm `default` có hợp lệ không?

**Đáp án:** Không. `String` luôn là một `CharSequence`, nên nhánh `String` bị nhánh trước dominate; thêm `default` không chữa lỗi. Hãy đặt `case String s` trước.

**Bài 6.** `new Envelope(null)` có đi vào `default` trong đoạn `case Envelope(String s)`, `case null`, `default` không?

**Đáp án:** Có, vì selector là một đối tượng record non-null nhưng component `null` không khớp `String s`. `case null` chỉ dành cho selector `null`.

## 14. Quy tắc ghi nhớ

- `default` là fallback cho **giá trị non-null chưa được case nào tiếp nhận**.
- `when` sai có thể dẫn tới một case khác hoặc `default`; guard được đánh giá khi runtime match phần pattern tương ứng.
- `case null` xử lý riêng selector `null`; `case null, default` gộp xử lý `null` với các giá trị còn lại.
- `switch` expression và enhanced `switch` statement cần exhaustive. `default` là một cách đạt điều kiện đó, nhưng sealed hierarchy và các tập enum constant được bao phủ đủ có thể không cần.
- `default` không chứa pattern variable; đặt các pattern cụ thể trước và nhánh dự phòng cuối để tránh dominance.
- Chọn hành vi fallback phù hợp: trả giá trị mặc định cho dữ liệu dự kiến, hoặc báo lỗi rõ khi giá trị vi phạm contract.

### Tài liệu chính thức

- [Oracle Java 21 — Pattern Matching for switch Expressions and Statements](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [Oracle Java 21 — Switch Expressions](https://docs.oracle.com/en/java/javase/21/language/switch-expressions-and-statements.html)
- [Java SE 21 JLS §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [Java SE 21 JLS §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
