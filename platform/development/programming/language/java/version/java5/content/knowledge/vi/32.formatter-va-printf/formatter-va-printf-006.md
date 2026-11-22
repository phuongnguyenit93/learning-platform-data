# Định dạng số nguyên, số thực và BigDecimal

## 1. Tách giá trị số khỏi cách trình bày

Cùng giá trị 1234.5 có thể được trình bày thành `1234.50`, `1,234.50` hoặc `1.23e+03`. Định dạng chọn cách **hiển thị**, không tự thay đổi kiểu, độ chính xác hay quy tắc tính toán của dữ liệu gốc.

Trong họ API `Formatter`/`printf`, conversion phải tương thích với kiểu đối số:

```java
System.out.printf(Locale.ROOT, "Count: %d%n", 12);
System.out.printf(Locale.ROOT, "Price: %.2f%n", 12.5);
```

Đoạn minh họa cần đặt trong một phương thức và import `java.util.Locale`. Nó in:

```text
Count: 12
Price: 12.50
```

Không suy luận rằng `%d` chấp nhận mọi giá trị “trông như số nguyên”. Một Double có giá trị 12.0 vẫn không phải đối số hợp lệ cho `%d`.

Bài dùng các API còn phù hợp trên Java hiện đại, với ví dụ chạy bằng Java 17+. Quy tắc làm tròn BigDecimal dùng enum `RoundingMode`, không dùng các hằng số nguyên làm tròn đã cũ.

## 2. Chọn conversion theo kiểu và mục tiêu

| Đối số | Conversion phù hợp tiêu biểu | Mục tiêu |
| --- | --- | --- |
| byte, short, int, long và các kiểu đóng hộp tương ứng | d, o, x/X | Số nguyên thập phân, bát phân, hex |
| BigInteger | d, o, x/X | Số nguyên lớn |
| float/Float, double/Double | f, e/E, g/G, a/A | Các dạng số thực |
| BigDecimal | f, e/E, g/G | Số thập phân chính xác theo giá trị đã lưu |

`char`/Character không thuộc nhóm số nguyên của các conversion d/o/x chỉ vì Java có thể dùng char trong một số biểu thức số học.

`BigDecimal` không được hỗ trợ bởi `%a`. `Number` là lớp cha chung cũng không có nghĩa mọi lớp con Number được mọi conversion số chấp nhận.

Những quy tắc kiểu được định nghĩa trong [Formatter](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Formatter.html). Khi sai kiểu hoặc sai tổ hợp cờ/precision, lỗi thường được phát hiện lúc chạy.

## 3. Số nguyên: cơ số, dấu và độ rộng

### Dạng thập phân, bát phân và hex

```java
String text = String.format(Locale.ROOT,
        "dec=%d oct=%o hex=%x", 26, 26, 26);
```

`text` bằng `"dec=26 oct=32 hex=1a"`.

Cờ `#` yêu cầu dạng thay thế khi được hỗ trợ:

```java
String text = String.format(Locale.ROOT,
        "oct=%#o hex=%#x", 26, 26);
```

Kết quả là `"oct=032 hex=0x1a"`.

Chữ X tạo dạng hex chữ hoa tương ứng. Các ký hiệu cơ số phục vụ trình bày; chúng không đổi biến số nguyên gốc thành một kiểu dữ liệu khác.

### Width là tối thiểu, không phải số chữ số tối đa

```java
String text = String.format(Locale.ROOT, "[%4d]", 123456);
```

Kết quả vẫn là `"[123456]"`, không cắt bớt hai chữ số.

Cờ 0 đệm số 0 khi có width:

```java
String text = String.format(Locale.ROOT,
        "positive=%08d negative=%08d", 42, -42);
```

Kết quả là:

```text
positive=00000042 negative=-0000042
```

Width tính cả dấu; các số 0 được đặt theo quy tắc của conversion, không đơn giản nối vào trước mọi ký tự. Nếu thêm dấu dương bằng `+`, dấu đó cũng chiếm vị trí trong width.

### Số âm dạng hex phụ thuộc kiểu

Với kiểu nguyên cố định như int, hex của số âm biểu diễn theo độ rộng của kiểu. Với BigInteger, số âm có cách biểu diễn dấu khác.

```java
String text = String.format(Locale.ROOT,
        "int=%x big=%x", -1, BigInteger.valueOf(-1));
```

Cần import `java.math.BigInteger`. Kết quả là `"int=ffffffff big=-1"`.

Không áp dụng quy tắc “số âm luôn thêm dấu trừ trong mọi cơ số” cho mọi kiểu đối số.

### Số nguyên không dùng precision thập phân

`%.2d` không phải cách in số nguyên với ít nhất hai chữ số. Dùng `%02d` nếu mục tiêu là đệm 0 tới width 2. Nếu mục tiêu là kiểm tra miền số chỉ có hai chữ số, cần kiểm tra dữ liệu riêng; định dạng không giới hạn miền giá trị.

## 4. Số thực: f, e, g và a khác nhau ở đâu?

### f — dạng thập phân

```java
String text = String.format(Locale.ROOT, "%.2f", 12.5);
```

Kết quả là `"12.50"`. Với f, precision là số chữ số sau dấu phân cách thập phân. Không truyền precision thì mặc định là 6.

`%.0f` định dạng không có chữ số phần lẻ, nhưng vẫn là trình bày một đối số thuộc nhóm số thực; nó không làm đối số biến thành Integer.

### e — dạng khoa học

```java
String text = String.format(Locale.ROOT, "%.2e", 1234.5);
```

Kết quả là `"1.23e+03"`. Precision 2 áp dụng cho số chữ số sau dấu phân cách của phần định trị. Chữ số trước dấu phân cách vẫn tồn tại, nên ở đây có ba chữ số có nghĩa.

Dùng E nếu muốn ký hiệu số mũ viết hoa theo conversion tương ứng.

### g — dạng tổng quát theo chữ số có nghĩa

```java
String text = String.format(Locale.ROOT,
        "%.3g / %.3g", 12.5, 12345.0);
```

Kết quả là `"12.5 / 1.23e+04"`.

Với g, precision là tổng số chữ số có nghĩa của độ lớn kết quả sau làm tròn. Nó chọn dạng thập phân hoặc khoa học theo độ lớn đã làm tròn và precision; không phải lúc nào cũng là “N chữ số sau dấu phẩy”.

Precision mặc định của g là 6; precision bằng 0 được xử lý thành 1 theo hợp đồng. Nếu cần chính xác hai chữ số sau dấu phân cách để trình bày một khoản tiền, f phù hợp với ý định đó hơn g.

### a — số thực hex

```java
String text = String.format(Locale.ROOT, "%a", 1.5);
```

Kết quả là `"0x1.8p0"`. Chữ p biểu diễn số mũ theo cơ số 2 trong dạng số thực hex.

Dạng này hữu ích khi khảo sát biểu diễn số thực nhị phân; không thường dùng cho báo cáo phục vụ người dùng. Không dùng a cho BigDecimal.

## 5. Precision của định dạng không sửa sai số đầu vào

Float và Double lưu giá trị theo nhị phân. Nhiều phân số thập phân không có biểu diễn nhị phân hữu hạn.

```java
double total = 0.1 + 0.2;
String shortText = String.format(Locale.ROOT, "%.2f", total);
```

`shortText` có thể phục vụ hiển thị `"0.30"`, nhưng biến total vẫn giữ kết quả tính toán double của nó. In gọn không làm phép tính trở thành số thập phân chính xác.

Một khác biệt dễ thấy là:

```java
String text = String.format(Locale.ROOT,
        "float=%.9f double=%.9f", 0.1f, 0.1);
```

Kết quả:

```text
float=0.100000001 double=0.100000000
```

Đối số float được đưa qua quy tắc định dạng số thực, và precision hiển thị có thể làm lộ việc giá trị float ban đầu khác giá trị double ban đầu.

Đừng dùng một con số hiển thị ngắn làm bằng chứng hai giá trị tính toán hoàn toàn giống nhau. Ngược lại, cũng không cần in rất nhiều chữ số nếu hợp đồng trình bày chỉ yêu cầu hai chữ số; điều cần giữ rõ là ranh giới giữa dữ liệu và output.

Double còn có NaN, Infinity và dấu âm của zero. Chúng có cách biểu diễn theo Formatter, không được tự hiểu thành số 0 thông thường. Nếu miền nghiệp vụ chỉ chấp nhận số hữu hạn, kiểm tra điều kiện ấy trước khi định dạng.

## 6. BigDecimal: giữ số thập phân, không ép qua double

Tạo BigDecimal từ chuỗi số thập phân khi chuỗi đó là nguồn dữ liệu mong muốn:

```java
BigDecimal amount = new BigDecimal("1234.567");
String text = String.format(Locale.ROOT, "%.2f", amount);
```

Cần import `java.math.BigDecimal`. Kết quả là `"1234.57"`, còn amount vẫn biểu diễn `1234.567`.

Không cần gọi `amount.doubleValue()` để dùng f. Làm vậy có thể đưa giá trị qua một miền số có độ chính xác hữu hạn rồi mới định dạng, mất lợi ích của việc dùng BigDecimal.

Theo [BigDecimal](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html), lớp này biểu diễn số thập phân bất biến với unscaled value và scale. Chính giá trị đã được tạo/lưu mới là cơ sở cho định dạng.

### new BigDecimal(double) khác tạo từ chuỗi

```java
BigDecimal fromDouble = new BigDecimal(0.1);
BigDecimal fromText = new BigDecimal("0.1");
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
```

`fromDouble` phản ánh chính xác giá trị nhị phân của double 0.1 khi đổi sang BigDecimal, nên không bằng về trị số với số thập phân 0.1 mong muốn.

`valueOf(0.1)` dùng biểu diễn chuỗi chuẩn của double để tạo BigDecimal, nên trong ví dụ này cho giá trị thập phân 0.1. Nó không thể khôi phục mọi ý định đã mất trong tính toán double trước đó.

Ví dụ, `BigDecimal.valueOf(0.1 + 0.2)` vẫn phản ánh kết quả double đã tính ra, không tự trở thành BigDecimal chính xác 0.3 theo ý định ban đầu.

### Scale của dữ liệu và precision của Formatter khác nhau

Một BigDecimal `new BigDecimal("12.500")` có scale 3. Nhưng:

- `%.2f` in hai chữ số phần lẻ.
- `%.4f` in bốn chữ số phần lẻ.
- Cả hai không sửa scale của đối tượng gốc.

Nếu cần giữ nguyên biểu diễn thập phân hoặc tránh dạng số mũ, xem `toString()` và `toPlainString()` theo đúng mục tiêu. Chẳng hạn BigDecimal tạo từ `"1E+6"` có thể in `1E+6` bằng toString, còn toPlainString cho `1000000`.

Đó là các lựa chọn chuyển thành chuỗi, không phải các khuôn Locale có dấu phân nhóm hay số chữ số cố định.

## 7. Làm tròn hiển thị và làm tròn nghiệp vụ

Formatter có quy tắc làm tròn riêng cho các conversion số, chẳng hạn f dùng quy tắc half-up khi cần làm tròn theo precision. Chuỗi khuôn không có tham số chọn tùy ý RoundingMode.

Nếu nghiệp vụ yêu cầu HALF_EVEN, DOWN hoặc một chế độ cụ thể khác, hãy tạo giá trị đã được chuẩn hóa bằng BigDecimal trước rồi mới trình bày.

```java
BigDecimal raw = new BigDecimal("2.345");
BigDecimal rounded = raw.setScale(2, RoundingMode.HALF_EVEN);
String text = String.format(Locale.ROOT, "%.2f", rounded);
```

Cần import `java.math.RoundingMode`. Kết quả là `"2.34"`.

Trong khi đó, định dạng trực tiếp raw bằng `%.2f` cho `"2.35"`. Hai kết quả phản ánh hai chính sách khác nhau, không phải Formatter tự biết quy tắc nghiệp vụ cần dùng.

`setScale` trả đối tượng kết quả; BigDecimal bất biến. Gọi `raw.setScale(...)` rồi bỏ kết quả không làm raw thay đổi.

Các chế độ làm tròn có ý nghĩa cụ thể được định nghĩa tại [RoundingMode](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html). Không mặc định mọi tổ chức dùng cùng một quy tắc chỉ vì cùng hiển thị hai chữ số.

### Tránh làm tròn hai lần ngoài ý muốn

Nếu nghiệp vụ yêu cầu làm tròn một lần ở bước cuối, đừng tự làm tròn giá trị trung gian rồi lại rút precision thêm khi hiển thị mà không đánh giá kết quả.

Nên xác định rõ:

1. Giá trị được tính ở độ chính xác nào.
2. Bước nào được làm tròn theo quy tắc nghiệp vụ.
3. Giá trị nào được lưu/trao đổi.
4. Chuỗi hiển thị có chỉ trình bày giá trị đã chuẩn hóa không.

## 8. Locale, cờ và hình dạng output số

Một số cờ thường dùng:

| Khuôn | Mục đích |
| --- | --- |
| %08d | Số nguyên, width 8, đệm 0 |
| %+d | Hiện dấu dương hoặc âm |
| %,d | Phân nhóm chữ số nguyên theo locale |
| %,.2f | Phân nhóm và hai chữ số phần lẻ |
| %(.2f | Đặt giá trị âm trong ngoặc khi hợp lệ |
| %-12.2f | Căn trái trong width tối thiểu 12 |

Dấu phân cách là vấn đề locale:

```java
String us = String.format(Locale.US, "%,.2f", 1234.5);
String de = String.format(Locale.GERMANY, "%,.2f", 1234.5);
```

Kết quả:

```text
US: 1,234.50
DE: 1.234,50
```

Hai dòng trên mô tả giá trị hai chuỗi khi được in kèm nhãn. Với bài kiểm tra hoặc định dạng cho máy, truyền locale tường minh để tránh kết quả phụ thuộc máy chạy.

Không phải mọi cờ số đều hợp lệ với mọi conversion. Ví dụ dấu phân nhóm `,` không được tùy ý dùng cùng e; cờ `#` cũng có quy tắc riêng theo f/e/g/a và nhóm số nguyên.

Không dùng một chuỗi số đã định dạng theo locale như dữ liệu trung gian cho phép tính. Khi cần trao đổi dữ liệu máy đọc, xác định riêng định dạng và hợp đồng parse.

## 9. Chương trình số nguyên và số thực

Lưu thành `NumericFormattingDemo.java`:

```java
import java.math.BigInteger;
import java.util.Locale;

public class NumericFormattingDemo {
    public static void main(String[] args) {
        System.out.printf(Locale.ROOT,
                "dec=%d oct=%#o hex=%#x%n", 26, 26, 26);

        System.out.printf(Locale.ROOT,
                "positive=%08d negative=%08d%n", 42, -42);

        System.out.printf(Locale.ROOT,
                "int=%x big=%x%n", -1, BigInteger.valueOf(-1));

        System.out.printf(Locale.ROOT,
                "fixed=%.2f scientific=%.2e%n", 1234.5, 1234.5);

        System.out.printf(Locale.ROOT,
                "general=%.3g / %.3g hexFloat=%a%n",
                12.5, 12345.0, 1.5);

        System.out.printf(Locale.ROOT,
                "float=%.9f double=%.9f%n", 0.1f, 0.1);

        System.out.printf(Locale.ROOT,
                "special=%f / %f / %.2f%n",
                Double.NaN, Double.POSITIVE_INFINITY, -0.0);

        System.out.printf(Locale.US,
                "US: %,.2f%n", 1234.5);
        System.out.printf(Locale.GERMANY,
                "DE: %,.2f%n", 1234.5);
    }
}
```

Chạy:

```shell
javac NumericFormattingDemo.java
java NumericFormattingDemo
```

Stdout:

```text
dec=26 oct=032 hex=0x1a
positive=00000042 negative=-0000042
int=ffffffff big=-1
fixed=1234.50 scientific=1.23e+03
general=12.5 / 1.23e+04 hexFloat=0x1.8p0
float=0.100000001 double=0.100000000
special=NaN / Infinity / -0.00
US: 1,234.50
DE: 1.234,50
```

## 10. Chương trình BigDecimal và chính sách làm tròn

Lưu thành `DecimalFormattingDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.IllegalFormatException;
import java.util.Locale;

public class DecimalFormattingDemo {
    private static void showError(
            String label, String pattern, Object value) {
        try {
            String result = String.format(Locale.ROOT, pattern, value);
            System.out.println(label + ": " + result);
        } catch (IllegalFormatException e) {
            System.out.println(label + ": "
                    + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        BigDecimal raw = new BigDecimal("2.345");
        BigDecimal even = raw.setScale(2, RoundingMode.HALF_EVEN);

        System.out.printf(Locale.ROOT,
                "Direct format: %.2f%n", raw);
        System.out.printf(Locale.ROOT,
                "HALF_EVEN first: %.2f%n", even);
        System.out.println("Raw unchanged: " + raw.toPlainString());

        BigDecimal carried = new BigDecimal("999.995");
        System.out.printf(Locale.ROOT,
                "Carry: %.2f%n", carried);

        BigDecimal binary = new BigDecimal(0.1);
        BigDecimal decimal = new BigDecimal("0.1");
        BigDecimal viaValueOf = BigDecimal.valueOf(0.1);

        System.out.println("Double constructor equals decimal value: "
                + (binary.compareTo(decimal) == 0));
        System.out.println("valueOf equals decimal value: "
                + (viaValueOf.compareTo(decimal) == 0));
        System.out.println("valueOf after double arithmetic: "
                + BigDecimal.valueOf(0.1 + 0.2).toPlainString());

        BigDecimal scaled = new BigDecimal("12.500");
        System.out.printf(Locale.ROOT,
                "Two places: %.2f / four places: %.4f%n",
                scaled, scaled);
        System.out.println("Original scale: " + scaled.scale());

        BigDecimal exponent = new BigDecimal("1E+6");
        System.out.println("toString: " + exponent);
        System.out.println("toPlainString: " + exponent.toPlainString());

        showError("decimal with d", "%d", raw);
        showError("integer with f", "%f", 12);
        showError("integer precision", "%.2d", 12);
        showError("decimal with a", "%a", raw);
        showError("grouping with e", "%,e", 12.5);
    }
}
```

Chạy:

```shell
javac DecimalFormattingDemo.java
java DecimalFormattingDemo
```

Stdout:

```text
Direct format: 2.35
HALF_EVEN first: 2.34
Raw unchanged: 2.345
Carry: 1000.00
Double constructor equals decimal value: false
valueOf equals decimal value: true
valueOf after double arithmetic: 0.30000000000000004
Two places: 12.50 / four places: 12.5000
Original scale: 3
toString: 1E+6
toPlainString: 1000000
decimal with d: IllegalFormatConversionException
integer with f: IllegalFormatConversionException
integer precision: IllegalFormatPrecisionException
decimal with a: IllegalFormatConversionException
grouping with e: FormatFlagsConversionMismatchException
```

Dòng Carry cho thấy làm tròn có thể tăng cả phần nguyên. Đặt width nhỏ không ngăn kết quả tăng độ dài.

Các lỗi ở cuối được bắt chỉ để minh họa hợp đồng kiểu/khuôn. Trong ứng dụng, cần sửa khuôn hoặc kiểu dữ liệu phù hợp thay vì che lỗi bằng chuỗi mặc định.

## 11. Những lỗi chọn công cụ cần tránh

- Ép BigDecimal qua double chỉ để printf nhận được: f đã hỗ trợ BigDecimal.
- Dùng `%.2f` như quy tắc làm tròn nghiệp vụ toàn hệ thống: nó chỉ định dạng theo hợp đồng Formatter.
- Dùng `%d` để parse chuỗi số hoặc chuyển double thành int: định dạng không thực hiện những chuyển đổi đó.
- Nghĩ width buộc số không vượt một số chữ số: cần kiểm tra miền giá trị riêng.
- Dùng `%g` khi thật sự cần số chữ số phần lẻ cố định.
- Dùng locale mặc định cho output cần tái lập.
- So sánh giá trị bằng chuỗi đã định dạng: nhiều giá trị khác nhau có thể cùng được làm tròn thành một chuỗi.

Nếu mục tiêu là tiền tệ có ký hiệu đơn vị, quy tắc trình bày theo vùng hoặc một mẫu thập phân tùy chỉnh phức tạp, có thể cần NumberFormat/DecimalFormat theo hợp đồng riêng. Không nên tự suy ra những quy tắc đó chỉ từ `%,.2f`.

## 12. Tự kiểm tra

**Double 12.0 có dùng được với %d không?**  
Không. Conversion số nguyên không tự nhận Double.

**Precision 3 của e và g có giống nhau không?**  
Không. e dùng ba chữ số sau dấu phân cách của phần định trị; g dùng ba chữ số có nghĩa cho độ lớn kết quả.

**In BigDecimal bằng %.2f có sửa scale của nó không?**  
Không. Nó tạo biểu diễn để hiển thị; đối tượng gốc bất biến.

**BigDecimal.valueOf có xóa sai số của mọi phép tính double trước đó không?**  
Không. Nó bắt đầu từ giá trị double đã có và biểu diễn chuỗi của giá trị ấy.

**Nếu nghiệp vụ yêu cầu HALF_EVEN thì làm gì?**  
Tạo kết quả BigDecimal với RoundingMode phù hợp ở bước nghiệp vụ, rồi trình bày giá trị đó bằng khuôn nhất quán.

Chọn đúng ba lớp quyết định: kiểu dữ liệu giữ giá trị nào, quy tắc tính/làm tròn tạo kết quả nào, và Formatter trình bày kết quả đó ra sao.
