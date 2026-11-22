# Kiểm thử phép tính ở biên và tránh giả định tính kết hợp trong Java 17

Các kiểu số thực của Java thuận tiện cho phép tính khoa học, đo lường, đồ họa và nhiều bài toán kỹ thuật. Nhưng số thực dấu phẩy động không lưu được mọi số thập phân một cách chính xác. Mỗi phép toán có thể làm tròn kết quả về một giá trị biểu diễn được, và sai số đó có thể tích lũy hoặc làm thay đổi kết quả ở gần một ngưỡng.

Vì vậy, khi viết và kiểm thử chương trình Java 17, không nên chỉ thử một vài giá trị thông thường. Cần xem xét **các biên của miền đầu vào**, **giá trị biểu diễn được gần ngưỡng**, **overflow/underflow**, **NaN và infinity**, và đặc biệt **không giả định phép toán số thực có tính kết hợp như số thực toán học**.

## 1. double và float biểu diễn số như thế nào?

Java có hai kiểu số thực dấu phẩy động nguyên thủy phổ biến:

| Kiểu | Kích thước | Độ chính xác gần đúng | Phạm vi độ lớn |
| --- | ---: | ---: | --- |
| float | 32 bit | khoảng 6–7 chữ số thập phân có nghĩa | khoảng 1.4 × 10⁻⁴⁵ đến 3.4 × 10³⁸ |
| double | 64 bit | khoảng 15–16 chữ số thập phân có nghĩa | khoảng 4.9 × 10⁻³²⁴ đến 1.8 × 10³⁰⁸ |

Hai kiểu này tuân theo định dạng IEEE 754 binary floating-point. Một giá trị được mã hóa bằng dấu, số mũ và phần significand (phần có nghĩa). Hệ nhị phân biểu diễn chính xác các phân số có mẫu là lũy thừa của 2, ví dụ 0.5, 0.25 và 0.125. Những phân số như 0.1 hoặc 0.2 có biểu diễn nhị phân tuần hoàn nên phải được làm tròn thành giá trị gần nhất có thể lưu.

Ví dụ:

~~~java
double result = 0.1 + 0.2;
System.out.println(result);
System.out.println(result == 0.3);
~~~

Kết quả thường thấy:

~~~text
0.30000000000000004
false
~~~

Đây không phải lỗi riêng của Java. Các giá trị double được lưu gần với 0.1 và 0.2; phép cộng thực hiện trên những giá trị nhị phân đã làm tròn và kết quả lại được làm tròn. Giá trị lưu được vì thế không nhất thiết bằng biểu diễn của literal 0.3.

### Độ chính xác không đồng đều trên toàn miền

Khoảng cách giữa hai số double biểu diễn được kề nhau phụ thuộc độ lớn của số. Gần 1.0, khoảng cách có cỡ 10⁻¹⁶; gần 10¹⁶, khoảng cách lớn hơn rất nhiều. Vì vậy không tồn tại một ngưỡng sai số tuyệt đối duy nhất phù hợp cho mọi giá trị.

Một ví dụ cho thấy giới hạn chính xác của số nguyên khi chuyển sang double:

~~~java
double a = 9_007_199_254_740_992d; // 2^53
double b = 9_007_199_254_740_993d; // 2^53 + 1

System.out.println(a == b); // true
~~~

Double có thể biểu diễn chính xác mọi số nguyên trong khoảng từ -2⁵³ đến 2⁵³. Ngoài vùng này, không phải mọi số nguyên liên tiếp đều có biểu diễn riêng. Với float, giới hạn tương ứng là 2²⁴. Nếu ứng dụng cần định danh số nguyên lớn, số đếm hoặc số tiền ở đơn vị nhỏ nhất, dùng long/BigInteger hoặc kiểu thập phân phù hợp thay vì chuyển sang double.

## 2. Vì sao không được giả định tính kết hợp?

Trong số học thực, phép cộng có tính kết hợp:

\[
(a+b)+c = a+(b+c)
\]

Nhưng phép cộng dấu phẩy động phải làm tròn sau từng phép toán. Việc đặt dấu ngoặc làm thay đổi thứ tự làm tròn, nên hai vế có thể khác nhau.

Ví dụ:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double left = (a + b) + c;
double right = a + (b + c);

System.out.println(left);  // 1.0
System.out.println(right); // 0.0
System.out.println(left == right); // false
~~~

Giải thích:

1. Ở vế trái, a + b triệt tiêu thành 0, rồi cộng c cho kết quả 1.
2. Ở vế phải, b + c phải làm tròn. Vì c quá nhỏ so với độ lớn của b, kết quả được làm tròn thành b. Sau đó a + b triệt tiêu thành 0.

Tương tự, phép nhân dấu phẩy động cũng có thể không kết hợp do làm tròn và overflow/underflow. Các quy tắc biến đổi đại số như đổi nhóm, phân phối hoặc rút gọn biểu thức cần được cân nhắc theo độ chính xác và miền giá trị, không chỉ dựa trên đại số thực.

### Thứ tự tính trong Java

Các biểu thức Java tuân theo thứ tự ưu tiên và kết hợp toán tử được quy định bởi ngôn ngữ. Phép cộng cùng mức được nhóm từ trái sang phải:

~~~java
double result = a + b + c;
~~~

Biểu thức này được nhóm như:

~~~java
double result = (a + b) + c;
~~~

Không tự ý đổi thành a + (b + c) với giả định kết quả sẽ giống nhau. Từ Java 17, các phép toán dấu phẩy động của Java có ngữ nghĩa strict theo JEP 306; điều đó giúp hành vi phép toán được nhất quán theo đặc tả, nhưng **không làm số thực trở nên chính xác tuyệt đối và không tạo ra tính kết hợp**.

### Tác động đến stream và xử lý song song

Một phép gộp như cộng double không có tính kết hợp chính xác trong số học dấu phẩy động. Nếu chia dữ liệu thành các nhóm khác nhau rồi cộng từng nhóm, thứ tự và cách nhóm có thể làm kết quả thay đổi ở những bit cuối. Điều này đặc biệt đáng chú ý với reduction song song, vì các phần dữ liệu có thể được gộp theo cấu trúc khác nhau.

Không nên dùng kết quả double của một phép reduction làm khóa so sánh chính xác nếu nghiệp vụ đòi hỏi kết quả ổn định tuyệt đối. Nếu thứ tự tính có ý nghĩa, hãy xác định thứ tự và thuật toán cộng; nếu cần tính tiền chính xác theo thập phân, chọn biểu diễn thập phân hoặc số nguyên theo đơn vị nhỏ nhất.

## 3. Những tình huống số thực cần kiểm thử ở biên

Kiểm thử số thực cần bao phủ các vùng mà hành vi có thể đổi khác. Với một ngưỡng T, không chỉ thử một giá trị nhỏ hơn và lớn hơn tùy ý; hãy thử **giá trị ngay trước T, đúng T và ngay sau T** trong miền biểu diễn.

| Nhóm biên | Ví dụ cần xét | Vấn đề có thể xuất hiện |
| --- | --- | --- |
| Gần 0 | +0.0, -0.0, số subnormal nhỏ nhất, giá trị âm/dương gần 0 | Chia cho zero, underflow, signed zero |
| Ngưỡng nghiệp vụ | ngay dưới, bằng và ngay trên ngưỡng | So sánh < hay <=, sai số làm thay đổi nhánh |
| Số nhỏ | Double.MIN_VALUE, Double.MIN_NORMAL | Subnormal, underflow, mất độ chính xác tương đối |
| Số lớn | Double.MAX_VALUE và số kề nó | Overflow thành infinity |
| Không hữu hạn | NaN, positive/negative infinity | So sánh, validate, truyền dữ liệu |
| Giá trị tích lũy | tổng nhiều số lớn và nhỏ | Mất chữ số có nghĩa, triệt tiêu |
| Giá trị chuyển kiểu | long lớn sang double, double sang int | Mất độ chính xác hoặc bị giới hạn/cắt |
| Dữ liệu thập phân | 0.1, 0.2, 0.3 và giá trị tiền | Không thể so sánh bằng tuyệt đối |

### Kiểm thử sát một ngưỡng bằng Math.nextDown và Math.nextUp

Java cung cấp:

- Math.nextDown(x): số dấu phẩy động biểu diễn được liền trước x theo hướng âm vô hạn.
- Math.nextUp(x): số dấu phẩy động biểu diễn được liền sau x theo hướng dương vô hạn.
- Math.ulp(x): khoảng cách theo đơn vị ở chữ số cuối (unit in the last place) tại độ lớn x.
- Math.nextAfter(start, direction): bước tới giá trị biểu diễn được kế tiếp theo hướng direction.

Ví dụ:

~~~java
double limit = 100.0;

double justBelow = Math.nextDown(limit);
double exact = limit;
double justAbove = Math.nextUp(limit);

System.out.println(justBelow < limit); // true
System.out.println(exact == limit);    // true
System.out.println(justAbove > limit); // true
System.out.println(Math.ulp(limit));
~~~

Đây là cách tạo bộ dữ liệu kiểm thử chính xác quanh một biên double, không cần đoán một epsilon tùy ý. Với một điều kiện nghiệp vụ như score phải nhỏ hơn 100, ba trường hợp này giúp xác định rõ hành vi tại biên.

### Kiểm thử miền đóng và miền mở

Giả sử điểm hợp lệ nằm trong khoảng đóng [0, 100]:

~~~java
static boolean isValidScore(double score) {
    return Double.isFinite(score) && score >= 0.0 && score <= 100.0;
}
~~~

Các trường hợp sát biên:

~~~java
double min = 0.0;
double max = 100.0;

System.out.println(isValidScore(Math.nextDown(min))); // false
System.out.println(isValidScore(min));                // true
System.out.println(isValidScore(Math.nextUp(min)));   // true
System.out.println(isValidScore(Math.nextDown(max))); // true
System.out.println(isValidScore(max));                // true
System.out.println(isValidScore(Math.nextUp(max)));   // false
~~~

Nếu miền là khoảng mở (0, 100), điều kiện phải dùng score > 0 và score < 100. Bộ kiểm thử cần phản ánh chính xác hợp đồng, không suy đoán từ cách viết UI.

## 4. Kiểm tra overflow và underflow

### Overflow

Khi kết quả vượt quá độ lớn hữu hạn có thể biểu diễn, phép toán dấu phẩy động có thể tạo positive infinity hoặc negative infinity:

~~~java
double large = Double.MAX_VALUE;
double overflow = large * 2.0;

System.out.println(overflow);                // Infinity
System.out.println(Double.isInfinite(overflow)); // true
System.out.println(Double.isFinite(overflow));   // false
~~~

Không có ArithmeticException tự động như một số phép toán số nguyên có kiểm tra. Nếu miền nghiệp vụ không chấp nhận infinity, phải kiểm tra kết quả:

~~~java
static double multiplyFinite(double a, double b) {
    double result = a * b;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("Floating-point result is not finite");
    }
    return result;
}
~~~

Lưu ý: kiểm tra đầu vào hữu hạn và kiểm tra kết quả hữu hạn là hai việc riêng. Hai đầu vào đều finite vẫn có thể tạo overflow.

### Underflow và subnormal

Khi độ lớn kết quả rất nhỏ, kết quả có thể rơi vào vùng subnormal (denormal) để giữ độ lớn nhỏ hơn giới hạn normal, hoặc cuối cùng làm tròn thành zero.

Các hằng số quan trọng:

| Hằng số | Ý nghĩa |
| --- | --- |
| Double.MIN_VALUE | Số double dương nhỏ nhất khác 0; đây là subnormal nhỏ nhất |
| Double.MIN_NORMAL | Số double dương nhỏ nhất ở vùng normal |
| Double.MAX_VALUE | Số double hữu hạn dương lớn nhất |
| Float.MIN_VALUE | Số float dương nhỏ nhất khác 0 |
| Float.MIN_NORMAL | Số float dương nhỏ nhất ở vùng normal |

Tên MIN_VALUE dễ gây hiểu nhầm: nó **không phải số âm nhỏ nhất** và cũng không phải số có độ lớn nhỏ nhất theo nghĩa giá trị tuyệt đối. Với double, Double.MIN_VALUE xấp xỉ 4.9 × 10⁻³²⁴; Double.MIN_NORMAL xấp xỉ 2.2 × 10⁻³⁰⁸.

~~~java
double smallest = Double.MIN_VALUE;
double underflow = smallest / 2.0;

System.out.println(smallest > 0.0);   // true
System.out.println(underflow == 0.0); // true
~~~

Underflow không nhất thiết là lỗi. Trong một số thuật toán, giá trị cực nhỏ có thể được bỏ qua; trong thuật toán khác, mất nó có thể làm sai kết quả. Cần chọn ngưỡng, độ chính xác và thuật toán theo yêu cầu miền.

## 5. NaN, infinity và signed zero

### NaN

NaN (Not a Number) có thể xuất hiện từ những phép toán không xác định theo số thực, ví dụ 0.0 / 0.0 hoặc căn bậc hai của số âm bằng Math.sqrt:

~~~java
double nan = 0.0 / 0.0;

System.out.println(Double.isNaN(nan)); // true
System.out.println(nan == nan);        // false
System.out.println(nan < 1.0);         // false
System.out.println(nan > 1.0);         // false
System.out.println(nan != 1.0);        // true
~~~

Mọi phép so sánh quan hệ với NaN như <, <=, >, >= đều false; phép == với NaN cũng false, kể cả khi so với chính nó. Vì thế, kiểm tra dữ liệu bằng điều kiện score < 0 || score > 100 **không loại được NaN**: cả hai vế đều false và chương trình có thể kết luận nhầm rằng giá trị hợp lệ. Dùng Double.isNaN hoặc Double.isFinite khi miền không cho phép NaN.

### Infinity

Với phép toán double:

~~~java
System.out.println(1.0 / 0.0);   // Infinity
System.out.println(-1.0 / 0.0);  // -Infinity
System.out.println(1.0 / -0.0);  // -Infinity
~~~

Chia floating-point cho zero không giống chia số nguyên cho zero: phép chia số nguyên ném ArithmeticException, trong khi phép chia double có thể tạo infinity hoặc NaN theo quy tắc IEEE 754.

Nếu một API chỉ nhận giá trị hữu hạn, dùng Double.isFinite(x) thay vì chỉ kiểm tra x != Double.POSITIVE_INFINITY, vì cách sau bỏ sót negative infinity và NaN.

### Positive zero và negative zero

IEEE 754 có cả +0.0 và -0.0:

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);            // Infinity
System.out.println(1.0 / negativeZero);           // -Infinity
~~~

Phép so sánh == xem hai zero bằng nhau, nhưng dấu có thể ảnh hưởng đến một số phép toán và cách biểu diễn. Nếu miền cần phân biệt dấu zero (ví dụ thuật toán số học đặc thù), cần kiểm tra sign bit hoặc dùng Double.compare trong ngữ cảnh thích hợp. Đừng dùng == để khẳng định hai giá trị có cùng bit pattern.

## 6. So sánh số thực: không dùng một epsilon tùy tiện

So sánh bằng tuyệt đối:

~~~java
if (actual == expected) {
    // ...
}
~~~

chỉ phù hợp khi hai giá trị được kỳ vọng có cùng biểu diễn, hoặc phép toán đảm bảo kết quả chính xác theo hợp đồng. Với kết quả tính toán từ nhiều phép toán dấu phẩy động, so sánh tuyệt đối thường quá nghiêm ngặt.

Một cách thường dùng là so sánh với tolerance:

~~~java
Math.abs(actual - expected) <= tolerance
~~~

Nhưng tolerance tuyệt đối cố định không phù hợp cho mọi độ lớn. Sai số 1e-9 có thể rất lớn khi expected gần 0, nhưng lại quá nhỏ khi expected cỡ 1e12.

### Kết hợp sai số tuyệt đối và tương đối

Một tiêu chí phổ biến:

\[
|a-b| \leq \max(\varepsilon_{abs}, \varepsilon_{rel}\cdot\max(|a|,|b|))
\]

Trong đó:

- epsilon tuyệt đối phù hợp để kiểm soát sai số gần zero.
- epsilon tương đối tỷ lệ theo độ lớn của hai giá trị.
- Ngưỡng phải dựa trên yêu cầu và sai số cho phép của thuật toán, không lấy một hằng số dùng cho mọi miền.

Ví dụ triển khai:

~~~java
static boolean nearlyEqual(
        double a,
        double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (absoluteTolerance < 0.0
            || relativeTolerance < 0.0
            || relativeTolerance > 1.0) {
        throw new IllegalArgumentException("Invalid tolerance");
    }

    if (Double.isNaN(a) || Double.isNaN(b)) {
        return false;
    }

    if (a == b) {
        // Bao gồm cùng infinity và +0.0 so với -0.0.
        return true;
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    double allowed = Math.max(
            absoluteTolerance,
            relativeTolerance * scale);

    return difference <= allowed;
}
~~~

Hàm này chọn quy ước NaN không bằng bất kỳ giá trị nào, hai infinity cùng dấu được coi bằng nhau, và +0.0/-0.0 được coi tương đương về số học. Những lựa chọn đó phải phù hợp hợp đồng của bài toán. Nếu cần phân biệt signed zero hoặc so sánh NaN theo bit, cần API so sánh khác.

Một tolerance thực tế phải được xác định từ:

1. Đơn vị và độ lớn dữ liệu.
2. Số phép toán và sai số tích lũy dự kiến.
3. Yêu cầu chính xác của nghiệp vụ hoặc thuật toán.
4. Ảnh hưởng của sai số đến quyết định ở ngưỡng.

### Math.ulp không phải epsilon phổ quát

Math.ulp(x) trả về khoảng cách giữa x và số dấu phẩy động kế tiếp lớn hơn theo độ lớn/biểu diễn tại vị trí đó. Nó hữu ích để hiểu spacing ở một giá trị cụ thể, nhưng không phải ngưỡng chấp nhận sai số chung cho mọi thuật toán.

Ví dụ:

~~~java
System.out.println(Math.ulp(1.0));
System.out.println(Math.ulp(1.0e16));
System.out.println(Math.ulp(0.0));
~~~

Khoảng cách tăng theo độ lớn. Một sai số vài ULP có thể phù hợp cho một thuật toán số học cụ thể, nhưng không tự động là hợp lệ cho mọi phép đo hay quy tắc nghiệp vụ.

## 7. Khi nào nên dùng BigDecimal thay vì double?

Nếu cần biểu diễn số thập phân theo quy tắc nghiệp vụ chính xác, chẳng hạn tiền, tỷ lệ hóa đơn hoặc giá trị cần làm tròn theo số chữ số thập phân xác định, BigDecimal thường phù hợp hơn double.

~~~java
double floatingTotal = 0.1 + 0.2;

java.math.BigDecimal decimalTotal =
        new java.math.BigDecimal("0.1")
                .add(new java.math.BigDecimal("0.2"));

System.out.println(floatingTotal); // 0.30000000000000004
System.out.println(decimalTotal);  // 0.3
~~~

### Tránh new BigDecimal(double) cho số thập phân nhập vào

~~~java
System.out.println(new java.math.BigDecimal(0.1));
System.out.println(java.math.BigDecimal.valueOf(0.1));
System.out.println(new java.math.BigDecimal("0.1"));
~~~

- Constructor nhận double chuyển chính xác giá trị nhị phân double sang BigDecimal, vì vậy thường tạo ra chuỗi chữ số dài ngoài mong muốn của người dùng.
- BigDecimal.valueOf(double) dựa trên biểu diễn thập phân chuẩn của Double.toString.
- Constructor nhận String là lựa chọn rõ ràng khi nguồn dữ liệu đã là chuỗi thập phân, ví dụ request JSON được parse theo hợp đồng decimal.

Nếu nguồn đầu vào đã là double, BigDecimal.valueOf có thể phù hợp với ý nghĩa thập phân được biểu diễn bởi chuỗi chuẩn của double, nhưng nó không khôi phục được thông tin thập phân ban đầu đã mất khi parse vào double.

### BigDecimal vẫn cần chính sách scale và rounding

BigDecimal biểu diễn số thập phân chính xác, nhưng phép chia có kết quả thập phân vô hạn (ví dụ 1 chia 3) cần quy định scale và RoundingMode:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal result = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        2,
        RoundingMode.HALF_UP);

System.out.println(result); // 0.33
~~~

Ngoài ra:

- BigDecimal.equals so sánh cả giá trị lẫn scale; 2.0 và 2.00 không equals.
- BigDecimal.compareTo so sánh giá trị số; 2.0 và 2.00 có compareTo bằng 0.
- Không nên chọn rounding mode chỉ vì tiện; quy tắc làm tròn tiền phải theo hợp đồng nghiệp vụ và quy định áp dụng.
- Với tiền tệ, có thể dùng số nguyên theo đơn vị nhỏ nhất nếu miền xác định rõ scale; với nhiều loại tiền có số chữ số thập phân khác nhau, cần quy tắc theo Currency/đơn vị tương ứng.

## 8. Thuật toán cộng nhiều số và sai số tích lũy

Khi cộng nhiều số có độ lớn rất khác nhau, số nhỏ có thể bị mất khi cộng vào tổng lớn. Ví dụ:

~~~java
double total = 1.0e16;
total += 1.0;
total -= 1.0e16;

System.out.println(total); // 0.0
~~~

Giá trị 1.0 có thể bị làm tròn mất khi cộng vào 1e16; sau đó phép trừ không thể khôi phục nó.

### Sắp xếp thứ tự cộng

Trong một số dữ liệu, cộng các giá trị nhỏ trước rồi mới cộng vào tổng lớn có thể giảm mất mát:

~~~java
double smallFirst = (1.0 + 1.0) + 1.0e16;
double largeFirst = (1.0e16 + 1.0) + 1.0;

System.out.println(smallFirst);
System.out.println(largeFirst);
~~~

Đây không phải quy tắc tổng quát bảo đảm kết quả chính xác cho mọi tập dữ liệu. Sắp xếp lại thứ tự có thể thay đổi kết quả và đôi khi tốn chi phí; chỉ dùng khi thuật toán và hợp đồng cho phép.

### Kahan compensated summation

Với phép cộng nhiều giá trị double, thuật toán Kahan giữ một biến hiệu chỉnh để bù một phần sai số bị mất:

~~~java
static double kahanSum(double[] values) {
    double sum = 0.0;
    double compensation = 0.0;

    for (double value : values) {
        double adjusted = value - compensation;
        double next = sum + adjusted;
        compensation = (next - sum) - adjusted;
        sum = next;
    }

    return sum;
}
~~~

Kahan summation có thể cải thiện độ chính xác trong nhiều trường hợp cộng dãy số, nhưng không làm phép cộng double trở thành kết hợp hoặc đảm bảo kết quả đúng tuyệt đối. Với các dãy đặc biệt, độ lớn rất khác nhau hoặc overflow, cần đánh giá thuật toán phù hợp; Neumaier summation hoặc thuật toán chuyên biệt có thể phù hợp hơn.

### Math.fma

Java cung cấp Math.fma(a, b, c) để tính a × b + c với một lần làm tròn cuối thay vì làm tròn riêng tích rồi mới làm tròn tổng:

~~~java
double a = 1.0000000000000002;
double b = 1.0000000000000002;
double c = -1.0000000000000004;

double separate = a * b + c;
double fused = Math.fma(a, b, c);

System.out.println(separate);
System.out.println(fused);
~~~

Math.fma có thể cho kết quả khác với phép nhân rồi cộng tách rời. Đây là hành vi được định nghĩa, không phải lỗi. Chỉ thay bằng FMA khi thuật toán cần ngữ nghĩa fused multiply-add và đã được phân tích; nó không làm mọi biểu thức đại số tương đương trở thành tương đương bit.

## 9. Kiểm thử biên với JUnit 5

Kiểm thử số thực cần xác định rõ điều kiện hợp lệ, sai số chấp nhận và các giá trị biên. Ví dụ lớp:

~~~java
public final class ScoreValidator {
    private ScoreValidator() {}

    public static boolean isValid(double score) {
        return Double.isFinite(score)
                && score >= 0.0
                && score <= 100.0;
    }
}
~~~

Bài test JUnit Jupiter:

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class ScoreValidatorTest {
    @Test
    void acceptsBothInclusiveBoundaries() {
        assertTrue(ScoreValidator.isValid(0.0));
        assertTrue(ScoreValidator.isValid(100.0));
    }

    @Test
    void rejectsValuesImmediatelyOutsideBoundaries() {
        assertFalse(ScoreValidator.isValid(Math.nextDown(0.0)));
        assertFalse(ScoreValidator.isValid(Math.nextUp(100.0)));
    }

    @Test
    void acceptsValuesImmediatelyInsideBoundaries() {
        assertTrue(ScoreValidator.isValid(Math.nextUp(0.0)));
        assertTrue(ScoreValidator.isValid(Math.nextDown(100.0)));
    }

    @Test
    void rejectsNonFiniteValues() {
        assertFalse(ScoreValidator.isValid(Double.NaN));
        assertFalse(ScoreValidator.isValid(Double.POSITIVE_INFINITY));
        assertFalse(ScoreValidator.isValid(Double.NEGATIVE_INFINITY));
    }
}
~~~

Khi kiểm thử một phép tính gần đúng, JUnit 5 cung cấp overload có delta:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

assertEquals(0.3, 0.1 + 0.2, 1.0e-12);
~~~

Delta trong test phải xuất phát từ yêu cầu và scale của phép tính. Đừng dùng một delta quá rộng khiến test chấp nhận cả kết quả sai; cũng đừng dùng một delta quá nhỏ khiến test phụ thuộc vào sai số không có ý nghĩa với nghiệp vụ.

### Kiểm thử tính không kết hợp

~~~java
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class FloatingPointTest {
    @Test
    void additionCanDependOnGrouping() {
        double a = 1.0e16;
        double b = -1.0e16;
        double c = 1.0;

        double left = (a + b) + c;
        double right = a + (b + c);

        assertEquals(1.0, left);
        assertEquals(0.0, right);
        assertNotEquals(left, right);
    }

    @Test
    void decimalFractionsAreNotAlwaysExactlyRepresentable() {
        assertNotEquals(0.3, 0.1 + 0.2);
        assertEquals(0.3, 0.1 + 0.2, 1.0e-12);
    }
}
~~~

Test đầu tiên không phải để khuyến khích code phụ thuộc vào kết quả cụ thể của mọi phép tính, mà để ghi nhận rằng **đổi nhóm có thể đổi kết quả**. Với thuật toán thật, hãy kiểm tra tính chất đầu ra, sai số tối đa và các tình huống cực trị thay vì chỉ lặp lại ví dụ minh họa.

## 10. Chuyển đổi số giữa double và kiểu khác

Chuyển từ double sang int hoặc long không làm tròn theo cách Math.round. Phép ép kiểu số thực sang số nguyên loại bỏ phần thập phân theo hướng về 0, đồng thời có quy tắc giới hạn với giá trị quá lớn và xử lý NaN:

~~~java
System.out.println((int) 3.9);                 // 3
System.out.println((int) -3.9);                // -3
System.out.println((int) Double.NaN);          // 0
System.out.println((int) Double.POSITIVE_INFINITY); // Integer.MAX_VALUE
~~~

Nếu nghiệp vụ cần làm tròn, chọn Math.round, Math.floor, Math.ceil hoặc BigDecimal.setScale với RoundingMode phù hợp. Không dùng ép kiểu để thay thế một quy tắc làm tròn chưa được xác định.

Ngoài ra, khi chuyển long sang double, các số nguyên lớn hơn vùng chính xác liên tiếp có thể bị làm tròn. Khi chuyển double sang long, phần thập phân bị bỏ và giá trị quá phạm vi có thể bị giới hạn theo quy tắc chuyển đổi của Java. Nếu dữ liệu là ID, mã, số lượng hoặc số nguyên chính xác, giữ kiểu nguyên phù hợp xuyên suốt hệ thống.

## 11. Danh sách tình huống nên có trong bộ test

| Mục tiêu kiểm thử | Dữ liệu đề xuất | Điều cần khẳng định |
| --- | --- | --- |
| Đúng tại ngưỡng | T | Điều kiện inclusive/exclusive |
| Sát dưới ngưỡng | Math.nextDown(T) | Nhánh phía dưới |
| Sát trên ngưỡng | Math.nextUp(T) | Nhánh phía trên |
| Giá trị zero | +0.0 và -0.0 | Quy tắc signed zero |
| Số dương nhỏ nhất | Double.MIN_VALUE | Hành vi subnormal |
| Biên normal | Double.MIN_NORMAL và số kề | Chuyển vùng normal/subnormal |
| Biên hữu hạn | Double.MAX_VALUE và phép toán gây overflow | Kết quả finite/infinite |
| NaN | Double.NaN | Validation và so sánh |
| Infinity | Hai dấu infinity | Validation và nhánh xử lý |
| Giá trị thập phân phổ biến | 0.1, 0.2, 0.3 | So sánh có tolerance |
| Cộng dãy độ lớn khác nhau | Số rất lớn xen số nhỏ | Sai số tích lũy |
| Đổi nhóm | (a + b) + c và a + (b + c) | Không giả định kết quả giống nhau |
| Chuyển kiểu | long lớn, double ngoài phạm vi | Mất chính xác, truncation/saturation |

Không nhất thiết mọi hàm số thực đều cần toàn bộ các trường hợp này. Hãy chọn theo miền đầu vào và các phép toán mà hàm thực hiện. Ví dụ một hàm nhận tỷ lệ phần trăm hữu hạn trong [0, 1] cần test ngưỡng, NaN, infinity và giá trị sát biên; một thuật toán cộng dữ liệu cảm biến dài hạn cần quan tâm thêm đến sai số tích lũy và thứ tự cộng.

## 12. Nguyên tắc thiết kế và kiểm thử số thực

Khi làm việc với float/double trên Java 17:

1. Xác định rõ miền hợp lệ và các ngưỡng inclusive/exclusive.
2. Dùng Math.nextDown/nextUp để tạo giá trị biểu diễn được ngay hai bên ngưỡng.
3. Kiểm tra NaN và infinity tường minh nếu miền chỉ chấp nhận số hữu hạn.
4. Không mặc định phép cộng hoặc phép nhân có tính kết hợp; thay đổi thứ tự có thể đổi kết quả.
5. Chọn tolerance theo độ lớn, đơn vị và sai số thuật toán; không dùng một epsilon toàn cục.
6. Dùng BigDecimal hoặc số nguyên theo đơn vị nhỏ nhất khi cần quy tắc thập phân chính xác.
7. Dùng thuật toán cộng bù hoặc thuật toán chuyên biệt nếu tích lũy nhiều giá trị gây sai số đáng kể.
8. Kiểm thử cả dữ liệu hợp lệ, sát biên và dữ liệu không hữu hạn; không chỉ kiểm tra ví dụ thông thường.

Số thực dấu phẩy động rất hữu ích, nhưng chúng tuân theo quy tắc biểu diễn hữu hạn và làm tròn. Bộ test tốt phải kiểm tra những quy tắc đó một cách chủ động. Khi hiểu biên biểu diễn và không giả định tính kết hợp, chương trình Java 17 sẽ ít phụ thuộc vào những khác biệt nhỏ nhưng có thể gây hậu quả lớn trong tính toán thực tế.
