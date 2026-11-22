# Tiêu chí dùng static import trong mã kiểm thử và mã tính toán dễ đọc

## 1. Mục tiêu là đọc rõ ý định của mã

Static import cho phép viết tên thành viên static mà không lặp lại kiểu sở hữu:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static java.lang.Math.hypot;
```

Nhờ đó, có thể viết `assertEquals(expected, actual)` trong kiểm thử hoặc `hypot(x, y)` trong công thức.

Lợi ích không nằm ở số ký tự tiết kiệm được. Một static import tốt làm hành vi hoặc công thức nổi bật hơn mà người đọc vẫn nhận ra nguồn và ý nghĩa của tên. Nếu phải mở nhiều tệp để biết `of()`, `get()` hay `check()` thuộc đâu, cách viết ngắn có thể làm mã khó đọc hơn.

Bài dùng API JUnit Jupiter hiện hành cho kiểm thử và `java.lang.Math` cho tính toán; không dựa trên cách kế thừa lớp kiểm thử cũ chỉ để gọi assertion.

## 2. Những câu hỏi nên trả lời trước khi nhập static

| Tiêu chí | Nên cân nhắc static import khi | Nên giữ tên kiểu khi |
| --- | --- | --- |
| Nhận diện nguồn | Tên quen thuộc trong ngữ cảnh, như assertEquals trong tệp kiểm thử | Tên chung chung hoặc xuất hiện ở nhiều thư viện |
| Tính tập trung | Một nhóm thao tác từ một nguồn được dùng nhiều lần | Tệp trộn nhiều nguồn có tên giống nhau |
| Ý nghĩa nghiệp vụ | Bỏ tên kiểu vẫn hiểu đúng hành vi | Kiểu sở hữu mang thông tin quan trọng về nghiệp vụ |
| Công thức | Tên hàm toán học giúp biểu thức gần cách đọc toán | Bỏ tên kiểu khiến nhầm thư viện hoặc biến cục bộ |
| Xung đột | Không có tên cùng nghĩa khác trong phạm vi hiện tại | Có tên trùng hoặc lời gọi nạp chồng khó đoán |
| Quy ước dự án | Cách viết phù hợp với các tệp xung quanh | Công cụ/quy ước yêu cầu import tường minh hoặc tên có kiểu |

Không có một ngưỡng số lần dùng bắt buộc cho mọi dự án. Một assertion xuất hiện một lần vẫn có thể đủ quen thuộc để nhập static; một phương thức tên `execute` xuất hiện nhiều lần vẫn có thể cần tên kiểu để người đọc biết nó thực hiện việc gì.

## 3. Trong mã kiểm thử: làm nổi bật điều đang được xác nhận

### 3.1. Nhập tường minh các assertion cần dùng

Cách viết có tên kiểu:

```java
Assertions.assertEquals(5.0, actualDistance, 1e-12);
Assertions.assertTrue(actualDistance >= 0.0);
```

Cách viết sau static import:

```java
assertEquals(5.0, actualDistance, 1e-12);
assertTrue(actualDistance >= 0.0);
```

Trong tệp kiểm thử Jupiter, `assertEquals` và `assertTrue` có vai trò quen thuộc, nên bỏ tiền tố thường làm điều kiện kiểm thử nổi bật hơn. Tuy vậy, static import không thay đổi ý nghĩa hay thứ tự tham số: vẫn phải phân biệt giá trị mong đợi và kết quả thực tế.

Ví dụ:

```java
double expectedDistance = 5.0;
double actualDistance = DistanceMath.distanceFromOrigin(3.0, 4.0);
assertEquals(expectedDistance, actualDistance, 1e-12);
```

Tên biến rõ ràng quan trọng hơn việc viết ngắn lời gọi assertion. Với số thực, dung sai phải phù hợp với yêu cầu và độ lớn dữ liệu; `1e-12` ở đây chỉ dành cho ví dụ có giá trị cỡ vài đơn vị, không phải chính sách sai số dùng cho mọi phép tính.

### 3.2. Ví dụ kiểm thử Jupiter đầy đủ

Phần này gồm hai tệp. Tệp sản phẩm `DistanceMath.java`:

```java
import static java.lang.Math.hypot;

public final class DistanceMath {
    private DistanceMath() {
    }

    public static double distanceFromOrigin(double x, double y) {
        return hypot(x, y);
    }
}
```

Tệp kiểm thử `DistanceMathTest.java`:

```java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DistanceMathTest {
    @Test
    void computesDistanceForThreeAndFour() {
        double actualDistance =
                DistanceMath.distanceFromOrigin(3.0, 4.0);

        assertAll(
                () -> assertEquals(5.0, actualDistance, 1e-12),
                () -> assertTrue(actualDistance >= 0.0)
        );
    }

    @Test
    void originHasZeroDistance() {
        double actualDistance =
                DistanceMath.distanceFromOrigin(0.0, 0.0);

        assertEquals(0.0, actualDistance, 0.0);
    }
}
```

Tệp kiểm thử cần dự án đã cấu hình dependency JUnit Jupiter và bộ chạy kiểm thử tương ứng. Không thể chỉ dùng `javac DistanceMathTest.java` khi classpath chưa có JUnit rồi coi lỗi thiếu thư viện là lỗi static import.

Chạy bằng tác vụ kiểm thử của dự án hoặc IDE đã cấu hình Jupiter. Nếu đặt hai tệp vào đúng source set của một dự án Gradle có Jupiter và `useJUnitPlatform()`, có thể dùng:

```shell
./gradlew test --tests DistanceMathTest
```

Trên Windows, dùng `gradlew.bat` thay cho `./gradlew`; với dự án nhiều module, cần gọi tác vụ test của module sở hữu lớp kiểm thử. Câu lệnh này giả định phần cấu hình kiểm thử đã tồn tại, không phải hướng dẫn tạo một dự án Gradle mới.

Kết quả mong đợi là hai phương thức kiểm thử thành công. Ví dụ không tự in stdout; cách bộ chạy trình bày báo cáo có thể khác giữa Gradle và IDE.

Điểm đáng chú ý:

- `Test` là kiểu annotation nên dùng import kiểu thông thường.
- `assertAll`, `assertEquals`, `assertTrue` là phương thức static nên có thể dùng static import.
- `DistanceMath.distanceFromOrigin` vẫn giữ tên lớp để nguồn mã đang được kiểm thử rõ ràng.
- Không cần cho lớp kiểm thử kế thừa `Assertions` để dùng tên ngắn.

### 3.3. Khi nào dùng wildcard trong tệp kiểm thử?

`import static org.junit.jupiter.api.Assertions.*;` có thể phù hợp nếu tệp dùng nhiều assertion từ cùng một thư viện và dự án thống nhất quy ước đó.

Nhập riêng từng tên có lợi khi cần nhìn nhanh những assertion nào được dùng hoặc muốn tránh mở rộng tập tên ngoài ý định. Không có yêu cầu của Java buộc mọi tệp kiểm thử phải dùng `*`.

Cần thận trọng khi trộn nhiều thư viện assertion hoặc công cụ giả lập có tên giống nhau. Nếu có hai phương thức `assertThat` hoặc `fail` từ hai nguồn, giữ tên kiểu ở lời gọi ít dùng hoặc chỉ nhập một nguồn qua tên ngắn thường rõ hơn.

## 4. Trong mã tính toán: để công thức nổi bật nhưng giữ rõ đơn vị

So sánh:

```java
double vertical = speed * Math.sin(Math.toRadians(angleDegrees));
```

và:

```java
double vertical = speed * sin(toRadians(angleDegrees));
```

Nếu tệp đã nhập tường minh `Math.sin` và `Math.toRadians`, phiên bản sau có thể gần cách đọc công thức hơn. Tuy nhiên, tên `angleDegrees` và phép chuyển đổi `toRadians` mới giúp người đọc thấy rõ đơn vị; static import không tự chuyển độ thành radian.

Một số nguyên tắc:

- Chỉ bỏ tiền tố khi tên hàm toán học đủ quen thuộc trong ngữ cảnh.
- Giữ tên biến thể hiện ý nghĩa và đơn vị, như `angleDegrees`, `distanceMeters`, `elapsedSeconds`.
- Nếu công thức quá dài, tách biến trung gian có ý nghĩa thay vì chỉ cố rút ngắn tên hàm.
- Không tạo biến cục bộ cùng tên với hằng hoặc phương thức được nhập nếu điều đó làm người đọc hiểu sai.
- Nếu phải phân biệt `Math`, `StrictMath` hoặc thư viện chuyên biệt, giữ tên kiểu ở các phép gọi cần nêu rõ nguồn.

### Ví dụ tính toán chạy độc lập

Lưu thành `ReadableCalculation.java`:

```java
import java.util.Locale;

import static java.lang.Math.hypot;
import static java.lang.Math.sin;
import static java.lang.Math.toRadians;

public class ReadableCalculation {
    public static void main(String[] args) {
        double distanceMeters = hypot(3.0, 4.0);

        double speedMetersPerSecond = 10.0;
        double angleDegrees = 90.0;
        double verticalSpeed =
                speedMetersPerSecond * sin(toRadians(angleDegrees));

        System.out.printf(Locale.ROOT,
                "distance=%.1f m%n", distanceMeters);
        System.out.printf(Locale.ROOT,
                "vertical speed=%.1f m/s%n", verticalSpeed);
    }
}
```

Biên dịch và chạy trên Java 17+:

```shell
javac -encoding UTF-8 ReadableCalculation.java
java ReadableCalculation
```

Kết quả:

```text
distance=5.0 m
vertical speed=10.0 m/s
```

`Locale.ROOT` giữ dấu chấm thập phân trong ví dụ, không phụ thuộc thiết lập ngôn ngữ của máy. Tên kiểu `Locale` được giữ vì `ROOT` đứng một mình ít nói rõ vai trò của nó hơn `sin` trong công thức.

`hypot(x, y)` tính độ dài cạnh huyền và tránh vấn đề tràn/sụt số ở bước trung gian theo hợp đồng của API, so với cách tự viết ngây thơ `sqrt(x * x + y * y)`. Đây là lựa chọn thuật toán/API; static import chỉ làm cách gọi ngắn hơn, không tạo ra tính ổn định số học đó.

## 5. Những điều static import không giải quyết

### Không thay đổi kết quả hay hiệu năng chỉ vì bỏ tên lớp

`Math.sin(angle)` và `sin(angle)` sau import phù hợp gọi cùng phương thức. Không có lợi ích tốc độ chỉ nhờ bỏ tiền tố `Math.`.

Trong kiểm thử, static import không sửa được assertion sai kỳ vọng, không bảo đảm kiểm thử có ý nghĩa và không tự làm bộ chạy phát hiện lớp kiểm thử.

### Không tự loại bỏ xung đột tên

Nhập static rộng từ cả `Math` và `StrictMath` có thể làm lời gọi `sqrt(...)` mơ hồ. Thứ tự các dòng import không phải quy tắc “dòng sau thắng”.

Nếu muốn hai nguồn cùng xuất hiện, viết `Math.sqrt(...)` và `StrictMath.sqrt(...)` thường rõ hơn.

### Không thay thế thiết kế tên miền

Một lời gọi `validate()` hoặc `process()` không rõ nguồn không tự trở thành mã dễ đọc vì được static import. Nếu lớp sở hữu giải thích vai trò quan trọng, chẳng hạn `PaymentRules.validate(...)`, việc giữ lớp có thể hữu ích.

Đừng chuyển mọi phương thức tiện ích thành static rồi nhập toàn bộ chỉ để các lời gọi trông giống ngôn ngữ riêng. Thiết kế trách nhiệm và quản lý phụ thuộc là vấn đề rộng hơn cơ chế import.

### Không yêu cầu sao chép hằng hoặc dùng kế thừa

Không cần tạo một trường mới trỏ tới hằng khác chỉ để rút ngắn tên. Cũng không cần cho lớp nghiệp vụ hoặc lớp kiểm thử kế thừa một lớp/triển khai một interface chỉ để dùng tên hằng. Static import đã cung cấp cơ chế dùng tên ngắn mà không thêm quan hệ kiểu không cần thiết.

## 6. Cách lựa chọn trong thực tế

Trước khi thêm static import, đọc lại đoạn mã như một người chưa biết tệp đó:

1. Có nhận ra tên đang biểu thị phép kiểm tra, hàm toán học hay thao tác nghiệp vụ không?
2. Nếu bỏ tên lớp, thông tin quan trọng nào bị mất?
3. Có tên trùng trong biến cục bộ, lớp hiện tại hoặc thư viện khác không?
4. Import riêng những tên cần dùng có đủ gọn không?
5. Cách viết có phù hợp quy ước hiện tại của dự án không?

Trong kiểm thử, các assertion quen thuộc thường là ứng viên tốt; mã đang được kiểm thử vẫn có thể giữ tên lớp để nêu rõ nguồn. Trong tính toán, các hàm toán học cùng một nguồn thường là ứng viên tốt; đơn vị, tên biến và các bước biến đổi vẫn phải tường minh.

## 7. Bài tập đọc và sửa mã

1. Đổi ba static import trong `ReadableCalculation` thành lời gọi có tiền tố `Math.`. Chạy lại để xác nhận kết quả không đổi, rồi đánh giá cách nào dễ đọc hơn trong chính tệp đó.
2. Viết `sin(angleDegrees)` thay cho `sin(toRadians(angleDegrees))`. Giải thích vì sao đây là thay đổi ngữ nghĩa và có thể sai đơn vị, chứ không phải thay đổi import.
3. Trong ví dụ kiểm thử, đổi lời gọi của mã sản phẩm thành static import `DistanceMath.distanceFromOrigin`. So sánh xem việc giữ hay bỏ `DistanceMath` giúp người đọc nhận ra đối tượng kiểm thử tốt hơn.
4. Nếu một tệp kiểm thử dùng hai thư viện có tên assertion trùng nhau, chọn một lời gọi để viết rõ tên kiểu thay vì cố nhập cả hai qua tên ngắn.
5. Tìm một công thức dài trong mã của mình và tách biến trung gian có tên rõ trước khi quyết định thêm static import. Nhận xét riêng tác dụng của tên biến và của import.

## Tài liệu đối chiếu

- [JUnit User Guide — Mô hình kiểm thử Jupiter](https://docs.junit.org/current/user-guide/).
- [Java SE 21 Math — Các hàm toán học và hợp đồng số học](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html).
- [JLS §7.5.3 và §7.5.4 — Các dạng static import](https://docs.oracle.com/javase/specs/jls/se25/html/jls-7.html#jls-7.5.3).
