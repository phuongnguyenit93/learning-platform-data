# Escape xuống dòng để nối các dòng nguồn trong text block (Java 15+)

## Mục tiêu và phạm vi

Bài học này tập trung vào **line-continuation escape** (escape nối dòng nguồn) trong *text block* của Java: viết dấu backslash `\` ngay trước ký tự kết thúc dòng trong mã nguồn để **bỏ dấu xuống dòng đó khỏi giá trị `String`**. Sau khi học, bạn sẽ dự đoán được chuỗi kết quả, phân biệt nó với `\n` và `\\`, chủ động quản lý dấu cách/lề, cũng như tránh vô tình làm thay đổi payload hoặc dữ liệu kiểm thử.

Tính năng text block cùng hai escape bổ sung `\s` và `\` theo sau bởi line terminator đã trở thành tính năng **chính thức từ Java 15 (JEP 378)** và tiếp tục áp dụng trong Java hiện đại. Ví dụ hoàn chỉnh ở dưới chạy với **JDK 17 trở lên**, không cần bật preview.

## 1. Ý nghĩa của escape nối dòng nguồn

Khi text block có các dòng bình thường, dấu xuống dòng trong nội dung thường trở thành ký tự `\n` ở `String`. Nếu cần trình bày một dòng văn bản dài trên **nhiều dòng mã Java** nhưng **không muốn giữ dấu xuống dòng** tại điểm ngắt nguồn, đặt `\` ở ngay cuối dòng nội dung:

```java
String phrase = """
        Hello, \
        Java!\
        """;

System.out.println(phrase.equals("Hello, Java!")); // true
```

Kết quả là chuỗi `Hello, Java!`; không có ký tự `\` hay `\n` ở điểm nối. Dấu cách giữa hai từ được giữ **vì có một dấu cách trước backslash** ở dòng đầu: `Hello, \`. Dấu `\` sau `Java!` còn loại bỏ dấu xuống dòng ngay trước dòng chứa dấu đóng `"""`.

Trong tài liệu Java, cú pháp này thường được viết là **`\` + `LineTerminator`**. `LineTerminator` là ký tự kết thúc dòng thực của tệp nguồn (LF, CR hoặc CRLF), không phải hai ký tự in được `\` và `n`.

### So sánh cùng một nội dung

```java
String normal = """
        Hello,
        Java!
        """;
// Giá trị: "Hello,\nJava!\n"

String joined = """
        Hello,\
        Java!\
        """;
// Giá trị: "Hello,Java!"

String withSpace = """
        Hello, \
        Java!\
        """;
// Giá trị: "Hello, Java!"
```

**Điểm cần nhớ:** `\` ở cuối dòng **chỉ xóa backslash và ký tự kết thúc dòng đó**. Nó **không tự chèn khoảng trắng**, dấu phẩy hoặc bất kỳ dấu ngăn cách nào. Ký tự còn lại ở hai phía được ghép liền theo đúng giá trị sau khi Java xử lý lề.

## 2. Cú pháp hợp lệ và điều kiện sử dụng

Một text block bắt đầu bằng ba dấu nháy kép `"""`, theo sau là ký tự xuống dòng; dấu đóng cũng là `"""`. Bên trong nội dung, đặt backslash ngay trước *dấu xuống dòng thực*:

```java
String oneLine = """
        Phần thứ nhất \
        tiếp nối ở dòng sau.\
        """;
```

Để dễ kiểm soát, hãy đặt `\` làm ký tự cuối cùng của dòng, **không thêm dấu cách hoặc chú thích sau nó**. Nếu một ký tự khác xen giữa backslash và xuống dòng, không thể dựa vào ý định nối dòng như cách viết bên trên; một số chuỗi escape không hợp lệ còn gây lỗi biên dịch. Công cụ tự động thêm/xóa whitespace cuối dòng có thể ảnh hưởng đến cách đọc mã nguồn, nên ví dụ nối dòng phải nhìn rõ vị trí của `\`.

**Không áp dụng kiểu viết này cho string literal một dòng truyền thống:**

```java
// KHÔNG HỢP LỆ: literal "..." không được chứa line terminator thực.
String invalid = "Hello, \
Java!";
```

Với literal thông thường, dùng `+` để nối các chuỗi Java hoặc dùng `\n` nếu thật sự muốn ký tự xuống dòng:

```java
String concatenated = "Hello, " +
                      "Java!";
String twoLines = "Hello,\nJava!";
```

Đoạn `invalid` phía trên **chỉ minh họa cú pháp sai**, không đặt chung vào tệp Java để biên dịch. Các mã khác trong bài đều có thể dùng trong phương thức Java phù hợp.

## 3. Phân biệt ba dạng backslash thường nhầm lẫn

| Cách viết trong mã Java | Ý nghĩa khi tạo `String` | Có ký tự xuống dòng trong giá trị không? |
| --- | --- | --- |
| Dòng nội dung text block kết thúc bình thường | Dấu kết thúc dòng thực được giữ thành `\n` (LF) | Có |
| `\` ngay trước dấu kết thúc dòng nguồn trong text block | Escape nối dòng: bỏ cả backslash lẫn line terminator | Không, tại vị trí ấy |
| `\n` (hai ký tự nguồn `\` và `n`) | Escape tạo **một** ký tự LF trong chuỗi | Có |
| `\\` | Escape tạo **một** ký tự backslash thực | Không |
| `\s` | Escape tạo **một** dấu cách (space) thực | Không |

Ví dụ tách biệt cách viết `\n` và escape nối dòng:

```java
String actualNewline = """
        A\nB\
        """;
System.out.println(actualNewline.equals("A\nB")); // true

String noNewline = """
        A\
        B\
        """;
System.out.println(noNewline.equals("AB")); // true
```

Ở ví dụ thứ nhất, `\n` sinh ra LF trong chuỗi, còn `\` ở cuối dòng `B` chỉ bỏ newline cuối. Ở ví dụ thứ hai, cả hai dấu xuống dòng nguồn đều bị loại nên `A` và `B` dính liền.

**Đừng nhầm với `\\n`:** chuỗi Java chứa `\\n` là ký tự backslash rồi đến chữ `n`, không phải LF. Nếu bạn tạo một ví dụ JSON hay dữ liệu để kiểm tra escape, phải phân biệt văn bản nhìn thấy và các ký tự thực được lưu.

## 4. Escape nối dòng tương tác với khoảng trắng như thế nào?

Java không sinh ra một dấu cách tại vị trí nối. Vì thế, bạn cần **chủ động quyết định** có muốn giữ khoảng cách giữa các mảnh hay không.

### 4.1. Nối sát hai mảnh

```java
String token = """
        java\
        text\
        block\
        """;

System.out.println(token.equals("javatextblock")); // true
```

Phù hợp khi bạn đang chia một token hoặc một chuỗi cố định rất dài chỉ để mã nguồn dễ đọc.

### 4.2. Giữ khoảng cách giữa các từ

```java
String sentence = """
        Lorem ipsum dolor sit amet, \
        consectetur adipiscing elit.\
        """;

System.out.println(sentence.equals(
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.")); // true
```

Dấu cách trước `\` đứng **giữa các ký tự không phải whitespace cuối dòng** nên được giữ trong giá trị sau khi bỏ line terminator. Nếu bỏ dấu cách đó, hai từ cuối/đầu dòng sẽ ghép trực tiếp.

Bạn cũng có thể dùng escape `\s` cho khoảng trắng có chủ đích:

```java
String message = """
        Please\s\
        continue\
        """;

System.out.println(message.equals("Please continue")); // true
```

Ở đây `\s` tạo một dấu cách, còn `\` nối sang dòng tiếp theo. Cách viết này có ích khi muốn làm dấu cách được giữ lại rõ ràng, nhất là ở các ví dụ cần đối chiếu chính xác ký tự.

### 4.3. Lề tương đối của dòng sau vẫn quan trọng

```java
String indentedJoin = """
        A\
          B\
        """;

System.out.println(indentedJoin.equals("A  B")); // true
```

Java loại bỏ phần lề chung của text block trước khi dịch escape. Dòng chứa `B` được thụt vào **thêm hai dấu cách** so với mức lề chung, vì thế hai dấu cách này trở thành nội dung chuỗi. Khi bỏ newline bởi `\`, kết quả là `"A  B"`, không phải `"AB"`.

**Quy tắc thực hành:** trước khi dự đoán một text block có `\`, hãy xác định nội dung sau khi chuẩn hóa dòng và bỏ lề chung, rồi mới xóa các cặp `\` + line terminator.

## 5. Mối liên hệ với dấu xuống dòng ở cuối text block

Khi dấu đóng `"""` nằm trên một dòng riêng, dòng nội dung cuối thường có `\n`:

```java
String withFinalNewline = """
        line one
        line two
        """;

System.out.println(withFinalNewline.equals("line one\nline two\n")); // true
```

Nếu không muốn ký tự `\n` cuối cùng, có thể đặt `\` ngay cuối dòng nội dung cuối:

```java
String withoutFinalNewline = """
        line one
        line two\
        """;

System.out.println(withoutFinalNewline.equals("line one\nline two")); // true
```

Hoặc đặt dấu đóng ngay sau nội dung cuối:

```java
String closingOnSameLine = """
        line one
        line two""";

System.out.println(closingOnSameLine.equals("line one\nline two")); // true
```

Hai cách đều có thể bỏ newline cuối trong trường hợp này, nhưng **vị trí dấu đóng còn ảnh hưởng quy tắc xử lý lề**, nên không mặc định các biến thể luôn cho cùng chuỗi ở mọi bố cục. Dùng `\` cuối dòng khi muốn dấu đóng riêng một dòng mà chuỗi kết quả không có newline cuối.

Nếu đầu ra được so sánh từng byte (payload, snapshot, chuỗi ký số), một ký tự `\n` ngoài ý muốn vẫn là khác biệt thật; đừng dựa vào `println()` để phát hiện vì việc in chuỗi có thể tạo thêm dấu xuống dòng riêng.

## 6. Vì sao Java xử lý theo thứ tự nào?

Theo Java Language Specification, nội dung text block được xử lý theo thứ tự:

1. **Chuẩn hóa dòng:** CRLF hoặc CR trong nguồn được quy về LF (`\n`).
2. **Bỏ khoảng trắng phụ:** xử lý common indentation và trailing whitespace tương tự `String.stripIndent()`.
3. **Dịch escape:** xử lý như `String.translateEscapes()`, trong đó escape `\` + line terminator được thay bằng **chuỗi rỗng**.

Do escape được xử lý **sau khi bỏ lề**, phần lề phụ tương đối của dòng phía sau vẫn có thể tồn tại khi nối hai dòng. Và do `\s` chỉ biến thành một dấu cách tại bước cuối, nó có thể dùng để giữ dấu cách mà bình thường quá trình bỏ trailing whitespace sẽ loại đi.

Việc chuẩn hóa newline cũng giúp hành vi này nhất quán giữa tệp nguồn dùng LF và CRLF: escape nối dòng luôn loại bỏ terminator tương ứng; nếu còn newline thường trong nội dung thì kết quả text block chứa LF. Dấu `\` dùng để nối dòng **không giống** việc thay toàn bộ newline của chuỗi bằng `String.replace("\n", "")`: nó chỉ tác động ở những vị trí đã chọn trong mã nguồn.

## 7. Ví dụ thực tế: giữ nội dung một dòng dài dễ đọc

Giả sử bạn cần khai báo một thông báo cố định dài, xuất ra thành một dòng mà vẫn muốn chia mã nguồn để dễ review:

```java
String notice = """
        Your session will expire soon; \
        save your work before continuing.\
        """;
```

Giá trị chính xác là:

```text
Your session will expire soon; save your work before continuing.
```

Không có newline cuối. Trong trường hợp nội dung thuộc JSON, HTML hoặc SQL có tham số động, escape nối dòng chỉ hỗ trợ trình bày mã; nó **không** thay thế serializer, HTML escaping hoặc bind tham số SQL. Nếu cần giữ các dòng mới thật sự (ví dụ thông báo nhiều đoạn, truy vấn SQL dễ đọc), đừng nối chúng một cách không cần thiết.

Một đoạn SQL minh họa khi cần chia dòng dài trong mã nhưng câu lệnh lưu được ghép đúng:

```java
String sql = """
        SELECT id, title FROM books \
        WHERE category_id = ? \
        ORDER BY title\
        """;
```

Giá trị là một dòng `SELECT id, title FROM books WHERE category_id = ? ORDER BY title`. Khi chạy với giá trị người dùng, dùng `PreparedStatement` để bind tham số; không ghép dữ liệu không tin cậy trực tiếp vào `String`.

## 8. Chương trình hoàn chỉnh và stdout chính xác

Tạo tệp **`LineContinuationDemo.java`** bằng UTF-8:

```java
public class LineContinuationDemo {
    public static void main(String[] args) {
        String joined = """
                Lorem ipsum dolor sit amet, \
                consectetur adipiscing elit.\
                """;

        String touching = """
                java\
                text\
                block\
                """;

        String withFinalNewline = """
                line one
                line two
                """;

        String withoutFinalNewline = """
                line one
                line two\
                """;

        String withSpace = """
                Please\s\
                continue\
                """;

        String withRelativeIndent = """
                A\
                  B\
                """;

        System.out.println("joined=" + joined.equals(
                "Lorem ipsum dolor sit amet, consectetur adipiscing elit."));
        System.out.println("touching=" + touching.equals("javatextblock"));
        System.out.println("finalNewline="
                + withFinalNewline.endsWith("\n"));
        System.out.println("noFinalNewline=" + withoutFinalNewline.equals(
                "line one\nline two"));
        System.out.println("space=" + withSpace.equals("Please continue"));
        System.out.println("relativeIndent="
                + withRelativeIndent.equals("A  B"));
    }
}
```

Biên dịch và chạy bằng JDK 17+ (text block chính thức từ Java 15):

```bash
javac -encoding UTF-8 LineContinuationDemo.java
java LineContinuationDemo
```

**Stdout chính xác:**

```text
joined=true
touching=true
finalNewline=true
noFinalNewline=true
space=true
relativeIndent=true
```

Kết quả chứng minh: (1) ghép hai đoạn có dấu cách chủ động, (2) nối sát không tạo separator, (3) newline cuối tồn tại khi không có escape, (4) escape cuối bỏ newline, (5) `\s` giữ dấu cách, và (6) lề tương đối của dòng kế tiếp có thể trở thành nội dung sau khi nối. Cách đối chiếu bằng `equals()` giúp nhìn ra chính xác những ký tự khó thấy.

## 9. Các lỗi thường gặp

| Hiện tượng | Giải thích | Cách xử lý |
| --- | --- | --- |
| Muốn `"Hello, Java!"` nhưng được `"Hello,Java!"` | Escape nối dòng xóa newline, không chèn dấu cách | Thêm dấu cách trước `\` hoặc dùng `\s\` |
| Muốn một dòng nhưng chuỗi vẫn có `\n` | Một dòng nội dung không có `\` ở điểm ngắt nguồn | Chỉ thêm `\` ở đúng những dòng cần nối |
| Kết quả có thêm khoảng trắng không rõ lý do | Dòng sau chứa lề *tương đối* được giữ sau `stripIndent` | Kiểm tra lề các dòng và vị trí dấu đóng |
| Kết quả khác ở cuối chuỗi | Thiếu/thừa newline trước dấu đóng | Kiểm tra `endsWith("\n")` và vị trí `\` cuối |
| Tưởng `\n` giúp nối dòng | `\n` lại tạo newline LF trong chuỗi | Dùng backslash rồi xuống dòng nguồn thực khi muốn bỏ newline |
| Thấy `\` xuất hiện trong kết quả | Đã viết `\\`, là escape ký tự backslash | Phân biệt `\\` với `\` + line terminator |
| Text block không biên dịch | Viết nội dung ngay sau dấu mở `"""` hoặc viết escape lỗi | Đặt newline ngay sau dấu mở, kiểm tra chuỗi escape |
| String literal `"..."` bị lỗi khi xuống dòng nguồn | String literal truyền thống không cho chứa line terminator thực | Dùng nối literal bằng `+` hoặc chuyển sang text block |
| Nội dung một dòng bị ghép sai token khi chia nguồn | Vị trí `\` quá sát từ/ký hiệu, thiếu separator | Dự đoán toàn bộ chuỗi và thêm phép kiểm tra `equals` |

Ngoài ra, đừng cố dùng `\` nối dòng như công cụ để “sửa mọi whitespace”. Escape này phục vụ trường hợp **ngắt dòng phục vụ việc đọc mã nguồn**; nếu bạn thật sự cần xử lý chuỗi động, hãy dùng API như `String.join(...)` hoặc `StringBuilder`.

### Cách tự kiểm tra trong dự án

- Đặt văn bản mong đợi bên trong một assertion, chẳng hạn `expected.equals(actual)`, đặc biệt nếu dữ liệu nhạy với dấu cách/newline.
- So sánh `length()` hoặc chuyển nội dung thành biểu diễn nhìn thấy khi có nghi ngờ ký tự ẩn.
- Giữ cấu hình định dạng mã nhất quán để việc tự động thay lề không vô tình thay đổi nội dung thực của text block.
- Nếu định dạng đầu ra quy định CRLF, xử lý rõ ràng khi xuất tệp/dữ liệu; text block chuẩn hóa newline thông thường thành LF.

## 10. Bài tập tự kiểm tra

**Bài 1.** Đoán kết quả:

```java
String value = """
        A\
        B\
        C\
        """;
```

Đáp án: `"ABC"`; không có newline cuối.

**Bài 2.** Đoán độ dài chuỗi:

```java
String value = """
        Hi \
        Java\
        """;
```

Đáp án: `7` ký tự, tương ứng `"Hi Java"` (hai ký tự `Hi`, một space, bốn ký tự `Java`).

**Bài 3.** Sửa text block sau để nhận `"one two"` mà vẫn đặt dấu đóng ở dòng riêng:

```java
String value = """
        one\
        two
        """;
```

Một lời giải là chèn dấu cách trước `\` ở dòng `one` và chèn `\` ở dòng `two` để bỏ newline cuối:

```java
String value = """
        one \
        two\
        """;
```

**Bài 4.** Giải thích vì sao không nên dùng `\` để nối tất cả dòng trong JSON nhiều dòng. Đáp án: nó sẽ loại bỏ newline đúng tại các điểm nối, khiến bố cục chuỗi thay đổi; riêng JSON vẫn cần hợp lệ về cú pháp, dấu phẩy, dấu cách, và nội dung động cần serializer. Nối dòng chỉ nên dùng tại vị trí đã hiểu tác động đến giá trị.

## Ghi nhớ

Escape `\` **đặt ngay trước dấu xuống dòng nguồn** trong text block sẽ bỏ chính backslash và dấu xuống dòng đó, giúp chia mã Java thành nhiều dòng mà tạo chuỗi liền mạch. Java không thêm dấu cách tự động, lề tương đối vẫn có thể được giữ, và `\n` là escape **tạo newline**, trái với nối dòng. Khi xử lý text block, hãy luôn suy xét ba giai đoạn: **chuẩn hóa newline → bỏ lề/khoảng trắng phụ → dịch escape**.

### Tài liệu chính thức

- [OpenJDK JEP 378 – Text Blocks](https://openjdk.org/jeps/378)
- [Oracle Programmer's Guide to Text Blocks – New Escape Sequences](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html)
- [Java Language Specification, mục 3.10.6 (Text Blocks)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6)
- [Java Language Specification, mục 3.10.7 (Escape Sequences)](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.7)
