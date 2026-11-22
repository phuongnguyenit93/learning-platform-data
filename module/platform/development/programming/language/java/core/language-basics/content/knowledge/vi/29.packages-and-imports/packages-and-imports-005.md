# Static import cho thành viên static (Java 17+)

## 1. Static import là gì?

`static import` cho phép dùng **tên ngắn** của một thành viên `static` có thể truy cập từ lớp hoặc interface khác, thay vì luôn viết `TênKiểu.tênThànhViên`. Đây là cú pháp phân giải tên ở **thời điểm biên dịch**, không tạo bản sao thành viên, không biến thành viên thành biến cục bộ và không thay đổi hành vi hay hiệu năng của phương thức.

Ví dụ, thay `Math.PI`, `Math.pow(2, 3)` bằng `PI`, `pow(2, 3)` nếu có các khai báo import tương ứng. Cả hai cách vẫn truy cập đúng thành viên của `java.lang.Math`.

## 2. Cú pháp và vị trí

Khai báo `import static` nằm **sau dòng `package` (nếu có), trước các khai báo kiểu** và ở cùng cấp với `import` thông thường:

```java
package lesson;

import java.util.List;              // import tên kiểu List
import static java.lang.Math.PI;    // một trường static
import static java.lang.Math.pow;   // một phương thức static (các overload cùng tên)
import static java.lang.Math.*;     // toàn bộ thành viên static có thể truy cập, theo nhu cầu
```

Hai dòng `import static java.lang.Math.PI;` và `import static java.lang.Math.*;` ở đây được đặt cạnh nhau để minh họa cú pháp; trong mã thực tế chỉ cần dùng các khai báo phù hợp, tránh import thừa.

Có hai dạng chính:

| Dạng | Cú pháp | Ý nghĩa |
| --- | --- | --- |
| Import rõ tên | `import static ten.package.TenKieu.TEN;` | Đưa tên của một thành viên static vào phạm vi tra cứu tên ngắn |
| Import theo nhu cầu | `import static ten.package.TenKieu.*;` | Cho phép tra cứu các thành viên static có thể truy cập của kiểu đó bằng tên ngắn |

Dấu `*` không nhập package con, không tự nhập thành viên của tất cả lớp trong package và không nhập thành viên instance. `static import` không thay thế `package`, `classpath`, `module path` hoặc việc biên dịch lớp chứa thành viên.

## 3. Ví dụ đầy đủ với Math

Tạo tệp `src/lesson/CircleDemo.java`:

```java
package lesson;

import static java.lang.Math.PI;
import static java.lang.Math.pow;
import static java.lang.Math.max;

public class CircleDemo {
    public static void main(String[] args) {
        double radius = 2.0;
        double area = PI * pow(radius, 2);
        System.out.printf(java.util.Locale.ROOT, "area=%.2f%n", area);
        System.out.println("max=" + max(3, 7));
    }
}
```

Chạy tại thư mục chứa `src` (Java 17+). **Trước lần đầu dùng `javac -d out`, cần tạo sẵn thư mục `out`**: Bash/Linux/macOS dùng `mkdir -p out`; PowerShell dùng `New-Item -ItemType Directory -Force out | Out-Null` (CMD dùng `if not exist out mkdir out`). Sau đó biên dịch và chạy:

```sh
javac -d out src/lesson/CircleDemo.java
java -cp out lesson.CircleDemo
```

Kết quả chính xác:

```text
area=12.57
max=7
```

`PI` là trường `public static final`, `pow` và `max` là các phương thức `public static`. Phép tính tương đương `Math.PI * Math.pow(radius, 2)`; `max(3, 7)` tương đương `Math.max(3, 7)`. `Locale.ROOT` giúp dấu thập phân trong output là dấu chấm, không lệ thuộc locale hệ thống.

## 4. Static import cho thành viên tự định nghĩa và kiểu lồng nhau

Không chỉ API JDK: ta có thể import một trường static, một phương thức static và một kiểu thành viên static từ lớp do mình viết.

Tạo `src/lesson/util/Toolbox.java`:

```java
package lesson.util;

public final class Toolbox {
    private Toolbox() {}

    public static final int LIMIT = 3;

    public static String label(String name) {
        return "Hi, " + name;
    }

    public static class Token {
        public String text() {
            return "token";
        }
    }
}
```

Tạo `src/lesson/ToolboxDemo.java`:

```java
package lesson;

import static lesson.util.Toolbox.LIMIT;
import static lesson.util.Toolbox.label;
import static lesson.util.Toolbox.Token;

public class ToolboxDemo {
    public static void main(String[] args) {
        System.out.println("limit=" + LIMIT);
        System.out.println(label("Java"));
        System.out.println(new Token().text());
    }
}
```

Biên dịch cả hai tệp và chạy:

```sh
javac -d out src/lesson/util/Toolbox.java src/lesson/ToolboxDemo.java
java -cp out lesson.ToolboxDemo
```

Output:

```text
limit=3
Hi, Java
token
```

`LIMIT`, `label` và `Token` đều là thành viên static của `Toolbox`; `Token` là **kiểu lớp lồng static**, nên có thể dùng như tên kiểu sau static import. Nếu muốn, ba import này có thể được thay bằng `import static lesson.util.Toolbox.*;`; cách import từng tên thường dễ đọc và kiểm soát xung đột hơn.

## 5. Thành viên nào được phép import?

- **Trường static**: hằng `PI`, `MAX_VALUE`, trường `public static` khác. `final` không phải điều kiện bắt buộc.
- **Phương thức static**: `Math.max`, `Math.pow`, phương thức static của interface như `List.of`. Import theo tên phương thức cho phép trình biên dịch cân nhắc các overload thích hợp.
- **Kiểu thành viên static có thể truy cập**: ví dụ `Toolbox.Token` là nested static class; các kiểu thành viên của interface cũng là static theo quy tắc ngôn ngữ.

Quy tắc truy cập vẫn giữ nguyên: thành viên `private` ở lớp khác, thành viên `package-private` ngoài package hay thành viên `protected` không đủ điều kiện truy cập từ ngữ cảnh hiện tại sẽ không hợp lệ chỉ vì thêm static import. Không thể static import phương thức hoặc trường **instance**; chẳng hạn `import static java.lang.String.length;` là sai vì `length()` là phương thức đối tượng. Muốn dùng phải gọi `"abc".length()`.

## 6. Phân giải tên, trùng tên và bẫy thường gặp

**Trùng tên:** Khi nhiều import theo nhu cầu đưa vào các phương thức hoặc trường cùng tên có thể áp dụng, sử dụng tên ngắn có thể mơ hồ. Ví dụ, nếu vừa dùng `import static java.lang.Math.*;` vừa dùng `import static java.lang.StrictMath.*;`, gọi `sqrt(9.0)` bằng tên ngắn sẽ gặp xung đột; có thể viết rõ `Math.sqrt(9.0)` hoặc chỉ import một `sqrt` cần dùng. Phương thức cùng tên vẫn chịu cơ chế chọn overload của Java.

**Tên trong phạm vi gần:** Khai báo cùng tên ở lớp hoặc biến cục bộ có thể che khuất trường được static import; phương thức thành viên cũng có thể được ưu tiên khi phân giải lời gọi. Khi đọc code mà tên ngắn khó truy nguồn gốc, viết rõ `TênLớp.tên` sẽ an toàn hơn.

**Thứ tự import:** `import static` là khai báo cấp tệp; đặt trong thân class hoặc phương thức sẽ lỗi cú pháp. `import java.lang.Math;` chỉ đưa tên kiểu `Math` vào phạm vi và vẫn phải viết `Math.PI`; muốn dùng `PI` riêng phải viết `import static java.lang.Math.PI;`. Java tự nhận diện nhiều kiểu trong `java.lang`, nhưng không tự static import các thành viên của chúng.

**Wildcard:** `import static some.Type.*;` không có nghĩa mọi tên được chép thành biến cục bộ, không nhập thành viên instance và không phải cơ chế tải lớp ngay lúc chạy. Dùng wildcard quá rộng ở nhiều lớp tiện ích có thể khiến code khó đọc và tăng nguy cơ tên mơ hồ.

**Phụ thuộc:** Static import không tạo quyền truy cập đặc biệt; kiểu được import phải có thể biên dịch/giải quyết từ mã nguồn hoặc thư viện sẵn có trên classpath/module path. Đổi tên hoặc xóa thành viên static ở thư viện có thể làm mã dùng import không biên dịch.

## 7. Khi nào nên dùng?

Nên cân nhắc static import khi một nhóm thao tác thực sự xuất hiện liên tục và nguồn của chúng vẫn rõ ràng: phép toán `PI`/`pow`, các hàm xác nhận trong mã kiểm thử, hoặc hằng enum rất dễ nhận ra ngữ cảnh. Ưu tiên import **từng tên** và tránh dùng hai nguồn cho cùng một tên.

Nên giữ tiền tố `Math.`, `Collections.`, `Objects.` hoặc `TênLớp.` nếu việc chỉ rõ nguồn giúp người đọc nhanh chóng hiểu ý nghĩa, nhất là trong code nghiệp vụ. Static import là lựa chọn về **độ dễ đọc** chứ không phải yêu cầu để gọi thành viên static.

## 8. Tự kiểm tra

1. `import java.lang.Math;` có đủ để viết `sqrt(4)` không? **Không**; viết `Math.sqrt(4)` hoặc `import static java.lang.Math.sqrt;`.
2. Có thể `import static` một phương thức đối tượng không? **Không**; đối tượng phải cung cấp receiver để gọi.
3. `import static lesson.util.Toolbox.Token;` có hợp lệ khi `Token` là `public static class` không? **Có**, nếu `Toolbox` truy cập được và có trong đường dẫn biên dịch.
4. Khi trùng tên do static import, cách sửa dễ hiểu nhất là gì? **Gọi đầy đủ với tên kiểu**, hoặc thu hẹp các import.

Ghi nhớ: `static import` rút gọn tên thành viên static có thể truy cập; quy tắc phạm vi, quyền truy cập, overload và biên dịch của Java vẫn được áp dụng bình thường.
