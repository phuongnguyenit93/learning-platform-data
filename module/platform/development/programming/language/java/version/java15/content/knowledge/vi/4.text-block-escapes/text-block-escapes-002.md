# Dấu gạch chéo ngược và đường dẫn trong Java text block

## 1. Vấn đề cốt lõi: text block không phải chuỗi “raw”

Từ **Java 15**, text block (`""" ... """`) là cú pháp chuẩn để viết `String` nhiều dòng. Nó giúp đọc văn bản dễ hơn, nhưng **không làm mất ý nghĩa đặc biệt của dấu gạch chéo ngược** (`\`). Bên trong text block, Java vẫn xử lý escape sequence như trong string literal `"..."` thông thường. Vì thế, muốn tạo **một dấu `\` thật trong giá trị chuỗi**, phải viết **`\\` trong mã nguồn Java**.

Đây là điểm dễ gây lỗi khi nhúng đường dẫn Windows, đường dẫn mạng UNC, mẫu regex hoặc JSON vào text block. Ví dụ, ký tự `\` trước chữ `n` có thể tạo **xuống dòng**, còn trước chữ `t` có thể tạo **tab**, thay vì giữ nguyên hai ký tự thuộc tên đường dẫn.

Trong bài này, cần phân biệt ba tầng:

1. **Mã nguồn Java:** những ký tự lập trình viên gõ, ví dụ `"C:\\data\\file.txt"`.
2. **Giá trị `String` khi chương trình chạy:** ký tự thực sự có trong bộ nhớ, ví dụ `C:\data\file.txt` (mỗi dấu `\` ở đây là một ký tự).
3. **Cách một hệ thống khác diễn giải chuỗi đó:** `Path`, regex engine hay JSON parser có quy tắc riêng; Java text block không tự xử lý thay chúng.

**Nguyên tắc:** Việc một chuỗi trông giống đường dẫn không khiến Java tự tắt escape. Không dùng text block với kỳ vọng rằng mọi dấu `\` sẽ được giữ nguyên.

## 2. `\\` vẫn là cách ghi một dấu backslash

Các escape dưới đây đều có ý nghĩa trong **text block** lẫn **string literal** Java.

| Ký tự trong **mã nguồn Java** | Ký tự thực sự trong `String` | Hệ quả với đường dẫn |
| --- | --- | --- |
| `\\` | Một dấu `\` | Cách viết đúng khi cần dấu phân cách Windows trong literal. |
| `\n` | Một ký tự xuống dòng LF | Tên/đường dẫn bị chèn xuống dòng ngoài ý muốn. |
| `\t` | Một ký tự tab | Đường dẫn bị chèn tab ngoài ý muốn. |
| `\r` | Một ký tự carriage return | Có thêm ký tự điều khiển, khó nhận ra khi in. |
| `\b` | Một ký tự backspace | Không phải ký tự `\` và `b` trong tên đường dẫn. |
| `\f` | Một ký tự form feed | Không phải dấu `\` theo sau chữ `f`. |
| `\s` | Một dấu cách U+0020 | Không tạo ra `\`; đôi khi dùng để giữ khoảng trắng cuối dòng. |
| `\` ngay trước dấu xuống dòng *thực* | Không thêm ký tự xuống dòng tại vị trí đó | Đây là **line continuation** trong text block. |

Một backslash đứng trước các chữ không tạo escape hợp lệ, ví dụ `\p` hoặc `\D`, có thể dẫn đến lỗi biên dịch `illegal escape character`. Đặc biệt, `\u` còn liên quan đến xử lý Unicode escape ở bước đọc mã nguồn, vì vậy đường dẫn như `C:\users` càng không thể gõ nguyên một dấu `\` rồi mong được giữ lại.

Lưu ý: Trong text block, dấu nháy kép đơn lẻ `"` thường không cần escape, nhưng **dấu backslash vẫn cần**. Java xử lý nội dung text block theo thứ tự: chuẩn hóa xuống dòng nguồn về LF → loại lề chung và khoảng trắng cuối dòng → diễn giải escape. Điều này giải thích vì sao escape `\\` được chuyển thành một backslash trong giá trị cuối cùng.

## 3. Đường dẫn Windows: viết giống nhau trong hai loại literal

Giả sử giá trị mong muốn khi chương trình chạy là:

```text
C:\Users\Lan\Documents\report.txt
```

Với string literal một dòng:

```java
String literal = "C:\\Users\\Lan\\Documents\\report.txt";
```

Với text block, **vẫn phải viết hai dấu backslash** cho mỗi dấu cần giữ, và có thể đặt dấu đóng `"""` trên cùng dòng nội dung cuối để không thêm LF:

```java
String block = """
        C:\\Users\\Lan\\Documents\\report.txt""";

System.out.println(literal.equals(block)); // true
```

Các khoảng trắng thụt đầu dòng trong mã nguồn được Java bỏ phần lề chung. Giá trị thực tế của cả hai biến có **bốn dấu backslash**, không có khoảng trắng thụt đầu và không có dấu xuống dòng cuối.

Khi chuỗi chỉ có **một dòng ngắn**, string literal thường rõ ràng hơn text block. Text block có ích chủ yếu khi cần một đoạn nhiều dòng, ví dụ nhiều đường dẫn hoặc một mẫu cấu hình lớn.

### 3.1. Lỗi âm thầm với `\n` và `\t`

Đoạn sau **vẫn có thể biên dịch**, nhưng **không mang giá trị đường dẫn tác giả muốn**:

```java
String wrong = """
        D:\new\test""";
```

Java diễn giải `\n` thành LF và `\t` thành tab. Giá trị vì thế không chứa đường dẫn nguyên văn `D:\new\test`. Đây là loại lỗi nguy hiểm hơn lỗi biên dịch vì mã có thể chạy nhưng tạo đường dẫn sai.

Viết đúng:

```java
String correct = """
        D:\\new\\test""";

System.out.println(correct.equals("D:\\new\\test")); // true
```

Ngược lại, một đoạn như `C:\Program Files` có thể bị Java báo lỗi biên dịch vì `\P` không phải escape hợp lệ. Cả hai trường hợp đều có cùng cách phòng tránh: **dùng `\\` cho backslash xuất hiện trong mã nguồn Java**.

### 3.2. Đường dẫn mạng UNC cần hai backslash thật ở đầu

Trên Windows, một đường dẫn mạng có thể bắt đầu bằng **hai dấu `\`**:

```text
\\server\share\file.txt
```

Trong mã nguồn Java, hai dấu backslash đầu giá trị phải được biểu diễn bằng **bốn dấu**:

```java
String unc = """
        \\\\server\\share\\file.txt""";

System.out.println(unc.equals("\\\\server\\share\\file.txt")); // true
```

Đếm theo cặp: `\\\\` trong mã nguồn trở thành `\\` trong giá trị; mỗi `\\` ở phần còn lại trở thành một `\`. Nếu vô tình chỉ viết `\\server` ở đầu mã nguồn, giá trị chỉ còn **một** `\` ban đầu và không giữ đúng dạng UNC.

## 4. Ví dụ Java đầy đủ, chạy được từ Java 15+

Lưu thành **`TextBlockBackslashPaths.java`**. Chương trình không truy cập hệ thống tệp nên có thể kiểm tra **nội dung chuỗi** trên cả Windows, Linux và macOS.

```java
public class TextBlockBackslashPaths {
    public static void main(String[] args) {
        String literal = "C:\\Users\\Lan\\Documents\\report.txt";
        String block = """
                C:\\Users\\Lan\\Documents\\report.txt""";

        String withFinalNewline = """
                C:\\Users\\Lan\\Documents\\report.txt
                """;

        String mistaken = """
                D:\new\test""";

        String unc = """
                \\\\server\\share\\file.txt""";

        String twoPaths = """
                C:\\data\\a.txt
                C:\\data\\b.txt
                """;

        System.out.println("same=" + literal.equals(block));
        System.out.println(
                "slashes=" + block.chars()
                        .filter(c -> c == '\\')
                        .count()
        );
        System.out.println(
                "hasTrailingLF=" + withFinalNewline.endsWith("\n")
        );
        System.out.println(
                "wrongContainsLF=" + (mistaken.indexOf('\n') >= 0)
        );
        System.out.println(
                "wrongContainsTab=" + (mistaken.indexOf('\t') >= 0)
        );
        System.out.println(
                "unc=" + unc.equals("\\\\server\\share\\file.txt")
        );
        System.out.println("paths=" + twoPaths.lines().count());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên (text block đã là tính năng chính thức từ Java 15; **không cần cờ preview**):

```bash
javac -encoding UTF-8 TextBlockBackslashPaths.java
java TextBlockBackslashPaths
```

Đầu ra chính xác:

```text
same=true
slashes=4
hasTrailingLF=true
wrongContainsLF=true
wrongContainsTab=true
unc=true
paths=2
```

Giải thích kết quả:

- `same=true`: string literal và text block tạo cùng một dãy ký tự, kiểm tra bằng `String.equals`.
- `slashes=4`: mỗi `\\` trong mã nguồn tạo một `\` ở giá trị, đúng bốn dấu phân cách của đường dẫn ví dụ.
- `hasTrailingLF=true`: khi dấu đóng ở dòng riêng, dấu xuống dòng sau nội dung cũng thuộc `String`.
- `wrongContainsLF=true` và `wrongContainsTab=true`: nguồn viết sai đã bị diễn giải thành ký tự điều khiển.
- `unc=true`: text block tạo chính xác hai backslash mở đầu của đường dẫn mạng UNC.
- `paths=2`: `String.lines()` đọc hai dòng đường dẫn từ text block và không tạo thêm một dòng rỗng chỉ vì có LF kết thúc.

Hãy phân biệt việc **chuỗi đã được tạo đúng** với việc **đường dẫn có tồn tại**. Chương trình này chỉ kiểm tra nội dung `String`; nó không khẳng định các đường dẫn Windows có tồn tại trên máy đang chạy.

## 5. Dấu backslash ở cuối dòng: hai ý nghĩa hoàn toàn khác

Trong text block, dấu `\` ngay trước **xuống dòng vật lý của mã nguồn** là cú pháp **line continuation**: Java loại bỏ xuống dòng đó khỏi giá trị. Đây **không phải** cách ghi một dấu backslash cuối đường dẫn.

Ví dụ, xét biểu thức minh họa đặt trong một phương thức:

```java
String joined = """
        C:\\temp\\\
        log.txt""";

System.out.println(
        joined.equals("C:\\temp\\log.txt")
); // true
```

Phân tích phần cuối của dòng đầu: có **ba** dấu backslash liên tiếp trong mã nguồn. Hai dấu đầu (`\\`) trở thành **một** dấu backslash thật; dấu thứ ba cùng xuống dòng thực phía sau là **line continuation**, nên `log.txt` nối liền ngay sau dấu `\`. Kết quả là một đường dẫn một dòng: `C:\temp\log.txt`.

Tuy hợp lệ, cách viết này khó đếm dấu backslash, vì vậy khi chỉ có một đường dẫn hãy ưu tiên string literal một dòng `"C:\\temp\\log.txt"` hoặc text block với dấu đóng ở ngay cuối dòng nội dung.

Nếu cuối dòng nguồn có **hai** backslash (`\\`) rồi xuống dòng thực, hai dấu đó là escape cho **một backslash thật**; chúng **không** tự xóa xuống dòng. Cần đọc riêng từng cặp escape và dấu xuống dòng sau chúng.

### 5.1. Đừng vô tình thêm `\n` cuối đường dẫn

Hai giá trị này không giống nhau:

```java
String oneLine = """
        C:\\data\\report.txt""";

String endsWithLf = """
        C:\\data\\report.txt
        """;

System.out.println(oneLine.endsWith("\n"));   // false
System.out.println(endsWithLf.endsWith("\n")); // true
```

Dấu LF cuối có thể làm thao tác xử lý đường dẫn thất bại. Đặt dấu đóng `"""` ngay sau ký tự nội dung cuối khi muốn chuỗi không có `\n` cuối; nếu chủ đích giữ LF, đặt dấu đóng ở dòng riêng. Không nên tùy tiện gọi `trim()` hoặc `strip()` để sửa mọi chuỗi, vì chúng còn có thể xóa khoảng trắng thật trong dữ liệu.

### 5.2. Nhiều đường dẫn: ứng dụng phù hợp của text block

Khi cần danh sách gồm nhiều dòng, text block giúp thể hiện bố cục rõ ràng:

```java
String pathList = """
        C:\\data\\input.csv
        C:\\data\\output.csv
        """;

for (String pathText : pathList.lines().toList()) {
    System.out.println(pathText);
}
```

Đầu ra hiển thị:

```text
C:\data\input.csv
C:\data\output.csv
```

`String.lines()` trả về các dòng đã bỏ dấu kết thúc dòng, nên mỗi phần tử ở đây là một chuỗi đường dẫn riêng, **không** mang LF cuối. Ví dụ này chỉ xử lý văn bản; nếu cần mở tệp, hãy biến các giá trị hợp lệ thành `Path` theo quy tắc của hệ điều hành hiện tại.

## 6. Khi nên dùng `Path` thay vì tự ghép chuỗi đường dẫn

Backslash trong mã nguồn và dấu phân cách của hệ điều hành là hai vấn đề khác nhau. Trong Java hiện đại, khi thao tác với hệ thống tệp, thường nên dùng **`java.nio.file.Path`** và `Files`:

```java
import java.nio.file.Path;

Path relative = Path.of("data", "reports", "2026.txt");
System.out.println(relative.getNameCount()); // 3
```

`Path.of` ghép các **thành phần** theo file system của máy đang chạy. Ta không phải tự viết `"data\\reports\\2026.txt"` hoặc `"data/reports/2026.txt"` khi xây một đường dẫn tương đối gồm ba thành phần.

Nếu dữ liệu thực sự là đường dẫn Windows tuyệt đối do chương trình dùng trên Windows, có thể viết:

```java
Path windowsPath = Path.of("C:\\Users\\Lan\\Documents\\report.txt");
```

Nhưng **`Path.of` không có chức năng “gỡ escape Java”**. Khi chương trình chạy, nó nhận giá trị `String` đã được trình biên dịch xử lý; nếu chuỗi chứa LF/tab do gõ sai `\n`/`\t` thì `Path.of` không thể đoán rằng bạn vốn muốn backslash.

Cũng không nên nhầm việc chương trình Java chạy trên Unix với việc đang dùng đường dẫn Windows: `Path.of("C:\\data\\file.txt")` được phân tích theo file system hiện hành, nên trên Unix không mang cùng ngữ nghĩa đường dẫn Windows. Dùng `Path` để thao tác với **file system hiện tại**; khi chỉ cần lưu, trao đổi, hiển thị một chuỗi đường dẫn của nền tảng khác, hãy giữ nó như dữ liệu chuỗi hoặc dùng cơ chế phân tích riêng phù hợp.

**Một lưu ý quan trọng về dữ liệu nhận lúc chạy:** nếu người dùng nhập `C:\data\file.txt` hay ứng dụng đọc giá trị đó từ tệp cấu hình ở dạng **văn bản thực tế**, Java **không xử lý lại Java source escape** cho giá trị `String` đã có. Cần hai backslash `\\` chỉ khi *viết literal bên trong mã nguồn Java*. Không tự nhân đôi backslash trong đường dẫn đã đọc vào bộ nhớ nếu không có yêu cầu định dạng khác.

## 7. Khi có nhiều lớp escape: JSON và regex

Ngoài đường dẫn, một số trường hợp khiến người học tưởng rằng text block tự bỏ escape. Thực tế có thể cần **nhiều lần escape cho nhiều bộ phân tích khác nhau**.

### 7.1. Đường dẫn nằm trong văn bản JSON

JSON sử dụng dấu `\` làm ký tự escape của **riêng JSON**. Để chuỗi JSON biểu diễn đường dẫn `C:\data\report.txt`, văn bản JSON phải có **hai backslash** ở mỗi vị trí:

```json
{"path":"C:\\data\\report.txt"}
```

Nếu bạn **nhúng chính văn bản JSON đó vào mã nguồn text block Java**, lại phải escape thêm một lần cho Java:

```java
String jsonBlock = """
        {"path":"C:\\\\data\\\\report.txt"}""";

String sameJson = "{\"path\":\"C:\\\\data\\\\report.txt\"}";
System.out.println(jsonBlock.equals(sameJson)); // true
```

Đọc từ ngoài vào trong:

1. `\\\\` trong **Java source** thành `\\` trong **giá trị `String`**.
2. JSON parser, khi thực sự phân tích văn bản JSON đó, chuyển `\\` thành **một backslash** trong trường `path`.

Text block không tự parse JSON. Việc hai đoạn Java bằng nhau chỉ chứng minh rằng chúng sinh **cùng văn bản JSON**, chưa kiểm tra giá trị sau khi JSON parser xử lý. Với chương trình thực tế, nên để thư viện JSON serialize dữ liệu thay vì tự viết JSON bằng nối chuỗi khi nội dung động có dấu nháy, backslash hoặc ký tự điều khiển.

### 7.2. Backslash trong biểu thức chính quy

Java regex engine cũng dùng `\` làm ký tự escape. Mẫu regex để khớp **một backslash thật** cần giá trị runtime gồm **hai backslash** (`\\`). Vì mã nguồn Java vẫn phải escape từng backslash, mã nguồn có **bốn**:

```java
String regexFromLiteral = "\\\\";
String regexFromBlock = """
        \\\\""";

System.out.println(
        regexFromLiteral.equals(regexFromBlock)
); // true

System.out.println(
        "C:\\logs\\app.txt".replaceAll(regexFromBlock, "/")
); // C:/logs/app.txt
```

Ở đây, text block **không phải regex raw string**. Cần phân biệt lớp escape của Java và lớp escape của regex. Nếu chỉ cần thay **ký tự cố định**, cách dễ hiểu hơn là dùng `String.replace`:

```java
String normalizedForDisplay = "C:\\logs\\app.txt".replace('\\', '/');
System.out.println(normalizedForDisplay); // C:/logs/app.txt
```

Phép thay thế này là **biến đổi văn bản**, không có nghĩa mọi đường dẫn trên mọi hệ điều hành đều trở nên hợp lệ hay tương đương. Khi làm việc với tệp thực, ưu tiên API `Path`.

## 8. Cách phát hiện lỗi backslash khó nhìn

Khi một đường dẫn in ra trông bất thường, hãy kiểm tra nội dung từng ký tự thay vì chỉ nhìn chuỗi trên màn hình. Một hàm hỗ trợ hiển thị các ký tự đặc biệt:

```java
static String visible(String text) {
    return text
            .replace("\\", "\\\\")
            .replace("\r", "\\r")
            .replace("\n", "\\n")
            .replace("\t", "\\t");
}
```

Đặt hàm này vào một class Java và gọi khi debug:

```java
String mistaken = """
        D:\new\test""";

System.out.println(visible(mistaken)); // D:\new\test
```

**Phân biệt khi đọc đầu ra:** kết quả hiển thị có hai ký tự `\` và `n` tại vị trí LF, hai ký tự `\` và `t` tại vị trí tab; đó là **ký hiệu minh họa ký tự điều khiển**, không phải bằng chứng rằng chuỗi gốc có backslash. Hãy đọc mã của `visible` để biết vì sao ký tự điều khiển được thay bằng ký hiệu dễ nhận. Nếu cần kiểm tra từng đơn vị ký tự, dùng `charAt(i)` hoặc `codePoints()`.

Có thể so sánh trực tiếp giá trị sau khi tạo text block:

```java
String expected = "C:\\data\\file.txt";
String actual = """
        C:\\data\\file.txt""";

if (!expected.equals(actual)) {
    throw new AssertionError("Text block không giữ đúng đường dẫn");
}
```

Đoạn kiểm tra này đặt bên trong một phương thức, ví dụ `main`; nó dùng `equals` để xác nhận nội dung, thay vì `==` (so sánh tham chiếu).

## 9. Lỗi thường gặp và cách sửa

| Lỗi | Vì sao sai? | Cách xử lý |
| --- | --- | --- |
| Gõ `C:\new\test` trực tiếp bên trong text block | `\n` và `\t` trở thành LF/tab. | Viết `C:\\new\\test` trong mã nguồn. |
| Gõ đường dẫn chứa `\P` hoặc `\D` | Không phải escape hợp lệ của Java. | Dùng `\\` cho mỗi backslash thật. |
| Gõ sai `\u` trong tên đường dẫn | Unicode escape được xử lý rất sớm trong mã nguồn Java; có thể gây lỗi biên dịch. | Dùng cặp `\\`, đừng gõ một backslash trước chữ `u`. |
| Dùng `\\server` ở đầu source cho UNC | `\\` ở mã nguồn chỉ còn một backslash trong giá trị. | Viết `\\\\server` ở đầu source. |
| Đặt dấu đóng text block trên dòng riêng khi chỉ muốn một path | Vô tình có LF cuối. | Đặt dấu đóng ngay sau ký tự cuối của đường dẫn hoặc thiết kế nội dung rõ LF. |
| Viết `\` ở cuối dòng nguồn để giữ backslash | Dấu đó có thể là line continuation, làm mất xuống dòng. | Dùng `\\` cho backslash; hiểu riêng việc có/không có LF. |
| Nhân đôi backslash sau khi đã đọc `String` từ input | Java không xử lý source escape lần thứ hai ở runtime. | Chỉ escape khi cần serialize sang một định dạng đích có quy tắc escape. |
| Tưởng text block tự escape JSON/regex | Java và JSON/regex là các lớp phân tích riêng. | Đếm escape theo từng lớp hoặc dùng thư viện phù hợp. |

## 10. Tự kiểm tra

**Câu 1.** Text block sau có giữ nguyên đường dẫn mong muốn `D:\new\test` không?

```java
String p = """
        D:\new\test""";
```

**Trả lời:** Không. `\n` là LF và `\t` là tab. Phải ghi `D:\\new\\test` trong source.

**Câu 2.** Nếu cần đường dẫn UNC có **hai** backslash thật ở đầu, mã nguồn Java cần bao nhiêu dấu backslash ở đầu?

**Trả lời:** Bốn dấu, viết `\\\\server` trong source để tạo `\\server` trong chuỗi.

**Câu 3.** Dấu `\` ngay trước xuống dòng thực của text block có tác dụng gì?

**Trả lời:** Nó là line continuation, loại bỏ dấu xuống dòng đó. Muốn **một** backslash thật trong chuỗi cần cặp `\\`; nếu ghép dòng có cả backslash thật, phải xét cả hai cơ chế.

**Câu 4.** Giá trị đọc từ một file cấu hình có đường dẫn `C:\data\file.txt` có tự động bị Java đổi `\f` thành form feed không?

**Trả lời:** Không theo cú pháp Java literal: bộ biên dịch chỉ xử lý escape của **mã nguồn**. Giá trị runtime được đọc là gì còn tùy parser của file cấu hình; nếu parser ấy có quy tắc escape riêng thì phải áp dụng quy tắc của nó.

## Ghi nhớ

- **Text block là `String`, không phải raw string.** Một backslash thật trong giá trị cần `\\` trong mã nguồn.
- Đường dẫn Windows có `\n`, `\t`, `\u` và các tổ hợp khác đặc biệt dễ gây lỗi hoặc biến dạng dữ liệu.
- Dấu `\` cuối dòng nguồn có thể nối dòng; dấu đóng `"""` trên dòng riêng thường giữ lại LF cuối.
- Đường dẫn mạng UNC có **hai backslash thật ở đầu**, nên cần **bốn backslash trong Java source**.
- Khi làm việc với file thực, ưu tiên `Path.of` và `Files`; khi làm việc với JSON/regex, phân biệt rõ các lớp escape.
- Chỉ thêm escape vào **literal trong mã nguồn** hoặc định dạng yêu cầu escape; không tự thay đổi chuỗi đã đọc từ hệ thống.

### Tài liệu Java hiện còn áp dụng

- [Oracle — Text Blocks (Java 25)](https://docs.oracle.com/en/java/javase/25/language/text-blocks.html): cú pháp text block, dòng cuối, escape, xử lý lề và line continuation.
- [Java Language Specification `3.10.6 — Text Blocks](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.10.6): định nghĩa cú pháp và giá trị text block.
- [Java Language Specification `3.3 — Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se25/html/jls-3.html#jls-3.3): xử lý Unicode escape trong mã nguồn Java.
- [Java SE API — `Path`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/nio/file/Path.html): cách biểu diễn và thao tác với đường dẫn theo file system.
