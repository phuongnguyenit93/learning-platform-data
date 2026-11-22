# Các kiểu number, date, time và choice của MessageFormat trong Java

## 1. MessageFormat làm gì?

`java.text.MessageFormat` ghép một **mẫu thông điệp** (message pattern) với các đối số để tạo chuỗi cho người dùng. Thay vì viết cố định `"Có " + count + " đơn hàng"`, người viết bản dịch có thể quyết định thứ tự từ và cách biểu diễn số, ngày giờ tùy theo `Locale`.

`MessageFormat` dùng dấu ngoặc nhọn để khai báo các *format element*:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Trong đó:

- `argumentIndex`: vị trí đối số bắt đầu từ `0` trong mảng truyền vào `format(...)`.
- `formatType`: một trong `number`, `date`, `time`, `choice`; bỏ trống type thì đối số được định dạng theo kiểu mặc định của nó.
- `formatStyle`: tên style có sẵn (ví dụ `integer`, `currency`, `short`) hoặc chuỗi pattern riêng phù hợp với kiểu.

Ví dụ một mẫu tiếng Anh:

```text
"You bought {0,number,integer} items on {1,date,long}."
```

Đối số `0` là một số, đối số `1` phải là giá trị ngày giờ phù hợp (thường là `java.util.Date`). `MessageFormat` sẽ đặt chúng vào thông điệp theo quy tắc của locale được cấu hình.

**Phạm vi bài:** bốn kiểu `number`, `date`, `time`, `choice`, cách kiểm tra ranh giới, locale, time zone, và lỗi thường gặp khi kết hợp chúng. Bài không coi `choice` là giải pháp đầy đủ cho mọi quy tắc số nhiều của tất cả ngôn ngữ.

## 2. Cấu trúc API và tác động của Locale

Để tạo một formatter cho locale cố định:

```java
Locale locale = Locale.forLanguageTag("en-US");
MessageFormat mf = new MessageFormat(
        "Total: {0,number,currency}", locale);
String text = mf.format(new Object[] {1234.5});
```

*Đoạn minh họa đặt trong một phương thức Java; nó cần import `java.text.MessageFormat` và `java.util.Locale`.*

`MessageFormat` giữ mẫu và `Locale` được thiết lập bằng constructor hoặc `setLocale(...)`. Mẫu được biên dịch thành các phần literal và formatter cho từng vị trí đối số. Khi thay locale, có thể cần áp dụng lại pattern để tạo lại các formatter theo locale mới; cách đơn giản là **khởi tạo một `MessageFormat` riêng cho mỗi locale**.

Hai điểm dễ nhầm:

1. `new MessageFormat(pattern, Locale.US)` điều khiển quy tắc ngôn ngữ/định dạng. `MessageFormat.format(pattern, args...)` là phương thức tĩnh tiện dụng sử dụng locale mặc định `FORMAT` của JVM, nên khó dự đoán hơn trong test phụ thuộc môi trường.
2. `MessageFormat` là đối tượng **mutable**, không được đảm bảo an toàn khi dùng đồng thời trên nhiều thread nếu có thay đổi cấu hình. Không chia sẻ một instance và gọi `applyPattern(...)`, `setFormat(...)` hoặc `setLocale(...)` từ nhiều request không được đồng bộ. Cách đơn giản nhất trong code web là khởi tạo formatter theo request hoặc dùng chiến lược quản lý instance an toàn.

Đối số là mảng `Object[]`. Khi mẫu chỉ định kiểu, đối số phải thích hợp: `number` cần `Number`, `date`/`time` cần `Date` hoặc kiểu thời gian được API định dạng chấp nhận. Riêng `LocalDate` hay `Instant` của `java.time` không tự động được xử lý như `Date` trong format element `date/time` của `MessageFormat`; nên chuyển đổi có chủ đích hoặc dùng `DateTimeFormatter` riêng.

## 3. Format type `number`

`number` dùng cơ chế `NumberFormat`/`DecimalFormat` để hiển thị đối số số. Cùng một giá trị có thể có các cách thể hiện khác nhau:

| Pattern element | Ý nghĩa | Ví dụ theo `Locale.US` |
| --- | --- | --- |
| `{0,number}` | Dạng số thông thường theo locale | `1,234.5` cho `1234.5` |
| `{0,number,integer}` | Số nguyên dùng quy tắc format/làm tròn | `1,234` cho `1234` |
| `{0,number,currency}` | Kiểu tiền tệ theo locale và quy tắc formatter | `$1,234.50` cho `1234.5` |
| `{0,number,percent}` | Giá trị nhân 100 rồi thêm ký hiệu phần trăm | `26%` cho `0.256` khi làm tròn theo formatter |
| `{0,number,#,##0.00}` | Mẫu `DecimalFormat` tự định nghĩa | `1,234.50` cho `1234.5` |

### 3.1. Số thông thường và integer

Với `{0,number,integer}`, Java dùng NumberFormat với style số nguyên, có thể **làm tròn** khi đối số có phần thập phân. Vì vậy, không dùng style này như cách ép kiểu sang `int`, kiểm tra giá trị có nguyên hay không, hoặc bảo toàn số thập phân. Cần validation nghiệp vụ trước khi quyết định định dạng.

Các dấu phân cách và cách nhóm phụ thuộc locale. Không nên tự thay dấu chấm bằng dấu phẩy hay dùng `String.format` với locale mặc định rồi đưa lại vào `MessageFormat`.

### 3.2. Currency không đồng nghĩa chuyển đổi tiền

`{0,number,currency}` tạo giá trị với định dạng tiền của locale, chẳng hạn `Locale.US` thường hiển thị ký hiệu `$`. Nó **không đổi 1234.5 USD sang 1234.5 VND**, cũng không tra tỷ giá. Đơn vị tiền tệ thực và tỷ giá thuộc dữ liệu nghiệp vụ.

Nếu giao dịch được ghi theo một currency cụ thể khác với currency thường gắn cho locale, hãy tạo `NumberFormat.getCurrencyInstance(locale)`, gọi `setCurrency(Currency.getInstance("EUR"))` theo giá trị giao dịch, rồi gắn formatter bằng `setFormatByArgumentIndex(...)` hoặc xử lý riêng tiền trước khi chèn. Không đánh đồng định dạng và chuyển đổi số tiền.

### 3.3. Percent nhân giá trị với 100

`{0,number,percent}` hiểu `0.256` là tỷ lệ `25.6%` và với số chữ số thập phân mặc định của locale, có thể hiển thị `26%`. Nếu đối số nghiệp vụ đã được lưu là `25.6` theo đơn vị phần trăm, dùng `percent` trực tiếp sẽ nhân 100 thêm lần nữa. Cần thống nhất dữ liệu nguồn là **fraction 0–1** hay **percent points 0–100**.

### 3.4. Pattern số tự định nghĩa

`{0,number,#,##0.00}` sử dụng cú pháp pattern của `DecimalFormat`: `0` là chữ số bắt buộc, `#` là chữ số tùy chọn, dấu phẩy trong mẫu thể hiện grouping và dấu chấm trong mẫu thể hiện ranh giới phần thập phân. **Dấu hiển thị thực tế vẫn do locale quyết định**. Các pattern số phức tạp có dấu ngoặc, ký tự literal và ký hiệu tiền cần đọc theo quy tắc `DecimalFormat`, không tự coi mọi dấu phẩy trong format element là dấu phân chia tham số.

Để format tiền chính xác, số nguồn thường nên dùng `BigDecimal` và quy tắc làm tròn nghiệp vụ rõ ràng; `MessageFormat` chỉ giải quyết cách hiển thị.

## 4. Format type `date`

`{0,date,...}` chọn cách hiển thị ngày của đối số thời gian dựa trên `DateFormat`. Các style chuẩn:

| Style | Pattern | Ý nghĩa |
| --- | --- | --- |
| Mặc định | `{0,date}` | Dùng style mặc định cho ngày. |
| Short | `{0,date,short}` | Ngày ngắn, thường dạng chữ số. |
| Medium | `{0,date,medium}` | Ngày ở mức trung bình. |
| Long | `{0,date,long}` | Ngày dài, có thể có tên tháng. |
| Full | `{0,date,full}` | Ngày đầy đủ, có thể có tên thứ. |
| Custom | `{0,date,yyyy-MM-dd}` | Mẫu `SimpleDateFormat` riêng. |

Các style `short`/`medium`/`long`/`full` **không phải chuỗi ngày cố định**. Thứ tự ngày/tháng/năm, dấu tách, chữ tháng và tên thứ phụ thuộc locale cùng dữ liệu locale của JDK. Điều này phù hợp cho UI bản địa hóa, nhưng không phù hợp để mã hóa ngày vào API hoặc database. Khi trao đổi dữ liệu, dùng kiểu ngày hoặc chuẩn serialization rõ ràng, ví dụ ISO 8601.

**Điểm quan trọng:** `MessageFormat` dùng hệ `java.text.DateFormat` dựa trên thời điểm/ngày kiểu `Date`. Để format `LocalDate` trong Java hiện đại, nên dùng `java.time.format.DateTimeFormatter` (với `Locale` rõ ràng) rồi đưa chuỗi kết quả vào thông điệp, hoặc chuyển sang kiểu `Date` bằng quy tắc time zone nếu thực sự cần tương thích `java.text`.

Mẫu tùy chỉnh `yyyy-MM-dd` trong `MessageFormat` được diễn giải theo `SimpleDateFormat`. Ký hiệu `y`, `M`, `d` có ý nghĩa riêng; đừng nhầm với pattern `DateTimeFormatter` trong `java.time`, vì hai API có sự khác nhau ở một số ký hiệu và quy tắc xử lý.

## 5. Format type `time`

`{0,time,...}` định dạng phần thời gian từ cùng kiểu đối số tương thích `DateFormat`. Styles phổ biến:

| Style | Pattern | Ý nghĩa |
| --- | --- | --- |
| Mặc định | `{0,time}` | Dùng style mặc định của thời gian. |
| Short | `{0,time,short}` | Giờ và phút trong bố cục ngắn theo locale. |
| Medium | `{0,time,medium}` | Có thể hiển thị giây. |
| Long | `{0,time,long}` | Có thể có zone hoặc độ lệch giờ. |
| Full | `{0,time,full}` | Biểu diễn đầy đủ theo dữ liệu locale/JDK. |
| Custom | `{0,time,HH:mm:ss}` | Giờ 24h, phút và giây với `SimpleDateFormat`. |

**Locale khác time zone.** Locale có thể ảnh hưởng cách trình bày giờ (12h/24h, tên, ký hiệu), còn `TimeZone`/`ZoneId` quyết định giờ địa phương của một thời điểm. Nếu tạo `MessageFormat` sử dụng formatter mặc định mà không định timezone, đầu ra ngày/giờ có thể khác giữa máy cá nhân và CI.

Để có kết quả cố định cho một `Date` đại diện cho `Instant`, thiết lập timezone lên các formatter `DateFormat` nằm trong `MessageFormat`:

```java
MessageFormat message = new MessageFormat(
        "day={0,date,yyyy-MM-dd}; time={0,time,HH:mm:ss}",
        Locale.US);

for (java.text.Format format : message.getFormats()) {
    if (format instanceof java.text.DateFormat dateFormat) {
        dateFormat.setTimeZone(java.util.TimeZone.getTimeZone("UTC"));
    }
}

System.out.println(message.format(new Object[] {new java.util.Date(0L)}));
// day=1970-01-01; time=00:00:00
```

Đây là đoạn code đặt trong phương thức Java có import hoặc tên class đầy đủ. `getFormats()` trả các formatter của từng format element theo thứ tự xuất hiện; vì cùng đối số `0` được dùng trong cả `date` và `time`, duyệt **toàn bộ `getFormats()`** giúp thiết lập timezone cho cả hai formatter. Không thay default timezone toàn JVM chỉ để chạy một format test.

Các formatter ngày giờ có thể phải được tạo lại sau `applyPattern(...)` hoặc thay đổi mẫu/locale. Khi dùng format object riêng, cấu hình trước rồi đưa vào `MessageFormat` bằng API thích hợp để tránh phụ thuộc cấu hình mặc định.

## 6. Format type `choice`

`choice` chọn một đoạn thông điệp theo một giá trị số, sử dụng cú pháp `ChoiceFormat`:

```text
{0,choice,0#no files|1#one file|1<more than one file}
```

- `0#no files`: áp dụng khi giá trị nằm từ giới hạn 0 trở lên đến trước giới hạn tiếp theo.
- `1#one file`: áp dụng tại đúng giá trị 1 theo các nhánh được sắp giới hạn.
- `1<more than one file`: áp dụng khi giá trị **lớn hơn 1**.
- Dấu `|` phân tách các nhánh.
- Dấu `#` biểu diễn giới hạn **bao gồm** tại giá trị đặt sau nó; `<` biểu diễn ranh giới **loại trừ** giá trị giới hạn (strictly greater).
- Các giới hạn số cần sắp đúng thứ tự tăng và thiết kế nhánh phù hợp với tập dữ liệu đầu vào.

**Chú ý ranh giới và giá trị ngoài phạm vi:** `ChoiceFormat` dựa trên các giới hạn numeric, và với giá trị nhỏ hơn nhánh đầu nó vẫn dùng thông điệp của nhánh đầu. Ví dụ mẫu mở đầu ở 0 có thể hiển thị `no files` cho số âm. Không dùng cách này để validate dữ liệu đếm âm; kiểm tra input riêng trước khi format.

### 6.1. Lựa chọn chuỗi và định dạng lồng nhau

Có thể cho kết quả lựa chọn chứa một format element khác để chèn lại chính số đã dùng:

```text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

Với giá trị `0`, `1`, `2`, kết quả lần lượt là `no files`, `one file`, `2 files`. `MessageFormat` có thể xử lý pattern con trong kết quả `choice` khi kết quả chứa dấu ngoặc format element; vì vậy cần đặc biệt cẩn thận với dấu nháy đơn, dấu ngoặc nhọn và chuỗi lồng nhau.

### 6.2. Khi nào choice chưa đủ?

`ChoiceFormat` là lựa chọn theo **ngưỡng số**, rất phù hợp để giải thích cơ chế chọn thông điệp, hoặc giải quyết một số trường hợp đơn giản. Tuy nhiên:

- Quy tắc số nhiều của các ngôn ngữ có thể phụ thuộc 0, 1, 2, 3–4, nhiều lớp ngữ pháp hoặc phần thập phân, chứ không chỉ các ngưỡng cố định dễ suy luận.
- Có ngôn ngữ cần hình thái số ít/số nhiều thay đổi theo từ vựng và loại câu.
- `choice` không thể tự suy ra đầy đủ plural rules của mọi locale chỉ từ `Locale`.
- Với yêu cầu i18n phức tạp, cân nhắc hệ thống message có plural/select theo locale như ICU4J; sử dụng bản dịch được kiểm thử với từng ngôn ngữ cụ thể.

**Không mã hóa các nhánh tiếng Anh rồi cho rằng chúng đúng khi thay locale thành tiếng Việt, tiếng Nga, tiếng Ả Rập...** Nội dung của các nhánh vẫn cần dịch theo ngôn ngữ và quy tắc của sản phẩm.

## 7. Ví dụ Java 17+ đầy đủ: number, date, time, choice

Tạo tệp **`MessageFormatTypesDemo.java`** chứa nội dung dưới đây. Ví dụ chọn `Locale.US` rõ ràng và đặt timezone UTC chỉ trên các formatter ngày/giờ. Không thay đổi locale hay timezone mặc định của toàn JVM.

```java
import java.text.DateFormat;
import java.text.Format;
import java.text.MessageFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public class MessageFormatTypesDemo {

    private static void useUtcForDates(MessageFormat message) {
        TimeZone utc = TimeZone.getTimeZone("UTC");

        for (Format format : message.getFormats()) {
            if (format instanceof DateFormat dateFormat) {
                dateFormat.setTimeZone(utc);
            }
        }
    }

    public static void main(String[] args) {
        Locale locale = Locale.US;

        String summaryPattern =
                "count={0,number,integer}; "
                + "money={1,number,currency}; "
                + "ratio={2,number,percent}; "
                + "day={3,date,yyyy-MM-dd}; "
                + "time={3,time,HH:mm:ss}";

        MessageFormat summary =
                new MessageFormat(summaryPattern, locale);
        useUtcForDates(summary);

        Object[] values = {
                1234, 1234.5, 0.256, new Date(0L)
        };
        System.out.println(summary.format(values));

        MessageFormat files = new MessageFormat(
                "{0,choice,0#no files|1#one file"
                + "|1<{0,number,integer} files}",
                locale);

        for (int count : new int[] {0, 1, 2}) {
            System.out.println("files-" + count + "="
                    + files.format(new Object[] {count}));
        }

        MessageFormat apostrophe = new MessageFormat(
                "You''ve got {0,number,integer} files.", locale);
        System.out.println(apostrophe.format(new Object[] {2}));
    }
}
```

Chạy trong thư mục chứa tệp, sử dụng JDK 17 trở lên:

```bash
javac -encoding UTF-8 MessageFormatTypesDemo.java
java MessageFormatTypesDemo
```

**Stdout chính xác với Java 17 và dữ liệu locale thông dụng cho `Locale.US`:**

```text
count=1,234; money=$1,234.50; ratio=26%; day=1970-01-01; time=00:00:00
files-0=no files
files-1=one file
files-2=2 files
You've got 2 files.
```

Giải thích:

1. `count={0,number,integer}` hiển thị `1234` có dấu nhóm của `Locale.US` thành `1,234`.
2. `money={1,number,currency}` dùng định dạng tiền của `Locale.US`, ra `$1,234.50`; không có chuyển đổi tỷ giá.
3. `ratio={2,number,percent}` nhận `0.256`, nhân 100 rồi làm tròn theo style mặc định, thành `26%`.
4. `day` và `time` cùng đọc `Date(0L)`, tức mốc Unix epoch, và nhờ cấu hình UTC ở từng `DateFormat` mà có `1970-01-01` và `00:00:00`.
5. `choice` chọn nhánh dựa trên 0, 1 và lớn hơn 1; nhánh cuối có format element số lồng nhau.
6. Mẫu `"You''ve"` sử dụng **hai dấu nháy đơn** trong pattern để tạo một dấu nháy đơn hiển thị `You've`; nếu chỉ viết một `'`, parser có thể coi phần sau là văn bản được trích dẫn và bỏ qua placeholder.

Đối với style số/tiền mặc định, tên tháng và quy ước CLDR, đầu ra có thể có khác biệt nhỏ giữa các bản JDK hoặc dữ liệu locale. Các trường ngày và giờ tùy chỉnh đã được cố định bằng pattern và UTC để giảm nguồn sai khác của ví dụ.

## 8. Cú pháp dấu nháy đơn, ngoặc nhọn và dấu phẩy

Trong `MessageFormat`, dấu nháy đơn `'` là ký tự quote của **ngôn ngữ pattern**, không chỉ là dấu câu bình thường:

- Muốn in một dấu apostrophe trong literal text, viết `''` trong message pattern.
- Muốn in dấu ngoặc nhọn như ký tự literal, cần quote phần ngoặc: `'{'` và `'}'`; không đặt một dấu `{` đơn lẻ trong message pattern nếu bạn muốn nó chỉ là văn bản.
- Với một cặp quote không đóng, parser có thể tự xử lý phần kết thúc pattern theo quy tắc quote của nó, dẫn tới placeholder không được nhận diện. Đừng trông chờ nó tự sửa nội dung.
- Khi pattern có định dạng lồng nhau, việc escape có thể qua nhiều lớp parser; cần test trực tiếp đầu ra mong muốn của từng locale, đặc biệt nếu pattern đến từ file dịch.

Ví dụ:

| Pattern literal | Kết quả mong muốn |
| --- | --- |
| `You''ve got {0} files.` | In dấu apostrophe và chèn đối số. |
| `'{'{0}'}'` | Hiển thị dấu ngoặc nhọn bao quanh giá trị đối số. |
| `{0,number,#,##0.00}` | Sử dụng dấu phẩy/thập phân theo **cú pháp `DecimalFormat`**, không phải tách format element sai vị trí. |

Không nên dùng nối chuỗi để “né” quote, vì nối chuỗi có thể ép thứ tự từ giống nhau ở mọi ngôn ngữ. Thiết kế thông điệp và cách escape phù hợp sẽ giữ quyền điều chỉnh câu cho người dịch.

## 9. Format đối số lặp, thiếu đối số và sai kiểu

### 9.1. Cùng một đối số ở nhiều format element

Trong mẫu:

```text
"Date={0,date,yyyy-MM-dd}; Time={0,time,HH:mm:ss}"
```

Đối số `0` được sử dụng **hai lần**, nhưng mỗi lần có formatter khác. Khi cần cấu hình time zone, đừng mặc định `getFormatsByArgumentIndex()[0]` đại diện cho cả hai format element; hãy dùng `getFormats()` để duyệt từng phần, hoặc cấu hình bằng `setFormat(...)` theo đúng thứ tự format element.

### 9.2. Thiếu đối số

`MessageFormat` yêu cầu các index khớp mảng đối số. Nếu index được tham chiếu trong pattern nhưng mảng không có đối số tương ứng, việc hiển thị placeholder chưa được thay thế có thể xảy ra. Đừng coi đó là một cách fallback bản dịch an toàn. Test tính đầy đủ của tham số và quản lý key/argument contract trong ứng dụng.

### 9.3. Sai kiểu

Nếu pattern yêu cầu `number` nhưng truyền `String` không phải `Number`, hoặc yêu cầu `date` nhưng truyền đối tượng không hợp lệ, formatter có thể ném `IllegalArgumentException`. Ví dụ trong code review, hãy phân biệt ba lỗi:

- Lỗi thiếu khóa dịch (`MissingResourceException`) khi nạp thông điệp từ bundle.
- Lỗi pattern không hợp lệ khi tạo hoặc `applyPattern`.
- Lỗi giá trị đối số không tương thích lúc gọi `format`.

Các lỗi này cần biện pháp sửa khác nhau; tránh bắt chung rồi trả chuỗi trống làm mất thông tin.

## 10. Tích hợp với ResourceBundle và dữ liệu nghiệp vụ

Thông thường bạn lưu từng pattern theo key:

```properties
cart.summary=You have {0,number,integer} items.
invoice.paidAt=Paid at {0,date,short} {0,time,short}.
file.count={0,choice,0#No files|1#One file|1<{0,number,integer} files}
```

Sau khi tải một `ResourceBundle`, dùng chính locale đã chọn cho `MessageFormat`:

```java
Locale locale = Locale.US;
ResourceBundle bundle = ResourceBundle.getBundle("messages", locale);

MessageFormat message =
        new MessageFormat(bundle.getString("cart.summary"), locale);
String result = message.format(new Object[] {3});
```

Đoạn này cần tệp resource và import `ResourceBundle`, `Locale`, `MessageFormat` để chạy trong chương trình thực.

Lưu ý khi ứng dụng dùng bundle fallback: bundle được nạp có thể là bản gốc hoặc bundle cha; chuỗi pattern cần đúng ngữ pháp `MessageFormat` cho ngôn ngữ của bản dịch ấy. Cùng một key ở các locale khác nhau có thể đổi thứ tự đối số (ví dụ `{1}` xuất hiện trước `{0}`), nhưng **vẫn phải giữ hợp đồng kiểu và ý nghĩa đối số**. Đừng giả định chỉ vì pattern ở hai locale dùng cùng index thì mô tả ngữ pháp đã chính xác.

Với dữ liệu thời gian trong nghiệp vụ hiện đại, lưu `Instant`, `LocalDate` hoặc `ZonedDateTime` theo ngữ nghĩa thật; ở tầng trình bày, chuyển về đối số phù hợp hoặc format bằng `java.time` rồi dùng `MessageFormat` để ghép thông điệp. Ngôn ngữ (locale) và múi giờ (zone) là hai lựa chọn khác nhau; truyền tường minh để tránh phụ thuộc cấu hình máy chủ.

## 11. Lưu ý hiệu năng, phân tích ngược và kiểm thử

- `MessageFormat` lưu cấu trúc pattern và các formatter thành phần; nếu lặp hàng nghìn lần với cùng mẫu, có thể chuẩn bị và tái sử dụng theo cách **có kiểm soát trạng thái/concurrency**. Không sửa cùng instance từ nhiều thread.
- `MessageFormat.parse(...)` không phải phương pháp tổng quát, đáng tin cho mọi chuỗi đã format, nhất là khi có `choice`, văn bản lặp, định dạng phụ thuộc locale hay format lồng nhau. Dùng parser có hợp đồng dữ liệu rõ ràng cho input của người dùng.
- Pattern trong bundle có thể bị thay đổi bởi người dịch; khi đưa vào CI, cần kiểm tra cân bằng ngoặc/quote, chỉ số tham số và sự tương thích kiểu giữa các locale.
- Với `choice`, phải test tại ngưỡng **dưới, đúng bằng, trên** giới hạn; đồng thời test số âm, số thập phân và số lớn theo domain thực tế.
- Test `date/time` với timezone cố định và ngày biên (gần nửa đêm, chuyển ngày). Không dùng định dạng hiển thị làm khóa dữ liệu nghiệp vụ hoặc chuẩn trao đổi API.
- Đừng giả định timezone sẽ thay đổi chỉ vì `Locale` thay đổi; `DateFormat` và `TimeZone` là những cơ chế riêng.

### Ma trận kiểm thử gợi ý

| Trường hợp | Kỳ vọng |
| --- | --- |
| `{0,number,integer}` với `1234` | Grouping theo locale, đúng số nguyên. |
| `{0,number,percent}` với `0.256` | Hiển thị phần trăm theo format, không thay đổi số nguồn. |
| `{0,number,currency}` | Có ký hiệu/kiểu tiền phù hợp và currency nghiệp vụ được kiểm soát. |
| `{0,date,short}`, `{0,time,short}` | Kết quả theo locale/zone tường minh. |
| `choice` với `0, 1, 2` | Chọn đúng nhánh ranh giới. |
| `choice` với `-1, 1.5` | Nhận diện hành vi ngoài domain, validate input trước. |
| Apostrophe trong pattern | Literal `'` được in, placeholder vẫn hoạt động. |
| Thiếu đối số hoặc sai kiểu | Test phát hiện hành vi lỗi; không coi là chuỗi dịch hoàn chỉnh. |
| Cùng index xuất hiện nhiều lần | Mỗi format element được cấu hình đúng. |

## 12. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vì sao gây vấn đề | Cách làm |
| --- | --- | --- |
| Dùng `{0,number,percent}` với giá trị `25` để biểu diễn 25% | Formatter nhân 100, gây lệch đơn vị. | Lưu tỷ lệ `0.25` hoặc chọn formatter khác theo domain. |
| Coi `{0,number,currency}` tự biết currency giao dịch | Locale không nhất thiết là mã tiền của nghiệp vụ. | Gắn `Currency` thực và định dạng rõ ràng. |
| Truyền `LocalDate` trực tiếp vào `{0,date}` | `DateFormat` dùng API kiểu `Date`, không tự hỗ trợ toàn bộ `java.time`. | Dùng `DateTimeFormatter` hoặc chuyển đổi có zone phù hợp. |
| Quên timezone khi format `Date(0L)` | Mỗi JVM có thể hiển thị giờ/ngày khác. | Cấu hình `DateFormat.setTimeZone(...)` tường minh. |
| Viết `You've {0}` trong pattern | Một dấu `'` có ý nghĩa quote, khiến placeholder bị hiểu sai. | Viết `You''ve {0}`. |
| Mặc định `choice` xử lý plural toàn thế giới | Quy tắc số nhiều có thể phức tạp theo locale. | Dùng cơ chế plural phù hợp ngôn ngữ khi cần. |
| Không test số âm dưới nhánh đầu của `choice` | Vẫn có thể chọn nhánh đầu, trả câu sai nghĩa. | Validate miền giá trị trước khi format. |
| Cấu hình timezone qua `getFormatsByArgumentIndex()` khi cùng index lặp | Có thể bỏ sót các format element khác nhau. | Duyệt `getFormats()` hoặc gắn format theo từng occurrence. |
| Dùng static `MessageFormat.format(...)` trong test phụ thuộc locale | Có thể lấy default `FORMAT` từ JVM. | Khởi tạo `MessageFormat(pattern, locale)`. |
| Dùng chung mutable formatter giữa request | Nguy cơ lỗi concurrency và trạng thái chéo. | Tạo mới hoặc dùng chiến lược clone/đồng bộ an toàn. |

## 13. Bài tập tự luyện

**Bài 1 — So sánh kiểu số:** truyền `1234.567` và `0.256` vào các pattern `number`, `integer`, `currency` và `percent`. Thử `Locale.US` và `Locale.forLanguageTag("vi-VN")`; ghi lại khác biệt về grouping, decimal separator, ký hiệu tiền và kết quả làm tròn. Không sửa giá trị nguồn để khớp chuỗi hiển thị.

**Bài 2 — Múi giờ:** cho `Instant.parse("2026-01-01T00:00:00Z")`. Tạo `Date.from(instant)` rồi format theo UTC và `Asia/Ho_Chi_Minh`; giải thích sự khác biệt giữa hai output mà không thay đổi `Instant`. Thử xem ngày địa phương có thể khác khi đổi timezone.

**Bài 3 — Choice boundaries:** viết pattern cho mức tồn kho: 0 = hết, 1 = còn một, lớn hơn 1 = còn N. Test `0`, `1`, `2`, `-1` và `1.5`. Phân biệt trách nhiệm **chọn thông điệp** với trách nhiệm **kiểm tra dữ liệu hợp lệ**.

**Bài 4 — Apostrophe và literal braces:** tạo thông điệp có dấu `'` và dấu ngoặc nhọn literal, vẫn chèn được `{0,number,integer}`. Test output chính xác, đặc biệt khi pattern đến từ file `.properties`.

**Bài 5 — Bundle theo ngôn ngữ:** tạo `messages_en.properties` và `messages_vi.properties` với cùng key nhưng thứ tự tham số khác nhau. Tải bundle theo locale, format hai kiểu số/ngày và kiểm tra hợp đồng tham số ở cả hai. Nếu ngôn ngữ yêu cầu plural phức tạp, mô tả lý do nên chuyển sang giải pháp plural theo locale.

### Ghi nhớ

- `number` định dạng số, số nguyên, currency, percent hoặc pattern DecimalFormat riêng.
- `date` và `time` dùng DateFormat với locale và timezone; đối số thường là `java.util.Date`.
- `choice` chọn một nhánh theo ngưỡng số; `#` bao gồm ngưỡng, `<` loại trừ ngưỡng.
- `Locale` điều khiển cách trình bày; timezone, currency giao dịch và quy tắc nghiệp vụ cần kiểm soát riêng.
- Dùng một hoặc hai dấu `'` trong pattern sai chỗ có thể thay đổi nghĩa toàn bộ thông điệp; phải kiểm thử chuỗi thực tế.
