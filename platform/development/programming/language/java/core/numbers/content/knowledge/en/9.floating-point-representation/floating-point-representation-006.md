# Normal, subnormal và gradual underflow trong Java

## 1. Mục tiêu của bài học

Trong Java, **float** và **double** biểu diễn số dấu phẩy động nhị phân với độ rộng cố định. Khi một số rất gần 0, cách biểu diễn của nó có thể thay đổi từ **normal** (số chuẩn hóa) sang **subnormal** (số dưới chuẩn), rồi cuối cùng thành **+0.0** hoặc **-0.0** nếu kết quả nhỏ tới mức không còn số khác 0 biểu diễn được.

**Gradual underflow** là cơ chế cho phép các kết quả nhỏ tiếp tục tồn tại dưới dạng subnormal thay vì lập tức bị thay bằng 0 tại ngưỡng nhỏ nhất của số normal. Đây là một phần quan trọng của ngữ nghĩa dấu phẩy động trong Java.

Sau bài này, bạn cần có khả năng:

- Nhận biết normal, subnormal, zero, infinity và NaN từ các trường bit của float/double.
- Giải thích **hidden leading bit** là 1 ở số normal và 0 ở số subnormal.
- Phân biệt **Float.MIN_NORMAL** với **Float.MIN_VALUE**, và tương tự ở double.
- Tính ngưỡng nhỏ nhất, khoảng cách giữa các số subnormal, cũng như thời điểm làm tròn thành 0.
- Hiểu gradual underflow giữ được gì, mất độ chính xác tương đối ở đâu và tại sao kết quả Java không tự động “flush to zero”.
- Đọc mẫu bit và tái hiện các tình huống bằng Java 17+.

## 2. Cấu trúc IEEE 754 của float và double

Java dùng hai định dạng nhị phân thông dụng:

| Thuộc tính | **float** (binary32) | **double** (binary64) |
| --- | ---: | ---: |
| Tổng số bit | 32 | 64 |
| Bit dấu | 1 | 1 |
| Bit số mũ lưu trữ | 8 | 11 |
| Bit phân số lưu trữ | 23 | 52 |
| Độ chính xác của significand ở miền normal | 24 bit | 53 bit |
| Độ lệch số mũ (bias) | 127 | 1023 |
| Số mũ nhỏ nhất của normal | −126 | −1022 |
| Số mũ lớn nhất của normal | +127 | +1023 |

Một mẫu bit float có bố cục:

~~~text
float (32 bit)
+---+----------+-------------------------+
| s | exponent |         fraction        |
| 1 |  8 bit   |          23 bit         |
+---+----------+-------------------------+
~~~

Một mẫu bit double:

~~~text
double (64 bit)
+---+-------------+----------------------------------------------+
| s |  exponent   |                   fraction                   |
| 1 |   11 bit    |                     52 bit                   |
+---+-------------+----------------------------------------------+
~~~

Gọi **s** là bit dấu, **E** là số nguyên không dấu lưu trong trường exponent, và **F** là số nguyên không dấu lưu trong trường fraction. Dấu của giá trị do **(−1)^s** quyết định. **E** là trường bit được mã hóa và không phải luôn là số mũ thực tế.

Những trường hợp đặc biệt phụ thuộc vào mẫu của exponent:

| Trường exponent | Fraction | Loại giá trị |
| --- | --- | --- |
| Khác 0 và chưa phải toàn bit 1 | Bất kỳ | **Normal** |
| Toàn bit 0 | Khác 0 | **Subnormal** |
| Toàn bit 0 | Bằng 0 | **+0.0** hoặc **−0.0** |
| Toàn bit 1 | Bằng 0 | **+Infinity** hoặc **−Infinity** |
| Toàn bit 1 | Khác 0 | **NaN** |

Đừng nhầm **subnormal** với NaN, infinity hoặc zero. Subnormal là **số hữu hạn khác 0**, có thể tham gia cộng, trừ, nhân, chia thông thường. Dấu âm không thay đổi quy tắc phân loại.

## 3. Normal: số chuẩn hóa và bit 1 ẩn

Đối với float, khi **1 ≤ E ≤ 254**, số normal có giá trị:

\[
(-1)^s \times \left(1+\frac{F}{2^{23}}\right)\times 2^{E-127}
\]

Đối với double, khi **1 ≤ E ≤ 2046**:

\[
(-1)^s \times \left(1+\frac{F}{2^{52}}\right)\times 2^{E-1023}
\]

Phần **1 + F/2^n** có một bit **1** ở đầu trong dạng nhị phân của significand. Bit 1 này **không cần lưu trữ trong trường fraction**, vì biết chắc nó tồn tại đối với mọi số normal. Nó thường được gọi là **implicit leading 1** hoặc **hidden bit**.

Ví dụ số float **1.0f**:

~~~text
Bit dấu:      0
Exponent E:   01111111 (127)
Fraction F:   00000000000000000000000 (0)

Giá trị: (+1) × (1 + 0/2^23) × 2^(127−127) = 1
Mẫu 32 bit: 0x3F800000
~~~

Trong miền normal, các số không cách đều nhau trên toàn trục số. Với cùng số mũ thực tế, các số kế tiếp nhau có độ chênh cố định, nhưng khi số mũ thay đổi thì khoảng cách cũng thay đổi theo lũy thừa của 2. Nhờ vậy, số normal duy trì một mức **độ chính xác tương đối** gần như ổn định trong miền biểu diễn.

### Ranh giới nhỏ nhất của số normal

Số normal dương nhỏ nhất xuất hiện khi E = 1 và F = 0:

| Hằng Java | Công thức | Mẫu bit |
| --- | --- | --- |
| **Float.MIN_NORMAL** | **2^−126** ≈ **1.17549435 × 10^−38** | **0x00800000** |
| **Double.MIN_NORMAL** | **2^−1022** ≈ **2.2250738585072014 × 10^−308** | **0x0010000000000000** |

Nếu định dạng chỉ có số normal và zero, mọi kết quả dương nhỏ hơn ngưỡng này có nguy cơ phải nhảy mạnh xuống 0. **Subnormal** tạo ra các mức trung gian giữa zero và normal nhỏ nhất.

## 4. Subnormal: bỏ bit 1 ẩn và dùng số mũ cố định

Với **E = 0 và F ≠ 0**, bit đầu của significand là **0**, thay vì 1. Giá trị float lúc này là:

\[
(-1)^s \times \left(\frac{F}{2^{23}}\right)\times 2^{-126}
= (-1)^s \times F \times 2^{-149}
\]

Với double:

\[
(-1)^s \times \left(\frac{F}{2^{52}}\right)\times 2^{-1022}
= (-1)^s \times F \times 2^{-1074}
\]

Điều cần nhớ là **E = 0 không có nghĩa dùng số mũ −127 ở float hay −1023 ở double**. Trong công thức subnormal, số mũ nền vẫn là **−126** với float và **−1022** với double. Sự lựa chọn này làm cho bước khoảng cách nối tiếp từ subnormal lớn nhất đến normal nhỏ nhất **không bị gián đoạn**.

Minh họa significand với một số float:

~~~text
Normal nhỏ nhất:
1.00000000000000000000000 × 2^-126
^ bit 1 ẩn

Subnormal lớn nhất:
0.11111111111111111111111 × 2^-126
^ bit 0 ẩn

Subnormal nhỏ nhất:
0.00000000000000000000001 × 2^-126
~~~

Vì subnormal không có bit 1 ẩn, khi độ lớn giảm, số bit có nghĩa thực sự giảm theo. Điều này tạo ra phần “gradual”: ta vẫn biểu diễn được những số khác 0, nhưng độ chính xác **tương đối** suy giảm gần 0.

### Hằng MIN_VALUE dễ gây hiểu nhầm

| Hằng Java | Nghĩa chính xác | Giá trị xấp xỉ | Mẫu bit |
| --- | --- | --- | --- |
| **Float.MIN_VALUE** | Số **float dương khác 0 nhỏ nhất** | 1.40129846 × 10^−45 | **0x00000001** |
| **Double.MIN_VALUE** | Số **double dương khác 0 nhỏ nhất** | 4.9406564584124654 × 10^−324 | **0x0000000000000001** |

Cả hai **MIN_VALUE đều là subnormal**, không phải số âm nhất. Số âm hữu hạn có độ lớn lớn nhất tương ứng với **−Float.MAX_VALUE** hoặc **−Double.MAX_VALUE**.

Giá trị subnormal dương lớn nhất có F toàn bit 1:

| Kiểu | Công thức | Mẫu bit |
| --- | --- | --- |
| float | **2^−126 − 2^−149** | **0x007FFFFF** |
| double | **2^−1022 − 2^−1074** | **0x000FFFFFFFFFFFFF** |

Có thể lấy số subnormal lớn nhất bằng **Math.nextDown(Float.MIN_NORMAL)** hoặc **Math.nextDown(Double.MIN_NORMAL)** mà không cần tự tính.

## 5. Gradual underflow: từ normal xuống subnormal rồi mới tới zero

**Underflow** là tình huống phép tính dấu phẩy động tạo ra kết quả có độ lớn quá nhỏ so với miền normal. Java áp dụng **gradual underflow**: khi kết quả có thể biểu diễn hoặc làm tròn thành subnormal khác 0, số đó vẫn được giữ.

Hãy nhìn vào một phép chia cho 2 trong float:

~~~text
2^-125                     normal
2^-126                     normal nhỏ nhất = Float.MIN_NORMAL
2^-127                     subnormal, biểu diễn chính xác
2^-128                     subnormal, biểu diễn chính xác
...
2^-148                     subnormal, biểu diễn chính xác
2^-149                     subnormal nhỏ nhất = Float.MIN_VALUE
2^-150                     nằm giữa 0 và Float.MIN_VALUE; làm tròn thành +0.0
~~~

Từ **2^−126** đến **2^−149**, các phép chia đúng cho 2 được minh họa vẫn cho số khác 0 và biểu diễn chính xác. Khi tới **2^−150**, kết quả đúng toán học nằm đúng giữa 0 và **2^−149**; quy tắc làm tròn **nearest, ties to even** chọn **+0.0** vì bit cuối được chọn là bit 0.

Nếu hệ thống dùng cơ chế **flush-to-zero (FTZ)**, một kết quả nằm trong miền subnormal có thể bị thay ngay thành 0. Đây không phải ngữ nghĩa của toán tử dấu phẩy động Java 17+: Java yêu cầu hỗ trợ subnormal và gradual underflow.

### Hình dung “bậc thang” sát zero

~~~text
float dương, không theo tỉ lệ hình học:

0        1·u       2·u       ...   (2^23−1)·u      2^23·u
|---------|---------|-------------------|-----------------|
zero   minSub      subnormal           maxSub        minNormal
                                             
u = 2^-149 = Float.MIN_VALUE
minNormal = 2^23 · u = 2^-126
~~~

Các số subnormal dương float chính xác là **k × 2^−149** với k nguyên từ **1** đến **2^23 − 1**. Vì thế chúng **cách nhau một lượng tuyệt đối cố định u**. Bước từ subnormal lớn nhất đến normal nhỏ nhất cũng đúng bằng **u**, tạo liên tục về *khoảng cách biểu diễn* ở ranh giới. Điều này không có nghĩa các số thực nằm giữa hai giá trị float cũng biểu diễn được; mọi kết quả vẫn phải làm tròn về giá trị khả dụng.

Tương tự, các subnormal dương double có bước cố định **2^−1074**.

## 6. Mất dần độ chính xác tương đối

Trong miền normal, significand chứa **24 bit có nghĩa với float** và **53 bit với double** (gồm bit 1 ẩn). Khi sang subnormal, bit đầu bắt buộc là 0, phần có nghĩa hiệu dụng ít dần khi giá trị tiến về zero.

Hai ý tưởng về sai số cần phân biệt:

- **Độ phân giải tuyệt đối (absolute spacing)**: khoảng cách giữa hai giá trị biểu diễn được gần nhau. Với mọi float subnormal dương, đó là **2^−149**.
- **Độ phân giải tương đối (relative spacing)**: tỉ lệ của khoảng cách trên so với độ lớn số đang xét. Tỉ lệ này tăng mạnh khi số tiến về zero.

Ví dụ tại **Float.MIN_NORMAL = 2^−126**:

~~~text
Bước lưới             = 2^-149
Bước / giá trị        = 2^-149 / 2^-126 = 2^-23
                      ≈ 1.1920929 × 10^-7
~~~

Nhưng tại **Float.MIN_VALUE = 2^−149**, bước lưới lại **bằng chính giá trị đó**. Số rất nhỏ có thể có sai số tương đối lớn khi nhân, chia, cộng hoặc trừ. Đó là đánh đổi có chủ đích của gradual underflow: bảo toàn được nhiều giá trị rất nhỏ, nhưng không bảo toàn được độ chính xác tương đối như ở miền normal.

**Subnormal không mặc nhiên là kết quả sai.** Ví dụ phép tính **Float.MIN_NORMAL / 2** tạo ra một subnormal **chính xác**. Ngược lại, một phép tính dưới ngưỡng có thể phải làm tròn; tình trạng “kết quả là subnormal” và “kết quả bị làm tròn không chính xác” không đồng nghĩa nhau. Theo IEEE 754, khái niệm cờ *underflow* còn liên quan điều kiện tininess/inexact; Java không cung cấp một API thông thường để đọc cờ trạng thái phần cứng đó.

## 7. Làm tròn khi độ lớn nhỏ hơn subnormal nhỏ nhất

Java 17+ áp dụng ngữ nghĩa dấu phẩy động strict, phù hợp với quy tắc làm tròn của các toán tử tương ứng. Đối với cộng/trừ/nhân/chia dấu phẩy động thông thường, kết quả hữu hạn không biểu diễn chính xác sẽ được làm tròn về giá trị gần nhất; khi ở đúng trung điểm, chọn giá trị có bit thấp nhất chẵn (*ties to even*).

Xét float dương:

~~~text
0.0f                   = 0
Float.MIN_VALUE        = 2^-149
Float.MIN_VALUE / 2    = 2^-150
~~~

**2^−150** nằm đúng giữa 0 và **2^−149**, nên làm tròn thành **+0.0f**. Với số âm, **−2^−150** làm tròn thành **−0.0f**: bit dấu vẫn có ý nghĩa trong biểu diễn mặc dù hai số zero so sánh bằng nhau qua **==**.

Một trường hợp khác:

~~~text
Float.MIN_VALUE * 1.5 = 1.5 × 2^-149
~~~

Giá trị toán học nằm đúng giữa **1 × 2^−149** và **2 × 2^−149**; ties-to-even chọn **2 × 2^−149**, nên kết quả có trường fraction là **2**, tương ứng mẫu **0x00000002**.

**Không có ArithmeticException** khi kết quả phép toán float/double bị làm tròn thành 0 do underflow. Các phép toán này trả về giá trị floating-point thích hợp.

### Signed zero khác nhau khi quan sát bằng bit

~~~java
float positiveZero = Float.MIN_VALUE / 2.0f;
float negativeZero = -Float.MIN_VALUE / 2.0f;

System.out.println(positiveZero == negativeZero); // true
System.out.println(1.0f / positiveZero);            // Infinity
System.out.println(1.0f / negativeZero);            // -Infinity
~~~

Đoạn mã trên minh họa, không phải chương trình độc lập. Dùng **Float.floatToRawIntBits** để quan sát bit dấu chính xác; so sánh **==** không phân biệt +0.0 với −0.0.

## 8. Ví dụ Java 17+ kiểm tra các ranh giới bằng bit

Tạo tệp **SubnormalDemo.java** với toàn bộ mã sau:

~~~java
public class SubnormalDemo {
    static String bits(float value) {
        return "0x%08X".formatted(Float.floatToRawIntBits(value));
    }

    static String bits(double value) {
        return "0x%016X".formatted(Double.doubleToRawLongBits(value));
    }

    static String category(float value) {
        int raw = Float.floatToRawIntBits(value);
        int exponent = (raw >>> 23) & 0xFF;
        int fraction = raw & 0x7FFFFF;

        if (exponent == 0) {
            return fraction == 0 ? "zero" : "subnormal";
        }
        if (exponent == 0xFF) {
            return fraction == 0 ? "infinity" : "NaN";
        }
        return "normal";
    }

    public static void main(String[] args) {
        float minNormal = Float.MIN_NORMAL;
        float minSub = Float.MIN_VALUE;
        float maxSub = Math.nextDown(minNormal);

        System.out.println("float minNormal: " + bits(minNormal)
                + " / " + category(minNormal));
        System.out.println("float maxSub: " + bits(maxSub)
                + " / " + category(maxSub));
        System.out.println("float minSub: " + bits(minSub)
                + " / " + category(minSub));
        System.out.println("float zero: " + bits(0.0f)
                + " / " + category(0.0f));
        System.out.println("float -zero: " + bits(-0.0f)
                + " / " + category(-0.0f));

        System.out.println("float minNormal hex: "
                + Float.toHexString(minNormal));
        System.out.println("float minSub hex: "
                + Float.toHexString(minSub));

        System.out.println("float minNormal / 2: " + bits(minNormal / 2.0f));
        System.out.println("float maxSub + minSub: " + bits(maxSub + minSub));
        System.out.println("float minSub / 2: " + bits(minSub / 2.0f));
        System.out.println("float -minSub / 2: " + bits(-minSub / 2.0f));
        System.out.println("float minSub * 1.5: " + bits(minSub * 1.5f));

        double minNormalD = Double.MIN_NORMAL;
        double minSubD = Double.MIN_VALUE;

        System.out.println("double minNormal: " + bits(minNormalD));
        System.out.println("double maxSub: "
                + bits(Math.nextDown(minNormalD)));
        System.out.println("double minSub: " + bits(minSubD));
        System.out.println("double minNormal / 2: "
                + bits(minNormalD / 2.0));
        System.out.println("double minSub / 2: " + bits(minSubD / 2.0));
        System.out.println("double minNormal hex: "
                + Double.toHexString(minNormalD));
        System.out.println("double minSub hex: "
                + Double.toHexString(minSubD));
    }
}
~~~

Biên dịch, chạy:

~~~bash
javac --release 17 SubnormalDemo.java
java SubnormalDemo
~~~

Kết quả stdout chính xác:

~~~text
float minNormal: 0x00800000 / normal
float maxSub: 0x007FFFFF / subnormal
float minSub: 0x00000001 / subnormal
float zero: 0x00000000 / zero
float -zero: 0x80000000 / zero
float minNormal hex: 0x1.0p-126
float minSub hex: 0x0.000002p-126
float minNormal / 2: 0x00400000
float maxSub + minSub: 0x00800000
float minSub / 2: 0x00000000
float -minSub / 2: 0x80000000
float minSub * 1.5: 0x00000002
double minNormal: 0x0010000000000000
double maxSub: 0x000FFFFFFFFFFFFF
double minSub: 0x0000000000000001
double minNormal / 2: 0x0008000000000000
double minSub / 2: 0x0000000000000000
double minNormal hex: 0x1.0p-1022
double minSub hex: 0x0.0000000000001p-1022
~~~

**Giải thích những dòng quan trọng:**

- **float minNormal 0x00800000**: bit exponent đầu tiên bằng 1, fraction bằng 0 → normal nhỏ nhất.
- **float maxSub 0x007FFFFF**: exponent bằng 0, fraction toàn bit 1 → subnormal lớn nhất.
- **float minSub 0x00000001**: exponent bằng 0, chỉ bit fraction thấp nhất bằng 1 → subnormal nhỏ nhất.
- **float minNormal / 2 0x00400000**: kết quả đã chuyển sang miền subnormal, nhưng không mất đi.
- **float maxSub + minSub 0x00800000**: từ subnormal lớn nhất tiến đúng một bước đến normal nhỏ nhất; chứng minh tính liên tục của khoảng cách biểu diễn ở ngưỡng.
- **float minSub / 2 0x00000000**: giá trị đúng toán học quá nhỏ, làm tròn thành zero dương.
- **float -minSub / 2 0x80000000**: sự mất độ lớn không xóa bit dấu.
- **float minSub * 1.5 0x00000002**: ví dụ một phép làm tròn đúng trung điểm về phía significand chẵn.
- **double minNormal / 2 0x0008000000000000**: gradual underflow cũng hiện diện ở kiểu double, với độ rộng trường fraction là 52 bit.

**Float.toHexString/Double.toHexString** in số hexa dấu phẩy động dạng **0x...p...**, trong đó **p** mô tả số mũ cơ số 2. Nó không giống chuỗi **0x00800000** biểu thị nguyên mẫu bit. Đó là lý do chương trình dùng cả **toHexString** và **floatToRawIntBits/doubleToRawLongBits**.

Hàm **category** dựa trên trường bit và phù hợp để hiểu cách phân loại số float. Java còn có **Float.isFinite**, **Float.isNaN**, **Float.isInfinite**, nhưng các hàm này không phân biệt riêng normal/subnormal; nếu cần xác định subnormal, hãy xét trường exponent và fraction như ví dụ.

## 9. Vì sao gradual underflow có ích trong tính toán?

Các thuật toán khoa học, xử lý tín hiệu và phép tính giá trị xác suất đôi khi tạo ra những lượng rất nhỏ. Gradual underflow có thể duy trì chúng để các phép tính tiếp theo còn khai thác được thay vì đột ngột biến mất.

Ví dụ, giả sử một bước tính cho ra **x = Float.MIN_NORMAL / 2**. Nếu kết quả ấy còn được giữ, **x × 2** phục hồi đúng **Float.MIN_NORMAL**:

~~~java
float x = Float.MIN_NORMAL / 2.0f;
float restored = x * 2.0f;
System.out.println(restored == Float.MIN_NORMAL); // true
~~~

Trong phép tính này, giá trị trung gian là subnormal khác 0. Nếu nó bị làm tròn ngay thành 0, phép nhân sau đó không thể khôi phục thông tin. Tuy nhiên không phải mọi thao tác với subnormal đều chính xác; gần ngưỡng nhỏ nhất, một bước làm tròn thành 0 là điều không tránh được.

Với những ứng dụng cần **độ chính xác tương đối ổn định** ở miền rất nhỏ, chỉ dựa vào gradual underflow chưa đủ. Có thể cần **đổi thang đo (rescaling)**, tính tổng theo thuật toán số ổn định, sử dụng **logarithm** để lưu giá trị xác suất rất nhỏ, hoặc chọn biểu diễn số khác theo bài toán. Mỗi hướng đều đòi hỏi đánh giá lại công thức; không mặc nhiên chuyển mọi phép tính sang BigDecimal nếu vấn đề gốc là sự ổn định của thuật toán nhị phân.

## 10. Những lưu ý riêng khi chạy trên Java

### Java 17+ yêu cầu ngữ nghĩa strict

Từ Java 17, [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306) khôi phục việc đánh giá strict cho các biểu thức dấu phẩy động. Các toán tử floating-point Java phải tuân theo ngữ nghĩa tương ứng, bao gồm subnormal và gradual underflow. Từ khóa **strictfp** không còn làm thay đổi cách đánh giá số học ở Java 17+, dù vẫn tồn tại để tương thích mã nguồn.

Đừng nhầm yêu cầu ngữ nghĩa Java với cách cấu hình xử lý subnormal trong các thư viện native/JNI, GPU hoặc môi trường tính toán khác. Các hệ thống ngoài Java có thể sử dụng thiết lập flush-to-zero riêng; kết quả ở ranh giới liên kết cần kiểm chứng theo môi trường cụ thể.

### Tối ưu hiệu năng không làm thay đổi quy tắc số học

Trên một số phần cứng hoặc đường xử lý nhất định, phép toán liên quan subnormal có thể có chi phí hiệu năng khác normal. Không nên mặc định mọi JVM hay CPU đều bị chậm. Khi cần tối ưu, đo trên JVM và đầu vào thực tế, đồng thời bảo toàn tính đúng đắn của thuật toán.

### Những hàm giúp khảo sát giá trị

| API | Công dụng |
| --- | --- |
| **Float.MIN_NORMAL**, **Double.MIN_NORMAL** | Ngưỡng normal dương nhỏ nhất |
| **Float.MIN_VALUE**, **Double.MIN_VALUE** | Subnormal dương nhỏ nhất, không phải số âm nhỏ nhất |
| **Math.nextDown(x)** | Giá trị dấu phẩy động biểu diễn được gần nhất ở phía nhỏ hơn |
| **Math.nextUp(x)** | Giá trị dấu phẩy động biểu diễn được gần nhất ở phía lớn hơn |
| **Math.ulp(x)** | Khoảng đơn vị tại mức độ lớn của x theo định nghĩa của API |
| **Float.toHexString(x)**, **Double.toHexString(x)** | Biểu diễn hexa dấu phẩy động với số mũ nhị phân |
| **Float.floatToRawIntBits(x)** | Xem 32 bit của float, bao gồm bit dấu của −0.0 |
| **Double.doubleToRawLongBits(x)** | Xem 64 bit của double |

**Math.ulp(Float.MIN_NORMAL)** và **Math.ulp(Float.MIN_VALUE)** đều bằng **Float.MIN_VALUE**. Mẫu này phản ánh bước lưới không đổi của miền subnormal tại phía gần ngưỡng normal.

### Float và double không có cùng ngưỡng

Một giá trị dưới **Float.MIN_NORMAL** chưa chắc là subnormal đối với **double**. Ví dụ giá trị toán học **2^−149** là subnormal nhỏ nhất của float, nhưng là số **normal** trong double, vì **−149** vẫn lớn hơn rất nhiều so với số mũ normal nhỏ nhất **−1022** của double. Khi đổi kiểu từ double sang float, một giá trị có thể bị làm tròn thành subnormal hoặc zero; hãy xét kiểu lưu trữ của kết quả, không chỉ giá trị ban đầu.

## 11. Những nhầm lẫn phổ biến

| Nhầm lẫn | Điều đúng cần ghi nhớ |
| --- | --- |
| **Float.MIN_VALUE** là float âm nhất | Nó là float **dương khác 0 nhỏ nhất**, thuộc miền subnormal |
| Subnormal nghĩa là zero | Subnormal có fraction khác 0, là số hữu hạn khác 0 |
| Exponent E=0 luôn có nghĩa số mũ thực bằng −bias | Subnormal dùng số mũ nền **−126** (float) hoặc **−1022** (double) và leading bit **0** |
| Số normal vừa dưới ngưỡng sẽ trở thành 0 ngay | Java giữ subnormal khi làm tròn có giá trị subnormal |
| Subnormal có đủ 24/53 bit có nghĩa như normal | Độ chính xác tương đối giảm dần khi tiến về zero |
| Giá trị subnormal luôn do phép tính sai số tạo ra | Nhiều kết quả subnormal, ví dụ chia đôi MIN_NORMAL, là chính xác |
| Underflow luôn ném exception | Phép toán float/double trả subnormal hoặc signed zero, không ném ArithmeticException do underflow |
| **0.0f == -0.0f** nghĩa là mẫu bit giống nhau | Hai zero so sánh bằng nhau nhưng khác bit dấu và có thể dẫn tới +/−Infinity khi làm mẫu số |
| Toán tử Java có thể tự flush mọi subnormal về 0 để tối ưu | Ngữ nghĩa floating-point Java yêu cầu gradual underflow; việc tối ưu phải giữ kết quả tương đương |
| In giá trị thập phân là đủ để hiểu biểu diễn | Dùng **toHexString** và **RawBits** để thấy ngưỡng, số mũ, bit fraction và signed zero |

## 12. Câu hỏi và bài tập tự kiểm tra

**Câu 1.** Vì sao **Float.MIN_NORMAL / 2.0f** là số khác 0?

**Đáp án:** Kết quả bằng **2^−127**, vẫn là bội nguyên của **2^−149**, nên biểu diễn được chính xác bằng subnormal có mẫu **0x00400000**.

**Câu 2.** Mẫu bit **0x00000001** của float thuộc loại nào? Giá trị là bao nhiêu?

**Đáp án:** Exponent bằng 0 và fraction bằng 1, nên là **subnormal** dương nhỏ nhất, giá trị **2^−149 = Float.MIN_VALUE**.

**Câu 3.** Vì sao **Float.MIN_VALUE / 2.0f** thành **+0.0f**, nhưng **Float.MIN_VALUE * 1.5f** thành **0x00000002**?

**Đáp án:** Cả hai kết quả toán học đều ở đúng trung điểm trên lưới biểu diễn. Ties-to-even chọn **0** trong trường hợp đầu và chọn **2 × 2^−149** trong trường hợp sau.

**Câu 4.** Số subnormal dương lớn nhất của float là gì? Số normal dương nhỏ nhất cách nó bao xa?

**Đáp án:** **0x007FFFFF = (2^23−1) × 2^−149**; khoảng cách đến **Float.MIN_NORMAL** đúng **Float.MIN_VALUE = 2^−149**.

**Câu 5.** Khi chuyển **float** nhỏ nhất dương sang **double**, nó còn là subnormal không?

**Đáp án:** Không. **2^−149** là số normal của double. Loại normal/subnormal phụ thuộc **định dạng đích**.

**Câu 6.** Nếu tính xác suất rất nhỏ, chỉ có gradual underflow thì đã tránh được mọi mất độ chính xác chưa?

**Đáp án:** Chưa. Nó kéo dài miền số hữu hạn khác 0, nhưng độ chính xác tương đối vẫn suy giảm ở subnormal và các kết quả đủ nhỏ vẫn bị làm tròn về zero. Có thể cần biến đổi công thức hoặc làm việc trong miền log tùy thuật toán.

## 13. Tài liệu đối chiếu

- [Java Language Specification SE 17 — §4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): miền biểu diễn normal/subnormal, độ rộng và độ chính xác.
- [Java Language Specification SE 17 — §15.4 Floating-Point Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): ngữ nghĩa phép tính, underflow và các giá trị đặc biệt.
- [Float API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html): các hằng **MIN_NORMAL**, **MIN_VALUE**, phương thức **toHexString** và thao tác bit.
- [Double API, Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): hằng số và hàm tương ứng với binary64.
- [OpenJDK JEP 306](https://openjdk.org/jeps/306): ngữ nghĩa floating-point luôn strict từ Java 17.