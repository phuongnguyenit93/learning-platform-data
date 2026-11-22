# NumberFormat cho số thông thường và số nguyên trong Java

## 1. Mục tiêu: cùng một giá trị, nhiều cách biểu diễn

Trong ứng dụng Java hỗ trợ nhiều ngôn ngữ/khu vực, cùng giá trị số có thể được **hiển thị khác nhau**: tiếng Anh (Mỹ) thường dùng dấu phẩy phân nhóm nghìn và dấu chấm thập phân; tiếng Đức (Đức) thường đảo hai dấu đó. Dữ liệu số bên trong chương trình vẫn giữ nguyên ý nghĩa, còn cách biểu diễn phục vụ người đọc phụ thuộc vào `Locale`.

Lớp trừu tượng `java.text.NumberFormat` cung cấp các factory để tạo đối tượng **định dạng số** và **phân tích chuỗi thành số** phù hợp với locale:

- `NumberFormat.getNumberInstance(locale)`: số thông thường, có thể có phần thập phân.
- `NumberFormat.getIntegerInstance(locale)`: kiểu trình bày **số nguyên**, không hiển thị chữ số thập phân, đồng thời mặc định **chỉ parse phần nguyên**.
- `NumberFormat.getNumberInstance()` và `getIntegerInstance()`: dùng locale mặc định cho category `Locale.Category.FORMAT`.
- `NumberFormat.getInstance(locale)`: tương đương factory số thông thường `getNumberInstance(locale)`.

Hai kiểu số trong đề bài là **kiểu định dạng**. `NumberFormat` không thay đổi kiểu dữ liệu `int`/`long`/`BigDecimal` trong domain và không tự đặt quy tắc làm tròn nghiệp vụ.

Ví dụ khái niệm:

| Dữ liệu số | `getNumberInstance(Locale.US)` với 2 chữ số lẻ | `getIntegerInstance(Locale.US)` với HALF_UP |
| --- | --- | --- |
| 12345.678 | `12,345.68` | `12,346` |
| 1234 | `1,234.00` nếu yêu cầu ít nhất 2 số lẻ | `1,234` |
| 12.5 | `12.50` nếu yêu cầu ít nhất 2 số lẻ | `13` |

Trong bảng, hai cột đầu ra đã có **cấu hình minh họa riêng**; đừng giả định factory mặc định luôn hiển thị đúng hai chữ số lẻ hoặc sử dụng HALF_UP. Khi tự triển khai, cần đặt quy tắc định dạng rõ ràng.

## 2. Factory dành cho số thông thường

### 2.1. Tạo formatter theo Locale tường minh

~~~java
import java.text.NumberFormat;
import java.util.Locale;

NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);
~~~

Đoạn trên là **minh họa các câu lệnh**, cần nằm trong một phương thức hoặc khối khởi tạo của lớp Java; chương trình chạy độc lập có đầy đủ ở mục 7.

`NumberFormat` trừu tượng hóa quy ước định dạng. Cùng số `12345.678` có thể cho ra `12,345.678` ở `en-US`, `12.345,678` ở `de-DE` với cấu hình phần lẻ cho phép ba chữ số. Tên dấu, cách nhóm và ký tự Unicode cụ thể có thể thay đổi theo locale, provider hoặc phiên bản dữ liệu CLDR; cần kiểm thử trên môi trường mục tiêu.

`Locale` ảnh hưởng nhiều yếu tố:

- Ký tự phân cách phần thập phân, ký tự phân nhóm nghìn.
- Quy ước phân nhóm và số chữ số.
- Hệ chữ số (có thể là chữ số không phải ASCII, tùy locale và Unicode extension).
- Cách hiển thị dấu âm và một số ký hiệu đặc biệt.

Đừng dùng `String.format("%,.2f", value)` với default locale không kiểm soát nếu đầu ra phải ổn định theo người dùng. Nếu dùng `String.format(locale, ...)`, cũng phải truyền locale tường minh; `NumberFormat` phù hợp hơn khi cần thay đổi kiểu định dạng và parse hai chiều theo locale.

### 2.2. Cấu hình số chữ số lẻ

Các phương thức thường dùng:

~~~java
formatter.setMinimumFractionDigits(2);
formatter.setMaximumFractionDigits(2);
~~~

`formatter` là `NumberFormat` đã tạo. **Minimum** đảm bảo thêm số 0 nếu cần, **maximum** giới hạn số chữ số lẻ được hiển thị, nên có thể phải **làm tròn**. Khi áp dụng min/max, đối tượng formatter có thể điều chỉnh giá trị còn lại để thỏa quan hệ min ≤ max. Nên đặt cả hai bằng quy tắc rõ ràng nếu cần hiển thị chính xác 2 chữ số lẻ.

Ví dụ với `en-US`:

| Giá trị | min = 2, max = 2 | Lý do |
| --- | --- | --- |
| `12` | `12.00` | Thêm hai số 0 |
| `12.3` | `12.30` | Thêm một số 0 |
| `12.345` | `12.35` khi HALF_UP | Làm tròn đến 2 chữ số |
| `-12.345` | `-12.35` khi HALF_UP | Làm tròn theo độ lớn theo quy tắc HALF_UP |

Phải phân biệt **làm tròn để hiển thị** và **làm tròn kết quả nghiệp vụ**. `NumberFormat` chỉ tạo chuỗi; nếu hệ thống tính tiền hay lưu số lượng, hãy dùng `BigDecimal` với scale và `RoundingMode` phù hợp ở lớp nghiệp vụ.

### 2.3. Cấu hình grouping

~~~java
formatter.setGroupingUsed(true);   // Bật nhóm nghìn theo quy tắc locale.
formatter.setGroupingUsed(false);  // Không nhóm nghìn.
~~~

Ví dụ số `12345.68` ở `Locale.US`, cấu hình hai chữ số lẻ:

- Grouping bật: `12,345.68`.
- Grouping tắt: `12345.68`.

Một số locale sử dụng **khoảng trắng không ngắt dòng** hoặc loại khoảng trắng Unicode khác để phân nhóm. Không tự dùng `replace(",", "")` để “bỏ phân nhóm”: dấu phẩy có thể là dấu thập phân ở locale khác.

## 3. NumberFormat cho số nguyên

`NumberFormat.getIntegerInstance(locale)` được thiết kế cho kiểu **đầu ra số nguyên**. Trên các formatter chuẩn của JDK, factory này cấu hình giới hạn phần thập phân bằng 0 và `isParseIntegerOnly()` là `true`:

~~~java
NumberFormat integers = NumberFormat.getIntegerInstance(Locale.US);
System.out.println(integers.getMaximumFractionDigits()); // 0
System.out.println(integers.isParseIntegerOnly());        // true
~~~

Đây là **đoạn minh họa** nằm bên trong phương thức, với import `NumberFormat` và `Locale`.

### 3.1. Khi format: làm tròn để hiển thị số nguyên

Với `getIntegerInstance(Locale.US)`, định dạng một giá trị có phần lẻ **không có nghĩa Java cắt bỏ phần thập phân**. Giá trị có thể được làm tròn theo quy tắc của formatter. Nếu muốn kết quả dễ dự đoán trong bài học, cấu hình rõ ràng:

~~~java
integers.setRoundingMode(java.math.RoundingMode.HALF_UP);
System.out.println(integers.format(
        new java.math.BigDecimal("12345.5"))); // 12,346
~~~

Cần nhớ:

- `format(12345.5)` tạo `String` `"12,346"` theo cấu hình trên. Nó **không trả về** một `int` hoặc tự biến số gốc thành `12346`.
- Với quy tắc HALF_EVEN mặc định phổ biến của `DecimalFormat`, các số nằm đúng điểm giữa có thể cho kết quả khác HALF_UP. Nếu ứng dụng đòi hỏi một quy tắc cụ thể, hãy đặt `RoundingMode` và kiểm thử.
- `getIntegerInstance` phù hợp để hiển thị số lượng nguyên, số bản ghi, điểm nguyên hoặc bộ đếm; **không** dùng để ép kiểu dữ liệu, xác thực input nguyên tuyệt đối hoặc tạo ID kỹ thuật.

### 3.2. Khi parse: chỉ lấy tiền tố số nguyên

Quan trọng hơn, `getIntegerInstance` thường đặt `parseIntegerOnly = true`. Khi gặp chuỗi `12,345.67` theo `en-US`, parser có thể dừng **trước dấu thập phân** và trả `12345` dù vẫn còn `.67` chưa được tiêu thụ.

Điều này **không phải** cơ chế kiểm tra rằng toàn bộ chuỗi đầu vào là một số nguyên hợp lệ. `parse` có thể thành công với **một phần** input.

Nếu API nhận số lượng hàng hoặc số sản phẩm, chuỗi `12,345.67` phải bị từ chối hoặc được xử lý theo quy tắc input đã công bố; không im lặng nhận `12345`.

### 3.3. `setParseIntegerOnly(true)` không thay độ chính xác khi format

Đây là hai cấu hình độc lập:

| Cấu hình | Ảnh hưởng chính |
| --- | --- |
| `setMaximumFractionDigits(0)` | Giới hạn phần lẻ khi **format** |
| `setParseIntegerOnly(true)` | Dừng khi gặp phần thập phân trong bước **parse** |
| `getIntegerInstance(locale)` | Factory cấu hình phù hợp cả định dạng số nguyên và parse phần nguyên |

Ví dụ:

~~~java
NumberFormat parserMode =
        NumberFormat.getNumberInstance(Locale.US);
parserMode.setParseIntegerOnly(true);
System.out.println(parserMode.format(12.75)); // 12.75
~~~

Thay đổi `parseIntegerOnly` **không làm mất** phần lẻ trong chuỗi đã format. Hai phương thức điều chỉnh hai hành vi khác nhau; đoạn mã này được kiểm tra trong chương trình hoàn chỉnh ở mục 7.

## 4. Parse chuỗi theo locale: đầu vào là dữ liệu, không phải định dạng hiển thị

`NumberFormat.parse(String)` cố chuyển một đoạn đầu của chuỗi thành `Number` theo locale đã chọn. Nó có thể ném `ParseException` nếu **không parse được gì** từ vị trí đầu, nhưng không mặc nhiên yêu cầu toàn bộ chuỗi được tiêu thụ.

Với `Locale.US`:

~~~java
NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
Number value = us.parse("12,345.67");
~~~

Đây là đoạn minh họa trong phương thức đã khai báo hoặc xử lý `ParseException`. Giá trị được parse tương ứng với số `12345.67`, nhưng kiểu kết quả có thể là `Long`, `Double` hoặc kiểu khác tùy parser và cấu hình. Không ép kiểu thẳng thành `Double` hay `Long` khi chưa xác định hợp đồng API.

### 4.1. Kiểm tra toàn bộ input bằng ParsePosition

`java.text.ParsePosition` cho biết parser đã tiêu thụ đến ký tự nào:

~~~java
ParsePosition position = new ParsePosition(0);
Number parsed = formatter.parse(input, position);
boolean fullyConsumed =
        parsed != null && position.getIndex() == input.length();
~~~

Đoạn này giả định `formatter` là `NumberFormat` và `input` là `String`, nằm trong một phương thức. Với chuỗi `"12,345.67"` dài 9 ký tự:

- Number formatter `en-US`: parse `12345.67`, tiêu thụ 9/9.
- Integer formatter `en-US`: parse `12345`, tiêu thụ 6/9 (dừng trước dấu chấm).

Kết quả `6/9` cho biết không thể chấp nhận input như một **số nguyên đầy đủ**. Nếu chưa tiêu thụ đủ hoặc `parsed == null`, thông báo lỗi cho người dùng.

**Giới hạn quan trọng:** kiểm tra `position.getIndex() == input.length()` chỉ đảm bảo tiêu thụ toàn chuỗi, **không đủ** để đảm bảo cú pháp grouping nghiêm ngặt hay phù hợp quy tắc nghiệp vụ. Một số parser có thể chấp nhận cách phân nhóm không chuẩn; ứng dụng nên có thêm chính sách validate riêng (ví dụ không cho phép grouping, kiểm tra dấu, khoảng giá trị, độ dài, toàn bộ biểu diễn). Đừng dùng parse như một bộ xác thực “đúng mọi định dạng địa phương”.

### 4.2. Cần giữ độ chính xác thập phân?

Trong nhiều triển khai JDK, `NumberFormat.getNumberInstance(locale)` trả về `DecimalFormat`. `DecimalFormat` hỗ trợ `setParseBigDecimal(true)` để tạo `BigDecimal` thay vì phụ thuộc vào biểu diễn nhị phân `double` cho giá trị thập phân. Nếu cần:

~~~java
NumberFormat format = NumberFormat.getNumberInstance(Locale.US);
if (format instanceof java.text.DecimalFormat decimalFormat) {
    decimalFormat.setParseBigDecimal(true);
    Number number = decimalFormat.parse("12345.67");
    // Trong trường hợp số hữu hạn thông thường trên, number là BigDecimal.
}
~~~

Đây là **đoạn minh họa**, với xử lý `ParseException` thích hợp. Không giả định mọi `NumberFormat` của mọi provider đều là `DecimalFormat`; nếu code cần trực tiếp `DecimalFormat`, hãy kiểm tra kiểu và hợp đồng của provider.

Đối với số tiền, định dạng và phân tích phải dựa trên quy tắc tiền tệ, scale và nguồn dữ liệu; không nên dùng `NumberFormat` như bộ lưu trữ giá trị. `getCurrencyInstance` là factory riêng của cách hiển thị tiền tệ, còn bài này tập trung vào số thông thường và số nguyên.

## 5. Locale mặc định so với Locale tường minh

Hai cách tạo đối tượng:

~~~java
NumberFormat implicit = NumberFormat.getNumberInstance();
NumberFormat explicit =
        NumberFormat.getNumberInstance(Locale.forLanguageTag("vi-VN"));
~~~

Trong đó:

- `implicit` dùng locale mặc định cho category `Locale.Category.FORMAT` của JVM.
- `explicit` có locale cụ thể, nên không phụ thuộc vào lựa chọn mặc định của máy chạy đối với việc chọn dấu và mẫu formatter.

Với chương trình CLI một ngôn ngữ, default locale có thể hữu ích. Với website, server và ứng dụng có nhiều người dùng cùng lúc, **không gọi `Locale.setDefault(...)` trên mỗi request** để chuyển dấu phân cách số: `Locale.setDefault` thay đổi trạng thái toàn JVM, các thread/request khác có thể bị ảnh hưởng. Thay vào đó, chọn locale tại input/UI boundary và truyền nó vào lớp trình bày.

`Locale` **không** xác định duy nhất loại tiền tệ hoặc múi giờ. Dùng `ZoneId` riêng cho thời điểm và `Currency` cùng giá trị khi xử lý tiền.

## 6. Cấu hình NumberFormat có thể thay đổi đối tượng

Các setter như `setGroupingUsed`, `setMinimumFractionDigits`, `setMaximumFractionDigits`, `setParseIntegerOnly` và `setRoundingMode` **thay đổi trạng thái của formatter**. `NumberFormat` nói chung không đảm bảo thread-safe: không chia sẻ một instance mutable giữa nhiều request/thread nếu không có cơ chế đồng bộ phù hợp.

Một mẫu an toàn cho lớp trình bày:

~~~java
static String formatQuantity(Number quantity, Locale locale) {
    NumberFormat format = NumberFormat.getIntegerInstance(locale);
    format.setRoundingMode(java.math.RoundingMode.HALF_UP);
    return format.format(quantity);
}
~~~

Đoạn này là **một phương thức minh họa**, cần `import java.text.NumberFormat;` và `import java.util.Locale;` ở class chứa nó. Để dùng thực tế, quy tắc làm tròn số lượng phải được domain xác định trước; nếu số lượng bắt buộc nguyên tuyệt đối, hãy validate số lượng trước khi formatter nhận nó.

Đừng trả `NumberFormat` ở dạng singleton rồi thay locale/cấu hình “cho request hiện tại”. Hãy tạo formatter theo ngữ cảnh hoặc sử dụng bản sao/chiến lược quản lý riêng đảm bảo không chia sẻ state mutable.

## 7. Chương trình Java 17 chạy độc lập

Đặt mã sau trong file **`NumberFormatDemo.java`**. Ví dụ chọn rõ locale, số chữ số lẻ và `RoundingMode.HALF_UP`; không phụ thuộc default locale của máy chạy.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;

public class NumberFormatDemo {
    static String parseResult(NumberFormat format, String input) {
        ParsePosition position = new ParsePosition(0);
        Number number = format.parse(input, position);
        return String.valueOf(number) + ", consumed=" + position.getIndex()
                + "/" + input.length();
    }

    public static void main(String[] args) {
        BigDecimal amount = new BigDecimal("12345.678");
        NumberFormat us = NumberFormat.getNumberInstance(Locale.US);
        NumberFormat de = NumberFormat.getNumberInstance(Locale.GERMANY);
        for (NumberFormat formatter : new NumberFormat[]{us, de}) {
            formatter.setMinimumFractionDigits(2);
            formatter.setMaximumFractionDigits(2);
            formatter.setRoundingMode(RoundingMode.HALF_UP);
        }

        System.out.println("US number: " + us.format(amount));
        System.out.println("DE number: " + de.format(amount));

        NumberFormat integer = NumberFormat.getIntegerInstance(Locale.US);
        integer.setRoundingMode(RoundingMode.HALF_UP);
        System.out.println("US integer: "
                + integer.format(new BigDecimal("12345.5")));
        System.out.println("integer parser only: "
                + integer.isParseIntegerOnly());
        System.out.println("decimal parse: "
                + parseResult(NumberFormat.getNumberInstance(Locale.US),
                        "12,345.67"));
        System.out.println("integer parse: "
                + parseResult(integer, "12,345.67"));

        NumberFormat parsingOnly = NumberFormat.getNumberInstance(Locale.US);
        parsingOnly.setParseIntegerOnly(true);
        System.out.println("parseIntegerOnly format: "
                + parsingOnly.format(12.75));

        us.setGroupingUsed(false);
        System.out.println("without grouping: " + us.format(amount));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 NumberFormatDemo.java
java NumberFormatDemo
~~~

**Stdout chính xác của ví dụ** trên JDK chuẩn với dữ liệu định dạng `Locale.US`/`Locale.GERMANY` thông dụng:

~~~text
US number: 12,345.68
DE number: 12.345,68
US integer: 12,346
integer parser only: true
decimal parse: 12345.67, consumed=9/9
integer parse: 12345, consumed=6/9
parseIntegerOnly format: 12.75
without grouping: 12345.68
~~~

Ý nghĩa của kết quả:

1. Cùng một `BigDecimal("12345.678")` được trình bày theo hai quy ước phân cách.
2. `getIntegerInstance` hiển thị `12345.5` thành `12,346` khi yêu cầu HALF_UP; số gốc không bị thay đổi.
3. Cùng chuỗi nhập `12,345.67`, parser số thường tiêu thụ 9/9 ký tự, còn parser số nguyên chỉ tiêu thụ 6/9.
4. Chỉ gọi `setParseIntegerOnly(true)` không làm thay kết quả `format(12.75)`.
5. `setGroupingUsed(false)` tắt phân nhóm của formatter US đã tạo.

Kết quả định dạng của một số locale có thể khác giữa nguồn dữ liệu CLDR, provider hoặc phiên bản JDK; nếu dùng snapshot test, hãy chỉ khẳng định output trong môi trường được kiểm soát.

## 8. Chọn loại NumberFormat theo nhu cầu

| Nhu cầu | Gợi ý | Điều cần kiểm tra thêm |
| --- | --- | --- |
| Hiển thị số đo có phần lẻ | `getNumberInstance(locale)` | Min/max fraction, đơn vị đo, rounding |
| Hiển thị số lượng nguyên đã được domain validate | `getIntegerInstance(locale)` | Grouping và rounding cho giá trị đầu vào |
| Parse số thập phân người dùng gõ | `getNumberInstance(locale)` + `ParsePosition` | Tiêu thụ đủ chuỗi, grouping, miền giá trị |
| Parse input **bắt buộc nguyên** | Parser theo locale + xác thực riêng | Không chấp nhận phần lẻ, overflow, dấu sai |
| Hiển thị phần trăm | `getPercentInstance(locale)` | Quy tắc nhân 100 và fraction digits |
| Hiển thị tiền | `getCurrencyInstance(locale)` | `Currency`, scale, rounding, tỷ giá |
| Lưu/trao đổi số máy đọc (JSON/API) | Biểu diễn số chuẩn hóa theo contract | Không dùng chuỗi phân nhóm theo locale |

Đối với **ID, mã khách hàng, số điện thoại, mã bưu chính**, không dùng formatter số nguyên để “làm đẹp”: các giá trị đó có thể có số 0 ở đầu, dấu cộng, dấu gạch hoặc nhiều chữ số vượt phạm vi số nguyên. Chúng là **định danh**, nên nên giữ dưới dạng chuỗi và kiểm tra theo quy tắc riêng.

## 9. Lỗi thường gặp

| Lỗi | Hệ quả | Cách sửa |
| --- | --- | --- |
| `getIntegerInstance` được dùng để cắt phần thập phân | Formatter **làm tròn** khi hiển thị | Xác thực/đổi kiểu ở domain trước; đặt rounding khi format |
| Dùng `setParseIntegerOnly(true)` rồi tưởng `format` sẽ là số nguyên | Hai hành vi độc lập | Dùng `getIntegerInstance` hoặc đặt maxFractionDigits=0 |
| Chỉ kiểm tra `parse` không ném `ParseException` | Chuỗi có thể chỉ được parse một phần | Dùng `ParsePosition`, kiểm tra đã dùng hết input |
| Dùng `ParsePosition` rồi tin input tuân thủ mọi quy tắc grouping | Parser có thể dễ dãi với grouping | Thêm validator theo contract |
| Lấy `Number` trả về rồi ép `(Long)` hoặc `(Double)` tùy tiện | `ClassCastException` hoặc mất thông tin | Kiểm tra kiểu và quy tắc dữ liệu |
| Dùng `double` cho số tiền cần chính xác thập phân | Sai số nhị phân khi tính toán | `BigDecimal` trong domain; kiểm soát scale |
| Hardcode `,` là dấu thập phân hay grouping | Sai với locale khác | Dùng `NumberFormat` theo locale |
| Dùng `Locale.setDefault` theo request | Trạng thái chung JVM gây nhiễu request khác | Truyền locale tường minh |
| Chia sẻ một `NumberFormat` mutable giữa thread | Race/định dạng không ổn định | Tạo theo ngữ cảnh hoặc quản lý thread-safe |
| Dùng formatter để chuẩn hóa ID/số điện thoại | Mất số 0 đầu hoặc làm biến đổi ký tự | Giữ định danh là chuỗi |

## 10. Kiểm thử nên viết

Với một thành phần hiển thị hoặc nhận số theo locale, nên kiểm thử:

- **Khác locale:** số `12345.678` ở `en-US` và `de-DE`, kiểm tra dấu/grouping theo môi trường có dữ liệu locale đã định.
- **Minimum/maximum fraction:** `12`, `12.3`, `12.345`, giá trị âm, `0`, số rất lớn và `BigDecimal` có scale cao.
- **Rounding:** giá trị đúng giữa (ví dụ `2.5`, `3.5`, `-2.5`) với HALF_UP/HALF_EVEN hoặc quy tắc nghiệp vụ đã chọn.
- **Integer display:** formatter số nguyên không còn chữ số lẻ nhưng có làm tròn.
- **Integer parsing:** nhập `12,345.67` phải bị validator cho input nguyên từ chối vì chỉ tiêu thụ 6/9 ký tự.
- **Chuỗi lỗi:** trống, chỉ dấu phân cách, nhiều dấu âm, grouping lạ, chữ số Unicode không mong muốn, trailing garbage và số vượt miền.
- **Đa luồng:** không chia sẻ mutable formatter hoặc default locale do request thay đổi.
- **Định danh:** các mã `00123` và số điện thoại giữ nguyên ký tự dù locale thay đổi.

Một test được thiết kế tốt so sánh **giá trị parse và số ký tự tiêu thụ**, không dựa vào `NumberFormat` như một bộ xác thực nhập liệu nghiêm ngặt mà thư viện chưa hứa cung cấp.

## 11. Bài tập thực hành

1. Thay `Locale.GERMANY` bằng `Locale.forLanguageTag("vi-VN")`, quan sát separator và chữ số trên JDK đang dùng.
2. Đổi `setMinimumFractionDigits(2)` thành `0`, giữ `setMaximumFractionDigits(2)`; giải thích khác biệt giữa `12` và `12.345`.
3. Thử HALF_EVEN khi format `2.5` và `3.5` bằng integer formatter, so với HALF_UP. Hãy kiểm tra tác động của dấu âm.
4. Tạo `NumberFormat.getNumberInstance(Locale.US)`, đặt `setParseIntegerOnly(true)` và kiểm tra parse `12,345.67`; sau đó thử format `12.75`.
5. Dùng `ParsePosition` kiểm tra `"12,345.67abc"`, `"12,345.67"` và `"12,345.67 "`; xác định phần nào parser tiêu thụ.
6. Thử `DecimalFormat.setParseBigDecimal(true)` với giá trị có nhiều chữ số thập phân; so sánh kiểu trả về với khi không bật.
7. Tắt grouping và so sánh `us.format(new BigDecimal("1234567.89"))` trước/sau.
8. Viết hàm `formatCount(long count, Locale locale)` tạo formatter mới tại mỗi lần gọi, rồi thử với nhiều locale trong các thread khác nhau.

Qua các bài tập này, cần nhớ rằng **format là chuyển số thành chuỗi cho người đọc**, còn **parse là chuyển chuỗi thành số**, và hai hoạt động có thể được cấu hình khác nhau ngay trên một đối tượng `NumberFormat`.

## 12. Tổng kết

`NumberFormat.getNumberInstance(locale)` phù hợp để định dạng và parse **số thông thường**, có thể có phần thập phân. `NumberFormat.getIntegerInstance(locale)` phục vụ **cách trình bày số nguyên** và mặc định chỉ parse **phần nguyên**; điều này không biến nó thành validator cho input chỉ gồm số nguyên.

Hãy tạo formatter với `Locale` tường minh, quyết định grouping/min/max/rounding theo yêu cầu, kiểm tra phần input được tiêu thụ khi parse và giữ dữ liệu nghiệp vụ ở kiểu số thích hợp. Với các yêu cầu độ chính xác cao, kết hợp `BigDecimal` và chính sách parse/rounding rõ ràng, không dùng chuỗi đã bản địa hóa làm dữ liệu nguồn.

**Tài liệu tham khảo:**

- Java SE 17, `java.text.NumberFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html
- Java SE 17, `java.text.DecimalFormat`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html
- Java SE 17, `java.text.ParsePosition`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html
- Java SE 17, `java.util.Locale`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html
