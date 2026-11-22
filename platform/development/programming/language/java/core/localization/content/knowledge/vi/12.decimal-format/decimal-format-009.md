# Giới hạn ép kiểu từ NumberFormat sang DecimalFormat trong Java

`java.text.NumberFormat` là lớp trừu tượng để **định dạng và phân tích số theo locale**. `java.text.DecimalFormat` là một lớp con cụ thể có thêm pattern, bộ ký hiệu dấu thập phân/phân nhóm, cách xử lý parse `BigDecimal`, prefix/suffix và nhiều cấu hình riêng. Khi nhận một `NumberFormat` từ factory, lập trình viên thường muốn chuyển sang `DecimalFormat` để dùng những tính năng này. Nhưng **không phải mọi `NumberFormat` đều là `DecimalFormat`**, và Java **không cam kết** tất cả factory đều trả về lớp con đó.

Quy tắc quan trọng nhất: **chỉ ép kiểu khi đối tượng thực sự là `DecimalFormat`**, kiểm tra bằng `instanceof`; nếu chức năng cần thiết đã có ở `NumberFormat` thì **không cần ép kiểu**. Nếu ứng dụng bắt buộc phải có pattern và các phương thức đặc thù của `DecimalFormat`, có thể **khởi tạo `DecimalFormat` tường minh với `DecimalFormatSymbols` phù hợp**, nhưng cần hiểu sự khác biệt với formatter được factory tự lựa chọn.

Bài học áp dụng cho **Java 17+**, minh họa lỗi biên dịch, `ClassCastException`, pattern matching cho `instanceof`, trường hợp `CompactNumberFormat`, sự phụ thuộc vào locale provider và các lựa chọn thiết kế an toàn.

## 1. Quan hệ kế thừa không có nghĩa ép kiểu luôn hợp lệ

Cấu trúc các lớp liên quan:

```text
java.lang.Object
    └── java.text.Format
           └── java.text.NumberFormat (abstract)
                  ├── java.text.DecimalFormat
                  ├── java.text.CompactNumberFormat
                  └── java.text.ChoiceFormat
                       (+ subclass/provider khác)
```

Có hai hướng khác nhau:

- **Upcast** (lớp con → lớp cha): `NumberFormat f = new DecimalFormat();`, được Java cho phép và an toàn. Đối tượng thực vẫn là `DecimalFormat`, chỉ kiểu của biến tham chiếu rộng hơn.
- **Downcast** (lớp cha → lớp con): `DecimalFormat d = (DecimalFormat) f;`, chỉ chạy được khi đối tượng thực trong `f` là một `DecimalFormat` hoặc lớp con của nó. Nếu không, JVM ném `ClassCastException`.

Không thể suy ra đối tượng thực chỉ từ khai báo biến `NumberFormat`. Một tham chiếu cùng kiểu có thể lần lượt trỏ tới một `DecimalFormat`, một `CompactNumberFormat`, một `ChoiceFormat`, hoặc một subclass do nhà cung cấp dịch vụ triển khai.

**Phân biệt kiểu khai báo và kiểu thực tế:**

```java
// Đoạn mã minh họa, cần import java.text.*.
NumberFormat number = new DecimalFormat("0.00"); // upcast
boolean ok = number instanceof DecimalFormat;   // true

NumberFormat choice = new ChoiceFormat(
        new double[] {0, 1},
        new String[] {"zero", "one or more"});
boolean notDecimal = choice instanceof DecimalFormat; // false
```

`number` và `choice` đều có kiểu khai báo là `NumberFormat`. Nhưng chúng thuộc **hai lớp con khác nhau**. Java không “biến” một formatter thành formatter khác khi ta cast: phép cast chỉ **kiểm tra kiểu runtime** và trả lại một tham chiếu có kiểu hẹp hơn nếu kiểm tra thành công.

## 2. Vì sao factory NumberFormat không bảo đảm DecimalFormat?

Các factory phổ biến:

```java
NumberFormat number = NumberFormat.getNumberInstance(locale);
NumberFormat general = NumberFormat.getInstance(locale);
NumberFormat currency = NumberFormat.getCurrencyInstance(locale);
NumberFormat percent = NumberFormat.getPercentInstance(locale);
NumberFormat integer = NumberFormat.getIntegerInstance(locale);
NumberFormat compact = NumberFormat.getCompactNumberInstance(
        locale, NumberFormat.Style.SHORT);
```

Đây là **fragment**: biến `locale` phải là một `Locale` đã khai báo, và cần `import java.text.NumberFormat;`.

Các phương thức này có **kiểu trả về khai báo là `NumberFormat`**, cho phép JDK chọn triển khai phù hợp theo kiểu định dạng, locale, dữ liệu locale và nhà cung cấp dịch vụ (`NumberFormatProvider`). Trong nhiều bản JDK chuẩn, các factory số thường/tiền tệ/phần trăm thường trả `DecimalFormat`. Tuy nhiên, đó **không phải hợp đồng mà ứng dụng nên dựa vào một cách tuyệt đối**.

Đặc biệt, từ Java 12 có `getCompactNumberInstance(...)` để định dạng rút gọn như số nghìn/triệu. Triển khai chuẩn của factory này sử dụng `CompactNumberFormat` — một **lớp con khác** của `NumberFormat`, **không kế thừa `DecimalFormat`**. Chưa kể các locale service provider có thể trả về lớp con phù hợp khác.

Tài liệu Oracle của `DecimalFormat` hướng dẫn kiểm tra kiểu trước khi dùng các tính năng riêng của nó. Do đó, lời khuyên “cứ cast, với Locale.US chắc chắn được” không phải một nguyên tắc viết code có tính di động.

### Ba tầng cần nhớ

| Tầng | Điều ta biết chắc | Điều không nên tự suy diễn |
| --- | --- | --- |
| **Compile-time** | Factory khai báo trả về `NumberFormat` | Không có phép gán ngầm sang `DecimalFormat` |
| **Runtime** | `instanceof` và cast kiểm tra lớp thật của object | Không phải mọi object `NumberFormat` là `DecimalFormat` |
| **Triển khai/locale** | Factory tìm formatter phù hợp với môi trường | Không thể coi một class cụ thể là bảo đảm trên mọi JDK/provider |

**`getClass().getName()`** có thể dùng để chẩn đoán lớp thực khi chạy, nhưng không dùng so sánh tên class để quyết định ép kiểu: điều kiện `instanceof DecimalFormat` mới là đúng về mặt hệ kiểu, kể cả với subclass của `DecimalFormat`.

## 3. Lỗi biên dịch so với lỗi lúc chạy

Đoạn sau **không biên dịch**:

```java
// KHÔNG HỢP LỆ: return type của factory là NumberFormat.
DecimalFormat bad = NumberFormat.getNumberInstance(Locale.US);
```

Trình biên dịch không được phép gán tự động một giá trị kiểu cha `NumberFormat` vào biến kiểu con `DecimalFormat`. Nếu thêm cast:

```java
// Biên dịch được; runtime vẫn phụ thuộc class thực tế.
DecimalFormat maybe =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.US);
```

thì chỉ **chuyển trách nhiệm kiểm tra xuống runtime**. Khi factory trả một subclass khác, câu lệnh này ném `ClassCastException`.

Nguy cơ tăng lên nếu nhiều môi trường dùng locale provider khác nhau, JDK/vendor khác nhau, hoặc code sau này đổi từ `getNumberInstance` sang `getCompactNumberInstance` nhưng giữ nguyên cast cũ.

### Ví dụ chắc chắn tạo ClassCastException mà không phụ thuộc provider

Lưu **`CastFailureDemo.java`**:

```java
import java.text.ChoiceFormat;
import java.text.DecimalFormat;
import java.text.NumberFormat;

public class CastFailureDemo {
    public static void main(String[] args) {
        NumberFormat number = new ChoiceFormat(
                new double[] {0, 1},
                new String[] {"zero", "one or more"});

        System.out.println("NumberFormat: "
                + (number instanceof NumberFormat));
        System.out.println("DecimalFormat: "
                + (number instanceof DecimalFormat));

        try {
            DecimalFormat decimal = (DecimalFormat) number;
            System.out.println(decimal.format(2));
        } catch (ClassCastException exception) {
            System.out.println("Cast failed: ClassCastException");
        }
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 CastFailureDemo.java
java CastFailureDemo
```

Stdout:

```text
NumberFormat: true
DecimalFormat: false
Cast failed: ClassCastException
```

Đây là ví dụ **cố ý tạo một formatter không phải DecimalFormat**, không cần đoán provider nào đang được cài. `ChoiceFormat` vẫn là một `NumberFormat` nhưng cast xuống một sibling class (`DecimalFormat`) là sai. Việc bắt `ClassCastException` minh họa lỗi, **không phải** khuyến nghị dùng ngoại lệ để chọn nhánh ở code thông thường.

## 4. Cách an toàn nhất: instanceof kết hợp pattern matching Java 17

Từ Java 16, cú pháp **pattern matching for `instanceof`** có thể khai báo biến đã được kiểm tra kiểu trong nhánh `if`. Java 17 hỗ trợ cú pháp này bình thường:

```java
NumberFormat formatter =
        NumberFormat.getNumberInstance(Locale.US);

if (formatter instanceof DecimalFormat decimal) {
    decimal.setDecimalSeparatorAlwaysShown(true);
    System.out.println(decimal.format(100));
} else {
    System.out.println(formatter.format(100));
}
```

Đây là **fragment trong một phương thức**, cần `import java.text.NumberFormat;`, `DecimalFormat;` và `java.util.Locale;`. Không đưa ra stdout cố định cho toàn bộ chương trình này: nếu object là `DecimalFormat`, dấu thập phân được buộc xuất hiện; nếu không, code dùng khả năng chung của `NumberFormat`.

Tương đương với cú pháp trước Java 16:

```java
if (formatter instanceof DecimalFormat) {
    DecimalFormat decimal = (DecimalFormat) formatter;
    decimal.setDecimalSeparatorAlwaysShown(true);
}
```

Nhánh `if` là bằng chứng rằng cast trong nhánh được thực hiện trên **đúng cùng đối tượng** đã kiểm tra. Nếu gọi lại factory lần thứ hai rồi cast object khác, phép kiểm tra ban đầu không bảo đảm gì cho object vừa nhận:

```java
// Không nên kiểm tra một object rồi cast một object mới.
if (formatter instanceof DecimalFormat) {
    // Đừng coi kết quả factory sau đây chắc chắn có cùng subtype:
    // DecimalFormat other = (DecimalFormat)
    //         NumberFormat.getNumberInstance(Locale.US);
}
```

Hãy giữ formatter trong một biến, kiểm tra một lần và thao tác đúng object đó.

### Chương trình hoàn chỉnh: hỗ trợ cả hai nhánh

Lưu **`SafeFactoryDemo.java`**:

```java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class SafeFactoryDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);

        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        if (formatter instanceof DecimalFormat decimal) {
            decimal.setDecimalSeparatorAlwaysShown(true);
            System.out.println("Decimal-specific settings applied");
        } else {
            System.out.println("Using NumberFormat fallback");
        }

        System.out.println("Formatted value: "
                + formatter.format(1234.5));
    }
}
```

```bash
javac -encoding UTF-8 SafeFactoryDemo.java
java SafeFactoryDemo
```

Chương trình luôn in hai dòng, nhưng **không có một stdout bất biến chung** cho mọi JDK/provider. Với triển khai `DecimalFormat` thông dụng cho `Locale.US`, hai dòng thường là:

```text
Decimal-specific settings applied
Formatted value: 1,234.50
```

Nếu factory trả subclass khác, nhánh `else` vẫn chạy và định dạng số thông qua `NumberFormat`; chuỗi có thể theo quy tắc của provider đó. Không dùng `formatter.getClass() == DecimalFormat.class`: một lớp **kế thừa `DecimalFormat`** cũng có thể được cast hợp lệ, nhưng phép so sánh class tuyệt đối lại từ chối nó.

## 5. Khi chỉ cần tính năng NumberFormat thì không nên cast

`NumberFormat` đã có nhiều phương thức phục vụ công việc phổ biến:

| Nhu cầu | API có sẵn trên NumberFormat |
| --- | --- |
| Định dạng số | `format(long)`, `format(double)`, `format(Object)` |
| Đọc số từ chuỗi | `parse(String)` |
| Bật/tắt nhóm hàng nghìn | `setGroupingUsed(boolean)` |
| Chữ số phần nguyên tối thiểu/tối đa | `setMinimumIntegerDigits(int)`, `setMaximumIntegerDigits(int)` |
| Chữ số phần lẻ tối thiểu/tối đa | `setMinimumFractionDigits(int)`, `setMaximumFractionDigits(int)` |
| Giới hạn parse ở phần nguyên | `setParseIntegerOnly(boolean)` |
| Đơn vị tiền (nếu implementation hỗ trợ) | `setCurrency(Currency)` |
| Chế độ làm tròn (nếu implementation hỗ trợ) | `setRoundingMode(RoundingMode)` |

Nên viết code theo interface khả năng cần thiết thay vì phụ thuộc một class cụ thể.

**Lưu ý quan trọng về hỗ trợ:** việc một phương thức được *khai báo* trên `NumberFormat` không có nghĩa mọi subclass triển khai được nó. Ví dụ, `NumberFormat.setRoundingMode` trong lớp cơ sở có implementation ném `UnsupportedOperationException`; subclass có hỗ trợ rounding mode phải override. Tương tự, `setCurrency` mặc định ở lớp cơ sở có thể không được hỗ trợ. Vì vậy, “không cần cast” không đồng nghĩa “mọi cấu hình đều được đảm bảo bởi mọi provider”. Nếu tính năng rất quan trọng, phải kiểm tra hành vi/capability của implementation hoặc chọn một đối tượng cụ thể đã biết.

**Chương trình chạy độc lập — `BaseApiDemo.java`**:

```java
import java.text.NumberFormat;
import java.util.Locale;

public class BaseApiDemo {
    public static void main(String[] args) {
        NumberFormat formatter =
                NumberFormat.getNumberInstance(Locale.US);

        formatter.setGroupingUsed(false);
        formatter.setMinimumFractionDigits(2);
        formatter.setMaximumFractionDigits(2);

        System.out.println("Min fraction: "
                + formatter.getMinimumFractionDigits());
        System.out.println("Max fraction: "
                + formatter.getMaximumFractionDigits());
        System.out.println("Value: "
                + formatter.format(12.5));
    }
}
```

```bash
javac -encoding UTF-8 BaseApiDemo.java
java BaseApiDemo
```

Với triển khai số thường của JDK cho `Locale.US`, kết quả là:

```text
Min fraction: 2
Max fraction: 2
Value: 12.50
```

Ưu điểm là mã vẫn sử dụng chung những khả năng có sẵn ngay cả khi factory thay đổi subtype. Nếu chỉ cần tối đa hai chữ số thập phân và grouping, **đừng ép kiểu chỉ để gọi những setter đã có trong `NumberFormat`**.

## 6. Những chức năng riêng của DecimalFormat đòi hỏi kiểm tra subtype

`DecimalFormat` cung cấp các phương thức không có ở `NumberFormat`:

| Nhu cầu nâng cao | API DecimalFormat | Ghi chú |
| --- | --- | --- |
| Áp dụng pattern không theo địa phương | `applyPattern("#,##0.00")` | Pattern ký hiệu `.`/`,` chuẩn, ký hiệu hiển thị do symbols/locale quyết định |
| Xuất pattern hiện tại | `toPattern()` | Không dùng như ID ổn định hoặc quy tắc nghiệp vụ |
| Áp dụng pattern cục bộ | `applyLocalizedPattern(...)` | Ký hiệu pattern phải đúng theo symbols hiện hành |
| Điều chỉnh dấu phân cách và chữ số | `getDecimalFormatSymbols()`, `setDecimalFormatSymbols(...)` | Cần biết ảnh hưởng đến grouping, tiền tệ, số âm |
| Luôn in dấu phân cách thập phân | `setDecimalSeparatorAlwaysShown(true)` | Ví dụ số nguyên có thể thành `100.` |
| Kích thước nhóm hàng | `setGroupingSize(int)` | Chi tiết riêng của DecimalFormat |
| Prefix/suffix | `setPositivePrefix(...)`, `setNegativeSuffix(...)` | Có thể thay đổi nội dung báo hiệu dấu âm |
| Chọn parse thành BigDecimal | `setParseBigDecimal(true)` | Có ích cho parsing thập phân với độ chính xác decimal |
| Hệ số nhân | `setMultiplier(int)` | Có thể làm thay đổi ý nghĩa số (như percent) |

Nếu chỉ cần ví dụ `setParseBigDecimal(true)`, đừng viết:

```java
// KHÔNG BIÊN DỊCH vì NumberFormat không khai báo setParseBigDecimal.
NumberFormat nf = NumberFormat.getNumberInstance(Locale.US);
nf.setParseBigDecimal(true);
```

Muốn dùng nó, phải có biến mà compiler biết là `DecimalFormat`, thông qua `instanceof` hoặc tạo `new DecimalFormat(...)`.

### Ví dụ có kiểm tra kiểu: cấu hình parse BigDecimal

```java
NumberFormat number = NumberFormat.getNumberInstance(Locale.US);
if (number instanceof DecimalFormat decimal) {
    decimal.setParseBigDecimal(true);
    // Từ đây dùng decimal.parse(...) theo chính sách kiểm tra input.
} else {
    // Subclass khác: không giả định nó có cùng cơ chế parse BigDecimal.
}
```

Đây là **fragment**, không phải chương trình đầy đủ. Khi triển khai thực tế, `DecimalFormat.parse(String)` có thể không tiêu thụ toàn bộ chuỗi đầu vào. Nếu cần validation, dùng `ParsePosition` và xác nhận `pos.getIndex() == input.length()` cùng `pos.getErrorIndex()` thích hợp, bên cạnh kiểm tra phạm vi và scale.

## 7. Trường hợp CompactNumberFormat: subclass có thật, không phải DecimalFormat

`CompactNumberFormat` được dùng trong các định dạng rút gọn theo locale. Nó là một **lớp con của `NumberFormat`**, không phải subclass của `DecimalFormat`. Factory `NumberFormat.getCompactNumberInstance(locale, style)` được thiết kế cho dạng compact.

Chương trình **`CompactTypeDemo.java`**:

```java
import java.text.CompactNumberFormat;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class CompactTypeDemo {
    public static void main(String[] args) {
        NumberFormat compact =
                NumberFormat.getCompactNumberInstance(
                        Locale.US, NumberFormat.Style.SHORT);

        if (compact instanceof DecimalFormat) {
            System.out.println("DecimalFormat implementation");
        } else if (compact instanceof CompactNumberFormat) {
            System.out.println("CompactNumberFormat implementation");
        } else {
            System.out.println("Another NumberFormat implementation");
        }

        System.out.println("Assignable to NumberFormat: "
                + (compact instanceof NumberFormat));
    }
}
```

```bash
javac -encoding UTF-8 CompactTypeDemo.java
java CompactTypeDemo
```

Trên JDK 17/21 dùng triển khai compact thông thường, dòng phân loại thường là `CompactNumberFormat implementation`, tiếp theo:

```text
Assignable to NumberFormat: true
```

Dòng đầu có thể khác nếu môi trường sử dụng triển khai khác, nên đoạn stdout ở trên chỉ trích **dòng thứ hai luôn đúng** chứ không phải stdout liên tiếp đầy đủ. Đây là minh họa vì sao **định dạng compact không nên bị ép sang `DecimalFormat`** để gọi `applyPattern`. Chọn API chuyên biệt của subtype thực tế (nếu cần và phù hợp), hoặc sử dụng các thao tác chung của `NumberFormat`.

Nếu một thư viện chỉ nhận `DecimalFormat`, đừng cố giả mạo compact formatter bằng cast. Hãy chuyển đổi giao diện của thư viện để nhận `NumberFormat`/`Format` nếu nghiệp vụ cho phép, hoặc cung cấp một `DecimalFormat` được cấu hình riêng và chấp nhận rằng nó **không tương đương** định dạng compact.

## 8. Khi thật sự cần DecimalFormat: tạo đối tượng tường minh

Nếu chức năng bắt buộc là pattern `"#,##0.00"` hoặc `setParseBigDecimal`, bạn có thể tạo đúng lớp yêu cầu:

```java
Locale locale = Locale.forLanguageTag("en-US");
DecimalFormat decimal = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(locale));
```

Đây là **fragment** cần `import java.text.DecimalFormat;`, `DecimalFormatSymbols;`, `java.util.Locale;`. Không có phép cast nào. Constructor hai tham số cho phép kiểm soát **pattern** và **ký hiệu theo locale**.

**Ví dụ chạy độc lập — `ExplicitDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class ExplicitDecimalDemo {
    public static void main(String[] args) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));

        format.setRoundingMode(RoundingMode.HALF_UP);
        format.setParseBigDecimal(true);

        System.out.println(format.format(
                new BigDecimal("12345.678")));
        System.out.println(format.format(
                new BigDecimal("12.5")));
        System.out.println("Parse as BigDecimal: "
                + format.isParseBigDecimal());
        System.out.println("Pattern: " + format.toPattern());
    }
}
```

```bash
javac -encoding UTF-8 ExplicitDecimalDemo.java
java ExplicitDecimalDemo
```

Stdout:

```text
12,345.68
12.50
Parse as BigDecimal: true
Pattern: #,##0.00
```

Kết quả này được kiểm soát bằng **pattern cụ thể**, `DecimalFormatSymbols` của `Locale.US` và `HALF_UP`. Dùng constructor tường minh là lựa chọn đúng khi bạn cần bảo đảm **subtype `DecimalFormat`**, nhưng không phải lúc nào nó cũng giữ được mọi quy tắc mà factory locale cung cấp.

### Đánh đổi với factory

| Tiêu chí | Factory `NumberFormat.getNumberInstance(locale)` | `new DecimalFormat(pattern, symbols)` |
| --- | --- | --- |
| Kiểu khai báo/trả về | `NumberFormat` | Chắc chắn là `DecimalFormat` |
| Tự chọn kiểu format phù hợp locale/provider | Có | Không — bạn chọn pattern/chữ số |
| Có thể cast sang DecimalFormat | Chỉ sau `instanceof` | Không cần cast |
| Hỗ trợ pattern DecimalFormat | Nếu subtype đúng | Có |
| Kiểm soát quy tắc ký hiệu | Theo locale/provider | Qua `DecimalFormatSymbols` |
| Mức độ thích hợp khi cần currency chuẩn theo locale | Thường nên lấy từ factory chuyên biệt | Cần tự cấu hình pattern/currency và xem xét quy tắc |

Nếu muốn một **định dạng số chung bản địa hóa trước**, sau đó chỉ chỉnh nhẹ, ưu tiên factory rồi kiểm tra subtype. Nếu muốn một **pattern bắt buộc** và không cần giữ chính xác mọi quyết định format của provider, tạo `DecimalFormat` trực tiếp với ký hiệu locale. Với giá trị tiền, cần thêm mã tiền tệ nghiệp vụ và chính sách làm tròn; đừng mặc định pattern `"#,##0.00"` biểu diễn tiền tệ đúng ở mọi nước.

## 9. Một mẫu thiết kế có fallback rõ ràng

Trong mã sản phẩm, nếu tùy chỉnh đặc thù là **tùy chọn**, có thể giữ formatter nhà cung cấp:

```java
// Fragment trong phương thức đã import NumberFormat, DecimalFormat, Locale.
NumberFormat format = NumberFormat.getNumberInstance(locale);
format.setMinimumFractionDigits(2);
format.setMaximumFractionDigits(2);

if (format instanceof DecimalFormat decimal) {
    decimal.setDecimalSeparatorAlwaysShown(true);
}
// Format tiếp bằng NumberFormat; không thay bằng object khác chỉ vì cast lỗi.
```

Nếu pattern là **bắt buộc về mặt hợp đồng hiển thị**, có hai lựa chọn có chủ đích:

1. **Cần giữ formatter factory:** yêu cầu subtype `DecimalFormat` và báo lỗi cấu hình có ý nghĩa nếu không đáp ứng; điều này phù hợp khi ứng dụng chỉ chấp nhận một tập runtime/provider được kiểm soát.
2. **Được phép tự quyết định pattern:** tạo `new DecimalFormat(pattern, DecimalFormatSymbols.getInstance(locale))`. Khi đó app không còn sử dụng đầy đủ các quy tắc định dạng mặc định do factory/provider chọn.

Ví dụ hàm xây dựng formatter chỉ khi bắt buộc subtype:

```java
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class FormatterFactoryGuard {
    public static DecimalFormat requireDecimal(Locale locale) {
        NumberFormat candidate =
                NumberFormat.getNumberInstance(locale);
        if (candidate instanceof DecimalFormat decimal) {
            return decimal;
        }
        throw new IllegalStateException(
                "DecimalFormat required, got "
                + candidate.getClass().getName());
    }

    public static void main(String[] args) {
        Locale locale = Locale.US;
        NumberFormat format =
                NumberFormat.getNumberInstance(locale);
        System.out.println("NumberFormat available: "
                + (format != null));
        // Khi ứng dụng bắt buộc phải có DecimalFormat:
        // DecimalFormat decimal = requireDecimal(locale);
    }
}
```

Lưu file **`FormatterFactoryGuard.java`** và chạy:

```bash
javac -encoding UTF-8 FormatterFactoryGuard.java
java FormatterFactoryGuard
```

Stdout của `main`:

```text
NumberFormat available: true
```

Hàm `requireDecimal` được biên dịch và có thể được gọi từ code khác; `main` chủ ý không gọi hàm yêu cầu subtype để có stdout ổn định trên các provider. Nếu gọi `requireDecimal` và provider không trả `DecimalFormat`, nó ném `IllegalStateException` **có nội dung chẩn đoán**, không để một `ClassCastException` khó hiểu xuất hiện từ cast mù. Ở nơi subtype là tùy chọn, **không cần ném lỗi**, chỉ dùng formatter gốc và chức năng chung.

## 10. Locale, pattern và bộ ký hiệu: không đánh đồng

`DecimalFormatSymbols.getInstance(locale)` cung cấp các ký hiệu như dấu thập phân, dấu grouping, chữ số, dấu âm theo locale. Với constructor `DecimalFormat("#,##0.00", symbols)`, pattern dùng **ký hiệu cú pháp chuẩn không localize**; ký tự thực tế xuất ra theo `symbols`.

Ví dụ `"#,##0.00"` khi dùng ký hiệu en-US thường ra `1,234.50`; với de-DE có thể ra `1.234,50`. Đừng viết pattern `"#.##0,00"` cho de-DE vào `applyPattern(...)` rồi nghĩ Java sẽ tự hiểu đó là cú pháp locale Đức: `applyPattern` nhận pattern theo **quy ước chuẩn**. Nếu thực sự xử lý **localized pattern**, dùng `applyLocalizedPattern(...)` và kiểm soát `DecimalFormatSymbols` tương ứng.

**Đặc biệt với currency:** `getCurrencyInstance(locale)` không chỉ thay một dấu `$`, mà còn có thể chọn pattern, grouping, ký hiệu âm và quy ước tiền tệ. Một `new DecimalFormat("#,##0.00", symbols)` không đương nhiên giữ được lựa chọn tiền tệ của factory. Khi cần cách in tiền, ưu tiên nhận formatter currency từ factory, sử dụng API chung khi đủ và chỉ tùy chỉnh `DecimalFormat` sau `instanceof`.

**Đặc biệt với BigDecimal:** `DecimalFormat` có hỗ trợ định dạng và parse decimal theo khả năng riêng của nó. `NumberFormat` có hợp đồng chung nhưng các subclass có thể xử lý `Number` khác nhau; không giả định mọi subclass tự bảo toàn precision của `BigDecimal` khi gọi `format(Object)`. Việc tiền được tính chính xác nên nằm ở tầng nghiệp vụ `BigDecimal`, formatter chỉ chịu trách nhiệm biểu diễn.

## 11. Phân tích số không phải lúc nào cũng là phân tích BigDecimal

`NumberFormat.parse(String)` trả `Number`, không bảo đảm kiểu cụ thể như `BigDecimal`. Ngay cả khi đối tượng thật là `DecimalFormat`, nếu chưa gọi `setParseBigDecimal(true)`, giá trị parse có thể là `Long` hoặc `Double` tùy nội dung và cấu hình.

**Ví dụ chạy độc lập — `ParseBigDecimalDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class ParseBigDecimalDemo {
    public static void main(String[] args) {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(Locale.US));
        parser.setParseBigDecimal(true);

        String input = "1,234.50";
        ParsePosition position = new ParsePosition(0);
        Number result = parser.parse(input, position);

        if (result instanceof BigDecimal amount
                && position.getIndex() == input.length()) {
            System.out.println("Parsed: "
                    + amount.toPlainString());
            System.out.println("Type: BigDecimal");
        } else {
            System.out.println("Invalid or incomplete number");
        }
    }
}
```

```bash
javac -encoding UTF-8 ParseBigDecimalDemo.java
java ParseBigDecimalDemo
```

Stdout:

```text
Parsed: 1234.50
Type: BigDecimal
```

Ví dụ sử dụng `ParsePosition` để từ chối các ký tự thừa sau số; tùy chính sách input, có thể cần kiểm tra thêm dấu phân cách, cách viết nhóm hàng, ký tự whitespace, số âm, giá trị trong phạm vi, scale và ký tự Unicode. `setParseBigDecimal` chỉ điều khiển **kiểu giá trị parse** của `DecimalFormat`, không thay thế validation.

Nếu chỉ có một `NumberFormat` không phải `DecimalFormat`, đừng ép nó thành `DecimalFormat` chỉ để lấy `BigDecimal`. Hoặc bạn áp dụng một parser được lựa chọn rõ ràng, hoặc bạn dùng API `parse` chung và kiểm soát chuyển đổi theo chính sách độ chính xác, thay vì gọi `new BigDecimal(parsed.doubleValue())` một cách tùy tiện.

## 12. Điều gì xảy ra khi dùng clone và truyền qua nhiều lớp?

Ví dụ một service nhận tham số kiểu `NumberFormat`, trong khi caller tạo `DecimalFormat`. Việc truyền vào một phương thức khai báo tham số `NumberFormat` **không làm mất kiểu thật** của object; bạn vẫn có thể dùng `instanceof` ở phía nhận.

```java
// Fragment trong lớp Java (không phải file độc lập):
static void render(NumberFormat format) {
    if (format instanceof DecimalFormat decimal) {
        decimal.setGroupingSize(3);
    }
    System.out.println(format.format(1234));
}
```

Tuy nhiên, làm thay đổi formatter **của caller** trong phương thức `render` có thể gây tác dụng phụ, nhất là khi formatter được dùng lại. `NumberFormat`/`DecimalFormat` là các đối tượng **mutable** và không được bảo đảm thread-safe nếu chia sẻ giữa những request khác nhau. Để tránh điều đó, cân nhắc truyền cấu hình bất biến, tạo formatter mới cho mỗi thao tác hoặc clone/copy có kiểm soát trước khi sửa.

Việc `clone()` của một formatter thường bảo toàn kiểu runtime là đặc điểm của một đối tượng được clone, **không chứng minh** đối tượng ban đầu là `DecimalFormat`. Không dùng cast trên bản clone nếu chưa biết subtype thật, và không chia sẻ các formatter mutable giữa nhiều thread mà không có cơ chế đồng bộ thích hợp.

Nếu cần kiến trúc dài hạn, hãy để tầng UI làm việc với một interface hẹp như `Function<Number, String>` hoặc `NumberFormat` nếu đủ, thay vì mọi service phải nhận `DecimalFormat`. Chỉ nơi thực sự cần `applyPattern` mới phụ thuộc lớp cụ thể và xử lý nhánh không hỗ trợ một cách rõ ràng.

## 13. Các lựa chọn thiết kế theo tình huống

| Tình huống | Cách nên làm | Lý do |
| --- | --- | --- |
| Hiển thị số theo locale, tối đa hai chữ số lẻ | Dùng `NumberFormat.getNumberInstance(locale)`, setter chung | Không cần subtype |
| Muốn dấu thập phân luôn xuất hiện với số nguyên | `instanceof DecimalFormat` rồi `setDecimalSeparatorAlwaysShown(true)`, có fallback | Tính năng riêng DecimalFormat |
| Bắt buộc một pattern chuẩn xác để xuất báo cáo | `new DecimalFormat(pattern, DecimalFormatSymbols.getInstance(locale))` | Bảo đảm object và pattern |
| Định dạng số rút gọn (`1K`, `2M`...) | `getCompactNumberInstance(...)` | Không tương đương DecimalFormat thường |
| Parser phải tạo `BigDecimal` | Chọn `DecimalFormat` có `setParseBigDecimal(true)`, kiểm tra toàn input | Tránh giả định kiểu Number trả về |
| Nhận formatter từ thư viện/provider không kiểm soát | Dùng `instanceof`, không cast mù | Thay đổi implementation không làm crash ngẫu nhiên |
| Formatter currency nghiệp vụ | Factory currency + kiểm soát mã tiền và rounding riêng | Không thay tiền tệ bằng một pattern đơn giản |
| Xử lý server nhiều luồng | Formatter riêng cho lần render/request hoặc đồng bộ | Formatter mutable, không bảo đảm thread-safe |
| API của bạn chỉ cần `format` | Nhận `NumberFormat`/`Format` thay vì `DecimalFormat` | Giảm coupling |

### Câu hỏi phân loại nhanh

Trước khi cast, nên tự hỏi:

1. **Tôi có thật sự cần một phương thức chỉ có ở `DecimalFormat` không?** Nếu không, cứ dùng `NumberFormat`.
2. **Tôi có biết object được tạo từ đâu không?** Nếu từ factory/provider, kiểm tra subtype; nếu do chính code gọi `new DecimalFormat`, biết rõ kiểu ngay từ đầu.
3. **Nếu không phải `DecimalFormat`, ứng dụng phải làm gì?** Bỏ qua tùy chỉnh, dùng fallback chung, tự tạo `DecimalFormat` khác hay báo lỗi cấu hình? Hãy quyết định trước.
4. **Tính năng này có phụ thuộc locale/currency/provider không?** Tạo một formatter mới bằng pattern có thể thay đổi quy ước mà factory đã chọn.
5. **Có bị chia sẻ qua thread/request không?** Dù cast thành công, việc mutating object vẫn có thể sai về concurrency.

## 14. Bài tập thực hành

**Bài 1 — Dự đoán ClassCastException.** Với `NumberFormat first = new DecimalFormat("0.00");` và `NumberFormat second = new ChoiceFormat(new double[]{0,1}, new String[]{"zero","one+"});`, dự đoán `instanceof DecimalFormat` cho mỗi biến. Thử downcast cả hai; giải thích vì sao chỉ một trường hợp hợp lệ.

**Bài 2 — Kiểm tra factory.** Chạy `SafeFactoryDemo` với `Locale.US` rồi thay bằng `Locale.GERMANY`. In thêm `formatter.getClass().getName()` để quan sát runtime class; dùng `instanceof` thay vì dựa vào tên class. Nếu có provider khác, nhánh nào chạy? Chương trình có tiếp tục định dạng được không?

**Bài 3 — Compact format.** Tạo `NumberFormat.getCompactNumberInstance(Locale.US, NumberFormat.Style.SHORT)`. Kiểm tra `instanceof DecimalFormat` và `instanceof CompactNumberFormat`; không cast xuống `DecimalFormat` nếu điều kiện không đúng. So sánh ý nghĩa của định dạng compact với pattern `"#,##0.00"`.

**Bài 4 — Pattern bắt buộc.** Xây hàm tạo `DecimalFormat("#,##0.000", DecimalFormatSymbols.getInstance(Locale.US))`, đặt `RoundingMode.HALF_UP`. Định dạng `new BigDecimal("12.3456")`, giải thích vì sao output có ba chữ số lẻ và vì sao số `BigDecimal` nguồn không thay đổi.

**Bài 5 — Parser chính xác.** Lấy ví dụ `ParseBigDecimalDemo` rồi đưa input `"1,234.50xyz"`. Xác nhận phần còn lại không được tiêu thụ nên validation từ chối. Sau đó thử `"1,234.50"` và ghi nhận kiểu `BigDecimal`; giải thích vì sao một lệnh cast ngẫu nhiên từ `NumberFormat` không giải quyết được kiểm tra input.

## 15. Lỗi phổ biến

| Lỗi | Vì sao sai | Hướng sửa |
| --- | --- | --- |
| `DecimalFormat d = NumberFormat.getInstance(locale)` | Incompatible types ở compile time | Giữ `NumberFormat` hoặc kiểm tra và cast |
| `(DecimalFormat) NumberFormat.getCompactNumberInstance(...)` | Compact formatter chuẩn thuộc subtype khác | Dùng NumberFormat/CompactNumberFormat phù hợp |
| Cast factory không kiểm tra | Phụ thuộc provider/JDK và có thể ném `ClassCastException` | `instanceof DecimalFormat` |
| So `getClass() == DecimalFormat.class` | Bỏ qua subclass hợp lệ của DecimalFormat | `instanceof` |
| Nghĩ cast chuyển đổi formatter | Cast không đổi kiểu runtime hay cách định dạng | Tạo formatter mới nếu cần hành vi khác |
| Cast chỉ để chỉnh số chữ số thập phân | Các setter đã nằm trên NumberFormat | Dùng interface chung |
| Tin `setRoundingMode` luôn hoạt động ở mọi NumberFormat | Base implementation có thể ném `UnsupportedOperationException` | Kiểm tra hỗ trợ của implementation |
| Dùng `new DecimalFormat(pattern)` và nghĩ đã theo locale của user | Constructor một tham số dùng default FORMAT locale cho symbols | Truyền `DecimalFormatSymbols.getInstance(locale)` |
| Dùng `applyPattern` với ký hiệu pattern đã localize | API này dùng pattern syntax chuẩn | Dùng `applyLocalizedPattern` khi phù hợp |
| Dùng constructor thường thay formatter currency mà không xét quy tắc | Có thể làm mất pattern/currency conventions của provider | Chọn factory currency hoặc cấu hình đầy đủ |
| `parse` rồi cast mặc định thành `BigDecimal` | `NumberFormat.parse` trả `Number` đa kiểu | Kiểm tra subtype parser + `setParseBigDecimal` |
| Dùng formatter chung mutable trên nhiều request | Race condition, cấu hình rò giữa user | Tạo formatter theo request hoặc đồng bộ |
| Chỉ kiểm thử trên máy dev | Provider/JDK khác có thể chọn subclass khác | Kiểm thử fallback branch và các runtime hỗ trợ |

## 16. Tài liệu chính thức

- [Java SE 21 — NumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/NumberFormat.html): factory methods, superclass API, giới hạn subtype và các phương thức có thể không được hỗ trợ.
- [Java SE 21 — DecimalFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/DecimalFormat.html): `instanceof`, constructor, pattern, `DecimalFormatSymbols`, parsing `BigDecimal`.
- [Java SE 21 — CompactNumberFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/CompactNumberFormat.html): subtype riêng của `NumberFormat` và định dạng rút gọn.
- [Java SE 21 — NumberFormatProvider](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/spi/NumberFormatProvider.html): khả năng cung cấp các định dạng số cho locale từ nhà cung cấp.

## 17. Ghi nhớ

**`NumberFormat` không đồng nghĩa `DecimalFormat`.** Factory khai báo trả `NumberFormat` và có thể cung cấp lớp con khác tùy loại định dạng, locale hay provider. **Chỉ downcast sau khi kiểm tra `instanceof`**, hoặc tạo hẳn một `DecimalFormat` nếu sản phẩm thật sự cần pattern/tính năng của lớp đó. Những thiết lập như số chữ số thập phân hay grouping đã có ở `NumberFormat` thì không cần cast.

Một phép ép kiểu thành công không phải phép chuyển đổi và cũng không bảo đảm mọi quy tắc về locale, currency, precision hay thread-safety. Hãy chọn abstraction **hẹp nhất đáp ứng nhu cầu**, có nhánh xử lý khi subtype không được hỗ trợ, và dùng formatter tường minh khi muốn kiểm soát pattern.