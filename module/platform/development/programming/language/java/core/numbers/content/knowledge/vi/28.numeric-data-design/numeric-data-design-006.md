# Đưa precision, scale và rounding vào hợp đồng thiết kế dữ liệu số trong Java

## 1. Tại sao đây phải là hợp đồng, không chỉ là lựa chọn định dạng?

Một trường số như `amount`, `price`, `rate`, `distance` hoặc `quantity` không được định nghĩa đầy đủ chỉ bằng câu “kiểu `BigDecimal`”. Hai hệ thống đều dùng `BigDecimal` nhưng có thể bất đồng về số chữ số cho phép, ngưỡng lớn nhất và cách làm tròn. Kết quả: lỗi nhập dữ liệu, chênh lệch một đơn vị tiền nhỏ nhất khi đối soát, thay đổi ngoài ý muốn lúc ghi database, hoặc khác biệt giữa các endpoint.

Khi thiết kế dữ liệu số, cần coi ba yếu tố sau là **một phần hợp đồng công khai**:

- **Precision (độ chính xác chữ số):** tổng số chữ số có nghĩa mà giá trị được phép chứa.
- **Scale (vị trí thập phân):** số chữ số bên phải dấu thập phân trong biểu diễn `BigDecimal` (scale có thể âm).
- **Rounding (chính sách làm tròn):** điều gì xảy ra nếu phép tính hay dữ liệu đầu vào không thể biểu diễn tại precision/scale yêu cầu.

Ngoài ra hợp đồng thực tế còn phải nêu **đơn vị, miền giá trị, cách xử lý null, quy tắc parse/serialize, thứ tự thao tác và thời điểm làm tròn**. Không thể chỉ nhìn một câu `setScale(2)` mà suy ra tất cả các điều trên.

Ví dụ hợp đồng cụ thể:

> `totalAmount`: tiền theo một đơn vị tiền tệ đã xác định, không âm, tối đa 10 chữ số phần nguyên và 2 chữ số phần thập phân; dữ liệu phải biểu diễn chính xác tới đơn vị 0.01; không âm thầm làm tròn khi nhận input. Khi tính thuế, chỉ làm tròn đến 2 chữ số **ở bước tính thuế của dòng hóa đơn**, sử dụng `HALF_EVEN`. Khi xuất API, chuỗi decimal phải giữ chính xác 2 chữ số thập phân.

Chính sách này có thể diễn đạt bằng `DECIMAL(12,2)` ở cơ sở dữ liệu và `BigDecimal` trong Java, **nhưng hai khai báo đó chưa đủ để định nghĩa toàn bộ quy trình tính**. Phải bổ sung validation, thời điểm rounding và định dạng truyền dữ liệu.

## 2. Precision, scale và unscaled value của `BigDecimal`

Một đối tượng `BigDecimal` được mô tả về mặt giá trị bởi:

```text
value = unscaledValue × 10^(-scale)
```

Ví dụ:

| Chuỗi dùng để khởi tạo | `unscaledValue()` | `scale()` | `precision()` | Giá trị số học |
|---|---:|---:|---:|---:|
| `"123.45"` | `12345` | `2` | `5` | 123.45 |
| `"123.450"` | `123450` | `3` | `6` | 123.45 |
| `"0.00"` | `0` | `2` | `1` | 0 |
| `"1E+3"` | `1` | `-3` | `1` | 1000 |
| `"0.001"` | `1` | `3` | `1` | 0.001 |

`precision()` là số chữ số của phần *unscaled value* (theo quy tắc của `BigDecimal`), **không phải số chữ số sau dấu chấm**. `scale()` là độ dịch thập phân, **không phải số chữ số có nghĩa**. Precision của zero bằng 1.

Cùng giá trị số học có thể có precision và scale khác nhau:

```java
BigDecimal a = new BigDecimal("2.0");
BigDecimal b = new BigDecimal("2.00");

System.out.println(a.compareTo(b) == 0); // true
System.out.println(a.equals(b));         // false
```

`compareTo` so sánh giá trị số học. `equals` của `BigDecimal` còn đòi **cùng scale**. Vì vậy, khi hợp đồng cần bảo toàn cách biểu diễn (ví dụ input phải có đúng 2 chữ số thập phân), phép so sánh `compareTo` không đủ để kiểm tra chi tiết đó.

**Ghi nhớ:** `DECIMAL(12,2)` trong database thường thể hiện tối đa 12 chữ số theo precision và scale 2 (tương ứng tối đa 10 chữ số phần nguyên). Nó không đồng nghĩa “12 chữ số bên trái dấu chấm và 2 chữ số bên phải”. Hành vi lưu/round khi vượt scale có thể khác nhau giữa các hệ CSDL và cấu hình; ứng dụng phải xác nhận rõ thay vì phó mặc driver/database quyết định.

## 3. `setScale` và `MathContext`: hai loại giới hạn khác nhau

### 3.1. `setScale(newScale, mode)`: điều chỉnh số chữ số thập phân

`setScale` tạo một `BigDecimal` với scale yêu cầu. Nếu tăng scale, Java bổ sung số 0 mà không thay đổi giá trị số học; nếu giảm scale, có thể phải làm tròn:

```java
new BigDecimal("12.3").setScale(2); // 12.30
new BigDecimal("12.345").setScale(2, RoundingMode.HALF_UP); // 12.35
```

Nếu giảm scale mà sẽ mất chữ số có nghĩa và không truyền rounding mode phù hợp, phép thay đổi chính xác không thể thực hiện. `setScale(2, RoundingMode.UNNECESSARY)` là cách **xác thực giá trị có thể biểu diễn đến 2 chữ số thập phân mà không làm tròn**.

Điểm khác nhau quan trọng:

- `new BigDecimal("12.300").setScale(2, UNNECESSARY)` thành công: kết quả `12.30`, phần bị bỏ chỉ là zero.
- `new BigDecimal("12.301").setScale(2, UNNECESSARY)` ném `ArithmeticException`: việc bỏ chữ số 1 sẽ mất giá trị.
- `new BigDecimal("12.3").setScale(2, UNNECESSARY)` thành công: thêm zero thành `12.30`.

Do đó, `UNNECESSARY` kiểm tra **khả năng biểu diễn chính xác**, không kiểm tra input có **chính xác** 2 chữ số trên văn bản hay không. Hai hợp đồng này phải phân biệt.

### 3.2. `MathContext(precision, mode)`: giới hạn tổng chữ số có nghĩa

`MathContext` đưa một precision áp dụng cho kết quả thao tác `BigDecimal`, cùng rounding mode. Ví dụ:

```java
BigDecimal x = new BigDecimal("123.456");

System.out.println(x.setScale(2, RoundingMode.HALF_EVEN)); // 123.46
System.out.println(x.round(new MathContext(4, RoundingMode.HALF_EVEN))); // 123.5
```

`setScale(2)` giữ **2 chữ số bên phải dấu chấm**; `MathContext(4)` giữ **4 chữ số có nghĩa trên toàn giá trị**. Đây là hai mục tiêu khác nhau, không thể dùng thay thế nhau.

`MathContext.UNLIMITED` có precision bằng 0, nghĩa là không giới hạn precision của phép toán mà nó áp dụng; nó **không có nghĩa** phép chia không kết thúc như `1/3` có thể biểu diễn chính xác hữu hạn. Đối với `BigDecimal.ONE.divide(new BigDecimal("3"))` không có rounding/scale, Java ném `ArithmeticException` vì thương không có biểu diễn thập phân hữu hạn.

### 3.3. Những kết quả dễ hiểu sai

| Phép toán | Kết quả / hành vi |
|---|---|
| `new BigDecimal("123.450").precision()` | `6` |
| `new BigDecimal("123.450").scale()` | `3` |
| `new BigDecimal("2.3").setScale(2)` | `2.30` |
| `new BigDecimal("2.345").setScale(2, HALF_UP)` | `2.35` |
| `new BigDecimal("2.345").setScale(2, HALF_EVEN)` | `2.34` |
| `new BigDecimal("2.355").setScale(2, HALF_EVEN)` | `2.36` |
| `new BigDecimal("123.456").round(MathContext(4, HALF_EVEN))` | `123.5` |

Chỉ sử dụng `MathContext` nếu hợp đồng nêu rõ precision trên **kết quả phép toán**; chỉ sử dụng `setScale` nếu muốn điều chỉnh **số chữ số thập phân**. Nhiều ứng dụng tiền tệ cần cả miền precision/scale của **giá trị lưu trữ**, nhưng ở mỗi phép tính trung gian không nhất thiết được làm tròn đến precision đó.

## 4. RoundingMode: quy tắc nghiệp vụ bắt buộc phải đặt tên

`java.math.RoundingMode` gồm nhiều chế độ. Khi không thể giữ nguyên số chữ số theo precision/scale mong muốn, cách làm tròn quyết định kết quả:

| Mode | Ý nghĩa | `2.345` → 2 chữ số | `-2.345` → 2 chữ số |
|---|---|---:|---:|
| `UP` | Ra xa 0 | 2.35 | -2.35 |
| `DOWN` | Về 0 | 2.34 | -2.34 |
| `CEILING` | Về +∞ | 2.35 | -2.34 |
| `FLOOR` | Về -∞ | 2.34 | -2.35 |
| `HALF_UP` | Gần nhất; ở đúng giữa thì xa 0 | 2.35 | -2.35 |
| `HALF_DOWN` | Gần nhất; ở đúng giữa thì về 0 | 2.34 | -2.34 |
| `HALF_EVEN` | Gần nhất; ở đúng giữa thì chữ số giữ lại cuối là chẵn | 2.34 | -2.34 |
| `UNNECESSARY` | Không cho phép làm tròn | Ngoại lệ | Ngoại lệ |

Lưu ý các cột kết quả trên giả định **đúng giá trị thập phân được tạo từ chuỗi** `"2.345"` và `"-2.345"`. Với `2.355`, mode `HALF_EVEN` cho `2.36`, vì chữ số hàng phần trăm giữ lại là 6 (chẵn). `HALF_EVEN` thường gọi là *banker's rounding*, nhưng việc phù hợp hay không còn tùy luật, chuẩn kế toán hoặc quy tắc sản phẩm.

Cách viết **không có rounding mode** thường là thiếu hợp đồng. Đặc biệt cần xác định:

- Khi nào **từ chối** đầu vào có nhiều chữ số hơn cho phép?
- Khi nào **được phép làm tròn**?
- Làm tròn ở bước nào: từng đơn giá, từng dòng, trước/sau thuế, hay chỉ cuối hóa đơn?
- Dùng mode nào, do ai quy định và có thay đổi theo loại phí/đơn vị tiền tệ không?

**Tránh** dùng `RoundingMode.DOWN` chỉ vì từ “down” nghe giống làm tròn xuống: với số âm, `DOWN` là **về 0**, trong khi `FLOOR` là về âm vô cực.

## 5. Hợp đồng số phải mô tả cả đơn vị, miền và cách biểu diễn

Một ví dụ về đặc tả dành cho API `POST /payments`:

| Thuộc tính hợp đồng | Ví dụ được quy định |
|---|---|
| Tên trường | `amount` |
| Đơn vị | Một loại tiền tệ được xác định, không suy đoán theo locale |
| Miền hợp lệ | `0.00 ≤ amount ≤ 9,999,999,999.99` |
| Giới hạn lưu trữ | `precision ≤ 12`, `scale = 2` sau chuẩn hóa |
| Quy tắc input | Chấp nhận nếu **chính xác** đến 0.01; `19.900` có thể chuẩn hóa thành `19.90`, `19.999` bị từ chối |
| Rounding khi nhận input | `UNNECESSARY` (cấm mất chữ số có nghĩa) |
| Rounding khi tính thuế | `HALF_EVEN` ở bước tính thuế theo dòng đã định |
| Cách xuất | Chuỗi thập phân `"19.90"`; không ép về `double` |
| Null / dữ liệu thiếu | Bị từ chối nếu `amount` bắt buộc |
| Overflow | Bị từ chối nếu tổng cuối vượt miền hỗ trợ |

Đây là **một ví dụ chính sách**, không phải luật chung cho mọi tiền tệ. Những đơn vị không có phần thập phân hoặc có số chữ số thập phân khác phải đặt scale theo cấu hình riêng. Miền hợp lệ, xử lý hoàn tiền (số âm), số học thuế và cách báo lỗi cũng cần tuân thủ yêu cầu thực tế.

**Hợp đồng ngữ nghĩa** và **hợp đồng định dạng** có thể khác nhau:

- Hợp đồng ngữ nghĩa “giá trị là bội số chính xác của 0.01” có thể chấp nhận `"19.900"` và chuẩn hóa về `19.90`.
- Hợp đồng văn bản “client **phải gửi chính xác 2 chữ số** sau dấu chấm” sẽ từ chối `"19.900"`, dù giá trị số học tương đương.

Muốn áp dụng hợp đồng định dạng, kiểm tra chuỗi đầu vào theo format đã công bố trước khi parse; không thể chỉ dựa vào `setScale(2, UNNECESSARY)` để xác nhận số chữ số có mặt trong văn bản gốc.

## 6. Ví dụ Java 17+ hoàn chỉnh: validate theo hợp đồng rồi chuẩn hóa

Bên dưới là ví dụ chính sách **số tiền không âm, tối đa 12 chữ số với scale 2**. Đầu vào có thể chứa nhiều zero ở cuối nhưng tuyệt đối không bị bỏ chữ số có nghĩa để vừa scale.

**Tệp `MoneyContractDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class MoneyContractDemo {
    private static final int SCALE = 2;
    private static final int PRECISION = 12;

    public static BigDecimal parseAmount(String input) {
        Objects.requireNonNull(input, "amount");

        // Giới hạn độ dài input trước khi parse để tránh dữ liệu quá lớn.
        if (input.length() > 100) {
            throw new IllegalArgumentException("Amount is too long");
        }

        BigDecimal parsed;
        try {
            parsed = new BigDecimal(input);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException("Invalid decimal", ex);
        }

        BigDecimal normalized;
        try {
            normalized = parsed.setScale(SCALE, RoundingMode.UNNECESSARY);
        } catch (ArithmeticException ex) {
            throw new IllegalArgumentException("Fractional cent", ex);
        }

        if (normalized.signum() < 0 || normalized.precision() > PRECISION) {
            throw new IllegalArgumentException("Amount outside contract");
        }

        return normalized;
    }

    private static void test(String input) {
        try {
            System.out.println(input + " -> " + parseAmount(input));
        } catch (IllegalArgumentException ex) {
            System.out.println(input + " -> REJECTED");
        }
    }

    public static void main(String[] args) {
        test("19.90");
        test("19.900");
        test("0");
        test("19.999");
        test("10000000000.00");
        test("-1.00");
        test("9999999999.99");
    }
}
```

Biên dịch và chạy:

```bash
javac MoneyContractDemo.java
java MoneyContractDemo
```

Kết quả:

```text
19.90 -> 19.90
19.900 -> 19.90
0 -> 0.00
19.999 -> REJECTED
10000000000.00 -> REJECTED
-1.00 -> REJECTED
9999999999.99 -> 9999999999.99
```

Giải thích:

1. **Parse bằng `new BigDecimal(String)`** để giữ giá trị thập phân mà client gửi. Không parse thành `double` trước.
2. **`setScale(2, UNNECESSARY)`** kiểm tra có mất phần có nghĩa hay không. `19.900` chuyển thành `19.90` mà không mất giá trị; `19.999` bị từ chối.
3. **`signum()`** từ chối số âm theo miền đã chọn.
4. **`precision() <= 12` sau khi scale đã được chuẩn hóa**: kết quả không có quá 12 chữ số có nghĩa, phù hợp miền `DECIMAL(12,2)` cho những giá trị không âm ở đây. Với `10000000000.00`, precision là 13 nên bị từ chối.
5. **Không auto-round đầu vào**: thay vì biến `19.999` thành `20.00` một cách âm thầm, hệ thống trả lỗi rõ ràng.

Trong ứng dụng thật, còn cần giới hạn kích thước HTTP/JSON, số ký tự và **mũ/scientific notation** tùy chính sách. Constructor `BigDecimal(String)` chấp nhận dạng số mũ như `"1E+3"`; nếu API chỉ cho phép dạng thập phân không có số mũ, hãy dùng validation cú pháp trước khi gọi constructor. `Objects.requireNonNull` ở ví dụ ném `NullPointerException` cho input null; tầng API có thể chuyển thành lỗi validation có cấu trúc theo quy ước ứng dụng.

### Nếu bắt buộc đúng hai chữ số trong văn bản đầu vào

Đây là **hợp đồng khác**, cần kiểm tra định dạng, ví dụ:

```java
// Mảnh mã minh họa trong phương thức nhận String text:
if (!text.matches("(0|[1-9][0-9]*)\\.[0-9]{2}")) {
    throw new IllegalArgumentException("Expected decimal with 2 places");
}
```

Biểu thức trên không chấp nhận dấu âm, số mũ, zero đứng đầu không cần thiết hay chuỗi thiếu phần thập phân; đó là lựa chọn format riêng. Trong tệp Java thực, chuỗi regex dùng `\\.` để khớp dấu chấm literal. Quy định về dấu `+`, khoảng trắng, locale, ký tự Unicode và độ dài cũng phải công bố rõ ràng nếu có.

## 7. Hợp đồng rounding ở bước tính toán: thứ tự có thể đổi kết quả

Một lỗi thiết kế kinh điển là ghi “làm tròn 2 chữ số” nhưng không chỉ rõ **làm tròn trước hay sau khi nhân**.

Giả sử một đơn giá chính xác nội bộ là `0.335` và số lượng là `3`; chính sách `HALF_UP` với 2 chữ số:

- **Làm tròn đơn giá trước**: `0.335 → 0.34`, rồi `0.34 × 3 = 1.02`.
- **Nhân trước, làm tròn cả dòng sau**: `0.335 × 3 = 1.005 → 1.01`.

Cả hai dùng **cùng rounding mode và scale**, nhưng cho **kết quả khác**. Một hợp đồng đủ rõ phải chọn một trong hai mô hình.

**Tệp `InvoiceRoundingDemo.java`:**

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class InvoiceRoundingDemo {
    private static final int MONEY_SCALE = 2;
    private static final RoundingMode POLICY = RoundingMode.HALF_UP;

    public static void main(String[] args) {
        BigDecimal rawUnitPrice = new BigDecimal("0.335");
        BigDecimal quantity = new BigDecimal("3");

        BigDecimal unitFirst = rawUnitPrice
                .setScale(MONEY_SCALE, POLICY)
                .multiply(quantity);

        BigDecimal lineFirst = rawUnitPrice
                .multiply(quantity)
                .setScale(MONEY_SCALE, POLICY);

        System.out.println("unitFirst=" + unitFirst);
        System.out.println("lineFirst=" + lineFirst);

        // Ví dụ khác: tính thuế từ giá trị gốc rồi làm tròn riêng thuế.
        BigDecimal net = new BigDecimal("19.99");
        BigDecimal rate = new BigDecimal("0.075");
        BigDecimal tax = net.multiply(rate)
                .setScale(MONEY_SCALE, RoundingMode.HALF_EVEN);
        BigDecimal gross = net.add(tax);

        System.out.println("tax=" + tax);
        System.out.println("gross=" + gross);
    }
}
```

```bash
javac InvoiceRoundingDemo.java
java InvoiceRoundingDemo
```

```text
unitFirst=1.02
lineFirst=1.01
tax=1.50
gross=21.49
```

Đây là **hai ví dụ chính sách độc lập**, không phải quy tắc thuế/pháp lý mặc định. Trong dự án thật phải làm rõ giá đưa vào có gồm thuế không, thuế tính theo dòng hay cả đơn, có bao nhiêu loại thuế, quy tắc phân bổ chênh lệch, loại tiền tệ, xử lý hoàn tiền và rounding mode bắt buộc.

**Nguyên tắc triển khai:** giữ precision thích hợp trong các bước trung gian và làm tròn **tại điểm được hợp đồng quy định**, không gọi `setScale(2, ...)` bừa bãi sau mọi phép cộng/nhân. Nếu phải kiểm soát precision trong phép tính dài, dùng `MathContext` theo thiết kế thuật toán, đồng thời ý thức rằng làm tròn trung gian có thể ảnh hưởng kết quả cuối.

## 8. Chia số và tỷ lệ: xác định precision/scale ngay trong phép toán

Phép chia là nguồn lỗi phổ biến khi dùng `BigDecimal`:

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = new BigDecimal("3");

// one.divide(three) ném ArithmeticException vì 1/3 vô hạn thập phân.
BigDecimal rounded = one.divide(three, 2, RoundingMode.HALF_UP);
System.out.println(rounded); // 0.33
```

Đây là mảnh mã minh họa trong một phương thức, cần import `BigDecimal` và `RoundingMode`.

Quyết định đúng tùy hợp đồng:

- “Lưu tỷ lệ có 4 chữ số sau dấu chấm” → cân nhắc `divide(divisor, 4, mode)`.
- “Giữ 8 chữ số có nghĩa cho tính toán khoa học” → cân nhắc `divide(divisor, new MathContext(8, mode))`.
- “Tỷ lệ phần trăm hiển thị 2 số sau dấu chấm” → xác định giá trị lưu là `0.075` hay `7.5%`, và làm tròn ở bước **hiển thị** hay tính toán.
- “Phải chia chính xác, không làm tròn” → chấp nhận ngoại lệ nếu thương không có biểu diễn thập phân hữu hạn, hoặc dùng biểu diễn phân số riêng.

**Không** viết `divide` không có mode rồi ngạc nhiên với `ArithmeticException` ở `1/3`. Ngược lại, cũng không mặc định `HALF_UP` và scale 2 cho mọi phép chia: hệ thống có thể cần thêm chữ số trung gian để không làm mất thông tin quan trọng.

## 9. Hợp đồng qua các tầng: Java, JSON, database và báo cáo

### 9.1. Java domain model

Một thiết kế tốt đặt tên cho cấu hình số, tránh “magic number” 2 xuất hiện ở nhiều nơi:

```java
public final class MoneyPolicy {
    public static final int SCALE = 2;
    public static final int PRECISION = 12;
    public static final java.math.RoundingMode TAX_ROUNDING =
            java.math.RoundingMode.HALF_EVEN;

    private MoneyPolicy() {
    }
}
```

Đây là lớp hoàn chỉnh có thể lưu ở `MoneyPolicy.java` trong Java 17+. Trong kiến trúc thực, đặt chính sách ở domain hoặc module cấu hình phù hợp; nếu nhiều loại tiền tệ có scale khác nhau, không dùng một hằng `SCALE=2` toàn cục cho mọi đối tượng.

Đừng che giấu rounding trong setter không rõ hợp đồng: `setAmount(input)` âm thầm làm tròn có thể khiến phần còn lại của chương trình tưởng rằng dữ liệu gốc chưa bị đổi. API rõ ý định hơn có thể là `parseExactAmount`, `calculateRoundedTax`, `serializeAmount`.

### 9.2. API JSON và định dạng

JSON hỗ trợ số nhưng client có thể parse thành `double`, JavaScript `Number`, hoặc đưa dữ liệu qua một hệ thống không giữ nguyên số chữ số sau dấu chấm. Vì vậy, với lượng tiền cần bảo toàn biểu diễn, **decimal string** thường là lựa chọn dễ quy định hơn:

```json
{
  "currency": "USD",
  "amount": "19.90"
}
```

Hợp đồng cần nêu chuỗi `amount` theo quy tắc nào: dấu chấm thập phân, có cho số mũ không, bao nhiêu chữ số, có cho dấu âm/plus không, có khoảng trắng không; lỗi trả về mã gì. Không phụ thuộc locale người dùng để parse chuỗi giao tiếp máy với máy.

Nếu API sử dụng JSON number, cũng cần nêu rõ hai bên phải dùng kiểu decimal chính xác và round-trip an toàn. JSON number **không bảo đảm** mọi client gìn giữ scale như `"19.90"` và tránh biến về IEEE 754.

### 9.3. Database `DECIMAL(P,S)`

Với một ví dụ SQL schema:

```sql
amount DECIMAL(12, 2) NOT NULL
```

Thông thường, `P=12` là tổng số chữ số, `S=2` là số chữ số thập phân được lưu. Một giá trị `9999999999.99` vừa giới hạn này; `10000000000.00` vượt số chữ số phần nguyên cho phép.

**Không dựa vào database tự quyết rounding**. Quy tắc ép/làm tròn khi insert giá trị có quá nhiều chữ số có thể thay đổi theo sản phẩm database, phiên bản hoặc mode. Để không bị lệch giữa môi trường dev/staging/production, validate trong domain trước và test tích hợp với schema thật. Database còn là lớp bảo vệ cuối giúp từ chối giá trị ngoài phạm vi; không thay thế validation nghiệp vụ.

Nếu cần lưu cả số chữ số đầu vào gốc, ví dụ “2.00” khác “2.0” về bằng chứng đo lường, phải thiết kế **metadata biểu diễn** tương ứng; `DECIMAL(P,S)` cố định có thể chuẩn hóa scale và không bảo toàn chuỗi người dùng đã nhập.

### 9.4. Báo cáo và CSV

Sử dụng `BigDecimal.toPlainString()` khi cần xuất dạng thập phân không dùng ký pháp khoa học, đồng thời **đặt scale theo hợp đồng** trước khi xuất. `stripTrailingZeros()` có thể khiến `new BigDecimal("1000.00")` thành `1E+3` (scale âm), nên không được coi là hàm định dạng hiển thị tiền.

Nếu báo cáo có nhiều đơn vị tiền tệ, mỗi giá trị cần có đơn vị cụ thể. Hai giá trị có cùng số “10.00” nhưng khác currency không thể cộng nếu chưa có quy tắc quy đổi, nguồn tỷ giá, thời điểm và precision/rounding liên quan.

## 10. Test như thế nào để đảm bảo hợp đồng số?

Viết test từ **hợp đồng**, không chỉ test khi thấy bug:

| Nhóm | Ca thử nên có | Điều cần xác nhận |
|---|---|---|
| Giá trị hợp lệ | `0`, `19.90`, `9999999999.99` | Chuẩn hóa chính xác, đúng miền |
| Trailing zero | `19.900` | Chấp nhận nếu hợp đồng là giá trị chính xác tới cent |
| Không hợp lệ do scale | `19.999` | Từ chối, không âm thầm `20.00` |
| Không hợp lệ do precision | `10000000000.00` | Từ chối vượt miền |
| Giá trị âm | `-1.00` | Từ chối hoặc chấp nhận theo quy tắc hoàn tiền riêng |
| Không phải số | `"abc"`, `""` | Lỗi parse/validation có cấu trúc |
| Cú pháp ngoài format | `"1E+3"`, `"+1.00"` | Cho phép/từ chối theo hợp đồng input |
| Rounding tie | `2.345`, `2.355`, `-2.345` | Đúng `HALF_EVEN`/`HALF_UP` |
| Thứ tự làm tròn | `0.335 × 3` | Cùng chính sách, kết quả 1.01 hoặc 1.02 tùy điểm làm tròn |
| Chia không kết thúc | `1 / 3` | Bắt buộc mode/scale hoặc ngoại lệ có chủ ý |
| Round-trip | Java → JSON → Java → DB → Java | Không đổi giá trị và biểu diễn theo phần hợp đồng cần giữ |

### Ví dụ test Java không cần framework

**Tệp `MoneyContractChecks.java`**; dùng lớp `MoneyContractDemo` từ mục 6 đã biên dịch:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class MoneyContractChecks {
    private static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    private static void rejects(String input) {
        try {
            MoneyContractDemo.parseAmount(input);
            throw new AssertionError("Expected rejection: " + input);
        } catch (IllegalArgumentException expected) {
            // Đúng: đầu vào bị từ chối theo hợp đồng.
        }
    }

    public static void main(String[] args) {
        check(MoneyContractDemo.parseAmount("19.900")
                .equals(new BigDecimal("19.90")),
                "trailing zero accepted and normalized");

        check(MoneyContractDemo.parseAmount("0")
                .equals(new BigDecimal("0.00")),
                "zero has required scale");

        rejects("19.999");
        rejects("10000000000.00");
        rejects("-1.00");

        check(new BigDecimal("2.345")
                .setScale(2, RoundingMode.HALF_EVEN)
                .equals(new BigDecimal("2.34")),
                "tie-to-even lower");

        check(new BigDecimal("2.355")
                .setScale(2, RoundingMode.HALF_EVEN)
                .equals(new BigDecimal("2.36")),
                "tie-to-even higher");

        System.out.println("Contract checks passed");
    }
}
```

```bash
javac MoneyContractDemo.java MoneyContractChecks.java
java MoneyContractChecks
```

```text
Contract checks passed
```

Chú ý `rejects()` bắt `IllegalArgumentException` mà `parseAmount` phát sinh, còn `AssertionError` là một loại `Error` riêng nên không bị nuốt bởi catch này. Nếu muốn test exception subclass cụ thể, JUnit 5 có `assertThrows`; nhưng bài học này không cần thêm thư viện.

Khi kiểm thử giá trị money đã được chuẩn hóa và **scale là hợp đồng**, `BigDecimal.equals` là phù hợp vì kiểm tra cả giá trị và scale. Khi chỉ yêu cầu giá trị số học (ví dụ so sánh 2.0 với 2.00), `compareTo == 0` phù hợp hơn. Chọn assertion đúng ý định, không sử dụng một kiểu so sánh cho mọi trường hợp.

## 11. Các sai lầm thiết kế thường gặp

### 11.1. Lẫn precision với scale

Ghi “precision = 2” khi muốn “2 chữ số sau dấu chấm” sẽ dẫn đến tính toán sai. Với `123.456`, `MathContext(2)` chỉ giữ 2 chữ số có nghĩa (kết quả gần `120`), còn `setScale(2)` giữ 2 chữ số thập phân (`123.46` với `HALF_EVEN`).

### 11.2. Dùng `double` làm trung gian cho tiền

`double` không biểu diễn chính xác nhiều số thập phân như `0.1`. `new BigDecimal(0.1)` tạo `BigDecimal` chứa chính xác giá trị nhị phân của `double`, không phải đúng giá trị thập phân `0.1` mong muốn. Hãy tạo từ chuỗi `new BigDecimal("0.1")` hoặc từ một nguồn decimal chính xác. `BigDecimal.valueOf(double)` sử dụng chuỗi biểu diễn chuẩn của `double`, nhưng không thể khôi phục chữ số gốc đã mất từ trước.

### 11.3. Làm tròn khi parse, không thông báo

Một client gửi `19.999` có thể vô tình bị đổi thành `20.00`; đây là thay đổi giá trị nghiệp vụ. Nếu hợp đồng đòi nhập chính xác đến cent, dùng `UNNECESSARY` và **từ chối** thay vì ngầm sửa dữ liệu.

### 11.4. Áp `MathContext` quá sớm

Dùng `MathContext(4)` cho mọi phép cộng/nhân có thể làm mất chữ số ở từng bước. Kết quả cuối có thể khác cách giữ precision trung gian lớn hơn rồi rounding một lần ở điểm được hợp đồng quy định. Chọn chính sách có căn cứ, không “đặt cho an toàn” tùy tiện.

### 11.5. `stripTrailingZeros()` cho mục tiêu hiển thị

`stripTrailingZeros()` có thể tạo scale âm và ký pháp khoa học, ví dụ `1000.00 → 1E+3`. Nó hữu ích khi cần canonical hóa giá trị theo một chính sách rõ ràng, nhưng không thay thế `setScale(2)`/định dạng phù hợp khi xuất `1000.00`.

### 11.6. Không công bố đơn vị và mức làm tròn

“Dùng 2 chữ số thập phân” chưa trả lời currency nào, đơn vị giá nào, có làm tròn từng dòng không hay một lần ở toàn bộ đơn. Các hệ thống khác nhau có thể đều “đúng 2 chữ số” nhưng khác kết quả. Cần viết ví dụ số cụ thể trong hợp đồng.

### 11.7. Không giới hạn miền và đầu vào quá lớn

`BigDecimal` hỗ trợ độ chính xác tùy ý nhưng không miễn phí. Chuỗi rất dài, số mũ cực lớn và chuyển scale có thể làm hệ thống dùng nhiều CPU/bộ nhớ. Giới hạn kích thước payload, độ dài chuỗi, số mũ và miền giá trị phù hợp trước khi cấp phát lớn hoặc chuẩn hóa dữ liệu.

### 11.8. Phó mặc database hoặc serialize tự làm tròn

Rounding ở tầng persistence có thể âm thầm đổi giá trị so với domain; round-trip giữa Java/JSON/DB có thể không giữ scale đúng như mong đợi. Thiết kế nên quy định một **nguồn sự thật** cho chính sách số và kiểm tra bằng test tích hợp.

## 12. Checklist viết một hợp đồng dữ liệu số

Trước khi chốt schema hoặc API, nên ghi thành văn bản:

1. **Ý nghĩa & đơn vị** của số: tiền, phần trăm, tỷ lệ 0..1, đo lường hoặc số lượng.
2. **Kiểu số**: `BigDecimal`, integer minor units, `BigInteger` hay `double` (nêu lý do).
3. **Miền hợp lệ**: min, max, có nhận số âm/0/giá trị đặc biệt không.
4. **Precision** tối đa theo từng tầng và cách xử lý khi vượt giới hạn.
5. **Scale** đầu vào, trong tính toán, tại lưu trữ, tại xuất dữ liệu.
6. **RoundingMode** và **điểm làm tròn**: theo đơn giá, dòng, nhóm, thuế hay tổng.
7. **Chính sách dữ liệu không hợp lệ**: từ chối, trả lỗi nào, có cho làm tròn có chủ ý không.
8. **Định dạng wire**: decimal string hay JSON number, cú pháp được phép, locale, số mũ, trailing zeros.
9. **Persistence**: `DECIMAL(P,S)` và đối chiếu giới hạn/rounding của database thật.
10. **Kiểm thử**: ca biên, tie, negative, zero, precision overflow, chia không kết thúc, round-trip.
11. **Tương thích phiên bản**: thay precision, scale hoặc rounding là thay đổi hợp đồng có thể ảnh hưởng dữ liệu lưu, API clients và kết quả kế toán; cần kế hoạch migration.
12. **Quyền thay đổi chính sách**: ai duyệt rounding mode, cách lưu lịch sử version chính sách và tái tính khi cần đối soát.

Đối với các trường mà số chữ số mang ý nghĩa đo lường (ví dụ `2.0` và `2.00` có thể báo độ phân giải đo khác nhau), lưu riêng metadata về độ phân giải hoặc văn bản gốc nếu nghiệp vụ đòi. `BigDecimal` giữ scale khi khởi tạo từ chuỗi nhưng nhiều phép toán, serialize hoặc lưu DB có thể chuẩn hóa cách biểu diễn.

## 13. Bài tập tự kiểm tra, có lời giải

1. **`new BigDecimal("123.450").precision()` và `scale()` là bao nhiêu?**  
   Lần lượt 6 và 3. Hai giá trị này không cùng nghĩa.

2. **Vì sao `new BigDecimal("19.900").setScale(2, UNNECESSARY)` không ném ngoại lệ?**  
   Vì việc bỏ số 0 thập phân cuối không đổi giá trị số học, kết quả là `19.90`.

3. **Vì sao `new BigDecimal("19.999").setScale(2, UNNECESSARY)` ném ngoại lệ?**  
   Vì không thể giữ giá trị chính xác ở scale 2: cần bỏ chữ số 9 khác 0.

4. **`2.345` làm tròn 2 chữ số theo `HALF_UP` và `HALF_EVEN` được gì?**  
   Lần lượt `2.35` và `2.34`, với đầu vào `BigDecimal` từ chuỗi.

5. **`0.335 × 3` nếu làm tròn đơn giá trước hoặc sau khi nhân theo `HALF_UP` được gì?**  
   Lần lượt `1.02` và `1.01`; điểm làm tròn là một phần của hợp đồng.

6. **`BigDecimal.ONE.divide(new BigDecimal("3"))` có trả một số thập phân tùy ý dài vô hạn không?**  
   Không; nếu không chỉ định rounding/scale/MathContext và thương không kết thúc, Java ném `ArithmeticException`.

7. **`DECIMAL(12,2)` có cho 12 chữ số phần nguyên không?**  
   Không theo ý nghĩa SQL phổ biến: precision tổng 12, scale 2, nên tối đa 10 chữ số phần nguyên.

8. **Nếu API đòi đúng ký tự `"12.30"` thay vì `"12.300"`, chỉ dùng `UNNECESSARY` đủ không?**  
   Không. `UNNECESSARY` kiểm tra giá trị có biểu diễn chính xác được sau chuẩn hóa, không đếm chữ số của chuỗi đầu vào; cần kiểm tra định dạng văn bản riêng.

9. **Dùng `equals` hay `compareTo` cho hai giá trị tiền đã chuẩn hóa theo scale 2?**  
   `equals` phù hợp khi yêu cầu **cả scale** thuộc hợp đồng; `compareTo == 0` phù hợp khi chỉ yêu cầu cùng giá trị số học.

10. **Vì sao một thay đổi rounding mode có thể là breaking change dù API field vẫn tên `amount`?**  
    Vì cùng input có thể cho output khác, ảnh hưởng dữ liệu đã lưu, đối soát, hóa đơn và client; cần version/chính sách migration nếu thay đổi.

## 14. Tổng kết và tài liệu chính thức

**Precision, scale và rounding là phần của hợp đồng dữ liệu số, không phải ba tham số kỹ thuật tùy ý.** `precision` giới hạn chữ số có nghĩa; `scale` xác định vị trí thập phân; `RoundingMode` quy định cách xử lý khi buộc giảm độ chính xác. Một hệ thống đúng phải thống nhất cách parse, tính toán, lưu trữ, trao đổi và kiểm thử—kèm miền hợp lệ, đơn vị và điểm làm tròn rõ ràng.

Tài liệu tham khảo:

- [Java 21 — `BigDecimal`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigDecimal.html)
- [Java 21 — `MathContext`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/MathContext.html)
- [Java 21 — `RoundingMode`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/RoundingMode.html)
