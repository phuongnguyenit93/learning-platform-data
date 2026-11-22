# Lỗi compiler do `case` bị dominated trong Java

> **Module:** Java Core Pattern Matching → Dominance. Bài dựa trên **Java 21**, phiên bản đầu tiên mà pattern matching for `switch` là tính năng chính thức (JEP 441). Các đoạn đánh dấu **ERROR** được viết để compiler từ chối có chủ đích; chỉ đoạn có tên tệp và lệnh `javac` ở phần 9 là chương trình chạy độc lập.

## Mục tiêu

Bạn sẽ hiểu nguyên nhân lỗi **`this case label is dominated by a preceding case label`**, biết xác định nhánh nào che nhánh nào, sửa đúng thứ tự pattern, hằng số và `when`, đồng thời phân biệt dominance với lỗi nhãn trùng, guard sai quy tắc hay `switch` không exhaustive. Sau bài này, bạn có thể phân tích lỗi ngay từ **kiểu tĩnh và thứ tự nhãn `case`**, không phải thử các giá trị đầu vào một cách mò mẫm.

## 1. Lỗi “case bị dominated” nghĩa là gì?

Với pattern matching for `switch` trong Java 21, một giá trị selector có thể tương thích với **nhiều nhãn `case`**. Java chọn **nhãn áp dụng đầu tiên** theo thứ tự khai báo. Compiler cấm những nhãn mà nó có thể xác định rằng **mọi giá trị nhãn đó nhận được đều sẽ được một nhãn trước nhận mất**.

Đó là một nhãn **dominated** (bị bao phủ/che hoàn toàn bởi nhãn đi trước). Trình biên dịch thường báo:

~~~text
error: this case label is dominated by a preceding case label
~~~

Ví dụ **cố ý không biên dịch**:

~~~java
static String broken(Object input) {
    return switch (input) {
        case CharSequence sequence -> "a character sequence";
        case String text -> "a string"; // ERROR: dominated.
        default -> "other";
    };
}
~~~

**Vì sao?**

- Một đối tượng `String` luôn triển khai `CharSequence`.
- Nhãn `case CharSequence sequence` đứng **trước** sẽ match mọi đối tượng `String` không null.
- Vì vậy, `case String text` đặt sau sẽ không có giá trị nào để xử lý.
- Compiler phát hiện quan hệ subtype này khi biên dịch, dù bạn định chạy chương trình với `String` hay không.

**Sửa: đặt pattern cụ thể trước, pattern rộng hơn sau.**

~~~java
static String corrected(Object input) {
    return switch (input) {
        case String text -> "a string: " + text;
        case CharSequence sequence -> "a character sequence";
        default -> "other";
    };
}
~~~

Bây giờ `String` được nhận trước; `StringBuilder` và các `CharSequence` khác có thể rơi vào nhánh thứ hai.

> **Quy tắc dễ nhớ:** Nếu nhãn A có thể nhận **tất cả** giá trị nhãn B nhận, và A đứng trước B, thì B có nguy cơ bị **dominated**. Compiler áp dụng các quy tắc dominance cụ thể của JLS chứ không cố suy diễn tất cả mệnh đề logic tùy ý.

## 2. Phân biệt dominance ở compile time và chọn nhánh lúc runtime

Đừng nhầm hai khái niệm:

- **Dominance:** compiler xác định một nhãn bị nhãn trước che hoàn toàn theo quy tắc tĩnh; lỗi **compile time** và mã không chạy.
- **First applicable label:** nếu nhiều nhãn còn hợp lệ có thể xử lý cùng một giá trị, runtime chọn nhãn được áp dụng **đầu tiên**.

Ví dụ hợp lệ:

~~~java
static String kind(Object value) {
    return switch (value) {
        case String s -> "string";
        case Integer i -> "integer";
        default -> "other";
    };
}
~~~

`String` và `Integer` là hai lớp không có quan hệ subtype với nhau, nên không có nhãn nào bao phủ toàn bộ tập đối tượng nhãn kia nhận được. `default` xử lý những loại khác.

Nhưng ví dụ sau **lỗi**:

~~~java
static String brokenNumber(Object value) {
    return switch (value) {
        case Number n -> "number";
        case Integer i -> "integer"; // ERROR: Integer là Number.
        default -> "other";
    };
}
~~~

Mọi `Integer` đều là `Number`. Chỉ cần hoán đổi:

~~~java
static String fixedNumber(Object value) {
    return switch (value) {
        case Integer i -> "integer";
        case Number n -> "number";
        default -> "other";
    };
}
~~~

**Thứ tự thông thường:** `Integer` → `Number` → `Object`/`default`, hoặc `String` → `CharSequence` → `Object`/`default`.

## 3. Kiểu tĩnh của selector và quan hệ kiểu là điểm xuất phát

Trong:

~~~java
Object input = "Java";
String result = switch (input) {
    case String text -> text.toUpperCase();
    case CharSequence sequence -> "Other sequence";
    default -> "Other";
};
~~~

- `input` là **selector**, có **kiểu tĩnh `Object`**.
- Các `case` chứa **type pattern**; runtime có thể xác định `input` là `String`, `StringBuilder` hoặc một loại khác.
- Biến `text` có kiểu tĩnh `String` trong arm được chọn; `sequence` có kiểu tĩnh `CharSequence` trong arm riêng.
- Kiểm tra dominance dựa trên **quan hệ kiểu và các quy tắc nhãn** lúc biên dịch, không dựa vào việc hôm nay `input` tình cờ chứa chuỗi `"Java"`.

Nếu selector có kiểu tĩnh `Integer`, một nhãn `case String s` lại có thể bị từ chối vì **pattern không áp dụng được cho kiểu selector**, là **lỗi tương thích kiểu**, không phải dominated:

~~~java
static String invalidSelector(Integer value) {
    return switch (value) {
        case String s -> "text"; // ERROR: pattern String không tương thích.
        default -> "other";
    };
}
~~~

Một chẩn đoán biên dịch chỉ nên được gọi là dominance khi nhánh **có thể áp dụng** nhưng bị một nhánh trước bao phủ theo quy tắc JLS. Đây là khác biệt quan trọng khi tìm nguyên nhân gốc.

## 4. Case cùng kiểu: guard `when` làm thay đổi dominance thế nào?

**Guarded pattern label** có dạng:

~~~text
case Type variable when booleanCondition -> result
~~~

Pattern phải match trước, rồi điều kiện `when` mới được xét. **Guard có thể thu hẹp** tập giá trị mà nhánh thực sự nhận.

### 4.1. Nhánh không guard đứng trước: nhánh có guard bị dominated

~~~java
static String wrongGuardOrder(Object value) {
    return switch (value) {
        case String s -> "any string";
        case String s when s.isBlank() -> "blank"; // ERROR: dominated.
        default -> "other";
    };
}
~~~

Nhãn `case String s` đầu đã match **mọi chuỗi**. Nhãn sau không còn cơ hội, dù điều kiện `s.isBlank()` đúng với một số chuỗi.

**Sửa: guard đặc biệt trước, nhánh chung cùng kiểu sau.**

~~~java
static String rightGuardOrder(Object value) {
    return switch (value) {
        case String s when s.isBlank() -> "blank";
        case String s -> "nonblank";
        default -> "other";
    };
}
~~~

- Với `"  "`, guard `isBlank()` đúng → `"blank"`.
- Với `"Java"`, guard sai nhưng pattern `String` vẫn match ở nhãn kế tiếp → `"nonblank"`.
- Với `42`, pattern `String` không match; guard `String` không được đánh giá → `"other"`.

### 4.2. Guard không hằng thường **không** làm compiler suy ra dominance

~~~java
static String overlappingGuards(Object value) {
    return switch (value) {
        case String s when s.length() > 3 -> "long";
        case String s when s.startsWith("A") -> "starts A";
        case String s -> "other string";
        default -> "other";
    };
}
~~~

Đây là code **hợp lệ**. `"ABCD"` thỏa cả hai điều kiện đầu nhưng vào nhánh `"long"` vì nó được xét trước. Trình biên dịch không chứng minh tất cả quan hệ logic giữa hai biểu thức guard tùy ý.

Nói cách khác, **không bị báo dominated không có nghĩa nhánh chắc chắn được thực thi với dữ liệu nào đó**. Bạn vẫn cần xét ưu tiên nghiệp vụ và kiểm thử.

### 4.3. `when true` được coi như nhánh không guard về dominance

~~~java
static String badTrueGuard(Object value) {
    return switch (value) {
        case String s when true -> "all strings";
        case String s -> "another string"; // ERROR: dominated.
        default -> "other";
    };
}
~~~

Guard là **constant expression true**, không làm hẹp pattern. Java 21 xem nó tương đương nhãn **unguarded** khi xét dominance.

### 4.4. `when false` gây lỗi, nhưng không phải lỗi dominated

~~~java
static String badFalseGuard(Object value) {
    return switch (value) {
        case String s when false -> "never"; // ERROR: constant false guard.
        default -> "other";
    };
}
~~~

JLS cấm guard là **constant expression false**. Compiler có thể báo:

~~~text
this case label has a guard that is a constant expression with value 'false'
~~~

Đây là **lỗi tính hợp lệ của guard**, không nên gán nhãn nhầm thành dominated.

**Gợi ý sửa:** Xóa case không thể chạy, hoặc thay bằng predicate runtime thực sự có ý nghĩa nghiệp vụ. Đừng thêm `when true`/`when false` chỉ để “bật/tắt” logic.

## 5. Type pattern có thể dominate cả nhãn hằng

Dominance không chỉ xảy ra giữa hai type patterns.

### 5.1. Nhãn `case Integer i` che nhãn `case 1`

Mã sau **cố ý không biên dịch**:

~~~java
static String badConstant(Integer value) {
    return switch (value) {
        case Integer i -> "an integer";
        case 1 -> "one"; // ERROR: case 1 dominated.
    };
}
~~~

Vì selector có kiểu tham chiếu `Integer`, `case Integer i` bao phủ mọi giá trị `Integer` không null, bao gồm `1`.

**Sắp xếp đúng:**

~~~java
static String goodConstant(Integer value) {
    return switch (value) {
        case 1 -> "exactly one";
        case Integer i -> "some other integer";
    };
}
~~~

`case 1` được ưu tiên trước, sau đó mới tới pattern tổng quát. `case Integer i` cũng giúp bao phủ các giá trị `Integer` khác để switch expression exhaustive.

Lưu ý: `null` vẫn là trường hợp riêng; nếu truyền `null` và không có `case null`, pattern switch của Java 21 sẽ ném `NullPointerException`.

### 5.2. Type pattern của enum có thể che enum constant

~~~java
enum Color { RED, GREEN, BLUE }

static String badEnum(Color color) {
    return switch (color) {
        case Color c -> "some color";
        case RED -> "red"; // ERROR: RED dominated.
    };
}
~~~

`case Color c` là **type pattern**; mọi hằng `Color` không null đều match pattern này. Vì vậy, nhãn `case RED` đặt sau không thể áp dụng.

**Sửa:**

~~~java
static String goodEnum(Color color) {
    return switch (color) {
        case RED -> "red";
        case Color c -> "other color";
    };
}
~~~

Phân biệt:

- `case RED`: **enum constant label**, không tạo biến pattern.
- `case Color c`: **type pattern**, bind `c` là `Color` khi match.

### 5.3. Guarded pattern thường không dominate nhãn hằng phía sau

Đây là mã **hợp lệ** trong Java 21:

~~~java
static String legalButSurprising(Integer value) {
    return switch (value) {
        case Integer i when i > 0 -> "positive";
        case 1 -> "one";
        case Integer i -> "nonpositive";
    };
}
~~~

`legalButSurprising(1)` trả `"positive"`, không phải `"one"`, vì guard của nhánh đầu đúng. Compiler **không** dùng guard tùy ý `i > 0` để kết luận nhãn hằng `1` bị dominated.

**Lời khuyên về thứ tự:** Đặt **nhãn hằng cụ thể → guarded patterns → unguarded patterns**. Như vậy, giá trị đặc biệt `1` không bị nhánh “số dương” lấy mất lúc chạy.

~~~java
static String preferred(Integer value) {
    return switch (value) {
        case 1 -> "one";
        case Integer i when i > 0 -> "positive";
        case Integer i -> "nonpositive";
    };
}
~~~

Quy tắc này có ngoại lệ tùy yêu cầu nghiệp vụ, nhưng là mặc định dễ hiểu và ít bất ngờ.

## 6. Nhãn quá tổng quát: `Object`, `default` và `null`

### 6.1. Pattern `Object` đứng đầu làm các type patterns phía sau bị che

~~~java
static String badObject(Object value) {
    return switch (value) {
        case Object any -> "object";
        case String text -> "string"; // ERROR: dominated.
    };
}
~~~

Với selector kiểu `Object`, `case Object any` bao phủ tất cả đối tượng **không null**, kể cả `String`. Hãy đặt những type pattern cụ thể trước:

~~~java
static String goodObject(Object value) {
    return switch (value) {
        case String text -> "string";
        case Object any -> "other object";
    };
}
~~~

Đây là switch expression exhaustive cho các đối tượng không null với selector kiểu `Object`. Nhưng nó **không tự nhận `null`**; muốn xử lý `null` thay vì để switch ném `NullPointerException`, thêm `case null -> ...`.

### 6.2. `null` không phải là một đối tượng match type pattern

~~~java
static String safeObject(Object value) {
    return switch (value) {
        case null -> "missing";
        case String text -> "string";
        case Object any -> "other object";
    };
}
~~~

`case null` là **nhãn đặc biệt**, không phải một type pattern `Object`. Do đó, `case Object any` không dominate `case null`.

Đừng suy luận rằng một type pattern tổng quát sẽ xử lý được mọi giá trị bao gồm null. Theo Java 21, nếu selector là `null` và không có nhãn `case null`, switch có thể ném `NullPointerException`.

### 6.3. `default` không thay thế việc suy luận dominance

`default` dùng để xử lý các giá trị không khớp nhãn khác theo quy tắc switch. Với mã:

~~~java
static String categorize(Object value) {
    return switch (value) {
        case String text -> "text";
        case Number number -> "number";
        default -> "other";
    };
}
~~~

Đặt `String` và `Number` trước `default` là cách trình bày dễ đọc. `default` không có pattern variable và không xác nhận kiểu cụ thể; nó chỉ cung cấp một nhánh dự phòng.

Tuy nhiên, không thể dùng `default` để “cứu” một nhãn bị dominated trước đó: nếu có `case CharSequence` đứng trước `case String`, dù thêm `default` vào cuối thì lỗi vẫn tồn tại.

**Đừng nhập nhằng:** Dominance, type coverage/exhaustiveness, `default` và xử lý null là các kiểm tra liên quan nhưng **khác nhau**.

## 7. Các lỗi trông giống dominance nhưng bản chất khác

| Lỗi | Ví dụ | Bản chất | Hướng xử lý |
| --- | --- | --- | --- |
| **Dominated case** | `case CharSequence c` trước `case String s` | Mọi chuỗi đã bị nhánh trước lấy | Đưa `String` lên trước |
| **Dominated constant** | `case Integer i` trước `case 1` | Pattern nhận cả giá trị hằng | Đưa hằng cụ thể lên trước |
| **Duplicate constant** | Hai nhãn `case 1` | Hai hằng cùng giá trị | Gộp/xóa một nhãn |
| **Guard constant false** | `case String s when false` | Guard sai ngay tại compile time | Xóa nhánh chết |
| **Pattern không tương thích** | Selector `Integer`, `case String s` | Kiểu không áp dụng cho selector | Sửa kiểu selector/pattern |
| **Non-exhaustive switch** | Selector `Object`, chỉ có `case String s` | Thiếu xử lý các giá trị khác | Bổ sung `default`/pattern tổng quát |
| **Trùng tên biến cục bộ** | `String s` ngoài scope, `case String s` trong phạm vi trùng | Quy tắc khai báo tên | Đổi tên binding |
| **Fall-through không an toàn** | Switch dạng `:` rơi vào nhánh có binding pattern chưa khởi tạo | Quy tắc luồng điều khiển | Dùng `->` hoặc kết thúc nhánh đúng |

**Ví dụ duplicate constant (cố ý không biên dịch):**

~~~java
static String duplicate(Integer n) {
    return switch (n) {
        case 1 -> "first";
        case 1 -> "second"; // ERROR: duplicate case label.
        default -> "other";
    };
}
~~~

Lỗi này khác dominated pattern: bạn đã khai báo **cùng một giá trị hằng hai lần**.

**Ví dụ non-exhaustive (cố ý không biên dịch):**

~~~java
static String missing(Object input) {
    return switch (input) {
        case String text -> text;
        // ERROR: Object còn nhiều kiểu khác ngoài String.
    };
}
~~~

Đây không phải dominated vì chỉ có một nhãn. Compiler yêu cầu switch expression bao phủ kiểu selector. Thêm `default` hoặc một pattern tổng quát phù hợp.

## 8. Cách xử lý khi compiler báo dominated case

Một quy trình ngắn mà đáng tin:

1. **Đọc nhãn bị gạch lỗi.** Ví dụ `case String text` hoặc `case 1`.
2. **Nhìn lên những nhãn đứng trước.** Tìm kiểu cha/interface (`Object`, `CharSequence`, `Number`), pattern cùng kiểu không guard, hoặc một pattern nhận cả nhãn hằng đang bị lỗi.
3. **Kiểm tra quan hệ tập giá trị.** Mọi `String` có phải `CharSequence`? Mọi số `1` đóng hộp có phải `Integer`? Nếu có, nhãn trước có thể che toàn bộ nhãn sau.
4. **Xét `when`.** Nếu nhãn trước không guard hoặc `when true`, nó không lọc giá trị theo guard. Nếu có guard phụ thuộc runtime, compiler thường không dùng nó để kết luận dominance; vẫn phải xem thứ tự để tránh logic bất ngờ.
5. **Sắp xếp lại theo mức độ đặc thù.** Ưu tiên nhãn hằng, rồi pattern cụ thể/guard đặc biệt, cuối cùng là pattern rộng hơn, unguarded pattern hoặc `default`.
6. **Không sửa bằng cast hoặc đổi tên pattern variable một cách máy móc.** Cast không làm biến mất quan hệ subtype khiến nhãn sau không thể áp dụng.
7. **Kiểm tra exhaustiveness sau khi sửa.** Đổi thứ tự có thể hợp lệ nhưng xóa nhánh rộng/`default` có thể khiến switch không bao phủ hết tập selector.
8. **Biên dịch lại ở đúng phiên bản Java.** Các ví dụ `case T x when ...` dùng Java 21. Với bản Java 17, pattern switch chưa phải tính năng chính thức; không quy mọi lỗi preview/version thành dominance.
9. **Chạy thử nhiều trường hợp runtime.** Kiểm tra giá trị khớp nhánh cụ thể, kiểu con khác, giá trị làm guard đúng/sai, `null` và fallback.

### Chẩn đoán nhanh bằng checklist

| Câu hỏi | Nếu trả lời “có” |
| --- | --- |
| Có `case Object any` phía trước? | Các type patterns phía sau nhận object không null rất dễ bị che |
| Có `case CharSequence` trước `case String`? | `String` bị dominated |
| Có `case Number` trước `case Integer`? | `Integer` bị dominated |
| Có unguarded `case String` trước guarded `case String when ...`? | Guarded case bị dominated |
| Có `when true` ở nhánh cùng kiểu trước? | Nhãn sau có thể bị dominated |
| Có unguarded `case Integer` trước hằng `case 1`? | Nhãn hằng `1` bị dominated |
| Có hai nhãn `case 1`? | Đó là duplicate constant, không phải loại lỗi trên |
| Có `when false`? | Guard constant false không hợp lệ, là lỗi riêng |

## 9. Chương trình Java 21 hoàn chỉnh, chạy được

Lưu tệp **`DominanceLessonDemo.java`**:

~~~java
public class DominanceLessonDemo {

    enum Color {
        RED, GREEN, BLUE
    }

    // Các nhãn đặt từ trường hợp cụ thể đến rộng hơn.
    static String classify(Object value) {
        return switch (value) {
            case null -> "null";
            case String s when s.isBlank() -> "blank";
            case String s -> "text=" + s.trim();
            case Integer n when n == 0 -> "zero";
            case Integer n -> "integer=" + n;
            case Number n -> "number=" + n;
            case CharSequence cs -> "chars=" + cs.length();
            default -> "other";
        };
    }

    // Đặt hằng cụ thể trước pattern tổng quát.
    static String rank(Integer n) {
        return switch (n) {
            case null -> "no number";
            case 1 -> "one";
            case Integer value when value > 0 -> "positive";
            case Integer value -> "nonpositive";
        };
    }

    // Đặt hằng enum trước type pattern nhận tất cả Color.
    static String color(Color c) {
        return switch (c) {
            case RED -> "red";
            case Color any -> "other color";
        };
    }

    public static void main(String[] args) {
        Object[] values = {
                "  ",
                " Java ",
                0,
                7,
                2.5,
                new StringBuilder("ok"),
                new Object(),
                null
        };

        for (Object value : values) {
            System.out.println(classify(value));
        }

        System.out.println(
                "rank=" + rank(1) + "," + rank(3) + "," + rank(-1)
        );
        System.out.println("color=" + color(Color.BLUE));
    }
}
~~~

**Biên dịch và chạy** bằng JDK 21 trở lên:

~~~bash
javac --release 21 DominanceLessonDemo.java
java DominanceLessonDemo
~~~

**Stdout chính xác:**

~~~text
blank
text=Java
zero
integer=7
number=2.5
chars=2
other
null
rank=one,positive,nonpositive
color=other color
~~~

**Diễn giải từng nhánh:**

1. `"  "` match `String` và `isBlank()` đúng → `blank`.
2. `" Java "` match `String` nhưng guard sai → `text=Java` sau `trim()`.
3. `0` được autobox thành `Integer` khi nằm trong mảng `Object[]`. Guard `n == 0` đúng → `zero`.
4. `7` match `Integer` nhưng guard bằng 0 sai → `integer=7`; không bị `Number` phía sau lấy mất.
5. `2.5` là `Double`, cũng là `Number` → `number=2.5`.
6. `StringBuilder("ok")` không phải `String`, nhưng là `CharSequence` → `chars=2`.
7. `new Object()` chỉ match `default` → `other`.
8. `null` match nhãn riêng `case null` → `null`.
9. `rank(1)` vào nhãn hằng `case 1`, `rank(3)` qua guard `value > 0`, còn `rank(-1)` vào nhánh `Integer` không guard.
10. `Color.BLUE` không phải `RED`, nên vào type pattern `case Color any` → `other color`.

**Điểm kiểm chứng:** Nếu hoán đổi `case CharSequence cs` lên trước `case String s`, hoặc `case Integer n` lên trước hằng `case 1`, Java 21 không còn biên dịch được — đây chính là lỗi dominance mà bài học phân tích.

## 10. Bài tập tự kiểm tra

**Câu 1.** Đoạn sau có biên dịch không? Nếu không, nhãn nào bị dominated?

~~~java
return switch (value) {
    case Number n -> "number";
    case Double d -> "double";
    default -> "other";
};
~~~

**Câu 2.** Vì sao `case String s` đặt sau `case CharSequence cs` bị lỗi? Thay đổi ít nhất để sửa.

**Câu 3.** Đoạn này hợp lệ không? Với `value == "ABCD"`, nhánh nào được chọn?

~~~java
return switch (value) {
    case String s when s.length() > 3 -> "long";
    case String s when s.startsWith("A") -> "starts A";
    case String s -> "string";
    default -> "other";
};
~~~

**Câu 4.** `case String s when true` đứng trước `case String t` có gây lỗi dominance ở Java 21 không? Giải thích.

**Câu 5.** Vì sao `case String s when false` có lỗi biên dịch, nhưng không phải thông báo “dominated” điển hình?

**Câu 6.** Với selector kiểu `Integer`, tại sao `case Integer i` đặt trước `case 1` bị lỗi? Sửa lại theo thứ tự phù hợp.

**Câu 7.** Có mã:

~~~java
return switch (n) {
    case Integer i when i > 0 -> "positive";
    case 1 -> "one";
    case Integer i -> "other";
};
~~~

Nó có biên dịch không? Với `n == 1` trả gì? Muốn ưu tiên kết quả `"one"` thì làm sao?

**Câu 8.** Một enum `Color { RED, GREEN, BLUE }`. Vì sao `case Color c` có thể dominate `case RED` khi nó đứng trước?

**Câu 9.** `case Object o` có xử lý selector `null` không? Nếu muốn in `"missing"` cho null, thêm nhãn nào?

**Câu 10.** Hai nhãn `case 1` giống nhau bị lỗi gì? Nó có phải lỗi “pattern bị dominated” theo nghĩa thông thường không?

**Câu 11.** Một switch expression trên `Object` chỉ có `case String s -> ...`. Compiler từ chối vì dominated hay non-exhaustive?

**Câu 12.** Phân biệt việc compiler từ chối `case String s` vì selector là `Integer` với việc từ chối `case String s` vì trước nó có `case CharSequence cs`.

### Đáp án gợi ý

1. **Không.** `case Double d` bị dominated vì mọi `Double` đều là `Number`. Đặt `Double` trước `Number`.
2. `String implements CharSequence`, nên nhánh tổng quát bắt hết chuỗi. Đặt `String` trước.
3. **Hợp lệ.** `"ABCD"` trả `"long"` vì guard nhánh đầu đúng và nó đứng trước guard `startsWith("A")`.
4. **Có.** Guard hằng `true` được xem là unguarded; nó đã nhận mọi `String` trước nhánh sau.
5. JLS cấm constant guard `false`, lỗi là guard không hợp lệ; không cần có nhãn trước nào để phát sinh lỗi.
6. `case Integer i` match mọi `Integer` không null, bao gồm `1`. Đặt `case 1` trước rồi mới `case Integer i`.
7. **Hợp lệ.** Trả `"positive"` khi `n == 1` vì guard nhánh đầu đúng. Muốn `"one"` thì đặt `case 1` trước guarded pattern.
8. `case Color c` match mọi hằng `Color` không null, trong đó có `RED`. Đặt `case RED` trước.
9. **Không.** Type pattern không match null. Thêm `case null -> "missing"` nếu muốn xử lý riêng.
10. **Duplicate case label**, vì cùng giá trị hằng xuất hiện hai lần; không gọi nhầm thành lỗi subtype dominance.
11. **Non-exhaustive** vì `Object` có nhiều kiểu ngoài `String`. Thêm `default` hoặc pattern bao phủ phần còn lại.
12. Trường hợp selector `Integer` là **pattern không tương thích với kiểu selector**; trường hợp `CharSequence` trước `String` là **dominated case** do thứ tự nhãn.

## Tài liệu tham khảo chính thức

- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): phần *Pattern Label Dominance*, *When Clauses*, *Null case Labels* và phạm vi pattern variable.
- [Java Language Specification 21 — `14.11.1 The switch Block](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1): quy tắc switch compatibility, guard, dominance và các nhãn trùng.
- [Java Language Specification 21 — `14.11.1.2 Determining which Switch Label Applies at Run Time](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1.2): quy tắc chọn nhãn runtime.
- [Java Language Specification 21 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28): switch expression và yêu cầu bao phủ.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): thiết kế Java 21, thứ tự case, guarded patterns và null.
