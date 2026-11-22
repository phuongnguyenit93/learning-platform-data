# Mẫu thông điệp và đối số theo chỉ số {0}, {1}

`java.text.MessageFormat` cho phép **tạo một mẫu thông điệp chứa những vị trí dành cho dữ liệu động**. Thay vì nối chuỗi cứng trong chương trình, ứng dụng lưu mẫu như `"Xin chào {0}, bạn có {1} thư."` rồi truyền tên người dùng và số thư khi hiển thị. Những ký hiệu `{0}`, `{1}` là **đối số theo chỉ số** (*indexed arguments*) và được thay bằng phần tử tương ứng trong mảng đối số.

Đây là nền tảng quan trọng cho địa phương hóa (localization): cùng một tập dữ liệu, các ngôn ngữ có thể sắp xếp các thành phần câu theo thứ tự khác nhau mà không cần thay đổi code. Khi cần, `MessageFormat` còn định dạng số, ngày và giờ bằng `Locale` cụ thể.

Mục tiêu bài học là hiểu **mẫu thông điệp, ánh xạ chỉ số → giá trị, thứ tự xuất hiện, lặp chỉ số, cú pháp định dạng, escaping và các trường hợp lỗi** để sử dụng đúng với `ResourceBundle`.

## 1. Mẫu thông điệp là gì?

Một mẫu (*pattern*) là chuỗi chứa phần văn bản cố định và các phần thay thế:

~~~text
Xin chào {0}, bạn có {1} thư.
~~~

Trong đó:

- `Xin chào `, `, bạn có ` và ` thư.` là văn bản cố định.
- `{0}` tham chiếu đến **đối số thứ nhất**, ở vị trí chỉ số 0.
- `{1}` tham chiếu đến **đối số thứ hai**, ở vị trí chỉ số 1.
- Giá trị không nằm trong pattern; code truyền các đối số vào khi format.

Ví dụ chương trình độc lập `BasicMessageDemo.java`:

~~~java
import java.text.MessageFormat;

public class BasicMessageDemo {
    public static void main(String[] args) {
        String pattern = "Xin chào {0}, bạn có {1} thư.";
        String result = MessageFormat.format(pattern, "Mai", 3);

        System.out.println(result);
    }
}
~~~

~~~bash
javac -encoding UTF-8 BasicMessageDemo.java
java BasicMessageDemo
~~~

Kết quả:

~~~text
Xin chào Mai, bạn có 3 thư.
~~~

Lời gọi tĩnh `MessageFormat.format(pattern, Object...)` phù hợp cho ví dụ ngắn, nhưng **không cho phép truyền `Locale` trực tiếp trong chữ ký này**; nó tạo một formatter sử dụng locale định dạng mặc định của JVM. Trong dịch vụ nhiều người dùng, nên tạo `MessageFormat` với `Locale` tường minh, như phần tiếp theo.

## 2. Chỉ số bắt đầu từ 0, không bắt đầu từ 1

Cú pháp cơ bản của phần thay thế là:

~~~text
{argumentIndex}
~~~

`argumentIndex` là số nguyên không âm đại diện cho **vị trí trong mảng `Object[]`**, tính từ 0. Cách ánh xạ:

| Pattern | Đối số được sử dụng | Ví dụ |
| --- | --- | --- |
| `{0}` | `arguments[0]` | Tên người nhận |
| `{1}` | `arguments[1]` | Số lượng |
| `{2}` | `arguments[2]` | Giá tiền |
| `{3}` | `arguments[3]` | Thời điểm hoặc thông tin tiếp theo |

Chẳng hạn:

~~~java
Object[] arguments = {"Lan", 5, "tháng 10"};
String pattern = "{0} nhận {1} thông báo trong {2}.";
~~~

Đây là **đoạn mã minh họa bên trong phương thức**. Khi gọi `new MessageFormat(pattern, locale).format(arguments)` với locale thích hợp, ba chỗ thay thế lần lượt lấy từ `arguments[0]`, `arguments[1]`, `arguments[2]`.

**Quan trọng:** `{1}` không có nghĩa “tham số được viết thứ hai trong mẫu”. Nó luôn chỉ **phần tử index 1 của mảng đầu vào**, dù xuất hiện ở đầu câu hay cuối câu.

Java cũng dùng ký hiệu kiểu `{name}` trong một số thư viện/template khác, nhưng `java.text.MessageFormat` chuẩn dùng **chỉ số số nguyên**; `{username}` không phải đối số được đặt tên hợp lệ của API này.

## 3. Thứ tự xuất hiện được phép khác thứ tự đối số

Đặc điểm cốt lõi cho bản dịch: người dịch có thể **đảo vị trí placeholder** mà vẫn dùng cùng bộ tham số.

Ví dụ một thông điệp hiển thị hai giá trị:

~~~text
{0} đã giao {1} cho bạn.
~~~

Một ngôn ngữ khác có thể cần:

~~~text
Bạn nhận {1} từ {0}.
~~~

Cả hai vẫn dùng `arguments[0]` cho người gửi và `arguments[1]` cho đối tượng được giao. Code không phải sửa thứ tự truyền đối số theo thứ tự placeholder trong câu, miễn bản dịch giữ đúng **nghĩa** của từng chỉ số.

Ví dụ runnable `ArgumentOrderDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class ArgumentOrderDemo {
    public static void main(String[] args) {
        Object[] arguments = {"đầu", "cuối"};
        MessageFormat formatter = new MessageFormat(
                "Các vị trí: {1} rồi {0}, sau đó {1}.",
                Locale.US
        );

        System.out.println(formatter.format(arguments));
    }
}
~~~

~~~bash
javac -encoding UTF-8 ArgumentOrderDemo.java
java ArgumentOrderDemo
~~~

Kết quả:

~~~text
Các vị trí: cuối rồi đầu, sau đó cuối.
~~~

Như vậy:

- `{1}` được dùng **trước** `{0}` trong câu.
- Cùng `{1}` xuất hiện **hai lần**, mỗi lần lấy `arguments[1]`.
- Không có cơ chế “tiêu thụ đối số” theo thứ tự một lần rồi bỏ: placeholder là **tham chiếu theo chỉ số**, có thể lặp lại.

Thứ tự trong mảng `arguments` là hợp đồng giữa code và người dịch. Nếu đổi nghĩa của index 0 từ “tên người” sang “số lượng”, mọi bản dịch có `{0}` có thể sai dù cú pháp còn hợp lệ.

## 4. Mẫu có thể dùng một phần hoặc lặp lại đối số

Không bắt buộc pattern phải tham chiếu **tất cả** đối số đã truyền. Ví dụ mẫu `"{1}"` vẫn có thể được format với mảng hai phần tử; phần tử ở index 0 không xuất hiện.

Cũng không bắt buộc các chỉ số xuất hiện liên tiếp trong pattern. Một mẫu `"{2} - {0}"` có thể bỏ qua `{1}`, miễn đối số ở index 2 tồn tại khi cần.

Tuy nhiên, ở lớp nghiệp vụ cần quy ước rõ những trường hợp như vậy để tránh truyền nhầm tham số:

- Đặt thứ tự đối số cố định theo một **mẫu hợp đồng** hoặc kiểu dữ liệu có ý nghĩa.
- Kiểm tra bản dịch không thêm placeholder vượt số lượng tham số code có thể cung cấp.
- Nếu cùng index được dùng nhiều lần với **kiểu định dạng khác nhau**, xem xét kỹ tính nhất quán: `{0}`, `{0,number,integer}` và `{0,number,currency}` có thể tạo ra ba biểu diễn khác nhau của cùng giá trị.

**Lưu ý:** Truyền thêm đối số thường không gây lỗi chỉ vì chúng không được sử dụng; đó không phải cơ chế xác minh đầy đủ tính đúng đắn của mẫu và code.

## 5. Cú pháp đầy đủ: chỉ số, loại định dạng và kiểu hiển thị

Phần thay thế có thể có dạng:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Ba thành phần:

1. **`argumentIndex`:** vị trí trong mảng, ví dụ `0` hoặc `1`.
2. **`formatType`:** loại formatter, thông dụng là `number`, `date`, `time`, `choice`.
3. **`formatStyle`:** kiểu hiển thị; với number có thể là `integer`, `currency`, `percent` hoặc một mẫu số tùy chỉnh; với date/time có thể là `short`, `medium`, `long`, `full` hoặc pattern thích hợp.

Ví dụ:

| Placeholder | Ý nghĩa |
| --- | --- |
| `{0}` | Thay trực tiếp đối số 0; đối tượng số/ngày có thể được định dạng ngầm |
| `{1,number,integer}` | Định dạng đối số 1 như số nguyên để hiển thị |
| `{2,number,#,##0.00}` | Định dạng đối số 2 theo mẫu số cụ thể |
| `{1,number,currency}` | Định dạng đối số 1 dưới dạng tiền tệ theo locale |
| `{2,date,short}` | Định dạng ngày ở đối số 2 theo mẫu ngày ngắn |
| `{2,time,short}` | Định dạng thời gian ở đối số 2 theo mẫu thời gian ngắn |

Dấu phẩy sau `argumentIndex` là cú pháp của `MessageFormat`. Không có dấu phẩy đó thì `{1}` là phần thay thế thông thường.

### Ví dụ có `Locale` tường minh

Tạo `TypedArgumentsDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class TypedArgumentsDemo {
    public static void main(String[] args) {
        String pattern =
                "Order {0}: {1,number,integer} items; " +
                "total {2,number,#,##0.00}";

        MessageFormat formatter =
                new MessageFormat(pattern, Locale.US);

        Object[] arguments = {"A-17", 12, 1234.5};

        System.out.println(formatter.format(arguments));
    }
}
~~~

~~~bash
javac TypedArgumentsDemo.java
java TypedArgumentsDemo
~~~

Kết quả với định dạng số chuẩn `Locale.US`:

~~~text
Order A-17: 12 items; total 1,234.50
~~~

Giải thích:

- `{0}` lấy chuỗi `"A-17"`.
- `{1,number,integer}` định dạng giá trị `12`.
- `{2,number,#,##0.00}` dùng mẫu số, yêu cầu hai chữ số thập phân và nhóm hàng nghìn theo quy tắc Mỹ.
- Mã `Locale.US` xác định quy ước định dạng khi tạo formatter.

Mẫu số `#,##0.00` sử dụng ngôn ngữ pattern của `DecimalFormat`. Ký tự dấu phẩy/dấu chấm **trong pattern** mô tả nhóm và phần thập phân, còn **ký tự đầu ra** được điều chỉnh theo locale. Không nên tự thay dấu trong chuỗi sau khi format.

Đối với dữ liệu tiền, `MessageFormat` chỉ làm công việc hiển thị; nó **không đổi tỷ giá**. Với số tiền chính xác trong nghiệp vụ, ưu tiên `BigDecimal` thay vì tính tiền bằng `double`.

## 6. Placeholder là ký hiệu có ý nghĩa; dấu nháy đơn dùng để escape

Trong pattern của `MessageFormat`, dấu ngoặc nhọn `{` và `}` có ý nghĩa cú pháp. Nếu muốn chúng xuất hiện **nguyên văn**, phải quote đúng quy tắc của `MessageFormat`.

Đặc biệt, dấu nháy đơn `'` là ký tự escape, **không** chỉ là dấu nháy văn bản bình thường:

| Pattern | Ý nghĩa | Kết quả với đối số 0 là `X` |
| --- | --- | --- |
| `Giá trị {0}` | Thay đối số | `Giá trị X` |
| `Giá trị '{0}'` | Quote nguyên đoạn placeholder | `Giá trị {0}` |
| `Giá trị ''{0}''` | Hai nháy đơn biểu diễn một nháy đơn literal | `Giá trị 'X'` |
| `Hiển thị '{0}' và giá trị {0}.` | Một placeholder nguyên văn, một được thay | `Hiển thị {0} và giá trị X.` |

Ví dụ runnable `MessageQuotingDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuotingDemo {
    public static void main(String[] args) {
        MessageFormat quotedWord = new MessageFormat(
                "Người dùng ''{0}'' đã hoàn thành.",
                Locale.US
        );
        MessageFormat literalBraces = new MessageFormat(
                "Hiển thị '{0}' và giá trị {0}.",
                Locale.US
        );

        System.out.println(quotedWord.format(new Object[]{"Lan"}));
        System.out.println(literalBraces.format(new Object[]{"X"}));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MessageQuotingDemo.java
java MessageQuotingDemo
~~~

Kết quả:

~~~text
Người dùng 'Lan' đã hoàn thành.
Hiển thị {0} và giá trị X.
~~~

Ở mẫu đầu, `''` tạo dấu nháy đơn hiển thị, còn `{0}` vẫn được thay. Ở mẫu thứ hai, cặp nháy đơn quanh `{0}` khiến nó trở thành văn bản literal.

### Cạm bẫy với văn bản tự nhiên

Một bản dịch tiếng Anh có dấu apostrophe như `don't` có thể gặp lỗi vì ký tự `'` được hiểu là điểm bắt đầu/kết thúc quote. Trong pattern `MessageFormat`, hãy viết `don''t` để biểu diễn một apostrophe nguyên văn.

Ví dụ:

~~~text
Pattern:  Don''t forget {0}.
Output:   Don't forget X.
~~~

Không dùng escape kiểu `\{0\}` để quote placeholder: dấu backslash không có nghĩa escape dấu ngoặc nhọn như trong nhiều ngôn ngữ lập trình khác. Cũng không tự động bọc mọi placeholder trong dấu nháy đơn, vì làm vậy chúng **không còn được thay bằng đối số**.

Đối với dấu nháy đơn không được đóng trong pattern, Java có quy tắc xử lý riêng khiến kết quả dễ gây bất ngờ. Nên sử dụng pattern cân bằng, viết test cho bản dịch có dấu apostrophe và giải thích quy ước quoting cho người biên dịch bản dịch.

## 7. Đối số thiếu, sai kiểu và mẫu không hợp lệ

### Đối số thiếu

Nếu pattern tham chiếu đến `{1}` nhưng mảng chỉ có `arguments[0]`, việc format có thể **giữ nguyên ký hiệu `{1}`** trong chuỗi đầu ra. Đây là hành vi nguy hiểm vì ứng dụng có thể không báo lỗi mà hiển thị placeholder cho người dùng.

Ví dụ độc lập `MissingArgumentDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class MissingArgumentDemo {
    public static void main(String[] args) {
        MessageFormat formatter =
                new MessageFormat("Thiếu {1}", Locale.US);

        System.out.println(formatter.format(new Object[]{"một"}));
    }
}
~~~

~~~bash
javac -encoding UTF-8 MissingArgumentDemo.java
java MissingArgumentDemo
~~~

Kết quả:

~~~text
Thiếu {1}
~~~

Vì mảng chỉ có một phần tử (index 0), `{1}` chưa được thay. **Không xem việc formatter trả về chuỗi là bằng chứng mẫu đã được cung cấp đủ tham số.**

### Mẫu sai cú pháp

Các pattern như `{abc}` (chỉ số không phải số), `{0` (thiếu dấu đóng) hoặc `{0,unknown}` (loại định dạng không hợp lệ) có thể làm quá trình khởi tạo/`applyPattern` ném `IllegalArgumentException`.

Nên phát hiện lỗi này khi build, test, hoặc tải bản dịch, thay vì chờ đến request của người dùng. Đối với bộ tài nguyên có nhiều locale, cần kiểm thử mọi mẫu, không chỉ locale mặc định.

### Đối số sai kiểu

`{0,number,integer}` kỳ vọng đối số phù hợp với định dạng số. Truyền một chuỗi văn bản không phải số có thể gây `IllegalArgumentException` khi format. `null`, đối tượng ngày, và các kiểu dữ liệu đặc biệt có thể được xử lý theo các nhánh khác nhau của API; không nên dựa vào ép kiểu ngầm khi hợp đồng nghiệp vụ đã xác định kiểu.

Nên tách ba loại lỗi:

- **Lỗi pattern:** không parse được biểu thức thay thế.
- **Lỗi hợp đồng đối số:** index không tồn tại, hoặc kiểu dữ liệu không phù hợp.
- **Lỗi ngữ nghĩa bản dịch:** pattern hợp lệ nhưng người dịch dùng sai index, sai số nhiều hoặc sai ý nghĩa.

Compiler Java không thể tự bảo đảm các chuỗi pattern lấy từ file dịch luôn khớp đối số ở mỗi lời gọi.

## 8. Kết hợp `MessageFormat` và `ResourceBundle`

Trong ứng dụng đa ngôn ngữ, mẫu thông điệp thường nằm trong `ResourceBundle`; `MessageFormat` nhận chuỗi mẫu được lấy từ bundle và thay các đối số.

Ví dụ một bộ tài nguyên gồm hai ngôn ngữ:

**Tệp `Messages_en.properties`:**

~~~properties
notification=Hello {0}, you have {1,number,integer} messages.
~~~

**Tệp `Messages_vi.properties`:**

~~~properties
notification=Xin chào {0}, bạn có {1,number,integer} tin nhắn.
~~~

**Tệp `LocalizedMessageDemo.java`:**

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedMessageDemo {
    private static String notification(Locale locale, String name, int count) {
        ResourceBundle bundle = ResourceBundle.getBundle("Messages", locale);

        MessageFormat formatter =
                new MessageFormat(bundle.getString("notification"), locale);

        return formatter.format(new Object[]{name, count});
    }

    public static void main(String[] args) {
        System.out.println(notification(Locale.ENGLISH, "Mai", 3));
        System.out.println(notification(
                Locale.forLanguageTag("vi"), "Mai", 3));
    }
}
~~~

Chạy trong thư mục chứa cả ba tệp:

~~~bash
javac -encoding UTF-8 LocalizedMessageDemo.java
java -cp . LocalizedMessageDemo
~~~

Kết quả:

~~~text
Hello Mai, you have 3 messages.
Xin chào Mai, bạn có 3 tin nhắn.
~~~

Trong Java 17, `PropertyResourceBundle` hỗ trợ đọc các tài nguyên `.properties` bằng UTF-8 theo cơ chế tương thích của JDK; nên lưu tệp bằng UTF-8 nhất quán. Trong ứng dụng thực tế, đặt bundle trên runtime classpath/module đúng cấu trúc, ví dụ `src/main/resources`.

**Hai đối tượng đảm nhiệm hai việc khác nhau:**

1. `ResourceBundle` **chọn chuỗi mẫu** theo locale và cơ chế tìm kiếm/fallback.
2. `MessageFormat` **thay placeholder và định dạng giá trị** theo locale mà ta truyền khi khởi tạo.

Nếu chỉ truyền locale vào `getBundle` nhưng tạo `new MessageFormat(pattern)` không kèm locale, có thể lấy bản dịch tiếng Việt nhưng lại định dạng số/ngày theo locale mặc định của JVM. Vì vậy nên truyền **cùng locale hiệu lực** vào cả hai khi nghiệp vụ yêu cầu một ngữ cảnh thống nhất.

### Hợp đồng chỉ số giữa code và bản dịch

Trong hai tệp trên, `{0}` **luôn** là tên, `{1}` **luôn** là số lượng. Người dịch được phép đổi thứ tự placeholder trong câu nhưng không được tùy ý đổi ý nghĩa từng index.

Ví dụ câu thông báo ở một ngôn ngữ có thể viết:

~~~properties
notification={1,number,integer} notifications are waiting for {0}.
~~~

Chỉ đổi **thứ tự trong pattern**, không đổi `new Object[]{name, count}`. Đó là lý do indexed arguments hữu ích cho i18n.

Không nên xây một cơ chế thay thế bằng `String.replace("{0}", name)` cho mọi thông điệp: nó không hiểu quoting, kiểu định dạng, tham số lặp hoặc các cú pháp đặc thù của `MessageFormat`.

## 9. Cách truyền đối số cho đúng overload

`MessageFormat` có cả phương thức tĩnh và phương thức instance, dễ dẫn tới nhầm lẫn khi dùng mảng đối số:

~~~java
// Cách ngắn: dùng Locale FORMAT mặc định tại thời điểm format.
String a = MessageFormat.format("Xin chào {0}", "Mai");

// Cách tường minh: tạo formatter với locale cụ thể.
MessageFormat formatter =
        new MessageFormat("Xin chào {0}", Locale.forLanguageTag("vi-VN"));
String b = formatter.format(new Object[]{"Mai"});
~~~

Đây là **đoạn đặt trong phương thức**, cần import `java.text.MessageFormat` và `java.util.Locale`. Hai cách đều trả nội dung `Xin chào Mai` trong ví dụ này, nhưng **cách thứ hai kiểm soát locale** và rõ ràng khi đối số là số/ngày.

Với phương thức instance `format(Object[] arguments)`, mỗi vị trí trong mảng khớp một chỉ số trong mẫu. Khi API nhận `Object...` dạng varargs, các đối số truyền bằng danh sách cũng được đóng thành mảng. Hãy đọc đúng chữ ký overload thay vì truyền nhầm một `Object[]` làm **một** đối số duy nhất trong các API tự xây.

Nếu nhiều phương thức nghiệp vụ cùng dùng một pattern, nên tạo một hàm có tham số mang tên có ý nghĩa, chẳng hạn `formatTransfer(sender, recipient, amount, locale)`, rồi trong hàm mới gói thành `Object[]{sender, recipient, amount}` theo quy ước ổn định. Việc này tránh rải thứ tự chỉ số ở nhiều nơi.

## 10. Locale quyết định hình thức số/ngày, nhưng không đổi ý nghĩa index

Xét mẫu:

~~~text
{0} đặt {1,number,integer} sản phẩm vào ngày {2,date,short}.
~~~

Các phần tử có thể gồm tên người, số lượng và đối tượng ngày:

~~~java
Object[] arguments = {
        "Mai",
        4,
        new java.util.Date(0)
};
~~~

Đây là **đoạn minh họa**, không phải chương trình hoàn chỉnh. Khi tạo formatter bằng `new MessageFormat(pattern, locale)`:

- `{0}` vẫn là tên, dù locale thay đổi.
- `{1,number,integer}` dùng quy ước số của locale.
- `{2,date,short}` dùng quy tắc ngày ngắn của locale cho đối tượng thời gian phù hợp.

Một `java.util.Date` biểu diễn thời điểm, nên hình thức hiển thị ngày cũng có thể phụ thuộc múi giờ được formatter bên dưới chọn. Với Java Time (`LocalDate`, `Instant`), `MessageFormat` chuẩn không mặc nhiên hỗ trợ tất cả kiểu thời gian mới theo cùng cách như `DateTimeFormatter`; có thể chuyển đổi thích hợp hoặc **định dạng trước** bằng `java.time.format.DateTimeFormatter` rồi truyền chuỗi.

Đừng giả định `MessageFormat` tự chuyển đổi tiền tệ hoặc múi giờ. Nó chỉ áp dụng formatter theo tham số; nhu cầu chuyển đổi đơn vị, tỷ giá và logic thời gian phải được giải quyết riêng.

### Vì sao kết quả localized có thể khác theo JDK?

Dữ liệu CLDR/provider của runtime quyết định nhiều ký hiệu, mẫu ngày, quy tắc nhóm số và dạng tên. Do đó cùng pattern và tham số có thể cho chuỗi hơi khác ở hai phiên bản runtime. Khi muốn ví dụ hoặc snapshot test ổn định, nên chọn locale cụ thể, cố định môi trường kiểm thử và tránh so sánh các ký tự Unicode nhìn giống nhau (dấu cách thường và non-breaking space).

## 11. Các quy tắc hiển thị số nhiều và giới hạn của placeholder chỉ số

`{0}`, `{1}` giúp **chèn và sắp xếp** dữ liệu; chúng **không tự chọn ngữ pháp số ít/số nhiều** cho một ngôn ngữ. Ví dụ pattern tiếng Anh:

~~~properties
notification=You have {0,number,integer} messages.
~~~

Sẽ cho `You have 1 messages.` với số 1: placeholder chỉ thay con số, không biến `messages` thành `message`. Tương tự, câu tiếng Việt có thể cần cách diễn đạt tự nhiên khác tùy số lượng hoặc bối cảnh.

Java có định dạng `choice` trong `MessageFormat` để chọn văn bản theo ngưỡng số, nhưng ngữ pháp số nhiều của các ngôn ngữ trên thế giới phong phú hơn nhiều so với vài điều kiện ngưỡng. Với ứng dụng quốc tế lớn, có thể cần giải pháp i18n có quy tắc plural dành cho từng ngôn ngữ, ví dụ thư viện hỗ trợ ICU MessageFormat, hoặc hệ thống message catalog có cơ chế plural phù hợp.

**Không nên tự tuyên bố mẫu có `{0,number,integer}` là bản dịch “đã xử lý số nhiều”.** Bài học này tập trung vào **đối số theo chỉ số**, không thay thế một chủ đề riêng về plural rules.

## 12. Chuỗi dữ liệu người dùng và an toàn của pattern

Nếu tên người dùng là `"{1}"` và code truyền nó như **đối số**, giá trị đó được xem là dữ liệu, **không tự biến thành placeholder mới cần đánh giá** trong cách format thông thường. Đây là lý do nên tách rõ **pattern** do ứng dụng kiểm soát và **argument** do người dùng/nhà cung cấp dữ liệu đưa vào.

Ngược lại, đưa nội dung đầu vào tùy ý vào **pattern** có thể gây lỗi cú pháp, tạo đầu ra khó dự đoán hoặc làm phức tạp việc kiểm soát nội dung. Không nên xây mẫu bằng cách nối trực tiếp nội dung không tin cậy vào chuỗi pattern.

Ví dụ cần tránh:

~~~java
// Không nên: lời người dùng được nối trực tiếp vào pattern.
String pattern = "Bình luận: " + userInput + " - {0}";
MessageFormat formatter = new MessageFormat(pattern, locale);
~~~

Nếu `userInput` chứa dấu `'` hoặc `{...}`, parser có thể hiểu nhầm thành cú pháp pattern. Cách an toàn về mặt phân tách dữ liệu:

~~~java
String pattern = "Bình luận: {0} - {1}";
MessageFormat formatter = new MessageFormat(pattern, locale);
String rendered = formatter.format(new Object[]{userInput, status});
~~~

Hai đoạn trên là **snippet trong phương thức**, với `userInput`, `locale` và `status` được khai báo ở code gọi. Phần thay thế bằng đối số giúp tránh việc nội dung đầu vào điều khiển **cú pháp MessageFormat**. Tuy nhiên nếu kết quả sẽ đưa vào HTML, SQL hoặc lệnh shell, ứng dụng vẫn cần escaping/encoding theo **ngữ cảnh đầu ra** và dùng API an toàn chuyên biệt; `MessageFormat` không phải HTML sanitizer.

## 13. Vòng đời formatter và sử dụng nhiều luồng

`MessageFormat` là lớp **mutable**, với các phương thức như `applyPattern(...)`, `setFormat(...)` và `setLocale(...)`. Theo hợp đồng của API, việc chia sẻ một instance cho nhiều luồng mà không đồng bộ không được bảo đảm an toàn.

Đừng cache một `static MessageFormat` rồi dùng cho mọi request khác locale. Thiết kế đó có thể sai cả **locale** lẫn **thread-safety**.

Các lựa chọn:

- Tạo một `MessageFormat(pattern, locale)` mới khi cần, đặc biệt nếu số lượng format không lớn.
- Cache **pattern bất biến** theo message key/locale, rồi tạo formatter mới cho mỗi lượt sử dụng.
- Nếu thực sự cần cache formatter, dùng bản sao/chiến lược đồng bộ an toàn sau khi đo hiệu năng và hiểu các thiết lập locale/pattern.

Với ứng dụng đa người dùng, hãy chọn locale của từng request tường minh. Không gọi `Locale.setDefault(...)` để phục vụ riêng request, vì trạng thái default là chung cho JVM và có thể gây trộn dữ liệu giữa các luồng.

## 14. Kiểm thử contract giữa pattern và arguments

Một danh mục kiểm thử thực tế nên gồm:

| Trường hợp | Kiểm tra |
| --- | --- |
| Pattern dùng `{0}` và `{1}` | Đúng giá trị index 0 và 1 |
| Bản dịch đảo `{1}` trước `{0}` | Không đảo dữ liệu đầu vào theo thứ tự xuất hiện |
| Chỉ số lặp | Cùng tham số được chèn ở mọi vị trí |
| Thiếu `arguments[1]` | Không để `{1}` lộ ra giao diện |
| Thừa đối số | Không coi formatter chạy thành công là kiểm tra hợp đồng |
| Kiểu number/date | Giá trị có kiểu phù hợp với formatter |
| Mẫu có apostrophe | `''` và quote literal được xử lý đúng |
| Mẫu được lấy từ bundle | Có key, pattern hợp lệ, locale chính xác |
| Ngôn ngữ khác nhau | Có thể đổi cấu trúc câu mà giữ nguyên nghĩa index |
| Chạy đồng thời | Không chia sẻ `MessageFormat` mutable thiếu đồng bộ |

Khi kiểm tra placeholder, **không nên chỉ tìm chuỗi `"{0}"` đơn giản bằng regex** rồi coi đủ: pattern có thể chứa `{0,number,integer}`, placeholder được quote thành literal, hoặc một số trường hợp nested format. Với nhiều locale, nên dùng parser/cơ chế kiểm thử phù hợp hoặc các trường hợp mẫu đại diện, đồng thời so sánh kết quả thực tế theo đặc tả nội dung.

Một chương trình kiểm thử chất lượng cần bao quát mọi locale mà sản phẩm công bố hỗ trợ, các mẫu có index khác nhau và các chuỗi có dấu nháy đơn. Khi phát hiện bản dịch đổi vị trí index nhưng vẫn có cú pháp hợp lệ, kiểm tra **ý nghĩa của đối số** mới xác định đúng/sai.

## 15. Những nhầm lẫn thường gặp

1. **“`{1}` là đối số thứ nhất.”** Sai: index bắt đầu từ 0; `{1}` là phần tử thứ hai.
2. **“Thứ tự placeholder phải giống thứ tự mảng.”** Sai: `{1}` có thể đứng trước `{0}`; đây là khả năng quan trọng khi dịch câu.
3. **“Mỗi index chỉ dùng được một lần.”** Sai: cùng `{0}` có thể lặp ở nhiều nơi.
4. **“Mẫu sẽ báo lỗi ngay nếu thiếu index.”** Không luôn đúng; có trường hợp placeholder thiếu được giữ nguyên trong đầu ra.
5. **“`{name}` là tên đối số hợp lệ của `java.text.MessageFormat`.”** Sai: API chuẩn dùng chỉ số số nguyên.
6. **“Bọc `{0}` trong dấu nháy đơn để có dấu nháy quanh kết quả.”** Sai: `'{0}'` tạo chữ `{0}` nguyên văn; muốn dấu nháy hiển thị quanh giá trị dùng `''{0}''`.
7. **“Dùng dấu `\` để escape dấu ngoặc nhọn.”** Không đúng theo cú pháp pattern của `MessageFormat`.
8. **“Mẫu số `#,##0.00` luôn sinh dấu chấm thập phân.”** Sai: đầu ra phụ thuộc locale, dấu trong pattern có ý nghĩa quy ước.
9. **“`MessageFormat` tự dịch nội dung.”** Sai: bản dịch là mẫu do ứng dụng cung cấp (ví dụ qua `ResourceBundle`).
10. **“MessageFormat là thread-safe vì chỉ định dạng chuỗi.”** Sai: lớp có trạng thái mutable và không bảo đảm thread-safe.
11. **“`{0,number,integer}` xử lý số nhiều.”** Sai: nó định dạng số, không chọn dạng từ.
12. **“Có thể đưa nguyên văn đầu vào người dùng vào pattern.”** Dễ làm hỏng cú pháp; truyền đầu vào như đối số.

## 16. Quy trình áp dụng vào dự án thực tế

1. **Định nghĩa message key và hợp đồng index**: ví dụ `order.confirmed` có index 0 = mã đơn, 1 = số lượng, 2 = số tiền.
2. **Lưu mẫu theo ngôn ngữ** trong các bundle/catalog và cho phép người dịch thay đổi **vị trí xuất hiện** của placeholder.
3. **Giữ placeholder nhất quán về ý nghĩa** giữa các bản dịch; khi cần định dạng kiểu cụ thể, chỉ định `number`/`date`/`time` hợp lý.
4. **Truyền `Locale` hiệu lực tường minh** cho `MessageFormat` để không phụ thuộc vào default JVM.
5. **Truyền giá trị động thành đối số**, không nối chúng vào pattern.
6. **Kiểm thử bản dịch**: chỉ số đủ, kiểu đúng, escaping apostrophe, ngữ pháp số nhiều, fallback và đầu ra các locale chính.
7. **Quản lý vòng đời formatter**: tránh dùng chung mutable instance mà không có chiến lược thread-safety.
8. **Encode nội dung ở ranh giới xuất ra** nếu chuỗi cuối đưa vào HTML hoặc định dạng nhạy cảm khác.

### Câu hỏi tự kiểm tra

**1.** Với `new Object[]{"Lan", 5}`, `{1}` lấy dữ liệu nào?

**Đáp án:** Số `5` (phần tử index 1); `{0}` lấy chuỗi `"Lan"`.

**2.** Pattern `"{1} - {0} - {1}"` có hợp lệ không?

**Đáp án:** Hợp lệ. Với mảng `{"A", "B"}`, kết quả là `B - A - B`.

**3.** Vì sao khi dịch câu có thể đặt `{1}` trước `{0}`?

**Đáp án:** Placeholder tham chiếu theo index, không phụ thuộc vị trí xuất hiện, nên bản dịch có thể đổi thứ tự từ tự nhiên.

**4.** Làm thế nào để hiển thị dấu nháy đơn quanh giá trị `{0}`?

**Đáp án:** Dùng `''{0}''` trong pattern `MessageFormat`.

**5.** Khi nào pattern và giá trị cần sử dụng cùng locale?

**Đáp án:** Khi ứng dụng cần bản dịch và định dạng giá trị theo một ngữ cảnh người dùng nhất quán: lấy mẫu từ bundle theo locale và tạo `MessageFormat(pattern, locale)`.

**6.** Vì sao chuỗi trả về `Thiếu {1}` là dấu hiệu cần kiểm tra đầu vào?

**Đáp án:** Index 1 có thể chưa được cung cấp; `MessageFormat` không bắt buộc ném lỗi cho mọi trường hợp thiếu index.

**Ghi nhớ:** `{0}`, `{1}`, `{2}` là **hợp đồng vị trí giữa mẫu thông điệp và mảng đối số**. Thứ tự xuất hiện được phép thay đổi theo ngôn ngữ; dữ liệu gắn với mỗi index phải giữ đúng ý nghĩa. Kết hợp `ResourceBundle` để chọn mẫu, `MessageFormat` để thay/định dạng đối số, và kiểm thử đầy đủ các trường hợp escaping, index thiếu và locale.