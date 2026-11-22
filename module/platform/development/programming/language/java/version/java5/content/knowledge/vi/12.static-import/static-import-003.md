# Nhập static theo ký tự đại diện

## 1. Khái niệm: dùng tên thành viên static mà không lặp tên kiểu

Nhập static theo ký tự đại diện (static import on demand) cho phép dùng tên ngắn của các thành viên static có thể truy cập được từ một kiểu:

```java
import static java.lang.Math.*;
```

Trong tệp này, có thể viết `sqrt(81)`, `max(3, 7)` hoặc `PI` thay cho `Math.sqrt(81)`, `Math.max(3, 7)` và `Math.PI`.

Dấu `*` có nghĩa là cho phép phân giải các tên static phù hợp từ kiểu đã chỉ định khi cần. Nó không thực thi mọi phương thức, không tạo bản sao các trường và không chép mã của lớp vào tệp hiện tại.

Cơ chế này vẫn được sử dụng trong Java hiện đại. Ví dụ trong bài chạy được trên Java 17+ và chỉ dùng những API còn có giá trị sử dụng.

## 2. Cú pháp và vị trí

Cú pháp:

```java
import static ten.goi.TenKieu.*;
```

Trong một đơn vị biên dịch Java thông thường có khai báo lớp tường minh, thứ tự là:

```java
package example;

import static java.lang.Math.*;

public class Geometry {
    // Nội dung lớp.
}
```

Đoạn trên minh họa cấu trúc tệp, không phải chương trình có `main`.

Các điểm cần nhớ:

- Phải có từ khóa `static`.
- Trước `.*` là tên chuẩn của một kiểu, không phải tên biến hay tên gói để tìm mọi hàm trong gói.
- Khai báo có dấu chấm phẩy kết thúc.
- Import nằm ngoài thân lớp và thân phương thức.
- Import chỉ ảnh hưởng tới việc phân giải tên trong tệp chứa nó; không tự áp dụng cho các tệp khác trong cùng gói.

Không thể đặt `import static` bên trong `main` để giới hạn phạm vi cho riêng phương thức đó.

## 3. So sánh ba cách viết

| Cách viết | Cách sử dụng | Ý nghĩa |
| --- | --- | --- |
| Không nhập static | `Math.sqrt(81)` | Nêu rõ kiểu sở hữu tại vị trí dùng |
| `import static java.lang.Math.sqrt;` | `sqrt(81)` | Nhập static theo một tên thành viên |
| `import static java.lang.Math.*;` | `sqrt(81)`, `PI`, `max(3, 7)` | Cho phép dùng nhiều tên static từ Math |

Nhập theo một tên phương thức không giới hạn một chữ ký cụ thể. Chẳng hạn, nhập tên `max` có thể đưa các phiên bản nạp chồng có thể truy cập của `Math.max` vào việc xét lời gọi. Không có cú pháp import viết kèm danh sách kiểu tham số để chọn riêng `max(int, int)`.

Nhập static theo ký tự đại diện có phạm vi tên rộng hơn nhập từng tên, nhưng cả hai đều là cơ chế ở mức mã nguồn; dấu `*` không phải tối ưu hiệu năng lúc chạy.

## 4. Ví dụ chạy đầy đủ

Lưu thành `StaticWildcardDemo.java`:

```java
import static java.lang.Math.*;
import static java.time.DayOfWeek.*;
import static java.util.Map.*;

public class StaticWildcardDemo {
    public static void main(String[] args) {
        double radius = 2.0;
        long roundedArea = round(PI * pow(radius, 2));

        System.out.println("rounded area=" + roundedArea);
        System.out.println("sqrt=" + sqrt(81));
        System.out.println("max=" + max(3, 7));
        System.out.println("day=" + MONDAY.name());

        Entry<String, Integer> version = entry("Java", 21);
        System.out.println("entry="
                + version.getKey() + ":" + version.getValue());
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 StaticWildcardDemo.java
java StaticWildcardDemo
```

Kết quả:

```text
rounded area=13
sqrt=9.0
max=7
day=MONDAY
entry=Java:21
```

Ba nguồn nhập static minh họa ba nhóm tên:

1. `Math.*`: các phương thức như `round`, `pow`, `sqrt`, `max` và trường hằng `PI`.
2. `DayOfWeek.*`: các hằng enum như `MONDAY`. Hằng enum là thành viên static của kiểu enum.
3. `Map.*`: phương thức static `entry` và kiểu thành viên `Entry`. `Map.Entry` là một interface thành viên và có tính static.

Đây là ví dụ gom nhiều nhóm để quan sát cơ chế; trong mã nghiệp vụ, không cần nhập rộng như vậy nếu chỉ dùng một hoặc hai tên.

## 5. Chính xác thì dấu * cho phép dùng những gì?

Nhập static theo ký tự đại diện không chỉ dành cho hằng số. Nó có thể làm các tên sau khả dụng khi được phép truy cập:

- Trường static.
- Phương thức static.
- Kiểu thành viên static, chẳng hạn lớp lồng static hoặc interface thành viên.
- Hằng enum.

Quy tắc truy cập vẫn có hiệu lực. Khai báo `import static` không làm một thành viên `private` trở nên public, cũng không vượt qua ranh giới truy cập của gói hoặc module.

Các thành viên static được kế thừa cũng có thể liên quan nếu chúng là thành viên của kiểu được nhập và đáp ứng quy tắc truy cập. Không nên hiểu dấu `*` chỉ nhìn các dòng được khai báo trực tiếp trong thân kiểu; việc tra cứu vẫn tuân theo quy tắc thành viên của Java.

Ngược lại, phương thức đối tượng không được biến thành phương thức static:

```java
// Ví dụ sai ý nghĩa:
// import static java.lang.String.*;
// int length = length();
```

`String.length()` cần một đối tượng chuỗi. Muốn lấy độ dài phải có biểu thức như `"Java".length()`; static import không cung cấp đối tượng nhận lời gọi.

## 6. Không nhập đệ quy vào các kiểu bên trong

Với:

```java
import static java.util.Map.*;
```

có thể dùng tên kiểu thành viên `Entry` và phương thức static `entry` của `Map`.

Nhưng dấu `*` không tiếp tục nhập tất cả thành viên static bên trong `Map.Entry`. Ví dụ, muốn gọi phương thức `Map.Entry.comparingByKey()`, có thể viết:

```java
// Trong tệp đã có import static java.util.Map.*:
Entry.comparingByKey();
```

Đoạn này minh họa một biểu thức gọi, không phải chương trình độc lập. Nếu muốn viết riêng `comparingByKey()`, phải nhập static tên đó từ `java.util.Map.Entry`, hoặc nhập static theo ký tự đại diện từ chính kiểu `Entry`.

Tương tự, `import static java.util.Map.*;` không nhập tên kiểu sở hữu `Map` cho các vị trí khai báo biến. Nếu cần viết `Map<String, Integer>`, hãy thêm import kiểu thông thường `import java.util.Map;` hoặc dùng tên đầy đủ.

## 7. Phân biệt với import gói thông thường

Hai câu sau có mục tiêu khác nhau:

```java
import java.util.*;
import static java.util.Collections.*;
```

- `import java.util.*;` cho phép dùng các tên kiểu phù hợp trong gói `java.util`, ví dụ `List` và `ArrayList`.
- `import static java.util.Collections.*;` cho phép dùng tên thành viên static phù hợp của kiểu `Collections`, ví dụ `emptyList()` và `sort(...)`.

Import gói thông thường không tự nhập các phương thức static của mọi lớp trong gói. Ví dụ, chỉ có `import java.util.*;` chưa đủ để gọi trực tiếp `emptyList()`; có thể viết `Collections.emptyList()` hoặc thêm static import.

Cả hai dạng ký tự đại diện đều không tự đi đệ quy qua các gói con. Trong trường hợp static import, đơn vị chỉ định là kiểu sở hữu thành viên, không phải một cây gói.

## 8. Xung đột tên: lỗi có thể xuất hiện khi dùng tên

Hai static import theo ký tự đại diện không nhất thiết tự gây lỗi ngay khi đứng cạnh nhau. Vấn đề xuất hiện khi tên được sử dụng mà trình biên dịch không chọn được một cách hiểu duy nhất.

### 8.1. Hai trường cùng tên

Đoạn minh họa gây lỗi biên dịch:

```java
import static java.lang.Integer.*;
import static java.lang.Long.*;

class AmbiguousConstant {
    // Không biên dịch nếu bỏ dấu chú thích:
    // long limit = MAX_VALUE;
}
```

Cả `Integer` và `Long` đều có trường `MAX_VALUE`. Trình biên dịch không tự đoán cần giá trị nào dựa trên tên biến `limit` hoặc tự chọn `Long.MAX_VALUE` vì biến nhận có kiểu long.

Cách rõ ràng nhất thường là ghi kiểu sở hữu:

```java
long integerLimit = Integer.MAX_VALUE;
long longLimit = Long.MAX_VALUE;
```

Nếu cố ý dùng tên ngắn cho một nguồn, có thể nhập riêng:

```java
import static java.lang.Integer.MAX_VALUE;
import static java.lang.Long.*;
```

Trong bối cảnh không có khai báo khác che tên, `MAX_VALUE` khi đó chỉ trường được nhập riêng từ `Integer`. Nhập static theo một tên trường che trường cùng tên được nhập static theo ký tự đại diện. Không nên suy rộng quy tắc trường này thành mọi trường hợp phương thức nạp chồng.

### 8.2. Hai phương thức cùng tên có thể tạo lời gọi mơ hồ

Đoạn minh họa:

```java
import static java.lang.Math.*;
import static java.lang.StrictMath.*;

class AmbiguousMethod {
    // Không biên dịch nếu bỏ dấu chú thích:
    // double result = sqrt(9);
}
```

Cả hai kiểu cung cấp phương thức `sqrt(double)` phù hợp. Không có quy tắc “import viết sau thắng”, nên lời gọi tên ngắn bị mơ hồ.

Viết rõ `Math.sqrt(9)` hoặc `StrictMath.sqrt(9)` để xác định nguồn. Nếu các phương thức cùng tên có chữ ký khác nhau, chúng có thể cùng tham gia lựa chọn nạp chồng; không phải mọi tên trùng đều gây lỗi. Kết quả phụ thuộc tập ứng viên và kiểu đối số.

### 8.3. Tên trong phạm vi gần có thể thay đổi cách hiểu

Ví dụ minh họa một biến cục bộ:

```java
// Tệp có import static java.lang.Math.*:
double PI = 3.0;
System.out.println(PI);       // Dùng biến cục bộ.
System.out.println(Math.PI);  // Dùng hằng của Math.
```

Một tên ngắn không bảo đảm luôn chỉ tới nguồn static import. Phải xét cả các khai báo trong phạm vi hiện tại. Khi nguồn của tên không còn rõ, tên có chỉ định kiểu thường dễ đọc và ít gây nhầm hơn.

## 9. Ký tự đại diện không làm chương trình tải mọi thành viên

Import phục vụ việc tìm và kiểm tra tên khi biên dịch. Nó không có nghĩa:

- gọi tất cả phương thức static;
- tạo đối tượng cho mọi kiểu thành viên;
- sao chép tất cả trường vào bộ nhớ riêng;
- tăng hiệu năng vì không cần viết tên lớp.

Việc khởi tạo lớp khi thực thi phụ thuộc vào thao tác dùng lớp/thành viên và quy tắc khởi tạo của Java, không phụ thuộc đơn thuần vào việc có một dòng static import. Ngay cả việc đọc một hằng cũng có quy tắc riêng, nên không nên gắn mọi static import với một lần khởi tạo lớp bắt buộc.

Vì vậy, lựa chọn nhập từng tên hay dùng ký tự đại diện chủ yếu liên quan đến khả năng đọc, quản lý xung đột và bảo trì mã nguồn, không phải mẹo tối ưu tốc độ chạy.

## 10. Khi nào nên dùng và khi nào nên nhập từng tên?

Nhập static theo ký tự đại diện có thể phù hợp khi tệp dùng nhiều thành viên từ một nguồn có ý nghĩa rõ ràng, ví dụ một đoạn tính toán tập trung vào các hàm của `Math`.

Nên cân nhắc nhập từng tên hoặc giữ tên kiểu khi:

- Chỉ dùng rất ít thành viên.
- Tệp nhập từ nhiều kiểu có các tên chung như `of`, `get`, `max` hoặc `EMPTY`.
- Người đọc khó biết tên thuộc API nào.
- Thư viện được cập nhật có thể bổ sung tên gây xung đột khi biên dịch lại.
- Nhóm phát triển có quy ước định dạng hoặc kiểm tra tĩnh yêu cầu import tường minh.

Thêm một thành viên mới vào thư viện có thể làm tập tên ứng viên rộng hơn trong mã dùng ký tự đại diện. Vì vậy, mã nguồn từng biên dịch được vẫn có thể gặp xung đột tên khi dùng phiên bản thư viện mới và biên dịch lại.

Một số IDE tự gộp nhiều static import thành `*` theo ngưỡng cấu hình. Đây là lựa chọn định dạng của công cụ, không phải yêu cầu của Java. Hãy tuân thủ quy ước của dự án và giữ nguồn của các tên quan trọng dễ nhận biết.

## 11. Thực hành

1. Trong chương trình đầy đủ, thay `Math.*` bằng các static import riêng cho `PI`, `pow`, `round`, `sqrt`, `max`. Kết quả phải giữ nguyên.
2. Thêm một biến cục bộ `double PI = 3.0;` trước phép tính diện tích. Giải thích vì sao kết quả thay đổi, rồi dùng `Math.PI` để chỉ rõ hằng cần dùng.
3. Trong ví dụ hai `MAX_VALUE`, bỏ dấu chú thích để quan sát lỗi mơ hồ. Sau đó sửa bằng tên có kiểu sở hữu.
4. Xóa `import static java.util.Map.*;` khỏi ví dụ chính. Xác định hai tên mất nguồn phân giải là `Entry` và `entry`, rồi sửa bằng import phù hợp hoặc tên đầy đủ.
5. Phân biệt ba tên: `Map` là kiểu sở hữu, `Entry` là kiểu thành viên, `entry` là phương thức static. Static import không biến chúng thành cùng một loại tên.

## Tài liệu đối chiếu

- [JLS §7.5.4 — Static import theo ký tự đại diện](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.4).
- [JLS §6.4.1 — Che tên](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.4.1).
- [Java SE 21 Map — Các thành viên và phương thức entry](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html).
