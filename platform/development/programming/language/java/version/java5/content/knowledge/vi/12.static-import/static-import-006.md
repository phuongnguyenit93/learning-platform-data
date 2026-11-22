# Xung đột tên giữa các thành viên được nhập

## 1. Vì sao static import có thể làm tên trở nên mơ hồ?

Static import cho phép dùng tên thành viên static mà không viết kiểu sở hữu:

```java
import static java.lang.Math.sqrt;
```

Nhờ đó, `sqrt(9)` có thể thay cho `Math.sqrt(9)`. Nếu nhiều nguồn cùng đưa một tên vào phạm vi xét, trình biên dịch phải xác định tên đó chỉ tới thành viên nào.

Xung đột không có một cách xử lý chung cho mọi tên. Cần phân biệt:

- **Trường**: tên như `MAX_VALUE` phải xác định được trường cần đọc.
- **Phương thức**: nhiều khai báo cùng tên có thể cùng tham gia chọn phương thức nạp chồng.
- **Kiểu thành viên**: tên kiểu như `Entry` phải xác định được một kiểu phù hợp; một số tổ hợp import bị cấm ngay ở phần khai báo.

Các quy tắc này vẫn áp dụng trong Java hiện đại. Ví dụ trong bài dùng các API hiện hành và chạy được trên Java 17+.

## 2. Hai trường cùng tên: kiểu biến nhận không chọn hộ

Ví dụ dưới đây cố ý gây lỗi. Lưu riêng nếu muốn quan sát thông báo trình biên dịch:

```java
import static java.lang.Integer.*;
import static java.lang.Long.*;

class AmbiguousField {
    long limit = MAX_VALUE;
}
```

`MAX_VALUE` có thể là:

- `Integer.MAX_VALUE`, giá trị `2147483647`.
- `Long.MAX_VALUE`, giá trị `9223372036854775807L`.

Cả hai trường đều có thể truy cập. Java không chọn `Long.MAX_VALUE` chỉ vì biến `limit` có kiểu `long`. Việc xác định trường được tham chiếu không phải phép chọn theo kiểu của biến nhận như vậy.

Hai import theo ký tự đại diện có thể cùng tồn tại nếu không dùng tên gây xung đột. Lỗi ở ví dụ xuất hiện khi biểu thức `MAX_VALUE` cần được phân giải.

Cách sửa dễ đọc:

```java
long integerLimit = Integer.MAX_VALUE;
long longLimit = Long.MAX_VALUE;
```

Tên có chỉ định kiểu thể hiện rõ nguồn và giữ cả hai giá trị dùng được trong cùng tệp.

### Nhập riêng một trường có thể che nguồn nhập theo ký tự đại diện

Với:

```java
import static java.lang.Integer.MAX_VALUE;
import static java.lang.Long.*;
```

trong bối cảnh không có khai báo khác che tên, `MAX_VALUE` chỉ tới trường được nhập riêng từ `Integer`. Trường nhập theo một tên được ưu tiên bằng quy tắc che tên so với trường cùng tên nhập theo ký tự đại diện.

Đừng sửa bằng cách đảo vị trí hai dòng import. Quy tắc không phụ thuộc vào việc dòng nào đứng trước hay sau.

Nếu cả hai trường đều được nhập riêng:

```java
import static java.lang.Integer.MAX_VALUE;
import static java.lang.Long.MAX_VALUE;
```

thì không có nguồn nào thắng vì viết sau. Hai dòng import trường này tự chúng có thể tồn tại, nhưng dùng tên ngắn `MAX_VALUE` vẫn mơ hồ nếu không có khai báo khác xác định nguồn. Khi cần cả hai, nên giữ tên kiểu ở nơi dùng.

## 3. Phương thức trùng tên chưa chắc gây lỗi

Xét:

```java
import static java.lang.Integer.valueOf;
import static java.lang.Double.valueOf;
```

Đây là hai static import theo cùng tên phương thức từ hai kiểu khác nhau. Các phương thức được nhập có thể tạo thành tập ứng viên để chọn lời gọi.

- `valueOf(7)` chọn `Integer.valueOf(int)`: đối số `int` khớp trực tiếp; phương án dùng `Double.valueOf(double)` cần mở rộng kiểu.
- `valueOf(2.5)` chọn `Double.valueOf(double)`: `Integer.valueOf(int)` không nhận được giá trị double bằng chuyển đổi thu hẹp ngầm định.

Do đó, không thể kết luận “hai import có cùng tên phương thức là sai”.

Ngược lại:

```java
// Với đúng hai import valueOf ở trên:
// Object number = valueOf("7");
```

nếu bỏ dấu chú thích sẽ bị mơ hồ. Cả `Integer.valueOf(String)` và `Double.valueOf(String)` đều phù hợp với cùng đối số chuỗi; không có phương thức nào cụ thể hơn chỉ dựa trên kiểu trả về khác nhau.

Đổi biến nhận thành `Integer` cũng không làm lời gọi thông thường này tự chọn nguồn:

```java
// Vẫn mơ hồ:
// Integer number = valueOf("7");
```

Cách sửa:

```java
Integer integerNumber = Integer.valueOf("7");
Double decimalNumber = Double.valueOf("7");
```

Import không tạo ra hàm mới và không đổi chữ ký của các phương thức. Nó chỉ làm nhiều ứng viên xuất hiện khi dùng tên ngắn; bước chọn nạp chồng vẫn tuân theo quy tắc Java.

## 4. Hai phương thức có cùng tham số: nêu rõ kiểu sở hữu

Ví dụ cố ý không biên dịch:

```java
import static java.lang.Math.sqrt;
import static java.lang.StrictMath.sqrt;

class AmbiguousSqrt {
    double value = sqrt(9);
}
```

Cả hai nguồn đều có `sqrt(double)`. Đối số `9` có thể mở rộng thành `double` cho cả hai ứng viên, và không thể chọn một phương thức tốt hơn chỉ vì thứ tự import.

Giải pháp:

```java
double first = Math.sqrt(9);
double second = StrictMath.sqrt(9);
```

Tình huống tương tự có thể xuất hiện với import ký tự đại diện từ hai kiểu. Việc chuyển từ `*` sang hai import tường minh cùng tên chưa chắc giải quyết được xung đột; phải loại bớt nguồn của tên ngắn hoặc chỉ rõ kiểu sở hữu tại lời gọi.

## 5. Ví dụ chạy đầy đủ: cùng tên hợp lệ và cách sửa rõ nguồn

Lưu thành `StaticImportConflictDemo.java`:

```java
import static java.lang.Integer.valueOf;
import static java.lang.Double.valueOf;

public class StaticImportConflictDemo {
    public static void main(String[] args) {
        System.out.println("int source="
                + valueOf(7).getClass().getSimpleName());
        System.out.println("double source="
                + valueOf(2.5).getClass().getSimpleName());

        Integer integerText = Integer.valueOf("7");
        Double decimalText = Double.valueOf("7");

        System.out.println("integer text=" + integerText);
        System.out.println("double text=" + decimalText);
        System.out.println("integer max=" + Integer.MAX_VALUE);
        System.out.println("long max=" + Long.MAX_VALUE);
        System.out.println("Math sqrt=" + Math.sqrt(9));
        System.out.println("StrictMath sqrt=" + StrictMath.sqrt(9));
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 StaticImportConflictDemo.java
java StaticImportConflictDemo
```

Kết quả:

```text
int source=Integer
double source=Double
integer text=7
double text=7.0
integer max=2147483647
long max=9223372036854775807
Math sqrt=3.0
StrictMath sqrt=3.0
```

Hai lời gọi đầu cho thấy trùng tên phương thức vẫn hợp lệ khi quy tắc nạp chồng chọn được một ứng viên. Những dòng sau giữ tên kiểu để nguồn dữ liệu và phép tính không mơ hồ.

## 6. Nhập tường minh và nhập ký tự đại diện không luôn được gộp cùng nhau

Cần đọc đúng tập import trước khi dự đoán tập phương thức ứng viên.

Ví dụ cố ý gây lỗi:

```java
import static java.lang.Integer.valueOf;
import static java.lang.Double.*;

class SingleAndWildcard {
    Object value = valueOf(2.5);
}
```

Phương thức tên `valueOf` được nhập tường minh từ `Integer` che các phương thức cùng tên nhập theo ký tự đại diện từ `Double`. Java không lấy `Double.valueOf(double)` làm ứng viên dự phòng chỉ vì các phiên bản của `Integer.valueOf` không nhận được đối số này.

Khác biệt so với mục 3 nằm ở cách nhập nguồn thứ hai:

```java
// Nhập tường minh cả hai tên:
import static java.lang.Integer.valueOf;
import static java.lang.Double.valueOf;
```

Khi cần cả hai nguồn, viết `Integer.valueOf(...)` và `Double.valueOf(...)` thường dễ đọc hơn việc trông chờ vào nhiều quy tắc che tên và nạp chồng.

Không nên rút gọn toàn bộ vấn đề thành “import tường minh luôn thắng mọi thứ”. Các khai báo trong phạm vi hiện tại, loại tên và bước tra cứu phương thức vẫn có quy tắc riêng.

## 7. Kiểu thành viên trùng tên: có thể lỗi ngay ở import

Static import cũng có thể nhập kiểu thành viên static, không chỉ trường và phương thức.

Ví dụ cố ý không biên dịch:

```java
import java.util.Map.Entry;
import static java.security.KeyStore.Entry;

class ConflictingEntryTypes {
}
```

`Map.Entry` và `KeyStore.Entry` là hai kiểu khác nhau nhưng cùng tên đơn `Entry`. Tệp kết hợp một import kiểu thông thường cho `Map.Entry` với một static import tường minh cho `KeyStore.Entry`. Hai import này đưa hai kiểu khác nhau cùng tên đơn vào tệp và gây lỗi ngay cả khi thân lớp chưa dùng `Entry`.

Nếu thay hai dòng trên bằng hai static import ký tự đại diện:

```java
import static java.util.Map.*;
import static java.security.KeyStore.*;
```

bản thân hai dòng này có thể tồn tại, nhưng việc dùng `Entry` làm tên kiểu sẽ mơ hồ nếu không có khai báo/import khác xác định rõ nguồn.

Cách rõ ràng:

```java
java.util.Map.Entry<String, Integer> mapEntry;
java.security.KeyStore.Entry keyStoreEntry;
```

Đây là các khai báo biến minh họa, không phải chương trình độc lập. Trong mã thực tế có thể nhập kiểu sở hữu rồi viết `Map.Entry` và `KeyStore.Entry` để ngắn hơn.

Không có cú pháp import đặt bí danh kiểu `as` trong Java. Đổi tên biến thành `mapEntry` cũng không tự giải quyết tên kiểu `Entry`; phải thay cách tham chiếu tới kiểu.

## 8. Phân biệt mơ hồ với bị che tên

Mơ hồ là có nhiều cách hiểu phù hợp mà Java không chọn được một nguồn duy nhất. Bị che tên là một khai báo khiến nguồn khác không được dùng qua tên ngắn ở vị trí đó.

Ví dụ:

```java
// Trong tệp có import static java.lang.Integer.MAX_VALUE:
int MAX_VALUE = 100;
System.out.println(MAX_VALUE);          // Biến cục bộ: 100.
System.out.println(Integer.MAX_VALUE);  // Trường của Integer.
```

Đoạn này minh họa các câu lệnh trong một phương thức. Tên ngắn hợp lệ nhưng có thể không trỏ tới nguồn người đọc kỳ vọng.

Với phương thức, việc có một phương thức cùng tên trong lớp hiện tại cũng có thể làm bước tra cứu không đi tới các phương thức được static import, kể cả khi chữ ký tại lớp hiện tại không phù hợp với lời gọi. Không nên dùng mẹo “đổi tham số là sẽ tự rơi sang hàm import”; khi gặp lỗi, hãy xem cả các phương thức được khai báo hoặc kế thừa trong kiểu hiện tại.

## 9. Quy trình xử lý một xung đột thực tế

1. Xác định vị trí lỗi: ngay ở import hay tại biểu thức dùng tên.
2. Xác định loại tên: trường, phương thức hay kiểu.
3. Liệt kê các nguồn có cùng tên, bao gồm import tường minh, import ký tự đại diện và khai báo trong phạm vi hiện tại.
4. Với phương thức, ghi kiểu tĩnh của từng đối số và xem các ứng viên phù hợp; đừng chỉ nhìn tên phương thức hoặc kiểu biến nhận.
5. Nếu hai nguồn đều có ý nghĩa trong tệp, dùng tên có chỉ định kiểu tại nơi sử dụng.
6. Xóa import không còn dùng và biên dịch lại. Việc đảo thứ tự import không phải giải pháp phân giải tên.

Thông báo như `reference to ... is ambiguous` thường chỉ ra các ứng viên xung đột. Lỗi `no suitable method found` lại có thể cho thấy nguồn mong muốn đã không nằm trong tập ứng viên, chẳng hạn bị che bởi import tường minh.

Các thông báo cụ thể có thể khác theo phiên bản trình biên dịch; điều cần hiểu là nguồn nào được xét và tại sao không chọn được phương thức/thành viên mong muốn.

## 10. Thói quen giúp giảm xung đột

- Dùng static import cho những tên thường dùng và vẫn nhận ra nguồn trong ngữ cảnh.
- Tránh nhập rộng từ nhiều kiểu có các tên phổ biến giống nhau như `of`, `valueOf`, `empty` hoặc `MAX_VALUE`.
- Giữ tên kiểu với các giá trị hoặc thao tác mà nguồn sở hữu là thông tin quan trọng.
- Khi nâng phiên bản thư viện, kiểm tra việc thư viện bổ sung thành viên mới có mở rộng tập tên từ wildcard import hay không.
- Không dùng kế thừa chỉ để truy cập hằng ngắn hơn; đó là thay đổi quan hệ kiểu, không phải cách giải quyết xung đột import.

Mục tiêu là làm nguồn của tên rõ ràng cho cả trình biên dịch và người đọc. Một tên ngắn tiết kiệm vài ký tự nhưng buộc người đọc tra nhiều nguồn thường không còn mang lại lợi ích.

## 11. Tự kiểm tra

1. Vì sao `long limit = MAX_VALUE;` không tự chọn `Long.MAX_VALUE` khi hai trường cùng khả dụng? Vì phải xác định trường trước, không đoán từ kiểu biến nhận.
2. Vì sao hai static import `valueOf` vẫn dùng được với `7` và `2.5`? Vì quy tắc chọn nạp chồng xác định được ứng viên phù hợp nhất.
3. Vì sao `Integer number = valueOf("7");` vẫn mơ hồ khi nhập tường minh cả hai nguồn? Vì hai phương thức nhận String đều phù hợp; kiểu trả về không giải quyết cặp ứng viên này.
4. Ví dụ kết hợp import kiểu `Map.Entry` với static import `KeyStore.Entry` khác hai wildcard import ở thời điểm nào phát hiện lỗi? Ví dụ tường minh bị lỗi ngay tại import; ví dụ wildcard gây lỗi khi tên `Entry` được dùng.
5. Nếu cần giữ cả hai nguồn trong tệp, cách sửa ổn định và dễ đọc nhất thường là gì? Chỉ rõ kiểu sở hữu ở những chỗ đang xung đột.

## Tài liệu đối chiếu

- [JLS §7.5.3 và §7.5.4 — Static import tường minh và theo ký tự đại diện](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.3).
- [JLS §6.4.1 — Quy tắc che tên](https://docs.oracle.com/javase/specs/jls/se25/html/jls-6.html#jls-6.4.1).
- [JLS §15.12 — Tra cứu và lựa chọn phương thức](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12).
