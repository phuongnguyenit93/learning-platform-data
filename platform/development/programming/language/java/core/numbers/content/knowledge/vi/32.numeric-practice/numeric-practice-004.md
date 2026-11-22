# Khảo sát sai số của 0.1, tổng lặp và thứ tự cộng trong Java

## 1. Mục tiêu thực hành

Thử trực tiếp trong Java:

~~~java
double a = 0.1;
double b = 0.2;

System.out.println(a + b);          // 0.30000000000000004
System.out.println(a + b == 0.3);   // false
~~~

Về mặt toán học, `0.1 + 0.2 = 0.3`. Nhưng với kiểu `double`, phép toán được thực hiện trên những **giá trị nhị phân gần đúng** với các số thập phân mà lập trình viên đã viết. Sai số biểu diễn và sai số làm tròn khi tính toán làm kết quả khác giá trị `double` biểu diễn literal `0.3`.

Bài thực hành này khảo sát bốn vấn đề:

1. Vì sao `0.1` không được biểu diễn chính xác bằng `double`.
2. Vì sao cộng `0.1` lặp lại nhiều lần có thể khác phép nhân `n * 0.1`.
3. Vì sao **thứ tự cộng** có thể thay đổi kết quả của số dấu phẩy động.
4. Cách đo, giải thích và xử lý sai số: `Math.ulp`, sai số tuyệt đối/tương đối, thuật toán cộng bù và `BigDecimal`.

Cần phân biệt **giá trị toán học kỳ vọng**, **giá trị thực tế được lưu trong kiểu số** và **chuỗi ký tự được in ra**. Việc `System.out.println(0.1)` in `0.1` không có nghĩa mọi chữ số thập phân của giá trị lưu trong `double` đều chính xác bằng một phần mười.

## 2. Nguồn gốc: 0.1 có khai triển nhị phân vô hạn

Số thập phân `0.1 = 1/10` không biểu diễn bằng một phân số có mẫu số là lũy thừa của 2 trong một số bit hữu hạn. Tương tự cách `1/3 = 0.3333...` có khai triển vô hạn ở hệ thập phân, `1/10` có khai triển vô hạn ở hệ nhị phân:

~~~text
0.1 (hệ thập phân) = 0.000110011001100110011... (hệ nhị phân)
                                  ^ mẫu 0011 lặp
~~~

`double` Java dùng định dạng nhị phân IEEE 754 binary64: 64 bit gồm bit dấu, trường số mũ và 52 bit phần fraction, với **53 bit chữ số có nghĩa** cho các giá trị chuẩn hóa. Nó chỉ lưu được hữu hạn bit của khai triển nhị phân, nên phải làm tròn sang một giá trị gần nhất.

Kiểm tra giá trị thực tế của `double` đại diện cho `0.1`:

~~~java
double x = 0.1;
System.out.println(Double.toHexString(x));
// 0x1.999999999999ap-4
System.out.println(new java.math.BigDecimal(x));
// 0.1000000000000000055511151231257827021181583404541015625
~~~

Chuỗi hex `0x1.999999999999ap-4` biểu diễn chính xác bit-value của `double`. Constructor `new BigDecimal(double)` cũng cho phép nhìn thấy **giá trị decimal chính xác của double đã lưu**; đây là trường hợp ta cố ý sử dụng constructor này để khảo sát sai số.

Giá trị lưu lớn hơn `0.1` đúng khoảng `5.55 × 10^-18`. Đây là **sai số biểu diễn ban đầu**; các phép cộng tiếp theo có thể phát sinh thêm sai số làm tròn. Sai số trong phép tính phức tạp không nhất thiết tăng đều theo số lần gọi và có thể có dấu thay đổi.

### Tại sao System.out.println(0.1) chỉ in 0.1?

`Double.toString` chọn biểu diễn thập phân ngắn đủ để phân biệt/khôi phục đúng giá trị `double` tương ứng khi parse, không phải in toàn bộ khai triển decimal chính xác của giá trị nhị phân. Vì vậy:

~~~java
System.out.println(0.1);                  // 0.1
System.out.println(new BigDecimal(0.1));  // 0.100000000000000005551...
~~~

Hai dòng đang **biểu diễn cùng một giá trị double theo hai cách khác nhau**. Không được kết luận dòng đầu chứng minh số lưu là đúng 1/10.

## 3. 0.1 + 0.2 khác 0.3: thực sự đã xảy ra điều gì?

Với `double`, các literal `0.1`, `0.2`, `0.3` được làm tròn riêng từ decimal sang binary64. Phép cộng `0.1 + 0.2` trên hai giá trị gần đúng tạo kết quả rồi làm tròn sang giá trị double có thể biểu diễn:

~~~java
double actual = 0.1 + 0.2;
double expected = 0.3;

System.out.println(actual);            // 0.30000000000000004
System.out.println(expected);          // 0.3
System.out.println(actual == expected); // false
~~~

Hai giá trị `actual` và `expected` là **hai điểm nhị phân có thể biểu diễn khác nhau** gần số thập phân 0.3. Kiểm tra `==` thực hiện so sánh giá trị `double` hiện có, không thực hiện so sánh phép tính thập phân lý tưởng.

Điều này là hành vi bình thường của số dấu phẩy động, không phải bug riêng của `println` hoặc Java. Thư viện và ngôn ngữ tuân theo các quy tắc toán học trên số hữu hạn bit. Số rất gần đúng có thể là đủ cho đo lường, đồ họa hoặc tính gần đúng, nhưng không tự đáp ứng hợp đồng về số decimal chính xác.

## 4. Cộng lặp: 10 lần và 100 lần có thể khác phép nhân

So sánh ba cách tính về mặt toán học đều có giá trị là 10:

~~~java
double sum = 0.0;
for (int i = 0; i < 100; i++) {
    sum += 0.1;
}

double multiplication = 100 * 0.1;
~~~

Trên Java 17:

| Cách thực hiện | Giá trị `double` được in |
| --- | --- |
| Cộng `0.1` 10 lần từ `0.0` | `0.9999999999999999` |
| Cộng `0.1` 100 lần từ `0.0` | `9.99999999999998` |
| Nhân `100 * 0.1` | `10.0` |

Tại sao khác nhau dù cùng công thức toán học?

- Với phép cộng lặp, mỗi lượt `sum += 0.1` thực hiện **một phép cộng dấu phẩy động và làm tròn**. Sai số sau lượt trước đi vào lượt sau.
- Với phép nhân `100 * 0.1`, phần tử đầu vào `0.1` vốn đã xấp xỉ, nhưng phép nhân rồi làm tròn có thể dẫn đến một giá trị lưu khác; trong ví dụ này được in là đúng `10.0`.
- Không có quy tắc “nhân luôn chính xác hơn cộng”, và cũng không có bảo đảm “sai số của tổng luôn tăng”. Kết quả phụ thuộc giá trị, phương pháp và trình tự phép toán.

**Đừng lấy một ví dụ rồi suy ra `100 * 0.1` luôn tốt trong mọi hoàn cảnh.** Nó chỉ cho thấy những biểu thức tương đương toán học có thể cho ra `double` khác nhau.

### Vì sao so sánh bằng tuyệt đối gây bất ngờ?

~~~java
double sum = 0.0;
for (int i = 0; i < 10; i++) {
    sum += 0.1;
}
System.out.println(sum == 1.0); // false
~~~

Sai số ở đây nhỏ, nhưng `==` không có khái niệm “gần bằng”. Độ lớn sai số có thể quan trọng hoặc không quan trọng tùy ứng dụng, nên cần một tiêu chí đánh giá dựa trên miền dữ liệu thực tế thay vì mặc định kỳ vọng kết quả bằng bit.

## 5. Thứ tự cộng: phép cộng double không có tính kết hợp toán học

Với số thực lý tưởng, ta có `(a + b) + c = a + (b + c)`. Với số dấu phẩy động hữu hạn bit, **hai vế có thể khác nhau** do mỗi phép toán trung gian đều có thể làm tròn.

Chọn:

~~~java
double huge = 1.0e16;

double first = (huge + (-huge)) + 1.0;
double second = (huge + 1.0) + (-huge);

System.out.println(first);  // 1.0
System.out.println(second); // 0.0
~~~

Lý giải:

1. `huge + (-huge)` bằng zero chính xác, rồi `0.0 + 1.0` là `1.0`.
2. `huge + 1.0` quá sát `huge` so với khoảng cách giữa các giá trị double có thể biểu diễn quanh `1e16`: phần `1.0` bị mất khi làm tròn. Bước sau cộng `-huge` cho `0.0`.

Vì vậy, ngay cả khi **cùng các toán hạng và cùng phép cộng**, thay đổi thứ tự tính cũng có thể làm thay đổi kết quả.

| Cách cộng ba số | Giá trị |
| --- | ---: |
| `(1e16 + (-1e16)) + 1.0` | `1.0` |
| `(1e16 + 1.0) + (-1e16)` | `0.0` |

Tình huống này thường được gọi là **mất chữ số có nghĩa** khi cộng số nhỏ vào số quá lớn (*loss of significance*), kết hợp với phép triệt tiêu (*cancellation*). Triệt tiêu có thể làm lộ rõ sai số đã có ở các bước trước.

### Thứ tự của mảng và phép tổng hợp

Ví dụ một mảng có `[1e16, 1.0, -1e16]`:

~~~java
double[] values = {1e16, 1.0, -1e16};
double sum = 0.0;
for (double value : values) {
    sum += value;
}
System.out.println(sum); // 0.0
~~~

Nếu đổi thành `[1e16, -1e16, 1.0]`, vòng lặp tuần tự cho `1.0`. Do đó, khi so sánh kết quả giữa các triển khai, hãy ghi nhận **cả thứ tự đầu vào và thuật toán cộng dồn**.

Trong xử lý song song, thuật toán reduction có thể nhóm các phép cộng khác nhau; kết quả dấu phẩy động có thể khác với vòng lặp tuần tự mà không nhất thiết vi phạm hợp đồng của phép tổng. Không nên đòi `parallelStream` tái tạo chính xác bit-wise tổng của một `for` tuần tự trừ khi đã có hợp đồng xác định cụ thể và kiểm chứng.

## 6. Chương trình Java 17 đầy đủ có thể chạy và đối chiếu

Lưu tệp `FloatingPointExperiment.java`:

~~~java
import java.math.BigDecimal;
import java.util.Locale;

public class FloatingPointExperiment {

    static double repeated(double term, int count) {
        double sum = 0.0;
        for (int i = 0; i < count; i++) {
            sum += term;
        }
        return sum;
    }

    static double kahan(double term, int count) {
        double sum = 0.0;
        double compensation = 0.0;
        for (int i = 0; i < count; i++) {
            double y = term - compensation;
            double t = sum + y;
            compensation = (t - sum) - y;
            sum = t;
        }
        return sum;
    }

    public static void main(String[] args) {
        double tenth = 0.1;

        System.out.printf(Locale.ROOT, "hex(0.1) = %a%n", tenth);
        System.out.println("exact(0.1) = " + new BigDecimal(tenth));
        System.out.println("valueOf(0.1) = " + BigDecimal.valueOf(tenth));

        System.out.println("0.1+0.2 = " + (0.1 + 0.2));
        System.out.println("equal 0.3 = " + ((0.1 + 0.2) == 0.3));

        System.out.println("10 additions = " + repeated(0.1, 10));
        System.out.println("100 additions = " + repeated(0.1, 100));
        System.out.println("100 multiplied = " + (100 * 0.1));
        System.out.println("Kahan 100 additions = " + kahan(0.1, 100));

        System.out.println("BigDecimal 100 additions = "
                + BigDecimal.valueOf(0.1)
                    .multiply(BigDecimal.valueOf(100)));

        double large = 1e16;
        System.out.println("(big + -big) + 1 = "
                + ((large + -large) + 1.0));
        System.out.println("(big + 1) + -big = "
                + ((large + 1.0) + -large));

        System.out.println("ulp(1.0) = " + Math.ulp(1.0));
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac FloatingPointExperiment.java
java FloatingPointExperiment
~~~

Kết quả đã đối chiếu khi chạy trên Java 17:

~~~text
hex(0.1) = 0x1.999999999999ap-4
exact(0.1) = 0.1000000000000000055511151231257827021181583404541015625
valueOf(0.1) = 0.1
0.1+0.2 = 0.30000000000000004
equal 0.3 = false
10 additions = 0.9999999999999999
100 additions = 9.99999999999998
100 multiplied = 10.0
Kahan 100 additions = 10.0
BigDecimal 100 additions = 10.0
(big + -big) + 1 = 1.0
(big + 1) + -big = 0.0
ulp(1.0) = 2.220446049250313E-16
~~~

Chương trình có bốn nhóm đối chiếu:

- **Biểu diễn:** `0.1` dạng hex và decimal chính xác của double.
- **Tích lũy:** `repeated` cộng lặp 10/100 lần so với phép nhân một lần.
- **Cải thiện thuật toán:** `kahan` cộng bù để giảm mất mát khi tích lũy trong ví dụ.
- **Miền giá trị lớn:** cùng ba toán hạng nhưng hai thứ tự cộng tạo `1.0` và `0.0`.

Các con số được in từ API chuẩn, không phụ thuộc vào ngôn ngữ hệ thống nhờ `Locale.ROOT` ở lời gọi in hex. Các biểu thức in còn lại dựa vào `Double.toString` mặc định theo Java.

## 7. Sai số tuyệt đối, tương đối và đơn vị ULP

Để phân tích kết quả, đặt:

~~~text
expected = giá trị tham chiếu
actual   = giá trị tính được

absoluteError = |actual - expected|
relativeError = absoluteError / |expected|   (khi expected != 0)
~~~

**Sai số tuyệt đối** đo chênh lệch theo đơn vị của đại lượng. Ví dụ kết quả `9.99999999999998` so với 10 có sai số tuyệt đối khoảng `2 × 10^-14`.

**Sai số tương đối** biểu diễn sai lệch so với độ lớn giá trị chuẩn. Nó không phù hợp khi giá trị tham chiếu bằng 0; nếu gần 0, mẫu số quá nhỏ có thể làm tỷ lệ tăng mạnh dù sai số tuyệt đối nhỏ.

Một công cụ liên quan là `Math.ulp(x)` (*unit in the last place*): trả khoảng cách cỡ một bước biểu diễn dấu phẩy động tại độ lớn `x` theo định nghĩa của Java. Ví dụ:

~~~java
System.out.println(Math.ulp(1.0));
// 2.220446049250313E-16
~~~

Giá trị này cho biết mức độ chi tiết của double quanh 1.0. Khoảng cách giữa các số double có thể biểu diễn **không cố định trên toàn trục số**: khi trị tuyệt đối của số lớn lên, khoảng cách tuyệt đối giữa các số lân cận nhìn chung cũng lớn hơn.

Lưu ý: Không thể lấy `Math.ulp(1.0)` làm ngưỡng so sánh đúng cho mọi miền. Trong phép cộng `1e16 + 1.0`, bước biểu diễn tại `1e16` lớn hơn đơn vị `1.0`; đó là lý do đóng góp nhỏ có thể bị mất.

## 8. Kiểm tra gần bằng: đặt dung sai theo bài toán, không dùng một epsilon tùy tiện

Nếu mục tiêu là biết kết quả có **đủ gần** một tham chiếu không, có thể định nghĩa dung sai:

~~~java
double actual = 0.1 + 0.2;
double expected = 0.3;
double absoluteTolerance = 1e-12;

boolean nearEqual = Math.abs(actual - expected)
        <= absoluteTolerance;
System.out.println(nearEqual); // true
~~~

Đây là **mảnh code minh họa** đặt trong một phương thức/lớp Java. Ngưỡng `1e-12` chỉ là ví dụ cho bài toán có giá trị cỡ 0.3, **không phải hằng số đúng cho mọi ứng dụng**.

Hãy phân biệt:

- **Dung sai tuyệt đối:** phù hợp khi đơn vị và ngưỡng sai số có ý nghĩa cố định, đặc biệt quanh zero.
- **Dung sai tương đối:** hợp lý cho những giá trị có độ lớn trải rộng; so sánh chênh lệch với thang của dữ liệu.
- **So sánh theo ULP:** hữu ích trong kiểm thử thuật toán dấu phẩy động đã được phân tích kỹ; cần xét các trường hợp đặc biệt và miền biến thiên.

Một quy tắc kết hợp thường gặp về mặt ý tưởng:

~~~text
|actual - expected| <= max(absTolerance,
                           relTolerance * max(|actual|, |expected|))
~~~

Trước khi áp dụng thực tế phải xác định tolerance không âm, xử lý `NaN`, vô cực, zero và khả năng overflow/underflow ở phép tính chênh lệch hoặc nhân tolerance. Không áp dụng công thức này một cách máy móc cho mọi bài toán.

**Quan trọng:** Không dùng kiểm tra “gần bằng” để thay thế bằng nhau chính xác cho định danh, số đếm, số tiền hoặc các bất biến bắt buộc có giá trị exact. Chọn thuật toán/kiểu dữ liệu đúng vẫn quan trọng hơn việc tăng tolerance cho qua kiểm thử.

### Toán tử == không phải luôn sai

Với `double`, `==` chính xác khi bạn **muốn so giá trị nhị phân hiện có** và biết rõ điều kiện. Ví dụ `x == 0.0` là cách kiểm tra đúng nghĩa “x hiện đang bằng 0.0 theo phép so sánh double” (cả `+0.0` và `-0.0` đều bằng nhau theo `==`). Điều không an toàn là giả định các phép toán gần đúng tự cho kết quả bit-wise bằng một literal thập phân mong đợi.

`NaN` là trường hợp đặc biệt: `Double.NaN == Double.NaN` là false. Dùng `Double.isNaN(x)` khi cần nhận diện NaN và `Double.isFinite(x)` khi cần loại cả NaN/vô cực. Không kết luận một kết quả `false` của `==` luôn đến từ sai số làm tròn.

## 9. Cộng bù Kahan: giảm lỗi tích lũy, không biến double thành decimal exact

Thuật toán cộng bù của Kahan giữ một biến `compensation` để ước lượng phần nhỏ bị mất trong quá trình cộng:

~~~java
static double kahan(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;
    for (double value : values) {
        double y = value - compensation;
        double t = sum + y;
        compensation = (t - sum) - y;
        sum = t;
    }
    return sum;
}
~~~

Đây là **mảnh phương thức** đặt trong lớp Java. Các bước theo trực giác:

1. `y` điều chỉnh hạng tử tiếp theo bằng phần lỗi bù đã ghi nhận.
2. `t` thực hiện cộng vào tổng.
3. `compensation` lưu một ước lượng của phần làm tròn từ phép cộng vừa diễn ra.
4. `sum` nhận kết quả tích lũy mới.

Trong ví dụ cộng `0.1` 100 lần, Kahan cho `10.0` thay vì `9.99999999999998`. Đây là **một cải thiện ở ví dụ cụ thể**, không phải lời hứa mọi tổng và mọi thứ tự cộng đều trở thành chính xác.

Các giới hạn:

- `0.1` đầu vào vẫn được biểu diễn gần đúng bằng double; thuật toán không thay được bản chất của kiểu số.
- Kahan có thể giúp với nhiều trường hợp tích lũy nhưng không xử lý hoàn hảo mọi trường hợp hủy chữ số, tràn, thiếu chính xác đầu vào hoặc dữ liệu có điều kiện số xấu.
- Các thuật toán khác như cộng theo cặp (*pairwise summation*), Neumaier summation hoặc sắp xếp hạng tử trước khi cộng có thể hữu ích tùy bài toán; sắp xếp lại có thể ảnh hưởng ý nghĩa xử lý dữ liệu, và không tự bảo đảm kết quả exact.
- Trong hệ thống cần kết quả có thể phát lại, phải giữ cố định thuật toán, thứ tự và chế độ song song theo hợp đồng.

Nếu quan trọng là **đúng 100 lần số thập phân 0.1 bằng 10.0**, dùng kiểu biểu diễn decimal chính xác như `BigDecimal` từ chuỗi, thay vì coi Kahan là thay thế chung.

## 10. BigDecimal: biểu diễn thập phân chính xác khi đầu vào chính xác

`BigDecimal` có thể lưu chính xác số decimal đã định nghĩa trong chuỗi:

~~~java
BigDecimal tenth = new BigDecimal("0.1");
BigDecimal sum = BigDecimal.ZERO;

for (int i = 0; i < 100; i++) {
    sum = sum.add(tenth);
}

System.out.println(sum.toPlainString()); // 10.0
~~~

Khác biệt căn bản:

- `new BigDecimal("0.1")` diễn giải thập phân trong chuỗi và lưu đúng giá trị 0.1.
- `BigDecimal.valueOf(0.1)` lấy biểu diễn thập phân chuẩn của **giá trị double** qua `Double.toString`, nên với literal này tạo `BigDecimal` có giá trị decimal `0.1`. Đây thường là cách hợp lý khi nguồn đầu vào thực sự chỉ có sẵn kiểu double và muốn biểu diễn thập phân chuẩn của nó.
- `new BigDecimal(0.1)` lưu chính xác **giá trị nhị phân đã làm tròn** của double, vì thế có chuỗi thập phân dài `0.10000000000000000555...`, **không** phải exact 1/10.

So sánh:

~~~java
System.out.println(new BigDecimal("0.1"));
// 0.1

System.out.println(BigDecimal.valueOf(0.1));
// 0.1

System.out.println(new BigDecimal(0.1));
// 0.1000000000000000055511151231257827021181583404541015625
~~~

`BigDecimal` dùng số thập phân tùy ý precision để thực hiện các phép cộng/nhân chính xác khi không yêu cầu một `MathContext` làm tròn. Nhưng **không có nghĩa mọi phép chia đều cho biểu diễn thập phân hữu hạn**. Chẳng hạn `1 / 3` không kết thúc trong decimal; cần định nghĩa scale và `RoundingMode` khi chia.

Lưu ý thêm: `BigDecimal` immutable, nên phải **gán lại** `sum = sum.add(tenth)`; nếu chỉ gọi `sum.add(tenth);` mà bỏ kết quả, `sum` không thay đổi.

## 11. Cách tiến hành một thí nghiệm có ý nghĩa

Để so sánh sai số giữa các chiến lược, hãy xác định trước:

1. **Giá trị tham chiếu:** trong thí nghiệm 100 lần 0.1, giá trị decimal lý tưởng là 10.0. Tạo tham chiếu bằng `BigDecimal("0.1")`, không suy ra từ cùng phép cộng double đang kiểm tra.
2. **Dữ liệu và thứ tự:** số phần tử, giá trị ban đầu, thứ tự nhập, trường hợp có độ lớn rất chênh lệch và dấu đối nhau.
3. **Thuật toán:** vòng lặp tuần tự, phép nhân, Kahan, pairwise, hoặc `BigDecimal`.
4. **Chỉ tiêu:** giá trị in, sai số tuyệt đối/tương đối, thời gian và chi phí bộ nhớ khi thích hợp.
5. **Quy tắc kết luận:** hiệu năng không thể được đánh giá đáng tin chỉ bằng một lần đo nhỏ; độ chính xác không thể được đánh giá chỉ qua một ví dụ thuận lợi.

Một bảng thí nghiệm minh họa:

| Bài thử | Thuật toán | Kết quả | Giá trị tham chiếu |
| --- | --- | --- | --- |
| 10 × 0.1 | Cộng double lặp | `0.9999999999999999` | 1.0 |
| 100 × 0.1 | Cộng double lặp | `9.99999999999998` | 10.0 |
| 100 × 0.1 | Nhân double | `10.0` | 10.0 |
| 100 × 0.1 | Kahan double | `10.0` | 10.0 |
| 100 × 0.1 | BigDecimal từ chuỗi | `10.0` | 10.0 |
| 1e16, -1e16, 1 | Cộng theo một thứ tự | `1.0` | 1.0 |
| 1e16, 1, -1e16 | Cộng theo thứ tự khác | `0.0` | 1.0 |

Hai hàng cuối đặc biệt quan trọng: kết quả có thể **lệch hẳn 1.0** chứ không chỉ ở vài chữ số cuối, khi các hạng tử chênh lệch độ lớn và triệt tiêu nhau.

## 12. Stream và song song: đừng vô tình thay đổi mô hình cộng dồn

Java cung cấp:

~~~java
double sum = java.util.Arrays.stream(values).sum();
~~~

Khi `values` là mảng `double[]`, đây là `DoubleStream.sum()`. Hành vi thực hiện có thể sử dụng kỹ thuật cộng bù/các chiến lược được Java mô tả để cải thiện chất lượng kết quả. Không nên mặc định phép tổng này nhất thiết giống vòng `for (double x : values) sum += x`, đặc biệt khi cấu trúc pipeline hoặc thực thi song song khiến thứ tự kết hợp thay đổi.

Với số dấu phẩy động:

- Tổng toán học không đổi khi hoán vị thứ tự, nhưng tổng thực hiện bằng số hữu hạn bit có thể đổi.
- Cộng theo nhánh song song có thể thay đổi thứ tự kết hợp; kết quả có thể phụ thuộc chiến lược reduction.
- Các benchmark so sánh độ chính xác và tốc độ phải xác định rõ tập dữ liệu, thuật toán và điều kiện chạy.
- Không dùng `parallel()` chỉ vì nghĩ kết quả số học phải giống từng bit với vòng lặp tuần tự.

Nếu một kết quả phải tái lập chính xác, hãy chọn thuật toán có hợp đồng đủ chặt và kiểm soát cách phân chia/cộng kết quả. Nếu cần decimal exact, xem xét `BigDecimal` và mô hình làm tròn nghiệp vụ thay vì dựa vào thứ tự tổng hợp double.

## 13. Khi nào nên dùng double, khi nào nên dùng BigDecimal?

| Nhu cầu | Lựa chọn thường phù hợp | Điểm cần kiểm tra |
| --- | --- | --- |
| Đồ họa, mô phỏng, cảm biến, tính toán khoa học chấp nhận xấp xỉ | `double` | Sai số tuyệt đối/tương đối, điều kiện số, thuật toán ổn định |
| Tổng nhiều số có độ lớn chênh nhau | `double` với phương pháp tổng thích hợp, nếu chính sách sai số cho phép | Thứ tự, khả năng triệt tiêu, Kahan/pairwise, test theo tham chiếu |
| Số tiền theo đơn vị thập phân chính xác | `BigDecimal` từ chuỗi hoặc đơn vị nhỏ nhất bằng `long` khi phù hợp | Scale, rounding, overflow, đơn vị tiền |
| Giá trị decimal cần đúng 0.1 + 0.2 = 0.3 | `BigDecimal("0.1")` + `BigDecimal("0.2")` | Không đi vòng qua double |
| Số đếm nguyên | `int`, `long`, `BigInteger` theo miền | Overflow, không dùng float/double nếu cần số nguyên chính xác |

Không có quy tắc rằng `BigDecimal` luôn tốt hơn `double`. Nó thường có chi phí tính toán/bộ nhớ cao hơn, yêu cầu quản lý scale và chính sách làm tròn. Ngược lại, `double` hiệu quả và phù hợp cho nhiều ứng dụng số học xấp xỉ nếu kết quả được đánh giá bằng tiêu chí sai số đúng đắn.

## 14. Lỗi thường gặp và cách sửa

**Lỗi 1 — Tin rằng 0.1 lưu trong double đúng 1/10.** `println(0.1)` in ngắn gọn; dùng `Double.toHexString` và `new BigDecimal(0.1)` khi cần khám phá giá trị chính xác của double.

**Lỗi 2 — So `0.1 + 0.2 == 0.3` để kiểm thử phép cộng số thực xấp xỉ.** Phép so sánh có thể false do biểu diễn và làm tròn. Dùng tolerance có ý nghĩa hoặc mô hình thập phân exact theo yêu cầu.

**Lỗi 3 — Nghĩ cộng lặp và phép nhân phải cho cùng double.** Nhiều phép cộng có nhiều lần làm tròn; một phép nhân chỉ thực hiện bước tính/làm tròn tương ứng của nó. Kết quả có thể khác.

**Lỗi 4 — Mặc định phép cộng dấu phẩy động kết hợp được.** `(a+b)+c` và `a+(b+c)` có thể khác. Các số độ lớn rất chênh lệch hoặc trái dấu là tình huống dễ bộc lộ sai lệch.

**Lỗi 5 — Dùng ngưỡng sai số chung cho tất cả số.** `1e-12` có thể hợp lý ở thang 1 nhưng vô nghĩa ở thang 1e15 hoặc 1e-20. Xác định tolerance theo đơn vị, ngưỡng nghiệp vụ và độ lớn của giá trị.

**Lỗi 6 — Suy ra Kahan cho kết quả luôn chính xác.** Nó giảm sai số tích lũy trong nhiều trường hợp nhưng không sửa tất cả tình huống triệt tiêu và không biến dữ liệu double thành decimal exact.

**Lỗi 7 — Dùng `new BigDecimal(0.1)` để thể hiện một phần mười exact.** Constructor này nhận bit-value double đã xấp xỉ. Hãy tạo từ chuỗi `"0.1"` khi nguồn chính là thập phân đó.

**Lỗi 8 — Gọi `sum.add(...)` mà không gán kết quả.** `BigDecimal` immutable; phải dùng `sum = sum.add(...)`.

**Lỗi 9 — Kết luận giá trị double bị lỗi chỉ vì biểu diễn in ra khác mong đợi.** Cần định lượng sai số so với giá trị tham chiếu, xem xét yêu cầu và điều kiện số. Một sai lệch nhỏ có thể chấp nhận được, nhưng cũng có thể tích lũy thành lỗi lớn.

**Lỗi 10 — Coi số 0 âm, NaN và Infinity là các giá trị thông thường.** Những giá trị đặc biệt ảnh hưởng so sánh và phép đo sai số. Dùng `Double.isFinite` và quy tắc xử lý dữ liệu đầu vào rõ ràng.

**Lỗi 11 — So sánh kết quả vòng lặp với DoubleStream.sum rồi khẳng định Java chạy sai.** Thuật toán và thứ tự cộng dồn có thể khác. Chỉ kết luận sau khi so sánh cùng giả định và hợp đồng.

**Lỗi 12 — Dựa vào một bộ test với 0.1 để kết luận thuật toán ổn định.** Hãy khảo sát thêm số rất lớn/nhỏ, dấu đối nhau, phép trừ gần nhau, nhiều lượt cộng, đầu vào ngẫu nhiên lẫn phản ví dụ có chủ đích.

## 15. Bài luyện tập và đáp án

### Bài 1 — Dự đoán và giải thích

~~~java
double s = 0.0;
for (int i = 0; i < 10; i++) {
    s += 0.1;
}
System.out.println(s);
System.out.println(s == 1.0);
~~~

**Đáp án:**

~~~text
0.9999999999999999
false
~~~

Mỗi lần cộng sử dụng double gần đúng và có thể làm tròn. Sai số cuối khiến giá trị biểu diễn khác `1.0`.

### Bài 2 — Đổi thứ tự cộng

Với `a=1e16`, `b=-1e16`, `c=1.0`, hãy dự đoán:

~~~java
double left = (a + b) + c;
double right = (a + c) + b;
~~~

**Đáp án:** `left = 1.0`, `right = 0.0`. Nhánh `a+c` làm mất `1.0` khi làm tròn vì số lớn hơn quá nhiều.

### Bài 3 — BigDecimal: chọn constructor

Dự đoán:

~~~java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
System.out.println(a.add(b).toPlainString());
~~~

**Đáp án:** `0.3`. Cả hai được tạo chính xác từ chuỗi decimal và `add` không yêu cầu làm tròn.

Nếu thay `new BigDecimal("0.1")` bằng `new BigDecimal(0.1)`, dữ liệu đầu vào đã là giá trị nhị phân xấp xỉ, không còn là exact 1/10.

### Bài 4 — Thiết kế kiểm thử sai số

Bạn cần kiểm tra một thuật toán tính tổng dữ liệu cảm biến có giá trị khoảng `10^-6` và `10^6`. Có nên dùng một epsilon tuyệt đối duy nhất như `1e-12`?

**Đáp án:** Không nên mặc định. Cần xem đơn vị, thang giá trị, mức nhiễu đo, yêu cầu sai số và khả năng triệt tiêu; có thể cần phối hợp sai số tuyệt đối, tương đối hoặc các tiêu chí thống kê riêng. Tolerance là đặc tả, không phải thủ thuật để làm mọi test pass.

### Bài 5 — Kahan có thay thế BigDecimal không?

Trong ví dụ 100 lần cộng `0.1`, Kahan cho `10.0`. Có thể suy ra Kahan lưu exact `0.1` không?

**Đáp án:** Không. Biểu diễn đầu vào vẫn là binary64 gần đúng; Kahan giúp bù phần sai số tích lũy. Với nghiệp vụ cần giá trị decimal chính xác, dùng `BigDecimal` từ chuỗi và quy tắc làm tròn rõ ràng.

## 16. Checklist khi khảo sát một lỗi số dấu phẩy động

1. **Giá trị đầu vào thực tế là gì?** Decimal từ chuỗi, double đã làm tròn hay dữ liệu cảm biến?
2. **Giá trị tham chiếu là gì?** Được tạo độc lập bằng một mô hình đủ chính xác chưa?
3. **Đã phân biệt sai số biểu diễn với sai số phép tính và sai số tích lũy chưa?**
4. **Có số quá lớn so với số quá nhỏ trong cùng tổng không?** Có triệt tiêu hay đổi thứ tự cộng không?
5. **Kiểm thử có nhìn cả giá trị in, hex bit-value, sai số tuyệt đối/tương đối và ULP khi cần không?**
6. **Nếu cần cộng nhiều phần tử, có chọn thuật toán cộng dồn phù hợp và xác định thứ tự xử lý không?**
7. **Nếu cần decimal exact, có dùng `BigDecimal` từ chuỗi hoặc kiểu nguyên biểu diễn đơn vị nhỏ nhất không?**
8. **Nếu dùng tolerance, ngưỡng có xuất phát từ yêu cầu nghiệp vụ/đơn vị và đã xét NaN/vô cực chưa?**

**Kết luận:** `0.1` không biểu diễn chính xác được trong binary64, nên `0.1 + 0.2`, tổng cộng lặp và phép cộng ở các thứ tự khác nhau có thể cho các kết quả `double` khác nhau. Đây là giới hạn của số dấu phẩy động hữu hạn bit. Hãy thực nghiệm, đo sai số và chọn đúng thuật toán/kiểu số; không nhầm **gần đúng đủ tốt** với **bằng nhau chính xác theo giá trị decimal**.
