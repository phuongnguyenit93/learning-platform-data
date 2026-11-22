# Tương tác với phương thức nạp chồng

Static import cho phép gọi một phương thức static bằng tên ngắn. Khi tên ấy có nhiều phiên bản nạp chồng (overload), trình biên dịch vẫn phải xác định phương thức nào phù hợp với các đối số.

Điểm quan trọng là tách hai câu hỏi: **tên phương thức đến từ đâu**, rồi **trong các ứng viên đã tìm được, phương thức nào được chọn**. Static import tác động đến việc tìm tên; nó không thay thế quy tắc chọn overload của Java.

## 1. Import theo tên, không theo chữ ký

```java
import static java.lang.Math.max;
```

Khai báo này không có nghĩa “chỉ nhập `max(int, int)`”. Nó nhập theo tên `max`, nên các overload truy cập được cùng tên có thể tham gia phân giải lời gọi:

```java
int first = max(3, 8);
double second = max(3.5, 8.5);
```

Các dòng trên là đoạn dùng trong thân phương thức khi đã có static import tương ứng.

Không có cú pháp để ghi danh sách kiểu tham số trong import:

```java
// Cố ý minh họa cú pháp không hợp lệ:
// import static java.lang.Math.max(int, int);
```

Muốn tác động đến overload được chọn, cần xem kiểu biểu thức tại lời gọi, tên kiểu chứa phương thức nếu muốn chỉ rõ nguồn, và thiết kế API. Không giải quyết bằng việc thêm chữ ký vào dòng import.

## 2. Trình tự suy nghĩ khi đọc một lời gọi

Với những ví dụ không dùng generic phức tạp, có thể kiểm tra theo thứ tự:

1. Tên đơn giản có trỏ đến phương thức của lớp đang viết hoặc một nguồn tên trong phạm vi gần hơn không?
2. Nếu tên được tìm qua static import, những phương thức truy cập được nào cùng tên là ứng viên?
3. Số lượng và kiểu đối số phù hợp với ứng viên nào?
4. Giai đoạn xét lời gọi nào đầu tiên tìm được ứng viên phù hợp?
5. Trong giai đoạn đó, có phương thức cụ thể nhất để chọn không?

Java xét các giai đoạn chính:

| Giai đoạn | Cách gọi được xét |
| --- | --- |
| 1 | Số tham số cố định, chưa cần boxing/unboxing hoặc đóng gói varargs; có thể có mở rộng kiểu |
| 2 | Số tham số cố định, cho phép thêm boxing/unboxing theo quy tắc lời gọi |
| 3 | Lời gọi với số lượng đối số thay đổi, có đóng gói varargs |

Khi một giai đoạn đã tìm được ứng viên phù hợp, các giai đoạn sau không được dùng để tìm một ứng viên “có vẻ tiện hơn”.

Một phương thức khai báo varargs vẫn có thể tham gia cách gọi số tham số cố định nếu đối số truyền vào đã là mảng phù hợp. Vì vậy, cần phân biệt khai báo có dấu `...` với một lời gọi thực sự cần đóng gói varargs.

Trong giai đoạn đang xét, trình biên dịch còn cần quy tắc phương thức cụ thể nhất (most specific). Nếu không xác định được ứng viên cần chọn, lời gọi có thể nhập nhằng và không biên dịch.

## 3. Chương trình: cùng tên từ hai lớp

Ví dụ dưới đây dùng hai lớp cung cấp phương thức cùng tên `format`. Mỗi phương thức in dấu hiệu riêng để quan sát overload được chọn. Các lớp dùng cú pháp tương thích Java 17+.

Tạo cấu trúc:

```text
demo/
  numeric/
    NumericOps.java
  text/
    TextOps.java
  StaticOverloadDemo.java
```

### Tệp demo/numeric/NumericOps.java

```java
package demo.numeric;

public final class NumericOps {
    private NumericOps() {
    }

    public static String format(int value) {
        return "int: " + value;
    }

    public static String format(long value) {
        return "long: " + value;
    }

    public static String format(Integer value) {
        return "Integer: " + value;
    }

    public static String format(int... values) {
        return "int... count: " + values.length;
    }
}
```

### Tệp demo/text/TextOps.java

```java
package demo.text;

public final class TextOps {
    private TextOps() {
    }

    public static String format(String value) {
        return "String: " + value;
    }

    public static String format(Object value) {
        return "Object: " + value;
    }
}
```

### Tệp demo/StaticOverloadDemo.java

```java
package demo;

import static demo.numeric.NumericOps.format;
import static demo.text.TextOps.format;

public class StaticOverloadDemo {
    public static void main(String[] args) {
        System.out.println(format(4));
        System.out.println(format(4L));
        System.out.println(format(Integer.valueOf(4)));
        System.out.println(format("java"));
        System.out.println(format(1, 2));
        System.out.println(format());

        Object item = "java";
        System.out.println(format(item));
    }
}
```

Từ thư mục chứa `demo`, biên dịch và chạy:

```shell
javac -encoding UTF-8 -d out demo/numeric/NumericOps.java demo/text/TextOps.java demo/StaticOverloadDemo.java
java -cp out demo.StaticOverloadDemo
```

Stdout:

```text
int: 4
long: 4
Integer: 4
String: java
int... count: 2
int... count: 0
Object: java
```

### Phân tích từng lời gọi

| Lời gọi | Overload được chọn | Cơ sở chính |
| --- | --- | --- |
| `format(4)` | `NumericOps.format(int)` | Khớp kiểu `int`; cụ thể hơn phương án mở rộng sang `long` trong cùng giai đoạn |
| `format(4L)` | `NumericOps.format(long)` | Biểu thức có kiểu `long` |
| `format(Integer.valueOf(4))` | `NumericOps.format(Integer)` | Khớp `Integer`; cụ thể hơn tham số `Object`, không cần chờ unboxing |
| `format("java")` | `TextOps.format(String)` | `String` cụ thể hơn `Object` |
| `format(1, 2)` | `NumericOps.format(int...)` | Cần cách gọi varargs để nhận hai đối số |
| `format()` | `NumericOps.format(int...)` | Mảng varargs rỗng |
| `format(item)` với `item` khai báo là `Object` | `TextOps.format(Object)` | Chọn theo kiểu biểu thức tại thời điểm biên dịch |

Hai static import cùng tên trong ví dụ không tự gây lỗi. Các chữ ký khác nhau có thể tạo một tập ứng viên mà từng lời gọi được giải quyết rõ ràng.

Đây không phải thao tác gộp hai lớp thành một lớp hay tạo quan hệ kế thừa. Các phương thức vẫn thuộc hai kiểu ban đầu.

## 4. Kiểu khai báo của đối số quan trọng hơn điều “đang chứa”

Trong chương trình:

```java
Object item = "java";
System.out.println(format(item));
```

Mặc dù đối tượng thực tế là chuỗi, kiểu của biểu thức `item` là `Object`. Lời gọi chọn `format(Object)`, không tự đổi sang `format(String)` lúc chạy.

Nếu viết `format((String) item)`, kiểu biểu thức đối số trở thành `String`, từ đó có thể chọn overload nhận `String`. Phép ép kiểu có thể thất bại khi giá trị thực tế không phải chuỗi; không nên thêm ép kiểu chỉ để buộc một overload mà chưa có bảo đảm về dữ liệu.

Các phương thức trong bài là static. Không có cơ chế ghi đè phương thức instance để chuyển việc chọn overload sang thời gian chạy.

## 5. Null có thể làm lời gọi nhập nhằng

Nếu thêm dòng sau vào `main` của ví dụ:

```java
// System.out.println(format(null));
```

rồi bỏ dấu chú thích, lời gọi không biên dịch. `null` có thể phù hợp với nhiều tham số tham chiếu như `Integer`, `String` và `int[]`, nhưng các kiểu này không tạo ra một lựa chọn cụ thể nhất chung cho lời gọi.

Overload nhận `Object` không giải quyết được xung đột đó, vì một số ứng viên khác cụ thể hơn nó nhưng vẫn không so sánh được với nhau.

Có thể diễn đạt chủ đích rõ hơn khi dữ liệu thực sự có ý nghĩa:

```java
System.out.println(format((String) null));   // String: null
System.out.println(format((Integer) null));  // Integer: null
```

Ép `null` thành `int[]` sẽ chọn phương thức có tham số mảng, nhưng thân `format(int...)` trong ví dụ đọc `values.length` nên khi chạy sẽ gây `NullPointerException`. Chọn được overload không có nghĩa dữ liệu đã hợp lệ với hợp đồng của phương thức.

Trong API thực tế, nhiều overload nhận các kiểu tham chiếu không liên quan có thể làm cách dùng `null` khó hiểu. Tên phương thức diễn đạt rõ từng mục đích thường tốt hơn việc buộc người gọi nhớ nhiều phép ép kiểu.

## 6. Phương thức trong lớp có thể chặn đường tìm tên từ import

Xét chương trình cố ý không biên dịch sau:

```java
import static java.lang.Math.max;

class LocalNameConflict {
    static int max(String left, String right) {
        return left.compareTo(right);
    }

    static int calculate() {
        return max(1, 2); // Không tự ghép overload này với Math.max.
    }
}
```

Tên phương thức `max` đã có trong lớp hiện tại. Với lời gọi tên đơn giản ở đây, quá trình tìm phương thức hướng đến kiểu đang chứa lời gọi; nó không tự bổ sung mọi phương thức `Math.max` đã nhập khi `max(String, String)` không phù hợp.

Để gọi rõ phương thức thư viện, viết:

```java
return Math.max(1, 2);
```

Không nên học quy tắc này thành “phương thức cục bộ luôn được chọn”. Trong ví dụ, nó còn không nhận được các đối số `int`, nên kết quả là lỗi biên dịch. Điều cần hiểu là **phạm vi tìm kiếm được xác định trước khi chọn overload**.

Quy tắc tìm tên có thêm chi tiết với lớp bao ngoài và kế thừa; khi gặp trường hợp phức tạp, dùng tên kiểu chứa API để thể hiện chủ đích thường giúp việc đọc và sửa mã rõ ràng hơn.

## 7. Hai nguồn có cùng chữ ký

Nếu nhập hai phương thức static khác nhau với cùng chữ ký có thể áp dụng cho lời gọi, trình biên dịch không chọn theo thứ tự các dòng import.

Ví dụ hai import sau là khai báo hợp lệ, nhưng lời gọi bên dưới nhập nhằng:

```java
import static java.lang.Math.max;
import static java.lang.StrictMath.max;

// Trong một phương thức:
// int value = max(1, 2); // Nhập nhằng giữa Math.max và StrictMath.max.
```

Đổi vị trí hai dòng import không giải quyết được vấn đề. Muốn chọn nguồn, viết `Math.max(1, 2)` hoặc `StrictMath.max(1, 2)`, hoặc bỏ import không cần thiết.

Kiểu biến nhận kết quả cũng không phải công cụ để chọn nguồn trong ví dụ này:

```java
// long value = max(1, 2); // Vẫn không chỉ ra Math hay StrictMath.
```

Với các API generic và biểu thức đa kiểu, kiểu đích có thể tham gia suy luận kiểu theo quy tắc riêng. Điều đó không tạo quy tắc “chọn static import theo kiểu trả về” và không làm import có thứ tự ưu tiên từ trên xuống dưới.

## 8. Cách xử lý khi lỗi xuất hiện sau khi sửa import

1. Đọc tên đơn giản đang lỗi và xác định nó đang tìm phương thức trong lớp nào hay qua import.
2. Liệt kê chữ ký các ứng viên phù hợp; đừng chỉ đọc tên phương thức.
3. Kiểm tra kiểu khai báo của từng biểu thức đối số, đặc biệt kiểu bao và `null`.
4. Phân biệt lời gọi số tham số cố định với lời gọi cần đóng gói varargs.
5. Dùng tên kiểu chứa để chỉ rõ nguồn nếu mục đích là chọn thư viện.
6. Chỉ ép kiểu khi kiểu đó phản ánh hợp đồng dữ liệu thực tế.

Không sửa lỗi nhập nhằng bằng cách ngẫu nhiên đổi thứ tự import hoặc thay kiểu biến nhận. Những thay đổi đó không thể hiện rõ ý định API.

Static import có ích khi các tên ngắn dễ nhận biết. Khi có nhiều thư viện dùng những tên chung như `format`, `convert` hoặc `max`, giữ tiền tố kiểu có thể làm nguồn của lời gọi rõ hơn.

## 9. Tự kiểm tra

1. Import `Math.max` có chỉ nhập một overload cụ thể không?
2. Hai lớp có phương thức static cùng tên nhưng khác kiểu tham số có luôn xung đột không?
3. Trong ví dụ, vì sao biến `Object item = "java"` chọn `format(Object)`?
4. Đảo thứ tự import `Math.max` và `StrictMath.max` có chọn được nguồn ưu tiên không?
5. Nếu lớp có phương thức `max(String, String)`, lời gọi `max(1, 2)` có tự thử `Math.max` đã nhập không?

Đáp án:

1. Không; import theo tên, các overload truy cập được cùng tên có thể được xét.
2. Không; lời gọi có thể chọn được một ứng viên rõ ràng như trong chương trình.
3. Kiểu của biểu thức đối số tại thời điểm biên dịch là `Object`.
4. Không.
5. Không trong trường hợp đã minh họa; nên viết `Math.max(1, 2)` để chỉ rõ nguồn.

## Tài liệu đối chiếu

Xem [JLS 21 §7.5.3 — Single-Static-Import Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5.3), [§15.12.1 — Determine Type to Search](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.1) và [§15.12.2 — Determine Method Signature](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.12.2).
