# Chi phí BigDecimal theo precision và scale

## 1. Vì sao hiệu năng BigDecimal phụ thuộc dữ liệu?

`BigDecimal` trong Java dùng để tính toán giá trị thập phân với độ chính xác tùy ý. Nó cho phép cộng, trừ, nhân, chia và làm tròn theo các quy tắc kiểm soát được, nhưng thường cần nhiều bộ nhớ và công việc hơn kiểu nguyên thủy `long` hoặc `double`. Hai phép `add` nhìn giống nhau trong source code có thể chênh lệch chi phí rất lớn: một phép cộng hai số vài chữ số và một phép cộng giữa `1E+1000000` với `1` đều gọi `add`, nhưng kết quả chính xác của trường hợp thứ hai cần khoảng một triệu chữ số nguyên.

Để phân tích hiệu năng cần hiểu **precision**, **scale**, kích thước số nguyên chưa đặt dấu thập phân, chênh lệch scale, kết quả trung gian, chế độ làm tròn và việc format chuỗi. Bài này dùng ví dụ Java 17+, chỉ ra các ranh giới đúng/sai khi tối ưu và cách đo thực tế.

## 2. Precision, scale và unscaled value

BigDecimal biểu diễn giá trị theo công thức:

\[
\text{value} = \text{unscaledValue}\times10^{-\text{scale}}.
\]

- **Unscaled value** là số nguyên mang các chữ số của giá trị. Ví dụ, `123.4500` có unscaled value `1234500`.
- **Scale** là số nguyên `int`: `123.4500` có scale 4; `1E+6` có scale -6; `1000` có scale 0. Scale có thể âm.
- **Precision** là số chữ số thập phân của giá trị tuyệt đối unscaled value, không tính các số 0 ở đầu. Với zero, precision là 1. `123.4500` có precision 7, `1E+6` có precision 1.
- **MathContext precision** là giới hạn số chữ số có nghĩa sau phép toán khi chỉ định `MathContext`; nó **không phải** số chữ số sau dấu thập phân.

Precision = 1 không có nghĩa giá trị nhỏ: `1E+1000000` có precision 1 nhưng trị số cực lớn. Scale lớn không có nghĩa precision lớn: `1E-1000000` có precision 1 và scale 1000000.

### Ví dụ 1: đọc metadata của BigDecimal

Lưu thành `BigDecimalMetaDemo.java`:

~~~java
import java.math.BigDecimal;

public class BigDecimalMetaDemo {
    private static void inspect(String source) {
        BigDecimal x = new BigDecimal(source);
        System.out.println(source + ": p=" + x.precision()
                + ", s=" + x.scale());
    }

    public static void main(String[] args) {
        inspect("123.4500");
        inspect("1000.00");
        inspect("1E+6");
        inspect("0.000001");
        inspect("0.00");
    }
}
~~~

Biên dịch/chạy bằng JDK 17:

~~~bash
javac BigDecimalMetaDemo.java
java BigDecimalMetaDemo
~~~

Kết quả:

~~~text
123.4500: p=7, s=4
1000.00: p=6, s=2
1E+6: p=1, s=-6
0.000001: p=1, s=6
0.00: p=1, s=2
~~~

Các số có **giá trị số học bằng nhau** vẫn có thể khác biểu diễn. `2.0` và `2.00` có `compareTo(...) == 0` nhưng `equals(...) == false` vì scale khác nhau; việc chuẩn hóa scale có thể tác động đến khóa bản đồ và dữ liệu hiển thị.

## 3. Biểu diễn nội bộ và chi phí của số nguyên lớn

BigDecimal lưu unscaled value và scale. Trong JDK 17, những giá trị unscaled nhỏ có thể đi qua biểu diễn gọn tương tự `long`; những giá trị lớn hơn có thể cần cấu trúc số nguyên lớn như `BigInteger`. Chi tiết nội bộ và ngưỡng tối ưu hóa có thể thay đổi theo phiên bản JDK, nên đây là lời giải thích cơ chế phổ biến, **không phải hợp đồng thời gian chạy của API**.

Về nguyên tắc, các phép số học trên số nguyên gồm hàng trăm hoặc hàng nghìn chữ số cần nhiều công việc hơn phép toán trên số nguyên nhỏ. Nhân/chia số lớn còn có thể dùng các thuật toán khác nhau theo kích cỡ. BigDecimal là **immutable**: các kết quả logic mới, biểu diễn trung gian và số nguyên lớn có thể gây cấp phát bộ nhớ/GC. Implementation có thể tái sử dụng một số đối tượng hoặc tối ưu đường nhanh trong vài trường hợp, nhưng chương trình không được giả định mọi phép cộng là “không cấp phát”.

Vì vậy, chi phí thực phải đo trên **độ dài chữ số, scale và phép toán cụ thể**, không đoán từ số lượng object BigDecimal hoặc một phép tính tổng quát.

## 4. Cộng và trừ: căn chỉnh scale

Với phép cộng chính xác, các toán hạng cần được đưa về một đơn vị thập phân tương thích:

\[
1.20 + 0.003 = 1.203.
\]

Khi cộng/trừ chính xác, scale kết quả thường là scale lớn hơn trong hai toán hạng. Chênh lệch scale lớn có thể buộc JDK xử lý lũy thừa 10 rất lớn và số nguyên kết quả dài.

Ví dụ:

- `1E+6`: precision 1, scale -6.
- `1`: precision 1, scale 0.
- Tổng **chính xác**: `1000001`, precision 7, scale 0.

Nếu thay `1E+6` bằng `1E+1000000`, kết quả chính xác cộng `1` cần khoảng một triệu chữ số nguyên. Dù hai toán hạng có precision nhỏ, **chênh lệch scale quyết định lượng dữ liệu phải được biểu diễn**.

### Ví dụ 2: so sánh cộng chính xác và có MathContext

Lưu thành `BigDecimalAddDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalAddDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1E+6");
        BigDecimal b = BigDecimal.ONE;

        BigDecimal exact = a.add(b);
        BigDecimal rounded = a.add(b,
                new MathContext(4, RoundingMode.HALF_UP));

        System.out.println("a scale = " + a.scale());
        System.out.println("exact = " + exact.toPlainString());
        System.out.println("exact p = " + exact.precision());
        System.out.println("rounded = " + rounded.toPlainString());
        System.out.println("rounded p = " + rounded.precision());
    }
}
~~~

~~~bash
javac BigDecimalAddDemo.java
java BigDecimalAddDemo
~~~

Kết quả:

~~~text
a scale = -6
exact = 1000001
exact p = 7
rounded = 1000000
rounded p = 4
~~~

`MathContext(4, HALF_UP)` giới hạn bốn chữ số có nghĩa và làm mất đóng góp `1` trong kết quả. Đây là **thay đổi ngữ nghĩa**, không đơn thuần tăng tốc. Một số thuật toán có thể tiết kiệm công việc nhờ precision hữu hạn, nhưng không được khẳng định mọi phép toán có MathContext đều nhanh hơn.

## 5. Nhân: độ dài chữ số và scale có thể tăng

Với `a.multiply(b)` chính xác, scale kết quả thông thường bằng tổng scale của hai toán hạng, nếu còn trong phạm vi hợp lệ. Độ dài unscaled value của tích thường tăng theo số chữ số của cả hai toán hạng. Chi phí nhân số có vài chữ số khác đáng kể nhân hai số có hàng nghìn chữ số.

### Ví dụ 3: scale sản phẩm giữ chữ số 0

Lưu thành `BigDecimalMultiplyDemo.java`:

~~~java
import java.math.BigDecimal;

public class BigDecimalMultiplyDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("12.3400");
        BigDecimal b = new BigDecimal("0.010");
        BigDecimal product = a.multiply(b);

        System.out.println("a scale = " + a.scale());
        System.out.println("b scale = " + b.scale());
        System.out.println("product = " + product.toPlainString());
        System.out.println("product scale = " + product.scale());
        System.out.println("product p = " + product.precision());
    }
}
~~~

~~~bash
javac BigDecimalMultiplyDemo.java
java BigDecimalMultiplyDemo
~~~

Kết quả:

~~~text
a scale = 4
b scale = 3
product = 0.1234000
product scale = 7
product p = 7
~~~

Số 0 cuối của `0.1234000` không làm thay đổi giá trị, nhưng được giữ trong biểu diễn scale 7 của phép nhân chính xác. Lặp phép nhân nhiều lần có thể tạo precision và scale trung gian ngày càng lớn. Chọn làm tròn chỉ khi chính sách độ chính xác của bài toán cho phép.

## 6. Chia: precision, scale và rounding mode tác động trực tiếp

`divide(divisor)` không tự chọn mức làm tròn. Nếu kết quả thập phân vô hạn như `1/3`, phương thức ném `ArithmeticException`. Các overload nhận tham số cho phép kiểm soát:

- `divide(divisor, scale, roundingMode)`: số chữ số **sau dấu thập phân** và cách làm tròn.
- `divide(divisor, MathContext)`: số chữ số **có nghĩa** và cách làm tròn.
- `divide(divisor)`: chỉ chấp nhận kết quả thập phân chính xác hữu hạn.

Yêu cầu nhiều chữ số thương thường tăng công việc, bộ nhớ và chi phí làm tròn. Nhưng thời gian thực còn phụ thuộc kích thước và cấu trúc của divisor; không đưa ra một hệ số tốc độ cố định khi chưa benchmark.

### Ví dụ 4: so sánh hai hợp đồng chia

Lưu thành `BigDecimalDivideDemo.java`:

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalDivideDemo {
    public static void main(String[] args) {
        BigDecimal one = BigDecimal.ONE;
        BigDecimal three = new BigDecimal("3");

        try {
            one.divide(three);
            System.out.println("unexpected exact result");
        } catch (ArithmeticException ex) {
            System.out.println("exact division rejected");
        }

        System.out.println("scale 2 = " + one.divide(
                three, 2, RoundingMode.HALF_UP));
        System.out.println("precision 6 = " + one.divide(
                three, new MathContext(6, RoundingMode.HALF_UP)));
    }
}
~~~

~~~bash
javac BigDecimalDivideDemo.java
java BigDecimalDivideDemo
~~~

Kết quả:

~~~text
exact division rejected
scale 2 = 0.33
precision 6 = 0.333333
~~~

Giới hạn precision một cách mù quáng có thể làm sai kết quả, còn đặt precision cực lớn “cho an toàn” có thể lãng phí tài nguyên. Cần xác định chính sách làm tròn theo nghiệp vụ và đo trên dữ liệu thực.

## 7. setScale không phải lúc nào cũng rẻ

`setScale(newScale)` có thể:

- **Tăng scale:** nhân unscaled value với lũy thừa 10 để giữ giá trị, làm số chữ số unscaled tăng.
- **Giảm scale:** chia unscaled value, có thể cần rounding nếu phần bị bỏ khác 0.
- **Giữ scale:** thường ít công việc hơn, nhưng API không cam kết kết quả luôn không cấp phát.
- **Dùng scale âm:** ví dụ `1E+3` có scale -3 và giá trị 1000.

### Ví dụ 5: tăng scale làm precision tăng

Lưu thành `ScaleExpansionDemo.java`:

~~~java
import java.math.BigDecimal;

public class ScaleExpansionDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("12.3");
        BigDecimal b = a.setScale(5);

        System.out.println("original = " + a);
        System.out.println("expanded = " + b);
        System.out.println("before p = " + a.precision());
        System.out.println("after p = " + b.precision());
        System.out.println("after s = " + b.scale());
    }
}
~~~

~~~bash
javac ScaleExpansionDemo.java
java ScaleExpansionDemo
~~~

Kết quả:

~~~text
original = 12.3
expanded = 12.30000
before p = 3
after p = 7
after s = 5
~~~

Giá trị số học vẫn là 12.3, nhưng biểu diễn unscaled dài hơn. Scale tăng hàng trăm nghìn bậc có thể gây cấp phát lớn; không cho phép đầu vào tùy ý quyết định scale không giới hạn trong ứng dụng cần kiểm soát tài nguyên.

## 8. stripTrailingZeros và so sánh

`stripTrailingZeros()` loại các số 0 cuối trong unscaled value và điều chỉnh scale. Nó có thể làm biểu diễn ngắn hơn, nhưng cũng có thể đổi scale sang số âm. Ví dụ `1000.00` trở thành dạng `1E+3`, scale -3.

`BigDecimal.equals` và `compareTo` khác nhau:

- `new BigDecimal("2.0").equals(new BigDecimal("2.00"))` là `false` vì scale khác nhau.
- `compareTo` trên hai số này trả `0` vì giá trị số học bằng nhau.

Không xem `stripTrailingZeros` như tối ưu miễn phí trong mọi vòng lặp; phép chuẩn hóa cũng có thể xử lý unscaled value và làm thay đổi hợp đồng biểu diễn. Sự khác biệt equals/compareTo còn tác động tới khóa `HashMap` và tập `TreeSet`. Với dữ liệu lớn, chi phí so sánh có thể phụ thuộc độ dài và scale; không giả định mọi phép compareTo là O(1).

### Ví dụ 6: chuẩn hóa có thể tạo scale âm

Lưu thành `NormalizeDemo.java`:

~~~java
import java.math.BigDecimal;

public class NormalizeDemo {
    public static void main(String[] args) {
        BigDecimal original = new BigDecimal("1000.00");
        BigDecimal normalized = original.stripTrailingZeros();
        BigDecimal x = new BigDecimal("2.0");
        BigDecimal y = new BigDecimal("2.00");

        System.out.println("before s = " + original.scale());
        System.out.println("after s = " + normalized.scale());
        System.out.println("normalized = " + normalized);
        System.out.println("compare = " + x.compareTo(y));
        System.out.println("equals = " + x.equals(y));
    }
}
~~~

~~~bash
javac NormalizeDemo.java
java NormalizeDemo
~~~

Kết quả:

~~~text
before s = 2
after s = -3
normalized = 1E+3
compare = 0
equals = false
~~~

Chỉ loại zero cuối khi hợp đồng của bài toán cho phép thay đổi scale. Với dữ liệu tiền tệ bắt buộc hai chữ số thập phân, phải giữ quy ước scale thích hợp thay vì chuẩn hóa vô điều kiện.

## 9. Chuỗi có thể rất dài dù precision là 1

`toString()` có thể biểu diễn giá trị bằng ký pháp khoa học, còn `toPlainString()` xuất số thập phân không dùng số mũ. Do đó `new BigDecimal("1E+1000000")` có precision 1 nhưng `toPlainString()` tạo chuỗi gồm chữ số 1 cùng khoảng một triệu số 0.

### Ví dụ 7: phí tạo chuỗi

Lưu thành `StringRepresentationDemo.java`:

~~~java
import java.math.BigDecimal;

public class StringRepresentationDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("1E+6");

        System.out.println("precision = " + x.precision());
        System.out.println("scale = " + x.scale());
        System.out.println("toString = " + x.toString());
        System.out.println("plain = " + x.toPlainString());
        System.out.println("plain length = " + x.toPlainString().length());
    }
}
~~~

~~~bash
javac StringRepresentationDemo.java
java StringRepresentationDemo
~~~

Kết quả:

~~~text
precision = 1
scale = -6
toString = 1E+6
plain = 1000000
plain length = 7
~~~

Việc tạo chuỗi dài tốn bộ nhớ theo độ dài chuỗi đầu ra ngay cả khi giá trị BigDecimal ngắn gọn. Không gọi `toPlainString` liên tục trong vòng lặp hoặc log số có scale cực đoan mà không giới hạn độ dài và nhu cầu hiển thị.

## 10. MathContext và trade-off độ chính xác

`MathContext` chứa precision và rounding mode. Nó **không trực tiếp quy định scale**. Ví dụ `new MathContext(4, HALF_UP)` chỉ giữ bốn chữ số có nghĩa; `setScale(4, HALF_UP)` giữ bốn chữ số sau dấu thập phân.

Giới hạn precision có thể làm một số phép toán xử lý kết quả ngắn hơn, nhưng cũng có thể tạo bước làm tròn. Chi phí phụ thuộc thuật toán và JDK; **không bảo đảm MathContext nhỏ luôn nhanh hơn**. Quan trọng hơn, precision thấp có thể loại đóng góp của số nhỏ hoặc làm thay đổi kết quả.

Cộng chính xác trước rồi làm tròn sau cũng có thể khác làm tròn ở **mỗi bước cộng**, nên chính sách này phải được thiết kế từ yêu cầu độ chính xác. Với tiền, thuế và sổ sách, không được thay đổi thời điểm làm tròn chỉ vì thấy nhanh hơn.

## 11. Cấp phát, bộ nhớ và thiết kế dữ liệu

Vì BigDecimal bất biến, một vòng lặp tích lũy như đoạn minh họa sau tạo kết quả logic sau mỗi phép cộng:

~~~java
BigDecimal total = BigDecimal.ZERO;
for (BigDecimal item : values) {
    total = total.add(item);
}
~~~

Đây chỉ là đoạn minh họa; `values` cần được khai báo khi dùng trong chương trình độc lập. Trong quá trình chạy, implementation có thể tối ưu hoặc tái sử dụng một số đối tượng, nhưng phép tính trên unscaled value lớn vẫn có thể tạo nhiều dữ liệu trung gian.

Hướng cải thiện hợp lý:

- Dùng `BigDecimal.ZERO`, `ONE`, `TEN` và `BigDecimal.valueOf(long)` khi thích hợp; tránh parse chuỗi trong mỗi bước nếu dữ liệu đã là số decimal chính xác.
- Với literal thập phân, dùng `new BigDecimal("0.1")` nếu cần giá trị đúng 0.1; `new BigDecimal(0.1)` giữ giá trị nhị phân gần đúng của `double`.
- Hạn chế gọi `setScale`, `stripTrailingZeros` và format chuỗi trong vòng lặp nóng nếu chỉ cần biểu diễn sau cùng.
- Với nghiệp vụ scale cố định và miền số cho phép, cân nhắc lưu bằng đơn vị nhỏ nhất trong `long`; bắt buộc kiểm soát overflow và rounding. Không áp dụng mẹo này cho bài toán scale/precision tùy ý.
- Cấu hình bộ nhớ và đánh giá lượng cấp phát/GC bằng profiler hoặc benchmark khi có bằng chứng đó là điểm nghẽn.

## 12. Benchmark đúng để tránh kết luận sai

Dùng một phép `System.nanoTime()` cho một lời gọi BigDecimal thường thiếu độ tin cậy vì JVM warmup/JIT, GC, lịch CPU và tối ưu loại bỏ phép tính không dùng kết quả.

**JMH (Java Microbenchmark Harness)** là công cụ phù hợp cho microbenchmark, cần thêm dependency vào dự án thử nghiệm riêng; nó không tích hợp sẵn trong JDK. Quy trình đo nên:

1. Chuẩn bị toán hạng trước vùng đo nếu mục tiêu chỉ đo `add` hoặc `multiply`.
2. Warmup đủ, chạy nhiều lần và báo cáo phân bố, không chỉ một trị số.
3. Tiêu thụ kết quả bằng `Blackhole` hoặc cơ chế JMH tương đương để tránh dead-code elimination.
4. Đo cả thời gian/op và allocation/op; quan sát GC nếu liên quan.
5. Thử dữ liệu có unscaled ngắn/dài, scale bằng/khác xa, precision 16/100/1000, kết quả format ngắn/dài.
6. Xác minh giá trị và scale đầu ra trước khi so sánh tốc độ; tối ưu làm sai số học không phải phép tối ưu tương đương.

Một ma trận benchmark hữu ích:

| Tình huống | Ví dụ | Điều cần đo |
| --- | --- | --- |
| Cộng cùng scale | `1234.56 + 78.90` | Chi phí cơ bản |
| Cộng scale rất lệch | `1E+1000 + 1` | Căn chỉnh và cấp phát |
| Nhân số dài | Hai số hàng nghìn chữ số | Độ dài tích và CPU |
| Chia precision lớn | `1/7` precision 16, 100, 1000 | Chi phí tính thương/làm tròn |
| Format số mũ | `1E+100000` | `toString` vs `toPlainString` |

Bảng là **đề xuất thử nghiệm**, không phải kết quả đo. Không tuyên bố “BigDecimal chậm hơn double N lần” khi chưa so đúng công việc và tập dữ liệu.

## 13. Đầu vào cực đoan và an toàn tài nguyên

Scale là kiểu `int`, nhưng các phép toán với scale cực lớn vẫn có thể đòi cấp phát hàng triệu chữ số. Ví dụ:

- Cộng `1E+1000000 + 1` tạo kết quả decimal chính xác khổng lồ.
- `setScale` tăng nhiều bậc có thể tạo unscaled value dài.
- `multiply` nhiều lần có thể làm precision/scale tăng.
- `divide` với precision rất cao phải xử lý nhiều chữ số thương.
- `toPlainString` có thể tạo chuỗi lớn hơn nhiều so với biểu diễn khoa học.
- Phép toán có thể phát sinh `ArithmeticException` với scale không hợp lệ, phép chia vô hạn không được làm tròn hoặc chế độ `UNNECESSARY`; tải bộ nhớ quá lớn còn có thể gây `OutOfMemoryError`.

Nên kiểm soát độ dài chuỗi nhập, precision, scale, số phần tử và kích thước kết quả trước khi chạy phép tính từ input bên ngoài. Giới hạn phải xuất phát từ ứng dụng và tài nguyên cho phép.

## 14. Sai lầm phổ biến

1. **Nhầm precision với scale:** `1E+6` có precision 1 và scale -6.
2. **Nghĩ precision thấp nghĩa là mọi phép toán nhẹ:** chênh lệch scale vẫn có thể tạo kết quả dài.
3. **Nghĩ setScale chỉ đổi metadata:** nó có thể nhân/chia unscaled value với lũy thừa 10.
4. **Dùng MathContext precision thấp chỉ để tăng tốc:** có thể làm mất dữ liệu.
5. **Dùng divide không quy định rounding cho 1/3:** sẽ ném `ArithmeticException`.
6. **Tưởng stripTrailingZeros giữ nguyên scale:** có thể tạo scale âm.
7. **Nhầm equals và compareTo:** equals xét scale, compareTo xét giá trị.
8. **Gọi toPlainString với số mũ cực lớn:** có thể tạo chuỗi rất dài.
9. **Chuyển sang double vì nhanh:** có thể mất tính chính xác thập phân.
10. **Dùng long đơn vị nhỏ nhất mà không kiểm tra overflow:** làm sai miền giá trị.
11. **Benchmark không warmup hoặc đo cả parse:** không phân lập được chi phí phép tính.
12. **Bỏ qua precision/scale do người dùng cung cấp:** có thể gây quá tải bộ nhớ/CPU.

## 15. Tự kiểm tra

**Câu 1.** `new BigDecimal("123.4500")` có precision và scale bằng bao nhiêu?

**Đáp án:** Precision 7, scale 4 vì unscaled value là 1234500.

**Câu 2.** Tại sao `1E+1000000 + 1` tốn tài nguyên dù toán hạng thứ nhất có precision 1?

**Đáp án:** Phép cộng chính xác cần căn scale và biểu diễn kết quả có khoảng một triệu chữ số nguyên.

**Câu 3.** `new BigDecimal("12.3").setScale(5)` tạo giá trị nào?

**Đáp án:** `12.30000`, precision tăng từ 3 lên 7, scale trở thành 5; giá trị số học không đổi.

**Câu 4.** `new BigDecimal("1000.00").stripTrailingZeros()` có thể có scale nào?

**Đáp án:** -3, biểu diễn `1E+3`.

**Câu 5.** Vì sao MathContext precision thấp không phải tối ưu miễn phí?

**Đáp án:** Nó làm tròn, có thể loại những chữ số cần thiết và thay đổi kết quả nghiệp vụ.

**Câu 6.** Muốn đo hiệu năng riêng của `add`, cần chú ý gì?

**Đáp án:** Chuẩn bị operand ngoài phần benchmark, warmup, tiêu thụ kết quả, đo nhiều mẫu với precision/scale khác nhau và đối chiếu độ đúng.

## 16. Kết luận

- Precision đo số chữ số có nghĩa của unscaled value; scale xác định vị trí dấu thập phân và có thể âm.
- Chi phí BigDecimal phụ thuộc **precision, scale, chênh lệch scale, phép toán, intermediate allocation và định dạng đầu ra**.
- Cộng scale lệch lớn và `toPlainString` của số mũ lớn có thể gây tải rất cao dù precision ban đầu nhỏ.
- Chia/nhân với precision lớn tốn thêm công việc, nhưng làm tròn sớm chỉ hợp lệ khi nghiệp vụ cho phép.
- Đo trên dữ liệu mục tiêu bằng công cụ như JMH và kiểm tra độ đúng trước khi tối ưu.

Tài liệu tham khảo: Java SE 17 API `BigDecimal`, `BigInteger`, `MathContext`, `RoundingMode`.