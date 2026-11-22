# `static import` trong Java: tiện ích và nguy cơ giảm khả năng đọc

Khi sử dụng thành viên `static` của một lớp khác, Java thông thường yêu cầu nêu **tên kiểu** trước thành viên, chẳng hạn `Math.PI`, `Math.max(3, 5)` hoặc `Collections.emptyList()`. **Static import** cho phép đưa một hoặc nhiều tên thành viên static **có thể truy cập** vào phạm vi tra cứu tên của đơn vị biên dịch, nhờ đó trong những ngữ cảnh thích hợp có thể viết `PI`, `max(3, 5)` hoặc `emptyList()` mà không lặp lại tên kiểu.

Cú pháp này rất hữu ích cho công thức toán, mã kiểm thử, hằng số có ý nghĩa rõ và một số hàm tiện ích thường xuyên sử dụng. Tuy nhiên, nếu dùng tràn lan, **người đọc khó nhìn ra một tên bắt nguồn từ đâu**, dễ gặp nhầm lẫn với tên trong lớp hiện tại hoặc các static import khác. Vấn đề không nằm ở hiệu năng của lệnh import, mà ở **ngữ nghĩa và khả năng bảo trì của mã nguồn**.

Bài này thuộc Java Core — *class-object*, nhóm **Thành viên static**. Mục tiêu là hiểu đúng static import, phân biệt nó với import thông thường và với bản thân `static`, biết cách xử lý trùng tên và chọn quy tắc sử dụng hợp lý. Các chương trình độc lập sử dụng **Java 17 trở lên**, kèm lệnh chạy và kết quả có thể đối chiếu.

## 1. Từ truy cập thành viên static tới static import

Một lớp có thể công bố trường và phương thức static:

~~~java
double area = Math.PI * Math.pow(2.0, 2.0);
int larger = Math.max(3, 5);
~~~

Đây là hai câu lệnh minh họa đặt trong một phương thức. `Math` là lớp `java.lang.Math`, `PI` là một trường static, còn `pow` và `max` là những phương thức static của lớp đó.

Có thể thay bằng:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
import static java.lang.Math.pow;
~~~

Các khai báo import này phải được đặt tại **vùng import của tệp Java**, sau khai báo `package` nếu có và trước các khai báo lớp ở cấp cao nhất. Sau đó, ở phần thân lớp/phương thức, có thể dùng:

~~~java
double area = PI * pow(2.0, 2.0);
int larger = max(3, 5);
~~~

Hai cách tính ra cùng giá trị. **Static import không sao chép field hoặc method** vào lớp của bạn; nó chỉ giúp compiler phân giải **tên đơn giản** về thành viên tương ứng.

Điều kiện quan trọng: thành viên phải thực sự là thành viên static phù hợp và **có thể truy cập** từ nơi sử dụng. Static import **không bỏ qua** `private`, `protected` hoặc các quy tắc truy cập package/module của Java.

## 2. Hai dạng cú pháp của static import

Java hỗ trợ hai dạng chính:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
~~~

Dạng **single-static-import declaration** nhập tên của một thành viên static xác định từ một kiểu. Với phương thức overload như `Math.max`, tên `max` được dùng để tìm các overload static thích hợp; nó không nhất thiết chỉ mang một chữ ký tham số.

Dạng thứ hai:

~~~java
import static java.lang.Math.*;
~~~

là **static-import-on-demand declaration**. Nó cho phép tra cứu theo tên những thành viên static có thể truy cập của `Math`, khi cần. Dấu `*` ở đây **không có nghĩa mọi lớp trong package `java.lang`**, cũng không nhập các phương thức instance thông thường của `Math`.

| Cú pháp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `import java.util.Collections;` | Nhập **tên lớp** `Collections` | `Collections.emptyList()` |
| `import static java.util.Collections.emptyList;` | Nhập tên **static method** `emptyList` | `emptyList()` |
| `import static java.lang.Math.PI;` | Nhập tên **static field** `PI` | `PI * radius * radius` |
| `import static java.lang.Math.*;` | Tra cứu các thành viên static truy cập được của `Math` theo nhu cầu | `sqrt(9)`, `max(2,3)` |
| `import java.lang.Math.*;` | **Không hợp lệ** theo ý định nhập thành viên như static import | Không dùng thay cho `import static` |

Một tệp Java có thể dùng **cả import thông thường và static import**. Ví dụ, `import java.util.List;` giúp viết tên kiểu `List`, còn `import static java.util.List.of;` giúp gọi phương thức static `of(...)` theo tên ngắn.

## 3. Chương trình hoàn chỉnh: nhập chọn lọc thành viên `Math`

Tạo tệp **`StaticImportBasicDemo.java`**:

~~~java
import static java.lang.Math.PI;
import static java.lang.Math.max;
import static java.lang.Math.pow;
import static java.lang.Math.sqrt;
import static java.lang.System.out;

import java.util.Locale;

public class StaticImportBasicDemo {
    public static void main(String[] args) {
        double radius = 2.0;
        double area = PI * pow(radius, 2);

        out.printf(Locale.ROOT, "area=%.2f%n", area);
        out.println("sqrt=" + sqrt(81));
        out.println("max=" + max(4, 9));

        // Cách viết đầy đủ luôn vẫn hợp lệ.
        out.println("qualified=" + Math.max(4, 9));
    }
}
~~~

Chạy trong thư mục chứa tệp:

~~~bash
javac -encoding UTF-8 StaticImportBasicDemo.java
java StaticImportBasicDemo
~~~

**Stdout:**

~~~text
area=12.57
sqrt=9.0
max=9
qualified=9
~~~

### Những gì đang diễn ra

- `PI` là `Math.PI`, và `pow(radius,2)` là `Math.pow(radius,2)`.
- `sqrt(81)` trả một `double`, được nối thành chuỗi `9.0`.
- `max(4,9)` chọn overload xử lý hai giá trị `int`, trả 9.
- `out` là trường `public static final PrintStream out` của `System`; `out.println(...)` tương đương truy cập `System.out.println(...)`.
- `Locale.ROOT` giúp việc format phần thập phân `12.57` không phụ thuộc locale mặc định của máy chạy.
- Dù đã có static import `max`, code vẫn **có thể** viết `Math.max(...)`. Import không xóa hoặc cấm tên đầy đủ.

Ví dụ này dùng static import chọn lọc để cho thấy cơ chế. Trong ứng dụng thật, nhiều nhóm sẽ **không static import `System.out`** vì `System.out.println` vốn rất dễ nhận diện, còn `out.println` có thể làm người đọc phải tìm nguồn của `out`. Đây chính là sự đánh đổi về khả năng đọc của static import.

## 4. `static import` không giống khai báo `static`

Cần phân biệt hai câu hỏi:

1. **`static` tại nơi khai báo thành viên:** quyết định thành viên thuộc kiểu/lớp thay vì từng instance, theo ngữ nghĩa Java.
2. **`import static` tại đầu tệp sử dụng:** quyết định có thể gọi tên thành viên static của **kiểu khác** theo dạng ngắn hay không.

Ví dụ:

~~~java
class Calculations {
    static int twice(int number) {
        return Math.multiplyExact(number, 2);
    }

    int instanceValue() {
        return 7;
    }
}
~~~

Đây là một lớp minh họa hợp lệ. Trong một tệp khác có `package`/quyền truy cập phù hợp, có thể static import `twice` nếu phương thức được công bố đến nơi gọi. Không thể dùng static import để tự biến `instanceValue()` thành static method.

Đối với ví dụ class `Calculations` ở trên, `twice` đang package-private. Nếu client ở **package khác**, cần công bố phương thức `public static` và cho phép truy cập tới kiểu chứa, thay vì trông chờ static import mở quyền.

Static import cũng **không khởi tạo object** cho bạn. Nó chỉ nhập tên của thành viên có thể dùng mà không cần một receiver instance. Với instance method, caller vẫn cần object, ví dụ `text.trim()` chứ không thể dựa vào `import static java.lang.String.trim;`.

## 5. Khi nào static import cải thiện khả năng đọc?

Một quy tắc thực dụng: **tên ngắn nên tự mang đủ ý nghĩa trong ngữ cảnh dùng**.

Ví dụ với các hàm toán quen thuộc:

~~~java
double distance = sqrt(pow(dx, 2) + pow(dy, 2));
~~~

Đây là biểu thức minh họa, giả định tệp có static import `sqrt` và `pow`, còn `dx`, `dy` là các giá trị số trong phạm vi. Nếu tác giả đang viết hàng loạt công thức toán, các tên `sqrt`, `pow`, `sin`, `cos` có thể làm biểu thức gọn hơn và gần cách đọc công thức.

Tuy nhiên:

~~~java
double distance = Math.sqrt(Math.pow(dx, 2) + Math.pow(dy, 2));
~~~

cũng rõ ràng, và còn cho thấy ngay **nguồn hàm**. Với người mới đọc code hoặc khi trong dự án tồn tại nhiều lớp tiện ích có `sqrt`/`pow` riêng, dạng có `Math.` có thể dễ tra cứu hơn.

Static import phù hợp khi:

- Có nhiều lời gọi tới **một tập nhỏ static members** và tên thành viên quen thuộc.
- Ngữ cảnh khiến nguồn tên **rõ ràng** mà không cần nhảy lên đầu tệp.
- Việc lặp tên lớp che khuất ý chính của biểu thức.
- Quy ước nhóm đã xác định rõ những static imports được phép ưu tiên.

Không nên đánh giá “gọn hơn” chỉ bằng số ký tự. **Gọn mà mơ hồ** có thể tốn nhiều thời gian debug hơn việc viết đầy đủ `Math.max` hoặc `Collections.emptyList`.

## 6. Static import trong mã xử lý collection và stream

Thư viện chuẩn có nhiều static utility methods thích hợp để import chọn lọc. Tạo tệp **`CollectionStaticImportDemo.java`**:

~~~java
import static java.util.Comparator.comparingInt;
import static java.util.Collections.reverseOrder;
import static java.util.stream.Collectors.joining;

import java.util.List;

public class CollectionStaticImportDemo {
    public static void main(String[] args) {
        List<String> words = List.of("Java", "Go", "Kotlin");

        String byLength = words.stream()
                .sorted(comparingInt(String::length))
                .collect(joining(", "));

        String descending = words.stream()
                .sorted(reverseOrder())
                .collect(joining(", "));

        System.out.println("length=" + byLength);
        System.out.println("reverse=" + descending);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 CollectionStaticImportDemo.java
java CollectionStaticImportDemo
~~~

**Stdout:**

~~~text
length=Go, Java, Kotlin
reverse=Kotlin, Java, Go
~~~

Giải thích:

- `comparingInt(String::length)` trả `Comparator<String>` dựa trên độ dài. Các chuỗi dài 2, 4, 6 được sắp xếp lần lượt.
- `joining(", ")` là collector trả về để nối các chuỗi với dấu phẩy và khoảng trắng.
- `reverseOrder()` của `Collections` trả comparator theo **thứ tự tự nhiên đảo ngược** của `String`, nên trong bộ dữ liệu này là `Kotlin, Java, Go`.

Các tên `comparingInt`, `joining` có ý nghĩa khá rõ trong chuỗi thao tác stream. Nhưng nếu một tệp chỉ có **một lần gọi**, cách viết `Comparator.comparingInt` hoặc `Collectors.joining` thường cũng đủ ngắn.

**Lưu ý:** `Collections.reverseOrder()` tạo comparator; nó không tự đảo tại chỗ danh sách `words`. Trong ví dụ, việc sắp xếp chạy trên stream và tạo chuỗi kết quả. Nếu dùng `Collections.reverse(list)`, hành vi khác: nó thay đổi thứ tự list mutable tại chỗ.

## 7. Static import trên hằng số và enum constants

Static import có thể đưa những **hằng số static** vào phạm vi tên:

~~~java
import static java.time.DayOfWeek.MONDAY;
import static java.time.DayOfWeek.FRIDAY;
~~~

Với các dòng import này ở đầu tệp, đoạn sử dụng:

~~~java
java.time.DayOfWeek first = MONDAY;
boolean isFriday = first == FRIDAY;
~~~

có ý nghĩa rõ khi ngữ cảnh đang nói về **các ngày trong tuần**. `MONDAY` và `FRIDAY` là các enum constants thuộc `DayOfWeek`.

Ví dụ chạy độc lập **`EnumStaticImportDemo.java`**:

~~~java
import static java.time.DayOfWeek.FRIDAY;
import static java.time.DayOfWeek.MONDAY;

import java.time.DayOfWeek;

public class EnumStaticImportDemo {
    public static void main(String[] args) {
        DayOfWeek start = MONDAY;
        DayOfWeek end = FRIDAY;

        System.out.println("start=" + start);
        System.out.println("end=" + end);
        System.out.println("same=" + (start == end));
        System.out.println("end number=" + end.getValue());
    }
}
~~~

~~~bash
javac EnumStaticImportDemo.java
java EnumStaticImportDemo
~~~

Stdout:

~~~text
start=MONDAY
end=FRIDAY
same=false
end number=5
~~~

Enum constants là những đối tượng duy nhất theo mỗi constant trong enum, nên `==` là cách so sánh identity phù hợp với cùng enum type.

### Hạn chế khi nhập hằng số quá nhiều

Nếu viết:

~~~java
import static java.time.DayOfWeek.*;
~~~

thì những tên như `MONDAY`, `TUESDAY`, `SUNDAY` được đưa vào khả năng tra cứu. Với tệp chỉ xử lý lịch, việc này có thể hợp lý; ở tệp đa chức năng, các tên ngắn có thể thiếu ngữ cảnh. Viết `DayOfWeek.MONDAY` đôi khi giúp tránh phải đoán `MONDAY` thuộc enum nào.

Một điểm độc lập: trong `switch` trên enum ở Java 17, case labels dùng **tên enum constant không có tên kiểu đứng trước** theo quy tắc switch enum; điều đó **không phải** lợi ích do static import tạo ra. Đừng thêm static import chỉ để biện minh cho cú pháp `case MONDAY:`.

## 8. Static import một nested type

Không chỉ field và method, static import còn có thể nhập tên của **kiểu thành viên static có thể truy cập**, ví dụ kiểu `Map.Entry`:

~~~java
import static java.util.Map.Entry;
~~~

`Entry` là một interface thành viên của `Map`, và member type trong interface được khai báo ngầm định `public static`. Sau import, có thể nêu tên `Entry` mà không viết `Map.Entry` trong những chỗ sử dụng kiểu thích hợp.

Tạo tệp **`StaticNestedTypeImportDemo.java`**:

~~~java
import static java.util.Map.Entry;

import java.util.Map;

public class StaticNestedTypeImportDemo {
    public static void main(String[] args) {
        Entry<String, Integer> entry = Map.entry("An", 7);

        System.out.println("key=" + entry.getKey());
        System.out.println("value=" + entry.getValue());
    }
}
~~~

Chạy:

~~~bash
javac StaticNestedTypeImportDemo.java
java StaticNestedTypeImportDemo
~~~

Stdout:

~~~text
key=An
value=7
~~~

Cách phổ biến và có thể dễ nhận diện hơn là import kiểu bằng:

~~~java
import java.util.Map.Entry;
~~~

Cả hai có thể làm tên `Entry` dùng được theo quy tắc riêng của từng dạng import. Với **kiểu thành viên lồng**, hãy ưu tiên cách nào bộc lộ ngữ nghĩa tốt và nhất quán trong dự án. Static import nested type là tính năng hợp lệ nhưng không phải lúc nào cũng cần dùng.

Đừng nhầm **static nested class** với **top-level class**: `import static some.package.*;` không dùng để nhập toàn bộ lớp của package. Dấu `*` trong static import vận hành trên **static members của một kiểu cụ thể**.

## 9. Dùng static import với lớp tiện ích do dự án định nghĩa

Muốn static import một thành viên của **lớp do mình viết** từ package khác, lớp và thành viên cần có quyền truy cập phù hợp. Chúng ta sẽ tạo cấu trúc thư mục:

~~~text
src/
  com/
    example/
      shared/
        Numbers.java
      app/
        PackageStaticImportDemo.java
~~~

Tệp thứ nhất: **`src/com/example/shared/Numbers.java`**

~~~java
package com.example.shared;

public final class Numbers {
    public static final int LIMIT = 10;

    private Numbers() {
    }

    public static int capped(int value) {
        return Math.min(LIMIT, Math.max(0, value));
    }
}
~~~

Tệp thứ hai: **`src/com/example/app/PackageStaticImportDemo.java`**

~~~java
package com.example.app;

import static com.example.shared.Numbers.LIMIT;
import static com.example.shared.Numbers.capped;

public class PackageStaticImportDemo {
    public static void main(String[] args) {
        System.out.println("limit=" + LIMIT);
        System.out.println("low=" + capped(-3));
        System.out.println("high=" + capped(18));
        System.out.println("qualified="
                + com.example.shared.Numbers.capped(4));
    }
}
~~~

Từ thư mục **chứa `src`**, chạy:

~~~bash
javac -encoding UTF-8 -d out src/com/example/shared/Numbers.java src/com/example/app/PackageStaticImportDemo.java
java -cp out com.example.app.PackageStaticImportDemo
~~~

**Stdout:**

~~~text
limit=10
low=0
high=10
qualified=4
~~~

Giải thích:

- `Numbers` là `public final class` thuộc package `com.example.shared`.
- `LIMIT` và `capped` là thành viên `public static`, nên tệp thuộc `com.example.app` có thể nhập và sử dụng.
- `private Numbers()` ngăn việc tạo instance `Numbers` từ bên ngoài; ta không cần instance vì các tiện ích đều static.
- `capped` giữ giá trị trong khoảng `0..LIMIT` bằng `Math.min` và `Math.max`.
- Việc viết tên đầy đủ `com.example.shared.Numbers.capped(4)` vẫn hợp lệ dù đã static import.
- Khi có khai báo `package`, lệnh `java` chạy **tên lớp đủ package**, không chỉ tên file.

**Lưu ý về unnamed package:** không nên dựa vào việc static import một lớp khai báo trong package mặc định (không có tên), vì import cần tên kiểu phù hợp và Java không hỗ trợ nhập kiểu từ unnamed package theo cách dùng với package được đặt tên. Dự án có nhiều tệp nên đặt package rõ ràng.

## 10. Static import không vượt qua phạm vi truy cập

Xem lớp:

~~~java
package com.example.shared;

public final class SecretNumbers {
    private static final int INTERNAL = 7;
    static final int PACKAGE_ONLY = 8;
    public static final int PUBLIC_VALUE = 9;

    private SecretNumbers() {
    }
}
~~~

Đây là lớp minh họa có thể lưu riêng thành `SecretNumbers.java`, không có `main`. Một tệp ở package **khác** có thể static import `PUBLIC_VALUE`, nhưng:

~~~java
// Các dòng sau nếu được dùng làm import trong package khác
// sẽ không cấp quyền truy cập tới thành viên không public.
// import static com.example.shared.SecretNumbers.INTERNAL;
// import static com.example.shared.SecretNumbers.PACKAGE_ONLY;
~~~

Hai dòng đã comment là **ví dụ không hợp lệ có chủ đích**, vì `INTERNAL` là `private` còn `PACKAGE_ONLY` có mức truy cập package-private. Static import không làm các thành viên ấy trở thành public.

Ngay cả khi dùng `import static com.example.shared.SecretNumbers.*;`, các thành viên private hoặc package-private không truy cập được vẫn **không trở nên có thể sử dụng** từ package khác.

Nếu một helper phải là chi tiết triển khai nội bộ, nên giữ nó private/package-private theo kiến trúc dự án. Đừng nới quyền chỉ để một static import có thể biên dịch, trừ khi API thực sự cần công bố thành viên đó.

## 11. Rủi ro thứ nhất: tên ngắn nhưng mất nguồn gốc

Xét một hàm `normalize` trong đoạn mã:

~~~java
String result = normalize(input);
~~~

Đây là dòng minh họa trong một phương thức có `input` kiểu phù hợp. Người đọc chưa biết:

- `normalize` là phương thức của lớp hiện tại hay một **static method được import**?
- Nếu là static import, nó thuộc `TextUtils`, `PathUtils` hay một kiểu tiện ích khác?
- Nó chỉ tính kết quả mới hay còn sửa trạng thái khác?
- Nó có quy tắc chuẩn hóa nào, có thể ném exception không?

Nếu viết:

~~~java
String result = TextNormalizer.normalize(input);
~~~

thì nguồn gốc được công bố ngay tại chỗ sử dụng. Với thao tác nghiệp vụ ít gặp hoặc có tác dụng phụ, tên kiểu làm code dễ đọc hơn nhiều so với chỉ `normalize(input)`.

Tất nhiên, nếu dự án có **một tên rất chuẩn** và ai cũng biết cách dùng trong module đó, static import có thể vẫn rõ. Tiêu chí là **khả năng hiểu ở vị trí sử dụng**, không chỉ số dòng import.

### `System.out` là ví dụ của đánh đổi này

Viết `out.println(...)` ngắn hơn `System.out.println(...)`, nhưng `out` là tên rất chung; trong một class cũng có thể có biến tên `out` mang ý nghĩa khác. Vì vậy việc static import `System.out` để tiết kiệm vài ký tự thường **không mang lại lợi ích rõ rệt** cho code sản xuất.

## 12. Rủi ro thứ hai: hai nguồn có thành viên cùng tên

Ví dụ `Integer` và `Long` đều công bố hằng `MAX_VALUE`. Nếu dùng static import on-demand từ cả hai:

~~~java
import static java.lang.Integer.*;
import static java.lang.Long.*;
~~~

và sau đó viết:

~~~java
// System.out.println(MAX_VALUE); // Lỗi: tên MAX_VALUE mơ hồ.
~~~

thì compiler không có một lựa chọn duy nhất giữa `Integer.MAX_VALUE` và `Long.MAX_VALUE` trong ngữ cảnh này.

Đoạn minh họa sau là **chương trình hoàn chỉnh** **`StaticImportAmbiguityDemo.java`** cho thấy cách khắc phục bằng qualification:

~~~java
import static java.lang.Integer.*;
import static java.lang.Long.*;

public class StaticImportAmbiguityDemo {
    public static void main(String[] args) {
        // System.out.println(MAX_VALUE); // Nếu bỏ comment sẽ mơ hồ.

        System.out.println("int max=" + Integer.MAX_VALUE);
        System.out.println("long max=" + Long.MAX_VALUE);
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac StaticImportAmbiguityDemo.java
java StaticImportAmbiguityDemo
~~~

**Stdout:**

~~~text
int max=2147483647
long max=9223372036854775807
~~~

Bài học không phải là mọi static import chứa tên trùng đều không thể khai báo trong một tệp. **Một lỗi trùng tên có thể chỉ xuất hiện khi sử dụng một tên đơn giản** trong ngữ cảnh không phân giải được. Dùng tên đủ kiểu là cách giải quyết rõ ràng và ổn định.

Với các phương thức overload từ nhiều nguồn, quy tắc chọn method có thể phức tạp hơn: compiler có thể tìm được overload phù hợp hoặc báo mơ hồ tùy danh sách tham số, nguồn khai báo và phạm vi. Đừng tự giả định “nhập sau sẽ ghi đè nhập trước”: **Java không lựa chọn static import dựa trên thứ tự dòng import**.

## 13. Một số quy tắc giải quyết tên cần nhớ

Việc phân giải một tên đơn giản trong Java tuân theo những quy tắc của JLS về phạm vi, khai báo và import. Ở cấp học này, nên ghi nhớ:

1. **Khai báo gần nơi dùng có thể che tên được import.** Nếu một biến cục bộ đang mang tên `PI`, viết `PI` trong phạm vi đó có thể đọc biến cục bộ thay vì `Math.PI`.
2. **Các thành viên của lớp hiện tại có thể được ưu tiên hơn tên nhập qua static import** trong những trường hợp quy tắc scope và method resolution quy định. Đừng suy rằng imported `max` nhất định là `Math.max` nếu trong lớp hiện tại cũng có `max`.
3. **Các nhập theo tên cụ thể và nhập on-demand có quy tắc phân giải khác nhau.** Không nên trông chờ vị trí của dòng import quyết định kết quả.
4. **Hai static imports on-demand có thành viên cùng tên** có thể làm tên đó trở nên mơ hồ khi sử dụng.
5. **Tên đầy đủ qua kiểu** như `Math.PI` hoặc `Long.MAX_VALUE` thường cho biết rõ loại thành viên cần dùng và là cách giải quyết dễ review.
6. **Import không làm bỏ qua quyền truy cập** hoặc thay đổi chữ ký phương thức, overload, static type của biểu thức.

Ví dụ về local variable che tên một hằng đã static import:

~~~java
import static java.lang.Math.PI;

public class ShadowStaticImportDemo {
    public static void main(String[] args) {
        double PI = 3.0;
        System.out.println("local=" + PI);
        System.out.println("math=" + Math.PI);
    }
}
~~~

Lệnh:

~~~bash
javac ShadowStaticImportDemo.java
java ShadowStaticImportDemo
~~~

Stdout:

~~~text
local=3.0
math=3.141592653589793
~~~

Chương trình này chứng minh **một import không buộc mọi lần dùng `PI` đều trỏ về `Math.PI`**. Cùng một tên đơn giản có thể diễn đạt ý nghĩa khác do phạm vi khai báo. Vì vậy tên đủ kiểu thường thích hợp khi cần loại bỏ hiểu nhầm.

## 14. Import on-demand `*` và chi phí đọc mã

Dạng:

~~~java
import static java.lang.Math.*;
~~~

ngắn hơn nhiều import riêng khi dùng hàng loạt hàm `Math`. Nó cũng không tạo phép toán runtime để “nạp mọi hàm” vào một object; import chủ yếu phục vụ **phân giải tên ở compile time**.

Nhưng import on-demand có những đánh đổi:

- Người đọc không thấy ngay trong phần import **tên cụ thể nào được sử dụng**.
- Khi một static member mới xuất hiện trong API hoặc thêm import khác, có thể phát sinh **trùng tên** tại vị trí dùng.
- Công cụ review hoặc tra cứu có thể cần tìm thêm để biết một lời gọi ngắn là của lớp nào.
- Đối với hằng số ngắn, `*` có thể đưa nhiều tên phổ biến vào phạm vi tra cứu, tăng nguy cơ shadowing hoặc ambiguity.

**Không nên nói rằng import on-demand làm JVM tải mọi thành viên static vào RAM khi chương trình chạy.** Nó không phải vòng lặp hoặc lời gọi method; việc tải/khởi tạo lớp tuân các quy tắc riêng, không đơn giản xảy ra chỉ vì khai báo import.

Trong codebase lớn, **single static imports** thường là mặc định an toàn hơn. On-demand có thể hợp lý khi thật sự có nhiều tên static rõ nghĩa của **một kiểu cụ thể** và nhóm nhất quán về quy ước.

## 15. Static import và Java `enum` / kiểm thử

Trong mã kiểm thử, có nhiều lời gọi xác nhận như `assertEquals`, `assertTrue`, `assertThrows`. Static import thường giúp biểu thức kiểm thử tập trung vào **điều được kiểm tra**, ví dụ khi công cụ test cung cấp các phương thức này dưới dạng `static`.

Minh họa **ý tưởng API của một thư viện kiểm thử**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
~~~

Đây **không phải ví dụ biên dịch với chỉ JDK 17**: các kiểu trong package `org.junit.jupiter.api` thuộc thư viện JUnit Jupiter cần thêm dependency và cấu hình test tương ứng. Mục đích là minh họa một tình huống thực tế mà static import được dùng phổ biến.

Khi tên `assertEquals` đã rất quen trong tệp test, cách viết:

~~~java
assertEquals(5, actual);
assertTrue(isValid);
~~~

thường dễ hiểu. Ngược lại, nếu dự án có nhiều thư viện assertion định nghĩa các hàm cùng tên, việc import ồ ạt có thể khiến overload hoặc thông báo lỗi trở nên khó phân tích.

Ngoài test, enum constants `MONDAY`, `FRIDAY` có thể được static import khi một thuật toán thực sự xoay quanh **một enum cụ thể**. Không cần áp dụng giống nhau cho mọi loại hằng số trong dự án.

## 16. Tránh static import những helper nghiệp vụ mơ hồ

Nếu một dự án có các lớp:

~~~text
PriceRules.calculate(...)
TaxRules.calculate(...)
ShippingRules.calculate(...)
~~~

thì static import các `calculate` từ nhiều nguồn có thể làm lời gọi `calculate(order)` khó hiểu: đang tính giá, thuế hay phí vận chuyển?

Ngay cả khi compiler chọn được một overload duy nhất, người đọc vẫn phải tự dò lại import để biết **quy tắc nghiệp vụ nào đã được gọi**. Tên kiểu ở dạng `TaxRules.calculate(order)` là thông tin có giá trị, không đơn thuần là phần ký tự thừa.

Một gợi ý:

| Tình huống | Thường nên viết |
| --- | --- |
| Công thức toán dài, dùng vài hàm `Math` quen thuộc | Có thể static import chọn lọc `sqrt`, `pow` |
| Kiểm thử với assertion API nhất quán | Static import những assertion cần dùng |
| Một hằng enum xuất hiện nhiều lần trong hàm chuyên biệt | Có thể static import enum constant |
| Helper domain mang tên chung `calculate`, `validate`, `parse` | Ưu tiên `TypeName.method(...)` |
| Hằng số `MAX_VALUE`, `DEFAULT`, `LIMIT` từ nhiều nơi | Ưu tiên `TypeName.CONSTANT` |
| Một lời gọi tiện ích duy nhất trong cả file | Thường viết đủ tên kiểu |
| Nhiều thư viện có method cùng tên | Giữ qualifier để tránh ambiguous/static imports khó theo dõi |

Điều này đặc biệt quan trọng ở module có logic bảo mật, tiền bạc hoặc trạng thái: **thấy rõ nguồn quyết định** thường có giá trị hơn vài ký tự tiết kiệm được.

## 17. Code review: quyết định dùng hay bỏ static import

Khi review một static import, đặt những câu hỏi thực tế:

1. **Tên ngắn có rõ nghĩa ngay tại chỗ sử dụng không?** `PI` trong công thức toán có thể rõ, `process` thì không.
2. **Nguồn thành viên có quan trọng về nghiệp vụ không?** Nếu có, giữ `TypeName.`.
3. **Được dùng bao nhiêu lần?** Một lần dùng thường chưa đáng mất ngữ cảnh.
4. **Có nguy cơ tên trùng với local/member/import khác không?** Kiểm tra cả trường và phương thức.
5. **Các overload có dễ hiểu không?** Nhiều nguồn cùng nhập method tên ngắn có thể làm kết quả phân giải khó dự đoán.
6. **Có thể thay bằng ordinary import của lớp không?** `Math.max` đôi khi là phương án cân bằng hơn.
7. **Import có đang nới API vô ích không?** Đừng chuyển helper `private` thành public chỉ vì muốn static import.
8. **Công cụ formatter/IDE có đổi từ explicit sang wildcard không?** Nếu có, cấu hình style cần nhất quán.
9. **Người mới vào dự án có thể lần ra khai báo dễ dàng không?** Nếu khó, đổi tên/giữ qualifier.
10. **Có quy tắc style chính thức của nhóm không?** Nên áp dụng ổn định trên cả codebase.

Một static import dễ đọc là import mà khi bỏ tên lớp, **ý nghĩa biểu thức vẫn hiển nhiên**. Nếu phải liên tục tìm trên đầu file để giải mã, nó có thể gây hại hơn lợi.

## 18. Các lỗi biên dịch thường gặp

| Lỗi | Nguyên nhân | Hướng sửa |
| --- | --- | --- |
| Viết `import Math.PI;` | Không đúng cú pháp import thành viên static | `import static java.lang.Math.PI;` |
| Viết `import static java.lang.Math;` | Không có tên thành viên sau tên kiểu | Chọn `Math.PI`, `Math.max` hoặc `Math.*` |
| Viết static import bên trong thân class/method | Import phải ở vùng import của compilation unit | Di chuyển lên đầu tệp, sau `package` |
| Import một instance method như `String.trim` | Method không phải static | Gọi qua object, ví dụ `text.trim()` |
| Static import private member từ package khác | Import không cấp quyền mới | Dùng public API hoặc thay thiết kế |
| Nhập on-demand hai lớp có `MAX_VALUE` rồi gọi `MAX_VALUE` | Tên dùng trở nên mơ hồ | `Integer.MAX_VALUE` / `Long.MAX_VALUE` |
| Viết `import static my.package.*;` nhằm nhập mọi lớp package | Static import cần **kiểu chứa thành viên**, không phải wildcard package | Import class thông thường hoặc một thành viên static cụ thể |
| Static import lớp từ unnamed package | Không dùng được dạng nhập kiểu dựa trên package mặc định như dự định | Đưa source vào package có tên |
| Mong `import static` giúp gọi method của object bất kỳ | Không thay object receiver | Dùng `instance.method()` |
| Giả định imported method ghi đè method cùng tên trong class | Phân giải tên/overload theo JLS, không theo thứ tự import | Dùng tên kiểu đầy đủ để làm rõ |
| Dùng `*` ở mọi lớp tiện ích | Tăng khả năng xung đột tên và khó truy nguồn | Static import chọn lọc hoặc bỏ static import |

Những lỗi **comment làm ví dụ** không được xem là mã cần biên dịch. Mọi chương trình độc lập trong bài đã giữ các dòng gây lỗi ở dạng không hoạt động hoặc dùng tên đầy đủ để biên dịch được.

## 19. Static import có ảnh hưởng tới hiệu năng không?

**Bản thân khai báo import không tương đương gọi một phương thức lúc chạy.** Nó giúp compiler giải quyết tên. Hai biểu thức:

~~~java
Math.max(3, 5)
~~~

và:

~~~java
max(3, 5)
~~~

(khi có `import static java.lang.Math.max;`) được giải quyết tới thành viên phù hợp theo quy tắc overload. Không nên tối ưu hiệu năng bằng cách chuyển `Math.max` thành `max`; sự khác nhau là **cách viết source**.

Những yếu tố quyết định hành vi runtime thật gồm method được chọn, đối số, kiểu, JIT, side effect và cấu trúc dữ liệu, không phải việc tên được viết qua qualifier hay static import.

Dù vậy, **xung đột tên ở source** có thể khiến một biểu thức không biên dịch hoặc chọn method khác khi môi trường khai báo thay đổi. Vì thế static import có ảnh hưởng thực tế tới **khả năng hiểu và bảo trì**, dù không phải cơ chế runtime để tăng tốc.

## 20. Bài tập tự kiểm tra

**Bài 1 — Cú pháp.** Viết static import để dùng `PI` và `sqrt` của `java.lang.Math` mà không cần viết `Math.` tại vị trí gọi.

**Bài 2 — Phân biệt.** `import java.util.Collections;` và `import static java.util.Collections.emptyList;` khác nhau về những tên nào có thể được viết ngắn?

**Bài 3 — Dấu `*`.** `import static java.lang.Math.*;` có nhập tất cả lớp trong package `java.lang` không? Có làm JVM lập tức chạy toàn bộ static methods của `Math` không?

**Bài 4 — Access.** Một kiểu `public Utils` có method `private static int secret()`. Một lớp khác có thể `import static Utils.secret;` để vượt qua `private` không?

**Bài 5 — Ambiguity.** Nếu nhập on-demand `Integer.*` và `Long.*`, tại sao `MAX_VALUE` có thể mơ hồ? Viết lại câu in sao cho biết rõ cần giới hạn `int`.

**Bài 6 — Shadowing.** Trong một phương thức có `double PI=3;`, dù đã static import `Math.PI`, `System.out.println(PI)` in giá trị nào? Muốn giá trị từ `Math` phải viết gì?

**Bài 7 — Static và instance.** Tại sao static import `Collections.sort` là một chuyện khác với việc gọi `list.sort(comparator)`? Cái nào là static method và cái nào cần receiver object?

**Bài 8 — Enum.** Nếu một tệp xử lý `DayOfWeek` rất nhiều lần, khi nào nhập `MONDAY` và `FRIDAY` có thể hợp lý? Khi nào `DayOfWeek.MONDAY` rõ hơn?

**Bài 9 — Nested type.** Viết static import để sử dụng tên `Entry` của `java.util.Map`. Nếu không dùng static import, có thể dùng import thông thường nào?

**Bài 10 — Thiết kế.** Dự án có ba static methods cùng tên `calculate` trong các lớp `TaxRules`, `PriceRules`, `ShippingRules`. Nên nhập cả ba vào tệp xử lý đơn hàng không? Vì sao?

**Bài 11 — Package.** Trong ví dụ `Numbers`, cần điều kiện nào về quyền truy cập để tệp khác package gọi `capped` qua static import? Lệnh chạy lớp có package phải nêu tên nào?

**Bài 12 — Review.** Với một lời gọi duy nhất `Math.max(2,5)` trong tệp 300 dòng, static import `max` có chắc giúp code dễ đọc hơn không? Bạn dùng tiêu chí nào để quyết định?

### Đáp án tham khảo

1. `import static java.lang.Math.PI;` và `import static java.lang.Math.sqrt;`.
2. Import thường cho tên kiểu `Collections`; static import cho tên method `emptyList` dùng ở lời gọi phù hợp.
3. Không. Nó chỉ tham gia tra cứu các static members có thể truy cập của kiểu `Math`; không tự thực thi toàn bộ method.
4. Không. Quy tắc quyền truy cập private không thay đổi khi static import.
5. Cả `Integer` và `Long` có `MAX_VALUE`; viết `Integer.MAX_VALUE` để chỉ rõ `int`.
6. In `3.0` vì biến cục bộ che tên import; dùng `Math.PI` để chỉ trường static.
7. `Collections.sort(list)` là lời gọi static method của `Collections`; `list.sort(comparator)` là instance method trên object danh sách. Static import không biến instance method thành static.
8. Khi ngữ cảnh đã rõ một enum và tên xuất hiện thường xuyên; dùng qualifier nếu dễ nhầm hoặc muốn nêu rõ kiểu.
9. `import static java.util.Map.Entry;`; import thường `import java.util.Map.Entry;`.
10. Thường không: `TaxRules.calculate(...)` rõ nguồn nghiệp vụ hơn `calculate(...)`.
11. Kiểu `Numbers` và method `capped` phải truy cập được từ client, ví dụ `public`; chạy `com.example.app.PackageStaticImportDemo` với classpath chứa file đã biên dịch.
12. Không chắc; xem tần suất, độ rõ tên, khả năng trùng và quy ước codebase. Một lời gọi duy nhất thường đủ rõ với `Math.max`.

## 21. Tài liệu đối chiếu

- [Java Language Specification 17, §7.5.3 — Single Static Import Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.5.3): static import theo tên thành viên cụ thể.
- [Java Language Specification 17, §7.5.4 — Static-Import-on-Demand Declarations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-7.html#jls-7.5.4): static import với `*`.
- [Java Language Specification 17, §6.5 — Determining the Meaning of a Name](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.5): phân giải tên, thành viên và phạm vi.
- [Java Language Specification 17, §6.6 — Access Control](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.6): các quy tắc accessibility vẫn áp dụng khi import.
- [Java SE 17 API — Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `PI`, `max`, `pow`, `sqrt`.
- [Java SE 17 API — Introspector không liên quan; xem Comparator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Comparator.html): `comparingInt` và các phương thức tiện ích so sánh.
- [Java SE 17 API — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html): `joining`.

**Ghi nhớ:** `import static` giúp gọi **thành viên static có thể truy cập của một kiểu** bằng tên ngắn hơn, nhưng không đổi quyền truy cập, không biến method instance thành static và không tăng tốc chương trình. Ưu tiên **nhập có chọn lọc** khi tên ngắn vẫn rõ nghĩa (công thức, assertion, một số hằng số/tiện ích); giữ `TypeName.member` khi nguồn gốc quan trọng, tên quá chung hoặc có nguy cơ trùng. Static import tốt là một lựa chọn phục vụ **người đọc code**, không phải mục tiêu rút ngắn mọi dòng.
