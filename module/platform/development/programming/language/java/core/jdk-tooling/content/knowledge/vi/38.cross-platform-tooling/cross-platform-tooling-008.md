# Line ending trong Java và công cụ cross-platform

Line ending là ký tự hoặc chuỗi ký tự đánh dấu điểm kết thúc một dòng trong file văn bản. Windows, Linux và macOS có quy ước lịch sử khác nhau; editor, Git, build tool, shell và Java I/O có thể đọc hoặc ghi các quy ước đó theo cách khác nhau.

Một dự án Java làm việc trên nhiều hệ điều hành cần thống nhất cách lưu file trong repository, đồng thời hiểu khi nào chương trình phải giữ nguyên line ending và khi nào cần ghi theo chuẩn của hệ điều hành hoặc giao thức. Nếu không kiểm soát, một thay đổi nhỏ có thể làm hàng trăm file xuất hiện trong Git diff, script shell không chạy, file cấu hình bị đọc sai hoặc dữ liệu trao đổi với hệ thống khác sai định dạng.

## 1. LF, CRLF và CR là gì?

Ba ký tự ASCII thường gặp:

| Tên | Escape trong Java | Unicode | Hex | Ý nghĩa |
|---|---|---:|---:|---|
| Line Feed (LF) | **\n** | U+000A | **0A** | Chuyển xuống dòng |
| Carriage Return (CR) | **\r** | U+000D | **0D** | Đưa vị trí về đầu dòng |
| CRLF | **\r\n** | U+000D U+000A | **0D 0A** | CR theo sau bởi LF |

Quy ước thường gặp:

- Linux và macOS hiện đại: LF.
- Windows: CRLF.
- macOS trước OS X: CR đơn, hiện nay rất hiếm.

CRLF gồm hai ký tự nhưng được hiểu là một line terminator. CR đơn vẫn xuất hiện trong một số file cũ và được Java hỗ trợ khi đọc text line.

Ví dụ cùng hai dòng alpha và beta:

~~~text
LF:    alpha\nbeta\n
CRLF:  alpha\r\nbeta\r\n
CR:    alpha\rbeta\r
~~~

Các chuỗi escape trên mô tả ký tự thực trong file. Nếu bạn nhìn thấy hai ký tự dấu gạch chéo ngược và n trong nội dung thay vì một line feed, đó là văn bản escape được in ra, không phải line ending LF.

### 1.1. Line ending khác encoding

Encoding quy định cách ký tự được chuyển thành byte; line ending là ký tự điều khiển nằm trong nội dung. UTF-8 có thể chứa LF, CR hoặc CRLF như các byte tương ứng. UTF-16 biểu diễn cùng ký tự bằng đơn vị 16-bit và thứ tự byte phù hợp.

Không nên kết luận file dùng LF chỉ vì file là UTF-8. Cũng không nên thay byte 0A trong mọi file một cách mù quáng: trong UTF-16 hoặc file nhị phân, byte đó có thể là một phần của dữ liệu khác.

Byte Order Mark (BOM) là dấu nhận diện encoding ở đầu file, ví dụ UTF-8 BOM EF BB BF. BOM không phải line ending. Một số tool chấp nhận BOM, một số parser hoặc compiler có thể xử lý khác nhau; hãy thống nhất UTF-8 có BOM hay không theo định dạng và toolchain của dự án.

### 1.2. Line ending cuối file

File có thể kết thúc ngay sau ký tự cuối cùng hoặc có thêm một line terminator ở cuối:

~~~text
"alpha\nbeta"   // Không có final newline
"alpha\nbeta\n" // Có final newline
~~~

Final newline không tạo thêm một dòng rỗng trong cách đếm của String.lines() hoặc BufferedReader.readLine(). Nó vẫn là một phần của nội dung file và có thể ảnh hưởng tới diff, shell script hoặc công cụ đọc file.

Với source code, cấu hình, Markdown và script, dự án thường chọn có final newline để Git diff và các công cụ Unix xử lý nhất quán. Với dữ liệu có schema riêng, hãy tuân thủ format của dữ liệu đó.

## 2. Vì sao line ending gây lỗi cross-platform?

Một file source có thể biên dịch trên Windows nhưng tạo diff lớn khi mở và lưu bằng editor trên Linux. Script shell có CRLF có thể làm interpreter đọc phần CR ở cuối dòng như một phần của lệnh hoặc đường dẫn interpreter. Một file .bat bị đổi toàn bộ sang LF có thể gây vấn đề với một số tool Windows cũ.

Các tình huống phổ biến:

- Developer Windows commit file CRLF; developer Linux checkout và editor lưu LF; Git báo thay đổi trên toàn bộ file.
- File .sh có CRLF khiến shebang hoặc shell báo lỗi như bad interpreter hay ^M.
- File .bat/.cmd cần CRLF trong working tree nhưng bị đổi thành LF.
- Test so sánh chuỗi chính xác thất bại vì output dùng CRLF còn expected value dùng LF.
- Một parser xử lý LF nhưng quên trường hợp CRLF hoặc CR.
- File CSV hoặc text export bị trộn nhiều kiểu line ending.
- Một chương trình ghi file bằng line separator của máy hiện tại trong khi định dạng đầu ra yêu cầu LF cố định.
- Một HTTP client tự ghép header bằng line separator của hệ điều hành thay vì CRLF theo giao thức.

Cách giải quyết tốt là xác định chuẩn cho từng loại file và để Git/editor áp dụng nhất quán. Ở tầng Java, chọn API đọc/ghi theo mục đích của dữ liệu.

## 3. Java đọc line ending như thế nào?

Java source compiler nhận diện LF, CR và CRLF là line terminator. Với Java I/O, BufferedReader.readLine() cũng nhận cả ba dạng và trả về nội dung dòng mà không bao gồm ký tự kết thúc.

### 3.1. BufferedReader.readLine()

Ví dụ:

~~~java
try (BufferedReader reader =
         Files.newBufferedReader(path, StandardCharsets.UTF_8)) {
    String line;
    while ((line = reader.readLine()) != null) {
        System.out.println(line);
    }
}
~~~

readLine() nhận:

- LF đơn.
- CR đơn.
- CRLF, được tính là một terminator.

Phương thức loại bỏ line terminator khi trả về String. Vì vậy, sau khi đọc bằng readLine(), bạn không còn biết dòng ban đầu kết thúc bằng LF, CR hay CRLF.

Nếu ứng dụng chỉ cần xử lý từng dòng, đây thường là hành vi phù hợp. Nếu cần bảo toàn chính xác định dạng nguồn, hãy đọc toàn bộ nội dung hoặc byte trước khi phân tích.

### 3.2. Files.readAllLines()

Files.readAllLines(path, charset) đọc file thành List<String>. API nhận CRLF, LF và CR làm dấu phân cách; mỗi phần tử không chứa terminator.

~~~java
List<String> lines =
    Files.readAllLines(path, StandardCharsets.UTF_8);
~~~

Cách này thuận tiện cho file nhỏ. Không dùng nó để xử lý file rất lớn vì toàn bộ dòng được giữ trong bộ nhớ. Tương tự BufferedReader.readLine(), API này không giữ lại kiểu line ending ban đầu.

### 3.3. String.lines() từ Java 11

String.lines() tạo stream các dòng và nhận LF, CRLF hoặc CR:

~~~java
String content = "alpha\r\nbeta\ngamma\r";
long count = content.lines().count();

System.out.println("LINES=" + count);
~~~

Output:

~~~text
LINES=3
~~~

String.lines() không đưa line terminator vào từng phần tử. Nếu String kết thúc bằng line terminator, nó không tạo thêm một dòng rỗng sau terminator đó. Chuỗi rỗng có zero lines.

Nếu dùng regex, split("\\R", -1) có thể giữ cả phần tử rỗng cuối cùng. Cần chú ý rằng split("\\R") mặc định loại bỏ các phần tử rỗng ở cuối, nên kết quả khác với cách xử lý của String.lines().

### 3.4. Khi cần giữ nguyên line ending

Dùng Files.readString() khi cần giữ nguyên toàn bộ chuỗi ký tự, bao gồm line separator ở giữa và cuối file:

~~~java
String raw = Files.readString(path, StandardCharsets.UTF_8);
~~~

Files.readString() không tự chuẩn hóa CRLF thành LF. Nếu file có CRLF, String chứa CRLF; nếu file có LF, String chứa LF.

Ví dụ, hai file có nội dung hiển thị giống nhau có thể tạo ra hai String khác nhau:

~~~java
String lf = "alpha\nbeta\n";
String crlf = "alpha\r\nbeta\r\n";

System.out.println(lf.equals(crlf)); // false
~~~

Đây là điều cần nhớ khi viết test so sánh file, hash nội dung, ký số hoặc tạo bản sao byte-for-byte.

## 4. Java ghi line ending như thế nào?

Java cung cấp hai kiểu hành vi chính: ghi theo line separator của JVM hiện tại hoặc ghi một chuỗi separator được quy định rõ.

### 4.1. System.lineSeparator()

System.lineSeparator() trả về separator phụ thuộc hệ điều hành/JVM:

- Unix/Linux/macOS hiện đại: LF.
- Microsoft Windows: CRLF.

~~~java
String nativeSeparator = System.lineSeparator();
System.out.println(nativeSeparator.equals("\r\n") ? "CRLF" : "LF");
~~~

Giá trị này là giá trị ban đầu của system property line.separator khi JVM khởi động. Không dùng nó như một chuẩn universal cho mọi file hoặc mọi protocol.

### 4.2. BufferedWriter.newLine()

BufferedWriter.newLine() ghi line separator của hệ điều hành theo line.separator:

~~~java
try (BufferedWriter writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("alpha");
    writer.newLine();
    writer.write("beta");
    writer.newLine();
}
~~~

Trên Windows, file sẽ chứa CRLF; trên Linux/macOS hiện đại, file sẽ chứa LF. Dùng API này khi yêu cầu là ghi text line theo quy ước của môi trường chạy.

### 4.3. PrintWriter.println()

PrintWriter.println() cũng kết thúc dòng bằng line separator của hệ điều hành:

~~~java
try (PrintWriter writer =
         new PrintWriter(
             Files.newBufferedWriter(path, StandardCharsets.UTF_8))) {
    writer.println("alpha");
    writer.println("beta");

    if (writer.checkError()) {
        throw new IOException("Could not write output");
    }
}
~~~

PrintWriter có một điểm cần chú ý: các phương thức ghi không ném IOException theo cách thông thường; hãy kiểm tra checkError() khi cần phát hiện lỗi ghi.

Không gọi println() nếu format yêu cầu LF cố định và bạn đang chạy trên Windows. Khi đó, dùng separator tường minh.

### 4.4. Ghi LF cố định

Nếu file cần LF trên mọi OS, ghi trực tiếp LF:

~~~java
String content = "alpha\nbeta\n";
Files.writeString(path, content, StandardCharsets.UTF_8);
~~~

Files.writeString() ghi đúng các ký tự trong CharSequence, bao gồm line separator đã có trong chuỗi; API không tự đổi LF thành CRLF.

Một lựa chọn khác:

~~~java
try (BufferedWriter writer =
         Files.newBufferedWriter(path, StandardCharsets.UTF_8)) {
    writer.write("alpha\n");
    writer.write("beta\n");
}
~~~

Không dùng writer.newLine() trong đoạn code này nếu mục tiêu là luôn tạo LF trên mọi hệ điều hành.

### 4.5. Files.write() với danh sách dòng

Files.write(path, lines, charset) nhận một danh sách dòng và tự kết thúc từng phần tử bằng line separator của nền tảng:

~~~java
Files.write(
    path,
    List.of("alpha", "beta"),
    StandardCharsets.UTF_8
);
~~~

Nếu cần byte-for-byte hoặc line ending cố định, hãy tự tạo chuỗi với separator đã chọn rồi dùng Files.writeString() hoặc ghi byte rõ ràng. Files.write() với Iterable là API tiện lợi cho native text output.

### 4.6. Chọn API theo yêu cầu

| Yêu cầu | API phù hợp |
|---|---|
| Đọc từng dòng, không cần biết separator gốc | BufferedReader.readLine() |
| Đọc file nhỏ thành danh sách dòng | Files.readAllLines() |
| Tách String thành stream dòng | String.lines() |
| Giữ nguyên separator trong file | Files.readString() |
| Ghi native line ending | BufferedWriter.newLine() hoặc PrintWriter.println() |
| Ghi LF cố định | Files.writeString() với LF |
| Ghi CRLF cố định | Files.writeString() với CRLF |
| Ghi byte chính xác | Files.write() với byte array |

## 5. Line ending của file và line ending của protocol

Không phải mọi dữ liệu nhiều dòng đều nên dùng separator của hệ điều hành. Một file source trong Git có thể dùng LF cố định; một giao thức mạng có thể bắt buộc CRLF; output cho người dùng có thể dùng native line ending.

Ví dụ, HTTP/1.1 yêu cầu CRLF để kết thúc dòng trong phần message framing. Nếu tự triển khai protocol, phải tuân thủ đúng spec; không thay CRLF bằng System.lineSeparator() vì chương trình chạy trên Linux sẽ tạo LF. Trong ứng dụng thông thường, hãy dùng HTTP client/server library để thư viện quản lý framing.

Một số ví dụ khác:

- File .sh: thường cần LF và shebang ở dòng đầu.
- File .bat/.cmd: có thể yêu cầu CRLF theo toolchain Windows của dự án.
- File .java, .kt, .gradle, .xml, .properties, .yml: thường chọn LF trong repository.
- CSV/text export: chọn một chuẩn cố định theo hệ thống nhận file và tài liệu tích hợp.
- SMTP hoặc protocol dạng dòng: theo đúng chuẩn protocol, không theo OS.
- Binary như .jar, .class, .png, .zip: không áp dụng line-ending conversion.

Khi giao tiếp với process bên ngoài bằng ProcessBuilder, nhớ rằng script interpreter có quy tắc riêng. Một shell script chạy trên Linux nên có LF; batch script trên Windows nên theo định dạng được command processor và tool liên quan hỗ trợ.

## 6. Chuẩn hóa line ending trong Git

Git có thể chuẩn hóa text file thành LF trong repository/index, rồi chuyển sang LF hoặc CRLF trong working tree theo cấu hình. Đây là cách phổ biến để các contributor trên Windows, Linux và macOS không tạo diff chỉ vì khác hệ điều hành.

### 6.1. .gitattributes

Nên định nghĩa chính sách theo file trong .gitattributes ở root repository:

~~~gitattributes
# Detect text files and normalize their content in the Git index.
* text=auto

# Keep source, build files and Unix scripts as LF in the working tree.
*.java text eol=lf
*.kt text eol=lf
*.gradle text eol=lf
*.gradle.kts text eol=lf
*.properties text eol=lf
*.xml text eol=lf
*.yml text eol=lf
*.yaml text eol=lf
*.sh text eol=lf

# Use CRLF in Windows command scripts in the working tree.
*.bat text eol=crlf
*.cmd text eol=crlf

# Binary files must never be normalized as text.
*.jar binary
*.class binary
*.png binary
*.jpg binary
*.zip binary
~~~

Ý nghĩa:

- text=auto: Git tự nhận diện text file và chuẩn hóa line ending trong index.
- text: xác định rõ file là text và bật conversion.
- eol=lf: working tree dùng LF.
- eol=crlf: working tree dùng CRLF.
- binary hoặc -text: tắt text conversion cho file nhị phân.

Khi text được bật, Git chuẩn hóa line ending của text file thành LF trong index khi add. Khi checkout, eol quyết định line ending trong working tree. Ví dụ .bat có thể được lưu trong index bằng LF nhưng checkout thành CRLF trên máy Windows theo cấu hình trên.

Không áp dụng text cho archive, ảnh, executable hoặc file nhị phân khác. Nếu Git nhận nhầm binary là text, conversion có thể làm hỏng nội dung.

### 6.2. core.autocrlf và core.eol

Git có các cấu hình cá nhân:

~~~bash
git config --global core.autocrlf true
~~~

Trên Windows, true thường tạo CRLF trong working tree và chuẩn hóa khi add. Trên macOS/Linux, nhiều người dùng:

~~~bash
git config --global core.autocrlf input
~~~

input chuẩn hóa CRLF thành LF khi add và không chuyển LF thành CRLF khi checkout. core.eol có các giá trị lf, crlf, native để chọn line ending cho text file khi checkout trong các trường hợp cấu hình đó được áp dụng.

core.autocrlf là cấu hình môi trường của contributor. .gitattributes là chính sách được lưu trong repository và kiểm soát từng loại file. Dự án nhiều hệ điều hành nên dùng .gitattributes làm nguồn quy định chính; đừng yêu cầu mỗi developer tự nhớ một cấu hình global khác nhau.

### 6.3. Kiểm tra Git đang áp dụng gì

Xem line ending của file trong index và working tree:

~~~bash
git ls-files --eol
~~~

Kết quả thường có dạng:

~~~text
i/lf    w/crlf  attr/text eol=crlf  script.bat
i/lf    w/lf    attr/text eol=lf    src/Main.java
~~~

Trong đó:

- i/lf: index chứa LF.
- w/crlf: working tree chứa CRLF.
- attr/...: thuộc tính Git áp dụng cho file.

Kiểm tra thuộc tính theo đường dẫn:

~~~bash
git check-attr text eol -- src/Main.java script.bat
~~~

Kiểm tra cấu hình hiệu lực và nguồn cấu hình:

~~~bash
git config --show-origin --get core.autocrlf
git config --show-origin --get core.eol
~~~

Dùng git diff --ignore-space-at-eol để xem nội dung thay đổi mà bỏ qua khác biệt ở cuối dòng khi đang chẩn đoán. Đừng dùng tùy chọn này để che một lỗi nội dung thật trong review.

### 6.4. Chuẩn hóa repository đã có file cũ

Khi thêm hoặc sửa .gitattributes, các file đã được track có thể chưa được chuẩn hóa trong index. Trong một branch riêng, sau khi bảo đảm working tree đã lưu các thay đổi cần thiết:

~~~bash
git add --renormalize .
git status
git diff --cached --stat
~~~

git add --renormalize . áp dụng lại clean filter/line-ending conversion cho các file đã track. Đọc kỹ danh sách thay đổi và xác nhận các file binary không bị đụng tới trước khi commit.

Nếu diff chỉ thay line ending, review có thể dùng git diff --ignore-space-at-eol để kiểm tra phần nội dung. Tránh thực hiện normalization giữa lúc đang có thay đổi chưa lưu hoặc trên branch chứa nhiều công việc không liên quan.

## 7. Chuẩn hóa editor bằng EditorConfig

.gitattributes điều khiển Git. EditorConfig hướng dẫn editor lưu file theo cùng một quy ước. Hai cơ chế bổ sung cho nhau.

Tạo .editorconfig ở root repository:

~~~ini
root = true

[*]
charset = utf-8
end_of_line = lf
insert_final_newline = true
trim_trailing_whitespace = true

[*.bat]
end_of_line = crlf

[*.cmd]
end_of_line = crlf
~~~

Các thuộc tính:

- charset = utf-8: thống nhất encoding.
- end_of_line = lf hoặc crlf: chọn line ending khi editor lưu.
- insert_final_newline = true: thêm newline ở cuối file.
- trim_trailing_whitespace = true: xóa whitespace ở cuối dòng.
- root = true: dừng tìm cấu hình EditorConfig ở thư mục cha.

Editor phải hỗ trợ EditorConfig hoặc có plugin tương ứng. Sau khi thêm file, mở lại file trong editor và kiểm tra trạng thái line ending hiển thị ở thanh status. EditorConfig không tự sửa mọi file đã tồn tại; một số editor chỉ áp dụng khi file được mở hoặc lưu.

Nếu một số định dạng có quy ước riêng, tạo section cụ thể cho extension đó. Đảm bảo .editorconfig và .gitattributes không mâu thuẫn về cùng một loại file.

## 8. Phân biệt line ending với encoding và BOM trong Java

Khi đọc file text, chỉ định charset rõ ràng để tránh kết quả phụ thuộc cấu hình mặc định của máy:

~~~java
String text = Files.readString(path, StandardCharsets.UTF_8);
~~~

Files.readString(path, charset) đọc cả line separator và giữ nguyên separator trong String. Files.readAllLines(path, charset) thì tách dòng và bỏ terminator.

Nếu file UTF-8 có BOM, decoder UTF-8 thông thường có thể trả BOM dưới dạng ký tự U+FEFF ở đầu String. BOM không tự biến thành newline. Nếu format yêu cầu bỏ BOM, hãy xử lý có chủ đích ở đầu nội dung; không xóa U+FEFF ở mọi vị trí vì ký tự đó có thể là dữ liệu thật.

Ví dụ:

~~~java
if (!text.isEmpty() && text.charAt(0) == '\uFEFF') {
    text = text.substring(1);
}
~~~

Chỉ làm bước này khi định dạng đầu vào cho phép/đòi hỏi bỏ UTF-8 BOM. Không dùng trim() để xóa line ending vì trim() còn loại bỏ whitespace ở đầu/cuối nội dung và có thể làm mất dữ liệu.

## 9. Thực hành Java 17+: đọc và ghi nhiều kiểu line ending

Ví dụ sau tạo file LF, CRLF, CR và mixed endings, rồi kiểm tra cách Java đọc và ghi. Chương trình chạy độc lập trên Java 17 trở lên.

Tạo file LineEndingProbe.java:

~~~java
import java.io.BufferedReader;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.PrintWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;

public final class LineEndingProbe {
    private static String classify(String separator) {
        if ("\r\n".equals(separator)) return "CRLF";
        if ("\n".equals(separator)) return "LF";
        if ("\r".equals(separator)) return "CR";
        throw new IllegalStateException("Unexpected line separator");
    }

    private static int count(String value, String token) {
        int result = 0;
        for (int i = 0; i <= value.length() - token.length();) {
            if (value.startsWith(token, i)) {
                result++;
                i += token.length();
            } else {
                i++;
            }
        }
        return result;
    }

    private static void inspect(Path file, String expected, int expectedLines)
            throws IOException {
        Files.writeString(file, expected, StandardCharsets.UTF_8);
        String raw = Files.readString(file, StandardCharsets.UTF_8);

        if (!raw.equals(expected)) {
            throw new AssertionError("Files.readString changed line separators");
        }

        int crlf = count(raw, "\r\n");
        int lf = count(raw, "\n") - crlf;
        int cr = count(raw, "\r") - crlf;

        long streamLines = raw.lines().count();
        List<String> readerLines = new ArrayList<>();

        try (BufferedReader reader =
                 Files.newBufferedReader(file, StandardCharsets.UTF_8)) {
            String line;
            while ((line = reader.readLine()) != null) {
                readerLines.add(line);
            }
        }

        List<String> allLines =
            Files.readAllLines(file, StandardCharsets.UTF_8);

        if (streamLines != expectedLines
                || readerLines.size() != expectedLines
                || allLines.size() != expectedLines) {
            throw new AssertionError("Line count mismatch for " + file.getFileName());
        }

        System.out.println(file.getFileName()
                + ": CRLF=" + crlf
                + " LF_ONLY=" + lf
                + " CR_ONLY=" + cr
                + " LINES=" + streamLines);
        System.out.println("  READ_LINES=" + String.join("|", readerLines));
    }

    public static void main(String[] args) throws Exception {
        Path dir = Path.of(args[0]);
        Files.createDirectories(dir);

        System.out.println(
            "SYSTEM_LINE_SEPARATOR=" + classify(System.lineSeparator())
        );

        inspect(dir.resolve("lf.txt"), "one\ntwo\n", 2);
        inspect(dir.resolve("crlf.txt"), "one\r\ntwo\r\n", 2);
        inspect(dir.resolve("cr.txt"), "one\rtwo\r", 2);
        inspect(dir.resolve("mixed.txt"), "one\r\ntwo\nthree\rfour", 4);

        Path fixedLf = dir.resolve("fixed-lf.txt");
        Files.writeString(fixedLf, "one\ntwo\n", StandardCharsets.UTF_8);
        String fixed = Files.readString(fixedLf, StandardCharsets.UTF_8);

        if (!fixed.equals("one\ntwo\n")) {
            throw new AssertionError("Fixed LF changed");
        }
        System.out.println("FILES_WRITE_STRING_PRESERVES_LF=true");

        Path nativeWriter = dir.resolve("native-writer.txt");
        try (BufferedWriter writer =
                 Files.newBufferedWriter(nativeWriter, StandardCharsets.UTF_8)) {
            writer.write("one");
            writer.newLine();
            writer.write("two");
            writer.newLine();
        }

        String nativeText = Files.readString(nativeWriter, StandardCharsets.UTF_8);
        String expectedNative = "one" + System.lineSeparator()
            + "two" + System.lineSeparator();

        if (!nativeText.equals(expectedNative)) {
            throw new AssertionError("BufferedWriter.newLine mismatch");
        }
        System.out.println(
            "BUFFERED_WRITER_NEWLINE=" + classify(System.lineSeparator())
        );

        Path printWriterFile = dir.resolve("print-writer.txt");
        try (PrintWriter writer = new PrintWriter(
                Files.newBufferedWriter(printWriterFile, StandardCharsets.UTF_8))) {
            writer.println("one");
            writer.println("two");
            if (writer.checkError()) {
                throw new IllegalStateException("PrintWriter error");
            }
        }

        String printText = Files.readString(printWriterFile, StandardCharsets.UTF_8);
        if (!printText.equals(expectedNative)) {
            throw new AssertionError("PrintWriter.println mismatch");
        }
        System.out.println(
            "PRINT_WRITER_PRINTLN=" + classify(System.lineSeparator())
        );

        Path bomFile = dir.resolve("utf8-bom.txt");
        byte[] bomText = {
            (byte) 0xEF, (byte) 0xBB, (byte) 0xBF, 'x', '\n'
        };
        Files.write(bomFile, bomText);

        String withBom = Files.readString(bomFile, StandardCharsets.UTF_8);
        if (withBom.isEmpty() || withBom.charAt(0) != '\uFEFF') {
            throw new AssertionError("UTF-8 BOM was not preserved");
        }
        System.out.println("UTF8_BOM_FIRST_CHAR_UFEFF=true");
        System.out.println("LINE_ENDING_TEST=PASS");
    }
}
~~~

Biên dịch và chạy:

~~~powershell
$JdkHome = "C:\path\to\jdk-17"

& "$JdkHome\bin\javac.exe" --release 17 -d out LineEndingProbe.java
& "$JdkHome\bin\java.exe" -cp out LineEndingProbe data
~~~

Output đã kiểm thử trên Windows với Amazon Corretto 17.0.15+6-LTS:

~~~text
SYSTEM_LINE_SEPARATOR=CRLF
lf.txt: CRLF=0 LF_ONLY=2 CR_ONLY=0 LINES=2
  READ_LINES=one|two
crlf.txt: CRLF=2 LF_ONLY=0 CR_ONLY=0 LINES=2
  READ_LINES=one|two
cr.txt: CRLF=0 LF_ONLY=0 CR_ONLY=2 LINES=2
  READ_LINES=one|two
mixed.txt: CRLF=1 LF_ONLY=1 CR_ONLY=1 LINES=4
  READ_LINES=one|two|three|four
FILES_WRITE_STRING_PRESERVES_LF=true
BUFFERED_WRITER_NEWLINE=CRLF
PRINT_WRITER_PRINTLN=CRLF
UTF8_BOM_FIRST_CHAR_UFEFF=true
LINE_ENDING_TEST=PASS
~~~

Trên Linux/macOS hiện đại, dòng SYSTEM_LINE_SEPARATOR, BUFFERED_WRITER_NEWLINE và PRINT_WRITER_PRINTLN sẽ là LF. Các file lf.txt, crlf.txt, cr.txt và mixed.txt vẫn giữ đúng separator mà chương trình đã ghi vào.

## 10. Kiểm tra và sửa lỗi line ending

Khi một file bất ngờ xuất hiện trong Git diff, hãy kiểm tra line ending trước khi chỉnh sửa thủ công.

### 10.1. Nhận diện file có mixed line endings

Dùng Git:

~~~bash
git ls-files --eol
~~~

Hoặc dùng PowerShell để đếm byte CRLF/LF/CR trong file UTF-8 không BOM:

~~~powershell
$bytes = [IO.File]::ReadAllBytes("src\Main.java")
$text = [Text.Encoding]::UTF8.GetString($bytes)
$cr = [char]13
$lf = [char]10

$crlf = [regex]::Matches($text, [regex]::Escape([string]$cr + [string]$lf)).Count
$crCount = ($text.ToCharArray() | Where-Object { $_ -eq $cr }).Count
$lfCount = ($text.ToCharArray() | Where-Object { $_ -eq $lf }).Count
$lfOnly = $lfCount - $crlf
$crOnly = $crCount - $crlf

"CRLF=$crlf LF_ONLY=$lfOnly CR_ONLY=$crOnly"
~~~

Lệnh PowerShell trên giả định file là UTF-8 không BOM và đang được giải mã bằng UTF-8. Với UTF-16 hoặc binary, hãy dùng công cụ hiểu encoding/format đó; không dùng phép đếm byte này một cách trực tiếp.

### 10.2. Đổi line ending trong editor

Trong VS Code, trạng thái LF hoặc CRLF thường xuất hiện ở thanh status. Chọn giá trị đó để đổi kiểu line ending của file đang mở, sau đó lưu. IntelliJ IDEA có lựa chọn line separator trong status bar hoặc menu File tùy phiên bản.

Sau khi lưu, chạy:

~~~bash
git diff --check
git diff -- src/Main.java
git ls-files --eol
~~~

Kiểm tra xem diff còn thay đổi nội dung thật hay chỉ là line ending.

### 10.3. Tránh normalize nhầm binary

Nếu Git báo binary bị thay đổi sau khi thêm text=auto, kiểm tra thuộc tính:

~~~bash
git check-attr text eol -- path/to/file
~~~

Đánh dấu file binary bằng binary hoặc -text trong .gitattributes. Đừng dùng git add --renormalize . trước khi kiểm tra pattern và phạm vi file sẽ bị tác động.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Git diff hiện cả file dù chỉ sửa một dòng | Working tree dùng CRLF còn index dùng LF hoặc ngược lại | Thêm .gitattributes, kiểm tra git ls-files --eol |
| .sh báo bad interpreter hoặc ^M | Script có CRLF ở shebang | Đặt *.sh text eol=lf, chuyển file về LF |
| .bat/.cmd bị thay đổi line ending liên tục | Editor hoặc Git đang áp dụng LF cho batch file | Đặt *.bat text eol=crlf và *.cmd text eol=crlf |
| Test equals thất bại trên Windows | Expected LF, actual CRLF | Chuẩn hóa dữ liệu theo contract hoặc so sánh theo dòng nếu separator không có ý nghĩa |
| Parser chỉ đọc được file Linux | Code chỉ tìm LF | Dùng BufferedReader.readLine(), String.lines() hoặc parser hiểu CRLF/CR |
| readLine() đọc đúng nhưng file ghi ra bị đổi | Đọc bỏ terminator rồi ghi bằng newLine() | Chọn separator đích rõ ràng; không kỳ vọng round-trip bảo toàn |
| File có dòng rỗng cuối bị mất | String.lines() không tạo dòng rỗng sau final terminator; split() mặc định bỏ trailing empty | Dùng parser phù hợp hoặc split("\\R", -1) khi cần giữ phần tử rỗng cuối |
| File có ký tự lạ đầu nội dung | BOM được giữ lại như U+FEFF | Xử lý BOM theo format, chỉ tại đầu file |
| Binary bị hỏng sau khi add | Git áp dụng text conversion nhầm | Đánh dấu binary/-text và khôi phục binary từ nguồn chuẩn |
| Windows và Linux tạo output khác nhau | Dùng System.lineSeparator()/println() cho format cần separator cố định | Ghi LF hoặc CRLF tường minh theo specification |
| HTTP request tự ghép bị lỗi | Dùng LF/native separator thay CRLF của protocol | Dùng HTTP library hoặc tạo framing đúng chuẩn CRLF |
| File vẫn có mixed endings sau khi sửa | Một số dòng chưa được normalize hoặc tool ghi lại khác kiểu | Chạy kiểm tra toàn file và chuẩn hóa bằng editor/Git |

## 12. Quy trình thống nhất cho nhóm Java

Một quy trình đơn giản có thể áp dụng trong dự án đa hệ điều hành:

1. Chọn LF cho Java source, build script, cấu hình và tài liệu trong repository.
2. Chọn CRLF cho .bat/.cmd nếu toolchain Windows của dự án cần.
3. Đánh dấu rõ binary bằng binary hoặc -text.
4. Commit .gitattributes để Git chuẩn hóa index và working tree theo từng loại file.
5. Commit .editorconfig để editor tự lưu đúng line ending và encoding.
6. Dùng BufferedReader.readLine()/String.lines() cho logic xử lý dòng.
7. Dùng Files.readString() nếu cần giữ nguyên separator; dùng Files.writeString() với LF hoặc CRLF khi cần output cố định.
8. Dùng System.lineSeparator(), BufferedWriter.newLine() hoặc println() khi thật sự muốn native line ending.
9. Với protocol, tuân thủ line terminator do protocol quy định.
10. Sau khi thêm chính sách mới, kiểm tra git ls-files --eol, review diff và chỉ sau đó mới commit normalization.

Không thay đổi hàng loạt line ending trên branch đang có thay đổi chưa lưu. Nếu repository đã có nhiều file trộn kiểu, tạo thay đổi normalization riêng để review dễ dàng và tránh trộn với refactor logic.

## 13. Checklist trước khi hoàn tất

- [ ] Đã phân biệt LF, CRLF và CR.
- [ ] Đã phân biệt line ending với encoding và BOM.
- [ ] Đã quyết định final newline policy.
- [ ] Đã chọn chuẩn cho source, config, script, data và binary.
- [ ] .gitattributes có text/eol phù hợp cho từng loại file.
- [ ] .editorconfig có charset, end_of_line và insert_final_newline.
- [ ] Java đọc dòng bằng API nhận LF/CRLF/CR khi cần.
- [ ] Java ghi native hay fixed line ending đúng yêu cầu.
- [ ] Test không giả định separator của một OS khi format không yêu cầu.
- [ ] Script shell dùng LF và batch script dùng line ending được hỗ trợ.
- [ ] Protocol network dùng đúng CRLF nếu specification yêu cầu.
- [ ] Git binary files được loại khỏi text conversion.
- [ ] Đã kiểm tra git ls-files --eol và git diff --check.
- [ ] Đã review kỹ diff sau git add --renormalize ..

## 14. Ghi nhớ

LF là U+000A, CR là U+000D, CRLF là hai ký tự CR rồi LF nhưng được xem là một line terminator. Windows thường dùng CRLF; Linux và macOS hiện đại dùng LF. Encoding và BOM là vấn đề riêng của cách biểu diễn văn bản.

Java BufferedReader.readLine(), Files.readAllLines() và String.lines() nhận LF, CRLF và CR nhưng loại bỏ separator khi trả về dòng. Files.readString() giữ nguyên separator; Files.writeString() ghi đúng các ký tự trong chuỗi. BufferedWriter.newLine() và PrintWriter.println() dùng line separator của hệ điều hành.

Trong dự án đa hệ điều hành, dùng .gitattributes để chuẩn hóa file trong Git, .editorconfig để đồng bộ editor và chọn API Java theo mục tiêu của dữ liệu. Đừng dùng native separator cho file hoặc protocol có yêu cầu cố định; luôn kiểm tra diff và định dạng sau khi thay đổi chính sách.

Tài liệu tham khảo:

- [Git — gitattributes: End-of-line conversion](https://git-scm.com/docs/gitattributes)
- [Git — core.autocrlf and core.safecrlf](https://git-scm.com/docs/git-config)
- [GitHub Docs — Configuring Git to handle line endings](https://docs.github.com/en/get-started/git-basics/configuring-git-to-handle-line-endings)
- [EditorConfig Specification](https://spec.editorconfig.org/)
- [BufferedReader — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedReader.html)
- [BufferedWriter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/BufferedWriter.html)
- [PrintWriter — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/PrintWriter.html)
- [System.lineSeparator — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/System.html)
- [Files — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/file/Files.html)
- [String.lines — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [Java Language Specification — Line Terminators](https://docs.oracle.com/javase/specs/jls/se17/jls17.pdf)