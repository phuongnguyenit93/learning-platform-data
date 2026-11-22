# Đảo thứ tự đối số theo cấu trúc câu của từng ngôn ngữ bằng MessageFormat

## 1. Vì sao thứ tự đối số không thể cố định theo một ngôn ngữ?

Trong ứng dụng đa ngôn ngữ, cùng một sự kiện có thể được diễn đạt bằng trật tự từ khác nhau. Tiếng Anh có thể bắt đầu bằng người gửi; tiếng Việt có thể bắt đầu bằng người nhận. Dữ liệu nghiệp vụ **không thay đổi** khi câu dịch đổi thứ tự.

Giả sử ứng dụng biết:

| Vai trò dữ liệu | Đối số | Giá trị minh họa |
| --- | --- | --- |
| Người gửi | `{0}` | `Lan` |
| Tên tệp | `{1}` | `report.pdf` |
| Người nhận | `{2}` | `Minh` |

Hai mẫu câu đúng về cùng sự kiện:

- Tiếng Anh: `{0} sent file {1} to {2}.` → **Lan sent file report.pdf to Minh.**
- Tiếng Việt: `{2} đã nhận tệp {1} do {0} gửi.` → **Minh đã nhận tệp report.pdf do Lan gửi.**

Pattern tiếng Anh dùng thứ tự `{0} → {1} → {2}`; tiếng Việt dùng `{2} → {1} → {0}`. **Chỉ số đối số mô tả vai trò, không mô tả thứ tự xuất hiện trong câu**. Vì thế, bản dịch có thể thay trật tự mà Java vẫn lấy đúng người gửi, tệp và người nhận.

`java.text.MessageFormat` trong Java giúp tách mẫu câu khỏi mảng dữ liệu động. Nó không tự dịch văn bản; **người biên dịch nội dung** cung cấp câu hoàn chỉnh theo từng ngôn ngữ, còn `MessageFormat` thay placeholder theo chỉ số.

## 2. Cơ chế ánh xạ của MessageFormat

Một pattern có thể chứa `{0}`, `{1}`, `{2}` và các format element như `{0,number}`. Các số nguyên không âm đó là **chỉ số trong mảng arguments**, bắt đầu từ 0.

```text
Object[] args
  [0] = "Lan"        (sender)
  [1] = "report.pdf" (fileName)
  [2] = "Minh"       (recipient)
         |
         +--> en: {0} sent file {1} to {2}.
         |         Lan        report.pdf  Minh
         |
         +--> vi: {2} đã nhận tệp {1} do {0} gửi.
                   Minh           report.pdf Lan
```

Khi pattern bắt đầu bằng `{2}`, formatter lấy phần tử ở index 2 ngay đầu câu. Nó **không** lấy `args[0]` chỉ vì placeholder này xuất hiện đầu tiên.

Ví dụ minh họa trong một method có các import phù hợp:

```java
Object[] arguments = {"Lan", "report.pdf", "Minh"};
String pattern = "{2} đã nhận tệp {1} do {0} gửi.";
String message = new MessageFormat(
        pattern, Locale.forLanguageTag("vi-VN")).format(arguments);
```

Giá trị `message` là `Minh đã nhận tệp report.pdf do Lan gửi.`.

Sai lầm phổ biến là sửa mảng thành `{"Minh", "report.pdf", "Lan"}` để khớp thứ tự đọc của bản dịch Việt. Cách đó biến `args[0]` thành hai vai trò khác nhau tùy locale, dễ tạo lỗi đảo người gửi/người nhận.

**Quy tắc:** lập trình viên xác định hợp đồng argument **theo ý nghĩa**, rồi người dịch sắp xếp placeholder **theo ngữ pháp**.

## 3. Ví dụ đầy đủ Java 17+: cùng đối số, hai bản dịch, thứ tự khác

Tạo ba tệp trong một thư mục trên classpath:

```text
MessageOrderDemo.java
Messages_en.properties
Messages_vi.properties
```

**`Messages_en.properties`**

```properties
upload.notice={0} sent file {1} to {2}.
review.notice={0} approved {1}. Thank you, {0}!
```

**`Messages_vi.properties`**

```properties
upload.notice={2} đã nhận tệp {1} do {0} gửi.
review.notice=Cảm ơn {0}! {1} đã được {0} duyệt.
```

**`MessageOrderDemo.java`**

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageOrderDemo {
    private static String translate(
            Locale locale, String key, Object... values) {

        ResourceBundle.Control noDefaultFallback =
                ResourceBundle.Control.getNoFallbackControl(
                        ResourceBundle.Control.FORMAT_PROPERTIES);

        ResourceBundle bundle =
                ResourceBundle.getBundle(
                        "Messages", locale, noDefaultFallback);

        String pattern = bundle.getString(key);
        return new MessageFormat(pattern, locale).format(values);
    }

    public static void main(String[] args) {
        Locale en = Locale.forLanguageTag("en");
        Locale vi = Locale.forLanguageTag("vi");

        Object[] upload = {"Lan", "report.pdf", "Minh"};
        System.out.println("EN: " +
                translate(en, "upload.notice", upload));
        System.out.println("VI: " +
                translate(vi, "upload.notice", upload));

        Object[] review = {"Lan", "PR-17"};
        System.out.println("EN review: " +
                translate(en, "review.notice", review));
        System.out.println("VI review: " +
                translate(vi, "review.notice", review));
    }
}
```

Lưu tệp mã nguồn và `.properties` với UTF-8. Chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 MessageOrderDemo.java
java -cp . MessageOrderDemo
```

**Stdout chính xác (terminal hỗ trợ UTF-8):**

```text
EN: Lan sent file report.pdf to Minh.
VI: Minh đã nhận tệp report.pdf do Lan gửi.
EN review: Lan approved PR-17. Thank you, Lan!
VI review: Cảm ơn Lan! PR-17 đã được Lan duyệt.
```

Quan sát:

1. `upload` luôn là mảng `{"Lan", "report.pdf", "Minh"}`. Chỉ có mẫu câu trong resource bundle thay đổi.
2. `review.notice` dùng `{0}` **hai lần** để nhắc lại người duyệt, nhưng ứng dụng chỉ cần cung cấp tên này một lần. Không có quy tắc cấm xuất hiện nhiều lần cho một chỉ số.
3. Tiếng Việt `{1} đã được {0} duyệt` đổi sang câu bị động để phù hợp cách diễn đạt. Việc chọn chủ động/bị động là trách nhiệm của bản dịch, không do formatter tự quyết định.
4. `ResourceBundle` tìm **mẫu dịch** theo key và locale; `MessageFormat` xử lý **các argument** của mẫu. Hai trách nhiệm tách biệt.
5. Ví dụ dùng `Control.FORMAT_PROPERTIES` trên **classpath/unnamed module**, tránh thử fallback locale mặc định JVM. Các overload dùng `ResourceBundle.Control` không được hỗ trợ khi gọi từ named module; môi trường JPMS cần cơ chế bundle/module phù hợp.

Từ Java 9, `PropertyResourceBundle` có cơ chế đọc UTF-8 mặc định và fallback tương thích ISO-8859-1; thực tế nên quản lý encoding nhất quán từ nguồn, build đến terminal.

## 4. Hợp đồng vai trò: điều mà người dịch phải biết

Một key không chỉ có tên và chuỗi mẫu; nó còn có **ý nghĩa của từng placeholder**. Hãy mô tả contract rõ ràng:

| Key | `{0}` | `{1}` | `{2}` |
| --- | --- | --- | --- |
| `upload.notice` | Tên người gửi | Tên tệp | Tên người nhận |
| `review.notice` | Tên người duyệt | Mã yêu cầu | Không dùng |
| `project.summary` | Tên dự án | Trạng thái | Người phụ trách |

Hợp đồng này gắn với **từng key**. Không có quy định toàn cục rằng `{0}` luôn là tên người. Ví dụ key khác có thể quy định `{0}` là số lượng và `{1}` là ngày.

Để bàn giao cho người dịch, có thể dùng metadata minh họa như:

```yaml
upload.notice:
  description: "Thông báo tệp đã chuyển từ người gửi tới người nhận."
  arguments:
    0: "senderName: tên người gửi"
    1: "fileName: tên tệp"
    2: "recipientName: tên người nhận"
  example:
    en: "{0} sent file {1} to {2}."
    vi: "{2} đã nhận tệp {1} do {0} gửi."
```

Đây là **tài liệu hợp đồng dịch**, không phải cấu trúc `ResourceBundle` mặc định. Với tệp `.properties`, giá trị thật vẫn là pattern như trong phần 3. Metadata giúp người dịch tránh đổi số placeholder để “đánh lại số” theo trật tự mới.

## 5. Những kiểu thay đổi mà MessageFormat hỗ trợ

### 5.1. Đảo trật tự

```text
en: {0} approved {1}.
vi: {1} đã được {0} duyệt.
```

Đối số `{0}=Lan`, `{1}=PR-17` có kết quả `Lan approved PR-17.` và `PR-17 đã được Lan duyệt.`. Cùng dữ liệu, cách nhấn mạnh khác nhau.

### 5.2. Lặp một argument

```text
en: {0} approved {1}. Thank you, {0}!
vi: Cảm ơn {0}! {1} đã được {0} duyệt.
```

Không cần truyền tên người duyệt hai lần. Đây không phải “argument mới”; hai `{0}` đều đọc từ `args[0]`.

### 5.3. Một ngôn ngữ lược bỏ thông tin có thể suy ra

Một pattern có thể không sử dụng mọi giá trị trong mảng. `MessageFormat` không ép từng argument phải xuất hiện đúng một lần. Tuy nhiên, lược bỏ thông tin có thể gây hiểu nhầm nghiệp vụ: ẩn tên người gửi trong thông báo thanh toán/phê duyệt, bỏ số lượng hoặc tên người nhận có thể khiến câu không còn đủ ý nghĩa. Hợp đồng phải nêu **argument nào bắt buộc phải thể hiện** và argument nào chỉ hỗ trợ cách diễn đạt.

### 5.4. Đổi trật tự nhưng giữ kiểu dữ liệu

Ví dụ `{0}` là số lượng, `{1}` là người nhận, `{2}` là người gửi:

```text
en: {1} received {0,number,integer} items from {2}.
vi: {2} đã gửi {0,number,integer} mục cho {1}.
```

Đảo trật tự không làm `{0}` biến thành tên người, và không được xóa mất ý nghĩa `number,integer` nếu thông điệp cần định dạng số lượng.

## 6. Đừng nhầm chỉ số argument với thứ tự format element

Một `MessageFormat` có hai loại vị trí:

- **Argument index:** số trong `{0}`, `{1}`, `{2}`, ứng với phần tử mảng dữ liệu.
- **Format element index:** số thứ tự placeholder **xuất hiện trong pattern**, tính từ trái sang phải.

Với pattern `"{2} / {0} / {1}"`:

| Format element index | Format element | Argument index |
| ---: | --- | ---: |
| 0 | `{2}` | 2 |
| 1 | `{0}` | 0 |
| 2 | `{1}` | 1 |

Các API dễ gây nhầm:

| API | Áp dụng theo chỉ số nào? |
| --- | --- |
| `setFormat(int formatElementIndex, Format f)` | Thứ tự placeholder xuất hiện |
| `setFormats(Format[] fs)` | Thứ tự placeholder xuất hiện |
| `setFormatByArgumentIndex(int argumentIndex, Format f)` | Chỉ số trong `{n}` |
| `setFormatsByArgumentIndex(Format[] fs)` | Chỉ số trong `{n}` |

Khi bản dịch hoán đổi thứ tự, **`setFormatByArgumentIndex` thường hợp lý hơn**, vì format vẫn gắn với vai trò dữ liệu. Nếu một chỉ số xuất hiện nhiều lần, phương thức này áp dụng formatter cho mọi format element có cùng argument index.

### Ví dụ Java 17 đầy đủ về số lượng

Tệp `NumberArgumentOrder.java`:

```java
import java.text.MessageFormat;
import java.text.NumberFormat;
import java.util.Locale;

public class NumberArgumentOrder {
    public static void main(String[] args) {
        MessageFormat format = new MessageFormat(
                "{1} received {0} items from {2}; {1} will review.",
                Locale.US);

        // Định dạng argument 0 (số lượng), không phải
        // placeholder xuất hiện đầu tiên là {1}.
        format.setFormatByArgumentIndex(
                0, NumberFormat.getIntegerInstance(Locale.US));

        Object[] values = {1200, "Minh", "Lan"};
        System.out.println(format.format(values));
    }
}
```

```bash
javac -encoding UTF-8 NumberArgumentOrder.java
java NumberArgumentOrder
```

Stdout với `Locale.US`:

```text
Minh received 1,200 items from Lan; Minh will review.
```

Nếu dùng `setFormat(0, ...)` trong ví dụ này, formatter số nguyên sẽ gắn với **format element đầu tiên `{1}`**, vốn là tên người nhận, dẫn tới lỗi kiểu dữ liệu khi format. `setFormatByArgumentIndex(0, ...)` gắn đúng với số lượng `{0}` dù `{0}` xuất hiện sau `{1}`.

## 7. Các cú pháp format được phép sử dụng

Dạng tổng quát của phần tử thay thế là:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Một số dạng trong Java SE 17:

| Dạng | Ý nghĩa |
| --- | --- |
| `{0}` | Giá trị của đối số 0 |
| `{0,number}` | Định dạng số theo locale |
| `{0,number,integer}` | Định dạng số nguyên |
| `{0,number,currency}` | Định dạng tiền theo locale và số liệu |
| `{1,date,short}` | Định dạng ngày ngắn, với loại ngày được `DateFormat` hỗ trợ |
| `{1,time,short}` | Định dạng thời gian ngắn |
| `{2,choice,...}` | Lựa chọn nhánh theo `ChoiceFormat` |

Các đối số số và ngày không đơn thuần được chuyển thành chuỗi trước rồi thay vào. `MessageFormat` tạo hoặc sử dụng **subformat**; kết quả phụ thuộc locale, kiểu của đối số và format style. Khi cần kết quả với `java.time.LocalDate`, nên format trước bằng `DateTimeFormatter` hoặc dùng `Format` tương thích; `{0,date}` chuẩn không tự bảo đảm xử lý trực tiếp mọi kiểu `java.time`.

Thí dụ định dạng tiếng Việt (đoạn mã nằm trong method):

```java
Locale locale = Locale.forLanguageTag("vi-VN");
String pattern = "{2} đã gửi {0,number,integer} mục cho {1}.";
Object[] arguments = {1200, "Minh", "Lan"};
String sentence = new MessageFormat(pattern, locale).format(arguments);
```

Thông điệp sẽ có thứ tự vai trò **Lan → số lượng → Minh**, còn dấu phân nhóm của số phụ thuộc dữ liệu locale từ JDK/CLDR. Không nên chốt mọi chuỗi format bản địa hóa giống hệt nhau giữa các phiên bản JDK.

**Chú ý nghiệp vụ:** `{0,number,currency}` không tự lấy currency từ giao dịch. Nó dựa vào formatter/currency theo locale nếu không được cấu hình khác. Một giao dịch USD cho người dùng `vi-VN` vẫn là USD; muốn thể hiện đúng đơn vị tiền phải truyền và áp dụng `Currency` theo nghiệp vụ, có thể tạo chuỗi tiền trước hoặc dùng formatter tùy chỉnh.

## 8. Dấu nháy đơn và ngoặc nhọn: lỗi dịch dễ làm sai placeholder

`MessageFormat` có cú pháp đặc biệt cho dấu nháy đơn `'`. Trong pattern:

- Một cặp `''` biểu thị dấu apostrophe thật.
- Đoạn nằm trong cặp dấu nháy đơn có thể được hiểu là văn bản literal, nên `'{0}'` tạo chữ `{0}` thay vì thay argument.
- Nếu pattern có một dấu nháy đơn mở mà không đóng, cách parser diễn giải phần còn lại có thể khiến placeholder không được thay.

Ví dụ Java trong method:

```java
String pattern = "It''s {0}''s file.";
String message = new MessageFormat(pattern, Locale.ENGLISH)
        .format(new Object[]{"Lan"});
System.out.println(message);
```

Kết quả:

```text
It's Lan's file.
```

Nếu người dịch viết `"It's {0}'s file."` mà không escape apostrophe cho `MessageFormat`, output có thể chứa literal `{0}` hoặc sai nội dung. Các bản dịch có apostrophe thường xuyên cần được kiểm thử riêng.

Một trường hợp khác:

```java
String pattern = "Literal: '{0}', actual: {0}.";
String message = new MessageFormat(pattern, Locale.ENGLISH)
        .format(new Object[]{"VALUE"});
```

Kết quả là `Literal: {0}, actual: VALUE.`. Ở đây `'{0}'` được quote để **in nguyên placeholder**, còn `{0}` còn lại mới thực sự thay bằng dữ liệu.

Phân biệt **ba lớp escaping** khi cần thiết: chuỗi Java, nội dung `.properties` và cú pháp `MessageFormat`. Dấu `{`, `}` không cân đối hoặc format type không hợp lệ có thể khiến `new MessageFormat(pattern, locale)` ném `IllegalArgumentException`.

## 9. Những lỗi thường gặp khi đổi trật tự

| Lỗi | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| Đánh lại `{0}`, `{1}` theo vị trí chữ trong bản dịch | Các chỉ số đang gắn với role, nên dữ liệu bị tráo | Giữ chỉ số theo hợp đồng |
| Hoán đổi phần tử mảng theo ngôn ngữ | Logic ứng dụng bị buộc phải hiểu cấu trúc câu | Giữ mảng nhất quán, đổi pattern |
| Dịch từng từ/ghép chuỗi | Ngữ pháp, giới từ, biến tố và thứ tự có thể khác | Dịch toàn câu với placeholder |
| Dùng `setFormat(0, f)` và tưởng đó là `{0}` | Đó là format element đầu tiên | Dùng `setFormatByArgumentIndex` khi cần gắn role |
| Quên dấu `''` trong pattern | Quote sai khiến placeholder mất tác dụng | Kiểm thử apostrophe và literal braces |
| Thiếu argument nhưng không kiểm tra output | Argument không khả dụng có thể hiện literal `{n}` | Kiểm tra hợp đồng và số lượng đối số |
| Dùng `{0,number}` với String | Subformat số cần kiểu phù hợp | Truyền Number hoặc định dạng trước |
| Chuyển một ngày thành String mặc định rồi gắn nhãn | Dễ sai locale và timezone | Chọn formatter và `ZoneId` tường minh |
| Xem `MessageFormat` là bộ dịch tự động | Nó chỉ thay và format dữ liệu | Viết từng pattern dịch |
| Chia sẻ `MessageFormat` mutable giữa request | `applyPattern`, `setFormat` có thể sửa trạng thái | Tạo instance riêng hoặc đồng bộ quản lý |
| Dùng `MessageFormat` cho HTML không escape | Nó không xử lý XSS | Encode theo ngữ cảnh đầu ra |

### 9.1. Argument thiếu và argument `null`

Theo đặc tả Java, khi một placeholder có argument index vượt ra khỏi mảng, `MessageFormat` có thể giữ literal như `{2}` trong output, **không bắt buộc ném lỗi**. Vì vậy “format chạy không lỗi” chưa bảo đảm dữ liệu đầy đủ.

Đối số `null` có thể được biểu diễn bằng chữ `null`. Trong giao diện thực, cần chính sách xử lý dữ liệu thiếu rõ ràng, tránh lộ placeholder hoặc `null` cho người dùng. Nếu subformat yêu cầu Number hoặc Date nhưng truyền kiểu không tương thích, có thể ném `IllegalArgumentException`.

### 9.2. Gộp tất cả thành một ngôn ngữ làm mẫu gốc

Dùng tiếng Anh làm mẫu đối chiếu cũng được, nhưng không được bắt mọi bản dịch giữ **thứ tự placeholder** y hệt tiếng Anh. Hãy giữ **vai trò đối số** và ý nghĩa sự kiện; để người dịch quyết định cấu trúc câu.

## 10. Đảo thứ tự chưa giải quyết hết biến thể ngữ pháp

Đổi từ `{0} {1}` thành `{1} {0}` giúp chuyển thứ tự thông tin, nhưng nhiều ngôn ngữ còn có:

- Quy tắc số ít/số nhiều phụ thuộc số lượng;
- Giống ngữ pháp, cách chia động từ, biến tố của danh từ và đại từ;
- Đơn vị đo, số, tiền, ngày tháng;
- Hình thức lịch sự, mức độ trang trọng;
- Văn bản phải–trái (RTL) và xử lý bidi cho chuỗi xen ký tự Latin.

`MessageFormat` của JDK 17 có `ChoiceFormat` nhưng **không hỗ trợ trực tiếp** cú pháp ICU `{count, plural, ...}` hoặc `{gender, select, ...}` như format type chuẩn. Nếu sản phẩm cần plural phức tạp, cân nhắc ICU MessageFormat hoặc một lớp chọn mẫu thông điệp phù hợp. Chỉ đổi vị trí placeholder không thể thay thế việc dịch ngữ pháp.

Ví dụ `"{1} đã được {0} duyệt"` là câu bị động, cần người dịch bảo đảm nội dung không đổi nghĩa; `MessageFormat` không kiểm tra ai thật sự là người duyệt.

## 11. Tổ chức tài nguyên và định dạng trong ứng dụng

Một flow thường gặp:

```text
Sự kiện/domain
  senderName = "Lan"
  fileName = "report.pdf"
  recipientName = "Minh"
        |
        v
App xác định locale người dùng (vi/en/...)
        |
        v
ResourceBundle lấy pattern theo key + locale
        |
        v
MessageFormat(pattern, locale)
        |
        v
format(new Object[] {senderName, fileName, recipientName})
        |
        v
Chuỗi hiển thị -> output encoding phù hợp với UI
```

`ResourceBundle` chọn mẫu dịch và có cơ chế candidate/fallback theo locale, base, parent. `MessageFormat` không tự tìm ngôn ngữ và không tự tải bundle. Khi một bundle thiếu key, có thể kế thừa từ parent hoặc ném `MissingResourceException` nếu không tìm được ở toàn chain.

Nên truyền `Locale` tường minh từ request/profile thay vì `Locale.setDefault(...)` trên server đa người dùng. `Locale.setDefault` thay mặc định toàn JVM và có thể ảnh hưởng request khác. `MessageFormat.format(pattern, args...)` dạng static sử dụng locale mặc định của formatter được tạo bên trong; muốn locale xác định, dùng `new MessageFormat(pattern, locale).format(args)`.

`MessageFormat` là mutable; các phương thức như `applyPattern` và `setFormat` có thể đổi cấu hình. Không chia sẻ một instance rồi thay đổi pattern/locale đồng thời giữa các request. `ResourceBundle` có cache, nhưng điều đó không biến `MessageFormat` thành immutable.

Với nội dung HTML, `MessageFormat` chỉ trả text; **không tự escape HTML/URL**. Giá trị do người dùng nhập phải được encode đúng tại điểm xuất HTML, DOM hoặc các kênh khác. Không dùng thay thế placeholder làm lớp bảo mật.

## 12. Kiểm thử trật tự đối số và bản dịch

Dùng **giá trị sentinel khác nhau** cho từng vai trò để phát hiện bị đảo:

```text
args[0] = SENDER_A
args[1] = FILE_B
args[2] = RECIPIENT_C

en: SENDER_A sent file FILE_B to RECIPIENT_C.
vi: RECIPIENT_C đã nhận tệp FILE_B do SENDER_A gửi.
```

Nếu dùng cùng tên cho người gửi và người nhận, test có thể bỏ sót lỗi hoán đổi.

Những ca cần kiểm tra:

1. **Trật tự khác nhau:** cùng array mà các locale tạo câu đúng nghĩa.
2. **Chỉ số lặp:** `{0}` xuất hiện nhiều lần đều có cùng giá trị.
3. **Thiếu placeholder bắt buộc:** kiểm định hợp đồng của key.
4. **Đối số dư/thiếu:** test định danh index không hợp lệ, thiếu giá trị hoặc `null`.
5. **Kiểu dữ liệu:** `{0,number}` luôn nhận Number, `{1,date}` nhận kiểu tương thích `DateFormat`.
6. **Apostrophe và braces:** pattern tiếng Pháp/tiếng Anh chứa nháy đơn vẫn thay đúng.
7. **Locale và resource fallback:** có đủ key và ngôn ngữ mong muốn, không phụ thuộc default JVM.
8. **Ngữ nghĩa câu:** người bản ngữ hoặc reviewer xác nhận đúng vai trò người gửi/người nhận, chủ động/bị động.
9. **Ký tự đặc biệt:** tên người dùng, tệp và nội dung có thể chứa ký tự không Latin, dấu ngoặc, apostrophe và ký tự HTML.
10. **Formatter mutable:** không có race khi chạy request đồng thời.

Không nên dùng regex đơn giản trên chuỗi `{...}` để kiểm tra mọi pattern, vì `MessageFormat` có quoting, subformat và khả năng nested pattern với `ChoiceFormat`. Dùng parser phù hợp kết hợp test với giá trị mẫu và quy tắc dịch.

## 13. Bài tập thực hành

### Bài 1 — đổi chủ ngữ khi dịch

Cho `args = {"Hoa", "contract.pdf", "Nam"}`, trong đó `{0}` là người gửi, `{1}` tệp, `{2}` người nhận. Viết pattern tiếng Anh bắt đầu từ người gửi và tiếng Việt bắt đầu bằng người nhận, không đổi array.

**Đáp án:**

```text
en: {0} sent file {1} to {2}.
vi: {2} đã nhận tệp {1} từ {0}.
```

Output lần lượt: `Hoa sent file contract.pdf to Nam.` và `Nam đã nhận tệp contract.pdf từ Hoa.`.

### Bài 2 — format element index khác argument index

Pattern `"{2}: {0} - {1}"`, phần tử placeholder đầu tiên là gì? `setFormat(0, f)` khác `setFormatByArgumentIndex(0, f)` như thế nào?

**Đáp án:** Format element đầu tiên là `{2}`; `setFormat(0, f)` tác động `{2}`. `setFormatByArgumentIndex(0, f)` tác động `{0}` ở vị trí thứ hai.

### Bài 3 — lặp cùng đối số

Với `args = {"Lan", "PR-17"}` và pattern `"Cảm ơn {0}! {1} đã được {0} duyệt."`, output là gì?

**Đáp án:** `Cảm ơn Lan! PR-17 đã được Lan duyệt.`.

### Bài 4 — dấu apostrophe

Pattern `"It's {0}'s file."` có thể hỏng ở đâu? Cách viết đúng?

**Đáp án:** `'` thuộc cú pháp quote của `MessageFormat`. Viết `"It''s {0}''s file."` để nhận `It's Lan's file.` khi `{0}=Lan`.

### Bài 5 — giới hạn của đảo thứ tự

Một ngôn ngữ cần nhiều dạng số nhiều theo `count`. Có thể chỉ đảo `{0}` và `{1}` để dịch đúng không?

**Đáp án:** Không. Đảo thứ tự giải quyết vị trí từ/cụm từ; cần cơ chế chọn biến thể số nhiều riêng theo ngôn ngữ.

## 14. Ghi nhớ

- **Thứ tự xuất hiện của placeholder có thể khác nhau giữa các ngôn ngữ.** Mỗi `{n}` luôn chỉ đến argument index `n`.
- **Giữ vai trò và thứ tự mảng đầu vào ổn định** cho cùng message key; đặt placeholder theo cách diễn đạt của từng bản dịch.
- **Có thể lặp hoặc di chuyển placeholder**, nhưng phải giữ ý nghĩa và đủ thông tin nghiệp vụ.
- **`setFormatByArgumentIndex` gắn formatter với role**, còn `setFormat` gắn với thứ tự format element; sự khác biệt đặc biệt quan trọng khi dịch đổi vị trí.
- **Kiểm thử bằng dữ liệu phân biệt các vai trò** và kiểm tra apostrophe, loại argument, số lượng đối số, ngữ nghĩa câu.
- **`MessageFormat` không tự dịch, không xử lý ngữ pháp phức tạp và không escape HTML**; phần còn lại cần nội dung dịch tốt và xử lý đúng ở tầng ứng dụng.

Tham khảo: [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) và [Java SE 17 — ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html).
