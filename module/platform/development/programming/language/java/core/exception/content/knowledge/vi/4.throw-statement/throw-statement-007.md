# Đường thực thi không thể tới sau `throw` trong Java

Câu lệnh `throw` **kết thúc đường thực thi bình thường tại vị trí nó được thực thi**. Quyền điều khiển chuyển sang cơ chế tìm và xử lý ngoại lệ: có thể vào một `catch` phù hợp, thực hiện `finally` hoặc truyền ngoại lệ ra phương thức gọi. Vì vậy, câu lệnh viết **ngay sau một `throw` vô điều kiện trong cùng khối** không có đường đi hợp lệ đến nó và sẽ bị trình biên dịch Java từ chối với lỗi dạng `unreachable statement`.

Tuy nhiên, cần phân biệt ba nhận định:

- **`throw` luôn hoàn tất đột ngột** (*always completes abruptly*), theo Java Language Specification (JLS) §14.18.
- **Một câu lệnh có thể tới được hay không** (*reachability*) là quy tắc phân tích tĩnh của trình biên dịch, theo JLS §14.22.
- **Một dòng có được thực thi trong một lần chạy cụ thể hay không** là quan sát động, không nhất thiết trùng hoàn toàn với quy tắc reachability.

Phạm vi bài này là tác động của `throw` đối với các câu lệnh kế tiếp, cách trình biên dịch xác định câu lệnh không thể tới và những nơi ngoại lệ được bắt để chương trình tiếp tục.

## 1. Vì sao `throw` chặn đường chạy phía sau?

Cú pháp:

```java
throw expression;
```

Biểu thức phải cho ra giá trị tham chiếu gán được cho `Throwable` (hoặc `null`, gây `NullPointerException` khi chạy). Khi biểu thức được đánh giá thành một đối tượng ngoại lệ, `throw` ném đối tượng đó và **hoàn tất đột ngột** với lý do `throw`. Nếu bản thân biểu thức đánh giá đã ném một ngoại lệ khác, `throw` cũng hoàn tất đột ngột theo lý do đó. Không có trường hợp câu lệnh `throw` hoàn tất bình thường để chuyển thẳng sang câu lệnh kế tiếp.

Ví dụ sau **cố ý không biên dịch**:

```java
class InvalidAfterThrow {
    static void fail() {
        throw new IllegalStateException("Dừng tại đây");
        // System.out.println("Không tới được"); // Nếu bỏ comment: lỗi biên dịch.
    }
}
```

Nếu bỏ dấu comment ở câu lệnh `System.out.println(...)`, `javac` từ chối câu lệnh đó vì **unreachable statement**. Bản thân phiên bản đang để comment biên dịch được; ví dụ nhằm minh họa điểm lỗi chứ không phải tạo đầu ra khi chạy.

Tại sao? Trong cùng khối `{ ... }`, câu lệnh kế tiếp chỉ *reachable* nếu câu lệnh trước **có thể hoàn tất bình thường** (*can complete normally*). `throw` không bao giờ có khả năng này, nên câu lệnh tiếp theo không thỏa điều kiện reachability.

```text
Khối phương thức
    |
    v
throw new IllegalStateException(...)
    |
    +-- hoàn tất đột ngột --> tìm catch / tháo stack / finally
    |
    X  Không có cạnh điều khiển bình thường đến dòng tiếp theo
       System.out.println(...)
```

Không thể “sửa” lỗi này bằng cách đặt thêm `return;` phía sau `throw`: chính `return` cũng không thể tới. Không thể yêu cầu trình biên dịch bỏ qua lỗi reachability chỉ bằng cách ghi chú rằng đó là mã dự phòng.

## 2. `Unreachable statement` là lỗi biên dịch, khác ngoại lệ lúc chạy

Java phân tích reachability khi **biên dịch** dựa trên cấu trúc các câu lệnh. Nó không cần chạy chương trình để xác định đường đi của một `throw` vô điều kiện. Chẳng hạn:

```java
class AnotherInvalidExample {
    static int parse() {
        throw new IllegalArgumentException("Bad input");
        // return 42; // Nếu mở comment sẽ là unreachable statement.
    }
}
```

Phương thức trả `int` không yêu cầu bổ sung `return` sau `throw`, vì phương thức có thể kết thúc bằng ngoại lệ thay vì trả một giá trị. Câu lệnh `throw` là con đường kết thúc hợp lệ. Cần đặt điều kiện để chỉ ném ở trường hợp lỗi, rồi trả giá trị ở trường hợp hợp lệ.

**Hai chẩn đoán không được nhầm nhau:**

| Hiện tượng | Ví dụ | Bản chất |
| --- | --- | --- |
| `unreachable statement` | Có câu lệnh trong cùng khối ngay sau `throw` vô điều kiện. | Lỗi reachability lúc biên dịch. |
| `missing return statement` | Phương thức `int` có đường đi rơi xuống cuối thân phương thức mà không `return` hay `throw`. | Kiểm tra mọi đường đi bắt buộc trả giá trị hoặc kết thúc đột ngột. |
| `unreported exception ... must be caught or declared to be thrown` | Ném checked exception nhưng không `catch` hoặc khai báo `throws` thích hợp. | Kiểm tra ngoại lệ checked, độc lập với reachability. |
| `NullPointerException` tại `throw null;` | Biểu thức `throw` được đánh giá thành `null` khi chạy. | Ngoại lệ runtime; `throw` vẫn hoàn tất đột ngột. |

Nội dung nguyên văn và vị trí lỗi trình biên dịch có thể thay đổi theo phiên bản JDK. Quan trọng là nguyên nhân và cách sửa.

Ví dụ về checked exception (đoạn sau **cố ý không hợp lệ**):

```java
import java.io.IOException;

class CheckedExceptionExample {
    static void load() {
        throw new IOException("Read failed"); // Phải bắt hoặc khai báo throws.
    }
}
```

Đoạn này không gặp lỗi “unreachable statement”, vì không có câu lệnh phía sau `throw`. Lỗi nằm ở hợp đồng checked exception. Có thể sửa khai báo thành `static void load() throws IOException` rồi để bên gọi chịu trách nhiệm bắt/khai báo; hoặc xử lý ngoại lệ tại `catch` có ngữ cảnh phù hợp.

## 3. `throw` có điều kiện: các nhánh hợp lệ vẫn được đi tiếp

Một nhánh `if` có thể ném, còn đường khác vẫn có khả năng chạy tới câu lệnh kế tiếp:

```java
static int requirePositive(int value) {
    if (value <= 0) {
        throw new IllegalArgumentException("value phải dương");
    }
    return value * 2;
}
```

Đây là phương thức minh họa nằm trong một lớp. Với `value = -1`, câu lệnh `throw` được chạy và `return` không chạy. Với `value = 5`, điều kiện sai, khối `if` được bỏ qua và phương thức trả `10`. Vì có đường đi hợp lệ, `return value * 2;` là **reachable**.

Khi cả hai nhánh cùng không thể hoàn tất bình thường, câu lệnh ngay sau `if-else` có thể không reachable. Ví dụ **cố ý không biên dịch nếu mở comment**:

```java
class InvalidBothBranches {
    static void fail(boolean mode) {
        if (mode) {
            throw new IllegalArgumentException("A");
        } else {
            throw new IllegalStateException("B");
        }
        // System.out.println("after"); // Nếu mở comment: unreachable statement.
    }
}
```

Mỗi nhánh đều ném ngoại lệ, nên không có đường hoàn tất bình thường qua `if-else`. Khi một nhánh trả giá trị hoặc dùng `throw`, cần xem **toàn bộ cấu trúc `if`**, không chỉ câu lệnh cuối trong một nhánh.

Một mẫu thực tế thường gặp là *guard clause*:

```java
static String normalizeName(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("Tên không được để trống");
    }
    return name.trim();
}
```

Cách này đưa đường lỗi ra khỏi luồng chính, nên phần xử lý trường hợp hợp lệ có thể đọc tuần tự. Đặt điều kiện kiểm tra **trước** khi dùng giá trị để tránh phát sinh ngoại lệ thiếu ngữ cảnh (ví dụ `NullPointerException`). Đoạn này là phương thức trong một lớp, không có `main` để chạy độc lập.

## 4. Ví dụ Java 17+ chạy được: guard clause, `throw` và `catch`

Lưu tệp `ThrowReachabilityDemo.java`:

```java
public class ThrowReachabilityDemo {
    static int parsePositive(String input) {
        final int value;

        try {
            value = Integer.parseInt(input);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Not a number: " + input, ex);
        }

        if (value <= 0) {
            throw new IllegalArgumentException("Must be positive");
        }
        return value;
    }

    static void runTask(int kind) {
        try {
            if (kind == 0) {
                throw new IllegalStateException("stop");
            }
            System.out.println("try-ok");
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        } finally {
            System.out.println("finally");
        }
        System.out.println("after-try");
    }

    public static void main(String[] args) {
        System.out.println("positive=" + parsePositive("7"));

        try {
            parsePositive("-2");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=" + ex.getMessage());
        }

        runTask(0);
        runTask(1);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 ThrowReachabilityDemo.java
java ThrowReachabilityDemo
```

Kết quả:

```text
positive=7
invalid=Must be positive
caught=stop
finally
after-try
try-ok
finally
after-try
```

**Phân tích:**

1. `parsePositive("7")` không ném vì điều kiện `value <= 0` sai; kết quả `7` được trả bình thường.
2. `parsePositive("-2")` ném `IllegalArgumentException`. Câu lệnh `return value;` **vẫn reachable xét về mặt biên dịch**, nhưng không chạy trong lần gọi này. `catch` bên ngoài xử lý ngoại lệ.
3. `runTask(0)` ném trong `try` và chuyển đến `catch`. Phần `try-ok` bị bỏ qua, `finally` được chạy, rồi `after-try` chạy vì cấu trúc `try-catch-finally` đã hoàn tất bình thường.
4. `runTask(1)` không ném: `try-ok` được in, `catch` được bỏ qua, `finally` vẫn chạy và sau đó `after-try` chạy.

Lỗi **unreachable statement** là khái niệm tĩnh; kết quả của một lần gọi với tham số cụ thể không tự biến một câu lệnh hợp lệ thành lỗi biên dịch.

## 5. Vì sao sau `try-catch` vẫn có thể tới được?

Ví dụ:

```java
try {
    throw new IllegalArgumentException("bad");
} catch (IllegalArgumentException ex) {
    System.out.println("handled");
}
System.out.println("after");
```

Đây là đoạn minh họa đặt trong thân phương thức. Trình tự thực thi bình thường là:

```text
throw "bad"
    |
    v
catch (IllegalArgumentException)
    |  in "handled"
    v
sau try-catch
       in "after"
```

Dòng `after` nằm **ngoài** khối `try` chứa `throw`. `catch` bắt và xử lý lý do hoàn tất đột ngột; vì `catch` hoàn tất bình thường, cả cấu trúc `try-catch` có thể hoàn tất bình thường, khiến câu lệnh kế tiếp hợp lệ.

So sánh mã sau (có lỗi nếu mở comment):

```java
try {
    throw new IllegalArgumentException("bad");
    // System.out.println("in try"); // unreachable statement nếu mở comment
} catch (IllegalArgumentException ex) {
    System.out.println("handled");
}
System.out.println("after"); // reachable
```

Phần `catch` không làm cho dòng ở **trong cùng khối `try`, ngay sau `throw`** trở nên reachable. Nó chỉ tạo một đường tiếp tục hợp lệ sau khi khối `try` đã hoàn tất đột ngột.

Đồng thời, `catch` phải tương thích kiểu ngoại lệ. Nếu chỉ có `catch (NumberFormatException ex)`, nó không bắt được `IllegalArgumentException` thông thường do lập trình viên ném (mặc dù `NumberFormatException` là lớp con của `IllegalArgumentException`). Trong ví dụ ném `new IllegalArgumentException(...)`, loại đối tượng là `IllegalArgumentException`, nên nhánh chỉ bắt `NumberFormatException` không phù hợp. Đường ngoại lệ tiếp tục lan ra.

## 6. `finally` được chạy nhưng không mở lại đường phía sau `throw`

Khi chuyển quyền điều khiển từ `try` vì `throw`, Java thực hiện `finally` tương ứng trong quá trình chuyển quyền, theo quy tắc của `try-finally` và `try-catch-finally`. Nhưng `finally` **không quay ngược vào phần phía sau `throw` trong khối `try`**.

Chương trình chạy được, lưu thành `FinallyThrowDemo.java`:

```java
public class FinallyThrowDemo {
    static void process() {
        try {
            System.out.println("before throw");
            throw new IllegalStateException("failed");
        } finally {
            System.out.println("cleanup");
        }
    }

    public static void main(String[] args) {
        try {
            process();
        } catch (IllegalStateException ex) {
            System.out.println("caught=" + ex.getMessage());
        }
        System.out.println("after call");
    }
}
```

```bash
javac -encoding UTF-8 FinallyThrowDemo.java
java FinallyThrowDemo
```

Kết quả:

```text
before throw
cleanup
caught=failed
after call
```

Điểm cần ghi nhớ: `process()` không hoàn tất bình thường vì ngoại lệ thoát ra ngoài; nhưng lời gọi nằm trong `try-catch` của `main`, và `main` có thể tiếp tục tại `after call` sau khi bắt lỗi. Không có lý do nào cho phép thêm một câu lệnh bình thường ngay sau `throw` trong cùng khối `try`.

**Cảnh báo về `finally`:** Nếu `finally` tự thực thi `throw` hoặc `return`, lý do hoàn tất mới của nó có thể **thay thế** ngoại lệ đang được truyền. Tránh `return` trong `finally` và đừng làm mất ngoại lệ gốc khi dọn dẹp. Với tài nguyên `AutoCloseable`, `try-with-resources` được thiết kế để giữ các lỗi phát sinh khi đóng tài nguyên trong danh sách `suppressed` ở những tình huống thích hợp.

## 7. Sự khác nhau giữa `throw` tường minh và một lời gọi luôn ném

Xét hai phiên bản:

```java
static void alwaysFails() {
    throw new IllegalStateException("failed");
}

static void caller() {
    alwaysFails();
    System.out.println("after call"); // Java vẫn xem là reachable.
}
```

Cả hai phương thức là đoạn mã đặt trong một lớp. Dù `alwaysFails()` không bao giờ trả bình thường khi được thực thi đúng như nội dung đã viết, trình biên dịch Java **không suy diễn xuyên phương thức** rằng lời gọi `alwaysFails()` chắc chắn sẽ ném. Một câu lệnh biểu thức gọi phương thức thông thường được xem là có thể hoàn tất bình thường theo quy tắc reachability của JLS §14.22. Vì thế dòng `after call` được chấp nhận lúc biên dịch, dù không được chạy trong kịch bản này.

So sánh:

```java
static void directThrow() {
    throw new IllegalStateException("failed");
    // System.out.println("after throw"); // Nếu mở comment, không biên dịch.
}
```

Ở `directThrow()`, trình biên dịch nhìn thấy trực tiếp `throw` ngay trước câu lệnh kế tiếp. Điều này chứng minh **“không thể chạy theo thực tế” khác với “unreachable theo đặc tả”**.

Tương tự, trình biên dịch không phân tích sâu mọi giá trị của biến để chứng minh đường đi có/không có thể xảy ra. Hãy sử dụng cấu trúc điều khiển rõ ràng, thay vì dựa vào giả định rằng trình biên dịch sẽ suy ra ý nghĩa nghiệp vụ của phương thức tên `alwaysFails` hoặc một hằng cục bộ.

## 8. Ngoại lệ đặc biệt: `if (true)` và quy tắc reachability của Java

Quy tắc `if` có một trường hợp đặc biệt theo JLS §14.22. Dù điều kiện là hằng `true` và nhánh chứa `throw` vô điều kiện, câu lệnh **sau toàn bộ `if` không có `else`** vẫn có thể được coi là reachable. Ví dụ này biên dịch được:

```java
class IfReachabilityExample {
    static void example() {
        if (true) {
            throw new IllegalStateException("always");
        }
        System.out.println("reachable to compiler");
    }
}
```

Ở runtime, nếu gọi `example()` thì ngoại lệ luôn xảy ra, nên dòng in không chạy. Nhưng JLS cố ý có quy tắc đặc biệt cho `if` để hỗ trợ các kiểu viết mã mang tính “biên dịch có điều kiện”. Vì vậy, **đừng kết luận rằng `javac` phải báo unreachable cho mọi mã mà con người chứng minh được không chạy**.

Trái lại, bên **trong cùng khối của nhánh `if`**, đặt câu lệnh sau `throw` vô điều kiện vẫn là unreachable:

```java
class IfInvalidExample {
    static void example() {
        if (true) {
            throw new IllegalStateException("always");
            // System.out.println("never"); // Nếu mở comment: unreachable.
        }
    }
}
```

Còn `if-else` là một cấu trúc khác: để toàn bộ `if-else` có thể hoàn tất bình thường thì ít nhất một nhánh phải có thể hoàn tất bình thường. Nếu cả hai nhánh đều chứa `throw` vô điều kiện, mã sau cấu trúc sẽ bị từ chối là unreachable.

**Lưu ý:** quy tắc đặc biệt này không cho phép đặt một câu lệnh trực tiếp sau `throw` trong cùng khối; nó liên quan đến khả năng hoàn tất bình thường được mô hình hóa cho **toàn bộ câu lệnh `if`**.

## 9. `switch`, `case` và các nhánh sau `throw`

Một `case` khác không nhất thiết bị chặn bởi câu lệnh `throw` ở `case` trước. `switch` có nhiều điểm vào theo nhãn `case`.

Ví dụ hợp lệ:

```java
static void choose(int code) {
    switch (code) {
        case 1:
            throw new IllegalArgumentException("bad code");
        case 2:
            System.out.println("code=2");
            break;
        default:
            System.out.println("other");
    }
    System.out.println("switch done");
}
```

Đây là phương thức minh họa, không phải tệp độc lập. Với `code = 2`, chương trình vào `case 2` trực tiếp; không cần đi qua `case 1` và lệnh `throw` ở đó. Với `code = 1`, ngoại lệ được ném. Với giá trị khác `1` và `2`, `default` chạy. Câu lệnh sau `switch` là reachable vì có những đường hoàn tất bình thường.

Trong `switch expression`, nhánh `throw` cũng có thể hợp lệ vì nó biểu diễn một trường hợp lỗi trong khi các nhánh khác trả về giá trị:

```java
static int points(int level) {
    return switch (level) {
        case 1 -> 10;
        case 2 -> 20;
        default -> throw new IllegalArgumentException("unknown level");
    };
}
```

Nhánh `default` ném ngoại lệ, nhưng hai nhánh khác giúp biểu thức `switch` cung cấp kết quả bình thường. Không cần viết một biểu thức “giá trị giả” phía sau `throw`. Đoạn mã dùng cú pháp `switch expression` ổn định trong Java 17.

## 10. Vòng lặp và câu lệnh không thể tới: liên hệ nhưng không đồng nhất

JLS còn có quy tắc về vòng lặp không thể hoàn tất bình thường, ví dụ `while (true)` không có `break` phù hợp:

```java
class InvalidInfiniteLoop {
    static void loop() {
        while (true) {
            System.out.println("running");
        }
        // System.out.println("after loop"); // Nếu mở comment: unreachable.
    }
}
```

Đây là ví dụ về reachability **không cần `throw`**. Nó cho thấy lỗi unreachable đến từ mô hình luồng điều khiển của ngôn ngữ nói chung. Nếu vòng lặp có `break` reachable thoát khỏi nó, câu lệnh sau vòng lặp có thể reachable.

Điểm khác biệt đáng chú ý:

```java
static void conditionalLoop(boolean keepRunning) {
    while (keepRunning) {
        if (Thread.currentThread().isInterrupted()) {
            break;
        }
    }
    System.out.println("after loop");
}
```

Phương thức này chỉ minh họa đường điều khiển, **không nên dùng làm vòng chờ quay liên tục trong chương trình thực tế**. Khi điều kiện `keepRunning` là biến (không phải hằng `true`), về mặt reachability có thể thoát vòng lặp để tới `after loop`. Quy tắc reachability không dự đoán vòng lặp chắc chắn chấm dứt trong một lần chạy cụ thể.

Khi so sánh với `throw`: một câu lệnh `throw` vô điều kiện không thể hoàn tất bình thường trong mọi trường hợp, còn cấu trúc vòng lặp hoặc `if` phải được xét theo quy tắc riêng của chúng.

## 11. Lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa phù hợp |
| --- | --- | --- |
| Đặt `System.out.println` hoặc `return` sau `throw` vô điều kiện trong cùng khối. | Lệnh trước không thể hoàn tất bình thường nên lệnh tiếp theo unreachable. | Bỏ dòng vô hiệu, hoặc chuyển hành động cần chạy lên **trước `throw`**. |
| Viết `throw ...; return defaultValue;` để bảo đảm có giá trị trả về. | `throw` đã là đường kết thúc phương thức; `return` phía sau unreachable. | Dùng `throw` cho đường lỗi và `return` riêng cho đường hợp lệ. |
| Cho rằng `catch` sẽ chạy rồi quay lại dòng ngay sau `throw`. | `catch` xử lý và tiếp tục sau cấu trúc `try` thích hợp, không quay lại điểm ném. | Chuyển mã cần chạy sau xử lý sang **sau `try-catch`**. |
| Nhầm checked exception error với `unreachable statement`. | Đây là hai bước kiểm tra độc lập. | Với checked exception, `catch` hoặc khai báo `throws` đúng kiểu. |
| Nhầm lời gọi “luôn ném” với `throw` trực tiếp. | Trình biên dịch không suy diễn xuyên phương thức theo cách đó. | Diễn đạt kiểm tra và nhánh lỗi tại vị trí hợp lý; không trông chờ `javac` phân tích toàn chương trình. |
| Diễn giải `if (true) { throw ... }` như mã buộc phải gây unreachable ở ngoài `if`. | `if` có quy tắc reachability đặc biệt. | Áp dụng đúng quy tắc JLS cho cấu trúc bao quanh. |
| Đặt `return` trong `finally` để “dọn dẹp”. | `return` của `finally` có thể che khuất ngoại lệ ban đầu. | Chỉ đặt công việc dọn dẹp cần thiết trong `finally`; tránh thay thế lý do lỗi đang được truyền. |

Một thay đổi nhỏ thường rõ ràng hơn:

**Trước (không hợp lệ nếu bỏ comment):**

```java
static String requireName(String name) {
    throw new IllegalArgumentException("invalid");
    // return name.trim(); // unreachable
}
```

**Sau (hợp lệ, có hai đường đi):**

```java
static String requireName(String name) {
    if (name == null || name.isBlank()) {
        throw new IllegalArgumentException("invalid");
    }
    return name.trim();
}
```

Nhờ có điều kiện, đoạn `return name.trim();` chạy được khi đầu vào hợp lệ; nếu đầu vào sai, phương thức ném ngoại lệ và không cố trả giá trị.

## 12. Cách tự kiểm tra luồng điều khiển

Đối với một đoạn mã có `throw`, hãy lần theo thứ tự:

1. **Xác định cấp đang xét:** ngay trong một khối, toàn bộ `if-else`, một `case` của `switch`, một vòng lặp, `try-catch-finally` hay lời gọi phương thức.
2. **Hỏi câu lệnh trước có thể hoàn tất bình thường không:** nếu là `throw` trực tiếp thì câu trả lời luôn là **không**.
3. **Xem cấu trúc bao ngoài có xử lý lý do đột ngột không:** nhánh `catch` phù hợp, `finally`, `switch` và các đường điều khiển riêng không phải cùng một kiểu xử lý.
4. **Áp dụng reachability theo JLS:** không suy ra lỗi biên dịch chỉ từ việc một dòng sẽ không được chạy với đầu vào hiện tại.
5. **Kiểm tra ngoại lệ checked riêng:** sau khi kết luận về luồng điều khiển, vẫn phải xem phương thức cần `throws` hay `catch`.

Thử dự đoán kết quả của đoạn mã sau khi đặt trong một phương thức:

```java
int value = 3;
try {
    if (value > 0) {
        throw new IllegalArgumentException("positive");
    }
    System.out.println("inside try");
} catch (IllegalArgumentException ex) {
    System.out.println("handled: " + ex.getMessage());
}
System.out.println("outside");
```

Kết quả:

```text
handled: positive
outside
```

Dòng `inside try` **reachable theo phân tích tĩnh** vì điều kiện phụ thuộc vào biểu thức sử dụng biến, nhưng không chạy trong lần thực thi này. Ngoại lệ được `catch` xử lý, nên dòng `outside` chạy. Nếu đem dòng `inside try` vào ngay sau `throw` **trong cùng khối con của nhánh `if`**, câu lệnh mới sẽ là unreachable khi biên dịch.

## 13. Tự kiểm tra nhanh

**Câu 1.** Sau `throw new RuntimeException();` vô điều kiện, có thể đặt `return 0;` trong cùng khối để tránh lỗi thiếu `return` không?  
**Không.** `throw` đã kết thúc đường chạy và `return` phía sau là unreachable.

**Câu 2.** Câu lệnh ở ngoài `try-catch` có thể chạy sau khi `throw` bên trong `try` không?  
**Có.** Nếu `catch` phù hợp xử lý lỗi và cấu trúc `try-catch` hoàn tất bình thường, luồng tiếp tục ở câu lệnh sau nó.

**Câu 3.** Nếu `throw` nằm trong một nhánh `if`, câu lệnh sau `if` luôn unreachable?  
**Không.** Phải xét cấu trúc `if` và quy tắc reachability đặc biệt của nó.

**Câu 4.** Có thể đặt `case 2:` sau `case 1: throw ...;` trong `switch` statement?  
**Có.** `case 2` là một điểm vào khác của `switch` và có thể reachable.

**Câu 5.** Nếu gọi phương thức mà thân chỉ có `throw`, trình biên dịch có bắt lỗi unreachable cho dòng phía sau lời gọi không?  
**Không chỉ vì thế.** Java không phân tích xuyên phương thức để suy ra lời gọi luôn thất bại.

**Câu 6.** `throw null;` có được xem là hoàn tất bình thường không?  
**Không.** Khi chạy, Java tạo và ném `NullPointerException`, nên câu lệnh vẫn hoàn tất đột ngột.

## Tham khảo đặc tả

- [Java Language Specification 21 — §14.18 The `throw` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.18).
- [Java Language Specification 21 — §14.22 Unreachable Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.22).
- [Java Language Specification 21 — §14.20 `try` Statement](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.20).
- [Java Language Specification 21 — §11.2 Compile-Time Checking of Exceptions](https://docs.oracle.com/javase/specs/jls/se21/html/jls-11.html#jls-11.2).

**Ghi nhớ:** `throw` luôn hoàn tất đột ngột. Một lệnh đặt trực tiếp sau `throw` vô điều kiện trong cùng khối là unreachable, nhưng một `catch` phù hợp hoặc một nhánh điều khiển khác có thể tạo đường tiếp tục hợp lệ **ở cấp cấu trúc bao ngoài**. Phải đánh giá reachability theo quy tắc Java, không chỉ theo dự đoán của một lần chạy.
