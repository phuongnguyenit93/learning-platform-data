# Phân biệt mã hóa ký tự và quy tắc `Locale` khi đọc, định dạng số (Java 10+)

## 1. Hai tầng xử lý phải tách riêng

Khi hệ thống Java đọc một con số từ file, HTTP request hoặc nguồn nhập liệu khác, thường tồn tại **hai bài toán độc lập**:

1. **`Charset` — mã hóa/giải mã ký tự:** chuyển giữa các **byte** bên ngoài chương trình và chuỗi ký tự Java (`String`/`char`).
2. **`Locale` — quy ước văn hóa khi phân tích/định dạng số:** quyết định các ký hiệu như dấu thập phân, dấu phân nhóm nghìn và một số dạng hiển thị số trong **chuỗi ký tự**.

Đường đi đúng khi đọc:

```text
Bytes của tệp / mạng
       |
       | Giải mã bằng Charset, ví dụ UTF-8
       v
String "1.234,56"
       |
       | Phân tích bằng Locale.GERMANY
       v
BigDecimal 1234.56
```

Đường đi đúng khi ghi:

```text
BigDecimal 1234.56
       |
       | Định dạng theo Locale.US
       v
String "1,234.56"
       |
       | Mã hóa bằng Charset UTF-8
       v
Bytes của tệp / mạng
```

**Quy tắc cốt lõi:** Charset không tự biến dấu phẩy thành dấu chấm thập phân. Locale không tự biến byte UTF-8 thành ký tự Unicode. Một file UTF-8 có thể chứa số theo quy ước Đức, Mỹ hoặc một định dạng máy–máy hoàn toàn độc lập Locale.

Ví dụ cùng một số:

```java
var amount = new java.math.BigDecimal("1234.56");

System.out.println(
        String.format(java.util.Locale.US, "%,.2f", amount));
// 1,234.56

System.out.println(
        String.format(java.util.Locale.GERMANY, "%,.2f", amount));
// 1.234,56
```

Hai chuỗi khác nhau về **quy tắc hiển thị**, còn giá trị `BigDecimal` ở giữa không đổi.

Bài thuộc nhóm kiến thức **Charset trong I/O** của Java 10 và chỉ sử dụng các khái niệm, API vẫn được áp dụng trong Java hiện đại. Ví dụ chạy độc lập dùng JDK 17 trở lên.

## 2. Mục tiêu học tập

Sau bài học, bạn có thể:

- Phân biệt Charset và Locale mà không nhầm chức năng.
- Đọc văn bản UTF-8 từ byte hoặc file rồi parse số theo đúng Locale.
- Hiển thị cùng một số ở định dạng Mỹ và Đức.
- Sử dụng `NumberFormat`, `DecimalFormat`, `DecimalFormatSymbols` và `Scanner.useLocale`.
- Biết vì sao `Double.parseDouble` và `BigDecimal(String)` không tự chấp nhận cú pháp số theo Locale.
- Dùng `BigDecimal` cho số thập phân cần độ chính xác.
- Xác minh một chuỗi số được parse hết, không bỏ qua suffix trái phép.
- Phân biệt cú pháp số dùng cho giao diện người dùng và giao thức máy–máy.
- Phòng tránh lỗi charset, default locale, CSV dấu phẩy, parser lenient và formatter mutable trong môi trường đa luồng.
- Viết test với charset, locale tường minh để kết quả không thay đổi theo máy chạy.

## 3. `Charset` là gì?

`java.nio.charset.Charset` mô tả mối quan hệ giữa chuỗi các byte và các đơn vị ký tự Java. Khi `InputStreamReader` đọc một stream byte, nó sử dụng charset để **giải mã** thành ký tự; khi `OutputStreamWriter` ghi ký tự vào stream byte, nó **mã hóa** theo charset.

Các charset thường gặp:

| Charset | Mục đích |
| --- | --- |
| `StandardCharsets.UTF_8` | Biểu diễn Unicode dạng UTF-8, rất phổ biến cho file và giao thức hiện đại |
| `StandardCharsets.UTF_16` | Biểu diễn Unicode bằng cách mã hóa UTF-16 |
| `StandardCharsets.ISO_8859_1` | Charset một byte, không biểu diễn được mọi ký tự Unicode |
| `StandardCharsets.US_ASCII` | Chỉ bao phủ nhóm ký tự ASCII |

Ví dụ:

```java
String text = "Số tiền: 1.234,56 €";

byte[] bytes = text.getBytes(
        java.nio.charset.StandardCharsets.UTF_8);

String restored = new String(
        bytes, java.nio.charset.StandardCharsets.UTF_8);

System.out.println(restored.equals(text)); // true
```

Nếu giải mã **cùng byte UTF-8** bằng charset không khớp:

```java
String wrong = new String(
        bytes, java.nio.charset.StandardCharsets.ISO_8859_1);

System.out.println(wrong.equals(text)); // false
```

Chữ có dấu hoặc ký hiệu `€` có thể bị biến thành chuỗi ký tự sai (*mojibake*). Đổi sang `Locale.GERMANY` hoặc `Locale.US` sau đó **không phục hồi văn bản**, vì lỗi đã xảy ra ở tầng giải mã byte.

### Tại sao ví dụ toàn số ASCII dễ gây hiểu nhầm?

Các ký tự `0–9`, `,` và `.` đều thuộc ASCII, nên chuỗi `"1.234,56"` có thể trông nguyên vẹn cả khi sử dụng một số charset khác nhau. Điều này **không chứng minh hai charset tương đương**. Hãy test với chữ có dấu, emoji hoặc ký hiệu tiền tệ để phát hiện charset không phù hợp.

### `char` khác byte

Một ký tự Java `char` là một đơn vị UTF-16, không đồng nghĩa một byte UTF-8. Ví dụ emoji `🙂` dùng hai đơn vị UTF-16 nhưng bốn byte UTF-8. Charset xử lý biểu diễn byte, không định nghĩa dấu thập phân hoặc dấu phân cách số.

## 4. `Locale` là gì trong bài toán số?

`java.util.Locale` thể hiện các đặc điểm ngôn ngữ/vùng và được các API *locale-sensitive* sử dụng. Với số, các quy tắc thường liên quan:

- **Dấu thập phân:** Mỹ thường dùng `.`, Đức thường dùng `,`.
- **Dấu nhóm nghìn:** Mỹ thường dùng `,`, Đức thường dùng `.`.
- **Biểu diễn tiền tệ, phần trăm**, dấu âm hoặc các chữ số theo hệ chữ số của locale.
- Cách parser nhận diện chuỗi số đã được người dùng nhập.

Bảng ví dụ:

| Giá trị toán học | `Locale.US` | `Locale.GERMANY` |
| --- | --- | --- |
| Một nghìn hai trăm ba mươi tư phẩy năm sáu | `1,234.56` | `1.234,56` |
| Dấu thập phân | Dấu chấm `.` | Dấu phẩy `,` |
| Dấu nhóm nghìn | Dấu phẩy `,` | Dấu chấm `.` |

Đây là **quy tắc trình bày/phân tích** chứ không phải định dạng byte. Cả hai chuỗi đều có thể lưu trong file UTF-8.

**Không tự suy luận charset từ tên quốc gia.** Một hệ thống tại Đức hoàn toàn có thể dùng UTF-8; một hệ thống tại Mỹ cũng dùng UTF-8, nhưng vẫn khác nhau về quy ước hiển thị số.

## 5. So sánh trực tiếp Charset và Locale

| Câu hỏi | Charset | Locale |
| --- | --- | --- |
| Giải quyết việc gì? | Byte ↔ ký tự | Số ↔ chuỗi số có quy ước vùng |
| Đối tượng chính | `Charset`, `StandardCharsets` | `Locale`, `NumberFormat`, `DecimalFormat` |
| Có quyết định `1.234,56` mang nghĩa gì không? | **Không** | **Có**, theo quy tắc số |
| Có quyết định cách đọc byte UTF-8 không? | **Có** | **Không** |
| Thường cấu hình ở đâu? | `InputStreamReader`, `OutputStreamWriter`, `Files.newBufferedReader` | `NumberFormat`, `DecimalFormat`, `Scanner.useLocale` |
| Khi nào dùng? | Đọc/ghi file, mạng, luồng byte | Nhập số từ người dùng và hiển thị theo vùng |
| Có làm đổi giá trị số đã lưu không? | Không trực tiếp, nhưng decode sai làm text sai | Chỉ cách parse/format; phải chọn đúng để tránh hiểu sai dữ liệu |
| Nên khai báo tường minh? | Có, ở ranh giới byte/văn bản | Có, ở ranh giới dữ liệu số có quy tắc vùng |

Không có “Charset cho dấu phẩy kiểu Đức” hay “Locale cho giải mã UTF-8”. Từng kiểu cấu hình trả lời một câu hỏi riêng.

## 6. Quy trình đọc số: từ byte tới `BigDecimal`

Giả sử nguồn cho biết:

- Byte được mã hóa UTF-8.
- Trường số theo quy ước Đức.
- Dữ liệu là `1.234,56`, tức giá trị thập phân `1234.56`.

Bước 1: decode:

```java
byte[] bytes = "1.234,56".getBytes(StandardCharsets.UTF_8);
String text = new String(bytes, StandardCharsets.UTF_8);
```

Bước 2: parse:

```java
NumberFormat parser = NumberFormat.getNumberInstance(Locale.GERMANY);
Number number = parser.parse(text);
```

Hai đoạn là **mã minh họa** trong phương thức đã import `StandardCharsets`, `Locale`, `NumberFormat` và xử lý `ParseException`.

Điều có thể sai:

- Chọn charset sai → text sai từ trước.
- Chọn Locale sai → giá trị số có thể bị hiểu sai, không parse được hoặc parse được **một phần**.
- Parse xong nhưng dùng `double` cho dữ liệu cần decimal chính xác → xuất hiện rủi ro sai số nhị phân.
- Chỉ kiểm xem `parse(...)` trả một `Number` mà không kiểm phần dư → có thể nhận dữ liệu không hợp lệ.

Đối với số thập phân cần chính xác, tiếp tục sử dụng `DecimalFormat` với `setParseBigDecimal(true)` và validation.

## 7. Định dạng số bằng `NumberFormat`

`NumberFormat` cung cấp factory theo Locale:

```java
var amount = new java.math.BigDecimal("1234.56");

var us = java.text.NumberFormat.getNumberInstance(
        java.util.Locale.US);
var de = java.text.NumberFormat.getNumberInstance(
        java.util.Locale.GERMANY);

us.setMinimumFractionDigits(2);
us.setMaximumFractionDigits(2);
de.setMinimumFractionDigits(2);
de.setMaximumFractionDigits(2);

System.out.println(us.format(amount)); // 1,234.56
System.out.println(de.format(amount)); // 1.234,56
```

Cùng `BigDecimal` nhưng có cách hiển thị khác nhau.

### Những factory khác

```java
NumberFormat currency =
        NumberFormat.getCurrencyInstance(Locale.GERMANY);
NumberFormat percent =
        NumberFormat.getPercentInstance(Locale.US);
```

Đoạn này minh họa trong môi trường đã import `NumberFormat`/`Locale`. Các formatter tiền tệ và phần trăm có quy tắc riêng; **không** nên tạo định dạng tiền tệ chỉ bằng cách nối ký hiệu vào một chuỗi số nếu ứng dụng cần quốc tế hóa đúng.

Lưu ý ký hiệu tiền tệ, dấu cách đặc biệt và các mẫu locale có thể tùy thuộc dữ liệu locale/provider được JDK cung cấp. Khi test, chỉ cố định chuỗi output literal nếu đã xác định rõ môi trường và các yếu tố ảnh hưởng.

## 8. `DecimalFormat` + `DecimalFormatSymbols` để kiểm soát mẫu số

Khi cần hai chữ số thập phân và phân nhóm nghìn:

```java
static DecimalFormat decimalFormat(Locale locale) {
    var symbols = DecimalFormatSymbols.getInstance(locale);
    var format = new DecimalFormat("#,##0.00", symbols);
    format.setParseBigDecimal(true);
    return format;
}
```

Đây là **phương thức minh họa** trong một class có import `DecimalFormat`, `DecimalFormatSymbols` và `Locale`; phiên bản hoàn chỉnh nằm ở mục 16.

Giải thích:

- `#,##0.00` là **pattern kỹ thuật**, với ký tự cú pháp phân nhóm/thập phân được `DecimalFormat` hiểu theo quy tắc pattern chuẩn.
- `DecimalFormatSymbols.getInstance(locale)` cung cấp ký hiệu hiển thị của locale cụ thể.
- `format.setParseBigDecimal(true)` cho phép parse thành `BigDecimal`, phù hợp dữ liệu decimal chính xác.
- Một `DecimalFormat` là object **mutable**, không mặc nhiên an toàn nếu nhiều thread cùng truy cập.

```java
var amount = new BigDecimal("1234.56");

System.out.println(decimalFormat(Locale.US).format(amount));
// 1,234.56

System.out.println(decimalFormat(Locale.GERMANY).format(amount));
// 1.234,56
```

### Định dạng không phải biến đổi giá trị gốc

Mẫu `#,##0.00` có thể làm tròn **chuỗi đầu ra** về hai chữ số thập phân. Không được coi việc format là sửa chính `BigDecimal` đầu vào. Khi nghiệp vụ quy định số chữ số tiền tệ, nên xác định quy tắc scale và rounding riêng.

## 9. Parse chuỗi số theo Locale

Với văn bản Đức:

```java
var parser = decimalFormat(Locale.GERMANY);
var value = (BigDecimal) parser.parse("1.234,56");

System.out.println(value.toPlainString()); // 1234.56
```

Đoạn trên cần `throws ParseException` hoặc khối catch phù hợp. Vì `decimalFormat` gọi `setParseBigDecimal(true)`, giá trị parse có kiểu `BigDecimal`.

### Không thử Locale ngẫu nhiên đến khi parser báo thành công

Một parser số có thể mặc định chấp nhận input **lenient** và tiêu thụ **chỉ phần đầu**. Ví dụ, nếu dùng quy tắc Mỹ để parse `"1.234,56"`, không được mặc định rằng chắc chắn có lỗi thay vì một giá trị sai hoặc parse dở. Chọn Locale theo **hợp đồng của dữ liệu** — metadata của nhà cung cấp, vùng nhập liệu, cấu hình export hoặc ngôn ngữ của trường nhập.

Với dữ liệu tài chính, giá trị sai còn nguy hiểm hơn một exception rõ ràng.

## 10. Parse hết chuỗi: `ParsePosition` và validation

`NumberFormat.parse(String)` có thể parse phần đầu hợp lệ mà **không kiểm tra toàn bộ hậu tố**. Để từ chối field có chữ thừa, dùng `ParsePosition`.

```java
static BigDecimal parseFully(String text, Locale locale) {
    var parser = decimalFormat(locale);
    var position = new ParsePosition(0);
    Number value = parser.parse(text, position);

    if (value == null || position.getIndex() != text.length()) {
        throw new IllegalArgumentException("Invalid numeric input");
    }
    return (BigDecimal) value;
}
```

Đây là phương thức minh họa có import `BigDecimal`, `Locale` và `ParsePosition`, được đặt trong chương trình độc lập ở mục 16.

Ví dụ:

```java
var format = NumberFormat.getNumberInstance(Locale.US);
var position = new ParsePosition(0);
Number n = format.parse("1,234.56 extra", position);

System.out.println(n.doubleValue());  // 1234.56
System.out.println(position.getIndex()); // 8
System.out.println(position.getIndex()
        == "1,234.56 extra".length()); // false
```

Parser lấy số từ phần đầu và dừng trước `" extra"`. Nếu đây là một trường API chỉ được chứa số, cần từ chối hậu tố.

**Giới hạn:** tiêu thụ hết chuỗi **chưa chắc đủ** cho validation cú pháp chặt. `DecimalFormat` có thể chấp nhận một số kiểu nhóm chữ số không canonical theo chế độ lenient; nếu nghiệp vụ yêu cầu chính xác từng dấu nhóm, số thập phân, dấu âm, khoảng trắng, ký hiệu tiền tệ và giới hạn giá trị, phải thêm bước kiểm tra. API `NumberFormat` trên các bản Java mới có khả năng cấu hình strict parsing ở một số trường hợp, nhưng code ví dụ Java 17+ dùng `ParsePosition` để giữ tương thích và không nhầm kiểm tra “đã parse hết” với “đúng mọi tiêu chí nghiệp vụ”.

## 11. `Scanner.useLocale`: đọc token số và giải mã ký tự tách riêng

`Scanner` cho phép cấu hình Locale của việc parse số:

```java
try (var scanner = new Scanner(
        new StringReader("1.234,56"))) {

    scanner.useLocale(Locale.GERMANY);
    BigDecimal amount = scanner.nextBigDecimal();

    System.out.println(amount.toPlainString()); // 1234.56
}
```

Đây là đoạn minh họa có import `Scanner`, `StringReader`, `Locale`, `BigDecimal`.

Nếu nguồn của Scanner đến từ **byte**, cần decode đúng **trước khi** đưa cho parser số:

```java
byte[] encoded = "1.234,56".getBytes(StandardCharsets.UTF_8);

try (var reader = new InputStreamReader(
            new ByteArrayInputStream(encoded),
            StandardCharsets.UTF_8);
     var scanner = new Scanner(reader)) {

    scanner.useLocale(Locale.GERMANY);
    System.out.println(scanner.nextBigDecimal()); // 1234.56
}
```

Đây là đoạn minh họa trong phương thức có `throws IOException` vì đóng `InputStreamReader` trong `try-with-resources` có thể ném ngoại lệ. Các import tương ứng gồm `InputStreamReader`, `ByteArrayInputStream`, `StandardCharsets`, `Scanner` và `Locale`.

**Hai dòng quan trọng:**

- `new InputStreamReader(..., UTF_8)`: byte → ký tự.
- `scanner.useLocale(Locale.GERMANY)`: ký tự số → giá trị.

Chỉ dùng `Scanner.useLocale` mà quên charset **không** giải quyết lỗi decode; chỉ dùng charset mà quên Locale **không** giải quyết lỗi dấu thập phân.

### Vòng đời resource

Khi Scanner được đóng, nó có thể đóng Reader bên dưới. Cần thống nhất ai sở hữu input; nếu input là `System.in` hoặc Reader do framework cấp, không tự ý đóng nếu hợp đồng không cho phép. Ví dụ độc lập dùng `ByteArrayInputStream` nội bộ, do đó chủ động đóng tài nguyên là phù hợp.

## 12. `Double.parseDouble` và `BigDecimal(String)` không áp dụng Locale

Một số API parse số có cú pháp **độc lập Locale**:

```java
System.out.println(Double.parseDouble("1234.56")); // 1234.56
System.out.println(new BigDecimal("1234.56"));      // 1234.56

// Double.parseDouble("1.234,56"); // NumberFormatException
// new BigDecimal("1.234,56");      // NumberFormatException
```

Đoạn minh họa cần import `BigDecimal`. Không có chuyện `Locale.setDefault(Locale.GERMANY)` làm constructor `BigDecimal(String)` tự động hiểu dấu phẩy thập phân.

Bảng lựa chọn:

| Mục tiêu | API nên dùng |
| --- | --- |
| Dữ liệu máy–máy ở cú pháp thập phân cố định như `1234.56` | `BigDecimal(String)` hoặc `Double.parseDouble` khi phù hợp |
| Dữ liệu số nhập theo quy tắc vùng | `NumberFormat`, `DecimalFormat`, `Scanner.useLocale` |
| Chuỗi số hiển thị theo vùng | `NumberFormat.format` hoặc `String.format(Locale, ...)` |
| Byte từ file cần chuyển thành ký tự | `InputStreamReader(..., Charset)`, `Files.newBufferedReader` |
| Ký tự cần mã hóa sang file | `OutputStreamWriter(..., Charset)`, `Files.newBufferedWriter` |

### Với JSON và giao thức

Các giao thức như JSON có **ngữ pháp số riêng**, không tự động dùng dấu phân cách theo Locale giao diện. Ví dụ giá trị số JSON thường có dạng `1234.56`, không phải một số `1.234,56` không có dấu nháy. Chọn parser và serializer theo đặc tả giao thức, không thay bằng formatter giao diện người dùng.

## 13. Vì sao nên dùng `BigDecimal` khi cần chính xác thập phân?

`double` biểu diễn số dấu phẩy động nhị phân, không biểu diễn chính xác mọi giá trị thập phân như `0.1`. Nếu nghiệp vụ cần cộng tiền hoặc tính toán decimal chính xác theo chính sách xác định, `BigDecimal` phù hợp hơn:

```java
BigDecimal first = new BigDecimal("0.10");
BigDecimal second = new BigDecimal("0.20");

System.out.println(first.add(second).toPlainString()); // 0.30
```

**Lưu ý:** `new BigDecimal(0.1)` có thể tạo giá trị phản ánh chi tiết biểu diễn nhị phân của `double`. Nếu muốn giá trị decimal do người dùng nhập, hãy parse từ **văn bản** với Locale đúng, hoặc dùng chuỗi canonical khi giao thức đã chuẩn hóa.

Quy trình bền vững:

- **Đầu vào:** decode đúng charset → parse thành `BigDecimal`.
- **Trong hệ thống:** lưu/tính với số, không giữ dấu phân nhóm nghìn như một phần của giá trị.
- **Đầu ra:** format theo Locale người nhận → encode theo charset của đích.

Không dùng chuỗi `"1.234,56"` để so sánh lớn nhỏ theo thứ tự từ vựng hoặc cộng bằng phép nối chuỗi.

## 14. Mặc định của môi trường không phải hợp đồng dữ liệu

Một số API có overload không truyền `Charset` hoặc `Locale`:

```java
NumberFormat implicit = NumberFormat.getNumberInstance();
NumberFormat explicit = NumberFormat.getNumberInstance(Locale.GERMANY);
```

`implicit` dựa trên Locale mặc định thích hợp, có thể khác giữa máy nhà phát triển, CI và server; `explicit` rõ ràng hơn về quy tắc số.

Về charset: Java hiện đại (JDK 18+ theo JEP 400) sử dụng UTF-8 làm default charset của nhiều API, nhưng các luồng standard I/O có thể có cấu hình encoding riêng. Dù vậy, khi xử lý file/protocol cụ thể, **truyền `StandardCharsets.UTF_8` theo hợp đồng** giúp mã rõ ràng và không phụ thuộc môi trường.

**Không dùng global mutable defaults để xử lý từng request:**

```java
// Tránh trong ứng dụng server đa luồng chỉ để parse một request:
// Locale.setDefault(Locale.GERMANY);
```

Việc thay đổi default Locale ảnh hưởng nhiều chỗ khác trong ứng dụng. Thay vào đó truyền `Locale.GERMANY` cho parser/formatter ở request đó.

Tương tự, đừng đổi hệ thống mặc định encoding chỉ để “sửa” một file có charset đã được chỉ định. Sửa tại **điểm decode/encode** của file.

## 15. Ghi file, CSV và dữ liệu có quy ước thập phân

### Ghi văn bản UTF-8 có số hiển thị theo Đức

```java
BigDecimal amount = new BigDecimal("1234.56");
String localized = decimalFormat(Locale.GERMANY).format(amount);

Path path = Path.of("report.txt");

try (Writer writer = Files.newBufferedWriter(
        path, StandardCharsets.UTF_8)) {
    writer.write("Betrag: ");
    writer.write(localized);
}
```

Đây là đoạn minh họa trong phương thức có import và xử lý `IOException`. Chuỗi đọc lại đúng UTF-8 có dạng `Betrag: 1.234,56`. File Writer mã hóa văn bản **đã định dạng**; không tự thay dấu thập phân.

### Tách CSV phải tuân theo quy tắc quote

Nếu CSV dùng dấu phẩy làm delimiter trong khi field số theo Locale Đức cũng chứa dấu phẩy:

```text
id,amount
A,"1.234,56"
```

Thì `String.split(",")` không đủ để phân tích CSV có quote và escape. Dùng CSV parser hiểu cấu trúc file, lấy đúng field `amount` rồi parse field theo Locale được giao thức quy định. **Charset không giải quyết xung đột dấu delimiter với dấu thập phân**.

### Khác biệt khi báo cáo qua file và hiển thị trên UI

- File trao đổi với máy khác nên có **schema** và quy ước số cố định.
- Báo cáo dành cho người dùng có thể cần locale-sensitive formatting.
- Cả hai có thể dùng UTF-8.
- Đừng tạo field số của JSON bằng `NumberFormat(Locale.GERMANY)` nếu schema yêu cầu số JSON theo cú pháp cố định.

## 16. Chương trình Java 17+ biên dịch và chạy độc lập

Tạo tệp **`CharsetLocaleNumberDemo.java`**:

```java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStreamReader;
import java.io.OutputStreamWriter;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Scanner;

public class CharsetLocaleNumberDemo {
    static DecimalFormat decimalFormat(Locale locale) {
        var symbols = DecimalFormatSymbols.getInstance(locale);
        var format = new DecimalFormat("#,##0.00", symbols);
        format.setParseBigDecimal(true);
        return format;
    }

    static BigDecimal parseFully(String text, Locale locale) {
        var parser = decimalFormat(locale);
        var position = new ParsePosition(0);
        Number value = parser.parse(text, position);

        if (value == null || position.getIndex() != text.length()) {
            throw new IllegalArgumentException(
                    "Invalid numeric input for locale: " + locale);
        }
        return (BigDecimal) value;
    }

    static BigDecimal scannerFromUtf8(String numericText, Locale locale)
            throws IOException {
        byte[] encoded = numericText.getBytes(StandardCharsets.UTF_8);
        try (var reader = new InputStreamReader(
                    new ByteArrayInputStream(encoded),
                    StandardCharsets.UTF_8);
             var scanner = new Scanner(reader)) {

            scanner.useLocale(locale);
            return scanner.nextBigDecimal();
        }
    }

    public static void main(String[] args) throws Exception {
        var amount = new BigDecimal("1234.56");
        var usText = decimalFormat(Locale.US).format(amount);
        var deText = decimalFormat(Locale.GERMANY).format(amount);

        System.out.println("usText=" + usText);
        System.out.println("deText=" + deText);
        System.out.println("usParsed="
                + parseFully(usText, Locale.US).toPlainString());
        System.out.println("deParsed="
                + parseFully(deText, Locale.GERMANY).toPlainString());
        System.out.println("sameNumber="
                + (parseFully(usText, Locale.US).compareTo(
                        parseFully(deText, Locale.GERMANY)) == 0));

        String note = "Số tiền: " + deText + " €";
        byte[] utf8 = note.getBytes(StandardCharsets.UTF_8);
        String correctlyDecoded = new String(
                utf8, StandardCharsets.UTF_8);
        String wronglyDecoded = new String(
                utf8, StandardCharsets.ISO_8859_1);

        System.out.println("utf8RoundTrip="
                + note.equals(correctlyDecoded));
        System.out.println("wrongCharsetChanged="
                + !note.equals(wronglyDecoded));
        System.out.println("sameDecimalText="
                + correctlyDecoded.contains("1.234,56"));

        System.out.println("scannerGermany="
                + scannerFromUtf8("1.234,56",
                        Locale.GERMANY).toPlainString());
        System.out.println("scannerUS="
                + scannerFromUtf8("1,234.56",
                        Locale.US).toPlainString());

        System.out.println("doubleCanonical="
                + Double.parseDouble("1234.56"));
        try {
            Double.parseDouble("1.234,56");
        } catch (NumberFormatException expected) {
            System.out.println("doubleRejectsGermanSyntax=true");
        }

        var usParser = NumberFormat.getNumberInstance(Locale.US);
        var position = new ParsePosition(0);
        var partial = usParser.parse("1,234.56 extra", position);

        System.out.println("partialValue="
                + partial.doubleValue());
        System.out.println("partialConsumed="
                + position.getIndex());
        System.out.println("partialAtEnd="
                + (position.getIndex()
                        == "1,234.56 extra".length()));
        try {
            parseFully("1,234.56 extra", Locale.US);
        } catch (IllegalArgumentException expected) {
            System.out.println("fullParseRejectsSuffix=true");
        }

        System.out.println("stringFormatUS="
                + String.format(Locale.US, "%,.2f", amount));
        System.out.println("stringFormatDE="
                + String.format(Locale.GERMANY, "%,.2f", amount));

        var decimalSum = new BigDecimal("0.10")
                .add(new BigDecimal("0.20"));
        System.out.println("decimalSum="
                + decimalSum.toPlainString());

        var outputBytes = new ByteArrayOutputStream();
        try (var writer = new OutputStreamWriter(
                outputBytes, StandardCharsets.UTF_8)) {
            writer.write("Giá: " + deText);
        }
        String outputText = new String(
                outputBytes.toByteArray(), StandardCharsets.UTF_8);
        System.out.println("writerRoundTrip="
                + outputText.equals("Giá: 1.234,56"));
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 CharsetLocaleNumberDemo.java
java CharsetLocaleNumberDemo
```

**Stdout chính xác:**

```text
usText=1,234.56
deText=1.234,56
usParsed=1234.56
deParsed=1234.56
sameNumber=true
utf8RoundTrip=true
wrongCharsetChanged=true
sameDecimalText=true
scannerGermany=1234.56
scannerUS=1234.56
doubleCanonical=1234.56
doubleRejectsGermanSyntax=true
partialValue=1234.56
partialConsumed=8
partialAtEnd=false
fullParseRejectsSuffix=true
stringFormatUS=1,234.56
stringFormatDE=1.234,56
decimalSum=0.30
writerRoundTrip=true
```

### Phân tích kết quả

1. `usText` và `deText` có cùng giá trị `1234.56` nhưng khác dấu thập phân và dấu nhóm nghìn.
2. `parseFully` dùng Locale tương ứng để đưa hai chuỗi về `BigDecimal` giống nhau.
3. `utf8RoundTrip=true` xác nhận đúng cặp mã hóa/giải mã; `wrongCharsetChanged=true` mô tả tác động của charset sai.
4. `scannerGermany` và `scannerUS` đều parse đúng số sau khi dùng Reader UTF-8 và Locale phù hợp.
5. `Double.parseDouble` chỉ chấp nhận cú pháp dạng canonical đã được API quy định, không tự nhận dấu phẩy thập phân Đức.
6. Parser `NumberFormat` có thể tiêu thụ `8` ký tự của `"1,234.56 extra"`, để lại hậu tố. `parseFully` từ chối hậu tố.
7. `String.format` cho chuỗi số theo locale, còn `BigDecimal` làm phép cộng `0.10 + 0.20 = 0.30` đúng độ chính xác decimal.
8. `writerRoundTrip=true` chứng minh có thể format số theo Đức rồi mã hóa văn bản sang UTF-8 và đọc lại đúng.

Ví dụ không dùng charset mặc định, không thay đổi Locale toàn cục, không in kết quả tiền tệ phụ thuộc CLDR/provider, và không cần đọc/ghi file ngoài.

## 17. Những lỗi thường gặp và cách sửa

### Lỗi A: “Đổi sang UTF-8 sẽ khiến `1,234.56` thành `1.234,56`”

Không. UTF-8 là cách mã hóa ký tự, không phải formatter số.

**Sửa:** dùng `NumberFormat`/`DecimalFormat` theo Locale mong muốn, rồi mới encode bằng UTF-8.

### Lỗi B: “Locale sẽ sửa được chuỗi đã decode sai charset”

Nếu bytes UTF-8 bị giải mã sai, chữ tiếng Việt có thể hỏng. Locale không tái giải mã byte.

**Sửa:** dùng đúng Charset ngay khi tạo Reader/đọc bytes.

### Lỗi C: Dùng `Double.parseDouble("1.234,56")`

API này không chấp nhận cú pháp dấu phẩy thập phân địa phương.

**Sửa:** dùng parser locale-aware cho input địa phương, hoặc dùng chuỗi số máy–máy có dấu `.` chuẩn.

### Lỗi D: Chọn sai Locale mà parser vẫn trả Number

Một parser lenient có thể parse phần đầu và bỏ phần còn lại hoặc diễn giải sai dấu phân nhóm.

**Sửa:** xác định Locale nguồn, dùng `ParsePosition` kiểm tra tiêu thụ hết và áp dụng validation nghiệp vụ cần thiết.

### Lỗi E: Gộp giá trị số với chuỗi hiển thị

Không dùng `"1.234,56"` như đối tượng tính toán. **Sửa:** parse vào `BigDecimal`, lưu số, format ra chuỗi khi hiển thị.

### Lỗi F: Dùng `new BigDecimal(0.1)` cho giá tiền

`double` có thể chứa sai số biểu diễn nhị phân. **Sửa:** dùng `new BigDecimal("0.1")` hoặc parse BigDecimal từ text.

### Lỗi G: Dùng `Locale.getDefault()` trong API có input quốc tế

Server/CI/máy cá nhân có thể có locale khác; request từ các quốc gia cũng khác.

**Sửa:** truyền Locale từ hợp đồng request hoặc dùng định dạng protocol cố định độc lập locale.

### Lỗi H: Chia CSV bằng dấu phẩy thủ công

Dấu phẩy có thể nằm trong field được quote, kể cả số Đức. **Sửa:** dùng CSV parser và sau đó parse từng trường theo quy ước số.

### Lỗi I: Dùng chung `DecimalFormat` mutable giữa thread

`NumberFormat` và `DecimalFormat` thường không synchronized. **Sửa:** mỗi tác vụ dùng formatter riêng hoặc đồng bộ truy cập nếu thật sự cần chia sẻ.

### Lỗi J: Cho rằng formatter hai chữ số làm tròn cả `BigDecimal` gốc

Mẫu định dạng có thể làm tròn **chuỗi kết quả**, không biến đổi object nguồn. **Sửa:** tách rõ policy tính toán và policy trình bày.

### Lỗi K: Test currency symbol/spacing không tính khác biệt dữ liệu locale

Các locale provider và bản JDK có thể thay đổi chi tiết spacing/ký hiệu. **Sửa:** kiểm kết quả theo hợp đồng đã chọn, không giả định mọi JDK sẽ sinh đúng cùng ký hiệu.

### Lỗi L: Tự đổi `Locale.setDefault(...)` khi xử lý nhiều request

Đây là trạng thái mặc định ảnh hưởng phạm vi ứng dụng, có thể gây hành vi khó dự đoán trong hệ thống đa luồng.

**Sửa:** đặt Locale riêng cho parser/formatter tại request.

## 18. Checklist triển khai

Trước khi đọc hoặc ghi số theo địa phương:

1. **Nguồn byte là gì?** File, mạng, console hay một String đã được decode?
2. **Charset được khai báo ở đâu?** UTF-8 hay encoding do đối tác cung cấp?
3. **Text đã đúng chưa?** Kiểm ký tự có dấu/ngoài ASCII để phát hiện mojibake.
4. **Quy tắc số là gì?** Mỹ, Đức, hay cú pháp số cố định của giao thức?
5. **Có ký hiệu tiền tệ, phần trăm, đơn vị hoặc grouping không?**
6. **Có cần số thập phân chính xác không?** Nếu có, ưu tiên `BigDecimal`.
7. **Có kiểm parse hết toàn bộ string không?** `ParsePosition` giúp phát hiện suffix.
8. **Đã kiểm thêm cú pháp strict/domain chưa?** Khoảng trắng, số âm, grouping, scale, giới hạn giá trị.
9. **Có tách định dạng UI khỏi dữ liệu lưu trữ/API không?**
10. **Có cấu hình Charset và Locale tường minh không?** Tránh phụ thuộc default.
11. **Nếu dùng Scanner byte stream, Reader đã decode đúng chưa?**
12. **Parser/formatter có bị nhiều thread dùng chung không?**
13. **Nếu xuất CSV, quoted fields có được parse đúng không?**
14. **Nếu chạy CI trên locale khác, test có còn đúng không?**
15. **Nếu format số rồi ghi file, charset ở Writer có khớp hợp đồng file không?**

## 19. Bài tập và đáp án

**Câu 1.** UTF-8 quyết định dấu thập phân của chuỗi số không?

**Câu 2.** `Locale.GERMANY` có tự đọc đúng byte UTF-8 từ file không?

**Câu 3.** Giá trị `1234.56` thường định dạng khác nhau thế nào ở Mỹ và Đức?

**Câu 4.** Nếu file UTF-8 được đọc bằng charset sai, đổi Locale có phục hồi chữ có dấu không?

**Câu 5.** `Double.parseDouble("1.234,56")` có chấp nhận cú pháp Đức không?

**Câu 6.** Khi nào `Scanner.useLocale(Locale.GERMANY)` cần kết hợp `InputStreamReader(..., UTF_8)`?

**Câu 7.** Vì sao `NumberFormat.parse(...)` trả về Number chưa đủ để xác nhận toàn bộ input hợp lệ?

**Câu 8.** `ParsePosition` tiêu thụ hết chuỗi có bảo đảm grouping/scale đúng mọi quy tắc nghiệp vụ không?

**Câu 9.** Nên lưu `"1.234,56"` hay `BigDecimal("1234.56")` để tính toán?

**Câu 10.** Dùng `new BigDecimal(0.1)` có thể mang rủi ro gì?

**Câu 11.** Vì sao file CSV có `"1.234,56"` không nên được tách bằng `String.split(",")`?

**Câu 12.** Có thể ghi file UTF-8 nhưng định dạng số theo cả Mỹ lẫn Đức được không?

**Câu 13.** Vì sao nên truyền Locale explicit cho `NumberFormat` trên server đa ngôn ngữ?

**Câu 14.** Có nên tái sử dụng một `DecimalFormat` mutable trên nhiều thread không?

**Đáp án:**

1. Không; charset chỉ quy định cách biểu diễn byte/ký tự.
2. Không; phải chọn Charset đúng khi giải mã.
3. Mỹ: `1,234.56`; Đức: `1.234,56`.
4. Không; phải decode lại đúng từ byte gốc.
5. Không; `Double.parseDouble` không tự dùng quy tắc dấu phẩy theo Locale.
6. Khi dữ liệu nguồn là byte UTF-8 nhưng cú pháp số theo Đức; hai cấu hình có nhiệm vụ khác nhau.
7. Vì parser có thể chỉ lấy tiền tố hợp lệ và bỏ suffix.
8. Chưa; cần thêm validation nghiêm ngặt nếu domain yêu cầu.
9. Lưu số `BigDecimal`; format chuỗi tại ranh giới hiển thị.
10. Có thể nhận sai số nhị phân từ `double`.
11. Vì dấu phẩy có thể nằm trong quoted field của CSV.
12. Có; Charset và Locale là hai tầng độc lập.
13. Tránh phụ thuộc locale của máy chủ hoặc thay đổi global default.
14. Không nếu không đồng bộ; ưu tiên instance riêng hoặc thiết kế concurrency phù hợp.

## 20. Tóm tắt và nguồn còn áp dụng

- **Charset:** byte ↔ ký tự. **Locale:** quy ước vùng cho số ↔ chuỗi.
- Đọc đúng: **decode bằng charset tường minh → parse theo Locale phù hợp**.
- Ghi đúng: **format theo Locale → encode bằng charset của đích**.
- `NumberFormat`/`DecimalFormat`/`Scanner.useLocale` hỗ trợ chuỗi số địa phương.
- `Double.parseDouble` và `BigDecimal(String)` không tự áp dụng dấu thập phân địa phương.
- Cần `BigDecimal` cho độ chính xác thập phân và validation để tránh parse dở.
- Không phụ thuộc default locale/charset, không chia sẻ formatter mutable giữa các thread và không dùng CSV split thủ công khi có quote.
- Các kỹ thuật này đều còn phù hợp trong Java hiện đại; dùng Java 17+ cho chương trình mẫu.

Tài liệu tham khảo chính thức:

1. [Java SE 27 — Charset](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): quan hệ giữa byte và ký tự Java.
2. [Java SE 27 — Locale](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Locale.html): các API locale-sensitive, bao gồm biểu diễn số.
3. [Java SE 26 — NumberFormat](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/NumberFormat.html): định dạng/parse số theo Locale, ParsePosition và đồng bộ hóa.
4. [Java SE 26 — DecimalFormat](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/text/DecimalFormat.html): pattern số, DecimalFormatSymbols và parse BigDecimal.
5. [Java SE 26 — Scanner.useLocale](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Scanner.html#useLocale(java.util.Locale)): locale khi parse số với Scanner.
6. [Java SE 27 — StandardCharsets](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html): UTF-8 và các charset chuẩn.
7. [OpenJDK — JEP 400](https://openjdk.org/jeps/400): UTF-8 mặc định trong Java hiện đại và ý nghĩa của việc chỉ định Charset.
