# Chọn kiểu tính toán trung gian riêng với kiểu lưu trữ trong Java

## 1. Vì sao không nên dùng một kiểu số cho mọi giai đoạn?

Khi thiết kế dữ liệu số, cần phân biệt **kiểu của giá trị được lưu** với **kiểu dùng trong phép tính trung gian**. Một thuộc tính có thể vừa vặn trong `int` hoặc `long` ở trạng thái cuối, nhưng phép tính tạo ra nó có thể cần phạm vi rộng hơn, độ chính xác khác hoặc một cách biểu diễn khác.

Ví dụ số lượng và đơn giá đều là `int`:

```java
int quantity = 50_000;
int unitPrice = 50_000;
long total = quantity * unitPrice; // Sai: phép nhân int đã tràn trước khi gán.
```

Giá trị toán học mong muốn là `2_500_000_000`, lớn hơn `Integer.MAX_VALUE` (`2_147_483_647`). Do cả hai toán hạng là `int`, Java **nhân bằng `int` trước**, kết quả tràn thành `-1_794_967_296`, rồi mới mở rộng sang `long`. Việc gán vào biến `long` không sửa được phép tính đã tràn.

Cách đúng khi miền giá trị tổng nằm trong `long`:

```java
long total = (long) quantity * unitPrice; // 2_500_000_000
```

**Quy tắc nền tảng:** xác định giới hạn và độ chính xác ở *từng bước tính*, rồi chọn kiểu thực hiện phép toán; chỉ ở ranh giới lưu trữ hoặc xuất dữ liệu mới kiểm tra và chuyển về kiểu đích. Không giả định kiểu của biến nhận kết quả sẽ quyết định kiểu của phép tính.

## 2. Hai hợp đồng cần xác định

### Hợp đồng của phép tính

Cần trả lời:

- Phạm vi cực đại, cực tiểu của **các kết quả trung gian** là bao nhiêu?
- Có phép cộng, nhân, tổng hợp hàng triệu bản ghi, bình phương, tỷ lệ hoặc chia tạo phần thập phân không?
- Phép toán cần chính xác tuyệt đối, hay chấp nhận sai số dấu phẩy động?
- Nếu vượt phạm vi, chương trình phải ném lỗi, đổi sang kiểu lớn hơn hay có quy tắc làm tròn?
- Có đơn vị nào phải giữ nhất quán, chẳng hạn **đồng** so với **xu**, **mét** so với **milimét**, **giây** so với **nano giây**?

### Hợp đồng của lưu trữ

Cần trả lời:

- Trường là `int`/`long` của Java, `INTEGER`/`BIGINT`/`DECIMAL(p,s)` của cơ sở dữ liệu, hay chuỗi số trong giao diện JSON?
- Giá trị cuối cần giữ đến chữ số thập phân nào, có thể âm không, và có cần bảo toàn scale không?
- Có yêu cầu tương thích schema, index, truy vấn, kích thước dữ liệu hay giao tiếp với hệ thống khác không?
- Chuyển đổi thu hẹp có được phép làm tròn không? Dữ liệu ngoài phạm vi phải được từ chối như thế nào?

Chỉ sau khi nêu rõ hai hợp đồng mới chọn được kiến trúc. Có thể dùng `int` để lưu năm sinh, `long` để lưu tổng số lượt; dùng `long` lưu tiền ở đơn vị nhỏ nhất nhưng tính thuế bằng `BigDecimal`; hoặc dùng `BigInteger` để cộng các giá trị cực lớn trước khi xác nhận kết quả cuối có thể lưu bằng `long`.

## 3. Miền giá trị của những kiểu số thông dụng

| Kiểu Java | Miền và đặc tính | Vai trò thường gặp |
| --- | --- | --- |
| `byte` | -128 đến 127 | Dữ liệu nhị phân hoặc giao thức, ít khi là kiểu phép tính tổng hợp |
| `short` | -32.768 đến 32.767 | Lưu các trường có miền nhỏ; phép toán số học thường được nâng thành `int` |
| `int` | -2³¹ đến 2³¹-1 | Đếm hoặc thuộc tính nhỏ, số nguyên thông dụng |
| `long` | -2⁶³ đến 2⁶³-1 | Bộ đếm lớn, tổng và tích vượt phạm vi `int` |
| `float` | IEEE 754 32-bit; độ chính xác hữu hạn | Số đo xấp xỉ khi có yêu cầu tài nguyên cụ thể |
| `double` | IEEE 754 64-bit; độ chính xác xấp xỉ 15–17 chữ số thập phân có nghĩa | Thống kê, khoa học, tỷ lệ chấp nhận sai số |
| `BigInteger` | Số nguyên có độ lớn giới hạn chủ yếu bởi tài nguyên | Phép toán nguyên vượt `long` |
| `BigDecimal` | Thập phân với số nguyên không chia tỷ lệ và `scale`; độ chính xác theo phép toán/`MathContext` | Tài chính, decimal chính xác và rounding có kiểm soát |

`float` và `double` có phạm vi độ lớn rất rộng nhưng **không biểu diễn chính xác mọi số nguyên hoặc số thập phân** trong phạm vi đó. Chọn `double` chỉ vì nó chứa được số “rất lớn” có thể làm mất chữ số nguyên thấp. Ngược lại, dùng `BigDecimal` cho một phép đo vật lý vốn có sai số đầu vào không tự tạo ra độ chính xác chưa từng tồn tại.

Không chọn kiểu chỉ dựa vào giá trị hiện tại. Cần tính cả **biên của phép toán trung gian**, số lượng dữ liệu tương lai, dấu âm, các lần nhân hệ số và giới hạn khi gộp dữ liệu.

## 4. Cơ chế thăng hạng kiểu và tràn số trước khi gán

Trong Java, kết quả của phép cộng, trừ, nhân trên `byte`, `short`, `char` thường được thăng hạng thành `int`. Khi hai toán hạng là `int`, phép toán vẫn có kiểu `int`. Có một toán hạng `long` trong phép toán số nguyên thì phép tính được thực hiện bằng `long`, miễn không có phép toán con nào đã tràn trước đó.

```java
int x = 50_000;
int y = 50_000;

long wrong = x * y;          // -1_794_967_296: int đã tràn
long right = (long) x * y;   //  2_500_000_000: nhân bằng long
long also = 1L * x * y;      //  2_500_000_000: literal long
long stillWrong = (long) (x * y); // tràn xảy ra trong dấu ngoặc
```

Ép kiểu **sau** phép tính không thể phục hồi phần dữ liệu đã mất.

Với tổng:

```java
int a = 2_000_000_000;
int b = 1_000_000_000;

long wrongSum = a + b;          // -1_294_967_296
long rightSum = (long) a + b;   //  3_000_000_000
```

Phép chia cũng chịu kiểu của toán hạng:

```java
int sum = 5;
int count = 2;

double wrongAverage = sum / count;         // 2.0: đã chia nguyên
double rightAverage = (double) sum / count; // 2.5
```

Đối với một biểu thức phức tạp, mở rộng kiểu tại **đúng phép toán cần miền rộng**. Ví dụ `(long) quantity * unitPrice` mở rộng ngay phép nhân; còn `(long) (quantity * unitPrice)` mở rộng quá muộn.

### Java không tự báo lỗi mọi phép toán tràn

Các phép cộng/trừ/nhân nguyên `int` và `long` thông thường có thể tràn và cho kết quả theo số học mô-đun 2^32 hoặc 2^64, thay vì ném ngoại lệ. Để phát hiện tràn khi điều đó là lỗi, dùng `Math.addExact`, `Math.subtractExact`, `Math.multiplyExact`, `Math.incrementExact`, `Math.negateExact` hoặc `Math.toIntExact` theo kiểu phù hợp.

```java
long valid = Math.multiplyExact((long) 50_000, 50_000); // 2_500_000_000
int invalid = Math.multiplyExact(50_000, 50_000);       // ArithmeticException
```

Dòng thứ hai cố ý minh họa ngoại lệ; nếu thực thi nối tiếp mà không `try/catch`, chương trình dừng ở đó. `multiplyExact(int,int)` phát hiện tràn `int`, còn `multiplyExact(long,long)` phát hiện tràn `long`. Việc mở rộng lên `long` không phải bảo đảm không thể tràn trong mọi bài toán.

## 5. Chương trình Java 17+ minh họa lỗi và cách xử lý

Lưu tệp `IntermediateIntegerDemo.java`:

```java
import java.util.stream.IntStream;

public class IntermediateIntegerDemo {
    public static void main(String[] args) {
        int quantity = 50_000;
        int unitPrice = 50_000;

        long overflowed = quantity * unitPrice;
        long widened = (long) quantity * unitPrice;
        long exact = Math.multiplyExact((long) quantity, unitPrice);

        System.out.println("int multiplication: " + overflowed);
        System.out.println("long multiplication: " + widened);
        System.out.println("checked long product: " + exact);

        try {
            Math.multiplyExact(quantity, unitPrice);
        } catch (ArithmeticException e) {
            System.out.println("int overflow detected");
        }

        try {
            Math.toIntExact(exact);
        } catch (ArithmeticException e) {
            System.out.println("cannot store in int");
        }

        int intSum = IntStream.of(2_000_000_000, 1_000_000_000).sum();
        long longSum = IntStream.of(2_000_000_000, 1_000_000_000)
                .asLongStream().sum();

        System.out.println("IntStream sum: " + intSum);
        System.out.println("long stream sum: " + longSum);
    }
}
```

Chạy:

```bash
javac IntermediateIntegerDemo.java
java IntermediateIntegerDemo
```

Stdout chính xác:

```text
int multiplication: -1794967296
long multiplication: 2500000000
checked long product: 2500000000
int overflow detected
cannot store in int
IntStream sum: -1294967296
long stream sum: 3000000000
```

Ví dụ chỉ minh họa miền trung gian và tràn số; những giá trị trên không được diễn giải là “Java trả số ngẫu nhiên”. Kết quả âm đầu tiên và kết quả âm của `IntStream.sum()` là hậu quả xác định của phép toán nguyên 32-bit bị tràn.

Để tổng hợp số lượng lớn hơn phạm vi `long`, chuyển hẳn sang `BigInteger` hoặc tính trong miền đã được chứng minh an toàn. `LongStream.sum()` dùng `long` nhưng không tự bảo đảm chống tràn số.

## 6. Kiểu lưu trữ nhỏ không bắt buộc phép tính trung gian nhỏ

Giả sử một hệ thống lưu số điểm là `short` vì mỗi điểm từ 0 đến 100. Trung bình cộng cần một tổng lớn hơn nhiều khi có hàng triệu bản ghi; tính trực tiếp trong `short` là sai thiết kế ngay cả khi **kết quả trung bình cuối cùng** vẫn nằm trong 0..100.

Một ví dụ khác là số lượng từng dòng chỉ vừa trong `int`, nhưng tổng đơn hàng phải là `long`. Ta có thể lưu lại số lượng từng dòng bằng `int` và trả tổng bằng `long`. Không cần đổi tất cả cột dữ liệu sang `long` chỉ vì một phép cộng gộp có thể lớn.

Mặt khác, nếu phép tính trung gian dùng `long` và giá trị cuối cần lưu trong `int`, phải kiểm tra **miền đích ngay khi chuyển**:

```java
long total = 2_500_000_000L;
int unsafe = (int) total; // -1_794_967_296, thu hẹp bị mất dữ liệu

// Ném ArithmeticException thay vì lặng lẽ biến đổi:
int checked = Math.toIntExact(total);
```

Dòng `Math.toIntExact` sẽ ném ngoại lệ trong tình huống minh họa; những dòng này không phải chương trình đầy đủ chạy nối tiếp.

Với kiểu `short` và `byte` không có `Math.toShortExact`/`Math.toByteExact` chuẩn tương tự; có thể kiểm tra phạm vi trước:

```java
static short toShortExact(int value) {
    if (value < Short.MIN_VALUE || value > Short.MAX_VALUE) {
        throw new ArithmeticException("Out of short range");
    }
    return (short) value;
}
```

Đoạn này là một phương thức có thể đặt bên trong class; không có `main` riêng. Nó giúp diễn đạt rõ **quy tắc thu hẹp**. Không dùng ép kiểu thu hẹp trực tiếp khi việc mất dữ liệu bị cấm.

## 7. Trường hợp cần BigInteger làm kiểu tính trung gian

`long` có giới hạn `Long.MAX_VALUE = 9_223_372_036_854_775_807`. Nếu đầu vào hoặc tổng/tích có thể vượt giới hạn đó, `BigInteger` cho phép phép tính nguyên không bị tràn theo kiểu cố định:

```java
import java.math.BigInteger;

public class BigIntegerIntermediateDemo {
    public static void main(String[] args) {
        BigInteger total = BigInteger.valueOf(Long.MAX_VALUE)
                .add(BigInteger.ONE);

        System.out.println("Exact total: " + total);
        System.out.println("Beyond long: "
                + (total.compareTo(BigInteger.valueOf(Long.MAX_VALUE)) > 0));

        try {
            total.longValueExact();
        } catch (ArithmeticException e) {
            System.out.println("Cannot fit long");
        }
    }
}
```

Chạy:

```bash
javac BigIntegerIntermediateDemo.java
java BigIntegerIntermediateDemo
```

Stdout:

```text
Exact total: 9223372036854775808
Beyond long: true
Cannot fit long
```

`longValue()` cắt bớt các bit cao nếu giá trị nằm ngoài `long`, dẫn tới một kết quả sai nghĩa. `longValueExact()` mới là lựa chọn khi muốn kiểm tra phép chuyển về kiểu lưu trữ. Tương tự, `BigInteger.intValueExact()` giúp xác nhận giá trị vừa với `int`.

Không lạm dụng `BigInteger` cho mọi biến đếm: nó cấp phát đối tượng và có chi phí cao hơn phép tính primitive. Chọn `BigInteger` khi các phép tính thực sự có khả năng vượt `long` hoặc hợp đồng miền giá trị không thể đặt giới hạn an toàn.

## 8. double có thể rộng hơn int/long nhưng không giữ đúng mọi chữ số

`double` thường được dùng làm kiểu trung gian cho thống kê, tỷ lệ, vị trí, đo lường hoặc thuật toán xấp xỉ. Nó có dải độ lớn rộng nhưng chỉ **53 bit độ chính xác nhị phân** (bao gồm bit dẫn), nên chỉ biểu diễn chính xác mọi số nguyên trong một miền liên tiếp tới 2^53. Những số nguyên lớn hơn có thể bị làm tròn khi đổi thành `double`.

Ví dụ:

```java
long exactCount = 9_007_199_254_740_993L; // 2^53 + 1
double approximate = exactCount;
System.out.println(approximate == 9_007_199_254_740_992.0); // true
```

`approximate` không lưu được chữ số đơn vị của `exactCount`. Vì vậy, không nên đổi mọi tổng hoặc ID số nguyên lớn sang `double` chỉ để “tránh overflow”. Đặc biệt ID, số đơn vị nhỏ nhất và số lượng cần chính xác nên ở `long`/`BigInteger` khi phù hợp.

Thập phân cũng có vấn đề biểu diễn:

```java
double binary = 0.1 + 0.2;
System.out.println(binary); // 0.30000000000000004
```

Đây không phải phép tính lỗi của Java mà là đặc điểm IEEE 754: `0.1` và `0.2` không thể biểu diễn chính xác bằng hữu hạn bit nhị phân. Dùng `double` khi **sai số chấp nhận được và có chính sách kiểm thử**, còn khi cần decimal chính xác, dùng `BigDecimal` với đầu vào thích hợp.

Một vài điểm cần nhớ khi chuyển từ `double` sang số nguyên:

- `(int) doubleValue` có thể mất phần thập phân, bão hòa ở biên của kiểu đích khi vượt phạm vi và chuyển `NaN` thành 0; không phải một phép chuyển kiểm tra chính xác.
- `Math.round` áp quy tắc làm tròn riêng và vẫn cần xét giới hạn, không phải tương đương với chuyển đổi exact.
- Khi không chấp nhận phần lẻ hoặc giá trị không hữu hạn, hãy kiểm tra đầu vào và miền trước khi thu hẹp, hoặc dùng biểu diễn `BigDecimal` thích hợp nếu domain yêu cầu số thập phân.

## 9. BigDecimal cho phép tính thập phân, kiểu lưu trữ có thể khác

Một cách thiết kế phổ biến trong hệ thống tài chính là lưu **đơn vị nhỏ nhất** bằng `long` (ví dụ cents) nhưng thực hiện tính thuế, chiết khấu, lãi, tỷ lệ và làm tròn bằng `BigDecimal`.

Lý do:

1. `long` lưu được số nguyên đơn vị nhỏ nhất chính xác và phù hợp cho truy vấn/đối chiếu khi schema đặt miền hợp lệ.
2. Tính phần trăm hoặc chia tỷ lệ có thể tạo số với nhiều chữ số thập phân, dù giá trị lưu cuối chỉ có hai chữ số.
3. Chỉ làm tròn tại **ranh giới nghiệp vụ được định nghĩa**, rồi chuyển về đơn vị lưu trữ với kiểm tra exact và phạm vi.

Chẳng hạn: số tiền trước thuế là 37.02, thuế suất 7.5%; tiền thuế chính xác trước làm tròn là 2.77650, và làm tròn đến hai chữ số theo `HALF_UP` cho 2.78. Lưu trực tiếp từng bước vào `long` cents trước khi có chính sách rounding có thể làm mất chữ số cần cho tính toán.

### Chương trình Java 17+ hoàn chỉnh

Lưu tệp `MoneyIntermediateDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyIntermediateDemo {
    static BigDecimal fromCents(long cents) {
        return BigDecimal.valueOf(cents, 2);
    }

    static long toCentsExact(BigDecimal amount) {
        return amount.movePointRight(2).longValueExact();
    }

    public static void main(String[] args) {
        long unitPriceCents = 1_234L;
        long quantity = 3L;

        long subtotalCents = Math.multiplyExact(unitPriceCents, quantity);
        BigDecimal subtotal = fromCents(subtotalCents);

        BigDecimal exactTax = subtotal.multiply(new BigDecimal("0.075"));
        BigDecimal bookedTax = exactTax.setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.add(bookedTax);
        long storedTotalCents = toCentsExact(total);

        System.out.println("Subtotal: " + subtotal);
        System.out.println("Tax before rounding: " + exactTax);
        System.out.println("Tax booked: " + bookedTax);
        System.out.println("Total: " + total);
        System.out.println("Stored cents: " + storedTotalCents);

        try {
            toCentsExact(new BigDecimal("1.005"));
        } catch (ArithmeticException e) {
            System.out.println("Fractional cent rejected");
        }
    }
}
```

Chạy:

```bash
javac MoneyIntermediateDemo.java
java MoneyIntermediateDemo
```

Stdout:

```text
Subtotal: 37.02
Tax before rounding: 2.77650
Tax booked: 2.78
Total: 39.80
Stored cents: 3980
Fractional cent rejected
```

Giải thích:

- `Math.multiplyExact` phát hiện tràn `long` khi nhân giá với số lượng.
- `BigDecimal.valueOf(cents, 2)` biểu diễn chính xác số tiền với scale 2.
- Nhân `BigDecimal` với chuỗi `"0.075"` giữ chính xác giá trị thập phân của thuế suất.
- `setScale(2, HALF_UP)` là **quy tắc làm tròn của ví dụ**, không phải quy tắc mặc định cho mọi hệ thống hay mọi đồng tiền.
- `movePointRight(2).longValueExact()` chỉ chuyển sang cents nếu giá trị là một số nguyên cents chính xác và trong phạm vi `long`. Giá trị `1.005` cents hóa thành `100.5`, nên bị từ chối thay vì lặng lẽ làm tròn.

Đây là ví dụ về ranh giới chuyển đổi, không phải phần mềm tính thuế hoàn chỉnh. Hệ thống thực tế phải xác định đơn vị tiền tệ, thời điểm làm tròn, chính sách thuế, cách phân bổ phần dư và biểu diễn lưu trữ hợp lệ.

## 10. Tính trung gian với precision và scale khác kiểu lưu

`BigDecimal` có `scale` (số chữ số sau dấu thập phân đối với scale không âm) và `precision` (số chữ số của số nguyên không chia tỷ lệ). Đầu vào, kết quả trung gian và đầu ra có thể có những scale khác nhau mà vẫn cùng giá trị toán học.

Ví dụ:

```java
BigDecimal amount = new BigDecimal("12.34");
BigDecimal ratio = new BigDecimal("0.075");
BigDecimal product = amount.multiply(ratio); // 0.92550

BigDecimal finalValue = product.setScale(2, RoundingMode.HALF_EVEN);
// 0.93
```

Đây là minh họa trong một phương thức với `BigDecimal`, `RoundingMode` đã import. Tính trung gian giữ thêm chữ số, sau đó chuyển sang scale lưu trữ ở **đúng điểm làm tròn**. Nếu mỗi bước đều `setScale(2, ...)`, sai số có thể tích lũy theo chuỗi phép tính và khiến kết quả cuối khác phép tính chỉ làm tròn ở cuối.

Cũng cần nhớ:

- `new BigDecimal("0.1")` biểu diễn đúng decimal 0.1; `new BigDecimal(0.1)` nhận một giá trị `double` nhị phân gần đúng.
- `divide(divisor)` yêu cầu thương thập phân hữu hạn chính xác; nếu thương như 1/3 không hữu hạn, Java ném `ArithmeticException`. Cần định nghĩa `scale`, `MathContext` hoặc `RoundingMode` phù hợp.
- `RoundingMode.UNNECESSARY` hữu ích khi hợp đồng cấm mọi mất chữ số có giá trị: nếu việc đổi scale/precision cần rounding thật thì phép chuyển sẽ ném lỗi.
- Lưu `BigDecimal` dưới dạng `DECIMAL(p,s)` trong database cần đối chiếu giới hạn **precision/scale** của cột và kiểm tra phía ứng dụng. Không nên giả định database sẽ luôn tự báo lỗi hoặc làm tròn theo chính sách Java.
- Khi nhận và xuất giá trị, phải thống nhất format, scale, đơn vị và chính sách xử lý số quá lớn hoặc quá nhiều chữ số.

## 11. Thiết kế miền số và ranh giới chuyển đổi

Thay vì cho phép mọi tầng tùy ý ép kiểu, nên mô tả các ranh giới rõ ràng:

```text
Dữ liệu lưu/nhập
    |
    | parse + kiểm tra miền, đơn vị, scale
    v
Kiểu tính toán trung gian đủ rộng/chính xác
    |
    | phép tính với kiểm tra overflow/rounding
    v
Kết quả nghiệp vụ
    |
    | kiểm tra giới hạn và chuyển kiểu exact
    v
Kiểu lưu trữ/DTO/schema đầu ra
```

Ví dụ với kho hàng:

- `quantityPerLine` có thể là `int` khi giới hạn mỗi dòng nhỏ và được validate.
- `totalQuantity` có thể là `long` nếu cộng nhiều dòng.
- `grandTotal` có thể dùng `BigDecimal` nếu áp giá, thuế, chiết khấu decimal.
- Dữ liệu lưu tổng có thể là `long` cents hoặc cột `DECIMAL(p,s)`, tùy schema/domain.
- Trước khi lưu, gọi phép chuyển exact hoặc validation; nếu vượt khả năng lưu, trả lỗi có ngữ cảnh, không cast và để sai dữ liệu.

Có thể đặt các phương thức `fromStorage(...)` và `toStorageExact(...)` trong kiểu domain hoặc adapter. Chúng chịu trách nhiệm thống nhất chính sách chuyển đổi, giúp tầng tính toán không phải biết DB dùng `BIGINT` hay `DECIMAL(18,2)`. Nếu một kết quả hợp lệ về nghiệp vụ nhưng không vừa kiểu lưu trữ, đó là dấu hiệu cần đánh giá lại **schema**, không mặc nhiên xóa phần dư để ép vừa.

### Đơn vị là một phần của hợp đồng

Hai giá trị kiểu `long` vẫn có thể hoàn toàn khác nghĩa:

```java
long amountCents = 1_234L;  // 12.34 đơn vị tiền lớn
long amountUnits = 1_234L;  // 1234 đơn vị tiền lớn
```

Cùng một kiểu primitive nhưng không thể cộng hoặc so sánh như thể cùng đơn vị. Với miền phức tạp, cân nhắc tạo `record`/class có tên và kiểm tra, chẳng hạn `MoneyCents`, `DurationMillis`, `Quantity`, thay vì chuyển đơn vị rải rác. Việc chuyển đơn vị có thể nhân gây overflow và phải sử dụng `Math.multiplyExact` hoặc kiểu rộng trước.

## 12. Cơ sở dữ liệu và giao diện trao đổi dữ liệu

Chọn kiểu lưu trữ cần xét đến các tầng bên ngoài Java.

| Nhu cầu | Kiểu tính toán có thể phù hợp | Kiểu lưu trữ có thể phù hợp | Rủi ro cần kiểm tra |
| --- | --- | --- | --- |
| Đếm sự kiện của từng ngày | `long` hoặc checked `BigInteger` nếu rất lớn | `BIGINT` | Tổng vượt `int` hoặc `long` |
| Tổng hợp số lượng từ nhiều dòng `int` | `long` | `INTEGER`/`BIGINT` tùy giới hạn tổng cuối | Cast thu hẹp làm sai số |
| Số tiền đơn vị nhỏ nhất | `long` cho cộng/nhân nguyên có kiểm tra; `BigDecimal` cho tỷ lệ | `BIGINT` cents | Mismatch đơn vị, overflow, rounding |
| Thuế/lãi/phí thập phân | `BigDecimal` | `DECIMAL(p,s)` hoặc đơn vị nhỏ nhất sau rounding | Mất scale, sai chính sách làm tròn |
| Thống kê xấp xỉ | `double` và thuật toán cộng phù hợp | `DOUBLE PRECISION` hoặc trường có quy ước precision | Sai số IEEE 754, NaN/Infinity |
| Số nguyên cực lớn | `BigInteger` | `DECIMAL(p,0)` đủ lớn hoặc chuỗi theo hợp đồng | Vượt precision/giới hạn schema |

`DECIMAL(12,2)` thông thường cho 12 chữ số precision, trong đó 2 chữ số thập phân, để lại tối đa 10 chữ số phần nguyên; cần xác nhận giới hạn cụ thể của database. Trước khi insert/update, kiểm tra kiểu lưu có đủ miền, scale và quy tắc rounding yêu cầu.

**JSON/JavaScript:** JavaScript `Number` cũng là số dấu phẩy động nhị phân (thường dùng IEEE 754 double). Nó không thể biểu diễn chính xác mọi số nguyên `long`. Với ID hoặc số nguyên vượt `Number.MAX_SAFE_INTEGER`, cân nhắc truyền chuỗi decimal hoặc encoding/schema có kiểu số nguyên lớn rõ ràng. Không giả định việc Java serialize một `long` thành JSON number giúp mọi client giữ được đầy đủ chữ số.

Tương tự, đổi từ `BigDecimal` sang `double` trước khi trả API có thể làm mất tính chính xác dù dữ liệu trong Java và DB vẫn đúng. Ranh giới giao tiếp cần hợp đồng riêng, không chỉ phụ thuộc vào kiểu nội bộ.

## 13. Tối ưu dung lượng và hiệu năng một cách có căn cứ

Kiểu lưu trữ nhỏ có thể giảm kích thước hoặc phù hợp schema, nhưng không nên tạo rủi ro tràn số trong xử lý chỉ để tiết kiệm bộ nhớ tạm.

Những câu hỏi đáng cân nhắc:

1. **Miền giá trị:** `int`, `long` hoặc `BigInteger` có đủ phạm vi cho phép tính lớn nhất?
2. **Độ chính xác:** phép tính cần exact decimal hay xấp xỉ nhị phân?
3. **Số bước làm tròn:** có thể trì hoãn rounding đến một ranh giới được xác định để giảm sai lệch?
4. **Tính bất biến/chi phí cấp phát:** `BigInteger` và `BigDecimal` là object immutable; phép toán tạo đối tượng mới và có chi phí so với primitive.
5. **Kiểu của collection/stream:** `IntStream.sum()` trả `int`; nếu cần `long` phải đổi bằng `mapToLong(...)` hoặc thuật toán tổng hợp phù hợp từ đầu.
6. **Khả năng quan sát lỗi:** dùng checked arithmetic và chuyển kiểu exact để phát hiện dữ liệu ngoài miền thay vì âm thầm sai.

Không tự tối ưu bằng cách giữ phép tính trong `int` nếu nghiệp vụ không thể bảo đảm miền. Nếu hiệu năng của `BigDecimal` là vấn đề đã đo được, có thể dùng đơn vị nguyên có scale cố định và checked arithmetic trong các bước phù hợp, đồng thời đảm bảo mọi phép áp tỷ lệ đều tuân theo rounding của domain.

## 14. Lỗi thường gặp

| Sai lầm | Hệ quả | Cách đúng |
| --- | --- | --- |
| `long total = intA * intB` | Tràn `int` trước khi gán | `(long) intA * intB`, hoặc `Math.multiplyExact` với kiểu rộng |
| `(long) (intA * intB)` | Ép sau khi mất dữ liệu | Thăng hạng **trước** phép nhân |
| `double mean = intSum / intCount` | Chia nguyên, mất phần lẻ | `(double) intSum / intCount` và kiểm tra count |
| `int result = (int) longResult` | Có thể đổi thành giá trị không liên quan | `Math.toIntExact(longResult)` |
| Dùng `double` cho tất cả tổng số nguyên lớn | Mất chữ số nguyên ngoài miền chính xác | Giữ `long`/`BigInteger` |
| Tính tiền bằng `double` rồi lưu cents | Sai số nhị phân và rounding khó kiểm soát | Dùng `BigDecimal` hoặc số nguyên đơn vị nhỏ nhất với hợp đồng rõ |
| Làm tròn tiền sau từng phép tính trung gian bất kể nghiệp vụ | Sai lệch tích lũy | Làm tròn tại ranh giới đã quy định |
| Dùng `BigDecimal.longValue()` để lưu không kiểm tra | Có thể bỏ phần lẻ/tràn | `longValueExact()` sau chuẩn hóa |
| Cho rằng `long` không thể tràn | Tổng/tích rất lớn có thể tràn | `Math.addExact`/`multiplyExact` hoặc `BigInteger` |
| Lưu `BigDecimal` vào `DECIMAL(p,s)` mà không validate | Rounding hoặc từ chối ngoài ý muốn | Kiểm tra precision/scale theo schema |
| Dùng cùng `long` cho cents và đơn vị lớn | Sai hệ số 100 | Kiểu domain/tên trường và chuyển đổi rõ ràng |
| Xuất `long` lớn qua JSON number và JavaScript `Number` | Client mất chữ số | Hợp đồng chuỗi decimal hoặc kiểu số lớn phù hợp |

## 15. Hướng dẫn chọn kiểu theo từng tình huống

**Tổng hợp số lượng:** nếu từng giá trị là `int` nhưng tổng có thể vượt `int`, tính bằng `long` ngay từ phép cộng; dùng checked addition nếu có nguy cơ vượt `long`. Chỉ lưu vào `int` sau khi `Math.toIntExact` thành công.

**Nhân số lượng với đơn giá:** xác định phạm vi lớn nhất của tích; nếu cả hai là `int` mà tích vượt `int`, ép một toán hạng sang `long` trước khi nhân. Với tích vượt `long`, dùng `BigInteger`. Kiểu lưu đơn giá có thể giữ nguyên nếu miền riêng vẫn phù hợp.

**Tỷ lệ hoặc trung bình:** nếu bài toán chỉ cần xấp xỉ, `double` và kiểm tra chia 0, NaN/Infinity là đủ trong nhiều trường hợp. Nếu cần chính xác decimal, dùng `BigDecimal`, nêu `scale` và `RoundingMode`, hoặc giữ tử/mẫu nguyên riêng cho đến khi cần làm tròn.

**Tiền tệ:** xác định đơn vị nhỏ nhất, đồng tiền, chính sách thuế/chiết khấu và rounding. Có thể lưu cents bằng `long` và dùng `BigDecimal` trung gian. Việc đổi về cents phải là phép kiểm tra exact; không giả định tất cả đồng tiền có hai chữ số.

**Giới hạn giao diện/API:** một giá trị Java lưu đúng trong `long`/`BigInteger` có thể vượt kiểu số của hệ thống nhận. Kiểm tra *toàn bộ đường đi*, không chỉ tính đúng trong Java.

**Giá trị có độ lớn biến thiên cực rộng:** tránh tràn trong biến trung gian khi tính bình phương hoặc lũy thừa. Có thể cần `BigInteger`/`BigDecimal`, hoặc một thuật toán khác tránh tạo kết quả trung gian quá lớn nếu kết quả cuối chỉ là phép so sánh.

## 16. Tự kiểm tra

1. **Vì sao `long x = 50_000 * 50_000` có thể sai?** Vì hai literal mặc định là `int`, phép nhân tràn trước khi gán. Dùng `50_000L * 50_000`.
2. **Ép `(long) (a * b)` có sửa được tràn `int` không?** Không. Phải mở rộng kiểu một toán hạng trước phép nhân.
3. **Nếu cần lưu kết quả `long` vào `int` mà không chấp nhận mất dữ liệu?** Dùng `Math.toIntExact` hoặc kiểm tra miền đầy đủ.
4. **Khi nào dùng `BigInteger`?** Khi phép tính nguyên cần chính xác và có thể vượt giới hạn `long`.
5. **Dùng `double` để chứa mọi số nguyên lớn có an toàn không?** Không; `double` không biểu diễn chính xác mọi số nguyên vượt 2^53.
6. **Vì sao tổng tiền có thể lưu cents bằng `long`, nhưng thuế được tính bằng `BigDecimal`?** Vì áp tỷ lệ tạo phần thập phân trung gian cần chính sách rounding; lưu cents chỉ phù hợp sau khi đã xử lý phần dư.
7. **`BigDecimal.longValueExact()` kiểm tra điều gì?** Giá trị phải là số nguyên chính xác và nằm trong miền `long`; không được lặng lẽ mất phần lẻ hoặc overflow.
8. **`IntStream.sum()` có tự đổi sang `long` khi tổng lớn không?** Không; nó trả `int`. Phải chọn phép tổng hợp `long` trước.
9. **Tại sao cần kiểm tra kiểu ở ranh giới JSON?** Vì số nguyên chính xác trong Java có thể không còn chính xác khi client dùng `Number`.
10. **Có nhất thiết mọi kiểu lưu trữ phải trùng với kiểu trung gian không?** Không; kiểu trung gian phục vụ độ đúng của phép tính, kiểu lưu phục vụ hợp đồng dữ liệu. Phải có phép chuyển đổi kiểm tra giữa hai tầng.

## 17. Ghi nhớ

**Chọn kiểu tính toán trung gian theo miền giá trị và độ chính xác lớn nhất của phép tính; chọn kiểu lưu trữ theo miền và biểu diễn của dữ liệu đã được chốt.** Kiểu của biến nhận không thay đổi kiểu đã dùng để đánh giá biểu thức. Muốn tránh tràn `int` phải thăng hạng trước phép toán; muốn phát hiện tràn hãy dùng checked arithmetic; muốn thu hẹp phải kiểm tra exact.

Đối với số nguyên lớn, dùng `long` hoặc `BigInteger` theo miền; đối với phép tính decimal chính xác, dùng `BigDecimal` và chính sách rounding rõ ràng; đối với số đo xấp xỉ, dùng `double` khi sai số đã được chấp nhận. Mọi chuyển đổi về schema lưu trữ, đơn vị nhỏ nhất và định dạng API phải được xem là một bước kiểm tra hợp đồng, tránh lưu dữ liệu “vừa kiểu” nhưng sai nghĩa.
