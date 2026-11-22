# Kiểm thử dấu nháy đơn, ngoặc nhọn và mẫu MessageFormat trong Java

## 1. Vì sao bài kiểm thử này quan trọng?

`java.text.MessageFormat` giúp chèn dữ liệu vào câu đã được bản địa hóa. Thay vì ghép chuỗi thủ công, một mẫu như:

```text
Xin chào, {0}! Bạn có {1,number,integer} thông báo.
```

cho phép người dịch thay đổi vị trí các tham số khi cần. Nhưng `MessageFormat` **không xử lý pattern như chuỗi văn bản thường**. Hai loại ký tự có chức năng cú pháp đặc biệt:

- Dấu nháy đơn thẳng `'` (U+0027) bắt đầu/kết thúc vùng văn bản literal (*quoted text*).
- Dấu ngoặc nhọn mở `{` và đóng `}` đánh dấu phần tử định dạng (*format element*), chẳng hạn `{0}` hoặc `{1,number,integer}`.

Vì vậy, câu bản địa hóa chứa `You're`, `It's`, ví dụ JSON `{"name": "{0}"}` hay muốn hiển thị nguyên văn `{0}` rất dễ bị xử lý sai. Đặc biệt nguy hiểm: **dấu nháy đơn mở mà không đóng không nhất thiết tạo exception**. Parser có thể tự xem cuối pattern là điểm kết thúc vùng quote, rồi **ngừng thay thế placeholder** mà không báo lỗi.

Bài học thuộc nhóm **kiểm thử và lỗi** của Java localization, tập trung vào:

1. Hiểu cú pháp và phạm vi quote của `MessageFormat`.
2. Viết đúng dấu nháy đơn, ngoặc nhọn literal và placeholder.
3. Kiểm chứng output của pattern đơn, pattern number, choice và pattern lồng nhau.
4. Phát hiện các mẫu lỗi cú pháp, những mẫu hợp lệ nhưng cho **sai ý nghĩa**, các tham số thiếu/sai kiểu.
5. Kiểm tra pattern lấy từ `ResourceBundle`, file `.properties` và dữ liệu dịch.
6. Tổ chức bộ test chạy được trên Java 17+, tránh lỗi khi thêm hoặc sửa bản dịch.

Điểm cần ghi nhớ: **một pattern không ném exception chưa chắc định dạng đúng**. Phải kiểm thử **đầu ra mong muốn** với những dữ liệu đại diện.

## 2. Cú pháp cơ bản của MessageFormat

Một format element có dạng tổng quát:

```text
{argumentIndex}
{argumentIndex,formatType}
{argumentIndex,formatType,formatStyle}
```

Ví dụ:

```text
Hello, {0}!
Amount: {1,number,#,##0.00}
Date: {2,date,short}
{3,choice,0#none|1#one|1<{3,number,integer} items}
```

Các thành phần:

| Thành phần | Ý nghĩa |
|---|---|
| `argumentIndex` | Chỉ số đối số không âm trong mảng `Object[]`, bắt đầu từ 0 |
| `formatType` | Ví dụ `number`, `date`, `time`, `choice` |
| `formatStyle` | Ví dụ `integer`, `short`, pattern `DecimalFormat`, hoặc quy tắc `ChoiceFormat` |
| Văn bản ngoài format element | Chuỗi literal theo quy tắc quote của `MessageFormat` |
| `'` | Điều khiển việc quote literal trong pattern; cần `''` để hiển thị một dấu nháy đơn thẳng |
| `{` | Mở format element, trừ khi đã được quote |
| `}` | Đóng format element, hoặc là literal theo ngữ cảnh và cách parser chấp nhận |

Một ví dụ độc lập về gọi API:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class HelloMessage {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "Hello, {0}! You have {1,number,integer} messages.",
                Locale.US);

        System.out.println(
                message.format(new Object[]{"Mai", 2}));
    }
}
```

Chạy:

```bash
javac HelloMessage.java
java HelloMessage
```

Output:

```text
Hello, Mai! You have 2 messages.
```

`{0}` và `{1,number,integer}` là **cú pháp của pattern**, không phải nội dung sẽ luôn được in nguyên văn. Nếu muốn in chính chuỗi `{0}`, cần quote nó đúng cách.

`MessageFormat` của `java.text` là API khác `String.format` (cú pháp `%s`) và khác `java.time.format.DateTimeFormatter` (các chữ cái pattern ngày). Không áp dụng quy tắc escape của một API lên API khác.

## 3. Luật dấu nháy đơn: ' và '' không giống nhau

Trong `MessageFormat`, ký tự nháy đơn **thẳng ASCII** `'` có hai vai trò:

- Một dấu nháy đơn bắt đầu hoặc kết thúc vùng literal đã quote.
- **Hai dấu nháy đơn liên tiếp `''`** biểu diễn **một** dấu nháy đơn literal trong output.

Ví dụ:

| Pattern | Đối số | Output | Diễn giải |
|---|---|---|---|
| `You''re invited, {0}.` | `Mai` | `You're invited, Mai.` | Hai dấu nháy đơn cho ra một dấu |
| `You're invited, {0}.` | `Mai` | `Youre invited, {0}.` | Dấu nháy đơn không đóng khiến phần sau là literal |
| `'{0}'` | `Mai` | `{0}` | Placeholder được quote nên không thay thế |
| `''{0}''` | `Mai` | `'Mai'` | Hai dấu nháy ở hai bên, placeholder vẫn hoạt động |
| `It's {0}` | `Mai` | `Its {0}` | Pattern hợp lệ nhưng cho kết quả sai |
| `A '' B` | Không cần | `A ' B` | In một dấu nháy đơn |

**Không dùng dấu `\` như cách thay thế cho `''` trong `MessageFormat`.** Backslash là ký tự escape của nhiều ngôn ngữ/định dạng khác, nhưng không phải cơ chế quote trực tiếp cho dấu nháy đơn trong pattern của `MessageFormat`.

Ví dụ viết:

```text
You're invited, {0}.
```

trông đúng trong file dịch nhưng sai khi đưa nguyên pattern vào `MessageFormat`. Chuyển thành:

```text
You''re invited, {0}.
```

mới giúp giữ dấu nháy đơn và thay `{0}`. Dấu nháy đơn trong bản dịch phải được kiểm thử vì chúng có thể xuất hiện tự nhiên trong tiếng Anh, Pháp và nhiều ngôn ngữ.

### Dấu nháy cong khác dấu nháy thẳng

Ký tự `’` (U+2019, *right single quotation mark*) là một ký tự Unicode khác `'` (U+0027). Nó **không phải ký tự quote cú pháp** của `MessageFormat`.

Do đó, một bản dịch dùng dấu nháy cong như `It’s {0}` không kích hoạt quy tắc quote của ASCII apostrophe theo cách `It's {0}` làm. Nhưng **không nên dựa vào việc đổi kiểu dấu câu để tránh lỗi lập trình**: quy tắc typography, accessibility và copy/paste thuộc chính sách nội dung. Đối với ASCII apostrophe, vẫn phải escape thành `''` trong pattern.

## 4. Dấu nháy đơn chưa đóng có thể bị tự đóng ở cuối pattern

Một rủi ro lớn với `MessageFormat` là pattern có quote không đóng có thể **không ném `IllegalArgumentException`**. Parser có thể xử lý như thể đã có dấu nháy đóng ở cuối mẫu.

Ví dụ:

```java
MessageFormat message =
        new MessageFormat("It's {0}", Locale.US);

System.out.println(
        message.format(new Object[]{"Mai"}));
```

Đoạn này (cần import `MessageFormat`, `Locale`) in:

```text
Its {0}
```

Giải thích:

1. Phần `It` là văn bản thường.
2. Dấu `'` trước `s` mở vùng literal, **không được in ra**.
3. Các ký tự `s {0}` được coi là literal cho tới cuối pattern.
4. Placeholder `{0}` không còn được thay bằng `Mai`.
5. Pattern được chấp nhận, không phải lỗi cú pháp bị exception chặn.

Một trường hợp khác:

```text
Pattern: A ' B {0}
Output:  A  B {0}
```

Không thể chỉ chạy:

```java
new MessageFormat(pattern, locale);
```

rồi kết luận bản dịch đạt chất lượng. **Test output hoặc kiểm tra cấu trúc placeholder** là cần thiết để phát hiện loại lỗi im lặng này.

Cách sửa pattern chính xác:

```text
It''s {0}
```

Khi đó `{0}` lại được thay bởi đối số.

## 5. Nguyên tắc ngoặc nhọn và placeholder literal

Trong pattern, dấu `{` thường được hiểu là **mở một format element**. Nếu chuỗi chứa ví dụ kỹ thuật, JSON, template hoặc biểu thức như `{id}` mà không phải placeholder của MessageFormat, parser có thể cố phân tích và báo lỗi.

### Muốn in nguyên văn {0}

Dùng:

```text
'{0}'
```

Kết quả:

```text
{0}
```

Placeholder được đặt **bên trong vùng quote**, nên nó không được thay thế.

### Muốn bọc giá trị đối số bằng ngoặc nhọn

Dùng:

```text
'{'{0}'}'
```

Với đối số `Mai`, output:

```text
{Mai}
```

Ba phần tách biệt:

- `'{'`: literal ngoặc nhọn mở.
- `{0}`: placeholder thực sự.
- `'}'`: literal ngoặc nhọn đóng.

Đây là cách đáng tin cậy để hiển thị một đối số bên trong một cặp braces mà không biến phần ngoặc thành cú pháp format element.

### Muốn in dấu nháy đơn xung quanh giá trị

Dùng:

```text
''{0}''
```

Với `Mai`, output:

```text
'Mai'
```

Đừng dùng `'{0}'` nếu mục đích là **thay thế giá trị rồi thêm nháy đơn**; mẫu đó sẽ in literal `{0}`.

### Dấu ngoặc đóng đứng một mình

Trong triển khai `MessageFormat` được kiểm chứng, pattern `Bad }` **không ném lỗi** và in `Bad }`. Không được suy ra **mọi dấu ngoặc mở/đóng đều được parser kiểm tra cân bằng như nhau**. Muốn có hành vi rõ ràng trong bản dịch và ví dụ văn bản kỹ thuật, dùng quote tường minh `'}'` khi có thể.

## 6. Ví dụ Java 17+ hoàn chỉnh: các ca quote quan trọng

Lưu file `MessageQuoteDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessageQuoteDemo {
    public static void main(String[] args) {
        Object[] values = {"Mai", 2, 1234.5};

        String[] patterns = {
                "You''re invited, {0}.",
                "Literal '{0}' plus {0}",
                "''{0}''",
                "'{'{0}'}'",
                "JSON: '{'\"name\": \"{0}\"'}'",
                "It's {0}"
        };

        for (String pattern : patterns) {
            MessageFormat message =
                    new MessageFormat(pattern, Locale.US);

            System.out.println(message.format(values));
        }
    }
}
```

Biên dịch/chạy:

```bash
javac MessageQuoteDemo.java
java MessageQuoteDemo
```

Kết quả đã kiểm chứng bằng JDK:

```text
You're invited, Mai.
Literal {0} plus Mai
'Mai'
{Mai}
JSON: {"name": "Mai"}
Its {0}
```

Hai dòng cuối đặc biệt đáng chú ý:

- Ví dụ JSON sử dụng `'{'` và `'}'` cho cặp braces cố định, nhưng vẫn giữ `{0}` là placeholder.
- Dòng `Its {0}` là **kết quả sai có chủ đích** để minh họa lỗi nháy đơn không đóng. Bài kiểm thử sản phẩm phải xem đây là **FAIL** nếu kỳ vọng `It's Mai`.

Sử dụng escape `\"` trong **Java string literal** ở ví dụ JSON là để biểu diễn ký tự dấu nháy kép `"` trong mã Java. Đây là tầng cú pháp **Java source**, hoàn toàn khác quy tắc dấu nháy đơn của `MessageFormat`.

## 7. Hai tầng cú pháp: Java string literal và MessageFormat pattern

Khi pattern nằm trong Java source, phải phân biệt:

**Tầng A — Java compiler:** giải mã ký tự đặc biệt của Java string literal, ví dụ `\"` hoặc `\\`.

**Tầng B — MessageFormat:** nhận `String` sau khi Java compiler xử lý, rồi phân tích dấu nháy đơn `'`, dấu nháy kép đơn `''`, braces và format elements.

Ví dụ:

```java
String pattern = "JSON: '{'\"name\": \"{0}\"'}'";
```

Sau khi Java giải mã chuỗi, MessageFormat thấy:

```text
JSON: '{'"name": "{0}"'}'
```

Sau khi MessageFormat xử lý với đối số `Mai`, kết quả:

```text
JSON: {"name": "Mai"}
```

**Không đếm số backslash trong Java source như thể đó là một phần của quy tắc quote của MessageFormat.**

Nếu pattern đến từ file `.properties`, nó không đi qua Java source-string parser như dòng `"..."`. Nhưng `.properties` có **quy tắc escape riêng**, chẳng hạn backslash ở đầu continuation line hoặc `\uXXXX`; sau khi tải file, nội dung pattern mới được phân tích bởi MessageFormat.

Nếu pattern đến từ JSON API, nó lại đi qua JSON string escape. Vì vậy, cùng một pattern ở nhiều định dạng chứa có thể phải viết **khác ký tự escape ở tầng lưu trữ**, trong khi quy tắc MessageFormat cuối cùng không đổi.

## 8. JSON và văn bản chứa cặp ngoặc nhọn

Một bài tập phổ biến là hiển thị:

```text
JSON: {"name": "Mai"}
```

Pattern rõ nghĩa là:

```text
JSON: '{'"name": "{0}"'}'
```

Trong Java source, phải escape dấu nháy kép nếu chuỗi được viết trong `"..."`:

```java
String pattern = "JSON: '{'\"name\": \"{0}\"'}'";
String result = new MessageFormat(
        pattern, Locale.US).format(new Object[]{"Mai"});
```

Kết quả đã kiểm chứng:

```text
JSON: {"name": "Mai"}
```

Nếu toàn bộ nội dung JSON đến từ đối số đã được chuẩn bị:

```java
new MessageFormat("Payload: {0}", Locale.US)
        .format(new Object[]{"{\"name\":\"Mai\"}"});
```

đối số `{"name":"Mai"}` được chèn như **dữ liệu đối số**, không được tự động phân tích như cú pháp MessageFormat ở bước thay thế thông thường.

Tuy nhiên, **chèn string vào JSON qua MessageFormat không bảo đảm JSON hợp lệ**: nếu giá trị chứa dấu nháy kép, backslash, ký tự xuống dòng hoặc nội dung đặc biệt, cần JSON serializer đúng chuẩn. `MessageFormat` không phải JSON encoder và không phải công cụ tạo dữ liệu máy-máy an toàn.

### Literal brace và phần mở không hợp lệ

Hai pattern không tương đương:

```text
User: '{0}'        -> In ra ký tự {0}
User: {0}          -> Chèn giá trị argument 0
```

Pattern `Bad {0` có dấu ngoặc mở không đóng, nên không phải format element hợp lệ. Pattern `Bad {{0}}` có ngoặc mở lồng sai ở vị trí chỉ số argument, cũng bị từ chối trong ví dụ JDK.

Không dùng mẹo “thêm một dấu `{` nữa” như cách escape ngoặc nhọn của một số template engine. **`{{0}}` không phải ký pháp escape braces của MessageFormat**.

## 9. Các pattern lỗi và hành vi cần kiểm thử

Một số lỗi được phát hiện ngay khi dựng `MessageFormat`, thường qua `IllegalArgumentException`:

| Pattern | Kết quả |
|---|---|
| `Bad {0` | `IllegalArgumentException`: phần tử chưa được đóng |
| `Bad {abc}` | `IllegalArgumentException`: chỉ số đối số không hợp lệ |
| `Bad {0,unknown}` | `IllegalArgumentException`: loại formatter không hỗ trợ |
| `Bad {{0}}` | `IllegalArgumentException`: dấu ngoặc mở lồng sai |
| `Bad {0,number,#,##0.00` | `IllegalArgumentException`: thiếu dấu đóng format element |

Những trường hợp **không nhất thiết là lỗi**:

| Pattern | Hành vi đã kiểm chứng |
|---|---|
| `Bad }` | In nguyên `Bad }` |
| `It's {0}` | In `Its {0}` nếu argument là `Mai` |
| `X '{0}` | In `X {0}`; quote kéo tới cuối mẫu |
| `'{0}'` | In `{0}`, đúng nếu chủ đích là literal |
| `''{0}''` | In một nháy đơn, giá trị, rồi một nháy đơn |

Lưu ý: **không phải mọi lỗi logic đều được API ném exception**. Tính đúng phụ thuộc kỳ vọng của thông điệp, không chỉ câu lệnh `new MessageFormat(pattern, locale)` thành công.

### Chỉ số argument và dữ liệu thiếu

Pattern `Hi {2}, {0}.` với mảng chỉ có một argument (index 0) có thể in:

```text
Hi {2}, Mai.
```

Placeholder không có dữ liệu có thể **còn nguyên dạng** trong output thay vì ném lỗi bắt buộc. Vì vậy, khi các bản dịch đổi vị trí tham số, nên kiểm tra tập indices và số lượng đối số thực sự được truyền.

Pattern `{0,number}` đòi đối số có kiểu phù hợp với formatter số. Truyền một string như `oops` có thể gây `IllegalArgumentException` khi format. **Dữ liệu null, thiếu và sai kiểu** phải nằm trong ma trận kiểm thử, không chỉ pattern quotes.

## 10. Java 17+ chạy được: kiểm tra cú pháp pattern xấu

Lưu `InvalidMessagePatternDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class InvalidMessagePatternDemo {
    public static void main(String[] args) {
        String[] invalid = {
                "Bad {0",
                "Bad {abc}",
                "Bad {0,unknown}",
                "Bad {{0}}"
        };

        for (String pattern : invalid) {
            try {
                new MessageFormat(pattern, Locale.US);
                System.out.println("ACCEPTED");
            } catch (IllegalArgumentException exception) {
                System.out.println("IllegalArgumentException");
            }
        }

        MessageFormat closing =
                new MessageFormat("Bad }", Locale.US);

        MessageFormat unterminatedQuote =
                new MessageFormat("It's {0}", Locale.US);

        System.out.println(
                closing.format(new Object[0]));
        System.out.println(
                unterminatedQuote.format(new Object[]{"Mai"}));
    }
}
```

Chạy:

```bash
javac InvalidMessagePatternDemo.java
java InvalidMessagePatternDemo
```

Kết quả:

```text
IllegalArgumentException
IllegalArgumentException
IllegalArgumentException
IllegalArgumentException
Bad }
Its {0}
```

Ý nghĩa: bốn pattern đầu bị chặn trong bước parse pattern, còn hai pattern sau được chấp nhận nhưng phải **đánh giá kết quả và ý nghĩa**. Không nên giữ pattern `It's {0}` trong bản dịch với kỳ vọng thay tên người dùng.

Trong ứng dụng, log lỗi có thể ghi message key và locale để xác định bản dịch hỏng; nếu pattern chứa dữ liệu nhạy cảm hoặc user input, tránh ghi nguyên văn không cần thiết.

## 11. Mẫu number và trích dẫn trong pattern lồng

Format element có thể chứa **mẫu định dạng con**, ví dụ:

```text
Amount: {0,number,#,##0.00}
```

Với `Locale.US` và giá trị `1234.5`, output:

```text
Amount: 1,234.50
```

Quy tắc định dạng số bên trong `{0,number,...}` có thể liên quan đến `DecimalFormat`. Khi dùng style tuỳ chỉnh, phải phân biệt:

1. Dấu nháy đơn ở tầng **MessageFormat**.
2. Dấu nháy đơn của **subformat** như `DecimalFormat`.
3. Các dấu ngoặc nhọn thuộc **MessageFormat** hoặc xuất hiện trong text literal.

Ví dụ được kiểm chứng với JDK:

```text
Pattern: {0,number,#,##0.00' kg'}
Output:  1,234.50 kg
```

Kết quả thể hiện số có hai chữ số thập phân và suffix `kg`. Ở đây phần pattern con được chuyển tới formatter số theo quy tắc của MessageFormat. Đừng tự thêm nhiều dấu nháy đơn ở mọi tầng “cho chắc”: nhân đôi không đúng chỗ có thể làm output xuất hiện nháy đơn thừa.

Ví dụ:

```text
Pattern: {0,number,#,##0.00'' kg''}
Output:  1,234.50' kg'
```

Đây là một khác biệt **có thể đo bằng test**, không phải suy luận từ số lượng nháy đơn bằng mắt.

Nếu làm sản phẩm thực, hãy ưu tiên pattern đơn giản và tránh nhúng cú pháp phức tạp khi có thể. Trong các trường hợp nhiều tầng format hoặc chính sách locale phức tạp, có thể định dạng value riêng bằng formatter phù hợp, rồi truyền string hoàn chỉnh vào MessageFormat. Nhưng phải kiểm soát rằng bản dịch vẫn được phép đảo vị trí các đối số.

## 12. ChoiceFormat và MessageFormat lồng nhau

`ChoiceFormat` được hỗ trợ qua style `choice` của MessageFormat. Ví dụ:

```text
{0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

Với các đối số 0, 1, 2, 5:

```text
0 -> no files
1 -> one file
2 -> 2 files
5 -> 5 files
```

Cú pháp:

- `0#no files` áp dụng từ ngưỡng 0.
- `1#one file` áp dụng từ ngưỡng 1.
- `1<...` diễn đạt nhánh dành cho giá trị lớn hơn 1.
- Trong nhánh cuối, `{0,number,integer}` là một format element **lồng nhau**.

### Chương trình Java 17+ độc lập

Lưu `ChoiceMessageDemo.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class ChoiceMessageDemo {
    public static void main(String[] args) {
        MessageFormat message = new MessageFormat(
                "{0,choice,0#no files|1#one file|" +
                "1<{0,number,integer} files}",
                Locale.US);

        for (int n : new int[]{0, 1, 2, 5}) {
            System.out.println(
                    n + " -> " + message.format(new Object[]{n}));
        }
    }
}
```

Chạy:

```bash
javac ChoiceMessageDemo.java
java ChoiceMessageDemo
```

Output:

```text
0 -> no files
1 -> one file
2 -> 2 files
5 -> 5 files
```

### Lưu ý cực quan trọng về quote khi lồng pattern

Khi một nhánh choice chứa các placeholder hoặc văn bản có dấu nháy đơn, quá trình format có thể phải diễn giải pattern ở **nhiều tầng**. Số dấu nháy đơn cần viết có thể khác so với một pattern phẳng, bởi quote có thể được xử lý khi phân tích pattern ngoài và khi xử lý thông điệp từ nhánh choice.

Vì thế:

- **Không đoán** bằng cách nhân đôi số dấu nháy một cách mù quáng.
- Viết test riêng cho từng nhánh `choice`, gồm giá trị tại ngưỡng và ngay trên ngưỡng.
- Kiểm thử những bản dịch chứa apostrophe hoặc literal braces ngay trong nhánh.
- Khi logic số nhiều có các nhánh ngữ pháp phức tạp, cân nhắc cách thiết kế message keys/formatting phù hợp thay vì nhồi mọi logic vào một pattern khó bảo trì.

Mẫu choice trên được chọn để tránh quote phức tạp và có stdout đã kiểm chứng. Nếu muốn chỉnh nó cho một ngôn ngữ khác, cần test đúng ngưỡng và chính sách số nhiều của ngôn ngữ đó; `ChoiceFormat` không tự thực thi mọi quy tắc plural hiện đại.

## 13. Pattern từ ResourceBundle và file .properties

Thông điệp ứng dụng thường nằm trong các file như:

```properties
welcome=You''re invited, {0}.
quoted=Literal '{0}' plus {0}
braced=Result: '{'{0}'}'
files={0,choice,0#no files|1#one file|1<{0,number,integer} files}
```

Đây là **nội dung file `.properties`**, không phải Java source. Khi code lấy:

```java
String pattern = bundle.getString("welcome");
MessageFormat message =
        new MessageFormat(pattern, locale);
```

MessageFormat nhận **chuỗi giá trị đã được ResourceBundle nạp**, rồi áp quy tắc quote như bình thường.

Đối với `.properties`, các tầng xử lý chính là:

```text
File .properties
      |
      v
Properties/ResourceBundle parser
      |  giải mã escape và cấu trúc key=value
      v
String pattern trong Java
      |
      v
MessageFormat parser
      |  xử lý nháy đơn, braces, format element
      v
Chuỗi cuối cùng sau khi chèn đối số
```

Không dùng JSON escape, Java source escape hoặc Markdown escape để đoán giá trị thật sau khi file `.properties` được tải. Nếu chưa chắc, test bằng cùng cơ chế ResourceBundle mà sản phẩm đang dùng.

### Java 9+ và encoding properties của ResourceBundle

Với Java 17, resource bundle dạng `.properties` được cơ chế mặc định của `ResourceBundle` đọc theo UTF-8, có khả năng fallback theo quy tắc API cho dữ liệu không hợp lệ. Nhưng `java.util.Properties.load(InputStream)` và các cơ chế nạp khác **không mặc nhiên có cùng quy tắc encoding**.

Do đó, các bài test trên dữ liệu Việt/Pháp/Nhật nên dùng đường load **giống hệt ứng dụng production**, tránh kết luận sai chỉ từ một cách đọc file khác. Kiểm tra encoding là một việc riêng với việc escape apostrophe cho MessageFormat.

### Không nhất thiết mọi chuỗi trong bundle đều là MessageFormat pattern

Nếu một message key không có placeholder và ứng dụng hiển thị nguyên chuỗi từ bundle mà **không gọi MessageFormat**, dấu `'` không bị MessageFormat xử lý.

Nhưng khi cùng key được đưa qua `MessageFormat` vì một API helper dùng chung cho tất cả thông điệp, apostrophe lại có ý nghĩa cú pháp. Cần thống nhất **contract của message catalog**: key nào là plain text, key nào là MessageFormat pattern, và helper nào được phép chạy formatter.

Không đòi người dịch viết `''` cho mọi chuỗi thuần văn bản nếu chúng không bao giờ qua `MessageFormat`; cũng không cho phép viết `'` đơn trong các mẫu thực sự được format.

## 14. Kiểm thử pattern bằng assertion, không chỉ nhìn console

Một hướng kiểm thử bền vững:

1. Mỗi thông điệp có một **key** và các locale áp dụng.
2. Test dữ liệu đối số điển hình và các trường hợp biên.
3. Assert kết quả **chính xác**, gồm dấu nháy, braces, vị trí placeholder, dấu cách và chữ số.
4. Assert những pattern lỗi quan trọng bị ném exception.
5. Assert các pattern tưởng hợp lệ nhưng sai semantics phải cho ra kết quả mà QA coi là lỗi.
6. Khi pattern dùng `number/date/choice`, cố định locale/timezone hoặc cấu hình có thể làm output thay đổi.
7. Với bản dịch thực tế, kiểm tra mọi key theo locale được hỗ trợ và có bộ test vector đại diện.

**Không chỉ test rằng constructor không lỗi.** `It's {0}` là phản ví dụ quan trọng nhất.

**Không chỉ test bằng tên `A` hoặc số `1`.** Những chuỗi có dấu nháy, braces, dấu câu và số ở ngưỡng choice mới làm lộ lỗi. Test cả nhiều đối số để phát hiện bản dịch đổi vị trí sai.

## 15. Bộ test Java 17+ hoàn chỉnh, không cần JUnit

Lưu tệp `MessagePatternTests.java`:

```java
import java.text.MessageFormat;
import java.util.Locale;

public class MessagePatternTests {
    private static int passed;

    private static void equalsText(
            String name,
            String pattern,
            Object[] args,
            String expected) {

        String actual =
                new MessageFormat(pattern, Locale.US).format(args);

        if (!expected.equals(actual)) {
            throw new AssertionError(
                    name + " expected=[" + expected +
                    "] actual=[" + actual + "]");
        }

        System.out.println("PASS " + name + " => " + actual);
        passed++;
    }

    private static void rejects(String name, String pattern) {
        try {
            new MessageFormat(pattern, Locale.US);
            throw new AssertionError(
                    "Accepted invalid pattern: " + name);
        } catch (IllegalArgumentException expected) {
            System.out.println(
                    "PASS " + name + " => IllegalArgumentException");
            passed++;
        }
    }

    public static void main(String[] args) {
        Object[] a = {"Mai", 2, 1234.5};

        equalsText(
                "escaped-apostrophe",
                "You''re invited, {0}.",
                a,
                "You're invited, Mai.");

        equalsText(
                "quoted-placeholder",
                "Literal '{0}' plus {0}",
                a,
                "Literal {0} plus Mai");

        equalsText(
                "apostrophes-around-value",
                "''{0}''",
                a,
                "'Mai'");

        equalsText(
                "braces-around-value",
                "'{'{0}'}'",
                a,
                "{Mai}");

        equalsText(
                "json",
                "JSON: '{'\"name\": \"{0}\"'}'",
                a,
                "JSON: {\"name\": \"Mai\"}");

        equalsText(
                "unmatched-quote",
                "It's {0}",
                a,
                "Its {0}");

        equalsText(
                "choice-nested",
                "{1,choice,0#none|1#one|" +
                "1<{1,number,integer} files}",
                a,
                "2 files");

        equalsText(
                "closing-brace-literal",
                "Bad }",
                a,
                "Bad }");

        rejects(
                "unclosed-opening-brace",
                "Bad {0");

        rejects(
                "nonnumeric-index",
                "Bad {abc}");

        rejects(
                "unknown-format-type",
                "Bad {0,unknown}");

        rejects(
                "unescaped-nested-opening-brace",
                "Bad {{0}}");

        System.out.println("TOTAL=" + passed);
    }
}
```

Biên dịch/chạy:

```bash
javac MessagePatternTests.java
java MessagePatternTests
```

Đầu ra từ chương trình đã biên dịch và chạy thành công trên JDK:

```text
PASS escaped-apostrophe => You're invited, Mai.
PASS quoted-placeholder => Literal {0} plus Mai
PASS apostrophes-around-value => 'Mai'
PASS braces-around-value => {Mai}
PASS json => JSON: {"name": "Mai"}
PASS unmatched-quote => Its {0}
PASS choice-nested => 2 files
PASS closing-brace-literal => Bad }
PASS unclosed-opening-brace => IllegalArgumentException
PASS nonnumeric-index => IllegalArgumentException
PASS unknown-format-type => IllegalArgumentException
PASS unescaped-nested-opening-brace => IllegalArgumentException
TOTAL=12
```

Bộ test này minh họa hai kiểu assertion:

- `equalsText(...)`: so **output cuối** theo một expectation cụ thể.
- `rejects(...)`: kiểm tra pattern cú pháp sai phải ném `IllegalArgumentException`.

Trong bài học, case `unmatched-quote` assert **hành vi thực tế của API** để giải thích cơ chế. Trong ứng dụng thật, nếu ý định là `It's Mai`, test nên assert kết quả đúng và vì vậy sẽ **fail** khi pattern bị viết thành `It's {0}`. Không nên lấy các kết quả sai có chủ đích của demo làm kỳ vọng sản phẩm.

### Giới hạn của harness

Harness này dùng một `Locale.US` và vài pattern minh họa. Dự án thực tế cần duyệt **message catalog** của các locale được hỗ trợ, test message keys quan trọng và những lựa chọn format phụ (number, date, choice...). Với CI, có thể dùng JUnit 5 parameterized tests để quản lý nhiều trường hợp hơn, nhưng ví dụ trên không yêu cầu thư viện ngoài JDK.

## 16. Kiểm thử quote trong dữ liệu đối số khác quote trong pattern

Một nhầm lẫn phổ biến: người dùng nhập:

```text
O'Brien {1}
```

vào ô tên, ứng dụng dùng pattern:

```text
User input: {0}
```

Thông thường, đối số này được **chèn như dữ liệu**, không tự biến thành cú pháp MessageFormat ở tầng pattern ngoài. Ví dụ:

```java
MessageFormat formatter =
        new MessageFormat("User input: {0}", Locale.US);

System.out.println(
        formatter.format(
                new Object[]{"O'Brien {1}"}));
```

Kết quả đã kiểm chứng:

```text
User input: O'Brien {1}
```

Từ đó:

- **Không cần sửa mọi dấu apostrophe trong tên người dùng thành `''` chỉ để chèn qua `{0}` đơn giản.**
- **Cần sửa dấu apostrophe literal nằm trong chính pattern** trước khi MessageFormat phân tích.
- Không được lấy một pattern do người dùng tự nhập rồi truyền cho `MessageFormat` mà thiếu validation, vì cú pháp `{...}` sẽ được hiểu là lệnh định dạng.
- Nhánh `choice` có thể có **bước phân tích lại pattern nhúng** trong quá trình mở rộng, nên không tổng quát hóa quy tắc “đối số không bao giờ có thể liên quan đến parsing” cho mọi chuỗi định dạng lồng.

Phân biệt rõ **template/pattern** với **giá trị arguments** giúp bảo đảm bộ test không escape dữ liệu hai lần hoặc làm hỏng tên, địa chỉ và nội dung tự nhiên của người dùng.

## 17. Giá trị null, thiếu đối số và sai kiểu

Một bản dịch có thể được chấp nhận về cú pháp nhưng vẫn lỗi ở thời điểm format.

### Thiếu argument

Với pattern:

```text
Hi {2}, {0}.
```

và mảng đối số chỉ chứa `{"Mai"}`, output được quan sát:

```text
Hi {2}, Mai.
```

Như vậy, **không thể coi việc format thành công là đã có đủ arguments**. QA bản dịch nên xác định tập index trong pattern và so với dữ liệu được truyền.

### Null

Với pattern `Hi {0}` và `new Object[]{null}`, output thông dụng của Java MessageFormat là:

```text
Hi null
```

Nếu sản phẩm yêu cầu câu tự nhiên khi thiếu tên người, nên xử lý null theo nghiệp vụ thay vì vô tình hiển thị chữ `null`. Cũng có thể cần phân nhánh resource keys tùy ngữ cảnh.

### Sai kiểu

Pattern `{0,number}` không thể mặc nhiên nhận mọi đối số `String`. Ví dụ truyền string `oops` sẽ làm formatter số không thể xử lý và có thể ném `IllegalArgumentException`.

Vì vậy, hợp đồng message cần có:

- Số lượng và index các arguments.
- Kiểu dữ liệu mong đợi tại từng index.
- Có được phép null không.
- Những format styles theo locale.
- Kiểm thử ngưỡng số, ngày và kiểu đặc biệt.

Không đặt tất cả lỗi vào một catch chung rồi trả nguyên pattern cho người dùng: điều đó dễ che giấu bản dịch sai và gây hiển thị placeholder `{0}` không mong muốn.

## 18. Đừng phụ thuộc tuyệt đối vào toPattern() để sửa lỗi quote

`MessageFormat.toPattern()` trả lại một dạng pattern dựa trên cấu hình đã được parser lưu. Dạng này có thể **khác chuỗi gốc**, vì parser đã diễn giải quote và chuẩn hóa những cấu trúc nhất định.

Ví dụ pattern:

```text
You're welcome, {0}!
```

đã bị phân tích sai: nháy đơn bắt đầu literal cho đến cuối, nên `{0}` không được coi là argument. Gọi `toPattern()` không thể suy đoán **ý định của người dịch** để tự sửa thành `You''re welcome, {0}!`.

Khi QA:

1. Giữ nguyên pattern từ bundle để báo lỗi bằng message key và locale.
2. Tạo MessageFormat và kiểm tra output/test vectors.
3. Có thể dùng `toPattern()` như dữ liệu hỗ trợ debug **sau khi hiểu nó không phải raw source**.
4. Không dựa trên việc string `toPattern()` có vẻ cân bằng quote để khẳng định bản dịch đúng.

Nếu ứng dụng có công cụ lint pattern tĩnh, nó nên phân biệt cú pháp được MessageFormat cho phép với **quy ước sản phẩm nghiêm ngặt hơn** (ví dụ placeholder bắt buộc, không chấp nhận nháy đơn chưa đóng). Lint không thay thế test output.

## 19. Locale, dấu câu và văn bản được dịch

Khi bản dịch tiếng Việt, Pháp, Anh hoặc Nhật sử dụng MessageFormat, phải test với **đúng Locale**:

```java
Locale locale = Locale.FRANCE;
MessageFormat formatter =
        new MessageFormat(
                "Total : {0,number,#,##0.00}",
                locale);
```

Với `Locale.FRANCE`, các dấu nhóm, dấu thập phân và khoảng trắng có thể khác US. Trên môi trường JDK dùng để kiểm chứng, output cho 1234.5 là một số nhóm bằng khoảng trắng hẹp không ngắt và dấu phẩy thập phân, không phải `1,234.50`.

Không nên copy expected result US sang FR hay vi-VN. Hơn nữa, dữ liệu CLDR có thể cập nhật theo JDK/provider, nên tests phụ thuộc ký hiệu locale cần được cố định phiên bản runtime hoặc đánh giá khi cập nhật.

### Placeholder có thể đổi vị trí theo ngôn ngữ

Ví dụ:

```text
English: {0} sent {1} a message.
Locale khác: {1} đã nhận tin nhắn từ {0}.
```

Đây là một ưu điểm của MessageFormat: người dịch có thể đảo `{0}` và `{1}` cho tự nhiên. Test phải xác nhận **ý nghĩa và vị trí** arguments, không cấm mọi thay đổi thứ tự.

Nhưng nếu người dịch vô tình thêm dấu `'` trước `{1}`, phần sau có thể bị quote và placeholder không được thay. Vì vậy, kiểm thử toàn văn trong từng locale quan trọng hơn kiểm tra chỉ số placeholder bằng regex đơn giản.

### Apostrophe trong văn bản dịch

Ví dụ tiếng Pháp chứa dấu nháy đơn ASCII trong các từ có lược bỏ âm. Nếu chuỗi **đi qua MessageFormat**, nháy đơn này cần `''` như tiếng Anh. Nếu bản dịch dùng dấu cong `’`, quy tắc cú pháp khác, nhưng tính chính xác typography vẫn là trách nhiệm riêng của nội dung dịch.

Không được “sửa” bằng cách xóa mọi dấu nháy đơn: điều đó làm hỏng ngôn ngữ tự nhiên và che lỗi pattern.

## 20. MessageFormat là mutable: cách quản lý khi kiểm thử

`java.text.MessageFormat` có các phương thức như `applyPattern(...)`, `setLocale(...)`, `setFormat(...)` và `setFormats(...)`; các formatter con cũng có thể có trạng thái. Không nên dùng một instance `static MessageFormat` rồi sửa pattern/locale theo từng request trong nhiều thread.

Hai phương án đơn giản:

1. Tạo `new MessageFormat(pattern, locale)` theo mỗi operation/test.
2. Cache prototype theo **locale + pattern + cấu hình/version** rồi clone cho mỗi caller nếu benchmark chứng minh cần.

Với unit tests, tạo instance mới giúp tránh test trước làm thay đổi trạng thái test sau. Cách này đặc biệt hữu ích khi kiểm thử quote, bởi `applyPattern` có thể làm thay đổi hoàn toàn cách phân tích văn bản.

`MessageFormat.format(String pattern, Object... arguments)` là tiện ích static, nhưng lựa chọn locale không giống constructor truyền `Locale` tường minh; nếu cần output phụ thuộc số/ngày, dùng instance với locale rõ ràng.

Không chia sẻ một MessageFormat mutable giữa threads chỉ vì pattern giống nhau. Thread safety của `ConcurrentHashMap` cache không biến formatter bên trong thành thread-safe.

## 21. Kiểm thử round-trip parse và giới hạn của MessageFormat.parse

`MessageFormat` có các phương thức parse, nhưng **không phải mọi pattern format đều có thể parse trở lại một cách hoàn hảo**. Pattern lặp placeholder, choice, text literal và sự mơ hồ giữa các field có thể khiến kết quả parse không phải thông tin ban đầu.

Hơn nữa, một parse có thể thành công trên **tiền tố** chuỗi. Ví dụ:

```java
MessageFormat parser =
        new MessageFormat(
                "{0,number,integer} units", Locale.US);

ParsePosition position = new ParsePosition(0);

Object[] values =
        parser.parse("12 units extra", position);
```

Ví dụ cần import `java.text.MessageFormat`, `ParsePosition` và `Locale`.

Kết quả quan sát:

```text
values[0] = 12
position.getIndex() = 8
position.getErrorIndex() = -1
```

Input `"12 units extra"` có độ dài lớn hơn 8. Vì vậy, nếu dùng `MessageFormat.parse` để **kiểm tra toàn bộ input**, phải xác nhận:

```java
values != null &&
position.getIndex() == input.length()
```

với `input` là chuỗi đang parse. Đây là **mảnh code** minh họa điều kiện chấp nhận; không phải thuật toán kiểm tra mọi quy tắc nghiệp vụ. `getErrorIndex()==-1` không đảm bảo toàn chuỗi đã được tiêu thụ.

Nội dung chính của bài vẫn là **kiểm thử pattern format**, nhưng parse cần được xem xét nếu ứng dụng dùng MessageFormat hai chiều. Không hứa “format xong parse lại sẽ luôn có Object[] bằng dữ liệu gốc”.

## 22. Thiết kế ma trận kiểm thử cho bản dịch sản phẩm

Một bảng test vector tối thiểu:

| Nhóm | Pattern hoặc tình huống | Kỳ vọng |
|---|---|---|
| Text thường | `Hello, {0}!` | Placeholder được thay |
| ASCII apostrophe | `You''re {0}.` | Có một dấu `'` trong output |
| Nháy đơn chưa đóng | `You're {0}.` | QA phát hiện output sai ý nghĩa |
| Literal placeholder | `'{0}'` | In `{0}`, không thay |
| Literal apostrophe quanh giá trị | `''{0}''` | In `'Mai'` |
| Braces quanh giá trị | `'{'{0}'}'` | In `{Mai}` |
| JSON-like text | `'{' ... ` / `'}'` | Braces literal và placeholders hoạt động đúng |
| Dấu `{` chưa đóng | `Bad {0` | Ném `IllegalArgumentException` |
| Chỉ số sai | `{abc}` | Ném `IllegalArgumentException` |
| Format type sai | `{0,unknown}` | Ném `IllegalArgumentException` |
| Ngưỡng choice | 0, 1, 2, 5 | Chọn đúng nhánh và placeholder con |
| Locale number | US và FR | Dấu số phù hợp từng locale |
| Thiếu argument | `{2}` với 1 argument | QA phát hiện placeholder chưa thay |
| Null argument | `{0}` với null | Output đáp ứng quy tắc sản phẩm |
| Sai kiểu | `{0,number}` với string không số | Test lỗi runtime phù hợp |
| Nội dung người dùng chứa `'`/`{...}` | Giá trị đi vào `{0}` | Dữ liệu được chèn, không escape thừa |
| Pattern từ bundle | Mỗi key/locale | Output đúng, không chỉ parse thành công |

Một bộ QA tốt nên có **assertions khác nhau cho cú pháp và ngữ nghĩa**:

- Syntax test: tạo formatter từ pattern.
- Semantic test: output phải chính xác theo câu được dịch.
- Argument-contract test: tất cả placeholder cần có giá trị đúng kiểu.
- Locale test: định dạng số/ngày không bị lẫn từ default locale.
- Regression test: pattern mới và pattern đã duyệt được kiểm tra lại trong CI.

## 23. Các sai lầm thường gặp

**1. Dùng một dấu `'` để in dấu nháy đơn.** Trong pattern `MessageFormat`, một nháy đơn có chức năng quote; muốn hiển thị một nháy thẳng dùng `''`.

**2. Coi nháy đơn chưa đóng luôn là syntax error.** Parser có thể tự đóng ở cuối pattern và để lại `{0}` literal.

**3. Viết `'{0}'` khi muốn in `'Mai'`.** Đó là quote placeholder, không phải chèn giá trị. Dùng `''{0}''`.

**4. Viết `{{0}}` như cách escape brace.** MessageFormat không dùng cơ chế escape này.

**5. Chỉ kiểm tra “pattern compile được”.** Nhiều pattern sai ý nghĩa vẫn được chấp nhận.

**6. Chỉ test các thông điệp tiếng Anh không dấu nháy đơn.** Bản dịch có apostrophe, dấu nháy cong hoặc ngôn ngữ khác có thể phơi bày lỗi.

**7. Đồng nhất escape của Java source với escape của MessageFormat.** Đây là hai tầng cú pháp riêng.

**8. Đồng nhất escape của `.properties` với MessageFormat.** File được load trước rồi chuỗi mới đến MessageFormat.

**9. Không kiểm tra JSON literal braces.** Dấu `{` có thể bị hiểu là format element thay vì dữ liệu cố định.

**10. Quên rằng đối số có thể thiếu.** Output có thể giữ placeholder literal thay vì ném exception.

**11. Đưa string vào `{0,number}` mà không kiểm soát kiểu.** Formatter số có thể ném lỗi.

**12. Chỉ test một nhánh choice.** Lỗi pattern lồng thường chỉ xuất hiện khi đi vào nhánh nhất định.

**13. Tự tăng số nháy đơn trong nested choice bằng phỏng đoán.** Phải test từng nhánh và từng tầng.

**14. Dùng formatter mặc định locale cho output test cố định.** Dấu nhóm/thập phân có thể khác.

**15. Dùng MessageFormat để JSON-escape dữ liệu người dùng.** Nó không phải JSON serializer.

**16. Đổi dấu nháy đơn của tên người dùng thành `''` trước khi truyền như argument thường.** Dễ làm thay đổi dữ liệu thật không cần thiết.

**17. Xem `toPattern()` như công cụ phục hồi ý định của người dịch.** Nó chỉ phản ánh pattern đã được phân tích/lưu, không tự sửa nội dung sai.

**18. Dùng một MessageFormat mutable chung giữa threads và thay `applyPattern`.** Dễ lẫn dữ liệu/cấu hình.

**19. Chỉ kiểm thử `format` mà bỏ qua `parse` khi ứng dụng thực sự dùng parse.** Parse có thể tiêu thụ một phần input.

**20. Dùng các kết quả lỗi có chủ đích của bài demo làm expected output sản phẩm.** Test cần phản ánh **ý định thông điệp**, không chỉ hành vi API.

## 24. Bài tập tự kiểm tra

**Câu 1.** Trong MessageFormat, pattern `You''re {0}` cho ra dấu nháy đơn nào?

**Đáp án:** `''` trong pattern trở thành một `'` ở output. `{0}` vẫn được thay bằng argument.

**Câu 2.** Vì sao `You're {0}` có thể cho output `Youre {0}`?

**Đáp án:** Dấu `'` mở vùng literal đến cuối pattern, làm placeholder mất vai trò thay thế. Đây là lỗi ngữ nghĩa im lặng.

**Câu 3.** Muốn in nguyên văn `{0}`, viết pattern thế nào?

**Đáp án:** `'{0}'`.

**Câu 4.** Muốn in `{Mai}` từ đối số `Mai` thì sao?

**Đáp án:** `'{'{0}'}'`.

**Câu 5.** Muốn in `'Mai'` (có hai dấu nháy bao quanh giá trị), dùng gì?

**Đáp án:** `''{0}''`.

**Câu 6.** Có thể viết `{{0}}` để escape brace như một số template engine không?

**Đáp án:** Không. Trong ví dụ JDK, pattern này bị từ chối bằng `IllegalArgumentException`.

**Câu 7.** Vì sao test Java constructor thành công chưa đủ?

**Đáp án:** Những pattern như `It's {0}` vẫn hợp lệ theo parser nhưng in sai, không thay đối số.

**Câu 8.** Dữ liệu người dùng `O'Brien {1}` truyền qua `{0}` có cần escape nháy thành `''` trước không?

**Đáp án:** Không, nếu chỉ chèn như argument bình thường; phải phân biệt dữ liệu đối số và pattern.

**Câu 9.** Vì sao `MessageFormat` với `Locale.FRANCE` không nên assert output số theo `Locale.US`?

**Đáp án:** Các quy tắc nhóm chữ số, dấu thập phân và ký tự khoảng trắng khác nhau giữa locale.

**Câu 10.** Với `MessageFormat.parse`, điều kiện kiểm tra không còn phần dư là gì?

**Đáp án:** Ngoài parse không trả `null`, `position.getIndex() == input.length()` khi ParsePosition bắt đầu tại 0.

## 25. Tổng kết

Với `MessageFormat`, dấu nháy đơn và ngoặc nhọn là **một phần của ngôn ngữ pattern**, không chỉ là dấu câu để hiển thị:

- `''` tạo **một dấu nháy đơn ASCII literal**.
- `'{0}'` hiển thị nguyên văn `{0}`; `''{0}''` hiển thị dấu nháy quanh **giá trị đã thay**.
- `'{'{0}'}'` bao giá trị trong braces.
- Nháy đơn chưa đóng có thể **tự đóng ở cuối pattern**, không ném lỗi nhưng làm mất placeholder.
- Pattern `choice` và subformats có thể chứa các tầng cú pháp, phải test bằng dữ liệu từng nhánh.
- Đừng nhầm nội dung `.properties`, Java source string và quy tắc quote của `MessageFormat`.
- Kiểm thử **output theo locale, kiểu và tập arguments**, không chỉ `new MessageFormat(...)` thành công.

**Tài liệu chính thức:** [Java SE 17 — MessageFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/MessageFormat.html) · [ChoiceFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ChoiceFormat.html) · [DecimalFormat](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/DecimalFormat.html) · [ResourceBundle](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ResourceBundle.html) · [ParsePosition](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/ParsePosition.html).
