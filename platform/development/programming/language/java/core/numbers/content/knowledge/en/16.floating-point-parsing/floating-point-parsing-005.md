# Phân biệt parse số theo cú pháp Java với parse theo locale

Trong Java, **“chuỗi biểu diễn một số” không chỉ có một cú pháp duy nhất**. Chuỗi kỹ thuật như `"1234.56"`, `"1.25e3"` có cách hiểu khác với văn bản số do người dùng nhập theo khu vực, ví dụ `"1,234.56"` ở Hoa Kỳ hay `"1.234,56"` ở Đức.

Hai họ API phổ biến phục vụ **hai hợp đồng đầu vào khác nhau**:

- **Cú pháp độc lập locale, dùng cho dữ liệu máy:** `Double.parseDouble`, `Float.parseFloat`, `new BigDecimal(String)`. Dấu thập phân thông thường là **dấu chấm `.`**, không tự dùng quy ước phân cách của người dùng.
- **Cú pháp theo ngôn ngữ/khu vực (locale):** `NumberFormat` và `DecimalFormat`. Dấu thập phân, dấu nhóm hàng nghìn, ký tự số, thậm chí ký hiệu âm có thể phụ thuộc `Locale` và cấu hình định dạng.

Ví dụ:

```java
double machine = Double.parseDouble("1234.56"); // 1234.56

NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

double fromUs = us.parse("1,234.56").doubleValue();  // 1234.56
double fromDe = de.parse("1.234,56").doubleValue();  // 1234.56
```

*Các dòng trên là mã minh họa đặt trong một phương thức, có `import java.text.NumberFormat;`, `import java.util.Locale;` và khai báo `throws ParseException` hoặc xử lý exception.*

**Không nên dùng `Double.parseDouble` để đọc trực tiếp chuỗi người dùng nhập theo locale**, cũng không nên sử dụng `NumberFormat` thay cho một parser dữ liệu giao thức cố định khi cần bảo đảm cú pháp hoàn toàn nhất quán.

Bài này thuộc phần **Phân tích số thực** trong module **Java core – numbers**. Ta sẽ đi từ cơ chế, các trường hợp ranh giới, lỗi parse đến cách thiết kế parser an toàn cho Java 17+.

## 1. Locale là gì và liên quan đến số ra sao?

`java.util.Locale` mô tả quy ước ngôn ngữ/khu vực dùng bởi các API có tính quốc tế hóa. Với một số, `Locale` có thể ảnh hưởng đến:

- **Dấu thập phân:** dấu chấm `.` hoặc dấu phẩy `,`.
- **Dấu nhóm chữ số:** dấu phẩy, dấu chấm, khoảng trắng thông thường, khoảng trắng không ngắt hoặc ký tự nhóm riêng.
- **Nhóm số:** quy ước chia nhóm theo 3 chữ số hoặc kiểu nhóm khác.
- **Chữ số:** một số locale dùng chữ số và ký hiệu không phải ASCII.
- **Biểu diễn số âm, phần trăm hoặc tiền tệ:** có thể thay đổi theo loại `NumberFormat`.

Hai ví dụ cơ bản:

| Giá trị toán học | Chuỗi theo `Locale.US` | Chuỗi theo `Locale.GERMANY` |
| ---: | --- | --- |
| Một nghìn hai trăm ba mươi bốn phẩy năm sáu | `1,234.56` | `1.234,56` |
| Một phẩy năm | `1.5` | `1,5` |
| Một nghìn | `1,000` | `1.000` |

**Điều nguy hiểm:** `"1.234"` trong dữ liệu kiểu US có thể được hiểu là một phẩy hai ba bốn, trong khi với quy ước số Đức nó có thể là một nghìn hai trăm ba mươi bốn. **Không thể suy ra ý nghĩa số chỉ từ chuỗi nếu thiếu hợp đồng locale/format**.

### Locale mặc định và locale tường minh

```java
Locale current = Locale.getDefault();
NumberFormat format = NumberFormat.getNumberInstance(current);
```

Locale mặc định có thể thay đổi theo hệ điều hành, cấu hình JVM hoặc do phần khác của chương trình sửa. Nếu một API phải xử lý **dữ liệu có format cố định**, hãy truyền locale tường minh thay vì mặc định môi trường:

```java
NumberFormat parser = NumberFormat.getNumberInstance(Locale.US);
```

**Chọn `Locale.US` không làm parser trở thành “parser cú pháp Java”**: nó vẫn là parser theo locale, với quy tắc grouping và hành vi parse có thể linh hoạt. Đối với giao thức máy quy định `1234.56`, thường nên dùng `Double.parseDouble` hoặc `BigDecimal(String)` và validation riêng.

## 2. Double.parseDouble và Float.parseFloat: cú pháp độc lập locale

`Double.parseDouble(String)` trả `double`; `Float.parseFloat(String)` trả `float`. Cả hai xử lý văn bản theo cú pháp số thực do Java quy định, **không nhìn `Locale.getDefault()` để tự đổi dấu thập phân**.

```java
double a = Double.parseDouble("1234.56"); // 1234.56
double b = Double.parseDouble("1.25e3");  // 1250.0
float c = Float.parseFloat("-2.5");      // -2.5f
```

Các cách viết thường được hỗ trợ:

| Input | Kết quả/ý nghĩa |
| --- | --- |
| `"12.5"` | Số thập phân 12.5 |
| `"-0.5"` | Số âm -0.5 |
| `"+3.0"` | Số dương có dấu + |
| `"1e3"` | 1000.0 |
| `"1.5E-2"` | 0.015 |
| `"0x1.8p1"` | Số thực hệ 16 với mũ nhị phân, bằng 3.0 |
| `"NaN"` | Giá trị đặc biệt NaN |
| `"Infinity"` | Vô cực dương |
| `"-Infinity"` | Vô cực âm |
| `"1.5f"` hoặc `"1.5d"` | Cú pháp có hậu tố kiểu được parser dấu phẩy động Java chấp nhận |

**Không đồng nhất hoàn toàn cú pháp literal trong source với chuỗi runtime:** `Double.parseDouble` chấp nhận một số cách viết giống literal số thực như dạng hexadecimal float hoặc hậu tố `f`/`d`, nhưng **không chấp nhận dấu gạch dưới phân tách chữ số** như Java source.

```java
double sourceLiteral = 1_234.56; // Literal Java có dấu gạch dưới.
// Double.parseDouble("1_234.56"); // NumberFormatException.
```

### Dấu thập phân không phụ thuộc locale

```java
double correct = Double.parseDouble("1.5"); // 1.5.
// Double.parseDouble("1,5"); // NumberFormatException.
```

`Locale.GERMANY` không khiến `Double.parseDouble("1,5")` tự thành 1.5. Muốn parse dữ liệu người dùng theo Đức, dùng `NumberFormat` với locale thích hợp hoặc một cú pháp được ứng dụng định nghĩa rõ.

### Khoảng trắng và suffix: những chi tiết cần nhớ

`Double.parseDouble` và `Float.parseFloat` cho phép một số whitespace ASCII ở đầu/cuối theo quy tắc trim của parser, nhưng không vì thế mà chấp nhận dấu nhóm hay khoảng trắng bất kỳ ở giữa một con số:

```java
double trimmed = Double.parseDouble(" 2.5 "); // 2.5.
// Double.parseDouble("2 5"); // NumberFormatException.
```

Không nên suy ra mọi dạng Unicode whitespace được tự loại bỏ. Nếu cần xử lý input nhập từ người dùng, hãy xác định chính sách `strip`/`trim`, Unicode và validation tường minh.

**Không nhận định rằng số quá lớn luôn ném NumberFormatException:** cú pháp có thể hợp lệ nhưng giá trị vượt miền hữu hạn của `double`.

```java
double overflow = Double.parseDouble("1e309");
System.out.println(Double.isInfinite(overflow)); // true

double underflow = Double.parseDouble("1e-400");
System.out.println(underflow == 0.0); // true
```

Ngược lại, chuỗi sai cú pháp như `"1_000.0"` hay `"abc"` gây `NumberFormatException`. **Tính hợp lệ cú pháp** và **tính hợp lệ về miền nghiệp vụ** là hai câu hỏi khác nhau.

## 3. BigDecimal(String): cú pháp thập phân chính xác, không theo locale

`new BigDecimal(String)` đọc biểu diễn số thập phân theo cú pháp được `BigDecimal` hỗ trợ. Nó cho phép **giữ chính xác giá trị thập phân** của chuỗi đầu vào thay vì buộc giá trị vào nhị phân `double`.

```java
BigDecimal amount = new BigDecimal("1234.56");
System.out.println(amount.toPlainString()); // 1234.56
```

`BigDecimal` thích hợp khi cần tính số tiền, thuế, hoặc các giá trị thập phân mà quy tắc làm tròn và `scale` phải được kiểm soát.

```java
BigDecimal price = new BigDecimal("0.10");
BigDecimal tax = new BigDecimal("0.20");
BigDecimal sum = price.add(tax);
System.out.println(sum.toPlainString()); // 0.30
```

Không nên viết:

```java
BigDecimal wrong = new BigDecimal(0.1);
```

Cách đó lấy **đúng giá trị nhị phân double đã xấp xỉ 0.1**, chứ không dựng lại số thập phân 0.1 mong muốn. Nếu đầu vào là text thập phân gốc, dùng `new BigDecimal(text)`. Nếu nhận `double` hợp lệ và chủ ý muốn chuyển theo biểu diễn thập phân chuẩn hóa, cân nhắc `BigDecimal.valueOf(double)`, nhưng nó không khôi phục dữ liệu đầu vào đã mất thông tin.

### BigDecimal(String) cũng không tự hiểu dấu phân cách locale

```java
new BigDecimal("1234.56"); // Hợp lệ.

// new BigDecimal("1.234,56"); // NumberFormatException.
// new BigDecimal("1,234.56"); // NumberFormatException.
```

Để xử lý giá trị **theo locale mà vẫn giữ số thập phân chính xác**, có thể cấu hình `DecimalFormat.setParseBigDecimal(true)` sau khi xác định đúng `Locale` và cú pháp được chấp nhận. Đây là chủ đề của phần tiếp theo.

### Khác biệt với NaN và Infinity

`BigDecimal` không có NaN hoặc vô cực làm giá trị biểu diễn:

```java
// new BigDecimal("NaN");       // NumberFormatException.
// new BigDecimal("Infinity");  // NumberFormatException.
```

Nếu hệ thống yêu cầu số hữu hạn, đó có thể là đặc điểm có lợi. Nếu nguồn là `double`, cần kiểm tra `Double.isFinite` trước khi chuyển tiếp sang kiểu thập phân chính xác.

## 4. NumberFormat: parse theo Locale

`java.text.NumberFormat` là lớp trừu tượng cho định dạng và phân tích các con số theo locale. Các factory method thường dùng:

- `NumberFormat.getNumberInstance(locale)`: định dạng/parse số thông thường.
- `NumberFormat.getIntegerInstance(locale)`: cấu hình phục vụ số nguyên; cần hiểu quy tắc làm tròn/parse của implementation.
- `NumberFormat.getPercentInstance(locale)`: định dạng/parse tỷ lệ phần trăm theo quy ước locale.
- `NumberFormat.getCurrencyInstance(locale)`: định dạng/parse số tiền có dấu tiền tệ.

Ví dụ parse số thông thường theo US và Đức:

```java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat german = NumberFormat.getNumberInstance(Locale.GERMANY);

Number x = us.parse("1,234.56");      // 1234.56
Number y = german.parse("1.234,56");  // 1234.56
```

`NumberFormat.parse(String)` ném **`ParseException`** nếu không thể bắt đầu parse một giá trị hợp lệ, nhưng có một điểm cực kỳ quan trọng: phương thức **không mặc định đòi tiêu thụ hết chuỗi**.

### Cùng chuỗi, locale khác: dễ hiểu thành giá trị khác

Giả sử người dùng nhập `"1,5"`:

- Với định dạng Đức, dấu phẩy là dấu thập phân; ý nghĩa thường là 1.5.
- Với một định dạng US mặc định, dấu phẩy là dấu nhóm. Parser có thể diễn giải dấu nhóm theo cách linh hoạt thay vì báo lỗi như bạn kỳ vọng.

Kết quả phụ thuộc locale và cấu hình `NumberFormat`/`DecimalFormat`; vì thế **không đoán “người dùng chắc đang dùng dấu phẩy thập phân” rồi âm thầm đổi ký tự**.

### NumberFormat không nhất thiết trả Double

`NumberFormat.parse(...)` trả `Number`, không phải luôn `Double`:

```java
Number n = NumberFormat.getNumberInstance(Locale.US).parse("42");
```

Kiểu đối tượng thực tế có thể là `Long`, `Double` hoặc một kiểu `Number` khác tùy định dạng, giá trị và cấu hình. **Không ép thẳng sang `Double`** khi chưa có hợp đồng:

```java
// Double d = (Double) n; // Có thể gây ClassCastException.
double value = n.doubleValue(); // Có thể làm mất chính xác nếu n là số lớn.
```

Nếu cần số thập phân chính xác, hãy dùng cấu hình `DecimalFormat` trả `BigDecimal` như ở phần sau, chứ không parse `Number` rồi gọi `doubleValue()` trước khi chuyển sang `BigDecimal`.

## 5. ParseException và lỗi bị bỏ sót: parser có thể chỉ nhận tiền tố

Một parser theo locale có thể **parse thành công một phần đầu chuỗi rồi dừng**:

```java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
Number parsed = us.parse("123xyz");
// Thông thường parsed là số 123; phần "xyz" không được dùng.
```

Đây là tình huống nguy hiểm khi ứng dụng tưởng toàn bộ chuỗi đã hợp lệ. `parse(String)` thành công **không tự chứng minh** dữ liệu đầu vào đã được tiêu thụ toàn bộ.

### Dùng ParsePosition để kiểm tra parse hết chuỗi

`ParsePosition` giữ vị trí bắt đầu, vị trí parser dừng (`getIndex()`) và vị trí lỗi (`getErrorIndex()`). Một hàm kiểm tra có thể là:

```java
static Number parseWhole(String text, NumberFormat format) {
    if (text == null) {
        throw new IllegalArgumentException("Value is required");
    }

    ParsePosition position = new ParsePosition(0);
    Number result = format.parse(text, position);

    if (result == null ||
            position.getIndex() != text.length() ||
            position.getErrorIndex() >= 0) {
        throw new IllegalArgumentException("Invalid localized number");
    }
    return result;
}
```

Đây là **mã minh họa đặt trong một class**, cần import `NumberFormat` và `ParsePosition`. Với `"123xyz"`, nếu parser tiêu thụ `"123"` và dừng ở index 3, phép kiểm tra vị trí sẽ **từ chối**, vì chuỗi dài 6 ký tự.

**Giới hạn của kiểm tra này:** dù parse hết chuỗi, `NumberFormat` vẫn có thể linh hoạt với grouping, khoảng trắng và những quy ước khác. Parse hết chuỗi **không đồng nghĩa validation cú pháp nghiêm ngặt theo mọi quy tắc nghiệp vụ**. Nếu cần cú pháp chính xác tuyệt đối, hãy xác thực pattern/dấu nhóm/độ dài trước hoặc chọn parser chuyên biệt.

### Vì sao không chỉ bắt ParseException?

`NumberFormat.parse(String)` có thể trả kết quả mà không ném `ParseException` khi còn phần đuôi. Ngược lại, `parse(String, ParsePosition)` **không ném ParseException** mà thể hiện tình trạng qua giá trị `null`, `index` và `errorIndex`. Hai API có quy tắc báo lỗi khác nhau; cần xử lý theo overload thực tế.

## 6. DecimalFormat.setParseBigDecimal(true): kết hợp locale với thập phân chính xác

`DecimalFormat` là implementation phổ biến của `NumberFormat` cho số thập phân. Khi cần đọc **số thập phân theo locale** mà tránh trung gian `double`, có thể bật:

```java
DecimalFormat parser =
        (DecimalFormat) NumberFormat.getNumberInstance(Locale.GERMANY);
parser.setParseBigDecimal(true);

BigDecimal amount =
        (BigDecimal) parser.parse("1.234,56");
System.out.println(amount.toPlainString()); // 1234.56
```

Đoạn này cần xử lý hoặc khai báo `ParseException` nếu dùng overload `parse(String)`; cũng dựa vào factory mặc định trả một `DecimalFormat` như các provider thông thường của JDK. Nếu hệ thống dùng `NumberFormatProvider` tùy biến, kiểm tra implementation trước khi cast.

**Khi `setParseBigDecimal(true)`:** kết quả hữu hạn thông thường được parse thành `BigDecimal`, nhưng các giá trị đặc biệt như NaN/vô cực không thể nằm trong `BigDecimal` nên cần chính sách kiểm tra riêng, không cast mù quáng với mọi đầu vào.

Đối với dữ liệu số tiền, nên kiểm tra cả:

- Chính xác locale của người nhập.
- Có được phép nhóm hàng nghìn không? Dấu nhóm đặt ở đâu?
- Có chấp nhận dấu cộng/âm hoặc ký hiệu tiền tệ không?
- `scale` tối đa là mấy chữ số thập phân?
- Nếu cần làm tròn, dùng `RoundingMode` nào?
- Parse phải tiêu thụ hết chuỗi và có cần pattern strict không?

### BigDecimal từ locale parser không phải BigDecimal từ Double

Tránh:

```java
Number n = NumberFormat.getNumberInstance(Locale.GERMANY)
        .parse("1.234,56");

BigDecimal potentiallyApproximate = new BigDecimal(n.doubleValue());
```

Ở đây dữ liệu đã đi qua `double` rồi mới vào `BigDecimal`. Nếu cần giữ giá trị thập phân chính xác từ văn bản, bật `setParseBigDecimal(true)` và parse trực tiếp thành `BigDecimal`.

## 7. NumberFormat và DecimalFormat có trạng thái: tránh dùng chung tùy tiện giữa luồng

Các formatter thuộc họ `NumberFormat`/`DecimalFormat` có thể được cấu hình:

```java
NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
format.setGroupingUsed(true);
format.setMaximumFractionDigits(2);
```

Các cấu hình này thay đổi **hành vi của object cụ thể**. `DecimalFormat` **không thread-safe**; không nên chia sẻ một instance mutable không đồng bộ giữa nhiều request/worker. Trong web service, thường tạo instance riêng theo request, sử dụng factory hoặc một phương án quản lý an toàn được kiểm chứng.

Cũng không tự ý thay `Locale.setDefault(...)` để parse một request: thao tác đó có thể ảnh hưởng các thành phần khác trong cùng JVM. Truyền `Locale` tường minh sẽ dễ kiểm thử hơn.

### Format để hiển thị không đồng nghĩa parse dữ liệu máy

```java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

String usText = us.format(1234.56); // Thường là "1,234.56".
String deText = de.format(1234.56); // Thường là "1.234,56".
```

`format` dùng cho giao diện theo locale; đầu ra có thể bị giới hạn số chữ số thập phân theo cấu hình mặc định. Không dùng output trình bày cho người đọc làm định dạng truyền dữ liệu chính xác mà không định nghĩa rõ pattern, độ chính xác và policy làm tròn.

## 8. Các chuỗi “trông giống nhau” nhưng parser hiểu khác

| Chuỗi | `Double.parseDouble` | `NumberFormat` US | `NumberFormat` Đức | Bài học |
| --- | --- | --- | --- | --- |
| `"1234.56"` | 1234.56 | 1234.56 | Dấu chấm có thể được hiểu là dấu nhóm | Cần chọn format tường minh |
| `"1,234.56"` | Lỗi cú pháp | Thường 1234.56 | Không nên coi là decimal Đức | Grouping theo locale |
| `"1.234,56"` | Lỗi cú pháp | Không nên coi là decimal US | Thường 1234.56 | Dấu chấm/phẩy đổi vai |
| `"1,5"` | Lỗi cú pháp | Có thể thành nhóm chữ số | 1.5 | Cùng text có thể đổi nghĩa |
| `"1e3"` | 1000.0 | Phụ thuộc parser locale/pattern | Phụ thuộc parser locale/pattern | Không giả định hỗ trợ exponent |
| `"NaN"` | NaN | Không phải số hữu hạn thông thường | Không phải số hữu hạn thông thường | Cần policy riêng |
| `"0x1.8p1"` | 3.0 | Không phải cú pháp number locale thông thường | Tương tự | Dạng hex float của Java |
| `"1_000"` | Lỗi | Không tự xem là literal Java | Tương tự | Dấu gạch dưới source khác dữ liệu |
| `" 2.5 "` | 2.5 | Theo quy tắc parse locale | Theo quy tắc parse locale | Whitespace cần hợp đồng |

Bảng diễn đạt **mục đích và những rủi ro điển hình**; `NumberFormat` còn phụ thuộc cấu hình và provider. Đừng suy diễn kết quả cứng cho các trường không được bảo đảm, đặc biệt khi parser linh hoạt và chấp nhận một tiền tố.

## 9. Thiết kế parser cho ba luồng dữ liệu thực tế

### 9.1. Dữ liệu giao thức máy: cú pháp cố định

Giả sử một API định nghĩa số đo JSON/text theo dấu chấm thập phân, không grouping và không NaN/vô cực:

```java
static double parseFiniteMachineDouble(String text) {
    if (text == null) {
        throw new IllegalArgumentException("Value is required");
    }

    final double value;
    try {
        value = Double.parseDouble(text);
    } catch (NumberFormatException ex) {
        throw new IllegalArgumentException("Invalid numeric syntax", ex);
    }
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Finite value required");
    }
    return value;
}
```

Hàm trên dùng cú pháp Java `parseDouble`, cho phép dấu mũ, hexadecimal float, suffix và một số whitespace theo hợp đồng parser. **Nếu giao thức máy yêu cầu grammar hẹp hơn** (ví dụ chỉ `-?[0-9]+(\.[0-9]+)?`), phải validate grammar **trước** hoặc bên cạnh parse. `Double.isFinite` không thay thế validation ký tự.

### 9.2. Form nhập theo locale của người dùng

Một ứng dụng nhập số đo từ người dùng có thể cung cấp locale đang được chọn:

```java
Locale userLocale = Locale.GERMANY;
NumberFormat format = NumberFormat.getNumberInstance(userLocale);
Number number = parseWhole("1.234,56", format);
double value = number.doubleValue();
```

Sau khi parse, kiểm tra miền dữ liệu và `Double.isFinite`. Nếu giá trị là tiền hoặc cần đúng số thập phân đầu vào, dùng `DecimalFormat.setParseBigDecimal(true)` và `BigDecimal` phù hợp.

Với locale có dấu nhóm là **khoảng trắng không ngắt** hoặc dấu nhóm đặc biệt, không đơn giản thay toàn bộ khoảng trắng và dấu phẩy/dấu chấm mà không hiểu quy tắc Unicode. Hãy dùng parser locale đúng và validation theo format được hệ thống cho phép.

### 9.3. Tiền tệ/thập phân chính xác

Tiền không chỉ cần parse thành một giá trị; nó còn cần:

- **Đơn vị và loại tiền** (VND, USD, EUR...).
- **Số chữ số thập phân được chấp nhận**.
- **Định dạng của giao diện và của API** có thể khác nhau.
- **Policy làm tròn** rõ ràng cho phép chia, phần trăm, tỷ giá.
- **Không chuyển qua double** nếu yêu cầu chính xác thập phân.

Một thiết kế tốt thường tách: **input localized text → parser/validation → BigDecimal chuẩn hóa theo nghiệp vụ → dữ liệu miền**; khi hiển thị làm chiều ngược lại **BigDecimal → localized output text**.

## 10. Chương trình Java 17+ chạy độc lập

Lưu đoạn sau thành **`LocaleNumberParsingDemo.java`**:

```java
import java.math.BigDecimal;
import java.text.DecimalFormat;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class LocaleNumberParsingDemo {
    static Number parseWhole(String text, NumberFormat format) {
        if (text == null) {
            throw new IllegalArgumentException("Text is required");
        }
        ParsePosition position = new ParsePosition(0);
        Number number = format.parse(text, position);
        if (number == null
                || position.getErrorIndex() >= 0
                || position.getIndex() != text.length()) {
            throw new IllegalArgumentException("Invalid localized number");
        }
        return number;
    }

    static String tryMachineDouble(String text) {
        try {
            return Double.toString(Double.parseDouble(text));
        } catch (NumberFormatException ex) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        System.out.println("machine=" +
                Double.parseDouble("1234.56"));
        System.out.println("scientific=" +
                Double.parseDouble("1e3"));
        System.out.println("hex-float=" +
                Double.parseDouble("0x1.8p1"));
        System.out.println("whitespace=" +
                Double.parseDouble(" 2.5 "));
        System.out.println("comma-machine=" +
                tryMachineDouble("1,234.56"));
        System.out.println("underscore-machine=" +
                tryMachineDouble("1_000"));
        System.out.println("overflow-infinite=" +
                Double.isInfinite(Double.parseDouble("1e309")));
        System.out.println("nan=" +
                Double.isNaN(Double.parseDouble("NaN")));

        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);

        Number usValue = parseWhole("1,234.56", us);
        Number deValue = parseWhole("1.234,56", de);
        System.out.println("locale-us=" + usValue.doubleValue());
        System.out.println("locale-de=" + deValue.doubleValue());
        System.out.println("locale-same=" +
                (usValue.doubleValue() == deValue.doubleValue()));

        String withSuffix = "123xyz";
        ParsePosition position = new ParsePosition(0);
        Number prefix = us.parse(withSuffix, position);
        System.out.println("prefix=" + prefix +
                ",consumed=" + position.getIndex());
        try {
            parseWhole(withSuffix, us);
        } catch (IllegalArgumentException ex) {
            System.out.println("strict-consumption=INVALID");
        }

        DecimalFormat germanDecimal =
                (DecimalFormat) NumberFormat.getNumberInstance(
                        Locale.GERMANY);
        germanDecimal.setParseBigDecimal(true);
        BigDecimal exactLocalized =
                (BigDecimal) parseWhole("1.234,56", germanDecimal);
        System.out.println("localized-decimal=" +
                exactLocalized.toPlainString());

        BigDecimal exactMachine = new BigDecimal("1234.56");
        System.out.println("machine-decimal=" +
                exactMachine.toPlainString());
        System.out.println("decimal-sum=" +
                new BigDecimal("0.10")
                        .add(new BigDecimal("0.20"))
                        .toPlainString());

        System.out.println("format-us=" + us.format(1234.56));
        System.out.println("format-de=" + de.format(1234.56));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac LocaleNumberParsingDemo.java
java LocaleNumberParsingDemo
```

Stdout trên JDK 17+ với dữ liệu locale chuẩn US/Đức:

```text
machine=1234.56
scientific=1000.0
hex-float=3.0
whitespace=2.5
comma-machine=INVALID
underscore-machine=INVALID
overflow-infinite=true
nan=true
locale-us=1234.56
locale-de=1234.56
locale-same=true
prefix=123,consumed=3
strict-consumption=INVALID
localized-decimal=1234.56
machine-decimal=1234.56
decimal-sum=0.30
format-us=1,234.56
format-de=1.234,56
```

**Chú ý về locale provider:** dữ liệu ký hiệu/nhóm có thể được mở rộng qua hệ thống locale/provider của JDK. Chương trình cố định `Locale.US` và `Locale.GERMANY` để tránh lệ thuộc locale mặc định, nhưng với môi trường cấu hình provider tùy biến, hãy kiểm tra đầu ra thực tế thay vì gắn mọi biến thể ký hiệu vào một giả định chung.

### Giải thích kết quả

1. `machine`, `scientific`, `hex-float` cho thấy parser dấu phẩy động Java xử lý cú pháp độc lập locale, gồm exponent và hexadecimal float.
2. `comma-machine=INVALID` vì `Double.parseDouble` không tự nhận nhóm chữ số `1,234.56`; dấu `_` cũng bị từ chối trong chuỗi runtime.
3. `overflow-infinite=true` chứng minh parse hợp lệ về cú pháp **không đồng nghĩa giá trị hữu hạn**.
4. Hai số locale US/Đức biểu diễn cùng giá trị nhưng văn bản khác nhau.
5. `prefix=123,consumed=3` cho thấy parser có thể nhận **một đoạn đầu** rồi dừng; `parseWhole` từ chối vì không hết input.
6. `setParseBigDecimal(true)` trả `BigDecimal` cho chuỗi hữu hạn Đức, giữ thập phân **1234.56** mà không đi qua `double`.
7. `decimal-sum=0.30` cho thấy `BigDecimal` giữ chính xác chữ số thập phân và `scale` của dữ liệu mẫu.

## 11. Lỗi thường gặp và cách khắc phục

| Lỗi/nhầm lẫn | Vì sao sai | Hướng xử lý |
| --- | --- | --- |
| Cho rằng `Double.parseDouble` dùng locale mặc định | Nó dùng grammar riêng, không tự đổi dấu thập phân | Dùng NumberFormat nếu input localized |
| Parse `"1,5"` bằng `Double.parseDouble` | Dấu phẩy không phải dấu thập phân được nhận | Chọn locale/parser phù hợp |
| Dùng NumberFormat không truyền locale | Kết quả phụ thuộc cấu hình hệ thống | Truyền Locale tường minh |
| Cho rằng parse(String) tiêu thụ cả chuỗi | Có thể nhận tiền tố hợp lệ rồi dừng | Dùng ParsePosition và kiểm tra index |
| Cho rằng ParsePosition bảo đảm mọi grouping đúng format | Parser locale có thể linh hoạt | Validation pattern/grammar bổ sung |
| Ép `(Double) numberFormat.parse(text)` | Kết quả Number có thể là Long | Dùng Number, hoặc cấu hình BigDecimal |
| Gọi `new BigDecimal(number.doubleValue())` sau parse locale | Đưa sai số nhị phân vào BigDecimal | Parse trực tiếp với setParseBigDecimal(true) |
| Coi `Double.parseDouble("1e309")` là input hữu hạn | Kết quả Infinity dù cú pháp hợp lệ | Kiểm tra Double.isFinite |
| Parse số tiền thành double | Có thể mất decimal exactness | BigDecimal + scale/RoundingMode |
| Tự thay tất cả dấu chấm/phẩy | Dễ đổi nghĩa số hoặc chấp nhận format sai | Dùng locale chính xác và hợp đồng grammar |
| Cho rằng formatter dùng chung thread-safe | NumberFormat/DecimalFormat có trạng thái | Tạo instance riêng, tránh chia sẻ mutable |
| Lấy chuỗi format UI làm payload API | Format có grouping và rounding theo locale | Dùng schema số máy cố định |
| Coi NaN/Infinity là các BigDecimal hợp lệ | BigDecimal không biểu diễn chúng | Validation và loại dữ liệu tường minh |

## 12. Bài tập tự luyện

1. **So sánh hai parser.** Với `"1,234.56"` và `"1.234,56"`, thử `Double.parseDouble`, `NumberFormat` US và `NumberFormat` Đức. Mỗi trường hợp có tiêu thụ hết chuỗi không? Chỉ kết luận sau khi kiểm tra `ParsePosition`.
2. **Chuỗi có phần đuôi.** Parse `"42kg"` bằng `NumberFormat.parse(String)` và bằng hàm `parseWhole`. Vì sao một cách có thể nhận 42 còn cách kia phải từ chối?
3. **Cú pháp Java.** Dự đoán hành vi của `Double.parseDouble("1e3")`, `Double.parseDouble("0x1.8p1")`, `Double.parseDouble("1_000")`, `Double.parseDouble("NaN")`.
4. **Số hữu hạn.** Viết method nhận số máy và từ chối NaN, Infinity, giá trị ngoài `[-1000, 1000]`. Vì sao bắt NumberFormatException chưa đủ?
5. **Locale và tiền.** Tạo parser số tiền theo `Locale.GERMANY`, bật `setParseBigDecimal(true)` rồi tính thuế bằng `BigDecimal`. Chọn scale/RoundingMode theo hợp đồng cụ thể.
6. **Ràng buộc nhóm.** Thiết kế validator US chỉ chấp nhận `"1234.56"` hoặc `"1,234.56"` theo quy tắc nhóm ba chữ số, nhưng từ chối `"12,34.56"`. Tại sao chỉ parse hết chuỗi chưa đủ để chứng minh grouping hợp lệ?
7. **Quốc tế hóa.** Thử locale dùng dấu nhóm không phải dấu phẩy/chấm. Tại sao không nên tự xóa tất cả khoảng trắng?
8. **API và UI.** Thiết kế luồng lưu trữ: input localized → BigDecimal → dữ liệu miền → format localized; phân biệt bước nào được phép làm tròn.
9. **Test tự động.** Viết unit test cho `parseWhole` với null, chuỗi rỗng, chuỗi sai, số có suffix, số hợp lệ US/Đức và trường hợp có phần đuôi.
10. **Giao thức.** Một file CSV máy quy định dấu chấm thập phân và không có grouping. Tại sao đặt `Locale.getDefault()` vào parser khiến file có thể được hiểu khác khi chạy trên máy khác?

## 13. Checklist thực hành

- Hỏi đầu tiên: **đây là dữ liệu kỹ thuật cố định hay chuỗi hiển thị/nhập theo locale?**
- Với dữ liệu máy: dùng `Double.parseDouble`, `Float.parseFloat` hoặc `BigDecimal(String)` và validation grammar theo giao thức.
- Với dữ liệu người dùng theo vùng: dùng `NumberFormat`/`DecimalFormat` với **Locale tường minh**.
- Nhớ dấu `.`, `,`, grouping và ký tự Unicode có thể đổi nghĩa theo locale.
- Với `NumberFormat`, **kiểm tra tiêu thụ hết chuỗi** bằng `ParsePosition` khi cần; kết quả parse một tiền tố chưa phải chứng cứ input hợp lệ.
- Nếu grammar phải nghiêm ngặt, bổ sung validator cho grouping, dấu, whitespace, số chữ số và format chấp nhận.
- Không ép kết quả `Number` thành `Double` mà không kiểm tra kiểu; nếu cần thập phân chính xác, dùng `DecimalFormat.setParseBigDecimal(true)`.
- Không dùng `new BigDecimal(double)` sau khi đã parse qua double để “phục hồi” chuỗi thập phân.
- Kiểm tra `NaN`/`Infinity` và miền dữ liệu khi parse ra float/double.
- Với số tiền hoặc dữ liệu decimal exact, giữ `BigDecimal` và quy tắc làm tròn nghiệp vụ.
- Không chia sẻ `DecimalFormat` mutable giữa các thread nếu không có bảo vệ phù hợp.
- Kiểm thử trên nhiều `Locale`, kể cả locale khác dấu nhóm, và với input sai ở cuối chuỗi.

**Kết luận:** `parseDouble`/`parseFloat` và `BigDecimal(String)` phù hợp với **cú pháp số độc lập locale**, trong khi `NumberFormat`/`DecimalFormat` phục vụ **chuỗi số theo quy ước khu vực**. Chọn đúng parser, kiểm tra tiêu thụ hết input, giữ độ chính xác theo yêu cầu và tách parse khỏi validation là chìa khóa để tránh những lỗi số học âm thầm trong ứng dụng Java.
