# Cú pháp static import cho trường và phương thức

## 1. Static import giải quyết việc gì?

Khi dùng một thành viên `static` ở một kiểu khác, ta thường ghi tên kiểu đứng trước thành viên:

```java
double circumference = 2 * Math.PI * radius;
int larger = Math.max(left, right);
```

Nếu `Math.PI` và `Math.max` xuất hiện nhiều lần trong một công thức hoặc một nhóm phép tính, **static import** cho phép dùng tên ngắn:

```java
double circumference = 2 * PI * radius;
int larger = max(left, right);
```

Đây là cách khai báo để trình biên dịch phân giải tên. Nó không tạo thêm một trường mới, không sao chép phương thức sang lớp đang viết và không làm thành viên thay đổi chủ sở hữu. `PI` vẫn là trường của `Math`; `max` vẫn là phương thức của `Math`.

Bài tập trung vào cú pháp static import cho **trường** và **phương thức**, bằng các ví dụ còn áp dụng trên Java hiện hành và chạy được từ Java 17 trở lên.

## 2. Hai dạng cú pháp

### 2.1. Nhập một tên thành viên static

Khuôn cú pháp:

```text
import static <tên đầy đủ của kiểu>.<tên thành viên>;
```

Ví dụ hợp lệ:

```java
import static java.lang.Math.PI;
import static java.lang.Math.max;
import static java.lang.System.out;
import static java.util.concurrent.TimeUnit.MINUTES;
```

Đọc từng phần của `import static java.lang.Math.max;`:

- `import static`: khai báo nhập thành viên static.
- `java.lang.Math`: kiểu chứa thành viên.
- `max`: tên thành viên cần dùng.
- `;`: kết thúc khai báo.

Đối với trường, phần cuối là **tên trường**. Đối với phương thức, phần cuối là **tên phương thức**, không có dấu ngoặc gọi hàm, không có đối số và không ghi kiểu tham số.

```java
import static java.lang.Math.max; // Đúng.

// Sai cú pháp:
// import static java.lang.Math.max();
// import static java.lang.Math.max(int, int);
```

Một khai báo nhập tên `max` có thể đưa các phương thức static truy cập được cùng tên vào việc phân giải lời gọi. Không viết một dòng import riêng cho `max(int, int)` và một dòng khác cho `max(double, double)`; trình biên dịch chọn overload khi thấy các đối số ở nơi gọi.

### 2.2. Nhập theo yêu cầu bằng dấu *

Khuôn cú pháp:

```text
import static <tên đầy đủ của kiểu>.*;
```

Ví dụ:

```java
import static java.lang.Math.*;
```

Dạng này cho phép dùng các thành viên static truy cập được từ kiểu đã nêu bằng tên ngắn khi cần. Trong phạm vi trường và phương thức của bài, ta có thể dùng `PI`, `round(...)`, `max(...)` mà không viết riêng từng dòng import.

Dấu `*` ở đây đi sau **tên kiểu**, không phải tên package. Nó không có nghĩa là nhập mọi thành viên static trong toàn bộ package.

Hai dạng được quy định trong [JLS §7.5.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5.3) và [JLS §7.5.4](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.5.4).

## 3. Đặt static import ở đâu?

Trong tệp Java thông thường có khai báo lớp, thứ tự là:

```java
package demo; // Nếu tệp có khai báo package.

import java.util.List;
import static java.lang.Math.max;

public class Example {
    // Khai báo trường, constructor, phương thức...
}
```

Các khai báo import nằm sau khai báo `package` nếu có, và trước các khai báo kiểu cấp cao nhất. Không đặt import trong thân lớp hoặc trong phương thức.

Java cho phép các dòng import thường và static import xuất hiện trong phần import; việc nhóm chúng thành hai nhóm hoặc sắp thứ tự là quy ước định dạng của dự án.

Phạm vi khai báo là **đơn vị biên dịch**, thường tương ứng với tệp nguồn đang viết. Một tệp khác trong cùng package không tự có các static import của tệp này.

### Tên kiểu trong dòng static import phải đầy đủ

Đoạn sau không thay thế được dòng khai báo đầy đủ:

```java
import java.lang.Math;
// import static Math.PI; // Không dùng tên ngắn Math theo cách này.
```

Hãy viết:

```java
import static java.lang.Math.PI;
```

Một import thường ở phía trên không biến tên kiểu ngắn thành tên hợp lệ để rút gọn phần chủ sở hữu trong khai báo static import.

## 4. Ví dụ đầy đủ: nhập trường và phương thức từ JDK

Lưu tệp tên `StaticImportDemo.java`:

```java
import java.util.List;

import static java.lang.Math.PI;
import static java.lang.Math.max;
import static java.lang.Math.round;
import static java.lang.System.out;
import static java.util.concurrent.TimeUnit.MINUTES;

public class StaticImportDemo {
    public static void main(String[] args) {
        out.println("rounded circumference=" + round(2 * PI * 3));
        out.println("max int=" + max(4, 9));
        out.println("max double=" + max(2.5, 7.5));
        out.println("seconds=" + MINUTES.toSeconds(2));
        out.println("labels=" + List.of("A", "B"));
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -Xlint:all -Werror StaticImportDemo.java
java StaticImportDemo
```

Stdout:

```text
rounded circumference=19
max int=9
max double=7.5
seconds=120
labels=[A, B]
```

### Các trường được nhập

- `PI` là trường static của `Math`, dùng trực tiếp trong biểu thức.
- `out` là trường static của `System`. Sau khi lấy được tham chiếu `out`, chương trình gọi phương thức `println` trên đối tượng mà trường đó tham chiếu.
- `MINUTES` là hằng enum của `TimeUnit`; hằng enum được truy cập như một trường static của kiểu enum.

Cần phân biệt hai bước ở dòng:

```java
out.println("hello");
```

Static import ở đây nhập **trường `out`**. Nó không nhập phương thức `println`; `println` là lời gọi qua đối tượng `PrintStream` được lấy từ trường `out`.

Tương tự, `MINUTES.toSeconds(2)` sử dụng trường hằng enum đã nhập, sau đó gọi phương thức trên giá trị enum đó. Không suy ra rằng mọi phương thức xuất hiện sau một tên được static import cũng phải là static.

### Các phương thức được nhập

- `round(...)` là lời gọi phương thức static `Math.round(...)`.
- `max(4, 9)` và `max(2.5, 7.5)` dùng cùng tên được nhập, nhưng được chọn overload theo kiểu đối số.

Không cần tạo `new Math()` để gọi các phương thức này. Static import thay cách viết tên ở nơi sử dụng, không đổi cách Java hiểu thành viên static.

### Import thường vẫn có vai trò riêng

Dòng `import java.util.List;` cho phép viết `List` thay cho `java.util.List`. Vì chương trình không static import `List.of`, nó vẫn viết `List.of("A", "B")`.

Hai công cụ này có thể dùng cùng nhau trong một tệp:

| Khai báo | Tên được viết ngắn ở nơi dùng |
|---|---|
| `import java.util.List;` | `List` |
| `import static java.lang.Math.PI;` | `PI` |
| `import static java.lang.Math.max;` | `max(...)` |

Ngược lại, `import static java.util.List.of;` sẽ cho phép lời gọi `of(...)`, nhưng bản thân nó không nhập tên kiểu `List`. Nếu vẫn khai báo biến bằng `List<String>`, cần import kiểu hoặc ghi tên kiểu đầy đủ.

## 5. Ví dụ dạng dấu *

Lưu tệp `WildcardStaticImportDemo.java`:

```java
import static java.lang.Math.*;

public class WildcardStaticImportDemo {
    public static void main(String[] args) {
        System.out.println(round(PI));
        System.out.println(max(4, 9));
    }
}
```

Chạy:

```shell
javac --release 17 -Xlint:all -Werror WildcardStaticImportDemo.java
java WildcardStaticImportDemo
```

Kết quả:

```text
3
9
```

`round`, `PI` và `max` được dùng nhờ cùng một dòng `import static java.lang.Math.*;`.

Dấu `*` không làm chương trình tải hoặc chạy tất cả các phương thức. Import là cơ chế phân giải tên; một dòng import tự nó không gọi phương thức và không tạo đối tượng.

Dạng nhập từng tên thường giúp người đọc thấy nguồn của các tên ngắn ngay trong phần import. Dạng dấu `*` có thể phù hợp khi một nhóm thành viên được dùng dày đặc và nguồn của chúng rõ ràng. Nếu nhiều kiểu đưa vào cùng một tên, việc dùng tên ngắn có thể trở nên không rõ hoặc gây lỗi phân giải; khi đó giữ dạng có tên kiểu như `Math.max(...)` là một lựa chọn trực tiếp.

## 6. Static import không chỉ dành cho hằng số

Điều kiện là thành viên phải `static` và truy cập được, không phải cứ trường được nhập là bắt buộc có `final`.

Thí nghiệm hai tệp sau dùng một trường static có thể thay đổi để nhìn rõ rằng import không tạo bản sao. Đây là ví dụ quan sát cơ chế; khi thiết kế API thực tế, việc cho phép thay đổi trạng thái cần có chủ đích.

Cấu trúc:

```text
demo/
├── Limits.java
└── OwnStaticImportDemo.java
```

Tệp `demo/Limits.java`:

```java
package demo;

public final class Limits {
    public static int limit = 10;

    private Limits() {
    }

    public static int increase() {
        return ++limit;
    }
}
```

Tệp `demo/OwnStaticImportDemo.java`:

```java
package demo;

import static demo.Limits.increase;
import static demo.Limits.limit;

public class OwnStaticImportDemo {
    public static void main(String[] args) {
        System.out.println("before=" + limit);
        System.out.println("returned=" + increase());
        System.out.println("after=" + limit);
        System.out.println("qualified=" + Limits.limit);
    }
}
```

Từ thư mục chứa thư mục `demo`, chạy:

```shell
javac --release 17 -Xlint:all -Werror -d out demo/Limits.java demo/OwnStaticImportDemo.java
java -cp out demo.OwnStaticImportDemo
```

Kết quả:

```text
before=10
returned=11
after=11
qualified=11
```

Sau lời gọi `increase()`, cả tên ngắn `limit` lẫn tên có chủ sở hữu `Limits.limit` đều đọc được 11. Chúng cùng chỉ đến trường đã khai báo trong `Limits`.

Trong ví dụ, hai lớp ở cùng package `demo`, nên có thể viết tên kiểu `Limits` mà không thêm import thường. Việc đó đến từ quan hệ package, không phải vì static import đã nhập luôn tên lớp.

Khi muốn static import thành viên từ lớp tự viết, hãy đặt lớp trong package có tên và dùng đúng tên đầy đủ. Không dùng một lớp trong package không tên làm nguồn static import.

## 7. Quyền truy cập và giới hạn cần nhớ

Static import không bỏ qua quy tắc truy cập. Một trường `private static` không trở thành truy cập được từ tệp khác chỉ vì viết thêm một dòng import.

Tương tự, một phương thức thực thể không thể được nhập như phương thức static. Ví dụ sau có chủ đích chứa khai báo không hợp lệ:

```java
// Không hợp lệ: String.length() là phương thức thực thể.
// import static java.lang.String.length;
```

Muốn lấy độ dài chuỗi, vẫn cần một đối tượng chuỗi:

```java
String text = "Java";
int length = text.length();
```

Với mã nằm trong named module, khả năng đọc module và truy cập package vẫn phải hợp lệ. Static import không thay thế các điều kiện truy cập của hệ thống module.

## 8. Các lỗi cú pháp thường gặp

| Cách viết sai hoặc hiểu sai | Cách viết đúng hoặc cách hiểu đúng |
|---|---|
| `import java.lang.Math.PI;` để nhập trường | Thêm `static`: `import static java.lang.Math.PI;` |
| `import static java.lang.Math.max();` | Bỏ ngoặc: `import static java.lang.Math.max;` |
| Ghi kiểu tham số của overload trong import | Chỉ nhập tên phương thức; overload được chọn tại lời gọi |
| `import static java.util.*;` | Dấu `*` của static import phải theo sau một kiểu, ví dụ `java.util.Collections.*` |
| Đặt import bên trong `main` | Đưa import lên phần đầu tệp, trước khai báo lớp |
| Cho rằng `import java.lang.Math;` cho phép viết `max(...)` | Import kiểu chỉ cho phép viết `Math`; muốn dùng `max(...)` cần static import hoặc ngữ cảnh khác cho phép |
| Cho rằng static import một phương thức nhập luôn tên lớp | Import thành viên và import kiểu là hai việc riêng |
| Cho rằng tất cả trường static import đều là hằng | `static` không đồng nghĩa `final` |
| Cho rằng import một lần áp dụng cho mọi tệp cùng package | Mỗi tệp cần các khai báo import của chính nó |

`java.lang` được nhập kiểu một cách tự động trong mã Java thông thường, nhưng không vì thế mà mọi thành viên static của `Math` đều xuất hiện dưới tên ngắn. Đây là lý do ta có thể viết `Math.max(...)` mà không import kiểu `Math`, trong khi `max(...)` vẫn cần được phân giải từ một nguồn hợp lệ.

## 9. Thực hành từ tên đầy đủ sang tên ngắn

Giả sử trong một phương thức đang có:

```java
long seconds = java.util.concurrent.TimeUnit.MINUTES.toSeconds(5);
int bigger = java.lang.Math.max(12, 8);
System.out.println(seconds);
System.out.println(bigger);
```

Yêu cầu: thêm các khai báo static import thích hợp và viết lại sao cho trực tiếp dùng `MINUTES`, `max` và `out`.

Đáp án — đặt ở phần import của tệp:

```java
import static java.lang.Math.max;
import static java.lang.System.out;
import static java.util.concurrent.TimeUnit.MINUTES;
```

Phần thân phương thức:

```java
long seconds = MINUTES.toSeconds(5);
int bigger = max(12, 8);
out.println(seconds);
out.println(bigger);
```

Kết quả:

```text
300
12
```

Hãy tự chỉ ra thành viên nào được nhập: `MINUTES` và `out` là trường, `max` là phương thức. `toSeconds` và `println` vẫn là các lời gọi qua đối tượng nhận được từ trường tương ứng.

Khi viết một static import, hãy kiểm tra bốn điểm: **đúng tên đầy đủ của kiểu → đúng tên thành viên static truy cập được → không có ngoặc hay chữ ký phương thức → dấu chấm phẩy ở cuối**. Sau đó chọn giữa tên ngắn và tên có chủ sở hữu dựa trên độ rõ của mã tại nơi sử dụng.
