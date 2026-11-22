# `stripIndent`, `translateEscapes` và quan hệ với text block trong Java 17

Java 17 cung cấp hai phương thức của `String` là `stripIndent()` và `translateEscapes()` để xử lý chuỗi nhiều dòng và các chuỗi có ký hiệu escape. Chúng có liên hệ chặt chẽ với **text block** (`""" ... """`), nhưng mỗi cơ chế làm một việc khác nhau:

- **Text block** là cú pháp literal nhiều dòng. Ngay khi biên dịch, Java đã xử lý thụt lề không đáng kể và các escape sequence trong nội dung.
- **`stripIndent()`** là phương thức chạy lúc runtime, loại bỏ phần thụt lề chung của các dòng trong một `String`.
- **`translateEscapes()`** là phương thức chạy lúc runtime, chuyển các escape sequence hợp lệ đang có trong `String` thành ký tự tương ứng.

Cả hai phương thức được bổ sung từ Java 15 và sử dụng bình thường trong **Java 17**, không cần bật preview. Hiểu rõ thứ tự xử lý giúp tránh xóa nhầm khoảng trắng, tạo xuống dòng sai hoặc dịch escape hai lần.

## 1. Text block là gì?

Text block cho phép viết một chuỗi nhiều dòng trực tiếp trong mã nguồn:

```java
String message = """
        Xin chào!
        Chào mừng đến với Java 17.
        Chúc bạn học tốt.
        """;

System.out.println(message);
```

Kết quả:

```text
Xin chào!
Chào mừng đến với Java 17.
Chúc bạn học tốt.
```

Text block bắt đầu bằng ba dấu nháy kép `"""`. Sau dấu mở phải có một **line terminator** (ký tự xuống dòng trong mã nguồn); nội dung bắt đầu ở dòng tiếp theo. Dấu `"""` đóng text block.

Một số đặc điểm:

- Chuỗi tạo ra vẫn có kiểu `String`; text block không phải một kiểu dữ liệu riêng.
- Các dòng trong nội dung được giữ thành các ký tự xuống dòng trong chuỗi.
- Java chuẩn hóa line terminator trong text block thành `\n`, kể cả khi tệp mã nguồn dùng kiểu xuống dòng khác.
- Java loại bỏ phần thụt lề không đáng kể theo vị trí nội dung và dấu đóng.
- Escape sequence trong text block được xử lý khi biên dịch.

Text block trở thành tính năng chính thức từ **Java 15** (JEP 378). Trong Java 17, có thể dùng trực tiếp:

```bash
javac --release 17 TextBlockDemo.java
java TextBlockDemo
```

Không cần `--enable-preview` cho text block, `stripIndent()` hay `translateEscapes()`.

## 2. Java xử lý text block theo thứ tự nào?

Để hiểu quan hệ với hai phương thức, cần nắm quá trình tạo `String` từ text block. Về khái quát, Java thực hiện các bước:

1. **Chuẩn hóa line terminator:** các kiểu kết thúc dòng trong tệp nguồn được chuẩn hóa thành `\n` trong giá trị chuỗi.
2. **Xác định và loại bỏ incidental white space:** Java tính mức thụt lề chung dựa trên các dòng nội dung và vị trí dấu đóng text block, rồi loại bỏ phần thụt lề đó. Khoảng trắng ở cuối dòng cũng được xử lý theo quy tắc text block.
3. **Dịch escape sequence:** các ký hiệu như `\n`, `\t`, `\s`, `\\` được chuyển thành ký tự tương ứng.

Đây là xử lý **lúc biên dịch**. Khi chương trình chạy, biến đã chứa một `String` với kết quả sau các bước trên. Java không giữ lại dấu `"""` hoặc một đối tượng text block đặc biệt ở runtime.

### 2.1. Vì sao vị trí dấu đóng ảnh hưởng đến thụt lề?

Ví dụ:

```java
String sql = """
        SELECT id, name
        FROM users
        WHERE active = true
        """;
```

Dấu đóng nằm dưới các dòng nội dung với 8 khoảng trắng. Phần thụt lề chung là 8 khoảng trắng, nên chuỗi thu được là:

```text
SELECT id, name
FROM users
WHERE active = true
```

Ngược lại, nếu dấu đóng đặt ở cột đầu tiên:

```java
String sql = """
        SELECT id, name
        FROM users
        WHERE active = true
""";
```

Dấu đóng ở cột đầu tiên khiến mức thụt lề chung là 0. Các khoảng trắng viết trước nội dung được giữ lại. Chuỗi có dạng:

```text
        SELECT id, name
        FROM users
        WHERE active = true
```

Do đó, vị trí dấu đóng không chỉ là cách trình bày mã nguồn; nó tham gia quyết định nội dung thực tế của chuỗi.

### 2.2. Khoảng trắng tương đối vẫn được giữ

```java
String menu = """
        Menu
            1. New
            2. Open
            3. Exit
        """;
```

Java loại bỏ 8 khoảng trắng chung ở đầu mỗi dòng. Bốn khoảng trắng thêm trước các mục vẫn được giữ:

```text
Menu
    1. New
    2. Open
    3. Exit
```

Đây là điều mong muốn khi tạo nội dung có cấu trúc như SQL, JSON, HTML hoặc văn bản nhiều cấp.

## 3. `stripIndent()` làm gì?

`stripIndent()` là phương thức của `String`, dùng để **loại bỏ phần thụt lề chung của các dòng**. Phương thức này hữu ích khi chuỗi được tạo từ dữ liệu động, ghép từ nhiều nguồn hoặc không được khai báo trực tiếp bằng text block.

Cú pháp:

```java
String normalized = original.stripIndent();
```

Ví dụ:

```java
String original =
        "    alpha\n" +
        "        beta\n" +
        "    gamma\n";

String normalized = original.stripIndent();

System.out.println(normalized);
```

Kết quả:

```text
alpha
    beta
gamma
```

Java tìm mức thụt lề chung là 4 khoảng trắng:

- Dòng `alpha` có 4 khoảng trắng đầu dòng.
- Dòng `beta` có 8 khoảng trắng đầu dòng.
- Dòng `gamma` có 4 khoảng trắng đầu dòng.
- Mỗi dòng được bỏ đi 4 khoảng trắng chung; phần thụt lề thêm của `beta` vẫn còn.

### 3.1. Cách xác định mức thụt lề

Theo hợp đồng của `String.stripIndent()`, Java xét các dòng của chuỗi:

- Với mỗi dòng không trống, xác định số ký tự whitespace ở đầu dòng.
- Mức thụt lề chung là số nhỏ nhất trong các dòng không trống.
- Loại bỏ mức chung khỏi các dòng; các dòng trắng cũng được xử lý theo quy tắc của phương thức.
- Khoảng trắng ở cuối dòng được loại bỏ.
- Các dòng kết quả được ghép bằng line feed (`\n`).

Ví dụ:

```java
String source = """
        first
            second

        third
        """;

System.out.print(source);
```

Text block đã tự xử lý incidental indentation lúc biên dịch. Với chuỗi `source` sau khi tạo, các dòng đã có mức thụt lề tương đối. Khi gọi thêm `stripIndent()`, phương thức lại xét chính nội dung `String` đang có ở runtime.

### 3.2. Dòng trắng và khoảng trắng cuối dòng

`stripIndent()` không chỉ xóa khoảng trắng đầu dòng. Nó còn loại bỏ khoảng trắng ở cuối dòng. Điều này thường hữu ích cho văn bản định dạng, nhưng cần lưu ý nếu khoảng trắng cuối dòng mang ý nghĩa dữ liệu.

Ví dụ:

```java
String raw = "    A    \n    B   \n";
String result = raw.stripIndent();

System.out.println(result.replace(" ", "·"));
```

Dấu `·` trong biểu thức `replace` chỉ dùng để hiển thị khoảng trắng. Các khoảng trắng đầu dòng chung và khoảng trắng cuối dòng sẽ được loại bỏ.

Nếu nội dung cần giữ nguyên số khoảng trắng ở cuối dòng (ví dụ định dạng cố định hoặc dữ liệu có ý nghĩa theo từng cột), không gọi `stripIndent()` một cách tùy tiện. Hãy thiết kế cách xử lý chuỗi phù hợp với định dạng đó.

### 3.3. Tab và space

Mức thụt lề được tính theo **ký tự whitespace**, không theo độ rộng hiển thị của tab trên màn hình. Một ký tự tab có thể chiếm nhiều cột khi editor hiển thị, nhưng vẫn là một ký tự trong chuỗi.

Trộn tab và space có thể khiến phần thụt lề nhìn bằng mắt không giống kết quả xử lý. Khi viết text block hoặc dữ liệu nhiều dòng, nên thống nhất cách thụt lề trong cùng một nội dung.

## 4. Text block đã strip indent rồi, có cần gọi `stripIndent()` nữa không?

Thông thường, **không cần gọi thêm**. Text block đã được Java loại bỏ incidental white space ngay khi biên dịch. Ví dụ:

```java
String json = """
        {
            "name": "An",
            "active": true
        }
        """;
```

Giá trị `json` đã có dạng:

```text
{
    "name": "An",
    "active": true
}
```

Nếu gọi `json.stripIndent()`, kết quả thường không thay đổi vì dòng mở đầu `{` đã không có khoảng trắng đầu dòng; mức thụt lề chung là 0. Việc gọi thêm không giúp text block “hoạt động” và thường là thừa.

Tuy nhiên, `stripIndent()` vẫn có ích khi:

- Chuỗi đến từ một cấu hình hoặc nguồn dữ liệu runtime.
- Nội dung được ghép từ nhiều mảnh và có thụt lề chung không mong muốn.
- Muốn chuẩn hóa chuỗi nhiều dòng trước khi so sánh, hiển thị hoặc lưu trữ.
- Một chuỗi được xây dựng bằng cách khác, không phải text block.

Ví dụ với dữ liệu runtime:

```java
static String normalizeMessage(String input) {
    return input.stripIndent();
}

String raw = "        Warning\n            Disk is almost full\n        Contact admin\n";
System.out.println(normalizeMessage(raw));
```

Kết quả:

```text
Warning
    Disk is almost full
Contact admin
```

Đây là trường hợp điển hình mà `stripIndent()` có vai trò thực tế.

### 4.1. Phân biệt với `trim()` và `strip()`

Ba phương thức không có cùng mục đích:

| Phương thức | Phạm vi xử lý | Ý nghĩa |
|---|---|---|
| `trim()` | Hai đầu toàn chuỗi | Loại bỏ ký tự có giá trị không lớn hơn U+0020 ở đầu và cuối |
| `strip()` | Hai đầu toàn chuỗi | Loại bỏ whitespace theo định nghĩa Unicode của `Character.isWhitespace` |
| `stripIndent()` | Từng dòng | Bỏ phần thụt lề chung và whitespace cuối dòng |

Ví dụ:

```java
String text = "    alpha\n        beta\n    gamma\n";

System.out.println(text.strip());
System.out.println(text.stripIndent());
```

`strip()` loại bỏ khoảng trắng ở đầu toàn chuỗi và cuối toàn chuỗi. Nó không căn chỉnh từng dòng. `stripIndent()` xử lý thụt lề của từng dòng theo mức chung.

Đừng dùng `trim()` để thay thế `stripIndent()` khi muốn giữ cấu trúc nhiều dòng và bỏ indentation đồng đều.

## 5. `translateEscapes()` làm gì?

`translateEscapes()` chuyển các **escape sequence hợp lệ đang có trong một `String`** thành ký tự tương ứng.

Cú pháp:

```java
String decoded = encoded.translateEscapes();
```

Ví dụ:

```java
String encoded = "First line\\nSecond line\\tDone";
String decoded = encoded.translateEscapes();

System.out.println(decoded);
```

Kết quả:

```text
First line
Second line    Done
```

Trong literal Java, `\\n` tạo ra hai ký tự `\` và `n` trong `encoded`. Khi gọi `translateEscapes()`, hai ký tự đó được dịch thành ký tự xuống dòng. Tương tự, `\\t` được dịch thành ký tự tab.

### 5.1. Các escape sequence thông dụng

`translateEscapes()` hỗ trợ các escape sequence của string literal theo Java Language Specification (ngoại trừ Unicode escape):

| Dạng escape trong chuỗi runtime | Ký tự được tạo | Mục đích |
|---|---|---|
| `\b` | Backspace | Lùi một vị trí |
| `\t` | Horizontal tab | Tab ngang |
| `\n` | Line feed | Xuống dòng |
| `\f` | Form feed | Ngắt trang |
| `\r` | Carriage return | Về đầu dòng |
| `\"` | Dấu nháy kép | Chèn `"` vào chuỗi |
| `\'` | Dấu nháy đơn | Chèn `'` |
| `\\` | Dấu backslash | Chèn một ký tự `\` |
| `\s` | Một dấu cách | Biểu diễn space rõ ràng |
| Escape bát phân | Ký tự theo mã bát phân | Biểu diễn ký tự bằng mã octal |

`\s` là escape sequence được bổ sung trong Java 15, hữu ích khi muốn biểu diễn một dấu cách một cách tường minh, nhất là trong text block.

Ví dụ:

```java
String encoded = "A\\sB";
String decoded = encoded.translateEscapes();

System.out.println(decoded.replace(" ", "·"));
```

Kết quả là `A·B`. Chuỗi runtime trước khi dịch chứa backslash và chữ `s`; sau khi dịch, chúng trở thành một dấu cách.

### 5.2. Escape không hợp lệ gây ngoại lệ

Nếu chuỗi runtime chứa backslash theo sau bởi một ký hiệu không phải escape hợp lệ, `translateEscapes()` ném `IllegalArgumentException`.

Ví dụ:

```java
String encoded = "Hello\\q";

String decoded = encoded.translateEscapes(); // IllegalArgumentException
```

Lưu ý: literal `"Hello\\q"` vẫn biên dịch được vì nó tạo ra backslash literal theo sau là `q`. Ngoại lệ xuất hiện **khi gọi phương thức** `translateEscapes()`.

Điều này khác với viết trực tiếp `"Hello\q"` trong mã nguồn: đó là một escape không hợp lệ ngay ở literal và sẽ bị trình biên dịch từ chối.

Khi xử lý chuỗi đến từ file, cấu hình hoặc người dùng, cần biết dữ liệu có thực sự tuân theo quy ước escape của Java hay không trước khi gọi phương thức này.

### 5.3. Unicode escape không được dịch bởi `translateEscapes()`

`translateEscapes()` **không xử lý Unicode escape sequence**. Unicode escape của Java được xử lý ở giai đoạn phân tích mã nguồn, trước khi tạo string literal; phương thức runtime này không chạy lại bước đó.

Ví dụ tạo một chuỗi runtime gồm backslash và `u0041`:

```java
String encodedUnicode = "\\" + "u0041";

System.out.println(encodedUnicode); 
System.out.println(encodedUnicode.translateEscapes());
```

Cả hai dòng đều biểu diễn chuỗi ký tự `\u0041`, không biến nó thành chữ `A`. Nếu cần chuyển mã Unicode dạng văn bản thành ký tự, phải dùng cách giải mã Unicode phù hợp với định dạng dữ liệu của ứng dụng.

Không nên nhầm:

- `\n` là escape sequence được `translateEscapes()` hỗ trợ.
- `\u0041` dưới dạng sáu ký tự runtime không được phương thức này dịch thành `A`.

## 6. Text block đã dịch escape trước khi chương trình chạy

Đây là quan hệ quan trọng nhất giữa `translateEscapes()` và text block.

Trong text block, escape sequence đã được xử lý **lúc biên dịch**:

```java
String message = """
        First line
        Second line
        """;
```

Text block trên đã chứa line feed thật trong giá trị `message`. Không cần gọi `translateEscapes()` để biến xuống dòng thành xuống dòng; chúng đã là ký tự xuống dòng.

Một ví dụ khác:

```java
String message = """
        Column A\tColumn B
        """;
```

Vì `\t` trong mã nguồn text block là escape sequence, giá trị `message` chứa ký tự tab thật giữa hai cột.

Gọi thêm `message.translateEscapes()` thường là thừa. Quan trọng hơn, nó có thể **dịch nhầm các backslash vốn được chủ ý giữ lại**.

### 6.1. Tránh dịch escape hai lần

Giả sử cần lưu một đường dẫn Windows dưới dạng text block:

```java
String path = """
        C:\\temp\\new
        """;

System.out.println(path);
```

Trong mã nguồn, mỗi cặp `\\` tạo ra một backslash literal. Vì vậy chuỗi runtime chứa:

```text
C:\temp\new
```

Nếu gọi tiếp:

```java
String corrupted = path.translateEscapes();
```

phương thức sẽ nhìn thấy `\t` trong `\temp` và `\n` trong `\new`. Chúng bị dịch thành tab và newline, làm đường dẫn sai.

Đây là lý do **không nên gọi `translateEscapes()` một cách tự động trên mọi text block**. Chỉ gọi khi giá trị runtime thực sự còn chứa các escape sequence cần giải mã theo quy ước Java.

## 7. Escape trong text block: `\s` và backslash nối dòng

Text block có hai cách viết đặc biệt rất hữu ích khi định dạng nội dung.

### 7.1. `\s` giữ một dấu cách ở cuối dòng

Trong text block, trailing whitespace thường bị loại bỏ theo quy tắc incidental white space. Nếu thật sự cần một dấu cách ở cuối dòng, dùng `\s`:

```java
String line = """
        Hello\s
        World
        """;
```

`\s` được dịch thành một dấu cách sau chữ `Hello`. Ký tự này không bị loại bỏ như một dấu cách cuối dòng viết trực tiếp trong source, vì escape được dịch **sau bước xử lý indentation/trailing whitespace**.

Có thể quan sát bằng cách thay dấu cách bằng ký hiệu dễ nhìn:

```java
System.out.println(line.replace(" ", "·"));
```

Kết quả có dấu `·` ở cuối dòng `Hello`:

```text
Hello·
World
```

Dùng `\s` khi khoảng trắng cuối dòng thực sự có ý nghĩa. Đừng thêm trailing spaces thủ công rồi mong chúng luôn được giữ trong text block.

### 7.2. Backslash ở cuối dòng nối hai dòng nguồn

Trong text block, backslash ngay trước line terminator có thể **loại bỏ line break trong source**, giúp một chuỗi kết quả không bị ngắt dòng:

```java
String greeting = """
        Hello \
        Java 17
        """;
```

Giá trị chuỗi:

```text
Hello Java 17
```

Dòng nguồn được nối với nhau; khoảng trắng trước backslash vẫn là nội dung, còn line terminator và indentation của dòng tiếp theo được xử lý theo quy tắc text block.

Đây là cơ chế của **text block literal**, không phải lý do để gọi `translateEscapes()` ở runtime.

## 8. Thứ tự gọi `stripIndent()` và `translateEscapes()` có thể làm đổi kết quả

Hai phương thức xử lý hai loại ký tự khác nhau:

- `stripIndent()` nhận diện **dòng thực tế đang có trong chuỗi** và căn chỉnh whitespace.
- `translateEscapes()` có thể biến hai ký tự `\n` thành một line feed thật, từ đó tạo ra một dòng mới.

Vì vậy thứ tự gọi có thể quan trọng.

Ví dụ chuỗi runtime ban đầu có bốn dấu cách, ký tự `A`, hai ký tự `\n` và bốn dấu cách trước `B`:

```java
String encoded = "    A\\n    B";

String firstStrip = encoded.stripIndent().translateEscapes();
String firstTranslate = encoded.translateEscapes().stripIndent();

System.out.println(firstStrip.replace(" ", "·"));
System.out.println("---");
System.out.println(firstTranslate.replace(" ", "·"));
```

Giải thích:

**Cách 1: `stripIndent()` trước**

- Tại thời điểm strip, chuỗi runtime vẫn chỉ có một line thật, vì `\n` chưa được dịch.
- Phương thức loại bỏ bốn khoảng trắng đầu chuỗi.
- Sau đó `translateEscapes()` mới tạo line feed.
- Bốn khoảng trắng trước `B` vẫn nằm ở đầu phần sau line feed.

Kết quả có dạng:

```text
A
····B
```

**Cách 2: `translateEscapes()` trước**

- Escape `\n` được chuyển thành line feed thật.
- Chuỗi lúc này có hai dòng thực.
- `stripIndent()` tìm mức thụt lề chung của cả hai dòng và bỏ bốn khoảng trắng mỗi dòng.

Kết quả:

```text
A
B
```

Khi làm việc với dữ liệu chứa escape biểu diễn xuống dòng, hãy quyết định rõ muốn giải mã trước hay căn lề trước. Không có một thứ tự đúng cho mọi định dạng; thứ tự phải phù hợp với **cấu trúc mà dữ liệu biểu diễn**.

Với text block thông thường, Java đã thực hiện cả hai bước ở compile time theo thứ tự quy định. Không nên mô phỏng lại thứ tự đó bằng cách gọi hai phương thức một cách máy móc.

## 9. Khi nào nên dùng từng cơ chế?

| Tình huống | Cách phù hợp | Lý do |
|---|---|---|
| Viết SQL/JSON/HTML nhiều dòng trong mã nguồn | Text block | Dễ đọc, Java xử lý indentation và escape khi biên dịch |
| Chuỗi nhiều dòng nhận từ cấu hình có indentation đồng đều | `stripIndent()` | Chuẩn hóa phần thụt lề ở runtime |
| Chuỗi runtime chứa `\n`, `\t` theo quy ước escape Java | `translateEscapes()` | Chuyển ký hiệu escape thành ký tự tương ứng |
| Cần giữ một dấu cách cuối dòng trong text block | `\s` trong text block | Bảo toàn dấu cách tường minh |
| Muốn nối dòng trong text block mà không tạo newline | Backslash line continuation | Điều khiển nội dung literal khi biên dịch |
| Text block đã chứa newline/tab thật | Không cần dịch lại | Escape đã được xử lý khi biên dịch |
| Chuỗi có backslash trong đường dẫn hoặc biểu thức chính quy | Cẩn trọng với `translateEscapes()` | Dịch nhầm `\t`, `\n` hoặc escape khác có thể làm đổi dữ liệu |

### Ví dụ: SQL dễ đọc

```java
String sql = """
        SELECT id, full_name, email
        FROM users
        WHERE active = true
        ORDER BY full_name
        """;
```

Text block phù hợp vì nội dung có cấu trúc nhiều dòng và không cần tự ghép `"..." +`.

### Ví dụ: dữ liệu runtime được thụt lề

```java
String configText = readConfigText();
String normalized = configText.stripIndent();
```

Nếu file cấu hình chứa một đoạn được thụt lề đồng đều, `stripIndent()` có thể giúp chuẩn hóa trước khi parse. Cần bảo đảm định dạng file thực sự cho phép bỏ indentation; YAML, Python hoặc một số định dạng có thể dùng indentation mang ý nghĩa cú pháp, nên không áp dụng mù quáng.

### Ví dụ: chuỗi escape đến từ cấu hình

```java
String encodedMessage = readEncodedMessage();
String decodedMessage = encodedMessage.translateEscapes();
```

Chỉ dùng cách này nếu hợp đồng dữ liệu quy định escape theo Java. Nếu nguồn sử dụng JSON, URL encoding, HTML entity hoặc định dạng riêng, hãy dùng parser/decoder tương ứng thay vì mặc định dùng quy tắc escape Java.

## 10. Những nhầm lẫn thường gặp

### Nhầm 1 — Tưởng `stripIndent()` chỉ xóa khoảng trắng đầu toàn chuỗi

Không đúng. Nó xử lý **từng dòng**, dựa trên mức indentation chung của các dòng không trống. Nếu chỉ muốn bỏ khoảng trắng ở đầu và cuối toàn chuỗi, xem `strip()`.

### Nhầm 2 — Tưởng text block không tự xóa indentation

Không đúng. Text block đã xử lý incidental white space khi biên dịch. `stripIndent()` là phương thức runtime cho `String` nói chung, không phải một bước bắt buộc để text block hoạt động.

### Nhầm 3 — Tưởng `translateEscapes()` biến mọi dạng `\uXXXX` thành Unicode

Không đúng. Unicode escape được xử lý ở giai đoạn lexical của mã nguồn; `String.translateEscapes()` không dịch Unicode escape trong dữ liệu runtime.

### Nhầm 4 — Tưởng gọi `translateEscapes()` trên text block luôn an toàn

Không đúng. Text block đã dịch escape một lần. Nếu kết quả có backslash literal mà theo sau là chữ `t`, `n` hoặc một escape hợp lệ khác, lần dịch thứ hai có thể làm thay đổi nội dung.

### Nhầm 5 — Tưởng `\\s` và dấu cách thông thường giống nhau ở cuối dòng text block

Không đúng. Dấu cách cuối dòng trong source có thể bị loại bỏ theo quy tắc text block. `\\s` được dịch sau bước xử lý đó và giữ lại một dấu cách trong giá trị.

### Nhầm 6 — Tưởng thứ tự gọi hai phương thức không quan trọng

Không đúng. `translateEscapes()` có thể tạo line terminator mới; `stripIndent()` xử lý các dòng hiện có. Nếu dịch escape trước, tập hợp dòng mà `stripIndent()` nhìn thấy có thể khác.

### Nhầm 7 — Tưởng escape không hợp lệ sẽ được giữ nguyên

Không đúng. `translateEscapes()` ném `IllegalArgumentException` khi gặp escape không hợp lệ. Hãy xử lý lỗi theo hợp đồng dữ liệu nếu chuỗi đến từ nguồn bên ngoài.

### Nhầm 8 — Dùng `stripIndent()` với mọi định dạng nhiều dòng

Không nên. Có định dạng dùng indentation để biểu đạt cấu trúc, chẳng hạn YAML hoặc Python. Loại bỏ indentation có thể làm thay đổi ý nghĩa dữ liệu. Chỉ dùng khi định dạng cho phép thao tác đó.

## 11. Ví dụ hoàn chỉnh: xử lý text block và chuỗi runtime

Tạo file `TextProcessingDemo.java`:

```java
public class TextProcessingDemo {
    static void printVisibleSpaces(String label, String text) {
        System.out.println(label);
        System.out.println(text.replace(" ", "·"));
    }

    public static void main(String[] args) {
        // Text block tự xử lý indentation lúc biên dịch.
        String sql = """
                SELECT id, name
                FROM users
                WHERE active = true
                """;

        printVisibleSpaces("SQL:", sql);

        // stripIndent xử lý chuỗi nhiều dòng ở runtime.
        String indented =
                "    alpha\n" +
                "        beta\n" +
                "    gamma\n";

        String normalized = indented.stripIndent();
        printVisibleSpaces("Normalized:", normalized);

        // translateEscapes giải mã escape còn ở runtime.
        String encoded = "First\\nSecond\\tDone";
        String decoded = encoded.translateEscapes();
        printVisibleSpaces("Decoded:", decoded);

        // Không dịch lại text block có backslash path.
        String path = """
                C:\\temp\\new
                """;
        printVisibleSpaces("Path:", path);
    }
}
```

Biên dịch và chạy với JDK 17:

```bash
javac --release 17 TextProcessingDemo.java
java TextProcessingDemo
```

Các điểm cần quan sát:

- `sql` đã được căn lề tự động từ text block.
- `normalized` có indentation chung bị loại bỏ ở runtime.
- `decoded` có line feed và tab thật do `translateEscapes()` tạo ra.
- `path` giữ backslash literal; không gọi `translateEscapes()` lần hai để tránh dịch nhầm `\t` và `\n` trong tên thư mục.

## 12. Bài tập tự luyện

### Bài 1 — Dự đoán kết quả của `stripIndent()`

```java
String text =
        "    A\n" +
        "        B\n" +
        "    C\n";

System.out.println(text.stripIndent().replace(" ", "·"));
```

**Đáp án:** Mức thụt lề chung là bốn dấu cách. Kết quả có dạng:

```text
A
····B
C
```

### Bài 2 — Vì sao `translateEscapes()` ném ngoại lệ?

```java
String value = "Line\\q";
System.out.println(value.translateEscapes());
```

**Đáp án:** Giá trị runtime chứa `\q`, không phải escape sequence hợp lệ. `translateEscapes()` ném `IllegalArgumentException`. Nếu muốn hiển thị backslash và chữ q như dữ liệu thông thường, không gọi phương thức dịch escape.

### Bài 3 — Text block có cần `translateEscapes()` không?

```java
String text = """
        A\nB
        """;
```

**Đáp án:** Không. Trong text block, `\n` đã được dịch lúc biên dịch thành một line feed thật. Giá trị `text` có hai dòng `A` và `B`. Gọi `translateEscapes()` lần nữa không phải bước cần thiết.

### Bài 4 — Giữ khoảng trắng cuối dòng

Hãy viết text block chứa dòng `"Name: "` với đúng một dấu cách ở cuối, rồi đến dòng `"Value"`.

Một cách viết:

```java
String text = """
        Name:\s
        Value
        """;
```

`\s` tạo một dấu cách tường minh sau dấu hai chấm; dấu cách này được giữ trong giá trị.

### Bài 5 — Chọn thứ tự xử lý

Chuỗi runtime có nội dung `"    A\\n    B"`, trong đó `\n` là hai ký tự backslash và n. Nếu muốn tạo hai dòng rồi loại bỏ indentation chung, dùng:

```java
String result = encoded.translateEscapes().stripIndent();
```

Nếu gọi `stripIndent()` trước khi dịch `\n`, phương thức chỉ nhìn thấy một dòng và không thể loại bỏ indentation chung của hai dòng mà escape biểu diễn.

## 13. Ghi nhớ

- **Text block** là cú pháp literal nhiều dòng; Java tự loại bỏ incidental indentation và dịch escape khi biên dịch.
- **`stripIndent()`** là thao tác runtime trên `String`; nó loại bỏ indentation chung của các dòng và xử lý whitespace cuối dòng.
- **`translateEscapes()`** là thao tác runtime; nó dịch các escape sequence Java hợp lệ còn nằm trong chuỗi, không dịch Unicode escape.
- Text block đã xử lý escape; không gọi `translateEscapes()` lại nếu không có nhu cầu rõ ràng.
- Thứ tự `translateEscapes()` và `stripIndent()` có thể thay đổi kết quả vì dịch `\n` tạo thêm dòng thật.
- Dùng `\s` trong text block khi cần giữ dấu cách cuối dòng; dùng backslash line continuation khi muốn nối hai dòng source mà không thêm newline.
- Chỉ loại bỏ indentation khi định dạng dữ liệu cho phép; whitespace có thể mang ý nghĩa trong YAML, Python, SQL literal hoặc dữ liệu theo cột.

## Tài liệu tham khảo chính thức cho Java 17

- [Java Language Specification 17 — `3.10.6`: Text Blocks](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6).
- [Java Language Specification 17 — `3.10.7`: Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7).
- [Java SE 17 API — `String.stripIndent()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#stripIndent()).
- [Java SE 17 API — `String.translateEscapes()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#translateEscapes()).
- [JEP 378 — Text Blocks (Final)](https://openjdk.org/jeps/378).
- [JEP 355 — Text Blocks (Preview history)](https://openjdk.org/jeps/355).

