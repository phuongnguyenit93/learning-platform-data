# Nhập một thành viên static cụ thể

Khi thường xuyên dùng một hằng số hoặc phương thức `static`, việc lặp tên lớp có thể làm biểu thức dài hơn. Khai báo nhập một thành viên tĩnh cụ thể (single static import) cho phép dùng tên ngắn của thành viên đó trong tệp mã nguồn.

Ví dụ, thay vì viết `Math.abs(-7)`, ta có thể nhập `abs` từ `Math` rồi viết `abs(-7)`. Thành viên vẫn thuộc lớp `Math`; import chỉ hỗ trợ cách viết tên trong mã nguồn.

## 1. Cú pháp và ý nghĩa từng phần

```java
import static java.lang.Math.abs;
```

Đọc từ trái sang phải:

| Thành phần | Ý nghĩa |
| --- | --- |
| `import static` | Khai báo nhập thành viên tĩnh |
| `java.lang.Math` | Tên đầy đủ của kiểu chứa thành viên |
| `abs` | Tên thành viên được nhập |
| `;` | Kết thúc khai báo |

Cấu trúc tổng quát:

```java
import static packageName.TypeName.memberName;
```

Đây là mẫu cú pháp, không phải một import có thể chép nguyên vào chương trình.

Với phương thức, chỉ ghi tên, không ghi danh sách tham số và không gọi phương thức tại dòng import:

```java
import static java.lang.Math.abs;      // Đúng.

// Các dòng dưới đây minh họa cú pháp không hợp lệ:
// import static java.lang.Math.abs();
// import static java.lang.Math.abs(int);
```

Khai báo `import static java.lang.Math.abs;` không nhập các tên khác như `max` hoặc `sqrt`. Nếu cần dùng tên ngắn của chúng, mỗi tên cần được nhập rõ ràng bằng một khai báo phù hợp.

## 2. Vị trí trong tệp mã nguồn

Nếu tệp có khai báo package, thứ tự là:

```java
package example.math;

import static java.lang.Math.abs;
import static java.lang.Math.PI;

public class CircleMath {
    public static double distance(double left, double right) {
        return abs(left - right);
    }

    public static double area(double radius) {
        return PI * radius * radius;
    }
}
```

Đoạn trên là một lớp tiện ích minh họa có package, không có `main`. Hai import nằm sau `package` và trước khai báo lớp. Không đặt import bên trong lớp hoặc phương thức.

Static import có phạm vi trong đơn vị biên dịch chứa nó, thường tương ứng với một tệp `.java`. Import ở một tệp không tự áp dụng cho tệp khác trong cùng package hoặc dự án.

Import thông thường và static import có thể cùng xuất hiện. Nhóm và sắp xếp chúng theo quy ước của dự án để người đọc dễ tìm nguồn của tên ngắn.

## 3. Nhập trường static

Một trường `static` truy cập được có thể được dùng theo tên đơn giản sau khi nhập:

```java
import static java.lang.Math.PI;

// Trong thân một phương thức:
double area = PI * 2.0 * 2.0;
```

Ở đây, `PI` là hằng số `public static final` của `Math`. Không tạo một biến `PI` mới và cũng không sao chép trường đó thành thành viên của lớp đang viết.

Static import không chỉ dành cho hằng số `final`. Nó có thể nhập trường `static` thay đổi được nếu quyền truy cập cho phép. Tuy nhiên, việc viết tên ngắn không làm thay đổi quy tắc cập nhật hoặc quyền truy cập của trường. Với trạng thái dùng chung có thể thay đổi, giữ rõ tên lớp đôi khi giúp người đọc thấy tác động tốt hơn.

## 4. Nhập tên phương thức static và overload

Với:

```java
import static java.lang.Math.abs;
```

có thể gọi cả:

```java
int count = abs(-7);
double distance = abs(-2.5);
```

Dù tên gọi là “nhập một thành viên”, một khai báo nhập **theo tên** có thể đưa vào nhiều phương thức overload truy cập được cùng tên. Nó không khóa lời gọi vào một chữ ký cụ thể như `abs(int)`.

Trình biên dịch vẫn chọn overload theo kiểu đối số và các quy tắc lời gọi phương thức của Java. Static import không thay đổi phép chuyển đổi kiểu, kết quả tính toán hoặc cách xử lý ngoại lệ của API được gọi.

Ví dụ `Math.abs(Integer.MIN_VALUE)` vẫn có hành vi của chính `Math.abs(int)`; bỏ tiền tố `Math.` không khắc phục các giới hạn biểu diễn số nguyên. Khi dùng một API, vẫn cần hiểu hợp đồng của API đó.

## 5. Enum constant và kiểu lồng static

Hằng enum là các trường tĩnh nên có thể nhập riêng:

```java
import static java.time.DayOfWeek.MONDAY;
```

Sau đó, trong ngữ cảnh phù hợp, có thể viết `MONDAY` thay cho `DayOfWeek.MONDAY`.

Một kiểu thành viên `static` cũng có thể được nhập. Ví dụ `Map.Entry` là một interface thành viên tĩnh của `Map`:

```java
import static java.util.Map.Entry;
```

Khi ấy, có thể khai báo `Entry<String, Integer>` trong tệp. Đây là nhập tên kiểu `Entry`, không nhập các phương thức instance như `getKey` hoặc `getValue`.

Với kiểu lồng, import kiểu thông thường như `import java.util.Map.Entry;` cũng là lựa chọn hợp lệ và thường diễn đạt mục đích trực tiếp hơn. Ví dụ static import ở đây giúp thấy phạm vi những loại thành viên mà cú pháp hỗ trợ.

## 6. Chương trình chạy hoàn chỉnh

Lưu thành `SingleStaticImportDemo.java`. Ví dụ dùng các API còn áp dụng trong Java hiện hành và chạy trên Java 17+.

```java
import static java.lang.Math.PI;
import static java.lang.Math.abs;
import static java.time.DayOfWeek.MONDAY;
import static java.util.Map.Entry;

import java.time.DayOfWeek;
import java.util.Map;

public class SingleStaticImportDemo {
    public static void main(String[] args) {
        int whole = abs(-7);
        double decimal = abs(-2.5);
        System.out.println("abs int: " + whole);
        System.out.println("abs double: " + decimal);
        System.out.println("PI greater than 3: " + (PI > 3));

        DayOfWeek next = MONDAY.plus(1);
        System.out.println("next day: " + next);

        Entry<String, Integer> entry = Map.entry("java", 21);
        System.out.println(entry.getKey() + "=" + entry.getValue());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 SingleStaticImportDemo.java
java SingleStaticImportDemo
```

Stdout:

```text
abs int: 7
abs double: 2.5
PI greater than 3: true
next day: TUESDAY
java=21
```

### Tại sao chương trình dùng được các tên ngắn?

- `abs` đến từ import tên phương thức của `Math`; hai lời gọi chọn overload khác nhau.
- `PI` đến từ import trường của `Math`.
- `MONDAY` đến từ import hằng enum của `DayOfWeek`.
- `Entry` đến từ import kiểu thành viên của `Map`.
- `DayOfWeek` và `Map` được dùng như tên kiểu nhờ các import thông thường.

Việc nhập thành viên không mặc nhiên nhập tên kiểu chứa nó. Chẳng hạn, chỉ nhập `MONDAY` chưa cho phép dùng tên đơn giản `DayOfWeek` trong một khai báo biến; dòng import kiểu riêng trong ví dụ giải quyết nhu cầu đó.

Với `Math`, tên kiểu có sẵn qua import ngầm từ `java.lang`, nhưng các thành viên `PI` và `abs` không tự được nhập thành tên đơn giản. Đây là lý do static import vẫn có tác dụng dù `Math` nằm trong `java.lang`.

## 7. Các điều kiện và lỗi thường gặp

### Thành viên phải là static và truy cập được

Import không vượt qua kiểm soát truy cập. Không thể nhập một thành viên `private` của lớp khác chỉ để bỏ qua giới hạn của nó. Kiểu chứa thành viên và chính thành viên đều phải truy cập được từ nơi sử dụng.

Một phương thức instance cũng không trở thành static nhờ import:

```java
// Cố ý minh họa một import không hợp lệ:
// import static java.lang.String.length;
```

`String.length()` là phương thức của một đối tượng chuỗi. Muốn gọi nó, cần một giá trị chuỗi như `"java".length()`, không dùng static import để thay thế đối tượng.

### Import tên thành viên không nhập mọi thứ bên trong nó

Ví dụ `import static java.lang.System.out;` cho phép viết `out.println("hello")`. Thành viên được nhập là trường `out`; `println` vẫn là phương thức instance được gọi trên đối tượng mà trường đó tham chiếu.

Không thể suy luận thành `println("hello")` chỉ vì đã nhập `out`.

### Tên ngắn phải giải quyết được rõ ràng

Nếu đưa nhiều thành viên cùng tên từ các kiểu khác nhau vào cùng tệp, cách dùng tên đơn giản có thể gây xung đột hoặc nhập nhằng. Ví dụ nhập cả `Integer.MAX_VALUE` và `Long.MAX_VALUE` rồi dùng `MAX_VALUE` sẽ không thể hiện rõ trường nào cần dùng.

Khi tên ngắn không còn rõ nghĩa, hãy dùng tên có kiểu chứa như `Integer.MAX_VALUE` hoặc bỏ import không cần thiết. Không cần cố dùng static import cho mọi lời gọi.

### Import không thực thi phương thức

Dòng `import static ...;` hỗ trợ phân giải tên lúc biên dịch; nó không phải một câu lệnh gọi và không khiến một phương thức được thực thi chỉ vì xuất hiện ở đầu tệp. Việc thực thi vẫn diễn ra ở chỗ mã thực sự gọi hoặc truy cập thành viên theo các quy tắc Java tương ứng.

## 8. Khi nào nên dùng?

Nhập riêng một vài tên quen thuộc thường có ích trong biểu thức toán học hoặc mã kiểm thử: nguồn của các tên dễ nhận ra, còn phần logic chính gọn hơn.

Nếu tên quá chung như `get`, `create`, `run` hoặc `value`, giữ tiền tố kiểu có thể giúp hiểu mã nhanh hơn. Hãy ưu tiên tính dễ đọc và quy ước hiện có của dự án.

Một cách kiểm tra đơn giản là đọc riêng thân phương thức: người đọc có nhận ra tên đó biểu thị việc gì và tìm được nguồn của nó nhanh không? Nếu không, dạng có tên kiểu thường phù hợp hơn.

## 9. Tự kiểm tra

1. Sau `import static java.lang.Math.abs;`, có gọi được `abs(-2.5)` không?
2. Muốn chỉ định `abs(int)` ngay trong dòng import thì viết thế nào?
3. Chỉ nhập `MONDAY` có tự nhập tên kiểu `DayOfWeek` không?
4. Static import có làm thành viên private của lớp khác truy cập được không?
5. Sau khi nhập `System.out`, có được gọi trực tiếp `println("x")` không?

Đáp án:

1. Có; import theo tên đưa các overload `abs` truy cập được vào quá trình phân giải lời gọi.
2. Không có cú pháp đó; import chỉ ghi tên `abs`, còn chữ ký được chọn tại lời gọi.
3. Không; muốn dùng tên kiểu ngắn thì phải có cách phân giải tên kiểu thích hợp, chẳng hạn import kiểu.
4. Không.
5. Không; có thể viết `out.println("x")`, vì thứ được nhập là trường `out`.

## Tài liệu đối chiếu

Cú pháp và phạm vi được quy định tại [JLS 21 §7.5.3 — Single-Static-Import Declarations](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5.3). Xem thêm [Math](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html) và khai báo `public static interface` của [Map.Entry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.Entry.html).
