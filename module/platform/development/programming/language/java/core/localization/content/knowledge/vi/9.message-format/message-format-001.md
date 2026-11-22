# Vì sao cần định dạng toàn câu thay cho nối các mảnh văn bản?

## 1. Vấn đề: một câu có ý nghĩa lớn hơn tổng các mảnh ghép

Trong ứng dụng Java, cách đơn giản để tạo thông báo động là nối các chuỗi:

```java
String sentence = "Hello, " + name + "! You have "
        + count + " new messages.";
```

Đoạn code có thể hoạt động khi chỉ hỗ trợ tiếng Anh. Nhưng nếu dùng các “mảnh” để bản địa hóa:

```java
String sentence = bundle.getString("greeting.prefix")
        + name
        + bundle.getString("inbox.middle")
        + count
        + bundle.getString("inbox.suffix");
```

thì người dịch bị buộc tuân theo **thứ tự ghép do Java quyết định**. Ngữ pháp từng ngôn ngữ không có cùng thứ tự chủ ngữ, số lượng, danh từ và lời xưng hô. Có ngôn ngữ cần di chuyển cả cụm từ, thêm hậu tố theo ngữ cảnh hoặc bỏ dấu câu vốn thuộc một mảnh khác.

Ví dụ:

- Tiếng Anh: **“Hello, Linh. You have 2 new messages.”**
- Tiếng Việt: **“Bạn có 2 tin nhắn mới, Linh.”**

Ở tiếng Anh, tên `Linh` xuất hiện trước số lượng `2`; ở tiếng Việt, vị trí được đổi lại. Nếu chia thông điệp thành “prefix + name + middle + count + suffix”, bản dịch phải chấp nhận một cấu trúc câu cứng nhắc, hoặc code phải thêm các nhánh điều kiện ngôn ngữ. Mỗi nhánh mới lại tăng rủi ro lỗi.

**Quy tắc chính:** hãy dịch **nguyên câu có ngữ cảnh**, và đưa các dữ liệu động vào **tham số được đánh dấu**. Java xử lý dữ liệu, còn bản dịch được quyền sắp xếp các thành phần trong câu.

Trong Java, `java.text.MessageFormat` là một công cụ chuẩn để biểu diễn một thông điệp hoàn chỉnh có tham số, định dạng số, ngày và một số dạng lựa chọn đơn giản theo locale.

## 2. Phân biệt nối chuỗi và mẫu thông điệp

So sánh hai thiết kế:

| Khía cạnh | Nối nhiều mảnh | Định dạng toàn câu |
| --- | --- | --- |
| Đơn vị dịch | `prefix`, `suffix`, từ và dấu câu | Một thông điệp có ý nghĩa đầy đủ |
| Thứ tự tên và số | Cố định trong code | Mỗi bản dịch có thể đổi vị trí tham số |
| Dấu câu và khoảng trắng | Chia giữa các mảnh, dễ thừa hoặc thiếu | Thuộc câu hoàn chỉnh |
| Cách nói tự nhiên | Dễ bị ép theo ngữ pháp của ngôn ngữ gốc | Người dịch tự chọn cấu trúc |
| Dữ liệu động | Nối hoặc thay chuỗi thủ công | Tham số `{0}`, `{1}`, ... |
| Số/ngày theo locale | Thường bị chuyển thành chuỗi quá sớm | Có thể định dạng tại thời điểm tạo câu |
| Kiểm thử | Khó kiểm tra ngữ pháp toàn câu | Kiểm thử từng mẫu thông điệp và tham số |

Thiết kế toàn câu vẫn cần một **khóa thông điệp** ở tầng tài nguyên. Ví dụ:

```properties
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
```

Với bản dịch tiếng Việt:

```properties
inbox.summary=Bạn có {1,number,integer} tin nhắn mới, {0}.
```

Cả hai tệp dùng **cùng một key** `inbox.summary` và cùng một danh sách đối số, nhưng thứ tự `{0}`, `{1}` hoàn toàn khác nhau. Điều đó chính là lợi ích của việc định dạng cả câu.

**Điểm cần tránh:** `MessageFormat` không tự dịch tiếng Anh sang tiếng Việt. Bạn phải cung cấp các mẫu câu phù hợp trong các tệp dịch; `MessageFormat` chỉ diễn giải mẫu và chèn dữ liệu theo quy tắc định dạng.

## 3. Cấu trúc cơ bản của MessageFormat

Ví dụ mẫu:

```text
Hello, {0}. You have {1,number,integer} new messages.
```

- `{0}`: lấy đối số có **chỉ số 0**.
- `{1}`: lấy đối số có **chỉ số 1**.
- `{1,number,integer}`: lấy đối số 1 và trình bày dưới dạng số nguyên theo locale của `MessageFormat`.
- Văn bản ở ngoài dấu ngoặc nhọn là một phần của câu, được giữ nguyên như translator đã viết.

API chính:

```java
MessageFormat format = new MessageFormat(pattern, locale);
String result = format.format(new Object[] {name, count});
```

`pattern` là **mẫu thông điệp**; `locale` quyết định cách định dạng các đối số có kiểu số/ngày. `name` và `count` là dữ liệu động. Để thay đổi cấu trúc câu, sửa mẫu trong bản dịch, không cần sửa thứ tự đối số Java gửi vào.

Trong mẫu, chỉ số tham số bắt đầu từ 0 và **không cần xuất hiện theo thứ tự tăng dần**. Có thể lặp lại một đối số ở nhiều vị trí, hoặc bỏ qua đối số không cần dùng. Dù vậy, hãy giữ một hợp đồng rõ ràng cho từng key: đối số 0 là gì, đối số 1 là gì, kiểu dữ liệu nào được phép.

## 4. Ví dụ Java 17+ chạy độc lập: hai ngôn ngữ, một danh sách đối số

Tạo file `WholeSentenceDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class WholeSentenceDemo {
    static String render(Locale locale, String pattern,
                         String name, int count) {
        MessageFormat formatter = new MessageFormat(pattern, locale);
        return formatter.format(new Object[] {name, count});
    }

    public static void main(String[] args) {
        String english =
                "Hello, {0}. You have {1,number,integer} new messages.";
        String vietnamese =
                "Bạn có {1,number,integer} tin nhắn mới, {0}.";

        System.out.println(render(Locale.US, english, "Linh", 2));
        System.out.println(render(
                Locale.forLanguageTag("vi-VN"),
                vietnamese,
                "Linh",
                2));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 WholeSentenceDemo.java
java WholeSentenceDemo
```

Stdout:

```text
Hello, Linh. You have 2 new messages.
Bạn có 2 tin nhắn mới, Linh.
```

Mỗi câu hoàn chỉnh được lưu trong một biến pattern, nhưng cả hai nhận cùng dữ liệu `"Linh"` và `2`. Bản tiếng Việt dùng `{1}` trước `{0}`. Khi có thêm ngôn ngữ, ta thêm một bản dịch toàn câu và vẫn dùng cùng lời gọi `formatter.format(...)`.

Việc hard-code `english` và `vietnamese` ở ví dụ chỉ nhằm tập trung vào cơ chế `MessageFormat`. Trong ứng dụng thật, mẫu nên được lấy từ tài nguyên bản địa hóa, ví dụ `ResourceBundle`, để người dịch chỉnh văn bản mà không sửa code.

## 5. Kết hợp ResourceBundle: lưu cả câu trong file tài nguyên

Một cấu trúc chạy được với Java 17+:

```text
message-demo/
├── MessageBundleDemo.java
├── messages.properties
├── messages_en.properties
└── messages_vi.properties
```

`messages.properties` — bundle gốc, chứa bản mặc định:

```properties
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
```

`messages_en.properties`:

```properties
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
```

`messages_vi.properties` (lưu UTF-8):

```properties
inbox.summary=Bạn có {1,number,integer} tin nhắn mới, {0}.
```

`MessageBundleDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class MessageBundleDemo {
    static String message(Locale locale, String name, int count) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", locale);
        String pattern = bundle.getString("inbox.summary");

        MessageFormat format = new MessageFormat(pattern, locale);
        return format.format(new Object[] {name, count});
    }

    public static void main(String[] args) {
        System.out.println(message(Locale.US, "Linh", 2));
        System.out.println(message(
                Locale.forLanguageTag("vi-VN"), "Linh", 2));
    }
}
```

Ở thư mục chứa bốn tệp:

```bash
javac -encoding UTF-8 MessageBundleDemo.java
java -cp . MessageBundleDemo
```

Stdout:

```text
Hello, Linh. You have 2 new messages.
Bạn có 2 tin nhắn mới, Linh.
```

**Luồng hoạt động:**

1. Java xác định locale mà người dùng yêu cầu.
2. `ResourceBundle.getBundle("messages", locale)` tìm một bundle theo quy tắc locale/fallback.
3. `getString("inbox.summary")` lấy **toàn câu** bằng key cố định.
4. `new MessageFormat(pattern, locale)` tạo formatter với locale mong muốn.
5. `format(new Object[] {name, count})` chèn dữ liệu vào đúng vị trí mà bản dịch quy định.

Các file `.properties` phải có mặt trên classpath. Trong Maven hoặc Gradle, thông thường đặt chúng ở `src/main/resources`. Với Java 9+ và `PropertyResourceBundle`, UTF-8 là cách mã hóa mặc định theo cơ chế chuẩn; cần giữ encoding nhất quán trong công cụ biên dịch, soạn thảo và dịch thuật.

**Phân biệt hai loại fallback:** nếu không có bundle cho locale được yêu cầu, `ResourceBundle` có cơ chế tìm bundle cha, locale mặc định và bundle gốc theo quy tắc riêng. Nếu đã chọn được bundle nhưng thiếu một key, việc tra cứu có thể dùng parent bundle. `MessageFormat` không xử lý việc tìm bản dịch; nó chỉ nhận `pattern` sau khi lookup.

## 6. Vì sao việc ghép câu hay hỏng khi đổi ngôn ngữ?

### 6.1. Thứ tự từ và vị trí tham số

Các ngôn ngữ có thể đặt chủ thể, đối tượng hoặc tên người ở vị trí khác nhau. Bản dịch toàn câu có thể dùng `{1}` trước `{0}`; ghép `prefix + value + suffix` không cho translator quyền đó.

### 6.2. Dấu câu và khoảng trắng

Nếu key `greeting.prefix` kết thúc bằng dấu phẩy và khoảng trắng, còn `greeting.suffix` có dấu chấm than, một chỉnh sửa nhỏ có thể tạo hai dấu cách hoặc thiếu khoảng trắng. Một số ngôn ngữ có khoảng cách và dấu câu khác nhau. Đặt chúng trong toàn câu giúp trách nhiệm rõ ràng.

### 6.3. Ngữ pháp phụ thuộc số lượng

Câu kiểu `count + " files"` không đủ khi cần hình thức số ít/số nhiều, và quy tắc khác nhau giữa các ngôn ngữ. Tiếng Anh phân biệt “1 file” và “2 files”; nhiều ngôn ngữ có **hơn hai loại số lượng**, hoặc hình thức phụ thuộc giá trị và ngữ cảnh. Không nên chỉ dịch riêng từ “file” rồi nối sau số.

### 6.4. Giới tính, cách xưng hô và sắc thái

Một câu thông báo có thể thay đổi cách xưng hô theo đối tượng, quan hệ xã hội hoặc ngữ pháp của ngôn ngữ. Chia thành các mảnh từ vựng thường khiến translator không nhìn thấy bối cảnh. Lưu cả câu, thêm chú thích ngữ cảnh và tạo biến thể thông điệp khi cần.

### 6.5. Số, ngày và tiền tệ

Nếu chuyển `double` hoặc `Date` thành chuỗi trước khi chọn locale, có thể đem dấu phân cách số hoặc tên tháng của ngôn ngữ này vào câu của ngôn ngữ khác. Mẫu `{0,number}`, `{0,number,integer}`, `{0,date,short}` có thể trì hoãn định dạng cho đúng locale của formatter. Múi giờ là vấn đề riêng; cần lựa chọn rõ khi hiển thị thời điểm.

### 6.6. Tính nhất quán và dễ thay đổi

Khi một câu là một key, người viết nội dung có thể thay đổi giọng văn, dấu câu và thứ tự thành phần trong một nơi. Code chỉ biết hợp đồng đối số. Việc kiểm thử cũng có thể dựa trên tập key và định dạng câu, ít phụ thuộc vào số mảnh rải rác.

## 7. Định dạng số và ngày phải gắn với ngữ cảnh người đọc

Một số mẫu của `MessageFormat`:

```text
Total items: {0,number,integer}
Price: {0,number,currency}
Processed on {0,date,short}
Started at {0,time,short}
```

Các tham số `number`, `date`, `time` dựa vào locale của `MessageFormat`. Với `number,currency`, đơn vị tiền tệ mặc định thường được suy ra từ locale; nếu nghiệp vụ quản lý nhiều đơn vị tiền, hãy xác định `Currency` và cấu hình `NumberFormat` phù hợp thay vì suy diễn toàn bộ từ ngôn ngữ.

Nếu ứng dụng cần hiển thị thời điểm, cần xác định thêm `TimeZone` của formatter/ngữ cảnh người dùng. Locale không tự chọn đúng múi giờ.

**Không nhầm định dạng giao diện với serialization:** JSON number, timestamp ISO, mã định danh hay dữ liệu trao đổi API phải theo đặc tả giao thức. Không dùng `MessageFormat` để sinh JSON bằng cách nối một số đoạn văn bản: escaping, kiểu dữ liệu và bảo mật cần serializer chuyên dụng.

## 8. Số ít/số nhiều: ví dụ ChoiceFormat và giới hạn của nó

Java `MessageFormat` hỗ trợ cú pháp `choice` để tạo một số nhánh dựa trên giá trị số. Ví dụ tiếng Anh đơn giản:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceDemo {
    public static void main(String[] args) {
        String pattern =
                "{0,choice,0#No items|1#One item|1<{0,number,integer} items}";

        MessageFormat format = new MessageFormat(pattern, Locale.US);

        System.out.println(format.format(new Object[] {0}));
        System.out.println(format.format(new Object[] {1}));
        System.out.println(format.format(new Object[] {2}));
    }
}
```

Lưu `ChoiceDemo.java`, rồi chạy:

```bash
javac -encoding UTF-8 ChoiceDemo.java
java ChoiceDemo
```

Stdout:

```text
No items
One item
2 items
```

Ở đây `0#` áp dụng từ mốc 0, `1#` từ mốc 1, và `1<` áp dụng cho giá trị **lớn hơn 1**. Mẫu có thể chứa `{0,number,integer}` trong nhánh, nên Java tiếp tục xử lý placeholder lồng nhau.

Đây chỉ là ví dụ cho tiếng Anh và số nguyên không âm. **Không nên sao chép quy tắc 0/1/nhiều cho mọi ngôn ngữ.** `ChoiceFormat` dựa trên ranh giới số, không cung cấp đầy đủ plural categories của CLDR như `one`, `few`, `many` tùy ngôn ngữ. Khi sản phẩm cần nhiều ngôn ngữ và pluralization chính xác, cân nhắc hệ thống bản dịch hỗ trợ plural rules theo CLDR/ICU hoặc giải pháp i18n được kiểm chứng, đồng thời giữ toàn câu trong từng nhánh.

Điểm chung vẫn là: không nối phần đầu, số lượng và danh từ một cách cố định từ Java.

## 9. Dấu nháy đơn, ngoặc nhọn và ký tự đặc biệt trong pattern

`MessageFormat` có cú pháp riêng: **dấu nháy đơn** `'` dùng để quote một đoạn literal. Để hiển thị một dấu nháy đơn trong pattern, thường phải viết thành `''` (hai dấu nháy đơn). Ví dụ:

```java
MessageFormat format = new MessageFormat(
        "You''re welcome, {0}!", Locale.US);
System.out.println(format.format(new Object[] {"Linh"}));
```

Stdout:

```text
You're welcome, Linh!
```

Nếu viết `You're welcome, {0}!` trực tiếp trong pattern, dấu `'` có thể bắt đầu vùng quote, khiến `{0}` không được xử lý như mong muốn. Khi dịch các câu dùng apostrophe (ví dụ tiếng Pháp), đây là một lỗi khá phổ biến.

Dấu ngoặc nhọn `{` và `}` cũng có ý nghĩa đánh dấu tham số. Nếu cần hiển thị chúng như văn bản, phải dùng quy tắc quote của `MessageFormat`. Tránh đưa chuỗi chưa kiểm soát từ người dùng vào **pattern**; người dùng chỉ nên cung cấp **argument values**, không phải một mẫu định dạng tự do được parser thực thi.

Với file `.properties`, còn có quy tắc escape riêng của định dạng properties, ví dụ `\\` hoặc ký tự xuống dòng. Vì vậy một mẫu phải đúng ở **hai tầng**: cú pháp file tài nguyên và cú pháp MessageFormat sau khi được đọc. Kiểm thử nên dùng đúng đường nạp ResourceBundle thực tế.

## 10. Thiết kế khóa và hợp đồng tham số

Một key dịch tốt diễn đạt *mục đích* của thông điệp, không chỉ lặp nguyên câu tiếng Anh:

```properties
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
checkout.total=Your total is {0,number,currency}.
profile.update.success=Your profile was updated.
```

Để người dịch không nhầm `{0}` và `{1}`, ghi ngữ cảnh:

```properties
# {0}: recipient display name; {1}: unread message count (integer)
inbox.summary=Hello, {0}. You have {1,number,integer} new messages.
```

Những quy tắc nên thống nhất trong dự án:

1. **Một key tương ứng một ý nghĩa và một ngữ cảnh hiển thị.** Hai nút cùng chữ “Open” nhưng khác mục đích có thể cần key riêng.
2. **Các đối số có thứ tự và kiểu rõ ràng.** Ví dụ `{0}` là tên hiển thị (`String`), `{1}` là số lượng (`Number`).
3. **Mọi locale dùng cùng hợp đồng đối số**, nhưng được đổi vị trí và thay cấu trúc câu.
4. **Không xóa placeholder bắt buộc** hoặc thay cú pháp `{0}` bằng `%s` tùy tiện. `String.format` và `MessageFormat` là hai hệ cú pháp khác nhau.
5. **Đổi câu chữ không buộc đổi key**. Đổi ý nghĩa hoặc hợp đồng đối số cần được xem là thay đổi giao diện giữa code và tài nguyên dịch.
6. **Không nối câu hoàn chỉnh với một mảnh câu khác** chỉ vì muốn “tái sử dụng”. Sự trùng câu giữa hai vị trí hôm nay không đảm bảo bản dịch về sau giống nhau.

Nếu ngôn ngữ đích không cần một tham số nhất định, bản dịch có thể chủ động không dùng nó khi có lý do chính đáng; tuy vậy, key quan trọng nên có kiểm thử để tránh lỗi vô tình bỏ sót dữ liệu. Đặc biệt với số tiền, ngày, tên và điều kiện nghiệp vụ, không được đánh rơi thông tin cần thiết.

## 11. MessageFormat khác String.format và nối StringBuilder thế nào?

- **Nối chuỗi / `StringBuilder`:** hữu ích để tạo các dữ liệu kỹ thuật có cấu trúc đơn giản hoặc ghép những thành phần **không phải câu văn cần dịch**. Không nên là cơ chế chính để địa phương hóa cả câu.
- **`String.format`:** hỗ trợ cú pháp kiểu `%s`, `%d`, `%.2f` và có overload nhận `Locale`. Có thể dùng cho thông điệp đơn giản, nhưng bản dịch phải tuân thủ các quy tắc đánh chỉ số tham số của Formatter nếu muốn đổi thứ tự.
- **`MessageFormat`:** thiết kế để xử lý message pattern có `{0}`, `{1,number}`, `{2,date}` và những cấu trúc lựa chọn; được dùng phổ biến kết hợp ResourceBundle.

Ví dụ `String.format(Locale.US, "Hello %s", name)` vẫn là một thông điệp đủ ngắn hợp lệ. Giá trị của `MessageFormat` rõ hơn khi bạn có **cả một hệ thống mẫu dịch** với tham số, số và ngày. Điều cốt lõi của bài này là **đơn vị dịch phải là toàn câu**, không nhất thiết mỗi câu đều phải dùng một API duy nhất.

## 12. Các lỗi dễ gặp khi đưa vào sản phẩm

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Dịch `prefix` và `suffix` độc lập | Mất quyền đổi thứ tự và dấu câu | Dịch toàn câu với placeholder |
| Dịch riêng danh từ và nối sau số | Không xử lý được số ít/số nhiều nhiều ngôn ngữ | Dùng thông điệp đầy đủ cùng cơ chế plural phù hợp |
| Viết `{0}` theo thứ tự cứng trong code | Bản dịch khó đặt tên và số đúng vị trí | Giữ hợp đồng đối số, cho bản dịch đổi thứ tự |
| Trộn `%s` với `{0}` | Hai API có cú pháp khác nhau | Chọn rõ formatter cho từng key |
| `MessageFormat` dùng default locale vô tình | Số/ngày có thể sai vùng | Tạo formatter với locale người dùng |
| Nối giá trị đã format trước khi dịch | Cứng dấu số và múi giờ không phù hợp | Truyền giá trị typed, định dạng trong message hoặc bằng formatter phù hợp |
| Quên escape apostrophe | Placeholder bị quote, hiển thị sai | Dùng `''` và kiểm thử |
| Dùng một nhánh plural tiếng Anh cho mọi locale | Quy tắc đa ngôn ngữ phức tạp hơn | Dùng giải pháp plural bản địa hóa đã kiểm chứng |
| Gộp các phần dịch giống chữ nhưng khác nghĩa | Người dịch thiếu ngữ cảnh | Đặt key theo mục đích |
| Xem `MessageFormat` là bộ lọc XSS/SQL | Nó chỉ định dạng thông điệp | Escape theo ngữ cảnh đầu ra; dùng prepared statement/serializer thích hợp |
| Chia sẻ đối tượng `MessageFormat` mutable giữa thread | Không an toàn cho cập nhật/format đồng thời | Tạo instance theo lần dùng, hoặc quản lý bản sao/đồng bộ phù hợp |

`MessageFormat` có trạng thái có thể thay đổi qua `applyPattern`, `setFormat`, v.v. Không coi một instance mutable chia sẻ tự do giữa nhiều luồng là thread-safe. Tạo một instance mới khi render hoặc áp dụng một chiến lược quản lý đồng thời được kiểm chứng.

Dữ liệu người dùng khi đưa vào `{0}` được chèn như dữ liệu; `MessageFormat` **không** làm HTML escaping. Nếu kết quả được đưa vào HTML, JSON, SQL hoặc log, tầng tiêu thụ vẫn phải dùng cách mã hóa/escape đúng theo context.

## 13. Kiểm thử: chứng minh câu dịch tự nhiên và đầy đủ

Với mỗi key có tham số, nên kiểm tra:

- **Đổi vị trí:** một ngôn ngữ sử dụng `{0}` trước `{1}`, ngôn ngữ khác đảo thứ tự, nhưng code vẫn truyền cùng dữ liệu.
- **Giữ đúng kiểu dữ liệu:** số lượng truyền dưới dạng `Number`, ngày dưới dạng `Date`/kiểu được formatter hỗ trợ, không làm mất thông tin bằng `toString` sớm.
- **Đúng dấu câu:** khoảng trắng, dấu phẩy, dấu chấm, ngoặc và nháy đơn không bị sai.
- **Đủ tham số quan trọng:** thông điệp kết quả thể hiện những giá trị nghiệp vụ bắt buộc.
- **Các trường hợp số:** 0, 1, 2, nhiều, giá trị biên, và mọi plural categories cần hỗ trợ.
- **Khác locale:** chạy với `vi-VN`, `en-US` và các locale thực sự hỗ trợ; xác nhận cách định dạng số và ngày.
- **Tài nguyên:** key có trong bundle chính; mọi bản dịch chứa mẫu hợp lệ, placeholder đúng hợp đồng và không bị thiếu.
- **Fallback:** nếu một locale chưa có bản dịch, chính sách hiển thị có chủ đích; không giả định `ResourceBundle` sẽ luôn chọn ngôn ngữ mong muốn.
- **Nội dung nguy hiểm:** với dữ liệu chứa `<`, `&`, dấu nháy hoặc ký tự đặc biệt, bảo đảm tầng xuất kết quả có escaping phù hợp.

Một bài test điển hình có thể kiểm tra ngay hai dòng stdout ở phần 4. Ngoài automated tests, cần có **review ngôn ngữ thực tế** vì một mẫu có thể hợp lệ về cú pháp nhưng vẫn sai ngữ pháp.

## 14. Khi nào cần giải pháp nâng cao?

`MessageFormat` của JDK phù hợp để học nguyên tắc toàn câu, chèn tham số, định dạng số/ngày và xử lý một số mẫu `choice`. Với dự án có nhiều ngôn ngữ cần quy tắc plural/gender phức tạp, khả năng đổi trật tự câu và bản địa hóa số lượng chuyên sâu, có thể dùng các giải pháp dựa trên ICU MessageFormat hoặc thư viện i18n của framework, với chính sách format và tài nguyên rõ ràng.

Dù chọn công cụ nào, những nguyên tắc vẫn giữ nguyên:

- **Cả câu là đơn vị dịch**, bao gồm dấu câu và cấu trúc ngữ pháp.
- **Dữ liệu động là tham số có hợp đồng**, không phải các mảnh câu.
- **Người dịch có ngữ cảnh** về ý nghĩa và kiểu tham số.
- **Locale của người dùng điều khiển định dạng hiển thị**; không vô tình dùng locale máy chủ.
- **Mỗi bản dịch được kiểm thử như một thông điệp hoàn chỉnh**, bao gồm trường hợp lỗi và fallback.

## 15. Bài tập thực hành

1. Thay `count = 2` thành `count = 12` ở phần 4. Xác nhận hai bản dịch vẫn dùng cùng danh sách đối số; chỉ vị trí tham số khác nhau.
2. Viết phiên bản nối `prefix + name + middle + count + suffix`. Thử chuyển tên người xuống cuối câu; quan sát phải sửa Java hoặc tạo logic riêng.
3. Thêm file `messages_fr.properties` với toàn câu tiếng Pháp và cùng hợp đồng `{0}` là tên, `{1}` là số lượng. Sửa chương trình để gọi locale `fr-FR`, không tạo nhánh nối chuỗi mới.
4. Tạo mẫu chứa apostrophe: `You''re welcome, {0}!`. Thử sửa thành một nháy đơn để quan sát cách parser xử lý khác nhau.
5. Thêm thông điệp về số tệp hoặc lượt đăng ký. Kiểm thử 0, 1, 2, 5, 21; xác định quy tắc số ít/số nhiều của từng ngôn ngữ hỗ trợ trước khi chọn cơ chế `choice` hay plural nâng cao.
6. Thử truyền một tên chứa `<tag>` vào argument. Chú ý `MessageFormat` không tự escape HTML; nếu render trong web, yêu cầu encode theo ngữ cảnh HTML.

**Ghi nhớ:** Lỗi của cách nối các mảnh văn bản không chỉ là code trông dài. Nó lấy mất khả năng viết **một câu tự nhiên và hoàn chỉnh** của người dịch. `MessageFormat` giải quyết bằng cách giữ thông điệp nguyên vẹn, còn biến động được đánh dấu bằng các tham số có thể đặt ở bất kỳ vị trí thích hợp nào trong bản dịch.

## Tài liệu tham khảo

- [Oracle JDK 21 — MessageFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/MessageFormat.html)
- [Oracle JDK 21 — ResourceBundle](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/ResourceBundle.html)
- [Oracle JDK 21 — ChoiceFormat](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/text/ChoiceFormat.html)
- [Unicode CLDR — Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules)
