# negate, abs, plus, min, max và signum trong BigDecimal

## 1. Mục tiêu và bối cảnh

Trong Java, BigDecimal biểu diễn số thập phân với độ chính xác tùy ý, phù hợp khi cần kiểm soát chữ số và cách làm tròn (ví dụ tiền tệ). Nhóm phương thức này phục vụ hai việc khác nhau:

- **Tác động lên dấu hoặc trị tuyệt đối:** negate(), abs(), plus().
- **Xác định dấu hoặc chọn số theo thứ tự:** signum(), min(BigDecimal), max(BigDecimal).

Đây là các phương thức của java.math.BigDecimal. Chúng **không thay đổi đối tượng gốc** vì BigDecimal là kiểu bất biến (immutable). Kết quả là một giá trị BigDecimal hoặc, riêng signum(), một số nguyên int.

BigDecimal lưu giá trị theo dạng unscaledValue × 10^(-scale). Ví dụ, -12.340 có scale = 3. Hai số 2.0 và 2.00 có giá trị số học bằng nhau nhưng scale khác nhau; điều này ảnh hưởng đến kết quả biểu diễn khi dùng min/max.

## 2. Bảng tra cứu nhanh

| Phương thức | Ý nghĩa | Kết quả | Đặc điểm quan trọng |
| --- | --- | --- | --- |
| negate() | Đổi dấu x thành -x | BigDecimal | Giữ scale của x |
| abs() | Trị tuyệt đối | BigDecimal | Số âm thành dương; số không và số dương giữ nguyên giá trị |
| plus() | Dấu cộng đơn ngôi +x | BigDecimal | Không cộng thêm 1; không đổi giá trị hay scale |
| min(y) | Chọn giá trị nhỏ hơn giữa x và y | BigDecimal | Dựa trên compareTo(); khi hai giá trị bằng nhau, trả x (đối tượng gọi) |
| max(y) | Chọn giá trị lớn hơn giữa x và y | BigDecimal | Dựa trên compareTo(); khi hai giá trị bằng nhau, trả x (đối tượng gọi) |
| signum() | Xác định dấu của x | int | -1 nếu âm, 0 nếu bằng không, 1 nếu dương |

Ở bảng trên, x là BigDecimal nhận lời gọi phương thức; y là tham số BigDecimal khác. min() và max() không có phiên bản nhận MathContext.

## 3. negate(), abs(), plus(): ba phép toán đơn ngôi

- **x.negate()** cho giá trị đối của x. Số dương thành âm, số âm thành dương; với 0, dấu số học vẫn là 0.
- **x.abs()** cho độ lớn không âm của x. Có thể hình dung là x khi x không âm, hoặc x.negate() khi x âm.
- **x.plus()** là phép cộng đơn ngôi, giống ý nghĩa toán học của +x. Nó hữu ích nhất khi dùng cùng MathContext để áp dụng độ chính xác/làm tròn.

Ba phương thức không tham số bảo toàn scale, kể cả các số 0 có phần thập phân. Ví dụ, -12.340.negate() cho 12.340 chứ không tự rút gọn thành 12.34.

### Ví dụ Java 17: đổi dấu và giữ nguyên dữ liệu gốc

Lưu thành BigDecimalUnaryDemo.java:

~~~java
import java.math.BigDecimal;

public class BigDecimalUnaryDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("-12.340");

        System.out.println("x       = " + x);
        System.out.println("negate  = " + x.negate());
        System.out.println("abs     = " + x.abs());
        System.out.println("plus    = " + x.plus());
        System.out.println("signum  = " + x.signum());
        System.out.println("scale   = " + x.scale());
        System.out.println("x after = " + x);
    }
}
~~~

Chạy bằng JDK 17 trở lên:

~~~bash
javac BigDecimalUnaryDemo.java
java BigDecimalUnaryDemo
~~~

Đầu ra:

~~~text
x       = -12.340
negate  = 12.340
abs     = 12.340
plus    = -12.340
signum  = -1
scale   = 3
x after = -12.340
~~~

Lệnh cuối cho thấy lời gọi không sửa x. Không dùng toán tử trừ đơn ngôi hoặc Math.abs(x) với BigDecimal; hãy gọi trực tiếp negate() và abs().

### Số 0 và biểu diễn

~~~java
import java.math.BigDecimal;

public class BigDecimalZeroDemo {
    public static void main(String[] args) {
        BigDecimal z = new BigDecimal("-0.00");
        System.out.println(z);               // 0.00
        System.out.println(z.negate());      // 0.00
        System.out.println(z.abs());         // 0.00
        System.out.println(z.signum());      // 0
        System.out.println(z.scale());       // 2
        System.out.println(z.compareTo(BigDecimal.ZERO)); // 0
    }
}
~~~

BigDecimal không duy trì một dấu âm có ý nghĩa số học riêng cho zero. Chuỗi đầu vào "-0.00" trở thành giá trị 0.00 với scale 2; signum() vẫn trả 0. Nếu chỉ cần nhận biết có bằng 0 hay không, dùng signum() == 0 hoặc compareTo(BigDecimal.ZERO) == 0; đừng so sánh chuỗi hiển thị.

## 4. signum(): quyết định theo dấu mà không làm mất độ chính xác

signum() trả về đúng ba trạng thái:

| Giá trị | Kết quả signum() | Ý nghĩa |
| --- | ---: | --- |
| -0.001 | -1 | Âm |
| 0, 0.00, -0.00 | 0 | Bằng không |
| 0.001 | 1 | Dương |

Dùng khi nghiệp vụ rẽ nhánh theo âm/dương/không, chẳng hạn phân loại biến động số dư:

~~~java
import java.math.BigDecimal;

public class BigDecimalSignDemo {
    static String describe(BigDecimal amount) {
        return switch (amount.signum()) {
            case -1 -> "decrease";
            case 0 -> "unchanged";
            case 1 -> "increase";
            default -> throw new IllegalStateException("Unexpected sign");
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new BigDecimal("-7.50")));
        System.out.println(describe(new BigDecimal("0.00")));
        System.out.println(describe(new BigDecimal("7.50")));
    }
}
~~~

Đầu ra:

~~~text
decrease
unchanged
increase
~~~

signum() không phải phép làm tròn và không phụ thuộc scale. Không suy ra số chữ số, độ lớn hay dấu gốc của chuỗi văn bản từ kết quả -1/0/1.

## 5. min() và max(): so sánh giá trị số học

Với x.min(y), phương thức trả về giá trị nhỏ hơn; với x.max(y), trả về giá trị lớn hơn. Cả hai dùng thứ tự tự nhiên của BigDecimal, tức kết quả compareTo().

Quy tắc chọn cụ thể:

- Nếu x.compareTo(y) < 0, x.min(y) trả x và x.max(y) trả y.
- Nếu x.compareTo(y) > 0, x.min(y) trả y và x.max(y) trả x.
- Nếu x.compareTo(y) == 0, **cả x.min(y) và x.max(y) đều trả x**, kể cả khi scale của x và y khác nhau.

### Ví dụ Java 17: thứ tự và scale

Lưu thành BigDecimalMinMaxDemo.java:

~~~java
import java.math.BigDecimal;

public class BigDecimalMinMaxDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal c = new BigDecimal("3.5");

        System.out.println("min(a,c) = " + a.min(c));
        System.out.println("max(a,c) = " + a.max(c));
        System.out.println("compare  = " + a.compareTo(b));
        System.out.println("equals   = " + a.equals(b));
        System.out.println("min(a,b) = " + a.min(b));
        System.out.println("min(b,a) = " + b.min(a));
        System.out.println("max(a,b) = " + a.max(b));
    }
}
~~~

Chạy:

~~~bash
javac BigDecimalMinMaxDemo.java
java BigDecimalMinMaxDemo
~~~

Đầu ra:

~~~text
min(a,c) = 2.0
max(a,c) = 3.5
compare  = 0
equals   = false
min(a,b) = 2.0
min(b,a) = 2.00
max(a,b) = 2.0
~~~

**Điểm dễ nhầm:** compareTo() xem 2.0 và 2.00 là bằng nhau về mặt số học; equals() còn xét scale nên trả false. min/max chọn theo compareTo(), không theo equals(). Trường hợp bằng nhau, toán hạng đứng bên trái quyết định cách biểu diễn/scale của kết quả. Vì vậy kết quả của min(a,b) có thể hiển thị khác min(b,a) dù cùng giá trị.

min/max không tự làm tròn, không đổi scale của BigDecimal được chọn và không cộng/trừ hai số. Để giới hạn một giá trị vào đoạn [lower, upper] khi lower <= upper, có thể dùng x.max(lower).min(upper); cần định nghĩa trước chính sách scale nếu kết quả sẽ được lưu hoặc hiển thị theo chuẩn cố định.

## 6. Các phiên bản nhận MathContext

negate(MathContext), abs(MathContext) và plus(MathContext) có overload cho phép **áp dụng độ chính xác (precision) và quy tắc làm tròn**. Chúng trả về kết quả tương ứng được làm tròn theo MathContext. MathContext kiểm soát **số chữ số có nghĩa**, không đồng nghĩa với số chữ số sau dấu thập phân; muốn cố định số lẻ thường dùng setScale() với RoundingMode phù hợp.

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalContextDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("-123.4567");
        MathContext mc = new MathContext(4, RoundingMode.HALF_UP);

        System.out.println("original    = " + x);
        System.out.println("plus(mc)    = " + x.plus(mc));
        System.out.println("negate(mc)  = " + x.negate(mc));
        System.out.println("abs(mc)     = " + x.abs(mc));
        System.out.println("exact abs   = " + x.abs());
    }
}
~~~

Đầu ra:

~~~text
original    = -123.4567
plus(mc)    = -123.5
negate(mc)  = 123.5
abs(mc)     = 123.5
exact abs   = 123.4567
~~~

Ở đây 4 là **precision = 4 chữ số có nghĩa**; chữ số tiếp theo là 5 nên HALF_UP làm tròn. Không có MathContext, ba phép toán đơn ngôi giữ độ chính xác ban đầu. Với MathContext.UNLIMITED (precision = 0), không yêu cầu làm tròn. RoundingMode.UNNECESSARY cùng một precision không đủ lớn có thể phát sinh ArithmeticException nếu kết quả bắt buộc làm tròn.

Đặc biệt, plus(mc) không đồng nghĩa cộng thêm số dương nào: nó áp dụng phép cộng đơn ngôi rồi làm tròn theo mc. Việc dùng MathContext cho nghiệp vụ tính tiền phải tuân thủ quy tắc làm tròn thực tế của nghiệp vụ.

## 7. Tình huống ứng dụng: xử lý số dư và giới hạn

Giả sử một khoản điều chỉnh có dấu âm biểu thị tiền rời tài khoản. Ta có thể:

1. Dùng signum() để phân loại chiều biến động.
2. Dùng abs() để hiển thị độ lớn của khoản điều chỉnh.
3. Dùng negate() để tạo giá trị đảo chiều cho bút toán hoàn tác (khi quy tắc nghiệp vụ cho phép).
4. Dùng min()/max() để áp dụng các ngưỡng số học.

~~~java
import java.math.BigDecimal;

public class BigDecimalBusinessDemo {
    public static void main(String[] args) {
        BigDecimal change = new BigDecimal("-125.50");
        BigDecimal lower = new BigDecimal("-100.00");
        BigDecimal upper = new BigDecimal("100.00");

        BigDecimal limited = change.max(lower).min(upper);

        System.out.println("sign    = " + change.signum());
        System.out.println("display = " + change.abs());
        System.out.println("reverse = " + change.negate());
        System.out.println("limited = " + limited);
        System.out.println("source  = " + change);
    }
}
~~~

Đầu ra:

~~~text
sign    = -1
display = 125.50
reverse = 125.50
limited = -100.00
source  = -125.50
~~~

Đoạn này minh họa biến đổi giá trị, **không tự thực hiện giao dịch tài chính**. Ví dụ cũng cho thấy kẹp giá trị (clamp) chỉ giới hạn số; việc chọn ngưỡng và tạo bút toán đảo chiều phải thuộc về quy tắc nghiệp vụ. Khi dữ liệu cần 2 chữ số thập phân, thống nhất scale/rounding tại ranh giới nhập, lưu và xuất thay vì giả định min/max luôn trả scale 2.

## 8. Lỗi thường gặp và cách tránh

1. **Nhầm plus() với add().** x.plus() giữ giá trị x; để cộng hai BigDecimal dùng x.add(y). Tương tự, negate() chỉ đảo dấu, còn x.subtract(y) mới là phép trừ hai số.
2. **Dùng toán tử của kiểu nguyên thủy.** BigDecimal không dùng trực tiếp +, -, <, > hoặc Math.abs(BigDecimal). Dùng add/subtract/compareTo/abs/negate theo API.
3. **Nhầm so sánh bằng với equals().** x.equals(y) có thể false khi scale khác; x.compareTo(y) == 0 kiểm tra bằng nhau theo giá trị số học. min/max dùng compareTo().
4. **Giả định min/max chuẩn hóa dữ liệu.** Trong trường hợp hai giá trị bằng nhau, chúng chọn toán hạng gọi phương thức; không tự ép scale. Nếu cần chuẩn hóa, áp dụng setScale(...) theo quy tắc riêng.
5. **Cấp BigDecimal bằng new BigDecimal(0.1).** Constructor nhận double giữ đúng giá trị nhị phân đã được biểu diễn gần đúng, có thể gây số thập phân dài bất ngờ. Với hằng số thập phân dùng new BigDecimal("0.1") hoặc BigDecimal.valueOf(0.1).
6. **Để null làm đối số.** x.min(null) hoặc x.max(null) gây NullPointerException. Bảo đảm x và đối số là BigDecimal hợp lệ trước khi gọi.
7. **Nhầm MathContext precision với scale.** new MathContext(4) thường giới hạn 4 chữ số có nghĩa, không phải 4 chữ số lẻ. Đừng làm tròn tùy tiện nếu độ chính xác nguyên gốc còn cần thiết.
8. **Tưởng đổi dấu làm thay đổi biến nguồn.** BigDecimal immutable; cần lưu kết quả, ví dụ x = x.negate(), khi thật sự muốn biến x trỏ tới đối tượng mang giá trị mới.
9. **Kiểm tra số âm bằng chuỗi.** signum() xử lý chính xác cả 0.00; kiểm tra chuỗi bắt đầu bằng dấu '-' không phải phép kiểm tra dấu số học tin cậy.

## 9. Tự kiểm tra

**Câu 1.** Với x = new BigDecimal("-0.000"), x.signum() bằng bao nhiêu? x.abs().scale() bằng bao nhiêu?

**Đáp án:** 0 và 3. BigDecimal nhận giá trị zero, giữ scale là 3 khi gọi abs() không tham số.

**Câu 2.** Cho a = new BigDecimal("1.0"), b = new BigDecimal("1.00"). a.min(b) và b.min(a) có hiển thị như nhau không?

**Đáp án:** a.min(b) là 1.0, b.min(a) là 1.00. compareTo() bằng 0 nên nhận lại toán hạng gọi phương thức.

**Câu 3.** Muốn đổi -9.25 thành 9.25 thì dùng phương thức gì? Nếu x đã dương, abs() có làm x âm không?

**Đáp án:** x.negate() hoặc x.abs() đều cho 9.25 khi x = -9.25, nhưng ý nghĩa khác nhau; abs() không bao giờ làm một số dương trở thành âm.

**Câu 4.** Điều gì khác nhau giữa new BigDecimal("12.3456").plus() và .plus(new MathContext(4, RoundingMode.HALF_UP))?

**Đáp án:** plus() giữ 12.3456; phiên bản nhận MathContext làm tròn còn 12.35 (4 chữ số có nghĩa).

## 10. Ghi nhớ

- **negate()** đảo dấu; **abs()** lấy độ lớn không âm; **plus()** giữ giá trị (hoặc áp dụng làm tròn khi truyền MathContext).
- **signum()** trả -1/0/1 để kiểm tra dấu chính xác.
- **min()/max()** chọn theo compareTo(); khi bằng nhau, trả toán hạng gọi phương thức và giữ biểu diễn của nó.
- BigDecimal bất biến, scale có ý nghĩa, và việc làm tròn phải được chỉ định rõ khi cần.

Tham khảo API chuẩn trong tài liệu Java SE 17: java.math.BigDecimal, java.math.MathContext và java.math.RoundingMode.