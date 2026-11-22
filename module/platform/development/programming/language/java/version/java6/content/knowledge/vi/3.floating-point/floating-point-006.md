# NaN, vô cực và số không có dấu

`float` và `double` không chỉ chứa các số hữu hạn. Chúng còn có NaN, hai vô cực và hai số không có dấu. Những giá trị này giúp phép tính số thực biểu diễn các tình huống như kết quả không xác định, tràn phạm vi hoặc tiến sát không.

Chương trình có thể tiếp tục chạy khi các giá trị đặc biệt xuất hiện. Vì vậy, “không có ngoại lệ” chưa đủ để kết luận kết quả có ý nghĩa với thuật toán.

## 1. Bản đồ các giá trị

| Nhóm | Ví dụ double | Ý nghĩa cần nhớ |
| --- | --- | --- |
| Hữu hạn khác không | `1.5`, `-2.0` | Có độ lớn trong phạm vi biểu diễn |
| Số không dương | `+0.0` | Giá trị không với dấu dương |
| Số không âm | `-0.0` | Giá trị không với dấu âm |
| Vô cực | `Double.POSITIVE_INFINITY`, `Double.NEGATIVE_INFINITY` | Giá trị vô hạn có dấu trong mô hình số thực |
| NaN | `Double.NaN` | Not a Number, kết quả không phải một giá trị số thông thường |

`float` có các nhóm tương ứng qua lớp `Float`. Các quy tắc trong bài áp dụng cùng tinh thần cho cả hai kiểu; ví dụ dùng `double` để giữ mã ngắn.

NaN không phải `null`. NaN là một giá trị số thực; `null` là giá trị tham chiếu, không gán trực tiếp được cho biến `double`.

Xem [JLS: các kiểu và giá trị số thực](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.3).

## 2. Những phép tính có thể tạo giá trị đặc biệt

Các ví dụ sau là phép tính số thực:

| Phép tính | Kết quả |
| --- | --- |
| `0.0 / 0.0` | NaN |
| `1.0 / +0.0` | `+Infinity` |
| `1.0 / -0.0` | `-Infinity` |
| `Double.MAX_VALUE * 2.0` | `+Infinity` |
| `Infinity - Infinity` cùng dấu | NaN |
| `0.0 * Infinity` | NaN |

Phép tràn của số thực không có cùng hành vi với số nguyên. Chẳng hạn, phép chia số nguyên cho không ở lúc chạy gây `ArithmeticException`, còn phép chia số thực theo các tình huống trên cho giá trị đặc biệt.

Xem [JLS: phép chia](https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.17.2) và [các phép toán số thực](https://docs.oracle.com/javase/specs/jls/se25/html/jls-4.html#jls-4.2.4).

Đừng ghi literal thập phân vượt phạm vi như một cách thử tràn trong mã nguồn rồi mong nó chạy: compiler có quy tắc kiểm tra literal. Ví dụ thực hành tạo tràn bằng một phép nhân giữa các giá trị hợp lệ.

## 3. Chương trình hoàn chỉnh

Tạo tệp `SpecialFloatingPointDemo.java`:

```java
public class SpecialFloatingPointDemo {
    public static void main(String[] args) {
        double zero = 0.0;
        double nan = zero / zero;
        double positiveInfinity = 1.0 / zero;
        double negativeInfinity = -1.0 / zero;
        double negativeZero = -0.0;

        System.out.println("nan=" + nan);
        System.out.println("positive.infinity=" + positiveInfinity);
        System.out.println("negative.infinity=" + negativeInfinity);
        System.out.println("overflow=" + (Double.MAX_VALUE * 2.0));
        System.out.println("nan.equal=" + (nan == nan));
        System.out.println("nan.not-equal=" + (nan != nan));
        System.out.println("nan.less=" + (nan < 10.0));
        System.out.println("nan.greater-or-equal=" + (nan >= 10.0));
        System.out.println("nan.detected=" + Double.isNaN(nan));
        System.out.println("infinity.detected=" + Double.isInfinite(positiveInfinity));
        System.out.println("nan.finite=" + Double.isFinite(nan));
        System.out.println("infinity.finite=" + Double.isFinite(positiveInfinity));
        System.out.println("zero.finite=" + Double.isFinite(negativeZero));
        System.out.println("zeros.equal=" + (zero == negativeZero));
        System.out.println("negative-zero.less=" + (negativeZero < zero));
        System.out.println("positive-zero.reciprocal=" + (1.0 / zero));
        System.out.println("negative-zero.reciprocal=" + (1.0 / negativeZero));
        System.out.println("negative-underflow=" + (-Double.MIN_VALUE / 2.0));
        System.out.println("infinity-minus-itself=" + (positiveInfinity - positiveInfinity));
        System.out.println("zero-times-infinity=" + (zero * positiveInfinity));
        System.out.println("nan.wrapper-equal=" + Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));
        System.out.println("zero.wrapper-equal=" + Double.valueOf(zero).equals(Double.valueOf(negativeZero)));
        System.out.println("compare.nan-infinity=" + Double.compare(nan, positiveInfinity));
        System.out.println("compare.negative-positive-zero=" + Double.compare(negativeZero, zero));

        int integerZero = 0;
        try {
            System.out.println(1 / integerZero);
        } catch (ArithmeticException e) {
            System.out.println("integer.divide-by-zero=ArithmeticException");
        }
    }
}
```

Biên dịch và chạy trên JDK 17 trở lên, từ thư mục chứa tệp:

```powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -d out SpecialFloatingPointDemo.java
java -cp out SpecialFloatingPointDemo
```

Lưu mã UTF-8 không BOM. Stdout đã kiểm chứng trên Microsoft OpenJDK 21.0.9:

```text
nan=NaN
positive.infinity=Infinity
negative.infinity=-Infinity
overflow=Infinity
nan.equal=false
nan.not-equal=true
nan.less=false
nan.greater-or-equal=false
nan.detected=true
infinity.detected=true
nan.finite=false
infinity.finite=false
zero.finite=true
zeros.equal=true
negative-zero.less=false
positive-zero.reciprocal=Infinity
negative-zero.reciprocal=-Infinity
negative-underflow=-0.0
infinity-minus-itself=NaN
zero-times-infinity=NaN
nan.wrapper-equal=true
zero.wrapper-equal=false
compare.nan-infinity=1
compare.negative-positive-zero=-1
integer.divide-by-zero=ArithmeticException
```

`Double.isFinite` là API hiện đại có từ Java 8; nó được dùng ở đây để thực hành rõ ràng trên JDK đang dùng. Các khái niệm giá trị đặc biệt không phải đều mới xuất hiện ở Java 6.

## 4. NaN phá vỡ giả định “chắc chắn nhỏ hơn, bằng hoặc lớn hơn”

Với `n` là NaN:

| Biểu thức | Kết quả |
| --- | --- |
| `n == n` | `false` |
| `n != n` | `true` |
| `n < x` | `false` |
| `n <= x` | `false` |
| `n > x` | `false` |
| `n >= x` | `false` |

Các quan hệ thứ tự trên cũng trả `false` khi NaN ở phía còn lại. NaN không phải một số “rất lớn” mà các toán tử sẽ xếp sau vô cực.

Do đó, mã minh họa này có lỗi nếu cần bảo đảm đầu vào hữu hạn trong khoảng:

```java
if (value < 0.0 || value > 100.0) {
    throw new IllegalArgumentException("Out of range");
}
```

NaN khiến cả hai phép so sánh đều `false`, nên lọt qua.

Nếu hợp đồng là “hữu hạn, từ 0 đến 100”, viết rõ:

```java
if (!Double.isFinite(value) || value < 0.0 || value > 100.0) {
    throw new IllegalArgumentException("Expected a finite value in [0, 100]");
}
```

Đây là đoạn áp dụng khi đã có biến `value`. Không tự thay NaN bằng không trừ khi quy tắc dữ liệu chủ động định nghĩa như vậy; việc thay có thể che giấu nguồn lỗi.

Dùng `Double.isNaN(value)` để nhận NaN. Viết `value == Double.NaN` không phải phép kiểm tra đúng.

## 5. Vô cực có thứ tự, nhưng không có mọi tính chất của số hữu hạn

Với `x` hữu hạn:

```text
-Infinity < x < +Infinity
```

Hai vô cực cùng dấu bằng nhau qua `==`. Chúng hữu ích trong một số thuật toán làm cận hoặc giá trị khởi tạo, nhưng phải xét hợp đồng của phép tính tiếp theo.

Chẳng hạn, trừ một vô cực khỏi chính nó không khôi phục về không. Chương trình nhận:

```text
infinity-minus-itself=NaN
```

Tương tự, nhân không với vô cực không cho kết quả không. NaN có thể xuất hiện sau một bước trung gian đã tràn, dù đầu vào ban đầu đều hữu hạn.

Vì vậy, khi điều tra một chuỗi phép tính, hãy tìm **bước đầu tiên** tạo vô cực hoặc NaN. Chỉ kiểm tra kết quả cuối thường làm khó xác định nguyên nhân.

## 6. Hai số không bằng nhau qua == nhưng vẫn khác nhau

Trong chương trình:

```text
zeros.equal=true
negative-zero.less=false
```

`-0.0` không nhỏ hơn `+0.0` theo các toán tử thứ tự số học. Nhưng:

```text
positive-zero.reciprocal=Infinity
negative-zero.reciprocal=-Infinity
```

cho thấy không thể thay thế tùy ý hai số không trong mọi biểu thức.

`negative-underflow=-0.0` còn cho thấy số không âm có thể là kết quả của việc một số âm rất nhỏ bị làm tròn về không. Nó không chỉ đến từ cách gõ literal `-0.0`.

Nếu cần kiểm tra dấu bao gồm cả `-0.0`, không dùng riêng `value < 0.0`. Với nhu cầu sao chép dấu, có API như `Math.copySign`; với nhu cầu quan sát biểu diễn, có `Double.doubleToRawLongBits`. Chọn công cụ theo câu hỏi thay vì ép mọi phép kiểm tra về so sánh với không.

Trong quy tắc phạm vi `[0,100]` ở trên, `-0.0` được chấp nhận vì nó là số hữu hạn và bằng không về số học. Nếu dữ liệu cần phân biệt dấu của không, phải thêm một điều kiện được nêu rõ.

## 7. ==, Double.equals và Double.compare trả lời khác nhau

Các toán tử trên kiểu nguyên thủy theo quy tắc số học không phải hợp đồng duy nhất trong Java. Lớp bao `Double` cung cấp quy tắc phù hợp cho so sánh đối tượng và thứ tự tổng.

| Câu hỏi | NaN so với NaN | -0.0 so với +0.0 |
| --- | --- | --- |
| `double` qua `==` | Không bằng | Bằng |
| `Double.equals` | Bằng | Không bằng |
| `Double.compare` | Bằng theo thứ tự | -0.0 đứng trước +0.0 |

`Double.compare` còn đặt NaN sau `+Infinity`. Đây là hợp đồng thứ tự của phương thức, không phải thay đổi kết quả toán tử `>` trên NaN.

Vì vậy, stdout:

```text
nan.wrapper-equal=true
zero.wrapper-equal=false
compare.nan-infinity=1
compare.negative-positive-zero=-1
```

không mâu thuẫn với phần so sánh trước đó. Ta đang đặt các câu hỏi theo các hợp đồng khác nhau.

Tài liệu [Double: equality, equivalence và comparison](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Double.html) giải thích các quy tắc này. Khi dữ liệu dùng làm khóa hoặc được sắp xếp bằng cơ chế lớp bao, phải đọc đúng hợp đồng thay vì áp quy tắc của `double ==`.

Ngoài ra, `==` giữa hai biến `Double` đều là tham chiếu có thể là phép so sánh tham chiếu. Đừng dùng nó thay cho `equals` hoặc phép so sánh số đã chủ động chọn.

## 8. Phân loại đầu vào trước khi xử lý

Một đoạn minh họa dễ đọc:

```java
if (Double.isNaN(value)) {
    // Xử lý trường hợp không phải số.
} else if (Double.isInfinite(value)) {
    // Xử lý cận vô hạn hoặc từ chối theo hợp đồng.
} else {
    // Giá trị hữu hạn, bao gồm +0.0 và -0.0.
}
```

Đoạn này mô tả cấu trúc phân loại, không phải một chương trình độc lập.

Nếu ứng dụng chỉ cho phép hữu hạn, điều kiện `Double.isFinite(value)` thể hiện trực tiếp yêu cầu. Nếu một thuật toán dùng vô cực làm cận hợp lệ, không nên từ chối nó chỉ vì một quy tắc chung không liên quan.

Những phép phân loại này cũng không chứng minh giá trị đã đáp ứng mọi điều kiện: một số hữu hạn vẫn có thể sai đơn vị, sai khoảng hoặc là kết quả tính toán không chính xác cho mục tiêu đang xét.

Nếu dữ liệu được bọc trong `Double` có thể `null`, cần xử lý thiếu tham chiếu trước khi tự động mở hộp để gọi các phương thức nhận `double`.

## 9. Lỗi thường gặp

| Cách nghĩ/cách viết | Vấn đề |
| --- | --- |
| Dùng `x == Double.NaN` | Không nhận NaN |
| Chỉ bắt ArithmeticException để phát hiện lỗi số thực | Nhiều phép tạo NaN/vô cực vẫn trả bình thường |
| Coi NaN như vô cực dương | Sai quy tắc so sánh và ý nghĩa |
| Từ `+0.0 == -0.0` suy ra mọi phép tính giống nhau | Bỏ qua ảnh hưởng của dấu |
| Dùng kiểm tra ngoài khoảng mà không xét NaN | NaN có thể qua nhánh kiểm tra |
| Áp kết quả `Double.compare` cho toán tử `>` | Trộn hai hợp đồng |
| Thay NaN bằng 0 ngay khi nhìn thấy | Có thể mất dấu vết lỗi tính toán |

## 10. Tự kiểm tra

1. Vì sao `NaN != NaN` là `true`, nhưng hai đối tượng Double chứa NaN lại có thể `equals` nhau?
2. Vì sao kiểm tra `value <= 0` chưa đủ để từ chối mọi đầu vào không hợp lệ nếu NaN không được phép?
3. Viết một trường hợp tạo `-0.0` mà không chỉ gán literal trực tiếp.
4. Vì sao `Infinity - Infinity` không phải phép trừ thông thường để lấy 0?
5. Khi nào kiểm tra hữu hạn là quy tắc phù hợp, và khi nào thuật toán có thể chủ động chấp nhận vô cực?

Đọc giá trị đặc biệt theo ba lớp: **nó được tạo ra thế nào, phép so sánh nào đang dùng, và hợp đồng thuật toán có chấp nhận nó không**. Làm rõ cả ba giúp chương trình xử lý số thực đúng thay vì chỉ tiếp tục chạy.
