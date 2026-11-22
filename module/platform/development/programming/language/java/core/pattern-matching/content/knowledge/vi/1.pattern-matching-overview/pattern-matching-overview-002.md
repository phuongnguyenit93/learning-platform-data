# Từ kiểm tra kiểu đến kiểm tra và lấy dữ liệu trong Java

## 1. Vấn đề: biết kiểu thôi chưa đủ

Khi một biến có kiểu khai báo rộng như `Object`, chương trình thường cần xác định kiểu thực tế trước khi sử dụng hành vi riêng của đối tượng. Ví dụ, một `String` có phương thức `length()`, còn một `Integer` có thể được dùng như số nguyên. Kiểm tra kiểu giúp chọn nhánh xử lý; nhưng để gọi phương thức hoặc lấy thành phần dữ liệu cụ thể, ta còn phải truy cập đối tượng theo kiểu thích hợp.

**Pattern matching** đưa hai thao tác gần nhau hơn: **kiểm tra xem một giá trị có khớp mẫu hay không** và, nếu khớp, **gắn dữ liệu phù hợp vào biến**. Với *type pattern*, biến nhận chính đối tượng đã được kiểm tra kiểu; với *record pattern* (Java 21+), mẫu có thể lấy trực tiếp các thành phần của một `record`.

Sau bài này, bạn có thể:
- Giải thích vì sao `instanceof` truyền thống thường đi kèm ép kiểu.
- Viết `instanceof Type variable` để vừa kiểm tra vừa dùng giá trị đã khớp.
- Hiểu phạm vi tồn tại của pattern variable theo luồng điều khiển.
- Phân biệt *type pattern* (gắn cả đối tượng) với *record pattern* (tách các thành phần).
- Nhận biết khi nào dùng pattern matching trong `switch` và các lỗi thường gặp.

## 2. Cách truyền thống: kiểm tra trước, ép kiểu sau

Trước khi có pattern matching cho `instanceof`, mã nguồn thường tách việc hỏi “có phải kiểu này không?” và việc ép kiểu thành hai bước.

~~~java
public class BeforePattern {
    static String describe(Object value) {
        if (value instanceof String) {
            String text = (String) value;
            return "String(length=" + text.length() + ")";
        }
        if (value instanceof Integer) {
            Integer number = (Integer) value;
            return "Integer(value=" + number + ")";
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(42));
        System.out.println(describe(null));
    }
}
~~~

Lưu tệp `BeforePattern.java`, chạy với JDK 17 trở lên:

~~~bash
javac --release 17 BeforePattern.java
java BeforePattern
~~~

Kết quả:

~~~text
String(length=4)
Integer(value=42)
Other
~~~

Trong nhánh đầu, `value instanceof String` trả về `true` nếu giá trị đang tham chiếu đến một đối tượng `String`. Tuy nhiên, kiểu khai báo của `value` vẫn là `Object`; vì vậy mã phải viết thêm `(String) value` trước khi gọi `length()`.

Cách này hợp lệ, nhưng lặp tên kiểu, tạo thêm một biến và có thể gây lỗi khi người viết sửa điều kiện mà quên sửa ép kiểu tương ứng. Ép kiểu sai có thể gây `ClassCastException`. Mục tiêu của pattern matching là giảm phần mã lặp ấy, đồng thời đặt thông tin kiểu ngay tại vị trí kiểm tra.

## 3. Type pattern: kiểm tra và gắn biến trong một biểu thức

Từ Java 16, *pattern matching for instanceof* là tính năng chính thức; Java 17 sử dụng được mà không cần bật preview.

~~~java
public class PatternBinding {
    static String describe(Object value) {
        if (value instanceof String text) {
            return "String(length=" + text.length() + ")";
        }
        if (value instanceof Integer number) {
            return "Integer(value=" + number + ")";
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(42));
        System.out.println(describe(null));
    }
}
~~~

~~~bash
javac --release 17 PatternBinding.java
java PatternBinding
~~~

Kết quả vẫn là:

~~~text
String(length=4)
Integer(value=42)
Other
~~~

Đọc biểu thức `value instanceof String text` theo ba phần:

1. **Giá trị cần kiểm tra:** `value`.
2. **Mẫu kiểu:** `String` — yêu cầu giá trị là một đối tượng tương thích với kiểu này.
3. **Pattern variable:** `text` — chỉ được gắn với giá trị khi mẫu khớp, và có kiểu `String`.

Vì `text` đã có kiểu `String`, bạn dùng ngay `text.length()` mà không ép kiểu. Biến `text` không phải bản sao của đối tượng; nó tham chiếu cùng đối tượng mà `value` tham chiếu. Với `Integer number`, nguyên tắc cũng tương tự.

Lưu ý: **`null instanceof String text` luôn không khớp**. Do đó lời gọi `describe(null)` đi tới nhánh `Other`, không tự phát sinh `NullPointerException` ở phép kiểm tra `instanceof`.

Có thể hình dung tiến trình như sau:

~~~text
Giá trị có kiểu khai báo Object
           |
           v
   Khớp mẫu String text?
       /           \
     có             không
      |               |
Gắn biến text     Thử mẫu khác
      |
Dùng API của String
~~~

## 4. Phạm vi biến phụ thuộc vào nhánh đã khớp

Pattern variable không tự động tồn tại trong toàn bộ phương thức. Trình biên dịch theo dõi luồng điều khiển để xác định nơi mẫu **chắc chắn đã khớp** (*flow scoping*).

Trường hợp đơn giản: trong nhánh `if (value instanceof String text)`, biến `text` dùng được. Ở nhánh `else` tương ứng, bạn không thể giả định nó đã được gắn.

Một trường hợp hữu ích là kiểm tra phủ định rồi thoát sớm:

~~~java
public class FlowScopeDemo {
    static String normalized(Object value) {
        if (!(value instanceof String text)) {
            return "Not a String";
        }
        if (text.isBlank()) {
            return "Blank String";
        }
        return text.trim().toUpperCase();
    }

    public static void main(String[] args) {
        System.out.println(normalized("  java  "));
        System.out.println(normalized("   "));
        System.out.println(normalized(3));
    }
}
~~~

~~~bash
javac --release 17 FlowScopeDemo.java
java FlowScopeDemo
~~~

Kết quả:

~~~text
JAVA
Blank String
Not a String
~~~

Vì nhánh “không phải String” đã `return`, mọi đường thực thi còn lại tại dòng `text.isBlank()` đều đã khớp `String text`. Vì thế biến `text` hợp lệ sau `if`.

**Điều kiện kết hợp cũng tuân theo luồng thực thi:**

- `value instanceof String text && !text.isBlank()` hợp lệ: vế phải chỉ chạy khi mẫu ở vế trái đã khớp.
- `value instanceof String text || text.isBlank()` không hợp lệ: vế phải có thể chạy khi mẫu ở vế trái **không** khớp, nên `text` chưa được gắn.
- Nếu nhánh thất bại không thoát khỏi luồng xử lý, đừng dùng pattern variable ở đoạn mã mà nhánh thất bại cũng có thể đi tới.

Quy tắc thực hành: chỉ sử dụng biến được tạo từ pattern ở những vị trí mà Java chứng minh được phép kiểm tra tương ứng đã thành công.

## 5. Từ gắn cả đối tượng đến lấy từng thành phần: record pattern

Với `String text`, mẫu kiểu chỉ cho ta một biến trỏ tới toàn bộ `String`. Nếu dữ liệu nằm trong nhiều thành phần, ta vẫn có thể phải gọi các phương thức truy cập. Ví dụ, với `record Point(int x, int y)`, kiểu `Point` có các accessor `x()` và `y()`.

Từ **Java 21**, *record pattern* cho phép kiểm tra record và lấy trực tiếp các thành phần trong cùng một mẫu, kể cả khi các record lồng nhau:

~~~java
record Point(int x, int y) {}
record Line(Point start, Point end) {}

public class RecordPatternDemo {
    static String describe(Object value) {
        if (value instanceof Point(int x, int y)) {
            return "Point(" + x + "," + y + ")";
        }
        if (value instanceof Line(Point(int x1, int y1), Point(int x2, int y2))) {
            return "Line(" + x1 + "," + y1 + ")->(" + x2 + "," + y2 + ")";
        }
        return "Other";
    }

    public static void main(String[] args) {
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe(
            new Line(new Point(1, 2), new Point(3, 4))
        ));
        System.out.println(describe("Java"));
    }
}
~~~

~~~bash
javac --release 21 RecordPatternDemo.java
java RecordPatternDemo
~~~

Kết quả:

~~~text
Point(2,5)
Line(1,2)->(3,4)
Other
~~~

Trong mẫu `Point(int x, int y)`:
- `Point` xác định loại record phải khớp.
- Hai mẫu thành phần `int x` và `int y` lấy giá trị từ hai record component tương ứng theo thứ tự khai báo.
- Bên trong nhánh khớp, `x` và `y` là biến kiểu `int` có thể dùng ngay.

Mẫu `Line(Point(int x1, int y1), Point(int x2, int y2))` tiến thêm một bước: kiểm tra một `Line`, sau đó khớp hai `Point` bên trong và gắn bốn tọa độ vào biến. Đây là *deconstruction*: mô tả cấu trúc dữ liệu mà ta muốn lấy ra, thay vì tự ép kiểu rồi lần lượt gọi `start().x()`, `start().y()`, `end().x()`, `end().y()`.

**Giới hạn cần hiểu:** cú pháp record pattern áp dụng cho `record`, không phải cách tự động “bóc tách” mọi lớp Java thông thường. Kiểu và thứ tự thành phần phải phù hợp với khai báo record. Nếu một thành phần lồng nhau không khớp mẫu tương ứng, toàn bộ mẫu không khớp. Record pattern là tính năng ổn định từ Java 21; đoạn này không biên dịch bằng `--release 17`.

## 6. Pattern matching trong switch: phân nhánh và lấy dữ liệu cùng lúc

Khi có nhiều loại đầu vào, chuỗi `if/else if` có thể dài. Từ **Java 21**, `switch` hỗ trợ type pattern và điều kiện bổ sung bằng `when` một cách chính thức.

~~~java
public class SwitchPatternDemo {
    static String classify(Object value) {
        return switch (value) {
            case null -> "Null";
            case String text when text.isBlank() -> "Blank String";
            case String text -> "String(length=" + text.length() + ")";
            case Integer n -> "Integer(value=" + n + ")";
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(classify(null));
        System.out.println(classify("  "));
        System.out.println(classify("Java"));
        System.out.println(classify(7));
    }
}
~~~

~~~bash
javac --release 21 SwitchPatternDemo.java
java SwitchPatternDemo
~~~

Kết quả:

~~~text
Null
Blank String
String(length=4)
Integer(value=7)
~~~

`case String text` vừa nhận diện đầu vào kiểu `String`, vừa gắn biến `text` để dùng trong nhánh đó. Với `case String text when text.isBlank()`, điều kiện `when` chỉ xét sau khi type pattern đã khớp. Nhánh dành cho `String` rỗng hoặc chỉ chứa khoảng trắng phải đứng **trước** nhánh `case String text` rộng hơn; đảo thứ tự có thể khiến nhánh hẹp bị báo là không thể tới được (*dominated case*).

Với `switch` trên đối tượng, `null` cần được xem xét riêng: nếu không có `case null`, truyền `null` thông thường làm `switch` ném `NullPointerException`. `default` xử lý những kiểu còn lại trong ví dụ. Java 17 chưa hỗ trợ cú pháp `switch` này như tính năng ổn định; dùng JDK 21+.

## 7. Chọn mức pattern phù hợp

| Nhu cầu | Cú pháp điển hình | Dữ liệu nhận được | Phiên bản ổn định |
| --- | --- | --- | --- |
| Chỉ hỏi có thuộc một kiểu không | `obj instanceof String` | Giá trị `boolean` | Java từ lâu đã có |
| Kiểm tra kiểu rồi dùng đối tượng | `obj instanceof String s` | Biến `s` kiểu `String` | Java 16+ |
| Kiểm tra record và lấy thành phần | `obj instanceof Point(int x, int y)` | Các biến `x`, `y` | Java 21+ |
| Chọn một trong nhiều mẫu | `switch (obj) { case String s -> ...; ... }` | Biến chỉ có trong nhánh tương ứng | Java 21+ |

Khi chỉ cần biết “có phải kiểu này không?”, phép `instanceof` truyền thống vẫn đủ. Khi cần dùng đối tượng sau kiểm tra, *type pattern* thường làm mã ngắn và dễ đọc hơn. Khi xử lý nhiều record có cấu trúc rõ ràng, *record pattern* giúp thể hiện trực tiếp dữ liệu muốn lấy; khi có nhiều nhánh kiểu, `switch` giúp tập trung logic phân loại.

Pattern matching không chuyển đổi một chuỗi thành số, không tự giải mã JSON và không thay thế việc xác thực dữ liệu nghiệp vụ. Nó **khớp kiểu/cấu trúc có sẵn** của đối tượng và chỉ gắn biến khi mẫu thành công.

## 8. Sai lầm thường gặp và cách tránh

1. **Dùng biến pattern ngoài vùng được đảm bảo khớp.** Ví dụ, không truy cập `text` ở vế phải của biểu thức `||` khi `text` chỉ được khai báo trong type pattern ở vế trái. Dùng `&&` khi logic phù hợp hoặc tách thành nhánh `if` có điểm thoát rõ ràng.
2. **Cho rằng null là một đối tượng khớp type pattern.** `null instanceof String s` trả về `false`; với `switch` trên tham chiếu, chủ động quyết định cách xử lý `null`.
3. **Nhầm gắn biến với tạo bản sao hoặc chuyển đổi dữ liệu.** `obj instanceof String s` không tạo `String` mới. Record pattern lấy các thành phần theo khai báo record; nó không tạo đối tượng mới để thay thế giá trị gốc.
4. **Dùng cú pháp mới trên JDK cũ.** `instanceof String s` dùng được trong Java 17; cú pháp record pattern và `switch` pattern ở trên cần Java 21+. Khi chia sẻ mã, kiểm tra cả phiên bản JDK và cấu hình `--release`.
5. **Đặt mẫu bao quát trước mẫu cụ thể trong switch.** Một `case String s` không có guard có thể che mọi nhánh `String` đặt sau nó. Đặt trường hợp có điều kiện `when` trước.
6. **Nghĩ rằng record pattern áp dụng được cho mọi class.** Đối tượng của lớp thường không tự cung cấp cấu trúc record component; khi cần, hãy dùng accessor hoặc thiết kế kiểu dữ liệu phù hợp.

## 9. Tự kiểm tra

**Bài tập 1.** Cho `Object input = "  Java  ";`. Viết điều kiện dùng `instanceof` pattern để chỉ gọi `trim()` nếu `input` là `String` không trống. Gợi ý: kết hợp `instanceof String s` với `&& !s.isBlank()`. Giá trị sau `trim()` là `"Java"`.

**Bài tập 2.** Với `record Size(int width, int height) {}`, hãy dùng một record pattern để nhận `Size` từ biến kiểu `Object` và tính diện tích. Nếu biến chứa `new Size(3, 4)`, kết quả là `12`; nếu chứa `"3x4"`, mẫu không khớp. Bài này cần Java 21+.

**Câu hỏi tư duy.** Vì sao `if (!(value instanceof String s)) return;` (trong phương thức có kiểu trả về `void`) cho phép dùng `s` ở dòng sau, còn `if (!(value instanceof String s)) { System.out.println("other"); }` thì không? Đáp án: trường hợp đầu loại bỏ hoàn toàn đường thực thi chưa khớp; trường hợp sau vẫn có thể đi tiếp đến dòng kế khi mẫu thất bại.

**Ghi nhớ:** bước phát triển quan trọng của pattern matching là đi từ **“giá trị có thuộc kiểu này không?”** đến **“nếu khớp, ta có thể dùng ngay dữ liệu nào, và dữ liệu đó chắc chắn hợp lệ ở đâu trong luồng chương trình?”**.
