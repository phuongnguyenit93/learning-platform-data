# Phân biệt MessageFormat với String.format và Formatter

## 1. Ba API cùng tạo chuỗi, nhưng giải quyết những việc khác nhau

Khi xây dựng ứng dụng Java có nhiều ngôn ngữ, chúng ta thường cần chèn tên người dùng, số tiền, ngày hoặc số lượng vào văn bản. Java cung cấp ba công cụ dễ bị nhầm:

- **`java.text.MessageFormat`**: tạo **thông điệp cho người dùng** từ một *mẫu câu* với đối số được đánh số `{0}`, `{1}`. Mẫu câu có thể dịch sang các ngôn ngữ khác, thay đổi vị trí các đối số, và chọn định dạng số/ngày theo `Locale`.
- **`String.format(...)`**: tạo một chuỗi bằng cú pháp **`printf`**, chẳng hạn `%s`, `%d`, `%,.2f`, `%1$s`. Phù hợp cho trình bày số, căn lề, tạo log, kết quả kiểm tra hoặc chuỗi có cấu trúc.
- **`java.util.Formatter`**: là **bộ máy đứng sau kiểu định dạng `printf`**, có thể ghi nhiều lần vào một `Appendable` như `StringBuilder`, `Writer` hoặc `System.out` và có trạng thái/chu kỳ sử dụng riêng.

Cả ba đều có thể nhận `Locale`, nhưng **cú pháp mẫu, cách xử lý đối số, khả năng bản địa hóa, hành vi với ngày giờ và đặc tính quản lý đối tượng khác nhau**.

| Câu hỏi | `MessageFormat` | `String.format` | `Formatter` |
| --- | --- | --- | --- |
| Đầu vào mẫu | `"Xin chào {0}"` | `"Xin chào %s"` | `formatter.format("Xin chào %s", name)` |
| Đối số | Chỉ số **0-based** `{0}`, `{1}` | Mặc định theo thứ tự; chỉ số tường minh **1-based** `%1$s`, `%2$d` | Cùng cú pháp với `String.format` |
| Trọng tâm | Câu dịch, sắp xếp lại thành phần thông điệp | Chuỗi trình bày, độ rộng, precision, flags | Ghi nối nhiều kết quả vào một destination |
| Số/ngày theo locale | Qua `{0,number}`, `{0,date}` và subformat | Qua conversion tương ứng như `%,.2f`, `%tF` | Cùng semantics kiểu `printf` |
| Đổi vị trí tham số khi dịch | Tự nhiên với `{1}`, `{0}` | Có `%2$s`, `%1$s` nhưng pattern khó đọc hơn cho biên dịch viên | Tương tự `String.format` |
| Mẫu thường đặt trong ResourceBundle | Rất phù hợp | Có thể dùng nhưng đòi hỏi hiểu cú pháp `printf` | Có thể dùng, cùng ràng buộc `printf` |
| Kiểu kết quả | `String` hoặc ghi vào `StringBuffer` | Trả `String` | Ghi vào `Appendable`, trả `Formatter` để nối thao tác |
| Đa luồng | `MessageFormat` không synchronized | Mỗi lời gọi tạo công việc định dạng riêng | Một `Formatter` dùng chung không bảo đảm thread-safe |

**Quy tắc lựa chọn:** với **câu cần dịch**, ưu tiên `ResourceBundle` + `MessageFormat`; với **chuỗi kỹ thuật, biểu bảng, độ rộng cột, precision, số liệu**, dùng `String.format`; khi cần **ghi nhiều đoạn đã format vào cùng đích**, dùng `Formatter`.

## 2. Cú pháp: `{0}` so với `%s`

### 2.1. MessageFormat: đánh số đối số từ 0

Cấu trúc các phần thay thế của `MessageFormat`:

~~~text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
~~~

Ví dụ:

~~~text
"Chào {0}, bạn có {1,number,integer} thông báo."
~~~

Trong đó:

- `{0}` là **đối số đầu tiên**.
- `{1,number,integer}` là **đối số thứ hai**, được định dạng bằng quy tắc số nguyên phù hợp `Locale`.
- Các loại `formatType` chuẩn của Java 17 gồm `number`, `date`, `time`, `choice`.
- Một số `formatStyle` hợp lệ gồm `integer`, `currency`, `percent`, `short`, `medium`, `long`, `full` hoặc pattern dành riêng cho subformatter.

Ví dụ trực tiếp:

~~~java
MessageFormat message = new MessageFormat(
        "Chào {0}, bạn có {1,number,integer} thông báo.",
        Locale.forLanguageTag("vi-VN")
);
String output = message.format(new Object[]{"Lan", 3});
~~~

Đoạn trên là **mảnh mã trong phương thức**, cần import `java.text.MessageFormat` và `java.util.Locale`. Kết quả phụ thuộc quy ước số của locale (đối số `3` không cần dấu nhóm). Quan trọng là thứ tự đối số có thể thay đổi trong **pattern** mà không cần thay mã cung cấp dữ liệu.

### 2.2. String.format và Formatter: cú pháp printf

Với conversion thông thường:

~~~text
%[argument_index$][flags][width][.precision]conversion
~~~

Một vài thành phần:

| Cú pháp | Công dụng |
| --- | --- |
| `%s` | Biểu diễn đối tượng thành chuỗi |
| `%d` | Số nguyên |
| `%f` / `%.2f` | Số thực / hai chữ số sau dấu thập phân |
| `%,.2f` | Thêm phân nhóm theo locale, hiển thị hai chữ số thập phân |
| `%10s` / `%-10s` | Độ rộng tối thiểu 10, căn phải / căn trái |
| `%04d` | Bổ sung số 0 theo độ rộng 4 |
| `%1$s` / `%2$s` | Tham chiếu đối số **thứ nhất / thứ hai** |
| `%%` | In dấu phần trăm `%` theo nghĩa ký tự |
| `%n` | In dấu xuống dòng theo hệ thống, không lấy đối số |

**Lưu ý chỉ số:** `MessageFormat` bắt đầu từ **`0`**, trong khi chỉ số tường minh của `Formatter` bắt đầu từ **`1$`**. `%0$s` không phải chỉ số đối số hợp lệ của cú pháp `printf`.

Ví dụ:

~~~java
String output = String.format(
        Locale.US,
        "Hello %1$s, count=%2$04d, cost=%3$,.2f",
        "Lan", 7, 1234.5
);
~~~

Đây là mảnh mã trong method với import `java.util.Locale`. Kết quả:

~~~text
Hello Lan, count=0007, cost=1,234.50
~~~

`String.format` chỉ định rõ precision/width/flags; những điều đó giúp tạo dòng báo cáo có bố cục cố định. `MessageFormat` mạnh hơn ở việc biểu diễn **mẫu câu có thể dịch** và sử dụng subformat địa phương hóa.

## 3. Ví dụ chạy được: cùng một dữ liệu, ba cách

Tạo tệp `FormatComparisonDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Formatter;
import java.util.Locale;

public class FormatComparisonDemo {
    public static void main(String[] args) {
        String name = "Lan";
        double amount = 1234.5;

        // 1. Mẫu câu có tham số đánh số từ 0.
        MessageFormat message = new MessageFormat(
                "Hello {0}, balance: {1,number,#,##0.00}",
                Locale.US
        );
        System.out.println("MessageFormat: "
                + message.format(new Object[]{name, amount}));

        // 2. Mẫu kiểu printf, đối số bắt đầu từ 1.
        String oneShot = String.format(
                Locale.US,
                "Hello %1$s, balance: %2$,.2f",
                name, amount
        );
        System.out.println("String.format: " + oneShot);

        // 3. Ghi nhiều lần vào cùng một StringBuilder.
        StringBuilder destination = new StringBuilder();
        try (Formatter formatter =
                     new Formatter(destination, Locale.US)) {
            formatter.format("Hello %s", name);
            formatter.format(", balance: %,.2f", amount);
        }
        System.out.println("Formatter: " + destination);
    }
}
~~~

Biên dịch và chạy trên Java 17+:

~~~bash
javac -encoding UTF-8 FormatComparisonDemo.java
java FormatComparisonDemo
~~~

Kết quả:

~~~text
MessageFormat: Hello Lan, balance: 1,234.50
String.format: Hello Lan, balance: 1,234.50
Formatter: Hello Lan, balance: 1,234.50
~~~

Cùng kết quả nhưng cơ chế khác:

1. `MessageFormat` nhận `Object[]`, chèn theo `{0}` và `{1}`. Subpattern `#,##0.00` do `DecimalFormat` diễn giải với ký hiệu địa phương của `Locale.US`.
2. `String.format` nhận các đối số varargs, xử lý `%1$s` và `%2$,.2f` bằng cú pháp `Formatter`. Nó không đọc mẫu của `MessageFormat`.
3. `Formatter` nhận một `StringBuilder` làm đích và nối hai lần format. Đóng `Formatter` hoàn tất việc dùng đối tượng; `StringBuilder` vẫn giữ văn bản và có thể đọc bằng `toString()`.

**Không thể thay máy móc** `"Hello {0}"` thành đầu vào `String.format`, cũng không thể đưa `"Hello %s"` thẳng vào `MessageFormat` rồi mong cú pháp được diễn giải. Mỗi công cụ có parser pattern riêng.

## 4. Bản địa hóa thông điệp: vì sao MessageFormat phù hợp hơn

Một bản dịch tốt có thể phải đổi **thứ tự các thành phần**, không chỉ đổi từng từ. Ví dụ ngôn ngữ A muốn “{tên} đã đặt {số lượng}”, còn ngôn ngữ B muốn “Đã đặt {số lượng} cho {tên}”. Nếu ghép chuỗi bằng toán tử `+` hoặc dựa hoàn toàn vào thứ tự lập trình viên viết trong mã, biên dịch viên khó điều chỉnh trật tự câu.

`MessageFormat` dùng chỉ số đối số để biên dịch viên giữ đúng dữ liệu và thay đổi trật tự:

~~~java
MessageFormat first = new MessageFormat(
        "{0} ordered {1,number,integer} items.", Locale.US
);
MessageFormat second = new MessageFormat(
        "Đã đặt {1,number,integer} món cho {0}.",
        Locale.forLanguageTag("vi-VN")
);

Object[] args = {"Lan", 3};
System.out.println(first.format(args));
System.out.println(second.format(args));
~~~

Đoạn trên là mảnh mã có `import java.text.MessageFormat;` và `import java.util.Locale;`. Với số `3`, hai kết quả:

~~~text
Lan ordered 3 items.
Đã đặt 3 món cho Lan.
~~~

**Phân biệt với `String.format`:** cú pháp `%2$d` và `%1$s` cũng cho phép đổi vị trí đối số, nhưng người dịch phải hiểu conversion phù hợp với kiểu dữ liệu, flags, precision và escape dấu `%`. Với một **câu dịch** cần định dạng số/ngày và thay đổi cấu trúc câu, `MessageFormat` có ý nghĩa ngữ nghĩa trực tiếp hơn.

### Kết hợp ResourceBundle đúng cách

Trong ứng dụng, pattern không nên bị hard-code cho mọi ngôn ngữ. Một cấu trúc đơn giản:

~~~text
demo/
├── LocalizedMessageDemo.java
├── Messages_en.properties
└── Messages_de.properties
~~~

`Messages_en.properties`:

~~~properties
receipt=Hello {0}, total: {1,number,#,##0.00}.
~~~

`Messages_de.properties`:

~~~properties
receipt=Hallo {0}, Gesamtbetrag: {1,number,#,##0.00}.
~~~

Tạo `LocalizedMessageDemo.java`:

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class LocalizedMessageDemo {
    public static void main(String[] args) {
        Locale locale = Locale.GERMANY;
        ResourceBundle bundle = ResourceBundle.getBundle(
                "Messages", locale
        );

        MessageFormat formatter = new MessageFormat(
                bundle.getString("receipt"), locale
        );

        System.out.println(
                formatter.format(new Object[]{"Lan", 1234.5})
        );
    }
}
~~~

Lưu các file trong cùng thư mục, dùng JDK 17+:

~~~bash
javac -encoding UTF-8 LocalizedMessageDemo.java
java -cp . LocalizedMessageDemo
~~~

Đầu ra với dữ liệu locale Đức thông dụng trong JDK:

~~~text
Hallo Lan, Gesamtbetrag: 1.234,50.
~~~

Trong ví dụ, `ResourceBundle` chọn **mẫu câu**, còn `MessageFormat` dùng **Locale.GERMANY` để định dạng tham số số. Hai việc liên quan nhưng không trùng nhau: khi bundle fallback sang một locale khác, ứng dụng cần có chính sách rõ ràng về locale dùng định dạng số/ngày. Dùng `bundle.getLocale()` hay requested locale là quyết định của sản phẩm, không phải một chân lý áp dụng cho mọi hệ thống.

Các file `.properties` ở Java 17 có thể chứa Unicode UTF-8; kiểm soát encoding trong build và runtime để tránh lỗi dấu tiếng Việt/ký tự quốc tế.

## 5. Locale và kiểu dữ liệu: các API có giới hạn khác nhau

### 5.1. Cách truyền locale

Các phiên bản phổ biến:

~~~java
// MessageFormat: constructor nhận locale.
MessageFormat message =
        new MessageFormat("{0,number,#,##0.00}", Locale.GERMANY);

// String.format: locale là đối số đầu.
String s = String.format(Locale.GERMANY, "%,.2f", 1234.5);

// Formatter: locale được chỉ định khi tạo instance.
StringBuilder out = new StringBuilder();
try (Formatter formatter = new Formatter(out, Locale.GERMANY)) {
    formatter.format("%,.2f", 1234.5);
}
~~~

Đây là các đoạn minh họa trong method với import tương ứng. Nếu bỏ `Locale`:

- `new MessageFormat(pattern)` sử dụng locale mặc định cho danh mục `Locale.Category.FORMAT`.
- `MessageFormat.format(pattern, args...)` là **static convenience method**, tạo một instance dùng locale mặc định; nó **không có overload đầu tiên là `Locale`** giống `String.format(Locale, ...)`.
- `String.format(pattern, args...)` dùng locale mặc định danh mục `FORMAT`; `String.format(locale, pattern, args...)` cho phép truyền tường minh.
- `new Formatter()` và các constructor không nhận locale dùng locale mặc định thích hợp; các constructor nhận `Locale` giúp xác định quy ước ngay khi tạo.
- `Formatter.format(Locale, pattern, args...)` cho phép chỉ định locale cho một lần format trên instance nếu cần.

Trong ứng dụng phục vụ nhiều người dùng, truyền locale của người nhận cho từng thao tác sẽ rõ ràng và tránh phụ thuộc vào mặc định JVM. **Không nên thay `Locale.setDefault(...)` mỗi khi xử lý request**, vì đó là trạng thái dùng chung có thể tác động luồng khác.

### 5.2. Số và tiền

Đối với số:

~~~text
MessageFormat : {0,number,#,##0.00}
printf        : %,.2f
~~~

Hai mẫu có thể hiển thị cùng một số nhưng **không có quy tắc chuyển đổi cú pháp một-một**. Pattern của `MessageFormat` còn chứa cấu trúc thông điệp; pattern của `Formatter` có flags, width, precision và conversion.

Đối với tiền:

~~~java
MessageFormat moneyMessage = new MessageFormat(
        "Amount: {0,number,currency}", Locale.US
);

String withPrintf = String.format(
        Locale.US, "Amount: $%,.2f", 1234.5
);
~~~

Đây là các mảnh mã minh họa. Dòng thứ nhất tạo số tiền theo `NumberFormat.getCurrencyInstance(Locale.US)` ở cấp subformat; dòng thứ hai đặt ký hiệu `$` **bằng literal trong pattern**. Dòng thứ hai có thể sai nếu người dùng muốn EUR, VND hay nếu ký hiệu tiền phải đặt ở vị trí khác. Khi xử lý tiền thực tế, phải biết **Currency của giao dịch** và có thể cấu hình `NumberFormat` hoặc `MessageFormat.setFormatByArgumentIndex(...)` theo yêu cầu nghiệp vụ; không suy diễn đồng tiền chỉ từ địa chỉ người dùng.

### 5.3. Ngày giờ và java.time

`MessageFormat` ở Java 17 dùng các subformat kế thừa như `DateFormat` cho `{0,date}`/`{0,time}`, và chúng thường mong đợi `java.util.Date` hoặc kiểu phù hợp với subformat. Không giả định rằng truyền thẳng `LocalDate` hoặc `LocalDateTime` vào `{0,date}` sẽ hoạt động.

`Formatter` hỗ trợ các conversion ngày giờ `%t...`/`%T...` cho những kiểu đối số thời gian được Javadoc liệt kê; ví dụ `Date`, `Calendar`, `long` và các `TemporalAccessor` thích hợp. Nhưng điều đó **không** có nghĩa `MessageFormat` và `Formatter` dùng cùng API định dạng ngày.

Với `java.time` hiện đại, khi chỉ cần tạo riêng một chuỗi ngày/giờ, thường nên dùng `DateTimeFormatter` tường minh:

~~~java
LocalDate date = LocalDate.of(2025, 7, 14);
String dateText = date.format(
        DateTimeFormatter.ofPattern("d MMMM uuuu", Locale.US)
);
MessageFormat message = new MessageFormat(
        "Scheduled for {0}", Locale.US
);
String output = message.format(new Object[]{dateText});
~~~

Đây là đoạn minh họa trong method, cần import `java.time.LocalDate`, `java.time.format.DateTimeFormatter`, `java.text.MessageFormat` và `java.util.Locale`.

Cách này tạo `dateText` theo locale trước rồi chèn như chuỗi. Tuy nhiên, nếu muốn mẫu câu dịch **tự chọn cách biểu diễn ngày** thì cần thiết kế rõ trách nhiệm của dịch vụ định dạng. `Locale` không tự xác định múi giờ: khi định dạng một thời điểm tuyệt đối phải chọn `ZoneId` riêng.

## 6. Cú pháp escape: nguồn lỗi rất thường gặp

### 6.1. MessageFormat có quy tắc dấu nháy đơn đặc biệt

Trong `MessageFormat`, ký tự **single quote** `'` là ký hiệu dùng để quote cú pháp. Muốn hiển thị dấu nháy đơn thật trong phần pattern, dùng **hai dấu nháy đơn `''`**. Muốn in một dấu ngoặc nhọn `{` hoặc `}` mà không khiến parser hiểu là tham số, phải quote phần literal đó thích hợp.

Ví dụ độc lập:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class QuoteDemo {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "It''s '{'ok'}': {0}",
                Locale.US
        );
        System.out.println(message.format(new Object[]{"yes"}));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 QuoteDemo.java
java QuoteDemo
~~~

Đầu ra:

~~~text
It's {ok}: yes
~~~

Giải thích: `''` biểu thị dấu nháy đơn thật; `'{'` và `'}'` biểu thị dấu ngoặc nhọn theo nghĩa literal, còn `{0}` là placeholder thực sự.

**Bẫy:** một dấu nháy đơn đơn lẻ trong mẫu như `"It's {0}"` có thể vô tình kích hoạt chế độ quote, khiến `{0}` không được thay như mong muốn. Khi đọc pattern từ `ResourceBundle`, người dịch phải được hướng dẫn rõ quy tắc này.

### 6.2. Formatter có quy tắc dấu phần trăm

Trong `String.format` và `Formatter`, dấu `%` mở đầu conversion. Nếu muốn in literal `%`, viết `%%`:

~~~java
String output = String.format(
        Locale.US, "Progress: %d%%", 75
);
System.out.println(output);
~~~

Kết quả:

~~~text
Progress: 75%
~~~

Trong pattern `printf`, dấu nháy đơn `'` **không** phải escape cấu trúc tương tự `MessageFormat`. Ngược lại, dấu `%` trong mẫu của `MessageFormat` thường là ký tự bình thường nếu nó không nằm trong subpattern có quy tắc riêng.

**Không chuyển đổi pattern bằng tìm-thay đơn giản** giữa hai API: có thể tạo câu sai, thiếu đối số hoặc lỗi parser. Khi biên tập viên được phép thay đổi pattern, nên có kiểm tra syntax và bài test định dạng từng locale.

## 7. Format số lượng, số ít/số nhiều

`MessageFormat` có `choice`, có thể lựa chọn một đoạn văn bản theo ngưỡng giá trị:

~~~java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceDemo {
    public static void main(String[] args) {
        String pattern =
                "{0,choice,0#No files|1#One file|1<Many files}";

        MessageFormat message =
                new MessageFormat(pattern, Locale.US);

        System.out.println(message.format(new Object[]{0}));
        System.out.println(message.format(new Object[]{1}));
        System.out.println(message.format(new Object[]{2}));
    }
}
~~~

Biên dịch/chạy:

~~~bash
javac -encoding UTF-8 ChoiceDemo.java
java ChoiceDemo
~~~

Kết quả:

~~~text
No files
One file
Many files
~~~

Đây chỉ là ví dụ ngưỡng cho tập số lượng **không âm**; `choice` **không tự cung cấp** toàn bộ các quy tắc plural phức tạp của mọi ngôn ngữ (ví dụ các dạng ngữ pháp theo 0, 1, 2, vài hoặc nhiều ở một số ngôn ngữ). `String.format`/`Formatter` không có conversion `%plural`: dùng chúng để in số không đồng nghĩa lựa chọn câu văn đúng ngữ pháp.

Khi sản phẩm cần pluralization theo chuẩn CLDR, nên cân nhắc engine i18n có hỗ trợ plural rules (chẳng hạn ICU MessageFormat hoặc thư viện được sản phẩm chọn). Cú pháp và feature set của thư viện ngoài có thể khác `java.text.MessageFormat` trong Java 17; cần kiểm tra API và định dạng pattern trước khi thay thế.

## 8. Stateful Formatter, String.format tiện ích, và MessageFormat có thể cấu hình

### 8.1. Khi nào dùng Formatter trực tiếp?

`String.format` thường đủ cho việc tạo **một chuỗi**:

~~~java
String line = String.format(
        Locale.US, "%-12s | %08d | %,.2f", "Order", 42, 1234.5
);
~~~

`Formatter` hợp lý khi đang xây dựng nhiều phần của cùng output:

~~~java
StringBuilder buffer = new StringBuilder();

try (Formatter formatter = new Formatter(buffer, Locale.US)) {
    formatter.format("Report%n");
    formatter.format("%-10s %8d%n", "Orders", 42);
    formatter.format("%-10s %8.2f%n", "Rate", 3.5);
}

String report = buffer.toString();
~~~

Những đoạn này cần import `java.util.Locale` và `java.util.Formatter`; đây là các mảnh mã có thể đặt trong method.

Với `Formatter`, destination có thể là `Appendable`. Khi gắn với `Writer`/stream có tài nguyên bên ngoài, việc `close()` có thể **đóng destination** nếu nó triển khai `Closeable`; xác định rõ quyền sở hữu tài nguyên. Đóng `Formatter` rồi gọi `formatter.format(...)` nữa sẽ gây lỗi trạng thái. Nếu chỉ cần tạo `String` từ một lần định dạng, `String.format` ngắn và dễ quản lý hơn.

### 8.2. MessageFormat là một đối tượng có thể sửa pattern/subformat

`MessageFormat` cung cấp `applyPattern`, `setLocale`, `setFormatByArgumentIndex` và các phương thức khác để thay đổi cách định dạng. Nó **không bất biến** và **không synchronized**. Cùng một instance bị các luồng thay pattern hay subformat trong lúc đang format có thể gây kết quả không mong muốn.

`Formatter` cũng không bảo đảm an toàn khi nhiều luồng cùng sử dụng. Một cách xử lý rõ ràng là tạo instance theo lời gọi hoặc dùng biện pháp đồng bộ phù hợp. Ngược lại, `String` kết quả là bất biến; bản thân lời gọi tĩnh `String.format(locale, ...)` không yêu cầu bạn chia sẻ `Formatter` có trạng thái với các request khác nhau.

Nếu tối ưu hiệu năng bằng cache `MessageFormat`, có thể lưu pattern đã xác thực và tạo bản sao phù hợp trước khi dùng, hoặc quản lý đồng bộ; không nên chia sẻ trực tiếp một instance mutable không được bảo vệ.

### 8.3. Ngoại lệ khi truyền sai pattern hoặc kiểu

| Lỗi đầu vào | Khả năng gặp |
| --- | --- |
| `MessageFormat` có dấu ngoặc nhọn không cân bằng | `IllegalArgumentException` khi phân tích pattern |
| `MessageFormat` yêu cầu `{0,number}` nhưng nhận kiểu không thích hợp | `IllegalArgumentException` từ quá trình định dạng |
| `String.format` dùng `%d` cho một `String` | `IllegalFormatConversionException` hoặc ngoại lệ họ `IllegalFormatException` |
| `String.format` có conversion hợp lệ nhưng thiếu tham số | `MissingFormatArgumentException` |
| `Formatter` đã đóng rồi vẫn format | `FormatterClosedException` |
| Pattern từ bản dịch có `%` hay dấu `'` sai quy tắc | Mất placeholder, sai chuỗi hoặc lỗi parser |

Vì pattern có thể do người biên tập cung cấp qua file dịch, **kiểm thử bằng dữ liệu mẫu cho từng locale** là rất hữu ích. Đừng coi lỗi định dạng lúc runtime là chuyện chỉ ảnh hưởng mỹ thuật: giao diện có thể không hiển thị thông điệp hoặc mất thông tin quan trọng.

## 9. Phân biệt chuỗi hiển thị với định dạng dữ liệu trao đổi

Cả ba API đều thiên về **presentation**. Các định dạng số/ngày theo locale thường phù hợp với người đọc, nhưng không lý tưởng để làm dữ liệu máy trao đổi.

Ví dụ, cùng số `1234.5` có thể biểu diễn là `1,234.50` hoặc `1.234,50`. Nếu dùng chuỗi này làm số trong JSON, CSV hoặc chuỗi truy vấn mà không có quy ước rõ ràng, phía nhận có thể hiểu sai.

- Dữ liệu trao đổi: dùng JSON number, `BigDecimal`/giao thức số nhất quán, ngày theo ISO-8601 khi phù hợp.
- Dữ liệu hiển thị: dùng `Locale` tường minh và API tương ứng.
- Văn bản cần dịch: lấy mẫu câu từ `ResourceBundle`/hệ thống i18n, sau đó format bằng cơ chế thích hợp.
- Báo cáo có căn lề: `Formatter`/`String.format` phù hợp cho cột và độ rộng; với định dạng Unicode và bảng phức tạp, độ rộng ký tự hiển thị trên terminal còn phụ thuộc font và ký tự nhiều code point.

Một nội dung dịch không trở nên đúng ngữ pháp chỉ vì mọi biến đã được chèn và con số đã có dấu phân nhóm thích hợp. Khi văn bản là câu hoàn chỉnh, phải xem xét ngữ pháp và cấu trúc của ngôn ngữ đích.

## 10. Hướng dẫn chọn API theo tình huống

| Tình huống | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| “Xin chào {tên}, bạn có {số} thông báo” bằng nhiều ngôn ngữ | `ResourceBundle` + `MessageFormat` | Người dịch chủ động đặt vị trí đối số và định dạng |
| Một dòng kiểm tra `"x=12.30; y=4.50"` | `String.format(Locale.ROOT, ...)` hoặc locale xác định | Ngắn gọn, precision rõ ràng; dùng locale thống nhất cho dữ liệu kỹ thuật |
| Căn lề nhiều dòng trong report text | `Formatter` gắn với `StringBuilder`/`Writer` | Ghi nối nhiều lần vào cùng destination |
| Chỉ tạo một nhãn số `1.234,50` | `NumberFormat.getNumberInstance(locale)` | Định dạng số theo locale không cần mẫu thông điệp |
| Chỉ tạo ngày `14 July 2025` từ `LocalDate` | `DateTimeFormatter` với locale | API hiện đại cho ngày giờ |
| Dịch thông điệp có 0/1/nhiều hoặc quy tắc plural phức tạp | `MessageFormat` với `choice` đơn giản; thư viện i18n/CLDR khi phức tạp | Chọn đúng ngữ pháp từng ngôn ngữ |
| In log/diagnostic dùng định dạng ổn định | `String.format(Locale.ROOT, ...)` hoặc format kỹ thuật nhất quán | Tránh phụ thuộc locale mặc định của host |
| Format ngày trong `MessageFormat` | `Date`/subformat được hỗ trợ, hoặc format riêng bằng `DateTimeFormatter` | Tránh truyền trực tiếp `LocalDate` vào subformat kế thừa khi không được hỗ trợ |

### Một checklist ngắn cho code review

1. Mẫu là câu dịch được lấy từ nơi lưu bản dịch, hay chỉ là chuỗi kỹ thuật cần trình bày?
2. Các tham số trong pattern dùng đúng **0-based** (`MessageFormat`) hoặc **1-based** khi chỉ định tường minh (`Formatter`)?
3. `Locale` được truyền rõ ràng chưa? Có đang dựa vô tình vào locale mặc định của JVM không?
4. Có dùng đúng conversion và kiểu đối số? Ngày giờ đã xử lý đúng kiểu dữ liệu và múi giờ chưa?
5. Pattern từ bản dịch có dấu nháy đơn/ngoặc nhọn hoặc dấu `%` cần escape không?
6. Có chia sẻ `MessageFormat`/`Formatter` mutable giữa nhiều luồng không?
7. Thông điệp số lượng có cần pluralization phức tạp hơn `choice`?
8. Output là văn bản cho người đọc hay dữ liệu trao đổi máy? Có nên dùng locale-dependent format ở đây không?

## 11. Bài tập thực hành

1. Viết hai pattern `MessageFormat` tiếng Anh và tiếng Việt sử dụng cùng `Object[] {"Lan", 3}` nhưng đổi vị trí đối số. Dùng `Locale` tường minh khi tạo instance.
2. Thực hiện cùng kết quả `"Lan: 1,234.50"` bằng `MessageFormat`, `String.format` và `Formatter`, rồi đổi `Locale.US` sang `Locale.GERMANY` và so sánh.
3. Sửa chương trình `QuoteDemo` để hiển thị một câu có dấu nháy đơn và dấu ngoặc nhọn. Giải thích tại sao pattern `MessageFormat` cần quote khác cú pháp `printf`.
4. Tạo `String.format(Locale.US, "Value=%08d", 42)`. Thử truyền `"42"` thay vì `42` và quan sát ngoại lệ.
5. Xây dựng mẫu thông điệp theo `ResourceBundle` có tên người và tổng tiền; xác định locale nào dùng để chọn mẫu, locale nào dùng để định dạng số khi xảy ra fallback.
6. Viết một `Formatter` nối ba dòng vào `StringBuilder`; giải thích khi nào phải đóng destination và khi nào chỉ đóng wrapper.
7. Lấy một ngày cố định `LocalDate.of(2025, 7, 14)`, format qua `DateTimeFormatter` thành văn bản ngày rồi chèn vào `MessageFormat`. Vì sao thiết kế này tránh được nhầm lẫn giữa `java.time` và subformat `DateFormat` cũ?

**Ghi nhớ:** `MessageFormat` được thiết kế cho **thông điệp có thể bản địa hóa**, sử dụng placeholder `{0}` bắt đầu từ 0 và các subformat phù hợp locale. `String.format` và `Formatter` sử dụng cú pháp **`printf`**, với tham chiếu tường minh `%1$s` bắt đầu từ 1, mạnh về precision, độ rộng, flags và bố cục. `String.format` tiện cho một lần tạo chuỗi; `Formatter` phù hợp khi ghi nhiều lần vào đích. Chọn API theo bản chất nội dung và luôn kiểm soát locale, kiểu dữ liệu, escape cùng an toàn đa luồng.

### Tài liệu tham khảo

- [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) — cú pháp `{index}`, subformat, dấu nháy đơn, `choice` và đồng bộ.
- [Java SE 17 — Formatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Formatter.html) — cú pháp `printf`, conversion, flags, width, locale, Appendable và an toàn đa luồng.
- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html) — `String.format(...)`.
- [Java SE 17 — DateTimeFormatter](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/format/DateTimeFormatter.html) — định dạng ngày giờ thuộc `java.time`.