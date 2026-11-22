# Giá trị `null`, unboxing và thời điểm phát sinh lỗi trong `switch` expression

## 1. Ba giá trị cần phân biệt

Từ Java 14, `switch` có thể là **biểu thức trả về một giá trị**. Nhánh `case ... ->` tạo ra kết quả trực tiếp; nhánh có khối lệnh dùng `yield` để trả kết quả. Cú pháp này vẫn là Java hiện đại. Khi phân tích `NullPointerException` (NPE), cần phân biệt:

- **Selector**: biểu thức trong `switch (selector)`, ví dụ `Integer code`, `String status` hoặc một lời gọi phương thức.
- **Dữ liệu được dùng ở nhánh đã chọn**: có thể là `Integer`, `Boolean` hay đối tượng khác đang mang `null`.
- **Kết quả của `switch`**: có thể là tham chiếu `null` nếu kiểu kết quả cho phép; một phép unboxing hoặc truy cập phương thức về sau mới gây lỗi.

`null` là giá trị của **kiểu tham chiếu**, không phải của `int`, `boolean` hay kiểu nguyên thủy khác. `Integer` có thể `null`, còn `int` không thể. **Unboxing** là việc đổi wrapper như `Integer` thành `int` hoặc `Boolean` thành `boolean`. Unbox một tham chiếu `null` gây `NullPointerException`.

**Mốc phiên bản cần nhớ:** Java 14 có `switch` expression ổn định, nhưng chưa có `case null` ổn định. Trên Java 14–20 khi không bật tính năng preview, phải kiểm tra selector `null` trước `switch`. Từ **Java 21**, pattern matching for `switch` là tính năng chính thức và cho phép `case null -> ...` với selector kiểu tham chiếu. Nếu bỏ `case null`, selector `null` vẫn ném NPE. Những quy tắc về unboxing và thời điểm đánh giá bên dưới vẫn áp dụng trong Java hiện đại.

## 2. Thứ tự đánh giá quyết định thời điểm lỗi

1. Java đánh giá biểu thức selector trong `switch (...)` **một lần**. Nếu một lời gọi, phép ép kiểu hoặc phép unboxing trong chính selector ném ngoại lệ, `switch` chưa hề chọn nhánh.
2. Với selector kiểu tham chiếu, Java xử lý `null`. Java 21+ chọn `case null` nếu có; nếu không, ném NPE **trước khi chạy `default`**. Với các wrapper không null và nhãn hằng số số học, Java có thể unbox để so khớp hằng số.
3. Java chọn nhãn phù hợp. Dạng `case ... ->` không có fall-through; biểu thức của những nhánh khác **không được chạy**.
4. Java thực thi thân nhánh được chọn và đánh giá biểu thức sau `->` hoặc `yield`. Các phép `Integer + int` hay kiểm tra `Boolean` có thể unbox và ném NPE ngay ở bước này.
5. Sau khi `switch` trả kết quả, phép gán, trả về hoặc tính toán **bên ngoài** cũng có thể cần unboxing. Một `Integer` kết quả là `null` chỉ gây NPE khi thực sự bị unbox hoặc dereference.

| Trường hợp | Thời điểm / kết quả |
| --- | --- |
| `Integer x = null; switch (x)`, không có `case null` | NPE ở bước xử lý selector, trước mọi nhánh |
| `Integer x = null; switch ((int) x)` | NPE ngay lúc đánh giá selector do unboxing |
| `String s = null; switch (s)`, không có `case null` | NPE ở selector dù `String` không liên quan đến unboxing |
| Nhánh được chọn thực hiện `Integer amount = null; amount + 5` | NPE khi tính phép cộng trong nhánh |
| Nhánh không được chọn có `amount + 5` | Không đánh giá phép cộng, nên không phát sinh NPE từ nó |
| `Integer result = switch (...) { case 1 -> null; default -> 10; };` | Có thể trả tham chiếu `null` bình thường; cần xem nơi dùng `result` |
| Java 21+: `case null -> "Chưa có"` | Selector `null` được xử lý thành một kết quả có chủ đích |

**Chi tiết kỹ thuật:** với selector `Integer` mang `null` trong `switch` không có nhánh null, đặc tả kiểm tra `null` trước khi so khớp các hằng số số học có thể cần unboxing. Do đó không nên tự kết luận NPE này chắc chắn đến từ lời gọi `intValue()`. Đối với `switch ((int) x)`, phép unboxing được yêu cầu rõ ràng ngay trong selector.

## 3. Chương trình Java 17+: ba vị trí NPE khác nhau

Tệp `SwitchNullTiming.java` sau chạy được trên Java 17+; `switch` expression đã là cú pháp ổn định từ Java 14:

~~~java
public class SwitchNullTiming {
    static String describe(Integer code) {
        return switch (code) {
            case 1 -> "Một";
            case 2 -> "Hai";
            default -> "Khác";
        };
    }

    static int calculate(int action, Integer amount) {
        return switch (action) {
            case 1 -> {
                int total = amount + 5;
                yield total;
            }
            default -> 0;
        };
    }

    static Integer choose(int action) {
        return switch (action) {
            case 1 -> null;
            default -> 10;
        };
    }

    public static void main(String[] args) {
        Integer code = null;
        System.out.println("Trước switch");
        try {
            System.out.println(describe(code));
        } catch (NullPointerException ex) {
            System.out.println("NPE: selector null");
        }

        System.out.println("Nhánh không chạy: " + calculate(0, null));
        try {
            calculate(1, null);
        } catch (NullPointerException ex) {
            System.out.println("NPE: unboxing trong nhánh");
        }

        Integer result = choose(1);
        System.out.println("Kết quả reference null: " + result);
        try {
            int primitive = result;
            System.out.println(primitive);
        } catch (NullPointerException ex) {
            System.out.println("NPE: unboxing sau switch");
        }
    }
}
~~~

Biên dịch với JDK 17 trở lên; cờ `--release 17` cho biết mã không phụ thuộc vào cú pháp mới hơn Java 17:

~~~bash
javac --release 17 -encoding UTF-8 SwitchNullTiming.java
java SwitchNullTiming
~~~

Stdout chính xác:

~~~text
Trước switch
NPE: selector null
Nhánh không chạy: 0
NPE: unboxing trong nhánh
Kết quả reference null: null
NPE: unboxing sau switch
~~~

Giải thích:

- `describe(null)` ném NPE **trước** cả `case 1`, `case 2` và `default`. `default` không có nghĩa “bắt mọi giá trị kể cả null”.
- `calculate(0, null)` chọn `default -> 0` nên không đọc `amount`; kết quả `0`, không có NPE.
- `calculate(1, null)` chọn `case 1`, rồi `amount + 5` cần unboxing `Integer amount`; NPE phát sinh **trong nhánh, trước `yield total`**.
- `choose(1)` trả `null` dưới kiểu `Integer` hợp lệ. `System.out.println` in `null` mà không unbox.
- `int primitive = result` mới cần `int` nên ném NPE **sau khi `switch` đã kết thúc**.

`try/catch` trong chương trình chỉ nhằm quan sát nhiều tình huống trong cùng một lượt chạy; ở ứng dụng thực, xử lý hợp đồng `null` rõ ràng thường tốt hơn việc bắt mọi NPE.

## 4. Java 21+: dùng `case null` cho selector kiểu tham chiếu

Java 21 chuẩn hóa pattern matching for `switch`, vì vậy đoạn sau biên dịch bình thường **không cần `--enable-preview`**. Tạo tệp `SwitchNullJava21.java`:

~~~java
public class SwitchNullJava21 {
    static String label(Integer number) {
        return switch (number) {
            case null -> "Chưa có mã";
            case 0 -> "Không";
            default -> "Mã " + number;
        };
    }

    public static void main(String[] args) {
        System.out.println(label(null));
        System.out.println(label(0));
        System.out.println(label(7));
    }
}
~~~

~~~bash
javac --release 21 -encoding UTF-8 SwitchNullJava21.java
java SwitchNullJava21
~~~

Stdout:

~~~text
Chưa có mã
Không
Mã 7
~~~

`case null` xử lý chính xác selector mang `null`. `default` xử lý những giá trị **không null** chưa khớp nhãn trước đó; nếu xóa `case null`, `label(null)` lại ném NPE. Java 21 cũng cho phép `case null, default -> ...` khi thật sự muốn gộp hai trường hợp. Không dùng `case null` trên selector nguyên thủy `int`, vì `int` không thể null.

**Tương thích Java 14/17:** không dán ví dụ có `case null` vào mã biên dịch bằng `--release 17`. Nếu dự án cần hỗ trợ Java 17, kiểm tra trước khi vào `switch`:

~~~java
static String labelCompatible(Integer number) {
    if (number == null) {
        return "Chưa có mã";
    }
    return switch (number) {
        case 0 -> "Không";
        default -> "Mã " + number;
    };
}
~~~

Đây là **phương thức minh họa trong một lớp Java**, không phải tệp chứa `main` độc lập. Nó biểu diễn cùng hợp đồng với phiên bản Java 21.

## 5. `case null` không ngăn được các phép unboxing ở nơi khác

Ngay cả khi selector đã được xử lý, NPE vẫn có thể xảy ra ở:

- **Thân nhánh**: `Integer amount = null; int total = amount + 5;` ném NPE khi cộng.
- **Điều kiện**: `Boolean enabled = null; if (enabled) { ... }` ném NPE vì điều kiện cần `boolean`.
- **Sau `switch`**: kết quả `Integer result = null` hợp lệ, nhưng `int total = result;` ném NPE.
- **Truy cập đối tượng**: `result.toString()` khi `result == null` cũng ném NPE, nhưng đây là dereference null, **không phải unboxing**.

Nếu dùng `when` trong pattern matching for `switch` (Java 21+), điều kiện guard cũng có thể unbox. Phương thức minh họa:

~~~java
static String classify(Object value, Boolean enabled) {
    return switch (value) {
        case String s when enabled -> "Bật";
        case String s -> "Tắt hoặc không thỏa";
        default -> "Khác";
    };
}
~~~

- `classify(123, null)` trả `"Khác"`: giá trị không khớp `String`, nên guard không chạy.
- `classify("ok", null)` ném NPE: `String` khớp, Java đánh giá `when enabled`, phải unbox `Boolean enabled` đang null, và lỗi xảy ra **trong bước chọn nhãn, trước phần thân nhánh**.
- Nếu `enabled == null` mang nghĩa “không bật”, hãy dùng `when Boolean.TRUE.equals(enabled)` để so sánh an toàn, không unbox null. Nếu null bị cấm, hãy kiểm tra đầu vào để phát hiện sai hợp đồng sớm.

## 6. Cách chọn chính sách `null` đúng nghiệp vụ

**`null` là trạng thái hợp lệ:** Ví dụ “chưa nhập mã”. Hãy mô tả nó như một trường hợp nghiệp vụ: `case null` trên Java 21+ hoặc `if (value == null)` trước `switch` trên Java 14/17. Nếu phương thức trả `Integer` có thể null, người gọi cũng cần xử lý giá trị thiếu trước khi unbox.

**`null` là đầu vào sai:** Có thể dùng `Objects.requireNonNull` để fail fast với thông điệp rõ ràng:

~~~java
import java.util.Objects;

static String describeRequired(Integer code) {
    Objects.requireNonNull(code, "code không được null");
    return switch (code) {
        case 1 -> "Một";
        case 2 -> "Hai";
        default -> "Khác";
    };
}
~~~

Đây là đoạn phương thức minh họa trong một lớp Java. `Objects.requireNonNull` chỉ phù hợp khi hợp đồng **thật sự cấm null**. Đừng biến một trạng thái nghiệp vụ hợp lệ thành ngoại lệ không cần thiết.

**Chỉ nhánh cụ thể dùng wrapper có thể null:** Kiểm tra tại điểm sử dụng trong nhánh, hoặc kiểm tra ở đầu hàm nếu muốn xác nhận hợp đồng đầu vào sớm. Nhánh không được chọn không chạy, nhưng dựa vào đó để bỏ qua dữ liệu sai hợp đồng có thể khiến lỗi xuất hiện muộn ở lượt gọi khác.

**Cần đầu ra nguyên thủy:** Thiết kế các nhánh trả về giá trị `int` hợp lệ, hoặc quyết định rõ quy tắc thay thế `null` trước phép gán vào `int`. Đừng tự dùng `0` làm mặc định trừ khi `0` có ý nghĩa nghiệp vụ phù hợp; như vậy có thể che lỗi dữ liệu.

## 7. Những kết luận sai thường gặp

1. **“Có `default` là hết NPE do selector null.”** Sai; cần `case null` trên Java 21+ hoặc kiểm tra bên ngoài.
2. **“NPE ở `switch` lúc nào cũng do unboxing.”** Sai với `String` selector null. Cần xác định chính xác bước đánh giá, chọn nhánh và chuyển kiểu.
3. **“Một nhánh không chạy vẫn có thể gây NPE qua biểu thức trong nhánh.”** Sai với `case ->`: biểu thức của nhánh không chọn không được đánh giá.
4. **“`switch` expression không bao giờ trả null.”** Sai khi kiểu kết quả cho phép tham chiếu null; NPE có thể nằm ở lời gọi phía sau.
5. **“`case null` dùng được trên Java 17 ổn định.”** Sai; tính năng chuẩn, không-preview cần Java 21+.
6. **“Bắt mọi NPE rồi trả mặc định là sửa xong lỗi.”** Không đáng tin: có thể che lỗi selector, lỗi trong nhánh hoặc phép unboxing ở nơi khác. Hãy kiểm tra hợp đồng null trước.

Khi debug, hãy lần lượt hỏi: **selector được tính bằng biểu thức nào? Giá trị selector có null không? Java đang chạy phiên bản nào và có `case null` không? Nhánh nào được chọn? Biểu thức trong nhánh nào cần unboxing? Kết quả `switch` được dùng ở đâu?** Trả lời theo đúng thứ tự sẽ định vị lỗi thay vì sửa nhầm `default`.

## Nguồn kỹ thuật chính thức

- Oracle Java 21, *Switch Expressions and Statements*: https://docs.oracle.com/en/java/javase/21/language/switch-expressions-statements.html
- Oracle Java 21, *Pattern Matching for switch Expressions and Statements* (bao gồm `case null` và `when`): https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- Java Language Specification 21, §14.11 (chọn nhánh) và §15.28 (đánh giá `switch` expression): https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html và https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html
- Java Language Specification 21, §5.1.8 (unboxing conversion): https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html