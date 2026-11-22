# Thu hẹp `double` sang `float` và mất độ chính xác trong Java

Trong Java, `double` và `float` đều là kiểu dấu phẩy động nhị phân theo IEEE 754, nhưng **khác độ rộng và miền biểu diễn**. Ép `double` sang `float` là *narrowing primitive conversion* (chuyển kiểu nguyên thủy thu hẹp). Phép ép được phép với cú pháp `(float)`, nhưng có thể **làm tròn, mất bit chính xác, mất khả năng phân biệt hai giá trị, thành vô cực hoặc thành 0**.

```java
double original = 0.1;
float narrowed = (float) original;
double widenedAgain = narrowed;

System.out.println(original);             // 0.1
System.out.println(narrowed);             // 0.1
System.out.println(widenedAgain);         // 0.10000000149011612
System.out.println(original == widenedAgain); // false
```

Bề ngoài cả hai dòng đầu đều in `0.1`, nhưng chúng **không chứa cùng một giá trị nhị phân**. Phần dưới sẽ giải thích điều gì xảy ra, khi nào an toàn, cách phát hiện mất thông tin và cách chọn kiểu cho bài toán thực tế.

## 1. `double` và `float` khác nhau thế nào?

| Thuộc tính | `float` (binary32) | `double` (binary64) |
| --- | --- | --- |
| Dung lượng biểu diễn | 32 bit | 64 bit |
| Bit dấu | 1 | 1 |
| Bit số mũ lưu trữ | 8 | 11 |
| Bit phần fraction lưu trữ | 23 | 52 |
| Độ chính xác significand với bit ẩn ở số chuẩn hóa | 24 bit | 53 bit |
| Số chữ số thập phân chính xác thường dùng để ước lượng | Khoảng 6–7 chữ số có nghĩa | Khoảng 15–16 chữ số có nghĩa |
| Số dương hữu hạn lớn nhất | Khoảng `3.4028235 × 10^38` | Khoảng `1.7976931348623157 × 10^308` |
| Số dương chuẩn hóa nhỏ nhất | `Float.MIN_NORMAL`, khoảng `1.17549435 × 10^-38` | `Double.MIN_NORMAL`, khoảng `2.2250738585072014 × 10^-308` |
| Số dương khác 0 nhỏ nhất (subnormal) | `Float.MIN_VALUE`, khoảng `1.4 × 10^-45` | `Double.MIN_VALUE`, khoảng `4.9 × 10^-324` |

**Chú ý:** `Float.MIN_VALUE` **không phải** số âm có độ lớn lớn nhất. Nó là **số dương khác 0 nhỏ nhất** mà `float` biểu diễn được. Muốn giá trị âm hữu hạn có độ lớn lớn nhất, dùng `-Float.MAX_VALUE`. Hai kiểu còn có `+0.0`, `-0.0`, `NaN`, `+Infinity` và `-Infinity`.

`float` không đơn giản là “`double` nhưng in ít chữ số hơn”. Nó chỉ có 24 bit significand và miền số mũ nhỏ hơn nhiều. Khi đổi từ binary64 sang binary32, Java phải chọn một giá trị có thể biểu diễn trong **tập số `float`**, chứ không được giữ nguyên mọi bit có trong `double`.

## 2. Cú pháp: vì sao cần cast tường minh?

Chuyển từ `float` lên `double` là *widening primitive conversion*: Java cho phép ngầm. Chuyển từ `double` xuống `float` là thu hẹp: ở gán biến, cần cast rõ ràng.

```java
float measurement = 12.5f;
double widened = measurement; // Được phép ngầm.

double source = 12.5;
// float invalid = source;     // Lỗi biên dịch: possible lossy conversion.
float narrowed = (float) source; // Hợp lệ.
```

Với literal, `1.25` mặc định là `double`, còn hậu tố `f` hoặc `F` chọn literal `float`:

```java
float a = 1.25f;       // Literal float.
float b = (float) 1.25; // Ép literal double sang float.
double c = 1.25;       // Literal double.
```

Hậu tố `f` **khác** với việc bỏ qua mất chính xác: nó nói rằng literal được xét như giá trị `float`. Ví dụ `0.1f` vẫn là xấp xỉ nhị phân của 0.1, không phải 0.1 toán học chính xác.

### Khi cast xuất hiện gián tiếp

- Khi **truyền tham số**: phương thức nhận `float` không tự chấp nhận một biến `double`.
- Khi **trả kết quả**: phương thức khai báo trả `float` không thể `return` một biến `double` mà không cast.
- Khi **gán phần tử mảng** `float[]` hoặc trường `float`: cần chuyển hẹp.
- Trong **toán tử gán kết hợp** như `+=`, Java có quy tắc chuyển kiểu ngầm có thể che bớt sự mất chính xác.

```java
float sum = 0.1f;
double step = 0.2;

// sum = sum + step; // Không biên dịch: biểu thức float + double có kiểu double.
sum += step;         // Biên dịch; về ngữ nghĩa gần như sum = (float)(sum + step).
```

Quy tắc gán kết hợp đặc biệt này không bảo đảm kết quả chính xác. Tránh dùng nó để che khuất một quyết định thu hẹp trong phép tính tài chính hoặc thuật toán nhạy với sai số.

## 3. Java làm gì khi chuyển `double` sang `float`?

Theo quy tắc chuyển kiểu chấm động, Java chuyển một giá trị `double` về biểu diễn `float`:

1. Nếu là **NaN**, kết quả vẫn là `float` NaN.
2. Nếu là **+Infinity** hoặc **-Infinity**, kết quả giữ vô cực tương ứng.
3. Nếu là **+0.0** hoặc **-0.0**, kết quả giữ dấu của zero.
4. Nếu là giá trị **hữu hạn**, Java làm tròn về số `float` biểu diễn được gần nhất, theo *round-to-nearest, ties-to-even*; nếu vượt ngưỡng phía lớn, kết quả có thể là vô cực; nếu quá gần 0, có thể là số subnormal hoặc zero có dấu.

Phép thu hẹp số thực thông thường **không ném `ArithmeticException` vì tràn hoặc mất độ chính xác**. Kiểu đích có các giá trị `Infinity` và `0.0` để nhận kết quả làm tròn tương ứng.

Với giá trị nằm trong miền bình thường, mất chính xác có nghĩa hai giá trị `double` khác nhau có thể cùng chuyển thành một `float`. Điều này **không phải lỗi của cú pháp cast**; đó là giới hạn của biểu diễn 32 bit.

### Tại sao một số giá trị chuyển vẫn chính xác?

Những số như `0.5`, `1.25`, `12.5` có khai triển nhị phân hữu hạn ngắn, nên `float` có thể biểu diễn chúng chính xác. Nhưng `0.1` có khai triển nhị phân vô hạn tuần hoàn; cả `double` lẫn `float` chỉ lưu được giá trị xấp xỉ.

Còn các số nguyên: `float` với significand 24 bit biểu diễn **mọi số nguyên** có độ lớn tới `2^24 = 16_777_216`, nhưng không biểu diễn được **mọi số nguyên** lớn hơn mốc này. Một số nguyên lớn hơn vẫn có thể biểu diễn chính xác nếu phù hợp khoảng cách giữa các số `float` liền kề.

## 4. Mất chính xác dễ nhận thấy: `0.1` và 16.777.217

### 4.1. `0.1`: kết quả in không thể hiện hết bit

```java
double source = 0.1d;
float smaller = (float) source;

System.out.println(source);           // 0.1
System.out.println(smaller);          // 0.1
System.out.println((double) smaller); // 0.10000000149011612
```

`System.out.println(float)` dùng cách biểu diễn thập phân có thể chuyển ngược về đúng giá trị `float`. Dòng `0.1` **không chứng minh** biến đang lưu đúng 0.1 thập phân. Khi chuyển `smaller` trở lại `double`, mọi bit của **giá trị `float` hiện tại** được giữ chính xác trong `double`, nên sự khác biệt thành dễ thấy.

- `source`: xấp xỉ 0.1 theo binary64.
- `smaller`: xấp xỉ 0.1 theo binary32.
- `(double) smaller`: diễn đạt chính xác giá trị binary32 đó trong binary64.

**Ép ngược `float -> double` không khôi phục các bit đã mất từ `source`.** Đây là sự khác biệt giữa “mở rộng chỗ chứa” và “phục hồi thông tin”.

### 4.2. Số nguyên 16.777.217 mất một đơn vị

```java
double original = 16_777_217.0;
float rounded = (float) original;

System.out.println(original); // 1.6777217E7
System.out.println(rounded);  // 1.6777216E7
```

`double` có đủ significand để biểu diễn chính xác 16.777.217. `float` ở vùng giá trị này có khoảng cách 2 giữa các số biểu diễn liền nhau; 16.777.217 nằm giữa 16.777.216 và 16.777.218. Với *ties-to-even*, kết quả được chọn là **16.777.216**.

Điểm cốt lõi không phải cứ vượt mốc 16.777.216 là mọi giá trị sai, mà là **độ phân giải của `float` thưa dần khi độ lớn tăng**.

## 5. Khái niệm ULP và độ phân giải tại một độ lớn

*ULP* (*unit in the last place*) mô tả khoảng cách giữa các số biểu diễn liên tiếp trong một vùng. Java có `Math.ulp(float)` và `Math.ulp(double)`.

```java
System.out.println(Math.ulp(1.0f)); // 1.1920929E-7
System.out.println(Math.ulp(1.0d)); // 2.220446049250313E-16
```

Gần 1.0, bước lượng tử của `float` vào khoảng 0.000000119, còn `double` nhỏ hơn nhiều. Khi giá trị lớn, ULP lớn dần; không có một con số “độ chính xác tuyệt đối” cố định cho mọi vùng.

Ví dụ:

```java
float a = 16_777_216f;
float b = a + 1.0f;
System.out.println(a == b); // true: cộng 1 không đổi được giá trị float tại đây.
```

Đây không phải lỗi toán tử `+`. Kết quả toán học nằm giữa hai số `float` biểu diễn được và làm tròn về một trong hai. Với phép tích lũy số lượng lớn, nhiều phép làm tròn có thể làm sai số tăng hoặc phụ thuộc thứ tự cộng.

### Bao nhiêu chữ số thập phân có thể tin tưởng?

Cụm “`float` khoảng 7 chữ số, `double` khoảng 15 chữ số” chỉ là **ước lượng độ chính xác**, không phải cam kết rằng *bất kỳ* 7 chữ số sau dấu phẩy đều đúng. Số chữ số **có nghĩa** khác với số chữ số **sau dấu thập phân**; sai số phụ thuộc độ lớn, phép tính và khoảng cách giữa các số biểu diễn.

Nếu dữ liệu cần phân biệt hai giá trị cách nhau 0.001 ở vùng hàng tỷ, `float` thường không phù hợp. Hãy tính cận trên của dữ liệu và độ phân giải cần thiết theo đơn vị thực tế.

## 6. Vượt miền: vô cực, subnormal và zero

Độ chính xác không phải rủi ro duy nhất. `float` có miền số mũ hẹp hơn `double`.

### 6.1. Overflow thành vô cực

```java
double huge = 1.0e40;       // double hữu hạn.
float f = (float) huge;     // +Infinity.

System.out.println(f);                    // Infinity
System.out.println(Float.isInfinite(f));  // true
```

`1.0e40` nhỏ hơn `Double.MAX_VALUE` nhưng lớn hơn rất nhiều so với `Float.MAX_VALUE`. Cast không tự động kẹp về `Float.MAX_VALUE` và không ném exception.

Để kiểm tra một kết quả có là số hữu hạn hay không, dùng `Float.isFinite(f)`; muốn biết riêng vô cực dùng `Float.isInfinite(f)`.

### 6.2. Underflow: mất thành 0 hoặc số subnormal

```java
double tiny = 1.0e-50;
float zero = (float) tiny;
System.out.println(zero); // 0.0

double small = 1.0e-40;
float subnormal = (float) small;
System.out.println(subnormal); // 1.0E-40
```

`1.0e-50` quá gần 0 để có `float` khác 0 theo quy tắc làm tròn, nên kết quả là `0.0f`. `1.0e-40` vẫn có thể thành một giá trị `float` **subnormal** (nhỏ hơn `Float.MIN_NORMAL` nhưng khác 0), song thường mất nhiều chữ số chính xác tương đối.

Nói cách khác, underflow không nhất thiết luôn cho 0 ngay: có một vùng subnormal, đổi lại độ chính xác tương đối giảm dần khi tiến tới 0.

### 6.3. NaN và hai số 0 có dấu

```java
float notANumber = (float) Double.NaN;
System.out.println(Float.isNaN(notANumber)); // true

float negativeZero = (float) -0.0d;
System.out.println(1.0f / negativeZero); // -Infinity
```

`0.0f == -0.0f` là `true` theo phép so sánh số học, nhưng dấu 0 có thể ảnh hưởng phép chia và một số API bit-level. `NaN` không so sánh bằng chính nó theo `==`; cần dùng `Float.isNaN` thay vì `value == Float.NaN`.

## 7. Mất thông tin có thể lan qua biểu thức hỗn hợp

Java thực hiện *binary numeric promotion* khi hai toán hạng số học có kiểu khác nhau: nếu có `double`, biểu thức thường được tính bằng `double`. Nhưng **chuyển sang `double` sau khi `float` đã mất thông tin không khôi phục giá trị gốc**.

```java
float f = (float) 0.1d;
double result = f + 0.2d;
System.out.println(result); // 0.30000000149011613
```

Ở phép `+` trên, `f` được mở rộng sang `double` rồi cộng với `0.2d`. Giá trị của `f` vẫn là xấp xỉ binary32 của 0.1. Nếu cần chuỗi tính toán dùng `double` từ đầu, tránh ép xuống `float` ở bước trung gian.

### Khi gọi phương thức và API

```java
static float narrowMeasurement(double input) {
    return (float) input; // Quyết định có thể mất dữ liệu được ghi rõ.
}
```

Đây là phương thức minh họa, cần đặt trong một lớp. Khi API bên ngoài yêu cầu `float` (ví dụ buffer đồ họa, mạng hoặc thư viện xử lý dữ liệu), hãy đặt cast tại **ranh giới chuyển giao dữ liệu** và kiểm tra giới hạn ở đó. Tránh đổi toàn bộ nội bộ ứng dụng sang `float` chỉ vì lớp lưu trữ đích dùng `float`.

Đặc biệt với `float[]`, việc lưu một chuỗi `double` đã chuyển hẹp đồng nghĩa toàn bộ mẫu trong mảng bị giới hạn bởi độ chính xác binary32, kể cả khi sau đó đọc lên dưới dạng `double`.

## 8. Làm sao biết việc thu hẹp có “an toàn” không?

Từ “an toàn” có thể mang ba nghĩa khác nhau:

1. **Không thành NaN/vô cực hoặc 0 bất ngờ**: yêu cầu giới hạn miền và giá trị hữu hạn.
2. **Giữ chính xác cùng giá trị số học**: kiểm tra chuyển qua `float` rồi mở rộng lại có bằng giá trị ban đầu hay không, với lưu ý xử lý đặc biệt NaN và zero có dấu.
3. **Sai số nằm trong mức chấp nhận của nghiệp vụ**: cần dung sai tuyệt đối/tương đối, đơn vị dữ liệu và kiểm thử mô hình; đây là tiêu chí thực tế của nhiều thuật toán số.

### 8.1. Kiểm tra giá trị hữu hạn và trường hợp đổi thành vô cực

```java
static float requireFiniteFloat(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Input must be finite");
    }
    float narrowed = (float) value;
    if (!Float.isFinite(narrowed)) {
        throw new IllegalArgumentException("Outside finite float range");
    }
    return narrowed;
}
```

Phương thức này loại **đầu vào không hữu hạn** và kết quả **overflow thành Infinity**. Nó **không** bảo đảm giữ chính xác tất cả bit và **không** loại underflow về 0 hoặc làm tròn.

Nếu không muốn từ chối `NaN` hoặc vô cực theo nghiệp vụ, cần xác định hợp đồng cho chúng thay vì mặc định “mọi NaN đều sai”.

### 8.2. Kiểm tra có mất giá trị số học hay không

```java
static float requireExactFiniteFloat(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Input must be finite");
    }
    float narrowed = (float) value;
    if (!Float.isFinite(narrowed) || (double) narrowed != value) {
        throw new IllegalArgumentException("Not exactly representable as float");
    }
    return narrowed;
}
```

Với các giá trị **hữu hạn** mà sự bằng nhau số học là tiêu chí, so sánh round-trip như trên kiểm tra được việc làm tròn có đổi giá trị không. Ví dụ:

- `1.25d` chuyển chính xác sang `float`.
- `0.1d` không giữ được nguyên giá trị `double` khi chuyển.
- `16_777_217d` cũng không giữ được.
- `1.0e40` thành vô cực và bị từ chối.
- `1.0e-50` thành 0, khác giá trị ban đầu và bị từ chối.

Điều kiện `==` trên số hữu hạn chấp nhận cả hai trường hợp zero cùng giá trị số học: `+0.0 == -0.0`. Nếu hợp đồng cần phân biệt **bit dấu zero**, phải kiểm tra thêm với `Double.doubleToRawLongBits`/`Float.floatToRawIntBits` sau khi xác định cách đối chiếu; không dùng chỉ `==` để kiểm soát điều này.

### 8.3. Chấp nhận sai số theo yêu cầu thực tế

Không phải ứng dụng nào cũng cần giữ nguyên mọi giá trị `double`. Với dữ liệu tọa độ hiển thị, cảm biến hoặc ảnh, sai số nhỏ có thể chấp nhận; với tài chính, kiểm toán hay dữ liệu định danh, làm tròn như vậy có thể không phù hợp.

Một quy trình thực tế:

1. Định nghĩa miền giá trị (ví dụ `-1_000..1_000`) và độ phân giải cần thiết (ví dụ nhỏ hơn 0,0001 đơn vị).
2. Thử cast tại các điểm biên và giá trị đại diện.
3. Tính sai số `Math.abs(original - (double) narrowed)` khi cả hai hữu hạn, rồi so với ngân sách sai số do nghiệp vụ quy định.
4. Nếu gần 0 hoặc trên nhiều bậc độ lớn, cân nhắc tiêu chí sai số tuyệt đối kết hợp tương đối, tránh chia cho 0.
5. Kiểm thử cả các chuỗi phép toán thực tế, không chỉ một cast lẻ.

Không đặt một epsilon chung cho mọi bài toán. `Math.ulp` giúp ước lượng bước lượng tử theo độ lớn, nhưng **ngưỡng chấp nhận cuối cùng phải xuất phát từ nghiệp vụ**.

## 9. Chuyển `String` và ghi/đọc dữ liệu: đừng nhầm với cast

`Double.parseDouble("0.1")` trả giá trị binary64 gần 0.1; `Float.parseFloat("0.1")` trả giá trị binary32 gần 0.1. Cả hai đều parse văn bản và chọn miền biểu diễn của kiểu đích.

```java
double d = Double.parseDouble("0.1");
float f = Float.parseFloat("0.1");

System.out.println(d); // 0.1
System.out.println(f); // 0.1
System.out.println((double) f); // 0.10000000149011612
```

Chuỗi hiển thị `"0.1"` là **biểu diễn thập phân** được tạo ra để việc chuyển ngược về kiểu tương ứng nhận lại cùng một giá trị, không nói rằng hai kiểu lưu cùng một số nhị phân.

Khi cần giữ chính xác thập phân nhập từ người dùng (ví dụ tiền), có thể dùng:

```java
java.math.BigDecimal price = new java.math.BigDecimal("0.1");
```

`BigDecimal` là mô hình số thập phân chính xác ở mức giá trị được khai báo, không phải bản “`float` nhiều bit hơn”. Dùng `BigDecimal.valueOf(double)` có quy tắc chuyển từ biểu diễn thập phân của `double`, nhưng nó cũng không thể phục hồi dữ liệu đã từng bị ép thành `float`.

### `float` không đồng nghĩa với “ít bộ nhớ mà luôn đủ”

Một mảng `float[]` có phần tử 32 bit, trong khi `double[]` có phần tử 64 bit. Điều này có thể hữu ích với tập dữ liệu rất lớn, bộ đệm đồ họa hoặc giao thức lưu trữ bắt buộc binary32. Tuy nhiên tổng bộ nhớ còn có overhead, căn chỉnh và cấu trúc dữ liệu. Tiết kiệm dung lượng là lựa chọn kỹ thuật phải cân bằng với sai số, không phải lý do tự động thu hẹp mọi phép tính.

## 10. Chương trình Java 17+ chạy độc lập

Tạo tệp `NarrowingDoubleToFloatDemo.java`:

```java
public class NarrowingDoubleToFloatDemo {
    public static void main(String[] args) {
        double d = 0.1d;
        float f = (float) d;
        double widened = f;

        System.out.println("Original double: " + d);
        System.out.println("Narrowed float: " + f);
        System.out.println("Widened again: " + widened);
        System.out.println("Round trip equal? " + (d == widened));

        double largeInteger = 16_777_217.0;
        float roundedInteger = (float) largeInteger;
        System.out.println("Integer original: " + largeInteger);
        System.out.println("Integer as float: " + roundedInteger);

        System.out.println("Float spacing near 1: " + Math.ulp(1.0f));
        System.out.println("Double spacing near 1: " + Math.ulp(1.0d));

        System.out.println("Overflow: " + (float) 1.0e40);
        System.out.println("Underflow: " + (float) 1.0e-50);
        float subnormal = (float) 1.0e-40;
        System.out.println("Subnormal: " + subnormal);

        float negativeZero = (float) -0.0d;
        System.out.println("Negative zero sign: " + (1.0f / negativeZero));
        System.out.println("NaN stays NaN? " + Float.isNaN((float) Double.NaN));

        double mixed = f + 0.2d;
        System.out.println("Mixed expression type double value: " + mixed);
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 NarrowingDoubleToFloatDemo.java
java NarrowingDoubleToFloatDemo
```

Stdout:

```text
Original double: 0.1
Narrowed float: 0.1
Widened again: 0.10000000149011612
Round trip equal? false
Integer original: 1.6777217E7
Integer as float: 1.6777216E7
Float spacing near 1: 1.1920929E-7
Double spacing near 1: 2.220446049250313E-16
Overflow: Infinity
Underflow: 0.0
Subnormal: 1.0E-40
Negative zero sign: -Infinity
NaN stays NaN? true
Mixed expression type double value: 0.30000000149011613
```

Ví dụ thể hiện ba hiện tượng độc lập: **giảm độ chính xác** (`0.1` và số nguyên 16.777.217), **thu hẹp miền** (vô cực, zero và subnormal), cùng **quy tắc lan truyền kiểu** (phép cộng với `double` vẫn giữ xấp xỉ `float` đã có). Có thể thử thêm `1.25d` để thấy một trường hợp chuyển chính xác.

## 11. Các lỗi phổ biến và cách tránh

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Cho rằng `(float) d` chỉ “đổi tên kiểu” | `float` chỉ có 24 bit significand | Xác định sai số cho phép; giữ `double` nếu cần |
| Thấy hai biến đều in `0.1` nên kết luận bằng nhau | `Float.toString` và `Double.toString` chọn chuỗi biểu diễn theo kiểu | Kiểm tra giá trị mở rộng lại, bit hoặc sai số đúng ngữ cảnh |
| Ép lại `(double)(float)d` rồi cho rằng đã phục hồi dữ liệu | Mở rộng không khôi phục bit đã mất | Giữ nguồn `double` nếu còn cần |
| Cho rằng cast quá lớn sẽ ném exception | Giá trị hữu hạn lớn có thể thành `Infinity` | Kiểm tra `Float.isFinite`, giới hạn miền |
| Cho rằng cast quá nhỏ giữ nguyên khác 0 | Có thể thành subnormal hoặc `0.0` | Kiểm tra ngưỡng nhỏ nhất và sai số |
| Dùng `float` cho số đếm lớn cần biểu diễn đúng từng đơn vị | Không phải mọi số nguyên trên `2^24` còn chính xác | Dùng `int`/`long` cho số đếm nguyên |
| Dùng `==` để so sánh kết quả thuật toán chấm động với kỳ vọng toán học | Làm tròn khiến các đường tính khác nhau | Chọn tiêu chí dung sai theo đơn vị và miền |
| Chuyển `double` xuống `float` trước phép tính rồi mở rộng ở cuối | Sai số đã xuất hiện ở bước trung gian | Tính bằng `double` trong suốt pipeline khi cần |
| Tưởng `float` đủ cho tiền vì “chỉ hai chữ số lẻ” | Decimal như 0.1 không biểu diễn chính xác trong binary32 | Dùng `BigDecimal` hoặc đơn vị nguyên (xu) khi phù hợp |
| Không để ý `+=` nhận `double` với biến `float` | Compound assignment thực hiện chuyển hẹp ngầm | Tách phép tính và cast tường minh |
| Dùng `Float.MIN_VALUE` như giá trị âm nhỏ nhất | Đây là số dương subnormal nhỏ nhất | Phân biệt `MIN_VALUE`, `MIN_NORMAL`, `MAX_VALUE` |

## 12. Câu hỏi tự kiểm tra

1. Vì sao `float f = d;` không biên dịch với `d` kiểu `double`, còn `float f = (float) d;` thì được?
2. `(double) (float) 0.1d` có bằng `0.1d` không? Tại sao cả hai có thể được in ra gần giống nhau?
3. Tại sao `16_777_217.0d` không giữ nguyên sau khi ép sang `float`, trong khi `16_777_216.0d` giữ nguyên?
4. Sự khác nhau giữa **độ chính xác (precision)** và **miền số mũ (range)** thể hiện ra sao khi ép `1e40` và `1e-50` sang `float`?
5. `Float.MIN_VALUE` biểu diễn điều gì? Số `float` subnormal có giống zero không?
6. Khi nào phép kiểm tra round-trip `(double)(float) d == d` hữu ích, và tại sao phải xử lý riêng NaN hoặc dấu của zero nếu hợp đồng yêu cầu?
7. Vì sao kết quả `float f = (float) 0.1d; double x = f + 0.2d;` vẫn chứa sai số từ `f` dù biểu thức cộng có kiểu `double`?
8. Ứng dụng đo đạc chấp nhận sai số dưới 0,01 đơn vị. Cần kiểm tra những yếu tố nào trước khi lưu kết quả `double` vào `float[]`?

### Ghi nhớ

**Ép `double` sang `float` là một phép làm tròn sang tập giá trị biểu diễn được của binary32**, không phải chuyển đổi đảm bảo giữ nguyên giá trị. Cast có thể khiến kết quả **mất độ chính xác, thành ±Infinity hoặc ±0.0, hoặc nằm trong vùng subnormal** mà không ném ngoại lệ. Hãy giữ `double` cho đến ranh giới thực sự phải lưu/truyền `float`, kiểm tra miền và sai số theo nghiệp vụ, và không kỳ vọng cast ngược lên `double` sẽ lấy lại thông tin đã mất.