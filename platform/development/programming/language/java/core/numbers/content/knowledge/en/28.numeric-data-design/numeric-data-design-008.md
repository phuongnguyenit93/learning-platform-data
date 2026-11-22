# Tách định dạng hiển thị khỏi tính toán và trao đổi dữ liệu số trong Java

## 1. Một giá trị số, ba trách nhiệm khác nhau

Một số tiền có giá trị toán học là 12348.17 có thể xuất hiện với nhiều cách viết:

- **Trong tính toán:** đối tượng `BigDecimal` giữ giá trị thập phân để cộng, trừ, nhân, chia theo quy tắc nghiệp vụ.
- **Trên giao diện cho người dùng:** `12.348,17` ở một số locale sử dụng dấu phẩy thập phân, hoặc `12,348.17` ở locale dùng dấu chấm thập phân.
- **Khi trao đổi giữa hệ thống:** `12348.17` là một biểu diễn trung lập về locale nếu hợp đồng API chọn chuỗi thập phân có dấu chấm và không có phân nhóm.

Ba cách biểu diễn có mục đích khác nhau. **Giá trị dùng để tính toán không nên thay đổi chỉ vì locale hoặc kiểu trình bày thay đổi.** Chuỗi đã thêm dấu phân nhóm, dấu tiền tệ hay chữ viết tắt để hiển thị không mặc nhiên hợp lệ để đưa trở lại công thức hoặc truyền qua API.

Một mô hình đơn giản:

~~~text
Chuỗi nhập từ người dùng
    │ kiểm tra định dạng theo locale đã chọn
    ▼
Giá trị miền dữ liệu (BigDecimal + đơn vị/tiền tệ)
    │ tính toán theo chính sách precision, scale và rounding
    ▼
Giá trị kết quả BigDecimal
    ├──> Format bằng locale/currency --> Giao diện người dùng
    └──> Serialize bằng hợp đồng ổn định --> JSON/CSV/API/lưu trữ
~~~

Nếu chuỗi vào vốn là một giá trị chuẩn từ hệ thống khác, parse theo **hợp đồng trao đổi** thay vì parse theo locale của người đang đăng nhập. Nếu chuỗi vào đến từ form người dùng, parse theo định dạng mà form yêu cầu. **Điều kiện nhận đầu vào** khác với **định dạng hiển thị đầu ra** và khác với **hợp đồng trao đổi**.

## 2. Lớp tính toán: giữ số, không ghép ký tự định dạng

Khi dữ liệu là số thập phân nghiệp vụ cần chính xác, `BigDecimal` thường phù hợp hơn `double`. Hãy dựng đối tượng từ nguồn thập phân như chuỗi:

~~~java
BigDecimal price = new BigDecimal("12345.67");
BigDecimal fee = new BigDecimal("2.50");
BigDecimal total = price.add(fee);

System.out.println(total.toPlainString()); // 12348.17
~~~

Đây là **đoạn mã minh họa**, cần import `java.math.BigDecimal` và đặt trong phương thức hoặc chương trình Java thích hợp. Cả `price`, `fee` và `total` đều là dữ liệu số, chưa mang dấu phân cách hàng nghìn hay ký hiệu tiền tệ.

Điểm cần phân biệt:

- `new BigDecimal("0.1")` biểu diễn chính xác số thập phân 0.1.
- `new BigDecimal(0.1)` nhận giá trị nhị phân `double` gần với 0.1, nên có thể chứa một biểu diễn thập phân dài không mong muốn.
- `BigDecimal.valueOf(0.1)` dựa vào dạng chuỗi thập phân của `double`; thường hữu dụng nếu dữ liệu đã ở dạng `double`, nhưng không khôi phục được văn bản thập phân ban đầu chưa biết.
- `BigDecimal` giữ giá trị, scale và precision theo quy tắc kiểu số; **không giữ locale, ký hiệu tiền tệ hay dấu phân nhóm của văn bản nguồn**.

Với số tiền, đơn vị là một phần của mô hình nghiệp vụ. Giá trị `100.00` USD và `100.00` EUR không tự động là cùng một lượng tiền có thể cộng. Giữ **mã tiền tệ hoặc đơn vị** trong thuộc tính miền dữ liệu riêng và xác nhận hai đại lượng có cùng đơn vị trước khi cộng.

Một thiết kế minh họa:

~~~java
record Amount(BigDecimal value, String currencyCode) {}
~~~

`record` trên chỉ minh họa ranh giới kiểu dữ liệu, chưa triển khai kiểm tra giá trị hợp lệ hoặc quy tắc chuyển đổi tiền tệ. Để dùng thực tế, cần xác thực mã tiền tệ, null, miền giá trị và các phép toán tương thích đơn vị.

## 3. Lớp hiển thị: locale, dấu phân nhóm và độ dài chữ số

Cùng một `BigDecimal` có thể hiển thị khác nhau theo khu vực:

| Giá trị `BigDecimal` | Hiển thị kiểu US | Hiển thị kiểu Đức |
| --- | --- | --- |
| 12348.17 | `12,348.17` | `12.348,17` |
| 1000.50 | `1,000.50` | `1.000,50` |
| 0.50 | `0.50` | `0,50` |

Bảng sử dụng quy tắc định dạng **cụ thể đã chọn**: có dấu nhóm hàng nghìn và đúng hai chữ số sau dấu thập phân. Đó không phải quy tắc bắt buộc cho mọi ứng dụng, mọi kiểu số và mọi locale.

Java cung cấp `NumberFormat` và `DecimalFormat` trong `java.text`. Ví dụ:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.util.Locale;

BigDecimal total = new BigDecimal("12348.17");
DecimalFormat german = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.GERMANY));
german.setRoundingMode(RoundingMode.HALF_UP);

System.out.println(german.format(total)); // 12.348,17
~~~

Pattern `#,##0.00` trong ví dụ quy định dấu phân nhóm và hai chữ số thập phân. `DecimalFormatSymbols` cung cấp dấu phân nhóm và dấu thập phân theo `Locale.GERMANY`. Đây là đoạn minh họa sử dụng bên trong phương thức.

**Format trả về `String`, không biến đối tượng `BigDecimal` đầu vào thành giá trị mới.** Hai người dùng có thể nhìn thấy cách trình bày khác nhau mà vẫn tính trên cùng một số.

### 3.1. Chính sách làm tròn khi hiển thị

Một `DecimalFormat` có thể giới hạn số chữ số được in ra. Nếu độ chính xác nguồn lớn hơn, chuỗi hiển thị có thể bị làm tròn:

~~~java
BigDecimal precise = new BigDecimal("1.005");
DecimalFormat display = new DecimalFormat(
        "#,##0.00", DecimalFormatSymbols.getInstance(Locale.GERMANY));
display.setRoundingMode(RoundingMode.HALF_UP);

System.out.println(display.format(precise)); // 1,01
System.out.println(precise.toPlainString()); // 1.005
~~~

`display.format` chỉ quyết định người dùng **nhìn thấy** gì; giá trị `precise` vẫn chính xác là 1.005. Vì vậy **chuỗi hiển thị đã bị làm tròn không được dùng thay cho giá trị tính toán nếu chính sách nghiệp vụ chưa cho phép làm tròn tại đó**.

Ví dụ hai khoản `1.005`:

| Cách xử lý | Kết quả |
| --- | --- |
| Hiển thị từng khoản với hai chữ số và `HALF_UP` | `1,01` và `1,01` |
| Tổng chính xác `1.005 + 1.005` | `2.010` |
| Hiển thị tổng chính xác ở hai chữ số | `2,01` |
| Cộng hai chuỗi hiển thị đã làm tròn như hai số `1.01` | `2.02` |

Đây **không tự động là lỗi phần mềm**: nếu hóa đơn quy định phải làm tròn từng dòng trước khi cộng, `2.02` có thể là kết quả hợp đồng. Nếu quy định cộng các số chính xác rồi làm tròn tổng, `2.01` mới đúng. Điều quan trọng là **tách chính sách tính toán ra khỏi cách hiển thị**, không để thao tác format âm thầm quyết định thuật toán cộng.

### 3.2. Tiền tệ không chỉ là dấu tiền

`NumberFormat.getCurrencyInstance(locale)` có thể dùng cho giao diện trình bày tiền tệ, nhưng một `Locale` **không thay thế thuộc tính `Currency` của giá trị miền**. Locale mô tả thói quen hiển thị; đơn vị tiền là dữ liệu nghiệp vụ. Người dùng ở Việt Nam vẫn có thể xem một khoản USD. Hãy truyền currency của khoản tiền vào formatter thích hợp, không mặc định suy ra đơn vị từ vị trí người xem.

Số chữ số thập phân “mặc định” của một tiền tệ cũng không thay thế các yêu cầu cụ thể về quy tắc làm tròn của giao dịch, thuế, phí hoặc thanh toán.

### 3.3. Formatter là đối tượng có trạng thái

`NumberFormat`/`DecimalFormat` có các thuộc tính có thể thay đổi, như maximum fraction digits, grouping và rounding mode. Chúng **không bảo đảm thread-safe khi chia sẻ và dùng đồng thời**. Trong ứng dụng nhiều luồng, thường tạo formatter theo từng lần dùng/yêu cầu hoặc bảo đảm cơ chế sử dụng có kiểm soát. Không chia sẻ một `static DecimalFormat` rồi thay `Locale`/pattern từ nhiều request mà không có thiết kế đồng bộ.

## 4. Lớp trao đổi: hợp đồng ổn định và độc lập với người xem

Chuỗi ở giao diện ví dụ `12.348,17` có nghĩa ở locale Đức, nhưng hệ thống khác có thể hiểu dấu chấm là dấu thập phân và dấu phẩy là dấu nhóm. **Không đưa trực tiếp chuỗi hiển thị vào JSON, CSV hoặc API nếu hợp đồng nhận không định nghĩa cách parse chuỗi đó.**

Một hợp đồng trao đổi dữ liệu số thập phân có thể quy định:

- Giá trị là **chuỗi thập phân**, dấu thập phân là `.`, không dùng dấu phân nhóm; ví dụ `"12348.17"`.
- Dấu âm là `-`; đơn vị hoặc mã tiền tệ là trường riêng; scale/precision/miền giá trị được mô tả rõ.
- Phía nhận dùng `BigDecimal` hoặc kiểu decimal tương thích để parse, thay vì tự ép qua `double`.
- Các thay đổi làm tròn phải xảy ra theo chính sách nghiệp vụ, không do locale của máy gửi hoặc máy nhận.

Ví dụ một **hợp đồng JSON do ứng dụng tự thiết kế** cho số tiền:

~~~json
{
  "amount": "12348.17",
  "currency": "EUR"
}
~~~

Ở đây `amount` cố ý là **JSON string** để phía nhận có thể tái dựng `BigDecimal` từ chuỗi mà không phải đi qua `double`. Đây là một lựa chọn thiết kế, không phải yêu cầu rằng JSON phải luôn mã hóa số thập phân thành string. JSON cũng có cú pháp number `12348.17`, nhưng một số thư viện/consumer có thể đưa JSON number vào kiểu nhị phân `double`; nếu hợp đồng cần độ chính xác thập phân, phải quy định kiểu xử lý ở cả hai phía.

### 4.1. Biểu diễn chuẩn từ `BigDecimal`

~~~java
BigDecimal total = new BigDecimal("12348.17");

String transportValue = total.toPlainString(); // "12348.17"
BigDecimal received = new BigDecimal(transportValue);
~~~

`toPlainString()` trả biểu diễn không dùng ký pháp mũ, phù hợp khi hợp đồng chọn **chuỗi thập phân dạng thường**. Ví dụ `new BigDecimal("1E+3").toPlainString()` trả `"1000"`. Tuy nhiên, `toPlainString()` không giữ nguyên mọi thông tin về scale trong các trường hợp như scale âm; một phép round-trip qua nó có thể giữ **giá trị** nhưng không giữ **biểu diễn scale ban đầu**. Nếu scale là dữ liệu bắt buộc, hãy định nghĩa thêm trường scale hoặc quy định biểu diễn có thể round-trip theo nhu cầu.

`BigDecimal.toString()` cũng độc lập locale nhưng có thể dùng ký pháp mũ, ví dụ `1E+3`. Nếu hợp đồng API cho phép ký pháp mũ, nó có thể phù hợp; nếu cấm, phải dùng hoặc xây dựng biểu diễn theo hợp đồng. Đừng thay `toPlainString()` cho `toString()` chỉ vì sở thích nếu hợp đồng và chi phí biểu diễn có ràng buộc đặc biệt.

### 4.2. Không format theo locale rồi parse trở lại để tính

Tránh chuỗi thao tác:

~~~text
BigDecimal -> DecimalFormat.format -> String hiển thị
           -> parser theo locale khác -> tính toán hoặc trao đổi
~~~

Rủi ro gồm mất chữ số do format, hiểu sai dấu nhóm/dấu thập phân, xử lý không thống nhất của ký hiệu tiền, và lỗi do locale máy chủ thay đổi. Khi cần làm tròn số trước khi lưu hoặc truyền, gọi **phép toán số** có quy tắc tường minh:

~~~java
BigDecimal accepted = total.setScale(2, RoundingMode.HALF_EVEN);
String transport = accepted.toPlainString();
~~~

Đây là việc **thay đổi giá trị theo hợp đồng**, khác với format giao diện thuần túy. Nếu cấm làm tròn, dùng `setScale(2, RoundingMode.UNNECESSARY)` để báo `ArithmeticException` khi giá trị không biểu diễn chính xác ở scale 2.

## 5. Nhận dữ liệu: chuỗi người dùng và chuỗi giao thức có cách parse khác nhau

### 5.1. Chuỗi chuẩn do API gửi

Nếu hợp đồng trao đổi gửi `"12348.17"` theo dạng thập phân dấu chấm, dùng:

~~~java
BigDecimal amount = new BigDecimal("12348.17");
~~~

Constructor nhận `String` dùng cú pháp số thập phân của `BigDecimal`, **không đọc locale người dùng**. Chuỗi `"12.348,17"` hoặc `"12,348.17"` có dấu nhóm không phải chuỗi đầu vào hợp lệ cho constructor này.

Đừng gọi `Double.parseDouble` trước rồi tạo `BigDecimal` từ `double` nếu mục tiêu là giữ chính xác giá trị thập phân nguồn.

### 5.2. Chuỗi gõ theo locale của giao diện

Khi một người dùng nhập `12.348,17` với quy ước Đức, formatter/parser theo `Locale.GERMANY` mới có ý nghĩa. Ví dụ parser trả kết quả số thập phân:

~~~java
DecimalFormat parser = new DecimalFormat(
        "#,##0.################",
        DecimalFormatSymbols.getInstance(Locale.GERMANY));
parser.setParseBigDecimal(true);

String input = "12.348,17";
ParsePosition pos = new ParsePosition(0);
Number parsed = parser.parse(input, pos);

if (parsed == null || pos.getIndex() != input.length()) {
    throw new IllegalArgumentException("Sai dinh dang so");
}
BigDecimal value = (BigDecimal) parsed;
// value = 12348.17
~~~

`setParseBigDecimal(true)` yêu cầu `DecimalFormat.parse` trả `BigDecimal` trong trường hợp số thông thường, tránh đưa giá trị thập phân qua `double`. `ParsePosition` giúp kiểm tra parser đã đọc **hết chuỗi**, bởi nhiều parser có thể đọc thành công chỉ một tiền tố hợp lệ.

**Giới hạn:** Kiểm tra đã tiêu thụ hết chuỗi không tự bảo đảm mọi nhóm chữ số đều theo định dạng chặt mà ứng dụng yêu cầu. `DecimalFormat` có thể linh hoạt với vị trí dấu nhóm ở một số trường hợp. Nếu dữ liệu nhập phải tuân thủ chuẩn nghiêm ngặt, hãy bổ sung bước xác minh pattern/nhóm/ký tự được phép, khoảng trắng và miền giá trị trước khi chấp nhận. Không dùng việc parse thành công để ngầm hợp thức hóa mọi chuỗi.

### 5.3. Tránh suy diễn locale từ chuỗi

Chuỗi `1,234` có thể là một nghìn hai trăm ba mươi bốn theo một quy ước hoặc là một phẩy hai ba bốn theo quy ước khác. Nếu không biết locale, **không thể luôn tự động xác định ý định người nhập**.

Hệ thống nên chọn một trong các cách: form quy định locale rõ ràng; hiển thị ví dụ ngay cạnh ô nhập; dùng input tách phần nguyên/phần lẻ; hoặc bắt người dùng xác nhận khi giá trị không rõ ràng. Với API giữa các dịch vụ, tốt nhất công bố cú pháp duy nhất trong schema và từ chối chuỗi trái hợp đồng.

## 6. Chương trình hoàn chỉnh với Java 17+

Tạo tệp **NumericBoundariesDemo.java**:

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.text.DecimalFormat;
import java.text.DecimalFormatSymbols;
import java.text.ParsePosition;
import java.util.Locale;

public class NumericBoundariesDemo {
    private static DecimalFormat formatter(Locale locale) {
        DecimalFormat format = new DecimalFormat(
                "#,##0.00",
                DecimalFormatSymbols.getInstance(locale));
        format.setRoundingMode(RoundingMode.HALF_UP);
        return format;
    }

    private static BigDecimal parseGerman(String input) {
        DecimalFormat parser = new DecimalFormat(
                "#,##0.################",
                DecimalFormatSymbols.getInstance(Locale.GERMANY));
        parser.setParseBigDecimal(true);

        ParsePosition position = new ParsePosition(0);
        Number parsed = parser.parse(input, position);
        if (parsed == null || position.getIndex() != input.length()) {
            throw new IllegalArgumentException("Invalid localized amount");
        }
        return (BigDecimal) parsed;
    }

    public static void main(String[] args) {
        BigDecimal price = new BigDecimal("12345.67");
        BigDecimal fee = new BigDecimal("2.50");
        BigDecimal total = price.add(fee);

        DecimalFormat german = formatter(Locale.GERMANY);
        DecimalFormat us = formatter(Locale.US);

        System.out.println("calculation: " + total.toPlainString());
        System.out.println("display de: " + german.format(total));
        System.out.println("display us: " + us.format(total));

        BigDecimal item = new BigDecimal("1.005");
        System.out.println("single display de: " + german.format(item));
        System.out.println("exact two-item sum: "
                + item.add(item).toPlainString());
        System.out.println("sum display de: "
                + german.format(item.add(item)));

        System.out.println("localized input: "
                + parseGerman("12.348,17").toPlainString());

        String wire = total.toPlainString();
        System.out.println("wire decimal: " + wire);
        System.out.println("roundtrip exact: "
                + (new BigDecimal(wire).compareTo(total) == 0));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac NumericBoundariesDemo.java
java NumericBoundariesDemo
~~~

Đầu ra:

~~~text
calculation: 12348.17
display de: 12.348,17
display us: 12,348.17
single display de: 1,01
exact two-item sum: 2.010
sum display de: 2,01
localized input: 12348.17
wire decimal: 12348.17
roundtrip exact: true
~~~

Ba điểm quan trọng được chương trình chứng minh:

1. **Một tổng chính xác** `BigDecimal` có thể có **nhiều chuỗi hiển thị** khác nhau theo locale, trong khi dữ liệu tính toán không đổi.
2. **Format có làm tròn**: chuỗi hiển thị `1,01` của từng khoản `1.005` không phải giá trị dùng để cộng; tổng chính xác vẫn là `2.010`.
3. **Trao đổi dùng hợp đồng riêng**: chuỗi `12348.17` được đọc lại bởi `new BigDecimal(wire)` cho giá trị toán học giống nguồn, không phụ thuộc locale.

Đây là một chương trình Java thuần chỉ dùng Java standard library, không yêu cầu Spring Boot hay thư viện ngoài.

## 7. Tách ranh giới trong thiết kế ứng dụng

Một tổ chức mã dễ kiểm soát thường có ba lớp trách nhiệm:

| Lớp | Nhận dữ liệu | Trả dữ liệu | Có nên dùng locale? |
| --- | --- | --- | --- |
| Domain/tính toán | `BigDecimal`, đơn vị, quy tắc số học | `BigDecimal` kết quả | Thường không |
| UI/hiển thị | Giá trị domain + `Locale` + tùy chọn hiển thị | Chuỗi để hiển thị | Có |
| API/serialization | Giá trị domain + schema/hợp đồng | JSON/CSV/protocol chuẩn | Theo hợp đồng; tránh dựa vào locale của người dùng |

Gợi ý giao diện phương thức theo trách nhiệm:

~~~java
BigDecimal calculateTotal(List<BigDecimal> amounts);
String formatForUser(BigDecimal value, Locale locale);
String serializeDecimal(BigDecimal value);
BigDecimal parseWireDecimal(String wireValue);
BigDecimal parseLocalizedDecimal(String text, Locale inputLocale);
~~~

Đây chỉ là **chữ ký gợi ý để đặt vào một API thiết kế riêng**, không phải chương trình runnable độc lập. Trong hiện thực, cần xác định các chính sách null, rounding, validation, giới hạn đầu vào và đơn vị tiền tệ. Nên viết test riêng cho các ranh giới để phát hiện lỗi do locale hoặc serialization.

### 7.1. Dữ liệu qua DTO và JSON

Nếu DTO sử dụng `BigDecimal`, thư viện JSON có thể hỗ trợ serialize/deserialize thành số JSON hoặc chuỗi tùy cấu hình. **Không mặc định rằng consumer khác ngôn ngữ sẽ giữ độ chính xác tương đương**. Một consumer đọc number vào `double` có thể mất chữ số dù phía gửi dùng `BigDecimal`. Cần xác định rõ contract JSON và kiểm thử cả producer lẫn consumer.

Ví dụ contract dùng string:

~~~json
{
  "unitPrice": "1.005",
  "quantity": 2,
  "total": "2.010",
  "currency": "EUR"
}
~~~

Nếu có nghiệp vụ làm tròn theo dòng hoặc theo tổng, cần quy định số `total` đã được tính thế nào. Hiển thị thành `2,01` chỉ là một phép format; **không đủ để xác định số tiền đã được làm tròn theo dòng hay theo tổng**.

### 7.2. Dữ liệu trong cơ sở dữ liệu

Với số thập phân cần chính xác, thường dùng cột `DECIMAL`/`NUMERIC` có precision và scale phù hợp. Java đọc/ghi qua `BigDecimal` để tránh chuyển trung gian sang `float`/`double`. Thao tác database có thể áp ràng buộc scale, precision và quy tắc làm tròn riêng; cần kiểm tra schema và hành vi của database/driver cụ thể.

Không lưu những chuỗi như `"12.348,17 EUR"` vào cột giá trị số khi cần truy vấn tổng, lọc và so sánh số. Ký hiệu tiền, nhóm hàng nghìn, dấu thập phân locale là thông tin trình bày; lưu giá trị số và đơn vị theo schema.

### 7.3. Báo cáo và CSV

Một tập tin CSV có thể dùng dấu phẩy phân cột, nên chuỗi hiển thị `"12,348.17"` có dấu phẩy cũng có thể đòi hỏi quoting/escaping. Cách an toàn hơn cho trao đổi máy là thống nhất **delimiter, dấu thập phân, encoding, quy tắc quoting và locale** trong hợp đồng xuất dữ liệu. Không giả định một CSV “dễ đọc bằng Excel ở máy mình” luôn được dịch vụ khác hiểu như nhau.

Với báo cáo dành cho con người, có thể tạo một bản CSV tương thích locale cụ thể; với dữ liệu trao đổi, hãy đưa ra một định dạng có thể parse nhất quán và tài liệu hóa.

## 8. Kiểm tra và thử nghiệm bắt buộc theo ranh giới

Các tình huống nên có trong kiểm thử:

- **Cùng giá trị, nhiều locale:** 12348.17 hiển thị ở US và Đức khác chuỗi nhưng kết quả domain không đổi.
- **Làm tròn hiển thị:** 1.005 format còn 2 chữ số khác với giá trị domain ban đầu.
- **Cộng trước hoặc sau làm tròn:** hai lần 1.005 cho kết quả khác nếu cộng hai chuỗi đã làm tròn; so với hợp đồng nghiệp vụ.
- **Đọc chuỗi giao thức:** `"12348.17"` parse chính xác; từ chối `"12,348.17"` nếu contract chỉ cho phép dạng chuẩn không phân nhóm.
- **Đọc chuỗi locale:** parse `"12.348,17"` với locale phù hợp; phát hiện phần dư không được parser tiêu thụ, kiểm tra group nếu yêu cầu nghiêm ngặt.
- **Scale, precision và số âm:** giá trị `0.10`, `1000`, `1E+3`, số âm, số rất lớn, hoặc nhiều chữ số sau dấu thập phân.
- **Round-trip:** gửi và nhận có bảo toàn **giá trị toán học** không? Nếu cần bảo toàn **scale**, phải kiểm tra thêm scale hoặc sử dụng contract hỗ trợ.

Không dùng phép so sánh chuỗi hiển thị làm phép kiểm tra bằng nhau của số. So sánh giá trị `BigDecimal` bằng `compareTo` nếu chỉ xét giá trị toán học; dùng `equals` nếu còn yêu cầu scale giống nhau.

## 9. Lỗi phổ biến và cách tránh

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| API gửi `"12.348,17"` rồi hệ thống nhận parse lỗi | Chuỗi hiển thị gắn với locale | Gửi dạng chuẩn `"12348.17"` theo contract |
| Số tiền thay đổi khi đổi ngôn ngữ UI | Code dùng chuỗi đã format làm nguồn tính | Giữ `BigDecimal` domain, format chỉ ở lớp trình bày |
| Hai dòng `1.005` hiển thị `1,01`, tổng hiển thị `2,01` | Tổng được cộng chính xác rồi làm tròn một lần | Xác định chính sách làm tròn theo dòng hoặc theo tổng; giải thích nhất quán |
| `Double.parseDouble("1,25")` thất bại | Parser chuẩn không đọc dấu phẩy decimal theo locale | Parse input UI với `DecimalFormat` cấu hình locale |
| `NumberFormat.parse` chỉ đọc được một phần | Parser có thể chấp nhận tiền tố hợp lệ | Dùng `ParsePosition` và kiểm tra cuối chuỗi; xác minh định dạng chặt nếu cần |
| Giá trị từ JSON mất chữ số | Consumer trung gian đọc vào `double` | Định nghĩa schema và kiểu decimal tương thích; dùng chuỗi khi contract yêu cầu |
| Số thập phân được nhân/chia rồi ghi dạng chuỗi theo UI | Chính sách làm tròn bị trộn với format | Áp `setScale`/`MathContext` khi tính theo nghiệp vụ, serialize độc lập |
| Code dùng formatter `static` chia sẻ giữa các request | `DecimalFormat` có trạng thái và không được bảo đảm thread-safe | Tạo formatter theo phạm vi request hoặc quản lý concurrency tường minh |
| Bản ghi chỉ còn `"100.00"` nhưng mất loại tiền | Đơn vị bị xử lý như trang trí | Lưu currency/unit trong domain và contract |
| Chuỗi `"1,234"` được tự đoán tùy máy | Locale không rõ | Chỉ định locale/form input rõ hoặc dùng format chuẩn máy |

## 10. Tự kiểm tra

1. **Khi đổi locale từ Mỹ sang Đức, nên thay đổi số đang tính không?** Không. Chỉ chuỗi hiển thị thay đổi, giá trị `BigDecimal` phải giữ nguyên.
2. **Tại sao `"12.348,17"` không nên là mặc định của một API machine-to-machine?** Nó phụ thuộc locale và có thể bị parse khác nhau. Chọn một contract xác định như chuỗi thập phân dấu chấm, không dấu nhóm.
3. **Vì sao không cộng trực tiếp `"1,01" + "1,01"` khi hai chuỗi vốn là biểu diễn của `1.005`?** Vì formatter đã làm tròn mất thông tin; nghiệp vụ phải chỉ rõ cộng trước hay làm tròn từng khoản.
4. **`BigDecimal.toPlainString()` có luôn giữ scale ban đầu không?** Không trong mọi trường hợp, đặc biệt với scale âm; nó bảo toàn giá trị thập phân để đọc lại, còn scale cần contract riêng nếu quan trọng.
5. **Nếu form nhập theo locale Đức nhưng API nhận dấu chấm thì có mâu thuẫn không?** Không. Hai ranh giới có trách nhiệm khác nhau: parse locale ở UI, rồi serialize chuẩn ở tầng API.
6. **Vì sao `setParseBigDecimal(true)` hữu ích với `DecimalFormat`?** Nó giúp lấy `BigDecimal` trực tiếp từ số thập phân được parse, tránh trung gian `double` đối với trường hợp số thông thường.
7. **Một số được format với `HALF_UP` có làm thay đổi `BigDecimal` gốc không?** Không. `format` tạo chuỗi; thay đổi giá trị để lưu phải là thao tác tính toán được quy định rõ.
8. **Phải ghi gì trong hợp đồng trao đổi số thập phân?** Kiểu biểu diễn (JSON number hay string), dấu thập phân, nhóm chữ số, kiểu nhận ở hai phía, precision/scale, đơn vị và quy tắc làm tròn.

**Ghi nhớ:** **Tính trên số; hiển thị theo locale; trao đổi theo contract.** `BigDecimal` là giá trị miền, `NumberFormat`/`DecimalFormat` tạo chuỗi cho người dùng, còn `toPlainString` hoặc serializer được cấu hình theo schema tạo dạng trao đổi. Không đưa kết quả format hiển thị trở lại phép tính hay mạng dữ liệu nếu chưa có bước parse và chính sách nghiệp vụ phù hợp.