# Reachability, return và các nhánh điều khiển không hợp lệ trong Java

Một chương trình Java có thể đúng cú pháp và đúng kiểu dữ liệu nhưng vẫn bị `javac` từ chối vì **câu lệnh không thể được đi tới**, **phương thức trả về giá trị có đường đi kết thúc mà không trả về**, hoặc **`break`/`continue` không có đích hợp lệ**. Những lỗi này thuộc phần kiểm tra ngữ nghĩa và luồng điều khiển (*control flow*) trong quá trình biên dịch.

Ví dụ, sau `return 42;` trong cùng một khối lệnh, câu lệnh thông thường phía sau không có đường thực thi; ngược lại, nếu phương thức `int` chỉ `return` khi điều kiện đúng, cần xét trường hợp điều kiện sai. Trong Java, **reachability là quy tắc phân tích tĩnh của ngôn ngữ**, không phải việc `javac` chạy thử chương trình cho mọi giá trị đầu vào.

Bài sử dụng Java 17 trở lên và tập trung vào ba câu hỏi: *Câu lệnh này có được coi là reachable không? Luồng điều khiển của phương thức có thể hoàn tất bình thường không? Và lệnh chuyển hướng điều khiển có hợp lệ trong cấu trúc đang chứa nó không?*

## 1. Cấu trúc điều khiển và hai cách kết thúc một câu lệnh

Một câu lệnh có thể **complete normally** (hoàn tất bình thường: luồng tiếp tục đến câu lệnh tiếp theo) hoặc **complete abruptly** (kết thúc đột ngột: do `return`, `break`, `continue`, `throw` hay ngoại lệ). Điều này khác với việc toàn bộ tiến trình kết thúc.

~~~java
static int answer() {
    return 42;
}
~~~

Khi `return 42;` được thực thi, phương thức thoát và trả về 42 cho nơi gọi. Nếu trong cùng một khối có câu lệnh thường đứng ngay sau `return` vô điều kiện, câu lệnh sau không thể đi tới từ đầu khối:

~~~java
static int answer() {
    return 42;
    // System.out.println("never"); // bỏ comment sẽ gây unreachable statement
}
~~~

Đoạn trên chỉ mang tính minh họa về lỗi khi bỏ comment. `return` là một cách hoàn tất đột ngột; `throw` cũng vậy, nhưng khác ở chỗ nó chuyển quyền điều khiển sang xử lý ngoại lệ, không trả về giá trị bình thường.

Một khối `{\u0020...\u0020}` được xem là có thể hoàn tất bình thường nếu luồng điều khiển có thể đi qua các câu lệnh của nó rồi đi ra cuối khối. Khái niệm này dùng để kiểm tra sự tồn tại của `return` ở phương thức có kiểu trả về khác `void`.

## 2. Reachability là kiểm tra cấu trúc theo quy tắc JLS

Một statement được xem là *reachable* nếu quy tắc phân tích của Java cho phép luồng điều khiển đi tới vị trí đó. Quy tắc được mô tả trong Java Language Specification, phần **Unreachable Statements** (JLS §14.22 đối với Java SE 17). Trình biên dịch không phải chứng minh tất cả điều kiện logic hay giải mọi bài toán dừng để phân biệt reachable/unreachable.

Các trường hợp cơ bản:

- Câu lệnh đầu tiên trong khối có thể reachable khi khối đó reachable.
- Câu lệnh kế tiếp phụ thuộc câu lệnh đứng trước có thể **complete normally** không.
- Sau `return` hoặc `throw` vô điều kiện ở cùng nhánh, một câu lệnh thường tiếp theo trở nên unreachable.
- Cấu trúc `if`, `while`, `do`, `for`, `switch`, nhãn, `break` và `try/finally` có những quy tắc riêng.
- Compiler sử dụng **constant expression** trong một số quy tắc cụ thể, nhất là điều kiện vòng lặp; không nên suy luận rằng mọi giá trị biểu thức có thể tính sẵn đều được dùng giống nhau ở mọi cấu trúc.

### 2.1. Vì sao `if (false)` và `while (false)` khác nhau?

Đây là ngoại lệ học tập quan trọng của quy tắc reachability Java:

~~~java
class IfFalseAllowed {
    public static void main(String[] args) {
        if (false) System.out.println("never");
        System.out.println("after");
    }
}
~~~

`javac --release 17 IfFalseAllowed.java` **chấp nhận** chương trình. Khi chạy, kết quả là:

~~~text
after
~~~

Ngôn ngữ cho phép các nhánh `if (false)` kiểu này để hỗ trợ các nhánh mã có thể bật/tắt bằng hằng khi phát triển; đây không phải bằng chứng rằng nhánh `if (false)` sẽ được thực thi.

Ngược lại, đoạn sau **bị từ chối**:

~~~java
class WhileFalse {
    void bad() {
        while (false) {
            System.out.println("unreachable");
        }
    }
}
~~~

Chạy `javac --release 17 WhileFalse.java` nhận lỗi `unreachable statement` tại thân vòng lặp. Quy tắc riêng của `while` xem điều kiện là hằng `false`, nên thân vòng lặp không reachable. Trường hợp `do { ... } while (false);` khác: thân `do` có thể được thực thi **một lần trước khi kiểm tra điều kiện**, vì thế có thể hợp lệ.

**Không thay** bộ quy tắc reachability của Java bằng quy tắc suy đoán “compiler đánh giá mọi `if` có điều kiện hằng và xóa nhánh không chạy”. Hai đoạn trên được kiểm chứng bằng `javac --release 17` và có kết quả biên dịch khác nhau.

### 2.2. Hằng `true`, vòng lặp vô hạn và `break`

~~~java
class WhileTrueNoBreak {
    static void run() {
        while (true) {
        }
        // System.out.println("after"); // bỏ comment: unreachable statement
    }
}
~~~

Khi điều kiện vòng lặp là constant expression `true` và không có đường `break` thích hợp được quy tắc reachability công nhận, vòng lặp không thể complete normally. Với phương thức `void`, việc không bao giờ kết thúc tự nó không sai; chỉ câu lệnh đặt sau vòng lặp đó mới có vấn đề reachability.

~~~java
class WhileTrueBreak {
    static int compute() {
        while (true) {
            break;
        }
        return 3;
    }

    public static void main(String[] args) {
        System.out.println(compute());
    }
}
~~~

Ví dụ thứ hai hợp lệ và in `3`. `break` không nhãn chấm dứt vòng `while`, vì thế `return 3;` reachable.

Điểm tinh tế: quy tắc reachability **không thay thế bằng suy luận toàn bộ giá trị runtime**. Ví dụ:

~~~java
static void unusual() {
    while (true) {
        if (false) break;
    }
    System.out.println("after");
}
~~~

Đoạn này được `javac --release 17` **chấp nhận về reachability**, vì quy tắc dành cho `if` vẫn cho phép câu lệnh `break` được xem là reachable khi kiểm tra cấu trúc vòng lặp. Khi thực thi, vòng lặp không kết thúc và dòng `println` phía sau không chạy. Đó là minh chứng rõ rằng “reachable theo JLS” không đồng nghĩa “chắc chắn có đường chạy tới trong thực tế”.

## 3. Quy tắc return trong phương thức

`return` chấm dứt việc thực thi **phương thức**, **constructor** hoặc **lambda body** đang chứa nó theo đúng ngữ cảnh cú pháp. Quy tắc loại giá trị trả về phụ thuộc vào khai báo tương ứng.

### 3.1. Phương thức void và phương thức có giá trị

Trong phương thức `void`, có thể dùng `return;` để kết thúc sớm, nhưng không được `return expression;`:

~~~java
static void printPositive(int n) {
    if (n <= 0) return;
    System.out.println(n);
}
~~~

Trong phương thức khai báo kiểu trả về `int`, các câu lệnh `return` bình thường phải có biểu thức có thể chuyển đổi hợp lệ sang `int`. Viết `return;` trong phương thức này là sai. Viết `return "42";` cũng sai vì `String` không được chuyển ngầm sang `int`.

~~~java
static int doubleValue(int n) {
    return n * 2;
}
~~~

Phương thức có kiểu trả về khác `void` **không được có khả năng complete normally tại cuối thân phương thức**. Quy tắc này giải thích lỗi `missing return statement`: có ít nhất một đường đi kết thúc thân phương thức mà không hoàn tất đột ngột theo cách được phép (chẳng hạn `return` hoặc `throw`).

### 3.2. Vì sao thiếu return dù một nhánh đã return?

Tệp ví dụ sai `MissingReturn.java`:

~~~java
public class MissingReturn {
    static int sign(int x) {
        if (x > 0) return 1;
    }
}
~~~

Lệnh `javac --release 17 MissingReturn.java` báo:

~~~text
error: missing return statement
~~~

Nếu `x <= 0`, phương thức đi qua `if` mà không trả về. Có thể sửa bằng `else`, hoặc bằng `return` ở sau `if`:

~~~java
static int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    return 0;
}
~~~

Trong cách sửa này, mọi đường đi bình thường qua các nhánh đều tới một `return`. Không cần ép một `return` duy nhất ở cuối phương thức nếu đã có nhiều nhánh kết thúc thích hợp.

### 3.3. `if (true)` không phải là bằng chứng đầy đủ return

Ví dụ:

~~~java
class IfTrueMissing {
    static int value() {
        if (true) return 1;
    }
}
~~~

Mặc dù trong lúc chạy điều kiện luôn đúng, đoạn này vẫn bị `javac --release 17` từ chối với `missing return statement`. Quy tắc đánh giá việc một `if-then` **có thể complete normally** không giống cách đánh giá `while(true)`; `if` thiếu `else` vẫn được xem xét như có khả năng đi qua nhánh không thực hiện. Đây là một ví dụ nữa cho thấy kiểm tra luồng điều khiển dựa trên các quy tắc cấu trúc xác định trong JLS.

Viết `return 1;` trực tiếp, hoặc bao phủ rõ các nhánh cần thiết, sẽ loại bỏ sự mơ hồ đó.

### 3.4. throw có thể thay cho return trên một nhánh lỗi

~~~java
static int parsePositive(String text) {
    int result = Integer.parseInt(text);
    if (result <= 0) {
        throw new IllegalArgumentException("Must be positive");
    }
    return result;
}
~~~

Nếu dữ liệu không hợp lệ, phương thức hoàn tất đột ngột bằng `throw`; nếu hợp lệ, `return` kết thúc với giá trị. Không có đường complete normally rơi qua cuối thân phương thức. Dù vậy, phương thức có thể phát sinh `NumberFormatException` lúc chạy khi chuỗi không phải số; các kiểm tra flow tĩnh không bảo đảm dữ liệu đầu vào luôn hợp lệ.

Một phương thức `int` với `while(true) { }` vô hạn cũng có thể được biên dịch dù không chứa `return`, vì thân phương thức không có khả năng complete normally. Quy tắc **không** yêu cầu mọi lần gọi bắt buộc trả về trong thời gian hữu hạn.

## 4. Nhánh điều khiển: if/else và các đường đi

Compiler xem các nhánh theo cấu trúc ngôn ngữ. Ví dụ hợp lệ:

~~~java
static String classify(int number) {
    if (number < 0) {
        return "âm";
    } else if (number == 0) {
        return "không";
    } else {
        return "dương";
    }
}
~~~

Vì mọi nhánh được bao phủ bằng `if/else if/else`, thân không thể complete normally. Có thể viết tương đương bằng hai guard clauses và `return` cuối, như chương trình đầy đủ ở phần 9.

Nếu bỏ `else` cuối mà không thêm `return` dự phòng, compiler có thể báo `missing return statement`. Khi cấu trúc logic phức tạp, nên tự kiểm tra **mỗi đường đi từ đầu phương thức đến cuối**. Những đường đi gặp `return` hoặc `throw` sẽ không đi tiếp; đường đi còn lại phải kết thúc theo quy tắc return của phương thức.

### 4.1. Return trong lambda không phải return của phương thức bên ngoài

~~~java
static int sizeOfLongNames(java.util.List<String> names) {
    long count = names.stream()
        .filter(name -> {
            if (name.length() < 5) return false;
            return true;
        })
        .count();
    return Math.toIntExact(count);
}
~~~

Hai `return` trong lambda là của **lambda**, không kết thúc `sizeOfLongNames`. Phương thức bên ngoài vẫn cần `return Math.toIntExact(count);`. Trong body lambda kiểu block, đường đi trả về phải phù hợp kiểu đích của functional interface; không thể coi `return` của lambda là một lối thoát khỏi phương thức bao quanh.

## 5. switch statement và switch expression

`switch` trong Java có hai vai trò cần phân biệt:

- **`switch` statement** điều khiển luồng thực thi; `case` có thể chứa câu lệnh, và ở dạng colon có thể có fall-through theo quy tắc.
- **`switch` expression** tạo ra **một giá trị**; các nhánh phải tuân thủ quy tắc cung cấp kết quả hoặc hoàn tất đột ngột phù hợp.

### 5.1. Switch statement không bảo đảm return nếu thiếu nhánh

Tệp cố ý sai `SwitchIncompleteReturn.java`:

~~~java
public class SwitchIncompleteReturn {
    static int value(int n) {
        switch (n) {
            case 1: return 1;
            case 2: return 2;
        }
    }
}
~~~

`javac --release 17 SwitchIncompleteReturn.java` từ chối bằng `missing return statement`: giá trị `n` khác 1, 2 làm `switch` kết thúc bình thường. Sửa bằng một `default: return ...;` phù hợp, hoặc thêm `return` sau `switch`.

Một `break` trong `switch` statement kết thúc `switch`, **không** kết thúc phương thức. Nếu phương thức cần trả về, vẫn phải bảo đảm có `return` trên mọi đường đi.

### 5.2. Switch expression dùng arrow hoặc yield

~~~java
static int points(String grade) {
    return switch (grade) {
        case "A" -> 10;
        case "B" -> 8;
        default -> 0;
    };
}
~~~

Đây là switch **expression**, có giá trị kiểu phù hợp với `int`. Với selector kiểu `String`, việc có `default` bao phủ các giá trị không khớp hai case đã nêu.

Khi cần khối lệnh trong một arm, dùng `yield` để cung cấp giá trị:

~~~java
static int adjusted(String grade) {
    return switch (grade) {
        case "A" -> {
            int bonus = 2;
            yield 8 + bonus;
        }
        default -> 0;
    };
}
~~~

`yield` trả giá trị cho **switch expression**, không trả trực tiếp khỏi phương thức bao quanh như `return`; trong ví dụ, `return` phía ngoài trả giá trị của cả switch expression. Với switch expression dùng block arrow, không thể để nhánh kết thúc bình thường mà không cho ra giá trị.

Tệp cố ý sai:

~~~java
class SwitchExpressionMissing {
    static int value(String s) {
        return switch (s) {
            case "A" -> 1;
            default -> {
                int unused = 1;
            }
        };
    }
}
~~~

`javac --release 17` báo `switch rule completes without providing a value` ở nhánh `default`. Cách sửa là thay khối bằng `default -> 0;` hoặc thêm `yield 0;` trong block.

Không dùng `break 10;` thay cho `yield 10;` trong switch expression Java 17. `yield` và `break` có trách nhiệm khác nhau.

## 6. break, continue và nhãn hợp lệ

`break` và `continue` đều là cách hoàn tất đột ngột, nhưng **đích chuyển điều khiển khác nhau**:

| Cấu trúc | `break;` không nhãn | `continue;` không nhãn |
|---|---|---|
| `for`, `while`, `do` | Thoát khỏi vòng lặp gần nhất phù hợp | Chuyển đến lần lặp tiếp theo của vòng lặp gần nhất |
| `switch` statement bên ngoài vòng lặp | Thoát khỏi `switch` | Không hợp lệ vì không có vòng lặp chứa |
| `switch` statement trong vòng lặp | Thoát khỏi `switch`, thường tiếp tục thân vòng | Tiếp tục vòng lặp bao quanh |
| Khối `if` đơn thuần | `break` không nhãn không có đích hợp lệ nếu không nằm trong loop/switch | `continue` không nhãn không hợp lệ nếu không nằm trong loop |

Ví dụ:

~~~java
static int firstOdd(int[] values) {
    for (int value : values) {
        if (value % 2 == 0) continue;
        return value;
    }
    return -1;
}
~~~

Nếu gặp số chẵn, `continue` bỏ qua phần còn lại của lượt lặp hiện tại; nếu gặp số lẻ đầu tiên, `return` thoát phương thức; nếu hết mảng, `return -1` bảo đảm không thiếu đường return.

### 6.1. break có nhãn và continue có nhãn

~~~java
static int countPositive(int[][] matrix) {
    int count = 0;
    outer:
    for (int[] row : matrix) {
        for (int n : row) {
            if (n < 0) break outer;
            if (n == 0) continue;
            count++;
        }
    }
    return count;
}
~~~

`break outer;` chuyển điều khiển ra khỏi vòng `for` mang nhãn `outer`, chứ không chỉ thoát vòng trong. `continue;` không nhãn áp dụng cho vòng `for (int n : row)` gần nhất. Nếu viết `continue outer;`, đích `outer` phải chỉ một **iteration statement** (vòng lặp) đang bao quanh vị trí đó.

Một câu lệnh có thể được gắn nhãn để làm đích `break label;` nếu nhãn bao quanh câu lệnh đó, nhưng **`continue label;` chỉ hợp lệ khi nhãn gắn với vòng lặp**.

### 6.2. Những lỗi điều khiển bị compiler chặn

Tệp sai thứ nhất:

~~~java
class BreakOutside {
    void bad() {
        break;
    }
}
~~~

`javac --release 17 BreakOutside.java` từ chối: `break outside switch or loop`.

Tệp sai thứ hai:

~~~java
class ContinueSwitch {
    static void bad(int n) {
        switch (n) {
            case 1: continue;
            default: break;
        }
    }
}
~~~

`javac --release 17 ContinueSwitch.java` từ chối: `continue outside of loop`. `switch` không phải iteration statement. Nếu `switch` nằm bên trong một vòng lặp, `continue` không nhãn có thể áp dụng cho vòng lặp đó.

Tệp sai thứ ba:

~~~java
class LabelContinueNonLoop {
    static void bad() {
        start: {
            continue start;
        }
    }
}
~~~

Trường hợp này bị từ chối bởi `not a loop label: start`: nhãn `start` gắn với một block, không gắn với vòng lặp. Thay `continue start;` bằng `break start;` là một cấu trúc hợp lệ để kết thúc block có nhãn phù hợp.

`break` hoặc `continue` không thể nhảy tùy ý vào một khối chưa bắt đầu; Java không hỗ trợ kiểu nhảy `goto` đến vị trí code tùy chọn.

## 7. try/catch/finally tác động đến luồng return

Một phương thức có thể `return` trong `try` hoặc `catch`, nhưng `finally` sẽ được thực thi khi điều khiển rời cấu trúc `try` trong các trường hợp bình thường theo ngữ nghĩa ngôn ngữ. Vì thế cần xem xét cả `finally` trước khi kết luận kết quả quan sát.

~~~java
static int safeParse(String text) {
    try {
        return Integer.parseInt(text);
    } catch (NumberFormatException ex) {
        return -1;
    } finally {
        System.out.println("cleanup");
    }
}
~~~

Nếu gọi `safeParse("12")`, khối `finally` in `cleanup` trước khi lời gọi trả 12 cho nơi gọi. Nếu gọi `safeParse("x")`, `catch` xử lý `NumberFormatException`, `finally` in `cleanup`, sau đó trả -1.

Cần phân biệt **thực thi `finally`** và **`finally` hoàn tất bình thường**. Nếu chính `finally` `return` hoặc `throw`, nó có thể thay thế nguyên nhân thoát trước đó:

~~~java
class FinallyReturn {
    static int f() {
        try {
            return 1;
        } finally {
            return 2;
        }
    }
}
~~~

Java 17 **biên dịch được** và lời gọi `f()` trả 2, nhưng cách viết `return` trong `finally` rất khó bảo trì, có thể che mất ngoại lệ hay kết quả của `try`. Thông thường để `finally` chỉ làm thao tác dọn dẹp, hoặc dùng **try-with-resources** khi quản lý `AutoCloseable`.

Với mã phức tạp hơn, `javac` cũng phải kiểm tra flow qua `catch` và `finally`; một câu lệnh sau `try` có thể unreachable nếu mọi đường ra đều hoàn tất đột ngột. Tuy nhiên, trong logic nghiệp vụ, nên tránh phụ thuộc vào các tổ hợp return/throw trong finally khó nhìn ra.

## 8. Kết hợp với definite assignment và phân tích ngữ nghĩa

**Reachability** trả lời câu hỏi một statement có thể được đi tới theo quy tắc ngôn ngữ không. **Definite assignment** kiểm tra một biến cục bộ đã được gán chắc chắn trước khi đọc chưa. Chúng có liên quan trong phân tích flow, nhưng không đồng nhất.

~~~java
static int maybeValue(boolean flag) {
    int n;
    if (flag) {
        n = 10;
    }
    // return n; // lỗi: variable n might not have been initialized
    return 0;
}
~~~

`return n;` sẽ reachable, nhưng biến `n` không được bảo đảm đã gán nếu `flag` là `false`. Muốn trả n, phải gán một giá trị ở cả hai nhánh, hoặc khởi tạo giá trị trước `if`.

~~~java
static int definite(boolean flag) {
    int n;
    if (flag) {
        n = 10;
    } else {
        n = 20;
    }
    return n;
}
~~~

Các đường đi đến `return n;` đều đã gán `n` nên đoạn hợp lệ.

Tương tự, phương thức có thể có tất cả biểu thức kiểu đúng, nhưng vẫn thiếu `return`; hoặc `return` đầy đủ nhưng không tìm thấy một biểu tượng/phương thức. `javac` xét nhiều quy tắc ngữ nghĩa khác nhau, và thông báo lỗi đầu tiên thường là điểm bắt đầu tốt nhất để điều tra.

## 9. Chương trình Java 17 hoàn chỉnh và stdout đã kiểm chứng

Tạo một tệp **`FlowDemo.java`** với toàn bộ mã sau (không có `package`). Đây là chương trình độc lập, bao gồm nhiều đường return, switch expression, break/continue, nhãn và finally.

~~~java
public final class FlowDemo {
    static String classify(int n) {
        if (n < 0) return "âm";
        if (n == 0) return "không";
        return "dương";
    }

    static int points(String grade) {
        return switch (grade) {
            case "A" -> 10;
            case "B" -> 8;
            default -> 0;
        };
    }

    static int firstOdd(int[] values) {
        for (int value : values) {
            if (value % 2 == 0) continue;
            return value;
        }
        return -1;
    }

    static int countPositive(int[][] matrix) {
        int count = 0;
        outer:
        for (int[] row : matrix) {
            for (int n : row) {
                if (n < 0) break outer;
                if (n == 0) continue;
                count++;
            }
        }
        return count;
    }

    static int safeParse(String text) {
        try {
            return Integer.parseInt(text);
        } catch (NumberFormatException ex) {
            return -1;
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        System.out.println(classify(-3));
        System.out.println(classify(0));
        System.out.println(classify(4));
        System.out.println(points("A"));
        System.out.println(firstOdd(new int[]{2, 4, 7, 8}));
        System.out.println(firstOdd(new int[]{2, 4}));
        System.out.println(
            countPositive(new int[][]{{1, 0, 2}, {3, -1, 9}, {10}})
        );
        System.out.println(safeParse("12"));
        System.out.println(safeParse("x"));
    }
}
~~~

Trong terminal đang ở thư mục chứa `FlowDemo.java`, chạy:

~~~sh
javac --release 17 -encoding UTF-8 FlowDemo.java
java FlowDemo
~~~

Stdout **chính xác** đã kiểm chứng:

~~~text
âm
không
dương
10
7
-1
3
cleanup
12
cleanup
-1
~~~

Vì sao có kết quả đó?

| Dòng | Lý giải luồng điều khiển |
|---|---|
| `âm`, `không`, `dương` | Ba giá trị đầu vào rẽ vào các guard `return` khác nhau trong `classify` |
| `10` | Switch expression chọn `case "A"`, trả giá trị cho `points` |
| `7` | `continue` bỏ qua 2, 4; gặp 7 thì `return` ngay |
| `-1` | Không có số lẻ trong mảng thứ hai; vòng kết thúc rồi chạy `return -1` |
| `3` | Đếm 1, 2, 3; gặp -1, `break outer` nên bỏ qua 9 và hàng cuối |
| `cleanup` rồi `12` | `try` chuẩn bị trả 12; `finally` chạy trước khi caller in kết quả |
| `cleanup` rồi `-1` | `catch` chuẩn bị trả -1 vì lỗi parse; `finally` chạy trước khi caller in |

Mã được kiểm tra biên dịch bằng `javac --release 17` và thực thi bằng JVM; các kết quả trên không phải dự đoán chưa thử. Tất cả kết quả `return` và câu lệnh chuyển hướng trong ví dụ đều có đích hợp lệ.

## 10. Những chương trình cố ý sai để luyện đọc lỗi javac

Lưu từng ví dụ lỗi vào **tệp riêng** tương ứng. Chúng được chủ đích trình bày để compiler từ chối, không được gộp vào chương trình `FlowDemo.java` nếu muốn ví dụ phần 9 vẫn chạy.

| Tệp | Tình huống sai | Chẩn đoán chính của javac Java 17 |
|---|---|---|
| `MissingReturn.java` | Phương thức `int` chỉ return khi `x > 0` | `missing return statement` |
| `WhileFalse.java` | Câu lệnh bên trong `while (false)` | `unreachable statement` |
| `BreakOutside.java` | `break;` nằm ngoài loop/switch | `break outside switch or loop` |
| `ContinueSwitch.java` | `continue;` trong switch không có vòng lặp bao ngoài | `continue outside of loop` |
| `SwitchIncompleteReturn.java` | Switch statement thiếu nhánh/return cho vài giá trị | `missing return statement` |
| `SwitchExpressionMissing.java` | Một block arm của switch expression không `yield` giá trị | `switch rule completes without providing a value` |
| `WrongReturnType.java` | Phương thức `int` trả về `String` | `incompatible types: String cannot be converted to int` |
| `LabelContinueNonLoop.java` | `continue label;` nhảy đến block có nhãn nhưng không phải loop | `not a loop label` |

Các kết quả biên dịch lỗi nêu trong bảng được kiểm tra với các lớp đúng nội dung như mô tả. Tùy bản JDK, vị trí caret, số lỗi và cách trình bày chi tiết có thể khác, nhưng nguyên nhân ngữ nghĩa tương ứng không đổi.

### 10.1. Phân biệt lỗi unreachable và lỗi missing return

Hai lỗi dễ bị lẫn:

~~~java
class UnreachableConcrete {
    void bad() {
        throw new IllegalStateException();
        System.out.println("unreachable");
    }
}
~~~

Lệnh `javac --release 17 UnreachableConcrete.java` báo `unreachable statement`: câu `println` không thể được đi tới theo cấu trúc block.

~~~java
class MissingReturn {
    static int sign(int x) {
        if (x > 0) return 1;
    }
}
~~~

Lệnh `javac --release 17 MissingReturn.java` báo `missing return statement`: không có câu lệnh unreachable; vấn đề là **có một đường đi qua cuối thân phương thức `int`**.

Điểm khác nhau:

- **Unreachable:** một vị trí code tồn tại nhưng không thể được đi tới theo quy tắc phân tích tĩnh.
- **Missing return:** thân một phương thức trả giá trị có thể kết thúc bình thường mà không `return` hoặc hoàn tất đột ngột theo cách hợp lệ.
- **Incorrect return type:** có `return` nhưng biểu thức không chuyển đổi hợp lệ sang kiểu khai báo.
- **Invalid control target:** có `break`/`continue` nhưng cấu trúc không cho phép đích chuyển tiếp.

Sửa lỗi bằng cách xác định **đồ thị đường đi** và trách nhiệm của từng nhánh, thay vì thêm `return null;`, `break;` hoặc ép kiểu ngẫu nhiên.

## 11. Một số tình huống dễ bỏ sót

### 11.1. Return trong constructor

Constructor không khai báo kiểu trả về và có thể dùng `return;` (không kèm biểu thức) để kết thúc sớm. Constructor **không thể `return value;`**. Khác với phương thức `int`, constructor được phép complete normally: khi đó đối tượng được khởi tạo xong theo quy tắc ngôn ngữ.

~~~java
class State {
    State(boolean skip) {
        if (skip) return;
        System.out.println("initialize");
    }
}
~~~

Đây là lớp minh họa hợp lệ; cần một phương thức main riêng để chạy. Thực tế nên cẩn thận với đường `return` sớm trong constructor vì có thể tạo trạng thái đối tượng chưa được thiết lập như dự kiến.

### 11.2. continue không giống break

Trong vòng lặp:

~~~java
for (int i = 0; i < 3; i++) {
    if (i == 1) continue;
    System.out.println(i);
}
~~~

Khi chạy trong phương thức hợp lệ, kết quả là `0` và `2` (mỗi giá trị trên một dòng). `continue` bỏ phần còn lại của lần lặp `i == 1`, rồi đến bước cập nhật của `for`. Nếu thay `continue` bằng `break`, vòng lặp kết thúc khi `i == 1`, nên chỉ in `0`.

### 11.3. Kiểu switch và nhánh điều khiển

Trong switch statement với nhãn colon, một `case` thiếu `break` có thể rơi xuống code của `case` sau nếu cấu trúc cho phép. Với switch expression, kết quả phải tuân thủ quy tắc của biểu thức; một arm block không được kết thúc bình thường mà không mang lại giá trị.

Java 17 còn kiểm tra trùng nhãn `case`, tính tương thích của nhãn với selector, khả năng truy cập, phạm vi khai báo và những ràng buộc khác. Một lỗi switch có thể là lỗi kiểu hoặc nhãn trước cả khi kiểm tra reachability/return.

### 11.4. Trình biên dịch không thay cho kiểm thử runtime

Một phương thức có đủ return vẫn có thể chạy sai, chẳng hạn vòng lặp xử lý thiếu trường hợp, trả giá trị sai hoặc ném ngoại lệ không mong muốn. Một vòng lặp được coi là reachable cũng không bảo đảm nó kết thúc. Cần kết hợp **kiểm tra tĩnh** của compiler với unit test của các nhánh điều kiện và test các ranh giới như mảng rỗng, đầu vào âm, `null`, lỗi parse.

## 12. Cách tự kiểm tra một phương thức trước khi biên dịch

Vẽ luồng điều khiển ở mức đủ để kiểm tra:

~~~text
                 [Entry]
                    |
               [Condition?]
                /        \
             true        false
              |            |
         [return 1]     [return 0]
              \            /
               [Caller resumes]
~~~

Đối với phương thức có kiểu trả về:

1. Đánh dấu mọi điểm **return/throw**.
2. Với mỗi `if`, xét đường true, false và vị trí sau `if`.
3. Với `switch`, xét tất cả giá trị selector không khớp case, `default`, fall-through hoặc switch expression.
4. Với vòng lặp, phân biệt điều kiện hằng `true`/`false`, khả năng `break` và việc vòng lặp có thể không chạy.
5. Với `try/catch/finally`, xét mọi đường thoát và liệu `finally` có đổi kết quả hoàn tất không.
6. Với `break`/`continue`, xác định rõ đích trong cấu trúc bao quanh; `continue label` phải nhắm vào vòng lặp.
7. Tìm các statement đứng sau một đoạn không thể hoàn tất bình thường; kiểm tra theo quy tắc reachability, tránh suy luận chỉ bằng trực giác runtime.
8. Đảm bảo không có đường đi **rơi qua cuối thân phương thức trả giá trị**; nếu có, sửa thiết kế nhánh hoặc trả về giá trị hợp lệ.

Nếu còn phân vân, tạo một lớp tối giản riêng và biên dịch bằng `javac --release 17 -encoding UTF-8`. Cách này giúp tách lỗi reachability, missing return và sai đích điều khiển khỏi những vấn đề khác của dự án lớn.

## 13. Bài tập có hướng dẫn đối chiếu

**Bài 1:** Đoán kết quả biên dịch của `if(false) { System.out.println("x"); }` và `while(false) { System.out.println("x"); }`. Sau đó chạy compiler. Giải thích vì sao JLS có quy tắc riêng cho hai cấu trúc.

**Bài 2:** Phương thức `int` có `if (true) return 1;` nhưng không có `return` nào khác sẽ được biên dịch hay không? Kiểm chứng; gợi ý: quy tắc `if-then` có thể complete normally không tương đương với tối ưu hóa của compiler.

**Bài 3:** Với một `while(true)`, thêm một `break` có thể đi tới theo quy tắc reachability. Chèn `return 5;` sau vòng và giải thích vì sao hợp lệ. Thử bỏ `break`, xem compiler báo điều gì nếu vẫn giữ `return 5;` phía sau.

**Bài 4:** Viết một phương thức `int score(String level)` dùng switch expression với `case "A"`, `case "B"` và `default`. Sau đó thử viết `default -> { int x = 0; }` không `yield`; quan sát lỗi.

**Bài 5:** Viết hai vòng lặp lồng nhau và thử `break;`, `break outer;`, `continue;`, `continue outer;`. Dự đoán lần lặp nào tiếp tục và câu lệnh nào còn reachable. Cuối cùng thử `continue` đến nhãn của một block không phải vòng lặp để xem lỗi compiler.

**Bài 6:** Viết một phương thức có `return` trong `try` và `finally` chỉ in log; đoán thứ tự đầu ra. Thử `return` trong `finally` ở chương trình nhỏ riêng, rồi giải thích vì sao cấu trúc ấy có thể làm mất thông tin lỗi/giá trị trả về.

Hãy phân biệt bốn lớp kết luận khi đọc một chương trình Java: **cú pháp đúng**, **kiểu biểu thức đúng**, **luồng điều khiển hợp lệ ở compile-time**, và **hành vi runtime đúng với yêu cầu**. `javac` kiểm tra nghiêm ngặt ba lớp đầu theo quy tắc ngôn ngữ; lớp cuối vẫn cần mô hình hóa, thử nghiệm và kiểm thử thực tế.