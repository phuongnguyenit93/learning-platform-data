# BigDecimal.toPlainString() và bảo toàn cách trình bày mong muốn

## 1. Mục tiêu: xuất số thập phân ở dạng thông thường

`BigDecimal` trong Java biểu diễn số thập phân có độ chính xác tùy ý. Một số có thể được xuất dưới dạng **ký pháp khoa học** như `1E+3` hoặc `1.2E-7`. Khi cần một chuỗi số thập phân thông thường, **không chứa `E` hoặc `e` để biểu diễn số mũ**, hãy dùng `toPlainString()`:

```java
BigDecimal large = new BigDecimal("1E+3");
BigDecimal small = new BigDecimal("1.2E-7");

System.out.println(large.toString());      // 1E+3
System.out.println(large.toPlainString()); // 1000
System.out.println(small.toString());      // 1.2E-7
System.out.println(small.toPlainString()); // 0.00000012
```

`toPlainString()` chỉ **chuyển cách biểu diễn của giá trị thành `String`**. Nó không làm tròn, không thay đổi `BigDecimal` nguồn, không thêm dấu phân cách hàng nghìn và không tự chọn số lượng chữ số thập phân theo nghiệp vụ. Muốn “bảo toàn cách trình bày mong muốn” cần phân biệt rõ **giá trị**, **scale**, **cách chuyển ra chuỗi** và **định dạng dành cho người đọc**.

> Các đoạn mã minh họa rời bên dưới sử dụng `import java.math.BigDecimal;` và, khi có làm tròn, `import java.math.RoundingMode;`. Chương trình Java 17+ đầy đủ có lệnh biên dịch và đầu ra nằm ở mục 7.

## 2. Ba cách chuyển BigDecimal sang chuỗi

Ba phương thức liên quan có mục đích khác nhau:

| Phương thức | Cách biểu diễn | Điểm cần nhớ |
| --- | --- | --- |
| `toString()` | Chuỗi chuẩn (*canonical*) của `BigDecimal`, có thể dùng ký pháp khoa học. | Đặc tả bảo đảm chuỗi thể hiện phân biệt được cặp `unscaledValue` và `scale`; có thể dùng để tái tạo cùng trạng thái số học và scale qua constructor nhận `String`. |
| `toPlainString()` | Dạng thập phân thông thường, không dùng số mũ. | Dễ đọc hoặc phù hợp nơi yêu cầu decimal text không số mũ; khi scale âm, chuyển lại từ chuỗi này có thể **khác scale**. |
| `toEngineeringString()` | Có thể dùng ký pháp kỹ thuật, với số mũ (khi có) là bội số của 3. | Hữu ích cho biểu diễn kỹ thuật; không phải lựa chọn thay cho `toPlainString()` nếu đầu ra cấm ký pháp số mũ. |

Ví dụ:

```java
BigDecimal a = new BigDecimal("123.4500");
BigDecimal b = new BigDecimal("1E+3");
BigDecimal c = new BigDecimal("1.2E-7");

System.out.println(a.toString());      // 123.4500
System.out.println(a.toPlainString()); // 123.4500
System.out.println(b.toString());      // 1E+3
System.out.println(b.toPlainString()); // 1000
System.out.println(c.toString());      // 1.2E-7
System.out.println(c.toPlainString()); // 0.00000012
```

Với nhiều giá trị thông thường, `toString()` và `toPlainString()` có thể giống hệt. Sự khác biệt nổi bật khi đối tượng có **scale âm** hoặc giá trị đủ nhỏ để `toString()` chọn ký pháp khoa học theo quy tắc biểu diễn của `BigDecimal`.

`String.valueOf(bigDecimal)` và phép nối chuỗi như `"value=" + bigDecimal` gọi đến cách biểu diễn `toString()` thông qua chuyển đối tượng sang chuỗi. Nếu yêu cầu cụ thể là **không số mũ**, hãy gọi `toPlainString()` tường minh.

## 3. Vì sao xuất hiện E+3 hoặc E-7? Vai trò của scale

`BigDecimal` được xác định bởi một số nguyên không xét dấu phẩy (*unscaled value*) và một số nguyên `scale`:

```text
giá trị = unscaledValue × 10^(-scale)
```

Ví dụ:

| Khởi tạo | Trị số | `scale()` | `toString()` | `toPlainString()` |
| --- | --- | ---: | --- | --- |
| `new BigDecimal("12.3400")` | 12.3400 | 4 | `12.3400` | `12.3400` |
| `new BigDecimal("1E+3")` | 1000 | -3 | `1E+3` | `1000` |
| `new BigDecimal("1.2E-7")` | 0.00000012 | 8 | `1.2E-7` | `0.00000012` |
| `new BigDecimal("0.00")` | 0 | 2 | `0.00` | `0.00` |

`scale` không phải số chữ số có nghĩa (*precision*). Nó cho biết vị trí dấu thập phân đối với `unscaledValue`. Scale **có thể âm**: `1E+3` biểu diễn `1 × 10³` và có scale `-3`. Khi chuyển sang dạng plain, `toPlainString()` viết đủ chữ số 0 thành `1000`.

Với scale không âm, `toPlainString()` in vị trí dấu chấm thập phân phù hợp, kể cả các chữ số 0 cuối do scale quy định; ví dụ `12.3400` vẫn là `12.3400`. Đây là cách giữ **biểu diễn decimal đã có trong đối tượng** khi cần hiển thị đúng số lượng chữ số lẻ đang lưu.

Điều đó khác với việc khôi phục **chính xác chuỗi nhập ban đầu**: `BigDecimal` không lưu mọi ký tự, dấu `+`, số 0 ở đầu hoặc kiểu viết số mũ trong văn bản gốc.

## 4. toPlainString() không làm tròn và không tự cố định chữ số thập phân

So sánh ba nhu cầu riêng biệt:

1. **Không dùng số mũ:** `value.toPlainString()`.
2. **Buộc kết quả có đúng hai chữ số sau dấu chấm:** trước hết chọn `value.setScale(2, roundingMode)`, sau đó mới `toPlainString()`.
3. **Hiển thị cho con người với dấu phân nhóm, dấu thập phân theo ngôn ngữ hoặc ký hiệu tiền tệ:** dùng công cụ định dạng như `NumberFormat` hoặc `DecimalFormat` với `Locale` và quy tắc làm tròn phù hợp.

Ví dụ:

```java
BigDecimal amount = new BigDecimal("12.3");

System.out.println(amount.toPlainString());           // 12.3
System.out.println(amount.setScale(2).toPlainString()); // 12.30
System.out.println(amount.toPlainString());           // 12.3
```

`setScale(2)` ở đây tăng scale từ 1 lên 2 nên không phải làm tròn. Phương thức trả về **`BigDecimal` kết quả mới về mặt ngữ nghĩa**; đối tượng `amount` ban đầu không thay đổi vì `BigDecimal` bất biến. Không nên giả định JVM luôn tạo tham chiếu vật lý khác, đặc biệt khi scale yêu cầu đã đúng.

Nếu cần giảm scale mà phải loại chữ số khác 0, overload `setScale(int)` sẽ ném `ArithmeticException`. Khi nghiệp vụ cho phép làm tròn, nêu rõ `RoundingMode`:

```java
BigDecimal raw = new BigDecimal("12.345");

System.out.println(raw.toPlainString()); // 12.345
System.out.println(
        raw.setScale(2, RoundingMode.HALF_UP).toPlainString()
); // 12.35
```

**Không làm tròn vô tình trong bước trình bày.** `toPlainString()` tự nó không thay giá trị; lời gọi `setScale(2, HALF_UP)` đã chủ động áp dụng quy tắc làm tròn. Với tiền tệ, thuế, thống kê hoặc dữ liệu lưu trữ, cần xác định rõ thời điểm và phương pháp làm tròn theo hợp đồng nghiệp vụ.

## 5. “Bảo toàn cách trình bày” có nhiều mức khác nhau

Cần xác định chính xác thứ muốn giữ:

### 5.1. Giữ trị số toán học

Hai chuỗi `1E+3` và `1000` mô tả cùng một số. Trong phép so sánh trị số `BigDecimal.compareTo()`, chúng bằng nhau:

```java
BigDecimal scientific = new BigDecimal("1E+3");
BigDecimal plain = new BigDecimal("1000");

System.out.println(scientific.compareTo(plain)); // 0
```

Nếu giao thức chỉ yêu cầu trị số decimal chính xác và cấm số mũ, `toPlainString()` có thể phù hợp.

### 5.2. Giữ scale đang có khi scale không âm

`new BigDecimal("12.3400").toPlainString()` cho `"12.3400"`; hai chữ số 0 cuối vẫn xuất hiện. Giá trị `new BigDecimal("12.34")` chỉ in `"12.34"` vì scale của nó là 2, không phải 4. `toPlainString()` phản ánh trạng thái biểu diễn đã có, **không tự khôi phục** số chữ số 0 mà một bước xử lý trước đó đã bỏ.

Nếu phải luôn in hai chữ số thập phân, tạo đối tượng có scale 2 theo quy tắc phù hợp trước khi xuất.

### 5.3. Giữ nguyên cả chữ viết người dùng đã nhập

`BigDecimal` không lưu bản sao nguyên văn chuỗi nguồn. Ví dụ:

```java
BigDecimal x = new BigDecimal("00012.300");
System.out.println(x.toPlainString()); // 12.300
```

Số 0 ở đầu không còn. Tương tự, cách viết `+12.30`, `12.30` và một số kiểu ký pháp số mũ có thể được chuẩn hóa khi tạo `BigDecimal`. Nếu yêu cầu sản phẩm là **lưu chính xác chuỗi người dùng đã nhập** (chẳng hạn biên bản, đơn hàng có chữ viết gốc, trường văn bản được ký số), phải lưu riêng `String originalInput`, đồng thời phân tích thành `BigDecimal` để tính toán khi cần.

Ví dụ về số 0 âm: `new BigDecimal("-0.00").toPlainString()` xuất `"0.00"`, không giữ dấu âm đầu vào. `BigDecimal` biểu diễn giá trị 0, không giữ “negative zero” như một thành phần ngữ nghĩa riêng của dữ liệu decimal.

### 5.4. Giữ scale âm khi chuyển qua chuỗi rồi đọc lại

Đây là trường hợp **dễ bị bỏ sót**:

```java
BigDecimal original = new BigDecimal("1E+3");     // scale = -3
String plainText = original.toPlainString();      // "1000"
BigDecimal restored = new BigDecimal(plainText);  // scale = 0

System.out.println(original.scale());           // -3
System.out.println(restored.scale());           // 0
System.out.println(original.equals(restored));  // false
System.out.println(original.compareTo(restored)); // 0
```

Hai đối tượng bằng nhau về **trị số**, nhưng `equals()` trả `false` vì `BigDecimal.equals()` xét cả biểu diễn và scale. Không nên dùng `toPlainString()` làm chuỗi *round-trip* khi hợp đồng dữ liệu cần bảo toàn **cả scale âm**.

Ngược lại:

```java
BigDecimal original = new BigDecimal("1E+3");
BigDecimal restored = new BigDecimal(original.toString());

System.out.println(original.equals(restored)); // true
```

`toString()` được thiết kế là biểu diễn chuẩn một-một của cặp unscaled value và scale, thuận lợi cho việc chuyển ra chuỗi rồi khôi phục `BigDecimal` với cùng biểu diễn. Vì vậy, lựa chọn phương thức xuất cần xuất phát từ yêu cầu **hiển thị không số mũ** hay **bảo toàn dữ liệu BigDecimal khi truyền/lưu**.

## 6. Tác động của stripTrailingZeros() và các phép chuyển đổi trước khi xuất

`stripTrailingZeros()` bỏ các chữ số 0 cuối có thể bỏ mà không thay đổi giá trị số học, rồi trả về `BigDecimal`. Nó có thể thay đổi scale sang **âm**:

```java
BigDecimal amount = new BigDecimal("1000");
BigDecimal stripped = amount.stripTrailingZeros();

System.out.println(amount.toPlainString());   // 1000
System.out.println(stripped.toString());      // 1E+3
System.out.println(stripped.toPlainString()); // 1000
System.out.println(stripped.scale());         // -3
```

Nếu sau khi `stripTrailingZeros()` lại gọi `toString()`, ký pháp khoa học có thể xuất hiện dù đầu vào ban đầu là số thông thường. `toPlainString()` tạo dạng không số mũ, nhưng **không phục hồi scale và dấu 0 cuối của biểu diễn gốc** đã bị `stripTrailingZeros()` loại bỏ.

Ví dụ:

```java
BigDecimal original = new BigDecimal("12.3400");
BigDecimal stripped = original.stripTrailingZeros();

System.out.println(original.toPlainString()); // 12.3400
System.out.println(stripped.toPlainString()); // 12.34
```

Nếu hợp đồng hiển thị đòi đúng bốn vị trí thập phân, đừng gọi `stripTrailingZeros()` trước khi xuất; hoặc áp dụng `setScale(4)` khi việc nâng scale là có chủ đích. Nên định nghĩa một nơi chịu trách nhiệm cho việc “chuẩn hóa số để lưu” và một nơi cho việc “định dạng số để xem”, thay vì trộn các thao tác này trong nhiều lớp.

### Tránh tạo BigDecimal từ double nếu yêu cầu decimal chính xác

`new BigDecimal(0.1)` biểu diễn chính xác giá trị nhị phân của `double` literal `0.1`, vốn là một xấp xỉ của số thập phân 0.1. `toPlainString()` **không sửa được** sai khác đầu vào đó. Ưu tiên:

```java
BigDecimal fromText = new BigDecimal("0.1");
BigDecimal fromDouble = BigDecimal.valueOf(0.1);

System.out.println(fromText.toPlainString());   // 0.1
System.out.println(fromDouble.toPlainString()); // 0.1
```

`BigDecimal.valueOf(double)` sử dụng biểu diễn chuỗi của `double` để dựng `BigDecimal`; điều đó thường phù hợp cho literal như `0.1`, nhưng không thể khôi phục chữ số thập phân đã bị mất bởi những phép tính `double` trước đó.

## 7. Chương trình Java 17+ chạy độc lập

Lưu toàn bộ mã sau thành `BigDecimalPlainStringDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;

public class BigDecimalPlainStringDemo {
    public static void main(String[] args) {
        BigDecimal thousand = new BigDecimal("1E+3");
        BigDecimal tiny = new BigDecimal("1.2E-7");

        System.out.println("thousand toString = " + thousand.toString());
        System.out.println("thousand plain = " + thousand.toPlainString());
        System.out.println("tiny toString = " + tiny.toString());
        System.out.println("tiny plain = " + tiny.toPlainString());

        BigDecimal entered = new BigDecimal("12.3400");
        System.out.println("entered plain = " + entered.toPlainString());
        System.out.println("stripped plain = "
                + entered.stripTrailingZeros().toPlainString());

        BigDecimal oneDecimal = new BigDecimal("12.3");
        System.out.println("one decimal = " + oneDecimal.toPlainString());
        System.out.println("two decimals = "
                + oneDecimal.setScale(2).toPlainString());

        BigDecimal rounded = new BigDecimal("12.345");
        System.out.println("rounded two decimals = "
                + rounded.setScale(2, RoundingMode.HALF_UP)
                         .toPlainString());

        BigDecimal fromPlain = new BigDecimal(thousand.toPlainString());
        BigDecimal fromCanonical = new BigDecimal(thousand.toString());
        System.out.println("original scale = " + thousand.scale());
        System.out.println("plain round-trip scale = " + fromPlain.scale());
        System.out.println("plain equals original = "
                + thousand.equals(fromPlain));
        System.out.println("canonical equals original = "
                + thousand.equals(fromCanonical));
        System.out.println("same numeric value = "
                + (thousand.compareTo(fromPlain) == 0));
    }
}
```

Biên dịch và chạy từ thư mục chứa file:

```bash
javac BigDecimalPlainStringDemo.java
java BigDecimalPlainStringDemo
```

Kết quả chuẩn:

```text
thousand toString = 1E+3
thousand plain = 1000
tiny toString = 1.2E-7
tiny plain = 0.00000012
entered plain = 12.3400
stripped plain = 12.34
one decimal = 12.3
two decimals = 12.30
rounded two decimals = 12.35
original scale = -3
plain round-trip scale = 0
plain equals original = false
canonical equals original = true
same numeric value = true
```

Đối chiếu phần đầu để thấy lợi ích của `toPlainString()` với số mũ; phần giữa cho thấy dấu 0 cuối được giữ hay bị loại tùy **scale hiện tại**; phần cuối chứng minh một bản decimal text không số mũ có thể **mất thông tin scale âm** khi đọc lại, dù vẫn bảo toàn giá trị số học.

## 8. Hiển thị theo locale, tiền tệ và trao đổi dữ liệu

### 8.1. Chuỗi plain phù hợp khi nào?

`toPlainString()` hữu ích khi đích yêu cầu một số thập phân ASCII cơ bản:

- Giá trị đặt vào tệp văn bản hoặc một trường decimal quy định **không dùng số mũ**.
- Chuỗi số thập phân trao đổi với hệ thống có thể đọc dấu chấm làm dấu thập phân, không yêu cầu dấu phân nhóm.
- Các thông báo kỹ thuật cần xem toàn bộ chữ số thập phân thay vì ký pháp khoa học.

Tuy nhiên, cần kiểm tra hợp đồng của hệ thống đích: có nơi chấp nhận ký pháp số mũ, có nơi bắt buộc scale cố định, có nơi giới hạn số chữ số hoặc độ dài. `toPlainString()` không bảo đảm đáp ứng mọi giới hạn đó.

### 8.2. Giao diện cho người dùng thường cần formatter

Ví dụ muốn hiển thị `1234.50` theo chuẩn sử dụng dấu chấm phân nhóm và dấu phẩy thập phân ở Đức:

```java
import java.math.BigDecimal;
import java.text.NumberFormat;
import java.util.Locale;

public class LocaleNumberDemo {
    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("1234.50");

        NumberFormat formatter = NumberFormat.getNumberInstance(Locale.GERMANY);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        System.out.println(amount.toPlainString());
        System.out.println(formatter.format(amount));
    }
}
```

Lưu thành `LocaleNumberDemo.java` rồi chạy `javac LocaleNumberDemo.java` và `java LocaleNumberDemo`. Với dữ liệu và `Locale.GERMANY` trên Java 17+, đầu ra:

```text
1234.50
1.234,50
```

Khác biệt ở đây là **quy tắc trình bày của locale**, không phải thay đổi giá trị trong `BigDecimal`. `NumberFormat` có khả năng làm tròn để vừa mức chữ số hiển thị; nếu có yêu cầu nghiệp vụ cụ thể về làm tròn, hãy thiết lập và kiểm thử chính sách phù hợp thay vì phụ thuộc hoàn toàn vào mặc định của formatter. Với tiền tệ, sử dụng formatter tiền tệ khi cần ký hiệu tiền, vị trí ký hiệu và quy tắc hiển thị; không tự ghép ký hiệu tiền vào chuỗi plain nếu có yêu cầu địa phương hóa.

### 8.3. Lưu trữ và serialization: chọn theo hợp đồng

Nếu muốn bảo toàn **cả unscaled value và scale**, `toString()` có đặc tính round-trip phù hợp cho `BigDecimal` qua constructor `String`. Cũng có thể lưu tường minh `unscaledValue` cùng `scale` khi thiết kế cấu trúc dữ liệu chuyên biệt.

Nếu hợp đồng yêu cầu **đầu ra không có ký pháp số mũ** và chỉ quan tâm trị số, `toPlainString()` thường hợp lý. Khi đọc lại, đừng giả định `equals()` giữ nguyên với số từng có scale âm; so sánh `compareTo() == 0` nếu mục tiêu thực sự là bằng nhau về trị số.

Đối với JSON, cơ sở dữ liệu, XML hoặc API, kiểm tra kiểu dữ liệu, quy tắc serialize của thư viện và giới hạn độ dài/precision/scale cụ thể. Không nên tự cho rằng mọi serializer đều gọi `toPlainString()`, hoặc rằng mọi hệ thống lưu chữ số 0 và scale giống Java.

### 8.4. Cân nhắc hiệu năng và độ dài

Một `BigDecimal` chứa số mũ rất lớn vẫn có thể được biểu diễn dưới dạng chuỗi khoa học ngắn gọn. Khi chuyển thành dạng plain, nhiều chữ số 0 phải xuất hiện trực tiếp.

```java
BigDecimal large = new BigDecimal("1E+10");
System.out.println(large.toPlainString()); // 10000000000
```

Với số mũ quá lớn, chuỗi plain có thể dài bất thường, tiêu tốn bộ nhớ và không phù hợp với giới hạn kích thước payload. Trước khi xuất dữ liệu đầu vào không tin cậy, cần giới hạn phạm vi trị số, scale, độ dài hoặc sử dụng biểu diễn khác theo yêu cầu giao thức. Không dùng `toPlainString()` vô điều kiện trên dữ liệu có số mũ không giới hạn.

## 9. Mẫu áp dụng và các lỗi thường gặp

### Mẫu 1 — Decimal text không số mũ, có đúng hai chữ số thập phân

Khi hợp đồng yêu cầu đúng 2 chữ số sau dấu chấm và quy định `HALF_UP`:

```java
static String toPlainTwoDecimals(BigDecimal value) {
    return value.setScale(2, RoundingMode.HALF_UP).toPlainString();
}
```

Đây là **phương thức minh họa** phải đặt trong một lớp và import `BigDecimal`, `RoundingMode` tương ứng; chính sách `HALF_UP` và scale 2 chỉ là ví dụ. Một số nghiệp vụ có quy tắc làm tròn riêng hoặc không cho phép làm tròn giá trị gốc.

Nếu tuyệt đối không cho phép mất chữ số, có thể thay bằng `value.setScale(2, RoundingMode.UNNECESSARY).toPlainString()`. Trường hợp đầu vào cần giảm scale mà có chữ số khác 0 bị bỏ sẽ ném `ArithmeticException`, giúp phát hiện dữ liệu vi phạm hợp đồng.

### Mẫu 2 — Bảo toàn chính xác text nhập vào

Nếu yêu cầu giữ mọi ký tự gốc:

```java
String originalInput = "00012.300";
BigDecimal value = new BigDecimal(originalInput);

System.out.println(originalInput);        // 00012.300
System.out.println(value.toPlainString()); // 12.300
```

Lưu chuỗi gốc riêng; `BigDecimal` giữ thông tin để tính toán, **không phải kho lưu nguyên văn**. Đặc biệt cần chú ý khoảng trắng, ký hiệu cộng, số 0 đầu và chuẩn dấu phân cách theo locale trước khi parse.

### Mẫu 3 — Cấu trúc round-trip có giữ scale

Khi mục tiêu là khôi phục đúng đối tượng `BigDecimal` theo `equals()`, dùng `toString()` rồi `new BigDecimal(text)`, hoặc lưu hai thành phần `unscaledValue` và `scale`. Không dùng plain text thay thế tùy ý khi scale âm có thể xuất hiện.

### Sai lầm thường gặp

1. **Cho rằng `toPlainString()` tự làm tròn:** nó chỉ xuất chuỗi. Muốn giảm chữ số phải có thao tác làm tròn tường minh.
2. **Cho rằng `toPlainString()` luôn có đúng hai chữ số lẻ:** số chữ số phụ thuộc scale đang có. `12.3` vẫn là `12.3`, còn `12.3000` vẫn là `12.3000` nếu chưa thay scale.
3. **Cho rằng chuỗi kết quả luôn khớp nguyên văn input:** `"00012.300"` thành `"12.300"`; mất cách viết gốc.
4. **Dùng `stripTrailingZeros()` trước khi cần giữ số chữ số lẻ:** `12.3400` thành `12.34`. Đây là thay đổi biểu diễn có chủ đích và không thể đoán lại mọi dấu 0 ban đầu.
5. **Dùng `toPlainString()` cho serialization phải giữ scale âm:** `1E+3` thành `1000`, parse lại có scale 0 thay vì -3.
6. **Dùng `new BigDecimal(double)` và nghĩ rằng xuất plain sửa được sai số đầu vào:** không đúng; nên kiểm soát cách tạo số và toán học trước khi chuyển sang chuỗi.
7. **Dùng `toPlainString()` để định dạng locale:** nó không thêm dấu phân cách hàng nghìn, không chọn dấu phẩy thập phân và không hiển thị đơn vị tiền.
8. **Dùng `equals()` khi chỉ cần bằng nhau về trị số:** `1E+3` và `1000` có thể khác scale; dùng `compareTo() == 0` cho so sánh trị số.
9. **Bỏ qua quy mô của chuỗi plain:** số có mũ lớn có thể bung ra nhiều chữ số 0; áp đặt giới hạn theo giao thức trước khi xuất.
10. **Nhầm chuỗi với đối tượng:** `toPlainString()` trả `String`; việc gọi nó không sửa hay định dạng vĩnh viễn `BigDecimal` nguồn. Muốn lưu cách trình bày, lưu riêng chuỗi, cấu hình formatter hoặc hợp đồng định dạng.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `new BigDecimal("1E+3").toPlainString()` là `"1000"`?

**Đáp án:** `toPlainString()` biểu diễn decimal không số mũ. Giá trị `1 × 10³` được viết bằng các chữ số thông thường.

**Câu 2.** Vì sao `new BigDecimal("12.3400").toPlainString()` vẫn là `"12.3400"`?

**Đáp án:** Đối tượng có scale 4. `toPlainString()` không tự bỏ số 0 cuối hoặc chọn scale khác.

**Câu 3.** Nếu muốn `"12.30"` từ `new BigDecimal("12.3")` thì làm gì?

**Đáp án:** `value.setScale(2).toPlainString()`, vì chỉ tăng scale từ 1 lên 2 và thêm số 0 không mất độ chính xác.

**Câu 4.** Nếu cần `"12.35"` từ `new BigDecimal("12.345")` với quy tắc `HALF_UP`?

**Đáp án:** `value.setScale(2, RoundingMode.HALF_UP).toPlainString()`. Việc làm tròn đến `12.35` diễn ra ở `setScale()`.

**Câu 5.** `new BigDecimal(new BigDecimal("1E+3").toPlainString())` có `equals()` với bản gốc không?

**Đáp án:** Không. Bản gốc có scale -3, bản parse từ `"1000"` có scale 0. `compareTo()` vẫn trả 0 vì trị số bằng nhau.

**Câu 6.** Lúc nào ưu tiên `toString()` thay vì `toPlainString()`?

**Đáp án:** Khi cần biểu diễn canonical có thể tái tạo đúng unscaled value và scale qua constructor nhận chuỗi, và hợp đồng cho phép ký pháp khoa học.

**Câu 7.** Muốn hiện `"1.234,50"` theo quy ước Đức thì dùng `toPlainString()` hay formatter?

**Đáp án:** Dùng `NumberFormat` hoặc `DecimalFormat` được cấu hình theo `Locale.GERMANY`, với chính sách chữ số thập phân và rounding phù hợp.

**Câu 8.** Muốn lưu lại chính xác input `"00012.300"`, chỉ giữ `BigDecimal` có đủ không?

**Đáp án:** Không. Cần lưu riêng chuỗi input gốc nếu những chữ số 0 đầu hoặc dấu/ký hiệu định dạng ban đầu là dữ liệu cần bảo toàn.

**Ghi nhớ:** `toPlainString()` tạo **chuỗi số thập phân không dùng ký pháp khoa học** từ `BigDecimal` đang có. Nó bảo toàn trị số nhưng **không tự cố định scale, làm tròn, định dạng locale hay lưu nguyên văn văn bản nhập**. Nếu cần bảo toàn scale âm khi serialize, cân nhắc `toString()` hoặc lưu cấu trúc; nếu cần số chữ số hiển thị cụ thể, áp dụng `setScale()` theo đúng quy tắc rồi mới xuất.
