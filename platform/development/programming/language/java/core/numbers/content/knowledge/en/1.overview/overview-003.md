# Số nguyên, số dấu phẩy động và số thập phân chính xác trong Java

Trong Java, “số” không phải một kiểu duy nhất. Chọn kiểu dữ liệu là chọn **miền giá trị**, **cách biểu diễn**, **mức chính xác** và **quy tắc tính toán**. Ba nhóm cần phân biệt là số nguyên (integer), số dấu phẩy động nhị phân (floating point) và số thập phân chính xác (decimal với `BigDecimal`). Bài này tập trung vào ý nghĩa, hành vi thực tế và cách chọn đúng cho từng phép tính.

## 1. Bản đồ lựa chọn nhanh

| Nhu cầu | Kiểu nên xét | Lý do và giới hạn |
| --- | --- | --- |
| Đếm, chỉ số mảng, số lượng nguyên trong phạm vi đã biết | `int`, `long` | Tính toán nguyên chính xác **trong phạm vi kiểu**; tràn số cần kiểm soát. |
| Số nguyên lớn hơn `long` | `BigInteger` | Độ lớn tùy ý theo bộ nhớ; phép toán qua phương thức, không dùng `+` với đối tượng. |
| Đo lường, mô phỏng, đồ họa, dữ liệu khoa học chấp nhận sai số làm tròn nhị phân | `double` (hoặc `float` khi có lý do rõ ràng) | Nhanh, hỗ trợ các giá trị đặc biệt; nhiều phân số thập phân không biểu diễn chính xác. |
| Tiền, thuế, đơn giá, phép tính thập phân cần quy tắc làm tròn minh bạch | `BigDecimal` | Lưu hệ số thập phân và scale; vẫn phải quyết định độ chính xác/làm tròn khi phép chia không kết thúc. |
| Số tiền theo đơn vị nhỏ nhất, với thang cố định | `long` hoặc `BigInteger` | Có thể biểu diễn chính xác số đồng/xu/cent nguyên; phải quy định đơn vị, phạm vi và cách chuyển đổi. |

Không có kiểu nào tự giải quyết mọi yêu cầu nghiệp vụ: kể cả khi dùng `BigDecimal`, ứng dụng vẫn cần quy tắc làm tròn, đơn vị, scale và thời điểm làm tròn.

## 2. Số nguyên: chính xác trong miền biểu diễn

### 2.1. Các kiểu nguyên nguyên thủy

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `byte` | 8 | -128 | 127 |
| `short` | 16 | -32.768 | 32.767 |
| `int` | 32 | -2.147.483.648 | 2.147.483.647 |
| `long` | 64 | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

Các kiểu này có dấu và dùng biểu diễn bù hai (two's complement). `char` là kiểu ký tự 16 bit không dấu, không nên chọn làm kiểu số đếm. Các lớp bao `Byte`, `Short`, `Integer`, `Long` là đối tượng, khác với kiểu nguyên thủy về `null`, boxing và chi phí cấp phát.

Literal nguyên mặc định thường là `int`; thêm `L` để tạo literal `long`. Java cho phép viết nhị phân với `0b`, thập lục phân với `0x`, bát phân với tiền tố `0`, và dùng dấu gạch dưới để dễ đọc:

```java
int population = 1_250_000;
long distance = 9_000_000_000L;
int mask = 0b1010_0001;
int color = 0xFF_A0_10;
```

Đây là các khai báo minh họa, không phải một chương trình chạy độc lập. Không thêm ký tự `L` cho giá trị nguyên `long` lớn dễ khiến trình biên dịch từ chối literal vì nó cố phân tích thành `int` trước. Ngoài ra, một chữ số đầu `0` trên literal nguyên mang nghĩa bát phân, nên `010` là 8, không phải 10.

### 2.2. Tràn số và cách phòng tránh

Phép cộng, trừ, nhân trên `int`/`long` không tự ném ngoại lệ khi tràn; kết quả quay vòng theo độ rộng bit. Ví dụ `Integer.MAX_VALUE + 1` cho `Integer.MIN_VALUE`. Việc gán kết quả sang `long` **sau** khi tính không cứu được phép tính đã tràn:

```java
int count = 1_500_000_000;
long wrong = count * 2;          // Phép nhân int đã tràn trước khi gán.
long correct = (long) count * 2; // Nâng một toán hạng trước phép nhân.
```

Khi tràn được xem là lỗi, dùng `Math.addExact`, `subtractExact`, `multiplyExact`, `incrementExact`, `toIntExact` hoặc `negateExact` ở nơi thích hợp. Chúng ném `ArithmeticException` khi kết quả không biểu diễn được. Cần chọn `long` nếu dữ liệu vượt `int` nhưng vẫn nằm trong 64 bit; chọn `BigInteger` khi không có biên hữu hạn phù hợp.

### 2.3. Chia nguyên, phần dư và số âm

Khi cả hai toán hạng là số nguyên, `/` là **chia nguyên, bỏ phần thập phân hướng về 0**, còn `%` là phép lấy phần dư; mẫu số 0 gây `ArithmeticException`.

| Biểu thức Java | Kết quả | Giải thích |
| --- | ---: | --- |
| `7 / 2` | `3` | Bỏ phần lẻ. |
| `7 / 2.0` | `3.5` | Một toán hạng là `double`. |
| `-7 / 3` | `-2` | Làm tròn về 0. |
| `-7 % 3` | `-1` | Phần dư có dấu của số bị chia. |
| `Math.floorDiv(-7, 3)` | `-3` | Chia làm tròn xuống. |
| `Math.floorMod(-7, 3)` | `2` | Phù hợp quy tắc floor khi số chia dương. |

Với `byte` hoặc `short`, các toán tử số học thường nâng toán hạng lên `int`, nên `byte b = 10; b = b + 1;` không biên dịch nếu không ép kiểu; `b++` có cơ chế chuyển kiểu ngầm riêng. Ép kiểu thu hẹp (`(int) aLong`, `(byte) anInt`) có thể mất bit và đổi giá trị; đừng xem cast là kiểm tra phạm vi.

### 2.4. Số nguyên độ lớn tùy ý: BigInteger

`java.math.BigInteger` lưu số nguyên không giới hạn cố định 32/64 bit và là bất biến (immutable). Tạo từ chuỗi để tránh giới hạn của literal `long`, sau đó dùng `add`, `subtract`, `multiply`, `divide`, `remainder`, `pow`, `gcd`, `compareTo`:

```java
BigInteger huge = new BigInteger("9223372036854775808");
BigInteger next = huge.add(BigInteger.ONE);
boolean larger = next.compareTo(huge) > 0;
```

Đoạn trên cần `import java.math.BigInteger;`. Hàm `add` trả đối tượng mới: gọi `huge.add(BigInteger.ONE);` mà không nhận kết quả sẽ không thay đổi `huge`. `BigInteger` phù hợp cho số đếm hoặc phép toán nguyên vượt `long`, nhưng không mang phần thập phân.

## 3. Số dấu phẩy động: gần đúng theo hệ nhị phân

### 3.1. float và double lưu gì?

Java dùng chuẩn IEEE 754 cho `float` 32 bit và `double` 64 bit. Mỗi giá trị hữu hạn được biểu diễn theo dấu, số mũ và phần trị nhị phân; `float` có khoảng 6–7 chữ số thập phân có nghĩa, `double` khoảng 15–16 chữ số có nghĩa. `double` có phạm vi và độ chính xác lớn hơn, thường là lựa chọn mặc định cho phép tính thực khi được phép có sai số nhị phân. Literal `0.1` có kiểu `double`; literal `0.1f` có kiểu `float`.

Nhiều phân số tưởng chừng đơn giản trong hệ thập phân, ví dụ 1/10, không có biểu diễn nhị phân hữu hạn. Vì thế:

```java
System.out.println(0.1 + 0.2);        // 0.30000000000000004
System.out.println(0.1 + 0.2 == 0.3); // false
```

Các dòng này là mảnh mã minh họa đặt trong `main`. Sai số không có nghĩa JVM cộng “sai”; phép toán đã làm tròn đến giá trị `double` gần biểu thức toán học nhất theo quy tắc của kiểu. Thứ tự cộng các số thực có thể thay đổi kết quả: do làm tròn sau mỗi bước, tính toán dấu phẩy động nói chung không có tính kết hợp như số thực toán học.

### 3.2. Giá trị đặc biệt và cách so sánh

Floating point có `NaN` (không phải số), `POSITIVE_INFINITY`, `NEGATIVE_INFINITY`, `+0.0` và `-0.0`:

- `1.0 / 0.0` cho `Infinity`, `0.0 / 0.0` cho `NaN`; khác chia nguyên cho 0.
- `NaN == NaN` là `false`. Kiểm tra bằng `Double.isNaN(value)` hoặc `Float.isNaN(value)`; kiểm tra giá trị hữu hạn bằng `Double.isFinite(value)`.
- `-0.0 == 0.0` là `true`, nhưng một số phép toán và `Double.compare(-0.0, 0.0)` phân biệt được dấu (kết quả `Double.compare` là số âm).
- `Double.compare` tạo thứ tự tổng để phục vụ sắp xếp theo quy tắc Java, nhưng không thay thế tiêu chí so gần đúng trong tính toán khoa học.

Tránh kiểm tra hai kết quả phép tính dấu phẩy động bằng `==` khi ý nghĩa bài toán là “xấp xỉ bằng nhau”. Một cách cơ bản là kiểm tra `Math.abs(a - b) <= tolerance`, với ngưỡng tuyệt đối phù hợp **đơn vị và quy mô**. Với miền giá trị rộng, cần kết hợp ngưỡng tuyệt đối và tương đối; phải định nghĩa cách xử lý `NaN`, vô cực, giá trị rất gần 0 và nguy cơ tràn khi trừ. Không có một `epsilon` cố định dùng đúng cho mọi chương trình.

### 3.3. Làm tròn và in kết quả

Hàm `Math.round`, `Math.floor`, `Math.ceil` có quy tắc riêng và không biến `double` thành số thập phân chính xác. `System.out.printf` hoặc `String.format` có thể **định dạng cách hiển thị**, nhưng phần lưu trữ vẫn là nhị phân:

```java
System.out.printf(java.util.Locale.US, "%.2f%n", 1.235);
```

Mảnh lệnh trên hiển thị hai chữ số sau dấu thập phân theo quy tắc định dạng số thực; tránh suy luận rằng chuỗi hiển thị là bằng chứng phép tính tài chính đã được thực hiện bằng thập phân chính xác. Locale ảnh hưởng ký hiệu dấu thập phân và dấu nhóm khi định dạng; dữ liệu nội bộ và dữ liệu trao đổi nên có quy ước rõ ràng.

## 4. BigDecimal: giá trị thập phân chính xác cùng quy tắc scale

### 4.1. Mô hình giá trị

`BigDecimal` biểu diễn số hữu hạn dạng **unscaledValue × 10^(-scale)**: hệ số nguyên không giới hạn cố định và `scale` là số nguyên 32 bit. Ví dụ `2.50` có hệ số 250 và scale 2. Khác `double`, chuỗi thập phân `"0.1"` có thể được lưu chính xác.

Tạo `BigDecimal` từ **chuỗi**, hoặc dùng `BigDecimal.valueOf(double)` nếu đầu vào đang là `double` và bạn chủ ý lấy biểu diễn thập phân chuẩn của chính giá trị đó:

```java
BigDecimal precise = new BigDecimal("0.1");
BigDecimal fromDouble = BigDecimal.valueOf(0.1);
BigDecimal exposedBinary = new BigDecimal(0.1);
```

`precise` và `fromDouble` đều có giá trị thập phân `0.1` trong ví dụ này. `exposedBinary` mang giá trị thập phân chính xác của số nhị phân `double` gần 0.1, thường là một chuỗi dài; tránh `new BigDecimal(0.1)` khi kỳ vọng số tiền 0.1. `BigDecimal.valueOf(0.1 + 0.2)` không thể khôi phục ý định `0.3` sau khi phép cộng `double` đã làm tròn thành `0.30000000000000004`.

Có thể sử dụng `BigDecimal.ZERO`, `ONE`, `TEN`, hoặc `BigDecimal.valueOf(long)`. Không dùng toán tử `+`, `-`, `*`, `/` trực tiếp giữa các `BigDecimal`; dùng phương thức và nhận giá trị mới.

### 4.2. Bốn phép toán và bài toán phép chia

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal sum = a.add(b);                       // 0.3
BigDecimal difference = b.subtract(a);          // 0.1
BigDecimal product = a.multiply(b);             // 0.02
BigDecimal quotient = BigDecimal.ONE.divide(
        new BigDecimal("8"));                   // 0.125, kết thúc hữu hạn
```

Đây là mảnh mã; thêm `import java.math.BigDecimal;` và đặt trong phương thức khi chạy. Các phép cộng, trừ, nhân có thể cho kết quả thập phân chính xác (giới hạn tài nguyên máy). Tuy nhiên **1/3 không có biểu diễn thập phân hữu hạn**. `BigDecimal.ONE.divide(new BigDecimal("3"))` không có chế độ làm tròn sẽ ném `ArithmeticException` vì yêu cầu kết quả chính xác.

Khi kết quả không kết thúc, quy định số chữ số sau dấu thập phân và chế độ làm tròn:

```java
BigDecimal third = BigDecimal.ONE.divide(
        new BigDecimal("3"), 2, RoundingMode.HALF_UP); // 0.33
```

Đoạn này cần `import java.math.RoundingMode;`. Không tự mặc định `HALF_UP` là “đúng về tài chính”: quy tắc có thể là `HALF_EVEN` (làm tròn điểm giữa về chữ số chẵn), `DOWN`, `UP`, `CEILING`, `FLOOR`, v.v., tùy hợp đồng hoặc chuẩn nghiệp vụ. Chọn đúng cả dấu, trường hợp nửa chừng và nơi áp dụng làm tròn.

### 4.3. Scale khác precision

- **Scale**: số chữ số ở bên phải dấu thập phân theo biểu diễn (`12.340` có scale 3); scale có thể âm.
- **Precision**: số chữ số của hệ số nguyên khi tính theo `BigDecimal.precision()` (`12.340` có precision 5).
- `setScale(2, mode)`: đặt số vị trí thập phân của kết quả; nếu phải bỏ chữ số, cần `RoundingMode`.
- `MathContext(precision, mode)`: giới hạn số **chữ số có nghĩa** khi thực hiện phép toán với context; không đồng nghĩa luôn lấy từng ấy chữ số sau dấu thập phân.

```java
BigDecimal price = new BigDecimal("12.345");
BigDecimal cents = price.setScale(2, RoundingMode.HALF_EVEN); // 12.34
BigDecimal significant = price.round(
        new MathContext(3, RoundingMode.HALF_EVEN));          // 12.3
```

Mảnh này cần `import java.math.MathContext;` và `import java.math.RoundingMode;`. `BigDecimal` bất biến: `price.setScale(2, ...)` không sửa `price`; phải gán kết quả. Việc làm tròn từng dòng hóa đơn trước khi cộng và làm tròn một lần ở tổng có thể khác nhau; quy tắc nghiệp vụ cần xác định rõ.

### 4.4. equals, compareTo và hiển thị

`new BigDecimal("2.0").equals(new BigDecimal("2.00"))` trả `false` vì `equals` xét cả **giá trị và scale**. `compareTo` trả 0 vì hai số có cùng giá trị toán học. Vì thế kiểm tra bằng giá trị nên dùng `compareTo(...) == 0` khi scale không mang ý nghĩa:

```java
BigDecimal x = new BigDecimal("2.0");
BigDecimal y = new BigDecimal("2.00");
boolean sameRepresentation = x.equals(y);   // false
boolean sameNumericValue = x.compareTo(y) == 0; // true
```

Tương ứng, `HashSet<BigDecimal>` dùng `equals`/`hashCode`, còn cấu trúc sắp xếp như `TreeSet<BigDecimal>` thường xét `compareTo`; do đó hai chuỗi biểu diễn khác scale có thể được xử lý khác nhau. `stripTrailingZeros()` có thể đổi scale (kể cả sang scale âm). Dùng `toPlainString()` khi muốn chuỗi thập phân thông thường và tránh cách in ký hiệu khoa học ở những giá trị có thể biểu diễn kiểu đó; vẫn cần quy định scale của dữ liệu xuất ra.

`BigDecimal` không mang `NaN` hay vô cực; nếu nhận `double` không hữu hạn để chuyển sang `BigDecimal`, phải kiểm tra và xử lý trước.

## 5. Chương trình Java 17+ chạy độc lập

Lưu đoạn sau thành **`NumericDemo.java`**. Ví dụ này chọn những phép tính có kết quả và cách in xác định, để thấy sự khác nhau giữa integer, floating point, `BigInteger` và `BigDecimal`.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

public class NumericDemo {
    public static void main(String[] args) {
        System.out.println("int-division=" + (7 / 2));
        System.out.println("real-division=" + (7 / 2.0));

        System.out.println("int-overflow=" + (Integer.MAX_VALUE + 1));
        try {
            Math.addExact(Integer.MAX_VALUE, 1);
        } catch (ArithmeticException e) {
            System.out.println("checked-overflow=detected");
        }

        System.out.println("floating-sum=" + (0.1 + 0.2));
        System.out.println("floating-equal=" + ((0.1 + 0.2) == 0.3));
        System.out.println("nan=" + Double.isNaN(0.0 / 0.0));

        BigDecimal oneTenth = new BigDecimal("0.1");
        BigDecimal twoTenths = new BigDecimal("0.2");
        System.out.println("decimal-sum=" + oneTenth.add(twoTenths));
        System.out.println("third=" + BigDecimal.ONE.divide(
                new BigDecimal("3"), 2, RoundingMode.HALF_UP));

        BigDecimal first = new BigDecimal("2.0");
        BigDecimal second = new BigDecimal("2.00");
        System.out.println("scale-equals=" + first.equals(second));
        System.out.println("value-equal=" + (first.compareTo(second) == 0));

        BigInteger beyondLong = new BigInteger("9223372036854775808");
        System.out.println("big-integer=" + beyondLong.add(BigInteger.ONE));
    }
}
```

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

```bash
javac NumericDemo.java
java NumericDemo
```

Kết quả stdout:

```text
int-division=3
real-division=3.5
int-overflow=-2147483648
checked-overflow=detected
floating-sum=0.30000000000000004
floating-equal=false
nan=true
decimal-sum=0.3
third=0.33
scale-equals=false
value-equal=true
big-integer=9223372036854775809
```

Giải thích: `7 / 2` mất phần lẻ theo chia nguyên, còn `7 / 2.0` dùng `double`; cộng `int` tràn thì quay vòng trong khi `Math.addExact` phát hiện; `0.1 + 0.2` làm tròn nhị phân; `BigDecimal` tạo từ chuỗi cộng ra đúng `0.3`. Hai biểu diễn `2.0` và `2.00` có cùng giá trị toán học nhưng khác scale. `BigInteger` xử lý giá trị lớn hơn `Long.MAX_VALUE`.

## 6. Quy tắc chuyển đổi và lỗi phổ biến

| Tình huống | Điều gì có thể xảy ra? | Cách xử lý |
| --- | --- | --- |
| `int` cộng/nhân vượt giới hạn | Tràn âm thầm | Phân tích miền dữ liệu; dùng `long`, `BigInteger` hoặc hàm `Math.*Exact`. |
| Nhân hai `int` rồi gán `long` | Đã tràn ở bước nhân | Nâng ít nhất một toán hạng lên `long` **trước** phép tính. |
| `int / int` rồi gán `double` | Phần lẻ đã bị bỏ | Dùng `(double) numerator / denominator` nếu muốn chia thực. |
| Lưu tiền vào `double` | Sai số biểu diễn hoặc phép tính | Tạo `BigDecimal` từ chuỗi/thông tin thập phân gốc; hoặc lưu đơn vị tiền nhỏ nhất dạng nguyên. |
| `new BigDecimal(someDouble)` | Bộc lộ giá trị nhị phân gần đúng | Nhận chuỗi thập phân gốc; `valueOf` khi chủ ý chuyển theo `Double.toString`. |
| `BigDecimal.divide` không quy định làm tròn | Có thể ném `ArithmeticException` với kết quả vô hạn tuần hoàn | Quy định scale hoặc `MathContext` và `RoundingMode`. |
| So sánh `BigDecimal.equals` | `2.0` khác `2.00` | Dùng `compareTo == 0` để so giá trị không phụ thuộc scale. |
| Không nhận kết quả của `add`/`setScale` | Đối tượng ban đầu không đổi | Gán hoặc trả về đối tượng mới. |
| Ép `double` sang `int`/`long` | Bỏ phần lẻ, NaN thành 0, giá trị ngoài miền bị chặn về biên theo quy tắc chuyển kiểu | Kiểm tra hữu hạn, miền giá trị và quy tắc làm tròn trước khi chuyển. |
| Gọi `Double.parseDouble` hoặc `new BigDecimal(text)` trên dữ liệu lỗi | `NumberFormatException` | Kiểm tra đầu vào; thống nhất quy ước thập phân và locale ở lớp giao tiếp. |

**Về conversion:** chuyển `int` sang `double` thường chính xác cho mọi giá trị `int`, nhưng không phải mọi `long` đều biểu diễn được chính xác dưới dạng `double` (độ chính xác phần trị hữu hạn). Chuyển `BigDecimal` sang `double` qua `doubleValue()` cũng có thể mất chữ số hoặc vượt miền. Không đem phép định dạng chuỗi làm bước thay thế cho phép tính chính xác.

**Về dữ liệu tiền tệ:** ví dụ số tiền `"19.99"` có thể tạo bằng `new BigDecimal("19.99")`. Khi nhân với số lượng nguyên, dùng `price.multiply(BigDecimal.valueOf(quantity))`. Ứng dụng cần định nghĩa đồng tiền/đơn vị, scale hợp lệ, chế độ làm tròn khi thuế/chiết khấu/phân bổ, cách xử lý giá trị âm và so khớp tổng các dòng. Một `BigDecimal` đơn lẻ không chứa mã tiền tệ và không tự chọn quy tắc kế toán.

## 7. Tự kiểm tra kiến thức

1. Vì sao `long total = 2_000_000_000 * 2;` có thể cho kết quả sai, còn `long total = 2_000_000_000L * 2;` thì không tràn tại phép nhân này? Hãy chỉ ra **kiểu của toán hạng trước khi phép nhân xảy ra**.
2. Dự đoán và xác minh `-7 / 3`, `-7 % 3`, `Math.floorDiv(-7, 3)` và `Math.floorMod(-7, 3)`.
3. Vì sao `0.1 + 0.2 == 0.3` là `false`, nhưng `new BigDecimal("0.1").add(new BigDecimal("0.2"))` có giá trị đúng `0.3`?
4. Viết phép chia `1 / 3` với `BigDecimal` lấy bốn chữ số sau dấu thập phân, chỉ rõ chế độ làm tròn và giải thích tại sao `divide` không có quy tắc làm tròn có thể ném lỗi.
5. So sánh `new BigDecimal("10.0")` và `new BigDecimal("10.00")` bằng `equals` và `compareTo`. Trong chương trình dùng `HashSet` và `TreeSet`, khác biệt đó ảnh hưởng thế nào?
6. Thiết kế phép tính tổng hóa đơn có đơn giá thập phân, số lượng, giảm giá và thuế. Nêu thời điểm làm tròn, scale, đơn vị tiền và kiểm thử tình huống nửa chừng; không sử dụng `double` để tính số tiền.

## 8. Điểm cần ghi nhớ

- **Số nguyên** chính xác trong miền kiểu, nhưng tràn số cần được chủ động kiểm soát; `BigInteger` dành cho số nguyên vượt `long`.
- **`float`/`double`** biểu diễn số thực nhị phân gần đúng; phù hợp bài toán có sai số chấp nhận được, cần chính sách so gần đúng và xử lý `NaN`/vô cực.
- **`BigDecimal`** biểu diễn thập phân hữu hạn chính xác khi khởi tạo đúng; phép chia và ràng buộc nghiệp vụ vẫn đòi hỏi chính sách precision, scale và rounding.
- Kiểu dữ liệu đúng được quyết định từ miền giá trị, đơn vị, độ chính xác yêu cầu và quy tắc của bài toán, không chỉ từ việc chương trình có biên dịch thành công hay không.
