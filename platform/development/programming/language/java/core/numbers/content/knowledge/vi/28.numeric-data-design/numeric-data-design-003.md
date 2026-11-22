# Số đếm, đại lượng đo và giá trị thập phân có quy tắc làm tròn

## 1. Vấn đề thiết kế: cùng là số, nhưng không cùng ý nghĩa

Trong Java, `int`, `long`, `double` và `BigDecimal` đều lưu được những dạng dữ liệu số. Tuy nhiên, chọn kiểu chỉ theo “giá trị này có dấu phẩy không?” thường dẫn đến lỗi nghiệp vụ. Hãy phân biệt ba loại thông tin:

1. **Số đếm (*count*)**: số lượng phần tử rời rạc, thường là số nguyên không âm, chẳng hạn 12 học viên, 7 lần thử, 300 lượt truy cập.
2. **Đại lượng đo (*measurement*)**: độ dài, khối lượng, thời gian, nhiệt độ, tốc độ… luôn có **đơn vị**, độ phân giải và đôi khi có sai số đo. Ví dụ `2.5 m` khác `2.5 cm`.
3. **Giá trị thập phân có quy tắc làm tròn (*rounded decimal value*)**: tiền, thuế, lãi, tỷ lệ được tính toán chính xác ở mức cần thiết rồi **chuẩn hóa scale và rounding mode theo quy tắc nghiệp vụ**.

Chúng có thể cùng hiển thị là `"2"` nhưng phải có quy tắc khác nhau:

| Dữ liệu | Ý nghĩa | Đại diện Java thường phù hợp | Bất biến/cách sử dụng |
| --- | --- | --- | --- |
| 2 sản phẩm trong giỏ | Số đếm | `int`, `long`, `BigInteger` | Không âm, nguyên; tránh tràn khi cộng. |
| 2 mét chiều dài | Đại lượng đo | `BigDecimal` hoặc `double` **kèm đơn vị** | Không được cộng sai đơn vị; xác định độ chính xác và sai số đo. |
| 2.00 USD tiền thanh toán | Giá trị tiền theo thỏa thuận | `BigDecimal` **kèm loại tiền và rounding policy** | Không trộn tiền tệ; làm tròn đúng thời điểm và đúng chế độ. |
| 2.5 sản phẩm tính theo khối lượng | Số lượng bán đo được | `BigDecimal` kèm `kg`, `lít`… | Không ép mọi “quantity” thành số đếm nguyên. |
| Tỷ lệ 2% | Tỷ lệ, không phải 2 đơn vị | `BigDecimal` hoặc `double` tùy bài toán | Chọn rõ biểu diễn 2% là `0.02` hay `2`, không trộn. |

**Mô hình dữ liệu phải nói lên ý nghĩa của số**, giới hạn giá trị, đơn vị, quy tắc toán học và thời điểm làm tròn. Kiểu số chỉ là một phần của thiết kế.

## 2. Số đếm: miền nguyên, ràng buộc và nguy cơ tràn

### 2.1. Vì sao số đếm thường dùng int hoặc long?

Số đếm các thực thể không chia nhỏ được thường thuộc tập `0, 1, 2, ...`. Các lựa chọn:

- `int`: số nguyên 32 bit có dấu, miền từ `-2^31` đến `2^31 - 1`. Hợp lý cho vòng lặp, số lượng nhỏ hoặc phạm vi đã biết.
- `long`: số nguyên 64 bit có dấu, từ `-2^63` đến `2^63 - 1`. Dùng cho lượt sự kiện lớn, bộ đếm dài hạn, tổng từ nhiều nguồn.
- `BigInteger`: số nguyên độ chính xác tùy ý khi yêu cầu vượt miền `long` hoặc kết quả toán học bắt buộc không tràn.

Một `long` cho phép biểu diễn số âm nhưng **miền nghiệp vụ “số mặt hàng” có thể không cho phép âm**. Kiểu và validation cùng chịu trách nhiệm:

```java
record ItemCount(long value) {
    ItemCount {
        if (value < 0) {
            throw new IllegalArgumentException("Count must be non-negative");
        }
    }
}
```

Đây là đoạn record minh họa, đặt trong lớp hoặc source hợp lệ. Bởi Java `record` là value carrier, validation trong compact constructor giúp mọi lần tạo `ItemCount` tuân thủ invariant. Một phép *delta* như `-3` lần điều chỉnh số lượng có thể cần **kiểu riêng `CountDelta`**, không ép nó vào `ItemCount` vốn chỉ cho giá trị không âm.

### 2.2. Tràn số không phải một phép cộng đúng theo nghiệp vụ

`int` và `long` có giới hạn. Phép cộng primitive thông thường khi tràn không ném exception; kết quả tràn theo quy tắc Java:

```java
int max = Integer.MAX_VALUE;
System.out.println(max + 1); // -2147483648
```

Trong nghiệp vụ số lượng, “từ số dương thành âm” thường là lỗi. `Math.addExact` phát hiện tràn:

```java
long result = Math.addExact(1_000_000L, 2_000_000L);
System.out.println(result); // 3000000
// Math.addExact(Long.MAX_VALUE, 1L) ném ArithmeticException.
```

Với dữ liệu có thể vượt `long`, dùng `BigInteger.add` hoặc áp đặt giới hạn miền hợp lệ theo hợp đồng. Không dùng `double` để “chứa được mọi số đếm rất lớn”: `double` có khoảng giá trị rất rộng nhưng không giữ chính xác mọi số nguyên vượt `2^53`.

### 2.3. Không cộng các count có ý nghĩa khác nhau

Tổng `3 người` và `5 lần đăng nhập` không phải `8 đơn vị` có ý nghĩa. Dù cùng là `long`, chúng nên được đặt tên rõ, phân lớp hoặc dùng record domain khi cần:

```java
record UserCount(long value) {}
record LoginAttemptCount(long value) {}
```

Đây chỉ là ví dụ biểu diễn loại dữ liệu, chưa có validation. Nếu thiết kế đầy đủ, kiểm tra số không âm và tránh vô tình cộng chéo kiểu. Một đối tượng `Count` tổng quát phù hợp khi các số đếm có cùng đơn vị/ý nghĩa; các số đếm khác miền không nên tự cộng chỉ vì Java cho phép toán tử `+`.

## 3. Đại lượng đo: trị số phải đi cùng đơn vị và ngữ cảnh độ chính xác

“`10`” không nói lên điều gì nếu nó có thể là `10 mét`, `10 inch` hoặc `10 miligiây`. Một đại lượng đo cần ít nhất:

- **Loại đại lượng**: độ dài, khối lượng, thời lượng, nhiệt độ, thể tích...
- **Đơn vị**: `m`, `cm`, `kg`, `ms`… theo quy ước nhất quán.
- **Giá trị** trong đơn vị đó.
- **Độ phân giải/sai số đo** khi có ý nghĩa: thước chia mm và cảm biến có sai số ±0.1 °C không cùng độ chính xác thực nghiệm.

Phép cộng chỉ hợp lệ khi các giá trị có đơn vị tương thích, sau khi chuyển đổi nếu cần:

```text
1.25 m + 75 cm
= 1.25 m + 0.75 m
= 2.00 m
```

Không thể cộng trực tiếp `1.25 + 75` rồi gắn hậu tố `m`. Tương tự, nhiệt độ Celsius là một ví dụ cho thấy **không phải mọi loại đại lượng có thể cộng/trừ đơn giản như độ dài**: nhiệt độ tuyệt đối và độ chênh nhiệt độ cần mô hình phân biệt trong nghiệp vụ.

### 3.1. Hai hướng biểu diễn measurement

**Hướng A — Lưu số nguyên theo đơn vị cơ sở đủ nhỏ.** Ví dụ thời lượng chính xác đến mili giây có thể lưu bằng `long milliseconds`; khoảng cách chính xác đến mm có thể lưu bằng `long millimeters`. Ưu điểm: các phép cộng đơn vị rời rạc chính xác và không bị lỗi dấu phẩy động. Đổi đơn vị có thể cần làm tròn; phải xác định quy tắc. Ngoài ra cần tránh overflow.

**Hướng B — Lưu BigDecimal hoặc double cùng đơn vị.** Ví dụ độ dài ghi tới `0.001 m` có thể biểu diễn bằng `BigDecimal("1.235")`; số đo vật lý từ cảm biến đôi khi hợp lý hơn với `double` do bản chất xấp xỉ, chi phí tính toán và thuật toán xử lý tín hiệu. Chọn `BigDecimal` **không làm số đo vật lý chính xác hơn thiết bị đo**: nó chỉ giúp biểu diễn và tính chính xác các chữ số decimal đã cung cấp.

Hãy cố định **đơn vị nội bộ thống nhất**, ví dụ luôn lưu mét và chỉ chuyển sang cm/inch ở giao diện. Khi chuyển đổi có hệ số chính xác trong hệ thập phân như `cm → m = chia 100`, `BigDecimal.movePointLeft(2)` thực hiện phép đổi chính xác:

```java
BigDecimal centimeters = new BigDecimal("125.0");
BigDecimal meters = centimeters.movePointLeft(2);
System.out.println(meters.toPlainString()); // 1.250
```

Giá trị kết quả có scale 3, phản ánh việc dịch dấu thập phân trên biểu diễn hiện tại. Đây không phải cam kết rằng phép đo có ba chữ số thập phân mang ý nghĩa thực nghiệm; ý nghĩa đo đạc phải được mô tả riêng.

### 3.2. Số đo có bất định, không chỉ có nhiều chữ số

Giả sử cảm biến ghi `1.234 m` nhưng sai số đo khoảng ±`0.01 m`. Nếu in `1.234000000 m`, số chữ số mới chỉ là *trình bày*, không làm sai số giảm. Trong báo cáo khoa học, nên ghi độ không chắc chắn và mức chữ số phù hợp tiêu chuẩn ngành, ví dụ `1.23 m ± 0.01 m` nếu đó là quy tắc trình bày được chọn.

`setScale`, `DecimalFormat` và `MathContext` thay đổi **biểu diễn/kết quả số học**, không đánh giá hay giảm sai số thực nghiệm.

## 4. Giá trị thập phân và BigDecimal: scale khác precision

`BigDecimal` xác định một số bằng `unscaledValue × 10^(-scale)`. Với `new BigDecimal("12.3400")`:

- `unscaledValue()` là `123400`.
- `scale()` là `4` (bốn chữ số sau dấu chấm trong biểu diễn này).
- `precision()` là `6` (sáu chữ số có nghĩa của unscaled value).

`scale` khác `precision`. `setScale(2)` hướng tới **hai chữ số sau dấu chấm**, không phải hai chữ số có nghĩa. `MathContext(2, mode)` giới hạn **hai chữ số có nghĩa** khi áp dụng vào phép toán. Chọn sai khái niệm có thể làm tròn sai bậc độ lớn.

```java
BigDecimal x = new BigDecimal("123.456");
System.out.println(x.setScale(2, RoundingMode.HALF_UP)); // 123.46
System.out.println(x.round(new MathContext(2, RoundingMode.HALF_UP))); // 1.2E+2
```

Đoạn mã rời trên cần `import java.math.BigDecimal;`, `import java.math.MathContext;` và `import java.math.RoundingMode;`.

### 4.1. Khởi tạo từ String thay vì double khi decimal là dữ liệu chính xác

`new BigDecimal(0.1)` lưu chính xác giá trị nhị phân xấp xỉ của literal `double`, vốn khác số thập phân `0.1`. Để biểu diễn `0.1` decimal một cách chủ ý:

```java
BigDecimal exactDecimal = new BigDecimal("0.1");
BigDecimal fromValueOf = BigDecimal.valueOf(0.1);
System.out.println(exactDecimal); // 0.1
System.out.println(fromValueOf);   // 0.1
```

`BigDecimal.valueOf(double)` chuyển từ biểu diễn decimal của `double`, thường hợp lý cho literal đơn giản, nhưng **không khôi phục được các chữ số đã mất từ một chuỗi phép tính `double` trước đó**. Với input từ API hoặc DB, nên sử dụng định dạng decimal chính xác của nguồn thay vì đi qua `double`.

### 4.2. BigDecimal bất biến

`add`, `multiply`, `divide` (khi đủ thông tin làm tròn), `setScale` đều trả về một `BigDecimal` kết quả; không sửa instance gốc:

```java
BigDecimal raw = new BigDecimal("10.005");
BigDecimal rounded = raw.setScale(2, RoundingMode.HALF_UP);
System.out.println(raw);     // 10.005
System.out.println(rounded); // 10.01
```

Nếu chỉ gọi `raw.setScale(2, mode);` mà bỏ kết quả, biến `raw` vẫn giữ nguyên. Tính bất biến giúp mô hình giá trị dễ suy luận hơn, nhưng **bản thân BigDecimal không chứa currency/unit hay quy tắc làm tròn nghiệp vụ**.

## 5. Quy tắc làm tròn phải là một phần hợp đồng dữ liệu

Một giá trị raw `10.005` có thể thành `10.00` hoặc `10.01` tùy quy tắc làm tròn. Khi thiết kế giá trị thập phân, hãy xác định rõ:

1. **Scale đầu vào/tính toán**: giữ bao nhiêu chữ số để không đánh mất thông tin quan trọng trước thời điểm quyết toán.
2. **Scale kết quả**: ví dụ hai vị trí decimal cho một định dạng ví dụ, chứ không phải mọi loại tiền tệ.
3. **RoundingMode**: `HALF_UP`, `HALF_EVEN`, `DOWN`, `CEILING`… theo hợp đồng.
4. **Ranh giới làm tròn**: sau từng dòng, sau tính thuế, sau tổng cuối, khi lưu DB, hay chỉ khi xuất cho người dùng.
5. **Áp dụng với số âm**: hoàn tiền/điều chỉnh; `CEILING` hướng về dương vô cực, `FLOOR` về âm vô cực.
6. **Khi không cho mất chính xác**: `RoundingMode.UNNECESSARY` để phát hiện giá trị chưa tuân thủ scale.

Ví dụ `HALF_UP` về scale 2:

```java
System.out.println(new BigDecimal("10.004").setScale(2, RoundingMode.HALF_UP)); // 10.00
System.out.println(new BigDecimal("10.005").setScale(2, RoundingMode.HALF_UP)); // 10.01
System.out.println(new BigDecimal("-10.005").setScale(2, RoundingMode.HALF_UP)); // -10.01
```

`HALF_EVEN` chọn chữ số cuối chẵn khi hai kết quả đích cách đều giá trị gốc. Đây là quy tắc có thể giảm thiên lệch thống kê trong nhiều phép làm tròn, nhưng không được mặc định là chính sách đúng cho mọi giao dịch. Ví dụ:

```java
System.out.println(new BigDecimal("1.245").setScale(2, RoundingMode.HALF_EVEN)); // 1.24
System.out.println(new BigDecimal("1.255").setScale(2, RoundingMode.HALF_EVEN)); // 1.26
```

**Không làm tròn sớm chỉ để “dữ liệu đẹp”.** Nếu tổng được làm tròn sau khi cộng, phải giữ các hạng mục đủ chính xác để cộng trước; nếu luật hạch toán yêu cầu làm tròn mỗi dòng, đó là một quy trình khác cần được triển khai chủ ý.

### 5.1. Làm tròn từng phần khác làm tròn tổng

Giả sử hai khoản tiền decimal chính xác là `10.005` và `0.005`, cuối cùng trả về scale 2 và `HALF_UP`:

```text
Làm tròn từng khoản:
round2(10.005) + round2(0.005)
= 10.01 + 0.01
= 10.02

Cộng chính xác rồi làm tròn:
round2(10.005 + 0.005)
= round2(10.010)
= 10.01
```

Cả hai kết quả có thể xuất hiện trong hệ thống đúng về mặt kỹ thuật. Hợp đồng quyết định **kết quả nào được phép**. Thiết kế tốt đặt chính sách này ở một lớp hoặc hàm có tên rõ, thay vì rải `setScale(2)` ở khắp các bước tính toán.

### 5.2. Không tùy tiện làm tròn hai lần

Với `1.245`, `HALF_UP`:

```text
round1(round2(1.245)) = round1(1.25) = 1.3
round1(1.245) = 1.2
```

Kết quả khác vì round trung gian làm mất chữ số cần thiết để đánh giá ngưỡng ở bước cuối. Khi cần làm tròn về một scale đích, hãy làm trực tiếp từ giá trị có đủ độ chính xác, trừ khi một bước làm tròn trung gian được quy định rõ là sự kiện nghiệp vụ.

## 6. Mô hình hóa bằng value object thay vì truyền các primitive không rõ nghĩa

Một hàm như `calculate(long a, BigDecimal b, BigDecimal c)` không tiết lộ `a` đếm gì, `b` có đơn vị gì hay `c` là tiền theo đồng nào. Value object/record có thể đưa invariant vào kiểu dữ liệu.

Ví dụ về hợp đồng:

| Value object | Dữ liệu nội bộ | Quy tắc ở ranh giới |
| --- | --- | --- |
| `ItemCount` | `long value` | Không âm; cộng bằng `Math.addExact`; không cộng với số đo. |
| `Length` | `BigDecimal meters` | Đổi đơn vị về mét trước khi cộng; không tạo chiều dài âm trong miền ví dụ này. |
| `Money` | `String currency`, `BigDecimal amount` | Không cộng khác currency; cho phép khoản âm nếu nghiệp vụ có hoàn tiền; làm tròn theo chính sách explicit. |

`record` từ Java 16+ phù hợp làm value carrier với thành phần bất biến như `long`, `String` và `BigDecimal`. Có thể định nghĩa constructor chuẩn hóa/validate, phương thức tạo từ đơn vị có ý nghĩa và phương thức nghiệp vụ thay vì để caller tự tổ hợp các phép cộng trần.

Đừng nhầm **“dữ liệu hợp lệ”** với “đúng nghiệp vụ mọi nơi”. Ví dụ count âm có thể là hợp lệ với *delta* nhưng không hợp lệ với tồn kho; length âm có thể không hợp lệ cho chiều dài, nhưng độ dời có hướng có thể âm. Chọn tên và invariant đúng miền.

## 7. Chương trình Java 17+ hoàn chỉnh

Ví dụ dưới đây cố ý giữ riêng ba value object: `ItemCount`, `Length` và `Money`. Nó minh họa validation, kiểm soát overflow, đổi cm sang m, làm tròn tiền tại ranh giới và giữ nguyên kết quả raw.

Lưu mã thành **`NumericDomainModelDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

public class NumericDomainModelDemo {

    record ItemCount(long value) {
        ItemCount {
            if (value < 0) {
                throw new IllegalArgumentException("Negative item count");
            }
        }

        ItemCount plus(ItemCount other) {
            Objects.requireNonNull(other, "other");
            return new ItemCount(Math.addExact(value, other.value));
        }
    }

    record Length(BigDecimal meters) {
        Length {
            Objects.requireNonNull(meters, "meters");
            if (meters.signum() < 0) {
                throw new IllegalArgumentException("Negative length");
            }
        }

        static Length fromCentimeters(String centimeters) {
            return new Length(
                    new BigDecimal(centimeters).movePointLeft(2));
        }

        Length plus(Length other) {
            Objects.requireNonNull(other, "other");
            return new Length(meters.add(other.meters));
        }

        String formatMeters(int scale, RoundingMode mode) {
            return meters.setScale(scale, mode).toPlainString() + " m";
        }
    }

    record Money(String currency, BigDecimal amount) {
        Money {
            Objects.requireNonNull(currency, "currency");
            Objects.requireNonNull(amount, "amount");
            if (currency.isBlank()) {
                throw new IllegalArgumentException("Blank currency");
            }
        }

        Money plus(Money other) {
            Objects.requireNonNull(other, "other");
            if (!currency.equals(other.currency)) {
                throw new IllegalArgumentException("Currency mismatch");
            }
            return new Money(currency, amount.add(other.amount));
        }

        Money rounded(int scale, RoundingMode mode) {
            return new Money(currency, amount.setScale(scale, mode));
        }

        String display() {
            return currency + " " + amount.toPlainString();
        }
    }

    public static void main(String[] args) {
        ItemCount count = new ItemCount(4).plus(new ItemCount(7));
        System.out.println("items = " + count.value());

        Length distance = Length.fromCentimeters("12.5")
                .plus(Length.fromCentimeters("7.5"));
        System.out.println("meters exact = "
                + distance.meters().toPlainString());
        System.out.println("meters display = "
                + distance.formatMeters(2, RoundingMode.HALF_UP));

        Money first = new Money("USD", new BigDecimal("10.005"));
        Money second = new Money("USD", new BigDecimal("0.005"));
        Money rawTotal = first.plus(second);

        Money roundedTotal = rawTotal.rounded(2, RoundingMode.HALF_UP);
        Money roundedLines = first.rounded(2, RoundingMode.HALF_UP)
                .plus(second.rounded(2, RoundingMode.HALF_UP));

        System.out.println("raw total = " + rawTotal.display());
        System.out.println("rounded total = " + roundedTotal.display());
        System.out.println("sum rounded lines = " + roundedLines.display());

        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");
        System.out.println("same numeric value = "
                + (a.compareTo(b) == 0));
        System.out.println("same representation = " + a.equals(b));

        try {
            new ItemCount(Long.MAX_VALUE).plus(new ItemCount(1));
        } catch (ArithmeticException overflow) {
            System.out.println("count overflow = detected");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17+ trong thư mục chứa file:

```bash
javac NumericDomainModelDemo.java
java NumericDomainModelDemo
```

Đầu ra chính xác:

```text
items = 11
meters exact = 0.200
meters display = 0.20 m
raw total = USD 10.010
rounded total = USD 10.01
sum rounded lines = USD 10.02
same numeric value = true
same representation = false
count overflow = detected
```

**Giải thích từng kết quả:**

- `ItemCount` cộng hai số nguyên không âm bằng `Math.addExact`, tạo count 11 và phát hiện overflow ở tình huống cuối.
- `12.5 cm = 0.125 m`; `7.5 cm = 0.075 m`. Cộng decimal chính xác cho `0.200 m`. `formatMeters(2, HALF_UP)` xuất `0.20 m` mà không biến đổi đối tượng `Length` nguồn.
- Hai khoản tiền có tổng raw `10.010`. Rounding tổng sau phép cộng là `10.01`, còn rounding từng khoản là `10.01 + 0.01 = 10.02`. Chương trình không tự nhận chính sách nào đúng ngoài giả định.
- `BigDecimal.compareTo` so sánh theo giá trị số học; `equals` xét cả scale. `1.0` và `1.00` bằng về trị số nhưng không có cùng biểu diễn.
- `Money.plus` kiểm tra currency để không vô tình cộng USD và EUR. Ví dụ vẫn đơn giản hóa nghiệp vụ thực tế: không tự mã hóa toàn bộ chính sách ISO currency, tỷ giá, phân số đơn vị tiền hoặc pháp lý.

Các `record` và thao tác đã dùng là API hợp lệ từ Java 17. Code không sử dụng thư viện bên ngoài. Trong hệ thống thật, có thể nâng cấp sang các lớp/domain module chuyên biệt, dùng kiểu currency rõ và áp dụng giới hạn độ dài, miền giá trị, loại đơn vị theo hợp đồng ứng dụng.

## 8. Khi nào dùng double, khi nào dùng BigDecimal?

Không có quy tắc “mọi số đo dùng `double`” hoặc “mọi số thập phân dùng `BigDecimal`”. Hãy dựa trên **nghĩa của dữ liệu và độ chính xác cần bảo toàn**.

| Tiêu chí | `double` | `BigDecimal` |
| --- | --- | --- |
| Biểu diễn | Nhị phân IEEE 754, độ chính xác hữu hạn. | Thập phân theo unscaled value và scale. |
| Decimal `0.1` | Không thể biểu diễn đúng chính xác bằng nhị phân hữu hạn. | `new BigDecimal("0.1")` biểu diễn đúng decimal 0.1. |
| Khối lượng xử lý lớn, phép toán khoa học | Thường hiệu quả, có hỗ trợ mạnh từ thư viện số học. | Chi phí tạo đối tượng và số học cao hơn, cần đánh giá. |
| Tiền/thuế đòi decimal chính xác và rounding policy | Thường không phù hợp để làm nguồn tính toán nghiệp vụ. | Thường phù hợp khi quản lý đúng precision, scale và rounding. |
| Số đo vật lý có sai số và phép tính liên tục | Có thể phù hợp, khi độ chính xác binary đủ mục tiêu. | Có thể phù hợp khi dữ liệu/đầu ra quy định decimal; không xóa sai số đo. |
| So sánh bằng nhau | `==` có những trường hợp cần chú ý rounding, `NaN`, `-0.0`. | `equals()` xét cả scale; `compareTo()` xét giá trị số học. |

Với `double`, tránh so sánh kết quả tính toán phức tạp chỉ bằng `==` nếu sai số làm tròn được chấp nhận. Với `BigDecimal`, tránh ngộ nhận rằng precision tùy ý đồng nghĩa phép chia luôn cho kết quả hữu hạn: `1 / 3` cần rounding policy hoặc cách biểu diễn khác; overload `divide` không cung cấp rounding thích hợp có thể ném `ArithmeticException`.

Một giá trị bán hàng `0.5 kg` là measurement hoặc *measured quantity*; nếu nghiệp vụ đòi lưu chính xác tới gram, có thể lưu `long grams = 500`, và hiển thị `0.500 kg` ở ranh giới. Một thiết bị đo công suất hoạt động theo tín hiệu nhiễu có thể dùng `double` vì độ không chắc chắn thực nghiệm vượt nhiều so với sai số số học nhị phân. Sự lựa chọn phải được tài liệu hóa.

## 9. Ranh giới chuyển đổi và định dạng

Mô hình số tốt xác định các **bước chuyển đổi** riêng biệt:

```text
Input (chuỗi / API / DB)
    ↓ Parse và kiểm tra phạm vi
Value object (Count / Length / Money)
    ↓ Chuyển về đơn vị nội bộ thống nhất
Tính toán (giữ độ chính xác phù hợp)
    ↓ Áp dụng rounding policy đúng ranh giới
Giá trị giao tiếp / lưu trữ được chuẩn hóa
    ↓ Format theo locale hoặc giao thức
Chuỗi hiển thị / payload trao đổi
```

Điểm cần tránh: gộp cả parse, chuyển đơn vị, tính toán, làm tròn và format trong một lời gọi không rõ nghĩa.

### 9.1. Chuyển từ BigDecimal sang số nguyên phải kiểm soát

`longValue()` có thể làm mất phần thập phân hoặc tràn theo cách chuyển primitive. Nếu hợp đồng yêu cầu giá trị **nguyên và vừa miền long**, dùng `longValueExact()`:

```java
System.out.println(new BigDecimal("3.00").longValueExact()); // 3
// new BigDecimal("3.5").longValueExact() -> ArithmeticException.
// new BigDecimal("999999999999999999999999").longValueExact()
// -> ArithmeticException vì vượt miền long.
```

Dùng `BigDecimal.toBigIntegerExact()` nếu phải giữ một số nguyên không giới hạn mà từ chối phần thập phân. Những phương thức exact nên nằm trong bước validation/conversion, không dùng cast im lặng.

### 9.2. Chuỗi không có số mũ, còn scale là câu chuyện riêng

`toPlainString()` tạo chuỗi decimal không ký pháp khoa học. Muốn đúng 2 chữ số sau dấu thập phân theo `HALF_UP`:

```java
BigDecimal amount = new BigDecimal("3.5");
String text = amount.setScale(2, RoundingMode.HALF_UP)
        .toPlainString();
System.out.println(text); // 3.50
```

Nhưng `toPlainString()` không thêm dấu phân nhóm, dấu thập phân theo vùng miền hoặc đơn vị tiền. Dùng formatter như `NumberFormat` với `Locale` khi trình bày cho người đọc. Rounding trong formatter là một quyết định riêng: đồng bộ với chính sách nghiệp vụ để tránh khác biệt giữa giá trị thực và giá trị hiển thị.

Lưu ý việc `stripTrailingZeros()` có thể thay đổi scale; với `BigDecimal` có scale âm, `toPlainString()` rồi parse lại **có thể không giữ scale gốc** dù trị số không thay đổi. Nếu cần bảo toàn cặp unscaledValue/scale khi truyền dữ liệu, dùng biểu diễn canonical `toString()` hoặc lưu các thành phần rõ ràng theo hợp đồng.

## 10. Thiết kế database, API và dữ liệu đa đơn vị

Nếu database lưu tiền và decimal, kiểu `DECIMAL(p, s)`/`NUMERIC(p, s)` thường hợp lý hơn kiểu floating-point cho giá trị nghiệp vụ cần decimal exact; tuy nhiên, khả năng, giới hạn precision/scale, mặc định và cách xử lý overflow/rounding **phụ thuộc hệ quản trị CSDL**. Phải cấu hình schema theo ràng buộc thực tế, không tự giả định CSDL luôn “âm thầm” làm tròn đúng cách.

Ví dụ nguyên tắc thiết kế (không phải lệnh SQL dành cho mọi CSDL):

```sql
CREATE TABLE invoice_line (
    id BIGINT PRIMARY KEY,
    quantity BIGINT NOT NULL,
    unit_price DECIMAL(19, 4) NOT NULL,
    currency_code CHAR(3) NOT NULL
);
```

Bảng minh họa lưu `quantity` như số nguyên, đơn giá decimal với scale 4, và currency code riêng. Nếu doanh nghiệp bán hàng theo kg với số lẻ, `quantity BIGINT` **không đủ**; cần thêm `quantity_value DECIMAL(...)` và `unit_code` hoặc một số nguyên theo đơn vị nhỏ nhất được quy định. Tương tự, loại tiền khác nhau có quy tắc số lẻ khác nhau, cần xác định policy khi kết toán.

Ở API, nên nêu rõ ý nghĩa từng trường:

```json
{
  "quantity": 3,
  "unitPrice": "12.3450",
  "currency": "USD",
  "amountRounding": "HALF_UP",
  "settlementScale": 2
}
```

JSON này chỉ **minh họa một hợp đồng có thể thiết kế**, chưa phải schema bắt buộc. Chuỗi `"12.3450"` giúp giữ decimal text/scale mong muốn qua những hệ thống không xử lý JSON Number với precision tương thích; cần parse và validate nó thành `BigDecimal` ở phía Java. Nếu dùng JSON number hoặc decimal string phụ thuộc vào giao thức đã thống nhất với client. **Không tin trực tiếp roundingMode và scale gửi từ client nếu đó là quy tắc do server/nghiệp vụ quản lý**; server phải áp dụng policy đã được phê duyệt.

Với measurement API, đặt `value` và `unit` tách nhau hoặc dùng một đơn vị nội bộ được tài liệu hóa rõ. Ví dụ:

```json
{
  "length": "125.0",
  "unit": "cm"
}
```

Server chuyển thành `1.250 m` theo quy tắc đơn vị. Nếu client gửi `125.0` nhưng không ghi đơn vị, việc suy diễn một đơn vị mặc định dễ dẫn tới lỗi đổi đơn vị nghiêm trọng.

## 11. Những lỗi thường gặp khi thiết kế dữ liệu số

1. **Dùng `double` cho mọi số decimal cần tiền/thuế chính xác.** Dấu phẩy động nhị phân có sai số biểu diễn; dùng `BigDecimal` hoặc số nguyên theo đơn vị tiền nhỏ nhất khi phù hợp hợp đồng.
2. **Dùng `BigDecimal` cho mọi dữ liệu số mà không cần thiết.** Nếu số đếm luôn nguyên và trong giới hạn, `int`/`long` dễ hiểu và hiệu quả hơn; nếu measurement có sai số vật lý, precision decimal vô hạn không tự hữu ích.
3. **Không lưu đơn vị cho measurement.** `10` không phân biệt được mét với cm; thêm đơn vị hoặc một kiểu bảo đảm đơn vị cơ sở.
4. **Cho phép count âm ngoài miền nghiệp vụ.** Dùng constructor validation; phân biệt count tuyệt đối và count delta.
5. **Bỏ qua overflow khi cộng số đếm.** `Math.addExact` hoặc `BigInteger` giúp phát hiện/tránh kết quả sai.
6. **Cộng các đơn vị/loại tiền khác nhau.** Kiểm tra compatibility trước khi tính; chuyển đổi đơn vị chính xác hoặc tỷ giá theo policy.
7. **Dùng `new BigDecimal(0.1)` để biểu diễn 0.1 decimal chính xác.** Nên tạo từ chuỗi hoặc nguồn decimal chính xác.
8. **Nhầm precision với scale.** `MathContext(2)` và `setScale(2)` trả lời hai yêu cầu khác nhau.
9. **Làm tròn tùy ý sau mỗi phép toán.** Rounding ở trung gian có thể đổi tổng; xác định rõ ranh giới nghiệp vụ.
10. **Dùng `setScale(2)` với số phải làm tròn mà không chỉ định mode.** Overload một tham số ném `ArithmeticException` khi phải bỏ chữ số có giá trị khác 0; chọn mode hoặc dùng `UNNECESSARY` để chủ động kiểm tra.
11. **So sánh BigDecimal sai.** `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` là `false` vì scale khác; `compareTo() == 0` khi chỉ cần bằng nhau về trị số.
12. **Cho rằng dữ liệu đo nhiều chữ số là chính xác tuyệt đối.** Bảo toàn sai số đo và độ phân giải trong mô hình/báo cáo khi cần.
13. **Trộn quy tắc format với quy tắc tiền tệ.** Ký hiệu tiền và dấu phân cách theo locale là presentation; rounding hợp đồng là quyết định nghiệp vụ.
14. **Không kiểm soát ranh giới dữ liệu bên ngoài.** Input âm khi không được phép, đơn vị lạ, chuỗi quá dài, NaN/Infinity của double hoặc decimal vượt precision DB phải được xử lý phù hợp.
15. **Biến scale hiển thị thành scale lưu trữ quá sớm.** Nếu lưu `amount` đã làm tròn trước khi tính thuế/tổng, không thể khôi phục những chữ số bị mất sau đó.

## 12. Câu hỏi tự kiểm tra

**Câu 1.** Một ứng dụng đếm lượt xem đến hàng tỷ, và số có thể tăng liên tục. Chọn `int` hay `long`?

**Đáp án:** `long` khi giới hạn `int` có thể bị vượt; nếu tổng có thể vượt cả `long` thì `BigInteger` hoặc chính sách miền hợp lệ rõ ràng. Cần dùng `Math.addExact` khi muốn phát hiện tràn thay vì wraparound.

**Câu 2.** Vì sao `2.5 kg` không nên lưu bằng `ItemCount(2)`?

**Đáp án:** Đó là đại lượng đo theo kg, không phải số mặt hàng rời rạc nguyên. Cần giá trị thập phân hoặc số nguyên theo đơn vị cơ sở như gram, cùng đơn vị.

**Câu 3.** `125.0 cm` đổi ra mét bằng decimal exact là gì?

**Đáp án:** `1.250 m` với `new BigDecimal("125.0").movePointLeft(2)`. Các chữ số được trình bày phản ánh biểu diễn, không tự khẳng định thêm độ chính xác thực nghiệm.

**Câu 4.** Vì sao `new BigDecimal("12.3400").scale()` và `precision()` khác nhau?

**Đáp án:** Scale là 4 vị trí sau dấu chấm; precision là 6 chữ số có nghĩa trong unscaled value. Chúng đo hai thuộc tính khác nhau.

**Câu 5.** Hai khoản `10.005` và `0.005`, `HALF_UP` về scale 2, tổng rounded sau cùng so với rounded từng khoản?

**Đáp án:** Round tổng là `10.01`; cộng từng khoản đã rounded là `10.02`. Chính sách hợp đồng quyết định cách thực hiện.

**Câu 6.** Nếu muốn từ chối một decimal có phần lẻ khi chuyển sang `long`, chọn phương thức nào?

**Đáp án:** `longValueExact()`; phương thức ném `ArithmeticException` nếu có phần thập phân khác 0 hoặc vượt miền `long`.

**Câu 7.** Vì sao không được cộng `Money("USD", x)` với `Money("EUR", y)` trực tiếp?

**Đáp án:** Currency là một phần của ý nghĩa giá trị. Cần quy trình chuyển đổi tỷ giá có ngày hiệu lực/quy tắc làm tròn cụ thể, hoặc từ chối phép cộng.

**Câu 8.** Khi nào `double` vẫn là lựa chọn hợp lý cho measurement?

**Đáp án:** Khi dữ liệu bản chất xấp xỉ, chi phí xử lý/thuật toán quan trọng, sai số dấu phẩy động nằm trong mức cho phép, và hợp đồng không đòi decimal exact.

**Câu 9.** Nếu đo chiều dài `1.234 m` với sai số ±`0.01 m`, hiển thị `1.234000 m` có chính xác hơn không?

**Đáp án:** Không. Dấu 0 hiển thị thêm không giảm độ không chắc chắn của phép đo; báo cáo phải theo quy tắc chữ số có nghĩa và sai số đo.

**Câu 10.** Vì sao value object/record hữu ích cho thiết kế dữ liệu số?

**Đáp án:** Nó đặt tên miền dữ liệu, kiểm tra invariant, hạn chế phép toán không hợp lệ như cộng chéo đơn vị/currency, đồng thời gom logic chuyển đổi và rounding vào nơi có nghĩa rõ ràng.

## 13. Tài liệu Java chính thức

- [Java SE 17 — BigDecimal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): decimal, precision, scale, immutable operations và round.
- [Java SE 17 — RoundingMode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/RoundingMode.html): định nghĩa các chế độ làm tròn.
- [Java SE 17 — Math.addExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#addExact(long,long)): phát hiện overflow kiểu nguyên.
- [Java SE 17 — BigInteger](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): số nguyên độ chính xác tùy ý.
- [Java SE 17 — NumberFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): định dạng số theo locale, tách khỏi phép tính nghiệp vụ.

**Ghi nhớ:** **Số đếm** đòi quy tắc về tính nguyên và phạm vi; **đại lượng đo** đòi giá trị đi cùng đơn vị và ý nghĩa sai số; **giá trị decimal có làm tròn** đòi precision, scale, rounding mode và ranh giới áp dụng rõ ràng. Thiết kế đúng mô hình trước, rồi chọn `int`/`long`/`BigInteger`/`double`/`BigDecimal` phù hợp với nghĩa của dữ liệu.
