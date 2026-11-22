# So sánh bằng sai số tuyệt đối trong Java

Khi làm việc với `float` và `double`, không phải lúc nào hai giá trị đại diện cho cùng kết quả toán học cũng có cùng **mẫu bit**. Chẳng hạn phép cộng `0.1 + 0.2` trên `double` thường cho giá trị được in là `0.30000000000000004`, khác literal `0.3`. Nếu bài toán đo lường cho phép chênh lệch nhỏ, ta có thể so sánh bằng **sai số tuyệt đối** (*absolute tolerance*) thay vì bắt buộc dùng `==`.

```java
double actual = 0.1 + 0.2;
double expected = 0.3;
double epsilon = 1e-12;

boolean exact = actual == expected; // false
boolean close = Math.abs(actual - expected) <= epsilon; // true
```

Tuy nhiên, biểu thức thứ hai **không phải cách thay thế `==` cho mọi tình huống**. Nó chỉ có ý nghĩa khi `epsilon` được chọn từ yêu cầu thực tế, đơn vị của dữ liệu, và có chính sách xử lý NaN, vô cực, số rất lớn, số gần 0. Bài này trình bày phép so sánh tuyệt đối, ý nghĩa kỹ thuật, cài đặt Java 17+, cách kiểm thử và những ranh giới không nên lạm dụng.

## 1. Tại sao so sánh `double` bằng `==` dễ gây bất ngờ?

`double` lưu số theo định dạng nhị phân IEEE 754 binary64 với 53 bit significand. Phân số như `0.1` và `0.2` không có biểu diễn nhị phân hữu hạn, nên Java lưu các giá trị **gần nhất có thể biểu diễn**. Phép cộng lại áp dụng quy tắc làm tròn chấm động.

```java
double sum = 0.1 + 0.2;
System.out.println(sum);        // 0.30000000000000004
System.out.println(sum == 0.3); // false
```

Ở đây không có lỗi “Java cộng sai”. Vấn đề là phép toán chạy trên các giá trị nhị phân xấp xỉ; kết quả gần 0.3 nhưng không có cùng giá trị binary64 với literal `0.3`.

**Phân biệt hai loại yêu cầu:**

- **Bằng nhau chính xác:** Hai giá trị số cần thật sự bằng nhau theo ngữ nghĩa Java; `==` có thể là lựa chọn đúng, ví dụ kiểm tra bộ đếm nguyên, mã định danh, hoặc một trạng thái số phải chính xác.
- **Gần nhau trong dung sai:** Hai kết quả đo hoặc tính toán có thể khác nhẹ nhưng vẫn được coi như đạt yêu cầu ứng dụng. Khi đó, một ngưỡng sai số cụ thể có thể phù hợp hơn.

Đừng chuyển toàn bộ phép so sánh số thực sang gần đúng theo thói quen. Sự gần đúng là **chính sách nghiệp vụ**, không phải thuộc tính mặc định của mọi số `double`.

## 2. Định nghĩa sai số tuyệt đối

Với hai giá trị hữu hạn `a` và `b`, **sai số tuyệt đối** là:

\[
E_{\mathrm{abs}} = |a-b|
\]

Ta nói hai giá trị **gần nhau theo ngưỡng tuyệt đối** `ε` khi:

\[
|a-b| \leq \varepsilon
\qquad (\varepsilon \geq 0)
\]

Trong Java, cách viết tương ứng cho phép kiểm tra đơn giản:

```java
boolean close = Math.abs(a - b) <= epsilon;
```

Ở đây `Math.abs(double)` trả độ lớn không âm của hiệu (trừ các trường hợp đặc biệt như NaN), còn dấu `<=` chọn quy ước **cho phép bằng ngưỡng**. Nếu bài toán yêu cầu nhỏ hơn **nghiêm ngặt**, dùng `<`, nhưng phải viết rõ hợp đồng kiểm thử.

### Ví dụ bằng số

Cho `a = 12.34`, `b = 12.35` và sai số cho phép `epsilon = 0.02`:

```text
absolute error = |12.34 - 12.35|
               ≈ 0.01
tolerance      = 0.02
0.01 <= 0.02   => true
```

Các số thập phân nhập dưới dạng `double` có thể bị làm tròn; dấu `≈` nhắc rằng phép trừ thực tế cũng dùng số nhị phân. Ví dụ chỉ minh họa **đại lượng chênh lệch**; kết luận nên được kiểm tra bằng chính dữ liệu và kiểu số thực tế.

Với giá trị **biểu diễn chính xác trong nhị phân**, ranh giới rất rõ:

```java
System.out.println(Math.abs(1.0 - 1.125) <= 0.125); // true
System.out.println(Math.abs(1.0 - 1.25) <= 0.125);  // false
```

`1.125`, `1.25` và `0.125` là các phân số có mẫu là lũy thừa 2, nên ở đây không bị nhập nhằng do việc lưu literal.

## 3. `epsilon` là ngưỡng có **đơn vị**, không phải hằng số thần kỳ

`epsilon` phải diễn tả **mức chênh lệch lớn nhất mà bài toán chấp nhận**.

| Dữ liệu | Ví dụ mức dung sai tuyệt đối | Đơn vị và ý nghĩa |
| --- | --- | --- |
| Nhiệt độ cảm biến | `0.2` | 0,2 °C nếu dữ liệu biểu diễn °C |
| Tọa độ theo mét | `0.005` | 5 mm |
| Thời gian theo giây | `0.001` | 1 ms |
| Hiệu điện thế | `0.01` | 0,01 V |
| Thuật toán chỉ kiểm tra sai số làm tròn quanh 0.3 | `1e-12`, chỉ khi có căn cứ | Là lựa chọn của bài toán thử nghiệm, **không phải ngưỡng chuẩn** cho mọi `double` |

Các con số minh họa không phải khuyến cáo đo lường cho một thiết bị cụ thể; tiêu chuẩn chất lượng thiết bị và hợp đồng ứng dụng quyết định ngưỡng thật.

Nếu `a` và `b` có đơn vị **mét**, `epsilon` cũng phải tính bằng **mét**. Nếu một bên dùng mét còn bên kia dùng millimét, phép so sánh có thể trả lời rất “hợp cú pháp” nhưng **sai ngữ nghĩa**.

**Không dùng một giá trị `1e-6` ở mọi dự án** chỉ vì nó nhỏ. Trong một hệ thống đo kích thước nano, `1e-6` có thể quá lớn; khi đo quãng đường tính bằng triệu km, nó có thể quá nhỏ.

### Tại sao `Double.MIN_VALUE` không phải epsilon mặc định?

`Double.MIN_VALUE` là số dương **khác 0 nhỏ nhất** mà binary64 có thể biểu diễn, xấp xỉ `4.9e-324`. Nó không biểu thị sai số làm tròn điển hình. `Math.ulp(1.0)` khoảng `2.220446049250313e-16` gần 1.0; khoảng cách giữa các giá trị biểu diễn thay đổi theo độ lớn. Dùng `Double.MIN_VALUE` để kiểm tra “gần nhau” thường tương đương yêu cầu gần như bằng nhau chính xác.

Ngay cả một bội số cố định của `Math.ulp(1.0)` cũng không có nghĩa phù hợp với mọi giá trị: bước lượng tử chấm động phụ thuộc độ lớn của số, trong khi ngưỡng tuyệt đối là một độ chênh **theo đơn vị nghiệp vụ**.

## 4. Hàm so sánh Java 17+ có kiểm tra điều kiện đầu vào

Biểu thức `Math.abs(a-b) <= epsilon` ngắn gọn nhưng **không nêu rõ chính sách NaN, vô cực hoặc ngưỡng sai**. Với dữ liệu đo lường yêu cầu các số phải **hữu hạn**, có thể viết:

```java
static boolean closeAbs(double a, double b, double epsilon) {
    if (!Double.isFinite(epsilon) || epsilon < 0.0) {
        throw new IllegalArgumentException(
                "epsilon must be finite and >= 0");
    }
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }
    if (a == b) {
        return true;
    }
    return Math.abs(a - b) <= epsilon;
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp. Phiên bản đầy đủ chạy được có ở phần 10.

**Hợp đồng của hàm:**

1. `epsilon` phải **hữu hạn** và **không âm**. NaN, ±Infinity và epsilon âm bị từ chối bằng `IllegalArgumentException`.
2. Nếu `a` hoặc `b` là NaN/vô cực, trả `false`. Điều này phù hợp bài toán chỉ chấp nhận **giá trị đo hữu hạn**.
3. Hai số hữu hạn đã bằng nhau theo `==` được coi là gần nhau, kể cả epsilon bằng 0.
4. Với các số hữu hạn còn lại, trả giá trị của `Math.abs(a-b) <= epsilon`.

Không nên gọi chính sách trên là **quy tắc duy nhất**. Một ứng dụng có thể coi `+Infinity` với `+Infinity` là cùng trạng thái đặc biệt, hoặc yêu cầu zero phải phân biệt dấu. Nếu vậy cần **định nghĩa chính sách khác**, thay vì đổi mã mà không giải thích.

### Vì sao phải kiểm tra `epsilon` trước?

Nếu `epsilon = Double.NaN`, phép so sánh `<=` với NaN luôn sai; nếu `epsilon = Double.POSITIVE_INFINITY`, nhiều cặp số cực kỳ khác nhau sẽ được coi là gần, làm mất ý nghĩa kiểm tra. Nếu `epsilon < 0`, ngay cả hai số hữu hạn giống nhau cũng không thỏa công thức ngưỡng thông thường.

Việc ném `IllegalArgumentException` làm lộ lỗi cấu hình hoặc lỗi chọn ngưỡng ngay tại ranh giới gọi hàm.

### Có cần nhánh `a == b`?

Trong hàm này, với các số hữu hạn, nhánh đó giúp thể hiện rõ rằng **bằng nhau chính xác phải được chấp nhận ngay cả khi epsilon bằng 0**. Công thức trừ và lấy trị tuyệt đối cũng cho kết quả đúng trong trường hợp ấy; nhánh chỉ làm hợp đồng dễ đọc và tránh tính hiệu không cần thiết.

**Không** đặt `a == b` trước kiểm tra hữu hạn nếu chính sách yêu cầu từ chối Infinity: `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` là `true`, nhưng ứng dụng không muốn coi hai giá trị đo vô hạn là hợp lệ.

## 5. Những trường hợp ranh giới phải xử lý rõ

### 5.1. NaN

`Double.NaN` thường đại diện cho kết quả không xác định trong phép toán chấm động. Các toán tử so sánh với NaN có hành vi đặc biệt:

```java
double x = Double.NaN;
System.out.println(x == x); // false
System.out.println(Math.abs(x - 1.0) <= 1.0); // false
```

Hàm `closeAbs` phía trên trả `false` cho NaN trước khi trừ. Nếu muốn coi hai giá trị NaN là cùng **trạng thái dữ liệu thiếu**, cần logic riêng; đừng lẫn việc “cùng trạng thái” với **sai số số học**.

### 5.2. Vô cực

`Math.abs(Double.POSITIVE_INFINITY - Double.POSITIVE_INFINITY)` là NaN, do đó phép kiểm tra ngưỡng thuần túy trả `false`. Nhưng `Double.POSITIVE_INFINITY == Double.POSITIVE_INFINITY` là `true`. Hai cách so sánh đơn giản có chính sách khác nhau.

Vì vậy, cách làm rõ ràng là **quyết định trước** có cho phép giá trị không hữu hạn hay không. Với dữ liệu đo cần hữu hạn, `Double.isFinite` giúp loại vô cực và NaN một cách tường minh.

### 5.3. Zero có dấu

`+0.0` và `-0.0` được coi là bằng nhau theo `==`:

```java
System.out.println(+0.0 == -0.0); // true
```

Hàm so sánh sai số tuyệt đối trên trả `true` cho cặp này, kể cả `epsilon = 0`. Nếu cần so sánh **mẫu bit IEEE 754** (chẳng hạn serialization hoặc giao thức số học đặc biệt), `+0.0` và `-0.0` khác nhau; khi ấy so sánh độ gần số học **không phải bài toán đúng**. Cân nhắc `Double.doubleToRawLongBits` với chính sách NaN rõ ràng.

### 5.4. Hiệu tràn khi trừ hai số hữu hạn rất lớn

Hai `double` đều hữu hạn nhưng hiệu của chúng có thể vượt miền `double`:

```java
double a = Double.MAX_VALUE;
double b = -Double.MAX_VALUE;
double difference = a - b; // +Infinity
```

Nếu `epsilon` cũng là một số hữu hạn, hiệu toán học của cặp trên lớn hơn mọi epsilon hữu hạn có thể biểu diễn. Vì vậy trả `false` là hợp lý. Trường hợp này cho thấy **phép trừ cũng có miền biểu diễn**, và không nên mù quáng đưa các phép biến đổi đại số tương đương vào mã số học chấm động.

### 5.5. Giá trị rất gần 0

Giả sử `a = 1e-12`, `b = 0` và `epsilon = 1e-9`. Hai giá trị được coi là gần vì `1e-12 <= 1e-9`, nhưng `a` vẫn là **một giá trị khác 0**.

Một ngưỡng tuyệt đối giúp xác định “đủ gần zero” theo đơn vị, nhưng **không biến giá trị đó thành zero toán học**. Nếu `a` là dòng rò điện cần phát hiện, hoặc tín hiệu vật lý cực nhỏ quan trọng, việc coi gần zero thành zero có thể che giấu sự kiện thật.

## 6. Sai số tuyệt đối tốt khi nào, yếu khi nào?

### Tốt: đại lượng có miền và ngưỡng chênh cố định

Ví dụ kiểm tra nhiệt độ đo so với nhiệt độ mục tiêu, sai số cho phép ±0,2 °C, một ngưỡng tuyệt đối có ý nghĩa rõ ràng. Với tọa độ đo bằng mét, kiểm tra chênh không quá 1 mm cũng là một quyết định theo **đơn vị**.

Sai số tuyệt đối đặc biệt dễ hiểu gần zero: “giá trị này cách zero bao nhiêu đơn vị?”.

### Yếu: dữ liệu trải qua nhiều bậc độ lớn

Xét hai trường hợp dùng cùng `epsilon = 1e-6`:

- So sánh các giá trị quanh `1e-12`: ngưỡng lớn gấp nhiều lần giá trị, dễ coi những giá trị khác nhau về tỷ lệ là tương đương.
- So sánh các giá trị quanh `1e12`: ngưỡng nhỏ hơn khoảng cách giữa một số cặp `double` liền kề ở vùng này, có thể quá khắt khe.

Do đó, nếu lỗi chấp nhận được **phụ thuộc tỷ lệ hoặc độ lớn**, một ngưỡng **tương đối** hoặc kết hợp tương đối/tuyệt đối có thể phù hợp hơn. Nhưng đó là một chính sách khác; chỉ nên chọn sau khi xác định đầu ra và mức lỗi nghiệp vụ.

Một công thức kết hợp thường gặp là:

\[
|a-b| \leq \max(\varepsilon_{\mathrm{abs}},\ \varepsilon_{\mathrm{rel}}\max(|a|,|b|)).
\]

Không dùng công thức đó mà quên kiểm tra NaN, Infinity, ngưỡng âm hoặc overflow khi tính các đại lượng trung gian. Ở đây trọng tâm là **absolute tolerance**; công thức kết hợp chỉ để định vị giới hạn của phương pháp.

### Bảng lựa chọn

| Trường hợp | Sai số tuyệt đối có phù hợp? | Lưu ý |
| --- | --- | --- |
| Giá trị gần 0, đơn vị và ngưỡng rõ | Thường phù hợp | Ví dụ khoảng cách tuyệt đối tới 0 |
| Độ lệch cảm biến cho phép tối đa 0,2 đơn vị | Phù hợp nếu hợp đồng đã quy định | Ngưỡng phải cùng đơn vị |
| So sánh giá trị từ `1e-12` đến `1e12` | Một ngưỡng duy nhất thường không đủ | Cân nhắc tương đối/kết hợp |
| Kiểm tra số nguyên, ID hoặc hash | Không nên dùng | Dùng bằng nhau chính xác và kiểu nguyên |
| Tiền tệ cần tính đúng theo cent | Không phù hợp như cách chữa sai số | `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất |
| So sánh mẫu bit và signed zero | Không phù hợp | Dùng API kiểm tra bit |
| NaN, Infinity trong mô hình trạng thái | Chỉ khi có chính sách riêng | Không gọi chúng là số đo “gần nhau” |
| Dùng ngưỡng để che sai thuật toán | Không phù hợp | Điều tra nguyên nhân sai số |

## 7. `float`, `double` và tác động của kiểu dữ liệu

`float` có khoảng 24 bit significand, còn `double` có 53 bit significand. Vì vậy, cùng một giá trị toán học có thể chịu sai số lưu trữ khác nhau theo kiểu.

```java
float x = 0.1f;
double y = 0.1d;

System.out.println((double) x); // 0.10000000149011612
System.out.println(y);          // 0.1
```

Khi so sánh một `float` với một `double`, giá trị `float` được **mở rộng sang `double` nhưng không khôi phục thông tin đã mất**. Nếu dùng hàm nhận `double`, phép chuyển mở rộng là hợp lệ; tuy nhiên ngưỡng phải được chọn theo độ phân giải thực tế của đầu vào binary32, không giả định hai toán hạng có cùng độ chính xác.

### Vì sao không dùng một epsilon bất biến cho mọi `float`?

Giống `double`, khoảng cách giữa hai số `float` biểu diễn được **tăng theo độ lớn**. Ở gần 1.0, `Math.ulp(1.0f)` khoảng `1.1920929e-7`; ở gần 1.0 với `double`, `Math.ulp(1.0d)` khoảng `2.220446049250313e-16`.

`Math.ulp` đo bước biểu diễn ở một vùng giá trị, **không phải ngưỡng sai số nghiệp vụ tự sinh**. Nó hữu ích khi đánh giá việc một ngưỡng tuyệt đối có nhỏ hơn độ phân giải của dữ liệu hay không.

Nếu dữ liệu đến từ cảm biến chính xác tới 0,01 đơn vị, ngưỡng `1e-12` có thể hoàn toàn không thực tế, dù kiểu lưu trữ là `double`.

## 8. So sánh “gần bằng” không phải quan hệ bằng nhau toán học

Với `epsilon > 0`, một phép so sánh gần đúng có thể:

- **Đối xứng:** `closeAbs(a,b,epsilon)` và `closeAbs(b,a,epsilon)` cho cùng kết quả trên số hữu hạn theo tiêu chí sai số tuyệt đối.
- **Tự gần chính mình:** mọi giá trị **hữu hạn** đều gần chính nó nếu epsilon hợp lệ và không âm.
- **Không có tính bắc cầu:** `a` gần `b` và `b` gần `c` **không bảo đảm** `a` gần `c`.

Ví dụ chọn các số biểu diễn được chính xác:

```java
double epsilon = 0.25;
double a = 0.0;
double b = 0.25;
double c = 0.5;

// closeAbs(a,b,epsilon) == true.
// closeAbs(b,c,epsilon) == true.
// closeAbs(a,c,epsilon) == false.
```

Vì thế **không** nên dùng so sánh epsilon thay cho `equals`/`hashCode` của khóa trong `HashMap`/`HashSet` hoặc kỳ vọng nó là quan hệ tương đương của nhóm đối tượng. Các thuật toán sắp xếp và cấu trúc dữ liệu đòi hỏi hợp đồng nhất quán; comparator dùng epsilon thiếu bắc cầu có thể vi phạm hợp đồng so sánh.

### Một hậu quả khác: “gần bằng” có thể làm mờ ngưỡng

Nếu dùng `closeAbs(x, limit, epsilon)` để quyết định “`x` không được vượt `limit`”, đó không phải kiểm tra bất đẳng thức phù hợp: số nằm **dưới** giới hạn rất xa là hợp lệ nhưng không “gần” giới hạn. Bài toán **kiểm tra giới hạn** nên dùng bất đẳng thức có chính sách biên rõ:

```java
boolean withinUpperBound = x <= upperBound;
```

Nếu cho phép vượt nhẹ ngưỡng, phải quy định cụ thể “`x <= upperBound + tolerance`” cùng chính sách chống overflow và xử lý không hữu hạn, thay vì gọi “gần bằng” một cách mơ hồ. So sánh gần đúng chỉ trả lời **độ chênh giữa hai số**, không thay thế logic thứ tự.

## 9. Lưu ý khi viết test tự động

Trong unit test, thường có ba đầu vào quan trọng: **actual**, **expected**, và **tolerance**.

```java
double actual = 0.1 + 0.2;
double expected = 0.3;
double tolerance = 1e-12;

if (Math.abs(actual - expected) > tolerance) {
    throw new AssertionError("Actual is too far from expected");
}
```

Đoạn này minh họa ý tưởng nhưng chưa đầy đủ chính sách NaN/Infinity: với NaN, phép `>` cũng trả `false`, khiến nhánh throw **không chạy**. Vì vậy, khi viết helper kiểm thử tin cậy, nên dùng kết quả của một hàm đã kiểm tra finite và ngưỡng:

```java
if (!closeAbs(actual, expected, tolerance)) {
    throw new AssertionError("Values differ beyond absolute tolerance");
}
```

Với thư viện kiểm thử như JUnit, dùng overload assertion cho số chấm động có `delta` nếu phiên bản/framework cung cấp, và đọc hợp đồng của API đó (nhất là NaN và Infinity). Không tự giả định mọi thư viện xử lý giá trị đặc biệt giống hệt helper tự viết.

### Các bài test nên có

| Trường hợp | Ví dụ | Kỳ vọng theo helper `closeAbs` |
| --- | --- | --- |
| Chênh nhỏ trong ngưỡng | `0.1+0.2`, `0.3`, `1e-12` | `true` |
| Chênh vượt ngưỡng | Cặp trên với `1e-17` | `false` |
| Chính xác tại biên | `1.0`, `1.125`, `0.125` | `true` |
| Vượt biên | `1.0`, `1.25`, `0.125` | `false` |
| Giá trị hữu hạn bằng nhau | `2.0`, `2.0`, `0` | `true` |
| Zero khác dấu | `+0.0`, `-0.0`, `0` | `true` |
| Có NaN | `NaN`, `NaN`, `1` | `false` |
| Vô cực | `+Infinity`, `+Infinity`, `1` | `false` |
| Epsilon âm | `1`, `1`, `-1` | `IllegalArgumentException` |
| Epsilon NaN/vô cực | `1`, `1`, `NaN` | `IllegalArgumentException` |
| Hai số hữu hạn có hiệu tràn | `MAX_VALUE`, `-MAX_VALUE`, `MAX_VALUE` | `false` |

Cần test cả **thay đổi đơn vị** và **cận trên/cận dưới của phép đo**, vì một ngưỡng hợp lý ở dữ liệu nhỏ có thể quá lỏng hoặc quá chặt ở miền lớn.

## 10. Chương trình Java 17+ chạy độc lập

Tạo tệp `AbsoluteToleranceDemo.java`:

```java
import java.util.Locale;

public class AbsoluteToleranceDemo {
    static boolean closeAbs(double a, double b, double epsilon) {
        if (!Double.isFinite(epsilon) || epsilon < 0.0) {
            throw new IllegalArgumentException(
                    "epsilon must be finite and >= 0");
        }
        if (!Double.isFinite(a) || !Double.isFinite(b)) {
            return false;
        }
        if (a == b) {
            return true;
        }
        return Math.abs(a - b) <= epsilon;
    }

    public static void main(String[] args) {
        double sum = 0.1 + 0.2;
        System.out.printf(Locale.ROOT, "0.1 + 0.2 = %.17f%n", sum);

        System.out.println("Exact equality with 0.3: " + (sum == 0.3));
        System.out.println("epsilon 1e-12: " + closeAbs(sum, 0.3, 1e-12));
        System.out.println("epsilon 1e-17: " + closeAbs(sum, 0.3, 1e-17));

        System.out.println("At boundary: "
                + closeAbs(1.0, 1.125, 0.125));
        System.out.println("Outside boundary: "
                + closeAbs(1.0, 1.25, 0.125));

        System.out.println("Signed zero: "
                + closeAbs(+0.0, -0.0, 0.0));
        System.out.println("NaN accepted: "
                + closeAbs(Double.NaN, Double.NaN, 1.0));
        System.out.println("Infinity accepted: "
                + closeAbs(Double.POSITIVE_INFINITY,
                        Double.POSITIVE_INFINITY, 1.0));

        System.out.println("Large values: "
                + closeAbs(1e12, 1e12 + 0.01, 0.001));
        System.out.println("Tiny signal considered close: "
                + closeAbs(1e-12, 0.0, 1e-9));
        System.out.println("Gap overflow accepted: "
                + closeAbs(Double.MAX_VALUE,
                        -Double.MAX_VALUE, Double.MAX_VALUE));

        try {
            closeAbs(1.0, 1.0, Double.NaN);
        } catch (IllegalArgumentException ex) {
            System.out.println("Invalid tolerance: rejected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 AbsoluteToleranceDemo.java
java AbsoluteToleranceDemo
```

Stdout (đã kiểm chứng):

```text
0.1 + 0.2 = 0.30000000000000004
Exact equality with 0.3: false
epsilon 1e-12: true
epsilon 1e-17: false
At boundary: true
Outside boundary: false
Signed zero: true
NaN accepted: false
Infinity accepted: false
Large values: false
Tiny signal considered close: true
Gap overflow accepted: false
Invalid tolerance: rejected
```

Điều quan trọng nhất ở ví dụ là **cùng một cặp giá trị** có thể gần nhau với epsilon này nhưng không gần với epsilon nhỏ hơn. Đó không phải sự mâu thuẫn: epsilon là **đầu vào quyết định hợp đồng**, không phải một hằng nội tại của `double`.

Dòng `Tiny signal considered close: true` cũng là lời cảnh báo: một ngưỡng tuyệt đối quá rộng có thể che khuất tín hiệu nhỏ. Dòng `Infinity accepted: false` phản ánh **chính sách chỉ nhận số hữu hạn** của helper, chứ không phải toán tử `==` của Java.

## 11. Những lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách đúng |
| --- | --- | --- |
| `a == b` cho mọi kết quả tính toán chấm động | Các bước làm tròn có thể khiến khác bit | Chỉ dùng absolute tolerance khi nghiệp vụ cho phép |
| Dùng epsilon cố định `1e-6` cho mọi đơn vị và miền | Ngưỡng quá lớn hoặc quá nhỏ tùy ngữ cảnh | Chọn epsilon theo đơn vị, miền, độ phân giải, yêu cầu |
| Dùng `Double.MIN_VALUE` như “sai số mặc định” | Đây là số dương subnormal nhỏ nhất | Chọn ngưỡng theo bài toán, hiểu `Math.ulp` |
| Dùng epsilon âm hoặc NaN | Công thức gần bằng mất ý nghĩa hoặc cho kết quả bất ngờ | Validate epsilon hữu hạn và không âm |
| Chỉ kiểm tra `if (abs(actual-expected) > eps) fail` | Với NaN, phép `>` trả false, có thể bỏ lọt lỗi | Dùng `if (!closeAbs(...)) fail` và chính sách NaN |
| Coi Infinity bằng Infinity là “gần nhau” dù dữ liệu đo phải hữu hạn | `==` và so sánh sai số có hợp đồng khác | Kiểm tra `Double.isFinite` |
| Coi `+0.0` và `-0.0` phải khác nhau trong đo lường | Dấu 0 thường không có ý nghĩa khoảng cách | So sánh theo độ gần; dùng raw bits khi cần phân biệt dấu |
| Dùng tolerance để so sánh index/ID | Chấp nhận nhầm hai giá trị khác nhau | Dùng kiểu nguyên và `==`/`equals` thích hợp |
| Dùng `closeAbs` làm `equals`/Comparator | Gần bằng không bắc cầu | Tách kiểm tra gần bằng khỏi hợp đồng collection |
| Quên thay đổi đơn vị | Ngưỡng 0,01 m không bằng 0,01 mm | Chuẩn hóa đơn vị trước khi so sánh |
| Chỉ nghĩ đến sai số lúc lưu literal | Mỗi phép toán trung gian có thể làm tròn | Xem toàn bộ pipeline tính toán |
| Dùng `float` rồi lấy epsilon của `double` mà không đánh giá | `float` có độ phân giải thấp hơn | Xem `Math.ulp` và mức sai số của dữ liệu nguồn |
| Dùng “gần bằng giới hạn” để thay kiểm tra `<=` | Gần bằng không diễn đạt miền cho phép | Viết điều kiện giới hạn và chính sách biên riêng |

## 12. Câu hỏi tự kiểm tra

1. Vì sao `0.1 + 0.2 == 0.3` là `false` trong Java? Đổi sang so sánh tuyệt đối có ý nghĩa khi nào?
2. Với `a = 1.0`, `b = 1.125`, `epsilon = 0.125`, điều kiện `Math.abs(a-b) <= epsilon` cho kết quả gì? Nếu dùng `<` thay vì `<=` thì sao?
3. Vì sao epsilon cần có **cùng đơn vị** với dữ liệu? Chuyện gì xảy ra nếu một giá trị tính bằng mét và một giá trị tính bằng mm?
4. Nếu một cảm biến đo gần zero nhưng tín hiệu `1e-12` là quan trọng, vì sao epsilon `1e-9` có thể nguy hiểm?
5. Vì sao `Double.MIN_VALUE` không phải ngưỡng thích hợp để kiểm tra các phép toán gần 1.0?
6. `Math.abs(Double.NaN - expected) <= epsilon` cho kết quả gì? Dùng biểu thức `Math.abs(...) > epsilon` để fail unit test có thể gây vấn đề nào?
7. Hàm `closeAbs` trong bài xử lý Infinity như thế nào? Nếu ứng dụng muốn coi Infinity cùng dấu là cùng trạng thái, bạn sẽ thay đổi hợp đồng ra sao?
8. `closeAbs(+0.0,-0.0,0.0)` trả gì? Khi nào cần kiểm tra bit thay vì độ gần số học?
9. Vì sao quan hệ “gần bằng” không có tính bắc cầu? Đưa ví dụ ba số gần nhau từng cặp kế tiếp nhưng hai đầu không gần nhau.
10. Khi dữ liệu trải trên miền từ `1e-12` tới `1e12`, tại sao một epsilon tuyệt đối cố định có thể không phù hợp?
11. Nếu lưu cảm biến dưới dạng `float` rồi so sánh với dữ liệu `double`, bước widening có phục hồi các bit đã mất không?
12. Vì sao khi cần kiểm tra giá trị không vượt ngưỡng, `closeAbs(x,upperBound,eps)` không thay thế trực tiếp cho `x <= upperBound`?

## 13. Tham khảo

- [Java SE 17 — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): các giá trị NaN/Infinity, `isFinite`, `isNaN` và các quy tắc liên quan tới binary64.
- [Java SE 17 — `Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): `abs(double)`, `ulp(double)` và các phép toán số học.
- [Java Language Specification, `4.2.3 — Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): định dạng số dấu phẩy động và các giá trị đặc biệt.
- [Java Language Specification, `15.21.1 — Numerical Equality Operators](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.21.1): `==`/`!=` và hành vi với NaN/signed zero.

**Ghi nhớ:** So sánh bằng sai số tuyệt đối là quy tắc **`|a-b| <= epsilon`**, trong đó `epsilon` phải được chọn theo **đơn vị, miền và yêu cầu chính xác của bài toán**. Đây là cách đánh giá chênh lệch có chủ đích, **không phải phép thay thế `==` phổ quát**. Để triển khai đáng tin cậy trên Java, cần xác định chính sách NaN/Infinity/±0, validate epsilon, kiểm thử biên, và biết khi nào một ngưỡng tương đối hoặc mô hình số khác phù hợp hơn.