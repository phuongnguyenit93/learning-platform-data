# float, double và làm tròn theo biểu diễn nhị phân trong Java 17

**Chủ đề:** Java 17 → Số thực  
**Trọng tâm:** Hai kiểu số thực nguyên thủy float và double, cách chúng lưu giá trị theo chuẩn IEEE 754, vì sao nhiều phân số thập phân chỉ được biểu diễn gần đúng, và việc làm tròn trong phép tính khác với làm tròn khi hiển thị.

Trong Java 17, **float** và **double** là hai kiểu số thực dấu phẩy động (*floating-point primitive types*). Chúng lưu trữ số theo dạng nhị phân có độ chính xác hữu hạn. Vì vậy, một số thập phân nhìn rất đơn giản như 0.1 có thể không có biểu diễn nhị phân chính xác. Khi chương trình tính toán, giá trị được làm tròn về số dấu phẩy động có thể biểu diễn gần nhất theo quy tắc của IEEE 754.

Đây là đặc điểm của cách biểu diễn số, không phải lỗi riêng của Java. Hiểu rõ nó giúp chọn đúng kiểu dữ liệu, viết phép so sánh an toàn, giải thích kết quả làm tròn và tránh dùng float/double cho các phép tính cần độ chính xác thập phân tuyệt đối như số tiền.

## 1. float và double là gì?

Java cung cấp hai kiểu số thực nguyên thủy:

| Kiểu | Kích thước | Định dạng IEEE 754 | Độ chính xác significand | Độ chính xác thập phân gần đúng |
| --- | ---: | --- | ---: | ---: |
| float | 32 bit | binary32 | 24 bit (23 bit fraction + bit đầu ẩn với số chuẩn hóa) | khoảng 6–7 chữ số có nghĩa |
| double | 64 bit | binary64 | 53 bit (52 bit fraction + bit đầu ẩn với số chuẩn hóa) | khoảng 15–17 chữ số có nghĩa |

double có vùng giá trị và độ chính xác lớn hơn float, nên là lựa chọn mặc định cho phần lớn phép tính số thực thông thường trong Java.

Ví dụ khai báo:

~~~java
float temperature = 36.5f;
double distance = 12345.6789;
~~~

Hậu tố f hoặc F nói rằng literal là kiểu float. Nếu bỏ hậu tố, một literal dấu phẩy động như 36.5 mặc định có kiểu double.

~~~java
float a = 36.5f;  // Hợp lệ: literal có kiểu float.
double b = 36.5;  // Hợp lệ: literal có kiểu double.

// float c = 36.5; // Lỗi: double không tự thu hẹp thành float.
float c = (float) 36.5; // Ép kiểu tường minh, có thể mất độ chính xác.
~~~

Khi một giá trị float được chuyển rộng sang double, giá trị nhị phân mà float đang giữ được biểu diễn chính xác trong double; việc chuyển kiểu này không khôi phục phần thập phân đã mất trước đó.

## 2. Số dấu phẩy động được lưu theo dạng nhị phân

float và double dùng dạng biểu diễn gồm ba thành phần:

1. **Sign bit (bit dấu):** cho biết số dương hay âm.
2. **Exponent (số mũ):** điều chỉnh thang độ lớn của số.
3. **Significand/fraction (phần có nghĩa):** chứa các bit xác định độ chính xác của giá trị.

Với số chuẩn hóa (*normal number*), có thể hình dung giá trị theo dạng:

\[
(-1)^{sign} \times 1.fraction \times 2^{exponent-bias}
\]

Đây là mô hình khái quát; IEEE 754 còn có số dưới chuẩn hóa (*subnormal*), số không, vô cực và NaN với quy tắc riêng.

### 2.1. Cấu trúc bit

| Định dạng | Bit dấu | Bit exponent | Bit fraction | Độ chính xác significand |
| --- | ---: | ---: | ---: | ---: |
| binary32 (float) | 1 | 8 | 23 | 24 bit đối với số chuẩn hóa |
| binary64 (double) | 1 | 11 | 52 | 53 bit đối với số chuẩn hóa |

Bit đầu 1 của significand ở số chuẩn hóa được ngầm định nên không cần lưu trực tiếp. Cách tổ chức này cho phép biểu diễn một dải giá trị rất rộng bằng số bit hữu hạn, nhưng cũng có nghĩa chỉ một tập hợp hữu hạn các giá trị thực có thể được lưu chính xác.

### 2.2. Vì sao 0.5 chính xác nhưng 0.1 thì không?

Một phân số có biểu diễn nhị phân hữu hạn nếu sau khi rút gọn, mẫu số là lũy thừa của 2.

Ví dụ:

| Số thập phân | Phân số | Dạng nhị phân | Có thể biểu diễn chính xác hữu hạn? |
| --- | --- | --- | --- |
| 0.5 | 1/2 | 0.1₂ | Có |
| 0.25 | 1/4 | 0.01₂ | Có |
| 0.125 | 1/8 | 0.001₂ | Có |
| 0.75 | 3/4 | 0.11₂ | Có |
| 0.1 | 1/10 | 0.0001100110011...₂ | Không |
| 0.2 | 1/5 | 0.001100110011...₂ | Không |

Ví dụ 1/10 có mẫu số là 10 = 2 × 5. Sau khi rút gọn vẫn còn thừa số 5, nên biểu diễn nhị phân tiếp tục lặp. float hoặc double chỉ giữ được một số bit hữu hạn; phần còn lại phải được làm tròn.

Điều này không có nghĩa 0.1 luôn sai một cách đáng kể. Giá trị lưu thường là số nhị phân gần nhất với 0.1; sai số rất nhỏ, nhưng có thể quan sát được khi so sánh chính xác hoặc thực hiện nhiều phép tính liên tiếp.

## 3. Ví dụ quen thuộc: 0.1 + 0.2 không bằng 0.3

Xét chương trình:

~~~java
public class FloatingPointIntro {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;
        double sum = a + b;

        System.out.println(sum);
        System.out.println(sum == 0.3);

        System.out.println(Double.toHexString(a));
        System.out.println(Double.toHexString(b));
        System.out.println(Double.toHexString(sum));
        System.out.println(Double.toHexString(0.3));
    }
}
~~~

Biên dịch và chạy với JDK 17:

~~~shell
javac --release 17 FloatingPointIntro.java
java FloatingPointIntro
~~~

Kết quả:

~~~text
0.30000000000000004
false
0x1.999999999999ap-4
0x1.999999999999ap-3
0x1.3333333333334p-2
0x1.3333333333333p-2
~~~

Double.toHexString hiển thị dạng thập lục phân của giá trị dấu phẩy động, giúp nhìn rõ giá trị nhị phân đang được giữ. Kết quả của a + b là số biểu diễn được gần nhất với tổng toán học của hai giá trị đã lưu; literal 0.3 lại được làm tròn riêng. Hai kết quả khác nhau một đơn vị ở bit cuối của significand, nên == trả về false.

**Cần phân biệt:** System.out.println(0.1) thường in 0.1, vì Java dùng dạng chuỗi ngắn nhất có thể chuyển ngược về đúng giá trị double. Điều đó không chứng minh bit lưu trữ biểu diễn chính xác phân số 1/10.

## 4. Làm tròn xảy ra ở đâu?

Với kiểu dấu phẩy động có độ chính xác hữu hạn, làm tròn có thể xuất hiện ở nhiều thời điểm:

- Khi một literal thập phân được chuyển thành giá trị float hoặc double.
- Khi chuyển từ double sang float.
- Sau một phép toán dấu phẩy động như cộng, trừ, nhân hoặc chia, kết quả phải được biểu diễn lại bằng định dạng đích.
- Khi chuyển một giá trị dấu phẩy động sang dạng số nguyên hoặc dạng thập phân có số chữ số giới hạn.
- Khi định dạng giá trị thành chuỗi để hiển thị hoặc xuất tệp.

Những thao tác này không cùng một việc. Đặc biệt, **làm tròn giá trị lưu trong binary32/binary64** khác với **làm tròn số chữ số thập phân khi trình bày**.

### 4.1. Làm tròn khi lưu literal

~~~java
float f = 0.1f;
double d = 0.1;

System.out.println(f);
System.out.println(Double.toString((double) f));
System.out.println(d);
System.out.println(Float.toHexString(f));
System.out.println(Double.toHexString(d));
~~~

0.1f được làm tròn vào định dạng binary32. Khi mở rộng giá trị đó sang double, Java giữ chính xác giá trị binary32 đã lưu, nên Double.toString((double) f) có thể in 0.10000000149011612. Trong khi đó, 0.1 là literal double được làm tròn độc lập vào binary64.

### 4.2. Làm tròn khi chuyển double sang float

~~~java
double original = 1.23456789012345;
float narrowed = (float) original;
double widenedAgain = narrowed;

System.out.println(original);
System.out.println(narrowed);
System.out.println(widenedAgain);
~~~

narrowed chỉ còn độ chính xác binary32. Phép chuyển ngược float sang double không thể lấy lại các bit đã mất; nó chỉ biểu diễn chính xác giá trị float hiện có bằng định dạng rộng hơn.

### 4.3. Làm tròn sau phép toán

Mỗi phép toán dấu phẩy động tạo kết quả trong định dạng của nó và kết quả phải được làm tròn về một giá trị có thể biểu diễn. Vì vậy, sai số có thể xuất hiện ở từng bước chứ không chỉ ở lúc in ra màn hình.

Ví dụ:

~~~java
double x = 0.1 + 0.2;
double y = x + 0.3;
double z = 0.1 + (0.2 + 0.3);

System.out.println(x);
System.out.println(y);
System.out.println(z);
~~~

Do các toán hạng và kết quả trung gian được làm tròn, phép cộng dấu phẩy động không luôn có tính kết hợp như phép cộng số thực toán học:

\[
(a+b)+c \ne a+(b+c)
\]

trong một số trường hợp. Nếu chương trình nhạy với sai số tích lũy, cần chọn thuật toán và kiểu số phù hợp thay vì giả định mọi thứ tự tính toán đều cho kết quả giống nhau.

## 5. Quy tắc làm tròn mặc định của IEEE 754

Các phép toán dấu phẩy động cơ bản của Java tuân theo quy tắc IEEE 754. Với các phép toán thông thường, hướng làm tròn mặc định là **round to nearest, ties to even**:

- Chọn giá trị có thể biểu diễn gần nhất với kết quả chính xác.
- Nếu kết quả chính xác nằm đúng giữa hai giá trị biểu diễn được (*tie*), chọn giá trị có bit thấp nhất của significand chẵn.

Quy tắc này còn được gọi là *round half to even* hoặc *banker's rounding* trong ngữ cảnh làm tròn thập phân, nhưng phải chú ý rằng ở đây nó áp dụng cho **lưới giá trị nhị phân** của định dạng dấu phẩy động.

Không nên nhầm quy tắc này với:

- Math.round, có quy tắc làm tròn về số nguyên riêng.
- RoundingMode.HALF_UP, HALF_EVEN của BigDecimal, dùng khi làm tròn giá trị thập phân theo scale hoặc precision.
- Việc định dạng chuỗi với một số chữ số sau dấu thập phân.

Một giá trị double có thể đã được làm tròn ở binary64 trước khi bạn yêu cầu hiển thị hai chữ số thập phân. Làm tròn hiển thị không thể khôi phục phần thập phân ban đầu mà kiểu binary không lưu được.

## 6. float hay double: chọn thế nào?

| Tiêu chí | float | double |
| --- | --- | --- |
| Bộ nhớ mỗi giá trị | 4 byte | 8 byte |
| Độ chính xác | Thấp hơn | Cao hơn |
| Phạm vi giá trị | Hẹp hơn | Rộng hơn |
| Literal mặc định | Phải thêm f/F | Là mặc định cho literal thập phân |
| Dùng trong tính toán thông thường | Khi có lý do về bộ nhớ, băng thông hoặc API yêu cầu | Lựa chọn mặc định phổ biến |
| Sai số nhị phân với phân số thập phân | Có | Có, nhưng độ chính xác cao hơn |

Ví dụ chọn kiểu:

~~~java
float[] sensorSamples = new float[1_000_000];
double average = 0.0;
~~~

float có thể tiết kiệm bộ nhớ khi lưu lượng dữ liệu lớn, chẳng hạn một số mảng cảm biến, ảnh, đồ họa hoặc mô hình số. Tuy nhiên, cần đánh giá độ chính xác cần thiết và API đang sử dụng. Nếu không có lý do cụ thể, double thường là lựa chọn đơn giản và an toàn hơn về độ chính xác.

**Không chọn float chỉ vì số đầu vào có ít chữ số sau dấu phẩy.** Số lượng chữ số được viết trong source không quyết định nó có biểu diễn nhị phân chính xác hay không.

## 7. Không dùng float/double để lưu tiền cần chính xác thập phân

Giả sử cần tính tổng ba món hàng, mỗi món giá 0.10:

~~~java
double price = 0.10;
double total = price + price + price;

System.out.println(total);
~~~

Chương trình có thể hiển thị một kết quả gần 0.3, nhưng không nên dựa vào double để bảo đảm mọi phép tính tiền tệ chính xác theo từng đơn vị thập phân. Sai số nhỏ có thể tích lũy qua nhiều phép tính, ảnh hưởng đến tổng hóa đơn, thuế, chiết khấu và đối soát.

### 7.1. Dùng BigDecimal với chuỗi thập phân

Java cung cấp java.math.BigDecimal để biểu diễn số thập phân với độ chính xác tùy chọn. Khi giá trị đầu vào là dữ liệu thập phân, hãy tạo BigDecimal từ **chuỗi**:

~~~java
import java.math.BigDecimal;

public class MoneyExample {
    public static void main(String[] args) {
        BigDecimal price = new BigDecimal("0.10");
        BigDecimal quantity = new BigDecimal("3");
        BigDecimal total = price.multiply(quantity);

        System.out.println(total); // 0.30
    }
}
~~~

BigDecimal lưu giá trị thập phân không phụ thuộc vào việc phân số có biểu diễn hữu hạn trong binary hay không. Constructor nhận chuỗi "0.10" hiểu đúng giá trị thập phân và giữ cả scale là hai chữ số sau dấu thập phân.

### 7.2. Vì sao new BigDecimal(0.1) thường gây bất ngờ?

Ba cách tạo sau không hoàn toàn giống nhau:

~~~java
import java.math.BigDecimal;

BigDecimal fromString = new BigDecimal("0.1");
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
BigDecimal fromDouble = new BigDecimal(0.1);

System.out.println(fromString);
System.out.println(fromValueOf);
System.out.println(fromDouble);
~~~

Kết quả:

~~~text
0.1
0.1
0.1000000000000000055511151231257827021181583404541015625
~~~

- new BigDecimal("0.1"): tạo chính xác số thập phân được viết trong chuỗi.
- BigDecimal.valueOf(0.1): chuyển qua biểu diễn chuỗi chuẩn của double, cho kết quả thập phân ngắn 0.1 trong ví dụ này.
- new BigDecimal(0.1): biểu diễn chính xác giá trị binary64 hiện có của literal 0.1, vì vậy cho thấy phần sai lệch nhị phân dài.

Với dữ liệu tiền tệ hoặc dữ liệu thập phân từ người dùng, file, API hay cơ sở dữ liệu, ưu tiên đọc chuỗi thập phân và tạo BigDecimal từ chuỗi. Nếu dữ liệu đã là double, valueOf thường hữu ích hơn constructor BigDecimal(double), nhưng nó không thể khôi phục thông tin thập phân đã mất trước đó.

## 8. Làm tròn số thập phân với BigDecimal và RoundingMode

Làm tròn đến hai chữ số thập phân cần một chính sách được xác định rõ. BigDecimal.setScale nhận số chữ số thập phân mong muốn và một RoundingMode.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class DecimalRoundingDemo {
    public static void main(String[] args) {
        BigDecimal value = new BigDecimal("1.235");

        System.out.println(
            value.setScale(2, RoundingMode.HALF_UP)
        );
        System.out.println(
            value.setScale(2, RoundingMode.HALF_EVEN)
        );
    }
}
~~~

Kết quả:

~~~text
1.24
1.24
~~~

Với ví dụ này cả hai chế độ đều cho 1.24. Để thấy sự khác biệt ở trường hợp đúng giữa:

~~~java
BigDecimal value = new BigDecimal("1.245");

System.out.println(value.setScale(2, RoundingMode.HALF_UP));   // 1.25
System.out.println(value.setScale(2, RoundingMode.HALF_EVEN)); // 1.24
~~~

HALF_UP chọn phía xa số 0 khi đúng giữa hai lựa chọn; HALF_EVEN chọn phía có chữ số cuối cùng chẵn. Quy tắc phù hợp phải được chọn theo hợp đồng nghiệp vụ, quy định kế toán hoặc tiêu chuẩn mà ứng dụng phải tuân thủ.

### 8.1. Một số RoundingMode thường gặp

| Chế độ | Ý nghĩa khái quát |
| --- | --- |
| UP | Làm tròn xa số 0 nếu phải bỏ phần dư. |
| DOWN | Bỏ phần dư về phía 0. |
| CEILING | Làm tròn về phía dương vô cực. |
| FLOOR | Làm tròn về phía âm vô cực. |
| HALF_UP | Gần nhất; trường hợp đúng giữa thì xa số 0. |
| HALF_DOWN | Gần nhất; trường hợp đúng giữa thì về phía 0. |
| HALF_EVEN | Gần nhất; trường hợp đúng giữa thì chọn chữ số cuối chẵn. |
| UNNECESSARY | Yêu cầu không phát sinh làm tròn; nếu cần làm tròn sẽ ném ArithmeticException. |

setScale(2, ...) giới hạn **hai chữ số sau dấu thập phân**. Đây khác với MathContext, vốn giới hạn số chữ số có nghĩa tổng thể.

## 9. Math.round, ép kiểu và định dạng hiển thị không giống nhau

Nhiều lỗi xuất hiện vì dùng một thao tác cho mục đích của thao tác khác.

### 9.1. Math.round làm tròn về số nguyên

~~~java
System.out.println(Math.round(2.3));   // 2
System.out.println(Math.round(2.5));   // 3
System.out.println(Math.round(-2.5));  // -2
System.out.println(Math.round(-2.6));  // -3
~~~

Math.round(double) trả về long; Math.round(float) trả về int. Quy tắc tương đương floor(x + 0.5) đối với giá trị hữu hạn trong phạm vi có thể biểu diễn. Vì vậy, trường hợp đúng giữa với số âm không giống RoundingMode.HALF_UP: Math.round(-2.5) là -2, tức làm tròn về phía dương vô cực.

Math.round không phải cách tổng quát để làm tròn tiền đến hai chữ số thập phân.

### 9.2. Ép kiểu sang số nguyên cắt phần thập phân về phía 0

~~~java
System.out.println((int) 3.9);   // 3
System.out.println((int) -3.9);  // -3
~~~

Đây là phép chuyển kiểu thu hẹp sang số nguyên, không phải làm tròn đến số nguyên gần nhất. Nó bỏ phần lẻ về phía 0 (ngoại lệ về NaN/vô cực và tràn được quy định riêng).

### 9.3. Định dạng chỉ làm tròn cách trình bày

Nếu mục tiêu là hiển thị số với hai chữ số thập phân, có thể dùng DecimalFormat và chỉ định chế độ làm tròn:

~~~java
import java.text.DecimalFormat;
import java.math.RoundingMode;

DecimalFormat formatter = new DecimalFormat("0.00");
formatter.setRoundingMode(RoundingMode.HALF_UP);

System.out.println(formatter.format(12.3)); // 12.30
~~~

DecimalFormat tạo ra chuỗi để hiển thị. Nó **không thay đổi biến double ban đầu** thành một giá trị có hai chữ số thập phân và cũng không khôi phục được phần thập phân ban đầu nếu giá trị binary đã gần đúng. Với dữ liệu cần tính toán chính xác, hãy làm việc với BigDecimal, áp dụng scale và rounding policy, sau đó định dạng kết quả.

## 10. So sánh float/double: tránh dùng == cho kết quả tính gần đúng

Với số nguyên, so sánh bằng == thường đúng với ý nghĩa mong muốn. Với số thực được tạo từ các phép tính gần đúng, hai giá trị toán học dự kiến bằng nhau có thể khác nhau ở bit cuối.

Ví dụ:

~~~java
double result = 0.1 + 0.2;

if (result == 0.3) {
    System.out.println("Bằng nhau");
} else {
    System.out.println("Khác nhau theo biểu diễn");
}
~~~

Nếu bài toán chấp nhận sai số, có thể so sánh theo ngưỡng:

~~~java
static boolean nearlyEqual(double a, double b, double tolerance) {
    return Math.abs(a - b) <= tolerance;
}
~~~

Ví dụ:

~~~java
double result = 0.1 + 0.2;
System.out.println(nearlyEqual(result, 0.3, 1e-12)); // true
~~~

tolerance phải xuất phát từ độ chính xác cần thiết và thang độ lớn của dữ liệu. Một epsilon cố định không phù hợp cho mọi miền giá trị. Với bài toán yêu cầu chính xác tuyệt đối theo đơn vị thập phân, dùng BigDecimal hoặc số nguyên theo đơn vị nhỏ nhất thay vì so sánh gần đúng.

Ngoài ra, cần xử lý riêng NaN và vô cực:

~~~java
double value = Double.NaN;

System.out.println(value == value);         // false
System.out.println(Double.isNaN(value));    // true
System.out.println(Double.isFinite(value)); // false
~~~

NaN không bằng chính nó theo phép so sánh ==; dùng Double.isNaN để kiểm tra. Double.isFinite giúp xác định giá trị không phải NaN và cũng không phải vô cực.

## 11. Số 0 âm, số dưới chuẩn hóa và giới hạn biểu diễn

IEEE 754 có hai biểu diễn số 0: +0.0 và -0.0. Trong Java:

~~~java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0 / positiveZero);           // Infinity
System.out.println(1.0 / negativeZero);          // -Infinity
~~~

Hai số 0 so sánh bằng nhau bằng ==, nhưng dấu có thể ảnh hưởng đến kết quả một số phép toán như phép chia. Khi cần phân biệt dấu của số 0, có thể dùng Double.doubleToRawLongBits hoặc Double.compare.

Ở vùng rất nhỏ, IEEE 754 hỗ trợ **subnormal values** (số dưới chuẩn hóa) để biểu diễn dần các giá trị tiến gần về 0 với độ chính xác giảm. Ở vùng rất lớn, kết quả có thể tràn thành vô cực:

~~~java
System.out.println(Double.MAX_VALUE);
System.out.println(Double.MIN_VALUE);
System.out.println(1e308 * 1e308); // Infinity
~~~

Lưu ý Double.MIN_VALUE là số dương nhỏ nhất khác 0 có thể biểu diễn, không phải giá trị âm nhỏ nhất. Giá trị âm nhỏ nhất theo độ lớn là -Double.MAX_VALUE.

Đối với float, các hằng tương ứng là Float.MAX_VALUE, Float.MIN_VALUE và các phương thức kiểm tra Float.isFinite, Float.isNaN.

## 12. Java 17 và tính nhất quán của phép toán dấu phẩy động

Từ Java 17, **mọi phép toán dấu phẩy động đều có ngữ nghĩa nghiêm ngặt theo IEEE 754** nhờ JEP 306 (*Restore Always-Strict Floating-Point Semantics*). Kết quả float và double không còn phụ thuộc việc JVM có sử dụng chế độ biểu diễn mở rộng trung gian như các quy tắc cũ cho phép hay không.

Điều này có nghĩa:

- Các phép toán cơ bản tuân theo ngữ nghĩa nghiêm ngặt của kiểu float hoặc double.
- Kết quả không thay đổi chỉ vì JVM chạy trên một kiến trúc phần cứng khác.
- strictfp không còn cần thiết để yêu cầu ngữ nghĩa nghiêm ngặt trong Java 17. Modifier này vẫn có thể xuất hiện trong mã cũ, nhưng không còn làm thay đổi ngữ nghĩa tính toán.

Ví dụ:

~~~java
public strictfp class StrictFloatingPoint {
    public static double calculate(double a, double b) {
        return a + b;
    }
}
~~~

Trong Java 17, từ khóa strictfp ở đây là dư thừa về ngữ nghĩa. Khi đọc mã mới, không cần thêm strictfp cho mọi lớp hoặc phương thức số học.

**Ngữ nghĩa nghiêm ngặt không đồng nghĩa số thực trở nên chính xác tuyệt đối.** 0.1 + 0.2 vẫn có thể là 0.30000000000000004, vì đó là kết quả nhất quán của phép tính trên các giá trị binary đã được lưu.

## 13. Chương trình tổng hợp: quan sát nhiều loại làm tròn

Tạo tệp **FloatDoubleRoundingDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class FloatDoubleRoundingDemo {
    public static void main(String[] args) {
        double a = 0.1;
        double b = 0.2;
        double sum = a + b;

        System.out.println("0.1 + 0.2 = " + sum);
        System.out.println("sum == 0.3: " + (sum == 0.3));
        System.out.println("binary64 0.1: " + Double.toHexString(a));

        float f = 0.1f;
        System.out.println("float 0.1: " + f);
        System.out.println("float widened: " + (double) f);

        BigDecimal exact = new BigDecimal("0.1")
            .add(new BigDecimal("0.2"));
        BigDecimal rounded = exact.setScale(2, RoundingMode.HALF_EVEN);
        System.out.println("BigDecimal sum: " + exact);
        System.out.println("Rounded to 2 places: " + rounded);
    }
}
~~~

Biên dịch và chạy:

~~~shell
javac --release 17 FloatDoubleRoundingDemo.java
java FloatDoubleRoundingDemo
~~~

Kết quả:

~~~text
0.1 + 0.2 = 0.30000000000000004
sum == 0.3: false
binary64 0.1: 0x1.999999999999ap-4
float 0.1: 0.1
float widened: 0.10000000149011612
BigDecimal sum: 0.3
Rounded to 2 places: 0.30
~~~

Chương trình minh họa ba lớp vấn đề khác nhau:

1. float và double lưu các giá trị gần đúng trong định dạng nhị phân hữu hạn.
2. double có nhiều bit chính xác hơn float, nhưng vẫn không biểu diễn chính xác được mọi phân số thập phân.
3. BigDecimal nhận chuỗi thập phân có thể giữ đúng giá trị thập phân mong muốn và áp dụng chính sách làm tròn được chỉ định.

## 14. Chọn công cụ theo mục tiêu

| Mục tiêu | Cách dùng phù hợp | Lý do |
| --- | --- | --- |
| Tính toán số thực khoa học, đồ họa, mô phỏng | double hoặc float khi có lý do rõ ràng | Hiệu năng tốt, vùng giá trị rộng, sai số được kiểm soát theo IEEE 754. |
| Dữ liệu thập phân như tiền, thuế, giá bán | BigDecimal từ chuỗi hoặc số nguyên theo đơn vị nhỏ nhất | Tránh sai số binary không phù hợp với hợp đồng nghiệp vụ. |
| Hiển thị số với số chữ số cố định | DecimalFormat/Formatter với quy tắc làm tròn được xác định | Điều khiển cách trình bày mà không nhầm với giá trị lưu trữ. |
| Làm tròn số thực về số nguyên gần nhất | Math.round khi đúng với quy tắc nghiệp vụ | Quy tắc tie của Math.round khác các RoundingMode thập phân. |
| So sánh kết quả tính gần đúng | So sánh theo tolerance có căn cứ | Tránh yêu cầu bit bằng nhau khi bài toán chỉ cần gần bằng. |
| Yêu cầu làm tròn đến số lẻ thập phân xác định | BigDecimal.setScale(scale, mode) | Quy định rõ scale và rounding policy. |

Không có một kiểu số phù hợp cho mọi bài toán. Hãy xác định **độ chính xác, miền giá trị, quy tắc làm tròn và hợp đồng dữ liệu** trước khi chọn kiểu.

## 15. Các câu hỏi thường gặp

**Vì sao System.out.println(0.1) in 0.1 dù giá trị không chính xác tuyệt đối?**  
Vì Java in dạng thập phân ngắn nhất có thể đọc lại thành đúng giá trị double đang lưu. Chuỗi hiển thị ngắn không phải bản chụp toàn bộ bit nhị phân.

**Dùng double có hết lỗi 0.1 + 0.2 không?**  
Không. double giảm sai số so với float nhờ significand dài hơn, nhưng vẫn không biểu diễn chính xác mọi phân số thập phân.

**Tại sao float f = 0.1 báo lỗi?**  
Literal 0.1 mặc định là double; gán sang float là thu hẹp có thể mất thông tin. Viết 0.1f hoặc ép kiểu tường minh nếu chấp nhận việc làm tròn.

**Math.round có phải cách làm tròn tiền đến hai chữ số không?**  
Không. Math.round làm tròn về số nguyên và có quy tắc riêng với giá trị âm. Dùng BigDecimal.setScale với RoundingMode theo chính sách thập phân của ứng dụng.

**BigDecimal.valueOf(double) có giống new BigDecimal(double) không?**  
Không. Constructor BigDecimal(double) biểu diễn chính xác giá trị binary64. valueOf sử dụng dạng chuỗi chuẩn của double; với dữ liệu đầu vào thập phân, tạo trực tiếp từ String vẫn rõ ràng nhất.

**Java 17 có cần strictfp không?**  
Không cần để có ngữ nghĩa dấu phẩy động nghiêm ngặt. Từ Java 17, mọi phép toán float và double đã luôn strict theo JEP 306.

**Có thể dùng == để so sánh hai double không?**  
Có thể khi chủ đích là so sánh chính xác hai giá trị biểu diễn, nhưng với kết quả tính gần đúng thường nên so sánh theo tolerance hoặc dùng kiểu thập phân chính xác nếu nghiệp vụ yêu cầu.

## 16. Tài liệu tham khảo chính thức

- [Java Language Specification 17 — Floating-Point Types, Formats, and Values (§4.2.3)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): kiểu float, double, định dạng và các giá trị đặc biệt.
- [Java Language Specification 17 — Floating-Point Operations (§15.4)](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): ngữ nghĩa thực hiện phép toán dấu phẩy động.
- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): thay đổi được áp dụng từ Java 17.
- [Java SE 17 API — java.math.BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số thập phân chính xác, scale, precision và phép làm tròn.
- [Java SE 17 API — java.math.RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): các chính sách làm tròn.
- [Java SE 17 API — java.lang.Math](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): round, abs, các hàm số học và kiểm tra giá trị.
- [Java SE 17 API — java.text.DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): định dạng số và thiết lập rounding mode.

**Nguyên tắc áp dụng:** float và double lưu số theo biểu diễn nhị phân có độ chính xác hữu hạn, vì vậy một số thập phân có thể được lưu gần đúng và mỗi phép tính có thể phát sinh làm tròn. Hãy dùng double cho số thực thông thường khi cần độ chính xác cao hơn float; dùng BigDecimal hoặc đơn vị nguyên cho dữ liệu thập phân cần chính xác; và tách riêng làm tròn giá trị tính toán với định dạng hiển thị.
