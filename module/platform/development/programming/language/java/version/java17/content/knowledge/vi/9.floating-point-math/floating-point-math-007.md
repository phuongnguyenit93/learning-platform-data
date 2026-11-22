# Math, StrictMath và yêu cầu tái hiện kết quả trong Java 17

> **Chủ đề:** Java 17  
> **Chương:** Số thực  
> **Mục tiêu:** Hiểu phép toán dấu phẩy động trong Java 17, phân biệt vai trò của `Math` và `StrictMath`, chọn API phù hợp khi cần kết quả có thể tái hiện giữa các môi trường, và biết những giới hạn của tính tái hiện trong ứng dụng thực tế.

## 1. Vì sao cùng một công thức có thể tạo kết quả khác nhau?

Trong Java, kiểu `double` và `float` biểu diễn số thực bằng dạng dấu phẩy động nhị phân. Nhiều số thập phân quen thuộc không thể biểu diễn chính xác bằng một số bit hữu hạn. Ví dụ:

```java
double value = 0.1 + 0.2;
System.out.println(value);
```

Kết quả thường thấy:

```text
0.30000000000000004
```

Đây không phải lỗi riêng của Java. `0.1` và `0.2` được xấp xỉ trong hệ nhị phân; phép cộng thực hiện trên các giá trị dấu phẩy động đó, vì vậy kết quả không nhất thiết là số thập phân chính xác `0.3`.

Ngoài sai số biểu diễn, một chương trình còn có thể quan tâm đến việc **cùng đầu vào có tạo cùng kết quả số hay không** khi chạy trên các máy, hệ điều hành hoặc runtime khác nhau. Java cung cấp hai nhóm công cụ cần phân biệt:

- **Ngữ nghĩa phép toán dấu phẩy động của ngôn ngữ:** quy định `+`, `-`, `*`, `/`, chuyển đổi kiểu và các biểu thức `float`/`double` được tính như thế nào.
- **Các hàm toán học trong thư viện:** như `sin`, `cos`, `log`, `pow`, `sqrt`, `exp`, được cung cấp bởi `Math` và `StrictMath`.

Từ Java 17, phép toán dấu phẩy động của ngôn ngữ đã trở lại chế độ **always-strict**. Tuy nhiên, điều đó không đồng nghĩa mọi hàm trong `Math` đều phải trả về cùng bit kết quả trên mọi nền tảng. Khi cần kết quả hàm toán học có thể tái hiện chặt chẽ, cần hiểu thêm hợp đồng của `StrictMath`.

## 2. Ba khái niệm không nên nhầm lẫn

| Khái niệm | Phạm vi | Ý nghĩa |
|---|---|---|
| IEEE 754 và kiểu `float`/`double` | Biểu diễn và phép toán số thực | Xác định cách mã hóa số hữu hạn, vô cực, NaN, số không có dấu và quy tắc làm tròn |
| Always-strict floating-point của Java 17 | Biểu thức dấu phẩy động trong ngôn ngữ | Không còn chế độ tính toán mở rộng tùy nền tảng; kết quả biểu thức tuân theo ngữ nghĩa dấu phẩy động Java |
| `Math` / `StrictMath` | Các hàm toán học trong thư viện | Cung cấp hàm số; mức bảo đảm về độ chính xác và khả năng tái hiện phụ thuộc đặc tả từng lớp/phương thức |

**Điểm quan trọng:** `strictfp` và `StrictMath` không phải một khái niệm.

- `strictfp` là modifier liên quan ngữ nghĩa phép toán dấu phẩy động của một lớp, interface hoặc phương thức. Từ Java 17, ngữ nghĩa always-strict đã áp dụng mặc định, vì vậy modifier này không còn tạo khác biệt thực tế.
- `StrictMath` là một lớp thư viện có các phương thức toán học. Nó vẫn có vai trò khi chương trình cần kết quả của các hàm được đặc tả theo thuật toán có khả năng tái hiện giữa các nền tảng.

Ví dụ, viết `strictfp` trên một phương thức gọi `Math.sin(x)` không biến `Math.sin` thành `StrictMath.sin`. Nếu yêu cầu là kết quả của hàm lượng giác theo hợp đồng tái hiện, phải chọn API tương ứng.

## 3. Phép toán dấu phẩy động trong Java 17: always-strict

### 3.1. Trước Java 17 và từ Java 17

Trong một số phiên bản Java trước đây, ngữ nghĩa mặc định cho phép một số phép tính trung gian dùng value set mở rộng trên phần cứng phù hợp. Modifier `strictfp` được dùng khi chương trình muốn giới hạn phép tính theo ngữ nghĩa nghiêm ngặt.

JEP 306 khôi phục ngữ nghĩa **always-strict** từ Java 17:

- Mọi biểu thức dấu phẩy động trong Java 17 đều dùng ngữ nghĩa nghiêm ngặt theo đặc tả.
- Không cần thêm `strictfp` để yêu cầu phép tính `float`/`double` có hành vi nhất quán theo ngôn ngữ.
- `strictfp` vẫn có thể xuất hiện trong mã nguồn để tương thích, nhưng không còn thay đổi cách tính; compiler có thể cảnh báo modifier này không cần thiết.

Ví dụ:

```java
public class FloatingPointDemo {
    static double calculate(double a, double b, double c) {
        return a * b + c;
    }

    public static void main(String[] args) {
        System.out.println(calculate(0.1, 0.2, 0.3));
    }
}
```

Trong Java 17, biểu thức `a * b + c` được đánh giá theo ngữ nghĩa dấu phẩy động chuẩn của Java. Chương trình không cần đánh dấu `strictfp` ở lớp hoặc phương thức để loại bỏ phép tính trung gian mở rộng.

### 3.2. Always-strict không làm số thập phân trở nên chính xác tuyệt đối

Always-strict đảm bảo ngữ nghĩa tính toán theo đặc tả, **không loại bỏ sai số biểu diễn nhị phân**:

```java
double x = 0.1;
double y = 0.2;

System.out.println(x + y);             // 0.30000000000000004
System.out.println((x + y) == 0.3);    // false
```

Kết quả này là hành vi bình thường. Việc dùng `strictfp`, `Math` hoặc `StrictMath` không biến `double` thành kiểu số thập phân chính xác.

### 3.3. Khi nào `strictfp` còn xuất hiện?

Bạn có thể gặp mã cũ:

```java
strictfp class Geometry {
    strictfp double area(double radius) {
        return Math.PI * radius * radius;
    }
}
```

Trong Java 17, `strictfp` không còn cần thiết để bảo đảm phép toán dấu phẩy động luôn-strict. Khi bảo trì mã nguồn, có thể bỏ modifier này theo chính sách của dự án, sau khi xem xét yêu cầu tương thích và quy ước code. Không cần thêm `strictfp` mới cho các lớp Java 17 chỉ để mong có kết quả giống nhau giữa máy Intel và ARM.

## 4. `Math` và `StrictMath` khác nhau ở đâu?

Cả hai đều là lớp tiện ích với các phương thức `static`, cung cấp những phép tính như:

```java
double root = Math.sqrt(2.0);
double sine = Math.sin(Math.PI / 6);
double logarithm = Math.log(10.0);
```

Các phương thức tương ứng cũng có trong `StrictMath`:

```java
double root = StrictMath.sqrt(2.0);
double sine = StrictMath.sin(StrictMath.PI / 6);
double logarithm = StrictMath.log(10.0);
```

Sự khác biệt chính nằm ở **cam kết về kết quả và quyền tối ưu hóa của implementation**.

| Tiêu chí | `Math` | `StrictMath` |
|---|---|---|
| Mục đích | Hàm toán học thuận tiện, cho phép implementation tối ưu theo nền tảng | Hàm toán học ưu tiên kết quả tái hiện theo đặc tả |
| Kết quả của các hàm được đặc tả tái hiện | Không phải mọi phương thức đều được cam kết bit-for-bit giống nhau trên mọi nền tảng | Các phương thức được đặc tả dùng thuật toán fdlibm phải cho kết quả tương ứng giống nhau giữa các implementation phù hợp |
| Tối ưu hóa | Có thể dùng thư viện native, lệnh phần cứng hoặc implementation tối ưu của runtime | Các hàm có yêu cầu tái hiện dùng thuật toán được đặc tả thay vì tùy ý chọn implementation native khác |
| Khi nên cân nhắc | Hiệu năng, tính toán thông thường, không cần bit-for-bit cross-platform cho mọi hàm | Kết quả hàm toán học cần tái hiện chặt chẽ giữa môi trường |
| Có thay thế sai số dấu phẩy động không? | Không | Không |

`Math` thường là lựa chọn mặc định tốt cho ứng dụng thông thường. `StrictMath` phù hợp khi đặc tả sản phẩm, kiểm thử hoặc thuật toán yêu cầu kết quả của hàm toán học có thể tái hiện trên nhiều nền tảng.

### 4.1. Vì sao `Math` có thể cho kết quả khác?

Một hàm như `sin(x)` không đơn giản là một phép toán dấu phẩy động cơ bản. Runtime có thể triển khai nó bằng nhiều thuật toán xấp xỉ, thư viện hệ thống hoặc lệnh chuyên biệt. Các implementation phải tuân thủ yêu cầu về độ chính xác của API, nhưng đặc tả `Math` không buộc mọi hàm phải trả cùng chuỗi bit trên tất cả nền tảng.

Vì vậy, hai máy có thể:

- Cùng nhận một giá trị `double` đầu vào.
- Cùng chạy Java 17.
- Cùng gọi `Math.sin(x)`.
- Nhưng nhận được kết quả cuối khác nhau ở một hoặc một số bit thấp, trong phạm vi cho phép của hợp đồng phương thức.

Không nên suy luận rằng mọi máy chắc chắn sẽ khác nhau; nhiều runtime có thể trả cùng kết quả. Điều cần nhớ là **không có cam kết bit-for-bit phổ quát cho mọi hàm `Math` chỉ vì Java 17 có always-strict floating-point**.

### 4.2. `StrictMath` và fdlibm

`StrictMath` được thiết kế để hỗ trợ tính di động của chương trình. Đối với các hàm được chỉ định, đặc tả dựa trên thuật toán của thư viện **fdlibm** (*Freely Distributable Math Library*) để các implementation Java có kết quả thống nhất.

Điều đó hữu ích trong những trường hợp:

- Kết quả toán học được lưu vào dữ liệu và cần so sánh lại trên máy khác.
- Các nút trong một hệ thống phân tán phải cùng tính ra một giá trị theo thuật toán.
- Bộ kiểm thử cần kết quả xác định giữa nhiều hệ điều hành/kiến trúc.
- Một ứng dụng khoa học cần quy định rõ hàm thư viện và cách tính, thay vì dựa vào implementation tùy nền tảng.

Không nên diễn giải điều này thành “mọi phương thức của `StrictMath` chính xác tuyệt đối về mặt toán học”. Nó là **hợp đồng tái hiện của phép tính dấu phẩy động**, vẫn có sai số làm tròn so với giá trị thực.

## 5. Ví dụ chọn `Math` hay `StrictMath`

### 5.1. Tính toán thông thường

Nếu chương trình chỉ cần tính chiều dài đường chéo để hiển thị:

```java
double diagonal(double width, double height) {
    return Math.sqrt(width * width + height * height);
}
```

`Math.sqrt` có hợp đồng rất chặt về độ chính xác và là lựa chọn tự nhiên. Với các hàm khác, hãy xem đặc tả từng phương thức và yêu cầu của ứng dụng; không phải bài toán nào cũng cần ép toàn bộ lời gọi thành `StrictMath`.

### 5.2. Cần kết quả hàm lượng giác tái hiện

Nếu một chương trình cần tính cùng một giá trị lượng giác trên nhiều máy và muốn dựa vào cam kết tái hiện của thư viện:

```java
static double projectedX(double radius, double angle) {
    return radius * StrictMath.cos(angle);
}
```

Trong dự án, hãy ghi rõ vì sao chọn `StrictMath` ở vị trí này. Không nên thay đổi qua lại giữa `Math.cos` và `StrictMath.cos` trong cùng một quy trình mà không có lý do, vì yêu cầu tái hiện cần được quản lý như một phần của hợp đồng tính toán.

### 5.3. Cùng một hàm, đổi namespace

```java
double a = Math.sin(1.2345);
double b = StrictMath.sin(1.2345);

System.out.println(a);
System.out.println(b);
System.out.println(Double.doubleToLongBits(a));
System.out.println(Double.doubleToLongBits(b));
```

Không nên viết bài kiểm thử với giả định `a` và `b` bắt buộc khác nhau. Một implementation có thể trả cùng giá trị. Điều có ý nghĩa là **hợp đồng API**: `StrictMath` cung cấp cam kết tái hiện phù hợp với phương thức được đặc tả; `Math` cho phép implementation tối ưu hơn trong giới hạn độ chính xác của nó.

## 6. Độ chính xác: ulp, sai số và so sánh số thực

### 6.1. ULP là gì?

**ULP** (*unit in the last place*) là khoảng cách giữa hai giá trị dấu phẩy động biểu diễn liên tiếp ở vùng đang xét. Đặc tả các hàm toán học có thể diễn đạt độ chính xác bằng số ULP so với kết quả toán học chính xác.

Ví dụ khái niệm:

- Một kết quả sai một ULP nghĩa là kết quả cách giá trị làm tròn chuẩn khoảng một bước biểu diễn ở độ lớn đó.
- Một ULP không phải một hằng số cố định cho mọi giá trị; khoảng cách giữa các số `double` thay đổi theo số mũ.
- “Trong một ULP” không có nghĩa kết quả chính xác tuyệt đối, cũng không có nghĩa mọi ứng dụng có thể dùng `==` để so sánh các kết quả gần nhau.

API `Math` và `StrictMath` nêu yêu cầu độ chính xác/monotonicity trong tài liệu từng phương thức và phần mô tả lớp. Khi một phép tính quan trọng, hãy xem hợp đồng cụ thể của hàm đó thay vì chỉ dựa vào tên lớp.

### 6.2. Không so sánh số thực bằng `==` khi muốn so gần đúng

Ví dụ:

```java
double a = 0.1 + 0.2;
double b = 0.3;

if (a == b) {
    System.out.println("Bằng nhau");
} else {
    System.out.println("Khác nhau");
}
```

Nếu nghiệp vụ chấp nhận sai số nhỏ, có thể dùng ngưỡng:

```java
static boolean nearlyEqual(double a, double b, double epsilon) {
    return Math.abs(a - b) <= epsilon;
}
```

Nhưng `epsilon` phải xuất phát từ miền giá trị và yêu cầu nghiệp vụ. Một ngưỡng cố định `1e-9` có thể phù hợp cho một bài toán, quá chặt hoặc quá lỏng ở bài toán khác.

Với giá trị rất lớn/nhỏ, có thể cân nhắc so sánh tương đối:

```java
static boolean approximatelyEqual(
        double a, double b, double absoluteTolerance, double relativeTolerance) {

    if (Double.doubleToLongBits(a) == Double.doubleToLongBits(b)) {
        return true;
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    return difference <= Math.max(
            absoluteTolerance,
            relativeTolerance * scale);
}
```

Hàm trên minh họa một chiến lược so sánh hỗn hợp absolute/relative tolerance. Trong ứng dụng thật, cần chọn tolerance phù hợp đơn vị, miền dữ liệu và quy tắc với NaN/vô cực; không sao chép các hằng số mà không hiểu yêu cầu.

### 6.3. `NaN`, vô cực và số không có dấu

Các phép toán dấu phẩy động có những giá trị đặc biệt:

```java
double nan = Double.NaN;
double positiveInfinity = Double.POSITIVE_INFINITY;
double negativeZero = -0.0;

System.out.println(Double.isNaN(nan));                    // true
System.out.println(Double.isInfinite(positiveInfinity)); // true
System.out.println(negativeZero == 0.0);                 // true
System.out.println(Double.doubleToRawLongBits(-0.0));
```

Một vài quy tắc cần nhớ:

- `NaN == NaN` là `false`; dùng `Double.isNaN(value)` để kiểm tra.
- `+0.0 == -0.0` là `true`, dù hai giá trị có bit dấu khác nhau.
- Phép chia số thực cho `0.0` có thể tạo vô cực hoặc NaN thay vì ném `ArithmeticException` như chia số nguyên.
- Khi kiểm tra kết quả tái hiện bit-for-bit, phải xác định chính sách đối với NaN, signed zero và cách chuẩn hóa bit.

`Double.doubleToLongBits` chuẩn hóa các biểu diễn NaN về một dạng NaN chuẩn; `Double.doubleToRawLongBits` giữ payload bit của NaN nếu có. Hai phương thức phục vụ mục đích khác nhau khi kiểm tra bit.

## 7. Phép toán cơ bản luôn-strict không đồng nghĩa với hàm `Math` luôn tái hiện

Hãy phân biệt một biểu thức cơ bản:

```java
double product = a * b;
double sum = product + c;
```

với lời gọi thư viện:

```java
double result = Math.sin(a);
```

Biểu thức `a * b + c` chịu ngữ nghĩa always-strict của Java 17. Lời gọi `Math.sin` còn chịu hợp đồng độ chính xác và quyền tối ưu của phương thức `Math.sin`.

Do đó, khi đọc một yêu cầu “cùng đầu vào phải có cùng kết quả”, cần hỏi rõ:

1. Yêu cầu áp dụng cho các phép toán `+ - * /` hay cho các hàm lượng giác/logarithm?
2. Cần kết quả số học theo đặc tả Java, hay cần cùng bit kết quả trên mọi nền tảng?
3. Chỉ so kết quả của một hàm, hay so cả quy trình có thứ tự phép tính, dữ liệu đầu vào và quy tắc làm tròn?
4. Có cần giữ nguyên kết quả qua các phiên bản thư viện, thuật toán hoặc dữ liệu đầu vào hay không?

Chọn `StrictMath` giải quyết phần hợp đồng hàm toán học mà nó cung cấp, nhưng không tự làm cho toàn bộ ứng dụng có tính tái hiện.

## 8. `Math.fma`: một phép toán, một lần làm tròn

Java cung cấp `Math.fma(a, b, c)` (*fused multiply-add*):

```java
double result = Math.fma(a, b, c);
```

Nó tính tích `a * b` rồi cộng `c` với **một lần làm tròn cuối cùng**, theo định nghĩa của fused multiply-add. Biểu thức thông thường:

```java
double result = a * b + c;
```

có thể làm tròn sau phép nhân và tiếp tục làm tròn sau phép cộng. Vì vậy hai cách không nhất thiết cho cùng bit kết quả.

Ví dụ minh họa khác biệt về ngữ nghĩa:

```java
static double ordinary(double a, double b, double c) {
    return a * b + c;
}

static double fused(double a, double b, double c) {
    return Math.fma(a, b, c);
}
```

Không nên tự ý thay một cách bằng cách kia nếu kết quả đã là một phần của giao thức, kiểm thử golden file hoặc mô hình số học. Nếu thuật toán yêu cầu fused multiply-add, gọi rõ `Math.fma` (hoặc `StrictMath.fma` khi phù hợp với hợp đồng thư viện cần dùng) để ý định được thể hiện trong mã.

`fma` không phải cách “tăng độ chính xác cho mọi phép tính” miễn phí: nó thay đổi quy tắc làm tròn so với hai phép toán tách rời, do đó có thể làm kết quả khác với code cũ. Hãy dùng khi thuật toán yêu cầu phép toán fused hoặc khi đã đánh giá ảnh hưởng số học.

## 9. Khi cần số thập phân chính xác: dùng `BigDecimal`

`Math` và `StrictMath` hoạt động trên các kiểu dấu phẩy động. Nếu yêu cầu nghiệp vụ là số thập phân chính xác, chẳng hạn số tiền hoặc tỷ lệ cần quy tắc làm tròn được công bố, `BigDecimal` thường là lựa chọn phù hợp hơn.

### 9.1. Tránh tạo `BigDecimal` từ literal `double`

Không nên:

```java
BigDecimal wrong = new BigDecimal(0.1);
System.out.println(wrong);
```

Constructor này nhận **giá trị nhị phân `double` đã được xấp xỉ**, rồi biểu diễn chính xác giá trị nhị phân ấy dưới dạng thập phân dài.

Nên dùng chuỗi:

```java
BigDecimal amount = new BigDecimal("0.1");
```

Hoặc khi thật sự đang có một `double` và muốn biểu diễn giá trị thập phân ngắn mà `Double.toString` trả về:

```java
BigDecimal amount = BigDecimal.valueOf(0.1);
```

Đối với dữ liệu tiền tệ, nhận đầu vào dạng chuỗi/kiểu thập phân phù hợp và xác định rõ scale, rounding mode.

### 9.2. Quy định cách làm tròn

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.995");
BigDecimal rounded = price.setScale(2, RoundingMode.HALF_UP);

System.out.println(rounded); // 20.00
```

Ở đây, quy tắc làm tròn là một phần tường minh của logic nghiệp vụ. `BigDecimal` không tự quyết định mọi quy tắc tiền tệ; chương trình vẫn phải chọn `RoundingMode` và scale phù hợp.

### 9.3. `Math.round` không thay thế `BigDecimal.setScale`

`Math.round(double)` trả về số nguyên `long` theo quy tắc của phương thức. Nó không phải công cụ tổng quát để làm tròn tiền đến hai chữ số thập phân:

```java
double amount = 19.995;
long whole = Math.round(amount);
```

Nếu cần hai chữ số thập phân, việc nhân với 100, gọi `Math.round` rồi chia lại có thể tạo thêm vấn đề biểu diễn và không diễn đạt rõ chính sách làm tròn. Hãy dùng `BigDecimal` với rounding mode đã chọn.

## 10. Tái hiện kết quả trong ứng dụng nhiều máy

Chọn `StrictMath` là một bước hữu ích, nhưng kết quả của cả ứng dụng còn phụ thuộc vào nhiều yếu tố khác.

### 10.1. Cố định đầu vào và thứ tự tính toán

Ví dụ, tổng một tập số thực có thể phụ thuộc thứ tự cộng do tính chất không kết hợp của phép cộng dấu phẩy động:

```java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

double first = (a + b) + c;
double second = a + (b + c);

System.out.println(first);  // 1.0
System.out.println(second); // Có thể là 0.0
```

Với dấu phẩy động, `(a + b) + c` không bắt buộc bằng `a + (b + c)`. Nếu tổng được tính từ collection mà thứ tự duyệt không được đảm bảo, kết quả có thể thay đổi theo nguồn dữ liệu hoặc cấu trúc collection.

Khi cần tái hiện:

- Xác định thứ tự phần tử đầu vào.
- Dùng thuật toán cộng có thứ tự được quy định.
- Không dựa vào thứ tự iteration không được API cam kết.
- Cân nhắc thuật toán cộng bù (*compensated summation*, chẳng hạn Kahan summation) nếu mục tiêu là giảm sai số; thuật toán này không thay thế việc quy định thứ tự đầu vào.

### 10.2. Cố định cách tạo số ngẫu nhiên

`Math.random()` không phải lựa chọn phù hợp nếu cần phát lại một phiên tính toán chính xác. Nếu muốn một chuỗi giả ngẫu nhiên lặp lại, hãy dùng một generator có thuật toán và seed được quy định:

```java
import java.util.Random;

Random firstRun = new Random(12345L);
Random replay = new Random(12345L);

for (int i = 0; i < 5; i++) {
    System.out.println(firstRun.nextInt() == replay.nextInt());
}
```

Với `java.util.Random`, cùng seed và cùng chuỗi lời gọi tạo cùng chuỗi kết quả theo hợp đồng của lớp. Tuy nhiên:

- Nếu thứ tự gọi khác nhau do concurrency, kết quả gán cho từng tác vụ có thể khác.
- Generator khác (`SplittableRandom`, các generator trong `java.util.random`) có hợp đồng/thuật toán khác nhau.
- Không dùng `Random` cho mục đích mật mã; dùng `SecureRandom` khi cần nguồn ngẫu nhiên bảo mật, và chấp nhận rằng nó không nhằm tạo chuỗi có thể phát lại từ seed như generator mô phỏng.

### 10.3. Cố định các yếu tố ngoài số học

Một chương trình có thể dùng `StrictMath` nhưng vẫn không tái hiện đầu ra nếu còn phụ thuộc:

- Thời gian hiện tại, timezone và quy tắc lịch.
- Locale, cách định dạng số và ký hiệu thập phân.
- Charset mặc định khi đọc/ghi file.
- Thứ tự dữ liệu từ database hoặc API.
- Dữ liệu môi trường, cấu hình, phiên bản thư viện.
- Thread scheduling, thứ tự hoàn tất tác vụ song song và race condition.
- Phiên bản thuật toán ứng dụng, dữ liệu đầu vào và chính sách rounding.

Do đó, yêu cầu tái hiện cần một **hồ sơ tính toán** đủ rõ: đầu vào, phiên bản Java, thuật toán, thư viện, thứ tự dữ liệu, quy tắc làm tròn và định dạng đầu ra.

### 10.4. Phân biệt tái hiện trong cùng Java với tái hiện giữa ngôn ngữ

`StrictMath` giúp Java implementations thống nhất kết quả theo hợp đồng của phương thức. Nó không tự bảo đảm rằng một chương trình viết bằng C, Python, JavaScript hoặc GPU sẽ cho cùng bit kết quả khi gọi một hàm toán học có tên tương tự. Mỗi ngôn ngữ/runtime có thể có:

- Kiểu dữ liệu và độ chính xác trung gian khác.
- Quy tắc làm tròn khác.
- Thư viện toán học và thuật toán khác.
- Cách xử lý NaN, signed zero hoặc exception khác.

Nếu cần so khớp kết quả giữa nhiều ngôn ngữ, phải định nghĩa một giao thức số học chung (độ rộng kiểu, cách làm tròn, hàm cụ thể, phiên bản thuật toán và biểu diễn serialization), rồi kiểm thử chéo các implementation.

## 11. Cách kiểm tra tính tái hiện một cách có ý nghĩa

### 11.1. So sánh giá trị số hay so sánh bit?

Hai phép kiểm tra khác nhau:

```java
static boolean sameNumericValue(double a, double b) {
    return a == b;
}

static boolean sameBits(double a, double b) {
    return Double.doubleToLongBits(a) == Double.doubleToLongBits(b);
}
```

- `==` coi `+0.0` và `-0.0` bằng nhau; NaN không bằng chính nó.
- `Double.doubleToLongBits` phân biệt signed zero nhưng chuẩn hóa NaN về một dạng canonical.
- `Double.doubleToRawLongBits` cho phép xem bit thô, gồm payload NaN.

Hãy chọn phép so sánh phù hợp với yêu cầu. Không nên gọi một bài kiểm thử là “bit-for-bit” nếu nó chỉ dùng `==`.

### 11.2. In bit để chẩn đoán

```java
static String bits(double value) {
    return String.format(
            "%016X",
            Double.doubleToLongBits(value));
}

public static void main(String[] args) {
    double value = StrictMath.sin(1.2345);
    System.out.println(value);
    System.out.println(bits(value));
}
```

Chuỗi hex giúp xem sự khác biệt ở mức bit. Khi so kết quả giữa hai máy, hãy ghi cả đầu vào, phiên bản runtime, nền tảng, phương thức được gọi và cách chuẩn hóa NaN nếu có.

### 11.3. Không chỉ dùng một vài ví dụ dễ

Một bộ kiểm thử số học tốt nên bao phủ:

- Giá trị bình thường ở nhiều miền độ lớn.
- Giá trị rất nhỏ/gần zero và rất lớn/gần overflow.
- Giá trị âm, signed zero, NaN và vô cực nếu phương thức cho phép.
- Điểm biên của miền hàm (ví dụ gần cực trị hoặc tiệm cận).
- Đầu vào không hợp lệ và chính sách xử lý của ứng dụng.
- Trường hợp mà sai số ULP có ý nghĩa đối với quyết định nghiệp vụ.

Với hàm toán học, hãy phân biệt kiểm thử **độ chính xác** với kiểm thử **tính tái hiện**. Một kết quả giống nhau trên nhiều máy không chứng minh nó gần giá trị toán học chính xác nhất; một kết quả có sai số nhỏ cũng không tự động chứng minh nó giống bit trên mọi máy.

## 12. Ví dụ tổng hợp: Dịch vụ tính tọa độ có yêu cầu tái hiện

Giả sử một dịch vụ tính tọa độ từ bán kính và góc, kết quả được ghi vào log và đối chiếu giữa các node. Nếu đặc tả yêu cầu dùng cùng hàm lượng giác có kết quả tái hiện trong Java, có thể viết:

```java
public final class CoordinateCalculator {
    private CoordinateCalculator() { }

    public record Point(double x, double y) { }

    public static Point fromPolar(double radius, double angleRadians) {
        if (!Double.isFinite(radius) || radius < 0.0) {
            throw new IllegalArgumentException("radius phải hữu hạn và >= 0");
        }
        if (!Double.isFinite(angleRadians)) {
            throw new IllegalArgumentException("angle phải hữu hạn");
        }

        double x = radius * StrictMath.cos(angleRadians);
        double y = radius * StrictMath.sin(angleRadians);
        return new Point(x, y);
    }

    public static void main(String[] args) {
        Point point = fromPolar(10.0, StrictMath.PI / 6.0);
        System.out.println(point);
    }
}
```

Thiết kế này làm rõ:

1. Input được xác thực trước khi tính.
2. `StrictMath` được chọn tường minh cho hai hàm lượng giác.
3. Phép nhân vẫn là phép toán dấu phẩy động theo ngữ nghĩa always-strict của Java 17.
4. Kết quả vẫn là `double`, vì vậy vẫn có sai số làm tròn; không phải giá trị hình học chính xác vô hạn.
5. Nếu ghi/đọc kết quả, cần quy định định dạng và cách serialization thay vì phụ thuộc locale hoặc định dạng mặc định.

Nếu dịch vụ cần lưu tọa độ theo một số chữ số thập phân cố định, phải bổ sung bước lượng tử hóa/rounding theo chính sách đã thống nhất. Không nên dùng `String.format` với locale mặc định làm định dạng giao thức.

## 13. Lựa chọn API theo yêu cầu

| Yêu cầu | Hướng lựa chọn |
|---|---|
| Tính toán `double` thông thường, không có yêu cầu bit-for-bit cho mọi hàm | Dùng `Math` và tuân thủ độ chính xác API |
| Cần kết quả hàm toán học tái hiện theo đặc tả Java giữa các implementation | Dùng phương thức `StrictMath` phù hợp |
| Muốn phép tính dấu phẩy động của Java 17 không phụ thuộc extended-exponent value sets | Mặc định đã được bảo đảm bởi always-strict; không cần thêm `strictfp` |
| Tính tiền hoặc giá trị thập phân cần rounding được quy định | Dùng `BigDecimal` và `RoundingMode` phù hợp |
| Cần tính fused multiply-add theo đúng một lần làm tròn | Dùng `Math.fma` hoặc API tương ứng theo yêu cầu |
| Cần so sánh gần đúng số thực | Xây dựng tolerance theo miền dữ liệu và đơn vị |
| Cần phát lại chuỗi giả ngẫu nhiên | Chọn generator có hợp đồng phù hợp, cố định seed và thứ tự gọi |
| Cần tái hiện cả quy trình phân tán | Quy định đầu vào, thứ tự, phiên bản, thuật toán, môi trường và serialization |

Không nên thay toàn bộ `Math` bằng `StrictMath` chỉ vì từ “Strict” nghe an toàn hơn. Việc lựa chọn phải xuất phát từ hợp đồng cần có và phương thức cụ thể đang sử dụng.

## 14. Các hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
|---|---|
| Java 17 always-strict nghĩa là mọi phép tính `Math` giống bit trên mọi máy | Always-strict áp dụng cho biểu thức FP của ngôn ngữ; hàm `Math` có hợp đồng riêng |
| `strictfp` và `StrictMath` giống nhau | Một bên là modifier ngôn ngữ, một bên là lớp thư viện |
| `StrictMath` luôn chính xác tuyệt đối | Nó cung cấp hợp đồng tái hiện cho các phương thức được đặc tả, vẫn có sai số dấu phẩy động |
| `Math` luôn nhanh hơn `StrictMath` | Không có bảo đảm hiệu năng tuyệt đối; phụ thuộc phương thức, JVM, CPU và implementation |
| Chuyển `Math` sang `StrictMath` sẽ làm toàn bộ ứng dụng tái hiện | Thứ tự tính, dữ liệu, concurrency, random, rounding và serialization vẫn có thể thay đổi |
| `double` có thể lưu chính xác mọi số thập phân | Nhiều phân số thập phân không biểu diễn chính xác trong nhị phân |
| `==` là cách tốt để so sánh mọi kết quả số thực | Cần phân biệt equality, tolerance và bitwise equality |
| `BigDecimal(double)` khôi phục số thập phân ban đầu | Nó biểu diễn chính xác giá trị `double` đã xấp xỉ; dùng chuỗi hoặc `BigDecimal.valueOf` khi phù hợp |
| Thêm `strictfp` vào Java 17 sẽ làm `Math.sin` giống `StrictMath.sin` | Không; phải chọn phương thức thư viện theo yêu cầu |

## 15. Bài tập thực hành

### Bài 1 — Phân biệt ngữ nghĩa phép toán và hàm thư viện

Cho hai đoạn:

```java
double a = 0.1 + 0.2;
double b = Math.sin(1.0);
```

Giải thích phần nào chịu always-strict floating-point của Java 17 và phần nào chịu hợp đồng của thư viện `Math`.

**Gợi ý:** Phép cộng trong `a` là biểu thức FP của ngôn ngữ; lời gọi `Math.sin` trong `b` là hàm thư viện có đặc tả độ chính xác/implementation riêng. `strictfp` không biến lời gọi `Math.sin` thành `StrictMath.sin`.

### Bài 2 — Chọn hàm cho một yêu cầu tái hiện

Một ứng dụng chạy trên nhiều loại máy cần tính `sin(angle)` và lưu kết quả vào dữ liệu để so sánh giữa các node Java.

- Nên cân nhắc `Math.sin` hay `StrictMath.sin`?
- Vì sao chọn `StrictMath` vẫn không đủ để đảm bảo toàn bộ workflow giống nhau?

**Đáp án định hướng:** Chọn `StrictMath.sin` nếu yêu cầu là kết quả hàm lượng giác tái hiện theo hợp đồng Java. Đồng thời phải cố định đầu vào, thứ tự phép tính, phiên bản logic, cách làm tròn, cách xử lý NaN/signed zero và serialization.

### Bài 3 — So sánh số thực

Viết phương thức so sánh hai số `double` theo absolute tolerance, sau đó giải thích vì sao không thể chọn cùng một tolerance cho mọi miền giá trị.

**Gợi ý:**

```java
static boolean close(double a, double b, double epsilon) {
    return Double.isFinite(a)
            && Double.isFinite(b)
            && Math.abs(a - b) <= epsilon;
}
```

Đây chỉ là một chính sách đơn giản; cần quyết định riêng cho NaN, vô cực, signed zero và miền độ lớn.

### Bài 4 — Chọn `BigDecimal` cho tiền

Giải thích sự khác nhau giữa:

```java
new BigDecimal(0.1)
new BigDecimal("0.1")
BigDecimal.valueOf(0.1)
```

**Đáp án định hướng:** Constructor nhận `double` chuyển chính xác giá trị nhị phân đang có; constructor chuỗi chuyển biểu diễn thập phân được chỉ định; `valueOf` dùng biểu diễn chuỗi chuẩn của `double`. Với dữ liệu tiền tệ, ưu tiên nhận giá trị thập phân từ nguồn phù hợp và chỉ rõ scale/rounding mode.

### Bài 5 — Tái hiện tổng một tập số

Giả sử một dịch vụ cộng các giá trị trong `HashSet<Double>`. Vì sao việc dùng `StrictMath` cho từng phép tính không tự bảo đảm tổng cuối cùng giống nhau?

**Đáp án định hướng:** Thứ tự duyệt `HashSet` không phải thứ tự nghiệp vụ được bảo đảm; phép cộng số thực không kết hợp nên thứ tự cộng có thể làm kết quả khác. Cần xác định thứ tự dữ liệu và thuật toán cộng.

## 16. Tài liệu chính thức để tra cứu

- [JEP 306 — Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306): thay đổi ngữ nghĩa dấu phẩy động từ Java 17.
- [Java Language Specification 17 — `15.4 FP-strict Expressions](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.4): định nghĩa biểu thức FP-strict trong Java 17.
- [Java Language Specification 17 — `4.2.3 Floating-Point Types, Formats, and Values](https://docs.oracle.com/javase/specs/jls/se17/html/jls-4.html#jls-4.2.3): các kiểu `float`, `double` và giá trị dấu phẩy động.
- [Java SE 17 API — `Math`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html): độ chính xác, monotonicity, quyền tối ưu implementation và các phương thức toán học.
- [Java SE 17 API — `StrictMath`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StrictMath.html): các hàm được đặc tả nhằm hỗ trợ kết quả tái hiện giữa các nền tảng.
- [Java SE 17 API — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): số thập phân độ chính xác tùy ý và các quy tắc rounding.

**Ghi nhớ:** Java 17 đã áp dụng always-strict cho phép toán dấu phẩy động của ngôn ngữ. `Math` cho phép implementation tối ưu trong phạm vi hợp đồng độ chính xác của nó; `StrictMath` là lựa chọn khi cần kết quả hàm toán học có cam kết tái hiện phù hợp. Còn để tái hiện toàn bộ ứng dụng, phải kiểm soát cả đầu vào, thứ tự tính, thuật toán, làm tròn, random và môi trường dữ liệu.
