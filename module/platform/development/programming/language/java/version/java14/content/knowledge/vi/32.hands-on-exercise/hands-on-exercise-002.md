# Kiểm thử yield, nhánh throw và kiểu kết quả hỗn hợp trong switch expression

## 1. Mục tiêu của bài thực hành tổng hợp

Từ **Java 14**, `switch expression` đã là một cấu trúc ngôn ngữ **chính thức** theo JEP 361. Khác với `switch statement` truyền thống chủ yếu thực hiện các câu lệnh, switch expression **tạo một kết quả** được sử dụng trong phép gán, lời gọi phương thức hoặc biểu thức lớn hơn. Tuy nhiên, một nhánh có thể **ném ngoại lệ** thay vì tạo kết quả. Những nhánh hợp lệ khác có thể sinh ra **các kiểu dữ liệu khác nhau**.

Bài **“Kiểm thử yield, nhánh throw và kiểu kết quả hỗn hợp”** thuộc mục **Thực hành tổng hợp** tập trung vào ba trục:

- **`yield`**: chứng minh mỗi đường đi tạo đúng giá trị, kể cả arrow block, nhóm label dấu hai chấm và điều kiện bên trong block.
- **`throw`**: chứng minh nhánh lỗi ném đúng **exception class**, có message đúng với thông điệp do ứng dụng định nghĩa, và không tiếp tục chạy nhánh khác.
- **Kiểu kết quả hỗn hợp**: chứng minh compiler và runtime xử lý `int`, `double`, `String` như thế nào khi switch expression có target type `Object`, `Number` hoặc khi suy luận kiểu bằng `var`.

Để kết quả đáng tin, bài có **chương trình Java 17+ hoàn chỉnh**, tự chạy **26 assertions**, một **ma trận nhánh**, bốn **ví dụ compiler phải từ chối**, cách diễn giải output và các bài tự kiểm tra.

**Special Note:** Chỉ dùng quy tắc Java còn hiệu lực trên Java 17 và JDK hiện đại. Cú pháp switch expression được **chính thức hóa từ Java 14**, không dùng kỹ thuật preview lịch sử, cũng không dựa vào các switch selector primitive hiện còn thuộc diện preview ở một số JDK mới.

## 2. Ôn lại cú pháp chuẩn

### 2.1. Arrow expression trực tiếp

~~~java
int letters = switch (day) {
    case "MONDAY", "FRIDAY" -> 6;
    case "TUESDAY" -> 7;
    default -> 0;
};
~~~

Đây là mảnh code đặt trong method có biến `String day`. Với `case L -> expression;`, chính expression tạo kết quả; **không cần thêm `yield`**. Arrow case không tự fall-through sang case khác.

### 2.2. Arrow block phải yield khi có kết quả

~~~java
int letters = switch (day) {
    case "MONDAY" -> {
        int length = "MONDAY".length();
        yield length;
    }
    case "TUESDAY" -> 7;
    default -> 0;
};
~~~

Khi `->` đi với block `{ ... }`, có thể viết nhiều statements, log hoặc rẽ nhánh trước khi tạo giá trị. `yield length;` **chuyển giá trị đến switch expression bao ngoài**, không phải lệnh trả khỏi toàn bộ phương thức. Nếu block có thể chạy xong bình thường mà không `yield` hoặc `throw`, compiler báo lỗi.

### 2.3. Colon labels và yield

~~~java
String category = switch (code) {
    case 10:
    case 11:
        yield "PAIR";
    case 12:
        yield "ONE";
    default:
        yield "OTHER";
};
~~~

Đây cũng là mảnh code trong method có `int code`. `case 10:` và `case 11:` là hai label dùng chung một statement group. Trong switch expression, `yield` mới tạo giá trị; **`break;` không thay cho `yield`**. Kiểm thử vẫn phải có **cả input 10 lẫn 11**, dù chúng chung đoạn code.

### 2.4. Throw branch không tạo kết quả

~~~java
String category = switch (code) {
    case 0 -> "READY";
    case 1 -> {
        String state = "RUNNING";
        yield state;
    }
    default -> throw new IllegalArgumentException(
            "unknown code: " + code);
};
~~~

`throw` là cách kết thúc bất thường hợp lệ của một nhánh. Nó **không tạo ra kiểu kết quả String**, không phải `yield null`, và không chuyển sang default sau đó. Caller nhận ngoại lệ nếu không có handler khác bắt lại.

## 3. Quy tắc kiểu: poly expression và standalone expression

JLS Java 17 phân biệt hai bối cảnh:

- **Poly expression**: switch expression ở vị trí có **target type** (như assignment hoặc invocation), các result expressions được kiểm tra tương thích với target.
- **Standalone expression**: compiler suy ra kiểu của switch từ các result expressions; nếu chúng toàn numeric, áp dụng **numeric promotion**, nếu mixed reference/primitive không chỉ toàn numeric, có thể dùng boxing và **least upper bound**.

Nhánh `throw` **không góp một result expression** có giá trị vào phép xác định kiểu.

| Ngữ cảnh | Các nhánh giá trị | Ý nghĩa kiểm thử |
|---|---|---|
| `Object result = switch (...)` | `7`, `2.5`, `"READY"` | Primitive được boxing; runtime types là `Integer`, `Double`, `String` |
| `Number number = switch (...)` | `10`, `2.5` | `Number` là target type, hai runtime wrappers vẫn khác nhau |
| `var result = switch (...)` | `4`, `2.5` | Standalone numeric promotion thành `double`, nhánh 4 thành `4.0` |
| `String text = switch (...)` | `"OK"`, `"OTHER"` | Mỗi result expression phải tương thích với String |
| `int count = switch (...)` | `0`, `1`, `throw ...` | Throw không cần tạo int; các đường bình thường phải tạo int |

### 3.1. Object target giữ nhiều runtime types

~~~java
Object value = switch (code) {
    case 0 -> 7;
    case 1 -> 2.5;
    case 2 -> "READY";
    default -> throw new IllegalArgumentException("bad code");
};
~~~

Nếu `code` là 0, runtime object là `Integer(7)`; nếu 1 thì `Double(2.5)`; nếu 2 thì `String("READY")`. Điều này **không có nghĩa mọi switch trộn kiểu sẽ tự có static type Object**. Ở đây **chúng ta chủ động chọn target type Object** để mọi result expression tương thích.

Đừng dùng `value.toString()` làm phép thử kiểu: hai giá trị có thể in giống nhau dù runtime type khác. Nên kiểm tra giá trị bằng `equals` và loại bằng `getClass()` hoặc `instanceof`.

### 3.2. Number target giữ boxing của từng nhánh

~~~java
Number n = switch (code) {
    case 0 -> 10;
    case 1 -> 2.5;
    default -> throw new IllegalArgumentException("bad number code");
};
~~~

`10` được boxing thành `Integer`, `2.5` thành `Double`. Vì target type là `Number`, Java không bắt buộc chuyển cả hai runtime objects thành Double. Test về **runtime class** giúp phát hiện thay đổi API contract do refactor.

### 3.3. var với các result numeric

~~~java
var n = switch (code) {
    case 0 -> 4;
    case 1 -> 2.5;
    default -> throw new IllegalArgumentException("bad number code");
};
~~~

`var` được suy luận từ standalone switch expression. Với `int` và `double`, kết quả là `double` theo numeric promotion. Giá trị nhánh 0 sẽ là `4.0`, khác với `Integer(4)` trong một Object-target switch.

**Không giả định `var` luôn là Object khi kiểu các nhánh khác nhau.** Với result expressions thuộc reference types khác nhau, compiler có thể suy ra type liên quan least upper bound, thậm chí intersection type. Để API và test rõ ràng, chọn một type có ý nghĩa đối với miền nghiệp vụ hoặc khai báo `Object`/`Number` khi việc trộn kiểu thực sự cần thiết.

### 3.4. Không phải mọi kiểu đều tương thích target

~~~java
String text = switch (code) {
    case 0 -> "OK";
    default -> 7;
};
~~~

Đây là **đoạn cố ý sai**: kiểu `int` không tương thích với target type `String`. Không nên cố ép `(String)(Object)7`, vì chỉ đẩy lỗi sang runtime. Nếu muốn text, dùng `Integer.toString(7)`; nếu API thật sự cho phép số và chuỗi, chọn một target type phù hợp hoặc thiết kế một result type có ý nghĩa.

### 3.5. Switch chỉ có throw cũng sai

~~~java
int number = switch (code) {
    case 0 -> throw new IllegalStateException();
    default -> throw new IllegalArgumentException();
};
~~~

Trong Java 17, switch expression **phải có ít nhất một result expression**. Nếu tất cả branches chỉ throw, compiler từ chối, dù mọi đường đi đều kết thúc bất thường. Với logic chỉ ném ngoại lệ, dùng switch **statement** phù hợp, không ép tạo switch expression vô giá trị.

## 4. Ma trận kiểm thử cần bao phủ

Trước khi chạy code, liệt kê rõ input, output, runtime type và side effect.

### 4.1. Đường đi của phương thức mixed

| `code` | Rule | Expected value | Runtime type | Trace |
|---|---|---|---|---|
| `0` | Arrow block `yield 7` | `7` | `Integer` | `i` |
| `1` | Arrow block `yield 2.5` | `2.5` | `Double` | `d` |
| `2` | Arrow block `yield "READY"` | `READY` | `String` | `t` |
| `3` | `throw IllegalArgumentException` | Không có | Exception | Không đổi |
| `99` | `default` yield | `OTHER` | `String` | `x` |

Khi gọi lần lượt 0, 1, 2, 99 rồi 3 trên cùng `StringBuilder`, trace phải bằng **`idtx`**. Test kiểm tra trace giúp xác nhận đường lỗi không vô tình chạy nhánh khác hoặc để lại side effect sai.

### 4.2. Đường đi của phương thức grouped

| code | premium | Expected | Điều cần xác minh |
|---|---|---|---|
| 10 | false | `PAIR` | Colon label đầu tiên |
| 11 | true | `PAIR` | Colon label thứ hai |
| 12 | true | `VIP` | `yield` trong `if` |
| 12 | false | `STANDARD` | `yield` ở đường còn lại |
| 13 | false | `IllegalStateException` | Throw branch |
| 100 | false | `OTHER` | Default |

Một case có nhiều nhãn và điều kiện nội bộ **không thể được xem là đã test đủ** chỉ vì một input bất kỳ vào case đó chạy thành công.

### 4.3. Numeric và enum

Phương thức `numeric` dùng target `Number`, test cả giá trị **và** class `Integer`/`Double`. Phương thức `promoted` dùng `var` và kiểm tra `4.0`/`2.5`. Phương thức `state` switch trên enum `NEW`/`DONE`, không có default khi enum đã được bao phủ toàn bộ, đồng thời kiểm tra input `null` trong Java 17 phải ném `NullPointerException`.

## 5. Các nguyên tắc viết phép kiểm thử tin cậy

**Thứ nhất — giá trị và kiểu phải được test riêng khi có kết quả hỗn hợp.** `Integer(7)` và `Double(7.0)` có thể cùng được in thành các chuỗi giống nhau trong một số format; việc kiểm tra runtime class giúp chứng minh API return đúng kiểu.

**Thứ hai — test nhánh throw bằng đúng exception class.** Bắt mọi `Exception` rồi cho PASS có thể vô tình chấp nhận `NullPointerException` do bug. Với message do code chủ động tạo, có thể assert exact message. Với message do JVM sinh, tránh ràng buộc chính xác toàn văn.

**Thứ ba — test default, enums và các đường yield điều kiện.** Java compiler giúp kiểm tra exhaustiveness nhưng không thay thế test về behavior của từng case.

**Thứ tư — phân biệt compile-time failure với runtime exception.** Code sai `yield` hoặc sai target type không thể được test bằng `assertThrows` vì nó còn chưa biên dịch.

**Thứ năm — không dùng Java `assert` một cách mặc định để đo tính đúng của test suite.** Từ khóa `assert` có thể bị vô hiệu hóa nếu không chạy `java -ea`. Bài dưới sử dụng helper tự ném `AssertionError` nên luôn kiểm tra; trong dự án thực có thể dùng JUnit.

## 6. Chương trình Java 17+ hoàn chỉnh: 26 assertions

Lưu chương trình vào **`SwitchYieldMixedTest.java`**. Đây là class tự chạy, không cần thư viện ngoài JDK. Nội dung dưới đây đã được biên dịch và chạy với `javac --release 17`. Các nhánh `yield`, `throw`, type boxing/promotion, enum và null đều được kiểm tra bằng phép so sánh thực.

~~~java
import java.util.Objects;

public final class SwitchYieldMixedTest {
    enum State { NEW, DONE }
    private static int assertions;

    static Object mixed(int code, StringBuilder trace) {
        return switch (code) {
            case 0 -> { trace.append("i"); yield 7; }
            case 1 -> { trace.append("d"); yield 2.5; }
            case 2 -> { trace.append("t"); yield "READY"; }
            case 3 -> throw new IllegalArgumentException("bad code: 3");
            default -> { trace.append("x"); yield "OTHER"; }
        };
    }

    static String grouped(int code, boolean premium) {
        return switch (code) {
            case 10:
            case 11:
                yield "PAIR";
            case 12:
                if (premium) {
                    yield "VIP";
                }
                yield "STANDARD";
            case 13:
                throw new IllegalStateException("blocked: 13");
            default:
                yield "OTHER";
        };
    }

    static Number numeric(int code) {
        return switch (code) {
            case 0 -> 10;
            case 1 -> 2.5;
            default -> throw new IllegalArgumentException("number: " + code);
        };
    }

    static double promoted(int code) {
        var result = switch (code) {
            case 0 -> 4;
            case 1 -> 2.5;
            default -> throw new IllegalArgumentException("promoted: " + code);
        };
        return result;
    }

    static String state(State state) {
        return switch (state) {
            case NEW -> "new";
            case DONE -> "done";
        };
    }

    static void equal(Object expected, Object actual, String label) {
        assertions++;
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    label + " expected=" + expected + " actual=" + actual);
        }
    }

    static void sameType(Class<?> expected, Object value, String label) {
        assertions++;
        if (value == null || value.getClass() != expected) {
            throw new AssertionError(
                    label + " expectedType=" + expected.getName());
        }
    }

    static void throwsExactly(Class<? extends Throwable> expected,
                              String expectedMessage, Runnable action) {
        assertions++;
        try {
            action.run();
        } catch (Throwable actual) {
            if (actual.getClass() == expected
                    && (expectedMessage == null
                        || Objects.equals(expectedMessage, actual.getMessage()))) {
                return;
            }
            throw new AssertionError("wrong exception: " + actual, actual);
        }
        throw new AssertionError("expected " + expected.getSimpleName());
    }

    public static void main(String[] args) {
        StringBuilder trace = new StringBuilder();
        Object i = mixed(0, trace);
        Object d = mixed(1, trace);
        Object t = mixed(2, trace);
        Object x = mixed(99, trace);

        equal(7, i, "int value");
        sameType(Integer.class, i, "int type");
        equal(2.5, d, "decimal value");
        sameType(Double.class, d, "decimal type");
        equal("READY", t, "text value");
        sameType(String.class, t, "text type");
        equal("OTHER", x, "fallback value");
        throwsExactly(IllegalArgumentException.class, "bad code: 3",
                () -> mixed(3, trace));
        equal("idtx", trace.toString(), "yield/throw trace");

        equal("PAIR", grouped(10, false), "colon 10");
        equal("PAIR", grouped(11, true), "colon 11");
        equal("VIP", grouped(12, true), "nested first yield");
        equal("STANDARD", grouped(12, false), "nested second yield");
        equal("OTHER", grouped(100, false), "colon fallback");
        throwsExactly(IllegalStateException.class, "blocked: 13",
                () -> grouped(13, false));

        Number n0 = numeric(0);
        Number n1 = numeric(1);
        equal(10, n0, "poly int");
        sameType(Integer.class, n0, "poly Integer");
        equal(2.5, n1, "poly double");
        sameType(Double.class, n1, "poly Double");
        throwsExactly(IllegalArgumentException.class, "number: 9",
                () -> numeric(9));

        equal(4.0, promoted(0), "numeric promoted int");
        equal(2.5, promoted(1), "numeric promoted double");
        throwsExactly(IllegalArgumentException.class, "promoted: 9",
                () -> promoted(9));

        equal("new", state(State.NEW), "enum new");
        equal("done", state(State.DONE), "enum done");
        throwsExactly(NullPointerException.class, null, () -> state(null));

        System.out.println("mixed=" + i.getClass().getSimpleName() + ":"
                + i + "," + d.getClass().getSimpleName() + ":" + d
                + "," + t.getClass().getSimpleName() + ":" + t);
        System.out.println("trace=" + trace);
        System.out.println("numeric=" + n0.getClass().getSimpleName()
                + "," + n1.getClass().getSimpleName());
        System.out.println("promoted=" + promoted(0) + "," + promoted(1));
        System.out.println("grouped=" + grouped(10, false) + ","
                + grouped(12, true) + "," + grouped(12, false));
        System.out.println(
                "exceptions=IllegalArgumentException,IllegalStateException,NullPointerException");
        System.out.println("PASS assertions=" + assertions);
    }
}
~~~

### Lệnh biên dịch và chạy

~~~bash
javac --release 17 SwitchYieldMixedTest.java
java SwitchYieldMixedTest
~~~

Không cần bật bất kỳ preview feature nào. Chạy từ thư mục chứa source, có `javac` và `java` của JDK phù hợp trong PATH. Khi test sai, helper sẽ ném `AssertionError` và không in dòng PASS cuối cùng.

### Stdout đã chạy thực tế

~~~text
mixed=Integer:7,Double:2.5,String:READY
trace=idtx
numeric=Integer,Double
promoted=4.0,2.5
grouped=PAIR,VIP,STANDARD
exceptions=IllegalArgumentException,IllegalStateException,NullPointerException
PASS assertions=26
~~~

**Số lượng assertions** được kiểm tra:

| Nhóm | Giá trị/nhánh/kiểu | Số phép thử |
|---|---|---:|
| `mixed` | int/double/text, types, fallback, throw và trace | 9 |
| `grouped` | Hai labels, hai yield paths, fallback, throw | 6 |
| `numeric` | Hai giá trị, hai runtime wrapper types, throw | 5 |
| `promoted` | 4.0, 2.5 và throw | 3 |
| `state` | NEW, DONE và null | 3 |
| **Tổng** | | **26** |

### Vì sao helper kiểm tra exception dùng null cho expectedMessage?

Trong `throwsExactly`, tham số `expectedMessage==null` được hiểu là **không kiểm tra message**, không phải kỳ vọng thực tế ngoại lệ phải có message null. `NullPointerException` do JVM sinh có thể chứa **Helpful NPE message**, thay đổi theo compiler/JDK. Khi kiểm tra `state(null)`, phần quan trọng là đúng exception type; message cụ thể không phải thông điệp do ứng dụng quản lý.

### Vì sao trace quan trọng?

Bốn lần gọi thành công `mixed(0,1,2,99)` nối `i`, `d`, `t`, `x`. Sau khi `mixed(3, trace)` ném lỗi, trace phải giữ nguyên. Nếu default chạy sau throw, nếu branch bị nhầm, hoặc code có side effect thừa, một trong các test sẽ thất bại.

### Khác biệt của numeric và promoted

`numeric(0)` trả `Number` chứa `Integer`, trong khi `promoted(0)` trả primitive `double` là `4.0`. Cả hai đều hợp lệ; đừng refactor `Number` thành `var` rồi mặc định hợp đồng về runtime type giữ nguyên.

### Enum exhaustive

`State` chỉ có `NEW` và `DONE`, nên `state(State)` có thể không dùng default theo Java 17. Nếu enum thêm một constant và biên dịch lại, compiler buộc bạn xử lý đủ nhánh. Với binary enum thay đổi mà code không biên dịch lại, runtime behavior có thể khác; phải có versioning/regression tests phù hợp.

## 7. Những ví dụ compiler phải từ chối

Bộ test thực thi nói trên đã PASS. Để kiểm tra **các quy tắc không hợp lệ**, tạo **bốn file độc lập**, chạy `javac --release 17` trên từng file và kỳ vọng **exit code khác 0**. Các ví dụ dưới là code cố ý sai, **không được đưa vào file runnable**.

### 7.1. Không dùng break mang giá trị

Lưu `InvalidBreak.java`:

~~~java
class InvalidBreak {
    static int bad(int x) {
        return switch (x) {
            case 0: break 7;
            default: yield 8;
        };
    }
}
~~~

Trong switch expression Java 17+, cú pháp `break 7;` **không hợp lệ**. Cách trả kết quả trong colon group là `yield 7;`. Đây là test từ chối syntax cũ không còn áp dụng, không phải hướng dẫn sử dụng một tính năng legacy.

### 7.2. Arrow block thiếu yield

Lưu `InvalidMissingYield.java`:

~~~java
class InvalidMissingYield {
    static int bad(int x) {
        return switch (x) {
            case 0 -> {
                System.out.println("side effect");
            }
            default -> 1;
        };
    }
}
~~~

Compiler từ chối vì block có đường đi **hoàn thành bình thường nhưng không tạo giá trị**. Một diagnostic quan sát được từ `javac` là `switch rule completes without providing a value`. Sửa bằng `yield 0;` sau side effect, hoặc `throw` nếu nhánh thực sự biểu thị lỗi nghiệp vụ.

### 7.3. Mixed result incompatible với target String

Lưu `InvalidMixedTarget.java`:

~~~java
class InvalidMixedTarget {
    static String bad(int x) {
        return switch (x) {
            case 0 -> "text";
            default -> 7;
        };
    }
}
~~~

Result expression `7` không gán được vào `String` target. Muốn text, dùng `Integer.toString(7)`; muốn API thực sự hỗn hợp, chọn type cho phép kết quả hỗn hợp và test runtime types.

### 7.4. Toàn bộ các nhánh đều throw

Lưu `InvalidNoValue.java`:

~~~java
class InvalidNoValue {
    static int bad(int x) {
        return switch (x) {
            case 0 -> throw new IllegalStateException();
            default -> throw new IllegalArgumentException();
        };
    }
}
~~~

JLS yêu cầu switch expression có ít nhất **một result expression**. Nếu mục tiêu chỉ chọn ngoại lệ để ném, dùng switch statement thay vì cố biểu diễn kết quả không tồn tại.

### Kiểm tra bằng javac

~~~bash
javac --release 17 InvalidBreak.java
javac --release 17 InvalidMissingYield.java
javac --release 17 InvalidMixedTarget.java
javac --release 17 InvalidNoValue.java
~~~

**Tất cả các lệnh này được kỳ vọng thất bại.** Bốn trường hợp đã được chạy thử và `javac --release 17` đều trả exit code khác 0. Thông báo đầy đủ của compiler có thể khác theo release, OS và vị trí dòng; một negative-test harness nên kiểm tra exit code và một phần diagnostic bền vững thay vì hard-code toàn bộ output gồm path/line numbers.

**Tách hai cấp kiểm tra:** code sai compile-time không được kiểm thử bằng `assertThrows` lúc runtime, bởi nó không thể tạo bytecode để chạy. Với source hợp lệ, kiểm thử runtime mới xác minh giá trị, side effect và ngoại lệ.

## 8. Khi sử dụng JUnit trong dự án

Chương trình 26 assertions chạy được chỉ với JDK. Dự án thực tế thường đã dùng JUnit Jupiter để tổ chức nhiều test, chạy trên CI và báo cáo kết quả từng method. Khi có dependency JUnit phù hợp, có thể tạo **`SwitchYieldMixedJUnitTest.java`** trong cùng package:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class SwitchYieldMixedJUnitTest {
    @Test
    void mixedValueAndType() {
        Object value = SwitchYieldMixedTest.mixed(
                1, new StringBuilder());
        assertEquals(2.5, value);
        assertInstanceOf(Double.class, value);
    }

    @Test
    void throwsExpectedClassAndMessage() {
        IllegalArgumentException error = assertThrows(
                IllegalArgumentException.class,
                () -> SwitchYieldMixedTest.mixed(
                        3, new StringBuilder()));
        assertEquals("bad code: 3", error.getMessage());
    }

    @Test
    void checksBothYieldPaths() {
        assertEquals("VIP",
                SwitchYieldMixedTest.grouped(12, true));
        assertEquals("STANDARD",
                SwitchYieldMixedTest.grouped(12, false));
    }
}
~~~

Đây là **ví dụ tích hợp framework**, **không phải mã đã chạy trong lần thử JDK-only**: nó cần JUnit Jupiter trong dependencies và test runner Maven/Gradle/JUnit Platform. Các static methods trong class demo là package-private nên file test phải nằm **cùng package** (hoặc API được điều chỉnh có chủ đích). Cấu hình test build nên quyết định phiên bản JUnit được hỗ trợ; không giả định Java standard library tự cung cấp `@Test` hoặc `assertThrows`.

**Lợi ích khi chuyển sang JUnit:** dễ tách case, dùng parameterized tests cho selector values, có report CI và dễ đo branch coverage. Tuy nhiên, coverage phần trăm cao không tự chứng minh đúng **runtime type** hay đúng **exception message**; assertions về hợp đồng vẫn cần rõ.

## 9. Xử lý những tình huống biên

### 9.1. Null selector trong Java 17

Với switch enum trong bài:

~~~java
String stateLabel = switch (state) {
    case NEW -> "new";
    case DONE -> "done";
};
~~~

Nếu selector `state` bằng null trên Java 17, có `NullPointerException`. Không có nghĩa default tự bắt null. Những phiên bản Java mới hơn có một số dạng switch hỗ trợ `case null` ổn định, nhưng không đem cú pháp ngoài phạm vi vào ví dụ Java 17 rồi tuyên bố không cần cấu hình thêm.

### 9.2. Exhaustiveness không thay thế branch testing

Compiler bắt buộc switch expression bao phủ các trường hợp cần thiết, nhưng nó không biết `case 12` nên trả VIP hay STANDARD. Do đó ma trận test cần ít nhất một input cho mỗi label/đường điều kiện, một input cho default, và input ném exception.

### 9.3. Throw có thể phát sinh trước yield

~~~java
case 5 -> {
    recordAudit();
    yield createResult();
}
~~~

Đây là ví dụ **chỉ minh họa**, giả sử đã có method `recordAudit` và `createResult`. Nếu `recordAudit()` ném exception, `yield` không chạy. Một test bổ sung trong ứng dụng thực nên mô phỏng lỗi của dependency bên trong branch và kiểm tra việc không tạo kết quả sai. Đừng chỉ test các exception được viết trực tiếp ngay sau `->`.

### 9.4. Yield không bỏ qua quy tắc method control flow

`yield` target là **switch expression gần nhất**, không phải statement `if` hay phương thức Java. Không dùng `return`, `break` hoặc `continue` tùy ý trong block để thay cho việc tạo result. Khi có nested switch expressions, cần xác định `yield` thuộc expression nào; code khó đọc nên được tách thành hàm nhỏ có type rõ.

### 9.5. Trường hợp nhận null làm result

Với `Object` hoặc `String` target type, `yield null;` có thể hợp lệ theo type system nhưng caller phải xử lý null; `result.getClass()` sẽ ném NPE. Nếu miền nghiệp vụ cấm null, nên dùng `throw` hoặc một kiểu kết quả biểu đạt rõ tình trạng thay vì phát null bất ngờ.

### 9.6. Tránh thiết kế API có mixed result types tùy tiện

Bài tập dùng `Object` để minh họa boxing và type inference. Trong dự án thực tế, nếu caller thường xuyên phải hỏi `instanceof Integer`/`Double`/`String`, nên cân nhắc trả một record/sealed domain result (nếu đó là mô hình phù hợp) hoặc chuẩn hóa các case sang một kiểu cụ thể. Mục tiêu là hợp đồng API rõ, không phải làm switch khó đoán kiểu.

## 10. Sai lầm thường gặp và hướng sửa

| Lỗi | Biểu hiện | Cách sửa |
|---|---|---|
| Arrow block chỉ log rồi hết | Compile error vì thiếu result | `yield` hoặc `throw` |
| `break 7;` trong switch expression | Compile error | `yield 7;` |
| Dùng `break;` để trả kết quả | Không tạo giá trị | Dùng `yield value;` |
| Dùng `return` trong rule block để thay yield | Sai điều khiển luồng | Dùng `yield` |
| Không có result expression nào | Compiler từ chối switch chỉ throw | Dùng switch statement khi chỉ cần throw |
| Target `String` nhưng nhánh trả `int` | Incompatible result type | Chuyển kiểu đúng hoặc đổi target type |
| `var` được mặc định xem là `Object` | Sai inference | Kiểm tra numeric promotion/LUB |
| `Number` bị tưởng là luôn `Double` | Sai runtime wrapper | Test `Integer` và `Double` |
| Chỉ test một label trong nhóm colon | Thiếu coverage | Test mọi label cần thiết |
| Chỉ test `premium=true` | Bỏ sót yield còn lại | Test true/false |
| Bắt bất kỳ exception và cho PASS | Có thể che bug | Kiểm tra exact class và message có chủ đích |
| Bắt buộc message JVM NPE bằng null | Test dễ vỡ giữa JDK | Kiểm tra NPE class, không cố định message |
| Cho rằng default bắt null Java 17 | Có thể NPE | Test null theo hợp đồng |
| Dùng Java keyword `assert` nhưng không có `-ea` | Tests không chạy | JUnit hoặc helper ném AssertionError |
| Test code không biên dịch bằng runtime asserts | Không chạy được | Tách negative compilation tests |
| Tin compiler diagnostics giống nhau mọi JDK | CI flaky | Kiểm tra exit code và pattern ổn định |
| Thay enum constants nhưng không recompile/test | Có thể mismatch behavior | Recompile và cập nhật test cases |
| Dùng kiểu hỗn hợp `Object` ở mọi API | Caller ép kiểu rối | Chọn domain result type rõ ràng |
| Dùng tính năng switch preview mới với `--release 17` | Compile failure | Dùng syntax ổn định đúng source target |

## 11. Checklist kiểm thử trước khi hoàn tất

- [ ] Đã tạo đúng file `SwitchYieldMixedTest.java` có class public cùng tên.
- [ ] Biên dịch bằng `javac --release 17` thành công.
- [ ] Chạy `java SwitchYieldMixedTest` và thấy `PASS assertions=26`.
- [ ] Đã test arrow expression và arrow block có `yield`.
- [ ] Đã test colon form với hai label chung.
- [ ] Đã test hai `yield` khác nhau theo điều kiện `premium`.
- [ ] Đã test nhánh `throw` đúng exception class.
- [ ] Message ứng dụng tự viết được kiểm tra khi cần.
- [ ] Không hard-code JVM Helpful NPE message.
- [ ] Đã test default/fallback.
- [ ] Đã test runtime `Integer`/`Double`/`String` dưới target `Object`.
- [ ] Đã test `Integer`/`Double` trong target `Number`.
- [ ] Đã test numeric promotion dưới `var`.
- [ ] Đã test enum exhaustive và null selector theo Java 17.
- [ ] Đã test trace/side effect không thay đổi sau throw.
- [ ] Đã biên dịch riêng các mẫu sai và xác nhận javac trả nonzero.
- [ ] Không đặt negative samples cùng file runnable.
- [ ] Nếu dùng JUnit, đã khai báo dependencies và chạy bằng test runner thực.
- [ ] Khi thêm case/enum constant, đã cập nhật ma trận test.
- [ ] Không nhầm kiểm thử compile-time với runtime exception test.

## 12. Tự kiểm tra kiến thức

**Câu 1.** `case 1 -> 10;` có cần `yield` không?

**Đáp án:** Không. Expression sau arrow là result expression trực tiếp của switch expression.

**Câu 2.** `case 1 -> { System.out.println("x"); }` có hợp lệ nếu switch cần trả int không?

**Đáp án:** Không. Block hoàn thành bình thường mà không tạo giá trị; cần yield hoặc throw.

**Câu 3.** `case 1 -> throw new IllegalArgumentException();` trong switch trả String có hợp lệ không?

**Đáp án:** Có. Throw kết thúc bất thường, không cần giá trị String.

**Câu 4.** Tất cả nhánh chỉ throw có tạo được switch expression Java 17 không?

**Đáp án:** Không. Switch expression phải có ít nhất một result expression.

**Câu 5.** `String text = switch(x) { case 0 -> "OK"; default -> 7; };` có compile không?

**Đáp án:** Không. Result `int` không tương thích target String.

**Câu 6.** `Number n = switch(x){case 0 -> 10;default -> 2.5;};` giữ runtime types nào?

**Đáp án:** Integer và Double tương ứng với hai nhánh.

**Câu 7.** `var n = switch(x){case 0 -> 4;default -> 2.5;};` suy ra kiểu gì?

**Đáp án:** double, do numeric promotion trong standalone switch expression.

**Câu 8.** Tại sao phải test `grouped(12,true)` và `grouped(12,false)`?

**Đáp án:** Vì đó là hai đường yield khác nhau nằm trong cùng case.

**Câu 9.** Vì sao không ép Helpful NPE message phải rỗng?

**Đáp án:** JVM có thể sinh message khác theo JDK và ngữ cảnh; loại NPE mới là hợp đồng nên test ở đây.

**Câu 10.** Khi enum đã cover mọi constant, có cần default không?

**Đáp án:** Không bắt buộc trong Java 17; compiler kiểm tra exhaustiveness.

**Câu 11.** Code không thể biên dịch vì thiếu yield nên test bằng `assertThrows` không?

**Đáp án:** Không. Phải kiểm tra compile-time bằng javac, thường kỳ vọng exit code khác 0.

**Câu 12.** Vì sao output value đúng vẫn có thể chưa chứng minh type đúng?

**Đáp án:** Cùng biểu diễn text có thể đến từ các runtime types khác nhau; với mixed results cần kiểm tra cả value và class.

**Câu 13.** Java `assert` và JUnit `assertEquals` có luôn chạy như nhau không?

**Đáp án:** Không. Java `assert` có thể bị tắt nếu không bật `-ea`; JUnit assertions chạy trong test runner.

**Câu 14.** Vì sao không được giả định `Object` luôn là type compiler tự suy ra khi dùng `var`?

**Đáp án:** Vì numeric promotion và least-upper-bound inference có quy tắc riêng tùy result expressions; ví dụ int/double suy ra double.

## 13. Tài liệu tham khảo

- [Oracle Java SE 17 — Switch Expressions](https://docs.oracle.com/en/java/javase/17/language/switch-expressions-and-statements.html): arrow/colon, yield, throw, exhaustiveness.
- [JLS Java SE 17 — `15.28 Switch Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.28): result expressions, poly/standalone type, numeric promotion, runtime evaluation.
- [JLS Java SE 17 — `14.11 Switch Statements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.11): switch labels, nhóm colon và phân biệt statement/expression.
- [JLS Java SE 17 — `14.21 Yield Statement](https://docs.oracle.com/javase/specs/jls/se17/html/jls-14.html#jls-14.21): yield target, chuyển điều khiển và các giới hạn hợp lệ.
- [OpenJDK JEP 361 — Switch Expressions](https://openjdk.org/jeps/361): chuyển switch expressions thành tính năng chính thức Java 14.
- [Oracle Java SE 26 — Switch Expressions and Statements](https://docs.oracle.com/en/java/javase/26/language/switch-expressions-statements.html): xác minh cú pháp cốt lõi tiếp tục được duy trì; các phần preview của JDK mới không dùng trong bài này.
- [JUnit 5 User Guide](https://docs.junit.org/5.13.4/user-guide/): tham khảo chuyển self-contained tests sang framework test với CI.

**Ghi nhớ:** `yield` trả kết quả từ rule block/colon group, `throw` làm nhánh kết thúc bất thường, còn **kiểu của switch expression** phụ thuộc vào target typing hay standalone inference. Phải kiểm thử cả value, runtime type, exception, default, các đường yield bên trong và những lỗi compile-time. Bộ kiểm thử 26 assertions cùng bốn negative compile cases minh họa cách làm điều đó bằng Java ổn định từ Java 14 trở đi.