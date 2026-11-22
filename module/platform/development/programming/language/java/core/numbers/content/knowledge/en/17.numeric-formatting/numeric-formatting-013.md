# Không dùng chuỗi đã định dạng cho người đọc làm dạng trao đổi dữ liệu mặc định

Trong Java, một **giá trị số** và một **chuỗi trình bày giá trị số** không phải cùng một loại dữ liệu. Khi hiển thị, ứng dụng có thể dùng dấu phân nhóm hàng nghìn, dấu thập phân theo ngôn ngữ, ký hiệu tiền tệ, số chữ số làm tròn hay đơn vị đo để con người dễ đọc. Nhưng nếu mặc định dùng chính chuỗi **đã định dạng cho người đọc** để lưu file, truyền API hoặc tích hợp với hệ thống khác, dữ liệu có thể **bị đọc sai, không parse được hoặc mất độ chính xác**.

```java
double amount = 1_234_567.89;

System.out.println(String.format(
        java.util.Locale.US, "%,.2f", amount));
// 1,234,567.89

System.out.println(String.format(
        java.util.Locale.GERMANY, "%,.2f", amount));
// 1.234.567,89

System.out.println(Double.toString(amount));
// 1234567.89
```

Ba chuỗi biểu diễn cùng một `double` đầu vào, nhưng hai chuỗi đầu phục vụ **con người ở các locale khác nhau**. Chuỗi thứ ba là cách biểu diễn số `double` ổn định theo quy tắc Java, không phụ thuộc locale, tiện hơn cho một số hợp đồng trao đổi văn bản đã được **quy định rõ**.

**Quy tắc chính:** dữ liệu trao đổi giữa chương trình phải có **schema và định dạng máy** được định nghĩa tường minh. Định dạng trình bày giao diện (human display format) không nên trở thành wire format mặc định chỉ vì người dùng nhìn thấy nó.

## 1. Phân biệt value, presentation và wire representation

Ba tầng thường gặp:

| Tầng | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Giá trị nội bộ** | Hệ thống đang tính trên kiểu và giá trị nào? | `long 1234567L`, `double 1234.5`, `BigDecimal("1234.50")` |
| **Trình bày cho người đọc** | Người dùng ở locale nào, muốn bao nhiêu chữ số, đơn vị gì? | `"1.234,50"`, `"1,234.50"`, `"1 234,50 €"` |
| **Dữ liệu trao đổi** | Bên nhận sẽ đọc chính xác theo schema nào? | JSON number `1234.5`, JSON string `"1234.50"` với quy tắc decimal, hoặc binary int64 |

**Định dạng cho người đọc** là một phép biến đổi từ giá trị thành chuỗi để hiển thị. Nó có thể làm tròn, thêm dấu phân nhóm, thay ký hiệu decimal hoặc đưa thêm chữ. Một khi đã làm tròn cho UI, việc parse ngược chưa chắc phục hồi giá trị trước khi làm tròn.

**Định dạng trao đổi** cần xác định rõ tập ký tự, kiểu dữ liệu, signedness, đơn vị, cách biểu diễn phần lẻ, phiên bản schema, cách biểu diễn giá trị đặc biệt và quy tắc validation. Đây là hợp đồng giữa bên phát và bên nhận, **không phải** hiệu ứng phụ của cài đặt locale trên máy.

### Ví dụ điển hình

Ứng dụng có giá trị `1234.5`:

```text
Internal double:             1234.5
Hiển thị English (US):       1,234.50
Hiển thị German (Germany):   1.234,50
Wire decimal text (ví dụ):   1234.5
```

Nếu một API nhận chuỗi `"1.234,50"` nhưng giả định đó là số decimal dùng dấu chấm, nó có thể từ chối, cắt một phần chuỗi hoặc diễn giải sai. Nếu format cho UI vô tình trở thành dữ liệu lưu trữ, chỉ cần đổi locale của server hoặc người dùng đã đủ tạo lỗi tương thích.

## 2. Dấu phân nhóm và dấu thập phân không có nghĩa toàn cầu

Các ký tự dấu phẩy và dấu chấm có vai trò khác nhau tùy locale.

| Giá trị | Ví dụ US | Ví dụ Germany |
| ---: | --- | --- |
| 1234.5 với 2 chữ số lẻ | `1,234.50` | `1.234,50` |
| 1234567.89 với 2 chữ số lẻ | `1,234,567.89` | `1.234.567,89` |
| 1000 nếu phân nhóm | `1,000` | `1.000` |

Chuỗi `"1,234"` **mơ hồ** nếu không có locale: có thể được hiểu là một nghìn hai trăm ba mươi tư trong hệ US, hoặc một phẩy hai ba bốn trong hệ dùng dấu phẩy thập phân. Chuỗi `"1.234"` cũng có tình huống ngược lại.

Không chỉ có dấu chấm/phẩy: một số locale dùng khoảng trắng, khoảng trắng không ngắt dòng hoặc ký tự Unicode riêng làm dấu phân nhóm. Tiền tệ còn có ký hiệu và quy tắc vị trí ký hiệu khác nhau. Vì vậy, regex đơn giản để bỏ dấu phẩy hoặc dấu chấm **không phải một parser quốc tế an toàn**.

### Định dạng bằng `String.format`

```java
double value = 1_234_567.89;

String us = String.format(
        java.util.Locale.US, "%,.2f", value);
String de = String.format(
        java.util.Locale.GERMANY, "%,.2f", value);
```

Trong định dạng kiểu `%,.2f`:
- `,` là **cờ grouping** của `Formatter`; ký tự phân nhóm thực tế phụ thuộc locale.
- `.2` yêu cầu hai chữ số sau dấu thập phân trong chuỗi hiển thị.
- `f` yêu cầu định dạng số thực dạng fixed-point.
- `Locale.US` hoặc `Locale.GERMANY` quyết định ký tự hiển thị.

Mẫu `%,.2f` **không có nghĩa đầu ra luôn dùng dấu phẩy phân nhóm và dấu chấm thập phân**. Nó diễn đạt chính sách trình bày thông qua locale.

Đối với giao thức, chỉ dùng `String.format` nếu giao thức **quy định đúng** locale, số chữ số, quy tắc làm tròn, grouping và cách parse. Không tự dùng output của formatter UI làm nội dung mặc định cho JSON, CSV hay cơ sở dữ liệu.

## 3. Tác hại của việc parse chuỗi trình bày bằng parser máy

`Double.parseDouble` hiểu cú pháp số thực của Java theo hợp đồng riêng, **không** nhận định dạng phân nhóm số theo locale:

```java
double original = 1_234_567.89;
String shown = "1.234.567,89";

// Double.parseDouble(shown); // NumberFormatException.
double recovered = Double.parseDouble(
        Double.toString(original)); // Hoạt động.
```

`Double.parseDouble` không phải bộ parser tất cả các kiểu hiển thị địa phương. `Integer.parseInt("1,000")` cũng không hoạt động dù `"1,000"` trông rất bình thường với người dùng US.

Cần phân biệt:
- **`Double.parseDouble`/`Integer.parseInt`**: parser giá trị số theo các cú pháp riêng của Java, không tự nhận grouping locale.
- **`NumberFormat.parse`/`DecimalFormat.parse`**: parser theo quy tắc trình bày và locale; phù hợp khi nhận **input dành cho con người** với quy tắc cụ thể.
- **Parser của chuẩn dữ liệu**: ví dụ JSON parser, CSV reader + codec field, binary decoder; phải tuân theo **schema dữ liệu trao đổi**.

Nếu dữ liệu thực sự do người dùng gõ theo locale, việc dùng `NumberFormat` có thể hợp lý. Nhưng kết quả parse nên được **chuẩn hóa thành kiểu số** trước khi đi tiếp tới lớp xử lý và lưu trữ.

## 4. `NumberFormat.parse` có thể đọc được tiền tố hợp lệ rồi dừng

Một bẫy ít được để ý: parser định dạng cho người đọc có thể **chấp nhận một phần đầu chuỗi** mà không tiêu thụ hết dữ liệu. Chẳng hạn:

```java
java.text.NumberFormat german =
        java.text.NumberFormat.getNumberInstance(
                java.util.Locale.GERMANY);

java.text.ParsePosition position = new java.text.ParsePosition(0);
String input = "1.234,50junk";
Number number = german.parse(input, position);

System.out.println(number);              // 1234.5
System.out.println(position.getIndex()); // 8
System.out.println(input.length());      // 12
```

Ở đây chuỗi có phần cuối `"junk"`. Một kết quả `Number` khác null **không đồng nghĩa toàn bộ input đã hợp lệ**. Muốn validator chặt chẽ khi nhận dữ liệu do người dùng nhập, cần kiểm tra:

```java
boolean allConsumed = number != null
        && position.getIndex() == input.length();
```

Dù tiêu thụ hết chuỗi, còn phải kiểm tra miền giá trị, kiểu số trả về, ký tự cho phép, giới hạn độ dài và điều kiện nghiệp vụ. `NumberFormat` có thể dùng các chế độ parse khác nhau như `setParseIntegerOnly` hoặc `DecimalFormat.setParseBigDecimal`; kiểu `Number` trả về không nhất thiết là `BigDecimal` hay `Double` duy nhất.

**Không sử dụng parser trình bày địa phương làm bộ kiểm tra wire format không khai báo locale.** Khi parsing phụ thuộc cấu hình, hai máy/phiên bản hoặc hai người dùng có thể hiểu cùng chuỗi theo cách khác nhau.

## 5. Xác định wire format bằng schema rõ ràng

Một schema trao đổi số nguyên/số thực thường cần quy định:

1. **Loại giá trị:** signed 32-bit, signed 64-bit, unsigned, decimal cố định, binary float, phần trăm, hay định danh?
2. **Kiểu của trường:** JSON number, JSON string, CSV text field, binary integer/float, database numeric column?
3. **Cú pháp:** dấu thập phân `.` hay `,`, exponent có được phép không, có grouping không, có dấu `+` không?
4. **Độ chính xác và miền:** giá trị tối thiểu/tối đa, có cho số thập phân vô hạn hay độ phân giải cố định không?
5. **Làm tròn:** cho phép làm tròn ở lớp nào, theo `RoundingMode` nào nếu dùng decimal?
6. **Giá trị đặc biệt:** null, thiếu field, NaN, ±Infinity, ±0 được biểu diễn thế nào?
7. **Đơn vị:** giá trị là đồng, xu, giây, mili giây, mét, độ hay một đại lượng không đơn vị?
8. **Tương thích phiên bản:** khi schema đổi đơn vị, cách parse, kiểu hoặc ký hiệu, làm sao client cũ nhận ra?
9. **Giới hạn bảo mật:** độ dài đầu vào, độ lớn số mũ, ký tự Unicode, validation và thông báo lỗi.

Ví dụ một hợp đồng text decimal đơn giản có thể viết:

```text
Field: amount_decimal
Type on wire: JSON string
Grammar: optional ASCII '-' followed by digits, optional '.' and digits
Grouping: forbidden
Locale: fixed, not taken from client/server default
Precision/range: agreed by application schema
Example: "1234.50"
Java receiver: new BigDecimal(value) after validation
```

Đây là **định dạng do hệ thống tự quy định**, không phải chuẩn chung bắt buộc của mọi API. Điều quan trọng là cả hai phía hiểu cùng hợp đồng.

Một định dạng khác có thể dùng JSON number `1234.5` trực tiếp. Nó phù hợp nếu tất cả bên nhận có thể bảo toàn miền và độ chính xác cần thiết. Không có một cách biểu diễn tối ưu cho mọi nhu cầu.

## 6. `toString` và `parseXxx`: lựa chọn tốt hơn formatter UI khi hợp đồng phù hợp

Đối với số nguyên có dấu:

```java
int i = -42;
long l = 9_000_000_000L;

String encodedInt = Integer.toString(i);  // "-42"
String encodedLong = Long.toString(l);    // "9000000000"

int decodedInt = Integer.parseInt(encodedInt);
long decodedLong = Long.parseLong(encodedLong);
```

Các API này không tự thêm grouping, ký hiệu tiền tệ hay thay dấu thập phân theo default locale. Chúng có thể dùng trong **schema decimal ASCII có dấu** cho `int`/`long` nếu bên nhận đồng ý về cú pháp và miền.

Với cơ số khác 10:

```java
String hex = Integer.toString(255, 16);  // "ff"
int recovered = Integer.parseInt(hex, 16); // 255
```

`radix` cũng phải là một phần hợp đồng. `Integer.toString(value,16)` không tự tạo `0x`; parser `parseInt(text,16)` không tự bỏ `0x`. Không đưa chuỗi với tiền tố UI vào parser không hỗ trợ tiền tố ấy.

### Signed và unsigned là hai quy ước riêng

`Integer.toUnsignedString(-1)` trả `"4294967295"`, còn `Integer.toString(-1)` trả `"-1"`. Chuỗi khác dù mẫu bit `int` giống nhau. Nếu wire schema là unsigned 32 bit, bên nhận cần phân tích với `Integer.parseUnsignedInt` (hoặc mô hình số rộng hơn) và biết đây là giá trị unsigned.

Với `long`, `Long.toUnsignedString` và `Long.parseUnsignedLong` diễn đạt bit 64 theo nghĩa không dấu. Đừng mô tả số âm dạng hex “ffffffff” rồi gọi parser signed mặc định, vì có thể vượt miền và thất bại.

### `Double.toString` là formatter cho giá trị binary64, không phải tiền tệ

`Double.toString(double)` trả một biểu diễn số thực decimal **không phụ thuộc locale** cho giá trị binary64. Với số hữu hạn, chuỗi được thiết kế để parse bằng `Double.parseDouble` và nhận lại cùng giá trị `double`.

```java
double sample = 0.1 + 0.2;
String text = Double.toString(sample);

System.out.println(text); // 0.30000000000000004
System.out.println(Double.parseDouble(text) == sample); // true
```

Điều đó bảo toàn **giá trị nhị phân hiện có**, không chứng minh `0.1 + 0.2` là phép tính thập phân chính xác. `Double.toString` còn có dạng chuỗi `"NaN"`, `"Infinity"`, `"-Infinity"` cho giá trị đặc biệt, **không hợp lệ làm JSON number theo chuẩn JSON**.

Vì vậy, trong ứng dụng trao đổi JSON, dùng một **JSON serializer** đúng chuẩn, với chính sách xử lý số không hữu hạn; không nối chuỗi tùy tiện từ `Double.toString` để dựng JSON.

## 7. `BigDecimal`: giữ decimal có ý nghĩa nghiệp vụ

Khi dữ liệu mang nghĩa số thập phân chính xác (ví dụ lượng tiền, thuế suất, số lượng tính theo đơn vị nhỏ nhất), `BigDecimal` là một lựa chọn phổ biến. Nó khác `double` ở chỗ có thể biểu diễn chính xác số decimal như `0.1` khi được tạo từ **chuỗi decimal**.

```java
java.math.BigDecimal a = new java.math.BigDecimal("0.1");
java.math.BigDecimal b = new java.math.BigDecimal("0.2");

System.out.println(a.add(b).toPlainString()); // 0.3
```

Không xây `BigDecimal` từ chuỗi đã thêm grouping/đổi dấu thập phân:

```java
// new BigDecimal("1.234,50"); // NumberFormatException.

java.math.BigDecimal amount =
        new java.math.BigDecimal("1234.50");

System.out.println(amount.toPlainString()); // 1234.50
System.out.println(amount.scale());         // 2
```

`BigDecimal.toPlainString()` không dùng notation số mũ; `BigDecimal.toString()` có thể chọn cách biểu diễn exponent khi phù hợp:

```java
java.math.BigDecimal x = new java.math.BigDecimal("1E+7");
System.out.println(x.toString());      // 1E+7
System.out.println(x.toPlainString()); // 10000000
```

### Chọn `toString` hay `toPlainString`?

- `toString()` là biểu diễn chuẩn của `BigDecimal` có thể dùng exponent, được thiết kế cho các nhu cầu biểu diễn/parse và giữ thông tin scale theo định nghĩa API.
- `toPlainString()` phù hợp với schema chỉ nhận decimal digits và dấu chấm, **không cho exponent**; nhưng dạng plain có thể dài đáng kể khi số có exponent rất lớn.
- `stripTrailingZeros()`, `setScale(...)` và các phép làm tròn có thể thay đổi scale hoặc giá trị, nên chỉ áp dụng khi **schema quy định**. Không tùy ý strip `"1234.50"` thành `"1234.5"` nếu số chữ số lẻ/scale mang ý nghĩa.

Nếu yêu cầu giữ **scale** qua round trip, chú ý `toPlainString()` với các `BigDecimal` có scale âm có thể dựng lại cùng giá trị số nhưng scale khác khi parse. Cần dùng `BigDecimal.toString` hoặc lưu cả scale/representation khi đây là thành phần của hợp đồng. Đừng dùng `toPlainString` như cách “giữ mọi metadata số” phổ quát.

### `new BigDecimal(double)` khác `new BigDecimal(String)`

`new BigDecimal(0.1)` diễn đạt chính xác giá trị **xấp xỉ nhị phân** của `double 0.1`, vì thế chuỗi decimal của nó có thể rất dài. Nếu đầu vào thực sự là số thập phân do user gõ, ưu tiên **giữ text gốc hợp lệ** và tạo bằng `new BigDecimal("0.1")` thay vì cho nó đi qua `double` trước.

`BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi chuẩn của `double` nên thường nhận `BigDecimal("0.1")`, nhưng nó **không thể phục hồi số chữ số hoặc sai số bị mất trước đó** ở dữ liệu gốc. Cần xem hợp đồng nguồn và xử lý rounding rõ ràng.

## 8. JSON: numeric token không giống chuỗi hiển thị

JSON phân biệt **number** và **string**:

```json
{
  "quantity": 12,
  "ratio": 0.125,
  "amountDecimal": "1234.50",
  "accountCode": "00042"
}
```

Đây là ví dụ một **schema có chủ đích**:
- `quantity` là numeric integer.
- `ratio` là JSON number có cú pháp thập phân của JSON, không có grouping locale.
- `amountDecimal` là JSON **string** chứa decimal text chính xác theo hợp đồng.
- `accountCode` là string vì các số 0 đầu là một phần định danh.

Với JSON, numeric token dùng dấu chấm `.` cho phần fraction theo grammar chuẩn. Chuỗi `"1.234,50"` có thể xuất hiện như một **string** nhưng **không trở thành JSON number chỉ vì đặt trong JSON**.

### NaN và Infinity

JSON không có numeric token chuẩn cho `NaN`, `Infinity` hoặc `-Infinity`. Bởi vậy:

```java
double value = Double.NaN;
System.out.println(Double.toString(value)); // NaN
```

Chuỗi `NaN` đó **không phải** JSON number hợp lệ. Khi serialize giá trị chấm động, phải quy định xử lý: từ chối, dùng null với hợp đồng riêng, hoặc dùng một enum/string trạng thái được schema mô tả. Đừng ghi `{"value": NaN}` rồi nghĩ mọi JSON parser đều đọc được.

### Giới hạn của phía nhận

Một giá trị `long` hợp lệ có thể vượt miền **số nguyên liên tiếp chính xác** của JavaScript `Number`, tức lớn hơn `2^53` về độ lớn. Ví dụ:

```java
long id = 9_007_199_254_740_993L;
System.out.println(Long.toString(id)); // 9007199254740993
System.out.println((double) id);       // 9.007199254740992E15
```

`double` không biểu diễn chính xác số nguyên này; nhiều client xử lý JSON number bằng binary64 có cùng rủi ro. Với **ID hoặc số nguyên lớn cần chính xác tuyệt đối**, có thể quy định truyền **decimal string** và parse vào `long`/`BigInteger` phù hợp ở phía nhận, thay vì JSON number tùy tiện.

Tuy nhiên, **không phải mọi số JSON phải chuyển sang string**. Numeric token vẫn là lựa chọn tự nhiên cho các số trong miền/độ chính xác đã kiểm soát, miễn hai phía dùng model tương thích.

### Tránh tự nối chuỗi JSON

Không ghép:

```java
// KHÔNG nên làm một JSON serializer tổng quát như vậy:
String json = "{\\"value\\":" + Double.toString(value) + "}";
```

Đoạn trên không kiểm tra NaN/Infinity, không xử lý object string escaping, field optional, schema hay các quy tắc serialization khác. Hãy dùng thư viện JSON phù hợp của dự án để serialize **giá trị có kiểu**, sau khi chính sách precision/finite/null đã được xác định.

## 9. CSV và các file văn bản: cần schema cho từng cột

CSV là ví dụ rõ về nguy cơ nhầm display với data. Giả sử dấu phân tách cột là dấu phẩy:

```text
id,quantity,price
42,3,1234.50
```

Một chuỗi tiền tệ hiển thị kiểu US `"1,234.50"` nếu viết thẳng vào cột price sẽ chứa **dấu phẩy có vai trò phân tách cột**. Nếu thực sự muốn lưu text có dấu phẩy, cần **CSV escaping/quoting** theo quy tắc CSV được chọn:

```text
id,quantity,price_display
42,3,"1,234.50"
```

Nhưng CSV quoting chỉ bảo vệ **cấu trúc hàng/cột**, nó **không bảo đảm** bên nhận sẽ hiểu decimal format US. Một schema ổn định thường quy định riêng rằng cột `price` có định dạng decimal với dấu chấm, không grouping và đơn vị rõ.

Nếu ứng dụng cần export CSV cho **người dùng mở trong spreadsheet**, có thể cần format theo locale và công cụ nhận. Đó là **xuất báo cáo phục vụ con người**, khác **CSV integration feed** giữa các dịch vụ. Không nên dùng cùng một export mode cho cả hai nếu hợp đồng không tương thích.

### Ký tự phân tách và ký tự số có thể xung đột

Ở locale dùng dấu phẩy thập phân, CSV dùng dấu phẩy làm delimiter càng dễ bị mơ hồ. Có nơi dùng dấu chấm phẩy làm delimiter trong file văn bản cho spreadsheet. Không tự suy rằng mọi tệp `.csv` đều có quy ước giống nhau; cần biết schema, delimiter, encoding, quoting và cách parse decimal.

### Những dữ liệu trông như số nhưng không nên chuyển sang numeric

Mã bưu chính, số chứng từ, số điện thoại, số tài khoản và ID có số 0 đầu là **chuỗi định danh**, không phải đối tượng để cộng trừ. Nếu đưa `"00042"` qua `Integer.parseInt` rồi `Integer.toString` sẽ chỉ còn `"42"`. Đừng mất thông tin vì cho rằng “ký tự toàn số thì phải lưu số”.

## 10. Lưu trữ database và thông điệp giữa dịch vụ

Cùng một nguyên tắc áp dụng cho database:

- Nếu column có ý nghĩa **số nguyên**, dùng kiểu nguyên phù hợp với miền.
- Nếu column là số decimal cần chính xác, dùng `DECIMAL`/`NUMERIC` với precision/scale rõ, và Java `BigDecimal` nếu driver/API thích hợp.
- Nếu column là mã định danh, dùng text hoặc kiểu chuyên biệt đúng ngữ nghĩa.
- Nếu giao diện muốn hiển thị tiền tệ, chỉ **format tại lớp trình bày** khi biết locale/ngôn ngữ/quy tắc.

Không nên lưu chuỗi `"1.234,50 €"` làm giá trị duy nhất của cột tiền chỉ vì UI hiển thị như vậy: truy vấn sắp xếp, lọc, tính tổng, đổi đơn vị và đổi locale sau này sẽ khó khăn hơn. Dữ liệu chuẩn hóa nên tách **giá trị, currency code, đơn vị và metadata** theo schema.

Nếu dùng JDBC, hãy dùng các setter/getter có kiểu (`setLong`, `setBigDecimal`...) phù hợp với schema/driver, thay vì `setString` một chuỗi đã format cho người đọc rồi hy vọng database nhận biết đúng.

### Tách rõ luồng dữ liệu

```text
Input của người dùng
       |
       v
Validation + parse theo locale/chính sách nhập
       |
       v
Giá trị có kiểu: int / long / BigDecimal / double
       |                         |
       |                         +--> Codec wire theo schema -> API/file/DB
       |
       +--> Formatter theo locale -> UI/report
```

Không nên cho nhánh **Formatter theo locale** chảy ngược thành nhánh **Codec wire** mà không có hợp đồng parse tương ứng và kiểm tra chính xác.

## 11. Chương trình Java 17+ chạy độc lập

Lưu tệp `HumanVsWireDemo.java`:

```java
import java.math.BigDecimal;
import java.text.DecimalFormatSymbols;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class HumanVsWireDemo {
    static String parseDoubleResult(String text) {
        try {
            return Double.toString(Double.parseDouble(text));
        } catch (NumberFormatException ex) {
            return "INVALID";
        }
    }

    public static void main(String[] args) {
        double amount = 1_234_567.89;

        System.out.println("Human US: "
                + String.format(Locale.US, "%,.2f", amount));
        System.out.println("Human DE: "
                + String.format(Locale.GERMANY, "%,.2f", amount));
        System.out.println("Machine double: "
                + Double.toString(amount));

        System.out.println("Parse human DE as double: "
                + parseDoubleResult("1.234.567,89"));
        System.out.println("Parse machine: "
                + parseDoubleResult(Double.toString(amount)));

        NumberFormat german =
                NumberFormat.getNumberInstance(Locale.GERMANY);
        ParsePosition pos = new ParsePosition(0);
        String untrusted = "1.234,50junk";
        Number parsed = german.parse(untrusted, pos);
        System.out.println("Lenient locale parse: " + parsed
                + "; consumed=" + pos.getIndex()
                + "/" + untrusted.length());

        BigDecimal exact = new BigDecimal("1234.50");
        System.out.println("Exact decimal plain: "
                + exact.toPlainString());
        System.out.println("Decimal scale: " + exact.scale());

        System.out.println("Scientific BigDecimal: "
                + new BigDecimal("1E+7").toString());
        System.out.println("Plain BigDecimal: "
                + new BigDecimal("1E+7").toPlainString());

        System.out.println("Exact decimal 0.1+0.2: "
                + new BigDecimal("0.1")
                    .add(new BigDecimal("0.2")).toPlainString());
        System.out.println("Double 0.1+0.2: "
                + Double.toString(0.1 + 0.2));

        long bigId = 9_007_199_254_740_993L;
        System.out.println("ID as long string: "
                + Long.toString(bigId));
        System.out.println("ID as double: "
                + Double.toString((double) bigId));

        System.out.println("NaN is finite? "
                + Double.isFinite(Double.NaN));
        System.out.println("Infinity is finite? "
                + Double.isFinite(Double.POSITIVE_INFINITY));
        System.out.println("German decimal code point: "
                + (int) DecimalFormatSymbols
                    .getInstance(Locale.GERMANY)
                    .getDecimalSeparator());
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 HumanVsWireDemo.java
java HumanVsWireDemo
```

Stdout trên JDK 17+ với dữ liệu locale tương ứng:

```text
Human US: 1,234,567.89
Human DE: 1.234.567,89
Machine double: 1234567.89
Parse human DE as double: INVALID
Parse machine: 1234567.89
Lenient locale parse: 1234.5; consumed=8/12
Exact decimal plain: 1234.50
Decimal scale: 2
Scientific BigDecimal: 1E+7
Plain BigDecimal: 10000000
Exact decimal 0.1+0.2: 0.3
Double 0.1+0.2: 0.30000000000000004
ID as long string: 9007199254740993
ID as double: 9.007199254740992E15
NaN is finite? false
Infinity is finite? false
German decimal code point: 44
```

`44` là mã số Unicode/ASCII của ký tự dấu phẩy (`,`). Dòng `Lenient locale parse` cho thấy parser đã đọc `"1.234,50"` nhưng **không tiêu thụ `"junk"`**; đây là lý do cần kiểm tra `ParsePosition` nếu biến nó thành validation.

Các kết quả định dạng locale hiển thị như ví dụ phụ thuộc vào **dữ liệu locale của JDK**; với giao thức lâu dài, càng không nên để cấu hình locale trở thành hợp đồng wire. Các kết quả `Double.toString`, `Long.toString` và `BigDecimal` minh họa chuỗi số không phải số đã định dạng cho UI.

## 12. Thiết kế parser / serializer theo ranh giới trách nhiệm

### Tại nơi người dùng nhập

1. Xác định ngôn ngữ/locale của người dùng và loại ô nhập.
2. Hiển thị gợi ý rõ về dấu thập phân, dấu phân nhóm và đơn vị.
3. Parse bằng bộ parser dành cho input đó; kiểm tra toàn bộ chuỗi đã tiêu thụ.
4. Xác thực miền, precision, scale, kiểu và null.
5. Biến kết quả thành **giá trị có kiểu** để tầng nghiệp vụ sử dụng.

### Tại nơi hệ thống xuất API/file

1. Chọn JSON/CSV/protobuf/SQL/... theo giao thức thật, không chọn output trực tiếp của `NumberFormat` theo cảm tính.
2. Ghi schema rõ số nguyên hay decimal, đơn vị, cách xử lý null và số đặc biệt.
3. Dùng serializer/codec tiêu chuẩn hoặc một codec được kiểm thử chặt chẽ.
4. Bảo toàn chính xác theo yêu cầu của phía nhận; chú ý giới hạn IEEE binary64 cho integer lớn.
5. Validate khi nhận ngược; **không tin** rằng mọi chuỗi đến từ hệ thống khác đều hợp lệ.
6. Kiểm thử round trip và tương thích chéo các locale/JDK/đối tác.

### Tại nơi hiển thị

1. Nhận **giá trị đã có kiểu** từ nghiệp vụ hoặc API.
2. Chọn locale người dùng, kiểu tiền tệ, quy tắc rounding và số chữ số.
3. Format thành một chuỗi để đọc, không sử dụng nó làm nguồn dữ liệu tính toán.
4. Nếu UI cần người dùng chỉnh sửa, parse trở lại **qua lớp input** với validation, không đưa chuỗi display xuyên qua các service như một “numeric value”.

Các bước tách riêng này cũng giúp test dễ hơn: codec có test tính đúng chuẩn, logic nghiệp vụ có test số học, còn UI format có test locale mà không ảnh hưởng wire protocol.

## 13. Các trường hợp đặc biệt cần ghi hợp đồng rõ

### 13.1. Làm tròn để hiển thị

`String.format(Locale.US,"%.2f",value)` có thể rút số chữ số hiển thị xuống hai chữ số phần lẻ. Nếu giá trị gốc có nhiều chữ số hơn, chuỗi hiển thị đã **mất thông tin**. Không parse lại nó để lưu thay giá trị gốc trừ khi nghiệp vụ thực sự muốn làm tròn tại bước đó.

Ví dụ giá trị `1234.567` hiển thị thành `"1,234.57"` với nhóm và 2 chữ số lẻ; parse ngược `1234.57` không thể hồi phục `1234.567`.

### 13.2. Giá trị âm không, Infinity và NaN

Trong `double` có `-0.0` và `+0.0`, cùng `NaN`/`±Infinity`. Một formatter UI có thể xử lý hoặc hiển thị chúng theo chính sách địa phương. Với JSON number chuẩn, các giá trị NaN/Infinity không hợp lệ; còn signed zero có thể cần kiểm tra nghĩa ở phía nhận. Nếu các trạng thái đặc biệt quan trọng, **schema phải định nghĩa riêng**, không chỉ dùng kết quả `toString`.

### 13.3. Precision và exponent

Một JSON number có thể chứa ký pháp exponent, nhưng bên nhận có thể chuyển nó sang binary64, `BigDecimal` hoặc kiểu số khác. Dùng `BigDecimal.toPlainString` khi hợp đồng cấm exponent, nhưng phải giới hạn độ lớn/độ dài để tránh sinh chuỗi khổng lồ từ giá trị exponent không tin cậy.

### 13.4. Đơn vị và phần trăm

Chuỗi UI `"12.5%"` là biểu diễn cho người đọc: số thật trong hệ thống có thể là `0.125`, `12.5` hoặc một giá trị có đơn vị “percent” tùy hợp đồng. Một phép xóa ký tự `%` không xác định được cách chuẩn hóa. Tương tự, `"1,2 km"` cần xử lý đơn vị, decimal locale và quy tắc đổi km sang m, không chỉ gọi `Double.parseDouble`.

### 13.5. Kiểu số nguyên rất lớn

Mã định danh `9007199254740993` vừa `long` Java nhưng vượt khoảng liên tiếp chính xác của JavaScript `Number`. Một schema có thể giữ nó như JSON string decimal. Với ứng dụng chỉ Java-to-Java sử dụng parser long chính xác và miền có kiểm soát, numeric token cũng có thể phù hợp. **Lựa chọn dựa trên toàn bộ hệ sinh thái bên nhận**, không chỉ code Java phía gửi.

## 14. Bộ test nên có khi xây định dạng trao đổi

| Nhóm test | Input/góc cạnh | Kỳ vọng |
| --- | --- | --- |
| Locale US/DE | `1234.5` | UI format khác, wire format không tùy tiện thay đổi |
| Parse human | `"1.234,50"` | Chỉ parser locale phù hợp mới nhận theo policy |
| Parse machine | `"1234.50"` | Codec decimal nhận đúng, không grouping |
| Grouping lạ | `"1,23,4.5"` | Reject nếu schema không cho grouping |
| Có dữ liệu thừa | `"1.234,50junk"` | Full-consumption validation phải từ chối |
| Precision decimal | `"0.1"` cộng `"0.2"` | BigDecimal đúng `0.3` |
| Trailing zeros/scale | `"1234.50"` | Giữ scale nếu schema yêu cầu |
| Exponent | `"1E+7"` | Định nghĩa có cho exponent không |
| Số nguyên lớn | `"9007199254740993"` | Bảo toàn trên mọi client yêu cầu exact |
| Non-finite | NaN, Infinity | Không sinh JSON numeric token không hợp lệ |
| Âm zero | `-0.0` | Xác định có cần phân biệt dấu không |
| Định danh | `"00042"` | Không làm mất số 0 đầu |
| CSV quoting | `"1,234.50"` | Trường không bị tách sai cột |
| Ký tự Unicode | NBSP, chữ số Unicode | Policy chấp nhận/từ chối rõ ràng |
| Giá trị quá dài | Nhiều nghìn chữ số/số mũ lớn | Giới hạn tài nguyên và thông báo lỗi |
| Default locale bị đổi | Locale JVM khác giữa các host | Wire payload không đổi với cùng giá trị/schema |

Các bài kiểm thử cần bao gồm cả **giá trị qua lại** và **cú pháp**. Nếu một parser quá dễ dãi tự bỏ qua ký tự lạ, round-trip các giá trị hợp lệ vẫn có thể qua hết trong khi input độc hại được chấp nhận.

## 15. Các sai lầm thường gặp

| Sai lầm | Hệ quả | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `NumberFormat.getInstance().format(x)` rồi gửi API | Phụ thuộc default locale | Xác định wire codec và schema riêng |
| Parse output locale bằng `Double.parseDouble` | Gặp grouping/decimal comma sẽ lỗi | Parse UI bằng parser theo locale; wire bằng parser ổn định |
| Dùng `NumberFormat.parse` làm strict validator | Có thể chỉ đọc đầu chuỗi | Kiểm tra `ParsePosition` đã đi hết |
| Bỏ mọi dấu phẩy/chấm để “chuẩn hóa” | Có thể biến thập phân thành số lớn hơn | Validate đúng locale/grammar trước |
| Gửi giá trị tiền bằng `String.format("%.2f")` | Làm tròn và mất dữ liệu gốc | BigDecimal + policy rounding đúng thời điểm |
| Cho rằng `Double.toString` giữ decimal gốc hoàn hảo | Chỉ bảo toàn giá trị binary64 hiện có | Giữ input decimal dưới dạng BigDecimal/String nếu cần |
| Tạo `BigDecimal` từ một `double` đã mất thông tin | Không khôi phục số decimal ban đầu | Parse từ text decimal đúng schema |
| Gửi `NaN` thành JSON number | Không phải JSON chuẩn | Policy non-finite rõ ràng trước serialize |
| Gửi ID long lớn dưới JSON number mà bỏ qua client JS | Có thể mất độ chính xác | Decimal string theo schema khi cần |
| Đổi `"00042"` thành số để “gọn” | Mất số 0 đầu | Giữ mã định danh ở kiểu String |
| Dùng `toPlainString` cho exponent rất lớn không giới hạn | Chuỗi có thể quá lớn | Giới hạn miền/độ dài khi encode |
| Dùng output `String.format` để lưu DB numeric | Chuỗi có thể bị diễn giải sai | JDBC setter theo kiểu số và schema |
| Coi CSV quoting là giải pháp parse decimal | Chỉ bảo vệ cấu trúc trường | Quy định codec cột numeric |
| Thay đổi locale JVM rồi API response đổi theo | Phá tương thích và test | Không dùng locale mặc định ở wire layer |
| Không ghi đơn vị và scale | Bên nhận tính sai ý nghĩa số | Schema có đơn vị/currency/scale rõ ràng |
| Dùng cùng formatter cho UI và integration | Trộn hai loại hợp đồng | Tách formatter trình bày khỏi serializer |

## 16. Câu hỏi tự kiểm tra

1. Vì sao `"1,234.50"` và `"1.234,50"` có thể hiển thị cùng giá trị nhưng không nên dùng làm một wire format không khai báo locale?
2. `Double.parseDouble("1.234.567,89")` cho kết quả gì? Muốn nhận input người dùng Đức, API nào liên quan?
3. Vì sao dùng `NumberFormat.parse` mà không kiểm tra `ParsePosition` có thể bỏ lọt `"1.234,50junk"`?
4. `Integer.toString`/`Long.toString` và `NumberFormat` khác nhau ở mục tiêu nào?
5. `Double.toString(0.1+0.2)` có bảo đảm kết quả đúng 0.3 theo số thập phân hay chỉ bảo toàn giá trị `double` hiện có?
6. Vì sao `new BigDecimal("1234.50")` có lợi hơn việc parse chuỗi hiển thị với grouping rồi đưa qua `double` nếu cần exact decimal?
7. `BigDecimal.toString` và `toPlainString` khác nhau khi giá trị được tạo từ `"1E+7"` như thế nào?
8. Vì sao `NaN` là một trạng thái `double` hợp lệ nhưng không thể ghi trực tiếp làm JSON numeric token chuẩn?
9. Một ID kiểu `long` bằng `9007199254740993` có vấn đề gì khi client dùng JavaScript `Number`?
10. CSV có dấu phẩy ngăn cột: nếu một field chứa `"1,234.50"`, bước nào giữ được cấu trúc cột? Bước nào định nghĩa ý nghĩa numeric của field?
11. Vì sao mã `"00042"` thường cần giữ dưới dạng `String` dù toàn chữ số?
12. Tầng UI, tầng nghiệp vụ và tầng wire nên mỗi tầng giữ loại giá trị nào?
13. Trong schema decimal string, phải ghi những điều gì về ký tự dấu, radix, exponent, grouping, precision/scale và đơn vị?
14. Nếu một formatter làm tròn 1234.567 thành `"1,234.57"`, parse lại có thể phục hồi số gốc không?
15. Làm sao test rằng thay đổi `Locale.getDefault()` không làm đổi JSON/CSV integration payload theo cùng schema?

## 17. Tài liệu tham khảo chính thức

- [Java SE 17 — `NumberFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): định dạng và parse số theo locale, các tùy chỉnh grouping/precision.
- [Java SE 17 — `DecimalFormat`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html): pattern trình bày decimal và tính chất parser.
- [Java SE 17 — `ParsePosition`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html): vị trí parser đã tiêu thụ và thông tin lỗi.
- [Java SE 17 — `Double`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html): `toString`, `parseDouble`, non-finite và quy tắc binary64.
- [Java SE 17 — `BigDecimal`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): `toString`, `toPlainString`, scale, decimal exact.
- [RFC 8259 — The JavaScript Object Notation (JSON) Data Interchange Format](https://www.rfc-editor.org/rfc/rfc8259): JSON number grammar, interoperability, non-finite values không được phép.
- [Java SE 17 — `Formatter`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html): ký hiệu grouping, precision và locale trong output trình bày.

**Kết luận:** Chuỗi định dạng theo locale thích hợp cho **UI và báo cáo con người**, nhưng không phải wire format đáng tin cậy mặc định. Hãy trao đổi **giá trị có kiểu** thông qua **schema/serializer ổn định**; với số thập phân cần chính xác, xác định decimal text và BigDecimal; với `long` lớn, cân nhắc client JS; với floating-point, quy định chính sách NaN/Infinity. Chỉ tại lớp hiển thị mới chọn cách phân nhóm, tiền tệ, ký hiệu thập phân, đơn vị và làm tròn phù hợp người đọc.