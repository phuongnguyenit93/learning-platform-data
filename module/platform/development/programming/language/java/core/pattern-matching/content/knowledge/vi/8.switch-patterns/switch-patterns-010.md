# Giá trị trả về từ từng nhánh pattern trong switch (Java 21)

## 1. Mục tiêu: phân loại một giá trị và tạo ra kết quả

Trong Java, pattern matching cho `switch` cho phép nhận diện kiểu hoặc cấu trúc của một giá trị rồi dùng **pattern variable** ngay trong nhánh được chọn. Khi muốn **lấy một kết quả chung từ các nhánh**, cú pháp thích hợp thường là **switch expression**: toàn bộ biểu thức `switch (...) { ... }` được đánh giá thành **một giá trị**.

Ví dụ:

~~~java
String label = switch (value) {
    case String text -> "TEXT:" + text.toUpperCase();
    case Number number -> "NUMBER:" + number.intValue();
    case null -> "NULL";
    default -> "OTHER";
};
~~~

Đây là đoạn mã minh họa trong một phương thức có biến `Object value`. Biến `label` được gán **giá trị của nhánh duy nhất được chọn**, chẳng hạn `"TEXT:JAVA"` với `value = "java"`. Pattern `String text` quyết định nhánh; biểu thức sau `->` quyết định **giá trị kết quả**.

Sau bài này, bạn có thể:

- Phân biệt **switch statement** (thực thi câu lệnh) với **switch expression** (sinh ra một giá trị).
- Giải thích mỗi nhánh pattern dạng `case Pattern -> expression` tạo ra kết quả ra sao.
- Dùng `yield` để trả giá trị từ nhánh dạng khối `{ ... }` hoặc statement group dạng dấu hai chấm `case ...:`.
- Hiểu các nhánh `throw`, xử lý `null`, thứ tự nhãn và điều kiện `when`.
- Xác định kiểu kết quả chung của switch expression và ảnh hưởng của ngữ cảnh kiểu đích.
- Kiểm tra tính *exhaustive* (bao phủ toàn bộ trường hợp), kể cả trường hợp dùng sealed types.
- Nhận diện các lỗi biên dịch khi thiếu giá trị, dùng `return`/`break` thay `yield`, thiếu nhánh bao phủ hoặc dùng kiểu trả về không tương thích.

**Phiên bản:** pattern matching for `switch` và record pattern là các tính năng ổn định từ **Java 21**. Các chương trình có `case String s -> ...` ở bài này sử dụng `javac --release 21` và không cần `--enable-preview`. Trong Java 17, switch expression cơ bản đã ổn định nhưng pattern matching for switch còn là preview.

## 2. Phân biệt ba khái niệm: pattern, nhánh và giá trị

Một nhánh switch expression có thể viết:

~~~java
case String s -> "length=" + s.length();
~~~

Đọc theo thứ tự:

1. **Selector expression**: giá trị nằm trong `switch (value)`; nó được đánh giá một lần để chọn nhánh phù hợp.
2. **Case pattern**: `String s`. Nhãn khớp nếu selector là một đối tượng `String` thích hợp; khi đó `s` được gắn với đối tượng và có kiểu tĩnh `String`.
3. **Rule expression**: `"length=" + s.length()`. Khi nhánh đó được chọn, Java tính biểu thức này và dùng kết quả làm **giá trị của toàn switch expression**.

Một switch expression dùng cú pháp mũi tên có ba dạng rule body quan trọng:

| Rule body | Tác dụng | Ví dụ |
| --- | --- | --- |
| Một expression | Giá trị expression trở thành kết quả nhánh | `case String s -> s.length();` |
| Một block `{ ... }` | Có thể xử lý nhiều câu lệnh; cần `yield giáTrị;` trên đường hoàn tất bình thường | `case String s -> { int n = s.length(); yield n; }` |
| Một `throw` statement | Ném ngoại lệ; nhánh không sinh ra kết quả bình thường | `case null -> throw new IllegalArgumentException("null");` |

**Không được nhầm** dấu chấm phẩy sau rule `->` với dấu `return`. Phần `s.length()` là biểu thức sản sinh giá trị; switch expression có thể đặt ở bên phải phép gán, trong `return` của phương thức, hoặc làm đối số hàm.

## 3. Ví dụ hoàn chỉnh: mỗi pattern trả về một String khác nhau

Lưu tệp `SwitchBranchValueDemo.java`:

~~~java
public class SwitchBranchValueDemo {
    static String describe(Object value) {
        return switch (value) {
            case null -> "NULL";
            case String s when s.isBlank() -> "BLANK";
            case String s -> "TEXT:" + s.toUpperCase();
            case Integer n -> "INTEGER:" + n;
            case Number n -> "NUMBER:" + n.doubleValue();
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("   "));
        System.out.println(describe("java"));
        System.out.println(describe(7));
        System.out.println(describe(2.5));
        System.out.println(describe(new Object()));
    }
}
~~~

Biên dịch/chạy bằng JDK 21+:

~~~bash
javac --release 21 SwitchBranchValueDemo.java
java SwitchBranchValueDemo
~~~

Kết quả chính xác:

~~~text
NULL
BLANK
TEXT:JAVA
INTEGER:7
NUMBER:2.5
OTHER
~~~

Phân tích giá trị từ từng nhánh:

| Đầu vào | Nhánh được chọn | Giá trị trả về |
| --- | --- | --- |
| `null` | `case null` | `"NULL"` |
| `"   "` | `case String s when s.isBlank()` | `"BLANK"` |
| `"java"` | `case String s` | `"TEXT:JAVA"` |
| `7` | `case Integer n` | `"INTEGER:7"` |
| `2.5` | `case Number n` | `"NUMBER:2.5"` |
| `new Object()` | `default` | `"OTHER"` |

Ở đây kiểu tham số của `describe` là `Object`. Runtime chọn đúng một nhánh. Trong nhánh `String s`, compiler biết `s` là `String`; trong nhánh `Number n`, compiler biết `n` là `Number`. Mỗi rule tính ra một `String` nên có thể trả kết quả từ phương thức `describe` có kiểu trả về `String`.

**Chú ý thứ tự:** `case Integer n` phải xuất hiện trước `case Number n` nếu muốn phân biệt `Integer`, vì `Integer` là subtype của `Number`. Nếu đặt `Number n` trước, case `Integer n` ở phía sau bị *dominated* (không thể được chọn) và bị compiler từ chối.

## 4. Guard when ảnh hưởng nhánh được chọn, không tự tạo giá trị

Trong ví dụ trên, `case String s when s.isBlank()` phân loại thêm các chuỗi rỗng hoặc chỉ chứa khoảng trắng:

~~~java
case String s when s.isBlank() -> "BLANK";
case String s -> "TEXT:" + s.toUpperCase();
~~~

Quá trình:

1. Java thử khớp `String s`. Nếu không phải `String`, guard `when` không được đánh giá.
2. Nếu khớp, `s` có kiểu `String` và được dùng trong `s.isBlank()`.
3. Nếu guard đúng, Java chọn rule trả `"BLANK"`.
4. Nếu guard sai, Java xét nhãn tiếp theo và có thể chọn rule `case String s` trả `"TEXT:..."`.

Guard `when` là **điều kiện để chọn nhánh**, không phải giá trị của switch expression. Giá trị kết quả vẫn được xác định bởi expression hoặc `yield` trong rule body.

Một nhánh bao quát đặt trước nhánh cụ thể có thể gây lỗi dominance. Hãy đặt các trường hợp đặc biệt (ví dụ chuỗi blank) trước trường hợp chung (mọi chuỗi), và các subtype (ví dụ `Integer`) trước supertype (ví dụ `Number`) khi chúng cùng cần xử lý.

## 5. Khi cần nhiều câu lệnh: block và yield

Một rule có thể cần tính trung gian, ghi log hoặc áp dụng nhiều bước. Khi đó viết block:

~~~java
case String s -> {
    int normalizedLength = s.strip().length();
    yield normalizedLength * 10;
}
~~~

Trong **switch expression**, `yield` là câu lệnh trả một giá trị **cho chính switch expression gần nhất chứa nó**. Nó khác với `return`, vốn trả khỏi phương thức (và bị cấm trong block của switch expression theo ngữ cảnh này), và khác `break`, vốn dùng để điều khiển switch statement truyền thống.

Ví dụ hoàn chỉnh dùng cả type pattern và record pattern (Java 21). Lưu `SwitchYieldValueDemo.java`:

~~~java
record Point(int x, int y) {}

public class SwitchYieldValueDemo {
    static int score(Object value) {
        return switch (value) {
            case null -> 0;
            case String s -> {
                int normalizedLength = s.strip().length();
                yield normalizedLength * 10;
            }
            case Point(int x, int y) -> {
                int squaredDistance = x * x + y * y;
                yield squaredDistance;
            }
            case Number n -> n.intValue();
            default -> -1;
        };
    }

    public static void main(String[] args) {
        System.out.println(score(" java "));
        System.out.println(score(new Point(3, 4)));
        System.out.println(score(7));
        System.out.println(score(null));
        System.out.println(score(new Object()));
    }
}
~~~

~~~bash
javac --release 21 SwitchYieldValueDemo.java
java SwitchYieldValueDemo
~~~

Kết quả:

~~~text
40
25
7
0
-1
~~~

Giải thích:

- `" java "` khớp `String s`; sau `strip()` còn 4 ký tự, `yield 4 * 10` đưa giá trị `40` ra khỏi switch expression.
- `new Point(3, 4)` khớp record pattern `Point(int x, int y)`; hai biến thành phần `x`, `y` dùng được trong block; `yield 3*3 + 4*4` là `25`.
- `7` khớp `Number n` và rule một expression `n.intValue()` trả ngay `7`, không cần `yield`.
- `null` có rule riêng tạo `0`.
- Giá trị khác các mẫu đi tới `default` và cho `-1`.

Tất cả các nhánh hoàn thành bình thường đều tạo ra `int`. Một nhánh block trong switch expression **không được kết thúc bình thường mà thiếu `yield`**. Nếu block không tạo giá trị mà cũng không ném ngoại lệ hoặc chấm dứt luồng hợp lệ, compiler sẽ báo lỗi.

### Yield không làm thoát phương thức

Xét:

~~~java
int result = switch (value) {
    case String s -> {
        yield s.length();
    }
    default -> 0;
};
System.out.println(result);
~~~

Đây là đoạn minh họa nằm trong phương thức có `Object value`. Lệnh `yield s.length();` làm switch expression hoàn tất với giá trị tương ứng; sau đó chương trình tiếp tục tới `System.out.println(result)`. Nếu thay `yield` bằng `return`, ngữ nghĩa khác và Java không cho phép `return` thoát khỏi switch expression.

## 6. Switch expression vẫn dùng được cú pháp dấu hai chấm và yield

Dạng mũi tên dễ đọc, nhưng Java cũng cho viết **switch expression** với các *switch-labeled statement groups* dạng dấu hai chấm. Để mỗi đường đi tạo giá trị, sử dụng `yield` trong các group đó.

Lưu `SwitchColonValueDemo.java`:

~~~java
public class SwitchColonValueDemo {
    static String describe(Object value) {
        String result = switch (value) {
            case null:
                yield "NULL";
            case String s:
                if (s.isBlank()) {
                    yield "EMPTY";
                }
                yield s.toUpperCase();
            case Number n:
                yield "N:" + n.intValue();
            default:
                yield "OTHER";
        };
        return result;
    }

    public static void main(String[] args) {
        System.out.println(describe(null));
        System.out.println(describe("  "));
        System.out.println(describe("java"));
        System.out.println(describe(12));
        System.out.println(describe(new Object()));
    }
}
~~~

~~~bash
javac --release 21 SwitchColonValueDemo.java
java SwitchColonValueDemo
~~~

Kết quả:

~~~text
NULL
EMPTY
JAVA
N:12
OTHER
~~~

Phân tích:

- `case String s:` có hai đường đi: nếu `s.isBlank()`, `yield "EMPTY";`; nếu không, `yield s.toUpperCase();`. Cả hai đều đưa giá trị cho **toàn switch expression**.
- `case Number n:` dùng pattern variable `n` để tạo chuỗi `"N:..."`.
- Mỗi group kết thúc bằng `yield` trên các đường đi tương ứng nên không rơi xuống group kế tiếp.
- Dạng dấu hai chấm khác `switch statement` truyền thống: trong một **switch expression**, `yield` trả giá trị; `break` không cung cấp giá trị cho biểu thức.

**Lời khuyên:** ưu tiên `->` khi có thể. Dùng `case ...:` với `yield` khi có lý do rõ ràng về cấu trúc nhiều câu lệnh; tránh vô tình áp dụng tư duy `break`/fall-through của switch statement vào switch expression.

## 7. Kiểu kết quả của toàn switch expression được quyết định như thế nào?

Dù các nhánh có pattern khác nhau, **switch expression vẫn có một kiểu** tại vị trí sử dụng. Kiểu này chịu quy tắc kiểu của Java và có thể phụ thuộc **target type** (ngữ cảnh phép gán, `return`, lời gọi hàm) hoặc được suy luận từ các expression của từng nhánh.

Trong ví dụ `SwitchBranchValueDemo`, mọi nhánh sinh ra `String` nên đơn giản. Với một phương thức trả `int` như `score`, các nhánh sinh `int`.

Một trường hợp đáng chú ý là mỗi nhánh sinh một loại số khác nhau. Lưu `SwitchPolymorphicValueDemo.java`:

~~~java
public class SwitchPolymorphicValueDemo {
    static Number number(String tag) {
        return switch (tag) {
            case "integer" -> 1;
            case "decimal" -> 2.5;
            default -> 3L;
        };
    }

    static String format(Object value) {
        return switch (value) {
            case String s -> "S:" + s;
            case Number n -> "N:" + n;
            case null -> "NULL";
            default -> "OTHER";
        };
    }

    public static void main(String[] args) {
        Number a = number("integer");
        Number b = number("decimal");
        Number c = number("other");
        System.out.println(a.getClass().getSimpleName() + ":" + a);
        System.out.println(b.getClass().getSimpleName() + ":" + b);
        System.out.println(c.getClass().getSimpleName() + ":" + c);
        System.out.println(format(3));
    }
}
~~~

~~~bash
javac --release 21 SwitchPolymorphicValueDemo.java
java SwitchPolymorphicValueDemo
~~~

Kết quả:

~~~text
Integer:1
Double:2.5
Long:3
N:3
~~~

Ở đây `return switch (tag)` là một switch expression trong **ngữ cảnh kiểu đích `Number`**. Các expression `1`, `2.5` và `3L` lần lượt được boxing thành `Integer`, `Double`, `Long`; cả ba đều phù hợp với kiểu trả về `Number`. Giá trị thực tế giữ loại wrapper tương ứng như output.

Điều này **không đồng nghĩa** mọi switch expression trộn `int`/`double`/`long` sẽ luôn tạo `Number`: nếu không có target type và expression được xét theo quy tắc *standalone*, Java có thể áp dụng numeric promotion và tạo một kiểu kết quả khác. Không đoán kiểu chỉ bằng cách nhìn nhánh đầu tiên.

### Các nhánh phải tương thích với kiểu đích

Đây là đoạn **cố ý không biên dịch**:

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> "text"; // String không chuyển được thành int
        default -> 1;
    };
}
~~~

Compiler báo kiểu kết quả `String` của nhánh đầu không phù hợp với `int`. Mọi nhánh tạo giá trị bình thường cần là expression tương thích theo quy tắc kiểu tại vị trí sử dụng; một nhánh `throw` không cần sinh giá trị.

## 8. Một nhánh có thể ném ngoại lệ thay vì sinh giá trị

Một switch expression có thể dùng rule body `throw` để biểu thị đầu vào không hợp lệ. Nếu nhánh đó được chọn, đánh giá switch **kết thúc bất thường** bằng ngoại lệ và không có giá trị kết quả bình thường.

Lưu `SwitchThrowDemo.java`:

~~~java
public class SwitchThrowDemo {
    static int lengthOfString(Object value) {
        return switch (value) {
            case String s -> s.length();
            case null -> throw new IllegalArgumentException("null value");
            default -> throw new IllegalArgumentException("not string");
        };
    }

    public static void main(String[] args) {
        System.out.println(lengthOfString("Java"));
        try {
            lengthOfString(42);
        } catch (IllegalArgumentException error) {
            System.out.println("ERROR:" + error.getMessage());
        }
        try {
            lengthOfString(null);
        } catch (IllegalArgumentException error) {
            System.out.println("ERROR:" + error.getMessage());
        }
    }
}
~~~

~~~bash
javac --release 21 SwitchThrowDemo.java
java SwitchThrowDemo
~~~

Kết quả:

~~~text
4
ERROR:not string
ERROR:null value
~~~

`case String s` trả `int` từ `s.length()`; hai nhánh còn lại ném ngoại lệ. Phương thức `lengthOfString` chỉ trả về `int` khi đầu vào hợp lệ. Không cần đặt một giá trị giả như `-1` cho trường hợp lỗi nếu hợp đồng API yêu cầu ném ngoại lệ.

Trong một block có nhiều câu lệnh, cũng có thể `throw` một ngoại lệ trên đường lỗi và `yield` trên đường thành công; tất cả các đường đi được phép phải tuân thủ quy tắc của switch expression.

## 9. Exhaustiveness: không thể thiếu đường tạo kết quả

Một switch expression phải **exhaustive**: compiler phải xác định mọi giá trị selector thuộc miền áp dụng đều có một nhánh phù hợp. Không có nhánh xử lý thì biểu thức không thể bảo đảm sẽ có giá trị.

Với selector kiểu `Object` có vô số lớp runtime khác nhau, thường cần `default`:

~~~java
String label = switch (value) {
    case String s -> "S:" + s;
    case Integer n -> "I:" + n;
    default -> "OTHER";
};
~~~

Đây là đoạn minh họa trong phương thức có `Object value`. Nếu bỏ `default` trong trường hợp này, compiler báo switch expression không bao phủ mọi giá trị có thể có.

Ví dụ **cố ý không biên dịch**:

~~~java
static String invalid(Object value) {
    return switch (value) {
        case String s -> "S:" + s;
        case Integer i -> "I:" + i;
    };
}
~~~

Thông báo tiêu biểu của `javac --release 21`:

~~~text
error: the switch expression does not cover all possible input values
~~~

### Khi nào có thể không cần default?

Nếu selector có kiểu **sealed interface/class** và các case pattern bao phủ toàn bộ các subtype được phép, compiler có thể chứng minh tính exhaustive mà không cần `default`.

Lưu `SwitchSealedExhaustiveDemo.java`:

~~~java
sealed interface Outcome permits Success, Failure {}
record Success(int count) implements Outcome {}
record Failure(String reason) implements Outcome {}

public class SwitchSealedExhaustiveDemo {
    static String describe(Outcome outcome) {
        return switch (outcome) {
            case Success(var count) -> "OK:" + count;
            case Failure(var reason) -> "FAIL:" + reason;
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new Success(2)));
        System.out.println(describe(new Failure("invalid")));
    }
}
~~~

~~~bash
javac --release 21 SwitchSealedExhaustiveDemo.java
java SwitchSealedExhaustiveDemo
~~~

Kết quả:

~~~text
OK:2
FAIL:invalid
~~~

Chỉ có hai implementation được phép của `Outcome` và mỗi loại được bao phủ bằng một record pattern. Vì vậy compiler chấp nhận switch expression không có `default`. **Điều này không có nghĩa nó tự xử lý `null`:** nếu gọi `describe(null)` mà không có `case null`, switch ném `NullPointerException`.

Nếu hệ thống thay đổi thứ bậc subtype hoặc trạng thái của sealed hierarchy, cần kiểm tra lại bao phủ và biên dịch các switch liên quan.

## 10. Null: default không thay thế case null trong pattern switch

Với selector kiểu tham chiếu:

~~~java
return switch (value) {
    case null -> "NULL";
    case String s -> "STRING";
    default -> "OTHER";
};
~~~

Java 21 cho phép xử lý `null` riêng bằng `case null`. Nếu không có nhãn phù hợp cho `null`, switch trên `null` thường ném `NullPointerException`, **kể cả khi có `default`**.

Phân biệt:

- `case String s` không khớp `null`, nên không thể gắn `s`.
- `case null` khớp giá trị `null` và có thể trả giá trị rõ ràng như `"NULL"`.
- `default` là nhánh dự phòng cho các giá trị khác không khớp những case trước; không mặc nhiên thay thế `case null`.
- Nếu muốn xem `null` là lỗi, chọn `case null -> throw new IllegalArgumentException("null value");` như ví dụ `SwitchThrowDemo`.

Tùy nghiệp vụ, có thể chọn trả giá trị mặc định, ném ngoại lệ hoặc xử lý `null` trước switch. Quan trọng là hành vi đó phải được thiết kế rõ.

## 11. Switch statement không sinh giá trị như switch expression

Cả hai đều có thể dùng pattern matching với Java 21, nhưng mục đích khác nhau.

**Switch statement:** chạy các câu lệnh, có thể ghi log/cập nhật trạng thái/gọi hàm; cú pháp `switch (...) { ... }` ở đây là **statement**, không phải expression được gán vào biến.

~~~java
switch (value) {
    case String s -> System.out.println("Text:" + s);
    case Number n -> System.out.println("Number:" + n);
    case null -> System.out.println("Null");
    default -> System.out.println("Other");
}
~~~

**Switch expression:** tính một giá trị, rồi caller quyết định dùng giá trị đó ra sao:

~~~java
String message = switch (value) {
    case String s -> "Text:" + s;
    case Number n -> "Number:" + n;
    case null -> "Null";
    default -> "Other";
};
System.out.println(message);
~~~

Hai đoạn trên là **trích đoạn Java trong một phương thức có `Object value`**, không phải chương trình độc lập. Với switch expression, mỗi nhánh cung cấp đúng một kết quả bình thường hoặc ném ngoại lệ; với switch statement, các rule thực hiện câu lệnh và không có một giá trị chung để gán.

**Không phải cứ có `case ... ->` là switch expression.** Dấu `->` dùng được cho cả switch statement và switch expression. Hãy xem switch đang được dùng ở **vị trí một expression** như vế phải của `=`, trong `return`, hoặc trong lời gọi phương thức hay đang đứng độc lập như một statement.

## 12. Các lỗi biên dịch về giá trị của nhánh

Đây là những tình huống điển hình đã được kiểm tra bằng `javac --release 21`. Các đoạn dưới là **ví dụ cố ý sai**, không dùng như mã chạy.

### 12.1. Block hoàn thành mà không yield

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> {
            int result = s.length();
            // Thiếu yield result;
        }
        default -> 0;
    };
}
~~~

Compiler báo:

~~~text
error: switch rule completes without providing a value
~~~

Cách sửa: thêm `yield result;` sau dòng gán. **Tính ra một biến trong block chưa phải trả giá trị từ block.**

### 12.2. Dùng return thay yield

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> { return s.length(); } // COMPILE ERROR
        default -> 0;
    };
}
~~~

Compiler báo:

~~~text
error: attempt to return out of a switch expression
~~~

Cách sửa trong block: `yield s.length();`. `return` ngoài switch expression ở đầu phương thức là hợp lệ, như các chương trình hoàn chỉnh ở trên: `return switch (value) { ... };`.

### 12.3. Dùng break thay yield

~~~java
static int invalid(Object value) {
    return switch (value) {
        case String s -> { break; } // COMPILE ERROR
        default -> 0;
    };
}
~~~

Compiler báo:

~~~text
error: attempt to break out of a switch expression
~~~

Trong switch statement dạng dấu hai chấm, `break` dùng để thoát switch. Trong switch expression, `break` không tạo ra giá trị cần thiết; dùng `yield` ở nhánh block hoặc expression trực tiếp ở rule.

### 12.4. Thiếu nhánh bao phủ

Với `switch (Object value)`, chỉ có `case String s` và `case Integer i` sẽ bỏ sót nhiều kiểu. Compiler báo switch expression không cover tất cả các giá trị đầu vào. Thêm `default` hoặc thiết kế một mô hình kiểu có thể chứng minh đầy đủ như sealed hierarchy.

### 12.5. Giá trị nhánh không tương thích kiểu trả về

Nếu phương thức trả `int` nhưng `case String s -> "text";`, compiler từ chối `String` không chuyển thành `int`. Hãy đưa các nhánh về kết quả theo cùng một hợp đồng kiểu như `String`, `int` hoặc interface/kiểu cha phù hợp.

### 12.6. Đặt nhánh bao quát trước nhánh riêng

~~~java
return switch (value) {
    case Number n -> "NUMBER";
    case Integer i -> "INTEGER"; // Bị case Number bao trùm
    default -> "OTHER";
};
~~~

Đây là đoạn minh họa lỗi với `Object value`. `Integer` là `Number`, nên compiler không cho nhánh `Integer` đứng sau một type pattern `Number` không guard. Sắp xếp trường hợp chuyên biệt trước.

## 13. Những sai lầm thường gặp khi thiết kế giá trị của nhánh

1. **Nhầm phần kiểm tra pattern với phần trả kết quả.** `case String s` chỉ kiểm tra/gắn biến; `-> expression` hoặc `yield` mới cung cấp giá trị cho switch expression.
2. **Dùng `break` hoặc `return` trong block của switch expression.** Hai câu lệnh này không thay được `yield`.
3. **Chỉ gán biến cục bộ rồi quên yield.** Một block hoàn tất bình thường phải cung cấp giá trị; compiler không tự lấy biến cuối làm kết quả.
4. **Bỏ sót trường hợp đầu vào.** Switch expression phải exhaustive; với selector `Object` thường dùng `default`.
5. **Tin rằng default tự bắt null.** Trên switch pattern Java 21, xử lý `null` bằng case riêng nếu muốn trả giá trị từ đầu vào null.
6. **Nghĩ mọi nhánh phải có cùng kiểu runtime.** Khi có target type thích hợp như `Number`, nhánh `Integer`/`Double`/`Long` có thể cùng hợp lệ mà vẫn giữ wrapper runtime riêng.
7. **Nghĩ rule có throw cũng phải yield.** `throw` kết thúc bất thường; nó không cần giá trị kết quả bình thường.
8. **Quên thứ tự case có guard và subtype.** Guard cụ thể và subtype cần đứng trước nhánh bao quát nếu muốn xử lý riêng.
9. **Sử dụng pattern variable ngoài nhánh của nó.** `s` của `case String s` chỉ có phạm vi trong guard và rule hoặc group tương ứng; không được sử dụng ở `case Number n`.
10. **Dùng cấu hình Java cũ.** Các ví dụ pattern switch ở đây yêu cầu JDK 21+.

## 14. Bài tập và đáp án

### Bài 1 — Dự đoán giá trị

Giả sử:

~~~java
static String category(Object value) {
    return switch (value) {
        case null -> "NULL";
        case String s when s.isEmpty() -> "EMPTY";
        case String s -> "TEXT:" + s.length();
        case Number n -> "NUMBER";
        default -> "OTHER";
    };
}
~~~

Với `category("")`, `category("hi")`, `category(12)` và `category(null)`, kết quả lần lượt là gì?

**Đáp án:** `EMPTY`, `TEXT:2`, `NUMBER`, `NULL`. Guard `isEmpty()` chỉ đúng với chuỗi không có ký tự (khác `isBlank()`, vốn còn đúng với chuỗi toàn khoảng trắng).

### Bài 2 — Điền yield

Điền nội dung còn thiếu:

~~~java
static int score(Object input) {
    return switch (input) {
        case String s -> {
            int n = s.length();
            // Cần câu lệnh nào để trả n * 2?
        }
        default -> 0;
    };
}
~~~

**Đáp án:** `yield n * 2;`. Đây là câu lệnh đưa giá trị từ block của switch expression.

### Bài 3 — Chọn giữa return và yield

Trong một phương thức `static int calculate(Object value)`, hai câu sau có cùng ý nghĩa không?

~~~java
return switch (value) {
    case String s -> s.length();
    default -> 0;
};
~~~

~~~java
return switch (value) {
    case String s -> {
        yield s.length();
    }
    default -> 0;
};
~~~

**Đáp án:** Có, đối với các đầu vào đó, cả hai trả về cùng `int`. Dạng thứ nhất dùng rule expression; dạng thứ hai dùng block và `yield`. `return` nằm **bên ngoài** switch expression để trả khỏi phương thức.

### Bài 4 — Exhaustiveness và sealed interface

Với `sealed interface Shape permits Circle, Rectangle`, trong đó cả hai là các lớp/record thực thi hợp lệ, vì sao switch expression có `case Circle ...` và `case Rectangle ...` có thể không cần `default`?

**Đáp án:** Kiểu selector `Shape` có tập subtype được phép đã xác định. Khi tất cả subtype đã được bao phủ bởi các pattern phù hợp, compiler có thể chứng minh tính exhaustive. Tuy nhiên, `null` vẫn cần được cân nhắc riêng ở runtime.

### Bài 5 — Kiểu kết quả

Một phương thức trả `Number` dùng switch expression với các nhánh `-> 1`, `-> 2.5` và `-> 3L`. Vì sao hợp lệ, và giá trị runtime thuộc lớp nào?

**Đáp án:** Ba giá trị có thể được boxing thành `Integer`, `Double`, `Long`; tất cả đều là subtype của `Number`. Đừng suy ra mọi switch expression trộn số đều sẽ cho kiểu `Number` nếu không có target type tương ứng.

### Bài 6 — Nhánh ném ngoại lệ

Hãy sửa một `switch(Object value)` sao cho chỉ nhận `String`, còn lại báo lỗi:

~~~java
static int length(Object value) {
    return switch (value) {
        case String s -> s.length();
        // Viết cách xử lý null và các kiểu khác
    };
}
~~~

**Đáp án tham khảo:**

~~~java
static int length(Object value) {
    return switch (value) {
        case String s -> s.length();
        case null -> throw new IllegalArgumentException("null");
        default -> throw new IllegalArgumentException("wrong type");
    };
}
~~~

Nếu `value` là `String`, biểu thức có kết quả `int`. Các trường hợp khác kết thúc bằng ngoại lệ, không cần tạo giá trị giả.

## 15. Checklist khi viết switch expression có pattern

Trước khi kết thúc một switch expression, hãy kiểm tra:

1. Selector có kiểu tĩnh nào và những loại giá trị runtime nào có thể xuất hiện?
2. Case pattern và guard nào được chọn? Các subtype và guard cụ thể đã đặt trước nhánh bao quát chưa?
3. Mỗi rule `-> expression` có thực sự sinh **giá trị** mong muốn không?
4. Mỗi block `-> { ... }` có `yield` trên các đường hoàn tất bình thường không?
5. Nếu dùng dạng `case ...:`, mỗi đường thực thi có `yield` hoặc ném ngoại lệ hợp lệ không?
6. Giá trị các nhánh có tương thích với target type hoặc kiểu suy luận của switch expression không?
7. Switch đã exhaustive chưa? Có cần `default` hoặc sealed type coverage không?
8. Giá trị `null` có được xử lý rõ khi nghiệp vụ yêu cầu không?
9. Có nhầm `break`/`return`/`yield` hoặc phạm vi pattern variable giữa các nhánh không?
10. Mã đang dùng Java 21+ cho pattern matching trong `switch` chứ?

**Ghi nhớ:** *pattern chọn nhánh*, còn *expression hoặc yield quyết định giá trị của nhánh*. Một switch expression chỉ hoàn tất bình thường khi nhánh được chọn đã cung cấp một giá trị tương thích với kiểu của biểu thức; nhánh `throw` thay vào đó kết thúc bất thường.

### Tham khảo đặc tả Java 21

- JLS `15.28 — Switch Expressions: https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.28
- JLS `14.21 — Yield Statement: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.21
- JLS `14.11.1 — Switch Blocks, case labels, dominance: https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11.1
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
