# Quy tắc dấu nháy đơn, ngoặc nhọn và escape trong mẫu Java `MessageFormat`

## 1. Vì sao mẫu `MessageFormat` dễ bị lỗi dù chuỗi nhìn “đúng”?

`java.text.MessageFormat` tạo thông điệp có tham số theo `Locale`. Ví dụ:

```java
MessageFormat format =
        new MessageFormat("Xin chào {0}!", Locale.forLanguageTag("vi-VN"));
System.out.println(format.format(new Object[] {"Lan"}));
```

Đầu ra:

```text
Xin chào Lan!
```

Ký hiệu `{0}` là **phần giữ chỗ (placeholder)** cho tham số ở vị trí 0. Nhưng `MessageFormat` không xử lý chuỗi mẫu như văn bản thông thường: dấu **nháy đơn `'`** có ý nghĩa cú pháp, ngoặc **`{` và `}`** đánh dấu thành phần định dạng, còn dấu **gạch chéo ngược `\` không phải cách escape tổng quát trong cú pháp `MessageFormat`**.

Bởi vậy, một thông điệp như `It's {0}` có thể không thay tham số như người viết mong đợi. Một ví dụ chứa ký hiệu `{0}` để giải thích tài liệu cũng có thể bị coi là tham số. Khi mẫu nằm trong mã Java hoặc tệp `.properties`, phải phân biệt **hai tầng xử lý**: cú pháp lưu chuỗi và cú pháp của `MessageFormat`.

Bài này tập trung vào quy tắc **dấu nháy đơn, ngoặc nhọn, escape và cách kiểm thử mẫu**; không nhầm nó với `String.format` hoặc cơ chế interpolation của ngôn ngữ khác.

## 2. Hình thức cơ bản của một phần định dạng

Một phần tử trong pattern có hình thức:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Ví dụ:

```text
Xin chào {0}; bạn có {1,number,integer} thông báo.
```

- `{0}` là tham số thứ nhất, `{1}` là tham số thứ hai (chỉ số bắt đầu từ **0**).
- `number`, `date`, `time`, `choice` có thể mở rộng cách định dạng theo `Locale`; kiểu và style hợp lệ tùy loại.
- Dấu phẩy, dấu ngoặc nhọn trong cú pháp phần tử định dạng được parser xử lý đặc biệt.
- Nếu chỉ muốn in **chữ `{0}`**, thay vì chèn tham số, cần **quote nó như văn bản literal**.

**Cặp ngoặc nhọn không phải cú pháp thay tên biến.** `MessageFormat` chuẩn sử dụng chỉ số tham số dạng số nguyên không âm như `{0}`, không tự nhận `{username}`. Mẫu không đúng cú pháp có thể ném `IllegalArgumentException` khi tạo hoặc áp dụng pattern.

## 3. Quy tắc dấu nháy đơn: ba hành vi phải nhớ

Trong `MessageFormat`, **dấu nháy đơn đơn lẻ `'`** bắt đầu/kết thúc **một đoạn được quote**, tức đoạn ký tự được xem là văn bản thường. Bản thân dấu nháy dùng để đóng/mở đoạn **không xuất hiện** trong kết quả.

**Hai dấu nháy đơn liền nhau `''`** biểu diễn **một dấu nháy đơn thật** trong kết quả.

**Dấu nháy đơn mở nhưng không đóng** được xem như tự đóng ở cuối pattern, thường làm cho placeholder phía sau bị in nguyên văn thay vì thế chỗ.

| Pattern truyền cho `MessageFormat` | Tham số `{0}` | Kết quả | Giải thích |
| --- | --- | --- | --- |
| `Hello {0}` | `Lan` | `Hello Lan` | Placeholder thông thường |
| `It''s {0}` | `Lan` | `It's Lan` | `''` sinh một dấu `'` |
| `It's {0}` | `Lan` | `Its {0}` | Dấu `'` trước `s` mở quote đến cuối mẫu; `{0}` mất vai trò placeholder |
| `'Hello' {0}` | `Lan` | `Hello Lan` | `Hello` được quote; dấu `'` cú pháp bị bỏ |
| `''{0}''` | `Lan` | `'Lan'` | Hai cặp `''` tạo nháy đơn bao quanh **giá trị đã định dạng** |
| `'{0}'` | `Lan` | `{0}` | Cả phần `{0}` bị quote nên **không** được thay |
| `'abc {0}` | `Lan` | `abc {0}` | Quote mở không đóng, Java mặc nhiên coi nó đóng cuối mẫu |

**Phân biệt rất quan trọng:**

- `'{0}'` → in đúng **`{0}`** (không chèn dữ liệu).
- `''{0}''` → in **`'Lan'`** nếu `{0}` là `Lan` (có chèn dữ liệu, có nháy đơn thật).

Nhiều lỗi được sinh ra chỉ vì người viết thêm một cặp nháy đơn quanh placeholder và tưởng rằng chúng là ký tự trang trí. Trong `MessageFormat`, đó là **lệnh quote cú pháp**.

### Dấu nháy trong dữ liệu đầu vào khác dấu nháy trong pattern

Nếu tham số là tên `O'Brien`, truyền trực tiếp:

```java
Object[] args = {"O'Brien"};
```

Dấu nháy đơn trong **dữ liệu thay thế** không tự làm parser phân tích lại pattern. Vì vậy không được tự nhân đôi dấu nháy đơn trong tên người, địa chỉ hoặc dữ liệu đầu vào như thể chúng là mẫu `MessageFormat`. Chỉ cần escape **dấu nháy nằm trong pattern**.

## 4. In dấu ngoặc nhọn literal bằng `'{'` và `'}'`

Ngoặc nhọn `{` mở một phần tử format; `}` liên quan đến việc kết thúc phần tử. Khi cần in một dấu ngoặc như văn bản thường, hãy đặt nó trong đoạn quote bằng nháy đơn:

| Ý định | Pattern | Kết quả với `{0} = OK` |
| --- | --- | --- |
| In dấu `{` | `'{' ` | `{ ` |
| In dấu `}` | `'}'` | `}` |
| In chuỗi ký hiệu `{0}` | `'{0}'` | `{0}` |
| Bao **giá trị** trong cặp `{...}` | `'{'{0}'}'` | `{OK}` |
| Giải thích thao tác gõ ngoặc | `Gõ '{' và '}' để bao {0}` | `Gõ { và } để bao OK` |

Ở dòng đầu, khoảng trắng sau `'{'` chỉ nhằm làm ví dụ có ký tự theo sau; bản thân pattern `'{'` cho đầu ra chính xác một ký tự `{`.

Mẫu `'{'{0}'}'` là sự kết hợp của **ba đoạn**: dấu mở `{` literal, placeholder `{0}` thực, dấu đóng `}` literal. Nếu viết `'{0}'` thì toàn bộ placeholder lại trở thành văn bản literal.

**Không dùng** dấu gạch chéo ngược để “escape ngoặc” theo thói quen của regex hoặc JavaScript:

```text
\{0\}     ← không phải cú pháp escape ngoặc nhọn của MessageFormat
```

`MessageFormat` không có quy tắc “backslash làm mất ý nghĩa của ngoặc nhọn” như vậy. Dấu gạch chéo ngược trong pattern thường được xem như ký tự thường; các dấu ngoặc nhọn vẫn được parser xử lý theo quy tắc của nó.

## 5. Chương trình Java 17+ kiểm chứng mọi trường hợp cơ bản

Tạo tệp **`MessageFormatEscapingDemo.java`**:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatEscapingDemo {
    private static void show(String label, String pattern, String value) {
        MessageFormat format = new MessageFormat(pattern, Locale.ROOT);
        String result = format.format(new Object[] {value});
        System.out.println(label + ": " + result);
    }

    public static void main(String[] args) {
        show("basic", "Xin chào {0}!", "Lan");
        show("apostrophe", "It''s {0}.", "OK");
        show("literal-placeholder", "Mẫu '{0}' và giá trị {0}", "Lan");
        show("quoted-value", "Giá trị: ''{0}''.", "OK");
        show("literal-braces", "Mở '{', đóng '}', nội dung {0}.", "OK");
        show("around-value", "'{'{0}'}'", "OK");

        // Sai về ý nghĩa, nhưng vẫn là pattern có thể phân tích được:
        show("wrong-apostrophe", "It's {0}.", "OK");
        show("unclosed-quote", "Lỗi 'từ {0}", "OK");

        try {
            new MessageFormat("Sai {0", Locale.ROOT);
            System.out.println("invalid: unexpected success");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid: IllegalArgumentException");
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp bằng JDK 17+ (terminal cần hiển thị Unicode):

```bash
javac -encoding UTF-8 MessageFormatEscapingDemo.java
java -cp . MessageFormatEscapingDemo
```

Đầu ra khi terminal hiển thị đúng UTF-8:

```text
basic: Xin chào Lan!
apostrophe: It's OK.
literal-placeholder: Mẫu {0} và giá trị Lan
quoted-value: Giá trị: 'OK'.
literal-braces: Mở {, đóng }, nội dung OK.
around-value: {OK}
wrong-apostrophe: Its {0}.
unclosed-quote: Lỗi từ {0}
invalid: IllegalArgumentException
```

Hai dòng `wrong-apostrophe` và `unclosed-quote` **cố ý trình bày lỗi logic**: pattern không nhất thiết ném exception mà có thể cho chuỗi sai ý định. Vì thế phép thử “tạo `MessageFormat` không lỗi” là chưa đủ; cần so sánh kết quả thực tế, đặc biệt với các bản dịch có dấu nháy.

Cấu trúc `show(...)` dùng `Locale.ROOT` và tham số chuỗi để tránh khác biệt định dạng số/ngày theo từng locale; ví dụ này kiểm tra thuần quy tắc quote/placeholder.

## 6. Escape tồn tại ở nhiều tầng: Java source, `.properties`, `MessageFormat`

Một lỗi rất thường gặp là thấy dấu nháy hoặc ngoặc không hoạt động, rồi thêm gạch chéo ngược `\`. Nhưng trước khi sửa, phải biết **chuỗi đang được đọc từ đâu**.

### 6.1. Pattern viết trực tiếp trong mã Java

Giả sử cần hiển thị `It's Lan`:

```java
String pattern = "It''s {0}";
String output =
        new MessageFormat(pattern, Locale.ROOT)
                .format(new Object[] {"Lan"});
System.out.println(output); // It's Lan
```

Ở đây:

- Cặp `"` mở/đóng **Java string literal**.
- Hai dấu `''` được giữ nguyên trong Java string; khi `MessageFormat` phân tích, chúng sinh một dấu `'` thật.
- Dấu `{` và `}` không cần escape trong Java string literal.
- Nháy kép `"` nếu nằm trong chính Java string phải viết `\"` theo quy tắc Java; nháy kép **không** phải dấu quote đặc biệt của `MessageFormat`.

Muốn chứa dấu gạch chéo ngược **thật** trong Java string, dùng `\\` ở **tầng Java source**. Nhưng backslash do Java tạo ra không tự làm mất ý nghĩa ngoặc trong `MessageFormat`.

Ví dụ, hai chuỗi sau không tương đương về chức năng:

```java
String literalBracePattern = "'{'{0}'}'"; // MessageFormat quote
String backslashPattern = "\\{0}";      // Java escape để chứa \ thật
```

Với tham số `OK`, mẫu thứ nhất trả `{OK}`, còn mẫu thứ hai trả `\OK`. Vì ở mẫu thứ hai, `{0}` vẫn là placeholder và dấu `\` chỉ được in nguyên văn.

### 6.2. Pattern đọc từ tệp `.properties`

Giả sử tệp **`messages.properties`** chứa:

```properties
welcome=Xin chào {0}!
notice=It''s {0}.
quoted=Giá trị: ''{0}''.
braced=Nhập '{' và '}' để bao {0}.
literal=Mẫu '{0}' và giá trị {0}.
```

Khi được đọc qua `ResourceBundle` trên Java 17+, các dòng này trở thành **chuỗi pattern của `MessageFormat`**. Trong file properties, cặp nháy `''` cũng cần được giữ vì đây là yêu cầu của **`MessageFormat`**, không phải của parser properties.

Ba điều cần nhớ về `.properties`:

1. Trong cú pháp properties, dấu nháy đơn `'` **không phải ký tự escape mặc định**. Dòng `notice=It's {0}.` vẫn có thể đọc thành đúng chuỗi `It's {0}.`, nhưng **`MessageFormat` sẽ xử lý sai nghĩa**. Phải viết `It''s {0}.` cho nội dung muốn hiển thị `It's ...`.
2. Trong file properties, dấu gạch chéo ngược **có** chức năng escape riêng, ví dụ `\n` có thể được chuyển thành ký tự xuống dòng và `\\` biểu diễn một dấu `\` thật. Các quy tắc này xảy ra **trước khi** chuỗi được chuyển cho `MessageFormat`.
3. Viết `\'` trong file properties **không phải cách thay thế an toàn** cho `''`. Sau khi parser properties xử lý, nháy đơn vẫn có thể còn trong pattern và tiếp tục mang ý nghĩa đặc biệt đối với `MessageFormat`.

Đối với Java 9+ (bao gồm Java 17), `PropertyResourceBundle` mặc định hỗ trợ UTF-8 theo đặc tả hiện đại, với cơ chế tương thích encoding cũ. Hãy lưu resource bằng UTF-8 nhất quán và kiểm tra pipeline build/runtime; quy tắc `MessageFormat` về nháy đơn **không thay đổi** chỉ vì file sử dụng UTF-8.

### 6.3. Mẫu đi qua nhiều định dạng hơn

Nếu pattern được đưa vào JSON, YAML, SQL, HTML template hoặc hệ thống dịch thuật, có thể tồn tại **nhiều lớp escape**. Ví dụ nháy kép `"` và backslash `\` trong JSON có quy tắc riêng; chuỗi sau khi giải mã mới được `MessageFormat` phân tích. Đừng đoán số lần cần nhân đôi ký tự ở từng lớp; hãy kiểm tra **chuỗi Java thực nhận được** ngay trước `new MessageFormat(pattern, locale)`.

Nên mô tả từng tầng rõ ràng:

```text
Tệp nguồn / chuỗi Java / JSON / properties
        ↓ (quy tắc giải mã riêng)
String pattern thực tế trong JVM
        ↓ (parser MessageFormat)
FormatElement + văn bản literal
        ↓ (format với Object[])
Thông điệp đầu ra
```

Đây là lý do escape của **Java source** không đồng nhất với escape của **MessageFormat** và cũng không đồng nhất với escape của **properties**.

## 7. Ví dụ hoàn chỉnh: `ResourceBundle` kết hợp `MessageFormat`

Một dự án bản địa hóa thường đặt pattern trong bundle. Ví dụ này sử dụng bundle gốc `messages.properties` ở classpath root để mọi kết quả có thể kiểm tra độc lập với ngôn ngữ mặc định JVM.

Tạo đúng hai tệp:

```text
workspace/
├── BundleMessageFormatDemo.java
└── messages.properties
```

**`messages.properties`** (lưu UTF-8):

```properties
welcome=Xin chào {0}!
notice=It''s {0}.
quoted=Giá trị: ''{0}''.
braced=Nhập '{' và '}' để bao {0}.
literal=Mẫu '{0}' và giá trị {0}.
```

**`BundleMessageFormatDemo.java`:**

```java
import java.text.MessageFormat;
import java.util.Locale;
import java.util.ResourceBundle;

public class BundleMessageFormatDemo {
    public static void main(String[] args) {
        ResourceBundle bundle =
                ResourceBundle.getBundle("messages", Locale.ROOT);
        Locale outputLocale = Locale.forLanguageTag("vi-VN");

        for (String key : new String[] {
                "welcome", "notice", "quoted", "braced", "literal"
        }) {
            String pattern = bundle.getString(key);
            MessageFormat formatter =
                    new MessageFormat(pattern, outputLocale);
            System.out.println(key + ": " +
                    formatter.format(new Object[] {"Lan"}));
        }
    }
}
```

Từ thư mục `workspace`, chạy:

```bash
javac -encoding UTF-8 BundleMessageFormatDemo.java
java -cp . BundleMessageFormatDemo
```

Kết quả logic của ví dụ (terminal hiển thị đúng Unicode):

```text
welcome: Xin chào Lan!
notice: It's Lan.
quoted: Giá trị: 'Lan'.
braced: Nhập { và } để bao Lan.
literal: Mẫu {0} và giá trị Lan.
```

Ví dụ cho thấy một pattern có thể được dịch dưới dạng **văn bản có placeholder** và nạp từ bundle mà vẫn bảo toàn cách quote. Khi tạo bundle cho một locale khác, phải kiểm tra pattern mới có số placeholder đúng và các dấu `'`, `{`, `}` được diễn giải đúng, không chỉ so sánh văn bản trước/sau.

**Lưu ý:** `ResourceBundle` tự có cơ chế fallback tài nguyên; `MessageFormat` chỉ nhận **chuỗi giá trị** từ `bundle.getString(key)` rồi phân tích pattern. Một bundle được nạp thành công không chứng minh mọi chuỗi trong đó có cú pháp `MessageFormat` hợp lệ.

## 8. Các lỗi tinh vi và cách phòng tránh

### 8.1. Nhầm dấu nháy đơn trong ngôn ngữ tự nhiên với cú pháp quote

Tiếng Anh có nhiều dạng `don't`, `it's`, `user's`, `you're`; tiếng Pháp thường có `l'utilisateur`, `d'accord`. Nếu đưa trực tiếp các câu này vào pattern `MessageFormat`, dấu nháy đơn có thể **nuốt placeholder phía sau**.

Ví dụ:

```text
Sai:   It's {0}.     → Its {0}.
Đúng:  It''s {0}.    → It's Lan.   (với {0} = Lan)
```

Đây có thể là **lỗi im lặng**, không xuất hiện exception. Kiểm thử nội dung thực tế là bắt buộc.

### 8.2. Quote toàn bộ placeholder khi chỉ muốn in dấu nháy

`'{0}'` hiển thị ký hiệu `{0}` thay vì giá trị. Nếu muốn tên người trong nháy đơn, dùng `''{0}''`. Nếu muốn in một placeholder ở tài liệu trợ giúp, `'{0}'` lại là cách đúng.

### 8.3. Dùng backslash để escape nháy đơn hoặc ngoặc

Dấu `\` có thể mang ý nghĩa với Java source và properties, nhưng **không phải ký tự escape cơ bản của `MessageFormat`**. Dùng `''` cho nháy đơn literal, `'{'`, `'}'` cho dấu ngoặc literal.

### 8.4. Cố sửa pattern malformed bằng cách bắt exception rồi tiếp tục thay thế

Pattern như `Sai {0` là không hợp lệ và có thể ném `IllegalArgumentException`. Hãy coi lỗi cú pháp trong bundle là **lỗi tài nguyên/dịch thuật cần sửa**, không lặng lẽ dùng string replace như `pattern.replace("{0}", value)`, vì phép thay thế đó bỏ qua locale, kiểu format, parent/bundle và khả năng escape.

### 8.5. Nhầm dữ liệu tham số với pattern

`MessageFormat` phân tích **pattern**, không tự parse lại dữ liệu truyền vào `format` như một pattern khác trong trường hợp thay thế thông thường. Nếu dữ liệu chứa `O'Brien` hay `{0}`, không cần tự quote theo cú pháp pattern. Ngược lại, không nên dùng trực tiếp **văn bản không tin cậy** làm pattern nếu chưa kiểm soát, vì nó có thể thay đổi ý nghĩa placeholder hoặc gây lỗi parser.

### 8.6. Pattern phức tạp và subformat

Với cú pháp `{0,number,...}`, `{0,date,...}` hoặc `{0,choice,...}`, phần **format style** có cú pháp riêng (chẳng hạn `DecimalFormat`, `SimpleDateFormat`, `ChoiceFormat`). `ChoiceFormat` còn có thể chứa các mẫu con và ký tự `|`, `#`, `<` có nghĩa đặc biệt.

Vì vậy, khi pattern có **subformat lồng nhau**, không đủ để áp dụng máy móc một bảng quote ở tầng ngoài: phải hiểu **cả parser của subformat**. Kiểm thử cả nhánh có chứa placeholder và nhánh không chứa, nhất là khi dịch thay đổi dấu nháy hoặc dấu ngoặc. Nếu cần quy tắc plural/gender phức tạp, cân nhắc hệ thống bản địa hóa đáp ứng đầy đủ yêu cầu của sản phẩm thay vì nhồi chuỗi điều kiện khó bảo trì.

### 8.7. Dấu nháy kép khác dấu nháy đơn

Trong `MessageFormat`, `"` bình thường là ký tự văn bản, **không** thay vai trò của `'` trong pattern. Nhưng nếu pattern được viết trong **Java string literal**, dấu `"` cần escape theo cú pháp Java (`\"`). Nếu ghi trong file properties, cách xử lý dấu nháy kép lại khác Java source. Luôn xác định đang nói tới tầng nào.

### 8.8. Không dựa vào `toPattern()` như phép đối chiếu nguyên văn

`MessageFormat.toPattern()` trả một **biểu diễn pattern** của đối tượng; nó có thể chuẩn hóa cách quote. Nó không nhất thiết là chuỗi đầu vào giống hệt từng ký tự. Dùng `toPattern()` để chẩn đoán, nhưng tiêu chí cuối vẫn là **đầu ra được format và hành vi thật của placeholder**.

## 9. Cách kiểm thử pattern trong hệ thống dịch thuật

Một quy trình kiểm tra hiệu quả khi có nhiều locale:

1. **Xác định pattern gốc:** lấy đúng giá trị từ `ResourceBundle`, phân biệt với khóa và với chuỗi đã thay tham số.
2. **Kiểm tra cấu trúc:** tạo `new MessageFormat(pattern, locale)` để phát hiện nhiều lỗi cú pháp ngoặc/format ngay từ đầu.
3. **Kiểm tra nội dung đã format:** gọi `format` với tham số đại diện, so sánh kết quả mong đợi; đừng chỉ xem parser có chấp nhận không.
4. **Kiểm tra dấu nháy trong văn bản:** thử các từ có apostrophe thật (`don't`, `l'utilisateur`) và xác nhận các placeholder đứng sau vẫn được thay thế.
5. **Kiểm tra ngoặc literal:** thử mẫu cần hiển thị `{`, `}`, `{0}` như tài liệu hoặc dấu bao giá trị.
6. **Kiểm tra tham số là dữ liệu đặc biệt:** đưa giá trị như `O'Brien`, `{0}` vào tham số; đảm bảo chúng không bị phân tích nhầm thành cú pháp pattern.
7. **Kiểm tra mỗi bản dịch:** bản tiếng Việt hợp lệ không bảo đảm bản tiếng Pháp/Anh hợp lệ; người dịch có thể thêm một dấu nháy đơn làm thay đổi cú pháp.
8. **Kiểm tra môi trường lưu trữ:** UTF-8, quy tắc escape của properties/JSON, cache bundle và pipeline xây dựng ứng dụng.
9. **Kiểm tra nhánh subformat:** nếu có `choice`, ngày/giờ hoặc số, thử các giá trị buộc chạy tất cả nhánh quan trọng. Định dạng phụ thuộc locale/JDK có thể khác nhau, nên snapshot cần gắn với runtime được kiểm thử.

Có thể viết unit test với vài pattern then chốt:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageFormatAssertions {
    private static String apply(String pattern, Object value) {
        return new MessageFormat(pattern, Locale.ROOT)
                .format(new Object[] {value});
    }

    private static void require(String expected, String actual) {
        if (!expected.equals(actual)) {
            throw new AssertionError(
                    "Expected: " + expected + "; actual: " + actual);
        }
    }

    public static void main(String[] args) {
        require("It's Lan", apply("It''s {0}", "Lan"));
        require("{0}", apply("'{0}'", "Lan"));
        require("'Lan'", apply("''{0}''", "Lan"));
        require("{Lan}", apply("'{'{0}'}'", "Lan"));
        require("O'Brien", apply("{0}", "O'Brien"));
        System.out.println("5 checks passed");
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 MessageFormatAssertions.java
java -cp . MessageFormatAssertions
```

Khi các điều kiện đúng:

```text
5 checks passed
```

Ví dụ này cố ý dùng assertion tự viết thay vì lệnh Java `assert` để kiểm tra luôn hoạt động, kể cả khi không chạy với `-ea`.

## 10. Bảng tra nhanh

| Muốn hiển thị | Pattern `MessageFormat` | Ghi nhớ |
| --- | --- | --- |
| `Lan` từ tham số 0 | `{0}` | Thay giá trị bình thường |
| `It's Lan` | `It''s {0}` | Hai nháy đơn trong mẫu sinh một nháy thật |
| `'Lan'` | `''{0}''` | Hai cặp nháy sinh dấu nháy bao quanh giá trị |
| `{0}` nguyên văn | `'{0}'` | Quote cả placeholder để in ký hiệu |
| `{` | `'{'` | Quote dấu ngoặc mở |
| `}` | `'}'` | Quote dấu ngoặc đóng |
| `{Lan}` | `'{'{0}'}'` | Quote hai ngoặc, không quote placeholder |
| `O'Brien` khi đó là dữ liệu tham số | `{0}` với giá trị `O'Brien` | Không escape lại dữ liệu như pattern |

**Ghi nhớ:** trong `MessageFormat`, dấu nháy đơn là **toán tử quote**; `''` mới là cách in dấu nháy đơn thật. Ngoặc nhọn được dành cho placeholder, nên muốn in chúng như văn bản thì dùng `'{'` và `'}'`. Backslash không thay thế hai quy tắc này. Hãy kiểm tra pattern **sau khi** Java/properties giải mã và kiểm thử **kết quả format thực sự**, vì nhiều lỗi dấu nháy không gây exception nhưng khiến placeholder không được thay thế.
