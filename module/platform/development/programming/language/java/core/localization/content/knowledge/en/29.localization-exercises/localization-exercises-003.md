# Tạo thông điệp có tham số và nhánh số lượng trong Java

Một ứng dụng đa ngôn ngữ không nên ghép cố định các mảnh câu như `"Bạn có " + count + " tệp"` rồi áp dụng cho mọi ngôn ngữ. Ngoài việc cần chèn số, tên hoặc ngày vào thông điệp, **ngữ pháp của câu có thể thay đổi theo số lượng**, và thứ tự các thành phần có thể khác nhau giữa các ngôn ngữ. Chẳng hạn tiếng Anh thường phân biệt “one file” và “two files”, còn tiếng Việt có thể dùng cấu trúc “1 tệp”, “2 tệp” mà không đổi dạng danh từ.

Trong Java Core, có thể kết hợp **`ResourceBundle`**, **`MessageFormat`** và **`ChoiceFormat`** để xây dựng thông điệp được dịch, chèn tham số và chọn **nhánh theo ngưỡng số**. Đây là một bài **thực hành tổng hợp**: ta sẽ viết một chương trình Java 17+, định nghĩa tài nguyên tiếng Anh/tiếng Việt, phân tích pattern, kiểm chứng đầu ra và tìm hiểu khi nào khả năng tiêu chuẩn của Java không đủ cho plural rules của nhiều ngôn ngữ.

**Giới hạn cần biết ngay:** `ChoiceFormat` là công cụ chọn nhánh theo số/ngưỡng; **không phải một bộ thực thi đầy đủ Unicode CLDR plural categories**. `java.text.MessageFormat` trong Java 17 **không** hiểu trực tiếp cú pháp ICU `{count, plural, ...}`. Những hệ thống cần plural/select theo ngôn ngữ phức tạp nên dùng một engine phù hợp, như ICU4J, hoặc một chiến lược dịch có kiểm soát.

## 1. Bài toán: một thông điệp có nhiều tham số và dạng câu

Giả sử trang quản lý tài liệu cần thông báo cho người dùng “An” theo số tệp:

| Số tệp | Tiếng Anh | Tiếng Việt |
| ---: | --- | --- |
| 0 | An: no files | An: không có tệp |
| 1 | An: one file | An: 1 tệp |
| 2 | An: 2 files | An: 2 tệp |
| 5 | An: 5 files | An: 5 tệp |

Có hai thông tin biến đổi:

- **`owner`**: tên người dùng, ví dụ `An` — tham số văn bản.
- **`count`**: số lượng tệp, ví dụ `0`, `1` hoặc `2` — tham số số và điều kiện chọn nhánh.

Một giải pháp đúng cần **tách văn bản nguồn dịch** khỏi code nghiệp vụ. Code truyền tham số có ý nghĩa rõ ràng; tài nguyên theo locale quyết định câu nào được dùng. Formatter chịu trách nhiệm chèn tham số và định dạng số theo locale.

### Vì sao ghép chuỗi bằng toán tử + không đủ?

Ví dụ dễ viết nhưng kém quốc tế hóa:

~~~java
String message = owner + " has " + count + " files";
~~~

Kết quả với `count = 1` là `"An has 1 files"` — sai ngữ pháp tiếng Anh. Nếu thay bằng `count == 1 ? "file" : "files"`, ta vẫn đặt cố định cấu trúc tiếng Anh trong code, chưa xét những ngôn ngữ có nhiều dạng số lượng hoặc trật tự câu khác.

Đừng chuyển vấn đề thành phép “dịch từng từ”:

~~~text
prefix + number + suffix
~~~

Một số ngôn ngữ phải đổi **cả câu**, giới từ, giống, cách, thứ tự hoặc dạng danh từ. Vì vậy, **người dịch cần quyền kiểm soát thông điệp hoàn chỉnh của mỗi nhánh**, không chỉ một từ “file”.

## 2. Ba API tham gia và trách nhiệm riêng

| API | Package | Vai trò |
| --- | --- | --- |
| `Locale` | `java.util` | Chỉ định ngôn ngữ/vùng của nội dung và cách định dạng |
| `ResourceBundle` | `java.util` | Nạp pattern văn bản được dịch theo locale và fallback |
| `MessageFormat` | `java.text` | Chèn các tham số `{0}`, `{1}`; gọi định dạng số/ngày/giờ và xử lý choice |
| `ChoiceFormat` | `java.text` | Chọn đoạn thông điệp theo ngưỡng giá trị số |
| `NumberFormat` | `java.text` | Định dạng số, tiền, phần trăm khi cần điều khiển riêng |

Trong ví dụ Java 17, thứ tự trách nhiệm là:

~~~text
Nghiệp vụ: owner="An", count=2
                   |
                   v
          kiểm tra count >= 0
                   |
                   v
      xác định Locale: en-US / vi-VN
                   |
                   v
     ResourceBundle.getBundle("messages", locale)
                   |
                   v
    nhận pattern cho khóa "files"
                   |
                   v
       new MessageFormat(pattern, locale)
                   |
                   v
     format(new Object[]{owner, count})
                   |
                   v
     thông điệp hiển thị theo locale
~~~

**`Locale` không tự dịch câu.** Các bản dịch của ứng dụng phải được cung cấp trong bundle hoặc hệ thống localization tương ứng. `MessageFormat` không tự đoán người dùng muốn đọc “file” hay “tệp”; nó định dạng theo pattern đã được người dịch/nhóm sản phẩm đưa vào.

## 3. Cú pháp tham số trong MessageFormat

Một số mẫu cơ bản:

~~~text
Hello, {0}!
User {0} has {1,number,integer} points.
The price is {0,number,currency}.
The deadline is {0,date,short}.
Completion: {0,number,percent}.
~~~

Các thành phần chính:

- `{0}`: tham số có **chỉ số 0** trong mảng đối số.
- `{1}`: tham số có **chỉ số 1**; không bắt buộc xuất hiện sau `{0}` trong pattern.
- `{1,number,integer}`: dùng định dạng số nguyên theo locale của `MessageFormat`.
- `{0,number,currency}`: dùng định dạng tiền theo locale; **không** tự biết đơn vị tiền thực của giao dịch nếu chỉ truyền một con số.
- `{0,date,short}` và `{0,time,short}`: dùng cơ chế `java.text.DateFormat`; với Java 17, phải cung cấp kiểu đối số thời gian tương thích, điển hình là `java.util.Date`.
- `{1,choice,...}`: chọn nhánh theo số.

**Chỉ số tham số bắt đầu từ 0.** Thứ tự tham số có thể thay đổi trong bản dịch. Ví dụ cùng hai đối số `[name, score]`, một ngôn ngữ có thể đặt `{0}` trước `{1}` và ngôn ngữ khác đảo ngược.

### MessageFormat không dùng cú pháp String.format

`MessageFormat` khác với `String.format` hoặc `Formatter`. Trong `String.format`, ta thường gặp `%s`, `%d` và `%.2f`; còn `MessageFormat` dùng `{0}`, `{1,number}` và các format type riêng.

Đừng viết `"%s có %d tệp"` rồi đưa nguyên pattern đó vào `new MessageFormat(...)` với hy vọng các dấu phần trăm được thay như `String.format`.

Nếu đối số `{0}` là một chuỗi văn bản, `MessageFormat` chèn nó theo dạng được cung cấp, không tự dịch, không tự HTML-escape và không tự kiểm soát độ dài. Validation và render an toàn vẫn là trách nhiệm của ứng dụng.

## 4. ChoiceFormat: chọn nhánh bằng ngưỡng

Một pattern choice:

~~~text
{1,choice,0#no files|1#one file|1<{1,number,integer} files}
~~~

Phân tích:

1. `1` ngay sau dấu `{` là **argument index** — tức `count` nằm ở phần tử thứ hai trong mảng đối số.
2. `choice` báo dùng `ChoiceFormat`.
3. `0#no files` nghĩa là nhánh bắt đầu tại **ngưỡng 0 bao gồm 0**.
4. `1#one file` nghĩa là nhánh từ **ngưỡng 1 bao gồm 1**.
5. `1<{1,number,integer} files` nghĩa là nhánh cho **giá trị lớn hơn 1**, và đoạn được chọn chứa tham số `{1,number,integer}` cần định dạng lần nữa.
6. `|` tách các lựa chọn.

Nhánh được chọn theo **giới hạn số** đã sắp tăng dần. Nó không phải biểu thức `if/else` tùy ý, không nhận kiểu boolean và không tự phân loại số nhiều theo ngôn ngữ. Với dữ liệu không phù hợp các ngưỡng, cần có validation và lựa chọn nhánh mặc định phù hợp.

### Ý nghĩa của # và <

| Cú pháp | Ý nghĩa khái niệm |
| --- | --- |
| `0#text` | Ngưỡng **bao gồm** giá trị 0 |
| `1#text` | Ngưỡng **bao gồm** giá trị 1 |
| `1<text` | Ngưỡng **lớn hơn** 1 |
| `2#text` | Ngưỡng **bao gồm** giá trị 2 |

Vì `ChoiceFormat` dùng các ngưỡng và số thực, việc diễn giải khi input là số thập phân hoặc số lớn cần kiểm thử rõ. Với **số đếm tệp**, nghiệp vụ nên nhận **số nguyên không âm**; không nên để `1.5` tệp lọt vào rồi ngạc nhiên vì formatter chọn nhánh theo số thực và tiếp đó làm tròn khi hiển thị.

**Đừng bỏ kiểm tra số âm.** Với pattern bắt đầu ở ngưỡng 0, `ChoiceFormat` có thể chọn nhánh đầu cho giá trị thấp hơn ngưỡng nhỏ nhất. Nếu `count=-1`, việc hiển thị “no files” sẽ che giấu dữ liệu nghiệp vụ không hợp lệ. Hãy từ chối ở tầng domain.

### Nhánh có thể chứa tham số lồng nhau

Trong ví dụ:

~~~text
1<{1,number,integer} files
~~~

Khi `count=2`, `ChoiceFormat` chọn đoạn chứa `{1,number,integer}`; `MessageFormat` nhận diện dấu `{...}` và **định dạng lại đoạn được chọn**. Đây là cơ chế nested choice formatting được API Java 17 hỗ trợ.

Ví dụ toàn pattern:

~~~text
{0}: {1,choice,0#no files|1#one file|1<{1,number,integer} files}
~~~

Với `Object[]{"An", 2}` và `Locale.US`, kết quả:

~~~text
An: 2 files
~~~

**Cẩn thận với đệ quy:** việc tạo `ChoiceFormat` và `MessageFormat` bằng code riêng rồi cho choice branch tham chiếu lại formatter theo cấu trúc tuần hoàn có thể gây đệ quy không kết thúc. Giữ các template đã được review và test theo miền dữ liệu thực.

## 5. Tiếng Việt không nhất thiết cần nhánh giống tiếng Anh

Một pattern tiếng Việt đơn giản:

~~~text
{0}: {1,choice,0#không có tệp|0<{1,number,integer} tệp}
~~~

Ở đây:

- `count=0` → `An: không có tệp`.
- `count=1` → `An: 1 tệp`.
- `count=2` → `An: 2 tệp`.

Điểm quan trọng là **không ép mọi ngôn ngữ có cùng số nhánh**. Tiếng Anh trong ví dụ dùng ba nhánh; tiếng Việt dùng hai. Đây là **lựa chọn nội dung cụ thể cho thông điệp này**, không phải khẳng định rằng tất cả cấu trúc ngữ pháp tiếng Việt chỉ cần hai lựa chọn hoặc mọi thông điệp tiếng Việt đều có quy tắc số lượng giống nhau.

Thay vì cố tái sử dụng cùng một choice pattern cho tất cả locale, mỗi bản dịch nên có pattern đầy đủ và được duyệt bởi người hiểu ngôn ngữ.

### Bản dịch có thể đổi trật tự tham số

Giả sử thông điệp cần hai tham số `user` và `count`. Một ngôn ngữ có thể bắt đầu bằng tên người, ngôn ngữ khác có thể bắt đầu bằng số lượng. Các placeholder có index cho phép người dịch đổi thứ tự mà **không đổi mảng đối số** của code nghiệp vụ.

Tránh nối các mảnh từ nhiều bundle như:

~~~java
String message = bundle.getString("prefix")
        + count
        + bundle.getString("suffix");
~~~

Cách này khóa cứng cấu trúc câu và có thể khiến dịch đúng ngữ pháp trở nên bất khả thi. Hãy dịch **cả thông điệp hoặc cả nhánh hoàn chỉnh**.

## 6. Cấu trúc project thực hành

Tạo cấu trúc:

~~~text
plural-message-demo/
  src/
    PluralMessagesDemo.java
  resources/
    messages_en.properties
    messages_vi.properties
  out/                    (được tạo khi biên dịch)
~~~

Ba tệp nguồn thực sự cần là một tệp Java và hai tệp tài nguyên. Thư mục `out` được tạo bởi lệnh trong bài; nó không phải tệp source được viết bằng tay.

### File 1: resources/messages_en.properties

~~~properties
files={0}: {1,choice,0#no files|1#one file|1<{1,number,integer} files}
today=Today''s total: {0,number,integer}
~~~

### File 2: resources/messages_vi.properties

~~~properties
files={0}: {1,choice,0#không có tệp|0<{1,number,integer} tệp}
today=Tổng hôm nay: {0,number,integer}
~~~

**Giải thích file:**

- Mỗi file là một `ResourceBundle` dạng properties.
- Khóa `files` có pattern hoàn chỉnh theo ngôn ngữ.
- Khóa `today` dùng để minh họa dấu nháy đơn trong `MessageFormat`.
- `{0}` là tên người dùng; `{1}` là số tệp.
- Pattern tiếng Anh có ba nhánh; tiếng Việt có hai nhánh.
- Với **JDK 17**, `PropertyResourceBundle` đọc properties bằng **UTF-8 theo mặc định**, và có cơ chế fallback tương thích ISO-8859-1 nếu byte không hợp lệ trong UTF-8. Nên lưu tệp thực tế dưới UTF-8 và kiểm tra charset khi build.
- Không đặt file `messages_vi.properties` trong thư mục package khác với base name nếu code gọi `getBundle("messages", ...)` ở classpath root.

**Quy tắc dấu nháy đơn:** Trong `MessageFormat`, dấu nháy đơn có ý nghĩa đặc biệt để quote ký tự mẫu. `Today''s` (hai dấu `'`) sẽ in một dấu apostrophe: `Today's`. Viết `Today's` với một dấu nháy trong pattern có thể làm nội dung sau đó bị hiểu là phần quoted, khiến placeholder không được thay đúng cách.

### File 3: src/PluralMessagesDemo.java

~~~java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class PluralMessagesDemo {
    private static String renderFiles(
            ResourceBundle messages,
            Locale locale,
            String owner,
            int count) {

        if (count < 0) {
            throw new IllegalArgumentException(
                    "count must be >= 0");
        }

        String pattern = messages.getString("files");
        MessageFormat formatter = new MessageFormat(pattern, locale);
        return formatter.format(new Object[] { owner, count });
    }

    public static void main(String[] args) {
        Locale english = Locale.US;
        Locale vietnamese = Locale.forLanguageTag("vi-VN");

        ResourceBundle en =
                ResourceBundle.getBundle("messages", english);
        ResourceBundle vi =
                ResourceBundle.getBundle("messages", vietnamese);

        for (int count : new int[] { 0, 1, 2 }) {
            System.out.println("EN " + count + ": "
                    + renderFiles(en, english, "An", count));
        }

        for (int count : new int[] { 0, 1, 2 }) {
            System.out.println("VI " + count + ": "
                    + renderFiles(vi, vietnamese, "An", count));
        }

        MessageFormat quoted = new MessageFormat(
                en.getString("today"), english);
        System.out.println("Quoted: "
                + quoted.format(new Object[] { 2 }));

        System.out.println("Argument as data: "
                + renderFiles(en, english, "Eva {0}", 2));

        try {
            renderFiles(en, english, "An", -1);
        } catch (IllegalArgumentException ex) {
            System.out.println("Negative count: rejected");
        }
    }
}
~~~

Chương trình là **Java 17 chạy được** khi hai properties nằm trên classpath như bước tiếp theo. Nó chủ động tạo formatter mới cho mỗi lần render, nên không chia sẻ một `MessageFormat` có trạng thái thay đổi được giữa các request.

### Biên dịch và chạy trên macOS/Linux

Từ thư mục `plural-message-demo`:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -d out src/PluralMessagesDemo.java
cp resources/messages_en.properties out/
cp resources/messages_vi.properties out/
java -cp out PluralMessagesDemo
~~~

### Biên dịch và chạy trên Windows PowerShell

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -d out src/PluralMessagesDemo.java
Copy-Item resources/messages_en.properties out/
Copy-Item resources/messages_vi.properties out/
java -cp out PluralMessagesDemo
~~~

`java -cp out` tìm được cả `PluralMessagesDemo.class` lẫn `messages_en.properties` và `messages_vi.properties` ở classpath root.

### Stdout mong đợi

Khi file properties được lưu đúng UTF-8 và terminal hiển thị Unicode:

~~~text
EN 0: An: no files
EN 1: An: one file
EN 2: An: 2 files
VI 0: An: không có tệp
VI 1: An: 1 tệp
VI 2: An: 2 tệp
Quoted: Today's total: 2
Argument as data: Eva {0}: 2 files
Negative count: rejected
~~~

**Kiểm chứng:** logic `MessageFormat`, `ChoiceFormat`, tham số và dấu apostrophe của ví dụ đã được thử trên JDK: các nhánh tiếng Anh/Việt, chuỗi chứa `{0}` dưới dạng dữ liệu và từ chối số âm cho đúng kết quả. Việc nạp từ `ResourceBundle` phụ thuộc vị trí hai file tài nguyên trên classpath như chỉ dẫn; nếu thiếu file, Java báo `MissingResourceException` thay vì có stdout trên.

Nếu terminal Windows hiện ký tự tiếng Việt thành dấu hỏi dù chương trình đã đọc đúng properties, cần kiểm tra **mã hóa console và file**, không tự kết luận `ChoiceFormat` đã chọn nhánh sai.

## 7. Phân tích từng bước của ví dụ

### Bước 1 — Chọn locale có chủ đích

~~~java
Locale english = Locale.US;
Locale vietnamese = Locale.forLanguageTag("vi-VN");
~~~

`Locale.US` tương ứng ngôn ngữ/vùng `en-US`; `Locale.forLanguageTag("vi-VN")` chọn tiếng Việt/vùng Việt Nam. Không dựa vào `Locale.getDefault()` của máy chủ vì một server có thể phục vụ nhiều người dùng với những ngôn ngữ khác nhau.

### Bước 2 — Nạp pattern theo locale

~~~java
ResourceBundle en =
        ResourceBundle.getBundle("messages", english);
~~~

Java tìm bundle ứng với `messages` và locale. Với `en-US`, nó có thể tìm bundle ngôn ngữ `messages_en.properties` khi không có bản cụ thể hơn `messages_en_US.properties`. Với `vi-VN`, file `messages_vi.properties` được dùng khi không có bản `messages_vi_VN.properties`.

Nếu **không** có một bản dịch phù hợp, `ResourceBundle` có thể thử fallback theo locale mặc định JVM và bundle gốc, tùy quy tắc của API. Vì vậy, trong ứng dụng thực tế cần xác định **ngôn ngữ fallback có chủ ý** (thường là một bundle gốc hoặc chiến lược của sản phẩm), không vô tình để người dùng nhận ngôn ngữ của máy chủ.

### Bước 3 — Validation dữ liệu nghiệp vụ

~~~java
if (count < 0) {
    throw new IllegalArgumentException("count must be >= 0");
}
~~~

Chọn ngưỡng số không thay cho kiểm tra đầu vào. Một số tệp âm là vô nghĩa trong bài toán này. Nếu ứng dụng có điều kiện “không xác định số lượng”, cần một trạng thái riêng hoặc thông điệp riêng, không ngầm mã hóa thành `-1` rồi đưa vào choice pattern.

### Bước 4 — Chọn nhánh và chèn tham số

~~~java
String pattern = messages.getString("files");
MessageFormat formatter = new MessageFormat(pattern, locale);
String output = formatter.format(
        new Object[] { owner, count });
~~~

Đây là **đoạn minh họa** tương ứng phương thức trong chương trình chính. `MessageFormat` phân tích pattern, chọn nhánh `ChoiceFormat` theo `count` và chèn `owner`/`count`. Tham số số trong nhánh `{1,number,integer}` được định dạng theo locale được truyền khi xây formatter.

### Bước 5 — Chữ trong tham số không phải cú pháp template

Ở ví dụ `owner = "Eva {0}"`, kết quả là:

~~~text
Eva {0}: 2 files
~~~

`{0}` bên trong **giá trị tham số** được xem như dữ liệu, không phải placeholder để áp thêm lần nữa. Điều này khác với việc lấy **một pattern không đáng tin** rồi gọi `new MessageFormat(pattern)`. Pattern có cú pháp đặc biệt và phải được xem là cấu hình nội dung được quản lý/kiểm duyệt, không nên cho người dùng tùy ý thay đổi mà không xác thực.

**Lưu ý:** dữ liệu tham số vẫn cần được escape theo **ngữ cảnh output**. Chèn vào HTML phải dùng HTML escaping, chèn vào SQL phải parameterize, chèn vào log cần chú ý control characters; `MessageFormat` không phải bộ lọc bảo mật.

## 8. Trường hợp số nhiều của các ngôn ngữ khác

Ví dụ của chúng ta chỉ có hai ngôn ngữ và một ngữ cảnh “số tệp”. Nhưng nhiều ngôn ngữ có hệ thống số lượng phức tạp:

- Tiếng Anh thường có dạng singular và plural, cùng cách diễn đạt riêng cho số 0 nếu sản phẩm muốn.
- Tiếng Việt trong ví dụ không buộc biến đổi danh từ ở số 1/số 2.
- Một số ngôn ngữ như tiếng Nga, Ba Lan hay Ả Rập có nhiều **plural categories** và quy tắc dựa trên phần dư chia hoặc dạng số, không đơn thuần là `count == 1`.
- Số thập phân, chữ số có phần phân số hay cách phát âm số cũng có thể ảnh hưởng category.

Trong hệ sinh thái Unicode CLDR, quy tắc cardinal/ordinal plural có thể chia giá trị thành các category như `zero`, `one`, `two`, `few`, `many`, `other` tùy ngôn ngữ. **Không phải ngôn ngữ nào cũng dùng đủ các category này**, và category không nhất thiết được xác định bằng một ngưỡng tăng dần.

### ChoiceFormat không tự hiểu plural categories

Pattern choice như:

~~~text
0#no files|1#one file|1<some files
~~~

chỉ xử lý các **khoảng số theo ngưỡng**. Nó không tự tính, chẳng hạn, một category phụ thuộc `n % 10` và `n % 100` theo quy tắc của một ngôn ngữ. Với một miền số nhỏ cố định, bạn có thể lập nhánh thủ công; nhưng việc giả lập một hệ thống plural phức tạp bằng danh sách ngưỡng dài thường khó bảo trì hoặc sai.

**Đừng dịch pattern tiếng Anh theo từng từ rồi dùng y nguyên nhánh 0/1/2 cho tiếng Nga hoặc Ả Rập.** Những ngôn ngữ ấy cần chính sách category và bản dịch toàn câu đã được kiểm chứng.

### Cú pháp ICU plural khác Java 17 MessageFormat

Một mẫu kiểu ICU thường có dạng ý tưởng:

~~~text
{count, plural,
  =0 {No files}
  one {One file}
  other {# files}
}
~~~

Đây là **mẫu theo cú pháp ICU MessageFormat**, **không** phải pattern được `java.text.MessageFormat` trên Java 17 hỗ trợ trực tiếp. Trên Java 17, `MessageFormat` hiểu những format type như `number`, `date`, `time`, `choice`, chứ **không tự nhận ra format type `plural`**.

Nếu cần plural/select chính xác cho nhiều ngôn ngữ, có thể dùng **ICU4J** hoặc nền tảng dịch tương đương, nhưng phải thêm dependency, kiểm tra phiên bản API, quy tắc CLDR, bảo trì tài nguyên và kiểm thử tích hợp. Không giả định một thư viện ngoài có cùng cú pháp hoặc tương thích hoàn toàn với formatter của Java Core.

## 9. Những ranh giới kỹ thuật quan trọng

### 9.1. Số nguyên nghiệp vụ khác định dạng số nguyên

`{1,number,integer}` có nghĩa **in dạng số nguyên** theo `NumberFormat` của locale. Nó không tự bảo đảm đầu vào `1.5` là “một tệp rưỡi hợp lệ”. Nếu sản phẩm đếm đối tượng nguyên, **dùng kiểu số nguyên** và validate tại boundary trước khi định dạng.

Nếu dùng giá trị `long` rất lớn, cần cân nhắc rằng `ChoiceFormat` làm việc bằng các ngưỡng số thực `double`. Những miền số cần phân biệt chính xác từng số nguyên vượt khả năng biểu diễn chính xác của `double` không nên dựa vào so sánh equality choice để ra quyết định nghiệp vụ. Có thể chọn nhánh bằng số nguyên chính xác trước rồi đưa thông điệp đã chọn vào formatter để in.

### 9.2. Dấu phân nhóm phụ thuộc locale

Với `count = 1200`, một mẫu English `{1,number,integer}` có thể hiển thị `1,200`, còn bản Việt có thể hiển thị `1.200` theo dữ liệu locale của JDK được dùng. Cách hiển thị còn phụ thuộc phiên bản CLDR/provider và các lựa chọn numbering system.

Vì vậy không nên lưu lại chuỗi đã render làm **giá trị đếm** trong database/API. Lưu số nguyên `1200`, rồi định dạng tại tầng UI theo locale được người dùng chọn.

### 9.3. NumberFormat và MessageFormat là mutable

`MessageFormat` cho phép `applyPattern`, `setFormat`, `setLocale` và các thao tác thay đổi trạng thái; `NumberFormat` cũng thường mutable. Không chia sẻ cùng một formatter có thể bị chỉnh giữa các request đa luồng nếu không có quản lý đồng bộ.

Trong ví dụ, mỗi lần render tạo một `MessageFormat` mới từ pattern và locale. Với hệ thống traffic lớn, có thể phân tích cache/clone/thread confinement theo hợp đồng, nhưng không nên tối ưu sớm bằng cách dùng chung một formatter mutable cho mọi người dùng.

### 9.4. Thông điệp format theo locale không đồng nghĩa xử lý timezone

Nếu message chứa ngày/giờ:

~~~text
Cuộc họp vào {0,date,short} lúc {0,time,short}
~~~

Formatter `date/time` mặc định làm việc với API `java.text.DateFormat` và các cấu hình timezone của nó. Với Java 17, tham số tương thích điển hình là `java.util.Date`, **không phải trực tiếp `LocalDate`** cho `{0,date,short}`.

Nếu dữ liệu nguồn là một `Instant` hoặc một cuộc họp theo múi giờ người dùng, xác định `ZoneId` đúng bằng nghiệp vụ, rồi thiết lập formatter ngày/giờ thích hợp. Thay `Locale` không tự suy ra timezone, cũng không tự biến `LocalDate` thành `java.util.Date`.

Một hướng kiểm soát rõ là format ngày/giờ bằng `java.time.format.DateTimeFormatter` với `Locale` và `ZoneId`, rồi truyền **chuỗi đã định dạng** làm tham số `{0}` của thông điệp. Nhờ vậy timezone và calendar có thể được xác định riêng với grammar câu.

### 9.5. Currency không tự là đơn vị của giao dịch

`{0,number,currency}` dùng `NumberFormat.getCurrencyInstance(locale)` theo locale của formatter. Nếu đơn hàng thực sự bằng USD nhưng người xem có locale tiếng Việt, không được kết luận tiền giao dịch là VND chỉ vì locale UI. Cần giữ `Currency` và `BigDecimal` riêng, áp rounding policy của nghiệp vụ, rồi định dạng bằng formatter được thiết lập đúng đơn vị.

### 9.6. MessageFormat không tự xử lý dấu nháy như Java string

Hai tầng escape khác nhau:

1. **Java source literal**: dấu `"`, ký tự `\` và các escape phải hợp lệ để tạo `String` Java.
2. **MessageFormat pattern**: dấu apostrophe `'` và ngoặc nhọn `{ }` có ý nghĩa cú pháp của `MessageFormat`.

Trong file properties, bạn thường không phải escape một dấu `"` như trong Java string literal, nhưng vẫn phải viết `''` cho một dấu apostrophe muốn in ra nếu văn bản được xử lý bằng `MessageFormat`.

Ví dụ:

~~~java
String pattern = "Today''s total: {0,number,integer}";
System.out.println(new MessageFormat(pattern, Locale.US)
        .format(new Object[] { 2 }));
// Today's total: 2
~~~

Đây là đoạn minh họa với import `java.text.MessageFormat` và `java.util.Locale`. Khi người dịch dùng apostrophe trong bản dịch Pháp hoặc ngôn ngữ khác, cần hướng dẫn rõ quy tắc này; nếu không pattern có thể in sai hoặc nuốt placeholder.

### 9.7. Không sửa pattern không đáng tin bằng phép replace tùy tiện

Không ghép trực tiếp giá trị người dùng vào **pattern** trước khi parse, ví dụ:

~~~java
String unsafePattern = userText + " {0}";
MessageFormat formatter = new MessageFormat(unsafePattern, locale);
~~~

Đây là **phản ví dụ**. Nếu `userText` chứa `{...}` hoặc apostrophe, nó có thể được xem như cú pháp template, gây lỗi hoặc kết quả ngoài mong đợi. Hãy giữ **pattern cố định và được duyệt** trong tài nguyên, còn dữ liệu người dùng chỉ truyền trong mảng arguments.

Tuy nhiên, đầu ra của `MessageFormat` không tự an toàn cho HTML, JSON, SQL, shell hay markdown. Cần encoding/escaping phù hợp **tại nơi tiêu thụ kết quả**, đồng thời giới hạn dữ liệu từ nguồn không đáng tin.

## 10. Test các nhánh đầy đủ trước khi phát hành

Một bảng test tối thiểu cho bài thực hành:

| Locale | count | Kết quả mong đợi |
| --- | ---: | --- |
| `en-US` | 0 | `An: no files` |
| `en-US` | 1 | `An: one file` |
| `en-US` | 2 | `An: 2 files` |
| `vi-VN` | 0 | `An: không có tệp` |
| `vi-VN` | 1 | `An: 1 tệp` |
| `vi-VN` | 2 | `An: 2 tệp` |
| `en-US` | -1 | Ném `IllegalArgumentException` trước khi format |
| `en-US` | 2, tên `Eva {0}` | `Eva {0}: 2 files` |
| `en-US` | `today=2` | `Today's total: 2` |

Đừng chỉ test một giá trị mặc định như 2. Với choice branch, mọi ranh giới `0`, `1`, `2` và cận bất hợp lệ phải được kiểm thử.

### Những test bổ sung có giá trị

- **Bundle thiếu key:** `getString("files")` có thể ném `MissingResourceException`. Kiểm tra key bắt buộc bằng công cụ build/test.
- **Bundle fallback:** thử locale có bản vùng đầy đủ, locale chỉ có bản ngôn ngữ và locale không có bản phù hợp; xác minh ngôn ngữ fallback sản phẩm đã chọn.
- **Param ordering:** bản dịch đổi vị trí `{0}` và `{1}` vẫn đúng dữ liệu.
- **Quoting:** apostrophe đơn, ngoặc nhọn cần quote và pattern có choice lồng.
- **Integer boundaries:** 0, 1, 2, số rất lớn, số âm, dữ liệu null hoặc không xác định.
- **Number formatting:** kiểm tra `1,200`, `1.200` và các locale khác trên JDK được triển khai, không giả định dấu phân nhóm bất biến.
- **Encoding:** tên người có dấu tiếng Việt, emoji, ký tự kết hợp Unicode và properties UTF-8.
- **Concurrency:** nhiều request/locale cùng lúc không làm formatter bị chỉnh trộn.
- **Security:** input `"{0}"`, apostrophe, HTML tags, line breaks; chúng phải là dữ liệu, không biến thành template hoặc nội dung thực thi.
- **JDK/provider changes:** chạy regression khi nâng JDK hoặc thay dữ liệu CLDR.

Có thể tạo test helper:

~~~java
private static void assertEquals(String expected, String actual) {
    if (!expected.equals(actual)) {
        throw new AssertionError(
                "Expected <" + expected + "> but got <" + actual + ">");
    }
}
~~~

Đây là **đoạn minh họa** bên trong một class; nếu dùng JUnit, chọn assertion và test runner thích hợp. Với nội dung quan trọng, test cả **câu hoàn chỉnh**, không chỉ kiểm tra số lượng ký tự hoặc có chứa tên người.

### Test trên tài nguyên thật quan trọng hơn test một pattern hardcode

Nếu chỉ new `MessageFormat` bằng một chuỗi hardcode trong unit test, bạn chưa chứng minh file `messages_vi.properties` có pattern đúng, resource được đóng gói vào JAR, mọi key được dịch và fallback sản phẩm hoạt động.

Do đó hãy có integration test dùng `ResourceBundle.getBundle(...)` trong **artifact build thực tế**. Điều này đặc biệt quan trọng nếu build có bước mã hóa/chuyển đổi tệp properties hoặc đóng gói bằng Maven/Gradle/JAR.

## 11. Thiết kế khi số lượng là dữ liệu bất đồng bộ hoặc chưa chắc chắn

Một số UI có trạng thái “đang đếm”, “không có quyền xem”, “không có dữ liệu” và “đếm được 0”. Đây là **những trạng thái nghiệp vụ khác nhau**, không nên dùng `count=0` cho tất cả.

Ví dụ:

~~~text
LOADING       → Đang kiểm tra số lượng tệp…
FORBIDDEN     → Không có quyền xem thông tin này.
UNKNOWN       → Chưa xác định số lượng tệp.
KNOWN(0)      → Không có tệp.
KNOWN(1)      → 1 tệp.
KNOWN(2)      → 2 tệp.
~~~

Sơ đồ này là **minh họa state UI**, không phải API Java chuẩn. Có thể chọn **message key** theo trạng thái nghiệp vụ trước, rồi dùng `ChoiceFormat` chỉ khi count đã biết và hợp lệ.

Không đưa `null`, `NaN`, `Infinity` hoặc một sentinel âm vào choice pattern rồi hy vọng formatter quyết định ý nghĩa nghiệp vụ. Nếu số lượng đến từ nhiều nguồn, cần xác thực và làm rõ chính sách tính số lượng trước khi hiển thị.

## 12. Mở rộng bằng ChoiceFormat trong Java code

Ngoài cú pháp `{1,choice,...}` đặt trong pattern, có thể xây một `ChoiceFormat` riêng và gắn vào `MessageFormat`:

~~~java
MessageFormat message = new MessageFormat(
        "{0}: {1}", Locale.US);

double[] limits = { 0, 1, 2 };
String[] forms = {
        "no files",
        "one file",
        "{1,number,integer} files"
};

ChoiceFormat choice = new ChoiceFormat(limits, forms);
message.setFormatByArgumentIndex(1, choice);

String output = message.format(
        new Object[] { "An", 2 });
~~~

Đây là **đoạn minh họa** với import `java.text.MessageFormat`, `java.text.ChoiceFormat` và `java.util.Locale`. Giới hạn 0/1/2 ở đây dành cho **số nguyên đếm tệp**. Nếu các giá trị số thực được phép, hãy thiết kế lại ngưỡng theo đúng ý nghĩa thay vì tùy tiện dùng ba giới hạn trên.

Cách tạo `ChoiceFormat` bằng code có ích khi tổ chức muốn giữ thuật toán chọn nhánh ở tầng Java; tuy nhiên, nếu câu và thứ tự phải được dịch, vẫn cần chuyển các form/tài nguyên sang đúng locale. Cũng phải tránh tạo đồ thị formatter có tham chiếu đệ quy vô hạn khi branch chứa nested placeholders.

### Khi nào nên chọn nhánh trong Java thay vì ChoiceFormat?

Nếu nghiệp vụ chọn theo điều kiện không chỉ là `count` (ví dụ trạng thái tài khoản, quyền truy cập, giới hạn sản phẩm), hoặc cần plural rules CLDR phức tạp, có thể dùng code xác định **message key** dựa trên một chính sách rõ ràng, rồi format câu tương ứng. Nhánh phải được kiểm thử theo **ngôn ngữ và ngữ pháp**, không phải luôn dùng `if (count == 1)` trên tất cả locale.

Với giao diện nhiều ngôn ngữ cần số lượng/giống/cách linh hoạt, cân nhắc một thư viện plural/select được phát triển cho mục tiêu đó, thay vì mở rộng `ChoiceFormat` quá xa phạm vi của nó.

## 13. Lỗi thường gặp và cách khắc phục

| Lỗi | Hệ quả | Cách khắc phục |
| --- | --- | --- |
| Ghép tiếng Anh bằng `"has " + count + " files"` | Sai với 1; khó dịch thứ tự | Dùng message pattern nguyên câu |
| Dùng cùng nhánh plural tiếng Anh cho mọi locale | Sai ngữ pháp ở ngôn ngữ khác | Dịch pattern/nhánh theo từng ngôn ngữ |
| Truyền pattern ICU plural vào Java 17 `MessageFormat` | Format type không được hỗ trợ | Dùng ChoiceFormat phù hợp hoặc ICU engine |
| Nhầm `{0}` là tên biến | Tham số không được thay | Truyền arguments theo chỉ số 0-based |
| Quên `{1,number,integer}` trong nhánh nhiều tệp | Chỉ in chữ, mất số lượng | Nested placeholder phù hợp |
| Không chặn count âm | Có thể in nhầm “no files” | Validate nghiệp vụ trước |
| Dùng `double` không xét miền số | Số thập phân/số lớn chọn nhánh không mong muốn | Chỉ nhận count nguyên; xử lý exact domain |
| Lấy số đã format làm dữ liệu API | Dấu chấm/phẩy đổi theo locale | Lưu số gốc, format ở UI |
| Dùng `Locale.getDefault()` trên server nhiều khách | Kết quả phụ thuộc máy chủ | Truyền locale tường minh |
| Dùng MessageFormat pattern chứa apostrophe đơn | Quote placeholder ngoài ý muốn | Dùng `''` khi cần in `'` |
| Ghép input người dùng vào pattern | Input có thể bị parse như cú pháp | Pattern đáng tin; input trong arguments |
| Nghĩ MessageFormat tự escape HTML | Có thể sinh nội dung không an toàn | Escape theo ngữ cảnh render |
| Không đóng gói properties đúng classpath | `MissingResourceException` | Test integration trên JAR/build cuối |
| Không có bundle fallback có chủ đích | UI rơi về ngôn ngữ máy chủ | Có fallback được định nghĩa |
| Chia một câu thành nhiều translation key | Dịch thiếu tự nhiên, sai trật tự | Dịch cả câu/nhánh |
| Dùng chung formatter mutable giữa nhiều thread | Kết quả có thể bị thay đổi ngoài ý muốn | Tạo formatter riêng hoặc đồng bộ phù hợp |
| Đếm số lượng chưa xác định như 0 | Che giấu trạng thái nghiệp vụ | Tách LOADING/UNKNOWN/KNOWN |
| Test mỗi count=2 | Bỏ lỗi ngưỡng 0/1 | Test mọi nhánh và cận |
| Cho rằng `ResourceBundle` đồng nghĩa dữ liệu CLDR | Không có bản dịch UI trong JDK | Quản lý tài nguyên ứng dụng riêng |
| Kết luận tiếng Việt/tiếng Anh đủ cho mọi plural | Bỏ sót few/many/zero/... | Kiểm thử từng ngôn ngữ và engine |

## 14. Bài tập thực hành tiếp theo

**Bài 1 — Thêm locale khác.** Tạo `messages_fr.properties` với nội dung được người có chuyên môn tiếng Pháp duyệt. Đừng chỉ tự sửa chữ “file”; phải dịch câu hoàn chỉnh và kiểm tra dấu apostrophe của `MessageFormat`.

**Bài 2 — Thêm một tham số.** Mở rộng thông điệp có `{2}` là tên thư mục, ví dụ thông báo “An: 2 files in Projects”. Cho phép người dịch đổi thứ tự tên và thư mục. Đảm bảo `{2}` ở đúng vị trí trong mảng đối số, không được ghép string cứng.

**Bài 3 — Bổ sung kiểm thử.** Chạy count 0, 1, 2, 3, 1200, -1 cho cả tiếng Anh/Việt; xác minh số âm bị từ chối và số lớn vẫn giữ nguyên ở tầng nghiệp vụ. Với output số lớn, đừng giả định dấu phân nhóm giống nhau giữa locale.

**Bài 4 — Thêm trạng thái chưa biết.** Nếu số lượng chưa được tính xong, dùng key `files.loading` riêng trong bundle thay vì truyền `-1` vào `ChoiceFormat`.

**Bài 5 — Đánh giá ICU.** Lấy một ngôn ngữ có nhiều plural categories. Tìm hiểu vì sao chọn nhánh theo `count == 1` không đủ, so sánh cách giải quyết bằng CLDR plural engine với việc dùng `ChoiceFormat` dựa trên ngưỡng.

**Bài 6 — Đóng gói.** Tạo JAR chứa class và hai properties rồi chạy trên một máy/JVM có locale mặc định khác. Xác nhận khi truyền `Locale.US`/`vi-VN` tường minh, nội dung vẫn đúng ngôn ngữ.

### Câu hỏi tự kiểm tra

**Câu 1.** Sự khác biệt giữa `{1}` và `{1,number,integer}` là gì?

**Đáp án:** `{1}` chèn tham số theo format mặc định dựa trên kiểu, còn `{1,number,integer}` yêu cầu format dạng số nguyên theo locale; không thay thế validation kiểu và miền dữ liệu.

**Câu 2.** Vì sao pattern tiếng Việt trong bài có hai nhánh, còn tiếng Anh có ba?

**Đáp án:** Đây là lựa chọn dịch cho từng câu. Tiếng Anh cần hình thức “no/one/many files” trong ví dụ, còn tiếng Việt dùng câu riêng cho số 0 và cách biểu diễn “n tệp” cho số từ 1 trở lên.

**Câu 3.** Vì sao `1<{1,number,integer} files` hoạt động khi count=2?

**Đáp án:** `ChoiceFormat` chọn nhánh cho các giá trị lớn hơn 1; khi nhánh chứa dấu `{...}`, `MessageFormat` xử lý nested format element với cùng arguments.

**Câu 4.** Nếu người dùng nhập tên `Eva {0}`, kết quả có bị thay `{0}` lần nữa không?

**Đáp án:** Không trong thiết kế của bài: tên người dùng nằm ở **argument**, không phải pattern. Tuy nhiên vẫn phải escape theo ngữ cảnh UI.

**Câu 5.** `MessageFormat` của Java 17 có tự phân loại `few/many/other` của mọi ngôn ngữ theo CLDR không?

**Đáp án:** Không. `ChoiceFormat` chọn theo ngưỡng số; muốn plural categories đúng ở nhiều ngôn ngữ cần engine/quy tắc phù hợp, ví dụ một thư viện ICU.

**Câu 6.** Có thể dùng một `MessageFormat` mutable dùng chung cho mọi request không?

**Đáp án:** Không nên nếu có khả năng sửa formatter hoặc gọi đồng thời thiếu kiểm soát. Tạo formatter riêng, thread confinement hoặc đồng bộ phù hợp.

## 15. Tài liệu tham khảo

- [MessageFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html): cú pháp placeholder, nested choice và quy tắc apostrophe.
- [ChoiceFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html): ngưỡng số, ký hiệu `#` và `<`, choice pattern.
- [ResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html): tìm bundle theo locale, parent/fallback.
- [PropertyResourceBundle — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PropertyResourceBundle.html): tệp properties, đọc UTF-8 và fallback charset.
- [NumberFormat — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/NumberFormat.html): định dạng số theo locale.
- [Locale — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Locale.html): locale, language tag và lựa chọn ngôn ngữ.
- [Unicode CLDR Plural Rules](https://cldr.unicode.org/index/cldr-spec/plural-rules): các loại số lượng và dữ liệu ngôn ngữ.
- [ICU MessageFormat Guide](https://unicode-org.github.io/icu/userguide/format_parse/messages/): cách biểu đạt plural/select bằng một engine khác với Java 17 Core.

**Ghi nhớ:** **Tài nguyên chứa câu được dịch, `MessageFormat` chèn tham số, `ChoiceFormat` chọn theo ngưỡng số.** Hãy kiểm tra miền số, truyền `Locale` tường minh, dịch trọn câu theo ngôn ngữ, test tất cả nhánh và phân biệt rõ `ChoiceFormat` với plural rules CLDR khi mở rộng ứng dụng đa ngôn ngữ.
