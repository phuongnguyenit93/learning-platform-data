# Sai số dấu phẩy động, tràn số và phép toán kiểm tra giới hạn

> Phạm vi: ngữ nghĩa số của Java 27, các API số học hiện hành và cách chọn kiểu biểu diễn phù hợp. Các ví dụ dùng Java không cần preview feature.

## 1. Vì sao cần quan tâm đến độ chính xác và giới hạn số?

Các phép tính số trong chương trình có thể sai theo nhiều cách khác nhau:

- **Sai số biểu diễn dấu phẩy động**: một số thập phân hữu hạn như `0.1` không nhất thiết có biểu diễn nhị phân hữu hạn. Giá trị được lưu gần đúng.
- **Sai số làm tròn**: kết quả trung gian được làm tròn sau phép toán; nhiều phép tính liên tiếp có thể tích lũy sai số.
- **Tràn số nguyên (integer overflow)**: kết quả vượt giới hạn của `int` hoặc `long`, nhưng phép toán nguyên thủy vẫn trả về giá trị theo quy tắc bit của kiểu.
- **Tràn hoặc hụt miền dấu phẩy động**: kết quả quá lớn có thể thành vô cực; kết quả quá nhỏ có thể thành số dưới chuẩn hoặc 0.
- **Chuyển đổi kiểu mất thông tin**: ép kiểu hẹp có thể bỏ các bit cao hoặc làm tròn giá trị dấu phẩy động.

Những vấn đề này xuất hiện trong tính tiền, thống kê, đo lường, xử lý ảnh, tính kích thước bộ nhớ, phân trang, thời gian và thuật toán khoa học. Chọn kiểu dữ liệu đúng và xác định rõ cách xử lý giới hạn là một phần của thiết kế nghiệp vụ.

## 2. Cách Java biểu diễn số dấu phẩy động

Java có hai kiểu dấu phẩy động nguyên thủy:

| Kiểu | Kích thước | Định dạng | Độ chính xác thập phân xấp xỉ |
| --- | ---: | --- | ---: |
| `float` | 32 bit | IEEE 754 binary32 | khoảng 6–7 chữ số có nghĩa |
| `double` | 64 bit | IEEE 754 binary64 | khoảng 15–16 chữ số có nghĩa |

Mỗi giá trị hữu hạn được biểu diễn bằng bit dấu, phần mũ và phần định trị (significand). Vì hệ thống dùng cơ số 2, nhiều phân số viết gọn ở cơ số 10 có biểu diễn lặp vô hạn ở cơ số 2. Máy chỉ lưu được số bit hữu hạn nên phải chọn một giá trị gần nhất theo quy tắc làm tròn của định dạng.

Ví dụ:

~~~
double a = 0.1;
double b = 0.2;
double c = 0.3;

System.out.println(a + b);       // thường hiển thị 0.30000000000000004
System.out.println(a + b == c);  // false
~~~

`0.1`, `0.2` và `0.3` không có biểu diễn binary64 chính xác. Khi cộng hai giá trị gần đúng, kết quả được làm tròn thêm một lần; kết quả có thể khác giá trị `0.3` được biểu diễn riêng.

Đây không phải lỗi riêng của Java. Đây là hệ quả của biểu diễn số dấu phẩy động nhị phân hữu hạn. Không nên kết luận rằng `double` luôn không chính xác: nhiều giá trị, phép tính và kết quả được biểu diễn chính xác; điều cần hiểu là độ chính xác hữu hạn và quy tắc làm tròn.

### 2.1. Độ chính xác không đồng nghĩa với số chữ số sau dấu phẩy

`double` có khoảng 15–16 chữ số có nghĩa, không phải luôn có 15–16 chữ số thập phân chính xác ở mọi độ lớn. Khi độ lớn của số tăng, khoảng cách giữa hai giá trị `double` liên tiếp cũng tăng. Vì vậy, cộng một số rất nhỏ vào một số rất lớn có thể không làm thay đổi giá trị đã lưu:

~~~
double large = 1e16;
double small = 1.0;

System.out.println(large + small == large); // true
~~~

Ứng dụng không được giả định rằng mọi số nguyên trong mọi khoảng đều biểu diễn chính xác bằng `double`. Binary64 biểu diễn chính xác tất cả số nguyên trong khoảng từ \(-2^{53}\) đến \(2^{53}\); bên ngoài khoảng đó, không phải mọi số nguyên liên tiếp đều có thể được phân biệt.

### 2.2. Quy tắc dấu phẩy động trong Java hiện đại

Java dùng ngữ nghĩa dấu phẩy động dựa trên IEEE 754. Từ Java 17, JEP 306 khôi phục ngữ nghĩa dấu phẩy động luôn nghiêm ngặt trên mọi nền tảng; mã chạy trên Java 27 không cần modifier `strictfp` để có kết quả theo ngữ nghĩa này.

Các tài liệu cũ thường khuyên thêm `strictfp` để tránh khác biệt giữa các kiến trúc. Modifier đó không còn thay đổi cách đánh giá biểu thức dấu phẩy động trong Java hiện đại. Khi bảo trì mã mới, hãy dựa vào ngữ nghĩa hiện hành của Java và đặc tả, không sao chép hướng dẫn dành cho Java trước phiên bản 17.

## 3. Sai số làm tròn và tích lũy sai số

Mỗi phép toán dấu phẩy động có thể tạo ra kết quả gần đúng. Sai số có thể tăng hoặc giảm qua các phép toán tiếp theo.

### 3.1. Phép cộng không có tính kết hợp tuyệt đối

Trong số thực toán học, `(a + b) + c` và `a + (b + c)` có cùng kết quả. Với dấu phẩy động, mỗi thứ tự có thể làm tròn ở thời điểm khác nhau:

~~~
double a = 1e16;
double b = -1e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // có thể là 0.0
~~~

Thứ tự tính toán có thể ảnh hưởng kết quả. Điều này quan trọng trong phép cộng hàng triệu số, xử lý song song, thống kê và thuật toán số.

### 3.2. Triệt tiêu chữ số có nghĩa

Khi trừ hai số gần bằng nhau, các chữ số có nghĩa đầu tiên có thể triệt tiêu. Phần sai số tương đối của đầu vào khi đó có thể chiếm tỷ lệ lớn trong kết quả.

Ví dụ, biểu thức toán học tương đương nhưng cách tính khác nhau có thể cho độ ổn định số khác nhau. Với thuật toán khoa học, hãy tìm công thức số ổn định, phân tích miền đầu vào và kiểm thử bằng dữ liệu có độ lớn/độ lệch đại diện. Đổi sang `BigDecimal` không tự động sửa mọi vấn đề của thuật toán; kiểu dữ liệu chính xác cũng cần công thức và độ chính xác phù hợp.

### 3.3. Tính tổng nhiều giá trị

Nếu phải cộng nhiều số dấu phẩy động, thứ tự cộng và độ lớn tương đối của các phần tử có thể làm thay đổi sai số. Có thể:

- Cộng các giá trị theo thứ tự có kiểm soát, chẳng hạn nhóm các số có độ lớn gần nhau.
- Dùng thuật toán cộng bù (compensated summation), ví dụ Kahan summation, khi cần giảm sai số tích lũy.
- Chọn kiểu số thập phân hoặc số nguyên có scale cố định nếu bài toán yêu cầu quy tắc thập phân chính xác.
- Kiểm thử với tập dữ liệu lớn, giá trị âm/dương xen kẽ và trường hợp triệt tiêu.

Java cung cấp `Math.fma(a, b, c)` để tính tích `a * b` cộng `c` với một lần làm tròn cuối cùng theo ngữ nghĩa fused multiply-add. Trong một số công thức số, `fma` giảm sai số so với thực hiện phép nhân và phép cộng riêng. Nó không thay thế việc phân tích độ ổn định của thuật toán.

## 4. Giá trị đặc biệt: vô cực, NaN, số không có dấu và số dưới chuẩn

Kiểu `float` và `double` có các giá trị đặc biệt ngoài các số hữu hạn thông thường.

| Giá trị | Ý nghĩa | Cách kiểm tra |
| --- | --- | --- |
| `Double.POSITIVE_INFINITY` | Dương vô cực | `Double.isInfinite(value)` |
| `Double.NEGATIVE_INFINITY` | Âm vô cực | `Double.isInfinite(value)` |
| `Double.NaN` | Not a Number, kết quả không phải số | `Double.isNaN(value)` |
| `+0.0`, `-0.0` | Hai dạng số không có dấu khác nhau ở mức bit | `Double.doubleToRawLongBits(value)` khi cần phân biệt |
| Số dưới chuẩn (subnormal) | Số hữu hạn rất gần 0 với độ chính xác giảm dần | `Double.MIN_VALUE` là số dương khác 0 nhỏ nhất; `Double.MIN_NORMAL` là số chuẩn dương nhỏ nhất |

### 4.1. Chia cho 0 khác nhau giữa số nguyên và dấu phẩy động

~~~
int whole = 10;
// int result = whole / 0; // ném ArithmeticException

double decimal = 10.0;
System.out.println(decimal / 0.0);   // Infinity
System.out.println(0.0 / 0.0);       // NaN
System.out.println(-10.0 / 0.0);    // -Infinity
~~~

Phép chia số nguyên cho 0 ném `ArithmeticException`. Phép chia `float`/`double` cho số 0 tuân theo quy tắc dấu phẩy động và có thể tạo ra vô cực hoặc NaN.

### 4.2. NaN có quy tắc so sánh đặc biệt

Mọi phép so sánh quan hệ với NaN đều không cho kết quả đúng; ngay cả `NaN == NaN` cũng là `false`. Dùng `Double.isNaN` hoặc `Float.isNaN` để kiểm tra:

~~~
double value = Math.sqrt(-1.0);

System.out.println(value == Double.NaN); // false
System.out.println(Double.isNaN(value)); // true
~~~

Nếu dữ liệu đầu vào không được phép chứa NaN hoặc vô cực, hãy kiểm tra ngay tại biên hệ thống:

~~~
static double requireFinite(String name, double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException(
                name + " must be finite");
    }
    return value;
}
~~~

`Double.isFinite` trả về `false` cho NaN và cả hai giá trị vô cực. Kiểm tra này hữu ích trước khi lưu dữ liệu, tính toán tiếp hoặc trả kết quả qua API.

### 4.3. Số không có dấu

`+0.0 == -0.0` trả về `true`, nhưng hai giá trị có bit dấu khác nhau. Chẳng hạn, nghịch đảo của chúng lần lượt là dương vô cực và âm vô cực. Hầu hết logic nghiệp vụ không cần phân biệt hai số không; thuật toán số học, đồ họa hoặc xử lý dấu có thể cần.

Nếu cần phân biệt chính xác mẫu bit, dùng `Double.doubleToRawLongBits` hoặc `Float.floatToRawIntBits`. Chỉ dùng phép so sánh bit khi hợp đồng của thuật toán thực sự yêu cầu, bởi nó khác với so sánh giá trị số.

### 4.4. Underflow và subnormal

Khi một kết quả quá nhỏ để biểu diễn thành số chuẩn, Java có thể biểu diễn nó dưới dạng subnormal. Nếu còn nhỏ hơn giới hạn đó, kết quả có thể làm tròn về `0.0` hoặc `-0.0`. Điều này có thể khiến một đại lượng nhỏ biến mất trong tính toán tiếp theo. Khi thuật toán phụ thuộc vào các giá trị gần 0, cần xác định miền đầu vào, ngưỡng chấp nhận và cách xử lý underflow.

## 5. So sánh số dấu phẩy động

Không nên dùng `==` để kiểm tra hai kết quả tính toán độc lập có “gần bằng nhau” hay không, trừ khi hợp đồng yêu cầu bằng nhau chính xác. Cách so sánh phải dựa trên ý nghĩa của đại lượng.

### 5.1. Sai số tuyệt đối

Sai số tuyệt đối là:

\(|a-b|\)

Có thể chấp nhận hai giá trị nếu sai số không vượt ngưỡng tuyệt đối đã định:

\(|a-b| \leq \varepsilon\)

Cách này phù hợp khi miền giá trị tập trung quanh một độ lớn đã biết. Nếu dữ liệu có thể dao động từ rất nhỏ đến rất lớn, một ngưỡng tuyệt đối duy nhất thường không phù hợp.

### 5.2. Sai số tương đối kết hợp sai số tuyệt đối

Một cách kiểm tra phổ biến là chấp nhận nếu sai số tuyệt đối nhỏ hoặc sai số tương đối so với độ lớn hai số đủ nhỏ:

\(|a-b| \leq \max(\varepsilon_{abs},\varepsilon_{rel}\cdot\max(|a|,|b|))\)

Ví dụ:

~~~
static boolean nearlyEqual(
        double a,
        double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (absoluteTolerance < 0.0
            || relativeTolerance < 0.0
            || relativeTolerance > 1.0
            || !Double.isFinite(absoluteTolerance)
            || !Double.isFinite(relativeTolerance)) {
        throw new IllegalArgumentException("Invalid tolerance");
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return a == b; // xử lý vô cực cùng dấu; NaN vẫn false
    }

    if (a == b) {
        return true;
    }

    double difference = Math.abs(a - b);
    double scale = Math.max(Math.abs(a), Math.abs(b));
    double tolerance = Math.max(
            absoluteTolerance,
            relativeTolerance * scale);

    return difference <= tolerance;
}
~~~

Hai ngưỡng phải được chọn theo đơn vị, độ chính xác đo và yêu cầu của bài toán. Ví dụ giới hạn `relativeTolerance` trong khoảng từ 0 đến 1 để ngưỡng tương đối không vượt quá độ lớn tham chiếu. Không có một hằng số epsilon phù hợp cho mọi ứng dụng. Với kiểm thử thuật toán, hãy chọn ngưỡng từ sai số được phép của miền đầu vào, không chọn chỉ vì một giá trị thường thấy trên Internet.

## 6. Tràn số nguyên trong Java

Các kiểu số nguyên nguyên thủy có miền biểu diễn hữu hạn:

| Kiểu | Miền giá trị |
| --- | --- |
| `byte` | -128 đến 127 |
| `short` | -32.768 đến 32.767 |
| `int` | -2.147.483.648 đến 2.147.483.647 |
| `long` | -2^63 đến 2^63 - 1 |

Phép cộng, trừ và nhân trên `int`/`long` không tự động ném ngoại lệ khi tràn. Kết quả giữ các bit thấp theo độ rộng kiểu số nguyên, tương đương phép tính modulo \(2^{32}\) hoặc \(2^{64}\) rồi diễn giải theo kiểu có dấu. Các phép toán số học trên `byte`, `short` và `char` thường được nâng kiểu thành `int` trước khi tính; khi gán kết quả về kiểu hẹp, cần ép kiểu rõ ràng hoặc dùng phép gán kết hợp với hiểu biết về bước thu hẹp tự động.

~~~
int max = Integer.MAX_VALUE;
System.out.println(max + 1); // -2147483648

int min = Integer.MIN_VALUE;
System.out.println(Math.abs(min)); // vẫn là số âm

long wrapped = Long.MAX_VALUE + 1L;
System.out.println(wrapped); // -9223372036854775808
~~~

Đặc biệt, `Math.abs(Integer.MIN_VALUE)` và `Math.abs(Long.MIN_VALUE)` không thể tạo ra số dương tương ứng vì miền kiểu không có giá trị dương đủ lớn. Kết quả vẫn là giá trị âm ban đầu.

### 6.1. Các trường hợp tràn dễ bỏ sót

- **Nhân trước khi chuyển kiểu**: `(long) (a * b)` vẫn nhân bằng `int` trước, rồi mới chuyển kết quả đã tràn sang `long`. Hãy chuyển một toán hạng trước phép nhân: `(long) a * b`.
- **Tăng kích thước**: `capacity * 2`, `count + 1` hoặc `offset + length` có thể tràn trước khi cấp phát hoặc truy cập mảng.
- **Giá trị biên khi chia**: `Integer.MIN_VALUE / -1` trả về `Integer.MIN_VALUE` do tràn; phép chia này không ném ngoại lệ. Chia cho 0 mới ném `ArithmeticException`.
- **Ép kiểu hẹp**: chuyển `long` sang `int`, hoặc `int` sang `short`/`byte`, có thể làm mất các bit cao. Ép kiểu không tự kiểm tra miền giá trị.
- **Phép cộng có dấu**: cộng một số dương vào số gần `MAX_VALUE` hoặc trừ một số âm khỏi số gần `MIN_VALUE` có thể tràn.

Ví dụ lỗi do ép kiểu quá muộn:

~~~
int width = 100_000;
int height = 100_000;

long wrong = width * height;        // int tràn trước khi gán
long correct = (long) width * height;

System.out.println(wrong);   // giá trị sai do tràn int
System.out.println(correct); // 10000000000
~~~

## 7. Dùng phép toán kiểm tra tràn với Math

Khi kết quả phải nằm trong miền `int` hoặc `long`, ưu tiên các phương thức kiểm tra tràn có sẵn:

| Phương thức | Tác dụng |
| --- | --- |
| `Math.addExact(a, b)` | Cộng và ném `ArithmeticException` nếu tràn |
| `Math.subtractExact(a, b)` | Trừ và kiểm tra tràn |
| `Math.multiplyExact(a, b)` | Nhân và kiểm tra tràn |
| `Math.incrementExact(a)` | Tăng 1 và kiểm tra tràn |
| `Math.decrementExact(a)` | Giảm 1 và kiểm tra tràn |
| `Math.negateExact(a)` | Đổi dấu và kiểm tra trường hợp không biểu diễn được |
| `Math.toIntExact(value)` | Chuyển `long` sang `int`, ném ngoại lệ nếu ngoài miền |

Các phương thức có overload phù hợp cho `int` hoặc `long` theo API. Ví dụ:

~~~
int quantity = 1_500_000;
int unitSize = 2_000;

try {
    int total = Math.multiplyExact(quantity, unitSize);
    System.out.println(total);
} catch (ArithmeticException ex) {
    System.out.println("Kết quả vượt miền int");
}
~~~

Nếu nghiệp vụ yêu cầu giá trị hợp lệ trong miền `long`, hãy dùng overload `long` và vẫn kiểm tra tràn. Ví dụ tính offset:

~~~
static long pageOffset(int page, int pageSize) {
    if (page < 0 || pageSize <= 0) {
        throw new IllegalArgumentException(
                "page must be >= 0 and pageSize must be > 0");
    }

    return Math.multiplyExact((long) page, (long) pageSize);
}
~~~

Không nên bắt `ArithmeticException` rồi trả về một con số mặc định tùy tiện. Hãy quyết định rõ nghiệp vụ cần từ chối đầu vào, trả lỗi, dùng miền số rộng hơn hay dùng kiểu số có độ lớn tùy ý.

### 7.1. Chuyển đổi kiểu có kiểm tra

Nếu nhận `long` nhưng API downstream chỉ chấp nhận `int`, dùng:

~~~
long requestedId = 42L;
int id = Math.toIntExact(requestedId);
~~~

Nếu `requestedId` nằm ngoài miền `int`, phương thức ném `ArithmeticException`. Với chuyển đổi dấu phẩy động sang số nguyên, phép ép kiểu bỏ phần lẻ theo hướng về 0; NaN chuyển thành 0; giá trị quá lớn hoặc vô cực được đưa về giới hạn nhỏ nhất/lớn nhất của kiểu đích. Không coi phép ép kiểu là bước validate. Hãy kiểm tra giá trị hữu hạn và miền hợp lệ trước khi chuyển đổi.

## 8. Chọn kiểu số theo yêu cầu của bài toán

| Bài toán | Kiểu thường phù hợp | Lý do và lưu ý |
| --- | --- | --- |
| Đo lường, mô phỏng, đồ họa, thống kê | `double` | Dải giá trị rộng, phần cứng hỗ trợ tốt; cần chấp nhận sai số và thiết kế tolerance |
| Dữ liệu dấu phẩy động cần ít bộ nhớ, khối lượng lớn | `float` | Tiết kiệm bộ nhớ nhưng độ chính xác thấp hơn; chỉ chọn khi đã đánh giá sai số |
| Bộ đếm, số lượng, chỉ số, kích thước | `int` hoặc `long` | Số nguyên chính xác trong miền; dùng phép toán exact nếu vượt giới hạn phải bị phát hiện |
| Số nguyên lớn hơn miền `long` | `BigInteger` | Độ lớn tùy ý, chi phí bộ nhớ và tính toán cao hơn |
| Tiền, thuế, tỷ lệ thập phân theo quy tắc nghiệp vụ | `BigDecimal` hoặc số nguyên theo đơn vị nhỏ nhất | Tránh sai số nhị phân; phải quy định scale và rounding |
| ID, mã định danh | Kiểu nguyên hoặc kiểu định danh chuyên biệt | Không dùng `float`/`double` vì có thể mất khả năng phân biệt số nguyên lớn |

### 8.1. Tiền tệ và số thập phân

Không dùng `float` hoặc `double` làm biểu diễn tiền nếu yêu cầu nghiệp vụ cần kết quả thập phân xác định. Có thể dùng `BigDecimal`, hoặc lưu số nguyên theo đơn vị nhỏ nhất (ví dụ xu) nếu loại tiền và quy tắc scale của miền nghiệp vụ cho phép.

`BigDecimal` biểu diễn số thập phân với độ chính xác tùy ý và scale rõ ràng. Khi tạo từ chuỗi, giá trị thập phân được giữ theo chuỗi:

~~~
import java.math.BigDecimal;
import java.math.RoundingMode;

BigDecimal price = new BigDecimal("19.99");
BigDecimal quantity = new BigDecimal("3");
BigDecimal subtotal = price.multiply(quantity);

BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal tax = subtotal.multiply(taxRate)
        .setScale(2, RoundingMode.HALF_UP);

BigDecimal total = subtotal.add(tax);
System.out.println(total); // 64.77
~~~

`RoundingMode.HALF_UP` chỉ là ví dụ. Luật làm tròn phải lấy từ quy tắc kế toán, thuế, tiền tệ hoặc hợp đồng của hệ thống. Một số nghiệp vụ yêu cầu `HALF_EVEN`, `DOWN`, `CEILING` hoặc làm tròn ở cấp dòng hàng thay vì tổng hóa đơn.

### 8.2. Tránh tạo BigDecimal từ literal double

~~~
BigDecimal wrong = new BigDecimal(0.1);
BigDecimal decimal = new BigDecimal("0.1");
BigDecimal fromValue = BigDecimal.valueOf(0.1);

System.out.println(wrong);   // biểu diễn chính xác giá trị double gần 0.1
System.out.println(decimal); // 0.1
System.out.println(fromValue); // 0.1
~~~

`new BigDecimal(double)` giữ chính xác giá trị nhị phân gần đúng đã có trong `double`; vì vậy nó có thể tạo ra nhiều chữ số thập phân bất ngờ. Dùng constructor nhận `String` khi nguồn dữ liệu là số thập phân, hoặc `BigDecimal.valueOf` khi muốn chuyển từ biểu diễn chuẩn của `double`.

### 8.3. Scale, chia và so sánh BigDecimal

Phép chia thập phân có thể tạo ra chuỗi vô hạn, ví dụ `1/3`. Khi đó cần chỉ định scale và `RoundingMode`:

~~~
BigDecimal third = BigDecimal.ONE.divide(
        BigDecimal.valueOf(3),
        6,
        RoundingMode.HALF_UP);
~~~

`BigDecimal.equals` xét cả giá trị và scale: `2.0` và `2.00` không bằng nhau theo `equals`. Nếu cần so sánh giá trị số bất kể scale, dùng `compareTo`:

~~~
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");

System.out.println(x.equals(y));         // false
System.out.println(x.compareTo(y) == 0); // true
~~~

Nếu dùng `BigDecimal` làm key của `HashMap` hoặc phần tử `HashSet`, cần chú ý hợp đồng `equals`/`hashCode` và chuẩn hóa scale khi miền nghiệp vụ yêu cầu các biểu diễn tương đương được coi là cùng một key.

## 9. Dùng BigInteger khi miền số nguyên không cố định

`BigInteger` biểu diễn số nguyên có độ lớn tùy ý, không bị giới hạn ở 32 hoặc 64 bit. Nó phù hợp cho số đếm cực lớn, số học chính xác, mã hóa hoặc thuật toán cần miền số vượt `long`.

~~~
import java.math.BigInteger;

BigInteger a = new BigInteger("9223372036854775808");
BigInteger b = BigInteger.valueOf(2);

BigInteger result = a.multiply(b);
System.out.println(result);
~~~

Các phép toán trên `BigInteger` trả về đối tượng mới vì kiểu này bất biến. Chi phí tính toán tăng theo kích thước số; không dùng `BigInteger` mặc định cho mọi bộ đếm nếu `long` đã đáp ứng miền nghiệp vụ. Khi chuyển về kiểu nguyên thủy, dùng `intValueExact()` hoặc `longValueExact()` để phát hiện mất thông tin; `intValue()`/`longValue()` có thể giữ các bit thấp và không phải phép chuyển đổi có kiểm tra.

## 10. Thiết kế phép tính an toàn ở biên hệ thống

Khi nhận số từ JSON, HTTP, database, tệp hoặc người dùng, hãy xác định rõ:

1. Kiểu dữ liệu và đơn vị đo: byte hay kilobyte, giây hay mili giây, đồng hay xu.
2. Miền hợp lệ của đầu vào: giá trị âm có được phép không, giới hạn tối đa là bao nhiêu.
3. Quy tắc làm tròn: làm tròn tại mỗi bước hay chỉ ở kết quả cuối, scale bao nhiêu.
4. Hành vi khi vượt miền: từ chối, báo lỗi, dùng kiểu rộng hơn hay dùng số học độ lớn tùy ý.
5. Hành vi khi gặp NaN/vô cực: từ chối, đánh dấu dữ liệu không hợp lệ hay có ý nghĩa chuyên biệt trong thuật toán.
6. Kiểm tra sau phép tính: kết quả có còn hữu hạn, không âm và nằm trong miền nghiệp vụ không.

Ví dụ, khi tính kích thước buffer từ số phần tử và kích thước mỗi phần tử, kiểm tra số âm và dùng phép nhân exact trước khi cấp phát. Khi tính tiền, phân biệt số tiền, tỷ lệ và số lượng; quy định điểm làm tròn. Khi tính tỷ lệ phần trăm từ số đo, kiểm tra mẫu số bằng 0 và xử lý trường hợp dữ liệu không hữu hạn.

Đừng âm thầm bão hòa hoặc clamp kết quả nếu nghiệp vụ chưa quy định. Bão hòa có thể phù hợp với một số bộ đếm hoặc tín hiệu, nhưng với số tiền, giới hạn tài khoản hoặc chỉ số bảo mật, việc biến lỗi tràn thành giá trị biên có thể che giấu lỗi nghiêm trọng.

## 11. Ví dụ tổng hợp: tính tổng an toàn

Ví dụ sau tính tổng các số nguyên trong một danh sách, đồng thời kiểm tra dữ liệu null và tràn `long`:

~~~
import java.util.List;
import java.util.Objects;

public final class SafeTotals {
    private SafeTotals() {
    }

    public static long sum(List<Long> values) {
        Objects.requireNonNull(values, "values");

        long total = 0L;
        for (Long value : values) {
            if (value == null) {
                throw new IllegalArgumentException(
                        "values must not contain null");
            }

            total = Math.addExact(total, value);
        }
        return total;
    }

    public static void main(String[] args) {
        var values = List.of(10L, 20L, 30L);
        System.out.println(sum(values)); // 60
    }
}
~~~

Nếu tổng vượt miền `long`, `Math.addExact` ném `ArithmeticException` tại phép cộng gây tràn. Lớp gọi có thể chuyển ngoại lệ thành lỗi đầu vào hoặc lỗi nghiệp vụ phù hợp. Nếu miền hợp lệ của ứng dụng thực sự có thể vượt `long`, hãy thay đổi hợp đồng để dùng `BigInteger` thay vì bắt ngoại lệ rồi tiếp tục với tổng đã sai.

## 12. Những lỗi thường gặp và cách xử lý

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| So sánh kết quả `double` bằng `==` dù kết quả đến từ phép tính gần đúng | Test hoặc nhánh điều kiện không ổn định theo sai số | Dùng tolerance theo miền nghiệp vụ hoặc biểu diễn chính xác hơn |
| Dùng `double` để lưu tiền | Sai số nhị phân và làm tròn không theo quy tắc kế toán | Dùng `BigDecimal`/đơn vị nhỏ nhất và quy định rounding |
| Giả định `int`/`long` tự ném lỗi khi tràn | Giá trị âm hoặc giá trị sai tiếp tục lan truyền | Dùng `Math.*Exact`, kiểm tra miền hoặc `BigInteger` |
| Ép `(long) (a * b)` sau khi nhân `int` | Kết quả đã tràn trước khi chuyển kiểu | Ép một toán hạng sang `long` trước phép nhân hoặc dùng `multiplyExact` |
| Dùng `Math.abs` với `MIN_VALUE` | Kết quả vẫn âm | Dùng `negateExact` khi cần phát hiện, hoặc thiết kế miền dữ liệu phù hợp |
| Không kiểm tra NaN/vô cực | Dữ liệu không hợp lệ lan qua tính toán hoặc API | Dùng `Double.isFinite`/`Float.isFinite` tại biên |
| Tạo `BigDecimal` bằng `new BigDecimal(0.1)` | Giữ sai số nhị phân của `double` | Dùng chuỗi thập phân hoặc `BigDecimal.valueOf` |
| Chia `BigDecimal` không chỉ định scale khi kết quả tuần hoàn | Ném `ArithmeticException` | Chỉ định scale và `RoundingMode` |
| Dùng `intValue()`/`longValue()` để thu hẹp `BigInteger` | Mất các bit cao | Dùng `intValueExact()`/`longValueExact()` |
| Dùng một epsilon cố định cho mọi độ lớn | Có thể quá lỏng hoặc quá chặt | Kết hợp sai số tuyệt đối/tương đối theo miền và đơn vị |

## 13. Checklist khi thiết kế và review phép tính

- [ ] Đã chọn `float`, `double`, `int`, `long`, `BigInteger` hoặc `BigDecimal` theo yêu cầu độ chính xác và miền giá trị.
- [ ] Đã xác định đơn vị, scale và giới hạn hợp lệ của dữ liệu.
- [ ] Không giả định số thập phân hữu hạn luôn biểu diễn chính xác bằng `float`/`double`.
- [ ] Không dùng `==` cho hai kết quả dấu phẩy động gần đúng khi yêu cầu là “gần bằng”.
- [ ] Đã xử lý NaN, vô cực, số không có dấu hoặc subnormal nếu thuật toán có thể gặp.
- [ ] Đã tính đến sai số tích lũy và thứ tự phép toán.
- [ ] Đã dùng `Math.addExact`, `subtractExact`, `multiplyExact` hoặc API exact tương ứng khi tràn phải được phát hiện.
- [ ] Đã tránh tràn trước khi ép kiểu rộng hơn.
- [ ] Đã kiểm tra chuyển đổi kiểu hẹp và giá trị ngoài miền.
- [ ] Với tiền, đã quy định scale, điểm làm tròn và cách so sánh `BigDecimal`.
- [ ] Với số nguyên lớn, đã dùng các phương thức chuyển đổi exact khi quay về kiểu nguyên thủy.
- [ ] Đã kiểm thử các giá trị biên: `MIN_VALUE`, `MAX_VALUE`, 0, số rất lớn/rất nhỏ, NaN và vô cực khi thích hợp.

## 14. Nguồn tài liệu chính thức

- [Java Language Specification, Java SE 27 — Types, Values, and Variables](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html) — các kiểu nguyên thủy, kiểu dấu phẩy động, biểu diễn và chuyển đổi.
- [Java Language Specification, Java SE 27 — Numeric Types and Operations](https://docs.oracle.com/javase/specs/jls/se27/html/jls-4.html#jls-4.2) — miền giá trị và ngữ nghĩa số.
- [Java Language Specification, Java SE 27 — Expressions](https://docs.oracle.com/javase/specs/jls/se27/html/jls-15.html) — ngữ nghĩa biểu thức và phép toán.
- [Java SE 27 API — Math](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Math.html) — `addExact`, `subtractExact`, `multiplyExact`, `toIntExact`, `fma` và các hàm số học.
- [Java SE 27 API — Double](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/Double.html) — hằng số, NaN, vô cực, kiểm tra hữu hạn và chuyển đổi bit.
- [Java SE 27 API — BigDecimal](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigDecimal.html) — số thập phân chính xác, scale, rounding và phép chia.
- [Java SE 27 API — BigInteger](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/math/BigInteger.html) — số nguyên có độ lớn tùy ý và chuyển đổi exact.
- [JEP 306: Restore Always-Strict Floating-Point Semantics](https://openjdk.org/jeps/306) — ngữ nghĩa dấu phẩy động thống nhất từ Java 17.

Khi quyết định kiểu dữ liệu, hãy ghi rõ độ chính xác, miền hợp lệ, đơn vị và cách xử lý vượt giới hạn trong hợp đồng của thành phần. Điều đó giúp người bảo trì hiểu vì sao một phép tính được thực hiện bằng kiểu cụ thể và khi nào kết quả phải bị từ chối.
