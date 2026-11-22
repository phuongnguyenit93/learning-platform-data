# Pattern matching cho `switch` trong Java 21

**Pattern matching for switch** là tính năng chuẩn từ **Java 21 (JEP 441)**: thay vì chỉ so sánh `case` với hằng số, Java có thể kiểm tra **kiểu thực tế** của đối tượng, ràng buộc đối tượng với **biến mẫu** và dùng điều kiện bổ sung `when`.

~~~java
Object value = "Java";

String result = switch (value) {
    case String s -> "Chuỗi: " + s.toUpperCase();
    case Integer n -> "Số: " + n;
    case null -> "Thiếu dữ liệu";
    default -> "Kiểu khác";
};
~~~

Nếu `value` là `"Java"`, kết quả là `"Chuỗi: JAVA"`. Khi nhãn `case String s` khớp, `s` có kiểu tĩnh `String`, nên không cần viết `(String) value`. **Mẫu `case String s` không đồng nghĩa `case "String"`**: một bên kiểm tra kiểu, một bên là nhãn hằng chuỗi.

**Lưu ý phiên bản:** `instanceof String s` đã là tính năng chuẩn từ Java 16 và dùng được ở JDK 17. Nhưng **pattern matching trong `switch` là tính năng chuẩn từ JDK 21**. Ví dụ `case String s ->` dưới đây **không biên dịch với `javac` JDK 17 tiêu chuẩn**. Mục 3 có cách viết tương đương chạy bằng JDK 17, không cần preview.

## 1. Kiểu mẫu, `when`, `null` và `default`

Ví dụ:

~~~java
return switch (value) {
    case null -> "missing";
    case String s when s.isBlank() -> "blank";
    case String s -> "text:" + s;
    case Integer n when n >= 0 -> "nonnegative:" + n;
    case Integer n -> "negative:" + n;
    default -> "other";
};
~~~

Quy tắc:

- `case String s`: khớp khi đối tượng có kiểu `String` tương thích; ràng buộc nó với `s`, chỉ có hiệu lực trong nhánh tương ứng.
- `case String s when s.isBlank()`: trước tiên phải khớp kiểu `String`, sau đó kiểm tra thêm điều kiện `when`. Nếu guard false, Java tiếp tục xét nhãn phía sau.
- `case null`: **xử lý selector null**. Đây là điểm khác đáng chú ý so với switch truyền thống Java 17.
- `default`: xử lý trường hợp không nhãn nào khớp. **`default` riêng lẻ không bắt `null`**; nếu thiếu `case null`, selector null thông thường ném `NullPointerException`.
- `case ... ->`: thực thi đúng nhánh đã chọn, **không fall-through** xuống nhãn sau.

| Selector | Nhãn được chọn trong ví dụ trên | Kết quả |
| --- | --- | --- |
| `null` | `case null` | `missing` |
| `"   "` | `String s when s.isBlank()` | `blank` |
| `"Java"` | `String s` | `text:Java` |
| `12` (Integer) | `Integer n when n >= 0` | `nonnegative:12` |
| `-2` (Integer) | `Integer n` | `negative:-2` |
| `2.5` (Double) | `default` | `other` |

### Thứ tự nhãn và dominance

Nếu `case String s` **không có guard** xuất hiện trước `case String s when s.isBlank()`, nhãn thứ hai sẽ bị bao phủ bởi nhãn thứ nhất và gây lỗi **dominated case**. Do đó đặt mẫu **hẹp/có điều kiện** trước mẫu **rộng/không có điều kiện**.

Không dùng `when` sau một nhãn hằng như thể nó là phép `if` tổng quát; cú pháp guarded pattern được thiết kế để đi cùng **pattern label**.

## 2. Ví dụ hoàn chỉnh chạy với JDK 21

Tạo file UTF-8 **`PatternSwitch21Demo.java`**:

~~~java
import java.util.Locale;

public class PatternSwitch21Demo {
    sealed interface Action permits Start, Stop {}
    record Start(String task) implements Action {}
    record Stop() implements Action {}

    static String describe(Object value) {
        return switch (value) {
            case null -> "missing";
            case String s when s.isBlank() -> "blank";
            case String s -> "text:" + s.toUpperCase(Locale.ROOT);
            case Integer n when n >= 0 -> "nonnegative:" + n;
            case Integer n -> "negative:" + n;
            case Start s -> "start:" + s.task();
            case Stop s -> "stop";
            default -> "other";
        };
    }

    static String action(Action action) {
        return switch (action) {
            case Start s -> "start:" + s.task();
            case Stop s -> "stop";
        };
    }

    public static void main(String[] args) {
        Object[] inputs = {
            null, "   ", "java", 12, -2,
            new Start("build"), new Stop(), 2.5
        };
        for (Object input : inputs) {
            System.out.println(describe(input));
        }
        System.out.println("sealed=" + action(new Start("deploy")));
    }
}
~~~

Dùng **JDK 21 trở lên** trong thư mục chứa file (PowerShell hoặc Bash):

~~~bash
java -version
javac -version
javac -encoding UTF-8 PatternSwitch21Demo.java
java PatternSwitch21Demo
~~~

**Exact expected stdout** của riêng `java PatternSwitch21Demo`:

~~~text
missing
blank
text:JAVA
nonnegative:12
negative:-2
start:build
stop
other
sealed=start:deploy
~~~

Không cần `--enable-preview` trên JDK 21. Đầu ra `java -version` và `javac -version` phụ thuộc bản JDK được cài, nên không tính vào stdout cố định.

### Exhaustiveness với `sealed`

`Action` là một **sealed interface** chỉ cho phép `Start` và `Stop` triển khai trực tiếp. Compiler biết tập subtype được phép, vì vậy switch expression sau có thể **không cần `default`**:

~~~java
static String action(Action action) {
    return switch (action) {
        case Start s -> "start:" + s.task();
        case Stop s -> "stop";
    };
}
~~~

Biểu thức `switch` phải **bao phủ đầy đủ** (*exhaustive*) những giá trị thuộc kiểu selector theo quy tắc biên dịch; nếu có subtype mới được phép mà không cập nhật các nhánh, compiler có thể yêu cầu sửa. `switch` statement với mẫu cũng có các quy tắc bao phủ/nhãn phù hợp, nhưng không nên nhầm với switch statement truyền thống chỉ dùng hằng.

**Trường hợp null:** liệt kê đủ subtype `Start` và `Stop` không có nghĩa là đã xử lý null. Nếu `action == null`, switch này ném `NullPointerException` khi chạy.

## 3. Phương án tương thích Java 17: `instanceof` type pattern

Nếu chỉ có JDK 17, dùng các chuỗi `if` với `instanceof Type name` và guard. Cách này thể hiện cùng logic, chỉ không dùng pattern-switch Java 21.

Tạo file UTF-8 **`PatternSwitch17Compat.java`**:

~~~java
import java.util.Locale;

public class PatternSwitch17Compat {
    sealed interface Action permits Start, Stop {}
    record Start(String task) implements Action {}
    record Stop() implements Action {}

    static String describe(Object value) {
        if (value == null) {
            return "missing";
        }
        if (value instanceof String s) {
            if (s.isBlank()) {
                return "blank";
            }
            return "text:" + s.toUpperCase(Locale.ROOT);
        }
        if (value instanceof Integer n) {
            return n >= 0 ? "nonnegative:" + n : "negative:" + n;
        }
        if (value instanceof Start s) {
            return "start:" + s.task();
        }
        if (value instanceof Stop) {
            return "stop";
        }
        return "other";
    }

    static String action(Action action) {
        if (action instanceof Start s) {
            return "start:" + s.task();
        }
        if (action instanceof Stop) {
            return "stop";
        }
        throw new IllegalArgumentException("unsupported action");
    }

    public static void main(String[] args) {
        Object[] inputs = {
            null, "   ", "java", 12, -2,
            new Start("build"), new Stop(), 2.5
        };
        for (Object input : inputs) {
            System.out.println(describe(input));
        }
        System.out.println("sealed=" + action(new Start("deploy")));
    }
}
~~~

Chạy với **JDK 17 trở lên**:

~~~bash
javac -encoding UTF-8 PatternSwitch17Compat.java
java PatternSwitch17Compat
~~~

**Exact expected stdout** của `java PatternSwitch17Compat`:

~~~text
missing
blank
text:JAVA
nonnegative:12
negative:-2
start:build
stop
other
sealed=start:deploy
~~~

Hai chương trình cho cùng đầu ra minh họa. Tuy nhiên, cách viết Java 17 dùng các kiểm tra `instanceof` tuần tự nên **không có cùng kiểm tra exhaustiveness của switch expression trên sealed type**: phương thức `action` ở bản này sử dụng một `throw` dự phòng.

## 4. Pattern switch, `switch expression` và `yield`

Pattern matching có thể xuất hiện trong cả switch statement lẫn switch expression. Trong chương trình JDK 21, `describe` dùng **switch expression** trả về `String` trực tiếp từ từng nhánh.

Nếu một nhánh cần nhiều câu lệnh, dùng khối và `yield` để tạo giá trị:

~~~java
String result = switch (value) {
    case String s -> {
        String cleaned = s.trim();
        yield "length:" + cleaned.length();
    }
    case null -> "missing";
    default -> "other";
};
~~~

`yield` trả giá trị **từ switch expression**, không thoát toàn bộ phương thức như `return`. Với `case ... ->` đơn, chỉ cần viết biểu thức kết quả, không phải `yield`.

**Kiểu kết quả** được xác định khi biên dịch từ các nhánh/ngữ cảnh đích; không tự thay đổi kiểu ở runtime tùy vào pattern nào khớp. Biến mẫu `s` có kiểu tĩnh `String`, nhưng biến `value` bên ngoài vẫn có kiểu tĩnh `Object`.

## 5. Giới hạn quan trọng và lỗi thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| “Java 17 hỗ trợ `case String s ->` như Java 21.” | Java 17 chỉ có pattern-switch ở dạng preview, không phải cú pháp chuẩn không bật preview |
| “`case String s` tạo đối tượng String mới.” | Chỉ ràng buộc tham chiếu khi kiểu khớp |
| “`case String s` và `case "String"` giống nhau.” | Một bên là **type pattern**, một bên là hằng chuỗi |
| “`case String s` nên đặt trước `case String s when ...`.” | Mẫu rộng có thể thống trị mẫu hẹp và gây lỗi biên dịch |
| “`default` tự xử lý `null`.” | Cần `case null`, hoặc null có thể gây NPE |
| “`when` chạy trước khi kiểm tra kiểu.” | Guard chỉ được xét sau khi pattern khớp |
| “Dạng `case ->` rơi tiếp xuống nhánh sau.” | Không có fall-through |
| “Khai báo đủ subtype sealed cũng tự bắt null.” | Null phải được xử lý riêng nếu cần |
| “`case List<String> list` luôn kiểm tra được generic argument.” | Type erasure hạn chế kiểm tra kiểu generic tham số hóa; thường dùng `List<?>` rồi xác thực phần tử |

Trong Java 21, record patterns cũng được chuẩn hóa và có thể phối hợp với pattern-switch, nhưng đó là kỹ thuật **phân rã cấu trúc record**, khác với type pattern cơ bản của bài này. Không cần dùng record pattern để thực hiện ví dụ trên.

## 6. Bài tập tự kiểm tra

1. `switch(value) { case String s -> ...; default -> ...; }` khi `value` là `"abc"` sẽ chạy nhánh nào?  
   *Đáp án:* `String s`.
2. Nếu `value == null` và không có `case null`, `default` có chạy không?  
   *Đáp án:* Không; thường ném `NullPointerException`.
3. Có thể đặt `case String s when s.isBlank()` sau `case String s` không?  
   *Đáp án:* Không; mẫu trước bao phủ mẫu sau và gây dominated-case compile error.
4. `when` được đánh giá ở bước nào?  
   *Đáp án:* Sau khi kiểu pattern đã khớp, trước khi chọn nhánh đó.
5. Java 17 chuẩn có thể dùng cú pháp `instanceof String s` không?  
   *Đáp án:* Có, từ Java 16.
6. Vì sao `switch(action)` trên `sealed Action` có thể không cần `default`?  
   *Đáp án:* Compiler biết toàn bộ subtype được phép và các pattern đã bao phủ chúng.
7. Dùng gì để trả giá trị từ một khối trong switch expression?  
   *Đáp án:* `yield`.

## Checklist

- [ ] Phân biệt **`instanceof` type pattern chuẩn Java 17** và **pattern matching for switch chuẩn Java 21**.
- [ ] Hiểu `case Type variable` vừa kiểm tra kiểu vừa ràng buộc biến đúng kiểu.
- [ ] Dùng `when` cho điều kiện bổ sung và đặt mẫu hẹp trước mẫu rộng.
- [ ] Xử lý `null` tường minh bằng `case null` khi cần; không nhầm với `default`.
- [ ] Dùng `->` để tránh fall-through, `yield` khi nhánh switch expression là một khối.
- [ ] Nắm quy tắc exhaustiveness, đặc biệt với sealed hierarchy.
- [ ] Biết viết phương án Java 17 bằng `if` và `instanceof` nếu môi trường chưa nâng lên JDK 21.

**Kết luận:** Java 21 đưa kiểm tra kiểu trực tiếp vào `switch`, giúp chọn nhánh theo loại đối tượng, kết hợp guard `when`, xử lý `null` và kiểm tra độ bao phủ. Khi dự án vẫn dùng Java 17, hãy dùng `instanceof` type pattern với `if` để đạt hành vi tương đương mà không phụ thuộc preview.
