# DecimalFormat: Mẫu số dương, số âm, phần tiền tố và hậu tố trong Java

## 1. Mục tiêu và bối cảnh

`java.text.DecimalFormat` là lớp định dạng/đọc số có thể tùy biến bằng **pattern** và ký hiệu theo `Locale`. Khi ứng dụng muốn hiển thị số âm trong ngoặc kế toán, thêm từ chỉ đơn vị vào sau số, hoặc đặt nhãn khác nhau trước giá trị dương và âm, người học cần nắm **hai phần mẫu số dương/số âm** và **prefix/suffix**.

Ví dụ cùng một độ lớn 1.234,5 có thể được biểu diễn theo quy ước:

- Số dương: `1,234.50`
- Số âm: `-1,234.50`
- Số âm theo kiểu kế toán: `(1,234.50)`
- Có nhãn: `Amount: 1,234.5 units` hoặc `Loss: 1,234.5 units`

Trong các ví dụ trên, dấu phẩy, dấu chấm và ký hiệu nhóm phụ thuộc bộ ký hiệu đã chọn; văn bản `Amount`, `Loss` và `units` là **phần tiền tố/hậu tố do ứng dụng quy định**, không phải giá trị bản thân của số.

Sau bài học, bạn có thể:

1. Đọc và viết cú pháp `positiveSubpattern;negativeSubpattern`.
2. Hiểu sự khác biệt giữa các ký hiệu cú pháp `0`, `#`, `,`, `.`, `;`, `'` và các literal của prefix/suffix.
3. Dùng mẫu âm để hiển thị dấu trừ hoặc dấu ngoặc, hiểu hành vi khi không khai báo mẫu âm.
4. Phân biệt **mẫu chữ số** với **prefix/suffix**, tránh lỗi khi cấu hình số dương và âm theo độ chính xác khác nhau.
5. Sử dụng `DecimalFormatSymbols`/`Locale`, định dạng currency/percent và API setter một cách có kiểm soát.
6. Xử lý các trường hợp 0, âm 0, làm tròn, parse, chia sẻ formatter giữa thread và kiểm thử.

## 2. Cấu trúc tổng quát của pattern

Một pattern `DecimalFormat` thông thường có cấu trúc:

```text
positiveSubpattern[;negativeSubpattern]
```

Mỗi subpattern có thể chứa ba vùng:

```text
[prefix] number-pattern [suffix]
```

Ví dụ:

```text
#,##0.00;(#,##0.00)
│           │
│           └── âm: prefix "("; phần số "#,##0.00"; suffix ")"
└────────────── dương: prefix/suffix rỗng; phần số "#,##0.00"
```

Với ký hiệu theo `Locale.US`:

| Giá trị | Pattern | Hiển thị |
| ---: | --- | --- |
| `1234.5` | `#,##0.00` | `1,234.50` |
| `-1234.5` | `#,##0.00` | `-1,234.50` |
| `1234.5` | `#,##0.00;(#,##0.00)` | `1,234.50` |
| `-1234.5` | `#,##0.00;(#,##0.00)` | `(1,234.50)` |
| `0` | `#,##0.00;(#,##0.00)` | `0.00` |

**Chỉ có một subpattern?** Nếu không khai báo mẫu âm, formatter sẽ suy ra kiểu âm từ mẫu dương, thường thêm dấu trừ theo `DecimalFormatSymbols` vào trước prefix của nhánh dương. Không cần viết thủ công nhánh âm chỉ để được dấu trừ thông thường.

**Có hai subpattern?** Dấu chấm phẩy `;` phân tách mẫu dương và âm; ký tự này không được in ra kết quả. Nếu muốn dấu `;` là văn bản hiển thị trong prefix/suffix, phải quote như literal.

### Điều thường bị hiểu sai: mẫu chữ số trong nhánh âm

Trong `DecimalFormat`, các quy tắc **số chữ số, dấu nhóm, độ chính xác** được lấy từ **nhánh dương**. Phần số trong negative subpattern được dùng để xác định cấu trúc, nhưng **không thể dùng nhánh âm để có một số chữ số thập phân khác nhánh dương**. Nhánh âm chủ yếu quyết định prefix/suffix của giá trị âm.

Ví dụ:

```java
DecimalFormat df = new DecimalFormat(
        "0.00;(0)",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(df.format(-12.3)); // (12.30)
```

Dù phần số trong nhánh âm viết `0`, kết quả vẫn có hai chữ số thập phân theo phần dương `0.00`. Nếu sản phẩm thật sự cần số âm và dương có quy tắc chữ số khác nhau, hãy chọn **hai formatter** hoặc cấu hình riêng trong code dựa trên nghiệp vụ, không kỳ vọng hai subpattern giải quyết vấn đề đó.

## 3. Các ký hiệu quan trọng trong phần số

| Ký hiệu | Vai trò trong pattern | Cần nhớ |
| --- | --- | --- |
| `0` | Chữ số bắt buộc; thiếu thì điền `0`. | `0.00` luôn thể hiện hai chữ số phần thập phân. |
| `#` | Chữ số tùy chọn; không thêm số 0 không cần thiết. | `#,##0` vẫn có ít nhất một chữ số nguyên vì có `0`. |
| `.` | Ký hiệu phân cách phần nguyên/thập phân **trong pattern không localized**. | Dấu hiển thị tùy `DecimalFormatSymbols`. |
| `,` | Ký hiệu grouping trong pattern. | Vị trí và ký hiệu hiển thị do pattern + locale. |
| `;` | Tách positive/negative subpattern. | Không phải dấu ngăn cách dữ liệu thực. |
| `'... '` | Quote literal trong pattern. | Cho phép đưa ký hiệu đặc biệt thành chữ hiển thị. |
| `%` | Biểu thị percent và áp hệ số nhân 100. | Không phải chỉ đơn thuần chữ “%”. |
| `‰` | Biểu thị per-mille và áp hệ số nhân 1000. | Không tương đương percent. |
| `¤` | Placeholder cho ký hiệu tiền tệ; `¤¤` thường đại diện mã ISO currency. | Currency thực phải lấy từ dữ liệu giao dịch. |
| `E` | Ký hiệu dạng số mũ khi dùng theo cú pháp khoa học. | Không phải literal khi đứng trong khuôn số. |

Các ký hiệu trên là **cú pháp pattern chuẩn**, thường dùng với `applyPattern(...)` hoặc constructor `DecimalFormat(pattern, symbols)`. Cách hiển thị dấu phân cách, dấu âm, ký hiệu % và tiền tệ có thể khác giữa các locale.

Chẳng hạn, pattern `#,##0.00` theo ký hiệu Hoa Kỳ có thể in `1,234.50`, trong khi theo một locale khác dấu thập phân và dấu nhóm có thể đảo vị trí. Không được suy luận từ dấu `.` và `,` trong pattern rằng dữ liệu đầu ra bắt buộc sử dụng đúng các ký tự ấy.

## 4. Mẫu số dương và số âm

### 4.1. Định dạng âm mặc định

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(df.format(-1234.5)); // -1,234.50
```

Vì không cung cấp nhánh âm, `DecimalFormat` dùng số theo nhánh dương và thêm dấu âm mặc định của bộ ký hiệu. Đây là lựa chọn thường đủ cho số lượng, giá trị thông thường hoặc nhãn kỹ thuật.

### 4.2. Âm bằng ngoặc theo quy ước kế toán

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00;(#,##0.00)",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(df.format(1234.5));  // 1,234.50
System.out.println(df.format(-1234.5)); // (1,234.50)
```

Các dấu `(` và `)` là prefix/suffix của nhánh âm. Không có dấu trừ `-` trong kết quả vì ta chủ động thay cách hiển thị dấu âm.

Đây chỉ là **quy ước trình bày**. Độ lớn của số không thay đổi: `df.format(-1234.5)` vẫn định dạng một giá trị âm; chỉ chuỗi được hiển thị khác.

### 4.3. Prefix/suffix riêng cho từng dấu

Có thể đặt văn bản trước và sau vùng số:

```text
'Amount: '#,##0.0' units';'Loss: '#,##0.0' units'
```

Theo `Locale.US`:

- `1234.5` → `Amount: 1,234.5 units`
- `-1234.5` → `Loss: 1,234.5 units`

Tại đây, `Amount: ` và `Loss: ` là prefix; ` units` là suffix. Dùng literal được quote để parser phân biệt văn bản với ký hiệu đặc biệt trong pattern.

Đừng dùng kiểu ghép `"Loss: " + format.format(-number)` để biểu diễn mọi dạng âm: ứng dụng có thể cần âm bằng ngoặc, đổi trật tự chữ, hoặc một ngôn ngữ sử dụng cách diễn đạt khác. Tuy nhiên, **DecimalFormat không phải hệ thống dịch cả câu**; với văn bản giàu ngữ pháp, hãy dùng `ResourceBundle`/`MessageFormat` cho thông điệp, còn `DecimalFormat` chỉ định dạng con số.

## 5. Cách đọc và thay đổi prefix/suffix qua API

`DecimalFormat` cung cấp các getter/setter tương ứng:

| Getter | Setter | Chức năng |
| --- | --- | --- |
| `getPositivePrefix()` | `setPositivePrefix(String)` | Chuỗi trước số dương. |
| `getPositiveSuffix()` | `setPositiveSuffix(String)` | Chuỗi sau số dương. |
| `getNegativePrefix()` | `setNegativePrefix(String)` | Chuỗi trước số âm. |
| `getNegativeSuffix()` | `setNegativeSuffix(String)` | Chuỗi sau số âm. |

Ví dụ minh họa:

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00",
        DecimalFormatSymbols.getInstance(Locale.US));
df.setPositivePrefix("+");
df.setPositiveSuffix(" units");
df.setNegativePrefix("(");
df.setNegativeSuffix(" units)");

System.out.println(df.format(8));  // +8.00 units
System.out.println(df.format(-8)); // (8.00 units)
```

Đoạn mã này đặt trong phương thức Java với import phù hợp; nó thể hiện việc thay đổi **chuỗi affix**, không thay đổi bản thân số. Các setter dùng literal string, không yêu cầu người gọi tự bọc chuỗi bằng dấu quote trong Java như pattern.

**Đổi pattern sau setter:** `applyPattern(...)` phân tích lại pattern và có thể thay thế prefix/suffix trước đó. Hãy xác định rõ thứ tự cấu hình; nếu dùng pattern làm nguồn chuẩn, áp dụng pattern trước rồi mới ghi đè affix cần thiết.

**Lưu pattern lại:** `toPattern()` là dạng biểu diễn pattern; nếu đã tùy biến các ký hiệu/affix bằng setter, không nên lấy chuỗi từ `toPattern()` rồi suy đoán toàn bộ semantics của các thao tác tùy biến. Kiểm thử formatter theo các giá trị thực quan trọng.

**Điểm cần chú ý về tính phân biệt:** positive và negative subpattern không nên có prefix/suffix giống hệt khiến bộ parse không thể phân biệt dấu. Khi cần đọc số từ chuỗi, phải thiết kế cú pháp không mơ hồ và kiểm thử việc parse âm/dương.

## 6. Literal, dấu nháy đơn và các ký tự đặc biệt

Trong cú pháp `DecimalFormat`, **quote bằng dấu nháy đơn** cho phép đưa ký hiệu vốn có ý nghĩa đặc biệt thành phần chữ hiển thị. Ví dụ:

```text
'Total: '#,##0.00' USD'
```

Nó thể hiện một số có prefix `Total: ` và suffix ` USD`, không nhân hay đổi giá trị số. Nếu cần hiển thị **dấu nháy đơn** trong literal, viết hai nháy đơn `''` theo quy tắc quoting của `DecimalFormat`.

Các ký hiệu như `%` và `¤` cần được phân biệt cẩn thận:

- **Không quote `%` trong pattern** → nó là percent formatting, nhân giá trị số với 100 trước khi hiển thị.
- **Quote `'%'`** → thể hiện ký tự percent như một chữ literal; nó **không nhân 100**. Việc dùng đúng cái nào phụ thuộc đơn vị của giá trị nguồn.
- **Dùng `¤`** → placeholder tiền tệ do `DecimalFormatSymbols` và `Currency` quyết định.
- **Dùng `'USD '` hoặc `' VND'`** → chữ literal cố định; nó không tự đảm bảo đơn vị tiền tệ của dữ liệu.

Nếu một thông điệp người dùng cần diễn giải như “Số dư âm”, “Khoản hoàn”, “Khoản ghi có”, hãy để lớp localization quyết định câu văn phù hợp. Prefix/suffix nên phục vụ các trường hợp gắn chặt với cách **biểu diễn số**, tránh nhồi cả câu hoặc cấu trúc ngữ pháp vào pattern số.

### Dấu chấm phẩy literal

Dấu `;` không quote có vai trò tách hai subpattern; nếu muốn prefix hiển thị chứa `;`, dùng cú pháp quote để parser hiểu đó là ký tự văn bản, thay vì mở nhánh âm không chủ ý.

### Dấu âm theo Locale

Ký hiệu dấu trừ trong chuỗi có thể do `DecimalFormatSymbols.getMinusSign()` cung cấp. Đừng mặc định mọi locale dùng đúng ASCII `-`, cũng đừng tự thay ký tự trên chuỗi kết quả sau khi format. Nếu sản phẩm cần dấu âm đặc biệt, hãy cấu hình symbols hoặc prefix/negative pattern một cách chủ đích và test.

## 7. Percent, per-mille và currency trong prefix/suffix

### 7.1. Percent và hệ số nhân

`DecimalFormat` hiểu `%` trong pattern là ký hiệu đặc biệt: nó đặt percent sign vào affix **và nhân giá trị với 100**.

```java
DecimalFormat ratio = new DecimalFormat(
        "0.0%;(0.0%)",
        DecimalFormatSymbols.getInstance(Locale.US));

System.out.println(ratio.format(0.125));  // 12.5%
System.out.println(ratio.format(-0.125)); // (12.5%)
```

Nếu dữ liệu nghiệp vụ đã lưu giá trị `12.5` với nghĩa “12,5 phần trăm”, dùng pattern percent mà không chuyển đơn vị sẽ thành `1,250.0%`. Hãy thống nhất đầu vào là fraction (0.125) hay phần trăm đã nhân 100 (12.5).

Tương tự, ký hiệu per-mille `‰` áp hệ số nhân 1000. Khi chỉ muốn thêm một ký hiệu literal không quy đổi số, cần quote đúng cách.

### 7.2. Currency chỉ là định dạng

Pattern:

```text
¤#,##0.00;(¤#,##0.00)
```

có thể hiển thị một khoản tiền dương/âm, với nhánh âm dùng ngoặc. Ký hiệu `¤` được thay thành ký hiệu tiền tệ theo cấu hình; `¤¤` có thể thể hiện mã ISO 4217 như `USD`. Một số locale và bản JDK có dữ liệu/ký hiệu currency khác nhau.

Khi tiền tệ của giao dịch khác currency thông thường của locale, hãy thiết lập currency **theo dữ liệu nghiệp vụ**:

```java
Locale locale = Locale.US;
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);
DecimalFormat money = new DecimalFormat(
        "¤#,##0.00;(¤#,##0.00)", symbols);
money.setCurrency(Currency.getInstance("EUR"));
```

Đoạn này nằm trong phương thức Java, cần import `java.text.DecimalFormat`, `java.text.DecimalFormatSymbols`, `java.util.Locale` và `java.util.Currency`. Hãy kiểm tra ký hiệu tiền tệ thực được hiển thị nếu ứng dụng phụ thuộc vào một nhãn cụ thể.

**`setCurrency(...)` không chuyển đổi tỷ giá.** Nó thay thông tin dùng để định dạng đơn vị tiền, không nhân/chia số tiền để đổi EUR sang USD hoặc ngược lại. Phép chuyển đổi phải nằm trong tầng nghiệp vụ và có tỷ giá được xác định rõ.

### 7.3. Khi nào dùng literal “USD” thay vì currency placeholder?

Nếu pattern có `' USD'` thì đây chỉ là chuỗi văn bản luôn hiện ra. Nó có thể phù hợp với báo cáo cố định USD nhưng sẽ sai nếu tái sử dụng với giao dịch bằng EUR. Với phần mềm thanh toán nhiều currency, nên truyền currency động qua dữ liệu, không lưu toàn bộ thông tin đơn vị vào literal của pattern.

## 8. Ví dụ hoàn chỉnh Java 17+: định dạng dương, âm, affix và hậu tố

Tạo tệp **`DecimalFormatAffixDemo.java`** với nội dung sau. Các ví dụ sử dụng ký hiệu của `Locale.US` để kết quả số có thể dự đoán, không thay đổi mặc định toàn JVM.

```java
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

public class DecimalFormatAffixDemo {
    public static void main(String[] args) {
        DecimalFormatSymbols symbols =
                DecimalFormatSymbols.getInstance(Locale.US);

        DecimalFormat accounting = new DecimalFormat(
                "#,##0.00;(#,##0.00)", symbols);

        System.out.println("positive="
                + accounting.format(1234.5));
        System.out.println("negative="
                + accounting.format(-1234.5));
        System.out.println("zero="
                + accounting.format(0));
        System.out.println("negativeZero="
                + accounting.format(-0.0));
        System.out.println("negativePrefix="
                + accounting.getNegativePrefix());
        System.out.println("negativeSuffix="
                + accounting.getNegativeSuffix());

        DecimalFormat ordinary = new DecimalFormat(
                "#,##0.00", symbols);
        System.out.println("autoNegative="
                + ordinary.format(-1234.5));

        DecimalFormat labeled = new DecimalFormat(
                "'Amount: '#,##0.0' units';"
                + "'Loss: '#,##0.0' units'",
                symbols);
        System.out.println("labelPositive="
                + labeled.format(1234.5));
        System.out.println("labelNegative="
                + labeled.format(-1234.5));

        DecimalFormat ratio = new DecimalFormat(
                "0.0%;(0.0%)", symbols);
        System.out.println("percentPositive="
                + ratio.format(0.125));
        System.out.println("percentNegative="
                + ratio.format(-0.125));

        // Phần số của nhánh âm không đổi precision của
        // nhánh dương "0.00".
        DecimalFormat sameDigits = new DecimalFormat(
                "0.00;(0)", symbols);
        System.out.println("negativeDigits="
                + sameDigits.format(-12.3));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 DecimalFormatAffixDemo.java
java DecimalFormatAffixDemo
```

**Stdout chính xác:**

```text
positive=1,234.50
negative=(1,234.50)
zero=0.00
negativeZero=(0.00)
negativePrefix=(
negativeSuffix=)
autoNegative=-1,234.50
labelPositive=Amount: 1,234.5 units
labelNegative=Loss: 1,234.5 units
percentPositive=12.5%
percentNegative=(12.5%)
negativeDigits=(12.30)
```

### Đọc kết quả từng bước

1. `positive` và `negative` được định dạng cùng hai chữ số thập phân, cùng grouping. Nhánh âm dùng `(` và `)` thay dấu trừ.
2. `zero` sử dụng quy tắc nhánh dương: `0.00`. `DecimalFormat` không có “zero subpattern” thứ ba trong cú pháp positive/negative thông thường.
3. `negativeZero` cho `(0.00)` vì số `double` có thể mang dấu âm dù trị tuyệt đối bằng 0. Đây là **negative zero**; xem thêm mục 9.
4. `getNegativePrefix()` và `getNegativeSuffix()` phản ánh affix thực đã được phân tích từ pattern.
5. `ordinary` không khai báo nhánh âm, nên cho `autoNegative=-1,234.50`.
6. `labeled` sử dụng nhãn prefix `Amount: ` / `Loss: ` và suffix ` units` cho hai dấu.
7. `ratio` nhân giá trị với 100 và thêm percent sign; phần âm lại dùng ngoặc.
8. `negativeDigits=(12.30)` chứng tỏ quy tắc chữ số được lấy từ nhánh dương `0.00`, dù nhánh âm chứa `0`.

Các giá trị dùng để kiểm chứng là ví dụ biểu diễn số; không xem các chữ “Amount”/“Loss” là bản dịch tự động của mọi locale.

## 9. Số 0, âm 0, làm tròn và các giá trị đặc biệt

### 9.1. Số 0 thông thường

Pattern `#,##0.00;(#,##0.00)` không định nghĩa một nhánh cho số 0 riêng biệt. Với số 0 không âm, formatter dùng positive subpattern và in `0.00`. Nếu ứng dụng muốn hiển thị số 0 bằng dấu gạch ngang hay chữ “Không”, cần một chính sách riêng ở tầng trình bày hoặc nghiệp vụ; đừng đoán rằng thứ ba `;zeroPattern` là cú pháp của `DecimalFormat`.

### 9.2. Âm 0

`double` và `float` theo IEEE 754 có thể mang `-0.0` khác với `+0.0` về dấu. `DecimalFormat` có thể giữ dấu khi format, nên nhánh âm có thể được chọn cho `-0.0`, khiến ứng dụng in `(0.00)`.

Nếu quy định nghiệp vụ yêu cầu cả `-0.0` và `0.0` xuất ra `0.00`, hãy chuẩn hóa đầu vào **theo hợp đồng nghiệp vụ** trước khi format; lưu ý việc chuẩn hóa có thể làm mất thông tin dấu mà những ứng dụng tính toán khoa học cần giữ.

Tương tự, một giá trị âm rất nhỏ có thể bị làm tròn thành dạng số 0 nhưng vẫn mang dấu âm trong chuỗi hiển thị. Cần kiểm thử các ngưỡng làm tròn nếu số âm bằng ngoặc có ý nghĩa kế toán.

### 9.3. RoundingMode và số thập phân

`DecimalFormat` có thể làm tròn khi số chữ số hiển thị ít hơn số chữ số của nguồn. Việc hiển thị `1.234` thành `1.23` không có nghĩa số gốc đã bị thay đổi. Nếu kết quả là tiền tệ hoặc số liệu chính xác cao, nên dùng `BigDecimal` cho đầu vào cùng `RoundingMode` phù hợp hợp đồng, ví dụ:

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00;(#,##0.00)",
        DecimalFormatSymbols.getInstance(Locale.US));
df.setRoundingMode(RoundingMode.HALF_UP);
String view = df.format(new BigDecimal("-12.345"));
```

Đoạn nằm trong phương thức Java với import `java.math.BigDecimal`, `java.math.RoundingMode`. `setRoundingMode(...)` chỉ điều khiển **quy tắc làm tròn trong formatter**; không tự tạo quy tắc tài chính hợp lệ cho mọi tiền tệ và tình huống.

### 9.4. Infinity và NaN

Các giá trị `Double.NaN` hoặc vô cực có cách hiển thị đặc biệt theo `DecimalFormatSymbols`. Không nên kỳ vọng chúng được xử lý như những số thập phân hữu hạn thông thường, hay luôn tuân đúng mọi quy tắc precision và grouping. Đầu vào phục vụ giao dịch, bảng lương hoặc hóa đơn nên được xác thực và có chính sách rõ ràng đối với số không hữu hạn.

## 10. Parse số đã định dạng: các lưu ý quan trọng

`DecimalFormat` cũng có khả năng phân tích chuỗi thông qua `parse(...)`. Ví dụ formatter kế toán `#,##0.00;(#,##0.00)` có thể nhận diện giá trị âm từ dấu ngoặc nếu pattern và symbols tương thích.

Tuy nhiên, format và parse không phải lúc nào cũng đối xứng tuyệt đối cho mọi trường hợp:

- **Phần thập phân đã bị làm tròn** trong chuỗi hiển thị thì không thể tự phục hồi độ chính xác ban đầu.
- Một mẫu chỉ phân biệt âm/dương bằng affix phải bảo đảm **affix đủ khác nhau**, nếu không parser có thể không biết dấu.
- `parse(String)` có thể chấp nhận một tiền tố hợp lệ của chuỗi; nếu dùng để kiểm tra input người dùng, nên dùng `ParsePosition` để xác minh đã tiêu thụ **toàn bộ** chuỗi.
- `parseBigDecimal` trên `DecimalFormat` hữu ích khi cần giá trị thập phân chính xác hơn cho đầu vào, nhưng nó không biến parser thành bộ xác thực nghiệp vụ hay một phép chuyển đổi currency.
- Các dấu phân cách, dấu âm, suffix và ký hiệu tiền tệ phải khớp với `DecimalFormatSymbols`/pattern của bộ parse.
- Không dùng kết quả format để làm “mã định danh số” hoặc serialization cho API/database. Định dạng hiển thị có thể đổi theo locale, yêu cầu sản phẩm và phiên bản dữ liệu locale.

Ví dụ cách kiểm tra tiêu thụ hết chuỗi (mã minh họa đặt trong phương thức Java):

```java
DecimalFormat df = new DecimalFormat(
        "#,##0.00;(#,##0.00)",
        DecimalFormatSymbols.getInstance(Locale.US));

ParsePosition pos = new ParsePosition(0);
String input = "(1,234.50)";
Number value = df.parse(input, pos);

boolean valid = value != null
        && pos.getIndex() == input.length();
```

Cần import `java.text.ParsePosition`. Điều kiện `valid` ở đây chỉ kiểm tra mức parser đã đọc trọn chuỗi; các kiểm tra như giới hạn giá trị, kiểu nghiệp vụ, độ chính xác và currency vẫn phải thực hiện riêng.

## 11. Locale và DecimalFormatSymbols: pattern không đồng nghĩa chuỗi cố định

`DecimalFormatSymbols` cung cấp các ký hiệu thực tế cho chữ số, dấu grouping, dấu thập phân, dấu trừ, phần trăm, currency và các giá trị đặc biệt. Khi muốn kết quả ổn định, nên tạo symbols từ locale tường minh:

```java
Locale locale = Locale.US;
DecimalFormatSymbols symbols =
        DecimalFormatSymbols.getInstance(locale);
DecimalFormat df = new DecimalFormat("#,##0.00", symbols);
```

Đây là các câu lệnh minh họa trong phương thức Java.

**`applyPattern(...)` và `applyLocalizedPattern(...)` không giống nhau:**

- `applyPattern(...)` đọc cú pháp pattern chuẩn (`.`, `,`, `#`, `0`...) và sau đó sử dụng symbols để hiển thị.
- `applyLocalizedPattern(...)` đọc pattern với ký hiệu đã bản địa hóa theo bộ `DecimalFormatSymbols`. Chỉ dùng khi đầu vào thực sự là localized pattern; tránh chuyển tùy tiện giữa hai dạng.

Ví dụ một pattern chuẩn `#,##0.00` không nên bị dịch thủ công bằng việc thay `.` thành `,` rồi đưa vào `applyPattern(...)` chỉ vì locale muốn dùng dấu phẩy thập phân. Thay vào đó, cấu hình symbols/locale. Pattern nói về **cấu trúc định dạng**; symbols nói về **ký tự hiển thị**.

### Dữ liệu locale không phải currency giao dịch

Locale giúp quyết định ký hiệu/format mặc định, nhưng giá trị tiền tệ, số chữ số thập phân bắt buộc, cách âm bằng ngoặc hoặc dấu trừ và quy tắc rounding thường là yêu cầu sản phẩm. Có thể cần chọn `Currency` riêng và kiểm thử từng thị trường. Không suy ra mã tiền từ quốc tịch hoặc chỉ từ `getCountry()` trong dữ liệu người dùng.

## 12. Thread safety và tái sử dụng formatter

`DecimalFormat` là đối tượng **mutable**, không được bảo đảm thread-safe khi nhiều thread sử dụng đồng thời. Các phương thức `applyPattern(...)`, `setPositivePrefix(...)`, `setRoundingMode(...)` và các setter khác có thể thay đổi cấu hình mà request khác đang dùng.

Những lựa chọn thực tế:

1. **Tạo formatter theo lần gọi/request** khi yêu cầu đơn giản và chi phí chấp nhận được.
2. **Tạo formatter mẫu và `clone()` cho từng luồng/lần dùng** khi cấu hình nhiều và việc clone đã được kiểm thử.
3. **Đồng bộ hóa đúng phạm vi** nếu buộc phải chia sẻ instance; tránh khoá cục bộ không có tác dụng với các thread khác.
4. **Không dùng một static DecimalFormat mutable** rồi cập nhật prefix/suffix theo request hoặc locale khác nhau.

Ngay cả nếu chỉ gọi `format(...)` trong nhiều thread, hợp đồng của `DecimalFormat` không bảo đảm việc chia sẻ là an toàn; đừng dựa vào may mắn test đơn luồng.

## 13. Lỗi phổ biến và cách tránh

| Lỗi | Hệ quả | Cách xử lý |
| --- | --- | --- |
| Viết `positive;negative` để định dạng âm có số chữ số khác dương | Numeric pattern của nhánh âm không điều khiển precision riêng. | Dùng hai formatter khi cần chính sách số khác nhau. |
| Thiếu negative subpattern nhưng kỳ vọng có ngoặc | Mặc định sẽ dùng dấu âm thông thường. | Khai báo negative prefix/suffix, ví dụ `(#,##0.00)`. |
| Ghép thủ công dấu trừ vào chuỗi sau `format` | Dễ sai với locale, âm 0 và những affix đã có. | Đặt pattern/negative prefix đúng ngay từ đầu. |
| Quên quote ký tự `;`, `%` hoặc literal đặc biệt | Parser hiểu là cú pháp, thay đổi nhánh hoặc multiplier. | Dùng quote đúng hoặc API setter cho chuỗi literal. |
| Dùng `0.0%` với giá trị đã nhân 100 | Kết quả sai một bậc 100 lần. | Xác định đơn vị ratio trước khi format. |
| Dùng `'USD'` cố định cho nhiều currency | Nhãn tiền bị sai khi giao dịch đổi đơn vị. | Cấp `Currency` theo nghiệp vụ. |
| Coi `¤` có tác dụng đổi tỷ giá | Chỉ biểu diễn tiền tệ, không chuyển giá trị. | Tách format khỏi phép đổi tiền. |
| Quên test `-0.0` | Kết quả có thể thành `(0.00)`. | Định nghĩa policy với negative zero. |
| Đặt nhánh âm sau khi thêm setter rồi gọi `applyPattern` | Pattern có thể ghi đè cấu hình affix trước đó. | Cấu hình theo thứ tự nhất quán, test output cuối. |
| Parse chuỗi có hậu tố mà không kiểm tra phần dư | Chấp nhận input sai khi parser dừng giữa chừng. | Dùng `ParsePosition` và kiểm tra độ dài tiêu thụ. |
| Dùng một static mutable formatter cho nhiều thread | Nguy cơ trạng thái chéo, kết quả khó tái hiện. | Clone hoặc tạo formatter theo request. |
| Chỉ test số dương | Bỏ sót nhánh âm, âm 0, zero, rounding và affix. | Tạo test matrix đủ các dấu và các biên. |

## 14. Bài tập tự luyện

**Bài 1 — Mẫu âm theo kế toán:** dùng `#,##0.00;(#,##0.00)` để in `1234.5`, `-1234.5`, `0`, `-0.0`. Giải thích vì sao `-0.0` có thể ra ngoặc, và nếu sản phẩm muốn khác thì nên xử lý ở đâu.

**Bài 2 — Prefix/suffix:** thiết kế format có nhãn `Credit: ` cho dương, `Debit: ` cho âm, cùng suffix ` units`. Thực hiện một lần bằng pattern quote literal và một lần bằng setter. Kiểm tra `getPositivePrefix()`/`getNegativeSuffix()` rồi gọi `applyPattern(...)` để quan sát cấu hình bị thay đổi.

**Bài 3 — Precision nhánh âm:** thử `0.00;(0)` với `-12.3`. Giải thích tại sao không ra `(12)`. Thiết kế hai formatter riêng nếu yêu cầu nghiệp vụ thực sự muốn hiển thị số dương với hai chữ số phần lẻ, số âm không có phần lẻ.

**Bài 4 — Percent và currency:** thử `0.0%;(0.0%)` với `0.125` và `-0.125`; so sánh với pattern có dấu `'%'` literal. Tiếp theo, phân biệt `¤`, `¤¤` và `'USD'` khi locale/`Currency` thay đổi. Không thực hiện phép quy đổi tỷ giá trong formatter.

**Bài 5 — Parse kế toán:** dùng `parse(String, ParsePosition)` với `(1,234.50)`, `1,234.50`, chuỗi có ký tự thừa ở cuối và chuỗi sai prefix. Chỉ nhận input khi parse thành công **và** đọc hết toàn bộ string. Thêm validation về miền giá trị.

**Bài 6 — Hai locale:** tạo formatter `#,##0.00;(#,##0.00)` với `Locale.US` và một locale khác được sản phẩm hỗ trợ. Quan sát cách ký hiệu thập phân/grouping thay đổi mà cấu trúc pattern vẫn như nhau; giải thích khi nào dùng `applyLocalizedPattern`.

### Checklist hoàn thành

- [ ] Biết đọc `positiveSubpattern;negativeSubpattern` và phân biệt dấu `;` với dấu ngăn thập phân.
- [ ] Hiểu negative subpattern đổi **prefix/suffix**, không đặt riêng precision cho số âm.
- [ ] Biết dùng `get/setPositivePrefix`, `get/setNegativeSuffix` và quote literal.
- [ ] Phân biệt percent multiplier, per-mille, currency symbol với chữ literal.
- [ ] Kiểm thử đúng `0`, `-0.0`, số dương/âm, làm tròn và parse.
- [ ] Truyền `Locale`/`DecimalFormatSymbols` tường minh và quản lý currency theo dữ liệu nghiệp vụ.
- [ ] Không chia sẻ `DecimalFormat` mutable giữa nhiều thread nếu không có cơ chế an toàn.

**Ghi nhớ:** pattern `DecimalFormat` quyết định cách thể hiện **giá trị số và affix**. Đừng dùng nhánh âm để đổi precision, đừng coi currency symbol là chuyển đổi tiền, và đừng biến định dạng số thành nơi cất toàn bộ logic bản dịch/nghiệp vụ.
