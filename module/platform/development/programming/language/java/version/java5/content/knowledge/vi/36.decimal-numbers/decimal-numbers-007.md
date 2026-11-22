# Tạo BigDecimal từ chuỗi và BigDecimal.valueOf

## 1. Điểm xuất phát quyết định dữ liệu được giữ lại

Muốn tính toán thập phân chính xác, hãy quan tâm **đường đi của dữ liệu trước khi tạo BigDecimal**.

Nếu nguồn là văn bản `"0.1"`, `new BigDecimal("0.1")` giữ đúng giá trị một phần mười. Nếu trước đó dữ liệu đã được chuyển thành `double`, ta đang có một giá trị dấu phẩy động nhị phân; chuyển nó sang `BigDecimal` sau đó không thể tự khôi phục mọi thông tin ban đầu.

Ba cách dưới đây có hợp đồng khác nhau:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = BigDecimal.valueOf(0.1);
BigDecimal c = new BigDecimal(0.1);
```

- `a` được tạo từ các chữ số trong chuỗi.
- `b` được tạo từ biểu diễn chuỗi chuẩn của giá trị `double`, theo `Double.toString`.
- `c` biểu diễn chính xác giá trị nhị phân đang nằm trong `double`, nên có thể xuất hiện một dãy thập phân dài.

`new BigDecimal(double)` có mục đích riêng và không phải một API bị loại bỏ. Tuy nhiên, nếu ý định là nhập một số thập phân nghiệp vụ từ văn bản, đi thẳng từ chuỗi thường diễn đạt đúng yêu cầu hơn.

## 2. Tạo trực tiếp từ chuỗi

`new BigDecimal(String)` phù hợp khi nguồn dữ liệu có dạng số thập phân bằng văn bản: ô nhập liệu đã chuẩn hóa, trường dữ liệu, cấu hình hoặc hằng số trong mã.

Ví dụ minh họa trong một phương thức:

```java
BigDecimal unitPrice = new BigDecimal("125000.50");
BigDecimal discountRate = new BigDecimal("0.075");
BigDecimal negativeAdjustment = new BigDecimal("-12.30");
BigDecimal exponentForm = new BigDecimal("1.25E+3");
```

Không có bước trung gian `double`, nên các chữ số thập phân được giữ theo đầu vào. Constructor này không tự giới hạn số chữ số theo `MathContext`; nếu dùng overload nhận `MathContext`, phải xem đó là một yêu cầu làm tròn riêng.

### Các số 0 cuối và scale

`new BigDecimal("12.3400")` giữ scale bằng 4; `new BigDecimal("12.34")` có scale bằng 2. Hai đối tượng bằng nhau về giá trị số nhưng không bằng nhau theo `equals`, vì `equals` còn xét scale.

Với chuỗi số mũ, scale còn phụ thuộc số mũ. `"1.25E+3"` là giá trị 1250 với scale bằng -1. Constructor không đơn giản đếm mọi ký tự sau dấu chấm rồi coi đó là scale cuối cùng.

`BigDecimal` cũng không phải kho lưu nguyên văn đầu vào. Dấu cộng đầu chuỗi, cách viết số mũ, các số 0 đứng trước hoặc chữ `e`/`E` không nhất thiết được tái tạo nguyên dạng khi xuất. Nếu cần bảo toàn đúng chuỗi người dùng gõ, hãy lưu chuỗi đó riêng.

### Chuỗi phải tuân theo cú pháp số của API

Trong cú pháp này, dấu chấm `.` là dấu thập phân; `"1,25"`, `"1,234.56"`, `"12 đồng"` không phải đầu vào hợp lệ của constructor. Khoảng trắng bao quanh cũng không được tự bỏ qua.

Dữ liệu hiển thị theo vùng miền cần được phân tích hoặc chuẩn hóa theo một hợp đồng xác định trước. Không thay tất cả dấu phẩy thành dấu chấm một cách tùy ý: `"1,234"` có thể mang nghĩa 1.234 hoặc 1234 tùy quy ước nguồn.

Đầu vào sai cú pháp gây `NumberFormatException`; `null` gây `NullPointerException`. Hãy xử lý tại nơi tiếp nhận dữ liệu và trả lỗi rõ ràng. Đừng biến một giá trị không hợp lệ thành số 0 nếu yêu cầu nghiệp vụ không quy định như vậy.

## 3. Ba overload valueOf thường gặp

| Phương thức | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `valueOf(long val)` | Tạo số nguyên chính xác với scale 0 | `valueOf(125L)` → 125 |
| `valueOf(long unscaledVal, int scale)` | Tạo `unscaledVal × 10^(-scale)` | `valueOf(125L, 2)` → 1.25 |
| `valueOf(double val)` | Dùng biểu diễn chuỗi chuẩn của `double` | `valueOf(0.1)` → 0.1 |

### valueOf(long): giữ số nguyên

Nếu số đếm hoặc số nguyên đã có kiểu `long`, không cần chuyển sang `double` rồi mới tạo `BigDecimal`. Bước chuyển qua `double` có thể làm mất các chữ số khi số nguyên lớn.

```java
long count = 9_007_199_254_740_993L;
BigDecimal exactCount = BigDecimal.valueOf(count);
```

`exactCount` giữ nguyên giá trị số nguyên đó. Ngoài phạm vi `long`, chuỗi hoặc `BigInteger` là hướng phù hợp tùy nguồn dữ liệu.

### valueOf(long, scale): đơn vị nhỏ nhất

Khi hệ thống lưu tiền hoặc đại lượng theo số nguyên đơn vị nhỏ nhất, có thể đặt dấu thập phân bằng scale:

```java
long cents = 12345L;
BigDecimal amount = BigDecimal.valueOf(cents, 2); // 123.45
```

Đây không phải `12345` rồi “thêm hai số 0”. Công thức là `12345 × 10^-2`. Số lượng vị trí thập phân phải đến từ hợp đồng đơn vị; không phải mọi loại tiền hoặc đại lượng đều có scale 2.

### valueOf(double): thuận tiện khi nguồn vốn đã là double

Với `0.1`, `Double.toString(0.1)` là `"0.1"`; bởi vậy `BigDecimal.valueOf(0.1)` có biểu diễn gọn, khác `new BigDecimal(0.1)`.

Điều này không có nghĩa là `valueOf` sửa mọi sai số:

```java
BigDecimal afterBinaryCalculation = BigDecimal.valueOf(0.1 + 0.2);
// 0.30000000000000004
```

Phép cộng đã chạy bằng `double` trước khi `valueOf` được gọi. Muốn tính toán thập phân từ đầu, tạo các toán hạng thập phân trước:

```java
BigDecimal decimalCalculation =
        new BigDecimal("0.1").add(new BigDecimal("0.2")); // 0.3
```

`valueOf(double)` không chấp nhận `NaN` hoặc vô cực; các giá trị đó gây `NumberFormatException`. `BigDecimal` không có biểu diễn riêng cho chúng.

## 4. Literal và overload cũng ảnh hưởng biểu diễn

Dấu `L` và dấu chấm trong literal có ý nghĩa:

```java
BigDecimal integerInput = BigDecimal.valueOf(100L);   // 100, scale 0
BigDecimal doubleInput = BigDecimal.valueOf(100.0);   // 100.0, scale 1
BigDecimal textInput = new BigDecimal("100.00");      // 100.00, scale 2
```

Cả ba cùng giá trị số nhưng khác scale. Tương tự, literal `12.3400` kiểu `double` không lưu rằng mã nguồn có bốn vị trí thập phân; `valueOf(12.3400)` cho `12.34`, scale 2.

Không có overload `BigDecimal.valueOf(String)`; chuỗi dùng constructor `new BigDecimal(text)`. Đồng thời, hãy so sánh giá trị đối tượng bằng `equals` hoặc `compareTo` theo yêu cầu; không dựa vào `==` hay việc một factory có thể dùng lại đối tượng.

Nếu nguồn là `float`, lời gọi `valueOf(floatVariable)` sẽ nâng kiểu sang `double`. Đừng coi đây là đường giữ nguyên chuỗi thập phân ban đầu của `float`. Với nguồn thập phân cần chính xác, giữ dữ liệu văn bản ngay từ lúc tiếp nhận là lựa chọn rõ ràng hơn.

## 5. Chương trình kiểm chứng đầy đủ

Lưu thành `DecimalCreationDemo.java`. Ví dụ dùng API có trên Java 17 trở lên.

```java
import java.math.BigDecimal;

public class DecimalCreationDemo {
    private static void show(String label, BigDecimal value) {
        System.out.println(label + " = " + value.toPlainString()
                + " (scale=" + value.scale() + ")");
    }

    public static void main(String[] args) {
        BigDecimal fromText = new BigDecimal("0.1");
        BigDecimal fromDouble = BigDecimal.valueOf(0.1);
        BigDecimal exactBinaryValue = new BigDecimal(0.1);

        show("text", fromText);
        show("valueOf(double)", fromDouble);
        show("constructor(double)", exactBinaryValue);
        System.out.println("text.equals(valueOf) = "
                + fromText.equals(fromDouble));

        show("text with zeros", new BigDecimal("12.3400"));
        show("valueOf literal", BigDecimal.valueOf(12.3400));
        show("whole long", BigDecimal.valueOf(100L));
        show("whole double", BigDecimal.valueOf(100.0));
        show("minor units", BigDecimal.valueOf(12345L, 2));

        show("double sum", BigDecimal.valueOf(0.1 + 0.2));
        show("decimal sum",
                new BigDecimal("0.1").add(new BigDecimal("0.2")));

        show("exponent", new BigDecimal("1.25E+3"));

        try {
            new BigDecimal("1,25");
        } catch (NumberFormatException ex) {
            System.out.println("comma input: invalid");
        }
        try {
            BigDecimal.valueOf(Double.NaN);
        } catch (NumberFormatException ex) {
            System.out.println("NaN input: invalid");
        }
    }
}
```

Lệnh:

```shell
javac --release 17 -encoding UTF-8 DecimalCreationDemo.java
java DecimalCreationDemo
```

Stdout:

```text
text = 0.1 (scale=1)
valueOf(double) = 0.1 (scale=1)
constructor(double) = 0.1000000000000000055511151231257827021181583404541015625 (scale=55)
text.equals(valueOf) = true
text with zeros = 12.3400 (scale=4)
valueOf literal = 12.34 (scale=2)
whole long = 100 (scale=0)
whole double = 100.0 (scale=1)
minor units = 123.45 (scale=2)
double sum = 0.30000000000000004 (scale=17)
decimal sum = 0.3 (scale=1)
exponent = 1250 (scale=-1)
comma input: invalid
NaN input: invalid
```

Chương trình dùng `toPlainString()` để dễ quan sát giá trị, kể cả khi scale âm. Phương thức xuất chuỗi này không thay đổi scale của đối tượng.

Dòng `constructor(double)` giải thích chính xác điều đang được chuyển: giá trị nhị phân gần một phần mười, chứ không phải ý định nhập chuỗi `"0.1"`. Hai dòng tính tổng chỉ ra vì sao thời điểm chuyển đổi quan trọng hơn việc chọn factory ở cuối phép tính.

## 6. Quy tắc chọn theo nguồn dữ liệu

- **Nguồn là chuỗi số thập phân hợp lệ:** dùng `new BigDecimal(text)`; tránh `Double.parseDouble(text)` làm bước trung gian.
- **Nguồn là số nguyên:** dùng `valueOf(long)`, hoặc constructor từ `BigInteger` nếu miền giá trị lớn hơn.
- **Nguồn là số nguyên có đơn vị thập phân đã xác định:** dùng `valueOf(unscaled, scale)`.
- **Nguồn bắt buộc là double:** `valueOf(double)` thường phù hợp khi muốn biểu diễn theo chuỗi chuẩn của `double`; chấp nhận rằng những chữ số đã mất trước đó không thể phục hồi.
- **Cần khảo sát chính xác giá trị nhị phân đang được double biểu diễn:** `new BigDecimal(double)` có thể là lựa chọn có chủ đích.

Nếu một trình đọc dữ liệu đã biến số thập phân thành `double` trước khi mã nghiệp vụ nhận được nó, đổi sang `valueOf` ở lớp sau chưa giải quyết tận gốc yêu cầu bảo toàn chữ số. Cần cấu hình đường đọc để nhận `BigDecimal` trực tiếp hoặc giữ chuỗi, tùy hợp đồng của thư viện.

## 7. Tự kiểm tra đường đi dữ liệu

1. Muốn giữ số `"45.600"` và scale 3, chọn cách nào?
2. `BigDecimal.valueOf(45600L, 3)` có giá trị gì?
3. Chuyển `double` đã qua nhiều phép tính sang `valueOf` có khôi phục kết quả thập phân mong muốn không?

Đáp án:

1. `new BigDecimal("45.600")`. Chuyển qua `double` sẽ làm mất thông tin số 0 cuối của văn bản.
2. `45.600`, scale 3, vì `45600 × 10^-3`.
3. Không. Nó chuyển giá trị `double` hiện tại theo hợp đồng của factory; để bảo toàn phép tính thập phân, cần dùng toán hạng `BigDecimal` từ đầu.

Tham khảo: [BigDecimal trong Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html), các constructor từ `String`/`double` và các overload `valueOf`.
