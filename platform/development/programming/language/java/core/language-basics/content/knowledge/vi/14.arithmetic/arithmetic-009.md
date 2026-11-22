# Giới thiệu Math: trị tuyệt đối, lũy thừa và làm tròn trong Java

> **Java core — language-basics / Số học**  
> **Môi trường:** Java 17+, chỉ dùng thư viện chuẩn.  
> **Mục tiêu:** Dùng đúng `Math.abs`, `Math.pow`, `Math.round`, `Math.floor` và `Math.ceil`; hiểu kiểu trả về, cách xử lý số âm, giới hạn kiểu nguyên và sai số số thực.

## 1. Lớp `Math` dùng như thế nào?

`java.lang.Math` cung cấp các phương thức `static` cho tính toán số học; không cần tạo đối tượng `Math` hay viết lệnh `import`:

~~~java
int distance = Math.abs(-12);         // 12
double area = Math.pow(3, 2);        // 9.0
long rounded = Math.round(2.7);      // 3L
double below = Math.floor(2.7);      // 2.0
double above = Math.ceil(2.7);       // 3.0
~~~

**Quan trọng:** `Math.pow`, `Math.floor` và `Math.ceil` trả `double`. `Math.round(float)` trả `int`, còn `Math.round(double)` trả `long`. Phương thức `Math.abs` có các overload cho `int`, `long`, `float`, `double` và trả kiểu tương ứng.

## 2. Trị tuyệt đối với `Math.abs`

Trị tuyệt đối thể hiện độ lớn không xét dấu:

~~~java
Math.abs(-8);     // int 8
Math.abs(-3.25);  // double 3.25
Math.abs(0);      // int 0
~~~

Dùng trong tính khoảng cách hoặc sai lệch, nhưng lưu ý **ngoại lệ về miền giá trị nguyên**. `int` có miền từ `-2147483648` đến `2147483647`, nên trị tuyệt đối toán học của `Integer.MIN_VALUE` không chứa được trong `int`:

~~~java
Math.abs(Integer.MIN_VALUE); // Vẫn là -2147483648, không ném lỗi!
~~~

Tương tự, `Math.abs(Long.MIN_VALUE)` vẫn âm. Nếu muốn **phát hiện trường hợp không biểu diễn được**, Java 17 hỗ trợ `Math.absExact(int)` và `Math.absExact(long)`, ném `ArithmeticException` khi gặp giá trị nhỏ nhất. Nếu cần trị tuyệt đối của một `int` dưới dạng `long`, hãy **chuyển kiểu trước**:

~~~java
long safe = Math.abs((long) Integer.MIN_VALUE); // 2147483648.
~~~

Đừng ép kiểu sau `Math.abs(Integer.MIN_VALUE)` vì phép tính ở kiểu `int` đã cho kết quả ngoài mong đợi.

## 3. Lũy thừa với `Math.pow`

`Math.pow(base, exponent)` trả `double`, kể cả khi truyền vào hai số nguyên:

~~~java
Math.pow(2, 3);    // 8.0
Math.pow(10, 2);   // 100.0
Math.pow(4, -1);   // 0.25
Math.pow(9, 0.5);  // 3.0: tương đương căn bậc hai của 9.
~~~

| Trường hợp | Kết quả và lưu ý |
| --- | --- |
| `Math.pow(2, 10)` | `1024.0`, kiểu `double` |
| `Math.pow(4, -1)` | `0.25`, số mũ âm |
| `Math.pow(-2, 0.5)` | `NaN`: không có kết quả thực |
| `Math.pow(2, 0)` | `1.0` |
| `Math.sqrt(81)` | `9.0`, API chuyên dụng để lấy căn bậc hai |

`Math.pow` tính bằng số thực, **không bảo đảm chính xác tuyệt đối** đối với số nguyên lớn. Tránh chuyển thẳng kết quả `double` về `int`/`long` để tính lũy thừa nguyên lớn. Nếu cần phép lũy thừa nguyên chính xác, dùng `BigInteger.pow(int)` khi miền số có thể vượt kiểu nguyên; nếu cần phát hiện tràn trong phép nhân nguyên, xem `Math.multiplyExact`.

## 4. Làm tròn: `round`, `floor`, `ceil` và `rint`

| Đầu vào | `Math.round(double)` | `Math.floor(double)` | `Math.ceil(double)` |
| --- | ---: | ---: | ---: |
| `2.2` | `2` | `2.0` | `3.0` |
| `2.5` | `3` | `2.0` | `3.0` |
| `-2.2` | `-2` | `-3.0` | `-2.0` |
| `-2.5` | `-2` | `-3.0` | `-2.0` |
| `-2.7` | `-3` | `-3.0` | `-2.0` |

- **`Math.floor(x)`:** số nguyên lớn nhất không vượt quá `x`, nhưng **kiểu trả về là `double`**. Với số âm, `floor(-2.7) == -3.0`.
- **`Math.ceil(x)`:** số nguyên nhỏ nhất không nhỏ hơn `x`, kiểu trả về `double`. Với số âm, `ceil(-2.7) == -2.0`.
- **`Math.round(x)`:** làm tròn về số nguyên gần nhất; khi đúng giữa hai số nguyên, chọn số **về phía dương**. Vì vậy `round(2.5) == 3` nhưng `round(-2.5) == -2`, không phải -3.
- **`Math.rint(x)`:** trả `double`, trường hợp đúng nửa chọn **số nguyên chẵn gần nhất** (*ties to even*): `rint(2.5) == 2.0` và `rint(3.5) == 4.0`.

Không nhầm `Math.round` với cách làm tròn luôn ra xa số 0. Giá trị `Double.NaN` và vô cực có xử lý đặc biệt trong `round`; nếu nghiệp vụ cần số hữu hạn, kiểm tra `Double.isFinite` trước.

## 5. Chương trình Java 17+ chạy được

Tạo file **MathBasicsDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public final class MathBasicsDemo {
    public static void main(String[] args) {
        System.out.println("absInt=" + Math.abs(-17));
        System.out.println("absDouble=" + Math.abs(-4.25));
        System.out.println("absMinInt=" + Math.abs(Integer.MIN_VALUE));
        System.out.println("absMinAsLong="
                + Math.abs((long) Integer.MIN_VALUE));

        try {
            System.out.println("absExact="
                    + Math.absExact(Integer.MIN_VALUE));
        } catch (ArithmeticException ex) {
            System.out.println("absExact=ArithmeticException");
        }

        System.out.println("power=" + Math.pow(2, 10));
        System.out.println("negativePower=" + Math.pow(4, -1));
        System.out.println("rootViaPow=" + Math.pow(9, 0.5));
        System.out.println("negativeRootNaN="
                + Double.isNaN(Math.pow(-2, 0.5)));

        int roundedFloat = Math.round(2.5f);
        long roundedDouble = Math.round(2.5);
        System.out.println("roundFloat=" + roundedFloat);
        System.out.println("roundDouble=" + roundedDouble);
        System.out.println("roundNegative=" + Math.round(-2.5));
        System.out.println("roundBelowHalf=" + Math.round(2.49));

        System.out.println("floorPositive=" + Math.floor(2.7));
        System.out.println("ceilPositive=" + Math.ceil(2.7));
        System.out.println("floorNegative=" + Math.floor(-2.7));
        System.out.println("ceilNegative=" + Math.ceil(-2.7));
        System.out.println("rintEven2=" + Math.rint(2.5));
        System.out.println("rintEven4=" + Math.rint(3.5));

        BigDecimal value = new BigDecimal("2.345");
        System.out.println("moneyHalfUp="
                + value.setScale(2, RoundingMode.HALF_UP));
        System.out.println("moneyHalfEven="
                + value.setScale(2, RoundingMode.HALF_EVEN));
    }
}
~~~

Mở terminal tại thư mục chứa file và chạy (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 MathBasicsDemo.java
java MathBasicsDemo
~~~

**Expected output chính xác:**

~~~text
absInt=17
absDouble=4.25
absMinInt=-2147483648
absMinAsLong=2147483648
absExact=ArithmeticException
power=1024.0
negativePower=0.25
rootViaPow=3.0
negativeRootNaN=true
roundFloat=3
roundDouble=3
roundNegative=-2
roundBelowHalf=2
floorPositive=2.0
ceilPositive=3.0
floorNegative=-3.0
ceilNegative=-2.0
rintEven2=2.0
rintEven4=4.0
moneyHalfUp=2.35
moneyHalfEven=2.34
~~~

Giải thích các dòng dễ nhầm: `absMinInt` vẫn âm vì không có `int` dương tương ứng; `absExact` chủ động phát hiện tràn; `negativeRootNaN` là true vì lũy thừa có cơ số âm và số mũ phân số không cho giá trị thực; `roundNegative=-2` do quy tắc chọn phía dương tại điểm chính giữa. Hai kiểu làm tròn `BigDecimal` thể hiện chính sách khác nhau với chữ số 5.

## 6. Khi nào nên dùng API nào?

| Bài toán | API gợi ý | Cần kiểm tra thêm |
| --- | --- | --- |
| Độ lớn sai lệch, bỏ dấu | `Math.abs` | `MIN_VALUE` của `int`/`long` |
| Trị tuyệt đối nguyên, không chấp nhận tràn | `Math.absExact` | Bắt/đưa tiếp `ArithmeticException` |
| Lũy thừa thực | `Math.pow` | `NaN`, vô cực, sai số `double` |
| Căn bậc hai số không âm | `Math.sqrt` | Đầu vào âm cho `NaN` |
| Làm tròn gần nhất theo `Math` | `Math.round` | Quy tắc nửa về phía dương, kiểu trả về |
| Luôn làm tròn xuống / lên | `Math.floor` / `Math.ceil` | Số âm và kiểu `double` |
| Nửa chọn số nguyên chẵn | `Math.rint` | Kiểu trả về `double` |
| Tiền tệ cần quy định số chữ số thập phân | `BigDecimal.setScale` | Chọn `RoundingMode` theo nghiệp vụ |

**Đừng chuyển `double` sang `int` để “làm tròn”**: ép kiểu số thực sang số nguyên bỏ phần lẻ theo hướng về 0, không tương đương với `Math.round` hay `Math.floor`. Tính tiền hoặc số liệu cần thập phân chính xác phải quy định rõ độ chính xác, không chỉ gọi `Math.round(x * 100) / 100.0` rồi mặc định tránh được sai số nhị phân.

## 7. Bài tập tự luyện

**Bài 1.** Tính `Math.abs(-25)` và `Math.abs(-3.75)`. Chúng trả về kiểu nào?

**Bài 2.** Vì sao `Math.abs(Integer.MIN_VALUE)` vẫn âm? Viết hai cách xử lý: chuyển sang `long` trước, hoặc phát hiện lỗi bằng `Math.absExact`.

**Bài 3.** Dự đoán `Math.pow(2, 5)`, `Math.pow(4, -1)` và `Math.pow(-2, 0.5)`. Kết quả thuộc kiểu gì?

**Bài 4.** So sánh `Math.round(-2.5)`, `Math.floor(-2.5)`, `Math.ceil(-2.5)` và `Math.rint(2.5)`. Chú ý quy tắc tại giá trị đúng nửa.

**Bài 5.** Chọn một `RoundingMode` thích hợp cho báo giá thập phân có hai chữ số; nêu vì sao phải ghi rõ chính sách làm tròn trước khi cài đặt.

### Ghi nhớ

`Math.abs` tính trị tuyệt đối nhưng có ngoại lệ với giá trị nhỏ nhất của `int`/`long`; `Math.pow` trả `double` và có thể mang sai số/`NaN`. `Math.round` làm tròn gần nhất (đúng nửa chọn phía dương), còn `Math.floor` và `Math.ceil` luôn về phía âm/dương vô cực; `Math.rint` chọn số chẵn khi đúng nửa. Hãy chọn hàm theo **kiểu dữ liệu và chính sách làm tròn** thật sự cần.
