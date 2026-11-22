# Nhầm pattern switch với switch cũ trong Java 21: phân biệt cú pháp, phạm vi và hành vi

## 1. Vấn đề và mục tiêu

Nhiều lỗi khi học **Java Core Pattern Matching** đến từ việc gọi mọi cú pháp mới của `switch` là "pattern switch", hoặc ngược lại áp các giả định của `switch` cổ điển cho `switch` có type/record patterns. Thực tế Java hiện đại có **ba trục khái niệm độc lập** cần phân biệt:

1. **Dạng cấu trúc:** `switch statement` chỉ điều khiển luồng lệnh; `switch expression` là một biểu thức tạo **giá trị**.
2. **Dạng nhãn:** nhãn hằng như `case 1`, `case "go"`, `case MONDAY` khác nhãn pattern như `case String s` hoặc `case Point(var x, var y)`.
3. **Dạng thân nhánh:** cú pháp cổ điển dùng `case ...:` và có thể *fall-through*; cú pháp rule `case ... ->` không tự fall-through sang rule sau.

Ba trục này **không đồng nghĩa**. Ví dụ `switch` với `case 1 ->` **chưa phải pattern matching**. Một `switch expression` cũng có thể dùng chỉ các hằng số, không cần pattern. Ngược lại, `switch statement` trong Java 21 vẫn có thể dùng `case String s:`, dù người học thường thấy `->` tiện và an toàn hơn.

Bài học tập trung vào cách **nhận diện và sửa các nhầm lẫn thường gặp**, cùng chương trình Java 21 để kiểm tra bằng thực tế.

**Các mốc phiên bản quan trọng:**

- `switch` truyền thống với hằng số và `case:` đã có từ những phiên bản Java đầu; hỗ trợ `enum` từ Java 5 và `String` từ Java 7.
- `switch expressions` và dạng rule `case ... ->` được chuẩn hóa trong Java 14 (JEP 361).
- `instanceof` pattern matching trở thành tính năng chuẩn trong Java 16 (JEP 394), **không đồng nghĩa** pattern matching trong `switch` cũng đã chuẩn từ Java 16.
- **Pattern matching for `switch`** (JEP 441) và **record patterns** (JEP 440) chuẩn từ **Java 21**.

Với những ví dụ `case Type variable`, `case Record(...)` hoặc `when` trong bài, dùng JDK 21 trở lên và biên dịch với `javac --release 21`; không cần bật preview.

## 2. Bảng phân biệt nhanh: cũ, mới và pattern

| Tiêu chí | `switch` statement cổ điển | `switch` statement dạng rule | `switch` với patterns trong Java 21 |
| --- | --- | --- | --- |
| Mục đích | Chọn và chạy lệnh | Chọn và chạy lệnh | Chọn nhánh theo kiểu/cấu trúc, có thể là statement hoặc expression |
| Ví dụ nhãn | `case 0:`, `case "go":` | `case 0 ->`, `case "go" ->` | `case String s ->`, `case Point(var x,var y) ->` |
| Biến được bind từ giá trị | Không, với nhãn hằng | Không, nếu chỉ có nhãn hằng | Có, ví dụ `s`, `x`, `y` |
| Fall-through | Có thể xảy ra khi không thoát nhánh | Không giữa các switch rules | Phụ thuộc `:`/`->`; pattern còn có giới hạn flow |
| `when` | Không phải guard của constant label truyền thống | Rule hằng không tự có guard | Dùng sau nhãn pattern: `case String s when ...` |
| `null` | `switch` trên reference `null` thường ném `NullPointerException` | Không tự xử lý `null` nếu thiếu case thích hợp | Có thể dùng `case null`; `default` không thay `null` |
| Kiểm tra coverage | Switch statement cổ điển có thể thiếu case | Tùy enhanced/traditional switch | Enhanced switch phải exhaustive; switch expression luôn exhaustive |
| Version tối thiểu của ví dụ | Tùy selector (`String` từ Java 7) | Java 14 khi dùng rule | Java 21 với các pattern chuẩn |

Đừng chỉ nhìn vào ký tự `->` để kết luận "đây là pattern switch". **Pattern matching nằm ở chính nhãn case**, không nằm ở mũi tên.

### 2.1. Một `switch` có thể vừa là expression vừa dùng nhãn hằng

Ví dụ Java 14+:

```java
static String label(int code) {
    return switch (code) {
        case 0 -> "zero";
        case 1, 2 -> "small";
        default -> "other";
    };
}
```

Đoạn trên trả một `String` từ switch expression, dùng rule `->`, nhưng **không có pattern variable**. Đây không phải ví dụ pattern matching.

### 2.2. Một `switch` có thể là statement nhưng vẫn dùng pattern

Java 21 cho phép:

```java
static String colonPattern(Object value) {
    switch (value) {
        case String s: return "pattern:" + s;
        case Integer i: return "number:" + i;
        case null: return "null";
        default: return "other";
    }
}
```

Đây là **switch statement** với nhãn có pattern và ký tự `:`. Mỗi nhánh ở ví dụ thoát bằng `return`; không có fall-through. Như vậy, "pattern switch bắt buộc viết `->`" là nhận định sai.

## 3. Switch cổ điển: hằng số, dấu `:` và fall-through

Trong dạng truyền thống, selector thường là kiểu nguyên thủy được hỗ trợ (ví dụ `int` và các kiểu số nguyên nhỏ hơn), các wrapper tương ứng, `String` hoặc `enum`. Case so với các **hằng số** hoặc enum constants, chứ không tạo biến dựa trên runtime type.

```java
static String classic(int code) {
    String result;
    switch (code) {
        case 0:
            result = "zero";
            break;
        case 1:
        case 2:
            result = "small";
            break;
        default:
            result = "other";
    }
    return result;
}
```

Với `code = 2`, chương trình bắt đầu tại `case 2:`, gán `"small"` rồi `break` thoát khỏi switch statement.

**Fall-through** là điều dễ nhầm nhất khi đổi sang kiểu mới. Với dấu `:`, nếu nhánh không có `break`, `return`, `throw` hoặc lệnh thoát thích hợp, luồng có thể chạy tiếp **các câu lệnh của nhánh kế**:

```java
static String fallThrough(int value) {
    StringBuilder result = new StringBuilder();
    switch (value) {
        case 1:
            result.append("one/");
        case 2:
            result.append("two/");
            break;
        default:
            result.append("other/");
    }
    return result.toString();
}
```

Kết quả: `fallThrough(1)` trả `"one/two/"` còn `fallThrough(2)` trả `"two/"`. Đây là fall-through **có thể có chủ đích**, nhưng cũng thường là bug do quên `break`. Khi review, cần hiểu điều kiện nào bắt đầu tại nhánh nào và lệnh nào thực sự dừng luồng.

### 3.1. Nhãn `String` của switch cũ không phải type pattern

```java
static String classicWord(String value) {
    switch (value) {
        case "go": return "go!";
        case "stop": return "stop!";
        default: return "unknown";
    }
}
```

`case "go"` so sánh với **giá trị chuỗi hằng**. Nó không có biến `s` và không bắt bất kỳ chuỗi nào khác. Trái lại, `case String s` của Java 21 là **type pattern**, có thể match mọi chuỗi không `null` và bind `s`.

Trong cách switch String cổ điển này, `classicWord(null)` ném `NullPointerException` trước khi chọn `default`.

## 4. Mũi tên `->` không tự biến switch thành pattern matching

Từ Java 14, dạng rule giúp tránh fall-through giữa các case:

```java
static String arrowStatement(String command) {
    String result;
    switch (command) {
        case "START" -> result = "started";
        case "STOP" -> result = "stopped";
        default -> result = "other command";
    }
    return result;
}
```

Ở đây:

- Vẫn là **statement**; `result` được gán rồi trả về ở dòng sau.
- Các `case` đều là hằng chuỗi, không hề bind pattern variable.
- Không cần `break` để ngăn code chạy sang rule tiếp theo.
- Cú pháp `->` không bảo đảm đầu vào `null` được xử lý; với `switch(String)` như trên, `null` vẫn ném `NullPointerException`.

**Khác biệt với switch expression:**

```java
static String expressionExample(String command) {
    return switch (command) {
        case "START" -> "started";
        case "STOP" -> "stopped";
        default -> "other command";
    };
}
```

Đây là **expression**: toàn bộ `switch(...) { ... }` tạo ra giá trị `String` để `return`. Chú ý dấu `;` sau dấu `}` và yêu cầu các nhánh cung cấp giá trị phù hợp.

Cả hai đoạn đều dùng hằng số và không có pattern matching. Có thể chuyển giữa chúng nếu giữ nguyên ngoại lệ, kiểu trả về và ưu tiên nhánh.

## 5. Pattern switch Java 21: `case Type variable` và `case Record(...)`

Pattern matching trong `switch` mở rộng nhãn `case` thành **mẫu kiểm tra giá trị**. Ví dụ:

```java
record Point(int x, int y) {}

static String kind(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank text";
        case String s -> "text:" + s.strip();
        case Point(var x, var y) when x == y -> "diagonal=" + x;
        case Point(var x, var y) -> "point=" + x + "," + y;
        case Integer n -> "integer=" + n;
        case Number n -> "number=" + n;
        case null -> "null";
        default -> "other";
    };
}
```

Những dòng có `case String s`, `case Integer n`, `case Number n` là **type patterns**; chúng kiểm tra kiểu runtime và tạo pattern variables. `Point(var x, var y)` là **record pattern**, vừa kiểm tra `Point` vừa lấy các component qua accessor.

Với selector kiểu `Object`, cách này có thể loại bỏ chuỗi `if (value instanceof ...) { ... } else if (...)` dài. Tuy vậy, không có nghĩa switch pattern "có thể nhận mọi kiểu selector mà switch cũ không nhận": quy tắc kiểu selector được mở rộng cho enhanced switch và vẫn phụ thuộc phiên bản ngôn ngữ. Trên **Java 21**, những pattern trong ví dụ hợp lệ.

### 5.1. `case String.class` không tương đương `case String s`

`String.class` là một giá trị kiểu `Class<String>`, **không** phải pattern kiểm tra xem `value` là `String`. Dùng nhãn `case String s` để match đối tượng, không dùng `case String.class` theo suy nghĩ "so class".

Nếu thực sự muốn phân loại các đối tượng `Class<?>` (thay vì đối tượng thông thường), đó là một bài toán khác.

### 5.2. Tên biến chỉ được dùng ở nơi pattern match

Trong nhánh:

```java
case String s -> "text:" + s.strip();
```

biến `s` có scope hợp lệ trong thân nhánh đó. Không lấy `s` của nhánh này dùng trực tiếp trong `case Integer n` hay ngoài toàn bộ `switch`. Khi dùng guard, biến pattern cũng có scope ở biểu thức `when` tương ứng.

## 6. Guard `when` khác điều kiện `if` lồng trong nhánh

Để xử lý chuỗi blank trước các chuỗi khác, viết:

```java
return switch (value) {
    case String s when s.isBlank() -> "blank";
    case String s -> "nonblank";
    case null -> "null";
    default -> "other";
};
```

Quá trình lựa chọn:

1. `case String s` thử match type.
2. Nếu thành công, `when s.isBlank()` mới được đánh giá.
3. Nếu guard đúng, lấy kết quả `"blank"`.
4. Nếu guard sai, tiếp tục xét case sau. `case String s` không guard sẽ match chuỗi còn lại.

**Cú pháp Java 21 là `when`**. Không viết lẫn vào nhãn bằng cách dùng `case String s && s.isBlank()` như một vài bài preview cũ, và không viết `value instanceof String s when s.isBlank()`. Với `instanceof`, dùng `value instanceof String s && s.isBlank()`.

### 6.1. Vì sao không đặt pattern tổng quát lên trước?

Đoạn sau **cố ý sai**:

```java
return switch (value) {
    case String s -> "any string";
    case String s when s.isBlank() -> "blank"; // bị dominated
    default -> "other";
};
```

Nhánh `String s` không guard đã nhận tất cả chuỗi non-null. Nhánh phía sau không thể được chọn, nên compiler báo **dominance error**.

Trong pattern switch, **thứ tự case là một phần của logic**, đặc biệt khi một giá trị có thể khớp nhiều pattern hoặc nhiều guard.

### 6.2. Guard không phải bộ giải mọi điều kiện nghiệp vụ

Compiler không chứng minh tùy ý mọi predicate trong `when` là đúng/sai. Một `when true` có quy tắc dominance đặc biệt, giống nhánh không guard, nhưng `when s.length() >= 0` không tự được compiler suy luận thành "nhận mọi String" cho mục đích dominance. Việc lựa chọn nhánh thực tế vẫn xét guard từ trên xuống.

Tối ưu cho người đọc: nhánh **chuyên biệt có guard** trước nhánh **không guard cùng kiểu**, sau đó mới tới kiểu cha nếu có.

## 7. Dominance: lỗi mà switch cũ ít gặp theo cách này

Một giá trị `String` cũng là `CharSequence`. Nếu viết:

```java
// CỐ Ý SAI: không biên dịch trong Java 21.
return switch (value) {
    case CharSequence seq -> "sequence";
    case String text -> "string"; // bị nhánh trước bao phủ
    default -> "other";
};
```

compiler báo nhãn `String` bị **dominated**. Sửa bằng cách đổi thứ tự:

```java
return switch (value) {
    case String text -> "string";
    case CharSequence seq -> "sequence";
    default -> "other";
};
```

Đây không chỉ là sở thích về readability. Ngôn ngữ bắt buộc tránh nhánh chắc chắn không có cơ hội được chọn do nhãn phía trước bao phủ.

Các quy tắc thường gặp:

- **Subtype trước supertype**: `Integer` trước `Number`, `String` trước `CharSequence`.
- **Case có guard trước case không guard cùng kiểu**.
- **Nhãn hằng cụ thể trước pattern không guard bao phủ giá trị đó**, ví dụ trong switch theo kiểu `Integer`, `case 0` trước `case Integer i`.
- **Record pattern hẹp trước pattern bao phủ rộng hơn**, ví dụ `Holder(Point(var x, var y))` trước `Holder(var p)` nếu cả hai áp dụng.
- Không thêm `default` cạnh một **unconditional pattern** bao phủ selector, chẳng hạn `case Object o` trong `switch(Object)` theo cấu trúc tạo xung đột; compiler có quy tắc riêng cho trường hợp đó.

### Dominance và fall-through là hai khái niệm khác nhau

Fall-through là việc **thực thi lệnh** sau một nhãn `case:` mà không thoát khối. Dominance là kiểm tra **tính bao phủ của nhãn** tại compile time. Thêm `break` không sửa được case bị dominated; đổi sang `->` cũng không sửa được quan hệ `CharSequence` bao phủ `String`.

## 8. Xử lý `null`: nhầm lẫn gây lỗi runtime phổ biến

Người chuyển chuỗi `if/else if` sang pattern switch rất dễ bỏ sót `null`.

Với `instanceof`:

```java
if (value instanceof String s) {
    return "text:" + s;
}
return "other"; // value == null cũng đến đây
```

Nếu refactor thành:

```java
return switch (value) {
    case String s -> "text:" + s;
    default -> "other";
};
```

thì **`value == null` không tự rơi vào `default`**; switch có thể ném `NullPointerException`. Nếu muốn bảo toàn fallback gốc, thêm:

```java
return switch (value) {
    case String s -> "text:" + s;
    case null -> "other";
    default -> "other";
};
```

Java 21 cũng hỗ trợ dạng:

```java
return switch (value) {
    case String s -> "text:" + s;
    case null, default -> "other";
};
```

Dạng kết hợp này phù hợp khi xử lý `null` và các loại không khớp bằng **cùng một kết quả**.

### 8.1. `null` ngoài và `null` bên trong record không giống nhau

`case Point(var x, var y)` không match selector `null`. Nhưng một **record object non-null** có component reference bằng `null` vẫn có thể match mẫu dùng `var`:

```java
record Started(String id) implements Event {}
// Event là sealed interface được khai báo ở ví dụ đầy đủ.

// new Started(null) vẫn match:
case Started(var id) -> "started without id";
```

Ở ví dụ này, `var id` có thể bind `null`. Nếu thay bằng nested type pattern `Started(String id)`, component `null` không match nested `String` pattern. Đừng lẫn quy tắc `null` ở selector ngoài với các giá trị component của record.

### 8.2. `default` không phải là "nếu null"

Trong cả kiểu cũ và mới, `default` không phải biểu thức `else` đặc biệt cho `null`. Với những switch trên reference có thể bằng `null`, viết test `null` riêng và xác định có cần `case null` hay giữ ngoại lệ hay không.

## 9. Switch statement và switch expression: tính đầy đủ khác nhau

Hai dạng nhìn gần giống nhau nhưng có hợp đồng khác:

**Switch statement cổ điển** có thể chỉ xử lý một số giá trị:

```java
static void process(int code) {
    switch (code) {
        case 1:
            System.out.println("one");
            break;
    }
    // Nếu code khác 1, statement không làm gì.
}
```

Đoạn trên hợp lệ vì statement truyền thống không buộc liệt kê hết trường hợp.

**Switch expression** phải **exhaustive**: bất kể selector thuộc trường hợp hợp lệ nào theo phân tích ngôn ngữ, biểu thức đều phải tạo kết quả hoặc kết thúc bất thường. Ví dụ thiếu `default` khi selector là `Object`:

```java
// CỐ Ý SAI: switch expression không exhaustive.
return switch (value) {
    case String s -> s;
};
```

Compiler báo `the switch expression does not cover all possible input values`.

**Enhanced switch statement** (ví dụ switch dùng patterns) trong Java 21 cũng có yêu cầu exhaustiveness. Đừng thấy từ khóa statement mà suy rằng có thể bỏ tất cả nhánh còn lại như switch cổ điển:

```java
// CỐ Ý SAI trong Java 21.
switch (value) {
    case String s -> System.out.println(s);
}
// Selector Object còn có nhiều kiểu khác: thiếu coverage.
```

Ví dụ trên không exhaustive và bị compiler từ chối. Có thể thêm `default` hoặc phân loại đủ các subtype theo quy tắc JLS.

### 9.1. Sealed hierarchy có thể exhaustive không cần `default`

Với một tập subtype được hạn chế:

```java
sealed interface Event permits Started, Stopped {}
record Started(String id) implements Event {}
record Stopped(int code) implements Event {}

static String eventKind(Event event) {
    return switch (event) {
        case Started(var id) when id != null && !id.isBlank() ->
                "started:" + id;
        case Started(var id) -> "started without id";
        case Stopped(var code) -> "stopped:" + code;
        case null -> "null event";
    };
}
```

Compiler biết `Event` chỉ có các subtype được phép. Nhánh `Started(var id)` không guard bao phủ những `Started` mà guard đầu tiên bỏ qua, còn nhánh `Stopped` xử lý subtype khác; không cần `default`. `case null` là lựa chọn **xử lý null tường minh**, không phải một subtype.

Điều này khác với `switch(Object)`: object có thể là rất nhiều kiểu không được liệt kê, nên thông thường cần `default` hoặc một cấu trúc thực sự bao phủ toàn bộ miền hợp lệ.

### 9.2. Dominance và exhaustiveness độc lập

- **Dominance:** một case sau có bị case trước bao phủ hoàn toàn không?
- **Exhaustiveness:** toàn bộ switch có đủ trường hợp theo miền selector không?

Có thể viết switch **exhaustive nhưng vẫn có case dominated** (không biên dịch), hoặc không có case dominated nhưng **thiếu coverage** (cũng không biên dịch với expression/enhanced switch). Hai lỗi cần sửa bằng hai phép kiểm tra khác nhau.

## 10. `return`, `break` và `yield` không có cùng vai trò

Trong switch statement cổ điển:

- `break;` kết thúc switch statement (nhưng không tự thoát khỏi method).
- `return value;` thoát khỏi method; có thể dùng ngay trong nhánh nếu kiểu trả về phù hợp.
- `throw` ném ngoại lệ.

Trong **switch expression**, giá trị của mỗi rule dạng expression được tạo trực tiếp:

```java
return switch (value) {
    case String s -> s.trim();
    case null -> "null";
    default -> "other";
};
```

Nếu một rule dùng block, muốn cung cấp giá trị cho switch expression phải dùng **`yield`**, không phải `return`:

```java
static String computed(Object value) {
    return switch (value) {
        case Point(var x, var y) -> {
            int sum = x + y;
            yield "sum=" + sum;
        }
        case String s -> "len=" + s.length();
        case null -> "null";
        default -> "other";
    };
}
```

Với `new Point(2, 3)`, kết quả là `"sum=5"`.

Đoạn **cố ý sai**:

```java
// LỖI: không thể return từ bên trong switch expression.
return switch (value) {
    case String s -> { return s; }
    default -> "other";
};
```

Java báo lỗi tương đương `attempt to return out of a switch expression`. Sửa bằng `yield s;` trong block, hoặc viết trực tiếp `case String s -> s;`.

### 10.1. Switch expression vẫn có thể dùng dấu `:`

Một nhầm lẫn khác: "switch expression bắt buộc dùng `->`". Java cho phép dạng colon với `yield`:

```java
static int colonExpression(int x) {
    return switch (x) {
        case 0: yield 10;
        default: yield 20;
    };
}
```

Đây là switch expression hợp lệ ở Java 21 và không có pattern. Tuy nhiên, để tránh nhầm fall-through và luồng điều khiển, dạng rule `->` thường rõ ràng hơn cho code mới. Trong một switch block, không trộn tùy tiện nhãn `:` và `->` của hai dạng khác nhau.

## 11. Chương trình Java 21 hoàn chỉnh: đối chiếu bằng hành vi thực tế

Tạo tệp **`LegacyAndPatternSwitchDemo.java`**. Chương trình gồm switch cổ điển, fall-through, switch statement dạng rule, type/record patterns, `when`, sealed hierarchy, `yield` và switch statement có pattern dùng dấu `:`. Nó cho thấy các khác biệt **không thể suy ra chỉ từ việc nhìn dấu mũi tên**.

```java
import java.util.function.Supplier;

public class LegacyAndPatternSwitchDemo {
    record Point(int x, int y) {}
    sealed interface Event permits Started, Stopped {}
    record Started(String id) implements Event {}
    record Stopped(int code) implements Event {}

    static String classic(int code) {
        String result;
        switch (code) {
            case 0:
                result = "zero";
                break;
            case 1:
            case 2:
                result = "small";
                break;
            default:
                result = "other";
        }
        return result;
    }

    static String fallThrough(int value) {
        StringBuilder result = new StringBuilder();
        switch (value) {
            case 1:
                result.append("one/");
            case 2:
                result.append("two/");
                break;
            default:
                result.append("other/");
        }
        return result.toString();
    }

    static String classicWord(String value) {
        switch (value) {
            case "go": return "go!";
            case "stop": return "stop!";
            default: return "unknown";
        }
    }

    static String arrowStatement(String command) {
        String result;
        switch (command) {
            case "START" -> result = "started";
            case "STOP" -> result = "stopped";
            default -> result = "other command";
        }
        return result;
    }

    static String kind(Object value) {
        return switch (value) {
            case String s when s.isBlank() -> "blank text";
            case String s -> "text:" + s.strip();
            case Point(var x, var y) when x == y -> "diagonal=" + x;
            case Point(var x, var y) -> "point=" + x + "," + y;
            case Integer n -> "integer=" + n;
            case Number n -> "number=" + n;
            case null -> "null";
            default -> "other";
        };
    }

    static String eventKind(Event event) {
        return switch (event) {
            case Started(var id) when id != null && !id.isBlank() ->
                    "started:" + id;
            case Started(var id) -> "started without id";
            case Stopped(var code) -> "stopped:" + code;
            case null -> "null event";
        };
    }

    static String computed(Object value) {
        return switch (value) {
            case Point(var x, var y) -> {
                int sum = x + y;
                yield "sum=" + sum;
            }
            case String s -> "len=" + s.length();
            case null -> "null";
            default -> "other";
        };
    }

    static String colonPattern(Object value) {
        switch (value) {
            case String s: return "pattern:" + s;
            case Integer i: return "number:" + i;
            case null: return "null";
            default: return "other";
        }
    }

    static String safe(Supplier<String> action) {
        try {
            return action.get();
        } catch (RuntimeException error) {
            return error.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        System.out.println("legacy 0: " + classic(0));
        System.out.println("legacy 2: " + classic(2));
        System.out.println("legacy 7: " + classic(7));
        System.out.println("fallthrough 1: " + fallThrough(1));
        System.out.println("fallthrough 2: " + fallThrough(2));
        System.out.println("old String: " + classicWord("go"));
        System.out.println("old null: " + safe(() -> classicWord(null)));
        System.out.println("arrow statement: " + arrowStatement("START"));
        System.out.println("type string: " + kind(" Java "));
        System.out.println("type blank: " + kind("   "));
        System.out.println("record diag: " + kind(new Point(3, 3)));
        System.out.println("record off: " + kind(new Point(2, 3)));
        System.out.println("int: " + kind(9));
        System.out.println("double: " + kind(2.5));
        System.out.println("null: " + kind(null));
        System.out.println("other: " + kind(new Object()));
        System.out.println("sealed: " + eventKind(new Started("A1")));
        System.out.println("sealed null component: " + eventKind(new Started(null)));
        System.out.println("sealed stopped: " + eventKind(new Stopped(7)));
        System.out.println("sealed null selector: " + eventKind(null));
        System.out.println("yield: " + computed(new Point(2, 3)));
        System.out.println("colon pattern: " + colonPattern("hi"));
    }
}
```

**Biên dịch/chạy:** sử dụng JDK 21+ ở thư mục chứa file.

```bash
javac --release 21 LegacyAndPatternSwitchDemo.java
java LegacyAndPatternSwitchDemo
```

**Kết quả stdout đã kiểm chứng:**

```text
legacy 0: zero
legacy 2: small
legacy 7: other
fallthrough 1: one/two/
fallthrough 2: two/
old String: go!
old null: NullPointerException
arrow statement: started
type string: text:Java
type blank: blank text
record diag: diagonal=3
record off: point=2,3
int: integer=9
double: number=2.5
null: null
other: other
sealed: started:A1
sealed null component: started without id
sealed stopped: stopped:7
sealed null selector: null event
yield: sum=5
colon pattern: pattern:hi
```

### 11.1. Phân tích các kết quả cần ghi nhớ

- **`classic`:** `case 1:` và `case 2:` dùng chung code; `break` ngăn fall-through ngoài dự kiến.
- **`fallThrough`:** đầu vào `1` đi qua cả phần `one/` và `two/` vì không có `break` ở nhánh thứ nhất.
- **`classicWord(null)`:** nhãn hằng chuỗi + `default` không tránh được `NullPointerException`; hàm `safe` chỉ bắt exception để chương trình tiếp tục chạy.
- **`arrowStatement`:** có `->` nhưng các case vẫn chỉ là hằng số chuỗi, chưa phải pattern.
- **`kind`:** `String` với guard đứng trước `String` chung, `Integer` đứng trước `Number`; record `Point` cho thấy tách component.
- **`kind(null)`:** nhánh `case null` chạy, không phải `default`.
- **`eventKind`:** switch trên sealed type exhaustive không cần `default`; record `Started(null)` khớp `Started(var id)` và được fallback theo guard.
- **`computed`:** block trong switch expression dùng `yield` để tạo giá trị.
- **`colonPattern`:** type pattern với dấu `:` vẫn hợp lệ khi luồng từng nhánh thoát đúng cách.

Kết quả đủ để phân biệt ba trục: statement/expression, constant/pattern labels và colon/arrow. Một chương trình lớn có thể phối hợp nhiều kiểu, nhưng nên dùng cấu trúc nhất quán và dễ review.

## 12. Những lỗi biên dịch thường gặp và cách sửa

Các đoạn dưới đây **cố ý không biên dịch**; đừng ghép chúng vào tệp chương trình chạy ở mục 11.

### 12.1. Dùng Java 17 cho pattern switch Java 21

```java
// CỐ Ý SAI khi biên dịch với javac --release 17.
return switch (value) {
    case String s -> s;
    default -> "other";
};
```

Trình biên dịch báo `patterns in switch statements are not supported in -source 17` (chẩn đoán có thể khác giữa các JDK). Điều này **không mâu thuẫn** với việc Java 17 có `instanceof String s`: `instanceof` pattern và `switch` pattern có lịch chuẩn hóa khác nhau.

**Sửa:** nâng source/release target lên Java 21 và bảo đảm runtime mục tiêu tương thích, hoặc giữ cách `if (value instanceof String s)` nếu dự án bắt buộc Java 17.

### 12.2. Pattern rộng đứng trước pattern hẹp

```java
// CỐ Ý SAI.
return switch (value) {
    case CharSequence seq -> "wide";
    case String text -> "narrow";
    default -> "other";
};
```

Compiler báo `this case label is dominated by a preceding case label`. **Sửa:** đặt `String` trước `CharSequence`.

### 12.3. Pattern không guard che nhánh có guard

```java
// CỐ Ý SAI.
return switch (value) {
    case String text -> "all";
    case String text when text.isBlank() -> "blank";
    default -> "other";
};
```

Nhánh sau bị dominated. **Sửa:** đặt nhánh `when` lên trên và nhánh tổng quát xuống dưới.

### 12.4. Không đầy đủ các kiểu của enhanced switch

```java
// CỐ Ý SAI: Object còn nhiều kiểu khác ngoài String.
return switch (value) {
    case String s -> s;
};
```

Compiler báo switch expression không bao phủ hết giá trị selector. Dạng enhanced switch **statement** với pattern mà thiếu những trường hợp khác cũng có thể bị từ chối:

```java
// CỐ Ý SAI: enhanced switch statement không exhaustive.
switch (value) {
    case String s -> System.out.println(s);
}
```

**Sửa:** thêm `default` hoặc bao phủ đủ các trường hợp theo selector type (ví dụ sealed hierarchy). Khi hành vi `null` cần được bảo toàn, xét `case null` riêng.

### 12.5. Thêm `default` cạnh unconditional pattern

```java
// CỐ Ý SAI:
return switch (value) {
    case Object obj -> "all objects";
    default -> "other";
};
```

Java 21 báo lỗi tương đương `switch has both an unconditional pattern and a default label`. **Sửa:** chọn cấu trúc tổng quát phù hợp, không khai báo hai nhãn bao phủ cạnh nhau theo cách bị cấm.

### 12.6. `return` thay cho `yield` bên trong switch expression

```java
// CỐ Ý SAI:
return switch (value) {
    case String text -> { return text; }
    default -> "other";
};
```

**Sửa:** `case String text -> text;` hoặc trong block dùng `yield text;`. Không nhầm `return` từ method với `yield` từ switch expression.

### 12.7. Coi `case null` là nhãn hằng thông thường của switch cũ

Trong Java 21, `case null` là cơ chế xử lý selector `null` tường minh của switch nâng cao; không được suy rằng switch `String` cổ điển từ Java 7 đã luôn hỗ trợ `case null`. Khi đọc code từ nhiều source level, hãy kiểm tra mức Java đích thay vì dựa vào JDK đang cài trên máy.

### 12.8. Cho rằng chuyển sang `->` sẽ sửa mọi bug

`->` loại bỏ fall-through giữa các rule, nhưng **không** giải quyết dominance, thiếu nhánh `null`, sai guard, exception trong accessor hoặc rủi ro thay đổi hợp đồng khi refactor logic cũ. Đánh giá riêng từng lớp vấn đề.

## 13. Ma trận kiểm thử khi chuyển switch cũ sang pattern switch

Nếu mục tiêu là refactor chứ không phải thay đổi nghiệp vụ, nên kiểm tra khả năng **bảo toàn hành vi**.

| Nhóm input / trường hợp | Kiểm tra ở switch cũ | Kiểm tra ở switch mới |
| --- | --- | --- |
| Hằng số đã khai báo | Chọn case tương ứng | Có còn nhận cùng giá trị/trả cùng kết quả không? |
| Hằng số chưa khai báo | `default` hoặc không làm gì | Có đổi thành return/exception khác không? |
| Fall-through chủ ý | Một input chạy nhiều block `case:` | Dạng `->` có mất side effect cũ không? |
| String non-null | So đúng hằng literal | Type pattern có lỡ nhận **mọi** String không? |
| `null` | Có thể NPE với legacy switch(String) | `case null` có đổi ngoại lệ thành fallback ngoài ý muốn không? |
| Subtype/implements interface | Nhánh if/else cũ ưu tiên theo thứ tự | Có giữ type pattern hẹp trước pattern rộng? |
| Record bình thường | Cast + accessor | Record pattern có cho kết quả và side effect tương đương? |
| Component record `null` | Logic cũ kiểm tra accessor và null thế nào? | Nested pattern/`var` có đổi hành vi không? |
| Guard `true`/`false` | Điều kiện `if`/`else` nào chạy? | Nhánh `when` và fallback có đúng thứ tự? |
| Switch expression | Mọi đường đi có return/yield hợp lệ? | Có đầy đủ nhánh và kiểu kết quả? |
| Sealed hierarchy | Tập subtype thực tế | Có xử lý đủ mọi permitted subtype khi thêm subtype mới? |

Với mã có side effect (ghi log, thay đổi object, gọi I/O hoặc thanh toán), phải kiểm tra cả **thứ tự và số lần thực hiện**, không chỉ so sánh chuỗi kết quả. Một `switch` expression gọn hơn không tự chứng minh có cùng semantics với nhiều `if`/`switch` lồng nhau.

### 13.1. Quy trình migration gợi ý

1. **Chốt target Java:** xác định build dùng source/release nào, runtime production tương thích ra sao.
2. **Chụp baseline:** ghi nhận đầu vào, đầu ra, exception, hành vi fall-through quan trọng.
3. **Phân loại cấu trúc cũ:** nhãn hằng hay kiểm tra runtime type qua `if/instanceof`? Statement hay đang muốn expression?
4. **Chọn hình thức mới có chủ đích:** chỉ muốn bỏ fall-through thì dùng rule `->`; muốn kiểm tra type/record thì dùng pattern labels.
5. **Xếp thứ tự nhánh:** subtype trước supertype; case có guard trước case không guard cùng kiểu; hằng số cụ thể trước pattern tổng quát nếu liên quan.
6. **Bảo toàn null:** quyết định rõ `case null`, giữ NPE, hoặc fallback được duyệt theo hợp đồng.
7. **Kiểm tra exhaustiveness:** selector Object khác với sealed type; expression và enhanced statement đều phải theo quy tắc bao phủ.
8. **So semantics:** test hồi quy, test biên, test exception, test side effects.
9. **Review diff và CI:** đảm bảo không trộn thay đổi nghiệp vụ chưa được phê duyệt vào refactor cú pháp.

## 14. Checklist dành cho code review

- [ ] Đã phân biệt rõ **statement/expression**, **constant/pattern labels**, **colon/arrow**.
- [ ] Build sử dụng Java version hỗ trợ cú pháp thực tế; `--release 21` cho pattern `switch`/record patterns chuẩn.
- [ ] `case "value"` và `case String s` không bị nhầm: một bên so hằng, bên kia match kiểu.
- [ ] Không đánh đồng `case ->` với pattern matching.
- [ ] Không mất fall-through có chủ đích khi đổi `case:` sang `->`.
- [ ] Với switch String hoặc reference, `null` có kết quả theo đúng contract; `default` không được giả định xử lý `null`.
- [ ] Guard có cú pháp `when` và sử dụng pattern variables đúng phạm vi.
- [ ] Không có case dominated: kiểu hẹp/guard cụ thể đứng trước kiểu rộng/không guard.
- [ ] Switch expression trả giá trị ở các nhánh, dùng `yield` đúng khi có block.
- [ ] Enhanced switch statement và switch expression thỏa exhaustiveness; sealed hierarchy được bao phủ theo subtype.
- [ ] Không trộn colon/arrow thiếu nhất quán trong cùng switch block; pattern case dùng dấu `:` không rơi qua nhánh có biến bind trái quy tắc.
- [ ] Đã test `null` selector, component null, subtype và giá trị biên.
- [ ] Đã chạy regression/CI trên commit được review; không đổi ngầm thứ tự side effect/exception.
- [ ] Nếu có thay đổi hành vi có chủ ý, nó được ghi rõ và có test riêng.

**Tiêu chí hoàn tất:** Người đọc chỉ nhìn một `switch` có thể nhận biết nó là statement hay expression, các case kiểm tra hằng hay pattern, case nào ưu tiên trước, mỗi đường đi có kết quả/thoát ra sao và `null` được xử lý thế nào. Code biên dịch với target Java của dự án và test chứng minh các tình huống quan trọng.

## 15. Câu hỏi tự kiểm tra

**1. `case 1 -> "one"` có phải pattern matching không?**  
Không. Đây là rule có nhãn hằng `1`. Dấu `->` là dạng thân nhánh, không phải dấu hiệu xác định pattern.

**2. `return switch(code) { case 0 -> "zero"; default -> "other"; };` có phải switch expression dù không có pattern?**  
Có. Switch expression tạo một giá trị; nó độc lập với việc có pattern variable hay không.

**3. `case String s:` có được dùng trong switch statement Java 21 không?**  
Có, khi các quy tắc về flow và nhánh được tuân thủ. Pattern không yêu cầu bắt buộc ký hiệu `->`.

**4. Vì sao `case String s` không giống `case "go"`?**  
`case String s` match các đối tượng String phù hợp và bind `s`; `case "go"` chỉ so với một giá trị chuỗi cụ thể.

**5. Khi nào switch statement kiểu cũ có thể fall-through?**  
Khi một nhánh `case:` không thoát bằng `break`, `return`, `throw` hoặc luồng tương đương trước khi chạy tiếp lệnh sau.

**6. Vì sao `case CharSequence cs` trước `case String s` bị lỗi ở Java 21?**  
Vì mọi String đều là CharSequence; nhánh rộng đứng trước làm nhánh String bị dominated.

**7. `default` có tự xử lý selector `null` của pattern switch không?**  
Không. Thường cần `case null` hoặc chủ động chấp nhận `NullPointerException`, tùy hợp đồng.

**8. Trong `case Point(var x,var y) when x==y`, lúc nào `when` được đánh giá?**  
Sau khi record pattern đã match và các biến `x`, `y` đã được bind.

**9. Tại sao dùng `return` bên trong block switch expression lại sai?**  
Switch expression cần giá trị của chính nó: block sử dụng `yield`; `return` từ method không được phép thoát khỏi switch expression như vậy.

**10. Switch statement có pattern mà thiếu `default` luôn hợp lệ vì statement không cần kết quả?**  
Không. Enhanced switch statement có yêu cầu exhaustive; sealed hierarchy có thể đạt bằng việc bao phủ đầy đủ subtype mà không cần default.

**11. Có thể dùng `case null, default -> ...` trong Java 21 khi muốn cùng xử lý hai nhóm không?**  
Có. Đây là cú pháp hợp lệ cho nhánh chung của selector null và các giá trị khác còn lại.

**12. Nếu đổi switch cổ điển sang pattern switch mà các test đầu ra vẫn đúng, đã chắc chắn bảo toàn mọi hành vi chưa?**  
Chưa. Cần xét cả ngoại lệ, fall-through có tác dụng phụ, side effects của accessor/guard, trường hợp null, subtype và các input chưa test.

## Tham khảo

- [JEP 361 — Switch Expressions (Java 14)](https://openjdk.org/jeps/361)
- [JEP 394 — Pattern Matching for instanceof (Java 16)](https://openjdk.org/jeps/394)
- [JEP 440 — Record Patterns (Java 21)](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch (Java 21)](https://openjdk.org/jeps/441)
- [Oracle Java SE 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html)
- [JLS Java SE 21 §14.11 — The switch Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11)
- [JLS Java SE 21 §15.28 — switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28)
