# Switch expression trả về một giá trị — Java 17+

Từ Java 14, `switch` không chỉ là **câu lệnh rẽ nhánh** (*switch statement*) mà còn có dạng **biểu thức** (*switch expression*) để **tạo ra một giá trị**. Java 17 hỗ trợ đầy đủ tính năng này, không cần bật preview.

~~~java
int month = 7;
String season = switch (month) {
    case 12, 1, 2 -> "winter";
    case 3, 4, 5 -> "spring";
    case 6, 7, 8 -> "summer";
    case 9, 10, 11 -> "autumn";
    default -> "invalid";
};
// season == "summer"
~~~

Biểu thức `switch` có thể đứng bên phải phép gán, trong `return` hoặc làm đối số cho phương thức. **Điểm khác với switch statement:** toàn bộ cấu trúc `switch (...) { ... }` được đánh giá thành **một giá trị**, chứ không chỉ điều khiển các câu lệnh.

## 1. Cú pháp và quy tắc chính

Dạng thông dụng nhất là các **switch rule** dùng dấu mũi tên `->`:

~~~java
String label = switch (number) {
    case 0 -> "zero";
    case 1, 2 -> "small";
    default -> "other";
};
~~~

Java đánh giá `number`, chọn đúng nhãn tương ứng rồi đánh giá biểu thức sau `->`. **Không xảy ra fall-through** từ nhánh này sang nhánh sau và **không cần `break`** để tránh rơi tiếp.

| Thuộc tính | Switch expression |
| --- | --- |
| Vai trò | Biểu thức tạo giá trị, có thể gán hoặc `return` |
| Giá trị nhánh đơn | `case X -> expression;` |
| Nhánh nhiều câu lệnh | `case X -> { ... yield value; }` |
| Nhiều nhãn cùng kết quả | `case A, B -> value;` |
| Tính đầy đủ | Phải **exhaustive**: mọi giá trị đầu vào có đường xử lý |
| Fall-through với dạng `->` | Không |
| Dấu `;` sau `}` | Cần khi toàn bộ cấu trúc nằm trong câu lệnh gán |

Những nhánh có kiểu khác nhau phải thỏa mãn **quy tắc kiểu của switch expression** và ngữ cảnh sử dụng. Không thể tùy ý trả một kiểu bất kỳ ở từng nhánh rồi giả định Java luôn chuyển chúng thành cùng kiểu.

## 2. Demo Java 17+ chạy trực tiếp

Tạo file UTF-8 tên **`SwitchExpressionDemo.java`**:

~~~java
public class SwitchExpressionDemo {
    enum Day {
        MON, TUE, WED, THU, FRI, SAT, SUN
    }

    static String category(int number) {
        return switch (number) {
            case 0 -> "zero";
            case 1, 2 -> "small";
            default -> "other";
        };
    }

    static String kind(Day day) {
        return switch (day) {
            case MON, TUE, WED, THU, FRI -> "work";
            case SAT, SUN -> "rest";
        };
    }

    static int score(int level) {
        return switch (level) {
            case 0 -> 0;
            case 1, 2 -> {
                int computed = level * 10;
                System.out.println("computed=" + computed);
                yield computed;
            }
            default -> -1;
        };
    }

    static String direction(int code) {
        return switch (code) {
            case 1:
                yield "left";
            case 2:
                yield "right";
            default:
                yield "unknown";
        };
    }

    static String traditional(int code) {
        String result;
        switch (code) {
            case 1:
                result = "left";
                break;
            case 2:
                result = "right";
                break;
            default:
                result = "unknown";
        }
        return result;
    }

    static String safeStatus(String input) {
        if (input == null) {
            return "missing";
        }
        return switch (input) {
            case "ON" -> "enabled";
            case "OFF" -> "disabled";
            default -> "unknown";
        };
    }

    static String requireNonNegative(int number) {
        return switch (number) {
            case 0 -> "zero";
            default -> {
                if (number < 0) {
                    throw new IllegalArgumentException("negative");
                }
                yield "positive";
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("== arrow rules ==");
        System.out.println("category0=" + category(0));
        System.out.println("category2=" + category(2));
        System.out.println("category9=" + category(9));

        System.out.println("== exhaustive enum ==");
        System.out.println("monday=" + kind(Day.MON));
        System.out.println("sunday=" + kind(Day.SUN));

        System.out.println("== yield ==");
        System.out.println("score0=" + score(0));
        System.out.println("score2=" + score(2));
        System.out.println("score9=" + score(9));

        System.out.println("== colon expression ==");
        System.out.println("direction1=" + direction(1));
        System.out.println("direction9=" + direction(9));

        System.out.println("== statement comparison ==");
        System.out.println("traditional2=" + traditional(2));

        System.out.println("== String and null ==");
        System.out.println("statusON=" + safeStatus("ON"));
        System.out.println("statusOther=" + safeStatus("PAUSE"));
        System.out.println("statusNull=" + safeStatus(null));

        System.out.println("== exceptions ==");
        System.out.println("nonNegative0=" + requireNonNegative(0));
        System.out.println("nonNegative3=" + requireNonNegative(3));
        try {
            requireNonNegative(-1);
        } catch (IllegalArgumentException ex) {
            System.out.println("caught=" + ex.getMessage());
        }

        var inferred = switch (1) {
            case 1 -> "yes";
            default -> "no";
        };
        System.out.println("inferred=" + inferred);
    }
}
~~~

Mở PowerShell hoặc Bash tại thư mục chứa file; yêu cầu **JDK 17 trở lên**:

~~~bash
java -version
javac -version
javac -encoding UTF-8 SwitchExpressionDemo.java
java SwitchExpressionDemo
~~~

**Exact expected stdout** của lệnh `java SwitchExpressionDemo` (không tính thông tin phiên bản JDK):

~~~text
== arrow rules ==
category0=zero
category2=small
category9=other
== exhaustive enum ==
monday=work
sunday=rest
== yield ==
score0=0
computed=20
score2=20
score9=-1
== colon expression ==
direction1=left
direction9=unknown
== statement comparison ==
traditional2=right
== String and null ==
statusON=enabled
statusOther=unknown
statusNull=missing
== exceptions ==
nonNegative0=zero
nonNegative3=positive
caught=negative
inferred=yes
~~~

Chương trình sử dụng Java chuẩn; không cần thư viện bên thứ ba. Kết quả trên được xác định theo các nhánh và thứ tự thực thi của Java 17.

## 3. Nhánh có nhiều lệnh trả kết quả thế nào?

Với `case -> expression`, chính biểu thức sau mũi tên là kết quả. Nếu cần tính toán hoặc ghi log, dùng block và `yield`: `case 1 -> { int x = 10; yield x * 2; }`. `yield` kết thúc **switch expression**, không rời toàn bộ phương thức như `return`.

Switch expression cũng cho phép nhãn `case:`, ví dụ `case 1: yield "ONE";`. Bài chuyên về từ khóa `yield` đi sâu vào đường đi có điều kiện và lỗi thiếu kết quả.

## 4. Biểu thức phải bao phủ mọi trường hợp

Với `int` và `String`, thông thường cần `default` để xử lý giá trị chưa liệt kê. Với enum, liệt kê đủ mọi hằng có thể làm switch expression exhaustive mà không cần `default`. Việc thêm hằng enum sau này có thể khiến mã phải bổ sung case khi biên dịch lại. Quy tắc chứng minh độ bao phủ và chọn kiểu kết quả được phân tích ở bài riêng.

## 5. Dạng `->` khác `case:` và switch statement

| Cấu trúc | Có tạo ra giá trị? | Có fall-through? | Cách kết thúc |
| --- | --- | --- | --- |
| `switch (x) { case 1: ... break; }` | Không: **statement** | Có thể | `break`, `return` hoặc hết khối |
| `switch (x) { case 1 -> ... }` | Không nếu dùng như **statement** | Không | Kết thúc switch rule |
| `var y = switch (x) { case 1 -> v; ... };` | Có: **expression** | Không | Giá trị biểu thức hoặc `yield` |
| `var y = switch (x) { case 1: yield v; ... };` | Có: **expression** | Dạng dấu hai chấm có luồng thực thi tuần tự | `yield`/`throw` hoặc đường thực thi hợp lệ khác |

Dấu mũi tên `->` **không đồng nghĩa switch expression**: Java 17 cũng cho phép switch **statement** với `case ->`. Phân biệt dựa vào **ngữ cảnh có đang lấy một giá trị từ switch hay không**.

Trong một khối `switch`, không trộn nhãn `case ...:` với `case ... ->`. Với switch expression dạng dấu hai chấm, mọi đường chạy bình thường phải tạo được giá trị theo quy tắc Java.

## 6. Kiểu kết quả, `var` và `null`

~~~java
var label = switch (option) {
    case 1 -> "start";
    default -> "other";
};
~~~

Ở đây `label` suy ra kiểu `String` từ switch expression; `var` không “đổi kiểu linh hoạt” theo nhánh được chạy. Trình biên dịch quyết định kiểu theo **các nhánh và ngữ cảnh đích**.

`switch` Java 17 thông thường không xem `String null` hay wrapper số null như một nhãn mặc định:

~~~java
String value = null;
// String result = switch (value) {
//     case "ON" -> "enabled";
//     default -> "unknown";
// };
// Khi chạy: NullPointerException với selector null.
~~~

Nếu cần xử lý null, kiểm tra **trước** khi đưa vào `switch`; phương thức `safeStatus` trong demo làm điều này.

## 7. Bẫy thường gặp

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “`switch` luôn là statement.” | Java 17 còn có switch **expression** |
| “Có dấu `->` nghĩa là chắc chắn switch expression.” | Switch statement cũng dùng được `->` |
| “Nhánh `->` cần `break`.” | Không có fall-through, thường không cần |
| “Trong khối `-> { ... }` dùng `return` để tạo giá trị.” | Dùng **`yield`** |
| “`yield` tương đương `return` khỏi phương thức.” | `yield` trả giá trị từ switch expression |
| “Switch expression có thể bỏ mọi nhánh còn lại mà không cần default.” | Phải **exhaustive** |
| “`default` tự bắt null selector.” | Không trong switch truyền thống Java 17 |
| “`var` thay đổi kiểu ở runtime theo case.” | Kiểu xác định khi biên dịch |
| “Có thể trộn `case X:` và `case Y ->`.” | Không được trộn trong cùng switch |

## 8. Tự kiểm tra

1. `int n = switch (2) { case 1 -> 10; case 2 -> 20; default -> 0; };` cho gì?  
   *Đáp án:* `20`.
2. Nhánh `case 1 -> { int x = 5; yield x * 2; }` tạo giá trị nào?  
   *Đáp án:* `10`.
3. `yield` có thoát luôn phương thức bao ngoài không?  
   *Đáp án:* Không; nó đưa giá trị ra khỏi switch expression.
4. Có thể dùng `case 1: yield "one";` trong switch expression không?  
   *Đáp án:* Có.
5. Switch expression trên `int` có một nhánh `case 1` nhưng không có `default` có đầy đủ không?  
   *Đáp án:* Không.
6. Dạng `case 1 -> System.out.println("x");` có nhất thiết là switch expression không?  
   *Đáp án:* Không; đó có thể là switch statement.
7. Vì sao cần xử lý `String null` trước switch Java 17 thường?  
   *Đáp án:* Selector null có thể gây `NullPointerException`.

## Checklist

- [ ] Hiểu switch **expression** tạo giá trị để gán, `return` hoặc truyền vào hàm.
- [ ] Dùng `case -> value` cho nhánh đơn; dùng `yield` khi nhánh là khối nhiều lệnh.
- [ ] Nhớ dạng `->` không rơi tiếp xuống case sau.
- [ ] Bảo đảm nhánh bao phủ đầy đủ; chọn `default` hoặc liệt kê toàn bộ enum.
- [ ] Phân biệt `yield` với `return` và `break`.
- [ ] Không nhầm switch statement dùng `->` với switch expression.
- [ ] Hiểu kiểu kết quả xác định khi biên dịch và xử lý selector null khi cần.

**Kết luận:** Switch expression giúp lựa chọn **một giá trị** trực tiếp từ nhiều trường hợp, giảm việc khai báo biến rồi gán trong từng nhánh. Trong Java 17, hãy ưu tiên `->` cho nhánh độc lập, dùng `yield` khi cần khối xử lý, và giữ tính **đầy đủ** của các trường hợp.
