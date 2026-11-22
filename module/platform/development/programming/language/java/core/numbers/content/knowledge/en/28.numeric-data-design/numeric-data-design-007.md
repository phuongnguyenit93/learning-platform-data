# Tránh dùng `double` làm trung gian cho dữ liệu thập phân chính xác trong Java

Khi đầu vào đại diện cho tiền, đơn giá, thuế suất, tỷ lệ đã quy định theo chữ số thập phân hoặc số liệu cần đối soát chính xác, việc sử dụng `BigDecimal` **ở bước cuối** chưa đủ. Chỉ một lần chuyển **chuỗi thập phân → `double` → `BigDecimal`** có thể làm mất chữ số và khiến giá trị khác dữ liệu gốc. Tương tự, một phép nhân/cộng bằng `double` trước khi tạo `BigDecimal` đã mang theo các sai số nhị phân.

Nguyên tắc thiết kế: **Dữ liệu cần chính xác theo hệ thập phân phải đi qua một pipeline thập phân chính xác từ lúc tiếp nhận đến khi tính toán, kiểm tra, lưu và trả về.** Chuyển trực tiếp từ chuỗi decimal, số nguyên hoặc nguồn decimal có bảo đảm sang `BigDecimal`; tránh `double` trung gian trừ khi sai số xấp xỉ được hợp đồng cho phép.

Bài học phân tích lý do, chỉ ra điểm mất thông tin đầu tiên, so sánh constructor `BigDecimal`, đề xuất kiến trúc DTO/API và minh họa bằng Java 17+ có thể chạy.

## 1. `double` không giữ nguyên mọi số thập phân

Kiểu `double` trong Java là số dấu phẩy động nhị phân IEEE 754 binary64. Nó có độ chính xác hữu hạn theo cơ số 2. Các phân số như 1/2 và 1/4 có biểu diễn nhị phân hữu hạn, nhưng 1/10 không có. Vì vậy literal `0.1` được làm tròn sang một giá trị nhị phân gần nhất.

```java
double x = 0.1;
double y = 0.2;
System.out.println(x + y);
```

Stdout:

```text
0.30000000000000004
```

Đây không phải một lỗi ngẫu nhiên: các số `double` đầu vào và phép cộng được làm tròn theo quy tắc floating-point. Trong mô phỏng, xử lý ảnh hoặc đo đạc chấp nhận sai số, `double` hoàn toàn có ích. Nhưng nếu yêu cầu là giữ nguyên số decimal như `"0.1"` hoặc `"19.99"`, phải tách **mô hình số thực xấp xỉ** khỏi **mô hình decimal chính xác**.

`BigDecimal` biểu diễn giá trị dạng số nguyên không tỉ lệ (`unscaled value`) nhân với 10 mũ âm của `scale`. Khi được tạo trực tiếp từ chuỗi decimal, nó bảo toàn giá trị số mà chuỗi mô tả, không đi qua sự xấp xỉ binary64.

Ba loại giá trị thường bị nhầm:

- **Nguồn decimal:** ví dụ người dùng nhập chuỗi `"0.10000000000000001"`.
- **Số `double` sau parse:** một giá trị binary64 gần số đã nhập, không mang theo chuỗi nguồn.
- **`BigDecimal` được tạo sau bước parse:** decimal của chính số `double` đã có; không nhất thiết là decimal gốc.

Một khi hai chuỗi nguồn khác nhau đã trở thành cùng một giá trị `double`, thông tin phân biệt chúng mất vĩnh viễn trong nhánh xử lý đó.

## 2. Phản ví dụ: chuyển qua `double` làm mất giá trị decimal

Sai khi giá trị decimal đầu vào phải được giữ đúng:

```java
String input = "19.99";
double intermediate = Double.parseDouble(input);
BigDecimal amount = new BigDecimal(intermediate);
```

`Double.parseDouble` có thể làm tròn một số thập phân vào miền binary64. Constructor `new BigDecimal(double)` tạo ra decimal **chính xác của số binary64 đã được làm tròn**. Điều này khác với decimal do người gửi mô tả.

Ví dụ rõ nhất:

```java
System.out.println(new BigDecimal(0.1).toPlainString());
```

Stdout:

```text
0.1000000000000000055511151231257827021181583404541015625
```

Đây là giá trị thập phân chính xác của `double` gần số 0,1, **không phải** giá trị decimal 1/10. Constructor làm đúng chức năng của nó; sai lầm nằm ở việc dùng `double` làm trung gian không phù hợp.

Còn nghiêm trọng hơn, hai chuỗi decimal khác nhau có thể bị làm tròn thành cùng `double`:

```java
String source = "0.10000000000000001";
BigDecimal correct = new BigDecimal(source);
BigDecimal wrong = BigDecimal.valueOf(Double.parseDouble(source));

System.out.println(correct.toPlainString());
System.out.println(wrong.toPlainString());
```

Stdout:

```text
0.10000000000000001
0.1
```

Dù `wrong` có vẻ gọn và đẹp, nó **không còn bằng** số decimal ban đầu. Không có thuật toán nào có thể khôi phục chuỗi nguồn chỉ từ `double` trong mọi trường hợp, vì nhiều chuỗi decimal cùng ánh xạ về một giá trị floating-point.

Nếu đã nhận chuỗi đầu vào, hãy tạo trực tiếp:

```java
BigDecimal correct = new BigDecimal(source);
```

Không nên parse chuỗi decimal thành `double` với lý do “kiểm tra xem có phải số không”: nếu cần validation, có thể parse bằng `BigDecimal` rồi bắt `NumberFormatException` hoặc áp quy tắc định dạng/miền tương ứng.

## 3. Phân biệt `new BigDecimal(double)` và `BigDecimal.valueOf(double)`

| Cách tạo | Nguồn | Điều được bảo toàn | Dùng trong tình huống nào? |
| --- | --- | --- | --- |
| `new BigDecimal("0.1")` | Chuỗi thập phân | Giá trị decimal đúng như chuỗi, scale phù hợp với biểu diễn | Dữ liệu decimal cần chính xác |
| `new BigDecimal(0.1)` | `double` | Giá trị binary64 chính xác đang lưu | Phân tích biểu diễn binary64, không phải khôi phục nguồn |
| `BigDecimal.valueOf(0.1)` | `double` | Decimal theo `Double.toString(double)` | Chỉ còn giá trị `double` và cần biểu diễn decimal ngắn theo nghĩa đó |
| `BigDecimal.valueOf(100L)` | `long` | Số nguyên 100 chính xác | Số nguyên nguồn |
| `new BigDecimal(BigInteger)` | Số nguyên lớn | Số nguyên lớn chính xác | Khi `long` không đủ |

`BigDecimal.valueOf(double)` là lựa chọn thường hợp lý hơn constructor nhận `double` khi nguồn **thực sự chỉ có `double`** và ta muốn decimal dựa trên chuỗi round-trip chuẩn của `Double.toString`. Ví dụ:

```java
System.out.println(BigDecimal.valueOf(0.1).toPlainString()); // 0.1
```

Tuy vậy, việc kết quả trông giống literal decimal không chứng minh nó khớp **dữ liệu thập phân ban đầu**. Ví dụ `"0.10000000000000001"` trở thành `"0.1"` sau đường đi `Double.parseDouble` rồi `BigDecimal.valueOf`.

`valueOf` cũng không sửa những phép tính đã thực hiện trước đó bằng `double`:

```java
double calculated = 0.1 + 0.2;
BigDecimal late = BigDecimal.valueOf(calculated);
System.out.println(late.toPlainString());
```

Stdout:

```text
0.30000000000000004
```

Hãy chuyển **các toán hạng** sang `BigDecimal` từ nguồn decimal **trước phép cộng**:

```java
BigDecimal exact = new BigDecimal("0.1")
        .add(new BigDecimal("0.2"));
System.out.println(exact.toPlainString()); // 0.3
```

`BigDecimal.valueOf(long)` là overload **khác**: nó nhận số nguyên nguyên vẹn và không trải qua binary64, nên phù hợp với tiền được biểu diễn bằng số nguyên đơn vị nhỏ.

## 4. Xây dựng pipeline giữ decimal chính xác

Để một field tiền/thuế giữ đúng decimal, cần kiểm soát **mọi ranh giới chuyển kiểu**, không chỉ class ở tầng domain.

Đường đi dễ làm mất dữ liệu:

```text
JSON/CSV input chứa số decimal
  → parser chuyển sang double
  → DTO hoặc entity chứa double
  → cộng/nhân/chia bằng double
  → BigDecimal.valueOf(double)
  → database DECIMAL
```

Database có thể lưu chính xác một `BigDecimal`, nhưng đó là **giá trị của kết quả xấp xỉ đã xảy ra**, không phải dữ liệu decimal nguồn.

Đường đi đúng khi hợp đồng yêu cầu decimal chính xác:

```text
JSON token decimal hoặc chuỗi decimal gốc
  → parse trực tiếp sang BigDecimal
  → validate miền, đơn vị và độ phân giải
  → tính toán bằng BigDecimal
  → làm tròn tại thời điểm được quy định
  → lưu SQL DECIMAL/NUMERIC hoặc đơn vị nhỏ nguyên theo chuyển đổi exact
  → serialize về decimal theo schema
```

Có thể dùng một value object để bảo vệ invariant, ví dụ `Money` lưu cả mã tiền tệ và `BigDecimal`, hoặc lưu số nguyên đơn vị nhỏ (`long`) khi nghiệp vụ cho phép và miền biểu diễn được chứng minh đủ rộng. Trong cả hai cách, **không cần dùng `double` làm cầu nối**.

### JSON và frontend

JSON hỗ trợ ký pháp số decimal, nhưng cách parser và DTO ánh xạ quyết định giá trị có đi qua floating-point hay không. Nếu phần mềm deserialization đưa token vào `double` rồi mới dựng `BigDecimal`, có nguy cơ mất chính xác. Hãy dùng kiểu trường `BigDecimal` và cấu hình parse trực tiếp tương ứng với thư viện.

Client JavaScript thường dùng `Number` dựa trên binary64. Nếu input nhập tay `"19.99"` đã được chuyển thành `Number` rồi thực hiện nhiều phép tính, backend không thể khôi phục toàn bộ ý nghĩa decimal bằng cách nhận `BigDecimal`. Khi cần giữ chuỗi decimal nguyên vẹn, frontend có thể truyền chuỗi decimal qua một field có schema rõ ràng hoặc dùng thư viện decimal chính xác thích hợp. **Không tự đổi kiểu JSON number thành string mà không đồng bộ hợp đồng API.**

Số nguyên lớn cũng có rủi ro riêng: JavaScript `Number` không thể biểu diễn chính xác mọi số nguyên vượt `2^53 - 1`. Nếu API chuyển số tiền đơn vị nhỏ dạng `long` qua client JavaScript, cần xác định định dạng truyền và kiểm thử round-trip, không chỉ kiểm thử backend.

### JDBC, ORM và database

Cột `DECIMAL(p,s)` hoặc `NUMERIC(p,s)` phù hợp cho decimal chính xác trong phạm vi cấu hình. Khi đọc, ưu tiên mapping/getter decimal tương ứng như `BigDecimal` thay vì lấy `getDouble()` rồi chuyển kiểu tiếp. Nếu một cột vốn lưu floating-point, đọc nó dưới dạng `BigDecimal` sau này không giúp khôi phục số decimal trước khi dữ liệu đã bị xấp xỉ.

Kiểu SQL, precision, scale, đơn vị và miền số hợp lệ phải khớp với schema/API. Cột hỗ trợ 12 chữ số không đồng nghĩa nghiệp vụ cho phép mọi giá trị có 12 chữ số.

### CSV, cấu hình và bảng tính

CSV giữ văn bản của trường; nếu giá trị decimal được lưu nguyên văn, có thể parse trực tiếp bằng `BigDecimal(String)`. Tránh chế độ tự suy đoán kiểu thành `double` trong phần đọc import. Với bảng tính, giá trị hiển thị `19.99` chưa chứng minh giá trị nội bộ không được tính bằng floating-point; nếu nguồn đã mất chính xác từ trước, parse chuỗi hiển thị không cho phép khẳng định đã phục hồi nguyên bản dữ liệu.

Tất cả nơi nhập decimal cần thống nhất **dấu thập phân**, dấu phân nhóm, locale, ký hiệu tiền tệ và có chấp nhận biểu diễn dạng lũy thừa hay không. Constructor `BigDecimal(String)` không tự hiểu `"1,25"` là 1,25.

## 5. Tính toán thập phân đúng từ toán hạng đầu tiên

Giả sử có đơn giá `"19.90"`, số lượng 3 và thuế suất `"0.075"` (7,5%). Đừng viết:

```java
double unitPrice = 19.90;
double taxRate = 0.075;
double subtotal = unitPrice * 3;
BigDecimal total = BigDecimal.valueOf(subtotal * (1 + taxRate));
```

Dù kết quả cuối là `BigDecimal`, phép tính vẫn đã thực hiện bằng `double`. Giá trị trung gian và thời điểm làm tròn không được kiểm soát theo hợp đồng decimal.

Ví dụ đúng:

```java
BigDecimal unitPrice = new BigDecimal("19.90");
BigDecimal rate = new BigDecimal("0.075");
BigDecimal quantity = BigDecimal.valueOf(3L);

BigDecimal subtotal = unitPrice.multiply(quantity);
BigDecimal tax = subtotal.multiply(rate)
        .setScale(2, RoundingMode.HALF_UP);
BigDecimal total = subtotal.add(tax);

System.out.println(subtotal.toPlainString()); // 59.70
System.out.println(tax.toPlainString());      // 4.48
System.out.println(total.toPlainString());    // 64.18
```

Đây là đoạn minh họa cần import `java.math.BigDecimal` và `java.math.RoundingMode`, và đặt trong một phương thức. Phép nhân 59,70 × 0,075 = 4,47750; làm tròn thuế thành 4,48 theo **chính sách minh họa** `HALF_UP`.

Không có quy tắc làm tròn duy nhất phù hợp cho mọi lĩnh vực. Có sản phẩm làm tròn mỗi dòng hóa đơn, có sản phẩm làm tròn sau khi cộng các dòng. Hai chính sách đều có thể dùng `BigDecimal` nhưng cho kết quả khác nhau vì thời điểm làm tròn.

### Chia số và `MathContext`

`BigDecimal.add`, `subtract` và `multiply` không nhận `MathContext` có thể thực hiện chính xác theo decimal. Phép chia đôi khi có kết quả thập phân vô hạn, ví dụ 1/3:

```java
BigDecimal third = BigDecimal.ONE.divide(
        new BigDecimal("3"), 4, RoundingMode.HALF_UP);
// 0.3333
```

Nếu gọi `BigDecimal.ONE.divide(new BigDecimal("3"))` không chỉ định cách làm tròn, Java ném `ArithmeticException` vì kết quả decimal không kết thúc. `MathContext` cũng có thể dùng để quản lý precision và rounding theo hợp đồng, nhưng **không thể phục hồi chữ số nguồn đã mất ở một `double` trước đó**.

Đặc tả nghiệp vụ nên ghi rõ độ phân giải, precision, `RoundingMode` và thời điểm áp dụng.

## 6. Scale, biểu diễn và độ phân giải không phải một khái niệm

```java
BigDecimal a = new BigDecimal("1.0");
BigDecimal b = new BigDecimal("1.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
System.out.println(b.scale());           // 2
```

Hai giá trị cùng số học nhưng khác `scale`. `compareTo` chỉ so giá trị số; `equals` còn kiểm tra scale. Nếu một trường có hợp đồng giữ nguyên số chữ số thập phân người dùng nhập, việc đưa giá trị qua `double` có thể phá cả thông tin biểu diễn đó: từ `"1.000"` qua `double` bạn không thể biết nguồn ban đầu có mấy số 0.

Cần phân biệt:

1. **Đúng giá trị decimal:** `"1.0"` và `"1.00"` bằng nhau theo số học.
2. **Độ phân giải/scale nghiệp vụ:** ví dụ chấp nhận giá trị biểu diễn được chính xác tới 0,01.
3. **Đúng định dạng văn bản:** có cần giữ nguyên chính chuỗi `"1.00"` hay không?

Để kiểm tra số tiền có thể biểu diễn không mất mát ở scale 2:

```java
BigDecimal accepted = new BigDecimal("1.230")
        .setScale(2, RoundingMode.UNNECESSARY);
// accepted.toPlainString() là "1.23".
```

Giá trị `"1.234"` không thể giảm scale về 2 mà không thay đổi giá trị số, nên `RoundingMode.UNNECESSARY` ném `ArithmeticException`. Nếu hợp đồng **cho phép** rounding, hãy chỉ định mode chính xác thay vì âm thầm giảm chữ số.

`BigDecimal` có thể giữ scale âm; vì vậy “scale” không đơn giản là đếm ký tự sau dấu chấm của một chuỗi bất kỳ. Khi hợp đồng cần kiểm soát biểu diễn đầu vào, xác thực cả cú pháp chuỗi và giá trị numeric nếu cần.

## 7. Khi có thể lưu thành số nguyên đơn vị nhỏ

Một cách tránh floating-point cho giá trị decimal có độ phân giải cố định là chuyển **trực tiếp từ decimal nguồn** sang số nguyên đếm đơn vị nhỏ. Ví dụ giả định một đơn vị lớn bằng 100 đơn vị nhỏ:

```java
BigDecimal amount = new BigDecimal("12.30")
        .setScale(2, RoundingMode.UNNECESSARY);

long minorUnits = amount.movePointRight(2).longValueExact();
System.out.println(minorUnits); // 1230
```

`movePointRight(2)` nhân 100 theo decimal; `longValueExact()` từ chối khi có phần lẻ còn lại hoặc vượt giới hạn `long`. Cách này khác hoàn toàn với:

```java
double amount = Double.parseDouble("12.30");
long minorUnits = (long) (amount * 100); // Không nên dùng khi cần exact.
```

Phép nhân floating-point có thể tạo giá trị hơi thấp/hơi cao so với số nguyên dự kiến; ép `(long)` có thể bỏ phần lẻ âm thầm.

Hệ số 100 **không phải quy tắc chung cho mọi đồng tiền**. Nếu phần mềm đa tiền tệ, phải gắn mã tiền tệ và thang đơn vị tương ứng; không cộng các số nguyên minor units của các đồng tiền khác nhau nếu chưa có bước quy đổi có chính sách rõ ràng.

Trước khi lưu sang `long`, cũng cần kiểm tra miền min/max của nghiệp vụ: `longValueExact()` chỉ bảo đảm **chuyển đổi nguyên chính xác**, không tự biết giá âm có được phép hay số tiền có vượt hạn mức giao dịch không.

## 8. Chương trình Java 17+ chạy đầy đủ

Chương trình sau minh họa cách mất dữ liệu decimal khi qua `double`, phép tính chính xác khi tạo toán hạng đúng lúc và việc từ chối giá sai độ phân giải. Chính sách ví dụ: đơn giá không âm, tối đa 1.000.000 đơn vị lớn, biểu diễn được theo bước 0,01; thuế suất từ 0 đến 1 và thuế được làm tròn `HALF_UP` tới hai chữ số decimal.

Lưu tệp **`ExactDecimalPipelineDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public final class ExactDecimalPipelineDemo {
    private static final BigDecimal MAX_AMOUNT =
            new BigDecimal("1000000.00");

    private ExactDecimalPipelineDemo() {}

    static BigDecimal parseAmount(String text) {
        Objects.requireNonNull(text, "amount text");
        BigDecimal amount = new BigDecimal(text)
                .setScale(2, RoundingMode.UNNECESSARY);
        if (amount.signum() < 0 || amount.compareTo(MAX_AMOUNT) > 0) {
            throw new IllegalArgumentException("amount out of range");
        }
        return amount;
    }

    static BigDecimal parseRate(String text) {
        Objects.requireNonNull(text, "rate text");
        BigDecimal rate = new BigDecimal(text);
        if (rate.signum() < 0 || rate.compareTo(BigDecimal.ONE) > 0) {
            throw new IllegalArgumentException("rate out of range");
        }
        return rate;
    }

    public static void main(String[] args) {
        String raw = "0.10000000000000001";
        BigDecimal original = new BigDecimal(raw);
        BigDecimal afterDouble =
                BigDecimal.valueOf(Double.parseDouble(raw));

        System.out.println("raw decimal = " + original.toPlainString());
        System.out.println("after double = " + afterDouble.toPlainString());
        System.out.println("value changed = "
                + (original.compareTo(afterDouble) != 0));

        System.out.println("double constructor = "
                + new BigDecimal(0.1).toPlainString());
        System.out.println("valueOf double = "
                + BigDecimal.valueOf(0.1).toPlainString());

        double binarySum = 0.1 + 0.2;
        BigDecimal decimalSum = new BigDecimal("0.1")
                .add(new BigDecimal("0.2"));
        System.out.println("binary sum converted = "
                + BigDecimal.valueOf(binarySum).toPlainString());
        System.out.println("decimal sum = "
                + decimalSum.toPlainString());

        BigDecimal unitPrice = parseAmount("19.90");
        BigDecimal subtotal =
                unitPrice.multiply(BigDecimal.valueOf(3L));
        BigDecimal rate = parseRate("0.075");
        BigDecimal tax = subtotal.multiply(rate)
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal total = subtotal.add(tax);

        System.out.println("subtotal = " + subtotal.toPlainString());
        System.out.println("tax = " + tax.toPlainString());
        System.out.println("total = " + total.toPlainString());
        System.out.println("minor units = "
                + total.movePointRight(2).longValueExact());

        System.out.println("input scale = "
                + new BigDecimal("1.2300").scale());
        System.out.println("normalized scale = "
                + parseAmount("1.2300").scale());

        try {
            parseAmount("19.999");
            System.out.println("extra precision = accepted");
        } catch (ArithmeticException ex) {
            System.out.println("extra precision = rejected");
        }

        try {
            parseAmount("-0.01");
            System.out.println("negative amount = accepted");
        } catch (IllegalArgumentException ex) {
            System.out.println("negative amount = rejected");
        }

        BigDecimal largeExact =
                new BigDecimal("9007199254740993");
        BigDecimal largeViaDouble = BigDecimal.valueOf(
                Double.parseDouble("9007199254740993"));
        System.out.println("large decimal changed = "
                + (largeExact.compareTo(largeViaDouble) != 0));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ExactDecimalPipelineDemo.java
java ExactDecimalPipelineDemo
```

Stdout chính xác:

```text
raw decimal = 0.10000000000000001
after double = 0.1
value changed = true
double constructor = 0.1000000000000000055511151231257827021181583404541015625
valueOf double = 0.1
binary sum converted = 0.30000000000000004
decimal sum = 0.3
subtotal = 59.70
tax = 4.48
total = 64.18
minor units = 6418
input scale = 4
normalized scale = 2
extra precision = rejected
negative amount = rejected
large decimal changed = true
```

Giải thích kết quả:

- Decimal nguồn `"0.10000000000000001"` còn nguyên khi parse trực tiếp nhưng đổi thành `0.1` sau `Double.parseDouble` rồi `BigDecimal.valueOf`.
- Constructor `new BigDecimal(0.1)` hiển thị dãy decimal đầy đủ của binary64; `valueOf(0.1)` rút về `0.1`, nhưng không phải công cụ khôi phục chuỗi nguồn.
- Chuyển `double` sau khi cộng `0.1 + 0.2` vẫn thu được `0.30000000000000004`; cộng hai `BigDecimal` tạo trực tiếp từ chuỗi cho `0.3`.
- Giá 19,90 nhân 3 bằng 59,70; thuế 7,5% là 4,47750, làm tròn theo chính sách ví dụ thành 4,48; tổng 64,18 và chuyển chính xác thành 6.418 đơn vị nhỏ.
- Chuỗi `"1.2300"` có scale 4; có thể chuẩn hóa thành scale 2 mà không đổi giá trị số. Chuỗi `"19.999"` không thể chuẩn hóa chính xác sang hai chữ số nên bị từ chối.
- Số `9007199254740993` lớn hơn miền số nguyên liên tiếp biểu diễn chính xác của binary64, vì thế nếu parse qua `double`, `BigDecimal` sau đó không thể lấy lại đúng giá trị.

## 9. Kiểm thử dữ liệu từ nguồn đến đích

Khi viết test cho yêu cầu decimal chính xác, **giá trị expected phải xuất phát từ chuỗi decimal gốc** hoặc một phép tính decimal độc lập, không xuất phát từ chính biểu thức `double` cần kiểm thử.

| Đầu vào/thao tác | Mong đợi |
| --- | --- |
| `"0.1"` → `new BigDecimal(text)` | Chính xác 0,1 |
| `"0.1"` → `new BigDecimal(Double.parseDouble(text))` | Decimal của binary64 gần 0,1, không bằng số gốc |
| `"0.10000000000000001"` qua `double` | Có thể thành decimal `0.1`; khác nguồn |
| `BigDecimal("0.1") + BigDecimal("0.2")` | `0.3` |
| `BigDecimal.valueOf(0.1 + 0.2)` | `0.30000000000000004` |
| `"1.2300"` | Giữ scale gốc hoặc chuẩn hóa rõ theo hợp đồng |
| `"19.999"` với bước 0,01 | Từ chối, hoặc làm tròn theo chính sách được quy định |
| `"-0.01"` ở field không âm | Từ chối theo miền nghiệp vụ |
| `"9007199254740993"` qua `double` | Mất khả năng giữ số nguyên chính xác |
| Dữ liệu `DECIMAL` lấy qua `getDouble()` | Có thể làm tròn decimal gốc |
| Giá từ JSON qua JavaScript `Number` | Kiểm tra nguy cơ chuyển đổi trước khi gửi |
| Một giá trị decimal chuyển sang minor units | Dùng phép decimal và chuyển kiểu exact, không qua `double` |

Kiểm thử tích hợp nên bao phủ cả đường đi **request → DTO → domain → phép tính → database → response**. Khi có khác biệt, tìm bước đầu tiên sử dụng `double`, `float`, `doubleValue()`, `Double.parseDouble()`, `getDouble()`, cột floating, phép tính nhị phân hoặc parser tự chọn `Number`.

Đối với dữ liệu cũ đã sai do floating-point, `setScale(2, ...)` có thể làm kết quả trông hợp lý nhưng **không chứng minh được số nguồn ban đầu**. Nếu phải hiệu chỉnh dữ liệu lịch sử, đối chiếu nguồn có thẩm quyền hoặc quy tắc nghiệp vụ riêng; không tự giả định mọi giá sau rounding bằng số người dùng đã gửi.

### Chẩn đoán nhanh

Trước khi sửa, hãy hỏi:

1. Dữ liệu decimal bắt đầu từ **chuỗi**, từ `BigDecimal`, từ số nguyên hay từ `double`?
2. Có chuỗi → `Double.parseDouble` → `BigDecimal` ở bất kỳ chỗ nào không?
3. Phép cộng, nhân, chia có dùng `double` trước khi lưu kết quả?
4. `BigDecimal.valueOf(double)` chỉ đang chuyển một `double` có sẵn hay đang được xem nhầm như cách khôi phục decimal?
5. Đơn vị, miền, scale, rounding mode và thời điểm rounding đã được ghi trong hợp đồng chưa?
6. JSON/JavaScript và SQL/ORM có thay đổi kiểu thành floating-point trung gian không?
7. Có kiểm thử số khó như 0,1; 0,1 + 0,2; decimal nhiều chữ số; giá có số 0 cuối; số nguyên vượt \(2^{53}\) chưa?

## 10. Những lỗi phổ biến và cách tránh

1. **“`double` chỉ để parse, sau đó dùng `BigDecimal` là đủ.”** Không đúng: parse đã có thể làm mất chữ số.
2. **“`new BigDecimal(0.1)` có nghĩa decimal 0,1.”** Nó biểu diễn decimal của một số binary64 xấp xỉ 0,1.
3. **“`BigDecimal.valueOf(d)` luôn khôi phục decimal gốc.”** Nó dùng `Double.toString(d)` và không đảo được phép làm tròn từ nhiều nguồn.
4. **“Cộng bằng `double` trước, chuyển sang `BigDecimal` sau sẽ chính xác.”** Kết quả `0.30000000000000004` chứng minh điều ngược lại.
5. **“Một biến DTO kiểu `double` không ảnh hưởng vì domain dùng `BigDecimal`.”** Thông tin có thể đã mất ngay tại DTO.
6. **“Gọi `setScale(2)` sẽ sửa mọi lỗi decimal.”** Rounding/normalization có thể thay đổi số hoặc che giấu sai sót, không khôi phục nguồn.
7. **“`BigDecimal.equals` và `compareTo == 0` giống nhau.”** `equals` xét thêm scale.
8. **“Dùng `(long)(doubleAmount*100)` là cách an toàn lấy cent.”** Có thể mất chính xác và cast bỏ phần lẻ không báo lỗi.
9. **“JSON number luôn giữ toàn bộ chữ số decimal.”** Điều đó phụ thuộc parser và kiểu dữ liệu từng client/server.
10. **“Không bao giờ được dùng `double`.”** Nếu miền nghiệp vụ chấp nhận đo lường xấp xỉ, `double` có thể là lựa chọn đúng. Vấn đề là dùng nó **trong pipeline đòi hỏi decimal chính xác**.

## 11. Checklist áp dụng trước khi phát hành

- Xác định nguồn có cần **giá trị thập phân chính xác** hay chỉ là phép đo xấp xỉ.
- Nhận/parsing trực tiếp thành `BigDecimal` từ chuỗi hoặc kiểu decimal chính xác, không qua `double`.
- Kiểm tra toàn bộ DTO, serializer, mapper, ORM, JDBC, CSV và client để loại bỏ conversion floating-point không chủ đích.
- Thực hiện cộng, trừ, nhân, chia bằng `BigDecimal` khi hợp đồng cần decimal chính xác.
- Ghi rõ scale/độ phân giải, miền min/max, đơn vị, rounding mode và **thời điểm** làm tròn.
- Nếu chuyển thành số nguyên đơn vị nhỏ, dùng `movePointRight` và `longValueExact()`/`intValueExact()`.
- Kiểm thử trường hợp decimal không biểu diễn được bằng binary64, số nguyên lớn, nhiều chữ số sau dấu, dữ liệu vượt miền và round-trip qua client/database.
- Nếu phát hiện sai số, tìm **bước đầu tiên** mất thông tin, không cố sửa ở bước cuối bằng một phép cast hoặc rounding tùy ý.

**Kết luận:** Việc chọn `BigDecimal` chỉ có ý nghĩa đầy đủ khi **dữ liệu không bị chuyển qua `double` trên đường tới nó**. Giữ decimal từ nguồn, tính trong decimal, kiểm tra miền/độ phân giải rõ ràng và chỉ làm tròn khi hợp đồng yêu cầu.

### Tài liệu Java chính thức

- [`BigDecimal`: constructor, `valueOf`, phép toán và scale](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [`Double`: `parseDouble`, `toString`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Double.html)
- [`RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
- [JLS §4.2.3: Floating-point types and values](https://docs.oracle.com/javase/specs/jls/se21/html/jls-4.html#jls-4.2.3)